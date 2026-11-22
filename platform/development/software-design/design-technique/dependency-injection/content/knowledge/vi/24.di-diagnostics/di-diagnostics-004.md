# Scope không tồn tại hoặc đã kết thúc khi đối tượng được sử dụng

Một service có thể được **Dependency Injection (DI)** lắp ghép thành công nhưng lại thất bại khi xử lý một yêu cầu cụ thể. Ví dụ: controller dùng được dependency trong HTTP request, còn tác vụ chạy bởi `ExecutorService` lại báo không có request scope; hoặc một job giữ tham chiếu tới session, nhưng callback bất đồng bộ chỉ chạy sau khi session đã đóng. Trong cả hai trường hợp, nhìn vào constructor có thể không thấy điều gì sai.

Đây là một nhóm lỗi rất quan trọng trong **chẩn đoán DI**: **scope không tồn tại tại thời điểm lấy dependency**, hoặc **scope/tài nguyên đã kết thúc trước thời điểm sử dụng**. Chúng khác với lỗi thiếu binding, vòng phụ thuộc và lỗi nghiệp vụ bên trong service, dù thông báo lỗi đôi khi xuất hiện cùng lúc.

Bài thuộc module **DEPENDENCY_INJECTION / Inversion of Control (IoC)**. Ta tiếp cận bằng **constructor injection, composition root, scope và vòng đời trong Java thuần**, rồi liên hệ cách DI container và framework có thể dùng provider, scoped proxy, request/job context và lifecycle callback. Trọng tâm là **phát hiện đúng ranh giới thời gian, thread và quyền sở hữu**, thay vì chỉ thêm annotation hoặc thay scope cho hết exception.

Sau bài này, bạn có thể:

- Phân biệt **chưa có scope hoạt động**, **scope đã đóng**, **dependency chưa được resolve** và **resource đã bị đóng**.
- Lần theo thời điểm tạo consumer, lấy target, gọi phương thức và đóng scope để tìm nguyên nhân.
- Giải thích vì sao **scoped proxy** hoặc **provider** có thể inject thành công nhưng lỗi xuất hiện ở runtime.
- Chẩn đoán request context bị mất khi chuyển từ HTTP thread sang executor/background task.
- Phân biệt **truyền dữ liệu bất biến** với **kéo dài vòng đời của session/transaction/request context**.
- Viết Java 17 thuần tái hiện hai lỗi theo thứ tự xác định, rồi kiểm thử cách xử lý bằng snapshot và scope riêng của job.
- Đánh giá cách sửa phù hợp: truyền tham số, tạo scope hợp lệ, chuyển ownership hoặc điều phối hoàn tất tác vụ.

## 1. Scope quyết định *khi nào và ở đâu* một instance hợp lệ

**Scope** là ranh giới mà trong đó một dependency instance được tạo, tra cứu và/hoặc tái sử dụng. **Lifecycle** nói về các giai đoạn tạo, khởi tạo, sử dụng và hủy tài nguyên. Hai khái niệm liên quan nhưng không đồng nhất.

| Phạm vi | Ví dụ đối tượng | Ranh giới cần xác định |
| --- | --- | --- |
| **Application/singleton** | Cấu hình bất biến, client dùng chung đúng chuẩn | Từ lúc runtime khởi tạo đến khi ứng dụng đóng |
| **Request** | Request context, dữ liệu gắn với một HTTP request | Từ khi request được framework kích hoạt đến khi kết thúc |
| **Job/unit of work** | Context thao tác, entity đang theo dõi, session theo job | Từ lúc mở công việc đến commit/discard/close |
| **Transaction** | Đối tượng quản lý giao dịch, connection/session được enlist | Trong một transaction có điểm bắt đầu/kết thúc rõ |
| **Prototype/transient** | Một collaborator cần tạo mới khi resolve | Quy tắc tạo mới; trách nhiệm dispose có thể thuộc caller |

Tên và cách triển khai scope tùy framework. Đặc biệt, **thread**, **request**, **transaction** và **unit of work không mặc định là cùng một thứ**. Một HTTP request có thể gọi nhiều job; một job có thể chạy sau khi response đã được trả; thread pool có thể dùng một worker để xử lý nhiều công việc.

Giả sử `InvoiceService` là singleton, còn `CurrentRequest` chỉ hợp lệ trong request A. Nếu service cần đọc tenant ID, một thiết kế phù hợp có thể là truyền một **giá trị dữ liệu của A** vào phương thức, hoặc dùng scoped provider/proxy **chỉ trong thời gian request A còn hoạt động**.

Một scoped dependency không phải là tài nguyên vĩnh viễn chỉ vì container đã biết đăng ký nó.

## 2. Phân loại bốn lỗi có biểu hiện gần giống nhau

Khi gặp thông báo “scope not active”, “no context bound”, “session closed” hoặc “resource already closed”, hãy tách **lúc lấy đối tượng** khỏi **lúc sử dụng đối tượng**.

| Nhóm sự cố | Điều đã xảy ra | Thời điểm lỗi điển hình | Hướng kiểm tra |
| --- | --- | --- | --- |
| **Scope chưa tồn tại/không active** | Mã yêu cầu resolve request/job-scoped target nhưng không có scope hiện tại | Provider `get()` hoặc phương thức proxy | Scope được kích hoạt trên thread/ngữ cảnh nào? |
| **Scope đã kết thúc** | Mã vẫn giữ context hoặc target của job/request đã đóng | Method đọc context sau khi callback/job chạy | Ai đóng scope? Task đã hoàn thành chưa? |
| **Resource bên trong scope đã đóng** | Scope/owner đóng session, connection, stream trước khi người dùng cuối hoàn tất | Gọi I/O, truy vấn, lazy load | Resource thuộc owner nào? Có tác vụ còn đang dùng? |
| **Thiếu binding hoặc wiring sai** | Container hoàn toàn không biết cung cấp dependency nào | Bootstrap/resolve | Có đăng ký implementation, qualifier và scope đúng không? |

Nhóm thứ tư thường bị chẩn đoán nhầm. **Không có binding** khác với **đã có binding request-scoped nhưng request scope chưa được kích hoạt**. Với scoped proxy, constructor có thể nhận được proxy hợp lệ ngay cả khi target chưa sẵn sàng; lỗi chỉ xuất hiện khi **proxy cần tìm target thực**.

### Hai trục độc lập: khả năng tìm context và trạng thái sống

Có thể hình dung theo hai câu hỏi:

1. Mã thực thi **đang ở trong một scope hoạt động** có thể được truy cập không?
2. **Đối tượng/tài nguyên cần dùng** có còn đang sống không?

| Ngữ cảnh hiện tại | Tài nguyên còn sống | Kết quả có thể |
| --- | --- | --- |
| Có scope phù hợp | Có | Có khả năng sử dụng được, nếu hợp đồng khác cũng hợp lệ |
| Không có scope phù hợp | Có | Scoped lookup có thể thất bại: chưa có current scope |
| Có tham chiếu tới scope cũ | Không | Có thể báo closed/detached/expired dù reference chưa thành `null` |
| Không có scope | Không | Có thể gặp một trong hai lỗi tùy đường thực thi chạm tới trước |

**Một tham chiếu Java còn tồn tại trên heap không có nghĩa đối tượng vẫn thuộc một scope hợp lệ.** Tránh dùng `!= null` như bằng chứng rằng request/session còn được phép sử dụng.

## 3. Vì sao constructor injection thành công mà runtime vẫn lỗi?

Với DI thủ công:

~~~java
ReportService report = new ReportService(repository, requestContext);
~~~

Nếu constructor nhận một **target request-scoped thực**, ta cần xác định `requestContext` có hợp lệ trong toàn bộ vòng đời của `report` hay không. Nhưng một framework có thể inject **proxy** thay cho target.

~~~mermaid
flowchart LR
    Root["Container bootstrap"] --> Service["Singleton ReportService"]
    Service --> Proxy["RequestContext proxy"]
    Proxy -->|"mỗi lần được gọi"| Resolver["Scope resolver"]
    Resolver -->|"request A active"| TargetA["Target A"]
    Resolver -->|"không có active scope"| Error["Lỗi scope"]
~~~

**Proxy** là một đối tượng trung gian có thể giữ tham chiếu ổn định; **target** phía sau được lấy theo scope tại thời điểm gọi. Vì vậy:

- Bootstrap có thể tạo service và proxy mà chưa cần có HTTP request.
- Service gọi proxy trong request hợp lệ thì target được resolve.
- Service gọi proxy trong background thread không có request scope thì lookup có thể lỗi.
- So sánh hai proxy bằng `==` không chứng minh rằng target phía sau là cùng một instance.
- Nếu code lấy **target thật** từ request A rồi giữ trong singleton, request B có thể dùng nhầm state cũ ngay cả khi request B đang active.

Tương tự, `Provider<RequestContext>` hoặc `Supplier<RequestContext>` có thể được inject thành công nhưng `get()` chưa được gọi. Khi `get()` chạy ngoài scope, lỗi xuất hiện lúc đó. **Provider không tự tạo scope** và cũng không tự bảo đảm mỗi `get()` tạo một object mới.

### Khi nào container phát hiện lỗi?

Điều này phụ thuộc container, scope và cách inject. Inject trực tiếp dependency ngắn hạn vào singleton có thể bị từ chối lúc khởi động, hoặc bị resolve một lần rồi giữ lại. Inject scoped proxy/provider có thể trì hoãn lookup cho đến lời gọi đầu tiên. Vì vậy câu “ứng dụng đã khởi động thành công” **không đủ** để kết luận mọi scoped dependency đều có thể dùng ở mọi đường xử lý.

## 4. Tình huống A: không có request scope trong background task

Giả sử controller xử lý request A rồi đẩy tác vụ tạo báo cáo lên executor:

~~~java
// Mã khái niệm, không phải chương trình độc lập.
final class ReportController {
    private final ReportService reports;
    private final Executor executor;

    ReportController(ReportService reports, Executor executor) {
        this.reports = reports;
        this.executor = executor;
    }

    void requestReport() {
        executor.execute(reports::generate);
    }
}
~~~

Nếu `reports.generate()` đọc `CurrentRequest` thông qua request-scoped proxy, lời gọi trên worker có thể không thấy request scope của HTTP thread.

~~~mermaid
sequenceDiagram
    participant H as HTTP thread
    participant C as Controller
    participant Q as Executor queue
    participant W as Worker thread
    participant P as Scoped proxy
    H->>C: Xử lý request A (scope active)
    C->>Q: enqueue generate()
    C-->>H: Trả response
    Note over H: Request A kết thúc
    Q->>W: Chạy generate()
    W->>P: Lấy CurrentRequest
    P-->>W: Không có request scope trong worker
~~~

**Hai nguyên nhân khác nhau có thể cùng tồn tại:**

1. **Context không được truyền:** ngay cả khi HTTP request chưa kết thúc, worker có thể không có request scope được ràng buộc với nó.
2. **Scope đã kết thúc:** khi worker bắt đầu, request có thể đã xong và tài nguyên đã bị đóng.

Chỉ đặt `ThreadLocal` trên HTTP thread không bảo đảm worker khác nhìn thấy nó. `InheritableThreadLocal` cũng không phải giải pháp chung cho thread pool: worker có thể được tạo từ trước, tái sử dụng cho nhiều request, và dễ mang dữ liệu không còn phù hợp.

### Dấu hiệu dễ nhận ra

- Gọi `reports.generate()` đồng bộ trong controller thì thành công.
- Chuyển sang `@Async`, `CompletableFuture` hoặc `ExecutorService` thì phát sinh lỗi scope.
- Lỗi chỉ xảy ra ở callback, scheduler, listener hoặc job chạy ngoài HTTP request.
- Test đơn luồng có thể pass vì vô tình gọi ngay trong scope hiện tại; test executor thật thất bại.

## 5. Tình huống B: scope đã đóng trước khi tác vụ dùng dependency

Ngay cả khi không có cơ chế scope theo thread, lỗi vẫn xảy ra nếu task giữ một context được đóng quá sớm:

~~~java
// Minh họa thứ tự lỗi; WorkUnit và process là kiểu giả định.
CompletableFuture<Void> work;
try (WorkUnit unit = openUnit()) {
    work = CompletableFuture.runAsync(
            () -> process(unit), executor);
}
// try-with-resources đã đóng unit ở đây.
work.join(); // Task có thể chưa hoàn thành lúc unit đóng.
~~~

**Lỗi nằm ở ownership và thứ tự lifecycle**. Một object `unit` vẫn được lambda capture bằng tham chiếu, nhưng `unit.close()` đã chạy. Nếu task tiếp tục sử dụng repository/session trong unit, nó có thể gặp “closed”, “detached”, “session unavailable”, hoặc lỗi nghiệp vụ khác.

~~~mermaid
flowchart TD
    Open["Tạo unit A"] --> Submit["Đẩy task dùng unit A"]
    Submit --> Close["Owner đóng unit A"]
    Close --> Run["Task chạy hoặc tiếp tục"]
    Run --> Fail["Dùng context đã đóng"]
~~~

Trường hợp này khác với scope không active: task **có tham chiếu trực tiếp tới unit** nhưng nó đã hết hạn. Việc “truyền được object sang thread khác” không bảo đảm unit có thể dùng sau `close()` hoặc an toàn đồng thời.

### Không nên “sửa” bằng cách bỏ `close()`

Bỏ `close()` có thể khiến exception biến mất trong ngắn hạn, nhưng gây rò connection, session, file descriptor, bộ nhớ hoặc dữ liệu stale. Cách đúng là **gắn vòng đời resource với vòng đời của công việc sở hữu nó** hoặc **không mang resource qua ranh giới async**.

Một lựa chọn là để worker tự tạo và đóng **unit riêng của job**:

~~~java
// Pseudocode để diễn đạt ownership, không phải Java độc lập.
CompletableFuture<Result> future = CompletableFuture.supplyAsync(
    () -> {
        try (WorkUnit unit = unitFactory.open()) {
            Result result = process(unit, command);
            unit.commit();
            return result;
        }
    },
    executor
);
~~~

Điều này chỉ phù hợp nếu mỗi job thực sự sở hữu một unit độc lập và factory được cấu hình đúng scope. **Transaction, auth context và request data không tự động được sao chép sang unit mới**. Worker phải nhận dữ liệu được phép sử dụng và thực hiện kiểm tra quyền tại ranh giới thích hợp.

## 6. Chẩn đoán bằng chuỗi thời gian thay vì chỉ nhìn stack trace

Khi gặp lỗi scope, trước tiên hãy lập timeline:

~~~text
T0  Application khởi động, container tạo singleton + scoped proxy
T1  HTTP request A bắt đầu, request scope được kích hoạt
T2  Service A gọi provider/proxy thành công trong request A
T3  Controller enqueue một tác vụ bất đồng bộ
T4  HTTP request A kết thúc, framework đóng request scope
T5  Worker thực thi tác vụ và gọi provider/proxy
T6  Scope không active, hoặc target cũ đã đóng -> exception
~~~

Cần tìm **T5** và so với T1/T4, không chỉ hỏi “bean có được inject không?”. Bốn mốc quan trọng là: **tạo**, **tra cứu target**, **sử dụng**, **đóng**.

Một checklist chẩn đoán nhanh:

1. **Dependency nào lỗi?** Tìm interface/bean, không chỉ class báo exception.
2. **Lỗi ở thời điểm nào?** Constructor, `provider.get()`, phương thức proxy, I/O hay cleanup?
3. **Scope của dependency là gì?** Singleton, request, session, transaction, job hay custom?
4. **Consumer sống bao lâu?** Singleton có giữ request target trong field không?
5. **Lời gọi chạy ở thread/ngữ cảnh nào?** HTTP thread, pool worker, scheduler, event listener, callback?
6. **Ai mở scope?** Request dispatcher, job coordinator, test fixture hoặc code thủ công?
7. **Ai đóng scope và khi nào?** HTTP response, `try-with-resources`, transaction completion, cancellation?
8. **Có async boundary không?** `CompletableFuture`, reactive callback, executor, message handler?
9. **Đối tượng đang dùng là proxy hay target?** Proxy có resolve lại target hiện tại không, hay đã capture target cũ?
10. **Có cách tái hiện với lịch chạy cố định không?** Buộc task chạy sau khi scope đóng để thấy lỗi rõ.

### Mẫu bảng sự kiện hữu ích khi điều tra

| Thời điểm | Thread/entry point | Sự kiện | Scope/target |
| --- | --- | --- | --- |
| T1 | HTTP-12 | Request A bắt đầu | A active |
| T2 | HTTP-12 | Gọi service qua proxy | Resolve target A |
| T3 | HTTP-12 | Enqueue job J | Job chưa chạy |
| T4 | HTTP-12 | Response hoàn tất | A closed |
| T5 | pool-3 | Job J gọi scoped provider | Không có A trong worker |
| T6 | pool-3 | Báo lỗi | Missing scope |

Bản ghi vận hành nên dùng correlation ID/job ID **được phép ghi log**, không log token, password hoặc dữ liệu nhạy cảm. Nếu thông báo lỗi hiển thị tên class proxy, cần truy ngược về **bean/contract cần resolve** và scope thực, tránh chỉ sửa lớp proxy.

## 7. Cách sửa đúng phụ thuộc nhu cầu nghiệp vụ

Không có một phép sửa bằng annotation duy nhất cho mọi trường hợp.

| Nhu cầu thật sự | Cách tiếp cận ưu tiên | Cảnh báo |
| --- | --- | --- |
| Worker chỉ cần tenant ID, report ID, locale | Truyền **snapshot bất biến tối thiểu** trong job command | Không mang token hoặc quyền cũ sang job ngoài chính sách bảo mật |
| Worker cần mở repository/session để lưu kết quả | Worker tạo **unit of work riêng**, có commit/close | Xác định transaction và ownership tại worker |
| Tác vụ phải chạy khi HTTP request còn sống | Điều phối completion trước khi kết thúc scope, nếu phù hợp | Blocking có thể không phù hợp với yêu cầu hiệu năng |
| Consumer singleton dùng dữ liệu request trong lời gọi đồng bộ | Truyền request data qua tham số, hoặc scoped provider/proxy đúng ranh giới | Không cache target request trong singleton |
| Framework hỗ trợ context propagation | Sử dụng wrapper/executor chính thức theo tài liệu framework | Propagation **không kéo dài** request/resource đã đóng |
| Test trực tiếp gọi một bean cần request scope | Kích hoạt scope trong fixture/harness phù hợp | Đừng chỉnh bean thành singleton chỉ để test pass |
| Resource dùng chung bị đóng khi một request kết thúc | Đưa `close()` về owner application scope | Không để consumer đóng tài nguyên không thuộc quyền sở hữu |
| Callback đang chạy ngoài transaction | Mở transaction theo boundary nghiệp vụ thực sự | Transaction không phải request scope và không sửa mọi lỗi scope |

**Hai nguyên tắc quan trọng:**

- **Truyền dữ liệu ≠ truyền scope.** Chụp một `record JobCommand(...)` bất biến có thể phù hợp để xử lý sau, nhưng không có nghĩa worker được phép dùng session/transaction/auth context cũ.
- **Truyền context ≠ kéo dài lifecycle.** Một wrapper có thể giúp task thấy context hiện hành theo cơ chế framework; nếu context đã hết hạn, wrapper không thể làm tài nguyên “sống lại”.

## 8. Thực hành Java 17: tái hiện lỗi “không có scope” và “đã đóng”

Ta sẽ viết một chương trình **Java 17 thuần**, không cần Spring/Jakarta DI, database hoặc HTTP server. Mục tiêu là nhìn thấy hai đường lỗi khác nhau:

1. **No active scope:** service nhận một `Supplier<JobData>` giống provider/scoped resolver. Tác vụ được enqueue **trong một scope** nhưng chạy **ngoài scope**, nên provider không tìm được context hiện tại.
2. **Scope closed:** một task giữ tham chiếu trực tiếp đến `JobScope`, nhưng owner đóng nó trước khi task được chạy.

Sau đó ta sửa bằng **snapshot bất biến** chỉ chứa dữ liệu cần thiết cho tác vụ. Snapshot an toàn trong ví dụ vì chỉ mang định danh thử nghiệm, không giữ session hay credential.

### Thiết kế các thành phần

~~~mermaid
flowchart TD
    Root["Composition root / Main"] --> Scope["JobScope (AutoCloseable)"]
    Root --> Queue["QueuedExecutor"]
    Root --> Resolver["ScopedReportGenerator"]
    Resolver --> Provider["Supplier<JobData>"]
    Provider --> Current["CurrentJob: lookup scope hiện tại"]
    Queue --> Unsafe["Task gọi ScopedReportGenerator muộn"]
    Queue --> Safe["Task nhận JobData snapshot"]
    Scope -.->|"close trước khi task khác chạy"| Expired["Closed scope"]
~~~

`CurrentJob` dùng `ThreadLocal` **chỉ để mô phỏng một scope context kiểu thread-bound**. Đây **không phải Service Locator được đề xuất cho mã nghiệp vụ production**: provider được inject có kiểu cụ thể, còn dữ liệu request trong ứng dụng thật nên được truyền rõ hoặc được framework quản lý đúng contract.

`QueuedExecutor` chỉ xếp task và cho chạy theo thứ tự kiểm soát. Nó **không tạo thread mới**. Vì vậy test xác định được thời điểm mất context/đóng scope mà không phụ thuộc scheduler; phần sau sẽ bổ sung thread pool thật.

Lưu đoạn dưới đây vào `Main.java`:

~~~java
import java.util.ArrayDeque;
import java.util.Objects;
import java.util.Queue;
import java.util.concurrent.Executor;
import java.util.function.Supplier;

// Snapshot chỉ chứa dữ liệu cần thiết của một job.
record JobData(String jobId, String tenantId) {
    JobData {
        if (jobId == null || jobId.isBlank()) {
            throw new IllegalArgumentException("Invalid job id");
        }
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Invalid tenant id");
        }
    }
}

// Scope có lifecycle rõ. Trong ví dụ chỉ sử dụng tuần tự.
final class JobScope implements AutoCloseable {
    private final JobData data;
    private boolean closed;

    JobScope(JobData data) {
        this.data = Objects.requireNonNull(data, "data");
    }

    JobData data() {
        if (closed) {
            throw new IllegalStateException("Job scope is closed");
        }
        return data;
    }

    @Override
    public void close() {
        closed = true;
    }
}

// Mô phỏng cơ chế ràng buộc scope vào thread hiện tại.
final class CurrentJob {
    private static final ThreadLocal<JobScope> CURRENT =
            new ThreadLocal<>();

    private CurrentJob() {}

    static JobData data() {
        JobScope scope = CURRENT.get();
        if (scope == null) {
            throw new IllegalStateException("No active job scope");
        }
        return scope.data(); // Cũng kiểm tra scope còn mở.
    }

    static <T> T within(JobScope scope, Supplier<T> action) {
        Objects.requireNonNull(scope, "scope");
        Objects.requireNonNull(action, "action");
        scope.data(); // Từ chối scope đã đóng trước khi bind.

        JobScope previous = CURRENT.get();
        CURRENT.set(scope);
        try {
            return action.get();
        } finally {
            if (previous == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(previous);
            }
        }
    }
}

// Executor thử nghiệm: cho phép task chạy sau khi scope kết thúc.
final class QueuedExecutor implements Executor {
    private final Queue<Runnable> tasks = new ArrayDeque<>();

    @Override
    public void execute(Runnable command) {
        tasks.add(Objects.requireNonNull(command, "command"));
    }

    void runAll() {
        while (!tasks.isEmpty()) {
            tasks.remove().run();
        }
    }
}

// Service giữ provider, không giữ một JobScope cụ thể.
final class ScopedReportGenerator {
    private final Supplier<JobData> currentJob;

    ScopedReportGenerator(Supplier<JobData> currentJob) {
        this.currentJob =
                Objects.requireNonNull(currentJob, "currentJob");
    }

    String generate() {
        JobData data = Objects.requireNonNull(
                currentJob.get(), "currentJob.get()");
        return "report(" + data.jobId()
                + "," + data.tenantId() + ")";
    }
}

// Service dùng giá trị request/job được truyền rõ.
final class SnapshotReportGenerator {
    String generate(JobData data) {
        Objects.requireNonNull(data, "data");
        return "report(" + data.jobId()
                + "," + data.tenantId() + ")";
    }
}

public class Main {
    public static void main(String[] args) {
        QueuedExecutor queue = new QueuedExecutor();
        ScopedReportGenerator scoped =
                new ScopedReportGenerator(CurrentJob::data);
        SnapshotReportGenerator snapshotGenerator =
                new SnapshotReportGenerator();

        try (JobScope scope = new JobScope(
                new JobData("JOB-1", "TENANT-A"))) {
            // Trong scope: provider resolve được JobData.
            String inside = CurrentJob.within(
                    scope, scoped::generate);
            System.out.println("Within: " + inside);

            // Chỉ enqueue trong scope. Task chạy sau khi
            // ThreadLocal binding đã được dọn.
            CurrentJob.within(scope, () -> {
                queue.execute(() -> {
                    try {
                        scoped.generate();
                    } catch (IllegalStateException expected) {
                        System.out.println(
                                "No scope: " + expected.getMessage());
                    }
                });
                return null;
            });
            queue.runAll();

            // Snapshot được lấy khi scope còn hợp lệ.
            JobData snapshot = CurrentJob.within(
                    scope, CurrentJob::data);
            queue.execute(() -> System.out.println(
                    "Snapshot: " + snapshotGenerator.generate(snapshot)));
            queue.runAll();
        }

        // Đường lỗi khác: có reference nhưng scope đã đóng.
        JobScope expired = new JobScope(
                new JobData("JOB-2", "TENANT-B"));
        queue.execute(() -> {
            try {
                expired.data();
            } catch (IllegalStateException expected) {
                System.out.println(
                        "Expired: " + expected.getMessage());
            }
        });
        expired.close(); // Owner đóng trước khi task được chạy.
        queue.runAll();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Main.java
java Main
~~~

Kết quả dự kiến:

~~~text
Within: report(JOB-1,TENANT-A)
No scope: No active job scope
Snapshot: report(JOB-1,TENANT-A)
Expired: Job scope is closed
~~~

### Giải thích từng dòng output

**`Within`:** code thực thi bên trong `CurrentJob.within(...)`. Provider `CurrentJob::data` tìm được `JobScope` hiện tại, nên trả `JobData`.

**`No scope`:** việc enqueue diễn ra khi scope active, nhưng `QueuedExecutor.runAll()` chỉ chạy **sau khi `within` đã khôi phục/xóa ThreadLocal binding**. Provider không biết scope nào đang active, dù object `scope` trong khối `try` chưa bị đóng ở thời điểm này.

**`Snapshot`:** ta lấy `JobData` là record bất biến trước khi gọi task. Nó không cần lookup ThreadLocal khi được dùng; trong ví dụ, job chỉ cần ID để tạo chuỗi báo cáo.

**`Expired`:** task giữ một tham chiếu trực tiếp đến `JobScope`. Owner đã gọi `close()` trước khi task đọc `data()`. Lỗi xuất hiện **vì lifecycle kết thúc**, không phải vì thiếu binding trong registry.

**Giới hạn quan trọng:** `JobScope` trong ví dụ **không được thiết kế để nhiều thread dùng đồng thời**; field `closed` không có đồng bộ. Ta chỉ dùng nó tuần tự để chứng minh ranh giới thời gian. Nếu production job context phải chia sẻ giữa các thread, cần cơ chế thread-safety, ownership và close coordination riêng. `QueuedExecutor` cũng không phải executor đa luồng thực tế.

## 9. Bài kiểm thử có kiểm soát và kiểm thử executor thật

Đặt file `ScopeDiagnosticsTest.java` cùng thư mục với `Main.java`.

Bài kiểm thử xác minh năm nhóm hành vi:

1. Provider hoạt động trong scope, từ chối lookup ngoài scope.
2. Enqueue trong scope không đồng nghĩa task có scope khi chạy muộn.
3. Scope đã đóng từ chối đọc ngay cả khi vẫn có tham chiếu.
4. Snapshot bất biến đã được tách khỏi scope có thể được dùng sau `close()` **trong hợp đồng của ví dụ**.
5. Một worker thread thực trong `ExecutorService` không tự nhận `ThreadLocal` của thread gọi, và cleanup đúng cách.

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ScopeDiagnosticsTest {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void expectNoScope(Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected missing scope");
        } catch (IllegalStateException expected) {
            check("No active job scope".equals(expected.getMessage()),
                    "Unexpected missing-scope message");
        }
    }

    private static void expectClosed(Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected closed scope");
        } catch (IllegalStateException expected) {
            check("Job scope is closed".equals(expected.getMessage()),
                    "Unexpected closed-scope message");
        }
    }

    private static void testLookupAndExpiry() {
        ScopedReportGenerator scoped =
                new ScopedReportGenerator(CurrentJob::data);

        expectNoScope(scoped::generate);

        JobData snapshot;
        QueuedExecutor queue = new QueuedExecutor();
        final String[] delayedFailure = {null};

        try (JobScope job = new JobScope(
                new JobData("TEST-A", "TENANT-A"))) {
            String inside = CurrentJob.within(job, scoped::generate);
            check("report(TEST-A,TENANT-A)".equals(inside),
                    "Provider must resolve inside active scope");

            snapshot = CurrentJob.within(job, CurrentJob::data);

            CurrentJob.within(job, () -> {
                queue.execute(() -> {
                    try {
                        scoped.generate();
                    } catch (IllegalStateException expected) {
                        delayedFailure[0] = expected.getMessage();
                    }
                });
                return null;
            });

            // Scope object vẫn mở nhưng không còn bound vào thread.
            queue.runAll();
            check("No active job scope".equals(delayedFailure[0]),
                    "Delayed task must not inherit thread binding");
        }

        // Scope đã đóng, snapshot dữ liệu vẫn có thể dùng trong ví dụ.
        String output = new SnapshotReportGenerator().generate(snapshot);
        check("report(TEST-A,TENANT-A)".equals(output),
                "Immutable job snapshot should remain usable");

        JobScope expired = new JobScope(
                new JobData("TEST-B", "TENANT-B"));
        expired.close();
        expectClosed(expired::data);
        expectClosed(() -> CurrentJob.within(
                expired, CurrentJob::data));

        expectNoScope(CurrentJob::data);
    }

    private static void testNestedScopeAndCleanup() {
        try (JobScope outer = new JobScope(
                    new JobData("OUTER", "TENANT-1"));
             JobScope inner = new JobScope(
                    new JobData("INNER", "TENANT-2"))) {
            String restored = CurrentJob.within(outer, () -> {
                check("OUTER".equals(CurrentJob.data().jobId()),
                        "Outer scope must be active");

                String innerId = CurrentJob.within(
                        inner, () -> CurrentJob.data().jobId());
                check("INNER".equals(innerId),
                        "Nested scope must see inner job");
                return CurrentJob.data().jobId();
            });

            check("OUTER".equals(restored),
                    "Nested scope must restore outer binding");
        }
        expectNoScope(CurrentJob::data);

        try (JobScope failed = new JobScope(
                new JobData("FAIL", "TENANT-3"))) {
            boolean observed = false;
            try {
                CurrentJob.within(failed, () -> {
                    throw new IllegalArgumentException("Task failed");
                });
            } catch (IllegalArgumentException expected) {
                observed = true;
            }
            check(observed, "Exception from action must propagate");
        }
        expectNoScope(CurrentJob::data);
    }

    private static void testRealExecutorDoesNotInheritScope()
            throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        ScopedReportGenerator scoped =
                new ScopedReportGenerator(CurrentJob::data);

        try {
            try (JobScope job = new JobScope(
                    new JobData("REAL", "TENANT-REAL"))) {
                Future<String> task = CurrentJob.within(job,
                        () -> pool.submit(scoped::generate));

                boolean failedWithoutScope = false;
                try {
                    task.get(5, TimeUnit.SECONDS);
                } catch (ExecutionException expected) {
                    failedWithoutScope =
                            expected.getCause()
                                    instanceof IllegalStateException;
                }
                check(failedWithoutScope,
                        "Worker must not silently inherit caller scope");
            }
        } finally {
            pool.shutdownNow();
            check(pool.awaitTermination(5, TimeUnit.SECONDS),
                    "Executor must terminate");
        }
    }

    public static void main(String[] args) throws Exception {
        testLookupAndExpiry();
        testNestedScopeAndCleanup();
        testRealExecutorDoesNotInheritScope();
        System.out.println("PASS");
    }
}
~~~

Chạy:

~~~bash
javac Main.java ScopeDiagnosticsTest.java
java ScopeDiagnosticsTest
~~~

Dòng kết quả dự kiến: `PASS`.

Bài test dùng `QueuedExecutor` để tái hiện ranh giới *thời gian* một cách xác định, và dùng `ExecutorService` thật để kiểm tra *thread context*. Nó không giả vờ rằng một test Java thuần có thể xác nhận request scope của Spring hoặc transaction/persistence context của ORM. Các hành vi đó cần **integration test trên container thật**.

### Khi test có kết quả bất thường

- **Test “No scope” không thất bại:** kiểm tra xem callback có đang thực thi ngay trong `CurrentJob.within(...)` hay không. Enqueue chưa phải chạy.
- **Task sử dụng context cũ sau request:** kiểm tra code có capture target hoặc `ThreadLocal` còn sót thay vì resolve theo request hiện tại.
- **Test dùng pool không tái hiện lỗi:** xem executor có chạy task trên thread gọi (direct executor) hay không; `newSingleThreadExecutor()` tạo worker độc lập.
- **Test treo:** dùng `Future.get(timeout, unit)`, bảo đảm shutdown pool trong `finally` và không tạo deadlock bằng cách chờ task ngay trên thread duy nhất đang chạy task đó.

## 10. Cách chuyển từ request-scoped context sang job độc lập

Một tác vụ nền thường **không còn là phần kéo dài của HTTP request**. Nó có thể cần job ID, tenant ID, input và một đơn vị công việc riêng. Thay vì đem nguyên `HttpServletRequest`, persistence session hoặc request-scoped bean sang worker, hãy chuyển thành **job command bất biến** với dữ liệu tối thiểu được phép mang qua ranh giới.

~~~java
// Minh họa thiết kế. Repository, transaction và command
// được định nghĩa bởi ứng dụng thực tế.
record ExportCommand(String jobId, String tenantId, String documentId) {}

final class ExportJobHandler {
    private final ExportRepositoryFactory repositories;

    ExportJobHandler(ExportRepositoryFactory repositories) {
        this.repositories = repositories;
    }

    void handle(ExportCommand command) {
        try (ExportRepositoryUnit unit =
                repositories.openFor(command.tenantId())) {
            unit.export(command.documentId());
            unit.commit();
        }
    }
}
~~~

Đoạn code trên là **mã thiết kế**, không biên dịch độc lập vì `ExportRepositoryFactory` và `ExportRepositoryUnit` chưa được định nghĩa. Trọng tâm:

- Factory được inject qua constructor có **hợp đồng rõ về tạo một unit cho job**.
- Worker **tự sở hữu và đóng unit** sau khi hoàn thành hoặc thất bại.
- `tenantId` trong command là dữ liệu định danh, **không thay thế xác thực/ủy quyền**. Worker phải dựa trên mô hình quyền phù hợp ở ranh giới của mình.
- Không truyền một repository/session mutable thuộc HTTP request sang job.
- Khi có retry, phải xét transaction, tính idempotent và xử lý lặp; DI không tự cung cấp các bảo đảm đó.

### Đừng chỉ đổi scope sang singleton

Nếu một lỗi request scope xuất hiện vì code chạy trong job, đổi `RequestContext` thành singleton có thể khiến lỗi lookup biến mất nhưng **gây rò dữ liệu giữa những job**. Đây là một cách chữa triệu chứng rất nguy hiểm: lúc này nhiều người dùng có thể chia sẻ một object mutable vốn chỉ nên thuộc từng request.

Cũng không nên tạo **request giả toàn cục** hoặc bật context bằng một `ThreadLocal` rồi quên `remove()`. Thread pool tái sử dụng worker; task tiếp theo có thể đọc tenant hoặc user của task trước.

## 11. Khi bắt buộc truyền context qua async boundary

Một số framework cung cấp cơ chế **context propagation**: wrapper executor, managed task, context snapshot, request/security context strategy hoặc scope activation theo job. Chúng có ích khi code cần chính sách framework cụ thể, nhưng phải phân biệt:

- **Propagation:** chuyển một giá trị hoặc liên kết ngữ cảnh đến chỗ thực thi khác.
- **Activation:** tạo/đánh dấu một scope hợp lệ trên thread/ngữ cảnh hiện hành.
- **Lifetime extension:** giữ tài nguyên còn sống đủ lâu để tác vụ dùng nó.
- **Ownership/cleanup:** ai đóng, rollback hoặc hủy tài nguyên sau khi không còn sử dụng.

Bốn việc này **không mặc định diễn ra cùng nhau**. Một wrapper chỉ copy correlation ID không thể mở lại transaction đã commit. Một wrapper truyền security context không có nghĩa worker được tiếp tục dùng database connection thuộc request đã kết thúc.

Nếu sử dụng `ThreadLocal` thủ công, mọi binding phải được **dọn/khôi phục bằng `try/finally`**, kể cả khi callback ném exception. Với scope lồng nhau, cần khôi phục giá trị scope bên ngoài thay vì xóa bừa. Trong ví dụ `CurrentJob.within`, ta làm điều đó rõ ràng.

**Tránh truyền thông tin nhạy cảm không cần thiết:** token, session hoặc principal cũ có thể hết hạn hoặc thay đổi quyền trước khi job chạy. Mô hình authorization cho background job phải được thiết kế riêng, không mặc định kế thừa quyền của request đã kết thúc.

## 12. Khi DI framework báo lỗi: đọc đúng tầng nguyên nhân

Những thông báo cụ thể khác nhau theo framework và phiên bản. Ví dụ:

| Mẫu triệu chứng | Diễn giải cần kiểm tra | Không nên vội kết luận |
| --- | --- | --- |
| “Scope … is not active for the current thread” | Có binding/scoped target nhưng scope hiện tại chưa được kích hoạt | Bean chưa đăng ký hoặc DI hoàn toàn hỏng |
| “No thread-bound request” hoặc thông báo tương tự | Code cố dùng ngữ cảnh request ở thread không được ràng buộc | Chỉ cần thêm `@Async`/proxy là tự có request |
| “Session is closed” / “EntityManager is closed” | Tài nguyên persistence có thể đã bị đóng trước khi dùng | Chắc chắn đang thiếu request scope |
| “Could not initialize proxy — no Session” hoặc lỗi lazy load | Entity/proxy cần session không còn hợp lệ | Chỉ cần chuyển mọi entity sang singleton |
| “Bean not found” / “No qualifying bean” | Có thể là thiếu binding/qualifier | Giống lỗi scope active nhưng chưa kiểm tra |
| “Cannot obtain target object” | Proxy/provider không lấy được target trong ngữ cảnh | Mỗi proxy đều bị lỗi hoặc target đã bị hủy |

Với Spring, request scope có thể được khai báo bằng `@RequestScope` hoặc cấu hình tương đương, còn `ObjectProvider<T>` có thể trì hoãn việc resolve; với CDI có khái niệm contextual instance và active context. **Tên exception, thông điệp và thời điểm lỗi có thể khác nhau** theo container, chế độ proxy và cấu hình, nên phải xem *root cause* cùng timeline thật.

### Phân biệt scope của framework với resource ORM

Một HTTP request scope đang active **không chứng minh** database transaction còn active. Ngược lại, một transaction hoặc session có thể được quản lý trong một job không có HTTP request. **Open Session in View** và các cơ chế giữ session mở dài hơn có đánh đổi riêng; đừng bật chúng chỉ để che một service đang sử dụng entity ngoài ranh giới hợp lệ.

## 13. Kiểm thử tích hợp đúng đường đi

Khi dùng framework thật, ngoài unit test Java thuần, nên có test thực hiện **đúng entry point và đúng ranh giới scope**:

| Tình huống cần kiểm tra | Thiết lập test | Kỳ vọng |
| --- | --- | --- |
| Gọi scoped service trong HTTP request | Request test harness/container hợp lệ | Resolve đúng target của request |
| Gọi từ scheduler không có request | Background worker không giả tạo HTTP scope | Phát hiện thiếu scope hoặc thiết kế job-specific context |
| Hai request độc lập | Hai request scope riêng | Không trộn instance/state của A và B |
| Task chạy sau response | Executor cho phép cố ý chạy chậm | Không dùng resource của request đã kết thúc |
| Một job có hai bước | Một work scope chung được tạo tại job boundary | Cùng context trong job nếu contract yêu cầu |
| Hai job tách biệt | Hai work scope độc lập | Không chia sẻ mutable state ngoài ý muốn |
| Hủy/timeout giữa chừng | Điều phối cancellation và cleanup | Không tiếp tục dùng resource đã đóng |
| Shutdown ứng dụng khi còn task | Stop intake, quiesce/await, close theo thứ tự | Không đóng datasource/executor trước khi tác vụ còn cần |

Để tái hiện lỗi lịch chạy, ưu tiên **controlled executor, latch hoặc barrier có timeout** hơn `Thread.sleep(...)`. Stress test có thể bổ sung nhưng không thay thế một phản ví dụ được lên lịch rõ ràng.

Đặc biệt, **test controller đồng bộ pass không phải bằng chứng job bất đồng bộ sẽ pass**. Cần test cả con đường gọi qua scoped proxy/provider và cả con đường worker nhận command riêng.

## 14. Những cách sửa làm lỗi khó phát hiện hơn

| “Cách chữa nhanh” | Vì sao nguy hiểm? | Thay bằng |
| --- | --- | --- |
| Đổi request-scoped bean thành singleton | Dữ liệu request có thể bị giữ và chia sẻ xuyên người dùng | Tách snapshot/parameter khỏi singleton; giữ scope đúng |
| Đặt context vào biến static | Che dependency, rò dữ liệu giữa job/test | Constructor DI, tham số tường minh và composition root |
| Dùng `ThreadLocal` nhưng không cleanup | Worker tái sử dụng context cũ | `try/finally`, khôi phục scope ngoài, hoặc truyền dữ liệu |
| Capture `EntityManager`/session vào future | Session có thể đóng trước khi future chạy | Mỗi job tự mở unit/session hoặc phối hợp lifetime đúng |
| Bỏ `close()` hoặc giữ request mãi | Rò tài nguyên, dữ liệu stale, khó shutdown | Thiết kế owner và thời điểm đóng chính xác |
| Catch và bỏ qua scope exception | Mất chức năng, có thể che lỗi tenant/security | Fail rõ ràng, sửa boundary và bổ sung test |
| Gọi `provider.get()` trong constructor để “kiểm tra sớm” | Scoped dependency có thể không có scope khi bootstrap | Resolve tại ranh giới hợp lệ; dùng cấu hình validation riêng |
| Cho worker chạy bằng HTTP request giả | Gắn job vào lifecycle không thuộc về nó | Job command + job-owned scope/resources |
| Chỉ kiểm tra `!= null` trước khi gọi object | Object có thể đã hết hạn dù còn reference | Kiểm tra lifecycle/ownership, không dùng lại sau close |
| Dùng proxy để “kéo dài” target | Proxy chỉ chọn/ủy quyền target; không hồi sinh scope cũ | Tạo target mới trong scope hợp lệ hoặc dùng snapshot |

Một dấu hiệu đáng cảnh giác là **sửa lỗi bằng cách kéo dài thời gian sống của mọi thứ**. Việc giữ connection, transaction, request object và dữ liệu người dùng lâu hơn cần thiết có thể làm tăng rò rỉ bộ nhớ, khóa dữ liệu và rủi ro bảo mật.

## 15. Quy trình chẩn đoán thực tế theo thứ tự

Khi nhận một báo cáo lỗi scope, có thể xử lý theo thứ tự sau:

1. **Ghi lại exception và root cause.** Xác định thao tác lỗi là resolve, lời gọi proxy, truy vấn session hay close.
2. **Xác định entry point.** HTTP handler, scheduler, message listener, CLI command, test hoặc callback bất đồng bộ?
3. **Dựng timeline.** Đánh dấu bắt đầu scope, lấy/capture dependency, enqueue, response/commit, task chạy và close.
4. **Vẽ đồ thị dependency.** Phân biệt consumer, proxy, provider và target; xác định nơi có direct reference được giữ.
5. **Đánh dấu lifetime trên mỗi cạnh.** Singleton có giữ request target? Job có dùng session của request khác không?
6. **Đối chiếu thread/context.** Scope được active trên thread nào; task chạy ở đâu; ai propagation?
7. **Xác minh ownership.** Ai có quyền đóng resource; tác vụ còn đang dùng khi close không?
8. **Chọn một sửa đổi có ý nghĩa nghiệp vụ.** Truyền immutable command, mở job-owned unit, điều phối completion hoặc dùng scope activation chính thức.
9. **Tái hiện bằng test xác định.** Ép task chạy **ngoài scope** hoặc **sau close**; kiểm tra đúng failure và hành vi sau sửa.
10. **Kiểm thử trên DI container thật.** Xác minh cấu hình scope/proxy/lifecycle, transaction và thread propagation với entry point thực.
11. **Kiểm thử đường lỗi.** Timeout, cancellation, exception trong callback, retry và shutdown.
12. **Theo dõi bằng metadata an toàn.** Job ID/request ID và lifecycle event; tránh log credential, token hoặc dữ liệu nhạy cảm.

### Các câu hỏi tự kiểm tra

**Tình huống A:** Singleton đã inject `RequestContext` thông qua scoped proxy thành công lúc startup. Khi job nền gọi proxy, framework báo request scope không active. Có mâu thuẫn không?

**Không.** Việc tạo proxy và việc tìm target là hai thời điểm khác nhau. Job nền không tự có request scope để proxy resolve target.

**Tình huống B:** Một `CompletableFuture` capture `WorkUnit` trong request, rồi chạy sau khi `try-with-resources` đóng unit. Thêm `volatile` vào field `closed` có làm unit hợp lệ trở lại không?

**Không.** `volatile` liên quan visibility của trạng thái, không kéo dài lifecycle. Phải đổi ownership/timeline hoặc không đưa unit qua async boundary.

**Tình huống C:** Task chỉ cần `reportId` và `tenantId` để xếp một job. Có nên đưa nguyên `HttpServletRequest` hoặc session database sang executor không?

**Thông thường không.** Chụp command bất biến tối thiểu, áp dụng chính sách xác thực/ủy quyền riêng tại worker và mở tài nguyên job-owned khi cần.

**Tình huống D:** Một wrapper tự động truyền MDC/correlation ID sang worker. Điều đó có bảo đảm database transaction của HTTP request cũng được truyền và chưa kết thúc không?

**Không.** Context propagation, scope activation và transaction lifetime là các cơ chế riêng, không được suy ra từ việc truyền ID.

**Tình huống E:** Test gọi service trong request pass, nhưng gọi từ scheduler fail. Có nên vô hiệu hóa test scheduler?

**Không.** Scheduler là entry point khác và có lifecycle khác. Test đang chỉ ra một đường gọi cần job-specific design hoặc scope hợp lệ.

**Tình huống F:** `JobScope` đã close nhưng biến Java vẫn trỏ tới nó. Nếu gọi một method đọc dữ liệu không lỗi, có thể kết luận dùng nó được không?

**Không.** Một vài phương thức không kiểm tra trạng thái không có nghĩa mọi hành vi được phép sau close. Hợp đồng lifecycle phải xác định rõ; tốt nhất tránh đưa managed object ra ngoài scope sở hữu.

**Tình huống G:** Có nên “giải quyết” thiếu request scope bằng cách bật một scope giả trên mọi thread pool worker?

**Không như một giải pháp mặc định.** Worker cần ranh giới công việc và quyền sở hữu riêng, không phải HTTP request giả toàn cục. Việc gắn context sai dễ làm trộn dữ liệu và khiến cleanup khó kiểm soát.

## Ghi nhớ

**Scope không tồn tại** nghĩa là tại thời điểm resolve không có ngữ cảnh hợp lệ; **scope đã kết thúc** nghĩa là một tham chiếu hoặc tài nguyên đang được dùng sau lifecycle của nó. Cả hai có thể xuất hiện dù constructor injection và bootstrap thành công, nhất là khi dùng scoped proxy, provider và tác vụ bất đồng bộ. Hãy chẩn đoán bằng **timeline tạo–resolve–sử dụng–đóng**, phân biệt proxy với target, và đặt scope theo đúng **request/job/unit of work**. Trong Java thuần, cách sửa dễ kiểm chứng thường là **truyền dữ liệu bất biến qua tham số** hoặc **cho job tự tạo và đóng unit của mình**; DI container chỉ tự động hóa một phần việc cấp và quản lý dependency, không thể sửa ownership hay ranh giới bất đồng bộ bị thiết kế sai.
