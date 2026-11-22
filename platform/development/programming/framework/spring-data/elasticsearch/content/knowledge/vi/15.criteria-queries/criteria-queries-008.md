# Truy vấn địa lý theo khả năng của Criteria

Spring Data Elasticsearch cung cấp CriteriaQuery để xây dựng truy vấn theo dạng fluent API. Ngoài điều kiện thông thường như so khớp keyword, range và boolean, Criteria còn hỗ trợ một số điều kiện địa lý trên field kiểu geo_point.

Các truy vấn địa lý thường gặp gồm:

- Tìm document nằm trong một bán kính quanh một tọa độ.
- Tìm document nằm trong một hình chữ nhật địa lý (bounding box).
- Tìm document nằm bên trong một đa giác (polygon).
- Kết hợp điều kiện địa lý với các điều kiện nghiệp vụ khác như trạng thái, loại địa điểm hoặc tenant.

CriteriaQuery giúp biểu đạt các điều kiện này bằng Java object thay vì tự ghép JSON query. Tuy nhiên, Criteria không phải lớp bao phủ toàn bộ Elasticsearch Query DSL. Các yêu cầu nâng cao như geo_shape, sắp xếp theo khoảng cách, aggregation địa lý hoặc các tùy chọn đặc thù có thể cần NativeQuery hay Elasticsearch Java API Client trực tiếp.

## 1. Chuẩn bị field địa lý trong entity

Elasticsearch hỗ trợ field kiểu geo_point để lưu một vị trí gồm vĩ độ và kinh độ. Trong Spring Data Elasticsearch, có thể khai báo field như sau:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Document(indexName = "stores")
public class Store {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.GeoPoint)
    private GeoPoint location;

    // constructors, getters and setters
}
~~~

Field location được khai báo với FieldType.GeoPoint. Kiểu GeoPoint của Spring Data Elasticsearch biểu diễn một điểm địa lý.

Có thể khởi tạo điểm bằng vĩ độ và kinh độ:

~~~java
GeoPoint location = new GeoPoint(10.7769, 106.7009);
~~~

Trong ví dụ này:

- 10.7769 là latitude (vĩ độ).
- 106.7009 là longitude (kinh độ).

Thứ tự trong constructor GeoPoint là latitude trước, longitude sau. Đây là điểm dễ nhầm vì một số định dạng JSON địa lý dùng thứ tự longitude, latitude.

### 1.1. Mapping thực tế trên Elasticsearch

Mapping tương ứng có dạng:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "keyword"
      },
      "active": {
        "type": "boolean"
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

Có thể kiểm tra mapping bằng:

~~~http
GET /stores/_mapping?pretty
~~~

Nếu location được tạo thành object thông thường thay vì geo_point, các truy vấn địa lý sẽ không hoạt động như mong đợi. Dynamic mapping có thể suy luận một số định dạng điểm, nhưng với dữ liệu nghiệp vụ quan trọng nên khai báo rõ mapping.

### 1.2. Các dạng biểu diễn geo_point

Elasticsearch hỗ trợ nhiều dạng biểu diễn điểm, chẳng hạn object có lat/lon, chuỗi "lat,lon", hoặc mảng tọa độ theo thứ tự longitude, latitude. Ví dụ object:

~~~json
{
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
~~~

Với mảng tọa độ dạng Elasticsearch/GeoJSON, thứ tự thường là [longitude, latitude]:

~~~json
{
  "location": [
    106.7009,
    10.7769
  ]
}
~~~

Không nhầm thứ tự này với constructor GeoPoint(latitude, longitude). Hãy thống nhất quy ước tại ranh giới nhận dữ liệu từ API, database hoặc bản đồ.

Latitude hợp lệ nằm trong khoảng -90 đến 90; longitude nằm trong khoảng -180 đến 180. Cần kiểm tra dữ liệu đầu vào để tránh đảo tọa độ hoặc lưu giá trị ngoài miền hợp lệ.

## 2. CriteriaQuery và Criteria cho truy vấn địa lý

CriteriaQuery là implementation Query của Spring Data Elasticsearch, được xây dựng từ một hoặc nhiều Criteria.

Import thường dùng:

~~~java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
~~~

Một query đơn giản:

~~~java
Criteria criteria = new Criteria("active").is(true);
Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

Với truy vấn địa lý, Criteria được tạo trên tên field geo_point:

~~~java
Criteria criteria = new Criteria("location");
~~~

Sau đó thêm điều kiện không gian như within với GeoCircle, GeoBox hoặc GeoPolygon, tùy loại vùng cần tìm và API có trong phiên bản Spring Data Elasticsearch đang dùng.

Các lớp địa lý thường dùng nằm trong package:

~~~java
import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.geo.GeoBox;
import org.springframework.data.elasticsearch.core.geo.GeoCircle;
import org.springframework.data.elasticsearch.core.geo.GeoPolygon;
~~~

Tên lớp, constructor và các overload có thể thay đổi theo phiên bản Spring Data Elasticsearch. Hãy đối chiếu với dependency thực tế trước khi áp dụng ví dụ vào project.

## 3. Tìm địa điểm trong một bán kính

Một yêu cầu phổ biến là tìm cửa hàng nằm trong bán kính nhất định quanh vị trí người dùng. Ví dụ: tìm cửa hàng trong phạm vi 5 km quanh trung tâm Thành phố Hồ Chí Minh.

Với Criteria hỗ trợ GeoCircle, có thể biểu đạt vùng tròn quanh một điểm:

~~~java
GeoPoint center = new GeoPoint(10.7769, 106.7009);

Criteria criteria = new Criteria("location")
    .within(new GeoCircle(center, 5000));

Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

Ví dụ dùng bán kính 5.000 mét. Trong API GeoCircle có constructor nhận bán kính dạng số, giá trị này được biểu diễn theo mét. Nếu phiên bản dự án dùng kiểu Distance hoặc một constructor khác, hãy chuyển đổi đơn vị theo đúng API đó.

Điều kiện vòng tròn thường được chuyển thành truy vấn geo_distance của Elasticsearch. Query REST tương đương có dạng:

~~~http
POST /stores/_search
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

Trong đó:

- distance là bán kính tìm kiếm.
- location là tọa độ tâm.
- Elasticsearch trả về document có điểm nằm trong khoảng cách quy định.

### 3.1. Đơn vị khoảng cách

Elasticsearch hỗ trợ nhiều đơn vị khoảng cách, ví dụ:

| Đơn vị | Ký hiệu thường dùng |
|---|---|
| Mét | m |
| Kilômét | km |
| Centimét | cm |
| Milimét | mm |
| Dặm | mi |
| Yard | yd |
| Feet | ft |
| Inch | in |
| Hải lý | nmi |

Khi dùng REST DSL, có thể truyền chuỗi có đơn vị như 5km hoặc 5000m. Khi dùng GeoCircle, kiểm tra constructor của phiên bản đang dùng để biết giá trị bán kính là mét hay một kiểu Distance có đơn vị riêng.

Không nên truyền số 5 rồi giả định đó là 5 km nếu API đang hiểu là 5 mét. Lỗi đơn vị có thể làm kết quả quá hẹp hoặc quá rộng.

### 3.2. Tìm trong bán kính với điều kiện khác

Có thể kết hợp điều kiện địa lý với trạng thái cửa hàng:

~~~java
GeoPoint center = new GeoPoint(10.7769, 106.7009);
GeoCircle radius = new GeoCircle(center, 5000);

Criteria criteria = new Criteria("active").is(true)
    .and("location").within(radius);

Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

Điều kiện này yêu cầu document vừa có active = true, vừa có location nằm trong vùng tròn. Criteria nối các điều kiện theo AND ở ví dụ trên.

Có thể bổ sung category:

~~~java
Criteria criteria = new Criteria("active").is(true)
    .and("category").is("grocery")
    .and("location").within(radius);
~~~

Hãy xác nhận field category có mapping phù hợp với phép so khớp chính xác, thường là keyword.

## 4. Tìm trong một hình chữ nhật địa lý (bounding box)

Bounding box là vùng hình chữ nhật được xác định bằng hai góc:

- Top-left: góc trên bên trái.
- Bottom-right: góc dưới bên phải.

Với GeoBox, ví dụ:

~~~java
GeoBox box = new GeoBox(
    new GeoPoint(10.85, 106.65),
    new GeoPoint(10.70, 106.80)
);

Criteria criteria = new Criteria("location").within(box);
Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

Hai điểm được truyền theo thứ tự top-left rồi bottom-right. GeoPoint vẫn dùng thứ tự latitude, longitude.

Query REST tương đương sử dụng geo_bounding_box:

~~~http
POST /stores/_search
{
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.85,
          "lon": 106.65
        },
        "bottom_right": {
          "lat": 10.70,
          "lon": 106.80
        }
      }
    }
  }
}
~~~

Bounding box phù hợp với các trường hợp:

- Tìm điểm trong khu vực bản đồ đang hiển thị.
- Tìm địa điểm trong một vùng chữ nhật gần đúng.
- Giới hạn dữ liệu theo phạm vi viewport của ứng dụng bản đồ.
- Lọc dữ liệu sơ bộ trước khi thực hiện xử lý địa lý phức tạp hơn.

Bounding box không mô tả chính xác biên giới hành chính hoặc một vùng có hình dạng bất kỳ. Nếu khu vực cần tìm có hình dạng không phải hình chữ nhật, dùng polygon hoặc geo_shape phù hợp hơn.

### 4.1. Giới hạn khi vùng đi qua kinh tuyến 180 độ

Các vùng gần đường đổi ngày quốc tế có thể cắt qua kinh tuyến 180 độ. Khi đó longitude có thể chuyển từ giá trị gần 180 sang -180. Bounding box đơn giản có thể không thể hiện đúng vùng nhỏ mà bạn muốn mô tả.

Với ứng dụng toàn cầu, hãy kiểm tra hành vi của Elasticsearch đối với bounding box qua kinh tuyến 180 độ và cân nhắc polygon hoặc cách chia vùng phù hợp. Không áp dụng giả định rằng mọi hình chữ nhật trên bản đồ phẳng đều tương đương hình chữ nhật địa lý.

## 5. Tìm trong một đa giác (geo polygon)

Một số khu vực có biên không phải hình chữ nhật hoặc hình tròn. Ví dụ khu vực phục vụ giao hàng, khuôn viên, vùng phủ sóng hoặc ranh giới một khu vực nghiệp vụ.

GeoPolygon mô tả vùng bằng danh sách các điểm tạo thành đường biên:

~~~java
List<GeoPoint> points = List.of(
    new GeoPoint(10.80, 106.65),
    new GeoPoint(10.80, 106.75),
    new GeoPoint(10.72, 106.75),
    new GeoPoint(10.72, 106.65),
    new GeoPoint(10.80, 106.65)
);

GeoPolygon polygon = new GeoPolygon(points);

Criteria criteria = new Criteria("location").within(polygon);
Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

Ví dụ này mô tả một vùng gần hình chữ nhật bằng polygon. Điểm cuối lặp lại điểm đầu để đóng đường biên. Hãy kiểm tra yêu cầu constructor và quy tắc polygon của phiên bản thư viện đang sử dụng.

Query REST tương đương dùng geo_polygon:

~~~http
POST /stores/_search
{
  "query": {
    "geo_polygon": {
      "location": {
        "points": [
          { "lat": 10.80, "lon": 106.65 },
          { "lat": 10.80, "lon": 106.75 },
          { "lat": 10.72, "lon": 106.75 },
          { "lat": 10.72, "lon": 106.65 },
          { "lat": 10.80, "lon": 106.65 }
        ]
      }
    }
  }
}
~~~

Một số lưu ý với polygon:

- Các điểm phải tạo thành đường biên hợp lệ.
- Tránh polygon tự cắt hoặc có các cạnh chồng lấn ngoài ý muốn.
- Thứ tự điểm phải đi quanh biên vùng theo đúng hình dạng mong muốn.
- Cần kiểm tra polygon ở khu vực có kinh tuyến hoặc vĩ tuyến đặc biệt.
- Với dữ liệu địa lý phức tạp, xác minh kết quả bằng các điểm mẫu nằm trong và ngoài vùng.

GeoPolygon trong Criteria biểu đạt truy vấn geo_polygon trên geo_point. Nó không đồng nghĩa với toàn bộ tính năng geo_shape của Elasticsearch.

## 6. Kết hợp truy vấn địa lý với điều kiện nghiệp vụ

Criteria có thể ghép điều kiện địa lý với điều kiện thông thường. Ví dụ tìm cửa hàng đang mở trong bán kính 3 km và thuộc nhóm pharmacy:

~~~java
GeoPoint center = new GeoPoint(10.7769, 106.7009);
GeoCircle radius = new GeoCircle(center, 3000);

Criteria criteria = new Criteria("active").is(true)
    .and("category").is("pharmacy")
    .and("location").within(radius);

Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

Các điều kiện trong ví dụ là AND: document phải thỏa cả ba điều kiện.

Nếu cần logic OR hoặc nhiều nhánh điều kiện, Criteria hỗ trợ các phép nối theo API của nó. Tuy nhiên, khi query có cấu trúc bool phức tạp, nên dùng query DSL tường minh để tránh hiểu sai cách parser nhóm các nhánh.

Ví dụ yêu cầu: cửa hàng phải nằm trong vùng địa lý và có một trong hai category. Cấu trúc logic mong muốn:

~~~text
location nằm trong vùng
        AND
   +----+----+
   |         |
category A  category B
   (OR)
~~~

Nếu Criteria chain không biểu đạt rõ nhóm ngoặc OR/AND theo yêu cầu, hãy chuyển sang NativeQuery hoặc Elasticsearch Java API Client để kiểm soát chính xác bool query.

## 7. Phân trang kết quả địa lý

Một vùng địa lý có thể chứa rất nhiều document. Không nên tải toàn bộ kết quả về ứng dụng nếu giao diện chỉ hiển thị một trang.

Có thể gắn Pageable vào CriteriaQuery:

~~~java
GeoPoint center = new GeoPoint(10.7769, 106.7009);
GeoCircle radius = new GeoCircle(center, 5000);

Criteria criteria = new Criteria("location").within(radius);

Query query = new CriteriaQuery(criteria)
    .setPageable(PageRequest.of(0, 20));

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

Ví dụ lấy tối đa 20 kết quả trong trang đầu. Pageable giới hạn số document trả về và có thể chứa thông tin sort.

Lưu ý:

- Page/total có thể yêu cầu Elasticsearch tính tổng hit.
- Offset lớn có thể tốn tài nguyên.
- Nếu dữ liệu lớn và cần duyệt nhiều trang, cân nhắc search_after hoặc cơ chế phân trang phù hợp.
- Nếu mục tiêu là hiển thị các địa điểm gần nhất, chỉ giới hạn size chưa đủ; cần sort theo khoảng cách.

## 8. Criteria lọc theo vùng không đồng nghĩa sắp xếp theo khoảng cách

Một điểm quan trọng: truy vấn geo_distance hoặc GeoCircle xác định document nằm trong bán kính. Điều đó không tự động bảo đảm kết quả được sắp xếp từ gần đến xa.

Ví dụ Criteria:

~~~java
Criteria criteria = new Criteria("location")
    .within(new GeoCircle(center, 5000));

Query query = new CriteriaQuery(criteria);
~~~

Query này giới hạn tập kết quả trong bán kính. Nếu giao diện cần hiển thị cửa hàng gần nhất trước, phải thêm geo distance sort.

Elasticsearch REST DSL có dạng:

~~~http
POST /stores/_search
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
~~~

Kết quả được sắp xếp theo khoảng cách tăng dần. Distance sort là phần riêng của Search DSL; khả năng biểu đạt nó trực tiếp bằng Criteria thay đổi theo phiên bản. Khi CriteriaQuery không cung cấp tùy chọn cần thiết, hãy dùng NativeQuery hoặc Elasticsearch Java API Client.

Khi có nhiều document cùng khoảng cách, nên thêm một tiêu chí sort phụ ổn định như ID để phân trang nhất quán. Cú pháp sort phụ phụ thuộc API query đang sử dụng.

## 9. CriteriaQuery hỗ trợ gì và giới hạn ở đâu?

Criteria là API tiện lợi cho các điều kiện được Spring Data ánh xạ rõ ràng. Với địa lý, các dạng thường gặp là:

| Dạng dữ liệu/vùng | Mục đích | Criteria thường dùng |
|---|---|---|
| geo_point trong bán kính | Tìm quanh một tâm theo khoảng cách | within(GeoCircle) |
| geo_point trong hình chữ nhật | Tìm trong bounding box | within(GeoBox) |
| geo_point trong đa giác | Tìm trong vùng polygon | within(GeoPolygon) |
| Kết hợp geo với field thường | Lọc theo vị trí và điều kiện nghiệp vụ | Criteria.and(...) / Criteria.or(...) |

Criteria không phải API thay thế toàn bộ Elasticsearch DSL. Các yêu cầu sau thường cần kiểm tra kỹ hoặc dùng query API khác:

- geo_shape với các hình dạng phức tạp như multipolygon, line string hoặc geometry collection.
- Quan hệ hình học như intersects, within, contains hoặc disjoint trên geo_shape.
- Sắp xếp theo khoảng cách bằng _geo_distance.
- Aggregation địa lý như geohash_grid, geo_tile_grid hoặc geo_bounds.
- Script tính toán dựa trên vị trí.
- Các tùy chọn geo_distance đặc thù như distance_type hoặc validation_method nếu Criteria version không expose.
- Kết hợp nhiều nhánh bool phức tạp cùng nested query hoặc filter đặc biệt.

Nếu cần các khả năng này, có thể dùng NativeQuery (ở các phiên bản Spring Data Elasticsearch hỗ trợ) để xây dựng query theo Elasticsearch Java API Client, hoặc gọi client trực tiếp. Hãy chọn abstraction phù hợp với phiên bản dependency và không cố ép DSL phức tạp vào Criteria.

## 10. Phân biệt geo_point và geo_shape

geo_point biểu diễn một vị trí đơn lẻ. Nó phù hợp với:

- Cửa hàng.
- Nhà hàng.
- Người dùng.
- Thiết bị GPS.
- Trạm cảm biến.
- Một điểm giao nhận.

geo_shape biểu diễn hình học phức tạp như đường, vùng hoặc tập hợp hình học. Nó phù hợp với:

- Ranh giới khu vực.
- Tuyến đường.
- Vùng phủ sóng.
- Khu vực giao hàng có hình dạng bất kỳ.
- Các hình nhiều cạnh hoặc nhiều phần.

| Đặc điểm | geo_point | geo_shape |
|---|---|---|
| Dữ liệu | Một điểm | Hình học |
| Query bán kính quanh điểm | geo_distance | Có thể dùng shape relation theo yêu cầu |
| Bounding box | Có | Có |
| Polygon query trên điểm | geo_polygon | Query hình học có relation |
| Đường hoặc vùng phức tạp | Không phù hợp | Phù hợp |
| Criteria địa lý thông dụng | Hỗ trợ một số predicate | Thường cần query DSL/native API |

Không dùng GeoPolygon của Criteria trên field geo_shape rồi giả định semantics giống geo_polygon query trên geo_point. Hai mapping type và query family có mục đích khác nhau.

## 11. Kiểm tra mapping và dữ liệu trước khi chạy query

Nếu truy vấn địa lý không trả kết quả, hãy xác nhận field thực sự là geo_point:

~~~http
GET /stores/_mapping?pretty
~~~

Kiểm tra document:

~~~http
GET /stores/_doc/store-1001
~~~

Document có thể chứa:

~~~json
{
  "_source": {
    "name": "Central Store",
    "location": {
      "lat": 10.7769,
      "lon": 106.7009
    }
  }
}
~~~

Kiểm tra các yếu tố:

- Field name có đúng là location không.
- Mapping có type geo_point không.
- Dữ liệu có latitude và longitude đúng thứ tự không.
- Tọa độ có nằm trong miền hợp lệ không.
- Query đang dùng đúng index hoặc alias không.
- Radius có đúng đơn vị không.
- Điểm mẫu có thực sự nằm trong vùng đã chọn không.

Nếu index được tạo trước khi entity mapping thay đổi, annotation mới trong Java không tự động sửa mapping cũ. Có thể cần tạo index mới, chuyển dữ liệu và chuyển alias theo quy trình migration.

## 12. Kiểm thử truy vấn địa lý

Nên tạo dữ liệu test có vị trí nằm trong và ngoài vùng cần tìm. Ví dụ:

~~~java
Store nearby = new Store(
    "S-NEAR",
    "Nearby Store",
    true,
    "grocery",
    new GeoPoint(10.7770, 106.7010)
);

Store farAway = new Store(
    "S-FAR",
    "Far Store",
    true,
    "grocery",
    new GeoPoint(10.9000, 106.9000)
);
~~~

Ghi document vào index test, sau đó refresh index trước khi chạy Search API:

~~~java
operations.save(List.of(nearby, farAway));

IndexOperations indexOperations =
    operations.indexOps(Store.class);

indexOperations.refresh();
~~~

Tạo Criteria bán kính:

~~~java
GeoPoint center = new GeoPoint(10.7769, 106.7009);

Criteria criteria = new Criteria("location")
    .within(new GeoCircle(center, 1000));

Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

Assertion nên xác nhận:

- S-NEAR có trong kết quả.
- S-FAR không có trong kết quả.
- Không có document thiếu location bị trả về như một điểm hợp lệ.
- Tọa độ ở ngay gần biên bán kính được xử lý theo quy tắc dự kiến.

Kết quả tìm kiếm địa lý phụ thuộc khoảng cách hình cầu và cách Elasticsearch xử lý tọa độ. Không nên chọn test point quá sát biên nếu chưa xác định rõ sai số và distance calculation. Dùng các điểm rõ ràng nằm bên trong và bên ngoài trước, sau đó bổ sung test biên riêng.

### 12.1. Refresh trong test

Elasticsearch là hệ thống near-real-time đối với Search. Document vừa được index có thể chưa xuất hiện trong query cho tới lần refresh tiếp theo.

Trong integration test, có thể gọi indexOperations.refresh() trước khi search. Không cần ép refresh sau mọi lần ghi trong production; refresh thường xuyên làm giảm hiệu năng indexing.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Criteria geo query lỗi mapping | Field chưa được khai báo geo_point | Đọc mapping của index |
| Không có kết quả dù tọa độ có vẻ đúng | Đảo latitude/longitude hoặc sai index | Kiểm tra _source và quy ước tọa độ |
| Kết quả quá ít | Radius bị hiểu sai đơn vị | Xác nhận bán kính mét/km |
| Kết quả quá rộng | Dùng nhầm longitude/latitude hoặc radius quá lớn | Kiểm tra tâm và đơn vị |
| GeoCircle constructor không khớp | Khác phiên bản Spring Data | Đối chiếu API GeoCircle của dependency |
| Bounding box sai vùng | Nhầm top-left/bottom-right | Kiểm tra hai góc và thứ tự lat/lon |
| Polygon không hợp lệ | Điểm sai thứ tự, tự cắt hoặc chưa đóng biên | Kiểm tra danh sách điểm |
| Kết quả không gần nhất đứng đầu | Query chỉ lọc, chưa geo distance sort | Thêm _geo_distance sort bằng NativeQuery/client |
| Không dùng được geo_shape | Criteria geo_point không bao phủ shape DSL | Dùng native query hoặc Java API Client |
| Test vừa ghi xong không tìm thấy | Index chưa refresh | Refresh index trong test |
| Query chạy chậm | Tìm trên nhiều index/shard hoặc vùng quá rộng | Giới hạn index, bounding box và kích thước kết quả |

## 14. Quy trình lựa chọn API

Có thể chọn cách xây dựng query theo nhu cầu:

1. Nếu chỉ tìm điểm trong bán kính, dùng Criteria với GeoCircle nếu phiên bản hỗ trợ.
2. Nếu tìm điểm trong vùng chữ nhật, dùng Criteria với GeoBox.
3. Nếu tìm điểm trong vùng polygon, dùng Criteria với GeoPolygon.
4. Nếu cần kết hợp các predicate địa lý với field thông thường, ghép Criteria bằng AND/OR khi logic rõ ràng.
5. Nếu cần geo_shape, distance sort, aggregation địa lý hoặc tùy chọn DSL không được Criteria expose, dùng NativeQuery hoặc Elasticsearch Java API Client.
6. Nếu cần kiểm soát index động, truyền IndexCoordinates vào overload ElasticsearchOperations phù hợp.

Ví dụ chọn API:

| Nhu cầu | Hướng triển khai |
|---|---|
| Cửa hàng trong 5 km | Criteria + GeoCircle |
| Điểm trong viewport bản đồ | Criteria + GeoBox |
| Điểm nằm trong vùng giao hàng | Criteria + GeoPolygon |
| Điểm gần nhất trước | Query geo + _geo_distance sort |
| Đường biên khu vực phức tạp | geo_shape + native DSL |
| Đếm số điểm trong bán kính | CriteriaQuery + operations.count nếu query được hỗ trợ |
| Tìm theo vị trí và trạng thái | Kết hợp Criteria địa lý với điều kiện field thường |

## 15. Lưu ý về hiệu năng và dữ liệu địa lý

Truy vấn địa lý vẫn chịu ảnh hưởng của số shard, số index, số document và tải cluster. Một số nguyên tắc hữu ích:

- Giới hạn phạm vi index nếu có thể.
- Dùng bounding box để giới hạn viewport khi phù hợp.
- Giới hạn số kết quả trả về.
- Chỉ lấy field cần thiết nếu document lớn.
- Không chạy geo query trên index không cần thiết.
- Dùng mapping geo_point cho field vị trí đơn lẻ.
- Kiểm tra dữ liệu đầu vào và loại bỏ tọa độ không hợp lệ.
- Đo latency với dữ liệu gần quy mô production.

Nếu query tìm cửa hàng gần một điểm nhưng kết quả cần sort theo khoảng cách, cần phân biệt chi phí lọc với chi phí sort. Không nên tải một tập kết quả lớn về Java rồi tính khoảng cách thủ công nếu Elasticsearch có thể xử lý geo query/sort phù hợp.

Đối với các yêu cầu như vùng giao hàng có hình dạng phức tạp, nên đánh giá geo_shape và cách lưu geometry ngay từ thiết kế mapping. Chuyển đổi từ nhiều điểm geo_point rời rạc thành một vùng polygon ở tầng ứng dụng không tự tạo ra semantics giao cắt hình học.

## 16. Bảng tra cứu nhanh

| Mục đích | Criteria / API |
|---|---|
| Khai báo điểm địa lý | @Field(type = FieldType.GeoPoint) |
| Tạo điểm | new GeoPoint(latitude, longitude) |
| Tạo CriteriaQuery | new CriteriaQuery(criteria) |
| Tìm trong bán kính | within(new GeoCircle(center, radius)) |
| Tìm trong hình chữ nhật | within(new GeoBox(topLeft, bottomRight)) |
| Tìm trong polygon | within(new GeoPolygon(points)) |
| Kết hợp điều kiện thường | Criteria.and(...) / Criteria.or(...) |
| Thực hiện truy vấn | ElasticsearchOperations.search(query, Entity.class) |
| Đếm kết quả | ElasticsearchOperations.count(query, Entity.class) |
| Sắp xếp theo khoảng cách | _geo_distance sort qua native query/client |
| Truy vấn hình học phức tạp | geo_shape qua native query/client |

CriteriaQuery hỗ trợ một số truy vấn địa lý phổ biến trên geo_point như bán kính, bounding box và polygon, đồng thời cho phép ghép chúng với điều kiện nghiệp vụ. Hãy khai báo mapping đúng, thống nhất thứ tự latitude/longitude và đơn vị khoảng cách, kiểm tra vùng bằng dữ liệu mẫu, và chuyển sang NativeQuery hoặc Elasticsearch Java API Client khi cần geo_shape, distance sort, aggregation hoặc tùy chọn DSL nâng cao mà Criteria không biểu đạt được.

