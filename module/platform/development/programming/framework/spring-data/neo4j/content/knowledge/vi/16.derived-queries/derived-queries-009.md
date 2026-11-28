# Truy vấn theo vị trí và kiểm chứng từ khóa không gian được hỗ trợ

Ứng dụng dùng Neo4j thường cần tìm địa điểm gần một tọa độ, chẳng hạn cửa hàng quanh khách hàng, trạm xe gần điểm đón hoặc chi nhánh nằm trong một khu vực. Spring Data Neo4j (SDN) hỗ trợ một số **derived finder keywords** dành riêng cho dữ liệu không gian. Thay vì tự viết Cypher cho mọi truy vấn khoảng cách và vùng giới hạn, bạn có thể đặt tên phương thức repository theo các từ khóa mà SDN thực sự nhận diện.

Điều quan trọng là phân biệt cú pháp của SDN với hàm không gian trong Cypher. Trong derived query, hai từ khóa được tài liệu SDN hiện hành liệt kê là **Near** và **Within**. Chúng yêu cầu kiểu tham số và kiểu thuộc tính không gian phù hợp. Khi cần logic ngoài phạm vi này, hãy dùng **@Query** và các hàm Cypher như **point.distance()** hoặc **point.withinBBox()**.

Sau bài học, bạn có thể:

- Lưu tọa độ vào property kiểu POINT và chọn hệ tọa độ phù hợp.
- Khai báo derived finder với **Near** để tìm địa điểm quanh một điểm.
- Dùng **Distance** hoặc **Range<Distance>** để giới hạn khoảng cách.
- Dùng **Within** với **Circle**, **Box** hoặc **BoundingBox** để tìm điểm trong một vùng.
- Phân biệt kiểu **Point** dùng cho derived finder với các kiểu không gian khác SDN hỗ trợ chuyển đổi.
- Kiểm chứng truy vấn và chọn **@Query** khi yêu cầu vượt quá các từ khóa không gian được hỗ trợ.

## 1. Biểu diễn vị trí bằng POINT

Neo4j lưu tọa độ dưới dạng giá trị không gian **POINT**. Một điểm có hai hoặc ba tọa độ và luôn gắn với hệ quy chiếu tọa độ (CRS). Hệ quy chiếu xác định ý nghĩa của các con số và cách Neo4j tính khoảng cách.

Với vị trí địa lý trên bề mặt Trái Đất, ứng dụng thường dùng **WGS 84 2D**, có SRID **4326**. Hai tọa độ là kinh độ và vĩ độ theo độ thập phân:

- **longitude** (kinh độ) tương ứng trục **x**.
- **latitude** (vĩ độ) tương ứng trục **y**.
- Khoảng cách giữa hai điểm WGS 84 được tính theo đường địa cầu và trả về **mét**.

Một số CRS được Neo4j hỗ trợ:

| CRS | SRID | Số chiều | Trường hợp sử dụng |
|---|---:|---:|---|
| WGS 84 | 4326 | 2D | Vị trí địa lý bằng kinh độ, vĩ độ |
| WGS 84 3D | 4979 | 3D | Vị trí địa lý có thêm độ cao |
| Cartesian | 7203 | 2D | Tọa độ trên mặt phẳng với đơn vị do ứng dụng quy ước |
| Cartesian 3D | 9157 | 3D | Không gian Descartes ba chiều |

Không thể so sánh hoặc tính khoảng cách giữa hai điểm khác CRS hoặc khác số chiều. Ví dụ, một điểm WGS 84 2D không tương thích với điểm Cartesian 2D, dù cả hai đều có hai con số. Khi dùng dữ liệu địa lý, hãy thống nhất WGS 84 2D và thứ tự kinh độ trước, vĩ độ sau.

SDN hỗ trợ chuyển đổi một số kiểu không gian như Spring Data **Point**, **GeographicPoint2d**, **GeographicPoint3d**, **CartesianPoint2d** và **CartesianPoint3d**. Spring Data **Point** được hỗ trợ với điều kiện điểm trong database là WGS 84 2D/SRID 4326. Tuy nhiên, tài liệu derived finder quy định cụ thể: nếu muốn sử dụng **Near** và **Within** trong tên phương thức repository, property vị trí cần dùng kiểu native của Neo4j Java Driver là **org.neo4j.driver.types.Point**.

## 2. Khai báo entity có tọa độ

Giả sử ứng dụng quản lý cửa hàng. Mỗi cửa hàng có tên, mã nghiệp vụ và vị trí:

~~~java
package com.acme.graph.domain;

import org.neo4j.driver.types.Point;
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Venue")
public class Venue {

    @Id
    @GeneratedValue
    private Long id;

    private String venueCode;
    private String name;
    private String category;

    private Point location;

    // Constructor, getter và setter được lược bớt.
}
~~~

Property **location** được ánh xạ thành **POINT** trong Neo4j. Với kiểu native của Driver, ứng dụng có thể tạo giá trị WGS 84 2D bằng **Values.point(srid, x, y)**:

~~~java
import org.neo4j.driver.Values;
import org.neo4j.driver.types.Point;

double longitude = 106.7009;
double latitude = 10.7769;

Point location = Values.point(4326, longitude, latitude);
~~~

Trong ví dụ, **x** là kinh độ và **y** là vĩ độ. Không đảo hai giá trị khi tạo điểm. Khi lưu entity qua repository, SDN và Neo4j Java Driver sẽ chuyển giá trị **Point** thành property không gian.

## 3. Kiểm chứng các derived finder keywords được hỗ trợ

Tài liệu tham khảo chính thức của SDN hiện hành liệt kê hai nhóm từ khóa không gian cho derived finder:

| Keyword | Ý nghĩa | Kiểu tham số được hỗ trợ |
|---|---|---|
| **Near** | Tìm các entity có điểm ở gần một điểm tham chiếu | Native Neo4j Driver **Point**; có thể thêm **Distance** hoặc **Range<Distance>** |
| **Within** | Tìm các entity có điểm nằm trong một hình hoặc vùng giới hạn | **Circle**, **Box** hoặc **BoundingBox** |

Phần tên property trong phương thức phải khớp với property không gian của entity. Với property **location**, các phương thức cụ thể sẽ bắt đầu bằng **findByLocation**.

### 3.1. Near: tìm địa điểm gần một điểm

Phương thức đơn giản nhất:

~~~java
List<Venue> findByLocationNear(Point point);
~~~

Phương thức này tìm các **Venue** quanh điểm truyền vào và trả kết quả theo khoảng cách tăng dần đến điểm đó. Các địa điểm gần hơn được xếp trước.

Có thể giới hạn kết quả bằng một khoảng cách tối đa:

~~~java
List<Venue> findByLocationNear(Point point, Distance maxDistance);
~~~

Hoặc chỉ định một khoảng cách dạng khoảng:

~~~java
List<Venue> findByLocationNear(
    Point point,
    Range<Distance> between
);

List<Venue> findByLocationNear(
    Range<Distance> between,
    Point point
);
~~~

**Distance** biểu diễn khoảng cách có đơn vị đo. **Range<Distance>** cho phép mô tả một khoảng cách tối thiểu và tối đa theo API của Spring Data Commons. Với tọa độ WGS 84, hãy chú ý quy đổi đơn vị của **Distance** sang đúng ý nghĩa khoảng cách địa lý mà ứng dụng mong muốn.

### 3.2. Within: tìm địa điểm trong một vùng

**Within** dùng hình học làm tham số:

~~~java
List<Venue> findByLocationWithin(Circle circle);

List<Venue> findByLocationWithin(Box box);

List<Venue> findByLocationWithin(BoundingBox boundingBox);
~~~

- **Circle** mô tả vùng tròn bằng tâm và bán kính.
- **Box** mô tả vùng hình chữ nhật.
- **BoundingBox** là lớp tiện ích của SDN biểu diễn hình chữ nhật bằng điểm góc dưới trái và góc trên phải.

Tài liệu SDN cũng cho phép sử dụng **Polygon** bằng cách chuyển nó thành **BoundingBox** qua **BoundingBox.of(polygon)**. Cần hiểu giới hạn của cách này: **BoundingBox** là hình chữ nhật bao quanh polygon, không phải phép kiểm tra điểm nằm chính xác bên trong đường biên đa giác. Nếu yêu cầu nghiệp vụ cần kiểm tra chính xác trong polygon, hãy dùng một giải pháp không gian phù hợp riêng, chẳng hạn Cypher tùy chỉnh kết hợp thư viện không gian được ứng dụng hỗ trợ.

## 4. Khai báo repository hoàn chỉnh

Ví dụ repository dùng cả hai nhóm keyword:

~~~java
package com.acme.graph.repository;

import java.util.List;

import org.neo4j.driver.types.Point;
import org.springframework.data.domain.Range;
import org.springframework.data.geo.Box;
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Distance;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.BoundingBox;

import com.acme.graph.domain.Venue;

public interface VenueRepository
        extends Neo4jRepository<Venue, Long> {

    // Sắp xếp theo khoảng cách tăng dần tới điểm tham chiếu.
    List<Venue> findByLocationNear(Point point);

    // Chỉ lấy các địa điểm nằm trong khoảng cách tối đa.
    List<Venue> findByLocationNear(
        Point point,
        Distance maxDistance
    );

    // Lọc theo một khoảng cách.
    List<Venue> findByLocationNear(
        Point point,
        Range<Distance> between
    );

    // Lấy địa điểm nằm trong vùng tròn.
    List<Venue> findByLocationWithin(Circle circle);

    // Lấy địa điểm nằm trong vùng chữ nhật.
    List<Venue> findByLocationWithin(Box box);

    // Dùng BoundingBox được tạo sẵn.
    List<Venue> findByLocationWithin(BoundingBox boundingBox);
}
~~~

Tên property trong method phải khớp với property của entity. Nếu trường tọa độ được đặt tên **position**, method phải dùng **findByPositionNear(...)** hoặc **findByPositionWithin(...)**, không dùng **findByLocationNear(...)**.

Không cần viết **@Query** cho các mẫu trên. SDN phân tích tên phương thức, kiểu tham số và metadata entity để tạo truy vấn không gian tương ứng. Nếu parser không nhận diện được tên property hoặc kiểu tham số không đúng, repository có thể lỗi ngay khi Spring khởi tạo hoặc khi thực thi truy vấn.

## 5. Sử dụng repository trong service

Ví dụ tìm các cửa hàng gần vị trí hiện tại của khách hàng:

~~~java
package com.acme.graph.service;

import java.util.List;

import org.neo4j.driver.Values;
import org.neo4j.driver.types.Point;
import org.springframework.stereotype.Service;

import com.acme.graph.domain.Venue;
import com.acme.graph.repository.VenueRepository;

@Service
public class VenueSearchService {

    private final VenueRepository venueRepository;

    public VenueSearchService(VenueRepository venueRepository) {
        this.venueRepository = venueRepository;
    }

    public List<Venue> findNearby(
            double longitude,
            double latitude) {

        Point origin = Values.point(4326, longitude, latitude);
        return venueRepository.findByLocationNear(origin);
    }
}
~~~

Nếu chỉ muốn tìm cửa hàng trong bán kính 3 km, truyền **Distance** tối đa phù hợp vào overload **findByLocationNear**. Với dữ liệu WGS 84, Cypher tính khoảng cách địa lý bằng mét; vì vậy cần bảo đảm đơn vị của tham số khoảng cách được cấu hình đúng, tránh nhầm 3 km thành 3 m.

Khi tìm trong một vùng, service có thể nhận một **Circle**, **Box** hoặc **BoundingBox** đã được tạo từ tọa độ đầu vào rồi truyền cho phương thức **Within**. Việc tạo hình học nên được đặt ở tầng ứng dụng để kiểm tra tọa độ, bán kính và thứ tự các góc trước khi truy vấn.

## 6. Khi nào cần dùng @Query và Cypher?

Derived finder đáp ứng các truy vấn lân cận và vùng giới hạn cơ bản. Khi cần kết hợp nhiều điều kiện phức tạp, trả về projection riêng, tính toán khoảng cách trong kết quả hoặc điều khiển Cypher chi tiết, có thể dùng **@Query**.

### Tìm trong bán kính bằng point.distance()

~~~java
import java.util.List;

import org.neo4j.driver.types.Point;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    MATCH (v:Venue)
    WHERE point.distance(v.location, $origin) <= $maxDistanceMeters
    RETURN v
    ORDER BY point.distance(v.location, $origin)
    """)
List<Venue> findNearbyWithCypher(
    @Param("origin") Point origin,
    @Param("maxDistanceMeters") double maxDistanceMeters
);
~~~

**point.distance(a, b)** tính khoảng cách giữa hai điểm cùng CRS. Với WGS 84, kết quả là mét; với Cartesian, kết quả dùng cùng đơn vị với tọa độ. Hai điểm khác CRS hoặc khác số chiều không cho ra khoảng cách hợp lệ. Trong truy vấn trên, **origin** phải cùng CRS với **v.location**.

### Tìm trong hình chữ nhật bằng point.withinBBox()

~~~java
@Query("""
    MATCH (v:Venue)
    WHERE point.withinBBox(
        v.location,
        $lowerLeft,
        $upperRight
    )
    RETURN v
    """)
List<Venue> findInsideBoundingBox(
    @Param("lowerLeft") Point lowerLeft,
    @Param("upperRight") Point upperRight
);
~~~

**point.withinBBox(point, lowerLeft, upperRight)** trả về **true** khi điểm nằm trong bounding box. Với tọa độ địa lý, **lowerLeft** thường là góc tây nam và **upperRight** là góc đông bắc. Ba điểm phải cùng CRS. Nếu có giá trị **null** hoặc CRS không tương thích, hàm có thể trả về **null**, khiến điều kiện **WHERE** không chọn bản ghi đó.

Hai ví dụ này dùng **RETURN v** để SDN ánh xạ node **Venue** về entity. Nếu trả về các giá trị tính toán như khoảng cách, hãy dùng projection hoặc kiểu kết quả phù hợp với các alias trong **RETURN**.

## 7. Tạo point index và kiểm tra hiệu năng

Neo4j hỗ trợ point index để tối ưu các truy vấn trên property không gian. Với entity **Venue** và property **location**, có thể tạo index:

~~~cypher
CREATE POINT INDEX venue_location_point IF NOT EXISTS
FOR (v:Venue)
ON (v.location)
~~~

Point index được tối ưu cho điều kiện khoảng cách và truy vấn bounding box. Tuy nhiên, việc có index không tự bảo đảm mọi câu truy vấn đều sử dụng nó. Hãy kiểm tra kế hoạch bằng **EXPLAIN** và số liệu thực thi bằng **PROFILE** trên dữ liệu gần với quy mô thực tế:

~~~cypher
PROFILE
MATCH (v:Venue)
WHERE point.distance(
    v.location,
    point({longitude: $longitude, latitude: $latitude})
) <= $maxDistanceMeters
RETURN v
~~~

Khi đọc kế hoạch, kiểm tra operator truy cập index, số hàng được đọc và số hàng còn lại sau bộ lọc. Nếu truy vấn bắt đầu bằng một điều kiện khác có độ chọn lọc cao, kế hoạch tối ưu có thể chọn cách truy cập khác. Hãy đo trên dữ liệu thực thay vì mặc định rằng point index luôn là lựa chọn nhanh nhất.

## 8. Những giới hạn và lỗi thường gặp

**Dùng nhầm Point class.** SDN có hỗ trợ chuyển đổi Spring Data **Point**, nhưng tài liệu derived spatial finder yêu cầu property dùng native **org.neo4j.driver.types.Point**. Hãy kiểm tra import, nhất là khi IDE gợi ý hai lớp cùng tên.

**Đặt sai thứ tự tọa độ.** Với WGS 84 2D, **Values.point(4326, x, y)** nhận **x** là longitude và **y** là latitude. Nếu truyền latitude trước longitude, kết quả có thể nằm sai vị trí dù cú pháp vẫn hợp lệ.

**Trộn CRS hoặc số chiều.** Điểm lưu trong database và điểm truy vấn phải cùng CRS và số chiều. Không so sánh trực tiếp WGS 84 2D với Cartesian 2D hoặc WGS 84 3D.

**Nhầm đơn vị khoảng cách.** **point.distance()** với WGS 84 trả về mét. Nếu giao diện nhận km, hãy đổi km sang mét trước khi truyền vào Cypher hoặc dùng **Distance** với đơn vị đo phù hợp.

**Hiểu sai Polygon thành phép kiểm tra đa giác chính xác.** **BoundingBox.of(polygon)** chỉ chuyển polygon thành hình chữ nhật bao quanh. Các điểm nằm trong hình chữ nhật nhưng ngoài đường biên polygon vẫn có thể được trả về.

**Dùng tên keyword không có trong tài liệu SDN.** Với derived finder không gian, kiểm chứng **Near** và **Within** cùng kiểu tham số tương ứng. Các tên như **findWithinDistance(...)** trong API spatial cũ không phải là derived finder keyword hiện hành của **Neo4jRepository**.

**Bỏ qua dữ liệu tọa độ rỗng hoặc sai.** Điểm **null**, thiếu CRS phù hợp hoặc tọa độ không hợp lệ có thể khiến truy vấn không trả về kết quả mong đợi. Hãy xác thực đầu vào trước khi gọi repository.

## 9. Tự kiểm tra

1. Hai derived finder keywords không gian được SDN hiện hành hỗ trợ là gì?
2. Vì sao derived finder cần dùng **org.neo4j.driver.types.Point** cho property vị trí?
3. **findByLocationNear(Point point)** khác **findByLocationNear(Point point, Distance maxDistance)** ở điểm nào?
4. **Within** chấp nhận những kiểu tham số nào?
5. Vì sao **BoundingBox.of(polygon)** không tương đương kiểm tra một điểm nằm chính xác bên trong polygon?
6. **point.distance()** trả về đơn vị gì khi hai điểm dùng WGS 84?
7. Point index giúp ích cho loại truy vấn nào và cần kiểm tra việc sử dụng index ra sao?

**Bài tập thực hành:** Xây dựng **Venue** có property **location** kiểu native Neo4j Driver **Point** và **VenueRepository** kế thừa **Neo4jRepository<Venue, Long>**. Viết hai phương thức derived finder: một phương thức tìm địa điểm gần điểm tham chiếu và một phương thức tìm địa điểm trong **Circle**. Tạo một điểm WGS 84 bằng **Values.point(4326, longitude, latitude)**, gọi repository và so sánh kết quả khi có hoặc không có **Distance** tối đa. Sau đó viết một truy vấn **@Query** dùng **point.distance()** để lọc theo bán kính và kiểm tra kế hoạch bằng **PROFILE**.

## Tài liệu tham khảo

- [Spring Data Neo4j — Spatial types and derived finder keywords](https://docs.spring.io/spring-data/neo4j/reference/appendix/spatial-types.html)
- [Spring Data Neo4j API — BoundingBox](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/query/BoundingBox.html)
- [Neo4j Cypher Manual — Spatial values](https://neo4j.com/docs/cypher-manual/current/values-and-types/spatial/)
- [Neo4j Cypher Manual — Spatial functions](https://neo4j.com/docs/cypher-manual/current/functions/spatial/)
- [Neo4j Cypher Manual — Point indexes and query performance](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/using-indexes/)
- [Neo4j Java Driver Manual — Spatial types](https://neo4j.com/docs/java-manual/current/data-types/)
