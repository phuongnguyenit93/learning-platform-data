# Truy vấn suy diễn với Point, Distance và GeoResults theo hỗ trợ

> **Chương:** Truy vấn không gian  
> **Module:** `SPRING_DATA_MONGODB`

Một ứng dụng giao nhận thường cần tìm điểm nhận hàng gần người dùng: “tìm các cửa hàng cách vị trí này tối đa 3 km và hiển thị khoảng cách đến từng cửa hàng”. Với Spring Data MongoDB, ta có thể khai báo phương thức repository như `findByLocationNear(Point, Distance)` để Spring Data **suy diễn truy vấn không gian** từ tên phương thức, thay vì tự viết MongoDB JSON cho mọi truy vấn. Nếu cần cả **khoảng cách tính được** của từng kết quả, cần chọn kiểu trả về `GeoResult<T>` hoặc `GeoResults<T>` đúng với repository imperative/reactive.

Các khái niệm dễ bị nhầm: `Point` chỉ giữ tọa độ, `Distance` chứa **giá trị và đơn vị đo/Metric**, còn `GeoResult<T>` và `GeoResults<T>` là **kết quả truy vấn có metadata khoảng cách**, không phải kiểu field GeoJSON được lưu trong MongoDB. Việc đặt sai thứ tự kinh độ/vĩ độ, dùng sai index `2d`/`2dsphere`, hoặc đọc sai đơn vị của `$geoNear` có thể khiến tìm kiếm sai bán kính dù code vẫn chạy.

Bài thuộc module `SPRING_DATA_MONGODB`: dùng Spring Data MongoDB kết nối, ánh xạ document và thao tác qua `MongoTemplate` hoặc repository; thực hành thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng. Chủ đề trực tiếp là **truy vấn suy diễn với `Point`, `Distance` và các kiểu trả kết quả địa lý theo mức hỗ trợ của framework**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định lúc nào phương thức repository `...Near(...)` và `...Within(...)` sinh ra truy vấn không gian.
2. Phân biệt `org.springframework.data.geo.Point` và `org.springframework.data.mongodb.core.geo.GeoJsonPoint` khi xây dữ liệu/toạ độ.
3. Dùng `Distance` với `Metrics.KILOMETERS`, `Metrics.MILES` và nhận biết cách metric làm thay đổi truy vấn cầu.
4. Khai báo `List<T>`, `GeoResults<T>` cho repository imperative; `Flux<T>`, `Flux<GeoResult<T>>` cho repository reactive, **không nhầm với `GeoResults<T>` reactive**.
5. Hiểu giá trị `GeoResult.getContent()`, `GeoResult.getDistance()` và `GeoResults.getAverageDistance()`, cùng giới hạn của số trung bình khi phân trang/lọc.
6. Tạo và xác minh index `2dsphere` đúng field, đúng BSON GeoJSON hoặc legacy coordinates.
7. Kết hợp tọa độ với lọc tenant/trạng thái, giới hạn kết quả, kiểm soát chi phí truy vấn, và tránh rò rỉ dữ liệu nhiều tenant.
8. Phân biệt derived `Near` với `Within`, `MongoTemplate.geoNear` và aggregation `$geoNear` khi yêu cầu vượt khả năng suy diễn.
9. Kiểm thử thứ tự kết quả, bán kính, metric và metadata khoảng cách bằng MongoDB test thực; nhận diện lỗi thông dụng.

## 2. Một tình huống xuyên suốt

Giả sử collection `pickup_points` chứa ba điểm nhận hàng. Mỗi document có `tenantId`, `active` và vị trí địa lý:

```javascript
// mongosh - dữ liệu minh họa, không phải hệ thống sản xuất.
db.pickup_points.insertMany([
  {
    _id: "PP-A",
    tenantId: "TENANT-A",
    name: "Kho A",
    active: true,
    location: {
      type: "Point",
      coordinates: [106.7009, 10.7769]
    }
  },
  {
    _id: "PP-B",
    tenantId: "TENANT-A",
    name: "Kho B",
    active: true,
    location: {
      type: "Point",
      coordinates: [106.7060, 10.7794]
    }
  },
  {
    _id: "PP-C",
    tenantId: "TENANT-B",
    name: "Kho tenant khác",
    active: true,
    location: {
      type: "Point",
      coordinates: [106.7010, 10.7770]
    }
  }
])
```

API được mong đợi:

```text
GET /pickup-points/nearby?longitude=106.7009&latitude=10.7769&radiusKm=3
    |
    v
Tenant được xác minh: TENANT-A
    |
    v
Find active pickup points near coordinate
    |
    +-- Kho A, khoảng cách ~0 km
    +-- Kho B, cách vài trăm mét
    +-- KHÔNG trả PP-C của TENANT-B
```

**Điều kiện bảo mật:** `tenantId` phải lấy từ ngữ cảnh đã xác thực hoặc được kiểm tra quyền ở service, không tin query parameter do client tự khai báo. Truy vấn không gian là một điều kiện **bổ sung**, không thay thế tenant filter hoặc authorization.

## 3. Ba loại dữ liệu khác nhau: tọa độ, khoảng cách, kết quả

| Kiểu | Package thường dùng | Đại diện cho | Không đại diện cho |
| --- | --- | --- | --- |
| `Point` | `org.springframework.data.geo.Point` | Cặp `x/y` để truyền tâm tìm kiếm | Đơn vị khoảng cách hoặc entity trả về |
| `GeoJsonPoint` | `org.springframework.data.mongodb.core.geo.GeoJsonPoint` | Hình học GeoJSON Point lưu/query theo hệ tọa độ địa lý | Một kết quả có khoảng cách |
| `Distance` | `org.springframework.data.geo.Distance` | Khoảng cách có value và `Metric` | Một point hoặc tọa độ |
| `Metric` / `Metrics` | `org.springframework.data.geo` | Hệ đo dùng để chuyển đổi giá trị | Hình học trên bản đồ |
| `GeoResult<T>` | `org.springframework.data.geo.GeoResult` | Một entity `T` và khoảng cách đến tâm | Một document MongoDB mặc định có distance field |
| `GeoResults<T>` | `org.springframework.data.geo.GeoResults` | Tập `GeoResult<T>` kèm khoảng cách trung bình | Flux/publisher streaming |
| `GeoPage<T>` | `org.springframework.data.geo.GeoPage` | Trang các GeoResult có metadata trang/khoảng cách nếu API hỗ trợ | Kiểu trả về hợp lệ cho reactive repository |

### 3.1. Kinh độ trước, vĩ độ sau

Trong hệ tọa độ địa lý GeoJSON (WGS84, các tọa độ kinh/vĩ độ), thứ tự là:

```text
[longitude, latitude]
     x         y
```

Ví dụ một điểm:

```java
import org.springframework.data.geo.Point;

Point center = new Point(106.7009, 10.7769);
// x = 106.7009: kinh độ
// y = 10.7769: vĩ độ
```

Không viết `new Point(latitude, longitude)` chỉ vì API frontend truyền `lat` trước. Một tọa độ đảo thứ tự đôi khi vẫn nằm trong khoảng số hợp lệ và trả các kết quả sai một cách âm thầm.

### 3.2. GeoJsonPoint cho dữ liệu GeoJSON

```java
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;

GeoJsonPoint location =
    new GeoJsonPoint(106.7009, 10.7769);
```

Khi Spring Data map một `GeoJsonPoint`, BSON lưu theo dạng:

```javascript
{
  location: {
    type: "Point",
    coordinates: [106.7009, 10.7769]
  }
}
```

Đây là **GeoJSON Point**. Trong khi đó một `Point` thông thường có thể được biểu diễn theo **legacy coordinate pair** `[x, y]` trong các đường mapping/query. Hai biểu diễn khác nhau dẫn tới các quy tắc về **đơn vị khoảng cách native**; phải chọn một hợp đồng nhất quán thay vì trộn tùy tiện.

### 3.3. Distance là một giá trị có Metric

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;

Distance radius = new Distance(3.0, Metrics.KILOMETERS);
Distance otherRadius = new Distance(2.0, Metrics.MILES);
```

`Metrics.KILOMETERS` và `Metrics.MILES` làm rõ **đơn vị mà caller dự định**. Spring Data sử dụng `Metric` để chuyển đổi tham số theo semantics truy vấn. Một số biểu diễn native của MongoDB dùng **radian**, trong khi GeoJSON và `2dsphere` thường gắn với **mét**; không coi số `3.0` trần là “3 km” trong mọi ngữ cảnh.

Khi cần giá trị:

```java
double number = radius.getValue();
// radius.getMetric() mô tả hệ đo tương ứng.
```

Đừng chuyển đổi bằng cách nhân “đại” 1000 hoặc 6378 trong nhiều chỗ. Giữ `Distance` rõ đơn vị tới ranh giới truy vấn, và kiểm thử đo thực tế đối chiếu với tọa độ.

## 4. Index địa lý là điều kiện tiên quyết

MongoDB `$near`/`$nearSphere` yêu cầu **geospatial index** thích hợp. Với document GeoJSON Point như `location` bên trên, lựa chọn thông dụng:

```javascript
db.pickup_points.createIndex(
  { location: "2dsphere" },
  { name: "idx_pickup_location_2dsphere" }
)
```

Để kiểm tra:

```javascript
db.pickup_points.getIndexes()
```

Nếu dùng model Java:

```java
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexed;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;

@GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
private GeoJsonPoint location;
```

Annotation mô tả index mong muốn trong mapping metadata; **đừng giả định index đã được tạo trên MongoDB**. Cơ chế auto-index creation của Spring Data có thể bị vô hiệu hóa theo mặc định/tùy cấu hình và phiên bản; quản lý index bằng migration hoặc gọi API bảo đảm index một cách có kiểm soát.

### 4.1. 2d và 2dsphere không phải hai tên thay thế

| Tính chất | `2d` | `2dsphere` |
| --- | --- | --- |
| Hình học chính | Tọa độ phẳng/legacy | Hình học trên mặt cầu |
| Phù hợp GeoJSON | Không phải lựa chọn chuẩn | **Có** |
| Truy vấn gần theo kinh/vĩ độ toàn cầu | Có giới hạn, tùy operator | **Thường chọn** |
| `$near` với legacy pair | Hỗ trợ theo quy tắc riêng | Có trường hợp hỗ trợ, cần đúng cách biểu diễn |
| `$nearSphere` và GeoJSON | Không dùng `2d` để thay `2dsphere` GeoJSON | Phù hợp |

Nếu collection dùng `GeoJsonPoint`, hãy ưu tiên `2dsphere` và viết test phản ánh chính xác operator/index. Không đưa GeoJSON vào collection đang chỉ có `2d` rồi mong các truy vấn hoạt động giống nhau.

### 4.2. Một field phải được index đúng tên BSON

Nếu model khai báo `@Field("pickupLocation")` nhưng bạn tạo index trên `location`, truy vấn có thể không dùng được index mong đợi. Hãy đối chiếu:

- Property Java đang được repository parse, ví dụ `location`.
- Tên field BSON sau `@Field`/converter, ví dụ `pickupLocation`.
- Tên field trên index thật từ `getIndexes()`.

Một lỗi thường gặp là test trên dữ liệu nhỏ chạy được `$geoWithin` nhưng đến `$near` mới gặp lỗi “unable to find index”, vì `$near` yêu cầu geospatial index thích hợp.

## 5. Model Java: PickupPoint và mapping GeoJSON

File `PickupPoint.java`:

```java
package com.example.delivery.pickup;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexed;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "pickup_points")
public class PickupPoint {

    @Id
    private String id;
    private String tenantId;
    private String name;
    private boolean active;

    @GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
    private GeoJsonPoint location;

    protected PickupPoint() {
        // Cho cơ chế materialization của Spring Data.
    }

    public PickupPoint(
            String id,
            String tenantId,
            String name,
            boolean active,
            GeoJsonPoint location) {
        this.id = id;
        this.tenantId = tenantId;
        this.name = name;
        this.active = active;
        this.location = location;
    }

    public String getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
    }

    public GeoJsonPoint getLocation() {
        return location;
    }
}
```

Model giữ `location` là một **GeoJSON Point** và mapping đến cùng tên field trên MongoDB. Đừng áp dụng hai kiểu biểu diễn khác nhau vào cùng một collection mà không có migration/đối chiếu dữ liệu. Những document thiếu `location` có thể bị loại khỏi geospatial index tùy semantics của `2dsphere`, nên các kết quả chỉ có thể đầy đủ nếu dữ liệu có vị trí hợp lệ.

### 5.1. Không biến GeoResult thành thuộc tính của entity

`GeoResult<PickupPoint>` được tạo **khi chạy truy vấn có tính khoảng cách**. Nó không có nghĩa cần thêm:

```java
private GeoResult<PickupPoint> location;
```

vào model. Một entity nên có `GeoJsonPoint location` cho vị trí; dữ liệu trả lời “cách tâm truy vấn bao xa” là **metadata của kết quả truy vấn**, thay đổi theo tâm tìm kiếm và không phải thuộc tính cố định của cửa hàng.

### 5.2. Entity GeoJSON và tham số Point là hai quyết định riêng

Repository có thể nhận `Point` làm **tâm query** trong khi field entity là `GeoJsonPoint`. Khi framework sinh query, biểu diễn tâm `Point`/`GeoJsonPoint` và `Distance/Metric` ảnh hưởng cách MongoDB giải nghĩa bán kính. Cần phân biệt:

1. **Kiểu dữ liệu của field**: GeoJSON lưu trong BSON document, đánh index `2dsphere`.
2. **Kiểu tham số tâm**: `Point` dùng ở API derived query; `GeoJsonPoint` dùng khi muốn làm rõ GeoJSON.
3. **Kiểu tham số khoảng cách**: `Distance` xác định giá trị cùng metric.
4. **Kiểu kết quả**: `List<T>` chỉ có entity; `GeoResults<T>` mang thêm distance.

Không chọn một kiểu trả về chỉ vì entity lưu GeoJSON. Đó là hai tầng không giống nhau.

## 6. Derived near query trả danh sách entity

Spring Data MongoDB nhận biết từ khóa `Near` trong tên method:

```java
package com.example.delivery.pickup;

import java.util.List;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface PickupPointRepository
        extends MongoRepository<PickupPoint, String> {

    List<PickupPoint> findByLocationNear(
        Point center,
        Distance maxDistance);
}
```

Lời gọi:

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;

Point center = new Point(106.7009, 10.7769);
Distance radius = new Distance(3, Metrics.KILOMETERS);

List<PickupPoint> places =
    repository.findByLocationNear(center, radius);
```

Trong đoạn này `repository` là bean `PickupPointRepository` đã inject. Tên property `Location` trong method được Spring Data ánh xạ tới `location` của entity, rồi chuyển sang geospatial query theo MongoDB operator tương ứng.

### 6.1. Ý nghĩa của hai tham số

- `center` là tọa độ x/y. Với dữ liệu địa lý: x = kinh độ, y = vĩ độ.
- `radius` là khoảng cách tối đa được chọn trong `Metric`. Ví dụ `3 KILOMETERS`.

Spring Data tạo truy vấn tìm những document gần tâm trong bán kính tương ứng, thường sử dụng `$near` hoặc `$nearSphere` tùy mapping/index/metric. Với `2dsphere` và metric cầu, cần kiểm tra toán tử được sinh trong driver logs/test thực để tránh suy đoán từ tên method.

### 6.2. List<PickupPoint> không có khoảng cách

Giả sử kết quả:

```text
PickupPoint("PP-A", "Kho A", location=...)
PickupPoint("PP-B", "Kho B", location=...)
```

`List<PickupPoint>` chỉ chứa entities. Không có `getDistance()` trên `PickupPoint` nếu class không khai báo property đó. Muốn UI hiển thị “Kho B cách bạn 0,6 km”, không nên tự giả định thứ tự trong list có thể thay thế một số đo khoảng cách.

Khi cần distance của từng entry, sử dụng **GeoResults** hoặc API `MongoTemplate.geoNear` phù hợp.

### 6.3. Near tự có ý nghĩa xếp theo khoảng cách

MongoDB `$near` trả các document **theo thứ tự gần đến xa**. Nhưng:

- Đừng thêm `Sort.by("name")` lên cùng query rồi kỳ vọng vẫn giữ thứ tự theo khoảng cách.
- Khi khoảng cách bằng hoặc rất gần bằng nhau, thứ tự giữa các document không nhất thiết ổn định nếu không có thêm quy tắc.
- Kết quả có thể thay đổi khi vị trí hoặc dữ liệu được cập nhật giữa các requests.
- Không suy ra tính hợp lệ của dữ liệu tenant từ thứ tự gần nhất.

### 6.4. Kết hợp điều kiện tenant và active

Trong ứng dụng multi-tenant, các ràng buộc không gian phải kết hợp **filter nghiệp vụ**. Ví dụ một phương thức khác:

```java
List<PickupPoint> findByTenantIdAndActiveTrueAndLocationNear(
    String permittedTenantId,
    Point center,
    Distance radius);
```

Đặt signature này trong `PickupPointRepository` ở trên nếu muốn sử dụng. Cấu trúc method thể hiện:

```text
tenantId == permittedTenantId
AND active == true
AND location NEAR(center, radius)
```

`permittedTenantId` phải được lấy từ authentication/authorization server. Đừng gọi hàm này với một tenant ID bất kỳ do client gửi rồi tin rằng phương thức derived query tự áp dụng phân quyền.

**Giới hạn:** khi query có nhiều điều kiện (tenant, active, geo), hãy kiểm tra JSON thực sự phát ra, explain plan và index; không mặc định mọi tổ hợp property/keyword ở mọi phiên bản đều có cùng tối ưu hóa hoặc thứ tự.

## 7. GeoResult<T> và GeoResults<T>: entity + distance

Một `GeoResult<T>` mang:

```text
GeoResult<PickupPoint>
    |
    +-- content  -> PickupPoint
    |
    +-- distance -> Distance
```

Một `GeoResults<T>` mang **nhiều GeoResult**:

```text
GeoResults<PickupPoint>
    |
    +-- getContent()
    |     +-- GeoResult<PickupPoint> #1
    |     +-- GeoResult<PickupPoint> #2
    |
    +-- getAverageDistance()
          +-- Distance (trung bình của các kết quả)
```

Với imperative Spring Data MongoDB, có thể khai báo:

File `PickupPointGeoResultsRepository.java`:

```java
package com.example.delivery.pickup;

import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface PickupPointGeoResultsRepository
        extends MongoRepository<PickupPoint, String> {

    GeoResults<PickupPoint> findByLocationNear(
        Point center,
        Distance maxDistance);
}
```

Đây là một **repository khác** với `PickupPointRepository` ở mục 6, dù cả hai cùng trỏ collection `pickup_points`. Ta tách interface bởi vì Java không thể có **hai method cùng tên, cùng tham số** nhưng chỉ khác **kiểu trả về**:

```java
// KHÔNG HỢP LỆ nếu cùng ở một interface:
List<PickupPoint> findByLocationNear(Point p, Distance d);
GeoResults<PickupPoint> findByLocationNear(Point p, Distance d);
// Java báo trùng signature; return type không phân biệt overload.
```

Trong sản phẩm thật, có thể chọn **một kiểu trả về phù hợp** hoặc dùng tên method/overload khác đã xác minh parser, không cần tạo nhiều repositories chỉ để trình diễn.

### 7.1. Đọc từng GeoResult và khoảng cách trung bình

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;

Point origin = new Point(106.7009, 10.7769);
Distance maxRadius =
    new Distance(3.0, Metrics.KILOMETERS);

GeoResults<PickupPoint> nearby =
    geoResultsRepository.findByLocationNear(
        origin, maxRadius);

for (GeoResult<PickupPoint> row : nearby.getContent()) {
    PickupPoint point = row.getContent();
    Distance distance = row.getDistance();

    System.out.printf(
        "%s, distance=%s, metric=%s%n",
        point.getName(),
        distance.getValue(),
        distance.getMetric());
}

Distance average = nearby.getAverageDistance();
System.out.println("Average = " + average);
```

`geoResultsRepository` là bean `PickupPointGeoResultsRepository` đã inject. Số đo trả về cần được **kiểm tra metric** thay vì in value trần với nhãn “mét” hoặc “km” tùy tiện.

### 7.2. Không nhầm average distance với một chỉ số cố định của toàn collection

`getAverageDistance()` nói về **các GeoResult thuộc GeoResults đang được xét**:

- Nếu query có bán kính 3 km, trung bình chỉ liên quan tới **những kết quả query trả về**.
- Nếu query có giới hạn hoặc trang, trung bình của trang **không nhất thiết là trung bình toàn bộ điểm trong 3 km**.
- Nếu collection có ít hoặc không có kết quả, code phải xử lý tập rỗng đúng theo API và không tự suy ra “điểm gần nhất cách 0”.
- Không dùng trung bình khoảng cách để suy ra toàn bộ các cửa hàng đáp ứng SLA giao hàng nếu chưa xét đường đi thực tế.

GeoResults cung cấp metadata tiện dụng, nhưng không phải công cụ đo thời gian lái xe, khoảng cách theo mạng đường phố hay vùng phục vụ trên thực tế.

### 7.3. GeoResults không phải MongoDB Document có field distance

Repository return `GeoResults<T>` có thể cần thực thi geo-near query/aggregation để tính khoảng cách. Không có nghĩa trong collection `pickup_points` tự xuất hiện:

```javascript
{ name: "Kho A", distance: 0.0 }
```

`distance` được tính từ **tâm của từng truy vấn**, thay đổi khi user di chuyển. Nếu muốn lưu một distance thường trực, phải xác định rõ distance **đến điểm tham chiếu nào**, không dùng nó như field không gian của entity gốc.

## 8. GeoPage, Pageable và giới hạn của pagination địa lý

Ở các API **imperative** có hỗ trợ, Spring Data Commons cung cấp `GeoPage<T>`, một `Page<GeoResult<T>>` có `getAverageDistance()`, `getContent()` cùng metadata trang. Ví dụ minh họa signature cần kiểm chứng với phiên bản Spring Data MongoDB của dự án:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoPage;
import org.springframework.data.geo.Point;

GeoPage<PickupPoint> findByLocationNear(
    Point center,
    Distance radius,
    Pageable pageable);
```

Signature đặt trong một imperative repository ở phiên bản hỗ trợ dạng return này; nó **không phải phương thức reactive**. Vì đường geo-near và trang hóa có thay đổi giữa các phiên bản Spring Data/MongoDB, phải chạy integration test trước khi chọn kiểu trả về làm hợp đồng API.

Ví dụ sử dụng ở lớp service (đã inject repository phù hợp):

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.geo.GeoPage;

GeoPage<PickupPoint> page =
    geoPageRepository.findByLocationNear(
        center,
        radius,
        PageRequest.of(0, 20));

page.getContent().forEach(row -> {
    System.out.println(row.getContent().getName());
    System.out.println(row.getDistance());
});
System.out.println(page.getAverageDistance());
```

Ở đây `geoPageRepository` là một interface riêng mà bạn khai báo với signature `GeoPage<PickupPoint>` ở trên (để tránh xung đột Java overload với hai repository demo trước).

### 8.1. Không nhầm tổng số và chi phí

Với các kiểu `Page`, framework thường cần biết tổng số phần tử — có thể phát sinh truy vấn đếm/chi phí bổ sung. Geospatial query có những giới hạn trong cách kết hợp `$near`, count, filter và geo-near pipeline, vì vậy **không mặc định** tổng số trang luôn được tính rẻ hoặc chuẩn trong mọi version.

Nếu UI chỉ cần “20 địa điểm gần nhất”, cân nhắc:

- Query có bán kính hợp lý.
- Giới hạn kết quả bằng `Pageable`/`Limit` được API hỗ trợ hoặc `NearQuery`.
- Không yêu cầu tổng số record khi UX không cần.
- Không sort lại theo tên nếu cần **distance ranking**.
- Kiểm tra tải và planner với dữ liệu thực.

### 8.2. Phân trang bằng offset trên tập kết quả di động

Giả sử user lấy trang 1, rồi có cửa hàng mới được thêm hoặc một vị trí đổi tọa độ; thứ tự gần-xa có thể thay đổi. Dùng trang 2 theo offset có thể **bỏ sót hoặc lặp** kết quả.

Không xem offset paging trong geo-near là snapshot bất biến. Nếu sản phẩm đòi hỏi danh sách nhất quán nhiều trang, cần thêm thiết kế snapshot/cursor, chính sách cập nhật vị trí hoặc một danh sách ID đã cố định theo phiên tìm kiếm; không thể bảo đảm điều ấy chỉ bằng `PageRequest.of(page, size)`.

### 8.3. GeoPage không phải GeoResults và không phải Pageable của Flux

| Kiểu | Metadata | Ngữ nghĩa |
| --- | --- | --- |
| `GeoResults<T>` | Danh sách có distance + average | Tập kết quả hoàn chỉnh đã materialize |
| `GeoPage<T>` | `Page<GeoResult<T>>` + average, page/total nếu được hỗ trợ | Một trang đã materialize |
| `Flux<GeoResult<T>>` | Mỗi item có distance; không có average mặc định | Dòng kết quả reactive |
| `Flux<T>` | Chỉ entity, không distance metadata | Dòng entity reactive |

**Một kiểu có tên “Geo” không tự có nghĩa hỗ trợ mọi phương thức repository.** Kiểm tra tài liệu của đúng Spring Data MongoDB version, đặc biệt khi chuyển synchronous code sang reactive.

## 9. Reactive repository: Flux<T> hoặc Flux<GeoResult<T>>

Trong repository reactive, Spring Data MongoDB hỗ trợ truy vấn không gian trả entity trực tiếp hoặc từng `GeoResult<T>`:

File `ReactivePickupPointRepository.java`:

```java
package com.example.delivery.pickup;

import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactivePickupPointRepository
        extends ReactiveMongoRepository<PickupPoint, String> {

    Flux<PickupPoint> findByLocationNear(Point center);

    Flux<GeoResult<PickupPoint>> findByLocationNear(
        Point center,
        Distance maxDistance);
}
```

Đây là hai signature khác nhau về **số tham số**, nên Java cho phép overload. Lệnh có `Point` và `Distance` được dùng để trả `GeoResult` có metadata khoảng cách. Nếu cần cùng hai tham số trả cả hai kiểu ở hai method, bạn phải tách repository hoặc chọn một interface tùy thiết kế.

### 9.1. Tại sao không trả Mono<GeoResults<T>>?

Spring Data MongoDB documentation nêu rõ **reactive repository geo-spatial queries không hỗ trợ `GeoResults<T>` và `GeoPage<T>` như return wrapper**, vì chúng thường yêu cầu tập hợp trước toàn bộ kết quả để tính khoảng cách trung bình/trang.

**Sai hoặc không được hỗ trợ theo hợp đồng reactive repository:**

```java
// KHÔNG dùng signature này như một reactive derived-query API.
Mono<GeoResults<PickupPoint>> findByLocationNear(
    Point center, Distance radius);

Mono<GeoPage<PickupPoint>> findByLocationNear(
    Point center, Distance radius, Pageable pageable);
```

Hai dòng trên là **phản ví dụ độc lập**, không đặt cùng một interface (chúng cũng cần import tương ứng nếu tự biến thành mã biên dịch). Ký hiệu `Mono<GeoResults<T>>` có thể là kiểu Java hợp lệ, nhưng **không phải kiểu Spring Data Reactive MongoDB repository tự hỗ trợ cho derived geo-near query**.

**Đúng:**

```java
Flux<GeoResult<PickupPoint>> findByLocationNear(
    Point center, Distance radius);
```

### 9.2. Reactive service tiêu thụ GeoResult

```java
package com.example.delivery.pickup;

import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public final class ReactivePickupSearchService {

    private final ReactivePickupPointRepository repository;

    public ReactivePickupSearchService(
            ReactivePickupPointRepository repository) {
        this.repository = repository;
    }

    public record NearbyPoint(
        String id, String name,
        double distanceValue, String distanceMetric) {}

    public Flux<NearbyPoint> search(
            double longitude, double latitude) {

        Point center = new Point(longitude, latitude);
        Distance max = new Distance(3, Metrics.KILOMETERS);

        return repository.findByLocationNear(center, max)
            .map(row -> {
                PickupPoint entity = row.getContent();
                Distance distance = row.getDistance();
                return new NearbyPoint(
                    entity.getId(),
                    entity.getName(),
                    distance.getValue(),
                    distance.getMetric().toString());
            });
    }
}
```

Service này chỉ minh họa **cách tiêu thụ Flux<GeoResult<T>>**. Trước khi đưa vào API công khai phải bổ sung validation tọa độ, giới hạn bán kính, authentication/tenant-scoped filter và phân quyền. Không trả toàn bộ collection chỉ vì có thể tạo một Flux.

### 9.3. Nếu cần average distance trong reactive

Bạn có thể chủ động materialize một **tập kết quả đã bị giới hạn** rồi tính trung bình theo metric thống nhất:

```java
import java.util.List;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.Metrics;
import reactor.core.publisher.Mono;

Mono<Double> averageKm = repository
    .findByLocationNear(
        new Point(106.7009, 10.7769),
        new Distance(3, Metrics.KILOMETERS))
    .take(100)
    .collectList()
    .map(rows -> rows.stream()
        .map(GeoResult::getDistance)
        .mapToDouble(distance ->
            distance.in(Metrics.KILOMETERS).getValue())
        .average()
        .orElse(Double.NaN));
```

Ở đây tính trung bình của **tối đa 100 entry được thu thập**, không phải toàn bộ collection. Nếu không có kết quả, trả `NaN` là một sentinel minh họa; API sản phẩm thường nên dùng `OptionalDouble`/nullable metric hoặc một response nói rõ không có dữ liệu. Đừng trả `0 km` vì sẽ bị hiểu nhầm “trung bình bằng 0”.

**Lưu ý:** `take(100)` là giới hạn **client-side trên Flux**; để giới hạn tải server/truyền mạng, ưu tiên API `Pageable`/`Limit` được hỗ trợ hoặc query có limit/bán kính. `collectList()` có memory cost, vì vậy không gom vô hạn chỉ để thay thế kiểu `GeoResults` imperative.

### 9.4. Với Pageable trong repository reactive

Tài liệu Spring Data cho biết reactive geo queries có thể nhận `Pageable` để giới hạn tập phát ra, nhưng **vẫn trả `Flux<T>` hoặc `Flux<GeoResult<T>>`**, không phải `Mono<GeoPage<T>>`:

```java
Flux<GeoResult<PickupPoint>> findByLocationNear(
    Point center, Distance radius, Pageable page);
```

Đây là một signature tùy chọn thay thế cho overload hai tham số ở trên khi cần. Khi dùng `PageRequest`, giới hạn/offset áp theo cơ chế query repository; phải kiểm thử chính phiên bản driver/framework đang chạy, giữ primary sort theo khoảng cách và biết dữ liệu di động có thể thay đổi thứ tự.

## 10. Truy vấn suy diễn Within khác Near

`Near` trả các điểm **gần tâm** và có semantics sắp theo khoảng cách. `Within` tìm document **nằm trong một hình học giới hạn**, không bắt buộc tính distance từng kết quả.

Ví dụ repository:

```java
import java.util.List;
import org.springframework.data.geo.Box;
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Point;

List<PickupPoint> findByLocationWithin(Circle circle);

List<PickupPoint> findByLocationWithin(Box box);
```

Với một `Circle`:

```java
Circle area = new Circle(
    new Point(106.7009, 10.7769), 0.01);

List<PickupPoint> points =
    repository.findByLocationWithin(area);
```

**Cảnh báo quan trọng:** `0.01` ở `Circle` không tự có nghĩa “0,01 km” hay “10 m”. Với legacy coordinate/spherical representations, radius có thể mang ngữ nghĩa đơn vị khác nhau. Nếu bài toán đòi hỏi bán kính 3 km và distance ranking, `Near` với `Distance(..., Metrics.KILOMETERS)` thường là điểm bắt đầu rõ hơn.

### 10.1. Box mô tả vùng tọa độ, không mô tả cự ly di chuyển

```java
Box box = new Box(
    new Point(106.6980, 10.7730),
    new Point(106.7090, 10.7830));

List<PickupPoint> inside =
    repository.findByLocationWithin(box);
```

Kết quả thể hiện điểm nằm trong hình chữ nhật theo tọa độ. Đừng gọi mọi điểm trong box là “cách user dưới 3 km”, vì góc của box có thể ở khoảng cách khác tâm và khoảng cách đường đi không đồng nhất với tọa độ.

### 10.2. Polygon và GeoJsonPolygon

Nếu vùng phục vụ là một polygon GeoJSON, Spring Data cung cấp các shape types như `GeoJsonPolygon` và method derived `...Within(GeoJsonPolygon)` trong những phiên bản hỗ trợ. Khi cần vùng phức tạp, lỗ polygon, giao nhau hoặc nhiều điều kiện đặc biệt, `Criteria` và aggregation có thể dễ kiểm soát hơn một derived method rất dài.

Đừng dùng `Near` để thay hoàn toàn bài toán “điểm nằm trong địa giới”, vì “gần ranh giới” và “nằm trong vùng được phép” là hai yêu cầu khác nhau.

## 11. Derived Near và MongoTemplate.geoNear

Khi cần lọc phức tạp, điều chỉnh `minDistance`, `maxDistance`, project distance field hoặc chọn index geospatial cụ thể, có thể chuyển từ repository method name sang `NearQuery` và `MongoTemplate`.

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.NearQuery;

Point center = new Point(106.7009, 10.7769);
NearQuery near = NearQuery.near(center)
    .maxDistance(new Distance(3, Metrics.KILOMETERS));

GeoResults<PickupPoint> result =
    mongoTemplate.geoNear(near, PickupPoint.class);
```

`mongoTemplate` là bean đã inject. Đây là API imperative. Nếu cần filter tenant trong `NearQuery`, dùng builder `query(Query)` với predicate đúng theo phiên bản API, thay vì lọc sau khi đã trả dữ liệu các tenants khác về application.

### 11.1. Vì sao Spring Data có hai đường?

| Vấn đề | Derived repository | MongoTemplate/NearQuery |
| --- | --- | --- |
| Tìm điểm trong bán kính | Ngắn và dễ đọc | Tường minh |
| Cần distance metadata | `GeoResults<T>` (sync) hoặc `GeoResult<T>` theo Flux (reactive) | `geoNear` / fluent geo near |
| Min/max distance, nhiều option | Tùy keyword/signature được hỗ trợ | Dễ khai báo trực tiếp hơn |
| Chọn geospatial index khi có nhiều index | Khó kiểm soát bằng tên method | Có thể dùng near query/aggregation tùy version |
| Kết hợp nhiều filter, projection | Method dài, dễ khó đọc | `Query`/aggregation rõ cấu trúc |
| Tính distance field trong pipeline | Không phải mục đích chính | `$geoNear`/aggregation |

### 11.2. Không dùng geoNear command đời cũ

MongoDB 4.2 đã loại bỏ **lệnh `geoNear` command cũ**. Spring Data MongoDB từ 2.2 chuyển `MongoOperations.geoNear(...)` sang dùng **aggregation stage `$geoNear`**. Không copy một driver command `db.runCommand({geoNear: ...})` từ hướng dẫn cũ rồi cho rằng vẫn chạy trên MongoDB hiện đại.

Trong aggregation, `$geoNear` phải là **stage đầu tiên**, có index không gian; khi có nhiều geospatial indexes, cần chỉ rõ field/index dùng theo API thích hợp. Ngoài ra, các operation có side effect như `$out`/`$merge` hoặc transaction có điều kiện hỗ trợ riêng, không mặc định là truy vấn đọc thuần.

### 11.3. Khi nào phải viết Criteria thay vì NearQuery?

Một yêu cầu như “tìm các cửa hàng **nằm trong địa giới** và có trạng thái mở cửa, nhưng không cần xếp theo khoảng cách” thường dễ diễn đạt bằng `Criteria.where("location").within(...)` hoặc `geoWithin`, với index/filter thích hợp, thay vì ép một geo-near query rồi sort lại.

Khi yêu cầu “trả nearest và khoảng cách từng kết quả”, chọn `GeoResults` hoặc `$geoNear`. Khi yêu cầu “chỉ lọc trong hình”, chọn `Within`/`$geoWithin`. Hai bài toán có thể trùng kết quả về mặt địa lý nhưng **khác semantics, chi phí và metadata**.

## 12. Thiết kế service tìm điểm nhận hàng gần nhất có validation

Đối với endpoint công khai, các bước phải có:

```text
Authentication/authorization
     |
     v
Trusted tenant ID
     |
     v
Validate coordinates and radius
     |
     v
Build NearQuery with tenantId and active=true
     |
     v
Limit results AT DATABASE
     |
     v
Map GeoResult<PickupPoint> to API DTO
```

### 12.1. DTO có nhãn đơn vị rõ ràng

File `NearbyPickupResponse.java`:

```java
package com.example.delivery.pickup;

public record NearbyPickupResponse(
    String id,
    String name,
    double distanceKm
) {}
```

Tên `distanceKm` trong response nói rõ đơn vị. Không trả `distance=0.5` không có đơn vị rồi để frontend tự suy đoán đó là kilômét, mét hay dặm.

### 12.2. Validator tọa độ và bán kính

File `GeoSearchInput.java`:

```java
package com.example.delivery.pickup;

public record GeoSearchInput(
    double longitude,
    double latitude,
    double radiusKm,
    int maxResults
) {
    public GeoSearchInput {
        if (!Double.isFinite(longitude)
                || longitude < -180 || longitude > 180) {
            throw new IllegalArgumentException(
                "Longitude phải nằm trong [-180, 180]");
        }
        if (!Double.isFinite(latitude)
                || latitude < -90 || latitude > 90) {
            throw new IllegalArgumentException(
                "Latitude phải nằm trong [-90, 90]");
        }
        if (!Double.isFinite(radiusKm)
                || radiusKm <= 0 || radiusKm > 25) {
            throw new IllegalArgumentException(
                "radiusKm phải trong (0, 25]");
        }
        if (maxResults < 1 || maxResults > 50) {
            throw new IllegalArgumentException(
                "maxResults phải trong [1, 50]");
        }
    }
}
```

Giới hạn `25 km` và `50 kết quả` chỉ là **policy ví dụ**, không phải giới hạn cứng của MongoDB. Dự án chọn giá trị từ SLA, dữ liệu và tải thực tế.

### 12.3. Service dùng MongoTemplate.geoNear với query+limit

File `NearbyPickupService.java`:

```java
package com.example.delivery.pickup;

import java.util.List;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.NearQuery;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public final class NearbyPickupService {

    private final MongoTemplate template;

    public NearbyPickupService(MongoTemplate template) {
        this.template = template;
    }

    public List<NearbyPickupResponse> findNearby(
            String authorizedTenantId,
            GeoSearchInput input) {

        if (authorizedTenantId == null
                || authorizedTenantId.isBlank()) {
            throw new IllegalArgumentException(
                "Tenant đã xác thực là bắt buộc");
        }
        if (input == null) {
            throw new IllegalArgumentException(
                "Thông số tìm kiếm là bắt buộc");
        }

        Point center = new Point(
            input.longitude(), input.latitude());

        Query filters = Query.query(
            Criteria.where("tenantId").is(authorizedTenantId)
                .and("active").is(true));

        NearQuery near = NearQuery.near(center)
            .maxDistance(new Distance(
                input.radiusKm(), Metrics.KILOMETERS))
            .in(Metrics.KILOMETERS)
            .query(filters)
            .limit(input.maxResults());

        GeoResults<PickupPoint> rows =
            template.geoNear(near, PickupPoint.class);

        return rows.getContent().stream()
            .map(row -> new NearbyPickupResponse(
                row.getContent().getId(),
                row.getContent().getName(),
                row.getDistance()
                    .in(Metrics.KILOMETERS)
                    .getValue()))
            .toList();
    }
}
```

Hàm `NearQuery.query(filters)` truyền các điều kiện tenant và `active` **vào truy vấn trên MongoDB**, không lọc sau khi dữ liệu của tenants khác đã được tải xuống. `limit(...)` giới hạn số kết quả ở đường query, thay vì gọi `rows.getContent().subList(0, 50)` sau khi server đã trả về một danh sách quá lớn.

### 12.4. Vì sao có cả maxDistance và in(Metrics.KILOMETERS)?

- `maxDistance(new Distance(..., Metrics.KILOMETERS))` nói về **bán kính tìm kiếm**.
- `in(Metrics.KILOMETERS)` yêu cầu **đơn vị cho khoảng cách kết quả** theo builder.

Hai quyết định có liên quan nhưng không đồng nhất. Khi dùng `NearQuery` với `Point` legacy-coordinate, metric cần xử lý đổi từ khoảng cách cầu tính bằng radian sang km. Với `GeoJsonPoint`, native unit của `$geoNear` là mét; không bỏ qua sự khác biệt khi thay kiểu tâm query.

Ví dụ code trên cố ý dùng `Point` và metric tường minh để nhất quán; hãy xác minh output mong đợi bằng test trên geospatial index/driver thực của dự án.

### 12.5. API không nên đưa ID tenant vào query string của user

Phản ví dụ:

```text
GET /pickup-points/nearby?tenantId=TENANT-B
```

Nếu controller lấy `tenantId` từ URL rồi truyền thẳng vào repository, caller có thể cố tình đọc vị trí kho của tenant khác. Lựa chọn đúng là xác minh tenant theo authentication context và role, hoặc dùng path tenant được kiểm tra quyền trước khi gọi service.

Các điểm nhận hàng có thể là dữ liệu nhạy cảm (kho nội bộ, địa điểm nhân viên). Phân quyền phải thực hiện ở service/query và không tiết lộ tọa độ không được phép qua exception, logging hay API.

### 12.6. Distance là cự ly địa lý, không phải quãng đường giao hàng

`$geoNear` tính khoảng cách theo mô hình không gian của MongoDB. Một địa điểm cách 500 m theo đường chim bay có thể cần đi vài kilômét do sông, cầu hoặc đường một chiều.

Nếu yêu cầu sản phẩm là **thời gian giao dự kiến/ETA**, có thể dùng geo-near để **lọc nhanh ứng viên**, sau đó dùng dịch vụ định tuyến (nếu được cấp quyền và phù hợp) cho nhóm ứng viên đã được lọc. Không gắn nhãn `estimatedTravelTime` cho một `Distance` nhận từ MongoDB.

## 13. Đơn vị đo: lỗi dễ gây sai kết quả nhất

MongoDB hỗ trợ:

- **Legacy pair** như `[106.7009, 10.7769]`.
- **GeoJSON Point** như `{"type":"Point","coordinates":[106.7009,10.7769]}`.

Khi chạy `$geoNear` theo hình học cầu:

| Tâm truy vấn | Diễn giải native distance phổ biến | Cách làm trong Spring Data |
| --- | --- | --- |
| Legacy `Point` / coordinate pair | Khoảng cách theo **radian** trên mặt cầu trong nhiều trường hợp | Dùng `Metric` để chuyển về km/miles theo builder |
| `GeoJsonPoint` / `$geometry` | Khoảng cách theo **mét** | Dùng tham số theo hợp đồng GeoJSON, không tự coi đơn vị là radian |
| `Distance(3, Metrics.KILOMETERS)` | Yêu cầu khoảng cách **3 km** ở lớp Spring | Để Spring xử lý chuyển đổi; test output và query thực |

**Không viết**:

```java
// PHẢN VÍ DỤ: thiếu Metric, rồi giả định max=3 có nghĩa 3 km.
Distance radius = new Distance(3);
```

`new Distance(3)` là một Distance dùng neutral metric. Trong một số đường query, số 3 có thể được hiểu theo native unit chứ **không phải km**. Luôn khai báo metric khi business requirement nói km/miles, trừ khi đang cố ý làm toán trên hệ tọa độ có unit khác đã được quy ước.

### 13.1. Kinh độ/vĩ độ không phải mét

`new Point(106.7009, 10.7769)` chứa góc theo hệ tọa độ địa lý; không có phép trừ đơn giản:

```java
double dx = other.getX() - center.getX();
double dy = other.getY() - center.getY();
double distanceInMeters = Math.sqrt(dx * dx + dy * dy);
// SAI: kết quả là độ tọa độ, không phải mét.
```

Khoảng cách theo kinh/vĩ độ không thể tính đúng bằng Euclidean distance trên đơn vị độ trong trường hợp tổng quát. Hãy dùng tính toán địa lý đúng hoặc MongoDB `2dsphere`, và kiểm chứng bằng các điểm đã biết.

### 13.2. So sánh minh họa giữa GeoJSON và legacy trong $geoNear

Với GeoJSON center:

```javascript
db.pickup_points.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      key: "location",
      spherical: true,
      maxDistance: 3000, // Mét với GeoJSON.
      distanceField: "distanceMeters",
      query: {
        tenantId: "TENANT-A",
        active: true
      }
    }
  },
  { $limit: 20 },
  { $project: {
      name: 1,
      location: 1,
      distanceMeters: 1
  }}
])
```

Ở ví dụ này `3000` là **3000 mét** do query sử dụng GeoJSON Point, `distanceMeters` cũng có ý nghĩa mét. Với legacy center trong `$geoNear`, trị số native có thể là **radian**; muốn output km cần conversion/distanceMultiplier theo kiểu query thích hợp. Đừng copy y nguyên `maxDistance: 3000` của GeoJSON sang legacy rồi tin cả hai giống nhau.

### 13.3. Đổi metric có thể đổi cả operator

Theo tài liệu Spring Data MongoDB, thêm `Distance` có một `Metric` có thể khiến derived query chuyển từ `$near` sang `$nearSphere`. Annotation `@GeoSpatialIndexed(type = GEO_2DSPHERE)` trên field cũng ảnh hưởng việc chọn operator cho query tương ứng. Vì vậy:

- Không khẳng định `Near` lúc nào cũng render thành một JSON duy nhất.
- Đối chiếu driver/server/MappingMongoConverter và Spring Data version khi nâng cấp.
- Kiểm thử **kết quả và khoảng cách** chứ không chỉ assert tên operator, trừ khi mục đích test là kiểm tra mapping.

### 13.4. Lọc maxDistance phải lấy đúng phần ngoài của hình

`$near` có thể trả ứng viên theo khoảng cách gần nhất tới geometry. Với dữ liệu là polygon hoặc multi-point, khoảng cách có thể dựa trên **điểm gần nhất của hình học** chứ không phải một centroid tự tính. Bài này dùng `GeoJsonPoint` để tránh lẫn semantics. Với dữ liệu polygon/line, phải định nghĩa rõ business distance muốn đo từ đâu.

## 14. Test địa lý phải kiểm chứng BSON, index và distance thật

Một unit test mock `PickupPointRepository` trả danh sách cố định không chứng minh:

- Spring Data có parse đúng `Near` và `Distance` hay không.
- Index `2dsphere` đã được tạo và được MongoDB chấp nhận hay chưa.
- Khoảng cách sử dụng **km**, **mét** hay **radian**.
- Thứ tự gần-xa được server tính theo vị trí thật.
- Lọc `tenantId` và `active` có thực thi ở database hay không.
- `GeoResults<T>` có chứa distance và average hợp lý hay không.

Cần integration test với một MongoDB **test database thực**, có index và dữ liệu được kiểm soát. Không cần bắt buộc replica set chỉ để thử phép đọc geo-near cơ bản; nếu toàn bộ ứng dụng dùng transaction thì test transaction cần topology hỗ trợ riêng.

### 14.1. Chuẩn bị repository có tenant filter

Để kiểm tra cả khoảng cách và bảo mật tenant, bổ sung signature vào `PickupPointGeoResultsRepository`:

```java
GeoResults<PickupPoint> findByTenantIdAndActiveTrueAndLocationNear(
    String authorizedTenantId,
    Point center,
    Distance radius);
```

Với `PickupPointRepository`, bổ sung một signature khác trả entity thường:

```java
List<PickupPoint> findByTenantIdAndActiveTrueAndLocationNear(
    String authorizedTenantId,
    Point center,
    Distance radius);
```

Hai method ở **hai interface khác nhau** nên không xung đột overload return type. Repository geo-near dùng filter tenant/active, còn API response nên chỉ phát thông tin đã được caller cấp quyền.

### 14.2. Test với @DataMongoTest (imperative)

Ví dụ Spring Boot 3.x, JUnit 5 và AssertJ. Test cấu hình `spring.data.mongodb.uri` ở **profile test**, trỏ đúng một database thử nghiệm chuyên biệt. Các import annotation/package có thể khác ở Spring Boot 4.x hoặc Spring Data major version khác; kiểm tra dependency thực tế trước khi biên dịch.

File `PickupPointGeoQueryIntegrationTest.java`:

```java
package com.example.delivery.pickup;

import com.mongodb.client.model.Filters;
import java.util.List;
import java.util.UUID;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class PickupPointGeoQueryIntegrationTest {

    @Autowired
    MongoTemplate template;

    @Autowired
    PickupPointRepository regularRepository;

    @Autowired
    PickupPointGeoResultsRepository geoRepository;

    @BeforeEach
    void ensureIndexExists() {
        // Chỉ chạy trong TEST database riêng.
        template.getCollection("pickup_points")
            .createIndex(new Document("location", "2dsphere"));
    }

    @Test
    void nearQueryRespectsTenantRadiusAndDistanceMetadata() {
        String suffix = UUID.randomUUID().toString();
        String tenant = "TENANT-TEST-" + suffix;

        String idHere = "HERE-" + suffix;
        String idNearby = "NEAR-" + suffix;
        String idFar = "FAR-" + suffix;
        String idOther = "OTHER-" + suffix;

        try {
            template.insertAll(List.of(
                new PickupPoint(
                    idHere, tenant, "Ngay tại tâm",
                    true, new GeoJsonPoint(106.7009, 10.7769)),
                new PickupPoint(
                    idNearby, tenant, "Gần tâm",
                    true, new GeoJsonPoint(106.7060, 10.7794)),
                new PickupPoint(
                    idFar, tenant, "Rất xa",
                    true, new GeoJsonPoint(106.8500, 10.9900)),
                new PickupPoint(
                    idOther, "OTHER-" + tenant, "Tenant khác",
                    true, new GeoJsonPoint(106.7010, 10.7770))
            ));

            Point center = new Point(106.7009, 10.7769);
            Distance radius =
                new Distance(3, Metrics.KILOMETERS);

            GeoResults<PickupPoint> geo =
                geoRepository
                    .findByTenantIdAndActiveTrueAndLocationNear(
                        tenant, center, radius);

            List<GeoResult<PickupPoint>> rows =
                geo.getContent();

            assertThat(rows).hasSize(2);
            assertThat(rows.get(0).getContent().getId())
                .isEqualTo(idHere);
            assertThat(rows.get(1).getContent().getId())
                .isEqualTo(idNearby);

            double nearestKm = rows.get(0).getDistance()
                .in(Metrics.KILOMETERS).getValue();
            double nextKm = rows.get(1).getDistance()
                .in(Metrics.KILOMETERS).getValue();

            assertThat(nearestKm)
                .isGreaterThanOrEqualTo(0.0)
                .isLessThan(0.05);
            assertThat(nextKm)
                .isGreaterThan(0.05)
                .isLessThan(3.0);
            assertThat(geo.getAverageDistance()
                .in(Metrics.KILOMETERS).getValue())
                .isBetween(0.0, 3.0);

            List<PickupPoint> plain =
                regularRepository
                    .findByTenantIdAndActiveTrueAndLocationNear(
                        tenant, center, radius);

            assertThat(plain).hasSize(2);
            assertThat(plain)
                .extracting(PickupPoint::getId)
                .containsExactly(idHere, idNearby);

        } finally {
            template.getCollection("pickup_points")
                .deleteMany(Filters.in(
                    "_id", idHere, idNearby, idFar, idOther));
        }
    }
}
```

Các giá trị kho A/B, tọa độ “gần” và “xa” được chọn cách biệt đủ lớn để không phải assert một cự ly tuyệt đối chính xác đến từng centimet. Thay vì viết `assertThat(nextKm).isEqualTo(0.623197...)`, test kiểm tra khoảng giá trị và thứ tự dự kiến.

### 14.3. Những điểm cần lưu ý trong test trên

1. **Index phải tồn tại trước query**. Annotation `@GeoSpatialIndexed` không tự chứng minh index đã có ở database.
2. **Database cô lập**. `@DataMongoTest` không tự tạo database cô lập nếu project đang dùng một URI trỏ dev/shared. Chỉ chạy khi profile test trỏ môi trường được cấp quyền.
3. **Bốn ID ngẫu nhiên**, cleanup theo ID cụ thể. Không `dropDatabase()` hoặc `deleteMany({})`.
4. Nếu có nhiều test cùng dùng database, createIndex trong `@BeforeEach` có thể đụng migration/index name/spec của test khác; nên tạo index trong fixture/migration trước tests cho ổn định.
5. `tenant` được tạo riêng để loại dữ liệu từ các tests khác.
6. `@DataMongoTest` chỉ kiểm thử configuration khi Spring đã scan đúng repository package; nếu project cấu hình repository scanning khác, có thể cần `@EnableMongoRepositories`/`@Import` phù hợp.
7. Mọi phép đo/geo-near đều phụ thuộc server version/index/query mapping; **chưa chạy test tại bước soạn nội dung**, không khẳng định kết quả môi trường thực khi chưa thực thi.

### 14.4. Test tọa độ bị đảo

Một kiểm thử unit cho validator:

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.junit.jupiter.api.Test;

@Test
void rejectsInvalidLatitudeAfterSwappingCoordinates() {
    assertThatThrownBy(() ->
        new GeoSearchInput(
            10.7769, 106.7009, 3.0, 20))
        .isInstanceOf(IllegalArgumentException.class);
}
```

Ở đây `latitude=106.7009` vượt `90` nên validator phát hiện sai. Nhưng nếu đảo tọa độ mà **cả hai số vẫn hợp lệ** trong khoảng cho phép, validator không thể tự biết tọa độ người dùng muốn nói là gì. API và frontend phải thống nhất hợp đồng `longitude`/`latitude` và test một điểm tham chiếu có vị trí đã biết.

### 14.5. Kiểm tra raw BSON sau insert

Nếu test chỉ assert entity từ `template.findById`, converter có thể che các khác biệt của BSON. Cần kiểm tra:

```java
Document stored = template.getCollection("pickup_points")
    .find(new Document("_id", idHere))
    .first();

assertThat(stored).isNotNull();
Document geoJson = stored.get("location", Document.class);
assertThat(geoJson.getString("type")).isEqualTo("Point");
assertThat(geoJson.getList("coordinates", Double.class))
    .containsExactly(106.7009, 10.7769);
```

Đây là một **đoạn bổ sung bên trong integration test** có `template`, `idHere` và imports tương ứng, không phải một class độc lập. Nó khẳng định field thật là GeoJSON `Point` và trật tự tọa độ đã ghi đúng. Nếu cấu hình converter tùy chỉnh, test sẽ phát hiện sự khác biệt ngay tại BSON.

### 14.6. Kiểm thử reactive bằng StepVerifier

Với reactive repository:

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import reactor.test.StepVerifier;

StepVerifier.create(
        reactiveRepository.findByLocationNear(
            new Point(106.7009, 10.7769),
            new Distance(3, Metrics.KILOMETERS)))
    .assertNext(first -> {
        assertThat(first.getContent()).isNotNull();
        assertThat(first.getDistance()).isNotNull();
    })
    .thenConsumeWhile(row -> row.getDistance() != null)
    .verifyComplete();
```

Đoạn nằm trong test có `reactiveRepository` và các imports đã được chuẩn bị. Test này chỉ minh họa **subscription và cách nhận GeoResult**; chưa kiểm tra tenant filter và expected IDs. Muốn bảo đảm correctness, dùng test reactive riêng có fixture giống imperative và kiểm tra IDs, thứ tự, metric, radius cùng chỉ mục thật.

Không dùng `Mono<GeoResults<T>>` làm return type derived reactive repository rồi mong `StepVerifier` giải quyết khả năng hỗ trợ bị thiếu. Nếu muốn trung bình, tính trên stream **có giới hạn** với semantics đã định nghĩa.

## 15. Giám sát index và chi phí truy vấn không gian

Geospatial query không đồng nghĩa “không cần index khác”. Với collection nhiều tenant và hàng triệu điểm, truy vấn tìm nearest trong một bán kính có thể vẫn gây tải lớn nếu điều kiện tenant/active không được hỗ trợ tốt bởi kế hoạch truy vấn.

### 15.1. Index đơn và compound

Index cơ bản:

```javascript
db.pickup_points.createIndex(
  { location: "2dsphere" },
  { name: "idx_geo_location" }
)
```

Một ứng viên compound cho query có tenant:

```javascript
db.pickup_points.createIndex(
  {
    tenantId: 1,
    active: 1,
    location: "2dsphere"
  },
  { name: "idx_tenant_active_geo" }
)
```

Đây là **ứng viên cần kiểm chứng**, không phải lựa chọn tốt nhất cho mọi workload. Thứ tự keys, cardinality tenant, tỉ lệ `active`, phân bố tọa độ và phiên bản MongoDB đều ảnh hưởng planner; đo bằng `explain()` trên workload đại diện.

Nếu ứng dụng cũng có query không gian không kèm tenant, cần cân nhắc thêm index phù hợp. Một compound index ràng buộc equality không thay thế mọi truy vấn đã tồn tại.

### 15.2. Một truy vấn MongoDB GeoJSON để đối chiếu

```javascript
const center = {
  type: "Point",
  coordinates: [106.7009, 10.7769]
};

db.pickup_points.find({
  tenantId: "TENANT-A",
  active: true,
  location: {
    $near: {
      $geometry: center,
      $maxDistance: 3000 // Mét với GeoJSON.
    }
  }
})
```

Lệnh này tương đương về **ý định nghiệp vụ** với “đọc điểm active của tenant A trong 3 km, sắp từ gần tới xa”. Không khẳng định JSON sinh từ mọi derived repository/version sẽ giống đúng từng token; khác biệt giữa `Point` legacy và `GeoJsonPoint`/Metric có thể làm serialization khác nhau.

### 15.3. Explain plan và số tài liệu đã quét

Trên database thử nghiệm:

```javascript
db.pickup_points.find({
  tenantId: "TENANT-A",
  active: true,
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      $maxDistance: 3000
    }
  }
}).explain("executionStats")
```

Những điểm cần quan sát tùy phiên bản server/explain format:

- Index nào được planner chọn và có đúng geospatial index không?
- `totalKeysExamined` / `totalDocsExamined` có cao bất thường so với số kết quả?
- Có additional sort/filter tốn tài nguyên sau geo query không?
- Latency thay đổi như thế nào khi bán kính tăng từ 1 km lên 25 km?
- Một tenant lớn có phân bố dữ liệu đặc biệt khiến query chậm hơn tenant khác không?

Không chỉ đánh giá từ test vài document. Query gần với bán kính lớn ở nơi có hàng chục nghìn địa điểm có thể trả rất nhiều dữ liệu, đặc biệt nếu API không có limit.

### 15.4. $near đã sắp theo khoảng cách

`$near` đã có thứ tự gần đến xa. Việc gắn `sort({name:1})` sau đó có thể gây **thêm một lần sort**, làm mất thứ tự gần nhất và tăng chi phí. Nếu muốn phân nhóm hoặc chọn tie-breaker, phải thiết kế lại mục tiêu sort và kiểm tra giá trị distance được tính:

```text
Near distance ranking:
  1. Kho A : 0.00 km
  2. Kho B : 0.63 km

Sort by name:
  ...không còn bảo đảm phần tử đầu là gần nhất...
```

### 15.5. $geoNear aggregation có ràng buộc riêng

Khi dùng `$geoNear` trong aggregation:

- `$geoNear` phải là **stage đầu tiên** của pipeline.
- Cần geospatial index, và có thể phải chọn field khi collection có nhiều geo indexes.
- Truy vấn lọc nghiệp vụ nên được đưa vào `query` của `$geoNear`/`NearQuery` khi phù hợp.
- Không nhét một `$near` predicate vào query nội bộ của `$geoNear`.
- Chỉ dùng `$limit`, `$project`, `$group`... sau stage địa lý theo thứ tự hợp lệ.

Trong MongoDB hiện đại, không dùng command `geoNear` đã bị loại bỏ. Các ví dụ Java cũ có nhắc `geoNear` đôi khi là **API method** `MongoTemplate.geoNear` (vẫn dùng được theo phiên bản hỗ trợ) chứ không phải command cũ. Phân biệt **tên API Java** và **lệnh BSON server**.

## 16. Các tình huống lỗi và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra/khắc phục |
| --- | --- | --- |
| `$near` báo không tìm thấy geospatial index | Thiếu `2dsphere` hoặc index tạo sai field | `getIndexes()`, đối chiếu BSON `location`, chạy migration index |
| Tất cả kết quả ở nơi rất xa | Đảo longitude/latitude | Xác minh `new Point(longitude, latitude)`; test tọa độ đã biết |
| Trả quá nhiều kết quả ngoài 3 km | Dùng số 3 không có metric hoặc sai native unit | Dùng `Distance(3, Metrics.KILOMETERS)`, test radius |
| Mức distance lớn hơn dự kiến ~1000 lần | Nhầm mét và kilômét khi dùng GeoJSON | Kiểm tra `getMetric()` và `NearQuery.in(...)` |
| Kho gần nhất trả distance không phải 0 dù tọa độ “giống nhau” | Khác precision/coordinate payload hoặc query center | Đọc raw BSON, so sánh x/y và rounding |
| `GeoResults` thiếu distance | Chọn `List<T>` hoặc query không tính khoảng cách | Đổi đúng return type/query path hỗ trợ `GeoResult<T>` |
| Repository reactive lỗi khi khai báo `Mono<GeoResults<T>>` | Return wrapper không được hỗ trợ trong reactive repository | Dùng `Flux<GeoResult<T>>` |
| `GeoPage` hoạt động khác kỳ vọng | Phiên bản framework/pagination/geoNear khác | Test integration của version; cân nhắc `NearQuery.limit` |
| `findByLocationWithin(Circle)` cho kết quả khác `Near` | Shape radius/unit khác, Within không phải distance ranking | Xác minh operator/đơn vị/tọa độ và test geometry |
| Không có kết quả với field GeoJSON | Dữ liệu lưu legacy sai hình hoặc index không phù hợp | Đọc raw Document `location`, inspect index |
| Có document thiếu location nhưng không xuất hiện | Geospatial index không bao gồm field thiếu/không hợp lệ | Chính sách data quality, kiểm tra import/migration |
| Truy vấn active/tenant chậm | Planner/index chưa tối ưu | Explain, compound index, giới hạn radius và result count |
| Dữ liệu tenant khác lọt vào API | Repository không có predicate tenant, hoặc filter sau truy vấn | Bắt buộc kiểm tra quyền và filter tại DB |
| `@GeoSpatialIndexed` đã đặt nhưng không thấy index | Auto-index creation chưa bật hoặc metadata chưa được apply | Migration/ensureIndex, `getIndexes()` |
| Query không gian trong aggregation lỗi | `$geoNear` đặt không phải stage đầu | Đưa `$geoNear` đầu pipeline |
| Query kết hợp `$near` với `$text` gặp lỗi | Hai operator cần special indexes không tương thích trực tiếp | Thiết kế search pipeline khác, không gộp tùy tiện |
| Nhiều geo indexes làm query mơ hồ | Không xác định field geo dùng cho `$geoNear` | Chỉ rõ index field/key bằng API được hỗ trợ |
| Chuyển driver/framework làm radius thay đổi | Mapping/operator/metric khác giữa các versions | Pin version và chạy regression tests trên DB thật |

### 16.1. JSON GeoJSON bị lưu thành string

Đây là lỗi dữ liệu phổ biến:

```javascript
// SAI: location là String chứa JSON.
{
  location:
    '{"type":"Point","coordinates":[106.7009,10.7769]}'
}
```

Đúng là một BSON document:

```javascript
{
  location: {
    type: "Point",
    coordinates: [106.7009, 10.7769]
  }
}
```

Một string có vẻ là JSON không tự được MongoDB hiểu thành GeoJSON. Cần parse/validate trước khi ghi hoặc migration dữ liệu đã lưu sai.

### 16.2. Không có kết quả không luôn là “không có cửa hàng”

Kết quả rỗng có thể do:

- Không có điểm nào trong bán kính.
- Lọc `tenantId/active` đúng nhưng điểm thuộc tenant khác.
- Document thiếu hoặc sai `location`.
- Client dùng tọa độ đảo hoặc radius quá nhỏ.
- Query dùng hình học đơn vị không mong đợi.
- Index/mapping sai, trong một số trường hợp sẽ báo lỗi chứ không trả rỗng.

Service nên phân biệt “không tìm thấy điểm phù hợp” với “request không hợp lệ” và “MongoDB operation lỗi”; không tự trả kết quả rỗng cho mọi exception.

### 16.3. Lỗi sai index không được giải bằng cách full collection scan

Khi `$near` không có index, cách đúng là tạo index phù hợp và xử lý dữ liệu sai. **Không** lấy toàn bộ collection qua `findAll()` rồi tính khoảng cách từng document trong Java để né index, đặc biệt với dữ liệu multi-tenant hoặc vài triệu bản ghi.

Nếu cần fallback trong tình huống đặc biệt, phải có giới hạn dataset, authorization, tài nguyên và SLA rõ. Một code fallback vô hạn rất dễ biến sự cố index thành sự cố quá tải toàn hệ thống.

### 16.4. Trường hợp không nên chọn nearest distance

Gần theo hình học chưa chắc là nơi tốt nhất:

```text
Kho A: cách 0.5 km nhưng đã đóng cửa
Kho B: cách 1.0 km nhưng còn hàng
Kho C: cách 0.7 km nhưng thuộc tenant khác
```

Sản phẩm phải lọc `active`, tồn kho, quyền truy cập, khu vực giao hàng, lịch mở cửa hoặc capacity **theo quy tắc nghiệp vụ**, chứ không chỉ xếp theo `GeoResult.getDistance()` rồi trả item đầu tiên.

## 17. Lựa chọn API theo bài toán

| Bài toán | API Spring Data khởi đầu | Kiểu trả về gợi ý |
| --- | --- | --- |
| Tìm entity trong bán kính, không cần distance số | Derived `findByLocationNear(Point, Distance)` | `List<T>` hoặc `Flux<T>` |
| Tìm gần nhất và hiển thị khoảng cách từng điểm | Derived geo-near có kết quả tính khoảng cách | `GeoResults<T>` sync, `Flux<GeoResult<T>>` reactive |
| Cần khoảng cách trung bình cho tập kết quả | `GeoResults` sync, hoặc tự tính trên reactive stream giới hạn | `Distance` / DTO metric rõ |
| Đòi hỏi `Page` có distance | `GeoPage` ở API sync được hỗ trợ | `GeoPage<T>`, test version/pagination |
| Chỉ kiểm tra nằm trong hình chữ nhật | `...Within(Box)` | `List<T>` / `Flux<T>` |
| Vùng polygon GeoJSON | `...Within(GeoJsonPolygon)` nếu hỗ trợ hoặc Criteria | `List<T>`/`Flux<T>` |
| Lọc tenant phức tạp, minDistance, limit, options | `MongoTemplate.geoNear(NearQuery)` | `GeoResults<T>` sync |
| Tính distance và pipeline aggregation phong phú | `$geoNear` aggregation | DTO projection có distance field |
| Đường đi/ETA | Geo-near chỉ lọc ứng viên | Kết hợp route service phù hợp |

**Gợi ý kiến trúc:** repository method name phù hợp khi truy vấn ngắn, rõ và ổn định. Khi method dài do nhiều filter và distance options, chuyển sang template/custom repository để reviewer thấy rõ query structure. Không ép mọi truy vấn thành một tên method derived hàng trăm ký tự.

## 18. Những hiểu nhầm cần loại bỏ

1. **“Point luôn là GeoJSON.”** Sai: `Point` có thể render thành legacy coordinates, `GeoJsonPoint` thể hiện GeoJSON.
2. **“x là latitude, y là longitude.”** Sai với WGS84 GeoJSON: x = longitude, y = latitude.
3. **“Distance(3) là 3 km.”** Sai nếu chưa có `Metric` hoặc policy đơn vị rõ.
4. **“GeoResults là field của entity.”** Sai: đây là wrapper của kết quả query.
5. **“Đổi List<T> thành GeoResults<T> có thể overload Java cùng signature.”** Sai: Java không phân biệt overload chỉ bởi return type.
6. **“Mono<GeoResults<T>> là return derived geo-query reactive hợp lệ.”** Không được Spring Data MongoDB reactive repository hỗ trợ theo tài liệu.
7. **“Reactive có GeoPage giống imperative.”** Không, reactive thường dùng `Flux<GeoResult<T>>` và tùy chọn Pageable.
8. **“Chọn @GeoSpatialIndexed là MongoDB có index ngay.”** Chưa chắc; kiểm tra DB/migration.
9. **“Near giống Within.”** Near có distance ranking, Within là kiểm tra không gian trong hình.
10. **“GeoPage average là trung bình mọi document.”** Chỉ tính theo content của trang/tập kết quả tương ứng, không mặc định toàn collection.
11. **“$geoNear đứng đâu trong pipeline cũng được.”** Sai: phải đứng đầu.
12. **“Tên geoNear trong Java luôn là command MongoDB cũ.”** Sai: API Spring hiện đại dùng aggregation `$geoNear`.
13. **“$near dùng chung $text sẽ tự kết hợp hai special indexes.”** Không; MongoDB có hạn chế khi kết hợp các special-index query operators.
14. **“Kho gần nhất chắc chắn giao nhanh nhất.”** Sai: địa hình, đường đi, tồn kho và giờ hoạt động còn quyết định.
15. **“Có tenantId trên entity là tự bảo mật.”** Sai: query và authorization phải áp đúng tenant.
16. **“getDistance().getValue() luôn là mét.”** Sai: xem `Metric` và cách tạo query.
17. **“Không thấy PP-B trong kết quả nghĩa là PP-B đã bị xóa.”** Chưa chắc: radius/filter/index/mapping có thể loại kết quả.
18. **“Có thể thay geo-index bằng tải toàn bộ collection về Java.”** Không phải giải pháp phù hợp cho dữ liệu lớn.

## 19. Checklist trước khi đưa geo-near API vào production

### 19.1. Mapping và kiểu dữ liệu

1. **Có hợp đồng tọa độ:** client/server cùng sử dụng `longitude, latitude` và WGS84.
2. **Kiểm tra miền giá trị:** longitude trong `[-180,180]`, latitude trong `[-90,90]`, loại bỏ `NaN`/`Infinity`.
3. **GeoJSON hay legacy?** Field lưu `GeoJsonPoint` hay `Point`? Đã kiểm tra raw BSON?
4. **Không lưu GeoJSON dưới dạng String** và không đảo trật tự `coordinates`.
5. **Có index phù hợp:** `2dsphere` cho GeoJSON; xác minh bằng `getIndexes()`.
6. **Có migration index được version hóa:** không chỉ dựa vào auto-index creation.
7. **Có data quality checks:** location thiếu/null/sai shape hoặc dữ liệu import từ hệ thống cũ.

### 19.2. Query và kết quả

8. **Chọn đúng semantics:** `Near` cần distance ranking, `Within` kiểm tra vùng.
9. **Gắn Metric tường minh:** `Distance(3, Metrics.KILOMETERS)` thay vì “số 3 bí ẩn”.
10. **Đọc đúng return type:** `List<T>` khác `GeoResults<T>` và `Flux<GeoResult<T>>`.
11. **Không áp GeoResults/GeoPage cho reactive repository** không hỗ trợ.
12. **Kiểm tra min/max distance:** đã chuyển đơn vị đúng với Point/GeoJSON?
13. **Xem planner:** query có dùng geospatial index đúng field không?
14. **Cố định giới hạn:** radius và max results đáp ứng SLA, không tải toàn bộ.
15. **Không sort sai:** giữ thứ tự gần-xa khi business cần nearest.
16. **Hiểu pagination:** trang theo offset trên dữ liệu thay đổi có thể bị lặp/thiếu.
17. **Biết average distance đại diện cho tập nào:** page, limit hay toàn kết quả.

### 19.3. Security, reliability và tests

18. **Filter tenant tại database:** không post-filter trong Java sau khi đã tải dữ liệu không được phép.
19. **Validate/authorize request:** không tin tenant ID do user tự khai báo.
20. **Kiểm soát location privacy:** không phơi địa điểm kho/người dùng trong logs.
21. **Error handling:** phân biệt input sai, thiếu index, MongoDB lỗi và kết quả trống.
22. **Có integration test MongoDB thật:** gần/xác tọa độ/xa/khác tenant/không active.
23. **Có regression tests khi nâng version:** operator, metric, mapping, query planner.
24. **Có monitoring:** geospatial query latency p95/p99, throughput, examined docs, radius/limit distribution.
25. **Có degrade mode hợp lý:** không tự scan toàn collection khi index chưa được tạo.

## 20. Bài tập thực hành

Một ứng dụng tìm trạm sạc xe điện có collection `charging_stations`. Mỗi trạm có `tenantId`, `available`, `connectorType` và `location`. UI cần hiển thị tối đa 10 trạm cách người dùng dưới 5 km, kèm khoảng cách theo km.

### Bài tập 1 — Tạo dữ liệu GeoJSON và index

Tạo ba trạm:

```javascript
db.charging_stations.insertMany([
  {
    _id: "CS-1",
    tenantId: "TENANT-EV",
    available: true,
    connectorType: "CCS2",
    location: {
      type: "Point",
      coordinates: [106.7009, 10.7769]
    }
  },
  {
    _id: "CS-2",
    tenantId: "TENANT-EV",
    available: true,
    connectorType: "CCS2",
    location: {
      type: "Point",
      coordinates: [106.7150, 10.7800]
    }
  },
  {
    _id: "CS-3",
    tenantId: "TENANT-EV",
    available: false,
    connectorType: "CCS2",
    location: {
      type: "Point",
      coordinates: [106.7000, 10.7770]
    }
  }
])

db.charging_stations.createIndex(
  { location: "2dsphere" },
  { name: "idx_charging_location" }
)
```

Hãy giải thích tại sao `CS-3` **không** nên xuất hiện khi yêu cầu chỉ tìm trạm khả dụng dù nó ở gần tâm hơn `CS-2`.

### Bài tập 2 — Derived repository

Khai báo entity `ChargingStation` với `GeoJsonPoint location`, `@GeoSpatialIndexed(type = GEO_2DSPHERE)` và method:

```java
List<ChargingStation>
    findByTenantIdAndAvailableTrueAndLocationNear(
        String tenantId,
        Point center,
        Distance radius);
```

Giải thích:

1. `Location` trong method name ánh xạ tới field nào?
2. `Point` khác `GeoJsonPoint` ra sao?
3. Bán kính nên truyền dưới dạng nào cho **5 km**?
4. Method có trả khoảng cách từng trạm không?
5. Tenant ID cần đến từ đâu?

### Bài tập 3 — GeoResults

Đổi sang một repository **imperative khác** với:

```java
GeoResults<ChargingStation>
    findByTenantIdAndAvailableTrueAndLocationNear(
        String tenantId,
        Point center,
        Distance radius);
```

Duyệt `getContent()`, truy cập `GeoResult.getContent()` và `getDistance()`, rồi trả DTO:

```json
{
  "id": "CS-2",
  "distanceKm": 1.6,
  "connectorType": "CCS2"
}
```

Giá trị `1.6` trong JSON **chỉ minh họa format response**, không phải kết quả tính chính xác của bộ dữ liệu trên. Trong test, dùng distance thực do MongoDB trả về.

### Bài tập 4 — Reactive repository

Với `ReactiveMongoRepository<ChargingStation,String>`, khai báo một phương thức trả:

```java
Flux<GeoResult<ChargingStation>>
    findByLocationNear(Point center, Distance radius);
```

Giải thích vì sao:

```java
Mono<GeoResults<ChargingStation>>
    findByLocationNear(Point center, Distance radius);
```

không phải return type derived reactive geo-query được hỗ trợ. Nếu muốn trung bình khoảng cách của **10 trạm gần nhất**, sẽ giới hạn và materialize stream ở đâu để tránh tốn memory/network?

### Bài tập 5 — Kiểm tra đơn vị đo

Lấy tâm `new Point(106.7009, 10.7769)` và so sánh:

```java
new Distance(5);
new Distance(5, Metrics.KILOMETERS);
new Distance(5, Metrics.MILES);
```

Hãy giải thích vì sao chỉ một trong ba trường hợp mô tả đúng yêu cầu **5 km**, và cách query builder xử lý metric native của MongoDB.

### Bài tập 6 — Near so với Within

1. Dùng `findByLocationNear(center, radius)` tìm trạm theo khoảng cách.
2. Dùng `findByLocationWithin(Box)` tìm trạm trong một vùng tọa độ.
3. Dự đoán sự khác nhau giữa kết quả và thứ tự.
4. Giải thích vì sao bounding box không đồng nghĩa “các trạm dưới 5 km”.
5. Nếu có vùng hạn chế đô thị dạng polygon, nên dùng `Within(GeoJsonPolygon)` hay `Near`?

### Bài tập 7 — GeoPage và hiệu năng

Một API dùng `GeoPage<T>` để trả tổng số trạm cùng các trang. Hãy phân tích:

- Query phải làm gì để tính total?
- Average distance có thể phản ánh **trang đang xem** hay toàn bộ tập?
- Khi thêm một trạm mới gần tâm giữa hai lần lấy trang, có thể lặp/bỏ sót kết quả không?
- Nếu UI chỉ cần 10 trạm đầu, liệu `NearQuery.limit(10)` phù hợp hơn việc đếm total?
- Với reactive repository, lựa chọn thay thế `GeoPage` là gì?

### Bài tập 8 — Lỗi production

Một ngày, API báo không tìm được geospatial index. Developer đề xuất:

```java
// PHẢN VÍ DỤ: quét toàn bộ collection trong service.
return repository.findAll().stream()
    .filter(station -> isNearInJava(station, center))
    .toList();
```

Giải thích vì sao giải pháp này sai cho collection lớn và không bảo đảm phân quyền/đơn vị. Đề xuất kế hoạch:

1. Dừng fallback không kiểm soát.
2. Kiểm tra `getIndexes()`/field mapping.
3. Kiểm kê dữ liệu GeoJSON lỗi.
4. Tạo index đúng qua migration được phép.
5. Chạy lại integration test và `explain("executionStats")`.
6. Theo dõi latency, số documents examined và số request thất bại.

### Bài tập 9 — Kiểm thử tính đúng của một điểm

Viết integration test trên MongoDB test:

- Seed một trạm **trùng tọa độ tâm**, một trạm cách vài trăm mét và một trạm rất xa.
- Thêm một trạm của tenant khác ngay sát tâm.
- Gọi repository gần tâm với bán kính 2 km.
- Assert trạm cùng tenant gần nhất đứng đầu, có khoảng cách gần 0.
- Assert trạm xa và trạm của tenant khác không xuất hiện.
- So sánh raw BSON với entity để xác nhận `location.type="Point"` và `coordinates[0]` là kinh độ.
- Không assert khoảng cách float chính xác đến quá nhiều chữ số; dùng tolerance hợp lý.

### Bài tập 10 — Khi nào đổi sang MongoTemplate

API mới yêu cầu:

```text
Input: tenantId đã xác thực, center, minKm, maxKm, maxResults
Filter: available=true, connectorType="CCS2"
Output: tối đa maxResults trạm, có khoảng cách theo km
```

Viết `NearQuery` với:

```java
NearQuery near = NearQuery.near(center)
    .minDistance(new Distance(minKm, Metrics.KILOMETERS))
    .maxDistance(new Distance(maxKm, Metrics.KILOMETERS))
    .in(Metrics.KILOMETERS)
    .query(Query.query(
        Criteria.where("tenantId").is(authorizedTenantId)
            .and("available").is(true)
            .and("connectorType").is("CCS2")))
    .limit(maxResults);
```

Giả định input đã được validate, `minKm >= 0`, `maxKm > minKm`, `maxResults` nằm trong giới hạn hệ thống. Giải thích vì sao logic này có thể dễ review hơn tên một derived method quá dài và vì sao filter phải nằm trong query server.

## 21. Câu hỏi ôn tập nhanh

| Câu hỏi | Gợi ý trả lời |
| --- | --- |
| Thứ tự GeoJSON coordinates? | `[longitude, latitude]` |
| Tìm cửa hàng gần nhất theo khoảng cách? | `Near` + geospatial index |
| Tìm điểm nằm trong polygon? | `Within`/`geoWithin` với geometry phù hợp |
| Bán kính 3 km trong Spring? | `new Distance(3, Metrics.KILOMETERS)` |
| Entity đơn thuần hay có distance? | `List<T>` vs `GeoResults<T>`/`GeoResult<T>` |
| Reactive trả GeoResults? | Không; dùng `Flux<GeoResult<T>>` theo hỗ trợ |
| Mean distance của GeoResults? | `getAverageDistance()` trên tập kết quả có mặt |
| Chỉ thêm @GeoSpatialIndexed là đủ? | Cần kiểm tra index thực đã tồn tại |
| $geoNear stage ở đâu? | Đầu pipeline aggregation |
| Tên geoNear Java = lệnh cũ MongoDB? | Không; Spring Data hiện đại dùng `$geoNear` stage |
| Có bảo mật tenant chỉ nhờ geospatial index? | Không; authorization + query tenant filter |
| Gần theo đường chim bay = ETA? | Không |

## 22. Tài liệu tham khảo

- Spring Data MongoDB — [MongoDB-specific Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): derived `Near`, `Within`, `Distance`/`Metric`, `GeoResults` và giới hạn reactive.
- Spring Data MongoDB — [Querying Documents — GeoSpatial and GeoNear](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): `Criteria`, `NearQuery`, `MongoTemplate.geoNear` và khác biệt GeoJSON/legacy.
- Spring Data MongoDB API — [NearQuery](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/NearQuery.html): `near`, `query`, `minDistance`/`maxDistance`, `in`, `limit`, `with(Pageable)`.
- Spring Data Commons — [GeoResults](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/geo/GeoResults.html): `getContent`, `getAverageDistance`.
- Spring Data Commons — [GeoPage](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/geo/GeoPage.html): page metadata và average distance.
- Spring Data MongoDB — [Repository Query Return Types](https://docs.spring.io/spring-data/mongodb/reference/repositories/query-return-types-reference.html): geo result/page wrappers theo store support.
- MongoDB Manual — [`$near`](https://www.mongodb.com/docs/manual/reference/operator/query/near/): yêu cầu index, thứ tự gần-xa, coordinate order và distance units.
- MongoDB Manual — [`$geoNear` aggregation stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geonear/): stage đầu tiên, metadata distance và query restrictions.
- MongoDB Manual — [Geospatial Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/): `2d`, `2dsphere` và cân nhắc index.
- MongoDB Manual — [`$geoWithin`](https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/): hình học vùng, khác với nearest-distance sort.

## Ghi nhớ

**`Point` xác định tâm tọa độ (longitude trước latitude), `Distance` xác định bán kính và metric, còn `GeoResult<T>`/`GeoResults<T>` mang kết quả kèm khoảng cách — ba vai trò khác nhau.** Với Spring Data MongoDB imperative, một derived `Near` có thể trả entity hoặc `GeoResults<T>` theo kiểu khai báo phù hợp; với reactive repository, dùng `Flux<T>` hoặc `Flux<GeoResult<T>>` chứ **không** dùng `Mono<GeoResults<T>>`/`GeoPage<T>` làm return wrapper được suy diễn. Muốn query đúng, dữ liệu GeoJSON phải có index `2dsphere`, tọa độ phải giữ đúng thứ tự, `Distance` phải có `Metric` tường minh và các filter tenant/active phải được thực thi ở MongoDB. Khi yêu cầu giới hạn/filter phức tạp, dùng `NearQuery`/`MongoTemplate.geoNear` và kiểm thử trên MongoDB thật để xác nhận BSON, index, radius, thứ tự và khoảng cách.
