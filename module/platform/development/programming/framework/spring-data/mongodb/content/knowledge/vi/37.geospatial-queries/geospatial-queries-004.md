# Near, Within và toán tử truy vấn không gian

## 1. Bài toán và mục tiêu

Một ứng dụng sử dụng **Spring Data MongoDB** muốn tra cứu những điểm giao nhận đang hoạt động theo vị trí của khách hàng. Những câu hỏi trông giống nhau nhưng có ngữ nghĩa rất khác:

1. **Điểm nào gần tôi nhất?** Cần kết quả sắp xếp theo khoảng cách: `$near` hoặc `$nearSphere`.
2. **Điểm nào nằm trong vòng bán kính 2 km?** Chỉ cần lọc theo vùng: `$geoWithin` với `$centerSphere`.
3. **Điểm nào nằm trong phạm vi một quận được mô tả bằng Polygon?** `$geoWithin` với `$geometry`.
4. **Tuyến giao hàng nào cắt qua khu vực cảnh báo?** `$geoIntersects`.
5. **Muốn trả cả khoảng cách tính được cho từng địa điểm?** Dùng aggregation `$geoNear` hoặc Spring Data `NearQuery`/`GeoResult`.

Nếu lẫn lộn các phép này, ứng dụng có thể trả sai thứ tự, sai khoảng cách, quét quá nhiều dữ liệu hoặc lỗi vì không có chỉ mục địa lý phù hợp.

Trong bài này, ta thực hành cả **MongoDB query operators**, **`MongoTemplate`/`Criteria`**, **repository derived queries**, các lưu ý với **reactive access**, index, transaction, kiểm thử và phân tích hiệu năng. Đây là bài học trong chương **Truy vấn không gian** của Spring Data MongoDB.

### Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt GeoJSON với legacy coordinate pairs, `2dsphere` với `2d` và trật tự **kinh độ – vĩ độ**.
- Chọn `$near`/`$nearSphere` khi cần **độ gần + thứ tự**, chọn `$geoWithin` khi cần **lọc vùng**.
- Dùng `$box`, `$center`, `$centerSphere`, GeoJSON Polygon và `$geoIntersects` đúng ngữ nghĩa.
- Viết `Criteria.near(...)`, `nearSphere(...)`, `within(...)`, `withinSphere(...)`, `intersects(...)` và các repository methods tương ứng.
- Hiểu đơn vị **mét, độ, radian**, vấn đề ranh giới, index/`explain`, `countDocuments` và `$geoNear`.
- Kiểm thử trên MongoDB thật thay vì dự đoán kết quả từ tọa độ bằng mắt.

## 2. Chuẩn dữ liệu: GeoJSON, kinh độ/vĩ độ và legacy pair

### 2.1. GeoJSON Point

Trong MongoDB, điểm địa lý thường biểu diễn như sau:

```javascript
{
  location: {
    type: "Point",
    coordinates: [106.7000, 10.8000]
  }
}
```

**Thứ tự bắt buộc: `[longitude, latitude]` — kinh độ trước, vĩ độ sau.** Đây là thứ tự mà GeoJSON/MongoDB dùng; nhiều UI và thư viện bản đồ lại biểu diễn `(latitude, longitude)`, nên đây là nguồn lỗi rất phổ biến.

Trong ví dụ, các tọa độ chỉ là **dữ liệu tổng hợp để minh họa**, không đại diện cho một doanh nghiệp hoặc điểm giao nhận thật. Phạm vi hợp lệ cho tọa độ địa lý WGS84 thông thường:

| Thuộc tính | Ý nghĩa | Miền giá trị |
| --- | --- | --- |
| Longitude / x | Kinh độ, Tây âm, Đông dương | Từ -180 đến +180 độ |
| Latitude / y | Vĩ độ, Nam âm, Bắc dương | Từ -90 đến +90 độ |
| `coordinates` | Trong GeoJSON Point | `[longitude, latitude]` |
| Thứ nguyên lưu trữ | Độ góc trên địa cầu | **Không phải mét** |

Ví dụ từ API frontend thường có `lat = 10.8` và `lng = 106.7`. Khi xây `GeoJsonPoint`, dùng `new GeoJsonPoint(lng, lat)`, không đảo lại vì một biến được đặt tên `x`/`y`.

### 2.2. Legacy coordinates

MongoDB cũng hỗ trợ mảng legacy:

```javascript
{ location: [106.7000, 10.8000] }
```

Đó **không phải GeoJSON**. Một `Point` của Spring Data là kiểu tọa độ hình học cơ bản; `GeoJsonPoint` biểu diễn cấu trúc GeoJSON với `type: "Point"` và `coordinates`. Hai kiểu khác nhau có thể khiến MongoDB tạo biểu thức query và diễn giải khoảng cách **khác đơn vị**.

| Tiêu chí | GeoJSON Point | Legacy pair |
| --- | --- | --- |
| BSON mẫu | `{type:"Point", coordinates:[x,y]}` | `[x,y]` |
| Java phổ biến | `GeoJsonPoint` | `Point` |
| Index thường chọn | `2dsphere` | `2d` cho planar; `2dsphere` cũng hỗ trợ một số dạng legacy |
| Hình học | Cầu/địa cầu | Có thể là phẳng hoặc cầu theo operator/index |
| Khoảng cách với `$near` | Thường là **mét** | Phụ thuộc operator/index; không mặc định là mét |

**Không trộn tùy tiện** legacy points và GeoJSON objects trong một field khi API yêu cầu quy đổi khoảng cách thống nhất. Khi migration dữ liệu cũ, phải kiểm tra từng BSON type, index và operator thực tế.

### 2.3. GeoJSON Polygon và các loại hình học

Polygon được tạo từ một hoặc nhiều **linear rings**. Tọa độ điểm đầu và cuối của mỗi ring phải trùng nhau:

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.69, 10.79],
      [106.72, 10.79],
      [106.72, 10.82],
      [106.69, 10.82],
      [106.69, 10.79]
    ]
  ]
}
```

Ring đầu biểu diễn đường bao ngoài; các ring tiếp theo có thể là lỗ theo chuẩn GeoJSON. Cần kiểm tra tính hợp lệ của polygon, chiều/hướng ring, self-intersection, đa giác vượt kinh tuyến ±180° và các trường hợp diện tích lớn. Một “rectangle” chỉ nhìn bằng mắt có thể không trùng ranh giới geodesic trên mặt cầu.

Các loại như `MultiPoint`, `LineString`, `MultiLineString`, `MultiPolygon` và `GeometryCollection` cũng có thể liên quan đến truy vấn, nhưng khả năng hỗ trợ từng operator/index và edge case cần được kiểm theo MongoDB release.

## 3. Chọn index: `2dsphere` và `2d` không tương đương

### 3.1. Tạo dữ liệu demo riêng

Tạo database minh họa **không chứa dữ liệu quan trọng**:

```javascript
use geospatial_training

db.pickup_points.insertMany([
  {
    _id: "P-001",
    tenant_id: "TENANT-A",
    name: "Điểm A",
    active: true,
    location: {
      type: "Point",
      coordinates: [106.7000, 10.8000]
    }
  },
  {
    _id: "P-002",
    tenant_id: "TENANT-A",
    name: "Điểm B",
    active: true,
    location: {
      type: "Point",
      coordinates: [106.7050, 10.8050]
    }
  },
  {
    _id: "P-003",
    tenant_id: "TENANT-A",
    name: "Điểm C",
    active: false,
    location: {
      type: "Point",
      coordinates: [106.7300, 10.8300]
    }
  },
  {
    _id: "P-004",
    tenant_id: "TENANT-B",
    name: "Điểm D",
    active: true,
    location: {
      type: "Point",
      coordinates: [106.7010, 10.8010]
    }
  }
])
```

Lệnh `insertMany` chỉ là seed một lần; chạy lại với cùng `_id` sẽ báo duplicate key. Test suite cần dọn dữ liệu trong database **riêng**, không áp dụng lệnh xóa toàn bộ lên production.

### 3.2. Index GeoJSON

```javascript
db.pickup_points.createIndex(
  { location: "2dsphere" },
  { name: "pickup_location_2dsphere" }
)

db.pickup_points.getIndexes()
```

`2dsphere` được thiết kế cho dữ liệu trên địa cầu và là lựa chọn tự nhiên cho GeoJSON Point/Polygon. Cần có geospatial index phù hợp để dùng `$near`/`$nearSphere` và `$geoNear`. `$geoWithin` có những trường hợp **có thể chạy không có index** nhưng thường chậm hơn đáng kể trên tập lớn; `$geoIntersects` cần xét yêu cầu `2dsphere` theo hình học/index sử dụng.

`2d` là loại index riêng cho tọa độ trên **mặt phẳng**. Không thêm `2d` vào field GeoJSON chỉ vì query chậm; nên kiểm đúng mô hình dữ liệu và loại hình học trước.

### 3.3. Compound index và lọc tenant

Query thực tế thường có:

```javascript
{
  tenant_id: "TENANT-A",
  active: true,
  location: { /* geospatial clause */ }
}
```

Bạn có thể cần index kết hợp scalar và địa lý, ví dụ:

```javascript
db.pickup_points.createIndex(
  { tenant_id: 1, active: 1, location: "2dsphere" },
  { name: "pickup_tenant_active_geo" }
)
```

Nhưng **không** mặc định compound index luôn nhanh hơn `{location:"2dsphere"}`. Hiệu quả phụ thuộc cardinality tenant, mật độ điểm, phạm vi truy vấn, selectivity và kế hoạch thực thi; hãy đo `explain("executionStats")` với dữ liệu đại diện. Trên sharded cluster còn phải xét shard key, phân vùng dữ liệu và routing. Đừng sử dụng geospatial query để đọc vượt tenant hoặc kỳ vọng index tự thực thi phân quyền.

### 3.4. Annotation Spring Data chỉ là định nghĩa

`@GeoSpatialIndexed` có thể khai báo chỉ mục trên entity, nhưng **không đảm bảo index được tạo tự động trên MongoDB production**. Spring Data MongoDB có cơ chế tạo index theo cấu hình và API `IndexOperations`; nên thực hiện migration và kiểm tra index thực trước khi nhận request:

```javascript
db.pickup_points.getIndexes()
```

Nếu chưa có index, `$near` sẽ báo lỗi thay vì trả kết quả rồi tự tối ưu. Đừng xử lý lỗi này bằng cách bắt exception rồi **bỏ điều kiện vị trí**.

## 4. Bảng chọn operator theo ý định

| MongoDB operator | Ý nghĩa | Sắp theo gần → xa? | Index / tình huống |
| --- | --- | --- | --- |
| `$near` | Các geometry gần một điểm; khoảng cách nhỏ nhất trước | **Có** | Cần geospatial index; với GeoJSON dùng `2dsphere` |
| `$nearSphere` | Các geometry gần một điểm theo hình học cầu | **Có** | Cần geospatial index; rõ ràng về spherical distance |
| `$geoWithin` + `$centerSphere` | Trong hình tròn trên mặt cầu | **Không** | Radius **radian**; 2dsphere hữu ích |
| `$geoWithin` + `$geometry` | Nằm trong hình học GeoJSON (ví dụ Polygon) | **Không** | Thường dùng `2dsphere` |
| `$geoWithin` + `$box` | Trong hộp tọa độ phẳng | **Không** | Với legacy planar/`2d` theo bài toán |
| `$geoWithin` + `$center` | Trong vòng tròn phẳng | **Không** | Bán kính theo **đơn vị tọa độ** |
| `$geoWithin` + `$polygon` | Trong polygon phẳng kiểu legacy | **Không** | Không phải GeoJSON Polygon |
| `$geoIntersects` + `$geometry` | Geometry giao nhau/đụng hình học vùng | **Không** | Dùng khi cần intersect thay vì chứa hoàn toàn |
| `$geoNear` aggregation | Gần nhất kèm trường **khoảng cách** trong pipeline | **Có** | Geospatial index, stage restrictions |

**Một ví dụ ra quyết định:**

- “Mười điểm gần nhất, có thứ tự” → `$near` hoặc `$geoNear` rồi `limit`.
- “Đếm điểm nằm trong bán kính 2 km” → `$geoWithin: {$centerSphere: ...}`; không dùng `$near` trong `countDocuments`.
- “Lọc điểm trong vùng giao hàng, sắp theo tên” → `$geoWithin` + `sort({name:1})`.
- “Kiểm tra tuyến đường (LineString) cắt vùng cấm” → `$geoIntersects`.

## 5. `$near`: lọc theo khoảng cách **và** trả kết quả đã xếp hạng

### 5.1. Query GeoJSON trực tiếp

Tìm điểm trong vòng 2.000 mét quanh `[106.7,10.8]`, chỉ trong tenant A và đang hoạt động:

```javascript
db.pickup_points.find({
  tenant_id: "TENANT-A",
  active: true,
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.8000]
      },
      $maxDistance: 2000
    }
  }
}).limit(10)
```

Với GeoJSON Point và `2dsphere` index, `$maxDistance: 2000` là **2.000 mét**, không phải 2.000 độ. Kết quả được sắp xếp theo khoảng cách từ gần đến xa. Giới hạn `limit(10)` chỉ lấy nhiều nhất mười điểm phù hợp.

Muốn tìm trong vành khăn từ 500 đến 2.000 mét:

```javascript
db.pickup_points.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.8000]
      },
      $minDistance: 500,
      $maxDistance: 2000
    }
  }
})
```

Đây là query minh họa **chỉ dựa vào khoảng cách**; trong API multi-tenant phải thêm tenant/authorization filters trước khi trả dữ liệu.

### 5.2. `$near` đã sort; thêm `sort` có thể làm đổi ý nghĩa

```javascript
// KHÔNG còn cam kết gần nhất đứng trước khi sort lại theo tên:
db.pickup_points.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7, 10.8]
      },
      $maxDistance: 2000
    }
  }
}).sort({ name: 1 })
```

MongoDB thực hiện bước sắp xếp bổ sung theo tên. Điều đó tốn thêm tài nguyên và phá thứ tự nearest-first. Nếu cần tie-breaking ổn định bằng ID hoặc nhiều tiêu chí, định nghĩa hợp đồng xếp hạng rõ và cân nhắc `$geoNear` + pipeline `$sort` thích hợp sau khi đã tính khoảng cách.

### 5.3. `$near` không thay cho mọi query

Một geospatial query theo `$near` là predicate có semantics riêng:

- Cần index địa lý. Thiếu index thường gây lỗi.
- Không dùng đồng thời với query yêu cầu special index khác như `$text`.
- `$or` chứa `$near`/`$nearSphere` không được thêm những nhánh khác (không dùng để “near HOẶC featured”).
- Trong aggregation, không đặt `$near` vào `$match`; dùng stage `$geoNear`.
- Khi chỉ cần lọc vùng **không quan tâm thứ tự**, `$geoWithin` thường đúng yêu cầu và tránh công sắp xếp theo khoảng cách.

Từ MongoDB 8.0, các toán tử `$near`, `$nearSphere` và `$geoNear` kiểm tra GeoJSON geometry truy vấn phải là **Point**. Đừng gửi Polygon như tâm `$near`, ngay cả khi mã client trước đây chấp nhận payload đó.

## 6. `$nearSphere`: chọn rõ khoảng cách trên mặt cầu

`$nearSphere` yêu cầu khoảng cách hình cầu và cũng trả kết quả **từ gần đến xa**. Khi lưu và truy vấn **GeoJSON Point + 2dsphere**, `$near` và `$nearSphere` có hành vi tương đương cho phép tìm gần điểm; nhưng `$nearSphere` thể hiện rõ dụng ý spherical:

```javascript
db.pickup_points.find({
  tenant_id: "TENANT-A",
  active: true,
  location: {
    $nearSphere: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.8000]
      },
      $minDistance: 300,
      $maxDistance: 2000
    }
  }
}).limit(10)
```

Với `$geometry` GeoJSON, `$minDistance`/`$maxDistance` đo bằng **mét**. Với **legacy coordinate pair**, cùng tên toán tử có thể diễn giải các giá trị giới hạn theo **radian**. Cần xác định kiểu query argument thực tế do Spring Data tạo ra, không chỉ nhìn vào tên method Java.

### 6.1. Không lấy khoảng cách từ thứ tự mà không có field distance

`find(...)` sử dụng `$nearSphere` trả về document theo thứ tự gần nhất, nhưng không tự bảo đảm response chứa trường `distanceMeters` đã tính. Nếu API cần hiển thị “450 m”, dùng **`$geoNear` aggregation** hoặc Spring Data `NearQuery`/`GeoResult`, hay một quy trình tính khoảng cách được định nghĩa rõ.

Không lấy `index` của document trong result list để suy ra một khoảng cách; thứ tự chỉ cho biết quan hệ gần hơn/xa hơn theo toán tử.

### 6.2. Khoảng cách địa cầu không phải đường đi thực tế

Khoảng cách địa lý hình cầu **không phải** khoảng cách di chuyển theo đường bộ, thời gian chạy xe hoặc đường đi vòng qua sông/cầu. API gợi ý điểm nhận hàng nên nói rõ `distanceMeters` là **geodesic/geospatial distance**, không phải ETA. Nếu muốn ETA/route thực, cần hệ thống định tuyến khác.

## 7. `$geoWithin`: chọn điểm trong một vùng, **không** sắp xếp theo độ gần

`$geoWithin` là predicate chọn geometry nằm trong một hình. Nó không tự xuất khoảng cách hoặc xếp hạng theo điểm gốc; có thể kết hợp các điều kiện `tenant_id`/`active` và thêm `sort` theo **thuộc tính nghiệp vụ**.

### 7.1. Vùng tròn hình cầu: `$centerSphere`

Để tìm điểm trong phạm vi 2 km quanh `[106.7,10.8]`:

```javascript
const earthRadiusKm = 6378.137; // xấp xỉ bán kính xích đạo WGS84
const radiusKm = 2;
const radiusRadians = radiusKm / earthRadiusKm;

db.pickup_points.find({
  tenant_id: "TENANT-A",
  active: true,
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7000, 10.8000],
        radiusRadians
      ]
    }
  }
}).sort({ name: 1 })
```

**Đơn vị `radiusRadians` ở đây là radian**. Nếu đặt `$centerSphere: [[lng, lat], 2000]`, MongoDB **không hiểu đó là 2.000 mét**. Đổi từ mét thành radian:

\[
r_{\mathrm{rad}} = \frac{d_{\mathrm{m}}}{R_{\mathrm{m}}}
\]

Với `R ≈ 6.378.137 m`, khoảng 2.000 m tương đương gần `0,00031357 rad`. Hệ quy chiếu “trái đất hình cầu” là phép xấp xỉ; không dùng độ chính xác này để kết luận các ranh giới pháp lý hoặc đo đạc khảo sát ở centimet.

### 7.2. Vùng hình hộp phẳng: `$box`

`$box` mô tả hai góc của hộp:

```javascript
db.legacy_locations.find({
  location: {
    $geoWithin: {
      $box: [
        [106.68, 10.78],
        [106.72, 10.83]
      ]
    }
  }
})
```

Ví dụ giả định collection `legacy_locations` chứa **legacy coordinate pairs** với cấu hình `2d`/dữ liệu phẳng phù hợp. `$box` không nhận bán kính theo mét; nó mô tả **hình học phẳng trong hệ tọa độ của dữ liệu**, nên dùng nó để vẽ “ô vuông 2 km” theo kinh/vĩ độ mà không xét biến dạng có thể dẫn tới sai số.

### 7.3. Vòng tròn phẳng: `$center`

```javascript
db.legacy_locations.find({
  location: {
    $geoWithin: {
      $center: [
        [106.7000, 10.8000],
        0.01
      ]
    }
  }
})
```

Ở đây bán kính `0.01` nằm trong **đơn vị tọa độ phẳng** (nếu đầu vào là longitude/latitude, đó là độ góc), không phải 0,01 km hay 10 m. Với bài toán diện tích trên mặt đất, `$centerSphere` và `2dsphere` thường rõ ràng hơn.

### 7.4. Polygon phẳng legacy: `$polygon`

```javascript
db.legacy_locations.find({
  location: {
    $geoWithin: {
      $polygon: [
        [106.69, 10.79],
        [106.72, 10.79],
        [106.72, 10.82],
        [106.69, 10.82]
      ]
    }
  }
})
```

Đây là toán tử vùng phẳng legacy, **không** đồng nhất với GeoJSON Polygon dùng `$geometry`. Với vùng thực tế theo GeoJSON và 2dsphere, ưu tiên `$geometry`.

### 7.5. GeoJSON Polygon với `$geometry`

```javascript
const deliveryZone = {
  type: "Polygon",
  coordinates: [[
    [106.69, 10.79],
    [106.72, 10.79],
    [106.72, 10.82],
    [106.69, 10.82],
    [106.69, 10.79]
  ]]
};

db.pickup_points.find({
  tenant_id: "TENANT-A",
  active: true,
  location: {
    $geoWithin: {
      $geometry: deliveryZone
    }
  }
})
```

MongoDB đánh giá hình học vùng và trả điểm nằm trong polygon. **Không có thứ tự theo khoảng cách**; nếu UI cần thứ tự, `sort` theo field (như name/priority) hoặc chạy một pipeline tính distance riêng.

### 7.6. Kiểm tra ranh giới vùng và polygon khó

Các ca cần kiểm thử riêng:

- Điểm **nằm đúng đường biên** hoặc gần biên trong sai số số thực.
- Polygon có lỗ, nhiều vòng hoặc `MultiPolygon`.
- Polygon tự cắt, ring chưa đóng, chiều hướng và vùng chiếm phần lớn địa cầu.
- Vùng cắt kinh tuyến 180° (antimeridian), gần cực hoặc qua kinh tuyến gốc.
- Hệ tọa độ không phải longitude/latitude WGS84 (ví dụ hệ chiếu theo mét nội bộ).

Không tự suy diễn rằng “đúng biên được tính như trong hình học Euclid” cho mọi truy vấn `2dsphere`: MongoDB có quy tắc hình học và giới hạn riêng, kể cả khả năng **không bảo đảm kết quả ổn định cho biên hình học** trong một số trường hợp. Nếu biên ảnh hưởng tiền, pháp lý hoặc phân vùng giao hàng, cần quy tắc nghiệp vụ dự phòng (buffer, tolerance, tie-break) và test dữ liệu thực.

## 8. `$geoIntersects`: giao nhau khác với nằm hoàn toàn bên trong

Với một point, kiểm tra nằm trong polygon có thể được diễn đạt bằng `$geoWithin`. Nhưng với tuyến đường, vùng hoặc hình học mở rộng, **giao nhau** và **nằm trọn bên trong** là hai điều kiện khác:

- `$geoWithin`: geometry của document **nằm hoàn toàn trong** vùng truy vấn.
- `$geoIntersects`: geometry **giao hoặc chạm** vùng truy vấn theo toán học không gian mà MongoDB hỗ trợ.

Ví dụ lưu tuyến đường:

```javascript
db.delivery_routes.insertOne({
  _id: "ROUTE-001",
  tenant_id: "TENANT-A",
  path: {
    type: "LineString",
    coordinates: [
      [106.68, 10.80],
      [106.70, 10.80],
      [106.73, 10.80]
    ]
  }
})

db.delivery_routes.createIndex(
  { path: "2dsphere" },
  { name: "route_path_geo" }
)
```

Tìm tuyến **cắt qua** vùng cảnh báo:

```javascript
db.delivery_routes.find({
  tenant_id: "TENANT-A",
  path: {
    $geoIntersects: {
      $geometry: {
        type: "Polygon",
        coordinates: [[
          [106.69, 10.79],
          [106.72, 10.79],
          [106.72, 10.82],
          [106.69, 10.82],
          [106.69, 10.79]
        ]]
      }
    }
  }
})
```

Tuyến trên bắt đầu ngoài vùng, đi xuyên vùng rồi đi ra ngoài. Nó **không nằm trọn trong** polygon, nhưng có phần giao nhau. Đây là bài toán của `$geoIntersects`, không chỉ `$geoWithin`.

## 9. Spring Data MongoDB: mapping Java và `Criteria`

### 9.1. Entity GeoJSON Point

```java
package com.example.geo;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexed;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "pickup_points")
public class PickupPoint {

    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String name;
    private boolean active;

    @GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
    private GeoJsonPoint location;

    protected PickupPoint() {}

    public PickupPoint(
            String id, String tenantId, String name,
            boolean active, GeoJsonPoint location) {
        this.id = id;
        this.tenantId = tenantId;
        this.name = name;
        this.active = active;
        this.location = location;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getName() { return name; }
    public boolean isActive() { return active; }
    public GeoJsonPoint getLocation() { return location; }
}
```

`new GeoJsonPoint(106.70, 10.80)` sinh GeoJSON Point, trong đó `x = longitude`, `y = latitude`. Annotation `@GeoSpatialIndexed` mô tả index cần thiết nhưng **không thay migration**; hãy xác nhận database có index trước khi chạy ứng dụng.

### 9.2. Template với `Criteria.nearSphere`

```java
package com.example.geo;

import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class PickupSearchService {

    private final MongoTemplate template;

    public PickupSearchService(MongoTemplate template) {
        this.template = template;
    }

    public List<PickupPoint> nearest(
            String authorizedTenantId,
            double longitude, double latitude,
            double maxDistanceMeters, int limit) {

        validate(authorizedTenantId, longitude, latitude,
            maxDistanceMeters, limit);

        Query query = Query.query(
            Criteria.where("tenantId").is(authorizedTenantId)
                .and("active").is(true)
                .and("location")
                    .nearSphere(new GeoJsonPoint(longitude, latitude))
                    .maxDistance(maxDistanceMeters)
        );

        query.limit(limit);
        return template.find(query, PickupPoint.class);
    }

    private static void validate(
            String tenantId, double lng, double lat,
            double meters, int limit) {
        if (tenantId == null || tenantId.isBlank()
                || !Double.isFinite(lng)
                || !Double.isFinite(lat)
                || lng < -180 || lng > 180
                || lat < -90 || lat > 90
                || !Double.isFinite(meters)
                || meters < 0 || meters > 50000
                || limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                "Tham số geospatial không hợp lệ");
        }
    }
}
```

`Criteria.nearSphere(...)` tạo điều kiện `$nearSphere`. Với `GeoJsonPoint` và `2dsphere`, giới hạn khoảng cách sử dụng **mét** trong query GeoJSON. `MongoTemplate` dùng mapping metadata của `PickupPoint` để chuyển property `tenantId` thành BSON `tenant_id`.

**Phân quyền vẫn phải do service/authorization layer quyết định.** Không nhận `authorizedTenantId` từ query parameter tùy ý; lấy từ danh tính đã xác thực. Khi thiếu index, sửa migration/index thay vì âm thầm chuyển sang query không filter địa lý.

### 9.3. Template với `Criteria.withinSphere`

`Circle` trong Spring Data có center `Point` và radius `double`. Khi dùng `withinSphere` để tạo `$centerSphere`, **radius phải là radian**:

```java
import java.util.List;
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

double radiusMeters = 2000.0;
double radiusRadians = radiusMeters / 6_378_137.0;

Circle area = new Circle(
    new Point(106.7000, 10.8000), radiusRadians);

Query withinQuery = Query.query(
    Criteria.where("tenantId").is(authorizedTenantId)
        .and("active").is(true)
        .and("location").withinSphere(area)
);

List<PickupPoint> points =
    mongoTemplate.find(withinQuery, PickupPoint.class);
```

`mongoTemplate`/`authorizedTenantId` là biến có sẵn trong service. `withinSphere` **không sắp xếp theo khoảng cách**. Nếu cần thứ tự theo tên, thêm `withinQuery.with(Sort.by("name"))`; nếu cần độ gần, phải chọn `nearSphere`/`$geoNear`.

### 9.4. Template với `within(Box)` và `within(GeoJsonPolygon)`

`Criteria.within(...)` nhận `Shape`:

```java
import org.springframework.data.geo.Box;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.geo.GeoJsonPolygon;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Box box = new Box(
    new Point(106.68, 10.78),
    new Point(106.72, 10.83)
);
Query legacyPlanar = Query.query(
    Criteria.where("location").within(box)
);

GeoJsonPolygon zone = new GeoJsonPolygon(
    new Point(106.69, 10.79),
    new Point(106.72, 10.79),
    new Point(106.72, 10.82),
    new Point(106.69, 10.82),
    new Point(106.69, 10.79)
);

Query withinGeoJson = Query.query(
    Criteria.where("location").within(zone)
);
```

**Không đánh đồng hai query**: `Box` thể hiện vùng phẳng legacy; `GeoJsonPolygon` được mapping sang `$geoWithin/$geometry` theo GeoJSON. Trong một service multi-tenant, cần thêm `tenantId`/`active` và validation; các đoạn này chỉ minh họa API.

### 9.5. Template với `Criteria.intersects`

Khi lưu geometry của tuyến đường hoặc khu vực, có thể dùng:

```java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query crossing = Query.query(
    Criteria.where("path").intersects(zone)
);
```

`zone` là `GeoJsonPolygon` từ ví dụ trên; query này dùng `$geoIntersects`. Collection `delivery_routes` phải có field `path` phù hợp và geospatial index. `PickupPoint` không có field `path`, vì vậy không chạy query này bằng `PickupPoint.class` rồi kỳ vọng tìm được tuyến đường.

## 10. Repository derived queries: `Near` và `Within`

Spring Data MongoDB hỗ trợ keywords `Near`/`Within` trong tên method repository:

```java
package com.example.geo;

import java.util.List;
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.geo.GeoJsonPolygon;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface PickupPointRepository
        extends MongoRepository<PickupPoint, String> {

    List<PickupPoint> findByLocationNear(
        Point center, Distance maxDistance);

    List<PickupPoint> findByLocationWithin(
        Circle circle);

    List<PickupPoint> findByLocationWithin(
        GeoJsonPolygon polygon);
}
```

Spring Data tạo query theo tên `findByLocationNear`/`findByLocationWithin`. Với method nhận `Distance` có `Metrics.KILOMETERS` hoặc `Metrics.MILES`, Spring Data có thể dùng `$nearSphere` và chuyển đơn vị theo metric; với kiểu shape GeoJSON, nó tạo cấu trúc `$geometry` phù hợp.

### 10.1. Gọi method Near

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;

List<PickupPoint> nearby = repository.findByLocationNear(
    new GeoJsonPoint(106.7000, 10.8000),
    new Distance(2, Metrics.KILOMETERS)
);
```

`repository` được inject trong một service. Query có thể dùng spherical semantics vì `Distance` mang `Metric`. **Không ghi đè hợp đồng đơn vị** bằng giả định rằng `new Distance(2)` luôn là 2 km; nếu không truyền metric, nghĩa của distance phụ thuộc query representation/index.

### 10.2. Gọi method Within

```java
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Point;

// Circle theo API Within(Circle) thông thường là planar,
// radius ở đơn vị tọa độ chứ KHÔNG phải mét.
Circle planarCircle = new Circle(
    new Point(106.70, 10.80),
    0.01
);

List<PickupPoint> results =
    repository.findByLocationWithin(planarCircle);
```

**Lưu ý quan trọng:** `findByLocationWithin(Circle)` thường ánh xạ sang `$geoWithin/$center` (planar). Đối với radius **2 km trên địa cầu**, dùng `Criteria.withinSphere`/`$centerSphere`, hoặc một repository method được thiết kế rõ về spherical semantics theo Spring Data version. Không truyền `new Circle(..., 2000)` và nghĩ nó là 2.000 m.

### 10.3. Method trả `GeoResults` và khoảng cách

Một repository geospatial finder có thể trả `GeoResults<T>` hoặc `GeoResult<T>` theo khả năng API/phiên bản:

```java
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface PickupDistancesRepository
        extends MongoRepository<PickupPoint, String> {

    GeoResults<PickupPoint> findByLocationNear(Point center);
}
```

Với Spring Data MongoDB, đường geonear trả `GeoResult` có `getContent()` và `getDistance()`; khoảng cách trong `GeoResult` cần được kiểm theo metric. Đối với API lớn, nên **bắt buộc giới hạn maxDistance/limit**, không query tất cả địa điểm chỉ để tính trung bình.

### 10.4. Đừng dựa vào derived method khi business filter phức tạp

Đường repository phù hợp với query đơn giản. Khi cần tenant authorization, active status, polygon động, distance, projection hoặc các điều kiện đặc thù theo version, `MongoTemplate`/`NearQuery` thường rõ ràng hơn. Một method `findByLocationNear(...)` chỉ lọc vị trí **không tự lọc tenant**; nếu dùng trực tiếp trong API multi-tenant có thể lộ dữ liệu.

## 11. `NearQuery` và `$geoNear`: khi cần trường khoảng cách

### 11.1. Aggregation `$geoNear` trên MongoDB

`$geoNear` trả các document theo khoảng cách gần → xa, có thể bổ sung field số như `distanceMeters`:

```javascript
db.pickup_points.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.8000]
      },
      key: "location",
      distanceField: "distanceMeters",
      spherical: true,
      maxDistance: 2000,
      query: {
        tenant_id: "TENANT-A",
        active: true
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      name: 1,
      tenant_id: 1,
      distanceMeters: 1
    }
  }
])
```

Với GeoJSON Point query, khoảng cách trong stage này thường có đơn vị **mét**, trừ khi chọn `distanceMultiplier` khác. `distanceField` là cách minh bạch để client nhận khoảng cách; trên một số phiên bản MongoDB mới có thay đổi về tính bắt buộc của field này, nên **vẫn chỉ định tường minh** để code dễ tương thích.

**Stage ordering:** `$geoNear` có yêu cầu xuất hiện **ở đầu pipeline** (sau một số ngoại lệ phiên bản như `$search` cần kiểm riêng). Đừng chèn `$match` trước `$geoNear` rồi tự kết luận lỗi index; sử dụng trường `query` của `$geoNear` để áp điều kiện lọc tenant/active. Không đặt `$near` trong `$match` aggregation: đó là query match execution operator bị hạn chế trong pipeline.

### 11.2. Java `NearQuery` và `MongoTemplate.geoNear`

```java
package com.example.geo;

import java.util.List;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.NearQuery;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class PickupDistanceService {

    private final MongoTemplate template;

    public PickupDistanceService(MongoTemplate template) {
        this.template = template;
    }

    public List<GeoResult<PickupPoint>> withDistance(
            String authorizedTenantId,
            double longitude, double latitude) {

        Query businessFilter = Query.query(
            Criteria.where("tenantId").is(authorizedTenantId)
                .and("active").is(true)
        );

        NearQuery near = NearQuery.near(
                new GeoJsonPoint(longitude, latitude),
                Metrics.KILOMETERS)
            .maxDistance(2)
            .query(businessFilter)
            .limit(10);

        GeoResults<PickupPoint> result =
            template.geoNear(near, PickupPoint.class);

        return result.getContent();
    }
}
```

Ở đây `maxDistance(2)` được diễn giải theo `Metrics.KILOMETERS` do `NearQuery` chọn, và `getDistance().getValue()` trong `GeoResult` biểu thị khoảng cách theo metric của kết quả — nên luôn kiểm response/metric nếu cần đổi sang mét để hiển thị. API minh họa rút gọn validation để tập trung vào `NearQuery`; service production phải kiểm tra tenant đã xác thực, longitude/latitude hữu hạn/hợp lệ, max radius và result limit như mục 9.

Lưu ý: Từ MongoDB 4.2, lệnh `geoNear` cũ bị loại bỏ; Spring Data MongoDB từ 2.2 chạy `MongoOperations.geoNear(...)` dựa trên **aggregation `$geoNear`**, không phải gửi lệnh server `geoNear` đời cũ. Vì vậy, khi nâng phiên bản hãy kiểm tra driver/Spring Data release thay vì dùng `runCommand({geoNear: ...})` từ tài liệu rất cũ.

### 11.3. `$near`, `NearQuery` và `$geoNear` khác gì?

| Cách dùng | Trả về | Có trường distance? | Giới hạn |
| --- | --- | --- | --- |
| `find({location: {$near: ...}})` | Documents gần → xa | Không tự thêm | Cần geo index, không dùng `$near` trong aggregation `$match` |
| `MongoTemplate.find(queryNear)` | `List<PickupPoint>` | Không tự thêm | Tương ứng `$near`/`$nearSphere` |
| `MongoTemplate.geoNear(NearQuery)` | `GeoResults<PickupPoint>` | `GeoResult.getDistance()` | Dựa trên aggregation `$geoNear` |
| `aggregate([{$geoNear: ...}])` | Documents + distance field nếu cấu hình | Có | Stage position/index/geometry restrictions |

Chỉ khi cần **độ gần và khoảng cách thực trả về** mới nên chấp nhận chi phí và độ phức tạp của `$geoNear`. Một danh sách “địa điểm trong vùng và sắp theo tên” thường chỉ cần `$geoWithin`.

## 12. Đơn vị khoảng cách: tổng kết để tránh sai gấp hàng nghìn lần

Một bảng đơn vị hữu ích:

| Dạng/Operator | Trường nhập | Đơn vị |
| --- | --- | --- |
| GeoJSON Point `coordinates` | `[lng,lat]` | Độ |
| GeoJSON `$near/$nearSphere` `$maxDistance` | `2000` | **Mét** |
| GeoJSON `$geoNear` `maxDistance` | `2000` | **Mét** |
| `$geoWithin/$centerSphere` | `radius` | **Radian** |
| `$geoWithin/$center` | `radius` | Đơn vị tọa độ planar |
| `$geoWithin/$box` | Hai góc | Đơn vị tọa độ planar |
| Legacy `$nearSphere` | `maxDistance` | Thường **radian** |
| `NearQuery` với `Metrics.KILOMETERS` | `maxDistance(2)` | **Km** ở API Java; Spring quy đổi khi build query |

### 12.1. Ví dụ đổi đơn vị an toàn

```java
public final class GeoDistanceUnits {

    private static final double EARTH_RADIUS_METERS = 6_378_137.0;

    private GeoDistanceUnits() {}

    public static double metersToRadians(double meters) {
        if (!Double.isFinite(meters) || meters < 0) {
            throw new IllegalArgumentException("meters không hợp lệ");
        }
        return meters / EARTH_RADIUS_METERS;
    }
}
```

Giá trị radius ở đây là xấp xỉ hình cầu, **không phải bán kính luôn chính xác** cho mọi phép đo ellipsoid. Một hệ thống cần độ chính xác địa chính/đo đạc pháp lý hoặc GPS có sai số cụ thể nên dùng phép đo/hệ tọa độ được chuyên gia GIS xác nhận.

### 12.2. Cùng một số có thể mang hai ý nghĩa rất khác

```text
GeoJSON $nearSphere:
    maxDistance = 2000  => khoảng 2 km

$geoWithin + $centerSphere:
    radius = 2000       => KHÔNG phải 2 km
    radius = 2000 / 6378137.0 => khoảng 2 km

Java NearQuery:
    near(geoPoint, Metrics.KILOMETERS).maxDistance(2)
    => mong muốn 2 km tại API Spring, framework quy đổi.
```

Đừng truyền trực tiếp một biến `radiusKm` vào `Criteria.withinSphere(new Circle(..., radiusKm))`. Trong ví dụ đó, radius **phải chuyển sang radian trước**.

## 13. Kết hợp điều kiện nghiệp vụ và những giới hạn của query

### 13.1. Tenant, trạng thái và vị trí

Với một ứng dụng đa tenant, geospatial predicate không thay thế authorization:

```javascript
db.pickup_points.find({
  tenant_id: "TENANT-A",
  active: true,
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7, 10.8],
        2000 / 6378137.0
      ]
    }
  }
})
```

Filter tenant được quyết định bởi **identity đã xác thực**; không đơn giản lấy tenant từ JSON của client. Để tối ưu query trên nhiều tenant, xét compound geospatial index và kiểm `explain`, nhưng vẫn đặt điều kiện tenant ở query bất kể optimizer chọn index nào.

### 13.2. `$or` với `$near` có giới hạn

Không dùng:

```javascript
// SAI: $or chứa near clause cùng nhánh bình thường.
db.pickup_points.find({
  $or: [
    {
      location: {
        $near: {
          $geometry: {
            type: "Point",
            coordinates: [106.7, 10.8]
          },
          $maxDistance: 2000
        }
      }
    },
    { featured: true }
  ]
})
```

MongoDB không cho một `$or` chứa `$near`/`$nearSphere` và những clause khác. Nếu nghiệp vụ là “điểm gần **hoặc** được quảng bá”, có thể thiết kế **hai truy vấn riêng** rồi hợp nhất có kiểm soát, hoặc dùng `$geoWithin` để diễn đạt điều kiện vùng không cần ranking. Khi hợp nhất, phải giải quyết dedupe, ordering và giới hạn kết quả.

`$geoWithin`/`$geoIntersects` có thể kết hợp với `$or` trong những tình huống phù hợp, nhưng mọi nhánh vẫn cần phân quyền và phải kiểm index.

### 13.3. `$text` và `$near` không dùng đồng thời

`$text` yêu cầu text index còn `$near` yêu cầu geospatial special index. MongoDB không cho kết hợp hai special-index operators này trong cùng query theo cách thông thường.

Thay vì:

```javascript
// SAI về restriction special indexes:
{
  $text: { $search: "coffee" },
  location: { $near: { /* GeoJSON query */ } }
}
```

Có thể lựa chọn:

- Tìm vùng bằng `$geoWithin` và lọc thêm thuộc tính từ khóa đã chuẩn hóa, khi đủ biểu đạt.
- Dùng hệ thống search có geospatial capabilities riêng (ví dụ Atlas Search với cấu hình/index phù hợp) và xác minh semantics.
- Tách hai bước “tìm candidate” và “xếp theo khoảng cách” có giới hạn tập kết quả, tránh đưa toàn bộ collection lên application.

**Đừng** tự chạy nhiều query rồi hợp nhất không giữ tenant filter và cho rằng đó là một cách “tối ưu” an toàn.

### 13.4. Geospatial search và pagination

`$near`/`$geoNear` sắp theo khoảng cách, nhưng khi nhiều điểm **bằng khoảng cách** hoặc dữ liệu thay đổi giữa hai request, page dùng `skip` có thể không ổn định. Với result set lớn:

1. Đặt `maxDistance`/vùng giới hạn để giảm candidate.
2. Dùng `limit` hợp lý.
3. Nếu cần order ổn định, xác định tie-breaker như `_id` sau khi có distance.
4. Khi API cần cursor pagination nghiêm ngặt, thiết kế một khóa thứ tự có thể so sánh và filter tiếp trang dựa trên các field đã tính; không đơn giản dựa vào `skip` vô hạn.
5. Nếu kết quả cần đúng “mười gần nhất” và có tie, công bố quy tắc xử lý distance gần bằng nhau.

### 13.5. `$geoWithin` không tự đặt thứ tự

`$geoWithin` có thể trả document theo thứ tự index/plan khác nhau giữa các lần query. Đừng mặc định đó là thứ tự gần nhất, thứ tự insert hoặc thứ tự ID. Thêm `sort` theo các field có index khi API cần thứ tự. Nếu muốn **sort theo khoảng cách thực**, dùng `$geoNear` hoặc tính distance và sort một cách tường minh.

## 14. `countDocuments`, `MongoTemplate.count` và transaction

### 14.1. Không đếm bằng `$near` trong `countDocuments`

MongoDB triển khai `countDocuments` qua aggregation, nên **không cho** các predicate `$near`/`$nearSphere` bên trong filter.

Ví dụ không đúng:

```javascript
// Không dùng $near trong countDocuments:
db.pickup_points.countDocuments({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7, 10.8]
      },
      $maxDistance: 2000
    }
  }
})
```

Nếu chỉ cần “có bao nhiêu địa điểm trong vòng 2 km?”, dùng `$geoWithin/$centerSphere`:

```javascript
db.pickup_points.countDocuments({
  tenant_id: "TENANT-A",
  active: true,
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7, 10.8],
        2000 / 6378137.0
      ]
    }
  }
})
```

**Đổi operator đồng nghĩa đổi ngữ nghĩa:** `$near` có sort theo gần nhất; `$geoWithin` không sort. Khi đếm theo vùng, ta không cần sort nên `$geoWithin` đúng ý định. Nếu yêu cầu “đếm 10 địa điểm gần nhất”, cần định nghĩa lại bài toán vì gần nhất thường có đủ 10 nếu dữ liệu trên toàn bộ collection không giới hạn.

### 14.2. Spring Data `count(...)` trong transaction

Trong transaction MongoDB, lệnh `count` cũ không được phép vì dựa trên collection metadata. Spring Data MongoDB chuyển `MongoTemplate.count(...)` sang aggregation `$match` + `$count` khi phát hiện transaction đang hoạt động.

Vì vậy, **query count chứa `Criteria.near(...)`/`nearSphere(...)` cần được đổi** sang `Criteria.within(...)` hoặc `withinSphere(...)` tương ứng:

```java
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

double radiusMeters = 2000;
Circle circle = new Circle(
    new Point(106.7, 10.8),
    radiusMeters / 6_378_137.0);

Query filter = Query.query(
    Criteria.where("tenantId").is(authorizedTenantId)
        .and("active").is(true)
        .and("location").withinSphere(circle)
);

long count = mongoTemplate.count(filter, PickupPoint.class);
```

Đây là query mẫu phù hợp với việc đếm trong vùng. Để chạy được trong một transaction, môi trường cần replica set/sharded cluster, transaction manager và collection/index sẵn sàng. Không mở một multi-document transaction dài chỉ để trả một tổng số cho dashboard khi không cần consistency mức đó.

### 14.3. `$near` không dùng trong `$match` aggregation

`$near` là match execution operator nhưng **không được phép trong aggregation pipelines**. Sai:

```javascript
db.pickup_points.aggregate([
  {
    $match: {
      location: {
        $near: {
          $geometry: {
            type: "Point",
            coordinates: [106.7, 10.8]
          }
        }
      }
    }
  }
])
```

Thay bằng **stage `$geoNear`** nếu cần nearest-first và distance, hoặc dùng `$match` với `$geoWithin` nếu chỉ cần lọc vùng. Với MongoDB transaction, hãy xác minh stage/operation cụ thể và server version trước khi mở transaction để làm search địa lý; không coi mọi aggregation đều được phép ở mọi topology.

## 15. Reactive MongoDB: `ReactiveMongoTemplate` và reactive repositories

Spring Data MongoDB có cùng nhóm geospatial predicates cho `ReactiveMongoTemplate`; `find` trả `Flux<PickupPoint>` thay vì `List<PickupPoint>`.

### 15.1. Reactive service lọc vùng

```java
package com.example.geo;

import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class ReactivePickupSearchService {

    private final ReactiveMongoTemplate template;

    public ReactivePickupSearchService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<PickupPoint> withinMeters(
            String authorizedTenantId,
            double longitude, double latitude,
            double radiusMeters) {

        if (authorizedTenantId == null
                || authorizedTenantId.isBlank()
                || !Double.isFinite(longitude)
                || !Double.isFinite(latitude)
                || longitude < -180 || longitude > 180
                || latitude < -90 || latitude > 90
                || !Double.isFinite(radiusMeters)
                || radiusMeters < 0 || radiusMeters > 50000) {
            return Flux.error(
                new IllegalArgumentException("Vùng tìm kiếm không hợp lệ"));
        }

        Circle circle = new Circle(
            new Point(longitude, latitude),
            radiusMeters / 6_378_137.0);

        Query query = Query.query(
            Criteria.where("tenantId").is(authorizedTenantId)
                .and("active").is(true)
                .and("location").withinSphere(circle)
        );

        query.limit(100);
        return template.find(query, PickupPoint.class);
    }
}
```

`Flux` là publisher; MongoDB query thường chỉ thực hiện khi có subscription. Đừng dùng `.block()`/`.collectList().block()` trong WebFlux handler chỉ để “trả cho controller”. Nếu cần DTO list, dùng `collectList()` và trả `Mono<List<...>>` ở rìa API, vẫn không blocking.

### 15.2. Reactive repository `Within`

```java
package com.example.geo;

import org.springframework.data.geo.Circle;
import org.springframework.data.mongodb.core.geo.GeoJsonPolygon;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactivePickupRepository
        extends ReactiveMongoRepository<PickupPoint, String> {

    Flux<PickupPoint> findByLocationWithin(Circle area);

    Flux<PickupPoint> findByLocationWithin(
        GeoJsonPolygon polygon);
}
```

Với reactive geo-spatial repositories, result wrapper `GeoPage`/`GeoResults` thường không được hỗ trợ vì việc tính sẵn average distance và count không phù hợp với deferred result. `Flux<PickupPoint>` hoặc `Flux<GeoResult<PickupPoint>>` có thể phù hợp theo method/API version. Nếu cần distance cụ thể, nên dùng `ReactiveMongoTemplate` với `NearQuery`/`geoNear` có contract rõ, không tự ép `Mono<GeoResults<T>>` vào reactive repository.

### 15.3. Reactive transaction không thay semantics của geospatial query

`ReactiveMongoTransactionManager` gắn session vào Reactor Context cho operation trong cùng transaction, nhưng **không làm `$near` được phép bên trong aggregation `$match`** và không đổi ràng buộc của `countDocuments`. Nếu chỉ cần tra cứu địa điểm, thường không cần transaction đa document; khi một luồng phải đọc location và update một tài nguyên nghiệp vụ, hãy xác nhận điều kiện cần cho update bằng **conditional query/CAS** thay vì tin rằng kết quả gần nhất từ request trước luôn còn hiệu lực.

## 16. Tối ưu hiệu năng: index, `explain` và bounding radius

### 16.1. Vì sao near search có thể chậm?

Một query `$near` có thể phải duyệt nhiều vùng index để tìm đủ điểm và đảm bảo thứ tự theo khoảng cách. Nếu không giới hạn `maxDistance`, việc lấy toàn bộ điểm gần → xa có thể tốn thời gian và tài nguyên lớn.

Nguyên tắc:

1. Đặt **bán kính hợp lý** theo nghiệp vụ, ví dụ 2–10 km cho điểm giao nhận nội đô, không lấy toàn cluster.
2. Đặt `limit` khi UI chỉ hiển thị top N.
3. Đảm bảo có **`2dsphere` index** trên đúng BSON path.
4. Kết hợp tenant/active filters đúng và cân nhắc compound index dựa trên đo lường.
5. Chỉ yêu cầu distance calculation khi API thật sự cần.
6. Tránh thêm một `sort` khác vào `$near` nếu muốn giữ xếp hạng nearest-first.
7. Không đọc toàn bộ result rồi lọc tenant/active trong Java; hãy filter ở MongoDB.

### 16.2. Kiểm `explain("executionStats")` ngoài transaction

```javascript
db.pickup_points.find({
  tenant_id: "TENANT-A",
  active: true,
  location: {
    $nearSphere: {
      $geometry: {
        type: "Point",
        coordinates: [106.7, 10.8]
      },
      $maxDistance: 2000
    }
  }
}).limit(10).explain("executionStats")
```

Những field/stage cần đọc tùy server/version/engine:

| Thành phần | Cách đọc |
| --- | --- |
| `winningPlan` | Planner chọn đường thực thi nào |
| `GEO_NEAR_2DSPHERE` hoặc stage địa lý tương ứng | Dấu hiệu dùng geo index/near plan |
| `IXSCAN`, `FETCH`, `COLLSCAN` | Index lookup, lấy document hay quét collection |
| `totalKeysExamined` | Số index entries được kiểm tra |
| `totalDocsExamined` | Số document được đọc |
| `nReturned` | Số document trả về |
| `executionTimeMillis` | Thời gian server quan sát trong explain; không thay toàn bộ API latency |

Với MongoDB release mới, tên stage/plan tree có thể khác; đừng assert cụ thể string `GEO_NEAR_2DSPHERE` trong test trên mọi phiên bản. Quan sát plan thực tế và so sánh với workload đại diện.

### 16.3. `$geoWithin` có thể không cần sort

Nếu API chỉ hỏi “điểm nào trong vùng”, query:

```javascript
db.pickup_points.find({
  tenant_id: "TENANT-A",
  location: {
    $geoWithin: {
      $centerSphere: [[106.7, 10.8], 2000 / 6378137.0]
    }
  }
})
```

không cần tính và sort distance; nó có thể ít tốn công hơn near search cùng bán kính, nhất là khi chỉ kiểm tra membership hoặc count. Tuy nhiên, điều đó **không bảo đảm `$geoWithin` luôn nhanh hơn**. Phải xem mật độ điểm, index, filter và query planner.

### 16.4. Có nhiều geospatial indexes thì sao?

Collection có thể chứa cả `location` và `serviceArea` đều có `2dsphere` indexes. Đối với `$geoNear`, chỉ rõ trường `key: "location"` để tránh chọn sai index hoặc lỗi khi server không xác định được geospatial index tương ứng.

```javascript
{
  $geoNear: {
    near: {
      type: "Point",
      coordinates: [106.7, 10.8]
    },
    key: "location",
    distanceField: "distanceMeters",
    spherical: true
  }
}
```

Giới hạn tốc độ và số kết quả nên được áp trong API; tránh để client truyền radius rất lớn hoặc result limit vô hạn.

## 17. Dữ liệu xấu, an toàn và các trường hợp ranh giới

### 17.1. Validate ở API và database

Mọi tọa độ gửi từ client cần được kiểm:

```java
public static void checkLngLat(double longitude, double latitude) {
    if (!Double.isFinite(longitude)
            || !Double.isFinite(latitude)
            || longitude < -180 || longitude > 180
            || latitude < -90 || latitude > 90) {
        throw new IllegalArgumentException(
            "Longitude/latitude không hợp lệ");
    }
}
```

Không chấp nhận `NaN`, `Infinity`, lat/lng đảo hoặc dữ liệu “địa chỉ đã geocode” nhưng không có nguồn/độ chính xác rõ. Cần validate GeoJSON type, cấu trúc coordinates, ring closure và topology của Polygon trước khi lưu.

MongoDB geospatial index thường **sparse-like** với field địa lý null/missing, nên document thiếu vị trí có thể không nằm trong index và không xuất hiện ở near search. Đừng tự suy ra “không tìm thấy” nghĩa là document không tồn tại; có thể nó có `location` thiếu/sai kiểu hoặc không được index.

### 17.2. Một điểm đứng đúng biên

Nếu người dùng ở gần ranh giới vùng giao hàng, sai số GPS (vài mét hoặc hơn) có thể khiến kết quả `within` thay đổi giữa hai lần đo. Kết quả geospatial query là quan sát dữ liệu tọa độ, **không phải chứng nhận chắc chắn về vị trí vật lý**.

Với quy tắc giao hàng quan trọng:

- Chọn policy rõ về boundary, tolerance/buffer và độ chính xác nguồn GPS.
- Cân nhắc lưu thêm vị trí đã xác minh/địa chỉ chuẩn hóa khi cần.
- Không dựa vào một phép `$geoWithin` đơn lẻ để quyết định khoản tiền/điều kiện pháp lý không thể đảo ngược.
- Nếu vùng có nhiều lỗ hoặc phần trùng, định nghĩa thứ tự ưu tiên vùng và cách xử lý overlap.

### 17.3. Antimeridian và vùng rộng hơn nửa địa cầu

Polygon đi qua kinh tuyến ±180° có thể gây kết quả khác nếu chỉ nối các điểm theo cách Euclid trên một bản đồ 2D. Với GeoJSON geospatial queries, MongoDB có quy tắc CRS/ring riêng; vùng lớn hơn một bán cầu có thể cần cấu hình strict winding CRS hoặc model thành nhiều polygon phù hợp. Hãy đọc tài liệu `$geoWithin`/`2dsphere` theo phiên bản và test ngay trên dữ liệu đi qua biên.

### 17.4. Tránh tự tính khoảng cách bằng công thức Euclid trên độ kinh/vĩ

Không dùng:

```java
double distance = Math.sqrt(
    Math.pow(lng1 - lng2, 2) +
    Math.pow(lat1 - lat2, 2)
);
// Giá trị là "độ" trong hệ tọa độ, KHÔNG phải mét.
```

Ở vĩ độ khác nhau, một độ kinh tuyến tương ứng quãng đường trên mặt đất rất khác nhau; ngay cả độ vĩ tuyến cũng không hoàn toàn giống mô hình phẳng cho mọi hệ quy chiếu. Với near search, dùng index/engine không gian của MongoDB hoặc thư viện GIS được xác thực theo yêu cầu.

### 17.5. Quyền riêng tư của dữ liệu vị trí

Tọa độ chính xác có thể là thông tin nhạy cảm. Với API địa điểm:

- Không log tọa độ GPS chính xác hoặc danh tính người dùng nếu không cần thiết.
- Áp quyền tenant và giới hạn truy vấn theo role.
- Đặt TTL/retention cho location history khi phù hợp, không giữ vô thời hạn theo mặc định.
- Giới hạn query radius và rate-limit để giảm nguy cơ dò tìm vị trí người dùng.
- Phân biệt **vị trí công cộng của cửa hàng** với **vị trí thời gian thực của cá nhân** về quyền truy cập.

## 18. Kiểm thử tích hợp: Near có thứ tự, Within chỉ lọc

Chỉ unit-test `Criteria`/`Query` không chứng minh geospatial index thực hoạt động. Cần chạy MongoDB thật trong **database test cô lập**, index được tạo trước query, và xác minh BSON cùng kết quả.

### 18.1. `@DataMongoTest` và seed các điểm tổng hợp

```java
package com.example.geo;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.index.GeospatialIndex;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class PickupGeoQueryIntegrationTest {

    @Autowired
    MongoTemplate template;

    @BeforeEach
    void prepareIsolatedTestCollection() {
        // CẢNH BÁO: chỉ chạy trên database test riêng!
        template.getCollection("pickup_points")
            .deleteMany(new Document());

        template.indexOps(PickupPoint.class)
            .ensureIndex(new GeospatialIndex("location")
                .typed(GeoSpatialIndexType.GEO_2DSPHERE)
                .named("pickup_location_2dsphere"));

        template.insertAll(List.of(
            new PickupPoint(
                "P-001", "TENANT-A", "Điểm A", true,
                new GeoJsonPoint(106.7000, 10.8000)),
            new PickupPoint(
                "P-002", "TENANT-A", "Điểm B", true,
                new GeoJsonPoint(106.7050, 10.8050)),
            new PickupPoint(
                "P-003", "TENANT-A", "Điểm C", false,
                new GeoJsonPoint(106.7300, 10.8300)),
            new PickupPoint(
                "P-004", "TENANT-B", "Điểm D", true,
                new GeoJsonPoint(106.7010, 10.8010))
        ));
    }

    @Test
    void nearSphereOrdersByDistanceAndFiltersTenant() {
        Query query = Query.query(
            Criteria.where("tenantId").is("TENANT-A")
                .and("active").is(true)
                .and("location")
                    .nearSphere(
                        new GeoJsonPoint(106.7000, 10.8000))
                    .maxDistance(2000)
        );

        List<PickupPoint> actual =
            template.find(query, PickupPoint.class);

        assertThat(actual).extracting(PickupPoint::getId)
            .containsExactly("P-001", "P-002");
    }

    @Test
    void withinSphereSelectsSameAreaWithoutDistanceRanking() {
        double radians = 2000.0 / 6_378_137.0;

        Query query = Query.query(
            Criteria.where("tenantId").is("TENANT-A")
                .and("active").is(true)
                .and("location")
                    .withinSphere(new org.springframework.data.geo.Circle(
                        new org.springframework.data.geo.Point(
                            106.7000, 10.8000),
                        radians))
        );

        List<PickupPoint> actual =
            template.find(query, PickupPoint.class);

        // Không assert thứ tự: $geoWithin không tự sort.
        assertThat(actual).extracting(PickupPoint::getId)
            .containsExactlyInAnyOrder("P-001", "P-002");
    }

    @Test
    void geoJsonMappingStoresLongitudeBeforeLatitude() {
        Document raw = template.getCollection("pickup_points")
            .find(new Document("_id", "P-001"))
            .first();

        assertThat(raw).isNotNull();
        Document loc = (Document) raw.get("location");
        assertThat(loc.getString("type")).isEqualTo("Point");
        assertThat(loc.getList("coordinates", Double.class))
            .containsExactly(106.7000, 10.8000);
    }
}
```

`template.getCollection(...).deleteMany(new Document())` xóa **toàn bộ document** trong collection test đang kết nối. Chỉ dùng trên MongoDB test chuyên dụng; không chạy trên production, database staging chung hoặc test suite song song dùng cùng collection. Nếu dự án dùng `GeoSpatialIndexType.GEO_2DSPHERE`/`GeospatialIndex` với API khác theo version, chỉnh đúng Javadoc; tuyệt đối không bỏ qua bước xác minh index.

### 18.2. Test dữ liệu khác đơn vị và điểm biên

Ngoài hai test chính, cần có những ca:

| Tình huống | Kỳ vọng |
| --- | --- |
| Point bằng hệt tâm | Near distance xấp xỉ 0, đứng đầu nếu không có điểm khác bằng |
| Điểm cách tâm ~700 m | Nằm trong radius 2 km |
| Điểm cách tâm ~4 km | Không nằm trong radius 2 km |
| Tenant khác gần hơn | Không xuất hiện trong result của tenant đang xác thực |
| `active=false` gần tâm | Không xuất hiện khi filter `active=true` |
| Ngay ngoài radius | Bị loại theo MongoDB semantics; dùng tolerance hợp lý trong test |
| Lat/lng bị đảo | Input validation từ chối khi vượt miền, hoặc test phát hiện sai vị trí |
| `NaN`/`Infinity` | Validation từ chối trước query |
| Thiếu index | Near query thất bại; migration readiness phát hiện |
| Polygon ring chưa đóng | Bị validation từ chối hoặc server báo lỗi theo type/version |
| `$geoWithin` kết quả khác order giữa hai run | Không assert thứ tự nếu không `sort` |
| Legacy pair và GeoJSON query | Test đơn vị/serialization theo type thực tế |

### 18.3. Test `GeoResults` theo metric

```java
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.NearQuery;

NearQuery near = NearQuery.near(
        new GeoJsonPoint(106.7, 10.8),
        Metrics.KILOMETERS)
    .maxDistance(2)
    .limit(10);

GeoResults<PickupPoint> results =
    template.geoNear(near, PickupPoint.class);

assertThat(results.getContent())
    .isNotEmpty();

GeoResult<PickupPoint> first = results.getContent().get(0);
assertThat(first.getContent().getId()).isEqualTo("P-001");
assertThat(first.getDistance().getValue())
    .isCloseTo(0.0, org.assertj.core.data.Offset.offset(0.001));
```

Đoạn này minh họa khối test với biến `template` đã được inject và fixture ở trên; nếu thêm các địa điểm trùng tọa độ, thứ tự hai điểm cùng distance có thể không cố định. `getDistance().getValue()` phản ánh metric của query; **không tự nhân 1000** nếu code đã chọn đơn vị m ngay từ đầu.

## 19. Bảng lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `$near` báo không có geo index | Chưa tạo `2dsphere` trên BSON field đúng | Kiểm tra `getIndexes()`, migration và đường field |
| Tìm gần nhưng trả điểm ở rất xa | Đảo lat/lng hoặc nhầm độ/mét/radian | Kiểm `GeoJsonPoint(x,y)` và biểu thức `$maxDistance` |
| `withinSphere` trả quá nhiều điểm | Đưa `radiusMeters` trực tiếp vào `Circle` | Chia cho bán kính Trái Đất để đổi sang radian |
| `within(Circle)` trả kết quả khác `withinSphere` | `$center` planar khác `$centerSphere` spherical | Chọn đúng mô hình hình học và đơn vị |
| `$near` có thứ tự sai sau khi thêm `sort` | Sort bổ sung thay distance ranking | Bỏ sort hoặc định nghĩa pipeline tính distance rồi sắp xếp |
| `$geoWithin` trả không theo độ gần | Within không tự xếp hạng | Dùng `$near`/`$geoNear` nếu cần ranking |
| `$geoIntersects` trả tuyến cắt vùng mà Within bỏ qua | Intersects cho phép geometry chỉ giao một phần | Chọn operator theo “giao” hay “nằm trọn” |
| Polygon không match dù nhìn đúng trên bản đồ | Ring chưa đóng, geometry lỗi/CRS không phù hợp | Validate GeoJSON, winding, holes và test |
| Kết quả sai gần ±180° | Vùng vượt antimeridian | Thiết kế Polygon/CRS đúng và dùng test biên |
| `$geoNear` bị lỗi nhiều geospatial indexes | Không rõ index location nào | Chỉ định `key: "location"` |
| `$geoNear` lỗi stage ordering | Đặt `$match`/stage khác trước `$geoNear` | Đặt `$geoNear` đúng vị trí, filter trong `query` |
| `$near` trong aggregation `$match` bị lỗi | `$near` không được dùng trong aggregation | Dùng `$geoNear` hoặc `$geoWithin` |
| `countDocuments` với `$nearSphere` bị lỗi | Count helper dùng aggregation | Đổi sang `$geoWithin/$centerSphere` |
| Repository `Near` trả khoảng cách khó hiểu | `Point` legacy/`GeoJsonPoint` và `Metric` khác nhau | Chọn type/metric rõ, test số đo thực |
| `NearQuery.maxDistance(2)` quá lớn hoặc quá nhỏ | Chưa chọn metric hoặc nhầm đơn vị | Truyền `Metrics.KILOMETERS` khi muốn km |
| Query dùng `$or` với near + nhánh khác bị lỗi | Giới hạn `$or`/near | Thiết kế lại query/merge có kiểm soát |
| Query dùng `$text` với near bị lỗi | Hai special-index requirements xung đột | Tách bước hoặc dùng search chuyên biệt |
| `2dsphere` index không bao phủ document | `location` thiếu, null, sai geometry hoặc sparse semantics | Kiểm schema, migration, dữ liệu lỗi |
| Repository trên nhiều tenant làm lộ địa điểm | Query derived chỉ có location, thiếu tenant filter | Thêm điều kiện tenant từ auth/service |
| `explain` có chi phí quét cao | Radius quá lớn, thiếu index/filter không selective | Giới hạn radius/limit và đo compound index |
| `GeoJsonPolygon` constructor báo lỗi | Ring chưa khép kín hoặc thiếu điểm | Dùng điểm đầu == điểm cuối, validate topology |
| Frontend truyền `lat,lng` nhưng server nhận `lng,lat` | Quy ước đặt tên không rõ | Dùng DTO tường minh và unit test serialization |
| Phân trang geosearch bị thiếu/lặp | Distance ties/dữ liệu đổi và deep skip | Tie-breaker, cap radius, chính sách cursor |
| Địa điểm “gần nhất” không phải đi nhanh nhất | Khoảng cách địa cầu khác đường bộ | Dùng routing/ETA service nếu mục tiêu là hành trình |

### Quy trình điều tra ngắn

1. **Xác nhận dữ liệu thật:** raw BSON `location` đang là GeoJSON Point hay legacy `[x,y]`? Có đảo longitude/latitude không?
2. **Xác nhận index:** xem `getIndexes()`, geospatial type, tên BSON field và trạng thái migration.
3. **In query thực tế:** kiểm `$geometry`, `$centerSphere`, giới hạn khoảng cách và tenant filter; tránh log tọa độ người dùng nhạy cảm.
4. **Kiểm tra operator:** có cần nearest-first không? Nếu chỉ đếm/lọc vùng, dùng Within.
5. **Kiểm tra đơn vị:** mét cho GeoJSON near, radian cho centerSphere, độ cho tọa độ.
6. **Xem explain ở ngoài transaction:** index nào được chọn, bao nhiêu keys/docs examined, latency thực tế.
7. **Kiểm test biên:** tâm, điểm ngoài bán kính, ring closure, tenant khác, ±180° và cập nhật dữ liệu đồng thời.

## 20. Bài tập thực hành và đáp án

### Bài tập 1. Near hay Within?

**Câu hỏi:** API chỉ cần trả tất cả điểm giao nhận trong bán kính 3 km để tô lên bản đồ, không cần thứ tự gần nhất. Chọn operator nào?

**Đáp án:** `$geoWithin` với `$centerSphere` (radius radian). `$near` không cần thiết vì nó tự sort theo khoảng cách. Vẫn nên có index địa lý và giới hạn số kết quả.

### Bài tập 2. Thứ tự tọa độ

**Câu hỏi:** Frontend gửi `latitude=10.8`, `longitude=106.7`. Mã nào tạo GeoJSON Point đúng?

**Đáp án:**

```java
GeoJsonPoint point = new GeoJsonPoint(106.7, 10.8);
```

Vì GeoJSON yêu cầu `[longitude, latitude]`.

### Bài tập 3. 2 km trong `$nearSphere`

**Câu hỏi:** Với GeoJSON Point và `2dsphere` index, `$maxDistance: 2000` bằng bao nhiêu km?

**Đáp án:** **2 km**, vì `$maxDistance` có đơn vị **mét** khi query dùng GeoJSON Point.

### Bài tập 4. 2 km trong `$centerSphere`

**Câu hỏi:** Có thể viết `$centerSphere: [[lng,lat], 2000]` để tìm trong 2 km không?

**Đáp án:** Không. Chuyển:

```javascript
const radians = 2000 / 6378137.0;
const filter = {
  location: {
    $geoWithin: {
      $centerSphere: [[106.7, 10.8], radians]
    }
  }
};
```

### Bài tập 5. Within(Circle) của repository

**Câu hỏi:** `findByLocationWithin(new Circle(new Point(...), 2))` có luôn là trong bán kính 2 km không?

**Đáp án:** Không. `Within(Circle)` thường tạo `$center` planar, radius theo đơn vị tọa độ. Với 2 km trên địa cầu, dùng `withinSphere` với radian hoặc một geospatial API được cấu hình rõ metric.

### Bài tập 6. Bị mất thứ tự

**Câu hỏi:** Vì sao `$near` rồi thêm `sort({name:1})` không còn trả nearest-first?

**Đáp án:** `$near` đã tạo thứ tự theo khoảng cách; `sort` bổ sung sắp lại theo tên. Nếu cần gần nhất, giữ order địa lý hoặc tạo `$geoNear` pipeline để quyết định tie-breaker rõ.

### Bài tập 7. Điểm trong Polygon

**Câu hỏi:** Kiểm tra các cửa hàng nằm trong GeoJSON Polygon đã khai báo, không cần sort theo khoảng cách, dùng gì?

**Đáp án:** `$geoWithin: {$geometry: polygon}`, hoặc `Criteria.where("location").within(geoJsonPolygon)`.

### Bài tập 8. Tuyến đường cắt vùng

**Câu hỏi:** Một `LineString` đi từ ngoài vùng vào rồi đi ra ngoài, có thể không thỏa `$geoWithin`. Operator đúng để phát hiện nó cắt vùng?

**Đáp án:** `$geoIntersects` với GeoJSON Polygon, và `2dsphere` index trên field tuyến đường.

### Bài tập 9. `countDocuments` và near

**Câu hỏi:** Vì sao `countDocuments({location: {$near: ...}})` bị từ chối?

**Đáp án:** Count helper dựa vào aggregation và không nhận `$near`/`$nearSphere`. Với bài toán “đếm điểm trong một bán kính”, đổi sang `$geoWithin` và `$centerSphere` đúng đơn vị.

### Bài tập 10. GeoNear aggregation

**Câu hỏi:** Khi cần trường `distanceMeters` cho từng địa điểm, `find` với `$near` có đủ không?

**Đáp án:** Không tự có field distance. Dùng `$geoNear` với `distanceField`, hoặc Spring Data `NearQuery`/`GeoResult.getDistance()`.

### Bài tập 11. Index bắt buộc

**Câu hỏi:** Với GeoJSON Point và `$near`, tạo loại index gì?

**Đáp án:** `{location: "2dsphere"}`. Không chỉ gắn annotation rồi cho rằng production đã có index.

### Bài tập 12. Legacy pair và GeoJSON

**Câu hỏi:** Vì sao `NearQuery.near(new Point(lng,lat))` có thể cho khoảng cách khác `NearQuery.near(new GeoJsonPoint(lng,lat))` nếu không chọn Metric?

**Đáp án:** Legacy pair và GeoJSON có cách biểu diễn và cách diễn giải đơn vị khác nhau (radian so với mét trong spherical near). Dùng đúng type và `Metrics.KILOMETERS`/`MILES` khi cần.

### Bài tập 13. Tenant khác rất gần

**Câu hỏi:** Một địa điểm của TENANT-B nằm cách khách hàng 100 m, một địa điểm của TENANT-A cách 500 m. API của TENANT-A có được trả địa điểm TENANT-B không?

**Đáp án:** Không. Geospatial query cần có tenant filter theo quyền đã xác thực. Không coi khoảng cách nhỏ là lý do bỏ qua authorization.

### Bài tập 14. Retry và GPS thay đổi

**Câu hỏi:** User gửi cùng một request hai lần nhưng vị trí GPS đã dịch vài mét; liệu kết quả nearest-first phải luôn giống nhau?

**Đáp án:** Không. Kết quả phụ thuộc tọa độ query, dữ liệu nguồn và trạng thái index; nếu cần phát lại chính xác một quyết định nghiệp vụ, phải lưu version/input/decision theo hợp đồng idempotency riêng, không dựa vào search luôn cố định.

### Bài tập 15. `$text` cùng `$near`

**Câu hỏi:** Có thể gộp `$text` và `$near` vào một query thông thường trên MongoDB không?

**Đáp án:** Không, do restriction của hai special indexes. Thiết kế query khác, dùng search engine có khả năng kết hợp text + geo, hoặc tách bước có giới hạn và test.

## 21. Checklist triển khai geospatial queries

1. **Mô hình dữ liệu rõ:** GeoJSON hay legacy? Có cần Point/Polygon/LineString?
2. **Longitude trước latitude:** validate miền giá trị và các giá trị non-finite.
3. **Chọn đúng geospatial index:** `2dsphere` cho GeoJSON/spherical, `2d` cho planar legacy.
4. **Migration index trước khi nhận request:** đừng chỉ dựa annotation `@GeoSpatialIndexed`.
5. **Chọn operator theo ý định:** nearest-first → Near; membership → Within; intersect → GeoIntersects.
6. **Đúng đơn vị:** GeoJSON Near theo mét; CenterSphere theo radian; legacy/Metric cần xác minh.
7. **Phân biệt `Circle` và `GeoJsonPolygon`:** Within(Circle) planar không phải WithinSphere(Circle).
8. **Đừng tự sort lại Near theo name** nếu cần thứ tự khoảng cách.
9. **Đừng dùng `$near` trong `$or` có thêm nhánh hay với `$text`.**
10. **Đừng dùng Near trong countDocuments/aggregation `$match`:** Within hoặc `$geoNear` tùy mục tiêu.
11. **Lọc tenant và quyền ngay trong query**, không làm ở Java sau khi tải dữ liệu.
12. **Giới hạn radius, limit và query time:** tránh toàn collection/distance sort quá lớn.
13. **Đặt `key` trong `$geoNear`** nếu collection có nhiều geospatial indexes.
14. **Khi cần distance trong response, dùng `NearQuery`/`$geoNear`** và quy định đơn vị rõ.
15. **Reactive chỉ thay dạng trả dữ liệu**, không thay query operator, index hoặc semantics.
16. **Xác minh BSON raw và explain:** tên field mapping, số keys/docs examined, geospatial plan.
17. **Kiểm tra Polygon hợp lệ:** ring closure, holes, winding, antimeridian, ranh giới và sai số.
18. **Không coi geodesic distance là driving time/route distance.**
19. **Test MongoDB thật:** gần/xa, tenant khác, active false, polygon, boundary và units.
20. **Có cơ chế dữ liệu vị trí an toàn:** privacy, retention, access control và rate limits.
21. **Đối chiếu đúng MongoDB/Spring Data version**, nhất là geospatial stage, transaction và repository API.

## 22. Tài liệu tham khảo

Những nguồn chính thức nên đối chiếu với phiên bản MongoDB/Spring Data đang dùng:

1. **MongoDB Manual — Geospatial Queries:** https://www.mongodb.com/docs/manual/geospatial-queries/
2. **MongoDB Manual — Geospatial Indexes:** https://www.mongodb.com/docs/manual/core/indexes/index-types/index-geospatial/
3. **MongoDB Manual — `$near`:** https://www.mongodb.com/docs/manual/reference/operator/query/near/
4. **MongoDB Manual — `$nearSphere`:** https://www.mongodb.com/docs/manual/reference/operator/query/nearSphere/
5. **MongoDB Manual — `$geoWithin`:** https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/
6. **MongoDB Manual — `$geoIntersects`:** https://www.mongodb.com/docs/manual/reference/operator/query/geoIntersects/
7. **MongoDB Manual — `$centerSphere`:** https://www.mongodb.com/docs/manual/reference/operator/query/centerSphere/
8. **MongoDB Manual — `$geoNear` aggregation:** https://www.mongodb.com/docs/manual/reference/operator/aggregation/geoNear/
9. **Spring Data MongoDB — Querying Documents:** https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html
10. **Spring Data MongoDB — Repository Query Methods:** https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html
11. **Spring Data MongoDB — Sessions & Transactions:** https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html
12. **Spring Data MongoDB — Criteria Javadoc:** https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Criteria.html
13. **Spring Data MongoDB — NearQuery Javadoc:** https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/NearQuery.html
14. **Spring Data MongoDB — GeoJsonPolygon Javadoc:** https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/geo/GeoJsonPolygon.html

Các trang `current` có thể mô tả API mới hơn version của dự án. Khi copy code, kiểm Javadoc theo đúng release Spring Data MongoDB và MongoDB server (đặc biệt với geospatial geometry parsing, `$geoNear` stage, indexing, transaction và unit conversion). Những tọa độ trong bài là **ví dụ tổng hợp**, không phải khuyến nghị địa điểm thực tế.

## 23. Kết luận

**`Near` và `Within` trả lời hai câu hỏi khác nhau:** `$near`/`$nearSphere` chọn các geometry gần tâm và **sắp từ gần đến xa**, còn `$geoWithin` lọc những geometry nằm **trong một vùng** mà không tự sắp xếp. Với đường/tuyến, `$geoIntersects` trả lời câu hỏi “có cắt/giao vùng không?”. Khi cần trường **khoảng cách thực tính**, chọn `$geoNear` hoặc `NearQuery`/`GeoResult`. Spring Data MongoDB cho phép diễn đạt các phép này qua `Criteria`, `MongoTemplate`, repository query methods và reactive template.

Để dữ liệu địa lý đúng và query chạy hiệu quả, hãy lưu GeoJSON với thứ tự **[longitude, latitude]**, tạo **`2dsphere` index** thực sự, chọn đúng đơn vị (**mét với GeoJSON Near, radian với `$centerSphere`**), kiểm soát tenant/radius/limit, và xác minh bằng `explain` cùng kiểm thử MongoDB thật. Đừng dùng `$near` trong `countDocuments`/aggregation `$match` hay ghép nó với các special-index operators không tương thích. Cuối cùng, cần test Polygon/antimeridian, hiểu sai số GPS và không đánh đồng khoảng cách trên địa cầu với hành trình giao thông.
