# Idempotency khi tự động hóa thao tác quản trị bằng Spring Framework JMX

## 1. Tổng quan

JMX là một kênh quản trị hữu ích để đọc trạng thái JVM và điều khiển ứng dụng Spring. Spring MBeanExporter cho phép công bố các thuộc tính và operation qua MBeanServer. Khi người vận hành bấm một thao tác trên JConsole, thông thường họ quan sát kết quả ngay. Nhưng khi một agent tự động gọi operation qua MBeanServerConnection theo lịch hoặc trong lúc xử lý sự cố, việc timeout, retry và cạnh tranh có thể tạo ra tác động trùng lặp.

Ví dụ một operation restartWorker() được gọi từ automation. Nếu server đã thực hiện restart nhưng phản hồi bị mất trên kết nối RMI, client tưởng request thất bại và gọi lại. Hai lần restart nối tiếp có thể làm ứng dụng gián đoạn lâu hơn và thậm chí mất những công việc vừa khôi phục.

**Idempotency là tính chất của nghiệp vụ quản trị, không phải bảo đảm mặc định của JMX.** Thiết kế API phải giúp automation nhận biết trạng thái mong muốn, phân biệt request mới với request retry và xác minh outcome sau lỗi không rõ kết quả.

## 2. Khái niệm idempotency

Một phép biến đổi trạng thái f là idempotent nếu thực hiện lặp với cùng ý định không tạo thêm thay đổi so với một lần:

~~~text
f(f(state)) = f(state)
~~~

Ví dụ gần với idempotent:
- setPaused(true): bảo đảm worker ở trạng thái paused.
- setConcurrencyLimit(8): đặt giới hạn cụ thể là 8.
- ensureMaintenanceMode(): yêu cầu chuyển đến maintenance mode, không tạo thêm một phiên maintenance mới.
- requestDrain(requestId): trả về cùng drain workflow cho một requestId đã được xử lý.

Ví dụ thường không idempotent:
- togglePaused(): mỗi lần đảo trạng thái.
- increaseConcurrency(1): mỗi lần tăng thêm một đơn vị.
- restartWorker(): mỗi lần kích hoạt một restart.
- enqueueRebuild(): có thể tạo job mới mỗi lần.
- rotateCredential(): có thể tạo phiên bản credential mới và làm mất hiệu lực phiên bản trước.

Tuy nhiên, trạng thái cuối giống nhau không tự bảo đảm side effect chỉ xảy ra một lần. Nếu setPaused(true) gửi một thông báo, tạo audit record hoặc enqueue drain mỗi lần được gọi, nó có thể không idempotent theo tác động bên ngoài. Cần xác định chính xác phạm vi guarantee.

## 3. Vì sao JMX remote không tự bảo đảm exactly-once?

Client JMX có thể gọi:

~~~java
connection.invoke(
    objectName,
    "requestPause",
    new Object[0],
    new String[0]
);
~~~

Một kết nối remote có các tình huống:
1. Request chưa tới server và operation chưa chạy.
2. Request tới server và operation đã chạy nhưng phản hồi bị mất.
3. Operation chạy thành công và client nhận response.
4. Operation chạy một phần rồi thất bại ở một dependency bên ngoài.

Khi client gặp IOException hoặc timeout, nó thường không thể xác định chắc chắn đang ở trường hợp nào. **Retry không có cơ chế bảo vệ là nguy hiểm với operation có side effect.** Đừng nhầm việc gửi một request duy nhất với việc tạo đúng một hiệu ứng nghiệp vụ.

Đối với local MBeanServer, lỗi mạng không xuất hiện nhưng retry trùng vẫn có thể đến từ scheduler, task replay, nhiều controller hoặc lỗi không rõ trạng thái trong nội bộ ứng dụng.

## 4. Phân loại thao tác quản trị trước khi tự động hóa

| Loại thao tác | Ví dụ | Chính sách retry |
| --- | --- | --- |
| Read-only | getQueueDepth(), isPaused() | Có thể thử lại có giới hạn, tránh poll quá mức |
| Set desired state | setPaused(true), setLimit(8) | Cho phép nếu implementation thật sự idempotent |
| Command có idempotency key | requestDrain(requestId) | Dùng lại cùng key, kiểm tra status |
| Toggle | togglePaused() | Không retry mù |
| Increment | increaseLimit(1) | Không retry mù |
| Command bất đồng bộ | restartWorker(), rebuildIndex() | Cần workflow ID và trạng thái |
| Command không thể hoàn tác | purgeData(), revokeAll() | Cần approval, xác minh, audit |

Một operation có tên tương tự các ví dụ không tự có guarantee. Phải đọc contract implementation, side effects và thiết kế failure handling.

## 5. Ưu tiên trạng thái mong muốn thay vì toggle

Interface chưa phù hợp cho automation:

~~~java
public interface WorkerAdminMBean {
    void togglePaused();
    void increaseConcurrency();
}
~~~

Interface dễ tự động hóa hơn:

~~~java
public interface WorkerAdminMBean {
    boolean isPaused();
    void setPaused(boolean paused);

    int getConcurrencyLimit();
    void setConcurrencyLimit(int desired);
}
~~~

Khi request đặt Paused=true bị lặp, trạng thái mong muốn vẫn là true. Ngược lại, gọi togglePaused hai lần tạo kết quả ngược lại ý định ban đầu.

Các setter cần validate giới hạn, bảo đảm tính nhất quán và mô tả rõ side effects. Với lệnh dài hoặc bất đồng bộ, thiết kế request operation và status riêng thường rõ ràng hơn một setter đồng bộ.

## 6. Ví dụ Spring JMX adapter hạn chế duplicate transition

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.worker:type=Manager,name=Primary",
    description = "Idempotent worker controls"
)
public final class WorkerManagementJmx {
    private final AtomicBoolean paused = new AtomicBoolean(false);

    @ManagedAttribute(description = "Current paused state")
    public boolean isPaused() {
        return paused.get();
    }

    @ManagedOperation(
        description = "Request pause; repeated requests must not restart drain"
    )
    public void requestPause() {
        if (paused.compareAndSet(false, true)) {
            onPauseTransition();
        }
    }

    @ManagedOperation(
        description = "Request resume without duplicate transitions"
    )
    public void requestResume() {
        if (paused.compareAndSet(true, false)) {
            onResumeTransition();
        }
    }

    private void onPauseTransition() {
        // Chỉ được kích hoạt khi trạng thái đổi từ false sang true.
    }

    private void onResumeTransition() {
        // Chỉ được kích hoạt khi trạng thái đổi từ true sang false.
    }
}
~~~

Đây là ví dụ trạng thái đơn giản. Nếu onPauseTransition() thất bại sau khi CAS đã chuyển trạng thái, boolean Paused có thể không phản ánh tình trạng worker thật. Operation production nên dùng state machine và cơ chế xử lý lỗi/reconciliation phù hợp, không xem một CAS là transaction xuyên mọi dependency.

## 7. State machine cho thao tác dài

Một workflow drain worker có thể dùng:

~~~text
RUNNING
   |
   | requestDrain
   v
DRAIN_REQUESTED
   |
   v
DRAINING
   |
   v
DRAINED
~~~

Thiết kế management contract:

~~~java
public interface WorkerDrainMBean {
    String getDrainState();
    String getActiveDrainId();

    String requestDrain(String requestId);
}
~~~

Ngữ nghĩa cần công bố:
- Request ID mới tạo một logical workflow.
- Retry cùng request ID trả lại workflow ID đã có.
- Request ID đã dùng với tham số không giống trước phải bị từ chối.
- Nếu request khác tới khi drain đang chạy, trả conflict hoặc tuân thủ chính sách điều phối rõ ràng.
- Nếu workflow đã hoàn tất, client vẫn đọc được trạng thái cho đến khi hết retention window.
- Khi JVM restart, giải thích rõ deduplication còn được giữ hay không.

Nếu operation trả workflow ID, nó có thể chỉ xác nhận yêu cầu đã được chấp nhận; trạng thái DRAINED phải được kiểm tra riêng.

## 8. Idempotency key: tạo một lần cho một logical intent

Automation nên tạo key khi bắt đầu một logical action:

~~~text
requestDrain("change-2026-11-11-worker-primary")
~~~

Nếu request timeout, **dùng lại chính key này**. Tạo UUID mới ở mỗi lần retry khiến server không thể nhận diện đó là duplicate của cùng một ý định.

Server có thể lưu dữ liệu:

~~~text
requestId
target ObjectName / logical resource
operation name
argument fingerprint
status: ACCEPTED, RUNNING, SUCCEEDED, FAILED
result or error summary
createdAt, updatedAt, expiresAt
~~~

Key phải được scope để tránh va chạm giữa operation và resource. Nếu cùng key được dùng với argument fingerprint khác, trả conflict thay vì âm thầm coi request cũ và mới là một.

Cần xác định TTL, memory budget và eviction policy. Khi key hết hạn, request rất muộn có thể không còn bị deduplicate. Với thao tác có tác động nghiêm trọng, durable store và retention phù hợp quan trọng hơn map trong heap.

## 9. Skeleton deduplication và giới hạn

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public final class DrainRequests {
    private final ConcurrentMap<String, String> ids =
        new ConcurrentHashMap<>();

    public String requestDrain(String requestId) {
        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException("requestId required");
        }

        return ids.computeIfAbsent(requestId, id -> {
            String workflowId = "drain-" + id;
            startDrainWorkflow(workflowId);
            return workflowId;
        });
    }

    private void startDrainWorkflow(String workflowId) {
        // Ví dụ minh họa; cần error handling thật.
    }
}
~~~

Ví dụ chỉ mô tả ý tưởng cho **một JVM**. computeIfAbsent bảo vệ việc tạo mapping đối với cùng key trong map nhưng không biến lời gọi queue/database bên ngoài thành transaction atomic. Nếu enqueue thành công rồi lambda ném exception, map có thể không giữ key trong khi external side effect đã xảy ra. Một retry sau đó có thể lặp tác động.

Khi cần durable guarantees, dùng state store transactional, outbox, unique constraint hoặc consumer-side deduplication; xem xét cả crash giữa các bước và xử lý recovery.

## 10. Phân biệt idempotency và concurrency safety

Hai lệnh riêng lẻ có thể idempotent nhưng vẫn xung đột:

~~~text
t0: Controller A reads ConcurrencyLimit=8
t1: Controller B sets ConcurrencyLimit=16
t2: A retries setConcurrencyLimit(8)
~~~

Kết quả A ghi đè quyết định mới hơn của B dù set(8) lặp bao nhiêu lần cũng ra 8.

Giải pháp:
- Một owner/controller duy nhất cho desired state khi có thể.
- Compare-and-set bằng expected version.
- Lease/epoch/fencing token để chặn stale controller.
- Quy tắc conflict và reconciliation rõ ràng.
- Không retry request cũ sau khi quyền điều phối đã hết hạn.

Ví dụ contract:

~~~java
public interface ConfigManagementMBean {
    long getConfigVersion();
    int getConcurrencyLimit();

    boolean setLimitIfVersion(int desired, long expectedVersion);
}
~~~

Server phải kiểm tra version và cập nhật state **trong một critical section hoặc transaction phù hợp**. Một if-check tách biệt với write không bảo đảm tính atomic trước concurrent requests.

## 11. Chiến lược retry theo loại lỗi

| Lỗi hoặc phản hồi | Hành động phù hợp |
| --- | --- |
| Validation error | Không retry; sửa input |
| Authorization failure | Không retry tự động; xử lý quyền |
| InstanceNotFoundException | Kiểm tra ObjectName, lifecycle và đúng JVM |
| Timeout/IOException | Truy vấn trạng thái hoặc request status trước khi retry |
| Conflict / stale version | Re-read, ra quyết định mới |
| Duplicate request key | Đọc trạng thái/result của request đã có |
| Transient dependency error | Retry có giới hạn nếu contract cho phép |
| Terminal failure | Dừng workflow, ghi audit và escalation |

Các retry được phép nên có exponential backoff, jitter, maximum attempts, total deadline và giới hạn concurrency. Nếu hệ thống đang bị quá tải, retry quá dày có thể làm sự cố nặng hơn.

Không gom mọi exception thành nhóm retryable. Exception runtime do validation hoặc method security không có ý nghĩa tương tự lỗi transport của remote connector.

## 12. Read–compare–act–verify

Một workflow an toàn:

~~~text
Read current state
  -> check preconditions and version
  -> derive desired state
  -> call idempotent operation / stable request ID
  -> verify postcondition or workflow status
  -> on uncertain result, read status before retry
  -> bounded retry only if contract permits
  -> audit final outcome
~~~

Ví dụ yêu cầu pause:

~~~java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class WorkerAutomation {
    public static void ensurePaused(
            MBeanServerConnection server,
            ObjectName name) throws Exception {

        boolean paused =
            (Boolean) server.getAttribute(name, "Paused");

        if (!paused) {
            server.invoke(
                name,
                "requestPause",
                new Object[0],
                new String[0]
            );
        }

        boolean after =
            (Boolean) server.getAttribute(name, "Paused");

        if (!after) {
            throw new IllegalStateException(
                "Pause was not confirmed"
            );
        }
    }
}
~~~

Ví dụ giả định trạng thái được đổi đồng bộ; với operation bất đồng bộ, cần poll DrainState hoặc request status theo deadline. Read-then-act không atomic trước actor khác; phần bảo vệ phiên bản phải nằm ở server.

## 13. At-most-once, at-least-once và effectively-once

Có thể dùng các khái niệm:
- **At-most-once:** không retry khi mất response; tránh duplicate nhưng có thể bỏ sót lệnh.
- **At-least-once:** có thể retry đến khi nhận phản hồi; giảm bỏ sót nhưng dễ duplicate.
- **Effectively-once:** nhận delivery lặp nhưng logical effect được deduplicate trong phạm vi xác định.
- **Exactly-once:** cần định nghĩa transaction boundary cụ thể và infrastructure hỗ trợ; không thể tuyên bố chỉ nhờ JMX.

Với automation quan trọng, thường kết hợp at-least-once request với idempotency key và reconciliation để đạt hiệu quả effectively-once cho một logical operation. Guarantee phải ghi rõ phạm vi node/cluster và thời gian retention.

## 14. Những thao tác khó làm idempotent

**Restart worker:** retry có thể restart lần hai. Dùng workflow ID, trạng thái RESTARTING/COMPLETED và kiểm tra một restart đang hoạt động trước khi chấp nhận request mới.

**Rotate credentials:** retry không được sinh thêm secret ngoài ý muốn; chỉ trả trạng thái rotation có sẵn và không bao giờ đưa secret vào ObjectName, logs hoặc JMX descriptions.

**Purge data:** dù delete lặp có thể cho trạng thái cuối giống nhau, operation vẫn cần scope, authorization, approval, dry-run khi phù hợp và khả năng kiểm tra hậu quả.

**Trigger batch:** nếu enqueue ở message broker, cần consumer deduplication hoặc unique logical job ID. Chỉ giữ request ID trong một JVM không giải quyết duplicate khi nhiều node cùng tiếp nhận.

**Scale resource:** phải có version check để lệnh retry cũ không đảo ngược thay đổi mong muốn mới.

## 15. Description cho người vận hành

Spring JMX hỗ trợ metadata:

~~~java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;

@ManagedOperation(
    description = "Drain current node once per requestId; "
        + "reuse requestId on retry and check DrainState"
)
@ManagedOperationParameters({
    @ManagedOperationParameter(
        index = 0,
        name = "requestId",
        description = "Stable idempotency key for this logical drain request"
    )
})
public String requestDrain(String requestId) {
    return drainService.requestDrain(requestId);
}
~~~

Description cần nói:
- Operation idempotent theo phạm vi nào.
- Key có bắt buộc không, dùng lại thế nào.
- Operation có bất đồng bộ không.
- Lấy status qua attribute/operation nào.
- Trường hợp nào không retry.
- Rủi ro và quyền yêu cầu thao tác.

Metadata chỉ hướng dẫn, không thay thế validation/deduplication. Với Spring exporter phải kiểm tra description thực sự xuất vào MBeanInfo qua metadata assembler phù hợp.

## 16. Observability và audit

Một bản ghi command nên có:

~~~text
timestamp
actor or controller ID
target ObjectName / JVM instance
operation and request ID
argument fingerprint (without secrets)
precondition state and version
accepted / duplicate / conflict / success / failure
duration
postcondition verification
~~~

Metric có thể gồm:
- jmx_admin_command_total theo operation/result.
- jmx_admin_duplicate_total.
- jmx_admin_conflict_total.
- jmx_admin_duration_seconds.
- jmx_admin_inflight.

Không đưa request ID, job ID hoặc dữ liệu tenant động vào metric labels vì có thể gây cardinality không giới hạn. Để correlation ID trong structured log với chính sách retention/access phù hợp.

Notification có thể hỗ trợ báo completion, nhưng không dùng JMX notification như durable message queue có guarantee replay mặc định.

## 17. Test tính idempotent ở tầng domain

Một test giả định:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class WorkerManagementTest {

    @Test
    void duplicatePauseDoesNotRepeatTransition() {
        CountingWorker worker = new CountingWorker();

        worker.requestPause();
        worker.requestPause();

        assertTrue(worker.isPaused());
        assertEquals(1, worker.pauseTransitions());
    }
}
~~~

CountingWorker là test double cần cài trong test suite. Unit test domain mới kiểm tra được một phần; integration test phải xác nhận JMX operation name, method signature và invocation thực qua MBeanServer.

Các case quan trọng:
1. Một request thành công.
2. Lặp lại cùng key và arguments.
3. Cùng key nhưng arguments khác.
4. Hai request đồng thời cùng key.
5. Timeout sau khi server đã commit.
6. JVM restart giữa hai lần request.
7. Hai node cùng tiếp nhận nếu dedup cluster-wide.
8. TTL key hết hạn.
9. Stale version từ controller cũ.
10. External dependency lỗi giữa commit và side effect.

## 18. Integration test bằng MBeanServer

~~~java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

MBeanServer server =
    MBeanServerFactory.createMBeanServer("automation-test");

ObjectName name = new ObjectName(
    "com.example.jobs:type=Worker,name=Test"
);

try {
    // Đăng ký test MBean qua exporter hoặc registerMBean.
    // Sau khi xác nhận server.isRegistered(name), gọi:
    server.invoke(name, "requestPause",
        new Object[0], new String[0]);

    server.invoke(name, "requestPause",
        new Object[0], new String[0]);

    boolean paused = (Boolean)
        server.getAttribute(name, "Paused");

    if (!paused) {
        throw new AssertionError("Pause not applied");
    }
} finally {
    if (server.isRegistered(name)) {
        server.unregisterMBean(name);
    }
    MBeanServerFactory.releaseMBeanServer(server);
}
~~~

Mẫu trên cần test fixture đăng ký MBean trước khi chạy; không thể chạy nguyên đoạn nếu chưa đăng ký. Với Spring context, phải cleanup exporter và server do test sở hữu để không để lại ObjectName trùng sang test sau.

Test remote còn cần mô phỏng mất response và reconnect trong mô hình auth/TLS tương ứng, không tắt bảo mật chỉ để làm benchmark.

## 19. Runbook đề xuất cho requestDrain

~~~text
Purpose:
    Drain jobs on exactly one node.

Preconditions:
    Confirm cluster capacity.
    Confirm target ObjectName and current state.
    Confirm automation lease/version.

Request:
    Generate requestId once per logical action.
    Call requestDrain(requestId).

On success:
    Record workflow ID.
    Poll DrainState until terminal outcome.

On timeout:
    Do not create a fresh requestId.
    Query active request/workflow state.
    Retry with same key only when contract permits.

On conflict:
    Re-read version and owner.
    Do not override a newer controller automatically.

Rollback:
    Follow explicitly documented cancel/resume flow.
    Do not assume all drain stages are reversible.

Audit:
    Record actor, requestId, target, state, result and duration.
~~~

Các lệnh quản trị có side effect phải được bảo vệ bằng authentication, authorization, TLS và network isolation khi dùng remote JMX. Runbook không thể thay cơ chế enforcement.

## 20. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Retry mọi timeout | Duplicate side effect | Query state trước |
| Sinh UUID mới mỗi retry | Mất deduplication | Reuse stable key |
| Dùng toggle trong automation | Đảo ngược ý định | Set desired state |
| In-memory dedup nhưng tuyên bố durable | Duplicate sau restart | Persistent state |
| Cùng key với argument khác | Mapping sai logical request | Check fingerprint |
| Không kiểm tra version | Retry cũ ghi đè yêu cầu mới | CAS/fencing |
| Thấy invoke trả về rồi coi hoàn tất | Bỏ qua workflow bất đồng bộ | Poll terminal state |
| Retry không giới hạn | Request storm | Backoff/jitter/deadline |
| Không audit | Khó điều tra tác động trùng | Correlation ID, result |
| Không giới hạn quyền JMX | Operation bị lạm dụng | Authn/authz và network policy |

## 21. Checklist trước khi đưa operation vào automation

- Xác định idempotency guarantee và external side effects.
- Chọn ObjectName đúng JVM/node.
- Có cách đọc trạng thái trước và sau khi thực hiện.
- Thiết kế request ID ổn định khi command cần deduplication.
- Xác định retention và phạm vi dedup qua restart/cluster.
- Bảo vệ concurrent controllers bằng version/epoch/owner.
- Phân loại lỗi retryable và non-retryable.
- Có backoff, jitter, maximum attempts và total deadline.
- Operation nguy hiểm có phê duyệt, quyền và audit.
- Không ghi secret trong logs, metadata hoặc notifications.
- Có unit/integration tests với duplicate, race và crash.
- Có runbook về verification, rollback và escalation.

## 22. Kết luận

**Idempotency là điều kiện quan trọng khi tự động hóa Spring JMX.** Client không biết chắc command đã chạy hay chưa sau timeout; JMX invoke không bảo đảm exactly-once. Thay toggle/increment bằng desired state khi phù hợp, sử dụng key ổn định và deduplication cho thao tác có side effect, so sánh phiên bản khi nhiều controller cạnh tranh và luôn xác minh postcondition. Kết hợp state machine, audit, security và kiểm thử tình huống retry để automation giúp hệ thống ổn định thay vì khuếch đại sự cố.
