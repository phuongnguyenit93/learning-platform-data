# $geoNear trong aggregation

Khi xây dựng tính năng **“tìm cửa hàng gần vị trí của khách hàng”**, ứng dụng không chỉ cần lọc những document nằm trong một vùng địa lý, mà còn muốn **tính khoảng cách, sắp xếp từ gần đến xa, lọc theo loại cửa hàng, trạng thái hoạt động và giới hạn số kết quả**. MongoDB cung cấp aggregation stage **`$geoNear`** để xử lý những yêu cầu đó bằng geospatial index.

Trong **Spring Data MongoDB**, có thể xây stage này qua `Aggregation.geoNear(NearQuery, String)` rồi thực thi bằng `MongoTemplate.aggregate(...)` hoặc `ReactiveMongoTemplate.aggregate(...)`. Điều quan trọng là hiểu đúng **GeoJSON, thứ tự kinh độ/vĩ độ, `2dsphere` index, đơn vị đo và vị trí bắt buộc của stage** trước khi lắp các phép `$limit`, `$project`, `$group` hoặc các phép tổng hợp khác.

Bài thuộc chương **Truy vấn không gian** của module `SPRING_DATA_MONGODB`. Module thực hành kết nối, ánh xạ document và thao tác MongoDB qua template hoặc repository, truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu. Chủ đề cụ thể là **`$geoNear` trong aggregation**: từ cú pháp MongoDB Server đến cách biểu diễn, chạy và kiểm chứng bằng Spring Data.

> **Nguyên tắc cần nhớ:** `$geoNear` trả documents **theo khoảng cách tăng dần**, yêu cầu **geospatial index** và phải nằm **đầu pipeline**. Với `near` là GeoJSON Point và `2dsphere` index, `maxDistance`, `minDistance` và `distanceField` dùng **mét** nếu không áp thêm `distanceMultiplier`. Để giới hạn tenant/category, đưa điều kiện vào **`$geoNear.query`** thay vì đặt `$match` trước `$geoNear`.

## 1. Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Phân biệt `$geoNear` với `$near`/`$nearSphere`, `$geoWithin` và `$geoIntersects`.
2. Giải thích vì sao `$geoNear` là stage đầu tiên trong pipeline của collection đang xét.
3. Chuẩn hóa vị trí theo GeoJSON `{ type: "Point", coordinates: [longitude, latitude] }`.
4. Kiểm tra dải hợp lệ: kinh độ từ −180 đến 180 và vĩ độ từ −90 đến 90.
5. Tạo và xác minh `2dsphere` index trước khi chạy truy vấn.
6. Nắm các tùy chọn `near`, `key`, `distanceField`, `includeLocs`, `query`, `minDistance`, `maxDistance`, `spherical` và `distanceMultiplier`.
7. Giải thích chính xác đơn vị đo **mét**, **kilômét** và **radian** trong GeoJSON và legacy coordinates.
8. Xây pipeline shell tìm cửa hàng gần một điểm, lọc tenant/category/active, giới hạn và project DTO.
9. Sử dụng `GeoJsonPoint`, `NearQuery` và `Aggregation.geoNear` của Spring Data MongoDB.
10. Biết cách chọn một geospatial index qua `GeoNearOperation.useIndex(...)`.
11. Hiểu mapping giữa Java field và BSON field khi dùng `@Field` hoặc typed aggregation.
12. Dùng `MongoTemplate.aggregate(...)` để trả document/DTO có field khoảng cách.
13. Sử dụng `ReactiveMongoTemplate.aggregate(...)` và hiểu lazy subscription.
14. Nhận ra khác biệt giữa `distanceField` và `distanceMultiplier` cùng các phép đổi đơn vị.
15. Hiểu thứ tự gần-xa, giới hạn số lượng, vấn đề ties, sort và pagination.
16. Tích hợp thống kê theo khoảng cách bằng `$group`, `$bucket`, `$addFields` và `$project`.
17. Xử lý collection có nhiều trường vị trí, nhiều geospatial indexes và document có nhiều locations.
18. Thiết kế truy vấn an toàn cho multi-tenant, validated coordinates và giới hạn bán kính.
19. Phân biệt độ gần tính theo mặt cầu với **thời gian/khoảng cách đường đi thực tế**.
20. Kiểm thử trên MongoDB thật, xem `explain`, quan sát hiệu năng và chẩn đoán các lỗi thường gặp.

## 2. $geoNear giải quyết vấn đề nào?

Giả sử một collection `geo_stores` có cửa hàng:

```javascript
{
  _id: "STORE-001",
  tenantId: "tenant-a",
  name: "Store Alpha",
  category: "COFFEE",
  active: true,
  location: {
    type: "Point",
    coordinates: [106.7005, 10.7754]
  }
}
```

Client gửi điểm tìm kiếm `[106.7000, 10.7750]` và bán kính 2.000 mét. Một API hữu ích phải trả được:

| Thuộc tính kết quả | Vì sao cần |
| --- | --- |
| `name`, `category` | Hiển thị thông tin cửa hàng |
| `distanceMeters` | Khoảng cách xấp xỉ theo hình học địa cầu |
| Thứ tự từ gần đến xa | Hiển thị lựa chọn liên quan nhất |
| `tenantId` + `active` | Tránh đọc nhầm dữ liệu tenant hoặc cửa hàng ngưng hoạt động |
| Giới hạn 10–20 rows | Bảo vệ API và UI |
| Vị trí sử dụng để tính toán | Hữu ích nếu một document có nhiều địa điểm |

MongoDB `$geoNear` có thể thực hiện phần tìm theo khoảng cách dựa trên geospatial index, thêm `distanceMeters` vào kết quả và sắp xếp tăng dần. Các stage sau có thể chọn fields, đặt giới hạn hoặc tổng hợp.

### 2.1. Không nhầm `$geoNear` với tuyến đường

Khoảng cách từ `$geoNear` là **khoảng cách hình học** theo semantics địa lý, không phải quãng đường ô tô/đi bộ thực tế, không phản ánh tắc đường, cầu, đường một chiều hoặc thời gian di chuyển. Nếu sản phẩm cần ETA hoặc đường đi, phải tích hợp dịch vụ routing phù hợp sau khi lọc các ứng viên bằng `$geoNear`.

## 3. So sánh $geoNear với các toán tử geospatial khác

| Cơ chế | Phạm vi sử dụng | Kết quả có khoảng cách? | Thứ tự gần-xa? |
| --- | --- | --- | --- |
| `$geoNear` | **Aggregation stage** | **Có**, thêm field tính toán | **Có**, mặc định |
| `$near` | Query predicate trên location | Thường không trả field distance riêng | Có, query có ngữ nghĩa gần-xa |
| `$nearSphere` | Query predicate | Không tự thêm distance field như aggregation | Có |
| `$geoWithin` | Chọn các hình/điểm nằm trong vùng | Không tự thêm khoảng cách | Không bắt buộc |
| `$geoIntersects` | Chọn các hình học giao nhau | Không tự thêm khoảng cách | Không bắt buộc |

Ví dụ `$geoWithin` có thể đủ nếu chỉ hỏi “có nằm trong khu vực phục vụ không?”. Nhưng nếu cần **distance field để hiển thị, phân nhóm, biến đổi và tổng hợp trong pipeline**, `$geoNear` phù hợp hơn.

`$near` thường là query predicate trong `find`. Không được đặt `$near` bên trong `$geoNear.query`: MongoDB cấm near predicate lồng như vậy.

### 3.1. `MongoTemplate.geoNear` và aggregation hiện đại

MongoDB đã bỏ **`geoNear` command** cũ từ MongoDB 4.2. Spring Data MongoDB 2.2 trở lên triển khai các geoNear operations dựa trên **`$geoNear` aggregation stage** thay vì command cũ. Tài liệu Spring Data khuyến nghị sử dụng trực tiếp `Aggregation.geoNear(NearQuery, String)`, vì nó cho phép nối tiếp các stage khác trong một pipeline. Tránh sao chép ví dụ MongoDB `db.runCommand({ geoNear: ... })` cũ. 

## 4. Dữ liệu vị trí: GeoJSON Point và thứ tự tọa độ

GeoJSON Point có dạng:

```json
{
  "type": "Point",
  "coordinates": [106.7005, 10.7754]
}
```

Thứ tự **luôn là [longitude, latitude]** trong ví dụ tọa độ địa lý chuẩn, tức **kinh độ trước, vĩ độ sau**.

| Thành phần | Ý nghĩa | Dải hợp lệ |
| --- | --- | --- |
| `coordinates[0]` | Longitude/kinh độ | −180 đến 180 |
| `coordinates[1]` | Latitude/vĩ độ | −90 đến 90 |

Không hoán đổi thành `[latitude, longitude]` vì nhiều thư viện bản đồ/UI hay biểu diễn dữ liệu theo cặp `(lat, lng)`. MongoDB GeoJSON expects `[lng, lat]`. Hai số bị đảo có thể vẫn nằm trong dải hợp lệ và trả ra một địa điểm cách rất xa, không có exception.

### 4.1. Vì sao dùng GeoJSON thay vì mảng legacy?

MongoDB còn hỗ trợ legacy coordinate pairs:

```javascript
locationLegacy: [106.7005, 10.7754]
```

Nhưng chúng đi kèm những quy tắc đơn vị và index khác. Với ứng dụng mới lưu vị trí trên địa cầu, nên ưu tiên `GeoJSON Point` + `2dsphere`. Trong bài này, **mọi ví dụ mới dùng GeoJSON** trừ khi ghi rõ “legacy”.

### 4.2. GeoJSON Point khác Polygon

Một document có thể chứa GeoJSON `Point`, `MultiPoint`, `LineString` hoặc `Polygon` tùy mô hình. `$geoNear` tính khoảng cách đến phần hình học gần nhất theo server semantics; với vùng/polygon, “khoảng cách đến tâm” không mặc nhiên là distance được trả.

Từ MongoDB 8.0, tham số **GeoJSON `near`** được kiểm tra có `type: "Point"`; đừng truyền `Polygon` hay `MultiPoint` làm tâm tìm kiếm. Index `2dsphere` vẫn hỗ trợ những hình học phù hợp khác trong dữ liệu theo quy tắc MongoDB.

## 5. Chuẩn bị bộ dữ liệu minh họa

Trên **database test** (không chạy lệnh này ở production), tạo collection `geo_stores` và một vài điểm giả lập:

```javascript
use geo_training

db.geo_stores.insertMany([
  {
    _id: "STORE-001",
    tenantId: "tenant-a",
    name: "Store Alpha",
    category: "COFFEE",
    active: true,
    location: { type: "Point", coordinates: [106.7005, 10.7754] }
  },
  {
    _id: "STORE-002",
    tenantId: "tenant-a",
    name: "Store Beta",
    category: "COFFEE",
    active: true,
    location: { type: "Point", coordinates: [106.7100, 10.7780] }
  },
  {
    _id: "STORE-003",
    tenantId: "tenant-a",
    name: "Store Gamma",
    category: "BOOK",
    active: true,
    location: { type: "Point", coordinates: [106.7050, 10.7800] }
  },
  {
    _id: "STORE-004",
    tenantId: "tenant-a",
    name: "Store Delta",
    category: "COFFEE",
    active: false,
    location: { type: "Point", coordinates: [106.6990, 10.7740] }
  },
  {
    _id: "STORE-005",
    tenantId: "tenant-b",
    name: "Store Other Tenant",
    category: "COFFEE",
    active: true,
    location: { type: "Point", coordinates: [106.7001, 10.7751] }
  }
])
```

Đây là **điểm giả định để học cú pháp**, không phải vị trí hay tên cơ sở kinh doanh được xác minh. Các ID dùng chữ `STORE-...` nhằm tránh chuyển đổi ID chuỗi 24-hex sang ObjectId trong một số đường mapping Spring Data.

### 5.1. Chọn test database/collection rõ ràng

`$geoNear` chỉ hoạt động trên collection có geospatial index đúng. Nếu collection được dùng bởi nhiều ứng dụng, hãy provision index bằng migration/management job có kiểm soát thay vì tạo index mỗi HTTP request.

## 6. Tạo 2dsphere index đúng trước khi query

MongoDB shell:

```javascript
db.geo_stores.createIndex(
  { location: "2dsphere" },
  { name: "location_2dsphere" }
)

db.geo_stores.getIndexes()
```

`2dsphere` index được dùng cho dữ liệu vị trí trên mặt cầu và GeoJSON. Nếu chưa có index, `$geoNear` sẽ thất bại; nó không được MongoDB tự thay bằng quét collection rồi tính khoảng cách trong Java.

### 6.1. 2d và 2dsphere

| Index | Dạng dữ liệu chính | Hình học |
| --- | --- | --- |
| `2dsphere` | GeoJSON và một số legacy locations theo quy tắc | Địa lý mặt cầu |
| `2d` | Legacy coordinate pairs | Tọa độ phẳng/legacy use cases |

Với `near` là GeoJSON Point, cần dùng một **`2dsphere` geospatial index** tương thích trên trường cần tìm. Một `2d` index trên legacy field không thay thế được index đúng cho trường GeoJSON.

### 6.2. Spring Data annotation chỉ là mô tả index

Trên entity có thể viết:

```java
@GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
private GeoJsonPoint location;
```

Nhưng Spring Data MongoDB **tắt tự động tạo index theo mặc định từ phiên bản 3.0**. Đừng nghĩ thêm `@GeoSpatialIndexed` là MongoDB đã có index. Hãy dùng index migration hoặc `IndexOperations` có chủ đích và kiểm tra bằng `getIndexes()`.

## 7. Cú pháp $geoNear đầy đủ

Một stage MongoDB có các tùy chọn quan trọng:

```javascript
{
  $geoNear: {
    near: {
      type: "Point",
      coordinates: [106.7000, 10.7750]
    },
    key: "location",
    distanceField: "distanceMeters",
    maxDistance: 2000,
    minDistance: 0,
    query: {
      tenantId: "tenant-a",
      active: true
    },
    spherical: true,
    includeLocs: "matchedLocation"
  }
}
```

| Tùy chọn | Công dụng | Ghi chú |
| --- | --- | --- |
| `near` | Tâm tìm kiếm | GeoJSON Point hoặc legacy coordinate pair |
| `key` | Trường geospatial được index dùng để tính | Nên chỉ rõ, bắt buộc khi mơ hồ nhiều indexes; time series cũng cần |
| `distanceField` | Field chứa khoảng cách tính ra | Nên luôn khai báo; bắt buộc với nhiều server versions và time series |
| `maxDistance` | Khoảng cách tối đa | **Mét** với GeoJSON Point |
| `minDistance` | Khoảng cách tối thiểu | **Mét** với GeoJSON Point |
| `query` | Bộ lọc các documents được xét | Không chứa `$near` |
| `spherical` | Tính theo hình học mặt cầu | `true` cho ví dụ địa lý |
| `includeLocs` | Ghi lại vị trí được sử dụng để tính khoảng cách | Hữu ích khi một document có nhiều vị trí |
| `distanceMultiplier` | Hệ số nhân **distance output** | Không tự đổi đơn vị ngưỡng lọc |

**Lưu ý phiên bản:** từ MongoDB 8.1, `distanceField` có thể không còn bắt buộc với collection thông thường, nhưng vẫn bắt buộc trên **time series collection**. Để tương thích và dễ mapping, bài này luôn khai báo `distanceField`.

### 7.1. “key” không phải tên của index

Trong `$geoNear`, `key: "location"` là **đường dẫn field có index**, không phải tên vật lý của index như `location_2dsphere`. Với Spring Data, `GeoNearOperation.useIndex("location")` cũng nhận **field path**.

### 7.2. Có được dùng $geoNear không có distanceField?

Chỉ với các server/version và collection types hỗ trợ. Đừng dựa vào tùy chọn bỏ field đó nếu ứng dụng phải chạy MongoDB 7.x/8.0 hoặc time series. Luôn chọn field rõ ràng giúp code kiểm thử và DTO ổn định.

## 8. Quy tắc đầu tiên trong pipeline

MongoDB yêu cầu `$geoNear` **là stage đầu tiên của pipeline mà nó nằm trong**:

```javascript
// ĐÚNG:
db.geo_stores.aggregate([
  { $geoNear: { /* near, key, distanceField... */ } },
  { $limit: 10 },
  { $project: { name: 1, distanceMeters: 1 } }
])
```

Không hợp lệ:

```javascript
// SAI: $match đứng trước $geoNear.
db.geo_stores.aggregate([
  { $match: { tenantId: "tenant-a" } },
  { $geoNear: { /* ... */ } }
])
```

Dù `$match` có thể lọc rất nhanh, bạn **không được** đặt nó trước `$geoNear`. Hãy dùng `$geoNear.query` để đẩy tenant/active/category predicates vào ngay stage đầu.

### 8.1. $geoNear trong $lookup subpipeline

`$geoNear` có thể xuất hiện **đầu một subpipeline** được phép, ví dụ trong `$lookup.pipeline` với các điều kiện server hỗ trợ. “Stage đầu” áp dụng **cho chính pipeline/subpipeline ấy**, không chỉ một pipeline cấp cao nhất trong toàn command. Hãy kiểm tra các ràng buộc của `$lookup`/`let` và version MongoDB nếu triển khai truy vấn tương quan.

### 8.2. $search cũng có yêu cầu stage đầu

Nếu cần kết hợp full-text search (nhất là Atlas Search) và geospatial distance, không thể đơn giản đặt hai stages đều yêu cầu vị trí đầu vào cùng một pipeline. Cần chọn truy vấn dẫn đầu, kết hợp điều kiện trong stage thích hợp hoặc thiết kế hai pha. Không tự ghép `$search` rồi `$geoNear` và mong server chấp nhận.

## 9. Truy vấn thực tế bằng MongoDB shell

Tìm tối đa 10 cửa hàng `COFFEE` đang hoạt động trong bán kính 2 km, thuộc tenant `tenant-a`:

```javascript
db.geo_stores.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7750]
      },
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 2000,
      spherical: true,
      query: {
        tenantId: "tenant-a",
        category: "COFFEE",
        active: true
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      _id: 1,
      name: 1,
      category: 1,
      distanceMeters: 1,
      location: 1
    }
  }
])
```

Kết quả là những documents hợp lệ theo `query`, có field `distanceMeters` được MongoDB tính và sắp xếp từ gần đến xa. Giá trị chính xác tùy tọa độ và hình học, nên không gán một con số “đã đo” nếu chưa chạy trên MongoDB thật.

### 9.1. Vì sao lọc tenant ngay trong $geoNear.query?

Đưa `tenantId` vào `query` bảo đảm **chỉ xem các documents thuộc tenant được phép** ngay từ geospatial search. Nếu chỉ filter tenant sau `$limit`, 10 kết quả gần nhất có thể đến từ tenant khác và số cửa hàng hợp lệ còn lại bị thiếu. Nếu cố lộ data ra application rồi mới lọc, còn tăng rủi ro an toàn thông tin.

### 9.2. Vì sao limit ngay sau $geoNear?

Stage `$geoNear` đã trả theo khoảng cách tăng dần. Khi API chỉ cần 10 ứng viên gần nhất, `$limit:10` ngay sau đó tránh gửi/biến đổi thêm quá nhiều records. Không đặt `$limit` **trước** stage geospatial. Nếu cần thêm lọc sau `$geoNear`, hãy hiểu rằng vị trí của `$limit` có thể thay đổi tập kết quả.

## 10. minDistance và maxDistance: tạo vùng vành khăn

Để tìm các cửa hàng nằm từ 500 đến 2.000 mét cách tâm:

```javascript
db.geo_stores.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7750]
      },
      key: "location",
      distanceField: "distanceMeters",
      minDistance: 500,
      maxDistance: 2000,
      spherical: true,
      query: { tenantId: "tenant-a", active: true }
    }
  },
  { $limit: 20 }
])
```

Đây là **vùng khoảng cách hình học** (một vành quanh tâm), không phải vùng phục vụ theo đường đi. Đừng dùng ngưỡng âm, NaN, Infinity hoặc `minDistance > maxDistance`. Validate inputs trước khi tạo pipeline để API có thông báo lỗi rõ.

### 10.1. maxDistance không tự có giới hạn nếu bỏ trống

Khi không có `maxDistance` và không có `$limit`, geospatial search có thể trả về lượng lớn documents, gây tốn CPU/index work, network, mapping và thời gian HTTP request. Đặt giới hạn bán kính và số kết quả theo product requirements; không để caller tự yêu cầu bán kính vô hạn.

## 11. distanceField, includeLocs và distanceMultiplier

### 11.1. distanceField

`distanceField` là tên field được thêm vào mỗi kết quả. Có thể dùng dotted field path:

```javascript
{
  $geoNear: {
    near: { type: "Point", coordinates: [106.7000, 10.7750] },
    key: "location",
    distanceField: "geo.distanceMeters",
    spherical: true
  }
}
```

Kết quả sẽ có dạng `geo: { distanceMeters: ... }` nếu không xung đột với cấu trúc có sẵn. Không chọn tên trùng field nghiệp vụ quan trọng vì `$geoNear` có thể tạo hoặc thay đổi dữ liệu output ở field path đó.

### 11.2. includeLocs

Giả sử một document chứa nhiều vị trí (ví dụ nhiều điểm giao nhận). `includeLocs: "geo.nearestPoint"` cho biết **vị trí mà MongoDB dùng để tính distance**, thay vì application tự đoán trong array. Trường này chỉ là output bổ sung; nó không thay đổi việc index nào được chọn.

### 11.3. distanceMultiplier

Với GeoJSON Point, distance output cơ bản là **mét**. Nếu muốn hiển thị **kilômét**, có thể nhân với `0.001`:

```javascript
db.geo_stores.aggregate([
  {
    $geoNear: {
      near: { type: "Point", coordinates: [106.7000, 10.7750] },
      key: "location",
      distanceField: "distanceKm",
      maxDistance: 2000,
      distanceMultiplier: 0.001,
      spherical: true
    }
  },
  { $limit: 10 }
])
```

**Cực kỳ quan trọng:** `maxDistance:2000` vẫn là **2.000 mét**; `distanceMultiplier:0.001` chỉ đổi **output field** thành km, không đổi ngưỡng thành 2.000 km. Nếu không muốn dùng multiplier, giữ field `distanceMeters` và nhân cho display ở stage `$set` hoặc code Java theo một policy rõ ràng.

## 12. GeoJSON và legacy: sự khác biệt về đơn vị

Spring Data `NearQuery` nhấn mạnh sự khác biệt giữa `new GeoJsonPoint(lng,lat)` và `new Point(lng,lat)`. Dù cùng các tọa độ, cú pháp BSON và native distance units khác nhau.

| Kiểu near | Hình học/index | `maxDistance` và `distanceField` mặc định |
| --- | --- | --- |
| GeoJSON `Point` | `2dsphere` | **Mét** |
| Legacy pair `[lng,lat]` với spherical | `2dsphere` | **Radian** khi không dùng metric/multiplier |
| Legacy pair với `2d` | Phẳng | Đơn vị tọa độ của hệ 2D |

Với legacy spherical, xấp xỉ `distanceMeters = distanceRadians × 6_371_000`, nhưng **không tự đổi một lần nữa nếu đã dùng `Metrics.KILOMETERS`/`Distance` của Spring Data**. Hệ số `distanceMultiplier:6378.137` trong nhiều ví dụ legacy là cách chuyển **radian sang km**, không phù hợp cho **GeoJSON mét sang km** (trường hợp đó dùng `0.001`).

**Quy ước nhất quán của bài này:** GeoJSON Point cho cả lưu trữ và `near`; tất cả radius/input/output cơ bản là **mét**; không đặt distanceMultiplier ngầm. Nếu API muốn km, đổi đơn vị rõ ở projection hoặc DTO và kiểm thử ngưỡng.

## 13. Ánh xạ entity Java với GeoJsonPoint

Spring Data MongoDB cung cấp `org.springframework.data.mongodb.core.geo.GeoJsonPoint`. Một record cho ví dụ:

```java
package dev.learning.geo;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("geo_stores")
public record Store(
    @Id String id,
    String tenantId,
    String name,
    String category,
    boolean active,
    GeoJsonPoint location
) {
}
```

Tạo điểm Java:

```java
GeoJsonPoint p = new GeoJsonPoint(106.7005, 10.7754);
Store shop = new Store(
    "STORE-010", "tenant-a",
    "Store Sample", "COFFEE", true, p
);

mongoTemplate.insert(shop);
```

Constructor `GeoJsonPoint(x, y)` đặt **longitude trước latitude**, giống GeoJSON `[lng,lat]`. Mapped BSON của `location` phải có `type: "Point"` và `coordinates` đúng thứ tự.

### 13.1. Java property khác tên BSON

Nếu entity dùng `@Field("tenant_id") String tenantId`, BSON sẽ có `tenant_id`. Raw MongoDB shell cần `tenant_id`; typed Spring Data aggregation/mapping thông thường sẽ dùng mapping context để xử lý Java property names. Tránh trộn tên Java và BSON khi viết một `AggregationOperation` custom chứa raw `Document`; dùng integration test và command monitoring để kiểm chứng query thực tế.

## 14. Provision geospatial index qua MongoTemplate

Tạo một index `2dsphere` có chủ đích bằng `IndexOperations`:

```java
package dev.learning.geo;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.index.GeospatialIndex;

public final class StoreIndexProvisioner {

    private StoreIndexProvisioner() {}

    public static String ensureIndex(MongoTemplate mongoTemplate) {
        return mongoTemplate.indexOps(Store.class).ensureIndex(
            new GeospatialIndex("location")
                .typed(GeoSpatialIndexType.GEO_2DSPHERE)
                .named("location_2dsphere")
        );
    }
}
```

Dùng trong **migration/startup hoặc test fixture**, không gọi cho từng request. Mặc dù có thể khai báo `@GeoSpatialIndexed(type=GEO_2DSPHERE)` trên property, **tự tạo index mặc định đã tắt từ Spring Data MongoDB 3.0**, do đó annotation không đủ để bảo đảm index tồn tại.

Kiểm tra bằng `db.geo_stores.getIndexes()`. Trong môi trường thực, lập migration/rollout index dưới quyền quản trị phù hợp; nếu dữ liệu địa lý bị lỗi, việc xây index có thể thất bại.

## 15. NearQuery: near, query, maxDistance

`NearQuery` thuộc package `org.springframework.data.mongodb.core.query`. Dựng một yêu cầu trong bán kính 2.000 mét:

```java
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.NearQuery;
import org.springframework.data.mongodb.core.query.Query;

GeoJsonPoint center = new GeoJsonPoint(106.7000, 10.7750);

Query filter = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("category").is("COFFEE")
        .and("active").is(true)
);

NearQuery near = NearQuery.near(center)
    .spherical(true)
    .maxDistance(2000.0)
    .query(filter);
```

- `near(center)` dùng **GeoJSON Point**, nên ngưỡng `2000` được hiểu là **mét** trong ví dụ không đổi metric.
- `spherical(true)` biểu diễn chủ đích tính theo hình học mặt cầu.
- `query(filter)` tạo `query` bên trong `$geoNear`: lọc tenant, active và category **trước khi giới hạn kết quả**.
- Không đặt `$near` trong `NearQuery.query(...)`; MongoDB không hỗ trợ lồng hai near predicates.

### 15.1. Dùng Metrics có chủ đích

`NearQuery` có `maxDistance(Distance)`, `minDistance(Distance)`, `inKilometers()`, `inMiles()` và các API liên quan đến `Metric`. Một số lựa chọn vừa quy đổi bán kính, vừa cấu hình output multiplier. Để tránh đổi đôi hay dùng nhầm radian, chọn **một quy ước** cho API/test; ví dụ này luôn dùng mét và `GeoJsonPoint`, không gọi `inKilometers()`.

### 15.2. Read preference không sửa geometry

`NearQuery` hỗ trợ `withReadPreference`/`withReadConcern` ở các phiên bản Spring Data tương ứng. Đây là tùy chọn nhất quán và chọn MongoDB node, **không** thay đổi giá trị distance hay thay thế geospatial index.

## 16. Aggregation.geoNear(NearQuery, String)

Spring Data khuyến nghị static factory `Aggregation.geoNear(...)` thay vì trực tiếp dựng một `GeoNearOperation`. Ví dụ:

```java
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.GeoNearOperation;

GeoNearOperation operation = Aggregation
    .geoNear(near, "distanceMeters")
    .useIndex("location");
```

`"distanceMeters"` là output field. `useIndex("location")` tương ứng với `key: "location"` trong MongoDB và nhận **field path**, không phải tên vật lý `location_2dsphere` của index.

### 16.1. TypedAggregation với limit và projection

```java
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;

TypedAggregation<Store> aggregation =
    Aggregation.newAggregation(
        Store.class,
        Aggregation.geoNear(near, "distanceMeters")
            .useIndex("location"),
        Aggregation.limit(10),
        Aggregation.project(
            "name", "category", "location", "distanceMeters")
    );
```

Tất cả các stage khác phải đứng **sau** `geoNear` trong aggregation pipeline này. Không đặt `Aggregation.match(...)` trước nó:

```java
// KHÔNG HỢP LỆ với MongoDB:
Aggregation.newAggregation(
    Aggregation.match(Criteria.where("tenantId").is("tenant-a")),
    Aggregation.geoNear(near, "distanceMeters")
);
```

Lọc tenant trong `NearQuery.query(filter)` từ đầu là cách phù hợp.

### 16.2. Typed mapping vẫn cần kiểm tra

`TypedAggregation<Store>` giúp Spring Data ánh xạ domain fields. Nếu bạn dùng `@Field("tenant_id")` hoặc nested `location.geo`, kiểm tra stage BSON được render ở version Spring Data thực tế. Những custom raw `Document` stages có thể yêu cầu dùng BSON field names thay vì dựa vào mapping tự động.

## 17. MongoTemplate.aggregate và DTO kết quả

Thực thi pipeline và quan sát các fields:

```java
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;

AggregationResults<Document> results =
    mongoTemplate.aggregate(
        aggregation, "geo_stores", Document.class);

List<Document> rows = results.getMappedResults();

for (Document row : rows) {
    Number distance = row.get("distanceMeters", Number.class);
    System.out.println(row.getString("name")
        + " -> " + distance + " m");
}
```

`mongoTemplate` là bean Spring Data đã được inject; `aggregation` là typed pipeline ở mục 16. Dùng `Number` để đọc distance vì conversion/type thực tế có thể khác trong một số custom pipelines.

Public API nên dùng DTO:

```java
package dev.learning.geo;

public record NearbyStoreDto(
    String id, String name, String category, double distanceMeters
) {
}
```

Có thể map kết quả:

```java
List<NearbyStoreDto> payload = rows.stream()
    .map(doc -> new NearbyStoreDto(
        doc.getString("_id"),
        doc.getString("name"),
        doc.getString("category"),
        doc.get("distanceMeters", Number.class)
            .doubleValue()
    ))
    .toList();
```

Trong ví dụ, `_id` là **String** như `STORE-001`. Nếu collection dùng `ObjectId`, ánh xạ đúng thay vì ép `getString("_id")`. `Aggregation.project(...)` ở trên vẫn để `_id` theo mặc định; nếu chủ động exclude ID phải thay đổi DTO mapping tương ứng.

### 17.1. Không trả tài liệu nội bộ cho client

Một result từ `$geoNear` có thể vẫn chứa toàn bộ document ban đầu nếu không `$project`. Luôn giới hạn fields trả ra và tránh rò rỉ `tenantId`, thông tin nội bộ hoặc vị trí chính xác ngoài quyền truy cập.

## 18. Service hoàn chỉnh: kiểm soát tọa độ và tài nguyên

Ví dụ service chỉ chấp nhận **tọa độ hợp lệ**, radius tối đa 20 km và limit tối đa 20; tenant ID đến từ security boundary đã xác thực.

```java
package dev.learning.geo;

import java.util.List;
import org.bson.Document;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.NearQuery;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class NearbyStoreService {

    private final MongoTemplate template;

    public NearbyStoreService(MongoTemplate template) {
        this.template = template;
    }

    public List<NearbyStoreDto> search(
            String authorizedTenantId,
            double lon,
            double lat,
            double radiusMeters,
            String category,
            int limit) {

        if (!Double.isFinite(lon) || lon < -180 || lon > 180
                || !Double.isFinite(lat) || lat < -90 || lat > 90) {
            throw new IllegalArgumentException("Tọa độ không hợp lệ");
        }
        if (!Double.isFinite(radiusMeters)
                || radiusMeters <= 0 || radiusMeters > 20_000) {
            throw new IllegalArgumentException(
                "Radius phải thuộc (0, 20000] mét");
        }
        if (limit < 1 || limit > 20) {
            throw new IllegalArgumentException("Limit thuộc [1, 20]");
        }
        if (authorizedTenantId == null
                || authorizedTenantId.isBlank()) {
            throw new IllegalArgumentException("Thiếu tenant xác thực");
        }

        Query filter = Query.query(
            Criteria.where("tenantId").is(authorizedTenantId)
                .and("category").is(category)
                .and("active").is(true));

        NearQuery near = NearQuery
            .near(new GeoJsonPoint(lon, lat))
            .spherical(true)
            .maxDistance(radiusMeters)
            .query(filter);

        TypedAggregation<Store> pipeline =
            Aggregation.newAggregation(
                Store.class,
                Aggregation.geoNear(near, "distanceMeters")
                    .useIndex("location"),
                Aggregation.limit(limit),
                Aggregation.project(
                    "name", "category", "distanceMeters")
            );

        return template
            .aggregate(pipeline, "geo_stores", Document.class)
            .getMappedResults().stream()
            .map(doc -> new NearbyStoreDto(
                doc.getString("_id"),
                doc.getString("name"),
                doc.getString("category"),
                doc.get("distanceMeters", Number.class)
                    .doubleValue()))
            .toList();
    }
}
```

### 18.1. Category cần validation riêng

Ví dụ tập trung vào tọa độ và radius. Với production API, `category` phải được so với enum/whitelist nghiệp vụ; không cho client gửi raw BSON query, field path, `$where` hoặc aggregation stage. Đặt tenant ID từ authenticated principal, **không** tin tenant do client chọn.

### 18.2. Query field và Java mapping

Nếu property Java tên `tenantId` nhưng BSON field `tenant_id`, dùng typed mapping hoặc trường BSON đúng trong raw custom stage. Khi không chắc, kiểm tra command BSON qua test/driver monitoring, không kết luận chỉ từ tên getter Java.

## 19. ReactiveMongoTemplate: Flux không đổi yêu cầu index

Spring Data reactive dùng cùng aggregation semantics và trả `Flux<Document>`:

```java
import org.bson.Document;
import reactor.core.publisher.Flux;

Flux<NearbyStoreDto> nearby =
    reactiveMongoTemplate
        .aggregate(aggregation, "geo_stores", Document.class)
        .map(doc -> new NearbyStoreDto(
            doc.getString("_id"),
            doc.getString("name"),
            doc.getString("category"),
            doc.get("distanceMeters", Number.class)
                .doubleValue()));
```

Trong WebFlux, return Publisher để framework subscribe; không gọi `block()` hoặc `subscribe()` ẩn trong service. MongoDB reactive Publishers thường **cold/lazy**: subscribe hai lần có thể chạy geospatial query hai lần, tạo thêm tải và thấy dữ liệu thay đổi.

`Flux` không tự giảm chi phí MongoDB: vẫn cần index `2dsphere`, bán kính tối đa, `$limit` và lựa chọn query plan.

## 20. Có nhiều geospatial indexes: dùng key rõ ràng

Nếu collection có `location` và `deliveryHub` đều được index:

```javascript
db.geo_stores.createIndex({ location: "2dsphere" })
db.geo_stores.createIndex({ deliveryHub: "2dsphere" })
```

`$geoNear` có thể lỗi **ambiguous geospatial index** nếu không chỉ rõ field muốn dùng. Cú pháp MongoDB:

```javascript
{
  $geoNear: {
    near: { type: "Point", coordinates: [106.7000, 10.7750] },
    key: "location",
    distanceField: "distanceMeters",
    spherical: true
  }
}
```

Spring Data:

```java
Aggregation.geoNear(near, "distanceMeters")
    .useIndex("location");
```

`key` là **indexed field path**, không phải tên index. Khai báo nó tường minh giúp code không bị mơ hồ khi đội dữ liệu thêm index mới.

### 20.1. includeLocs với nhiều vị trí

Nếu một document chứa **nhiều locations**, `includeLocs` tạo field chứa vị trí mà MongoDB đã dùng để tính khoảng cách. Nó giúp API giải thích kết quả “kho gần nhất” thay vì đoán vị trí nào trong array. Nếu mỗi document chỉ có một `location`, `includeLocs` thường không cần thiết.

## 21. Compound 2dsphere index và multi-tenant

Đối với query thường lọc `tenantId`/`active`, có thể đánh giá compound index:

```javascript
db.geo_stores.createIndex(
  { tenantId: 1, active: 1, location: "2dsphere" },
  { name: "tenant_active_location_geo" }
)
```

MongoDB hỗ trợ compound `2dsphere` index, nhưng không bảo đảm tổ hợp nào cũng nhanh hơn index đơn. Hiệu năng tùy cardinality, data distribution, geospatial selectivity, index ordering, sparse geo behavior và query planner. **Đo `explain`**, không chỉ thêm index và suy đoán.

Records thiếu `location` hoặc chứa `null` sẽ không tự xuất hiện trong `$geoNear` theo hành vi sparse của `2dsphere`. Nếu sản phẩm cần kết quả “chưa biết vị trí”, đó là nhánh dữ liệu riêng.

### 21.1. Chỉ tạo index cần thiết

Mỗi index thêm chi phí lưu trữ và cập nhật; đặc biệt khi cửa hàng đổi tọa độ liên tục. Không xây index cho mọi tổ hợp category/active/tenant mà không xem workload. Dùng migration, `getIndexes()` và executionStats.

## 22. Sắp xếp và phân trang: top-N đơn giản hơn deep skip

`$geoNear` trả kết quả tăng dần theo khoảng cách. Lấy 20 cửa hàng gần nhất:

```javascript
[
  { $geoNear: { /* near, key, query, distanceField... */ } },
  { $limit: 20 }
]
```

Với những documents có khoảng cách bằng nhau, thứ tự nội bộ không nên được xem là ổn định tuyệt đối. Khi API cần tie-breaker có thể thêm:

```javascript
[
  { $geoNear: { /* ... */ } },
  { $sort: { distanceMeters: 1, _id: 1 } },
  { $limit: 20 }
]
```

Tuy nhiên `$sort` sau `$geoNear` có thể phát sinh thêm chi phí; cân nhắc với explain. Nếu cửa hàng/địa điểm thay đổi giữa các requests, `$skip + $limit` dễ có lặp/bỏ kết quả. Keyset pagination theo `distanceMeters` cũng cần xử lý số thực, _id tie-breaker và consistency. Với màn hình bản đồ thông thường, ưu tiên radius + limit rõ ràng thay vì phân trang sâu.

**Không dựa vào giới hạn ngầm 100 documents** của geoNear command cũ: MongoDB hiện đại không còn mặc định `$geoNear` cắt đúng 100 rows. Hãy đặt `$limit` hoặc `NearQuery.limit` có chủ đích.

## 23. Kết hợp $geoNear với $set, $project và $group

`$geoNear` cung cấp field khoảng cách, nên các stage sau có thể dùng khoảng cách ấy để tạo output phục vụ API hoặc phân tích dữ liệu.

### 23.1. Hiển thị km từ khoảng cách mét

```javascript
db.geo_stores.aggregate([
  {
    $geoNear: {
      near: { type: "Point", coordinates: [106.7000, 10.7750] },
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 2000,
      spherical: true,
      query: { tenantId: "tenant-a", active: true }
    }
  },
  { $limit: 20 },
  {
    $set: {
      distanceKm: {
        $divide: ["$distanceMeters", 1000]
      }
    }
  },
  {
    $project: {
      name: 1,
      distanceMeters: 1,
      distanceKm: 1
    }
  }
])
```

Cách này giữ cả `distanceMeters` và `distanceKm` để client có thể hiển thị km nhưng business logic vẫn dùng ngưỡng mét. Nếu đã cấu hình `distanceMultiplier:0.001`, không chia thêm `1000` lần nữa.

### 23.2. Thống kê theo category

```javascript
db.geo_stores.aggregate([
  {
    $geoNear: {
      near: { type: "Point", coordinates: [106.7000, 10.7750] },
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 2000,
      spherical: true,
      query: { tenantId: "tenant-a", active: true }
    }
  },
  {
    $group: {
      _id: "$category",
      storeCount: { $sum: 1 },
      averageDistanceMeters: { $avg: "$distanceMeters" },
      nearestDistanceMeters: { $min: "$distanceMeters" }
    }
  },
  { $sort: { storeCount: -1, _id: 1 } }
])
```

**Thứ tự đầu ra sau `$group` không còn đảm bảo tăng dần theo khoảng cách.** `$group` gộp nhiều documents thành một nhóm và `$sort` cuối xếp theo count/category. Nếu API cần danh sách cửa hàng từ gần đến xa, không thay `$group` vào chỗ của `$limit`/`$project` một cách vô thức.

### 23.3. Phân nhóm theo vành khoảng cách

```javascript
db.geo_stores.aggregate([
  {
    $geoNear: {
      near: { type: "Point", coordinates: [106.7000, 10.7750] },
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 3000,
      spherical: true,
      query: { tenantId: "tenant-a", active: true }
    }
  },
  {
    $bucket: {
      groupBy: "$distanceMeters",
      boundaries: [0, 500, 1000, 2000, 3000],
      default: "outside",
      output: {
        count: { $sum: 1 }
      }
    }
  }
])
```

`$bucket` trả counts theo khoảng distance. Không nhầm histogram này là số điểm nằm trong khoảng cách đường bộ; MongoDB tính hình học theo geospatial semantics.

## 24. Thống kê và danh sách trong một $facet

Khi muốn trả **top gần nhất** và **thống kê theo category** trong một aggregation, có thể đặt `$facet` **sau** `$geoNear`:

```javascript
db.geo_stores.aggregate([
  {
    $geoNear: {
      near: { type: "Point", coordinates: [106.7000, 10.7750] },
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 2000,
      spherical: true,
      query: { tenantId: "tenant-a", active: true }
    }
  },
  {
    $facet: {
      closest: [
        { $limit: 10 },
        { $project: { name: 1, category: 1, distanceMeters: 1 } }
      ],
      byCategory: [
        { $group: { _id: "$category", count: { $sum: 1 } } }
      ]
    }
  }
])
```

`$facet` không thể đứng **trước `$geoNear`** trong ví dụ này; nhánh `closest` được cấp dữ liệu theo khoảng cách từ stage đầu.

### 24.1. Vì sao $facet không phải luôn tốt hơn hai truy vấn?

`$facet` có giới hạn bộ nhớ và có thể phải xử lý nhiều documents trong các nhánh. Nếu phần thống kê cần toàn bộ 100.000 stores trong một bán kính rộng nhưng UI chỉ cần top 10, việc làm hai queries độc lập hoặc cache summary có thể nhanh hơn. Đo `explain`, memory, output size và network thực tế trước khi chọn.

### 24.2. Không đặt $limit trước $facet nếu thống kê toàn bộ

Nếu đặt `$limit:10` giữa `$geoNear` và `$facet`, cả `closest` và `byCategory` chỉ thấy tối đa 10 documents. Hãy xác định **tập ứng viên nào** cần được thống kê trước khi tối ưu pipeline.

## 25. Sử dụng $geoNear với time series và tính năng theo phiên bản

MongoDB hỗ trợ `$geoNear` trên **time series collection** ở các phiên bản server phù hợp, nhưng có hạn chế quan trọng:

- Phải chỉ định `key` cho geospatial field của time series.
- Không thể sử dụng tùy chọn `$geoNear.query` với time series collection.
- `distanceField` vẫn là tùy chọn bắt buộc cho time series ngay cả khi một số MongoDB 8.1+ cho phép bỏ ở collection thường.
- Khả năng tạo `2dsphere` index trên time series và cách field được lưu khác collection bình thường; cần xác minh server version, schema và index thực tế.

Một time series collection lưu tọa độ cảm biến có thể có nhiều records cho một thiết bị. Truy vấn `$geoNear` vẫn tìm **documents/measurements** gần nhất, không tự suy ra “thiết bị gần nhất theo location mới nhất”. Nếu mục tiêu là vị trí mới nhất cho từng device, phải tính tới time filtering/rollup/last-state collection và giới hạn stage.

### 25.1. GeoJSON near type validation

Từ MongoDB 8.0, `$geoNear` với input GeoJSON bắt buộc `type:"Point"` hợp lệ. Truyền dữ liệu `"type":"Polygon"` hoặc một chuỗi JSON không đúng dạng là lỗi input, không phải kết quả rỗng.

### 25.2. $geoNear và let variables

MongoDB hiện đại có thể sử dụng `let`/bound variables để truyền near point trong những bối cảnh aggregation được hỗ trợ (chẳng hạn subpipeline của `$lookup`). Đó là khả năng nâng cao cần đối chiếu server version và chú ý stage order; ví dụ cơ sở của bài cố ý dùng GeoJSON Point trực tiếp để dễ đọc và kiểm thử.

## 26. Query plan, explain và chỉ số hiệu năng

Trên MongoDB test, xem executionStats:

```javascript
db.geo_stores.explain("executionStats").aggregate([
  {
    $geoNear: {
      near: { type: "Point", coordinates: [106.7000, 10.7750] },
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 2000,
      spherical: true,
      query: {
        tenantId: "tenant-a",
        active: true,
        category: "COFFEE"
      }
    }
  },
  { $limit: 20 }
])
```

Các điểm cần xem:

1. Geospatial index nào được dùng (ví dụ tên tương ứng với `location_2dsphere`).
2. Có geospatial stage hay index scan, không rơi vào query plan khác ngoài mong đợi.
3. Số documents/keys examined so với số results trả về.
4. Thời gian execution thực tế và độ ổn định qua các kích thước bán kính.
5. Tác động của `tenantId`, `active` và `category` trong `query`.
6. So sánh index đơn với compound `2dsphere` nếu workload có nhiều tenant.
7. Hiệu ứng thêm `$sort`, `$group`, `$facet` hoặc `$lookup` sau stage đầu.
8. Kích thước payload và thời gian ánh xạ kết quả trong Spring Data.

Tên các stage trong explain có thể thay đổi theo MongoDB version và execution engine; không khóa cứng test vào một tên stage duy nhất nếu không cần. Dùng `getIndexes()` để kiểm tra index đã provision và query profiler/metrics để quan sát production an toàn.

### 26.1. Một index không giải quyết bán kính vô hạn

Ngay cả khi `$geoNear` dùng index, yêu cầu bán kính hàng nghìn km hoặc không có `maxDistance` có thể phải xét rất nhiều vị trí. `$limit` giới hạn output nhưng không hứa mọi phép tính server đều có chi phí cố định. Hãy giới hạn input trước khi chạy aggregation.

### 26.2. Dữ liệu phân bố không đều

Một khu phố đông cửa hàng có thể chứa hàng chục nghìn records trong 1 km, còn vùng thưa có rất ít. Benchmarks phải phản ánh **mật độ, số lượng tenants, phân loại và tỷ lệ location null**, không chỉ kiểm thử 5 documents seed.

### 26.3. Chẩn đoán khi query trả rỗng

Kiểm tra theo thứ tự: center có bị đảo lat/lng? Bán kính là mét hay radian? `tenantId` đúng không? `category`/`active` đúng không? Location có nằm trong geospatial index? Có nhầm collection hoặc database không? Đừng kết luận hệ thống lỗi ngay khi query cho 0 rows.

## 27. Integration test: Spring Data + MongoDB thật

Một test hữu ích phải **tạo index thực**, insert điểm GeoJSON, chạy service và xác minh tenant filtering, distance và thứ tự. Dùng database test riêng (hoặc Testcontainers), không chạy với dữ liệu production.

```java
package dev.learning.geo;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;

@SpringBootTest
class GeoNearIntegrationTest {

    @Autowired MongoTemplate template;
    @Autowired NearbyStoreService service;

    @BeforeEach
    void ensureIndex() {
        StoreIndexProvisioner.ensureIndex(template);
    }

    @Test
    void returnsOnlyAuthorizedActiveNearbyStores() {
        String suffix = UUID.randomUUID().toString();
        String tenant = "tenant-test-" + suffix;

        Store nearest = new Store(
            "NEAR-" + suffix, tenant, "Near Store",
            "COFFEE", true, new GeoJsonPoint(106.7000, 10.7750));

        Store farther = new Store(
            "FARTHER-" + suffix, tenant, "Farther Store",
            "COFFEE", true, new GeoJsonPoint(106.7060, 10.7750));

        Store inactive = new Store(
            "INACTIVE-" + suffix, tenant, "Inactive",
            "COFFEE", false, new GeoJsonPoint(106.7000, 10.7750));

        Store wrongCategory = new Store(
            "BOOK-" + suffix, tenant, "Book",
            "BOOK", true, new GeoJsonPoint(106.7000, 10.7750));

        Store anotherTenant = new Store(
            "OTHER-" + suffix, "other-" + suffix, "Other Tenant",
            "COFFEE", true, new GeoJsonPoint(106.7000, 10.7750));

        template.insertAll(List.of(
            nearest, farther, inactive, wrongCategory, anotherTenant));

        List<NearbyStoreDto> found = service.search(
            tenant, 106.7000, 10.7750, 2000.0, "COFFEE", 20);

        assertThat(found)
            .extracting(NearbyStoreDto::id)
            .containsExactly(nearest.id(), farther.id());

        assertThat(found.get(0).distanceMeters())
            .isBetween(0.0, 2.0);

        assertThat(found.get(1).distanceMeters())
            .isGreaterThan(found.get(0).distanceMeters())
            .isLessThanOrEqualTo(2000.0);
    }
}
```

### 27.1. Vì sao các IDs dùng UUID?

Mỗi lần chạy tạo một tenant và IDs riêng, nên không lẫn records của test khác. Index là tài nguyên ở collection scope, nên test suite phải dùng database thử nghiệm được cách ly. Không gọi `dropCollection` hoặc `deleteAll` trên namespace có thể dùng chung/prod.

### 27.2. Vì sao không assert khoảng cách quá chính xác?

Khoảng cách `$geoNear` phụ thuộc hình học, độ chính xác tọa độ và sai số dấu chấm động. Với điểm trùng center, kỳ vọng gần 0; với điểm xa hơn, kiểm tra thứ tự và khoảng hợp lý. Không hardcode một số có quá nhiều chữ số thập phân khi không cần.

### 27.3. Test đảo kinh độ/vĩ độ

Một test nên gửi `longitude=10.7750, latitude=106.7000` và xác nhận service **từ chối** vì latitude vượt `90`. Nhưng các cặp bị đảo mà vẫn nằm trong dải hợp lệ **không thể được phát hiện chỉ bằng range validation**; sản phẩm có thể cần kiểm tra vùng hoạt động dự kiến hoặc xác minh nguồn coordinate system.

### 27.4. Test đơn vị đo

Dùng hai điểm có khoảng cách đã biết xấp xỉ 1 km, kiểm chứng `distanceMeters` nằm trong khoảng hợp lý và `maxDistance(500)` loại điểm xa hơn. Test này phát hiện lỗi dùng legacy Point/radian hoặc nhân multiplier sai.

### 27.5. Test nhiều indexes

Trong một database test riêng, provision thêm `deliveryHub` `2dsphere` index và xác minh pipeline có `useIndex("location")` vẫn dùng đúng field. Nếu bỏ `key`, MongoDB có thể báo ambiguity; đừng biến một lỗi theo version/index topology thành assertion exception message cứng.

## 28. Bảo mật vị trí và API geospatial

Vị trí chính xác có thể là dữ liệu nhạy cảm. Một endpoint “nearby stores” cần kiểm soát:

- `authorizedTenantId` phải lấy từ principal/authorization đã xác thực.
- Không nhận tùy ý MongoDB `query`, `$where`, field path hoặc raw pipeline từ client.
- Validate kinh độ/vĩ độ hữu hạn, dải hợp lệ và hệ tọa độ sử dụng.
- Cố định radius và limit tối đa theo chính sách sản phẩm.
- Không trả location chính xác của người dùng hoặc dữ liệu cửa hàng thuộc tenant khác.
- Phân biệt tìm gần theo tâm người dùng với việc **lưu vị trí người dùng**; không lưu nếu không cần.
- Áp rate limits/quota phù hợp vì truy vấn bán kính lớn có thể tốn tài nguyên.
- Ghi metrics/trace an toàn, tránh log toàn bộ GPS coordinates trong application logs.
- Nếu dùng tọa độ của người dùng, tuân thủ quyền truy cập và retention phù hợp; không kết luận vị trí cá nhân từ một document geospatial không đủ xác minh.

### 28.1. Một filter sai có thể gây lộ dữ liệu

Đừng lấy top 20 stores từ mọi tenants rồi mới lọc tenant ở code Java. Làm vậy có thể làm lộ độ tồn tại/distance của các địa điểm không được phép, hoặc bỏ lỡ những cửa hàng hợp lệ do đã `$limit` từ trước. **Điều kiện tenant phải nằm trong `$geoNear.query`.**

### 28.2. GeoNear không thay routing/ETA

Nếu API trả `distanceMeters=500`, đó là độ gần theo hình học, không phải cam kết khách đi bộ 500 m hay tới nơi trong 5 phút. Đặt tên field `distanceMeters` thay vì `travelDistanceMeters` và mô tả rõ trong API schema.

## 29. Những sai lầm thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| MongoDB báo thiếu geo index | Chưa tạo index hoặc sai field | Provision `2dsphere` trên đúng location |
| Query lỗi stage order | Đặt `$match`/`$project` trước `$geoNear` | Để `$geoNear` đầu pipeline |
| Kết quả ở nơi rất xa | Đảo longitude/latitude | Chuẩn hóa `[lng,lat]` |
| Radius 2 km không hoạt động | Nhầm m/radian hoặc dùng legacy `Point` | Dùng `GeoJsonPoint` và mét |
| Distance output gấp hàng nghìn lần | Dùng legacy multiplier với GeoJSON | `0.001` nếu muốn mét → km |
| Bán kính thành 2000 km | Nghĩ multiplier đổi `maxDistance` | MaxDistance luôn theo native unit của near |
| Query lồng `$near` bị từ chối | `$geoNear.query` không cho `$near` | Bỏ near predicate, dùng `near` của stage |
| Không biết index nào được dùng | Nhiều geospatial indexes | `key`/`useIndex` đúng field path |
| Trả dữ liệu tenant khác | Lọc tenant sau `$limit` | `NearQuery.query`/`$geoNear.query` |
| Không thấy document thiếu location | Geospatial index không index vị trí null/missing | Workflow riêng cho unknown locations |
| Thêm @GeoSpatialIndexed nhưng vẫn lỗi | Auto-index creation chưa bật | Migration/IndexOperations và kiểm tra getIndexes |
| DTO distance bị null | Sai `distanceField` hoặc projection bỏ field | Đồng bộ tên output |
| Kết quả không theo gần-xa sau group | `$group` phá thứ tự documents | Sort/output strategy phù hợp |
| Trang 2 lặp kết quả | Dữ liệu di chuyển, skip không ổn định | Cursor/tie-breaker/consistency |
| GeoJSON near Polygon lỗi | MongoDB 8.0+ yêu cầu type Point | Truyền GeoJSON Point hợp lệ |
| Time series query không hợp lệ | `key` thiếu hoặc dùng `query` không hỗ trợ | Theo constraints của time series |
| Test pass nhưng production chậm | Dataset nhỏ, radius rộng, thiếu index tối ưu | Explain/workload benchmark |
| GeoNear xem như khoảng đường đi | Hình học khác routing | Dùng routing service riêng |
| Reactive Flux trả nhiều items quá mức | Không limit radius/results | Bound pipeline và backpressure |
| Tạo index mỗi request | DDL overhead/permission | Provision startup/migration |
| Ghi log GPS người dùng | Privacy leak | Redact/truncate/log metadata an toàn |

### 29.1. Quy trình chẩn đoán

1. Collection nào, MongoDB Server version nào, indexes nào đang tồn tại?
2. Input có đúng GeoJSON `type:Point` và `[lon,lat]` không?
3. `$geoNear` là stage đầu tiên chưa?
4. `key` có trỏ đúng field geospatial index?
5. Đơn vị `maxDistance`/`distanceField`/`distanceMultiplier` đúng chưa?
6. Tenant/active/category lọc trong `$geoNear.query` chưa?
7. Có `$limit` và radius tối đa chưa?
8. Query có thêm `$sort`/`$group`/`$facet` thay đổi semantics?
9. Typed Spring Data mapping có đổi tên fields không?
10. Explain cho thấy chi phí keys/docs examined và thời gian thế nào?
11. Với time series/GeoJSON type, các ràng buộc server version có được thỏa?
12. Test đã dùng MongoDB thật và dữ liệu fixture an toàn chưa?

## 30. Bài tập, checklist và tài liệu chính thức

### 30.1. Bài tập thực hành

**Bài 1 — GeoJSON.** Viết một `Point` với longitude=106.7000, latitude=10.7750; giải thích vì sao đảo thứ tự là sai.

**Bài 2 — Index.** Tạo collection test và `2dsphere` index trên `location`; kiểm tra bằng `getIndexes()` trước khi query.

**Bài 3 — GeoNear shell.** Viết `$geoNear` với bán kính 2.000 mét, `distanceField:"distanceMeters"` và tenant filter.

**Bài 4 — Stage order.** Cho pipeline `$match → $geoNear → $limit`, giải thích lỗi và chuyển `$match` vào `$geoNear.query`.

**Bài 5 — MinDistance.** Tìm các điểm nằm cách tâm từ 500 đến 2.000 mét.

**Bài 6 — Đổi đơn vị.** Giữ `maxDistance:2000`, thêm `distanceMultiplier:0.001`; xác định output dùng đơn vị nào và vì sao radius không đổi.

**Bài 7 — NearQuery.** Dùng `NearQuery.near(new GeoJsonPoint(...)).maxDistance(2000)` với filter tenant/active.

**Bài 8 — Aggregation.geoNear.** Tạo typed aggregation, chỉ định `useIndex("location")`, thêm limit 10 và project DTO.

**Bài 9 — Nhiều indexes.** Thêm index `deliveryHub` và giải thích vì sao `key` cần được chỉ rõ.

**Bài 10 — Reactive.** Chuyển pipeline sang `ReactiveMongoTemplate.aggregate` trả `Flux<NearbyStoreDto>`, không gọi `block()`.

**Bài 11 — Group.** Thống kê số cửa hàng và average distance theo category trong bán kính 2 km.

**Bài 12 — Facet.** Trả hai nhánh: top 10 và count theo category. Vì sao không đặt `$limit` trước `$facet`?

**Bài 13 — Tenant.** Giải thích lỗi logic và bảo mật nếu lọc tenant sau `$limit`.

**Bài 14 — Pagination.** Khi hai cửa hàng có cùng khoảng cách và một cửa hàng di chuyển, offset pagination có thể gây điều gì?

**Bài 15 — Test.** Dùng MongoDB test thật, UUID tenant, điểm gần/xa, active/inactive, kiểm tra kết quả và distance.

**Bài 16 — Explain.** So executionStats khi index `location_2dsphere` và compound tenant/location index, trên dữ liệu đại diện.

**Bài 17 — Time series.** Tra constraints `key`, `distanceField`, `query` của `$geoNear` trên time series và giải thích khác collection thường.

### 30.2. Checklist triển khai

- [ ] Lưu GeoJSON Point với thứ tự `[longitude, latitude]`.
- [ ] Validate dải kinh/vĩ độ, NaN/Infinity và schema type Point.
- [ ] Có geospatial index đúng field, ưu tiên `2dsphere` cho GeoJSON.
- [ ] Biết `@GeoSpatialIndexed` không tự bảo đảm index đã được tạo.
- [ ] `$geoNear` là stage đầu tiên trong pipeline/subpipeline.
- [ ] Khai báo `near`, `key`, `distanceField` rõ ràng.
- [ ] Có `spherical` theo ngữ nghĩa mong muốn.
- [ ] Dùng `maxDistance`/`minDistance` theo **mét** khi near là GeoJSON.
- [ ] Không lẫn `Point` legacy và `GeoJsonPoint`.
- [ ] Không dùng radian multiplier cho GeoJSON metres.
- [ ] Không đặt `$near` bên trong `$geoNear.query`.
- [ ] Tenant, active/category filter trong `$geoNear.query`.
- [ ] Có server-side `$limit` và giới hạn bán kính của API.
- [ ] Hiểu `$group`/`$sort`/`$facet` có thể thay đổi thứ tự/tập kết quả.
- [ ] DTO chỉ trả fields được phép và đơn vị distance rõ ràng.
- [ ] Dùng `Aggregation.geoNear(NearQuery,String)` và `GeoNearOperation.useIndex` theo Javadoc.
- [ ] Kiểm tra typed Spring Data property→BSON mapping.
- [ ] Reactive pipeline được subscribe đúng ở framework boundary.
- [ ] Không xem distance là đường đi thực tế/ETA.
- [ ] Kiểm tra time series/server-version constraints nếu áp dụng.
- [ ] Dùng `getIndexes()` và `explain("executionStats")` trên workload thực.
- [ ] Có integration test gần/xa, tenant, null location và unit conversion.
- [ ] Không log GPS nhạy cảm hoặc chạy fixture trên production.
- [ ] `WRITTEN` chỉ là trạng thái viết kỹ thuật, không phải đã Content QA hay publish.

### 30.3. Tài liệu tham khảo chính thức

1. [MongoDB Manual — $geoNear aggregation stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geonear/): cú pháp, đầu pipeline, index, key, distance và time series.
2. [MongoDB Manual — $near query predicate](https://www.mongodb.com/docs/manual/reference/operator/query/near/): GeoJSON và legacy units.
3. [MongoDB Manual — 2dsphere Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/): geospatial indexing theo mặt cầu.
4. [MongoDB Manual — GeoJSON Objects](https://www.mongodb.com/docs/manual/reference/geojson/): điểm, geometry types và thứ tự coordinates.
5. [MongoDB Manual — $geoWithin](https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/): lựa chọn truy vấn vùng.
6. [MongoDB Manual — $geoIntersects](https://www.mongodb.com/docs/manual/reference/operator/query/geoIntersects/): truy vấn giao hình học.
7. [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): query plan/performance.
8. [Spring Data MongoDB — Geo-near Queries](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): NearQuery và chuyển từ geoNear command sang aggregation.
9. [Spring Data MongoDB — NearQuery Javadoc](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/NearQuery.html): GeoJsonPoint, legacy Point, metric, filters.
10. [Spring Data MongoDB — GeoNearOperation Javadoc](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/GeoNearOperation.html): `Aggregation.geoNear` và `useIndex`.
11. [Spring Data MongoDB — Index Management](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html): quản lý index và auto-creation default.
12. [Spring Data MongoDB — GeospatialIndex Javadoc](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/index/GeospatialIndex.html): lập trình `2dsphere` index.
13. [Spring Data MongoDB — Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html): typed pipelines và projections.
14. [Spring Data MongoDB — Reactive Template](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html): reactive aggregation.
15. [MongoDB Manual — Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/): giới hạn schema/index của time series.
16. [MongoDB Manual — $facet](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/): multiple output branches và resource limits.

**Kết luận:** `$geoNear` là aggregation stage dùng geospatial index để tìm documents theo khoảng cách, thêm `distanceField` và trả kết quả **gần trước, xa sau**. Đặt nó **ở đầu pipeline**, đưa filters như tenant/active vào `query`, chỉ định `key` khi chọn field vị trí và luôn kiểm tra index `2dsphere`. Với **GeoJSON Point**, dùng `[longitude, latitude]` và **mét** cho khoảng cách native, đừng nhầm với radian của legacy coordinates hoặc nhân distanceMultiplier sai. Trong Spring Data MongoDB, ghép `NearQuery` với `Aggregation.geoNear(...)`, thực thi qua `MongoTemplate` hoặc `ReactiveMongoTemplate`, kiểm thử trên MongoDB thật và đo `explain`. Giới hạn radius/results, bảo vệ dữ liệu vị trí và nhớ rằng khoảng cách geospatial không phải quãng đường di chuyển.

