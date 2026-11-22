# Tối ưu truy vấn JPA bằng fetch plan và @EntityGraph khi phù hợp trong Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể nhận biết N+1 query khi Spring Data REST serialize entity; phân biệt lazy và eager loading; thiết kế fetch plan theo từng use case; dùng `@EntityGraph` trên repository method; hiểu giới hạn của fetch join với collection và pagination; cân nhắc projection, DTO và batch fetching; và đo số SQL query để xác minh tối ưu có hiệu quả.

## 1. Vì sao fetch plan quan trọng với Spring Data REST?

Spring Data REST thường serialize entity thành HAL representation. Một entity có thể chứa association tới entity khác, ví dụ Order tham chiếu Customer và có nhiều OrderLine. Khi serializer đọc property, persistence provider có thể phải tải các association chưa được nạp.

Nếu mỗi association được tải bằng một query riêng cho từng entity, API dễ gặp N+1 query:

- Một query lấy danh sách N Order.
- Mỗi Order phát sinh thêm query lấy Customer hoặc OrderLine.
- Số query tăng theo số phần tử trong collection.
- Response chậm dần khi collection lớn dù endpoint chỉ thực hiện một request HTTP.

Fetch plan xác định association nào cần được nạp cho một use case cụ thể. Mục tiêu là lấy đúng dữ liệu cần để tạo response với số query hợp lý, không tải toàn bộ object graph cho mọi endpoint.

Không có một fetch plan tốt cho tất cả request. GET item có thể cần Customer và Address; collection page có thể chỉ cần vài field; màn hình chi tiết Order có thể cần OrderLine và Product. Hãy thiết kế theo representation và hành vi client thực sự sử dụng.

## 2. Hiểu LAZY và EAGER trong JPA

JPA định nghĩa fetch type cho association:

- `FetchType.LAZY`: provider được phép trì hoãn tải association cho đến khi ứng dụng truy cập.
- `FetchType.EAGER`: association phải được fetch khi entity được tải; provider có thể dùng join hoặc query riêng tùy mapping và query.

Với `@ManyToOne` và `@OneToOne`, mặc định là EAGER. Với `@OneToMany` và `@ManyToMany`, mặc định là LAZY.

Ví dụ:

```java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();
}
```

Nên cân nhắc khai báo LAZY cho association và chọn fetch plan ở query/use case cần dữ liệu. EAGER mặc định trên to-one có thể làm nhiều endpoint tải association không cần thiết; EAGER không bảo đảm một SQL join duy nhất và có thể tạo thêm query.

Lưu ý: JPA xem LAZY trên một số association to-one là hint cho provider, không phải bảo đảm tuyệt đối trong mọi implementation/configuration. Kiểm tra SQL thực tế của Hibernate và mapping đang dùng.

## 3. N+1 query khi serialize resource

Giả sử API trả collection Order và mỗi item chứa Customer:

```java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    private Instant createdAt;
}
```

Nếu repository query chỉ tải Order:

```java
List<PurchaseOrder> findAll();
```

Sau đó serializer đọc `order.getCustomer().getName()` cho từng Order, Hibernate có thể phát sinh một query tải Customer cho mỗi item. Với N Order, tổng số query có thể gần 1 + N nếu mỗi Order tham chiếu Customer khác nhau.

Ví dụ log SQL có thể trông như sau:

```sql
select o.id, o.customer_id, o.created_at
from purchase_order o;

select c.id, c.name
from customer c
where c.id = ?;

select c.id, c.name
from customer c
where c.id = ?;
```

Đây là ví dụ minh họa; SQL thực tế phụ thuộc dialect, mapping và cache. Nếu nhiều Order tham chiếu cùng một Customer, persistence context hoặc second-level cache có thể giảm số query, nhưng không nên dựa vào cache để che một fetch plan chưa phù hợp.

N+1 có thể xuất hiện ở:

- Collection resource khi serialize từng item.
- Association lồng nhau trong item representation.
- Projection gọi getter của association.
- Custom controller chuyển entity sang DTO bằng cách truy cập lazy property.
- Một vòng lặp service đọc từng entity rồi truy cập association.

## 4. Fetch plan là gì?

Fetch plan là cách xác định dữ liệu association cần nạp cho một truy vấn/use case. JPA/Hibernate cung cấp nhiều cơ chế:

- `@EntityGraph` để khai báo association cần fetch trên repository method.
- JPQL `JOIN FETCH` để fetch association trong câu query.
- Criteria API hoặc EntityManager để xây dựng query cụ thể.
- Batch fetching để gom các lần tải lazy association thành nhóm.
- DTO projection để chỉ truy vấn field cần cho response.

Chọn cơ chế dựa trên shape của response, kích thước collection và yêu cầu pagination. Không cố gắng fetch toàn bộ graph chỉ để tránh lazy loading; điều đó có thể làm response và memory usage lớn hơn đáng kể.

## 5. Dùng @EntityGraph trên repository method

`@EntityGraph` cho phép chỉ định attribute path cần fetch khi gọi một repository method. Ví dụ:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = "customer")
    List<PurchaseOrder> findByStatus(OrderStatus status);
}
```

Khi gọi method này, Spring Data JPA áp dụng entity graph để provider fetch association `customer` theo graph. Hibernate thường có thể dùng join trong SQL, nhưng chi tiết SQL là quyết định của provider và mapping. Hãy đo query thực tế.

### EntityGraphType.FETCH và LOAD

JPA hỗ trợ hai loại graph:

- `EntityGraphType.FETCH`: các attribute được chỉ định trong graph được xem là eager cho query; attribute không nằm trong graph được xử lý theo lazy semantics.
- `EntityGraphType.LOAD`: các attribute trong graph được fetch; các attribute không nằm trong graph tiếp tục theo fetch type đã khai báo trên mapping.

Ví dụ:

```java
@EntityGraph(
    type = EntityGraph.EntityGraphType.FETCH,
    attributePaths = {"customer", "shippingAddress"})
Optional<PurchaseOrder> findWithDetailsById(Long id);
```

Dùng FETCH khi muốn mô tả rõ graph cần cho query. Dùng LOAD khi muốn bổ sung fetch graph lên trên mapping hiện có. Cả hai đều là fetch plan, không phải cam kết một SQL statement duy nhất.

## 6. Named EntityGraph cho graph dùng lại

Khi nhiều query dùng chung một fetch graph, có thể khai báo named graph trên entity:

```java
@Entity
@NamedEntityGraph(
    name = "PurchaseOrder.withCustomer",
    attributeNodes = @NamedAttributeNode("customer"))
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;
}
```

Repository sử dụng graph:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(
        value = "PurchaseOrder.withCustomer",
        type = EntityGraph.EntityGraphType.FETCH)
    Optional<PurchaseOrder> findDetailedById(Long id);
}
```

Named graph có thể được mở rộng với subgraph khi cần fetch thuộc tính của association lồng. Ví dụ Order có Customer và Customer có Address:

```java
@NamedEntityGraph(
    name = "PurchaseOrder.withCustomerAddress",
    attributeNodes = @NamedAttributeNode(
        value = "customer",
        subgraph = "customerGraph"),
    subgraphs = @NamedSubgraph(
        name = "customerGraph",
        attributeNodes = @NamedAttributeNode("address")))
```

Không tạo graph quá sâu theo toàn bộ object model. Chỉ đưa vào các association mà representation hoặc use case thực sự cần.

## 7. Kết hợp @EntityGraph với query method và pagination

Có thể dùng `@EntityGraph` với query method theo tên:

```java
@EntityGraph(attributePaths = {"customer"})
Page<PurchaseOrder> findByStatus(
    OrderStatus status,
    Pageable pageable);
```

Điều này có thể giúp giảm N+1 khi collection representation cần Customer cho từng Order. Tuy nhiên, cần chú ý các association to-many.

Nếu graph fetch collection như `lines` trong một truy vấn phân trang, join có thể tạo nhiều hàng SQL cho cùng một Order. Điều này có thể gây:

- Trùng root entity trong kết quả.
- Pagination trên hàng join thay vì root entity.
- Kết quả page thiếu hoặc số phần tử không như mong đợi.
- Hibernate cảnh báo hoặc phải tải nhiều dữ liệu rồi phân trang trong memory.
- Count query bổ sung để tính tổng số trang.

Với collection to-many, không nên mặc định kết hợp fetch join/entity graph và database pagination sẽ luôn hiệu quả. Cần kiểm tra SQL và cảnh báo Hibernate. Một pattern thường dùng là phân trang ID/root entity trước, sau đó fetch chi tiết cho danh sách ID của page trong query thứ hai, hoặc dùng DTO projection phù hợp.

Ví dụ pattern hai bước:

```java
Page<Long> findIdsByStatus(
    OrderStatus status,
    Pageable pageable);

@EntityGraph(attributePaths = {"customer", "lines"})
List<PurchaseOrder> findWithDetailsByIdIn(
    Collection<Long> ids);
```

Service lấy page ID, rồi query graph cho các ID đó. Cần giữ thứ tự ban đầu của page khi dựng kết quả vì `IN (:ids)` không bảo đảm thứ tự. Có thể sắp xếp theo map vị trí hoặc dùng query có order phù hợp.

## 8. Khi nào dùng JOIN FETCH thay cho @EntityGraph?

JPQL fetch join diễn đạt trực tiếp association cần fetch:

```java
@Query("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    where o.id = :id
    """)
Optional<PurchaseOrder> findByIdWithCustomer(Long id);
```

Ưu điểm:

- Query thể hiện rõ join và association cần tải.
- Có thể kết hợp predicate hoặc join condition theo nhu cầu.
- Hữu ích cho một query chuyên biệt.

Nhược điểm:

- Query gắn chặt với object graph và cấu trúc mapping.
- Dễ tạo duplicate root khi fetch collection.
- Fetch join collection cùng pagination cần đặc biệt thận trọng.
- Không tiện tái sử dụng như named graph nếu nhiều query cùng dùng fetch plan.

Dùng `@EntityGraph` khi muốn tách query predicate khỏi fetch plan và dùng lại graph. Dùng fetch join khi cần điều khiển query cụ thể. Cả hai đều cần xác minh số SQL và dữ liệu trả về.

## 9. DTO projection khi không cần entity graph

Nếu response chỉ cần một số field, DTO projection có thể hiệu quả hơn tải entity đầy đủ cùng association.

Ví dụ record:

```java
public record OrderSummary(
    Long id,
    Instant createdAt,
    String customerName,
    BigDecimal total) {
}
```

Repository query:

```java
@Query("""
    select new com.example.api.OrderSummary(
        o.id,
        o.createdAt,
        c.name,
        o.total)
    from PurchaseOrder o
    join o.customer c
    where o.status = :status
    """)
Page<OrderSummary> findSummaries(
    OrderStatus status,
    Pageable pageable);
```

DTO projection chỉ chọn field cần cho response và tránh việc serializer đi qua lazy association. Đây là lựa chọn tốt cho collection summary hoặc custom REST endpoint.

Spring Data REST repository resource chủ yếu biểu diễn domain resources và projections theo cơ chế riêng. Nếu cần DTO response có shape nghiệp vụ rõ ràng, custom controller/service có thể phù hợp hơn. Không cố biến mọi DTO thành repository entity.

### Interface projection

Spring Data JPA cũng hỗ trợ interface projection:

```java
public interface OrderSummaryView {
    Long getId();
    Instant getCreatedAt();
    String getCustomerName();
}
```

Projection có thể giúp giảm dữ liệu đọc, nhưng nested projection vẫn có thể khiến provider tải association. Hãy kiểm tra generated SQL thay vì giả định projection luôn chỉ tạo một query gọn.

## 10. Batch fetching là giải pháp bổ sung

Batch fetching gom các lần tải lazy association thành một query dùng nhiều ID thay vì một query cho mỗi entity.

Với Hibernate, có thể dùng annotation:

```java
@ManyToOne(fetch = FetchType.LAZY)
@BatchSize(size = 32)
private Customer customer;
```

Hoặc cấu hình toàn cục:

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
```

Khi serializer truy cập association của nhiều entity trong cùng persistence context, Hibernate có thể tải theo batch. Thay vì N query riêng, số query có thể giảm gần thành các nhóm khoảng batch size.

Batch fetching là tối ưu bổ sung, không thay thế fetch plan có chủ đích. Nó không bảo đảm mọi query được gộp, còn phụ thuộc persistence context, association type, cache và thứ tự truy cập.

Chọn batch size bằng đo đạc. Giá trị quá lớn có thể tạo IN clause dài, tăng memory và tải database; giá trị quá nhỏ có thể không giảm đủ round trips.

## 11. EntityGraph và Spring Data REST serialization

Spring Data REST thường lấy entity qua repository rồi serialize thành HAL. Để giảm N+1, có thể cung cấp repository query method với `@EntityGraph` cho use case cụ thể. Tuy nhiên, cần phân biệt query method resource được export với phương thức service/controller tự gọi repository.

Ví dụ:

```java
@RepositoryRestResource(path = "orders")
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @RestResource(path = "by-status", rel = "byStatus")
    @EntityGraph(attributePaths = "customer")
    Page<PurchaseOrder> findByStatus(
        @Param("status") OrderStatus status,
        Pageable pageable);
}
```

Nếu method được export, Spring Data REST có thể tạo search resource cho query. Client khám phá link search rồi gọi query resource. Fetch graph áp dụng khi Spring Data REST gọi repository method đó.

Không phải lúc nào collection endpoint mặc định cũng dùng custom graph. Nếu cần fetch plan riêng cho collection root, có thể dùng custom repository implementation, service/controller hoặc query method được export tùy thiết kế API. Đừng giả định thêm `@EntityGraph` vào một method bất kỳ sẽ thay đổi mọi endpoint của repository.

Nếu serializer truy cập property không nằm trong graph, Hibernate vẫn có thể phát query bổ sung khi session còn mở; nếu session đã đóng, có thể gặp LazyInitializationException. Fetch plan phải khớp đúng representation mà endpoint serialize.

## 12. Open Session in View không phải giải pháp N+1

Spring Boot có thể bật Open EntityManager in View cho web application tùy cấu hình. Cơ chế này giữ persistence context mở trong suốt request, cho phép lazy association được tải trong lúc serialize response.

Điều đó có thể tránh LazyInitializationException nhưng cũng che giấu truy vấn phát sinh trong serialization và khiến database access xảy ra ngoài service transaction. Một collection response có thể trả về đúng dữ liệu nhưng tạo hàng trăm query.

Có thể tắt OSIV để buộc service/repository tải đủ dữ liệu trước khi trả response:

```properties
spring.jpa.open-in-view=false
```

Sau khi tắt, kiểm tra các endpoint cần association. Dùng EntityGraph, fetch join, DTO projection hoặc mapping trong transaction để lấy dữ liệu cần thiết. Không bật OSIV chỉ để làm biến mất exception mà không xem SQL.

OSIV không phải lúc nào cũng sai; quyết định phụ thuộc kiến trúc. Điều quan trọng là hiểu transaction boundary và số query phát sinh khi serialize.

## 13. Đo query count và xác minh tối ưu

Không đánh giá hiệu năng chỉ bằng cảm giác hoặc thời gian một lần gọi trên máy developer. Đo số SQL query và lượng dữ liệu được đọc.

Với Hibernate statistics, có thể bật trong test:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Sau khi reset statistics và thực hiện request:

```java
@Autowired
EntityManagerFactory entityManagerFactory;

@Test
void orderCollectionUsesBoundedQueryCount() throws Exception {
    SessionFactory sessionFactory =
        entityManagerFactory.unwrap(SessionFactory.class);

    Statistics statistics = sessionFactory.getStatistics();
    statistics.clear();

    mvc.perform(get("/orders?size=20")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk());

    assertThat(statistics.getPrepareStatementCount())
        .isLessThanOrEqualTo(4);
}
```

Ngưỡng query count trong ví dụ chỉ minh họa; chọn ngưỡng theo endpoint, database và các query phụ cần thiết. Statistics có thể bị ảnh hưởng bởi Spring context dùng chung hoặc test chạy song song. Cô lập test và reset statistics đúng thời điểm.

Có thể dùng datasource-proxy hoặc p6spy để log/count SQL. Khi đo, quan sát cả:

- Tổng số statement.
- Số query theo từng loại.
- Số row được trả về.
- Thời gian database và thời gian serialize.
- Query plan và index.
- Số lần truy cập association trong response.

Một endpoint có ít query nhưng mỗi query trả hàng trăm nghìn row vẫn có thể rất chậm. Tối ưu fetch plan cần cân bằng round trips, dữ liệu tải, memory và số lượng association.

## 14. Kiểm thử N+1 với dữ liệu đủ lớn

Test với một Order có một Customer thường không phát hiện N+1. Hãy tạo nhiều root entity với các association khác nhau:

1. Tạo 20 hoặc 50 Order.
2. Gắn Customer riêng hoặc lặp lại Customer theo kịch bản cần đo.
3. Flush và clear persistence context để tránh first-level cache làm sai kết quả.
4. Reset Hibernate statistics.
5. Gọi collection endpoint.
6. Đếm query và so sánh khi có/không có fetch plan.
7. Kiểm tra response vẫn đầy đủ field và link cần thiết.

Ví dụ setup:

```java
for (int i = 0; i < 20; i++) {
    Customer customer = customerRepository.save(
        new Customer("Customer " + i));

    orderRepository.save(
        new PurchaseOrder(customer, OrderStatus.OPEN));
}
orderRepository.flush();

entityManager.clear();
```

Sau khi clear, request sẽ phải tải dữ liệu từ database thay vì dùng entity đã nằm trong persistence context. Trong test thực tế, request có thể chạy trong transaction/persistence context khác; đảm bảo statistics đo đúng request và không bị fixture setup tính vào.

## 15. Những lỗi thường gặp khi dùng @EntityGraph

**Graph không giảm query count**

Kiểm tra query method nào thực sự được gọi, graph name/attribute path có đúng, association có được truy cập ngoài graph không, và Hibernate phát SQL gì. Một graph có thể được provider thực hiện bằng nhiều query.

**Fetch quá nhiều dữ liệu**

Graph sâu hoặc to-many lớn có thể làm result set phình to. Giảm graph hoặc dùng DTO projection; chia collection thành endpoint riêng khi phù hợp.

**Pagination bị sai hoặc chậm khi fetch collection**

Không fetch join to-many cùng pageable một cách tùy tiện. Dùng page ID trước rồi fetch chi tiết, hoặc projection phù hợp; kiểm tra count query và cảnh báo Hibernate.

**LazyInitializationException sau khi tắt OSIV**

Tải association cần thiết trong transaction qua EntityGraph/fetch join, hoặc chuyển dữ liệu sang DTO trước khi transaction kết thúc.

**Thêm EntityGraph vào method nhưng endpoint mặc định không đổi**

Graph chỉ áp dụng cho method được annotation. Xác định endpoint Spring Data REST gọi repository method nào và thiết kế query resource/custom endpoint phù hợp.

**Test query count không ổn định**

Cô lập statistics, tránh chạy song song, reset sau setup, cố định dữ liệu và không assert một con số quá chặt khi framework có thể thêm query phụ hợp lệ.

## 16. Quy trình chọn fetch plan cho một endpoint

1. Xác định representation HAL thực tế: field nào được serialize, projection nào được dùng và association link nào cần hiển thị.
2. Đo SQL hiện tại với dữ liệu đại diện.
3. Xác định query phát sinh theo từng entity hoặc association.
4. Với to-one cần cho response, thử `@EntityGraph(attributePaths = ...)`.
5. Với query đặc thù, cân nhắc JPQL fetch join.
6. Với collection summary, cân nhắc DTO/interface projection.
7. Với nhiều lazy association nhỏ, cân nhắc batch fetching.
8. Với to-many và pagination, tránh fetch join trực tiếp nếu làm sai page; cân nhắc hai bước.
9. Tắt OSIV trong test nếu production tắt, để lộ fetch plan thiếu.
10. Đo lại query count, thời gian, row count và xác minh response contract không đổi.

Fetch plan là một phần của thiết kế endpoint. Khi representation thay đổi, query cần thiết cũng có thể thay đổi. Nên có integration test đo query count cho các endpoint hiệu năng quan trọng để phát hiện regression.

## Tóm tắt

- N+1 xảy ra khi query root lấy N entity rồi serializer tải association riêng cho từng entity.
- LAZY giúp tránh tải không cần thiết nhưng có thể phát sinh query trong lúc serialize; EAGER không bảo đảm một SQL join duy nhất.
- `@EntityGraph` khai báo association cần fetch cho repository method; named graph hữu ích khi nhiều query dùng chung fetch plan.
- Fetch graph có thể áp dụng cho query method được Spring Data REST export, nhưng không tự thay đổi mọi endpoint của repository.
- Fetch to-many cùng pagination cần thận trọng vì duplicate root, page sai hoặc tải toàn bộ kết quả.
- DTO projection phù hợp khi response chỉ cần một số field; batch fetching là tối ưu bổ sung cho lazy associations.
- OSIV có thể che giấu N+1; tắt nó trong cấu hình phù hợp giúp xác định fetch plan thiếu.
- Dùng Hibernate statistics hoặc datasource-proxy để đo query count, row count và thời gian; kiểm thử với dữ liệu đủ lớn.
- Chọn fetch plan theo representation và use case, không tải toàn bộ object graph theo mặc định.

## Tài liệu tham khảo

- [Spring Data JPA — Entity Graphs](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA — Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)
- [Hibernate ORM — Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching)
- [Jakarta Persistence — Entity Graphs](https://jakarta.ee/specifications/persistence/)
- [Spring Boot — Open EntityManager in View](https://docs.spring.io/spring-boot/reference/data/sql.html)
