# Những bảo đảm Spring cung cấp và trách nhiệm của mã nghiệp vụ

> **Phạm vi:** Spring Framework – concurrency, phần **Tổng quan**. Bài học phân định chính xác đâu là cơ chế Spring quản lý, đâu là tính đúng đắn khi nhiều request, luồng, tác vụ và nhiều instance đồng thời thực thi mà mã nghiệp vụ phải tự bảo vệ.

## 1. Vì sao cần phân biệt?

Một ứng dụng Spring có thể tiếp nhận nhiều request HTTP, chạy tác vụ @Async, xử lý thông điệp, kích hoạt @Scheduled và thực thi giao dịch cùng lúc. Các lời gọi có thể truy cập cùng một bean singleton, cùng một hàng dữ liệu hoặc cùng một dịch vụ bên ngoài. Framework có thể tổ chức nơi thực thi nhưng không tự biết các bất biến như “tồn kho không được âm”, “một đơn không được thanh toán hai lần” hay “sự kiện phải được xử lý lại an toàn”.

Có ba tầng trách nhiệm cần phân tách:

1. **Điều phối:** nơi và thời điểm chạy, executor/scheduler, chuyển lời gọi qua Spring proxy, vòng đời của bean/tác vụ.
2. **An toàn truy cập:** dữ liệu chia sẻ, Java Memory Model, atomicity, locking, isolation và thứ tự cập nhật.
3. **Tính đúng đắn nghiệp vụ:** invariant, idempotency, khả năng phục hồi sau lỗi, duplicate, timeout và nhất quán giữa hệ thống.

Spring hỗ trợ tầng thứ nhất và cung cấp công cụ cho hai tầng còn lại. **Tính thread-safe và exactly-once không tự xuất hiện khi thêm annotation.**

## 2. Ma trận bảo đảm và trách nhiệm

| Cơ chế | Spring cung cấp | Mã nghiệp vụ cần bảo đảm |
| --- | --- | --- |
| IoC, DI và bean scope | Tạo, nối dependency, quản lý lifecycle; singleton mặc định là một bean instance cho mỗi bean definition trong một container | Trạng thái của bean và dependency được chia sẻ phải thread-safe hoặc stateless |
| TaskExecutor, @Async | Gửi lời gọi qua proxy tới executor đã chọn và trả Future/CompletableFuture nếu contract yêu cầu | Pool, queue, giới hạn tải, từ chối, lỗi, huỷ, timeout, shared state và kết quả cuối |
| TaskScheduler, @Scheduled | Kích hoạt tác vụ theo trigger trong runtime đã cấu hình | Chạy chồng, chạy trùng ở nhiều instance, bỏ lỡ lượt chạy, retry, idempotency và khôi phục |
| @Transactional (imperative) | Áp dụng transaction interceptor và transaction manager trên luồng đang thực thi khi lời gọi đi qua proxy | Transaction boundary, isolation, khóa/phiên bản, conflict và các tác dụng phụ ngoài DB |
| Request/session scope | Quản lý object theo lifetime của request/session khi web context hợp lệ | Không dùng object request sau khi request kết thúc; một session vẫn có thể được truy cập đồng thời |
| TaskDecorator và context-aware adapter | Cơ chế tùy biến việc mang một số execution context vào task | Chọn context hợp lệ để truyền, xóa ThreadLocal sau task, không rò dữ liệu giữa request |
| Lifecycle và shutdown | Hook khởi tạo/hủy, quản lý executor và scheduler, tùy chọn shutdown | Thời hạn chờ, hủy có kiểm soát, lưu trạng thái công việc dở dang, phục hồi sau crash |

Một cơ chế Spring chỉ có hợp đồng khi được **cấu hình và sử dụng đúng đường đi**. @Async không có ý nghĩa nếu annotation bị bỏ qua do self-invocation; @Transactional không tạo transaction cho lời gọi không đi qua interceptor của cấu hình proxy tương ứng.

## 3. Singleton bean có thể bị gọi đồng thời

Singleton là **cùng một object** được dùng lại trong một Spring IoC container, không phải một object riêng cho mỗi request. Ví dụ nguy hiểm:

~~~java
@Service
public class UnsafeCounterService {
    private int value;

    public int next() {
        return ++value;
    }
}
~~~

Đây là đoạn minh họa Spring (các import được bỏ để tập trung vào lỗi). Phép ++ là đọc–tính–ghi, nên hai luồng có thể cùng đọc một giá trị và ghi kết quả trùng. Bean được Spring tạo/inject **không** khiến thao tác này atomic.

Thực hành đúng theo loại dữ liệu:

- **Stateless singleton:** field chủ yếu là dependency hoặc cấu hình immutable; dùng local variables và input/output riêng từng lời gọi. Constructor injection giúp kiểm soát các dependency.
- **Mutable state nội bộ một JVM:** dùng AtomicInteger/AtomicLong, synchronized/Lock, ConcurrentHashMap hay primitive JDK khác theo bất biến cụ thể. volatile hỗ trợ visibility/ordering nhưng **không** biến phép tăng hay chuỗi “nếu chưa có thì thêm” thành một thao tác atomic.
- **Trạng thái bền vững chia sẻ nhiều replica:** đặt invariant ở datastore với transaction, constraint, update có điều kiện, optimistic/pessimistic locking, unique key; khóa trong JVM không bảo vệ các instance khác.
- **Scope khác chưa chắc giải quyết:** prototype tạo object khi được yêu cầu; một prototype được inject một lần vào singleton vẫn có thể bị giữ và chia sẻ. Request scope tách instance giữa request nhưng không biến session/application scope thành thread-safe.

### Ví dụ Java 17+ độc lập: cập nhật atomic

Lưu thành **AtomicCounterDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger counter = new AtomicInteger();
        ExecutorService executor = Executors.newFixedThreadPool(8);
        try {
            List<Future<?>> tasks = new ArrayList<>();
            for (int i = 0; i < 8; i++) {
                tasks.add(executor.submit(() -> {
                    for (int j = 0; j < 1_000; j++) {
                        counter.incrementAndGet();
                    }
                }));
            }
            for (Future<?> task : tasks) {
                task.get();
            }
            System.out.println("Total = " + counter.get());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

~~~bash
javac AtomicCounterDemo.java
java AtomicCounterDemo
~~~

Khi mọi Future hoàn thành thành công, stdout chính xác là:

~~~text
Total = 8000
~~~

Tám task nhân 1.000 phép incrementAndGet atomic tạo 8.000, còn get() chờ tất cả hoàn tất trước khi in. Đây chỉ là **an toàn bộ đếm trong một process**, không phải giải pháp cho tồn kho hoặc số dư lưu trên DB và được nhiều instance cập nhật.

## 4. Điều mà @Async thực sự thực hiện

Khi @EnableAsync (hoặc cấu hình tương đương) có hiệu lực và caller đi qua Spring proxy, @Async nộp công việc cho TaskExecutor phù hợp. Spring lo phần interception và điều phối; executor quyết định thực thi bằng thread pool, virtual thread hoặc cơ chế khác. Một TaskExecutor thậm chí có thể chạy đồng bộ tùy implementation; không được suy ra “mọi @Async luôn tạo thread mới”.

- Lời gọi **this.asyncMethod()** trong cùng instance bỏ qua Spring proxy ở proxy mode mặc định, làm async advice không chạy. Hãy đặt ranh giới gọi giữa các bean hoặc thiết kế để caller dùng bean được Spring inject.
- @Async không tự bảo đảm thứ tự task bắt đầu, thứ tự task kết thúc, bounded queue, timeout, retry hay durable completion. Từng thứ phụ thuộc executor và thiết kế.
- @Async trả Future/CompletableFuture cho phép quan sát kết quả/thất bại bất đồng bộ; get()/join() có thể ném exception dạng wrapper. Với @Async trả void, lỗi không quay về stack của caller; cần AsyncUncaughtExceptionHandler hoặc contract trả Future phù hợp. Lỗi **nộp task** khi pool bị từ chối khác với lỗi **trong task**.
- Một invocation @Async không có nghĩa là được giữ transaction, security context, request context hoặc MDC của caller sang worker thread.

### Ví dụ tích hợp Spring: giới hạn executor, transaction riêng tại worker

Ví dụ này dùng **Java 17+, Spring Framework, spring-jdbc, transaction manager và một DB có bảng inventory(product_id, available)**. Đặt toàn bộ snippet trong tệp **BusinessAsyncConfig.java** thuộc package được component scan; cần ApplicationContext/DataSource/schema/transaction management để thực thi. Đây là ví dụ tích hợp, **không phải** chương trình javac/java độc lập.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Configuration
@EnableAsync
public class BusinessAsyncConfig {
    @Bean("businessExecutor")
    public ThreadPoolTaskExecutor businessExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("business-");
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}

record ReservationCommand(long productId, int quantity) {
    ReservationCommand {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
    }
}

@Service
class ReservationAsyncService {
    private final ReservationTxService transactionService;

    ReservationAsyncService(ReservationTxService transactionService) {
        this.transactionService = transactionService;
    }

    @Async("businessExecutor")
    public CompletableFuture<Boolean> reserveAsync(ReservationCommand command) {
        boolean reserved = transactionService.reserve(command);
        return CompletableFuture.completedFuture(reserved);
    }
}

@Service
class ReservationTxService {
    private final JdbcTemplate jdbc;

    ReservationTxService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean reserve(ReservationCommand command) {
        int updatedRows = jdbc.update(
            "UPDATE inventory SET available = available - ? " +
            "WHERE product_id = ? AND available >= ?",
            command.quantity(), command.productId(), command.quantity()
        );
        return updatedRows == 1;
    }
}
~~~

Phân tích đúng từng ranh giới:

1. **Invocation:** caller từ một bean khác gọi ReservationAsyncService qua proxy; @Async đưa task vào businessExecutor. Self-invocation sẽ không kích hoạt proxy advice.
2. **Dữ liệu đầu vào:** record ReservationCommand bất biến; không truyền EntityManager, HttpServletRequest, connection hoặc object session mutable sang worker.
3. **Transaction:** trong worker, AsyncService gọi **bean khác** là ReservationTxService. @Transactional có hiệu lực qua transaction proxy và mở/tham gia giao dịch theo transaction manager **trên worker thread**; không kế thừa transaction từ HTTP caller.
4. **Bất biến DB:** SQL UPDATE kiểm tra available >= quantity trong cùng statement cập nhật. Khi không thỏa, cập nhật 0 dòng. Các bảo đảm thực tế phụ thuộc DB, schema, constraint và transaction manager. Cần thêm idempotency key để tránh trừ lại nếu cùng command bị retry.
5. **Tài nguyên:** pool cấu hình 4 core, 8 max và queue 100; task vượt sức chứa có thể bị từ chối. Đây là **số liệu minh họa**, cần đo throughput/connection pool/downstream latency trước khi chọn cho sản phẩm. Mã gọi cần chính sách xử lý rejection.
6. **Shutdown:** cho phép chờ task trong giới hạn cấu hình 30 giây; crash, kill hoặc mất điện vẫn có thể làm job chưa xong. Khi yêu cầu bền vững, cần lưu command vào datastore/queue đáng tin cậy.

## 5. Transaction không tự vượt ranh giới thread

Với **imperative transaction** dùng PlatformTransactionManager, Spring thường ràng buộc transaction và resource vào luồng hiện tại. Tạo luồng mới bằng @Async, ExecutorService, CompletableFuture.supplyAsync hoặc new Thread không tự truyền transaction của caller.

~~~text
Thread A (HTTP request)                       Thread B (@Async worker)
@Transaction đặt đơn hàng
  ghi đơn (chưa commit)
  gửi async task ---------------------------> xử lý tiếp, không ở transaction A
  commit / rollback A                        cần transaction riêng khi ghi DB
~~~

Hệ quả:

- Worker có thể chạy **trước commit**. Nó có thể không đọc thấy bản ghi của A hoặc gửi thông báo cho một đơn hàng sau đó bị rollback.
- Nếu worker cần transaction, hãy mở transaction ở worker qua Spring-managed service/interceptor hoặc TransactionTemplate.
- @Transactional không tự ngăn lost update, deadlock hay race ngoài DB; mức isolation mặc định tùy data source/manager. Cần kiểm soát version, lock, unique constraint và retry conflict có giới hạn.
- Email, HTTP call, file và message broker không mặc nhiên nằm chung transaction với DB. Khi cần chuyển trạng thái DB và phát sự kiện bền vững, cân nhắc **transactional outbox** rồi xử lý consumer **idempotent**.
- Với **ReactiveTransactionManager**, ngữ cảnh giao dịch nằm trong Reactor Context, không theo quy tắc ThreadLocal của imperative transaction. Không áp nhầm mô hình giữa hai stack.

## 6. Ngữ cảnh luồng và request không tự được sao chép

RequestContextHolder, SecurityContextHolder theo chiến lược ThreadLocal mặc định, logging MDC, locale và một số resource transaction phụ thuộc context của luồng. Worker thread có thể khác thread gọi và thường được tái sử dụng. Không được giả định task tự nhìn thấy principal, correlation ID, locale hay request object của caller.

- Truyền **tường minh** qua command immutable các dữ liệu nghiệp vụ đã xác thực: orderId, tenantId, correlationId cần thiết.
- Để lan truyền security/tracing/logging context khi thật sự cần, dùng adapter phù hợp, ví dụ security-aware executor, TaskDecorator hoặc cơ chế context propagation tương thích với runtime. Chỉ truyền dữ liệu cho phép; đảm bảo khôi phục/dọn ThreadLocal trong finally để task sau không nhận dữ liệu của task trước.
- Tránh mang request/response/session object sống vào tác vụ kéo dài hơn request. Truyền userId đã kiểm tra cũng không thay thế việc kiểm tra quyền ở thời điểm công việc được thực thi.
- InheritableThreadLocal không phải cách chung để truyền context vào thread pool: pool thường tái sử dụng thread đã được tạo từ trước.

## 7. Scheduler và message listener không bảo đảm exactly-once

@Scheduled/fixedRate/fixedDelay/cron giúp kích hoạt một phương thức trong runtime; nó **không** tự lưu lịch bền vững, khôi phục mọi lượt bị bỏ lỡ hoặc đảm bảo chỉ một JVM trong cluster chạy. Có thể có thực thi chồng lấn tùy cấu hình lịch/executor và bản thân một job có thể được đăng ký ở nhiều instance.

Với job quét đơn hết hạn, luôn hỏi:

1. Nếu job lâu hơn chu kỳ, cơ chế hiện tại có thể chồng lấn hay không? Hành vi của fixedRate, fixedDelay và scheduler được cấu hình thực tế là gì?
2. Khi triển khai ba replica, có ba bản sao cùng quét dữ liệu không?
3. Nếu process chết giữa job, checkpoint nào cho phép tiếp tục?
4. Nếu cùng item được xử lý hai lần, tác động có idempotent không?
5. Có giới hạn batch, timeout, lock/lease, retry hoặc dead-letter handling phù hợp không?

Nếu cần một job duy nhất toàn cluster, dùng lease/lock có vòng đời rõ ràng, scheduler hỗ trợ clustering, hoặc queue/job store thích hợp; local @Scheduled không tự bầu leader. Với message listener, số consumer, thứ tự theo key/partition, ack và redelivery phụ thuộc broker/adapter/configuration. Consumer phải xử lý duplicate, poison message và lỗi một phần theo hợp đồng thực tế.

## 8. Chọn cơ chế bảo vệ đúng bất biến

Ví dụ bất biến: **tồn kho không được âm**.

| Kỹ thuật | Phạm vi hữu ích | Giới hạn |
| --- | --- | --- |
| Immutable input, biến local | Tránh race do chia sẻ biến giữa những request | Không ngăn hai DB transaction cùng cập nhật |
| AtomicInteger/synchronized | Một giá trị hoặc critical section trong **một JVM** | Không đồng bộ nhiều replica |
| ConcurrentHashMap | Các thao tác collection được API bảo đảm; compute/merge có thể hỗ trợ cập nhật nguyên tử theo key | Không biến quy trình nhiều bước/đa tài nguyên thành một transaction |
| SQL UPDATE có điều kiện | Điều kiện kiểm tra và cập nhật cùng statement trong DB | Không tự chống retry trùng logic của cùng operation |
| Unique constraint + idempotency key | Chặn command/order trùng theo khóa nghiệp vụ | Cần thiết kế response, hiệu lực khóa và trạng thái retry |
| Optimistic locking/version | Phát hiện concurrent update conflict | Caller phải xử lý exception/retry có giới hạn |
| Transactional outbox + queue | Ghi ý định phát sự kiện cùng DB transaction, phục hồi tiến trình phát | Consumer vẫn có thể nhận lặp và phải idempotent |

**Nguyên tắc:** Bất biến phải được bảo vệ ở tầng có quyền kiểm soát tất cả các bên cập nhật nó. Mutex trong một Spring singleton không bảo vệ tồn kho khi hai replica cùng ghi một DB. Transaction DB không tự làm cuộc gọi gửi email trở thành atomic với câu lệnh UPDATE.

## 9. Giới hạn tài nguyên và khi bị quá tải

Concurrency làm tăng khả năng xử lý nhiều công việc chờ I/O, nhưng cũng dùng CPU, memory, connection pool, lock và quota của dịch vụ bên ngoài. MaxPoolSize lớn không khắc phục được DB pool nhỏ hoặc API bên ngoài đã đến giới hạn.

- **Pool và queue:** giới hạn rõ; queue dài có thể tăng latency và chiếm memory. Với ThreadPoolExecutor, cách queue nhận task ảnh hưởng thời điểm executor tăng số worker đến max; hiểu cấu hình queue trước khi tăng maxPoolSize.
- **Backpressure/rejection:** xác định cách caller xử lý khi không nhận thêm task: trả trạng thái quá tải, retry có backoff/jitter, hay ghi vào durable queue; tránh retry vô hạn.
- **Timeout và cancel:** đặt deadline cho I/O, DB và tác vụ; hủy Future không tự đảo ngược các tác dụng phụ đã hoàn thành. Đóng resource bằng finally/try-with-resources.
- **Shutdown:** dừng nhận việc, chờ trong giới hạn, lưu checkpoint, tái xử lý việc dở. Graceful shutdown không giải quyết sự cố đột ngột.
- **Virtual threads:** có thể giảm overhead của nhiều công việc blocking tương thích, nhưng không biến shared mutable state thành thread-safe, cũng không làm tăng số connection DB hoặc quota remote API.

Theo dõi active task, queue depth, rejection count, queue wait time, task duration, timeout, retry, downstream latency, DB connection pool usage. Những số liệu này giúp lựa chọn chính sách có bằng chứng thay vì suy diễn từ annotation.

## 10. Tình huống trước và sau

### A. Bộ đếm của dịch vụ singleton

**Trước:** int total++ trong @Service; hai request có thể làm mất lần cộng. @Transactional không chữa race của Java field.

**Sau:** nếu chỉ là metric nội bộ một JVM, dùng AtomicLong hoặc metrics library; nếu là điểm thưởng lưu bền và được nhiều replica cập nhật, đặt điều kiện/constraint và logic cập nhật trong DB, xử lý optimistic conflict/retry theo invariant.

### B. Đặt hàng rồi gửi email @Async

**Trước:** request tạo đơn trong transaction A rồi gọi @Async gửi email. Worker có thể gửi email trước khi A commit; A rollback vẫn để lại email.

**Sau:** ghi sự kiện “OrderCommitted” vào transactional outbox cùng transaction A; worker chỉ đọc sự kiện đã commit, gửi email rồi lưu trạng thái. Nếu worker crash sau khi gửi nhưng trước khi đánh dấu, sự kiện có thể được chạy lại: phải có idempotency key/cơ chế dedupe hoặc chấp nhận chính sách gửi trùng đã xác định. Spring cung cấp thành phần lập trình, còn quy tắc đúng của hệ thống do nghiệp vụ quyết định.

## 11. Kiểm chứng bằng concurrency và failure test

1. Đọc cấu hình thật: số bean, bean scope, executor được dùng, pool/queue/rejection, scheduler, proxy, transaction manager, số instance và shutdown policy.
2. Dùng CountDownLatch/CyclicBarrier để tạo tình huống hai hoặc nhiều worker cùng tranh chấp; assert invariant, đừng chỉ dùng Thread.sleep và hi vọng race xuất hiện.
3. Kiểm thử tích hợp với **transaction và connection DB thật**, nhiều caller song song; xác minh không âm tồn kho, không tạo trùng order và xử lý optimistic conflict/deadlock.
4. Giả lập rollback caller, executor rejection, timeout, crash/restart, message redelivery và retry trùng; kiểm tra kết quả cuối cùng cùng trạng thái phục hồi.
5. Kiểm tra context được mang đúng đối tượng, không lộ giữa task trong thread pool; log correlation ID và metric saturation quan sát được.

## 12. Checklist thiết kế

- Tôi đã nêu chính xác invariant nghiệp vụ và dữ liệu nào có thể bị nhiều luồng/instance cập nhật.
- Bean singleton là stateless hoặc bảo vệ mọi shared mutable state theo mô hình concurrency đã chọn.
- Phạm vi bảo vệ nằm ở tầng đúng: JVM, DB, queue hoặc coordinator phân tán.
- @Async và @Transactional thực sự đi qua proxy; không phụ thuộc self-invocation.
- Worker có transaction và dữ liệu đầu vào riêng; không dùng nhầm transaction/request context của caller.
- Executor/scheduler có giới hạn, chính sách thất bại và vận hành khi restart/shutdown.
- Công việc có thể retry/duplicate được thiết kế idempotent khi cần.
- Concurrency test, failure test và metric xác nhận được các giả định trên.

**Ghi nhớ:** Spring quản lý **cách bean và tác vụ được tạo, gọi và thực thi theo cấu hình**. Mã nghiệp vụ phải bảo đảm **kết quả chính xác, nhất quán và có thể phục hồi** trước tranh chấp, quá tải và lỗi. Không có một annotation nào thay thế được thiết kế bất biến.

## Tài liệu tham khảo chính thức

- Spring Framework – Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework – Bean Scopes: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework – Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework – Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Java Language Specification 17, Chapter 17 – Threads and Locks: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html