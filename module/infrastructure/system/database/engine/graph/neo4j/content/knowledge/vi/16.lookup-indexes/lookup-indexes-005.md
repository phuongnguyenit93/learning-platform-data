# Point index và truy vấn dữ liệu không gian trong Neo4j

## 1. Bài toán: tìm thực thể gần một vị trí

Trong mô hình **property graph**, vị trí địa lý có thể là một thuộc tính của node hoặc relationship. Ví dụ, hệ thống giao nhận lưu node `PickupPoint` (điểm nhận hàng), node `Supplier` (đối tác) và quan hệ `(:Supplier)-[:SUPPLIES]->(:PickupPoint)`. Một yêu cầu thường gặp là:

> Từ tọa độ khách hàng, tìm những điểm nhận hàng trong bán kính 2 km, sắp xếp theo khoảng cách và trả về nhà cung cấp của từng điểm.

Nếu chỉ lưu `latitude` và `longitude` thành hai số rồi lọc mọi node, cơ sở dữ liệu có thể phải duyệt nhiều bản ghi và tính khoảng cách liên tục. **Point index** là chỉ mục dành riêng cho thuộc tính kiểu `POINT`, giúp Neo4j tìm các điểm thỏa điều kiện vị trí như **nằm trong bán kính** hoặc **nằm trong một hình chữ nhật giới hạn** (*bounding box*).

Trong chương **Chỉ mục tra cứu**, cần phân biệt:

| Loại chỉ mục | Dữ liệu được tra cứu | Ví dụ ứng dụng |
| --- | --- | --- |
| **Token lookup index** | Node label và relationship type | Tìm các node có label `PickupPoint`, các quan hệ kiểu `SUPPLIES` |
| **Range index** | Thuộc tính theo giá trị/miền giá trị; cũng hỗ trợ một số phép so sánh với `POINT` | Tìm `p.code = 'P001'`, `p.capacity > 10` |
| **Point index** | Thuộc tính `POINT`, tối ưu cho vị trí | `point.distance(...)`, `point.withinBBox(...)` |
| **Text index** | Thuộc tính `STRING` | Tìm tên có chứa chuỗi `'mart'` |

**Point index không phải token lookup index** dù cùng nằm trong chủ đề hệ thống index. Chỉ mục token hỗ trợ tìm label/type; point index hỗ trợ điều kiện không gian trên **thuộc tính**.

## 2. Kiểu dữ liệu `POINT` và hệ tọa độ

Neo4j biểu diễn vị trí bằng giá trị `POINT`: các tọa độ đi kèm **coordinate reference system** (CRS, hệ quy chiếu tọa độ). Hai nhóm phổ biến:

| CRS | Cách tạo | SRID | Diễn giải |
| --- | --- | --- | --- |
| **WGS 84 2D** | `point({longitude: 106.70, latitude: 10.78})` | `4326` | Kinh độ/vĩ độ trên Trái Đất; phù hợp GPS |
| **WGS 84 3D** | `point({longitude: 106.70, latitude: 10.78, height: 15.0})` | `4979` | Có thêm độ cao, tính bằng mét |
| **Cartesian 2D** | `point({x: 30.0, y: 40.0})` | `7203` | Mặt phẳng tọa độ do ứng dụng quy định |
| **Cartesian 3D** | `point({x: 30.0, y: 40.0, z: 5.0})` | `9157` | Không gian ba chiều do ứng dụng quy định |

Thử trực tiếp trong Neo4j Browser:

```cypher
RETURN
  point({longitude: 106.7000, latitude: 10.7800}) AS geographic,
  point({x: 30.0, y: 40.0}) AS cartesian;
```

Với WGS 84, **`longitude` là kinh độ, `latitude` là vĩ độ**. Nếu dùng cặp `x`/`y` mà không chỉ rõ CRS, Neo4j mặc định hiểu là tọa độ Cartesian; không thể coi `x=106.7, y=10.78` là kinh/vĩ độ địa lý nếu chưa xác định đúng CRS.

Neo4j hỗ trợ cả node và relationship có thuộc tính `POINT`. Một point có thể được lưu trực tiếp ở thuộc tính `p.location`:

```cypher
MERGE (p:PickupPoint {code: 'P001'})
SET p.name = 'Điểm nhận A',
    p.location = point({longitude: 106.7000, latitude: 10.7800})
RETURN p;
```

Khác với lưu tọa độ dạng chuỗi `'106.7,10.78'` hoặc một `LIST<FLOAT>`, lưu **giá trị `POINT` thực sự** cho phép dùng các hàm không gian và point index.

### Khoảng cách được tính theo đơn vị nào?

`point.distance(a, b)` trả về số thực nếu hai point cùng CRS:

- Với **WGS 84 2D/3D**, kết quả là **mét** (phép tính địa lý có xấp xỉ hình dạng Trái Đất).
- Với **Cartesian**, kết quả dùng **đơn vị của hệ tọa độ đầu vào**. Nếu `x, y` là pixel thì khoảng cách tính theo pixel, không tự biến thành mét.
- Với hai point **khác CRS** hoặc có đầu vào `null`, hàm có thể trả về `null`; không nên tự động hiểu đó là khoảng cách bằng 0.

```cypher
WITH
  point({x: 0.0, y: 0.0}) AS origin,
  point({x: 3.0, y: 4.0}) AS target
RETURN point.distance(origin, target) AS distanceInCoordinateUnits;
// 5.0 (đơn vị tọa độ Cartesian)
```

**Khoảng cách địa lý không phải khoảng cách đi đường.** Hai điểm cách nhau 500 m theo `point.distance` có thể cần đi đường bộ xa hơn vì cầu, sông, đường một chiều hoặc địa hình. Muốn tìm tuyến đi ngắn nhất trên graph đường sá, cần mô hình hóa các cạnh đường và dùng thuật toán đường đi phù hợp.

## 3. Tạo dữ liệu ví dụ

Giả sử các điểm nhận hàng giả lập có tọa độ quanh cùng khu vực. Chạy câu lệnh sau trên cơ sở dữ liệu thử nghiệm; `MERGE` theo mã để tránh tạo lặp node khi chạy lại:

```cypher
UNWIND [
  {code: 'P001', name: 'Điểm nhận A', longitude: 106.7000, latitude: 10.7800},
  {code: 'P002', name: 'Điểm nhận B', longitude: 106.7050, latitude: 10.7830},
  {code: 'P003', name: 'Điểm nhận C', longitude: 106.7200, latitude: 10.7950},
  {code: 'P004', name: 'Điểm nhận D', longitude: 106.6900, latitude: 10.7750}
] AS row
MERGE (p:PickupPoint {code: row.code})
SET p.name = row.name,
    p.location = point({
      longitude: row.longitude,
      latitude: row.latitude
    });
```

Hai lưu ý khi nhập dữ liệu:

1. Dữ liệu từ CSV hoặc JSON thường có tọa độ ở dạng `STRING`. Cần kiểm tra dữ liệu và chuyển về số trước khi gọi `point(...)`, ví dụ `toFloat(row.longitude)`.
2. Kiểm tra tọa độ nguồn có thực sự thuộc CRS đã chọn. Hoán đổi kinh độ và vĩ độ hoặc trộn hệ mét địa phương với WGS 84 có thể làm truy vấn trả về kết quả sai dù Cypher hợp lệ.

## 4. Tạo và quản lý point index

### 4.1. Point index trên thuộc tính node

```cypher
CREATE POINT INDEX idx_pickup_location IF NOT EXISTS
FOR (p:PickupPoint) ON (p.location);
```

Lệnh này tạo point index cho thuộc tính `location` của các node mang label `PickupPoint`. Chỉ các giá trị thuộc kiểu `POINT` mới được dùng cho tìm kiếm không gian trên chỉ mục này. Việc có index **không** biến một chuỗi hoặc hai thuộc tính số `latitude`, `longitude` thành point.

`IF NOT EXISTS` giúp lệnh tạo index có thể chạy lại khi index tương đương đã tồn tại; nó không phải lệnh kiểm chứng mọi cấu hình của index cũ.

### 4.2. Point index trên thuộc tính relationship

Relationship cũng có thể giữ tọa độ, chẳng hạn vị trí giao cắt của một đoạn đường:

```cypher
CREATE POINT INDEX idx_road_intersection IF NOT EXISTS
FOR ()-[r:ROAD_SEGMENT]-() ON (r.intersection);
```

Index trên relationship hoạt động với thuộc tính `POINT` của quan hệ có type phù hợp. Tuy nhiên, nếu `location` mô tả vị trí của một địa điểm trong thực tế, mô hình hóa nó thành thuộc tính **node địa điểm** thường dễ truy vấn và bảo trì hơn.

### 4.3. Kiểm tra index đã sẵn sàng

```cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties, state
WHERE name = 'idx_pickup_location'
RETURN name, type, entityType, labelsOrTypes, properties, state;
```

Kết quả mong đợi có `type = 'POINT'`, `properties = ['location']` và `state = 'ONLINE'`. Sau khi tạo index trên một graph lớn, Neo4j có thể cần thời gian *population* trước khi index chuyển sang `ONLINE`. `SHOW INDEXES` giúp xác định chỉ mục đã tồn tại và có sẵn cho query planner.

Khi cần xóa **index thử nghiệm**, có thể dùng:

```cypher
DROP INDEX idx_pickup_location IF EXISTS;
```

Trong cơ sở dữ liệu đang phục vụ người dùng, cần kiểm tra các truy vấn phụ thuộc trước khi xóa index.

### 4.4. Cấu hình miền tọa độ — chỉ khi có nhu cầu

Point index hỗ trợ cấu hình `indexConfig` với các cặp `min`/`max` riêng cho Cartesian 2D/3D và WGS 84 2D/3D. Ví dụ cho **tọa độ mặt phẳng**:

```cypher
CREATE POINT INDEX idx_site_position IF NOT EXISTS
FOR (s:Site) ON (s.position)
OPTIONS {
  indexConfig: {
    `spatial.cartesian.min`: [-10000.0, -10000.0],
    `spatial.cartesian.max`: [10000.0, 10000.0]
  }
};
```

Không tự đặt `spatial.cartesian.*` cho các giá trị kinh/vĩ độ WGS 84: đó là **hai hệ tọa độ khác nhau**. Khi không có nhu cầu tinh chỉnh đã đo đạc, hãy dùng cấu hình mặc định. Point index nhận **một thuộc tính** trong khai báo; không tạo composite point index trên `(latitude, longitude)`.

## 5. Ba kiểu truy vấn tận dụng point index

### 5.1. Tìm điểm nằm trong bán kính

Với điểm trung tâm tại kinh độ `106.7000`, vĩ độ `10.7800`, truy vấn các node trong bán kính 2.000 m:

```cypher
WITH point({longitude: 106.7000, latitude: 10.7800}) AS center
MATCH (p:PickupPoint)
WHERE point.distance(p.location, center) <= 2000
RETURN
  p.code AS code,
  p.name AS name,
  round(point.distance(p.location, center)) AS distanceMeters
ORDER BY distanceMeters ASC;
```

Trong truy vấn này:

- `MATCH (p:PickupPoint)` thu hẹp phạm vi theo label có index.
- `point.distance(p.location, center) <= 2000` là điều kiện **có thể được point index hỗ trợ**.
- `ORDER BY distanceMeters` sắp xếp kết quả phù hợp yêu cầu hiển thị. Việc dùng point index để lọc **không có nghĩa** kết quả tự được trả về theo khoảng cách gần nhất.

Ứng dụng thực tế nên truyền tọa độ và bán kính bằng tham số:

```cypher
WITH point({
  longitude: $longitude,
  latitude: $latitude
}) AS center
MATCH (p:PickupPoint)
WHERE point.distance(p.location, center) <= $radiusMeters
RETURN
  p.code AS code,
  p.name AS name,
  point.distance(p.location, center) AS distanceMeters
ORDER BY distanceMeters ASC
LIMIT 20;
```

Ví dụ bộ tham số:

```json
{
  "longitude": 106.7,
  "latitude": 10.78,
  "radiusMeters": 2000
}
```

Chỉ chọn một bán kính **dương, hợp lý với mục đích tìm kiếm**; nếu bán kính quá lớn so với phân bố dữ liệu, nhiều bản ghi vẫn phải được xử lý và sắp xếp.

### 5.2. Tìm điểm trong bounding box

`point.withinBBox(value, lowerLeft, upperRight)` kiểm tra một điểm có nằm trong hình chữ nhật được xác định bởi **góc dưới trái** và **góc trên phải** hay không:

```cypher
MATCH (p:PickupPoint)
WHERE point.withinBBox(
  p.location,
  point({longitude: 106.6900, latitude: 10.7700}),
  point({longitude: 106.7100, latitude: 10.7900})
)
RETURN p.code, p.name, p.location;
```

Với WGS 84, góc dưới trái thường là kinh độ nhỏ và vĩ độ nhỏ, góc trên phải là kinh độ lớn và vĩ độ lớn. Hàm có quy tắc riêng khi hộp đi qua kinh tuyến 180°; khi tìm kiếm trên phạm vi rộng hoặc gần đường đổi ngày quốc tế, cần kiểm thử đúng các trường hợp đó.

Bounding box hữu ích khi giao diện bản đồ yêu cầu: **“Tải các địa điểm trong khung bản đồ đang nhìn thấy.”** Kết quả là tập các điểm nằm trong khung chữ nhật; nếu muốn lọc chính xác theo **bán kính tròn**, hãy dùng `point.distance`.

### 5.3. So sánh với một giá trị `POINT` cụ thể

```cypher
MATCH (p:PickupPoint)
WHERE p.location = point({longitude: 106.7000, latitude: 10.7800})
RETURN p.code, p.name;
```

Point index hỗ trợ kiểm tra bằng nhau trên thuộc tính `POINT`. So sánh bằng nhau phù hợp dữ liệu có cùng tọa độ chuẩn hóa, nhưng với GPS đo thực tế, các sai lệch nhỏ giữa hai phép đo thường khiến phép bằng nhau không khớp; lúc đó điều kiện bán kính nhỏ thích hợp hơn.

## 6. Kết hợp truy vấn không gian với quan hệ đồ thị

Lợi thế của Neo4j nằm ở việc dùng cùng một truy vấn để **lọc theo vị trí** và **truy vấn liên kết**. Giả sử ta tạo hai nhà cung cấp giả lập:

```cypher
MERGE (s1:Supplier {id: 'S001'})
SET s1.name = 'Nhà cung cấp 1'
MERGE (s2:Supplier {id: 'S002'})
SET s2.name = 'Nhà cung cấp 2'
WITH s1, s2
MATCH (p1:PickupPoint {code: 'P001'})
MATCH (p2:PickupPoint {code: 'P002'})
MATCH (p3:PickupPoint {code: 'P003'})
MERGE (s1)-[:SUPPLIES]->(p1)
MERGE (s1)-[:SUPPLIES]->(p2)
MERGE (s2)-[:SUPPLIES]->(p3);
```

Sau đó truy vấn nhà cung cấp của những điểm nhận hàng gần khách:

```cypher
WITH point({longitude: $longitude, latitude: $latitude}) AS center
MATCH (p:PickupPoint)
WHERE point.distance(p.location, center) <= $radiusMeters
MATCH (s:Supplier)-[:SUPPLIES]->(p)
RETURN
  p.code AS pickupCode,
  p.name AS pickupName,
  s.name AS supplierName,
  round(point.distance(p.location, center)) AS distanceMeters
ORDER BY distanceMeters, pickupCode;
```

Query planner có thể sử dụng point index để tìm những `PickupPoint` phù hợp, sau đó mở rộng theo relationship `SUPPLIES`. **Point index không phải index cho quan hệ**: nó giúp lọc điểm theo vị trí, còn traversal sử dụng cấu trúc graph. Tối ưu truy vấn thực tế còn phụ thuộc dữ liệu, số node phù hợp và kế hoạch do planner chọn.

## 7. Kiểm tra query planner và tối ưu thực tế

### 7.1. `EXPLAIN` và `PROFILE`

Chỉ tạo index không đảm bảo Neo4j sẽ dùng nó cho mọi câu lệnh. Dùng `EXPLAIN` để xem kế hoạch mà không chạy truy vấn:

```cypher
EXPLAIN
MATCH (p:PickupPoint)
WHERE point.distance(
  p.location,
  point({longitude: 106.7000, latitude: 10.7800})
) <= 2000
RETURN p.code, p.name;
```

Khi cần **số liệu thực tế**, dùng `PROFILE` trên dữ liệu thử hoặc khung tải phù hợp:

```cypher
PROFILE
MATCH (p:PickupPoint)
WHERE point.withinBBox(
  p.location,
  point({longitude: 106.6900, latitude: 10.7700}),
  point({longitude: 106.7100, latitude: 10.7900})
)
RETURN p.code;
```

Quan sát các operator truy cập index, số `Rows`, `DB Hits` và phần lọc bổ sung. Tên operator hiển thị có thể khác theo phiên bản Neo4j. Với tập ví dụ chỉ có bốn node, việc planner dùng label scan thay vì point index **không nhất thiết là lỗi**; chi phí quét một tập cực nhỏ có thể thấp hơn dùng index.

### 7.2. Cách viết để có cơ hội dùng point index

| Truy vấn/thiết kế | Khả năng tận dụng point index |
| --- | --- |
| `MATCH (p:PickupPoint) WHERE point.distance(p.location, center) <= radius` | Phù hợp với predicate khoảng cách được hỗ trợ |
| `MATCH (p:PickupPoint) WHERE point.withinBBox(p.location, lo, hi)` | Phù hợp với predicate bounding box được hỗ trợ |
| `MATCH (p:PickupPoint) WHERE p.location = point(...)` | Phù hợp với predicate bằng nhau của kiểu `POINT` |
| `MATCH (p:PickupPoint) WHERE p.latitude > 10.7` | Không dùng point index trên `p.location`, vì truy vấn lọc thuộc tính số khác |
| `MATCH (p) WHERE point.distance(p.location, center) <= radius` | Thiếu label `PickupPoint`, planner có ít cơ sở để chọn point index theo label đó |
| `MATCH (p:PickupPoint) WHERE point.distance(point({longitude: p.lon, latitude: p.lat}), center) <= radius` | Tính point tại thời điểm truy vấn từ các thuộc tính khác, không trực tiếp tìm trên thuộc tính đã tạo point index |

Trong trường hợp nhiều index hoặc điều kiện chọn lọc cùng tồn tại, query planner quyết định đường truy cập dựa trên ước lượng chi phí. Cần đo trên tập dữ liệu tương đối giống production, với thông số đầu vào đại diện.

### 7.3. Những điều cần đo

- **Độ chọn lọc:** truy vấn trả 50 điểm trong 10 triệu điểm thường có lợi thế index rõ rệt hơn truy vấn trả 9 triệu điểm.
- **Trạng thái index:** đảm bảo `SHOW INDEXES` cho biết index `ONLINE`, đúng label và đúng thuộc tính.
- **Chi phí sau bước lọc:** `ORDER BY`, `LIMIT`, mở rộng nhiều quan hệ và `collect` vẫn có thể tiêu tốn tài nguyên.
- **Tính nhất quán CRS:** dữ liệu WGS 84 và điểm tìm kiếm phải thuộc CRS tương thích; không tự trộn point 2D với 3D.
- **Tần suất ghi:** index có chi phí lưu trữ và cập nhật khi ghi; nên tạo cho thuộc tính phục vụ truy vấn thường xuyên.

**Không so sánh point index với range/text index chỉ bằng thời gian chạy một lần**; dữ liệu cache, khối lượng bản ghi, tham số tìm kiếm và query plan đều ảnh hưởng kết quả.

## 8. Tích hợp Java Driver và Spring Data Neo4j

### 8.1. Java Driver: truyền tham số vào Cypher

Với Java Driver, có thể giữ tọa độ và bán kính ở dạng tham số để tái sử dụng truy vấn. Ví dụ sau giả sử ứng dụng đã có đối tượng `Driver driver` và cơ sở dữ liệu `neo4j`:

```java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

String cypher = """
    WITH point({
      longitude: $longitude,
      latitude: $latitude
    }) AS center
    MATCH (p:PickupPoint)
    WHERE point.distance(p.location, center) <= $radiusMeters
    RETURN p.code AS code,
           p.name AS name,
           point.distance(p.location, center) AS distanceMeters
    ORDER BY distanceMeters ASC
    LIMIT 20
    """;

Map<String, Object> params = Map.of(
    "longitude", 106.7,
    "latitude", 10.78,
    "radiusMeters", 2000.0
);

try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    List<Map<String, Object>> nearest = session.executeRead(tx ->
        tx.run(cypher, params)
          .list(record -> Map.<String, Object>of(
              "code", record.get("code").asString(),
              "name", record.get("name").asString(),
              "distanceMeters", record.get("distanceMeters").asDouble()
          ))
    );
    nearest.forEach(System.out::println);
}
```

`executeRead` phù hợp vì truy vấn chỉ đọc; driver quản lý transaction đọc và thực thi callback. Cần validate bán kính, tọa độ và quyền truy cập ở tầng API; không ghép trực tiếp chuỗi nhập từ người dùng vào Cypher.

### 8.2. Spring Data Neo4j

Khi dùng Spring Data Neo4j, có thể viết repository query với tham số `$longitude`, `$latitude`, `$radiusMeters` tương tự. Ví dụ về mặt ý tưởng:

```cypher
WITH point({longitude: $longitude, latitude: $latitude}) AS center
MATCH (p:PickupPoint)
WHERE point.distance(p.location, center) <= $radiusMeters
RETURN p
ORDER BY point.distance(p.location, center)
LIMIT 20
```

Khi ánh xạ entity, thuộc tính vị trí phải được lưu thành kiểu `POINT` thích hợp; lớp Java và bộ chuyển đổi dữ liệu cần tương thích với phiên bản Spring Data Neo4j đang dùng. Nếu cần trả thêm `distanceMeters`, thiết kế DTO/projection hoặc dùng `Neo4jClient` với cách ánh xạ kết quả rõ ràng. Đừng giả định rằng chỉ cần đặt tên field là `location` thì framework tự tạo point index: index cần được quản lý bằng schema migration hoặc lệnh tạo index tương ứng.

## 9. Lỗi phổ biến và cách xử lý

**1. Đảo kinh độ và vĩ độ.** Dữ liệu vẫn có thể là số hợp lệ nhưng vị trí nằm ở khu vực khác. Luôn giữ quy ước `longitude` trước, `latitude` sau khi đọc nguồn, tạo point và viết API.

**2. Lưu point thành `STRING` hoặc hai trường số rồi mong point index phát huy tác dụng.** Point index trên `p.location` chỉ hỗ trợ truy vấn trên giá trị `POINT` thực. Cần chuyển đổi và lưu vào đúng thuộc tính.

**3. Dùng `point.distance` giữa hai CRS khác nhau.** Kết quả có thể là `null`, khiến predicate `<= radius` không chọn dòng đó. Kiểm tra `p.location.crs`, SRID và cách tạo điểm tìm kiếm.

**4. Hiểu bán kính WGS 84 là độ.** `point.distance` với WGS 84 trả về mét; `2000` nghĩa là 2 km, không phải 2.000 độ. Với Cartesian, đơn vị là đơn vị tọa độ do hệ thống quy định.

**5. Dùng bounding box như thể đó là hình tròn.** `point.withinBBox` lọc theo hình chữ nhật; các góc hộp có thể nằm xa tâm hơn bán kính cần tìm. Có thể dùng bounding box để thu hẹp rồi lọc chính xác bằng `point.distance` khi phù hợp.

**6. Nghĩ index sẽ luôn được dùng.** Planner chọn kế hoạch theo chi phí; xem `PROFILE` trên dữ liệu đủ lớn và kiểm tra label, thuộc tính, trạng thái index, predicate.

**7. Dùng khoảng cách địa lý như thời gian di chuyển.** Khoảng cách đường chim bay không tính mạng đường, hướng lưu thông hoặc tốc độ. Khi cần tuyến đường, phải có graph đường sá hoặc dịch vụ định tuyến.

## 10. Bài tập tự kiểm tra

1. Mở rộng dữ liệu mẫu với `P005` có tọa độ WGS 84 2D. Tìm các điểm trong bán kính 1.000 m quanh `P001` và sắp xếp theo khoảng cách.
2. Viết truy vấn bounding box cho khung bản đồ `longitude` từ `106.695` đến `106.715`, `latitude` từ `10.775` đến `10.790`. So sánh tập kết quả với truy vấn bán kính.
3. Chạy `SHOW INDEXES`, `EXPLAIN` và `PROFILE` để xác định index hiện diện, đã `ONLINE` và planner có dùng nó hay không.
4. Thiết kế quan hệ giữa `PickupPoint` và `Supplier`. Viết truy vấn vừa lọc các điểm cách vị trí khách dưới 2 km vừa lấy tên nhà cung cấp.
5. Giải thích vì sao `point.distance(point({x: 0, y: 0}), point({x: 3, y: 4}))` không mặc định trả về khoảng cách tính bằng mét.

## 11. Ghi nhớ

- Dùng kiểu **`POINT`** với CRS đúng ngay từ lúc mô hình hóa tọa độ; tránh lưu vị trí chỉ dưới dạng chuỗi.
- Tạo **`CREATE POINT INDEX`** cho node hoặc relationship có thuộc tính vị trí được lọc thường xuyên. Đây là index cho **thuộc tính không gian**, khác token lookup index tra cứu label/type.
- Dùng **`point.distance`** cho tìm theo bán kính, **`point.withinBBox`** cho khung bản đồ, và so sánh bằng nhau cho các điểm đúng cùng tọa độ.
- **WGS 84 đo khoảng cách bằng mét**, Cartesian dùng đơn vị của hệ tọa độ; point index không tính tuyến đường ngắn nhất.
- Dùng **`SHOW INDEXES`**, **`EXPLAIN`** và **`PROFILE`** để kiểm tra schema và hiệu năng; kết hợp lọc không gian với traversal để khai thác thế mạnh của property graph.

### Tài liệu tham khảo

- [Neo4j Cypher Manual — Create indexes (Point indexes)](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/)
- [Neo4j Cypher Manual — Spatial functions](https://neo4j.com/docs/cypher-manual/current/functions/spatial/)
- [Neo4j Cypher Manual — Spatial values](https://neo4j.com/docs/cypher-manual/current/values-and-types/spatial/)
- [Neo4j Cypher Manual — The impact of indexes on query performance](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/using-indexes/)
