# Quản lý scope, khởi tạo và kết thúc vòng đời

**DI container** (bộ chứa Dependency Injection) không chỉ giúp thay các lệnh `new` bằng cấu hình đăng ký. Khi ứng dụng cần nhiều dịch vụ và nhiều tài nguyên, container còn có thể đảm nhận các quyết định về **scope** (phạm vi tái sử dụng instance), **khởi tạo** (construction/initialization) và **kết thúc vòng đời** (destruction/disposal). Đây là những quyết định trực tiếp ảnh hưởng đến tính đúng đắn, hiệu năng, khả năng kiểm thử và việc giải phóng tài nguyên.

Bài thuộc chương **Bộ chứa DI** của module **Dependency Injection**. Chúng ta đi từ **constructor injection** và **composition root** bằng Java thuần đến cách một DI container tự động hóa object graph, sau đó phân tích điều container có thể quản lý và điều kiến trúc ứng dụng vẫn phải tự quyết định. Một ví dụ Java 17 mô phỏng ba phạm vi sử dụng và thứ tự dọn dẹp, không phụ thuộc Spring hoặc thư viện DI cụ thể.

## 1. DI container quản lý những gì?

Giả sử ứng dụng gồm `OrderService`, `OrderRepository` và một connection pool. Một composition root viết thủ công có thể làm:

~~~java
// Minh họa: các lớp OrderService, JdbcOrderRepository và
// ConnectionPool chỉ là những kiểu giả định ở đoạn này.
ConnectionPool pool = new ConnectionPool(/* cấu hình */);
OrderRepository repository = new JdbcOrderRepository(pool);
OrderService service = new OrderService(repository);
~~~

Cách này đã là **DI**: `OrderService` nhận cộng tác viên qua constructor, không tự biết cách tạo repository. Khi ứng dụng lớn lên, nơi lắp ghép phải tự quyết định đối tượng nào được dùng chung, đối tượng nào tạo mới, lúc nào khởi tạo và ai đóng pool.

DI container hỗ trợ biến các quyết định này thành **cấu hình/registration**. Mô hình tổng quát:

~~~mermaid
flowchart TD
    Root["Composition root / cấu hình ứng dụng"] --> Container["DI container"]
    Container --> Definitions["Đăng ký / binding"]
    Definitions --> Scope["Chính sách scope"]
    Scope --> Graph["Tạo và tiêm object graph"]
    Graph --> Init["Khởi tạo / kiểm tra sẵn sàng"]
    Init --> Run["Phục vụ các tác vụ"]
    Run --> Shutdown["Kết thúc scope / đóng resource"]
~~~

Một registration thường mô tả **kiểu hoặc khóa dependency**, **cách tạo implementation** và **scope/lifecycle** mong muốn. Khi một thành phần cần dependency, container có thể giải quyết đồ thị phụ thuộc, tái sử dụng instance theo scope và thực hiện các callback vòng đời phù hợp.

**Giới hạn:** không phải mọi DI container hỗ trợ mọi scope hoặc mọi loại callback giống nhau. Tên scope, chế độ tạo sớm/trễ, quy tắc gọi `close()` và trách nhiệm với đối tượng do người dùng cung cấp phải được kiểm tra theo **tài liệu của container cụ thể**.

## 2. Scope là chính sách tái sử dụng, không phải một tính chất cố định của class

**Scope** trả lời câu hỏi: *Trong phạm vi nào, những lần yêu cầu dependency được nhận cùng instance?*

| Scope thường gặp | Khi được tạo | Khi nào được tái sử dụng? | Ví dụ phù hợp |
| --- | --- | --- | --- |
| **Singleton/application** | Khi khởi động hoặc khi resolve lần đầu, tùy cấu hình | Cùng registration trong một container/application context | Pool, client hoặc service stateless được thiết kế dùng chung |
| **Transient/prototype** | Theo từng lần resolve hoặc theo quy tắc của container | Thường không tái sử dụng theo registration đó | Bộ xử lý giữ trạng thái riêng cho mỗi tác vụ |
| **Request/scoped** | Khi có request/scope và dependency lần đầu được cần | Trong **cùng request/scope**, không chia sẻ sang request khác | Ngữ cảnh request, đơn vị công việc theo request |
| **Custom scope** | Theo định nghĩa do ứng dụng/framework cung cấp | Trong một phiên, tác vụ, transaction hoặc ranh giới riêng | Session, job, tenant context nếu thiết kế đúng |

Không phải container nào cũng có sẵn **request scope**; thường scope đó chỉ tồn tại khi gắn với một môi trường thực thi như web framework, hoặc được ứng dụng chủ động tạo. Cũng không nên mặc định các từ **transient** và **prototype** có cùng lifecycle và cơ chế cleanup trên mọi container.

### Singleton của container không nhất thiết là Singleton pattern

Một lớp có constructor bình thường vẫn có thể được container quản lý theo singleton scope. Container tái sử dụng **một instance theo registration trong phạm vi context**; lớp không cần có trường `static INSTANCE` hoặc constructor private.

Ngược lại, Singleton pattern đặt quyền kiểm soát instance trong lớp, thường qua điểm truy cập static. Hai container độc lập có thể tạo hai instance singleton-scoped cùng kiểu; hai binding trong cùng container cũng có thể tạo hai instance khác nhau. Vì vậy, từ **singleton** trong scope không hàm ý một object duy nhất trong toàn JVM.

### Scope thuộc dependency chứ không tự lan sang consumer

Một `OrderService` được tạo mới mỗi request vẫn có thể nhận **cùng một connection pool** dùng chung toàn ứng dụng. Ngược lại, một service singleton-scoped có thể cần một `RequestContext` khác nhau trong từng lần xử lý. Không được gắn scope ứng dụng cho request context chỉ vì service sử dụng nó là singleton.

## 3. Ba giai đoạn vòng đời cần tách bạch

### 3.1. Construction: tạo đối tượng và giải quyết dependency

Container thường phải chọn implementation, lấy/khởi tạo các dependency mà constructor yêu cầu, rồi gọi constructor của đối tượng đích.

Ví dụ logic: để tạo `OrderService(repo)`, container cần có `OrderRepository` trước; để tạo repository JDBC, nó có thể cần một pool. Điều này khiến **thứ tự khởi tạo có quan hệ với đồ thị phụ thuộc**.

~~~mermaid
flowchart BT
    Pool["ConnectionPool"] --> Repo["JdbcOrderRepository"]
    Repo --> Service["OrderService"]
~~~

Đây là **hướng sử dụng phụ thuộc**: repository sử dụng pool và service sử dụng repository. Khi tạo service, container phải có các dependency thích hợp, có thể tạo chúng trước hoặc sử dụng proxy/provider tùy cơ chế.

**Fail fast:** với những dependency bắt buộc, lỗi không có binding, xung đột binding hoặc không tạo được dependency nên được phát hiện càng sớm càng tốt. Không nên âm thầm thay một database thật bằng No-Op chỉ để hệ thống khởi động thành công.

### 3.2. Initialization: sau khi object đã được tạo

Một số container hỗ trợ callback/hook **sau khi tiêm phụ thuộc**. Đây là nơi có thể kiểm tra thêm trạng thái, thiết lập tài nguyên cần thiết hoặc đánh dấu component sẵn sàng theo hợp đồng.

Điều cần phân biệt:

- **Constructor:** tạo object hợp lệ và gán những dependency bắt buộc; ưu tiên kiểm tra tham số ngay.
- **Initialization hook:** chạy sau khi container lắp ghép theo quy tắc của framework; không phải lúc nào cũng đồng nghĩa cả ứng dụng đã sẵn sàng nhận request.
- **Application readiness:** có thể cần kiểm tra database, queue, migration hoặc khởi động server ở cấp ứng dụng, vượt khỏi callback của một object.

Đừng phụ thuộc vào một thứ tự callback giả định giữa các component độc lập nếu container không cam kết thứ tự đó. Nếu A **phải** hoàn tất khởi tạo trước B, hãy biểu diễn quan hệ phụ thuộc và sử dụng cơ chế khởi tạo được framework hỗ trợ, thay vì trông chờ thứ tự quét class.

### 3.3. Destruction: kết thúc scope, đóng resource

Khi scope/container kết thúc, hệ thống cần giải phóng những object mà nó **sở hữu**, nhất là pool, executor, socket, client và các thành phần đăng ký callback.

Một số container gọi destroy callback, `close()` hoặc một interface lifecycle chuyên biệt theo registration; số khác yêu cầu người dùng khai báo rõ cleanup. Với object được cấp từ bên ngoài, container có thể **không có ownership** để đóng.

Ví dụ, nếu root tạo pool, repository mượn pool và service mượn repository, việc đóng pool phải diễn ra **sau khi** những consumer ngừng sử dụng nó. Container có thể hỗ trợ thứ tự teardown dựa trên dependency graph, nhưng **không thể mặc định mọi framework sẽ đóng theo đúng thứ tự ngược** trong mọi tình huống; cần xác minh lifecycle contract cụ thể.

## 4. Eager và lazy initialization

Hai chiến lược tạo instance phổ biến:

| Chiến lược | Đặc điểm | Lợi ích | Rủi ro/đánh đổi |
| --- | --- | --- | --- |
| **Eager** | Tạo tại bootstrap hoặc lúc mở scope | Phát hiện nhiều lỗi wiring/khởi tạo sớm; lần dùng đầu ít tốn công | Thời gian khởi động và tài nguyên ban đầu cao hơn |
| **Lazy** | Đợi đến lần resolve/sử dụng đầu | Tránh tạo đối tượng có thể không cần; khởi động nhẹ hơn | Lỗi cấu hình có thể chỉ lộ ở request đầu; độ trễ lần đầu cao hơn |

**Không nên hiểu lazy nghĩa là “không cần cleanup”.** Một singleton được tạo trễ vẫn phải được đóng khi container dừng **nếu nó đã được tạo và container là owner**. Một registration chưa từng được khởi tạo thường không có instance để đóng.

Một ví dụ khác: nếu service dùng lazy provider, việc gọi provider sau khi scope đã kết thúc phải được xử lý đúng theo container (thường là lỗi scope/closed context). Không nên giữ provider rồi truy cập resource đã đóng trong một tác vụ chạy muộn.

## 5. Ví dụ Java 17: mô phỏng singleton, request và transient

Ví dụ này tự tạo một **MiniContainer** để quan sát các quyết định về scope và lifecycle. Nó không phải thư viện DI đầy đủ: không có auto-discovery, qualifier, proxy hoặc injection annotation. Ta cố ý viết rõ mọi bước để thấy container thực sự phải làm gì.

Chương trình minh họa:

- `SharedPool` được tạo **lazy một lần** trong container, rồi chia sẻ cho mọi request.
- `RequestContext` được tạo **một lần cho mỗi request scope**.
- `RequestHandler` được tạo **mới mỗi lần yêu cầu handler**, nhưng nhận đúng pool và context của scope.
- `RequestScope.close()` đóng context; `MiniContainer.close()` đóng các scope còn mở trước khi đóng pool.
- Log sự kiện cho phép xác minh **identity và thứ tự cleanup**, không cần framework hoặc kết nối mạng.

Lưu toàn bộ vào `Main.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class SharedPool implements AutoCloseable {
    private final List<String> events;
    private boolean closed;

    SharedPool(List<String> events) {
        this.events = events;
        events.add("pool.open");
    }

    void send(String requestId, String payload) {
        if (closed) {
            throw new IllegalStateException("Pool already closed");
        }
        events.add("pool.send:" + requestId + ":" + payload);
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            events.add("pool.close");
        }
    }
}

final class RequestContext implements AutoCloseable {
    private final String id;
    private final List<String> events;
    private boolean closed;

    RequestContext(String id, List<String> events) {
        this.id = Objects.requireNonNull(id, "id");
        if (id.isBlank()) {
            throw new IllegalArgumentException("Blank request id");
        }
        this.events = events;
        events.add("context.open:" + id);
    }

    String id() {
        return id;
    }

    void record(String value) {
        if (closed) {
            throw new IllegalStateException("Request context closed");
        }
        events.add("context.record:" + id + ":" + value);
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            events.add("context.close:" + id);
        }
    }
}

// Đối tượng transient: mỗi lần lấy handler được tạo instance mới.
final class RequestHandler {
    private final SharedPool pool;
    private final RequestContext context;

    RequestHandler(SharedPool pool, RequestContext context) {
        this.pool = Objects.requireNonNull(pool, "pool");
        this.context = Objects.requireNonNull(context, "context");
    }

    void handle(String payload) {
        context.record(payload);
        pool.send(context.id(), payload);
    }
}

final class RequestScope implements AutoCloseable {
    private final MiniContainer owner;
    private final RequestContext context;
    private boolean closed;

    RequestScope(MiniContainer owner, String requestId, List<String> events) {
        this.owner = owner;
        this.context = new RequestContext(requestId, events);
    }

    RequestHandler handler() {
        if (closed) {
            throw new IllegalStateException("Request scope closed");
        }
        return new RequestHandler(owner.pool(), context);
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            context.close();
            owner.release(this);
        }
    }
}

final class MiniContainer implements AutoCloseable {
    private final List<String> events;
    private final List<RequestScope> activeScopes = new ArrayList<>();
    private SharedPool pool;
    private boolean closed;

    MiniContainer(List<String> events) {
        this.events = Objects.requireNonNull(events, "events");
        events.add("container.start");
    }

    SharedPool pool() {
        checkOpen();
        // Lazy singleton: tạo khi dùng lần đầu, sau đó tái sử dụng.
        if (pool == null) {
            pool = new SharedPool(events);
        }
        return pool;
    }

    RequestScope openRequest(String id) {
        checkOpen();
        RequestScope scope = new RequestScope(this, id, events);
        activeScopes.add(scope);
        return scope;
    }

    void release(RequestScope scope) {
        activeScopes.remove(scope);
    }

    private void checkOpen() {
        if (closed) {
            throw new IllegalStateException("Container closed");
        }
    }

    @Override
    public void close() {
        if (closed) {
            return;
        }
        // Scope con kết thúc trước dependency cấp ứng dụng.
        while (!activeScopes.isEmpty()) {
            activeScopes.get(activeScopes.size() - 1).close();
        }
        if (pool != null) {
            pool.close();
        }
        closed = true;
        events.add("container.close");
    }
}

public class Main {
    public static void main(String[] args) {
        List<String> events = new ArrayList<>();

        try (MiniContainer container = new MiniContainer(events)) {
            check(events.equals(List.of("container.start")),
                    "Pool phải được khởi tạo lazy");

            SharedPool a = container.pool();
            SharedPool b = container.pool();
            check(a == b, "Pool cùng container phải là một instance");

            try (RequestScope requestA = container.openRequest("A")) {
                RequestHandler h1 = requestA.handler();
                RequestHandler h2 = requestA.handler();
                check(h1 != h2, "Handler phải transient");
                h1.handle("one");
                h2.handle("two");
            }

            try (RequestScope requestB = container.openRequest("B")) {
                requestB.handler().handle("three");
            }

            check(!events.contains("pool.close"),
                    "Pool phải sống lâu hơn các request");
        }

        List<String> expected = List.of(
                "container.start",
                "pool.open",
                "context.open:A",
                "context.record:A:one",
                "pool.send:A:one",
                "context.record:A:two",
                "pool.send:A:two",
                "context.close:A",
                "context.open:B",
                "context.record:B:three",
                "pool.send:B:three",
                "context.close:B",
                "pool.close",
                "container.close"
        );
        check(events.equals(expected),
                "Sai identity hoặc thứ tự lifecycle: " + events);

        System.out.println("PASS");
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 Main.java
java Main
~~~

Kết quả mong đợi:

~~~text
PASS
~~~

Trong log, `pool.open` chỉ xuất hiện một lần cho cả hai request; `context.open:A`/`context.close:A` và `context.open:B`/`context.close:B` xác định hai phạm vi request độc lập; `pool.close` xuất hiện **sau** khi cả hai context đóng. Mỗi lời gọi `requestA.handler()` vẫn tạo một handler mới, nhưng các handler trong cùng request nhận **cùng context**.

**Giới hạn của mô phỏng:** mã `MiniContainer` và danh sách log này dành cho luồng đơn, **không được thiết kế thread-safe cho truy cập đồng thời**; production container thường có cơ chế đồng bộ/điều phối scope riêng. Ví dụ cũng bỏ qua chính sách xử lý lỗi `close()` của nhiều resource để tập trung vào nguyên lý. Không sao chép nó như một container production.

## 6. Đóng scope đúng lúc là một phần của tính đúng đắn

Một service singleton-scoped có thể nhận request context qua tham số phương thức hoặc provider theo scope. Điều quan trọng là context của request A **không lọt sang** request B.

~~~mermaid
flowchart TD
    Container["Application container"]
    Pool["Pool singleton"]
    ReqA["Request scope A"]
    ReqB["Request scope B"]
    CtxA["Context A"]
    CtxB["Context B"]
    HandlerA["Handler A1 / A2"]
    HandlerB["Handler B1"]
    Container --> Pool
    Container --> ReqA
    Container --> ReqB
    ReqA --> CtxA
    ReqB --> CtxB
    ReqA --> HandlerA
    ReqB --> HandlerB
    HandlerA --> CtxA
    HandlerB --> CtxB
    HandlerA --> Pool
    HandlerB --> Pool
~~~

Với **manual DI**, ta có thể mô hình hóa scope bằng khối `try-with-resources` như ví dụ. Với framework, request scope có thể gắn với lifecycle request tự động, nhưng **các tác vụ bất đồng bộ và callback chạy muộn** phải được kiểm tra cẩn thận: liệu scope còn hoạt động khi provider được truy cập hay resource được dùng?

### Captive dependency: dependency sống ngắn bị giữ trong object sống dài

Một lỗi phổ biến là singleton service giữ trực tiếp `RequestContext` được tạo khi request đầu tiên bắt đầu:

~~~java
// Minh họa lỗi thiết kế: class giữ context một request quá lâu.
final class BadReportService {
    private final RequestContext context;

    BadReportService(RequestContext context) {
        this.context = context;
    }

    void generate(String reportId) {
        context.record(reportId);
    }
}
~~~

Nếu `BadReportService` được quản lý singleton scope nhưng `RequestContext` thuộc request scope, object singleton giữ tham chiếu tới dependency có vòng đời **ngắn hơn**. Kết quả có thể là dữ liệu request bị lẫn, context đã đóng vẫn bị truy cập hoặc bộ nhớ được giữ quá lâu. Nhiều container có cơ chế phát hiện hoặc từ chối loại wiring này, nhưng không nên dựa hoàn toàn vào container để sửa thiết kế.

Các hướng xử lý thường rõ hơn:

- Truyền thông tin request cần thiết qua **tham số phương thức**.
- Sử dụng provider/proxy có **ngữ nghĩa resolve theo scope hiện tại**, nếu framework hỗ trợ và hợp đồng rõ ràng.
- Thay đổi scope của service khi chính service cũng mang trạng thái request.

**Không** biến `RequestContext` thành singleton chỉ để hết lỗi tiêm; điều đó có thể phá tính cô lập giữa người dùng.

## 7. Ai sở hữu và đóng tài nguyên do container cung cấp?

Scope và ownership có liên quan nhưng **không đồng nghĩa**.

| Tình huống | Owner cần xem xét | Điều không nên tự giả định |
| --- | --- | --- |
| Container tự tạo singleton pool từ registration | Container/lifecycle manager theo hợp đồng | Mọi container luôn tự `close()` tất cả các loại pool |
| Composition root tạo HTTP client bên ngoài rồi cấp instance sẵn cho container | Thường composition root, trừ khi chuyển giao | Container đương nhiên được phép đóng client được mượn |
| Provider thủ công tạo session mới mỗi lần `open()` | Caller hoặc transaction manager theo hợp đồng factory | Container biết mọi session đã được tạo |
| Request scope tạo context có cleanup callback | Scope/lifecycle manager | Dùng context sau khi request kết thúc vẫn an toàn |
| Transient/prototype chứa socket/file | Theo hợp đồng cụ thể của container hoặc consumer | Scope ngắn đồng nghĩa cleanup được thực hiện tự động |

Một nguyên tắc quan trọng: **container chỉ quản lý vòng đời những gì nó có quyền và có cơ chế quản lý**. Việc tiêm một factory không tự biến mọi sản phẩm do factory tạo ngoài container thành resource được container theo dõi.

Ví dụ, container có thể sở hữu một connection pool; mỗi connection mượn từ pool thường cần được **trả lại** sau một transaction. Nếu một consumer tự đóng cả pool, các service khác có thể bị ảnh hưởng. Nếu không trả connection, pool có thể cạn dù container vẫn hoạt động bình thường.

## 8. Nếu khởi tạo hoặc teardown gặp lỗi thì sao?

Các lỗi khởi tạo/vòng đời nên được tính ngay từ khi thiết kế wiring.

**Lỗi trong constructor hoặc initialization hook.** Một component có thể mở resource A thành công rồi không tạo được resource B. Container có thể chỉ nhìn thấy object chưa được đăng ký hoàn chỉnh; chính factory hoặc logic khởi tạo cũng phải bảo đảm cleanup resource đã mở dở theo hợp đồng. Không mặc định container sẽ đóng những resource nó chưa từng nhận ownership.

**Lỗi khi một destroy callback ném ngoại lệ.** Đóng một resource thất bại không nên khiến hệ thống vô tình bỏ qua hoàn toàn cleanup của các resource khác. Container/framework có thể cung cấp chính sách tổng hợp lỗi và tiếp tục shutdown; trong DI thủ công, cần tự thiết kế `try/finally` hoặc đóng nhiều resource và giữ các lỗi quan trọng. Với `try-with-resources`, Java hỗ trợ **suppressed exceptions** khi cả thao tác và cleanup thất bại.

**Lỗi thứ tự shutdown.** Nếu client phụ thuộc pool, không thể đóng pool khi client vẫn còn tác vụ đang chạy. Cần điều phối ngừng nhận request, hoàn thành/hủy tác vụ, đóng consumer rồi mới đóng dependency nền theo chính sách rõ ràng.

**Lazy dependency chưa từng được tạo.** Không cần gọi cleanup trên instance chưa tồn tại. Nhưng nếu đã tạo, container phải biết nó cần được đóng hay không theo registration.

**Scope kết thúc nhưng còn async task.** Việc trả về `CompletableFuture` không có nghĩa resource có thể đóng ngay lập tức. Đóng theo thời điểm công việc thực tế kết thúc hoặc lựa chọn ownership theo tác vụ bất đồng bộ.

~~~mermaid
flowchart TD
    Stop["Ngừng nhận tác vụ mới"] --> Drain["Chờ hoặc hủy tác vụ đang chạy"]
    Drain --> Scoped["Đóng scope ngắn hạn còn mở"]
    Scoped --> Consumers["Kết thúc consumer / callback"]
    Consumers --> Shared["Đóng pool/client dùng chung"]
    Shared --> End["Container đóng"]
~~~

Đây là **sơ đồ thứ tự mục tiêu**, không phải cam kết rằng mọi container tự triển khai chính xác các bước này. Với một framework cụ thể, phải xác minh cách nó quản lý server, background worker, shutdown hook và resource ownership.

## 9. Khả năng kiểm thử: kiểm tra hành vi và kiểm tra wiring riêng

Một bài unit test của `OrderService` có thể inject fake repository và kiểm tra nghiệp vụ **mà không khởi chạy container**. Nhưng unit test đó không chứng minh production đã đăng ký đúng scope hoặc cleanup đúng resource.

Nên tách hai loại kiểm thử:

1. **Unit test của consumer:** dependency được truyền qua constructor; xác minh logic với fake/stub, thời điểm lỗi và các nhánh nghiệp vụ.
2. **Integration/wiring test của container:** tạo context, resolve các component, xác minh **identity** của singleton và request-scoped instance, lỗi cấu hình, khởi tạo/đóng đúng lifecycle.

Với Java thuần, ví dụ `Main.java` ở trên đã kiểm tra:

- Hai lần lấy pool từ một container nhận **cùng instance**.
- Hai lần lấy handler trong request nhận **hai instance transient**.
- Hai request có các context riêng nhưng dùng chung pool.
- Scope đóng context trước khi ứng dụng đóng pool.

Với framework thực, nên thêm các test về lifecycle callback, bean có điều kiện, resource từ external factory, request scope, tình huống lỗi khởi tạo và shutdown khi có tác vụ đang chạy. Chạy test dùng context mới giúp giảm việc state dùng chung làm các test ảnh hưởng lẫn nhau.

## 10. Những nhầm lẫn hay gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Container luôn tạo dependency ngay lúc khởi động.” | Có thể eager hoặc lazy tùy binding/cấu hình. |
| “Singleton scope là chỉ có một object thuộc kiểu này trong toàn JVM.” | Thường là một instance **theo registration/context**, không phải toàn kiểu ở mọi context. |
| “Transient không cần đóng vì object sẽ được GC.” | Nếu transient giữ resource, vẫn phải có owner và cleanup rõ ràng. |
| “Tiêm vào singleton thì dependency tự thành singleton.” | Scope của consumer và dependency là hai chính sách khác nhau; cần tránh captive dependency. |
| “Một instance singleton tự nhiên thread-safe.” | Scope không xử lý race condition trên trạng thái mutable. |
| “Container biết factory thì biết mọi object factory tạo.” | Sản phẩm của factory thủ công có thể ngoài quản lý. |
| “Có annotation destroy thì tài nguyên nào cũng sẽ được đóng đúng thứ tự.” | Cần xem ownership, scope, callback và hợp đồng framework. |
| “Đóng container là có thể bỏ mặc task async.” | Task còn dùng resource phải được điều phối kết thúc/hủy an toàn. |

## 11. Bài tập thực hành

**Bài 1 — Chọn scope.** Cho `Clock`, connection pool, formatter stateless, `RequestContext` và `TransactionSession`. Chọn scope ban đầu hợp lý, giải thích điều kiện về trạng thái, thread safety và vòng đời; nêu loại nào không nên giữ toàn ứng dụng.

**Bài 2 — Chuyển từ manual DI sang container.** Từ chuỗi `Pool → Repository → Service`, viết bảng binding với implementation, scope và owner. Mô tả thứ tự khởi tạo và teardown dự kiến mà không dựa vào một framework cụ thể.

**Bài 3 — Khác biệt eager/lazy.** Nếu lazy singleton chỉ được gọi trong một request rất hiếm, điều gì xảy ra khi cấu hình bị sai? Đề xuất cách kiểm tra bootstrap/wiring hoặc readiness để phát hiện lỗi sớm hơn khi cần.

**Bài 4 — Captive dependency.** Một singleton `NotificationService` lưu `CurrentRequest` vào trường constructor. Xác định nguy cơ lẫn request; sửa bằng truyền dữ liệu request theo lời gọi hoặc provider theo scope hiện hành.

**Bài 5 — Lỗi shutdown.** Connection pool đang phục vụ 3 tác vụ async. Hãy mô tả thứ tự ngừng nhận request, chờ/cancel task và đóng pool. Nếu một task lỗi khi cleanup, nên xử lý các resource còn lại thế nào?

## 12. Tự kiểm tra hiểu bài

**Câu 1.** Một registration singleton-scoped có nhất thiết là Singleton pattern với constructor private? **Không.** Container có thể tái sử dụng object của class bình thường.

**Câu 2.** Hai lần resolve transient có bảo đảm luôn là hai object khác nhau? **Thường như vậy theo định nghĩa transient**, nhưng phải xem factory/binding: nếu factory tự trả cùng instance đã cache, ngữ nghĩa tạo mới thực tế không còn như mong đợi.

**Câu 3.** Container có luôn đóng `AutoCloseable` được caller tạo bên ngoài rồi cung cấp dưới dạng instance sẵn không? **Không thể khẳng định.** Cần xem quyền sở hữu và hợp đồng framework.

**Câu 4.** Vì sao singleton service không nên giữ trực tiếp `RequestContext` của request đầu tiên? **Vì** context sống ngắn hơn service; việc giữ lâu có thể làm lẫn trạng thái hoặc truy cập resource đã đóng.

**Câu 5.** Lazy initialization có làm mất yêu cầu cleanup không? **Không.** Instance nào đã được tạo và thuộc ownership của scope vẫn cần cleanup phù hợp khi scope kết thúc.

**Câu 6.** Unit test của một service dùng fake có đủ chứng minh scope container đúng không? **Không.** Cần kiểm tra wiring và lifecycle của container trong integration test thích hợp.

## Ghi nhớ

- **DI container** tự động hóa việc tạo/lắp ghép dependency **và có thể** quản lý scope, initialization, teardown theo registration và lifecycle contract.
- **Scope** quy định phạm vi tái sử dụng instance; singleton, transient và request-scoped giải quyết những nhu cầu khác nhau, không tự xác định thread safety.
- **Eager/lazy** quyết định lúc tạo object; khởi tạo thất bại và cleanup tài nguyên tạo dở vẫn cần được xử lý có chủ đích.
- **Lifecycle và ownership** phải rõ ở cả container, factory/provider, scope và resource được mượn. Không suy ra container sẽ đóng mọi thứ chỉ vì có DI.
- **Composition root, constructor injection và Java thuần** giúp hiểu đúng object graph trước khi dùng container; hãy kiểm thử cả hành vi của service lẫn **identity, scope, khởi tạo và kết thúc vòng đời** của cấu hình thực tế.
