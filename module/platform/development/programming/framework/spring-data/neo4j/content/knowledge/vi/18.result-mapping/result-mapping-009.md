# Khi nào chuyển sang mapping tùy chỉnh bằng Neo4jClient?

Spring Data Neo4j (SDN) có thể ánh xạ kết quả truy vấn repository thành entity, projection hoặc kiểu kết quả đơn giản. Với nhiều use case, cách mapping có sẵn này đã đủ rõ ràng và dễ bảo trì. Tuy nhiên, có những truy vấn trả về dữ liệu tổng hợp, giá trị tính toán, cấu trúc lồng nhau hoặc kiểu dữ liệu cần chuyển đổi theo quy tắc riêng. Khi đó, `Neo4jClient` cho phép ứng dụng kiểm soát cách từng record Cypher được chuyển thành đối tượng Java.

Quyết định chuyển sang mapping tùy chỉnh nên dựa trên hình dạng dữ liệu đầu ra và yêu cầu chuyển đổi. `Neo4jClient` không tự làm truy vấn nhanh hơn; lợi ích chính là kiểm soát kết quả, tránh nạp entity graph không cần thiết và ánh xạ chính xác dữ liệu mà use case cần.

## 1. Bắt đầu với mapping mặc định của repository

Khi truy vấn trả về node phù hợp với entity đã khai báo, repository method cùng `@Query` thường là lựa chọn đơn giản nhất:

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository extends Neo4jRepository<Product, String> {

    @Query("""
        MATCH (p:Product {sku: $sku})
        RETURN p
        """)
    Optional<Product> findProduct(@Param("sku") String sku);
}
```

Truy vấn trả về node `Product`, vì vậy SDN có thể dùng metadata của entity để ánh xạ property và relationship đã khai báo. Nếu kết quả là một tập trường đơn giản, projection cũng có thể đáp ứng:

```java
public interface ProductNameView {
    String getSku();
    String getName();
}
```

```java
@Query("""
    MATCH (p:Product {sku: $sku})
    RETURN p.sku AS sku, p.name AS name
    """)
Optional<ProductNameView> findName(@Param("sku") String sku);
```

Khi alias trong `RETURN` khớp với accessor của projection và kiểu dữ liệu tương thích, mapping mặc định giữ cho repository ngắn gọn. Không cần đưa `Neo4jClient` vào chỉ để thay đổi tên một vài cột hoặc đọc một entity bình thường.

## 2. Dấu hiệu cho thấy cần mapping tùy chỉnh

Hãy cân nhắc `Neo4jClient` khi kết quả Cypher khác đáng kể với cấu trúc entity hoặc cần logic chuyển đổi cụ thể:

1. **Kết quả tổng hợp:** truy vấn trả về `count`, `sum`, `collect`, khoảng cách hoặc điểm xếp hạng thay vì một node entity.
2. **Nhiều hình dạng dữ liệu trong một record:** một dòng gồm thông tin node, property relationship, danh sách giá trị và các chỉ số tính toán.
3. **Cấu trúc lồng nhau:** kết quả có danh sách map, nhóm con hoặc dữ liệu được gom theo một khóa.
4. **Chuyển đổi kiểu đặc thù:** cần xử lý `null`, kiểu temporal, point, duration hoặc kiểu Java riêng.
5. **Mapping theo quy tắc ứng dụng:** cần chuẩn hóa, đổi đơn vị, áp dụng fallback hoặc kết hợp nhiều trường thành một value object.
6. **Chỉ cần dữ liệu đọc chuyên biệt:** không muốn nạp cả entity graph chỉ để dựng báo cáo hoặc màn hình.

Nếu chỉ cần entity hoặc projection đơn giản, hãy ưu tiên mapping repository. Nếu phải viết nhiều đoạn chuyển đổi phức tạp trong service sau khi nhận `Map<String, Object>`, chuyển logic đó vào một mapper tường minh qua `Neo4jClient` có thể làm ý định rõ hơn.

## 3. `Neo4jClient` kiểm soát mapping ở cấp record

`Neo4jClient` là API của SDN dựa trên Neo4j Java Driver. Ứng dụng có thể viết Cypher, bind tham số và chỉ định cách chuyển mỗi record thành kiểu Java:

```java
neo4jClient.query("RETURN 1 AS value")
        .fetchAs(Long.class)
        .mappedBy((typeSystem, record) -> record.get("value").asLong())
        .one();
```

Các bước chính:

- `query(...)` khai báo câu Cypher.
- `bind(value).to("name")` truyền dữ liệu vào placeholder `$name`.
- `fetchAs(Target.class)` khai báo kiểu Java của kết quả.
- `mappedBy(...)` nhận callback cho từng record, cho phép đọc cột và tạo đối tượng đích.
- `one()` yêu cầu truy vấn trả về không quá một record và trả về `Optional<T>`; nếu có nhiều record, API báo lỗi kích thước kết quả. Dùng `all()` khi truy vấn được phép trả về nhiều record.

Callback nhận `TypeSystem` và `Record`. `Record` chứa các giá trị trả về theo alias; mỗi giá trị được đọc thông qua `record.get("alias")` rồi chuyển kiểu bằng các phương thức như `asString()`, `asLong()`, `asBoolean()` hoặc `asLocalDate()`.

## 4. Ví dụ: ánh xạ kết quả tổng hợp thành DTO

Giả sử màn hình catalog cần mã sản phẩm, tên, giá và danh sách tên danh mục. Kết quả này không cần entity graph đầy đủ, mà là một DTO dành cho use case đọc.

Định nghĩa record Java:

```java
import java.util.List;

public record ProductSummary(
        String sku,
        String name,
        Long priceMinor,
        List<String> categories) {
}
```

Repository hoặc component đọc dữ liệu dùng `Neo4jClient`:

```java
import java.util.Optional;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class ProductSummaryReader {

    private final Neo4jClient neo4jClient;

    public ProductSummaryReader(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public Optional<ProductSummary> findSummary(String sku) {
        return neo4jClient.query("""
                MATCH (p:Product {sku: $sku})
                OPTIONAL MATCH (p)-[:IN_CATEGORY]->(c:Category)
                RETURN p.sku AS sku,
                       p.name AS name,
                       p.priceMinor AS priceMinor,
                       collect(DISTINCT c.name) AS categories
                """)
                .bind(sku).to("sku")
                .fetchAs(ProductSummary.class)
                .mappedBy((typeSystem, record) -> {
                    var priceValue = record.get("priceMinor");
                    Long priceMinor = priceValue.isNull()
                            ? null
                            : priceValue.asLong();

                    return new ProductSummary(
                            record.get("sku").asString(),
                            record.get("name").asString(),
                            priceMinor,
                            record.get("categories").asList(value -> value.asString())
                    );
                })
                .one();
    }
}
```

Ở đây:

- `sku` xác định sản phẩm; cần có uniqueness constraint nếu nghiệp vụ yêu cầu mỗi SKU chỉ có một node.
- `OPTIONAL MATCH` cho phép sản phẩm chưa được gắn danh mục vẫn xuất hiện trong kết quả.
- `collect(DISTINCT c.name)` gom tên danh mục thành một danh sách và loại giá trị trùng.
- `priceMinor` được kiểm tra `null` trước khi đọc thành `long`, tránh gọi phép chuyển đổi trên giá trị rỗng.
- Callback tạo `ProductSummary` từ đúng các alias mà Cypher trả về.

DTO này không phải entity và không được SDN lưu ngược xuống Neo4j. Nó biểu diễn kết quả đọc theo nhu cầu của màn hình. Đơn vị giá được giữ là đơn vị nhỏ nhất do ứng dụng quy ước để tránh làm tròn số tiền khi chuyển đổi.

## 5. Ánh xạ nhiều record thành collection

Nếu truy vấn trả về nhiều dòng, callback trong `mappedBy` vẫn chuyển từng record thành một đối tượng. Dùng `all()` để nhận tập kết quả:

```java
import java.util.Collection;

public Collection<ProductSummary> findAllSummaries() {
    return neo4jClient.query("""
            MATCH (p:Product)
            OPTIONAL MATCH (p)-[:IN_CATEGORY]->(c:Category)
            RETURN p.sku AS sku,
                   p.name AS name,
                   p.priceMinor AS priceMinor,
                   collect(DISTINCT c.name) AS categories
            ORDER BY p.name
            """)
            .fetchAs(ProductSummary.class)
            .mappedBy((typeSystem, record) -> {
                var priceValue = record.get("priceMinor");
                Long priceMinor = priceValue.isNull() ? null : priceValue.asLong();

                return new ProductSummary(
                        record.get("sku").asString(),
                        record.get("name").asString(),
                        priceMinor,
                        record.get("categories").asList(value -> value.asString())
                );
            })
            .all();
}
```

Nếu logic mapping được dùng ở nhiều nơi, tách callback thành một phương thức hoặc component mapper riêng để tránh lặp mã. Cũng cần xác định thứ tự kết quả trong Cypher bằng `ORDER BY`; không dựa vào thứ tự ngẫu nhiên của graph.

## 6. Ánh xạ giá trị null và kiểu dữ liệu đặc biệt

Neo4j Driver biểu diễn dữ liệu trả về bằng `Value`. Không phải mọi cột đều có giá trị ở mọi record, nhất là khi dùng `OPTIONAL MATCH`. Trước khi gọi `asString()`, `asLong()` hoặc phương thức chuyển kiểu khác, hãy xác định cột có thể null hay không.

Ví dụ với ngày:

```java
var dateValue = record.get("createdOn");
LocalDate createdOn = dateValue.isNull()
        ? null
        : dateValue.asLocalDate();
```

Với boolean:

```java
var activeValue = record.get("active");
Boolean active = activeValue.isNull()
        ? null
        : activeValue.asBoolean();
```

Với point, Neo4j Driver cung cấp kiểu `org.neo4j.driver.types.Point`. Có thể đọc bằng `asPoint()` sau khi kiểm tra null, rồi chuyển tọa độ sang value object của ứng dụng:

```java
var locationValue = record.get("location");
Point location = locationValue.isNull()
        ? null
        : locationValue.asPoint();
```

Các kiểu temporal và spatial cần được chuyển đổi có chủ đích. Không chuyển mọi giá trị thành chuỗi nếu ứng dụng cần tính toán ngày giờ, khoảng cách hoặc so sánh tọa độ sau khi mapping.

## 7. Ánh xạ cấu trúc lồng nhau

Khi Cypher trả về một map hoặc danh sách map, `Neo4jClient` cho phép đọc từng phần tử và chuyển thành cấu trúc Java phù hợp. Ví dụ, một khách hàng cùng danh sách đơn hàng gần nhất:

```cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:PurchaseOrder)
RETURN c.customerId AS customerId,
       c.name AS customerName,
       collect({
           orderId: o.orderId,
           status: o.status
       }) AS orders;
```

Vì `OPTIONAL MATCH` có thể không tìm thấy đơn hàng, map được thu thập có thể chứa các giá trị null. Có thể lọc các phần tử không có `orderId` ngay trong Cypher bằng list comprehension:

```cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:PurchaseOrder)
RETURN c.customerId AS customerId,
       c.name AS customerName,
       [x IN collect({orderId: o.orderId, status: o.status})
        WHERE x.orderId IS NOT NULL] AS orders;
```

Khi nhận kết quả, có thể đọc `orders` thành danh sách map rồi chuyển mỗi map thành DTO con. Với cấu trúc lồng nhau sâu, nên tách hàm mapping cho từng cấp để dễ kiểm tra và xử lý null.

Không nên gom một graph quá lớn thành một map duy nhất nếu use case chỉ cần vài trường. `collect()` có thể làm tăng bộ nhớ của database và ứng dụng khi số phần tử lớn. Hãy giới hạn số lượng, phân trang hoặc tách truy vấn theo nhu cầu.

## 8. Giữ mapping trong một lớp riêng

Khi callback mapping có nhiều nhánh, việc đặt toàn bộ logic trong repository hoặc service khiến lớp đó khó đọc. Có thể tạo mapper chuyên biệt:

```java
import org.neo4j.driver.Record;
import org.springframework.stereotype.Component;

@Component
public class ProductSummaryMapper {

    public ProductSummary map(Record record) {
        var priceValue = record.get("priceMinor");
        Long priceMinor = priceValue.isNull() ? null : priceValue.asLong();

        return new ProductSummary(
                record.get("sku").asString(),
                record.get("name").asString(),
                priceMinor,
                record.get("categories").asList(value -> value.asString())
        );
    }
}
```

Sau đó dùng mapper trong `mappedBy`:

```java
.fetchAs(ProductSummary.class)
.mappedBy((typeSystem, record) -> productSummaryMapper.map(record))
.all();
```

Mapper nhận `Record` và chịu trách nhiệm chuyển dữ liệu đã truy vấn thành DTO. Nó không nên thực hiện thêm truy vấn database cho từng record; nếu làm vậy, ứng dụng dễ gặp N+1 query và thời gian phản hồi tăng theo số dòng.

## 9. `Neo4jClient` và transaction

`Neo4jClient` được Spring quản lý và tích hợp với hạ tầng Neo4j của ứng dụng. Nếu truy vấn đọc hoặc ghi cần tham gia cùng transaction với repository khác, hãy gọi chúng trong cùng phương thức service được đánh dấu `@Transactional` và sử dụng transaction manager Neo4j đã cấu hình.

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductReadService {

    private final ProductSummaryReader summaries;

    public ProductReadService(ProductSummaryReader summaries) {
        this.summaries = summaries;
    }

    @Transactional(readOnly = true)
    public ProductSummary getSummary(String sku) {
        return summaries.findSummary(sku)
                .orElseThrow(() -> new IllegalArgumentException("Product not found"));
    }
}
```

Ví dụ này cho thấy transaction boundary ở tầng service. Tùy cấu hình và phiên bản Spring, `readOnly = true` có thể được dùng như gợi ý cho transaction; không coi nó là cơ chế tự động tối ưu mọi truy vấn. Với thao tác ghi, dùng transaction phù hợp và không đánh dấu read-only.

## 10. Những trường hợp chưa cần chuyển sang Neo4jClient

Giữ mapping mặc định khi:

- Truy vấn trả về một entity hoặc collection entity có mapping rõ ràng.
- Một interface projection hoặc DTO projection đã đáp ứng đầy đủ shape kết quả.
- Không cần chuyển đổi kiểu đặc biệt hoặc xử lý từng cột theo logic riêng.
- Query đơn giản và việc thêm callback mapping chỉ làm code dài hơn.

Chuyển sang `Neo4jClient` khi callback mapping giải quyết một yêu cầu cụ thể: kết quả tổng hợp, cấu trúc lồng nhau, kiểu Driver, chuyển đổi null, hoặc dữ liệu đọc không phải entity. Không nên chọn `Neo4jClient` chỉ vì muốn dùng Cypher tùy chỉnh; repository `@Query` cũng hỗ trợ custom Cypher.

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng entity để nhận kết quả chỉ gồm vài cột | Mapping thiếu dữ liệu hoặc không phù hợp với entity graph | Dùng projection hoặc DTO |
| Alias trong `RETURN` không khớp tên đọc trong mapper | `Record` không có key mong đợi | Thống nhất alias giữa Cypher và callback |
| Gọi `asLong()` hoặc `asString()` khi giá trị null | Lỗi chuyển đổi lúc runtime | Kiểm tra `Value.isNull()` trước |
| Dùng `collect()` cho tập dữ liệu rất lớn | Tăng bộ nhớ và thời gian xử lý | Giới hạn, phân trang hoặc tách truy vấn |
| Thực hiện truy vấn mới trong callback cho từng record | Tạo N+1 query | Trả về đủ dữ liệu trong truy vấn ban đầu hoặc batch theo nhóm |
| Tưởng mapping tùy chỉnh tự tăng tốc Cypher | Hiệu năng truy vấn không đổi nếu kế hoạch vẫn như cũ | Tối ưu Cypher, index và kiểm tra `PROFILE` |
| Không bind tham số | Rủi ro injection và lỗi escape dữ liệu | Dùng `.bind(value).to("name")` |
| Đưa logic nghiệp vụ phức tạp vào mapper | Khó kiểm thử và khó tái sử dụng | Mapper chỉ chuyển đổi dữ liệu; xử lý nghiệp vụ ở service/domain layer |

## 12. Quy trình quyết định

Trước khi chuyển một repository query sang `Neo4jClient`, hãy tự trả lời:

1. Kết quả có phải entity được SDN quản lý không?
2. Projection mặc định có thể nhận đủ các cột với alias rõ ràng không?
3. Có cần chuyển kiểu, xử lý null hoặc dựng cấu trúc lồng nhau theo logic riêng không?
4. Có thể trả về đúng dữ liệu cần thiết bằng một truy vấn mà không nạp cả graph không?
5. Mapper có thể thuần chuyển đổi từng record mà không gọi thêm database không?
6. Query có được tham số hóa và có kế hoạch thực thi phù hợp không?

Nếu mapping mặc định đã rõ và đúng, tiếp tục dùng repository. Nếu kết quả cần điều khiển chi tiết ở cấp record, dùng `Neo4jClient` với mapper có tên và có thể kiểm thử độc lập.

## 13. Bài tập thực hành

Tạo một truy vấn trả về thông tin sản phẩm cùng danh sách danh mục:

```cypher
MATCH (p:Product {sku: $sku})
OPTIONAL MATCH (p)-[:IN_CATEGORY]->(c:Category)
RETURN p.sku AS sku,
       p.name AS name,
       p.priceMinor AS priceMinor,
       collect(DISTINCT c.name) AS categories;
```

Thực hiện các yêu cầu:

1. Viết `ProductSummary` dưới dạng Java record.
2. Viết một repository projection tương ứng và thử ánh xạ bằng mapping mặc định.
3. Viết lại bằng `Neo4jClient.fetchAs(ProductSummary.class).mappedBy(...)`.
4. Xử lý trường hợp `priceMinor` là null và sản phẩm chưa có danh mục.
5. Thay truy vấn thành trả về nhiều sản phẩm và dùng `.all()`.
6. Tách callback thành `ProductSummaryMapper` rồi kiểm thử mapper với record có đủ trường và trường nullable.
7. So sánh lượng dữ liệu được trả về giữa entity graph và DTO projection; dùng `PROFILE` nếu cần đánh giá kế hoạch Cypher.

Sau bài tập, hãy giải thích được khi nào repository projection đã đủ, khi nào cần custom mapping, cách xử lý `Value` nullable và vì sao mapper không nên phát sinh truy vấn riêng cho từng record.

## Kết luận

Mapping mặc định của repository là lựa chọn phù hợp cho entity và projection đơn giản. Hãy chuyển sang mapping tùy chỉnh bằng `Neo4jClient` khi kết quả Cypher cần tổng hợp, có cấu trúc lồng nhau, dùng kiểu dữ liệu đặc biệt hoặc cần logic chuyển đổi theo từng record. `fetchAs(...).mappedBy(...)` cho phép kiểm soát việc đọc alias và chuyển `Value` thành DTO. Bind tham số, xử lý null, giới hạn dữ liệu được gom và giữ mapper thuần chuyển đổi để kết quả dễ kiểm thử, an toàn và phù hợp với use case.
