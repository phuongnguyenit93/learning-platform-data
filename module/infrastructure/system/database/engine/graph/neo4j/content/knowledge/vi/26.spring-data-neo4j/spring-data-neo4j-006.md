# DTO, projection và kiểm soát độ rộng đồ thị được tải trong Spring Data Neo4j

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **entity**, **interface-based projection**, **DTO/record projection** và kết quả Cypher được ánh xạ thủ công trong Spring Data Neo4j.
- Giải thích vì sao đọc một node gốc có thể kéo theo nhiều relationship và node liên quan, làm tăng độ rộng và chi phí truy vấn.
- Thiết kế API trả về trường dữ liệu cần thiết mà không vô tình tải toàn bộ một **property graph**.
- Sử dụng repository projection, **dynamic projection**, `@Query` và `Neo4jClient` theo từng nhu cầu.
- Kiểm soát fan-out, độ sâu traversal, phân trang, N+1 query và giới hạn kết quả khi quan hệ có cardinality lớn.
- Kiểm tra truy vấn thực tế bằng `EXPLAIN`/`PROFILE`, query log và integration test thay vì đoán hiệu năng từ kiểu trả về Java.

Đây là bài thuộc chương **Spring Data Neo4j** của module **DATABASE_ENGINE_GRAPH_NEO4J**. Neo4j mô hình hóa node, relationship và các thuộc tính theo **property graph**, còn Cypher truy vấn các quan hệ và đường đi. Spring Data Neo4j (SDN) ánh xạ dữ liệu đồ thị vào đối tượng Java và cung cấp repository. Ánh xạ rất tiện cho nghiệp vụ, nhưng một entity có nhiều relationship có thể tạo **đồ thị đối tượng lớn** dù endpoint chỉ muốn trả vài trường.

> **Phạm vi:** Ví dụ dùng cách lập trình phổ biến của Spring Data Neo4j 6/7 và Spring Data Commons; chi tiết tạo query và khả năng projection phụ thuộc phiên bản Spring Boot, SDN, cách khai báo entity và loại query. Không coi việc chọn interface/DTO là bằng chứng database chắc chắn đã đọc ít hơn: cần quan sát **Cypher thực thi thực tế**. Các đoạn entity/repository trình bày phần liên quan; getter, constructor và cấu hình ứng dụng có thể được lược bỏ khi đã ghi chú.

## 1. Bài toán: API nhỏ nhưng graph lớn

Xét ứng dụng bán hàng với ba kiểu node:

~~~mermaid
flowchart LR
    C["Customer<br/>customerId, displayName"] -->|PLACED 1:N| O["Order<br/>orderId, status, totalCents"]
    O -->|CONTAINS N:M| P["Product<br/>sku, name"]
~~~

Giả sử một `Customer` có **10.000** đơn hàng; trung bình mỗi đơn liên quan tới **8** sản phẩm. Một màn hình “thông tin khách hàng” chỉ cần:

~~~json
{
  "customerId": "C-101",
  "displayName": "Lan"
}
~~~

Nếu lớp truy cập dữ liệu lại dựng cả `Customer.orders` và tiếp tục dựng `Order.products`, hệ thống có thể xử lý rất nhiều node/relationship và tạo một cấu trúc Java lớn chỉ để trả hai chuỗi. Đây là vấn đề **over-fetching** hoặc **tải đồ thị rộng hơn nhu cầu**.

Ba chiều cần kiểm soát:

| Chiều | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Độ rộng (breadth)** | Số node/relationship được lấy tại một bước | Một khách hàng có 10.000 cạnh `PLACED` |
| **Độ sâu (depth)** | Số bước quan hệ đi qua | `Customer → Order → Product` là hai bước |
| **Payload/shape** | Số thuộc tính và dữ liệu được trả về | Trả toàn bộ `Product.description` thay vì `sku` |

Độ rộng và độ sâu cộng hưởng với nhau. Nếu trung bình mỗi node có `d` hàng xóm, một phép duyệt dài `k` bước có thể sinh rất nhiều hàng trung gian; chu trình, node trùng và điều kiện lọc làm số thực tế khác phép ước lượng đơn giản `d^k`.

**Thông điệp chính:** Kiểm soát tải graph gồm **hai việc khác nhau**:

1. Giới hạn **Cypher đọc và trả về** bao nhiêu node, cạnh, thuộc tính.
2. Giới hạn **Java mapping/serialization** chuyển bao nhiêu dữ liệu vào object và HTTP response.

Chỉ tối ưu bước thứ hai mà để Cypher vẫn duyệt hàng triệu relationship có thể không giúp cải thiện nhiều.

## 2. Entity mapping: thuận tiện nhưng cần hiểu phạm vi

Mô hình Java đơn giản:

~~~java
import java.util.HashSet;
import java.util.Set;
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Customer")
public class Customer {
    @Id
    private String customerId;   // ID do nghiệp vụ gán
    private String displayName;

    @Relationship(
        type = "PLACED",
        direction = Relationship.Direction.OUTGOING
    )
    private Set<Order> orders = new HashSet<>();

    // Constructor và getter/setter được lược bỏ.
}

@Node("Order")
public class Order {
    @Id
    private String orderId;
    private String status;
    private long totalCents;

    @Relationship(
        type = "CONTAINS",
        direction = Relationship.Direction.OUTGOING
    )
    private Set<Product> products = new HashSet<>();

    // Constructor và getter/setter được lược bỏ.
}

@Node("Product")
public class Product {
    @Id
    private String sku;
    private String name;

    // Constructor và getter/setter được lược bỏ.
}
~~~

Ba entity dùng `@Node` để ánh xạ label, `@Id` làm khóa, `@Relationship` để biểu diễn cạnh có hướng. Mã giả định đã có các node/relationship tương ứng trong Neo4j. Trong ứng dụng thật, cần khai báo constructor/property access phù hợp, constraint trên ID nghiệp vụ và vòng đời aggregate rõ ràng.

Repository cơ bản:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface CustomerRepository
        extends Neo4jRepository<Customer, String> {
}
~~~

`findById("C-101")` trả `Customer` — một **entity graph** theo chiến lược query/mapping mà SDN tạo cho mô hình này. Không nên mặc định điều đó có nghĩa “chỉ lấy thuộc tính của customer”, nhưng cũng không khẳng định mọi phiên bản luôn tải vô hạn tất cả đường đi. **Hình dạng query thực tế** tùy các relationship mapping, projection, query method và phiên bản SDN.

Khác một số kỳ vọng từ JPA, đừng dựa vào giả định “quan hệ chưa cần sẽ được lazy-load tự động sau khi session đóng”. SDN hiện đại xây dựng truy vấn để ánh xạ graph theo các quy tắc riêng; hãy chủ động xác định phạm vi dữ liệu cần ở từng use case.

### Một anti-pattern thường gặp

~~~java
public Customer showCustomer(String id) {
    return customerRepository.findById(id).orElseThrow();
}
~~~

Sau đó trả trực tiếp entity từ controller. Những rủi ro:

- Query có thể lấy thêm relationship mà màn hình không dùng.
- JSON serializer đi qua các getter relationship, làm payload lớn hoặc gặp vòng tham chiếu.
- Domain entity vô tình lộ thuộc tính nội bộ.
- API phụ thuộc chặt vào cách entity được model hóa, khó thay đổi hợp đồng response.

Ưu tiên **response DTO** được thiết kế theo nhu cầu API, không trả toàn bộ entity graph như hợp đồng HTTP mặc định.

## 3. Interface-based projection: chọn thuộc tính qua getter

Spring Data hỗ trợ **interface projection**: ứng dụng khai báo một giao diện chỉ chứa các thuộc tính cần đọc.

~~~java
public interface CustomerCard {
    String getCustomerId();
    String getDisplayName();
}
~~~

Repository có thể khai báo một phương thức riêng cho projection:

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface CustomerRepository
        extends Neo4jRepository<Customer, String> {

    Optional<CustomerCard> findProjectedByCustomerId(
            String customerId);
}
~~~

Sử dụng:

~~~java
CustomerCard card = customerRepository
        .findProjectedByCustomerId("C-101")
        .orElseThrow();

String label = card.getDisplayName();
~~~

Ưu điểm:

- Kiểu trả về bộc lộ rõ API cần `customerId` và `displayName`.
- Không phải tự viết bộ chuyển đổi entity → DTO cho trường hợp đọc đơn giản.
- Có thể dùng projection cho nhiều view trên cùng node, tránh thêm vô số entity chỉ phục vụ hiển thị.

**Giới hạn quan trọng:** Projection là **quy ước ánh xạ và shape kết quả ở tầng SDN**. Query derivation có thể khai thác projection để thay đổi phạm vi dữ liệu được lấy, nhưng không bảo đảm mọi đường dẫn/trường hợp custom Cypher đều tự động tối ưu. Cần xem câu Cypher và plan đã thực thi.

### 3.1. Closed projection và open projection

`CustomerCard` là dạng **closed projection**: mọi accessor tương ứng thuộc tính của entity và có thể được framework phân tích.

Một **open projection** có thể dùng biểu thức:

~~~java
import org.springframework.beans.factory.annotation.Value;

public interface CustomerDisplay {
    @Value("#{target.customerId + ' - ' + target.displayName}")
    String getTitle();
}
~~~

Open projection phụ thuộc biểu thức tính từ `target`. Framework khó suy ra tất cả phụ thuộc như closed projection và **có thể cần tải entity đầy đủ hơn**. Không ưu tiên open projection khi mục tiêu chính là giảm số thuộc tính/quan hệ được đọc; cân nhắc tính trực tiếp trong Java sau khi lấy dữ liệu tối thiểu hoặc dùng Cypher `RETURN` trường cần thiết.

### 3.2. Nested projection: cẩn thận với quan hệ nhiều phần tử

Bạn có thể mô tả dữ liệu lồng nhau:

~~~java
public interface OrderCard {
    String getOrderId();
    String getStatus();
}

public interface CustomerWithOrders {
    String getCustomerId();
    java.util.Set<OrderCard> getOrders();
}
~~~

Kiểu `CustomerWithOrders` thể hiện rằng client muốn cả đơn hàng liên quan. **Nó không chứa quy tắc `LIMIT 5` hay phân trang ở collection `orders`**. Với khách hàng có 10.000 đơn, nested projection có thể vẫn kéo một tập quan hệ lớn.

Hơn nữa, projection lồng nhau có thể thay đổi dạng Cypher/mapping do SDN tạo. Đừng mặc định `getOrders()` tải lười (*lazy*) hoặc framework chỉ lấy một số đơn theo nhu cầu serializer.

Khi cần “20 đơn mới nhất”, một **truy vấn Cypher có phạm vi rõ ràng** phù hợp hơn việc đưa toàn bộ `Set<OrderCard>` vào response.

## 4. DTO/record projection: dữ liệu chỉ đọc, hợp đồng rõ ràng

**Data Transfer Object (DTO)** là kiểu Java được thiết kế để chuyển dữ liệu giữa các tầng. Với Java hiện đại, `record` là lựa chọn gọn cho kết quả đọc không cần thay đổi.

~~~java
public record CustomerSummary(
        String customerId,
        String displayName
) {}

public record OrderRow(
        String orderId,
        String status,
        long totalCents
) {}
~~~

Khác với `Customer` entity, `CustomerSummary` không mang `@Node`, `@Relationship` hoặc cơ chế lưu object graph. Nó không đại diện cho một aggregate dùng để `save(...)`; nó là **ảnh chụp dữ liệu phục vụ một use case**.

### 4.1. Class-based DTO projection trong repository

Spring Data Commons có khả năng **class-based projection** dựa trên constructor, gồm Java record. Ví dụ khai báo query method theo đặc điểm domain:

~~~java
public interface CustomerRepository
        extends Neo4jRepository<Customer, String> {

    java.util.Optional<CustomerSummary>
            findSummaryByCustomerId(String customerId);
}
~~~

Với query method có thể dẫn xuất từ thuộc tính entity, framework sử dụng thông tin constructor/property để ánh xạ các trường tương ứng khi phiên bản SDN hỗ trợ dạng projection này. Nếu tên thuộc tính/constructor không khớp, phép ánh xạ có thể thất bại.

**Không trộn lẫn** việc tạo DTO từ repository projection với **một custom Cypher trả tuple tùy ý**. Với kết quả tổng hợp, scalar alias, thuộc tính quan hệ hoặc nhiều loại node, ánh xạ rõ ràng qua `Neo4jClient` (phần sau) thường dễ dự đoán hơn.

### 4.2. Dynamic projection: một phương thức, nhiều kiểu trả về

Khi nhiều chỗ cần hình dạng kết quả khác nhau từ cùng điều kiện tìm kiếm, dùng **dynamic projection**:

~~~java
public interface CustomerRepository
        extends Neo4jRepository<Customer, String> {

    <T> java.util.Optional<T> findByCustomerId(
            String customerId, Class<T> projectionType);
}
~~~

Ví dụ:

~~~java
CustomerCard card = repository
        .findByCustomerId("C-101", CustomerCard.class)
        .orElseThrow();

CustomerSummary summary = repository
        .findByCustomerId("C-101", CustomerSummary.class)
        .orElseThrow();
~~~

Dynamic projection giúp tái sử dụng phương thức truy vấn, nhưng **không nên biến một repository thành điểm trả về tùy ý mọi graph shape**. Mỗi projection vẫn phải có mapping hợp lệ, được thử nghiệm với phiên bản SDN thực tế và không chứa những quan hệ có thể mở rộng vô hạn.

### 4.3. DTO không đồng nghĩa “không còn chi phí đồ thị”

Ngay cả khi response là `CustomerSummary`, có ba kịch bản khác nhau:

1. **Tốt:** Query chỉ tìm node gốc và lấy hai thuộc tính; database và mapping đều xử lý ít dữ liệu.
2. **Chưa tối ưu:** Query vẫn tải một graph rộng, sau đó Java chỉ lấy hai thuộc tính để tạo DTO; HTTP response nhỏ nhưng database vẫn tốn chi phí.
3. **Sai ngữ nghĩa:** Query chỉ trả thuộc tính nhưng code cố ánh xạ thành entity có relationship bắt buộc, dẫn tới dữ liệu thiếu hoặc mapping không đúng.

Do đó, mục tiêu tối ưu là **query shape + mapping shape**, không đơn thuần chọn một kiểu Java.

## 5. Kiểm soát chính xác bằng Neo4jClient và Cypher

Với màn hình/API cần dữ liệu phẳng hoặc một phần rất nhỏ của graph, `Neo4jClient` cho phép viết Cypher minh bạch rồi ánh xạ từng hàng thành DTO.

### 5.1. Đọc danh sách đơn hàng, không tải toàn bộ Customer graph

Ví dụ service chỉ trả tối đa 20 đơn đang ở trạng thái `PAID`:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderReadService {
    private final Neo4jClient neo4jClient;

    public OrderReadService(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    @Transactional(readOnly = true)
    public List<OrderRow> findPaidOrders(
            String customerId, int requestedLimit) {
        int limit = Math.max(1, Math.min(requestedLimit, 50));

        var result = neo4jClient.query("""
                MATCH (c:Customer {customerId: $customerId})
                      -[:PLACED]->(o:Order)
                WHERE o.status = 'PAID'
                RETURN o.orderId AS orderId,
                       o.status AS status,
                       o.totalCents AS totalCents
                ORDER BY o.orderId
                LIMIT $pageSize
                """)
                .bind(customerId).to("customerId")
                .bind(limit).to("pageSize")
                .fetchAs(OrderRow.class)
                .mappedBy((typeSystem, record) -> new OrderRow(
                        record.get("orderId").asString(),
                        record.get("status").asString(),
                        record.get("totalCents").asLong()))
                .all();

        return new ArrayList<>(result);
    }
}
~~~

Trong đoạn này, `OrderRow` chính là Java record ở phần trước. `Neo4jClient` sử dụng driver Neo4j và hạ tầng transaction do Spring cấu hình; `mappedBy` chuyển một record từ kết quả Cypher sang DTO. Phương thức này **không trả các entity `Customer` / `Order`** và không đi qua `Order.products`. Dữ liệu trả về gồm đúng các cột được khai báo ở `RETURN`.

Một điểm cần chú ý: `ORDER BY o.orderId` chỉ sắp theo ID; **không mặc định đại diện cho thời gian tạo đơn**. Nếu yêu cầu nghiệp vụ là “mới nhất”, hãy dùng `createdAt` và tie-breaker ổn định (xem phần phân trang).

### 5.2. Vì sao không luôn dùng `@Query` trên repository?

`@Query` rất phù hợp khi muốn khai báo Cypher cố định cạnh phương thức repository:

~~~java
import org.springframework.data.neo4j.repository.query.Query;

public interface CustomerRepository
        extends Neo4jRepository<Customer, String> {

    @Query("""
        MATCH (c:Customer {customerId: $customerId})
        RETURN c
        """)
    java.util.Optional<Customer>
            findCustomerNodeOnly(String customerId);
}
~~~

Tuy nhiên, **`RETURN c` chỉ trả node gốc trong câu Cypher**, trong khi phương thức tuyên bố trả **entity `Customer`** có mapping quan hệ. Kết quả có thể là một entity **không đầy đủ quan hệ**, khác với entity graph mà repository tạo tự động. Không nên lấy entity bị cắt bớt rồi `save(...)` mà không hiểu rõ semantics cập nhật relationship: có rủi ro ảnh hưởng dữ liệu liên quan hoặc làm sai aggregate.

Với query custom trả scalar/aggregation, ưu tiên **DTO và mapping minh bạch**. Với query custom trả entity + relationship, hãy tuân thủ shape trả về mà SDN yêu cầu để dựng object graph chính xác; ví dụ một projection chỉ đọc không phải nơi lưu lại nguyên aggregate.

### 5.3. Cách xem query thật thay vì đoán

Khi chọn repository projection hay `Neo4jClient`:

1. Bật quan sát **Cypher query log/statement logging** phù hợp môi trường và mức bảo mật.
2. Kiểm tra truy vấn SDN thực thi cho phương thức cụ thể.
3. Dùng `EXPLAIN` hoặc `PROFILE` an toàn với giá trị tham số đại diện.
4. So sánh `Rows`, `DB Hits`, thời gian query, số bản ghi trả về và dung lượng JSON.

Không so sánh chỉ bằng việc Java trả `CustomerCard` hay `Customer`, bởi phần tốn kém có thể nằm ở các phép `Expand` hoặc `Sort` phía Neo4j.

## 6. Độ rộng quan hệ: fan-out và bùng nổ hàng trung gian

### 6.1. Một khách hàng có rất nhiều đơn

Một truy vấn không giới hạn:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN c, o;
~~~

Nếu khách hàng có 10.000 đơn, Cypher có thể trả 10.000 hàng. Với trường hợp người dùng chỉ cần “tổng số đơn”, không nên kéo về 10.000 đối tượng Java để đếm:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN c.customerId AS customerId,
       count(DISTINCT o) AS orderCount;
~~~

`count(DISTINCT o)` tránh đếm một node `Order` nhiều lần nếu dữ liệu có nhiều cạnh `PLACED` tới cùng node. Nó không chữa được dữ liệu trùng; hãy dùng constraint/mô hình phù hợp nếu nghiệp vụ yêu cầu mỗi đơn chỉ thuộc một khách hàng.

**Đừng kết luận count luôn rẻ:** truy vấn đếm có điều kiện vẫn có thể phải duyệt rất nhiều relationship. Mục tiêu trước mắt là giảm **kích thước kết quả truyền về**, còn kế hoạch thực thi cần được đo riêng.

### 6.2. Đi qua hai bước quan hệ có thể nhân số hàng

~~~cypher
MATCH (c:Customer {customerId: $customerId})
      -[:PLACED]->(o:Order)
      -[:CONTAINS]->(p:Product)
RETURN o.orderId, p.sku;
~~~

Nếu mỗi khách hàng có 10.000 đơn và mỗi đơn có 8 sản phẩm, tập hàng trung gian có thể vào khoảng **80.000** hàng trước khi lọc hay tổng hợp, ngay cả khi chỉ có **một** customer gốc. `DISTINCT` hoặc DTO có thể loại hàng trùng ở kết quả nhưng không tự loại bỏ mọi công việc duyệt trước đó.

Nếu endpoint chỉ cần ID đơn và tổng tiền, hãy **không đưa `CONTAINS` vào query**. Việc bỏ một bước relationship thường quan trọng hơn thay kiểu trả về từ entity sang DTO.

### 6.3. Label/type và khóa chọn lọc

~~~cypher
// Quá rộng nếu chỉ cần một khách hàng:
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN o.orderId;

// Tập khởi đầu thường nhỏ hơn:
MATCH (c:Customer {customerId: $customerId})
      -[:PLACED]->(o:Order)
RETURN o.orderId;
~~~

Đặt uniqueness constraint trên `Customer.customerId` để bảo vệ khóa nghiệp vụ và hỗ trợ index seek:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

Truy vấn có thể bắt đầu từ `NodeUniqueIndexSeek` rồi `Expand(All)`. Tuy nhiên, **index seek ra một node** vẫn có thể kéo theo hàng nghìn relationship; cần tối ưu cả **điểm xuất phát lẫn fan-out**.

## 7. Phân trang: LIMIT ở cấp node gốc không phải LIMIT của collection quan hệ

### 7.1. Bẫy khi phân trang repository entity

Ví dụ một repository trả `Page<Customer>`:

~~~java
Page<Customer> page = customerRepository.findAll(
        org.springframework.data.domain.PageRequest.of(0, 20));
~~~

Giới hạn 20 thường áp dụng cho **tập root Customer**, không có nghĩa mỗi customer sẽ được tải tối đa 20 `Order`. Nếu một customer có 100.000 đơn, việc phân trang root có thể **chưa giải quyết** độ rộng của relationship.

Tương tự, `CustomerWithOrders.getOrders()` không tự có per-parent pagination. Khi client cần một tập con của collection, nên thiết kế một **operation riêng với query/response riêng**.

### 7.2. Query trang đầu của đơn hàng

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt,
       o.status AS status
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $pageSize;
~~~

Ở đây `createdAt` được giả định là một thuộc tính **temporal** phù hợp để sắp xếp, không phải chuỗi ngày giờ tùy ý. `orderId` là **tie-breaker** để thứ tự ổn định khi nhiều order có cùng timestamp. Hãy giới hạn `pageSize` ở application, không chuyển trực tiếp giá trị vô hạn từ client.

**Chú ý:** `LIMIT 20` giới hạn số hàng **trả ra** sau các toán tử trước đó. Nó không bảo đảm Neo4j chỉ mở rộng 20 relationship hoặc chỉ sắp xếp 20 đơn, đặc biệt khi có `ORDER BY`. Xem `PROFILE` để đo số hàng trước `Sort`.

### 7.3. Keyset pagination cho trang tiếp theo

Với trang thứ hai, dùng cursor từ **bản ghi cuối cùng của trang trước**:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.createdAt < datetime($cursorCreatedAt)
   OR (
        o.createdAt = datetime($cursorCreatedAt)
        AND o.orderId < $cursorOrderId
   )
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt,
       o.status AS status
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $pageSize;
~~~

Ví dụ sử dụng `$cursorCreatedAt` ở định dạng ISO 8601 có timezone và `$cursorOrderId` là ID của hàng cuối trang trước. Query trên áp dụng khi thuộc tính `o.createdAt` được lưu dưới kiểu temporal tương ứng, còn cursor đã được validate.

**Ưu điểm:** Tránh offset quá lớn ở tầng API và hỗ trợ thứ tự trang ổn định khi có khóa sắp xếp duy nhất. **Giới hạn:** Với các query bắt đầu từ customer rồi expand toàn bộ quan hệ, keyset pagination **không tự bảo đảm** giảm số cạnh cần duyệt. Phải xem plan và cân nhắc đường truy cập khác/index khi lượng quan hệ cực lớn. Nếu dữ liệu thay đổi giữa hai request, các trang cũng không mặc nhiên thuộc cùng snapshot giao dịch.

## 8. Tránh N+1 query và chọn chiến lược nhiều khách hàng

Anti-pattern:

~~~java
for (CustomerCard customer : customers) {
    // Mỗi khách hàng lại gọi database một lần để lấy số đơn.
    long count = orderService.countOrders(
            customer.getCustomerId());
    // Ghép DTO ...
}
~~~

Nếu một màn hình có 100 khách hàng, code có thể chạy **1 query lấy khách hàng + 100 query đếm đơn**. Đây là dạng N+1, làm tăng lượt network, transaction và áp lực connection pool.

Một giải pháp là query theo tập ID:

~~~cypher
UNWIND $customerIds AS id
MATCH (c:Customer {customerId: id})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN c.customerId AS customerId,
       count(DISTINCT o) AS orderCount
ORDER BY customerId;
~~~

Ứng dụng truyền một `List<String> customerIds` đã được giới hạn và có thể map kết quả thành `CustomerOrderCount`:

~~~java
public record CustomerOrderCount(
        String customerId,
        long orderCount
) {}
~~~

Kết quả: một lượt truy vấn thay vì N lượt. Nhưng một query lớn cũng có thể rất tốn kém nếu mỗi khách hàng có hàng triệu order. Hãy cân bằng kích thước batch, số hàng và phạm vi quan hệ.

### Lấy top-N cho **mỗi** khách hàng

Đừng dùng `LIMIT 3` sau `UNWIND` rồi mong được 3 đơn **mỗi khách hàng**: `LIMIT` ở query ngoài có thể chỉ giới hạn **tổng số hàng**.

Một cách tiếp cận là dùng **subquery theo từng node gốc**. Với Neo4j hỗ trợ cú pháp variable scope `CALL (c)` (Neo4j 5.23 trở lên và dòng hiện đại):

~~~cypher
UNWIND $customerIds AS id
MATCH (c:Customer {customerId: id})
CALL (c) {
    MATCH (c)-[:PLACED]->(o:Order)
    WITH o
    ORDER BY o.createdAt DESC, o.orderId DESC
    LIMIT 3
    RETURN collect(o.orderId) AS recentOrderIds
}
RETURN c.customerId AS customerId,
       recentOrderIds;
~~~

Mỗi lần chạy subquery có scope `c` riêng, nên `LIMIT 3` áp dụng cho tập order của **customer tương ứng**. Kiểm tra ngữ nghĩa với customer không có đơn và lựa chọn `OPTIONAL MATCH` hoặc mô hình response khi cần trả cả các khách hàng không có order. Trong phiên bản Neo4j cũ hơn, cú pháp truyền biến vào subquery có thể dùng `CALL { WITH c ... }`; đối chiếu tài liệu Cypher theo phiên bản.

Đây vẫn không nhất thiết là truy vấn rẻ: Neo4j có thể phải duyệt/sắp xếp nhiều order cho **mỗi** customer. Đừng bỏ qua `PROFILE`.

## 9. DTO summary, nested response và aggregate endpoint

Một API có thể cần:

~~~json
{
  "customerId": "C-101",
  "displayName": "Lan",
  "orderCount": 128,
  "recentOrders": [
    {"orderId": "O-500", "status": "PAID"},
    {"orderId": "O-499", "status": "CREATED"}
  ]
}
~~~

Không nhất thiết có một entity `Customer` chứa đúng toàn bộ JSON. Một chiến lược rõ ràng:

1. **Đọc `CustomerSummary`** bằng projection (chỉ hai thuộc tính gốc).
2. **Đọc `orderCount`** bằng truy vấn tổng hợp.
3. **Đọc tối đa N `OrderRow`** bằng query có `ORDER BY` và `LIMIT`.
4. **Ghép response DTO** tại service/controller, tránh trả entity trực tiếp.

Số query nhiều hơn một query cực lớn **không mặc định là xấu**: với endpoint đơn khách hàng, ba query nhỏ có thể rẻ và rõ ràng hơn một query dựng toàn graph. Ngược lại, với danh sách hàng trăm khách hàng, cần **batch** để tránh N+1. Chọn cách tốt hơn bằng số liệu.

### Chọn hình dạng response theo use case

| Use case | Shape dữ liệu nên cân nhắc | Đặc điểm |
| --- | --- | --- |
| Trang danh sách khách hàng | `CustomerCard` interface projection | Ít trường từ node gốc |
| Chi tiết một khách hàng đơn giản | `CustomerSummary` record/DTO | Hợp đồng response tường minh |
| 20 đơn gần đây | `OrderRow` từ Cypher + `Neo4jClient` | Kiểm soát ordering/limit/trường trả về |
| Báo cáo tổng số đơn theo customer | Aggregate DTO từ `count(...)` | Không dựng `Order` entity chỉ để đếm |
| Chỉnh sửa cả aggregate có liên kết | Entity graph đầy đủ phù hợp phạm vi ghi | Quan tâm tính nguyên tử và semantics `save` |
| Truy vấn đường đi phức tạp | DTO tùy shape / custom mapping | Trả đúng node, cạnh, độ sâu cần thiết |

## 10. Tránh những nhầm lẫn về “projection”

Trong hệ sinh thái Neo4j, từ **projection** có nhiều nghĩa:

| Khái niệm | Ý nghĩa | Có tạo graph riêng không? |
| --- | --- | --- |
| **Spring Data interface projection** | Chọn accessor Java cho phần dữ liệu cần đọc | Không |
| **Spring Data DTO projection** | Dựng class/record kết quả từ trường cần thiết | Không |
| **Cypher map projection** | Tạo map trực tiếp bằng Cypher, ví dụ `c { .customerId, .displayName }` | Không |
| **GDS graph projection** | Project node/relationship vào **in-memory graph catalog** cho thuật toán | **Có**, phục vụ Graph Data Science |

Ví dụ Cypher map projection:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
RETURN c {
    .customerId,
    .displayName
} AS customerCard;
~~~

Đây là một map do Cypher tạo và trả ra; **không phải** Java interface projection tự động của SDN. Nếu dùng `Neo4jClient`, bạn có thể giải mã map thành DTO một cách tường minh. Không nhầm `RETURN c { ... }` với `RETURN c` hoặc `gds.graph.project(...)`.

## 11. Transaction, tính nhất quán và rủi ro khi lưu entity thiếu dữ liệu

### 11.1. Projection chủ yếu cho đọc

Interface/DTO projection thích hợp để trả dữ liệu **chỉ đọc**. Khi cần cập nhật:

- Ghi trực tiếp bằng câu Cypher `MATCH ... SET ...` trong transaction thích hợp; hoặc
- Tải/mapping entity graph **đủ để thực hiện thao tác ghi** và dùng repository save với hiểu biết đúng về aggregate.

Đừng dùng một DTO chỉ có `customerId` và `displayName` để giả vờ đó là `Customer` đầy đủ, rồi ghi lại thành entity, bởi các relationship/thuộc tính không hiện diện trong view có thể bị xử lý sai.

### 11.2. Nhiều query đọc có cùng snapshot không?

Ví dụ ghép response bằng ba truy vấn ở phần 9 có thể thấy các thời điểm dữ liệu khác nhau nếu transaction khác đang ghi. Mặc định Neo4j có mức cô lập **read committed**, không có lời hứa snapshot cố định qua mọi lần đọc trong một transaction.

Nếu kết quả cần bất biến nghiệp vụ, phải xác định:

- Có cần gộp các truy vấn vào **cùng Spring transaction** không?
- Có cần cơ chế version, kiểm tra điều kiện hoặc khóa với các thao tác cạnh tranh ghi không?
- Có thể chấp nhận `orderCount` và `recentOrders` lệch nhau thoáng qua trên màn hình không?

`@Transactional(readOnly = true)` giúp khai báo ranh giới đọc và tham gia transaction manager phù hợp, **không tự nâng isolation lên serializable**.

### 11.3. Cẩn trọng với nhiều database và các nguồn dữ liệu khác

Một DTO API có thể ghép dữ liệu Neo4j với REST, Kafka hoặc database khác. Transaction của Neo4j **không tự bao trùm** những hệ thống đó. Nếu cần tính nhất quán toàn nghiệp vụ, hãy thiết kế version, idempotency, event/outbox hoặc cơ chế điều phối tương ứng, không dùng annotation transaction như một giao dịch phân tán mặc định.

## 12. Đo hiệu năng thật: Cypher, mapping, payload và bộ nhớ

Để xác định liệu projection/DTO có giúp giảm tải, đo theo **cùng workload và tập tham số**:

| Chỉ số | Ý nghĩa | Cách diễn giải |
| --- | --- | --- |
| `Rows` | Số hàng trong từng toán tử plan | Expand từ 1 customer thành hàng chục nghìn order? |
| `DB Hits` | Lượt truy cập dữ liệu phía Neo4j | Có quét quá nhiều node/relationship không? |
| `Estimated Rows` | Ước lượng của planner | Sai lệch lớn có thể dẫn tới plan kém |
| Thời gian query tại Neo4j | Chi phí thực thi Cypher | DTO nhỏ không giúp nếu scan/expand vẫn quá lớn |
| Số bản ghi và bytes trả về | Chi phí truyền qua Bolt và mapping | `RETURN` quá nhiều thuộc tính hoặc node? |
| CPU/heap/GC của ứng dụng | Chi phí mapping và serialization | Tạo object graph lớn gây áp lực bộ nhớ |
| Độ trễ p50/p95/p99 của endpoint | Trải nghiệm người dùng cuối | Kiểm tra hiệu năng dưới tải đồng thời |

Với query danh sách đơn:

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId, o.status, o.totalCents
ORDER BY o.orderId
LIMIT 20;
~~~

Khi an toàn:

~~~cypher
PROFILE
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId, o.status, o.totalCents
ORDER BY o.orderId
LIMIT 20;
~~~

Tìm các toán tử như `NodeUniqueIndexSeek`, `NodeByLabelScan`, `Expand(All)`, `Sort` và xem số hàng trung gian. `EXPLAIN` không chạy query; `PROFILE` **chạy thật**, nên cẩn trọng với các query ghi.

**Lưu ý thực nghiệm:** Cache ấm/lạnh, số lượng quan hệ theo customer, dữ liệu mới/cũ và độ đồng thời đều ảnh hưởng kết quả. Đừng chỉ kiểm tra khách hàng có 2 đơn rồi suy luận về khách hàng có 100.000 đơn.

### Bốn phép đo nên so sánh

1. Repository trả full `Customer` entity.
2. Repository trả `CustomerCard` projection.
3. DTO record qua `Neo4jClient` chỉ trả hai thuộc tính.
4. DTO tổng hợp/đơn hàng giới hạn `LIMIT` khi use case cần relationship.

Mỗi phương án phải trả **đúng kết quả nghiệp vụ cần so sánh**. Nếu phương án 1 tải toàn bộ đơn còn phương án 3 chỉ trả tên, có thể dùng số liệu để phát hiện over-fetching, nhưng không gọi đó là so sánh công bằng cho **cùng một yêu cầu dữ liệu**.

## 13. Kiểm thử trong Spring Data Neo4j

Integration test cần chạy với database Neo4j thực hoặc môi trường Testcontainers tương thích với Spring/SDN trong dự án; không thể xác minh plan graph chỉ bằng mock repository.

### Dữ liệu kiểm thử

Chuẩn bị:

- `C-001` có 0 đơn; `C-002` có 3 đơn; `C-003` có 500 đơn.
- Một số đơn có cùng `createdAt` để kiểm tra tie-breaker phân trang.
- Một đơn có nhiều `CONTAINS`; một số đơn ở trạng thái `PAID`, số khác `CREATED`.
- Constraint duy nhất cho `Customer.customerId`, `Order.orderId` và `Product.sku` nếu là định danh nghiệp vụ.

### Các case quan trọng

| Kiểm thử | Kỳ vọng |
| --- | --- |
| `findProjectedByCustomerId` | Trả đúng ID và tên, không lộ thuộc tính khác qua hợp đồng interface |
| `CustomerSummary` DTO | Giá trị constructor/record khớp tên field |
| Dynamic projection | Cùng ID ánh xạ đúng `CustomerCard` và `CustomerSummary` |
| `Neo4jClient` trả `OrderRow` | Không chứa `Product` và chỉ trả số hàng giới hạn |
| Customer không tồn tại | Trả empty/404 có chủ đích; không tạo entity ảo |
| Customer có 0 đơn | Count = 0, danh sách đơn rỗng |
| Customer có 500 đơn, limit 20 | Chỉ 20 hàng trả về cho API; kiểm tra plan có fan-out lớn không |
| Hai order cùng timestamp | Keyset pagination không lặp/mất hàng do thiếu tie-breaker |
| Trang nhiều khách hàng | Không có 1+N lượt query không chủ đích |
| Projection lồng nhau | Có giới hạn dữ liệu rõ, không đưa toàn collection lớn ra HTTP |
| Entity từ custom `RETURN c` | Không lưu lại phần graph thiếu dữ liệu như aggregate đầy đủ |
| Transaction đọc nhiều lần | Xác định mức nhất quán yêu cầu, không mặc định snapshot |

**Cần đo cả số query**: bật query logging hoặc instrumentation phù hợp trong môi trường kiểm thử, tránh ghi thông tin cá nhân/parameter nhạy cảm. Một bài test chỉ so JSON response vẫn có thể bỏ sót việc thực hiện 100 query hoặc duyệt hàng triệu cạnh.

## 14. Những anti-pattern cần tránh

### “Đổi kiểu trả về thành DTO chắc chắn giảm DB Hits”

**Sai.** DTO giảm shape dữ liệu Java; query tạo ra DTO vẫn có thể duyệt nhiều relationship hoặc trả nhiều cột rồi mới bỏ đi. Đo `PROFILE`.

### “Nested projection chỉ lấy những order đầu tiên”

**Sai nếu không có truy vấn/giới hạn cụ thể.** Giao diện `getOrders()` không định nghĩa phân trang; collection có thể rất lớn.

### “`Page<Customer>` đồng nghĩa mỗi customer có 20 order”

**Sai.** Pagination root entity không tự tạo giới hạn per-relationship. Tách operation lấy đơn có `ORDER BY`/`LIMIT`.

### “Có `LIMIT 20` thì database chỉ duyệt 20 cạnh”

**Không bảo đảm.** `Sort` hoặc `Expand` có thể xử lý nhiều hàng trước `LIMIT`, đặc biệt khi cần tìm 20 đơn mới nhất trên tập quan hệ lớn.

### “Custom query trả một node đủ để save đầy đủ entity”

**Không nên giả định.** Mapping entity và quan hệ trong SDN có các quy tắc riêng. Partial entity phục vụ đọc không phải aggregate đầy đủ để ghi trở lại.

### “Chỉ có một query là luôn tối ưu hơn ba query”

**Không chắc.** Một query dựng graph khổng lồ có thể tốn hơn ba query chọn lọc; nhưng N+1 vẫn rất tốn. So sánh dựa trên nghiệp vụ, độ lớn graph và đo lường.

### “Giống JPA, relationship không cần thì luôn lazy-load khi truy cập”

**Không nên áp dụng giả định đó.** SDN sử dụng query/mapping graph khác mô hình JPA phổ biến; phải xác định relationship nào được đọc từ kết quả query thật.

### “`@Transactional(readOnly=true)` biến nhiều lần đọc thành snapshot bất biến”

**Không.** Nó không mặc nhiên thay đổi mức cô lập read committed của Neo4j; dùng kiểm tra phiên bản/khóa khi nghiệp vụ đòi hỏi.

## 15. Bài thực hành: thiết kế endpoint không over-fetch

**Yêu cầu:** Endpoint `GET /customers/{id}/overview` trả:

- `customerId`, `displayName`;
- tổng số đơn;
- tối đa 5 đơn gần đây, chỉ gồm `orderId` và `status`.

**Bước 1 — Thiết kế DTO response.**

~~~java
import java.util.List;

public record CustomerOverview(
        String customerId,
        String displayName,
        long orderCount,
        List<OrderMini> recentOrders
) {}

public record OrderMini(String orderId, String status) {}
~~~

**Bước 2 — Chọn query phù hợp.** Có thể dùng `CustomerCard` cho thông tin gốc, `count(DISTINCT o)` cho tổng số đơn và query có `LIMIT 5` cho danh sách mới nhất. Khi chỉ phục vụ một customer, 2–3 truy vấn có thể dễ kiểm soát và kiểm thử hơn so với việc dựng nguyên entity graph.

**Bước 3 — Định nghĩa hợp đồng về dữ liệu vắng mặt.** Không có customer phải trả 404; customer có 0 order phải trả `orderCount=0` và `recentOrders=[]`. Không gọi `single()` trên kết quả trống mà không có xử lý lỗi rõ ràng.

**Bước 4 — Kiểm tra độ rộng.** Dùng customer có 500 đơn để quan sát `Rows` trong `Expand(All)`. Đặt giới hạn ở query đầu ra và đánh giá xem phải duyệt bao nhiêu order trước khi chọn 5 bản ghi.

**Bước 5 — Kiểm tra độ đúng.** Với nhiều đơn trùng `createdAt`, bảo đảm sắp xếp có `orderId` làm khóa phụ; query phải trả 5 bản ghi nhất quán với quy tắc sort.

**Bước 6 — Chạy thử nhiều khách hàng.** Nếu trang admin cần 100 overview, tránh lặp ba truy vấn 100 lần mà không đo. Cân nhắc query batch và subquery có giới hạn mỗi customer.

**Bước 7 — Đo trước/sau.** Đối chiếu full entity mapping với DTO + Cypher giới hạn, ghi số query, DB Hits, bytes dữ liệu và độ trễ p95. Chỉ chấp nhận cải tiến khi **kết quả nghiệp vụ không đổi** và chi phí giảm trên workload đại diện.

### Câu hỏi tự kiểm tra

**1. Interface projection khác DTO record ở đâu?**

Interface projection mô tả các accessor và thường được SDN tạo proxy/mapping theo dữ liệu entity; DTO record có constructor/field cố định, phù hợp hợp đồng dữ liệu bất biến. Cả hai đều cần query/mapping tương thích.

**2. Vì sao `CustomerWithOrders` nguy hiểm khi một khách hàng có 100.000 đơn?**

Vì nested projection chỉ biểu đạt quan hệ cần đọc, không tự giới hạn kích thước collection. Có thể tăng số node/cạnh được query, tạo object Java lớn và trả response quá rộng.

**3. `LIMIT 5` sau `ORDER BY` có chắc chỉ duyệt 5 order?**

Không. Neo4j có thể cần xem/sắp xếp nhiều order để chọn 5 bản ghi đúng; phải đo plan và xem có index/chiến lược truy cập tốt hơn.

**4. Tại sao không nên `save(...)` một entity được map từ custom query trả thiếu relationship?**

Vì entity đó không đại diện chắc chắn cho graph aggregate đầy đủ, dễ gây hiểu nhầm về tình trạng liên kết và semantics cập nhật. Dùng DTO cho read model hoặc ghi rõ các thuộc tính cần sửa bằng Cypher.

**5. Nếu query log cho thấy repository projection và DTO query có cùng Cypher, kết luận gì?**

Projection/DTO có thể khác chi phí Java mapping và payload; nhưng không thể mặc định DB Hits thấp hơn chỉ vì kiểu trả về khác.

## 16. Checklist trước khi xuất bản API dùng SDN

- [ ] Thiết kế **response DTO** theo trường dữ liệu người dùng cần, không trả entity graph trực tiếp theo thói quen.
- [ ] Xác định **độ rộng, độ sâu và fan-out** của các relationship trong từng use case.
- [ ] Dùng **closed interface projection** cho view đơn giản; dùng DTO/record hoặc `Neo4jClient` cho kết quả phẳng/tổng hợp.
- [ ] Kiểm tra projection lồng nhau có mở rộng collection quá lớn không.
- [ ] Không coi `Page<Root>` là per-relationship pagination; viết query riêng cho top-N child.
- [ ] Dùng `ORDER BY` ổn định, `LIMIT` có kiểm soát và cursor phù hợp khi phân trang.
- [ ] Phân biệt giới hạn số hàng **trả về** với số hàng **đã xử lý** trong plan.
- [ ] Tránh N+1 query; khi nhiều root, cân nhắc batch `UNWIND` hoặc subquery theo root.
- [ ] Dùng label, relationship type, business key và constraint/index phù hợp để tối ưu điểm xuất phát.
- [ ] Không ghi lại entity được tải một phần nếu chưa hiểu đúng semantics mapping/saving trong SDN.
- [ ] Không suy luận isolation hoặc lazy-loading từ kinh nghiệm JPA; kiểm tra hành vi Neo4j/SDN thực tế.
- [ ] Đo `EXPLAIN`/`PROFILE`, số query, DB Hits, bytes trả về, heap/GC và latency API.
- [ ] Integration test với đồ thị có **node bậc cao**, dữ liệu trùng timestamp và query không có kết quả.

## Tài liệu tham khảo

- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)
- [Spring Data Commons — Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html)
- [Spring Data Neo4j — Repositories](https://docs.spring.io/spring-data/neo4j/reference/repositories.html)
- [Spring Data Neo4j — Object Mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping.html)
- [Spring Data Neo4j — Neo4jClient](https://docs.spring.io/spring-data/neo4j/reference/neo4j-client.html)
- [Neo4j Cypher — Execution Plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)

**Kết luận:** Trong Spring Data Neo4j, tối ưu API đồ thị không chỉ là chọn Java DTO hay interface projection. Cần kiểm soát **graph nào được truy vấn**, **bao nhiêu node/relationship được duyệt**, **những thuộc tính nào được trả về** và **cách kết quả được ánh xạ**. Kết hợp projection/DTO với Cypher chọn lọc, giới hạn quan hệ, phân trang đúng ngữ nghĩa và phép đo thực tế sẽ giúp API vừa rõ hợp đồng dữ liệu vừa tránh tải đồ thị quá rộng.
