# FetchType, proxy và thời điểm truy cập quan hệ trong Spring Data JPA

Trong JPA, quan hệ giữa các entity có thể được nạp cùng entity gốc hoặc chỉ được nạp khi ứng dụng thật sự truy cập. Hai chiến lược chính là **EAGER** và **LAZY**. Hibernate thường dùng proxy cho tham chiếu entity và collection wrapper để trì hoãn việc đọc dữ liệu. Cơ chế này giúp tránh tải cả object graph khi không cần, nhưng cũng tạo ra các vấn đề như N+1 query hoặc LazyInitializationException nếu quan hệ được truy cập sau khi PersistenceContext đã đóng.

Điểm quan trọng: FetchType mô tả yêu cầu về thời điểm dữ liệu phải sẵn sàng, không quy định duy nhất một câu SQL hay bắt buộc provider phải dùng JOIN. Muốn kiểm soát dữ liệu cho một use case, hãy thiết kế fetch plan bằng fetch join, EntityGraph, batch fetching hoặc DTO projection; đồng thời kiểm tra SQL thực tế.

Tài liệu dùng Jakarta Persistence trong Spring Boot 3 trở lên và Hibernate làm ví dụ provider. Các chi tiết như proxy, batch fetching và SQL sinh ra có thể khác giữa provider và phiên bản.

## 1. FetchType là gì?

JPA định nghĩa hai giá trị:

- **FetchType.EAGER**: provider phải cung cấp dữ liệu của thuộc tính khi entity được nạp theo ngữ nghĩa eager. Provider có thể dùng JOIN, secondary SELECT hoặc chiến lược khác.
- **FetchType.LAZY**: provider được phép trì hoãn việc nạp dữ liệu cho tới khi ứng dụng truy cập. Đây là một yêu cầu/hint trong mapping; provider có thể nạp sớm hơn khi cần để đáp ứng query hoặc giới hạn kỹ thuật.

Ví dụ:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderItem> items = new ArrayList<>();
```

Khi tải Order, ứng dụng có thể chưa cần Customer hoặc OrderItem. LAZY cho phép provider trì hoãn việc tải các quan hệ đó.

FetchType không đồng nghĩa với SQL JOIN. Một quan hệ EAGER vẫn có thể được tải bằng SELECT bổ sung. Một quan hệ LAZY có thể được tải trong câu query ban đầu nếu fetch plan hoặc query yêu cầu.

## 2. FetchType mặc định của các quan hệ JPA

Các mặc định quan trọng của Jakarta Persistence:

| Mapping | FetchType mặc định |
|---|---|
| @ManyToOne | EAGER |
| @OneToOne | EAGER |
| @OneToMany | LAZY |
| @ManyToMany | LAZY |
| @ElementCollection | LAZY |
| @Basic | EAGER |

Vì vậy, nếu không khai báo fetch, quan hệ to-one thường là EAGER, còn to-many thường là LAZY.

Ví dụ:

```java
@Entity
public class Order {
    @Id
    private Long id;

    @ManyToOne
    private Customer customer; // mặc định EAGER

    @OneToMany(mappedBy = "order")
    private List<OrderItem> items = new ArrayList<>(); // mặc định LAZY
}
```

Đối với quan hệ to-one, nhiều ứng dụng chủ động khai báo LAZY để tránh nạp mọi liên kết khi không cần. Tuy nhiên, LAZY trên to-one là một hint theo đặc tả; khả năng trì hoãn thực tế phụ thuộc provider và cấu hình enhancement/proxy.

Không nên dựa vào default. Khai báo FetchType tường minh giúp người đọc hiểu ý định mapping, nhưng fetch plan vẫn cần được quyết định theo từng truy vấn.

## 3. Entity proxy là gì?

Hibernate có thể đại diện một entity liên quan chưa được nạp bằng một **proxy**. Proxy giữ định danh cần thiết và trì hoãn việc lấy trạng thái đầy đủ cho tới khi ứng dụng cần dữ liệu.

Ví dụ:

```java
Order order = entityManager.find(Order.class, 100L);

Customer customer = order.getCustomer();
// Customer có thể là proxy chưa được khởi tạo.

String name = customer.getName();
// Truy cập thuộc tính cần dữ liệu có thể kích hoạt SELECT.
```

Nếu mapping customer là LAZY và provider có thể tạo proxy, Hibernate có thể chỉ biết ID của Customer lúc đầu. Khi gọi getter cần trạng thái thực, proxy được khởi tạo và provider đọc dữ liệu.

Proxy là một implementation object do provider quản lý, không phải một entity khác về mặt domain. Nó đại diện cho cùng entity identity trong PersistenceContext.

Không nên giả định mọi lần gọi method đều gây query. Với Hibernate proxy thông thường, truy cập identifier thường không cần khởi tạo proxy; truy cập thuộc tính khác thường cần. Các trường hợp như composite identifier, bytecode enhancement, custom accessors và provider khác có thể thay đổi chi tiết. Hãy quan sát SQL để xác nhận.

## 4. Collection wrapper và lazy collection

Với quan hệ to-many, Hibernate thường không tạo proxy cho từng collection theo cách của to-one. Thay vào đó, nó thay collection bằng một wrapper triển khai interface List, Set hoặc Collection để theo dõi trạng thái và trì hoãn tải các phần tử.

Ví dụ:

```java
Order order = entityManager.find(Order.class, 100L);

List<OrderItem> items = order.getItems();
// Collection có thể chưa được khởi tạo.

int size = items.size();
// Thao tác này có thể kích hoạt SELECT lấy collection.
```

Các thao tác có thể khởi tạo lazy collection gồm:

- Duyệt bằng for-each hoặc iterator.
- Gọi stream hoặc chuyển collection sang array.
- Truy cập phần tử theo index.
- Gọi size/contains tùy loại collection và chiến lược provider.
- Serialize object graph hoặc gọi toString có duyệt collection.

Một số cấu hình Hibernate hỗ trợ extra-lazy behavior cho một số thao tác collection, nhưng không nên giả định size/contains luôn chỉ chạy một câu COUNT. Hãy kiểm tra SQL trong cấu hình thực tế.

Đừng thay wrapper do Hibernate quản lý bằng một collection mới một cách tùy tiện sau khi entity đã managed. Việc thay collection có thể ảnh hưởng dirty checking, orphan removal và trạng thái association.

## 5. Thời điểm truy cập và khởi tạo quan hệ

Một lazy association thường được khởi tạo khi:

1. Entity gốc đã được nạp trong PersistenceContext.
2. Ứng dụng truy cập thuộc tính quan hệ.
3. Provider còn khả năng truy cập PersistenceContext/session phù hợp.
4. Provider thực hiện SELECT để lấy trạng thái hoặc collection.

Ví dụ:

```java
@Transactional(readOnly = true)
public OrderSummary getOrder(Long id) {
    Order order = orderRepository.findById(id)
        .orElseThrow();

    String customerName = order.getCustomer().getName();
    int itemCount = order.getItems().size();

    return new OrderSummary(
        order.getId(),
        customerName,
        itemCount
    );
}
```

Trong transaction này, PersistenceContext thường còn mở khi code truy cập customer và items, nên lazy loading có thể thực hiện được.

Tuy nhiên, transaction còn mở không có nghĩa mọi truy vấn đều tối ưu. Nếu service lặp qua 100 Order và mỗi lần truy cập customer/items đều tạo query riêng, ứng dụng có thể gặp N+1. Cần chọn fetch plan để lấy dữ liệu theo số query phù hợp.

## 6. LazyInitializationException và entity detached

Khi PersistenceContext đã đóng, entity không còn managed. Một proxy hoặc collection chưa được khởi tạo có thể không còn khả năng tải dữ liệu.

Ví dụ:

```java
Order order;

try (EntityManager entityManager =
         entityManagerFactory.createEntityManager()) {
    order = entityManager.find(Order.class, 100L);
}

// EntityManager đã đóng.
// Nếu items chưa được khởi tạo:
int count = order.getItems().size();
```

Với Hibernate, truy cập lazy association sau khi session đóng thường gây LazyInitializationException.

Các tình huống thường gặp:

- Service trả entity ra controller rồi controller mới truy cập quan hệ.
- Jackson serialize entity và đi qua lazy getter sau transaction.
- Lưu entity vào cache rồi đọc quan hệ sau khi PersistenceContext kết thúc.
- Async task nhận entity detached và truy cập association.
- Test đóng EntityManager trước khi assert dữ liệu quan hệ.

Giải pháp tốt thường là tải đúng dữ liệu trong transaction/service rồi trả DTO. Có thể dùng fetch join hoặc EntityGraph để lấy association cần thiết. Không nên mở session vô thời hạn chỉ để che lỗi thiết kế fetch.

## 7. N+1 query problem

N+1 xảy ra khi một query lấy N entity gốc, sau đó ứng dụng phát sinh thêm một query cho mỗi entity khi truy cập quan hệ lazy hoặc eager được tải bằng SELECT.

Ví dụ:

```java
List<Order> orders = orderRepository.findAll();

for (Order order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

SQL có thể có dạng:

```sql
select * from orders;

select * from customer where id = ?;
select * from customer where id = ?;
select * from customer where id = ?;
-- tiếp tục cho từng Order
```

Nếu có 100 Order và mỗi Customer chưa có trong first-level cache, tổng query có thể xấp xỉ 1 + 100. Cache hoặc trùng association có thể làm số query thực tế thấp hơn, nhưng pattern vẫn có nguy cơ N+1.

N+1 không chỉ xảy ra với LAZY. Quan hệ EAGER cũng có thể bị provider tải bằng SELECT riêng cho từng entity nếu query không fetch chúng hiệu quả.

Cách xử lý phụ thuộc use case:

- Fetch join để lấy quan hệ cần thiết trong query.
- EntityGraph để định nghĩa fetch plan cho method.
- Batch fetching để gom nhiều lazy initialization vào một số query IN.
- DTO projection để chỉ lấy dữ liệu cần trả.
- Chia query theo hai bước nếu cần phân trang entity gốc và tải collection.

## 8. JPQL JOIN FETCH

Fetch join yêu cầu provider tải association trong cùng query JPQL:

```java
@Query("""
    select o
    from Order o
    join fetch o.customer
    where o.id = :id
    """)
Optional<Order> findWithCustomer(@Param("id") Long id);
```

Với collection:

```java
@Query("""
    select distinct o
    from Order o
    left join fetch o.items
    where o.id = :id
    """)
Optional<Order> findWithItems(@Param("id") Long id);
```

- `join fetch` thường chỉ lấy entity có association khớp.
- `left join fetch` vẫn giữ entity gốc ngay cả khi association không có.
- Fetch join nạp association vào entity graph đang được quản lý.
- Fetch join không thay đổi mapping FetchType của entity; nó chỉ thay fetch plan của query này.

Với collection, JOIN tạo nhiều hàng SQL cho một entity cha. DISTINCT giúp biểu đạt mong muốn lấy root entity duy nhất trong kết quả JPQL. Cách provider loại trùng và SQL thực tế phụ thuộc phiên bản; Hibernate 6 có xử lý loại trùng root entity khi fetch collection trong nhiều trường hợp, nhưng vẫn cần kiểm tra dữ liệu và query.

Không fetch mọi association theo thói quen. Fetch join nhiều collection có thể tạo tích Descartes lớn, tăng dữ liệu truyền và memory. Hibernate có thể ném MultipleBagFetchException khi cố fetch đồng thời nhiều bag collection.

## 9. Fetch join và phân trang

Fetch join collection kết hợp với pagination là tình huống cần đặc biệt cẩn trọng.

Ví dụ:

```java
@Query("""
    select distinct o
    from Order o
    left join fetch o.items
    where o.status = :status
    """)
Page<Order> findPageWithItems(
    @Param("status") OrderStatus status,
    Pageable pageable
);
```

Một Order có nhiều OrderItem nên một root có thể tạo nhiều hàng SQL. Database áp dụng LIMIT/OFFSET trên hàng JOIN, không phải lúc nào cũng tương đương phân trang trên tập Order duy nhất.

Tùy provider/version, Hibernate có thể cảnh báo và thực hiện pagination trong memory; cấu hình fail-on-pagination-over-collection-fetch có thể khiến truy vấn ném lỗi thay vì âm thầm tải quá nhiều dữ liệu. Đừng dựa vào hành vi pagination trên fetch join collection mà không kiểm tra.

Các cách an toàn hơn:

1. Phân trang ID của Order trước, không fetch collection.
2. Query thứ hai tải Order và items cho danh sách ID đó.
3. Dùng EntityGraph hoặc batch fetching nếu phù hợp, nhưng vẫn kiểm tra số query.
4. Trả DTO từ query được thiết kế rõ ràng nếu chỉ cần dữ liệu đọc.

Mẫu hai bước:

```java
Page<Long> ids = orderRepository.findIdsByStatus(
    status,
    pageable
);

List<Order> orders = ids.isEmpty()
    ? List.of()
    : orderRepository.findWithItemsByIdIn(ids.getContent());
```

Query thứ hai:

```java
@Query("""
    select distinct o
    from Order o
    left join fetch o.items
    where o.id in :ids
    """)
List<Order> findWithItemsByIdIn(@Param("ids") Collection<Long> ids);
```

Cần khôi phục thứ tự theo danh sách ID/page nếu thứ tự đầu vào quan trọng, vì IN query không bảo đảm giữ thứ tự của collection. Có thể sort lại trong service theo map vị trí ID hoặc đưa thứ tự vào query theo chiến lược phù hợp database.

## 10. EntityGraph: khai báo fetch plan theo use case

EntityGraph cho phép yêu cầu provider nạp một tập association cho một query mà không phải thay đổi FetchType trên mapping entity.

Spring Data JPA hỗ trợ `@EntityGraph`:

```java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @EntityGraph(attributePaths = {"customer", "items"})
    Optional<Order> findWithCustomerAndItemsById(Long id);
}
```

`attributePaths` dùng property path của entity. Spring Data tạo dynamic entity graph cho method đó.

Có thể dùng named entity graph:

```java
@Entity
@NamedEntityGraph(
    name = "Order.withCustomer",
    attributeNodes = @NamedAttributeNode("customer")
)
public class Order {
    @Id
    private Long id;
}
```

Repository:

```java
@EntityGraph(value = "Order.withCustomer")
Optional<Order> findById(Long id);
```

JPA phân biệt hai kiểu graph:

- **FETCH graph:** thuộc tính được liệt kê được xem là eager cho query; thuộc tính không liệt kê được xem là lazy theo graph semantics. Provider vẫn có thể lấy thêm dữ liệu.
- **LOAD graph:** thuộc tính được liệt kê được xem là eager; thuộc tính không liệt kê giữ fetch behavior mặc định trong mapping.

EntityGraph mô tả dữ liệu cần sẵn sàng, không bảo đảm SQL phải là một JOIN duy nhất. Provider có thể dùng JOIN hoặc SELECT bổ sung. Hãy kiểm tra SQL và số query.

## 11. Batch fetching

Batch fetching giảm N+1 bằng cách gom nhiều proxy/collection chưa khởi tạo vào một query có điều kiện IN.

Ví dụ Hibernate:

```java
@Entity
public class Order {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @BatchSize(size = 25)
    private Customer customer;
}
```

Hoặc cấu hình mặc định ở cấp session factory:

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=25
```

Khi ứng dụng truy cập một proxy, Hibernate có thể lấy cùng lúc một nhóm proxy cùng loại đang chờ trong persistence context. Thay vì 100 query cho 100 Customer, có thể chỉ cần một số query với IN list theo batch size.

Batch fetching:

- Là tính năng Hibernate, không phải annotation chuẩn JPA.
- Không biến quan hệ thành eager.
- Chỉ gom các proxy/collection phù hợp đang có trong context.
- Có thể chịu giới hạn số bind parameter và hành vi database.
- Không bảo đảm luôn đúng một query cho toàn bộ dữ liệu.

Chọn batch size dựa trên số lượng association, giới hạn parameter của database và đo hiệu năng. Batch fetching hữu ích khi cần duyệt nhiều association lazy nhưng không muốn fetch join làm phình kết quả.

## 12. Subselect fetching

Hibernate hỗ trợ subselect fetching cho collection trong một số mapping/cấu hình. Thay vì query riêng cho từng parent, provider có thể tải collection của nhóm parent đã được truy vấn bằng một câu SELECT phụ có subquery tương ứng.

Ví dụ annotation Hibernate:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<OrderItem> items = new ArrayList<>();
```

Subselect fetching là tính năng provider-specific. Nó có thể giảm N+1 khi tải collection của một nhóm parent, nhưng cũng có thể nạp nhiều dữ liệu hơn nhu cầu nếu PersistenceContext chứa nhiều parent. Hãy đo query và memory, không áp dụng đại trà.

## 13. DTO projection để tránh tải object graph

Nếu API chỉ cần một vài trường, DTO projection thường là cách hiệu quả và rõ ràng hơn việc tải entity rồi truy cập association.

Ví dụ:

```java
public record OrderSummary(
    Long id,
    String customerName,
    long itemCount
) {
}
```

JPQL:

```java
@Query("""
    select new com.example.order.OrderSummary(
        o.id,
        c.name,
        count(i)
    )
    from Order o
    join o.customer c
    left join o.items i
    where o.status = :status
    group by o.id, c.name
    order by o.id
    """)
List<OrderSummary> findSummaries(
    @Param("status") OrderStatus status
);
```

DTO được tạo từ kết quả query; không cần khởi tạo entity association để controller serialize. Query phải group đúng theo các biểu thức được chọn và package/constructor phải khớp.

DTO projection đặc biệt phù hợp cho read-only API, báo cáo và danh sách có số lượng trường cố định. Nếu cần cập nhật entity hoặc sử dụng domain behavior, load entity managed trong transaction.

## 14. Open Session in View (OSIV)

Spring Boot có thể cấu hình Open Session in View để giữ EntityManager/Session mở trong suốt HTTP request, cho phép lazy loading trong giai đoạn render/serialize response.

Điều này có thể làm LazyInitializationException ít xuất hiện hơn, nhưng dễ che giấu truy vấn phát sinh trong controller hoặc serializer. Một API trả danh sách 100 entity có thể phát sinh hàng trăm query khi JSON serializer đi qua quan hệ lazy.

Các rủi ro:

- SQL phát sinh ngoài service transaction boundary.
- N+1 khó nhận ra vì query xảy ra trong serialization.
- Response time phụ thuộc object graph mà serializer duyệt.
- Logic truy cập database bị phân tán giữa service, controller và serializer.

Cân nhắc tắt OSIV và tải dữ liệu cần thiết trong service bằng DTO/fetch plan rõ ràng. Nếu giữ OSIV vì lý do kiến trúc, vẫn phải kiểm soát query count và tránh serialize entity graph tùy tiện.

Trong Spring Boot, cấu hình thường gặp:

```properties
spring.jpa.open-in-view=false
```

Kiểm tra giá trị mặc định và warning theo phiên bản Spring Boot đang dùng; cấu hình tường minh giúp thể hiện quyết định của ứng dụng.

## 15. Transaction boundary và read-only

Lazy loading thường cần PersistenceContext còn mở. Service-level transaction giúp xác định rõ thời gian entity được quản lý:

```java
@Service
public class OrderQueryService {

    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderSummary getSummary(Long id) {
        Order order = repository.findWithCustomerAndItemsById(id)
            .orElseThrow();

        return new OrderSummary(
            order.getId(),
            order.getCustomer().getName(),
            order.getItems().size()
        );
    }
}
```

Service tải đúng association trong transaction rồi chuyển sang DTO. Controller nhận DTO và không cần truy cập lazy proxy.

`readOnly = true` là hint/transaction optimization theo transaction manager/provider; nó không tự biến mọi entity thành immutable và không thay thế fetch plan. Không dùng read-only annotation để giải quyết N+1.

## 16. Proxy, equals, hashCode và toString

Entity proxy có thể làm các method Java thông thường trở nên phức tạp:

- `toString()` nếu in association có thể khởi tạo proxy/collection và gây query.
- `equals()` hoặc `hashCode()` nếu truy cập field quan hệ có thể khởi tạo proxy.
- Dùng entity làm key trong HashSet/HashMap cần equality/hash code ổn định trong suốt vòng đời entity.
- Lombok `@Data` sinh equals/hashCode/toString dựa trên nhiều field có thể vô tình đi qua association.

Với entity, thường nên viết equals/hashCode có chủ đích dựa trên định danh phù hợp với lifecycle và không duyệt association. Tránh đưa collection hoặc quan hệ hai chiều vào toString.

Không so sánh proxy với entity bằng class equality đơn giản như `getClass()` nếu logic đó không tính tới proxy subclass. Chiến lược equality cần được kiểm thử với entity transient, managed, detached và proxy; không có một implementation chung phù hợp mọi domain.

## 17. Fetch plan không phải thay đổi mapping toàn cục

Một entity có thể được dùng ở nhiều use case:

- Màn hình danh sách chỉ cần ID và tên.
- Trang chi tiết cần Customer và OrderItems.
- Báo cáo chỉ cần tổng tiền và số lượng.
- Batch job cần đọc dữ liệu theo chunk.

Nếu đổi mọi quan hệ thành EAGER để sửa một màn hình, các use case khác có thể tải dư dữ liệu và tạo N+1. Nếu đổi mọi quan hệ thành LAZY, code cần xác định fetch plan trước khi truy cập.

Thiết kế tốt thường gồm:

1. Mapping entity mặc định ưu tiên tránh tải graph không cần thiết, thường dùng LAZY cho association.
2. Query method/EntityGraph/fetch join định nghĩa dữ liệu cần cho từng use case.
3. DTO projection dùng cho read model chỉ cần một phần dữ liệu.
4. Integration test kiểm tra cả kết quả và số SQL.
5. Không serialize entity graph tùy tiện qua API.

Đây là cách giữ mapping ổn định và điều khiển fetch behavior tại nơi có ngữ cảnh nghiệp vụ.

## 18. Quan sát và đo SQL

Bật SQL log trong môi trường phát triển:

```properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Bind parameter logging có thể lộ dữ liệu nhạy cảm; chỉ bật ở môi trường an toàn, giới hạn quyền truy cập và tắt sau khi debug.

Khi kiểm tra fetch behavior:

- Đếm số SELECT khi load danh sách và truy cập association.
- Kiểm tra một SELECT JOIN hay nhiều SELECT phụ.
- Kiểm tra N+1 khi số entity tăng từ 10 lên 100.
- Đo số hàng SQL và kích thước result set khi fetch nhiều collection.
- Kiểm tra query count trong transaction và khi serialize response.
- Dùng Hibernate statistics hoặc datasource query-count tool trong integration test.
- Chạy EXPLAIN trên query quan trọng để kiểm tra index và JOIN plan.

Không chỉ nhìn log ở một entity duy nhất; N+1 thường chỉ lộ rõ khi có nhiều entity trong kết quả.

## 19. Integration test cho lazy loading và fetch plan

Ví dụ test fetch join:

```java
@DataJpaTest
class OrderFetchTest {

    @Autowired
    private OrderRepository repository;

    @Autowired
    private EntityManager entityManager;

    @Test
    void fetchesItemsBeforeContextIsCleared() {
        Order order = repository.save(
            OrderFixtures.orderWithItems(2)
        );
        repository.flush();

        Long id = order.getId();
        entityManager.clear();

        Order loaded = repository.findWithItemsById(id)
            .orElseThrow();

        assertThat(loaded.getItems()).hasSize(2);
    }
}
```

Ví dụ giả định repository có method fetch join và fixture tạo Order cùng hai OrderItem hợp lệ. Clear trước khi query giúp tránh entity/collection đã có sẵn trong first-level cache làm test không phản ánh SQL fetch.

Các test quan trọng khác:

- Lazy association được khởi tạo khi truy cập trong transaction.
- Truy cập lazy association detached gây lỗi như mong đợi nếu chưa được fetch.
- Fetch join/EntityGraph trả đủ dữ liệu.
- Danh sách nhiều entity không tạo N+1 vượt ngưỡng query count đã định.
- Pagination không dùng fetch join collection theo cách gây in-memory pagination.
- DTO projection không truy cập association lazy ngoài ý muốn.
- Batch fetching tạo số query phù hợp với batch size.
- Serialization không kích hoạt query ngoài dự kiến.

Không chỉ assert object có dữ liệu; hãy xác minh số query hoặc SQL để biết fetch plan thực sự hoạt động.

## 20. Lựa chọn chiến lược theo tình huống

| Tình huống | Chiến lược nên cân nhắc |
|---|---|
| Chỉ cần entity gốc, không dùng quan hệ | LAZY association, không fetch thêm |
| Cần một to-one trong một query | JOIN FETCH hoặc EntityGraph |
| Cần collection cho một entity chi tiết | LEFT JOIN FETCH hoặc EntityGraph |
| Cần collection cho một trang nhiều parent | Phân trang ID rồi query association; hoặc batch fetching |
| Duyệt nhiều proxy cùng loại | Hibernate batch fetching |
| Chỉ cần một số cột cho API | DTO/interface projection |
| Báo cáo aggregate | DTO projection với GROUP BY |
| Controller cần serialize dữ liệu | Trả DTO đã tạo trong service transaction |
| Batch job rất lớn | Chunk/scrolling, DTO và fetch plan có kiểm soát |
| Nhiều collection lớn | Nhiều query có chủ đích, tránh Cartesian explosion |

Không có một FetchType hoặc một fetch join áp dụng tốt cho mọi use case. Quyết định dựa trên dữ liệu cần trả, cardinality, pagination, query count và memory.

## 21. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| LazyInitializationException | Truy cập proxy/collection sau khi PersistenceContext đóng | Fetch trong transaction hoặc trả DTO |
| N+1 query | Truy cập lazy/eager association theo từng entity | Fetch join, EntityGraph, batch fetching hoặc projection |
| EAGER vẫn chạy nhiều SELECT | EAGER không bắt buộc JOIN | Xác định fetch plan bằng query/EntityGraph và kiểm tra SQL |
| Response JSON phát sinh nhiều query | Serializer duyệt entity association dưới OSIV | Map DTO trong service |
| Pagination chậm/sai với collection fetch join | JOIN nhân bản hàng trước LIMIT/OFFSET | Phân trang ID trước, sau đó fetch association |
| Cartesian product lớn | Fetch nhiều collection trong cùng query | Tách query, batch fetching hoặc DTO |
| MultipleBagFetchException | Hibernate không thể đồng thời fetch nhiều bag collection theo cách query yêu cầu | Chia query hoặc thay đổi fetch strategy có chủ đích |
| toString/equals tạo query | Method đi qua proxy/collection | Loại association khỏi toString/equality |
| EntityGraph không tạo đúng một JOIN | Graph chỉ mô tả fetch requirement | Kiểm tra SQL; provider có thể dùng SELECT bổ sung |
| Test không thấy lazy behavior | Entity/collection đã nằm trong first-level cache | Flush rồi clear trước khi query |
| Dùng EAGER để sửa lỗi detached | Tải dư dữ liệu ở mọi use case | Xác định fetch plan và DTO đúng nơi |
| Batch fetching không giảm query | Proxy không cùng context, batch size hoặc mapping không phù hợp | Kiểm tra SQL và Hibernate configuration |

## 22. Checklist trước khi đưa fetch plan vào production

- [ ] Đã biết FetchType mặc định của từng association?
- [ ] Quan hệ to-one có cần khai báo LAZY tường minh?
- [ ] Query use case cần chính xác association nào?
- [ ] Có dùng fetch join hoặc EntityGraph ở query phù hợp?
- [ ] Có N+1 khi số entity tăng?
- [ ] Collection fetch join có kết hợp pagination không?
- [ ] Có nguy cơ Cartesian explosion hoặc MultipleBagFetchException?
- [ ] DTO projection có phù hợp hơn entity graph?
- [ ] Lazy association có bị truy cập sau transaction/EntityManager đóng?
- [ ] OSIV có che giấu query trong serialization?
- [ ] equals/hashCode/toString có duyệt association?
- [ ] Integration test đã clear PersistenceContext trước khi xác minh?
- [ ] Đã đo SQL count, row count, memory và execution plan?

## 23. Kết luận

FetchType.EAGER yêu cầu association sẵn sàng khi entity được nạp; FetchType.LAZY cho phép trì hoãn tới lúc truy cập. Hibernate thường dùng proxy cho entity to-one và wrapper cho collection to-many. Việc gọi getter, duyệt collection hoặc serialize entity có thể kích hoạt SQL; nếu PersistenceContext đã đóng, truy cập lazy chưa khởi tạo có thể gây LazyInitializationException.

Chọn fetch plan theo từng use case bằng JOIN FETCH, EntityGraph, batch/subselect fetching hoặc DTO projection. Đặc biệt chú ý N+1, fetch join collection với pagination, Cartesian explosion và OSIV. Mapping FetchType chỉ là nền tảng; SQL thực tế, số query và lượng dữ liệu cần được xác minh bằng integration test và log trên đúng provider/database.
