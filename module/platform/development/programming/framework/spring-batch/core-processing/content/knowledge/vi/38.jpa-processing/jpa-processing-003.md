# Clear persistence context theo chunk

Khi dùng JPA trong Spring Batch, mỗi entity được load hoặc persist có thể được quản lý bởi một `EntityManager`. Các entity managed được giữ trong **persistence context** (first-level cache) để JPA theo dõi thay đổi, thực hiện dirty checking và đồng bộ dữ liệu xuống database. Nếu một persistence context tồn tại quá lâu và giữ hàng nghìn hoặc hàng triệu entity, bộ nhớ có thể tăng liên tục.

Trong chunk-oriented processing, Spring Batch gom item thành từng chunk rồi gọi writer trong transaction của chunk. Đây là ranh giới tự nhiên để đồng bộ dữ liệu và giải phóng các entity không còn cần thiết. Với JPA, thao tác thường có dạng **flush trước, clear sau**: `flush()` gửi các thay đổi đang chờ xuống database trong transaction hiện tại; `clear()` detach toàn bộ entity khỏi persistence context để giảm lượng object được JPA quản lý.

Spring Batch cung cấp `JpaItemWriter` với tùy chọn `clearPersistenceContext` để thực hiện việc này sau khi ghi chunk. Khi tự viết writer, cần bảo đảm thứ tự flush/clear và hiểu rằng clear chỉ detach entity, không commit transaction.

## 1. Persistence context là gì?

`EntityManager` quản lý một persistence context. Persistence context là tập hợp các entity instance mà JPA đang theo dõi trong một phạm vi làm việc. Với entity managed, JPA có thể:

- Theo dõi thay đổi field để thực hiện dirty checking.
- Đảm bảo một identity trong persistence context tương ứng với một entity instance managed.
- Đồng bộ các thay đổi bằng SQL khi flush.
- Duy trì quan hệ và trạng thái entity trong suốt phạm vi persistence context.
- Phối hợp cascade, lazy loading và lifecycle callback theo mapping.

Ví dụ:

```java
Customer customer = entityManager.find(Customer.class, 100L);
customer.setName("Nguyen An");
```

Nếu `customer` đang managed, không cần gọi một lệnh update riêng. Khi persistence context được flush, JPA phát hiện thay đổi của `name` và tạo SQL `UPDATE` tương ứng.

Persistence context thường được gọi là first-level cache vì entity đã được quản lý có thể được lấy lại mà không cần truy vấn database lần nữa trong cùng context. Nó khác với second-level cache của provider như Hibernate, vốn có phạm vi rộng hơn và cấu hình riêng.

## 2. Vì sao persistence context có thể làm tăng bộ nhớ?

Mỗi entity managed cần trạng thái theo dõi. Provider có thể giữ entity instance, snapshot phục vụ dirty checking, collection state, proxy, quan hệ và metadata nội bộ.

Nếu một job đọc và ghi 500.000 entity trong một persistence context dài hạn, context có thể giữ tham chiếu tới rất nhiều object ngay cả khi code nghiệp vụ không còn dùng trực tiếp chúng. Garbage collector không thể thu hồi entity khi persistence context vẫn giữ reference.

Minh họa:

```text
Một persistence context kéo dài
  entity 1
  entity 2
  entity 3
  ...
  entity 500000
       |
       v
EntityManager vẫn giữ trạng thái managed
       |
       v
Heap tăng theo số entity được quản lý
```

Trong batch lớn, cần giới hạn số entity managed cùng lúc. Một cách là kết thúc persistence context theo transaction/chunk; một cách khác là flush và clear sau mỗi chunk nếu context được tái sử dụng lâu hơn phạm vi cần thiết.

Không phải mọi ứng dụng Spring Batch đều giữ một `EntityManager` duy nhất xuyên suốt toàn job. Với transaction-scoped persistence context thông thường, context gắn với transaction và được đóng/giải phóng theo lifecycle transaction. Tuy vậy, writer có thể chủ động clear sau khi ghi chunk để giải phóng trạng thái managed ngay trong transaction đó, đặc biệt khi context được chia sẻ hoặc có cấu hình lifecycle dài hơn dự kiến.

## 3. Phân biệt flush, clear và commit

Ba thao tác này có ý nghĩa khác nhau:

| Thao tác | Ý nghĩa | Có commit transaction không? |
|---|---|---:|
| `EntityManager.flush()` | Đồng bộ thay đổi đang chờ trong persistence context thành SQL gửi tới database. | Không. |
| `EntityManager.clear()` | Detach tất cả entity khỏi persistence context hiện tại. | Không. |
| Transaction `commit` | Xác nhận transaction database theo transaction manager. | Có. |

Ví dụ:

```java
entity.setStatus(Status.PROCESSED);
entityManager.flush(); // SQL được gửi trong transaction hiện tại.
entityManager.clear(); // Entity không còn managed.
// Transaction chỉ commit khi Spring Batch hoàn tất chunk.
```

`flush()` không bảo đảm thay đổi đã bền vững. Nếu transaction rollback sau đó, database vẫn có thể hoàn tác SQL đã flush. `clear()` cũng không commit và không rollback; nó chỉ thay đổi trạng thái quản lý entity trong bộ nhớ.

## 4. Vì sao phải flush trước khi clear?

Nếu entity managed có thay đổi chưa được flush, gọi `clear()` sẽ detach entity và loại nó khỏi persistence context. Các thay đổi chưa được đồng bộ có thể không còn được JPA theo dõi để tự động ghi xuống database.

Thứ tự đúng khi cần bảo đảm mọi thay đổi hiện tại được gửi tới database trước khi detach:

```java
entityManager.flush();
entityManager.clear();
```

Thứ tự không an toàn:

```java
entityManager.clear();
entityManager.flush(); // Các entity vừa clear không còn được theo dõi.
```

Một điểm cần nhớ: flush chỉ gửi SQL trong transaction. Nếu constraint violation hoặc lỗi SQL xảy ra ở flush, exception được phát sinh ngay tại đây thay vì đợi đến commit. Điều đó có thể giúp xác định lỗi ghi ở giai đoạn writer, nhưng transaction vẫn có thể rollback.

## 5. Chunk là ranh giới phù hợp để clear

Trong chunk-oriented step, Spring Batch thực hiện một vòng lặp khái quát:

```text
BEGIN transaction
  read item 1
  read item 2
  ...
  read item N
  process items
  call ItemWriter.write(chunk)
  flush JPA changes
  clear persistence context
COMMIT transaction
```

Một lần gọi writer thường tương ứng với một chunk. Nếu writer dùng `JpaItemWriter` và bật clear persistence context, writer flush rồi clear sau khi ghi các item trong chunk.

Lợi ích:

- Giới hạn số entity còn managed sau mỗi lần ghi.
- Giảm chi phí dirty checking trên một persistence context dài hạn.
- Tránh giữ snapshot và quan hệ của các entity đã xử lý.
- Giảm nguy cơ heap tăng tuyến tính theo tổng số item của job.

Clear theo chunk có ý nghĩa hơn clear sau mỗi item. Clear từng item có thể làm mất lợi ích batching, khiến các quan hệ cần lazy loading không còn khả dụng và tạo thêm chi phí quản lý entity. Chunk giúp gom một nhóm thay đổi, flush một lần theo thiết kế writer, rồi detach nhóm entity.

## 6. Cấu hình JpaItemWriter

`JpaItemWriter<T>` là writer có sẵn của Spring Batch để ghi entity thông qua JPA. Có thể cấu hình trực tiếp:

```java
@Bean
JpaItemWriter<Customer> customerWriter(EntityManagerFactory entityManagerFactory) {
    JpaItemWriter<Customer> writer = new JpaItemWriter<>();
    writer.setEntityManagerFactory(entityManagerFactory);
    writer.setUsePersist(false);
    writer.setClearPersistenceContext(true);
    return writer;
}
```

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `entityManagerFactory` | Factory tạo hoặc cung cấp `EntityManager` tham gia transaction. |
| `usePersist` | Chọn `persist` cho entity mới thay vì mặc định `merge`. |
| `clearPersistenceContext` | Yêu cầu writer clear persistence context sau khi ghi chunk. |

Nên cấu hình `clearPersistenceContext(true)` một cách tường minh khi mục tiêu là giới hạn số entity managed. Default có thể phụ thuộc phiên bản; hãy đối chiếu API/dependency đang dùng thay vì dựa vào một giá trị ngầm định.

`JpaItemWriter` phải chạy trong transaction phù hợp với `EntityManagerFactory`. Trong Spring Batch, thường cấu hình `JpaTransactionManager` dùng cùng `EntityManagerFactory` cho step. Không gọi writer ngoài transaction nếu writer yêu cầu một transactional `EntityManager`.

## 7. Ghi entity mới và entity đã tồn tại

`JpaItemWriter` hỗ trợ hai cách ghi:

- `persist`: tạo entity mới trong persistence context.
- `merge`: đồng bộ trạng thái của entity detached vào một instance managed.

Ví dụ entity mới:

```java
Customer customer = new Customer("C001", "Nguyen An");
entityManager.persist(customer);
```

Ví dụ entity detached cần merge:

```java
Customer detachedCustomer = loadFromEarlierContext();
detachedCustomer.setName("An Nguyen");

Customer managedCopy = entityManager.merge(detachedCustomer);
```

`merge()` trả về instance managed. Object truyền vào có thể vẫn là detached. Nếu cần thao tác tiếp trên entity managed, hãy dùng object được trả về từ `merge()`.

Trong `JpaItemWriter`, `usePersist(true)` phù hợp khi mọi item đều là entity mới theo contract của nguồn. Nếu item có thể đã tồn tại, `persist` có thể gây lỗi identity/constraint. Mặc định merge linh hoạt hơn cho detached entity nhưng có thể phát sinh truy vấn và chi phí khác.

Clear sau khi writer hoàn tất sẽ detach cả các entity được persist/merge trong chunk. Không giữ reference rồi kỳ vọng chúng vẫn managed ở chunk kế tiếp.

## 8. Tích hợp JpaItemWriter vào chunk step

Ví dụ step xử lý customer:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        JpaTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemProcessor<Customer, Customer> customerProcessor,
        JpaItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<Customer, Customer>chunk(300, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
```

Trong ví dụ, mỗi chunk có tối đa 300 item. `JpaItemWriter` ghi các item của chunk, flush và clear persistence context theo cấu hình. Transaction manager commit khi chunk hoàn tất.

Nếu dùng `PlatformTransactionManager` làm kiểu tham số thay vì `JpaTransactionManager`, cần bảo đảm instance thực tế là transaction manager tương thích với `EntityManagerFactory` đang dùng. Việc dùng một JDBC transaction manager không tự động bảo đảm JPA `EntityManager` tham gia cùng transaction.

## 9. Tự viết ItemWriter với flush và clear

Khi cần logic ghi riêng, có thể tự triển khai `ItemWriter` và quản lý `EntityManager` được Spring inject:

```java
@Component
public class ClearingCustomerWriter implements ItemWriter<Customer> {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public void write(Chunk<? extends Customer> chunk) {
        for (Customer customer : chunk) {
            entityManager.merge(customer);
        }

        entityManager.flush();
        entityManager.clear();
    }
}
```

`@PersistenceContext` thường inject một shared `EntityManager` proxy gắn với transaction hiện tại trong môi trường Spring. Cần cấu hình transaction manager phù hợp để proxy lấy đúng `EntityManager`.

Ví dụ này dùng `merge` cho mọi item. Nếu toàn bộ item là entity mới, có thể dùng `persist`; nếu dữ liệu có cả entity mới và entity hiện hữu, cần một quy tắc rõ ràng để tránh lỗi hoặc truy vấn không cần thiết.

Không nên tự viết writer chỉ để gọi `clear()` nếu `JpaItemWriter` đã đáp ứng nhu cầu. Writer tự viết cần tự chịu trách nhiệm mapping, merge/persist, exception, lifecycle và transaction semantics.

## 10. Clear trong writer hay dùng listener?

Có thể nghĩ đến việc clear persistence context trong `ChunkListener` hoặc `ItemWriteListener`. Tuy nhiên, cần hiểu thời điểm callback và transaction boundary.

| Vị trí | Nhận xét |
|---|---|
| Bên trong `JpaItemWriter` sau flush | Rõ ràng writer hoàn tất ghi chunk rồi clear; đây là lựa chọn trực tiếp và dễ kiểm soát. |
| Custom writer sau `flush()` | Phù hợp khi writer có logic ghi riêng. |
| `afterWrite` listener | Có thể chạy sau writer nhưng trước khi transaction commit; cần chắc chắn flush đã xảy ra và context đúng là context cần clear. |
| `afterChunk` listener | Callback ở lifecycle chunk; transaction có thể đã hoàn tất tùy callback contract. Không nên dùng như cách thay thế mặc định cho writer quản lý persistence context. |

Nếu chỉ muốn clear sau khi JPA writer đã ghi xong, cấu hình `JpaItemWriter.setClearPersistenceContext(true)` là cách đơn giản hơn. Nếu có listener đặc biệt, hãy xác minh callback chạy ở thời điểm nào trong phiên bản Spring Batch đang dùng và kiểm tra transaction có còn active không.

## 11. Clear persistence context detach tất cả entity

`EntityManager.clear()` không chỉ detach entity vừa ghi. Nó detach **tất cả** entity đang managed trong persistence context đó.

Điều này có thể ảnh hưởng tới:

- Entity được reader hoặc processor load trước đó trong cùng context.
- Entity liên quan qua quan hệ `@OneToMany`, `@ManyToOne`, `@OneToOne` hoặc `@ManyToMany`.
- Entity khác được service load trong cùng transaction.
- Thay đổi chưa flush của một entity không nằm trong chunk.
- Lazy collection/proxy cần persistence context để load dữ liệu.

Ví dụ:

```java
Customer customer = entityManager.find(Customer.class, 1L);
Order order = entityManager.find(Order.class, 10L);

entityManager.flush();
entityManager.clear();

// customer và order hiện là detached.
```

Sau clear, thay đổi trên object detached không còn được dirty checking tự động. Muốn cập nhật tiếp, cần merge lại hoặc load entity mới trong một persistence context phù hợp.

Không gọi clear trong một service dùng chung nếu service đó còn dựa vào entity managed khác. Clear là thao tác trên toàn bộ persistence context, không phải chỉ trên một loại entity.

## 12. Lazy loading sau clear

Một entity detached không thể dựa vào persistence context cũ để khởi tạo lazy association.

Ví dụ:

```java
Customer customer = entityManager.find(Customer.class, 1L);
entityManager.clear();

customer.getOrders().size(); // Có thể gây LazyInitializationException.
```

Với Hibernate, lỗi thường gặp là `LazyInitializationException` khi truy cập proxy/collection cần session đã đóng hoặc entity đã detached.

Nếu processor hoặc writer cần association, hãy load nó trong transaction/persistence context còn hiệu lực bằng fetch join, entity graph, projection hoặc truy vấn riêng phù hợp. Đừng dựa vào việc giữ entity managed qua nhiều chunk.

Một chiến lược thường tốt hơn là đọc projection/DTO chỉ chứa field cần thiết cho batch, sau đó ghi entity bằng một writer rõ ràng. Điều này giảm số entity và lazy association không cần thiết trong persistence context.

## 13. Reader và writer có thể dùng persistence context khác nhau

Trong một step, reader và writer không nhất thiết dùng cùng một `EntityManager` hoặc persistence context.

Ví dụ, `JpaPagingItemReader` có thể quản lý entity manager riêng cho quá trình đọc và trả entity theo semantics của reader. Writer có thể lấy transactional entity manager gắn với transaction của chunk. Clear trong writer chỉ clear context mà writer đang sử dụng; nó không nhất thiết clear entity manager nội bộ của reader.

Vì vậy, khi chẩn đoán memory growth:

- Xác định reader đang dùng `JpaPagingItemReader`, `HibernateCursorItemReader`, JDBC projection hay custom reader.
- Xác định entity nào được giữ managed trong reader context.
- Xác định writer dùng `JpaItemWriter` hay một `EntityManager` được inject.
- Xác định context nào tồn tại xuyên page/chunk và context nào được đóng khi kết thúc transaction.
- Đừng giả định `entityManager.clear()` trong writer giải phóng mọi entity được tạo bởi reader khác.

Nếu reader là nguồn gây giữ entity, cần cấu hình page size/lifecycle phù hợp hoặc dùng projection/DTO để không materialize entity managed không cần thiết.

## 14. JpaPagingItemReader và page lifecycle

`JpaPagingItemReader` đọc dữ liệu JPA theo page. Reader có lifecycle persistence context riêng để truy vấn và quản lý các entity của page. Tùy phiên bản/cấu hình, reader thực hiện flush/clear hoặc detach các entity khi chuyển page để hạn chế context tăng không giới hạn.

Một số điểm cần nhớ:

- Page size là số entity reader lấy trong một lần query.
- Chunk size là số item step xử lý trước khi commit.
- Page boundary và chunk boundary có thể khác nhau.
- Entity được trả từ reader có thể ở trạng thái detached khi processor xử lý.
- Không dựa vào lazy loading từ reader context nếu context đó đã bị clear/đóng.

Nếu page size lớn hơn chunk size, reader có thể đã load một page trước khi step tiêu thụ hết page đó. Điều này ảnh hưởng heap. Chọn page size dựa trên kích thước entity và workload.

## 15. Clear persistence context có thay thế commit không?

Không. Đây là nhầm lẫn nguy hiểm.

Ví dụ:

```java
entityManager.persist(customer);
entityManager.flush();
entityManager.clear();
```

SQL `INSERT` có thể đã được gửi tới database, nhưng transaction chưa chắc đã commit. Nếu writer hoặc step gặp lỗi sau đó, transaction manager có thể rollback thay đổi.

Không nên gọi `EntityTransaction.commit()` trực tiếp từ writer được quản lý bởi Spring Batch. Việc đó phá vỡ transaction boundary mà step điều phối. Hãy để `PlatformTransactionManager` của step commit/rollback.

## 16. Clear và rollback khi writer lỗi

Nếu `flush()` ném exception, writer chưa nên tiếp tục clear như thể ghi thành công. Exception cần được truyền ra để transaction rollback hoặc áp dụng fault tolerance policy.

Ví dụ custom writer an toàn hơn:

```java
@Override
public void write(Chunk<? extends Customer> chunk) {
    for (Customer customer : chunk) {
        entityManager.merge(customer);
    }

    entityManager.flush(); // Nếu lỗi, exception đi lên step.
    entityManager.clear(); // Chỉ chạy khi flush thành công.
}
```

Nếu `flush()` thành công rồi `clear()` được gọi, transaction vẫn có thể rollback khi một thành phần khác của chunk thất bại. Việc clear không làm thay đổi khả năng rollback SQL của transaction.

Sau rollback, transaction-scoped entity manager có thể bị đánh dấu rollback-only hoặc đóng theo transaction manager. Không nên tiếp tục dùng các entity managed/detached của transaction lỗi như thể chúng vẫn đồng bộ với database. Khi retry, hãy dùng lifecycle và semantics của Spring Batch/JPA writer.

## 17. Bulk update/delete và persistence context stale

JPQL bulk update/delete hoặc native SQL thường cập nhật database trực tiếp mà không đồng bộ trạng thái từng entity đang managed trong persistence context.

Ví dụ:

```java
entityManager.createQuery("""
        update Customer c
           set c.status = :status
         where c.lastLogin < :cutoff
        """)
        .setParameter("status", Status.INACTIVE)
        .setParameter("cutoff", cutoff)
        .executeUpdate();
```

Các `Customer` đã được load trước đó có thể vẫn chứa status cũ trong persistence context. Cần cân nhắc flush các thay đổi đang chờ trước bulk operation và clear/refresh các entity sau đó:

```java
entityManager.flush();
int updated = query.executeUpdate();
entityManager.clear();
```

Đây là trường hợp clear còn giúp tránh đọc lại trạng thái stale. Nếu chỉ một entity cần cập nhật lại, có thể dùng `refresh()` hoặc `detach()` phù hợp thay vì clear toàn bộ context.

## 18. Clear toàn bộ context hay detach từng entity?

JPA cung cấp một số thao tác quản lý entity:

| API | Tác dụng |
|---|---|
| `clear()` | Detach tất cả entity trong persistence context. |
| `detach(entity)` | Detach một entity cụ thể. |
| `refresh(entity)` | Nạp lại trạng thái entity managed từ database, ghi đè thay đổi local chưa flush theo semantics của JPA. |
| `merge(entity)` | Copy trạng thái entity detached vào một entity managed và trả về instance managed. |
| `flush()` | Đồng bộ thay đổi đang chờ xuống database. |

Clear toàn bộ phù hợp khi toàn bộ entity trong context đã hoàn thành và không còn cần dirty checking. Detach từng entity phù hợp khi chỉ muốn loại một object mà vẫn cần các entity khác managed.

Trong batch writer, clear theo chunk thường đơn giản và hiệu quả nếu writer sở hữu phạm vi persistence context đó. Nếu context được chia sẻ với các thao tác khác trong cùng transaction, cần thận trọng vì clear sẽ tác động tới tất cả.

## 19. Tác động của cascade và quan hệ entity

Khi persist/merge một entity có quan hệ cascade, JPA có thể quản lý thêm các entity liên quan trong cùng persistence context.

Ví dụ:

```java
@Entity
class Customer {
    @OneToMany(mappedBy = "customer", cascade = CascadeType.PERSIST)
    private List<Order> orders = new ArrayList<>();
}
```

Ghi một customer có nhiều order có thể khiến nhiều entity được quản lý trong một chunk. Vì vậy, số entity thực tế trong persistence context có thể lớn hơn số item của chunk.

Nếu một chunk gồm 300 customer và mỗi customer có hàng trăm child entity, clear sau chunk vẫn cần được xem xét cùng kích thước object graph. Có thể phải giảm chunk size, ghi child theo batch riêng hoặc chỉ load quan hệ thực sự cần thiết.

Clear không xóa dữ liệu quan hệ trong database và không xóa collection khỏi Java object. Nó chỉ detach các entity. Object graph vẫn có thể còn trong heap nếu processor, writer hoặc cache khác giữ reference.

## 20. Chunk size ảnh hưởng số entity managed

Chunk size lớn thường có thể làm tăng số entity cùng tồn tại trong transaction/persistence context. Tuy nhiên, số entity không nhất thiết bằng chunk size vì:

- Một item có thể tạo hoặc load nhiều entity liên quan.
- Processor có thể query thêm entity.
- Writer có thể merge và tạo managed copy.
- Reader có thể load page lớn hơn chunk.
- Listener hoặc cache có thể giữ reference qua nhiều chunk.

Ví dụ:

| Chunk size | Số item trong một lần ghi tối đa | Nhận xét |
|---:|---:|---|
| 50 | 50 | Transaction ngắn, clear thường xuyên hơn, overhead commit cao hơn. |
| 300 | 300 | Điểm bắt đầu để benchmark với entity vừa phải. |
| 2.000 | 2.000 | Có thể tăng heap, dirty checking và thời gian transaction. |

Đây là ví dụ minh họa, không phải giá trị khuyến nghị cố định. Hãy benchmark bằng kích thước object graph và database gần production.

## 21. Clear và JDBC batch insert/update

Clear persistence context không tự động bật JDBC batching. Hai cơ chế giải quyết hai vấn đề khác nhau:

- `clear()` giảm số entity được JPA quản lý trong bộ nhớ.
- JDBC batching gom nhiều SQL statement tương thích thành batch gửi tới database.

Với Hibernate, có thể cấu hình batching qua các property như `hibernate.jdbc.batch_size`, nhưng hiệu quả phụ thuộc loại ID generation, statement shape, driver và mapping. Một số chiến lược sinh ID có thể hạn chế batching cho insert.

Ví dụ cấu hình Hibernate trong Spring Boot:

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

Đừng đặt batch size JDBC quá lớn chỉ vì chunk size lớn. Cần đo số statement, batch execution, heap và thời gian commit. Clear sau khi flush không thay thế batching; writer có thể flush các statement theo cơ chế provider đã cấu hình rồi clear context.

## 22. Không clear trước khi hoàn tất logic cần entity managed

Processor có thể cập nhật entity rồi writer ghi nó. Nếu clear xảy ra quá sớm, các bước sau có thể nhận entity detached và không còn dirty checking tự động.

Ví dụ không nên:

```java
Customer customer = entityManager.find(Customer.class, id);
customer.setStatus(Status.READY);
entityManager.clear();

return customer; // Detached; thay đổi cần được merge lại để persist.
```

Nếu writer sau đó dùng `JpaItemWriter` với merge, thay đổi có thể được đồng bộ, nhưng sẽ phát sinh merge và có thể có chi phí truy vấn. Nếu writer giả định item vẫn managed, thay đổi có thể không được ghi.

Hãy đặt clear tại ranh giới sau khi writer đã hoàn tất công việc với entity. Đừng clear ở reader/processor chỉ để giảm heap nếu pipeline vẫn cần managed state.

## 23. Khi nào không nên clear?

Không phải lúc nào clear cũng phù hợp. Có thể không cần clear thủ công nếu:

- Persistence context đã được đóng sau mỗi transaction/chunk và memory profile ổn định.
- Writer cần tiếp tục dùng các entity managed trong cùng một transaction sau khi ghi.
- Các thay đổi chưa flush của entity khác trong context vẫn cần dirty checking.
- Service dùng chung context và còn thao tác với entity managed sau writer.
- Clear sẽ làm hỏng logic lazy loading hoặc cascade trong cùng chunk.

Trong các trường hợp này, cần xác định chính xác lifecycle persistence context và có thể dùng transaction-scoped context, DTO/projection hoặc detach có chọn lọc thay vì clear toàn bộ.

## 24. Clear persistence context theo chunk với listener

Nếu không thể dùng `JpaItemWriter`, đôi khi có thể dùng listener hoặc một wrapper writer để thực hiện clear sau khi ghi. Một wrapper giúp giữ thứ tự thao tác ngay trong writer:

```java
public class ClearingItemWriter<T> implements ItemWriter<T> {

    private final ItemWriter<T> delegate;
    private final EntityManager entityManager;

    public ClearingItemWriter(
            ItemWriter<T> delegate,
            EntityManager entityManager) {
        this.delegate = delegate;
        this.entityManager = entityManager;
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        delegate.write(chunk);
        entityManager.flush();
        entityManager.clear();
    }
}
```

Đây là pattern minh họa; chỉ dùng khi `delegate` và `entityManager` tham gia cùng transaction/persistence context và không clear một context mà delegate còn cần sau khi return. Nếu delegate là `JpaItemWriter` đã flush/clear, wrapper này dư thừa.

Không inject một `EntityManager` tùy ý được tạo ngoài Spring transaction rồi mong nó clear context đang dùng bởi writer. Phải bảo đảm cùng `EntityManagerFactory` và cùng transactional context.

## 25. Xử lý entity detached qua các chunk

Sau clear, object Java vẫn tồn tại nếu ứng dụng còn reference, nhưng trạng thái của nó là detached. Nếu một item được lưu vào cache rồi sử dụng ở chunk sau, JPA không tự theo dõi các thay đổi trên object đó.

Ví dụ:

```java
Customer customer = entityManager.merge(detachedCustomer);
entityManager.flush();
entityManager.clear();

customer.setName("Updated later"); // Không còn dirty checking.
```

Để cập nhật ở chunk sau:

```java
Customer managed = entityManager.merge(customer);
managed.setName("Updated later");
```

Hoặc load lại entity theo ID trong persistence context của transaction mới:

```java
Customer managed = entityManager.find(Customer.class, customerId);
managed.setName("Updated later");
```

Trong batch, tốt nhất không giữ entity detached lâu dài trong cache nếu chỉ cần khóa định danh. Lưu ID hoặc DTO nhỏ, rồi load lại dữ liệu cần thiết trong chunk tương ứng.

## 26. Transaction manager phải tương thích với JPA

Để `JpaItemWriter` tham gia transaction của chunk, cấu hình step với transaction manager dùng cùng `EntityManagerFactory`:

```java
@Bean
JpaTransactionManager transactionManager(EntityManagerFactory emf) {
    return new JpaTransactionManager(emf);
}
```

Trong ứng dụng có cả JDBC và JPA, cần hiểu cách hai tài nguyên tham gia transaction. `JpaTransactionManager` có thể phối hợp với JDBC connection của cùng datasource trong các điều kiện cấu hình phù hợp, nhưng không phải mọi cấu hình đa datasource đều tự động atomic.

Không tạo `EntityManager` bằng `entityManagerFactory.createEntityManager()` trong writer rồi tự đóng/mở tùy ý nếu mục tiêu là tham gia transaction của Spring. EntityManager tự tạo theo cách đó có thể không được transaction manager quản lý như mong đợi.

## 27. Kiểm thử flush và clear

Test cần xác nhận hai điều riêng biệt:

1. Thay đổi của chunk đã được flush vào transaction/database theo mong đợi.
2. Entity đã được detach sau khi writer hoàn tất nếu clear được bật.

Ví dụ với `EntityManager` trong integration test:

```java
@Test
void writerFlushesAndClearsPersistenceContext() {
    Customer customer = new Customer("C001", "Nguyen An");

    TransactionTemplate transaction = new TransactionTemplate(transactionManager);
    transaction.executeWithoutResult(status -> {
        customerWriter.write(new Chunk<>(List.of(customer)));

        assertThat(entityManager.contains(customer)).isFalse();
    });

    Customer persisted = entityManager.find(Customer.class, customer.getId());
    assertThat(persisted.getName()).isEqualTo("Nguyen An");
}
```

Test thực tế cần dùng đúng persistence context mà writer sử dụng. Nếu writer merge detached input, object đầu vào có thể vẫn detached ngay cả trước khi clear; do đó `contains(input)` không phải bằng chứng đủ để xác nhận clear. Có thể kiểm tra một entity được load/managed trong cùng context hoặc spy/mock `EntityManager.clear()` ở unit test.

Với database test, cần flush và clear trước khi đọc lại để tránh first-level cache trả object cũ làm test sai lệch. Nên dùng transaction boundary rõ ràng và kiểm tra dữ liệu sau commit khi test yêu cầu xác nhận persistence thực tế.

## 28. Kiểm thử clear theo từng chunk

Một integration test cho step nên xử lý nhiều chunk và xác nhận writer clear sau mỗi lần ghi, không chỉ một lần ở cuối job.

Ví dụ test strategy:

1. Tạo input có nhiều hơn hai lần chunk size.
2. Dùng writer wrapper hoặc spy để đếm số lần flush/clear.
3. Chạy step với chunk size nhỏ để có nhiều lần `write()`.
4. Xác nhận clear được gọi sau mỗi write thành công.
5. Xác nhận tổng số record trong database đúng.
6. Làm một chunk thất bại và xác nhận transaction rollback.
7. Restart job và xác nhận dữ liệu không bị mất hoặc ghi trùng.

Không chỉ assert số lần gọi clear. Cần kiểm tra dữ liệu và transaction semantics, vì clear được gọi nhưng writer có thể flush sai, dùng sai EntityManager hoặc làm mất thay đổi chưa đồng bộ.

## 29. Kiểm thử rollback sau flush

Một test quan trọng là chứng minh flush không đồng nghĩa commit:

1. Trong transaction, persist hoặc merge một entity.
2. Gọi `flush()`.
3. Phát sinh exception trước khi transaction commit.
4. Rollback transaction.
5. Mở transaction mới và xác nhận entity không được lưu.

Ví dụ ý tưởng:

```java
assertThatThrownBy(() -> transactionTemplate.executeWithoutResult(status -> {
    entityManager.persist(new Customer("C999", "Temporary"));
    entityManager.flush();
    throw new IllegalStateException("Force rollback");
}));

assertThat(customerRepository.existsByCustomerId("C999")).isFalse();
```

Test này xác nhận `flush()` đã gửi SQL nhưng transaction vẫn có thể rollback. Nếu dùng database/provider cụ thể, cần bảo đảm exception được phát sinh trong transaction và test kiểm tra sau khi transaction đã kết thúc.

## 30. Theo dõi memory và persistence context

Khi nghi ngờ memory leak do JPA, hãy quan sát nhiều chỉ số:

- Heap used và old generation sau mỗi chunk.
- Allocation rate và GC pause.
- Số item mỗi chunk và kích thước object graph.
- Thời gian flush và commit.
- Số SQL SELECT/INSERT/UPDATE được thực hiện.
- Số entity/collection được giữ trong heap dump.
- Reference path cho thấy EntityManager, Hibernate Session, collection hoặc cache nào giữ entity.

Với Hibernate, có thể bật statistics trong môi trường đo kiểm để quan sát entity load/fetch/insert/update và query count. Không nên bật logging SQL quá chi tiết trong production nếu nó làm tăng I/O và lộ dữ liệu nhạy cảm.

Nếu heap tăng đều sau mỗi chunk dù writer clear, hãy kiểm tra:

- Có một cache/list trong processor hoặc listener giữ entity không.
- Reader có persistence context riêng chưa được clear/đóng không.
- Có entity graph lớn hoặc collection lazy được khởi tạo không.
- Có listener lưu toàn bộ item để tổng hợp báo cáo không.
- Có transaction hoặc EntityManager extended sống lâu hơn dự kiến không.
- Có nhiều worker đồng thời, mỗi worker giữ chunk/context riêng không.

Clear chỉ giải phóng reference trong persistence context. Nó không giải phóng object còn được ứng dụng giữ ở nơi khác.

## 31. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Heap tăng theo tổng số item | Persistence context giữ entity managed quá lâu. | Flush/clear theo chunk hoặc kết thúc context đúng transaction scope. |
| Thay đổi không được ghi | Clear trước flush làm entity detached khi còn thay đổi pending. | Flush trước rồi mới clear. |
| Entity không còn lazy load được | Clear detach entity trước khi truy cập association. | Fetch dữ liệu cần thiết trước clear hoặc dùng DTO/projection. |
| Thay đổi sau clear không được lưu | Code tiếp tục sửa entity detached và mong dirty checking. | Merge/load lại trong context mới. |
| Dữ liệu đã flush nhưng vẫn mất | Transaction rollback sau flush. | Hiểu flush không commit; kiểm tra transaction manager. |
| `LazyInitializationException` | Truy cập lazy proxy sau khi context bị clear/đóng. | Fetch association trong phạm vi context hoặc không truyền entity cần lazy load qua boundary. |
| Clear làm ảnh hưởng entity không liên quan | `clear()` detach toàn bộ entity trong context. | Giới hạn phạm vi context hoặc dùng `detach(entity)` có chọn lọc. |
| Writer không tham gia transaction | EntityManagerFactory/transaction manager không tương thích hoặc tự tạo EM ngoài Spring. | Dùng JpaTransactionManager phù hợp và transactional EntityManager. |
| Reader vẫn giữ nhiều entity | Reader dùng persistence context riêng; writer clear context khác. | Kiểm tra reader lifecycle/page size và dùng projection khi phù hợp. |
| SQL không được batch | Clear bị nhầm với JDBC batching hoặc flush từng item. | Cấu hình Hibernate JDBC batch và đo execution thực tế. |
| Entity bị ghi hai lần sau retry | Side effect không idempotent hoặc transaction không bao phủ đúng resource. | Dùng unique key/upsert và kiểm thử rollback/restart. |
| Clear trong listener không hiệu quả | Callback chạy sai thời điểm hoặc dùng nhầm EntityManager. | Ưu tiên cấu hình JpaItemWriter hoặc clear trong writer sau flush. |

## 32. Quy trình thiết kế clear persistence context theo chunk

Khi xây dựng JPA step có khối lượng dữ liệu lớn, hãy xác định:

1. **Xác định EntityManager:** reader, processor và writer đang dùng persistence context nào?
2. **Xác định lifecycle:** context là transaction-scoped hay extended, mở/đóng ở đâu?
3. **Chọn chunk size:** dựa trên số entity và kích thước object graph, không chỉ số item.
4. **Chọn writer:** ưu tiên `JpaItemWriter` nếu semantics persist/merge đáp ứng yêu cầu.
5. **Bật clear:** cấu hình `clearPersistenceContext(true)` khi cần detach entity sau khi ghi chunk.
6. **Giữ thứ tự:** flush thành công trước clear; để Spring Batch quản lý commit.
7. **Kiểm tra lazy relation:** bảo đảm mọi dữ liệu cần thiết đã được fetch trước khi clear.
8. **Xử lý detached entity:** merge/load lại nếu cần cập nhật trong context mới.
9. **Cấu hình transaction:** dùng transaction manager tương thích với EntityManagerFactory.
10. **Tối ưu JDBC batch:** xem xét riêng với clear và đo hiệu quả.
11. **Kiểm tra bulk operation:** flush/clear hoặc refresh để tránh persistence context stale.
12. **Đo memory:** heap, GC, object graph và reference path sau nhiều chunk.
13. **Kiểm thử:** nhiều chunk, clear, flush failure, rollback, restart và dữ liệu cuối cùng.

## 33. Những điểm cần ghi nhớ

- Persistence context là first-level cache do `EntityManager` quản lý; nó theo dõi entity managed và thay đổi của chúng.
- Context tồn tại quá lâu có thể giữ nhiều entity và snapshot, làm heap tăng theo số item.
- `flush()` gửi thay đổi thành SQL trong transaction hiện tại; nó không commit.
- `clear()` detach toàn bộ entity khỏi persistence context; nó không commit hoặc rollback.
- Khi cần đồng bộ trước khi detach, luôn thực hiện flush thành công rồi mới clear.
- `JpaItemWriter` hỗ trợ `clearPersistenceContext`; cấu hình tường minh khi cần clear sau mỗi lần ghi chunk.
- `persist` phù hợp entity mới; `merge` copy trạng thái detached vào instance managed và trả về instance đó.
- Clear ảnh hưởng mọi entity trong context, không chỉ item của chunk; cần thận trọng với service/context dùng chung.
- Entity detached không còn dirty checking và có thể không lazy load được association.
- Reader và writer có thể dùng persistence context khác nhau; clear trong writer không tự giải phóng context của reader.
- Page size, chunk size và số entity trong object graph cùng ảnh hưởng memory.
- Clear không thay thế JDBC batching, transaction commit hoặc idempotency.
- Transaction manager phải phối hợp đúng với `EntityManagerFactory`; để Spring Batch quản lý commit/rollback.
- Kiểm thử clear theo nhiều chunk, rollback sau flush, detached behavior và dữ liệu sau commit.

Clear persistence context theo chunk giúp giới hạn số entity JPA tiếp tục quản lý trong một batch lớn. Hãy hiểu rõ phạm vi `EntityManager`, đặt thao tác clear sau khi writer flush thành công, và để transaction manager của Spring Batch quyết định commit hoặc rollback. Khi kết hợp chunk size phù hợp, fetch dữ liệu có chọn lọc, writer đúng lifecycle và kiểm thử restart/rollback, ứng dụng có thể xử lý lượng entity lớn mà không để first-level cache tích lũy không kiểm soát.
