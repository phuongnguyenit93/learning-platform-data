# Optimistic locking

Khi Spring Batch xử lý dữ liệu JPA, một record có thể bị Job khác hoặc ứng dụng trực tuyến cập nhật cùng lúc. Nếu hai transaction cùng đọc một phiên bản rồi ghi đè lên nhau, transaction ghi sau có nguy cơ làm mất thay đổi của transaction ghi trước. **Optimistic locking** phát hiện xung đột đó tại thời điểm cập nhật bằng version của entity.

Trong JPA, optimistic locking thường được khai báo bằng `@Version`. Provider đưa giá trị version hiện tại vào điều kiện cập nhật và chỉ ghi thành công nếu version trong database vẫn bằng version mà transaction đã đọc. Nếu một transaction khác đã cập nhật record, version không còn khớp và JPA báo lỗi optimistic lock. Spring Batch nhận lỗi này qua writer/transaction boundary rồi xử lý theo chính sách rollback, retry, skip hoặc fail của Step.

Optimistic locking hữu ích khi xung đột không xảy ra thường xuyên và muốn tránh giữ row lock trong suốt quá trình xử lý. Tuy nhiên, retry chỉ có ý nghĩa nếu lần thử tiếp theo đọc lại trạng thái mới và tính toán lại thao tác. Gửi lại nguyên một entity detached với version cũ thường chỉ lặp lại cùng xung đột.

## 1. Vấn đề lost update

Giả sử một đơn hàng có trạng thái `PENDING` và số tiền `100`. Hai transaction cùng đọc record đó:

```text
Transaction A                         Transaction B
-------------                         -------------
Đọc order version 5                   Đọc order version 5
Đổi status = APPROVED                 Đổi amount = 120
Ghi database                          Ghi database
Commit                                Commit sau
```

Nếu không có cơ chế phát hiện xung đột, lần ghi sau có thể ghi dựa trên bản dữ liệu cũ và làm mất thay đổi của transaction trước. Đây là lost update.

Optimistic locking thêm version vào quá trình ghi:

```text
Transaction A                         Transaction B
-------------                         -------------
Đọc version 5                         Đọc version 5
UPDATE ... WHERE version = 5
Ghi thành công, version thành 6
Commit
                                      UPDATE ... WHERE version = 5
                                      Không còn row khớp version 5
                                      Optimistic lock exception
```

Transaction B được thông báo rằng dữ liệu đã thay đổi kể từ lúc nó đọc. Ứng dụng có thể rollback và quyết định tải lại, hợp nhất hoặc từ chối thay đổi theo quy tắc nghiệp vụ.

## 2. Cách hoạt động của @Version

JPA định nghĩa optimistic versioning qua một thuộc tính được đánh dấu `@Version`. Provider quản lý giá trị này trong vòng đời entity.

Ví dụ entity:

```java
@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false)
    private String status;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    protected OrderEntity() {
    }

    public void approve() {
        this.status = "APPROVED";
    }

    public void changeAmount(BigDecimal amount) {
        this.amount = amount;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }
}
```

Khi entity được persist lần đầu, JPA khởi tạo version. Khi cập nhật entity, provider kiểm tra version cũ và tăng version sau lần ghi thành công. Ứng dụng không nên tự tăng version trong code entity thông thường và không nên gán một version tùy ý cho entity đang được quản lý.

Các kiểu version được JPA hỗ trợ phụ thuộc phiên bản specification/provider; `Long` là lựa chọn phổ biến. Tránh dùng một field thường như `updatedAt` thay cho `@Version` nếu mục tiêu là cơ chế optimistic locking chuẩn của JPA.

## 3. Cột version trong database

Bảng cần có cột tương ứng với thuộc tính version:

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    amount DECIMAL(19, 2) NOT NULL
);
```

Tên cột có thể được tùy chỉnh bằng `@Column(name = "row_version")`. Migration schema phải được triển khai trước khi ứng dụng dùng entity có `@Version`.

SQL thực tế do JPA provider tạo ra, nhưng logic thường tương đương:

```sql
UPDATE orders
SET status = ?, amount = ?, version = ?
WHERE id = ? AND version = ?;
```

Điều kiện `WHERE version = ?` là điểm cốt lõi. Nếu không có row nào được cập nhật vì version đã thay đổi hoặc row đã bị xóa, provider phát hiện số dòng cập nhật không như mong đợi và ném optimistic lock exception.

Không tự viết SQL cập nhật entity có `@Version` mà bỏ qua điều kiện version. Nếu có native SQL hoặc bulk update, cần tự bảo đảm kiểm tra và tăng version đúng cách.

## 4. Optimistic lock exception xuất hiện khi nào?

Xung đột thường được phát hiện khi JPA đồng bộ persistence context với database. Điều này có thể xảy ra lúc gọi `flush()` hoặc khi transaction commit, không nhất thiết ngay tại lệnh setter.

Ví dụ:

```java
@Transactional
public void approveOrder(Long orderId) {
    OrderEntity order = entityManager.find(OrderEntity.class, orderId);
    order.approve();
    // SQL update may execute during flush/commit.
}
```

Trong method trên, `order.approve()` chỉ thay đổi state trong persistence context. Khi flush/commit, provider mới thực hiện update có kiểm tra version. Vì vậy, lỗi có thể xuất hiện ở cuối method hoặc tại transaction boundary của Spring Batch.

Nếu cần phát hiện lỗi ngay trong phạm vi `write`, có thể flush sau khi merge/persist. Tuy nhiên, flush không commit transaction; rollback/commit vẫn do Step quản lý.

Các exception thường gặp gồm `jakarta.persistence.OptimisticLockException` ở tầng JPA và các exception đã được Spring dịch như `OptimisticLockingFailureException` hoặc subclass cụ thể khi dùng Spring Data/JPA integration. Cần quan sát exception thực tế trong stack trace để cấu hình retry đúng loại.

## 5. JPA transaction trong Spring Batch

Chunk-oriented Step thực hiện reader, processor và writer trong chu kỳ xử lý theo chunk. Khi writer dùng JPA, thao tác entity cần tham gia transaction được cấu hình cho Step, thường thông qua `JpaTransactionManager` gắn với `EntityManagerFactory` tương ứng.

```java
@Bean
PlatformTransactionManager transactionManager(
        EntityManagerFactory entityManagerFactory) {
    return new JpaTransactionManager(entityManagerFactory);
}
```

Ví dụ Step:

```java
@Bean
Step approveOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderCommand> reader,
        ItemProcessor<OrderCommand, OrderEntity> processor,
        ItemWriter<OrderEntity> writer) {

    return new StepBuilder("approveOrdersStep", jobRepository)
            .<OrderCommand, OrderEntity>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Khi một optimistic lock exception làm chunk thất bại, transaction của chunk được rollback theo cấu hình. Các thao tác database chưa commit trong cùng transaction được hoàn tác. Step sau đó có thể retry, skip hoặc kết thúc thất bại theo fault-tolerance policy.

Đảm bảo reader, writer và repository dùng đúng `EntityManagerFactory`/transaction manager. Nếu một phần thao tác chạy trên datasource hoặc transaction khác, rollback của chunk không tự động bao phủ resource đó.

## 6. Dùng JpaItemWriter

Nếu output là entity JPA, có thể dùng writer tích hợp `JpaItemWriter` thay vì tự viết vòng lặp EntityManager:

```java
@Bean
JpaItemWriter<OrderEntity> orderJpaWriter(
        EntityManagerFactory entityManagerFactory) {

    return new JpaItemWriterBuilder<OrderEntity>()
            .entityManagerFactory(entityManagerFactory)
            .build();
}
```

`JpaItemWriter` nhận chunk, ghi các entity qua JPA và flush theo lifecycle của writer. Với entity đã tồn tại, writer thường sử dụng thao tác merge theo cấu hình mặc định. Nếu entity mang version cũ, xung đột có thể xuất hiện trong quá trình merge/flush.

Writer tích hợp giúp xử lý lifecycle JPA theo cơ chế Spring Batch, nhưng không loại bỏ optimistic lock conflict. `@Version` vẫn phát hiện một transaction khác đã thay đổi entity trước khi ghi.

Không dùng cùng một entity instance mutable cho nhiều thread. Cũng không giữ một `EntityManager` singleton trong field rồi chia sẻ giữa nhiều execution; EntityManager không phải object thread-safe.

## 7. Đọc entity rồi cập nhật bằng JPA

Một cách xử lý thường gặp là đọc entity bằng `JpaPagingItemReader`, sau đó chuyển đổi hoặc cập nhật entity trong processor/writer.

Ví dụ reader:

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

Entity được đọc ở một thời điểm có version cụ thể. Nếu một ứng dụng khác cập nhật entity trước khi writer ghi, version trong object có thể đã cũ. Khi JPA đồng bộ thay đổi, optimistic locking phát hiện conflict.

Điều này đặc biệt quan trọng khi Job chạy lâu hoặc xử lý nhiều page: khoảng thời gian từ lúc đọc đến lúc ghi có thể dài, khiến xác suất entity stale tăng lên.

## 8. Vì sao retry cùng entity cũ thường không giải quyết conflict?

Giả sử reader tạo `OrderEntity` có `version = 5`. Một ứng dụng khác cập nhật row và database chuyển version thành 6. Writer thử ghi entity cũ và nhận optimistic lock exception.

Nếu lần retry chỉ gửi lại đúng object có version 5, điều kiện update vẫn không khớp. Retry lặp lại cùng dữ liệu cũ không làm conflict biến mất.

```text
Attempt 1:
  Entity trong item: version 5
  Database:          version 6
  => Conflict

Attempt 2 (vẫn dùng item cũ):
  Entity trong item: version 5
  Database:          version 6
  => Conflict lần nữa
```

Retry có ích khi lần thử mới có thể đọc trạng thái mới, tính toán lại và tạo update dựa trên version hiện tại. Nếu không có bước reload/recompute, cần fail hoặc chuyển item sang quy trình xử lý xung đột thay vì retry vô hạn.

## 9. Reload và áp dụng lại command nghiệp vụ

Một thiết kế thường dễ phục hồi hơn là reader đưa ra command/ID thay vì mang nguyên entity detached qua toàn bộ pipeline. Khi xử lý, service tải entity mới nhất trong transaction, kiểm tra trạng thái và áp dụng command.

Ví dụ:

```java
public record ApproveOrderCommand(Long orderId) {
}

@Service
public class OrderApprovalService {

    private final OrderRepository repository;

    public OrderApprovalService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void approve(ApproveOrderCommand command) {
        OrderEntity current = repository.findById(command.orderId())
                .orElseThrow(() -> new OrderNotFoundException(
                        command.orderId()));

        if ("APPROVED".equals(current.getStatus())) {
            return; // Idempotent for an already completed command.
        }

        if (!"PENDING".equals(current.getStatus())) {
            throw new InvalidOrderStateException(command.orderId());
        }

        current.approve();
    }
}
```

Service tải entity hiện tại trong transaction và thay đổi entity đang được quản lý. JPA kiểm tra version lúc flush/commit. Nếu có xung đột đúng vào thời điểm ghi, transaction thất bại; một lần xử lý mới phải tải lại entity và đánh giá lại điều kiện nghiệp vụ.

Nếu Job dùng `JpaItemWriter` với entity detached đã đọc từ trước, không tự động có nghĩa writer sẽ reload và áp dụng lại command. Hãy thiết kế rõ item là entity snapshot hay command, và nơi nào chịu trách nhiệm tải lại dữ liệu mới.

## 10. Retry optimistic locking trong Step

Spring Batch fault tolerance có thể retry một số exception khi writer/processor thất bại:

```java
return new StepBuilder("approveOrdersStep", jobRepository)
        .<ApproveOrderCommand, OrderEntity>chunk(100, transactionManager)
        .reader(orderCommandReader)
        .processor(orderReloadingProcessor)
        .writer(orderJpaWriter)
        .faultTolerant()
        .retry(OptimisticLockingFailureException.class)
        .retry(OptimisticLockException.class)
        .retryLimit(3)
        .build();
```

Trong ví dụ, hai exception đại diện cho trường hợp Spring Data/Spring translation và exception JPA trực tiếp. Không phải ứng dụng nào cũng cần khai báo cả hai; hãy cấu hình theo exception thực tế mà stack trả về sau transaction rollback/translation.

Retry limit phải hữu hạn. Khi nhiều Job liên tục cập nhật cùng row, retry nhiều lần có thể chỉ làm tăng tải và kéo dài xung đột. Có thể cần backoff, giảm concurrency, phân vùng lại dữ liệu hoặc chuyển sang locking phù hợp.

Quan trọng: retry policy không tự biến entity stale thành entity mới. Processor/service phải có cách reload và áp dụng lại command nếu nghiệp vụ cho phép. Cần integration test chứng minh lần thử lại thực sự dùng trạng thái mới, không chỉ lặp lại cùng payload.

## 11. Retry, rollback và vị trí phát sinh exception

Optimistic lock exception có thể được ném khi:

- Gọi `EntityManager.flush()` trong writer.
- Spring Data repository gọi flush.
- Transaction manager commit chunk và JPA tự flush trước commit.
- Một thao tác merge/persist phát hiện version không khớp.

Nếu exception chỉ xuất hiện ở commit, code `write()` có thể đã trả về bình thường trước khi transaction thất bại. Vì vậy, không nên chỉ bắt exception quanh một lệnh trong writer rồi giả định đã bao phủ mọi optimistic lock failure.

Khi cần exception xuất hiện trong phạm vi writer để phân loại lỗi dễ hơn, có thể flush rõ ràng sau các thao tác JPA. Flush vẫn nằm trong transaction của chunk và không thay thế commit.

Không bắt `OptimisticLockException` rồi tiếp tục xử lý các item khác trong cùng transaction đã bị đánh dấu rollback-only. Hãy để transaction thất bại và để Spring Batch điều phối retry/skip/fail ở ranh giới thích hợp.

## 12. Skip conflict hay retry conflict?

Không phải mọi optimistic lock conflict đều nên retry. Quyết định phụ thuộc ý nghĩa nghiệp vụ:

| Tình huống | Cách xử lý thường phù hợp |
|---|---|
| Xung đột ngắn hạn, có thể reload và áp dụng lại command | Retry hữu hạn, có backoff và reload. |
| Một trạng thái đã được người khác hoàn tất, command hiện tại trở nên dư thừa | Xác định idempotent success hoặc skip theo nghiệp vụ. |
| Hai thay đổi mâu thuẫn, cần người dùng quyết định | Ghi nhận conflict/reject và chuyển xử lý thủ công. |
| Record không còn tồn tại | Xử lý theo policy not-found; không retry vô hạn. |
| Xung đột liên tục do nhiều worker cùng sở hữu một row | Sửa partition/ownership/concurrency hoặc dùng locking khác. |

Skip không nên dùng để che mọi `OptimisticLockException`. Nếu xung đột có nghĩa dữ liệu đầu ra có thể sai hoặc mất cập nhật, bỏ qua item có thể làm Job báo thành công nhưng thiếu nghiệp vụ.

Nếu chọn skip, hãy ghi thông tin đủ để đối soát: entity ID, version đã đọc, thời điểm conflict, Job/Step execution và lý do quyết định skip. Tránh ghi payload nhạy cảm vào log.

## 13. Bulk JPQL update không tự áp dụng @Version như entity update

Một điểm dễ bỏ sót là JPQL bulk update và native SQL không đi qua dirty checking thông thường của từng entity. Chúng tác động trực tiếp lên database và không tự thực hiện đầy đủ optimistic version check như cập nhật entity được quản lý.

Ví dụ bulk update:

```java
@Modifying
@Query("""
       update OrderEntity o
       set o.status = :status
       where o.id = :id
       """)
int updateStatus(Long id, String status);
```

Query này có thể bỏ qua kiểm tra version mà ứng dụng kỳ vọng. Nếu cần optimistic locking với bulk update, hãy đưa version dự kiến vào điều kiện và tăng version rõ ràng:

```java
@Modifying
@Query("""
       update OrderEntity o
       set o.status = :status,
           o.version = o.version + 1
       where o.id = :id
         and o.version = :expectedVersion
       """)
int updateStatusIfVersionMatches(
        Long id,
        Long expectedVersion,
        String status);
```

Sau khi thực thi, kiểm tra số row được cập nhật:

```java
int updated = repository.updateStatusIfVersionMatches(
        command.orderId(), command.expectedVersion(), "APPROVED");

if (updated == 0) {
    throw new OptimisticLockingFailureException(
            "Order changed before update: " + command.orderId());
}
```

Bulk update còn có thể làm persistence context đang giữ entity cũ không đồng bộ với database. Cần clear/refresh context phù hợp và không tiếp tục dùng object stale sau bulk operation.

## 14. Native SQL và JDBC writer

Nếu custom writer dùng JDBC hoặc native SQL, JPA `@Version` không tự bảo vệ câu lệnh SQL đó. Phải tự đưa expected version vào `WHERE`, tăng version và kiểm tra update count.

```sql
UPDATE orders
SET status = :newStatus,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
```

Java:

```java
int updated = jdbcTemplate.update(
        """
        UPDATE orders
        SET status = ?, version = version + 1
        WHERE id = ? AND version = ?
        """,
        newStatus,
        orderId,
        expectedVersion);

if (updated != 1) {
    throw new OptimisticLockingFailureException(
            "Concurrent update detected for order " + orderId);
}
```

Lệnh này thực hiện compare-and-set ở cấp database. Nếu không có row nào khớp ID và version, có thể row đã bị xóa hoặc version đã thay đổi; nếu cần phân biệt hai trường hợp, thực hiện truy vấn chẩn đoán phù hợp sau rollback hoặc trong transaction mới.

Nếu cùng transaction có JPA persistence context đang giữ entity tương ứng, cần refresh/clear để tránh state trong memory cũ ghi đè lại dữ liệu vừa cập nhật bằng JDBC.

## 15. @Version không bảo vệ mọi invariant nghiệp vụ

Optimistic locking bảo vệ xung đột cập nhật trên entity/version được kiểm soát. Nó không tự giải quyết mọi race condition liên quan nhiều row hoặc điều kiện tổng hợp.

Ví dụ hai transaction cùng kiểm tra “còn ít nhất một chỗ trống” rồi mỗi transaction tạo một booking ở hai row khác nhau. Nếu không cùng cập nhật một entity/version, cả hai có thể thành công dù tổng số booking vượt giới hạn.

Các tình huống cần cơ chế bổ sung:

- Invariant trải qua nhiều entity hoặc nhiều bảng.
- Insert trùng business key.
- Kiểm tra không tồn tại row rồi insert đồng thời.
- Tổng số tiền/hạn mức được tính từ nhiều row.
- Quan hệ collection thay đổi mà version của entity gốc không được cập nhật theo cách mong đợi.
- Bulk update hoặc native SQL bỏ qua version.

Giải pháp có thể gồm unique constraint, aggregate version, pessimistic lock, atomic SQL update, serializable isolation hoặc thiết kế dữ liệu lại để invariant được bảo vệ tại một row/constraint. Không giả định thêm `@Version` vào một entity là đủ cho mọi invariant.

## 16. Optimistic locking trong multi-threaded Step và partitioning

Nếu nhiều worker cùng đọc và cập nhật các row chồng lấn, optimistic lock conflict có thể xảy ra thường xuyên. `@Version` phát hiện xung đột nhưng không tự phân phối ownership giữa worker.

Một thiết kế tốt thường partition theo khóa sao cho mỗi worker sở hữu tập row không giao nhau:

```text
Manager Step
    |
    +--> Partition A: order_id 1..100000
    |
    +--> Partition B: order_id 100001..200000
    |
    +--> Partition C: order_id 200001..300000
```

Nếu dữ liệu được phân vùng không chồng lấn, xác suất hai worker cùng cập nhật một entity giảm đáng kể. Tuy nhiên, các Job online hoặc Job khác vẫn có thể sửa cùng row; partitioning trong một Job không bảo vệ trước writer bên ngoài.

Các biện pháp:

- Chia partition theo business key/ID range không chồng lấn.
- Tránh hai Step/Job đồng thời sở hữu cùng tập record.
- Dùng claim/lease hoặc trạng thái `PROCESSING` nếu cần ownership.
- Theo dõi tỷ lệ optimistic lock conflict theo partition.
- Giảm concurrency nếu database hoặc workload gây contention.
- Dùng pessimistic locking cho đoạn ngắn nếu conflict thường xuyên và yêu cầu nghiệp vụ phù hợp.

Không chia sẻ một `EntityManager` giữa các worker. Mỗi transaction/thread cần persistence context phù hợp với transaction manager.

## 17. Optimistic locking và pessimistic locking

Hai chiến lược giải quyết cạnh tranh cập nhật theo cách khác nhau:

| Đặc điểm | Optimistic locking | Pessimistic locking |
|---|---|---|
| Cách bảo vệ | Kiểm tra version khi ghi | Database giữ lock trong transaction |
| Khi conflict | Phát hiện tại update/flush/commit | Transaction khác có thể phải chờ hoặc bị từ chối |
| Chi phí khi ít conflict | Thường thấp | Có overhead lock/đợi lock |
| Khi conflict cao | Retry có thể tốn kém | Có thể phù hợp hơn nếu lock scope ngắn và kiểm soát được |
| Giữ lock trong lúc xử lý lâu | Không cần giữ row lock suốt thời gian đọc | Có nguy cơ giữ lock lâu và gây contention |
| Restart | Cần reload/version mới sau conflict | Cần xử lý transaction/lock timeout và retry |

JPA hỗ trợ lock mode như `LockModeType.PESSIMISTIC_WRITE` cho trường hợp cần khóa khi đọc/cập nhật. Không chuyển sang pessimistic lock chỉ để loại bỏ exception mà không đo contention và đánh giá ảnh hưởng đến throughput.

Với Batch xử lý lâu, optimistic locking thường phù hợp khi xung đột hiếm và có thể xử lý lại. Nếu một số row nóng bị nhiều worker cập nhật liên tục, partition/ownership hoặc lock chiến lược có thể phù hợp hơn.

## 18. Version và dữ liệu detached

Một entity được đọc trong persistence context rồi chuyển ra ngoài có thể trở thành detached khi context đóng hoặc bị clear. Entity detached vẫn mang giá trị version tại thời điểm nó được đọc.

Khi merge entity detached, JPA đồng bộ state của nó vào một entity managed. Nếu version detached đã cũ so với database, provider có thể ném optimistic lock exception. Không nên tự gán version hiện tại vào object cũ để “sửa” conflict; điều đó che giấu việc dữ liệu đã thay đổi và có thể làm mất update.

Thay vào đó:

- Chỉ gửi ID/command qua pipeline nếu có thể.
- Tải lại entity mới nhất trong transaction xử lý.
- Kiểm tra trạng thái nghiệp vụ trước khi áp dụng command.
- Dùng expected version nếu người gọi muốn phát hiện thay đổi kể từ lúc đọc.
- Nếu cần merge hai thay đổi, viết logic hợp nhất theo từng field, không copy toàn bộ object cũ lên entity mới.

Không dùng `EntityManager.merge()` như một thao tác “ghi đè chắc chắn”. Merge không bỏ qua version check và không tự quyết định cách hợp nhất xung đột nghiệp vụ.

## 19. Xung đột giữa hai Job và giữa Job với ứng dụng online

Optimistic locking có thể phát hiện xung đột giữa:

- Hai Job Spring Batch chạy cùng lúc.
- Job Batch và REST/API application.
- Hai request online.
- Job retry sau khi một worker khác đã hoàn tất cập nhật.

Tất cả ứng dụng ghi entity cần tuân thủ version column. Nếu một ứng dụng cập nhật bằng SQL trực tiếp nhưng không tăng version, JPA application khác có thể không phát hiện được thay đổi theo cách mong muốn.

Quy ước database cần được thống nhất:

- Mọi update đường vòng phải cập nhật version.
- Không cho phép script maintenance bỏ qua version mà không có kế hoạch đồng bộ.
- Version column không bị reset khi import/restore một phần.
- Các service không tự gán version tùy tiện.
- Nếu bulk operation thay đổi nhiều row, phải quản lý persistence context và version nhất quán.

## 20. Theo dõi optimistic lock conflict

Optimistic lock exception là tín hiệu về contention, không chỉ là lỗi kỹ thuật ngẫu nhiên. Nên theo dõi:

- Số conflict theo Job/Step.
- Số conflict theo entity type hoặc loại thao tác.
- Số lần retry trung bình và retry exhaustion.
- Partition/worker phát sinh conflict.
- Tỷ lệ conflict trên tổng số update.
- Thời gian xử lý tăng do retry.
- Các business key thường xuyên xung đột (trong log có kiểm soát, không dùng làm metric tag cardinality cao).

Nếu conflict tăng, kiểm tra Job overlap, partition range, row hot spot, transaction duration, batch size và các writer online. Tăng retry limit không phải lúc nào cũng cải thiện throughput.

Không log toàn bộ entity hoặc dữ liệu cá nhân khi conflict. Ghi ID nội bộ, version expected/observed nếu có thể thu thập an toàn, JobExecution/StepExecution và correlation ID.

## 21. Kiểm thử optimistic locking bằng hai transaction

Test quan trọng nhất tạo hai persistence context độc lập đọc cùng một version, rồi cập nhật lần lượt.

```java
@Test
void secondTransactionFailsWhenEntityVersionIsStale() {
    OrderEntity first = transactionTemplate.execute(status ->
            entityManager.find(OrderEntity.class, orderId));

    OrderEntity second = transactionTemplate.execute(status ->
            entityManager.find(OrderEntity.class, orderId));

    transactionTemplate.executeWithoutResult(status -> {
        OrderEntity current = entityManager.find(OrderEntity.class, orderId);
        current.approve();
        entityManager.flush();
    });

    assertThatThrownBy(() -> transactionTemplate.executeWithoutResult(status -> {
        second.changeAmount(new BigDecimal("125.00"));
        entityManager.merge(second);
        entityManager.flush();
    })).hasRootCauseInstanceOf(OptimisticLockException.class);
}
```

Đây là pseudocode minh họa; test thực tế cần bảo đảm mỗi transaction dùng persistence context/EntityManager riêng. Không dùng cùng một `EntityManager` cho cả hai transaction vì persistence context có thể trả lại cùng managed instance và không tái hiện stale version.

Có thể dùng hai `TransactionTemplate` với transaction manager và `EntityManager` được inject đúng scope, hoặc mở hai `EntityManager` độc lập từ `EntityManagerFactory`. Test cần flush/commit transaction thứ nhất trước khi transaction thứ hai flush.

## 22. Kiểm thử với EntityManager độc lập

Một cách kiểm soát rõ ràng hơn trong integration test là mở hai EntityManager:

```java
@Test
void detectsConcurrentUpdateAcrossPersistenceContexts() {
    EntityManager em1 = entityManagerFactory.createEntityManager();
    EntityManager em2 = entityManagerFactory.createEntityManager();

    try {
        em1.getTransaction().begin();
        em2.getTransaction().begin();

        OrderEntity first = em1.find(OrderEntity.class, orderId);
        OrderEntity second = em2.find(OrderEntity.class, orderId);

        first.approve();
        em1.getTransaction().commit();

        second.changeAmount(new BigDecimal("125.00"));

        assertThatThrownBy(() -> {
            try {
                em2.flush();
                em2.getTransaction().commit();
            } catch (RuntimeException exception) {
                if (em2.getTransaction().isActive()) {
                    em2.getTransaction().rollback();
                }
                throw exception;
            }
        }).hasRootCauseInstanceOf(OptimisticLockException.class);
    } finally {
        if (em1.isOpen()) {
            em1.close();
        }
        if (em2.isOpen()) {
            em2.close();
        }
    }
}
```

Test minh họa quản lý transaction thủ công để làm rõ hai persistence context. Trong dự án dùng Spring, có thể ưu tiên test qua `TransactionTemplate` hoặc repository/service được cấu hình thật. Cần dọn transaction đang hoạt động trong `finally` và không tái sử dụng EntityManager sau optimistic lock failure vì transaction/persistence context có thể không còn ở trạng thái sử dụng được.

## 23. Kiểm thử retry trong Spring Batch

Unit test entity không chứng minh Step retry đúng. Integration test Batch nên tạo conflict có kiểm soát:

1. Seed một entity có version xác định.
2. Reader hoặc processor lấy command/entity cho item.
3. Test hook hoặc một transaction thứ hai cập nhật cùng row trước khi writer flush.
4. Writer nhận version cũ và phát sinh optimistic lock exception.
5. Retry path tải lại entity trong transaction mới và áp dụng lại command nếu nghiệp vụ cho phép.
6. Xác nhận Step hoàn tất hoặc fail theo retry limit.
7. Xác nhận version và trạng thái cuối đúng, không mất update của transaction cạnh tranh.

Test nên xác nhận số lần retry và việc reload thật sự xảy ra. Nếu lần retry vẫn dùng entity cũ, test cần thể hiện conflict lặp lại thay vì coi retry policy đã giải quyết vấn đề.

Các trường hợp nên có:

- Không có conflict: một lần ghi thành công.
- Một conflict rồi reload/retry thành công.
- Conflict vượt retry limit: Step fail hoặc recovery theo policy.
- Conflict được skip theo nghiệp vụ: skip listener/audit nhận đúng item.
- Row bị xóa trước khi retry: xử lý not-found rõ ràng.
- Hai Job xử lý cùng business key: kết quả cuối theo ownership/idempotency contract.

## 24. Những lỗi thường gặp

### Quên @Version

Không có version field được quản lý bởi JPA thì optimistic version check chuẩn không được áp dụng cho entity đó. Thêm field version và migration database tương ứng.

### Tự tăng version trong entity

Provider quản lý version. Tự sửa version có thể làm sai state hoặc khiến provider báo lỗi. Chỉ cập nhật version thủ công trong bulk/native SQL có điều kiện expected-version rõ ràng.

### Nghĩ exception luôn xuất hiện tại setter

Conflict thường được phát hiện khi flush/commit. Đặt test và logging tại đúng transaction boundary.

### Retry nguyên entity stale

Version cũ vẫn không khớp. Tải lại entity trong transaction mới và áp dụng lại command theo nghiệp vụ.

### Bắt exception rồi tiếp tục transaction

Transaction có thể đã rollback-only. Để exception thoát ra và retry ở transaction mới.

### Bật retry quá rộng

Retry mọi exception làm tăng tải và che lỗi cố định. Chỉ retry exception transient/conflict có chiến lược reload phù hợp.

### Skip mọi optimistic lock exception

Có thể bỏ mất nghiệp vụ quan trọng. Chỉ skip khi conflict được chấp nhận và có audit/reconciliation.

### Dùng bulk JPQL mà quên version

Bulk update không đi qua dirty checking thông thường. Thêm expected version, tăng version và kiểm tra update count nếu cần optimistic semantics.

### Dùng JDBC/native SQL nhưng không tăng version

JPA không thể phát hiện thay đổi qua version nếu writer SQL không cập nhật cột version theo hợp đồng.

### Chia partition chồng lấn

Nhiều worker cùng cập nhật row nóng và tạo conflict liên tục. Phân vùng theo ownership không chồng lấn hoặc claim record.

### Dùng một EntityManager nhiều thread

EntityManager không thread-safe. Mỗi transaction/thread cần persistence context riêng.

### Nghĩ @Version bảo vệ invariant nhiều row

Version bảo vệ entity/row được version hóa, không tự bảo vệ tổng hợp hoặc điều kiện xuyên nhiều row. Dùng constraint, atomic update hoặc locking phù hợp.

## 25. Quy trình áp dụng optimistic locking trong Batch JPA

Khi một Step cập nhật entity có thể bị ứng dụng khác thay đổi, hãy thực hiện theo trình tự:

1. Xác định entity nào có thể được cập nhật đồng thời.
2. Thêm `@Version` và migration cột version trong database.
3. Bảo đảm mọi đường ghi (JPA, repository, bulk SQL, native SQL) tuân thủ version contract.
4. Chọn item là entity snapshot hay command/ID; ưu tiên command khi cần reload trạng thái mới.
5. Cấu hình `JpaTransactionManager` và `EntityManagerFactory` đúng với Step.
6. Dùng `JpaItemWriter` hoặc writer custom có transaction/flush semantics rõ.
7. Xác định exception thực tế được ném tại flush/commit.
8. Chỉ retry conflict khi lần thử mới có thể reload và áp dụng lại an toàn.
9. Đặt retry limit/backoff hữu hạn; phân loại conflict không thể hợp nhất thành reject/failure phù hợp.
10. Giữ side effect idempotent và không dùng EntityManager chia sẻ giữa thread.
11. Giảm xung đột bằng partition không chồng lấn hoặc ownership/claim khi cần.
12. Kiểm thử hai persistence context, stale entity, bulk update, retry/reload và restart bằng database gần production.
13. Theo dõi conflict rate và điều chỉnh concurrency/locking theo số liệu thực tế.

| Nhu cầu | Cách xử lý |
|---|---|
| Phát hiện entity bị sửa kể từ lúc đọc | JPA `@Version` |
| Ghi entity JPA trong chunk | `JpaItemWriter` + transaction manager phù hợp |
| Xử lý conflict có thể phục hồi | Rollback, reload entity mới và áp dụng lại command trong transaction mới |
| Bulk JPQL/native SQL có kiểm tra version | `WHERE id = ? AND version = ?`, tăng version và kiểm tra update count |
| Giảm conflict giữa worker | Partition/ownership không chồng lấn hoặc claim record |
| Conflict thường xuyên trên row nóng | Đánh giá pessimistic lock hoặc thiết kế lại concurrency |
| Kiểm tra lost update | Hai EntityManager độc lập đọc cùng version rồi cập nhật lần lượt |

## Kết luận

Optimistic locking trong JPA dùng `@Version` để phát hiện entity đã bị transaction khác cập nhật kể từ lúc đọc. Khi version không còn khớp, JPA ném optimistic lock exception trong lúc flush hoặc commit; Spring Batch rollback chunk và áp dụng retry/skip/fail theo cấu hình Step. Retry chỉ giải quyết được conflict khi lần thử mới tải trạng thái hiện tại và áp dụng lại command theo quy tắc nghiệp vụ; gửi lại entity detached với version cũ thường lặp lại cùng lỗi. Hãy bảo đảm mọi đường ghi đều tuân thủ version contract, chú ý bulk JPQL/native SQL, dùng transaction manager JPA đúng, phân vùng dữ liệu để giảm xung đột và kiểm thử bằng nhiều persistence context độc lập. `@Version` bảo vệ cập nhật entity, nhưng các invariant nhiều row vẫn cần constraint, atomic update hoặc cơ chế locking phù hợp.
