# Ghi lại nguyên nhân timeout có thể chẩn đoán

> **Chương:** Async verification  
> **Module đào tạo:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Mục tiêu thực hành:** Khi một kiểm thử bất đồng bộ hết hạn, báo cáo phải chỉ ra **đã quan sát được gì, đang mắc tại ranh giới nào và cần kiểm tra bước nào tiếp theo**, thay vì chỉ in `ConditionTimeoutException` sau N giây. Áp dụng cho luồng event sau commit của Spring Modulith, listener, database, retry và CI.

## 1. Một timeout chỉ là triệu chứng: xác định câu hỏi chẩn đoán

Xét test:

~~~java
UUID orderId = orders.place("CUS-42");

await()
        .atMost(Duration.ofSeconds(5))
        .untilAsserted(() ->
                assertThat(fulfillment.find(orderId))
                        .isPresent());
~~~

Khi thất bại, dòng “condition was not fulfilled within 5 seconds” **không cho biết nguyên nhân**. Các sự cố có thể hoàn toàn khác nhau:

| Nhóm nguyên nhân | Tín hiệu cần thấy | Dạng kết luận hợp lệ |
| --- | --- | --- |
| Producer T1 chưa commit | Transaction đang mở, hoặc test `@Transactional` sẽ rollback | Listener hậu commit chưa có điều kiện để chạy |
| Producer đã commit nhưng không publish | Không có `OrderPlaced` đúng ID trong `PublishedEvents` | Cần kiểm tra publication path |
| Event được publish nhưng listener không đăng ký | Thiếu bean/bị exclude khỏi module bootstrap, không có callback | Kiểm tra bootstrap và event handler |
| Listener đã được schedule nhưng chưa bắt đầu | Executor backlog, queue/rejection, thread starvation | Cần kiểm tra executor, không đổ lỗi DB ngay |
| Listener bắt đầu rồi ném exception | Trace `ENTERED → FAILED`; lỗi và correlation ID | Cần kiểm tra handler và transaction T2 |
| Listener trả về nhưng T2 rollback | `RETURNED` có nhưng không thấy row đã commit | Không được gọi `RETURNED` là COMMITTED |
| T2 đã commit, test đọc stale state | DB chính có row, query qua cache/transaction dài/replica vẫn trống | Cần kiểm tra read consistency |
| Publication pending/retry | Registry adapter ghi chưa completed, work item RETRY_WAIT | Event có thể chưa hoàn tất, không tự coi là mất |
| External API chậm hoặc bị rate-limit | Last attempt, error class/code, next retry time | Đang chờ external/retry; không phải lỗi Spring transaction |
| Test tự gây deadlock | Latch không release, lock giữ lúc await, connection pool cạn | Lỗi test fixture, không nhất thiết lỗi sản phẩm |

**Không ghi “root cause: listener missing” khi chỉ biết không tìm thấy dữ liệu.** Dùng nhãn phân biệt: `OBSERVED` (đã thấy), `INFERRED` (suy luận có điều kiện), `UNKNOWN` (thiếu bằng chứng).

### Hợp đồng đầu ra khi timeout

Một báo cáo tốt tối thiểu chứa:

- **Identity:** `testCase`, `orderId`/`eventId`/`testRunId`; ID có thể dùng để ghép log T1 và T2.
- **Expected:** trạng thái nghiệp vụ phải đạt, ví dụ `fulfillment READY`.
- **Observed:** snapshot mới nhất từ public API, trạng thái listener probe, error gần nhất, publication/retry status nếu adapter hỗ trợ.
- **Time:** timeout budget, elapsed monotonic, khoảng thời gian từ event đến lần quan sát cuối.
- **Interpretation:** giai đoạn **không được xác nhận**, không khẳng định một root cause chưa chứng minh.
- **Next action:** xem transaction T1, bean registration, executor, T2 error, DB visibility hoặc registry tùy giai đoạn.

Ví dụ:

~~~text
ASYNC_OUTCOME_TIMEOUT
test=OrderFulfillmentDiagnosticIT.records_useful_timeout
orderId=fa90...
expected=READY
awaitBudgetMs=3000
elapsedMs=3008
lastCommittedView=NOT_OBSERVED
lastReadFailure=NONE
listenerProbe=FAILED
listenerErrorType=DataIntegrityViolationException
listenerThread=shop-async-2
eventPublication=UNKNOWN (adapter not inspected)
interpretation=Listener failed; no committed READY observation
next=Inspect T2 constraint/duplicate event and registry status
~~~

Đây là **định dạng diagnostic do bài học đề xuất**, không phải các field Spring Modulith tự sinh đồng loạt.

## 2. Chụp timeline qua đúng ranh giới transaction, không qua suy đoán

Một luồng `orders → fulfillment` có nhiều mốc khác nhau:

~~~mermaid
sequenceDiagram
    participant T as JUnit
    participant O as orders T1
    participant E as Spring events
    participant X as Async executor
    participant F as fulfillment T2
    participant DB as Database

    T->>O: place(orderId)
    O->>DB: INSERT order
    O->>E: publish OrderPlaced
    O->>DB: COMMIT T1
    O-->>T: Return orderId
    E-->>X: Schedule AFTER_COMMIT listener
    X-->>F: Enter listener
    F->>DB: INSERT fulfillment_task
    F->>DB: COMMIT T2
    T->>DB: Fresh query READY
    DB-->>T: READY
~~~

| Mốc | Bằng chứng cụ thể | Không đủ để kết luận |
| --- | --- | --- |
| `PUBLISHED` | Producer-only test có `PublishedEvents` đúng ID | T1 đã commit, listener bắt đầu |
| `T1_COMMITTED` | Service `@Transactional` hoàn tất qua proxy không có outer transaction; có read committed | T2 đã hoàn tất |
| `LISTENER_ENTERED` | Test probe/structured log ngay đầu callback | Handler đã success |
| `LISTENER_RETURNED` | Method listener chạy đến cuối | Transaction T2 đã commit |
| `T2_COMMITTED` | Query mới qua public API đọc row/state `READY` | External bước kế tiếp đã hoàn thành |
| `REGISTRY_COMPLETED` | Adapter báo completed theo semantics của nó | Mọi business workflow đã DONE |
| `EXTERNAL_DONE` | Receipt/terminal status từ provider | Không có công việc hậu xử lý khác |

**Đặc biệt:** `@ApplicationModuleListener` ở Spring Modulith thông thường là listener hậu commit, bất đồng bộ, có transaction riêng. Nếu listener log “done” **trong method body**, transaction interceptor có thể **chưa commit**. Commit/flush/constraint failure xảy ra sau dòng log đó vẫn có thể khiến T2 rollback. Muốn xác nhận business outcome, dùng public read API với transaction đọc mới; muốn xác nhận listener publication completed, hỏi registry adapter riêng.

### Đồng hồ và thứ tự

- Dùng `System.nanoTime()` để tính elapsed **trong cùng JVM**, không dùng `Instant.now()` trừ rồi suy đoán latency chính xác qua nhiều máy có clock lệch.
- Dùng `Instant` UTC trong log để ghép sự kiện; nếu hệ thống nhiều node, kèm trace/span ID, tránh khẳng định thứ tự tuyệt đối chỉ từ wall-clock timestamps.
- Thời gian được đo từ **mốc định nghĩa rõ** (thời điểm bắt đầu await hoặc ngay sau producer return), không trộn “Spring context startup” với “consumer delay”.
- Một listener có thể chạy và commit rất nhanh trước lúc test thread bắt đầu poll; không nên bắt buộc thấy mọi intermediate state.

### Không để log làm thay đổi nghĩa test

Thêm `Thread.sleep` vào listener để “cho logger kịp ghi” có thể che race. Đừng bắt test await `LISTENER_ENTERED` rồi suy luận `READY`; hai oracle khác nhau. Không dừng hệ thống chỉ để chụp một snapshot ngắn nếu điều đó khiến transaction không thể commit.

## 3. Thiết kế snapshot đủ thông tin nhưng không làm lộ implementation module

Test nên truy cập **public API** của module `fulfillment` để kiểm tra state đã commit. Một diagnostic port của module có thể trả snapshot nhẹ, không export JPA entity hoặc repository `internal`.

**`src/main/java/com/example/shop/fulfillment/FulfillmentState.java`**

~~~java
package com.example.shop.fulfillment;

public enum FulfillmentState {
    PENDING,
    RETRY_WAIT,
    READY,
    FAILED
}
~~~

**`src/main/java/com/example/shop/fulfillment/FulfillmentSnapshot.java`**

~~~java
package com.example.shop.fulfillment;

import java.time.Instant;
import java.util.UUID;

public record FulfillmentSnapshot(
        UUID orderId,
        FulfillmentState state,
        int attempt,
        String lastFailureCode,
        Instant nextAttemptAt,
        Instant updatedAt) {}
~~~

**`src/main/java/com/example/shop/fulfillment/FulfillmentQueries.java`**

~~~java
package com.example.shop.fulfillment;

import java.util.Optional;
import java.util.UUID;

public interface FulfillmentQueries {

    Optional<FulfillmentSnapshot> find(UUID orderId);
}
~~~

Với `Optional.empty()`, diagnostic ghi `NOT_OBSERVED`, **không khẳng định terminal FAILED**. `lastFailureCode` và `nextAttemptAt` có thể null nếu chưa retry; nếu dự án dùng `Optional` hoặc type riêng thì phải giữ API contract nhất quán.

### JPA query đọc snapshot mới

**Khung triển khai nội bộ**:

~~~java
package com.example.shop.fulfillment.internal;

import java.util.Optional;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.shop.fulfillment.FulfillmentQueries;
import com.example.shop.fulfillment.FulfillmentSnapshot;

@Service
class FulfillmentQueryService implements FulfillmentQueries {

    private final FulfillmentTaskRepository repository;

    FulfillmentQueryService(FulfillmentTaskRepository repository) {
        this.repository = repository;
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<FulfillmentSnapshot> find(UUID id) {
        return repository.findById(id)
                .map(task -> new FulfillmentSnapshot(
                        task.orderId(),
                        task.state(),
                        task.attempt(),
                        task.lastFailureCode(),
                        task.nextAttemptAt(),
                        task.updatedAt()));
    }
}
~~~

`FulfillmentTaskRepository` và entity getters là **ports/adapter cần triển khai theo schema thực tế**, không phải code tự chạy khi chưa có model JPA. Mục đích là minh họa **đọc read model đã commit** qua public API. Trong test cần tránh outer `@Transactional` giữ một snapshot/first-level cache cũ qua nhiều polls; dùng transaction đọc ngắn phù hợp isolation.

### Field nào không nên xuất ra?

- Không log request body chứa PII, token, email hoặc raw external exception message có thể chứa secrets.
- Ưu tiên `errorCode`/exception class name được phép công bố, không stringify toàn bộ exception vào báo cáo CI.
- `threadName`, `attempt`, `nextAttemptAt` và `publicationId` là thông tin kỹ thuật; chỉ công bố nếu cần và kiểm soát truy cập.
- `READY` phải được gắn với **bước nghiệp vụ cụ thể**. Nếu listener chỉ enqueue work item, `PENDING` chứng minh ingress đã xử lý, còn `READY` là bước worker sau đó.

## 4. Bổ sung test-only listener probe để nhìn thấy lỗi mất trong async thread

Một test gọi `orders.place(...)` không nhận được exception từ listener bất đồng bộ theo cách gọi Java đồng bộ. Nếu chỉ có Awaitility, exception của worker thường hiện thành timeout mơ hồ. Thêm một **probe ở ranh giới handler** để chụp tiến độ nhưng **không đổi logic retry/rollback**.

**`src/main/java/com/example/shop/fulfillment/internal/ListenerProbe.java`**

~~~java
package com.example.shop.fulfillment.internal;

import java.util.UUID;

interface ListenerProbe {
    void entered(UUID orderId);
    void returned(UUID orderId);
    void failed(UUID orderId, RuntimeException exception);
}
~~~

**`src/main/java/com/example/shop/fulfillment/internal/NoOpListenerProbe.java`**

~~~java
package com.example.shop.fulfillment.internal;

import java.util.UUID;

import org.springframework.stereotype.Component;

@Component
class NoOpListenerProbe implements ListenerProbe {

    @Override
    public void entered(UUID orderId) {}

    @Override
    public void returned(UUID orderId) {}

    @Override
    public void failed(UUID orderId, RuntimeException exception) {}
}
~~~

**`src/main/java/com/example/shop/fulfillment/internal/OrderPlacedListener.java`**

~~~java
package com.example.shop.fulfillment.internal;

import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

import com.example.shop.orders.OrderPlaced;

@Component
class OrderPlacedListener {

    private final FulfillmentProcessor processor;
    private final ListenerProbe probe;

    OrderPlacedListener(
            FulfillmentProcessor processor,
            ListenerProbe probe) {
        this.processor = processor;
        this.probe = probe;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        probe.entered(event.orderId());

        try {
            processor.createTask(event.orderId());
            probe.returned(event.orderId());
        } catch (RuntimeException failure) {
            probe.failed(event.orderId(), failure);
            throw failure; // QUAN TRỌNG: không nuốt lỗi.
        }
    }
}
~~~

`FulfillmentProcessor.createTask(id)` là service/port nội bộ cần implementation JPA; listener và processor chạy theo transaction boundary Spring Modulith đang cấu hình. Không cần biết repository type trong module khác. Hãy giữ `event.orderId()` xuyên mọi log/callback.

### Probe không có quyền tuyên bố COMMITTED

`returned()` được gọi **trước khi proxy hoàn tất transaction T2**. Nếu Hibernate flush/commit thất bại *sau* khi method return, `returned()` vẫn có thể xuất hiện. Vì vậy:

- `ENTERED`: handler đã bắt đầu.
- `RETURNED`: handler đã chạy hết body, **chưa chắc T2 commit**.
- `FAILED`: exception do body bắt được, **không nhất thiết mọi failure ở proxy/commit** đều bị probe quan sát.
- `READY` qua fresh public read: đã nhìn thấy committed side effect theo hợp đồng.
- Registry pending/completed và transaction logs: nguồn bổ sung khi cần tìm failure ngoài body.

**Không catch rồi return bình thường** chỉ để ghi log. Điều đó có thể khiến event registry tưởng handler đã thành công, làm mất khả năng recovery. Bắt lỗi để ghi bằng chứng, rồi rethrow.

### Test probe thread-safe

Đặt test ở cùng package `com.example.shop.fulfillment.internal` để truy cập `ListenerProbe` package-private:

~~~java
package com.example.shop.fulfillment.internal;

import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

final class RecordingListenerProbe implements ListenerProbe {

    record Observation(
            String stage,
            String failureType,
            String thread,
            Instant observedAt) {}

    private final ConcurrentHashMap<UUID, Observation> events =
            new ConcurrentHashMap<>();

    @Override
    public void entered(UUID id) {
        save(id, "ENTERED", "NONE");
    }

    @Override
    public void returned(UUID id) {
        save(id, "RETURNED", "NONE");
    }

    @Override
    public void failed(UUID id, RuntimeException failure) {
        save(id, "FAILED", failure.getClass().getSimpleName());
    }

    String describe(UUID id) {
        Observation observed = events.get(id);
        return observed == null
                ? "NOT_OBSERVED"
                : observed.toString();
    }

    private void save(UUID id, String stage, String error) {
        events.put(id, new Observation(
                stage,
                error,
                Thread.currentThread().getName(),
                Instant.now()));
    }
}
~~~

**Giới hạn:** Map chỉ giữ **quan sát cuối** của một ID. Nếu cùng event được retry và handler gọi `ENTERED` lần hai, lỗi của lần một có thể bị ghi đè. Khi cần phân tích retry, dùng bounded per-ID history/ring buffer, `attempt` và timestamps; không tạo log buffer vô hạn. Test fake/probe được tạo trong test context; không dùng static global state làm lẫn ID khi parallel tests.

## 5. Awaitility có bằng chứng cuối cùng: bọc timeout nhưng giữ nguyên cause

Thay vì:

~~~java
await()
        .atMost(Duration.ofSeconds(5))
        .until(() -> fulfillment.find(orderId)
                .map(s -> s.state() == FulfillmentState.READY)
                .orElse(false));
~~~

hãy tạo helper ghi snapshot đọc được ở **lần poll mới nhất**, lỗi query, trạng thái listener (nếu có) và elapsed time. Helper không phải query DB trong cleanup vô hạn; nó dùng dữ liệu đã quan sát ở vòng poll.

**`src/test/java/com/example/shop/fulfillment/internal/DiagnosticAwaiter.java`**

~~~java
package com.example.shop.fulfillment.internal;

import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;

import org.awaitility.core.ConditionTimeoutException;

import com.example.shop.fulfillment.FulfillmentQueries;
import com.example.shop.fulfillment.FulfillmentState;

final class DiagnosticAwaiter {

    private final FulfillmentQueries queries;
    private final Supplier<String> listenerEvidence;

    DiagnosticAwaiter(
            FulfillmentQueries queries,
            Supplier<String> listenerEvidence) {
        this.queries = queries;
        this.listenerEvidence = listenerEvidence;
    }

    void awaitReady(UUID id, Duration budget) {
        var lastState = new AtomicReference<>("NO_POLL_YET");
        var lastQueryFailure = new AtomicReference<>("NONE");

        long started = System.nanoTime();

        try {
            await()
                    .alias("fulfillment READY orderId=" + id)
                    .atMost(budget)
                    .pollInterval(Duration.ofMillis(50))
                    .until(() -> {
                        var snapshot = queries.find(id);

                        String observed = snapshot
                                .map(Object::toString)
                                .orElse("NOT_OBSERVED");

                        lastState.set(observed);

                        if (snapshot.isPresent()
                                && snapshot.get().state()
                                == FulfillmentState.FAILED) {
                            // Fail fast: FAILED terminal không phải
                            // một lỗi sẽ tự biến thành READY khi poll.
                            throw new TerminalFulfillmentFailure(
                                    "Terminal FAILED for " + id);
                        }

                        return snapshot.isPresent()
                                && snapshot.get().state()
                                == FulfillmentState.READY;
                    });

        } catch (RuntimeException failure) {
            // Bao gồm Awaitility ConditionTimeoutException,
            // terminal failure hoặc lỗi read model.
            if (!(failure instanceof ConditionTimeoutException)
                    && !(failure
                    instanceof TerminalFulfillmentFailure)) {
                lastQueryFailure.set(
                        failure.getClass().getSimpleName());
            }

            long elapsedMs = Duration.ofNanos(
                    System.nanoTime() - started).toMillis();

            String probe = safeEvidence(listenerEvidence);

            String report = """
                    ASYNC_VERIFICATION_FAILURE
                    orderId=%s
                    expected=READY
                    awaitBudgetMs=%d
                    elapsedMs=%d
                    lastCommittedView=%s
                    lastReadFailure=%s
                    listenerProbe=%s
                    causeType=%s
                    """.formatted(
                    id,
                    budget.toMillis(),
                    elapsedMs,
                    lastState.get(),
                    lastQueryFailure.get(),
                    probe,
                    failure.getClass().getSimpleName());

            throw new AssertionError(report, failure);
        }
    }

    private static String safeEvidence(
            Supplier<String> supplier) {
        try {
            return supplier.get();
        } catch (RuntimeException e) {
            return "PROBE_READ_FAILED:"
                    + e.getClass().getSimpleName();
        }
    }

    static final class TerminalFulfillmentFailure
            extends RuntimeException {
        TerminalFulfillmentFailure(String message) {
            super(message);
        }
    }
}
~~~

### Kỹ thuật trong helper này

- `AtomicReference` giữ thông tin cuối cùng mà poll ghi lại; không chỉ hiển thị expected condition.
- `System.nanoTime()` đo thời gian chờ **monotonic**.
- `ConditionTimeoutException` là một nguyên nhân, được giữ trong `AssertionError(report, failure)`, không mất stack trace.
- Khi quan sát trạng thái `FAILED` terminal, helper **ném lỗi không được coi là assertion cần retry** thay vì đợi hết timeout. Điều này giả định `FAILED` thật sự terminal theo workflow contract; nếu application cho phép recovery từ FAILED, phải dùng enum/điều kiện khác.
- `lastReadFailure` cho biết khi predicate ném runtime exception; nếu cần retry tạm thời lỗi query, cấu hình chính sách khác và ghi reason riêng, không `ignoreExceptions()` vô điều kiện.
- `listenerEvidence` đọc in-memory test probe, không gọi network/DB chậm trong catch block. Nếu probe bị lỗi, báo `PROBE_READ_FAILED` mà vẫn giữ timeout gốc.
- Nếu query thành công rồi trả `NOT_OBSERVED` hết hạn, report **không gán nguyên nhân**; nó cung cấp evidence cho bước điều tra tiếp theo.

### Một điểm cần nhận thức về Awaitility

`until(...)` theo mặc định không đồng nghĩa mọi exception được retry. Với `RuntimeException` không được bỏ qua, Awaitility thường phát exception ra ngoài; helper gói nguyên nhân và snapshot. Nếu version/ứng dụng bật `ignoreExceptions` toàn cục, có thể biến lỗi DB hoặc lỗi terminal thành timeout, làm mất fail-fast. Vì vậy **không bật ignore-all exceptions** cho các test này; nếu thật sự cần ignore một exception transient, khai báo đúng type và vẫn lưu diagnostic.

### Không tạo “double timeout” bằng helper

Một test đã có `@Timeout` toàn method và Awaitility budget phải để đủ phần còn lại cho cleanup. `ConditionTimeoutException` **không dừng listener thread**; đừng shutdown Spring-managed executor trong `finally`. Dùng `orderId` riêng, evidence và fixture isolation khi consumer còn retry.

## 6. JUnit kiểm tra chính chất lượng báo cáo timeout

Bài test về diagnostic phải có **negative control**: cố tình tạo tình huống không thể đạt `READY`, nhưng vẫn assert report chứa ID, trạng thái cuối, evidence và cause. Nếu không, một thay đổi sau này có thể khiến hệ thống quay về thông báo “timed out” vô nghĩa.

### Unit test rất ngắn cho đường timeout

**`src/test/java/com/example/shop/fulfillment/internal/DiagnosticAwaiterTest.java`**

~~~java
package com.example.shop.fulfillment.internal;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

import org.junit.jupiter.api.Test;

import com.example.shop.fulfillment.FulfillmentQueries;
import com.example.shop.fulfillment.FulfillmentSnapshot;
import com.example.shop.fulfillment.FulfillmentState;

class DiagnosticAwaiterTest {

    @Test
    void timeout_report_has_identity_last_view_and_listener_evidence() {
        UUID id = UUID.randomUUID();

        FulfillmentQueries noCommittedTask =
                ignored -> Optional.empty();

        var awaiter = new DiagnosticAwaiter(
                noCommittedTask,
                () -> "stage=FAILED, failureType=IllegalStateException");

        assertThatThrownBy(() ->
                awaiter.awaitReady(
                        id, Duration.ofMillis(180)))
                .isInstanceOf(AssertionError.class)
                .hasMessageContaining("ASYNC_VERIFICATION_FAILURE")
                .hasMessageContaining("orderId=" + id)
                .hasMessageContaining("expected=READY")
                .hasMessageContaining(
                        "lastCommittedView=NOT_OBSERVED")
                .hasMessageContaining("listenerProbe=stage=FAILED")
                .hasCauseInstanceOf(
                        org.awaitility.core.ConditionTimeoutException.class);
    }

    @Test
    void terminal_failure_is_not_disguised_as_timeout() {
        UUID id = UUID.randomUUID();

        FulfillmentQueries terminal = ignored -> Optional.of(
                new FulfillmentSnapshot(
                        id,
                        FulfillmentState.FAILED,
                        3,
                        "RETRY_EXHAUSTED",
                        null,
                        Instant.now()));

        var awaiter = new DiagnosticAwaiter(
                terminal,
                () -> "stage=RETURNED");

        assertThatThrownBy(() ->
                awaiter.awaitReady(
                        id, Duration.ofSeconds(2)))
                .isInstanceOf(AssertionError.class)
                .hasMessageContaining("state=FAILED")
                .hasMessageContaining(
                        "causeType=TerminalFulfillmentFailure");
    }
}
~~~

Hai phép thử chỉ xác nhận chất lượng diagnostic path và không cần dựng Spring context, Kafka hay PostgreSQL. Khi nhận trạng thái `FAILED` terminal, helper phải báo `TerminalFulfillmentFailure` thay vì biến lỗi thành một timeout thông thường.

### Integration test dùng listener thật, failure probe test-only

Trong test nằm ở `com.example.shop.fulfillment.internal`, dùng nested `@TestConfiguration` để thay probe no-op bằng recorder và inject failure vào processor **chỉ trong test context**:

**`src/test/java/com/example/shop/fulfillment/internal/AsyncTimeoutDiagnosticIT.java`**

~~~java
package com.example.shop.fulfillment.internal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;

import com.example.shop.ShopApplication;
import com.example.shop.orders.OrderCommands;
import com.example.shop.fulfillment.FulfillmentQueries;

@SpringBootTest(
        classes = ShopApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(AsyncTimeoutDiagnosticIT.FailureConfig.class)
class AsyncTimeoutDiagnosticIT {

    @Autowired OrderCommands orders;
    @Autowired FulfillmentQueries fulfillment;
    @Autowired RecordingListenerProbe recorder;

    @Test
    void reports_listener_failure_instead_of_anonymous_timeout() {
        UUID id = orders.place("CUS-" + UUID.randomUUID());

        // Chờ probe ghi nhận lỗi của callback bất đồng bộ.
        await()
                .atMost(Duration.ofSeconds(3))
                .until(() ->
                        recorder.describe(id).contains("stage=FAILED"));

        var awaiter = new DiagnosticAwaiter(
                fulfillment, () -> recorder.describe(id));

        assertThatThrownBy(() ->
                awaiter.awaitReady(id, Duration.ofMillis(250)))
                .isInstanceOf(AssertionError.class)
                .hasMessageContaining("orderId=" + id)
                .hasMessageContaining("listenerProbe=")
                .hasMessageContaining("stage=FAILED")
                .hasMessageContaining(
                        "failureType=IllegalStateException");
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FailureConfig {

        @Bean
        @Primary
        RecordingListenerProbe recordingListenerProbe() {
            return new RecordingListenerProbe();
        }

        @Bean
        @Primary
        FulfillmentProcessor failingProcessor() {
            return id -> {
                throw new IllegalStateException(
                        "Simulated listener failure");
            };
        }
    }
}
~~~

Để code có nghĩa đầy đủ, `FulfillmentProcessor` là interface nội bộ:

~~~java
package com.example.shop.fulfillment.internal;

import java.util.UUID;

interface FulfillmentProcessor {
    void createTask(UUID orderId);
}
~~~

Một adapter JPA thực sẽ implement `FulfillmentProcessor` và lưu task; trong test trên bean `@Primary` thay behavior bằng exception. Test không bật resubmission tự động trong thời gian chạy; nếu registry tự replay ngay, recorder cần lưu history theo ID thay vì snapshot cuối để tránh lost `FAILED` signal.

### Vì sao negative-control integration test có ích?

Nếu có bug làm listener không được bootstrap, recorder sẽ không thấy `FAILED` và test fail ở mốc **listener chưa chạy**. Nếu listener được gọi nhưng exception bị swallow, recorder/registry sẽ cho hình ảnh không phù hợp. Nếu listener ném exception như chủ định, test xác nhận **ID, phase và failure class** xuất hiện trong thông báo báo lỗi, không cần một `Thread.sleep(5_000)`.

**Đây là test cố ý kỳ vọng một failure, nên suite vẫn xanh** khi báo cáo chứa đúng nội dung. Đừng để một test thất bại vô điều kiện trong CI chỉ nhằm “xem log”.

### Một caveat về wiring

- Cần implementation thật của `OrderCommands`, read model và Spring Modulith events/JPA trong dự án để chạy integration code.
- `@Primary` chỉ chọn bean nếu injection thực sự dựa trên interface `FulfillmentProcessor`, không bị qualifier khác ưu tiên.
- Nếu một bean production processor đã dùng tên giống test bean, xử lý bean naming/override theo cấu hình; không bật global bean overriding chỉ vì dễ hơn.
- Không gắn `@Transactional` outer lên test method; event hậu commit cần T1 commit thật.
- Test kiểm tra diagnostic không nhất thiết xác minh persistent Event Publication Registry. Kiểm chứng registry là bài riêng ở mục 8.

## 7. Failure injection phải tạo các mẫu bằng chứng khác nhau

Một báo cáo tốt chỉ có giá trị nếu hai nguyên nhân khác nhau tạo **dấu vết khác nhau**.

### Ma trận test đối chiếu với nguyên nhân

| Injection | Producer | Probe | Read model | Cần kết luận thế nào |
| --- | --- | --- | --- | --- |
| Bỏ `publishEvent` | T1 commit | `NOT_OBSERVED` | `NOT_OBSERVED` | Không đủ evidence publication; kiểm tra producer test |
| Listener không được bootstrap | Publish có | `NOT_OBSERVED` | `NOT_OBSERVED` | Kiểm tra bean registration/module slice |
| T1 rollback sau publish | ROLLBACK | Listener hậu commit không entered | No committed row/task | Kiểm tra transaction boundary và phase |
| Executor bị chặn trước callback | T1 commit | `NOT_OBSERVED` hoặc queued signal | Chưa có READY | Scheduling/backlog, chưa phải handler failure |
| Handler ném exception trong body | T1 commit | `FAILED` + class | Có thể `NOT_OBSERVED` | Handler T2 lỗi; kiểm tra registry và DB |
| Constraint fail khi transaction T2 commit | T1 commit | Có thể `RETURNED` | Không thấy READY | Probe body không quan sát được commit failure |
| Gateway timeout, retry pending | T1 commit | `ENTERED/RETURNED` tùy thiết kế | `RETRY_WAIT`, attempt/nextRetryAt | Đang retry, không được tự gọi event lost |
| Reader giữ stale transaction/cache | T1/T2 đã commit | Probe có thể RETURNED | Public query vẫn cũ | Read consistency/transaction caching |
| Test giữ commit gate không release | T1 còn mở | Chưa entered | Chưa READY | Test-induced deadlock |
| Test dùng một connection pool cho hai threads | T1 giữ connection | Chưa rõ | Query bị block | Pool starvation, không phải event loss |

Không dựa vào `@ApplicationModuleListener` annotation để **đoán** mọi mốc. Ghi ít nhất một oracle cho producer, một cho listener và một cho committed business state. Nếu không có quyền instrument listener, diagnostic vẫn có thể báo rõ “listener status UNKNOWN; needs logs/trace”, thay vì giả tạo `NOT_STARTED`.

### Test producer riêng với PublishedEvents

~~~java
package com.example.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

@ApplicationModuleTest
class OrderPublicationTest {

    @Autowired OrderCommands orders;

    @Test
    void publishes_order_placed(PublishedEvents events) {
        UUID id = orders.place("CUS-PUBLICATION");

        assertThat(events.ofType(OrderPlaced.class))
                .anySatisfy(e ->
                        assertThat(e.orderId()).isEqualTo(id));
    }
}
~~~

Cần import `java.util.UUID` và public contract `orders.OrderPlaced`. `anySatisfy` chỉ chứng minh **ít nhất một** event khớp. `@ApplicationModuleTest` đặt trong producer module có thể **không bootstrap consumer**; không dùng test publication này làm bằng chứng listener hoặc T2 thành công.

### Rollback ngoài ý muốn do @Transactional trên test

Phản mẫu:

~~~java
@Transactional
@Test
void waits_for_after_commit_but_test_transaction_rolls_back() {
    UUID id = orders.place("CUS-ROLLBACK");

    await().atMost(Duration.ofSeconds(5))
            .until(() -> fulfillment.find(id)
                    .map(s -> s.state() == FulfillmentState.READY)
                    .orElse(false));
}
~~~

Nếu `orders.place` tham gia outer test transaction với propagation `REQUIRED`, Spring Test có thể rollback khi method test kết thúc; listener `AFTER_COMMIT` không có cơ hội chạy. Diagnostic nên chứa **“T1 commit not confirmed / outer test transaction active”**, thay vì kết luận thiếu listener.

### Trường hợp listener RETURNED nhưng DB chưa READY

Một test có thể log `RETURNED` rồi vẫn timeout nếu transaction commit của consumer fail **sau method body**. Chẩn đoán:

1. Kiểm tra exception từ transaction interceptor/asynchronous execution.
2. Kiểm tra database constraint, rollback logs, deadlock/connection timeout.
3. Nếu có publication registry persistent, kiểm tra record chưa completed.
4. Query lại business state trong transaction độc lập; tránh persistence context cũ.
5. Chỉ khi có evidence mới kết luận root cause là DB failure.

**Không sửa `RETURNED` thành `COMMITTED` chỉ để report trông dễ đọc.**

### Kỹ thuật latch để phân biệt “chưa được gọi” và “đang bị chặn”

Với test-only processor:

~~~java
CountDownLatch entered = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);

FulfillmentProcessor blocked = orderId -> {
    entered.countDown();
    try {
        if (!release.await(3, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                    "Test-controlled worker gate expired");
        }
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException(
                "Worker interrupted", interrupted);
    }
};

try {
    UUID id = orders.place("CUS-BLOCKED");

    assertThat(entered.await(2, TimeUnit.SECONDS)).isTrue();
    // Probe=ENTERED nhưng READY chưa được xác nhận.
    // Diagnostic có thể nói đang ở handler.
} finally {
    release.countDown();
}
~~~

Đây là **skeleton được wire vào test context**, không phải chương trình độc lập. `finally` phải release gate; nếu không test sẽ gây background work leak và ảnh hưởng Testcontainers teardown. Với listener production, không dùng latch làm “cơ chế sửa” timeout.

## 8. Lấy bằng chứng từ retry và Event Publication Registry mà không bịa API

Spring Modulith Event Publication Registry có thể theo dõi event publications chưa completed và được hoàn tất theo contract của listener/adapter. Cấu hình persistent registry, API inspect/recovery và tên bảng **khác nhau theo version/adapter**.

### Tách các trạng thái

| Bằng chứng | Điều có thể kết luận | Không được suy diễn |
| --- | --- | --- |
| `PublishedEvents` có `OrderPlaced` | Producer publish trong test | T1 commit, listener chạy |
| Registry có publication pending | Chưa marked completed theo adapter | Event chắc chắn “mất” |
| Registry completed | Handler xử lý theo registry semantics | External async worker đã READY |
| Probe `ENTERED` | Listener method bắt đầu | T2 commit |
| Probe `FAILED` | Exception trong body đã được quan sát | Toàn bộ error sau transaction proxy được ghi |
| Read model `RETRY_WAIT` | Workflow chờ retry theo persisted state | Scheduler chắc chắn sẽ chạy đúng hạn |
| Read model `READY` | Business outcome visible | Không còn duplicate/replay |
| Test timeout | Deadline quan sát hết | Listener đã bị cancel |

### Adapter diagnostics có kiểm soát

Một **test-only/observability facade** nên cung cấp mệnh đề có giới hạn, ví dụ:

~~~java
// Pseudocode: phải triển khai theo adapter/version đang dùng.
record PublicationDiagnostic(
        UUID orderId,
        String state,
        String targetListener,
        int knownAttemptCount,
        Instant lastUpdatedAt) {}

interface PublicationDiagnosticReader {
    Optional<PublicationDiagnostic> byOrderId(UUID orderId);
}
~~~

API `byOrderId` trong ví dụ **không phải phương thức Spring Modulith luôn có sẵn**. Nếu adapter không lưu attempt count, để `UNKNOWN` thay vì đoán 0; nếu một event fan-out tới nhiều listeners, có thể có **nhiều publication records cho cùng event ID**, cần group theo listener target và publication ID.

### Retry timeline cần tách ở ba lớp

~~~text
T1_COMMIT OrderPlaced(orderId)
  publication target=fulfillment created
  listener invocation #1 -> failure in T2
  publication still pending (if supported/configured)
  listener invocation #2 after resubmit -> returned
  registry completed for this target
  work item RETRY_WAIT (gateway attempt 2)
  external provider success -> READY
~~~

- **Listener invocation count** khác **gateway attempt count**.
- **Publication completed** khác **work item READY**.
- `FAILED` có thể là terminal hoặc tạm thời tùy state machine; báo cáo cần policy cụ thể.
- Một event có thể được xử lý nhiều lần; `orderId`, event ID và idempotency key giúp nối trace qua attempts.
- Nếu handler bắt exception rồi không rethrow, registry có thể đánh dấu completed sai, làm mất cơ hội recovery.

### Không lấy root cause bằng cách xóa publication

Nếu registry pending khi test timeout, **không xóa pending record để cleanup** trước khi chụp trạng thái. Làm như vậy xóa dấu vết cần điều tra, có thể phá reliability test. Khi dữ liệu thuộc môi trường test disposable, dọn theo lifecycle đã được cô lập và sau khi đã lưu diagnostic.

### Bắt lỗi ở đúng mức độ

| Failure location | Cách chẩn đoán |
| --- | --- |
| Producer trước event | Assertion/exception cùng thread producer |
| Listener method body | Test-only probe + structured logs; giữ exception |
| Transaction commit sau listener return | Transaction/JPA logs + registry pending + fresh DB read |
| External gateway | HTTP status/timeout class, attempt, idempotency key; không log token |
| Retry scheduler | `nextAttemptAt`, due job count, scheduling telemetry |
| Event replay | Publication ID, listener target, completed/pending |
| Read path | DataSource/read replica/cache/isolation diagnostics |

**Nguyên tắc:** Báo cáo có bằng chứng bao nhiêu nói bấy nhiêu. `UNKNOWN` là kết luận kỹ thuật tốt hơn một “root cause” sai.
## 9. Structured logs, tracing và quality gate CI

Thông báo lỗi của JUnit là **điểm bắt đầu điều tra**, không phải toàn bộ hệ thống observability. Khi listener chạy ở thread khác hoặc sau resubmit, cần correlation ID bền qua những boundary đó.

### Ghi log có cấu trúc ngay tại event boundary

Ví dụ trong listener có `OrderPlaced` công khai:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(OrderPlacedListener.class);

@ApplicationModuleListener
void on(OrderPlaced event) {
    UUID id = event.orderId();

    log.info("async_stage={} orderId={} eventType={} thread={}",
            "LISTENER_ENTERED",
            id,
            "OrderPlaced",
            Thread.currentThread().getName());

    probe.entered(id);

    try {
        processor.createTask(id);

        log.info("async_stage={} orderId={}",
                "LISTENER_RETURNED_NOT_YET_COMMIT_CONFIRMED", id);
        probe.returned(id);
    } catch (RuntimeException e) {
        log.error("async_stage={} orderId={} errorType={}",
                "LISTENER_FAILED_IN_BODY",
                id,
                e.getClass().getSimpleName());

        probe.failed(id, e);
        throw e;
    }
}
~~~

Cần imports `org.slf4j.Logger`, `org.slf4j.LoggerFactory` và `java.util.UUID`; snippet này thay body listener ở mục 4. Đặt stage name **đúng thực tế**, không log `T2_COMMITTED` khi phương thức còn nằm trong transaction interceptor. Nếu cần stack trace trong log nội bộ được phép, có thể truyền throwable làm tham số cuối và áp dụng chính sách redaction/retention của đội ngũ.

### MDC và @Async

SLF4J `MDC` thường là thread-local; **không giả định MDC từ producer thread tự chuyển sang async listener**. Có thể dùng `TaskDecorator` khi application kiểm soát executor, hoặc tracing instrumentation phù hợp để truyền context. Tuy nhiên:

- Event payload nên mang business correlation `orderId` hoặc event ID để còn truy vết sau restart/resubmit, không chỉ tin vào MDC.
- `TaskDecorator` phải copy/restore/clear context đúng scope, tránh ID từ task trước rò sang task sau.
- Với persisted/replayed events, cần đọc lại correlation từ event metadata/payload; thread-local không bền qua restart.
- Không đưa PII, access token, card number hay raw request body vào MDC hoặc build failure message.

### Log level theo giai đoạn

| Giai đoạn | Mức phổ biến | Dữ liệu |
| --- | --- | --- |
| Producer accepted/published | INFO/DEBUG | `orderId`, event type, trace ID |
| Listener entered | DEBUG | `orderId`, handler target, thread |
| Listener failed | ERROR/WARN theo retry policy | Error **class/code**, ID, attempt |
| Retry scheduled | INFO/DEBUG | `nextAttemptAt`, attempt, delay |
| T2 outcome | INFO/DEBUG hoặc metric | READY/FAILED, committed state |
| Timeout test | ERROR trong CI output | Last state, phase, elapsed, diagnostics |
| Registry pending | Metric/health signal | Count, age, target listener |

Đối với high-volume consumers, không log INFO cho mọi poll của Awaitility (có thể tạo nhiều log và làm test chậm). Để helper giữ **last snapshot** trong bộ nhớ và chỉ in **một báo cáo khi fail**. Khi cần full timeline, dùng bounded ring buffer theo ID.

### CI artifacts phải đủ để tái hiện

Ví dụ một failure artifact không chứa secrets:

~~~text
case=AsyncTimeoutDiagnosticIT.records_useful_timeout
runId=ci-4821
orderId=...
expected=READY
awaitBudgetMs=3000
lastCommittedView=FulfillmentSnapshot[state=PENDING,attempt=1]
listenerStage=FAILED
listenerFailure=IllegalStateException
publicationState=PENDING
replayAttempts=1
nextRetryAt=2026-11-26T03:25:00Z
readError=NONE
readSource=primary-db
classification=OBSERVED_LISTENER_FAILURE
followUp=Inspect handler exception and publication target
~~~

`publicationState`, `replayAttempts` và `readSource` **chỉ được điền khi instrument/adapter thực sự cung cấp**. Nếu không, ghi `UNKNOWN`. Để tránh báo cáo đánh tráo dữ liệu, tách các trường **expected**, **observed**, **inferred**.

### Các tầng timeout phải được đo tách biệt

| Budget | Nó giới hạn | Không được gọi là |
| --- | --- | --- |
| Spring context bootstrap | Start context, bean wiring, migrations | Listener execution time |
| Testcontainers readiness | Database/container ready | Business event latency |
| Producer transaction | T1 commit/rollback | Consumer T2 complete |
| Awaitility `atMost` | Thời hạn quan sát business outcome | Cancellation của listener |
| Gateway call timeout | Một call HTTP/JDBC | Toàn retry lifecycle |
| Retry due time | Khi công việc tiếp theo đến hạn | Event đã mất |
| JUnit `@Timeout` | Test method scope theo JUnit | Tắt toàn bộ Spring executor |
| CI job timeout | Toàn bước pipeline | Root cause của từng event |

Nếu JUnit timeout kích hoạt trước khi helper tạo báo cáo, outer budget có thể quá thấp so với producer + await + cleanup; cần cấu hình có cơ sở. **Không tăng mọi timeout** để che handler failure, DB lock hoặc test tự giữ latch.

### Quality gate theo bằng chứng

~~~mermaid
flowchart LR
    PR["Pull request"] --> A["ApplicationModules.verify()"]
    A --> PUB["@ApplicationModuleTest PublishedEvents"]
    PUB --> IT["Async state + diagnostic IT"]
    IT --> FI["Failure-injection diagnostic tests"]
    FI --> REG["Retry/registry reliability"]
    REG --> G{"Gates và diagnostics đạt?"}
    G -- "Có" --> OK["Merge / release"]
    G -- "Không" --> FIX["Điều tra bằng correlation ID"]
~~~

Kiểm chứng kiến trúc vẫn độc lập:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void verifies_public_module_boundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Trong codebase module, `fulfillment` nên import public `orders.OrderPlaced` thay vì `orders.internal.persistence.OrderRepository`. `ApplicationModules.verify()` bảo vệ ranh giới package/dependency, **không** chứng minh listener xử lý thành công. CI cần **cả architecture gate lẫn async diagnostic integration**.

### Negative controls cho quality gate

1. Bỏ `publishEvent`: producer `PublishedEvents` test phải fail, diagnostic listener có thể `NOT_OBSERVED`.
2. Thay listener bằng bean không được scan: integration diagnostic phải phân biệt không có callback với callback FAILED.
3. Cho processor ném exception: probe `FAILED` phải xuất hiện, exception được rethrow.
4. Làm hỏng constraint ở commit T2: probe có thể `RETURNED` nhưng READY không visible; diagnostic không được tuyên bố T2 committed.
5. Cho reader stale: test cần cho thấy khác biệt giữa primary DB và read path.
6. Chờ retry lâu: diagnostic phải báo `RETRY_WAIT`/`nextRetryAt` chứ không nói event lost.
7. Cho worker bị block: report cần stage `ENTERED` và mốc timeout, không tắt global executor để cleanup.

**Không để test negative control cố tình đỏ trên branch chính.** Viết phép thử có chủ đích kỳ vọng báo cáo failure/diagnostic, để CI vẫn xanh khi hệ thống phát hiện đúng loại lỗi.

## 10. Troubleshooting, bài thực hành và checklist hoàn thành

### Quy trình chẩn đoán năm nhánh

Khi một test timeout, không sửa bằng `Thread.sleep` trước tiên. Đi theo thứ tự dưới đây:

~~~mermaid
flowchart TD
    T["Timeout: READY chưa thấy"] --> P{"T1 đã commit và publish?"}
    P -- "Chưa/không rõ" --> A["Kiểm tra producer transaction, PublishedEvents"]
    P -- "Có" --> L{"Listener ENTERED?"}
    L -- "Không/UNKNOWN" --> B["Kiểm tra module bootstrap, executor, listener registration"]
    L -- "Có" --> F{"FAILED trong body?"}
    F -- "Có" --> C["Xem exception, T2 rollback, pending publication"]
    F -- "Không hoặc RETURNED" --> D{"READY qua primary read?"}
    D -- "Có" --> E["Sửa stale read, cache/replica/transaction"]
    D -- "Không" --> R["Kiểm tra T2 commit, retry/backoff, DB locks"]
~~~

**Nhánh không có thông tin:** Nếu test không có probe/registry, ghi `UNKNOWN`, giữ ID và bước điều tra tương ứng. “Không có record” không tự chứng minh “listener chưa bao giờ chạy”.

### Bảng triệu chứng ↔ điều cần xác minh

| Báo cáo thấy | Nguyên nhân có thể | Bước kiểm tra tiếp |
| --- | --- | --- |
| `lastCommittedView=NOT_OBSERVED`, probe UNKNOWN | Producer chưa commit, listener chưa boot, executor queue, missing event | `PublishedEvents`, service transaction, listener bean |
| Probe `ENTERED` nhưng view không đổi | Handler kẹt, chờ lock/external API hoặc transaction chưa commit | Thread dump, DB locks, transaction logs |
| Probe `RETURNED` nhưng READY không xuất hiện | T2 commit failure, write vào DB khác, stale reader | Constraint logs, primary DB query |
| Probe `FAILED` với `DataIntegrityViolationException` | Unique constraint, duplicate/replay, invalid data | Key constraint, idempotency, registry |
| `RETRY_WAIT`, nextRetryAt tương lai | Retry theo policy, không phải event lost | Attempt schedule và deadline |
| Registry pending, business NOT_OBSERVED | Handler fail hoặc chưa completed theo adapter | Pending publication ID/target, recovery |
| Registry completed, business PENDING | Listener chỉ enqueue work | Test downstream worker riêng |
| Producer test xanh, consumer IT đỏ | Producer publication đúng, consumer/bootstrap lỗi | Listener registration và T2 |
| Local pass, CI timeout | Pool starvation, I/O chậm, shared fixture, context/container race | Metrics queue, DB pool, Testcontainers lifecycle |
| Sau timeout row xuất hiện muộn | Awaitility không cancel worker | Correlation ID, fixture isolation |
| Test `@Transactional` không kích hoạt AFTER_COMMIT | Outer test transaction rollback | Loại outer transaction hoặc explicit commit |
| Query đọc stale snapshot | First-level cache, long transaction, read replica | Fresh read/primary, isolation |
| CI log thiếu correlation ID | MDC không propagate vào async thread | Event metadata, TaskDecorator/tracing |
| Handler failure biến thành timeout | Async exception không đi về test thread | Probe/rethrow, adapter failure state |

### Bài thực hành

**Bài A — Bảo đảm timeout cung cấp bằng chứng**

Dùng `DiagnosticAwaiterTest` ở mục 6. Đổi expected `READY` thành kết quả không bao giờ xảy ra, xác nhận report có `orderId`, last state, listener evidence và `ConditionTimeoutException` là cause. Không đo exact wall-clock time bằng `assertThat(elapsed).isEqualTo(...)`.

**Bài B — Listener lỗi và rollback**

Chạy `AsyncTimeoutDiagnosticIT` với processor ném `IllegalStateException`. Xác nhận probe `FAILED` nhưng public read vẫn `NOT_OBSERVED`. Giải thích vì sao rethrow cần thiết để registry/transaction biết invocation thất bại.

**Bài C — RETURNED nhưng không commit**

Dùng constraint hoặc failure injection tại DB commit T2 trong môi trường riêng. Xác nhận probe có thể `RETURNED` trước khi transaction fail; báo cáo không được đổi stage thành `COMMITTED`. Chỉ public query mới là oracle committed side effect.

**Bài D — Không có listener**

Tạm exclude listener khỏi một context test chuyên biệt. Producer `PublishedEvents` vẫn có thể xanh nhưng async integration hết hạn; diagnostic phải báo `listenerProbe=NOT_OBSERVED` và gợi ý kiểm tra module bootstrap thay vì khẳng định listener exception.

**Bài E — Retry chờ có chủ đích**

Tạo work item `RETRY_WAIT` với `attempt=2` và `nextAttemptAt` tương lai. Assert diagnostic hiển thị đủ ba trường; không chạy sleep tới thời điểm đó chỉ để quan sát hiện trạng.

**Bài F — Kiểm tra đọc stale**

Cho T2 commit task vào PostgreSQL, nhưng test giữ một transaction đọc cũ/cached view. So sánh với query transaction mới/primary; phân biệt reader bug với listener bug. Không bypass public module API trong production code.

**Bài G — MDC và correlation**

Log producer trên thread test và listener trên thread async. Xác nhận `orderId` xuất hiện ở cả hai qua event payload, ngay cả khi MDC không được propagate. Nếu dùng `TaskDecorator`, kiểm tra cleanup context giữa tasks.

**Bài H — Retry/publication registry**

Cho listener fail, kiểm tra publication pending theo adapter thực. Ghi publication ID/target và diagnostic; trigger recovery bằng API được dự án hỗ trợ thay vì đợi production timer. Không xóa pending trước khi lưu bằng chứng.

**Bài I — Quality gate**

Chạy `ApplicationModules.verify()`, producer module test, async integration và negative-control diagnostic tests. Tạm sửa consumer import `orders.internal` để architecture gate đỏ; sau đó khôi phục.

### Checklist đánh giá bài test timeout

- [ ] Test dùng correlation `orderId`/event ID riêng cho mỗi execution.
- [ ] Báo cáo ghi **expected** và **last observed** riêng.
- [ ] Ghi `elapsedMs` từ `System.nanoTime()` và timeout budget rõ.
- [ ] Không gộp producer publish, T1 commit, listener entered và T2 commit.
- [ ] `RETURNED` không bị đặt tên nhầm là `T2_COMMITTED`.
- [ ] Snapshot read model được lấy mới trong mỗi poll, không giữ boolean cũ.
- [ ] Trạng thái `NOT_OBSERVED` không bị gán là terminal FAILED.
- [ ] Lỗi đọc DB không bị `ignoreExceptions` vô điều kiện che mất.
- [ ] Async handler failure được ghi an toàn và rethrow.
- [ ] Probe thread-safe, theo từng event ID, không dùng static shared state thiếu isolation.
- [ ] Có bounded retry history khi cần, không tạo map/log vô hạn.
- [ ] Báo cáo giữ nguyên cause, không replace stack trace bằng string.
- [ ] Khi listener probe lỗi, report vẫn giữ original timeout.
- [ ] Có test kiểm tra chất lượng **chính report**, không chỉ test outcome.
- [ ] Có phân biệt missing listener, executor queue, T2 exception, stale DB read.
- [ ] Với persistent registry, status được lấy qua đúng adapter/version; UNKNOWN nếu không có dữ liệu.
- [ ] Không gọi registry completed là toàn bộ external workflow completed.
- [ ] Không log PII, token hoặc raw exception message không kiểm duyệt.
- [ ] MDC/thread-local được xử lý đúng khi đi qua `@Async`.
- [ ] Không dùng `Thread.sleep` để thay instrumentation/synchronization.
- [ ] Timeout của Awaitility khác cancellation của worker.
- [ ] Không shutdown shared Spring executor từ teardown một test method.
- [ ] Có isolation cho DB/Testcontainers/fixtures nếu worker còn retry.
- [ ] `@ApplicationModuleTest` + `PublishedEvents` bảo vệ producer contract.
- [ ] `ApplicationModules.verify()` và CI quality gate vẫn độc lập.

**Ghi nhớ:** Một timeout có thể chẩn đoán là một **báo cáo bằng chứng có giới hạn**, không phải một lời đoán. Hãy ghép `orderId` xuyên transaction T1, event publication, executor, listener T2 và public read model; lưu last snapshot và handler failure; giữ nguyên exception gốc; và ghi `UNKNOWN` khi hạ tầng không cung cấp trạng thái. Từ đó có thể phân biệt lỗi scheduling, rollback, retry, stale read và test fixture một cách có hệ thống mà không làm kiểm thử Spring Modulith chậm hơn hoặc che hồi quy kiến trúc.




