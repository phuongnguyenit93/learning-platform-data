# Dùng EAGER cho mọi quan hệ để xử lý LazyInitializationException

Khi một ứng dụng Hibernate ném `LazyInitializationException`, phản ứng dễ gặp là đổi mọi association sang `FetchType.EAGER` để Hibernate tải hết dữ liệu ngay từ đầu. Cách này đôi khi làm exception biến mất ở một màn hình cụ thể, nhưng thường tạo ra vấn đề hiệu năng lớn hơn: mỗi lần load entity có thể kéo theo graph dữ liệu rộng, SQL phụ, N+1 queries, nhiều object trong heap và thời gian giữ connection dài hơn.

**Đặt tất cả quan hệ thành EAGER không phải cách xử lý đúng cho LazyInitializationException.** Cần xác định dữ liệu nào thật sự cần cho từng use case, tải dữ liệu đó trong transaction bằng fetch plan rõ ràng, rồi trả DTO hoặc dữ liệu đã chuẩn bị đầy đủ ra khỏi persistence boundary.

Bài thuộc chương **Lỗi thường gặp** của module *Data Persistence Relational Access ORM Hibernate*. Nội dung giải thích nguyên nhân lazy loading thất bại, default fetch types của JPA, tác động của EAGER, các cách lấy dữ liệu đúng lúc bằng JOIN FETCH, EntityGraph, DTO projection và Hibernate utilities, cùng cách tổ chức transaction, OSIV, kiểm thử SQL và chẩn đoán lỗi.

## 1. Lazy loading và lỗi thường gặp

Hibernate thường không tải mọi association ngay khi đọc entity. Với association lazy, provider có thể tạo proxy hoặc persistent collection đại diện cho dữ liệu liên quan. Dữ liệu thực sự được đọc khi code truy cập association.

~~~java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

Khi đọc Order:

~~~java
Order order = entityManager.find(Order.class, 100L);
~~~

Hibernate có thể load row của Order trước, còn Customer và lines chưa được tải. Trong lúc Session còn hoạt động, truy cập:

~~~java
String customerName = order.getCustomer().getName();
int lineCount = order.getLines().size();
~~~

có thể khiến Hibernate chạy thêm SQL để lấy dữ liệu.

Vấn đề xuất hiện nếu code truy cập association sau khi Session đã đóng hoặc entity đã detached:

~~~java
Order order = orderService.loadOrder(100L);

// Service đã kết thúc transaction và Session có thể đã đóng.
String name = order.getCustomer().getName();
~~~

Nếu Customer là proxy chưa được khởi tạo, Hibernate không còn Session để chạy query. Nó có thể ném `LazyInitializationException`.

Một thông báo thường thấy:

~~~text
org.hibernate.LazyInitializationException:
could not initialize proxy - no Session
~~~

Với collection, thông báo có thể đề cập collection không thể khởi tạo vì không còn Session.

## 2. Session, persistence context và detached entity

Một entity được Hibernate quản lý khi nó thuộc persistence context của Session/EntityManager đang hoạt động.

~~~text
                 persist()
   New entity  ------------->  Managed entity
                                   |
                                   | Session closes,
                                   | clear(), detach()
                                   v
                              Detached entity
                                   |
                                   | merge()
                                   v
                         Managed copy in new context
~~~

- **New/transient:** object mới, chưa được persistence context quản lý.
- **Managed/persistent:** entity đang được Session/EntityManager quản lý.
- **Detached:** entity từng được quản lý nhưng hiện không còn thuộc persistence context đó.
- **Removed:** entity được đánh dấu xóa trong persistence context.

Lazy proxy hoặc collection thường cần persistence context để tải dữ liệu chưa được khởi tạo. Khi object detached, field đã có giá trị vẫn đọc được; association chưa khởi tạo có thể không đọc được.

**LazyInitializationException không có nghĩa dữ liệu không tồn tại.** Nó có nghĩa Hibernate không thể thực hiện lazy load ở thời điểm code yêu cầu dữ liệu.

## 3. Vì sao không nên đổi mọi quan hệ sang EAGER?

Giả sử một Order liên kết với Customer, OrderLines, Payments, Shipment, Notes và các association khác:

~~~text
Order
  |-- Customer
  |     |-- Addresses
  |     |-- Contacts
  |
  |-- OrderLines
  |     |-- Product
  |     |     |-- Category
  |     |     |-- Reviews
  |
  |-- Payments
  |-- Shipment
  |     |-- TrackingEvents
  |
  |-- Notes
~~~

Nếu các association được khai báo EAGER hàng loạt, một use case chỉ cần mã đơn hàng và tên khách hàng vẫn có thể khiến Hibernate tải nhiều dữ liệu không cần thiết.

Hậu quả có thể gồm:

1. Nhiều SQL hơn do provider tải association bằng các câu SELECT phụ.
2. N+1 query khi load danh sách entity.
3. Nhiều rows bị nhân lên khi join nhiều to-many associations.
4. Tăng số managed entities và collections trong L1 cache.
5. Tăng heap allocation, GC pressure và thời gian hydration.
6. Tăng thời gian transaction và giữ JDBC connection.
7. Tăng lock/wait exposure nếu transaction làm nhiều việc hơn.
8. Query plan phức tạp, dữ liệu truyền qua mạng nhiều hơn.
9. Khó dự đoán SQL phát sinh từ một lời gọi repository.
10. Một endpoint nhỏ có thể tải graph lớn hơn nhu cầu thực tế.

**EAGER là yêu cầu về fetch semantics của association, không phải cam kết rằng Hibernate sẽ luôn dùng một SQL JOIN.**

## 4. FetchType EAGER không đồng nghĩa JOIN FETCH

Hai ý niệm cần tách biệt:

- **Fetch timing/requirement:** association cần được khởi tạo sớm hay có thể lazy.
- **Fetch strategy/SQL plan:** Hibernate dùng JOIN, SELECT riêng, batch hay cách khác để lấy dữ liệu.

`FetchType.EAGER` yêu cầu provider cung cấp association theo eager fetch semantics khi entity được lấy. Provider có thể dùng join hoặc secondary selects tùy query, mapping và dialect.

Ví dụ JPQL query chỉ chọn Order:

~~~java
List<Order> orders = entityManager.createQuery(
    "select o from Order o",
    Order.class
).getResultList();
~~~

Nếu Order có association EAGER mà câu query không fetch join association đó, Hibernate vẫn phải đáp ứng eager requirement. Nó có thể phát sinh SELECT bổ sung sau query chính. Khi danh sách có nhiều Orders, các SELECT phụ có thể tạo N+1.

Vì vậy:

~~~java
@ManyToOne(fetch = FetchType.EAGER)
private Customer customer;
~~~

không bảo đảm SQL luôn là:

~~~sql
select o.*, c.*
from orders o
join customers c on c.id = o.customer_id;
~~~

Hãy xem SQL thực tế và query plan thay vì suy luận chỉ từ annotation.

## 5. Default fetch types trong Jakarta Persistence

Jakarta Persistence định nghĩa default khác nhau theo loại association:

| Mapping | Default fetch type |
| --- | --- |
| `@ManyToOne` | `EAGER` |
| `@OneToOne` | `EAGER` |
| `@OneToMany` | `LAZY` |
| `@ManyToMany` | `LAZY` |
| `@Basic` | `EAGER` |

Với association to-one, `EAGER` là default nếu không ghi rõ. Với to-many, `LAZY` là default.

Điều này khiến nhiều ứng dụng vô tình có EAGER fetch dù developer không ghi annotation parameter:

~~~java
@ManyToOne
private Customer customer; // Default EAGER

@OneToMany(mappedBy = "order")
private List<OrderLine> lines; // Default LAZY
~~~

Trong ứng dụng cần kiểm soát fetch plan, thường nên khai báo rõ:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;
~~~

### LAZY có mức độ bắt buộc khác nhau

Theo Jakarta Persistence, `LAZY` là hint cho provider, còn `EAGER` là requirement. Provider có thể fetch sớm hơn khi mapping hoặc runtime cần thiết.

Hibernate hỗ trợ lazy to-one thông qua proxy hoặc bytecode enhancement tùy trường hợp. Với một số one-to-one associations, đặc biệt association inverse/optional, khả năng lazy loading còn phụ thuộc mapping và enhancement. Vì thế hãy xác minh SQL thực tế; đừng giả định mọi annotation LAZY đều bảo đảm không có query sớm.

## 6. EAGER ở to-one cũng có thể gây N+1

Ví dụ:

~~~java
@Entity
public class Order {

    @Id
    private Long id;

    @ManyToOne // EAGER mặc định
    private Customer customer;
}
~~~

Một query lấy 100 Orders có thể tạo:

~~~text
1 query lấy 100 Orders
100 secondary selects để lấy Customers
---------------------------------------
101 SQL executions
~~~

Hibernate có thể chọn fetch plan khác trong một số tình huống, nhưng không nên dựa vào assumption rằng EAGER luôn join.

Nếu endpoint danh sách cần Customer name, hãy định nghĩa query fetch rõ ràng hoặc DTO projection. Mapping EAGER toàn cục làm cho mọi use case phải trả chi phí association, kể cả use case không cần nó.

## 7. EAGER không đảm bảo toàn bộ object graph đã sẵn sàng

Giả sử:

~~~text
Order
  |-- Customer (EAGER)
        |-- Addresses (LAZY)
              |-- Country (LAZY)
~~~

Load Order có thể làm Customer được khởi tạo, nhưng Addresses vẫn lazy. Truy cập:

~~~java
order.getCustomer()
     .getAddresses()
     .get(0)
     .getCountry()
     .getName();
~~~

vẫn có thể ném LazyInitializationException nếu một association sâu chưa được khởi tạo và Session đã đóng.

Đổi mọi association ở mọi entity sang EAGER để tránh lỗi sẽ làm graph ngày càng rộng. Việc đó khiến fetch behavior toàn ứng dụng khó kiểm soát và không giải quyết tận gốc việc truy cập entity sau persistence boundary.

**Cần tải đúng graph mà use case cần**, không tải tất cả graph có thể tồn tại.

## 8. Mapping fetch plan và use-case fetch plan

Mapping mô tả quan hệ và default behavior. Một use case cụ thể quyết định dữ liệu nào cần được lấy.

| Use case | Dữ liệu cần |
| --- | --- |
| Trang danh sách đơn hàng | Order ID, ngày tạo, tổng tiền, Customer name |
| Trang chi tiết đơn hàng | Order, Customer, OrderLines, Product name |
| Báo cáo doanh thu | Một số scalar/aggregate values |
| Cập nhật trạng thái đơn | Order và trạng thái cần thay đổi |
| Xuất CSV | Các columns trong file, không cần toàn entity graph |
| Email thông báo | Customer email và một số thông tin Order |

Một mapping EAGER áp dụng cho mọi use case. Fetch plan tại query/service có thể chọn đúng associations cho từng màn hình hoặc workflow.

Đây là lý do nên giữ mapping tương đối lazy và tải dữ liệu theo query-specific plan.

## 9. Cách 1: dùng JOIN FETCH khi query cần association

JPQL/HQL fetch join yêu cầu Hibernate lấy association trong query.

~~~java
List<Order> orders = entityManager.createQuery(
    """
    select o
    from Order o
    join fetch o.customer
    where o.status = :status
    """,
    Order.class
)
.setParameter("status", OrderStatus.OPEN)
.getResultList();
~~~

Trong ví dụ, Customer được fetch cùng Order cho use case này, kể cả mapping Customer là LAZY.

Nếu association optional, dùng `left join fetch` để không loại bỏ Order không có association:

~~~java
Order order = entityManager.createQuery(
    """
    select o
    from Order o
    left join fetch o.customer
    where o.id = :id
    """,
    Order.class
)
.setParameter("id", orderId)
.getSingleResult();
~~~

### Khi nào dùng?

- Một query detail cần to-one associations.
- Muốn tránh lazy access sau khi Session đóng.
- Muốn SQL/fetch plan thể hiện ngay trong query.
- Cần kiểm soát chính xác association được lấy.

Fetch join là quyết định theo query, không bắt buộc thay mapping thành EAGER.

## 10. Fetch join collection

Khi cần một collection:

~~~java
Order order = entityManager.createQuery(
    """
    select distinct o
    from Order o
    left join fetch o.lines
    where o.id = :id
    """,
    Order.class
)
.setParameter("id", orderId)
.getSingleResult();
~~~

`distinct` diễn đạt ý định loại duplicate root entities ở query result. Hibernate 6 có cơ chế loại duplicate root entity do fetch join trong một số kết quả entity; vẫn nên dùng query semantics và version phù hợp, không áp dụng DISTINCT máy móc cho mọi query.

Join một collection làm số rows SQL tăng theo số phần tử. Nếu một Order có 100 lines, dữ liệu Order có thể được lặp lại trên nhiều rows của result set trước khi Hibernate dựng object graph.

### Không join fetch mọi collection cùng lúc

~~~java
select distinct o
from Order o
left join fetch o.lines
left join fetch o.payments
left join fetch o.notes
~~~

Nếu Order có 10 lines, 4 payments và 5 notes, kết quả join có thể tạo tới 10 × 4 × 5 = 200 combinations cho một Order, tùy cardinality và join conditions. Đây là row multiplication.

Nhiều bag collections còn có thể gặp lỗi Hibernate như `MultipleBagFetchException`. Dùng fetch plan hẹp, DTO hoặc nhiều queries có kiểm soát.

## 11. Không paginate trực tiếp với collection fetch join

Một query collection fetch join kết hợp `setFirstResult`/`setMaxResults` có thể không tương ứng với pagination trên root Orders vì SQL rows đã nhân theo collection. Hibernate có thể phải paginate trong memory hoặc báo warning/failure tùy configuration/version.

Có thể bật guard:

~~~properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

### Cách xử lý: page IDs trước, fetch details sau

~~~java
List<Long> ids = entityManager.createQuery(
    """
    select o.id
    from Order o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """,
    Long.class
)
.setParameter("status", OrderStatus.OPEN)
.setFirstResult(offset)
.setMaxResults(pageSize)
.getResultList();
~~~

Sau đó lấy graph cho page IDs:

~~~java
List<Order> orders = entityManager.createQuery(
    """
    select distinct o
    from Order o
    left join fetch o.customer
    left join fetch o.lines
    where o.id in :ids
    """,
    Order.class
)
.setParameter("ids", ids)
.getResultList();
~~~

`IN` query không bảo đảm giữ thứ tự danh sách IDs; nếu thứ tự quan trọng, sắp xếp lại theo page ID sequence hoặc dùng query có thứ tự rõ ràng. Cũng cần xử lý IDs rỗng.

Một lựa chọn khác là DTO projection, nhất là khi trang chỉ cần vài fields.

## 12. Cách 2: dùng JPA EntityGraph

EntityGraph cho phép khai báo fetch plan mà không phải viết fetch join trong JPQL.

~~~java
@Entity
@NamedEntityGraph(
    name = "Order.detail",
    attributeNodes = {
        @NamedAttributeNode("customer"),
        @NamedAttributeNode(value = "lines", subgraph = "lineGraph")
    },
    subgraphs = {
        @NamedSubgraph(
            name = "lineGraph",
            attributeNodes = {
                @NamedAttributeNode("product")
            }
        )
    }
)
public class Order {
    // ...
}
~~~

Sử dụng graph:

~~~java
EntityGraph<?> graph = entityManager.getEntityGraph(
    "Order.detail"
);

Map<String, Object> hints = new HashMap<>();
hints.put("jakarta.persistence.fetchgraph", graph);

Order order = entityManager.find(
    Order.class,
    orderId,
    hints
);
~~~

Graph chỉ định attributes cần fetch cho operation đó. Với `fetchgraph`, attributes được liệt kê được xem là eager cho operation; attributes không liệt kê được xem là lazy theo graph semantics, dù provider có thể fetch thêm.

### Load graph và fetch graph

| Hint | Ý nghĩa tổng quát |
| --- | --- |
| `jakarta.persistence.fetchgraph` | Attributes được liệt kê là eager; phần còn lại được xem là lazy |
| `jakarta.persistence.loadgraph` | Attributes được liệt kê là eager; phần còn lại giữ mapping defaults |

EntityGraph là fetch plan, không phải cam kết provider phải dùng một SQL JOIN duy nhất.

## 13. Spring Data JPA với @EntityGraph

Nếu repository dùng Spring Data JPA:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @EntityGraph(attributePaths = {
        "customer",
        "lines",
        "lines.product"
    })
    Optional<Order> findDetailedById(Long id);
}
~~~

`@EntityGraph` trong ví dụ này là annotation của Spring Data JPA. Nó giúp khai báo associations cần fetch cho repository method.

Với list endpoint, hãy cẩn thận khi graph chứa collection và query có pagination. EntityGraph không xóa giới hạn row multiplication của collection fetching.

## 14. Cách 3: DTO projection để trả dữ liệu cần thiết

Một endpoint thường không cần trả entity đầy đủ. DTO projection chỉ lấy columns cần thiết.

~~~java
public record OrderSummary(
    Long id,
    String customerName,
    BigDecimal total
) {}
~~~

Query:

~~~java
List<OrderSummary> summaries = entityManager.createQuery(
    """
    select new com.example.store.api.OrderSummary(
        o.id,
        c.name,
        o.total
    )
    from Order o
    join o.customer c
    where o.status = :status
    order by o.createdAt desc
    """,
    OrderSummary.class
)
.setParameter("status", OrderStatus.OPEN)
.getResultList();
~~~

DTO không phải managed entity. Các values cần thiết được đưa vào DTO; serializer không phải truy cập proxy/collection lazy.

Ưu điểm:

- Chỉ chọn columns cần dùng.
- Không giữ graph entities trong L1 persistence context.
- Tránh accidental lazy loading trong JSON serialization.
- Dễ định nghĩa API contract.
- Giảm dữ liệu truyền qua JDBC và heap.
- Có thể tối ưu list/report queries riêng.

Với nested collection, có thể dùng hai query: một query lấy page Order summaries, một query lấy line DTOs theo danh sách Order IDs, rồi group chúng trong application layer.

## 15. Cách 4: map entity thành DTO khi Session còn mở

Nếu use case cần entity graph, vẫn có thể giữ mapping trong service transaction:

~~~java
@Service
public class OrderQueryService {

    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderDetailDto getDetail(Long id) {
        Order order = repository.findDetailedById(id)
            .orElseThrow();

        return new OrderDetailDto(
            order.getId(),
            order.getCustomer().getName(),
            order.getLines().stream()
                .map(line -> new OrderLineDto(
                    line.getProduct().getName(),
                    line.getQuantity()
                ))
                .toList()
        );
    }
}
~~~

Ở đây associations cần cho DTO phải được fetch trong transaction, ví dụ qua EntityGraph hoặc query phù hợp. Việc map DTO xảy ra **trước khi method transaction kết thúc**.

Controller nhận DTO:

~~~java
@GetMapping("/orders/{id}")
public OrderDetailDto detail(@PathVariable Long id) {
    return orderQueryService.getDetail(id);
}
~~~

Controller không phải điều hướng một graph entity lazy.

`@Transactional(readOnly = true)` không tự fetch association. Nó chỉ đặt transaction/read-only hints theo Spring/provider configuration; fetch plan vẫn cần được xác định.

## 16. Đặt transaction boundary đúng chỗ

Một nguyên nhân phổ biến là transaction kết thúc quá sớm:

~~~java
public Order loadOrder(Long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Nếu repository mở transaction riêng và method trả entity detached ra ngoài, code gọi có thể truy cập lazy association sau khi persistence context đóng.

Cách tốt hơn là tạo một service use case có transaction rõ ràng:

~~~java
@Transactional(readOnly = true)
public OrderDetailDto loadOrderDetail(Long id) {
    Order order = repository.findDetailedById(id)
        .orElseThrow();

    return mapper.toDetailDto(order);
}
~~~

Nguyên tắc:

- Transaction bắt đầu trước khi load dữ liệu.
- Fetch plan được chọn cho use case.
- Lazy associations cần thiết được đọc/map trong transaction.
- DTO/value objects rời khỏi service boundary.
- Session được đóng khi unit of work hoàn tất.
- Không truyền Session/EntityManager ra controller hoặc background thread.

Trong Spring proxy mode, method transactional phải được gọi qua proxy theo cách framework hỗ trợ. Self-invocation trong cùng bean có thể không kích hoạt transaction interceptor.

## 17. Vì sao không mở Session thủ công ở mọi nơi?

Một cách chữa tạm:

~~~java
Session session = sessionFactory.openSession();
// load entity, truy cập associations
session.close();
~~~

Nếu lifecycle được quản lý chính xác, Session mở sẽ cho phép lazy loading. Nhưng mở Session tùy tiện trong controller/mapper có thể tạo:

- Nhiều Sessions/transactions không đồng bộ.
- Connection lifecycle khó kiểm soát.
- Persistence contexts kéo dài.
- Không nhất quán với Spring transaction manager.
- Khó test và khó rollback.
- Connection leak nếu không close trong mọi exception path.

Với Spring Data JPA, ưu tiên transaction boundary ở service layer và để framework quản lý EntityManager. Native Hibernate app có thể tự quản Session, nhưng phải có unit-of-work lifecycle rõ.

## 18. Open Session in View (OSIV) có giải quyết không?

Open Session in View giữ EntityManager/Session mở trong suốt web request, có thể cho phép lazy loading khi controller hoặc JSON serializer truy cập association.

Điều này có thể làm một số LazyInitializationException biến mất, nhưng có trade-offs:

- Query có thể phát sinh trong lúc serialize response.
- Controller/serializer vô tình gây N+1.
- SQL không còn tập trung trong service transaction.
- Latency khó dự đoán.
- Session/persistence context sống lâu hơn.
- Database access có thể diễn ra sau transaction nghiệp vụ.
- Khó biết endpoint thực sự cần graph nào.

OSIV **không phải lời giải mặc định cho fetch planning**. Nó có thể phù hợp với một số ứng dụng web có policy rõ, nhưng không nên dựa vào nó để che mọi lazy access.

Với API cần kiểm soát query count và transaction boundaries, thường nên tắt OSIV sau khi chuyển sang DTO/fetch plan trong service. Nếu tắt, phải sửa những nơi đang lazy-load ngoài service trước.

## 19. Vì sao EAGER có thể làm lỗi biến mất nhưng tạo N+1?

Giả sử trang danh sách có 100 Orders. Developer đổi:

~~~java
@ManyToOne(fetch = FetchType.EAGER)
private Customer customer;
~~~

Màn hình hết exception vì Customer được load theo eager semantics. Nhưng Hibernate có thể chạy:

~~~text
SELECT ... FROM orders;
SELECT ... FROM customers WHERE id = ?;
SELECT ... FROM customers WHERE id = ?;
SELECT ... FROM customers WHERE id = ?;
...
~~~

Đó vẫn là N+1 nếu provider thực hiện secondary select cho từng Customer.

Một query cụ thể với fetch join thể hiện đúng ý định:

~~~java
select o from Order o join fetch o.customer
~~~

**EAGER thay đổi mapping default cho mọi use case; fetch join thay đổi fetch plan cho một query cụ thể.**

## 20. EAGER có thể làm tăng row multiplication

Nếu một root entity có nhiều to-many associations và các association được fetch trong cùng query, kết quả SQL có thể nhân rows.

~~~text
Order #100:
  8 lines
  3 payments
  4 notes

Join cả ba collections:
  8 × 3 × 4 = 96 rows tiềm năng
~~~

Dù Hibernate cuối cùng dựng một Order object, database vẫn xử lý rows và driver truyền dữ liệu lặp. Khi số associations lớn, memory và CPU hydration có thể tăng mạnh.

Không thay EAGER hàng loạt bằng JOIN FETCH hàng loạt. Cần chọn association theo màn hình và cardinality.

## 21. Sử dụng Hibernate.initialize() có chọn lọc

Trong một số trường hợp, code cần một lazy collection cụ thể nhưng không cần đổi query/mapping:

~~~java
Order order = entityManager.find(Order.class, orderId);

Hibernate.initialize(order.getLines());

List<OrderLine> lines = order.getLines();
~~~

`Hibernate.initialize()` phải được gọi khi collection/proxy còn gắn với Session mở. Nếu entity đã detached, gọi method này không thể tự tìm lại Session và thường vẫn ném LazyInitializationException.

Có thể kiểm tra trạng thái:

~~~java
boolean initialized =
    Hibernate.isInitialized(order.getLines());
~~~

Đây là Hibernate-specific API. Dùng cho một số trường hợp có chủ đích; không gọi initialize trong vòng lặp lớn nếu điều đó tạo N+1.

`Hibernate.initialize(collection)` khởi tạo collection itself; các associations bên trong từng element có thể vẫn lazy. Nếu DTO cần Product name của mỗi OrderLine, fetch Product hoặc map nó khi Session mở.

## 22. Batch fetching thay vì EAGER toàn cục

Khi cần load nhiều lazy associations cùng loại, Hibernate có thể batch fetching để giảm số SELECT.

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<OrderLine> lines;
~~~

Hoặc cấu hình default:

~~~properties
hibernate.default_batch_fetch_size=32
~~~

Thay vì một SELECT cho từng collection, Hibernate có thể gom identifiers vào một truy vấn batch theo khả năng/version/driver.

Batch fetching hữu ích khi associations chỉ được truy cập trong một số use cases. Nó giữ mapping lazy nhưng giảm round trips khi nhiều proxies/collections được khởi tạo.

Giá trị batch size cần benchmark. Quá lớn có thể tạo IN clause lớn hoặc tải nhiều dữ liệu hơn nhu cầu.

## 23. Fetch profiles và các cơ chế Hibernate khác

Hibernate còn có các cơ chế fetch plan riêng như fetch profiles và mapping-level fetch options. Chúng có thể hữu ích khi ứng dụng cần bật một nhóm associations theo use case.

Dù chọn cơ chế nào, nguyên tắc vẫn giống nhau:

- Xác định dữ liệu use case cần.
- Bật fetch plan tại operation phù hợp.
- Đo SQL và số rows.
- Giữ transaction/persistence context trong lúc mapping dữ liệu.
- Trả DTO khi không cần entity semantics ra ngoài.

Không bật nhiều fetch mechanisms chồng lên nhau mà không kiểm tra SQL cuối cùng.

## 24. To-one LAZY và bytecode enhancement

Với `@ManyToOne` hoặc `@OneToOne`, lazy loading có thể được thực hiện bằng proxy hoặc bytecode enhancement tùy mapping.

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id")
private Customer customer;
~~~

Khi truy cập `getCustomer()`, Hibernate có thể khởi tạo proxy nếu Session còn hoạt động.

Có những trường hợp provider cần biết association có tồn tại hay không, hoặc association inverse/optional làm proxy khó tạo. Bytecode enhancement có thể cải thiện khả năng lazy loading cho một số mappings.

Tuy nhiên:

- `LAZY` là hint theo Jakarta Persistence.
- Provider có thể fetch sớm hơn.
- Proxy/enhancement behavior tùy Hibernate version.
- Cần build enhancement đúng nếu dự án sử dụng nó.
- Không nên biến enhancement thành cách chữa entity graph trả ra API.

Kiểm tra SQL và runtime behavior trên mapping thật.

## 25. Không serialize entity graph trực tiếp ra JSON

Một controller trả entity:

~~~java
@GetMapping("/orders/{id}")
public Order get(@PathVariable Long id) {
    return repository.findById(id).orElseThrow();
}
~~~

JSON serializer có thể gọi getters:

~~~text
order.getCustomer()
order.getLines()
line.getProduct()
product.getCategory()
...
~~~

Nếu Session đã đóng, có thể ném LazyInitializationException. Nếu OSIV còn mở, serializer có thể tạo hàng loạt SQL và N+1.

Giải pháp API rõ ràng hơn:

~~~java
@GetMapping("/orders/{id}")
public OrderDetailDto get(@PathVariable Long id) {
    return orderQueryService.getDetail(id);
}
~~~

DTO chỉ chứa fields được phép public và đã được load theo fetch plan. Điều này giảm nguy cơ lộ fields nội bộ, vòng lặp serialization và query ngoài ý muốn.

## 26. Khi nào có thể dùng EAGER?

EAGER không phải lúc nào cũng sai. Nó có thể hợp lý khi:

- Association thực sự luôn cần cho hầu hết mọi lần load entity.
- Cardinality thấp, ổn định.
- Query plans được đo và không tạo N+1.
- Không kéo theo graph sâu ngoài ý muốn.
- Có integration tests chứng minh SQL và latency chấp nhận được.

Một association to-one nhỏ, gần như luôn cần, có thể phù hợp với EAGER trong một số domain. Nhưng default EAGER của `@ManyToOne`/`@OneToOne` không có nghĩa developer phải giữ default đó.

Với quan hệ có thể lớn như `@OneToMany`/`@ManyToMany`, LAZY thường là lựa chọn an toàn hơn để tránh tải collection không cần thiết.

## 27. Khi nào nên chọn từng giải pháp?

| Nhu cầu | Giải pháp thường phù hợp |
| --- | --- |
| Detail query cần một to-one | JOIN FETCH hoặc EntityGraph |
| Detail query cần một collection nhỏ | JOIN FETCH/EntityGraph, đo row count |
| List page cần vài fields | DTO projection |
| List page cần to-one name | DTO join hoặc fetch join to-one |
| List page cần collection | Page IDs rồi fetch, hoặc DTO query riêng |
| Một collection cần khởi tạo có chủ đích | Hibernate.initialize trong Session |
| Nhiều lazy collections cùng loại được truy cập | Batch fetching |
| Entity được dùng ngoài transaction | Map sang DTO/value object trước khi detach |
| Legacy web app đang phụ thuộc OSIV | Chuyển dần fetch logic vào service boundary |
| Association luôn nhỏ và luôn cần | Có thể cân nhắc EAGER sau khi đo |

## 28. Ví dụ hoàn chỉnh: entity LAZY, query chọn graph

Mapping:

~~~java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(
        mappedBy = "order",
        fetch = FetchType.LAZY
    )
    private List<OrderLine> lines = new ArrayList<>();

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public List<OrderLine> getLines() {
        return lines;
    }
}
~~~

Repository:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @EntityGraph(attributePaths = {
        "customer",
        "lines",
        "lines.product"
    })
    Optional<Order> findDetailedById(Long id);
}
~~~

DTO:

~~~java
public record OrderDetailDto(
    Long id,
    String customerName,
    List<OrderLineDto> lines
) {}

public record OrderLineDto(
    String productName,
    int quantity
) {}
~~~

Service:

~~~java
@Service
public class OrderQueryService {

    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderDetailDto getDetail(Long id) {
        Order order = repository.findDetailedById(id)
            .orElseThrow();

        List<OrderLineDto> lines = order.getLines().stream()
            .map(line -> new OrderLineDto(
                line.getProduct().getName(),
                line.getQuantity()
            ))
            .toList();

        return new OrderDetailDto(
            order.getId(),
            order.getCustomer().getName(),
            lines
        );
    }
}
~~~

Repository fetch plan đảm bảo associations được yêu cầu trong transaction. Service map sang DTO trước khi persistence context đóng. Entity mappings vẫn LAZY cho các use cases khác.

## 29. Ví dụ list endpoint bằng DTO projection

Một trang danh sách có thể không cần Order entity:

~~~java
public record OrderListItem(
    Long id,
    String customerName,
    Instant createdAt,
    BigDecimal total
) {}
~~~

Query:

~~~java
@Query(
    """
    select new com.example.store.api.OrderListItem(
        o.id,
        c.name,
        o.createdAt,
        o.total
    )
    from Order o
    join o.customer c
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """
)
Page<OrderListItem> findSummaryPage(
    OrderStatus status,
    Pageable pageable
);
~~~

Spring Data có thể tạo count query hoặc cần khai báo count query tùy JPQL/complexity. DTO projection giúp list endpoint không hydrate OrderLines, Payments hoặc graph không cần.

Nếu customer là optional, dùng `left join` thay `join` và constructor DTO phù hợp.

## 30. Một số lỗi trong cách xử lý vội

### Anti-pattern A: đổi tất cả sang EAGER

~~~java
@ManyToOne(fetch = FetchType.EAGER)
private Customer customer;

@OneToMany(fetch = FetchType.EAGER)
private List<OrderLine> lines;
~~~

Tải dữ liệu không cần cho mọi use case, có nguy cơ N+1 và graph lớn.

### Anti-pattern B: bật OSIV chỉ để exception biến mất

~~~properties
spring.jpa.open-in-view=true
~~~

Có thể che lỗi transaction boundary và làm query chạy trong serialization. Nếu giữ OSIV, phải hiểu và kiểm soát query lifecycle.

### Anti-pattern C: gọi getter ngoài Session

~~~java
Order order = service.findOrder(id);
return order.getLines().size();
~~~

Entity đã detached và collection chưa initialized.

### Anti-pattern D: initialize mọi association bằng vòng lặp

~~~java
for (Order order : orders) {
    Hibernate.initialize(order.getCustomer());
    Hibernate.initialize(order.getLines());
}
~~~

Có thể biến thành N+1. Hãy dùng batch fetch, graph hoặc query phù hợp.

### Anti-pattern E: merge detached entity chỉ để lấy lazy data

`merge()` copy state của detached entity vào một managed instance. Nó không phải API fetch plan để nạp mọi association. Hãy query lại entity với fetch plan đúng.

### Anti-pattern F: giữ Session sống vô hạn

Mở Session dài hạn để mọi proxy luôn có thể lazy-load sẽ làm persistence context lớn, giữ references và tạo concurrency/lifecycle issues.

## 31. Chẩn đoán LazyInitializationException

Khi gặp exception, tìm association và thời điểm truy cập:

1. Stack trace chỉ ra proxy/entity type nào?
2. Collection/association nào chưa được initialized?
3. Entity được load ở service/repository nào?
4. Transaction đã kết thúc ở đâu?
5. Session có bị đóng, clear hoặc detach trước khi getter chạy không?
6. Getter được gọi bởi controller, mapper, template hay JSON serializer?
7. Có OSIV hay không?
8. Use case thật sự cần association đó không?

Ví dụ:

~~~text
failed to lazily initialize a collection of role:
com.example.Order.lines
could not initialize proxy - no Session
~~~

Điều này cho biết `Order.lines` chưa được khởi tạo khi code truy cập và Session không còn khả dụng.

Không bắt exception rồi trả list rỗng. Điều đó biến lỗi fetch/lifecycle thành response sai dữ liệu.

## 32. Kiểm tra association đã được load chưa

Hibernate:

~~~java
boolean loaded = Hibernate.isInitialized(order.getLines());
~~~

Jakarta Persistence:

~~~java
boolean loaded = entityManagerFactory
    .getPersistenceUnitUtil()
    .isLoaded(order, "lines");
~~~

Các API này hữu ích cho diagnostics/tests. Đừng dùng chúng để điều khiển business logic kiểu “nếu chưa load thì bỏ qua dữ liệu”; use case nên khai báo rõ dữ liệu cần.

`PersistenceUnitUtil.isLoaded` có overload kiểm tra entity và attribute; semantics cụ thể theo Jakarta Persistence API.

## 33. Test query count để phát hiện EAGER/N+1

Một bài test nên kiểm tra không chỉ response đúng mà cả số SQL statements.

Với Hibernate Statistics:

~~~java
Statistics statistics = sessionFactory.getStatistics();

statistics.clear();

orderQueryService.getDetail(orderId);

long statements = statistics.getPrepareStatementCount();
~~~

Con số kỳ vọng phụ thuộc test setup, cache state, provider version và fetch plan. Không hard-code threshold chung cho mọi use case; xác định baseline có ý nghĩa cho query cụ thể.

Đối với danh sách 50 Orders, hãy test:

- Số statements có tăng tuyến tính theo số Orders không?
- Có một SELECT riêng cho mỗi Customer không?
- Collection fetch có tạo quá nhiều rows không?
- DTO projection có chỉ lấy columns cần không?
- SQL count có ổn định khi tăng page size không?

Có thể dùng datasource proxy hoặc SQL capture trong integration tests để quan sát query thực tế.

## 34. Test sau khi tắt OSIV

Nếu application định tắt OSIV, integration test nên mô phỏng đúng lifecycle:

1. Gọi service transaction.
2. Service trả DTO hoặc entity theo contract.
3. Transaction kết thúc và persistence context đóng.
4. Serialize response hoặc truy cập object ngoài service.
5. Xác nhận không có lazy loading bất ngờ.
6. Xác nhận response vẫn có đầy đủ fields cần thiết.

Một test chỉ chạy repository method bên trong transaction test có thể che mất lỗi vì test framework giữ persistence context lâu hơn request thực.

## 35. Batch fetching không thay thế fetch plan

Giả sử endpoint load 100 Orders, rồi truy cập Customer của mỗi Order. Batch fetching có thể gom lazy loads thành một số queries thay vì 100 queries.

Nhưng nếu endpoint chỉ cần customer name, DTO query có thể hiệu quả hơn vì:

- Không tạo 100 Order entity instances nếu không cần.
- Không giữ Customer entities trong L1.
- Chỉ lấy ID/name cần dùng.
- Query shape dễ tối ưu.

Batch fetching là công cụ giảm round trips khi cần lazy associations, không phải lý do để bỏ qua use-case fetch design.

## 36. EntityGraph không đảm bảo một SQL duy nhất

EntityGraph yêu cầu provider load attributes đã chỉ định theo graph semantics. Provider vẫn có quyền chọn SQL fetch strategy phù hợp.

Sau khi thêm EntityGraph, cần đo số SQL statements, rows trả về, kích thước result set, hydration time, memory impact, pagination behavior, query plan và index usage.

Nếu EntityGraph gồm nhiều to-many collections, nó vẫn có thể gây row multiplication hoặc secondary selects. Không coi graph là annotation “bật hiệu năng”.

## 37. LazyInitializationException trong mapper và serializer

Mapper có thể vô tình gọi lazy getters:

~~~java
OrderDto toDto(Order order) {
    return new OrderDto(
        order.getId(),
        order.getCustomer().getName(),
        order.getLines().stream()
            .map(line -> line.getProduct().getName())
            .toList()
    );
}
~~~

Mapper này chỉ an toàn nếu tất cả associations cần thiết được load khi Session còn mở.

Nếu mapper được gọi sau transaction, có thể ném LazyInitializationException. Đặt mapper trong transactional service hoặc dùng projection query để tạo DTO trực tiếp.

Các thư viện mapping như MapStruct không tự làm lazy associations an toàn; generated code vẫn gọi getters.

## 38. Lazy loading và serialization vòng lặp

Bidirectional mapping:

~~~java
class Order {
    private Customer customer;
}

class Customer {
    private List<Order> orders;
}
~~~

JSON serialization có thể đi:

~~~text
Order -> Customer -> Orders -> Customer -> Orders -> ...
~~~

Điều này có thể gây recursion, tải graph quá lớn hoặc lộ dữ liệu không mong muốn.

DTO cho phép chọn hướng và depth của response. Jackson annotations như ignore/back-reference có thể xử lý một số serialization cycles, nhưng không thay fetch planning và API model.

## 39. Những gì không nên làm khi nhận lỗi

| Phản ứng vội | Vấn đề |
| --- | --- |
| Đổi tất cả associations sang EAGER | Tải graph rộng và tạo query overhead |
| Bật OSIV mà không đo | Lazy queries chạy trong view/serialization |
| Catch exception rồi trả empty collection | Che lỗi và trả dữ liệu sai |
| Mở Session global | Không thread-safe, persistence context phình |
| Gọi initialize cho mọi entity trong loop | Có thể tạo N+1 |
| Merge detached object để fetch | Không phải fetch plan |
| Serialize entity trực tiếp | Trigger lazy load/cycles |
| Tắt transaction management | Không giải quyết persistence lifecycle |

## 40. Quy trình xử lý đúng

~~~text
LazyInitializationException
          |
          v
Xác định association chưa initialized
          |
          v
Tìm nơi Session/transaction kết thúc
          |
          v
Use case cần dữ liệu association đó?
          |
      +---+---+
      |       |
     Không    Có
      |       |
      v       v
Bỏ việc      Chọn fetch plan
truy cập     JOIN FETCH / EntityGraph
             DTO projection / batch
                 |
                 v
             Map DTO trong transaction
                 |
                 v
             Session đóng đúng scope
                 |
                 v
             Test SQL count và response
~~~

Các bước:

1. Đọc stack trace để xác định association.
2. Xác định use case có cần association hay không.
3. Nếu không cần, loại bỏ getter/access trong mapper/serializer.
4. Nếu cần, tải association trong transaction bằng fetch plan phù hợp.
5. Nếu chỉ cần vài fields, dùng DTO projection.
6. Map entity sang DTO trước khi Session đóng.
7. Đo SQL count và result size để tránh N+1/row multiplication.
8. Kiểm thử với OSIV disabled nếu đó là kiến trúc mục tiêu.

## 41. Association rất lớn cần được phân trang

Nếu một Order có hàng trăm nghìn OrderLines, việc load toàn bộ collection không hợp lý dù Session đang mở và không có exception.

Thay vì:

~~~java
order.getLines().forEach(this::process);
~~~

có thể query theo page/chunk:

~~~java
List<OrderLineRow> page = entityManager.createQuery(
    """
    select new com.example.OrderLineRow(
        line.id,
        line.productName,
        line.quantity
    )
    from OrderLine line
    where line.order.id = :orderId
      and line.id > :lastId
    order by line.id
    """,
    OrderLineRow.class
)
.setParameter("orderId", orderId)
.setParameter("lastId", lastId)
.setMaxResults(500)
.getResultList();
~~~

Đây là ví dụ projection minh họa; constructor/type phải khớp entity thực tế. Dữ liệu lớn nên được xử lý theo pages thay vì initialize toàn bộ collection chỉ để tránh lazy exception.

## 42. Fetching và transaction consistency

Fetch plan rộng hơn cũng có thể thay đổi thời điểm đọc dữ liệu. Nếu association được tải bằng secondary SELECTs trong transaction có isolation nhất định, các reads có thể quan sát database state theo semantics của isolation level.

Không giả định join và nhiều SELECT luôn có consistency giống nhau ở mọi isolation level/database.

Với use case cần snapshot consistency, hãy chọn transaction isolation và query strategy dựa trên business requirement. EAGER không phải công cụ đảm bảo consistency.

## 43. Performance trade-offs của các lựa chọn

| Cách làm | Ưu điểm | Rủi ro/giới hạn |
| --- | --- | --- |
| Mapping EAGER | Association được yêu cầu sớm | Áp dụng rộng, secondary selects/N+1 |
| JOIN FETCH to-one | SQL rõ, ít round trips | Có thể tăng row width |
| JOIN FETCH to-many | Lấy collection trong query | Row multiplication, pagination khó |
| EntityGraph | Fetch plan tách khỏi JPQL | Provider vẫn chọn SQL strategy |
| DTO projection | Chỉ lấy columns cần, không L1 entity graph | Không có managed entity semantics |
| Batch fetching | Giảm số lazy-load queries | Có thể vẫn tải entities không cần |
| Hibernate.initialize | Chủ động load một proxy/collection | Phải có Session; loop dễ N+1 |
| OSIV | Cho phép lazy access trong request | Query muộn, khó kiểm soát |
| Transaction service + DTO | Boundary rõ, response ổn định | Cần thiết kế DTO/fetch query |

## 44. So sánh ba endpoint

### Endpoint A: Order summary

Chỉ cần ID, ngày và Customer name. DTO projection là lựa chọn tự nhiên:

~~~java
select new OrderSummary(o.id, o.createdAt, c.name)
from Order o
join o.customer c
where o.status = :status
~~~

### Endpoint B: Order detail

Cần Customer và Lines. Dùng EntityGraph hoặc fetch join có chọn lọc, map DTO trong transaction.

### Endpoint C: Export hàng triệu OrderLines

Không load một graph Order với toàn bộ Lines. Dùng keyset pagination/DTO/JDBC streaming theo chunk, giữ Session/transaction phù hợp và theo dõi memory.

Cùng một entity model có thể có ba fetch plans khác nhau. Đó là lý do mapping EAGER toàn cục thường không phù hợp.

## 45. Checklist thiết kế fetch plan

- Association có thực sự cần trong use case không?
- Cần toàn entity hay chỉ một vài scalar fields?
- Cardinality là to-one hay to-many?
- Có thể dùng DTO projection không?
- Nếu dùng fetch join, result rows có bị nhân nhiều không?
- Có paginate collection fetch join không?
- EntityGraph có tải graph quá sâu không?
- Có N+1 secondary selects không?
- DTO có được map trong transaction không?
- Controller/serializer có gọi lazy getters không?
- Session có bị chia sẻ hoặc kéo dài không?
- OSIV có đang che query ngoài service không?
- Batch fetching có phù hợp access pattern không?
- SQL count/row count/latency đã được đo chưa?

## 46. Bài tập tự kiểm tra

**1. LazyInitializationException thường xuất hiện khi nào?** Khi code truy cập proxy/collection chưa khởi tạo nhưng không còn Session khả dụng.

**2. Đổi mọi association sang EAGER có phải cách sửa tốt?** Không; có thể tải quá nhiều dữ liệu và gây N+1.

**3. EAGER có đồng nghĩa JOIN không?** Không; provider có thể dùng secondary selects.

**4. Default của @ManyToOne là gì?** EAGER.

**5. Default của @OneToMany là gì?** LAZY.

**6. @OneToOne LAZY có luôn được đảm bảo không?** LAZY là hint; behavior phụ thuộc provider/mapping/enhancement.

**7. Nếu chỉ cần Customer name trong list, nên dùng gì?** DTO projection hoặc query fetch to-one có kiểm soát.

**8. JOIN FETCH collection có thể gây vấn đề gì?** Row multiplication và pagination không đúng/khó.

**9. EntityGraph có bắt buộc một SQL JOIN không?** Không.

**10. Hibernate.initialize có dùng sau khi Session đóng được không?** Không, proxy/collection cần Session để khởi tạo.

**11. Batch fetching có giải quyết mọi N+1 không?** Không; nó giảm một số lazy-load round trips theo access pattern.

**12. OSIV có thể che lỗi không?** Có, nhưng có thể đẩy SQL vào controller/serialization.

**13. Có nên serialize entity trực tiếp?** Thường không; DTO kiểm soát response và fetch boundary tốt hơn.

**14. @Transactional(readOnly=true) tự fetch association không?** Không; cần fetch plan riêng.

**15. MapStruct có tự giải quyết lazy loading không?** Không; generated mapper vẫn gọi getters.

**16. Detached entity có đọc được field đã load không?** Có; association chưa initialized có thể không truy cập được.

**17. merge có phải cách fetch association không?** Không; merge copy state vào managed instance.

**18. Làm sao kiểm tra association đã initialized?** Hibernate.isInitialized hoặc PersistenceUnitUtil.isLoaded.

**19. Cần test gì để phát hiện EAGER gây N+1?** SQL statement count khi tăng số root entities.

**20. Với collection rất lớn, cách nào hợp lý?** DTO/keyset pagination hoặc chunk processing, không initialize toàn bộ graph.

## 47. Tổng kết

Dùng `FetchType.EAGER` cho mọi quan hệ chỉ để làm biến mất `LazyInitializationException` là một anti-pattern phổ biến. Nó thay đổi fetch behavior trên toàn mapping, có thể kéo theo nhiều SQL phụ, N+1, row multiplication, object graph lớn và memory pressure. Nó cũng không đảm bảo mọi association sâu đều được khởi tạo.

Cách xử lý bền vững:

1. Hiểu LazyInitializationException là truy cập dữ liệu lazy khi không còn Session khả dụng.
2. Giữ mapping lazy ở những association không phải lúc nào cũng cần; khai báo fetch type rõ ràng.
3. Chọn dữ liệu theo use case bằng JOIN FETCH, EntityGraph hoặc DTO projection.
4. Giữ transaction/service boundary đủ để load và map dữ liệu cần thiết.
5. Trả DTO/value objects ra controller thay vì serialize entity graph.
6. Dùng batch fetching hoặc Hibernate.initialize có chọn lọc khi phù hợp.
7. Không paginate trực tiếp với collection fetch join nếu chưa xử lý row multiplication.
8. Coi OSIV là một policy có trade-offs, không phải cách chữa mặc định.
9. Đo SQL count, result rows, heap và latency để phát hiện N+1/overfetch.
10. Với collections rất lớn, xử lý bằng pages/chunks thay vì load cả graph.

**Mục tiêu là tải đúng dữ liệu, đúng thời điểm, trong đúng transaction.** Khi fetch plan được thiết kế theo use case, ứng dụng vừa tránh được lazy access ngoài Session, vừa giữ hiệu năng và memory usage có thể dự đoán.

## Tài liệu tham khảo

- [Jakarta Persistence 3.2 Specification — Fetching and entity graphs](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2)
- [Jakarta Persistence 3.1 Specification](https://jakarta.ee/specifications/persistence/3.1/)
- [Hibernate ORM 6.6 User Guide — Fetching](https://docs.hibernate.org/orm/6.6/userguide/html_single/)
- [Hibernate ORM 7.2 User Guide — Fetching](https://docs.hibernate.org/orm/7.2/userguide/html_single/)
- [Hibernate ORM 7.2 Javadocs — LazyInitializationException](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/LazyInitializationException.html)
- [Hibernate ORM 6.6 Javadocs — Hibernate.initialize](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/Hibernate.html)
- [Spring Data JPA — EntityGraph](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Framework — Declarative transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
