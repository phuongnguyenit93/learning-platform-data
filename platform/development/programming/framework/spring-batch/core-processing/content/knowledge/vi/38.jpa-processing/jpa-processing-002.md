# EntityManager và persistence context

Trong Spring Batch, khi đọc hoặc ghi dữ liệu bằng JPA, EntityManager là API làm việc với entity còn persistence context là vùng quản lý các entity đang được theo dõi. Persistence context giữ identity của entity, phát hiện thay đổi để ghi xuống database, điều phối trạng thái entity và áp dụng các thao tác persist, merge, remove, flush hoặc clear.

Hiểu đúng vòng đời của EntityManager và persistence context rất quan trọng khi chạy batch. Một Step thường xử lý hàng nghìn hoặc hàng triệu item theo từng chunk. Nếu persistence context giữ quá nhiều entity, bộ nhớ có thể tăng liên tục. Nếu context bị clear quá sớm, entity trở thành detached và lazy association có thể không còn truy cập được. Nếu dùng nhầm merge hoặc nghĩ flush đồng nghĩa với commit, dữ liệu có thể không như mong đợi.

Trong JPA processing, cần nắm:

- EntityManager và persistence context khác nhau thế nào.
- Entity đi qua các trạng thái new, managed, detached và removed ra sao.
- Dirty checking và first-level cache hoạt động thế nào.
- Transaction của chunk liên hệ với persistence context như thế nào.
- Khi nào dùng persist, merge, flush, clear, detach và refresh.
- Cách Spring Batch JPA reader/writer quản lý EntityManager.
- Cách kiểm soát bộ nhớ, lazy loading, batching, restart và concurrency.

## 1. EntityManager và persistence context

EntityManager là interface chính của Jakarta Persistence (JPA). Nó cung cấp các thao tác để tạo, tìm, theo dõi, cập nhật và xóa entity.

Persistence context là tập hợp các entity instance được EntityManager quản lý. Trong một persistence context, một entity identity (entity type và primary key) được đại diện bởi một managed object tương ứng. JPA dùng context này để theo dõi thay đổi và đồng bộ dữ liệu với database.

Có thể hình dung:

~~~text
Application / Spring Batch component
             |
             v
        EntityManager
             |
             v
      Persistence Context
       /       |       \
      v        v        v
   Order    Customer  OrderLine
      \        |        /
       \       |       /
        v      v      v
          Database
~~~

EntityManager cung cấp API; persistence context là vùng trạng thái mà API đó quản lý. Nhiều EntityManager có thể được tạo từ cùng EntityManagerFactory, nhưng mỗi EntityManager có persistence context riêng.

### EntityManagerFactory và EntityManager

Hai đối tượng này có vòng đời khác nhau:

| Thành phần | Vai trò | Vòng đời điển hình |
| --- | --- | --- |
| EntityManagerFactory | Tạo EntityManager và quản lý cấu hình persistence unit | Thường sống suốt vòng đời ứng dụng |
| EntityManager | Làm việc với entity và persistence context | Thường gắn với transaction hoặc một đơn vị công việc |
| Persistence context | Theo dõi các entity managed và thay đổi của chúng | Thường tồn tại cùng EntityManager/transaction-scoped context |

EntityManagerFactory được thiết kế để chia sẻ giữa các thread. Một EntityManager cụ thể không thread-safe và không được dùng đồng thời từ nhiều thread.

Trong Spring, ứng dụng thường inject EntityManager thông qua @PersistenceContext hoặc shared EntityManager proxy. Proxy này tìm EntityManager gắn với transaction hiện tại. Không nên tự tạo một EntityManager singleton rồi chia sẻ cho nhiều worker.

## 2. Persistence context là first-level cache

Persistence context hoạt động như first-level cache của JPA. Nếu một entity đã được load vào context, truy vấn lại cùng identity trong context thường trả về cùng managed instance thay vì tạo một object Java độc lập khác.

Ví dụ:

~~~java
Order first = entityManager.find(Order.class, 1001L);
Order second = entityManager.find(Order.class, 1001L);

assert first == second;
~~~

Trong cùng persistence context, hai biến thường tham chiếu cùng một object instance cho cùng entity identity.

Lợi ích:

- Tránh nhiều object đại diện cho cùng một entity trong cùng context.
- Giảm một số lần truy vấn database khi entity đã được quản lý.
- Cho phép dirty checking vì JPA biết entity nào đang được theo dõi.
- Duy trì consistency giữa các association trong context.

First-level cache không phải cache dùng chung toàn ứng dụng. Khi EntityManager đóng hoặc persistence context bị clear, entity không còn được quản lý trong context đó.

### Cùng identity không có nghĩa dữ liệu luôn mới nhất

Nếu entity đã được load rồi một transaction khác cập nhật database, managed entity hiện tại có thể vẫn giữ trạng thái đã đọc trước đó. Persistence context không tự động refresh mọi entity mỗi khi database thay đổi.

Khi cần đọc lại dữ liệu hiện tại, có thể dùng refresh() hoặc clear context rồi load lại. Cần cân nhắc vì refresh có thể ghi đè thay đổi chưa flush trong object.

## 3. Bốn trạng thái vòng đời của entity

Một entity JPA thường ở một trong bốn trạng thái:

| Trạng thái | Ý nghĩa | Có được persistence context theo dõi? |
| --- | --- | --- |
| New / transient | Object vừa được tạo, chưa được persist | Không |
| Managed / persistent | Entity đang được quản lý bởi context | Có |
| Detached | Entity từng managed nhưng không còn được context quản lý | Không |
| Removed | Entity được đánh dấu xóa trong context | Có cho đến khi remove được đồng bộ/commit |

Ví dụ vòng đời:

~~~text
new Order()
    |
    | persist()
    v
Managed entity
    |
    | clear(), detach() hoặc close()
    v
Detached entity
    |
    | merge()
    v
Một managed instance được trả về
~~~

Entity có thể chuyển sang removed khi gọi remove() trên managed instance. Khi transaction commit, lệnh DELETE tương ứng được thực thi nếu không bị rollback.

### New entity

~~~java
Order order = new Order();
order.setOrderId(1001L);
order.setStatus(OrderStatus.NEW);
~~~

Object mới chưa được EntityManager theo dõi. Thay đổi field trên object không tự tạo SQL.

### Managed entity

~~~java
Order order = entityManager.find(Order.class, 1001L);
order.setStatus(OrderStatus.PROCESSED);
~~~

Entity được find trong context hiện tại là managed. JPA có thể phát hiện thay đổi và tạo UPDATE khi flush.

### Detached entity

~~~java
entityManager.clear();
order.setStatus(OrderStatus.PROCESSED);
~~~

Sau clear(), entity trước đó bị detach. Thay đổi tiếp theo trên object không được persistence context cũ theo dõi.

### Removed entity

~~~java
Order order = entityManager.find(Order.class, 1001L);
entityManager.remove(order);
~~~

Entity được đánh dấu removed. SQL DELETE thường được đồng bộ khi flush hoặc commit.

## 4. persist() và merge()

Hai thao tác này thường bị nhầm lẫn.

### persist() cho entity mới

persist() đưa một entity mới vào persistence context:

~~~java
Order order = new Order();
order.setOrderId(1001L);
order.setStatus(OrderStatus.NEW);

entityManager.persist(order);
~~~

Sau lời gọi, object order trở thành managed trong context hiện tại. INSERT có thể được gửi ngay hoặc trì hoãn đến flush/commit tùy chiến lược ID và provider.

Không dùng persist() như cách cập nhật một entity detached. Trường hợp đó có thể dẫn đến lỗi entity detached hoặc vi phạm khóa duy nhất.

### merge() cho entity detached hoặc state cần đồng bộ

merge() sao chép state của object truyền vào sang một managed instance:

~~~java
Order detachedOrder = loadOrderFromPreviousStep();

Order managedOrder = entityManager.merge(detachedOrder);
managedOrder.setStatus(OrderStatus.PROCESSED);
~~~

Điểm rất quan trọng: merge() trả về managed instance. Object truyền vào không tự trở thành managed. Vì vậy, nếu cần tiếp tục thay đổi entity sau merge, hãy dùng object được trả về.

Không nên viết:

~~~java
entityManager.merge(detachedOrder);
detachedOrder.setStatus(OrderStatus.PROCESSED);
~~~

Thay đổi trên detachedOrder sau merge không được đảm bảo theo dõi bởi persistence context.

### Khi nào chọn persist hay merge?

| Tình huống | Thao tác thường phù hợp |
| --- | --- |
| Tạo entity mới | persist() |
| Cập nhật entity đang managed | Thay đổi trực tiếp; dirty checking sẽ phát hiện |
| Đồng bộ state từ entity detached | merge() và dùng object trả về |
| Xóa entity managed | remove() |
| Xóa entity detached | Tải entity managed hoặc merge rồi remove theo quy tắc phù hợp |

Không gọi merge cho mọi entity một cách máy móc. Merge có thể phải đọc state và sao chép graph association, tạo thêm truy vấn và làm tăng chi phí.

## 5. Dirty checking

Dirty checking là cơ chế JPA so sánh trạng thái managed entity với snapshot ban đầu để phát hiện thay đổi cần ghi.

Ví dụ:

~~~java
@Transactional
public void markProcessed(long orderId) {
    Order order = entityManager.find(Order.class, orderId);
    order.setStatus(OrderStatus.PROCESSED);
}
~~~

Không cần gọi save() hoặc update() sau khi thay đổi managed entity. Khi transaction flush, JPA phát hiện field đã đổi và tạo câu lệnh UPDATE.

Luồng khái quát:

~~~text
find(Order.class, id)
       |
       v
Entity managed + snapshot
       |
       v
Java code thay đổi status
       |
       v
Dirty checking phát hiện khác biệt
       |
       v
flush()
       |
       v
SQL UPDATE
~~~

Dirty checking chỉ áp dụng cho entity còn managed. Nếu entity đã detached, thay đổi trên object không tự được ghi.

### Dirty checking và batch

Trong một chunk có nhiều entity, persistence context có thể giữ snapshot của tất cả entity được load hoặc persist. Khi số lượng tăng, chi phí bộ nhớ và dirty checking cũng tăng.

Vì vậy, batch thường cần giới hạn số entity managed cùng lúc bằng chunk size, page size và flush/clear strategy phù hợp.

## 6. flush() không phải commit()

flush() đồng bộ các thay đổi đang chờ trong persistence context xuống database bằng SQL. Nó không kết thúc transaction.

~~~java
order.setStatus(OrderStatus.PROCESSED);
entityManager.flush();

// SQL UPDATE đã được gửi trong transaction,
// nhưng transaction vẫn có thể rollback.
~~~

Transaction commit mới xác nhận thay đổi là bền vững theo transaction semantics của database. Nếu transaction rollback sau flush, các câu lệnh đã thực thi trong transaction vẫn có thể bị rollback.

| Thao tác | Ý nghĩa |
| --- | --- |
| flush() | Đồng bộ thay đổi pending thành SQL trong transaction hiện tại |
| commit() | Hoàn tất transaction |
| clear() | Detach toàn bộ entity khỏi persistence context |
| close() | Đóng EntityManager và persistence context |

Flush có thể làm xuất hiện lỗi constraint, optimistic locking hoặc SQL error sớm hơn thời điểm commit. Đây là lý do nên kiểm tra lỗi tại flush khi cần biết chính xác chunk nào gây lỗi.

Không gọi commit() trực tiếp trên EntityManager được Spring quản lý. Transaction manager của Spring Batch phải điều khiển commit/rollback ở ranh giới chunk.

## 7. clear(), detach() và refresh()

Các API này tác động đến trạng thái entity theo cách khác nhau.

### clear()

clear() detach tất cả entity trong persistence context:

~~~java
entityManager.flush();
entityManager.clear();
~~~

Thường dùng sau khi flush trong batch để giải phóng tham chiếu và giảm bộ nhớ. Sau clear, các entity trước đó không còn managed.

### detach()

detach(entity) chỉ detach một entity:

~~~java
entityManager.detach(order);
~~~

Các entity khác vẫn được quản lý. Có thể dùng khi muốn ngừng theo dõi một object cụ thể, nhưng cần chú ý cascade detach nếu mapping có cấu hình phù hợp.

### refresh()

refresh(entity) tải lại state từ database và ghi đè các thay đổi chưa đồng bộ trên managed entity:

~~~java
entityManager.refresh(order);
~~~

Chỉ dùng refresh khi muốn bỏ state trong bộ nhớ và lấy state hiện tại từ database. Không gọi tùy tiện sau khi đã sửa entity vì thay đổi chưa flush có thể bị mất.

### flush trước clear

Trong batch, thứ tự thường là:

~~~java
entityManager.flush();
entityManager.clear();
~~~

Nếu clear trước khi flush, các thay đổi pending có thể bị bỏ khỏi persistence context và không được ghi. Không dùng clear như một cách commit; transaction vẫn đang hoạt động.

## 8. Transaction-scoped persistence context

Trong ứng dụng Spring thông thường, persistence context được gắn với transaction. JpaTransactionManager quản lý transaction cho một EntityManagerFactory và bind EntityManager tương ứng vào thread hiện tại.

Khi Spring Batch chạy chunk Step với JPA transaction manager:

~~~java
@Bean
public PlatformTransactionManager transactionManager(
        EntityManagerFactory entityManagerFactory) {

    return new JpaTransactionManager(entityManagerFactory);
}
~~~

Step:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
~~~

Mỗi chunk có một transaction theo cấu hình Step. Các thao tác JPA tham gia transaction đó nếu chúng dùng đúng EntityManagerFactory và transaction manager.

Với transaction-scoped persistence context, EntityManager/persistence context gắn với transaction được mở và kết thúc theo lifecycle của transaction. Vì chunk commit sau mỗi nhóm item, không nên giả định một persistence context duy nhất sẽ giữ tất cả entity từ đầu đến cuối Job.

### Extended persistence context

JPA cũng có khái niệm extended persistence context, tồn tại lâu hơn một transaction. Kiểu này thường không cần cho Spring Batch chunk processing và có thể giữ quá nhiều entity trong bộ nhớ nếu kéo dài qua nhiều chunk.

Với batch, transaction-scoped context và việc flush/clear có kiểm soát thường dễ quản lý hơn. Không giữ một EntityManager extended dùng chung cho toàn Job nếu không có lý do kiến trúc rõ ràng.

## 9. EntityManager trong Spring với @PersistenceContext

Có thể inject EntityManager vào repository hoặc custom writer:

~~~java
@Component
public class OrderJpaWriter implements ItemWriter<Order> {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            entityManager.merge(order);
        }
        entityManager.flush();
    }
}
~~~

Trong Spring, EntityManager được inject thường là shared proxy. Proxy tìm EntityManager đang gắn với transaction hiện tại. Điều này cho phép component singleton dùng API EntityManager mà không chia sẻ một EntityManager vật lý duy nhất giữa mọi thread.

Không tự tạo EntityManager trong mỗi method rồi quên đóng. Nếu thực sự tự tạo qua EntityManagerFactory, code phải chịu trách nhiệm quản lý open/close và transaction đúng cách.

### Không chia sẻ EntityManager vật lý giữa worker

EntityManager không thread-safe. Không lưu EntityManager được tạo thủ công trong static field hoặc singleton rồi để nhiều worker gọi đồng thời.

Nếu Step chạy multi-thread hoặc partitioned:

- Mỗi transaction/worker cần EntityManager phù hợp với thread và transaction của nó.
- Dùng Spring shared EntityManager proxy hoặc repository được cấu hình đúng.
- Không truyền EntityManager vật lý sang thread khác.
- Không giữ managed entity rồi sử dụng đồng thời ở nhiều worker.

## 10. JpaPagingItemReader và persistence context

Spring Batch cung cấp JpaPagingItemReader để đọc dữ liệu JPA theo từng trang. Reader nhận EntityManagerFactory và JPQL query:

~~~java
@Bean
@StepScope
public JpaPagingItemReader<Order> orderReader(
        EntityManagerFactory entityManagerFactory) {

    return new JpaPagingItemReaderBuilder<Order>()
            .name("orderReader")
            .entityManagerFactory(entityManagerFactory)
            .queryString("""
                    select o
                    from Order o
                    where o.status = :status
                    order by o.id
                    """)
            .parameterValues(Map.of(
                    "status", OrderStatus.READY))
            .pageSize(500)
            .saveState(true)
            .build();
}
~~~

Reader lấy các trang kết quả, mỗi trang tối đa theo pageSize. Việc đọc theo trang giúp tránh phải giữ toàn bộ result set trong một collection lớn.

### Entity trả về có thể detached

JpaPagingItemReader quản lý EntityManager của chính reader và có lifecycle riêng. Reader thực hiện truy vấn trang rồi clear persistence context sau khi đọc trang theo hành vi của implementation. Vì vậy, entity trả về cho processor thường là detached.

Hệ quả:

- Processor có thể đọc các field đã được load.
- Thay đổi entity detached không tự được dirty checking bởi persistence context của reader.
- Lazy association có thể không còn truy cập được sau khi context bị clear.
- Nếu cần ghi thay đổi, writer cần merge entity hoặc tải lại managed entity trong transaction ghi.

Không giả định entity được reader trả về vẫn managed trong EntityManager mà writer đang dùng. Reader và writer có thể quản lý EntityManager khác nhau.

### Reader transaction và chunk transaction

JpaPagingItemReader có thể thực hiện truy vấn trang trong transaction riêng theo thiết kế của reader; transaction đó không nhất thiết là transaction của chunk đang ghi. Hành vi chi tiết phụ thuộc phiên bản Spring Batch và cấu hình reader.

Do đó, không dùng việc entity được đọc thành công để suy ra reader và writer đang chia sẻ cùng persistence context. Nếu nghiệp vụ yêu cầu đọc và cập nhật trong một persistence context/transaction cụ thể, cần thiết kế và kiểm thử rõ ràng thay vì dựa vào mặc định của reader.

### Sort key ổn định

Paging cần thứ tự xác định:

~~~sql
order by o.id
~~~

Sort key nên duy nhất hoặc tổ hợp sort key phải tạo thứ tự toàn phần. Nếu truy vấn không có thứ tự ổn định, các trang có thể lặp hoặc bỏ sót item khi dữ liệu thay đổi.

Nếu writer cập nhật điều kiện lọc của chính query đang phân trang, tập kết quả có thể thay đổi giữa các trang. Cân nhắc batch ID, watermark hoặc staging table để cố định tập input.

## 11. JpaItemWriter và entity detached

JpaItemWriter là writer chuẩn để ghi entity bằng JPA:

~~~java
@Bean
public JpaItemWriter<Order> orderWriter(
        EntityManagerFactory entityManagerFactory) {

    return new JpaItemWriterBuilder<Order>()
            .entityManagerFactory(entityManagerFactory)
            .build();
}
~~~

Writer sử dụng EntityManager gắn với transaction nếu có, sau đó persist hoặc merge item theo cấu hình. Mặc định của nhiều phiên bản là merge; builder có tùy chọn usePersist để chọn persist khi ghi entity mới.

Vì JpaPagingItemReader thường trả entity detached, merge là một lựa chọn phổ biến khi cập nhật entity đã được đọc. Với entity mới, persist thường phù hợp hơn. Hãy kiểm tra cấu hình và API version của Spring Batch đang dùng.

### merge trả về managed entity

Nếu viết custom writer:

~~~java
for (Order detachedOrder : chunk) {
    Order managedOrder = entityManager.merge(detachedOrder);
    managedOrder.setStatus(OrderStatus.PROCESSED);
}

entityManager.flush();
~~~

Hãy tiếp tục dùng managedOrder sau merge. Đừng giả định detachedOrder đã được attach.

### persist cho entity mới

~~~java
for (Order newOrder : chunk) {
    entityManager.persist(newOrder);
}

entityManager.flush();
~~~

Không dùng persist cho entity detached chỉ để tránh chi phí merge. Nếu ID đã tồn tại, có thể gặp lỗi duplicate key hoặc detached entity.

## 12. JpaItemWriter và clear persistence context

JpaItemWriter có tùy chọn quản lý việc clear persistence context sau khi ghi; ở các phiên bản Spring Batch hiện đại, writer thường flush và có thể clear context sau write theo cấu hình mặc định của implementation.

Lợi ích của clear sau write:

- Không giữ toàn bộ entity của các chunk trước trong context.
- Giảm bộ nhớ cho Job xử lý nhiều item.
- Hạn chế dirty checking trên entity không còn cần thiết.

Nhưng clear cũng detach mọi entity đang được quản lý trong context đó. Nếu custom code dựa vào việc entity vẫn managed sau khi writer chạy, cần kiểm tra hành vi này.

Không giả định JpaItemWriter chỉ clear những item vừa ghi. EntityManager.clear() tác động đến toàn bộ persistence context. Hãy xem tài liệu của version Spring Batch đang dùng và tránh giữ managed entity cần tiếp tục thao tác sau write.

## 13. Flush và clear theo batch size

Với custom writer, có thể chủ động flush và clear sau một số item:

~~~java
public class ChunkedJpaWriter implements ItemWriter<Order> {

    @PersistenceContext
    private EntityManager entityManager;

    private final int flushInterval = 50;

    @Override
    public void write(Chunk<? extends Order> chunk) {
        int count = 0;

        for (Order order : chunk) {
            entityManager.persist(order);
            count++;

            if (count % flushInterval == 0) {
                entityManager.flush();
                entityManager.clear();
            }
        }

        entityManager.flush();
        entityManager.clear();
    }
}
~~~

Đây là mẫu minh họa cho writer tạo entity mới. Nếu entity cần được dùng tiếp sau clear, hãy giữ dữ liệu cần thiết trong DTO hoặc tải lại entity sau đó.

Flush theo nhóm giúp đẩy SQL xuống database sớm hơn và kiểm soát số entity managed. Clear giúp giải phóng các entity khỏi persistence context. Cả hai vẫn nằm trong transaction chunk nếu được gọi bên trong transaction đó.

Nếu flush lần thứ hai thất bại, toàn bộ SQL của chunk chưa commit vẫn có thể rollback. Flush giữa chunk không tạo commit giữa chunk.

### Không flush/clear tùy tiện giữa các quan hệ entity

Nếu entity cha và con được persist theo cascade, hãy bảo đảm graph đã được nối đúng trước khi flush. Clear giữa lúc đang xây dựng graph hoặc trước khi thao tác cascade hoàn tất có thể làm entity detached và tạo lỗi khó hiểu.

Với custom writer, nên tách rõ:

1. Xây dựng graph entity.
2. Persist/merge graph.
3. Flush.
4. Clear khi không còn cần managed entity.

## 14. Persistence context và JDBC batch

JPA provider như Hibernate có thể gom nhiều INSERT/UPDATE thành JDBC batch nếu cấu hình phù hợp. Tuy nhiên, việc bật JDBC batch không tự động bảo đảm mọi câu lệnh đều được batch.

Một số cấu hình Hibernate thường gặp:

~~~properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
~~~

Ý nghĩa:

- hibernate.jdbc.batch_size: số câu lệnh JDBC có thể gom trong batch.
- hibernate.order_inserts: sắp xếp insert để tăng cơ hội gom câu lệnh cùng loại.
- hibernate.order_updates: sắp xếp update để hỗ trợ batching và có thể giảm deadlock trong một số tình huống.

Các property phải được đặt trong cấu hình JPA/Hibernate phù hợp của ứng dụng. Tên và cách truyền có thể phụ thuộc Spring Boot, Hibernate và persistence provider version.

### Generation strategy ảnh hưởng batching

Với Hibernate, ID generation dùng IDENTITY thường làm hạn chế khả năng batch INSERT vì provider cần thực thi insert để lấy generated key. Sequence-based ID generation có thể thuận lợi hơn cho batching, tùy database và cấu hình.

Không đổi chiến lược ID chỉ để tăng tốc mà chưa đánh giá schema và yêu cầu nghiệp vụ.

### Chunk size, page size và batch size

Ba thông số này có ý nghĩa khác nhau:

| Tham số | Điều khiển |
| --- | --- |
| Chunk size | Số item trong một transaction của Step |
| Page size | Số entity reader lấy trong một trang |
| JDBC batch size | Số câu lệnh SQL provider gom trong một batch JDBC |

Ví dụ chunk size 100, page size 500, JDBC batch size 50:

- Reader có thể nạp một trang 500 item.
- Step commit sau mỗi 100 item.
- Provider có thể gửi SQL theo các nhóm tối đa 50 câu lệnh phù hợp.

Các giá trị cần được đo trên database thật. Page size lớn có thể tăng memory; chunk size lớn có thể kéo dài transaction và giữ lock; JDBC batch size quá lớn có thể tăng bộ nhớ phía driver.

## 15. Lazy loading và detached entity

JPA có thể trì hoãn tải association bằng FetchType.LAZY. Ví dụ:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
~~~

Nếu entity được detach trước khi association được tải, truy cập association có thể gây LazyInitializationException trong Hibernate hoặc lỗi tương ứng từ provider.

Ví dụ rủi ro:

~~~java
Order order = orderReader.read(); // entity có thể detached
String customerName = order.getCustomer().getName();
~~~

Nếu customer chưa được load trước khi reader clear context, processor có thể không truy cập được.

### Cách xử lý

- Dùng JPQL join fetch cho association cần trong batch.
- Dùng EntityGraph để khai báo fetch plan.
- Dùng projection/DTO chỉ chứa field cần xử lý.
- Tách bước đọc thông tin liên quan trong transaction phù hợp.
- Tránh phụ thuộc Open EntityManager in View; batch không có web request lifecycle để dựa vào cơ chế đó.

Ví dụ fetch join:

~~~java
.queryString("""
        select o
        from Order o
        join fetch o.customer
        where o.status = :status
        order by o.id
        """)
~~~

Fetch join collection có thể nhân số dòng kết quả và gây vấn đề với paging. Khi đọc trang, cần cẩn thận với one-to-many collection; projection hoặc query hai bước có thể phù hợp hơn.

Không chuyển tất cả association sang EAGER chỉ để tránh lỗi lazy loading. EAGER rộng có thể làm query nặng và tạo N+1 hoặc dữ liệu dư thừa.

## 16. N+1 query trong batch

N+1 xảy ra khi reader tải N entity chính, rồi processor truy cập association khiến mỗi entity tạo thêm một query.

Ví dụ:

~~~text
1 query lấy 500 Order
500 query lấy Customer cho từng Order
-----------------------------------
501 query
~~~

Đây là chi phí lớn trong batch.

Biện pháp:

- Fetch join các association cần thiết.
- Dùng EntityGraph.
- Dùng batch fetching của provider nếu phù hợp.
- Dùng projection DTO để chỉ lấy field cần thiết.
- Đo số query thực tế bằng SQL log hoặc datasource metrics.

Không chỉ tăng page size để xử lý N+1. Page lớn hơn có thể làm số query phụ tăng thêm và tăng bộ nhớ.

## 17. JPQL bulk update và persistence context

JPQL bulk update/delete thực hiện trực tiếp trên database và bỏ qua cơ chế dirty checking trên từng entity:

~~~java
int updated = entityManager.createQuery("""
        update Order o
        set o.status = :newStatus
        where o.status = :oldStatus
        """)
        .setParameter("newStatus", OrderStatus.PROCESSED)
        .setParameter("oldStatus", OrderStatus.READY)
        .executeUpdate();
~~~

Bulk update có thể nhanh hơn khi cập nhật số lượng lớn, nhưng persistence context hiện tại không tự đồng bộ state của các entity đã load trước đó.

Ví dụ, một Order đang managed có status READY. Bulk query đổi database thành PROCESSED, nhưng object trong context có thể vẫn là READY. Khi flush, trạng thái cũ trong context có thể gây ghi đè tùy mapping và provider.

Một chiến lược thường dùng:

~~~java
entityManager.flush();

int updated = query.executeUpdate();

entityManager.clear();
~~~

Flush các thay đổi managed trước bulk operation, chạy bulk SQL, rồi clear để tránh giữ entity stale. Nếu chỉ cần refresh một entity cụ thể, có thể dùng refresh sau bulk operation.

Bulk operation không tự gọi entity lifecycle callback cho từng entity và có thể bỏ qua optimistic locking/version handling thông thường. Nếu nghiệp vụ cần version check hoặc audit callback cho từng entity, hãy dùng cách cập nhật entity phù hợp.

## 18. Optimistic locking và @Version

Khi nhiều Job hoặc transaction có thể cập nhật cùng entity, dùng optimistic locking để phát hiện xung đột:

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

Khi entity được cập nhật, JPA kiểm tra version hiện tại. Nếu transaction khác đã thay đổi version trước đó, update có thể thất bại với optimistic locking exception.

Trong batch:

- Exception có thể xuất hiện tại flush hoặc commit.
- Có thể retry nếu xung đột là tạm thời và thao tác có thể thực hiện lại an toàn.
- Không skip mọi optimistic lock exception nếu việc bỏ qua làm mất cập nhật nghiệp vụ.
- Có thể cần đọc lại entity và tính toán lại thay vì merge state cũ.

merge() một detached entity có version cũ không đảm bảo cập nhật thành công. Version check vẫn có thể phát hiện stale state.

## 19. Persistence context và cascade

Entity relationship có thể khai báo cascade:

~~~java
@OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST,
        orphanRemoval = true)
private List<OrderLine> lines = new ArrayList<>();
~~~

Cascade xác định thao tác EntityManager có được truyền sang association hay không:

- PERSIST: persist cha có thể persist con.
- MERGE: merge cha có thể merge con.
- REMOVE: remove cha có thể remove con.
- REFRESH: refresh cha có thể refresh con.
- DETACH: detach cha có thể detach con.
- ALL: áp dụng tất cả các thao tác trên.

Không bật CascadeType.ALL theo thói quen. Nếu entity cha tham chiếu một entity dùng chung như Customer, cascade REMOVE có thể xóa dữ liệu không nên xóa.

Trong batch, graph entity lớn và cascade sâu có thể tạo nhiều SQL và tăng memory. Chỉ cascade những quan hệ thực sự thuộc vòng đời aggregate.

### orphanRemoval

Với orphanRemoval, bỏ một child khỏi collection có thể khiến child bị xóa khi flush:

~~~java
order.getLines().remove(line);
~~~

Test cần xác nhận hành vi xóa này đúng nghiệp vụ. Không dùng clear collection để giảm memory nếu collection đang managed và orphanRemoval có thể xóa dữ liệu con.

## 20. Transaction propagation và EntityManager

Các service được gọi từ processor/writer có thể khai báo @Transactional. Propagation quyết định service tham gia transaction chunk hay mở transaction khác.

| Propagation | Tác động thường gặp |
| --- | --- |
| REQUIRED | Tham gia transaction hiện tại nếu có |
| REQUIRES_NEW | Tạm ngưng transaction hiện tại và mở transaction mới |
| SUPPORTS | Tham gia nếu có transaction, nếu không thì không tạo mới |
| NOT_SUPPORTED | Tạm ngưng transaction hiện tại |

Nếu muốn thay đổi entity rollback cùng chunk, service thường dùng REQUIRED và cùng transaction manager.

Nếu dùng REQUIRES_NEW, service có thể commit độc lập. Khi writer sau đó lỗi và chunk rollback, thay đổi đã commit trong transaction mới không tự rollback theo chunk.

Gọi method transactional qua Spring proxy là điều kiện để transaction interceptor hoạt động. Self-invocation trong cùng bean có thể không đi qua proxy theo cách mong muốn.

Không gọi EntityTransaction.begin() hoặc commit() trên EntityManager được Spring quản lý. Hãy để JpaTransactionManager và Spring Batch điều khiển transaction.

## 21. Không giữ entity managed qua nhiều chunk

Một Job có thể chạy hàng giờ. Nếu một persistence context giữ tất cả entity đã đọc hoặc ghi từ đầu Job, memory sẽ tăng dần.

Các triệu chứng:

- Heap tăng theo số item.
- Dirty checking ngày càng tốn thời gian.
- Flush tạo ra nhiều SQL hơn dự kiến.
- GC hoạt động thường xuyên.
- Job chậm dần theo thời gian.

Giải pháp:

- Dùng transaction-scoped persistence context.
- Giới hạn chunk/page size.
- Flush và clear sau nhóm entity phù hợp.
- Dùng JpaItemWriter với clear policy phù hợp.
- Không lưu managed entity trong static collection hoặc singleton.
- Dùng DTO/ID trong ExecutionContext thay vì entity graph.

Không clear context khi còn pending changes chưa flush. Không giữ proxy association đã detach rồi truy cập ở Step sau.

## 22. EntityManager và restart của Spring Batch

Persistence context không phải checkpoint của Spring Batch. EntityManager và managed entity không được serialize vào ExecutionContext để tiếp tục Job.

Restart dựa trên:

- JobInstance và JobParameters.
- StepExecution/ExecutionContext.
- State của ItemStream reader/writer.
- Dữ liệu đã commit trong database.

Sau khi chunk commit, transaction kết thúc. EntityManager/persistence context transaction-scoped sẽ không được dùng làm trạng thái tiếp tục cho chunk sau. Khi restart, reader mở lại và tải dữ liệu từ database hoặc vị trí checkpoint.

### Không lưu entity vào ExecutionContext

Không nên lưu managed entity trực tiếp trong ExecutionContext. Thay vào đó, lưu định danh hoặc vị trí:

~~~java
executionContext.putLong("lastOrderId", 1001L);
~~~

Sau restart, tải lại entity bằng ID hoặc để reader khôi phục theo checkpoint. Điều này tránh lưu object graph lớn, proxy chưa serialize được và state stale.

### Writer idempotent

Nếu chunk rollback rồi chạy lại, writer có thể nhận cùng item. Dùng unique business key, version hoặc upsert có kiểm soát để tránh tạo dữ liệu trùng. Đừng dựa vào persistence context để chống duplicate giữa các transaction; first-level cache chỉ tồn tại trong context hiện tại.

## 23. Đọc và ghi cùng entity trong một Step

Một trường hợp phổ biến là reader chọn các Order READY, processor tính toán, writer đổi trạng thái thành PROCESSED.

Nếu reader dùng JpaPagingItemReader, entity có thể detached sau khi trang được đọc. Writer dùng JpaItemWriter/merge hoặc tải entity managed trong transaction ghi.

Tuy nhiên, nếu writer thay đổi cột status là điều kiện của query, tập dữ liệu READY có thể thay đổi khi reader đang paging. Với paging dựa trên offset, các trang tiếp theo có thể bỏ sót item nếu tập kết quả co lại.

Ví dụ:

~~~text
Trang đầu lấy READY: 1, 2, 3, 4, 5
Writer đổi status của 1-5 thành PROCESSED

Tập READY còn: 6, 7, 8, 9, 10
Nếu trang tiếp theo dùng offset 5 trên tập đã thay đổi,
các item 6-10 có thể bị bỏ qua.
~~~

Giải pháp:

- Dùng batch ID hoặc staging table để cố định tập item.
- Dùng cutoff/watermark ổn định.
- Phân trang theo khóa bất biến và query được thiết kế phù hợp.
- Tách bước claim input khỏi bước xử lý.
- Không thay đổi predicate/sort key đang dùng để paging nếu chưa kiểm soát được tác động.

Persistence context không giải quyết vấn đề tập kết quả thay đổi giữa các trang. Đây là vấn đề về query, transaction và chiến lược phân vùng input.

## 24. EntityManager trong multi-threaded Step và partitioning

EntityManager không thread-safe. Không dùng cùng một EntityManager vật lý cho nhiều thread.

Trong multi-threaded Step:

- Transaction có thể khác nhau giữa các thread.
- Mỗi thread cần persistence context gắn với transaction của nó.
- Không chia sẻ managed entity qua thread boundary.
- Không dùng collection entity mutable chung giữa worker.
- Reader/writer phải được thiết kế thread-safe hoặc dùng cơ chế đồng bộ phù hợp.

Trong partitioning:

- Mỗi partition thường có StepExecution riêng.
- Dùng StepScope cho component phụ thuộc partition parameters.
- EntityManager proxy sẽ làm việc với transaction hiện tại của worker nếu cấu hình đúng.
- Mỗi worker nên xử lý tập ID không chồng lấn hoặc có claim/locking.

Không truyền EntityManager vào Executor task rồi dùng sau khi transaction của thread gọi đã kết thúc. Nếu cần xử lý song song, mỗi worker phải có transaction và EntityManager riêng do Spring quản lý.

## 25. Test persistence context độc lập

Có thể dùng JPA integration test để xác nhận entity lifecycle và dirty checking. Ví dụ với transaction test:

~~~java
@DataJpaTest
class OrderPersistenceContextTest {

    @Autowired
    private EntityManager entityManager;

    @Test
    void dirtyCheckingUpdatesManagedEntity() {
        Order order = new Order();
        order.setId(1001L);
        order.setStatus(OrderStatus.READY);
        entityManager.persist(order);
        entityManager.flush();

        order.setStatus(OrderStatus.PROCESSED);
        entityManager.flush();
        entityManager.clear();

        Order reloaded = entityManager.find(Order.class, 1001L);
        assertEquals(OrderStatus.PROCESSED, reloaded.getStatus());
    }
}
~~~

Test này kiểm tra dirty checking và việc clear làm entity được load lại từ database. Cấu hình fixture/ID phải phù hợp với entity thực tế.

### Test merge trả về managed instance

~~~java
Order detached = new Order();
detached.setId(1001L);
detached.setStatus(OrderStatus.PROCESSED);

Order managed = entityManager.merge(detached);

assertNotSame(detached, managed);
assertTrue(entityManager.contains(managed));
assertFalse(entityManager.contains(detached));
~~~

Kết quả identity cụ thể có thể phụ thuộc trường hợp entity đã managed hay chưa. Test nên tạo tình huống detached thực sự bằng cách persist/flush/clear trước khi merge.

### Test flush không phải commit

Một integration test cần transaction boundary rõ ràng:

1. Persist entity và flush.
2. Gây exception khiến transaction rollback.
3. Mở transaction mới và xác nhận entity không tồn tại.

Không dùng một test method mặc định có transaction rollback sau khi test kết thúc để kết luận flush đã commit. Flush chỉ gửi SQL trong transaction.

## 26. Test JpaPagingItemReader và JpaItemWriter

Ngoài test JPA entity, cần kiểm tra cách Spring Batch reader/writer tương tác với persistence context:

- Reader trả đúng item và thứ tự.
- Reader page boundary không bỏ sót hoặc lặp item.
- Entity trả về có trạng thái detached như dự kiến.
- Lazy association cần thiết đã được fetch.
- Writer merge entity detached đúng.
- Writer persist entity mới đúng.
- Flush lỗi làm chunk rollback.
- Clear policy không làm mất thao tác chưa flush.
- Restart khôi phục đúng vị trí và không ghi trùng.

Có thể dùng Spring Batch Test để chạy Step thật với database test. Khi test restart, cần chạy JobInstance, làm Step thất bại có kiểm soát rồi launch lại cùng identifying JobParameters.

Không chỉ assert BatchStatus. Hãy truy vấn database và xác nhận record count, business key, version và trạng thái entity.

## 27. Những lỗi thường gặp

### Nghĩ merge làm object đầu vào trở thành managed

Merge trả về managed instance khác. Dùng object được trả về nếu cần thao tác tiếp.

### Gọi persist cho entity detached

Persist dành cho entity mới. Với entity detached, dùng merge hoặc tải lại entity managed rồi cập nhật.

### Nghĩ flush là commit

Flush chỉ gửi SQL trong transaction. Transaction vẫn có thể rollback.

### Clear trước flush

Thay đổi chưa flush có thể bị detach và không được ghi. Flush trước clear khi cần giữ thay đổi.

### Giữ toàn bộ entity trong persistence context

Job lớn có thể tăng memory và dirty checking cost. Giới hạn chunk/page và flush/clear có kiểm soát.

### Truy cập lazy association sau khi reader clear context

Entity detached có thể không tải được association. Fetch đúng dữ liệu hoặc dùng DTO/projection.

### Dùng EntityManager vật lý ở nhiều thread

EntityManager không thread-safe. Dùng shared proxy/transaction-scoped context và không truyền instance vật lý giữa thread.

### Dùng cùng persistence context cho toàn Job

Context quá dài dễ giữ nhiều entity và trạng thái stale. Dùng transaction-scoped context cho chunk.

### Không hiểu bulk JPQL bypass persistence context

Managed entity có thể stale sau bulk update. Flush trước và clear/refresh sau khi cần.

### Dùng merge cho mọi entity trong writer

Merge có thể tốn truy vấn và copy graph. Chọn persist cho entity mới, dirty checking cho managed entity và merge cho detached state.

### Nghĩ restart khôi phục EntityManager

Spring Batch khôi phục checkpoint, không khôi phục persistence context. Lưu ID/offset thay vì entity.

### Chỉ test H2 rồi kết luận production giống nhau

Locking, ID generation, batching và SQL behavior có thể khác theo database. Chạy integration test trên database cùng loại khi behavior phụ thuộc engine.

## 28. Quy trình thiết kế JPA processing trong Spring Batch

Khi xây dựng Step dùng JPA, hãy xác định:

1. EntityManagerFactory nào quản lý entity và database?
2. Step dùng JpaTransactionManager phù hợp với EntityManagerFactory đó không?
3. Persistence context có transaction-scoped hay bị giữ quá lâu?
4. Reader trả entity managed hay detached?
5. Writer cần persist, merge hay chỉ thay đổi managed entity?
6. Sau write có flush/clear không và ai sở hữu lifecycle?
7. Chunk size, page size và JDBC batch size có phù hợp không?
8. Lazy association nào cần fetch trước khi context bị clear?
9. Có N+1 query hoặc fetch join collection gây vấn đề paging không?
10. Bulk JPQL có làm persistence context stale không?
11. Nhiều Job/worker có thể cập nhật cùng entity không?
12. Có cần @Version và xử lý optimistic locking không?
13. Restart có dùng lại input, query, sort key và checkpoint ổn định không?
14. Writer có idempotent khi chunk được retry không?
15. Có integration test cho rollback, restart, lazy loading và batch behavior không?

Một thiết kế tốt giữ persistence context đủ ngắn để kiểm soát bộ nhớ, nhưng đủ lâu để dirty checking và transaction hoạt động đúng. Reader/writer phải có cách xử lý rõ ràng với entity detached; query phải có thứ tự ổn định; các thao tác flush, clear và merge phải được dùng theo đúng semantics của JPA.

## Kết luận

EntityManager là API làm việc với entity, còn persistence context là first-level cache theo dõi các entity managed và thay đổi của chúng. Dirty checking giúp cập nhật entity managed mà không cần gọi save, persist() dùng cho entity mới, merge() trả về managed instance, flush() gửi SQL nhưng không commit, còn clear() detach toàn bộ entity trong context. Trong Spring Batch, mỗi chunk thường có transaction riêng; JpaPagingItemReader có thể trả entity detached sau khi clear context của reader, vì vậy writer cần merge hoặc tải lại entity managed. Kiểm soát flush/clear, lazy loading, JDBC batching và sort key để tránh tăng bộ nhớ hoặc bỏ sót dữ liệu. Không chia sẻ EntityManager vật lý giữa thread và không xem persistence context là checkpoint; restart phải dựa vào ExecutionContext, input ổn định và thao tác ghi idempotent.
