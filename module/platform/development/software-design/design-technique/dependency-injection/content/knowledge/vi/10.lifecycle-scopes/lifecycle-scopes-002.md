# Dùng chung toàn ứng dụng, theo yêu cầu và tạo mới mỗi lần phân giải

Khi sử dụng **Dependency Injection (DI)**, việc đưa cộng tác viên vào constructor mới giải quyết được câu hỏi **“đối tượng này nhận phụ thuộc từ đâu?”**. Một câu hỏi khác cũng quan trọng là: **“khi nào tạo một instance mới, những ai được dùng chung instance đó, và khi nào kết thúc vòng đời của nó?”**

Ba cách tổ chức phổ biến là:

- **Dùng chung toàn ứng dụng (application-wide):** một instance phục vụ nhiều thành phần hoặc nhiều công việc trong phạm vi một ứng dụng/container cụ thể.
- **Theo yêu cầu (request-scoped):** mỗi request có một instance riêng, nhưng các thành phần tham gia *cùng request* có thể chia sẻ instance đó.
- **Tạo mới mỗi lần phân giải (transient/prototype):** mỗi thao tác yêu cầu nhà cung cấp tạo dependency có thể nhận một instance mới; nhà cung cấp không giữ lại instance để tái sử dụng theo chính sách này.

Ba tên gọi trên thường được nhắc cùng **singleton**, **request scope** và **transient/prototype**. Tuy nhiên, ý nghĩa chính xác về thời điểm tạo, cách lấy instance và trách nhiệm giải phóng còn tùy DI container. Bài này dùng **Java thuần** để thấy rõ các cơ chế, rồi mới liên hệ với container.

## 1. Phân biệt *scope* với *lifetime*

**Scope (phạm vi chia sẻ)** cho biết các nơi yêu cầu một dependency có thể nhận **cùng một instance** trong ranh giới nào. **Lifetime (vòng đời)** mô tả khoảng thời gian instance được tạo, sử dụng và kết thúc.

Hai khía cạnh thường liên quan nhưng không đồng nhất. Một đối tượng có thể được đăng ký dạng dùng chung và chỉ được tạo lười khi sử dụng lần đầu. Một đối tượng transient có thể được tạo mới khi resolve, nhưng vẫn sống rất lâu nếu một đối tượng dùng chung giữ tham chiếu đến nó. Vì vậy:

> **Scope quyết định chính sách cung cấp và chia sẻ instance; vòng đời thực tế còn phụ thuộc nơi giữ tham chiếu và cơ chế giải phóng tài nguyên.**

Ví dụ một ứng dụng đặt hàng có:

- `MetricsCounter` chỉ đếm số thao tác thành công, an toàn khi nhiều luồng dùng chung.
- `RequestWorkspace` giữ thông tin và tài nguyên liên quan tới **một request**.
- `FormatToken` chỉ tạo nhãn tạm cho một lần xử lý nhỏ, không cần chia sẻ.

Object graph dự kiến:

```text
ApplicationRoot
   │
   ├── MetricsCounter ───────────────────┐  dùng chung trong app
   │                                     │
   ├── RequestScope(REQ-1)               │
   │     ├── RequestWorkspace #1 ────────┤  cùng request dùng chung
   │     ├── RequestHandler #1           │
   │     └── resolve FormatToken         │
   │            ├── FormatToken #1       │  mỗi lần resolve là mới
   │            └── FormatToken #2       │
   │
   └── RequestScope(REQ-2)
         ├── RequestWorkspace #2 ────────┘  khác request là khác instance
         ├── RequestHandler #2
         └── resolve FormatToken
                └── FormatToken #3
```

Không có quy tắc “class A luôn phải singleton” hoặc “interface B luôn phải request scope”. Scope là **quyết định lắp ghép** dựa trên trách nhiệm, trạng thái và an toàn đồng thời của implementation.

## 2. So sánh ba chính sách cung cấp instance

| Tiêu chí | Dùng chung toàn ứng dụng | Theo yêu cầu | Mới mỗi lần phân giải |
|---|---|---|---|
| Phạm vi dùng chung | Các consumer trong một application/container | Các consumer trong cùng request/scope | Thông thường không chia sẻ tự động giữa hai lần resolve |
| Thời điểm tạo | Khi startup hoặc lúc sử dụng đầu tiên, tùy cấu hình | Khi bắt đầu request hoặc khi request cần lần đầu | Khi gọi factory/provider/resolve |
| Ví dụ hợp lý | Client/pool dùng chung được thiết kế thread-safe, bộ đếm an toàn luồng, policy bất biến | Thông tin request, unit of work theo request, bối cảnh phân quyền của request | Formatter có trạng thái cục bộ, đối tượng xử lý ngắn hạn |
| Vấn đề cần tránh | Giữ dữ liệu request hoặc mutable state không an toàn | Để instance thoát khỏi ranh giới request | Tưởng “resolve mỗi lần” là “gọi method mỗi lần”; không đóng resource đã tạo |
| Kết thúc vòng đời | Khi chủ sở hữu ứng dụng/container đóng | Khi request/scope đóng | Do nơi nhận hoặc scope/container nắm quyền sở hữu, tùy hợp đồng |

Một số hệ thống còn có **transaction scope**, **session scope**, **thread scope**, **job scope** hoặc scope do người dùng định nghĩa. Request scope cũng không nhất thiết đồng nghĩa HTTP: một message, job hoặc lệnh CLI có thể là *đơn vị công việc* mà ứng dụng chọn để mở và đóng scope.

### “Toàn ứng dụng” có nghĩa chính xác đến đâu?

Trong DI container, singleton thường nghĩa là **một instance cho mỗi registration trong một container/context**, không phải một đối tượng duy nhất trên toàn máy, toàn JVM hoặc toàn cụm dịch vụ. Hai ứng dụng được chạy riêng, hai container hoặc hai registration độc lập có thể có các instance khác nhau.

Trong DI thủ công, chúng ta tạo một instance ở composition root và truyền chính instance đó cho các consumer cần chia sẻ. Không nhất thiết phải viết **Singleton pattern** với `private static instance`. Một biến được tạo một lần và inject nhất quán đã đủ để thực hiện chính sách dùng chung.

## 3. Dùng chung toàn ứng dụng: lợi ích và điều kiện

Một instance dùng chung có thể giúp tiết kiệm chi phí khởi tạo và giữ trạng thái chung có chủ đích. Ví dụ pool kết nối tới database thường là tài nguyên được tạo ở ranh giới ứng dụng, còn từng connection từ pool có vòng đời riêng.

```java
MetricsCounter shared = new MetricsCounter();

OrderService orderService = new OrderService(shared);
RefundService refundService = new RefundService(shared);
// Cả hai nhận đúng một instance MetricsCounter.
```

Đây là mã minh họa cách lắp ghép khi các class đã được khai báo. Điều kiện quan trọng là **instance được chia sẻ phải phù hợp với concurrency và ownership của ứng dụng**.

Một ví dụ không an toàn:

```java
final class UnsafeCounter {
    private int count;

    void increment() {
        count++; // Không phải thao tác nguyên tử.
    }

    int value() {
        return count;
    }
}
```

Nếu nhiều thread gọi `increment()`, giá trị có thể sai vì `count++` là chuỗi đọc, tăng và ghi. Chỉ đánh dấu dependency là singleton không tự động bảo vệ trạng thái mutable. Có thể dùng cơ chế đồng bộ phù hợp hoặc một kiểu dữ liệu hỗ trợ đồng thời:

```java
import java.util.concurrent.atomic.AtomicInteger;

final class MetricsCounter {
    private final AtomicInteger operations = new AtomicInteger();

    void record() {
        operations.incrementAndGet();
    }

    int total() {
        return operations.get();
    }
}
```

`AtomicInteger` làm thao tác tăng và đọc ở ví dụ này an toàn theo hợp đồng atomic; điều đó **không có nghĩa mọi logic nhiều bước trên cùng object sẽ tự an toàn**. Một dependency dùng chung còn phải tránh giữ trạng thái riêng của request như `currentUserId` hoặc `currentTransaction` trong field.

## 4. Theo yêu cầu: chia sẻ bên trong, cô lập giữa các request

Giả sử `CheckoutHandler` và `PaymentService` đều cần bối cảnh làm việc của request đang xử lý. Ta muốn:

- Trong request `REQ-1`, các thành phần liên quan dùng cùng `RequestWorkspace #1`.
- Sang request `REQ-2`, chúng dùng một `RequestWorkspace #2` khác.
- Khi `REQ-1` kết thúc, các tài nguyên gắn với `RequestWorkspace #1` được đóng hoặc giải phóng.

Đây là ý tưởng **scope theo yêu cầu**, không đồng nghĩa “mỗi lời gọi method tạo một instance”.

```text
REQ-1
  CheckoutHandler ──┐
                     ├── RequestWorkspace #1
  PaymentService ───┘

REQ-2
  CheckoutHandler ──┐
                     ├── RequestWorkspace #2
  PaymentService ───┘
```

Điểm tạo scope nên nằm ở ranh giới request/job, ví dụ HTTP middleware, message consumer hoặc phần điều phối lệnh. Composition root ứng dụng có thể dùng một `RequestScopeFactory` để tạo scope riêng cho từng đơn vị công việc.

Nếu một request có ba lần gọi tới repository, không nhất thiết cần ba instance repository nếu repository được thiết kế chia sẻ trong request. Ngược lại, nếu mỗi thao tác cần transaction độc lập, scope transaction có thể ngắn hơn cả request. **Không chọn scope chỉ theo tên class.**

### Request scope không thay thế dữ liệu đầu vào mỗi lời gọi

`orderId`, `quantity` hay `paymentMethod` do caller cung cấp vẫn thường là tham số phương thức hoặc DTO. Chỉ vì dữ liệu xuất hiện trong một request không có nghĩa phải đăng ký từng giá trị vào container dưới dạng request-scoped bean.

Một bối cảnh có thể bao gồm thông tin chung thật sự cần dùng xuyên suốt request (ví dụ ID truy vết hoặc metadata được xác thực), nhưng nó cần hợp đồng rõ ràng; không nên biến context thành “túi dữ liệu toàn năng” để mọi service tìm tùy ý.

## 5. Mới mỗi lần phân giải: khác với “mới mỗi lần sử dụng”

Với **transient**, từ khóa cần chú ý là **phân giải (resolve)** — hành động lấy một dependency từ factory/provider/container. Nếu gọi factory hai lần, ta thường nhận hai instance khác nhau:

```java
Supplier<FormatToken> tokens = FormatToken::new;

FormatToken first = tokens.get();
FormatToken second = tokens.get();

System.out.println(first == second); // false
```

Đoạn phác họa giả định đã import `java.util.function.Supplier` và đã định nghĩa `FormatToken`.

Nhưng nếu một instance transient được inject vào constructor của một service dùng chung:

```java
final class ReportService {
    private final FormatToken token;

    ReportService(FormatToken token) {
        this.token = token;
    }

    String createReport() {
        return token.decorate("report");
    }
}
```

`token` được cung cấp **một lần khi `ReportService` được tạo**. Mỗi lần gọi `createReport()` sau đó dùng lại **cùng instance được giữ trong field**, dù registration nguồn là transient. Muốn tạo token mới mỗi lượt xử lý, có thể inject **khả năng tạo/lấy mới**:

```java
final class ReportService {
    private final Supplier<FormatToken> tokens;

    ReportService(Supplier<FormatToken> tokens) {
        this.tokens = Objects.requireNonNull(tokens);
    }

    String createReport() {
        return tokens.get().decorate("report");
    }
}
```

Đây là **factory/provider injection**: collaborator được inject là một nhà cung cấp, còn thời điểm tạo `FormatToken` được đặt tại ranh giới xử lý. Java thuần làm điều đó bằng `Supplier`; DI container có thể có `Provider<T>`, object factory hoặc scope proxy tùy hệ sinh thái. Không phải mọi API tên `get()` đều có cùng ngữ nghĩa, nên cần đọc hợp đồng framework.

## 6. Ví dụ Java thuần hoàn chỉnh: ba phạm vi trong một ứng dụng

Ta mô phỏng một ứng dụng xử lý yêu cầu với **ba cơ chế cung cấp khác nhau**:

1. `OperationCounter` dùng chung trong một `ApplicationRoot`.
2. `RequestWorkspace` và `RequestHandler` được tạo **một lần cho một `RequestScope`**.
3. `FormatToken` được tạo mới mỗi lần gọi `resolveToken()`.

Mã còn thể hiện **constructor injection**, **composition root**, provider truyền qua method reference và đóng scope rõ ràng. Lưu toàn bộ thành `ScopeDemo.java`, chạy với Java 17 trở lên:

```java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public final class ScopeDemo {

    // Dùng chung trong phạm vi một application root.
    static final class OperationCounter implements AutoCloseable {
        private final AtomicInteger total = new AtomicInteger();
        private final AtomicBoolean closed = new AtomicBoolean();

        void record() {
            if (closed.get()) {
                throw new IllegalStateException("Counter is closed");
            }
            total.incrementAndGet();
        }

        int total() {
            return total.get();
        }

        @Override
        public void close() {
            closed.set(true);
        }
    }

    // Tạo mới theo mỗi lần resolve.
    static final class FormatToken {
        private static final AtomicInteger sequence = new AtomicInteger();
        private final int id = sequence.incrementAndGet();

        int id() {
            return id;
        }

        String decorate(String text) {
            return text + "#" + id;
        }
    }

    // Được sở hữu và dùng chung trong đúng một request.
    static final class RequestWorkspace implements AutoCloseable {
        private static final AtomicInteger sequence = new AtomicInteger();

        private final int id = sequence.incrementAndGet();
        private final String requestId;
        private final OperationCounter counter;
        private final AtomicBoolean closed = new AtomicBoolean();

        RequestWorkspace(
                String requestId, OperationCounter counter) {
            if (requestId == null || requestId.isBlank()) {
                throw new IllegalArgumentException(
                        "requestId must not be blank");
            }
            this.requestId = requestId;
            this.counter = Objects.requireNonNull(counter);
        }

        int id() {
            return id;
        }

        void process(String operation, FormatToken token) {
            if (closed.get()) {
                throw new IllegalStateException(
                        "Request workspace is closed");
            }
            Objects.requireNonNull(operation, "operation");
            Objects.requireNonNull(token, "token");

            String label = token.decorate(operation);
            // Ví dụ chỉ ghi nhận thao tác, không dùng network thật.
            counter.record();
        }

        @Override
        public void close() {
            closed.set(true);
        }
    }

    // Handler nhận request dependency và nhà cung cấp transient.
    static final class RequestHandler {
        private final RequestWorkspace workspace;
        private final Supplier<FormatToken> tokens;

        RequestHandler(
                RequestWorkspace workspace,
                Supplier<FormatToken> tokens) {
            this.workspace = Objects.requireNonNull(workspace);
            this.tokens = Objects.requireNonNull(tokens);
        }

        void handle(String operation) {
            workspace.process(operation, tokens.get());
        }
    }

    // Phạm vi request được tạo và đóng ở ranh giới công việc.
    static final class RequestScope implements AutoCloseable {
        private final RequestWorkspace workspace;
        private final RequestHandler handler;
        private final AtomicBoolean closed = new AtomicBoolean();

        RequestScope(OperationCounter shared, String requestId) {
            this.workspace = new RequestWorkspace(requestId, shared);
            this.handler = new RequestHandler(
                    workspace, this::resolveToken);
        }

        RequestWorkspace workspace() {
            ensureOpen();
            return workspace;
        }

        RequestHandler handler() {
            ensureOpen();
            return handler;
        }

        FormatToken resolveToken() {
            ensureOpen();
            return new FormatToken();
        }

        private void ensureOpen() {
            if (closed.get()) {
                throw new IllegalStateException("Request is closed");
            }
        }

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                workspace.close();
            }
        }
    }

    // Composition root: quyết định phạm vi và quyền sở hữu.
    static final class ApplicationRoot implements AutoCloseable {
        private final OperationCounter counter = new OperationCounter();
        private final AtomicBoolean closed = new AtomicBoolean();

        OperationCounter counter() {
            ensureOpen();
            return counter;
        }

        RequestScope beginRequest(String requestId) {
            ensureOpen();
            return new RequestScope(counter, requestId);
        }

        private void ensureOpen() {
            if (closed.get()) {
                throw new IllegalStateException(
                        "Application is closed");
            }
        }

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                counter.close();
            }
        }
    }

    public static void main(String[] args) {
        try (ApplicationRoot app = new ApplicationRoot()) {
            System.out.println(
                "Shared counter: " + (app.counter() == app.counter()));

            int firstWorkspaceId;

            try (RequestScope request = app.beginRequest("REQ-1")) {
                RequestWorkspace workspace = request.workspace();
                firstWorkspaceId = workspace.id();

                System.out.println(
                    "Same workspace in REQ-1: "
                        + (workspace == request.workspace()));

                FormatToken first = request.resolveToken();
                FormatToken second = request.resolveToken();
                System.out.println(
                    "New token per resolution: "
                        + (first != second));

                request.handler().handle("create");
                request.handler().handle("confirm");
            }

            try (RequestScope request = app.beginRequest("REQ-2")) {
                System.out.println(
                    "Different workspace across requests: "
                        + (firstWorkspaceId != request.workspace().id()));
                request.handler().handle("approve");
            }

            System.out.println(
                "Operations recorded: " + app.counter().total());
        }
    }
}
```

Chạy:

```bash
javac ScopeDemo.java
java ScopeDemo
```

Kết quả dự kiến:

```text
Shared counter: true
Same workspace in REQ-1: true
New token per resolution: true
Different workspace across requests: true
Operations recorded: 3
```

### Đọc ví dụ theo thứ tự tạo đối tượng

`ApplicationRoot` tạo đúng một `OperationCounter` và giữ nó suốt vòng đời ứng dụng. Cả hai lần `beginRequest(...)` đều nhận cùng đối tượng đếm.

Mỗi `beginRequest(...)` tạo **một `RequestScope` mới**. Trong constructor của scope, `RequestWorkspace` và `RequestHandler` được tạo một lần. Hai lần gọi `request.workspace()` trả về cùng một tham chiếu, còn hai scope khác nhau có workspace khác nhau.

Mỗi lần gọi `request.resolveToken()` thực hiện `new FormatToken()`. `RequestHandler` nhận một `Supplier<FormatToken>` và gọi `get()` khi cần xử lý. Vì vậy, dù handler được dùng lại trong suốt request, từng thao tác có token mới.

`RequestScope` được đóng khi rời `try-with-resources`. `RequestWorkspace.process(...)` từ chối thao tác sau khi scope kết thúc. `ApplicationRoot` đóng counter khi ứng dụng kết thúc.

### Điều gì được mô phỏng và điều gì chưa?

Mã mô phỏng ranh giới request bằng phương thức `beginRequest(...)`, **không mở HTTP server** và không tạo thread. Nó giúp quan sát semantics bằng Java thuần, nhưng chưa bao gồm xử lý đồng thời các request, cancellation, timeout hoặc graceful shutdown.

`OperationCounter` dùng `AtomicInteger` để đếm, nhưng điều kiện “đã đóng” và lệnh tăng không tạo thành một giao dịch nguyên tử duy nhất. Ứng dụng có truy cập đồng thời cần quy định rõ ranh giới dừng nhận việc, chờ các request đang xử lý và đóng root cuối cùng. Không nên coi `AtomicBoolean` tự giải quyết toàn bộ lifecycle concurrency.

Trong `RequestWorkspace.process`, biến `label` chỉ cho thấy một token được dùng để biến đổi nội dung. Ứng dụng thực tế có thể đưa label đó vào kết quả hoặc log; ví dụ này chỉ quan tâm đến đếm số thao tác và danh tính instance.

## 7. Kiểm thử phạm vi và việc đóng request bằng Java thuần

Có thể viết một chương trình kiểm thử riêng để kiểm tra **identity, tính cô lập và lifetime** mà không dùng DI container. Lưu mã dưới đây thành `ScopeDemoCheck.java`, cùng thư mục với `ScopeDemo.java`:

```java
public final class ScopeDemoCheck {
    public static void main(String[] args) {
        ScopeDemo.RequestWorkspace closedWorkspace;

        try (ScopeDemo.ApplicationRoot app =
                     new ScopeDemo.ApplicationRoot()) {

            ScopeDemo.OperationCounter shared = app.counter();
            if (shared != app.counter()) {
                throw new AssertionError(
                        "Application dependency was not shared");
            }

            try (ScopeDemo.RequestScope first =
                         app.beginRequest("REQ-1")) {
                closedWorkspace = first.workspace();

                if (first.workspace() != closedWorkspace
                        || first.handler() != first.handler()) {
                    throw new AssertionError(
                        "Request dependencies were not shared");
                }

                if (first.resolveToken() == first.resolveToken()) {
                    throw new AssertionError(
                        "Transient dependency was reused");
                }

                first.handler().handle("create");
                first.handler().handle("confirm");
            }

            // Đã đóng request: một reference cũ không được tiếp tục dùng.
            boolean rejected = false;
            try {
                closedWorkspace.process(
                    "late", new ScopeDemo.FormatToken());
            } catch (IllegalStateException expected) {
                rejected = true;
            }
            if (!rejected) {
                throw new AssertionError(
                    "Closed workspace still accepted work");
            }

            try (ScopeDemo.RequestScope second =
                         app.beginRequest("REQ-2")) {
                if (second.workspace() == closedWorkspace) {
                    throw new AssertionError(
                        "Workspace leaked across requests");
                }
                second.handler().handle("approve");
            }

            if (shared.total() != 3) {
                throw new AssertionError(
                    "Expected three operations, got "
                        + shared.total());
            }
        }

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac ScopeDemo.java ScopeDemoCheck.java
java ScopeDemoCheck
```

Kết quả dự kiến: `PASS`.

Chương trình kiểm tra rằng application dependency được dùng chung; dependency theo request là cùng một instance trong một scope và khác giữa hai scope; transient được tạo mới ở các lần resolution; workspace đã đóng không tiếp tục nhận công việc. Đó là kiểm tra **chính sách lắp ghép**, còn tính đúng đắn nghiệp vụ của từng collaborator nên được kiểm thử riêng.

## 8. Vì sao scope ngắn không nên bị giữ trong scope dài?

Một lỗi nguy hiểm là **captive dependency**: đối tượng sống lâu giữ tham chiếu trực tiếp tới dependency được thiết kế chỉ hợp lệ trong vòng đời ngắn hơn.

```text
Sai về vòng đời:

ApplicationScope (sống lâu)
       │
       ▼
Singleton OrderProcessor
       │ giữ trực tiếp
       ▼
RequestWorkspace từ REQ-1 (đã đóng)
       │
       └── REQ-2 vẫn vô tình dùng REQ-1
```

Ví dụ phản thiết kế:

```java
final class OrderProcessor {
    private final RequestWorkspace workspace;

    // Nếu OrderProcessor được tạo một lần ở application scope,
    // workspace từ request đầu có thể bị giữ lại quá lâu.
    OrderProcessor(RequestWorkspace workspace) {
        this.workspace = workspace;
    }

    void processOrder(String orderId) {
        workspace.process(orderId, new FormatToken());
    }
}
```

*Đoạn trên minh họa khi các kiểu `RequestWorkspace`, `FormatToken` tồn tại trong cùng ngữ cảnh.* Vấn đề không nằm ở constructor injection tự thân; vấn đề là **composition root chọn vòng đời không tương thích**.

Có ba hướng giải quyết thường gặp:

1. Tạo `OrderProcessor` **trong cùng request scope** với `RequestWorkspace` nếu chúng thực sự gắn với request.
2. Giữ `OrderProcessor` ở application scope, nhưng **truyền dữ liệu/ngữ cảnh cần dùng theo lời gọi** nếu nó không cần giữ request dependency.
3. Inject **factory hoặc cơ chế truy cập scope hiện hành có hợp đồng hẹp** thay vì giữ trực tiếp instance ngắn hạn. Khi resolve tài nguyên, phải bảo đảm có scope hợp lệ và giải phóng đúng chủ sở hữu.

Một số DI container cung cấp scope proxy hoặc kiểm tra mismatch khi xây graph. Một số container chỉ kiểm tra ở runtime, và việc inject transient vào singleton có thể hoàn toàn được phép. **Đừng suy ra rằng container sẽ tự phát hiện mọi captive dependency.** Hãy xem contract và validation cụ thể của framework.

### Transient cũng có thể bị giữ lâu

Nếu một `ReportService` dùng chung nhận một `FormatToken` transient **trực tiếp qua constructor**, token đó có thể sống bằng `ReportService` vì service giữ tham chiếu. Điều này không vi phạm quy tắc “new at resolution”: thời điểm tạo `ReportService` đã có một lần resolution, sau đó không có lần resolution nào mới của token.

Nếu token có trạng thái mutable riêng cho từng lần xử lý, việc giữ lâu sẽ tạo lỗi đồng thời hoặc nhiễm trạng thái. Khi thật sự cần một instance cho mỗi thao tác, hãy inject factory/provider và gọi tại đúng thời điểm.

## 9. Vòng đời, quyền sở hữu và tài nguyên cần đóng

Scope được dùng để **chia sẻ** và **quản lý lifetime**, nhưng lifetime không đơn giản là “để garbage collector thu hồi”.

- Đối tượng chỉ chứa dữ liệu bất biến thường không cần bước `close()`; khi hết tham chiếu, JVM có thể thu hồi bộ nhớ.
- Connection, file handle, socket, transaction, scheduler hoặc thread pool thường có **tài nguyên ngoài heap** và cần cơ chế giải phóng rõ ràng.
- Nếu factory tạo tài nguyên để caller sở hữu, caller hoặc request scope phải đóng nó khi xong.
- Nếu container sở hữu tài nguyên dùng chung, container hoặc application lifecycle manager thường đóng nó lúc shutdown.

Sơ đồ ownership:

```text
ApplicationRoot
   ├── tạo ConnectionPool ────────────────┐
   ├── tạo RequestScope REQ-1             │
   │     └── mượn Connection từ pool      │
   │            └── đóng/trả về pool      │
   ├── tạo RequestScope REQ-2             │
   │     └── mượn Connection từ pool      │
   │            └── đóng/trả về pool      │
   └── đóng ConnectionPool <──────────────┘
```

Trong thực tế, `Connection.close()` có thể có ngữ nghĩa **trả connection về pool** thay vì đóng kết nối vật lý; điều này phụ thuộc thư viện. Dù vậy, ranh giới ownership vẫn là yêu cầu cốt lõi.

Một transient mở tài nguyên mới sau mỗi resolve có thể gây rò rỉ nếu consumer quên đóng. Một số container theo dõi disposable transient và giữ nó để đóng cuối scope; cách này có thể vô tình giữ nhiều đối tượng lâu hơn mong muốn. Do đó **không dùng transient như một giải pháp mặc định cho mọi tài nguyên ngắn hạn**. Cần biết ai gọi `close()` và thời điểm đóng có khớp với mức tiêu thụ tài nguyên hay không.

### Đóng theo thứ tự phụ thuộc

Giả sử root sở hữu `ClientPool` và một `Worker` sử dụng pool. Thông thường cần dừng worker trước khi đóng pool:

```text
Khởi tạo: ClientPool → Worker
Shutdown: Worker → ClientPool
```

Nếu không, worker có thể đang xử lý job và sử dụng pool vừa bị đóng. Khi có nhiều request đồng thời, quy trình dừng nên chặn công việc mới, chờ công việc đang xử lý hoàn thành theo chính sách, rồi đóng các tài nguyên chung.

## 10. Scope trong ứng dụng bất đồng bộ và nhiều luồng

Ranh giới request trong máy chủ web không nhất thiết trùng ranh giới **một thread**. Một yêu cầu có thể bắt đầu ở thread A, tiếp tục trên thread B sau thao tác bất đồng bộ, rồi hoàn thành ở thread C.

Vì vậy, **thread-local không tự động đồng nghĩa request-local**:

- Thread pool tái sử dụng thread cho nhiều request.
- Request có thể di chuyển giữa các thread do executor, callback hoặc reactive pipeline.
- Nếu quên xóa `ThreadLocal`, dữ liệu request trước có thể lọt sang công việc sau.
- Với cơ chế context propagation, phải hiểu cách capture/restore, thời điểm kết thúc scope và cách xử lý cancellation.

Trong Java thuần, một cách đơn giản để tránh phụ thuộc vào thread hiện hành là **truyền request context hoặc collaborator theo ranh giới lời gọi**. Nếu framework quản lý request scope, nên dùng cơ chế propagation chính thức của framework và tránh giữ reference sau khi request kết thúc.

Ví dụ API tường minh:

```java
record RequestData(String requestId, String userId) {}

final class AuditService {
    void writeAudit(RequestData request, String action) {
        // Sử dụng dữ liệu của lời gọi, không tìm một "current request"
        // bất kỳ từ thread-local toàn cục.
    }
}
```

Đoạn này chỉ minh họa hướng thiết kế. Nếu `AuditService` phải dùng connection hoặc transaction, dependency đó cần được cung cấp và quản lý theo scope thích hợp.

## 11. Khi dùng DI container: khác biệt về cách phân giải

Các container thường cung cấp cơ chế đăng ký lifetime tương tự:

| Khái niệm | Ý định chung | Điều cần xác nhận trong framework |
|---|---|---|
| Singleton/application-scoped | Chia sẻ một instance trong ranh giới container | Phạm vi của context; tạo eager hay lazy; dispose khi nào |
| Request/scoped | Một instance cho scope hiện hành | Cách mở/đóng scope; request async; phụ thuộc được phép inject vào singleton không |
| Transient/prototype | Tạo mới ở mỗi lần container được yêu cầu cung cấp | Khi nào xảy ra resolution; ai sở hữu và dispose instance được tạo |

**Ví dụ minh họa ngữ nghĩa, không phải cấu hình bắt buộc của một framework cụ thể:**

```text
register(OperationCounter, application)
register(RequestWorkspace, request)
register(FormatToken, transient)

app = buildContainer()
request1 = app.openScope()
a = request1.resolve(RequestWorkspace) // instance X
b = request1.resolve(RequestWorkspace) // vẫn X

t1 = request1.resolve(FormatToken)      // instance Y
t2 = request1.resolve(FormatToken)      // instance Z

request1.close()
app.close()
```

Với Spring, một bean singleton thường có scope trên mỗi application context; request scope cần một request context đang hoạt động. Prototype tạo instance khi bean được yêu cầu tạo/phân giải; inject prototype trực tiếp vào singleton không tự khiến nó đổi instance ở mỗi method call. Các framework khác có mô hình và thuật ngữ riêng, nên tránh bê nguyên cấu hình hoặc suy đoán semantics giữa các nền tảng.

Dù dùng framework nào, **composition root** vẫn chịu trách nhiệm chọn implementation và wiring của ứng dụng. DI container chỉ tự động hóa một phần việc lắp ghép; nó không tự xác định dependency nào an toàn khi dùng chung, vòng đời request thực tế kéo dài bao lâu, hoặc một tài nguyên do ai sở hữu.

## 12. Cách lựa chọn scope theo trách nhiệm

Khi thiết kế một collaborator, hãy hỏi theo thứ tự:

1. **Nó giữ trạng thái mutable nào?** Nếu chỉ giữ cấu hình bất biến và được thiết kế thread-safe, chia sẻ rộng có thể hợp lý. Nếu giữ dữ liệu request, scope rộng có thể không an toàn.
2. **Những ai phải quan sát cùng trạng thái?** Nếu nhiều thành phần của cùng request phải thấy một đơn vị công việc, hãy chia sẻ trong request thay vì tạo từng instance độc lập.
3. **Thời điểm tạo có tốn kém?** Kết nối mạng, pool và cache có thể cần dùng chung hoặc factory; tạo mới liên tục dễ gây quá tải.
4. **Phải đóng tài nguyên lúc nào?** Đây là quyết định ownership quan trọng hơn việc đặt nhãn singleton/transient.
5. **Có cần một instance mới cho *mỗi resolve* hay *mỗi thao tác*?** Nếu mỗi thao tác, provider/factory phải được gọi trong thao tác; chỉ đăng ký transient chưa đủ.
6. **Có cần dùng trong async hoặc đa luồng không?** Nếu có, xác định propagation của scope, tính an toàn luồng và quy tắc shutdown.

Một số lựa chọn thực hành:

| Thành phần | Scope thường cân nhắc | Lý do |
|---|---|---|
| Chính sách giá bất biến | Dùng chung | Không giữ dữ liệu từng request; có thể chia sẻ an toàn |
| HTTP client có cơ chế thread-safe và pooling | Dùng chung theo hợp đồng thư viện | Giảm chi phí tạo và quản lý tài nguyên |
| Request trace/tenant context | Theo request hoặc truyền tường minh | Không rò dữ liệu giữa các yêu cầu |
| Unit of work gắn một transaction | Theo transaction/đơn vị công việc | Cần một biên commit/rollback nhất quán |
| Bộ tạo nhãn mang state riêng cho thao tác | Mới khi cần | Không chia sẻ state của một thao tác |
| DTO chứa `orderId`, `quantity` | Dữ liệu per-call, không nhất thiết là dependency của container | Caller chủ động truyền tới use case |

Những gợi ý trên **không phải luật phổ quát**. Ví dụ HTTP client phải được xem xét theo tài liệu thread-safety của thư viện; một “policy” có cache mutable cần bảo vệ đồng thời; còn unit of work có thể có phạm vi khác HTTP request.

## 13. Các lỗi thường gặp

| Biểu hiện | Hệ quả | Cách xử lý |
|---|---|---|
| Singleton giữ `currentRequest` ở field | Dữ liệu request trộn lẫn khi có nhiều lời gọi | Truyền DTO theo method hoặc tạo collaborator theo request |
| Singleton giữ trực tiếp session/connection ngắn hạn | Dùng tài nguyên đã đóng hoặc sai transaction | Tách scope; inject factory/provider phù hợp |
| Dùng transient nhưng giữ instance trong singleton suốt đời | Vẫn dùng chung một object dù tưởng mỗi lần mới | Resolve bằng provider tại thời điểm cần |
| Tạo client/pool mới mỗi request không kiểm soát | Tăng chi phí khởi tạo và số kết nối | Dùng chung component thread-safe, phân biệt pool với connection |
| Request scope dựa vào thread-local mà không cleanup | Nhiễm ngữ cảnh giữa các request hoặc async task | Ràng buộc scope với request và propagate/close đúng cách |
| Không đóng scope khi request thất bại | Rò connection, transaction, buffer | `try-with-resources`/`finally` và ownership rõ |
| Đóng dependency dùng chung từ một request | Các request khác mất tài nguyên | Chỉ owner của application scope đóng dependency dùng chung |
| Đăng ký hết mọi thứ dạng singleton để “nhanh” | Có thể gây race và giữ state nhạy cảm | Chọn scope theo state, thread-safety và vòng đời |
| Đăng ký hết mọi thứ dạng transient để “an toàn” | Tạo thừa đối tượng, chi phí cao, khó dispose | Chỉ tạo mới theo nhu cầu tách state thực sự |
| Cho rằng container xác minh toàn bộ scope | Lỗi chỉ lộ ở runtime hoặc khi tải cao | Kiểm thử scope và đọc validation của framework |

## 14. Bài tập thực hành

Dùng `ScopeDemo.java` để thực hiện các nhiệm vụ sau.

**Bài tập 1 — Thấy rõ ý nghĩa “per resolution”.** Trong `REQ-1`, gọi `resolveToken()` ba lần và so sánh tham chiếu bằng `==`. Sau đó tạo một `FormatToken` duy nhất và truyền nó vào ba lần `workspace.process(...)`. Giải thích vì sao ba lần gọi method thứ hai **vẫn dùng chung token**, dù token lúc tạo được xem là transient.

**Bài tập 2 — Kiểm tra request isolation.** Tạo hai `RequestScope` nối tiếp và ghi lại `workspace.id()` của từng request. Vì sao hai ID khác nhau, còn `app.counter()` vẫn là cùng instance?

**Bài tập 3 — Thử lifetime sau khi đóng.** Lưu tham chiếu `RequestWorkspace`, đóng scope rồi gọi `process(...)`. Chương trình phải ném `IllegalStateException`. Hãy giải thích vì sao API không được giữ workspace để dùng ở request kế tiếp.

**Bài tập 4 — Tìm captive dependency.** Giả sử `ReportService` là application-scoped, còn `CurrentUserContext` là request-scoped. Phân tích ưu/nhược điểm của (a) inject trực tiếp instance; (b) tạo `ReportService` theo request; (c) truyền `CurrentUserContext` theo method; (d) inject một provider có thể resolve trong request scope hợp lệ.

**Bài tập 5 — Quản lý tài nguyên thật.** Thay `RequestWorkspace` bằng một tài nguyên giả có bộ đếm `open` và `close`. Viết test kiểm tra mỗi request mở và đóng đúng một lần kể cả khi handler ném exception. Sau đó thêm một tài nguyên chia sẻ cấp ứng dụng và đảm bảo nó chỉ đóng khi application root đóng.

### Tự kiểm tra

1. “Singleton” trong container có bắt buộc là một object duy nhất trên mọi process không?
2. “Request-scoped” có nghĩa mỗi lời gọi method nhận một instance mới không?
3. Nếu một transient được inject trực tiếp vào constructor singleton, có chắc mỗi lần gọi method singleton là một transient mới không?
4. Nếu một resource cần `close()`, ai phải đóng nó khi scope kết thúc?
5. Tại sao thread pool và async callback khiến việc dựa vào thread-local cho request context trở nên rủi ro?
6. Một service bất biến có thể chia sẻ rộng trong khi dữ liệu từng request vẫn truyền qua method không?

**Gợi ý trả lời:** (1) Không, chỉ trong ranh giới container/registration tương ứng; (2) không, trong cùng scope thường chia sẻ một instance; (3) không, phải resolve lại qua provider khi cần; (4) chủ sở hữu theo hợp đồng; (5) thread được tái sử dụng và request có thể đổi thread; (6) có, đó là một cách tách collaborator ổn định khỏi per-call data.

## Ghi nhớ

- **Dùng chung toàn ứng dụng:** cùng một instance được nhiều consumer sử dụng trong ranh giới ứng dụng/container; phải xét thread-safety, trạng thái và shutdown.
- **Theo yêu cầu:** cùng một request có thể chia sẻ dependency, còn request khác nhận instance khác; phải cô lập dữ liệu và đóng scope đúng thời điểm.
- **Tạo mới mỗi lần phân giải:** mỗi lần gọi factory/provider/resolve có thể tạo object mới; **không mặc định** có object mới mỗi lần method chạy.
- **Scope không thay thế ownership:** resource ngắn hạn phải được đóng, resource dùng chung không được một request tùy tiện đóng.
- **Constructor injection và composition root** giúp lắp graph có chủ đích; Java thuần đủ để thử nghiệm identity, vòng đời, captive dependency và cách cung cấp instance trước khi sử dụng DI container.
