#!/usr/bin/python

"""
//
//  Copyright (c) 2016 Petr Sleptsov <spetr@bk.ru>
//
//  This file is part of Heightmap2GCode.
//
//  Heightmap2GCode is free software: you can redistribute it and/or modify
//  it under the terms of the GNU General Public License as published by
//  the Free Software Foundation, either version 3 of the License, or
//  (at your option) any later version.
//
//  Heightmap2GCode is distributed in the hope that it will be useful,
//  but WITHOUT ANY WARRANTY; without even the implied warranty of
//  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
//  GNU General Public License for more details.
//
//  You should have received a copy of the GNU General Public License
//  along with Heightmap2GCode.  If not, see <http://www.gnu.org/licenses/>.
//
"""

import cv2
import sys
import math
import numpy
import argparse
from PIL import Image, ImageDraw

c_points = [[-1,-1], [0, -1], [1, -1], [-1, 0], [1, 0], [-1, 1], [0, 1], [1, 1]]

def normalize(image):
	pixels = image.load()
	width = image.size[0]
	length = image.size[1]

	matrix = []
	for i in range(width):
		matrix.append([])
		for j in range(length):
			a = pixels[i, j][0]
			b = pixels[i, j][1]
			c = pixels[i, j][2]
			S = (a + b + c) // 3
			matrix [i].append(S)
	return matrix
	
def get_levels(matrix, width, length):
	cache = {}
	levels = []
	for i in range(width):
		for j in range(length):
			key = matrix [i][j]
			if not key in cache and key != 255:
				cache [key] = 1
				levels.append(key)
	levels.sort()
	return levels
	
def draw_level(canvas, matrix, level):
	color = 0
	width = canvas.size[0]
	length = canvas.size[1]
	draw = ImageDraw.Draw(canvas)
	pixels = canvas.load()
	for i in range(width):
		for j in range(length):
			if level == matrix[i][j] and pixels[i, j] != 0:
				color = 0
			else:
				color = 255
			draw.point((i, j), color)

def detect_edge(pixels, x, y, width, length, color):
	if pixels[x, y] == color:
		for point in c_points:
			dx = x + point[0]
			dy = y + point[1]
			if dx >= 0 and dy >= 0 and dx < width and dy < length:
				if pixels[dx, dy] != color:
					return True
			else:
				return True
	return False

def detect_contours(mask):
	mask_arr = numpy.array(mask)
	(cnts, _) = cv2.findContours(mask_arr.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
	c = sorted(cnts, key = cv2.contourArea, reverse = True)
	return c

def draw_path(image, mill):
	width = image.size[0]
	length = image.size[1]

	edge = Image.new('L', image.size, 255)
	edge_draw = ImageDraw.Draw(edge)
	canvas = image.copy()
	cache = image.copy()
	
	mask = image.copy()
	mask_state = False
	state = True
	count_edge = 0
	c = []
	while state:
		count = 0
		pixels = canvas.load()
		draw = ImageDraw.Draw(cache)
		state = False
		for i in range(width):
			for j in range(length):
				detected = detect_edge(pixels, i, j, width, length, 0)
				if detected:
					draw.ellipse((math.ceil(i - mill), math.ceil(j - mill), math.floor(i + mill), math.floor(j + mill)), fill = 255, outline = 255)
					count += 1
				state = state or detected
		if state:
			if not mask_state:
				mask = cache.copy()
				mask_state = True
			cache_pixels = cache.load()
			c += detect_contours(cache)
			for i in range(width):
				for j in range(length):
					detected = detect_edge(cache_pixels, i, j, width, length, 255)
					if detected:
#						edge_draw.point((i, j), 0)
						count_edge += 1
		canvas = cache.copy()
	return (edge, mask, count_edge, c)
	
def merge_mask(canvas, mask, width, length):
	canvas_draw = ImageDraw.Draw(canvas)
	mask_pixels = mask.load()
	canvas_pixels = canvas.load()
	for i in range(width):
		for j in range(length):
			if mask_pixels[i, j] == 0 and mask_pixels[i, j] == canvas_pixels[i, j]:
				canvas_draw.point((i, j), 255)
	return canvas

def fflt(value):
	return "{0:.3f}".format(round(value, 3))
	
def save_contour(c, name, width, length, height, scale, zscale, step):
	border_delta = 2
	try:
		f = open(name, "w")
		f.write("G21\n")
		f.write("M3\n")
		f.write("G00 Z5\n")
		for ci in c:
			for i in ci[0]:
				draw_to = False
				max_z = height - zscale * ci[1]
				z = 0
				state = True
				while state:
					z += step
					if (z < max_z):
						z = max_z
						state = False
					last = [0, 0]
					for j in i:
						coord = j[0]
						x = coord[0] 
						y = length - coord[1] 
						current = [x, y]
						if (y <= border_delta or y >= length - border_delta) and (x <= border_delta or x >= width - border_delta):
							if draw_to:
								f.write("G00" + " X" + fflt(last[0] / scale) + " Y" + fflt(last[1] / scale) + " Z5" + "\n")
								draw_to = False
							last = current
							continue
#						f.write("(X" + str(x) + " Y" + str(y) + ")\n")
						if draw_to:
							f.write("G01" + " X" + fflt(x / scale) + " Y" + fflt(y / scale) + " Z" + fflt(z) + "\n")
						else:
							draw_to = True
							f.write("G00" + " X" + fflt(x / scale) + " Y" + fflt(y / scale) + " Z5" + "\n")
							f.write("G00" + " Z" + fflt(z) + "\n")
						last = current
					p = i[0][0]
					if draw_to:
						f.write("G01" + " X" + fflt(p[0] / scale) + " Y" + fflt((length - p[1]) / scale) + " Z" + fflt(z) + "\n")
						f.write("G00 Z5\n")
		f.write("M5\n")
	finally:
		f.close()

def progress_bar(progress):
	progress_show = progress / 2
	sys.stdout.write('\r[ {0}{1} ] {2}%'.format('#' * progress_show, ' ' * (50 - progress_show), progress))
	sys.stdout.flush()

def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("--image", "-f", required=True, type=str)
	
	parser.add_argument("--mill", "-m", required=True, action="append", type=float)
	
	parser.add_argument("--width", "-w", required=True, type=float)
	parser.add_argument("--length", "-l", required=True, type=float)
	parser.add_argument("--height", "-z", required=True, type=float)
	parser.add_argument("--step", "-s", type=float)
	args = parser.parse_args()
	
	matrix = []
	pixels = []
	levels = []
	
	img_width = args.width
	img_length = args.length
	img_height = args.height
	step = -1.0
	if args.step:
		step = args.step
	mills = args.mill
	filepath = args.image
	mills.sort(reverse=True)

	try:
		image = Image.open(filepath)
		
		width = image.size[0]
		length = image.size[1]
		
		scale = width / img_width
		zscale = img_height / 256
		matrix = normalize(image)
		levels = get_levels(matrix, width, length)

		canvas = Image.new('L', image.size, 255)
		mill_contours = {}
		full = len(mills) * len(levels)
		progress_counter = 0
		for mill in mills:
			mill_contours[mill] = []
		for level in levels:
			draw_level(canvas, matrix, level)
			cache = canvas.copy()
			for mill in mills:
				progress = int(math.floor(progress_counter * 100 / full))
				progress_bar(progress)
				
				(path, mask, count, contours) = draw_path(cache, mill / 2 * scale)
				if count > 0:
#					path.save("path" + "-M" + str(mill) + "-L" + str(level) + ".png")
					cache = merge_mask(cache, mask, width, length)
					mill_contours[mill].append([contours, level])
				progress_counter += 1
		progress_bar(100)
		for mill in mills:
			save_contour(mill_contours [mill], "path" + "-M" + str(mill) + ".ngc", width, length, img_height, scale, zscale, step)

	finally:
		sys.stdout.write("\n")
		print("Done.")

if __name__ == "__main__":
	main()


