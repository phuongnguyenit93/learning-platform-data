# Phân biệt fetch graph và load graph trong Spring Data JPA

JPA EntityGraph là cơ chế chỉ định những thuộc tính cần được tải khi một entity được truy vấn. Spring Data JPA tích hợp EntityGraph qua annotation @EntityGraph, giúp repository chọn fetch plan theo từng use case mà không phải thay đổi mapping FetchType trên entity hoặc viết JOIN FETCH cho mọi truy vấn.

Hai chế độ quan trọng là **fetch graph** và **load graph**. Cả hai đều coi các thuộc tính được liệt kê trong graph là cần tải eager. Khác biệt nằm ở các thuộc tính không được liệt kê: fetch graph xem chúng là lazy theo ngữ nghĩa của graph; load graph giữ fetch behavior mặc định được khai báo trên mapping. Hiểu đúng khác biệt này giúp tránh tải dữ liệu thừa, hạn chế N+1 và thiết kế truy vấn phù hợp với từng màn hình.

## 1. Fetch plan và EntityGraph là gì?

Một entity có thể liên kết với nhiều entity khác. Ví dụ PurchaseOrder có Customer và nhiều OrderItem; mỗi OrderItem lại liên kết với Product.

Khi chỉ tải PurchaseOrder, ứng dụng có thể cần:

- Màn hình danh sách: chỉ cần ID, mã đơn, ngày tạo và trạng thái.
- Màn hình chi tiết: cần Customer và danh sách OrderItem.
- Màn hình chi tiết đầy đủ: cần Customer, OrderItem và Product của từng dòng.
- Màn hình báo cáo: có thể chỉ cần một số trường tổng hợp, không cần entity graph.

Fetch plan là kế hoạch xác định phần trạng thái nào của entity và quan hệ được tải trong một lần truy vấn/use case. EntityGraph cho phép mô tả các thuộc tính cần được tải mà không buộc ứng dụng phải chỉ định chính xác SQL JOIN như thế nào.

Ví dụ, graph cho PurchaseOrder có thể yêu cầu:

~~~text
PurchaseOrder
  +-- customer
  +-- items
        +-- product
~~~

Graph này diễn đạt nhu cầu dữ liệu. JPA provider có thể thực hiện bằng JOIN, secondary SELECT hoặc chiến lược tải phù hợp. EntityGraph không cam kết một câu SQL duy nhất.

## 2. Mapping FetchType và EntityGraph khác nhau thế nào?

FetchType được khai báo trên mapping entity:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToMany(mappedBy = "purchaseOrder", fetch = FetchType.LAZY)
private List<OrderItem> items = new ArrayList<>();
~~~

Mapping quy định hành vi tải mặc định cho các lần sử dụng entity. Ngược lại, EntityGraph điều chỉnh fetch plan cho một truy vấn hoặc thao tác cụ thể.

| Cơ chế | Phạm vi | Mục đích |
|---|---|---|
| FetchType.LAZY/EAGER | Mapping entity | Khai báo hành vi tải mặc định |
| Fetch graph | Một truy vấn/thao tác | Các thuộc tính trong graph được yêu cầu tải; thuộc tính ngoài graph có ngữ nghĩa LAZY |
| Load graph | Một truy vấn/thao tác | Các thuộc tính trong graph được yêu cầu tải; thuộc tính ngoài graph giữ mapping default |
| JOIN FETCH | Một JPQL query | Chỉ rõ association được fetch trong câu query |

Một entity có thể dùng cùng mapping nhưng các repository method khác nhau áp dụng EntityGraph khác nhau. Điều này giúp giữ mapping mặc định gọn và chỉ tải quan hệ cần thiết cho từng use case.

## 3. Quy tắc chính: fetch graph và load graph

Giả sử entity PurchaseOrder có mapping:

~~~java
@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @ManyToOne(fetch = FetchType.EAGER)
    private SalesRegion region;

    @OneToMany(mappedBy = "purchaseOrder", fetch = FetchType.LAZY)
    private List<OrderItem> items = new ArrayList<>();
}
~~~

EntityGraph chỉ liệt kê thuộc tính customer.

**Fetch graph (jakarta.persistence.fetchgraph):**

- customer được yêu cầu tải eager vì nằm trong graph.
- region không nằm trong graph nên có ngữ nghĩa lazy theo fetch graph.
- items không nằm trong graph nên có ngữ nghĩa lazy theo fetch graph.

**Load graph (jakarta.persistence.loadgraph):**

- customer được yêu cầu tải eager vì nằm trong graph.
- region không nằm trong graph nên giữ mapping default EAGER.
- items không nằm trong graph nên giữ mapping default LAZY.

Có thể nhớ bằng bảng:

| Thuộc tính | Mapping | Fetch graph | Load graph |
|---|---|---|---|
| customer | LAZY | EAGER theo graph | EAGER theo graph |
| region | EAGER | LAZY theo graph | EAGER theo mapping |
| items | LAZY | LAZY theo graph | LAZY theo mapping |

Quy tắc này mô tả semantics của graph theo Jakarta Persistence. Provider được phép tải thêm trạng thái ngoài graph nếu cần. Vì vậy, fetch graph không phải cam kết rằng SQL tuyệt đối không lấy thêm cột hoặc association nào khác.

## 4. Ý nghĩa của “được tải eager” trong EntityGraph

Khi một thuộc tính được liệt kê trong EntityGraph, provider phải bảo đảm thuộc tính đó được tải theo fetch plan khi kết quả entity được trả về. Tuy nhiên, cách thực hiện không nhất thiết là JOIN trong cùng SQL.

Ví dụ graph yêu cầu customer và items:

- Provider có thể tạo SQL JOIN.
- Provider có thể tải root entity rồi chạy truy vấn bổ sung cho quan hệ.
- Provider có thể áp dụng batch hoặc chiến lược riêng.

Do đó, EntityGraph biểu diễn **những gì cần được tải**, không phải **SQL bắt buộc phải có hình dạng nào**.

Nếu mục tiêu là kiểm soát rõ join type, điều kiện JOIN hoặc projection, JPQL JOIN FETCH, Criteria API hoặc DTO projection có thể phù hợp hơn.

## 5. Khai báo Named EntityGraph

Named graph được định nghĩa trên entity bằng @NamedEntityGraph. Ví dụ PurchaseOrder có customer và collection items; mỗi item có product.

~~~java
@Entity
@Table(name = "purchase_orders")
@NamedEntityGraph(
    name = "PurchaseOrder.detail",
    attributeNodes = {
        @NamedAttributeNode("customer"),
        @NamedAttributeNode(
            value = "items",
            subgraph = "item-with-product"
        )
    },
    subgraphs = {
        @NamedSubgraph(
            name = "item-with-product",
            attributeNodes = @NamedAttributeNode("product")
        )
    }
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(
        mappedBy = "purchaseOrder",
        fetch = FetchType.LAZY
    )
    private List<OrderItem> items = new ArrayList<>();

    @ManyToOne(fetch = FetchType.EAGER)
    @JoinColumn(name = "sales_region_id")
    private SalesRegion region;

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public List<OrderItem> getItems() {
        return items;
    }
}
~~~

Graph có tên PurchaseOrder.detail. Các node:

- customer: tải quan hệ Customer.
- items: tải collection OrderItem.
- item-with-product: subgraph cho từng OrderItem, yêu cầu tải product.

Subgraph dùng để mô tả thuộc tính sâu hơn của association. Nếu không khai báo subgraph cho items, graph chỉ mô tả việc tải collection items; nó không tự động yêu cầu mọi quan hệ của từng OrderItem được tải.

Tên trong attributeNodes và subgraph là tên property Java, không phải tên bảng hay cột database.

## 6. Mapping entity liên quan trong ví dụ

Các association được graph tham chiếu phải tồn tại trong entity model. Ví dụ OrderItem:

~~~java
@Entity
@Table(name = "order_items")
public class OrderItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "purchase_order_id")
    private PurchaseOrder purchaseOrder;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "product_id")
    private Product product;

    private int quantity;

    protected OrderItem() {
    }

    public Long getId() {
        return id;
    }

    public PurchaseOrder getPurchaseOrder() {
        return purchaseOrder;
    }

    public Product getProduct() {
        return product;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

Graph root là PurchaseOrder. items là collection của OrderItem, vì vậy subgraph item-with-product tham chiếu property product của OrderItem.

Graph không tạo quan hệ mới và cũng không thay đổi owning side, cascade hoặc database foreign key. Nó chỉ mô tả fetch plan cho những association đã được mapping.

## 7. Sử dụng Named EntityGraph trong Spring Data JPA

Spring Data JPA cung cấp annotation org.springframework.data.jpa.repository.EntityGraph.

Repository:

~~~java
package example.repository;

import example.domain.OrderStatus;
import example.domain.PurchaseOrder;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(
        value = "PurchaseOrder.detail",
        type = EntityGraph.EntityGraphType.FETCH
    )
    Optional<PurchaseOrder> findById(Long id);

    @EntityGraph(
        value = "PurchaseOrder.detail",
        type = EntityGraph.EntityGraphType.LOAD
    )
    List<PurchaseOrder> findByStatus(OrderStatus status);
}
~~~

Hai method dùng cùng named graph nhưng chọn semantics khác nhau:

- findById áp dụng fetch graph.
- findByStatus áp dụng load graph.

Method findById khai báo lại method kế thừa từ JpaRepository để gắn EntityGraph. Kiểu trả về và tham số vẫn tương thích với hợp đồng repository.

Trong Spring Data JPA, EntityGraph.EntityGraphType.FETCH là loại mặc định nếu không chỉ định type. Có thể ghi rõ type để người đọc hiểu ý định.

## 8. Dynamic EntityGraph bằng attributePaths

Không phải use case nào cũng cần một named graph đặt trên entity. Spring Data JPA cho phép khai báo graph động trực tiếp trên repository method bằng attributePaths.

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {
        "customer",
        "items.product"
    })
    List<PurchaseOrder> findByStatus(OrderStatus status);
}
~~~

Spring Data xây dựng dynamic EntityGraph từ các property path:

- customer là association trực tiếp của PurchaseOrder.
- items.product là đường dẫn từ PurchaseOrder đến collection items rồi đến Product của từng item.

Khi dùng attributePaths, Spring Data tạo graph động; không cần khai báo @NamedEntityGraph cho trường hợp đó. Type mặc định là FETCH, hoặc có thể chỉ định LOAD:

~~~java
@EntityGraph(
    type = EntityGraph.EntityGraphType.LOAD,
    attributePaths = {
        "customer",
        "items.product"
    }
)
List<PurchaseOrder> findByStatus(OrderStatus status);
~~~

Dùng named graph khi cấu trúc fetch plan được tái sử dụng ở nhiều nơi hoặc muốn đặt tên tập trung. Dùng attributePaths khi graph ngắn, chỉ phục vụ một method và không cần khai báo riêng trên entity.

## 9. Dùng EntityGraph với @Query

EntityGraph có thể áp dụng cho repository query được khai báo bằng @Query:

~~~java
@Query("""
    select o
    from PurchaseOrder o
    where o.status = :status
    """)
@EntityGraph(
    value = "PurchaseOrder.detail",
    type = EntityGraph.EntityGraphType.FETCH
)
List<PurchaseOrder> findDetailedByStatus(
    @Param("status") OrderStatus status
);
~~~

Query vẫn quyết định tập PurchaseOrder thông qua WHERE. EntityGraph bổ sung fetch plan cho entity được trả về.

EntityGraph không thay đổi điều kiện lọc, không tự thêm ORDER BY và không thay đổi kiểu kết quả thành DTO. Nếu query trả scalar hoặc projection thay vì entity root, không nên kỳ vọng graph sẽ hoạt động như một entity fetch plan thông thường.

## 10. Sử dụng EntityGraph bằng EntityManager

Có thể tạo graph động bằng JPA API mà không cần Spring Data annotation:

~~~java
EntityGraph<PurchaseOrder> graph =
    entityManager.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer", "items");

Subgraph<OrderItem> itemGraph =
    graph.addSubgraph("items");

itemGraph.addAttributeNodes("product");

PurchaseOrder order = entityManager.find(
    PurchaseOrder.class,
    orderId,
    Map.of("jakarta.persistence.fetchgraph", graph)
);
~~~

Map properties truyền fetch graph hint cho thao tác find.

Để dùng load graph, đổi key thành:

~~~java
Map.of("jakarta.persistence.loadgraph", graph)
~~~

Với Jakarta Persistence 3.x, tên hint dùng namespace jakarta.persistence. Các ứng dụng cũ dùng JPA với namespace javax.persistence có tên hint tương ứng javax.persistence.fetchgraph và javax.persistence.loadgraph; không trộn hai namespace trong cùng ứng dụng.

Có thể áp dụng hint cho TypedQuery:

~~~java
EntityGraph<PurchaseOrder> graph =
    entityManager.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

List<PurchaseOrder> orders = entityManager
    .createQuery(
        "select o from PurchaseOrder o where o.status = :status",
        PurchaseOrder.class
    )
    .setParameter("status", OrderStatus.PAID)
    .setHint("jakarta.persistence.fetchgraph", graph)
    .getResultList();
~~~

Cách lập trình trực tiếp phù hợp khi fetch plan được xây theo điều kiện runtime hoặc repository fragment cần điều khiển query bằng EntityManager.

## 11. Named graph, dynamic graph và programmatic graph

| Cách tạo | Nơi khai báo | Khi phù hợp |
|---|---|---|
| @NamedEntityGraph | Trên entity class | Graph ổn định, được dùng ở nhiều repository method |
| @EntityGraph(attributePaths = ...) | Trên repository method | Graph ngắn, chỉ phục vụ method cụ thể |
| EntityManager.createEntityGraph | Trong code | Graph phụ thuộc runtime hoặc query được xây động |

Cả ba cách đều biểu diễn EntityGraph của JPA. Khác nhau ở nơi định nghĩa và thời điểm tạo graph.

Không nên tạo quá nhiều named graph gần giống nhau. Nếu chỉ khác một association nhỏ, hãy cân nhắc graph cơ bản và graph chi tiết có tên rõ nghĩa. Nếu graph chỉ dùng một lần, attributePaths có thể dễ bảo trì hơn.

## 12. Subgraph và nhiều cấp association

Subgraph giúp mô tả quan hệ lồng nhau. Ví dụ:

~~~text
PurchaseOrder
  +-- customer
        +-- address
  +-- items
        +-- product
              +-- manufacturer
~~~

Named graph có thể mô tả các nhánh:

~~~java
@NamedEntityGraph(
    name = "PurchaseOrder.fullDetail",
    attributeNodes = {
        @NamedAttributeNode(
            value = "customer",
            subgraph = "customer-with-address"
        ),
        @NamedAttributeNode(
            value = "items",
            subgraph = "items-with-product"
        )
    },
    subgraphs = {
        @NamedSubgraph(
            name = "customer-with-address",
            attributeNodes = @NamedAttributeNode("address")
        ),
        @NamedSubgraph(
            name = "items-with-product",
            attributeNodes = @NamedAttributeNode(
                value = "product",
                subgraph = "product-with-manufacturer"
            )
        ),
        @NamedSubgraph(
            name = "product-with-manufacturer",
            attributeNodes = @NamedAttributeNode("manufacturer")
        )
    }
)
~~~

Mỗi subgraph được áp dụng cho kiểu entity đích của association tương ứng. Vì vậy, customer-with-address mô tả thuộc tính của Customer; items-with-product mô tả thuộc tính của OrderItem; product-with-manufacturer mô tả thuộc tính của Product.

Graph sâu giúp tránh truy cập lazy ngoài ý muốn, nhưng cũng có thể tải rất nhiều dữ liệu. Chỉ thêm những nhánh mà use case thực sự cần.

## 13. Fetch graph và load graph qua ví dụ cụ thể

Giả sử mapping PurchaseOrder như sau:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@ManyToOne(fetch = FetchType.EAGER)
private SalesRegion region;

@OneToMany(mappedBy = "purchaseOrder", fetch = FetchType.LAZY)
private List<OrderItem> items = new ArrayList<>();
~~~

Named graph chỉ chứa customer:

~~~java
@NamedEntityGraph(
    name = "PurchaseOrder.withCustomer",
    attributeNodes = @NamedAttributeNode("customer")
)
~~~

Khi dùng FETCH:

- customer phải được tải theo graph.
- region không được liệt kê nên graph quy định LAZY.
- items không được liệt kê nên graph quy định LAZY.

Khi dùng LOAD:

- customer phải được tải theo graph.
- region không được liệt kê nên mapping EAGER vẫn áp dụng.
- items không được liệt kê nên mapping LAZY vẫn áp dụng.

Nếu mapping thay đổi region từ EAGER sang LAZY, hành vi load graph đối với region cũng đổi theo mapping. Đó là khác biệt quan trọng: load graph giữ default; fetch graph xác định lại trạng thái cho các thuộc tính ngoài graph theo semantics LAZY.

Provider vẫn được phép tải thêm trạng thái ngoài graph. Không dùng bảng này để suy ra chính xác số cột hay số SQL statement sẽ được thực thi.

## 14. EntityGraph khác JOIN FETCH như thế nào?

Ví dụ JOIN FETCH trong JPQL:

~~~jpql
select o
from PurchaseOrder o
left join fetch o.customer
left join fetch o.items i
left join fetch i.product
where o.status = :status
~~~

Ví dụ EntityGraph:

~~~java
@EntityGraph(attributePaths = {
    "customer",
    "items.product"
})
List<PurchaseOrder> findByStatus(OrderStatus status);
~~~

Khác biệt:

| Tiêu chí | EntityGraph | JOIN FETCH |
|---|---|---|
| Mục tiêu | Khai báo thuộc tính cần tải | Khai báo association fetch trong query |
| SQL shape | Provider quyết định | Query chỉ rõ JOIN FETCH |
| Có thể gắn vào derived query | Có, qua @EntityGraph | Không trực tiếp trong method name |
| Có thể dùng với @Query | Có | Có |
| Điều kiện JOIN riêng | Graph không mô tả ON/join type như query | Query có thể kiểm soát cấu trúc JOIN |
| Tái sử dụng | Named graph có thể dùng nhiều method | Query thường chứa fetch join riêng |
| Kết quả | Entity với fetch plan đã yêu cầu | Entity với association được fetch |

EntityGraph không phải cú pháp thay thế hoàn toàn JOIN FETCH. Nếu cần kiểm soát INNER/LEFT JOIN hoặc điều kiện join cụ thể, JOIN FETCH hoặc Criteria API rõ ràng hơn.

Ngược lại, EntityGraph phù hợp khi muốn giữ query method gọn và thay đổi fetch plan theo use case.

## 15. EntityGraph không phải DTO projection

EntityGraph vẫn trả entity root và điều chỉnh trạng thái được tải. Nó không biến entity thành DTO và không giới hạn kết quả chỉ còn những cột được liệt kê trong graph.

Ví dụ graph tải PurchaseOrder, customer và items.product vẫn trả về PurchaseOrder entity. Các field basic khác có thể được tải theo mapping/provider.

Nếu API chỉ cần id, orderCode, customerName và total, DTO projection có thể hiệu quả hơn:

~~~java
public record OrderSummary(
    Long id,
    String orderCode,
    String customerName,
    BigDecimal total
) {
}
~~~

Repository có thể dùng constructor projection:

~~~java
@Query("""
    select new example.dto.OrderSummary(
        o.id,
        o.orderCode,
        c.name,
        o.total
    )
    from PurchaseOrder o
    join o.customer c
    where o.status = :status
    """)
List<OrderSummary> findSummariesByStatus(
    @Param("status") OrderStatus status
);
~~~

Dùng EntityGraph khi cần entity và quan hệ của nó. Dùng DTO projection khi chỉ cần một tập trường phục vụ đọc, đặc biệt với báo cáo hoặc API danh sách.

## 16. EntityGraph có loại bỏ N+1 không?

EntityGraph có thể giảm N+1 bằng cách yêu cầu provider tải các association cần thiết cùng fetch plan của truy vấn.

Ví dụ nếu tải 50 PurchaseOrder rồi truy cập customer của từng đơn, mapping LAZY có thể dẫn đến nhiều query bổ sung nếu không có fetch plan phù hợp. EntityGraph yêu cầu customer được tải trong lần truy vấn đó.

Tuy nhiên, không thể kết luận EntityGraph luôn tạo đúng một SQL statement. Provider có thể dùng JOIN hoặc secondary SELECT, tùy mapping, database và chiến lược thực thi.

Cách xác minh:

1. Bật SQL logging hoặc datasource query counter.
2. Chạy truy vấn với và không có graph.
3. Kiểm tra số SQL statement.
4. Kiểm tra association nào được tải.
5. Đo tổng thời gian và số hàng được database trả về.
6. Kiểm tra dữ liệu lớn và các collection nhiều phần tử.

Mục tiêu là giảm truy vấn thừa mà không tải quá nhiều dữ liệu. Số query ít hơn chưa chắc luôn nhanh hơn nếu JOIN tạo hàng trung gian rất lớn.

## 17. EntityGraph và collection lớn

Nếu graph tải collection items, toàn bộ collection được yêu cầu tải theo graph. EntityGraph không phải bộ lọc để chỉ tải một số item theo điều kiện.

Ví dụ graph:

~~~java
@EntityGraph(attributePaths = "items")
Optional<PurchaseOrder> findById(Long id);
~~~

yêu cầu tải collection items của đơn hàng. Nếu một đơn có hàng chục nghìn item, việc tải toàn bộ có thể tốn bộ nhớ và thời gian.

Nếu chỉ cần một phần tử hoặc một trang item, hãy truy vấn OrderItem riêng bằng repository method có Pageable, hoặc dùng projection. Không dùng EntityGraph để thay thế pagination của collection.

## 18. Nhiều collection và nguy cơ nhân số hàng

Graph tải nhiều collection có thể khiến provider phải xử lý số hàng kết hợp lớn nếu chiến lược thực thi dùng JOIN.

Ví dụ:

~~~text
PurchaseOrder
  +-- items (10 phần tử)
  +-- payments (5 phần tử)
  +-- notes (4 phần tử)
~~~

Nếu các collection được join đồng thời, một root có thể tạo nhiều tổ hợp hàng trung gian. 10 × 5 × 4 = 200 tổ hợp cho một đơn hàng.

Hệ quả có thể gồm:

- Tăng dữ liệu truyền từ database.
- Tăng bộ nhớ khi hydrate entity.
- Kết quả root có thể cần loại trùng.
- Hibernate có thể gặp giới hạn với nhiều bag collection trong cùng một fetch plan.
- Pagination trên collection fetch có thể không thực hiện ở database như mong muốn.

Giải pháp:

- Chỉ tải collection cần thiết cho use case.
- Dùng DTO projection nếu chỉ cần dữ liệu đọc.
- Tải một collection bằng graph và collection khác bằng query riêng.
- Cân nhắc batch fetching hoặc subselect fetching theo provider.
- Kiểm tra SQL, số hàng và execution plan.

## 19. EntityGraph và phân trang

EntityGraph có thể gắn với repository method nhận Pageable:

~~~java
@EntityGraph(attributePaths = "customer")
Page<PurchaseOrder> findByStatus(
    OrderStatus status,
    Pageable pageable
);
~~~

Với association to-one như customer, cách này thường dễ kiểm soát hơn so với fetch collection. Tuy vậy vẫn cần kiểm tra SQL và count query được tạo.

Cần cẩn thận khi graph chứa collection như items. Nếu provider thực hiện bằng collection join, phân trang có thể áp dụng trên hàng JOIN thay vì root entity. Một số provider có thể cảnh báo hoặc phân trang trong bộ nhớ; hành vi phụ thuộc provider và phiên bản.

Một cách thiết kế chắc chắn hơn cho trang có collection:

1. Truy vấn một trang ID PurchaseOrder theo filter và Sort.
2. Dùng EntityGraph tải chi tiết cho các ID của trang đó.
3. Khôi phục thứ tự ban đầu từ trang ID vì IN (:ids) không bảo đảm giữ thứ tự.
4. Trả Page với totalElements từ trang ID đầu tiên.

Ví dụ repository:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select o.id
        from PurchaseOrder o
        where o.status = :status
        """)
    Page<Long> findIdsByStatus(
        @Param("status") OrderStatus status,
        Pageable pageable
    );

    @EntityGraph(attributePaths = {
        "customer",
        "items.product"
    })
    @Query("""
        select distinct o
        from PurchaseOrder o
        where o.id in :ids
        """)
    List<PurchaseOrder> findDetailsByIdIn(
        @Param("ids") Collection<Long> ids
    );
}
~~~

Service có thể tạo PageImpl từ ID page và danh sách entity đã sắp lại theo thứ tự ID. Đây là chiến lược hai bước; cần xử lý trang rỗng và bản ghi bị xóa giữa hai query nếu dữ liệu thay đổi đồng thời.

## 20. Kiểm tra thuộc tính đã được tải

JPA cung cấp PersistenceUnitUtil để kiểm tra trạng thái loaded của entity hoặc thuộc tính:

~~~java
PersistenceUnitUtil util =
    entityManagerFactory.getPersistenceUnitUtil();

PurchaseOrder order = repository.findById(orderId)
    .orElseThrow();

boolean customerLoaded =
    util.isLoaded(order, "customer");

boolean itemsLoaded =
    util.isLoaded(order, "items");
~~~

Với nested association:

~~~java
if (util.isLoaded(order, "items")) {
    for (OrderItem item : order.getItems()) {
        boolean productLoaded =
            util.isLoaded(item, "product");
    }
}
~~~

isLoaded giúp kiểm thử fetch plan mà không cần gọi getter rồi vô tình kích hoạt lazy loading trước khi kiểm tra.

Nên thực hiện kiểm tra trong transaction test phù hợp và dùng entity manager/persistence context đã được kiểm soát. Nếu kiểm tra sau khi entity đã bị truy cập trước đó, trạng thái loaded có thể phản ánh lần truy cập trước chứ không chỉ EntityGraph.

## 21. Kiểm thử EntityGraph với Spring Data JPA

Ví dụ integration test:

~~~java
@DataJpaTest
class PurchaseOrderEntityGraphTest {

    @Autowired
    private PurchaseOrderRepository repository;

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Test
    void fetchGraphLoadsRequestedAssociations() {
        Long orderId = 100L;

        PurchaseOrder order = repository.findById(orderId)
            .orElseThrow();

        PersistenceUnitUtil util =
            entityManagerFactory.getPersistenceUnitUtil();

        assertTrue(util.isLoaded(order, "customer"));
        assertTrue(util.isLoaded(order, "items"));

        for (OrderItem item : order.getItems()) {
            assertTrue(util.isLoaded(item, "product"));
        }
    }
}
~~~

Test giả định dữ liệu có order ID 100, các association được mapping đúng và test chạy trong persistence context do @DataJpaTest quản lý. Trong dự án thực tế, nên tạo fixture bằng repository hoặc TestEntityManager thay vì phụ thuộc ID cố định.

Ngoài loaded state, nên kiểm tra SQL count nếu mục tiêu là giảm N+1. Hai kiểm tra này khác nhau:

- isLoaded xác nhận trạng thái entity.
- Query counter xác nhận số câu SQL thực tế.

## 22. Lỗi thường gặp và cách khắc phục

**1. Dùng fetch graph nhưng association ngoài graph vẫn được tải**

Provider được phép tải thêm trạng thái ngoài graph. Fetch graph quy định semantics LAZY cho thuộc tính không được liệt kê, không bảo đảm SQL chỉ chứa đúng graph.

**2. Nghĩ load graph làm mọi thuộc tính eager**

Load graph chỉ yêu cầu thuộc tính trong graph eager. Thuộc tính ngoài graph giữ mapping default; mapping LAZY vẫn là LAZY.

**3. Đảo ngược FETCH và LOAD**

FETCH làm thuộc tính ngoài graph có semantics LAZY. LOAD giữ fetch behavior mặc định. Hãy nhớ khác biệt nằm ở thuộc tính không được liệt kê.

**4. Graph không tải nested product**

Chỉ thêm items chưa đủ để yêu cầu product của từng item. Thêm subgraph hoặc attribute path items.product.

**5. @EntityGraph không được áp dụng**

Kiểm tra method repository, tên named graph, root entity, property path, import annotation Spring Data và query method có trả entity phù hợp không.

**6. Named graph báo không tìm thấy**

Kiểm tra tên trong @NamedEntityGraph khớp chính xác với value của @EntityGraph. Tên graph phân biệt theo chuỗi.

**7. Vẫn có nhiều SQL statement**

EntityGraph không cam kết một SQL. Xem provider đang dùng JOIN hay secondary SELECT, mapping và batch fetching.

**8. Tải collection làm query rất lớn**

Giảm số collection trong graph, dùng DTO projection hoặc truy vấn collection riêng theo trang.

**9. Page trả dữ liệu không ổn định khi graph chứa collection**

Kiểm tra collection fetch pagination. Cân nhắc phân trang ID trước rồi tải graph cho trang đó.

**10. Dùng EntityGraph để lọc association**

Graph chỉ mô tả fetch plan, không lọc phần tử trong collection. Dùng query riêng hoặc projection để lọc.

**11. Mong EntityGraph trả DTO**

EntityGraph vẫn trả entity. Dùng projection/constructor expression nếu chỉ cần dữ liệu đọc.

**12. Dùng nhầm namespace hint**

Ứng dụng Jakarta Persistence 3.x dùng jakarta.persistence.fetchgraph và jakarta.persistence.loadgraph; code JPA cũ dùng namespace javax tương ứng.

## 23. Quy trình chọn fetch graph hoặc load graph

Khi thiết kế repository method:

1. Xác định root entity và association use case cần truy cập.
2. Kiểm tra mapping FetchType mặc định.
3. Liệt kê các thuộc tính cần tải trong lần truy vấn.
4. Nếu muốn thuộc tính ngoài graph có semantics LAZY, chọn FETCH.
5. Nếu muốn thuộc tính ngoài graph giữ mapping default, chọn LOAD.
6. Chọn named graph nếu nhiều method dùng lại; chọn attributePaths nếu graph chỉ phục vụ một method.
7. Dùng subgraph cho association lồng nhau.
8. Dùng EntityGraph khi cần entity; dùng DTO projection khi chỉ cần một tập field.
9. So sánh với JOIN FETCH nếu cần kiểm soát join type hoặc query structure.
10. Kiểm tra collection lớn và phân trang.
11. Bật SQL logging/query counter và kiểm tra loaded state.
12. Đo với dữ liệu gần production trước khi kết luận graph tối ưu hơn.

## 24. Checklist tự đánh giá

- [ ] Tôi giải thích được EntityGraph và fetch plan.
- [ ] Tôi phân biệt được FetchType với EntityGraph.
- [ ] Tôi biết FETCH graph yêu cầu thuộc tính ngoài graph có semantics LAZY.
- [ ] Tôi biết LOAD graph giữ mapping default cho thuộc tính ngoài graph.
- [ ] Tôi hiểu cả hai loại graph đều yêu cầu thuộc tính được liệt kê tải eager.
- [ ] Tôi biết provider có thể tải thêm trạng thái ngoài graph.
- [ ] Tôi biết khai báo @NamedEntityGraph và @NamedAttributeNode.
- [ ] Tôi biết dùng @NamedSubgraph cho association lồng nhau.
- [ ] Tôi biết dùng @EntityGraph(attributePaths = ...).
- [ ] Tôi biết EntityGraph.EntityGraphType.FETCH và EntityGraph.EntityGraphType.LOAD.
- [ ] Tôi biết truyền jakarta.persistence.fetchgraph/loadgraph qua EntityManager.
- [ ] Tôi phân biệt EntityGraph với JOIN FETCH.
- [ ] Tôi hiểu EntityGraph không phải DTO projection.
- [ ] Tôi biết graph có thể giảm N+1 nhưng không cam kết một SQL statement.
- [ ] Tôi hiểu rủi ro khi graph tải nhiều collection.
- [ ] Tôi biết thận trọng với collection fetch và pagination.
- [ ] Tôi biết kiểm tra loaded state bằng PersistenceUnitUtil.
- [ ] Tôi kiểm thử SQL count và hiệu năng trên database mục tiêu.

## 25. Câu hỏi ôn tập

**1. Fetch graph khác load graph ở điểm nào?**

Cả hai đều yêu cầu thuộc tính được liệt kê trong graph tải eager. Fetch graph xem thuộc tính ngoài graph là LAZY; load graph giữ mapping default cho thuộc tính ngoài graph.

**2. Nếu customer là LAZY nhưng nằm trong fetch graph thì sao?**

Customer được yêu cầu tải eager cho truy vấn áp dụng graph đó. Mapping LAZY mặc định của entity không bị thay đổi vĩnh viễn.

**3. Nếu region là EAGER nhưng không nằm trong fetch graph thì sao?**

Theo semantics fetch graph, region có ngữ nghĩa LAZY cho lần fetch plan đó. Provider vẫn được phép tải thêm trạng thái ngoài graph.

**4. Nếu region là EAGER nhưng không nằm trong load graph thì sao?**

Load graph giữ mapping default nên region vẫn được yêu cầu tải EAGER.

**5. @EntityGraph(attributePaths = {"items.product"}) có nghĩa gì?**

Tải collection items và yêu cầu tải association product của từng OrderItem trong graph.

**6. EntityGraph có bảo đảm tạo JOIN không?**

Không. Graph mô tả thuộc tính cần tải; provider quyết định dùng JOIN hay secondary SELECT.

**7. EntityGraph khác JOIN FETCH thế nào?**

EntityGraph tách fetch plan khỏi query structure. JOIN FETCH ghi rõ association cần fetch ngay trong JPQL và cho phép kiểm soát cấu trúc join rõ hơn.

**8. EntityGraph có thay thế DTO projection không?**

Không. EntityGraph vẫn trả entity. DTO projection chọn một tập trường cụ thể cho kết quả đọc.

**9. Vì sao graph tải nhiều collection có thể chậm?**

JOIN nhiều collection có thể nhân số hàng trung gian, tăng dữ liệu truyền và chi phí hydrate entity. Nên tải đúng collection cần thiết hoặc chia query.

**10. Làm sao xác minh EntityGraph hoạt động?**

Dùng PersistenceUnitUtil.isLoaded để kiểm tra thuộc tính, đồng thời bật SQL logging/query counter để xem số câu SQL và cách provider thực hiện fetch.

Chọn đúng fetch graph hoặc load graph giúp repository thể hiện rõ dữ liệu cần tải cho từng use case. Khi hiểu semantics của thuộc tính nằm ngoài graph, cách dùng subgraph và giới hạn của collection pagination, bạn có thể kiểm soát lazy loading mà vẫn giữ query và mapping dễ bảo trì hơn.

## Tài liệu tham khảo

- [Spring Data JPA — EntityGraph support](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence API — EntityGraph](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/entitygraph)
- [Hibernate ORM User Guide — Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html)
