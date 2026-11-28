# Point, hệ tọa độ và dữ liệu không gian

Neo4j hỗ trợ kiểu dữ liệu `POINT` để lưu vị trí và tọa độ trực tiếp trên node hoặc relationship. Kiểu dữ liệu này cho phép ứng dụng biểu diễn địa điểm, thiết bị, kho hàng, tuyến giao nhận hoặc các đối tượng có vị trí trong không gian. Cypher cung cấp hàm tạo point, tính khoảng cách và kiểm tra một điểm nằm trong vùng giới hạn.

Khi dùng Spring Data Neo4j (SDN), ứng dụng có thể ghi và truy vấn dữ liệu không gian bằng Cypher trong repository hoặc `Neo4jClient`. Để kết quả chính xác, cần chọn đúng hệ tọa độ, hiểu thứ tự longitude/latitude và bảo đảm các điểm được so sánh thuộc cùng hệ tọa độ.

## 1. Point là kiểu dữ liệu không gian

Một point chứa tọa độ trong một hệ tọa độ tham chiếu (Coordinate Reference System, CRS). Neo4j hỗ trợ các hệ tọa độ Cartesian và WGS-84, ở dạng hai chiều hoặc ba chiều.

- **Cartesian:** biểu diễn tọa độ phẳng như `x`, `y` và có thể có `z`. Thường dùng cho sơ đồ mặt bằng, bản đồ nội bộ, lưới tọa độ hoặc mô hình không gian cục bộ.
- **WGS-84:** biểu diễn vị trí địa lý bằng `longitude` và `latitude`; dạng ba chiều có thêm `height`. Thường dùng cho GPS, bản đồ và dịch vụ vị trí trên Trái Đất.

Ví dụ tạo một node địa điểm với tọa độ địa lý:

```cypher
CREATE (p:Place {
    placeId: 'PL-001',
    name: 'Central Station',
    location: point({longitude: 105.8412, latitude: 21.0245})
})
RETURN p;
```

Property `location` là một giá trị point. Nó không phải một map chứa hai property độc lập; Cypher và Neo4j Driver nhận diện nó như dữ liệu không gian, nhờ đó có thể sử dụng các hàm không gian và point index.

Point cũng có thể được lưu trên relationship nếu vị trí thuộc về chính liên kết, chẳng hạn vị trí một lần ghi nhận thiết bị trên một tuyến đường. Hãy đặt point ở node hay relationship theo ý nghĩa của dữ liệu trong miền nghiệp vụ.

## 2. Cartesian và WGS-84

Neo4j nhận diện point thông qua CRS và SRID (Spatial Reference Identifier). Những hệ tọa độ thường gặp:

| Hệ tọa độ | Số chiều | SRID | Thành phần |
|---|---:|---:|---|
| Cartesian 2D | 2 | `7203` | `x`, `y` |
| Cartesian 3D | 3 | `9157` | `x`, `y`, `z` |
| WGS-84 2D | 2 | `4326` | `longitude`, `latitude` |
| WGS-84 3D | 3 | `4979` | `longitude`, `latitude`, `height` |

Với tọa độ địa lý WGS-84, thứ tự trường cần được ghi nhớ là **longitude trước, latitude sau**. Longitude thường nằm trong khoảng từ -180 đến 180 độ; latitude nằm trong khoảng từ -90 đến 90 độ.

```cypher
// WGS-84 2D
RETURN point({longitude: 105.8412, latitude: 21.0245}) AS location;

// Cartesian 2D
RETURN point({x: 12.5, y: 8.25}) AS position;

// Cartesian 3D
RETURN point({x: 12.5, y: 8.25, z: 3.0}) AS position3d;

// WGS-84 3D, height tính bằng mét
RETURN point({longitude: 105.8412, latitude: 21.0245, height: 12.0}) AS gps;
```

Neo4j có thể suy ra CRS từ các trường được cung cấp. Có thể truyền `crs` hoặc `srid` một cách tường minh khi cần kiểm soát hệ tọa độ. Không trộn `x/y` với `longitude/latitude` trong cùng một point.

Cartesian dùng đơn vị do ứng dụng quy ước, chẳng hạn mét trên sơ đồ nhà xưởng. WGS-84 dùng tọa độ góc; khoảng cách địa lý được tính theo mét. Đối với dữ liệu GPS, không được coi longitude và latitude là hai trục Cartesian rồi tự tính khoảng cách Euclid theo độ.

## 3. Đọc thông tin từ một point

Cypher cung cấp hàm `point()` để tạo point và có thể truy cập các thành phần tọa độ từ point đã lưu:

```cypher
MATCH (p:Place {placeId: 'PL-001'})
RETURN p.location AS location,
       p.location.longitude AS longitude,
       p.location.latitude AS latitude,
       point.srid(p.location) AS srid;
```

`point.srid()` trả về SRID của point. Việc kiểm tra SRID hữu ích khi dữ liệu đến từ nhiều nguồn hoặc khi một ứng dụng lưu cả vị trí địa lý lẫn tọa độ mặt bằng.

Có thể kiểm tra point có tồn tại trước khi truy cập thành phần tọa độ:

```cypher
MATCH (p:Place)
WHERE p.location IS NOT NULL
RETURN p.placeId, p.location.latitude, p.location.longitude;
```

Nếu một node chưa có property `location`, điều kiện `IS NOT NULL` giúp loại node đó khỏi kết quả. Khi nhận dữ liệu từ thiết bị hoặc API bên ngoài, nên xác thực giá trị tọa độ và CRS trước khi ghi vào graph.

## 4. Tính khoảng cách giữa hai điểm

Hàm `point.distance(point1, point2)` tính khoảng cách giữa hai point tương thích về CRS và số chiều.

Với WGS-84, kết quả khoảng cách là mét. Với Cartesian, kết quả theo đơn vị tọa độ mà ứng dụng sử dụng.

```cypher
WITH point({longitude: 105.8412, latitude: 21.0245}) AS station,
     point({longitude: 105.8542, latitude: 21.0285}) AS warehouse
RETURN point.distance(station, warehouse) AS distanceMeters;
```

Khi làm việc với GPS, cần bảo đảm cả hai point đều được tạo theo WGS-84. Nếu một điểm là Cartesian còn điểm kia là WGS-84, phép đo không thể được diễn giải như khoảng cách địa lý hợp lệ. Hãy chuẩn hóa dữ liệu về cùng CRS trước khi so sánh.

### Tìm địa điểm gần một tọa độ

Một use case phổ biến là tìm các địa điểm trong bán kính nhất định quanh vị trí người dùng:

```cypher
WITH point({longitude: $longitude, latitude: $latitude}) AS origin
MATCH (p:Place)
WHERE p.location IS NOT NULL
WITH p, point.distance(p.location, origin) AS distanceMeters
WHERE distanceMeters <= $radiusMeters
RETURN p.placeId AS placeId,
       p.name AS name,
       distanceMeters
ORDER BY distanceMeters;
```

Truy vấn nhận longitude, latitude và bán kính từ tham số. Điều kiện `distanceMeters <= $radiusMeters` giữ các địa điểm nằm trong bán kính, còn `ORDER BY` sắp xếp địa điểm gần nhất lên trước.

Không nối trực tiếp dữ liệu đầu vào vào chuỗi Cypher. Dùng tham số giúp truy vấn an toàn hơn, dễ tái sử dụng và cho phép driver gửi kiểu dữ liệu phù hợp.

## 5. Tìm point trong một vùng giới hạn

Nếu use case cần tìm điểm nằm trong hình chữ nhật bao quanh, có thể sử dụng `point.withinBBox(point, lowerLeft, upperRight)`. Hai điểm biên xác định góc dưới bên trái và góc trên bên phải của bounding box; các point phải cùng CRS.

Ví dụ với WGS-84:

```cypher
WITH point({longitude: 105.80, latitude: 20.99}) AS lowerLeft,
     point({longitude: 105.90, latitude: 21.08}) AS upperRight
MATCH (p:Place)
WHERE p.location IS NOT NULL
  AND point.withinBBox(p.location, lowerLeft, upperRight)
RETURN p.placeId, p.name, p.location;
```

Bounding box hữu ích khi lọc sơ bộ địa điểm trong một khu vực bản đồ. Nó biểu diễn vùng hình chữ nhật theo CRS; nó không đồng nghĩa với bán kính tròn. Nếu nghiệp vụ yêu cầu bán kính quanh tâm, dùng `point.distance()`.

Với vùng địa lý cắt qua kinh tuyến 180 độ, cần xử lý riêng việc xác định hai góc bounding box để không vô tình tạo vùng lớn ngược với ý định. Với dữ liệu Cartesian, bounding box tuân theo trục `x/y` của hệ tọa độ đó.

## 6. Lưu và cập nhật point bằng Spring Data Neo4j

SDN hỗ trợ thực hiện Cypher tùy chỉnh qua `@Query`. Khi muốn ghi tọa độ, có thể truyền các thành phần tọa độ thành tham số rồi tạo point trong Cypher:

```java
public interface NearbyPlaceView {
    String getPlaceId();
    String getName();
    Double getDistanceMeters();
}
```

```java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PlaceRepository extends Neo4jRepository<Place, String> {

    @Query("""
        MATCH (p:Place {placeId: $placeId})
        SET p.location = point({
            longitude: $longitude,
            latitude: $latitude
        })
        RETURN p.placeId
        """)
    String updateLocation(
            @Param("placeId") String placeId,
            @Param("longitude") double longitude,
            @Param("latitude") double latitude);

    @Query("""
        WITH point({longitude: $longitude, latitude: $latitude}) AS origin
        MATCH (p:Place)
        WHERE p.location IS NOT NULL
        WITH p, point.distance(p.location, origin) AS distanceMeters
        WHERE distanceMeters <= $radiusMeters
        RETURN p.placeId AS placeId,
               p.name AS name,
               distanceMeters AS distanceMeters
        ORDER BY distanceMeters
        """)
    List<NearbyPlaceView> findNearby(
            @Param("longitude") double longitude,
            @Param("latitude") double latitude,
            @Param("radiusMeters") double radiusMeters);
}
```

Ví dụ này cho thấy cách ghi một point WGS-84 mà không cần tự ghép chuỗi tọa độ, đồng thời trả về projection `NearbyPlaceView` cho truy vấn tìm địa điểm trong bán kính. Trong ứng dụng thực tế, hãy xác thực longitude và latitude ở tầng đầu vào, xử lý trường hợp `placeId` không tồn tại và chọn kiểu kết quả repository phù hợp với phiên bản SDN.

Khi cần đọc point nguyên bản, có thể dùng Neo4j Java Driver thông qua `Neo4jClient`. Driver cung cấp kiểu `org.neo4j.driver.types.Point`; `Value.asPoint()` lấy giá trị point từ record:

```java
import java.util.Optional;

import org.neo4j.driver.types.Point;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class PlaceLocationReader {

    private final Neo4jClient neo4jClient;

    public PlaceLocationReader(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public Optional<Point> findLocation(String placeId) {
        return neo4jClient.query("""
                MATCH (p:Place {placeId: $placeId})
                RETURN p.location AS location
                """)
                .bind(placeId).to("placeId")
                .fetchAs(Point.class)
                .mappedBy((typeSystem, record) -> record.get("location").asPoint())
                .one();
    }
}
```

Đoạn code minh họa việc đọc point native từ Driver. Nếu `location` có thể chưa tồn tại, cần xử lý giá trị null trước khi gọi `asPoint()` hoặc dùng projection trả về tọa độ nullable. Với entity mapping trực tiếp, hãy kiểm tra kiểu point được hỗ trợ bởi phiên bản SDN và Neo4j Java Driver của dự án; có thể dùng converter khi mô hình miền cần một kiểu tọa độ riêng.

## 7. Tạo point index và tối ưu truy vấn

Khi số lượng địa điểm lớn, point index có thể hỗ trợ các truy vấn không gian phù hợp. Ví dụ tạo point index cho property `location` của node `Place`:

```cypher
CREATE POINT INDEX place_location IF NOT EXISTS
FOR (p:Place) ON (p.location);
```

Point index được thiết kế cho dữ liệu point và các predicate không gian được Neo4j hỗ trợ, chẳng hạn truy vấn theo khoảng cách hoặc bounding box. Việc tạo index không đảm bảo mọi truy vấn có `point.distance()` đều sử dụng index; planner còn phụ thuộc dạng predicate, phiên bản Neo4j, thống kê và độ chọn lọc dữ liệu.

Kiểm tra kế hoạch bằng `EXPLAIN` trước khi chạy và `PROFILE` khi cần số liệu thực tế:

```cypher
EXPLAIN
WITH point({longitude: 105.8412, latitude: 21.0245}) AS origin
MATCH (p:Place)
WHERE point.distance(p.location, origin) <= 2000
RETURN p.placeId, p.name;
```

Khi đọc kế hoạch, xem operator được dùng để tìm node và lọc point. Nếu truy vấn vẫn quét nhiều node, kiểm tra index đã online chưa, property có đúng kiểu point không, predicate có tương thích với point index không và truy vấn có điều kiện chọn lọc phù hợp hay không.

Một số nguyên tắc tối ưu:

1. Dùng point index cho property point được truy vấn không gian thường xuyên.
2. Giữ cùng CRS và số chiều cho các point trong cùng use case.
3. Giới hạn label và các điều kiện nghiệp vụ cần thiết trong pattern.
4. Chỉ trả về property cần dùng, tránh truyền cả node hoặc đường đi lớn nếu không cần.
5. Đo bằng `PROFILE` với phân bố dữ liệu và số lượng node gần với production.

## 8. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Đảo longitude và latitude | Vị trí bị đặt sai, đôi khi vẫn nằm trong miền giá trị hợp lệ nên khó phát hiện | Dùng thứ tự longitude trước, latitude sau cho WGS-84 |
| Dùng point Cartesian để tính khoảng cách GPS | Kết quả không biểu diễn khoảng cách địa lý | Dùng WGS-84 cho tọa độ địa lý |
| So sánh point khác CRS hoặc số chiều | Không thể tạo phép đo khoảng cách có ý nghĩa | Chuẩn hóa CRS và chiều trước khi tính |
| Coi longitude/latitude là mét | Bán kính tìm kiếm sai quy mô | Dùng `point.distance()` cho WGS-84, kết quả tính bằng mét |
| Dùng bounding box khi nghiệp vụ yêu cầu bán kính | Có thể lấy thêm điểm ở các góc của hình chữ nhật | Kết hợp `point.distance()` để lọc theo bán kính |
| Không kiểm tra tọa độ đầu vào | Lưu vị trí sai hoặc dữ liệu không hợp lệ | Kiểm tra miền longitude/latitude và nguồn CRS |
| Nghĩ rằng point index tự động tối ưu mọi truy vấn | Truy vấn vẫn có thể quét nhiều node | Dùng `EXPLAIN`/`PROFILE` xác minh planner |

## 9. Bài tập thực hành

Tạo một số địa điểm với point WGS-84:

```cypher
CREATE
  (:Place {placeId: 'PL-001', name: 'Station A',
           location: point({longitude: 105.8412, latitude: 21.0245})}),
  (:Place {placeId: 'PL-002', name: 'Warehouse B',
           location: point({longitude: 105.8542, latitude: 21.0285})}),
  (:Place {placeId: 'PL-003', name: 'Office C',
           location: point({longitude: 105.8000, latitude: 21.0100})});
```

Thực hiện các yêu cầu:

1. Truy vấn `longitude`, `latitude` và SRID của từng địa điểm.
2. Tính khoảng cách từ `Station A` đến các địa điểm còn lại bằng `point.distance()`.
3. Tìm địa điểm trong bán kính 2.000 mét quanh `Station A` và sắp xếp theo khoảng cách.
4. Tìm địa điểm trong một bounding box quanh khu vực đang khảo sát bằng `point.withinBBox()`.
5. Tạo point index trên `Place.location`, chạy `EXPLAIN` và so sánh kế hoạch truy vấn trước và sau khi tạo index.
6. Viết repository method trong SDN nhận longitude, latitude và bán kính làm tham số, trả về projection gồm mã địa điểm, tên và khoảng cách.

Khi hoàn thành, cần giải thích được vì sao point WGS-84 dùng longitude/latitude, vì sao khoảng cách địa lý được trả về theo mét, và vì sao point index cần được kiểm chứng bằng kế hoạch thực thi thay vì chỉ dựa vào việc index đã được tạo.

## Kết luận

Neo4j `POINT` lưu tọa độ có CRS rõ ràng và hỗ trợ truy vấn không gian ngay trong Cypher. WGS-84 phù hợp với dữ liệu địa lý, còn Cartesian phù hợp với hệ tọa độ phẳng do ứng dụng quy ước. `point.distance()` phục vụ tìm kiếm theo bán kính, `point.withinBBox()` lọc theo vùng chữ nhật và point index hỗ trợ tăng tốc các predicate không gian phù hợp. Trong Spring Data Neo4j, có thể ghi point qua `@Query`, đọc point native qua `Neo4jClient` hoặc ánh xạ bằng converter phù hợp. Luôn xác thực tọa độ, thống nhất CRS và đo hiệu năng bằng `EXPLAIN`/`PROFILE`.
