// Sentinel-2 NDVI for Iloilo: latest-year greenness and change since 2016.
//
// How to run (free for students and research):
//  1. Sign up at https://earthengine.google.com and open https://code.earthengine.google.com
//  2. Paste this whole file into the editor and click Run.
//  3. Open the Tasks tab and click RUN on both exports. They save to your Google Drive.
//  4. Download the two files and put them in data/processed/ as
//       s2_ndvi_iloilo.tif   and   s2_ndvi_change.tif
//
// Clouds are removed with Google's Cloud Score+ mask. Each year is a median
// of all clear pixels, so one cloudy day does not matter.

var BBOX = ee.Geometry.Rectangle([121.95, 10.40, 123.40, 11.75]);  // same as app/config.py
var EARLY_YEAR = 2016;
var LATE_YEAR = 2025;
var SCALE = 20;  // metres; 10 is possible but the files get 4x bigger

var csPlus = ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED');

function yearlyNdvi(year) {
  var s2 = ee.ImageCollection('COPERNICUS/S2_HARMONIZED')
    .filterBounds(BBOX)
    .filterDate(year + '-01-01', (year + 1) + '-01-01')
    .linkCollection(csPlus, ['cs_cdf'])
    .map(function (img) {
      var clear = img.select('cs_cdf').gte(0.6);
      return img.normalizedDifference(['B8', 'B4']).rename('ndvi').updateMask(clear);
    });
  return s2.median().clip(BBOX);
}

var early = yearlyNdvi(EARLY_YEAR);
var late = yearlyNdvi(LATE_YEAR);
var change = late.subtract(early).rename('ndvi_change');

Map.centerObject(BBOX, 9);
var pal = ['8c510a', 'f6e8c3', 'c7eae5', '01665e'];
Map.addLayer(late, {min: -0.2, max: 0.9, palette: pal}, 'NDVI ' + LATE_YEAR);
Map.addLayer(change, {min: -0.4, max: 0.4, palette: ['b2182b', 'f7f7f7', '2166ac']}, 'NDVI change');

Export.image.toDrive({
  image: late.toFloat(), description: 's2_ndvi_iloilo', fileNamePrefix: 's2_ndvi_iloilo',
  region: BBOX, scale: SCALE, crs: 'EPSG:4326', maxPixels: 1e10
});
Export.image.toDrive({
  image: change.toFloat(), description: 's2_ndvi_change', fileNamePrefix: 's2_ndvi_change',
  region: BBOX, scale: SCALE, crs: 'EPSG:4326', maxPixels: 1e10
});
