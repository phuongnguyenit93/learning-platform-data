# Lazy relation trong processor

Khi Spring Batch xử lý entity JPA, processor thường cần đọc thêm dữ liệu liên quan như customer, address, order lines hoặc product. Nếu các quan hệ được khai báo `FetchType.LAZY`, JPA chỉ tải chúng khi ứng dụng truy cập. Cách tải trì hoãn này giúp tránh lấy một object graph lớn khi chưa cần, nhưng có thể gây lỗi nếu processor truy cập quan hệ sau khi persistence context đã đóng hoặc entity đã bị detach.

Với `JpaPagingItemReader`, đây là tình huống cần chú ý: reader quản lý `EntityManager` riêng để đọc từng page và mặc định có thể clear persistence context sau mỗi page. Entity trả về cho processor vì thế thường đã detached. Khi processor gọi `order.getCustomer().getName()` hoặc duyệt `order.getLines()`, Hibernate có thể ném `LazyInitializationException` vì proxy/collection không còn một session đang mở để tải dữ liệu.

Giải pháp nên dựa trên dữ liệu processor thực sự cần: fetch quan hệ ngay trong query phù hợp, dùng DTO projection, hoặc tải lại dữ liệu bằng ID trong một service có transaction. Không nên đổi mọi quan hệ sang `EAGER` hoặc dựa vào Open Session in View để che lỗi.

## 1. Lazy loading trong JPA là gì?

JPA cho phép một entity tham chiếu đến entity khác hoặc collection liên quan. Fetch strategy xác định thời điểm provider tải dữ liệu quan hệ:

- `FetchType.LAZY`: quan hệ được tải khi ứng dụng truy cập nếu provider có thể thực hiện việc tải đó trong persistence context còn hoạt động.
- `FetchType.EAGER`: provider phải bảo đảm quan hệ được tải khi entity được truy xuất; điều này không đồng nghĩa luôn có một câu SQL join duy nhất.

Ví dụ entity đơn hàng:

```java
@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private Long id;

    private String orderNumber;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private CustomerEntity customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLineEntity> lines = new ArrayList<>();

    public Long getId() {
        return id;
    }

    public CustomerEntity getCustomer() {
        return customer;
    }

    public List<OrderLineEntity> getLines() {
        return lines;
    }
}
```

`customer` là quan hệ many-to-one được cấu hình lazy một cách tường minh. `lines` là collection one-to-many, vốn mặc định lazy theo JPA, nhưng khai báo rõ giúp người đọc hiểu ý định của mapping.

Khi truy vấn `OrderEntity`, provider có thể chỉ lấy các cột của bảng `orders` và giữ một proxy cho `customer` cùng một collection chưa khởi tạo cho `lines`. Dữ liệu liên quan được tải khi truy cập, miễn là proxy còn gắn với persistence context phù hợp.

## 2. Persistence context và entity detached

Persistence context là vùng quản lý entity của một `EntityManager`. Entity được đọc trong context có thể ở trạng thái managed. Khi context bị clear, đóng hoặc entity được detach, entity không còn được quản lý bởi context đó.

| Trạng thái | Ý nghĩa | Lazy relation |
|---|---|---|
| Managed | Entity đang được một persistence context quản lý | Có thể tải nếu context/session còn hoạt động và provider hỗ trợ. |
| Detached | Entity từng được quản lý nhưng không còn gắn với context đó | Quan hệ lazy chưa tải thường không thể tự tải. |
| Removed | Entity được đánh dấu xóa trong context | Không phải trạng thái phù hợp để tiếp tục xử lý dữ liệu như một entity bình thường. |
| New/Transient | Entity chưa được persist | Quan hệ phụ thuộc mapping và object graph được gán trong ứng dụng. |

Một lazy proxy không tự mở kết nối hoặc tự tạo transaction mới. Nó cần persistence context đã tạo ra nó. Khi context không còn hoạt động, việc khởi tạo proxy/collection có thể thất bại.

Với Hibernate, lỗi phổ biến là `org.hibernate.LazyInitializationException`, thường có thông báo tương tự “could not initialize proxy” hoặc “failed to lazily initialize a collection”. JPA không chuẩn hóa tên exception này cho mọi provider; provider khác có thể báo lỗi tương ứng theo cách riêng.

## 3. Vì sao lazy relation dễ lỗi trong ItemProcessor?

Trong một chunk Step, reader lấy item, processor xử lý item và writer ghi output. Tuy nhiên, JPA reader có thể quản lý persistence context riêng với persistence context của transaction chunk.

`JpaPagingItemReader` tạo `EntityManager` để thực hiện query theo page. Với cấu hình mặc định, reader quản lý transaction đọc page và clear persistence context sau page để tránh giữ toàn bộ entity trong memory. Entity được trả về cho processor vì thế thường đã detached, dù processor đang được gọi trong transaction của chunk.

Sơ đồ khái niệm:

```text
JpaPagingItemReader
  |
  +--> EntityManager của reader
  |       |
  |       +--> Query một page
  |       +--> Entity được load
  |       +--> Clear persistence context
  |
  v
OrderEntity được trả về (detached)
  |
  v
ItemProcessor
  |
  +--> order.getCustomer().getName()
  |       |
  |       +--> Lazy proxy cần EntityManager cũ
  |               |
  |               +--> Context không còn quản lý entity
  |                       |
  |                       +--> LazyInitializationException
  |
  v
Writer
```

Điểm cần nhớ: việc processor đang chạy trong một transaction của Step không có nghĩa entity từ `JpaPagingItemReader` tự động managed bởi `EntityManager` của transaction đó. Hai persistence context có thể hoàn toàn khác nhau.

Chi tiết lifecycle phụ thuộc reader, phiên bản Spring Batch và cấu hình `transacted`. Không nên dựa vào việc entity tình cờ còn managed trong một cấu hình cụ thể; hãy thiết kế rõ dữ liệu quan hệ cần thiết và kiểm thử với cấu hình thực tế.

## 4. Ví dụ lỗi LazyInitializationException

Giả sử processor cần tên khách hàng để tạo DTO:

```java
@Component
public class OrderExportProcessor
        implements ItemProcessor<OrderEntity, OrderExport> {

    @Override
    public OrderExport process(OrderEntity order) {
        String customerName = order.getCustomer().getName();

        return new OrderExport(
                order.getId(),
                customerName);
    }
}
```

Nếu `customer` chưa được tải và entity đã detached, lời gọi `getName()` có thể kích hoạt lazy load nhưng không còn session để thực hiện query. Processor thất bại trước khi trả output cho writer.

Một collection có cùng vấn đề:

```java
BigDecimal total = order.getLines().stream()
        .map(line -> line.getQuantity()
                .multiply(line.getUnitPrice()))
        .reduce(BigDecimal.ZERO, BigDecimal::add);
```

Nếu `lines` chưa được khởi tạo trước khi entity detached, duyệt collection cũng có thể ném `LazyInitializationException`.

Không phải mọi truy cập getter đều gây lỗi. Trường scalar đã được load trong query như `id`, `orderNumber` vẫn có thể đọc từ object detached. Lỗi xuất hiện khi code cần tải dữ liệu quan hệ chưa được khởi tạo hoặc truy cập một proxy phụ thuộc persistence context cũ.

## 5. Không dùng Open Session in View cho Batch

Open Session in View (OSIV) là một mẫu thường gặp trong ứng dụng web, giữ persistence context mở trong phạm vi HTTP request để view có thể truy cập lazy relation. Spring Batch không có HTTP request bao quanh một Job/Step theo cách đó.

Không nên bật OSIV hoặc tạo một session toàn cục chỉ để processor có thể truy cập lazy relation. Cách này làm ranh giới transaction và query trở nên khó dự đoán, có thể tạo N+1 query và giữ tài nguyên lâu.

Batch nên xác định dữ liệu cần đọc ở query/reader hoặc tải lại bằng service có transaction rõ ràng. Khi processor cần một DTO, hãy tạo DTO trong lúc dữ liệu cần thiết đang được tải và trả ra khỏi service, thay vì đưa lazy proxy qua nhiều tầng xử lý.

## 6. Cách 1: Fetch quan hệ ngay trong JPQL query

Nếu processor luôn cần một quan hệ cụ thể, có thể tải quan hệ đó cùng root entity bằng `JOIN FETCH`.

Ví dụ processor cần `customer`:

```java
@Bean
@StepScope
JpaPagingItemReader<OrderEntity> orderReader(
        EntityManagerFactory entityManagerFactory,
        @Value("#{jobParameters['tenant.id']}") Long tenantId) {

    return new JpaPagingItemReaderBuilder<OrderEntity>()
            .name("orderReader")
            .entityManagerFactory(entityManagerFactory)
            .queryString("""
                    select o
                    from OrderEntity o
                    join fetch o.customer c
                    where o.tenantId = :tenantId
                      and o.status = 'PENDING'
                    order by o.id
                    """)
            .parameterValues(Map.of("tenantId", tenantId))
            .pageSize(100)
            .saveState(true)
            .build();
}
```

Với quan hệ optional, dùng `left join fetch` nếu vẫn cần lấy order khi không có customer:

```sql
select o
from OrderEntity o
left join fetch o.customer
where o.status = 'PENDING'
order by o.id
```

Khi query đã tải customer cùng order, processor có thể đọc tên khách hàng từ dữ liệu đã có trong object graph mà không cần lazy load sau khi reader detach entity.

`JOIN FETCH` phù hợp nhất với quan hệ to-one như many-to-one hoặc one-to-one. Với collection to-many, cần chú ý đặc biệt khi kết hợp pagination.

## 7. Cách 2: Dùng EntityGraph

JPA EntityGraph cho phép chỉ định các quan hệ cần tải cho một query hoặc repository operation mà không phải thay đổi fetch strategy mặc định của entity.

Ví dụ với Spring Data JPA:

```java
public interface OrderRepository extends JpaRepository<OrderEntity, Long> {

    @EntityGraph(attributePaths = "customer")
    @Query("""
           select o
           from OrderEntity o
           where o.id = :id
           """)
    Optional<OrderEntity> findWithCustomerById(@Param("id") Long id);
}
```

Nếu cần nhiều quan hệ trong một lần tải:

```java
@EntityGraph(attributePaths = {"customer", "shippingAddress"})
@Query("select o from OrderEntity o where o.id = :id")
Optional<OrderEntity> findDetailedById(@Param("id") Long id);
```

EntityGraph xác định dữ liệu cần được fetch, còn provider quyết định cách thực hiện query. Provider có thể dùng join hoặc các câu query bổ sung; vì vậy, không nên mặc định rằng EntityGraph luôn tạo đúng một SQL statement.

Với `JpaPagingItemReader`, builder nhận JPQL query string. Nếu cần EntityGraph trên reader, cần cấu hình hint phù hợp cho query hoặc dùng repository/custom reader có hỗ trợ EntityGraph. Không thể chỉ thêm annotation vào entity rồi giả định mọi query tự động dùng graph.

EntityGraph hữu ích khi một use case cần một graph cụ thể nhưng các use case khác vẫn muốn giữ lazy loading. Hãy kiểm tra SQL và query count để bảo đảm graph không tải quá nhiều dữ liệu.

## 8. Cách 3: Dùng DTO projection thay cho entity graph

Nếu processor chỉ cần một vài field từ entity và quan hệ, DTO projection thường là lựa chọn gọn và an toàn. Query trả về dữ liệu scalar đã chọn, không mang lazy proxy qua pipeline.

Ví dụ DTO:

```java
public record OrderProcessData(
        Long orderId,
        String orderNumber,
        String customerName,
        String customerRegion) {
}
```

JPQL constructor expression:

```java
@Bean
@StepScope
JpaPagingItemReader<OrderProcessData> orderDataReader(
        EntityManagerFactory entityManagerFactory,
        @Value("#{jobParameters['tenant.id']}") Long tenantId) {

    return new JpaPagingItemReaderBuilder<OrderProcessData>()
            .name("orderDataReader")
            .entityManagerFactory(entityManagerFactory)
            .queryString("""
                    select new com.example.batch.OrderProcessData(
                        o.id,
                        o.orderNumber,
                        c.name,
                        c.region)
                    from OrderEntity o
                    join o.customer c
                    where o.tenantId = :tenantId
                      and o.status = 'PENDING'
                    order by o.id
                    """)
            .parameterValues(Map.of("tenantId", tenantId))
            .pageSize(100)
            .saveState(true)
            .build();
}
```

Processor nhận DTO:

```java
@Bean
ItemProcessor<OrderProcessData, OrderExport> orderExportProcessor() {
    return data -> new OrderExport(
            data.orderId(),
            data.orderNumber(),
            data.customerName(),
            data.customerRegion());
}
```

DTO projection có các lợi ích:

- Không có lazy proxy cần khởi tạo trong processor.
- Query chỉ lấy field cần thiết.
- Không phụ thuộc persistence context sau khi đọc.
- Tránh serialize hoặc vô tình sửa entity managed/detached.
- Hợp đồng input của processor thể hiện rõ dữ liệu có sẵn.

Nếu processor cần collection con, constructor projection đơn giản không tự tạo một nested collection đầy đủ. Có thể dùng query riêng để tổng hợp, native SQL/DTO mapping phù hợp hoặc một reader tùy chỉnh tạo aggregate item.

## 9. Cách 4: Đọc ID rồi tải lại trong transaction của processor

Nếu dữ liệu quan hệ thay đổi thường xuyên hoặc processor cần logic trên trạng thái mới nhất, reader có thể chỉ trả ID. Processor gọi một service để tải entity và quan hệ cần thiết trong transaction.

Reader trả ID:

```java
@Bean
@StepScope
JpaPagingItemReader<Long> orderIdReader(
        EntityManagerFactory entityManagerFactory) {

    return new JpaPagingItemReaderBuilder<Long>()
            .name("orderIdReader")
            .entityManagerFactory(entityManagerFactory)
            .queryString("""
                    select o.id
                    from OrderEntity o
                    where o.status = 'PENDING'
                    order by o.id
                    """)
            .pageSize(100)
            .saveState(true)
            .build();
}
```

Service tải dữ liệu cần thiết:

```java
@Service
public class OrderQueryService {

    private final OrderRepository orderRepository;

    public OrderQueryService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public OrderProcessData loadForProcessing(Long orderId) {
        OrderEntity order = orderRepository.findDetailedById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        return new OrderProcessData(
                order.getId(),
                order.getOrderNumber(),
                order.getCustomer().getName(),
                order.getCustomer().getRegion());
    }
}
```

Processor gọi service:

```java
@Bean
ItemProcessor<Long, OrderProcessData> orderLoadingProcessor(
        OrderQueryService orderQueryService) {
    return orderQueryService::loadForProcessing;
}
```

Trong method service, repository tải entity mới và EntityGraph tải customer. Service đọc các quan hệ rồi chuyển thành DTO trước khi transaction kết thúc. Processor nhận DTO đã hoàn chỉnh và không cần lazy load.

### Nếu reader trả entity thay vì ID

Có thể lấy ID scalar đã được load từ entity detached rồi gọi service:

```java
return orderQueryService.loadForProcessing(detachedOrder.getId());
```

Không truy cập `detachedOrder.getCustomer()` để lấy ID hoặc field quan hệ. Dùng khóa chính của root entity đã được load sẵn.

### Lưu ý về transaction

Service cần được gọi qua Spring bean proxy để `@Transactional` có hiệu lực. Nếu method tự gọi một method khác trong cùng object, self-invocation có thể bỏ qua proxy transaction tùy cơ chế proxy đang dùng.

Transaction của service thường tham gia transaction chunk hiện tại nếu dùng cùng transaction manager và propagation mặc định `REQUIRED`. Dù vậy, service tải entity mới trong persistence context của transaction hiện tại; nó không tự gắn lại lazy proxy thuộc EntityManager cũ của reader.

## 10. @Transactional trên processor có giải quyết được không?

Thêm `@Transactional` vào processor không tự động sửa lỗi lazy relation của entity detached.

Ví dụ:

```java
@Component
public class OrderProcessor
        implements ItemProcessor<OrderEntity, OrderExport> {

    @Override
    @Transactional(readOnly = true)
    public OrderExport process(OrderEntity order) {
        return new OrderExport(
                order.getId(),
                order.getCustomer().getName());
    }
}
```

Transaction này có thể mở một persistence context mới. Nhưng `order` vẫn là entity detached do reader trả ra; proxy customer vẫn gắn với persistence context cũ đã bị clear/đóng. Một EntityManager mới không tự nhận ownership của proxy cũ.

Nếu cần transaction để tải quan hệ, hãy tải lại entity bằng ID trong transaction mới hoặc dùng query projection/entity graph. `@Transactional` hữu ích cho service truy vấn mới, nhưng không phải phép gắn lại tự động cho mọi detached entity.

## 11. Cách 5: Merge entity rồi truy cập quan hệ

JPA `merge` có thể đưa state của entity detached vào persistence context mới và trả về một instance managed. Tuy nhiên, merge không phải giải pháp mặc định cho lazy relation.

Ví dụ về hình thức:

```java
@Transactional
public OrderExport mapDetachedOrder(OrderEntity detached) {
    OrderEntity managed = entityManager.merge(detached);
    return new OrderExport(
            managed.getId(),
            managed.getCustomer().getName());
}
```

Nếu dùng `merge`, phải sử dụng instance được trả về (`managed`), không tiếp tục truy cập object đầu vào (`detached`). Merge có thể tạo thêm query/copy state và vẫn phải tuân thủ optimistic locking khi cập nhật. Các association chưa được fetch có semantics riêng theo JPA provider; không nên dựa vào merge để tự động tải mọi collection cần thiết.

Nếu chỉ cần đọc một vài field, query lại bằng ID với EntityGraph hoặc projection thường rõ ràng hơn. Nếu cần cập nhật entity, hãy xác định version, transaction và quy tắc hợp nhất trước khi merge.

## 12. Vì sao không nên đổi mọi quan hệ sang EAGER?

Một cách chữa nhanh là đổi `LAZY` thành `EAGER` để mọi relation luôn được tải. Cách này có thể làm một use case chạy được nhưng tạo vấn đề hiệu năng và dữ liệu ở các use case khác.

Những rủi ro:

- Entity graph lớn hơn mức processor cần.
- Nhiều query phụ được thực hiện khi đọc một page.
- N+1 query vẫn có thể xảy ra tùy provider và mapping.
- Page chứa nhiều entity cùng với quan hệ con làm tăng heap usage.
- Quan hệ vòng hoặc nhiều tầng EAGER khiến graph khó dự đoán.
- Một reader cần ít field nhưng phải tải cả dữ liệu không sử dụng.

`EAGER` là yêu cầu fetch của mapping, không phải cam kết rằng provider sẽ luôn dùng một SQL join hiệu quả. Hãy giữ mapping theo đặc điểm domain và định nghĩa fetch plan theo use case của Step.

## 13. Cẩn thận với JOIN FETCH collection khi paging

Fetch join quan hệ to-one thường dễ kết hợp với paging hơn. Với collection như `@OneToMany`, một root entity có thể tạo nhiều SQL row:

```text
Order 1001 + Line A
Order 1001 + Line B
Order 1001 + Line C
Order 1002 + Line D
```

Nếu áp dụng `setFirstResult`/`setMaxResults` trên kết quả join đã nhân dòng, database có thể cắt page giữa các child row của cùng một order. Provider có thể phải xử lý pagination trong memory hoặc tạo cảnh báo; số root entity thực tế có thể khác dự kiến và hiệu năng giảm mạnh.

Ví dụ không nên dùng một cách tùy tiện:

```sql
select distinct o
from OrderEntity o
left join fetch o.lines
where o.status = 'PENDING'
order by o.id
```

`distinct` không tự giải quyết mọi vấn đề do row multiplication khi database áp dụng limit/offset. Với Hibernate, fetch collection cùng pagination có thể dẫn đến cảnh báo và pagination in-memory, tùy phiên bản/cấu hình.

Các lựa chọn tốt hơn:

- Page root IDs trước, sau đó tải collection cho nhóm ID bằng query riêng.
- Dùng DTO projection hoặc aggregate query nếu chỉ cần tổng hợp field.
- Dùng một reader/custom reader tạo aggregate item theo page.
- Chia bài toán thành bước đọc root và bước xử lý child nếu phù hợp nghiệp vụ.
- Dùng batch fetching khi các proxy cùng tồn tại trong một persistence context đang mở và đã đo hiệu quả.

Không dùng collection fetch join trong paging query nếu chưa kiểm tra SQL, số item root và memory behavior trên dữ liệu thật.

## 14. N+1 query khi processor tải quan hệ

Ngay cả khi không có `LazyInitializationException`, việc tải relation trong processor có thể tạo N+1 query.

Ví dụ Job đọc 1.000 order. Mỗi lần processor gọi service lấy order cùng customer bằng một query, và sau đó truy cập collection lines bằng một query khác:

```text
1 query lấy page/root orders
1000 query lấy customer hoặc detail
1000 query lấy order lines
```

Số query có thể tăng nhanh theo số item. Điều này làm Job chậm và tăng tải database.

Cách giảm N+1:

- Dùng projection để lấy field cần thiết trong query gốc.
- Fetch join to-one relation cần thiết.
- Dùng EntityGraph cho fetch plan rõ ràng.
- Tải nhiều association theo nhóm ID bằng query bulk phù hợp.
- Dùng batch fetch/subselect trong persistence context còn mở khi phù hợp.
- Đo query count và execution plan trước khi tăng page/chunk size.

`@BatchSize` hoặc `hibernate.default_batch_fetch_size` có thể giảm số query lazy khi nhiều proxy/collection cùng tồn tại trong một persistence context. Chúng không làm một proxy detached tự tải được sau khi EntityManager đã đóng hoặc clear.

## 15. Dùng DTO projection cho dữ liệu quan hệ một-nhiều

Nếu processor cần tổng số dòng, tổng số lượng hoặc một số field của order lines, có thể tính tổng trong query hoặc tạo một DTO aggregate.

Ví dụ query tổng hợp:

```sql
select new com.example.batch.OrderSummary(
    o.id,
    o.orderNumber,
    c.name,
    coalesce(sum(l.quantity * l.unitPrice), 0))
from OrderEntity o
join o.customer c
left join o.lines l
where o.status = :status
group by o.id, o.orderNumber, c.name
order by o.id
```

DTO:

```java
public record OrderSummary(
        Long orderId,
        String orderNumber,
        String customerName,
        BigDecimal lineTotal) {
}
```

Query aggregate không tạo collection `lines` trong Java, nhưng có thể cung cấp đúng giá trị processor cần. Nếu cần toàn bộ child record, có thể truy vấn chúng theo nhóm ID rồi map vào aggregate bằng custom reader hoặc một bước tiền xử lý.

Khi dùng `GROUP BY`, cần kiểm tra kết quả với order không có line, nhiều line, decimal precision và semantics của `coalesce`. Paging query cũng cần sort key duy nhất trên kết quả aggregate.

## 16. Explicit initialization trong persistence context còn mở

Nếu ứng dụng dùng Hibernate, có thể khởi tạo một proxy/collection tường minh bằng `Hibernate.initialize(...)` trong lúc session còn mở:

```java
@Transactional(readOnly = true)
public OrderExport loadAndMap(Long orderId) {
    OrderEntity order = entityManager.find(OrderEntity.class, orderId);

    Hibernate.initialize(order.getCustomer());
    Hibernate.initialize(order.getLines());

    return mapToExport(order);
}
```

Trong ví dụ, entity được tải trong transaction hiện tại; quan hệ được initialize trước khi service trả DTO. Không gọi `Hibernate.initialize(detachedOrder.getLines())` trên entity đã detached vì session gốc không còn hoạt động.

`Hibernate.initialize` là API riêng của Hibernate, không phải API chuẩn JPA. Khi có thể, JPQL fetch plan, EntityGraph hoặc DTO projection thường thể hiện ý định rõ hơn và ít phụ thuộc provider.

## 17. Lazy relation trong processor chain

Nếu Step dùng `CompositeItemProcessor`, một delegate có thể truy cập lazy relation trong khi delegate sau chỉ map DTO. Lỗi vẫn xảy ra ở delegate đầu tiên chạm vào proxy chưa tải.

Ví dụ:

```text
Detached OrderEntity
      |
      v
CustomerEnrichmentProcessor
      |
      +--> order.getCustomer().getName()
      |       |
      |       +--> LazyInitializationException
      |
      v
OrderExportMappingProcessor (không được chạy)
```

Hãy thiết kế input của chain sao cho mỗi delegate nhận đủ dữ liệu theo hợp đồng. Có thể dùng projection/DTO từ reader, hoặc để một delegate gọi service tải dữ liệu và trả DTO đã enrichment. Không để delegate sau phụ thuộc ngầm vào lazy proxy mà delegate trước chưa bảo đảm đã tải.

Nếu một delegate trả `null`, chain filter item và các delegate sau không chạy. Đó là semantics khác với lazy loading failure: lazy exception là lỗi xử lý, không phải tín hiệu filter.

## 18. Transaction boundary và service được gọi từ processor

Processor trong chunk Step thường được thực thi trong transaction của chunk, nhưng một service có `@Transactional` chỉ tham gia đúng transaction khi được gọi qua Spring proxy và dùng transaction manager phù hợp.

Ví dụ service riêng:

```java
@Service
public class OrderEnrichmentService {

    private final OrderRepository repository;

    public OrderEnrichmentService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderExport enrich(Long orderId) {
        OrderEntity order = repository.findDetailedById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        CustomerEntity customer = order.getCustomer();
        return new OrderExport(
                order.getId(),
                order.getOrderNumber(),
                customer.getName());
    }
}
```

Processor:

```java
@Component
public class OrderEnrichmentProcessor
        implements ItemProcessor<Long, OrderExport> {

    private final OrderEnrichmentService service;

    public OrderEnrichmentProcessor(OrderEnrichmentService service) {
        this.service = service;
    }

    @Override
    public OrderExport process(Long orderId) {
        return service.enrich(orderId);
    }
}
```

Service chuyển entity thành DTO khi quan hệ còn truy cập được. Không trả `OrderEntity` có lazy relation ra ngoài service rồi mới map ở một tầng không có persistence context.

Nếu Step dùng nhiều transaction manager, hãy chỉ rõ manager cho service và Step. Một service mở transaction trên datasource khác không tự tham gia transaction của chunk.

## 19. Reader trả entity hay trả ID/DTO?

Chọn kiểu item theo nhu cầu xử lý:

| Reader trả về | Ưu điểm | Cần chú ý |
|---|---|---|
| Entity JPA | Thuận tiện khi processor cần các field đã load và domain behavior. | Entity có thể detached; lazy relation chưa tải có thể lỗi. |
| ID | Nhẹ, không mang lazy proxy; dễ reload trạng thái mới. | Có thể tạo thêm query cho mỗi item nếu không batch. |
| DTO projection | Chỉ chứa field cần thiết, không phụ thuộc persistence context. | Cần định nghĩa projection/query; thay đổi field cần sửa mapping. |
| Aggregate DTO | Mang root và dữ liệu con đã tổng hợp. | Query/grouping phức tạp hơn, cần kiểm soát paging và duplicate. |

Nếu processor chỉ tạo output từ vài field, DTO projection thường là lựa chọn rõ ràng. Nếu cần cập nhật entity mới nhất, ID/command rồi reload trong transaction thường phù hợp. Chỉ đưa entity qua pipeline khi hiểu rõ lifecycle và fetch plan của nó.

## 20. Cấu hình transacted của JpaPagingItemReader

`JpaPagingItemReader` có cấu hình `transacted` liên quan đến cách reader quản lý transaction/persistence context cho page. Cấu hình mặc định quản lý transaction đọc page và reader có thể clear persistence context sau page. Có cấu hình chuyên biệt để thay đổi cách reader quản lý context, nhưng giữ entity managed qua nhiều page có thể làm persistence context lớn dần và tăng memory usage.

Không nên bật chế độ giữ context chỉ để tránh sửa processor. Cần cân nhắc:

- EntityManager của reader có phải persistence context mà processor/service đang dùng không?
- Context tồn tại trong bao lâu và khi nào được clear/close?
- Có thể giữ hàng nghìn/hàng triệu entity managed không?
- Lazy query có phát sinh trong lúc xử lý và làm tăng transaction/connection time không?
- Reader có được dùng trong multi-threaded Step không?
- Restart và memory behavior có được kiểm thử không?

Đặc biệt, thay đổi `transacted` không tự biến reader EntityManager thành một context dùng chung với transaction manager của Step. Hãy đọc tài liệu đúng phiên bản và test lifecycle cụ thể trước khi dùng. Fetch plan rõ ràng hoặc DTO projection thường dễ kiểm soát hơn.

## 21. Fetch relation và consistency của dữ liệu

Khi fetch quan hệ trong reader, root entity và relation được lấy theo query/page đó. Nếu processor tải lại relation trong transaction khác hoặc ở thời điểm sau, nó có thể nhìn thấy trạng thái mới hơn.

Hãy quyết định semantics nghiệp vụ:

- Processor cần trạng thái quan hệ tại thời điểm reader đọc root?
- Processor cần trạng thái mới nhất tại thời điểm xử lý?
- Một Job phải dùng snapshot nhất quán xuyên suốt nhiều chunk?
- Nếu customer đổi region giữa lúc đọc và lúc xử lý, output dùng giá trị nào?

Nếu cần snapshot, fetch join/EntityGraph đơn lẻ không bảo đảm mọi page và mọi relation phản ánh cùng một thời điểm. Cần transaction isolation/snapshot hoặc staging/versioned data phù hợp với database và chunk boundary.

Nếu cần trạng thái mới nhất, tải lại trong transaction và xác định cách xử lý khi entity không còn ở trạng thái mong đợi. Không trộn hai semantics một cách vô tình.

## 22. Xử lý quan hệ không tồn tại hoặc bị xóa

Lazy relation có thể không chỉ lỗi vì session đóng. Quan hệ có thể không còn tồn tại hoặc row liên quan bị xóa giữa lúc root được đọc và lúc processor tải lại.

Các trường hợp:

- Foreign key nullable: relation có thể là `null`.
- Row liên quan bị xóa: query reload có thể không tìm thấy entity.
- Referential integrity: database có thể chặn xóa nếu còn foreign key.
- Proxy tham chiếu đến row không tồn tại: provider có thể báo lỗi khi initialize.
- Quan hệ thay đổi giữa hai transaction: processor có thể thấy một relation khác với lúc reader query.

Hãy xác định policy: bỏ qua, reject record, dùng snapshot cũ hoặc fail Step. Không dùng `Optional`/null check để che lỗi dữ liệu không nhất quán nếu đó là vi phạm hợp đồng.

## 23. Kiểm thử lazy relation bị lỗi

Nên có integration test tái hiện đúng lifecycle của reader và processor. Một test đơn giản với entity lazy:

```java
@Test
void detachedEntityCannotInitializeLazyCustomer() throws Exception {
    JpaPagingItemReader<OrderEntity> reader = createOrderReader();
    reader.open(new ExecutionContext());

    OrderEntity order;
    try {
        order = reader.read();
    } finally {
        reader.close();
    }

    assertThatThrownBy(() -> order.getCustomer().getName())
            .isInstanceOf(LazyInitializationException.class);
}
```

Test minh họa cần dùng Hibernate và fixture có customer chưa được fetch. Reader phải được cấu hình tương tự production; nếu query đã fetch customer, assertion lỗi không còn phù hợp. Tên exception và thời điểm phát sinh phụ thuộc provider.

Có thể kiểm tra trạng thái loaded bằng JPA Persistence API:

```java
PersistenceUnitUtil util = entityManagerFactory
        .getPersistenceUnitUtil();

assertThat(util.isLoaded(order, "customer")).isFalse();
```

Với Hibernate, `Hibernate.isInitialized(order.getCustomer())` hoặc collection tương ứng giúp kiểm tra proxy/collection đã được khởi tạo hay chưa. Không gọi getter của association trong test nếu chính getter có thể kích hoạt lazy loading.

## 24. Kiểm thử EntityGraph hoặc fetch join

Với query đã tải relation, test xác nhận relation được khởi tạo và processor map thành công:

```java
@Test
void entityGraphLoadsCustomerForProcessor() {
    OrderEntity order = orderRepository.findDetailedById(orderId)
            .orElseThrow();

    assertThat(entityManagerFactory
            .getPersistenceUnitUtil()
            .isLoaded(order, "customer"))
            .isTrue();

    OrderExport result = processor.process(order);

    assertThat(result.customerName()).isEqualTo("Lan");
}
```

Test này giả định processor không cần các association khác chưa được fetch. Nếu processor dùng `lines`, cần thêm relation đó vào fetch plan hoặc thay bằng projection/service query phù hợp.

Để kiểm tra query count, có thể dùng Hibernate Statistics hoặc datasource proxy trong integration test. Đặt fixture nhiều order có customer khác nhau rồi xác nhận số query không tăng tuyến tính theo số item ngoài dự kiến.

## 25. Kiểm thử DTO projection

Với projection, xác nhận query trả đủ field và processor không cần persistence context:

```java
@Test
void projectionContainsFieldsRequiredByProcessor() {
    OrderProcessData data = reader.read();

    assertThat(data.orderId()).isEqualTo(orderId);
    assertThat(data.customerName()).isEqualTo("Lan");
    assertThat(data.customerRegion()).isEqualTo("VN");

    OrderExport result = processor.process(data);
    assertThat(result.customerName()).isEqualTo("Lan");
}
```

DTO projection là object thông thường, không có lazy proxy. Có thể đóng reader/EntityManager trước khi gọi processor trong unit/integration test để chứng minh processor không phụ thuộc persistence context.

## 26. Kiểm thử N+1 và paging collection

Một test hiệu năng/SQL nên bao gồm:

- Page có nhiều root entity.
- Số customer/association khác nhau.
- Một số root không có relation.
- Một root có nhiều child rows.
- Số page lớn hơn một.
- Reader restart giữa page nếu Step cần restart.

Kiểm tra:

- Số SQL select không tăng tuyến tính theo item ngoài dự kiến.
- Pagination trả đúng số root entity và không trùng/thiếu.
- Collection fetch plan không khiến provider load toàn bộ result vào memory.
- Query plan sử dụng index phù hợp.
- DTO/projection có giá trị đúng cho root không có child.

Không chỉ dùng một fixture có một order và một customer; fixture nhỏ đó không phát hiện N+1 hoặc row multiplication.

## 27. Những lỗi thường gặp

### Truy cập lazy relation trên entity detached

Processor gọi getter của proxy/collection sau khi reader clear/close persistence context. Fetch relation trong query, dùng DTO hoặc reload entity trong transaction.

### Nghĩ transaction của Step tự attach entity của reader

Reader có thể dùng EntityManager riêng. Transaction chunk mới không tự nhận proxy cũ. Tải lại entity trong context hiện tại.

### Thêm @Transactional nhưng vẫn dùng proxy cũ

Transaction mới không tự khởi tạo proxy gắn với EntityManager cũ. Dùng ID để query lại hoặc fetch dữ liệu trước khi detach.

### Đổi mọi relation thành EAGER

Có thể tạo object graph lớn, N+1 và tải dữ liệu không cần thiết. Chọn fetch plan theo use case.

### JOIN FETCH collection với paging

Row multiplication làm pagination sai hoặc buộc provider phân trang trong memory. Dùng DTO, page IDs rồi tải child theo nhóm hoặc reader aggregate.

### Dùng EntityGraph và giả định chỉ có một query

Provider có thể phát sinh query phụ. Kiểm tra SQL/query count thực tế.

### Merge entity detached để tải mọi relation

Merge không phải cơ chế fetch plan và có thể gây thêm query/version conflict. Query theo ID với EntityGraph hoặc projection rõ ràng hơn.

### Gọi Hibernate.initialize trên entity đã detached

Không có session để initialize. Gọi trong context còn mở hoặc tải lại entity trong service.

### Tạo N+1 khi reload từng item

Processor query lại từng entity/association. Dùng projection, fetch plan hoặc bulk query theo nhóm ID và đo query count.

### Dựa vào OSIV

Batch không có HTTP request scope như web. Quản lý persistence context và transaction rõ ràng trong Job.

### Không xác định semantics dữ liệu

Fetch trong reader và reload trong processor có thể nhìn thấy hai trạng thái khác nhau. Chọn snapshot hoặc latest-state semantics theo nghiệp vụ.

## 28. Quy trình xử lý lazy relation trong processor

Khi processor cần dữ liệu quan hệ, hãy làm theo trình tự:

1. Xác định chính xác association và field processor cần.
2. Xác định reader có trả entity detached hay DTO/ID; kiểm tra lifecycle `EntityManager` của reader.
3. Nếu chỉ cần vài field, ưu tiên DTO projection trong query.
4. Nếu cần một quan hệ to-one, cân nhắc `JOIN FETCH` hoặc EntityGraph.
5. Nếu cần collection, tránh fetch join collection trực tiếp với paging khi chưa chứng minh pagination đúng; cân nhắc aggregate/projection hoặc query theo nhóm ID.
6. Nếu cần trạng thái mới nhất, reader trả ID/command và service tải lại entity trong transaction.
7. Map sang DTO trước khi rời transaction; không trả lazy proxy qua các tầng sau.
8. Không dùng `EAGER` toàn cục hoặc OSIV để che vấn đề.
9. Đo SQL/query count để phát hiện N+1 và kiểm tra execution plan.
10. Kiểm thử lazy exception, loaded association, paging collection, restart và dữ liệu thay đổi.
11. Xác định rõ snapshot/latest-state semantics giữa reader và processor.

| Nhu cầu | Cách xử lý phù hợp |
|---|---|
| Processor cần field của quan hệ to-one | `JOIN FETCH` hoặc EntityGraph trên query phù hợp |
| Processor chỉ cần vài field từ nhiều bảng | DTO projection |
| Processor cần trạng thái entity mới nhất | Đọc ID/command rồi reload qua service `@Transactional` |
| Processor cần collection con khi paging | Aggregate DTO, query riêng theo nhóm ID hoặc custom reader; tránh fetch join collection tùy tiện |
| Entity đã detached và cần đọc lazy relation | Không dùng proxy cũ; tải lại entity trong persistence context mới |
| Muốn xác nhận relation đã được tải | `PersistenceUnitUtil.isLoaded` hoặc API kiểm tra của provider |
| Muốn giảm N+1 | Fetch plan rõ ràng, projection, batch query và kiểm tra SQL count |

## Kết luận

Lazy relation trong processor dễ gây `LazyInitializationException` khi entity được đọc bởi `JpaPagingItemReader` đã detached sau lifecycle page của persistence context riêng. Transaction của chunk hoặc `@Transactional` trên processor không tự gắn lại proxy thuộc EntityManager cũ. Hãy chọn fetch plan theo dữ liệu cần: `JOIN FETCH`/EntityGraph cho quan hệ phù hợp, DTO projection khi chỉ cần một số field, hoặc đọc ID rồi tải lại entity trong service có transaction khi cần trạng thái mới nhất. Tránh đổi mọi mapping sang `EAGER`, tránh fetch join collection trực tiếp với paging nếu chưa kiểm chứng và kiểm tra N+1 bằng query count. Map dữ liệu quan hệ thành DTO trước khi rời persistence context, đồng thời kiểm thử lifecycle reader, loaded state, pagination và semantics snapshot/latest-state của Job.
