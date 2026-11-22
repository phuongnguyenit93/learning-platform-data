# Kiểm chứng vòng đời khi ứng dụng khởi động, phục vụ và kết thúc

## 1. Vì sao cần kiểm chứng vòng đời, thay vì chỉ lắp ghép đúng kiểu?

**Dependency Injection (DI)** tách việc *sử dụng* một phụ thuộc khỏi việc *tạo và lắp ghép* nó. Với **constructor injection**, lớp nghiệp vụ nhận các cộng tác viên qua constructor; **composition root** chọn implementation, xây dựng object graph và quyết định nơi sở hữu các tài nguyên. Đây là một cách thực hiện **Inversion of Control (IoC)** bằng Java thuần, trước khi cần đến DI container.

Nhưng một object graph biên dịch thành công vẫn có thể sai ở thời điểm chạy:

- Ứng dụng nhận request khi một client hoặc repository chưa khởi tạo xong.
- Khởi động bị lỗi sau khi mở connection pool, làm pool không được đóng.
- Mỗi request tự tạo một client đắt tiền dù client đó được thiết kế để dùng chung.
- Một request giữ tài nguyên sau khi trả response, hoặc singleton giữ trạng thái của request đầu tiên.
- Khi tắt ứng dụng, tài nguyên bị đóng trước lúc xử lý đang chạy hoàn tất.
- Cùng một tài nguyên bị nhiều thành phần cùng coi là chủ sở hữu và cùng gọi `close()`.

Vì vậy, học **vòng đời và phạm vi (lifecycle and scopes)** cần kiểm chứng **khi nào đối tượng được tạo, được phép sử dụng, ngừng nhận công việc và được giải phóng**. Các điều kiện này quan trọng ngang với việc dependency được inject qua constructor.

**Sau bài này, bạn có thể:**

1. Mô tả các pha **khởi động → sẵn sàng → phục vụ → dừng nhận việc → dọn dẹp → kết thúc**.
2. Xác định quy tắc scope và ownership cho tài nguyên sống theo ứng dụng, request, tác vụ hoặc phiên.
3. Viết composition root có khả năng thu hồi tài nguyên nếu khởi tạo thất bại giữa chừng.
4. Dùng Java thuần và fake ghi sự kiện để xác minh thứ tự mở/đóng, dọn dẹp khi gặp lỗi và việc không sử dụng sau `close()`.
5. Phân biệt một bài kiểm thử vòng đời đơn luồng với kiểm thử shutdown thật trong server đồng thời.

## 2. Mô hình vòng đời của một ứng dụng

Một mô hình đơn giản có thể biểu diễn như sau:

```text
             STARTING
     đọc cấu hình, tạo dependency
                 |
          tạo thành công?
           /           \
         không          có
          |              |
     dọn phần đã mở     READY
          |              |
       FAILED        SERVING
                  phục vụ request/task
                      |
                 yêu cầu tắt
                      |
                  STOPPING
            ngừng tiếp nhận việc mới
                      |
                   DRAINING
             hoàn tất/hủy việc còn lại
                      |
                   CLOSING
           đóng dependency được sở hữu
                      |
                   STOPPED
```

`DRAINING` là pha cần đặc biệt chú ý với ứng dụng có xử lý đồng thời hoặc background worker. Với chương trình CLI xử lý tuần tự, có thể không có yêu cầu đang chạy vào lúc đóng, nên pha này không biểu hiện thành một khoảng chờ.

### 2.1. Những bất biến cần xác minh

| Pha | Điều phải đúng | Lỗi điển hình |
| --- | --- | --- |
| **STARTING** | Dependency bắt buộc có cấu hình hợp lệ; tạo theo thứ tự phụ thuộc; tài nguyên đã tạo thành công có chủ sở hữu. | Mở được pool rồi lỗi tạo mail client, pool bị bỏ quên. |
| **READY** | Object graph cần thiết đã lắp ghép xong; chỉ lúc này mới cho nhận công việc. | Cổng HTTP đã nhận request trong khi adapter còn chưa sẵn sàng. |
| **SERVING** | Mỗi request/task có đúng context, scope và cleanup; dependency dùng chung còn sống. | Singleton giữ `RequestContext`; request dùng connection đã đóng. |
| **STOPPING/DRAINING** | Không tiếp nhận thêm việc mới; xử lý việc còn lại theo chính sách đã chọn. | Đóng database pool trong khi request chưa kết thúc. |
| **CLOSING** | Chỉ chủ sở hữu giải phóng tài nguyên; các tài nguyên phụ thuộc được đóng theo thứ tự hợp lý; lỗi đóng không làm bỏ qua toàn bộ cleanup. | Đóng dependency nền trước đối tượng còn phải sử dụng nó để dọn dẹp. |
| **STOPPED** | Không thực hiện nghiệp vụ qua graph đã đóng; không giữ tài nguyên ngoài phạm vi cho phép. | Vẫn chấp nhận request hoặc chạy job trên client đã đóng. |

Một hệ thống có thể có các trạng thái phụ như `DEGRADED`, `RESTARTING` hoặc `UNHEALTHY`; đó là chính sách vận hành riêng. Điều cốt lõi là **không công bố READY trước khi đáp ứng điều kiện sẵn sàng đã định nghĩa**.

### 2.2. “Đã tạo” không có nghĩa là “đã sẵn sàng”

Constructor của một adapter có thể chỉ lưu cấu hình; kết nối thật được mở sau đó. Ngược lại, một constructor có thể chủ động mở socket hoặc đọc tài nguyên. Vì vậy, việc `new Client(...)` thành công không tự chứng minh endpoint thật truy cập được.

Composition root cần xác định một **readiness contract** có ý nghĩa với ứng dụng: ví dụ xác thực cấu hình, khởi tạo pool và hoàn tất bước kiểm tra kết nối cần thiết. Readiness khác liveness: một ứng dụng còn chạy chưa chắc đã sẵn sàng phục vụ.

## 3. Scope, quyền sở hữu và thứ tự đóng

**Scope** trả lời “những lần sử dụng nào chia sẻ cùng instance?”. **Ownership** trả lời “ai chịu trách nhiệm đóng instance hoặc tài nguyên này?”. **Lifecycle** trả lời “khi nào instance hợp lệ để dùng và khi nào kết thúc?”.

| Phạm vi | Ví dụ | Quy tắc vòng đời |
| --- | --- | --- |
| **Application** | Cấu hình bất biến, HTTP client dùng chung, connection pool, application service không giữ trạng thái request. | Tạo ở bootstrap hoặc lazy có kiểm soát; dùng trong suốt ứng dụng; đóng khi đã dừng công việc phụ thuộc. |
| **Request** | Request context, transaction, unit of work, stream mở cho một yêu cầu. | Tạo ở đầu request hoặc khi cần; dọn cả khi thành công, exception hoặc hủy. |
| **Task/job** | Job context, resource dành cho một message, file tạm xử lý batch. | Mỗi tác vụ có ranh giới cleanup riêng; retry phải tạo/khôi phục trạng thái theo hợp đồng. |
| **Session** | Giỏ hàng, phiên đã xác thực hoặc trạng thái cần dùng qua nhiều request. | Kéo dài qua nhiều request; hết hạn khi logout/timeout/invalidation; không giữ resource request đã hết hạn. |

Đối tượng sống lâu **không nên giữ trực tiếp instance sống ngắn hơn** rồi dùng nó sau khi scope ngắn kết thúc. Một application-scoped service có thể nhận `RequestContext` dưới dạng *tham số phương thức* mà không lưu lại; hoặc nhận factory/provider phù hợp để tạo dependency cho scope hiện tại.

### 3.1. Ai tạo chưa chắc là ai sở hữu

Ví dụ, `OrderService` nhận `OrderRepository` qua constructor. Nó **sử dụng** repository nhưng không nhất thiết phải gọi `repository.close()`; composition root có thể là chủ sở hữu repository và truyền cùng instance vào nhiều service.

Hãy ghi rõ quy ước:

- **Composition root** thường sở hữu client, pool và adapter ứng dụng do nó tạo.
- **Request boundary** thường sở hữu transaction, unit of work hoặc stream của request.
- **Task boundary** thường sở hữu tài nguyên riêng của job.
- Đối tượng được **mượn** từ một scope khác chỉ sử dụng theo contract, không tự đóng tài nguyên dùng chung.

Nếu một tài nguyên A cần tài nguyên B trong quá trình khởi tạo và dọn dẹp, thứ tự an toàn thường là **tạo B trước A, đóng A trước B**. Quy tắc này không thay thế contract cụ thể của thư viện, nhưng là điểm bắt đầu hợp lý khi lắp graph.

### 3.2. `AutoCloseable` giải quyết điều gì?

Java có `AutoCloseable` để mô tả thao tác `close()`; `try-with-resources` tự gọi `close()` khi thoát scope, kể cả khi khối lệnh phát sinh exception. Ví dụ:

```java
// UnitOfWork là kiểu giả định triển khai AutoCloseable.
try (UnitOfWork work = unitOfWorkFactory.open()) {
    work.execute();
}
```

Đoạn này đảm bảo `close()` được *gọi* khi thoát block, nhưng **không bảo đảm** việc rollback/commit diễn ra đúng, cleanup luôn thành công hay toàn bộ object graph được giải phóng. Các điều đó phụ thuộc implementation và chính sách nghiệp vụ.

Một interface sử dụng thuần như `OrderRepository` cũng không nhất thiết cần `extends AutoCloseable`. Composition root có thể giữ concrete adapter vừa triển khai `OrderRepository`, vừa triển khai `AutoCloseable`, qua hai vai trò riêng: một vai trò được inject để sử dụng, một vai trò để quản lý lifecycle.

## 4. Ví dụ Java thuần: khởi động, phục vụ và đóng theo thứ tự

Ví dụ sau dùng các adapter giả ghi sự kiện vào danh sách. Nó cố ý **không mở mạng hoặc database thật**, để kiểm tra thứ tự vòng đời một cách xác định.

Chương trình chạy tuần tự; chưa mô phỏng request đồng thời hoặc một server thực hiện graceful shutdown.

Lưu toàn bộ đoạn sau vào `LifecycleDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Objects;

interface OrderRepository {
    void save(String orderId);
}

interface ReceiptSender {
    void send(String orderId);
}

// Tài nguyên minh họa thuộc application scope.
final class TrackedRepository implements OrderRepository, AutoCloseable {
    private final List<String> events;
    private boolean closed;

    TrackedRepository(List<String> events) {
        this.events = Objects.requireNonNull(events, "events");
        events.add("repo:open");
    }

    @Override
    public void save(String orderId) {
        if (closed) {
            throw new IllegalStateException("Repository đã đóng");
        }
        events.add("repo:save:" + orderId);
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            events.add("repo:close");
        }
    }
}

final class TrackedSender implements ReceiptSender, AutoCloseable {
    private final List<String> events;
    private boolean closed;

    TrackedSender(List<String> events, boolean failOnOpen) {
        this.events = Objects.requireNonNull(events, "events");
        events.add("sender:open");
        if (failOnOpen) {
            events.add("sender:failed");
            // Giả định constructor chưa chiếm tài nguyên khi ném lỗi.
            throw new IllegalStateException("Không khởi tạo được sender");
        }
    }

    @Override
    public void send(String orderId) {
        if (closed) {
            throw new IllegalStateException("Sender đã đóng");
        }
        events.add("sender:send:" + orderId);
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            events.add("sender:close");
        }
    }
}

// Tài nguyên ngắn hạn: mỗi request có một instance.
final class RequestScope implements AutoCloseable {
    private final String requestId;
    private final List<String> events;
    private boolean closed;

    RequestScope(String requestId, List<String> events) {
        this.requestId = Objects.requireNonNull(requestId, "requestId");
        this.events = Objects.requireNonNull(events, "events");
        events.add("request:" + requestId + ":open");
    }

    void assertActive() {
        if (closed) {
            throw new IllegalStateException("Request scope đã đóng");
        }
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            events.add("request:" + requestId + ":close");
        }
    }
}

// Logic nghiệp vụ chỉ nhận và sử dụng dependency.
final class OrderService {
    private final OrderRepository repository;
    private final ReceiptSender sender;

    OrderService(OrderRepository repository, ReceiptSender sender) {
        this.repository = Objects.requireNonNull(repository, "repository");
        this.sender = Objects.requireNonNull(sender, "sender");
    }

    void confirm(String orderId, RequestScope request) {
        Objects.requireNonNull(orderId, "orderId");
        request.assertActive();

        repository.save(orderId);
        sender.send(orderId);
    }
}

// Đại diện cho object graph đã lắp ghép xong.
// Nó sở hữu các tài nguyên application-scoped trong Deque.
final class AppRuntime implements AutoCloseable {
    private final OrderService orders;
    private final Deque<AutoCloseable> owned;
    private final List<String> events;
    private boolean closed;

    AppRuntime(OrderService orders,
               Deque<AutoCloseable> owned,
               List<String> events) {
        this.orders = Objects.requireNonNull(orders, "orders");
        this.owned = Objects.requireNonNull(owned, "owned");
        this.events = Objects.requireNonNull(events, "events");
    }

    void serve(String requestId) {
        if (closed) {
            throw new IllegalStateException("Ứng dụng đã dừng");
        }
        // try-with-resources đóng request scope kể cả khi xử lý lỗi.
        try (RequestScope request = new RequestScope(requestId, events)) {
            orders.confirm(requestId, request);
        }
    }

    @Override
    public void close() {
        if (closed) {
            return; // Idempotent trong mô hình đơn luồng này.
        }
        closed = true;
        events.add("app:stopping");

        RuntimeException problem = null;
        while (!owned.isEmpty()) {
            try {
                owned.pop().close(); // Đóng ngược thứ tự được push.
            } catch (Exception failure) {
                if (problem == null) {
                    problem = new IllegalStateException(
                            "Không đóng hết tài nguyên", failure);
                } else {
                    problem.addSuppressed(failure);
                }
            }
        }
        events.add("app:stopped");
        if (problem != null) {
            throw problem;
        }
    }
}

public class LifecycleDemo {
    // Composition root: tạo, nối và chuyển quyền sở hữu tài nguyên.
    static AppRuntime start(List<String> events, boolean failSender) {
        Deque<AutoCloseable> owned = new ArrayDeque<>();

        try {
            TrackedRepository repository = new TrackedRepository(events);
            owned.push(repository);

            TrackedSender sender = new TrackedSender(events, failSender);
            owned.push(sender);

            OrderService service = new OrderService(repository, sender);
            AppRuntime runtime = new AppRuntime(service, owned, events);
            events.add("app:ready");
            return runtime;
        } catch (RuntimeException | Error failure) {
            // Khởi động thất bại: chỉ đóng những tài nguyên đã tạo xong.
            while (!owned.isEmpty()) {
                try {
                    owned.pop().close();
                } catch (Exception cleanupFailure) {
                    failure.addSuppressed(cleanupFailure);
                }
            }
            throw failure;
        }
    }

    public static void main(String[] args) {
        List<String> events = new ArrayList<>();

        // AppRuntime sở hữu application resources cho đến khi thoát try.
        try (AppRuntime runtime = start(events, false)) {
            runtime.serve("R1");
            runtime.serve("R2");
        }

        for (String event : events) {
            System.out.println(event);
        }
    }
}
```

Chạy:

```bash
javac LifecycleDemo.java
java LifecycleDemo
```

Đầu ra mong đợi:

```text
repo:open
sender:open
app:ready
request:R1:open
repo:save:R1
sender:send:R1
request:R1:close
request:R2:open
repo:save:R2
sender:send:R2
request:R2:close
app:stopping
sender:close
repo:close
app:stopped
```

### 4.1. Từ dấu vết, ta đã kiểm chứng được gì?

- **Khởi động:** `repo:open`, `sender:open` xuất hiện trước `app:ready`. `OrderService` chỉ được dùng sau khi được cung cấp hai dependency.
- **Phục vụ:** mỗi lần gọi `serve` tạo một `RequestScope`, làm việc, rồi đóng request scope. Hai request có **scope riêng**, trong khi repository và sender được dùng chung.
- **Kết thúc:** `app:stopping` xuất hiện trước các sự kiện đóng; sender và repository được đóng **ngược thứ tự chúng được đăng ký** trong `owned`.
- **Ownership:** `OrderService` không gọi `close()` trên repository/sender; `AppRuntime` giữ vai trò chủ sở hữu tài nguyên ứng dụng.
- **Chặn sử dụng sau khi đóng:** `AppRuntime.serve` từ chối request mới nếu `closed == true`; concrete adapters cũng kiểm tra trạng thái trước khi dùng.

**Giới hạn của mô hình:** các cờ `boolean closed` và `ArrayDeque` trong ví dụ không được đồng bộ hóa. Chúng minh họa vòng đời **đơn luồng**; không được xem là giải pháp shutdown đồng thời cho web server thật.

### 4.2. Nếu khởi động thất bại giữa chừng?

Gọi:

```java
List<String> events = new ArrayList<>();
try {
    LifecycleDemo.start(events, true);
} catch (IllegalStateException expected) {
    // Sender không khởi động được; repository phải được đóng.
}
```

Kết quả danh sách sự kiện:

```text
repo:open
sender:open
sender:failed
repo:close
```

Không có `app:ready`. Repository đã tạo thành công sẽ được giải phóng; sender thất bại **ngay trong constructor** nên không được đăng ký vào stack ownership. Ví dụ giả định sender **chưa chiếm tài nguyên** trước khi ném lỗi; adapter thật nếu cấp phát từng phần trong constructor phải tự cleanup phần đã cấp phát hoặc dùng factory có bước khởi tạo và rollback rõ ràng.

Khi khởi động hoàn tất, `owned` được chuyển cho `AppRuntime`; từ đó root chạy ứng dụng chịu trách nhiệm đóng. Khi khởi động thất bại, method `start` tự đóng các tài nguyên mà nó đã tạo xong. Cách chuyển ownership này tránh vừa rò rỉ vừa đóng hai lần.

## 5. Bài kiểm thử vòng đời không phụ thuộc framework

Không cần một DI container hay thư viện mock để kiểm tra *thứ tự*, *số lần* và *các mốc* của vòng đời. Fake lưu lại sự kiện trong một danh sách là đủ cho bài kiểm thử đơn luồng.

Lưu mã sau vào `LifecycleDemoTest.java`, cùng thư mục với `LifecycleDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class LifecycleDemoTest {
    static void assertEvents(List<String> expected, List<String> actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected: " + expected + "\nActual: " + actual);
        }
    }

    static void assertTrue(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        List<String> good = new ArrayList<>();
        AppRuntime app = LifecycleDemo.start(good, false);

        app.serve("R1");
        app.serve("R2");
        app.close();
        app.close(); // Gọi lần thứ hai không đóng tài nguyên lần nữa.

        boolean rejectedAfterClose = false;
        try {
            app.serve("R3");
        } catch (IllegalStateException expected) {
            rejectedAfterClose = true;
        }
        assertTrue(rejectedAfterClose, "Vẫn chấp nhận việc sau shutdown");

        assertEvents(Arrays.asList(
                "repo:open",
                "sender:open",
                "app:ready",
                "request:R1:open",
                "repo:save:R1",
                "sender:send:R1",
                "request:R1:close",
                "request:R2:open",
                "repo:save:R2",
                "sender:send:R2",
                "request:R2:close",
                "app:stopping",
                "sender:close",
                "repo:close",
                "app:stopped"), good);

        // Kiểm thử rollback nếu bootstrap thất bại.
        List<String> failed = new ArrayList<>();
        boolean startupFailed = false;
        try {
            LifecycleDemo.start(failed, true);
        } catch (IllegalStateException expected) {
            startupFailed = true;
        }
        assertTrue(startupFailed, "Startup phải báo lỗi");
        assertEvents(Arrays.asList(
                "repo:open",
                "sender:open",
                "sender:failed",
                "repo:close"), failed);

        // try-with-resources đóng request scope dù khối lệnh ném lỗi.
        List<String> requestFailed = new ArrayList<>();
        boolean workFailed = false;
        try (RequestScope request =
                     new RequestScope("FAIL", requestFailed)) {
            request.assertActive();
            throw new IllegalStateException("Giả lập lỗi xử lý");
        } catch (IllegalStateException expected) {
            workFailed = true;
        }
        assertTrue(workFailed, "Không ghi nhận lỗi xử lý");
        assertEvents(Arrays.asList(
                "request:FAIL:open",
                "request:FAIL:close"), requestFailed);

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac LifecycleDemo.java LifecycleDemoTest.java
java LifecycleDemoTest
```

Kết quả mong đợi: `PASS`.

Bài test xác minh rõ ràng các **bất biến vòng đời**: chỉ sẵn sàng khi tạo graph xong; mỗi request được dọn; application resource đóng đúng thứ tự; `close()` lần hai không đóng lặp; dùng sau đóng bị từ chối; khởi động lỗi có rollback; khối xử lý request lỗi vẫn gọi cleanup.

Đây là **unit test của mô hình vòng đời**, không chứng minh web server thật đã drain request đồng thời, JDBC pool đã đóng đúng hay shutdown hook luôn được chạy. Các phần đó cần integration test, stress test hoặc thử nghiệm có kiểm soát trên môi trường chạy thực.

## 6. Kiểm chứng khi phục vụ: tránh lỗi scope

Trong một ứng dụng server, các thành phần khác nhau thường có scope khác nhau:

```text
APPLICATION SCOPE
  DataSource / HTTP client / OrderService (nếu thread-safe)
       |
       +---- REQUEST A ---- RequestContext A, UnitOfWork A
       |
       +---- REQUEST B ---- RequestContext B, UnitOfWork B
       |
       +---- TASK T ------- TaskContext T, Job resources T
```

Có ba phép kiểm tra cơ bản:

1. **Identity:** hai request phải nhận context riêng nếu contract nói request-scoped; những request cần cùng application client phải được cấp chung instance.
2. **Không rò tham chiếu:** object ứng dụng sống lâu không lưu một `RequestContext` hoặc transaction cụ thể qua nhiều request.
3. **Cleanup dù lỗi:** transaction, temporary file hoặc resource thuộc request được dọn trong `finally` hoặc `try-with-resources`, kể cả khi nghiệp vụ ném exception.

**Ví dụ sai:**

```java
// Không nên inject một RequestContext cụ thể vào singleton.
final class SharedService {
    private final RequestContext firstRequest;

    SharedService(RequestContext firstRequest) {
        this.firstRequest = firstRequest;
    }
}
```

Nếu `SharedService` sống suốt tiến trình, nó có thể giữ dữ liệu người dùng từ request đầu. Với service dùng chung, hãy truyền dữ liệu request qua tham số phương thức hoặc dùng một factory/provider truy xuất đúng request scope đang hoạt động. Chỉ việc đổi annotation của container chưa đủ nếu code vẫn giữ tham chiếu sai.

**Trường hợp session:** một session có thể sống qua nhiều request, nhưng vẫn cần expiration, invalidation, giới hạn bộ nhớ và xử lý request đồng thời. Một session state mutable không tự thread-safe; một HTTP request context không tự trở thành session-scoped chỉ vì được lưu vào field của session.

## 7. Kiểm chứng lúc kết thúc: thứ tự shutdown trong ứng dụng đồng thời

Ứng dụng web hoặc worker thực tế có thể đang xử lý hàng trăm request/job khi nhận lệnh dừng. **Đóng pool ngay khi nhận tín hiệu shutdown là không an toàn** nếu các tác vụ còn cần pool.

Một trình tự thường hợp lý:

1. **Ngừng nhận việc mới:** đưa ứng dụng ra khỏi luồng nhận traffic theo cơ chế triển khai; dừng tạo job mới và dừng nhận message mới.
2. **Drain công việc đang chạy:** chờ các request/job hiện tại hoàn tất trong một giới hạn đã định; nếu quá hạn, áp dụng chính sách hủy, rollback hoặc ghi lại trạng thái để retry.
3. **Đóng scope ngắn hạn:** bảo đảm mọi request/task context, transaction và stream đang mở được dọn sau khi công việc tương ứng kết thúc hoặc bị hủy.
4. **Đóng tài nguyên dùng chung:** đóng client, producer, connection pool và executor theo thứ tự tôn trọng quan hệ phụ thuộc.
5. **Ghi nhận kết quả:** đánh dấu dừng hoàn tất hoặc báo rõ những lỗi cleanup cần theo dõi.

```text
STOP SIGNAL
    |
    v
Stop accepting new work
    |
    v
Drain/cancel in-flight requests and jobs
    |
    v
Close remaining request/task scopes
    |
    v
Close application resources in dependency-safe order
    |
    v
STOPPED
```

Không thể suy ra chính sách timeout, thời gian chờ hoặc cơ chế hủy phù hợp nếu chưa biết server, queue, transaction và yêu cầu độ tin cậy. Ví dụ `AppRuntime` phía trên chỉ có phương thức `close()` **đơn luồng**, không phải một thuật toán graceful shutdown có thể dùng nguyên trong production.

### 7.1. Nếu `close()` ném exception thì sao?

Một tài nguyên có thể không đóng được, nhưng vẫn cần thử đóng những tài nguyên còn lại. Trong mã demo, vòng lặp tiếp tục `close()` các resource khác và gom lỗi bằng `addSuppressed`. Điều này tránh bỏ qua cleanup của repository chỉ vì sender gặp lỗi đóng.

Quy tắc tổng quát:

- **Không nuốt mất lỗi vận hành:** ghi nhận cleanup failure để quan sát hoặc trả lỗi ở lớp quản lý lifecycle.
- **Không dừng dọn dẹp quá sớm:** nếu độc lập và an toàn, vẫn thử đóng tài nguyên còn lại.
- **Không đóng hai lần tùy tiện:** có thể thiết kế `close()` idempotent, nhưng không phải mọi thư viện đều bảo đảm idempotence; hãy tôn trọng hợp đồng của từng resource.
- **Phân biệt cleanup thất bại với nghiệp vụ thất bại:** không để lỗi dọn dẹp che mất nguyên nhân ban đầu; `try-with-resources` có thể ghi cleanup error dưới dạng suppressed exception.

### 7.2. Không nên dựa hoàn toàn vào shutdown hook

Java hỗ trợ `Runtime.addShutdownHook(...)` để phối hợp dọn dẹp trong một số tình huống JVM kết thúc có trật tự. Tuy nhiên, shutdown hook không chắc được chạy khi tiến trình bị `kill -9`, máy mất điện hoặc runtime bị dừng đột ngột. Thời điểm và khả năng chạy hook cũng không thay thế quản lý lifecycle của framework/server.

Vì vậy, tài nguyên quan trọng cần kết hợp cleanup đúng, timeout, cơ chế khôi phục sau lỗi và quan sát vận hành. Không nên dựa vào việc “JVM sẽ tự gọi `close()`” khi thực tế không có mã quản lý rõ ràng.

## 8. DI container hỗ trợ lifecycle đến đâu?

Sau khi hiểu vòng đời bằng Java thuần, DI container có thể tự động hóa:

- Khởi tạo graph từ binding/configuration và inject dependency.
- Quản lý scope (ví dụ singleton/application và request) theo tính năng framework.
- Gọi lifecycle callback hoặc destroy hook cho một số bean do container sở hữu.
- Báo lỗi thiếu binding, vòng phụ thuộc hoặc cấu hình không hợp lệ ở thời điểm phù hợp.

Nhưng **không phải mọi container đều có cùng scope và lifecycle semantics**. Đặc biệt:

- Một instance được ứng dụng tự tạo và đưa vào container có thể **không** được container sở hữu để đóng.
- Prototype/transient object có thể không được container theo dõi để gọi destroy callback tự động.
- Request scope có thể chỉ tồn tại khi đang xử lý request của framework.
- Singleton không tự thread-safe; inject một instance request-scoped vào singleton vẫn cần cơ chế proxy/provider hoặc thiết kế thích hợp.
- Các callback khi shutdown không bảo đảm chạy nếu tiến trình bị kết thúc không trật tự.

Vì thế, khi chuyển từ manual DI sang container, vẫn cần giữ **bảng ownership, điều kiện READY và các phép kiểm thử vòng đời**. Việc ứng dụng khởi động không có exception chỉ là một phần của kiểm chứng.

## 9. Checklist quan sát và kiểm thử lifecycle

Có thể dùng checklist sau khi thiết kế hoặc rà soát một module DI:

| Câu hỏi | Cách xác minh gợi ý |
| --- | --- |
| Dependency bắt buộc có được inject đầy đủ trước khi nhận việc? | Test khởi tạo root và kiểm tra fail-fast với cấu hình thiếu. |
| Startup lỗi giữa chừng có dọn những tài nguyên đã tạo? | Fake ném exception ở bước mở resource thứ hai; kiểm tra close event của resource đầu. |
| Application resource có được tạo đúng số lần? | Bộ đếm `open` và kiểm tra identity khi nhiều request dùng chung. |
| Request/task resource có scope độc lập? | Tạo hai request/job, so instance và thứ tự sự kiện. |
| Resource ngắn hạn được dọn khi nghiệp vụ ném lỗi? | Test `try-with-resources`, `finally` hoặc callback của framework. |
| Có request mới nào lọt vào sau khi shutdown bắt đầu? | Test chuyển trạng thái và rejection ở entry point. |
| Công việc đang chạy có hoàn tất/hủy đúng chính sách trước khi pool đóng? | Integration/concurrency test với các task có thể chặn và giải phóng có kiểm soát. |
| Tài nguyên có được đóng đúng thứ tự, đúng số lần? | Fake ghi lại `close`; thử gọi shutdown lặp nếu API yêu cầu. |
| Nếu một `close` thất bại, các cleanup khác có còn được thử? | Fake cố ý ném khi đóng, xác minh những dependency còn lại được giải phóng. |
| Khi JVM/server dừng bất thường, ứng dụng phục hồi thế nào? | Thử nghiệm khôi phục, retry, idempotency và cleanup ngoài tiến trình theo yêu cầu. |

**Ưu tiên quan sát điều kiện có thể kiểm chứng** (sự kiện `open/ready/serve/close`, bộ đếm instance, trạng thái scope) thay vì chỉ assert một phương thức nội bộ đã được gọi. Test cần xác minh hợp đồng vòng đời mà hệ thống thật phải giữ.

## 10. Bài tập: thiết kế vòng đời cho dịch vụ xuất báo cáo

**Bối cảnh:** một ứng dụng HTTP nhận yêu cầu xuất báo cáo, dùng `ReportService`, `ReportRepository`, `ReportSender`, một database pool và background worker. Một số báo cáo được xử lý ngay trong request; một số được đưa vào queue.

Hãy thực hiện:

1. **Vẽ object graph** và đánh dấu những tài nguyên thuộc application, request và task. Giải thích có nên chia sẻ database pool và có nên chia sẻ transaction không.
2. **Định nghĩa các pha khởi động:** đọc cấu hình, tạo pool, tạo sender, lắp `ReportService`, mở cổng nhận request. Chỉ ra thời điểm có thể công bố READY.
3. **Xây dựng rollback khi startup lỗi:** giả sử tạo pool thành công nhưng kết nối sender thất bại. Ai đóng pool, và làm sao giữ lại nguyên nhân lỗi chính?
4. **Xử lý request thất bại:** mô tả nơi mở và đóng unit of work; xác minh `close()` xảy ra cả khi `ReportService` ném exception.
5. **Xử lý shutdown khi đang gửi báo cáo:** đề xuất trình tự ngừng nhận việc, drain/hủy các job còn lại và đóng tài nguyên; nêu dữ liệu nào phải được lưu bền vững để có thể retry.
6. **Viết ít nhất ba test với fake:** kiểm tra thứ tự READY, đóng ngược thứ tự khởi tạo và không phục vụ sau shutdown. Bổ sung một test rollback khi startup thất bại.
7. **Nêu giới hạn của test đơn luồng:** cần bổ sung kiểm thử đồng thời nào để chứng minh request/job đang chạy không bị đóng tài nguyên quá sớm?

**Gợi ý đối chiếu:** pool dùng chung có thể thuộc application scope nếu implementation hỗ trợ; transaction thường gắn với request hoặc task. Entry point chỉ nhận việc sau khi các dependency bắt buộc đã sẵn sàng. Khi khởi động lỗi, composition root dọn những tài nguyên đã tạo thành công. Khi shutdown, cần ngừng nhận việc và xử lý in-flight trước khi đóng pool/client. Fake giúp kiểm tra trình tự vòng đời; kiểm thử tích hợp và đồng thời là cần thiết để xác nhận hành vi thật của server, queue, pool và adapter.

**Điểm cần nhớ:** Thiết kế DI đúng bao gồm **cả đồ thị phụ thuộc lẫn vòng đời của nó**. Composition root phải rõ quyền sở hữu tài nguyên, constructor injection giúp tạo đối tượng với dependency bắt buộc, scope giúp xác định ranh giới chia sẻ. Hãy kiểm chứng bằng sự kiện quan sát được trong ba pha **khởi động, phục vụ và kết thúc**, kể cả đường lỗi; chỉ sau đó mới giao phần tự động hóa wiring và lifecycle cho DI container.
