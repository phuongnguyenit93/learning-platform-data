# Entity graph và fetch profile để định nghĩa dữ liệu cần tải trong Hibernate ORM

Một màn hình chi tiết đơn hàng có thể cần khách hàng, các dòng hàng và sản phẩm của từng dòng. Một màn hình danh sách đơn hàng chỉ cần mã đơn, trạng thái và tên khách hàng. Nếu mọi truy vấn đều tải cùng một object graph lớn, ứng dụng dễ đọc dư dữ liệu, tạo nhiều SQL hoặc giữ quá nhiều entity trong persistence context. Nếu mặc định tải quá ít, code lại phải truy cập các association lazy từng cái một và có thể tạo ra N+1 query.

Hibernate ORM và Jakarta Persistence cung cấp những cách để **định nghĩa dữ liệu cần tải theo từng use case**. Hai cơ chế quan trọng là:

- **Entity graph**: cơ chế của Jakarta Persistence để mô tả các thuộc tính cần được fetch khi tải một entity. Có thể khai báo graph có tên hoặc tạo graph động trong code, áp dụng cho một query hay thao tác tìm entity.
- **Fetch profile**: cơ chế riêng của Hibernate để bật một tập override chiến lược fetch cho các association khi một Hibernate Session tải entity.

Cả hai giúp tách **fetch plan** khỏi mapping mặc định. Tuy nhiên, chúng không giống nhau về phạm vi, tính di động, cú pháp và cách Hibernate thực thi SQL. Chúng cũng không phải công cụ projection: entity graph và fetch profile định nghĩa association cần tải, còn DTO projection quyết định chính xác dữ liệu nào được chọn để trả về.

Bài học đi từ vấn đề tải dữ liệu, cách khai báo và sử dụng entity graph, fetch profile của Hibernate, so sánh hai cơ chế và các giới hạn hiệu năng cần chú ý.

## 1. Vì sao cần định nghĩa dữ liệu cần tải theo use case?

Giả sử hệ thống bán hàng có mô hình:

```text
PurchaseOrder
    |
    +---- customer
    |
    +---- lines
             |
             +---- product
             |
             +---- product
```

Entity có thể được ánh xạ như sau:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();
}
```

```java
@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY)
    private Product product;
}
```

Một use case có thể chỉ cần `PurchaseOrder.id` và `status`. Use case khác cần `customer.name`. Trang chi tiết có thể cần cả `lines.product.name` và `lines.quantity`.

Nếu khai báo tất cả association là eager ở mapping, mỗi truy vấn có thể kéo theo dữ liệu không cần. Nếu tất cả đều lazy, code truy cập lần lượt từng association có thể tạo nhiều truy vấn.

### 1.1. Ví dụ N+1 khi không có fetch plan phù hợp

```java
List<PurchaseOrder> orders = em.createQuery("""
    select o
    from PurchaseOrder o
    order by o.createdAt desc
    """, PurchaseOrder.class)
    .getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

Nếu danh sách có 100 order và mỗi customer chưa được tải, việc đọc tên có thể tạo một truy vấn lấy order cộng thêm nhiều truy vấn lấy customer. Identity map hoặc cache có thể làm giảm số truy vấn khi nhiều order dùng chung customer, nhưng mô hình N+1 vẫn là rủi ro.

### 1.2. Mapping và fetch plan giải quyết hai câu hỏi khác nhau

- **Mapping** mô tả quan hệ và hành vi mặc định: entity nào tham chiếu entity nào, collection nào được lazy, khóa ngoại ở đâu.
- **Fetch plan** mô tả dữ liệu cần lấy cho một lần đọc cụ thể: lần này cần customer và lines, lần khác chỉ cần customer.

Entity graph và fetch profile giúp biểu đạt fetch plan mà không phải đổi annotation mapping cho mỗi màn hình.

### 1.3. Fetch không phải điều kiện lọc

Fetch plan quyết định association nào được khởi tạo cùng quá trình tải entity. Nó không tự quyết định:

- Order nào được chọn.
- Có lọc theo trạng thái hay ngày tạo không.
- Sắp xếp theo thuộc tính nào.
- Có phân trang bao nhiêu hàng.
- Người dùng có quyền xem order hay không.

Những điều đó vẫn thuộc query, specification, predicate và authorization của ứng dụng.

## 2. Entity graph là gì?

**Entity graph** là mô tả cấu trúc thuộc tính của entity mà ứng dụng muốn fetch trong một thao tác tải. Đây là tính năng của Jakarta Persistence, vì vậy không chỉ dùng được với Hibernate mà còn có thể dùng với provider JPA khác.

Một entity graph gồm:

- **Root entity**: kiểu entity bắt đầu graph.
- **Attribute nodes**: những thuộc tính cần fetch.
- **Subgraphs**: mô tả sâu hơn những thuộc tính của association/embedded attribute bên trong graph.
- **Key subgraphs**: mô tả thuộc tính của key khi association là Map, nếu cần.

Ví dụ, graph cho trang chi tiết order:

```text
PurchaseOrder
    |
    +---- customer
    |
    +---- lines
             |
             +---- product
```

Graph có thể diễn đạt rằng khi lấy `PurchaseOrder`, ứng dụng cần customer và lines; mỗi line cần product.

Entity graph **không bắt buộc** Hibernate phải tạo đúng một câu SQL JOIN duy nhất. Provider có thể dùng join, secondary select hoặc chiến lược phù hợp khác để đáp ứng fetch semantics. Hãy xem graph là yêu cầu dữ liệu, không phải bản thiết kế SQL.

## 3. Named entity graph bằng annotation

Jakarta Persistence cho phép khai báo graph có tên bằng `@NamedEntityGraph` trên entity.

Ví dụ:

```java
import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Entity
@Table(name = "purchase_orders")
@NamedEntityGraph(
    name = "PurchaseOrder.detail",
    attributeNodes = {
        @NamedAttributeNode("customer"),
        @NamedAttributeNode(
            value = "lines",
            subgraph = "line-with-product"
        )
    },
    subgraphs = {
        @NamedSubgraph(
            name = "line-with-product",
            attributeNodes = {
                @NamedAttributeNode("product")
            }
        )
    }
)
public class PurchaseOrder {

    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public UUID getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public List<OrderLine> getLines() {
        return lines;
    }
}
```

Graph có tên `PurchaseOrder.detail` mô tả:

1. Fetch thuộc tính `customer` của PurchaseOrder.
2. Fetch collection `lines`.
3. Với mỗi `OrderLine` trong collection, fetch thuộc tính `product`.

`@NamedAttributeNode` tham chiếu **tên thuộc tính Java của entity**, không phải tên cột SQL. Ví dụ nếu field là `customer` nhưng cột là `customer_id`, graph vẫn ghi `customer`.

### 3.1. Subgraph cần thiết khi đi sâu vào association

Nếu chỉ viết:

```java
@NamedAttributeNode("lines")
```

thì graph yêu cầu fetch association `lines`. Khi cần chỉ rõ thêm thuộc tính `product` trên mỗi OrderLine, khai báo subgraph:

```java
@NamedAttributeNode(
    value = "lines",
    subgraph = "line-with-product"
)
```

và:

```java
@NamedSubgraph(
    name = "line-with-product",
    attributeNodes = @NamedAttributeNode("product")
)
```

Nếu cần đi sâu hơn, có thể khai báo subgraph tiếp theo theo cấu trúc mapping. Không nên đưa mọi association của toàn bộ domain vào một graph khổng lồ; mỗi graph nên phản ánh một nhu cầu đọc có ý nghĩa.

### 3.2. Nhiều named graph trên cùng entity

Có thể khai báo nhiều graph cho những use case khác nhau:

```java
@Entity
@NamedEntityGraphs({
    @NamedEntityGraph(
        name = "PurchaseOrder.summary",
        attributeNodes = {
            @NamedAttributeNode("customer")
        }
    ),
    @NamedEntityGraph(
        name = "PurchaseOrder.detail",
        attributeNodes = {
            @NamedAttributeNode("customer"),
            @NamedAttributeNode(
                value = "lines",
                subgraph = "line-product"
            )
        },
        subgraphs = {
            @NamedSubgraph(
                name = "line-product",
                attributeNodes = @NamedAttributeNode("product")
            )
        }
    )
})
public class PurchaseOrder {
    // Entity mapping.
}
```

Ở đây:

- `PurchaseOrder.summary` phù hợp với danh sách cần thông tin khách hàng.
- `PurchaseOrder.detail` phù hợp với trang chi tiết cần cả dòng hàng và sản phẩm.

Việc khai báo graph không tự chạy query. Code cần lấy graph và áp dụng vào một thao tác đọc.

## 4. Sử dụng named entity graph với EntityManager

Lấy graph bằng tên:

```java
EntityGraph<?> graph = em.getEntityGraph(
    "PurchaseOrder.detail"
);
```

Áp dụng vào JPQL query bằng hint `jakarta.persistence.fetchgraph`:

```java
PurchaseOrder order = em.createQuery("""
    select o
    from PurchaseOrder o
    where o.id = :id
    """, PurchaseOrder.class)
    .setParameter("id", orderId)
    .setHint("jakarta.persistence.fetchgraph", graph)
    .getSingleResult();
```

Khi query trả về, graph yêu cầu các thuộc tính được khai báo phải được fetch theo semantics của fetch graph. Nếu cần dùng load graph, đổi hint thành `jakarta.persistence.loadgraph`.

### 4.1. Áp dụng graph cho thao tác find

EntityManager cũng cho phép truyền property map vào `find`:

```java
EntityGraph<?> graph = em.getEntityGraph(
    "PurchaseOrder.detail"
);

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId,
    java.util.Map.of(
        "jakarta.persistence.fetchgraph",
        graph
    )
);
```

Cách này hữu ích khi chỉ tìm một entity theo khóa chính và muốn chỉ định fetch plan cho lần tải đó.

Nếu entity đã tồn tại trong persistence context, `find` có thể trả về managed instance hiện có. Không nên kỳ vọng việc áp graph sẽ làm một entity đã được khởi tạo trước đó quay lại trạng thái chưa tải hoặc luôn phát một query mới. Khi kiểm tra fetch behavior, hãy dùng persistence context mới hoặc kiểm soát rõ trạng thái entity/cache.

### 4.2. Dùng graph trong repository method

Với Spring Data JPA, repository có thể dùng annotation `@EntityGraph`:

```java
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, UUID> {

    @EntityGraph(
        value = "PurchaseOrder.detail",
        type = EntityGraph.EntityGraphType.FETCH
    )
    Optional<PurchaseOrder> findDetailedById(UUID id);
}
```

Spring Data lấy named graph và áp dụng nó vào query được tạo cho repository method. Cách này giúp tên fetch plan nằm gần method diễn đạt use case.

Có thể dùng graph động bằng `attributePaths` mà không cần khai báo named graph:

```java
@EntityGraph(
    attributePaths = {
        "customer",
        "lines.product"
    },
    type = EntityGraph.EntityGraphType.FETCH
)
Optional<PurchaseOrder> findWithCustomerAndProductsById(UUID id);
```

`attributePaths` dùng đường dẫn thuộc tính Java. Ví dụ `lines.product` tương ứng collection lines và association product bên trong mỗi line.

Tính năng này là tích hợp của Spring Data JPA. Nếu dùng Jakarta Persistence thuần hoặc một repository framework khác, hãy dùng API EntityGraph tương ứng thay vì import annotation Spring.

## 5. Dynamic entity graph trong Java

Không phải fetch plan nào cũng cần tên cố định. Có thể tạo graph trong code khi cấu trúc cần tải phụ thuộc use case.

Ví dụ:

```java
import jakarta.persistence.EntityGraph;
import jakarta.persistence.Subgraph;

EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

Subgraph<OrderLine> lineGraph =
    graph.addSubgraph("lines");

lineGraph.addAttributeNodes("product");
```

Áp dụng:

```java
PurchaseOrder order = em.createQuery("""
    select o
    from PurchaseOrder o
    where o.id = :id
    """, PurchaseOrder.class)
    .setParameter("id", orderId)
    .setHint("jakarta.persistence.fetchgraph", graph)
    .getSingleResult();
```

Dynamic graph hữu ích khi:

- Một use case có các biến thể fetch plan.
- Cấu trúc graph được xây từ cấu hình nội bộ đã kiểm soát.
- Muốn tái sử dụng một phần graph và thêm node theo điều kiện.
- Không muốn khai báo annotation graph cho mọi tổ hợp.

Tuy nhiên, không nên xây graph trực tiếp từ danh sách field do client gửi mà không whitelist. Điều đó có thể khiến API vô tình cho phép tải association nhạy cảm hoặc object graph rất lớn. Fetch plan nên là quyết định của ứng dụng dựa trên use case và quyền truy cập.

### 5.1. Tái sử dụng và kết hợp subgraph

Có thể lấy một named graph làm cơ sở và tạo bản sao để điều chỉnh:

```java
EntityGraph<?> base = em.getEntityGraph(
    "PurchaseOrder.summary"
);

EntityGraph<?> copy = em.createEntityGraph(base);
copy.addAttributeNodes("lines");
```

Khả năng sao chép graph và kiểu trả về cụ thể phụ thuộc API Jakarta Persistence version. Nếu cần graph phức tạp hoặc tái sử dụng nhiều tầng, có thể xây một factory nội bộ để giữ cấu trúc dễ đọc và tránh lặp chuỗi tên thuộc tính.

### 5.2. Map key subgraph

Nếu entity có thuộc tính Map:

```java
@ElementCollection
@CollectionTable(name = "localized_labels")
@MapKeyColumn(name = "locale")
private Map<String, Label> labels;
```

hoặc một map association với entity key/value, graph có thể dùng key subgraph để mô tả phần key cần tải khi phù hợp. Cấu trúc cụ thể tùy loại mapping và kiểu key/value; chỉ thêm key subgraph khi use case thực sự cần thuộc tính của entity key.

## 6. Fetch graph và load graph khác nhau thế nào?

Jakarta Persistence cung cấp hai cách diễn giải entity graph qua hint:

- `jakarta.persistence.fetchgraph`
- `jakarta.persistence.loadgraph`

Khác biệt quan trọng nằm ở cách xử lý những thuộc tính **không được khai báo trong graph**.

| Tiêu chí | Fetch graph | Load graph |
|---|---|---|
| Thuộc tính có trong graph | Được xem là eager cho lần tải này | Được xem là eager cho lần tải này |
| Thuộc tính không có trong graph | Được xem là lazy theo graph semantics | Giữ fetch behavior mặc định của mapping |
| Mapping mặc định EAGER | Graph có thể đặt thuộc tính không khai báo vào nhóm lazy theo semantics; provider vẫn có thể fetch thêm | Thuộc tính không khai báo tiếp tục theo mapping EAGER |
| Mapping mặc định LAZY | Không khai báo thì được xem là lazy | Không khai báo thì vẫn lazy |
| Ý định thường gặp | Định nghĩa một fetch plan cụ thể cho use case | Bổ sung một số thuộc tính vào fetch plan mặc định |

### 6.1. Ví dụ mapping có EAGER mặc định

JPA mặc định `@ManyToOne` và `@OneToOne` là EAGER nếu không khai báo khác; collection `@OneToMany` và `@ManyToMany` mặc định LAZY.

Giả sử:

```java
@ManyToOne
private Customer customer; // Mặc định EAGER theo JPA.

@OneToMany(mappedBy = "order")
private List<OrderLine> lines; // Mặc định LAZY.
```

Một fetch graph chỉ khai báo `lines`. Theo semantics của fetch graph, các thuộc tính không có trong graph được xem là lazy cho lần fetch đó, dù mapping mặc định có thể là EAGER. Provider vẫn được phép fetch thêm dữ liệu ngoài graph theo đặc tả, nên không thể coi graph là cam kết “SQL tuyệt đối không lấy thuộc tính nào khác”.

Với load graph chỉ khai báo `lines`, `customer` không được nêu vẫn tuân theo mapping mặc định, tức EAGER.

### 6.2. Chọn loại graph theo ý định

Dùng **fetch graph** khi muốn mô tả rõ tập thuộc tính mà use case cần, coi các thuộc tính không nêu là lazy theo semantics graph.

Dùng **load graph** khi muốn giữ mapping fetch mặc định rồi thêm một số association cần eager-load cho lần đọc.

Trong ứng dụng có nhiều association to-one mặc định EAGER, fetch graph thường hữu ích để kiểm soát fetch plan theo truy vấn. Dù vậy, hãy xác nhận provider có thực sự thực thi như mong muốn bằng SQL log và test.

### 6.3. Entity graph không thể bảo đảm mọi thứ khác đều chưa được tải

Jakarta Persistence cho phép provider fetch thêm state ngoài graph. Ngoài ra:

- Basic attributes có thể được tải theo mapping/provider.
- Association eager khác có thể tạo truy vấn phụ.
- Một entity đã có trong persistence context có thể đã initialized.
- Cache có thể cung cấp state mà không phát SQL.
- Provider có thể chọn nhiều câu SELECT thay vì một JOIN.

Do đó, graph là **yêu cầu fetch tối thiểu và hướng dẫn fetch semantics**, không phải bộ lọc bảo mật hoặc cam kết tuyệt đối về số cột SQL.

## 7. Named entity graph lồng nhiều cấp

Ví dụ trang chi tiết order cần:

- Customer.
- Các order line.
- Product của từng line.
- Category của từng product.

Có thể mô tả nhiều subgraph:

```java
@Entity
@NamedEntityGraph(
    name = "PurchaseOrder.fullDetail",
    attributeNodes = {
        @NamedAttributeNode("customer"),
        @NamedAttributeNode(
            value = "lines",
            subgraph = "line-detail"
        )
    },
    subgraphs = {
        @NamedSubgraph(
            name = "line-detail",
            attributeNodes = {
                @NamedAttributeNode(
                    value = "product",
                    subgraph = "product-detail"
                )
            }
        ),
        @NamedSubgraph(
            name = "product-detail",
            attributeNodes = {
                @NamedAttributeNode("category")
            }
        )
    }
)
public class PurchaseOrder {
    // ...
}
```

Cấu trúc:

```text
PurchaseOrder
  |
  +-- customer
  |
  +-- lines
        |
        +-- product
              |
              +-- category
```

Một graph nhiều cấp có thể hữu ích cho một trang chi tiết, nhưng không có nghĩa cần tải mọi association khác của category, customer hoặc product. Subgraph chỉ mở rộng các node được chỉ định.

### 7.1. Không biến graph thành toàn bộ object graph

Nếu category có parent/children, product có reviews, customer có orders, việc thêm tất cả vào graph có thể tạo object graph rất lớn, join phức tạp hoặc nhiều truy vấn thứ cấp.

Nên chọn đúng mức sâu mà use case cần. Nếu một màn hình cần một tập dữ liệu khác hẳn, hãy tạo graph riêng hoặc DTO projection thay vì tái sử dụng graph “full” cho mọi nơi.

### 7.2. Cẩn thận với chu trình entity

Domain có thể có quan hệ hai chiều:

```text
PurchaseOrder -> lines -> order -> lines -> ...
```

Entity graph không yêu cầu khai báo một vòng lặp vô hạn. Chỉ mô tả những đường thuộc tính cần tải. Không nên thêm subgraph quay ngược về root chỉ để “đảm bảo object hoàn chỉnh”.

## 8. Fetch profile là gì?

**Fetch profile** là cơ chế riêng của Hibernate ORM cho phép định nghĩa một nhóm override chiến lược fetch của các association. Khi profile được bật trên Hibernate Session, các association được khai báo trong profile có thể được fetch theo chế độ override, thường dùng `FetchMode.JOIN`.

Khác entity graph:

- Entity graph thuộc Jakarta Persistence và có thể dùng với các JPA provider.
- Fetch profile là Hibernate-specific.
- Entity graph mô tả attribute nodes và subgraphs.
- Fetch profile định nghĩa các association cụ thể cần thay đổi fetch strategy.
- Entity graph thường được áp dụng trên một query/find.
- Fetch profile được bật/tắt trên Session và ảnh hưởng các lần load phù hợp trong phạm vi Session khi profile đang hoạt động.

Fetch profile hữu ích khi một nhóm association thường được tải cùng nhau trong một workflow Hibernate-specific, và ứng dụng muốn bật cấu hình đó theo phạm vi Session.

## 9. Khai báo fetch profile bằng annotation Hibernate

Ví dụ Customer có collection orders:

```java
import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

import org.hibernate.annotations.FetchMode;
import org.hibernate.annotations.FetchProfile;

@Entity
@Table(name = "customers")
@FetchProfile(
    name = "customer-with-orders",
    fetchOverrides = {
        @FetchProfile.FetchOverride(
            entity = Customer.class,
            association = "orders",
            mode = FetchMode.JOIN
        )
    }
)
public class Customer {

    @Id
    private Long id;

    @Column(nullable = false)
    private String name;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {
    }

    public Long getId() {
        return id;
    }

    public List<PurchaseOrder> getOrders() {
        return orders;
    }
}
```

Các thành phần:

- `@FetchProfile(name = ...)` định nghĩa tên profile.
- `@FetchProfile.FetchOverride` xác định entity và association được override.
- `entity = Customer.class` chỉ ra mapping entity chứa association.
- `association = "orders"` là tên thuộc tính association Java trong entity.
- `mode = FetchMode.JOIN` yêu cầu Hibernate dùng chiến lược JOIN cho association khi profile có hiệu lực.

`FetchProfile` và `FetchMode` đến từ package `org.hibernate.annotations`, không phải Jakarta Persistence.

### 9.1. Tên association là tên thuộc tính mapping

Nếu entity có:

```java
@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> purchaseOrders;
```

thì profile cần dùng:

```java
association = "purchaseOrders"
```

không phải tên bảng `purchase_orders` hoặc tên cột `customer_id`.

### 9.2. Fetch profile có thể khai báo nhiều override

Một profile có thể gom nhiều association:

```java
@FetchProfile(
    name = "customer-dashboard",
    fetchOverrides = {
        @FetchProfile.FetchOverride(
            entity = Customer.class,
            association = "orders",
            mode = FetchMode.JOIN
        ),
        @FetchProfile.FetchOverride(
            entity = PurchaseOrder.class,
            association = "customer",
            mode = FetchMode.JOIN
        )
    }
)
```

Ví dụ chỉ minh họa cú pháp gom override; việc đưa cả hai đường vào cùng profile có hợp lý hay không phụ thuộc graph và query thực tế. Không thêm association trùng lặp hoặc tạo join vòng mà không có nhu cầu.

## 10. Bật và tắt fetch profile trên Session

Vì fetch profile là Hibernate-specific, ứng dụng lấy Session từ EntityManager:

```java
import org.hibernate.Session;

Session session = em.unwrap(Session.class);

session.enableFetchProfile("customer-with-orders");

Customer customer = session.find(Customer.class, customerId);
```

Khi profile được bật, Hibernate áp dụng override đã khai báo cho các lần load phù hợp trong Session.

Có thể tắt profile:

```java
session.disableFetchProfile("customer-with-orders");
```

Hoặc kiểm tra trạng thái:

```java
boolean enabled = session.isFetchProfileEnabled(
    "customer-with-orders"
);
```

Các API trên là Hibernate native. Không có API tương đương chuẩn Jakarta Persistence cho fetch profile.

### 10.1. Phạm vi Session

Fetch profile được bật trên Session hiện hành. Vì vậy:

- Các lần load tiếp theo trong Session có thể chịu ảnh hưởng profile.
- Profile không phải annotation mặc định cố định cho mọi request của ứng dụng.
- Tắt profile khi workflow không cần tiếp tục sử dụng nó.
- Không chia sẻ Session giữa các thread.
- Không giả định profile sẽ thay đổi trạng thái đã khởi tạo của association trong entity đã được load trước đó.

Trong ứng dụng Spring, Hibernate Session thường gắn với persistence context của transaction/request theo cấu hình. Nên bật profile trong một service/use case có boundary rõ và tránh thay đổi Session state ở nhiều tầng không kiểm soát.

### 10.2. Ví dụ service Hibernate-specific

```java
import jakarta.persistence.EntityManager;
import org.hibernate.Session;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerDashboardService {

    private final EntityManager em;

    public CustomerDashboardService(EntityManager em) {
        this.em = em;
    }

    @Transactional(readOnly = true)
    public Customer loadDashboard(Long customerId) {
        Session session = em.unwrap(Session.class);

        session.enableFetchProfile("customer-with-orders");

        try {
            return session.find(Customer.class, customerId);
        } finally {
            session.disableFetchProfile("customer-with-orders");
        }
    }
}
```

Ví dụ giả định profile đã được khai báo và Hibernate nhận diện nó. Việc trả entity ra khỏi transaction có thể khiến những association chưa được khởi tạo vẫn lazy; trong API thực tế nên chuyển sang DTO bên trong transaction hoặc định nghĩa rõ dữ liệu được trả về.

Việc tắt profile trong `finally` giúp tránh để Session tiếp tục bật profile ngoài đoạn code dự kiến. Tuy nhiên, nếu Session là transaction-bound và chỉ được dùng trong use case đó, hãy giữ cách quản lý profile nhất quán với lifecycle framework.

## 11. FetchMode.JOIN không có nghĩa luôn chỉ một câu SQL

Fetch profile có override `FetchMode.JOIN`, nhưng không nên diễn giải thành cam kết “mọi dữ liệu được tải bằng đúng một SQL duy nhất”.

SQL cuối cùng còn phụ thuộc:

- Loại association (to-one hay collection).
- Các fetch plan khác đang áp dụng.
- Query cụ thể và bảng tham gia.
- Database dialect.
- Persistence context đã chứa entity hay chưa.
- Hibernate version và cách xử lý fetch.

Nếu profile yêu cầu join collection, kết quả SQL có thể tạo nhiều hàng cho một root. Nếu cần tải nhiều collection, join có thể làm số hàng tăng theo tích số phần tử của từng collection.

### 11.1. Fetch profile thay đổi chiến lược fetch của association

Nó không thay đổi:

- Điều kiện WHERE.
- Quyền truy cập.
- Sort order.
- Page size.
- Cách serialize DTO.
- Vòng đời entity.
- Constraint database.

Profile chỉ là công cụ fetch; nó không thay query và không thay aggregate boundary.

## 12. So sánh EntityGraph và FetchProfile

| Tiêu chí | Entity graph | Hibernate fetch profile |
|---|---|---|
| Nguồn API | Jakarta Persistence | Hibernate ORM |
| Tính di động | Có thể dùng với JPA provider khác | Chỉ Hibernate |
| Cấu trúc | Attribute nodes, subgraphs, key subgraphs | Các association fetch overrides |
| Phạm vi áp dụng | Query/find cụ thể bằng hint hoặc API | Hibernate Session khi profile được bật |
| Khai báo | Annotation named graph hoặc dynamic graph | `@FetchProfile` |
| Thao tác kích hoạt | `fetchgraph` / `loadgraph` | `enableFetchProfile` |
| Ngữ nghĩa | Quy định thuộc tính cần fetch theo graph semantics | Override fetch strategy của association |
| Có đảm bảo một SQL JOIN? | Không | Không |
| Tích hợp Spring Data | `@EntityGraph` | Thường cần Hibernate Session/native integration |
| Dùng khi | Muốn fetch plan theo use case và portability | Muốn bật một nhóm fetch override trong Hibernate Session |

### 12.1. Khi nào chọn EntityGraph?

- Ứng dụng sử dụng JPA abstraction và muốn giữ tính di động.
- Fetch plan gắn với repository method hoặc một query cụ thể.
- Cần mô tả đường đi nested như `lines.product.category`.
- Muốn khai báo graph có tên để tái sử dụng.
- Muốn dùng Spring Data JPA `@EntityGraph`.

### 12.2. Khi nào chọn FetchProfile?

- Ứng dụng chủ động phụ thuộc Hibernate.
- Một nhóm association cần override chiến lược fetch trong phạm vi Session.
- Workflow có nhiều lần load entity và muốn bật một profile trong suốt phạm vi đó.
- Cần dùng tính năng Hibernate-specific và chấp nhận phụ thuộc provider.

### 12.3. Có nên dùng cả hai cùng lúc?

Có thể có những ứng dụng dùng cả hai cơ chế, nhưng không nên chồng nhiều fetch policy một cách tùy tiện. Khi entity graph, fetch profile, mapping EAGER/LAZY và query fetch join cùng tác động, cần kiểm tra cách Hibernate kết hợp chúng trong phiên bản cụ thể.

Hãy chọn một fetch plan chính cho use case, bổ sung cơ chế khác chỉ khi có lý do rõ ràng, rồi quan sát SQL và kết quả khởi tạo association.

## 13. Entity graph, fetch profile và JOIN FETCH khác nhau ra sao?

Một cách khác để định nghĩa dữ liệu cần tải là viết trực tiếp `JOIN FETCH` trong JPQL/HQL:

```java
List<PurchaseOrder> orders = em.createQuery("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.customer
    left join fetch o.lines l
    left join fetch l.product
    where o.status = :status
    """, PurchaseOrder.class)
    .setParameter("status", "SUBMITTED")
    .getResultList();
```

`JOIN FETCH` thể hiện rõ trong query association cần tải. So sánh:

| Cơ chế | Nơi mô tả fetch | Điểm mạnh |
|---|---|---|
| JPQL/HQL `JOIN FETCH` | Ngay trong câu query | SQL intent rõ, dễ đọc cho query cụ thể |
| EntityGraph | Graph metadata, áp dụng bằng hint | Tách fetch plan khỏi query predicate |
| FetchProfile | Hibernate Session profile | Bật nhóm override association theo phạm vi Session |
| Mapping EAGER/LAZY | Annotation/XML mapping | Đặt mặc định cho association |

### 13.1. JOIN FETCH phù hợp query đặc thù

Nếu chỉ có một query cần customer và lines, `JOIN FETCH` có thể rất dễ hiểu. Nhưng nếu nhiều repository method cần cùng một graph, entity graph có thể giúp tái sử dụng mà không lặp lại path trong JPQL.

### 13.2. EntityGraph không thay thế WHERE/JOIN logic

Entity graph không giúp lọc chỉ một số child theo điều kiện một cách trực tiếp như query join có predicate. Nếu cần “order và chỉ các line chưa giao”, hãy thiết kế query/DTO phù hợp; không coi graph là một bộ lọc collection.

### 13.3. FetchProfile không thay thế query

Fetch profile thay chiến lược tải association khi Session load entity, nhưng query vẫn quyết định root rows. Nếu muốn chỉ lấy order trạng thái SUBMITTED, điều kiện đó phải nằm trong query.

## 14. Fetch nhiều collection và nguy cơ Cartesian product

Giả sử một order có:

- 5 lines.
- 4 payments.
- 3 shipments.

Nếu join cùng lúc cả ba collection, số hàng SQL cho một order có thể tăng theo tích số phần tử: `5 × 4 × 3 = 60` hàng, dù chỉ có một root entity.

```text
PurchaseOrder
    |
    +-- lines (5)
    |
    +-- payments (4)
    |
    +-- shipments (3)

JOIN cả ba collection:
    có thể tạo 5 × 4 × 3 = 60 tổ hợp hàng
```

Hệ quả:

- Dữ liệu lặp ở các cột root/to-one.
- Tăng lượng dữ liệu truyền từ DB.
- Tốn bộ nhớ để hydrate và loại duplicate.
- Query có thể chậm dù số root nhỏ.
- Hibernate có thể từ chối fetch nhiều bag đồng thời bằng `MultipleBagFetchException` tùy mapping.

Entity graph cũng có thể dẫn tới chiến lược fetch làm phát sinh join/secondary select; việc dùng graph không loại bỏ nguy cơ này.

### 14.1. Không fetch tất cả collection chỉ vì trang chi tiết

Có thể tải order và lines cùng product, nhưng tải payments hoặc shipments bằng query riêng nếu UI hiển thị ở tab khác. Đây thường là trade-off tốt hơn một graph khổng lồ.

### 14.2. Tách query theo phần dữ liệu

Ví dụ:

```java
PurchaseOrder order = loadOrderWithLines(orderId);
List<Payment> payments = paymentRepository.findByOrderId(orderId);
List<Shipment> shipments = shipmentRepository.findByOrderId(orderId);
```

Nếu các phần cần được đọc nhất quán, thực hiện chúng trong một transaction đọc phù hợp; nếu có thể thay đổi đồng thời, xét isolation và snapshot semantics. Tách query không nhất thiết có nghĩa tách transaction.

## 15. Pagination và collection fetch

Một lỗi phổ biến là dùng fetch collection trong query phân trang:

```java
Page<PurchaseOrder> page = repository.findAllWithLines(
    pageable
);
```

Khi join collection, một order có nhiều line tạo nhiều hàng SQL. Database phân trang trên **row kết quả join**, không phải luôn theo root entity như lập trình viên mong đợi. Hibernate có thể phải xử lý pagination trong memory, cảnh báo hoặc từ chối theo cấu hình/version.

### 15.1. Hai bước đọc thường dễ kiểm soát hơn

Một cách phổ biến:

1. Phân trang ID/root entity trước.
2. Tải graph cần thiết cho tập ID của trang đó.

Ví dụ:

```java
Page<UUID> ids = em.createQuery("""
    select o.id
    from PurchaseOrder o
    where o.status = :status
    order by o.createdAt desc, o.id
    """, UUID.class)
    .setParameter("status", "SUBMITTED")
    .setFirstResult(offset)
    .setMaxResults(pageSize)
    .getResultList();
```

Sau đó tải dữ liệu cần thiết:

```java
List<PurchaseOrder> orders = em.createQuery("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.customer
    where o.id in :ids
    """, PurchaseOrder.class)
    .setParameter("ids", ids)
    .getResultList();
```

Ví dụ trên chỉ fetch to-one customer trong query thứ hai; nếu cần lines, có thể dùng query tiếp theo theo ID order hoặc graph phù hợp. `IN` không bảo đảm giữ thứ tự của danh sách ID, vì vậy cần sắp lại theo thứ tự trang hoặc đưa thứ tự vào query thích hợp.

### 15.2. Không tải collection khổng lồ bằng graph

Nếu một order có hàng chục nghìn lines, việc dùng entity graph để tải toàn bộ collection có thể gây vấn đề bộ nhớ. Dùng query riêng có phân trang hoặc DTO projection cho line list.

## 16. Entity graph không phải DTO projection

Một nhầm lẫn thường gặp: “Graph chỉ khai báo customer.name, vậy Hibernate chỉ chọn hai cột id và name của customer?”

Không nhất thiết. Entity graph định nghĩa **attribute fetch state của entity**, không phải danh sách cột projection chính xác. Khi tải một association entity, provider thường tải state entity theo mapping và các thuộc tính cần thiết; SQL có thể chọn nhiều cột hơn các field UI thực sự hiển thị.

Nếu use case chỉ cần một số giá trị, DTO projection thường rõ và nhẹ hơn.

Ví dụ:

```java
public record OrderListRow(
    UUID id,
    String status,
    String customerName
) {}
```

Query:

```java
List<OrderListRow> rows = em.createQuery("""
    select new com.example.orders.OrderListRow(
        o.id,
        o.status,
        c.name
    )
    from PurchaseOrder o
    join o.customer c
    where o.status = :status
    order by o.createdAt desc
    """, OrderListRow.class)
    .setParameter("status", "SUBMITTED")
    .getResultList();
```

DTO projection:

- Chỉ trả các trường được khai báo trong constructor/record.
- Không tạo một graph entity để serializer duyệt.
- Có thể tránh giữ nhiều entity trong persistence context.
- Phù hợp read model/list/report.

Đổi lại, DTO không phải managed entity để dirty checking. Nếu use case cần thay đổi aggregate, tải entity managed và áp dụng domain operation phù hợp.

## 17. Entity graph và fetch profile có thay đổi mapping mặc định không?

Thông thường, graph/profile là **fetch plan tạm thời cho thao tác đọc**, không viết lại annotation mapping toàn cục.

Ví dụ:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
```

Mapping vẫn mô tả customer là lazy theo mặc định. Một query áp dụng graph có customer hoặc Session bật profile có thể yêu cầu tải customer trong lần load tương ứng.

Sau khi thao tác kết thúc:

- Association đã được khởi tạo trong persistence context vẫn giữ trạng thái initialized.
- Association chưa tải vẫn có thể lazy nếu context còn hoạt động và mapping hỗ trợ.
- Graph/profile không biến association thành một mapping eager vĩnh viễn.
- Entity detached không thể tiếp tục truy vấn lazy nếu không có cơ chế context phù hợp.

Không nên thay fetch mode mapping liên tục để phục vụ từng màn hình; giữ mapping mặc định hợp lý và định nghĩa fetch plan tại query/use case.

## 18. Fetch plan và persistence context đã có entity

EntityManager duy trì một persistence context với identity map: cùng một entity type + ID trong cùng context thường tương ứng với một managed instance.

Ví dụ:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);

// Tải lại bằng một query có entity graph.
PurchaseOrder same = em.createQuery("""
    select o from PurchaseOrder o where o.id = :id
    """, PurchaseOrder.class)
    .setParameter("id", orderId)
    .setHint("jakarta.persistence.fetchgraph", graph)
    .getSingleResult();
```

`same` thường là managed instance tương ứng đã có trong persistence context. Provider có thể khởi tạo association theo fetch plan khi cần, nhưng không nên giả định graph tạo một object mới hoặc reset trạng thái hiện tại.

Khi test fetch plan:

- Dùng EntityManager mới cho từng kịch bản.
- Có thể `clear()` trước query nếu đã flush các thay đổi cần giữ.
- Kiểm soát second-level cache và query cache.
- Quan sát association initialization và SQL.
- Không dùng việc Java getter trả được giá trị làm bằng chứng chắc chắn một SQL vừa chạy.

### 18.1. Kiểm tra association đã khởi tạo

Với Hibernate:

```java
import org.hibernate.Hibernate;

boolean initialized = Hibernate.isInitialized(
    order.getLines()
);
```

`Hibernate.isInitialized` là API riêng Hibernate giúp kiểm tra trạng thái proxy/collection. Nó hữu ích khi debug hoặc viết kiểm thử integration, nhưng không nên biến thành điều kiện nghiệp vụ của domain.

## 19. Kết hợp fetch plan với transaction và DTO

Một repository method có thể tải entity graph trong transaction, sau đó service chuyển sang DTO:

```java
@Transactional(readOnly = true)
public OrderDetailView getDetail(UUID orderId) {
    PurchaseOrder order = repository.findDetailedById(orderId)
        .orElseThrow(() -> new OrderNotFoundException(orderId));

    List<OrderLineView> lines = order.getLines().stream()
        .map(line -> new OrderLineView(
            line.getProduct().getName(),
            line.getQuantity()
        ))
        .toList();

    return new OrderDetailView(
        order.getId(),
        order.getCustomer().getName(),
        lines
    );
}
```

Các DTO/exception là kiểu ứng dụng định nghĩa. Với graph detail chứa customer, lines và product, service có thể đọc các thuộc tính trong transaction rồi trả DTO độc lập.

Ưu điểm:

- Serializer không tự quyết định fetch graph.
- Không phụ thuộc Session còn mở sau khi service kết thúc.
- API chỉ công khai các trường được chọn.
- Có thể thay đổi query/fetch plan mà không thay đổi JSON contract.

Không cần bật Open Session in View chỉ để controller đọc lazy association. Hãy tải dữ liệu cần thiết và tạo DTO tại ranh giới service.

## 20. Fetch profile và EntityGraph trong Spring Data JPA

Spring Data JPA có tích hợp trực tiếp entity graph:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, UUID> {

    @EntityGraph(
        attributePaths = {"customer", "lines.product"},
        type = EntityGraph.EntityGraphType.FETCH
    )
    Optional<PurchaseOrder> findDetailedById(UUID id);

    @EntityGraph(
        attributePaths = {"customer"},
        type = EntityGraph.EntityGraphType.FETCH
    )
    Page<PurchaseOrder> findByStatus(
        String status,
        Pageable pageable
    );
}
```

Ví dụ thứ hai chỉ fetch customer là to-one nên thường ít gặp vấn đề pagination do collection join hơn. Tuy vậy, vẫn cần kiểm tra SQL và count query của Spring Data theo phiên bản/provider.

Fetch profile không có annotation Spring Data chuẩn tương đương. Có thể bật profile trong service bằng cách unwrap Session:

```java
Session session = em.unwrap(Session.class);
session.enableFetchProfile("customer-with-orders");

try {
    return session.find(Customer.class, customerId);
} finally {
    session.disableFetchProfile("customer-with-orders");
}
```

Nếu repository được gọi trong cùng Session và profile đã bật, các load phù hợp có thể chịu ảnh hưởng. Hãy giữ phạm vi bật profile rõ ràng; không bật ở một method rồi để Session tiếp tục dùng profile trong một workflow khác ngoài dự kiến.

## 21. Những giới hạn khi dùng EntityGraph

### 21.1. Provider có thể fetch nhiều hơn graph

Graph mô tả thuộc tính cần fetch, nhưng provider có quyền fetch thêm. Do đó, không dùng graph làm cơ chế bảo vệ dữ liệu hoặc cam kết tuyệt đối không tải association nhạy cảm.

Authorization và DTO vẫn phải kiểm soát dữ liệu được trả ra.

### 21.2. Không bảo đảm số SQL

Một graph có thể được thực hiện bằng join hoặc secondary selects. Nếu association có nhiều collection, provider có thể chọn cách tránh một join quá lớn.

Hãy kiểm tra SQL thực tế, không đánh giá hiệu quả chỉ từ annotation.

### 21.3. Subgraph phức tạp làm graph khó bảo trì

Graph nhiều tầng có thể trở thành một cấu trúc lớn khó hiểu. Đặt tên theo use case như `PurchaseOrder.summary`, `PurchaseOrder.detail` thay vì tên chung chung `full`/`all`.

### 21.4. Không thay thế fetch join khi query có logic đặc thù

Nếu cần join để lọc theo thuộc tính association, group, order hoặc aggregate, query vẫn cần biểu đạt logic đó. Entity graph chỉ định fetch, không thay thế predicate.

### 21.5. Entity graph không phải công cụ chọn một phần collection

Nếu cần chỉ một số phần tử của collection theo điều kiện, hãy viết query/DTO riêng. Đừng dùng graph để kỳ vọng Hibernate chỉ load những child đáp ứng predicate mà graph không mô tả.

## 22. Những giới hạn khi dùng FetchProfile

### 22.1. Phụ thuộc Hibernate

Code bật profile dùng `org.hibernate.Session` và annotation `org.hibernate.annotations.FetchProfile`. Điều này tạo phụ thuộc provider; nếu ứng dụng cần thay JPA provider, phải thay cơ chế tương ứng.

### 22.2. Scope là Session

Profile bật trong Session và có thể ảnh hưởng nhiều lần load. Nếu Session kéo dài qua nhiều thao tác, việc không disable profile có thể làm query sau tải dữ liệu ngoài dự kiến.

### 22.3. Profile mô tả association override, không phải projection

Profile không giới hạn các cột scalar theo DTO. Nó thay fetch strategy của association đã mapping; không phải cơ chế chọn một vài thuộc tính.

### 22.4. JOIN collection vẫn có thể phình dữ liệu

Dùng FetchMode.JOIN cho nhiều collection có thể gây Cartesian product hoặc vấn đề multiple bag. Profile không loại bỏ giới hạn SQL của database.

### 22.5. Đã khởi tạo association thì profile không “hủy tải”

Nếu association đã initialized trong persistence context, bật profile sau đó không làm nó quay lại lazy. Để quan sát profile, cần hiểu trạng thái entity và thời điểm bật.

## 23. Tránh fetch quá nhiều: dấu hiệu và cách điều chỉnh

Một fetch plan quá rộng có thể biểu hiện qua:

- SQL có nhiều JOIN hơn cần thiết.
- Một root lặp lại hàng chục/hàng trăm lần trong result set.
- Số lượng entity trong persistence context tăng nhanh.
- Response chậm dù chỉ hiển thị một vài field.
- Nhiều collection được khởi tạo mà use case không dùng.
- Pagination bị xử lý trong memory hoặc có cảnh báo.
- Bộ nhớ tăng trong các màn hình chi tiết.

Một fetch plan quá hẹp có thể biểu hiện qua:

- N+1 query khi duyệt association.
- LazyInitializationException khi code đọc ngoài transaction.
- Nhiều truy vấn nhỏ cho cùng một màn hình.
- Serializer tự kích hoạt lazy loading.

Cách điều chỉnh:

1. Ghi rõ dữ liệu mà use case cần.
2. Dùng entity graph/fetch profile cho association entity thực sự cần.
3. Dùng DTO projection nếu chỉ cần scalar fields.
4. Tải collection lớn theo query riêng có phân trang.
5. Tránh fetch nhiều bag/collection cùng lúc.
6. Đo SQL, số statement và lượng dữ liệu trả về.
7. Kiểm tra trong persistence context mới để tránh cache làm sai kết luận.

## 24. Lựa chọn chiến lược theo từng use case

| Use case | Cơ chế thường phù hợp | Lý do |
|---|---|---|
| Trang danh sách order cần customer name | DTO projection hoặc EntityGraph to-one customer | Tránh tải lines/products nếu không cần |
| Trang chi tiết order cần customer, lines, product | Named/dynamic EntityGraph hoặc JPQL fetch join | Mô tả rõ graph nhiều cấp |
| Một workflow Hibernate-specific cần luôn tải orders cùng customer trong Session | FetchProfile | Bật nhóm association override theo scope |
| Query cần lọc/sắp xếp theo association | JPQL/HQL join + fetch strategy phù hợp | Fetch plan không thay predicate |
| Báo cáo chỉ cần vài cột từ nhiều bảng | DTO projection/native SQL | Không cần managed object graph |
| Collection có hàng nghìn phần tử | Query collection riêng có pagination | Tránh tải toàn bộ collection vào memory |
| API trả JSON | DTO được tạo trong transaction | Tránh serializer tự duyệt lazy graph |
| Ứng dụng cần portability giữa JPA providers | EntityGraph | Chuẩn Jakarta Persistence |
| Ứng dụng phụ thuộc Hibernate và muốn override fetch mode theo Session | FetchProfile | Hibernate-specific |

Không có một annotation duy nhất tối ưu cho mọi truy vấn. Hãy bắt đầu từ dữ liệu mà use case cần và chọn cơ chế diễn đạt phù hợp.

## 25. Cách quan sát SQL và trạng thái fetch

Để xác nhận graph/profile hoạt động như dự kiến, có thể thực hiện các phép thử trong môi trường development/test.

### 25.1. Bật SQL logging

Trong cấu hình Hibernate, bật log SQL và bind parameters phù hợp với version/framework. Cú pháp cấu hình có thể khác nhau giữa Spring Boot/Hibernate versions.

Quan sát:

- Có bao nhiêu SELECT?
- Query có JOIN customer/lines/product không?
- Có secondary select sau query root không?
- Có query nào chỉ phát sinh khi gọi getter không?
- Số hàng SQL có tăng mạnh vì join collection không?

Không bật bind parameter logging chứa dữ liệu nhạy cảm trong production nếu không có chính sách bảo vệ log.

### 25.2. Kiểm tra initialized state

```java
PurchaseOrder order = repository.findDetailedById(orderId)
    .orElseThrow();

boolean customerLoaded =
    Hibernate.isInitialized(order.getCustomer());

boolean linesLoaded =
    Hibernate.isInitialized(order.getLines());
```

Nếu graph có subgraph product, có thể kiểm tra từng line:

```java
for (OrderLine line : order.getLines()) {
    boolean productLoaded =
        Hibernate.isInitialized(line.getProduct());
}
```

Các phép kiểm tra này chỉ có ý nghĩa trong context/provider phù hợp. Không dùng chúng để thay thế hợp đồng API hay authorization.

### 25.3. So sánh trong EntityManager mới

Nếu trước đó order đã được load và association initialized, query graph sau đó có thể không thể hiện đúng sự khác biệt. Mỗi kịch bản nên dùng persistence context mới và cache state được kiểm soát.

### 25.4. Đo số statement

Hibernate có thể cung cấp statistics nếu bật cấu hình statistics phù hợp. Thống kê số prepared statements/entity fetch/collection fetch có thể giúp so sánh các fetch plan.

Đo ở mức use case thực tế, gồm số order, số lines, số customer khác nhau và kích thước dữ liệu; một test chỉ có một order thường không bộc lộ N+1.

## 26. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng graph nhưng kỳ vọng đúng một SQL JOIN | Thực tế có thể có secondary SELECT | Kiểm tra SQL và xem graph là fetch requirement |
| Nhầm tên cột với tên attribute node | Graph không tìm được thuộc tính mapping | Dùng tên field/property Java |
| Quên subgraph cho đường nested | Entity đích được tải nhưng association sâu hơn vẫn lazy | Khai báo subgraph cho đường cần thiết |
| Dùng loadgraph khi muốn bỏ mapping EAGER không khai báo | Association EAGER mặc định vẫn có thể được fetch | Cân nhắc fetchgraph và kiểm chứng |
| Fetch nhiều collection cùng lúc | Cartesian product, duplicate root, multiple bag | Tách query hoặc DTO |
| Phân trang với collection fetch join | Pagination sai/khó tối ưu hoặc bị xử lý trong memory | Phân trang root IDs rồi tải association cần thiết |
| Dùng EntityGraph như DTO | Tải nhiều cột/entity hơn cần thiết | Dùng projection |
| Bật fetch profile rồi quên disable | Query sau có thể tải thêm association | Giới hạn scope và tắt trong finally |
| Bật profile sau khi entity đã được load | Association initialized trước đó không bị “unload” | Bật trước lần load; dùng context mới khi test |
| Dùng fetch profile trong code portable JPA | Phụ thuộc Hibernate Session | Dùng EntityGraph nếu cần provider portability |
| Dùng graph làm authorization | Dữ liệu vẫn có thể được fetch thêm và không được bảo vệ | Kiểm tra quyền và map DTO rõ ràng |
| Trả entity ra serializer | Lazy load/N+1/lỗi context đóng | Chuyển sang DTO trong transaction |
| Graph quá lớn dùng cho mọi endpoint | Tải dư, query phức tạp, memory tăng | Graph riêng theo use case |
| Dùng fetch plan để lọc collection | Graph không biểu đạt predicate collection tùy ý | Viết query/DTO chuyên biệt |

## 27. Ví dụ tổng hợp: hai fetch plan cho cùng một entity

Giả sử `PurchaseOrder` có `customer` và `lines`; `OrderLine` có `product`.

### Trang danh sách

Chỉ cần order ID, trạng thái, tên khách hàng:

```java
public record OrderSummary(
    UUID id,
    String status,
    String customerName
) {}
```

```java
List<OrderSummary> summaries = em.createQuery("""
    select new com.example.orders.OrderSummary(
        o.id,
        o.status,
        c.name
    )
    from PurchaseOrder o
    join o.customer c
    where o.status = :status
    order by o.createdAt desc
    """, OrderSummary.class)
    .setParameter("status", "SUBMITTED")
    .getResultList();
```

Không cần tải entity graph đầy đủ vì màn hình chỉ cần scalar fields.

### Trang chi tiết

Cần customer, lines và product:

```java
EntityGraph<?> graph = em.getEntityGraph(
    "PurchaseOrder.detail"
);

PurchaseOrder order = em.createQuery("""
    select o
    from PurchaseOrder o
    where o.id = :id
    """, PurchaseOrder.class)
    .setParameter("id", orderId)
    .setHint("jakarta.persistence.fetchgraph", graph)
    .getSingleResult();
```

Trong cùng transaction, service chuyển thành DTO:

```java
List<OrderLineView> lineViews = order.getLines().stream()
    .map(line -> new OrderLineView(
        line.getProduct().getName(),
        line.getQuantity()
    ))
    .toList();

OrderDetailView detail = new OrderDetailView(
    order.getId(),
    order.getCustomer().getName(),
    lineViews
);
```

Hai use case đọc cùng aggregate nhưng có nhu cầu dữ liệu khác nhau. **Không cần một mapping EAGER duy nhất để phục vụ cả hai.**

## 28. Quy trình thiết kế fetch plan

Khi tạo một query/use case mới, có thể làm theo trình tự:

1. **Xác định dữ liệu đầu ra.** Màn hình/API cần root, association nào và sâu bao nhiêu cấp?
2. **Phân biệt entity với DTO.** Nếu chỉ cần vài scalar, chọn projection trước khi tạo object graph.
3. **Giữ mapping mặc định hợp lý.** Tránh eager toàn cục chỉ để giải quyết một endpoint.
4. **Chọn cơ chế fetch.** EntityGraph cho fetch plan JPA; FetchProfile khi cần Hibernate-specific Session override; JOIN FETCH cho query đặc thù.
5. **Khai báo đường nested có chủ đích.** Chỉ thêm subgraph cho association cần đọc.
6. **Xét cardinality.** To-one thường ít nhân bản hàng; nhiều collection có thể gây Cartesian product.
7. **Xét pagination.** Tránh collection fetch join trực tiếp với page root nếu không hiểu hệ quả.
8. **Giữ transaction phù hợp.** Đọc association lazy và chuyển DTO trong persistence context thích hợp.
9. **Kiểm tra SQL trong context mới.** Đo statement count, rows và thời gian.
10. **Kiểm tra authorization riêng.** Fetch plan không phải chính sách bảo mật.
11. **Đặt tên graph/profile theo use case.** Ví dụ summary, detail, dashboard thay vì một graph all-purpose.
12. **Theo dõi khi domain thay đổi.** Thêm association mới không có nghĩa mọi graph đều cần thêm node đó.

## 29. Ghi nhớ

- **EntityGraph** là cơ chế Jakarta Persistence để mô tả attribute nodes và subgraphs cần fetch cho một lần tải entity.
- Entity graph có thể được khai báo bằng `@NamedEntityGraph` hoặc tạo động bằng `EntityManager.createEntityGraph`.
- Dùng `jakarta.persistence.fetchgraph` khi muốn các thuộc tính trong graph được xem là eager và các thuộc tính không khai báo được xem là lazy theo graph semantics.
- Dùng `jakarta.persistence.loadgraph` khi muốn fetch các thuộc tính trong graph và giữ mapping fetch mặc định cho thuộc tính không khai báo.
- Provider vẫn có thể fetch thêm; entity graph không bảo đảm SQL chỉ chứa các cột/association đã liệt kê hoặc chỉ có một câu JOIN.
- **Subgraph** mô tả đường association sâu hơn, ví dụ `lines.product.category`.
- Spring Data JPA cung cấp `@EntityGraph` để áp named graph hoặc `attributePaths` cho repository method.
- **FetchProfile** là cơ chế riêng Hibernate, định nghĩa association fetch overrides và được bật bằng `Session.enableFetchProfile`.
- Fetch profile có scope Session và thường dùng `FetchMode.JOIN` để override cách fetch association; nó không phải API JPA portable.
- Entity graph và fetch profile đều định nghĩa fetch plan, không thay query predicate, authorization hay DTO projection.
- Fetch nhiều collection cùng lúc có thể tạo Cartesian product, duplicate root hoặc `MultipleBagFetchException`.
- Phân trang root cùng collection fetch cần thiết kế cẩn thận; có thể phân trang ID trước rồi tải association theo batch.
- DTO projection phù hợp khi chỉ cần một số trường; entity graph phù hợp khi use case cần managed entity và association.
- Kiểm tra SQL, initialized state và số statement trong persistence context mới; cache và entity đã managed có thể che khuất hành vi fetch.
- Chọn graph/profile theo use case để tránh cả N+1 lẫn tải dư dữ liệu.

**Kết luận:** Entity graph và fetch profile cho phép ứng dụng mô tả **dữ liệu cần tải ở thời điểm đọc** mà không phải biến mọi association thành eager trong mapping. EntityGraph phù hợp khi cần fetch plan theo chuẩn JPA và gắn với query; FetchProfile phù hợp khi chủ động dùng Hibernate và muốn bật nhóm override theo Session. Chọn đúng graph cho từng use case, kết hợp DTO projection khi chỉ cần scalar fields và kiểm tra SQL thực tế sẽ giúp kiểm soát N+1, lượng dữ liệu tải và kích thước persistence context.
