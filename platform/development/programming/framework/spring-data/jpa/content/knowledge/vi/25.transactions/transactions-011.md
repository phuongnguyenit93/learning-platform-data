# Giao dịch qua luồng, `@Async` và phạm vi `EntityManager`

## 1. Mục tiêu và bối cảnh

Trong ứng dụng Spring Data JPA, một giao dịch thường được quản lý trong luồng đang thực thi. Khi dùng `@Async`, Spring chuyển công việc sang một luồng khác thuộc `TaskExecutor`. Luồng mới có ngữ cảnh thực thi riêng, vì vậy nó không tự động dùng chung giao dịch hoặc persistence context của luồng gọi.

Sau bài học, bạn cần giải thích được:

- Spring bắt đầu, commit và rollback giao dịch ở đâu.
- Vì sao transaction context và persistence context của JPA gắn với luồng trong mô hình imperative.
- `EntityManager` được Spring tiêm vào bean khác với một đối tượng `EntityManager` thực tế như thế nào.
- Vì sao `@Async` không kế thừa giao dịch của phương thức gọi.
- Cách tổ chức service để mỗi tác vụ bất đồng bộ có giao dịch JPA riêng.
- Cách xử lý dữ liệu chưa commit, entity detached, lazy loading và lỗi thường gặp khi chạy song song.

Các ví dụ dùng Spring Framework/Spring Data JPA theo mô hình Jakarta Persistence. Với dự án Spring Boot 2 hoặc Spring Data JPA 2, thay các import `jakarta.persistence.*` bằng `javax.persistence.*` tương ứng.

## 2. Spring quản lý giao dịch theo luồng

`@Transactional` là khai báo ranh giới giao dịch. Trong cấu hình Spring AOP thông thường, lời gọi đi qua proxy của bean sẽ được transaction interceptor xử lý:

1. Trước khi gọi thân phương thức, interceptor tìm hoặc tạo giao dịch theo transaction manager và propagation đã cấu hình.
2. Với JPA, `JpaTransactionManager` quản lý giao dịch và liên kết `EntityManager` phù hợp với luồng hiện tại.
3. Phương thức chạy trong giao dịch đó. Các thao tác repository và JPA tham gia giao dịch hiện hành nếu dùng cùng transaction manager và persistence unit.
4. Khi phương thức kết thúc, Spring commit nếu thành công hoặc rollback theo quy tắc rollback.

Mặc định, `@Transactional` dùng propagation `REQUIRED`: tham gia giao dịch đang có trên luồng hiện tại, hoặc tạo giao dịch mới nếu chưa có. Mặc định Spring rollback với `RuntimeException` và `Error`; checked exception không tự động làm rollback trừ khi cấu hình `rollbackFor`.

Trong mô hình imperative, Spring lưu thông tin giao dịch và tài nguyên đồng bộ với luồng, thường thông qua cơ chế thread-bound của `TransactionSynchronizationManager`. Vì thế, hai lời gọi ở hai luồng khác nhau không tự nhiên nhìn thấy cùng một transaction context.

Ví dụ minh họa:

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void markPaid(long orderId) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow();
        order.markPaid();
    }
}
```

Đây là đoạn mã minh họa cần có Spring context, repository và entity `Order`. Khi gọi `markPaid` qua Spring bean proxy, entity được nạp trong persistence context của giao dịch. Nếu entity đang được quản lý, thay đổi trạng thái sẽ được JPA dirty checking phát hiện và đồng bộ khi commit; không nhất thiết phải gọi `save` lần nữa.

### Ranh giới proxy cũng quan trọng

Trong proxy-based AOP, lời gọi nội bộ từ một phương thức sang phương thức khác cùng object, chẳng hạn `this.otherMethod()`, không đi qua proxy. Vì vậy, `@Transactional` hoặc `@Async` trên `otherMethod` có thể không được áp dụng như mong đợi. Hãy gọi qua một Spring bean khác hoặc tổ chức lại ranh giới service để lời gọi đi qua proxy.

## 3. Phạm vi và vòng đời của EntityManager

JPA phân biệt hai đối tượng:

- `EntityManagerFactory`: nhà máy tạo `EntityManager`, được thiết kế để dùng chung và an toàn cho nhiều luồng.
- `EntityManager`: đại diện cho một persistence context cụ thể; không an toàn khi nhiều luồng cùng truy cập đồng thời.

Trong cấu hình Spring thông dụng, field được tiêm bằng `@PersistenceContext` là một shared EntityManager proxy. Proxy này tìm `EntityManager` đang gắn với giao dịch/luồng hiện tại. Do đó, một singleton service có thể giữ field proxy này mà không có nghĩa nhiều luồng đang dùng chung một `EntityManager` thực tế.

Với persistence context có phạm vi giao dịch, `JpaTransactionManager` thường tạo hoặc lấy `EntityManager`, gắn nó vào luồng khi giao dịch bắt đầu, rồi đồng bộ và giải phóng tài nguyên khi giao dịch kết thúc. Các repository Spring Data JPA cũng tham gia cơ chế này.

Cần phân biệt:

- **Entity đang managed:** thuộc persistence context hiện tại; thay đổi được dirty checking theo dõi.
- **Entity detached:** không còn được quản lý bởi persistence context đã nạp nó. Đọc thuộc tính cơ bản có thể vẫn được, nhưng lazy association có thể không tải được.
- **EntityManager proxy:** đối tượng trung gian do Spring cung cấp; nó định tuyến thao tác đến persistence context phù hợp.
- **EntityManager thực tế:** đối tượng làm việc với persistence context; không được chia sẻ cho nhiều luồng.

Không lưu một `EntityManager` thực tế, Hibernate `Session`, hoặc entity đang managed vào biến static hay truyền chúng cho nhiều tác vụ chạy song song. Hãy truyền khóa chính hoặc DTO bất biến, sau đó nạp lại entity trong giao dịch của tác vụ nhận.

### Open EntityManager in View không truyền giao dịch sang luồng khác

Open EntityManager in View (OSIV) có thể giữ một EntityManager gắn với luồng xử lý request web trong suốt vòng đời request để hỗ trợ một số thao tác lazy loading sau khi service transaction kết thúc. Cơ chế này không làm cho EntityManager an toàn đa luồng và cũng không truyền transaction context sang executor của `@Async`.

Tác vụ bất đồng bộ chạy ở luồng riêng phải có persistence context và ranh giới giao dịch phù hợp với chính nó. Không dựa vào OSIV của request để truy cập lazy association từ tác vụ nền.

## 4. Điều gì xảy ra khi gọi @Async?

`@Async` yêu cầu Spring gửi lời gọi đến một executor. Thân phương thức chạy trên một worker thread, có thể là luồng khác với luồng controller hoặc service đã gọi nó.

Giả sử luồng A đang ở trong một phương thức `@Transactional` và gọi một phương thức `@Async`:

- Giao dịch của luồng A vẫn thuộc luồng A.
- Executor đưa tác vụ sang luồng B.
- Luồng B không nhận transaction context, EntityManager hay persistence context của luồng A.
- Nếu mã chạy ở luồng B gọi một phương thức `@Transactional` qua Spring proxy, Spring có thể tạo giao dịch mới cho luồng B.
- Giao dịch của luồng B commit hoặc rollback độc lập với giao dịch của luồng A.

Vì vậy, `@Async` không có nghĩa là “chạy tiếp trong cùng giao dịch nhưng ở nền”. Nó có nghĩa là “thực thi công việc trên executor”; giao dịch của công việc đó cần được thiết kế riêng.

### Propagation khi chạy trên luồng mới

| Propagation | Hành vi trên luồng chạy tác vụ |
|---|---|
| `REQUIRED` | Tham gia giao dịch nếu luồng đó đang có; nếu không, tạo giao dịch mới. |
| `REQUIRES_NEW` | Tạo giao dịch mới; nếu luồng đó có giao dịch hiện hành thì tạm ngưng giao dịch đó. |
| `MANDATORY` | Báo lỗi nếu luồng đó không có giao dịch hiện hành. |
| `SUPPORTS` | Tham gia nếu có giao dịch; nếu không thì chạy không có giao dịch. |
| `NOT_SUPPORTED` | Tạm ngưng giao dịch hiện hành trên luồng đó và chạy không có giao dịch. |

Nếu luồng A có giao dịch nhưng luồng B chưa có, `REQUIRED` ở luồng B sẽ tạo giao dịch mới. `REQUIRES_NEW` cũng tạo giao dịch mới ở luồng B; nó không thể “tạm ngưng” giao dịch của luồng A vì giao dịch đó không thuộc luồng B.

### Trường hợp dữ liệu chưa commit

Một lỗi dễ gặp là gửi tác vụ async trước khi giao dịch của luồng gọi commit:

```java
@Transactional
public void createOrder() {
    Order order = orderRepository.save(new Order());
    orderAsyncFacade.process(order.getId());
    // Giao dịch hiện tại vẫn chưa commit tại thời điểm này.
}
```

Tác vụ ở luồng khác có thể bắt đầu trước khi giao dịch tạo đơn hàng commit. Khi đó, truy vấn từ tác vụ nền có thể chưa thấy bản ghi; nếu giao dịch của luồng gọi rollback, tác vụ nền vẫn có thể đã chạy và tạo ra tác động độc lập.

Nếu tác vụ chỉ được phép chạy sau khi giao dịch tạo dữ liệu commit, hãy phát sự kiện trong giao dịch và xử lý sự kiện ở pha `AFTER_COMMIT`:

```java
public record OrderCreatedEvent(long orderId) {}

@Service
public class OrderCommandService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher publisher;

    public OrderCommandService(
            OrderRepository orderRepository,
            ApplicationEventPublisher publisher) {
        this.orderRepository = orderRepository;
        this.publisher = publisher;
    }

    @Transactional
    public void createOrder() {
        Order order = orderRepository.save(new Order());
        publisher.publishEvent(new OrderCreatedEvent(order.getId()));
    }
}

@Component
public class OrderCreatedListener {

    private final OrderAsyncFacade asyncFacade;

    public OrderCreatedListener(OrderAsyncFacade asyncFacade) {
        this.asyncFacade = asyncFacade;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        asyncFacade.process(event.orderId());
    }
}
```

Các đoạn mã trên là ví dụ tích hợp trong ứng dụng Spring; cần có entity, repository và cấu hình event tương ứng. Listener mặc định gắn với một transaction; nếu sự kiện được phát ngoài transaction, listener này không chạy trừ khi chủ động bật `fallbackExecution`.

`AFTER_COMMIT` bảo đảm listener chỉ được gọi sau khi transaction commit thành công, nhưng đây vẫn là xử lý trong tiến trình ứng dụng. Nếu yêu cầu giao nhận sự kiện bền vững khi ứng dụng dừng đột ngột, hãy cân nhắc Transactional Outbox và một tiến trình/consumer đọc outbox. Không coi event listener trong bộ nhớ là hàng đợi bền vững.

## 5. Cấu trúc service khuyến nghị

Một cách tổ chức rõ ràng là tách bean điều phối bất đồng bộ khỏi bean thực hiện nghiệp vụ trong giao dịch:

1. Bean điều phối nhận yêu cầu và có `@Async`.
2. Bean nghiệp vụ nhận ID hoặc dữ liệu bất biến, nạp entity trong luồng worker và có `@Transactional`.
3. Mỗi tác vụ nền có transaction boundary riêng; entity được dùng trong đúng persistence context của tác vụ đó.

### Cấu hình executor

```java
@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean("jpaTaskExecutor")
    public Executor jpaTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("jpa-async-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
```

Các con số chỉ là ví dụ ban đầu, không phải giá trị tối ưu cho mọi hệ thống. Cần chọn kích thước pool và queue theo thời gian xử lý, tải thực tế và giới hạn kết nối database. Nếu số worker cùng lúc vượt quá khả năng cấp connection, tác vụ có thể phải chờ hoặc làm hệ thống quá tải. Theo dõi queue, thời gian chờ, lỗi từ chối tác vụ và thời gian xử lý.

### Bean chạy async và bean mở transaction

```java
@Service
public class OrderAsyncFacade {

    private final OrderTransactionalWorker worker;

    public OrderAsyncFacade(OrderTransactionalWorker worker) {
        this.worker = worker;
    }

    @Async("jpaTaskExecutor")
    public CompletableFuture<Void> process(long orderId) {
        worker.process(orderId);
        return CompletableFuture.completedFuture(null);
    }
}

@Service
public class OrderTransactionalWorker {

    private final OrderRepository orderRepository;

    public OrderTransactionalWorker(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void process(long orderId) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow();
        order.markProcessing();
    }
}
```

Đây là các lớp minh họa cần được đăng ký trong Spring context và cần có `Order`, `OrderRepository` cùng phương thức nghiệp vụ tương ứng. Khi gọi `process` qua proxy của `OrderAsyncFacade`, Spring gửi lời gọi đến `jpaTaskExecutor`. Trên worker thread, lời gọi đến bean `OrderTransactionalWorker` đi qua proxy giao dịch và mở transaction cho công việc JPA.

`CompletableFuture` cho phép bên gọi quan sát thời điểm hoàn tất và lỗi:

```java
CompletableFuture<Void> task = orderAsyncFacade.process(orderId);

// Chỉ chờ khi luồng gọi thật sự cần kết quả hoàn tất.
task.join();
```

Không gọi `join()` hoặc `get()` ngay sau mọi lời gọi async nếu mục tiêu là giải phóng luồng gọi; làm vậy sẽ biến thao tác thành chờ đồng bộ. Với phương thức trả về `void`, lỗi không được trả về cho caller; cần cấu hình `AsyncUncaughtExceptionHandler` và cơ chế log/giám sát. Với `CompletableFuture`, hãy xử lý exceptional completion phù hợp.

Tránh đặt hai annotation `@Async` và `@Transactional` trên cùng một phương thức rồi giả định rằng giao dịch của caller được giữ nguyên. Ranh giới rõ ràng giữa bean async và bean transactional giúp dễ xác định luồng nào mở transaction, dễ kiểm thử và tránh nhầm lẫn về proxy/advisor.

## 6. Quy tắc an toàn khi dùng JPA trong tác vụ nền

### Truyền ID hoặc DTO, nạp entity trong worker

Không truyền entity đang managed từ transaction của luồng gọi sang worker. Sau khi rời persistence context ban đầu, entity có thể detached; các lazy association có thể không còn tải được. Ngay cả khi entity đã được tải đầy đủ, hai luồng cập nhật cùng một object vẫn có nguy cơ race condition.

Nên truyền ID:

```java
asyncFacade.process(order.getId());
```

Sau đó worker truy vấn lại:

```java
@Transactional
public void process(long orderId) {
    Order order = orderRepository.findById(orderId)
        .orElseThrow();
    order.recalculate();
}
```

Nếu dữ liệu cần thiết đã được tính trước và không cần entity, có thể truyền DTO bất biến. DTO giúp xác định rõ snapshot dữ liệu mà tác vụ nhận được.

### Kiểm soát cập nhật đồng thời

Hai worker có thể cùng đọc và cập nhật một bản ghi. Nếu nghiệp vụ cần phát hiện ghi đè, dùng optimistic locking với `@Version`:

```java
@Entity
public class Order {

    @Id
    private Long id;

    @Version
    private long version;

    // Các trường và phương thức nghiệp vụ khác.
}
```

Khi một transaction cập nhật phiên bản đã cũ, JPA provider có thể phát hiện xung đột và ném lỗi optimistic locking. Ứng dụng cần quyết định retry, báo xung đột hay bỏ tác vụ. Retry chỉ an toàn khi thao tác có tính idempotent hoặc có cơ chế chống xử lý trùng. Các ràng buộc unique ở database vẫn cần thiết để bảo vệ invariant dữ liệu.

### Giữ transaction ngắn

Không giữ transaction và connection trong lúc chờ API bên ngoài, gửi email hoặc thực hiện công việc chậm. Hãy tách phần đọc/ghi database khỏi I/O bên ngoài khi nghiệp vụ cho phép. Với xử lý theo lô, chia dữ liệu thành batch có kích thước phù hợp và xác định rõ mỗi batch là một transaction hay toàn bộ công việc là một transaction.

### Không chia sẻ transaction context bằng TaskDecorator

Executor có thể dùng `TaskDecorator` để truyền một số context như MDC hoặc thông tin quan sát. Cách này không biến transaction JPA thành tài nguyên dùng chung an toàn. Không sao chép `EntityManager`, Hibernate Session hoặc transaction synchronization sang worker thread. Mỗi worker cần tự mở transaction bằng Spring transaction manager.

## 7. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Worker không thấy bản ghi vừa tạo | Async chạy trước khi transaction caller commit | Phát sự kiện và xử lý ở `AFTER_COMMIT`, hoặc dùng outbox khi cần độ tin cậy cao |
| `LazyInitializationException` | Worker dùng entity detached hoặc không có persistence context phù hợp | Truyền ID/DTO và nạp lại entity trong transaction worker; fetch đúng dữ liệu cần dùng |
| `@Transactional` không có tác dụng | Gọi nội bộ qua `this`, gọi object tự tạo bằng `new`, hoặc bean không đi qua proxy | Gọi qua Spring bean proxy và kiểm tra cấu hình transaction management |
| `@Async` chạy đồng bộ | Tự gọi phương thức async trong cùng bean hoặc chưa bật async processing | Bật `@EnableAsync` và gọi qua proxy từ bean khác |
| Lỗi khi dùng `MANDATORY` ở worker | Worker thread không có transaction được truyền từ caller | Dùng propagation phù hợp, thường là `REQUIRED` để worker mở transaction riêng |
| Ghi đè dữ liệu giữa các worker | Nhiều transaction cập nhật cùng một entity | Dùng optimistic/pessimistic locking phù hợp, ràng buộc database và retry có kiểm soát |
| Tác vụ nền thất bại nhưng caller không biết | Phương thức async trả `void` hoặc không xử lý Future | Trả `CompletableFuture`, xử lý lỗi và bổ sung logging/monitoring |
| Connection pool bị cạn | Số worker hoặc thời gian giữ transaction quá lớn | Giới hạn executor, rút ngắn transaction và điều chỉnh theo connection pool |

## 8. Kiểm thử hành vi async và transaction

Kiểm thử cần đồng bộ theo kết quả tác vụ thay vì dùng `Thread.sleep` để đoán khi nào worker hoàn tất. Với `CompletableFuture`, có thể chờ có timeout rồi đọc lại dữ liệu bằng một transaction kiểm tra riêng.

Một điểm dễ gây nhầm là test Spring thường được đánh dấu `@Transactional` và rollback khi kết thúc. Transaction của test chạy trên luồng test không tự truyền sang worker. Nếu worker cần đọc dữ liệu do test tạo, hãy commit dữ liệu trước khi phát tác vụ hoặc thiết kế test không dựa vào transaction chưa commit. Worker có thể commit độc lập dù transaction của test sau đó rollback; vì vậy cần dọn dữ liệu kiểm thử rõ ràng.

Nên kiểm tra ít nhất các trường hợp:

- Worker đọc được dữ liệu đã commit và lưu thay đổi thành công.
- Worker không chạy khi transaction phát sự kiện rollback nếu dùng listener `AFTER_COMMIT`.
- Lỗi trong worker làm transaction worker rollback.
- Tác vụ nhận ID/DTO và tự nạp dữ liệu; không phụ thuộc entity managed của luồng gọi.
- Nhiều tác vụ cập nhật cùng bản ghi được xử lý theo chính sách khóa và retry của ứng dụng.

## 9. Checklist thiết kế

Trước khi đưa xử lý JPA bất đồng bộ vào production, hãy xác nhận:

- [ ] Async processing được bật và phương thức được gọi qua Spring proxy.
- [ ] Executor có giới hạn thread, queue và chính sách từ chối phù hợp.
- [ ] Transaction boundary của worker được khai báo rõ trong bean nghiệp vụ.
- [ ] Worker truyền/nhận ID hoặc DTO; không dùng chung EntityManager, Session hay managed entity giữa các luồng.
- [ ] Tác vụ cần dữ liệu vừa tạo chỉ được phát sau commit, hoặc dùng cơ chế outbox khi cần giao nhận bền vững.
- [ ] Xung đột cập nhật, xử lý trùng, retry và lỗi async có chính sách cụ thể.
- [ ] Kiểm thử chờ Future/event hoàn tất và xác minh dữ liệu sau commit.

## 10. Ghi nhớ

Trong Spring Data JPA theo mô hình imperative, transaction và persistence context gắn với luồng thực thi. `@Async` chuyển công việc sang worker thread nên không mang theo transaction của caller. Hãy để worker nạp entity trong persistence context của chính nó và gọi một service `@Transactional` qua Spring proxy. Nếu tác vụ phụ thuộc vào dữ liệu vừa được tạo, chỉ khởi chạy sau commit; nếu cần bảo đảm giao nhận khi tiến trình gặp sự cố, dùng cơ chế bền vững như Transactional Outbox.
