# Khoảng cách, đơn vị đo và xử lý ranh giới địa lý trong MongoDB

Một hệ thống giao hàng muốn tìm những điểm nhận hàng trong bán kính 500 mét; một ứng dụng quản lý đội xe cần xác định xe đã vào hay ra khỏi khu vực được phép; một công cụ giám sát thiên tai phải biết tuyến đường nào giao với vùng ngập. Cả ba đều là **bài toán dữ liệu địa lý**, nhưng chúng đặt ra những câu hỏi khác nhau:

- **Khoảng cách:** đối tượng nào gần một vị trí và cách bao nhiêu mét?
- **Thuộc vùng:** điểm hoặc hình học nào nằm trong một khu vực?
- **Giao nhau:** đường, điểm hay polygon nào cắt hoặc chạm một hình học khác?

MongoDB hỗ trợ những câu hỏi này qua **GeoJSON**, chỉ mục **`2dsphere`** và các toán tử `$near`, `$nearSphere`, `$geoNear`, `$geoWithin`, `$geoIntersects`. Tuy nhiên, sai lầm nguy hiểm nhất thường không phải cú pháp: đó là **nhầm kinh/vĩ độ (đơn vị độ) với khoảng cách (mét), hoặc nhầm bán kính góc (radian) với mét**. Sai một đơn vị có thể làm ứng dụng chọn vị trí cách hàng nghìn kilômét thay vì 500 mét.

Ranh giới cũng có nhiều tình huống phức tạp: điểm nằm sát biên polygon, vùng có lỗ, hai vùng chồng lên nhau, kinh tuyến đổi ngày ±180°, vùng gần cực, GPS sai số 20 m hoặc tọa độ bị đảo thứ tự. Database thực thi phép toán hình học, còn ứng dụng phải định nghĩa **ý nghĩa nghiệp vụ của bên trong, bên ngoài và không chắc chắn**.

Bài thuộc chương **Dữ liệu địa lý** của module *Database Engine Document MongoDB*. Các ví dụ sử dụng **mongosh**, thêm mã mẫu **Node.js** và **MongoDB Java Driver**. Bộ tọa độ ở khoảng 106,7° Đông, 10,78° Bắc hoàn toàn **giả lập**, không mô tả cửa hàng, vùng giao hàng hay địa giới pháp lý thật. Khi triển khai, cần kiểm tra phiên bản MongoDB/driver và yêu cầu của nguồn geometry chính thức.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Ghi GeoJSON đúng cấu trúc với thứ tự **[longitude, latitude]** và hệ quy chiếu WGS84.
2. Phân biệt mét, kilômét, độ và radian; biết khi nào phải chuyển đổi.
3. Chọn `2dsphere` cho tọa độ GPS thay vì nhầm với `2d` dùng mặt phẳng.
4. Tìm điểm gần nhất bằng `$near` hoặc `$nearSphere`, hiểu `$minDistance` và `$maxDistance`.
5. Dùng `$geoNear` để trả trường khoảng cách, và `distanceMultiplier` để đổi đơn vị hiển thị.
6. Tạo truy vấn trong vòng tròn bằng `$geoWithin + $centerSphere` với bán kính **radian**.
7. Dùng `$geoWithin` cho containment và `$geoIntersects` cho intersection.
8. Xây Polygon, Polygon có holes, MultiPolygon và xử lý nhiều khu vực trùng nhau.
9. Nhận diện tình huống trên biên, đỉnh, biên lỗ, sai số số học và GPS uncertainty.
10. Xử lý dateline ±180°, vĩ độ cao, polygon lớn và hình học không hợp lệ.
11. Phân biệt đường chim bay với quãng đường thực tế theo mạng lưới giao thông.
12. Đo hiệu năng `2dsphere` index và thiết kế bài kiểm thử geofence đáng tin cậy.

## 2. Proximity, containment và intersection

| Câu hỏi | Phép toán thích hợp | Ví dụ |
|---|---|---|
| Ai gần tôi nhất? | `$near` hoặc `$geoNear` | 10 điểm nhận hàng gần khách |
| Ai trong bán kính R? | `$near` hoặc `$geoWithin/$centerSphere` | Trạm cách dưới 500 m |
| Điểm nào nằm trong khu vực? | `$geoWithin/$geometry` | Thiết bị trong polygon |
| Khu vực nào chứa/giao với điểm? | `$geoIntersects/$geometry` | Tìm zone theo GPS |
| Đường nào cắt khu hạn chế? | `$geoIntersects` với LineString | Tuyến xe qua vùng ngập |

~~~mermaid
flowchart TD
    Goal["Bài toán địa lý"] --> Distance{"Cần khoảng cách / xếp gần nhất?"}
    Distance -->|"Có"| Near["$near / $geoNear"]
    Distance -->|"Không"| Inclusion{"Cần nằm hoàn toàn trong vùng?"}
    Inclusion -->|"Có"| Within["$geoWithin"]
    Inclusion -->|"Không, cần giao nhau"| Intersects["$geoIntersects"]
~~~

Một điểm gần **tâm** polygon chưa chắc nằm trong polygon. Một tuyến đường **cắt** polygon chưa chắc nằm **hoàn toàn trong** polygon. Một hình chữ nhật bao ngoài vùng không thay thế chính vùng đó.

## 3. Tọa độ GeoJSON: kinh độ trước, vĩ độ sau

GeoJSON Point:

~~~javascript
{
  type: "Point",
  coordinates: [106.7000, 10.7800]
}
~~~

Nghĩa là longitude 106,7° Đông và latitude 10,78° Bắc. Trong GeoJSON WGS84:

| Giá trị | Miền thông dụng | Đơn vị |
|---|---|---|
| Longitude | -180 đến +180 | Độ |
| Latitude | -90 đến +90 | Độ |

Không đảo thứ tự:

~~~javascript
// SAI: 106.7 không phải vĩ độ hợp lệ.
{
  type: "Point",
  coordinates: [10.7800, 106.7000]
}
~~~

Điểm nguy hiểm hơn là khi hai số sau khi đảo **đều** nằm trong miền hợp lệ: MongoDB có thể chấp nhận nhưng điểm nằm tại nơi khác trên Trái Đất.

### 3.1. GeoJSON Point và legacy coordinate pair

Hai định dạng sau không hoàn toàn đồng nghĩa:

~~~javascript
// GeoJSON Point: biểu diễn địa lý có type.
{ location: { type: "Point", coordinates: [106.7, 10.78] } }

// Legacy coordinate pair: định dạng cặp số cũ.
{ location: [106.7, 10.78] }
~~~

Khi chọn toán tử và chỉ mục, **đơn vị của tham số khoảng cách** có thể khác đáng kể giữa GeoJSON/`2dsphere` và legacy/`2d`. Vì thế, migration từ legacy data không chỉ là đổi cấu trúc lưu trữ; phải kiểm tra lại toàn bộ truy vấn liên quan radius.

### 3.2. Độ không phải mét

Một độ vĩ độ dài khoảng 111 km; còn độ dài một độ kinh độ thay đổi theo vĩ độ:

~~~text
Gần xích đạo: 1° longitude ~111 km
Vĩ độ 60°:   1° longitude ~55,5 km
Gần cực:     1° longitude tiến về 0 km
~~~

Do vậy, `longitude + 0.001` không tương đương tăng đúng 100 m ở mọi vị trí.

### 3.3. Độ cao

GeoJSON có thể có tọa độ thứ ba, nhưng không được suy ra rằng phép truy vấn `2dsphere` tính khoảng cách 3D theo độ cao. Đa số use case trong bài xét hình học **trên bề mặt cầu**; bài toán máy bay, drone hoặc khoảng cách ba chiều cần thêm mô hình chuyên dụng.

## 4. Phân biệt độ, radian, mét và kilômét

Một bảng quy tắc ngắn:

| Nơi dùng | Đơn vị phải lưu/truyền |
|---|---|
| GeoJSON `coordinates` | Longitude, latitude tính bằng **độ** |
| `$near` với GeoJSON Point và `2dsphere` | `$maxDistance`/`$minDistance` tính bằng **mét** |
| `$nearSphere` với GeoJSON Point và `2dsphere` | Khoảng cách bằng **mét** |
| `$geoNear` với GeoJSON Point, spherical | Khoảng cách đầu ra tính bằng **mét** trước multiplier |
| `$geoWithin + $centerSphere` | Bán kính tính bằng **radian** |
| `2d` planar distance trên tọa độ phẳng | Đơn vị của hệ tọa độ **phẳng** |
| Legacy spherical coordinate query | Có trường hợp dùng **radian**, theo operator/index |

### 4.1. Độ sang radian

\[
\theta_{\text{rad}}=\theta_{\text{deg}}\frac{\pi}{180}
\qquad
\theta_{\text{deg}}=\theta_{\text{rad}}\frac{180}{\pi}
\]

Ví dụ 180° = π radian, 90° = π/2 radian.

### 4.2. Độ dài cung và bán kính góc

Với bán kính Trái Đất trung bình tham khảo:

\[
R \approx 6\,371\,008.8\ \text{m}
\]

Ta có:

\[
\theta=\frac{d}{R}, \quad d=R\theta
\]

với `d` và `R` cùng đơn vị, `θ` tính bằng radian.

Ví dụ:

\[
500\text{ m}\rightarrow \frac{500}{6\,371\,008.8}
\approx 0.00007848\text{ rad}
\]

\[
2\text{ km}\rightarrow \frac{2000}{6\,371\,008.8}
\approx 0.0003139\text{ rad}
\]

Đây là phép đổi gần đúng theo mô hình hình cầu. Không dùng một bán kính trung bình để tuyên bố có độ chính xác đo đạc địa chính tuyệt đối.

### 4.3. Hàm chuyển đổi rõ đơn vị

~~~javascript
const EARTH_RADIUS_METERS = 6371008.8

function metersToRadians(meters) {
  if (!Number.isFinite(meters) || meters < 0) {
    throw new Error("INVALID_DISTANCE_METERS")
  }
  return meters / EARTH_RADIUS_METERS
}

function kilometersToRadians(kilometers) {
  return metersToRadians(kilometers * 1000)
}

print(metersToRadians(500))
print(kilometersToRadians(2))
~~~

**Không tự chia 500 cho bán kính Trái Đất khi dùng `$near` với GeoJSON Point:** trường `$maxDistance` trong trường hợp đó đã dùng mét. Hàm này cần cho `$centerSphere` hoặc những API angular-distance cụ thể.

## 5. Khoảng cách trên mặt cầu và khoảng cách đường đi

Một cách tính sai phổ biến:

~~~javascript
// SAI nếu muốn kết quả là mét.
const deltaLon = lon2 - lon1
const deltaLat = lat2 - lat1
const distanceMeters = Math.sqrt(deltaLon ** 2 + deltaLat ** 2)
~~~

Kết quả trên mang ý nghĩa chênh lệch **độ** và không xét độ dài longitude theo latitude. Với GeoJSON và `2dsphere`, MongoDB sử dụng mô hình hình học địa lý phù hợp trên mặt cầu.

### 5.1. Đường chim bay khác đường đi

Hai điểm có thể cách 400 m theo đường cung ngắn nhất, nhưng xe phải chạy 1,8 km do sông, cầu, đường một chiều hoặc lối vào tòa nhà. MongoDB `$near` không biết đường sá, tốc độ di chuyển, phương tiện hoặc giao thông.

Nếu sản phẩm cần **ETA** hay **giá cước theo số km chạy xe**, hãy dùng geospatial query để tìm **ứng viên gần**, rồi kết hợp routing engine/bản đồ đường để tính quãng đường thực hoặc thời gian. Không lấy `distanceMeters` của `$geoNear` làm số km xe chạy nếu hợp đồng không cho phép.

### 5.2. Hình cầu và ellipsoid

Trái Đất không phải hình cầu hoàn hảo. Truy vấn spherical của MongoDB phù hợp cho rất nhiều bài toán proximity/GIS ứng dụng nhưng không nhất thiết có độ chính xác đo đạc pháp lý/milimet. Khi phải xác định diện tích, biên đất hay hành lang an toàn chính xác cao, cần GIS/projection/mô hình ellipsoid chuyên dụng được kiểm định.

## 6. Cấu trúc GeoJSON thường dùng

### 6.1. Point

~~~javascript
{
  type: "Point",
  coordinates: [106.7000, 10.7800]
}
~~~

### 6.2. LineString

~~~javascript
{
  type: "LineString",
  coordinates: [
    [106.6970, 10.7770],
    [106.7000, 10.7800],
    [106.7090, 10.7850]
  ]
}
~~~

### 6.3. Polygon

~~~javascript
{
  type: "Polygon",
  coordinates: [[
    [106.6960, 10.7770],
    [106.7060, 10.7770],
    [106.7060, 10.7840],
    [106.6960, 10.7840],
    [106.6960, 10.7770]
  ]]
}
~~~

Polygon có **vòng (ring) khép kín**: tọa độ đầu và cuối trùng nhau. Một ring cần đủ đỉnh để tạo vùng hợp lệ, không được tự cắt. Vòng ngoài mô tả vùng, các vòng tiếp theo có thể biểu diễn **lỗ**.

### 6.4. MultiPolygon

~~~javascript
{
  type: "MultiPolygon",
  coordinates: [
    [[
      [106.690, 10.770],
      [106.695, 10.770],
      [106.695, 10.775],
      [106.690, 10.775],
      [106.690, 10.770]
    ]],
    [[
      [106.710, 10.790],
      [106.715, 10.790],
      [106.715, 10.795],
      [106.710, 10.795],
      [106.710, 10.790]
    ]]
  ]
}
~~~

MultiPolygon mô tả hai hoặc nhiều mảnh vùng địa lý. Đừng cố nối hai vùng rời bằng một ring hình nơ tự cắt.

## 7. `2dsphere` và `2d` index

| Index | Mô hình | Ứng dụng điển hình |
|---|---|---|
| `2dsphere` | Hình học spherical/GeoJSON | GPS/WGS84, vùng địa lý, gần nhất |
| `2d` | Hình học phẳng | Hệ tọa độ x/y cục bộ hoặc dữ liệu legacy |

Tạo `2dsphere` index:

~~~javascript
db.pickupPoints.createIndex(
  { location: "2dsphere" },
  { name: "idx_location_sphere" }
)
~~~

`$near`, `$nearSphere` và `$geoNear` cần geospatial index thích hợp. `$geoWithin` có thể thực hiện không index trong một số trường hợp, nhưng với dữ liệu lớn nên có index tương ứng. Một chỉ mục `2dsphere` có quy tắc về geometry hợp lệ và các document không có field địa lý; validation phải kiểm tra tọa độ trước khi ghi.

**Đừng dùng `2d` cho longitude/latitude toàn cầu chỉ vì suy đoán nó nhanh hơn.** Nó xử lý mặt phẳng, không giải quyết đúng những vấn đề về latitude, dateline và mặt cầu như `2dsphere`.

## 8. Khởi tạo lab: các điểm giả lập

Chỉ thao tác trên database lab:

~~~javascript
use geo_distance_lab

db.createCollection("pickupPoints")

db.pickupPoints.createIndex(
  { location: "2dsphere" },
  { name: "idx_location_sphere" }
)

db.pickupPoints.insertMany([
  {
    _id: "P-A", name: "Điểm A - tâm",
    active: true, type: "pickup",
    location: { type: "Point", coordinates: [106.7000, 10.7800] }
  },
  {
    _id: "P-B", name: "Điểm B - phía đông",
    active: true, type: "pickup",
    location: { type: "Point", coordinates: [106.7020, 10.7800] }
  },
  {
    _id: "P-C", name: "Điểm C - tây bắc",
    active: true, type: "pickup",
    location: { type: "Point", coordinates: [106.6970, 10.7810] }
  },
  {
    _id: "P-D", name: "Điểm D - đông bắc",
    active: true, type: "pickup",
    location: { type: "Point", coordinates: [106.7100, 10.7870] }
  },
  {
    _id: "P-E", name: "Điểm E - xa",
    active: true, type: "pickup",
    location: { type: "Point", coordinates: [106.7200, 10.8000] }
  },
  {
    _id: "P-F", name: "Điểm F - tây nam",
    active: false, type: "pickup",
    location: { type: "Point", coordinates: [106.6800, 10.7700] }
  },
  {
    _id: "P-G", name: "Điểm G - phía bắc",
    active: true, type: "pickup",
    location: { type: "Point", coordinates: [106.7000, 10.7830] }
  },
  {
    _id: "P-H", name: "Điểm H - phía nam",
    active: true, type: "pickup",
    location: { type: "Point", coordinates: [106.7030, 10.7760] }
  }
])

db.pickupPoints.countDocuments({}) // 8
~~~

Các tọa độ không đại diện cửa hàng hoặc địa chỉ có thật. Dữ liệu đủ nhỏ để quan sát semantics nhưng **không dùng để benchmark hiệu năng**. Nếu đã chạy setup, đừng insert lại cùng `_id`.

### 8.1. Tâm truy vấn

~~~javascript
const center = {
  type: "Point",
  coordinates: [106.7000, 10.7800]
}
~~~

P-A ở đúng tâm. P-B lệch đông 0,002° longitude (xấp xỉ 218 m ở latitude này), P-G lệch bắc 0,003° (~334 m). Không suy luận khoảng cách chính xác bằng cách lấy một hiệu độ nhân một hằng số ở mọi vĩ độ.

## 9. `$near`: tìm gần nhất bằng mét

~~~javascript
db.pickupPoints.find({
  active: true,
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      $maxDistance: 500
    }
  }
}, {
  _id: 1,
  name: 1,
  location: 1
}).limit(20)
~~~

Với **GeoJSON Point + `2dsphere`**, `$maxDistance:500` là **500 m**, không phải 500 độ hay 500 km. `$near` trả các điểm theo thứ tự khoảng cách gần trước. Nó không tự thêm field khoảng cách vào result.

### 9.1. Vành khuyên với `$minDistance`

~~~javascript
db.pickupPoints.find({
  active: true,
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      $minDistance: 100,
      $maxDistance: 500
    }
  }
})
~~~

Query chọn những điểm có khoảng cách nằm trong vành khuyên 100–500 m. Điểm ở đúng tâm có khoảng cách 0 và bị loại. Nếu muốn loại chính một business entity, filter `_id` thường rõ ràng hơn quy tắc khoảng cách nhỏ.

### 9.2. `$nearSphere`

~~~javascript
db.pickupPoints.find({
  location: {
    $nearSphere: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      $maxDistance: 500
    }
  }
})
~~~

Với GeoJSON Point trên `2dsphere`, `$maxDistance` vẫn là mét. `$nearSphere` mô tả spherical proximity; `$near` với GeoJSON/`2dsphere` cũng dùng hình học địa lý phù hợp. **Không suy từ tên toán tử rằng mọi trường hợp legacy coordinate pair cũng dùng mét**.

## 10. Legacy coordinate pairs và nguy cơ sai đơn vị

Một legacy point:

~~~javascript
{ location: [106.7000, 10.7800] }
~~~

có thể được dùng với chỉ mục `2d` và các toán tử legacy theo nghĩa **đơn vị tọa độ phẳng**. Các truy vấn spherical trên legacy pairs và `2dsphere` có những trường hợp biểu thị khoảng cách bằng **radian**. Vì thế:

~~~text
Legacy query: maxDistance = 0.005
GeoJSON query: maxDistance = 0.005
~~~

**Không được coi là cùng bán kính** nếu chưa xác định index, operator, kiểu geometry và đơn vị từng trường hợp. Khi migrate:

1. Xác định dữ liệu thực là WGS84 longitude/latitude hay hệ phẳng.
2. Xác định index hiện tại là `2d` hay `2dsphere`.
3. Xác định đơn vị hiện tại của `$maxDistance`.
4. Viết lại adapter API theo **mét** làm đơn vị business rõ ràng.
5. Kiểm thử tập điểm ở khoảng cách đã biết.

## 11. `$geoNear`: trả khoảng cách trong aggregation

Nếu API cần cả thứ tự lẫn giá trị khoảng cách:

~~~javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      key: "location",
      spherical: true,
      distanceField: "distanceMeters",
      maxDistance: 500,
      query: {
        active: true,
        type: "pickup"
      }
    }
  },
  {
    $project: {
      name: 1,
      distanceMeters: 1,
      location: 1
    }
  },
  { $limit: 20 }
])
~~~

Trong trường hợp GeoJSON spherical này, `distanceMeters` tính bằng **mét**. `key:"location"` chỉ rõ geospatial field/index, hữu ích nếu collection có nhiều geospatial indexes.

### 11.1. `$geoNear` phải là stage đầu

Không viết:

~~~javascript
// SAI: $geoNear không đặt sau $match.
db.pickupPoints.aggregate([
  { $match: { active: true } },
  { $geoNear: { /* ... */ } }
])
~~~

Đặt filter bình thường vào `query` của `$geoNear`, rồi dùng các stage tiếp theo để project/limit/ranking.

### 11.2. Đổi khoảng cách sang kilômét

~~~javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      key: "location",
      spherical: true,
      distanceField: "distanceKm",
      maxDistance: 2000,
      distanceMultiplier: 0.001
    }
  },
  { $project: { name: 1, distanceKm: 1 } }
])
~~~

`distanceMultiplier:0.001` đổi **kết quả từ mét sang km**. `maxDistance:2000` vẫn là **2.000 m**; không bị multiplier đổi thành 2.000 km.

### 11.3. `find + $near` hay `aggregate + $geoNear`?

| Yêu cầu | Gợi ý |
|---|---|
| Chỉ cần những điểm gần nhất theo bán kính | `find` + `$near` |
| Cần distance field cho UI/API | `aggregate` + `$geoNear` |
| Cần gộp thêm thống kê/ranking từ khoảng cách | `$geoNear` rồi pipeline |
| Chỉ cần inside circle, không sort | `$geoWithin` + `$centerSphere` |

Không thêm một `$sort` khác rồi vẫn gọi kết quả là nearest-first khi thứ tự đã bị thay đổi.

## 12. `$geoWithin + $centerSphere`: bán kính là radian

Lọc tất cả points trong vòng tròn bán kính 500 m mà **không cần** thứ tự gần nhất:

~~~javascript
const centerLonLat = [106.7000, 10.7800]
const earthRadiusMeters = 6371008.8
const radiusMeters = 500

db.pickupPoints.find({
  active: true,
  location: {
    $geoWithin: {
      $centerSphere: [
        centerLonLat,
        radiusMeters / earthRadiusMeters
      ]
    }
  }
})
~~~

Đây là nơi cần **chuyển mét → radian**. Không viết:

~~~javascript
// SAI: $centerSphere không nhận bán kính 500 mét trực tiếp.
$centerSphere: [[106.7000, 10.7800], 500]
~~~

### 12.1. `$near` khác `$centerSphere`

- `$near` trên GeoJSON: radius/maxDistance theo **mét**, thường trả kết quả theo khoảng cách.
- `$geoWithin + $centerSphere`: radius theo **radian**, không bảo đảm sắp theo khoảng cách.
- `$geoNear`: trả distance field, có thể convert sang km bằng multiplier.

### 12.2. Không trộn đơn vị trong API

Một API nên nhận `radiusMeters` có validate, và chỉ adapter database biết lúc nào chuyển đổi. Không để các nhóm frontend/backend tự quyết định `radius` là mét hay km.

## 13. `$geoWithin + $geometry`: điểm nằm trong polygon

Vùng giả lập:

~~~javascript
const deliveryArea = {
  type: "Polygon",
  coordinates: [[
    [106.6960, 10.7770],
    [106.7060, 10.7770],
    [106.7060, 10.7840],
    [106.6960, 10.7840],
    [106.6960, 10.7770]
  ]]
}
~~~

Lọc các pickup points thuộc vùng:

~~~javascript
db.pickupPoints.find({
  active: true,
  location: {
    $geoWithin: {
      $geometry: deliveryArea
    }
  }
})
~~~

Kết quả trả lời **thuộc polygon**, không phải trong vòng tròn 500 m quanh tâm. Hai điểm cách tâm cùng một khoảng có thể một điểm thuộc, một điểm ngoài vùng.

### 13.1. Polygon có hole

~~~javascript
const deliveryAreaWithHole = {
  type: "Polygon",
  coordinates: [
    [
      [106.6960, 10.7770],
      [106.7060, 10.7770],
      [106.7060, 10.7840],
      [106.6960, 10.7840],
      [106.6960, 10.7770]
    ],
    [
      [106.6990, 10.7790],
      [106.6990, 10.7810],
      [106.7010, 10.7810],
      [106.7010, 10.7790],
      [106.6990, 10.7790]
    ]
  ]
}
~~~

Vòng ngoài đi ngược chiều kim đồng hồ; vòng lỗ theo chiều kim đồng hồ trong biểu diễn longitude–latitude này, phù hợp quy ước right-hand rule thông dụng. Trong production, validator nên kiểm tra ring orientation, closed rings, self-intersection và quy tắc phiên bản.

Điểm P-A ở `[106.7000,10.7800]` nằm trong **lỗ**, nên không thuộc phần phủ của polygon có hole. Ring thứ hai **không phải** polygon được cộng thêm vào vùng.

### 13.2. MultiPolygon

Nếu một khu vực có hai phần tách nhau, dùng `MultiPolygon`. Không đặt vòng thứ hai vào `Polygon.coordinates` rồi nhầm đó là một vùng thêm: nó có thể bị hiểu là hole.

## 14. `$geoIntersects`: vùng chứa điểm, đường cắt vùng

Trong `pickupPoints`, field `location` là Point và query là Polygon. Một cấu trúc khác là collection chứa **các polygons** và query truyền vào một Point:

~~~javascript
db.createCollection("zones")
db.zones.createIndex(
  { geometry: "2dsphere" },
  { name: "idx_zone_geometry" }
)

db.zones.insertMany([
  {
    _id: "zone-central",
    name: "Vùng trung tâm giả lập",
    active: true,
    geometry: {
      type: "Polygon",
      coordinates: [[
        [106.6960, 10.7770],
        [106.7060, 10.7770],
        [106.7060, 10.7840],
        [106.6960, 10.7840],
        [106.6960, 10.7770]
      ]]
    }
  },
  {
    _id: "zone-northeast",
    name: "Vùng đông bắc giả lập",
    active: true,
    geometry: {
      type: "Polygon",
      coordinates: [[
        [106.7050, 10.7810],
        [106.7150, 10.7810],
        [106.7150, 10.7910],
        [106.7050, 10.7910],
        [106.7050, 10.7810]
      ]]
    }
  }
])
~~~

Tìm zones giao với điểm P-B:

~~~javascript
db.zones.find({
  active: true,
  geometry: {
    $geoIntersects: {
      $geometry: {
        type: "Point",
        coordinates: [106.7020, 10.7800]
      }
    }
  }
})
~~~

P-B nằm trong zone-central theo geometry giả lập, không thuộc zone-northeast. Nhưng một điểm ở phần chồng của hai zones có thể trả **hai bản ghi**.

### 14.1. Tìm zones bị tuyến đường cắt

~~~javascript
const courierRoute = {
  type: "LineString",
  coordinates: [
    [106.6930, 10.7780],
    [106.7010, 10.7810],
    [106.7120, 10.7870]
  ]
}

db.zones.find({
  geometry: {
    $geoIntersects: {
      $geometry: courierRoute
    }
  }
})
~~~

`$geoIntersects` trả lời **có giao** hay không, không tự tính “tuyến nằm trong vùng bao nhiêu mét”. Nếu cần cắt đường theo polygon hoặc đo đoạn tuyến bị ảnh hưởng, cần geometry clipping và tính chiều dài chuyên dụng.

## 15. Ranh giới địa lý: inside, outside, edge, vertex và hole

Những trạng thái cần phân biệt:

~~~text
INSIDE      Điểm rõ ràng trong vùng
OUTSIDE     Điểm rõ ràng ngoài vùng
EDGE        Điểm trùng một cạnh
VERTEX      Điểm trùng một đỉnh
IN_HOLE     Điểm ở phần lỗ bị loại
NEAR_EDGE   Điểm sát biên, chịu ảnh hưởng sai số
OVERLAP     Điểm thuộc nhiều vùng chồng lên nhau
~~~

Không mặc định mọi toán tử đều xử lý điểm đúng boundary giống hệt nhau. Một số trường hợp containment `$geoWithin` với geometry trùng cạnh/chia sẻ ranh giới không có bảo đảm như người dùng trực giác kỳ vọng. `$geoIntersects` nói về giao hình học, nhưng vẫn phải kiểm thử dữ liệu gần biên, floating-point precision và phiên bản engine.

### 15.1. Chính sách phải thuộc về nghiệp vụ

Ứng dụng cần định nghĩa:

- **Inclusive boundary:** điểm đúng biên được tính là trong vùng.
- **Exclusive boundary:** điểm đúng biên bị loại.
- **Priority rule:** hai zones cùng chứa điểm thì chọn vùng nào?
- **Uncertain band:** điểm đủ gần biên thì không kết luận ngay vì GPS có sai số.

MongoDB không tự đặt ra hợp đồng pháp lý cho “trên ranh giới được phép hay không”.

### 15.2. Nguồn sai số

- GPS báo vị trí có sai số vài mét đến hàng chục mét.
- Tọa độ bị làm tròn.
- Polygon được số hóa từ ảnh bản đồ có độ phân giải giới hạn.
- Nguồn GIS dùng CRS khác nhưng chưa chuyển về WGS84.
- Hai polygon chung cạnh nhưng dữ liệu tồn tại khe hở/đè lên nhau.
- Floating-point và phép toán hình học trên mặt cầu có giới hạn số học.

Đừng chữa sai lệch bằng cách tự thêm một tolerance bất kỳ vào mọi query mà không quy định nó ảnh hưởng thế nào tới nghiệp vụ.

## 16. GPS uncertainty: vì sao một Boolean chưa đủ

Giả sử một thiết bị báo điểm P:

~~~text
Khoảng cách ước lượng tới ranh giới: 8 m
Độ chính xác GPS báo:              25 m
Kết quả query point-in-polygon:      INSIDE
~~~

Vì độ bất định lớn hơn khoảng cách tới biên, kết luận chắc chắn “đã vào vùng” có thể sai.

Một API có thể trả:

~~~javascript
{
  zoneId: "zone-central",
  classification: "UNCERTAIN_NEAR_BOUNDARY",
  gpsAccuracyMeters: 25,
  boundaryDistanceMeters: 8,
  observedAt: ISODate("2026-10-01T08:00:00Z")
}
~~~

### 16.1. Ba mức phân loại gợi ý

1. `CONFIDENT_INSIDE` nếu điểm ở trong và cách biên xa hơn uncertainty + margin.
2. `CONFIDENT_OUTSIDE` nếu ở ngoài và cách biên đủ xa.
3. `UNCERTAIN` nếu nằm trong vùng đệm sát biên.

**Quan trọng:** `$geoWithin` không tự tính khoảng cách tới biên Polygon. Muốn có `boundaryDistanceMeters`, cần một thuật toán/engine GIS phù hợp để đo **đường biên**, không dùng khoảng cách tới centroid.

### 16.2. Buffer không phải vòng tròn quanh centroid

Để “nới rộng polygon 20 m”, không thể thay nó bằng một `$centerSphere` 20 m quanh tâm. Một phép **buffer polygon** cần xử lý cạnh, góc, holes và CRS/mô hình đo đúng. MongoDB không cung cấp một tham số `bufferMeters` chung cho mọi truy vấn `$geoWithin`.

### 16.3. Hysteresis chống rung geofence

Một xe đứng sát biên có thể được GPS báo:

~~~text
08:00 INSIDE
08:01 OUTSIDE
08:02 INSIDE
08:03 OUTSIDE
~~~

Nếu phát ENTER/EXIT ở mỗi điểm, ứng dụng tạo cảnh báo liên tục. Một mô hình khả dụng:

~~~mermaid
stateDiagram-v2
    [*] --> UNKNOWN
    UNKNOWN --> OUTSIDE: Đủ điểm ngoài ổn định
    UNKNOWN --> INSIDE: Đủ điểm trong ổn định
    OUTSIDE --> MAYBE_ENTER: Điểm bắt đầu vượt biên
    MAYBE_ENTER --> INSIDE: N lần ổn định + margin
    MAYBE_ENTER --> OUTSIDE: Quay lại ngoài
    INSIDE --> MAYBE_EXIT: Điểm bắt đầu ra
    MAYBE_EXIT --> OUTSIDE: N lần ổn định + margin
    MAYBE_EXIT --> INSIDE: Quay lại trong
~~~

Số lần đo và margin cần chọn theo tốc độ di chuyển, độ chính xác, tần suất thiết bị và rủi ro nghiệp vụ. Một vùng nguy hiểm có thể ưu tiên cảnh báo sớm thay vì chờ quá lâu.

## 17. Polygon hợp lệ: rings, holes và self-intersection

Một GeoJSON polygon hợp lệ cần:

- Ring **khép**: đỉnh đầu và cuối trùng nhau.
- Đủ vị trí để tạo vùng có diện tích.
- Không có đường biên tự cắt.
- Holes nằm bên trong vòng ngoài và không mâu thuẫn.
- Winding hợp lý theo GeoJSON/MongoDB, nhất là polygon rất lớn.
- Coordinates là số với thứ tự lon/lat đúng.

Ví dụ polygon bị thiếu tọa độ đóng:

~~~javascript
// SAI: vòng chưa khép.
{
  type: "Polygon",
  coordinates: [[
    [106.69, 10.77],
    [106.71, 10.77],
    [106.71, 10.79],
    [106.69, 10.79]
  ]]
}
~~~

Một ring hình nơ tự cắt cũng không phải geometry hợp lệ chỉ vì các đỉnh đều trong miền longitude/latitude. Cần validation GIS trước khi insert hoặc tại ingestion; không “sửa” bằng cách bỏ ngẫu nhiên một đỉnh.

### 17.1. Biên lỗ cũng là biên

Một điểm nằm sát **mép hole** phải tuân cùng chính sách uncertainty như điểm sát biên ngoài. Không chỉ tính khoảng cách đến outer ring rồi quên inner rings.

### 17.2. Một vùng tách thành nhiều mảnh

Khi một thành phố có hai khu vực giao hàng rời nhau, chọn `MultiPolygon` hoặc nhiều zone documents với policy cụ thể. Không nhét hai rings rời vào cùng Polygon và coi cả hai là vùng cộng, vì các rings sau có ý nghĩa hole theo cấu trúc.

## 18. Polygon lớn hơn bán cầu và strict winding

Đối với một polygon rất lớn, vòng trên mặt cầu có thể phân biệt **vùng nhỏ được bao** và **vùng bổ sung lớn hơn nửa Trái Đất**. MongoDB có cơ chế **strict winding CRS** cho những single-ring polygons lớn hơn bán cầu ở các trường hợp hỗ trợ:

~~~javascript
{
  type: "Polygon",
  coordinates: [
    // Một vòng khép kín, đúng winding,
    // chứa các tọa độ thực tế của polygon lớn.
  ],
  crs: {
    type: "name",
    properties: {
      name: "urn:x-mongodb:crs:strictwinding:EPSG:4326"
    }
  }
}
~~~

Đây là **mẫu cấu trúc** chứ không phải polygon có thể chạy: `coordinates` còn phải thay bằng ring hợp lệ. Không gắn custom CRS này vào mọi Point hay vùng nhỏ. Khi xử lý polygon lớn:

1. Kiểm tra diện tích tương đối với một bán cầu.
2. Kiểm tra winding phù hợp.
3. Xác định toán tử và phiên bản MongoDB hỗ trợ custom CRS.
4. Dùng các điểm test rõ ràng ở vùng dự định và ở phía đối diện Trái Đất.
5. Không suy luận “phần trắng trên bản đồ phẳng” là bên ngoài trên mặt cầu.

## 19. Kinh tuyến đổi ngày ±180°

Hai vị trí:

~~~text
Điểm A: longitude +179,8°
Điểm B: longitude -179,8°
~~~

chỉ cách nhau **0,4° longitude qua dateline**, không phải 359,6° theo đường cung ngắn nhất.

### 19.1. Sai với một bounding box tuyến tính

~~~javascript
// Không biểu diễn đúng một vùng băng qua dateline.
{
  longitude: {
    $gte: 179.5,
    $lte: -179.5
  }
}
~~~

Điều kiện này có cận dưới lớn hơn cận trên. Nếu dùng bounding boxes làm prefilter, cần chia thành hai khoảng `[179.5,180]` và `[-180,-179.5]` hoặc dùng mô hình GeoJSON/MultiPolygon được xử lý đúng trên mặt cầu.

### 19.2. Geometry qua dateline

Đừng vẽ một ring “170° → -170°” rồi mặc định mọi engine hiểu đúng **phía** muốn bao. Cần chuẩn hóa representation và chạy tests với các điểm ở cả hai phía ±180°, cả phía không mong muốn. Những vùng phức tạp có thể cần được biểu diễn bằng **MultiPolygon** sau khi xử lý bằng GIS.

### 19.3. ±180 biểu diễn cùng kinh tuyến

Ở điểm kết nối dateline, +180 và -180 có ý nghĩa địa lý liên quan nhưng là hai giá trị số khác nhau. Cần policy chuẩn hóa và test biên trong ứng dụng; không để một API ngầm định +180 còn API khác yêu cầu -180 mà thiếu quy tắc.

## 20. Gần cực: longitude không còn là thước đo độ dài ổn định

Gần vĩ độ ±90°, các kinh tuyến hội tụ. Hai điểm chênh longitude lớn vẫn có thể gần nhau theo khoảng cách thực. Những phép xấp xỉ kiểu:

~~~text
deltaLongDegrees * 111000 = meters
~~~

sai nghiêm trọng khi latitude tăng cao. Với vùng cực và dữ liệu hàng không/hàng hải, phải dùng spherical geometry hoặc phép tính chuyên dụng được thẩm định, kiểm thử points gần cực và polygon winding.

## 21. Haversine: tính khoảng cách tham khảo ở application

Cho vĩ độ `φ₁`, `φ₂` và hiệu vĩ/kinh độ `Δφ`, `Δλ` tính bằng radian:

\[
a=\sin^2\left(\frac{\Delta\varphi}{2}\right)
 +\cos(\varphi_1)\cos(\varphi_2)\sin^2\left(\frac{\Delta\lambda}{2}\right)
\]

\[
c=2\operatorname{atan2}(\sqrt{a},\sqrt{1-a}),
\qquad d=Rc
\]

### 21.1. JavaScript

~~~javascript
function degreesToRadians(degrees) {
  return degrees * Math.PI / 180
}

function haversineMeters(pointA, pointB) {
  const [lon1, lat1] = pointA
  const [lon2, lat2] = pointB
  const radius = 6371008.8

  const phi1 = degreesToRadians(lat1)
  const phi2 = degreesToRadians(lat2)
  const deltaPhi = degreesToRadians(lat2 - lat1)

  // Hiệu longitude ngắn nhất trong [-180, 180].
  let deltaLon = lon2 - lon1
  deltaLon = ((deltaLon + 540) % 360) - 180
  const deltaLambda = degreesToRadians(deltaLon)

  const a = Math.sin(deltaPhi / 2) ** 2 +
    Math.cos(phi1) * Math.cos(phi2) *
    Math.sin(deltaLambda / 2) ** 2

  const safeA = Math.max(0, Math.min(1, a))
  const c = 2 * Math.atan2(Math.sqrt(safeA), Math.sqrt(1 - safeA))
  return radius * c
}

print(haversineMeters(
  [106.7000, 10.7800],
  [106.7020, 10.7800]
)) // Khoảng 218 m.

print(haversineMeters(
  [179.8, 0.0],
  [-179.8, 0.0]
)) // Khoảng 44,5 km.
~~~

Haversine hữu ích để đối chiếu hoặc hiển thị khoảng cách, nhưng **không thay thế chỉ mục**: không nên đọc 10 triệu points lên ứng dụng rồi mới tự tính Haversine để lấy top 10. Hãy dùng `2dsphere + $near/$geoNear` để thu hẹp ứng viên.

### 21.2. Khoảng cách đến polygon là bài toán khác

Haversine tính **point-to-point**. Khoảng cách từ điểm tới vùng có thể là 0 khi điểm nằm trong vùng, hoặc khoảng cách ngắn nhất tới **biên** khi ngoài vùng. Nó không bằng khoảng cách tới centroid hay tới đỉnh đầu tiên của polygon.

## 22. Bounding box không thay hình tròn

Một rectangle theo longitude/latitude:

~~~text
lonMin 106.696
lonMax 106.706
latMin 10.777
latMax 10.784
~~~

có thể giúp lọc sơ bộ nhưng các góc rectangle có thể nằm xa tâm hơn bán kính 500 m. Nếu yêu cầu là “nằm trong bán kính”, phải dùng phép distance spherical hoặc circle query phù hợp.

### 22.1. Prefilter rồi kiểm tra chính xác

Một workflow khả dụng:

~~~text
1. Lọc ứng viên bằng index/bounding volume khi thích hợp.
2. Tính spherical distance hoặc containment.
3. Áp business tolerance và uncertainty policy.
4. Trả kết quả với đơn vị rõ ràng.
~~~

Không lấy `longitude ± 0.005` làm một radius cố định toàn cầu. Bên cạnh thay đổi theo vĩ độ, cách này còn bị dateline và các vùng gần cực ảnh hưởng.

## 23. Vùng chồng nhau và lựa chọn một zone

Hai polygon trong lab chồng ở khoảng longitude 106.705–106.706 và latitude 10.781–10.784. Query:

~~~javascript
db.zones.find({
  active: true,
  geometry: {
    $geoIntersects: {
      $geometry: {
        type: "Point",
        coordinates: [106.7055, 10.7830]
      }
    }
  }
})
~~~

có thể trả **nhiều zones**. Điều này không có nghĩa database sai: hình học thực sự chồng. Để chọn zone nghiệp vụ:

- Có `priority` rõ ràng.
- Có thể chọn giá/phí thấp nhất hoặc vùng thuộc đơn vị phụ trách.
- Có chính sách khi priorities bằng nhau.
- Ghi version geometry để giải thích vì sao kết quả thay đổi.

Không dùng `findOne()` rồi mặc định document đầu tiên là đúng. Tương tự, hai polygons chỉ **chạm ở một cạnh** chưa chắc có phần diện tích chồng đáng kể. `$geoIntersects` trả lời có giao, **không trả diện tích overlap**.

## 24. Bài toán geofence với dữ liệu theo thời gian

Một điểm GPS duy nhất chưa mô tả hành trình của xe. Cần phân biệt `capturedAt` (lúc đo), `receivedAt` (lúc server nhận), accuracy và event ID để xử lý packet gửi trễ.

Ví dụ:

~~~javascript
{
  vehicleId: "vehicle-01",
  capturedAt: ISODate("2026-10-01T08:00:00Z"),
  receivedAt: ISODate("2026-10-01T08:00:07Z"),
  accuracyMeters: 18,
  location: {
    type: "Point",
    coordinates: [106.7055, 10.7830]
  }
}
~~~

Nếu điểm 08:00 đến sau điểm 08:01, xử lý tuần tự theo **receivedAt** có thể phát sai ENTER/EXIT. Cần chính sách watermark/out-of-order, và tránh lưu vị trí chính xác quá lâu nếu không có nhu cầu/đồng ý phù hợp.

### 24.1. Geofence không phải bảo vệ chống GPS spoofing

Một thiết bị có thể báo tọa độ giả. Việc MongoDB xác định tọa độ đó nằm trong polygon **không chứng minh thiết bị thực sự ở đó**. Với chấm công, thanh toán hoặc an ninh, phải có chống gian lận và xác thực nguồn bổ sung.

## 25. Java Driver: GeoJSON Point và khoảng cách theo mét

Ví dụ dùng MongoDB Java Sync Driver:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.geojson.Point;
import com.mongodb.client.model.geojson.Position;
import org.bson.Document;
import org.bson.conversions.Bson;

public class NearbyPickupDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> places = client
                .getDatabase("geo_distance_lab")
                .getCollection("pickupPoints");

            // Position(longitude, latitude), không đảo.
            Point center = new Point(new Position(106.7000, 10.7800));

            // GeoJSON + 2dsphere: 500.0 là 500 mét.
            Bson nearby = Filters.near(
                "location", center, 500.0, 0.0
            );
            Bson filter = Filters.and(
                Filters.eq("active", true),
                nearby
            );

            for (Document place : places.find(filter).limit(20)) {
                System.out.println(place.toJson());
            }
        }
    }
}
~~~

Điểm cần nhớ: `Position` nhận **lon trước, lat sau**; `500.0` là **mét** trong cú pháp GeoJSON này; collection cần geospatial index. Với Java Driver khác phiên bản hoặc BSON builders khác, API signature có thể khác nhưng semantics về tọa độ/đơn vị phải giữ nguyên.

## 26. Node.js Driver: lấy khoảng cách bằng `$geoNear`

~~~javascript
import { MongoClient } from "mongodb"

const client = new MongoClient(process.env.MONGODB_URI)
await client.connect()

try {
  const col = client
    .db("geo_distance_lab")
    .collection("pickupPoints")

  const results = await col.aggregate([
    {
      $geoNear: {
        near: {
          type: "Point",
          coordinates: [106.7000, 10.7800]
        },
        key: "location",
        spherical: true,
        distanceField: "distanceMeters",
        maxDistance: 500,
        query: { active: true }
      }
    },
    { $project: { name: 1, distanceMeters: 1 } },
    { $limit: 20 }
  ]).toArray()

  console.log(results)
} finally {
  await client.close()
}
~~~

### 26.1. Validate tọa độ và bán kính

~~~javascript
function validateGeoInput({ longitude, latitude, radiusMeters }) {
  if (!Number.isFinite(longitude) ||
      longitude < -180 || longitude > 180) {
    throw new Error("INVALID_LONGITUDE")
  }
  if (!Number.isFinite(latitude) ||
      latitude < -90 || latitude > 90) {
    throw new Error("INVALID_LATITUDE")
  }
  if (!Number.isFinite(radiusMeters) ||
      radiusMeters < 0 || radiusMeters > 20000) {
    throw new Error("INVALID_RADIUS_METERS")
  }
}
~~~

Số `20000` ở đây chỉ là giới hạn API **minh họa**, không phải giới hạn cố định của MongoDB. Không truyền `NaN`, `Infinity`, string chưa parse hoặc bán kính vô hạn từ client.

### 26.2. API contract

Nên trả:

~~~javascript
{
  placeId: "P-B",
  distanceMeters: 218.4,
  distanceDisplay: "218 m"
}
~~~

Không trả `distance:218.4` mà thiếu đơn vị. `distanceDisplay` chỉ phục vụ UI; điều kiện nghiệp vụ nên so sánh trên số **chưa làm tròn**.

## 27. Sai số làm tròn và ngưỡng cứng

Hai khoảng cách:

~~~text
499,999 m
500,001 m
~~~

đều có thể hiển thị là “500 m”, nhưng nằm ở hai phía khác nhau của ngưỡng. Vì thế:

- Không so sánh **chuỗi đã format**.
- Không làm tròn trước khi xét `distance <= radius`.
- Nếu cần dung sai 1–5 m, ghi rõ đó là **business policy**.
- Với GPS accuracy 20 m, distance tính ra 499 m không chứng minh vị trí thật nằm trong bán kính 500 m.

Tăng số chữ số thập phân của tọa độ **không làm cảm biến chính xác hơn**. Độ chính xác đo được phải được đánh giá từ nguồn và phương pháp.

## 28. Compound geospatial index và bộ lọc business

Nếu gần như mọi query đều chọn `active:true`:

~~~javascript
db.pickupPoints.createIndex(
  {
    active: 1,
    location: "2dsphere"
  },
  { name: "idx_active_location" }
)
~~~

Đây chỉ là một **ứng viên** để đánh giá, không phải luôn tốt hơn index geo đơn. Thứ tự trường, độ chọn lọc, số query không filter active và chi phí ghi/index quyết định. Với compound `2dsphere` index, phải hiểu quy tắc các document có/mất field geometry và kiểu dữ liệu tương ứng.

### 28.1. Xem `explain()`

~~~javascript
db.pickupPoints.explain("executionStats").find({
  active: true,
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      $maxDistance: 1000
    }
  }
}).limit(50)
~~~

Hãy đọc:

- Index nào được sử dụng.
- Stage geospatial như `GEO_NEAR` hay các stage liên quan theo engine/version.
- `nReturned`, `totalKeysExamined`, `totalDocsExamined` khi có.
- Độ trễ p95/p99 với dữ liệu đại diện.
- Tỷ lệ index scan so với kết quả.

Không kết luận hiệu năng production từ **8 documents lab**. Tên stage có thể khác theo phiên bản.

### 28.2. Ranh giới polygon phức tạp

Polygon hàng nghìn đỉnh có thể tốn chi phí giải mã/geometry. Cần xác minh:

- Geometry được validate và nguồn version rõ.
- Có thể đơn giản hóa theo tolerance **không làm sai yêu cầu** không.
- Có thể prefilter theo tenant/metadata/time không.
- Kết quả có quá lớn để trả trong một API call không.

Với ranh giới pháp lý, không tự làm thưa đỉnh tùy ý vì có thể chuyển điểm từ trong sang ngoài.

## 29. Sharded cluster và truy vấn địa lý

Khi collection được shard, `mongos` có thể cần gửi geospatial query tới **nhiều shards** nếu filter không giúp định tuyến theo shard key. `2dsphere` index tối ưu tìm geometry **trên shard**, nhưng không tự tạo shard key hay bảo đảm query chỉ chạm một shard.

- Geospatial index có hạn chế khi dùng làm shard key; không mặc định `{location:"2dsphere"}` là một shard key hợp lệ.
- Nearest top N toàn cluster phải được xác định trên tất cả shards liên quan, không chỉ một shard.
- Khi shard key gắn tenant/region, query phải có filter phù hợp để giảm fan-out nếu có thể.
- Cần đo network/merge overhead khi số shards tăng.

**Zone sharding** quản lý placement của dữ liệu theo shard key; **geofence zone** là polygon nghiệp vụ. Hai khái niệm khác nhau dù cùng từ “zone”.

## 30. Bảo mật và quyền truy cập

Một collection multi-tenant:

~~~javascript
{
  tenantId: "t-01",
  location: {
    type: "Point",
    coordinates: [106.7000, 10.7800]
  }
}
~~~

Geospatial index không giới hạn quyền xem của tenant khác. Một API phải ràng buộc `tenantId` từ **ngữ cảnh xác thực**, không tin body user tự khai báo.

Vị trí chính xác của người dùng có thể là dữ liệu nhạy cảm. Hạn chế lưu/log coordinates khi không cần, quy định retention và phân quyền truy cập; `$geoNear` trả kết quả đúng về hình học nhưng không phải cơ chế authorization.

## 31. Độ mới của vị trí và độ tin cậy sự kiện

Một vị trí đo 20 phút trước có thể không phản ánh xe đang ở đâu. Với vehicle tracking:

~~~javascript
{
  vehicleId: "v-001",
  capturedAt: ISODate("2026-10-01T08:00:00Z"),
  receivedAt: ISODate("2026-10-01T08:00:02Z"),
  location: {
    type: "Point",
    coordinates: [106.7000, 10.7800]
  }
}
~~~

Ứng dụng cần kiểm tra:

- `capturedAt` có đủ mới?
- Event đến trễ hoặc đảo thứ tự không?
- GPS accuracy/confidence?
- Thiết bị có tự thay thế vị trí cũ bằng điểm mới không?
- Business decision có cần nhiều mẫu liên tiếp?

Một `$geoWithin` trả true trên **vị trí cũ** không chứng minh vị trí hiện tại vẫn thuộc vùng.

## 32. Bài thực hành A — nearby trong 500 mét

~~~javascript
db.pickupPoints.find({
  active: true,
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      $maxDistance: 500
    }
  }
}, { name: 1 }).limit(20)
~~~

Hãy giải thích đơn vị `500`, vị trí P-A trong thứ tự gần nhất và cách chuyển bán kính từ 500 m sang 2 km.

## 33. Bài thực hành B — `$centerSphere`

~~~javascript
const radiusMeters = 500

db.pickupPoints.find({
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7000, 10.7800],
        radiusMeters / 6371008.8
      ]
    }
  }
})
~~~

Tại sao không truyền trực tiếp `radiusMeters` vào vị trí bán kính của `$centerSphere`? Query này có tự sắp xếp gần nhất không?

## 34. Bài thực hành C — khoảng cách hiển thị

~~~javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      key: "location",
      distanceField: "distanceMeters",
      spherical: true,
      maxDistance: 1000,
      query: { active: true }
    }
  },
  {
    $project: {
      name: 1,
      distanceMeters: 1,
      distanceKm: { $divide: ["$distanceMeters", 1000] }
    }
  }
])
~~~

Nêu vì sao `distanceKm` được tính ở `$project` và `maxDistance` vẫn là mét. Thử `distanceMultiplier:0.001` như phương án khác để đổi output.

## 35. Bài thực hành D — polygon containment

~~~javascript
const area = {
  type: "Polygon",
  coordinates: [[
    [106.6960, 10.7770],
    [106.7060, 10.7770],
    [106.7060, 10.7840],
    [106.6960, 10.7840],
    [106.6960, 10.7770]
  ]]
}

db.pickupPoints.find({
  location: {
    $geoWithin: {
      $geometry: area
    }
  }
})
~~~

Kiểm tra vòng có khép kín không; so với kết quả vòng tròn 500 m. Thử query với `deliveryAreaWithHole` và giải thích vì sao P-A nằm trong hole có thể bị loại.

## 36. Bài thực hành E — hai zones chồng nhau

~~~javascript
db.zones.find({
  geometry: {
    $geoIntersects: {
      $geometry: {
        type: "Point",
        coordinates: [106.7055, 10.7830]
      }
    }
  }
})
~~~

Giải thích vì sao kết quả có thể là **hai zones**, và vì sao `findOne()` không phải thuật toán chọn vùng nghiệp vụ.

## 37. Bài thực hành F — tuyến đường cắt polygon

Dùng `courierRoute` đã khai báo ở mục 14 với `$geoIntersects`. Nếu cần số mét tuyến đi qua vùng hạn chế, phải bổ sung phép toán gì?

## 38. Bài thực hành G — đường kinh tuyến ±180°

~~~javascript
print(haversineMeters(
  [179.8, 0.0],
  [-179.8, 0.0]
))
~~~

Giải thích vì sao khoảng cách xấp xỉ **44,5 km**, không phải gần một vòng Trái Đất. Mô tả cách chuẩn hóa MultiPolygon/bounding boxes cho vùng qua dateline và các test hai phía ±180°.

## 39. Bài thực hành H — geofence sát biên

~~~text
Query polygon: INSIDE
Ước lượng cách biên: 8 m
GPS reported accuracy: 25 m
~~~

Thiết kế API trả `UNCERTAIN_NEAR_BOUNDARY` và quy tắc lấy thêm mẫu. Vì sao không gửi ENTER ngay sau một phép query trả INSIDE?

## 40. Bài thực hành I — giải thích plan

Chạy `explain("executionStats")` cho truy vấn `$near` của lab. Ghi index, số results, keys/docs examined và các stage thực sự được trả. Không tự bịa latency hoặc kết luận “nhanh gấp N lần” khi dữ liệu chỉ có 8 points.

## 41. Bài thực hành J — chọn phương án đúng

Hãy chọn truy vấn cho từng yêu cầu:

1. Lọc 20 điểm giao nhận gần nhất trong 2 km.
2. Tìm mọi tuyến xe cắt vùng ngập.
3. Kiểm tra một Point có nằm trong vùng giao hàng có hole.
4. Lọc điểm trong vòng tròn 500 m nhưng không cần sắp khoảng cách.
5. Tìm Polygon nào giao với GPS Point hiện tại.
6. Tính thời gian lái xe tới điểm giao hàng.

Phân biệt những tình huống cần MongoDB geospatial query và những tình huống cần GIS clipping/routing engine bên ngoài.

## 42. Gợi ý đáp án

**A:** Với GeoJSON Point và `2dsphere`, `$maxDistance:500` là 500 m. P-A ở tâm nên có khoảng cách 0; bán kính 2 km đặt `2000`.

**B:** Bán kính `$centerSphere` là radian, nên cần `meters/R`. Không bảo đảm sort theo distance.

**C:** `$geoNear` cho `distanceMeters`; phép chia 1000/`distanceMultiplier` tạo km, không thay đổi `maxDistance`.

**D:** Polygon ring đóng vì tọa độ cuối bằng đầu; containment khác circle distance. Hole loại phần nằm trong vòng lỗ của polygon.

**E:** Hai polygons có phần overlap; query có thể trả nhiều rows. Business phải có priority/giá/quy tắc ties, không lấy một record ngẫu nhiên.

**F:** `$geoIntersects` chỉ trả giao/không giao, muốn chiều dài giao phải clip LineString theo polygon rồi đo chiều dài bằng mô hình phù hợp.

**G:** Hai longitude cách nhau 0,4° qua dateline. Phải dùng spherical distance và representation/prefilter được chuẩn hóa đúng.

**H:** Accuracy 25 m lớn hơn distance-to-edge 8 m nên một điểm INSIDE chưa đủ chắc. Cần uncertainty/hysteresis policy.

**I:** Dùng kết quả `explain` thật, không suy luận từ tên index hoặc dataset quá nhỏ.

**J:** (1) `$geoNear` hoặc `$near`, (2) `$geoIntersects`, (3) `$geoWithin` cho point collection hoặc `$geoIntersects` cho polygon collection, (4) `$geoWithin+$centerSphere`, (5) `$geoIntersects`, (6) routing engine sau bước chọn ứng viên.

## 43. Những sai lầm phổ biến

| Sai lầm | Vì sao sai? | Cách làm đúng |
|---|---|---|
| Đảo `[lat,lon]` | GeoJSON nhận lon trước | Validate và chuẩn hóa input |
| Dùng độ như mét | Độ longitude đổi theo latitude | Spherical calculation và đơn vị rõ |
| Dùng 500 cho bán kính `$centerSphere` | Toán tử nhận **radian** | `500 / R` |
| Tự đổi 500 m thành radian cho `$near` GeoJSON | `$maxDistance` ở đây nhận **mét** | Dùng `500` trực tiếp |
| Đổi legacy query nhưng giữ số maxDistance | Legacy units có thể khác | Migrate cả geometry + index + units |
| Dùng `2d` cho GPS toàn cầu | Phép khoảng cách phẳng không đúng | `2dsphere` |
| Lấy `$near` làm đường lái xe | Không xét network/đường cấm | Routing engine |
| Lấy centroid để kiểm tra inside polygon | Vùng có góc, lỗ, lõm | `$geoWithin`/`$geoIntersects` |
| Dùng `$geoWithin` rồi tin kết quả gần nhất | Không có distance sort mặc định | `$near`/`$geoNear` |
| Đặt `$geoNear` sau `$match` | Stage phải đứng đầu | Đưa filter vào `query` |
| Lấy vòng thứ hai làm polygon cộng | Ring sau có thể là hole | MultiPolygon cho vùng rời |
| Ring thiếu điểm đóng | Polygon invalid | Đóng ring, validate |
| Polygon tự cắt | Hình học mơ hồ | GIS repair/validation |
| Tin điểm đúng biên luôn inside | Boundary semantics và sai số phức tạp | Policy + edge tests |
| Kết luận bằng một mẫu GPS sát biên | GPS uncertainty | Buffer/hysteresis/state machine |
| Dùng hộp longitude thường qua dateline | ±180° gây wrap | Split/normalize/GeoJSON hợp lệ |
| Cho rằng nearest luôn chỉ một shard | Query có thể scatter | Đo routing/shards touched |
| Chỉ dựa vào geospatial filter để phân quyền | Index không xác thực tenant | Auth + tenant filter |
| Log tọa độ người dùng tràn lan | Rủi ro privacy | Minimization/retention/auth |

## 44. Câu hỏi ôn tập

**1. GeoJSON Point lưu thứ tự gì?** — Longitude trước, latitude sau; đơn vị tọa độ là **độ**.

**2. `$near` với GeoJSON Point trên `2dsphere` dùng đơn vị khoảng cách nào?** — **Mét**.

**3. `$centerSphere` dùng bán kính nào?** — **Radian**; đổi `meters/R` với R tính bằng mét.

**4. Bán kính 1 km xấp xỉ bao nhiêu radian?** — `1000/6371008.8 ≈ 0.000157`.

**5. Khi nào dùng `$geoNear`?** — Khi muốn kết hợp truy vấn nearest với field khoảng cách và các stage aggregation.

**6. `distanceMultiplier:0.001` có đổi ý nghĩa `maxDistance` không?** — Không, nó chỉ đổi output distance theo quy tắc.

**7. `$geoWithin` và `$geoIntersects` khác nhau?** — Một bên hỏi containment, bên kia hỏi có giao hình học.

**8. Polygon hole là gì?** — Một vùng bên trong vòng ngoài **bị loại khỏi phần phủ**.

**9. MultiPolygon dùng khi nào?** — Khi vùng có nhiều phần rời nhau.

**10. Có thể coi điểm trên biên là inside mọi lúc không?** — Không nên. Cần quy tắc nghiệp vụ, kiểm thử geometry và xử lý uncertainty.

**11. GPS accuracy 25 m, điểm 8 m trong biên có chắc inside không?** — Không; khoảng bất định cắt qua biên.

**12. Vì sao longitude +179,8 và -179,8 gần nhau?** — Chúng nằm hai phía kinh tuyến đổi ngày, cách 0,4° theo hướng ngắn.

**13. Gần cực dùng khoảng longitude ×111 km được không?** — Không, kinh tuyến hội tụ nên xấp xỉ đó sai.

**14. `2d` và `2dsphere` khác nhau ở đâu?** — Phẳng so với spherical; GeoJSON GPS thường cần `2dsphere`.

**15. Haversine có thay geo index không?** — Không. Nó phù hợp tính khoảng cách trên tập nhỏ; index giúp tránh đọc mọi documents.

**16. `$geoIntersects` có tính diện tích overlap không?** — Không, nó trả kết quả giao nhau.

**17. Near 500 m có đồng nghĩa đường đi 500 m không?** — Không; mạng đường/ETA là bài toán routing khác.

**18. Hai zones cùng chứa điểm là lỗi database?** — Không, zones có thể chồng hình học. Business cần quy tắc ưu tiên.

**19. Geospatial query đúng có chứng minh xe đang ở đó không?** — Không; vị trí có thể cũ, sai số lớn hoặc bị spoof.

**20. Điều gì cần kiểm tra trước khi giao hàng theo vùng pháp lý?** — Geometry nguồn, CRS/version, boundary policy, độ chính xác vị trí và test edge cases.

## 45. Bảng ghi nhớ nhanh

| Yêu cầu | Công cụ |
|---|---|
| GeoJSON WGS84 | `{type:"Point",coordinates:[lon,lat]}` |
| Chỉ mục địa lý GPS | `createIndex({location:"2dsphere"})` |
| Nearest trong 500 m | `$near:{$geometry:point,$maxDistance:500}` |
| Spherical nearest | `$nearSphere` với GeoJSON |
| Lấy distance field | `$geoNear` |
| Đổi m sang km trong `$geoNear` | `distanceMultiplier:0.001` |
| Điểm trong circle 500 m | `$geoWithin:{$centerSphere:[[lon,lat],500/R]}` |
| Điểm trong Polygon | `$geoWithin:{$geometry:polygon}` |
| Polygon giao Point/Line | `$geoIntersects:{$geometry:...}` |
| Polygon có hole | `coordinates:[outerRing,holeRing]` |
| Vùng tách rời | `MultiPolygon` |
| Khoảng cách tham khảo | Haversine/hệ GIS |
| Vị trí qua dateline | Normalize longitude, geometry phù hợp |
| Geofence sát biên | Accuracy + tolerance + hysteresis |
| Kiểm tra query plan | `explain("executionStats")` |

## 46. Checklist trước khi triển khai production

- [ ] Tọa độ đã chuẩn WGS84 với **[longitude,latitude]**?
- [ ] Có validate miền tọa độ, kiểu số, `NaN`/`Infinity`?
- [ ] API gọi tên rõ `radiusMeters`/`distanceMeters`?
- [ ] Có phân biệt mét và radian đúng theo từng operator?
- [ ] `2dsphere` index đã tồn tại trên field GeoJSON cần dùng?
- [ ] Nếu migrate legacy data, đã kiểm tra lại đơn vị khoảng cách?
- [ ] Đã xác định business cần proximity, containment hay intersection?
- [ ] `$geoNear` đứng đầu pipeline và chỉ rõ `key` nếu có nhiều geo indexes?
- [ ] Có validate radius tối đa, limit, query timeout và tenant filter?
- [ ] Polygon rings khép kín, không tự cắt và holes hợp lệ?
- [ ] Đã test edge, vertex, hole, MultiPolygon và overlap?
- [ ] Đã xác định policy inclusive/exclusive/uncertain cho boundary?
- [ ] Có xử lý GPS accuracy, capturedAt, out-of-order và hysteresis?
- [ ] Có test dateline/near-pole nếu phạm vi toàn cầu?
- [ ] Geometry pháp lý có nguồn và version rõ ràng?
- [ ] Không dùng spherical distance làm route distance hoặc ETA?
- [ ] Đã đo explain, p95/p99 latency, keys/docs examined trên dữ liệu đại diện?
- [ ] Nếu sharded, đã kiểm tra số shards touched và global nearest ordering?
- [ ] Có phân quyền tenant và bảo vệ dữ liệu vị trí người dùng?
- [ ] Có bộ golden fixtures địa lý để test khi cập nhật index/driver/geometry?

## 47. Kết luận

Với MongoDB geospatial, **đơn vị đo và phép toán được lựa chọn phải khớp yêu cầu nghiệp vụ**. GeoJSON dùng **kinh độ/vĩ độ theo độ**; `$near`/`$geoNear` với GeoJSON Point và `2dsphere` thường dùng khoảng cách **mét**, trong khi bán kính của `$centerSphere` là **radian**. Nhầm lẫn những đơn vị này sẽ làm truy vấn trả vùng sai, dù câu lệnh có thể vẫn chạy.

Khoảng cách chỉ là một phần: **`$geoWithin`** giải quyết thuộc vùng, **`$geoIntersects`** giải quyết giao nhau. Polygon có holes, các zones chồng nhau, các điểm trên biên, dateline ±180° và GPS uncertainty đòi hỏi validation và chính sách rõ ràng. Một phép query hình học không thể thay thuật toán tìm đường đi, đo đạc pháp lý hay mô hình độ tin cậy thiết bị.

Trong production, hãy dùng **`2dsphere` index**, giới hạn bán kính/result, đọc `explain()`, xử lý đúng đơn vị và chuẩn hóa GeoJSON. Đối với geofencing, nên kết hợp kết quả hình học với **accuracy, khoảng thời gian, trạng thái ổn định và bộ test ranh giới**. Chỉ khi đó kết quả “gần”, “trong vùng” hay “đã ra khỏi vùng” mới có ý nghĩa nhất quán cho ứng dụng.
