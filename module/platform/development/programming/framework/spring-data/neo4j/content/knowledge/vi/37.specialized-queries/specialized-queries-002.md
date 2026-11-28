# Truy vấn không gian, khoảng cách và hệ tọa độ

Bài học này thuộc chương **Truy vấn chuyên biệt** của module **SPRING_DATA_NEO4J**. Neo4j lưu được giá trị không gian `POINT` trực tiếp trên node và relationship. Spring Data Neo4j ánh xạ các điểm này thành kiểu Java phù hợp, còn Cypher cung cấp các hàm để tính khoảng cách và kiểm tra một điểm có nằm trong vùng hay không.

Các truy vấn không gian thường gặp trong ứng dụng là tìm địa điểm gần một tọa độ, lọc địa điểm trong bán kính, tìm node trong một vùng bản đồ và sắp xếp kết quả theo khoảng cách. Để kết quả đúng, ứng dụng phải thống nhất hệ tọa độ (CRS), thứ tự kinh độ/vĩ độ, số chiều và đơn vị đo ngay từ lúc nhận dữ liệu.

## 1. Giá trị POINT trong Neo4j

Neo4j hỗ trợ kiểu không gian `POINT` với hai hoặc ba tọa độ. Mỗi điểm luôn gắn với một Coordinate Reference System (CRS), xác định các tọa độ có ý nghĩa gì và đơn vị được hiểu như thế nào.

`POINT` có thể được lưu thành property của node hoặc relationship. Ví dụ node `Place` có property `location`:

~~~cypher
CREATE (:Place {
    name: 'Central Library',
    location: point({longitude: 105.8342, latitude: 21.0278})
})
~~~

Neo4j tự suy ra CRS WGS-84 2D khi `point()` nhận các khóa `longitude` và `latitude`. Giá trị `location` được lưu dưới dạng `POINT`, không phải chuỗi `"105.8342,21.0278"` hay một list số thông thường.

Một `POINT` có các thành phần chính:

- Tọa độ `x`, `y` và có thể có `z`.
- CRS xác định ý nghĩa của các tọa độ.
- SRID (Spatial Reference Identifier) là mã số của CRS.

Không nên lưu tọa độ thành hai property số riêng nếu use case cần truy vấn khoảng cách hoặc vùng không gian. Lưu thành `POINT` giúp Cypher dùng hàm không gian và point index.

## 2. Bốn hệ tọa độ được Neo4j hỗ trợ

Neo4j hỗ trợ bốn CRS, chia thành hệ địa lý (geographic) và hệ tọa độ Descartes (Cartesian):

| CRS | SRID | Số chiều | Tọa độ | Đơn vị |
|---|---:|---:|---|---|
| WGS-84 2D | `4326` | 2 | Kinh độ, vĩ độ | Độ thập phân; khoảng cách trả về mét |
| WGS-84 3D | `4979` | 3 | Kinh độ, vĩ độ, độ cao | Độ thập phân và mét; khoảng cách trả về mét |
| Cartesian 2D | `7203` | 2 | `x`, `y` | Không quy định; kết quả cùng đơn vị với tọa độ |
| Cartesian 3D | `9157` | 3 | `x`, `y`, `z` | Không quy định; kết quả cùng đơn vị với tọa độ |

### WGS-84 cho vị trí trên Trái Đất

Với vị trí địa lý, WGS-84 2D là lựa chọn thông dụng:

~~~cypher
RETURN point({longitude: 105.8342, latitude: 21.0278}) AS location
~~~

Trong WGS-84, trục `x` tương ứng với longitude (kinh độ), trục `y` tương ứng với latitude (vĩ độ). Khi viết map cho `point()`, nên dùng tên `longitude` và `latitude` thay vì `x` và `y` để tránh đảo tọa độ.

WGS-84 3D bổ sung `height`:

~~~cypher
RETURN point({
    longitude: 105.8342,
    latitude: 21.0278,
    height: 18.5
}) AS location3d
~~~

`height` được tính bằng mét so với ellipsoid WGS-84. Vĩ độ hợp lệ nằm trong khoảng từ -90 đến 90 độ; kinh độ nằm trong khoảng từ -180 đến 180 độ. Nên xác thực dữ liệu đầu vào ở ứng dụng trước khi lưu, thay vì phụ thuộc vào hành vi chuẩn hóa của database.

### Cartesian cho mặt phẳng hoặc mô hình 3D

Cartesian phù hợp với tọa độ trong mặt phẳng, sơ đồ nhà máy, bản đồ nội bộ hoặc mô hình không gian ba chiều:

~~~cypher
RETURN point({x: 120.5, y: 42.0}) AS floorPosition,
       point({x: 12.0, y: 8.0, z: 3.5}) AS machinePosition
~~~

Neo4j không gán đơn vị vật lý cho `x`, `y`, `z` Cartesian. Nếu ứng dụng quy ước tọa độ là mét thì khoảng cách trả về là mét; nếu tọa độ là centimet thì kết quả cũng là centimet. Quy ước đơn vị phải nhất quán trong toàn bộ property.

Không trộn WGS-84 với Cartesian hoặc 2D với 3D trong cùng phép tính. Hai điểm khác CRS hoặc khác số chiều không thể được so sánh không gian trực tiếp; `point.distance()` và `point.withinBBox()` trả `null` khi các điểm không tương thích. Neo4j không tự chuyển đổi hệ tọa độ cho ứng dụng.

## 3. Chọn kiểu Java để ánh xạ điểm

Spring Data Neo4j hỗ trợ các kiểu sau:

| Kiểu Java | CRS được ánh xạ | Ghi chú |
|---|---|---|
| `org.springframework.data.geo.Point` | WGS-84 2D / SRID 4326 | Kiểu chung của Spring Data; dùng cho điểm địa lý 2D |
| `org.neo4j.driver.types.Point` | Điểm native Neo4j | Giữ thông tin SRID và số chiều; phù hợp với derived finder `Near` |
| `GeographicPoint2d` | WGS-84 2D / SRID 4326 | Kiểu SDN tường minh cho điểm địa lý 2D |
| `GeographicPoint3d` | WGS-84 3D / SRID 4979 | Kiểu SDN tường minh cho điểm địa lý 3D |
| `CartesianPoint2d` | Cartesian 2D / SRID 7203 | Kiểu SDN tường minh cho tọa độ phẳng 2D |
| `CartesianPoint3d` | Cartesian 3D / SRID 9157 | Kiểu SDN tường minh cho tọa độ phẳng 3D |

Các kiểu `GeographicPoint2d`, `GeographicPoint3d`, `CartesianPoint2d` và `CartesianPoint3d` nằm trong package `org.springframework.data.neo4j.types`. Nếu dùng `Neo4jPoint` làm kiểu thuộc tính tổng quát, không trộn các điểm khác CRS hoặc số chiều trên cùng một property của cùng label. Nên chọn kiểu concrete để thể hiện rõ mô hình dữ liệu.

Lưu ý thứ tự tham số khi tạo điểm:

~~~java
import org.neo4j.driver.Values;
import org.neo4j.driver.types.Point;
import org.springframework.data.neo4j.types.GeographicPoint2d;

Point driverPoint = Values.point(4326, 105.8342, 21.0278).asPoint();

GeographicPoint2d sdnPoint = new GeographicPoint2d(21.0278, 105.8342);
~~~

`Values.point(srid, x, y)` nhận `x` trước rồi `y`, vì vậy với WGS-84 phải truyền longitude trước latitude. Ngược lại, constructor `GeographicPoint2d` nhận latitude trước longitude. Đây là nguồn gây lỗi phổ biến khi tọa độ trông vẫn hợp lệ nhưng vị trí bị chuyển sang nơi khác.

## 4. Khai báo entity có property location

Ví dụ dùng kiểu native `org.neo4j.driver.types.Point` để tận dụng derived finder `Near`:

~~~java
package com.example.graph.domain;

import org.neo4j.driver.types.Point;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Place")
public class Place {

    @Id
    private String id;

    private String name;

    private Point location;

    public Place() {
    }

    public Place(String id, String name, Point location) {
        this.id = id;
        this.name = name;
        this.location = location;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Point getLocation() {
        return location;
    }

    public void setLocation(Point location) {
        this.location = location;
    }
}
~~~

Spring Data Neo4j chuyển đổi `Point` sang property không gian của Neo4j khi lưu entity và chuyển ngược khi đọc. Nếu ứng dụng không cần derived finder, có thể chọn kiểu SDN `GeographicPoint2d` hoặc `CartesianPoint2d` để thể hiện CRS rõ ngay trong domain model.

## 5. Tạo điểm WGS-84 trong Java

Với Neo4j Java Driver, dùng `Values.point()` để tạo giá trị point có SRID rõ ràng:

~~~java
import org.neo4j.driver.Values;
import org.neo4j.driver.types.Point;

public final class GeoPoints {

    private GeoPoints() {
    }

    public static Point wgs84(double longitude, double latitude) {
        if (longitude < -180 || longitude > 180) {
            throw new IllegalArgumentException("longitude out of range");
        }
        if (latitude < -90 || latitude > 90) {
            throw new IllegalArgumentException("latitude out of range");
        }

        return Values.point(4326, longitude, latitude).asPoint();
    }
}
~~~

Không tạo một `Point` WGS-84 bằng SRID Cartesian `7203`. SRID không chỉ là metadata trang trí; nó quyết định cách Neo4j hiểu tọa độ và tính khoảng cách.

## 6. Derived query tìm địa điểm gần một điểm

Spring Data Neo4j hỗ trợ từ khóa `Near` trong derived finder khi property trong entity có kiểu `org.neo4j.driver.types.Point`:

~~~java
package com.example.graph.repository;

import java.util.List;

import com.example.graph.domain.Place;
import org.neo4j.driver.types.Point;
import org.springframework.data.domain.Range;
import org.springframework.data.geo.Box;
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Distance;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.BoundingBox;

public interface PlaceRepository extends Neo4jRepository<Place, String> {

    List<Place> findByLocationNear(Point point);

    List<Place> findByLocationNear(Point point, Distance maxDistance);

    List<Place> findByLocationNear(Point point, Range<Distance> distanceRange);

    List<Place> findByLocationWithin(Circle circle);

    List<Place> findByLocationWithin(Box box);

    List<Place> findByLocationWithin(BoundingBox boundingBox);
}
~~~

Các biến thể có ý nghĩa:

- `findByLocationNear(point)`: tìm các địa điểm và sắp xếp theo khoảng cách tới điểm đầu vào tăng dần.
- `findByLocationNear(point, maxDistance)`: chỉ lấy các điểm trong khoảng cách tối đa.
- `findByLocationNear(point, distanceRange)`: giới hạn kết quả trong một khoảng cách từ min đến max.

Ví dụ gọi repository với bán kính 5 km:

~~~java
import java.util.List;

import com.example.graph.domain.Place;
import com.example.graph.repository.PlaceRepository;
import org.neo4j.driver.types.Point;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;

Point origin = GeoPoints.wgs84(105.8342, 21.0278);
Distance radius = new Distance(5, Metrics.KILOMETERS);

List<Place> nearby = placeRepository.findByLocationNear(origin, radius);
~~~

`Distance` và `Metrics` cho phép biểu diễn giới hạn bằng kilomet hoặc mile. Với WGS-84, Neo4j tính khoảng cách bằng mét; SDN xử lý metric của `Distance` khi tạo truy vấn. Không truyền một số `5` trần nếu nghiệp vụ muốn diễn đạt 5 km, vì số đó không nói rõ đơn vị.

## 7. Derived query tìm điểm trong vùng

SDN hỗ trợ từ khóa `Within` cho các hình dạng không gian `Circle`, `Box` và `BoundingBox`:

~~~java
import java.util.List;

import com.example.graph.domain.Place;
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;

Point center = new Point(105.8342, 21.0278); // x = longitude, y = latitude
Circle area = new Circle(center, new Distance(3, Metrics.KILOMETERS));

List<Place> places = placeRepository.findByLocationWithin(area);
~~~

Method repository tương ứng:

~~~java
List<Place> findByLocationWithin(Circle circle);
~~~

Ở đây `Circle` là kiểu hình học của Spring Data Commons; center là `org.springframework.data.geo.Point`. Với kiểu này, `x` là longitude và `y` là latitude khi được SDN ánh xạ thành WGS-84 2D.

Đối với một vùng hình chữ nhật, có thể dùng `Box` hoặc SDN `BoundingBox`. Nếu có `Polygon`, SDN cung cấp `BoundingBox.of(polygon)` để tạo bounding rectangle. Bounding box chỉ là hình chữ nhật bao quanh polygon, không phải phép kiểm tra điểm nằm chính xác bên trong biên polygon. Nếu nghiệp vụ cần kiểm tra hình dạng phức tạp, hãy dùng Cypher hoặc xử lý hình học chuyên biệt phù hợp.

## 8. Tính khoảng cách bằng point.distance()

Cypher có hàm `point.distance(from, to)` để tính khoảng cách giữa hai điểm cùng CRS và cùng số chiều:

~~~cypher
WITH
    point({longitude: 105.8342, latitude: 21.0278}) AS origin,
    point({longitude: 105.8542, latitude: 21.0278}) AS destination
RETURN point.distance(origin, destination) AS distanceMeters
~~~

Với WGS-84, hàm trả khoảng cách địa lý theo mét. Tính toán 2D sử dụng công thức haversine trên mô hình Trái Đất hình cầu. Với WGS-84 3D, Neo4j kết hợp khoảng cách bề mặt với chênh lệch độ cao bằng công thức Pythagoras; cách tính này phù hợp với các điểm gần bề mặt Trái Đất nhưng không phải phép đo chính xác cho khoảng cách giữa các vệ tinh ở độ cao rất lớn.

Với Cartesian, hàm trả khoảng cách Euclidean theo đơn vị của tọa độ:

~~~cypher
WITH
    point({x: 2.0, y: 3.0}) AS a,
    point({x: 5.0, y: 7.0}) AS b
RETURN point.distance(a, b) AS distance
~~~

Kết quả là 5.0 đơn vị Cartesian. Nếu `x` và `y` là mét thì kết quả là mét; nếu là pixel hoặc centimet thì kết quả giữ đơn vị đó.

Không dùng toán tử so sánh trực tiếp như `p.location < otherPoint` để tìm điểm gần hơn. Dùng `point.distance()` hoặc các điều kiện bounding box được hỗ trợ.

## 9. Truy vấn bán kính bằng @Query

Khi cần kiểm soát rõ Cypher, thêm phương thức `@Query` vào `PlaceRepository` và truyền point cùng bán kính qua parameter:

~~~java
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    MATCH (p:Place)
    WHERE point.distance(p.location, $origin) <= $radiusMeters
    RETURN p
    ORDER BY point.distance(p.location, $origin)
    """)
List<Place> findWithinRadius(
    @Param("origin") Point origin,
    @Param("radiusMeters") double radiusMeters
);
~~~

Ví dụ gọi:

~~~java
Point origin = GeoPoints.wgs84(105.8342, 21.0278);
List<Place> places = placeRepository.findWithinRadius(origin, 5000.0);
~~~

Trong ví dụ này, `radiusMeters` được quy định bằng mét vì điểm đầu vào thuộc WGS-84. Nếu muốn API nhận kilomet, hãy đổi đơn vị rõ ràng ở service trước khi gọi repository hoặc dùng derived finder với `Distance` và `Metrics.KILOMETERS`.

Parameter binding giữ dữ liệu tọa độ tách khỏi câu Cypher. Không ghép longitude, latitude hoặc bán kính thành chuỗi query bằng phép nối string.

## 10. Truy vấn bounding box bằng point.withinBBox()

`point.withinBBox(point, lowerLeft, upperRight)` kiểm tra điểm có nằm trong hộp giới hạn hay không. Hai góc phải cùng CRS và cùng số chiều với điểm cần kiểm tra.

~~~cypher
WITH
    point({longitude: 105.80, latitude: 20.98}) AS lowerLeft,
    point({longitude: 105.90, latitude: 21.08}) AS upperRight
MATCH (p:Place)
WHERE point.withinBBox(p.location, lowerLeft, upperRight)
RETURN p
~~~

Có thể dùng hàm này trong repository custom query:

~~~java
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    MATCH (p:Place)
    WHERE point.withinBBox(p.location, $lowerLeft, $upperRight)
    RETURN p
    """)
List<Place> findWithinBounds(
    @Param("lowerLeft") Point lowerLeft,
    @Param("upperRight") Point upperRight
);
~~~

Với tọa độ địa lý, `lowerLeft` là góc tây nam và `upperRight` là góc đông bắc. Neo4j xử lý trường hợp bounding box cắt qua kinh tuyến 180 độ; nếu latitude của lower-left nằm phía bắc latitude của upper-right, vùng kết quả là rỗng.

Nếu một trong các điểm là `null` hoặc CRS không tương thích, hàm có thể trả `null`. Trong điều kiện `WHERE`, giá trị `null` không được xem là `true`, vì vậy record sẽ không được chọn. Hãy xác thực tọa độ và CRS trước khi chạy query.

## 11. Kết hợp truy vấn không gian với điều kiện graph

Một điểm mạnh của Neo4j là có thể kết hợp điều kiện vị trí với quan hệ graph. Ví dụ tìm địa điểm trong bán kính 2 km có loại `Restaurant` và có liên kết tới một khu vực:

~~~cypher
MATCH (p:Place)-[:LOCATED_IN]->(area:Area)
WHERE p.category = $category
  AND point.distance(p.location, $origin) <= $radiusMeters
RETURN p, area
ORDER BY point.distance(p.location, $origin)
~~~

Điều kiện không gian giới hạn vị trí, còn traversal lọc theo cấu trúc graph. Có thể mở rộng thêm điều kiện như trạng thái hoạt động, loại dịch vụ, rating hoặc quan hệ với người dùng.

Nếu truy vấn trả entity có relationship, hãy bảo đảm phần `RETURN` chứa đủ node và relationship để SDN hydrate domain object đúng cách. Khi chỉ cần danh sách địa điểm cùng khoảng cách, cân nhắc trả DTO/projection thay vì tải toàn bộ graph.

## 12. Point index và tối ưu truy vấn

Với dữ liệu lớn, tạo point index cho property được dùng thường xuyên trong điều kiện không gian:

~~~cypher
CREATE POINT INDEX place_location_index IF NOT EXISTS
FOR (p:Place)
ON (p.location)
~~~

Point index hỗ trợ các predicate không gian như:

- So sánh point bằng nhau.
- Kiểm tra point trong bounding box bằng `point.withinBBox()`.
- Tìm theo khoảng cách bằng `point.distance(property, center) <= distance`.

Neo4j cũng có thể tạo point index trên property của relationship. Index chỉ được dùng khi truy vấn có dạng phù hợp với predicate được hỗ trợ và optimizer chọn index đó.

Sau khi tạo index, kiểm tra trạng thái:

~~~cypher
SHOW INDEXES
~~~

Index ở trạng thái `POPULATING` chưa thể phục vụ query. Chỉ khi trạng thái là `ONLINE`, index mới sẵn sàng sử dụng.

Để xác minh query có dùng point index hay không:

~~~cypher
EXPLAIN
MATCH (p:Place)
WHERE point.distance(p.location, point({longitude: 105.8342, latitude: 21.0278})) <= 5000
RETURN p
~~~

`EXPLAIN` hiển thị kế hoạch mà không thực thi truy vấn. `PROFILE` thực thi query và cung cấp số liệu thực tế. Hãy kiểm tra operator trong execution plan, số row được đọc và lượng dữ liệu mở rộng sau traversal. Không giả định rằng cứ có index là mọi truy vấn không gian sẽ tự động dùng index.

Một số nguyên tắc hiệu năng:

1. Lưu tọa độ thành `POINT`, không tính khoảng cách bằng công thức thủ công trên hai property số.
2. Tạo point index trên label/property được dùng trong truy vấn thường xuyên.
3. Dùng điều kiện radius hoặc bounding box ngay tại database để giảm số node trước khi hydrate entity.
4. Chỉ trả những node, relationship hoặc projection mà use case cần.
5. Kết hợp điều kiện thuộc tính có selectivity tốt và traversal hợp lý.
6. Dùng `EXPLAIN`/`PROFILE` với dữ liệu có quy mô gần production.
7. Theo dõi index state sau migration hoặc triển khai schema mới.

## 13. Polygon và bounding box

Spring Data Commons có kiểu `Polygon`, còn SDN cung cấp `BoundingBox.of(polygon)` để chuyển polygon thành hình chữ nhật bao quanh. Đây là cách thuận tiện cho truy vấn sơ bộ theo vùng:

Giả sử `polygon` đã được tạo từ các đỉnh theo đúng thứ tự và `placeRepository` là repository ở phần trước:

~~~java
import java.util.List;

import com.example.graph.domain.Place;
import com.example.graph.repository.PlaceRepository;
import org.springframework.data.geo.Polygon;
import org.springframework.data.neo4j.repository.query.BoundingBox;

BoundingBox box = BoundingBox.of(polygon);
List<Place> candidates = placeRepository.findByLocationWithin(box);
~~~

`BoundingBox` trả về góc dưới trái và trên phải. Nó không biểu diễn toàn bộ đường biên polygon. Nếu cần loại bỏ các điểm nằm trong hình chữ nhật nhưng ngoài polygon, cần thêm bước kiểm tra hình học chính xác bằng thư viện không gian hoặc custom logic phù hợp.

Đối với vùng địa lý đi qua kinh tuyến 180 độ, cần kiểm tra cách xây dựng polygon và bounding box. `point.withinBBox()` có quy tắc xử lý antimeridian riêng; không tự giả định một hình chữ nhật longitude luôn đi từ giá trị nhỏ sang lớn theo số học thông thường.

## 14. Phân biệt khoảng cách địa lý và khoảng cách theo mạng lưới

`point.distance()` tính khoảng cách đường chim bay giữa hai điểm. Nó không tính khoảng cách đi theo đường bộ, thời gian lái xe, tuyến đi bộ hoặc đường đi qua các node trong graph.

Ví dụ hai nhà hàng cách nhau 500 mét theo WGS-84 không có nghĩa người dùng chỉ cần đi bộ 500 mét. Sông, cầu, đường một chiều, đường cấm hoặc mạng lưới giao thông có thể làm đường đi thực tế dài hơn nhiều.

Chọn cách tính theo nhu cầu:

| Nhu cầu | Cách xử lý |
|---|---|
| Tìm địa điểm gần tọa độ nhất | `point.distance()` hoặc finder `Near` |
| Lọc điểm trong bán kính | `point.distance() <= radius` hoặc `Near` với `Distance` |
| Lọc điểm trong hình chữ nhật | `point.withinBBox()` hoặc finder `Within` |
| Tìm trong polygon chính xác | Spatial library hoặc custom geometry logic sau bước lọc sơ bộ |
| Tìm đường đi qua các tuyến đường/relationship | Traversal Cypher hoặc thuật toán đường đi trong graph |
| Tìm tuyến đường tối ưu theo trọng số | Neo4j Graph Data Science hoặc dịch vụ routing chuyên dụng |

Không dùng khoảng cách Euclidean trên longitude/latitude theo độ để thay thế khoảng cách địa lý. Một độ kinh độ không có cùng độ dài ở mọi vĩ độ, trong khi một độ vĩ độ cũng không tương đương một mét cố định.

## 15. Các lỗi thường gặp về CRS và tọa độ

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Địa điểm xuất hiện ở vị trí sai | Đảo longitude và latitude | Với WGS-84, dùng longitude trước latitude; kiểm tra cả constructor Java |
| Khoảng cách lớn bất thường | Dùng độ như thể là mét hoặc dùng Cartesian thay WGS-84 | Chọn CRS đúng và xác định đơn vị tọa độ |
| `point.distance()` trả `null` | Hai điểm khác CRS hoặc khác số chiều | Chuẩn hóa CRS và 2D/3D trước khi truy vấn |
| Query không tìm thấy điểm trong vùng | Lower-left/upper-right sai thứ tự hoặc CRS khác nhau | Kiểm tra góc tây nam, đông bắc và SRID |
| Derived finder `Near` không hoạt động như kỳ vọng | Property không dùng native Neo4j Driver `Point` | Dùng `org.neo4j.driver.types.Point` cho derived `Near` hoặc viết `@Query` |
| Điểm 3D không khớp truy vấn 2D | WGS-84 3D và WGS-84 2D là hai CRS khác nhau | Dùng cùng dimension hoặc chuyển đổi rõ ràng ngoài database |
| Index không được sử dụng | Index chưa `ONLINE` hoặc predicate không được hỗ trợ | Kiểm tra `SHOW INDEXES`, dùng predicate được point index hỗ trợ và xem `PROFILE` |
| Tính đường đi sai | Nhầm khoảng cách đường chim bay với đường đi trên mạng | Dùng graph traversal hoặc routing algorithm |
| Dữ liệu cùng property có CRS lẫn lộn | Không có quy ước thống nhất khi ingest | Chọn một CRS/dimension cho mỗi property và validate dữ liệu |

## 16. Kiểm thử truy vấn không gian

Một integration test nên xác minh cả mapping, CRS và kết quả truy vấn. Ví dụ chuẩn bị một vài địa điểm có tọa độ WGS-84:

~~~java
import java.util.List;

import com.example.graph.domain.Place;
import com.example.graph.repository.PlaceRepository;
import org.neo4j.driver.types.Point;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;

Point origin = GeoPoints.wgs84(105.8342, 21.0278);
Point nearby = GeoPoints.wgs84(105.8350, 21.0280);
Point farAway = GeoPoints.wgs84(106.7000, 10.8000);

placeRepository.saveAll(List.of(
    new Place("p-1", "Near place", nearby),
    new Place("p-2", "Far place", farAway)
));

List<Place> result = placeRepository.findByLocationNear(
    origin,
    new Distance(2, Metrics.KILOMETERS)
);
~~~

Test cần xác nhận:

- `location` được lưu và đọc lại dưới dạng `POINT` có SRID 4326.
- Tọa độ trả về giữ đúng longitude và latitude.
- Finder `Near` trả kết quả theo khoảng cách tăng dần.
- Điểm ngoài bán kính không xuất hiện.
- Query với CRS không khớp không âm thầm được xem là một phép tính hợp lệ.
- Point index đã `ONLINE` trước khi đánh giá hiệu năng.

Ngoài test repository, nên có test cho hàm tạo điểm Java để phát hiện lỗi đảo trục. Một test nhỏ xác nhận `Point.x()` là longitude và `Point.y()` là latitude có thể ngăn lỗi vị trí khó phát hiện ở production.

## 17. Nguyên tắc cần nhớ

- Lưu tọa độ dưới dạng Neo4j `POINT` nếu cần truy vấn không gian.
- WGS-84 2D dùng SRID 4326; WGS-84 3D dùng 4979; Cartesian 2D/3D dùng 7203/9157.
- WGS-84 nhận longitude trước latitude trong `point()` và `Values.point()`; `GeographicPoint2d` nhận latitude trước longitude.
- Khoảng cách WGS-84 trả về mét; khoảng cách Cartesian dùng đơn vị của tọa độ.
- Hai điểm cần cùng CRS và cùng số chiều để tính khoảng cách hoặc kiểm tra vùng.
- Spring Data Neo4j hỗ trợ `Near` và `Within`; derived `Near` được tài liệu hóa cho property dùng native Driver `Point`.
- Dùng `point.distance()` cho bán kính và thứ tự gần nhất; dùng `point.withinBBox()` cho vùng chữ nhật.
- Tạo point index cho property được truy vấn nhiều và xác nhận index ở trạng thái `ONLINE`.
- `point.distance()` là khoảng cách đường chim bay, không phải khoảng cách tuyến đường.
- Kiểm thử thứ tự tọa độ, CRS, đơn vị và execution plan trước khi triển khai dữ liệu lớn.

Khi xây dựng truy vấn không gian trong Spring Data Neo4j, hãy chọn CRS phù hợp với dữ liệu nguồn, giữ một quy ước tọa độ duy nhất và dùng đúng finder hoặc hàm Cypher cho nhu cầu. Kết hợp mapping `POINT`, truy vấn `Near`/`Within`, point index và kiểm thử CRS sẽ giúp ứng dụng tìm kiếm vị trí chính xác và hiệu quả.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.2 – Spatial types](https://docs.spring.io/spring-data/neo4j/reference/appendix/spatial-types.html)
- [Spring Data Neo4j 8.1.2 – Neo4jPoint API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/types/Neo4jPoint.html)
- [Spring Data Neo4j 8.2 – BoundingBox API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/query/BoundingBox.html)
- [Neo4j Cypher Manual – Spatial values and coordinate reference systems](https://neo4j.com/docs/cypher-manual/current/values-and-types/spatial/)
- [Neo4j Cypher Manual – Spatial functions](https://neo4j.com/docs/cypher-manual/current/functions/spatial/)
- [Neo4j Cypher Manual – Create indexes and point indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/)
- [Neo4j Java Driver – Data types and mapping to Cypher types](https://neo4j.com/docs/java-manual/current/data-types/)
- [Spring Data Commons – Distance API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/geo/Distance.html)
