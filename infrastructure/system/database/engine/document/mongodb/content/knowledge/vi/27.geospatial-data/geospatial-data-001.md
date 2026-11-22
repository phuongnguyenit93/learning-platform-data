# GeoJSON, thứ tự kinh độ vĩ độ và mô hình tọa độ trong MongoDB

Ứng dụng bản đồ, giao hàng, du lịch, logistics và tìm kiếm địa điểm thường cần lưu một vị trí, tuyến đường hoặc vùng địa lý trong cơ sở dữ liệu. MongoDB hỗ trợ dữ liệu này thông qua **GeoJSON**, các **2dsphere indexes** và những toán tử như **$near**, **$geoWithin**, **$geoIntersects** và **$geoNear**.

Một lỗi rất phổ biến là **đảo kinh độ và vĩ độ**. Nhiều API định vị trả về latitude trước longitude, nhưng **GeoJSON position luôn là [longitude, latitude]**, tức **[kinh độ, vĩ độ]**. Nếu đảo trục, điểm có thể xuất hiện ở nơi hoàn toàn khác hoặc bị từ chối vì tọa độ không hợp lệ. Một lỗi khác là lấy giá trị x/y từ hệ chiếu theo mét và lưu như thể đó là WGS84 theo độ.

Bài học làm rõ:

1. Cấu trúc GeoJSON của Point, LineString, Polygon, MultiPoint, MultiLineString và MultiPolygon.
2. Quy tắc **[longitude, latitude]**, giá trị hợp lệ, WGS84, sự khác biệt giữa GeoJSON và các định dạng/hệ tọa độ khác.
3. Ngữ nghĩa đường và vùng trên bề mặt Trái Đất, polygon rings, holes, antimeridian và độ cao.
4. Cách lưu GeoJSON trong MongoDB, tạo 2dsphere index và thực thi truy vấn địa lý.
5. Cách viết Java Sync Driver, nhập CSV/API/GIS, validate và migration dữ liệu cũ.
6. Những lỗi thường gặp, bài thực hành và checklist dùng trong dự án.

## 1. Tọa độ không chỉ là hai con số

Cặp [106.70098, 10.77689] chỉ có ý nghĩa khi biết hai giá trị thuộc hệ tọa độ nào và thứ tự ra sao.

| Mô hình | Ví dụ | Đơn vị/ngữ nghĩa |
| --- | --- | --- |
| GeoJSON WGS84 | [106.70098, 10.77689] | Kinh độ/vĩ độ, đơn vị độ |
| API địa điểm | {lat:10.77689,lng:106.70098} | Vĩ độ và kinh độ có tên field |
| Web Mercator | [11880000,1200000] | x/y theo mét trong hệ chiếu |
| Canvas | [300,180] | Pixel hoặc tọa độ giao diện |
| Local grid | [12,7] | Ô hoặc tọa độ nội bộ |
| Địa chỉ | "TP. Hồ Chí Minh" | Văn bản cần geocode |

Không thể lấy một cặp số từ canvas, EPSG:3857 hoặc lưới kho hàng rồi mặc nhiên dùng làm GeoJSON WGS84. MongoDB không tự suy luận hệ quy chiếu từ tên biến.

### 1.1. Những metadata cần biết từ nguồn

- **CRS/datum:** vị trí được quy chiếu bằng hệ nào?
- **Axis order:** longitude trước hay latitude trước?
- **Units:** độ, radian, mét, feet hay đơn vị riêng?
- **Accuracy:** dữ liệu GPS, người dùng đặt ghim hay hệ thống geocoding?
- **Timestamp:** điểm được ghi nhận lúc nào?
- **Geometry semantics:** vị trí, một đường, hay vùng kín?

### 1.2. Điểm bắt đầu cho mọi pipeline

Một pipeline nhập dữ liệu địa lý nên thực hiện:

~~~text
Source
  |
  v
Xác định CRS + thứ tự trục + đơn vị
  |
  v
Chuyển sang WGS84 longitude/latitude
  |
  v
Tạo GeoJSON geometry
  |
  v
Validate + lưu + geospatial index
  |
  v
Truy vấn / render / phân tích
~~~

Không bỏ qua bước đầu rồi cố sửa bằng cách đảo hai số khi phát hiện lỗi.

## 2. GeoJSON là gì?

GeoJSON là định dạng JSON chuẩn để mô tả hình học và đối tượng có thông tin địa lý. Hai nhóm cấu trúc quan trọng là **geometry objects** và **Feature objects**.

Một geometry Point:

~~~json
{
  "type": "Point",
  "coordinates": [106.70098, 10.77689]
}
~~~

Một Feature:

~~~json
{
  "type": "Feature",
  "geometry": {
    "type": "Point",
    "coordinates": [106.70098, 10.77689]
  },
  "properties": {
    "name": "Địa điểm minh họa",
    "category": "cafe"
  }
}
~~~

### 2.1. Geometry và Feature khác nhau

- **Geometry**: hình học thực tế, gồm type và coordinates hoặc geometries.
- **Feature**: đối tượng có geometry và properties.
- **FeatureCollection**: danh sách Feature.

Trong MongoDB, ứng dụng thường lưu geometry vào một field như **location**, còn thuộc tính nghiệp vụ lưu bên ngoài để dễ index/truy vấn:

~~~javascript
{
  _id: "P-001",
  name: "Quán mẫu",
  category: "cafe",
  active: true,
  location: {
    type: "Point",
    coordinates: [106.70098, 10.77689]
  }
}
~~~

Cấu trúc này khác với việc nhét toàn bộ FeatureCollection vào một document. Nếu một Feature chứa một địa điểm độc lập, thường nên tạo một MongoDB document riêng cho Feature đó.

### 2.2. Những GeoJSON geometry thường gặp

| Type | Ý nghĩa |
| --- | --- |
| Point | Một vị trí |
| MultiPoint | Tập các điểm |
| LineString | Đường nối các vị trí theo thứ tự |
| MultiLineString | Nhiều đường |
| Polygon | Vùng kín có thể có lỗ |
| MultiPolygon | Nhiều vùng polygon |
| GeometryCollection | Tập geometry khác loại |

Không phải mọi operator geospatial MongoDB đều nhận mọi geometry type với cùng semantics. Ví dụ các phép tìm điểm gần thường nhận **Point** làm tâm truy vấn.

## 3. Thứ tự tọa độ GeoJSON: [longitude, latitude]

Một position hai chiều theo GeoJSON có thứ tự:

~~~text
[longitude, latitude]
[kinh độ, vĩ độ]
~~~

Ví dụ:

~~~javascript
const longitude = 106.70098;
const latitude = 10.77689;

const point = {
  type: "Point",
  coordinates: [longitude, latitude]
};
~~~

### 3.1. Kinh độ (longitude)

Kinh độ biểu diễn hướng Đông–Tây so với kinh tuyến gốc.

- Khoảng giá trị thông thường: **-180° đến +180°**.
- Giá trị **dương**: phía Đông.
- Giá trị **âm**: phía Tây.
- 0°: kinh tuyến gốc.

~~~text
106.70  -> khoảng 106.70° Đông
-122.40 -> khoảng 122.40° Tây
0       -> kinh tuyến gốc
~~~

### 3.2. Vĩ độ (latitude)

Vĩ độ biểu diễn hướng Bắc–Nam so với xích đạo.

- Khoảng giá trị: **-90° đến +90°**.
- Giá trị **dương**: phía Bắc.
- Giá trị **âm**: phía Nam.
- 0°: xích đạo.

~~~text
10.77  -> khoảng 10.77° Bắc
-33.86 -> khoảng 33.86° Nam
0      -> xích đạo
~~~

### 3.3. Bảng quy tắc

| Thành phần | Tên khác | Vị trí trong GeoJSON | Khoảng hợp lệ |
| --- | --- | --- | --- |
| longitude | lon, lng | coordinates[0] | [-180, 180] |
| latitude | lat | coordinates[1] | [-90, 90] |

Hãy đặt tên biến **longitude** và **latitude** hoặc **lon** và **lat**, không chỉ đặt **x** và **y** nếu điều đó làm nhóm phát triển dễ nhầm.

## 4. Vì sao API và giao diện thường đảo thứ tự?

Nhiều ứng dụng và dịch vụ trả:

~~~json
{
  "lat": 10.77689,
  "lng": 106.70098
}
~~~

Nhưng GeoJSON phải là:

~~~javascript
{
  type: "Point",
  coordinates: [106.70098, 10.77689]
}
~~~

Code chuyển đúng:

~~~javascript
const source = {
  lat: 10.77689,
  lng: 106.70098
};

const location = {
  type: "Point",
  coordinates: [
    source.lng,
    source.lat
  ]
};
~~~

### 4.1. Lỗi đảo trục có thể hiện rõ

Sai:

~~~javascript
{
  type: "Point",
  coordinates: [10.77689, 106.70098]
}
~~~

Phần tử thứ hai được hiểu là **latitude = 106.70098°**, vượt giới hạn +90°, nên có thể bị MongoDB từ chối khi index hoặc query geospatial.

### 4.2. Lỗi đảo trục cũng có thể âm thầm

Xét điểm có kinh độ 2.35°, vĩ độ 48.86°:

~~~javascript
[2.35, 48.86]  // lon = 2.35; lat = 48.86
[48.86, 2.35]  // lon = 48.86; lat = 2.35
~~~

Cả hai đều nằm trong khoảng số hợp lệ nhưng là **hai vị trí khác nhau**. Do đó, kiểm tra range không đủ để chứng minh thứ tự trục đúng.

### 4.3. Không tự đảo khi dữ liệu “trông sai”

Nếu nguồn gửi lat = 106.7 và lng = 10.77, có thể đó là lỗi đảo field, nhưng cũng có thể là nguồn sai CRS hoặc lỗi mapping. Trước khi sửa cần xác định contract nguồn và kiểm tra sample, không tự swap mọi record.

## 5. WGS84 và hệ tọa độ

**WGS84** là hệ quy chiếu địa lý được dùng rộng rãi trong GPS và dữ liệu vị trí. GeoJSON hiện đại theo RFC 7946 sử dụng tọa độ địa lý dựa trên WGS84, với position có trục **longitude trước, latitude sau**.

### 5.1. CRS là gì?

**Coordinate Reference System (CRS)** xác định cách những con số tọa độ được ánh xạ tới vị trí. Nó liên quan tới datum, trục, đơn vị và có thể cả phép chiếu.

Hai vị trí có cùng con số x/y nhưng dùng CRS khác nhau có thể chỉ hai nơi khác nhau hoàn toàn.

### 5.2. EPSG:4326 và thứ tự trục

EPSG:4326 được dùng phổ biến để chỉ WGS84 geographic CRS. Nhưng trong một số định nghĩa/ứng dụng GIS, axis order chính thức có thể được trình bày là latitude, longitude.

**GeoJSON RFC 7946 vẫn quy định position theo longitude, latitude**, gần với trật tự trục của CRS84. Vì thế không chỉ đọc nhãn EPSG:4326 rồi mặc định tất cả thư viện sẽ trả [lon,lat].

Một pipeline nhập từ GIS phải xác nhận:

~~~text
Nguồn ghi WGS84 / EPSG:4326
  -> thư viện xuất lat/lon hay lon/lat?
  -> normalize thành GeoJSON [lon,lat]
~~~

### 5.3. EPSG:3857 Web Mercator

Một nguồn bản đồ có thể trả tọa độ phẳng x/y theo mét:

~~~javascript
{
  x: 11880000,
  y: 1200000,
  crs: "EPSG:3857"
}
~~~

Không được coi:

~~~javascript
[11880000, 1200000]
~~~

là longitude và latitude theo độ. Phải dùng phép chuyển CRS đúng qua thư viện GIS hoặc dịch vụ chuyển đổi tin cậy.

### 5.4. Đảo trục không phải chuyển CRS

Chuyển:

~~~text
[x, y] -> [y, x]
~~~

chỉ là đổi thứ tự. Nó không biến giá trị mét trong Web Mercator thành độ WGS84.

## 6. Đơn vị độ không phải mét

GeoJSON coordinates như:

~~~javascript
[106.70098, 10.77689]
~~~

là **kinh độ/vĩ độ theo độ**. Nhưng tham số bán kính của một số toán tử MongoDB lại dùng **mét**.

Không tự tính khoảng cách bằng:

~~~text
sqrt((lon2-lon1)^2 + (lat2-lat1)^2)
~~~

rồi coi kết quả là số mét. Phép tính trên cho ra độ và bỏ qua độ cong của Trái Đất.

### 6.1. Một độ kinh độ không tương ứng cùng số mét ở mọi nơi

Các đường kinh tuyến hội tụ ở hai cực. Vì vậy chênh lệch 0.01° longitude ở gần xích đạo và gần cực tương ứng những quãng đường khác nhau.

### 6.2. Khoảng cách địa lý khác khoảng cách đường bộ

Khi dùng 2dsphere, $near hoặc $geoNear trả kết quả dựa trên mô hình khoảng cách địa lý; không tự tính đường đi xe, cầu, đường một chiều hay thời gian tắc đường.

Nếu cần ETA, phải sử dụng routing engine và mạng đường phù hợp.

## 7. GeoJSON Point

Một Point gồm đúng một position:

~~~json
{
  "type": "Point",
  "coordinates": [106.70098, 10.77689]
}
~~~

Ứng dụng:

- Vị trí cửa hàng.
- Điểm đón khách.
- Một trạm GPS.
- Điểm giao hàng.
- Cảm biến hoặc trạm quan trắc.

Document MongoDB:

~~~javascript
db.places.insertOne({
  _id: "P-001",
  name: "Địa điểm mẫu",
  location: {
    type: "Point",
    coordinates: [106.70098, 10.77689]
  }
});
~~~

### 7.1. GeoJSON Point khác legacy coordinate pair

Legacy pair:

~~~javascript
{
  location: [106.70098, 10.77689]
}
~~~

GeoJSON geometry:

~~~javascript
{
  location: {
    type: "Point",
    coordinates: [106.70098, 10.77689]
  }
}
~~~

MongoDB hỗ trợ một số thao tác geospatial với legacy coordinate pairs, nhưng không nên đánh đồng hai schema hoặc tự gán mọi quy tắc về geometry type cho một array số trần.

## 8. GeoJSON LineString

LineString biểu diễn chuỗi các điểm nối tiếp:

~~~json
{
  "type": "LineString",
  "coordinates": [
    [106.7000, 10.7700],
    [106.7050, 10.7750],
    [106.7100, 10.7800]
  ]
}
~~~

Mỗi vị trí trong danh sách **vẫn là [lon,lat]**.

### 8.1. Ít nhất hai positions

LineString cần ít nhất hai position để biểu diễn một đoạn nối:

~~~javascript
{
  type: "LineString",
  coordinates: [
    [106.70, 10.77],
    [106.71, 10.78]
  ]
}
~~~

### 8.2. Không đồng nghĩa tuyến đường đi thực tế

Đưa hai GPS points vào LineString không làm MongoDB tìm tuyến đường bộ giữa chúng. Nó chỉ mô tả hình học từ các positions có sẵn.

Nếu cần phân tích xe đã đi, phải xét tần suất GPS, nhiễu đo và thông tin mạng đường.

## 9. GeoJSON Polygon

Polygon là một vùng được mô tả bằng **một hoặc nhiều closed linear rings**.

~~~json
{
  "type": "Polygon",
  "coordinates": [
    [
      [106.69, 10.76],
      [106.71, 10.76],
      [106.71, 10.78],
      [106.69, 10.78],
      [106.69, 10.76]
    ]
  ]
}
~~~

Cấu trúc:

~~~text
Polygon
  coordinates
    -> danh sách rings
      -> một ring
        -> danh sách positions
          -> [longitude, latitude]
~~~

### 9.1. Vì sao có thêm một tầng array?

Một Polygon có thể chứa outer ring và nhiều inner rings. Vì vậy **coordinates** chứa mảng các rings, dù polygon không có lỗ.

### 9.2. Ring phải đóng

Position đầu và cuối của ring phải bằng nhau:

~~~javascript
[
  [106.69, 10.76],
  [106.71, 10.76],
  [106.71, 10.78],
  [106.69, 10.78],
  [106.69, 10.76]
]
~~~

Nếu bỏ position cuối, ring không khép kín rõ ràng theo chuẩn.

### 9.3. Tối thiểu bốn positions

Ba đỉnh phân biệt và điểm đầu lặp ở cuối tạo ring tam giác tối thiểu:

~~~javascript
[
  [106.70, 10.77],
  [106.72, 10.77],
  [106.71, 10.79],
  [106.70, 10.77]
]
~~~

Đừng tạo các đỉnh trùng nhau để đạt số lượng mà không hình thành vùng hợp lệ.

## 10. Polygon có lỗ

Polygon có thể chứa outer ring và inner ring:

~~~javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.68, 10.75],
      [106.73, 10.75],
      [106.73, 10.80],
      [106.68, 10.80],
      [106.68, 10.75]
    ],
    [
      [106.695, 10.765],
      [106.695, 10.780],
      [106.710, 10.780],
      [106.710, 10.765],
      [106.695, 10.765]
    ]
  ]
}
~~~

Inner ring thường biểu diễn vùng bị loại trừ khỏi outer polygon.

### 10.1. Ring winding order

GeoJSON RFC 7946 quy định quy tắc hướng vòng, thường gọi là **right-hand rule**: outer ring ngược chiều kim đồng hồ, inner ring cùng chiều kim đồng hồ, với cách nhìn trên mặt phẳng bản đồ tương ứng.

Khi MongoDB diễn giải polygon trên cầu, đặc biệt với vùng rất lớn, các quy tắc winding và biểu diễn vùng bổ sung có thể quan trọng.

### 10.2. Hole phải phù hợp outer ring

Không đặt lỗ hoàn toàn bên ngoài outer ring hoặc để các ring tự giao vô lý. Dữ liệu polygon không hợp lệ có thể bị index/query từ chối hoặc gây kết quả không mong muốn.

### 10.3. Self-intersection

Nếu một vòng tạo hình “nơ bướm” với các cạnh cắt nhau, đó không phải polygon đơn giản đáng tin cậy. Cần chuẩn hóa topology bằng công cụ GIS thích hợp, không chỉ kiểm tra các array có đủ số phần tử.

## 11. MultiPoint

MultiPoint là một tập các điểm:

~~~json
{
  "type": "MultiPoint",
  "coordinates": [
    [106.700, 10.770],
    [106.710, 10.780],
    [106.720, 10.790]
  ]
}
~~~

Nó không nối các điểm thành đường như LineString.

Nếu mỗi điểm là một chi nhánh có ID, thời gian mở cửa và trạng thái riêng, **mỗi chi nhánh một MongoDB document Point** thường dễ quản lý hơn một MultiPoint rất lớn.

## 12. MultiLineString

MultiLineString chứa nhiều đoạn đường độc lập:

~~~json
{
  "type": "MultiLineString",
  "coordinates": [
    [
      [106.700, 10.770],
      [106.705, 10.775]
    ],
    [
      [106.710, 10.780],
      [106.715, 10.785],
      [106.720, 10.790]
    ]
  ]
}
~~~

Có thể biểu diễn những đoạn tuyến rời nhau mà không thêm đường nối tưởng tượng giữa chúng.

## 13. MultiPolygon

MultiPolygon chứa nhiều Polygon:

~~~json
{
  "type": "MultiPolygon",
  "coordinates": [
    [
      [
        [106.68, 10.75],
        [106.70, 10.75],
        [106.70, 10.77],
        [106.68, 10.77],
        [106.68, 10.75]
      ]
    ],
    [
      [
        [106.72, 10.78],
        [106.74, 10.78],
        [106.74, 10.80],
        [106.72, 10.80],
        [106.72, 10.78]
      ]
    ]
  ]
}
~~~

Cấu trúc:

~~~text
MultiPolygon
  -> danh sách polygons
     -> danh sách rings của mỗi polygon
        -> danh sách positions
           -> [longitude, latitude]
~~~

Một vùng giao hàng có hai khu vực không tiếp giáp có thể dùng MultiPolygon. Không nên nối hai khu vực rời bằng những đoạn giả để ép thành một Polygon.

## 14. GeometryCollection và FeatureCollection

GeometryCollection chứa nhiều geometry, có thể khác loại:

~~~json
{
  "type": "GeometryCollection",
  "geometries": [
    {
      "type": "Point",
      "coordinates": [106.70, 10.77]
    },
    {
      "type": "LineString",
      "coordinates": [
        [106.70, 10.77],
        [106.72, 10.79]
      ]
    }
  ]
}
~~~

Field bên trong GeometryCollection là **geometries**, không phải coordinates ở root.

FeatureCollection chứa nhiều Feature:

~~~json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [106.70, 10.77]
      },
      "properties": {
        "name": "Place A"
      }
    }
  ]
}
~~~

Trong MongoDB, nếu cần tìm kiếm từng Feature theo vị trí, thường nên nhập mỗi Feature thành một document riêng với geometry field nhất quán.

## 15. Độ cao: thành phần thứ ba

GeoJSON có thể biểu diễn position với thành phần thứ ba, thường được hiểu là elevation/altitude theo ngữ cảnh:

~~~json
{
  "type": "Point",
  "coordinates": [106.70098, 10.77689, 15]
}
~~~

Tuy nhiên, MongoDB geospatial indexes và operators thông thường tập trung vào hình học trên bề mặt Trái Đất, **không phải khoảng cách 3D có xét altitude**.

### 15.1. Mô hình rõ nghĩa hơn

~~~javascript
{
  location: {
    type: "Point",
    coordinates: [106.70098, 10.77689]
  },
  elevationMeters: 15,
  elevationReference: "SOURCE_SPECIFIC"
}
~~~

Điều này tránh nhầm một query 2dsphere đã tính chênh lệch độ cao.

### 15.2. Vertical datum

Cao độ so với ellipsoid, cao độ so với mực nước biển và số tầng trong tòa nhà khác nhau. Một số 15 không đủ để suy ra độ cao thực nếu không có vertical datum/đơn vị.

## 16. Kiểm tra phạm vi và kiểu dữ liệu

Với position hai chiều WGS84:

\[
-180 \leq \text{longitude} \leq 180
\]

\[
-90 \leq \text{latitude} \leq 90
\]

Các ví dụ không hợp lệ:

~~~javascript
[106.70, 110]              // latitude quá 90
[250, 10.77]               // longitude quá 180
["106.70", "10.77"]         // string, không phải number
[106.70]                   // thiếu latitude
[106.70, null]             // missing/null
[Infinity, 10.77]          // không hữu hạn
~~~

### 16.1. Hàm validate JavaScript

~~~javascript
function makeGeoPoint(longitude, latitude) {
  if (
    !Number.isFinite(longitude) ||
    !Number.isFinite(latitude)
  ) {
    throw new Error("Tọa độ phải là số hữu hạn");
  }

  if (longitude < -180 || longitude > 180) {
    throw new Error("Kinh độ ngoài [-180,180]");
  }

  if (latitude < -90 || latitude > 90) {
    throw new Error("Vĩ độ ngoài [-90,90]");
  }

  return {
    type: "Point",
    coordinates: [longitude, latitude]
  };
}
~~~

### 16.2. Validation không tự phát hiện mọi trục đảo

Cả [2.35,48.86] và [48.86,2.35] đều hợp lệ về range. Cần kiểm tra **contract nguồn, vị trí dự kiến và mẫu dữ liệu tham chiếu**.

### 16.3. Không nên dùng parseFloat mù quáng

JavaScript parseFloat có thể đọc được tiền tố số từ một string chứa ký tự khác. Với dữ liệu vị trí, cần parse strict và reject những record không hợp lệ.

## 17. Kinh tuyến 180° (antimeridian)

Hai điểm có kinh độ:

~~~text
179.8°
-179.8°
~~~

có thể ở rất gần nhau trên Trái Đất, dù hiệu số học là 359.6°.

### 17.1. Sai lầm với trục x phẳng

Nếu code vẽ một đoạn từ 179.8 sang -179.8 như x/y bình thường, đoạn có thể chạy ngang toàn bản đồ thay vì vượt qua kinh tuyến ±180°.

### 17.2. GeoJSON qua antimeridian

RFC 7946 khuyến nghị xử lý/split những hình học đi qua antimeridian để tránh diễn giải không mong muốn. Với một polygon cắt đường này, có thể cần biểu diễn thành **MultiPolygon** với các phần ở hai phía.

Không tự sửa bằng cách wrap longitude rồi cho rằng polygon/topology chắc chắn đúng.

### 17.3. Vùng gần cực

Ở gần ±90° latitude, các đường kinh tuyến hội tụ mạnh. Khoảng cách Euclid của các độ và bounding box naïve càng không đáng tin.

Dùng toán tử địa lý phù hợp và thử các trường hợp biên.

## 18. Polygon rất lớn và strict-winding

Trên hình cầu, một vòng kín có thể chia bề mặt thành hai miền. Với polygon rất lớn, cách diễn giải “phía trong” có thể phụ thuộc hướng ring và quy tắc MongoDB.

MongoDB có một cơ chế CRS đặc biệt cho một số polygon lớn, thường được gọi là **strict-winding CRS**:

~~~javascript
{
  type: "Polygon",
  coordinates: [
    [
      [-170, -10],
      [-170, 10],
      [170, 10],
      [170, -10],
      [-170, -10]
    ]
  ],
  crs: {
    type: "name",
    properties: {
      name: "urn:x-mongodb:crs:strictwinding:EPSG:4326"
    }
  }
}
~~~

**Đây là quy ước riêng của MongoDB, không phải giấy phép gắn mọi CRS tùy ý vào GeoJSON chuẩn RFC 7946.** Trước khi dùng phải kiểm tra đúng operator, version và yêu cầu winding.

Với Polygon nhỏ của cửa hàng hoặc một quận, thường chỉ cần GeoJSON WGS84 hợp lệ, không dùng strict-winding không có lý do.

## 19. 2dsphere index trong MongoDB

Để truy vấn địa lý theo hình cầu, thường dùng **2dsphere index**:

~~~javascript
db.places.createIndex({
  location: "2dsphere"
});
~~~

Ví dụ dữ liệu:

~~~javascript
use geo_lab

db.places.insertMany([
  {
    _id: "P-001",
    name: "Cửa hàng A",
    category: "shop",
    location: {
      type: "Point",
      coordinates: [106.70098, 10.77689]
    }
  },
  {
    _id: "P-002",
    name: "Cửa hàng B",
    category: "shop",
    location: {
      type: "Point",
      coordinates: [106.70900, 10.78400]
    }
  },
  {
    _id: "P-003",
    name: "Kho C",
    category: "warehouse",
    location: {
      type: "Point",
      coordinates: [106.72500, 10.79500]
    }
  }
]);

db.places.createIndex({
  location: "2dsphere"
});
~~~

### 19.1. 2dsphere và 2d khác nhau

| Index | Mô hình chính | Dữ liệu thường dùng |
| --- | --- | --- |
| **2dsphere** | Hình cầu/WGS84 | GeoJSON và các dạng được hỗ trợ |
| **2d** | Mô hình mặt phẳng/legacy | Legacy coordinate pairs |

Không dùng 2d chỉ vì hình học có hai số. Muốn truy vấn vị trí trên Trái Đất bằng GeoJSON, 2dsphere thường phù hợp hơn.

### 19.2. 2dsphere không tự sửa dữ liệu xấu

Nếu một document chứa latitude = 105°, tạo geospatial index có thể báo lỗi. Hãy validate trước khi index collection lớn.

### 19.3. Field index phải chính xác

Nếu geometry nằm trong **location**, tạo index trên **area** không giúp query location. Tương tự, một Feature object chứa geometry dưới field geometry cần đường dẫn index/query đúng.

### 19.4. Không có location

MongoDB 2dsphere index có những quy tắc sparse riêng. Một document không có vị trí có thể không có index entry tương ứng. Nếu schema nghiệp vụ bắt buộc có tọa độ, hãy dùng validation; không nên chỉ dựa vào index để cưỡng chế dữ liệu.

## 20. $near: điểm gần nhất

Ví dụ truy vấn những địa điểm gần một Point, tối đa 5.000 mét:

~~~javascript
db.places.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $maxDistance: 5000
    }
  }
});
~~~

Với GeoJSON Point và 2dsphere index, **$maxDistance** theo ngữ cảnh này dùng **mét**.

### 20.1. Đừng nhầm độ và mét

~~~text
Point coordinates = [106.70098°, 10.77689°]
$maxDistance      = 5000 mét
~~~

Nếu người dùng nhập bán kính 5 km, ứng dụng cần chuyển thành 5.000 mét. Không truyền 5 với ý nghĩ đó là 5 km.

### 20.2. Dùng $minDistance

~~~javascript
db.places.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $minDistance: 500,
      $maxDistance: 5000
    }
  }
});
~~~

Ví dụ tìm các địa điểm cách tâm ít nhất 500 m và nhiều nhất 5.000 m theo semantics của operator.

### 20.3. $near có thứ tự khoảng cách

$near thực hiện truy vấn có thứ tự gần đến xa. Nếu chỉ cần tập điểm nằm trong một vùng và không cần thứ tự distance, có thể dùng $geoWithin phù hợp.

## 21. $geoNear: lấy cả khoảng cách

Aggregation $geoNear phù hợp khi muốn kết quả có distance field:

~~~javascript
db.places.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      distanceField: "distanceMeters",
      maxDistance: 5000,
      spherical: true,
      key: "location"
    }
  },
  {
    $project: {
      name: 1,
      category: 1,
      location: 1,
      distanceMeters: 1
    }
  }
]);
~~~

### 21.1. $geoNear phải ở đầu pipeline

Trong aggregation, $geoNear có yêu cầu đứng ở đầu pipeline theo MongoDB semantics hỗ trợ. Đừng tùy ý đặt $match trước rồi kỳ vọng nó hoạt động như find thông thường.

Có thể dùng các tùy chọn lọc của $geoNear và stage sau để thực hiện điều kiện nghiệp vụ theo đúng khả năng hỗ trợ.

### 21.2. Key khi có nhiều geo index

Tùy chọn **key: "location"** giúp chỉ định geospatial field trong những tình huống có nhiều index phù hợp.

### 21.3. Distance chưa phải lộ trình

distanceMeters biểu diễn khoảng cách địa lý theo mô hình được dùng, không tự tìm đường bộ hoặc ETA.

## 22. $geoWithin: nằm trong Polygon

Ví dụ Polygon vùng giao hàng:

~~~javascript
const deliveryArea = {
  type: "Polygon",
  coordinates: [
    [
      [106.68, 10.76],
      [106.72, 10.76],
      [106.72, 10.80],
      [106.68, 10.80],
      [106.68, 10.76]
    ]
  ]
};

db.places.find({
  location: {
    $geoWithin: {
      $geometry: deliveryArea
    }
  }
});
~~~

### 22.1. $geoWithin không sort theo khoảng cách

Toán tử kiểm tra quan hệ nằm trong vùng, không hứa trả điểm gần tâm nhất trước.

### 22.2. Vùng có hole

Nếu Polygon có lỗ, điểm nằm trong lỗ có thể bị loại khỏi vùng theo semantics của geometry. Cần đảm bảo outer ring và inner ring hợp lệ.

### 22.3. Điểm ở biên

Đối với điểm đúng đường biên, hãy kiểm chứng semantics trên MongoDB version và dataset thực tế. Nếu nghiệp vụ cần xác định “đúng biên tính là trong hay ngoài”, phải có quy tắc rõ ràng và bài test số học.

## 23. $geoIntersects: hình học giao nhau

Nếu collection lưu các Polygon vùng phục vụ:

~~~javascript
db.serviceAreas.createIndex({
  area: "2dsphere"
});
~~~

Tìm những vùng giao với một Polygon:

~~~javascript
db.serviceAreas.find({
  area: {
    $geoIntersects: {
      $geometry: {
        type: "Polygon",
        coordinates: [
          [
            [106.70, 10.77],
            [106.73, 10.77],
            [106.73, 10.80],
            [106.70, 10.80],
            [106.70, 10.77]
          ]
        ]
      }
    }
  }
});
~~~

### 23.1. Giao cắt khác hoàn toàn nằm trong

Hai Polygon chỉ có một phần chồng lấp vẫn có thể thỏa điều kiện giao nhau, dù không polygon nào chứa toàn bộ polygon kia.

### 23.2. Truy vấn vùng chứa một Point

Có thể hỏi vùng phục vụ nào giao với Point khách hàng:

~~~javascript
db.serviceAreas.find({
  area: {
    $geoIntersects: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      }
    }
  }
});
~~~

Nếu có nhiều vùng chồng lấn, ứng dụng cần quy tắc chọn cửa hàng, không chỉ dựa vào danh sách vùng phù hợp.

## 24. $centerSphere dùng radian

Một kiểu truy vấn vùng hình tròn khác:

~~~javascript
db.places.find({
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.70098, 10.77689],
        0.001
      ]
    }
  }
});
~~~

Bán kính trong **$centerSphere** là **radian**, không phải mét.

| Truy vấn | Đơn vị khoảng cách/bán kính |
| --- | --- |
| $near với GeoJSON + 2dsphere | Mét |
| $geoNear với GeoJSON + spherical | Mét theo semantics tương ứng |
| $geoWithin + $centerSphere | Radian |

Nếu cần bán kính R mét, bán kính góc xấp xỉ **R / bán kính Trái Đất** khi dùng mô hình cầu thích hợp. Không truyền nguyên số mét làm tham số radian.

## 25. Thiết kế POI collection

Một nơi quan tâm (POI) thường dùng một Point:

~~~javascript
{
  _id: "STORE-001",
  tenantId: "T-A",
  name: "Cửa hàng A",
  category: "grocery",
  active: true,
  location: {
    type: "Point",
    coordinates: [106.70098, 10.77689]
  },
  updatedAt: new Date(),
  locationSource: "gps",
  accuracyMeters: 25
}
~~~

### 25.1. Metadata tốt

- **locationSource**: GPS, địa chỉ geocoding, người dùng đặt ghim.
- **accuracyMeters**: sai số ước lượng, khi có.
- **updatedAt**: vị trí được cập nhật khi nào.
- **active**: có còn phục vụ hay không.
- **tenantId**: tenant sở hữu.
- **category**: loại địa điểm.

### 25.2. Compound index

Một query thường lọc active + gần location có thể cần cân nhắc index:

~~~javascript
db.places.createIndex({
  active: 1,
  location: "2dsphere"
});
~~~

Hiệu quả phụ thuộc workload, thứ tự field, MongoDB version và query plan. Không mặc định compound geo index luôn tốt hơn mọi phương án khác.

### 25.3. Nhiều chi nhánh

Một chuỗi cửa hàng có 500 chi nhánh nên cân nhắc **500 document Point** nếu mỗi chi nhánh có lịch hoạt động, tồn kho và trạng thái độc lập, thay vì một MultiPoint khổng lồ.

## 26. Tracking GPS và LineString

Một tuyến mẫu:

~~~javascript
{
  _id: "ROUTE-001",
  path: {
    type: "LineString",
    coordinates: [
      [106.7000, 10.7700],
      [106.7050, 10.7750],
      [106.7100, 10.7800]
    ]
  }
}
~~~

Nếu cần thời gian ở mỗi GPS sample, có thể lưu các record riêng:

~~~javascript
{
  vehicleId: "V-01",
  recordedAt: ISODate("2026-11-14T03:00:00Z"),
  location: {
    type: "Point",
    coordinates: [106.7000, 10.7700]
  },
  speedKmh: 28
}
~~~

### 26.1. Không gom vô hạn vào một document

MongoDB document có giới hạn kích thước. Tập GPS samples không nên tăng vô hạn trong một array hoặc MultiPoint duy nhất nếu ứng dụng cần lưu lịch sử dài hạn.

### 26.2. Lọc theo thời gian và vị trí

Cân nhắc index cho vehicleId, recordedAt và index địa lý riêng khi cần query theo vị trí. Không chỉ có một geo index mà bỏ qua query patterns khác.

## 27. Schema validation

Có thể dùng JSON Schema kiểm soát Point gồm hai numeric values:

~~~javascript
db.createCollection("validatedPlaces", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["name", "location"],
      properties: {
        name: { bsonType: "string" },
        location: {
          bsonType: "object",
          required: ["type", "coordinates"],
          properties: {
            type: { enum: ["Point"] },
            coordinates: {
              bsonType: "array",
              minItems: 2,
              maxItems: 2,
              items: {
                bsonType: [
                  "double",
                  "int",
                  "long",
                  "decimal"
                ]
              }
            }
          }
        }
      }
    }
  }
});
~~~

Validator này kiểm soát shape cơ bản, chưa chứng minh:

- Longitude/latitude nằm trong phạm vi cụ thể.
- Axis order đúng từ nguồn.
- Địa điểm ở vùng nghiệp vụ mong đợi.
- Polygon không tự giao.
- Kinh độ/vĩ độ đã chuyển từ CRS nguồn.

Cần bổ sung validation ở ứng dụng, pipeline nhập hoặc công cụ GIS.

## 28. Nhập dữ liệu từ API và CSV

API thường trả:

~~~json
{
  "latitude": 10.77689,
  "longitude": 106.70098,
  "accuracy": 12
}
~~~

Chuyển:

~~~javascript
const location = makeGeoPoint(
  apiResponse.longitude,
  apiResponse.latitude
);
~~~

CSV có columns lat,lng:

~~~csv
id,lat,lng
P-001,10.77689,106.70098
P-002,10.78400,106.70900
~~~

Tạo GeoJSON:

~~~javascript
const location = {
  type: "Point",
  coordinates: [
    Number(row.lng),
    Number(row.lat)
  ]
};
~~~

### 28.1. Không dùng thứ tự cột CSV làm thứ tự GeoJSON

CSV có lat trước lng không làm GeoJSON thay chuẩn. Mapping phải tường minh.

### 28.2. Nhập từ GIS

Shapefile, GeoPackage, WKT hoặc dịch vụ địa lý khác có thể dùng những CRS khác nhau.

Quy trình:

~~~text
Read source geometry
  -> inspect source CRS and axis order
  -> transform to WGS84 longitude/latitude
  -> create GeoJSON geometry
  -> validate coordinate ranges and topology
  -> import MongoDB
  -> build index
  -> verify sample positions and queries
~~~

### 28.3. Một số điểm vẫn sai dù numeric hợp lệ

Kiểm tra trên bản đồ hoặc đối chiếu với polygon vùng hoạt động có thể phát hiện những điểm bị đảo lat/lon mà range validation không nhận ra.

## 29. Migration schema cũ sang GeoJSON

Dữ liệu cũ:

~~~javascript
{
  _id: "P-OLD-001",
  lat: 10.77689,
  lng: 106.70098
}
~~~

Schema mới:

~~~javascript
{
  _id: "P-OLD-001",
  location: {
    type: "Point",
    coordinates: [106.70098, 10.77689]
  }
}
~~~

Với nguồn cũ được xác nhận là WGS84 và các field numeric hợp lệ, có thể dùng update pipeline trong môi trường kiểm thử:

~~~javascript
db.places.updateMany(
  {
    lat: { $type: "number" },
    lng: { $type: "number" }
  },
  [
    {
      $set: {
        location: {
          type: "Point",
          coordinates: ["$lng", "$lat"]
        }
      }
    }
  ]
);
~~~

**Đây là minh họa**, không thay thế kiểm tra phạm vi, backup, phân loại dữ liệu và kiểm chứng kết quả. Không chạy batch này trực tiếp trên collection production mà chưa kiểm thử.

### 29.1. Các bước migration

1. Kiểm kê nguồn và schema.
2. Xác định đúng CRS/axis order từng nguồn.
3. Phân loại null, strings, out-of-range, duplicates.
4. Chuyển sang WGS84 lon/lat.
5. Tạo field GeoJSON mới.
6. Đối chiếu sample tọa độ và vùng hoạt động.
7. Tạo 2dsphere index.
8. Kiểm thử $near/$geoWithin.
9. Chuyển ứng dụng sang schema mới.
10. Xóa field cũ sau khi các consumers đã đổi.

### 29.2. Dữ liệu hỗn hợp đúng/sai

Nếu một số record đã lưu [lon,lat] còn số khác là [lat,lon], **không swap toàn bộ**. Cần nhận dạng nguồn/version và chỉ sửa nhóm có bằng chứng bị đảo.

## 30. Java Sync Driver: tạo Point

Trong Java Sync Driver có các lớp GeoJSON, ví dụ **Point** và **Position**:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.geojson.Point;
import com.mongodb.client.model.geojson.Position;
import org.bson.Document;

public class InsertPointExample {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu MONGODB_URI"
            );
        }

        double longitude = 106.70098;
        double latitude = 10.77689;

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                    client.getDatabase("geo_lab");

            MongoCollection<Document> places =
                    database.getCollection("places");

            Point point = new Point(
                    new Position(longitude, latitude)
            );

            Document place = new Document("_id", "JAVA-P-001")
                    .append("name", "Điểm Java")
                    .append("location", point);

            places.insertOne(place);
        }
    }
}
~~~

Thứ tự quan trọng:

~~~java
new Position(longitude, latitude)
~~~

Không tạo Position(latitude, longitude) theo thói quen hiển thị của API.

### 30.1. Tạo BSON Document tường minh

Nếu không cần lớp GeoJSON chuyên biệt:

~~~java
Document location = new Document("type", "Point")
        .append(
                "coordinates",
                java.util.Arrays.asList(
                        longitude,
                        latitude
                )
        );
~~~

Cần dùng codec/driver version phù hợp với cách encode BSON.

## 31. Java Sync Driver: 2dsphere index

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

// places là MongoCollection<Document>.

String indexName = places.createIndex(
        Indexes.geo2dsphere("location")
);

System.out.println(indexName);
~~~

Chỉ tạo index sau khi chuẩn hóa những record có location. Nếu collection chứa geometry sai, index build có thể thất bại.

## 32. Java Sync Driver: query $near

Có thể tạo filter BSON tường minh:

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import java.util.Arrays;

// places là MongoCollection<Document>.

double longitude = 106.70098;
double latitude = 10.77689;

Document point = new Document("type", "Point")
        .append(
                "coordinates",
                Arrays.asList(
                        longitude,
                        latitude
                )
        );

Document near = new Document("$geometry", point)
        .append("$maxDistance", 5000);

Document filter = new Document(
        "location",
        new Document("$near", near)
);

places.find(filter).forEach(
        row -> System.out.println(row.toJson())
);
~~~

Trong ví dụ, 5000 tương ứng **5.000 mét** theo semantics của GeoJSON 2dsphere near query.

### 32.1. Tại sao dùng Document?

Nó thể hiện cấu trúc MongoDB query trực tiếp, giảm phụ thuộc vào các overload của lớp Filters giữa các phiên bản driver. Ứng dụng cũng có thể dùng các helper geospatial của Java Driver khi thích hợp.

## 33. Java Sync Driver: query $geoWithin

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.Arrays;
import java.util.List;

// places là MongoCollection<Document>.

List<List<Double>> ring = Arrays.asList(
        Arrays.asList(106.68, 10.76),
        Arrays.asList(106.72, 10.76),
        Arrays.asList(106.72, 10.80),
        Arrays.asList(106.68, 10.80),
        Arrays.asList(106.68, 10.76)
);

Document polygon = new Document("type", "Polygon")
        .append(
                "coordinates",
                Arrays.asList(ring)
        );

Document filter = new Document(
        "location",
        new Document(
                "$geoWithin",
                new Document("$geometry", polygon)
        )
);

places.find(filter).forEach(
        row -> System.out.println(row.toJson())
);
~~~

Nesting:

~~~text
Polygon.coordinates
  = List<Ring>

Ring
  = List<Position>

Position
  = List<Double> [longitude, latitude]
~~~

Thiếu một tầng array sẽ khiến cấu trúc không phải Polygon đúng chuẩn.

## 34. Java helper để validate Point

~~~java
import java.util.Arrays;
import org.bson.Document;

public final class GeoJsonFactory {

    private GeoJsonFactory() {}

    public static Document point(
            double longitude,
            double latitude
    ) {
        if (!Double.isFinite(longitude) ||
                !Double.isFinite(latitude)) {
            throw new IllegalArgumentException(
                    "Tọa độ phải hữu hạn"
            );
        }

        if (longitude < -180 || longitude > 180) {
            throw new IllegalArgumentException(
                    "Longitude ngoài [-180,180]"
            );
        }

        if (latitude < -90 || latitude > 90) {
            throw new IllegalArgumentException(
                    "Latitude ngoài [-90,90]"
            );
        }

        return new Document("type", "Point")
                .append(
                        "coordinates",
                        Arrays.asList(
                                longitude,
                                latitude
                        )
                );
    }
}
~~~

Hàm này kiểm tra range và kiểu số, không tự biết source đảo trục khi cả hai số hợp lệ.

### 34.1. Tên tham số tránh bug

~~~java
GeoJsonFactory.point(
        request.longitude(),
        request.latitude()
);
~~~

dễ rà soát hơn các tham số không có nghĩa như a và b.

## 35. REST API contract

API nhận dữ liệu nên có tên field rõ:

~~~json
{
  "name": "Cửa hàng A",
  "location": {
    "longitude": 106.70098,
    "latitude": 10.77689
  }
}
~~~

Service chuyển thành:

~~~javascript
{
  type: "Point",
  coordinates: [
    body.location.longitude,
    body.location.latitude
  ]
}
~~~

Nếu frontend map library cần [lat,lon], hãy chuyển **ở boundary của thư viện đó**, không sửa quy tắc của GeoJSON trong database.

### 35.1. API trả GeoJSON trực tiếp

Nếu API đã công bố một field tuân theo GeoJSON, luôn giữ đúng [lon,lat]. Không trả [lat,lon] dưới một object ghi type: "Point".

### 35.2. Breaking change

Nếu phiên bản API cũ từng dùng coordinates theo [lat,lon], chuyển sang GeoJSON chuẩn là thay đổi contract. Cần version/migration thay vì sửa thầm và sinh bản ghi không nhất quán.

## 36. Precision và accuracy

Một tọa độ có 10 chữ số thập phân không có nghĩa nguồn định vị chính xác đến mức tương ứng.

- **Precision:** cách số được biểu diễn.
- **Accuracy:** mức gần với vị trí thực tế.
- **Uncertainty:** độ không chắc chắn/dao động của phép đo.

Ví dụ GPS dưới mái nhà hoặc giữa các tòa nhà có thể lệch nhiều mét dù số longitude/latitude có nhiều chữ số.

### 36.1. Lưu accuracyMeters khi có

~~~javascript
{
  location: {
    type: "Point",
    coordinates: [106.70098, 10.77689]
  },
  accuracyMeters: 40,
  locationSource: "gps"
}
~~~

Nếu ứng dụng quyết định “đã vào vùng 20 m”, phải cân nhắc việc sai số định vị có thể lớn hơn biên kiểm tra.

### 36.2. Làm tròn làm thay đổi vị trí

Làm tròn tọa độ quá mạnh có thể đẩy điểm sang phía khác của một Polygon nhỏ. Chọn precision theo yêu cầu, không làm tròn vô căn cứ.

## 37. Explain và hiệu năng

Có thể xem query plan:

~~~javascript
db.places.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $maxDistance: 5000
    }
  }
}).explain("executionStats");
~~~

Quan sát:

- Index được sử dụng.
- Documents/keys examined.
- Số kết quả.
- Chi phí xử lý geo và filter khác.
- Stage và plan theo MongoDB version.

Đừng so thời gian một lần query rồi kết luận mọi geo index luôn nhanh; cache, số lượng dữ liệu, kích thước polygon, query cardinality và mạng có ảnh hưởng.

### 37.1. Query trên sharded cluster

Một collection sharded có thể phân bố nhiều shards. 2dsphere index không tự giúp truy vấn target một shard nếu shard-key predicate không hạn chế được phạm vi.

Cần đọc explain để biết shard nào tham gia và local plan ở từng shard.

### 37.2. Hình học quá phức tạp

Polygon có hàng trăm nghìn vertices hoặc query trả hàng triệu điểm có thể tốn CPU/memory/network. Geospatial index không làm chi phí tính toán hình học và truyền dữ liệu biến mất.

## 38. Những nhầm lẫn thường gặp

| Sai lầm | Hậu quả |
| --- | --- |
| Lưu [latitude, longitude] trong GeoJSON | Sai vị trí hoặc lỗi vĩ độ |
| Thấy EPSG:4326 và bỏ qua axis order | Trộn lat/lon và lon/lat |
| Dùng EPSG:3857 x/y như độ | Out-of-range/sai CRS |
| Dùng strings cho coordinates | Không phải numeric GeoJSON position |
| Để longitude > 180 hoặc latitude > 90 | Geometry không hợp lệ |
| Tin range validation phát hiện mọi đảo trục | Hai số có thể vẫn hợp lệ |
| Point chỉ có một số | Thiếu position |
| Polygon thiếu một tầng array | Sai nesting rings |
| Ring không khép kín | Polygon không đúng cấu trúc |
| Ring tự giao | Topology sai |
| Hole nằm ngoài outer ring | Vùng sai |
| Dùng Point cho nhiều positions | Sai geometry type |
| Nhầm FeatureCollection với geometry field | Index/query sai path |
| Dùng LineString thay routing đường bộ | Không có tuyến đường thực tế |
| Dùng MultiPoint khổng lồ cho GPS history | Khó update và vượt document limit |
| Tính khoảng cách Euclid trên độ | Không có đơn vị mét đúng |
| Dùng $maxDistance=5 để tìm 5 km | Chỉ 5 mét trong ngữ cảnh GeoJSON near |
| Dùng $centerSphere radius=5000 | Radian, không phải mét |
| Coi $geoWithin sort gần–xa | Không bảo đảm thứ tự khoảng cách |
| Coi $geoNear trả ETA | Không có đường đi/traffic |
| Nhầm 2d và 2dsphere | Dùng sai mô hình khoảng cách |
| Đặt 2dsphere index trên sai field | Query không dùng đúng index |
| Tin nhiều chữ số là accuracy cao | Precision khác accuracy |
| Wrap longitude tùy tiện | Có thể che lỗi CRS |
| Swap tất cả record không phân loại | Làm hỏng record vốn đúng |
| Không test antimeridian | Vùng/đường có thể hiểu sai |
| Không xem winding với polygon lớn | Chọn miền bù ngoài ý muốn |
| Coi GeoJSON tự geocode địa chỉ | Geometry không tự sinh từ text |

## 39. Bài tập thực hành

### Bài 1 – Tọa độ chuẩn

API trả:

~~~json
{"lat":10.77689,"lng":106.70098}
~~~

Viết GeoJSON Point. Giá trị nào phải đứng trước?

### Bài 2 – Đảo trục rõ ràng

Tìm lỗi của:

~~~javascript
{
  type: "Point",
  coordinates: [10.77689, 106.70098]
}
~~~

Vì sao latitude vượt 90°?

### Bài 3 – Đảo trục khó phát hiện

So sánh [2.35,48.86] và [48.86,2.35]. Vì sao cả hai đều có thể được lưu dù một cặp không đúng địa điểm?

### Bài 4 – CRS

Nguồn trả EPSG:3857 x/y theo mét. Liệt kê bước cần thực hiện trước khi tạo GeoJSON WGS84.

### Bài 5 – Polygon

Viết một Polygon chữ nhật hợp lệ gồm ring có năm positions và vị trí đầu trùng cuối. Giải thích nesting của coordinates.

### Bài 6 – Hole

Tạo một Polygon có outer ring và một lỗ. Nêu điều kiện về ring orientation và việc lỗ phải nằm trong outer ring.

### Bài 7 – MultiPolygon

Vùng phục vụ có hai khu vực không liền kề. Vì sao không nối các đỉnh thành một Polygon duy nhất?

### Bài 8 – LineString

Ghi một LineString gồm bốn GPS positions. Vì sao nó không tự lưu timestamp/ETA của tuyến xe?

### Bài 9 – 2dsphere index

Tạo places với location Point, rồi tạo 2dsphere index. Thử một Point latitude = 100 trong lab và ghi nhận cách server xử lý.

### Bài 10 – $near

Viết truy vấn tìm những Point trong bán kính 3.000 mét, sắp theo khoảng cách. Vì sao không dùng $maxDistance=3 để biểu diễn 3 km?

### Bài 11 – $geoWithin

Viết một Polygon vùng giao hàng và truy vấn các Point bên trong. Nếu cần lấy gần nhất, operator này có tự sắp xếp không?

### Bài 12 – $geoIntersects

Tìm các serviceAreas cắt qua một Polygon kiểm tra. Phân biệt giao nhau và nằm hoàn toàn bên trong.

### Bài 13 – $geoNear

Dùng aggregation $geoNear để trả distanceMeters cho các địa điểm quanh một Point. Stage $geoNear được đặt ở đâu trong pipeline?

### Bài 14 – $centerSphere

Bán kính dùng đơn vị gì? Vì sao không truyền số mét trực tiếp vào tham số thứ hai?

### Bài 15 – Java

Viết Java helper GeoJsonFactory.point(longitude,latitude) kiểm tra finite/range rồi tạo BSON Document GeoJSON.

### Bài 16 – Import CSV

CSV có cột lat,lng theo thứ tự đó. Viết mapping sang GeoJSON [lon,lat] và báo lỗi record không hợp lệ.

### Bài 17 – Dữ liệu legacy pha trộn

Một số record đúng [lon,lat], số khác sai [lat,lon]. Thiết kế migration theo nguồn/version, vì sao không swap tất cả?

### Bài 18 – Antimeridian

Hai điểm 179.8° và -179.8° longitude có thể gần nhau thế nào? Vì sao bbox x/y đơn giản có thể sai?

### Bài 19 – Accuracy

Một GPS point có 10 chữ số thập phân nhưng accuracyMeters = 40. Nó có chính xác tới centimet không?

### Bài 20 – Sharding và geospatial

Một sharded collection dùng shard key tenantId. Query chỉ có $near trên location. Có chắc chỉ một shard tham gia không? Cần xem explain gì?

### Bài 21 – FeatureCollection

Một file GeoJSON chứa 1.000 Feature. Thiết kế import thành MongoDB documents để mỗi Feature có thể được tìm bằng 2dsphere index.

### Bài 22 – Service-area overlap

Một Point khách hàng thuộc hai Polygon vùng phục vụ. Cần thêm quy tắc nghiệp vụ nào để chọn cửa hàng?

## 40. Checklist trước production

1. Xác định CRS thật sự của mỗi nguồn dữ liệu.
2. Xác định axis order của nguồn và chuẩn hóa [lon,lat].
3. Kiểm tra số hữu hạn và phạm vi longitude/latitude.
4. Có bài test bắt lỗi đảo trục ngay cả khi cả hai số hợp lệ.
5. Dùng Point/LineString/Polygon/Multi* đúng ý nghĩa.
6. Đóng polygon rings, kiểm tra winding, holes và self-intersections.
7. Xử lý antimeridian/polar/large polygon khi liên quan.
8. Chuyển CRS projected sang WGS84, không chỉ đổi tên field.
9. Không giả định 2dsphere tính độ cao 3D.
10. Lưu accuracy/source/updatedAt theo nhu cầu.
11. Chỉ dùng geometry field có schema rõ.
12. Tạo 2dsphere index đúng field và sau khi dữ liệu đủ sạch.
13. Phân biệt $near, $geoWithin, $geoIntersects và $geoNear.
14. Kiểm tra mét với near/geoNear, radian với centerSphere.
15. Không thay khoảng cách địa lý cho distance đường bộ.
16. Kiểm tra query plans và index performance.
17. Nếu sharded, kiểm tra shard-key targeting.
18. Thiết kế API có tên longitude/latitude tường minh.
19. Có migration/test cho dữ liệu cũ lat/lng.
20. Có tọa độ mẫu được đối chiếu trên bản đồ.
21. Theo dõi tỷ lệ record địa lý lỗi và độ trễ query.
22. Có kế hoạch khi dữ liệu GPS quá chính xác giả hoặc quá cũ.

## 41. Kết luận

GeoJSON cung cấp mô hình JSON cho dữ liệu địa lý, từ điểm **Point**, đường **LineString** đến vùng **Polygon** và các geometry tổng hợp. MongoDB có thể lưu những geometry này, tạo **2dsphere index** và truy vấn theo khoảng cách, chứa trong vùng hoặc giao cắt.

Quy tắc quan trọng nhất:

> **Một GeoJSON position hai chiều luôn theo thứ tự [longitude, latitude] — [kinh độ, vĩ độ].**

Cả hai giá trị là **độ**, thường theo WGS84. Kinh độ nằm trong [-180,180], vĩ độ trong [-90,90]. Không nhầm với lat/lng của một số API, axis order của một số thư viện EPSG:4326, hay x/y theo mét của Web Mercator.

Khi sử dụng MongoDB:

- Lưu Point cho một vị trí, LineString cho đường, Polygon/MultiPolygon cho vùng.
- Giữ đúng nesting của coordinates, đóng ring và kiểm tra topology.
- Tạo **2dsphere index** trên trường geometry.
- Dùng **$near/$geoNear** cho khoảng cách, **$geoWithin** cho nằm trong, **$geoIntersects** cho giao nhau.
- Phân biệt đơn vị độ, mét và radian ở những vị trí khác nhau của query.
- Xác thực dữ liệu nguồn, kiểm tra lỗi đảo trục và thử những trường hợp biên.

**GeoJSON hợp lệ về cú pháp chưa bảo đảm vị trí đúng trên Trái Đất.** Mô hình hình học, thứ tự trục và hệ tọa độ nguồn phải được xác định cùng nhau.

## Tài liệu tham khảo

- [MongoDB Manual — Geospatial Queries](https://www.mongodb.com/docs/manual/geospatial-queries/)
- [MongoDB Manual — GeoJSON Objects](https://www.mongodb.com/docs/manual/reference/geojson/)
- [MongoDB Manual — Geospatial Indexes](https://www.mongodb.com/docs/manual/core/geospatial-indexes/)
- [MongoDB Manual — 2dsphere Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/)
- [MongoDB Manual — $near](https://www.mongodb.com/docs/manual/reference/operator/query/near/)
- [MongoDB Manual — $geoWithin](https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/)
- [MongoDB Manual — $geoIntersects](https://www.mongodb.com/docs/manual/reference/operator/query/geoIntersects/)
- [MongoDB Manual — $geoNear](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geoNear/)
- [MongoDB Manual — Geospatial Query Operators](https://www.mongodb.com/docs/manual/reference/operator/query-geospatial/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [GeoJSON RFC 7946](https://www.rfc-editor.org/rfc/rfc7946)
