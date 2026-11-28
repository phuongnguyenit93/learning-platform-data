# Chuyển từ JPA: thiết kế lại liên kết theo câu hỏi nghiệp vụ

Chuyển một ứng dụng từ JPA sang Spring Data Neo4j (SDN) không đơn thuần là đổi `@ManyToOne` thành `@Relationship`. JPA thường mô hình hóa dữ liệu quanh bảng, khóa chính, khóa ngoại và ranh giới transaction của relational database. Neo4j mô hình hóa dữ liệu quanh node, relationship và những đường đi mà ứng dụng cần truy vấn. Vì vậy, một migration tốt phải bắt đầu từ câu hỏi nghiệp vụ và cách ứng dụng cần đi qua graph.

Ví dụ, trong hệ thống bán hàng, relational model có thể gồm `customer`, `purchase_order`, `order_item` và `product`. Một câu hỏi như “khách hàng đã mua sản phẩm nào?”, “những khách hàng mua cùng sản phẩm là ai?” hoặc “sản phẩm nào thường được mua cùng nhau?” đi qua nhiều khóa ngoại. Trong graph model, các liên kết `PLACED` và `CONTAINS` trở thành relationship có ý nghĩa trực tiếp, giúp query thể hiện đường đi nghiệp vụ rõ ràng.

Bài học này trình bày cách đọc mô hình JPA hiện tại, rút ra câu hỏi nghiệp vụ quan trọng, thiết kế node và relationship tương ứng, ánh xạ bằng SDN, viết Cypher theo traversal thực tế và chuyển dữ liệu có kiểm chứng. Mục tiêu là giữ lại ý nghĩa nghiệp vụ của dữ liệu trong khi thiết kế graph phù hợp với cách ứng dụng đọc và cập nhật dữ liệu.

## 1. Khác biệt về tư duy mô hình hóa

Trong relational model, entity thường tương ứng với table; association được biểu diễn bằng foreign key hoặc join table. ORM dùng mapping metadata để dựng SQL join, quản lý persistence context và đồng bộ object state với các hàng dữ liệu.

Trong Neo4j, node biểu diễn thực thể hoặc khái niệm nghiệp vụ; relationship biểu diễn mối liên hệ có tên và có hướng giữa hai node. Property có thể nằm trên node hoặc relationship tùy ý nghĩa của dữ liệu.

| Khía cạnh | JPA / relational model | Neo4j / graph model |
|---|---|---|
| Thực thể | Row trong table | Node có một hoặc nhiều label |
| Định danh | Primary key | Property được chọn làm ID nghiệp vụ hoặc ID do database quản lý |
| Liên kết | Foreign key, join table | Relationship có type và direction |
| Nhiều-nhiều | Join table | Relationship trực tiếp hoặc relationship có properties |
| Thuộc tính của liên kết | Cột trên join table/entity liên kết | Property trên relationship hoặc node trung gian |
| Truy vấn liên kết | JOIN giữa các table | MATCH theo pattern và traversal qua relationship |
| Nạp dữ liệu | Lazy/eager fetch, entity graph, join fetch | Mapping graph theo query và aggregate boundary |
| Đồng bộ ghi | Dirty checking trong persistence context | SDN đồng bộ node/relationship theo entity graph được lưu |

Không có quy tắc rằng một table luôn phải trở thành một node hoặc một foreign key luôn phải trở thành một relationship. Đó là điểm khởi đầu để phân tích, không phải kết quả thiết kế cuối cùng.

## 2. Bắt đầu từ câu hỏi nghiệp vụ, không bắt đầu từ annotation

Trước khi viết `@Node` hoặc `@Relationship`, hãy thu thập những truy vấn mà hệ thống thực sự cần hỗ trợ. Ví dụ với domain thương mại:

1. Một khách hàng đã đặt những đơn hàng nào?
2. Một đơn hàng gồm những sản phẩm nào, số lượng và giá tại thời điểm mua là bao nhiêu?
3. Những khách hàng nào đã mua cùng một sản phẩm?
4. Sản phẩm nào thường được mua cùng các sản phẩm trong giỏ hàng?
5. Những sản phẩm nào có thể được đề xuất cho khách hàng dựa trên lịch sử mua hàng?
6. Một đơn hàng thuộc khách hàng nào và có những dòng hàng nào?

Từ câu hỏi, xác định đường đi cần có:

```text
(Customer)-[:PLACED]->(PurchaseOrder)
                           |
                           + -[:CONTAINS {quantity, unitPriceMinor}]->(Product)
```

Mỗi câu hỏi nên được diễn đạt thành một pattern graph. Nếu truy vấn thường xuyên phải đi từ `Customer` qua `PurchaseOrder` tới `Product`, các relationship đó cần được mô hình hóa trực tiếp và có tên thể hiện nghiệp vụ.

Một graph model tốt giúp người đọc nhìn query và hiểu được nghiệp vụ mà không phải suy luận qua nhiều tên khóa ngoại.

## 3. Đọc mô hình JPA hiện tại

Giả sử ứng dụng JPA có các entity sau:

```java
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.List;

import jakarta.persistence.*;

@Entity
class Customer {
    @Id
    private Long id;

    private String name;

    @OneToMany(mappedBy = "customer")
    private List<PurchaseOrder> orders = new ArrayList<>();
}
```

```java
@Entity
class PurchaseOrder {
    @Id
    private Long id;

    private ZonedDateTime placedAt;
    private String status;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL)
    private List<OrderItem> items = new ArrayList<>();
}
```

```java
@Entity
class OrderItem {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY)
    private Product product;

    private int quantity;
    private long unitPriceMinor;
    private String currencyCode;
    private String lineNumber;
}
```

```java
@Entity
class Product {
    @Id
    private Long id;

    private String sku;
    private String name;
    private long currentPriceMinor;
}
```

Relational schema thường có các khóa ngoại:

```text
customer
  id (PK)
  name

purchase_order
  id (PK)
  customer_id (FK -> customer.id)
  placed_at
  status

order_item
  id (PK)
  order_id (FK -> purchase_order.id)
  product_id (FK -> product.id)
  quantity
  unit_price_minor
  currency_code
  line_number

product
  id (PK)
  sku
  name
  current_price_minor
```

`OrderItem` là entity riêng vì nó có dữ liệu nghiệp vụ `quantity` và `unitPriceMinor`, đồng thời có thể có định danh hoặc lifecycle riêng. Trong graph, có thể biểu diễn nó thành relationship `CONTAINS` giữa `PurchaseOrder` và `Product`, mang theo hai thuộc tính đó. Đây là ví dụ điển hình của việc chuyển join entity thành relationship properties.

Tuy nhiên, nếu `OrderItem` có lifecycle độc lập, được tham chiếu từ nhiều aggregate, có nhiều trạng thái hoặc có các liên kết riêng, giữ nó thành node `OrderLine` có thể phù hợp hơn. Quyết định phụ thuộc vào câu hỏi nghiệp vụ và cách dữ liệu được quản lý.

## 4. Lập bảng ánh xạ trước khi viết code

Một bảng mapping giúp nhóm migration thống nhất ý nghĩa của dữ liệu:

| Relational source | Graph target | Lý do |
|---|---|---|
| `customer` | `(:Customer)` | Khách hàng là thực thể có định danh và thuộc tính riêng |
| `purchase_order` | `(:PurchaseOrder)` | Đơn hàng có trạng thái, thời điểm và lifecycle riêng |
| `product` | `(:Product)` | Sản phẩm được nhiều đơn hàng cùng tham chiếu |
| `purchase_order.customer_id` | `(:Customer)-[:PLACED]->(:PurchaseOrder)` | Thể hiện hành động khách hàng đặt đơn |
| `order_item.order_id` + `product_id` | `(:PurchaseOrder)-[:CONTAINS]->(:Product)` | Thể hiện một đơn hàng chứa sản phẩm |
| `order_item.quantity` | `CONTAINS.quantity` | Số lượng thuộc về lần sản phẩm xuất hiện trong đơn hàng |
| `order_item.unit_price_minor` | `CONTAINS.unitPriceMinor` | Giá lịch sử thuộc về dòng hàng, không phải giá hiện tại của Product |
| `order_item.currency_code` | `CONTAINS.currencyCode` | Đơn vị tiền tệ của giá tại thời điểm mua |
| `order_item.id` | `CONTAINS.legacyOrderItemId` (nếu cần) | Giữ khóa nguồn để đối soát hoặc hỗ trợ đồng bộ trong giai đoạn chuyển đổi |

Giữ `unitPriceMinor` trên relationship là quyết định nghiệp vụ quan trọng. Giá hiện tại của sản phẩm có thể thay đổi; giá tại thời điểm mua phải giữ nguyên theo từng đơn hàng. Nếu đặt giá lịch sử lên node `Product`, lần mua mới có thể làm sai lịch sử của các đơn trước.

Giá trị tiền theo đơn vị nhỏ nhất cần đi cùng mã tiền tệ, ví dụ `unitPriceMinor = 125000` và `currencyCode = "VND"`. Nếu toàn hệ thống chỉ dùng một đồng tiền, quy ước đó phải được xác định rõ; nếu hỗ trợ nhiều đồng tiền, không thể so sánh hoặc cộng các giá trị chỉ dựa trên số nguyên.

Không sao chép toàn bộ cột của `order_item` vào `Product`. Hãy đặt mỗi property ở nơi thể hiện đúng chủ sở hữu của nó.

## 5. Foreign key không phải lúc nào cũng trở thành relationship

Khi chuyển từ JPA, có thể dùng các quy tắc khởi đầu:

- Foreign key trỏ tới một thực thể nghiệp vụ thường trở thành relationship.
- Join table chỉ chứa hai khóa ngoại thường trở thành relationship trực tiếp.
- Join table có thuộc tính mô tả liên kết có thể trở thành relationship properties.
- Join table có lifecycle, trạng thái, định danh hoặc liên kết riêng có thể trở thành node trung gian.
- Bảng kỹ thuật chỉ phục vụ uniqueness, audit hoặc ORM mapping không nhất thiết phải thành node.

Ví dụ `user_role` có thể trở thành `(:User)-[:HAS_ROLE]->(:Role)` nếu chỉ biểu diễn membership. Nếu membership có thời hạn, người cấp quyền, trạng thái duyệt hoặc lịch sử thay đổi, có thể dùng relationship properties hoặc node `RoleAssignment` tùy nhu cầu truy vấn và lifecycle.

Không chuyển một join table thành relationship chỉ vì nó có hai foreign key. Hãy hỏi: “Bản ghi này có phải một sự kiện hoặc thực thể mà nghiệp vụ cần truy cập độc lập không?” Nếu câu trả lời là có, node trung gian có thể phù hợp hơn.

## 6. Chọn node hay relationship properties cho dữ liệu liên kết

Một relationship có thể mang property khi dữ liệu đó mô tả chính mối liên kết:

```text
(PurchaseOrder)-[:CONTAINS {
    quantity: 2,
    unitPriceMinor: 125000,
    currencyCode: "VND",
    lineNumber: 1
}]->(Product)
```

Đây là cách biểu diễn tự nhiên khi dòng hàng chỉ có ý nghĩa trong quan hệ giữa một đơn hàng và một sản phẩm.

Chuyển thành node trung gian khi bản ghi cần được truy vấn hoặc quản lý độc lập:

```text
(PurchaseOrder)-[:HAS_LINE]->(OrderLine)
                                  |
                                  + -[:FOR_PRODUCT]->(Product)
```

Chọn relationship properties khi:

- Dữ liệu gắn với đúng một liên kết giữa hai node.
- Không cần tham chiếu relationship như một node độc lập.
- Lifecycle của dữ liệu phụ thuộc vào hai endpoint.
- Các truy vấn thường đi qua relationship đó.

Chọn node trung gian khi:

- Bản ghi có trạng thái hoặc lifecycle độc lập.
- Bản ghi được nhiều entity khác tham chiếu.
- Có nhiều relationship đi vào/đi ra từ bản ghi.
- Cần audit hoặc định danh nghiệp vụ riêng cho bản ghi.
- Bản ghi tham gia nhiều câu hỏi nghiệp vụ khác nhau như một thực thể.

## 7. Cardinality trong graph cần được quản lý rõ ràng

Relational database có thể dùng unique constraint trên foreign key để biểu diễn một-một hoặc một-nhiều. Neo4j relationship không tự áp đặt cardinality theo kiểu đó. Một node có thể có nhiều relationship cùng type, và graph có thể chứa nhiều cạnh giữa cùng hai node.

Ví dụ, nếu nghiệp vụ yêu cầu một `PurchaseOrder` chỉ thuộc một `Customer`, ứng dụng phải bảo đảm quy tắc đó khi ghi. Có thể dùng unique constraint cho ID node, nhưng unique constraint không tự ngăn hai relationship `PLACED` từ hai customer khác nhau tới cùng một order.

Hãy xác định rõ:

- Một order có được phép có nhiều customer không?
- Một customer có thể đặt bao nhiêu order?
- Một order có thể chứa cùng một product nhiều lần không?
- Hai node có thể có nhiều relationship cùng type không?
- Quan hệ có thể bị xóa hay chỉ chuyển sang trạng thái inactive?

Nếu `OrderItem` cho phép nhiều dòng cùng product trong một order, relationship `CONTAINS` cần được phân biệt bằng `lineNumber` hoặc business key phù hợp. Không gom vào `Set<Product>` nếu việc đó làm mất thông tin nhiều dòng hàng.

## 8. Chọn hướng relationship theo ngữ nghĩa và truy vấn

Neo4j relationship có hướng. Hướng nên phản ánh một quy ước nhất quán, thường theo chiều hành động hoặc từ chủ thể tới đối tượng:

```text
(Customer)-[:PLACED]->(PurchaseOrder)
(PurchaseOrder)-[:CONTAINS]->(Product)
```

Điều này giúp Cypher đọc tự nhiên:

```cypher
MATCH (customer:Customer)-[:PLACED]->(order:PurchaseOrder)
      -[:CONTAINS]->(product:Product)
RETURN customer, order, product;
```

Nếu truy vấn thường đi theo chiều ngược lại, Cypher vẫn có thể match incoming relationship:

```cypher
MATCH (product:Product)<-[:CONTAINS]-(order:PurchaseOrder)
      <-[:PLACED]-(customer:Customer)
WHERE product.sku = $sku
RETURN customer, order;
```

Không tạo hai relationship ngược chiều chỉ để hỗ trợ query hai hướng nếu chúng biểu diễn cùng một sự kiện. Hai cạnh có thể lệch nhau khi cập nhật. Chỉ tạo relationship riêng khi chúng có ngữ nghĩa nghiệp vụ khác nhau.

Trong SDN, cũng không cần khai báo cùng một association ở cả hai entity chỉ vì JPA trước đây có hai field tham chiếu nhau. Một mapping hai chiều có thể khiến query do SDN tạo tiếp tục nạp các nhánh graph khác theo metadata của cả hai phía. Bắt đầu bằng mapping một chiều ở phía aggregate quản lý relationship; Cypher vẫn có thể match cạnh theo chiều incoming khi use case cần truy vấn ngược.

## 9. Thiết kế graph theo workload thay vì tái tạo schema SQL

Một cách kiểm tra thiết kế là viết trước các câu Cypher đại diện cho use case. Nếu query vẫn phải đi qua nhiều node trung gian chỉ để biểu diễn một khái niệm nghiệp vụ đơn giản, xem lại graph model.

Ví dụ câu hỏi “Khách hàng đã mua sản phẩm nào?”:

```cypher
MATCH (customer:Customer {customerId: $customerId})
      -[:PLACED]->(:PurchaseOrder)
      -[line:CONTAINS]->(product:Product)
RETURN product.sku AS sku,
       product.name AS name,
       sum(line.quantity) AS totalQuantity
ORDER BY name;
```

Câu hỏi “Ai đã mua cùng sản phẩm với khách hàng này?”:

```cypher
MATCH (customer:Customer {customerId: $customerId})
      -[:PLACED]->(:PurchaseOrder)
      -[:CONTAINS]->(product:Product)
      <-[:CONTAINS]-(:PurchaseOrder)
      <-[:PLACED]-(other:Customer)
WHERE other <> customer
RETURN DISTINCT other.customerId AS customerId,
       other.name AS name;
```

Câu hỏi “Đề xuất sản phẩm khách hàng chưa mua dựa trên khách hàng có lịch sử tương tự”:

```cypher
MATCH (customer:Customer {customerId: $customerId})
      -[:PLACED]->(:PurchaseOrder)
      -[:CONTAINS]->(knownProduct:Product)
      <-[:CONTAINS]-(:PurchaseOrder)
      <-[:PLACED]-(similarCustomer:Customer)
      -[:PLACED]->(:PurchaseOrder)
      -[:CONTAINS]->(candidate:Product)
WHERE similarCustomer <> customer
  AND NOT EXISTS {
      MATCH (customer)-[:PLACED]->(:PurchaseOrder)-[:CONTAINS]->(candidate)
  }
RETURN candidate.sku AS sku,
       candidate.name AS name,
       count(DISTINCT similarCustomer) AS evidence
ORDER BY evidence DESC, name
LIMIT $limit;
```

Những truy vấn này thể hiện trực tiếp quan hệ nghiệp vụ. Khi dữ liệu lớn, cần xem `PROFILE`, giới hạn kết quả và kiểm tra index cho các thuộc tính neo như `customerId` và `sku`.

## 10. Thiết kế entity SDN từ graph model

Node `Customer`:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.neo4j.core.schema.Version;

@Node("Customer")
public class Customer {

    @Id
    private String customerId;

    @Version
    private Long version;

    private String name;

    @Relationship(type = "PLACED", direction = Relationship.Direction.OUTGOING)
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {
    }

    public String getCustomerId() { return customerId; }
    public String getName() { return name; }
    public List<PurchaseOrder> getOrders() { return orders; }
}
```

Node `PurchaseOrder`:

```java
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.neo4j.core.schema.Version;

@Node("PurchaseOrder")
public class PurchaseOrder {

    @Id
    private String orderId;

    @Version
    private Long version;

    private ZonedDateTime placedAt;
    private String status;

    @Relationship(type = "CONTAINS", direction = Relationship.Direction.OUTGOING)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public String getOrderId() { return orderId; }
    public ZonedDateTime getPlacedAt() { return placedAt; }
    public String getStatus() { return status; }
    public List<OrderLine> getLines() { return lines; }
}
```

Relationship properties `OrderLine`:

```java
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class OrderLine {

    @RelationshipId
    private Long id;

    private String lineNumber;
    private Long legacyOrderItemId;
    private Integer quantity;
    private Long unitPriceMinor;
    private String currencyCode;

    @TargetNode
    private Product product;

    protected OrderLine() {
    }

    public String getLineNumber() { return lineNumber; }
    public Long getLegacyOrderItemId() { return legacyOrderItemId; }
    public Integer getQuantity() { return quantity; }
    public Long getUnitPriceMinor() { return unitPriceMinor; }
    public String getCurrencyCode() { return currencyCode; }
    public Product getProduct() { return product; }
}
```

Node `Product`:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Version;

@Node("Product")
public class Product {

    @Id
    private String sku;

    @Version
    private Long version;

    private String name;
    private Long currentPriceMinor;

    protected Product() {
    }

    public String getSku() { return sku; }
    public String getName() { return name; }
    public Long getCurrentPriceMinor() { return currentPriceMinor; }
}
```

Các ví dụ dùng business ID được gán từ hệ thống nguồn và khai báo `@Version` để SDN nhận biết trạng thái mới/cũ và hỗ trợ optimistic locking. Khi tạo node mới qua SDN, để framework quản lý version; không tự tăng version trong nghiệp vụ.

`@RelationshipProperties` mô tả property của relationship và cần đúng một field `@TargetNode` để chỉ node ở đầu còn lại. Không đặt `quantity` hoặc `unitPriceMinor` lên `Product`, vì chúng thuộc về một dòng hàng cụ thể.

`@RelationshipId` là định danh kỹ thuật do Neo4j/SDN dùng để nhận diện relationship đã ánh xạ khi cập nhật. Không dùng giá trị này làm business key hoặc trao nó ra API; `lineNumber` mới là thuộc tính nghiệp vụ của ví dụ.

## 11. Vì sao không giữ nguyên `OrderItem` thành node?

Hai cách biểu diễn đều có thể đúng, nhưng phục vụ mục đích khác nhau.

Relationship properties:

```text
(PurchaseOrder)-[:CONTAINS {quantity: 2, unitPriceMinor: 125000}]->(Product)
```

Node trung gian:

```text
(PurchaseOrder)-[:HAS_LINE]->(OrderLine)
(OrderLine)-[:FOR_PRODUCT]->(Product)
```

Chọn relationship properties nếu dòng hàng chỉ là thông tin của liên kết giữa order và product. Chọn node `OrderLine` nếu cần định danh, audit, trạng thái giao hàng riêng cho từng dòng hoặc nhiều liên kết khác cùng trỏ tới dòng hàng.

Không nên biến tất cả join table thành relationship properties một cách máy móc. Một join entity có thể mang nghiệp vụ phức tạp hơn một cạnh.

## 12. Định danh khi chuyển từ primary key sang business ID

JPA thường dùng numeric surrogate key như `customer.id = 1001`. Trong graph model, có thể tiếp tục dùng ID nguồn hoặc chọn business key như `customerId`, `orderId`, `sku`.

Các tiêu chí:

- ID có ổn định trong suốt lifecycle không?
- Có duy nhất trên toàn graph/database không?
- Có thể tái sử dụng sau khi xóa không?
- Có thể ghép từ tenant và ID nguồn không?
- Có cần giữ source ID để đối soát và đồng bộ không?

Nếu `id=42` có thể tồn tại ở cả bảng `customer` và `product`, không dùng cùng một label và cùng một ID namespace mà không phân biệt. Label khác nhau có thể cho phép cùng property ID, nhưng application lookup phải chỉ rõ label. Với multi-tenant, có thể dùng composite business key hoặc giữ `tenantId` làm property cùng unique constraint phù hợp.

Trong ví dụ JPA, primary key là `Long`, còn graph entity dùng `String customerId`, `String orderId` và `String sku` làm ID. Đây là quyết định chuyển sang business key, không phải phép ánh xạ tự động. CSV phải cung cấp các key ổn định tương ứng; nếu chỉ có numeric surrogate key, có thể chuyển thành chuỗi ổn định hoặc lưu riêng như `legacyCustomerId` trong khi tạo business ID. Giữ cùng một kiểu ID giữa field `@Id`, repository generic và dữ liệu đã import.

Ví dụ constraint:

```cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:PurchaseOrder)
REQUIRE o.orderId IS UNIQUE;

CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE p.sku IS UNIQUE;
```

Constraint giúp tránh node trùng khi import lặp hoặc khi hai request cùng tạo một business entity. `MERGE` không thay thế unique constraint trong môi trường concurrent; constraint là lớp bảo đảm tính duy nhất ở database.

## 13. Mapping repository và custom Cypher

Repository cho node có thể khai báo như sau:

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository extends Neo4jRepository<Customer, String> {
    Optional<Customer> findByCustomerId(String customerId);
}
```

SDN tạo derived query dựa trên property và mapping metadata. Khi cần traversal cụ thể, có thể dùng `@Query`:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    MATCH (c:Customer {customerId: $customerId})
          -[:PLACED]->(o:PurchaseOrder)
          -[line:CONTAINS]->(p:Product)
    RETURN p.sku AS sku,
           p.name AS name,
           sum(line.quantity) AS totalQuantity
    ORDER BY name
    """)
List<ProductPurchaseSummary> findPurchasedProducts(
    @Param("customerId") String customerId
);
```

Projection:

```java
public record ProductPurchaseSummary(
    String sku,
    String name,
    Long totalQuantity
) {
}
```

Alias trong `RETURN` phải khớp property hoặc constructor parameter mà projection dùng. Với custom query trả DTO, chỉ trả những field cần cho use case.

Nếu custom query trả domain entity, phải trả đủ graph structure cần để SDN hydrate entity đó. Không lấy một entity được map một phần rồi gọi `save()` như thể đó là aggregate đầy đủ; relationship không có trong object có thể bị xóa khi SDN đồng bộ graph. Dùng DTO cho read-only query, tải lại aggregate đầy đủ trước khi ghi hoặc dùng persistence projection để giới hạn rõ field cần cập nhật.

## 14. Không mang tư duy Lazy Loading sang graph một cách máy móc

Trong JPA, `FetchType.LAZY` thường được dùng để tránh join hoặc tải association cho tới khi code truy cập. Nhưng nếu service lặp qua collection lazy, có thể phát sinh N+1 query hoặc lỗi lazy initialization khi persistence context đã đóng.

Trong SDN, graph mapping được thực hiện theo query và mapping metadata. Query do repository tạo sẽ nạp các relationship mà mapping yêu cầu; custom Cypher quyết định rõ phần graph được trả về. Một mapping hai chiều hoặc có nhiều nhánh liên kết có thể khiến graph được hydrate rộng hơn dự tính. Không nên giả định một relationship field sẽ tự tải ở bất cứ thời điểm nào khi getter được gọi như lazy proxy của Hibernate.

Thay vì chuyển từng `FetchType.LAZY` sang một annotation tương tự, hãy xác định read model cho từng use case:

- Trang danh sách: chỉ cần ID, tên và trạng thái; dùng projection.
- Trang chi tiết: tải các association thực sự hiển thị.
- Báo cáo: dùng aggregation Cypher trả DTO.
- Recommendation: dùng traversal có giới hạn, không hydrate toàn bộ entity graph.
- Command update: tải đủ aggregate/relationship cần quản lý trước khi save.

## 15. Aggregate boundary và phạm vi save

Trong JPA, cascade và orphan removal thường điều khiển lifecycle của entity liên quan. Trong SDN, `save()` đồng bộ node cùng relationship được ánh xạ trong entity graph. Nếu một association được khai báo nhưng object truyền vào chỉ chứa một phần trạng thái, save có thể xóa relationship không hiện diện trong object.

Hãy xác định aggregate boundary: phần graph nào được một command service quản lý như một đơn vị nhất quán? Không nhất thiết toàn bộ graph có thể truy cập từ root đều thuộc cùng aggregate.

Các nguyên tắc:

1. Tải đầy đủ các relationship thuộc phạm vi command cần cập nhật.
2. Không lưu object được hydrate một phần từ custom query như full aggregate.
3. Dùng DTO cho read path.
4. Dùng `Neo4jTemplate.saveAs` với persistence projection hoặc targeted Cypher khi chỉ cập nhật một phần.
5. Đặt transaction ở ranh giới nghiệp vụ cần cập nhật nguyên tử.

## 16. Tách read model và write model khi chuyển đổi

Một ứng dụng JPA có thể dùng cùng entity class cho đọc, sửa và ghi. Khi chuyển sang graph, có thể giữ cách tổ chức service nhưng cần phân biệt rõ query trả dữ liệu và command thay đổi graph.

Ví dụ read model:

```java
public record CustomerOrderRow(
    String orderId,
    String status,
    String productSku,
    String productName,
    Integer quantity
) {
}
```

Ví dụ query đọc:

```cypher
MATCH (c:Customer {customerId: $customerId})
      -[:PLACED]->(o:PurchaseOrder)
      -[line:CONTAINS]->(p:Product)
RETURN o.orderId AS orderId,
       o.status AS status,
       p.sku AS productSku,
       p.name AS productName,
       line.quantity AS quantity
ORDER BY orderId, productSku;
```

Command service nên nhận command object như `ChangeOrderStatus`, xác thực transition hợp lệ, tải order cùng association cần thiết rồi cập nhật. Không nhận trực tiếp một DTO kết quả truy vấn làm entity để save.

## 17. Chuyển dữ liệu từ relational database sang Neo4j

Migration dữ liệu cần tách thành các bước có thể lặp và đối soát:

1. Chốt mapping table/column/FK sang label/property/relationship.
2. Chốt ID strategy và constraint cho node.
3. Import node trước: `Customer`, `PurchaseOrder`, `Product`.
4. Import relationship sau khi endpoint node đã tồn tại.
5. Chuyển dữ liệu join table thành relationship properties hoặc node trung gian theo thiết kế.
6. Kiểm tra count, orphan reference, duplicate key và property null/format.
7. Chạy reconciliation theo batch và lưu báo cáo sai lệch.
8. Chạy thử query nghiệp vụ trên graph đã import.
9. Chọn chiến lược cutover và rollback trước khi chuyển production traffic.

Ví dụ import node từ CSV:

```cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
CALL {
    WITH row
    MERGE (c:Customer {customerId: row.customer_id})
    ON CREATE SET c.version = 0
    SET c.name = row.name
} IN TRANSACTIONS OF 1000 ROWS;
```

Ví dụ import `PurchaseOrder`:

```cypher
LOAD CSV WITH HEADERS FROM 'file:///orders.csv' AS row
CALL {
    WITH row
    MERGE (o:PurchaseOrder {orderId: row.order_id})
    ON CREATE SET o.version = 0
    SET o.status = row.status,
        o.placedAt = datetime(row.placed_at)
} IN TRANSACTIONS OF 1000 ROWS;
```

Ví dụ import node Product:

```cypher
LOAD CSV WITH HEADERS FROM 'file:///products.csv' AS row
CALL {
    WITH row
    MERGE (p:Product {sku: row.sku})
    ON CREATE SET p.version = 0
    SET p.name = row.name,
        p.currentPriceMinor = toInteger(row.current_price_minor)
} IN TRANSACTIONS OF 1000 ROWS;
```

Ví dụ import relationship sau khi Customer và PurchaseOrder đã có:

```cypher
LOAD CSV WITH HEADERS FROM 'file:///orders.csv' AS row
CALL {
    WITH row
    MATCH (c:Customer {customerId: row.customer_id})
    MATCH (o:PurchaseOrder {orderId: row.order_id})
    MERGE (c)-[:PLACED]->(o)
} IN TRANSACTIONS OF 1000 ROWS;
```

Ví dụ import `CONTAINS` relationship có properties:

```cypher
LOAD CSV WITH HEADERS FROM 'file:///order_items.csv' AS row
CALL {
    WITH row
    MATCH (o:PurchaseOrder {orderId: row.order_id})
    MATCH (p:Product {sku: row.product_sku})
    MERGE (o)-[line:CONTAINS {lineNumber: row.line_number}]->(p)
        SET line.legacyOrderItemId = toInteger(row.order_item_id),
        line.quantity = toInteger(row.quantity),
        line.unitPriceMinor = toInteger(row.unit_price_minor),
        line.currencyCode = row.currency_code
} IN TRANSACTIONS OF 1000 ROWS;
```

Trong ví dụ cuối, `lineNumber` được dùng để phân biệt các dòng cùng sản phẩm trong một order. Hãy xác nhận business key này là duy nhất trong phạm vi order; nếu không, cần chọn key khác hoặc dùng node `OrderLine`.

Các node ví dụ có `@Version`, vì vậy dữ liệu import trực tiếp bằng Cypher cần khởi tạo `version` khi tạo node. `ON CREATE SET` tránh đặt version về `0` mỗi lần chạy lại migration sau khi ứng dụng đã cập nhật entity. Chỉ chạy lại backfill trong giai đoạn đã khóa hoặc điều phối rõ ràng với các writer đang hoạt động. `row.line_number` phải có giá trị và ổn định; nếu null hoặc trùng trong cùng order, `MERGE` có thể không tạo được quan hệ đúng như mong đợi.

`LOAD CSV` yêu cầu file nằm trong import directory được Neo4j cho phép hoặc dùng nguồn URL được cấu hình phù hợp. `CALL { ... } IN TRANSACTIONS` chạy các batch transaction và cần được thực thi trong ngữ cảnh hỗ trợ transactional subquery; không mặc định chạy bên trong transaction do client đã mở. Với nguồn dữ liệu lớn, có thể dùng ETL tool hoặc batch application thay vì một lệnh duy nhất.

## 18. Migration phải idempotent và có thể đối soát

Một job migration có thể bị chạy lại sau timeout hoặc restart. Dùng business key và `MERGE` để tạo lại node mà không nhân bản dữ liệu. Với relationship, `MERGE` phải dùng key phân biệt đúng một quan hệ nghiệp vụ; không dùng toàn bộ property có thể thay đổi làm pattern định danh.

Các kiểm tra nên có:

| Kiểm tra | Mục tiêu |
|---|---|
| Count source/target node | Phát hiện thiếu hoặc trùng entity |
| Count relationship theo type | Phát hiện thiếu association |
| Orphan FK | Tìm row tham chiếu endpoint không tồn tại |
| Duplicate business key | Bảo đảm `MERGE` không chọn nhầm nhiều node |
| Relationship properties | Đối chiếu quantity, historical price, timestamp |
| Null/type conversion | Phát hiện giá trị không chuyển đổi đúng |
| Query result sampling | So sánh kết quả nghiệp vụ giữa JPA và graph |
| Re-run migration | Xác nhận job idempotent |

Đừng chỉ so sánh tổng số node và relationship. Hai graph có cùng count vẫn có thể nối sai endpoint hoặc mất property. Nên đối soát theo business key và lấy mẫu theo use case.

## 19. Dual read, dual write và cutover

Với hệ thống đang hoạt động, có thể cần thời gian chạy song song relational database và Neo4j. Cần xác định rõ nguồn dữ liệu chính trong từng giai đoạn.

Một lộ trình thường dùng:

```text
JPA database là source of truth
        |
        v
Backfill dữ liệu hiện tại sang Neo4j
        |
        v
Phát change event / outbox cho dữ liệu phát sinh
        |
        v
Đối soát số lượng và query result
        |
        v
Shadow read: so sánh kết quả, chưa trả graph cho user
        |
        v
Chuyển read traffic theo từng use case
        |
        v
Chuyển write ownership theo kế hoạch cutover
```

Không ghi đồng bộ hai database bằng hai lệnh độc lập rồi giả định chúng luôn cùng commit. Nếu JPA transaction commit nhưng Neo4j write thất bại, hai nguồn sẽ lệch. Dùng transactional outbox/CDC để phát change event có thể retry, idempotent consumer và reconciliation định kỳ.

Trước cutover, thống nhất:

- Nguồn nào là source of truth?
- Event nào cần được phát khi row thay đổi?
- Làm sao đảm bảo event không mất khi transaction relational rollback/commit?
- Consumer có idempotent không?
- Có thể replay event từ checkpoint nào?
- Shadow read sẽ so sánh những query nào?
- Khi rollback cutover, dữ liệu phát sinh trong Neo4j được xử lý ra sao?

## 20. Giữ dữ liệu nguồn để truy vết và đồng bộ

Trong giai đoạn chuyển đổi, nên giữ source ID hoặc source key trên node để đối soát. Ví dụ `legacyCustomerId` có thể được lưu cùng `customerId` nếu cần liên kết với relational system trong thời gian dual run.

Không nhất thiết giữ mọi cột kỹ thuật của schema cũ mãi mãi. Sau khi cutover và hết thời hạn đồng bộ, có thể loại bỏ các property chỉ phục vụ migration theo một migration riêng. Nhưng cần giữ traceability nếu còn yêu cầu audit, replay hoặc đối chiếu lịch sử.

Nếu source ID không duy nhất giữa tenant hoặc bảng, hãy lưu namespace rõ ràng như `sourceSystem`, `sourceTable` hoặc composite key. Không dùng ID nội bộ của Neo4j làm khóa đồng bộ với hệ thống nguồn; internal ID có thể thay đổi và không phải business identifier ổn định.

## 21. Hiệu năng: graph traversal không tự động luôn nhanh hơn JOIN

Neo4j phù hợp khi câu hỏi cần đi qua nhiều liên kết và những liên kết đó là thành phần quan trọng của domain. Nhưng graph model kém phù hợp nếu thiết kế tạo ra quá nhiều node/relationship không cần thiết hoặc query traversal không giới hạn.

Các nguyên tắc:

1. Tạo index/unique constraint cho điểm bắt đầu traversal như `customerId`, `orderId`, `sku`.
2. Dùng relationship type có ngữ nghĩa rõ và hướng phù hợp.
3. Tránh traversal độ sâu không giới hạn trong endpoint công khai.
4. Chỉ trả property cần thiết bằng DTO/projection.
5. Dùng `PROFILE` để kiểm tra số row, DB hits và operator.
6. Không hydrate toàn bộ graph khi màn hình chỉ cần vài field.
7. Kiểm tra độ phân bố degree; một node có hàng triệu relationship có thể trở thành điểm nóng.
8. Đặt pagination/limit cho truy vấn danh sách và recommendation.

Không chuyển một truy vấn SQL nhiều JOIN thành một pattern graph dài mà không kiểm tra workload. Thiết kế graph cần được đánh giá bằng câu hỏi nghiệp vụ, cardinality, degree distribution và execution plan thực tế.

## 22. Những phần JPA không có ánh xạ một-một

Một số khái niệm ORM cần được thiết kế lại:

| JPA concept | Khi chuyển sang SDN cần xem xét |
|---|---|
| `@ManyToOne` / `@OneToMany` | Relationship type, direction và quy tắc cardinality do ứng dụng bảo đảm |
| `@ManyToMany` | Relationship trực tiếp hay relationship properties/node trung gian |
| `@JoinTable` | Quan hệ graph có ý nghĩa gì; thuộc tính join table thuộc edge hay node |
| `FetchType.LAZY` | Query/read model nào cần nạp graph; không giả định lazy proxy như Hibernate |
| `CascadeType` / `orphanRemoval` | Aggregate boundary và semantics khi SDN đồng bộ relationship |
| `@Embedded` / `@Embeddable` | Property phẳng, `@CompositeProperty` để flatten map hoặc node riêng; Neo4j không lưu nested map như property value |
| `@Inheritance` | Label hierarchy, nhiều label trên node hoặc mô hình node riêng |
| `@Version` | Optimistic locking cho node khi nhiều transaction cùng cập nhật |
| `@EntityGraph` | Query graph hoặc projection thể hiện chính xác phần dữ liệu cần đọc |
| `@Formula` / native SQL | Cypher expression, projection hoặc service-level calculation |

Không cố giữ tất cả semantics của Hibernate nếu chúng không còn phù hợp. Hãy viết lại command/query contract dựa trên graph và transaction model mới.

## 23. Lỗi thường gặp khi chuyển từ JPA

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chuyển mỗi table thành một node mà không xét use case | Graph chỉ là relational schema đổi hình thức | Thiết kế từ câu hỏi và đường đi nghiệp vụ |
| Chuyển mọi FK thành relationship cùng tên kỹ thuật | Query khó đọc, thiếu ngữ nghĩa | Đặt relationship type bằng động từ nghiệp vụ |
| Chuyển mọi join table thành relationship | Mất lifecycle hoặc identity của join entity | Chọn relationship properties hoặc node trung gian |
| Đặt giá lịch sử lên Product | Đơn cũ thay đổi theo giá hiện tại | Đặt giá trên relationship/dòng hàng của order |
| Giả định Neo4j tự enforce one-to-one | Graph có thể chứa nhiều relationship trái quy tắc | Validate trong command và kiểm tra graph consistency |
| Tạo relationship hai chiều cho cùng một sự kiện | Hai cạnh có thể lệch nhau khi cập nhật | Dùng một cạnh có direction và match hai chiều khi cần |
| Hydrate domain entity một phần rồi save | Relationship chưa tải có thể bị xóa | DTO, full aggregate hoặc `saveAs` projection |
| Dùng `Set` làm mất nhiều dòng hàng cùng product | Thông tin order line bị gộp | Dùng relationship properties có key hoặc node `OrderLine` |
| Dùng Neo4j internal ID làm source key | Đồng bộ không ổn định | Giữ business ID/source ID và unique constraint |
| Dual write không có outbox | Hai database lệch khi một write thất bại | Outbox/CDC, retry và reconciliation |
| Cho phép traversal không giới hạn | Query mở rộng quá lớn | Giới hạn độ sâu, endpoint và kết quả |

## 24. Quy trình chuyển đổi theo từng use case

1. Liệt kê câu hỏi nghiệp vụ và truy vấn quan trọng trong ứng dụng JPA.
2. Xác định table, foreign key và join entity hiện đang tham gia mỗi truy vấn.
3. Chọn node cho thực thể có identity/lifecycle riêng.
4. Chọn relationship type theo động từ nghiệp vụ, xác định direction và cardinality.
5. Quyết định dữ liệu join table là relationship properties hay node trung gian.
6. Chọn business ID và tạo unique constraint trước khi import.
7. Viết Cypher cho các query quan trọng trước khi hoàn thiện entity mapping.
8. Tạo entity SDN với `@Node`, `@Relationship`, `@RelationshipProperties` và `@TargetNode`.
9. Phân tách DTO/read projection khỏi aggregate dùng cho ghi.
10. Import node trước, relationship sau; dùng `MERGE` và batch transaction.
11. Đối soát endpoint, relationship properties và kết quả nghiệp vụ.
12. Chạy shadow read, cutover theo từng use case và có kế hoạch rollback.

## 25. Tự kiểm tra

1. Vì sao chuyển JPA sang SDN không chỉ là thay annotation?
2. Một foreign key thường trở thành gì trong graph model và khi nào không nên chuyển thành relationship?
3. Khi nào join table phù hợp với relationship properties, khi nào nên thành node trung gian?
4. Vì sao `unitPriceMinor` của một dòng hàng nên nằm trên relationship thay vì node Product?
5. Hướng relationship nên được chọn theo nguyên tắc nào?
6. Neo4j có tự enforce cardinality một-một hoặc một-nhiều không?
7. Vì sao không nên tạo hai cạnh ngược chiều cho cùng một sự kiện?
8. `@RelationshipProperties` và `@TargetNode` biểu diễn điều gì?
9. Tại sao business ID và unique constraint quan trọng khi import dữ liệu?
10. Vì sao custom query trả entity một phần không nên được dùng trực tiếp cho save?
11. Aggregate boundary khác lazy loading của Hibernate ở điểm nào?
12. Làm sao kiểm chứng migration không nối sai endpoint dù tổng số node/relationship đúng?
13. Vì sao dual write cần outbox hoặc CDC?
14. Khi nào graph traversal có thể không nhanh hơn JOIN?

## Tài liệu tham khảo

- [Spring Data Neo4j — Object Mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping.html)
- [Spring Data Neo4j — Mapping Relationships](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
- [Spring Data Neo4j — Projections](https://docs.spring.io/spring-data/neo4j/reference/projections/sdn-projections.html)
- [Spring Data Neo4j — FAQ: Custom Queries and Partial Mapping](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Neo4j — Graph Data Modeling Guidelines](https://neo4j.com/docs/getting-started/data-modeling/guide-data-modeling/)
- [Neo4j — Data Modeling: Relational to Graph](https://neo4j.com/docs/getting-started/data-modeling/tutorial-data-modeling/)
- [Neo4j Cypher Manual — MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Cypher Manual — LOAD CSV](https://neo4j.com/docs/cypher-manual/current/clauses/load-csv/)
