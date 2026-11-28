# Phân biệt `saveAll` với truy vấn ghi theo lô bằng `UNWIND`

Khi cần ghi hàng trăm hoặc hàng nghìn node vào Neo4j, có hai cách tiếp cận thường gặp trong Spring Data Neo4j (SDN): dùng `saveAll(...)` của repository để lưu các entity theo mô hình domain, hoặc gửi một danh sách parameter vào một câu Cypher dùng `UNWIND`. Hai cách đều có thể ghi nhiều bản ghi, nhưng khác nhau về abstraction, khả năng ánh xạ graph, lifecycle của entity, cách kiểm soát query và ranh giới transaction.

`saveAll` phù hợp khi dữ liệu đầu vào đã là các entity và cần SDN quản lý mapping node/relationship, version, auditing và callback. `UNWIND` phù hợp khi cần kiểm soát câu lệnh ghi, chỉ cập nhật một tập field xác định hoặc gửi nhiều hàng dữ liệu trong một lần gọi Cypher. `UNWIND` tự nó không chia một query thành nhiều transaction; nếu cần chia nhỏ transaction, phải chọn cách chunk ở ứng dụng hoặc dùng `CALL { ... } IN TRANSACTIONS` với đúng loại transaction.

## 1. `saveAll` và `UNWIND` giải quyết hai bài toán khác nhau

| Tiêu chí | `repository.saveAll(...)` | `UNWIND $rows` |
| --- | --- | --- |
| Đầu vào | Iterable các domain entity | List/map parameter do ứng dụng chuẩn bị |
| Mục tiêu | Lưu entity và graph liên quan theo mapping SDN | Thực thi một Cypher tùy chỉnh trên nhiều dòng dữ liệu |
| Mapping node/relationship | SDN dựa trên metadata entity | Lập trình viên viết rõ `CREATE`, `MERGE`, `MATCH`, relationship |
| Lifecycle SDN | Đi qua entity persistence path, bao gồm callback và auditing được cấu hình | Không tự chạy entity callback/auditing của SDN cho các node được query ghi trực tiếp |
| Version `@Version` | SDN xử lý theo persistence mapping | Tự viết predicate/version update nếu cần optimistic locking |
| Kết quả | Danh sách entity đã lưu | Record hoặc `ResultSummary` do query trả về |
| Kiểm soát Cypher | SDN sinh query theo graph mapping | Kiểm soát trực tiếp câu Cypher và các field được cập nhật |
| Phù hợp | CRUD domain, graph có quan hệ và lifecycle phong phú | Import dữ liệu phẳng, upsert theo key, cập nhật hàng loạt có quy tắc rõ |

Không nên chọn `UNWIND` chỉ vì tên `saveAll` có chữ “all”. API `saveAll` cam kết lưu nhiều entity, kể cả graph liên quan, và trả về các entity đã lưu. API không cam kết rằng mọi phiên bản SDN sẽ phát đúng một câu Cypher `UNWIND`, cũng không cam kết một số lượng query cố định. Chiến lược persistence cụ thể phụ thuộc mapping và phiên bản framework. Khi yêu cầu hiệu năng phụ thuộc số round trip hoặc hình dạng query, hãy đo trên đúng phiên bản SDN và mô hình dữ liệu của ứng dụng.

## 2. Mô hình entity dùng cho ví dụ

Giả sử ứng dụng quản lý sản phẩm với business key `sku`:

```java
import java.math.BigDecimal;

import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Product")
public class Product {

    @Id
    private String sku;

    @Version
    private Long version;

    private String name;

    private BigDecimal price;

    public Product(String sku, String name, BigDecimal price) {
        this.sku = sku;
        this.name = name;
        this.price = price;
    }

    public String getSku() { return sku; }
    public Long getVersion() { return version; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
}
```

Repository:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface ProductRepository extends Neo4jRepository<Product, String> {
}
```

Vì `sku` là business ID do ứng dụng gán, trường `@Version` kiểu `Long` giúp SDN phân biệt entity mới (`version == null`) với entity đã được persist. Business key cần uniqueness constraint trong Neo4j:

```cypher
CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE p.sku IS UNIQUE
```

Constraint giúp Neo4j kiểm tra tính duy nhất và hỗ trợ lookup theo key. `MERGE` không thay thế uniqueness constraint trong môi trường có ghi đồng thời.

## 3. Dùng `saveAll` khi đầu vào là domain entity

Khi đã có danh sách `Product`, cách tự nhiên nhất là truyền trực tiếp vào repository:

```java
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductImportService {

    private final ProductRepository productRepository;

    public ProductImportService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Transactional
    public List<Product> importProducts(List<Product> products) {
        return productRepository.saveAll(products);
    }
}
```

`SimpleNeo4jRepository.saveAll(...)` được đánh dấu `@Transactional`. Khi được gọi qua Spring repository proxy, các thao tác trong lần gọi `saveAll` tham gia một transaction theo propagation mặc định; nếu có transaction bên ngoài thì method tham gia transaction đó. Nếu một lỗi làm transaction rollback, các thay đổi trong transaction đó không được commit riêng lẻ từng entity.

`saveAll` hữu ích khi SDN cần biết toàn bộ cấu trúc entity:

- Xác định node mới hay node đã tồn tại dựa trên ID/version.
- Ánh xạ các property của entity sang node.
- Duyệt các association được khai báo trong domain model và lưu relationship liên quan.
- Áp dụng `@Version` cho optimistic locking.
- Chạy auditing và entity callback đã cấu hình trong persistence lifecycle.
- Trả về danh sách entity đã lưu, bao gồm các giá trị do persistence layer quản lý.

Điều này giúp code nghiệp vụ đơn giản hơn. Đổi lại, ứng dụng giao việc tạo query và xử lý graph cho SDN; không thể giả định một lời gọi `saveAll` tương đương một `UNWIND` đơn giản trên một label.

## 4. `saveAll` có phải là một bulk query duy nhất không?

Không nên suy luận số query từ tên method. Hợp đồng công khai của `Neo4jOperations.saveAll(Iterable)` mô tả việc lưu nhiều instance entity, bao gồm các entity liên quan. Hợp đồng đó không hứa rằng framework luôn gộp tất cả entity thành một query `UNWIND` duy nhất.

Kết quả thực thi phụ thuộc vào graph mapping, ví dụ:

- Entity chỉ có scalar properties có thể tạo ra workload khác với entity có nhiều relationship.
- Entity mới và entity đã tồn tại có quy tắc persistence khác nhau.
- Association có thể kéo theo thao tác trên các node/relationship liên quan.
- Callback, auditing, version và custom mapping có thể làm thay đổi dữ liệu cần bind.

Vì vậy, hãy xem `saveAll` là API lưu nhiều domain entity trong một transaction boundary, không phải cam kết về một hình dạng Cypher hoặc số round trip cố định. Nếu cần biết framework thực thi bao nhiêu statement trong phiên bản đang dùng, bật query logging/driver metrics trong môi trường kiểm thử hoặc quan sát query log của Neo4j.

## 5. Dùng `UNWIND` để ghi nhiều hàng trong một câu Cypher

`UNWIND` biến một list parameter thành nhiều dòng để các clause phía sau xử lý từng phần tử. Thay vì gửi một query cho mỗi sản phẩm, ứng dụng gửi một query với parameter `$rows`:

```cypher
UNWIND $rows AS row
MERGE (p:Product {sku: row.sku})
SET p.name = row.name,
    p.price = row.price
RETURN count(*) AS processedRows
```

Ứng dụng chuẩn bị dữ liệu parameter:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public record ProductInput(String sku, String name, BigDecimal price) {
}

List<Map<String, Object>> rows = new ArrayList<>();

for (ProductInput input : inputs) {
    Map<String, Object> row = new HashMap<>();
    row.put("sku", input.sku());
    row.put("name", input.name());
    row.put("price", input.price().doubleValue());
    rows.add(row);
}
```

Sau đó bind list vào `Neo4jClient`:

```java
import java.util.List;
import java.util.Map;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class ProductBulkWriter {

    private final Neo4jClient neo4jClient;

    public ProductBulkWriter(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public long upsertProducts(List<Map<String, Object>> rows) {
        if (rows.isEmpty()) {
            return 0;
        }

        Map<String, Object> result = neo4jClient.query("""
                UNWIND $rows AS row
                MERGE (p:Product {sku: row.sku})
                SET p.name = row.name,
                    p.price = row.price
                RETURN count(*) AS processedRows
                """)
            .bind(rows).to("rows")
            .fetch()
            .one()
            .orElseThrow(() -> new IllegalStateException("Bulk write returned no summary"));

        return ((Number) result.get("processedRows")).longValue();
    }
}
```

`UNWIND` giúp giảm số lần round trip từ ứng dụng xuống database: một parameter list được gửi trong một lần gọi query thay vì một lần gọi cho từng row. Các giá trị được truyền dưới dạng query parameter, không ghép chuỗi trực tiếp vào Cypher; cách này vừa an toàn hơn vừa giúp database tái sử dụng query plan. Ví dụ chuyển `BigDecimal` sang `double` chỉ phù hợp khi chấp nhận độ chính xác số thực; với tiền tệ cần chính xác tuyệt đối, nên truyền số nguyên theo đơn vị nhỏ nhất hoặc lưu biểu diễn decimal theo quy ước đã thống nhất.

### `UNWIND` không đảm bảo thứ tự row

Neo4j không bảo đảm thứ tự các dòng được tạo bởi `UNWIND`. Nếu thứ tự xử lý có ý nghĩa, phải dùng `ORDER BY` phù hợp. Đặc biệt, tránh gửi nhiều row có cùng `sku` nhưng giá trị khác nhau rồi kỳ vọng row cuối cùng trong list luôn thắng. Hãy deduplicate dữ liệu ở ứng dụng hoặc xác định quy tắc chọn bản ghi trước khi gửi.

## 6. Ghi node và relationship bằng `UNWIND`

`UNWIND` không chỉ ghi node. Có thể gửi danh sách cạnh và tạo relationship theo business key:

```cypher
UNWIND $rows AS row
MATCH (c:Customer {customerId: row.customerId})
MATCH (p:Product {sku: row.sku})
MERGE (c)-[r:PURCHASED {purchaseId: row.purchaseId}]->(p)
SET r.quantity = row.quantity,
    r.orderNumber = row.orderNumber
RETURN count(*) AS processedRows
```

Mỗi row mô tả một relationship cần tạo. Query dùng `MATCH` để tìm hai đầu node, rồi `MERGE` relationship theo key nghiệp vụ. Cần có uniqueness constraint/index phù hợp cho `Customer.customerId`, `Product.sku` và key của relationship nếu nghiệp vụ yêu cầu duy nhất.

Lưu ý: nếu một đầu node không tồn tại, `MATCH` làm row đó biến mất khỏi pipeline; query vẫn có thể hoàn tất thành công nhưng `processedRows` nhỏ hơn số input. So sánh số dòng đã xử lý với số dòng đầu vào hoặc trả thêm danh sách row lỗi để ứng dụng phát hiện dữ liệu tham chiếu thiếu.

Nếu phải tạo node và relationship cùng lúc, có thể dùng một query `UNWIND` với các `MERGE` node trước rồi `MERGE` relationship sau. Tuy nhiên, query sẽ khó đọc và khó xử lý lỗi hơn khi có nhiều loại quan hệ; chia thành các bước có ranh giới rõ ràng thường dễ vận hành hơn.

## 7. `UNWIND` là một query batch, chưa phải transaction batching

Đây là điểm rất dễ nhầm:

```cypher
UNWIND $rows AS row
CREATE (:Product {sku: row.sku, name: row.name})
```

Toàn bộ list `$rows` được xử lý bởi một câu query. Nếu query chạy trong một transaction, mọi thay đổi của query thuộc cùng transaction đó. `UNWIND` không tự chia 10.000 row thành 10 transaction nhỏ.

Với batch vừa phải, một query `UNWIND` đơn giản thường hiệu quả vì chỉ cần một lần gửi query và một transaction. Với batch rất lớn, một transaction duy nhất có thể giữ nhiều transaction state, lock và dữ liệu chưa commit trong bộ nhớ. Khi đó cần chia nhỏ.

Có hai cách chính:

1. Ứng dụng chia input thành các chunk, gửi từng chunk bằng một lần gọi `UNWIND` trong transaction riêng.
2. Dùng `CALL { ... } IN TRANSACTIONS OF n ROWS` để Neo4j chia input rows thành các inner transaction.

Hai cách có ranh giới commit khác nhau và không thể thay thế nhau một cách máy móc.

## 8. Chunk ở tầng ứng dụng

Chunking ở ứng dụng dễ tích hợp với `Neo4jClient`, Spring transaction và quy trình retry. Ví dụ chia danh sách thành các nhóm 500 row:

```java
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;

@Service
public class ChunkedProductImportService {

    private static final int CHUNK_SIZE = 500;

    private final ProductChunkWriter chunkWriter;

    public ChunkedProductImportService(ProductChunkWriter chunkWriter) {
        this.chunkWriter = chunkWriter;
    }

    public long importProducts(List<Map<String, Object>> rows) {
        long total = 0;

        for (int start = 0; start < rows.size(); start += CHUNK_SIZE) {
            int end = Math.min(start + CHUNK_SIZE, rows.size());
            total += chunkWriter.writeChunk(rows.subList(start, end));
        }

        return total;
    }

}
```

`ProductChunkWriter` là bean riêng; method `@Transactional` của nó được gọi qua Spring proxy nên mỗi lần gọi tạo một transaction riêng:

```java
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductChunkWriter {

    private final ProductBulkWriter bulkWriter;

    public ProductChunkWriter(ProductBulkWriter bulkWriter) {
        this.bulkWriter = bulkWriter;
    }

    @Transactional
    public long writeChunk(List<Map<String, Object>> chunk) {
        return bulkWriter.upsertProducts(chunk);
    }
}
```

`ProductBulkWriter` dùng `Neo4jClient` được SDN cấu hình với cùng `Driver` mà `Neo4jTransactionManager` sử dụng. Nhờ vậy query `UNWIND` tham gia transaction đang mở bởi `ProductChunkWriter`; nếu client dùng một Driver độc lập, query có thể chạy ngoài transaction đó.

Không chuyển `importProducts` sang `@Transactional` nếu mục tiêu là commit từng chunk riêng: khi đó các lời gọi `REQUIRED` của `writeChunk` sẽ tham gia transaction ngoài. Nếu cần transaction cho toàn bộ import, hãy đặt transaction ở service import và bỏ transaction riêng từng chunk. Nếu cần điều khiển programmatic, có thể dùng `TransactionTemplate` với transaction manager Neo4j.

Mỗi chunk commit độc lập. Nếu chunk thứ tư thất bại, các chunk đầu đã commit vẫn tồn tại; ứng dụng cần lưu tiến độ để tiếp tục từ vị trí phù hợp.

Kích thước 500 chỉ là ví dụ ban đầu. Hãy đo với kích thước 100, 500, 1.000 hoặc lớn hơn tùy kích thước payload, số thao tác trên mỗi row, index, network và heap. Chunk quá nhỏ làm tăng round trip; chunk quá lớn làm tăng transaction state và thời gian giữ lock.

## 9. Dùng `CALL { ... } IN TRANSACTIONS` cho import lớn

Cypher hỗ trợ inner transaction batching:

```cypher
UNWIND $rows AS row
CALL (row) {
    MERGE (p:Product {sku: row.sku})
    SET p.name = row.name,
        p.price = row.price
} IN TRANSACTIONS OF 500 ROWS
```

Neo4j gom 500 input rows cho mỗi inner transaction rồi commit trước khi xử lý batch tiếp theo. Batch cuối có thể ít hơn 500 row.

Cú pháp variable scope `CALL (row) { ... }` được hỗ trợ từ Neo4j 5.23. Với server cũ hơn, dùng cú pháp import biến qua `WITH` bên trong subquery theo phiên bản Cypher tương ứng.

Điểm quan trọng về transaction:

- `CALL { ... } IN TRANSACTIONS` yêu cầu query chạy trong implicit/auto-commit transaction.
- Không đặt query này bên trong một Spring `@Transactional` method đang mở explicit transaction; Neo4j sẽ từ chối cấu trúc transaction đó.
- Các inner transaction đã commit sẽ không bị rollback nếu một batch sau thất bại.
- Nếu cần all-or-nothing cho toàn bộ dữ liệu, dùng một transaction thông thường và chấp nhận chi phí bộ nhớ/lock, hoặc thiết kế quy trình staging/validation/compensation phù hợp.
- Có thể dùng `ON ERROR CONTINUE`, `BREAK`, `FAIL` hoặc `RETRY` tùy chính sách xử lý lỗi; cần ghi nhận row/batch thất bại để có thể sửa và chạy lại.

Đây là lựa chọn tốt cho import lớn, nhưng phải kiểm tra API thực thi hỗ trợ implicit transaction và không bọc nó trong transaction Spring đang hoạt động. Nếu gọi từ application code, dùng cơ chế chạy auto-commit phù hợp với Neo4j Driver/Neo4jClient và phiên bản đang triển khai.

## 10. Lifecycle: `saveAll` có, custom `UNWIND` phải tự xử lý

Khi dùng `saveAll`, SDN biết entity type và mapping metadata. Khi tự viết `UNWIND`, Neo4j chỉ nhận Cypher và parameter map; nó không biết các annotation Java trên class.

| Tính năng | `saveAll` | Custom `UNWIND` |
| --- | --- | --- |
| `@CreatedBy`, `@CreatedDate` | Được auditing infrastructure xử lý trong SDN persistence path | Tự set các property cần thiết trong Cypher/parameter |
| `@LastModifiedBy`, `@LastModifiedDate` | Được auditing infrastructure xử lý | Tự cập nhật |
| `@Version` | SDN kiểm tra và cập nhật version | Tự thiết kế kiểm tra version và xử lý conflict |
| `BeforeBindCallback` | Được gọi trong lifecycle tương ứng | Không tự gọi |
| Mapping association | SDN dựa trên metadata entity | Tự viết `MATCH`/`MERGE` relationship |
| Entity state detection | Dựa trên ID/version metadata | Tự định nghĩa `CREATE` hay `MERGE` |

Nếu custom query cần giữ metadata audit, hãy truyền actor/time đã xác thực và set tường minh:

```cypher
UNWIND $rows AS row
MERGE (p:Product {sku: row.sku})
ON CREATE SET p.createdBy = row.actor,
              p.createdAt = datetime()
SET p.name = row.name,
    p.lastModifiedBy = row.actor,
    p.lastModifiedAt = datetime()
```

Ví dụ này minh họa việc tự ghi audit properties. Nếu actor phải đáng tin cậy, ứng dụng phải lấy actor từ security context/service identity, không lấy trực tiếp từ input client. Nếu cần logic phức tạp, hãy tách audit event thành node riêng thay vì chỉ giữ metadata lần sửa gần nhất.

Với optimistic locking, custom query phải kiểm tra expected version và xử lý những row không khớp. Không chỉ tăng `p.version` một cách mù quáng; nếu có nhiều transaction cạnh tranh cùng update một node, cần bảo đảm thao tác kiểm tra version và cập nhật được bảo vệ bởi locking strategy phù hợp. Nếu không muốn tự quản lý những chi tiết này, hãy dùng SDN entity persistence path.

## 11. Chọn `CREATE`, `MERGE` và index đúng cách

Trong batch write, lựa chọn clause ảnh hưởng trực tiếp tới hiệu năng:

- `CREATE` tạo node/relationship mới và phù hợp khi input đã được xác nhận chưa tồn tại.
- `MERGE` tìm hoặc tạo theo pattern; phù hợp upsert nhưng cần key có index/constraint để lookup hiệu quả.
- `MATCH` chỉ tìm entity có sẵn; nếu không khớp, row bị loại khỏi pipeline.
- `SET` cập nhật property; gán `null` cho property sẽ xóa property đó trong Neo4j.

Ví dụ `MERGE` theo business key:

```cypher
UNWIND $rows AS row
MERGE (p:Product {sku: row.sku})
SET p.name = row.name,
    p.price = row.price
```

Nếu mọi row đều là sản phẩm mới và đã có kiểm soát trùng lặp ở upstream, `CREATE` có thể tránh chi phí kiểm tra tồn tại của `MERGE`. Tuy nhiên, nếu input có thể được gửi lại hoặc có key đã tồn tại, `CREATE` sẽ sinh duplicate nếu không có constraint ngăn chặn. Hãy chọn theo semantics nghiệp vụ, không chọn chỉ dựa vào benchmark nhỏ.

### Xử lý property null

Trong Cypher, `SET p.description = null` xóa property `description`. Nếu null trong payload có nghĩa “không cập nhật field này”, cần truyền cờ hiện diện hoặc tách các nhóm update thay vì set mọi field một cách mù quáng:

```cypher
UNWIND $rows AS row
MATCH (p:Product {sku: row.sku})
SET p.name = row.name,
    p.description = CASE
        WHEN row.updateDescription THEN row.description
        ELSE p.description
    END
```

Trong ví dụ, `updateDescription` phân biệt “không gửi field” với “muốn xóa field bằng null”.

## 12. Xử lý lỗi, retry và idempotency

Một batch ghi cần được thiết kế để có thể chạy lại an toàn:

- Dùng business key có uniqueness constraint.
- Dùng `MERGE` khi semantics là upsert và xác định rõ property nào được cập nhật.
- Dùng import ID hoặc batch ID để theo dõi tiến độ.
- Nếu chunk commit độc lập, lưu checkpoint sau mỗi chunk đã commit.
- Phân biệt lỗi dữ liệu không hợp lệ với lỗi transient như deadlock hoặc mất kết nối.
- Chỉ retry lỗi transient và giới hạn số lần retry.
- Đảm bảo một request retry không tạo duplicate relationship hoặc ghi đè dữ liệu mới hơn ngoài ý muốn.

Với `CALL { ... } IN TRANSACTIONS`, `ON ERROR CONTINUE` có thể cho phép các batch sau tiếp tục, nhưng ứng dụng phải đọc status/error và lưu lại các row thất bại. Khi một inner transaction thất bại, toàn bộ row thuộc batch đó có thể rollback cùng nhau; không giả định chỉ row gây lỗi bị loại bỏ.

Với `saveAll`, một optimistic locking failure trên entity có `@Version` phải được xử lý theo cơ chế Spring Data. Không retry bằng object stale; tải lại entity hoặc trả conflict theo nghiệp vụ.

## 13. Reactive `saveAll` và `UNWIND`

SDN reactive repository cung cấp `saveAll(Publisher<S>)` trả về `Flux<S>`. Ví dụ:

```java
Flux<Product> saved = reactiveProductRepository.saveAll(
    Flux.fromIterable(products)
);

return saved.collectList();
```

Publisher cho phép compose với Reactor và kiểm soát luồng tiêu thụ. Tuy nhiên, việc nhận `Flux` không có nghĩa SDN sẽ chuyển cả publisher thành một câu `UNWIND` duy nhất.

Reactive custom query có thể bind một list parameter tương tự imperative:

```java
import java.util.List;
import java.util.Map;

import org.neo4j.driver.summary.ResultSummary;
import org.springframework.data.neo4j.core.ReactiveNeo4jClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class ReactiveProductBulkWriter {

    private final ReactiveNeo4jClient reactiveNeo4jClient;

    public ReactiveProductBulkWriter(ReactiveNeo4jClient reactiveNeo4jClient) {
        this.reactiveNeo4jClient = reactiveNeo4jClient;
    }

    public Mono<ResultSummary> writeRows(List<Map<String, Object>> rows) {
        return reactiveNeo4jClient.query("""
                UNWIND $rows AS row
                MERGE (p:Product {sku: row.sku})
                SET p.name = row.name,
                    p.price = row.price
                """)
            .bind(rows).to("rows")
            .run();
    }
}
```

Hãy compose publisher này trong transaction reactive nếu cần kết hợp với các thao tác khác. Không gọi `subscribe()` bên trong service để tách query khỏi transaction context.

## 14. Đo hiệu năng công bằng

Không có một con số batch size tối ưu cho mọi graph. Khi so sánh `saveAll` và `UNWIND`, giữ các điều kiện thử nghiệm giống nhau:

1. Cùng số row, cùng payload và cùng graph schema.
2. Cùng uniqueness constraint/index và cùng trạng thái cache.
3. Cùng ranh giới transaction hoặc ghi rõ số transaction khác nhau.
4. Đo tổng thời gian, throughput, p95 latency, heap, transaction memory và số lần gọi query.
5. Chạy nhiều vòng sau khi warm up, không kết luận từ một lần chạy.
6. Kiểm tra dữ liệu cuối cùng, số node/relationship và tính đúng đắn sau mỗi cách ghi.

Với custom Cypher, dùng `EXPLAIN` để xem kế hoạch và `PROFILE` để đo operator thực tế. Đảm bảo lookup theo business key sử dụng index/constraint thay vì label scan không cần thiết. Với `saveAll`, bật query logging/driver metrics trong môi trường kiểm thử để quan sát query mà phiên bản SDN đang dùng thực sự phát ra.

### Các chỉ số nên theo dõi

| Chỉ số | Ý nghĩa |
| --- | --- |
| Rows/second | Throughput ghi |
| p50/p95 latency | Thời gian hoàn thành request/batch |
| Query round trips | Chi phí giao tiếp ứng dụng/database |
| Transaction duration | Thời gian giữ transaction và lock |
| Heap/transaction memory | Nguy cơ tăng bộ nhớ với batch lớn |
| Lock wait/deadlock | Cạnh tranh khi nhiều batch ghi cùng node |
| Retry count | Tần suất lỗi transient hoặc conflict |
| Rows accepted/rejected | Mức độ đầy đủ và chất lượng dữ liệu |

## 15. Chọn cách nào cho từng tình huống?

| Tình huống | Lựa chọn nên cân nhắc | Lý do |
| --- | --- | --- |
| Lưu danh sách entity domain có relationship | `repository.saveAll` | SDN quản lý graph mapping và lifecycle |
| Import bảng dữ liệu phẳng, chỉ có vài field | `UNWIND` | Một parameter list và một câu Cypher rõ ràng |
| Upsert theo business key | `UNWIND` + `MERGE` + constraint hoặc `saveAll` | Chọn theo nhu cầu lifecycle và mapping |
| Cập nhật một tập field có quy tắc cụ thể | Custom `UNWIND` | Không cần hydrate toàn bộ entity graph |
| Cần auditing, callbacks, version do SDN quản lý | `saveAll` | Giữ nguyên persistence lifecycle |
| Tạo hàng triệu node từ file/import job | `LOAD CSV` hoặc `UNWIND` kết hợp `CALL ... IN TRANSACTIONS` | Chia inner transaction và kiểm soát bộ nhớ |
| Ghi các chunk độc lập từ application worker | Chunked `UNWIND` theo transaction | Checkpoint/retry theo chunk |
| Reactive domain persistence | `ReactiveNeo4jRepository.saveAll` | Compose publisher và lifecycle SDN |

## 16. Checklist trước khi triển khai batch write

1. Xác định đầu vào là domain entity hay row data đã được chuẩn hóa.
2. Nếu cần graph mapping, callbacks, auditing hoặc `@Version`, ưu tiên `saveAll`.
3. Nếu dùng `UNWIND`, xác định rõ `CREATE`, `MERGE`, `MATCH` và relationship semantics.
4. Tạo uniqueness constraint/index cho business key trước khi import.
5. Dùng parameter binding; không nối dữ liệu người dùng vào chuỗi Cypher.
6. Nhớ rằng `UNWIND` đơn lẻ vẫn là một query/transaction, không tự chia batch commit.
7. Chọn chunk size bằng benchmark và kiểm tra heap/transaction duration.
8. Nếu dùng `CALL IN TRANSACTIONS`, chạy bằng implicit transaction và không bọc trong `@Transactional` explicit.
9. Xác định rõ atomicity: toàn bộ batch hay từng chunk được commit độc lập.
10. Thiết kế idempotency, checkpoint và retry cho import có thể chạy lại.
11. Đếm số row thực sự được xử lý; phát hiện row bị loại bởi `MATCH`.
12. Kiểm thử dữ liệu cuối cùng và các trường hợp lỗi giữa chừng.

## Kết luận

`saveAll` là API persistence cho nhiều domain entity: SDN quản lý graph mapping, association và các lifecycle feature như auditing, callback, version. API không hứa một query `UNWIND` duy nhất hay số statement cố định. `UNWIND $rows` là cách gửi nhiều row vào một câu Cypher để giảm round trip và kiểm soát trực tiếp thao tác ghi; đổi lại, ứng dụng phải tự quản lý mapping, auditing, version và relationship. `UNWIND` không tự chia transaction. Với batch lớn, hãy chunk ở ứng dụng hoặc dùng `CALL { ... } IN TRANSACTIONS` trong implicit transaction, hiểu rõ mỗi batch commit độc lập và thiết kế checkpoint/retry. Lựa chọn cuối cùng nên dựa trên lifecycle cần giữ, hình dạng graph, ranh giới atomicity và benchmark thực tế.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.1.2 API — `Neo4jTemplate.saveAll`](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jTemplate.html)
- [Spring Data Neo4j 8.1.2 API — `SimpleNeo4jRepository.saveAll`](https://docs.spring.io/spring-data/data-neo4j/reference/api/java/org/springframework/data/neo4j/repository/support/SimpleNeo4jRepository.html)
- [Spring Data Neo4j — Neo4jClient parameter binding](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
- [Neo4j Data Ingestion Guide — Loading data from application code with `UNWIND`](https://neo4j.com/docs/data-ingestion-guide/ingestion-methods/unwind/)
- [Cypher Manual — `UNWIND`](https://neo4j.com/docs/cypher-manual/current/clauses/unwind/)
- [Cypher Manual — `CALL` subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/)
- [Neo4j Data Ingestion Guide — Transactional and concurrent Cypher ingestion](https://neo4j.com/docs/data-ingestion-guide/best-practices/transactional-and-concurrent-cypher-ingestion/)
