# Geo distance sort và thứ tự theo khoảng cách

Elasticsearch có thể sắp xếp kết quả tìm kiếm theo khoảng cách giữa một vị trí tham chiếu và field địa lý của từng document. Tính năng này thường dùng cho tìm kiếm địa điểm gần nhất, cửa hàng quanh người dùng, trạm giao hàng, bệnh viện hoặc thiết bị gần một tọa độ. Trong Query DSL, kiểu sắp xếp này có tên `_geo_distance`.

Spring Data Elasticsearch cung cấp `GeoDistanceOrder`, một kiểu `Sort.Order` chuyên biệt để đưa geo distance sort vào `Sort`, `Pageable` hoặc repository method. Khi cần các tùy chọn Query DSL nâng cao, Elasticsearch Java API Client hoặc REST API vẫn cho phép điều khiển trực tiếp request.

Bài học này giải thích cách mapping `geo_point`, cách tính và sắp xếp khoảng cách, các tùy chọn `unit`, `distance_type`, `mode`, `order`, cách xử lý document thiếu tọa độ, cách dùng `GeoDistanceOrder` trong Spring Data và cách phân trang ổn định với kết quả có cùng khoảng cách.

## 1. Geo distance sort dùng để làm gì?

Giả sử index `places` lưu địa điểm cùng tọa độ. Một ứng dụng muốn tìm các địa điểm phù hợp với điều kiện nghiệp vụ rồi hiển thị địa điểm gần một điểm trung tâm nhất trước.

Ví dụ:

- Người dùng chọn vị trí hiện tại trên bản đồ.
- Ứng dụng tìm những cửa hàng đang hoạt động.
- Kết quả được sắp xếp theo khoảng cách từ vị trí người dùng tới từng cửa hàng.
- Cửa hàng gần nhất xuất hiện đầu danh sách.

Geo distance sort **sắp xếp các document đã khớp query** theo khoảng cách. Nó không tự giới hạn kết quả trong bán kính. Nếu chỉ muốn lấy địa điểm trong vòng 5 km, cần kết hợp thêm `geo_distance` query.

```text
Vị trí tham chiếu
       |
       v
Tính khoảng cách tới location của từng document
       |
       v
Sắp xếp theo khoảng cách tăng dần
       |
       v
Địa điểm gần nhất đứng trước
```

## 2. Mapping `geo_point` cho vị trí

Geo distance sort thường làm việc với field Elasticsearch kiểu `geo_point`. Kiểu này lưu một điểm trên bề mặt Trái Đất bằng latitude (vĩ độ) và longitude (kinh độ), theo hệ tọa độ WGS-84.

Ví dụ mapping:

```http
PUT places
{
  "mappings": {
    "properties": {
      "name": {
        "type": "keyword"
      },
      "active": {
        "type": "boolean"
      },
      "location": {
        "type": "geo_point"
      }
    }
  }
}
```

Document có thể được ghi với tọa độ dạng object:

```http
PUT places/_doc/place-1
{
  "name": "Central Store",
  "active": true,
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
```

Vĩ độ nằm trong khoảng -90 đến 90; kinh độ nằm trong khoảng -180 đến 180.

### 2.1. Các định dạng tọa độ được Elasticsearch chấp nhận

Một `geo_point` có thể được gửi theo nhiều dạng:

| Dạng | Ví dụ | Thứ tự |
|---|---|---|
| Object | `{"lat": 10.7769, "lon": 106.7009}` | Ghi rõ `lat`, `lon` |
| Array | `[106.7009, 10.7769]` | `[lon, lat]` |
| String | `"10.7769,106.7009"` | `lat,lon` |
| GeoJSON Point | `{"type":"Point","coordinates":[106.7009,10.7769]}` | `[lon, lat]` |
| WKT | `"POINT (106.7009 10.7769)"` | `POINT(lon lat)` |
| Geohash | `"w3gvk"` | Mã hóa vị trí |

Điểm dễ nhầm nhất là thứ tự tọa độ: constructor `GeoPoint` của Spring Data nhận latitude trước longitude, trong khi array, GeoJSON và WKT dùng longitude trước latitude.

### 2.2. Entity Spring Data Elasticsearch

Spring Data Elasticsearch có class `GeoPoint` trong package `org.springframework.data.elasticsearch.core.geo` và annotation `@GeoPointField`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.GeoPointField;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Document(indexName = "places")
public class Place {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Boolean)
    private boolean active;

    @GeoPointField
    private GeoPoint location;

    public Place() {
    }

    public Place(String id, String name, boolean active,
                 double latitude, double longitude) {
        this.id = id;
        this.name = name;
        this.active = active;
        this.location = new GeoPoint(latitude, longitude);
    }

    // Getters and setters
}
```

Tạo một `GeoPoint`:

```java
GeoPoint origin = new GeoPoint(10.7769, 106.7009);
```

Tham số thứ nhất là latitude, tham số thứ hai là longitude. Spring Data chuyển `GeoPoint` thành cấu trúc mà Elasticsearch hiểu cho field `geo_point`.

Sau khi tạo index, có thể kiểm tra mapping thực tế:

```http
GET places/_mapping
```

Nếu field `location` không được mapping thành `geo_point`, geo distance sort sẽ không hoạt động như mong muốn. Thay đổi annotation không tự sửa mapping của index đã tồn tại; khi cần đổi kiểu field, phải có kế hoạch migration index.

## 3. Geo distance sort trong Elasticsearch Query DSL

Geo distance sort được khai báo trong mảng `sort` bằng khóa `_geo_distance`.

Ví dụ sắp xếp cửa hàng gần tọa độ tham chiếu nhất trước:

```http
GET places/_search
{
  "query": {
    "term": {
      "active": true
    }
  },
  "sort": [
    {
      "_geo_distance": {
        "location": {
          "lat": 10.7769,
          "lon": 106.7009
        },
        "order": "asc",
        "unit": "km",
        "distance_type": "arc"
      }
    }
  ]
}
```

Query lọc các cửa hàng đang hoạt động. Elasticsearch tính khoảng cách từ điểm tham chiếu tới `location` của mỗi document rồi sắp xếp tăng dần theo kilomet.

- `order: "asc"`: gần nhất trước.
- `order: "desc"`: xa nhất trước.
- `unit: "km"`: đơn vị của giá trị khoảng cách được tính và trả về.
- `distance_type: "arc"`: dùng phép tính khoảng cách theo cung trên bề mặt Trái Đất.

Nếu không khai báo `order`, sort thông thường mặc định tăng dần; nếu không khai báo `unit`, đơn vị mặc định là mét. `distance_type` mặc định là `arc`.

### 3.1. Cách biểu diễn điểm tham chiếu

`_geo_distance` chấp nhận các dạng tọa độ giống field `geo_point`. Ví dụ dạng array:

```json
{
  "sort": [
    {
      "_geo_distance": {
        "location": [106.7009, 10.7769],
        "order": "asc",
        "unit": "km"
      }
    }
  ]
}
```

Array luôn dùng `[longitude, latitude]` theo quy ước GeoJSON. Nếu lấy giá trị trực tiếp từ `GeoPoint(latitude, longitude)`, không được đảo thứ tự nhầm khi chuyển sang array.

Có thể dùng WKT:

```json
{
  "sort": [
    {
      "_geo_distance": {
        "location": "POINT (106.7009 10.7769)",
        "order": "asc",
        "unit": "km"
      }
    }
  ]
}
```

Trong WKT, tọa độ cũng theo `longitude latitude`.

## 4. Phân biệt `geo_distance` query và `_geo_distance` sort

Hai cấu trúc có tên gần giống nhau nhưng chức năng khác nhau:

| Cấu trúc | Vị trí trong request | Mục đích |
|---|---|---|
| `geo_distance` | Trong `query` | Chỉ chọn document nằm trong khoảng cách tối đa |
| `_geo_distance` | Trong `sort` | Sắp xếp document đã khớp theo khoảng cách tới điểm tham chiếu |

Ví dụ chỉ lấy cửa hàng trong vòng 10 km:

```http
GET places/_search
{
  "query": {
    "geo_distance": {
      "distance": "10km",
      "location": {
        "lat": 10.7769,
        "lon": 106.7009
      }
    }
  },
  "sort": [
    {
      "_geo_distance": {
        "location": {
          "lat": 10.7769,
          "lon": 106.7009
        },
        "order": "asc",
        "unit": "km"
      }
    }
  ]
}
```

Ở đây `geo_distance` giới hạn tập kết quả trong 10 km; `_geo_distance` sắp xếp các kết quả đó theo khoảng cách tăng dần. Nếu chỉ khai báo sort mà không có query giới hạn khoảng cách, Elasticsearch vẫn có thể trả về các document ở rất xa miễn là chúng khớp query chính.

## 5. Chọn `distance_type`: `arc` và `plane`

`distance_type` xác định cách tính khoảng cách giữa hai tọa độ:

| Giá trị | Đặc điểm | Khi dùng |
|---|---|---|
| `arc` | Tính khoảng cách theo cung trên bề mặt Trái Đất; mặc định và chính xác hơn | Tìm địa điểm thực tế, khoảng cách trung bình/lớn, vùng gần cực |
| `plane` | Dùng phép tính phẳng gần đúng; có thể nhanh hơn nhưng kém chính xác khi khoảng cách dài hoặc gần cực | Trường hợp phạm vi nhỏ, đã đo và chấp nhận sai số |

Ví dụ:

```json
{
  "_geo_distance": {
    "location": [106.7009, 10.7769],
    "order": "asc",
    "unit": "km",
    "distance_type": "arc"
  }
}
```

Đối với tìm kiếm cửa hàng, dịch vụ hoặc phương tiện theo vị trí địa lý, thường nên giữ mặc định `arc`. Chỉ chuyển sang `plane` sau khi đo hiệu năng và xác nhận sai số phù hợp với phạm vi dữ liệu.

## 6. Đơn vị khoảng cách (`unit`)

Geo distance sort hỗ trợ các đơn vị khoảng cách thông dụng:

| Đơn vị | Giá trị |
|---|---|
| Millimeter | `mm` |
| Centimeter | `cm` |
| Meter | `m` hoặc `meters` |
| Kilometer | `km` hoặc `kilometers` |
| Inch | `in` hoặc `inch` |
| Feet | `ft` hoặc `feet` |
| Yard | `yd` hoặc `yards` |
| Mile | `mi` hoặc `miles` |
| Nautical mile | `nmi`, `NM` hoặc `nauticalmiles` |

Nếu không đặt `unit`, Elasticsearch dùng mét. Nên chọn một đơn vị phù hợp với nghiệp vụ và giữ nhất quán giữa API sort, giao diện hiển thị và kiểm thử.

Ví dụ dùng mile:

```json
{
  "_geo_distance": {
    "location": {
      "lat": 40.7128,
      "lon": -74.0060
    },
    "order": "asc",
    "unit": "mi"
  }
}
```

Đơn vị ở sort quyết định đơn vị của sort value trả về. Nếu cần hiển thị khoảng cách cho người dùng, có thể đọc sort value và định dạng theo hợp đồng API thay vì tự tính lại khoảng cách ở ứng dụng.

## 7. Field có nhiều geo point và `mode`

Một document có thể chứa nhiều tọa độ trong cùng một field `geo_point`, ví dụ một chuỗi cửa hàng có nhiều chi nhánh hoặc một đối tượng có nhiều vị trí liên quan.

Document:

```json
{
  "name": "Retail Network",
  "locations": [
    { "lat": 10.7769, "lon": 106.7009 },
    { "lat": 10.8000, "lon": 106.6500 },
    { "lat": 10.7500, "lon": 106.7200 }
  ]
}
```

Khi sort, Elasticsearch cần chọn một khoảng cách đại diện cho document. Tham số `mode` điều khiển cách chọn:

| Mode | Ý nghĩa |
|---|---|
| `min` | Khoảng cách nhỏ nhất |
| `max` | Khoảng cách lớn nhất |
| `avg` | Trung bình các khoảng cách |
| `median` | Trung vị các khoảng cách |

Mặc định:

- Sort tăng dần (`asc`) chọn khoảng cách nhỏ nhất (`min`), tức document được đánh giá theo điểm gần nhất của nó.
- Sort giảm dần (`desc`) chọn khoảng cách lớn nhất (`max`).

Ví dụ chọn điểm gần nhất của mỗi document:

```json
{
  "sort": [
    {
      "_geo_distance": {
        "locations": [106.7009, 10.7769],
        "order": "asc",
        "unit": "km",
        "mode": "min"
      }
    }
  ]
}
```

Nếu muốn xếp hạng một chuỗi cửa hàng theo khoảng cách trung bình từ người dùng tới các chi nhánh, có thể dùng `mode: "avg"`. Nếu muốn tìm document mà mọi điểm đều xa, có thể cân nhắc `mode: "max"` kết hợp sort tăng dần hoặc giảm dần theo mục tiêu.

### 7.1. Nhiều điểm tham chiếu

Elasticsearch cũng cho phép truyền nhiều điểm tham chiếu trong một mảng:

```json
{
  "sort": [
    {
      "_geo_distance": {
        "locations": [
          [106.7009, 10.7769],
          [106.6500, 10.8000]
        ],
        "order": "asc",
        "unit": "km",
        "mode": "min"
      }
    }
  ]
}
```

Elasticsearch tính các khoảng cách giữa các điểm trong document và các điểm tham chiếu rồi áp dụng `mode` để lấy giá trị sort cuối cùng. Đây là cách hữu ích khi người dùng có nhiều điểm xuất phát hoặc một truy vấn cần so sánh với nhiều trung tâm.

`GeoDistanceOrder` của Spring Data có constructor nhận một `GeoPoint` làm điểm tham chiếu. Nếu cần truyền nhiều điểm tham chiếu hoặc cấu trúc geo distance sort phức tạp hơn, dùng `NativeQuery`/Elasticsearch Java API Client hoặc REST API để khai báo trực tiếp.

## 8. Xử lý document thiếu tọa độ và field chưa được mapping

Không phải document nào cũng có `location`. Cần phân biệt hai tình huống:

1. Field đã được mapping là `geo_point`, nhưng một document không có giá trị tọa độ.
2. Một index trong tập index đang tìm kiếm không có mapping cho field được sort.

### 8.1. Document không có giá trị geo point

Geo distance sort không hỗ trợ cấu hình `missing` giống field sort thông thường. Document không có tọa độ được xem như có khoảng cách `Infinity`.

Hệ quả:

- Với `order: "asc"`, document không có tọa độ thường đứng cuối vì khoảng cách vô hạn lớn hơn các khoảng cách thực.
- Với `order: "desc"`, document không có tọa độ có thể đứng đầu vì khoảng cách vô hạn lớn nhất.

Nếu nghiệp vụ muốn bỏ hẳn document thiếu vị trí, thêm điều kiện `exists` trong query:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } },
        { "exists": { "field": "location" } }
      ]
    }
  }
}
```

### 8.2. Field không được mapping ở một index

Khi search nhiều index, một index có thể không có mapping cho `location`. Mặc định, Elasticsearch có thể từ chối request sort nếu field không được mapping. Dùng `ignore_unmapped: true` để coi field chưa được mapping như giá trị thiếu:

```json
{
  "_geo_distance": {
    "location": [106.7009, 10.7769],
    "order": "asc",
    "unit": "km",
    "ignore_unmapped": true
  }
}
```

`ignore_unmapped` có mặc định là `false`. Bật nó khi query trên nhiều index có schema khác nhau và chấp nhận document từ index thiếu field được xem như không có vị trí.

Đừng nhầm `ignore_unmapped` với việc cho phép dữ liệu tọa độ sai định dạng. Nó không thay thế bước xác thực latitude/longitude hoặc mapping `geo_point`.

## 9. Sort nhiều tiêu chí và kết hợp `_score`

Elasticsearch xử lý các phần tử trong mảng `sort` theo thứ tự. Tiêu chí sau chỉ được dùng khi các document hòa nhau ở tiêu chí trước.

Ví dụ:

```json
{
  "track_scores": true,
  "sort": [
    {
      "_geo_distance": {
        "location": [106.7009, 10.7769],
        "order": "asc",
        "unit": "km"
      }
    },
    { "_score": "desc" },
    { "name.keyword": "asc" }
  ],
  "query": {
    "match": {
      "name": "coffee shop"
    }
  }
}
```

Thứ tự ưu tiên:

1. Địa điểm gần hơn đứng trước.
2. Nếu khoảng cách bằng nhau, document có `_score` cao hơn đứng trước.
3. Nếu cả khoảng cách và score bằng nhau, tên tăng dần được dùng làm tiêu chí tiếp theo.

Khi sort theo field, Elasticsearch không tính score theo mặc định. `track_scores: true` yêu cầu vẫn tính và giữ `_score` nếu cần dùng nó như tiêu chí phụ hoặc hiển thị. Nếu sort chỉ theo khoảng cách và không dùng score, không cần bật `track_scores`.

Các field dùng để sort thông thường nên có `doc_values`; tránh sort trực tiếp trên `text` field. Với tên cần sort, dùng multi-field `keyword` như `name.keyword`.

## 10. Đọc sort value trong search response

Mỗi hit có thể chứa mảng `sort` tương ứng với các tiêu chí sort trong request:

```json
{
  "hits": {
    "hits": [
      {
        "_id": "place-1",
        "_source": {
          "name": "Central Store"
        },
        "sort": [0.42]
      },
      {
        "_id": "place-2",
        "_source": {
          "name": "West Store"
        },
        "sort": [1.85]
      }
    ]
  }
}
```

Các giá trị `0.42` và `1.85` minh họa khoảng cách theo đơn vị `km` trong request. Nếu có nhiều sort criteria, mảng `sort` chứa một giá trị cho mỗi tiêu chí theo thứ tự khai báo.

Trong Spring Data Elasticsearch, khi dùng `SearchHits<T>`, mỗi `SearchHit<T>` cung cấp metadata của hit. Tuy nhiên, không nên giả định khoảng cách geo được đưa vào entity; nó là sort value của search hit. Hãy đọc sort values từ metadata của `SearchHit` theo API của phiên bản Spring Data đang dùng nếu ứng dụng cần hiển thị khoảng cách.

## 11. Dùng `GeoDistanceOrder` trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp `org.springframework.data.elasticsearch.core.query.GeoDistanceOrder`, một lớp kế thừa `Order` và được thiết kế cho `_geo_distance` sort. API này có từ Spring Data Elasticsearch 4.0.

Constructor nhận:

- Tên property chứa `GeoPoint`.
- Điểm tham chiếu kiểu `GeoPoint`.

Ví dụ cơ bản theo tài liệu Spring Data:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.query.GeoDistanceOrder;

Sort distanceSort = Sort.by(
        new GeoDistanceOrder(
                "location",
                new GeoPoint(10.7769, 106.7009)));
```

Ví dụ đầy đủ hơn, chỉ rõ hướng và đơn vị:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.query.GeoDistanceOrder;
import org.springframework.data.elasticsearch.core.query.Order;

GeoDistanceOrder distanceOrder = new GeoDistanceOrder(
        "location",
        new GeoPoint(10.7769, 106.7009))
        .with(Sort.Direction.ASC)
        .withUnit("km")
        .with(GeoDistanceOrder.DistanceType.arc)
        .with(Order.Mode.min)
        .withIgnoreUnmapped(true);

Sort distanceSort = Sort.by(distanceOrder);
```

Các method quan trọng:

| Method | Mục đích |
|---|---|
| `with(Sort.Direction.ASC)` | Gần nhất trước |
| `with(Sort.Direction.DESC)` | Xa nhất trước |
| `withUnit("km")` | Chọn đơn vị khoảng cách |
| `with(GeoDistanceOrder.DistanceType.arc)` | Tính khoảng cách theo cung |
| `with(GeoDistanceOrder.DistanceType.plane)` | Dùng phép tính phẳng gần đúng |
| `with(Order.Mode.min)` | Chọn khoảng cách nhỏ nhất khi có nhiều điểm |
| `with(Order.Mode.max)` | Chọn khoảng cách lớn nhất |
| `with(Order.Mode.avg)` | Chọn khoảng cách trung bình |
| `with(Order.Mode.median)` | Chọn khoảng cách trung vị |
| `withIgnoreUnmapped(true)` | Bỏ qua index không có mapping cho field |

Tên enum trong API Java của Spring Data được viết thường (`arc`, `plane`, `min`, `max`, `avg`, `median`), tương ứng với giá trị trong Query DSL.

### 11.1. Dùng `GeoDistanceOrder` trong repository method

Repository có thể nhận `Pageable` hoặc `Sort` như tham số động:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface PlaceRepository
        extends ElasticsearchRepository<Place, String> {

    Page<Place> findByActiveTrue(Pageable pageable);
}
```

Service tạo `Pageable` có geo distance sort:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.query.GeoDistanceOrder;

@Service
public class NearbyPlaceService {

    private final PlaceRepository repository;

    public NearbyPlaceService(PlaceRepository repository) {
        this.repository = repository;
    }

    public Page<Place> findNearestPlaces() {
        GeoDistanceOrder order = new GeoDistanceOrder(
                "location",
                new GeoPoint(10.7769, 106.7009))
                .with(Sort.Direction.ASC)
                .withUnit("km");

        Pageable pageable = PageRequest.of(
                0,
                20,
                Sort.by(order));

        return repository.findByActiveTrue(pageable);
    }
}
```

`PageRequest` kết hợp vị trí trang, kích thước trang và `Sort`. Spring Data chuyển `GeoDistanceOrder` thành geo distance sort trong search request.

### 11.2. Chỉ cần `Sort`, không cần `Page`

Nếu không cần metadata tổng số trang, repository method có thể nhận `Sort` và trả `List`:

```java
List<Place> findByActiveTrue(Sort sort);
```

Gọi:

```java
List<Place> places = repository.findByActiveTrue(
        Sort.by(new GeoDistanceOrder(
                "location",
                new GeoPoint(10.7769, 106.7009))
                .with(Sort.Direction.ASC)
                .withUnit("km")));
```

Chọn `List` khi chỉ cần một tập kết quả có giới hạn hợp lý. Nếu dùng `Page`, Spring Data cần cung cấp thông tin tổng số phần tử/trang và có thể phải thực hiện thêm count query. Nếu giao diện chỉ cần biết còn trang tiếp theo hay không, cân nhắc `Slice`.

### 11.3. Dùng `ElasticsearchOperations`

Với query phức tạp hơn repository method, có thể đưa `Sort` vào query object rồi thực thi qua `ElasticsearchOperations`:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.GeoDistanceOrder;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

GeoDistanceOrder order = new GeoDistanceOrder(
        "location",
        new GeoPoint(10.7769, 106.7009))
        .with(Sort.Direction.ASC)
        .withUnit("km");

CriteriaQuery query = new CriteriaQuery(
        Criteria.where("active").is(true));
query.addSort(Sort.by(order));

SearchHits<Place> hits = operations.search(
        query,
        Place.class,
        IndexCoordinates.of("places"));
```

`CriteriaQuery` biểu diễn điều kiện tìm kiếm; `addSort` gắn thứ tự geo distance. Nếu cần Query DSL options không được abstraction của Spring Data expose trong release train đang dùng, có thể chuyển sang `NativeQuery` hoặc Elasticsearch Java API Client.

## 12. Nested geo point và cấu trúc nâng cao

Nếu field địa lý nằm trong một object có mapping `nested`, Elasticsearch cần biết nested path khi sort. Nếu không có nested context, request có thể báo lỗi vì không xác định được nested object dùng để lấy tọa độ.

Ví dụ mapping:

```http
PUT vendors
{
  "mappings": {
    "properties": {
      "name": {
        "type": "keyword"
      },
      "branches": {
        "type": "nested",
        "properties": {
          "city": {
            "type": "keyword"
          },
          "location": {
            "type": "geo_point"
          }
        }
      }
    }
  }
}
```

Sort theo khoảng cách của nested field:

```http
GET vendors/_search
{
  "sort": [
    {
      "_geo_distance": {
        "branches.location": [106.7009, 10.7769],
        "order": "asc",
        "unit": "km",
        "mode": "min",
        "nested": {
          "path": "branches",
          "filter": {
            "term": {
              "branches.city": "Ho Chi Minh City"
            }
          }
        }
      }
    }
  ],
  "query": {
    "match_all": {}
  }
}
```

`nested.path` xác định nested object cần sort. `nested.filter` giới hạn các nested object được dùng để lấy giá trị khoảng cách; trong ví dụ, chỉ các chi nhánh ở Ho Chi Minh City được xét. Nếu nested field lồng nhiều cấp, mỗi cấp cần nested context tương ứng.

`GeoDistanceOrder` kế thừa `Order`, có hỗ trợ nested sort thông qua các API của lớp cha ở các phiên bản tương ứng. Với nested filter phức tạp hoặc nhiều cấp, hãy xác nhận khả năng biểu diễn của phiên bản Spring Data đang dùng; dùng `NativeQuery`/Java API Client nếu cần kiểm soát JSON chính xác.

## 13. Phân trang kết quả theo khoảng cách

### 13.1. Offset pagination với `Pageable`

Spring Data repository có thể dùng `Pageable` cùng `GeoDistanceOrder` như ví dụ ở trên. Cách này phù hợp với danh sách giao diện thông thường, nơi người dùng xem một số trang đầu.

Elasticsearch triển khai offset pagination bằng `from` và `size`. Mỗi shard cần xử lý các kết quả trước offset để tạo trang được yêu cầu. Vì vậy, phân trang quá sâu sẽ tốn bộ nhớ và CPU.

Theo mặc định, `index.max_result_window` thường giới hạn tổng `from + size` ở 10.000. Không nên tăng giới hạn chỉ để cho phép cuộn qua hàng trăm nghìn kết quả bằng `PageRequest`; với phân trang sâu, dùng `search_after` và Point in Time (PIT).

### 13.2. Thêm tie-breaker khi nhiều document cùng khoảng cách

Nhiều địa điểm có thể có cùng sort value, ví dụ cùng tọa độ hoặc khoảng cách được làm tròn giống nhau. Nếu sort chỉ theo `_geo_distance`, thứ tự giữa các document bằng khoảng cách có thể không ổn định giữa các request.

Thêm một field keyword duy nhất làm tiêu chí phụ:

```json
{
  "sort": [
    {
      "_geo_distance": {
        "location": [106.7009, 10.7769],
        "order": "asc",
        "unit": "km"
      }
    },
    {
      "sortId": "asc"
    }
  ]
}
```

`sortId` cần có giá trị duy nhất cho mỗi document và có `doc_values` để sort. Không nên dựa vào `_id` làm sort field thông thường; nếu cần sắp xếp theo ID, hãy copy ID sang một field `keyword` có doc values khi index document.

### 13.3. `search_after` cho phân trang sâu

`search_after` dùng sort values của hit cuối cùng ở trang trước để lấy trang tiếp theo. Ví dụ request đầu:

```http
GET places/_search
{
  "size": 20,
  "query": {
    "term": {
      "active": true
    }
  },
  "sort": [
    {
      "_geo_distance": {
        "location": [106.7009, 10.7769],
        "order": "asc",
        "unit": "km"
      }
    },
    {
      "sortId": "asc"
    }
  ]
}
```

Giả sử hit cuối cùng của trang có sort values:

```json
"sort": [1.85, "place-200"]
```

Request tiếp theo dùng chính mảng đó:

```http
GET places/_search
{
  "size": 20,
  "query": {
    "term": {
      "active": true
    }
  },
  "sort": [
    {
      "_geo_distance": {
        "location": [106.7009, 10.7769],
        "order": "asc",
        "unit": "km"
      }
    },
    {
      "sortId": "asc"
    }
  ],
  "search_after": [1.85, "place-200"]
}
```

Các request phải giữ nguyên query và sort. `search_after` nhận đúng các giá trị trong `sort` của hit cuối cùng trang trước, theo cùng thứ tự. Không tự tính lại khoảng cách hoặc tự tạo giá trị sort.

### 13.4. Dùng Point in Time để giữ snapshot ổn định

Nếu index được refresh trong lúc người dùng chuyển trang, các document mới hoặc thay đổi tọa độ có thể làm thứ tự thay đổi. Điều này có thể khiến một document bị lặp hoặc bị bỏ qua khi dùng `search_after` trên dữ liệu đang thay đổi.

PIT giữ một view ổn định của index trong thời gian phân trang:

```http
POST places/_pit?keep_alive=1m
```

Dùng PIT ID trong các Search API request tiếp theo. Khi có PIT, Elasticsearch tự thêm `_shard_doc` làm tie-breaker cuối cùng; có thể giữ nguyên hoặc chỉ định rõ theo yêu cầu. Request search với PIT không ghi tên index trên path; index và routing đã gắn với PIT.

Khi hoàn tất, đóng PIT:

```http
DELETE _pit
{
  "id": "PIT_ID"
}
```

PIT và `search_after` là lựa chọn phù hợp cho phân trang sâu hoặc đọc ổn định qua nhiều request. Scroll chủ yếu dành cho xử lý tập dữ liệu lớn theo batch, không phải lựa chọn ưu tiên cho phân trang tương tác mới.

## 14. Giới hạn của `GeoDistanceOrder` và khi cần NativeQuery

`GeoDistanceOrder` giúp đưa một geo distance sort phổ biến vào abstraction `Sort` của Spring Data. API hiện hành cung cấp:

- Một property địa lý và một `GeoPoint` tham chiếu qua constructor.
- Hướng sắp xếp (`ASC`/`DESC`).
- Đơn vị khoảng cách.
- `arc` hoặc `plane`.
- Mode `min`, `max`, `avg`, `median`.
- `ignoreUnmapped`.
- Nested options thông qua lớp `Order` cha ở các phiên bản hỗ trợ.

Khi cần các cấu trúc nâng cao như nhiều điểm tham chiếu, nested filter phức tạp, các tùy chọn sort mới của Elasticsearch hoặc phối hợp với nhiều search options khác, `NativeQuery` và Elasticsearch Java API Client có thể diễn đạt đầy đủ hơn.

Ví dụ khung sử dụng `NativeQuery`:

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

// Build a native search request with the Elasticsearch Java API Client.
// Add the query and geo-distance sort to NativeQuery.builder().
// Execute with operations.search(nativeQuery, Place.class).
```

Builder cụ thể của Java API Client phụ thuộc phiên bản Elasticsearch client được Spring Data release train quản lý. Khi triển khai, dùng request builder của đúng dependency đang chạy thay vì thêm một major version client không tương thích.

## 15. Hiệu năng và lưu ý vận hành

Geo distance sort cần tính khoảng cách cho các document ứng viên và giữ sort values để xếp hạng. Một số lưu ý:

- Dùng query filter có tính chọn lọc để giảm số document cần sắp xếp.
- Nếu chỉ cần tìm trong bán kính, kết hợp `geo_distance` query để giới hạn candidate.
- Chọn `arc` theo mặc định; chỉ dùng `plane` khi phạm vi nhỏ và đã chấp nhận sai số.
- Tránh trả về quá nhiều document cùng lúc; dùng `size` hợp lý.
- Dùng `search_after` + PIT cho phân trang sâu, không tăng `from` quá lớn.
- Kiểm tra field được mapping đúng là `geo_point` và dữ liệu tọa độ hợp lệ.
- Với multi-valued geo points, chọn `mode` theo ý nghĩa nghiệp vụ thay vì phụ thuộc ngầm vào mặc định.
- Khi search nhiều index, kiểm tra mapping đồng nhất hoặc đặt `ignore_unmapped` có chủ đích.
- Theo dõi latency và số shard được truy vấn; geo sort trên nhiều index/shard có thể tốn chi phí đáng kể.

Geo distance sort không thay thế kiểm tra chất lượng dữ liệu địa lý. Tọa độ bị đảo latitude/longitude có thể vẫn hợp lệ về mặt số học nhưng trỏ tới một nơi hoàn toàn khác, dẫn tới kết quả xếp hạng sai mà không phát sinh lỗi mapping.

## 16. Các lỗi thường gặp

### Đảo latitude và longitude

`new GeoPoint(latitude, longitude)` nhận vĩ độ trước kinh độ sau. Array, GeoJSON và WKT dùng longitude trước latitude. Kiểm tra thứ tự khi chuyển đổi giữa các dạng.

### Dùng `geo_distance` query nhưng quên `_geo_distance` sort

Query chỉ giới hạn kết quả trong bán kính; nó không tự đảm bảo địa điểm gần nhất đứng đầu. Thêm `_geo_distance` vào `sort` nếu cần xếp hạng theo khoảng cách.

### Chỉ dùng `_geo_distance` sort nhưng nghĩ kết quả bị giới hạn bán kính

Sort không loại document ở xa. Nếu muốn giới hạn bán kính, thêm `geo_distance` query.

### Mapping field không phải `geo_point`

Field có thể bị dynamic mapping thành object hoặc được tạo sai kiểu. Kiểm tra `GET index/_mapping` và tạo mapping đúng trước khi index dữ liệu.

### Chọn `plane` cho khoảng cách dài

`plane` là phép tính gần đúng và có thể sai đáng kể ở khoảng cách dài hoặc gần cực. Dùng `arc` nếu độ chính xác địa lý quan trọng.

### Không chọn `mode` cho document có nhiều điểm

Mặc định sort tăng dần lấy điểm gần nhất, sort giảm dần lấy điểm xa nhất. Nếu nghiệp vụ cần khoảng cách trung bình hoặc trung vị, đặt `mode` rõ ràng.

### Document thiếu vị trí xuất hiện ngoài dự kiến

Document không có tọa độ được xem như khoảng cách vô hạn. Dùng `exists` query để loại chúng nếu cần.

### Search nhiều index bị lỗi unmapped field

Nếu một index không có mapping `location`, request có thể lỗi. Thêm mapping đồng nhất hoặc dùng `ignore_unmapped: true` khi chấp nhận coi index đó như không có vị trí.

### Phân trang bị lặp hoặc thiếu document

Nếu nhiều hit có cùng distance sort value, thêm tie-breaker duy nhất. Khi dữ liệu có thể refresh giữa các trang, dùng PIT với `search_after` để giữ snapshot.

### Dùng `PageRequest` cho kết quả quá sâu

Offset pagination tốn tài nguyên khi `from` lớn và mặc định bị giới hạn bởi `index.max_result_window`. Chuyển sang `search_after` + PIT cho tập kết quả lớn.

### Mong đợi sort value tự xuất hiện trong entity

Khoảng cách là metadata của search hit, không phải field trong `_source`. Đọc sort values từ SearchHit/SearchResponse nếu cần hiển thị khoảng cách.

## 17. Quy trình triển khai geo distance sort

Khi thêm chức năng tìm địa điểm gần nhất, có thể thực hiện theo trình tự:

1. Xác định điểm tham chiếu lấy từ đâu và dùng hệ tọa độ nào.
2. Mapping field vị trí thành `geo_point`.
3. Kiểm tra dữ liệu đầu vào, đặc biệt thứ tự latitude/longitude.
4. Xây query lọc nghiệp vụ, ví dụ active hoặc category.
5. Thêm `geo_distance` query nếu cần giới hạn bán kính.
6. Thêm `_geo_distance` sort với `order: asc` để gần nhất trước.
7. Chọn `unit`, `distance_type` và `mode` theo yêu cầu.
8. Xác định cách xử lý document thiếu tọa độ và index chưa có mapping.
9. Dùng `GeoDistanceOrder` nếu API Spring Data đáp ứng; chuyển sang `NativeQuery`/client khi cần tùy chọn nâng cao.
10. Thêm tie-breaker và chọn `Pageable` hoặc `search_after` + PIT theo độ sâu phân trang.
11. Kiểm thử với điểm ở gần, xa, trùng tọa độ, nhiều tọa độ, thiếu tọa độ và tọa độ biên.
12. Đo hiệu năng với dữ liệu gần kích thước production và theo dõi số shard được truy vấn.

## 18. Tổng kết

Elasticsearch dùng `_geo_distance` trong phần `sort` để xếp hạng document theo khoảng cách tới một điểm tham chiếu. `order: asc` đưa địa điểm gần nhất lên đầu; `desc` đưa địa điểm xa nhất lên đầu. `unit` chọn đơn vị, `distance_type` chọn `arc` hoặc `plane`, `mode` quyết định cách tổng hợp khoảng cách khi document có nhiều geo point và `ignore_unmapped` xử lý index không có mapping tương ứng. Document thiếu tọa độ được xem như có khoảng cách vô hạn; muốn loại chúng cần thêm `exists` filter.

Spring Data Elasticsearch cung cấp `GeoDistanceOrder` để kết hợp geo distance sort với `Sort`, `Pageable` và repository method. Constructor nhận property cùng `GeoPoint(latitude, longitude)`; các method `with(...)`, `withUnit(...)` và `withIgnoreUnmapped(...)` cấu hình hướng, đơn vị, kiểu tính, mode và mapping không đồng nhất. Khi cần nhiều điểm tham chiếu hoặc Query DSL nâng cao, dùng `NativeQuery`/Elasticsearch Java API Client.

Với phân trang, `Pageable` phù hợp cho những trang đầu. Khi kết quả sâu hoặc dữ liệu thay đổi giữa các request, dùng `search_after` với sort values của hit cuối và PIT để giữ snapshot ổn định. Thêm tie-breaker duy nhất để tránh lặp hoặc bỏ sót hit có cùng khoảng cách. Mapping chính xác, thứ tự tọa độ đúng và lựa chọn mode phù hợp là các yếu tố quyết định kết quả geo distance sort có đúng với nghiệp vụ hay không.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – Miscellaneous operations and sort options](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/misc.html)
- [Spring Data Elasticsearch – `GeoDistanceOrder` API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/GeoDistanceOrder.html)
- [Spring Data Elasticsearch – `GeoPoint` API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/geo/GeoPoint.html)
- [Elasticsearch – Sort search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/sort-search-results)
- [Elasticsearch – Paginate search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results)
- [Elasticsearch – Geo point field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/geo-point)
- [Elasticsearch – Geo queries](https://www.elastic.co/docs/reference/query-languages/query-dsl/geo-queries)
