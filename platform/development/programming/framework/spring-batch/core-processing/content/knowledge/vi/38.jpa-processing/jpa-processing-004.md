# Flush trước commit

Trong Spring Batch, khi writer lưu entity bằng JPA, thay đổi thường được giữ trong **persistence context** trước khi được đồng bộ xuống database. Lệnh `flush()` yêu cầu JPA đồng bộ các thay đổi đang chờ với database trong transaction hiện tại. Sau đó, transaction của chunk vẫn tiếp tục và chỉ commit khi Spring Batch hoàn tất các bước của chunk.

Vì vậy, **flush không phải commit**. Flush gửi các câu SQL cần thiết tới database và giúp phát hiện nhiều lỗi persistence sớm hơn; commit mới hoàn tất transaction và làm thay đổi trở nên bền vững theo transaction semantics của database.

Trong Spring Batch, `JpaItemWriter` thường thực hiện flush sau khi ghi chunk. Khi dùng custom JPA writer hoặc Spring Data repository, cần hiểu thời điểm flush, persistence context và transaction manager để tránh ghi dở, giữ quá nhiều entity trong memory hoặc hiểu nhầm rằng dữ liệu đã commit.

## 1. Persistence context giữ thay đổi như thế nào?

EntityManager quản lý một persistence context, nơi JPA theo dõi các entity đang ở trạng thái managed. Khi ứng dụng thay đổi một entity managed, provider thường đánh dấu thay đổi trong bộ nhớ. SQL có thể chưa được gửi ngay tại thời điểm setter được gọi.

Ví dụ:

~~~java
Order order = entityManager.find(Order.class, 1001L);
order.setStatus(OrderStatus.PAID);
~~~

Nếu order đang managed, dirty checking của JPA phát hiện status đã thay đổi. Ứng dụng không nhất thiết phải gọi update SQL thủ công. Khi flush, provider tạo và thực thi câu UPDATE phù hợp.

Có thể hình dung:

~~~text
EntityManager / Persistence Context
             |
             | entity được load hoặc persist
             v
       Managed entity
             |
             | thay đổi field
             v
      Pending changes
             |
             | flush()
             v
       SQL được thực thi
             |
             | commit transaction
             v
      Transaction hoàn tất
~~~

Trước flush, thay đổi có thể chỉ tồn tại trong persistence context. Sau flush, database đã thực thi SQL trong transaction hiện tại, nhưng transaction vẫn có thể rollback.

## 2. Flush là gì?

`EntityManager.flush()` đồng bộ trạng thái persistence context với database. Provider kiểm tra các entity managed, phát hiện thay đổi, xử lý persist/remove và gửi câu SQL cần thiết.

Flush có thể tạo ra:

- INSERT cho entity mới được persist.
- UPDATE cho entity managed đã thay đổi.
- DELETE cho entity đã được remove.
- Các thao tác liên quan tới cascade.
- Kiểm tra constraint hoặc optimistic locking ở thời điểm database thực thi SQL.

Ví dụ:

~~~java
@Transactional
public void updateOrder(Long id) {
    Order order = entityManager.find(Order.class, id);
    order.setStatus(OrderStatus.PAID);

    entityManager.flush();

    // SQL UPDATE đã được gửi trong transaction hiện tại.
    // Transaction vẫn chưa commit tại đây.
}
~~~

Nếu transaction sau đó rollback, UPDATE đã flush vẫn có thể được database hoàn tác. Flush không tạo một transaction độc lập và cũng không yêu cầu database commit.

Flush áp dụng cho các thay đổi đang chờ trong persistence context, không chỉ entity vừa được sửa ngay trước lời gọi flush.

## 3. Flush khác commit như thế nào?

Đây là khác biệt quan trọng nhất khi làm việc với JPA trong chunk processing.

| Thuộc tính | Flush | Commit |
|---|---|---|
| Mục đích | Đồng bộ persistence context với database | Hoàn tất transaction |
| SQL được thực thi | Có thể gửi INSERT/UPDATE/DELETE | Thực thi phần còn lại cần thiết và hoàn tất transaction |
| Transaction còn mở | Có | Không, sau khi commit thành công |
| Có thể rollback sau đó | Có | Không thể rollback transaction đã commit |
| Dữ liệu bền vững | Chưa được bảo đảm | Theo durability semantics của database |
| Lock database | Có thể được giữ tới transaction end | Được giải phóng theo database |
| Kiểm tra constraint | Nhiều lỗi xuất hiện khi flush | Một số constraint deferred chỉ kiểm tra lúc commit |

Ví dụ thứ tự:

~~~text
BEGIN
  |
  +--> entityManager.persist(order)
  |
  +--> entityManager.flush()
  |       |
  |       +--> INSERT được gửi tới database
  |       +--> Constraint/SQL error có thể xuất hiện
  |
  +--> processor/writer hoặc stream state tiếp tục
  |
  +--> COMMIT
          |
          +--> Transaction hoàn tất
~~~

Nếu một lỗi xảy ra sau flush nhưng trước commit, transaction vẫn có thể rollback. Không được báo cho hệ thống khác rằng dữ liệu đã hoàn tất chỉ vì flush thành công.

## 4. Khi nào JPA tự động flush?

Ứng dụng không cần gọi flush sau mỗi thao tác. JPA provider có thể tự flush ở một số thời điểm theo FlushModeType và transaction lifecycle.

Hai mode chính:

- `FlushModeType.AUTO`: mode mặc định trong nhiều cấu hình. Provider phải bảo đảm các thay đổi có thể ảnh hưởng kết quả query được phản ánh khi query chạy; provider có thể flush trước query.
- `FlushModeType.COMMIT`: provider được yêu cầu flush trước khi transaction commit. Kết quả query khi persistence context còn thay đổi chưa flush có thể không phản ánh các thay đổi đó; không nên dựa vào query visibility ở mode này.

Ví dụ:

~~~java
entityManager.setFlushMode(FlushModeType.AUTO);
~~~

Với AUTO, một query có thể kích hoạt flush sớm hơn dự kiến. Vì vậy, câu lệnh query trong processor hoặc writer có thể là điểm lỗi constraint xuất hiện, dù code không gọi flush tường minh.

Không nên đổi flush mode để che giấu lỗi. Hãy chọn mode theo semantics cần thiết và kiểm thử với provider/database thực tế.

## 5. Vì sao cần flush trước commit trong Spring Batch?

Flush tường minh có thể hữu ích khi muốn:

- Buộc SQL được thực thi trong giai đoạn writer, để lỗi xuất hiện gần thao tác ghi.
- Phát hiện sớm unique constraint, foreign key hoặc optimistic locking conflict.
- Đồng bộ thay đổi trước một truy vấn cần nhìn thấy dữ liệu vừa cập nhật.
- Giải phóng hoặc clear persistence context sau khi SQL đã được gửi.
- Đo thời gian thực thi SQL trong writer thay vì để lỗi xuất hiện muộn ở commit.

Tuy nhiên, flush không thay thế transaction commit và không bảo đảm mọi constraint đều được kiểm tra ngay lúc đó. Database có deferred constraint có thể chỉ báo lỗi khi commit.

Trong chunk Step, flush thường nên xảy ra trong writer trước khi Step cập nhật stream state và commit transaction. Điều này giúp nhiều lỗi persistence xuất hiện trong phạm vi lời gọi writer, dễ gắn với chunk hơn.

## 6. Chunk transaction trong Spring Batch

Một chunk-oriented Step gom các item, xử lý và ghi trong transaction. Ví dụ chunk size 100:

~~~text
Chunk transaction begins
       |
       v
Read up to 100 items
       |
       v
Process items
       |
       v
Writer writes 100 items
       |
       v
JPA flush
       |
       v
Update ExecutionContext / stream state
       |
       v
Commit chunk transaction
~~~

Nếu writer flush thành công, Spring Batch vẫn chưa commit ngay tại thời điểm đó. Các thao tác tiếp theo trong lifecycle chunk có thể còn thất bại.

Nếu exception được phân loại rollback, transaction của chunk rollback. Reader state và metadata transaction-aware được quản lý theo cơ chế của Spring Batch và transaction manager.

Không tự mở một transaction riêng trong writer nếu mong muốn dữ liệu JPA rollback cùng chunk. Writer phải tham gia transaction do Step quản lý.

## 7. JpaItemWriter và flush tự động

Spring Batch cung cấp `JpaItemWriter` để ghi item qua EntityManager. Writer sử dụng EntityManagerFactory đã cấu hình và lấy EntityManager gắn với transaction hiện tại.

Ví dụ:

~~~java
@Bean
public JpaItemWriter<Order> orderJpaWriter(
        EntityManagerFactory entityManagerFactory) {

    return new JpaItemWriterBuilder<Order>()
            .entityManagerFactory(entityManagerFactory)
            .usePersist(true)
            .build();
}
~~~

Trong các phiên bản Spring Batch phổ biến, JpaItemWriter ghi các item trong chunk rồi gọi flush. Nhiều phiên bản cũng clear persistence context sau khi flush để tránh giữ quá nhiều entity managed. Hãy kiểm tra API và mặc định của đúng phiên bản Spring Batch trong dự án, vì các tùy chọn như `usePersist` và clear persistence context có thể khác theo version.

Khi dùng JpaItemWriter chuẩn, thông thường không cần gọi thêm flush thủ công sau writer. Gọi flush nhiều lần không làm transaction commit sớm hơn và có thể giảm hiệu quả JDBC batching.

## 8. Persist và merge trong JpaItemWriter

JpaItemWriter có thể dùng persist hoặc merge tùy cấu hình.

- `persist(entity)` dành cho entity mới cần được quản lý trong persistence context.
- `merge(entity)` sao chép trạng thái của entity detached/new vào một instance managed và trả về instance managed đó.

Ví dụ:

~~~java
Order managed = entityManager.merge(detachedOrder);
~~~

Không nên giả định detachedOrder trở thành managed sau merge. Đối tượng trả về từ merge mới là instance managed; object đầu vào vẫn có thể detached.

Chọn persist hay merge dựa trên lifecycle entity và cách dữ liệu đầu vào được tạo. Nếu item đã có ID nhưng thực tế chưa tồn tại trong database, merge có thể tạo hoặc cập nhật theo semantics provider. Nếu entity mới được persist nhưng trùng khóa, lỗi có thể xuất hiện khi flush hoặc commit.

Không dùng merge như cách chữa mọi lỗi duplicate key. Hãy xác định entity mới hay entity cần cập nhật và có khóa nghiệp vụ/unique constraint phù hợp.

## 9. Cấu hình transaction manager cho JPA Step

JPA writer cần EntityManager tham gia transaction của Step. Cấu hình JpaTransactionManager với đúng EntityManagerFactory:

~~~java
@Bean
public PlatformTransactionManager transactionManager(
        EntityManagerFactory entityManagerFactory) {
    return new JpaTransactionManager(entityManagerFactory);
}
~~~

Step dùng transaction manager đó:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        JpaItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

Điểm quan trọng:

- JpaItemWriter và transaction manager phải dùng cùng EntityManagerFactory.
- EntityManager phải được lấy theo transaction hiện tại.
- Không tự tạo EntityManager rồi đóng/commit riêng trong mỗi write nếu cần rollback cùng chunk.
- Không gọi commit trực tiếp trên EntityTransaction của EntityManager do Spring quản lý.

Nếu ứng dụng có nhiều persistence unit, phải chọn đúng EntityManagerFactory và transaction manager cho Step tương ứng.

## 10. Custom ItemWriter và EntityManager

Nếu cần logic ghi riêng, có thể inject EntityManager thông qua `@PersistenceContext` hoặc shared EntityManager proxy do Spring cung cấp.

Ví dụ:

~~~java
@Component
public class OrderStatusWriter implements ItemWriter<Order> {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            entityManager.persist(order);
        }

        entityManager.flush();
    }
}
~~~

EntityManager được inject theo cơ chế Spring quản lý và tham gia transaction hiện tại nếu cấu hình đúng. Không tự gọi `entityManager.getTransaction().commit()` trong writer; transaction lifecycle thuộc về Spring Batch và transaction manager.

Với custom writer, flush một lần sau khi xử lý chunk thường hợp lý hơn flush từng item. Nếu cần flush theo lô nhỏ để giới hạn persistence context, hãy cân nhắc cách clear và tác động tới entity state.

## 11. Flush và dirty checking

JPA dirty checking theo dõi thay đổi của entity managed. Khi flush, provider so sánh trạng thái hiện tại với snapshot hoặc cơ chế tracking nội bộ để xác định UPDATE cần gửi.

Ví dụ:

~~~java
Order order = entityManager.find(Order.class, id);
order.setStatus(OrderStatus.SHIPPED);
order.setShippedAt(Instant.now());

// Không cần gọi merge nếu order vẫn managed.
entityManager.flush();
~~~

Nếu entity detached, thay đổi field không tự được flush. Cần merge hoặc reattach theo cách phù hợp.

Một lỗi thường gặp là tạo object mới từ dữ liệu reader, sửa object đó rồi nghĩ JPA tự UPDATE row có cùng ID. Object mới có thể detached hoặc transient; dirty checking chỉ áp dụng cho entity managed.

Hãy hiểu trạng thái entity:

| Trạng thái | Ý nghĩa |
|---|---|
| New/Transient | Chưa được quản lý bởi persistence context |
| Managed | Được EntityManager theo dõi; thay đổi có thể flush |
| Detached | Từng managed nhưng hiện không còn được theo dõi |
| Removed | Được đánh dấu xóa trong persistence context |

Flush chỉ đồng bộ trạng thái mà persistence context quản lý và các thao tác persist/remove đã đăng ký.

## 12. Flush và cascade

Khi entity có quan hệ cascade, persist/merge/remove có thể lan sang entity liên quan theo cấu hình cascade.

Ví dụ:

~~~java
@OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST,
        orphanRemoval = true)
private List<OrderLine> lines = new ArrayList<>();
~~~

Khi persist order mới, các OrderLine có thể được persist theo cascade. Khi flush, provider thực thi các câu SQL cần thiết cho cả aggregate theo mapping.

Nếu quan hệ thiếu cascade phù hợp, child entity có thể không được lưu như mong muốn hoặc phát sinh transient object exception. Nếu orphanRemoval được bật, xóa child khỏi collection có thể dẫn tới DELETE khi flush.

Không thêm CascadeType.ALL chỉ để làm lỗi biến mất. Hãy xác định aggregate ownership và lifecycle thực tế; cascade sai có thể xóa hoặc cập nhật entity ngoài dự kiến.

## 13. Flush và constraint violation

Nhiều lỗi database chỉ xuất hiện khi SQL thực sự được thực thi. Trước flush, ứng dụng có thể chưa biết rằng hai entity sẽ vi phạm unique constraint hoặc foreign key.

Ví dụ unique key:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT uk_orders_external_ref UNIQUE (external_ref);
~~~

Hai item có cùng external_ref có thể được persist vào persistence context. Khi flush, database thực thi INSERT và phát hiện duplicate key.

Exception có thể được chuyển thành PersistenceException, ConstraintViolationException của provider hoặc exception được Spring dịch sang DataAccessException tùy stack.

Flush tường minh giúp lỗi xuất hiện ngay trong writer. Nhưng nếu database dùng deferred constraint, một số kiểm tra vẫn có thể chỉ hoàn tất khi commit. Không nên coi flush thành công là bằng chứng mọi constraint đã được thỏa mãn.

## 14. Flush và optimistic locking

Entity dùng `@Version` để phát hiện cập nhật cạnh tranh:

~~~java
@Entity
public class Order {

    @Id
    private Long id;

    @Version
    private long version;

    private OrderStatus status;
}
~~~

Khi flush một UPDATE, provider thường gửi version cũ trong điều kiện WHERE và tăng version nếu update thành công.

Ví dụ SQL khái niệm:

~~~sql
UPDATE orders
SET status = ?, version = version + 1
WHERE id = ? AND version = ?
~~~

Nếu một transaction khác đã cập nhật entity trước đó, số row cập nhật có thể bằng 0 và provider ném optimistic locking exception tại flush hoặc commit.

Đây là lỗi cạnh tranh dữ liệu, không phải lỗi kết nối tạm thời. Retry có thể đọc lại entity mới nhất và áp dụng business rule lại; không nên chỉ lặp lại cùng UPDATE với version cũ.

## 15. Flush và generated identifier

Thời điểm ID được tạo phụ thuộc chiến lược `@GeneratedValue` và database/provider.

- SEQUENCE có thể lấy sequence value trước INSERT.
- IDENTITY thường cần INSERT để database sinh ID, nên SQL có thể được thực thi sớm khi persist.
- TABLE hoặc generator tùy chỉnh có semantics riêng.

Vì vậy, không thể khẳng định mọi generated ID chỉ xuất hiện sau flush. Nếu logic cần giá trị ID, hãy hiểu strategy đang dùng và kiểm thử với database thật.

Flush cũng không tự bảo đảm mọi cột generated/default ở database đã được phản ánh vào object. Có thể cần `refresh()` hoặc mapping/generated-value support phù hợp nếu ứng dụng cần đọc lại giá trị do database tạo.

Không gọi refresh tùy tiện cho từng item vì có thể tạo thêm SELECT và ảnh hưởng throughput.

## 16. Flush order không phải thứ tự persist trong code

Ứng dụng có thể gọi persist theo một thứ tự, nhưng JPA provider không bảo đảm SQL được gửi theo đúng thứ tự đó trong mọi trường hợp. Provider có thể sắp xếp action để tối ưu hoặc tuân theo dependency/constraint.

Nếu cần bảo đảm quan hệ parent-child, hãy khai báo mapping và owning side đúng, dùng cascade phù hợp và để provider quản lý thứ tự SQL theo mapping.

Không dùng `flush()` sau mỗi entity như một cách ép thứ tự insert nếu chưa xác định nguyên nhân. Việc flush quá thường xuyên có thể phá batching và tăng round-trip.

Nếu có dependency đặc biệt giữa các câu SQL, cân nhắc tách thao tác hoặc thiết kế mapping/transaction rõ ràng thay vì dựa vào thứ tự ngẫu nhiên.

## 17. Flush và JDBC batching

Hibernate và một số JPA provider có thể gom nhiều INSERT/UPDATE thành JDBC batch. Flush là thời điểm provider đồng bộ action queue và gửi các câu SQL; batching có thể diễn ra trong quá trình đó nếu cấu hình và loại SQL hỗ trợ.

Các yếu tố ảnh hưởng:

- JDBC batch size.
- ID generation strategy.
- Thứ tự insert/update.
- Entity có version hay không.
- Driver và database.
- Có gọi flush quá thường xuyên hay không.

Với Hibernate, có thể cấu hình các property như `hibernate.jdbc.batch_size` và `hibernate.order_inserts` theo workload. Hãy đo hiệu năng và kiểm tra SQL thực tế thay vì bật mọi tùy chọn.

Flush sau từng item thường làm giảm cơ hội gom nhiều câu lệnh thành batch. Trong chunk processing, flush ở cuối chunk thường là điểm bắt đầu hợp lý.

## 18. Flush và clear để giới hạn memory

Persistence context giữ reference tới entity managed để dirty checking. Nếu một Step xử lý hàng triệu entity và không clear, memory có thể tăng theo số entity được quản lý.

Một chiến lược trong custom writer là flush rồi clear theo nhóm:

~~~java
int batchSize = 100;

for (int i = 0; i < items.size(); i++) {
    entityManager.persist(items.get(i));

    if ((i + 1) % batchSize == 0) {
        entityManager.flush();
        entityManager.clear();
    }
}

entityManager.flush();
entityManager.clear();
~~~

Flush trước clear để SQL được gửi đi. `clear()` detach toàn bộ entity khỏi persistence context. Nếu clear trước flush, các thay đổi chưa đồng bộ có thể bị mất khỏi context.

Trong một chunk transaction, flush/clear nhiều lần không commit từng nhóm. Tất cả SQL vẫn thuộc transaction chunk nếu cùng EntityManager/transaction. Nếu lỗi trước commit, transaction có thể rollback toàn bộ chunk dù đã flush nhiều lần.

Tuy nhiên, sau clear, entity đã detach. Không tiếp tục thay đổi entity đó rồi kỳ vọng dirty checking ghi lại thay đổi nếu chưa merge/persist lại.

## 19. Clear không giống close EntityManager

`entityManager.clear()` xóa tất cả entity khỏi persistence context và chuyển chúng về detached state. Nó không đóng EntityManager và không commit transaction.

`entityManager.close()` kết thúc EntityManager. Với EntityManager do Spring quản lý trong transaction, ứng dụng không nên tự đóng.

Các thao tác này khác nhau:

| Thao tác | Tác động |
|---|---|
| flush() | Gửi thay đổi persistence context xuống database |
| clear() | Detach tất cả entity khỏi persistence context |
| detach(entity) | Detach một entity |
| refresh(entity) | Tải lại trạng thái từ database |
| close() | Đóng EntityManager do ứng dụng sở hữu |
| commit | Hoàn tất transaction |

Không gọi clear tùy tiện giữa quá trình processor còn cần các association managed. Clear có thể làm lazy relationship hoặc dirty checking hoạt động khác mong đợi.

## 20. Flush trước query cần nhìn thấy thay đổi

Với FlushModeType.AUTO, JPA provider có thể tự flush trước query nếu thay đổi pending có thể ảnh hưởng kết quả. Tuy nhiên, khi cần thứ tự rõ ràng, có thể gọi flush tường minh:

~~~java
entityManager.persist(new Order(...));
entityManager.flush();

Long count = entityManager.createQuery(
        "select count(o) from Order o",
        Long.class)
        .getSingleResult();
~~~

Query sau flush có thể nhìn thấy thay đổi trong cùng transaction theo transaction semantics và persistence context.

Nếu query chạy bằng JDBC trên một connection khác, visibility phụ thuộc transaction, connection và isolation. Không giả định mọi query qua mọi API đều thấy dữ liệu chưa commit.

Khi dùng JPQL bulk update/delete, cần chú ý chúng tác động trực tiếp lên database và không đồng bộ trạng thái của các entity đang managed. Thường cần flush pending changes trước bulk operation và clear/refresh sau đó để tránh persistence context giữ dữ liệu cũ.

## 21. Bulk JPQL update và flush

Ví dụ bulk update:

~~~java
entityManager.flush();

int updated = entityManager.createQuery("""
        update Order o
        set o.status = :status
        where o.businessDate = :businessDate
        """)
        .setParameter("status", OrderStatus.EXPIRED)
        .setParameter("businessDate", businessDate)
        .executeUpdate();

entityManager.clear();
~~~

Flush trước bulk update giúp các thay đổi đang pending được gửi trước câu bulk DML. Clear sau bulk update tránh tiếp tục dùng entity managed có trạng thái cũ.

Bulk JPQL update không gọi dirty checking cho từng entity và không thực hiện đầy đủ lifecycle callback/cascade như cập nhật entity thông thường. Nó cũng có thể bỏ qua optimistic locking version nếu query không tự cập nhật version.

Trong Spring Data JPA, `@Modifying(flushAutomatically = true, clearAutomatically = true)` có thể biểu diễn policy tương tự cho repository query, tùy phiên bản Spring Data.

## 22. Flush exception xuất hiện ở đâu?

Một số lỗi có thể xuất hiện khi persist/merge, một số khi flush và một số chỉ khi commit.

| Thời điểm | Ví dụ |
|---|---|
| Khi gọi persist/merge | Mapping hoặc lifecycle error, detached/removed state không hợp lệ |
| Khi flush | Unique/FK constraint, SQL error, optimistic locking conflict |
| Khi commit | Deferred constraint, transaction manager/database commit failure |
| Sau commit | Lỗi từ hệ thống ngoài hoặc bước publish tiếp theo |

Không phải tất cả exception đều được ném ngay tại dòng persist. JPA thường trì hoãn SQL cho tới flush hoặc commit.

Nếu writer không flush tường minh, lỗi có thể xuất hiện trong bước commit transaction của chunk. Khi đó stack trace có thể trỏ tới transaction manager thay vì dòng code trong writer.

JpaItemWriter chuẩn thường flush trong write(), giúp nhiều lỗi SQL xuất hiện trong phạm vi writer invocation. Nhưng lỗi commit-level vẫn có thể xảy ra sau đó.

## 23. Xử lý lỗi flush trong Spring Batch

Khi flush ném exception, Step xử lý nó theo transaction và fault-tolerance configuration.

Các lựa chọn:

- Fail Step nếu lỗi dữ liệu không thể phục hồi.
- Retry lỗi tạm thời có thể thử lại an toàn.
- Skip record lỗi nếu lỗi có thể gắn với item cụ thể và nghiệp vụ cho phép.
- Ghi rejected record hoặc audit bằng cơ chế có tính nhất quán.

Ví dụ retry lỗi deadlock:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .writer(writer)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

Tên exception và cách Spring dịch lỗi phụ thuộc version/framework. Cần quan sát exception thực tế trong ứng dụng.

Unique constraint violation thường không nên retry nếu dữ liệu không đổi. Optimistic locking conflict cần đọc lại state và áp dụng logic mới, không chỉ lặp lại thao tác cũ.

## 24. Flush và write skip

Nếu một item gây lỗi constraint trong lúc flush cả chunk, Spring Batch có thể cần xác định item lỗi thông qua cơ chế fault-tolerant write/scan. Hành vi phụ thuộc writer, exception type và khả năng rollback/transaction của hệ thống.

Không phải mọi lỗi flush đều có thể quy về một item duy nhất. Ví dụ lỗi deadlock có thể liên quan tới nhiều transaction; lỗi kết nối có thể ảnh hưởng cả chunk; constraint cross-row có thể phát sinh do tương tác giữa nhiều item.

Chỉ cấu hình skip cho exception đã hiểu rõ và có thể xác định item lỗi. Nếu không, skip có thể che giấu lỗi toàn chunk hoặc tạo kết quả thiếu nhất quán.

Với custom writer, test rõ trường hợp flush fail giữa chunk, rollback và writer được gọi lại với subset nếu framework thực hiện write scanning.

## 25. Retry sau flush và idempotency

Giả sử writer flush thành công, nhưng lỗi xảy ra trước commit. Transaction chunk rollback và Spring Batch retry chunk.

Các SQL đã flush trong transaction bị rollback nếu chúng thuộc cùng transaction. Khi retry, writer sẽ thực hiện lại các thao tác. Đây là behavior bình thường.

Nếu writer còn tạo side effect ngoài transaction, ví dụ gửi HTTP request trước khi commit, side effect đó không tự rollback. Retry có thể gửi request trùng.

Với side effect ngoài database:

- Dùng idempotency key ổn định theo business operation.
- Dùng transactional outbox để chỉ publish sau commit.
- Tránh gửi notification trực tiếp trong JPA writer.
- Có cơ chế deduplicate hoặc reconcile ở hệ thống đích.

Flush thành công không phải thời điểm an toàn để publish event không thể đảo ngược. Hãy chờ transaction commit hoặc dùng outbox.

## 26. Flush và database lock

Khi SQL được thực thi tại flush, database có thể lấy row/table lock. Các lock này thường được giữ cho tới commit hoặc rollback tùy database và isolation level.

Nếu flush sớm rồi tiếp tục xử lý lâu trước khi commit, transaction có thể giữ lock lâu hơn. Điều này làm tăng contention, deadlock hoặc ảnh hưởng transaction khác.

Một số cách giảm rủi ro:

- Giữ chunk size phù hợp.
- Không gọi API chậm giữa flush và commit.
- Tránh query/update không cần thiết trong transaction.
- Dùng index phù hợp cho predicate.
- Giữ thứ tự truy cập row nhất quán giữa các Job.
- Không giữ transaction mở khi chờ người dùng hoặc hệ thống ngoài.

Flush không giải phóng lock. Commit hoặc rollback mới kết thúc transaction và giải phóng lock theo semantics database.

## 27. Flush và transaction propagation

Một service được gọi từ writer có thể dùng `@Transactional` với propagation khác nhau.

- REQUIRED thường tham gia transaction chunk hiện tại nếu transaction manager và resource giống nhau.
- REQUIRES_NEW tạm suspend transaction ngoài và chạy transaction mới.
- NOT_SUPPORTED có thể chạy ngoài transaction.

Nếu service dùng REQUIRES_NEW và commit thành công, thay đổi của service có thể tồn tại ngay cả khi chunk transaction rollback sau đó.

Không đặt REQUIRES_NEW cho thao tác JPA chỉ để ép flush. Flush chỉ đồng bộ persistence context hiện tại; transaction manager quyết định commit/rollback.

Nếu cần một thao tác audit phải rollback cùng chunk, hãy dùng REQUIRED và cùng persistence unit/transaction manager. Nếu audit phải tồn tại độc lập, hãy mô hình hóa rõ semantics và khả năng đối soát.

## 28. Flush và nhiều EntityManagerFactory

Ứng dụng có thể có nhiều persistence unit hoặc database. Một JpaTransactionManager chỉ quản lý EntityManagerFactory tương ứng của nó.

Nếu writer A dùng EntityManagerFactory 1 còn writer B dùng EntityManagerFactory 2, flush của A không đồng nghĩa thay đổi của B được flush hoặc commit cùng transaction.

Ngay cả khi hai persistence unit trỏ tới cùng database, transaction coordination không tự động xảy ra. Muốn atomic qua nhiều resource cần transaction manager hỗ trợ phù hợp, chẳng hạn JTA/XA trong môi trường có yêu cầu và hỗ trợ tương ứng, hoặc thiết kế workflow/outbox/saga.

Không gọi một flush trên EntityManager để kết luận mọi JPA writer trong Job đã đồng bộ.

## 29. Spring Data JPA save, saveAndFlush và flush

Spring Data JPA repository có các phương thức:

- `save(entity)`: lưu hoặc merge entity; không nhất thiết flush ngay.
- `saveAll(entities)`: lưu tập entity; không nhất thiết flush ngay.
- `flush()`: đồng bộ thay đổi pending trong persistence context.
- `saveAndFlush(entity)`: save rồi flush.
- `saveAllAndFlush(entities)`: save tập entity rồi flush.

`saveAndFlush` vẫn không commit transaction. Nếu được gọi trong transaction chunk, transaction đó tiếp tục mở sau khi method trả về.

Ví dụ:

~~~java
repository.save(order);
repository.flush();

// SQL đã được gửi; transaction của Step vẫn có thể rollback.
~~~

Không dùng saveAndFlush cho từng item chỉ để "chắc chắn đã lưu". Nó có thể làm giảm batching và tăng số lần đồng bộ. Trong chunk writer, thường nên gom item và flush một lần theo ranh giới chunk nếu semantics cho phép.

## 30. Flush và transaction commit trong Spring Batch JPA

Một cấu hình thông thường:

~~~java
@Bean
public Step importStep(
        JobRepository jobRepository,
        JpaTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        JpaItemWriter<Order> writer) {

    return new StepBuilder("importStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Luồng chính:

1. Spring Batch bắt đầu transaction cho chunk.
2. Reader cung cấp item.
3. Processor chuyển input thành entity.
4. JpaItemWriter persist/merge entity.
5. Writer flush persistence context.
6. Spring Batch hoàn tất các cập nhật stream/checkpoint cần thiết.
7. Transaction manager commit chunk.

Nếu flush thất bại, chunk transaction rollback theo policy. Nếu commit thất bại, transaction cũng không được xem là hoàn tất; JobRepository và transaction coordination cần xử lý theo cấu hình Spring Batch.

Không gọi `entityManager.getTransaction().commit()` trong processor/writer. Điều đó phá vỡ quyền kiểm soát transaction của Step.

## 31. Generated columns và refresh sau flush

Một số database tạo giá trị mặc định hoặc generated column khi INSERT/UPDATE. Flush gửi SQL nhưng không bảo đảm provider tự đưa mọi giá trị generated vào entity trong mọi mapping.

Ví dụ cột created_at được database gán default:

~~~sql
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
~~~

Nếu ứng dụng cần đọc giá trị này ngay sau insert, có thể cần mapping generated property phù hợp hoặc gọi refresh:

~~~java
entityManager.persist(order);
entityManager.flush();
entityManager.refresh(order);
~~~

Refresh thực hiện SELECT để đồng bộ state từ database. Không dùng refresh cho từng entity nếu không cần, vì nó tạo thêm round-trip và có thể làm giảm throughput.

Với generated ID, timestamp hoặc computed column, kiểm tra provider/database và annotation mapping để biết giá trị nào có sẵn sau persist, flush hoặc refresh.

## 32. Flush và lifecycle callbacks

Một số JPA lifecycle callback liên quan đến persist/update/remove có thể chạy quanh thời điểm provider thực hiện thao tác SQL. Ví dụ @PrePersist và @PreUpdate thường được gọi trước khi entity được ghi; @PostPersist và @PostUpdate được gọi sau thao tác tương ứng theo lifecycle semantics.

Không dùng callback như cơ chế commit hook cho side effect ngoài database. Callback xảy ra trong lifecycle persistence, transaction vẫn có thể rollback sau đó.

Nếu cần gửi event sau commit, dùng transaction synchronization hoặc outbox phù hợp. Không gửi email hoặc gọi API từ @PostPersist với giả định dữ liệu chắc chắn đã commit.

## 33. Flush và bulk insert/update performance

Với dữ liệu lớn, hiệu năng phụ thuộc nhiều yếu tố:

- Số entity mỗi chunk.
- Số lượng SQL cần thực thi.
- JDBC batch size.
- Persistence context size.
- Dirty checking cost.
- Cascade graph.
- Index và constraint.
- Round-trip giữa ứng dụng và database.

Một số nguyên tắc:

- Bắt đầu với chunk size vừa phải.
- Dùng JDBC batching nếu provider/driver hỗ trợ.
- Flush theo chunk thay vì từng item.
- Clear sau flush khi không cần giữ entity managed.
- Tránh cascade graph quá lớn.
- Dùng projection hoặc JDBC writer nếu không cần JPA lifecycle.
- Đo heap, SQL count và transaction duration.

JPA thuận tiện cho mapping và domain lifecycle, nhưng với bulk ETL rất lớn, JdbcBatchItemWriter hoặc SQL bulk load có thể hiệu quả hơn. Chọn theo nhu cầu nghiệp vụ chứ không dùng JPA cho mọi trường hợp.

## 34. Kiểm thử flush trước commit

Một test nên chứng minh rằng flush gửi SQL nhưng transaction chưa commit.

Có thể dùng TransactionTemplate trong integration test:

~~~java
transactionTemplate.executeWithoutResult(status -> {
    entityManager.persist(new Order(1001L, OrderStatus.NEW));

    entityManager.flush();

    // Cùng transaction có thể đọc thay đổi đã flush.
    Order found = entityManager.find(Order.class, 1001L);
    assertNotNull(found);

    status.setRollbackOnly();
});

// Transaction đã rollback; truy vấn trong transaction mới
// phải xác nhận row không còn.
~~~

Test này cần transaction manager và EntityManagerFactory thực tế được cấu hình đúng. Khi kiểm tra từ cùng persistence context, entity có thể được trả từ first-level cache; nếu cần chứng minh database state, hãy clear context hoặc query bằng transaction/connection mới phù hợp.

Điểm cần xác nhận: sau flush, transaction vẫn có thể rollback và dữ liệu không còn sau rollback.

## 35. Kiểm thử lỗi constraint tại flush

Tạo một unique constraint trong test database, sau đó persist hai entity trùng business key:

~~~java
entityManager.persist(new Order("EXT-100"));
entityManager.persist(new Order("EXT-100"));

assertThrows(
        PersistenceException.class,
        entityManager::flush);
~~~

Exception cụ thể có thể được Hibernate hoặc provider bọc theo kiểu khác. Trong Spring, exception translation có thể chuyển thành DataIntegrityViolationException.

Sau lỗi flush, transaction thường đã ở trạng thái rollback-only hoặc không thể tiếp tục bình thường. Không bắt exception rồi tiếp tục dùng cùng transaction như thể không có gì xảy ra.

Integration test cần kiểm tra chunk rollback và trạng thái Step, không chỉ xác nhận một exception được ném từ EntityManager.

## 36. Kiểm thử JpaItemWriter trong chunk

Nên chạy một Step test với JpaItemWriter:

- Ghi một chunk hợp lệ.
- Xác nhận writer flush các entity trong transaction.
- Cố ý tạo constraint violation ở một chunk.
- Xác nhận chunk lỗi không commit dữ liệu.
- Restart Job nếu lỗi được xử lý theo restart policy.
- Xác nhận item đã commit không bị ghi trùng.
- Xác nhận persistence context không tích lũy entity ngoài dự kiến.

Không chỉ mock EntityManager và xác nhận phương thức flush được gọi. Mock không chứng minh SQL, constraint hoặc transaction rollback thực sự hoạt động.

## 37. Những lỗi thường gặp

### Nhầm flush với commit

Flush chỉ đồng bộ SQL trong transaction. Transaction vẫn có thể rollback. Chỉ xem dữ liệu là hoàn tất sau commit thành công.

### Gọi flush sau từng item

Có thể phá JDBC batching và tăng round-trip. Thường flush theo chunk hoặc theo nhóm có chủ đích.

### Clear trước flush

Các thay đổi pending có thể bị detach mà chưa được đồng bộ. Flush trước clear.

### Tự commit EntityManager trong writer

Làm mất quyền kiểm soát transaction của Spring Batch. Để transaction manager quản lý commit/rollback.

### Dùng EntityManagerFactory khác transaction manager

Writer có thể không tham gia transaction chunk. Dùng đúng persistence unit và JpaTransactionManager.

### Dùng merge rồi tiếp tục sửa object đầu vào

Object truyền vào merge có thể vẫn detached. Sử dụng instance managed được merge trả về nếu cần sửa tiếp.

### Cho rằng mọi constraint được kiểm tra tại flush

Deferred constraint có thể chỉ fail lúc commit. Test với database thật và hiểu constraint semantics.

### Cho rằng generated ID chỉ xuất hiện sau flush

ID strategy như IDENTITY có thể yêu cầu INSERT sớm. Kiểm tra provider/database.

### Bắt lỗi flush rồi tiếp tục transaction

Transaction có thể đã rollback-only hoặc không còn an toàn để dùng. Truyền lỗi cho Spring Batch theo policy.

### Gửi event ngoài database sau flush

Flush chưa commit; transaction có thể rollback. Dùng outbox hoặc publish sau commit.

### Đổi flush mode tùy tiện

AUTO và COMMIT có semantics khác nhau đối với query. Chọn mode theo yêu cầu và kiểm thử.

### Không kiểm soát persistence context size

Entity managed tích lũy có thể tăng heap và dirty checking cost. Dùng flush/clear theo chiến lược phù hợp.

## 38. Quy trình thiết kế flush trong JPA writer

Trước khi cấu hình writer, hãy xác định:

1. Entity được persist hay merge?
2. Entity có managed hay detached khi đến writer?
3. JpaItemWriter đã tự flush trong version đang dùng chưa?
4. Transaction manager của Step có dùng đúng EntityManagerFactory không?
5. Flush mode AUTO hay COMMIT có phù hợp với query trong Step không?
6. Constraint và optimistic locking có thể fail tại flush hay commit?
7. Chunk size và JDBC batch size có phù hợp không?
8. Persistence context có cần clear sau flush không?
9. Có bulk JPQL operation cần flush/clear trước và sau không?
10. Có generated field cần refresh không?
11. Writer có gọi service REQUIRES_NEW hoặc tự commit không?
12. Side effect ngoài database có chờ commit hoặc dùng outbox không?
13. Test có chứng minh rollback sau flush và lỗi constraint không?
14. Restart có giữ input, reader state và writer behavior nhất quán không?

Flush trước commit giúp JPA đồng bộ thay đổi và phát hiện nhiều lỗi SQL trong phạm vi xử lý chunk. Nhưng flush không kết thúc transaction, không bảo đảm durability và không giải phóng lock. Trong Spring Batch, hãy để JpaItemWriter hoặc custom writer flush trong transaction do Step quản lý, chọn persist/merge đúng trạng thái entity, giới hạn persistence context bằng flush/clear khi cần và kiểm thử cả lỗi tại flush lẫn lỗi tại commit. Chỉ sau khi transaction commit thành công mới xem chunk là đã hoàn tất.
