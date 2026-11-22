# LazyInitializationException và ranh giới context đã đóng trong Hibernate ORM

Hibernate ORM thường trì hoãn việc tải association cho đến khi ứng dụng thật sự cần dùng. Cơ chế **lazy loading** giúp một truy vấn chỉ lấy entity và những dữ liệu cần thiết ở thời điểm đó, thay vì luôn tải toàn bộ object graph. Đổi lại, một proxy hoặc collection lazy chỉ có thể được khởi tạo khi Hibernate còn có **Session/persistence context** phù hợp để thực hiện truy vấn.

Nếu ứng dụng giữ một entity sau khi context đã đóng rồi truy cập một association chưa được tải, Hibernate có thể ném lỗi:

```text
org.hibernate.LazyInitializationException:
    could not initialize proxy - no Session
```

hoặc:

```text
org.hibernate.LazyInitializationException:
    failed to lazily initialize a collection of role:
    com.example.Order.lines: could not initialize proxy - no Session
```

Đây là lỗi đặc trưng của Hibernate, thường báo hiệu code đã truy cập dữ liệu lazy **ngoài phạm vi persistence context có thể phục vụ việc tải dữ liệu**. Entity Java vẫn còn trong bộ nhớ; các trường đã được tải vẫn có thể đọc. Vấn đề nằm ở association hoặc thuộc tính lazy chưa khởi tạo, cần SQL bổ sung nhưng Session đã đóng hoặc entity không còn gắn với Session phù hợp.

Cách xử lý bền vững là xác định rõ **use case cần dữ liệu nào**, tải dữ liệu đó trong transaction/persistence context thích hợp, rồi chuyển thành DTO hoặc trả về một kết quả đã được chuẩn bị đầy đủ. Bài học giải thích proxy và lazy collection, vòng đời Session, nguyên nhân lỗi, cách thiết kế fetch plan, vai trò của transaction và Open Session in View (OSIV), cùng các cách xử lý không nên lạm dụng.

## 1. Lazy loading và lý do Hibernate cần một Session

Giả sử có entity đơn hàng:

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

Khi thực hiện:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
```

Hibernate có thể tải dữ liệu của `purchase_orders` mà chưa tải `customer` hoặc các hàng `order_lines`. Nó giữ một proxy cho association to-one hoặc một persistent collection wrapper cho association collection. Khi code lần đầu truy cập dữ liệu cần tải, Hibernate dùng Session để truy vấn database.

Ví dụ:

```java
String customerName = order.getCustomer().getName();

for (OrderLine line : order.getLines()) {
    System.out.println(line.getQuantity());
}
```

Nếu Session còn hoạt động và association chưa được tải, Hibernate có thể phát các SELECT bổ sung. Nếu Session đã đóng, Hibernate không còn context để thực hiện các SELECT ấy và có thể ném `LazyInitializationException`.

### 1.1. Lazy là trì hoãn tải, không phải không tải

`FetchType.LAZY` có nghĩa provider được phép trì hoãn việc nạp association/thuộc tính theo semantics của mapping. Khi code truy cập association, provider có thể khởi tạo nó.

Lazy loading không có nghĩa:

- Association không bao giờ được tải.
- Entity chỉ chứa ID và không thể truy cập thuộc tính khác.
- Hibernate tự tìm một Session bất kỳ để tải dữ liệu sau khi Session ban đầu đóng.
- Mọi truy cập getter đều chạy SQL.
- Một association lazy luôn được tải bằng đúng một SELECT.

Nếu entity hoặc association đã được tải trong persistence context, truy cập nó thường không cần truy vấn mới. Cache và identity map cũng có thể làm thay đổi số SQL thực tế.

### 1.2. Vì sao phải có Session?

Hibernate cần Session để:

- Biết entity thuộc persistence context nào.
- Theo dõi identity và trạng thái managed.
- Thực thi SQL qua connection phù hợp.
- Khởi tạo proxy hoặc collection wrapper.
- Áp dụng mapping, filter, tenant context và các cơ chế liên quan.
- Tích hợp việc đọc dữ liệu với transaction và cache.

Một proxy không phải là một kết nối database độc lập. Nó là một đối tượng đại diện có khả năng yêu cầu Session tải dữ liệu thật khi cần.

## 2. Proxy và persistent collection hoạt động ra sao?

Hibernate có thể dùng hai hình thức trì hoãn phổ biến.

### 2.1. Proxy cho association to-one

Ví dụ `PurchaseOrder.customer`:

```java
Customer customer = order.getCustomer();
```

`customer` có thể là một proxy mang định danh của Customer. Khi ứng dụng gọi một thuộc tính cần state thật, proxy yêu cầu Session tải entity:

```java
String name = customer.getName();
```

Nếu Session vẫn mở, Hibernate có thể chạy truy vấn tương đương:

```sql
SELECT id, name, email
FROM customers
WHERE id = ?;
```

Nếu Session đã đóng và proxy chưa initialized, việc gọi `getName()` có thể gây `LazyInitializationException`.

Một số thao tác chỉ cần identifier, chẳng hạn đọc ID từ proxy, có thể không cần khởi tạo proxy trong những mapping/access strategy phổ biến. Tuy nhiên, đừng dùng điều này làm hợp đồng chung cho mọi getter hoặc mọi kiểu mapping; hãy thiết kế code dựa trên dữ liệu thực sự đã được tải.

### 2.2. Persistent collection cho association to-many

Với `order.getLines()`, Hibernate thường dùng một wrapper như persistent bag/list/set để theo dõi trạng thái collection. Wrapper có thể biết owner và role của collection, đồng thời trì hoãn việc truy vấn các phần tử.

Ví dụ:

```java
List<OrderLine> lines = order.getLines();
```

Việc lấy tham chiếu collection có thể chưa tải toàn bộ phần tử. Nhưng các thao tác như:

```java
int count = order.getLines().size();

for (OrderLine line : order.getLines()) {
    // ...
}
```

có thể yêu cầu khởi tạo collection. Nếu Session đã đóng, việc cần tải dữ liệu sẽ thất bại.

Tùy loại collection và thao tác, Hibernate có thể tối ưu một số phép kiểm tra bằng SQL riêng mà không nhất thiết tải toàn bộ phần tử. Tuy nhiên, khi ứng dụng cần duyệt các entity con, dữ liệu phải được lấy bằng một context còn khả năng thực hiện truy vấn.

### 2.3. Lazy basic attribute và bytecode enhancement

Ngoài association, Hibernate còn có thể trì hoãn tải một số thuộc tính basic, ví dụ trường nội dung lớn:

```java
@Basic(fetch = FetchType.LAZY)
@Column(columnDefinition = "text")
private String longDescription;
```

Khả năng lazy loading của basic attribute thường cần bytecode enhancement hoặc cấu hình phù hợp; annotation đơn lẻ không phải lúc nào cũng tạo được hành vi trì hoãn như mong muốn. Khi thuộc tính lazy chưa được tải, truy cập sau khi context đóng cũng có thể dẫn đến lỗi lazy initialization.

Đừng nhầm lazy association với lazy basic field. Cơ chế proxy/field interception và điều kiện enhancement có thể khác nhau.

## 3. Persistence context, Session và vòng đời entity

Trong JPA, `EntityManager` quản lý một **persistence context**. Với Hibernate, persistence context thường được thực hiện bởi một `Session`.

Entity có thể trải qua các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| **Transient** | Object mới, chưa thuộc persistence context |
| **Managed** | Entity đang được context quản lý |
| **Detached** | Entity từng được quản lý nhưng không còn gắn với context hiện tại |
| **Removed** | Entity managed đã được yêu cầu xóa |

Một entity có thể vẫn tồn tại trong heap Java sau khi chuyển sang detached. Nhưng Hibernate không còn theo dõi thay đổi và không thể tự động khởi tạo lazy state qua Session cũ đã đóng.

### 3.1. Khi EntityManager đóng

Ví dụ resource-local:

```java
EntityManager em = emf.createEntityManager();

PurchaseOrder order;
try {
    order = em.find(PurchaseOrder.class, orderId);
} finally {
    em.close();
}

// order đã detached khỏi persistence context đã đóng.
String customerName = order.getCustomer().getName();
```

Sau `em.close()`, persistence context không còn hoạt động. Các thuộc tính đã được nạp vẫn nằm trong object. Association lazy chưa được khởi tạo không thể tiếp tục truy vấn qua EntityManager đã đóng.

Nếu `customer` đã được fetch trước khi đóng, đọc `customer.getName()` có thể hoạt động. Nếu `lines` chưa initialized, duyệt collection có thể ném lỗi.

### 3.2. Đóng Session và kết thúc transaction là hai sự kiện khác nhau

Điểm này rất quan trọng:

- **Transaction kết thúc** bằng commit hoặc rollback.
- **Session/EntityManager đóng** làm persistence context kết thúc và entity trở thành detached đối với context đó.

Hai sự kiện thường xảy ra gần nhau trong mô hình resource-local hoặc transaction-scoped EntityManager, nhưng không phải khái niệm đồng nhất.

Một Session có thể vẫn mở sau khi transaction kết thúc. Trong trường hợp đó, một số lazy loading vẫn có thể thực hiện nếu Session còn hoạt động, tùy trạng thái và cấu hình. Nhưng việc truy vấn ngoài transaction nghiệp vụ có thể tạo SQL ở thời điểm không mong muốn, dùng auto-commit hoặc không nằm trong cùng snapshot nhất quán.

Vì vậy, đừng định nghĩa lỗi này đơn giản là “transaction đã commit”. Điều kiện trực tiếp thường là **association chưa initialized cần truy cập khi không còn Session phù hợp**.

### 3.3. Clear, detach và close đều có thể làm entity không còn managed

Các thao tác:

```java
em.detach(order);
em.clear();
em.close();
```

có tác động khác nhau:

- `detach(order)` tách entity cụ thể khỏi persistence context; cascade DETACH có thể tách thêm entity liên quan.
- `clear()` tách tất cả entity managed khỏi context.
- `close()` đóng EntityManager và kết thúc khả năng sử dụng persistence context đó.

Nếu một association chưa initialized, các thao tác này có thể khiến việc truy cập sau đó không thể lazy-load qua context cũ.

### 3.4. Entity đã detached không bị xóa khỏi bộ nhớ

`order` vẫn là object Java. Có thể đọc những trường đã tải và dùng dữ liệu đó để tạo DTO. Chỉ những thao tác cần Hibernate tải thêm dữ liệu mới gặp giới hạn.

Detached không đồng nghĩa object hỏng; nó chỉ không còn là entity managed trong context cũ.

## 4. Tái hiện LazyInitializationException

Một ví dụ điển hình:

```java
public PurchaseOrder loadOrder(UUID id) {
    EntityManager em = emf.createEntityManager();

    try {
        return em.find(PurchaseOrder.class, id);
    } finally {
        em.close();
    }
}
```

Code gọi:

```java
PurchaseOrder order = loadOrder(orderId);

// EntityManager bên trong loadOrder đã đóng.
System.out.println(order.getLines().size());
```

Nếu `lines` chưa được initialize, Hibernate có thể ném:

```text
org.hibernate.LazyInitializationException:
    failed to lazily initialize a collection of role:
    PurchaseOrder.lines: could not initialize proxy - no Session
```

Lỗi không xuất phát từ `size()` như một phép tính Java đơn thuần. `size()` đang yêu cầu dữ liệu collection mà wrapper chưa có, nên Hibernate cần Session để thực hiện.

### 4.1. Cùng một entity, association đã initialized thì có thể đọc

```java
EntityManager em = emf.createEntityManager();

PurchaseOrder order;
try {
    order = em.find(PurchaseOrder.class, orderId);

    // Khởi tạo collection khi Session còn mở.
    order.getLines().size();
} finally {
    em.close();
}

// Collection đã được tải; có thể duyệt state đã có trong bộ nhớ.
for (OrderLine line : order.getLines()) {
    System.out.println(line.getQuantity());
}
```

Đây là ví dụ về khác biệt giữa association initialized và chưa initialized. Tuy nhiên, việc gọi `size()` để tải collection trước khi đóng context có thể tạo một truy vấn riêng và không phải cách tối ưu cho mọi use case. Tốt hơn thường là thiết kế query/fetch plan rõ ngay từ đầu.

### 4.2. Lỗi có thể nằm trong getter, mapper hoặc serializer

Code trực tiếp có thể không gọi `getLines()`, nhưng một thư viện khác có thể gọi:

- JSON serializer.
- Bean mapper.
- Logging framework khi gọi `toString()`.
- Debugger/watch expression.
- Template engine.
- GraphQL resolver.
- Object mapper dùng reflection/getter.
- Equals/hashCode do Lombok sinh.

Stack trace có thể chỉ ra mapper hoặc serializer, dù nguyên nhân gốc vẫn là một thuộc tính lazy được truy cập sau khi context đóng.

## 5. Ranh giới service transaction quyết định nơi tải dữ liệu

Một pattern thường gặp trong Spring:

```java
@Service
public class OrderQueryService {

    private final PurchaseOrderRepository repository;

    public OrderQueryService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public PurchaseOrder getOrder(UUID id) {
        return repository.findById(id).orElseThrow();
    }
}
```

Controller:

```java
@RestController
public class OrderController {

    private final OrderQueryService service;

    @GetMapping("/orders/{id}")
    public OrderResponse get(@PathVariable UUID id) {
        PurchaseOrder order = service.getOrder(id);

        return new OrderResponse(
            order.getId(),
            order.getCustomer().getName()
        );
    }
}
```

Với transaction-scoped persistence context thông thường, khi `service.getOrder` trả về, transaction kết thúc và context có thể được unbind/đóng. Controller truy cập `order.customer.name` sau đó có thể gặp `LazyInitializationException`.

### 5.1. Tải dữ liệu và chuyển DTO bên trong transaction

Một cách rõ ràng:

```java
@Service
public class OrderQueryService {

    private final EntityManager em;

    public OrderQueryService(EntityManager em) {
        this.em = em;
    }

    @Transactional(readOnly = true)
    public OrderResponse getOrder(UUID id) {
        PurchaseOrder order = em.createQuery("""
            select o
            from PurchaseOrder o
            left join fetch o.customer
            where o.id = :id
            """, PurchaseOrder.class)
            .setParameter("id", id)
            .getSingleResult();

        List<OrderLineResponse> lines = order.getLines().stream()
            .map(line -> new OrderLineResponse(
                line.getProduct().getName(),
                line.getQuantity()
            ))
            .toList();

        return new OrderResponse(
            order.getId(),
            order.getCustomer().getName(),
            lines
        );
    }
}
```

Ví dụ này giả định `customer` được fetch cùng query; nếu cần `lines` và `lines.product`, phải fetch chúng bằng query/fetch plan thích hợp. DTO được tạo trong transaction nên controller chỉ serialize dữ liệu đã chuẩn bị, không cần truy cập entity lazy.

### 5.2. Đừng trả entity rồi mong controller tải tiếp

Một service query nên có hợp đồng rõ:

- Trả **DTO/read model** đã đủ dữ liệu cho caller.
- Hoặc trả entity chỉ khi caller chắc chắn hoạt động trong cùng persistence context/transaction theo một thiết kế rõ ràng.

Trả entity ra khỏi transaction rồi để controller tùy ý gọi mọi getter làm ranh giới tải dữ liệu mơ hồ. Điều này dễ gây lazy exception, N+1 và lộ thuộc tính không nên trả ra API.

## 6. Giải pháp 1: JOIN FETCH cho association cần thiết

JPQL/HQL `JOIN FETCH` cho phép yêu cầu tải association cùng query.

Ví dụ tải order và customer:

```java
PurchaseOrder order = em.createQuery("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    where o.id = :id
    """, PurchaseOrder.class)
    .setParameter("id", orderId)
    .getSingleResult();
```

Nếu trang chi tiết cần cả lines và product:

```java
PurchaseOrder order = em.createQuery("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.customer
    left join fetch o.lines line
    left join fetch line.product
    where o.id = :id
    """, PurchaseOrder.class)
    .setParameter("id", orderId)
    .getSingleResult();
```

Khi query chạy trong transaction, association được yêu cầu fetch sẽ có sẵn để service chuyển DTO trước khi context kết thúc.

### 6.1. JOIN FETCH là lựa chọn theo query

Ưu điểm:

- Fetch plan nằm ngay trong JPQL/HQL.
- Dễ nhìn thấy association cần tải.
- Có thể giảm các SELECT phát sinh sau đó.
- Hữu ích cho query đặc thù của một use case.

Đánh đổi:

- Query có thể phức tạp khi nhiều association.
- Join collection làm nhân số hàng SQL.
- Không phải lúc nào cũng phù hợp với pagination.
- Fetch nhiều bag/collection có thể gây lỗi hoặc Cartesian product.
- Một query fetch join không tự bảo vệ việc serialize entity sau khi dữ liệu khác chưa được tải.

### 6.2. DISTINCT và hàng trùng root

Khi join một collection, một root có thể xuất hiện ở nhiều hàng SQL. `distinct` trong JPQL diễn đạt ý định lấy root entity không trùng trong kết quả; cách Hibernate xử lý duplicate phụ thuộc phiên bản và query. Nó không làm biến mất lượng hàng mà database phải trả qua join.

### 6.3. Không fetch mọi association

Nếu trang chỉ hiển thị mã đơn và tên customer, không cần fetch lines, payments, shipments, audit events và toàn bộ lịch sử. Hãy tải đúng dữ liệu màn hình cần.

## 7. Giải pháp 2: EntityGraph định nghĩa fetch plan

Jakarta Persistence cung cấp entity graph để mô tả association cần tải theo từng use case.

Named graph:

```java
@Entity
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
public class PurchaseOrder {
    // Mapping.
}
```

Áp dụng:

```java
EntityGraph<?> graph = em.getEntityGraph(
    "PurchaseOrder.detail"
);

PurchaseOrder order = em.createQuery("""
    select o from PurchaseOrder o where o.id = :id
    """, PurchaseOrder.class)
    .setParameter("id", orderId)
    .setHint("jakarta.persistence.fetchgraph", graph)
    .getSingleResult();
```

Entity graph giúp tách fetch plan khỏi câu query. Query vẫn quyết định root/filter/order; graph định nghĩa association cần fetch.

### 7.1. Fetch graph và load graph

- `jakarta.persistence.fetchgraph` xem các thuộc tính trong graph là eager cho lần tải, còn thuộc tính không khai báo được xem là lazy theo graph semantics.
- `jakarta.persistence.loadgraph` xem thuộc tính trong graph là eager, còn thuộc tính không khai báo giữ fetch behavior mặc định của mapping.

Provider có thể fetch thêm state ngoài graph theo đặc tả. Entity graph không bảo đảm một SQL JOIN duy nhất.

### 7.2. Spring Data JPA @EntityGraph

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, UUID> {

    @EntityGraph(
        value = "PurchaseOrder.detail",
        type = EntityGraph.EntityGraphType.FETCH
    )
    Optional<PurchaseOrder> findDetailedById(UUID id);
}
```

Service gọi repository trong transaction, sau đó map DTO:

```java
@Transactional(readOnly = true)
public OrderResponse getDetail(UUID id) {
    PurchaseOrder order = repository.findDetailedById(id)
        .orElseThrow();

    return mapper.toResponse(order);
}
```

Mapper cần chỉ đọc các association có trong graph hoặc được tải bằng cơ chế khác. Đừng giả định graph đã tải mọi thứ chỉ vì tên graph có chữ `detail`.

## 8. Giải pháp 3: DTO projection khi không cần entity graph

Nếu API chỉ cần một số trường, DTO projection thường là lựa chọn gọn và ít rủi ro hơn việc tải entity rồi duyệt association.

Ví dụ:

```java
public record OrderSummary(
    UUID id,
    String status,
    String customerName
) {}
```

```java
List<OrderSummary> rows = em.createQuery("""
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

Projection trả các giá trị được chọn, không yêu cầu giữ một object graph managed để controller đọc tiếp.

Dùng DTO projection khi:

- Chỉ cần một số cột.
- Làm danh sách, báo cáo hoặc dashboard.
- Không cần dirty checking trên kết quả.
- Muốn kiểm soát API response và tránh serialization entity.
- Cần pagination rõ ràng.

Dùng entity + fetch plan khi use case cần domain entity managed để thực hiện nghiệp vụ hoặc cần nhiều association đã tải.

## 9. Giải pháp 4: Khởi tạo association tường minh trong context còn mở

Đôi khi một use case cần một association cụ thể nhưng không cần thay query tổng thể. Có thể khởi tạo nó trong khi Session còn hoạt động.

Với Hibernate:

```java
import org.hibernate.Hibernate;

@Transactional(readOnly = true)
public void inspectOrder(UUID id) {
    PurchaseOrder order = em.find(PurchaseOrder.class, id);

    Hibernate.initialize(order.getLines());
}
```

`Hibernate.initialize` là API Hibernate-specific. Nó yêu cầu khởi tạo proxy/collection nếu chưa initialized và cần Session phù hợp còn mở.

Kiểm tra:

```java
boolean loaded = Hibernate.isInitialized(order.getLines());
```

Jakarta Persistence có API portable để kiểm tra trạng thái load:

```java
boolean loaded = em.getEntityManagerFactory()
    .getPersistenceUnitUtil()
    .isLoaded(order, "lines");
```

`PersistenceUnitUtil.isLoaded` chỉ kiểm tra trạng thái; nó không tự tải association.

### 9.1. Initialize không tự tải graph sâu

`Hibernate.initialize(order.getLines())` tải collection lines, nhưng không có nghĩa mọi `line.product.category` bên trong cũng initialized. Nếu mapper tiếp tục truy cập association sâu, vẫn có thể phát sinh query khác hoặc lazy exception sau khi context đóng.

Cần initialize đúng các tầng cần dùng hoặc tốt hơn là định nghĩa fetch plan ngay ở query.

### 9.2. Initialize từng collection có thể tạo N+1

```java
for (PurchaseOrder order : orders) {
    Hibernate.initialize(order.getLines());
}
```

Nếu có 100 order và mỗi collection được tải riêng, có thể tạo 100 query bổ sung. Hãy cân nhắc fetch join, entity graph, batch fetching hoặc query collection theo danh sách root IDs.

## 10. Batch fetching và subselect fetching

Nếu cần tải nhiều association lazy cho nhiều root, Hibernate có các chiến lược giúp giảm N+1.

### 10.1. @BatchSize

```java
import org.hibernate.annotations.BatchSize;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<OrderLine> lines = new ArrayList<>();
```

Khi nhiều collection cùng role thuộc các owner trong Session đang chờ initialize, Hibernate có thể tải chúng theo nhóm bằng một truy vấn có nhiều owner IDs, tùy mapping và phiên bản.

`@BatchSize` giảm số round-trip trong một số workload; nó không bảo đảm collection tự được tải trước khi Session đóng. Code vẫn cần truy cập chúng trong context còn hoạt động.

### 10.2. @Fetch(SUBSELECT)

Hibernate hỗ trợ chiến lược subselect fetching trong một số mapping:

```java
import org.hibernate.annotations.Fetch;
import org.hibernate.annotations.FetchMode;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<OrderLine> lines = new ArrayList<>();
```

Khi collection được khởi tạo, Hibernate có thể tải các collection cùng role cho nhóm owner liên quan bằng một subselect thay vì một SELECT riêng cho mỗi owner. Hành vi cụ thể phụ thuộc cách các owner được tải và query ban đầu.

Batch/subselect là chiến lược tối ưu số truy vấn. Chúng không thay thế việc thiết kế ranh giới context và DTO.

## 11. Open Session in View (OSIV) là gì?

**Open Session in View** là pattern giữ persistence context/Session mở trong suốt vòng đời một web request, thường qua filter hoặc interceptor. Mục tiêu ban đầu là cho phép view layer truy cập association lazy sau khi service transaction kết thúc.

Sơ đồ:

```text
HTTP request bắt đầu
       |
       v
Mở EntityManager / Session (OSIV)
       |
       v
Controller gọi service
       |
       +-- transaction bắt đầu
       +-- query entity
       +-- transaction commit
       |
       v
Controller / serializer đọc lazy association
       |
       +-- Session vẫn mở
       +-- có thể chạy thêm SELECT
       |
       v
HTTP response hoàn tất
       |
       v
Đóng EntityManager / Session
```

Nếu Session còn mở, truy cập lazy association trong serialization có thể thành công, nên lỗi `LazyInitializationException` ít xuất hiện. Nhưng điều đó không có nghĩa thiết kế fetch data đã rõ ràng.

### 11.1. OSIV không có nghĩa transaction vẫn mở

OSIV thường giữ Session mở qua request, nhưng transaction service có thể đã commit trước khi serializer đọc association. Khi đó, các truy vấn lazy bổ sung có thể chạy ngoài transaction nghiệp vụ ban đầu, tùy cấu hình connection/transaction.

Hệ quả:

- SQL phát sinh ở tầng controller/serialization.
- Các truy vấn không nằm trong cùng transaction snapshot với thao tác service trước đó.
- Một request có thể tạo nhiều truy vấn ngoài dự kiến.
- Thời gian giữ persistence context và tài nguyên dài hơn.
- Lỗi dữ liệu có thể xuất hiện muộn trong lúc render response.

### 11.2. OSIV có thể che giấu N+1

Ví dụ controller trả entity:

```java
@GetMapping("/orders")
public List<PurchaseOrder> list() {
    return service.findOrders();
}
```

Serializer duyệt `order.customer` và `order.lines`. Với OSIV, các lazy load có thể chạy thành công. Nhưng nếu có 100 order, serializer có thể kích hoạt rất nhiều SELECT.

API nhìn như hoạt động, nhưng hiệu năng phụ thuộc số entity và association trong response.

### 11.3. OSIV và tính nhất quán của response

Service transaction có thể đọc order ở thời điểm T1. Sau khi transaction kết thúc, serializer truy vấn customer hoặc lines ở thời điểm T2. Nếu dữ liệu thay đổi giữa hai thời điểm, response có thể kết hợp state được đọc từ các thời điểm khác nhau.

Đây không nhất thiết là lỗi trong mọi hệ thống, nhưng phải hiểu nếu API yêu cầu một snapshot nhất quán.

### 11.4. Có nên tắt OSIV?

Đó là quyết định kiến trúc. Tắt OSIV buộc ứng dụng tải dữ liệu cần thiết trong transaction/service và thường giúp phát hiện sớm code phụ thuộc lazy loading ngoài boundary. Tuy nhiên, sau khi tắt, các endpoint đang trả entity có thể bắt đầu ném LazyInitializationException; cần chuyển sang DTO/fetch plan trước hoặc cùng lúc.

Không nên chỉ tắt OSIV rồi xem mọi lỗi là Hibernate bug. Cần sửa hợp đồng dữ liệu của service và controller.

## 12. Cấu hình OSIV trong Spring Boot

Một số ứng dụng Spring Boot có thể bật Open EntityManager in View theo cấu hình mặc định hoặc tùy phiên bản/starter. Có thể cấu hình rõ trong application properties:

```properties
spring.jpa.open-in-view=false
```

Tên property thuộc Spring Boot. Hành vi mặc định và cảnh báo startup có thể khác theo version và cấu hình dự án; hãy xác nhận runtime config thực tế.

Khi tắt OSIV:

- Persistence context gắn với transaction/use case theo transaction manager.
- Lazy association chưa tải không nên được truy cập sau khi service transaction kết thúc.
- Service query cần fetch đúng dữ liệu hoặc map DTO.
- Những endpoint trước đây vô tình dựa vào lazy loading trong serializer phải được điều chỉnh.

Không xem `spring.jpa.open-in-view=false` là tối ưu hiệu năng tự động. Nếu query/service vẫn tải graph quá lớn hoặc tạo N+1 bên trong transaction, hiệu năng vẫn có thể kém.

## 13. Không nên dựa vào hibernate.enable_lazy_load_no_trans như cách sửa mặc định

Hibernate có cấu hình native:

```properties
hibernate.enable_lazy_load_no_trans=true
```

Tùy phiên bản Hibernate, cấu hình này cho phép một số lazy proxy/collection được khởi tạo ngoài transaction/session ban đầu bằng cách mở temporary Session hoặc cơ chế tương ứng.

Đây không phải cách xử lý mặc định nên chọn cho ứng dụng mới, vì:

- Có thể tạo truy vấn ẩn ở nơi code chỉ gọi getter.
- Dễ biến một lần serialize thành nhiều truy vấn riêng lẻ.
- Các lần tải có thể chạy trong transaction/connection khác với unit of work ban đầu.
- Có thể tạo N+1 và tăng chi phí connection.
- Dữ liệu được tải không nhất thiết thuộc cùng snapshot với entity đã lấy trước đó.
- Khó kiểm soát exception, transaction và hiệu năng tại service boundary.

Nó có thể hữu ích trong một số ứng dụng legacy có lý do tương thích cụ thể, nhưng không thay thế fetch plan và ranh giới transaction rõ ràng.

**Không nên bật property này chỉ để làm biến mất stack trace.** Nếu association là dữ liệu cần cho response, hãy tải nó có chủ đích trước khi context kết thúc.

## 14. EntityGraph và FetchProfile giúp tránh lazy access ngoài context

Thay vì để controller truy cập association tùy ý, service có thể xác định fetch plan.

### 14.1. EntityGraph

```java
@EntityGraph(
    attributePaths = {"customer", "lines.product"},
    type = EntityGraph.EntityGraphType.FETCH
)
Optional<PurchaseOrder> findDetailedById(UUID id);
```

Service:

```java
@Transactional(readOnly = true)
public OrderDetailResponse detail(UUID id) {
    PurchaseOrder order = repository.findDetailedById(id)
        .orElseThrow();

    return toResponse(order);
}
```

EntityGraph là tính năng Jakarta Persistence, có thể dùng với Hibernate và JPA provider khác. Graph mô tả association cần fetch; provider có thể chọn JOIN hoặc secondary SELECT.

### 14.2. Hibernate FetchProfile

Hibernate-specific fetch profile có thể được bật trong Session:

```java
Session session = em.unwrap(Session.class);
session.enableFetchProfile("customer-with-orders");

try {
    Customer customer = session.find(Customer.class, customerId);
    return toCustomerResponse(customer);
} finally {
    session.disableFetchProfile("customer-with-orders");
}
```

Fetch profile thay đổi chiến lược fetch association trong phạm vi Session. Nó không phải API portable JPA và không tự tạo DTO.

### 14.3. EntityGraph không đảm bảo một SQL

Dù graph chỉ rõ customer, lines và product, Hibernate có thể tạo nhiều SQL tùy cardinality, query và provider strategy. Điều quan trọng là các association cần thiết được tải trước khi service trả DTO; sau đó cần đo số statement để tránh N+1.

## 15. LazyInitializationException trong JSON serialization

Một nguyên nhân phổ biến là trả entity trực tiếp từ REST controller:

```java
@GetMapping("/orders/{id}")
public PurchaseOrder get(@PathVariable UUID id) {
    return orderService.get(id);
}
```

JSON serializer có thể gọi getter:

```text
getId()
getCustomer()
    getName()
getLines()
    getProduct()
        getName()
```

Nếu persistence context đã đóng, association lazy chưa initialized có thể gây exception. Nếu OSIV còn bật, serializer có thể kích hoạt nhiều truy vấn thay vì ném lỗi.

### 15.1. Vòng tham chiếu JSON là vấn đề riêng

Entity hai chiều có thể tạo vòng:

```text
PurchaseOrder -> lines -> OrderLine -> order -> lines -> ...
```

Serializer có thể đệ quy vô hạn hoặc báo lỗi vòng tham chiếu. Đây là vấn đề object graph/serialization riêng, dù lazy loading có thể làm nó phức tạp hơn.

Đừng nhầm:

- `LazyInitializationException`: không thể khởi tạo dữ liệu lazy do thiếu Session phù hợp.
- Vòng tham chiếu JSON: serializer đi theo association hai chiều không có điểm dừng.
- N+1: serializer hoặc mapper kích hoạt quá nhiều truy vấn.
- Lộ dữ liệu: entity có thuộc tính nhạy cảm bị serialize ngoài ý muốn.

DTO giải quyết được nhiều vấn đề vì chỉ chứa cấu trúc dữ liệu API cần công khai.

### 15.2. Không dùng @JsonIgnore như giải pháp chung cho fetch

`@JsonIgnore` có thể ngăn serializer đi vào một thuộc tính, nhưng không làm association được tải khi service thực sự cần nó. Nó chỉ thay đổi serialization. Dùng DTO để định nghĩa response thường rõ hơn việc điều khiển entity graph bằng annotation JSON.

## 16. Lazy loading trong mapper, equals, hashCode và toString

Một lỗi khó tìm là code không chủ ý truy cập lazy association.

### 16.1. Lombok @Data

`@Data` có thể sinh `toString`, `equals` và `hashCode` dựa trên nhiều field. Nếu entity có association lazy, logging hoặc so sánh object có thể gọi getter và kích hoạt tải dữ liệu.

Ví dụ không nên dùng bừa:

```java
@Entity
@Data
public class PurchaseOrder {
    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines;
}
```

Khi logger in `order`, `toString()` có thể duyệt `customer`/`lines`. Sau khi context đóng, có thể ném LazyInitializationException; trong Session đang mở, có thể tạo N+1.

Nên định nghĩa method equality/string representation có chủ đích, tránh đưa association vào `equals/hashCode/toString` của entity.

### 16.2. Mapper reflection

Một mapper có thể tự động đọc mọi property, bao gồm association không cần cho DTO. Cần cấu hình mapping rõ các trường được dùng hoặc viết projection/service mapper theo use case.

### 16.3. Debugger cũng có thể gọi getter

Một watch expression như `order.getLines()` có thể kích hoạt lazy loading khi debug trong Session còn mở, hoặc gây exception khi Session đã đóng. Đừng dùng một lần evaluate trong debugger làm bằng chứng rằng code production đã thực thi đúng fetch plan.

## 17. Truy cập association sau khi detach: những gì còn dùng được?

Giả sử:

```java
PurchaseOrder order = loadAndCloseEntityManager(orderId);
```

Sau khi context đóng:

| Thao tác | Kết quả có thể gặp |
|---|---|
| `order.getId()` | Thường đọc được identifier đã có |
| `order.getStatus()` nếu đã tải | Đọc được state đã có trong object |
| `order.getCustomer().getName()` khi customer chưa initialized | Có thể LazyInitializationException |
| Duyệt `order.getLines()` khi collection chưa initialized | Có thể LazyInitializationException |
| Duyệt collection đã initialized | Có thể dùng dữ liệu đã có trong bộ nhớ |
| Truy cập association sâu chưa tải trong một line | Có thể LazyInitializationException |
| Sửa field của detached entity | Chỉ đổi object Java; không có dirty checking của context đã đóng |

Kết quả chính xác phụ thuộc thuộc tính đã initialized hay chưa, proxy/access strategy và cách entity được tải.

### 17.1. Không cần tải mọi thứ để dùng entity detached

Nếu response chỉ cần ID và status, entity đã tải hai field ấy có thể đủ để map DTO sau khi đóng context. Tuy nhiên, tốt hơn là chuyển DTO ngay trong transaction để không phụ thuộc vào những giả định về state được tải.

### 17.2. Không thể “attach” bằng cách gọi getter

Gọi getter không gắn entity trở lại Session. Muốn tiếp tục thao tác persistence, dùng managed entity trong context mới hoặc merge theo hợp đồng thích hợp. Nhưng merge không phải giải pháp cho một response read-only chỉ cần vài association.

## 18. Có thể dùng merge để khắc phục LazyInitializationException không?

Thường **không nên dùng merge chỉ để đọc association lazy**.

Ví dụ:

```java
PurchaseOrder detached = loadAndClose(orderId);

PurchaseOrder managed = em.merge(detached);
String name = managed.getCustomer().getName();
```

Merge có thể hợp nhất state detached vào managed instance và cascade theo mapping. Nhưng:

- Nó có thể copy state cũ vào entity hiện tại.
- Có thể gây SELECT/UPDATE không cần thiết.
- Cascade MERGE có thể đi qua graph rộng.
- Có nguy cơ ghi đè thay đổi mới hơn nếu object detached stale.
- Không phải cách tối ưu để tạo một response DTO.

Nếu chỉ cần đọc chi tiết, tải root bằng query có fetch plan trong transaction đọc mới. Nếu cần cập nhật, tải managed entity và áp dụng command. Chỉ dùng merge khi use case thực sự cần hợp nhất detached state có kiểm soát.

## 19. Mở một EntityManager mới không tự khởi tạo proxy cũ

Một cách hiểu nhầm:

```java
PurchaseOrder detached = loadAndClose(orderId);

EntityManager newEm = emf.createEntityManager();

try {
    // Không làm proxy cũ tự thuộc newEm:
    detached.getLines().size();
} finally {
    newEm.close();
}
```

`detached` và proxy/collection của nó vẫn gắn với context cũ đã đóng. Mở EntityManager mới không tự động thay Session bên trong wrapper.

Cách đúng là tải lại entity trong context mới:

```java
EntityManager em = emf.createEntityManager();

try {
    PurchaseOrder managed = em.find(
        PurchaseOrder.class,
        orderId
    );

    // Tải association bằng query/fetch plan ở context mới.
} finally {
    em.close();
}
```

Hoặc dùng fetch join/entity graph trực tiếp trong query. Không cố dùng lại persistent collection wrapper cũ như một proxy có thể chuyển context.

## 20. Transaction propagation và self-invocation trong Spring

`@Transactional` không tự động áp dụng trong mọi lời gọi Java. Với Spring proxy-based transaction management phổ biến, lời gọi method phải đi qua proxy phù hợp.

Ví dụ:

```java
@Service
public class OrderService {

    public OrderResponse get(UUID id) {
        return loadDetail(id); // Self-invocation.
    }

    @Transactional(readOnly = true)
    public OrderResponse loadDetail(UUID id) {
        // ...
    }
}
```

Nếu `get` gọi trực tiếp `loadDetail` trên cùng object, lời gọi nội bộ có thể bỏ qua transaction interceptor. Khi đó, method tưởng có transaction nhưng thực tế không có boundary như mong muốn.

Hãy đặt `@Transactional` trên entry point được gọi qua Spring-managed bean/proxy, hoặc tách query use case thành một service riêng.

### 20.1. REQUIRED và transaction đang có

Nếu method tham gia transaction hiện có với propagation `REQUIRED`, nó thường dùng chung transaction và persistence context được transaction manager quản lý. Entity được tải trong đó có thể tiếp tục lazy-load trong cùng context.

Nếu method chạy độc lập và transaction kết thúc trước khi caller truy cập association, entity có thể detached.

### 20.2. REQUIRES_NEW không phải cách giữ context lâu hơn

`REQUIRES_NEW` tạo transaction độc lập theo transaction manager, không làm entity từ context cũ tự gắn sang context mới. Nếu method con trả entity ra ngoài, entity vẫn có thể detached sau khi transaction con kết thúc.

Đừng dùng propagation để che một hợp đồng trả entity không rõ ràng.

## 21. Lazy loading trong asynchronous task và thread khác

Hibernate Session/EntityManager thông thường không thread-safe và không nên chia sẻ giữa các thread.

Code nguy hiểm:

```java
@Transactional
public void process(UUID orderId) {
    PurchaseOrder order = em.find(PurchaseOrder.class, orderId);

    CompletableFuture.runAsync(() -> {
        // Thread khác, không nên dùng Session/EntityManager
        // hoặc lazy proxy của transaction ban đầu.
        order.getLines().forEach(this::processLine);
    });
}
```

Task bất đồng bộ có thể chạy sau khi transaction/context ban đầu kết thúc. Lazy association chưa initialized có thể gây LazyInitializationException; chia sẻ Session còn có nguy cơ concurrency không an toàn.

### 21.1. Truyền ID hoặc DTO sang worker

Một pattern an toàn hơn:

```java
public record ProcessOrderCommand(UUID orderId) {}
```

Worker mở transaction riêng và tải dữ liệu cần thiết:

```java
@Transactional
public void process(ProcessOrderCommand command) {
    PurchaseOrder order = repository.findForProcessing(
        command.orderId()
    ).orElseThrow();

    // Xử lý trong persistence context của worker.
}
```

Hoặc message chỉ chứa dữ liệu bất biến cần thiết. Không gửi entity managed/proxy qua message queue hoặc thread như một object graph có thể tự tải.

## 22. Entity graph, fetch profile và JOIN FETCH không tự bảo đảm mọi dữ liệu

Một fetch plan cần được thiết kế theo use case. Ví dụ graph có:

```text
PurchaseOrder
  +-- customer
  +-- lines
        +-- product
```

Nếu mapper tiếp tục truy cập `line.product.category.parent` nhưng graph chỉ tải đến product, association sâu hơn vẫn có thể lazy.

Hãy lập danh sách các đường thuộc tính mà response/service thực sự đọc. Sau đó chọn:

- JPQL/HQL JOIN FETCH.
- Jakarta Persistence EntityGraph.
- Hibernate FetchProfile.
- DTO projection.
- Query riêng theo collection/ID nếu collection lớn.

Đừng đặt tên graph `fullDetail` rồi mặc định nó tải mọi association có thể tồn tại. Tên graph phải phản ánh một hợp đồng use case cụ thể.

### 22.1. Fetch join collection và pagination

Fetch collection trong query phân trang có thể làm SQL nhân hàng và ảnh hưởng pagination root. Một pattern thường dễ kiểm soát:

1. Phân trang ID của root.
2. Tải association cần thiết cho tập ID của trang.
3. Map DTO trong transaction.
4. Giữ thứ tự kết quả theo danh sách ID ban đầu nếu query `IN` không bảo đảm thứ tự.

Nếu collection rất lớn, tải collection riêng có phân trang thay vì fetch toàn bộ.

### 22.2. Nhiều collection có thể tạo Cartesian product

Fetch lines, payments và shipments cùng lúc có thể nhân số hàng SQL. Lazy exception được xử lý bằng fetch plan không có nghĩa phải join tất cả association trong một query.

Có thể tải từng phần theo query riêng trong cùng transaction đọc nếu cần snapshot nhất quán, hoặc xây read model chuyên biệt.

## 23. Kiểm tra trạng thái load và khởi tạo association

Hibernate cung cấp:

```java
Hibernate.isInitialized(order.getLines());
```

để kiểm tra proxy/collection đã initialized chưa.

Có thể chủ động khởi tạo:

```java
Hibernate.initialize(order.getLines());
```

Hai API này là Hibernate-specific. Đối với code portable JPA, có `PersistenceUnitUtil.isLoaded`:

```java
boolean loaded = em.getEntityManagerFactory()
    .getPersistenceUnitUtil()
    .isLoaded(order, "lines");
```

`isLoaded` không khởi tạo association. Nó chỉ cho biết thuộc tính đã được load hay chưa theo provider.

### 23.1. Không gọi initialize ngoài context

`Hibernate.initialize` không mở lại Session đã đóng và không gắn proxy cũ vào EntityManager mới. Nó cần Session có thể phục vụ việc khởi tạo.

### 23.2. Đừng dùng isInitialized trong business logic

Ví dụ không nên để domain method thay đổi kết quả nghiệp vụ tùy association đã được tải:

```java
if (Hibernate.isInitialized(order.getLines())) {
    // Tính tổng theo lines.
} else {
    // Bỏ qua lines.
}
```

Fetch state là chi tiết persistence. Business behavior nên dựa trên dữ liệu hợp lệ được use case cung cấp, không dựa vào association tình cờ đã được khởi tạo hay chưa.

## 24. Logging, exception handling và nơi lỗi xuất hiện

LazyInitializationException thường xuất hiện đúng lúc truy cập proxy/collection, nhưng dòng code trực tiếp gây lỗi có thể nằm sâu trong mapper hoặc serializer.

Khi debug:

1. Xác định association hoặc thuộc tính lazy được nêu trong exception.
2. Tìm nơi entity được tải.
3. Xác định EntityManager/Session được tạo và đóng ở đâu.
4. Xem transaction boundary của service và caller.
5. Kiểm tra association đã initialized trước khi context đóng chưa.
6. Tìm getter/mapper/serializer/logging đang truy cập association.
7. Quyết định dữ liệu đó cần trong response/use case hay chỉ bị truy cập vô tình.
8. Sửa fetch plan hoặc DTO tại ranh giới phù hợp.

Không nên chỉ bắt exception:

```java
try {
    return order.getLines().size();
} catch (LazyInitializationException ex) {
    return 0;
}
```

Cách này biến lỗi persistence thành dữ liệu sai: ứng dụng có thể báo đơn không có line dù database thực tế có dữ liệu. Nếu dữ liệu là bắt buộc, phải tải nó đúng cách hoặc trả lỗi nghiệp vụ phù hợp.

### 24.1. Không log entity graph trực tiếp

Thay vì:

```java
log.info("Order: {}", order);
```

hãy log identifier và các trường scalar an toàn:

```java
log.info("Processing orderId={}", order.getId());
```

Logger không nên vô tình kích hoạt toString của association lazy hoặc làm lộ dữ liệu nhạy cảm.

## 25. LazyInitializationException và transaction read-only

Một query service thường có:

```java
@Transactional(readOnly = true)
public OrderDetailResponse getDetail(UUID id) {
    // Tải entity và map DTO.
}
```

`readOnly = true` là gợi ý/cấu hình cho transaction manager/provider; nó không tự tải association lazy. Association vẫn cần fetch plan rõ.

Nếu service chỉ trả entity, controller truy cập association sau khi transaction kết thúc thì read-only không giải quyết vấn đề. Cần map DTO trước khi trả hoặc có một persistence context khác được quản lý có chủ đích.

Không dùng `readOnly = true` để thay transaction boundary, và không giả định nó luôn cấm ghi ở mọi cấu hình.

## 26. So sánh các cách xử lý

| Cách | Khi phù hợp | Hạn chế/cảnh báo |
|---|---|---|
| **JOIN FETCH** | Query cụ thể cần một số association | Join collection có thể nhân hàng và ảnh hưởng pagination |
| **EntityGraph** | Fetch plan theo use case, muốn chuẩn JPA | Provider có thể fetch thêm hoặc dùng nhiều SQL |
| **FetchProfile** | Ứng dụng Hibernate cần override association theo Session | Hibernate-specific, scope Session |
| **DTO projection** | Chỉ cần một số field cho response/report | Không trả managed entity để dirty checking |
| **Hibernate.initialize** | Cần khởi tạo một association cụ thể trong Session đang mở | Dễ tạo N+1 nếu gọi lặp; không hoạt động với Session đã đóng |
| **Batch fetching** | Nhiều collection/proxy cùng role cần tải theo nhóm | Không thay fetch boundary; phụ thuộc workload |
| **Open Session in View** | Ứng dụng chấp nhận lazy load ở web view và kiểm soát được tác động | Có thể che N+1, SQL ngoài transaction và đọc không cùng snapshot |
| **enable_lazy_load_no_trans** | Một số tình huống legacy có lý do cụ thể | Truy vấn ẩn, temporary context, hiệu năng/nhất quán khó kiểm soát |
| **merge detached** | Cần hợp nhất detached state để cập nhật | Không phải giải pháp đọc; có thể ghi đè state và cascade rộng |

### Lựa chọn thường phù hợp cho REST API

- Danh sách: DTO projection hoặc graph to-one vừa đủ.
- Chi tiết: EntityGraph/JOIN FETCH cho association cần, map DTO trong transaction.
- Collection lớn: query riêng có phân trang.
- Background worker: truyền ID/command, tải entity trong transaction của worker.
- Domain update: tải managed aggregate và áp dụng command, không dựa vào proxy ngoài context.

## 27. Ví dụ đầy đủ: service trả DTO thay vì entity detached

DTO:

```java
public record OrderLineResponse(
    String productName,
    int quantity
) {}

public record OrderDetailResponse(
    UUID id,
    String customerName,
    List<OrderLineResponse> lines
) {}
```

Repository:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, UUID> {

    @EntityGraph(
        attributePaths = {"customer", "lines.product"},
        type = EntityGraph.EntityGraphType.FETCH
    )
    Optional<PurchaseOrder> findDetailedById(UUID id);
}
```

Service:

```java
@Service
public class OrderQueryService {

    private final PurchaseOrderRepository repository;

    public OrderQueryService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderDetailResponse getDetail(UUID id) {
        PurchaseOrder order = repository.findDetailedById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));

        List<OrderLineResponse> lines = order.getLines().stream()
            .map(line -> new OrderLineResponse(
                line.getProduct().getName(),
                line.getQuantity()
            ))
            .toList();

        return new OrderDetailResponse(
            order.getId(),
            order.getCustomer().getName(),
            lines
        );
    }
}
```

Controller:

```java
@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderQueryService service;

    public OrderController(OrderQueryService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public OrderDetailResponse get(@PathVariable UUID id) {
        return service.getDetail(id);
    }
}
```

Trong flow này:

1. Repository tải root và association theo entity graph.
2. Service đọc association khi transaction/persistence context còn hoạt động.
3. Service chuyển dữ liệu sang DTO.
4. Transaction kết thúc.
5. Controller serialize DTO, không truy cập lazy proxy.

Đây là một hợp đồng rõ: caller nhận dữ liệu response, không nhận entity cần Session để tải tiếp.

## 28. Kiểm thử hành vi lazy loading

Khi kiểm thử fetch boundary, cần phân biệt state đã initialized và state còn lazy.

### 28.1. Kiểm tra association sau khi service trả DTO

Gọi service qua Spring bean/proxy, xác nhận DTO có đủ dữ liệu sau khi transaction kết thúc. Đây là kiểm thử hợp đồng API hữu ích hơn việc chỉ xác nhận entity được trả về.

### 28.2. Tái hiện lỗi trong test riêng

Có thể:

1. Mở EntityManager.
2. Tải root mà không fetch collection.
3. Đóng EntityManager.
4. Truy cập collection chưa initialized.
5. Quan sát LazyInitializationException.

Test nên kiểm soát dữ liệu và fetch plan để bảo đảm collection thực sự chưa được khởi tạo.

### 28.3. Kiểm tra Hibernate.isInitialized

Trong integration test Hibernate:

```java
assertFalse(Hibernate.isInitialized(order.getLines()));
```

Sau query có fetch plan:

```java
assertTrue(Hibernate.isInitialized(order.getLines()));
```

Cần chạy trong persistence context mới hoặc clear state phù hợp, vì entity đã load trước đó có thể giữ association initialized.

### 28.4. Đếm query để phát hiện N+1

Một test chỉ có một order thường không bộc lộ N+1. Dùng nhiều root và nhiều association, sau đó quan sát statement count hoặc Hibernate statistics. Kết quả phải phản ánh cardinality thực tế của use case.

Không dùng việc “test không còn LazyInitializationException” làm tiêu chí duy nhất: OSIV hoặc temporary session có thể làm exception biến mất nhưng query vẫn bị phát sinh quá nhiều.

## 29. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Trả entity từ service rồi controller duyệt lazy association | LazyInitializationException khi context đã đóng | Map DTO trong transaction |
| Bật OSIV để che mọi lỗi | SQL ẩn trong serializer, N+1 và dữ liệu đọc ở thời điểm khác | Fetch plan rõ, DTO |
| Gọi Hibernate.initialize sau khi Session đóng | Vẫn không có Session để khởi tạo | Tải association trong context mới |
| Mở EntityManager mới rồi dùng proxy cũ | Proxy vẫn thuộc context cũ đã đóng | Tải lại entity trong context mới |
| Dùng merge để đọc detached graph | Copy state, cascade, SELECT/UPDATE không cần | Query/fetch plan trong transaction đọc |
| Đặt mọi association EAGER | Tải dư, query phức tạp và N+1 thứ cấp | Mapping LAZY phù hợp, fetch theo use case |
| Mapper gọi mọi getter | Kích hoạt lazy load ngoài ý muốn | Mapper/DTO có field rõ ràng |
| Lombok toString/equals/hashCode duyệt association | Lazy load hoặc đệ quy vòng | Loại association khỏi các method đó |
| Async task dùng entity/proxy của thread khác | Context không được truyền, Session không thread-safe | Truyền ID/DTO và tải trong worker |
| Initialize collection từng root | N+1 query | EntityGraph, JOIN FETCH, batch fetching |
| Fetch mọi collection cùng lúc | Cartesian product/multiple bag | Tách query hoặc projection |
| Catch LazyInitializationException rồi trả collection rỗng | Response sai dữ liệu | Tải dữ liệu đúng hoặc trả lỗi phù hợp |
| Cho rằng transaction commit đồng nghĩa Session đóng | Nhầm điều kiện gây lỗi | Phân biệt transaction lifecycle và Session lifecycle |

## 30. Quy trình xử lý một stack trace thực tế

Khi gặp:

```text
org.hibernate.LazyInitializationException:
    could not initialize proxy - no Session
```

hãy đi theo luồng:

1. **Xác định proxy/collection bị lỗi.** Đọc tên role trong exception nếu có.
2. **Tìm nơi entity được tải.** Repository/service nào tạo ra object?
3. **Xác định context owner.** EntityManager/Session nào quản lý object và khi nào context đóng/clear/detach?
4. **Tìm điểm truy cập thực tế.** Controller, mapper, serializer, logger, debugger hay async worker?
5. **Xác định dữ liệu có thực sự cần không.** Có thể bỏ association khỏi response hay không?
6. **Chọn fetch plan.** DTO projection, EntityGraph, JOIN FETCH, FetchProfile hoặc query riêng.
7. **Đưa việc map dữ liệu vào boundary phù hợp.** Thường là application/query service trong transaction.
8. **Kiểm tra cardinality và số SQL.** Tránh đổi exception thành N+1.
9. **Kiểm tra các đường gọi khác.** Self-invocation, thread khác, OSIV, batch job hoặc cache.
10. **Xác nhận hợp đồng trả về.** Controller/consumer nhận DTO hoặc dữ liệu đã được chuẩn bị, không cần lazy load ngoài context.

Không sửa bằng cách mở Session toàn cục hoặc bắt exception bỏ qua. Hãy xác định use case và nơi cần dữ liệu.

## 31. Ghi nhớ

- **LazyInitializationException** là exception riêng của Hibernate, thường xuất hiện khi proxy/collection/thuộc tính lazy chưa initialized cần được truy cập mà không còn Session phù hợp.
- Entity detached vẫn là object Java; các trường đã tải vẫn đọc được. Chỉ phần dữ liệu lazy chưa có mới cần truy vấn bổ sung.
- **Transaction kết thúc và Session đóng không phải cùng một khái niệm**. Điều kiện trực tiếp thường là context không còn khả năng khởi tạo association.
- Proxy to-one và persistent collection trì hoãn tải dữ liệu; thao tác getter, size, iteration, mapper, logger hoặc serializer đều có thể kích hoạt tải.
- **Đặt fetch plan theo use case** bằng JOIN FETCH, EntityGraph hoặc FetchProfile để dữ liệu cần thiết được tải trước khi service trả kết quả.
- Dùng **DTO projection** khi chỉ cần một số trường; map DTO trong transaction để controller không truy cập entity lazy.
- `Hibernate.initialize` cần Session còn mở và chỉ khởi tạo association được yêu cầu; gọi lặp có thể tạo N+1.
- Batch fetching và subselect fetching giảm số truy vấn trong một số workload nhưng không thay thế boundary.
- **OSIV giữ Session mở qua request**, không có nghĩa transaction service vẫn mở; nó có thể che lazy exception nhưng tạo SQL ẩn, N+1 và dữ liệu đọc ở các thời điểm khác nhau.
- Không nên dựa vào `hibernate.enable_lazy_load_no_trans` như giải pháp mặc định vì nó có thể tạo temporary context và truy vấn khó kiểm soát.
- Không dùng `merge` chỉ để tải association của detached entity; tải lại entity bằng query/fetch plan trong context mới.
- Không chia sẻ Session/EntityManager hoặc proxy cần lazy load qua thread khác; truyền ID/DTO rồi tải trong transaction của worker.
- Tránh để Lombok `toString`/`equals`/`hashCode`, mapper hoặc serializer duyệt association lazy không chủ ý.
- Khi kiểm thử, xác nhận cả **dữ liệu response, trạng thái initialized và số SQL**, vì hết exception chưa chắc hết N+1.
- Tách rõ lỗi lazy initialization, vòng tham chiếu JSON, N+1 và vấn đề authorization; chúng có thể xuất hiện cùng lúc nhưng là các vấn đề khác nhau.

**Kết luận:** Lazy loading cho phép Hibernate chỉ lấy association khi cần, nhưng khả năng đó gắn với vòng đời Session/persistence context. Khi context đóng, proxy hoặc collection chưa initialized không thể tự tải dữ liệu qua context cũ. Cách thiết kế rõ ràng là **xác định dữ liệu mỗi use case cần, fetch trong transaction phù hợp và trả DTO/read model đã chuẩn bị**. OSIV hoặc temporary lazy loading có thể làm lỗi ít xuất hiện hơn, nhưng không thay thế việc kiểm soát fetch plan, transaction boundary và số truy vấn thực tế.
