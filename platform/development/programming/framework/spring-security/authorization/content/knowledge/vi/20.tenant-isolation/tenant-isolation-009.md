# Truyền ngữ cảnh tenant qua tác vụ nền và dọn ngữ cảnh sau xử lý trong Spring Security

## 1. Mục tiêu: đúng tenant trong mọi thread, kể cả khi không còn HTTP request

Trong ứng dụng SaaS đa tenant, request HTTP thường được Spring Security xác thực rồi ứng dụng giải quyết một `AuthorizedTenantScope`: ai đang gọi, thuộc tenant nào và có quyền gì. Nhưng nghiệp vụ có thể tiếp tục ở thread khác: `@Async`, `CompletableFuture`, `ExecutorService`, scheduler, Spring Batch, queue consumer, job xuất báo cáo hoặc worker gửi email.

Tại các điểm chuyển này, có hai rủi ro đặc biệt:

1. **Mất ngữ cảnh:** worker không biết tenant đã được xác minh; developer dùng tenant mặc định, bỏ filter hoặc chọn tenant từ payload chưa đáng tin.
2. **Rò ngữ cảnh:** thread pool tái sử dụng worker; tenant `alpha` còn nằm trong `ThreadLocal`, `SecurityContextHolder`, MDC hoặc session của database, khiến job của tenant `beta` chạy với tenant `alpha`.

Lỗi thứ hai nguy hiểm vì không cần attacker gửi URL đặc biệt. Chỉ cần hai job thuộc hai tenants được thực hiện tuần tự trên cùng một worker và một đường lỗi không cleanup.

Bài này giải thích **truyền thông tin tenant đã được authorize** thay vì truyền một chuỗi tenant tùy ý, **kiểm tra lại quyền khi công việc thực sự chạy**, và **xóa/khôi phục mọi context trong `finally`**. Nội dung bao gồm Java 17 chạy độc lập, Spring `TaskDecorator`/`@Async`, Spring Security `DelegatingSecurityContext...`, queues, scheduler, Reactor, RLS, audit và tests.

### Bất biến cần giữ

```text
Trước khi task chạy:
    worker tenant context = EMPTY

Khi task chạy:
    worker tenant context = tenant đã được authorize
    DB query/update chỉ trên tenant đó

Sau khi task thành công / lỗi / bị ngắt:
    worker tenant context = EMPTY
    hoặc khôi phục đúng context trước đó theo contract

Task kế tiếp:
    không thể quan sát tenant của task trước
```

**Lưu ý:** cleanup bảo vệ tính cách ly giữa các tác vụ, nhưng không tự biến một tenant ID do client gửi thành tenant đáng tin. **Authorization phải xảy ra trước khi cấp tenant scope**, và với job trì hoãn phải kiểm tra lại tại execution time theo chính sách thu hồi quyền.

## 2. Bốn loại thông tin không nên trộn làm một

| Thông tin | Ví dụ | Tại sao không đồng nghĩa? |
| --- | --- | --- |
| Requested tenant | Header `X-Tenant-Id: alpha` | Caller tự chọn; chưa chứng minh quyền |
| Authenticated identity | `Authentication`, validated JWT `iss/sub` | Cho biết ai đang gọi, chưa chắc đang được phép ở alpha |
| Authorized tenant scope | `subject=alice, tenant=alpha, action=EXPORT` | Kết quả policy từ identity + membership + action |
| Execution context | `ThreadLocal`, MDC, Reactor `Context`, DB session | Chỉ là cơ chế truyền trạng thái, không phải chứng cứ quyền |

Một app có thể dùng `TenantContext` để Hibernate hoặc repository biết tenant hiện hành. Tuy vậy:

- `TenantContext.set("alpha")` **không phải lệnh cấp quyền**.
- `SecurityContextHolder.getContext().getAuthentication()` có thể có user nhưng **không có tenant scope của ứng dụng**.
- `MDC.put("tenant", "alpha")` chỉ thêm nhãn vào log, hoàn toàn không bảo vệ SQL.
- `Connection` đang dùng schema alpha không chứng minh caller được quyền vào alpha.
- DTO job chứa `tenantId=alpha` phải được xét trong trust model của producer/consumer.

**Thiết kế ưu tiên:** truyền một đối tượng immutable `AuthorizedTenantScope` hoặc `JobCommand` có identity và tenant đã được chuẩn hóa, rồi dùng policy server tại mỗi security boundary. Chỉ dùng ThreadLocal để hỗ trợ framework cần context ngầm; khi có thể, truyền scope thành tham số service/repository sẽ dễ kiểm tra hơn.

## 3. Luồng tổng quát: request → enqueue → worker

```text
HTTP / API
  |
  v
Authentication: JWT/session/mTLS đã verify
  |
  v
TenantResolver:
    requested tenant -> kiểm tra membership/authority
  |
  v
AuthorizedTenantScope(subject, tenant, permissions)
  |
  +------ request đồng bộ ----------------------+
  |                                             |
  v                                             v
Service đọc/ghi                          Submit background job
  |                                      /          \
  v                                     /            \
Repository WITH tenant predicate    In-process async  Durable queue
                                        |                 |
                                        v                 v
                                   Capture scope      Persist command
                                   tại submit        không gửi raw token
                                        |                 |
                                        v                 v
                                   Worker thread     Consumer identity
                                   có scope tạm      + reauthorization
                                        |                 |
                                        +--------+--------+
                                                 |
                                                 v
                                       Tenant-scoped repository
                                                 |
                                                 v
                                       finally cleanup context
                                                 |
                                                 v
                                       Thread/cursor/connection
                                       tái sử dụng an toàn
```

Hai đường này **khác trust model**:

- **Async trong cùng tiến trình, thời gian rất ngắn:** có thể truyền immutable snapshot đã được authorize tại submit, nhưng nên kiểm tra lại trước thao tác đặc biệt nhạy cảm.
- **Queue/job bền vững chạy sau vài phút/giờ hoặc qua service khác:** request-time snapshot không đủ. Consumer phải xác thực nguồn job, lấy identity/capability phù hợp, đối chiếu membership/policy hiện hành rồi mới tạo scope runtime.

Không lưu bearer token người dùng vào queue chỉ để worker “mượn” token cũ. Token có thời hạn, có thể bị lộ và có audience không phù hợp; dùng service identity và authorization contract cho công việc bền vững.

## 4. Vì sao ThreadLocal và thread pool nguy hiểm?

Java `ThreadLocal<T>` gắn giá trị với **thread đang chạy**. `Executors.newFixedThreadPool(...)` hoặc `ThreadPoolTaskExecutor` giữ lại các thread để xử lý nhiều task. Nếu task A gọi `CURRENT_TENANT.set("alpha")` mà không `remove()`:

```text
Worker-1:
  09:00 task A        CURRENT_TENANT = alpha
  09:01 task A kết thúc nhưng quên remove()
  09:02 task B        CURRENT_TENANT vẫn alpha
  09:03 task B query  -> truy cập sai tenant
```

Cách viết nguy hiểm:

```java
static final ThreadLocal<String> CURRENT_TENANT = new ThreadLocal<>();

void process(String tenant, Runnable action) {
    CURRENT_TENANT.set(tenant); // Sai: tenant chưa được authorize?
    action.run();               // Nếu throw exception, context còn lại.
}
```

Ngay cả khi `action.run()` thành công, worker vẫn giữ tenant cũ. Không dùng `ThreadLocal` để lưu trạng thái request dài hạn và không coi `InheritableThreadLocal` là lời giải cho pool.

### InheritableThreadLocal không giải quyết thread reuse

`InheritableThreadLocal` sao chép giá trị khi **tạo thread con mới**. Pooled worker có thể đã được tạo trước request hiện tại, nên không nhận giá trị mới; hoặc nhận giá trị từ một request trước ở lúc tạo rồi giữ lâu. Điều này có thể dẫn đến lẫn tenant, khó debug và có race. Spring Security cũng lưu ý việc chọn chiến lược `SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` phải được hiểu rõ; nó không biến tenant context độc lập của ứng dụng thành cơ chế an toàn cho task queue.

**Quy tắc:** context phải được **cài đặt sát lúc task thực thi, theo scope đã được xác minh**, và **cleanup trong `finally`**. Không dựa vào inheritance của pooled threads.

## 5. Mẫu an toàn: immutable scope và lexical boundary

Một record Java 17:

```java
public record AuthorizedTenantScope(
        String subjectId,
        String tenantId) {

    public AuthorizedTenantScope {
        if (subjectId == null || subjectId.isBlank()
                || tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Missing tenant identity");
        }
    }
}
```

Record bất biến về các reference; nếu có `Set` hoặc `List` bên trong phải copy `Set.copyOf(...)`/`List.copyOf(...)` để tránh caller thay đổi sau khi submit. **Record constructor kiểm tra nonblank không chứng minh subject/tenant có quyền.** Chỉ policy service được giao tạo authorized scope dùng trong các boundary bảo mật.

Mẫu wrapper:

```java
final class TenantContext {

    private static final ThreadLocal<AuthorizedTenantScope> CURRENT =
            new ThreadLocal<>();

    static AuthorizedTenantScope require() {
        AuthorizedTenantScope scope = CURRENT.get();
        if (scope == null) {
            throw new IllegalStateException("Missing authorized tenant context");
        }
        return scope;
    }

    static <T> T callWith(
            AuthorizedTenantScope scope,
            java.util.concurrent.Callable<T> task) throws Exception {

        if (scope == null || task == null) {
            throw new IllegalArgumentException("Missing scope or task");
        }

        if (CURRENT.get() != null) {
            throw new IllegalStateException("Nested tenant context prohibited");
        }

        CURRENT.set(scope);
        try {
            return task.call();
        } finally {
            CURRENT.remove();
        }
    }
}
```

Đây là **đoạn tích hợp**, không phải file độc lập vì dùng record ở trên. Nó có các ưu điểm:

- Nếu không có tenant đã resolve, `require()` thất bại thay vì trả “all tenants”.
- Một task thành công hay ném exception đều chạy `finally` để xóa.
- Cấm nested context theo contract này để ngăn âm thầm đổi tenant ở giữa một giao dịch.
- Không gọi `set` từ controller chỉ dựa vào header.
- Không để task sửa scope object nếu object được thiết kế immutable đúng cách.

**Mẫu restore previous:** một số dự án thực sự cho phép nested calls cùng tenant; có thể snapshot `previous = CURRENT.get()`, đặt scope rồi trong `finally` nếu previous null thì `remove()`, ngược lại `set(previous)`. Nếu cho phép nested **khác tenant**, cần kiểm tra cross-tenant authorization rõ ràng; đừng dùng cơ chế “restore” như quyền ngầm để chuyển tenants.

### Tại sao `finally` quan trọng?

`finally` chạy khi task trả kết quả hoặc ném exception đồng bộ thông thường. Nó còn chạy khi `InterruptedException` được ném lên đường stack mà code vẫn thoát. Tuy nhiên nếu thread bị dừng ở mức process crash, hard kill, infinite uninterruptible loop hoặc JVM bị kết thúc, không có bảo đảm `finally` đã thực thi. Worker cần timeout, cooperative cancellation và cơ chế cô lập/giám sát phù hợp.

## 6. Java 17 runnable: cùng một pooled thread chạy nhiều tenants

Ví dụ độc lập này có ba mục đích:

1. Chỉ tạo scope sau khi policy đối chiếu actor/tenant với membership và resource tenant.
2. Dùng **một worker thread duy nhất** để lộ lỗi nếu quên cleanup.
3. Chứng minh context trống sau thành công, sau exception và khi quyền bị thu hồi.

Tệp `TenantBackgroundLab.java`:

```java
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class TenantBackgroundLab {

    record Job(String actor, String requestedTenant, long documentId) {}

    record AuthorizedScope(String actor, String tenant) {}

    static final class TenantContext {
        private static final ThreadLocal<AuthorizedScope> CURRENT =
                new ThreadLocal<>();

        static AuthorizedScope current() {
            return CURRENT.get();
        }

        static <T> T callWith(
                AuthorizedScope scope, Callable<T> task) throws Exception {
            if (scope == null || task == null || CURRENT.get() != null) {
                throw new IllegalStateException("Invalid tenant boundary");
            }
            CURRENT.set(scope);
            try {
                return task.call();
            } finally {
                CURRENT.remove();
            }
        }
    }

    static final class Policy {
        private final Map<String, Set<String>> activeMemberships =
                new ConcurrentHashMap<>();

        private final Map<Long, String> resourceTenants =
                Map.of(11L, "alpha", 12L, "alpha", 21L, "beta");

        Policy() {
            activeMemberships.put("alice", Set.of("alpha"));
            activeMemberships.put("bob", Set.of("alpha", "beta"));
        }

        AuthorizedScope authorize(Job job) {
            if (job == null || job.actor() == null
                    || job.requestedTenant() == null
                    || !job.requestedTenant().matches("[a-z][a-z0-9-]*")
                    || !activeMemberships.getOrDefault(
                            job.actor(), Set.of()).contains(job.requestedTenant())
                    || !job.requestedTenant().equals(
                            resourceTenants.get(job.documentId()))) {
                throw new SecurityException("Denied");
            }
            return new AuthorizedScope(
                    job.actor(), job.requestedTenant());
        }

        void revoke(String actor, String tenant) {
            activeMemberships.computeIfPresent(actor, (key, before) -> {
                Set<String> next = new HashSet<>(before);
                next.remove(tenant);
                return Set.copyOf(next);
            });
        }
    }

    private static String workerState(ExecutorService pool)
            throws Exception {
        Future<String> state = pool.submit(() ->
                TenantContext.current() == null ? "EMPTY" : "LEAK");
        return state.get();
    }

    private static String runJob(
            ExecutorService pool,
            Policy policy,
            Job job,
            boolean failInside) throws Exception {

        Future<String> future = pool.submit(() -> {
            // Resolve lại khi worker CHẠY, không tin Job.requestedTenant.
            AuthorizedScope checked = policy.authorize(job);

            return TenantContext.callWith(checked, () -> {
                if (failInside) {
                    throw new IllegalStateException("Simulated failure");
                }
                return checked.tenant() + "/" + job.documentId();
            });
        });

        try {
            return future.get();
        } catch (ExecutionException ex) {
            Throwable cause = ex.getCause();
            if (cause instanceof SecurityException) {
                return "DENIED";
            }
            if (cause instanceof IllegalStateException) {
                return "FAILED";
            }
            throw ex;
        }
    }

    public static void main(String[] args) throws Exception {
        Policy policy = new Policy();

        try (var ignored = new java.io.Closeable() {
            @Override
            public void close() {
                // Không dùng cách này để đóng executor trong Java 17.
            }
        }) {
            ExecutorService pool = Executors.newSingleThreadExecutor();
            try {
                System.out.println("before=" + workerState(pool));

                System.out.println("alice-alpha=" + runJob(
                        pool, policy, new Job("alice", "alpha", 11L), false));
                System.out.println("after-alpha=" + workerState(pool));

                System.out.println("bob-beta=" + runJob(
                        pool, policy, new Job("bob", "beta", 21L), false));
                System.out.println("after-beta=" + workerState(pool));

                System.out.println("failed=" + runJob(
                        pool, policy, new Job("alice", "alpha", 12L), true));
                System.out.println("after-failure=" + workerState(pool));

                policy.revoke("bob", "beta");
                System.out.println("after-revocation=" + runJob(
                        pool, policy, new Job("bob", "beta", 21L), false));
                System.out.println("after-denied=" + workerState(pool));

                System.out.println("wrong-resource=" + runJob(
                        pool, policy, new Job("alice", "alpha", 21L), false));
                System.out.println("after-wrong-resource=" + workerState(pool));

                System.out.println("main-thread="
                        + (TenantContext.current() == null ? "EMPTY" : "LEAK"));
            } finally {
                pool.shutdown();
                if (!pool.awaitTermination(
                        5, java.util.concurrent.TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            }
        }
    }
}
```

**Giải thích cấu trúc:** `Policy.authorize` dùng membership và mapping resource tenant ở server; `Job.requestedTenant` chỉ là dữ liệu đầu vào. Chỉ khi policy cho phép, worker mới đặt `AuthorizedScope` vào `ThreadLocal`. Sau mỗi job, main submit thêm một task kiểm tra `ThreadLocal` của **chính worker thread đang được tái sử dụng**. Bước này bắt được lỗi leakage tốt hơn chỉ kiểm tra ThreadLocal ở main thread.

Lệnh chạy bằng Java 17+:

```bash
javac TenantBackgroundLab.java
java TenantBackgroundLab
```

Stdout của mã:

```text
before=EMPTY
alice-alpha=alpha/11
after-alpha=EMPTY
bob-beta=beta/21
after-beta=EMPTY
failed=FAILED
after-failure=EMPTY
after-revocation=DENIED
after-denied=EMPTY
wrong-resource=DENIED
after-wrong-resource=EMPTY
main-thread=EMPTY
```

Điều được chứng minh:

- Alice được chạy document 11 thuộc alpha; Bob được chạy document 21 thuộc beta khi còn membership.
- Task của Alice cố ý ném exception **sau khi đã đặt context**. `finally` vẫn gọi `remove()`, nên worker rỗng ở task tiếp theo.
- Membership Bob/beta bị thu hồi **trước khi một job mới chạy**; policy kiểm tra lại và trả `DENIED`.
- Alice không thể dùng tenant alpha để thao tác document 21 thuộc beta.
- Context main thread vẫn trống; worker không chia sẻ ThreadLocal với main.

**Phạm vi demo:** không có JWT, Spring, Kafka hay database thật; actor trong `Job` là dữ liệu minh họa. Production phải gắn actor với nguồn tin cậy (producer identity, signed capability, authenticated user hoặc service policy), chứ không cho client tự gửi tên “bob” và được hệ thống tin. Ví dụ cố ý dùng `newSingleThreadExecutor()` để chứng minh cleanup, không phải khuyến nghị mọi công việc nên dùng một thread.

### Cách viết production còn đơn giản hơn

Trong code thực, nên bỏ `try (var ignored = ...)` không có tác dụng; chỉ cần:

```java
ExecutorService pool = Executors.newFixedThreadPool(4);
try {
    // Submit và await các công việc đã được kiểm soát.
} finally {
    pool.shutdown();
}
```

Đoạn phía trên là snippet, không phải chương trình riêng. Trong Java 17, `ExecutorService` **chưa** có contract `AutoCloseable` như các JDK mới, vì thế không dùng `try (pool)` nếu mục tiêu biên dịch Java 17. Demo chỉ dùng một wrapper không ảnh hưởng semantics để minh họa quản lý tài nguyên bằng `finally`.

## 7. Ba thời điểm phải rõ: capture, execute và cleanup

### Capture-time: khi enqueue/submit

Tại thời điểm request đã authorize, ứng dụng có thể tạo immutable `AuthorizedTenantScope`. Không capture raw `HttpServletRequest`, mutable principal object, live transaction hay JDBC Connection để đưa cho worker.

```text
t0: Request Alice xác thực, membership alpha đang ACTIVE
t1: Scope(alice, alpha) được tạo
t2: Job được submit
```

### Execute-time: khi worker thực sự chạy

```text
t3: Membership của Alice bị thu hồi
t4: Worker chạy job
```

Nếu nghiệp vụ đòi thu hồi quyền có hiệu lực tức thời, worker tại `t4` phải **re-authorize**, không chỉ tin snapshot t1. Với job rất ngắn chạy ngay và policy cho phép khoảng trễ, có thể dùng scoped snapshot, nhưng cần SLA và audit rõ.

### Cleanup-time: bất kể kết quả

```text
try:
    set verified scope
    run operation
finally:
    clear / restore context
```

Cleanup phải bao gồm:

- Tenant ThreadLocal.
- `SecurityContextHolder` nếu worker code tự set nó (Spring wrappers có lifecycle riêng).
- Logging `MDC`/trace context nếu application tự set.
- Database connection/schema/RLS tenant setting nếu dùng connection-bound state.
- Request-scoped metrics/diagnostics bị lưu trong thread locals ứng dụng.

Một `finally` của Java **không tự reset mọi loại state**. Phải xem từng context API có cơ chế cleanup nào.

## 8. SecurityContextHolder và tenant context là hai việc riêng

Spring Security servlet thường đặt `SecurityContext` trong `SecurityContextHolder` dựa trên thread (chiến lược mặc định). Khi chuyển sang thread mới, context có thể không còn. Spring Security cung cấp:

- `DelegatingSecurityContextRunnable`.
- `DelegatingSecurityContextCallable`.
- `DelegatingSecurityContextExecutor`.
- `DelegatingSecurityContextExecutorService`.
- `DelegatingSecurityContextAsyncTaskExecutor`.
- `DelegatingSecurityContextTaskScheduler` và các lớp liên quan.

Tài liệu chính thức cho biết `DelegatingSecurityContextRunnable` cài `SecurityContext` của caller trong worker và gọi `SecurityContextHolder.clearContext()` ở `finally`. Nhưng nó **chỉ xử lý SecurityContext**, không tự propagate một `TenantContext` riêng của ứng dụng.

```text
Spring Security wrapper:
  Capture Authentication/SecurityContext
  |
  v
Run task with SecurityContext
  |
  v
Clear SecurityContextHolder

Application tenant wrapper:
  Capture authorized tenant scope
  |
  v
Run task with TenantContext
  |
  v
Remove/restore tenant context
```

### Cẩn trọng khi capture Authentication

`Authentication`/`SecurityContext` có thể chứa authorities, credentials, details hoặc dữ liệu mutable. Không giữ nguyên object này cho một job bền vững chạy lâu. Không giả định “có quyền lúc enqueue” sẽ luôn có quyền lúc execute. Nếu một wrapper được khởi tạo với **một SecurityContext cố định**, mọi task có thể chạy dưới cùng principal đó; đó chỉ đúng khi chủ đích dùng service identity cố định và các thao tác đều được giới hạn bởi policy.

## 9. Spring @Async: cấu hình TaskDecorator cho tenant scope

`TaskDecorator` của Spring Framework có thể bọc `Runnable` tại thời điểm executor nhận task; đây là hook thích hợp để **chụp scope ở thread submit** và cài vào worker trong phạm vi `run()`.

Giả định ứng dụng có `TenantContext.require()` và `TenantContext.callWith(...)` như mục 5, cùng record `AuthorizedTenantScope` đã được policy tạo.

```java
import java.util.concurrent.Callable;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class AsyncTenantConfiguration {

    @Bean("tenantWorkerExecutor")
    ThreadPoolTaskExecutor tenantWorkerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("tenant-worker-");

        TaskDecorator tenantDecorator = task -> {
            // Hàm decorate chạy trong thread SUBMIT.
            AuthorizedTenantScope captured = TenantContext.require();

            return () -> {
                try {
                    TenantContext.callWith(captured, () -> {
                        task.run();
                        return null;
                    });
                } catch (RuntimeException ex) {
                    throw ex;
                } catch (Exception checked) {
                    throw new IllegalStateException(
                            "Tenant task failed", checked);
                }
            };
        };

        executor.setTaskDecorator(tenantDecorator);
        return executor;
    }
}
```

**Đây là snippet tích hợp**, không phải một project Maven độc lập. Nếu `callWith` nhận `Callable<T>` và có contract từ chối nested scope, đoạn trên đảm bảo cleanup khi `task.run()` ném runtime exception.

Cần hiểu đúng:

- `TaskDecorator.decorate` có thể chạy khi submit. Vì thế `TenantContext.require()` phải có scope hợp lệ **trước khi gọi `@Async`**.
- Không capture giá trị từ ThreadLocal **ở worker**; khi worker chạy thì request thread đã khác.
- Không lấy tenant trực tiếp từ header ở decorator; decorator chỉ sao chép kết quả đã authorize.
- Nếu không có scope ở submit time, nên fail closed; scheduler/queue consumer không đi qua request cần một path riêng để tạo scope.
- Rejection khi queue đầy có thể xảy ra tại submit; policy retry/backpressure cần được xác định. Không bỏ qua lỗi rồi trả “job queued” khi không queue được.
- `TaskDecorator` có thể wrap một Runnable nội bộ dùng cho `Future`. Tài liệu Spring lưu ý exception của task dạng Future có thể không propagate từ `run()` như kỳ vọng; theo dõi `Future.get()`/`CompletableFuture`, metrics và error handlers thay vì dựa chỉ vào outer decorator.

### Gọi @Async ở đâu?

```java
@Service
class ExportFacade {

    private final TenantResolver resolver;
    private final AsyncExportService worker;

    ExportFacade(TenantResolver resolver, AsyncExportService worker) {
        this.resolver = resolver;
        this.worker = worker;
    }

    void requestExport(Authentication auth, String requestedTenant, long docId) {
        AuthorizedTenantScope scope =
                resolver.require(auth, requestedTenant, "EXPORT");

        TenantContext.callWith(scope, () -> {
            worker.export(docId); // Lời gọi qua bean proxy có @Async.
            return null;
        });
    }
}

@Service
class AsyncExportService {

    @Async("tenantWorkerExecutor")
    public CompletableFuture<Void> export(long documentId) {
        AuthorizedTenantScope scope = TenantContext.require();
        // Revalidate membership/permission ở đây nếu cần.
        // Query resource bằng (scope.tenantId(), documentId).
        return CompletableFuture.completedFuture(null);
    }
}
```

Mẫu này là **đoạn kết nối**, chưa hoàn chỉnh vì `TenantResolver`, repository, chính sách re-authorization, exception handling và persistence thuộc ứng dụng. Chữ ký `callWith` ném checked `Exception` nên caller phải `throws Exception` hoặc xử lý đúng; đừng copy nguyên method không xử lý checked exception vào production rồi cho rằng file đã biên dịch.

Lời gọi nội bộ `this.export(...)` trong cùng bean có thể bypass Spring AOP `@Async`. Dùng một bean khác, gọi qua proxy; có integration test xác nhận worker thread khác request thread.

## 10. Kết hợp DelegatingSecurityContextAsyncTaskExecutor khi cần cả identity

Nếu một tác vụ in-process thực sự cần `SecurityContext` của caller để gọi method security, có thể bọc `ThreadPoolTaskExecutor` đã cấu hình tenant decorator bằng `DelegatingSecurityContextAsyncTaskExecutor`.

```java
@Bean("securityAndTenantExecutor")
AsyncTaskExecutor securityAndTenantExecutor(
        @Qualifier("tenantWorkerExecutor")
        ThreadPoolTaskExecutor tenantExecutor) {

    return new DelegatingSecurityContextAsyncTaskExecutor(tenantExecutor);
}
```

Imports:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;
```

Khi dùng constructor chỉ nhận executor delegate, Spring Security wrapper chụp SecurityContext của thread submit theo cơ chế của nó. Tenant `TaskDecorator` chụp `AuthorizedTenantScope` riêng; mỗi wrapper xử lý cleanup context của chính mình.

**Hai lưu ý:**

1. Nếu một `@Async` method chỉ định `"securityAndTenantExecutor"`, bảo đảm bean đó thực sự được chọn và chưa bị một executor mặc định khác thay thế. Test cả SecurityContext và TenantContext **ở bên trong worker**.
2. SecurityContext propagation không thay việc **kiểm tra lại authorization**. Với job queue chạy sau nhiều giờ, không dùng lại SecurityContext người dùng cũ; dùng identity/capability và membership lookup ở consumer.

### Không tự set SecurityContextHolder bừa bãi

`SecurityContextHolder.setContext(...)` có thể hợp lệ trong một wrapper tự viết nhưng phải có `try/finally`, và tốt nhất dùng API Spring Security đã cung cấp. Nếu tự set context giả với quyền `ROLE_ADMIN` chỉ để job chạy, bạn đã tạo một đường privilege escalation nếu job payload không bị giới hạn và audit.

## 11. MDC và tracing: log phải đúng tenant nhưng không được làm nguồn quyền

MDC của SLF4J/Logback thường được dùng:

```java
MDC.put("tenantId", scope.tenantId());
MDC.put("subjectId", scope.subjectId());
```

MDC có thể dựa trên ThreadLocal và cũng cần cleanup. Nếu chỉ gọi `MDC.clear()`, bạn có thể vô tình xóa trace ID của wrapper bên ngoài. Khi dùng nested context, nên lưu map cũ rồi khôi phục:

```java
Map<String, String> previous = MDC.getCopyOfContextMap();

try {
    MDC.put("tenantId", scope.tenantId());
    MDC.put("subjectId", scope.subjectId());
    task.run();
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
```

Đoạn trên là **snippet tích hợp**, cần SLF4J `MDC`, `Map` và `task`. Chỉ ghi tenant đã được resolve vào MDC, không ghi raw client-supplied header như một giá trị đáng tin cho audit. Không log JWT/bearer token/cookie hoặc thông tin nhạy cảm. Nếu dùng Spring `ContextPropagatingTaskDecorator` dựa trên Micrometer context propagation, phải đăng ký `ThreadLocalAccessor` cho context **tùy chỉnh** khi muốn tự động propagate nó, và vẫn bảo vệ boundary tenant. Decorator mặc định tập trung vào propagation của các contexts đã đăng ký, **không tự biết phép xác minh tenant của nghiệp vụ**.

## 12. Tác vụ bất đồng bộ không được phép đổi tenant giữa chừng

Mỗi task nên được gắn **một** tenant scope rõ ràng. Nếu cần xử lý nhiều tenants:

```text
For each authorized tenant:
  establish scope(tenant)
  process tenant-specific batch
  finally cleanup
Move to next tenant
```

Không dùng:

```java
TenantContext.set("alpha");
processAlpha();
TenantContext.set("beta");
processBeta();
```

Cách này để lộ tenant nếu exception ở `processAlpha()` hoặc một nested call dùng context cũ. Hãy tạo hai lexical scopes tách biệt, với quyền chuyển tenant được service/job policy cho phép.

Khi xử lý document trong tenant `alpha`, repository phải query bằng tenant scope:

```sql
SELECT id, body
FROM documents
WHERE tenant_id = :authorized_tenant
  AND id = :document_id;
```

Đừng cho worker lấy một document chỉ bằng ID rồi mới “nếu tenant khác thì không trả”, bởi side effect, logs, joins hoặc lazy loading có thể đã chạm dữ liệu trái quyền. Với cập nhật, dùng conditional SQL hoặc transaction + re-check:

```sql
UPDATE documents
SET status = 'EXPORTED'
WHERE id = :document_id
  AND tenant_id = :authorized_tenant
  AND status = 'PENDING';
```

Sau UPDATE, kiểm tra affected rows để không coi zero rows là success. Dùng transaction cho cập nhật DB + outbox/event theo yêu cầu nghiệp vụ; phát event “exported” trước commit có thể tạo inconsistency.

## 13. Durable queue: tenantId trong message chỉ là selector

Ví dụ một message:

```json
{
  "jobId": "job-123",
  "tenantId": "alpha",
  "requestedBy": "alice",
  "documentId": 42,
  "action": "EXPORT",
  "policyVersion": 7
}
```

Không có dòng nào trong JSON tự chứng minh user Alice được quyền EXPORT. Producer có thể bị compromise, client có thể có đường gửi thẳng queue hoặc message bị replay. Consumer cần:

1. Xác thực producer/service identity và quyền ghi vào topic/queue.
2. Validate schema, type/action allowlist, canonical tenant ID và payload size.
3. Kiểm tra idempotency theo `(tenantId, jobId, action)` hoặc khóa tương đương.
4. Xác định source of truth của `requestedBy` (job record lưu ở DB sau authorization, signed capability hoặc trusted producer contract).
5. Tra membership/grant/permission hiện hành hoặc một snapshot/capability đã được policy chấp thuận.
6. Đối chiếu `documentId` với resource tenant trong database.
7. Cài `AuthorizedTenantScope` trước khi gọi domain service.
8. Dọn context trong `finally` kể cả khi handler ném exception.
9. Quyết định retry/DLQ mà không làm lộ dữ liệu; log jobId, tenant đã được xác minh, reason code nhưng không log token.

### Ví dụ consumer logic (pseudocode)

```text
onMessage(message):
    trustedOrigin = verifyProducer(message)
    job = jobRepository.findById(message.jobId)

    require trustedOrigin authorized to deliver job
    require message.tenantId equals job.tenantId
    require job.status is PENDING
    require actor/job capability still permitted for action
    require document.tenantId equals job.tenantId

    scope = authorizedScope(job.actor, job.tenantId, job.action)

    try:
        install scope
        execute idempotent business operation
        mark job COMPLETE atomically with outbox/event
    finally:
        clear scope, SecurityContext if manually set, MDC and DB state
```

Đây là pseudocode có chủ đích. Phần quan trọng là **consumer không lấy tenantId từ message rồi đi thẳng vào DB**. Job được queued khi membership ACTIVE có thể chạy sau khi membership REVOKED; policy phải xác định có hủy job hay cho phép job theo authorization snapshot tại submit, cùng TTL/audit.

### Retry và dead-letter queues

Một message được retry có thể chạy trên một worker khác hoặc cùng thread. Không dựa vào context từ lần chạy trước. Reauthorize ở **mỗi attempt**; không cần gửi raw SecurityContext qua queue. Nếu job đã commit nhưng ACK thất bại, consumer phải idempotent để retry không gửi hai email/cập nhật hai lần hoặc tạo thêm output cùng tenant.

## 14. Scheduler và Spring Batch: không có request principal

`@Scheduled`/cron không chạy trong một HTTP request đang xác thực user. Nếu scheduler làm báo cáo cho các tenant, cần **service identity** và danh sách tenant có quyền xử lý được lấy từ nguồn server tin cậy:

```java
@Scheduled(cron = "0 0 * * * *")
public void hourlyReports() {
    for (String tenantId : tenantRegistry.authorizedForReporting()) {
        AuthorizedTenantScope scope =
                reportPolicy.resolveServiceScope(tenantId);

        // Mỗi tenant có boundary riêng; xử lý xong phải cleanup.
        tenantRunner.run(scope,
                () -> reportService.generateForTenant(scope.tenantId()));
    }
}
```

Đoạn tích hợp giả định `TenantRegistry`, `ReportPolicy`, `TenantRunner`, `ReportService` đã được cung cấp. Service account không nên tự có global bypass; nếu workflow cần global admin, phải là quyền có chủ đích, audit và limit.

**Spring Batch:** có thể truyền tenant ID dưới dạng `JobParameters` để restart xác định đúng tenant, nhưng job parameter vẫn là **dữ liệu**, không phải quyền. Step/worker phải validate service identity, tenant entitlement và reader/writer predicates; partitioned steps hoặc chunk processing trên nhiều threads phải cài scope riêng rồi cleanup theo step/task. Không dùng singleton mutable field “currentTenant” trong ItemReader dùng chung cho partitions.

### Tác vụ cố định chạy cho một tenant

Có thể lưu tenant ID trong cấu hình scheduler được quản trị thay vì user input. Nhưng vẫn cần kiểm tra tenant còn ACTIVE, quyền service account còn hiệu lực và DB/query không vượt tenant. “Configuration file đáng tin” không có nghĩa chính sách không bao giờ thay đổi.

## 15. CompletableFuture, ExecutorService và mất context

Với `CompletableFuture.supplyAsync(...)` **không truyền executor**, công việc có thể chạy trên common ForkJoin pool. Nó không tự mang `SecurityContextHolder` hay custom `TenantContext` theo contract của bạn.

```java
// Phản ví dụ: bên trong supplier có thể không thấy tenant.
CompletableFuture.supplyAsync(() -> repository.loadCurrentTenant());
```

Nên dùng executor đã cấu hình propagation và/hoặc truyền immutable scope trực tiếp:

```java
AuthorizedTenantScope checked = tenantResolver.require(...);

CompletableFuture<Result> future =
        CompletableFuture.supplyAsync(
                () -> service.loadForTenant(
                        checked.tenantId(),
                        checked.subjectId()),
                tenantAwareExecutor);
```

Đây là **đoạn tích hợp**; `Result`, resolver, service, executor do ứng dụng định nghĩa. **Quan trọng:** nếu `service.loadForTenant` chỉ tin arguments mà không recheck resource/permission, code vẫn có thể lỗ hổng. Truyền scope đúng không thay policy enforcement.

### Capture ở submit, không ở worker

Nếu cần decorator tự propagate ThreadLocal:

```java
Runnable wrapAtSubmission(Runnable original) {
    AuthorizedTenantScope captured = TenantContext.require();
    return () -> TenantContext.runWith(captured, original);
}
```

Đây là pseudocode Java tích hợp; phương thức `TenantContext.runWith` cần được cài dựa trên `callWith` và phải cleanup. `wrapAtSubmission` cần chạy **trước** khi giao Runnable cho executor, còn lambda trả về mới chạy trong worker. Nếu chọn scope trong lambda worker bằng cách đọc ThreadLocal ở đó, lúc này context có thể null hoặc stale.

### Cancellation và timeout

Khi `Future.cancel(true)` interrupt worker, task phải tôn trọng interruption. `finally` chỉ chạy khi task rời khỏi phương thức đang thực thi; một thư viện blocking không phản ứng interrupt có thể giữ tenant context lâu hơn. Không giải quyết bằng cách cưỡng bức tái sử dụng thread đang bận. Với rejection trước khi task chạy, worker context chưa được cài; nhưng producer phải biết task không được enqueue.

## 16. Reactive: Reactor Context không phải ThreadLocal

Trong Spring WebFlux/reactive pipelines, execution có thể chuyển thread liên tục. Dùng `ThreadLocal` như servlet request là sai mô hình. Reactor cung cấp `Context` gắn với **subscription**, và Spring Security Reactive dùng `ReactiveSecurityContextHolder`.

Ví dụ **đoạn tích hợp**:

```java
static final String TENANT_SCOPE_KEY = "authorizedTenantScope";

Mono<String> operation(AuthorizedTenantScope verifiedScope) {
    return Mono.deferContextual(context -> {
        AuthorizedTenantScope scope =
                context.get(TENANT_SCOPE_KEY);
        return repository.findTitle(scope.tenantId())
                .map(title -> scope.tenantId() + ":" + title);
    }).contextWrite(context ->
            context.put(TENANT_SCOPE_KEY, verifiedScope));
}
```

Giả định `repository.findTitle` trả `Mono<String>` và `verifiedScope` được authorize trước đó. **Đặt một raw tenant string vào Reactor Context không biến nó thành quyền**. Reactor Context khác ThreadLocal: giá trị được truyền theo subscription; khi subscription kết thúc, không cần tự `ThreadLocal.remove()` cho Reactor Context thuần. Nhưng nếu bridge vào blocking JDBC code sử dụng ThreadLocal, phải có boundary rõ và cleanup riêng.

Không lưu một `ContextView` hoặc subscriber context làm singleton shared state giữa requests. Khi dùng `publishOn`/`subscribeOn`, dựa vào Reactor context propagation APIs đúng version thay vì copy ThreadLocal bằng tay.

### SecurityContext trong reactive

`ReactiveSecurityContextHolder.getContext()` là reactive API cho `SecurityContext`, không phải phép truy cập đồng bộ bằng `SecurityContextHolder.getContext()`. Bối cảnh reactive phải được giữ trong pipeline; nếu chuyển sang external queue, vẫn cần payload/trust/reauthorization như mục 13.

## 17. Database connection, schema và RLS cũng cần dọn đúng

Các hệ thống multi-tenant có thể dùng:

1. **Shared schema với cột `tenant_id`**: mọi SELECT/UPDATE/DELETE/COUNT/GROUP BY ràng buộc tenant.
2. **Schema per tenant**: connection đổi `search_path`/current schema.
3. **Database per tenant**: chọn DataSource theo authorized tenant.
4. **PostgreSQL RLS**: DB áp dụng policy dựa trên tenant context của transaction.

Dùng connection pool khiến connection được tái sử dụng giữa tenants. Nếu đổi schema hoặc session state mà không reset, request/job sau có thể chạy với tenant trước **dù Java ThreadLocal đã được remove**.

### Shared-table query

```sql
SELECT id, title
FROM documents
WHERE tenant_id = :authorized_tenant
  AND id = :document_id;
```

### PostgreSQL RLS với transaction-local setting

```sql
BEGIN;

SELECT set_config('app.tenant_id', :authorized_tenant, true);

SELECT id, title
FROM documents
WHERE id = :document_id;

COMMIT;
```

Ở PostgreSQL, tham số `true` của `set_config(name,value,is_local)` đặt setting trong phạm vi transaction; đây là một cách giảm rủi ro session state rò giữa connections. Tuy nhiên DB role/RLS policy phải được thiết kế đúng, tránh bypass RLS, và không cho user chạy SQL tùy ý trên cùng role nếu có thể tự đặt `app.tenant_id`.

Tác vụ async thường chạy trong **transaction riêng**; transaction của request **không tự truyền sang worker**. Worker phải tạo transaction, thiết lập DB tenant state đúng scope, query/update rồi kết thúc transaction và trả connection về pool an toàn.

### Không dùng raw tenant vào schema/database routing

```text
raw X-Tenant-Id -> "schema_" + value -> SET search_path
```

là sai nếu chưa authorize, validate và map qua registry. Nếu dùng `AbstractRoutingDataSource` hoặc Hibernate multi-tenancy, routing key cần là canonical authorized tenant; không tự gọi “default datasource” khi thiếu context vì có thể rò dữ liệu global.

## 18. MDC, transaction, cache và observability phải đồng bộ

Nếu tạo report CSV cho tenant alpha, không đủ để SQL lọc đúng khi:

- File object storage key không chứa tenant và bị overwrite bởi tenant khác.
- Cache dùng key `report:{jobId}` mà jobId chỉ duy nhất trong từng tenant.
- Audit log ghi tenant từ raw header chứ không từ resolved scope.
- Trace context được share giữa hai task khiến công cụ giám sát hiểu sai tenant.
- Metrics label chứa raw tenant string không kiểm soát, gây cardinality vô hạn.

Quy tắc:

```text
authorization scope = nguồn tenant duy nhất

DB predicate / routing  -> scope.tenantId
cache key               -> tenantId + subject/entitlement + operation
object storage path     -> tenantId + jobId đã validate
idempotency key         -> tenantId + jobId/action
audit tenant            -> scope.tenantId
MDC tenant              -> scope.tenantId (chỉ để log)
```

Bản thân key tenant không thay authorization khi đọc cache/object storage. Phải kiểm tra rằng caller/job được phép lấy object, và storage authorization không công khai bucket/path trái quyền.

Với OpenTelemetry/Micrometer, context propagation có thể được cấu hình tự động hoặc manual tùy stack/version. Đừng nhầm “trace ID truyền đúng” với “tenant scope được verify”. Khi thay đổi nền tảng async, regression tests phải chứng minh ngữ cảnh tenant **không thất lạc và không rò** trên đúng executor đang dùng.

## 19. Tránh biến một TaskDecorator thành lỗ hổng

TaskDecorator giúp truyền context nhưng **không phải authorization gateway**. Một số anti-pattern:

**A. Capture raw header ở submit.**

```java
String tenant = request.getHeader("X-Tenant-Id");
executor.execute(() -> TenantContext.set(tenant));
```

Kết quả: client điều khiển tenant, không policy check.

**B. Dùng fallback tenant.**

```java
String tenant = TenantContext.getOrDefault("public");
```

Nếu context mất do thread switch, task vô tình chạy với tenant không đúng. Với thao tác nhạy cảm, thiếu scope phải fail closed.

**C. Decorator chỉ set không remove.**

```java
return () -> {
    TenantContext.set(captured);
    task.run();
};
```

Nếu task throw exception hoặc trả về bình thường, worker còn tenant cũ. Luôn cleanup bằng `try/finally`.

**D. Dùng SecurityContext wrapper rồi mặc định tenant cũng có.**

Spring Security chỉ truyền `SecurityContext`, không tự truyền mọi ThreadLocal của ứng dụng. Cần kiểm tra `TenantContext` riêng.

**E. Dùng global fixed SecurityContext ROLE_ADMIN cho mọi jobs.**

Một job payload không đáng tin có thể lợi dụng role admin để đọc mọi tenants. Service identity phải gắn với operation/tenant scope có kiểm soát, không bypass toàn cục.

**F. Tạo wrapper capture trước khi authorize.**

Nếu ở thời điểm capture, `TenantContext` chưa có scope, wrapper nên ném lỗi và không enqueue, không tự đoán tenant theo request.

**G. Reuse cùng mutable scope object giữa tasks.**

Job A đổi `scope.tenantId` làm job B dùng giá trị sai. Dùng record hoặc immutable class, defensive copy collections.

**H. Chuyển token user qua queue.**

Có thể bị lộ/replay, hết hạn hoặc sai audience. Dùng job identity, service auth và policy tại consumer.

**I. Cache authorization vô hạn.**

Membership bị thu hồi nhưng worker tiếp tục dựa vào snapshot cũ; phải có TTL/invalidation hoặc check tại execution theo SLA.

**J. Quên context của DB.**

Java ThreadLocal được remove nhưng connection vẫn giữ schema tenant alpha. Cần transaction-scoped DB settings/reset.

## 20. Kiểm thử đúng rủi ro thread reuse

Một test cleanup không nên chỉ assert `TenantContext.current()==null` trong test thread. Nó phải dùng **cùng worker thread** để chạy ít nhất hai tác vụ.

### Ma trận unit/integration

| Case | Thiết lập | Điều cần assert |
| --- | --- | --- |
| Job alpha thành công | Pool size 1, scope alpha | Bên trong thấy alpha |
| Job beta tiếp theo | Cùng worker, scope beta | Bên trong thấy beta, không thấy alpha |
| Không scope | Submit đến executor đòi context | Fail closed, không mặc định tenant |
| Exception trong task | Task throw sau set scope | Job báo lỗi; task kế tiếp thấy EMPTY |
| Interrupted/cancelled | Task hợp tác xử lý interrupt | Sau khi thực sự kết thúc, context cleaned |
| Rejection/queue full | Executor không nhận task | Không báo job đã enqueue; producer xử lý |
| Membership revoked | Enqueue trước revoke, chạy sau | Deny theo execution-time policy |
| Sai resource tenant | URL/job chọn alpha, resource thuộc beta | Deny |
| Role bị thu hồi | Actor còn member nhưng thiếu action | Deny operation |
| Nested tenant khác | Task alpha cố mở beta | Deny hoặc kiểm tra explicit cross-tenant policy |
| Thread pool nhiều workers | Stress 2–8 threads | Không task nào thấy tenant khác |
| Scheduler một tenant | Service identity có scope alpha | Chỉ query alpha |
| Scheduler nhiều tenants | Vòng lặp có cleanup | Mỗi tenant tách rời |
| Queue replay | Cùng jobId/tenant | Idempotent, không làm hai lần |
| DB pooled connections | Pool size 1, xen alpha/beta | Không còn schema/RLS setting trước |
| Cache | Hai tenants có cùng local jobId | Không tráo output |
| MDC | Task success/failure | Tenant label được restore/remove |
| Reactive | Hai subscribers khác scope | Không lẫn khi đổi Scheduler |
| Propagated SecurityContext | Spring executor wrapper | Authentication đúng, cleanup độc lập với tenant |

### Kiểm tra exception path

```java
ExecutorService pool = Executors.newSingleThreadExecutor();
try {
    Future<?> failed = pool.submit(() -> {
        TenantContext.runWith(alphaScope, () -> {
            throw new IllegalStateException("boom");
        });
    });

    assertThrows(ExecutionException.class, failed::get);

    Future<Boolean> clean = pool.submit(
            () -> TenantContext.currentOrNull() == null);

    assertTrue(clean.get());
} finally {
    pool.shutdownNow();
}
```

Đây là **test snippet**, giả định `TenantContext.runWith`, `currentOrNull` và `alphaScope` có sẵn. Nó mô tả đúng chiến lược test bằng worker pool, nhưng không phải một class JUnit độc lập. Bộ Java 17 mục 6 đã triển khai kiểm chứng tương tự mà không cần JUnit.

### Đừng chỉ kiểm tra hai job thành công

Một implementation quên remove vẫn có thể cho kết quả “alpha rồi beta” đúng nếu decorator **luôn set lại** tenant trước mỗi job. Chỉ khi submit một **task quan sát context trống giữa hai job**, hoặc chạy một job không có scope có chủ đích, mới bắt được rò context. Bài test của mục 6 sử dụng chính cách này.

## 21. Tích hợp test với Spring Boot @Async

Ví dụ integration test cần:

- `@EnableAsync` và `ThreadPoolTaskExecutor` thật.
- Scope resolver và tenant decorator thật.
- Một service có `@Async("tenantWorkerExecutor")`, được gọi qua **bean khác/proxy**.
- `CompletableFuture<T>` để chờ task hoàn tất; không dùng `Thread.sleep` làm cách đồng bộ chính.
- Một task điều tra context bên trong worker sau thành công/lỗi.
- `@WithMockUser`/`jwt()` khi cần authentication, nhưng nhớ mock security không xác minh chữ ký JWT thật.
- Active membership có thể thay đổi giữa submit và execute; dùng `CountDownLatch` để điều phối đúng thứ tự.
- Assert DB row IDs/counts và không có side effect của tenant khác, không chỉ assert context string.

Ví dụ cấu trúc (pseudocode):

```text
given:
  alice active in alpha
  doc 11 belongs to alpha
  doc 21 belongs to beta

when:
  submit export(11) with AuthorizedTenantScope(alpha)
  worker waits at latch
  revoke Alice from alpha
  release latch

then:
  worker re-authorizes at execution time
  export denied
  no report/object storage output
  worker context cleaned even after denial
```

Nếu job bắt đầu trước khi quyền bị thu hồi, kết quả phụ thuộc contract consistency; test phải định nghĩa rõ điểm linearization hoặc policy snapshot, không giả định thứ tự theo thời gian wall-clock một cách mơ hồ.

### Spring MVC và async request khác background queue

Spring MVC hỗ trợ async processing và Spring Security có integration riêng với một số async constructs. Điều đó không có nghĩa mọi `@Async`, custom `Executor`, `CompletableFuture`, scheduled task, Kafka listener hay ThreadLocal tenant của ứng dụng **đều tự được propagate**. Test đúng executor/concurrency model đang sử dụng.

## 22. Đường lỗi, timeout và retry

Các tình huống ngoài happy path:

- Task chạy xong nhưng ACK queue thất bại → duplicate delivery.
- Task ném exception sau khi đặt tenant context.
- Task bị interrupt do shutdown/cancel.
- Worker process restart trước khi update job status.
- Pool bị saturated và reject work.
- Database timeout khi đang đặt local tenant setting.
- Membership service tạm không hoạt động.
- Task cố mở transaction mới sau khi request transaction đã đóng.

Nguyên tắc xử lý:

1. **Idempotency** dựa trên tenant + job identity.
2. Giao dịch DB theo ranh giới worker, không dùng entity manager/connection của request thread.
3. Reauthorize ở mỗi execution attempt khi policy yêu cầu.
4. Fail closed khi thiếu tenant hoặc không kiểm chứng được quyền.
5. Đặt timeout hợp lý; bảo đảm tác vụ tôn trọng interruption.
6. Cleanup context luôn ở `finally` của wrapper có hiệu lực.
7. Không log hay trả raw token, credentials và dữ liệu trái tenant trong error.
8. Với dead-letter queue, cần chính sách bảo vệ payload và replay control.

**Quan trọng:** lỗi liên quan membership service không nhất thiết luôn trả “403”; có thể là lỗi vận hành (retry/503) nhưng **không được coi là granted**. Job bị deny do quyền hết hiệu lực khác với job thất bại tạm thời do DB unavailable; ghi reason code chính xác để retry không tạo vòng lặp vô hạn.

## 23. So sánh các cách truyền tenant

| Cách | Phù hợp | Hạn chế/cảnh báo |
| --- | --- | --- |
| Tham số `AuthorizedTenantScope` | Service → repository, rõ ràng | Phải truyền qua các API; không bảo vệ nếu caller tự tạo giả |
| `ThreadLocal` + lexical wrapper | Legacy ORM/servlet, thread-bound code | Cần capture đúng chỗ, cleanup, không tự propagate |
| Spring `TaskDecorator` | `ThreadPoolTaskExecutor`/`@Async` | Chỉ propagate những context đã lập trình; không tự authorize |
| Spring `DelegatingSecurityContext...` | Cần SecurityContext qua thread | Không truyền custom tenant ThreadLocal |
| MDC | Logs/diagnostics | Không dùng làm nguồn authorization |
| Reactor `Context` | WebFlux/reactive | Per-subscription, không phải global và không auto bridge mọi API blocking |
| Durable job command | Kafka/RabbitMQ/DB outbox | Payload không tự trusted; reauth/identity/idempotency |
| Tenant-scoped service identity | Cron/scheduler/automation | Phải giới hạn quyền và audit |
| DB RLS/session-local | Defense in depth ở persistence | Cần DB role/transaction/pooling đúng |
| `InheritableThreadLocal` | Một số thread con mới đơn giản | Không đáng tin cho thread pool/reuse, dễ stale |

**Lựa chọn ưu tiên:** tham số immutable scope tại domain boundary; context wrapper chỉ khi integration framework cần; durable queue dùng job command + consumer re-authorization. Mỗi boundary đều có cleanup và test.

## 24. Checklist áp dụng

- [ ] Authenticated principal được xác minh trước khi resolve tenant.
- [ ] Tenant trong header/path/message là selector, không là bằng chứng quyền.
- [ ] AuthorizedTenantScope chỉ tạo sau membership/role/resource-policy check.
- [ ] Task in-process capture scope ở **submit thread**, không ở pooled worker.
- [ ] Task durable reauthorize ở execution time, không giữ raw bearer token lâu dài.
- [ ] Tenant context cài sát lúc chạy và `remove/restore` trong `finally`.
- [ ] `SecurityContextHolder` và custom `TenantContext` được propagation/cleanup **riêng**.
- [ ] MDC/trace context được restore, không log credentials.
- [ ] Không dùng `InheritableThreadLocal` làm phương án mặc định cho pool.
- [ ] Không dùng static mutable “currentTenant” chung cho các requests.
- [ ] `@Async` được gọi qua Spring proxy và đúng executor.
- [ ] Không tạo fallback tenant khi thiếu scope; fail closed.
- [ ] Worker query/update có tenant predicate; kiểm tra resource tenant authoritative.
- [ ] Connection schema/RLS settings được thiết lập và reset trong transaction/connection.
- [ ] Cache, object storage, idempotency keys và report paths tách tenant.
- [ ] Scheduler/batch có service identity và scope theo từng tenant.
- [ ] Queue consumer xác thực nguồn, validate payload, reauthorize và cleanup.
- [ ] Đã test tuần tự hai tenants **trên cùng thread**.
- [ ] Đã test success, exception, interruption, rejection, revocation và retry.
- [ ] Đã test nhiều workers, MDC, DB connection pool và cache không leak.
- [ ] Có audit và SLA thu hồi quyền cho background jobs.

**Kết luận:** `ThreadLocal`, Reactor Context, SecurityContext và DB session đều là **công cụ mang trạng thái**, không phải nguồn cấp quyền. Ngữ cảnh tenant phải bắt nguồn từ **identity và policy đã xác minh**, được truyền có chủ đích tới worker, được **kiểm tra lại khi job chạy** nếu cần, và được **dọn trong `finally`** hoặc theo lifecycle tương đương. Khi một worker phục vụ hàng nghìn tenants, phép kiểm thử quan trọng nhất là **không task nào nhận được context của task trước**.

## Tài liệu tham khảo chính thức

- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — TaskDecorator JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/TaskDecorator.html)
- [Spring Framework — ContextPropagatingTaskDecorator JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Project Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Spring Security — Reactive Security Context](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [PostgreSQL — Runtime Configuration Functions](https://www.postgresql.org/docs/current/functions-admin.html)
