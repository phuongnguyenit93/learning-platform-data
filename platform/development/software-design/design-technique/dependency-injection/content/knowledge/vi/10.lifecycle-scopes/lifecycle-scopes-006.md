# Đối tượng sống lâu giữ tham chiếu đến trạng thái của yêu cầu ngắn hạn

## 1. Một lỗi scope dễ bị che khuất bởi constructor injection

**Dependency Injection (DI)** giúp lớp nghiệp vụ nhận phụ thuộc từ bên ngoài thay vì tự tạo và lắp ghép chúng. Nhưng một object graph dùng constructor injection đúng cú pháp vẫn có thể sai về **vòng đời (lifecycle)** và **phạm vi (scope)**.

Giả sử ứng dụng có hai loại đối tượng:

- `OrderService` được tạo một lần khi ứng dụng khởi động và dùng chung cho nhiều request.
- `RequestContext` được tạo riêng cho từng request, mang danh tính đã xác thực, mã truy vết và những thông tin chỉ có hiệu lực khi request đó đang chạy.

Nếu composition root truyền `RequestContext` của request đầu tiên vào constructor của `OrderService` dùng chung, service có thể giữ nó trong field suốt vòng đời ứng dụng. Đây là **captive dependency** (phụ thuộc bị giữ lại quá vòng đời), một dạng **scope mismatch**: đối tượng sống lâu giữ tham chiếu trực tiếp đến trạng thái đáng lẽ chỉ sống ngắn hạn.

~~~java
// Mã minh họa lỗi thiết kế, sử dụng các kiểu định nghĩa trong bài.
final class WrongOrderService {
    private final OrderStore store;
    private final RequestContext capturedRequest; // Sai scope!

    WrongOrderService(OrderStore store, RequestContext request) {
        this.store = store;
        this.capturedRequest = request;
    }

    void place(String orderId) {
        store.save(capturedRequest.actorId(), orderId);
    }
}
~~~

`WrongOrderService` thực sự **có dùng DI**: nó nhận phụ thuộc qua constructor. Vấn đề là tham chiếu `capturedRequest` được lưu lâu hơn phạm vi mà nó có ý nghĩa. Đổi kiểu constructor sang interface hoặc dùng DI container sẽ không tự khắc phục lỗi này.

Hệ quả có thể gồm:

1. **Dữ liệu sai người dùng hoặc sai tenant:** nếu context không có cơ chế báo hết hạn, request B có thể sử dụng danh tính còn lưu từ request A.
2. **Sử dụng đối tượng đã hết hiệu lực:** khi request A kết thúc, context/session/connection của A có thể đã bị đóng; service vẫn tham chiếu và gây lỗi.
3. **Giữ bộ nhớ hoặc tài nguyên quá lâu:** tham chiếu của singleton ngăn các đối tượng liên quan được thu gom khi không còn cần thiết.
4. **Race condition:** nếu cố “sửa” bằng cách cập nhật field `currentRequest` mỗi khi có request mới, các request đồng thời sẽ ghi đè trạng thái của nhau.

Bài này tập trung vào việc **nhận biết và sửa quan hệ vòng đời sai** trong Java thuần, đồng thời giữ nguyên nguyên tắc constructor injection và composition root trước khi chuyển sang cơ chế request scope của DI container.

## 2. Scope, lifecycle và quyền giữ tham chiếu là ba vấn đề khác nhau

**Scope** là phạm vi mà các thành phần được phép dùng chung một instance; **lifecycle** là thời gian từ khi instance được tạo đến khi không còn hiệu lực hoặc được đóng. **Quyền giữ tham chiếu** quyết định có được lưu một đối tượng để dùng về sau hay chỉ được mượn nó trong một thao tác.

| Phạm vi | Thời điểm tạo | Thời điểm kết thúc | Ví dụ |
| --- | --- | --- | --- |
| Ứng dụng (application / singleton trong một container) | Khi startup hoặc lúc cần lần đầu | Khi ứng dụng dừng hoặc container đóng | Service không giữ trạng thái request, client dùng chung, connection pool |
| Request | Khi request bắt đầu | Khi request hoàn tất, kể cả xảy ra lỗi | Request context, transaction, unit of work |
| Tác vụ (job / operation) | Khi tác vụ được nhận | Khi tác vụ hoàn thành hoặc bị hủy | Context xử lý message, stream riêng của job |
| Tạm thời (transient) | Mỗi lần được yêu cầu tạo | Theo hợp đồng của nơi sở hữu hoặc khi không còn tham chiếu | Helper có trạng thái riêng, command object |

Trong thực tế, tên scope phụ thuộc ứng dụng và framework; “singleton” thường chỉ có nghĩa **một instance trong một phạm vi quản lý cụ thể**, không mặc nhiên là một instance duy nhất trên mọi process.

Một đối tượng được tạo xong chưa chắc đã sẵn sàng dùng mãi mãi. Ví dụ `RequestContext` có thể tồn tại trong bộ nhớ sau request nhưng **giá trị hợp đồng của nó đã hết hiệu lực**. Garbage collector không biết khái niệm “request kết thúc” để cảnh báo khi một singleton vẫn tham chiếu đến context cũ.

### Quy tắc hữu ích về quan hệ tuổi thọ

Nếu một đối tượng **lưu tham chiếu trong field và dùng nó ở các thời điểm về sau**, đối tượng được tham chiếu phải còn hợp lệ trong mọi khoảng thời gian sử dụng đó. Với một service sống suốt ứng dụng, giữ trực tiếp một session sống theo request thường vi phạm điều kiện này.

Tuy nhiên, **service sống lâu có thể sử dụng dữ liệu theo request qua tham số phương thức** nếu chỉ dùng trong lần gọi, không lưu lại hoặc để rò rỉ sang tác vụ chạy sau. Đó là điểm phân biệt quyết định khi thiết kế API.

## 3. Minh họa trên dòng thời gian: “request đầu tiên bị giữ lại”

~~~mermaid
sequenceDiagram
    participant App as Composition root
    participant S as OrderService dùng chung
    participant A as Request A / Context A
    participant B as Request B / Context B
    App->>S: Tạo một lần
    A->>S: Lắp Context A vào service sai cách
    Note over S: Field giữ Context A
    A-->>A: Kết thúc, Context A hết hiệu lực
    B->>S: Gửi đơn của B
    Note over S,B: Service vẫn tham chiếu Context A
    S-->>B: Sai danh tính hoặc lỗi context đã đóng
~~~

Có hai cách lỗi có thể biểu hiện:

**Không kiểm tra context hết hạn:** `context.actorId()` vẫn trả về `"user-A"`. Request B có thể bị xử lý dưới danh tính A. Đây là lỗi cách ly request nghiêm trọng; hệ thống không nên dựa vào việc dữ liệu “vẫn đọc được” để suy ra nó còn hợp lệ.

**Có kiểm tra context hết hạn:** `context.actorId()` ném `IllegalStateException` sau khi request A kết thúc. Việc có lỗi giúp phát hiện vấn đề sớm, nhưng hệ thống vẫn phải sửa kiến trúc để mỗi request dùng context đúng của mình.

Trường hợp dễ nhầm khác là **field mutable**:

~~~java
final class AlsoWrongOrderService {
    private RequestContext currentRequest;

    void setCurrentRequest(RequestContext request) {
        this.currentRequest = request;
    }

    void place(String orderId) {
        // Request B có thể thay currentRequest khi request A còn chạy.
        saveFor(currentRequest.actorId(), orderId);
    }

    private void saveFor(String actorId, String orderId) {
        // Minh họa đường gọi lưu dữ liệu.
    }
}
~~~

Việc thay field cho mỗi request không biến singleton thành request-scoped service. Nó biến dữ liệu của từng request thành **shared mutable state** và có thể sai ngay khi chạy đồng thời, kể cả khi `currentRequest` được khai báo `volatile`: `volatile` chỉ giải quyết một số vấn đề nhìn thấy giá trị giữa thread, không ràng buộc mỗi request với danh tính của chính nó.

## 4. Object graph đúng: giữ phụ thuộc dài hạn, truyền dữ liệu ngắn hạn theo lời gọi

Thiết kế đơn giản cho Java thuần:

- Composition root tạo một `OrderStore` và một `OrderService` dùng chung.
- Mỗi request có một `RequestContext` riêng, được tạo từ thông tin danh tính đã xác thực ở **ranh giới request**.
- `OrderService` nhận `OrderStore` bắt buộc qua **constructor injection**.
- `OrderService.place(request, orderId)` nhận `RequestContext` qua **method/parameter injection**, sử dụng ngay rồi kết thúc, không lưu nó vào field.
- Request boundary đảm bảo `RequestContext` hết hiệu lực khi request kết thúc.

~~~mermaid
flowchart TB
    Root["Application / composition root"] -->|"tạo một lần"| Store["OrderStore"]
    Root -->|"constructor injection"| Service["OrderService dùng chung"]
    Service -->|"field dài hạn"| Store
    RequestA["Request A"] -->|"tạo và sở hữu"| ContextA["RequestContext A"]
    RequestB["Request B"] -->|"tạo và sở hữu"| ContextB["RequestContext B"]
    RequestA -->|"gọi place(A, orderId)"| Service
    RequestB -->|"gọi place(B, orderId)"| Service
    ContextA -.->|"chỉ là tham số lần gọi A"| Service
    ContextB -.->|"chỉ là tham số lần gọi B"| Service
~~~

**Mũi tên nét đứt trong sơ đồ thể hiện cách sử dụng tạm thời**, không phải một cạnh tham chiếu được giữ lâu trong field. Hai request có thể dùng chung một service nếu service không giữ trạng thái riêng của từng request và các phụ thuộc dùng chung được thiết kế an toàn cho cách sử dụng đó.

Điểm quan trọng là **đưa dữ liệu ngắn hạn vào đúng nơi cần dùng**, đồng thời giữ cách tạo và cấu hình phụ thuộc dài hạn ở composition root.

## 5. Ví dụ Java 11 hoàn chỉnh: sửa lỗi captive dependency

Ví dụ sau mô phỏng lần lượt hai request thuộc hai tài khoản khác nhau. Nó dùng repository trong bộ nhớ để có thể chạy bằng JDK, không cần web server, Spring hay DI container.

Lưu thành `ScopedOrderDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class ScopedOrderDemo {

    // Chỉ có hiệu lực trong phạm vi một request.
    public static final class RequestContext implements AutoCloseable {
        private final String actorId;
        private boolean closed;

        public RequestContext(String actorId) {
            if (actorId == null || actorId.isBlank()) {
                throw new IllegalArgumentException("actorId không hợp lệ");
            }
            this.actorId = actorId;
        }

        public String actorId() {
            if (closed) {
                throw new IllegalStateException(
                        "RequestContext đã hết hiệu lực");
            }
            return actorId;
        }

        @Override
        public void close() {
            closed = true;
        }
    }

    // Hợp đồng của một dependency dài hạn.
    public interface OrderStore {
        void save(String actorId, String orderId);
    }

    // Adapter minh họa dùng theo thứ tự tuần tự, chưa hỗ trợ ghi đồng thời.
    public static final class InMemoryOrderStore implements OrderStore {
        private final List<String> saved = new ArrayList<>();

        @Override
        public void save(String actorId, String orderId) {
            saved.add(actorId + ":" + orderId);
        }

        public List<String> snapshot() {
            return List.copyOf(saved);
        }
    }

    // CÁCH SAI: giữ tham chiếu từ một request trong service sống lâu.
    public static final class CaptiveOrderService {
        private final OrderStore store;
        private final RequestContext capturedRequest;

        public CaptiveOrderService(
                OrderStore store, RequestContext capturedRequest) {
            this.store = Objects.requireNonNull(store, "store");
            this.capturedRequest =
                    Objects.requireNonNull(capturedRequest, "capturedRequest");
        }

        public void place(String orderId) {
            store.save(capturedRequest.actorId(), orderId);
        }
    }

    // CÁCH ĐÚNG: chỉ giữ dependency dùng chung.
    public static final class OrderService {
        private final OrderStore store;

        public OrderService(OrderStore store) {
            this.store = Objects.requireNonNull(store, "store");
        }

        public void place(RequestContext request, String orderId) {
            Objects.requireNonNull(request, "request");
            if (orderId == null || !orderId.matches("[A-Z0-9-]+")) {
                throw new IllegalArgumentException("orderId không hợp lệ");
            }

            // Đọc dữ liệu trong lifetime của request; không giữ request.
            String actorId = request.actorId();
            store.save(actorId, orderId);
        }
    }

    // Ranh giới ứng dụng: tạo dependency dài hạn một lần.
    public static final class Application {
        private final InMemoryOrderStore store =
                new InMemoryOrderStore();
        private final OrderService orders =
                new OrderService(store);

        public void handleRequest(
                String authenticatedActorId, String orderId) {
            // Trong thực tế actorId phải lấy từ cơ chế xác thực đáng tin cậy.
            try (RequestContext request =
                    new RequestContext(authenticatedActorId)) {
                orders.place(request, orderId);
            }
        }

        public List<String> savedOrders() {
            return store.snapshot();
        }
    }

    public static void main(String[] args) {
        // Demo lỗi: context A bị đóng nhưng service vẫn giữ tham chiếu.
        InMemoryOrderStore wrongStore = new InMemoryOrderStore();
        CaptiveOrderService wrongService;

        try (RequestContext requestA = new RequestContext("user-A")) {
            wrongService = new CaptiveOrderService(wrongStore, requestA);
            wrongService.place("ORDER-A1");
        }

        try (RequestContext requestB = new RequestContext("user-B")) {
            try {
                wrongService.place("ORDER-B1");
                throw new AssertionError(
                        "Service sai lẽ ra không được dùng context A");
            } catch (IllegalStateException expected) {
                System.out.println("Phát hiện captive dependency: "
                        + expected.getMessage());
            }
        }

        // Đồ thị đúng: một service dùng chung, context riêng mỗi request.
        Application app = new Application();
        app.handleRequest("user-A", "ORDER-A2");
        app.handleRequest("user-B", "ORDER-B2");

        System.out.println(app.savedOrders());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ScopedOrderDemo.java
java ScopedOrderDemo
~~~

Kết quả mong đợi:

~~~text
Phát hiện captive dependency: RequestContext đã hết hiệu lực
[user-A:ORDER-A2, user-B:ORDER-B2]
~~~

Trong ví dụ, `RequestContext.close()` chỉ thay trạng thái minh họa để kiểm tra hợp đồng. Ở ứng dụng thật, context có thể sở hữu tài nguyên cần đóng như transaction hoặc stream. Nếu context không có gì để giải phóng, có thể biểu diễn bằng đối tượng dữ liệu có hiệu lực theo request và để **request boundary** quyết định vòng đời sử dụng, không nhất thiết phải ép mọi context triển khai `AutoCloseable`.

**Không đưa `authenticatedActorId` trực tiếp từ dữ liệu do client tùy ý gửi**. Trong hệ thống thực, giá trị này phải được trích xuất từ một cơ chế xác thực đáng tin cậy, và thao tác nghiệp vụ vẫn phải kiểm tra quyền truy cập phù hợp. Ví dụ chỉ tập trung vào tính tách biệt giữa các request.

### Điều gì thay đổi sau khi sửa?

| Trước | Sau |
| --- | --- |
| `CaptiveOrderService` giữ `RequestContext` trong field | `OrderService` chỉ giữ `OrderStore` |
| Danh tính gắn vào instance service | Danh tính đi theo từng lời gọi `place(request, ...)` |
| Request B có thể dùng context A hoặc context đã đóng | Request B luôn cung cấp context B còn hiệu lực |
| Scope của service và context bị trộn | Scope dài hạn và ngắn hạn có ranh giới rõ ràng |
| Khó kiểm thử isolation | Có thể kiểm thử hai request tuần tự và tình huống context hết hạn |

## 6. Kiểm thử: bắt lỗi sai danh tính và dùng context đã hết hạn

Chỉ kiểm thử một request thường không đủ để phát hiện captive dependency: ở request đầu tiên, service giữ nhầm context vẫn có thể cho ra kết quả đúng. Hãy kiểm tra **nhiều request có danh tính khác nhau**, rồi cố tình sử dụng context đã đóng.

Lưu thành `ScopedOrderDemoTest.java` cùng thư mục:

~~~java
import java.util.List;

public final class ScopedOrderDemoTest {
    static void check(boolean valid, String message) {
        if (!valid) {
            throw new AssertionError(message);
        }
    }

    static void testPerRequestIsolation() {
        ScopedOrderDemo.Application app = new ScopedOrderDemo.Application();

        app.handleRequest("alice", "ORDER-101");
        app.handleRequest("bob", "ORDER-102");

        List<String> actual = app.savedOrders();
        check(
                actual.equals(List.of(
                        "alice:ORDER-101",
                        "bob:ORDER-102")),
                "Mỗi đơn phải gắn với danh tính đúng của request");
    }

    static void testExpiredContextRejected() {
        ScopedOrderDemo.InMemoryOrderStore store =
                new ScopedOrderDemo.InMemoryOrderStore();
        ScopedOrderDemo.OrderService service =
                new ScopedOrderDemo.OrderService(store);

        ScopedOrderDemo.RequestContext expired =
                new ScopedOrderDemo.RequestContext("alice");
        expired.close();

        boolean rejected = false;
        try {
            service.place(expired, "ORDER-103");
        } catch (IllegalStateException expected) {
            rejected = true;
        }

        check(rejected, "Phải từ chối context đã hết hiệu lực");
        check(store.snapshot().isEmpty(),
                "Không được ghi dữ liệu khi context đã hết hiệu lực");
    }

    static void testWrongGraphCapturesFirstRequest() {
        ScopedOrderDemo.InMemoryOrderStore store =
                new ScopedOrderDemo.InMemoryOrderStore();
        ScopedOrderDemo.RequestContext requestA =
                new ScopedOrderDemo.RequestContext("alice");
        ScopedOrderDemo.CaptiveOrderService wrong =
                new ScopedOrderDemo.CaptiveOrderService(store, requestA);

        wrong.place("ORDER-104");
        requestA.close();

        boolean failed = false;
        try {
            wrong.place("ORDER-105");
        } catch (IllegalStateException expected) {
            failed = true;
        }

        check(failed, "Service sai vẫn giữ context đã kết thúc");
        check(store.snapshot().equals(List.of("alice:ORDER-104")),
                "Service sai không được lưu đơn sau khi context hết hiệu lực");
    }

    static void testInvalidInputDoesNotReachStore() {
        ScopedOrderDemo.InMemoryOrderStore store =
                new ScopedOrderDemo.InMemoryOrderStore();
        ScopedOrderDemo.OrderService service =
                new ScopedOrderDemo.OrderService(store);

        try (ScopedOrderDemo.RequestContext request =
                new ScopedOrderDemo.RequestContext("alice")) {
            boolean rejected = false;
            try {
                service.place(request, "not valid");
            } catch (IllegalArgumentException expected) {
                rejected = true;
            }
            check(rejected, "Phải từ chối mã đơn sai định dạng");
        }

        check(store.snapshot().isEmpty(), "Không được lưu đơn không hợp lệ");
    }

    public static void main(String[] args) {
        testPerRequestIsolation();
        testExpiredContextRejected();
        testWrongGraphCapturesFirstRequest();
        testInvalidInputDoesNotReachStore();
        System.out.println("Tất cả kiểm thử đều đạt.");
    }
}
~~~

Chạy:

~~~bash
javac ScopedOrderDemo.java ScopedOrderDemoTest.java
java ScopedOrderDemoTest
~~~

Các test trên xác minh hai tính chất có ý nghĩa thiết kế: **context chỉ có hiệu lực trong request của nó** và **service dùng chung không ghi đè hoặc giữ nhầm danh tính của các request khác nhau**.

`InMemoryOrderStore` dùng `ArrayList` để ví dụ dễ đọc; đây là adapter phục vụ chương trình chạy tuần tự. Nếu nhiều request thực sự cùng chạy, repository phải hỗ trợ concurrency, hoặc lưu trữ phải có cơ chế đồng bộ/transaction thích hợp. Cải tiến đó là một vấn đề khác với việc ngăn service giữ context sai scope.

## 7. Các phương án sửa tùy vai trò của state ngắn hạn

Không phải mọi ứng dụng đều nên đưa toàn bộ `RequestContext` vào mọi phương thức. Lựa chọn phù hợp tùy trách nhiệm, cách định nghĩa scope và nhu cầu bất đồng bộ.

| Tình huống | Cách thiết kế gợi ý | Chú ý |
| --- | --- | --- |
| Service không có trạng thái request, chỉ đôi lúc cần danh tính hoặc mã truy vết | **Method injection:** truyền giá trị/context vào lần gọi cần dùng | Không lưu tham chiếu vào field, closure chạy sau hoặc cache dùng chung |
| Một use case được tạo và sử dụng hoàn toàn trong một request | Tạo **request-scoped service** tại request boundary | Mọi dependency gắn với request phải hết hiệu lực cùng request |
| Singleton cần tạo worker/session mới cho từng tác vụ | Tiêm **factory** phù hợp, tạo đối tượng theo tác vụ | Factory và caller phải xác định ai đóng đối tượng được tạo |
| Singleton cần truy cập dependency theo request bằng container | Tiêm provider/proxy được container hỗ trợ | Phải có scope đang hoạt động tại thời điểm resolve; tùy framework |
| Tác vụ chạy sau khi HTTP request kết thúc | Chuyển dữ liệu cần thiết vào **command/job snapshot** độc lập | Xác thực, phân quyền và ngữ nghĩa dữ liệu phải được bảo toàn |

### 7.1. Method injection cho thông tin ngắn hạn

Trong ví dụ chính, `OrderService.place(RequestContext request, String orderId)` nhận context **mỗi lần gọi**. Kiểu tham số không phải field và được dùng tại chỗ. Đây là cách dễ hiểu nhất khi logic nghiệp vụ đồng bộ, phụ thuộc chỉ được cần trong lời gọi.

Nếu một phương thức chỉ cần `actorId`, có thể cân nhắc truyền một giá trị cụ thể hoặc một value object bất biến thay cho toàn bộ request context. Tuy nhiên, việc chọn dữ liệu nào được truyền phải phù hợp ranh giới bảo mật: mã actor cần đến từ xác thực, không phải do caller bên ngoài tự nhận.

### 7.2. Factory theo request

Một ứng dụng có nhiều đối tượng chỉ sống trong request có thể tổ chức factory tạo **cả graph theo request**:

~~~java
// Sơ đồ API, giả định các kiểu là những thành phần của ứng dụng.
final class RequestWorkflowFactory {
    private final SharedOrderStore store; // App-scoped

    RequestWorkflowFactory(SharedOrderStore store) {
        this.store = store;
    }

    RequestWorkflow open(AuthenticatedIdentity identity) {
        RequestSession session = RequestSession.open(identity);
        return new RequestWorkflow(new RequestOrderService(store, session),
                session);
    }
}

// Caller sở hữu workflow, sử dụng trong phạm vi request:
try (RequestWorkflow workflow = factory.open(identity)) {
    workflow.orders().place(orderId);
}
~~~

Đoạn này **minh họa giao diện thiết kế**, không phải chương trình có thể biên dịch riêng: các kiểu như `SharedOrderStore`, `AuthenticatedIdentity` và `RequestWorkflow` là các thành phần cần định nghĩa theo ứng dụng.

Ưu điểm của hướng này là service mang state ngắn hạn cũng được tạo **trong cùng scope** với state của nó. Điều kiện cần giữ: request factory không trả những object như vậy vào cache của singleton; `RequestWorkflow.close()` phải giải phóng tài nguyên mà workflow thực sự sở hữu.

### 7.3. Provider hoặc proxy trong DI container

Một số container cho phép singleton giữ **provider** hoặc **proxy** của dependency theo request. Khi gọi, provider/proxy tìm **instance thuộc request hiện hành**, thay vì giữ cứng object của request đầu tiên.

Đây là cơ chế khác với việc lưu trực tiếp một `RequestContext` thật vào singleton. Nó phụ thuộc vào việc framework có thể xác định request đang hoạt động. Nếu gọi provider ngoài một scope hợp lệ, hệ thống có thể báo lỗi; nếu chuyển sang thread khác mà không truyền đúng context, kết quả cũng có thể sai. Các chi tiết thực tế khác nhau giữa framework và cấu hình.

Do đó, **provider không phải công thức để kéo dài vòng đời một request**. Nó chỉ là cách trì hoãn phân giải dependency theo scope hiện hành.

## 8. Bẫy bất đồng bộ: lời gọi kết thúc trước khi công việc dùng context

Một service có thể **không lưu context vào field** mà vẫn vô tình giữ context qua closure, task hoặc callback.

~~~java
// Nguy cơ: lambda giữ tham chiếu đến context thuộc request hiện tại.
executor.execute(() -> mailer.sendReceipt(
        request.actorId(), orderId));
~~~

Nếu executor thực thi task sau khi request đã kết thúc, `request.actorId()` có thể ném lỗi vì context hết hiệu lực. Nếu không kiểm tra hiệu lực, task có thể phụ thuộc vào dữ liệu không còn hợp lệ. Việc có thread pool không tự kéo dài scope request.

Một hướng an toàn hơn là **chuyển dữ liệu cần thiết thành một thông điệp bất biến** trước khi enqueue, sau khi hoàn thành kiểm tra và phân quyền:

~~~java
// Đọc dữ liệu trong request đang hoạt động.
String actorId = request.actorId();
String acceptedOrderId = validateOrderId(orderId);

// Task chỉ mang dữ liệu đã được chuẩn bị cho công việc về sau.
ReceiptJob job = new ReceiptJob(actorId, acceptedOrderId);
executor.execute(() -> mailer.sendReceipt(
        job.actorId(), job.orderId()));
~~~

Đoạn mã thứ hai là **phác họa**: `ReceiptJob` là value object bất biến và `validateOrderId` là logic của ứng dụng; cần định nghĩa theo miền nghiệp vụ. Khi phát tác vụ ngoài request, cần xem xét thêm tính bền vững của hàng đợi, retry, tính lặp/idempotency, tính mới của quyền truy cập và yêu cầu bảo vệ dữ liệu người dùng.

### Vì sao `ThreadLocal` không tự giải quyết vấn đề?

`ThreadLocal` gắn dữ liệu với **thread**, không gắn với khái niệm request một cách tự động. Trong thread pool, thread được tái sử dụng. Nếu không `remove()` trong `finally`, dữ liệu của request trước có thể còn lại khi thread xử lý request sau. Khi công việc chuyển sang thread khác, `ThreadLocal` ban đầu cũng không mặc nhiên theo sang thread mới.

Một hệ thống có thể triển khai scope request bằng các công cụ chuyên dụng, nhưng vẫn cần quản lý **bind/unbind**, cleanup và context propagation đúng cách. Dùng `ThreadLocal` như biến toàn cục được đổi giá trị ở mỗi request chỉ che giấu dependency và làm tăng rủi ro rò rỉ dữ liệu.

## 9. Captive dependency có thể nằm sâu trong chuỗi phụ thuộc

Không chỉ quan hệ trực tiếp kiểu `SingletonService → RequestContext` mới nguy hiểm. Một đối tượng sống lâu có thể giữ một đối tượng trung gian, mà đối tượng trung gian lại giữ trạng thái ngắn hạn.

~~~mermaid
flowchart LR
    Singleton["Application-scoped ReportService"]
    Adapter["ReportFormatter / helper"]
    Request["RequestLocale / RequestContext"]
    Singleton -->|"field"| Adapter
    Adapter -->|"field"| Request
~~~

Đồ thị này vẫn có vấn đề nếu `ReportFormatter` được xây với locale hoặc người dùng của một request rồi được chia sẻ cho các request khác. Cần xem xét **toàn bộ đường tham chiếu có khả năng giữ lại state**, không chỉ danh sách constructor của root.

Đặc biệt lưu ý:

- **Cache và singleton map:** lưu object chứa context, session hoặc dữ liệu nhạy cảm của từng request dưới khóa dùng chung.
- **Listener/callback đăng ký lâu dài:** callback đóng trên context hiện tại và chỉ được hủy khi ứng dụng dừng.
- **Async task và reactive pipeline:** lambda hoặc subscriber giữ tham chiếu đến đối tượng của scope đã kết thúc.
- **Đối tượng giữ tài nguyên có thể đóng:** transaction hoặc file stream thuộc request được lưu vào service sống lâu.
- **Shared mutable field:** một field như `currentUserId` hoặc `currentTenantId` ghi lại trên mỗi request.

Ngược lại, một **giá trị bất biến** được trích xuất và dùng đúng chính sách có thể có vòng đời khác với object request. Nhưng nếu giá trị đó là dữ liệu theo request (đặc biệt danh tính/tenant), việc đưa nó vào field singleton vẫn có thể gây **gắn nhầm một request cho tất cả request**. Bất biến về mặt kỹ thuật không đồng nghĩa phù hợp để chia sẻ về mặt nghiệp vụ.

## 10. Cách phân tích một object graph bị lệch scope

Khi review code hoặc debug lỗi “request B lại thấy dữ liệu của A”, hãy truy theo đường tham chiếu và thời gian sống:

1. **Xác định nguồn state:** dữ liệu có nguồn gốc từ request, transaction hay job cụ thể?
2. **Xác định nơi giữ nó:** field của singleton, closure, cache, listener, future hay provider?
3. **Xác định khi nào được lấy và khi nào được dùng:** chỉ trong lời gọi hiện tại hay sau khi request kết thúc?
4. **Xác định object nào sở hữu lifecycle:** ai đóng context/transaction, ai hủy listener, ai dọn cache?
5. **Kiểm tra concurrency:** hai request có thể xen kẽ cập nhật/đọc chung field không?
6. **Kiểm tra test nhiều request:** thay danh tính hoặc tenant giữa các request và xác minh kết quả không lẫn.
7. **Chọn cách sửa theo ranh giới:** truyền tham số theo lời gọi, tạo graph theo request, factory/provider đúng scope hoặc snapshot bất biến cho công việc bất đồng bộ.

Bảng chẩn đoán nhanh:

| Quan hệ thực tế | Đánh giá | Vì sao |
| --- | --- | --- |
| App-scoped service giữ app-scoped repository thread-safe | Thường hợp lý | Repository sống đủ lâu và hỗ trợ kiểu sử dụng dự kiến |
| App-scoped service giữ field `RequestContext` thật | Sai phổ biến | Context hết hiệu lực trước service |
| App-scoped service nhận context qua tham số, chỉ dùng đồng bộ | Thường hợp lý | Không giữ context sau khi request kết thúc |
| Request-scoped handler giữ app-scoped client | Thường hợp lý | Phụ thuộc sống dài hơn và có thể được dùng chung |
| Singleton giữ proxy/provider request-scoped có hợp đồng rõ | Có thể hợp lý | Mỗi lần phân giải phải nằm trong scope đang hoạt động |
| Singleton giữ object request-scoped được provider trả về | Vẫn sai nếu lưu dài hạn | Provider không kéo dài hiệu lực của instance đã trả |
| Async job giữ tham chiếu request context | Rủi ro | Job có thể chạy khi request đã kết thúc |
| Async job giữ command bất biến đã xác thực | Thường phù hợp | Dữ liệu và lifecycle của job được mô hình hóa độc lập |

**Quy tắc “scope của dependency phải dài hơn hoặc bằng consumer”** là quy tắc thực hành tốt khi consumer **giữ trực tiếp dependency trong suốt đời của mình**. Đừng áp dụng nó máy móc cho mọi tham số phương thức, factory hay proxy: những quan hệ ấy có **thời điểm phân giải và thời gian sử dụng** riêng.

## 11. Scope đúng chưa đủ: shutdown, tài nguyên và an toàn luồng

Một `OrderService` dùng chung nhiều request có thể hợp lý khi nó không giữ state theo request. Nhưng repository/client dùng chung cần được cấu hình và quản lý vòng đời đúng:

- Composition root tạo tài nguyên sống theo ứng dụng và chịu trách nhiệm đóng khi ứng dụng dừng.
- Request boundary tạo và kết thúc context/transaction của từng request, kể cả khi có ngoại lệ.
- Khi shutdown, dừng nhận công việc mới, đợi hoặc hủy tác vụ theo chính sách, rồi mới đóng tài nguyên mà tác vụ còn sử dụng.
- Service không được đóng tài nguyên được chia sẻ sau mỗi request nếu nó chỉ mượn để dùng.
- Nếu đối tượng app-scoped có mutable state, cần thiết kế thread safety thực sự; chỉ dùng `final` cho tham chiếu không làm dữ liệu bên trong thread-safe.

Trong demo, `RequestContext` dùng cờ `closed` đơn giản và `InMemoryOrderStore` dùng `ArrayList`, nên chỉ minh họa chạy **tuần tự**. Chúng không tạo cam kết concurrency. Nếu thêm xử lý song song, phải đánh giá cách phát hành tham chiếu, đồng bộ việc đóng, transaction, và khả năng đồng thời của store.

Đồng thời, **DI container không tự sửa captive dependency**. Tùy framework, một số scope mismatch có thể bị phát hiện lúc tạo graph, một số dùng scoped proxy/provider, còn một số dẫn tới lỗi khi sử dụng. Hãy đọc quy ước của container và cấu hình scope cụ thể, thay vì giả định cứ đặt annotation là vòng đời sẽ đúng.

## 12. Bài tập thực hành và câu hỏi tự đánh giá

**Bài 1 — Sửa một singleton đang giữ request state.** Cho `AuditService` dùng chung có field `private UserContext currentUser` và setter được gọi trước mỗi request. Hãy viết lại API theo cách truyền danh tính theo từng lời gọi và chứng minh bằng test hai request `alice` và `bob`.

**Bài 2 — Scope xuyên qua nhiều tầng.** `ReportService` app-scoped giữ `ReportFormatter`; formatter giữ `RequestLocale`. Hãy chỉ ra cạnh nào làm scope sai, đề xuất hai thiết kế (ví dụ truyền locale trong phương thức hoặc tạo formatter theo request) và so sánh khi nào dùng mỗi cách.

**Bài 3 — Captive dependency với tài nguyên đóng được.** Một repository app-scoped lưu một JDBC connection chỉ được mượn từ pool cho một transaction. Hãy giải thích vì sao request kế tiếp có thể gặp connection đã đóng, rồi đề xuất nơi acquire và release connection phù hợp. Phân biệt vòng đời của connection pool với vòng đời của connection được mượn.

**Bài 4 — Công việc bất đồng bộ.** Request A đăng ký tác vụ gửi biên nhận và kết thúc trước khi tác vụ chạy. Viết phiên bản lưu `RequestContext` trực tiếp trong lambda để tái hiện lỗi; sau đó thay bằng một `ReceiptJob` bất biến chứa đúng dữ liệu cần thiết. Thảo luận trường hợp quyền truy cập của người dùng thay đổi trước thời điểm tác vụ thực thi.

**Bài 5 — Test với hai request đồng thời.** Thiết kế một bài kiểm thử có thể phát hiện service lưu `currentTenantId` vào field chung. Vì sao bài test chỉ chạy tuần tự với một request thường không phát hiện được lỗi? Ngoài test, cần làm gì để giữ trạng thái request khỏi singleton?

Để tự kiểm tra, hãy trả lời ba câu hỏi: **Đối tượng nào sống suốt ứng dụng? Dữ liệu nào chỉ có hiệu lực trong request? Liệu có field, cache, closure hay task nào giữ lại dữ liệu ngắn hạn sau khi request kết thúc không?** Phân biệt rõ các câu hỏi này giúp áp dụng constructor injection, composition root, scope và lifecycle một cách nhất quán bằng Java thuần, trước khi mở rộng sang DI container.
