# Giới hạn đồ thị được tải bằng mô hình, projection hoặc Cypher

Một entity trong Spring Data Neo4j có thể liên kết với nhiều node khác, và mỗi node liên quan lại có thể tiếp tục liên kết đến những phần khác của đồ thị. Nếu một màn hình chỉ cần mã đơn hàng, trạng thái và tên khách hàng nhưng ứng dụng tải cả sản phẩm, lịch sử giao dịch, đánh giá và các quan hệ lân cận, chi phí truy vấn, truyền dữ liệu và ánh xạ object sẽ tăng không cần thiết.

Spring Data Neo4j (SDN) cung cấp ba cách chính để kiểm soát phần đồ thị cần tải:

1. **Mô hình entity và aggregate boundary:** định nghĩa ranh giới tải ngay trên domain model.
2. **Projection:** khai báo đúng property và relationship mà một use case cần đọc.
3. **Custom Cypher:** quyết định tường minh node, relationship và record được trả về.

Các cách này có thể kết hợp. Mục tiêu là trả đủ dữ liệu cho nghiệp vụ hiện tại, đồng thời tránh hydrate những nhánh không được sử dụng.

## 1. Vì sao tải quá nhiều đồ thị làm giảm hiệu năng?

Giả sử mô hình đơn hàng có cấu trúc:

```text
PurchaseOrder
  ├── Customer
  ├── OrderLine
  │     └── Product
  ├── Payment
  ├── Shipment
  └── OrderEvent
```

Một màn hình danh sách đơn hàng có thể chỉ cần `orderId`, `status`, `createdAt` và tên khách hàng. Nếu truy vấn tải mọi quan hệ đã khai báo trên entity, dữ liệu có thể mở rộng thành nhiều node và relationship cho mỗi đơn hàng.

Việc tải dư thừa gây ra nhiều loại chi phí:

- Database phải tìm và đọc thêm node, relationship cùng property.
- Kết quả trả về lớn hơn, làm tăng lượng dữ liệu truyền qua Bolt.
- SDN phải tạo thêm object Java, collection và relationship properties.
- Bộ nhớ heap tăng khi nhiều request cùng tải các graph lớn.
- JSON response có thể chứa dữ liệu mà client không sử dụng.
- Khi mô hình có quan hệ hai chiều hoặc vòng lặp, số nhánh được xét có thể tăng mạnh.

Vì vậy, hiệu năng không chỉ phụ thuộc vào số node gốc được tìm thấy. Cần quan tâm cả số node/relationship được hydrate cho mỗi node gốc và độ rộng của từng record kết quả.

## 2. SDN ánh xạ các quan hệ được khai báo trong mô hình

SDN dùng metadata của entity để xây dựng truy vấn và ánh xạ kết quả. Một field có `@Relationship` cho biết entity có một nhánh quan hệ cần được xử lý khi mapping.

Ví dụ mô hình đơn giản:

```java
import java.time.Instant;
import java.util.Set;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("PurchaseOrder")
public class PurchaseOrder {

    @Id
    private String orderId;

    private String status;
    private Instant createdAt;

    @Relationship(type = "PLACED_BY", direction = Relationship.Direction.OUTGOING)
    private Customer customer;

    @Relationship(type = "CONTAINS", direction = Relationship.Direction.OUTGOING)
    private Set<OrderLine> lines;

    @Relationship(type = "HAS_PAYMENT", direction = Relationship.Direction.OUTGOING)
    private Set<Payment> payments;
}
```

`OrderLine` có thể tiếp tục tham chiếu `Product`, còn `Customer` có thể tham chiếu các đơn hàng khác. SDN không áp dụng một con số depth cố định cho mọi truy vấn như cách một số phiên bản Neo4j-OGM cũ từng làm. Việc tạo graph mapping dựa trên các quan hệ trong mô hình và các giới hạn được khai báo.

Vì vậy, không lấy `@Depth` trong ví dụ Neo4j-OGM cũ làm cấu hình giới hạn graph cho SDN hiện đại. Trong SDN, hãy dùng aggregate boundary, projection hoặc custom query theo đúng use case.

Đây là điểm quan trọng khi thiết kế entity: thêm một quan hệ hai chiều để tiện điều hướng trong Java cũng có thể mở rộng graph mà SDN cần xét khi đọc. Chỉ khai báo các hướng điều hướng thật sự cần cho domain model; không thêm quan hệ ngược chỉ vì muốn truy cập tiện hơn ở một màn hình.

## 3. Chọn hướng quan hệ trong mô hình một cách có chủ đích

Neo4j relationship có hướng, còn `@Relationship` của SDN mặc định là `OUTGOING`. Hãy khai báo hướng dựa trên cách domain model điều hướng.

Ví dụ, nếu `PurchaseOrder` là aggregate root và nghiệp vụ thường đi từ đơn hàng đến khách hàng, có thể chỉ khai báo:

```java
@Relationship(type = "PLACED_BY", direction = Relationship.Direction.OUTGOING)
private Customer customer;
```

Không nhất thiết phải thêm một collection `orders` ở `Customer` nếu ứng dụng có thể truy vấn đơn hàng bằng repository riêng:

```java
List<PurchaseOrder> findByCustomer_CustomerId(String customerId);
```

Một mô hình hai chiều có thể khiến SDN tiếp tục xét các quan hệ được khai báo ở phía đối diện. Nếu `PurchaseOrder -> Customer` và `Customer -> PurchaseOrder` đều được mapping, một lần đọc có thể mở rộng sang nhiều đơn hàng khác của cùng khách hàng.

Điều này không có nghĩa mọi quan hệ hai chiều đều sai. Hãy dùng hai chiều khi domain thực sự cần điều hướng ở cả hai phía và đã xác định rõ phạm vi tải. Nếu chỉ cần một hướng trong một use case, query hoặc projection có thể giới hạn kết quả.

## 4. Đặt aggregate boundary bằng @Node

Khi một loại entity thường được tham chiếu từ aggregate khác nhưng không cần tải toàn bộ nội dung, SDN cho phép khai báo `aggregateBoundary` trên `@Node`.

Ví dụ, một đơn hàng có liên kết tới `Customer` và `Product`, nhưng khi tải aggregate `PurchaseOrder` ta chỉ cần identity của các node này:

```java
import java.util.Set;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node(aggregateBoundary = {Customer.class, Product.class})
public class PurchaseOrder {

    @Id
    private String orderId;

    private String status;

    @Relationship(type = "PLACED_BY")
    private Customer customer;

    @Relationship(type = "CONTAINS")
    private Set<OrderLine> lines;
}
```

Khi `Customer` hoặc `Product` được gặp như một aggregate boundary trong graph của entity này, SDN chỉ cần ID của entity tại ranh giới đó; nó không tiếp tục theo các relationship của entity đó và không tải các property khác của nó theo đường mapping này.

`aggregateBoundary` nhận một hoặc nhiều class. Đây là giới hạn mapping ở cấp entity model, phù hợp khi một số loại node thường đóng vai trò tham chiếu giữa các aggregate. Nó không phải bộ lọc quyền truy cập và không xóa relationship khỏi database.

Nếu một màn hình cần thêm `customer.name`, hãy dùng projection hoặc truy vấn riêng cho use case đó. Interface projection có thể mô tả một góc nhìn rộng hơn aggregate boundary đã khai báo. Vì vậy, hãy xem aggregate boundary là mặc định cho mapping aggregate, còn projection là hợp đồng dữ liệu cụ thể của từng truy vấn.

## 5. Khi nào nên dùng aggregate boundary?

Aggregate boundary hữu ích khi:

- Một entity được tham chiếu từ nhiều aggregate nhưng chỉ cần identity trong phần lớn thao tác.
- Một node có nhiều quan hệ lân cận và không nên được mở rộng trong mọi lần đọc.
- Domain model có các nhánh lớn, ví dụ `Customer`, `Product`, `Organization` hoặc `Catalog`.
- Muốn giới hạn cả việc tải và ranh giới persistence theo cấu trúc aggregate.

Không nên đặt boundary cho một type nếu hầu hết use case cần đọc các property hoặc relationship của nó. Trong trường hợp đó, projection cụ thể thường linh hoạt hơn.

Aggregate boundary cũng không thay thế việc thiết kế query. Nếu custom Cypher tự trả thêm node/relationship hoặc DTO có thêm dữ liệu, phần dữ liệu được query tường minh vẫn phải tuân theo câu lệnh đó.

## 6. Dùng interface projection để chỉ đọc các property cần thiết

Projection định nghĩa một góc nhìn hẹp hơn entity. Interface projection chỉ khai báo các accessor cần dùng. SDN dùng tên accessor để xác định property tương ứng trong domain model và có thể giới hạn property/relationship được truyền qua wire.

Ví dụ màn hình danh sách đơn hàng chỉ cần mã, trạng thái và tên khách hàng:

```java
public interface OrderCard {

    String getOrderId();

    String getStatus();

    CustomerCard getCustomer();

    interface CustomerCard {
        String getName();
    }
}
```

Repository:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PurchaseOrderRepository
        extends Neo4jRepository<PurchaseOrder, String> {

    List<OrderCard> findByStatus(String status);
}
```

`OrderCard` không khai báo `lines`, `payments` hoặc các relationship khác. Nested projection `CustomerCard` chỉ yêu cầu `name`. Vì vậy, SDN có thể tạo truy vấn chỉ lấy phần dữ liệu mà projection cần.

Interface projection là proxy đọc dựa trên entity gốc. Tên accessor phải khớp property trong domain model; nếu property là `customer`, accessor phải là `getCustomer()`. Nested projection có thể tiếp tục giới hạn các property ở node liên quan.

## 7. Projection nhiều cấp để giới hạn từng nhánh

Nếu một màn hình cần thông tin đơn hàng, một phần dòng hàng và tên sản phẩm, hãy mô tả từng cấp:

```java
import java.util.List;

public interface OrderDetailView {

    String getOrderId();

    String getStatus();

    List<LineView> getLines();

    interface LineView {
        Integer getQuantity();
        ProductView getProduct();
    }

    interface ProductView {
        String getSku();
        String getName();
    }
}
```

Projection này biểu diễn ba cấp dữ liệu:

1. `PurchaseOrder`: chỉ `orderId` và `status`.
2. `OrderLine`: chỉ `quantity` và quan hệ `product`.
3. `Product`: chỉ `sku` và `name`.

SDN hỗ trợ multi-level projection và tạo truy vấn theo cấu trúc lồng nhau. Projection logic không đi theo chu trình vô hạn nếu mô hình có quan hệ vòng; nó tạo query không chu trình theo projection đã khai báo.

Các lớp `@RelationshipProperties` cũng là một phần của mapping graph. Nếu relationship có property như `quantity`, `unitPrice` hoặc `addedAt`, hãy đưa các trường cần thiết vào nested projection tương ứng.

## 8. Projection kín và projection mở

Projection kín (closed projection) chỉ khai báo accessor ánh xạ tới property của domain type. SDN biết chính xác dữ liệu mà projection cần và có thể tối ưu query.

Ví dụ:

```java
public interface CustomerNameView {
    String getCustomerId();
    String getName();
}
```

Projection mở (open projection) có thể dùng biểu thức như `@Value`/SpEL để tính property từ target. Vì biểu thức có thể truy cập các field khác của target, framework khó xác định chính xác tập property cần tải. Nếu mục tiêu chính là giảm dữ liệu đọc, ưu tiên closed projection và tính giá trị dẫn xuất sau khi đã nhận đúng các trường cần thiết.

Nếu phép tính cần nhiều dữ liệu hoặc quy tắc phức tạp, cân nhắc DTO projection hoặc custom query thay vì nhúng logic lớn trong SpEL.

## 9. Dùng DTO projection cho response có cấu trúc cố định

DTO phù hợp khi API cần một cấu trúc trả về rõ ràng, không cần proxy tới entity. Java record là cách ngắn gọn để định nghĩa DTO:

```java
import java.time.Instant;

public record OrderListItem(
    String orderId,
    String status,
    Instant createdAt
) {}
```

Nếu query được tạo từ repository domain model, các property domain và relationship được xác định theo metadata. Với custom query, DTO có thể nhận thêm property từ record trả về. Tên property bổ sung phải khớp chính xác với tên alias trong kết quả; kiểu dữ liệu phải là kiểu đơn giản mà SDN hỗ trợ hoặc persistent entity đã biết. Collection của các kiểu phù hợp được hỗ trợ, nhưng không nên thiết kế DTO projection với `Map` như một property bổ sung.

Ví dụ DTO nhận số dòng hàng từ custom query:

Thêm phương thức sau vào `PurchaseOrderRepository` đã khai báo ở phần interface projection:

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    MATCH (o:PurchaseOrder {orderId: $orderId})
    OPTIONAL MATCH (o)-[:CONTAINS]->(line:OrderLine)
    RETURN o, count(line) AS lineCount
    """)
Optional<OrderSummary> findSummary(@Param("orderId") String orderId);
```

```java
public record OrderSummary(
    String orderId,
    String status,
    Long lineCount
) {}
```

Trong ví dụ này, `orderId` và `status` được lấy từ node `o`; `lineCount` là property bổ sung lấy từ record. Alias `lineCount` phải trùng tên component DTO. Nếu alias khác chữ hoa/thường hoặc tên, SDN không thể tự đoán ý định.

## 10. Projection động khi nhiều use case dùng chung finder

Nếu một điều kiện tìm kiếm cần trả về nhiều dạng dữ liệu, có thể dùng dynamic projection:

```java
import java.util.List;

<T> List<T> findByStatus(String status, Class<T> projectionType);
```

Đây là method bổ sung vào `PurchaseOrderRepository` ở phần 6; nó cho phép truyền kiểu projection tại thời điểm gọi. Ví dụ:

```java
List<PurchaseOrder> fullOrders = repository.findByStatus("OPEN", PurchaseOrder.class);

List<OrderCard> cards = repository.findByStatus("OPEN", OrderCard.class);

List<OrderListItem> items = repository.findByStatus("OPEN", OrderListItem.class);
```

Dynamic projection hữu ích khi các màn hình cần những tập property khác nhau nhưng dùng cùng điều kiện lọc. Dù vậy, không nên tạo quá nhiều kiểu projection gần giống nhau nếu chúng không đại diện cho một hợp đồng dữ liệu có ý nghĩa.

## 11. Dùng custom Cypher khi cần kiểm soát chính xác graph

Projection là lựa chọn tốt khi query có thể được sinh từ domain model. Khi cần pattern phức tạp, giới hạn số relationship, lọc theo property ở node liên quan hoặc kết hợp nhiều nhánh, custom Cypher cho phép chỉ định rõ phần graph cần trả về.

Ví dụ chỉ tải một đơn hàng và các dòng hàng trực tiếp:

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    MATCH (o:PurchaseOrder {orderId: $orderId})
    OPTIONAL MATCH (o)-[r:CONTAINS]->(line:OrderLine)
    RETURN o, collect(r), collect(line)
    """)
Optional<PurchaseOrder> findOrderWithLines(@Param("orderId") String orderId);
```

Query trả node gốc `o`, các relationship `CONTAINS` và node `OrderLine` trong một record. SDN dùng các node/relationship được trả về để hydrate phần graph tương ứng với entity.

Nếu chỉ trả `o`, các relationship không có trong record không được hydrate từ query đó. Đây là cách có chủ đích để giảm graph, nhưng kết quả là một entity chỉ được tải một phần. Không giả định object đó chứa toàn bộ quan hệ trong database.

## 12. Vì sao cần collect relationship và node?

SDN xử lý kết quả custom query theo record. Với một root node có nhiều relationship, query dạng:

```cypher
MATCH (o:PurchaseOrder {orderId: $orderId})-[r:CONTAINS]->(line:OrderLine)
RETURN o, r, line
```

có thể trả nhiều record cho cùng một `PurchaseOrder`, mỗi record chứa một dòng hàng. Nếu map trực tiếp, root node có thể lặp lại và graph không được tổng hợp như mong muốn.

Để có một record cho mỗi root node, hãy gom relationship và node liên quan:

```cypher
MATCH (o:PurchaseOrder {orderId: $orderId})
OPTIONAL MATCH (o)-[r:CONTAINS]->(line:OrderLine)
RETURN o, collect(r) AS lineRelationships, collect(line) AS lines
```

Kết quả chỉ có một record cho đơn hàng đó. `collect()` bỏ qua giá trị null do `OPTIONAL MATCH`, vì vậy đơn hàng không có dòng hàng vẫn có thể được trả về với các collection rỗng.

Khi custom query trả về nhiều root node, cần bảo đảm mỗi root node chỉ xuất hiện một lần trong kết quả sau khi gom các nhánh tương ứng.

## 13. Tránh Cartesian product khi tải nhiều nhánh

Giả sử một đơn hàng có 4 dòng hàng và 3 lần thanh toán. Nếu cùng lúc `MATCH` cả hai nhánh:

```cypher
MATCH (o:PurchaseOrder {orderId: $orderId})
OPTIONAL MATCH (o)-[lineRel:CONTAINS]->(line:OrderLine)
OPTIONAL MATCH (o)-[paymentRel:HAS_PAYMENT]->(payment:Payment)
RETURN o,
       collect(lineRel), collect(line),
       collect(paymentRel), collect(payment)
```

hai nhánh có thể nhân số dòng trung gian thành 4 × 3 trước khi `collect`, tạo dữ liệu lặp và tốn tài nguyên. `collect(DISTINCT ...)` có thể loại một số bản ghi trùng, nhưng không loại bỏ chi phí của tích Descartes đã hình thành.

Hãy tách các nhánh độc lập thành subquery để mỗi nhánh được gom riêng:

```cypher
MATCH (o:PurchaseOrder {orderId: $orderId})
CALL {
    WITH o
    OPTIONAL MATCH (o)-[r:CONTAINS]->(line:OrderLine)
    RETURN collect(r) AS lineRelationships,
           collect(line) AS lines
}
CALL {
    WITH o
    OPTIONAL MATCH (o)-[r:HAS_PAYMENT]->(payment:Payment)
    RETURN collect(r) AS paymentRelationships,
           collect(payment) AS payments
}
RETURN o,
       lineRelationships, lines,
       paymentRelationships, payments
```

Mỗi subquery trả một record chứa collection của nhánh tương ứng, tránh nhân chéo giữa các collection. Dùng tên alias rõ ràng để dễ kiểm tra kết quả và mapping.

## 14. Truy vấn sâu hơn nhưng chỉ lấy một nhánh có giới hạn

Nếu use case cần đơn hàng, dòng hàng và sản phẩm nhưng không cần toàn bộ graph của sản phẩm, hãy giới hạn đường đi:

```cypher
MATCH (o:PurchaseOrder {orderId: $orderId})
OPTIONAL MATCH (o)-[contains:CONTAINS]->(line:OrderLine)
OPTIONAL MATCH (line)-[forProduct:FOR_PRODUCT]->(product:Product)
RETURN o,
       collect(contains),
       collect(line),
       collect(forProduct),
       collect(product)
```

Query này chỉ yêu cầu các node/relationship trên nhánh đã nêu. Nó không tìm những đơn hàng khác của khách hàng, các sản phẩm cùng danh mục hoặc các đánh giá sản phẩm nếu các pattern đó không có trong query.

Nếu cùng một root có nhiều nhánh sâu độc lập, hãy tách chúng thành subquery như phần trước để tránh tích Descartes. Nếu chỉ cần vài property của sản phẩm chứ không cần entity `Product`, hãy trả scalar property và ánh xạ thành DTO thay vì hydrate node.

## 15. Khi nào nên dùng Neo4jClient thay cho entity mapping?

Không phải kết quả nào cũng cần biến thành entity graph. Với báo cáo, thống kê hoặc danh sách hiển thị phẳng, `Neo4jClient` có thể trả đúng các cột cần dùng.

Ví dụ chỉ lấy mã đơn hàng, trạng thái và số dòng hàng:

```java
import java.util.Collection;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

public record OrderRow(String orderId, String status, long lineCount) {}

@Repository
public class OrderReadDao {

    private final Neo4jClient neo4jClient;

    public OrderReadDao(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public Collection<OrderRow> findOrderRows(String status) {
        return neo4jClient.query("""
            MATCH (o:PurchaseOrder {status: $status})
            OPTIONAL MATCH (o)-[:CONTAINS]->(line:OrderLine)
            RETURN o.orderId AS orderId,
                   o.status AS status,
                   count(line) AS lineCount
            ORDER BY o.orderId
            """)
            .bind(status).to("status")
            .fetchAs(OrderRow.class)
            .mappedBy((typeSystem, record) -> new OrderRow(
                record.get("orderId").asString(),
                record.get("status").asString(),
                record.get("lineCount").asLong()
            ))
            .all();
    }
}
```

Kết quả là DTO phẳng, không có entity hoặc relationship nào được hydrate. Đây là lựa chọn phù hợp cho dashboard, báo cáo, autocomplete và API danh sách có cấu trúc cố định.

Quy tắc chọn API:

| Nhu cầu | Cách phù hợp |
|---|---|
| Domain object cần các relationship đã khai báo | Repository hoặc `Neo4jTemplate` |
| Chỉ một số property/relationship của domain object | Interface/DTO projection |
| Query cần graph cụ thể, có điều kiện hoặc traversal riêng | Repository `@Query` hoặc `Neo4jTemplate` với Cypher |
| Chỉ cần scalar, aggregate hoặc DTO phẳng | `Neo4jClient` |

## 16. Giới hạn số lượng kết quả và độ sâu traversal trong Cypher

Ngoài việc giới hạn loại entity được trả về, hãy giới hạn số lượng node/relationship được duyệt. Không dùng variable-length path không giới hạn khi nghiệp vụ chỉ cần một số bước nhất định.

Ví dụ chỉ duyệt tối đa ba bước:

```cypher
MATCH p = (start:Category {categoryId: $categoryId})-[:PARENT_OF*1..3]->(child:Category)
RETURN start, collect(nodes(p)), collect(relationships(p))
```

Giới hạn `*1..3` ngăn query đi sâu tùy ý. Với query nhiều đường đi, cần gom các node/relationship về một record mỗi root và cân nhắc loại bỏ trùng lặp trước khi mapping.

Độ sâu traversal trong Cypher và độ sâu mapping entity là hai khái niệm khác nhau:

- Pattern Cypher quyết định những đường đi database phải tìm.
- Các node/relationship trong `RETURN` quyết định dữ liệu có sẵn cho mapper.
- Projection và aggregate boundary quyết định phần entity model được hydrate trong query được SDN sinh.

Giới hạn một trong ba lớp không tự động thay thế giới hạn ở hai lớp còn lại.

## 17. Phân trang và chỉ tải trang dữ liệu cần hiển thị

Đối với danh sách lớn, đừng tải toàn bộ root entity cùng mọi relationship rồi mới cắt danh sách ở Java. Hãy giới hạn ngay trong truy vấn bằng `Pageable`, `LIMIT`/`SKIP` hoặc cơ chế scrolling phù hợp với repository.

Ví dụ custom Cypher giới hạn số đơn hàng:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    MATCH (o:PurchaseOrder {status: $status})
    RETURN o
    ORDER BY o.createdAt DESC, o.orderId ASC
    SKIP $skip
    LIMIT $limit
    """)
List<PurchaseOrder> findOrderPage(
    @Param("status") String status,
    @Param("skip") long skip,
    @Param("limit") long limit
);
```

Query trên chỉ trả các node `PurchaseOrder`. Nếu màn hình cần tên khách hàng hoặc tổng dòng hàng, hãy dùng projection/DTO và bổ sung đúng pattern hoặc scalar property cần thiết. Khi dùng `Page<T>` với custom query, cần cung cấp count query phù hợp nếu repository method yêu cầu tổng số phần tử.

Để phân trang ổn định, `ORDER BY` nên có tiêu chí phụ duy nhất như `orderId`. Nếu chỉ sắp xếp theo timestamp có thể trùng, các phần tử có cùng timestamp có thể đổi vị trí giữa các trang.

## 18. Lưu ý khi lưu lại entity đã tải một phần

Một entity được tải qua projection hoặc custom Cypher có thể không chứa tất cả relationship trong database. Nếu lấy object đó rồi gọi `save` như thể nó là aggregate đầy đủ, SDN có thể hiểu các relationship không có trong object là quan hệ cần loại bỏ.

Ví dụ, màn hình chỉ đọc `PurchaseOrder` và `Customer` nhưng bỏ qua `payments`. Không nên lấy entity partial đó, thay `status` rồi gọi `repository.save(order)` nếu thao tác save có thể đồng bộ toàn bộ graph theo mapping.

Các cách an toàn hơn:

- Dùng projection chỉ cho read path; khi cập nhật, tải aggregate đầy đủ theo đúng phạm vi cần ghi rồi áp dụng command.
- Dùng `Neo4jTemplate.saveAs(domainObject, Projection.class)` nếu muốn persistence chỉ cập nhật các field/relationship trong projection blueprint.
- Dùng custom Cypher `SET` cho một cập nhật property đơn lẻ khi không cần đồng bộ toàn bộ entity graph.
- Xác định rõ aggregate boundary và quyền sở hữu relationship trước khi thiết kế thao tác save.

Projection có thể dùng làm blueprint cho persistence, nhưng phải hiểu chính xác field và relationship nào được cập nhật. Chỉ tải dữ liệu cần cho ghi và bảo đảm không làm mất các quan hệ mà nghiệp vụ cần giữ.

## 19. Đánh giá hiệu năng bằng EXPLAIN và PROFILE

Giới hạn graph trong Java mapping không thay thế việc tối ưu query plan. Sau khi thu hẹp dữ liệu trả về, hãy kiểm tra database có tìm root node hiệu quả và tránh tạo quá nhiều row trung gian hay không.

Các bước kiểm tra:

1. Dùng `EXPLAIN` để xem kế hoạch thực thi mà không chạy query.
2. Dùng `PROFILE` trên dữ liệu thử nghiệm phù hợp để xem số row và DB hits thực tế.
3. Kiểm tra điều kiện lọc root có dùng index/constraint phù hợp không.
4. Kiểm tra số record trung gian trước `collect`, đặc biệt khi query có nhiều nhánh relationship.
5. Đo kích thước kết quả và thời gian mapping khi trả entity graph so với DTO.
6. Kiểm tra heap và độ trễ khi có nhiều request đồng thời.

Ví dụ:

```cypher
PROFILE
MATCH (o:PurchaseOrder {orderId: $orderId})
OPTIONAL MATCH (o)-[r:CONTAINS]->(line:OrderLine)
RETURN o, collect(r), collect(line)
```

Nếu query trả một root node nhưng phải duyệt hàng trăm nghìn relationship trước khi `collect`, việc gom kết quả không làm chi phí traversal biến mất. Hãy giới hạn pattern, lọc sớm, dùng index cho điều kiện tìm root và chỉ tải các nhánh cần thiết.

## 20. Kiểm thử phần graph được tải

Kiểm thử nên xác nhận cả dữ liệu trả về lẫn những nhánh không được yêu cầu. Có thể chuẩn bị một đơn hàng có customer, nhiều line item, payment và event.

Các trường hợp nên kiểm tra:

1. Repository trả `PurchaseOrder` đầy đủ theo use case chi tiết và có các relationship mong muốn.
2. Interface projection chỉ đọc accessor đã khai báo, gồm cả nested projection.
3. DTO projection nhận property domain và các alias bổ sung đúng tên.
4. Aggregate boundary chỉ hydrate identity của type nằm ở ranh giới trong query tương ứng.
5. Custom Cypher trả một record cho mỗi root và gom đủ relationship/target node.
6. Đơn hàng không có relationship vẫn được trả về khi dùng `OPTIONAL MATCH`.
7. Query nhiều nhánh không nhân bản collection do Cartesian product.
8. DTO/Neo4jClient chỉ trả scalar và không vô tình hydrate entity graph.
9. Phân trang trả đúng số phần tử và thứ tự ổn định.
10. Cập nhật entity đã tải một phần không làm mất relationship ngoài ý muốn.

Không chỉ kiểm tra số lượng root entity. Hãy kiểm tra danh sách relationship, node liên quan và trạng thái database sau thao tác ghi.

## 21. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Một truy vấn tải quá nhiều node | Mô hình có nhiều relationship hoặc nhiều hướng điều hướng | Thu hẹp model, dùng aggregate boundary hoặc projection. |
| Entity root bị lặp trong kết quả `@Query` | Mỗi relationship tạo một record riêng | `collect()` relationship và node liên quan để có một record mỗi root. |
| Collection relationship có phần tử trùng | Nhiều nhánh tạo Cartesian product | Tách nhánh bằng subquery; không chỉ dựa vào `DISTINCT` sau khi đã tạo tích chéo. |
| Node liên quan có ID nhưng thiếu property | Type được đặt làm aggregate boundary | Dùng projection hoặc query riêng nếu use case cần property của node đó. |
| Projection không tìm thấy property | Tên accessor không khớp tên property domain | Đối chiếu getter với field/property mapping. |
| DTO không nhận cột bổ sung | Alias trong Cypher khác tên component/property DTO | Dùng alias khớp chính xác và kiểu dữ liệu được hỗ trợ. |
| Custom Cypher trả entity thiếu quan hệ | Query không trả các node/relationship cần hydrate | Trả root, relationship và target node cần thiết trong record. |
| Lưu entity partial làm mất relationship | Object được xem như graph đầy đủ dù query chỉ tải một phần | Dùng read projection riêng, tải đủ graph khi ghi hoặc dùng `saveAs`/Cypher cập nhật có chủ đích. |
| Query nhanh ở dev nhưng chậm ở production | Graph lớn hơn, index thiếu hoặc số row trung gian tăng | Kiểm tra `PROFILE`, index, cardinality và nhánh traversal. |
| Phân trang có phần tử đổi trang | Thứ tự sort không duy nhất | Thêm tiêu chí phụ ổn định vào `ORDER BY`. |

## 22. Quy trình giới hạn đồ thị được tải

1. Xác định màn hình hoặc nghiệp vụ thực sự cần property và relationship nào.
2. Kiểm tra model entity có quan hệ hai chiều hoặc nhánh mở rộng ngoài ý muốn không.
3. Đặt `aggregateBoundary` cho các loại entity chỉ cần identity trong phần lớn thao tác.
4. Dùng closed interface projection hoặc DTO projection cho read model cụ thể.
5. Dùng nested projection khi cần một số property ở các cấp quan hệ tiếp theo.
6. Dùng custom Cypher khi cần giới hạn pattern, số bước hoặc nhiều nhánh cụ thể.
7. Với custom entity mapping, trả một record cho mỗi root và collect node/relationship cần thiết.
8. Tách các nhánh độc lập thành subquery để tránh Cartesian product.
9. Dùng `Neo4jClient` cho kết quả scalar, thống kê hoặc DTO phẳng không cần hydrate graph.
10. Giới hạn số root bằng pagination/limit và dùng thứ tự ổn định.
11. Không lưu ngược entity partial như một aggregate đầy đủ; xác định rõ write boundary.
12. Dùng `EXPLAIN`/`PROFILE` và integration test để xác nhận query plan, graph được hydrate và trạng thái dữ liệu sau ghi.

## 23. Ghi nhớ

SDN ánh xạ graph dựa trên domain model và các relationship được khai báo. Một mô hình có nhiều nhánh hoặc quan hệ hai chiều có thể làm truy vấn tải rộng hơn nhu cầu của use case. `@Node(aggregateBoundary = {...})` giúp giới hạn một số type ở mức ID; interface/DTO projection giới hạn property và relationship theo hợp đồng đọc; custom Cypher cho phép chỉ định chính xác node, relationship và đường đi cần trả về.

Với custom query trả entity, hãy gom relationship và target node để có một record cho mỗi root, tránh Cartesian product giữa các nhánh. Với báo cáo hoặc kết quả phẳng, dùng DTO/`Neo4jClient` thay vì hydrate entity graph. Hãy coi entity được tải một phần là read model: trước khi ghi, tải đủ graph cần thiết hoặc dùng persistence projection/Cypher có phạm vi cập nhật rõ ràng để không làm mất relationship. Kết hợp giới hạn graph với index, pagination, `PROFILE` và integration test sẽ giúp giảm chi phí truy vấn, truyền dữ liệu và mapping object.

## Tài liệu tham khảo

- [Spring Data Neo4j – Projections and aggregate boundaries](https://docs.spring.io/spring-data/neo4j/reference/projections/sdn-projections.html)
- [Spring Data Neo4j – Custom queries and relationship mapping](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
- [Spring Data Neo4j – Metadata-based mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
- [Spring Data Neo4j – FAQ: Custom queries and mapping](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
