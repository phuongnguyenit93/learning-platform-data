# Phân biệt geo_point và geo_shape

Elasticsearch hỗ trợ dữ liệu địa lý để tìm địa điểm gần một tọa độ, lọc document trong bán kính, kiểm tra một vị trí có nằm trong khu vực phục vụ hay không và tìm các vùng địa lý giao nhau. Hai kiểu dữ liệu chính cho mục đích này là `geo_point` và `geo_shape`.

`geo_point` biểu diễn một vị trí điểm bằng vĩ độ và kinh độ. Nó phù hợp với cửa hàng, người dùng, trạm giao hàng, thiết bị hoặc bất kỳ đối tượng nào được mô tả bằng một tọa độ.

`geo_shape` biểu diễn hình học địa lý phức tạp hơn như điểm, đường, đa giác và tập hợp hình học. Nó phù hợp với ranh giới quận/huyện, vùng giao hàng, khu vực cấm, tuyến đường hoặc phạm vi phủ sóng.

Hai kiểu dữ liệu có thể xuất hiện trong cùng một document. Ví dụ, một cửa hàng có `location` là `geo_point` để tìm cửa hàng gần người dùng và `service_area` là `geo_shape` để mô tả khu vực mà cửa hàng nhận giao hàng.

## 1. Khác biệt cốt lõi

| Tiêu chí | `geo_point` | `geo_shape` |
|---|---|---|
| Dữ liệu chính | Một tọa độ điểm; field cũng có thể chứa nhiều điểm | Hình học như point, line, polygon, multipolygon và geometry collection |
| Mục đích phổ biến | Tìm gần, lọc bán kính, sắp xếp theo khoảng cách | Kiểm tra giao nhau, chứa, nằm trong hoặc tách rời giữa các hình |
| Truy vấn tiêu biểu | `geo_distance`, `geo_bounding_box` | `geo_shape` với relation |
| Sort theo khoảng cách | Hỗ trợ `_geo_distance` | Không dùng như một điểm đơn giản; cần xác định điểm đại diện hoặc mô hình khác |
| Biểu diễn | Object lat/lon, chuỗi, mảng tọa độ hoặc geohash theo định dạng được hỗ trợ | GeoJSON, WKT hoặc định dạng hình học được Elasticsearch hỗ trợ |
| Ví dụ nghiệp vụ | Tọa độ của nhà hàng | Đa giác ranh giới khu vực giao hàng |

Có thể nhớ:

- Dùng `geo_point` khi câu hỏi chính là “địa điểm này ở đâu?” hoặc “điểm nào gần vị trí này?”.
- Dùng `geo_shape` khi câu hỏi chính là “hình học này giao, chứa hoặc nằm trong khu vực nào?”.

`geo_shape` cũng có thể lưu một geometry kiểu Point, nhưng nếu dữ liệu chỉ là tọa độ để tìm gần và sort khoảng cách, `geo_point` thường đơn giản và phù hợp hơn.

## 2. Tọa độ địa lý: latitude và longitude

Trước khi khai báo mapping, cần thống nhất thứ tự tọa độ. Một tọa độ địa lý có hai thành phần:

- **Latitude (vĩ độ):** vị trí Bắc/Nam, thường nằm trong khoảng -90 đến 90.
- **Longitude (kinh độ):** vị trí Đông/Tây, thường nằm trong khoảng -180 đến 180.

Thứ tự biểu diễn phụ thuộc định dạng:

| Định dạng | Thứ tự |
|---|---|
| GeoJSON coordinates | [longitude, latitude] |
| Mảng `geo_point` của Elasticsearch | [longitude, latitude] |
| Object `geo_point` | `{"lat": latitude, "lon": longitude}` |
| Chuỗi `geo_point` | `"latitude,longitude"` |
| WKT Point | `POINT (longitude latitude)` |

Ví dụ cùng một vị trí:

~~~json
{
  "lat": 10.78,
  "lon": 106.69
}
~~~

Biểu diễn dạng mảng:

~~~json
[106.69, 10.78]
~~~

Biểu diễn GeoJSON/WKT:

~~~json
{
  "type": "Point",
  "coordinates": [106.69, 10.78]
}
~~~

~~~text
POINT (106.69 10.78)
~~~

Lỗi đảo latitude và longitude là lỗi phổ biến. Một giá trị có thể vẫn nằm trong miền số hợp lệ nhưng lại trỏ đến một vị trí địa lý hoàn toàn khác. Hãy chuẩn hóa thứ tự tại biên hệ thống và viết test cho quá trình chuyển đổi.

## 3. Khai báo field geo_point

Mapping `geo_point` cho biết field chứa tọa độ điểm:

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
      "location": {
        "type": "geo_point"
      }
    }
  }
}
~~~

Document mẫu:

~~~http
PUT /places/_doc/place-001
Content-Type: application/json

{
  "name": "Central Coffee",
  "category": "cafe",
  "location": {
    "lat": 10.78,
    "lon": 106.69
  }
}
~~~

Elasticsearch cũng chấp nhận một số cách biểu diễn `geo_point` khác như chuỗi `"lat,lon"`, mảng `[lon, lat]` và geohash. Dùng object có `lat` và `lon` thường dễ đọc, ít gây nhầm lẫn hơn khi trao đổi dữ liệu giữa các service.

### 3.1. Một document có nhiều điểm

Một field `geo_point` có thể chứa nhiều tọa độ. Ví dụ một tài xế có thể gửi nhiều vị trí hoặc một đối tượng có một số điểm đo:

~~~json
{
  "driverId": "driver-42",
  "positions": [
    {"lat": 10.78, "lon": 106.69},
    {"lat": 10.79, "lon": 106.70}
  ]
}
~~~

Khi truy vấn field nhiều giá trị, cần hiểu semantics của query và sort: document có thể khớp nếu một trong các điểm thỏa điều kiện; với sort theo khoảng cách, cần chọn mode phù hợp hoặc dùng hành vi mặc định đã được xác định trong API. Nếu ứng dụng cần vị trí hiện tại duy nhất, nên lưu rõ một field đại diện thay vì để mảng lịch sử làm nguồn sort.

## 4. Truy vấn geo_point

### 4.1. geo_distance: tìm trong bán kính

`geo_distance` lọc các document có điểm nằm trong khoảng cách tối đa từ một origin:

~~~http
GET /places/_search
Content-Type: application/json

{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "location": {
        "lat": 10.78,
        "lon": 106.69
      }
    }
  }
}
~~~

Ví dụ tìm các địa điểm trong bán kính 5 km tính từ tọa độ đã cho. Khoảng cách có thể dùng các đơn vị được Elasticsearch hỗ trợ như m, km, mi hoặc yd.

Có thể kết hợp với bool filter để lọc thêm loại địa điểm:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "cafe"
          }
        },
        {
          "geo_distance": {
            "distance": "5km",
            "location": {
              "lat": 10.78,
              "lon": 106.69
            }
          }
        }
      ]
    }
  }
}
~~~

Điều kiện category và khoảng cách đều là filter bắt buộc. Không cần tính relevance score nếu mục tiêu chỉ là tìm tất cả quán cà phê trong bán kính.

### 4.2. geo_bounding_box: lọc theo hộp tọa độ

`geo_bounding_box` lọc các điểm nằm trong hình chữ nhật được xác định bởi hai góc:

~~~json
{
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.82,
          "lon": 106.64
        },
        "bottom_right": {
          "lat": 10.72,
          "lon": 106.75
        }
      }
    }
  }
}
~~~

Bounding box phù hợp với thao tác bản đồ như tìm các điểm trong vùng viewport hiện tại. Nó lọc theo hình chữ nhật tọa độ, không phải bán kính hình tròn.

### 4.3. Sort theo khoảng cách

Nếu muốn địa điểm gần nhất đứng trước, dùng `_geo_distance`:

~~~json
{
  "sort": [
    {
      "_geo_distance": {
        "location": {
          "lat": 10.78,
          "lon": 106.69
        },
        "order": "asc",
        "unit": "km",
        "distance_type": "arc"
      }
    }
  ]
}
~~~

Sort này sắp xếp theo khoảng cách từ origin đến tọa độ được lập chỉ mục. `arc` tính khoảng cách theo cung trên bề mặt Trái Đất; cần chọn cách tính và độ chính xác phù hợp với bài toán.

Có thể kết hợp relevance với khoảng cách bằng `function_score` hoặc distance feature nếu muốn nội dung phù hợp vẫn có trọng số. Sort thuần theo `_geo_distance` sẽ ưu tiên khoảng cách theo thứ tự chính, có thể khiến kết quả gần nhưng không liên quan đứng trước kết quả phù hợp hơn.

## 5. Khai báo field geo_shape

`geo_shape` dùng để lưu hình học thay vì chỉ một tọa độ. Các hình thường gặp:

- Point: một điểm.
- LineString: đường gồm nhiều tọa độ.
- Polygon: vùng có ranh giới khép kín.
- MultiPoint, MultiLineString, MultiPolygon: tập hợp nhiều hình cùng loại.
- GeometryCollection: tập hợp các geometry khác loại.
- Envelope: hình chữ nhật theo hai góc.

Ví dụ mapping:

~~~http
PUT /service-areas
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "name": {
        "type": "keyword"
      },
      "service_area": {
        "type": "geo_shape"
      }
    }
  }
}
~~~

Document chứa polygon theo GeoJSON:

~~~http
PUT /service-areas/_doc/area-001
Content-Type: application/json

{
  "name": "District Service Zone",
  "service_area": {
    "type": "polygon",
    "coordinates": [
      [
        [106.65, 10.75],
        [106.72, 10.75],
        [106.72, 10.81],
        [106.65, 10.81],
        [106.65, 10.75]
      ]
    ]
  }
}
~~~

Trong GeoJSON, mỗi tọa độ luôn có thứ tự longitude rồi latitude. Vòng ngoài của polygon phải khép kín: tọa độ cuối trùng tọa độ đầu. Polygon có lỗ có thêm các vòng tọa độ bên trong.

### 5.1. Polygon có lỗ

Một polygon có thể chứa một vòng ngoài và một hoặc nhiều vòng trong biểu diễn vùng bị khoét:

~~~json
{
  "type": "polygon",
  "coordinates": [
    [
      [106.60, 10.70],
      [106.80, 10.70],
      [106.80, 10.90],
      [106.60, 10.90],
      [106.60, 10.70]
    ],
    [
      [106.68, 10.78],
      [106.72, 10.78],
      [106.72, 10.82],
      [106.68, 10.82],
      [106.68, 10.78]
    ]
  ]
}
~~~

Vòng đầu là ranh giới ngoài; các vòng tiếp theo biểu diễn lỗ. Khi tạo polygon, cần bảo đảm tọa độ hợp lệ, vòng khép kín và hướng vòng theo quy tắc orientation mà Elasticsearch đang áp dụng. Với dữ liệu GIS được tạo từ công cụ bên ngoài, hãy xác minh orientation và hình học trước khi index.

### 5.2. LineString và MultiPolygon

Một tuyến đường có thể được lưu bằng LineString:

~~~json
{
  "type": "linestring",
  "coordinates": [
    [106.65, 10.75],
    [106.68, 10.77],
    [106.72, 10.80]
  ]
}
~~~

Một khu vực gồm nhiều vùng tách rời có thể dùng MultiPolygon:

~~~json
{
  "type": "multipolygon",
  "coordinates": [
    [
      [
        [106.60, 10.70],
        [106.65, 10.70],
        [106.65, 10.75],
        [106.60, 10.75],
        [106.60, 10.70]
      ]
    ],
    [
      [
        [106.75, 10.80],
        [106.80, 10.80],
        [106.80, 10.85],
        [106.75, 10.85],
        [106.75, 10.80]
      ]
    ]
  ]
}
~~~

MultiPolygon hữu ích khi một vùng phục vụ gồm nhiều khu vực địa lý không liền nhau.

## 6. Truy vấn geo_shape và relation

`geo_shape` query so sánh hình học được lưu trong document với một hình học truy vấn. Tham số `relation` xác định quan hệ không gian cần thỏa.

Các quan hệ thường dùng:

| Relation | Ý nghĩa tổng quát |
|---|---|
| `intersects` | Hai hình có phần giao nhau |
| `within` | Hình được index nằm trong hình truy vấn |
| `contains` | Hình được index chứa hình truy vấn |
| `disjoint` | Hai hình không giao nhau |

Hướng diễn giải luôn cần xét cả hình trong document và hình trong query. Ví dụ, nếu field `service_area` lưu polygon khu vực giao hàng còn query gửi một Point của khách hàng, `contains` hỏi polygon trong document có chứa điểm truy vấn hay không.

### 6.1. Kiểm tra điểm khách hàng nằm trong polygon

~~~http
GET /service-areas/_search
Content-Type: application/json

{
  "query": {
    "geo_shape": {
      "service_area": {
        "shape": {
          "type": "point",
          "coordinates": [106.69, 10.78]
        },
        "relation": "contains"
      }
    }
  }
}
~~~

Ở đây:

- Document chứa polygon service_area.
- Query gửi một điểm khách hàng.
- `contains` chọn những polygon trong document có chứa điểm đó.

Nếu mục tiêu là tìm polygon có giao với một polygon yêu cầu, dùng relation `intersects`:

~~~http
GET /service-areas/_search
Content-Type: application/json

{
  "query": {
    "geo_shape": {
      "service_area": {
        "shape": {
          "type": "polygon",
          "coordinates": [
            [
              [106.68, 10.76],
              [106.73, 10.76],
              [106.73, 10.82],
              [106.68, 10.82],
              [106.68, 10.76]
            ]
          ]
        },
        "relation": "intersects"
      }
    }
  }
}
~~~

Kết quả gồm các khu vực dịch vụ có phần giao với polygon được gửi trong query.

### 6.2. Phân biệt within và contains

Hai relation này dễ bị đảo:

- Nếu polygon trong document nằm trọn bên trong polygon truy vấn, dùng `within`.
- Nếu polygon trong document bao trùm hình truy vấn, dùng `contains`.

Với một điểm query và một polygon trong document:

- `contains` hỏi polygon document có chứa điểm query không.
- `within` hỏi polygon document có nằm trong hình query không; với query chỉ là một điểm, điều kiện này không biểu diễn bài toán “điểm nằm trong vùng”.

Hãy vẽ rõ hai hình và ghi nhãn “indexed shape” và “query shape” trước khi chọn relation. Test với một điểm nằm trong, một điểm nằm ngoài và một điểm nằm sát ranh giới để xác nhận semantics mong muốn.

### 6.3. disjoint

`disjoint` chọn các hình không có phần giao nhau với hình truy vấn. Ví dụ tìm các khu vực dịch vụ hoàn toàn tách rời một vùng cấm. Khi dùng relation này, cần kiểm tra xem việc trả về cả các khu vực ở rất xa có đúng với nghiệp vụ hay không; đôi khi nên kết hợp thêm điều kiện thuộc tỉnh/thành hoặc bounding box để giới hạn phạm vi.

## 7. So sánh truy vấn geo_point và geo_shape

| Câu hỏi nghiệp vụ | Field phù hợp | Query hoặc thao tác |
|---|---|---|
| Cửa hàng nào trong bán kính 5 km? | `geo_point` | `geo_distance` |
| Điểm nào nằm trong viewport bản đồ? | `geo_point` | `geo_bounding_box` |
| Cửa hàng nào gần nhất? | `geo_point` | `_geo_distance` sort |
| Khách hàng có nằm trong vùng giao hàng? | `geo_shape` polygon + point query | `geo_shape` relation `contains` |
| Hai vùng giao hàng có chồng lấn? | `geo_shape` | relation `intersects` |
| Tuyến đường có giao với khu vực cấm? | `geo_shape` | relation `intersects` |
| Khu vực nào hoàn toàn nằm trong vùng quy hoạch? | `geo_shape` | relation `within` |
| Một vùng có bị tách rời khỏi khu vực truy vấn? | `geo_shape` | relation `disjoint` |

Nếu use case cần cả khoảng cách gần nhất lẫn kiểm tra ranh giới vùng, có thể lưu cả `geo_point` và `geo_shape` trong cùng document. Hai field phục vụ hai câu hỏi khác nhau, không cần ép một kiểu dữ liệu gánh mọi nhu cầu.

## 8. Dữ liệu địa lý trong Spring Data Elasticsearch

Spring Data Elasticsearch hỗ trợ ánh xạ field địa lý thông qua annotation và các kiểu dữ liệu địa lý. Cách dùng cụ thể phụ thuộc release train Spring Data và Elasticsearch Java Client của dự án.

### 8.1. Entity dùng geo_point

Ví dụ entity địa điểm:

~~~java
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

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @GeoPointField
    private GeoPoint location;

    // constructors, getters and setters
}
~~~

`GeoPoint` của Spring Data Elasticsearch biểu diễn một điểm với latitude và longitude. Ví dụ tạo điểm:

~~~java
GeoPoint location = new GeoPoint(10.78, 106.69);
~~~

Trong constructor này, truyền latitude trước rồi longitude. Khi serialize thành GeoJSON coordinates hoặc mảng tọa độ Elasticsearch, thứ tự trên wire là longitude rồi latitude. Đây là hai quy ước khác nhau cần được converter xử lý đúng.

Có thể dùng `@Field(type = FieldType.GeoPoint)` nếu phiên bản và mapping metadata của dự án hỗ trợ cách khai báo đó; `@GeoPointField` là annotation chuyên biệt thường dùng cho thuộc tính GeoPoint.

### 8.2. Entity dùng geo_shape

Với geometry phức tạp, field cần được mapping là `geo_shape`. Ví dụ một model giữ GeoJSON dạng map:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

public class ServiceArea {

    @Field(type = FieldType.GeoShape)
    private Map<String, Object> serviceArea;
}
~~~

Giá trị map phải được serialize thành cấu trúc geometry mà Elasticsearch hiểu, ví dụ:

~~~java
Map<String, Object> polygon = Map.of(
        "type", "polygon",
        "coordinates", List.of(
                List.of(
                        List.of(106.65, 10.75),
                        List.of(106.72, 10.75),
                        List.of(106.72, 10.81),
                        List.of(106.65, 10.81),
                        List.of(106.65, 10.75)
                )
        )
);
~~~

Đây là cách biểu diễn dữ liệu GeoJSON ở mức cấu trúc. Với dự án thực tế, có thể dùng các kiểu GeoJSON chuyên biệt được release train hỗ trợ hoặc một value object riêng kèm converter. Hãy kiểm tra mapping và JSON được gửi thực tế; việc khai báo `FieldType.GeoShape` chỉ xác định kiểu mapping, không tự bảo đảm mọi Java geometry tùy ý được serialize đúng.

### 8.3. Tạo mapping qua Spring Data

Nếu index được tạo từ entity metadata, có thể lấy `IndexOperations`:

~~~java
IndexOperations indexOperations =
        operations.indexOps(Place.class);

if (!indexOperations.exists()) {
    indexOperations.createWithMapping();
}
~~~

Với index production, mapping địa lý nên được quản lý qua index template hoặc migration có kiểm soát. Sau khi tạo index, đọc mapping thực tế để xác nhận field là `geo_point` hoặc `geo_shape` đúng như yêu cầu:

~~~http
GET /places/_mapping
~~~

Thay đổi một field từ `geo_point` sang `geo_shape` hoặc ngược lại không phải thay đổi kiểu đơn giản có thể thực hiện trực tiếp trên mapping đang tồn tại. Thường cần tạo index mới với mapping đúng, chuyển đổi/reindex dữ liệu và chuyển alias.

## 9. Truy vấn geo_distance qua Spring Data

Khi cần truy vấn theo khoảng cách, có thể dùng `@Query` với DSL cố định hoặc `NativeQuery` nếu origin và radius thay đổi theo request.

Ví dụ repository với query cố định về cấu trúc:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface PlaceRepository
        extends ElasticsearchRepository<Place, String> {

    @Query("""
        {
          "geo_distance": {
            "distance": "?0",
            "location": {
              "lat": ?1,
              "lon": ?2
            }
          }
        }
        """)
    List<Place> findWithinDistance(
            String distance,
            double latitude,
            double longitude
    );
}
~~~

Ví dụ này minh họa positional binding cho khoảng cách và tọa độ; cần xác nhận cách binding số và chuỗi của phiên bản Spring Data Elasticsearch đang dùng. Với query động phức tạp hoặc cần kết hợp nhiều điều kiện, `NativeQuery` và Elasticsearch Java Client thường dễ kiểm soát hơn.

Không nên nối chuỗi JSON từ dữ liệu tọa độ người dùng. Hãy validate latitude/longitude, giới hạn distance theo nghiệp vụ và truyền giá trị qua API binding.

## 10. Truy vấn geo_shape trong ứng dụng

Một truy vấn kiểm tra vị trí khách hàng thuộc vùng giao hàng có thể được biểu diễn bằng JSON DSL:

~~~java
String queryJson = """
    {
      "geo_shape": {
        "service_area": {
          "shape": {
            "type": "point",
            "coordinates": [106.69, 10.78]
          },
          "relation": "contains"
        }
      }
    }
    """;
~~~

Trong ứng dụng Spring Data, có thể đặt DSL cố định trong `@Query`, hoặc xây dựng GeoShape query bằng Elasticsearch Java Client rồi truyền vào `NativeQuery`. Nếu vị trí thay đổi theo request, nên tạo query object từ các giá trị đã validate thay vì nối chuỗi JSON.

Khi dùng geometry được tạo từ thư viện GIS, cần chuyển đổi geometry sang định dạng mà Elasticsearch client hỗ trợ. Kiểm tra CRS (coordinate reference system) của nguồn dữ liệu: Elasticsearch geo fields làm việc với tọa độ địa lý WGS84 theo longitude/latitude. Nếu dữ liệu nguồn ở hệ tọa độ phẳng hoặc CRS khác, cần chuyển đổi trước khi index.

## 11. GeoJSON, WKT và chuẩn hóa dữ liệu

### 11.1. GeoJSON

GeoJSON là định dạng phổ biến để trao đổi geometry. Ví dụ Point:

~~~json
{
  "type": "Point",
  "coordinates": [106.69, 10.78]
}
~~~

Ví dụ LineString:

~~~json
{
  "type": "LineString",
  "coordinates": [
    [106.65, 10.75],
    [106.68, 10.77],
    [106.72, 10.80]
  ]
}
~~~

Ví dụ Polygon:

~~~json
{
  "type": "Polygon",
  "coordinates": [
    [
      [106.65, 10.75],
      [106.72, 10.75],
      [106.72, 10.81],
      [106.65, 10.81],
      [106.65, 10.75]
    ]
  ]
}
~~~

GeoJSON dùng tên geometry và mảng coordinates. Tọa độ trong mảng là longitude, latitude; không đảo thứ tự như object `geo_point` có tên thuộc tính.

### 11.2. WKT

Well-Known Text (WKT) biểu diễn geometry bằng chuỗi:

~~~text
POINT (106.69 10.78)
LINESTRING (106.65 10.75, 106.68 10.77, 106.72 10.80)
POLYGON ((106.65 10.75, 106.72 10.75, 106.72 10.81, 106.65 10.81, 106.65 10.75))
~~~

WKT dùng thứ tự X/Y, trong ngữ cảnh tọa độ địa lý là longitude/latitude. Hãy kiểm tra parser và định dạng được API Elasticsearch hoặc thư viện chuyển đổi hỗ trợ.

### 11.3. CRS và dữ liệu nguồn

Không phải mọi dữ liệu có hai con số đều là longitude/latitude. Một file GIS có thể dùng hệ tọa độ phẳng theo mét hoặc một CRS địa phương. Trước khi đưa vào Elasticsearch:

1. Xác định CRS nguồn.
2. Chuyển đổi sang WGS84 nếu cần.
3. Chuẩn hóa thứ tự longitude/latitude.
4. Kiểm tra miền giá trị.
5. Kiểm tra polygon khép kín và hình học hợp lệ.
6. Index thử một số geometry đại diện.
7. Chạy truy vấn không gian kiểm chứng vị trí và quan hệ.

Không chỉ dựa vào việc Elasticsearch chấp nhận document; một tọa độ sai CRS vẫn có thể được index nhưng cho kết quả địa lý sai.

## 12. Hiệu năng và chọn đúng kiểu dữ liệu

`geo_point` thường là lựa chọn gọn và hiệu quả cho tìm kiếm quanh điểm, bounding box, sort khoảng cách và aggregation khoảng cách.

`geo_shape` phù hợp với hình học phức tạp và quan hệ giữa các vùng. Việc lưu polygon có nhiều đỉnh hoặc geometry collection lớn đòi hỏi xử lý hình học và chỉ mục phức tạp hơn một điểm đơn giản.

Một số nguyên tắc:

- Không dùng polygon chỉ để lưu một tọa độ nếu không cần quan hệ hình học.
- Không dùng `geo_point` để mô tả ranh giới khu vực.
- Giảm số đỉnh không cần thiết của polygon nhưng vẫn giữ độ chính xác nghiệp vụ.
- Tránh gửi geometry rất lớn trong mọi request nếu có thể lưu và tham chiếu geometry đã index.
- Dùng filter khi chỉ cần kiểm tra điều kiện không gian, không cần score.
- Giới hạn bán kính hoặc vùng tìm kiếm theo nghiệp vụ để tránh query quá rộng.
- Kiểm tra mapping và query trên dữ liệu có kích thước tương đương production.

Không nên mặc định một truy vấn `geo_shape` luôn chậm hoặc `geo_point` luôn nhanh trong mọi workload. Hiệu năng phụ thuộc số lượng geometry, độ phức tạp hình học, số đỉnh, số shard và cách query.

## 13. Những lỗi thường gặp

### 13.1. Đảo latitude và longitude

Object `geo_point` dùng tên lat/lon, nhưng GeoJSON coordinates và mảng dùng longitude trước latitude. WKT cũng dùng X rồi Y. Hãy kiểm tra từng định dạng riêng.

### 13.2. Dùng geo_point cho vùng

Một điểm đại diện không thể mô tả ranh giới đa giác hoặc tuyến đường. Nếu nghiệp vụ cần kiểm tra khách có nằm trong vùng giao hàng, lưu `geo_shape`.

### 13.3. Dùng geo_shape cho truy vấn gần nhất đơn giản

Nếu chỉ cần cửa hàng gần người dùng và sort theo khoảng cách, `geo_point` cùng `geo_distance`/`_geo_distance` đơn giản hơn.

### 13.4. Chọn sai relation

`contains` và `within` được hiểu theo quan hệ giữa hình được index và hình truy vấn. Hãy xác định hình nào là polygon lưu trong document, hình nào là geometry query rồi mới chọn.

### 13.5. Polygon không khép kín hoặc sai orientation

Vòng polygon phải đóng và tuân theo quy tắc orientation. Dữ liệu GIS không chuẩn có thể bị từ chối hoặc diễn giải không như mong đợi.

### 13.6. Bỏ qua CRS

Tọa độ từ hệ quy chiếu khác WGS84 không thể được xem trực tiếp như longitude/latitude. Cần chuyển đổi trước khi index.

### 13.7. Mapping không đồng nhất giữa các index

Alias nhiều index cần field địa lý có kiểu tương thích. Không nên để một index cũ dùng object thường trong khi index mới dùng `geo_shape`.

### 13.8. Chuyển kiểu field trực tiếp

Không thể tùy ý đổi `geo_point` thành `geo_shape` trên index đã có dữ liệu. Tạo index mới, reindex/chuyển đổi geometry và chuyển alias theo quy trình migration.

## 14. Kiểm thử dữ liệu địa lý

Với `geo_point`, tạo test cho:

- Một điểm nằm trong bán kính.
- Một điểm nằm ngoài bán kính.
- Một điểm đúng gần ngưỡng khoảng cách.
- Một điểm trong và ngoài bounding box.
- Sort gần đến xa.
- Tọa độ thiếu hoặc sai miền.
- Trường hợp nhiều điểm trong cùng document nếu có.

Với `geo_shape`, tạo test cho:

- Điểm nằm bên trong polygon.
- Điểm nằm ngoài polygon.
- Điểm trên hoặc sát biên.
- Polygon giao một phần với polygon truy vấn.
- Polygon nằm hoàn toàn trong polygon truy vấn.
- Polygon chứa polygon truy vấn.
- Hai hình không giao nhau.
- Polygon có lỗ và MultiPolygon.
- Geometry không hợp lệ hoặc sai thứ tự tọa độ.

Test nên dùng dữ liệu có tọa độ và kết quả mong đợi được xác định trước. Với truy vấn khoảng cách, đừng chỉ kiểm tra có kết quả; hãy xác nhận khoảng cách hoặc thứ tự phù hợp với kỳ vọng.

Trong integration test, dùng phiên bản Elasticsearch tương thích với Spring Data Elasticsearch của dự án. Kiểm tra cả mapping được tạo, document JSON sau serialize và kết quả truy vấn trên cluster thật.

## 15. Quy trình chọn geo_point hay geo_shape

Khi thiết kế một field địa lý:

1. Xác định dữ liệu biểu diễn một vị trí hay một hình học.
2. Nếu chỉ là vị trí, chọn `geo_point`.
3. Nếu là đường, vùng hoặc geometry phức tạp, chọn `geo_shape`.
4. Chuẩn hóa CRS và thứ tự longitude/latitude.
5. Thiết kế mapping và kiểu Java tương ứng.
6. Kiểm tra JSON được Spring Data serialize.
7. Chọn query theo câu hỏi nghiệp vụ: distance, bounding box hay shape relation.
8. Kết hợp bool filter với điều kiện nghiệp vụ khác.
9. Kiểm thử điểm nằm trong/ngoài và hình giao/không giao.
10. Nếu thay mapping của index hiện tại, tạo index mới và migration dữ liệu có kiểm soát.

Ví dụ quyết định:

| Dữ liệu | Kiểu nên cân nhắc | Lý do |
|---|---|---|
| Tọa độ cửa hàng | `geo_point` | Tìm gần và sort khoảng cách |
| Vị trí GPS mới nhất của xe | `geo_point` | Một vị trí đại diện |
| Ranh giới phường/quận | `geo_shape` | Polygon |
| Tuyến đường giao hàng | `geo_shape` | LineString |
| Nhiều vùng phục vụ tách rời | `geo_shape` | MultiPolygon |
| Điểm khách hàng và vùng giao hàng | Cả hai | Điểm để xác định vị trí, polygon để kiểm tra vùng chứa |

## 16. Kết luận

`geo_point` biểu diễn tọa độ điểm và phù hợp với tìm kiếm gần, lọc bán kính, bounding box và sort theo khoảng cách. `geo_shape` biểu diễn hình học như đường và vùng, phù hợp với truy vấn quan hệ không gian như intersects, within, contains và disjoint.

Thứ tự tọa độ phải được xử lý chính xác: object `geo_point` dùng `lat`/`lon`, trong khi GeoJSON coordinates, mảng Elasticsearch và WKT dùng longitude trước latitude. Với polygon, cần bảo đảm vòng khép kín, orientation và CRS phù hợp.

Trong Spring Data Elasticsearch, `@GeoPointField` và `GeoPoint` là cách phổ biến để ánh xạ điểm. Với shape, dùng mapping `geo_shape` và một biểu diễn geometry được phiên bản dự án hỗ trợ, rồi xác minh JSON thực tế. Chọn kiểu dữ liệu theo câu hỏi không gian mà ứng dụng cần trả lời; khi cần cả vị trí và ranh giới, có thể lưu cả `geo_point` lẫn `geo_shape` trong cùng document.
