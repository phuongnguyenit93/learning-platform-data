# N+1 query trong processor

Trong Spring Batch, `ItemProcessor` được gọi cho từng item mà reader trả về. Nếu processor truy vấn database thêm cho mỗi item, hoặc truy cập các association JPA được tải lazy, một chunk có thể tạo ra rất nhiều câu SQL nhỏ. Đây là nguyên nhân phổ biến của hiện tượng **N+1 query**: một query ban đầu lấy N bản ghi, sau đó phát sinh thêm N query để lấy dữ liệu liên quan.

N+1 thường không làm Job thất bại. Job vẫn có thể hoàn tất đúng về mặt kết quả nhưng chậm dần khi số item tăng, tạo tải lớn lên database, tăng round trip mạng và giữ transaction lâu hơn. Cách xử lý hiệu quả thường là lấy đủ dữ liệu ngay từ query của reader, dùng projection/EntityGraph/fetch join phù hợp, hoặc gom việc tra cứu theo lô thay vì gọi repository lặp lại trong processor.

## 1. N+1 query là gì?

Giả sử reader lấy 100 đơn hàng bằng một câu query:

```sql
SELECT order_id, customer_id, amount
FROM orders
WHERE status = 'READY';
```

Sau đó processor cần tên khách hàng và gọi `customerRepository.findById(...)` cho từng đơn hàng. Nếu mỗi đơn hàng thuộc một khách hàng khác nhau, database có thể nhận:

- 1 query lấy danh sách 100 đơn hàng.
- 100 query lấy từng khách hàng.

Tổng cộng 101 query để xử lý 100 item. Đó là mẫu N+1.

```text
Reader: SELECT orders ...                 1 query
       |
       +--> Order 1 --> SELECT customer WHERE id = 1
       +--> Order 2 --> SELECT customer WHERE id = 2
       +--> Order 3 --> SELECT customer WHERE id = 3
       |                         ...
       +--> Order N --> SELECT customer WHERE id = N

Tổng: 1 + N query
```

Nếu một processor còn đọc collection `order.lines` và sau đó đọc `line.product`, có thể xuất hiện nhiều tầng N+1: một query cho orders, một query cho mỗi order để lấy lines, rồi một query cho mỗi line để lấy product.

N+1 là vấn đề về số lượng query và cách tải dữ liệu. Nó không nhất thiết có nghĩa mỗi query đều chậm; hàng trăm query nhỏ vẫn tạo overhead lớn do round trip, parse/plan, quản lý connection và tải database.

## 2. Vì sao N+1 thường xuất hiện trong ItemProcessor?

Processor được gọi riêng cho từng item:

```java
public OrderSummary process(Order order) {
    Customer customer = customerRepository.findById(order.getCustomerId())
            .orElseThrow();

    return new OrderSummary(
            order.getId(),
            customer.getName(),
            order.getAmount()
    );
}
```

Với chunk 100 item, đoạn code có thể gọi repository 100 lần. Transaction của chunk có thể vẫn chỉ là một transaction, nhưng điều đó không tự gộp 100 lần gọi repository thành một query. Một transaction không đồng nghĩa với một lần truy cập database.

Các nguyên nhân phổ biến:

- Processor gọi `findById()` hoặc `findBy...()` cho từng item.
- Processor duyệt association `LAZY` của entity và mỗi lần truy cập làm phát sinh SELECT.
- Processor gọi nhiều repository/service mà bên trong mỗi service lại query database.
- Mapper/converter được gọi trong processor vô tình truy cập association lazy.
- Logging hoặc biểu thức `toString()`/serialization truy cập getter lazy.
- Một processor lồng nhau thực hiện lookup theo item mà không có cache hoặc batch query.

Đặc biệt, N+1 có thể bị ẩn trong getter của entity. Nhìn code processor có vẻ chỉ đọc `order.getCustomer().getName()`, nhưng getter đó có thể kích hoạt một câu SELECT nếu `customer` chưa được tải.

## 3. N+1 từ repository lookup cho từng item

Một cách viết dễ gặp:

```java
@Component
public class OrderProcessor implements ItemProcessor<Order, OrderSummary> {

    private final CustomerRepository customerRepository;

    public OrderProcessor(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    @Override
    public OrderSummary process(Order order) {
        Customer customer = customerRepository.findById(order.getCustomerId())
                .orElseThrow(() -> new IllegalArgumentException(
                        "Customer not found: " + order.getCustomerId()));

        return new OrderSummary(
                order.getId(),
                customer.getName(),
                order.getAmount()
        );
    }
}
```

Nếu 500 orders tham chiếu 500 customer khác nhau, processor có thể phát sinh 500 lookup query. Nếu nhiều order dùng cùng customer và tất cả lookup tham gia cùng persistence context, first-level cache có thể giảm số query cho ID đã được quản lý. Tuy nhiên, với các ID khác nhau, vẫn có một query cho mỗi customer.

Không nên dựa vào việc dữ liệu trùng lặp để coi N+1 đã được giải quyết. Khi số lượng ID khác nhau tăng, số query vẫn tăng gần tuyến tính theo số item.

## 4. N+1 từ lazy association

JPA thường dùng `FetchType.LAZY` cho collection và có thể dùng lazy cho một số association to-one tùy mapping/provider. Ví dụ:

```java
@Entity
public class Order {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();
}
```

Reader lấy danh sách `Order`, sau đó processor gọi:

```java
order.getCustomer().getName();
order.getLines().size();
```

Nếu association chưa được tải và entity vẫn gắn với persistence context đang hoạt động, provider có thể thực hiện SELECT để tải từng association. Khi có nhiều Order, các lần truy cập này có thể tạo N+1.

Ví dụ query pattern:

```sql
SELECT ... FROM orders ...;                  -- 1 query
SELECT ... FROM customer WHERE id = ?;       -- lặp theo từng Order
SELECT ... FROM order_line WHERE order_id=?; -- lặp theo từng Order
```

Đây là lý do cần xem SQL thực tế khi tối ưu JPA. Một association `LAZY` không tự động là vấn đề; vấn đề xuất hiện khi ứng dụng truy cập association theo cách làm phát sinh quá nhiều query.

## 5. Phân biệt N+1 với LazyInitializationException

N+1 và `LazyInitializationException` có liên quan đến lazy loading nhưng là hai kết quả khác nhau.

- **N+1 query:** persistence context còn hoạt động, nên truy cập association lazy kích hoạt nhiều query riêng lẻ.
- **LazyInitializationException:** entity đã detached hoặc persistence context đã đóng, nên association lazy không thể được tải.

Trong Spring Batch, điều này phụ thuộc reader và transaction lifecycle. Ví dụ, `JpaPagingItemReader` thực hiện page read và clear persistence context theo lifecycle của nó; entity trả về có thể detached. Nếu processor truy cập association chưa tải, ứng dụng có thể nhận `LazyInitializationException` thay vì N+1.

Không nên bật một persistence context mở kéo dài chỉ để che lỗi lazy loading. Cần xác định dữ liệu processor thực sự cần và fetch dữ liệu đó một cách có chủ đích trong query hoặc projection.

## 6. Transaction của chunk không loại bỏ N+1

Spring Batch thường xử lý mỗi chunk trong một transaction:

```text
Begin chunk transaction
   |
   +--> read item 1
   +--> process item 1 -> repository query
   +--> read item 2
   +--> process item 2 -> repository query
   +--> ...
   +--> write chunk
   +--> commit
```

Nếu các repository dùng cùng `DataSource`, transaction manager và persistence context phù hợp, các query có thể tham gia transaction hiện tại. Nhưng JPA vẫn thực thi từng query theo lời gọi. Một transaction có thể chứa 101 SELECT.

Đặt `@Transactional` cho processor hoặc service không tự giải quyết N+1. Annotation chỉ ảnh hưởng transaction boundary/propagation khi method được gọi qua Spring proxy. Nếu method tham gia transaction chunk hiện tại với `REQUIRED`, nó vẫn có thể phát sinh một query cho mỗi item.

Tránh tạo `REQUIRES_NEW` cho mỗi item chỉ để xử lý lookup. Cách đó có thể tạo thêm transaction/connection overhead, phá vỡ atomicity của chunk và làm số query không giảm.

## 7. Cách đầu tiên: lấy dữ liệu cần thiết ngay trong query reader

Nếu processor luôn cần customer của order, có thể sửa query đọc để lấy customer cùng lúc. Với quan hệ to-one, `JOIN FETCH` thường là một lựa chọn:

```java
@Query("""
       select o
       from Order o
       join fetch o.customer
       where o.status = :status
       order by o.id
       """)
List<Order> findReadyOrdersWithCustomer(@Param("status") OrderStatus status);
```

Khi reader dùng query tương đương, customer được tải cùng orders trong một query thay vì query riêng khi processor truy cập `getCustomer()`.

Trong JPA, `JOIN FETCH` thay đổi fetch plan của query. Nó không có nghĩa mọi association khác cũng được tải. Chỉ fetch những quan hệ processor/writer thực sự cần để tránh tải quá nhiều dữ liệu.

Nếu dùng `JpaPagingItemReader`, có thể cấu hình JPQL query với fetch join phù hợp, nhưng phải chú ý giới hạn pagination khi fetch collection.

## 8. Fetch join cho to-one association

Các quan hệ `@ManyToOne` và `@OneToOne` thường có số row join dễ kiểm soát hơn collection. Ví dụ:

```java
@Query("""
       select o
       from Order o
       left join fetch o.customer
       where o.id between :fromId and :toId
       order by o.id
       """)
List<Order> findOrdersWithCustomer(
        @Param("fromId") long fromId,
        @Param("toId") long toId);
```

`LEFT JOIN FETCH` giữ lại Order ngay cả khi association customer là null. `JOIN FETCH` thông thường loại các Order không có customer khỏi kết quả. Chọn loại join theo quy tắc nghiệp vụ.

Fetch join to-one thường phù hợp cho page query hơn fetch join collection, nhưng vẫn cần kiểm tra SQL, số row, count query và execution plan trên database thực tế.

## 9. EntityGraph để khai báo fetch plan

Spring Data JPA hỗ trợ `@EntityGraph` để khai báo association cần tải cho một repository method:

```java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @EntityGraph(attributePaths = {"customer"})
    Page<Order> findByStatus(OrderStatus status, Pageable pageable);
}
```

Processor có thể truy cập `order.getCustomer()` mà không cần query riêng cho từng Order, vì customer đã được yêu cầu trong fetch graph của query.

EntityGraph giúp tách fetch plan khỏi JPQL. Nó hữu ích khi muốn dùng lại query method nhưng thay đổi association cần tải theo use case.

Với collection, cần kiểm tra SQL và pagination behavior của provider. EntityGraph không loại bỏ các vấn đề cardinality khi fetch nhiều collection hoặc phân trang trên join collection.

## 10. Vì sao fetch join collection có thể phá pagination?

Giả sử một Order có nhiều OrderLine. Query:

```jpql
select o
from Order o
left join fetch o.lines
where o.status = :status
order by o.id
```

Kết quả SQL có một row cho mỗi cặp Order/OrderLine. Một Order có 5 lines có thể chiếm 5 row. Nếu áp dụng `LIMIT/OFFSET` trực tiếp lên row join, page có thể bị cắt giữa các dòng của cùng một Order.

Một số JPA provider có thể cảnh báo và thực hiện pagination trong memory khi collection fetch join được kết hợp với pagination. Điều đó có thể tải nhiều row hơn dự kiến và làm giảm hiệu năng nghiêm trọng.

Vì vậy:

- Fetch join to-one thường dễ dùng với pagination hơn.
- Tránh fetch join collection trong query phân trang nếu chưa hiểu rõ hành vi provider.
- Dùng batch fetching cho collection hoặc tải collection theo query thứ hai có kiểm soát.
- Có thể page ID trước, sau đó bulk fetch dữ liệu liên quan cho page đó bằng một query `IN`.

Không chỉ dựa vào việc query chạy thành công; kiểm tra log SQL và execution plan để chắc chắn database không bị yêu cầu tải toàn bộ tập dữ liệu.

## 11. Page ID trước, bulk fetch dữ liệu liên quan

Một chiến lược hữu ích với collection là chia thành hai bước:

1. Lấy một page ID Order theo thứ tự ổn định.
2. Lấy các Order/association cần thiết cho toàn bộ ID trong một query bulk.

Ví dụ query ID:

```sql
SELECT order_id
FROM orders
WHERE status = ?
  AND order_id > ?
ORDER BY order_id
FETCH FIRST 100 ROWS ONLY;
```

Sau đó lấy lines cho cả page:

```sql
SELECT line.order_id, line.line_id, line.sku, line.quantity
FROM order_line line
WHERE line.order_id IN (?, ?, ..., ?)
ORDER BY line.order_id, line.line_id;
```

Ứng dụng nhóm các lines theo `order_id` rồi tạo DTO cho processor. Cú pháp giới hạn page phụ thuộc database; `FETCH FIRST` không phải cú pháp chung cho mọi hệ quản trị.

Hai query cho một page thường dễ kiểm soát hơn một query collection fetch join có pagination. Cần giới hạn số ID trong `IN` theo khả năng database/driver và giữ thứ tự item theo page ID ban đầu khi ghép kết quả.

## 12. DTO projection để tránh tải entity graph

Nếu processor chỉ cần một số field, không nhất thiết phải đọc entity JPA đầy đủ rồi truy cập association. Có thể dùng DTO projection để query đúng dữ liệu cần.

Ví dụ DTO:

```java
public record OrderProcessingData(
        Long orderId,
        String customerName,
        BigDecimal amount,
        String customerTier
) {
}
```

JPQL constructor projection:

```java
@Query("""
       select new com.example.batch.OrderProcessingData(
           o.id,
           c.name,
           o.amount,
           c.tier
       )
       from Order o
       join o.customer c
       where o.status = :status
       order by o.id
       """)
Page<OrderProcessingData> findProcessingData(
        @Param("status") OrderStatus status,
        Pageable pageable);
```

Reader có thể trả về `OrderProcessingData` thay vì entity. Processor nhận sẵn dữ liệu cần thiết và không cần gọi repository để lấy customer.

Ưu điểm:

- Chỉ lấy các cột cần dùng.
- Tránh lazy association ngoài ý muốn.
- Giảm chi phí materialize entity và dirty checking.
- Làm rõ input contract của processor.
- Dễ kiểm thử processor độc lập với persistence context.

DTO projection đặc biệt hữu ích cho batch export, reporting và transformation không cần cập nhật entity nguồn.

## 13. Interface projection của Spring Data JPA

Spring Data JPA cũng hỗ trợ interface projection:

```java
public interface OrderSummaryView {
    Long getOrderId();
    String getCustomerName();
    BigDecimal getAmount();
}
```

Repository:

```java
@Query("""
       select o.id as orderId,
              c.name as customerName,
              o.amount as amount
       from Order o
       join o.customer c
       where o.status = :status
       order by o.id
       """)
Page<OrderSummaryView> findOrderSummaries(
        @Param("status") OrderStatus status,
        Pageable pageable);
```

Projection interface phù hợp khi dữ liệu cần trả về là tập scalar property. Với DTO cần constructor rõ ràng hoặc logic chuyển đổi riêng, record/class projection có thể dễ đọc hơn.

Kiểm tra generated SQL và kiểu dữ liệu trả về; tên alias phải khớp getter của projection.

## 14. Hibernate batch fetching

Nếu dùng Hibernate, có thể cấu hình batch fetching để khi một số lazy proxy cùng loại được truy cập, provider tải nhiều entity trong một query `IN` thay vì mỗi proxy một query.

Ví dụ đặt `@BatchSize` trên entity Customer:

```java
@Entity
@BatchSize(size = 50)
public class Customer {
    @Id
    private Long id;

    private String name;
}
```

Hoặc đặt trên association collection:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 50)
private List<OrderLine> lines = new ArrayList<>();
```

Có thể cấu hình mặc định trong Hibernate:

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=50
```

Thay vì:

```sql
SELECT ... FROM customer WHERE id = 1;
SELECT ... FROM customer WHERE id = 2;
SELECT ... FROM customer WHERE id = 3;
```

Hibernate có thể gom các ID chưa tải:

```sql
SELECT ... FROM customer WHERE id IN (1, 2, 3, ...);
```

Batch fetching là tính năng của Hibernate, không phải annotation chuẩn JPA. Nó phụ thuộc persistence context có các proxy/collection cùng loại cần được tải. Nếu entity đã detached hoặc persistence context bị clear trước khi truy cập, batch fetching không thể tải association lazy như mong đợi.

Batch size không nhất thiết bằng chunk size. Chọn theo số proxy có thể được truy cập đồng thời, giới hạn bind parameter của database và kích thước query.

## 15. SUBSELECT fetch cho collection

Hibernate còn có `@Fetch(FetchMode.SUBSELECT)` cho một số collection. Khi một collection được truy cập, Hibernate có thể tải collection tương ứng cho các owner đã được load trong cùng persistence context bằng một subselect thay vì một query cho mỗi owner.

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<OrderLine> lines = new ArrayList<>();
```

Đây là tính năng riêng của Hibernate. Nó có thể hữu ích khi nhiều parent trong một persistence context cần cùng collection role, nhưng query tải collection có thể lấy nhiều dữ liệu hơn item hiện tại cần.

Không áp dụng `SUBSELECT` một cách toàn cục mà không đo. Kiểm tra SQL thực tế, số owner trong persistence context và kích thước collection. Với reader clear persistence context theo page, phạm vi owner được gom cũng có thể khác với kỳ vọng.

## 16. Tải lookup data một lần thay vì query trong từng item

Một số processor cần tra cứu dữ liệu tham chiếu tương đối nhỏ, ví dụ bảng mã quốc gia, loại phí hoặc cấu hình chuyển đổi. Nếu tập lookup nhỏ và ổn định, có thể tải một lần khi Step bắt đầu rồi tra cứu trong memory.

Ví dụ service cache dữ liệu tham chiếu:

```java
@Component
@StepScope
public class CountryLookup {

    private final CountryRepository repository;
    private Map<String, CountryInfo> byCode;

    public CountryLookup(CountryRepository repository) {
        this.repository = repository;
    }

    @PostConstruct
    public void load() {
        byCode = repository.findAll().stream()
                .collect(Collectors.toUnmodifiableMap(
                        Country::getCode,
                        country -> new CountryInfo(country.getName(), country.getRegion())
                ));
    }

    public CountryInfo find(String code) {
        return byCode.get(code);
    }
}
```

Processor dùng map:

```java
@Component
public class OrderProcessor implements ItemProcessor<Order, OrderSummary> {

    private final CountryLookup countryLookup;

    public OrderProcessor(CountryLookup countryLookup) {
        this.countryLookup = countryLookup;
    }

    @Override
    public OrderSummary process(Order order) {
        CountryInfo country = countryLookup.find(order.getCountryCode());
        if (country == null) {
            throw new IllegalArgumentException("Unknown country code");
        }
        return new OrderSummary(order.getId(), country.name(), order.getAmount());
    }
}
```

Ví dụ này phù hợp khi bảng lookup nhỏ, có thể tải toàn bộ và version của dữ liệu tham chiếu được kiểm soát. Với bảng lớn, không nên `findAll()` rồi giữ toàn bộ trong heap.

Trong Spring Batch, `@PostConstruct` chạy theo lifecycle bean và có thể xảy ra trước khi StepExecution/JobParameters được bind tùy scope. Nếu cần load đúng một lần khi Step mở, có thể triển khai một component `ItemStream` hoặc dùng listener để tải lookup trong lifecycle Step. Cần xử lý rõ khi reload/restart và bảo đảm dữ liệu lookup không thay đổi giữa các chunk nếu nghiệp vụ yêu cầu cùng version.

## 17. Bulk lookup theo nhóm ID

Nếu processor cần lookup nhiều ID khác nhau, một query bulk có thể hiệu quả hơn N query đơn:

```java
List<Customer> findByIdIn(Collection<Long> ids);
```

Query tương ứng thường dùng `WHERE id IN (...)`. Tuy nhiên, `ItemProcessor.process(item)` nhận từng item, không nhận cả chunk. Vì vậy, không thể đơn giản lấy toàn bộ ID của chunk từ bên trong một processor chuẩn.

Các cách thiết kế phù hợp:

- Đưa lookup vào query của reader bằng join/projection.
- Tải trước một tập lookup có giới hạn khi Step mở.
- Dùng một reader tùy chỉnh trả về dữ liệu đã enrich theo page/batch.
- Thiết kế một bước tiền xử lý gom ID rồi bulk fetch, nếu nghiệp vụ cho phép thay đổi pipeline.
- Dùng cache bounded để giảm lookup lặp cho các ID trùng, nhưng không kỳ vọng cache loại bỏ N+1 với mọi ID duy nhất.

Không nên tạo một biến static chứa danh sách ID toàn Job hoặc giữ cache không giới hạn trong singleton processor. Điều đó có thể gây rò bộ nhớ, rò dữ liệu giữa các JobExecution và kết quả không nhất quán.

## 18. Cache có giải quyết N+1 không?

Cache có thể giảm số query nếu nhiều item tra cứu cùng một key. Ví dụ 1.000 orders nhưng chỉ có 20 customer khác nhau; cache theo customer ID có thể giảm lookup từ 1.000 xuống khoảng 20 query.

Tuy nhiên, nếu mỗi item có một customer ID riêng, cache vẫn cần 1.000 lần tải. Cache chỉ giúp khi key được lặp lại hoặc dữ liệu đã được preload.

Khi dùng cache trong batch, cần cân nhắc:

- Scope theo Job/Step hay application.
- Kích thước tối đa và eviction policy.
- Dữ liệu tham chiếu thay đổi trong lúc Job chạy.
- Cache invalidation khi restart.
- Không chia sẻ dữ liệu nhạy cảm giữa tenant hoặc JobExecution.
- Đo hit ratio và số query thực tế.

First-level cache của JPA là persistence context cache. Nó tránh tải lại cùng entity identity trong cùng persistence context, nhưng không tự batch-fetch các ID khác nhau. Second-level cache có thể giúp nếu dữ liệu đã có trong cache, nhưng không nên dùng cache như cách duy nhất để che query pattern N+1.

## 19. Persistence context và JPA reader trong Spring Batch

JPA entity chỉ có thể lazy-load association khi còn gắn với một persistence context hoạt động. Cách reader quản lý EntityManager ảnh hưởng trực tiếp đến processor.

Với `JpaPagingItemReader`, reader thường quản lý EntityManager riêng và thực hiện page query theo lifecycle của nó. Trong quá trình đọc page, entity có thể được flush/clear và trở thành detached trước khi được processor xử lý. Khi đó:

- Association đã được fetch trong query có thể truy cập bình thường.
- Association lazy chưa tải có thể ném `LazyInitializationException` khi processor truy cập.
- Không nên giả định transaction của chunk sẽ tự gắn lại mọi entity detached vào persistence context của reader.

Với custom reader hoặc repository reader khác, entity có thể được trả về trong persistence context của transaction chunk. Khi processor truy cập lazy association, query có thể chạy và tạo N+1.

Do đó, khi tối ưu cần xác định rõ reader implementation, EntityManager lifecycle, transaction manager và thời điểm entity bị detach. Đừng áp dụng một giải pháp fetch plan mà không kiểm tra entity có còn managed tại thời điểm processor chạy.

## 20. Không dùng Open Session in View làm giải pháp batch

Trong ứng dụng web, Open Session in View có thể giữ persistence context mở đến hết HTTP request để view truy cập lazy association. Đây không phải cách giải quyết phù hợp cho Spring Batch.

Batch Job có lifecycle dài, nhiều chunk và có thể restart. Giữ persistence context mở toàn Job có thể:

- Làm persistence context phình lớn.
- Giữ entity và snapshot lâu hơn cần thiết.
- Tăng dirty checking và memory pressure.
- Che giấu query phát sinh từ getter.
- Làm behavior khác nhau giữa môi trường web và scheduler.

Hãy thiết kế query/fetch plan để processor nhận đủ dữ liệu. Không phụ thuộc vào việc một session vô tình còn mở để lazy load hoạt động.

## 21. Không đổi mọi association sang EAGER

Một phản ứng thường gặp khi gặp N+1 là đổi `FetchType.LAZY` thành `FetchType.EAGER`. Điều này có thể làm một use case hết N+1 nhưng tạo tải dữ liệu thừa ở mọi query khác.

Rủi ro:

- Entity query ở nơi không cần association vẫn tải association.
- Nhiều association EAGER có thể tạo thêm query hoặc join phức tạp.
- Collection EAGER có thể làm result set lớn và tăng memory.
- Khó kiểm soát fetch plan theo từng batch use case.
- Nhiều collection EAGER có thể gây lỗi multiple bag fetch hoặc Cartesian product tùy Hibernate mapping.

Thông thường nên giữ mapping domain phù hợp, rồi chọn fetch plan theo query/use case bằng `JOIN FETCH`, `EntityGraph`, projection hoặc batch fetching.

## 22. Phân biệt N+1 với query chậm

Một query có thể chậm vì thiếu index, join phức tạp hoặc đọc quá nhiều row. N+1 là vấn đề số lượng query tăng theo số item. Hai vấn đề có thể cùng tồn tại.

Ví dụ:

| Tình huống | Dấu hiệu |
|---|---|
| Một query chậm | Ít query nhưng mỗi query có latency/scan cao |
| N+1 | Một query ban đầu và nhiều query lặp cùng mẫu với tham số khác nhau |
| Over-fetching | Ít query nhưng mỗi query trả quá nhiều cột/row |
| Cartesian product | Join nhiều collection làm số row tăng mạnh |
| Connection contention | Query có thể nhanh riêng lẻ nhưng chờ lấy connection lâu |

Hãy xem SQL log, query count, bind parameters và execution plan. Chỉ tăng index không giải quyết được 500 round trip nếu processor vẫn gọi repository 500 lần.

## 23. Đo N+1 bằng Hibernate Statistics

Hibernate có thể cung cấp thống kê query để quan sát số statement. Trong môi trường test hoặc profiling, bật statistics:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Trong test có thể lấy `SessionFactory` và đọc thống kê:

```java
SessionFactory sessionFactory = entityManagerFactory
        .unwrap(SessionFactory.class);

Statistics statistics = sessionFactory.getStatistics();
statistics.clear();

// Chạy reader/processor trên tập dữ liệu test.

long preparedStatements = statistics.getPrepareStatementCount();
```

`getPrepareStatementCount()` đếm số prepared statement được tạo theo thống kê Hibernate. Cần reset statistics trước vùng đo và tránh để setup/test fixture query làm nhiễu số liệu.

Có thể dùng datasource proxy hoặc JDBC instrumentation để đếm query ở mức connection. Đây là cách hữu ích nếu ứng dụng dùng nhiều thư viện truy cập database, không chỉ Hibernate.

Không bật verbose SQL logging toàn thời gian trong production nếu lượng dữ liệu lớn. Dùng sampling, metrics hoặc profiling có kiểm soát.

## 24. Kiểm thử query count theo số item

Một dấu hiệu tốt để phát hiện N+1 là so sánh query count khi tăng số item. Nếu 10 item tạo khoảng 11 query và 100 item tạo khoảng 101 query, query count đang tăng gần tuyến tính theo số item.

Ví dụ chiến lược test:

1. Tạo 10 Order, mỗi Order tham chiếu một Customer riêng.
2. Clear persistence context trước khi chạy để tránh cache làm sai số đo.
3. Reset Hibernate Statistics.
4. Chạy query/processor cho 10 item và ghi số statement.
5. Lặp với 100 item cùng cấu trúc.
6. Sau khi tối ưu, xác nhận số query tăng theo số page/batch hợp lý thay vì tăng một query cho mỗi item.

Không nhất thiết kiểm tra một con số tuyệt đối cố định trong mọi phiên bản provider. Count có thể thay đổi do count query, sequence, schema validation hoặc framework metadata. Điều quan trọng là kiểm tra query pattern và mức tăng khi input tăng.

## 25. Ví dụ trước và sau khi tối ưu

### Trước: repository lookup trong processor

```java
public OrderSummary process(Order order) {
    Customer customer = customerRepository.findById(order.getCustomerId())
            .orElseThrow();

    return new OrderSummary(order.getId(), customer.getName(), order.getAmount());
}
```

Nếu có N customer ID khác nhau, processor có thể tạo N query bổ sung.

### Sau: reader query trả DTO

```java
@Query("""
       select new com.example.batch.OrderSummary(
           o.id, c.name, o.amount
       )
       from Order o
       join o.customer c
       where o.status = :status
       order by o.id
       """)
Page<OrderSummary> findSummaries(
        @Param("status") OrderStatus status,
        Pageable pageable);
```

Processor không cần lookup:

```java
public OrderSummary process(OrderSummary summary) {
    return summary.withNormalizedAmount(summary.amount());
}
```

Trong ví dụ, dữ liệu customer được lấy trong query đọc page. Không còn một query riêng cho mỗi item chỉ để lấy tên customer.

## 26. Tối ưu khi processor cần cập nhật entity

Không phải batch nào cũng chỉ đọc và xuất DTO. Có thể processor cần kiểm tra nhiều association rồi writer cập nhật entity. Khi đó:

- Fetch trước các association cần dùng bằng query/entity graph.
- Chỉ merge entity detached nếu thực sự cần và hiểu chi phí.
- Dùng update query hoặc repository operation theo lô nếu nghiệp vụ phù hợp.
- Tránh gọi `save()` riêng cho từng association nếu có thể ghi theo chunk.
- Chú ý persistence context và flush/clear để không giữ hàng nghìn entity lâu.

Ví dụ processor có thể nhận DTO chứa các giá trị cần để quyết định, rồi writer thực hiện cập nhật database bằng batch SQL. Cách này tránh tải một entity graph lớn chỉ để đọc vài field.

Nếu cần cập nhật entity managed, đảm bảo entity thuộc đúng persistence context và transaction. Không gọi `merge()` cho từng item một cách máy móc; merge có thể tạo thêm SELECT hoặc copy state và không tự giải quyết N+1 ở association.

## 27. Tác động của chunk size

Chunk size lớn hơn không tự loại bỏ N+1. Nếu mỗi item tạo một query, chunk 100 vẫn có thể tạo 100 query; chunk 1.000 có thể tạo 1.000 query trong một transaction.

Chunk size ảnh hưởng:

- Số item trong một transaction.
- Số lần commit.
- Kích thước persistence context/buffer nếu entity còn managed.
- Thời gian transaction và lock duration.
- Kích thước dữ liệu phải replay khi rollback.

Giảm chunk size có thể giảm thời gian giữ transaction nhưng không giải quyết số query trên mỗi item. Tăng chunk size có thể làm số query trong một transaction lớn hơn và transaction kéo dài hơn.

Hãy giải quyết fetch pattern trước, sau đó đo và điều chỉnh chunk size theo throughput, memory và transaction behavior.

## 28. Tác động của cache và first-level persistence context

JPA persistence context giữ một identity map: cùng một entity type và primary key thường chỉ có một managed instance trong context. Nếu processor nhiều lần gọi `findById(42)` trong cùng persistence context, provider có thể trả entity đã managed mà không query lại.

Nhưng có các giới hạn:

- Mỗi ID duy nhất vẫn cần tải lần đầu.
- Persistence context có thể bị clear giữa các page hoặc chunk tùy reader/lifecycle.
- Entity detached không lazy-load được.
- Cache không bảo đảm dữ liệu tham chiếu cùng version xuyên suốt nhiều transaction.
- Cache toàn application có thể tạo stale data hoặc rò dữ liệu giữa tenant nếu key/scope sai.

Do đó, first-level cache có thể giảm query trùng lặp nhưng không phải giải pháp tổng quát cho N+1. Fetch plan rõ ràng vẫn quan trọng.

## 29. Checklist thiết kế processor tránh N+1

Trước khi đưa processor vào production, hãy xác định:

- Processor cần những field/association nào?
- Những field đó có thể được lấy cùng query reader không?
- Có repository lookup nào đang chạy một lần cho mỗi item không?
- Có getter lazy nào bị gọi trong mapper, logger hoặc serializer không?
- Entity còn managed tại thời điểm process hay đã detached?
- Có thể dùng DTO projection hoặc EntityGraph không?
- Nếu dùng collection fetch, pagination có bị ảnh hưởng không?
- Hibernate batch fetching có phù hợp với persistence context và association không?
- Lookup cache có giới hạn kích thước và version không?
- Query count có tăng tuyến tính theo số item không?
- SQL có index phù hợp và trả đúng số cột cần thiết không?

## 30. Những nhầm lẫn thường gặp

**Cho rằng một chunk transaction đồng nghĩa một query.** Transaction có thể chứa hàng trăm query do processor gọi repository hoặc lazy loading.

**Cho rằng mọi lazy association đều tạo N+1.** Nếu entity detached, có thể nhận `LazyInitializationException`; nếu association đã được fetch hoặc cache, không phát sinh query bổ sung.

**Đổi mọi association thành EAGER.** Điều này có thể over-fetch ở các use case khác và tạo query phức tạp hơn.

**Fetch join mọi collection trong query phân trang.** Join collection nhân số row và có thể khiến provider paginate trong memory hoặc trả page sai kỳ vọng.

**Bật `@Transactional` cho processor để hết N+1.** Transaction giữ persistence context hoạt động nhưng không gom các lookup riêng lẻ thành một query.

**Tăng chunk size để giảm N+1.** Chunk size thay đổi transaction batching, không thay đổi một query cho mỗi item.

**Dựa vào cache mà không đo.** Cache chỉ giúp khi key được lặp lại hoặc dữ liệu đã preload; ID duy nhất vẫn cần query.

**Dùng Open Session in View trong batch.** Session dài có thể che lỗi lazy và tăng memory; hãy fetch dữ liệu có chủ đích.

**Không phân biệt reader trả entity managed hay detached.** Cần hiểu lifecycle của EntityManager theo reader cụ thể trước khi chọn fetch strategy.

## 31. Kiểm thử N+1 trong Spring Batch

Nên có hai lớp kiểm thử:

**Unit test processor:** xác nhận processor nhận đủ dữ liệu và không gọi repository không cần thiết. Có thể mock service/repository để kiểm tra số lần gọi, nhưng unit test không thể xác nhận SQL mà JPA provider thực thi.

**Integration test database:** dùng database/provider thực tế hoặc cấu hình gần production, tạo số item và association có kiểm soát, đo query count/SQL, chạy qua reader và processor. Test cả page boundary vì reader có thể clear persistence context theo từng page.

Các tình huống nên kiểm thử:

1. Một item và nhiều item với mỗi item có association riêng.
2. Nhiều item cùng tham chiếu một entity để quan sát first-level cache.
3. Lazy association được truy cập khi entity managed.
4. Lazy association truy cập sau khi entity detached.
5. Fetch join to-one và DTO projection.
6. EntityGraph với page query.
7. Batch fetching cho collection.
8. Collection fetch join kết hợp pagination để quan sát SQL/provider warning.
9. Query count với 10, 100 và 1.000 item.
10. Restart Job và xác nhận fetch strategy không thay đổi kết quả.

Nếu dùng Hibernate Statistics, clear statistics và persistence context trước vùng đo. Không để test fixture query hoặc cache nóng làm kết quả thấp giả tạo.

## 32. Cách chọn giải pháp

Nếu processor cần một association cụ thể của entity, ưu tiên tải association đó ngay trong query reader bằng fetch join to-one hoặc EntityGraph. Nếu processor chỉ cần vài field, DTO projection thường là cách gọn và ít tốn tài nguyên hơn. Nếu nhiều proxy cùng loại được truy cập trong một persistence context, Hibernate batch fetching có thể giảm số query. Nếu lookup data nhỏ và ổn định, có thể preload theo Step và dùng map có giới hạn.

Với collection và pagination, tránh fetch join collection một cách tùy tiện; cân nhắc batch fetching hoặc page ID rồi bulk fetch association. Với `JpaPagingItemReader`, xác định entity có bị detach sau khi đọc page hay không trước khi dựa vào lazy loading trong processor. Không dùng transaction annotation, EAGER mapping hoặc chunk size như một cách che giấu N+1.

Đo SQL và query count bằng Hibernate Statistics, datasource instrumentation hoặc log có kiểm soát. Một processor tốt không tạo một query phụ cho mỗi item nếu dữ liệu có thể được lấy theo một fetch plan/batch hợp lý. Khi reader cung cấp đúng dữ liệu, processor tập trung vào logic nghiệp vụ và Job có thể mở rộng số lượng item mà không làm số round trip database tăng tuyến tính ngoài ý muốn.
