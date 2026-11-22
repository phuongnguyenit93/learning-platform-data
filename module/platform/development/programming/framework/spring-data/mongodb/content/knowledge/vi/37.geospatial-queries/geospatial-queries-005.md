# Khoảng cách, đơn vị đo và hệ số chuyển đổi

## 1. Tại sao truy vấn đúng cú pháp vẫn trả sai bán kính?

Một API tìm điểm lấy hàng nhận yêu cầu: **“Tìm các điểm trong vòng 2 km từ vị trí hiện tại, trả về khoảng cách theo km.”** Người phát triển viết lệnh `$geoNear` với `maxDistance: 2` vì request gửi `radiusKm=2`. Lệnh chạy thành công, nhưng với **GeoJSON Point**, MongoDB hiểu `maxDistance: 2` là **2 mét**, không phải 2 km. Chỉ có những điểm gần như trùng tọa độ mới xuất hiện.

Một hệ thống cũ lưu tọa độ thành cặp `[longitude, latitude]` rồi gọi tìm kiếm cầu; giá trị `0.002` trong câu truy vấn khác lại có thể là **0,002 radian**, tương ứng khoảng 12,76 km nếu dùng bán kính Trái Đất 6.378,137 km. Nếu lập trình viên nhìn thấy «0.002» và diễn giải là 2 m, kết quả có thể rộng hơn hàng nghìn lần.

Sự cố nằm ở **hợp đồng đơn vị**, không nhất thiết ở index hoặc MongoDB driver:

- Input API có thể dùng **kilômét** hoặc **mét**.
- Tọa độ WGS84 là **kinh độ/vĩ độ theo độ góc**, không phải mét.
- Một số toán tử truy vấn GeoJSON dùng **mét**, một số toán tử cũ dùng **radian**.
- Kết quả khoảng cách có thể là **mét**, **radian**, hoặc đã nhân **distanceMultiplier**.
- Spring Data `Distance` và `Metrics` mang ý nghĩa đơn vị riêng, **không được đoán từ giá trị số**.

Bài thuộc chương **Truy vấn không gian** trong module **SPRING_DATA_MONGODB**. Phạm vi module là sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác qua `MongoTemplate` hoặc repository; thực hành thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.

Sau bài này, bạn có thể:

1. Phân biệt **độ (°)**, **radian (rad)**, **mét (m)**, **kilômét (km)** và **dặm (mi)**.
2. Chọn đúng đơn vị cho `$near`, `$nearSphere`, `$geoNear` và `$centerSphere`.
3. Hiểu vì sao định dạng **GeoJSON Point** khác **legacy coordinate pair** cả về dữ liệu lẫn khoảng cách.
4. Áp dụng `distanceMultiplier` để đổi **kết quả trả về**, không nhầm với bộ lọc `maxDistance`.
5. Sử dụng `Point`, `GeoJsonPoint`, `Distance`, `Metrics` và `NearQuery` trong Spring Data MongoDB.
6. Thiết kế DTO có đơn vị tường minh, kiểm tra giá trị input và bảo vệ API khỏi lỗi đổi đơn vị.
7. Tối ưu bằng index `2dsphere`/`2d`, giới hạn kết quả và test các điểm ở biên bán kính.

> **Định hướng:** Các ví dụ Java giả định Java 17+, một phiên bản Spring Data MongoDB tương thích với Spring Boot của dự án, MongoDB server hỗ trợ geospatial operators đang dùng và dữ liệu test cô lập. Cú pháp/behavior chi tiết có thể phụ thuộc server/driver/Spring Data version. Với triển khai thật, kiểm tra BSON/pipeline được tạo và đơn vị của giá trị trả về.

## 2. Mô hình đơn vị: một bảng để đọc mọi ví dụ

| Đại lượng | Ký hiệu | Ví dụ | Ý nghĩa |
| --- | --- | --- | --- |
| Kinh độ | ° longitude | `106.70` | Góc theo chiều Đông–Tây |
| Vĩ độ | ° latitude | `10.78` | Góc theo chiều Bắc–Nam |
| Góc ở tâm | radian | `0.00031357` | Góc giữa hai bán kính của hình cầu |
| Khoảng cách đường chim bay | mét | `2_000 m` | Độ dài cung trên mô hình cầu |
| Khoảng cách đường chim bay | kilômét | `2 km` | `2_000 m` |
| Khoảng cách đường chim bay | mile | `1 mi` | `1_609.344 m` |
| Khoảng cách tuyến đường | phút/km thực tế | Không suy từ `$geoNear` | Phải dùng dữ liệu mạng đường/giao thông khác |
| Hệ số trả kết quả | Không đơn vị (tỉ lệ) | `0.001` | Nhân mét để ra km |

Các phép tính dưới đây dùng **bán kính quy ước R = 6.378.137 mét** (6.378,137 km, gần bán kính xích đạo WGS84), nhất quán với ví dụ Spring Data về chuyển đổi radian sang kilômét. Đây là **hệ số quy ước cho ví dụ**, không phải bảo đảm rằng mọi hệ geospatial đều dùng chính xác cùng mô hình Trái Đất.

### 2.1. Ba nhóm đại lượng không được cộng hoặc so trực tiếp

```text
GeoJSON coordinates = [longitudeDegrees, latitudeDegrees]
maxDistance        = distance in meters (với truy vấn GeoJSON)
legacy spherical   = central angle in radians

Ví dụ:
  [106.70, 10.78] = một vị trí theo độ góc
  2_000           = 2.000 mét
  0.00031357      = khoảng 2 km tính bằng radian trên R đã chọn
```

Không lấy `Point.x` trừ `Point.y` để tính số mét. Chênh lệch kinh/vĩ độ theo độ không có một hệ số đổi ra mét cố định trên mọi vĩ độ.

### 2.2. GeoJSON Point và thứ tự tọa độ

```javascript
{
  type: "Point",
  coordinates: [106.70, 10.78]
}
```

Theo quy tắc GeoJSON/MongoDB, tọa độ địa lý viết **[longitude, latitude]**. Không phải `[latitude, longitude]` như một số API bản đồ/điện thoại trả về.

- Kinh độ longitude nằm trong `[-180, 180]`.
- Vĩ độ latitude nằm trong `[-90, 90]`.
- Các giá trị đầu vào ở đây là **độ**, không phải radian.
- GeoJSON Point trên Earth dùng WGS84 longitude/latitude; không nhét mét hoặc tọa độ UTM vào `coordinates` mà không chuyển hệ phù hợp.

### 2.3. Tránh ví dụ phụ thuộc địa danh thật

Các điểm trong bài tên **“Kho A”, “Điểm B”, “Điểm C”** đều là fixtures giả định có tọa độ số gần khu vực nhiệt đới; không đại diện cho một địa điểm kinh doanh thật và không dùng để suy ra khoảng cách đường bộ hoặc thời gian giao hàng.

## 3. Công thức đổi mét, kilômét, dặm và radian

Với một mô hình cầu có bán kính `R`:

\[
d_{\mathrm{m}} = \theta_{\mathrm{rad}}\times R_{\mathrm{m}}
\]

\[
\theta_{\mathrm{rad}} = \frac{d_{\mathrm{m}}}{R_{\mathrm{m}}}
\]

\[
d_{\mathrm{km}} = \frac{d_{\mathrm{m}}}{1000},\qquad
d_{\mathrm{mi}} = \frac{d_{\mathrm{m}}}{1609.344}
\]

Hệ số dùng trong bài:

```text
R_METERS      = 6_378_137.0
R_KILOMETERS  = 6_378.137
METERS_PER_KM = 1_000.0
METERS_PER_MI = 1_609.344
```

### 3.1. Ví dụ 2 km chuyển sang radian

```text
2 km = 2_000 m
2_000 / 6_378_137 ≈ 0.000313571 rad
```

Giá trị này hữu ích cho một truy vấn legacy spherical hoặc `$centerSphere`, **không** nên đưa làm `maxDistance` cho GeoJSON `$near`.

### 3.2. Ví dụ 0,001 radian chuyển thành km

```text
0.001 rad × 6_378.137 km/rad = 6.378137 km
```

Ngược lại, «1 radian» không có nghĩa «1 km». Radian là góc; nhân bán kính theo đơn vị khoảng cách mới ra độ dài cung.

### 3.3. Ví dụ 5 miles chuyển thành mét

```text
5 miles × 1_609.344 m/mile = 8_046.72 m
```

Với GeoJSON `$nearSphere`, nếu API nhận 5 miles thì gửi `$maxDistance: 8046.72`.

### 3.4. Đổi độ sang radian

\[
\theta_{\mathrm{rad}} = \theta_{\mathrm{deg}}\times\frac{\pi}{180}
\]

**Nhưng đừng áp công thức này trực tiếp lên kinh độ/vĩ độ rồi đưa vào GeoJSON.** GeoJSON vẫn cần độ góc. Công thức độ–radian hữu ích cho tính toán hình học (ví dụ Haversine) hoặc các toán tử yêu cầu **góc bán kính**, không phải để thay đổi định dạng GeoJSON.

## 4. Bảng đơn vị theo từng toán tử MongoDB

| Toán tử/đường query | Query point | Đơn vị bán kính/giới hạn | Đơn vị khoảng cách trả về | Index chính |
| --- | --- | --- | --- | --- |
| `$near` | GeoJSON `Point` | **Mét** | Chỉ tìm/sort, không tự thêm distance field | `2dsphere` |
| `$nearSphere` | GeoJSON `Point` | **Mét** | Không tự thêm distance field | `2dsphere` |
| `$geoNear` | GeoJSON `Point` | **Mét** | Thường **mét** trước multiplier | `2dsphere` |
| `$nearSphere` | Legacy `[lon,lat]` trên đường cầu | **Radian** | Không tự thêm distance field | `2d` hoặc `2dsphere` phù hợp |
| `$geoNear` | Legacy `[lon,lat]` với spherical | **Radian** | **Radian** trước multiplier | Index geospatial phù hợp |
| `$near` | Legacy `[x,y]` với `2d` | Tùy semantics/toán tử legacy (mặt phẳng) | Không tự thêm distance field | `2d` |
| `$geoWithin: {$centerSphere: ...}` | Center legacy `[lon,lat]` | **Radian** ở phần tử radius | Không tính distance output | `2dsphere` hoặc geospatial index phù hợp |
| `$geoWithin: {$center: ...}` | Legacy planar center | Đơn vị hệ tọa độ phẳng | Không tính distance output | `2d` |

**Một bẫy quan trọng:** Cùng lưu GeoJSON trong collection không tự khiến mọi dạng **query point** dùng mét. Trong `$geoNear`, dạng `near` (GeoJSON object hay legacy pair) và semantics spherical mới quyết định đơn vị của giới hạn/kết quả. Đừng chỉ nhìn field `location` trong một document rồi kết luận đơn vị.

### 4.1. Chọn chuẩn nội bộ càng đơn giản càng tốt

Đối với ứng dụng kinh doanh dùng kinh/vĩ độ, lựa chọn an toàn thường là:

1. Lưu **GeoJSON Point** theo chuẩn `[longitude, latitude]`.
2. Đặt index **2dsphere**.
3. Chuẩn hóa khoảng cách đầu vào thành **mét** trước khi gửi raw MongoDB query.
4. Đọc kết quả `$geoNear` bằng **mét** khi không có multiplier.
5. Đổi ra km/miles **một lần tại API boundary** hoặc dùng multiplier có kiểm soát.

Không bắt buộc tất cả API bên ngoài phải gửi mét; chỉ cần adapter đổi tường minh và test đúng.

## 5. Chuẩn bị collection GeoJSON và 2dsphere index

Các fixture sau chỉ chạy trên **database test cô lập**:

```javascript
use geo_training;

db.pickup_points.insertMany([
  {
    _id: "p-a",
    tenantId: "tenant-a",
    name: "Kho A",
    active: true,
    location: {
      type: "Point",
      coordinates: [106.7000, 10.7800]
    }
  },
  {
    _id: "p-b",
    tenantId: "tenant-a",
    name: "Điểm B",
    active: true,
    location: {
      type: "Point",
      coordinates: [106.7100, 10.7800]
    }
  },
  {
    _id: "p-c",
    tenantId: "tenant-a",
    name: "Điểm C",
    active: false,
    location: {
      type: "Point",
      coordinates: [106.7400, 10.8000]
    }
  },
  {
    _id: "p-foreign",
    tenantId: "tenant-b",
    name: "Điểm khác tenant",
    active: true,
    location: {
      type: "Point",
      coordinates: [106.7001, 10.7801]
    }
  }
]);

db.pickup_points.createIndex(
  { location: "2dsphere" },
  { name: "ix_pickup_location_2dsphere" }
);
```

Các kinh/vĩ độ này là dữ liệu giả lập. Trước khi tạo index trên collection có dữ liệu legacy, cần kiểm tra field geometry sai định dạng, `null`, thiếu field, coordinate order và version index.

### 5.1. Vì sao không dùng 2d index cho GeoJSON?

`2dsphere` dùng để hỗ trợ truy vấn hình học cầu và GeoJSON. `2d` hướng tới cặp tọa độ legacy và hình học phẳng. Nếu mục tiêu là “các điểm trong bán kính 2 km trên bề mặt Trái Đất”, đừng chọn `2d` rồi ngầm coi mỗi đơn vị x/y là một mét.

### 5.2. Tránh nhầm index theo field

```javascript
// Đúng cho GeoJSON Point:
db.pickup_points.createIndex({ location: "2dsphere" });

// Không thay thế tùy tiện bằng:
// db.pickup_points.createIndex({ "location.coordinates": "2d" });
```

Index vào `location.coordinates` theo `2d` thay đổi semantics và không tương đương việc index GeoJSON geometry object. Với nhiều geospatial fields/indexes, truy vấn `$geoNear` nên chỉ định `key` rõ ràng.

### 5.3. Không tạo index trong request handler

Tạo/quản lý index qua migration, provisioning hoặc quy trình vận hành; kiểm tra index tồn tại trước khi chạy geo query. Spring Data `@GeoSpatialIndexed` có thể hỗ trợ định nghĩa index metadata, nhưng index auto-creation tùy config/framework version và không thay thế quy trình quản lý production.

## 6. Truy vấn $near với GeoJSON: bán kính tính bằng mét

Tìm những điểm trong **2 km** quanh [106.7000, 10.7800]:

```javascript
db.pickup_points.find({
  tenantId: "tenant-a",
  active: true,
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      $minDistance: 0,
      $maxDistance: 2000
    }
  }
});
```

Ở đây `2000` là **mét**. `$near` thực hiện geospatial proximity query, kết quả gần tới xa theo semantics của toán tử; một lần `find` thông thường **không thêm field khoảng cách** để client đọc. Nếu API cần hiển thị số km chính xác, hãy dùng `$geoNear` hoặc tính khoảng cách ngoài database có định nghĩa nhất quán.

### 6.1. Nếu chỉ muốn trong 500 mét

```javascript
$maxDistance: 500
```

### 6.2. Nếu request nhận radiusKm = 2

```javascript
const radiusKm = 2;
const radiusMeters = radiusKm * 1000;
// Dùng radiusMeters làm $maxDistance của GeoJSON query.
```

### 6.3. Nếu bán kính đến từ miles

```javascript
const radiusMiles = 3;
const radiusMeters = radiusMiles * 1609.344;
// 4828.032 mét.
```

### 6.4. Không biến $near thành phép đo khoảng cách đường bộ

Khoảng cách geospatial theo hình học cầu không biết đường cấm, sông, cầu, cầu vượt, tắc đường hoặc routing restrictions. Dùng nó để **lọc ứng viên** và tính xấp xỉ khoảng cách đường chim bay; nếu hợp đồng cần ETA hoặc số km lái xe, phải tích hợp nguồn dữ liệu định tuyến phù hợp.

## 7. $nearSphere với GeoJSON: cũng là mét

```javascript
db.pickup_points.find({
  location: {
    $nearSphere: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      $maxDistance: 2000
    }
  }
});
```

Với **GeoJSON Point**, `$maxDistance` của `$nearSphere` cũng là mét. Đừng suy rằng tên `Sphere` có nghĩa phải truyền radian trong mọi trường hợp.

### 7.1. $near và $nearSphere chọn theo ngữ cảnh

Trong MongoDB geospatial:

- `$near` với GeoJSON sử dụng semantics spherical thích hợp với `2dsphere`.
- `$nearSphere` nhấn mạnh spherical geometry và cũng hỗ trợ legacy coordinate pairs theo quy tắc khác.
- Lựa chọn phải căn cứ **geometry representation và index**, không chỉ tên toán tử.

### 7.2. minDistance phải cùng đơn vị

Để tìm **vòng vành khăn từ 500 m đến 2.000 m**, dùng:

```javascript
db.pickup_points.find({
  location: {
    $nearSphere: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      $minDistance: 500,
      $maxDistance: 2000
    }
  }
});
```

Đừng để `$minDistance` là kilômét và `$maxDistance` là mét trong cùng query.

## 8. $geoNear: tính khoảng cách và gắn đơn vị trả về

Khi API cần **cả điểm gần nhất lẫn số mét/km** cho mỗi kết quả, `$geoNear` trong aggregation pipeline phù hợp hơn một query `$near` đơn giản.

### 8.1. Trả khoảng cách theo mét (mặc định với GeoJSON)

```javascript
db.pickup_points.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      key: "location",
      spherical: true,
      minDistance: 0,
      maxDistance: 2000,
      distanceField: "distanceMeters",
      query: {
        tenantId: "tenant-a",
        active: true
      }
    }
  },
  { $limit: 20 },
  {
    $project: {
      _id: 1,
      name: 1,
      location: 1,
      distanceMeters: 1
    }
  }
]);
```

Ở đây:

- `near` là **GeoJSON Point**.
- `maxDistance: 2000` là **2.000 mét**.
- Không có `distanceMultiplier` → `distanceMeters` là khoảng cách **theo mét** trong trường hợp này.
- `query` thêm điều kiện tenant/active trong chính `$geoNear`.
- `key` chỉ định field có index `2dsphere`.
- `$limit: 20` giới hạn số bản ghi trả về; `$geoNear` không mặc định giới hạn 100 kết quả trong các MongoDB version hiện hành.

### 8.2. $geoNear phải ở đầu pipeline

```javascript
// Không hợp lệ theo quy tắc chung của $geoNear:
db.pickup_points.aggregate([
  { $match: { tenantId: "tenant-a" } },
  { $geoNear: { /* ... */ } }
]);
```

`$geoNear` cần ở **stage đầu tiên** trong pipeline, có một số chi tiết riêng đối với time-series và phiên bản. Đặt predicate tenant/active vào `query` của stage khi API hỗ trợ. Không đẩy `$match` lên trước chỉ vì muốn lọc sớm.

### 8.3. Nhiều geospatial indexes cần key

Nếu collection có `location` và `backupLocation` cùng index `2dsphere`, server có thể không biết chọn index nào cho `$geoNear`. Đặt:

```javascript
key: "location"
```

để xác định field. Không suy rằng index theo thứ tự tên sẽ được dùng đúng.

### 8.4. distanceField không tự nói đơn vị

Tên field `"distanceMeters"` chỉ là lựa chọn đặt tên của chúng ta. MongoDB không kiểm tra tên và đơn vị tương ứng. Nếu thêm `distanceMultiplier: 0.001` nhưng vẫn đặt tên field `distanceMeters`, API có thể âm thầm nói dối consumer.

## 9. distanceMultiplier: nhân kết quả, không đổi bán kính lọc

`distanceMultiplier` của `$geoNear` **nhân các khoảng cách trả về** sau tính toán. Nó **không có tác dụng chuyển `maxDistance` từ km sang mét**.

### 9.1. GeoJSON: trả đơn vị kilômét

```javascript
db.pickup_points.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      key: "location",
      spherical: true,
      maxDistance: 2000,           // vẫn là MET
      distanceMultiplier: 0.001,   // m -> km cho OUTPUT
      distanceField: "distanceKm",
      query: {
        tenantId: "tenant-a",
        active: true
      }
    }
  },
  { $limit: 20 }
]);
```

Ví dụ một điểm có khoảng cách thô 1.250 m:

```text
distanceKm = 1_250 × 0.001 = 1.25 km

Điều kiện lọc vẫn là:
  raw distance <= 2_000 meters
```

### 9.2. GeoJSON: trả đơn vị miles

```javascript
distanceMultiplier: 1 / 1609.344
```

Một điểm cách 1.609,344 m được hiển thị là khoảng 1 mile. Đơn vị của `maxDistance` vẫn là **mét**, ví dụ `maxDistance: 4828.032` cho 3 miles.

### 9.3. Bảng hệ số với output GeoJSON

| Đơn vị raw result | Muốn output | Hệ số `distanceMultiplier` | Ví dụ |
| --- | --- | --- | --- |
| mét | mét | `1` (hoặc bỏ property) | 500 m → 500 |
| mét | kilômét | `0.001` | 500 m → 0.5 km |
| mét | miles | `1 / 1609.344` | 1609.344 m → 1 mi |

### 9.4. Không dùng 6378.137 cho output GeoJSON nếu muốn km

```javascript
// SAI với GeoJSON raw distance là mét:
distanceMultiplier: 6378.137
```

Hệ số 6378.137 (km/rad) dành cho **raw result là radian** trong một truy vấn spherical dùng legacy coordinate pair. Dùng nó với GeoJSON raw distance là mét sẽ phóng đại khoảng cách khoảng 6,378,137 lần so với giá trị km đúng.

### 9.5. Đừng chuyển đổi hai lần

Nếu pipeline trả `distanceKm` nhờ `distanceMultiplier: 0.001`, service **không được chia tiếp cho 1000**. Một hợp đồng API nên chọn:

- Trả raw `distanceMeters` từ MongoDB rồi chuyển sang km ở Java, **hoặc**
- Dùng `distanceMultiplier` trong MongoDB và trả `distanceKm` trực tiếp.

Không thực hiện cả hai phép chuyển đổi cho cùng một kết quả.

## 10. Dạng legacy coordinate pair và khoảng cách radian

Legacy point có cú pháp:

```javascript
[106.7000, 10.7800]
```

Đây vẫn là **tọa độ longitude/latitude theo độ**, **không phải** một cặp radian. Nhưng trong một truy vấn cầu legacy, **tham số khoảng cách** và khoảng cách tính có thể là radian.

### 10.1. Dữ liệu legacy minh họa

```javascript
db.legacy_pickup_points.insertMany([
  { _id: "l-a", tenantId: "tenant-a", loc: [106.7000, 10.7800] },
  { _id: "l-b", tenantId: "tenant-a", loc: [106.7100, 10.7800] }
]);

db.legacy_pickup_points.createIndex(
  { loc: "2dsphere" },
  { name: "ix_legacy_loc_2dsphere" }
);
```

Index `2dsphere` có thể làm việc với legacy coordinate pairs trong trường hợp phù hợp. Khi dùng một toán tử cụ thể, vẫn phải kiểm tra yêu cầu format/index của chính nó.

### 10.2. $nearSphere legacy: 2 km phải chuyển sang radian

```javascript
const earthRadiusMeters = 6378137.0;
const twoKmRadians = 2000.0 / earthRadiusMeters;

db.legacy_pickup_points.find({
  loc: {
    $nearSphere: [106.7000, 10.7800],
    $maxDistance: twoKmRadians
  }
});
```

Đây là điểm khác biệt lớn với `$nearSphere` sử dụng GeoJSON `$geometry`:

```text
GeoJSON nearSphere:
  $maxDistance = 2000 METERS

Legacy spherical nearSphere:
  $maxDistance = 2000 / R_METERS RADIANS
```

### 10.3. Legacy $geoNear trả khoảng cách theo km

```javascript
db.legacy_pickup_points.aggregate([
  {
    $geoNear: {
      near: [106.7000, 10.7800],
      key: "loc",
      spherical: true,
      maxDistance: 2000.0 / 6378137.0,
      distanceMultiplier: 6378.137,
      distanceField: "distanceKm",
      query: { tenantId: "tenant-a" }
    }
  },
  { $limit: 20 }
]);
```

Trong ví dụ này:

- Raw distance của truy vấn cầu legacy là **radian**.
- `maxDistance` được truyền **radian**.
- Nhân `distanceMultiplier: 6378.137` để output thành **km**.

Nếu muốn output theo mét thay vì km, dùng `distanceMultiplier: 6378137.0`. Phép đổi về mặt số học dựa trên một bán kính quy ước; không tự cho rằng phép tính hình học của các hệ hay các phiên bản luôn cho kết quả bitwise identical.

### 10.4. Dữ liệu lưu và hình dạng near query là hai chuyện

Một field MongoDB có thể lưu GeoJSON nhưng `$geoNear` vẫn chấp nhận query near input dạng legacy coordinate pair nếu dùng index phù hợp. Trong trường hợp đó, **dạng query near** ảnh hưởng đơn vị của giới hạn/kết quả. Đây là lý do kiểm tra **pipeline BSON** quan trọng hơn chỉ nhìn Java entity field type.

## 11. $centerSphere: luôn yêu cầu radius theo radian

Một truy vấn `$geoWithin` với `$centerSphere` trông giống tìm điểm trong vòng tròn:

```javascript
db.pickup_points.find({
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7000, 10.7800],
        2000.0 / 6378137.0
      ]
    }
  }
});
```

Với `$centerSphere`, phần tử radius của biểu thức **là radian**, kể cả collection lưu GeoJSON Point và đang dùng `2dsphere` index.

### 11.1. $centerSphere không trả khoảng cách tính sẵn

`$geoWithin` kiểm tra membership trong vùng; nó **không tự sắp xếp theo gần xa** và **không tự thêm distance field**. Nếu API muốn hiển thị km theo từng điểm, cần tính tiếp trong ứng dụng hoặc dùng `$geoNear`.

### 11.2. So sánh với $near

| Mục tiêu | Toán tử |
| --- | --- |
| Lấy điểm trong bán kính và tự xếp gần nhất | `$near`/`$nearSphere` |
| Lấy điểm + trường khoảng cách để hiển thị | `$geoNear` |
| Chỉ lọc những điểm thuộc vùng tròn | `$geoWithin + $centerSphere` |
| Vùng polygon/geometry phức tạp | `$geoWithin + $geometry` với semantics phù hợp |

### 11.3. Tối ưu khác nhau

`$near` và `$geoNear` thường đòi index geospatial tương ứng. `$centerSphere` có thể được đánh giá cả không index ở một số đường, nhưng index giúp tăng hiệu năng trên collection lớn. Dùng `explain` để kiểm tra, đừng giả định mọi geospatial query dùng cùng plan.

## 12. Hệ số quy đổi không phải hệ tọa độ

Một `distanceMultiplier` chỉ nhân **kết quả tính độ dài/góc**, không biến tọa độ GPS thành tọa độ phẳng. Nó không:

- Đổi longitude/latitude thành X/Y của hệ UTM.
- Sửa thứ tự `[latitude, longitude]` bị đảo.
- Thay đổi dữ liệu đã index.
- Biến đường chim bay thành khoảng cách lái xe.
- Bù sai lệch GPS do thiết bị, mái nhà hoặc canyon đô thị.
- Thêm độ cao hoặc địa hình vào thuật toán geospatial của MongoDB.

### 12.1. Ví dụ nhầm kiểu độ và mét

```javascript
// SAI: truyền tọa độ đã nhân 1000 với ý định "đổi sang mét".
{
  type: "Point",
  coordinates: [106700, 10780]
}
```

GeoJSON Point yêu cầu kinh/vĩ độ trong khoảng hợp lệ, nên số trên là vô nghĩa với tọa độ Earth. Chỉ chuyển đổi **radius/distance** ở nơi cần, không nhân longitude/latitude lên.

### 12.2. Độ vĩ tuyến và kinh tuyến không có cùng độ dài

Một độ kinh độ ở gần xích đạo đại diện quãng đường dài hơn một độ kinh độ tại vĩ độ cao. Do đó:

```text
deltaLon = 0.01 degrees
```

không có nghĩa một số mét cố định trên toàn thế giới. Dùng geo operators phù hợp hoặc thuật toán khoảng cách với mô hình Trái Đất đã định nghĩa.

### 12.3. Bán kính Trái Đất là tham số mô hình

Tài liệu MongoDB/Spring có ví dụ bán kính xích đạo gần `6378.1 km`. Một số hệ GIS dùng bán kính trung bình khoảng `6371 km`. Hai lựa chọn dẫn đến sai khác nhỏ nhưng có thể thấy trong các bài test ở biên. Nên:

- Dùng **một hằng số có tên** trong các phần chuyển `meters ↔ radians` của ứng dụng.
- Không hứa kết quả bitwise identical với thuật toán khác dùng ellipsoid/CRS.
- Tạo tolerance hợp lý cho distance assertion.

## 13. Spring Data MongoDB: Point và GeoJsonPoint khác nhau ở đâu?

### 13.1. Legacy Point

```java
import org.springframework.data.geo.Point;

Point legacyNear = new Point(106.7000, 10.7800);
```

Trong Spring Data MongoDB, `Point` trong ngữ cảnh geo query có thể được serialize thành **legacy coordinate pair**:

```javascript
[106.7000, 10.7800]
```

Với spherical legacy query, đơn vị giới hạn có thể được chuyển về radian. Đừng giả định một `Point` luôn có semantics GeoJSON chỉ vì x/y là longitude/latitude.

### 13.2. GeoJsonPoint

```java
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;

GeoJsonPoint geoNear = new GeoJsonPoint(
    106.7000, 10.7800
);
```

Nó được render thành:

```javascript
{
  type: "Point",
  coordinates: [106.7000, 10.7800]
}
```

`GeoJsonPoint.getX()` tương ứng **longitude**, `getY()` tương ứng **latitude**. Sự khác biệt serialization của origin quyết định cách MongoDB hiểu khoảng cách raw trong geospatial query.

### 13.3. Đừng import nhầm Point

```java
// Legacy:
org.springframework.data.geo.Point

// GeoJSON:
org.springframework.data.mongodb.core.geo.GeoJsonPoint
```

Một lệnh refactor chỉ đổi import/constructor từ `Point` sang `GeoJsonPoint` có thể làm thay đổi **đơn vị** trong pipeline dù các tọa độ số không đổi. Luôn kiểm tra câu query BSON được render trước và sau migration.

## 14. Spring Data Distance, Metric và Metrics

Spring Data Commons cung cấp `Distance` và `Metric` để mang ý nghĩa đơn vị vào query. Những kiểu thường gặp:

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metric;
import org.springframework.data.geo.Metrics;

Distance twoKilometers = new Distance(
    2, Metrics.KILOMETERS
);

Distance threeMiles = new Distance(
    3, Metrics.MILES
);

Distance rawNumber = new Distance(
    2000, Metrics.NEUTRAL
);
```

| Kiểu | Vai trò |
| --- | --- |
| `Distance` | Bao giá trị và đơn vị/metric |
| `Metric` | Abstraction chuyển đổi theo đơn vị đo |
| `Metrics.KILOMETERS` | Kilômét |
| `Metrics.MILES` | Miles |
| `Metrics.NEUTRAL` | Metric trung tính, không tự gắn km/mi |
| `NearQuery` | Builder cho geospatial near query và cấu hình điều kiện |
| `GeoResult<T>` | Kết quả có entity và khoảng cách |
| `GeoResults<T>` | Wrapper nhiều kết quả + thông tin tổng hợp cho API imperative |

### 14.1. Vấn đề không nằm ở tên enum

`Metrics.KILOMETERS` không có nghĩa MongoDB server nhận literal `maxDistance=2` và tự hiểu km. Spring Data dùng metric trong việc tạo **truy vấn có chuyển đổi phù hợp với representation**. Với legacy spherical, ví dụ Javadoc cho thấy `Distance(2, Metrics.KILOMETERS)` được chuyển thành giới hạn radian và distance multiplier tương ứng.

### 14.2. getValue() phải đi cùng getMetric()

```java
Distance distance = new Distance(
    2, Metrics.KILOMETERS
);

double numeric = distance.getValue();
Metric unit = distance.getMetric();
```

`numeric == 2` chỉ có nghĩa **2 theo metric của Distance**. Nếu bỏ `Metric` rồi lưu số vào JSON `distance` không có đơn vị, client có thể tưởng là mét.

### 14.3. Hai chiến lược an toàn

**Chiến lược A — chuẩn hóa mét ở tầng application:**

```text
radiusKm từ HTTP → convert thành radiusMeters
GeoJsonPoint → $geoNear(maxDistance=radiusMeters)
MongoDB raw distanceMeters → response distanceKm = /1000
```

**Chiến lược B — để Spring Data quản lý Metric:**

```text
Point + Distance(2, Metrics.KILOMETERS)
       ↓
NearQuery / Repository query construction
       ↓
Kiểm tra generated BSON:
  legacy spherical → maxDistance radians,
  distanceMultiplier tương ứng output km
```

Đừng kết hợp A và B rồi tự chuyển thêm nhiều lần. Với `GeoJsonPoint` và `NearQuery`, nên ưu tiên pipeline/giới hạn **mét tường minh** cho tutorial này và kiểm tra kết quả thay vì giả định Spring Data luôn tạo đúng một hình dạng BSON trong mọi version.

## 15. Một entity GeoJSON trong Spring Data MongoDB

### 15.1. Class lưu pickup point

```java
package com.example.geo.persistence;

import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexed;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document("pickup_points")
public record PickupPoint(
    @MongoId(FieldType.STRING) String id,
    String tenantId,
    String name,
    boolean active,
    @GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
    GeoJsonPoint location
) {}
```

`GeoJsonPoint` giúp lưu BSON:

```javascript
{
  type: "Point",
  coordinates: [106.7000, 10.7800]
}
```

Không phải mọi MongoDB collection tự có index khi thêm annotation. Tự động tạo index của Spring Data phụ thuộc configuration và phiên bản, thường **không nên bật tùy tiện trong production**. Với fixture mongosh đã tạo index, application nên xác minh schema/index thực tế.

### 15.2. Field phải mang ý nghĩa một điểm

Nếu một document lưu nhiều địa điểm bằng `MultiPoint`/array, `$geoNear` có thể tính khoảng cách tới điểm/biên gần nhất theo semantics của MongoDB, **không phải nhất thiết tới tâm hình học mà UI hiển thị**. Với API tìm điểm lấy hàng, một `GeoJsonPoint` trên mỗi document thường đơn giản hơn.

### 15.3. Không sửa trực tiếp số x/y mà quên mapping

Khi cập nhật vị trí, ghi cả GeoJSON geometry object hợp lệ. Nếu một migration chỉ thay một phần trong `location.coordinates`, cần kiểm tra index và dữ liệu sau ghi để không vô tình đảo kinh/vĩ độ hoặc lưu sai hệ tọa độ.

## 16. NearQuery: mô tả truy vấn với bán kính mét tường minh

### 16.1. GeoJSON origin với giới hạn 2.000 mét

```java
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.NearQuery;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

GeoJsonPoint origin = new GeoJsonPoint(
    106.7000, 10.7800
);

NearQuery near = NearQuery
    .near(origin)
    .maxDistance(2000.0)
    .spherical(true)
    .query(Query.query(
        Criteria.where("tenantId").is("tenant-a")
            .and("active").is(true)
    ));
```

Với `GeoJsonPoint` và numeric maxDistance trong query tường minh này, mục tiêu là truyền **2.000 mét** vào `$geoNear`. Dùng `spherical(true)` để tránh phụ thuộc lựa chọn implicit khi đọc mã. Trước khi dùng production, kiểm tra stage BSON được tạo ra trong đúng Spring Data version.

### 16.2. Vì sao không mặc định sử dụng Distance(2, Metrics.KILOMETERS) ở mọi chỗ?

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;

Distance twoKm = new Distance(
    2, Metrics.KILOMETERS
);
```

Một `Distance` có metric là lựa chọn hữu ích nếu để Spring Data xây query end-to-end. Nhưng khi code đã chuyển `radiusKm -> radiusMeters` và origin là GeoJSON, không nên **vừa truyền mét đã chuyển vừa gắn metric KILOMETERS**. Kiểm tra getMetric/serialized pipeline để tránh lỗi nhân 1.000 hoặc chia 1.000 hai lần.

### 16.3. Giới hạn cả min/max distance

```java
NearQuery annulus = NearQuery
    .near(new GeoJsonPoint(106.7000, 10.7800))
    .minDistance(500.0)
    .maxDistance(2000.0)
    .spherical(true);
```

Các numeric limits được truyền theo đơn vị native của GeoJSON: **mét** trong ví dụ. Tên `annulus` nói về một khoảng từ 500 m đến 2.000 m, không phải quét một hình vành khăn trên đường bộ.

### 16.4. Chú ý trường key và nhiều index

`NearQuery` là abstraction của Spring Data. Nếu collection có **nhiều geospatial index fields**, kiểm tra API version cho khả năng chỉ định key và, khi cần, dùng aggregation stage BSON explicit để buộc `key: "location"`. Đừng mặc định server luôn chọn geospatial index đúng.

## 17. MongoOperations.geoNear: hiểu API cũ và khoảng cách trả về

Spring Data có:

```java
import org.springframework.data.geo.GeoResults;
import org.springframework.data.mongodb.core.MongoOperations;

GeoResults<PickupPoint> rows =
    mongoOperations.geoNear(near, PickupPoint.class);
```

Trong các phiên bản hiện hành, `MongoOperations.geoNear(...)` được đánh dấu **deprecated từ Spring Data MongoDB 2.2**, vì MongoDB 4.2 loại bỏ command `geoNear` cũ; Spring Data dùng aggregation `$geoNear` để triển khai tương thích. **Ưu tiên `Aggregation.geoNear(...)` cho mã mới**.

### 17.1. GeoResult và GeoResults

```java
rows.getContent().forEach(row -> {
    PickupPoint pickup = row.getContent();
    double value = row.getDistance().getValue();
    // Không đặt tên value là km nếu chưa xác nhận metric.
});
```

`GeoResult.getDistance()` trả `Distance`. Một `Distance.getValue()` không tự ghi đơn vị lên API JSON nếu bạn serialize nó thành `double`. Cần xác nhận metric của query/result, nhất là khi code đang chuyển từ legacy `Point` sang `GeoJsonPoint`.

### 17.2. Ví dụ Point với Metrics.KILOMETERS

```java
import org.springframework.data.geo.Point;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;

Point legacyOrigin = new Point(106.7000, 10.7800);
NearQuery legacyNear = NearQuery
    .near(legacyOrigin)
    .maxDistance(new Distance(2, Metrics.KILOMETERS));

GeoResults<PickupPoint> legacyResults =
    mongoOperations.geoNear(legacyNear, PickupPoint.class);
```

Đây là đường API **để Spring Data xử lý metric**, không phải ví dụ truyền literal 2 vào MongoDB như radian. Javadoc mô tả Spring Data có thể tạo **maxDistance theo radian** cho legacy spherical, kèm multiplier trả kết quả theo km. Bản thân stored field GeoJSON không loại bỏ khác biệt của **near argument**.

### 17.3. Không so trực tiếp kết quả có metric khác nhau

```text
GeoJSON raw distance:
  1_250      → meters

Legacy + Metrics.KILOMETERS:
  1.25       → kilometers

Hai số đại diện cùng khoảng cách nhưng khác unit.
```

Chuẩn hóa về một unit nội bộ trước khi so, sort, aggregate hoặc serialize.

## 18. Spring Data Aggregation.geoNear: ưu tiên cho mã mới

### 18.1. Aggregation có $geoNear ở đầu pipeline

```java
package com.example.geo.persistence;

import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.NearQuery;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;

@Component
public class PickupGeoGateway {
    private final MongoOperations mongo;

    public PickupGeoGateway(MongoOperations mongo) {
        this.mongo = mongo;
    }

    public List<Document> nearbyMeters(
        String tenantId,
        double longitude,
        double latitude,
        double radiusMeters
    ) {
        GeoInput.validate(tenantId, longitude, latitude, radiusMeters);

        NearQuery near = NearQuery
            .near(new GeoJsonPoint(longitude, latitude))
            .maxDistance(radiusMeters)
            .spherical(true)
            .query(Query.query(
                Criteria.where("tenantId").is(tenantId)
                    .and("active").is(true)
            ));

        TypedAggregation<PickupPoint> agg =
            Aggregation.newAggregation(
                PickupPoint.class,
                Aggregation.geoNear(near, "distanceMeters"),
                Aggregation.limit(20)
            );

        return mongo
            .aggregate(agg, Document.class)
            .getMappedResults();
    }
}
```

Trong ví dụ, `GeoInput` là helper validation ở mục 22. Kết quả `Document` mang `distanceMeters` theo đơn vị raw GeoJSON **khi không cấu hình multiplier/metric khác**. Việc dùng `TypedAggregation<PickupPoint>` giúp Spring Data có metadata mapping, nhưng cần test đúng pipeline/collection field.

### 18.2. Dữ liệu trả về nên có DTO

```java
public record NearbyPickupResponse(
    String pickupId,
    String name,
    double distanceMeters,
    double distanceKm
) {}
```

Không trực tiếp trả raw `Document` từ API public; nó có thể chứa field nội bộ như tenant ID, metadata vị trí hoặc thông tin không được phép lộ. Map/whitelist sang DTO và đổi unit một lần.

### 18.3. Chuyển từ BSON sang DTO

```java
private NearbyPickupResponse toResponse(Document row) {
    Object raw = row.get("distanceMeters");
    if (!(raw instanceof Number number)) {
        throw new IllegalStateException(
            "Missing numeric distanceMeters"
        );
    }
    double meters = number.doubleValue();
    if (!Double.isFinite(meters) || meters < 0) {
        throw new IllegalStateException(
            "Invalid distance from MongoDB"
        );
    }
    return new NearbyPickupResponse(
        row.getString("_id"),
        row.getString("name"),
        meters,
        meters / 1000.0
    );
}
```

Method này đặt trong gateway/mapper class có imports phù hợp. Nếu ID không phải String (ví dụ BSON ObjectId), phải convert đúng loại. Không ép kiểu `Double` trực tiếp khi driver có thể trả các subtype của `Number`.

### 18.4. distanceField và server version

MongoDB 8.1 trở đi có thể cho phép bỏ `distanceField` trong một số `$geoNear` trên collection thường, nhưng **truyền rõ distanceField trong bài này** để giữ contract output và tương thích nhiều server versions. Không coi property có thể bỏ là lý do xóa tên đơn vị.

### 18.5. Giới hạn số kết quả

`Aggregation.limit(20)` sau `$geoNear` giới hạn document trả về. Server vẫn phải thực hiện geo index traversal/filter theo query; limit không sửa một index thiếu hoặc bán kính vô hạn. Chọn radius cap và page/limit theo workload.

## 19. Repository derived queries theo khoảng cách

### 19.1. Interface

```java
package com.example.geo.persistence;

import java.util.List;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface PickupRepository
        extends MongoRepository<PickupPoint, String> {

    List<PickupPoint> findByLocationNear(
        Point origin,
        Distance maxDistance
    );

    List<PickupPoint> findByTenantIdAndActiveTrue(
        String tenantId
    );
}
```

`findByLocationNear(Point, Distance)` là derived geospatial method. Spring Data chọn operator và chuyển metric dựa trên argument/index metadata phù hợp. Nếu repository API cần bắt buộc lọc tenant/active **cùng câu geo query**, xây derived query đầy đủ đã test hoặc dùng `MongoOperations`/aggregation explicit như mục 18, không lấy tất cả geospatial results rồi lọc tenant ở Java.

### 19.2. Gọi với Point legacy và Distance metric

```java
List<PickupPoint> nearby = repository.findByLocationNear(
    new Point(106.7000, 10.7800),
    new Distance(2, Metrics.KILOMETERS)
);
```

Phương thức này có thể render toán tử spherical và giới hạn được Spring Data chuyển đổi từ km. Không tự nhân thêm 1000 vào `Distance(2, Metrics.KILOMETERS)`.

### 19.3. Gọi với GeoJsonPoint và metric trung tính

```java
List<PickupPoint> nearbyGeoJson =
    repository.findByLocationNear(
        new GeoJsonPoint(106.7000, 10.7800),
        new Distance(2000, Metrics.NEUTRAL)
    );
```

Ở đây mục tiêu là dùng **numeric 2.000 native units** cho GeoJSON = mét. Kiểm tra BSON thực được render trên Spring Data version sử dụng. Nếu derived query tạo output/limit khác mong đợi, chuyển sang aggregation explicit cho contract quan trọng.

### 19.4. Repository trả entity khác repository trả distance

`List<PickupPoint>` cho biết các điểm, nhưng không tự cung cấp trường `distanceMeters` đã tính. Spring Data có return types `GeoResult<T>`/`GeoResults<T>` cho những derived geospatial queries được hỗ trợ, nhưng behavior và reactive support khác nhau. Với API phải trả cả khoảng cách và đơn vị, `$geoNear` có `distanceField` explicit dễ kiểm soát hơn.

### 19.5. Đừng lọc tenant sau geo query

```java
// Không nên: tìm tất cả tenant rồi lọc trong Java.
// repository.findByLocationNear(...).stream()
//     .filter(p -> p.tenantId().equals(authenticatedTenant))
//     .toList();
```

Điều kiện tenant từ authentication context phải ở query gửi xuống MongoDB.

## 20. ReactiveMongoOperations và khoảng cách

### 20.1. Reactive aggregation trả Flux

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.NearQuery;
import reactor.core.publisher.Flux;

TypedAggregation<PickupPoint> aggregate =
    Aggregation.newAggregation(
        PickupPoint.class,
        Aggregation.geoNear(
            NearQuery.near(
                new GeoJsonPoint(106.7000, 10.7800)
            )
            .maxDistance(2000.0)
            .spherical(true),
            "distanceMeters"
        ),
        Aggregation.limit(20)
    );

Flux<Document> nearby =
    reactiveMongoOperations.aggregate(
        aggregate, Document.class
    );
```

Ví dụ cần điều kiện tenant/active trong `NearQuery.query(...)` tương tự mục 18 trước khi production; ở đây chỉ minh họa **reactive API shape**. `Flux` thực thi khi được subscribe, không phải lúc tạo biến.

### 20.2. API geoNear reactive cũ

```java
// API có trong nhiều phiên bản nhưng đã deprecated:
// Flux<GeoResult<PickupPoint>> rows =
//     reactiveMongoOperations.geoNear(nearQuery, PickupPoint.class);
```

Spring Data hiện hành khuyến nghị `Aggregation.geoNear` thay vì convenience API deprecated. Nếu dự án legacy dùng API cũ, phải xác minh đơn vị của `GeoResult.getDistance()` khi nâng cấp.

### 20.3. Backpressure không tự sửa query nặng

Một `Flux<Document>` không có nghĩa MongoDB chỉ thực hiện ít work. `$geoNear` vẫn cần index, tính khoảng cách và sắp xếp/filter. Hãy giới hạn radius, số kết quả, số concurrent queries và dùng explain để tối ưu server-side.

### 20.4. Không block() trong WebFlux handler

```java
// Không dùng trong reactive controller:
// List<Document> rows = nearby.collectList().block();
```

Trả `Flux` hoặc `Mono<List<DTO>>` nếu danh sách nhỏ đã giới hạn; không chặn event loop. Nếu dùng `collectList()`, phải đặt `$limit` trong MongoDB aggregation trước, không gom hàng triệu locations vào RAM.

## 21. Tách hợp đồng đơn vị thành type-safe API

Thay vì truyền `double radius` không có đơn vị, dùng wrapper:

```java
package com.example.geo.domain;

public record Meters(double value) {
    public Meters {
        if (!Double.isFinite(value) || value < 0) {
            throw new IllegalArgumentException(
                "Meters must be finite and nonnegative"
            );
        }
    }

    public static Meters fromKilometers(double kilometers) {
        if (!Double.isFinite(kilometers) || kilometers < 0) {
            throw new IllegalArgumentException(
                "Kilometers must be finite and nonnegative"
            );
        }
        return new Meters(kilometers * 1000.0);
    }

    public static Meters fromMiles(double miles) {
        if (!Double.isFinite(miles) || miles < 0) {
            throw new IllegalArgumentException(
                "Miles must be finite and nonnegative"
            );
        }
        return new Meters(miles * 1609.344);
    }

    public double kilometers() {
        return value / 1000.0;
    }

    public double radians(double earthRadiusMeters) {
        if (!Double.isFinite(earthRadiusMeters)
                || earthRadiusMeters <= 0) {
            throw new IllegalArgumentException(
                "Invalid earth radius"
            );
        }
        return value / earthRadiusMeters;
    }
}
```

### 21.1. Ví dụ dùng wrapper

```java
Meters radius = Meters.fromKilometers(2.0);

double forGeoJsonQuery = radius.value(); // 2000 meters
double forCenterSphere = radius.radians(6_378_137.0);

double inKm = new Meters(1250).kilometers(); // 1.25 km
```

Với GeoJSON `maxDistance`, dùng `radius.value()`; với legacy spherical/$centerSphere, dùng `radius.radians(R)`.

### 21.2. Unit object chưa đủ để bảo vệ business cap

Wrapper trên cho phép 10 triệu km nếu số hữu hạn. API nên đặt **giới hạn tối đa** theo SLO, chẳng hạn không cho radius vượt 100.000 m trong tìm điểm lấy hàng. Không nhất thiết chọn cùng giới hạn cho hệ thống hàng không hoặc nghiên cứu địa lý.

## 22. Validation kinh độ, vĩ độ và bán kính

### 22.1. Một helper kiểm tra input

```java
package com.example.geo.persistence;

public final class GeoInput {
    private static final double MAX_BUSINESS_RADIUS_METERS =
        100_000.0;

    private GeoInput() {}

    public static void validate(
        String tenantId,
        double longitude,
        double latitude,
        double radiusMeters
    ) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Missing tenant");
        }
        if (!Double.isFinite(longitude)
                || longitude < -180 || longitude > 180) {
            throw new IllegalArgumentException("Invalid longitude");
        }
        if (!Double.isFinite(latitude)
                || latitude < -90 || latitude > 90) {
            throw new IllegalArgumentException("Invalid latitude");
        }
        if (!Double.isFinite(radiusMeters)
                || radiusMeters < 0
                || radiusMeters > MAX_BUSINESS_RADIUS_METERS) {
            throw new IllegalArgumentException("Invalid radius");
        }
    }
}
```

`MAX_BUSINESS_RADIUS_METERS` là **giới hạn ví dụ của ứng dụng**, không phải giới hạn mọi MongoDB geo query. Không để client chủ động truyền `tenantId` chưa xác thực; giá trị đó phải đến từ security context.

### 22.2. Chặn NaN và Infinity

```java
Double.NaN
Double.POSITIVE_INFINITY
Double.NEGATIVE_INFINITY
```

Không phải bán kính hợp lệ. Chỉ kiểm `radius >= 0` có thể không loại bỏ NaN vì so sánh với NaN trả false; dùng `Double.isFinite`.

### 22.3. Tránh overflow sau chuyển đổi

```java
Meters.fromKilometers(Double.MAX_VALUE)
```

Phép nhân có thể overflow thành Infinity, constructor `Meters` sẽ từ chối. Trong production, nên kiểm giới hạn business ngay trên input trước khi nhân để trả lỗi hữu ích hơn và tránh query phạm vi cực lớn.

### 22.4. Phân biệt giá trị coordinate và radius

`longitude = 106.7` là kinh độ hợp lệ. Nhưng `radiusMeters = 106.7` là **106,7 mét** nếu API nội bộ dùng mét. Một số chỉ có ý nghĩa khi đi cùng unit và field name.

## 23. Thiết kế API từ kilômét sang mét rồi trả kết quả

Giả sử REST endpoint nhận:

```http
GET /api/pickup-points/nearby?longitude=106.70&latitude=10.78&radiusKm=2
```

Đây chỉ là endpoint ví dụ, không phải một request đã được gọi. Một hợp đồng tốt nên ghi rõ:

| Field | Đơn vị | Validation |
| --- | --- | --- |
| `longitude` | Độ (°) | Hữu hạn, từ -180 đến 180 |
| `latitude` | Độ (°) | Hữu hạn, từ -90 đến 90 |
| `radiusKm` | Kilômét | Hữu hạn, không âm, dưới business cap |
| `distanceMeters` trả về | Mét | Không âm, số hữu hạn |
| `distanceKm` trả về | Kilômét | `distanceMeters / 1000` |
| `tenantId` nội bộ | Không phải đơn vị đo | Lấy từ authentication, không cho client tùy đặt |

### 23.1. Đưa việc chuyển đổi vào một boundary

```java
public record NearbyRequest(
    double longitude,
    double latitude,
    double radiusKm
) {
    public Meters toRadiusMeters() {
        Meters result = Meters.fromKilometers(radiusKm);
        if (result.value() > 100_000.0) {
            throw new IllegalArgumentException(
                "Radius too large"
            );
        }
        return result;
    }
}
```

Trong code thật, wrapper `Meters` nằm ở package domain và cần import. Controller chuyển `radiusKm` sang `Meters` **một lần** trước khi gọi persistence adapter.

### 23.2. Không trả tên field mập mờ

```json
{
  "pickupId": "p-b",
  "distanceMeters": 1093.4,
  "distanceKm": 1.0934
}
```

Số trong ví dụ là minh họa để thể hiện hợp đồng JSON, **không phải kết quả đo thực tế của một tuyến đường**. Với user-facing UI, có thể hiển thị `1.09 km` nhưng giữ raw numeric distance nội bộ để sort/filter.

### 23.3. Rounding ở bước cuối

```java
double displayKm =
    Math.round(distanceMeters / 1000.0 * 100.0) / 100.0;
```

Chỉ làm tròn để hiển thị, **không dùng displayKm đã làm tròn** quyết định điểm nằm trong hay ngoài bán kính. Ví dụ 2.004 km khi làm tròn có thể thành 2.00 km, nhưng vẫn ở **ngoài bán kính 2.000 m**.

### 23.4. Không tin client distance

Nếu client gửi thêm `distanceKm: 0.1` để tự xếp hạng, không nên coi đó là bằng chứng khoảng cách thực. Server nên tính/kiểm tra từ tọa độ và dữ liệu nguồn theo query policy; với những quyết định có hệ quả tài chính cần xem xét chống giả mạo vị trí và độ chính xác GPS.

## 24. Haversine để kiểm thử gần đúng, không thay MongoDB

Để kiểm tra độ lớn kết quả ngoài database, có thể dùng công thức Haversine giữa hai điểm longitude/latitude trên một hình cầu bán kính R:

\[
\begin{aligned}
\Delta\varphi &= \varphi_2-\varphi_1,\\
\Delta\lambda &= \lambda_2-\lambda_1,\\
a &= \sin^2\left(\frac{\Delta\varphi}{2}\right)
 + \cos\varphi_1\cos\varphi_2
\sin^2\left(\frac{\Delta\lambda}{2}\right),\\
d &= 2R\arcsin\left(\sqrt{a}\right).
\end{aligned}
\]

Trong đó `φ` là vĩ độ và `λ` là kinh độ **đã đổi sang radian cho phép tính lượng giác**, còn điểm GeoJSON gửi vào MongoDB vẫn là độ.

### 24.1. Java reference implementation

```java
package com.example.geo.domain;

public final class SphericalDistance {
    public static final double EARTH_RADIUS_METERS =
        6_378_137.0;

    private SphericalDistance() {}

    public static double haversineMeters(
        double lon1, double lat1,
        double lon2, double lat2
    ) {
        requireCoordinate(lon1, lat1);
        requireCoordinate(lon2, lat2);

        double phi1 = Math.toRadians(lat1);
        double phi2 = Math.toRadians(lat2);
        double deltaPhi = Math.toRadians(lat2 - lat1);
        double deltaLambda = Math.toRadians(lon2 - lon1);

        double sinPhi = Math.sin(deltaPhi / 2);
        double sinLambda = Math.sin(deltaLambda / 2);
        double a = sinPhi * sinPhi
            + Math.cos(phi1) * Math.cos(phi2)
            * sinLambda * sinLambda;

        // Clamp chống sai số floating point sát 0 hoặc 1.
        double clamped = Math.min(1.0, Math.max(0.0, a));
        return 2 * EARTH_RADIUS_METERS
            * Math.asin(Math.sqrt(clamped));
    }

    private static void requireCoordinate(
        double longitude, double latitude
    ) {
        if (!Double.isFinite(longitude)
                || !Double.isFinite(latitude)
                || longitude < -180 || longitude > 180
                || latitude < -90 || latitude > 90) {
            throw new IllegalArgumentException(
                "Invalid geographic coordinate"
            );
        }
    }
}
```

### 24.2. Những điều Haversine không chứng minh

- Không cho biết MongoDB index có được dùng.
- Không kiểm tra `$geoNear` maxDistance/multiplier được render đúng.
- Không cho khoảng cách chạy xe.
- Không mô tả độ cao/địa hình và tất cả hiệu ứng geodesic trên ellipsoid.
- Không kiểm tra query tenant, active, authorization và result limit.

Đây chỉ là **reference sanity check** trong test. Với điểm sát biên 2.000 m, có thể có sai lệch do mô hình bán kính, tính toán floating point hoặc cách MongoDB xử lý geometry. Tránh assert equality quá khắt khe.

### 24.3. Kiểm tra hai trường hợp dễ hiểu

```java
double same = SphericalDistance.haversineMeters(
    106.7, 10.78,
    106.7, 10.78
);

double nearby = SphericalDistance.haversineMeters(
    106.7, 10.78,
    106.71, 10.78
);

// same ≈ 0 mét; nearby xấp xỉ hơn 1 km.
```

Không ghi cứng «hai kinh độ cách nhau 0.01° luôn đúng 1.1 km» cho mọi vĩ độ.

## 25. Precision, biên bán kính và dữ liệu đo thực tế

### 25.1. Điều kiện 2 km không giống khoảng cách hiển thị

Ví dụ có hai candidate:

```text
Candidate A: 1_999.96 m
Candidate B: 2_000.04 m
```

Với `$maxDistance: 2000`, MongoDB nên xét theo khoảng cách server tính, không theo giá trị đã làm tròn về `2.00 km` trên giao diện. Khi kiểm thử, chọn các điểm **cách rõ ràng bên trong và bên ngoài** biên để tránh test quá nhạy với numerical tolerance.

### 25.2. GPS có độ chính xác hữu hạn

Một thiết bị có thể báo accuracy radius hàng chục mét hoặc hơn. MongoDB không tự biết độ tin cậy của mỗi vị trí nếu document không lưu metadata. Với hệ thống phụ thuộc vị trí, cân nhắc:

- Thời điểm tọa độ được đo.
- Accuracy/uncertainty của thiết bị.
- Thời gian từ lần cập nhật cuối.
- Liệu user có cho phép dùng location.
- Business rule khi một điểm ở gần ngưỡng.

### 25.3. Tọa độ sát kinh tuyến ±180°

Ở vùng anti-meridian, khoảng cách giữa longitude gần `+180°` và `-180°` có thể rất nhỏ trên Trái Đất dù phép trừ số học gần 360°. Không tự tính khoảng cách bằng `abs(lon1-lon2)`. Sử dụng geospatial operators/thuật toán cầu đúng.

### 25.4. Tọa độ vĩ độ gần ±90°

Vùng gần cực khiến độ dài một độ kinh tuyến/kinh độ khác đáng kể so với vùng xích đạo. Những giải pháp bounding box dựa trên độ cố định có thể sai; cần test trường hợp đặc biệt nếu dữ liệu trải khắp toàn cầu.

### 25.5. Độ cao

MongoDB 2dsphere thường tính địa lý trên bề mặt cầu, không tự cho khoảng cách 3D theo altitude. Nếu ứng dụng drone/định vị nhiều tầng yêu cầu độ cao, hãy thiết kế mô hình riêng, không tự hiểu một GeoJSON coordinate thứ ba là đã được truy vấn theo khoảng cách 3D.

## 26. Index, explain và giới hạn hiệu năng

### 26.1. Xem index hiện có

```javascript
db.pickup_points.getIndexes();
```

Kiểm tra field/type đúng `location: "2dsphere"`, không chỉ kiểm tra document có GeoJSON.

### 26.2. Explain một geoNear aggregation

```javascript
db.pickup_points.explain("executionStats").aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      key: "location",
      spherical: true,
      maxDistance: 2000,
      distanceField: "distanceMeters",
      query: {
        tenantId: "tenant-a",
        active: true
      }
    }
  },
  { $limit: 20 }
]);
```

Tìm các chỉ dấu plan/index như geospatial access, số documents/keys examined, time spent và các filter không tận dụng index. Tên stages và cấu trúc explain có thể khác MongoDB version/execution engine; không viết test chỉ dựa vào một tên stage cố định.

### 26.3. Compound geospatial index

Một ứng viên cho hệ thống multi-tenant:

```javascript
db.pickup_points.createIndex(
  { location: "2dsphere", tenantId: 1, active: 1 },
  { name: "ix_geo_tenant_active" }
);
```

Thứ tự key và hiệu quả phụ thuộc query shape, cardinality, tỷ lệ active/tenant, version/server optimizer. **Không** tạo chỉ mục này trên production chỉ vì nó có vẻ hợp lý: cần đo index size, write cost và explain trên dữ liệu đại diện.

Nếu cùng collection vẫn có index `location: "2dsphere"` đơn, `$geoNear.key: "location"` xác định **field**, không nhất thiết buộc một tên index compound cụ thể. Query planner có thể chọn giữa các index trên cùng field; đánh giá plan thật.

### 26.4. Radius càng lớn, số ứng viên càng nhiều

```text
radius = 500 m    → thường ít ứng viên
radius = 2 km     → nhiều hơn
radius = 100 km   → có thể rất nhiều ứng viên
```

Đây là xu hướng hình học chung, không phải số lượng cố định. Trong vùng phân bố tương đối đều trên mặt phẳng nhỏ, diện tích tăng xấp xỉ theo `r²`; bán kính tăng gấp đôi có thể làm vùng tìm kiếm tăng khoảng bốn lần. Density thực tế có thể không đều.

### 26.5. Giới hạn và projection

Sau `$geoNear`, thêm `$limit` hợp lý và `$project` các field thật sự cần:

```javascript
{ $limit: 20 },
{
  $project: {
    _id: 1,
    name: 1,
    distanceMeters: 1
  }
}
```

Đừng trả toàn bộ thông tin địa chỉ, owner, ghi chú nội bộ hoặc vị trí nhạy cảm của những điểm khác tenant.

### 26.6. Sort lại có thể phá thứ tự gần nhất

`$geoNear` trả điểm theo khoảng cách gần tới xa. Nếu thêm `$sort: { name: 1 }` sau đó, bạn đã thay đổi thứ tự kết quả thành theo tên, không còn đúng ý nghĩa «gần nhất». Nếu cần tie-breaker rõ hoặc ranking nhiều tiêu chí, mô tả tiêu chí đó trong API contract.

## 27. Geospatial search, phân quyền và tính nhất quán dữ liệu

### 27.1. Tenant filter đặt trong query server-side

```javascript
query: {
  tenantId: "tenant-a",
  active: true
}
```

Không lấy khoảng cách của mọi điểm rồi lọc tenant ở client; việc trả khoảng cách hoặc tồn tại của một vị trí có thể là rò rỉ dữ liệu.

### 27.2. Point location có thể thay đổi

Một điểm lấy hàng chuyển địa điểm giữa hai lần query. Vì vậy, kết quả «1,2 km» là ảnh chụp tại thời điểm query, không phải bảo đảm vĩnh viễn. Với use case đặt lịch giao nhận, cần xác minh điểm vẫn active, địa chỉ hợp lệ và sức chứa tại **thời điểm confirm**, không chỉ dựa vào một geospatial search result có thể stale.

### 27.3. Read preference và replica lag

Nếu đọc từ secondary, vị trí/active status có thể chậm hơn primary. Điều này ảnh hưởng freshness của kết quả dù đơn vị đúng. Hãy phân biệt **sai đơn vị** (logic bug) với **dữ liệu cũ** (consistency policy) và **sai geocoding** (data quality).

### 27.4. Vị trí và quyền riêng tư

Tọa độ người dùng là dữ liệu có thể nhạy cảm. Không log nguyên kinh/vĩ độ cùng định danh cá nhân khi không cần; giới hạn retention, authorization, precision và mục đích sử dụng theo chính sách áp dụng. Không cho debugging endpoint rò location của tenant khác.

## 28. Unit test cho phép chuyển đổi

Unit test có thể chứng minh các phép nhân/chia đúng mà không cần MongoDB. Nó **không** chứng minh query đã dùng index hoặc đúng semantics trên server.

### 28.1. JUnit 5 cho km, miles và radians

```java
package com.example.geo.domain;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class MetersTest {
    private static final double EARTH_R =
        6_378_137.0;

    @Test
    void kilometersConvertToMeters() {
        Meters d = Meters.fromKilometers(2.0);
        assertEquals(2000.0, d.value(), 1e-9);
        assertEquals(2.0, d.kilometers(), 1e-12);
    }

    @Test
    void milesConvertToMeters() {
        Meters d = Meters.fromMiles(5.0);
        assertEquals(8046.72, d.value(), 1e-8);
    }

    @Test
    void radiansRoundTripWithChosenEarthRadius() {
        Meters d = new Meters(2000.0);
        double radians = d.radians(EARTH_R);
        assertEquals(
            2000.0,
            radians * EARTH_R,
            1e-9
        );
    }

    @Test
    void rejectsNaNAndInfiniteDistance() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new Meters(Double.NaN)
        );
        assertThrows(
            IllegalArgumentException.class,
            () -> Meters.fromKilometers(Double.POSITIVE_INFINITY)
        );
    }

    @Test
    void rejectsNegativeDistance() {
        assertThrows(
            IllegalArgumentException.class,
            () -> Meters.fromKilometers(-1)
        );
    }
}
```

### 28.2. Unit test GeoInput

```java
@Test
void invalidLatitudeIsRejected() {
    assertThrows(
        IllegalArgumentException.class,
        () -> GeoInput.validate(
            "tenant-a", 106.7, 106.7, 2000
        )
    );
}

@Test
void validCoordinatesAndTwoKmPass() {
    assertDoesNotThrow(
        () -> GeoInput.validate(
            "tenant-a", 106.7, 10.78, 2000
        )
    );
}
```

Hai method đặt trong test class import JUnit/GeoInput phù hợp. Lưu ý kiểm tra bounds không phát hiện **mọi** trường hợp đảo kinh/vĩ độ: nếu hai số đều trong miền hợp lệ, thứ tự sai vẫn có thể qua validation. Cần contract, naming và fixture kiểm thử ngữ nghĩa.

### 28.3. Sanity check Haversine

```java
@Test
void nearbyPointIsRoughlyOneKilometerAway() {
    double meters = SphericalDistance.haversineMeters(
        106.7000, 10.7800,
        106.7100, 10.7800
    );

    assertTrue(meters > 1000.0);
    assertTrue(meters < 1200.0);
}
```

Kiểm thử chọn tolerance rộng để xác nhận **độ lớn**, không cố khớp mọi chữ số với thuật toán MongoDB khác radius/ellipsoid.

### 28.4. Không thử convert tọa độ như convert distance

```java
// SAI:
// new GeoJsonPoint(longitude * 1000, latitude * 1000)

// ĐÚNG:
new GeoJsonPoint(longitude, latitude);
```

Tọa độ vẫn theo độ, còn bán kính/distance mới cần convert đơn vị phù hợp.

## 29. Integration test MongoDB: bắt lỗi đơn vị ở database

Muốn chứng minh đơn vị của query, phải chạy trên MongoDB thật trong test environment, không chỉ mock `MongoOperations`. Ví dụ sau dùng MongoDB Testcontainers và Spring Boot 3.x; trên Spring Boot 4.x cần chọn đúng test starter và property URI.

### 29.1. Dependencies test

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>mongodb</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
```

Testcontainers 2.x có thể thay đổi artifact/module names so với ví dụ này. Sử dụng Spring Boot BOM/parent và test dependency versions đã được xác minh. Chạy Docker/Testcontainers trong môi trường được phép; không chạy suite có `drop()` trên database production.

### 29.2. Test fixture với ba khoảng cách và tenant khác

```java
package com.example.geo;

import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class GeoDistanceMongoIntegrationTest {

    @Container
    static MongoDBContainer mongo =
        new MongoDBContainer("mongo:7.0");

    @DynamicPropertySource
    static void mongoConfig(DynamicPropertyRegistry registry) {
        // Spring Boot 3.x:
        registry.add(
            "spring.data.mongodb.uri",
            mongo::getReplicaSetUrl
        );
        // Spring Boot 4.x: spring.mongodb.uri
    }

    @Autowired MongoOperations template;

    @BeforeEach
    void seed() {
        var col = template.getCollection("pickup_points");
        col.drop(); // CHỈ database test cô lập
        col.createIndex(new Document("location", "2dsphere"));

        col.insertMany(List.of(
            place("inside", "tenant-a", 106.7000, 10.7800),
            place("nearby", "tenant-a", 106.7100, 10.7800),
            place("outside", "tenant-a", 106.7500, 10.8000),
            place("foreign", "tenant-b", 106.7001, 10.7801)
        ));
    }

    private Document place(
        String id, String tenant,
        double longitude, double latitude
    ) {
        return new Document("_id", id)
            .append("tenantId", tenant)
            .append("active", true)
            .append("location", new Document("type", "Point")
                .append(
                    "coordinates", List.of(longitude, latitude)
                ));
    }

    private List<Document> query(Double multiplier) {
        Document geo = new Document(
            "near",
            new Document("type", "Point")
                .append(
                    "coordinates", List.of(106.7000, 10.7800)
                )
        )
        .append("key", "location")
        .append("spherical", true)
        .append("maxDistance", 2000.0)
        .append("distanceField",
            multiplier == null ? "distanceMeters" : "distanceKm")
        .append("query",
            new Document("tenantId", "tenant-a"));

        if (multiplier != null) {
            geo.append("distanceMultiplier", multiplier);
        }

        return template.getCollection("pickup_points")
            .aggregate(List.of(
                new Document("$geoNear", geo),
                new Document("$limit", 20)
            ))
            .into(new ArrayList<>());
    }

    @Test
    void twoKmIncludesInsideAndNearbyOnly() {
        List<Document> results = query(null);
        Set<String> ids = results.stream()
            .map(row -> row.getString("_id"))
            .collect(Collectors.toSet());

        assertEquals(Set.of("inside", "nearby"), ids);
    }

    @Test
    void multiplierChangesOutputButNotMatchingIds() {
        List<Document> meters = query(null);
        List<Document> kilometers = query(0.001);

        Set<String> meterIds = meters.stream()
            .map(d -> d.getString("_id"))
            .collect(Collectors.toSet());
        Set<String> kmIds = kilometers.stream()
            .map(d -> d.getString("_id"))
            .collect(Collectors.toSet());
        assertEquals(meterIds, kmIds);

        Document raw = meters.stream()
            .filter(d -> d.getString("_id").equals("nearby"))
            .findFirst().orElseThrow();
        Document converted = kilometers.stream()
            .filter(d -> d.getString("_id").equals("nearby"))
            .findFirst().orElseThrow();

        double rawMeters =
            ((Number) raw.get("distanceMeters")).doubleValue();
        double km =
            ((Number) converted.get("distanceKm")).doubleValue();

        assertEquals(rawMeters / 1000.0, km, 1e-6);
    }
}
```

Đây là **khung integration test theo Spring Boot 3/Testcontainers API tương thích**, cần ghép build configuration/app scanning cho dự án thực. Trong ví dụ, thư viện JUnit, Spring Boot MongoDB starter và MongoDB container được cấu hình riêng ở test scope; không dùng fixture production. Các điểm ngoài bán kính, cùng tenant và khác tenant giúp bắt lỗi đơn vị lẫn rò lọc.

### 29.3. Vì sao test bằng raw Document?

Test ở trên cố tình dùng raw BSON cho `$geoNear` để chứng minh **semantics của MongoDB** mà không bị layer `NearQuery` tự chuyển metric. Sau đó cần thêm một test **Spring Data aggregation** với cùng fixtures để xác minh generated stage và result DTO.

### 29.4. Test so sánh GeoJSON và legacy

Một regression test tốt:

1. Query GeoJSON `near: {type:"Point",coordinates:[...]}` với `maxDistance=2000`, result raw meters.
2. Query legacy `near: [lon,lat]`, `spherical:true` với `maxDistance=2000/R` và `distanceMultiplier=R/1000`, result kilometers.
3. So sets of IDs và so khoảng cách sau khi đổi cả hai về meters.
4. Dùng tolerance hợp lý vì mô hình khoảng cách có thể khác nhẹ.

Nếu test trên cùng một `2dsphere` field lưu GeoJSON, hãy xác nhận server version hỗ trợ query legacy input như tài liệu. Không tự giả định một query gần đúng có cùng **ordered output từng chữ số** khi phần representation/metric thay đổi.

### 29.5. Test missing/invalid index

Trước khi migration/provisioning index, một `$geoNear` cần geospatial index có thể lỗi. Test bằng collection tạm trong database test, không xóa index production. Assert failure được báo rõ trong monitoring/health chứ không biến thành empty result «không có điểm».

### 29.6. Reactive integration test

```java
Flux<Document> stream = reactiveMongoOperations.aggregate(
    geoAggregation, Document.class
);

StepVerifier.create(stream)
    .expectNextCount(2)
    .verifyComplete();
```

`geoAggregation` ở đây là một `TypedAggregation<PickupPoint>` giống mục 20 nhưng **phải có tenant filter và dữ liệu test** để bảo đảm đúng hai kết quả; cần imports Reactor/TestVerifier và reactive test context. Chỉ tạo `Flux` mà không subscribe không chứng minh query đã chạy.

### 29.7. Một tập test phải chứng minh cả unit và tenant

Nếu geospatial test trả thêm `foreign`, đó là lỗi access control dù khoảng cách đã tính đúng. Nếu trả `outside` vì radius 2 bị hiểu là 2 radian, đó là lỗi unit. Tách assertions để xác định chính xác nguyên nhân.

## 30. Những lỗi thường gặp khi đổi đơn vị

| Triệu chứng | Nguyên nhân điển hình | Cách sửa |
| --- | --- | --- |
| Radius 2 km nhưng gần như không có điểm | Truyền `maxDistance: 2` cho GeoJSON | Chuyển thành 2000 m |
| Radius 2 km nhưng nhận điểm rất xa | Truyền 2 cho legacy spherical (radian) | Dùng `2000 / R_METERS` |
| GeoJSON result là 1200 nhưng UI hiển thị 1200 km | Nhầm raw distance là km | Output GeoJSON raw tính bằng m |
| Legacy result là `0.0002` nhưng UI cho 0.0002 km | Nhầm raw radians là km | Nhân bán kính km thích hợp |
| `distanceMultiplier: 6378.137` làm kết quả cực lớn | Dùng hệ số legacy với GeoJSON meters | GeoJSON m → km dùng 0.001 |
| `distanceMultiplier: 0.001` nhưng vẫn lọc sai | Tin multiplier sẽ đổi `maxDistance` | Đổi bán kính query riêng |
| UI hiển thị khoảng cách nhỏ hơn 1000 lần | Chia 1000 cả trong MongoDB và Java | Chỉ đổi đơn vị một lần |
| Điểm xuất hiện ở vị trí lạ | Đảo longitude và latitude | GeoJSON là [longitude, latitude] |
| GeoJSON không tìm được index | Dùng 2d index trên field không phù hợp | Dùng `2dsphere` trên GeoJSON field |
| Query legacy bị hiểu sai khi đổi import | Thay `Point` bằng `GeoJsonPoint` | Regression test generated BSON/units |
| `$centerSphere` lọc quá rộng | Bán kính truyền bằng mét thay radian | Chia cho bán kính Trái Đất |
| `$geoNear` aggregation báo lỗi stage | Đặt `$match` trước `$geoNear` | Đặt `$geoNear` đầu, dùng `query` |
| `$geoNear` chọn sai geospatial field | Nhiều indexes không có `key` | Chỉ định key phù hợp |
| Results có field không như mong đợi | Metric trong `NearQuery` khác assumption | Kiểm tra query metric/BSON/result |
| `maxDistance` bị tính theo miles | Client gửi miles nhưng adapter coi km | API contract/validation theo unit |
| Boundary test lúc pass lúc fail | Điểm sát ngưỡng, sai số mô hình | Chọn điểm xa ngưỡng và tolerance |
| Cùng hiển thị 2.00 km nhưng một điểm bị loại | Làm tròn trước/filter sau | Filter raw numeric distance |
| Radius rất lớn làm truy vấn chậm | Không có business cap | Limit bán kính, kết quả và concurrency |
| Query trả vị trí tenant khác | Filter tenant sau khi query | Đưa tenant predicate vào server query |
| GeoJSON trả khoảng cách quá nhỏ ở vùng xa | Tự lấy chênh lệch độ thay vì địa lý | Dùng geo operators/Haversine đúng |
| Mong nhận thời gian lái xe từ `$geoNear` | Nhầm spherical distance với route distance | Dùng routing/travel-time service |
| Reactive endpoint trả rỗng dù query đúng | Không subscribe `Flux`/`Mono` | Compose và để framework subscribe |
| Backend thiếu metric validation | Cho phép NaN/Infinity | `Double.isFinite` và bounds |
| After migration thứ tự gần nhất đổi | Thay near geometry hoặc sort stage | Kiểm tra semantics + regression |
| Output không dùng đúng đơn vị đã công bố | Đặt `distanceKm` nhưng raw vẫn là mét | Rename/convert và contract test |
| Cache vị trí stale | Redis/read model trễ | Freshness policy và invalidation |
| Index quá lớn/ghi chậm sau thêm geo index | Tạo index thiếu đo đạc | Explain, size, write p95/p99, rollout |
| Dữ liệu gần cực/anti-meridian sai | Tính xấp xỉ Euclidean trên độ | Dùng geometry/hệ tọa độ thích hợp |

### 30.1. Quy trình chẩn đoán từng bước

```text
1. API nhận radius theo đơn vị nào (m/km/mi)?
                  ↓
2. Origin có phải GeoJSON Point [lon,lat] hay legacy pair?
                  ↓
3. Dùng $near, $nearSphere, $geoNear hay $centerSphere?
                  ↓
4. Lệnh MongoDB có maxDistance/minDistance ở đơn vị đúng không?
                  ↓
5. Nếu $geoNear: distanceMultiplier là bao nhiêu?
                  ↓
6. Result field được đặt tên/convert đúng đơn vị chưa?
                  ↓
7. Có 2dsphere/2d index đúng field và đúng query không?
                  ↓
8. Tenant/active filter, limit, projection có đúng không?
                  ↓
9. Kiểm tra BSON thật và explain trên MongoDB test.
                  ↓
10. Regression test points inside/outside radius và legacy/GeoJSON.
```

### 30.2. Chẩn đoán bằng một điểm có khoảng cách đã biết

Nếu một fixture dự kiến cách khoảng 1 km nhưng MongoDB trả `0.001`, trước hết hỏi **đơn vị là gì**. Nó có thể biểu diễn 0,001 rad (≈6,4 km) hoặc 0,001 km (1 m), hoàn toàn khác nhau. Không cố «sửa» bằng random multiplier cho đến khi xác nhận near point representation và output unit.

## 31. Bài thực hành có lời giải

### Bài 1 — Chuyển bán kính 2 km cho GeoJSON

**Đề bài:** Client gửi `radiusKm = 2`, MongoDB dùng `$near` với GeoJSON Point. Giá trị nào truyền vào `$maxDistance`?

**Lời giải:** `2 * 1000 = 2000` mét.

```javascript
{
  $near: {
    $geometry: {
      type: "Point",
      coordinates: [106.7000, 10.7800]
    },
    $maxDistance: 2000
  }
}
```

### Bài 2 — Legacy spherical cần radian

**Đề bài:** Với cùng 2 km, hãy tạo giới hạn `$maxDistance` cho legacy `$nearSphere`.

**Lời giải:** Dùng bán kính quy ước `R = 6_378_137 m`:

```javascript
const radiusRadians = 2000 / 6378137;
```

Giá trị xấp xỉ `0.000313571 rad`, **không phải** 2 hoặc 2000.

### Bài 3 — $centerSphere với GeoJSON lưu trong collection

**Đề bài:** Collection lưu GeoJSON và có 2dsphere index. Dùng `$geoWithin/$centerSphere` tìm trong 2 km; radius là mét hay radian?

**Lời giải:** Radius của `$centerSphere` luôn **radian** trong ví dụ:

```javascript
db.pickup_points.find({
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7000, 10.7800],
        2000 / 6378137
      ]
    }
  }
});
```

Đừng dùng `$centerSphere: [[lon,lat], 2000]`.

### Bài 4 — GeoJSON $geoNear trả km

**Đề bài:** Muốn lọc trong 3 km và output khoảng cách theo km.

**Lời giải:**

```javascript
{
  $geoNear: {
    near: {
      type: "Point",
      coordinates: [106.7, 10.78]
    },
    key: "location",
    spherical: true,
    maxDistance: 3000,
    distanceMultiplier: 0.001,
    distanceField: "distanceKm"
  }
}
```

`maxDistance` vẫn là 3000 m, còn output được chia 1000.

### Bài 5 — GeoJSON $geoNear trả miles

**Đề bài:** Cho bán kính 5 miles và output `distanceMiles`.

**Lời giải:**

```javascript
{
  maxDistance: 5 * 1609.344,
  distanceMultiplier: 1 / 1609.344,
  distanceField: "distanceMiles"
}
```

Phần này là các fields bổ sung cho `$geoNear` GeoJSON ở bài 4. Đầu vào bán kính bằng `8046.72 m`; output đổi mét sang miles.

### Bài 6 — Legacy $geoNear theo km

**Đề bài:** Legacy `near: [lon,lat]` chạy spherical, maxDistance cần 10 km, output cần km. Chọn hai hệ số.

**Lời giải:**

```javascript
maxDistance: 10000 / 6378137,
distanceMultiplier: 6378.137
```

Hệ số lọc là radian và hệ số output là km/radian. Không đảo hai hệ số.

### Bài 7 — distanceMultiplier có đổi membership không?

**Đề bài:** Một query GeoJSON `$geoNear` có `maxDistance=2000`. Nếu thêm `distanceMultiplier=0.001` thì một điểm cách 2.500 m có được chọn vào không?

**Lời giải:** Không. Multiplier chỉ thay đổi **distanceField trả về**, không làm maxDistance chuyển từ 2000 thành 2000 km. Điểm 2500 m vẫn ngoài bán kính 2000 m.

### Bài 8 — Point và GeoJsonPoint

**Đề bài:** Hai đối tượng Java:

```java
new Point(106.7, 10.78);
new GeoJsonPoint(106.7, 10.78);
```

Có chung ý nghĩa origin nhưng có cùng dạng BSON near query không?

**Lời giải:** Không. `Point` thường là legacy pair; `GeoJsonPoint` serialize thành object GeoJSON. Trong spherical geoNear, điều đó có thể thay đổi native distance unit (radians vs meters). Kiểm tra generated BSON và adapter conversion khi refactor.

### Bài 9 — Spring Distance và Metrics

**Đề bài:** Ý nghĩa của `new Distance(10, Metrics.MILES)` là gì? Có nên gọi `getValue()` rồi mặc định coi 10 là mét không?

**Lời giải:** Giá trị là **10 miles**, không phải 10 mét. Khi dùng với `NearQuery`/repository, Spring Data có thể chuyển metric thành giới hạn native và output unit tương ứng. Nếu lấy `getValue()` đem serialize, phải giữ unit đi kèm.

### Bài 10 — Sửa pipeline sai thứ tự

**Đề bài:** Code:

```javascript
db.pickup_points.aggregate([
  { $match: { tenantId: "tenant-a" } },
  { $geoNear: { /* geo options */ } }
]);
```

**Lời giải:** Đặt `$geoNear` ở stage đầu, đưa tenant condition vào `query` bên trong `$geoNear` (khi collection/operator hỗ trợ), rồi `$limit` và `$project`. Đừng tạo `$match` trước `$geoNear`.

### Bài 11 — Bắt lỗi tenant khác trong radius

**Đề bài:** Collection có điểm của tenant-b nằm cách origin chỉ vài mét. API tenant-a có nên trả điểm đó không nếu radius đúng 2 km?

**Lời giải:** Không. Geo query phải có tenant predicate server-side, ví dụ `query: {tenantId:"tenant-a", active:true}`. Trong test, assert **tập ID** đúng, không chỉ assert số lượng. Đừng lọc tenant sau khi đã trả raw results.

### Bài 12 — Lập bộ test đổi đơn vị

**Đề bài:** Thiết kế kiểm thử cho migration từ `Point` legacy sang `GeoJsonPoint`.

**Lời giải:** Cần (1) data fixture trong/ngoài bán kính; (2) kiểm tra thứ tự longitude/latitude; (3) generated BSON `near` là GeoJSON; (4) `maxDistance` là mét; (5) `distanceMultiplier` đúng output; (6) đối chiếu raw MongoDB query và Spring Data aggregation; (7) so ID membership theo tolerance; (8) tenant isolation; (9) index/explain; (10) perf dưới radius/limit thực; (11) reactive subscription test nếu dùng; (12) regression cho NaN/Infinity/negative/large radius. Không chỉ sửa import rồi dựa vào một test happy path.

## 32. Checklist kỹ thuật trước khi triển khai

| Câu hỏi review | Bằng chứng / cách kiểm tra |
| --- | --- |
| Input API có ghi rõ đơn vị không? | `radiusKm`/`radiusMeters`, schema và docs |
| Output API có ghi rõ đơn vị không? | `distanceMeters`/`distanceKm`, contract tests |
| Kinh/vĩ độ có đúng thứ tự không? | Fixture và validation `[lon, lat]` |
| Input có thể là NaN/Infinity không? | `Double.isFinite` |
| Longitude/latitude có trong bounds không? | -180..180 / -90..90 |
| Có business max radius không? | Validation và load tests |
| Có giới hạn số kết quả không? | `$limit` / query limit |
| Database lưu GeoJSON hay legacy? | Inspect persisted BSON |
| Index hiện có là 2dsphere hay 2d? | `getIndexes()` và migration |
| Truy vấn dùng $near, $nearSphere hay $geoNear? | Inspect generated BSON |
| $geoNear có ở stage đầu không? | Pipeline inspection/test |
| Có nhiều geospatial indexes không? | `key` và explain |
| GeoJSON maxDistance có dùng mét không? | Test giới hạn 2000 m |
| Legacy spherical maxDistance có dùng radian không? | Conversion test |
| $centerSphere radius có dùng radian không? | Query + boundary tests |
| minDistance và maxDistance cùng unit không? | DTO validation, query assertions |
| distanceMultiplier áp cho output đúng không? | Test có/không multiplier |
| Có chuyển đổi hai lần không? | Integration + response contract |
| Spring Data Point hay GeoJsonPoint? | Imports, serialized `near` |
| Distance và Metrics có bị mất unit không? | `getMetric`/test output |
| Code dùng geoNear deprecated không? | Ưu tiên `Aggregation.geoNear` |
| Có repository query/aggregation thật được test không? | Testcontainers |
| Read results có bị after-convert sai unit không? | Raw BSON + DTO readback |
| Hệ số R được thống nhất không? | Named constant + tolerance |
| Có dùng đường chim bay làm ETA không? | API copy / routing boundary |
| Có test anti-meridian/poles nếu hệ toàn cầu? | Edge fixtures |
| Có giữ dữ liệu vị trí quá chi tiết không? | Privacy/security review |
| Tenant authorization có trong Mongo query không? | Cross-tenant test |
| Có cache/read preference làm dữ liệu cũ không? | Freshness SLO |
| Có index plan và p95/p99 dưới tải không? | Explain và load test |
| Có migration plan khi đổi Point sang GeoJsonPoint không? | Pre/post BSON diff |
| Có QA học thuật sau bước viết không? | STEP 6 NEW theo quy trình |

### 32.1. Bảng quyết định nhanh

| Đầu vào | Mục tiêu | Lựa chọn |
| --- | --- | --- |
| GeoJSON Point + 2dsphere | Tìm điểm gần trong 2 km | `$near` với `$maxDistance: 2000` |
| GeoJSON Point + 2dsphere | Trả cả khoảng cách theo mét | `$geoNear`, distanceField, không multiplier |
| GeoJSON Point + 2dsphere | Trả khoảng cách theo km | `$geoNear`, maxDistance mét, multiplier 0.001 |
| Legacy near spherical | Tìm trong 2 km | `maxDistance = 2000/R_METERS` rad |
| Legacy geoNear spherical | Output km | `distanceMultiplier = R_KILOMETERS` |
| Bất kể dữ liệu lưu là GeoJSON/legacy | Vùng tròn `$centerSphere` | Bán kính radian |
| Spring Data với GeoJsonPoint | Giới hạn theo mét tường minh | `NearQuery.near(GeoJsonPoint).maxDistance(meters)` |
| Spring Data với legacy Point | Giới hạn theo km qua metric | `Distance(km, Metrics.KILOMETERS)` |
| Dịch vụ cần khoảng cách lái xe | ETA/km đường bộ | Geospatial lọc ứng viên, routing xử lý tiếp |

### 32.2. Chỉ đổi một biến mỗi lần debug

Nếu query trả sai, đừng cùng lúc đổi `Point -> GeoJsonPoint`, đổi index 2d -> 2dsphere và thêm multiplier rồi kết luận không biết sửa nào có tác dụng. Hãy giữ fixture và query tường minh, kiểm thử lần lượt:

1. Data/coordinate order.
2. Index và geometry representation.
3. `maxDistance` và raw result unit.
4. `distanceMultiplier`.
5. Spring Data serialization.
6. DTO/HTTP response unit.

### 32.3. Không dùng một screenshot bản đồ để chứng minh precision

Bản đồ có thể hiển thị tọa độ đã làm tròn hoặc hiệu ứng projection. Test bằng raw numeric values và fixture dưới/ngoài bán kính, rồi dùng UI map để xác nhận trải nghiệm. Không lấy một hình tròn vẽ trên bản đồ làm bằng chứng mọi query dùng cùng đơn vị.

## 33. Tài liệu chính thức để đối chiếu

Các tài liệu cần được đọc theo MongoDB Server và Spring Data MongoDB version thực sự đang dùng:

- MongoDB — [`$near` operator](https://www.mongodb.com/docs/manual/reference/operator/query/near/): quy tắc GeoJSON longitude/latitude, geospatial index và đơn vị `$minDistance`/`$maxDistance`.
- MongoDB — [`$nearSphere` operator](https://www.mongodb.com/docs/manual/reference/operator/query/nearsphere/): khác biệt GeoJSON meters và legacy radians.
- MongoDB — [`$geoNear` aggregation stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geonear/): `distanceField`, `distanceMultiplier`, `maxDistance`, `key`, stage ordering và version behavior.
- MongoDB — [`$centerSphere`](https://www.mongodb.com/docs/manual/reference/operator/query/centersphere/): bán kính theo radian.
- MongoDB — [Convert Distance to Radians](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2d/calculate-distances/): công thức distance / Earth radius.
- MongoDB — [2dsphere Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/): đặc điểm index không gian theo cầu.
- Spring Data MongoDB — [Querying Documents / Metrics and Distance Calculation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): so sánh `Point`, `GeoJsonPoint` và `NearQuery`.
- Spring Data MongoDB — [NearQuery API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/query/NearQuery.html): builder, metric conversion và result units.
- Spring Data MongoDB — [Repository Geo-spatial Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): derived Near methods và loại kết quả.
- Spring Data MongoDB — [MongoOperations API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/MongoOperations.html): ghi chú deprecation của `geoNear(...)`.
- Spring Data MongoDB — [ReactiveMongoOperations API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/ReactiveMongoOperations.html): lựa chọn aggregation cho reactive access.
- Testcontainers — [MongoDB module](https://java.testcontainers.org/modules/databases/mongodb/): thiết lập database test tương thích.

### 33.1. Ghi chú phiên bản

- MongoDB 4.2 loại bỏ command `geoNear` cũ; API Spring Data `geoNear(...)` tương thích dùng aggregation, nhưng đã deprecated và khuyến nghị `Aggregation.geoNear`.
- MongoDB 7.2 cho phép một số constant expressions ở `$geoNear.maxDistance`/`minDistance`; ví dụ trong bài luôn dùng numeric literal để dễ áp dụng nhiều phiên bản.
- MongoDB 8.0 kiểm tra nghiêm ngặt hơn kiểu `Point` của GeoJSON near input; luôn dùng GeoJSON Point hợp lệ.
- MongoDB 8.1 có thể cho phép bỏ `distanceField` với một số collection thường, nhưng bài vẫn khai báo để giữ output contract.
- Spring Data `NearQuery.maxDistance(double)` diễn giải numeric theo metric đã được gắn trước đó nếu có; **không trộn giá trị mét đã chuẩn hóa với metric KILOMETERS không chủ đích**.

Không tự suy những thay đổi mới hơn của database/driver mà chưa đối chiếu release notes. Khi nâng cấp Spring Boot/Spring Data hoặc MongoDB server, chạy lại các integration tests về đơn vị và query plan.

## 34. Tổng kết: mỗi khoảng cách cần mang theo đơn vị

1. **GeoJSON Point chứa longitude/latitude theo độ**, không phải mét hoặc radian. Thứ tự là `[longitude, latitude]`.
2. **GeoJSON `$near`, `$nearSphere`, `$geoNear`** nhận bán kính/giới hạn theo **mét** trong các ví dụ địa lý đã trình bày.
3. **Legacy spherical query** có thể nhận giới hạn và trả khoảng cách raw theo **radian**, đòi hỏi phép đổi `distance / Earth radius`.
4. **`$centerSphere` luôn dùng bán kính radian** trong cấu trúc `$geoWithin` của nó, kể cả với data lưu GeoJSON.
5. **`distanceMultiplier` chỉ nhân các khoảng cách output** của `$geoNear`; nó không chuyển `maxDistance`. Với raw GeoJSON meters muốn trả km, dùng multiplier `0.001`.
6. **Spring Data `Point` và `GeoJsonPoint` không đồng nhất về serialization/đơn vị** trong geospatial queries; `Distance`/`Metrics` cần được dùng nhất quán và test.
7. **Ưu tiên `Aggregation.geoNear` cho mã mới**, giữ `distanceField` có tên chứa đơn vị và giới hạn kết quả rõ.
8. **Type-safe wrapper Meters, unit-named DTO và input validation** giảm lỗi nhân/chia 1000, miles-to-meters hoặc đổi đơn vị hai lần.
9. **Index 2dsphere, tenant filter, limit và explain** bảo đảm hiệu năng và quyền truy cập; correct unit không tự giải quyết vấn đề query plan.
10. **Kiểm thử trên MongoDB thật** với fixtures bên trong/bên ngoài radius, so membership và distance output trước/sau multiplier; unit test thuần không thay thế integration test.
11. Khoảng cách trong truy vấn không gian là **đường chim bay theo mô hình hình học**, không phải ETA, quãng đường giao thông hoặc một độ chính xác GPS tuyệt đối.

**Kết luận:** Muốn một API “tìm gần 2 km” đáng tin cậy, đừng chỉ truyền một số `2`. Hãy định nghĩa vị trí, dạng GeoJSON hay legacy, đơn vị radius trước khi gọi MongoDB, hệ số của distance output và đơn vị response; đồng thời xác minh bằng integration tests và explain. Đó là nền tảng để geospatial search của Spring Data MongoDB hoạt động chính xác, có thể kiểm chứng và dễ bảo trì.







