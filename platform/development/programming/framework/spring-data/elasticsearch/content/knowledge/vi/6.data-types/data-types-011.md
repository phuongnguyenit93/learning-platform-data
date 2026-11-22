# Range, `geo_point`, `geo_shape` và phạm vi hỗ trợ của Spring Data

Elasticsearch cung cấp các kiểu dữ liệu chuyên biệt để lưu khoảng giá trị và thông tin không gian. **Range fields** biểu diễn một khoảng có cận dưới và cận trên, chẳng hạn độ tuổi từ 18 đến 65 hoặc thời gian hiệu lực của hợp đồng. **`geo_point`** biểu diễn một vị trí địa lý bằng vĩ độ và kinh độ. **`geo_shape`** biểu diễn hình học phức tạp như đường đi, vùng phục vụ hoặc đa giác địa lý.

Spring Data Elasticsearch hỗ trợ ánh xạ các kiểu này vào entity Java, cung cấp một số kiểu dữ liệu và abstraction truy vấn để làm việc với chúng. Tuy nhiên, Spring Data không biến toàn bộ Query DSL của Elasticsearch thành các repository method hoặc `Criteria` method. Khi cần một tùy chọn chuyên sâu mà abstraction không biểu diễn được, ứng dụng có thể dùng `NativeQuery`/Elasticsearch Java API Client hoặc REST API.

Bài học này giải thích cách chọn kiểu dữ liệu, cách khai báo mapping, cách biểu diễn dữ liệu trong Java, cách truy vấn range và dữ liệu địa lý, cũng như ranh giới giữa tính năng của Elasticsearch và phần API mà Spring Data cung cấp.

## 1. Chọn đúng kiểu dữ liệu

Ba nhóm field có mục đích khác nhau:

| Kiểu field | Dữ liệu biểu diễn | Ví dụ nghiệp vụ |
|---|---|---|
| `integer_range`, `long_range`, `float_range`, `double_range`, `date_range`, `ip_range` | Một khoảng giá trị có cận dưới và cận trên | Khoảng tuổi hợp lệ, khoảng giá, thời gian hợp đồng, dải địa chỉ IP |
| `geo_point` | Một điểm địa lý (hoặc nhiều điểm trong cùng field) | Vị trí cửa hàng, địa chỉ giao hàng, vị trí thiết bị |
| `geo_shape` | Một hình học địa lý có thể gồm điểm, đường hoặc vùng | Ranh giới khu vực, tuyến giao hàng, vùng phủ dịch vụ |

Hãy chọn kiểu theo bản chất dữ liệu. Nếu cần tìm cửa hàng trong bán kính 5 km, `geo_point` thường phù hợp. Nếu cần tìm những vùng giao hàng giao nhau với một khu vực được chọn, dùng `geo_shape`. Nếu cần lưu khoảng thời gian hiệu lực của một chính sách như từ ngày A đến ngày B, `date_range` thể hiện dữ liệu trực tiếp hơn hai field ngày rời rạc.

## 2. Range field trong Elasticsearch

### 2.1. Các loại range được hỗ trợ

Elasticsearch có sáu kiểu range chính:

| Kiểu | Miền giá trị |
|---|---|
| `integer_range` | Số nguyên có dấu 32 bit |
| `long_range` | Số nguyên có dấu 64 bit |
| `float_range` | Số thực dấu phẩy động 32 bit |
| `double_range` | Số thực dấu phẩy động 64 bit |
| `date_range` | Khoảng ngày giờ |
| `ip_range` | Khoảng địa chỉ IPv4 hoặc IPv6 |

Một range được biểu diễn bằng các cận. Elasticsearch hỗ trợ:

- `gt`: cận dưới loại trừ giá trị tại cận.
- `gte`: cận dưới bao gồm giá trị tại cận.
- `lt`: cận trên loại trừ giá trị tại cận.
- `lte`: cận trên bao gồm giá trị tại cận.

Ví dụ khoảng tuổi từ 18 đến dưới 30:

```json
{
  "validAge": {
    "gte": 18,
    "lt": 30
  }
}
```

Giá trị 18 thuộc khoảng, còn 30 không thuộc khoảng. Nếu dùng `lte: 30`, cận trên sẽ được bao gồm.

Range field là dữ liệu khoảng được lưu trong một field. Nó khác với việc dùng một `range` query trên field scalar thông thường. Ví dụ:

- Field `price` kiểu `long` lưu một giá trị giá tiền; range query kiểm tra giá tiền có nằm trong khoảng tìm kiếm không.
- Field `priceBand` kiểu `long_range` lưu một khoảng giá cho mỗi document; range query có thể so sánh khoảng trong document với khoảng truy vấn theo quan hệ không gian của hai khoảng.

### 2.2. Khai báo mapping cho range field

Ví dụ tạo index có khoảng số lượng người tham dự và khoảng thời gian sự kiện:

```http
PUT events
{
  "mappings": {
    "properties": {
      "expectedAttendees": {
        "type": "integer_range"
      },
      "activePeriod": {
        "type": "date_range",
        "format": "strict_date_optional_time||epoch_millis"
      }
    }
  }
}
```

Khi ghi document:

```http
PUT events/_doc/event-100
{
  "expectedAttendees": {
    "gte": 10,
    "lt": 20
  },
  "activePeriod": {
    "gte": "2026-11-01T00:00:00Z",
    "lte": "2026-11-30T23:59:59Z"
  }
}
```

Một cận có thể bỏ trống để biểu diễn khoảng không bị giới hạn về phía đó. Ví dụ `{"gte": 18}` biểu diễn mọi giá trị từ 18 trở lên. Hãy kiểm tra định dạng đầu vào của `date_range` giống như khi làm việc với field `date`.

Riêng `ip_range` còn chấp nhận biểu diễn CIDR, ví dụ `192.168.0.0/16`, ngoài cấu trúc cận `gte`/`lte`:

```json
{
  "allowedNetwork": "192.168.0.0/16"
}
```

### 2.3. Truy vấn range field

Range query trên một range field hỗ trợ tham số `relation`:

| Relation | Ý nghĩa đối với range được lưu trong document |
|---|---|
| `INTERSECTS` | Khoảng trong document giao với khoảng truy vấn; đây là mặc định |
| `CONTAINS` | Khoảng trong document chứa toàn bộ khoảng truy vấn |
| `WITHIN` | Khoảng trong document nằm hoàn toàn bên trong khoảng truy vấn |

Ví dụ tìm các sự kiện có thời gian hiệu lực nằm trong tháng 11/2026:

```http
GET events/_search
{
  "query": {
    "range": {
      "activePeriod": {
        "gte": "2026-11-01T00:00:00Z",
        "lt": "2026-12-01T00:00:00Z",
        "relation": "within"
      }
    }
  }
}
```

Nếu dùng `intersects`, một document có khoảng hiệu lực chỉ cần giao với khoảng truy vấn là được chọn. Ví dụ một hợp đồng từ ngày 25/10 đến ngày 05/11 sẽ giao với khoảng tháng 11, dù nó không nằm hoàn toàn trong tháng đó.

Đừng nhầm `relation` của range field với `relation` của `geo_shape`. Cả hai dùng các từ như `intersects`, `contains`, `within`, nhưng chúng so sánh hai loại dữ liệu khác nhau.

### 2.4. Range field có thể dùng term query

Với một số trường hợp, có thể dùng `term` query để kiểm tra một giá trị có nằm trong range được lưu hay không:

```http
GET events/_search
{
  "query": {
    "term": {
      "expectedAttendees": {
        "value": 15
      }
    }
  }
}
```

Document có khoảng `gte: 10, lt: 20` sẽ khớp vì 15 nằm trong khoảng. Đây là cách truy vấn khác với việc dùng range query trên một field số nguyên scalar.

### 2.5. Giới hạn của range field

Range fields hỗ trợ truy vấn khoảng nhưng khả năng aggregation có giới hạn. Elasticsearch hỗ trợ các aggregation như `histogram` và `cardinality` cho range field; không nên giả định mọi aggregation dành cho numeric field đều hoạt động giống nhau.

Elasticsearch không hỗ trợ sort trực tiếp trên các field kiểu range. Nếu cần sắp xếp theo một đầu mút của khoảng, hãy lưu thêm field scalar tương ứng (ví dụ `minimumPrice` hoặc `maximumPrice`) và sort theo field đó.

Nếu nghiệp vụ cần thống kê phân bố giá trị đơn lẻ, lưu một field numeric scalar riêng có thể phù hợp hơn. Nếu cần lưu khoảng hiệu lực và so sánh khoảng với khoảng, range field mới là mô hình trực tiếp.

## 3. Ánh xạ range field trong Spring Data Elasticsearch

Spring Data Elasticsearch có các giá trị `FieldType` tương ứng với range mapping:

- `Integer_Range`
- `Long_Range`
- `Float_Range`
- `Double_Range`
- `Date_Range`
- `Ip_Range`

Khi khai báo field có một trong những kiểu này, thuộc tính Java cần được chuyển đổi thành cấu trúc range mà Elasticsearch nhận được.

### 3.1. Dùng `org.springframework.data.domain.Range<T>`

Trong các phiên bản Spring Data hiện hành, có thể dùng `Range<T>` từ Spring Data Commons:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.domain.Range;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "events")
public class EventDocument {

    @Id
    private String id;

    @Field(type = FieldType.Integer_Range)
    private Range<Integer> expectedAttendees;

    // Constructors, getters and setters
}
```

Tạo khoảng có cả hai cận bao gồm:

```java
Range<Integer> attendees = Range.closed(10, 20);
```

Các factory method khác gồm `Range.open(from, to)`, `Range.leftOpen(from, to)`, `Range.rightOpen(from, to)`, `Range.unbounded()` và các cách tạo khoảng có một cận không giới hạn. `Range.closed(10, 20)` bao gồm cả 10 và 20; `Range.rightOpen(10, 20)` bao gồm 10 nhưng không bao gồm 20.

Lưu ý về phiên bản: Spring Data Elasticsearch từng có lớp `org.springframework.data.elasticsearch.core.Range`. Lớp cũ này đã deprecated từ Spring Data Elasticsearch 5.0 và được khuyến nghị thay bằng `org.springframework.data.domain.Range`. Khi đọc code hoặc tài liệu cũ, hãy kiểm tra package import để tránh dùng nhầm lớp đã deprecated.

### 3.2. Dùng một class riêng biểu diễn cận

Nếu cần mô hình hóa dữ liệu range theo một domain class cụ thể, có thể khai báo một class có các thuộc tính được ánh xạ thành `gte`, `gt`, `lte` hoặc `lt`:

```java
import org.springframework.data.elasticsearch.annotations.Field;

public class ValidAge {

    @Field(name = "gte")
    private Integer minimum;

    @Field(name = "lt")
    private Integer maximumExclusive;

    public ValidAge() {
    }

    public ValidAge(Integer minimum, Integer maximumExclusive) {
        this.minimum = minimum;
        this.maximumExclusive = maximumExclusive;
    }

    // Getters and setters
}
```

Entity:

```java
@Document(indexName = "people")
public class PersonDocument {

    @Id
    private String id;

    @Field(type = FieldType.Integer_Range)
    private ValidAge validAge;

    // Getters and setters
}
```

Khi chuyển đổi, Spring Data ánh xạ thuộc tính `minimum` thành key `gte` và `maximumExclusive` thành key `lt`. Cách này hữu ích khi tên thuộc tính trong domain cần dễ hiểu hơn tên key của Elasticsearch.

### 3.3. Các kiểu giá trị được hỗ trợ

Tài liệu Spring Data Elasticsearch hiện hành liệt kê các kiểu range value phổ biến gồm `Integer`, `Long`, `Float`, `Double`, `Date` và các kiểu triển khai `TemporalAccessor` như Java Time API. Với `ip_range`, cần kiểm tra converter và biểu diễn phù hợp của phiên bản Spring Data đang dùng; nếu abstraction không chuyển đổi được kiểu IP mong muốn, có thể dùng class riêng hoặc custom converter.

Không tự động giả định mọi kiểu Java đều có thể dùng với mọi `FieldType.*_Range`. Kiểu dữ liệu trong entity, mapping Elasticsearch và converter phải tương thích với nhau.

## 4. `geo_point`: lưu một vị trí địa lý

`geo_point` lưu một điểm trên bề mặt Trái Đất bằng latitude (vĩ độ) và longitude (kinh độ). Elasticsearch dùng hệ tọa độ WGS-84.

Ví dụ một vị trí:

```json
{
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
```

Trong ví dụ, `lat` là 10.7769 và `lon` là 106.7009. Vĩ độ hợp lệ nằm trong khoảng -90 đến 90; kinh độ hợp lệ nằm trong khoảng -180 đến 180.

### 4.1. Các cách biểu diễn geo point

Elasticsearch chấp nhận nhiều dạng biểu diễn một điểm:

| Dạng | Ví dụ | Thứ tự tọa độ |
|---|---|---|
| Object có `lat` và `lon` | `{"lat": 10.77, "lon": 106.70}` | Ghi rõ tên thuộc tính |
| Array | `[106.70, 10.77]` | `[lon, lat]` |
| String | `"10.77,106.70"` | `lat,lon` |
| GeoJSON Point | `{"type":"Point","coordinates":[106.70,10.77]}` | `[lon, lat]` |
| WKT | `"POINT (106.70 10.77)"` | `POINT(lon lat)` |
| Geohash | `"w3gvk"` | Mã hóa vị trí |

Đây là nguồn lỗi thường gặp: chuỗi dạng `lat,lon` nhưng array, GeoJSON và WKT lại dùng thứ tự `lon,lat`. Hãy kiểm tra thứ tự trước khi gửi dữ liệu.

### 4.2. Mapping geo_point

Tạo mapping:

```http
PUT places
{
  "mappings": {
    "properties": {
      "name": {
        "type": "keyword"
      },
      "location": {
        "type": "geo_point"
      }
    }
  }
}
```

Ghi document:

```http
PUT places/_doc/place-1
{
  "name": "Central Store",
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
```

Field `geo_point` có thể chứa một điểm hoặc nhiều điểm. Nếu một document có nhiều điểm, các truy vấn địa lý thường khớp document khi một trong những điểm đó thỏa điều kiện.

### 4.3. Ánh xạ geo_point trong Spring Data Elasticsearch

Spring Data Elasticsearch có class `GeoPoint` trong package `org.springframework.data.elasticsearch.core.geo`. Constructor nhận latitude trước, longitude sau:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.GeoPointField;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Document(indexName = "places")
public class Place {

    @Id
    private String id;

    private String name;

    @GeoPointField
    private GeoPoint location;

    public Place() {
    }

    public Place(String id, String name, double latitude, double longitude) {
        this.id = id;
        this.name = name;
        this.location = new GeoPoint(latitude, longitude);
    }

    // Getters and setters
}
```

Spring Data có converter để chuyển `GeoPoint` thành cặp `lat`/`lon` khi ghi và chuyển ngược lại khi đọc. Tùy kiểu Java được dùng, có thể dùng `org.springframework.data.geo.Point`; Spring Data Elasticsearch cũng hỗ trợ chuyển đổi kiểu Point này sang biểu diễn lat/lon.

Nếu thuộc tính đã có kiểu `GeoPoint`, Spring Data có thể nhận diện kiểu này mà không cần annotation riêng trong một số cấu hình. `@GeoPointField` thể hiện rõ ý định mapping; `@Field(type = FieldType.Geo_Point)` cũng là cách khai báo field type thông qua annotation `@Field` ở những phiên bản hỗ trợ.

### 4.4. Các truy vấn phổ biến với geo_point

`geo_point` có thể dùng cho các nhu cầu:

- Tìm điểm trong một bán kính (`geo_distance`).
- Tìm điểm trong hình chữ nhật (`geo_bounding_box`).
- Tìm điểm nằm trong một hình học (`geo_shape` query).
- Sắp xếp document theo khoảng cách tới một điểm (`_geo_distance` sort).
- Aggregation theo khoảng cách hoặc lưới địa lý như geohash, geotile hoặc geohex.

Ví dụ tìm địa điểm cách một tâm không quá 5 km:

```http
GET places/_search
{
  "query": {
    "geo_distance": {
      "distance": "5km",
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
        "unit": "km",
        "distance_type": "arc"
      }
    }
  ]
}
```

`geo_distance` giới hạn kết quả theo bán kính. `_geo_distance` sort sắp xếp các kết quả gần trước. Khoảng cách mặc định dùng phép tính cung trên bề mặt Trái Đất (`arc`); `plane` có thể nhanh hơn nhưng kém chính xác hơn, đặc biệt ở khoảng cách lớn hoặc gần cực.

Ví dụ bounding box:

```http
GET places/_search
{
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.90,
          "lon": 106.55
        },
        "bottom_right": {
          "lat": 10.65,
          "lon": 106.85
        }
      }
    }
  }
}
```

## 5. `geo_shape`: lưu hình học địa lý

`geo_shape` dùng khi dữ liệu không chỉ là một điểm. Ví dụ, một khu vực giao hàng có ranh giới đa giác, một tuyến đường có dạng LineString hoặc một khu vực bảo vệ có nhiều vùng con.

Elasticsearch hỗ trợ hình học GeoJSON và Well-Known Text (WKT). Các loại thường gặp:

| GeoJSON | WKT | Mục đích |
|---|---|---|
| `Point` | `POINT` | Một điểm |
| `MultiPoint` | `MULTIPOINT` | Nhiều điểm rời |
| `LineString` | `LINESTRING` | Đường nối từ hai điểm trở lên |
| `MultiLineString` | `MULTILINESTRING` | Nhiều đường riêng biệt |
| `Polygon` | `POLYGON` | Vùng đa giác, có thể có lỗ bên trong |
| `MultiPolygon` | `MULTIPOLYGON` | Nhiều đa giác |
| `GeometryCollection` | `GEOMETRYCOLLECTION` | Tập hợp nhiều loại geometry |
| `envelope` | `BBOX` | Hình chữ nhật bao quanh |

GeoJSON và WKT dùng thứ tự longitude trước, latitude sau trong cặp tọa độ. Đây là thứ tự `x, y`, khác với cách thường đọc địa chỉ theo `latitude, longitude`.

### 5.1. Mapping geo_shape

Tạo index có field `serviceArea` kiểu `geo_shape`:

```http
PUT delivery-zones
{
  "mappings": {
    "properties": {
      "zoneName": {
        "type": "keyword"
      },
      "serviceArea": {
        "type": "geo_shape"
      }
    }
  }
}
```

Ghi một polygon theo GeoJSON:

```http
PUT delivery-zones/_doc/zone-1
{
  "zoneName": "District Zone",
  "serviceArea": {
    "type": "Polygon",
    "coordinates": [
      [
        [106.68, 10.78],
        [106.74, 10.78],
        [106.74, 10.82],
        [106.68, 10.82],
        [106.68, 10.78]
      ]
    ]
  }
}
```

Polygon phải đóng vòng: tọa độ đầu và tọa độ cuối của mỗi linear ring phải giống nhau. Một polygon có ít nhất bốn tọa độ trong vòng ngoài vì điểm đầu được lặp lại ở cuối. Nếu polygon có lỗ, các vòng tiếp theo mô tả vùng rỗng bên trong.

### 5.2. Orientation của polygon

GeoJSON quy định vòng ngoài theo chiều ngược kim đồng hồ (counterclockwise) và các vòng lỗ theo chiều kim đồng hồ. Elasticsearch mặc định dùng orientation `RIGHT`/counterclockwise. Với WKT, có thể cần cấu hình orientation vì WKT không áp đặt thứ tự đỉnh theo cùng cách GeoJSON.

Orientation đặc biệt quan trọng với polygon đi qua đường đổi ngày quốc tế. Nếu dữ liệu được tạo bởi một hệ GIS khác, hãy xác nhận quy ước thứ tự đỉnh trước khi lập chỉ mục.

### 5.3. Các tùy chọn mapping thường gặp

`geo_shape` có một số tùy chọn:

- `orientation`: quy định cách hiểu thứ tự đỉnh polygon.
- `ignore_malformed`: nếu bật, hình học sai định dạng có thể bị bỏ qua thay vì từ chối toàn bộ document.
- `ignore_z_value`: mặc định cho phép tọa độ có chiều thứ ba nhưng chỉ dùng longitude/latitude khi lập chỉ mục.
- `coerce`: nếu bật, Elasticsearch có thể tự đóng các linear ring chưa khép kín.
- `index`: bật/tắt khả năng tìm kiếm nhanh qua field.
- `doc_values`: điều khiển dữ liệu dạng cột phục vụ một số thao tác như aggregation/script.

Không nên bật `ignore_malformed` hoặc `coerce` để che giấu dữ liệu không hợp lệ nếu ứng dụng cần bảo đảm ranh giới địa lý chính xác. Hãy xác thực geometry ở nguồn hoặc trong quy trình ingest.

## 6. Ánh xạ GeoJSON trong Spring Data Elasticsearch

Spring Data Elasticsearch có interface `GeoJson` và các class biểu diễn những geometry phổ biến:

- `GeoJsonPoint`
- `GeoJsonMultiPoint`
- `GeoJsonLineString`
- `GeoJsonMultiLineString`
- `GeoJsonPolygon`
- `GeoJsonMultiPolygon`
- `GeoJsonGeometryCollection`

Các kiểu này được chuyển đổi thành cấu trúc GeoJSON trong document. Khi Spring Data tạo mapping cho entity, thuộc tính GeoJSON tương ứng được khai báo kiểu `geo_shape`.

Ví dụ entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.GeoShapeField;
import org.springframework.data.elasticsearch.core.geo.GeoJsonPolygon;

@Document(indexName = "delivery-zones")
public class DeliveryZone {

    @Id
    private String id;

    private String zoneName;

    @GeoShapeField
    private GeoJsonPolygon serviceArea;

    // Constructors, getters and setters
}
```

`@GeoShapeField` cung cấp các tùy chọn liên quan đến orientation, `ignoreMalformed`, `ignoreZValue` và `coerce` trong các phiên bản có annotation này. Các thuộc tính hình học vẫn được biểu diễn bằng class GeoJSON phù hợp.

Có thể tạo GeoJSON point bằng factory method:

```java
import org.springframework.data.elasticsearch.core.geo.GeoJsonPoint;

GeoJsonPoint point = GeoJsonPoint.of(106.7009, 10.7769);
```

Với `GeoJsonPoint.of(x, y)`, `x` là longitude và `y` là latitude theo quy tắc GeoJSON. Nếu đã có `GeoPoint` với constructor nhận latitude trước longitude, có thể chuyển qua `GeoJsonPoint.of(geoPoint)` để tránh tự đảo thứ tự.

Spring Data cung cấp converter cho các GeoJSON type đã hỗ trợ. Nếu ứng dụng cần geometry đặc thù không có class tương ứng trong thư viện, có thể cân nhắc biểu diễn bằng GeoJSON/WKT ở tầng client, custom converter hoặc sử dụng Elasticsearch Java API Client trực tiếp.

## 7. Truy vấn geo_shape và spatial relations

`geo_shape` query so sánh geometry được lưu trong document với query shape. Các quan hệ chính:

| Relation | Ý nghĩa |
|---|---|
| `INTERSECTS` | Hai hình học có ít nhất một điểm chung; mặc định |
| `DISJOINT` | Hai hình học không có điểm chung |
| `WITHIN` | Hình học trong document nằm hoàn toàn bên trong query shape |
| `CONTAINS` | Hình học trong document chứa toàn bộ query shape |

Ví dụ tìm những vùng giao hàng giao với một bounding rectangle:

```http
GET delivery-zones/_search
{
  "query": {
    "geo_shape": {
      "serviceArea": {
        "shape": {
          "type": "envelope",
          "coordinates": [
            [106.65, 10.85],
            [106.80, 10.70]
          ]
        },
        "relation": "intersects"
      }
    }
  }
}
```

`envelope` là dạng mở rộng của Elasticsearch để biểu diễn hình chữ nhật bằng hai góc đối diện. Nó không phải một trong các class GeoJSON mà Spring Data liệt kê ở trên.

Spatial relation của Elasticsearch được tính trên mô hình hình học hai chiều của Lucene dựa trên tọa độ longitude/latitude. Không nên mặc định `within` hoặc `contains` có mọi chi tiết giống hệt các predicate của OGC GIS/DE-9IM. Nếu ứng dụng cần ngữ nghĩa hình học chuẩn xác theo một tiêu chuẩn GIS cụ thể, hãy xác minh kết quả bằng bộ dữ liệu kiểm thử đại diện.

`WITHIN` không hỗ trợ line geometry trong geo_shape query. Các thao tác `geo_shape` cũng không phải phép đo khoảng cách địa lý theo đường trắc địa. Khi cần tìm theo bán kính trên bề mặt Trái Đất, dùng `geo_distance`.

Do cấu trúc và cách lập chỉ mục phức tạp, Elasticsearch không hỗ trợ sort trực tiếp theo `geo_shape` và không trả geometry qua field retrieval thông thường; giá trị shape được lấy từ `_source`. Nếu cần sắp xếp theo khoảng cách tới một tâm, hãy cân nhắc `geo_point` hoặc một field tính toán phù hợp.

## 8. Query geo trong Spring Data Elasticsearch

Spring Data cung cấp `Criteria` cho một số thao tác địa lý. Ví dụ tìm địa điểm trong bán kính 5 km:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.stereotype.Service;

@Service
public class PlaceSearchService {

    private final ElasticsearchOperations operations;

    public PlaceSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Place> findNearby() {
        Criteria criteria = Criteria.where("location")
                .within(new GeoPoint(10.7769, 106.7009), "5km");

        CriteriaQuery query = new CriteriaQuery(criteria);
        return operations.search(query, Place.class);
    }
}
```

Constructor `GeoPoint(latitude, longitude)` nhận latitude trước longitude. Method `within(GeoPoint, String)` tạo điều kiện tìm vị trí trong khoảng cách được chỉ định.

Với GeoJSON shape, `Criteria` cung cấp một số method như `intersects`, `within`, `contains` và `isDisjoint` trên `GeoJson`:

```java
Criteria criteria = Criteria.where("serviceArea")
        .intersects(queryPolygon);

CriteriaQuery query = new CriteriaQuery(criteria);
SearchHits<DeliveryZone> hits = operations.search(query, DeliveryZone.class);
```

Các method cụ thể có thể thay đổi theo release train. Hãy kiểm tra Javadoc của phiên bản Spring Data Elasticsearch đang sử dụng trước khi áp dụng.

## 9. Range query và geo query không đồng nghĩa với repository method

Spring Data Elasticsearch hỗ trợ repository query method, `@Query`, `CriteriaQuery`, `NativeQuery` và `ElasticsearchOperations`. Tuy nhiên, không phải mọi cấu trúc Query DSL đều có một method dẫn xuất từ tên repository.

Ví dụ `findByPriceBetween(min, max)` có thể phù hợp với một field numeric scalar, nhưng không tự động có nghĩa là truy vấn quan hệ giữa hai range fields. Tương tự, `findByLocationWithin(...)` không phải một query method có thể suy ra một cách phổ quát từ tên thuộc tính và mọi loại hình học.

Khi cần truyền chính xác `relation`, query shape, `indexed_shape`, distance type hoặc các tùy chọn Elasticsearch đặc thù, hãy dùng `NativeQuery` hoặc Elasticsearch Java API Client. Ví dụ REST Query DSL thể hiện trực tiếp cấu trúc server nhận được và phù hợp để thử nghiệm trước khi chuyển sang Java API.

### 9.1. Dùng NativeQuery khi cần Query DSL đầy đủ

`NativeQuery` là abstraction của Spring Data Elasticsearch cho các truy vấn dựa trên Elasticsearch Java API Client. Cách xây dựng query cụ thể phụ thuộc phiên bản client mà Spring Data release train sử dụng. Ví dụ khái niệm:

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

// Build a native geo query with the Elasticsearch Java API Client query builder.
// Pass the resulting query into NativeQuery.builder().withQuery(...).build().
// Then execute it with operations.search(nativeQuery, Place.class).
```

Với những query phức tạp, không nên cố ép tất cả tùy chọn vào `Criteria` nếu abstraction không biểu diễn được. Dùng Java API Client query builder giúp tận dụng các kiểu request/query được client sinh ra theo đúng phiên bản Elasticsearch.

### 9.2. Dùng REST API để xác nhận semantics

Trước khi viết query bằng Java, có thể thử trực tiếp bằng Dev Tools hoặc HTTP client:

```http
GET places/_search
{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "location": [106.7009, 10.7769]
    }
  }
}
```

Khi kết quả đúng, chuyển cấu trúc query sang `NativeQuery` hoặc client API. Cách này giúp tách lỗi về semantics Query DSL khỏi lỗi chuyển đổi object Java.

## 10. Phạm vi hỗ trợ của Spring Data Elasticsearch

Để chọn đúng abstraction, cần tách hỗ trợ thành các lớp:

| Lớp | Spring Data hỗ trợ | Khi nào cần API cấp thấp hơn? |
|---|---|---|
| Mapping range | Có `FieldType` cho sáu range type và converter cho `Range<T>`/class biểu diễn cận | Khi cần kiểu range hoặc định dạng IP chưa có converter phù hợp |
| Mapping `geo_point` | Có `GeoPoint`, `Point`, converter lat/lon và annotation field | Khi cần mapping option mới của Elasticsearch chưa được annotation phiên bản đó expose |
| Mapping `geo_shape` | Có các GeoJSON type phổ biến và `@GeoShapeField` | Khi cần geometry đặc biệt hoặc cấu trúc chưa có class GeoJSON tương ứng |
| Query địa lý | `Criteria` có một số method distance, bounding box và GeoJSON relation; có `GeoDistanceOrder` cho sort khoảng cách | Khi cần toàn bộ tùy chọn của `geo_distance`, `geo_shape`, indexed shape hoặc API mới |
| Query range | Có các query abstraction thông thường và `NativeQuery` | Khi cần quan hệ range cụ thể hoặc Query DSL mới mà abstraction không cung cấp |
| Quản lý mapping | `@Field`, `@GeoPointField`, `@GeoShapeField`, `IndexOperations` | Khi cần mapping JSON/setting mới chưa được hỗ trợ trong annotation |

Spring Data tập trung vào mapping object và abstraction thao tác dữ liệu. Elasticsearch server mới là nơi thực thi các quy tắc mapping, range relation, spatial relation và giới hạn field type. Việc một kiểu dữ liệu tồn tại trong Elasticsearch không có nghĩa mọi tính năng của kiểu đó đã có một method tiện dụng trong Spring Data.

### 10.1. Kiểm tra phiên bản thư viện

Các class, annotation và query builder thay đổi theo release train. Khi đọc ví dụ trên mạng, cần kiểm tra:

- Phiên bản Spring Boot đang dùng quản lý Spring Data Elasticsearch phiên bản nào.
- `FieldType` của phiên bản có enum tương ứng như `Geo_Point`, `Geo_Shape`, `Integer_Range` hay không.
- Class `Range` được import từ `org.springframework.data.domain` hay package cũ `org.springframework.data.elasticsearch.core`.
- Các `GeoJson` class và `Criteria` method cần dùng có trong Javadoc của phiên bản đó không.
- Elasticsearch server có hỗ trợ query option hoặc mapping parameter mà code đang gửi không.

Không nâng riêng Elasticsearch Java API Client lên một major version khác với phiên bản Spring Data đang sử dụng nếu chưa kiểm tra tương thích. Spring Data Elasticsearch tích hợp client theo dependency train; request type và builder phải tương thích với client thực tế trên classpath.

### 10.2. Mapping tự động không thay thế kiểm tra mapping thực tế

Spring Data có thể tạo mapping từ annotation và metadata entity. Tuy nhiên, index có thể đã được tạo trước đó, hoặc mapping được quản lý bởi index template. Thay đổi annotation không tự động sửa mapping hiện hữu.

Sau khi tạo index, kiểm tra mapping:

```http
GET places/_mapping
```

```http
GET delivery-zones/_mapping
```

Nếu field đang là `object` thay vì `geo_point` hoặc `geo_shape`, các truy vấn địa lý sẽ không hoạt động như mong muốn. Nếu range field bị tạo thành numeric/date scalar, query theo range relation cũng không có semantics của range field.

## 11. Các lỗi thường gặp

### Đảo thứ tự latitude và longitude

`GeoPoint(latitude, longitude)` nhận latitude trước. GeoJSON và array của Elasticsearch dùng `[longitude, latitude]`. Kiểm tra quy tắc của biểu diễn trước khi tạo object hoặc JSON.

### Dùng `geo_point` cho dữ liệu vùng

Một điểm không thể thể hiện đầy đủ ranh giới đa giác. Nếu cần kiểm tra giao nhau hoặc chứa nhau giữa vùng, hãy dùng `geo_shape`.

### Dùng `geo_shape` cho mọi điểm dù không cần hình học

Nếu chỉ lưu vị trí đơn giản và cần distance sort, radius query hoặc distance aggregation, `geo_point` thường đơn giản và phù hợp hơn.

### Polygon không khép kín

Vòng ngoài hoặc vòng lỗ của polygon cần có điểm đầu và điểm cuối trùng nhau. Dữ liệu không khép kín có thể bị Elasticsearch từ chối trừ khi cấu hình `coerce` cho phép tự đóng vòng.

### Sai orientation của polygon

Thứ tự đỉnh có thể làm thay đổi cách Elasticsearch hiểu vùng polygon, đặc biệt khi hình học đi qua đường đổi ngày. Xác nhận quy tắc orientation của nguồn dữ liệu và mapping.

### Dùng nhầm `Range` class

Trong Spring Data Elasticsearch 5.x trở lên, lớp `org.springframework.data.elasticsearch.core.Range` đã deprecated để chuyển sang `org.springframework.data.domain.Range`. Kiểm tra import nếu compiler cảnh báo hoặc API không tương thích.

### Mong đợi `Criteria` hỗ trợ mọi Query DSL option

`Criteria` là abstraction tiện dụng cho một phần truy vấn. Nếu cần một relation, option hoặc cấu trúc phức tạp chưa được expose, dùng `NativeQuery` hoặc Elasticsearch Java API Client.

### Nhầm range field với range query trên scalar field

Một field `long` lưu một số; một field `long_range` lưu một khoảng. Cấu trúc document và semantics query khác nhau. Kiểm tra mapping trước khi thiết kế query.

### Dùng `geo_shape` để đo khoảng cách chính xác trên bề mặt Trái Đất

Spatial relation của geo_shape dựa trên mô hình hình học hai chiều. Khi cần bán kính theo khoảng cách địa lý, dùng `geo_distance` và chọn distance type phù hợp.

## 12. Quy trình triển khai

Khi thiết kế một entity có range hoặc dữ liệu địa lý, có thể làm theo quy trình:

1. Xác định dữ liệu là giá trị đơn, khoảng giá trị, điểm hay hình học.
2. Chọn field type tương ứng: scalar, `*_range`, `geo_point` hoặc `geo_shape`.
3. Chọn kiểu Java được Spring Data hỗ trợ; với range hiện hành, cân nhắc `org.springframework.data.domain.Range<T>`.
4. Khai báo mapping bằng `@Field`, `@GeoPointField` hoặc `@GeoShapeField` phù hợp với release train.
5. Xác định quy tắc cận mở/đóng của range và thứ tự tọa độ của dữ liệu địa lý.
6. Kiểm tra converter và mapping JSON thực tế sau khi tạo index.
7. Thử query trực tiếp bằng Elasticsearch Query DSL để xác nhận semantics.
8. Chuyển query sang `Criteria` nếu abstraction đáp ứng đầy đủ nhu cầu; nếu không, dùng `NativeQuery`/Elasticsearch Java API Client.
9. Kiểm thử với dữ liệu biên: cận bằng nhau, khoảng không giới hạn, tọa độ biên, polygon có lỗ và hình học đi qua đường đổi ngày.
10. Theo dõi phiên bản Spring Data và Elasticsearch server khi nâng cấp để xác nhận field type và query option còn tương thích.

## 13. Tổng kết

Range fields lưu một khoảng giá trị trong mỗi document và hỗ trợ so sánh khoảng bằng `intersects`, `contains` hoặc `within`. `geo_point` lưu vị trí latitude/longitude để tìm theo bán kính, bounding box, sort và aggregation địa lý. `geo_shape` lưu hình học như đường và polygon để truy vấn quan hệ không gian.

Spring Data Elasticsearch hỗ trợ mapping các range type, `GeoPoint`/`Point` và các GeoJSON geometry phổ biến. `Criteria` cung cấp một phần query địa lý và `ElasticsearchOperations` thực thi truy vấn; với Query DSL nâng cao hoặc option chưa được abstraction expose, hãy dùng `NativeQuery` hoặc Elasticsearch Java API Client. Nắm rõ sự khác nhau giữa mapping, kiểu Java và Query DSL giúp chọn đúng cấu trúc dữ liệu, tránh lỗi thứ tự tọa độ và không nhầm giới hạn của Spring Data với khả năng của Elasticsearch server.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – Object Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch – Criteria API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/Criteria.html)
- [Elasticsearch – Range field types](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/range)
- [Elasticsearch – Geo point field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/geo-point)
- [Elasticsearch – Geo shape field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/geo-shape)
- [Elasticsearch – Geo queries](https://www.elastic.co/docs/reference/query-languages/query-dsl/geo-queries)
