# Bounding box và lọc theo vùng bản đồ

Khi người dùng di chuyển hoặc phóng to bản đồ, ứng dụng thường cần lấy các địa điểm nằm trong phần bản đồ đang hiển thị. Vùng hiển thị đó có thể được mô tả bằng một hình chữ nhật địa lý gọi là **bounding box**. Elasticsearch hỗ trợ truy vấn **geo_bounding_box** để tìm các tài liệu có tọa độ nằm trong hình chữ nhật này.

Trong Spring Data Elasticsearch, dữ liệu vị trí thường được ánh xạ vào trường **geo_point**. Ứng dụng có thể xây dựng điều kiện bounding box bằng Query DSL rồi thực thi qua **ElasticsearchOperations**. Khi kết hợp với điều kiện nghiệp vụ như trạng thái, loại địa điểm hoặc quyền truy cập, nên đặt các điều kiện vào **bool.filter** để lọc kết quả mà không tính relevance score cho từng điều kiện.

Bài này sử dụng index **places**, trong đó mỗi tài liệu có tên địa điểm, loại, trạng thái và tọa độ. Nội dung tập trung vào cách biểu diễn tọa độ, cấu hình geo_point, xây dựng bounding box từ viewport của bản đồ, đọc kết quả và xử lý các trường hợp biên như tọa độ sai hoặc vùng bản đồ đi qua kinh tuyến 180 độ.

## 1. Bounding box là gì?

**Bounding box** là hình chữ nhật được xác định bởi hai góc đối diện:

- **Top-left**: góc phía tây bắc, có vĩ độ lớn hơn và thường có kinh độ nhỏ hơn.
- **Bottom-right**: góc phía đông nam, có vĩ độ nhỏ hơn và thường có kinh độ lớn hơn.

Ví dụ, một vùng bản đồ bao quanh trung tâm thành phố có thể được mô tả bởi:

- Top-left: latitude 10.82, longitude 106.65.
- Bottom-right: latitude 10.75, longitude 106.72.

Sơ đồ khái niệm:

~~~text
          West / Tây                 East / Đông
              |                          |
North / Bắc   +--------------------------+  Top-left
              |                          |
              |      Vùng bản đồ         |
              |      cần tìm             |
              |                          |
South / Nam   +--------------------------+  Bottom-right
~~~

Mọi điểm có tọa độ nằm trong hình chữ nhật này đều có thể được trả về. Bounding box thường được lấy từ viewport của bản đồ, tức phần địa lý đang nhìn thấy trên màn hình.

Bounding box là hình chữ nhật theo vĩ độ và kinh độ. Nó không phải một hình tròn có bán kính cố định, cũng không phải ranh giới hành chính. Vì vậy:

- Dùng bounding box khi muốn lấy các điểm trong vùng bản đồ đang hiển thị.
- Dùng geo_distance khi muốn tìm các điểm trong một bán kính tính từ tâm.
- Dùng geo_shape khi cần kiểm tra quan hệ với polygon, đường hoặc hình học địa lý phức tạp.

## 2. geo_point và thứ tự tọa độ

Elasticsearch dùng kiểu **geo_point** để lưu một vị trí gồm vĩ độ và kinh độ.

- **Latitude (lat)**: vĩ độ, nằm trong khoảng -90 đến 90.
- **Longitude (lon)**: kinh độ, nằm trong khoảng -180 đến 180.

Ví dụ tọa độ của một địa điểm:

~~~json
{
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
~~~

Cách biểu diễn object với hai thuộc tính lat và lon giúp người đọc phân biệt rõ thứ tự. Elasticsearch cũng chấp nhận một số dạng khác cho geo_point, nhưng thứ tự tọa độ phụ thuộc định dạng.

| Định dạng | Ví dụ | Thứ tự |
|---|---|---|
| Object | {"lat": 10.7769, "lon": 106.7009} | Ghi rõ lat và lon |
| String | "10.7769,106.7009" | Latitude, longitude |
| Array | [106.7009, 10.7769] | Longitude, latitude |
| GeoJSON point | {"type":"Point","coordinates":[106.7009,10.7769]} | Longitude, latitude |

Đây là nguồn lỗi thường gặp khi lấy dữ liệu từ thư viện bản đồ. Nhiều thư viện JavaScript biểu diễn tọa độ theo thứ tự **[longitude, latitude]**, trong khi một số API Java nhận hai tham số theo thứ tự **latitude, longitude**.

Khi chuyển dữ liệu giữa frontend, backend và Elasticsearch, hãy xác định rõ quy ước ở từng ranh giới. Không đổi thứ tự tọa độ theo cảm tính.

## 3. Khai báo trường geo_point trong Spring Data Elasticsearch

Một entity địa điểm có thể dùng annotation **@GeoPointField** để ánh xạ thuộc tính vị trí thành geo_point.

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

    @Field(type = FieldType.Keyword)
    private String status;

    @GeoPointField
    private GeoPoint location;

    public Place() {
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getCategory() {
        return category;
    }

    public void setCategory(String category) {
        this.category = category;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public GeoPoint getLocation() {
        return location;
    }

    public void setLocation(GeoPoint location) {
        this.location = location;
    }
}
~~~

Trong ví dụ:

- **@Document(indexName = "places")** liên kết entity với index places.
- **@Id** đánh dấu ID tài liệu.
- **@GeoPointField** xác định trường location là geo_point.
- **GeoPoint** biểu diễn tọa độ trong Java.
- category và status là keyword vì thường được dùng để lọc chính xác.

Lớp GeoPoint của Spring Data Elasticsearch có các giá trị latitude và longitude. Khi khởi tạo, hãy truyền đúng thứ tự mà constructor của phiên bản thư viện yêu cầu; API thông dụng nhận latitude trước, longitude sau.

Ví dụ:

~~~java
GeoPoint location = new GeoPoint(10.7769, 106.7009);
~~~

Trước khi triển khai, cần kiểm tra mapping thực tế của index. Annotation trong Java không tự thay đổi mapping của một index đã tồn tại. Nếu index cũ đang khai báo location thành text hoặc keyword, cần tạo mapping đúng bằng quy trình quản lý index và reindex dữ liệu khi cần.

Có thể kiểm tra mapping bằng API:

~~~http
GET /places/_mapping
~~~

Phần mapping mong đợi có dạng:

~~~json
{
  "properties": {
    "location": {
      "type": "geo_point"
    },
    "category": {
      "type": "keyword"
    },
    "status": {
      "type": "keyword"
    }
  }
}
~~~

Nếu trường location không phải geo_point, geo_bounding_box query sẽ không hoạt động như mong muốn.

## 4. Tạo bounding box từ viewport của bản đồ

Thư viện bản đồ thường cung cấp bounds của viewport khi người dùng kéo hoặc zoom bản đồ. Bounds này thường gồm bốn giá trị:

- North: vĩ độ phía bắc.
- South: vĩ độ phía nam.
- East: kinh độ phía đông.
- West: kinh độ phía tây.

Backend có thể nhận request như sau:

~~~json
{
  "north": 10.82,
  "south": 10.75,
  "east": 106.72,
  "west": 106.65
}
~~~

Từ các giá trị này, tạo hai góc:

~~~text
top_left     = (north, west)
bottom_right = (south, east)
~~~

Ví dụ payload API có thể dùng tên rõ ràng:

~~~java
public record MapBounds(
        double north,
        double south,
        double east,
        double west
) {
}
~~~

Không nên gửi một mảng tọa độ không có tên thuộc tính nếu backend và frontend chưa thống nhất thứ tự. Object có north/south/east/west giúp tránh nhầm lẫn khi xử lý.

Một số thư viện bản đồ trả về getNorthEast() và getSouthWest(). Khi chuyển sang request:

- North lấy từ latitude của northeast.
- East lấy từ longitude của northeast.
- South lấy từ latitude của southwest.
- West lấy từ longitude của southwest.

Hãy kiểm tra kiểu dữ liệu của thư viện bản đồ đang sử dụng. Có thư viện dùng object {lat, lng}, có thư viện dùng {lat, lon}, và có thư viện dùng mảng [lng, lat].

## 5. geo_bounding_box query trong Elasticsearch

Query DSL **geo_bounding_box** tìm các tài liệu có điểm geo_point nằm trong hình chữ nhật được chỉ định.

Ví dụ:

~~~http
POST /places/_search
{
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.82,
          "lon": 106.65
        },
        "bottom_right": {
          "lat": 10.75,
          "lon": 106.72
        }
      }
    }
  }
}
~~~

Đọc query:

- **geo_bounding_box** là loại query địa lý.
- **location** là trường geo_point trong mapping.
- **top_left** là góc tây bắc.
- **bottom_right** là góc đông nam.
- Các tài liệu có location nằm trong vùng này sẽ được xét là phù hợp.

Có thể dùng dạng rút gọn với array hoặc object khác theo cú pháp Elasticsearch, nhưng object có tên lat/lon thường dễ kiểm tra hơn.

### Bounding box là điều kiện hình học

Elasticsearch kiểm tra vị trí của điểm dựa trên tọa độ. Nó không kiểm tra địa điểm có nằm trong một khu phố, quận hay ranh giới hành chính theo ý nghĩa nghiệp vụ.

Ví dụ, nếu một bounding box bao quanh một khu vực có hình dạng không đều, các điểm nằm trong phần góc của hình chữ nhật vẫn được trả về dù có thể nằm ngoài ranh giới khu vực mong muốn. Nếu cần lọc theo ranh giới polygon chính xác, hãy dùng geo_shape query thay vì bounding box.

## 6. Kết hợp bounding box với điều kiện nghiệp vụ

Một màn hình bản đồ thường không chỉ lọc theo vị trí. Người dùng có thể chọn loại địa điểm, trạng thái hoặc các điều kiện khác. Có thể kết hợp tất cả trong **bool.filter**.

Ví dụ chỉ lấy địa điểm đang hoạt động, thuộc loại restaurant và nằm trong viewport:

~~~http
POST /places/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "geo_bounding_box": {
            "location": {
              "top_left": {
                "lat": 10.82,
                "lon": 106.65
              },
              "bottom_right": {
                "lat": 10.75,
                "lon": 106.72
              }
            }
          }
        },
        {
          "term": {
            "category": "restaurant"
          }
        },
        {
          "term": {
            "status": "ACTIVE"
          }
        }
      ]
    }
  }
}
~~~

Các filter được kết hợp theo logic AND:

- Địa điểm phải nằm trong bounding box.
- category phải bằng restaurant.
- status phải bằng ACTIVE.

Filter context phù hợp vì đây là điều kiện lọc dữ liệu, không cần tính relevance score. Có thể thêm các điều kiện khác như tenant, quyền truy cập, thời gian hoạt động hoặc loại dịch vụ vào cùng bool.filter.

Không nên chỉ dựa vào filter ở frontend. Backend phải áp dụng lại các điều kiện nghiệp vụ và quyền truy cập để bảo đảm client không thể tự gửi request bỏ qua giới hạn dữ liệu.

## 7. Tạo query bằng StringQuery trong Spring Data Elasticsearch

Khi cần dùng geo_bounding_box, có thể truyền Query DSL JSON qua **StringQuery** rồi thực thi bằng **ElasticsearchOperations**.

Ví dụ:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

String dsl = """
{
  "bool": {
    "filter": [
      {
        "geo_bounding_box": {
          "location": {
            "top_left": {
              "lat": 10.82,
              "lon": 106.65
            },
            "bottom_right": {
              "lat": 10.75,
              "lon": 106.72
            }
          }
        }
      },
      {
        "term": {
          "status": "ACTIVE"
        }
      }
    ]
  }
}
""";

Query query = new StringQuery(dsl);

SearchHits<Place> hits = operations.search(
        query,
        Place.class,
        IndexCoordinates.of("places")
);
~~~

Trong ví dụ:

- Chuỗi JSON chứa query clause bool.
- geo_bounding_box lọc theo vị trí.
- term lọc status.
- StringQuery đóng gói DSL cho Spring Data.
- operations.search thực thi trên index places.
- SearchHits giữ các hit cùng metadata tìm kiếm.

Chuỗi truyền vào StringQuery là query clause. Không truyền nguyên search request body có key **query**, **from**, **size** hoặc **sort** nếu constructor đang nhận riêng query JSON.

Để thêm phân trang, có thể cấu hình Pageable trên Query object nếu API phiên bản đang dùng hỗ trợ:

~~~java
query.setPageable(PageRequest.of(0, 100));
~~~

Cần import PageRequest:

~~~java
import org.springframework.data.domain.PageRequest;
~~~

Khi trả marker cho bản đồ, thường cần giới hạn số điểm mỗi request để tránh response quá lớn. Nếu viewport có hàng chục nghìn địa điểm, hãy cân nhắc clustering hoặc aggregation theo zoom level thay vì trả mọi marker cùng lúc.

## 8. Xây dựng query động từ MapBounds

Trong service thực tế, tọa độ không nên được hard-code. Backend nhận MapBounds, xác thực giá trị rồi tạo query JSON hoặc query builder phù hợp.

Ví dụ kiểm tra đầu vào:

~~~java
public void validateBounds(MapBounds bounds) {
    if (bounds == null) {
        throw new IllegalArgumentException("Bounds không được để trống");
    }

    if (bounds.north() < -90 || bounds.north() > 90
            || bounds.south() < -90 || bounds.south() > 90) {
        throw new IllegalArgumentException("Latitude phải nằm trong [-90, 90]");
    }

    if (bounds.east() < -180 || bounds.east() > 180
            || bounds.west() < -180 || bounds.west() > 180) {
        throw new IllegalArgumentException("Longitude phải nằm trong [-180, 180]");
    }

    if (bounds.north() < bounds.south()) {
        throw new IllegalArgumentException("North phải lớn hơn hoặc bằng South");
    }
}
~~~

Đây là kiểm tra cơ bản cho bounding box thông thường không đi qua kinh tuyến 180 độ. Trường hợp dateline cần được xử lý riêng vì west có thể lớn hơn east theo cách biểu diễn kinh độ chuẩn hóa.

Sau khi xác thực, có thể tạo JSON object bằng serializer thay vì nối chuỗi:

~~~java
Map<String, Object> topLeft = Map.of(
        "lat", bounds.north(),
        "lon", bounds.west()
);

Map<String, Object> bottomRight = Map.of(
        "lat", bounds.south(),
        "lon", bounds.east()
);
~~~

Sau đó đưa hai object này vào cấu trúc query rồi serialize bằng thư viện JSON của ứng dụng. Cách này tránh lỗi dấu ngoặc, dấu phẩy và escape khi tạo JSON động.

Nếu dùng Java API Client, có thể xây dựng query bằng builder có kiểu dữ liệu. Cú pháp builder cụ thể thay đổi theo phiên bản Elasticsearch Java API Client; hãy dùng phiên bản được Spring Boot quản lý và kiểm tra chữ ký API trong dự án. Dù dùng StringQuery hay NativeQuery, điều quan trọng là giữ đúng quy ước top_left/bottom_right và lat/lon.

## 9. Ví dụ service tìm địa điểm trong viewport

Một service có thể đóng gói việc xác thực bounds và thực thi query. Ví dụ dưới đây dùng StringQuery để làm rõ cấu trúc DSL:

~~~java
import java.util.Locale;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;
import org.springframework.stereotype.Service;

@Service
public class PlaceSearchService {

    private static final IndexCoordinates PLACES =
            IndexCoordinates.of("places");

    private final ElasticsearchOperations operations;

    public PlaceSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Place> findInViewport(MapBounds bounds) {
        validateBounds(bounds);

        String dsl = String.format(Locale.ROOT, """
        {
          "bool": {
            "filter": [
              {
                "geo_bounding_box": {
                  "location": {
                    "top_left": {
                      "lat": %f,
                      "lon": %f
                    },
                    "bottom_right": {
                      "lat": %f,
                      "lon": %f
                    }
                  }
                }
              }
            ]
          }
        }
        """,
                bounds.north(),
                bounds.west(),
                bounds.south(),
                bounds.east()
        );

        Query query = new StringQuery(dsl);

        return operations.search(query, Place.class, PLACES);
    }

    private void validateBounds(MapBounds bounds) {
        if (bounds == null
                || bounds.north() < -90
                || bounds.north() > 90
                || bounds.south() < -90
                || bounds.south() > 90
                || bounds.east() < -180
                || bounds.east() > 180
                || bounds.west() < -180
                || bounds.west() > 180
                || bounds.north() < bounds.south()) {
            throw new IllegalArgumentException("Bounding box không hợp lệ");
        }
    }
}
~~~

Ví dụ dùng String.formatted để minh họa việc đưa số tọa độ vào query. Trong code production, nên dùng JSON serializer hoặc Java API Client builder để tạo request an toàn và dễ bảo trì hơn. Nếu vẫn format chuỗi, chỉ truyền giá trị số đã được kiểm tra; không đưa text do người dùng nhập trực tiếp vào JSON.

Với vùng đi qua kinh tuyến 180 độ, không dùng điều kiện kiểm tra west nhỏ hơn east như bounding box thông thường. Hãy xử lý riêng theo quy tắc dateline ở phần sau.

## 10. Giới hạn số marker và phân trang kết quả

Một viewport có thể chứa rất nhiều địa điểm. Trả tất cả marker trong một response có thể gây:

- Payload JSON lớn.
- Tăng thời gian truy vấn và truyền mạng.
- Frontend phải tạo quá nhiều marker.
- Bản đồ khó thao tác khi marker chồng lên nhau.
- Tăng bộ nhớ ở cả backend lẫn browser.

Có thể giới hạn số kết quả:

~~~java
Query query = new StringQuery(dsl);
query.setPageable(PageRequest.of(0, 500));
~~~

Tuy nhiên, giới hạn size có nghĩa là một phần địa điểm trong vùng sẽ không được trả về nếu số hit lớn hơn giới hạn. Giao diện cần có chính sách rõ ràng:

- Thông báo số lượng kết quả bị giới hạn nếu có thể.
- Dùng pagination hoặc tải thêm khi người dùng cần danh sách đầy đủ.
- Dùng clustering để gom marker ở zoom thấp.
- Chỉ trả marker chi tiết khi zoom đủ lớn.
- Dùng aggregation hoặc grid-based clustering cho tập dữ liệu lớn.

Nếu cần phân trang sâu, không nên tăng from vô hạn. Với truy vấn nhiều trang hoặc dữ liệu lớn, cân nhắc search_after với sort ổn định hoặc Point in Time theo yêu cầu. Scroll thường phù hợp với batch export, không phải thao tác tải marker khi người dùng kéo bản đồ liên tục.

## 11. Kết hợp bounding box với sort theo khoảng cách

Bounding box trả về tất cả điểm trong hình chữ nhật. Nếu muốn ưu tiên địa điểm gần tâm bản đồ, có thể kết hợp geo filter với **geo_distance sort**.

Ví dụ:

~~~http
POST /places/_search
{
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.82,
          "lon": 106.65
        },
        "bottom_right": {
          "lat": 10.75,
          "lon": 106.72
        }
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

Ở đây:

- geo_bounding_box giới hạn vùng cần tìm.
- _geo_distance sắp xếp các điểm trong vùng theo khoảng cách đến tâm.
- order asc đặt địa điểm gần hơn lên trước.
- unit km yêu cầu đơn vị khoảng cách là kilomet.

Điều này không biến bounding box thành bán kính. Một điểm ở góc xa của hình chữ nhật vẫn được trả về nếu nó nằm trong box; sort chỉ thay đổi thứ tự.

Nếu yêu cầu là tìm mọi điểm trong bán kính 3 km, dùng **geo_distance query**:

~~~json
{
  "query": {
    "geo_distance": {
      "distance": "3km",
      "location": {
        "lat": 10.7769,
        "lon": 106.7009
      }
    }
  }
}
~~~

Không thay geo_distance bằng bounding box chỉ vì cả hai đều giới hạn vị trí. Hình tròn và hình chữ nhật có phạm vi khác nhau.

## 12. Bounding box và geo_shape

**geo_bounding_box** phù hợp với trường geo_point, tức mỗi tài liệu có một vị trí điểm. Nếu tài liệu biểu diễn một khu vực bằng polygon hoặc đường, kiểu dữ liệu phù hợp có thể là **geo_shape**.

Ví dụ một khu vực được lưu bằng GeoJSON polygon:

~~~json
{
  "type": "Polygon",
  "coordinates": [
    [
      [106.65, 10.82],
      [106.72, 10.82],
      [106.72, 10.75],
      [106.65, 10.75],
      [106.65, 10.82]
    ]
  ]
}
~~~

GeoJSON dùng thứ tự tọa độ **[longitude, latitude]**. Vòng polygon phải được đóng bằng cách lặp lại tọa độ đầu tiên ở cuối.

Nếu cần tìm các hình học giao với viewport, có thể dùng **geo_shape query** với hình dạng envelope:

~~~http
POST /areas/_search
{
  "query": {
    "geo_shape": {
      "boundary": {
        "shape": {
          "type": "envelope",
          "coordinates": [
            [106.65, 10.82],
            [106.72, 10.75]
          ]
        },
        "relation": "intersects"
      }
    }
  }
}
~~~

Trong envelope GeoJSON:

- Tọa độ đầu tiên là góc tây bắc [west, north].
- Tọa độ thứ hai là góc đông nam [east, south].
- **intersects** tìm hình học giao với envelope.

Các relation của geo_shape có thể gồm intersects, within, contains hoặc disjoint tùy kiểu query và mapping. Chọn relation theo ý nghĩa nghiệp vụ. Không dùng geo_bounding_box cho polygon chỉ vì tên query có chữ bounding box; hãy dùng geo_shape khi cần quan hệ hình học giữa các shape.

## 13. Xử lý bounding box đi qua kinh tuyến 180 độ

Kinh độ thường được chuẩn hóa trong khoảng -180 đến 180. Khi người dùng xem vùng gần đường đổi ngày quốc tế, viewport có thể đi qua kinh tuyến 180 độ.

Ví dụ vùng bao quanh một phần Thái Bình Dương:

- West = 170.
- East = -170.

Trong cách biểu diễn này, west lớn hơn east vì vùng đi qua dateline. Đây không phải lỗi nhập liệu tự động; nó có thể là bounding box hợp lệ trên quả địa cầu.

Cần phân biệt:

- Box thông thường: west nhỏ hơn hoặc bằng east.
- Box đi qua dateline: west lớn hơn east.
- Box có north nhỏ hơn south: thường là dữ liệu không hợp lệ nếu không có quy ước đặc biệt.

Elasticsearch hỗ trợ các quy tắc xử lý longitude khi bounding box đi qua dateline, nhưng hành vi cụ thể cần được kiểm tra theo phiên bản và định dạng query đang dùng. Nếu ứng dụng muốn chủ động, có thể chia vùng thành hai box:

1. Box từ west đến 180 độ.
2. Box từ -180 độ đến east.

Sau đó kết hợp hai box bằng bool.should:

~~~json
{
  "query": {
    "bool": {
      "should": [
        {
          "geo_bounding_box": {
            "location": {
              "top_left": {
                "lat": 20,
                "lon": 170
              },
              "bottom_right": {
                "lat": -20,
                "lon": 180
              }
            }
          }
        },
        {
          "geo_bounding_box": {
            "location": {
              "top_left": {
                "lat": 20,
                "lon": -180
              },
              "bottom_right": {
                "lat": -20,
                "lon": -170
              }
            }
          }
        }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

Cách chia này biểu diễn vùng ở hai phía của đường đổi ngày. Nếu có các filter khác như status hoặc category, đặt chúng cùng bool.filter ở cấp ngoài để áp dụng cho cả hai nhánh.

Không tự sắp xếp west/east bằng cách lấy min và max khi gặp dateline. Làm như vậy có thể biến vùng nhỏ quanh kinh tuyến 180 độ thành một vùng gần như bao phủ cả thế giới.

## 14. Kiểm tra tọa độ và bounds ở backend

Frontend có thể gửi bounds từ thư viện bản đồ, nhưng backend vẫn cần xác thực. Các kiểm tra cơ bản:

- North và south phải nằm trong [-90, 90].
- East và west phải nằm trong [-180, 180].
- North phải lớn hơn hoặc bằng south.
- Không nhận NaN hoặc Infinity.
- Không nhận giá trị null nếu endpoint yêu cầu đủ bốn cạnh.
- Giới hạn kích thước vùng nếu nghiệp vụ không cho phép tìm toàn cầu.
- Xử lý dateline rõ ràng thay vì âm thầm đổi thứ tự longitude.

Ví dụ giới hạn diện tích truy vấn có thể dùng quy tắc nghiệp vụ như mức zoom tối thiểu hoặc chặn viewport quá rộng. Không nên chỉ giới hạn số chữ số thập phân; cần kiểm tra phạm vi địa lý và số hit có thể tạo ra.

Nếu API nhận dữ liệu từ nhiều client, hãy chuẩn hóa đầu vào thành một kiểu MapBounds nội bộ. Đừng để service phải biết từng thư viện bản đồ gửi latitude/longitude theo cấu trúc riêng.

## 15. Hiệu năng của geo_bounding_box

geo_bounding_box thường phù hợp với lọc điểm trong một viewport, nhưng chi phí vẫn phụ thuộc vào quy mô dữ liệu và request.

Các yếu tố cần quan tâm:

- Số lượng tài liệu trong index.
- Số shard và cách phân bổ dữ liệu.
- Mật độ điểm trong vùng được chọn.
- Số trường trả về trong _source.
- Kích thước response.
- Các filter bổ sung.
- Sort theo khoảng cách.
- Tần suất frontend gửi request khi người dùng kéo/zoom.

Một bounding box bao phủ toàn quốc hoặc toàn cầu có thể khớp lượng tài liệu rất lớn. Nếu giao diện chỉ cần hiển thị marker trong viewport nhỏ, hãy gửi bounds đúng theo bản đồ và giới hạn kết quả.

### Debounce request khi pan và zoom

Không nên gửi một search request sau mỗi pixel di chuyển. Frontend nên đợi một khoảng ngắn sau khi thao tác kéo/zoom kết thúc rồi mới gửi bounds mới.

Luồng điển hình:

~~~text
Người dùng kéo hoặc zoom bản đồ
             |
             v
       Cập nhật viewport
             |
             v
       Chờ debounce
             |
             v
       Gửi bounds mới
             |
             v
       Backend xác thực
             |
             v
       geo_bounding_box query
             |
             v
       Trả marker trong vùng
             |
             v
       Cập nhật bản đồ
~~~

Nếu request cũ vẫn đang chạy khi người dùng thay đổi viewport, frontend có thể hủy request cũ hoặc bỏ qua response cũ để tránh marker của vùng trước ghi đè vùng mới. Backend cũng có thể giới hạn tốc độ request theo người dùng.

### Chỉ trả trường cần thiết

Nếu marker chỉ cần ID, tên và tọa độ, hãy dùng source filtering để giảm payload:

~~~http
POST /places/_search
{
  "_source": [
    "name",
    "location",
    "category"
  ],
  "size": 500,
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.82,
          "lon": 106.65
        },
        "bottom_right": {
          "lat": 10.75,
          "lon": 106.72
        }
      }
    }
  }
}
~~~

Nếu entity Place có nhiều trường lớn như mô tả dài hoặc metadata, không nhất thiết phải trả toàn bộ chúng cho marker. Có thể ánh xạ kết quả sang DTO hoặc projection dành riêng cho bản đồ.

## 16. Clustering và aggregation khi có quá nhiều điểm

Khi zoom thấp, hàng nghìn marker có thể chồng lên nhau. Trả tất cả điểm không giúp người dùng hiểu bản đồ. Thay vào đó, có thể gom điểm thành cluster theo vùng lưới hoặc dùng geo aggregation.

Một lựa chọn là **geotile_grid aggregation**, nhóm điểm geo_point theo các ô bản đồ ở một mức zoom nhất định:

~~~http
POST /places/_search
{
  "size": 0,
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.82,
          "lon": 106.65
        },
        "bottom_right": {
          "lat": 10.75,
          "lon": 106.72
        }
      }
    }
  },
  "aggs": {
    "clusters": {
      "geotile_grid": {
        "field": "location",
        "precision": 7
      },
      "aggs": {
        "center": {
          "geo_centroid": {
            "field": "location"
          }
        }
      }
    }
  }
}
~~~

Trong ví dụ:

- Query lọc các điểm nằm trong viewport.
- **geotile_grid** chia khu vực thành các ô theo hệ thống tile.
- **precision** quyết định mức chi tiết của ô.
- **geo_centroid** tính tâm trung bình của các điểm trong bucket.
- **size: 0** bỏ qua danh sách hit và chỉ trả aggregation.

Precision cao tạo nhiều ô nhỏ; precision thấp tạo ít ô lớn. Có thể chọn precision dựa trên zoom level của bản đồ. Tuy nhiên, aggregation có giới hạn số bucket và chi phí riêng, nên cần kiểm soát kích thước kết quả và số lượng bucket.

Một hệ thống bản đồ có thể dùng hai chế độ:

- Zoom thấp: trả cluster/bucket.
- Zoom cao: trả marker chi tiết trong bounding box.

Đây là quyết định trình bày và hiệu năng, không phải thay đổi ý nghĩa của geo_bounding_box.

## 17. Đọc kết quả SearchHits và chuyển thành marker

Khi dùng ElasticsearchOperations, **SearchHits<Place>** chứa các kết quả đã ánh xạ. Mỗi **SearchHit<Place>** cung cấp entity và metadata của hit.

Ví dụ:

~~~java
SearchHits<Place> hits = operations.search(
        query,
        Place.class,
        IndexCoordinates.of("places")
);

List<PlaceMarker> markers = hits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .map(place -> new PlaceMarker(
                place.getId(),
                place.getName(),
                place.getLocation().getLat(),
                place.getLocation().getLon()
        ))
        .toList();
~~~

DTO cho marker:

~~~java
public record PlaceMarker(
        String id,
        String name,
        double latitude,
        double longitude
) {
}
~~~

Nếu SearchHits không có kết quả, danh sách marker sẽ rỗng. Đây là kết quả bình thường khi viewport không chứa địa điểm phù hợp.

Khi tạo DTO, hãy bảo đảm location không null. Dữ liệu có thể thiếu tọa độ nếu tài liệu cũ được ghi trước khi trường location trở thành bắt buộc. Có thể lọc hoặc xử lý tài liệu thiếu location theo quy tắc nghiệp vụ; không gọi getLat/getLon trên giá trị null.

Nếu frontend mong đợi GeoJSON, cần chuyển thành đúng thứ tự [longitude, latitude]:

~~~json
{
  "type": "Feature",
  "geometry": {
    "type": "Point",
    "coordinates": [106.7009, 10.7769]
  },
  "properties": {
    "id": "place-1001",
    "name": "Central Place"
  }
}
~~~

Không trả [latitude, longitude] trong GeoJSON vì đó là thứ tự sai theo chuẩn tọa độ GeoJSON.

## 18. Bounding box có bao gồm biên không?

Bounding box xác định một vùng hình chữ nhật theo các cạnh. Điểm nằm đúng trên cạnh có thể cần được xử lý nhất quán giữa các hệ thống bản đồ, Elasticsearch và logic nghiệp vụ.

Khi kiểm thử, hãy tạo các điểm:

- Nằm hoàn toàn bên trong box.
- Nằm ngoài phía bắc.
- Nằm ngoài phía nam.
- Nằm ngoài phía đông.
- Nằm ngoài phía tây.
- Nằm đúng trên từng cạnh.
- Nằm đúng tại bốn góc.

Điều này giúp xác nhận cách Elasticsearch xử lý các tọa độ biên theo mapping và phiên bản đang dùng. Nếu nghiệp vụ yêu cầu một quy tắc biên đặc biệt, hãy mô tả rõ trong API và test; không dựa vào một phép làm tròn tọa độ ở frontend.

Không nên tự cộng hoặc trừ một lượng epsilon tùy tiện vào bounds để “bù sai số”. Việc đó có thể làm vùng truy vấn lớn hơn hoặc nhỏ hơn ngoài ý muốn. Nếu cần làm tròn tọa độ, hãy chọn độ chính xác nhất quán ở cả client và server.

## 19. Kiểm thử bounding box

Có thể kiểm thử logic bounds ở tầng unit test và hành vi query bằng integration test.

### Unit test cho việc tạo bounds

Ví dụ kiểm tra chuyển đổi từ bốn cạnh sang hai góc:

~~~java
@Test
void createsTopLeftAndBottomRightFromViewport() {
    MapBounds bounds = new MapBounds(
            10.82,
            10.75,
            106.72,
            106.65
    );

    assertEquals(10.82, bounds.north());
    assertEquals(10.75, bounds.south());
    assertEquals(106.72, bounds.east());
    assertEquals(106.65, bounds.west());
}
~~~

### Test xác thực bounds

~~~java
@Test
void rejectsLatitudeOutsideValidRange() {
    MapBounds bounds = new MapBounds(
            95,
            10.75,
            106.72,
            106.65
    );

    assertThrows(
            IllegalArgumentException.class,
            () -> validator.validate(bounds)
    );
}
~~~

### Integration test với Elasticsearch

Tạo index có mapping location là geo_point và chèn các tài liệu ở các tọa độ:

- Một điểm nằm trong box.
- Một điểm nằm ngoài box.
- Một điểm ở biên.
- Một tài liệu không có location nếu mapping cho phép.

Sau đó chạy geo_bounding_box query và xác nhận tập ID trả về. Integration test cần dùng phiên bản Elasticsearch tương thích với Spring Data Elasticsearch của dự án; mock repository không thể xác nhận hành vi địa lý thực tế của cluster.

## 20. Lỗi thường gặp khi lọc theo vùng bản đồ

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Query báo lỗi field không phải geo_point | Mapping location là text hoặc keyword | Kiểm tra mapping và tạo index đúng kiểu |
| Không tìm thấy điểm ở vị trí đúng | Đảo lat/lon khi lưu hoặc truy vấn | Kiểm tra quy ước tọa độ ở frontend, Java và JSON |
| Kết quả nằm ngoài vùng nhìn thấy | Bounds được gửi sai hoặc dùng nhầm north/south/east/west | Kiểm tra giá trị viewport và hai góc |
| Query trả quá nhiều marker | Bounding box quá rộng hoặc zoom thấp | Giới hạn size, clustering hoặc geotile aggregation |
| Query trả quá ít marker | Bounds bị thu nhỏ, đảo cạnh hoặc làm tròn sai | Log bounds đã xác thực và thử tọa độ biên |
| Địa điểm mới chưa xuất hiện | Index chưa refresh sau khi ghi | Xem xét refresh policy và đặc tính near-real-time |
| Địa điểm thiếu tọa độ gây lỗi DTO | location null trong một số tài liệu | Kiểm tra null và xử lý dữ liệu thiếu |
| Vùng qua dateline bị sai | Xử lý west/east như box thông thường | Hỗ trợ longitude wrap hoặc chia thành hai box |
| Dùng bounding box nhưng muốn lọc polygon | Hình chữ nhật không phản ánh ranh giới thực | Dùng geo_shape với polygon |
| Dùng bounding box để tìm trong bán kính | Hình chữ nhật khác hình tròn | Dùng geo_distance query |
| Frontend hiển thị marker sai vị trí | GeoJSON nhận nhầm thứ tự tọa độ | Xuất coordinates theo [longitude, latitude] |
| Request tăng đột biến khi kéo bản đồ | Gửi query sau mỗi thay đổi nhỏ của viewport | Debounce, hủy request cũ và rate limit |

## 21. Quy trình triển khai lọc theo viewport

Khi xây dựng tính năng tìm địa điểm trong vùng bản đồ, có thể đi theo trình tự:

1. **Chọn mô hình dữ liệu.** Dùng geo_point cho vị trí điểm; dùng geo_shape cho polygon hoặc hình học phức tạp.
2. **Khai báo mapping.** Bảo đảm trường location được lập chỉ mục đúng kiểu.
3. **Thống nhất quy ước tọa độ.** Xác định frontend, backend và Elasticsearch dùng thứ tự nào.
4. **Lấy viewport bounds.** Đọc north, south, east và west từ thư viện bản đồ.
5. **Xác thực đầu vào.** Kiểm tra phạm vi lat/lon, thứ tự cạnh và trường hợp dateline.
6. **Tạo geo_bounding_box.** Đưa top_left và bottom_right vào Query DSL.
7. **Kết hợp filter nghiệp vụ.** Thêm category, status, tenant hoặc quyền truy cập vào bool.filter.
8. **Giới hạn response.** Dùng size hợp lý, source filtering hoặc clustering.
9. **Chuyển kết quả thành marker.** Bảo đảm tọa độ GeoJSON theo [longitude, latitude].
10. **Tối ưu tương tác.** Debounce request, xử lý response cũ và theo dõi latency.
11. **Kiểm thử ranh giới.** Kiểm tra điểm trong, ngoài, trên cạnh và vùng qua dateline.
12. **Theo dõi production.** Đo số hit, payload, thời gian query và tần suất request theo viewport.

geo_bounding_box là cách trực tiếp để lấy các tài liệu có geo_point nằm trong vùng chữ nhật của viewport. Trong Spring Data Elasticsearch, cần ánh xạ trường vị trí đúng kiểu, chuyển bounds thành top_left/bottom_right với thứ tự latitude và longitude chính xác, rồi kết hợp các điều kiện khác trong bool.filter. Bounding box phù hợp với việc tải marker theo vùng bản đồ; nếu cần tìm theo bán kính, dùng geo_distance, còn nếu cần lọc theo ranh giới polygon, dùng geo_shape. Với dữ liệu lớn, hãy giới hạn số hit hoặc dùng clustering để giao diện bản đồ giữ được tốc độ và khả năng sử dụng.
