# Ngăn tái sử dụng nhầm ngữ cảnh khi dùng bộ luồng

## 1. Tình huống mở đầu: một luồng xử lý hai tổ chức khác nhau

Trong hệ thống SaaS đa tổ chức (multi-tenancy), mỗi request hoặc công việc nền phải đọc và ghi **đúng dữ liệu của tổ chức được phép**. Một ứng dụng Spring + Hibernate có thể định tuyến database/schema hoặc thêm điều kiện `tenant_id` dựa vào ngữ cảnh tổ chức hiện tại.

Giả sử hệ thống dùng `ThreadLocal<String>` để ghi tenant ID:

```java
public final class TenantContext {
    private static final ThreadLocal<String> CURRENT =
        new ThreadLocal<>();

    public static void set(String tenantId) {
        CURRENT.set(tenantId);
    }

    public static String get() {
        return CURRENT.get();
    }

    public static void clear() {
        CURRENT.remove();
    }
}
```

Một worker:

```java
executor.execute(() -> {
    TenantContext.set("tenant-A");
    importOrders();
    // Quên clear().
});
```

Sau đó thread pool dùng lại **chính thread cũ** để chạy tác vụ tenant B:

```java
executor.execute(() -> {
    // Không set tenant vì code nghĩ tác vụ không cần.
    generateReport();
});
```

Nếu `generateReport()` đọc `TenantContext.get()` và thấy `tenant-A`, nó có thể truy cập dữ liệu A dù tác vụ mới thuộc B hoặc không được chọn tenant nào.

```text
Pooled thread: worker-1
  |
  +-- Job 1: Tenant A
  |     set ThreadLocal = A
  |     query schema A
  |     return; KHÔNG clear
  |
  +-- Job 2: Tenant B
        quên set context
        get ThreadLocal = A  <-- RÒ NGỮ CẢNH
        query schema A       <-- CÓ THỂ RÒ DỮ LIỆU
```

**Chủ đề của bài** không chỉ là nhớ gọi `ThreadLocal.remove()`. Một giải pháp đúng còn phải bảo đảm:

- Tenant identity lấy từ nguồn đáng tin và được kiểm quyền.
- Tenant context được xác định **trước khi mở Hibernate Session/transaction hoặc lấy JDBC connection**.
- Ngữ cảnh được ràng buộc theo **một tác vụ**, không theo vòng đời thread trong pool.
- Mọi exit path (thành công, exception, timeout, cancel) đều dọn đúng context.
- Không truyền `Session`, `EntityManager` hoặc transaction resources giữa threads.
- Connection pool trả connection về trạng thái an toàn khi release.
- Cache, native SQL, background jobs và truy vấn by-ID không phá cách ly tenant.
- Kiểm thử có chủ đích tình huống **tenant A rồi tenant B trên cùng worker thread**.

## 2. “Nhiều tổ chức” là gì trong Hibernate?

Multi-tenancy là một ứng dụng phục vụ nhiều khách hàng/tổ chức nhưng phải cô lập dữ liệu và quyền truy cập.

Ba mô hình lưu trữ thường gặp:

| Mô hình | Đặc điểm | Rủi ro khi dùng sai tenant context |
|---|---|---|
| **Database-per-tenant** | Mỗi tổ chức có database riêng | Lấy sai DataSource/connection và đọc toàn bộ DB tenant khác |
| **Schema-per-tenant** | Nhiều schema trên cùng database | Dùng sai `schema` / `search_path` của connection |
| **Shared-table/discriminator** | Nhiều tenant dùng chung bảng, có `tenant_id` | Quên hoặc dùng sai tenant predicate, đọc chéo hàng |

Không có mô hình nào tự giải quyết tất cả lỗi ứng dụng. Database/schema riêng tạo ranh giới vật lý rõ hơn nhưng vẫn có thể chọn nhầm nguồn dữ liệu. Shared-table cần tenant restriction nhất quán trên mọi đường query/mutation, có thể bổ sung database Row-Level Security (RLS).

### Ví dụ shared-table

```sql
CREATE TABLE invoices (
    tenant_id VARCHAR(64) NOT NULL,
    invoice_id BIGINT NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (tenant_id, invoice_id)
);

INSERT INTO invoices VALUES
    ('tenant-A', 1001, 500000),
    ('tenant-B', 1001, 900000);
```

Hai hóa đơn có thể có cùng invoice ID nhưng thuộc hai tổ chức. Dùng `invoiceId` đơn lẻ mà không kiểm tra tenant có thể truy cập nhầm đối tượng.

## 3. Những loại context dễ bị nhầm

| Context | Phạm vi/thành phần | Có nên sao chép qua executor? |
|---|---|---|
| **Tenant ID** | Định danh tổ chức dùng để routing/authorization | Truyền **giá trị đáng tin**, thiết lập lại theo task |
| **Hibernate Session** | Persistence Context, identity map, pending changes | **Không** |
| **EntityManager thực** | Context quản lý entities | **Không** |
| **Spring transaction context** | Bound connection, synchronization, commit/rollback | **Không** |
| **JDBC Connection** | Kết nối và trạng thái schema/DB session | **Không** |
| **SecurityContext** | Authentication/authorities | Chỉ qua cơ chế bảo mật được thiết kế; không tự sao chép mù |
| **MDC/trace context** | Correlation ID, trace/span | Có thể propagate bằng thư viện/decorator thích hợp |
| **Job metadata** | jobId, tenantId, actorId, retry attempt | Nên lưu/truyền explicit |

Một nhiệm vụ của tenant A không phải một đối tượng Java có thể “mang toàn bộ request context” qua mọi thread. Những gì cần giữ là **định danh và điều kiện thực thi**, còn resources phải được khởi tạo trong unit of work của worker.

## 4. Vì sao ThreadLocal không phải bộ nhớ riêng cho từng task?

`ThreadLocal` gắn một giá trị với một **Java Thread**, không gắn với một `Runnable` hoặc `CompletableFuture`.

Ở thread pool:

```text
Thread worker-1 sống nhiều giờ
  Runnable A chạy 20 ms
  Runnable B chạy 50 ms
  Runnable C chạy 10 ms
```

Nếu A set ThreadLocal mà không remove, B/C có thể thấy giá trị của A.

### Không chỉ là giá trị stale

Một ThreadLocal có thể giữ reference đến:

- Tenant ID.
- Request DTO, principal hoặc tenant config object.
- Một Map chứa nhiều thông tin request.
- Classloader/objects có vòng đời dài.

Trong long-lived pooled threads, reference bị giữ lâu có thể gây **memory retention**. Nguy hiểm nhất với multi-tenancy là stale tenant identity trở thành **lựa chọn định tuyến hoặc điều kiện truy cập dữ liệu sai**.

### Đừng dùng null làm một “tenant mặc định”

Nếu resolver trả `null` rồi hệ thống âm thầm chọn `tenant-A` hoặc public schema, một tác vụ thiếu context có thể chạy trên tenant không mong muốn.

Đối với đường ghi/đọc nhạy cảm, **thiếu tenant phải fail closed**, trừ khi đây là một thao tác system-wide có quyền và API riêng, được thiết kế rõ.

## 5. Ví dụ lỗi: exception khiến tenant context còn sót

Code:

```java
public void execute(ImportJob job) {
    TenantContext.set(job.tenantId());

    importCsv(job); // Có thể ném RuntimeException.

    TenantContext.clear();
}
```

Nếu `importCsv` ném exception thì `clear` **không chạy**.

Đúng hơn:

```java
public void execute(ImportJob job) {
    TenantContext.set(job.tenantId());
    try {
        importCsv(job);
    } finally {
        TenantContext.clear();
    }
}
```

`finally` chạy cả khi method return bình thường hoặc ném exception thông thường. Dù vậy, nó không giải quyết trường hợp task đã mở Session/connection **trước** khi set tenant, và không thay thế xử lý crash/kill process, vì process dừng thì cũng không tiếp tục tasks.

### Nên kiểm thử với lỗi thật

Hãy seed task A chủ động ném exception rồi task B chạy trên cùng thread trong pool 1 worker. Nếu B thấy tenant A, cleanup đang sai.

## 6. Dùng Scope để đóng/mở tenant context có cấu trúc

Một API scope gọn giúp caller ít quên cleanup:

```java
import java.util.Objects;

public final class TenantContext {

    private static final ThreadLocal<String> CURRENT =
        new ThreadLocal<>();

    private TenantContext() {}

    public static String requireCurrent() {
        String id = CURRENT.get();
        if (id == null || id.isBlank()) {
            throw new IllegalStateException(
                "Tenant context is missing"
            );
        }
        return id;
    }

    public static String peek() {
        return CURRENT.get();
    }

    public static Scope use(String tenantId) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant ID required");
        }

        String previous = CURRENT.get();
        CURRENT.set(tenantId);

        return () -> {
            if (previous == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(previous);
            }
        };
    }

    public static void clear() {
        CURRENT.remove();
    }

    @FunctionalInterface
    public interface Scope extends AutoCloseable {
        @Override
        void close();
    }
}
```

Sử dụng:

```java
try (TenantContext.Scope ignored =
        TenantContext.use(trustedTenantId)) {
    workerService.process(jobId);
}
```

Khi rời block, `close()` khôi phục giá trị trước đó hoặc remove nếu trước đó chưa có context.

### Lưu ý quan trọng về nested scopes

Việc **khôi phục previous** hữu ích nếu application có nested scopes hợp lệ. Nhưng nó cũng có thể **khôi phục một tenant stale vốn đã nằm sẵn trên pooled thread**.

Vì vậy, ở **ranh giới ngoài cùng của mỗi executor task**, cần thêm chính sách:

- Phát hiện tenant context tồn đọng đầu task là lỗi hoặc cảnh báo quan trọng.
- Chỉ lấy tenant từ payload/context hợp lệ của tác vụ mới.
- Xóa tenant context ở `finally` cuối task, kể cả khi xử lý lỗi.
- Không tiếp tục dùng “previous” không đáng tin như tenant của job tiếp theo.

Scope là cấu trúc ngôn ngữ hỗ trợ cleanup; tính đúng phụ thuộc vào **lifecycle boundary** được thiết kế.

## 7. Ranh giới ngoài cùng của worker phải sạch

Một wrapper xử lý rõ từng job:

```java
public final class TenantJobBoundary {

    private final TenantWorkerService workerService;

    public TenantJobBoundary(TenantWorkerService workerService) {
        this.workerService = workerService;
    }

    public void run(TrustedJob job) {
        String tenantId = job.tenantId();

        if (TenantContext.peek() != null) {
            // Cảnh báo/metric về context tồn đọng.
            // Không dùng lại tenant cũ.
            TenantContext.clear();
        }

        try (TenantContext.Scope ignored =
                TenantContext.use(tenantId)) {
            workerService.process(job.id());
        } finally {
            // Ranh giới task ngoài cùng: dọn cả trong error path.
            TenantContext.clear();
        }
    }
}
```

`TrustedJob` đại diện payload đã xác thực từ kho job/queue; `tenantId` không được lấy tùy tiện từ input của người khác.

### Vì sao vừa use() vừa clear()?

`use()` hỗ trợ cấu trúc scope và nested calls. `clear()` cuối outer boundary bảo đảm pooled thread không mang tenant sang **task kế tiếp**.

Nếu hệ thống của bạn có executor/task wrappers lồng nhau thực sự cần duy trì outer context, phải định nghĩa lifecycle chính xác, không xóa context của parent khi parent vẫn chạy. Quy tắc **clear tại outermost task boundary** áp dụng khi worker thread đang hoàn tất một task độc lập.

## 8. Cẩn thận: tenant phải có trước khi transaction/Session được mở

Code sai:

```java
@Transactional
public void runJob(TrustedJob job) {
    TenantContext.set(job.tenantId());

    // Transaction advice có thể đã mở/bind EntityManager
    // hoặc connection trước khi vào thân method.
    repository.findAll();
}
```

Trong Spring proxy mode, transaction interceptor chạy **trước method body**. Tùy transaction manager, việc tạo/bind EntityManager hoặc lấy JDBC connection có thể đã diễn ra với tenant context thiếu hoặc stale.

Hậu quả:

- Hibernate Session được tạo với tenant sai.
- `CurrentTenantIdentifierResolver` trả tenant cũ.
- Routing DataSource đã chọn DB sai.
- JDBC connection đã đặt schema sai.

**Không coi việc set ThreadLocal ở dòng đầu thân method `@Transactional` là luôn đủ sớm.**

### Mẫu đúng: đặt context ở bean ngoài, gọi bean transactional phía trong

```text
TenantJobBoundary (không @Transactional)
    |
    |-- xác thực tenant
    |-- TenantContext.use(tenant)
    |
    v
TenantWorkerService (@Transactional, Spring proxy)
    |
    |-- tạo/bind EntityManager theo tenant
    |-- lấy Connection đúng
    |-- query và commit
    |
    v
return -> close Scope -> clear
```

## 9. Mẫu Spring đầy đủ: dispatcher + transactional worker

DTO:

```java
public record TrustedJob(
    long id,
    String tenantId,
    String requestedByUserId
) {}
```

Boundary:

```java
@Service
public class TenantJobDispatcher {

    private final TenantTransactionalWorker worker;

    public TenantJobDispatcher(TenantTransactionalWorker worker) {
        this.worker = worker;
    }

    public void dispatch(TrustedJob job) {
        String tenantId = job.tenantId();
        // Kiểm tra chữ ký/nguồn và quyền truy cập job ở tầng phù hợp.

        try (TenantContext.Scope ignored =
                TenantContext.use(tenantId)) {
            worker.process(job.id());
        } finally {
            TenantContext.clear();
        }
    }
}
```

Worker:

```java
@Service
public class TenantTransactionalWorker {

    private final InvoiceRepository repository;

    public TenantTransactionalWorker(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void process(long jobId) {
        String tenantId = TenantContext.requireCurrent();

        List<Invoice> invoices =
            repository.findPendingForTenant(tenantId);

        for (Invoice invoice : invoices) {
            invoice.markProcessed();
        }
    }
}
```

Mẫu giả định `InvoiceRepository.findPendingForTenant` là repository method có tenant predicates hoặc Hibernate tenancy routing phù hợp, `Invoice.markProcessed()` được domain định nghĩa.

### Lý do tách hai beans

`TenantJobDispatcher.dispatch` **không transactional**: nó đặt tenant trước.

`TenantTransactionalWorker.process` là bean khác: lời gọi qua Spring proxy mở transaction sau khi tenant đã hiện diện.

`TenantContext.clear` được gọi sau khi transaction method đã return hoặc throw; tức là sau transaction completion bình thường.

Trong production, cần thêm outermost thread cleanup và xử lý job failure/retry. Không chia một entity manager hoặc transaction từ caller sang worker.

## 10. Self-invocation và rủi ro không đi qua Spring proxy

Sai:

```java
@Service
public class TenantJobService {

    public void start(TrustedJob job) {
        try (var ignored = TenantContext.use(job.tenantId())) {
            this.process(job.id());
        }
    }

    @Transactional
    public void process(long id) {
        // Có thể không mở transaction do self-invocation.
    }
}
```

Với Spring AOP proxy mode mặc định, `this.process(...)` không đi qua proxy nên `@Transactional` có thể bị bỏ qua.

Tương tự, `this.processAsync(...)` có thể bỏ qua `@Async`.

Giải pháp ưu tiên:

- Dispatcher bean.
- Worker bean riêng, được inject qua Spring.
- Transaction annotation trên method được gọi qua proxy.
- Integration test xác nhận transaction đang active và tenant đúng.

Không tự tạo service bằng `new` rồi kỳ vọng annotations được Spring intercept.

## 11. @Async chạy ở thread khác: không mang theo tenant ThreadLocal

Ví dụ:

```java
@Transactional
public void acceptInvoice(long invoiceId, String tenantId) {
    TenantContext.set(tenantId);
    asyncWorker.processAsync(invoiceId);
}
```

Ngay cả khi request thread có tenant đúng, `@Async` thường chạy trên thread của executor:

```text
http-1:  TenantContext = tenant-A
worker-7: TenantContext = null hoặc stale tenant-B
```

Không có contract mặc định rằng `ThreadLocal` của caller được copy sang worker.

### Đừng truyền live Hibernate objects

```java
asyncWorker.processAsync(managedInvoice); // Không khuyến khích.
```

Entity có thể detached khi request kết thúc; lazy properties có thể fail; Session và EntityManager không thread-safe.

Thay bằng:

```java
asyncWorker.processAsync(
    new InvoiceJobCommand(invoiceId, trustedTenantId)
);
```

Worker dùng command để tạo context và **nạp entity lại trong transaction mới**.

## 12. Mẫu @Async với tenant boundary ở đúng vị trí

Outer async bean:

```java
public record InvoiceJobCommand(
    long invoiceId,
    String tenantId,
    long jobId
) {}

@Service
public class InvoiceAsyncWorker {

    private final TenantInvoiceProcessor processor;

    public InvoiceAsyncWorker(TenantInvoiceProcessor processor) {
        this.processor = processor;
    }

    @Async("tenantExecutor")
    public CompletableFuture<Void> processAsync(
            InvoiceJobCommand command) {

        try (TenantContext.Scope ignored =
                TenantContext.use(command.tenantId())) {
            processor.process(command.invoiceId(), command.jobId());
            return CompletableFuture.completedFuture(null);
        } finally {
            TenantContext.clear();
        }
    }
}
```

Transactional inner bean:

```java
@Service
public class TenantInvoiceProcessor {

    private final InvoiceRepository repository;

    public TenantInvoiceProcessor(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void process(long invoiceId, long jobId) {
        String tenantId = TenantContext.requireCurrent();

        Invoice invoice =
            repository.findByTenantIdAndId(tenantId, invoiceId)
                .orElseThrow();

        invoice.markProcessed(jobId);
    }
}
```

Đây là một mẫu cho **in-process async**. Nó không đảm bảo task đã được lưu bền vững sau khi process crash. Đối với công việc không được phép thất lạc, dùng durable job table/queue hoặc transactional outbox.

### Điều kiện đúng

- `@EnableAsync` và named executor đã cấu hình.
- Method `@Async` được gọi qua Spring proxy từ bean khác.
- Tenant ID từ command đáng tin hoặc đã được kiểm quyền.
- Không có transaction/Session được mở trước `TenantContext.use`.
- Worker transactional không share Session với caller.
- Có cleanup ở finally kể cả khi exception.

## 13. Cấu hình ThreadPoolTaskExecutor có giới hạn

Ví dụ:

```java
@Configuration
@EnableAsync
public class TenantAsyncConfig {

    @Bean("tenantExecutor")
    public ThreadPoolTaskExecutor tenantExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("tenant-worker-");
        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy()
        );
        executor.initialize();
        return executor;
    }
}
```

Imports minh họa:

```java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
```

Tại sao cần bounded pool?

1. Mỗi worker transaction có thể giữ một DB connection.
2. Worker quá nhiều có thể cạn HikariCP pool và gây chờ cho request chính.
3. Một tenant lớn có thể gây nghẽn các tenant nhỏ.
4. Queue quá lớn làm backlog khó kiểm soát.
5. Executor queue chỉ ở bộ nhớ, không durable.

`corePoolSize=4`, `maxPoolSize=8` và `queueCapacity=100` là **giá trị minh họa**, cần chỉnh theo database/connection capacity và service-level objectives.

## 14. TaskDecorator: truyền metadata có kiểm soát

Spring `TaskDecorator` cho phép bọc task được executor chạy. Nó có thể capture tenant ID tại thời điểm submit, thiết lập tenant đúng trong worker, rồi cleanup.

Mẫu minh họa:

```java
executor.setTaskDecorator(task -> {
    String capturedTenant = TenantContext.peek();

    return () -> {
        // Task boundary là nơi xóa mọi context tồn đọng.
        if (TenantContext.peek() != null) {
            // Ghi metric/cảnh báo về stale state.
            TenantContext.clear();
        }

        try {
            if (capturedTenant != null) {
                try (TenantContext.Scope ignored =
                        TenantContext.use(capturedTenant)) {
                    task.run();
                }
            } else {
                task.run(); // Worker phải fail closed nếu cần tenant.
            }
        } finally {
            TenantContext.clear();
        }
    };
});
```

Đoạn code phải được thêm **trước `executor.initialize()`** trong bean configuration.

### Ưu điểm

- Giúp propagate một giá trị tenant đã xác thực qua một executor đã được quản lý.
- Không truyền EntityManager/connection/transaction.
- Có cleanup kể cả khi task ném exception.
- Thích hợp khi nhiều lời gọi `@Async` hợp lệ đều cần cùng policy.

### Giới hạn và trade-off

- Chỉ có tác dụng với những tasks **thực sự chạy qua executor được trang trí**.
- Không bao phủ `CompletableFuture.supplyAsync(...)` dùng common pool nếu không truyền executor.
- Không bao phủ tự tạo `new Thread(...)` hoặc executor khác.
- Capture ThreadLocal tại submit có thể sai nếu caller context đã stale.
- Với background job được lấy từ persistent queue, tenant nên đến từ **job record đáng tin**, không phải từ ngữ cảnh tình cờ của dispatcher.
- Một task không có tenant không nên tự chọn tenant mặc định.

Đây là giải pháp propagation cho **trusted per-task metadata**, không phải toàn bộ isolation policy.

## 15. Chọn nơi thiết lập tenant: decorator hay command?

Hai cách thường gặp:

| Cách | Nguồn tenant | Phù hợp |
|---|---|---|
| TaskDecorator capture context | Tenant trên submitter thread | In-process handoff từ request đã xác thực |
| Job command + outer worker boundary | `tenantId` trong payload/job record đáng tin | Queue, scheduled job, retry sau restart, distributed workers |

**Không nên bật cả hai một cách mù quáng** nếu một task có thể nhận hai tenant khác nhau.

Ví dụ:

```text
Submitter ThreadLocal = tenant-A
Job payload tenantId = tenant-B
```

Nếu decorator set A nhưng worker command set B, phải coi đó là một **conflict** cần phát hiện/ghi log chứ không lặng lẽ đổi qua đổi lại. Xác định **một nguồn sự thật** cho mỗi loại task và assert sự nhất quán.

Trong durable job, ưu tiên tenant trong job row đã được tạo/ủy quyền hợp lệ và kiểm tra lại khi claim.

## 16. Không dùng InheritableThreadLocal cho worker pool

`InheritableThreadLocal` sao chép giá trị từ parent thread **khi tạo child thread**, không phải khi submit **mỗi task**.

Trong thread pool:

```text
Pool tạo worker-1 lúc tenant-A đang active
  -> worker-1 có thể thừa hưởng A

Sau đó:
  submit job B
  submit job C
  -> worker-1 vẫn có giá trị đã thừa hưởng
```

Nó có thể làm leak khó đoán hơn vì worker thread được khởi tạo vào thời điểm khác với xử lý task.

Không coi `InheritableThreadLocal` là cơ chế truyền tenant an toàn cho pool, `@Async` hoặc async pipelines.

### Tương tự với CompletableFuture

```java
CompletableFuture.supplyAsync(() -> loadInvoices());
```

thường dùng common `ForkJoinPool` nếu không truyền executor. Không có bảo đảm tenant của caller được chuyển qua, và task chạy trong một pool ngoài chính sách bạn quản lý.

Nếu thật sự cần in-process async:

```java
CompletableFuture.supplyAsync(
    () -> runWithTrustedTenant(command),
    tenantExecutor
);
```

Đảm bảo wrapper thiết lập/cleanup tenant trong task; không chỉ truyền một executor bất kỳ là đủ.

## 17. Virtual threads không xóa nhu cầu tenant scope

Với virtual threads trên các Java/Spring versions hỗ trợ, mỗi task có thể có virtual thread riêng thay vì dùng lại platform thread theo cùng cách một fixed pool hoạt động.

Điều này thay đổi mô hình reuse, nhưng:

- Context vẫn phải được thiết lập đúng trước Session/transaction.
- Không chuyển transaction và EntityManager giữa threads.
- Job payload phải có tenant đáng tin.
- Missing tenant vẫn phải fail closed.
- Executor/connection pool và database capacity vẫn hữu hạn.
- Các thư viện có thể dùng ThreadLocal hoặc context propagation với semantics cần kiểm tra.

Không diễn giải “dùng virtual threads” thành “multi-tenancy tự an toàn”.

## 18. @Scheduled không có tenant request nào để kế thừa

Một tác vụ định kỳ:

```java
@Scheduled(fixedDelay = 60_000)
public void expireInvoices() {
    // Scheduler không phải HTTP request của tenant cụ thể.
}
```

Nếu muốn xử lý mọi tenant, phải thiết kế **một vòng lặp điều phối tenants hợp lệ**:

```java
@Component
public class InvoiceExpirationScheduler {

    private final TenantRegistry tenantRegistry;
    private final TenantJobDispatcher dispatcher;

    @Scheduled(fixedDelay = 60_000)
    public void run() {
        for (String tenantId : tenantRegistry.activeTenantIds()) {
            TrustedJob job =
                tenantRegistry.createExpirationJob(tenantId);
            dispatcher.dispatch(job);
        }
    }
}
```

Ví dụ giả định `TenantRegistry` và `createExpirationJob` là services có quyền truy xuất danh sách tenants và tạo job. Không truy vấn một tenant DB trước khi tenant context đã được thiết lập, và không thực hiện transaction dài bao toàn bộ tenants.

### Tách transaction theo tenant

```text
Scheduler:
  tenant A -> transaction A -> commit -> cleanup
  tenant B -> transaction B -> commit -> cleanup
  tenant C -> transaction C -> commit -> cleanup
```

Không mang cùng Hibernate Session qua ba tenants. Tại mỗi lần, tenant được chọn trước khi tạo Session/connection.

## 19. Message consumers và tenant context

Consumer:

```java
@KafkaListener(topics = "invoice-jobs")
public void handle(InvoiceJobMessage message) {
    // Không có HTTP request context.
}
```

Trong một message consumer, tenant phải đến từ:

- Trusted event envelope đã được kiểm chứng.
- Message/job record lấy từ nguồn có phân quyền.
- Aggregate lookup có kiểm soát hoặc routing metadata tin cậy.

Không tự tin rằng header `tenantId` luôn đáng tin nếu producer không được xác thực hoặc topic cho phép bên ngoài gửi thông điệp.

### Mẫu xử lý

```java
public void handle(InvoiceJobMessage message) {
    TrustedJob job = jobService.loadAndAuthorize(message.jobId());

    try (TenantContext.Scope ignored =
            TenantContext.use(job.tenantId())) {
        transactionalWorker.process(job.id());
    } finally {
        TenantContext.clear();
    }
}
```

Nếu Kafka listener được annotate `@Transactional` ngay trên method và transaction bắt đầu **trước khi set tenant**, có thể mở sai context. Tách outer message handler không transactional với inner transactional service rõ ràng.

## 20. HTTP request: tenant phải được thiết lập từ nguồn đáng tin

Một anti-pattern:

```java
String tenantId = request.getHeader("X-Tenant-Id");
TenantContext.set(tenantId);
```

Client có thể tự sửa header. Nếu dữ liệu routing chỉ dựa vào giá trị này, kẻ tấn công có thể đổi tenant.

Một cách phù hợp hơn:

1. Xác thực request.
2. Lấy tenant membership/claim được xác thực hoặc route mapping đáng tin.
3. Kiểm tra người dùng có quyền thao tác tenant được yêu cầu.
4. Thiết lập tenant context trước khi repository/transaction mở.
5. Dọn ở `finally` khi request lifecycle hoàn tất.

### Filter minh họa

```java
@Component
public class TenantRequestFilter extends OncePerRequestFilter {

    private final TenantAuthorizationService authorization;

    public TenantRequestFilter(
            TenantAuthorizationService authorization) {
        this.authorization = authorization;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String tenantId =
            authorization.resolveAuthorizedTenant(request);

        try (TenantContext.Scope ignored =
                TenantContext.use(tenantId)) {
            chain.doFilter(request, response);
        } finally {
            TenantContext.clear();
        }
    }
}
```

`TenantAuthorizationService.resolveAuthorizedTenant` là **helper giả định**, phải kiểm quyền thật bằng authenticated identity, không đơn giản trả header từ request.

### Filter order và async servlet

Tenant filter phải chạy trước điểm tạo EntityManager/connection hoặc truy cập persistence. Một số ứng dụng có Open EntityManager in View (OSIV), security filters hoặc asynchronous servlet dispatch khiến thứ tự/lifecycle phức tạp hơn.

Với servlet async dispatch và tasks được chạy ở thread khác, **không coi một doFilterInternal trên request thread là đủ cho mọi worker**; dùng async task boundary/context propagation có kiểm soát và kiểm thử filter dispatch configuration.

## 21. Hibernate tenant resolver lấy tenant bằng cách nào?

Trong Hibernate có cơ chế `CurrentTenantIdentifierResolver` để xác định tenant ID hiện hành khi tạo/tra cứu Session theo configuration.

Ví dụ ý tưởng:

```java
import org.hibernate.context.spi.CurrentTenantIdentifierResolver;

public final class ThreadTenantResolver
        implements CurrentTenantIdentifierResolver<String> {

    @Override
    public String resolveCurrentTenantIdentifier() {
        return TenantContext.requireCurrent();
    }

    @Override
    public boolean validateExistingCurrentSessions() {
        return true;
    }
}
```

Kiểu generic và cách đăng ký resolver phụ thuộc Hibernate ORM version/bootstrapping setup; ví dụ này dành cho những phiên bản dùng `CurrentTenantIdentifierResolver<String>`.

### Giới hạn cần nhớ

- Resolver **không tự xác thực** tenant.
- Resolver chỉ đọc tenant do ứng dụng cung cấp/đã chuẩn bị.
- Nếu ThreadLocal còn tenant cũ, resolver cũng trả tenant cũ.
- Đổi ThreadLocal sau khi Session đã tạo không có nghĩa Session tự chuyển DB/schema.
- Một số Session được tạo với explicit tenant ID, không nhất thiết đọc resolver như mọi đường bootstrapping.

**Resolver không sửa một lifecycle context sai.** Nó chỉ là mắt xích chuyển tenant đã được xác định sang Hibernate.

## 22. validateExistingCurrentSessions() không phải kiểm tra quyền

`validateExistingCurrentSessions()` cho Hibernate biết có cần kiểm tra tenant ID đang yêu cầu với một current Session đã tồn tại trong current-session context hay không (theo contract cụ thể của version).

Nó có thể giúp phát hiện một số trường hợp cố dùng cùng current Session với tenant ID khác.

Tuy nhiên:

- Không phải authorization.
- Không kiểm tra user thuộc tenant hay không.
- Không bao quát tất cả `openSession()` hoặc EntityManager lifecycles.
- Không bảo đảm ThreadLocal luôn được cleanup.
- Không thay thế tests với thread pool và Session reuse.

Đừng bật `validateExistingCurrentSessions=true` rồi tuyên bố hệ thống đã chống cross-tenant access.

## 23. Cấu hình Hibernate multitenancy khác tùy đời phiên bản

Hibernate ORM có nhiều cách cấu hình tenant resolution:

- `CurrentTenantIdentifierResolver`.
- `MultiTenantConnectionProvider` để chọn/định tuyến connection cho database/schema tenancy.
- Tenant identifier được truyền khi mở Session theo API tương ứng.
- `@TenantId` cho discriminator/shared-table tenancy ở các version hỗ trợ.
- Tích hợp JPA/Spring Data và tenant context trong application infrastructure.

Vì API, property keys và một số bootstrapping detail thay đổi qua Hibernate 5.x/6.x/7.x, không copy một config example của phiên bản khác mà không đối chiếu Javadocs/runtime dependency.

Kiểm tra phiên bản:

```java
String ormVersion =
    org.hibernate.Version.getVersionString();
```

Sau đó dùng tài liệu đúng bản và kiểm chứng integration test trên DB mục tiêu.

## 24. Explicit tenant identifier khi mở Session

Thay vì resolver đọc ThreadLocal, một số đường API cho phép truyền tenant rõ:

```java
try (Session session = sessionFactory.withOptions()
        .tenantIdentifier(trustedTenantId)
        .openSession()) {

    Transaction tx = session.beginTransaction();
    try {
        List<Invoice> invoices = session.createQuery(
            "from Invoice",
            Invoice.class
        ).getResultList();
        tx.commit();
    } catch (RuntimeException ex) {
        tx.rollback();
        throw ex;
    }
}
```

Đây là hướng tốt khi muốn **tenant là tham số tường minh** cho một Session xử lý background task.

### Không vừa mở Session tenant A vừa đổi ThreadLocal sang B

Tenant identity của Session/connection không nên được xem là mutable per-query parameter. Khi dùng một Session đã mở cho tenant A, đừng đổi ThreadLocal sang B rồi tiếp tục dùng Session đó.

Một unit of work/Session nên gắn với **một tenant cố định**. Muốn làm B, đóng/hoàn tất Session A và tạo Session mới cho B.

### Explicit session cũng cần authorization

API `tenantIdentifier(...)` không xác thực quyền. Chỉ truyền `trustedTenantId` sau khi xác nhận nguồn và quyền truy cập.

## 25. MultiTenantConnectionProvider và trạng thái JDBC connection

Trong schema-per-tenant, Hibernate có thể dùng `MultiTenantConnectionProvider` để lấy connection cho tenant cụ thể.

Ý tưởng:

```text
Tenant identifier = tenant-A
      |
      v
MultiTenantConnectionProvider.getConnection(A)
      |
      v
Connection chọn schema A
      |
      v
Hibernate SQL
      |
      v
releaseConnection(A, connection)
      |
      v
Reset schema/connection session state
      |
      v
Return connection to pool
```

Nếu connection sau job A còn `search_path = tenant_A` rồi được trả về pool, job B có thể nhận chính connection ấy và **dùng sai schema** nếu provider không đặt lại trạng thái đúng.

ThreadLocal cleanup và connection reset là **hai trách nhiệm độc lập**.

## 26. Reset schema trong finally khi release connection

Ví dụ đơn giản mô tả nguyên tắc (không phải toàn bộ interface implementation):

```java
Connection acquireForTenant(String tenantId)
        throws SQLException {

    Connection connection = dataSource.getConnection();

    try {
        String schema = schemaRegistry.requireAllowedSchema(tenantId);
        connection.setSchema(schema);
        return connection;
    } catch (SQLException | RuntimeException ex) {
        connection.close();
        throw ex;
    }
}

void releaseForTenant(Connection connection)
        throws SQLException {
    try {
        connection.setSchema("public");
    } finally {
        connection.close();
    }
}
```

Trong ví dụ trên, `public` chỉ là schema mặc định **của một hệ thống PostgreSQL giả định**. Đừng dùng nó trên DB khác hoặc một ứng dụng mà `public` cũng chứa dữ liệu nhạy cảm.

### Điều kiện quan trọng

- `schemaRegistry.requireAllowedSchema` ánh xạ tenant ID sang schema **đã cho phép**, không nối trực tiếp input vào SQL identifier.
- `Connection.setSchema` có mức hỗ trợ khác nhau theo JDBC driver/database.
- Có database dùng `SET search_path` hoặc session context riêng, cần reset tương ứng.
- Nếu reset thất bại, connection có thể không an toàn để trả lại pool; phải theo policy discard/evict của pool/provider.
- Reset có thể cần xử lý transaction state trước khi tiếp tục tái sử dụng connection.
- Phải kiểm thử với pool thật, không chỉ một connection mới trên mỗi test.

**Không coi `connection.close()` của pooled connection luôn xóa mọi custom session variable/schema state**, trừ khi pool/driver documentation và integration test xác nhận.

## 27. Không trộn tenant trên cùng JDBC transaction

Một transaction:

```text
BEGIN
  query tenant A
  đổi ThreadLocal sang tenant B
  query tenant B
COMMIT
```

có thể đang dùng **cùng connection** được bind với transaction, cùng Hibernate Session tenant A. Đổi ThreadLocal không tự switch schema/connection hoặc reset Persistence Context.

### Vì sao nguy hiểm?

- Identity map có thể giữ entity ID trùng của A và B.
- SQL có thể chạy trên schema A dù ThreadLocal báo B.
- Dirty checking có thể flush entities cũ vào nơi không dự tính.
- JDBC transaction không được split tự động theo tenant.

Nên chọn:

```text
Tenant A:
  set A -> open tx A -> work A -> commit -> close -> clear

Tenant B:
  set B -> open tx B -> work B -> commit -> close -> clear
```

Nếu nghiệp vụ yêu cầu thay đổi nhiều tenants trong một operation, cần coordination/saga hoặc giao dịch được thiết kế đặc biệt; đừng giả định một Hibernate Session làm được atomic cross-tenant work.

## 28. Persistence Context và identity map cũng có ranh giới tenant

Trong Session stateful, Hibernate quản lý entity theo identity trong Persistence Context.

Giả sử hai tenant đều có `Invoice#1001`.

Nếu một Session tenant A đã nạp:

```java
Invoice invoiceA = session.find(Invoice.class, 1001L);
```

đừng đổi ThreadLocal sang B rồi:

```java
Invoice invoiceB = session.find(Invoice.class, 1001L);
```

và kỳ vọng invoiceB luôn là hàng tenant B.

`session.find` có thể trả entity đã nằm trong identity map hoặc dùng tenant identity đã gắn với Session A.

### Nguyên tắc

**Một Persistence Context chỉ thuộc về một tenant/unit of work.** Không sử dụng lại context giữa tenants, ngay cả khi service method chỉ “đọc” và IDs có vẻ giống nhau.

Spring `@PersistenceContext` thường inject proxy có thể lấy EntityManager theo current transaction. Điều đó không cho phép chia sẻ EntityManager thực hoặc một transaction xuyên tenants.

## 29. ThreadLocal cleanup không thay cho Session cleanup

Sai:

```java
Session session = factory.openSession();
TenantContext.set("tenant-A");
// ...
TenantContext.clear();

TenantContext.set("tenant-B");
// Tái sử dụng session đã tạo cho A.
```

`TenantContext.clear()` chỉ xóa giá trị ThreadLocal; nó **không đóng Session**, không rollback transaction và không làm connection chuyển schema.

Thực hành tốt:

- Dùng `try-with-resources` cho Session tự mở.
- Commit/rollback transaction có cấu trúc.
- Dùng Spring-managed transactional service cho JPA thông thường.
- Đóng Session trước khi kết thúc scope tenant.
- Dọn tenant ở finally ngoài cùng.

Thứ tự lý tưởng:

```text
Validate tenant
  -> set tenant
  -> open Session / begin transaction
  -> work
  -> commit/rollback
  -> close Session / release connection
  -> clear tenant
```

## 30. Spring @Transactional và @Async: ranh giới tách biệt

`@Transactional` của Spring imperative thường gắn transaction resources với **thread hiện tại**.

`@Async` chuyển method sang **executor thread khác** khi lời gọi đi qua Spring proxy.

Một method request:

```java
@Transactional
public void createInvoice(...) {
    repository.save(invoice);
    asyncFacade.processAsync(invoiceId);
}
```

không chuyển transaction của request sang worker. Nếu worker bắt đầu trước commit, nó có thể không thấy Invoice mới.

### Đúng hơn

- Commit business transaction trước khi worker phụ thuộc dữ liệu.
- Có thể dùng `@TransactionalEventListener(AFTER_COMMIT)` cho in-process handoff.
- Với yêu cầu không được mất job, dùng transactional outbox/job table trong cùng transaction.
- Worker tạo **transaction riêng**, tenant scope riêng, Session riêng.

### AFTER_COMMIT không bảo đảm durability

Nếu process crash sau DB commit nhưng trước khi enqueue/running task, event chỉ trong memory có thể mất. Outbox giúp lưu ý định công việc bền vững để dispatcher retry.

Không phụ thuộc `Thread.sleep` để “chờ commit”; đây là race condition, không phải timeout cố định.

## 31. Sự khác nhau giữa tenant và actor trong job

Một job có thể được khởi tạo bởi user của tenant A, nhưng được thực thi nhiều giờ sau bởi service account.

Payload:

```java
public record JobMetadata(
    long jobId,
    String tenantId,
    String requestedByUserId,
    String traceId
) {}
```

Trong worker:

- `tenantId`: quyết định data isolation/routing.
- `requestedByUserId`: audit ai khởi tạo.
- `servicePrincipal`: quyền thực thi của worker.
- `traceId`: liên kết logs/traces.

Đừng thay tenant ID bằng user ID hoặc lấy “current logged-in user” từ SecurityContext trên background thread rồi suy ra tenant.

### Authorization tại thời điểm enqueue và execute

Một hệ thống có thể kiểm quyền khi tạo job, rồi cho job tiếp tục ngay cả khi người dùng đăng xuất. Hệ thống khác phải revalidate quyền lúc worker chạy.

Hai lựa chọn có business semantics khác nhau. Quy định rõ và audit quyết định; **đừng để việc thiếu SecurityContext trong worker tự quyết định policy**.

## 32. SecurityContext và MDC không phải transaction context

Spring Security có `SecurityContextHolder`, logging có MDC:

```java
SecurityContextHolder.getContext()
                     .getAuthentication();
MDC.get("traceId");
```

Nhiều trường hợp chúng được gắn ThreadLocal. Có thể propagate qua executor với:

- Delegating SecurityContext wrappers do Spring Security cung cấp.
- `TaskDecorator` cho MDC hoặc các metadata được phép.
- Distributed tracing/context propagation libraries.

**Tuyệt đối không làm**:

```text
Copy all ThreadLocals
  bao gồm EntityManager/Session/Connection/transaction
```

vì transaction không thể được chuyển tùy tiện sang thread khác mà giữ nguyên bảo đảm Hibernate/Spring.

Thay vì clone toàn bộ context, hãy truyền **tập dữ liệu tối thiểu** được kiểm soát và tạo transaction trong worker thread.

## 33. MDC cleanup quan trọng dù chỉ là log

Giả sử worker-1 xử lý:

```text
Job A:
  tenantId=A, traceId=trace-A

Job B:
  tenantId=B, traceId=trace-B
```

Nếu MDC không được cleanup, logs của B có thể gắn nhãn A, làm điều tra sự cố sai hoặc lộ metadata tổ chức.

Mẫu:

```java
Map<String, String> captured = MDC.getCopyOfContextMap();

Runnable wrapped = () -> {
    try {
        MDC.clear();
        if (captured != null) {
            MDC.setContextMap(captured);
        }
        delegate.run();
    } finally {
        MDC.clear();
    }
};
```

Với nested execution trên cùng thread, có thể cần lưu/khôi phục previous MDC. Với **outermost independent executor task**, việc clear ở finally giúp tránh leak sang task kế tiếp.

Không dùng MDC làm nguồn sự thật quyết định database tenant. Logging context có thể bị set hoặc override vì mục đích observability.

## 34. Không coi @Filter là tenant security tuyệt đối

Một ứng dụng có thể dùng Hibernate dynamic filter:

```java
@FilterDef(
    name = "tenantFilter",
    parameters = @ParamDef(
        name = "tenantId",
        type = String.class
    )
)
@Filter(
    name = "tenantFilter",
    condition = "tenant_id = :tenantId"
)
@Entity
public class Invoice {
    @Id private Long id;
    @Column(name = "tenant_id")
    private String tenantId;
}
```

Và:

```java
session.enableFilter("tenantFilter")
       .setParameter("tenantId", tenantId);
```

Filter có thể áp cho nhiều entity queries, nhưng cần lưu ý:

- Direct `find(id)` và to-one identifier load có thể không áp filter theo mặc định ở Hibernate 6.6/7.x nếu `applyToLoadByKey=false`.
- Entity/collection đã được nạp vào Persistence Context không tự bị revoke khi đổi filter.
- Native SQL/JdbcTemplate không tự kế thừa filter.
- Bulk DML phải kiểm tra scope riêng.
- Nếu worker không bật filter trong Session mới, query có thể không giới hạn.

### Giải pháp đúng với shared-table tenant

- Dùng Hibernate tenant discriminator mapping phù hợp version (ví dụ `@TenantId` nếu áp dụng).
- Với queries nhạy cảm, kiểm tra tenant predicate rõ.
- Dùng composite keys/foreign keys có tenant scope khi cần.
- Xem database RLS như lớp bảo vệ bổ sung nếu topology hỗ trợ.
- Viết tests direct lookup, lazy relations, native/bulk operations.

Không dùng một ThreadLocal+`@Filter` như **biên bảo mật duy nhất** nếu hệ thống có yêu cầu cách ly nghiêm ngặt.

## 35. @TenantId với shared-table multi-tenancy

Hibernate các phiên bản 6.x/7.x hỗ trợ `@TenantId` để biểu diễn tenant discriminator trong mapping được hỗ trợ.

Ví dụ:

```java
@Entity
@Table(name = "invoices")
public class Invoice {

    @Id
    private Long id;

    @TenantId
    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    private BigDecimal amount;
}
```

Hibernate có thể dùng tenant ID của Session trong việc ghi/lọc entity theo cơ chế discriminator multitenancy, tránh phụ thuộc hoàn toàn vào việc mỗi service nhớ enable một dynamic filter.

Tuy nhiên:

- Tính năng, các ràng buộc mapping và hỗ trợ bulk/native operations cần đối chiếu version.
- Không tự cho phép client chọn tenant ID.
- Connection/Session vẫn phải được tạo với tenant đúng.
- Không dùng raw native SQL không có tenant scope rồi tin `@TenantId` sẽ tự rewrite.
- Row-level constraints và tenant-scoped foreign keys vẫn cần thiết kế ở database.

`@TenantId` không thay thế authentication/authorization, nhưng phù hợp hơn một filter tùy ý bật/tắt cho một số shared-table designs.

## 36. Row-Level Security ở database

Trên database hỗ trợ RLS như PostgreSQL, có thể cấu hình policy để chính database giới hạn hàng mà DB session được phép truy cập.

Ý tưởng:

```sql
SELECT *
FROM invoices
WHERE tenant_id = current_setting('app.tenant_id');
```

Với PostgreSQL, RLS policy có thể tham chiếu session setting tương tự, nhưng thiết kế cụ thể cần xử lý:

- Ai được quyền set `app.tenant_id`?
- Có dùng `SET LOCAL` trong transaction hay custom session variables không?
- Làm sao tránh rò session setting khi connection trở về pool?
- DB role có bypass RLS hoặc table owner privilege không?
- Native SQL và background jobs có được enforce?
- Có thể đặt tenant khác tùy ý qua JDBC SQL không?

**RLS mạnh hơn app-level filter ở phạm vi nhiều đường SQL**, nhưng nếu application DB role được phép tự đặt arbitrary tenant và không có auth binding, nó vẫn có thể dùng sai tenant. Cần thiết kế defense in depth.

## 37. Connection pool reset cả trạng thái DB session tùy chỉnh

Một pooled JDBC connection có thể giữ nhiều trạng thái:

- Schema/current catalog.
- Auto-commit và transaction isolation.
- Read-only mode.
- Session variables/custom `SET`.
- Temporary tables/session-level settings.
- Role/search path.
- Time zone hoặc các thông số vendor-specific.

Không chỉ xóa ThreadLocal trong Java. Sau khi dùng connection A, trạng thái connection trước khi trả lại pool phải được reset theo policy/provider.

### Bẫy khi reset chỉ trong success path

```java
Connection c = pool.getConnection();
c.setSchema(schemaA);
doWork(c); // Throws exception.
c.setSchema(defaultSchema);
c.close();
```

Nếu `doWork` lỗi, reset/close có thể không được chạy.

Mẫu có `try/finally`, và nếu reset thất bại, phải loại connection khỏi pool hoặc đóng hỏng theo contract của pool thay vì trả lại không an toàn.

### Thiết lập schema ở thời điểm nào?

Ngay sau khi lấy connection và trước mọi query/prepare statement cần tenant. Nếu transaction đã dùng connection trước đó, thay schema giữa transaction là một thay đổi nguy hiểm cần tránh.

## 38. L2 cache không phải biên tenant và phải được kiểm thử

Hibernate second-level cache có thể lưu entity data/collections chia sẻ giữa Sessions.

Trong multi-tenancy chuẩn của Hibernate, provider/cache key design có thể bao gồm tenant identifier theo API, nhưng không nên suy diễn rằng **mọi custom cache key/filter-based tenancy** đều được phân vùng đúng.

Ví dụ:

```text
Tenant A: Invoice#1001 = 500000
Tenant B: Invoice#1001 = 900000
```

Nếu cache được keyed chỉ bằng `entityName + id` trong một custom layer, dữ liệu A/B có thể đè lên hoặc bị trả nhầm.

### Cần kiểm tra

- Hibernate multitenancy cache key semantics theo version.
- Cache region names, tenant identifier và custom cache implementations.
- Application-level caches (Caffeine/Redis) có tenant in key không.
- Collection cache có tương thích filter động không.
- Cache evictions/updates có tenant scope.
- Quá trình chuyển request A → B trên pooled thread có bị ảnh hưởng bởi cached Session/data.

Trong custom key, thường cần:

```text
cache key = tenantId + entityType + entityId (+ version/scope)
```

Không cho phép thiếu tenant ngầm định thành “global cache key” cho dữ liệu private.

## 39. JPA EntityManager proxy và Session lifecycle

Một singleton Spring service:

```java
@PersistenceContext
private EntityManager entityManager;
```

thường nhận một shared proxy có thể phân giải EntityManager theo transaction/thread. Điều đó được Spring hỗ trợ.

Nhưng **không** có nghĩa một EntityManager thực hoặc Hibernate Session do:

```java
EntityManager em = emf.createEntityManager();
```

tạo ra có thể được chia sẻ đồng thời giữa tasks.

Không đưa `em`, `session` hay managed entity graph vào queue hoặc DTO.

Ở mỗi background job:

1. Có tenant ID đáng tin.
2. Đặt tenant context.
3. Vào bean transactional hoặc tạo Session riêng với explicit tenant.
4. Load dữ liệu theo tenant.
5. Commit/rollback.
6. Close/release resources.
7. Dọn tenant context.

## 40. Open EntityManager in View và filter order

Trong một số cấu hình Spring web, Open EntityManager in View (OSIV) giữ EntityManager trong HTTP request để lazy loading ở view/controller layer.

Với multi-tenancy, điều này đặt câu hỏi quan trọng:

> Tenant đã được resolve trước khi OSIV tạo EntityManager hay chưa?

Nếu tenant chỉ được đặt ở controller hoặc service, có thể **quá muộn** cho một EntityManager đã được tạo/bind trước đó.

### Cách tiếp cận

- Xác định filter/interceptor order thật.
- Đặt tenant authentication/routing trước ORM resource acquisition.
- Cân nhắc tắt OSIV nếu domain/service đã quản lý fetch đầy đủ.
- Không dùng lazy loading lúc serialize JSON để thay cho data access authorization.
- Kiểm tra nested servlet/async dispatch.

Không kết luận “OSIV bật thì tenant context được tự động theo request” mà không kiểm tra thứ tự tạo Session và những thread khác tham gia.

## 41. @TransactionalEventListener sau commit và tenant context

Một service:

```java
@Transactional
public void createInvoice(...) {
    repository.save(invoice);
    publisher.publishEvent(
        new InvoiceCreatedEvent(invoice.getId(), tenantId)
    );
}
```

Listener:

```java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void afterCommit(InvoiceCreatedEvent event) {
    asyncFacade.processAsync(event);
}
```

`AFTER_COMMIT` giúp tránh việc async worker đọc invoice **chưa commit**, nhưng:

- Listener có thể chạy khi Spring transaction resources/synchronization đang được hoàn tất.
- Không thực hiện thêm DB writes trong callback rồi giả định transaction đã commit sẽ commit lần nữa.
- Async worker ở thread khác phải đặt tenant theo event payload và mở transaction mới.
- Event chưa persist bền vững có thể mất nếu app crash sau commit.

Nếu công việc không được phép mất, lưu outbox event/job record trong transaction gốc, dispatcher đọc sau commit.

## 42. Tenant payload trong transactional outbox

Ví dụ bảng:

```sql
CREATE TABLE outbox_events (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    payload_json TEXT NOT NULL,
    status VARCHAR(20) NOT NULL
);
```

Trong transaction ghi Invoice:

```text
BEGIN tenant A
  INSERT invoice tenant A
  INSERT outbox_event tenant A
COMMIT
```

Dispatcher:

```text
load trusted outbox event
  -> tenantId=A from persisted row
  -> set tenant A
  -> new transaction A
  -> process
  -> mark outcome and clear
```

Outbox thường đạt **at-least-once delivery**, nên worker phải idempotent. Nếu retry job A, phải luôn thực thi lại trong tenant A; không được kế thừa tenant từ task trước đó.

### Metadata từ nguồn tin cậy

Nếu một external message có `tenantId` khác với outbox/job row trong DB, phải xác định policy reject/quarantine, không lấy bừa giá trị vừa đến.

## 43. Retry phải có tenant context và transaction mới

Một job A gặp deadlock:

```text
attempt 1:
  tenant A set
  begin transaction A
  deadlock -> rollback
  close Session
  clear tenant

backoff

attempt 2:
  tenant A set từ persisted job
  begin NEW transaction A
  re-read current state
  commit
  clear tenant
```

Không:

- Tái sử dụng transaction/Session đã lỗi.
- Giữ tenant ThreadLocal trong suốt thời gian delay nếu thread được dùng cho task khác.
- Retry tự chọn “tenant hiện tại” từ pooled thread.
- Chuyển business ID mà quên tenant ID.

### Retry ở tầng nào?

Nếu dùng Spring Retry/Resilience4j, cần kiểm tra thứ tự decorator/advice:

```text
tenant boundary
   -> retry coordinator
       -> transactional worker lần 1
       -> transactional worker lần 2
```

Mỗi attempt phải có transaction mới; tenant phải được xác định trước mỗi transaction. Khi retry từ durable queue sau restart, tenant phải được lấy lại từ dữ liệu đáng tin.

## 44. Cancellation, timeout và exception không được để sót context

Các đường kết thúc khác success:

- RuntimeException/SQLException.
- Executor rejection khi submit.
- InterruptedException/cancel request.
- Transaction timeout.
- Worker mất connection.
- Retry exhausted.
- Consumer nack/dead-letter.

`try/finally` trong worker đảm bảo cleanup ở các đường Java control flow bình thường/có exception. Nhưng:

- Nếu task bị **reject trước khi chạy**, wrapper trong worker không thực thi; caller phải xử lý trạng thái job.
- Nếu process bị kill, không có cleanup code chạy; connection pool sẽ đóng theo lifecycle process, nhưng công việc cần durable retry.
- Timeout không tự rollback các chunks đã commit.
- Khi nested scopes, việc clear ở sai mức có thể xóa context của outer caller còn hoạt động.

Mỗi task độc lập cần **một outer cleanup boundary** xác định rõ, thay vì scatter `set/clear` ở nhiều method rời rạc.

## 45. Parallel streams và nested futures

Ví dụ:

```java
List<InvoiceResult> results = invoiceIds.parallelStream()
    .map(this::processInvoice)
    .toList();
```

`parallelStream` có thể chạy các phần việc trên nhiều threads, không phải tất cả đều có tenant context của caller. Nếu `processInvoice` đọc ThreadLocal, kết quả không đáng tin.

Tương tự:

```java
CompletableFuture.supplyAsync(...)
    .thenApplyAsync(...)
    .thenComposeAsync(...);
```

Mỗi async stage có thể chạy ở thread/executor khác. Context không tự được bảo đảm qua toàn bộ chuỗi.

### Phương án

- Biến tenant thành một phần của immutable command.
- Truyền executor được quản lý tới mọi stage cần chạy riêng.
- Bọc mỗi stage cần database bằng tenant scope và transaction riêng.
- Tránh chạy JPA EntityManager/Session trên parallel stream.
- Nếu cần fan-out, thiết kế concurrency và DB pool limits rõ.

## 46. Nhiều tenants trong một batch job

Một bulk import có thể chứa rows của nhiều organizations:

```text
Row 1: tenant-A
Row 2: tenant-B
Row 3: tenant-A
Row 4: tenant-C
```

Anti-pattern:

```java
@Transactional
public void importAll(List<Row> rows) {
    for (Row row : rows) {
        TenantContext.set(row.tenantId());
        repository.save(map(row));
    }
}
```

Transaction/Session có thể đã mở trước vòng lặp; việc đổi TenantContext không tạo các DB connections/transactions đúng tenant.

### Thiết kế

1. Kiểm tra nguồn và authorization của từng row/tenant.
2. Chia các rows theo tenant.
3. Với mỗi tenant: bắt đầu **outer tenant boundary**.
4. Mở transaction riêng theo chunk cho tenant ấy.
5. Commit/rollback; đóng Session/connection.
6. Clear tenant trước tenant tiếp theo.

```text
Partition by tenant
  A: rows [1,3] -> transaction A1, A2...
  B: rows [2]   -> transaction B1...
  C: rows [4]   -> transaction C1...
```

Nếu cần global all-or-nothing xuyên nhiều databases, đây là một bài toán distributed transactions/saga; không giải quyết bằng `@Transactional` trong một JVM và ThreadLocal đổi giá trị.

## 47. Một tenant nhiều jobs: giới hạn fairness

Ví dụ:

```text
tenant-A: 100000 pending jobs
tenant-B: 10 pending jobs
tenant-C: 20 pending jobs
```

Nếu một executor FIFO duy nhất nhận toàn bộ jobs A trước, B/C có thể bị starvation. Dù tenant context không leak, hệ thống vẫn vận hành không công bằng.

Các chiến lược:

- Giới hạn concurrency per tenant.
- Weighted fair scheduling.
- Partitioned queues và worker quotas.
- Backpressure và rate limit.
- Thời gian transaction/chunk rõ.
- Metrics hàng đợi và latency theo tenant.

**Context isolation** và **resource fairness** là hai mục tiêu bổ sung, không thay thế nhau.

## 48. Tests: một worker thread xử lý A rồi B

Đây là test đơn giản nhưng cực kỳ quan trọng.

```java
ExecutorService executor =
    Executors.newSingleThreadExecutor();

try {
    Future<String> first = executor.submit(() -> {
        try (TenantContext.Scope ignored =
                TenantContext.use("tenant-A")) {
            return TenantContext.requireCurrent();
        } finally {
            TenantContext.clear();
        }
    });

    Future<String> second = executor.submit(() -> {
        return TenantContext.peek();
    });

    assertEquals("tenant-A", first.get());
    assertNull(second.get());  // Không còn A ở worker thread.
} finally {
    executor.shutdownNow();
}
```

Test này xác nhận **Java context cleanup**. Nó **chưa chứng minh** Session và DB connection isolation, vì chưa chạy truy vấn Hibernate.

### Test lỗi

Chạy A nhưng ném exception:

```java
executor.submit(() -> {
    try (var ignored = TenantContext.use("tenant-A")) {
        throw new IllegalStateException("Simulated failure");
    } finally {
        TenantContext.clear();
    }
});
```

Sau đó submit B và xác nhận không có tenant A. Chỉ `Future.get()` trên task lỗi để quan sát exception, không để test treo.

## 49. Tests: định tuyến connection đúng khi pool tái sử dụng

Với schema-per-tenant, tạo:

```text
tenant_a.invoices
  id=1001 amount=500000

tenant_b.invoices
  id=1001 amount=900000
```

Test dùng connection pool nhỏ (ví dụ tối đa 1 connection) để tăng khả năng tái sử dụng:

1. Mở Session tenant A, đọc Invoice#1001.
2. Commit/close Session A, trả connection.
3. Mở Session tenant B, đọc Invoice#1001.
4. Xác nhận amount B là 900000.
5. Mở Session tenant A lần nữa, amount vẫn 500000.
6. Lặp với exception/rollback ở A trước khi B bắt đầu.
7. Quan sát JDBC current schema/`search_path` trước và sau release.

Không chỉ kiểm tra ThreadLocal được clear: phải kiểm tra **SQL thực sự chạy ở schema/database nào**.

## 50. Tests: shared-table cách ly truy vấn và mutations

Seed hai tenants cùng business ID:

```sql
INSERT INTO invoices(tenant_id, invoice_id, amount)
VALUES
('tenant-A', 1001, 500000),
('tenant-B', 1001, 900000);
```

Kiểm thử:

- HQL/Criteria list queries.
- Direct `find` by ID.
- Lazy `@ManyToOne` và collection loads.
- JPQL/HQL bulk UPDATE/DELETE.
- Native SQL/JdbcTemplate.
- Spring Data `findById`/custom repositories.
- L2/application cache.
- Background tasks sau request.

Với mô hình dùng Hibernate tenancy, API Identifier có thể cần có identity key tenant-aware; thiết kế đúng mapping trước khi viết test.

### Ví dụ assertion nghiệp vụ

Trong context A, một thao tác update Invoice#1001 chỉ thay row A, row B không đổi. Sau một retry và worker thread reuse, invariant này vẫn phải đúng.

## 51. Tests: tenant A, B, exception, cancellation và scheduler

Ma trận:

| Test | Mục tiêu |
|---|---|
| A → B trên 1 thread | Không dùng tenant A cho B |
| A throws → B | Cleanup trong exception path |
| Task không có tenant | Fail closed, không dùng default tenant |
| A → system task → B | Không kế thừa tenant A vào system task |
| Concurrent A/B trên 2 threads | Không ghi chéo context |
| Nested tenant scope trong cùng thread | Khôi phục previous đúng hoặc reject cross-tenant nesting |
| @Async cùng named executor | Propagation/cleanup đúng |
| CompletableFuture common pool | Xác nhận không dựa vào propagation ngầm |
| @Scheduled không request | Từng tenant có scope riêng |
| Message retry sau restart | Tenant lấy từ durable record |
| RLS/session variable | Reset sau mỗi connection |
| L2 cache hit/miss | Không trả data chéo tenant |

Thực hiện trên DB vendor/version thực tế nếu đang kiểm tra `Connection.setSchema`, tenant discriminator hay RLS. H2/in-memory database không luôn mô phỏng đúng semantics của PostgreSQL/MySQL/Oracle.

## 52. Logging/observability khi phát hiện context stale

Một hệ thống nên có:

- `tenantId` từ trusted context trên logs quan trọng (đã được redacted đúng).
- `jobId`, `traceId`, `attempt`.
- Metric tenant-context-missing.
- Metric stale-context-found-at-task-start.
- Metric tenant mismatch giữa command và Session/connection.
- DB connection acquisition failures theo tenant.
- Count job retries/cross-tenant authorization failures.

### Không log dữ liệu nhạy cảm

Tenant ID có thể là metadata business nhạy cảm; không log raw tokens, passwords hoặc toàn bộ request payload.

Một stale context là dấu hiệu cần điều tra nghiêm túc. Đừng sửa bằng cách nuốt exception rồi dùng tenant mặc định và tiếp tục truy vấn.

## 53. Phát hiện mismatch giữa job và session

Khi có khả năng kiểm tra tenant identifier của Session theo API Hibernate version đang dùng, có thể xác nhận:

```text
Expected tenant (trusted job record): tenant-B
Actual Hibernate Session tenant:       tenant-A
```

Nếu khác nhau:

1. **Dừng job** trước khi đọc/ghi.
2. Rollback transaction nếu đang active.
3. Đóng Session/connection theo đúng lifecycle.
4. Báo lỗi, ghi metric và log không chứa PII.
5. Quarantine/retry sau khi sửa nguyên nhân routing.

Đừng cố “đổi ThreadLocal về B” trong Session A rồi tiếp tục. Tenant session đã gắn resource A; tạo Session/transaction đúng từ đầu.

## 54. Một số sai lầm phổ biến

### “ThreadLocal tự xóa khi Runnable chạy xong”

Sai với pooled thread. Runnable kết thúc nhưng Thread còn sống và ThreadLocal value có thể còn.

### “Chỉ cần set tenant ở controller”

Chưa đủ nếu OSIV/transaction/connection mở trước đó hoặc có async workers.

### “Chỉ cần clear trong success path”

Sai. Phải dùng `finally` để xử lý exception.

### “Scope khôi phục previous nên không thể leak”

Không tuyệt đối. Nếu previous stale, nó lại được khôi phục. Outer task boundary phải sạch.

### “@Async kế thừa transaction và tenant”

Không mặc định. Worker thread cần context và transaction riêng.

### “@Transactional ở method đã set tenant sớm”

Không chắc. Transaction interceptor có thể mở resources trước method body.

### “MultiTenantConnectionProvider sẽ tự sửa ThreadLocal stale”

Không. Provider định tuyến theo tenant ID nó nhận được; input sai vẫn gây routing sai.

### “ThreadLocal.clear đủ để đổi tenant của Hibernate Session”

Không. Session và connection đã gắn tenant theo lifecycle riêng.

### “Connection.close luôn reset custom schema”

Không mặc định được bảo đảm cho mọi pool/driver và custom variables.

### “InheritableThreadLocal truyền tenant theo từng task”

Không. Nó inherit tại thời điểm tạo thread và nguy hiểm với pool reuse.

### “@Filter sẽ ngăn mọi find(id) và native SQL đọc chéo tenant”

Không. Đường load-by-ID, native/bulk và caches phải được kiểm tra.

### “Cứ bật RLS là an toàn, không cần tin cậy tenant setting”

Không. Nếu DB role có bypass hoặc application tự chọn tenant setting tùy ý, policy vẫn có lỗ hổng.

### “Một transaction có thể đổi tenant giữa các rows”

Không nên. Tenant là thuộc tính unit of work/Session, không phải biến query tùy ý.

### “Job không có tenant thì dùng tenant-A mặc định”

Nguy hiểm. Thiếu tenant phải fail closed trên đường nghiệp vụ yêu cầu isolation.

### “Một executor pool lớn xử lý nhiều tenants nhanh hơn”

Không chắc. Connection pool/DB contention và fairness có thể tệ hơn.

## 55. Bài thực hành 1: chứng minh ThreadLocal leakage

Viết:

```java
ExecutorService executor =
    Executors.newSingleThreadExecutor();

executor.submit(() -> TenantContext.set("tenant-A")).get();
String leaked = executor.submit(TenantContext::peek).get();
```

Kỳ vọng `leaked` là tenant-A trong bản code lỗi.

Tiếp theo:

1. Đưa `set` vào `try/finally clear`.
2. Chạy lại test.
3. Tạo exception ở task A.
4. Chạy task B không có tenant.
5. Assert B không lấy tenant A.
6. Thêm metric phát hiện stale context trước task.

Đừng xem đây là test toàn bộ hệ thống; cần test Session/connection routing riêng.

## 56. Bài thực hành 2: đặt tenant trước @Transactional

Tạo một Hibernate resolver đọc `TenantContext.requireCurrent()`.

1. Viết method `@Transactional` tự set tenant ở dòng đầu thân method.
2. Đo khi nào EntityManager/connection được tạo.
3. Refactor thành dispatcher không transaction gọi worker transactional qua bean khác.
4. Assert tenant đúng trong Session.
5. Thử self-invocation để thấy advice có thể không chạy.
6. Test hai tenants cùng invoice ID.
7. Verify transaction rollback/close trước khi tenant clear.

Không phụ thuộc vào timing tình cờ của datasource nếu framework hiện tại defer connection acquisition; thiết kế đúng phải bảo đảm tenant có **trước mọi lần resource có thể được tạo**.

## 57. Bài thực hành 3: JDBC schema reset

Tạo PostgreSQL test database với hai schemas:

```sql
CREATE SCHEMA tenant_a;
CREATE SCHEMA tenant_b;

CREATE TABLE tenant_a.invoices(
    id BIGINT PRIMARY KEY,
    amount NUMERIC(18, 2)
);
CREATE TABLE tenant_b.invoices(
    id BIGINT PRIMARY KEY,
    amount NUMERIC(18, 2)
);

INSERT INTO tenant_a.invoices VALUES(1001, 500000);
INSERT INTO tenant_b.invoices VALUES(1001, 900000);
```

1. Pool size 1.
2. Lấy connection cho tenant A, query amount.
3. Close/release, lấy lại cho B.
4. Query amount B.
5. Cố tình bỏ reset schema trong DB test và quan sát rủi ro.
6. Thêm reset trong `finally`.
7. Simulate SQL exception trước release.
8. Đảm bảo connection không trả lại pool nếu reset thất bại theo contract pool.

## 58. Bài thực hành 4: @Async, TaskDecorator và message retry

1. Tạo named `ThreadPoolTaskExecutor` với một worker.
2. Tạo jobs A/B; lần lượt submit.
3. Thử `@Async` không decorator và không explicit command tenant.
4. Thêm TaskDecorator capture tenant + cleanup.
5. Thử submit từ caller thiếu tenant; worker phải fail closed nếu cần tenant.
6. Thử exception ở A rồi chạy B.
7. So sánh với command chứa tenant ID đọc từ durable job row.
8. Tắt/mở lại ứng dụng giả lập retry sau restart; không dựa vào ThreadLocal đã mất.

Giải thích vì sao TaskDecorator giúp **in-process context propagation** nhưng không thay thế durable identity của queued jobs.

## 59. Bài thực hành 5: multi-tenant query, cache và bảo mật

Seed hai tenants có Invoice ID trùng.

1. Kiểm tra repository queries theo tenant.
2. Kiểm tra `findById`/HQL/direct load.
3. Kiểm tra lazy to-one/collection.
4. Kiểm tra native SQL và bulk UPDATE.
5. Bật L2 hoặc custom cache; kiểm tra tenant trong key.
6. Chạy A/B trên same executor thread.
7. Kiểm tra kết quả không đổi khi thứ tự task đảo lại.
8. Thêm RLS nếu DB hỗ trợ, và test bằng SQL ngoài Hibernate.

Trong mỗi test, assert **không chỉ count** mà cả dữ liệu trả về đúng tenant.

## 60. Bài thực hành 6: scheduler xử lý mọi tenant

Giả sử:

```text
active tenants: A, B, C
```

Tạo scheduler:

1. Lấy danh sách tenants từ trusted registry.
2. Tạo một job/transaction boundary cho mỗi tenant.
3. Gắn job ID và tenant ID vào mỗi command.
4. Gây lỗi khi chạy B.
5. Xác nhận C vẫn có thể được xử lý theo failure policy.
6. Xác nhận không có Session/connection của B được dùng cho C.
7. Với nhiều replicas, thêm distributed job claiming/idempotency.
8. Đo fairness và connection pool.

Không nhầm “tách transaction” với “tự động đảm bảo exactly-once job execution”.

## 61. Câu hỏi tự kiểm tra

1. Vì sao `ThreadLocal` có thể giữ tenant A sau khi Runnable kết thúc?
2. `ThreadLocal.remove()` khác `set(null)` ở điểm nào về cleanup semantics?
3. Tại sao cần `try/finally` thay vì clear cuối happy path?
4. Vì sao việc restore previous trong nested scope chưa chắc ngăn leak ở outer task?
5. Tenant nên lấy từ đâu trong HTTP request?
6. Vì sao không lấy raw `X-Tenant-Id` làm chứng cứ authorization?
7. Tại sao tenant phải được đặt trước khi mở transaction/Session?
8. `@Transactional` method body có chắc chạy trước transaction interceptor không?
9. Vì sao `@Async` cần tenant/transaction riêng?
10. Vì sao không truyền managed entity/Session qua executor?
11. `TaskDecorator` có tự bao phủ `ForkJoinPool.commonPool` không?
12. `InheritableThreadLocal` sao chép context tại thời điểm nào?
13. Tenant context cleanup có tự reset JDBC `search_path` không?
14. Nếu connection reset schema thất bại, nên làm gì với connection?
15. `CurrentTenantIdentifierResolver` có xác thực tenant identity không?
16. `validateExistingCurrentSessions` có thay thế authorization không?
17. Có được đổi tenant giữa cùng Hibernate Session không?
18. Vì sao L1 identity map làm reuse Session giữa tenants nguy hiểm?
19. `@Filter` có bảo đảm mọi native SQL/by-ID lookup tuân theo tenant không?
20. `@TenantId` và DB RLS có thể giúp điều gì, nhưng còn giới hạn nào?
21. Vì sao scheduled job không nên dùng “tenant cuối cùng trong ThreadLocal”?
22. Outbox giúp job context tồn tại qua restart như thế nào?
23. Khi retry, vì sao phải tạo transaction mới cùng trusted tenant?
24. Vì sao một pool quá lớn có thể làm tenant khác bị starvation?
25. Test tối thiểu nào phát hiện A → B leak trên pooled thread?

**Gợi ý:** (1) thread tồn tại lâu hơn task; (2) remove xóa entry theo cơ chế ThreadLocal; (3) xử lý exceptions; (4) previous có thể stale; (5) identity/membership đã xác thực; (6) header do client sửa được; (7) ORM/connection routing có thể xảy ra sớm; (8) không; (9) thread-bound; (10) không thread-safe/detached; (11) không; (12) khi tạo child thread; (13) không; (14) discard/evict; (15) không; (16) không; (17) không nên; (18) cached entity identity; (19) không; (20) hỗ trợ enforcement theo mapping/DB nhưng không tự xác thực actor; (21) stale tenant; (22) persist tenant/job row; (23) reset failed state; (24) resource contention; (25) single-thread executor A rồi B, gồm exception path.

## 62. Checklist production cho context isolation

| Kiểm tra | Tại sao quan trọng |
|---|---|
| Trusted tenant resolution | Không cho client tự chọn data scope không được phép |
| Fail closed khi thiếu tenant | Không rơi về một tenant mặc định tùy ý |
| Tenant setup trước transaction/Session | Tránh ORM/DB routing sai |
| Một Session cho một tenant | Không dùng identity map/connection xuyên tổ chức |
| Outer task `finally` cleanup | Tránh ThreadLocal stale ở pooled threads |
| Nested scope restore policy | Không phá caller context hoặc khôi phục stale state |
| @Async named executor | Biết chính xác thread pool/context propagation |
| No unmanaged CompletableFuture common pool | Tránh bỏ qua policy |
| TaskDecorator/command consistency | Tránh hai nguồn tenant trái nhau |
| Scheduler/message consumer tenant scoping | Không có request context để kế thừa |
| Transactional worker bean/proxy | Boundary đúng và tránh self-invocation |
| Connection schema/variable reset | Pool trả connection sạch |
| Cache keys/regions tenant-aware | Không rò data qua L2/custom caches |
| Native/bulk/by-ID tests | Không chỉ test HQL list query |
| RLS/DB isolation khi cần | Defense in depth |
| Retry từ durable job record | Tenant vẫn đúng sau crash/restart |
| Job idempotency & claims | Tránh xử lý trùng trên nhiều replicas |
| Logs/metrics context mismatch | Phát hiện sự cố sớm |
| A → B same-thread integration test | Tái hiện lỗi pool reuse |
| Authorization across tenants | Chứng minh không đọc/ghi chéo |

## 63. Nguyên tắc cần ghi nhớ

1. **ThreadLocal gắn với Java Thread, không gắn với một request hoặc task**; pooled threads có thể dùng lại giá trị tenant cũ.
2. **Tenant phải được lấy từ nguồn đáng tin và kiểm quyền**, không nhận trực tiếp từ header/message tùy ý.
3. **Thiết lập tenant trước khi tạo Hibernate Session, EntityManager transaction hoặc lấy JDBC connection.** Set trong thân `@Transactional` đôi khi quá muộn.
4. **Một unit of work/Session gắn với đúng một tenant**; không đổi ThreadLocal rồi dùng lại Persistence Context.
5. **Dọn context trong `finally` ở ranh giới ngoài cùng của task**. Nested scopes phải có chính sách restore/clear nhất quán.
6. **@Async, scheduled jobs và message consumers cần context riêng.** Context của HTTP request không tự được chuyển sang worker thread.
7. **TaskDecorator chỉ truyền metadata có chủ đích**, không copy Hibernate Session/transaction resources.
8. **InheritableThreadLocal không phải cơ chế propagation cho thread pools**; nó inherit lúc tạo thread.
9. **Connection pool cũng cần reset schema/session variables** khi trả kết nối; ThreadLocal cleanup không làm việc đó.
10. **CurrentTenantIdentifierResolver không phải authorization layer**; input sai vẫn định tuyến sai.
11. **Shared-table @Filter không phải tenant security tuyệt đối**. Xem xét `@TenantId`, explicit predicates và DB RLS.
12. **L1/L2 caches và association loading phải được kiểm thử xuyên tenant**, không chỉ danh sách HQL.
13. **Retry phải có tenant đáng tin và transaction mới mỗi attempt**; không kế thừa tenant còn sót.
14. **Durable job/outbox lưu tenant cùng ý định xử lý**, để restart không phải dựa vào ThreadLocal.
15. **Test A → B trên cùng worker thread, cả khi A thất bại** là kiểm thử tối thiểu để chứng minh không tái sử dụng nhầm ngữ cảnh.

Khi dùng bộ luồng trong hệ thống Hibernate đa tổ chức, một thiết kế an toàn coi **tenant identity là đầu vào bất biến của mỗi unit of work**. Resolver đọc đúng tenant, Session/transaction dùng đúng tenant, connection được reset trước khi về pool, và ThreadLocal được dọn khi task kết thúc. Một lời gọi `remove()` là cần thiết nhưng chỉ có ý nghĩa khi được đặt trong **toàn bộ chuỗi bảo đảm** đó.

### Tài liệu tham khảo chính thức

- [Hibernate ORM User Guide — Multitenancy](https://docs.hibernate.org/orm/current/userguide/html_single/#multitenacy)
- [Hibernate ORM Javadocs — CurrentTenantIdentifierResolver](https://docs.hibernate.org/orm/current/javadocs/org/hibernate/context/spi/CurrentTenantIdentifierResolver.html)
- [Hibernate ORM Javadocs — MultiTenantConnectionProvider](https://docs.hibernate.org/orm/current/javadocs/org/hibernate/engine/jdbc/connections/spi/MultiTenantConnectionProvider.html)
- [Hibernate ORM Javadocs — TenantId](https://docs.hibernate.org/orm/current/javadocs/org/hibernate/annotations/TenantId.html)
- [Hibernate ORM Javadocs — SessionBuilder](https://docs.hibernate.org/orm/current/javadocs/org/hibernate/SessionBuilder.html)
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework Javadocs — TaskDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskDecorator.html)
- [Spring Security Reference — Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html)
- [Java SE — ThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java SE — InheritableThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InheritableThreadLocal.html)
- [PostgreSQL Documentation — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [PostgreSQL Documentation — SET](https://www.postgresql.org/docs/current/sql-set.html)
