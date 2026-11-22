# Chỉ mục `2d` và `2dsphere` trong Spring Data MongoDB

Khi xây dựng chức năng “tìm cửa hàng gần tôi”, kiểm tra một điểm có nằm trong khu vực giao hàng hay tìm các tuyến đường cắt qua một vùng, ứng dụng cần truy vấn dữ liệu theo vị trí. **Spring Data MongoDB** cung cấp repository và `MongoTemplate` để làm việc với các truy vấn này; **MongoDB** sử dụng chỉ mục không gian để giới hạn số đối tượng cần xét và thực hiện các phép toán hình học phù hợp. Hai loại chỉ mục cần phân biệt là **`2d`** và **`2dsphere`**.

Sau bài học, bạn có thể chọn đúng loại chỉ mục, chuẩn hóa cấu trúc tọa độ, khai báo chỉ mục bằng MongoDB hoặc Spring Data MongoDB, viết truy vấn và đọc kế hoạch thực thi để kiểm tra hiệu năng.

## 1. `2d` và `2dsphere` giải quyết hai mô hình hình học khác nhau

| Tiêu chí | `2d` | `2dsphere` |
| --- | --- | --- |
| Mô hình | Mặt phẳng Descartes, khoảng cách Euclid | Bề mặt Trái Đất, phép tính hình cầu |
| Dữ liệu điển hình | Cặp tọa độ legacy `[x, y]` hoặc đối tượng có hai trường tọa độ | GeoJSON (`Point`, `LineString`, `Polygon`, …) và cặp tọa độ legacy hợp lệ |
| Trường hợp sử dụng | Tọa độ nội bộ trong sơ đồ kho, trò chơi hoặc mặt bằng | Địa điểm thực với kinh độ/vĩ độ, bán kính tìm kiếm, vùng địa lý |
| Truy vấn tiêu biểu | `$near` trên tọa độ phẳng; `$geoWithin` với `$box`, `$polygon` | `$near`, `$nearSphere`, `$geoWithin`, `$geoIntersects`, `$geoNear` với ngữ nghĩa địa lý phù hợp |
| Đơn vị khoảng cách | Đơn vị của hệ tọa độ nguồn | Với GeoJSON và `$near`/`$geoNear`: thường là **mét**; với một số cú pháp legacy hình cầu: **radian** |
| Cấu hình tùy chọn | Có thể cấu hình miền tọa độ bằng `min`, `max` | Được thiết kế cho kinh độ/vĩ độ theo GeoJSON/WGS84 |

**Quy tắc chọn nhanh:** Nếu tọa độ mô tả vị trí trên bản đồ thế giới, ưu tiên **GeoJSON + `2dsphere`**. Chỉ chọn `2d` khi bài toán thực sự làm việc trên mặt phẳng và đơn vị khoảng cách đã được định nghĩa trong ứng dụng. Không dùng công thức khoảng cách Euclid trực tiếp trên độ kinh/vĩ cho yêu cầu “cách nhau 2 km”: một độ kinh tuyến tương ứng với khoảng cách khác nhau tùy vĩ độ.

> Chỉ mục giúp MongoDB tìm ứng viên hiệu quả; nó không thay thế việc xác định đúng hệ tọa độ, đơn vị đo và điều kiện nghiệp vụ. Một kết quả “trả về nhanh” vẫn có thể sai nếu dữ liệu đảo kinh độ với vĩ độ.

## 2. Chuẩn hóa dữ liệu trước khi tạo chỉ mục

### 2.1. GeoJSON cho vị trí địa lý

GeoJSON `Point` có cấu trúc `{"type": "Point", "coordinates": [longitude, latitude]}`. **Thứ tự là `[kinh độ, vĩ độ]`**, không phải `[vĩ độ, kinh độ]`. Kinh độ nằm trong khoảng `[-180, 180]`, vĩ độ trong `[-90, 90]`; tọa độ GeoJSON địa lý dùng hệ tham chiếu WGS84.

Ví dụ ba địa điểm *giả lập* tại khu vực TP. Hồ Chí Minh:

```javascript
db.places.insertMany([
  {
    _id: "p1",
    name: "Quán A",
    category: "cafe",
    location: { type: "Point", coordinates: [106.7000, 10.7800] }
  },
  {
    _id: "p2",
    name: "Quán B",
    category: "cafe",
    location: { type: "Point", coordinates: [106.7070, 10.7830] }
  },
  {
    _id: "p3",
    name: "Cửa hàng C",
    category: "shop",
    location: { type: "Point", coordinates: [106.7600, 10.8300] }
  }
]);
```

Để mô tả một khu vực thay vì một điểm, GeoJSON sử dụng `Polygon`. Một vòng ngoài của polygon phải được **đóng**: tọa độ đầu và cuối của vòng trùng nhau. `LineString` biểu diễn đường; có thể dùng với truy vấn giao cắt hình học. Những kiểu này phù hợp với `2dsphere` khi ứng dụng cần đối chiếu hình dạng địa lý thực.

### 2.2. Tọa độ legacy cho mặt phẳng

Với sơ đồ mặt bằng dùng đơn vị mét do ứng dụng tự quy định, ta có thể lưu:

```javascript
db.flat_points.insertMany([
  { _id: "a1", name: "Kệ A", position: [10, 20] },
  { _id: "b1", name: "Kệ B", position: [13, 24] }
]);
```

Ở đây `[10, 20]` là `[x, y]` trên sơ đồ, **không** phải vị trí trên Trái Đất. Dù cặp tọa độ legacy cũng có thể biểu diễn kinh/vĩ, chỉ mục `2d` vẫn thực hiện các phép tính trên mặt phẳng. Tránh trộn GeoJSON và hệ tọa độ nội bộ trong cùng một trường.

## 3. Tạo và quản lý chỉ mục trong MongoDB

### 3.1. Tạo chỉ mục `2dsphere`

```javascript
db.places.createIndex(
  { location: "2dsphere" },
  { name: "location_2dsphere" }
);
```

MongoDB sử dụng dữ liệu hình học của `location` để hỗ trợ truy vấn gần, trong vùng và giao cắt. Đối với truy vấn thường xuyên lọc theo `category` đồng thời tìm vị trí, có thể **thử** chỉ mục ghép:

```javascript
db.places.createIndex(
  { category: 1, location: "2dsphere" },
  { name: "category_location_2dsphere" }
);
```

Hiệu quả của chỉ mục ghép tùy vào mẫu truy vấn, độ chọn lọc của `category` và dữ liệu thực; cần kiểm tra bằng `explain()` thay vì mặc định rằng chỉ mục ghép luôn tốt hơn. Trường `location` bị thiếu, `null` hoặc là mảng rỗng sẽ không có mục tương ứng trong chỉ mục `2dsphere`; chỉ mục này có hành vi *sparse* theo thiết kế. Với chỉ mục ghép chứa `2dsphere`, việc một document được đưa vào chỉ mục phụ thuộc vào trường không gian.

### 3.2. Tạo chỉ mục `2d`

```javascript
db.flat_points.createIndex(
  { position: "2d" },
  { name: "position_2d", min: -1000, max: 1000 }
);
```

`min` và `max` ở đây xác định miền giá trị tọa độ của chỉ mục phẳng; cần chọn theo miền `[x, y]` thực tế của dữ liệu. Đừng sao chép hai giá trị trên cho hệ kinh/vĩ hoặc cho mọi sơ đồ: một điểm nằm ngoài miền mà chỉ mục chấp nhận có thể làm thao tác ghi/chỉ mục thất bại.

### 3.3. Quan sát chỉ mục hiện có

```javascript
db.places.getIndexes();
db.flat_points.getIndexes();
```

Khi đổi một trường từ dữ liệu phẳng sang GeoJSON, cần **chuyển đổi dữ liệu, thêm chỉ mục phù hợp và kiểm tra truy vấn** trước khi loại bỏ chỉ mục cũ. Không coi việc đổi annotation trong Java là đủ để tự động chuyển kiểu dữ liệu hoặc xóa chỉ mục `2d` đã tồn tại trên cơ sở dữ liệu.

## 4. Khai báo chỉ mục với Spring Data MongoDB

Spring Data có `GeoJsonPoint` để biểu diễn một điểm GeoJSON và `@GeoSpatialIndexed` để mô tả chỉ mục trên thuộc tính của entity.

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexed;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "places")
public class Place {
    @Id
    private String id;

    private String name;
    private String category;

    @GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
    private GeoJsonPoint location;

    protected Place() {}

    public Place(String name, String category, GeoJsonPoint location) {
        this.name = name;
        this.category = category;
        this.location = location;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public String getCategory() { return category; }
    public GeoJsonPoint getLocation() { return location; }
}
```

Ví dụ khởi tạo entity:

```java
Place place = new Place(
    "Quán A", "cafe", new GeoJsonPoint(106.7000, 10.7800)
);
// placeRepository.save(place);
```

`GeoJsonPoint` giữ thứ tự tham số `(longitude, latitude)` và khi được ánh xạ sang MongoDB sẽ có `type: "Point"` cùng mảng `coordinates`. Nếu dùng tọa độ phẳng, có thể khai báo `@GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2D)` trên thuộc tính tương ứng; đồng thời phải bảo đảm kiểu dữ liệu lưu trong MongoDB tương thích với `2d`.

**Lưu ý về tạo index:** Annotation mô tả chỉ mục nhưng chỉ mục cần thực sự tồn tại trong MongoDB. Từ các phiên bản Spring Data MongoDB hiện đại, tự động tạo chỉ mục không được bật mặc định. Trong môi trường phát triển có thể cấu hình Spring Boot:

```yaml
spring:
  data:
    mongodb:
      auto-index-creation: true
```

Với hệ thống vận hành thật, nên quản lý việc tạo chỉ mục qua migration hoặc quy trình triển khai có kiểm soát. Nếu muốn tạo rõ ràng bằng `MongoTemplate`:

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.GeospatialIndex;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;

// mongoTemplate là bean MongoTemplate đã được cấu hình.
mongoTemplate.indexOps(Place.class).ensureIndex(
    new GeospatialIndex("location")
        .typed(GeoSpatialIndexType.GEO_2DSPHERE)
);
```

Chọn cơ chế quản lý index phù hợp với ứng dụng và xác nhận kết quả bằng `db.places.getIndexes()`. Nếu schema đã có index cùng trường nhưng khác kiểu hoặc khác tùy chọn, cần xử lý xung đột trong migration.

## 5. Truy vấn dùng `2dsphere`

### 5.1. Tìm các điểm gần một vị trí

Với GeoJSON và `2dsphere`, `$near` nhận `$geometry` là `Point`; `$maxDistance` và `$minDistance` được biểu diễn bằng **mét**:

```javascript
db.places.find({
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
}).limit(10);
```

Truy vấn trên lấy tối đa 10 điểm cách tâm không quá khoảng 2 km và trả kết quả theo khoảng cách tăng dần. Toán tử `$near` yêu cầu chỉ mục không gian thích hợp; nếu không có, truy vấn sẽ lỗi. Khi muốn vừa tính toán vừa trả khoảng cách đo được, có thể dùng aggregation `$geoNear` (xem mục hiệu năng).

Repository của Spring Data MongoDB hỗ trợ truy vấn được suy ra từ tên phương thức `Near`:

```java
import java.util.List;
import org.springframework.data.geo.Distance;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface PlaceRepository extends MongoRepository<Place, String> {
    List<Place> findByLocationNear(GeoJsonPoint center, Distance maxDistance);
}
```

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;

GeoJsonPoint center = new GeoJsonPoint(106.7000, 10.7800);
List<Place> nearby = placeRepository.findByLocationNear(
    center, new Distance(2, Metrics.KILOMETERS)
);
```

`Distance` với `Metrics.KILOMETERS` thể hiện đơn vị ngay tại nơi gọi API; Spring Data chuyển đổi theo ngữ nghĩa truy vấn geospatial được tạo ra. Cần dùng cùng kiểu tọa độ giữa thuộc tính entity, tham số truy vấn và chỉ mục, đồng thời kiểm tra truy vấn sinh ra khi nâng cấp phiên bản framework.

### 5.2. Lọc các điểm bên trong polygon

`$geoWithin` trả về điểm hoặc hình học nằm trong vùng được mô tả. Polygon bên dưới chỉ là vùng chữ nhật mẫu; phần tử đầu/cuối lặp lại để đóng vòng:

```javascript
db.places.find({
  location: {
    $geoWithin: {
      $geometry: {
        type: "Polygon",
        coordinates: [[
          [106.6800, 10.7600],
          [106.7300, 10.7600],
          [106.7300, 10.8100],
          [106.6800, 10.8100],
          [106.6800, 10.7600]
        ]]
      }
    }
  }
});
```

Khác `$near`, `$geoWithin` không sắp xếp kết quả theo khoảng cách. Truy vấn vùng có thể thực hiện mà không có index, nhưng thường cần index để hoạt động tốt khi tập dữ liệu lớn. Với dữ liệu đường, vùng hoặc đa giác, `$geoIntersects` là lựa chọn cho câu hỏi “hai hình có giao nhau không?”. Các phép toán vùng và giao cắt trên Trái Đất nên dùng `2dsphere` cùng GeoJSON.

### 5.3. Tính khoảng cách với `MongoTemplate`

Khi ứng dụng cần cả entity lẫn khoảng cách đến tâm, `MongoTemplate.geoNear` trả `GeoResults<Place>`:

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.NearQuery;

NearQuery query = NearQuery
    .near(new GeoJsonPoint(106.7000, 10.7800))
    .maxDistance(new Distance(2, Metrics.KILOMETERS))
    .spherical(true);

GeoResults<Place> results = mongoTemplate.geoNear(query, Place.class);
for (GeoResult<Place> result : results) {
    System.out.println(result.getContent().getName()
        + ": " + result.getDistance());
}
```

Đây là ví dụ cho `MongoTemplate` đã được inject. `GeoResults` cung cấp `getDistance()` theo quy tắc đơn vị của truy vấn Spring Data; khi cần hiển thị con số cho người dùng, kiểm tra đơn vị trong đối tượng `Distance` rồi quy đổi/định dạng rõ ràng.

## 6. Truy vấn dùng `2d` trên mặt phẳng

Với `flat_points` đã có index `position: "2d"`, MongoDB có thể tìm các kệ gần điểm `[10, 20]` trong bán kính 5 **đơn vị sơ đồ**:

```javascript
db.flat_points.find({
  position: {
    $near: [10, 20],
    $maxDistance: 5
  }
});
```

Khoảng cách của ví dụ này được tính từ cặp `[x, y]` theo hình học Euclid. Nếu sơ đồ quy định một đơn vị bằng một mét thì bán kính là 5 mét; nếu là pixel thì kết quả có bán kính 5 pixel. Không diễn giải nó thành “5 km trên bản đồ” khi dữ liệu không có phép quy đổi tương ứng.

Để tìm điểm trong một hình chữ nhật phẳng:

```javascript
db.flat_points.find({
  position: {
    $geoWithin: {
      $box: [[0, 0], [20, 30]]
    }
  }
});
```

`$box` thích hợp cho phép lọc mặt phẳng với tọa độ legacy. Khi nghiệp vụ chuyển sang khoảng cách trên Trái Đất, cần chuyển mô hình và chỉ mục sang GeoJSON/`2dsphere`, thay vì chỉ đổi toán tử truy vấn.

## 7. Kiểm tra hiệu năng bằng `explain()`

Giả sử ứng dụng tìm tối đa 10 quán cà phê trong vòng 2 km. Aggregation `$geoNear` phải xuất hiện ở **đầu pipeline** và có thể kết hợp bộ lọc thuộc tính:

```javascript
db.places.explain("executionStats").aggregate([
  {
    $geoNear: {
      near: { type: "Point", coordinates: [106.7000, 10.7800] },
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 2000,
      spherical: true,
      query: { category: "cafe" }
    }
  },
  { $limit: 10 }
]);
```

Với GeoJSON, `distanceMeters` biểu thị khoảng cách theo mét nếu không đặt `distanceMultiplier` để đổi đơn vị. Trong kế hoạch thực thi, tập trung vào index được chọn, số khóa và document được kiểm tra (`totalKeysExamined`, `totalDocsExamined`), số kết quả trả về (`nReturned`) và thời gian thực thi. Tên các stage có thể khác giữa các phiên bản MongoDB; quan sát index thực tế thay vì phụ thuộc vào một tên stage cố định.

Một số cách tối ưu thường hữu ích:

- Áp dụng bộ lọc nghiệp vụ đủ chọn lọc (`category`, trạng thái hoạt động, tenant) và thử chỉ mục ghép tương ứng; đo lại với phân phối dữ liệu thật.
- Giới hạn số kết quả khi màn hình chỉ cần các địa điểm gần nhất; trả những trường cần thiết, đặc biệt khi document có payload lớn.
- Tránh sắp xếp thêm theo trường khác sau `$near` nếu nghiệp vụ không yêu cầu: `$near` đã tạo thứ tự theo khoảng cách; sort bổ sung có thể tăng chi phí.
- Kiểm tra độ hợp lệ của hình học ngay khi ghi dữ liệu, cập nhật dữ liệu và chỉ mục khi mô hình thay đổi; tránh đưa toàn bộ dữ liệu không gian qua ứng dụng để tự tính khoảng cách.

## 8. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Không tìm thấy địa điểm gần tâm mong đợi | Đảo thứ tự vĩ độ/kinh độ, dữ liệu ngoài miền hợp lệ, dùng tọa độ khác hệ | Kiểm tra `[longitude, latitude]`, đọc document gốc và tạo truy vấn mẫu với điểm đã biết |
| `$near` báo thiếu geospatial index | Chưa tạo index hoặc index trên trường khác | Chạy `db.places.getIndexes()`; xác minh đúng đường dẫn thuộc tính và kiểu chỉ mục |
| Truy vấn 2 km lại trả phạm vi rất khác | Trộn mét, km, radian hoặc đơn vị tọa độ phẳng | Phân biệt GeoJSON/legacy; với Java dùng `Distance` và `Metrics` một cách nhất quán |
| Tạo index thất bại | GeoJSON sai cấu trúc, kinh/vĩ không hợp lệ, giá trị sai kiểu, tọa độ ngoài miền `2d` | Kiểm tra các document bị lỗi và validate schema trước khi tạo lại chỉ mục |
| Có document trong collection nhưng không xuất hiện trong index `2dsphere` | Trường vị trí thiếu, `null` hoặc rỗng; chỉ mục geospatial có hành vi sparse | Kiểm tra trường `location`, sửa dữ liệu hoặc định nghĩa rõ chính sách cho địa điểm chưa có tọa độ |
| Query chậm khi lọc thêm thuộc tính | Index không phù hợp với điều kiện thực tế, tập kết quả quá rộng | Đọc `executionStats`, thử index ghép và đo lại trên workload đại diện |

Ngoài ra, cần kiểm thử riêng các điểm nằm gần ranh giới polygon, đường đổi ngày quốc tế và các vùng rất lớn: hình học cầu có quy tắc bao vùng khác trực giác mặt phẳng. Với polygon thực tế, hãy chuẩn hóa thứ tự các đỉnh, vòng đóng và quy tắc biểu diễn trước khi lưu.

## 9. Bài thực hành tự kiểm tra

1. Tạo collection `places` với ba document GeoJSON ở mục 2 và chỉ mục `location_2dsphere` ở mục 3.
2. Chạy `$near` với tâm `[106.7000, 10.7800]`, bán kính `2000` mét. Dự kiến `p1` và `p2` nằm gần tâm, còn `p3` ở ngoài phạm vi; kiểm tra thứ tự theo khoảng cách.
3. Chạy `$geoWithin` cho polygon ở mục 5 và so sánh kết quả với `$near`: vùng địa lý và bán kính là hai điều kiện khác nhau.
4. Tạo `flat_points` và `position_2d`; thử `$near` tại `[10, 20]` với bán kính `5` đơn vị. Giải thích vì sao không thể tự gọi đó là “5 km”.
5. Dùng `db.places.getIndexes()` và `explain("executionStats")` để kiểm tra index của truy vấn `$geoNear`; thay đổi bộ lọc `category` và so sánh kế hoạch thực thi.

**Ghi nhớ:** `2d` phục vụ tọa độ phẳng, còn `2dsphere` phục vụ phép toán địa lý hình cầu. Với Spring Data MongoDB, mô hình dữ liệu (`GeoJsonPoint`), annotation/index thật trong MongoDB, toán tử truy vấn và đơn vị đo phải nhất quán thì cả kết quả lẫn hiệu năng mới đáng tin cậy.
