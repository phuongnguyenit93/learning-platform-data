# Tìm địa điểm theo bán kính và thứ tự khoảng cách

Elasticsearch có thể lưu tọa độ địa lý trong field `geo_point` để tìm các document nằm trong một bán kính quanh vị trí người dùng và sắp xếp kết quả từ gần đến xa. Trong Spring Data Elasticsearch, có thể khai báo field tọa độ trên entity, tạo điều kiện `geo_distance` bằng `NativeQuery` và thêm sort theo khoảng cách địa lý.

Một request tìm địa điểm thường có ba phần độc lập:

1. **Điểm gốc (origin):** vị trí người dùng hoặc tâm tìm kiếm.
2. **Bán kính (radius):** giới hạn khoảng cách tối đa, ví dụ 5 km.
3. **Thứ tự khoảng cách:** sắp xếp tăng dần để địa điểm gần nhất xuất hiện trước.

Điều quan trọng là dùng đúng thứ tự latitude/longitude, đặt điều kiện bán kính trong query filter và dùng `_geo_distance` sort cho thứ tự kết quả. Query giới hạn bán kính và sort khoảng cách là hai thao tác riêng; chỉ thêm sort không tự giới hạn kết quả trong radius.

## 1. Mô hình dữ liệu địa lý

Elasticsearch hỗ trợ hai kiểu dữ liệu địa lý chính:

- `geo_point`: biểu diễn một vị trí bằng latitude và longitude.
- `geo_shape`: biểu diễn hình dạng phức tạp như polygon, multipolygon, line hoặc vùng địa lý.

Bài toán tìm cửa hàng, nhà hàng, bệnh viện hoặc trạm xe quanh một điểm thường dùng `geo_point`. Mỗi document có một tọa độ đại diện cho địa điểm.

Ví dụ document:

~~~json
{
  "name": "Central Coffee",
  "category": "CAFE",
  "status": "OPEN",
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
~~~

Trong đó:

- `lat`: vĩ độ (latitude), khoảng từ -90 đến +90.
- `lon`: kinh độ (longitude), khoảng từ -180 đến +180.
- `location`: field được mapping thành `geo_point`.

Không dùng `double` hoặc `keyword` thông thường cho tọa độ nếu cần geo query và geo-distance sort. Mapping phải là `geo_point` để Elasticsearch hiểu dữ liệu theo hệ tọa độ địa lý.

### 1.1. Latitude và longitude khác nhau thế nào?

Latitude đo vị trí theo hướng Bắc–Nam:

- Xích đạo là 0°.
- Bắc bán cầu có latitude dương.
- Nam bán cầu có latitude âm.
- Cực Bắc là +90°, cực Nam là -90°.

Longitude đo vị trí theo hướng Đông–Tây:

- Kinh tuyến gốc Greenwich là 0°.
- Phía Đông có longitude dương.
- Phía Tây có longitude âm.
- Giá trị nằm trong khoảng -180° đến +180°.

Ví dụ tọa độ khu vực trung tâm Thành phố Hồ Chí Minh có thể xấp xỉ:

~~~text
latitude  = 10.7769
longitude = 106.7009
~~~

Đây là tọa độ minh họa; ứng dụng cần dùng tọa độ chính xác từ nguồn dữ liệu địa điểm hoặc thiết bị định vị.

### 1.2. Cẩn thận thứ tự tọa độ

Các API và định dạng không phải lúc nào cũng dùng cùng thứ tự.

| Biểu diễn | Thứ tự |
| --- | --- |
| Object `geo_point` | `lat`, rồi `lon` |
| Chuỗi Elasticsearch | `"lat,lon"` |
| Array Elasticsearch | `[lon, lat]` |
| GeoJSON | `[longitude, latitude]` |
| Spring Data `GeoPoint` | Thường truyền `(latitude, longitude)` |

Ví dụ cùng một vị trí:

~~~json
{
  "lat": 10.7769,
  "lon": 106.7009
}
~~~

Array tương ứng:

~~~json
[106.7009, 10.7769]
~~~

Đây là lỗi phổ biến nhất khi tích hợp dữ liệu bản đồ: đảo latitude và longitude có thể tạo ra một vị trí hoàn toàn khác nhưng vẫn nằm trong miền giá trị hợp lệ. Vì vậy, chỉ kiểm tra latitude nằm trong [-90, 90] và longitude nằm trong [-180, 180] chưa đủ để phát hiện đảo trục.

### 1.3. Chọn một định dạng lưu trữ thống nhất

Elasticsearch chấp nhận nhiều cách biểu diễn `geo_point`, nhưng nên chuẩn hóa payload ở phía ứng dụng thành object có field rõ ràng:

~~~json
{
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
~~~

Object rõ nghĩa giúp giảm nhầm lẫn khi serialize, đọc log và kiểm tra dữ liệu. Với API bên ngoài dùng GeoJSON, hãy chuyển đổi từ `[lon, lat]` sang object `{lat, lon}` ở boundary của ứng dụng.

## 2. Khai báo mapping `geo_point`

Có thể tạo index với mapping tường minh:

~~~http
PUT /places
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "category": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      },
      "location": {
        "type": "geo_point"
      }
    }
  }
}
~~~

Sau khi tạo index, kiểm tra mapping:

~~~http
GET /places/_mapping
~~~

Kết quả cần thể hiện:

~~~json
{
  "properties": {
    "location": {
      "type": "geo_point"
    }
  }
}
~~~

Mapping nên được tạo trước khi index document đầu tiên. Nếu dynamic mapping đã suy luận `location` thành object thường hoặc field khác, chỉ đổi annotation Java không thể chuyển field đó thành `geo_point` trong index hiện tại. Khi cần đổi type, tạo index mới với mapping đúng rồi reindex dữ liệu.

### 2.1. Mapping field trong Spring Data Elasticsearch

Spring Data Elasticsearch có annotation `@GeoPointField` dành cho property tọa độ.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.GeoPointField;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Document(indexName = "places")
public class PlaceDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Keyword)
    private String status;

    @GeoPointField
    private GeoPoint location;

    // Constructor, getters và setters
}
~~~

`GeoPoint` của Spring Data Elasticsearch biểu diễn latitude và longitude. Khi khởi tạo, truyền latitude trước, longitude sau:

~~~java
GeoPoint location = new GeoPoint(10.7769, 106.7009);
~~~

Trong một số phiên bản, API factory hoặc package có thể có khác biệt. Dùng `org.springframework.data.elasticsearch.core.geo.GeoPoint` của dependency đang cài đặt và kiểm tra mapping thực tế sau khi tạo index.

Một lựa chọn khác là khai báo field bằng `@Field(type = FieldType.GeoPoint)` nếu phiên bản Spring Data đang dùng cung cấp enum tương ứng. `@GeoPointField` thể hiện rõ ý định mapping và thường dễ đọc hơn.

### 2.2. Lưu địa điểm

Ví dụ service lưu một địa điểm:

~~~java
@Service
public class PlaceService {

    private final ElasticsearchOperations operations;

    public PlaceService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public PlaceDocument save(
            String id,
            String name,
            String category,
            double latitude,
            double longitude) {

        PlaceDocument place = new PlaceDocument();
        place.setId(id);
        place.setName(name);
        place.setCategory(category);
        place.setStatus("OPEN");
        place.setLocation(new GeoPoint(latitude, longitude));

        return operations.save(place);
    }
}
~~~

Giá trị latitude/longitude phải được validate trước khi tạo `GeoPoint`. Nếu tọa độ đến từ client, API nên kiểm tra miền giá trị, kiểu số và quy ước trục. Nếu địa điểm đến từ geocoding provider, giữ nguồn và thời điểm cập nhật tọa độ để có thể điều tra dữ liệu sai.

## 3. Tìm document trong bán kính bằng `geo_distance`

Geo-distance query lọc document dựa trên khoảng cách giữa một điểm gốc và field `geo_point`.

Ví dụ tìm địa điểm trong bán kính 5 km quanh vị trí người dùng:

~~~http
GET /places/_search
Content-Type: application/json

{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "location": {
        "lat": 10.7769,
        "lon": 106.7009
      }
    }
  }
}
~~~

Ý nghĩa:

- `distance`: bán kính tối đa.
- `location`: field `geo_point` trong document.
- `lat`, `lon`: tọa độ tâm tìm kiếm.

Elasticsearch chỉ trả các document có khoảng cách tới điểm gốc nằm trong bán kính đã khai báo.

### 3.1. Đơn vị khoảng cách

Có thể biểu diễn khoảng cách bằng nhiều đơn vị:

| Đơn vị | Ví dụ |
| --- | --- |
| Kilomet | `5km` |
| Metre | `5000m` |
| Mile | `3mi` |
| Yard | `5000yd` |
| Foot | `16000ft` |
| Nautical mile | `2.7nmi` |
| Centimetre | `500000cm` |
| Millimetre | `5000000mm` |

Nên chọn một đơn vị thống nhất ở API. Ví dụ API nhận `radiusKm`, service chuyển thành chuỗi `5km` khi tạo query. Không trộn kilomet và metre trong cùng một contract mà không có tên field thể hiện đơn vị.

### 3.2. Thêm điều kiện nghiệp vụ

Tìm địa điểm gần nhất thường cần lọc thêm category hoặc status. Đặt các điều kiện trong `bool.filter` để chúng giới hạn tập kết quả mà không ảnh hưởng relevance score.

~~~http
GET /places/_search
Content-Type: application/json

{
  "query": {
    "bool": {
      "filter": [
        {
          "geo_distance": {
            "distance": "5km",
            "location": {
              "lat": 10.7769,
              "lon": 106.7009
            }
          }
        },
        {
          "term": {
            "category": "CAFE"
          }
        },
        {
          "term": {
            "status": "OPEN"
          }
        }
      ]
    }
  }
}
~~~

Query này trả các quán cà phê đang mở trong phạm vi 5 km. Nếu dùng `must` với match query cho tên hoặc mô tả, Elasticsearch có thể tính relevance score cho phần text; các điều kiện radius và trạng thái vẫn nên đặt trong filter.

### 3.3. Geo-distance query dùng `arc` hay `plane`?

Elasticsearch hỗ trợ hai cách tính khoảng cách trong một số geo operation:

- `arc`: tính khoảng cách theo cung trên bề mặt Trái Đất. Đây là lựa chọn mặc định và phù hợp với phần lớn ứng dụng địa lý.
- `plane`: dùng phép tính phẳng gần đúng, có thể nhanh hơn nhưng sai số tăng theo khoảng cách và vĩ độ.

Ví dụ:

~~~json
{
  "geo_distance": {
    "distance": "5km",
    "distance_type": "arc",
    "location": {
      "lat": 10.7769,
      "lon": 106.7009
    }
  }
}
~~~

Với tìm kiếm địa điểm quanh người dùng, thường giữ `arc`. Chỉ chọn `plane` sau khi benchmark và xác nhận sai số phù hợp với use case. Không dùng phép tính phẳng cho khoảng cách lớn hoặc vùng gần cực nếu độ chính xác địa lý quan trọng.

## 4. Sắp xếp theo khoảng cách với `_geo_distance`

Geo-distance filter chỉ giới hạn document trong radius. Nó không tự đảm bảo document gần nhất đứng đầu. Để sắp xếp, thêm `_geo_distance` vào mảng `sort`.

Ví dụ đầy đủ:

~~~http
GET /places/_search
Content-Type: application/json

{
  "size": 20,
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
~~~

Các thuộc tính:

- `location`: field địa lý cần tính khoảng cách.
- `order: asc`: gần nhất trước.
- `order: desc`: xa nhất trước.
- `unit`: đơn vị khoảng cách hiển thị trong sort value.
- `distance_type`: cách tính khoảng cách.

**Phải có cả `geo_distance` query và `_geo_distance` sort** nếu yêu cầu là “tìm trong bán kính rồi xếp từ gần đến xa”.

Nếu chỉ có `_geo_distance` sort, Elasticsearch vẫn có thể sắp xếp các document khớp query khác, kể cả document nằm ngoài bán kính. Nếu chỉ có `geo_distance` query, kết quả bị giới hạn đúng radius nhưng thứ tự mặc định không phải thứ tự gần nhất.

### 4.1. Sort value là khoảng cách, không phải tọa độ

Mỗi hit có thể chứa sort value do Elasticsearch tính. Khi sort theo `_geo_distance`, giá trị sort là khoảng cách từ origin đến document, theo đơn vị đã chọn.

Ví dụ response rút gọn:

~~~json
{
  "hits": {
    "hits": [
      {
        "_id": "place-01",
        "_source": {
          "name": "Cafe A",
          "location": {
            "lat": 10.7771,
            "lon": 106.7010
          }
        },
        "sort": [0.024]
      },
      {
        "_id": "place-02",
        "_source": {
          "name": "Cafe B",
          "location": {
            "lat": 10.7800,
            "lon": 106.7040
          }
        },
        "sort": [0.45]
      }
    ]
  }
}
~~~

Các số trong ví dụ là khoảng cách minh họa tính bằng kilomet. Có thể dùng sort value để hiển thị khoảng cách gần đúng trong kết quả API mà không cần tự tính lại từ tọa độ. Nếu ứng dụng cần định dạng như “450 m” hoặc “1,2 km”, chuyển đổi và làm tròn ở tầng presentation.

### 4.2. Nhiều điểm trong một document

Một `geo_point` field có thể chứa nhiều tọa độ. Khi sort, Elasticsearch cần một quy tắc tổng hợp khoảng cách từ các điểm đó, ví dụ `min`, `max`, `avg` hoặc `median` tùy operation hỗ trợ.

Với document biểu diễn một địa điểm có một vị trí duy nhất, nên lưu một `geo_point` để tránh semantics mơ hồ. Với document có nhiều chi nhánh, cân nhắc mỗi chi nhánh là một document riêng để mỗi kết quả có vị trí và khoảng cách rõ ràng.

## 5. Triển khai query bằng Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp `NativeQuery` để dùng query DSL của Elasticsearch Java API Client. Cách này phù hợp với `geo_distance`, vì có thể dùng đầy đủ các thuộc tính của Elasticsearch query.

Ví dụ tạo geo-distance query:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

public class PlaceSearchService {

    private final ElasticsearchOperations operations;

    public PlaceSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<PlaceDocument> findWithinRadius(
            double latitude,
            double longitude,
            String radius) {

        Query geoDistanceQuery = Query.of(q -> q.geoDistance(g -> g
                .field("location")
                .distance(radius)
                .location(location -> location.latlon(point -> point
                        .lat(latitude)
                        .lon(longitude)
                ))
        ));

        NativeQuery query = NativeQuery.builder()
                .withQuery(geoDistanceQuery)
                .build();

        return operations.search(query, PlaceDocument.class);
    }
}
~~~

Ở đây:

- `Query.of(...)` tạo một Elasticsearch query.
- `geoDistance(...)` tạo `geo_distance` query.
- `field("location")` chỉ định field `geo_point`.
- `distance(radius)` nhận chuỗi có đơn vị như `5km`.
- `latlon(...)` nhận latitude và longitude riêng biệt.
- `NativeQuery` chuyển query vào Spring Data Elasticsearch.

Tên method generated trong Java API Client có thể khác theo version client được Spring Data quản lý. Nếu nâng version Spring Data, hãy dùng API client tương thích do dependency quản lý và kiểm tra compile.

### 5.1. Kết hợp filter với geo-distance

Có thể thêm category và status vào bool filter:

~~~java
Query queryDsl = Query.of(q -> q.bool(b -> b
        .filter(f -> f.geoDistance(g -> g
                .field("location")
                .distance("5km")
                .location(location -> location.latlon(point -> point
                        .lat(latitude)
                        .lon(longitude)
                ))
        ))
        .filter(f -> f.term(t -> t
                .field("category")
                .value("CAFE")
        ))
        .filter(f -> f.term(t -> t
                .field("status")
                .value("OPEN")
        ))
));

NativeQuery query = NativeQuery.builder()
        .withQuery(queryDsl)
        .build();
~~~

Các filter độc lập được Elasticsearch kết hợp theo AND. Chỉ những document đồng thời nằm trong radius, đúng category và đang mở mới được trả về.

### 5.2. Sort theo khoảng cách trong Spring Data

Spring Data Elasticsearch có `GeoDistanceOrder` để biểu diễn sort theo khoảng cách trong Spring `Sort`.

Ví dụ:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.query.GeoDistanceOrder;

GeoPoint origin = new GeoPoint(latitude, longitude);

Sort distanceSort = Sort.by(
        new GeoDistanceOrder("location", origin)
);

NativeQuery query = NativeQuery.builder()
        .withQuery(geoDistanceQuery)
        .withSort(distanceSort)
        .withPageable(PageRequest.of(0, 20))
        .build();

SearchHits<PlaceDocument> hits =
        operations.search(query, PlaceDocument.class);
~~~

`GeoDistanceOrder` mặc định sắp xếp theo khoảng cách tăng dần trong API Spring Data tương ứng. Một số version có thêm tùy chọn unit, distance type hoặc sort mode. Nếu cần kiểm soát chính xác `unit: km`, `distance_type: arc` hoặc các option khác, kiểm tra API `GeoDistanceOrder` của dependency đang dùng; có thể dùng `SortOptions` từ Elasticsearch Java API Client nếu abstraction không expose thuộc tính cần thiết.

Không truyền `Sort.by("location")` thông thường để thay thế geo-distance sort. Sort theo field `geo_point` cần origin và semantics khoảng cách, không phải lexical/numeric field sort.

### 5.3. Lấy khoảng cách từ kết quả

`SearchHit<T>` chứa document content, ID, score và metadata của hit. Với geo-distance sort, sort values được trả về trong hit metadata theo API version.

Ví dụ:

~~~java
for (SearchHit<PlaceDocument> hit : hits) {
    PlaceDocument place = hit.getContent();

    List<Object> sortValues = hit.getSortValues();

    System.out.println(place.getName());
    System.out.println(sortValues);
}
~~~

Sort value có thể là một số hoặc kiểu biểu diễn phụ thuộc client/version. Nếu API sản phẩm cần trường `distanceKm`, hãy parse sort value theo contract đã xác định và trả về DTO, không làm rò metadata Elasticsearch vào domain entity.

## 6. Tạo API tìm kiếm địa điểm quanh người dùng

Một endpoint thực tế có thể nhận:

~~~http
GET /api/places/nearby?lat=10.7769&lon=106.7009&radiusKm=5&category=CAFE&page=0&size=20
~~~

API cần validate:

- `lat` nằm trong [-90, 90].
- `lon` nằm trong [-180, 180].
- `radiusKm` lớn hơn 0 và không vượt giới hạn nghiệp vụ.
- `size` có giới hạn tối đa.
- `category` thuộc danh sách được hỗ trợ.
- Nếu không có category, bỏ filter category thay vì tạo term filter với giá trị null.

Ví dụ DTO:

~~~java
public record NearbyPlaceRequest(
        double latitude,
        double longitude,
        double radiusKm,
        String category,
        int page,
        int size
) {
}
~~~

Validate input trước khi truy cập Elasticsearch:

~~~java
public void validate(NearbyPlaceRequest request) {
    if (request.latitude() < -90 || request.latitude() > 90) {
        throw new IllegalArgumentException("Latitude is out of range");
    }

    if (request.longitude() < -180 || request.longitude() > 180) {
        throw new IllegalArgumentException("Longitude is out of range");
    }

    if (request.radiusKm() <= 0 || request.radiusKm() > 100) {
        throw new IllegalArgumentException("Radius is out of range");
    }

    if (request.size() <= 0 || request.size() > 100) {
        throw new IllegalArgumentException("Page size is out of range");
    }

    if (request.page() < 0) {
        throw new IllegalArgumentException("Page must not be negative");
    }
}
~~~

Giới hạn 100 km và page size 100 chỉ là ví dụ. Sản phẩm cần chọn giới hạn dựa trên use case, chi phí query và trải nghiệm người dùng.

### 6.1. Chuyển radius thành đơn vị rõ ràng

Nếu API nhận kilomet:

~~~java
String distance = request.radiusKm() + "km";
~~~

Với input số thập phân, có thể format bằng `Locale.ROOT` để tránh dấu phẩy thập phân theo locale:

~~~java
String distance = String.format(
        Locale.ROOT,
        "%.3fkm",
        request.radiusKm()
);
~~~

Không nối chuỗi từ input không được validate vào Query DSL. Dùng kiểu số trong DTO, validate miền giá trị và tự tạo chuỗi đơn vị ở service.

### 6.2. DTO response có khoảng cách

Ví dụ response:

~~~json
{
  "items": [
    {
      "id": "place-01",
      "name": "Cafe A",
      "latitude": 10.7771,
      "longitude": 106.7010,
      "distanceKm": 0.024
    }
  ],
  "page": 0,
  "size": 20
}
~~~

Khoảng cách có thể lấy từ geo sort value. Nếu tính ở ứng dụng, dùng công thức địa lý phù hợp như Haversine và thống nhất đơn vị. Không tính khoảng cách phẳng bằng phép trừ latitude/longitude rồi coi kết quả là kilomet.

## 7. Tìm kiếm theo radius và text cùng lúc

Một use case phổ biến là tìm một loại địa điểm gần người dùng và có tên/mô tả khớp từ khóa.

Ví dụ tìm “phở” trong bán kính 3 km:

~~~http
GET /places/_search
Content-Type: application/json

{
  "size": 20,
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "phở",
            "fields": ["name^2", "description"]
          }
        }
      ],
      "filter": [
        {
          "geo_distance": {
            "distance": "3km",
            "location": {
              "lat": 10.7769,
              "lon": 106.7009
            }
          }
        },
        {
          "term": {
            "status": "OPEN"
          }
        }
      ]
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
~~~

Ở ví dụ này, text query nằm trong `must` và có thể ảnh hưởng `_score`, nhưng sort chính được ưu tiên theo khoảng cách. Nếu muốn ưu tiên relevance trước, có thể sort theo `_score` descending rồi mới theo distance; nếu muốn gần nhất luôn đứng đầu, giữ geo-distance sort là tiêu chí đầu tiên.

Cần chọn thứ tự theo mục tiêu sản phẩm:

| Mục tiêu | Sort |
| --- | --- |
| Địa điểm gần nhất luôn đứng đầu | Geo distance ascending. |
| Kết quả text phù hợp nhất đứng đầu | `_score` descending, sau đó distance ascending. |
| Ưu tiên relevance nhưng gần hơn khi score ngang nhau | `_score` desc rồi `_geo_distance` asc. |
| Chỉ tìm trong radius, không cần thứ tự gần nhất | Query `geo_distance`, sort theo tiêu chí khác hoặc mặc định. |

Không giả định query score và distance tự được kết hợp thành một ranking hợp lý. Nếu cần ranking kết hợp, hãy định nghĩa scoring/ranking policy rõ ràng và benchmark với dữ liệu relevance.

## 8. Phân trang và thứ tự ổn định

Có thể dùng `from`/`size` hoặc `PageRequest` cho phân trang đơn giản. Tuy nhiên, nếu nhiều địa điểm có cùng khoảng cách đã làm tròn, thứ tự giữa chúng có thể không ổn định.

Để có thứ tự ổn định, thêm một tie-breaker có tính duy nhất, thường là `_id` hoặc một keyword ID field.

Ví dụ:

~~~json
{
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
    },
    {
      "_id": "asc"
    }
  ]
}
~~~

Với page sâu, `from`/`size` khiến Elasticsearch phải giữ nhiều kết quả ở mỗi shard. Dùng `search_after` cho phân trang sâu nếu query và sort phù hợp.

### 8.1. Search after với geo-distance sort

`search_after` cần gửi lại sort values của hit cuối trang trước. Với geo-distance sort, sort value chứa khoảng cách; tie-breaker giúp xác định thứ tự duy nhất.

Luồng:

1. Gửi trang đầu với geo-distance sort và `_id`.
2. Lấy sort values của hit cuối cùng.
3. Gửi request tiếp theo với `search_after` chứa các sort values đó.
4. Giữ nguyên origin, radius, filter và sort trong các request sau.

Nếu origin thay đổi giữa các trang, sort order thay đổi và `search_after` không còn đại diện cho cùng một thứ tự. Với dữ liệu thay đổi liên tục, cân nhắc Point in Time (PIT) cùng `search_after` để giữ một view nhất quán trong quá trình duyệt.

Không dùng `search_after` với sort values từ request khác hoặc query khác.

## 9. Nhiều index và alias

Nếu query đi qua alias chứa nhiều index, tất cả index cần có mapping `location` tương thích là `geo_point`. Nếu một index có `location` là object thông thường hoặc thiếu mapping, query hoặc sort có thể lỗi tùy `ignore_unmapped` và API.

Kiểm tra mapping:

~~~http
GET /places-*/_mapping/field/location
~~~

Khi alias chứa các index version khác nhau:

- Dùng cùng field name và type.
- Giữ tọa độ cùng semantics.
- Kiểm tra index cũ trước khi thêm vào alias.
- Không để index chưa có field geo_point tham gia search mà không có chủ đích.
- Nếu cần bỏ qua index thiếu field trong sort, đánh giá `ignore_unmapped` và semantics kết quả.

Không nên dùng `ignore_unmapped` để che mapping lỗi của index đáng lẽ phải có tọa độ. Nó hữu ích trong một số truy vấn qua tập index không đồng nhất, nhưng cần hiểu rõ index nào bị bỏ qua.

## 10. Các tình huống địa lý dễ gây lỗi

### 10.1. Đảo latitude và longitude

Triệu chứng: query hợp lệ nhưng không tìm thấy địa điểm gần vị trí dự kiến, hoặc kết quả xuất hiện ở một khu vực khác.

Kiểm tra:

- Dữ liệu đầu vào có phải `[lon, lat]` từ GeoJSON không?
- Constructor Spring Data có nhận `(lat, lon)` không?
- Query DSL có dùng object `lat`/`lon` đúng không?
- Client map có trả thứ tự khác không?

Tạo unit test cho conversion từ GeoJSON sang `GeoPoint`.

### 10.2. Tọa độ ngoài miền

Latitude ngoài [-90, 90] hoặc longitude ngoài [-180, 180] thường cho thấy dữ liệu sai hoặc đảo trục. Validate ở API boundary trước khi index.

### 10.3. Điểm ở hai phía đường đổi ngày quốc tế

Longitude gần +180° và -180° nằm gần nhau về địa lý dù giá trị số khác nhau rất lớn. Không tự tính khoảng cách bằng hiệu longitude đơn giản. Geo-distance của Elasticsearch xử lý tọa độ trên bề mặt Trái Đất.

### 10.4. Khu vực gần cực

Khoảng cách longitude không tương ứng với cùng một quãng đường thực tế ở mọi latitude. Gần cực, kinh tuyến hội tụ. Dùng `geo_distance` thay vì phép tính phẳng tự viết nếu cần khoảng cách địa lý.

### 10.5. Điểm không có tọa độ

Document thiếu `location` sẽ không match geo-distance query. Không tạo tọa độ mặc định như `(0,0)` để lấp dữ liệu thiếu; vị trí giả có thể khiến document xuất hiện trong tìm kiếm quanh Vịnh Guinea.

Hãy phân biệt:

- Document có tọa độ hợp lệ.
- Document chưa geocode.
- Document geocode thất bại.
- Document có tọa độ bị đánh dấu không đáng tin cậy.

Có thể lưu `locationStatus` hoặc trạng thái tương tự để xử lý dữ liệu thiếu.

### 10.6. Tọa độ cũ hoặc sai độ chính xác

Vị trí địa điểm có thể thay đổi. Cần lưu `locationUpdatedAt`, nguồn tọa độ và độ chính xác nếu provider cung cấp. Với ứng dụng giao hàng hoặc tìm trạm dịch vụ, tọa độ sai vài trăm mét có thể ảnh hưởng kết quả.

## 11. Kiểm thử radius search

Nên tạo dữ liệu có khoảng cách biết trước để xác nhận query và sort.

Ví dụ fixture:

| ID | Vị trí | Kỳ vọng với radius 5 km |
| --- | --- | --- |
| A | Cách origin khoảng 0,5 km | Có kết quả, đứng trước B. |
| B | Cách origin khoảng 2 km | Có kết quả. |
| C | Cách origin khoảng 4,9 km | Có kết quả. |
| D | Cách origin khoảng 5,1 km | Bị loại. |
| E | Không có location | Bị loại khỏi geo-distance query. |

Các khoảng cách cần được tạo bằng tọa độ tính toán hoặc fixture đã kiểm chứng, không ước lượng chỉ bằng mắt trên bản đồ.

### 11.1. Test filter radius

Kiểm tra:

- Document ngay bên trong radius được trả về.
- Document ngoài radius bị loại.
- Document đúng category/status được trả về.
- Document sai category/status bị loại.
- Document không có location không xuất hiện.
- Radius rất nhỏ và radius lớn hoạt động theo contract.
- Tọa độ biên latitude/longitude được xử lý đúng.

### 11.2. Test sort order

Với origin cố định, xác nhận khoảng cách tăng dần:

~~~java
List<Double> distances = hits.getSearchHits().stream()
        .map(hit -> (Number) hit.getSortValues().get(0))
        .map(Number::doubleValue)
        .toList();

for (int i = 1; i < distances.size(); i++) {
    assertThat(distances.get(i))
            .isGreaterThanOrEqualTo(distances.get(i - 1));
}
~~~

Kiểu sort value và đơn vị phải được xác nhận theo request/version. Nếu query có thêm sort field trước geo distance, index sort value tương ứng cũng thay đổi.

### 11.3. Test coordinate order

Tạo test cho một vị trí có latitude và longitude khác biệt rõ, ví dụ một tọa độ tại Việt Nam. Kiểm tra giá trị đã serialize vào `_source` và query origin. Không chỉ kiểm tra object Java trước khi lưu.

Có thể đọc lại document:

~~~http
GET /places/_doc/place-01
~~~

Xác nhận `_source.location.lat` và `_source.location.lon` đúng giá trị mong đợi.

## 12. Hiệu năng và giới hạn truy vấn

Geo-distance query cần tính khoảng cách cho document ứng viên. Các biện pháp dưới đây giúp giữ query trong phạm vi hợp lý:

- Đặt radius tối đa theo nhu cầu sản phẩm.
- Thêm category/status/tenant filter khi phù hợp.
- Giới hạn page size.
- Tránh query radius cực lớn nếu UI chỉ hiển thị địa điểm gần.
- Chỉ trả các field cần thiết bằng source filtering.
- Theo dõi latency p95/p99 và số hit.
- Đảm bảo `location` được mapping là `geo_point`.
- Dùng pagination phù hợp với độ sâu kết quả.

Ví dụ chỉ lấy field cần thiết:

~~~http
GET /places/_search
Content-Type: application/json

{
  "_source": ["name", "category", "location"],
  "size": 20,
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
        "unit": "km"
      }
    }
  ]
}
~~~

Không cache kết quả chỉ bằng category và radius. Origin phải nằm trong cache key; nếu không, người dùng ở vị trí khác có thể nhận danh sách địa điểm của người trước. Cần làm tròn tọa độ trong cache key nếu muốn gom các vị trí gần nhau, nhưng việc làm tròn làm thay đổi độ chính xác và cần có chính sách rõ ràng.

### 12.1. Chọn radius hợp lý

Radius lớn hơn tạo nhiều document phù hợp và có thể làm query tốn hơn. Hãy đặt giới hạn theo nghiệp vụ:

- Tìm cửa hàng quanh người dùng: vài kilomet đến vài chục kilomet.
- Tìm bệnh viện trong vùng đô thị: có thể dùng radius rộng hơn.
- Tìm trạm sạc dọc tuyến đường: radius có thể phụ thuộc loại phương tiện và ngữ cảnh.
- Phân tích địa lý toàn quốc: có thể cần geo aggregation hoặc quy trình phân tích riêng.

Các mức trên là ví dụ use case, không phải ngưỡng kỹ thuật cứng.

### 12.2. Filter trước khi sort

Query filter giúp thu hẹp tập document. Sort theo khoảng cách sau đó xếp các hit phù hợp. Hãy đặt điều kiện nghiệp vụ trong `bool.filter` để Elasticsearch không phải tính relevance score không cần thiết cho những điều kiện exact-match.

Geo-distance sort vẫn cần tính khoảng cách cho các hit được xét để sắp xếp. Nếu radius rộng và số hit lớn, cân nhắc page size, shard distribution và yêu cầu UI.

## 13. Các lựa chọn khác: geohash, grid và geo aggregation

Nếu cần nhóm địa điểm theo khu vực hoặc tạo heatmap, `geo_point` còn hỗ trợ các aggregation địa lý như geotile grid, geohash grid hoặc geo bounds tùy use case.

Đó là bài toán khác với “tìm top địa điểm gần nhất”:

- Geo-distance query lọc document trong bán kính.
- Geo-distance sort xếp document theo khoảng cách tới origin.
- Geo-distance aggregation có thể tính khoảng cách theo bucket trong những trường hợp được hỗ trợ.
- Geotile/geohash grid gom document vào ô địa lý để hiển thị bản đồ hoặc heatmap.

Không dùng aggregation thay cho geo-distance sort nếu yêu cầu là trả từng địa điểm theo thứ tự gần nhất.

## 14. Checklist triển khai trong Spring Data Elasticsearch

1. Field tọa độ có mapping `geo_point` chưa?
2. Entity có `@GeoPointField` hoặc mapping tương đương chưa?
3. Java `GeoPoint` có được tạo theo `(latitude, longitude)` không?
4. Dữ liệu GeoJSON `[longitude, latitude]` có được chuyển đổi đúng không?
5. Input latitude/longitude đã được validate?
6. Query có `geo_distance` với radius và origin?
7. Các điều kiện nghiệp vụ có được đặt trong `bool.filter`?
8. Sort có `_geo_distance` và `order: asc`?
9. Unit có thống nhất giữa query, sort và API response?
10. Có tie-breaker ổn định khi phân trang?
11. Có kiểm tra mapping của mọi index phía sau alias?
12. Có xử lý document thiếu tọa độ?
13. Có test điểm trong/ngoài radius?
14. Có test thứ tự khoảng cách?
15. Cache key có bao gồm origin?
16. Có giới hạn radius, page size và query latency?

## 15. Tài liệu tham khảo

- [Spring Data Elasticsearch — GeoPoint and mapping annotations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch — NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Elasticsearch — Geo-point field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/geo-point.html)
- [Elasticsearch — Geo-distance query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-geo-distance-query.html)
- [Elasticsearch — Geo-distance sort](https://www.elastic.co/guide/en/elasticsearch/reference/current/sort-search-results.html#geo-sorting)
- [Elasticsearch — Search results sorting](https://www.elastic.co/guide/en/elasticsearch/reference/current/sort-search-results.html)
- [Elasticsearch — Geo-shape field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/geo-shape.html)
- [Elasticsearch — Geotile grid aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket-geotilegrid-aggregation.html)

Để tìm địa điểm trong một bán kính và xếp từ gần đến xa, cần mapping `location` thành `geo_point`, dùng `geo_distance` trong query để giới hạn bán kính và `_geo_distance` trong sort để xác định thứ tự. Spring Data Elasticsearch có thể khai báo tọa độ bằng `@GeoPointField`, tạo query bằng `NativeQuery` và dùng `GeoDistanceOrder` cho sort. Hãy đặc biệt kiểm soát thứ tự latitude/longitude, đơn vị khoảng cách, filter nghiệp vụ và pagination để kết quả đúng với vị trí người dùng.

