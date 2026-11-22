# Đồ thị theo ứng dụng, yêu cầu, tác vụ và phiên làm việc

## 1. Đồ thị đối tượng trong Dependency Injection là gì?

Trong **Dependency Injection (DI)**, một đối tượng nhận các cộng tác viên (dependency) từ bên ngoài, thường qua constructor. Khi nhiều đối tượng được tạo và nối với nhau, các quan hệ tham chiếu đó tạo thành một **đồ thị đối tượng** (*object graph*).

Một đồ thị đối tượng có:

- **Nút (node):** instance của service, adapter, repository, context, factory hoặc thành phần khác.
- **Cạnh (edge):** quan hệ một đối tượng đang giữ hoặc sử dụng một đối tượng khác.
- **Điểm lắp ghép (composition root):** nơi chọn implementation, tạo instance và nối dependency để tạo đồ thị phù hợp.

Ví dụ, `OrderHandler` giữ `OrderService`; `OrderService` giữ `OrderRepository` và `NotificationSender`. Đồ thị mô tả **đối tượng thực sự được nối**, không chỉ sơ đồ kế thừa hay quan hệ import giữa các class. Nó có thể chứa một node được nhiều node khác cùng tham chiếu.

Một ứng dụng thực tế ít khi tạo **toàn bộ** đồ thị một lần rồi giữ nguyên mãi. Có các đối tượng sống suốt tiến trình, đối tượng được tạo cho từng HTTP request, đối tượng sống qua nhiều request trong cùng một phiên và đối tượng chỉ thuộc về một job. Bài này tập trung vào **ranh giới lắp ghép và vòng đời của những đồ thị đó**.

Trong cách học bằng Java thuần, ta sẽ sử dụng **constructor injection** để thấy rõ nơi tạo và nơi sử dụng dependency, sau đó mới cân nhắc DI container để quản lý những scope phức tạp.

Sau bài này, bạn có thể:

1. Phân biệt application graph, request graph, task graph và session graph.
2. Giải thích vì sao đối tượng sống lâu không nên giữ trực tiếp dependency sống ngắn hơn.
3. Lắp ghép các graph thủ công bằng Java thuần và kiểm thử sự tách biệt giữa các scope.
4. Xác định ai quản lý khởi tạo, thời điểm hết hạn và giải phóng tài nguyên.
5. Nhận ra các lỗi như rò rỉ trạng thái request, giữ session vô hạn hoặc mang request context vào background job.

## 2. Bốn phạm vi đồ thị phổ biến

Một **scope** là quy tắc xác định instance nào được chia sẻ, trong ranh giới nào, và kết thúc khi nào. Những tên scope sau biểu diễn **ý định kiến trúc**; Java thuần không tự tạo các scope này, và DI container cũng có thể đặt tên hay hỗ trợ chúng khác nhau.

| Loại đồ thị | Khi nào bắt đầu? | Ví dụ đối tượng | Khi nào kết thúc? |
| --- | --- | --- | --- |
| **Application graph** | Khi một tiến trình hoặc application instance khởi động. | Cấu hình, client dùng chung, connection pool, service không giữ trạng thái theo người dùng. | Khi application instance dừng và tài nguyên được đóng. |
| **Request graph** | Khi bắt đầu xử lý một yêu cầu, thường là HTTP request. | Request context, request handler, transaction/unit-of-work theo request. | Khi xử lý request hoàn tất, kể cả khi kết thúc bằng lỗi. |
| **Task graph** | Khi một job/tác vụ bắt đầu, ví dụ xử lý message hoặc xuất báo cáo. | Job context, task handler, đơn vị công việc hoặc transaction của job. | Khi task thành công, thất bại hoặc bị hủy và cleanup đã chạy. |
| **Session graph** | Khi một phiên hợp lệ được thiết lập. | Session state, giỏ hàng theo phiên, dữ liệu phiên cần dùng qua nhiều request. | Khi logout, timeout hoặc phiên bị vô hiệu hóa. |

**Những giới hạn cần nhớ:**

- *Application scope* không đồng nghĩa với một singleton duy nhất cho toàn hệ thống phân tán. Mỗi JVM hoặc mỗi instance của ứng dụng có thể có application graph riêng.
- *Request scope* không đồng nghĩa với *thread scope*. Một request có thể đổi thread trong xử lý bất đồng bộ; một thread có thể phục vụ nhiều request liên tiếp.
- *Session scope* không phải request scope kéo dài: một session thường phục vụ **nhiều request**. Hai request trong cùng session vẫn phải có request context riêng.
- *Task scope* không nhất thiết nằm trong request. Một job có thể chạy sau khi request trả về, hoặc được kích hoạt độc lập bởi scheduler/message queue.

### 2.1. Đồ thị theo ứng dụng

Application graph thường gồm những thành phần được lắp ghép ở **composition root của tiến trình**. Ví dụ, một HTTP client được cấu hình dùng chung và một `OrderRepository` không giữ trạng thái request có thể được đưa vào nhiều service.

Điều kiện là implementation phải phù hợp với việc chia sẻ: nếu nó chứa trạng thái thay đổi hoặc dùng tài nguyên không thread-safe, cần quản lý đồng thời hoặc không chia sẻ như vậy.

### 2.2. Đồ thị theo yêu cầu

Mỗi HTTP request có thể cần `RequestContext` riêng (request ID, thông tin identity đã xác thực, correlation ID), một handler hoặc transaction riêng. Đồ thị này có thể **tham chiếu tới các dependency sống lâu hơn** ở application graph.

Khi request kết thúc, không nên có một application singleton tiếp tục giữ `RequestContext` vừa dùng, vì điều đó kéo dài vòng đời của dữ liệu request và có nguy cơ trộn thông tin giữa người dùng.

### 2.3. Đồ thị theo tác vụ

Một tác vụ nền có thể có `TaskContext` gồm job ID, chính sách retry, deadline và tài nguyên riêng. Nó thường nhận những service dùng chung từ application graph, nhưng **không nên dựa vào HTTP request hiện tại** để tồn tại.

Ví dụ, request “xuất báo cáo” tạo thông điệp job và trả kết quả sớm. Worker xử lý job vài phút sau phải tạo **task graph** riêng từ dữ liệu đã được truyền và xác thực cần thiết. Nó không thể giả định request context hoặc transaction của HTTP request vẫn sống.

### 2.4. Đồ thị theo phiên làm việc

Một phiên đăng nhập có thể liên quan đến nhiều request nên một `SessionState` có thể được dùng lại xuyên các request trong session đó. Tuy nhiên, **session state cần được ràng buộc với đúng phiên**, hết hạn đúng lúc và truy cập an toàn nếu có nhiều request đồng thời.

Nếu ứng dụng scale ngang qua nhiều JVM, map giữ session trong bộ nhớ mỗi instance không tự đồng bộ sang instance khác. Khi cần session dùng chung giữa các node, phải cân nhắc lưu trữ phân tán, routing, serialization và cơ chế nhất quán theo yêu cầu.

## 3. Quan hệ giữa các đồ thị: có chia sẻ, có cô lập

Về mặt kiến trúc, có thể hình dung một application graph cung cấp nền tảng chung. Mỗi lần có request hoặc job, hệ thống tạo graph ngắn hạn mới. Các request cùng phiên có thể cùng tham chiếu tới một session state.

```text
Application graph (tồn tại theo tiến trình)
  +-- EventSink dùng chung
  +-- SessionRegistry
  |      +-- Session S1 (user A) ----+
  |      |                          |
  |      +-- Session S2 (user B) --+ |
  |                                 | |
  +-- Request graph R1 --------------+ |  (tham chiếu S1)
  +-- Request graph R2 ----------------+  (tham chiếu S1)
  +-- Request graph R3 ---------- S2      (tham chiếu S2)
  |
  +-- Task graph T1
  +-- Task graph T2
```

Đây là **sơ đồ các quan hệ sở hữu và tham chiếu**, không phải yêu cầu mọi implementation phải có một cây đối tượng y hệt. Một phần graph có thể được tạo qua factory; một dependency dùng chung có thể xuất hiện ở nhiều nhánh.

### 3.1. Quy tắc về thời gian sống của tham chiếu

Nếu một đối tượng **giữ trực tiếp** một dependency suốt vòng đời của chính nó, dependency đó cần còn hợp lệ trong khoảng thời gian đối tượng chủ có thể dùng nó.

Các quan hệ thường an toàn nếu tuân thủ contract:

- Request handler giữ service dùng chung ở application scope.
- Request handler giữ context riêng của request hiện tại.
- Request handler tham chiếu session state đúng phiên.
- Session state giữ dữ liệu phiên và có thể tham chiếu tới service dùng chung phù hợp.
- Task handler giữ task context riêng và tham chiếu service dùng chung.

Các quan hệ dễ sai:

- Application singleton giữ **một `RequestContext` cụ thể** lấy từ request đầu tiên.
- Session-scoped component giữ một dependency chỉ hợp lệ trong một request.
- Background job giữ trực tiếp request object, transaction hoặc security context vốn sẽ hết hạn khi HTTP response kết thúc.

**Quy tắc thực dụng:** đối tượng sống lâu không nên *capture* trực tiếp một instance có scope sống ngắn hơn. Nếu nó cần thao tác trong scope ngắn hạn, hãy truyền **dữ liệu yêu cầu dưới dạng tham số**, dùng factory tạo đối tượng trong scope mới hoặc một provider biết đúng scope đang hoạt động; không lưu cố định instance ngắn hạn.

Quy tắc này liên quan đến **vòng đời tham chiếu**, không phải cấm mọi lời gọi từ service dùng chung tới logic theo request. Một service dùng chung vẫn có thể xử lý dữ liệu từ request khi dữ liệu đó được đưa vào **tham số của lời gọi**, và service không giữ lại dữ liệu sau khi xử lý.

### 3.2. Scope không thay thế tính an toàn đồng thời

Một object application-scoped có thể được nhiều thread gọi cùng lúc. Một session có thể có hai request đồng thời. Ngay cả khi scope được đặt đúng, implementation có trạng thái mutable vẫn phải dùng đồng bộ hóa, dữ liệu bất biến hoặc cơ chế concurrency thích hợp.

Ví dụ, tăng bộ đếm số lượt trong session nên dùng phép tăng atomic nếu nhiều request có thể thao tác đồng thời. Dùng `int visits++` không tự an toàn chỉ vì đối tượng nằm trong session scope.

## 4. Java thuần: lắp graph ứng dụng, phiên, yêu cầu và tác vụ

Ví dụ sau **tự lắp ghép đối tượng bằng Java** để làm rõ ranh giới. Nó có một event sink chung, registry quản lý những phiên đang hoạt động, mỗi request có handler/context riêng và mỗi task có worker/context riêng.

Lưu toàn bộ mã vào file `ObjectGraphScopesDemo.java`:

```java
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

// Hợp đồng dùng chung cho việc ghi sự kiện minh họa.
interface EventSink {
    void write(String event);
}

// Adapter chung ở application graph: chỉ in ra console.
final class ConsoleEventSink implements EventSink {
    @Override
    public void write(String event) {
        System.out.println(event);
    }
}

// Session graph: sống qua nhiều request trong cùng phiên.
final class SessionState {
    final String sessionId;
    final String userId;
    private final AtomicInteger visits = new AtomicInteger();

    SessionState(String sessionId, String userId) {
        this.sessionId = Objects.requireNonNull(sessionId, "sessionId");
        this.userId = Objects.requireNonNull(userId, "userId");
    }

    int registerVisit() {
        return visits.incrementAndGet();
    }
}

// Request graph: mỗi request tạo context riêng.
final class RequestContext {
    final String requestId;
    final SessionState session;

    RequestContext(String requestId, SessionState session) {
        this.requestId = Objects.requireNonNull(requestId, "requestId");
        this.session = Objects.requireNonNull(session, "session");
    }
}

final class RequestHandler {
    private final RequestContext context;
    private final EventSink sink;

    RequestHandler(RequestContext context, EventSink sink) {
        this.context = Objects.requireNonNull(context, "context");
        this.sink = Objects.requireNonNull(sink, "sink");
    }

    void handle() {
        int visit = context.session.registerVisit();
        sink.write("request=" + context.requestId
                + ",session=" + context.session.sessionId
                + ",user=" + context.session.userId
                + ",visit=" + visit);
    }
}

// Task graph: được tạo độc lập với request và session.
final class TaskContext {
    final String taskId;

    TaskContext(String taskId) {
        this.taskId = Objects.requireNonNull(taskId, "taskId");
    }
}

final class ExportTask {
    private final TaskContext context;
    private final EventSink sink;

    ExportTask(TaskContext context, EventSink sink) {
        this.context = Objects.requireNonNull(context, "context");
        this.sink = Objects.requireNonNull(sink, "sink");
    }

    void run() {
        sink.write("task=" + context.taskId + ",export=done");
    }
}

// Application graph: quyết định cách tạo các graph ngắn hạn.
final class ApplicationGraph {
    private final EventSink sink;
    private final ConcurrentMap<String, SessionState> sessions =
            new ConcurrentHashMap<>();

    ApplicationGraph(EventSink sink) {
        this.sink = Objects.requireNonNull(sink, "sink");
    }

    SessionState openSession(String sessionId, String userId) {
        Objects.requireNonNull(sessionId, "sessionId");
        Objects.requireNonNull(userId, "userId");

        SessionState session = sessions.computeIfAbsent(
                sessionId, id -> new SessionState(id, userId));
        if (!session.userId.equals(userId)) {
            throw new IllegalArgumentException(
                    "Một sessionId đã gắn với user khác");
        }
        return session;
    }

    RequestHandler forRequest(String requestId, SessionState session) {
        // Tạo graph mới mỗi lần; không lưu RequestContext vào field app.
        RequestContext context = new RequestContext(requestId, session);
        return new RequestHandler(context, sink);
    }

    ExportTask forTask(String taskId) {
        // Tạo graph mới cho mỗi tác vụ, không mang request context theo.
        return new ExportTask(new TaskContext(taskId), sink);
    }

    void expireSession(String sessionId) {
        sessions.remove(sessionId);
    }
}

public class ObjectGraphScopesDemo {
    public static void main(String[] args) {
        // Composition root của chương trình minh họa.
        EventSink sharedSink = new ConsoleEventSink();
        ApplicationGraph app = new ApplicationGraph(sharedSink);

        SessionState userA = app.openSession("S1", "an");
        SessionState userB = app.openSession("S2", "binh");

        // R1 và R2 khác graph nhưng cùng tham chiếu session S1.
        app.forRequest("R1", userA).handle();
        app.forRequest("R2", userA).handle();
        // R3 có session state riêng.
        app.forRequest("R3", userB).handle();

        // Các tác vụ có context độc lập, dùng chung EventSink.
        app.forTask("T1").run();
        app.forTask("T2").run();

        // Khi phiên hết hạn, registry bỏ tham chiếu do nó quản lý.
        app.expireSession("S1");
        app.expireSession("S2");
    }
}
```

Biên dịch và chạy trên JDK:

```bash
javac ObjectGraphScopesDemo.java
java ObjectGraphScopesDemo
```

Đầu ra dự kiến khi chương trình chạy tuần tự:

```text
request=R1,session=S1,user=an,visit=1
request=R2,session=S1,user=an,visit=2
request=R3,session=S2,user=binh,visit=1
task=T1,export=done
task=T2,export=done
```

### 4.1. Đâu là Composition Root và các graph con?

- `ObjectGraphScopesDemo.main` là **composition root ban đầu**: chọn `ConsoleEventSink`, tạo `ApplicationGraph`.
- `ApplicationGraph` là một **factory/registry thuộc vùng lắp ghép**, chịu trách nhiệm tạo graph theo sự kiện hoặc phiên: `openSession`, `forRequest`, `forTask`. Đây là logic wiring, không phải nghiệp vụ xác nhận đơn hay xuất báo cáo thật.
- Mỗi lời gọi `forRequest` tạo `RequestContext` và `RequestHandler` mới; request không được giữ trong `ApplicationGraph`.
- `openSession("S1", "an")` trả về cùng một `SessionState` khi session ID đã có; `S2` nhận state khác. `SessionState` là instance nằm ở graph phiên.
- `forTask` tạo `TaskContext` và `ExportTask` mới; job không dùng `RequestContext` hoặc `SessionState`.
- Cả handler và task đều nhận `EventSink` dùng chung qua constructor. Đây là **constructor injection**, dù các graph có vòng đời khác nhau.

Ví dụ dùng `ConcurrentHashMap` và `AtomicInteger` để diễn đạt ý định có thể dùng trên nhiều thread. Chúng chỉ bảo vệ **những thao tác cụ thể** của map và bộ đếm. Điều này không biến toàn bộ xử lý session, xác thực hay giao dịch thành an toàn khi có nhiều request đồng thời.

**Giới hạn của ví dụ:** `openSession` nhận tên người dùng trực tiếp để đơn giản hóa phần DI. Ứng dụng thật phải xác thực người dùng và session bằng cơ chế tin cậy trước khi tạo hoặc lấy session state. Registry trong ví dụ chỉ ở bộ nhớ của một tiến trình, chưa có timeout tự động hay cơ chế lưu trữ phân tán.

### 4.2. Vì sao graph theo request phải được tạo mới?

Hai request trong cùng phiên có thể có request ID, deadline, transaction và trạng thái xử lý khác nhau. Nếu vô tình giữ một `RequestHandler` dùng chung và cập nhật context trên field của nó trước mỗi request, hai request đồng thời có thể đọc nhầm dữ liệu của nhau.

Tạo `RequestHandler` mới cho mỗi request khiến ranh giới tham chiếu rõ ràng. Tuy nhiên, có những handler **không giữ trạng thái request** có thể an toàn khi dùng chung; lúc đó request context nên được truyền qua tham số thay vì field. Quyết định phụ thuộc vào hành vi và concurrency, không chỉ tên class.

### 4.3. Session hết hạn có làm mọi tham chiếu biến mất ngay?

Không. `expireSession("S1")` chỉ **gỡ tham chiếu của registry**. Nếu một request đang xử lý vẫn giữ `SessionState` S1, đối tượng đó vẫn tồn tại cho tới khi không còn tham chiếu liên quan và được garbage collector thu hồi khi thích hợp.

Một hệ thống thật có thể cần thêm cờ invalidation và kiểm tra thời điểm sử dụng để chặn các thao tác sau logout/timeout. **Xóa khỏi map không tự ngắt một request đang chạy**, cũng không tự thu hồi mọi tài nguyên mà session đã tạo.

## 5. Kiểm thử sự chia sẻ và cô lập giữa các scope

Tạo `ObjectGraphScopesTest.java` cùng thư mục với file demo. Ta thay sink thật bằng fake ghi sự kiện vào bộ nhớ; sau đó kiểm tra identity và dữ liệu của từng graph.

```java
import java.util.ArrayList;
import java.util.List;

final class RecordingEventSink implements EventSink {
    final List<String> events = new ArrayList<>();

    @Override
    public void write(String event) {
        events.add(event);
    }
}

public class ObjectGraphScopesTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        RecordingEventSink fake = new RecordingEventSink();
        ApplicationGraph app = new ApplicationGraph(fake);

        SessionState a = app.openSession("S1", "an");
        SessionState sameA = app.openSession("S1", "an");
        SessionState b = app.openSession("S2", "binh");

        check(a == sameA, "Cùng session phải dùng lại SessionState");
        check(a != b, "Hai session không được dùng cùng state");

        RequestHandler r1 = app.forRequest("R1", a);
        RequestHandler r2 = app.forRequest("R2", a);
        check(r1 != r2, "Mỗi request cần handler riêng trong ví dụ");

        r1.handle();
        r2.handle();
        app.forRequest("R3", b).handle();

        ExportTask t1 = app.forTask("T1");
        ExportTask t2 = app.forTask("T2");
        check(t1 != t2, "Hai task phải có instance riêng");

        t1.run();
        t2.run();

        check(fake.events.size() == 5, "Sai số lượng sự kiện");
        check(fake.events.get(0).equals(
                "request=R1,session=S1,user=an,visit=1"), "Sai R1");
        check(fake.events.get(1).equals(
                "request=R2,session=S1,user=an,visit=2"), "Sai R2");
        check(fake.events.get(2).equals(
                "request=R3,session=S2,user=binh,visit=1"), "Sai R3");
        check(fake.events.get(3).equals(
                "task=T1,export=done"), "Sai T1");
        check(fake.events.get(4).equals(
                "task=T2,export=done"), "Sai T2");

        app.expireSession("S1");
        SessionState restarted = app.openSession("S1", "an");
        check(restarted != a, "Phiên tạo lại phải có state mới");

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac ObjectGraphScopesDemo.java ObjectGraphScopesTest.java
java ObjectGraphScopesTest
```

Kết quả dự kiến: `PASS`.

Bài test xác nhận **scope identity theo quy ước của ví dụ**: cùng session dùng cùng state cho đến khi hết hạn, request và task mới có instance mới, các session không dùng chung bộ đếm. Đây là unit test chạy tuần tự. Nó **không kiểm chứng** tính đúng đắn khi xử lý nhiều thread, timeout thực tế, phân phối session giữa nhiều tiến trình hoặc giao dịch database. Những đặc điểm đó cần kiểm thử tích hợp và concurrency thích hợp khi triển khai thật.

## 6. Các cách lỗi scope xuất hiện trong ứng dụng

### 6.1. Singleton giữ request context từ lần đầu

```java
// Anti-pattern: service dùng chung nhưng giữ state của một request.
final class UnsafeSharedService {
    private final RequestContext firstRequest;

    UnsafeSharedService(RequestContext firstRequest) {
        this.firstRequest = firstRequest;
    }

    String currentRequestId() {
        return firstRequest.requestId;
    }
}
```

Nếu `UnsafeSharedService` sống suốt ứng dụng, mọi request sau có nguy cơ nhìn thấy ID của request đầu. Cách thay thế thường đơn giản là truyền `requestId`/context của **lần xử lý hiện tại** qua tham số:

```java
final class SharedService {
    String currentRequestId(RequestContext request) {
        return request.requestId;
    }
}
```

Bản thân `SharedService` không giữ state theo request. Khi cần tạo một collaborator request-scoped, hãy tạo nó tại **request composition boundary** hoặc một factory có scope phù hợp.

### 6.2. Session graph giữ resource ngắn hạn

Giả sử session giữ một `Connection` hoặc transaction đang mở để tái sử dụng cho nhiều request. Transaction có thể timeout, resource bị giữ quá lâu, và nhiều request đồng thời có thể tranh chấp connection. Thường nên giữ **dữ liệu phiên cần thiết** trong session, còn transaction hoặc unit-of-work được tạo theo từng request/tác vụ.

Tương tự, không đưa một `RequestContext` vào session chỉ vì muốn đọc request ID từ request sau.

### 6.3. Async task giữ lại request hoặc session object

```java
// Mã minh họa anti-pattern (không chạy độc lập):
queue.submit(() -> exportReport(requestContext));
```

Nếu `exportReport` chạy sau khi request đã kết thúc, `requestContext` có thể không còn hợp lệ; nó cũng giữ tham chiếu tới dữ liệu có thể nhạy cảm lâu hơn cần thiết. Thay vào đó, xác định payload tối thiểu mà job cần, ví dụ `reportId`, định danh đã xác thực hoặc snapshot dữ liệu được phép lưu, rồi **tạo TaskContext riêng ở worker**.

Nếu job phải sử dụng quyền truy cập của người dùng, cần thiết kế rõ cách tái xác thực, thời hạn ủy quyền và chính sách khi phiên đã hết hạn; không mặc định dựa vào `ThreadLocal` hoặc object session còn trong bộ nhớ.

### 6.4. Lẫn lộn scope với ThreadLocal

`ThreadLocal` gắn dữ liệu với thread, không phải với một HTTP request theo nghĩa nghiệp vụ. Với thread pool, quên cleanup có thể làm request sau nhận dữ liệu của request trước; với async xử lý chuyển thread, context có thể mất. Cơ chế request scope do framework cung cấp vẫn cần được dùng và cấu hình theo đúng lifecycle của framework.

### 6.5. Session registry không có giới hạn hoặc dọn dẹp

Giữ mỗi session trong một `Map` mà không timeout/logout/eviction sẽ khiến bộ nhớ tăng theo số phiên. Mục 4 chỉ có `expireSession` để minh họa hành động gỡ khỏi registry. Production cần cơ chế quản lý thực tế: TTL, invalidation, giám sát số session, tính nhất quán khi scale, và dọn những tài nguyên do phiên sở hữu.

### 6.6. Tạo client và pool đắt tiền cho mọi request

Không phải mọi dependency đều nên request-scoped. Việc tạo mới HTTP client, connection pool hoặc executor đắt tiền trong từng request có thể làm tốn tài nguyên. Những thành phần được thiết kế để dùng chung có thể thuộc application graph; còn connection hoặc transaction cụ thể có thể có vòng đời ngắn hơn theo hợp đồng của thư viện.

## 7. Scope khác với thời điểm tạo và quyền sở hữu tài nguyên

Ba câu hỏi cần tách riêng:

1. **Scope:** trong những lần sử dụng nào hệ thống trả về **cùng instance**?
2. **Creation timing:** instance được tạo lúc khởi động, lần đầu sử dụng, đầu request hay lúc task bắt đầu?
3. **Ownership/lifecycle:** ai có trách nhiệm giải phóng và hủy bỏ tài nguyên khi scope kết thúc?

Ví dụ, một adapter application-scoped có thể được tạo *lazy* lần đầu dùng, nhưng sau đó dùng chung. Một request-scoped handler có thể được tạo ngay khi request bắt đầu hoặc khi use case cụ thể cần đến. Hai lựa chọn khác thời điểm tạo nhưng vẫn cùng chính sách scope.

| Loại tài nguyên | Scope thường cân nhắc | Điều phải kiểm tra |
| --- | --- | --- |
| Cấu hình bất biến, clock hoặc service không giữ state | Application | Có an toàn khi chia sẻ và không giữ dữ liệu request không? |
| Connection pool/HTTP client có hỗ trợ tái sử dụng | Application | Chính sách concurrency và shutdown của thư viện là gì? |
| HTTP request context, transaction của request | Request | Có cleanup kể cả khi exception/cancel không? |
| Trạng thái phiên cần qua nhiều request | Session | Có giới hạn, timeout, chính sách đồng thời và storage phù hợp không? |
| Context, transaction, file tạm của job | Task | Có retry/cancel/cleanup và không phụ thuộc request cũ không? |

**DI không tự quản lý vòng đời tài nguyên bằng phép truyền qua constructor.** Trong Java thuần, composition boundary phải đảm nhận phần dọn dẹp thích hợp, ví dụ dùng `try-with-resources` cho `AutoCloseable`:

```java
// Pseudocode: UnitOfWork phải implements AutoCloseable.
void runTask(TaskInput input, UnitOfWorkFactory factory) {
    try (UnitOfWork work = factory.open()) {
        work.process(input);
        work.commit();
    }
}
```

Tại đây, một task mở một unit-of-work mới và đóng ở cuối scope. Nếu `process` thất bại, `close` vẫn được gọi; việc rollback/commit phải theo đúng contract của `UnitOfWork`. `try-with-resources` không tự biến mọi tài nguyên hay thao tác database thành giao dịch đúng.

## 8. Tạo đồ thị bằng factory, provider hoặc DI container

Với Java thuần, `ApplicationGraph.forRequest(...)` và `forTask(...)` trong ví dụ là **factory method** rõ ràng. Nó tạo graph ngắn hạn khi có sự kiện tương ứng. Cách này đủ cho nhiều ứng dụng nhỏ và giúp nhìn thấy nơi scope bắt đầu.

Trong hệ thống lớn, DI container có thể cung cấp application/singleton scope, request scope và những scope khác tùy framework. Một số container không có session hoặc task scope mặc định; phải đọc tài liệu và đăng ký scope phù hợp nếu thật sự cần.

**Phân biệt quan trọng:**

- Inject **một request-scoped instance cố định** vào application singleton có thể gây sai vòng đời.
- Inject một **factory/provider** vào singleton, sau đó gọi provider **trong scope hợp lệ của yêu cầu hiện tại**, có thể là một giải pháp. Provider phải biết cách xác định scope hiện hành, và lời gọi ngoài scope có thể báo lỗi.
- Dùng một container toàn cục rồi gọi `get(...)` từ mọi lớp nghiệp vụ là một dạng **Service Locator**: dependency trở nên ẩn và khó kiểm thử. Giữ việc lắp ghép ở composition root hoặc ranh giới factory thích hợp.

Một instance mới cho mỗi lần gọi provider chưa chắc là request scope: muốn một dependency **dùng chung trong cùng request**, provider/container phải duy trì đúng identity theo request. Sự khác biệt giữa *prototype/transient* và *request-scoped* ảnh hưởng trực tiếp tới transaction, context và bộ nhớ đệm theo request.

## 9. Cách thiết kế graph cho một use case thực tế

Giả sử một API nhận yêu cầu đặt hàng, có một worker xử lý email nền và có giỏ hàng theo phiên:

1. **Application graph:** tạo HTTP client, database pool, repository adapter, sender adapter, các service dùng chung thích hợp. Định nghĩa cách đóng các client/pool khi application dừng.
2. **Session graph:** lưu giỏ hàng theo đúng định danh phiên đã xác thực; không giữ database transaction hoặc request context. Thiết lập timeout, invalidation và cách xử lý nhiều request đồng thời.
3. **Request graph:** mỗi HTTP request nhận request ID, thông tin người dùng đã xác thực, transaction hoặc đơn vị công việc nếu cần. Controller/handler dùng các service chia sẻ, đọc/ghi giỏ hàng qua đúng session.
4. **Task graph:** khi email được đưa vào queue, ghi payload tối thiểu như `orderId`; worker tạo context và dependency của job khi lấy thông điệp. Retry/cancel và cleanup không phụ thuộc vào request tạo job.
5. **Kiểm thử:** xác nhận đúng instance được chia sẻ, đúng instance được cô lập, sai scope bị phát hiện, timeout/cleanup hoạt động và luồng thực thi thật không rò dữ liệu giữa người dùng.

Trước khi nối một dependency vào graph, hãy tự hỏi: **“Nếu instance này còn được sử dụng sau khi scope tạo ra nó kết thúc, chuyện gì xảy ra?”** Nếu câu trả lời là “đọc state cũ”, “resource đã đóng”, “giữ session không hết hạn” hoặc “dùng identity không còn hợp lệ”, quan hệ tham chiếu đó cần được thiết kế lại.

## 10. Bài tập thực hành và gợi ý đối chiếu

**Bối cảnh:** ứng dụng có `CatalogService`, `ShoppingCart`, `CheckoutHandler`, `EmailJob` và `DatabaseConnectionPool`. Người dùng có thể gửi hai request đồng thời, đăng xuất giữa chừng và đặt đơn hàng được xử lý qua queue.

Hãy làm các yêu cầu:

1. Vẽ graph theo application, request, session và task. Đặt từng thành phần vào scope hợp lý, nêu giả định về state/concurrency.
2. Giải thích vì sao `CheckoutHandler` thường không nên được lưu vĩnh viễn cùng một `RequestContext` trong application singleton.
3. Giả sử `ShoppingCart` là mutable session state, mô tả cách hai request cùng phiên cập nhật giỏ hàng mà không mất dữ liệu.
4. Đề xuất payload cho `EmailJob` để worker có thể chạy sau khi request và session ban đầu đã kết thúc.
5. Viết một factory Java thuần tạo `CheckoutHandler` cho mỗi request từ service dùng chung và request context mới.
6. Định nghĩa bài test xác nhận hai request khác nhau không dùng chung context, hai request của cùng phiên dùng đúng cart state, hai phiên khác nhau không lẫn dữ liệu.
7. Nêu cách dọn tài nguyên khi request thất bại, task bị hủy, session hết hạn và ứng dụng shutdown.

**Gợi ý đối chiếu:** connection pool được thiết kế tái sử dụng thường thuộc application scope; request context và handler có state theo request thuộc request graph; giỏ hàng theo session cần storage, đồng bộ, timeout phù hợp; email job sở hữu task context riêng và lấy dữ liệu từ hệ thống lưu trữ qua ID thay vì giữ object request. Scope đúng không tự đảm bảo an toàn đồng thời, idempotency hay tính nhất quán dữ liệu: các đặc tính đó cần thiết kế và kiểm thử riêng.

**Điểm cần nhớ:** Object graph thay đổi theo vòng đời của ứng dụng, request, task và session. Composition root cùng các factory/scope boundary tạo đúng dependency tại đúng thời điểm; constructor injection giúp quan hệ sử dụng tường minh. Hãy chú ý identity, tham chiếu từ đối tượng sống lâu sang đối tượng sống ngắn, concurrency và quyền sở hữu tài nguyên trước khi tự động hóa việc lắp ghép bằng DI container.
