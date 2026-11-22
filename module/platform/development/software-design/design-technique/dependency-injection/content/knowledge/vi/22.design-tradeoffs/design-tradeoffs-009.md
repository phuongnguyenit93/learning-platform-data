# Checklist lựa chọn hợp đồng, nơi lắp ghép, scope và quyền sở hữu

Khi áp dụng **Dependency Injection (DI)**, câu hỏi không chỉ là “có nên truyền dependency qua constructor không?”. Một thiết kế DI hoạt động đúng còn phải trả lời bốn câu hỏi liên kết với nhau:

1. **Hợp đồng (contract):** Consumer thực sự cần hành vi nào, ở mức trừu tượng nào?
2. **Nơi lắp ghép (composition root):** Ai chọn implementation và tạo object graph?
3. **Scope:** Một instance được chia sẻ trong phạm vi nào, và trạng thái của nó thuộc về ai?
4. **Quyền sở hữu (ownership):** Ai phải đóng hoặc giải phóng resource, kể cả khi có ngoại lệ?

Nếu chỉ tối ưu một câu hỏi, hệ thống vẫn có thể khó kiểm thử hoặc vận hành sai. Ví dụ, chuyển từ `new JdbcRepository()` trong service sang constructor injection giúp thay implementation, nhưng nếu composition root lại tiêm **cùng một database session mang trạng thái transaction** cho mọi request, ta đã thay một lỗi phụ thuộc ngầm bằng lỗi scope. Ngược lại, dùng connection pool đúng scope mà không rõ ai đóng từng connection cũng có thể dẫn đến cạn pool.

Bài này thuộc chương **Đánh đổi thiết kế** của module **Dependency Injection**. Ta sẽ dùng một checklist có thể áp dụng trước khi viết code, lúc review pull request và khi refactor. Sau đó thực hành **Java 17 thuần**, kết hợp constructor injection, factory có kiểu cụ thể, composition root, scope và cleanup; cuối cùng xác định khi nào một DI container có thể hỗ trợ và khi nào vẫn cần quyết định kiến trúc từ phía ứng dụng.

## 1. Bốn quyết định phải nhất quán với nhau

Sơ đồ dưới mô tả một cách tổ chức trách nhiệm phổ biến:

~~~mermaid
flowchart TD
    Requirements["Nhu cầu nghiệp vụ"] --> Contract["Chọn hợp đồng / port"]
    Contract --> Root["Composition root: chọn implementation"]
    Root --> Scope["Chọn scope / object identity"]
    Scope --> Ownership["Chọn owner và cleanup"]
    Ownership --> Test["Kiểm thử behavior, wiring và lifecycle"]
    Test --> Review["Review đánh đổi, rủi ro, thay đổi trong tương lai"]
~~~

Đây là **trình tự suy nghĩ**, không phải bắt buộc triển khai các lớp theo đúng số bước. Bốn lựa chọn ảnh hưởng lẫn nhau: một contract trả về resource mới cần nói rõ ownership; một factory tạo instance theo request phải tương thích scope của consumer; một object dùng chung cần kiểm tra thread safety.

| Quyết định | Câu hỏi quan trọng nhất | Triệu chứng khi chọn sai |
| --- | --- | --- |
| **Contract** | Consumer có biết quá nhiều chi tiết hạ tầng hoặc có đang tự tra cứu dịch vụ? | Test phải dựng cả hệ thống; đổi adapter khiến nghiệp vụ phải sửa |
| **Composition root** | Quyết định implementation nằm trong lớp nghiệp vụ hay ở ranh giới ứng dụng? | `new`, `System.getenv`, service locator phân tán trong use case |
| **Scope** | Đúng instance nào được tái sử dụng, trong bao lâu? | Lẫn dữ liệu request, race condition, tạo lại resource quá tốn kém |
| **Ownership** | Instance được mượn hay được chuyển giao quyền đóng? | Cạn connection, socket rò rỉ, đóng sớm resource dùng chung |
| **Verification** | Có test nào chứng minh lựa chọn đã hoạt động đúng? | Unit test xanh nhưng production wiring, lifecycle hoặc hạ tầng sai |

**Nguyên tắc:** DI là phương pháp **tách việc sử dụng phụ thuộc khỏi việc lựa chọn và lắp ghép phụ thuộc**; nó không tự giải quyết các lỗi concurrency, transaction hay giao thức đóng resource. Những vấn đề đó vẫn cần hợp đồng và kiểm thử cụ thể.

## 2. Checklist A — Chọn hợp đồng mà consumer thật sự cần

Một contract tốt giúp consumer biểu đạt **hành vi nó cần**, không buộc nó biết cách triển khai hạ tầng. Tuy nhiên, tạo interface cho mọi class bằng mọi giá cũng làm code rườm rà.

### Những câu hỏi nên trả lời

- **[ ] Nhu cầu có thể mô tả bằng một hành vi gắn kết không?** Ví dụ `OrderStore.save(order)`, `ReceiptPublisher.publish(receipt)` thay vì cung cấp cả `DatabaseConnection` hoặc `ApplicationContext`.
- **[ ] Contract có nhỏ và hướng tới consumer không?** Một interface với các thao tác consumer thực sự cần thường ổn định hơn một interface phơi toàn bộ SDK/hạ tầng.
- **[ ] Có lý do thay implementation hoặc fake dependency không?** Có thể là kiểm thử, thay môi trường, nhiều provider, yêu cầu bảo mật, hoặc chính sách vòng đời.
- **[ ] Concrete class có đủ phù hợp không?** Một helper ổn định, không mang phụ thuộc hạ tầng, không cần hoán đổi có thể nhận trực tiếp qua constructor mà không cần interface mới.
- **[ ] Dependency bắt buộc có xuất hiện trong constructor không?** Nếu không có nó thì object không thể thực hiện nhiệm vụ, hãy kiểm tra khi khởi tạo thay vì đến nhánh chạy muộn mới báo lỗi.
- **[ ] Giá trị theo từng lần gọi có nên là method parameter không?** `RequestContext`, người dùng hiện tại hoặc idempotency key thường không nên bị giữ trong singleton service.
- **[ ] Cần tạo mới theo thao tác hay chỉ dùng một instance có sẵn?** Nếu cần tạo mới, cân nhắc typed `SessionFactory`/`Supplier<Session>` với hợp đồng scope và ownership.
- **[ ] Có vô tình dùng dependency bag/service locator không?** `Dependencies.get(Class<T>)` cho phép consumer tự tìm mọi thứ sẽ che giấu nhu cầu thực.

### Phân biệt interface, concrete class, config và factory

| Nhu cầu | Lựa chọn thường hợp lý | Đánh đổi cần chấp nhận |
| --- | --- | --- |
| Thay adapter lưu trữ, dễ tạo fake | Port `OrderStore` | Thêm một lớp abstraction cần duy trì |
| Đối tượng giá trị bất biến và ổn định | `record Money(...)` hoặc concrete class | Không nhất thiết cần interface để tiêm |
| Các giá trị liên quan về timeout/endpoint | Typed `ClientSettings` | Phải xác minh và bảo vệ bất biến |
| Mỗi thao tác cần một session mới | `SessionFactory.open()` | Phải ghi rõ ai đóng session và khi nào |
| Nhiều dịch vụ phối hợp thành một hành vi rõ | Facade `PaymentProcessor.authorize(...)` | Facade phải có trách nhiệm thật, không chỉ là túi getter |
| Một use case muốn lấy tùy ý mọi dịch vụ | Tránh truyền container/registry vào domain | Composition root cần lắp ghép tường minh hơn |

Ví dụ sự khác biệt giữa hai constructor:

~~~java
// Che giấu dependency thực:
CheckoutService(Dependencies dependencies);

// Bộc lộ hợp đồng của consumer:
CheckoutService(OrderStore store, ReceiptPublisher publisher, Clock clock);
~~~

Các kiểu ở đây là minh họa; chương trình đầy đủ ở mục 7. Constructor thứ hai **không chứng minh mọi implementation đều đúng**, nhưng giúp compiler, người review và test nhìn thấy chính xác những cộng tác viên bắt buộc.

### Khi nào không nên trừu tượng hóa?

Đừng tạo `IOrderFormatter`, `OrderFormatterImpl` và một binding DI chỉ vì formatter là một class. Nếu formatter là thuật toán thuần, không có policy thay đổi và rất dễ test trực tiếp, concrete class có thể đủ. Tạo abstraction khi có **ranh giới biến động, trách nhiệm hoặc khả năng thay thế có ý nghĩa**.

Ngược lại, không nên chờ đến khi có ba implementation mới tạo port cho database/network: **khả năng thay một dependency có side effect trong test** cũng là lý do chính đáng.

## 3. Checklist B — Chọn nơi lắp ghép object graph

**Composition root** là nơi ứng dụng xác định **implementation nào được dùng**, tạo resource và nối các dependency. Với Java thuần, đó có thể là `main()` hoặc một hàm bootstrap. Với ứng dụng dùng DI container, đó có thể là module cấu hình, registration, bean definitions hoặc nơi tạo application context.

### Câu hỏi review composition root

- **[ ] Lớp nghiệp vụ có tự gọi `new` để tạo database client, HTTP client, queue publisher không?** Nếu có, cân nhắc chuyển việc chọn adapter ra root.
- **[ ] Service có tự đọc `System.getenv` hoặc file cấu hình triển khai không?** Validation config và chọn adapter nên nằm ở biên ứng dụng.
- **[ ] Có một nơi rõ ràng kiểm tra cấu hình trước khi mở resource không?** Cấu hình thiếu hoặc sai nên bị chặn trước I/O khi có thể.
- **[ ] Dependency được tạo **một lần hay nhiều lần** có chủ đích?** Root phải quyết định identity theo scope, không vô tình tạo hai kho trạng thái độc lập.
- **[ ] Lớp library có ép ứng dụng dùng một backend hay secret source cố định không?** Library nên nhận config/ports tường minh; factory nội bộ được tạo helper nhưng không nên tự chọn hạ tầng của caller.
- **[ ] Khi cần cấu hình khác nhau ở hai ứng dụng/test, có tạo được hai object graph độc lập không?** Tránh mutable global registry hoặc Singleton pattern dùng sai chỗ.
- **[ ] Nếu có DI container, business service có đang gọi `container.getBean(...)` không?** Container nên phục vụ root, không trở thành dependency locator bên trong domain.
- **[ ] Có test lắp ghép tối thiểu hoặc smoke test khởi tạo các binding quan trọng không?**

### Manual DI không phải trạng thái kém hoàn chỉnh

~~~java
// Minh họa lắp ghép bằng Java thuần.
OrderStore store = createOrderStore(settings);
ReceiptPublisher publisher = createPublisher(settings);
Clock clock = Clock.systemUTC();

OrderService service = new OrderService(store, publisher, clock);
~~~

Một ứng dụng nhỏ có thể dừng ở manual DI nếu cấu hình dễ đọc, phạm vi và cleanup rõ ràng. DI container hữu ích khi số lượng binding, scope, module, lifecycle callback hoặc yêu cầu cấu hình vượt khả năng quản lý thuận tiện bằng tay. **Container không thay thế việc lựa chọn contract và ownership**; nó chỉ tự động hóa một phần lắp ghép và vòng đời theo quy tắc của nó.

### Lưu ý về nhiều entrypoint

Web server, CLI command, background job và integration test có thể có **điểm bắt đầu khác nhau**. Không cần cưỡng ép chúng dùng một global root duy nhất. Mỗi entrypoint có thể có bootstrap riêng, nhưng nên **tái sử dụng các factory/hợp đồng lắp ghép rõ ràng**, tránh tạo ra những cấu hình ngầm mâu thuẫn.

## 4. Checklist C — Chọn scope và identity của instance

Scope trả lời: **một dependency được tái sử dụng trong giới hạn nào?** Nó không tự bảo đảm thread safety, tính bất biến hoặc tính đúng của giao dịch.

| Scope | Ý nghĩa thường gặp | Ví dụ | Cần cảnh giác |
| --- | --- | --- | --- |
| **Application/singleton-scoped** | Cùng binding/context dùng lại một instance | Connection pool, stateless service, cache có chính sách rõ | Chia sẻ state mutable, thread safety, teardown |
| **Request-scoped** | Một instance trong mỗi request | Request metadata, unit of work, một số transaction context | Bị singleton giữ tham chiếu quá lâu |
| **Operation/transient** | Mỗi lần mở/tạo có instance riêng | Session/stream cho một thao tác, stateful processor | Tạo tốn kém, quên cleanup, chi phí mở tài nguyên |
| **Factory/provider-scoped** | Factory có scope riêng và cấp sản phẩm theo contract | Pool dùng chung cấp session từng lần | Nhầm scope factory với scope sản phẩm |
| **Custom scope** | Theo job, tenant session, transaction hoặc ranh giới khác | Context của một batch job | Kết thúc scope không rõ, async task chạy quá hạn |

### Checklist xác định scope

- **[ ] Object có mutable state hay không?** Nếu có, state thuộc toàn ứng dụng, request, user hay một thao tác?
- **[ ] Nhiều luồng có truy cập chung không?** Nếu có, implementation có hợp đồng thread safety hoặc đồng bộ hóa thích hợp không?
- **[ ] Có cần chia sẻ **đúng cùng reference** giữa nhiều consumer không?** Kiểm tra identity bằng `==` ở wiring test nếu đây là yêu cầu.
- **[ ] Hai registration cùng class có được phép tách instance không?** Singleton của DI container thường là chính sách theo binding/context, **không phải một object duy nhất trong toàn JVM**.
- **[ ] Một singleton có đang giữ dependency ngắn hạn hơn nó không?** Đây là *captive dependency*: ví dụ singleton giữ `RequestContext` của request đầu tiên.
- **[ ] Factory cấp sản phẩm mới hay trả instance cached?** Không thể suy chỉ từ tên `Provider`/`Supplier`.
- **[ ] Khi request kết thúc, mọi tham chiếu tới resource request-scoped có còn bị giữ bởi job hoặc callback không?**
- **[ ] Một cache/pool dùng chung có được phép phục vụ nhiều tenant không?** Nếu không, cần isolation hoặc phân vùng rõ ràng.

~~~mermaid
flowchart TD
    Root["Application root"] --> Pool["Pool dùng chung"]
    Root --> Service["OrderService dùng chung"]
    ReqA["Request A"] --> CtxA["RequestContext A"]
    ReqB["Request B"] --> CtxB["RequestContext B"]
    ReqA -->|"truyền context theo lời gọi"| Service
    ReqB -->|"truyền context theo lời gọi"| Service
    Service -->|"mở session cho mỗi thao tác"| Factory["SessionFactory"]
    Factory -->|"mượn tài nguyên"| Pool
~~~

Ở sơ đồ này, **service dùng chung** không giữ trực tiếp `RequestContext`. Nó nhận dữ liệu request qua tham số, trong khi factory được phép dùng chung để tạo session cho từng tác vụ. Cần tránh giả định rằng “ít instance hơn” luôn nhanh hơn hoặc an toàn hơn: một session mutable dùng chung có thể phá isolation, còn nhiều kết nối được mở trực tiếp có thể quá tốn kém.

## 5. Checklist D — Xác định quyền sở hữu và cleanup

**Ownership** trả lời: *ai phải đảm bảo `close()` hoặc thao tác giải phóng được thực hiện?* Nơi tạo, nơi dùng và owner có thể trùng hoặc khác nhau.

| Tình huống | Owner điển hình | Quy tắc |
| --- | --- | --- |
| Composition root tự tạo pool/client dùng chung | Composition root/lifecycle manager | Đóng sau khi consumer ngừng sử dụng |
| Service mở session mới qua typed factory có hợp đồng caller-owned | Service trong phạm vi thao tác | Dùng `try-with-resources`, kể cả khi lỗi |
| Service chỉ mượn connection pool từ constructor | Owner bên ngoài service | Service không tự đóng pool sau một request |
| Factory mở resource rồi cấu hình thất bại trước khi trả | Factory | Dọn tất cả resource đã mở dở |
| Container tự tạo managed bean có lifecycle callback | Container theo registration/framework | Xem quy tắc disposal thực tế |
| Caller cấp instance có sẵn cho container | Theo hợp đồng chuyển giao | Không mặc định container được quyền đóng resource bên ngoài |

### Checklist ownership

- **[ ] API trả về `AutoCloseable` có ghi rõ *owned* hay *borrowed* không?**
- **[ ] Nếu factory tạo mới mỗi lần, từng instance có owner và giới hạn sống cụ thể không?**
- **[ ] Nếu resource dùng chung, các consumer có biết rằng họ chỉ được mượn không?**
- **[ ] Nếu bước khởi tạo thứ hai thất bại, những resource được mở trước đó có được dọn không?**
- **[ ] Nếu thao tác nghiệp vụ thất bại, cleanup có chạy trong `finally`/`try-with-resources` không?**
- **[ ] Nếu `close()` cũng ném lỗi, ngoại lệ gốc có được giữ lại hoặc ghi nhận phù hợp không?**
- **[ ] Các tác vụ async có còn dùng resource sau khi method trả về không?** Nếu có, không đóng quá sớm.
- **[ ] Khi container/context kết thúc, đã ngừng nhận tác vụ mới, xử lý tác vụ đang chạy và đóng dependency nền đúng thứ tự chưa?**
- **[ ] Có test/metric phát hiện tài nguyên đang active tăng mãi không?**

### Không suy ownership từ annotation

Một factory singleton-scoped có thể cấp hàng nghìn session caller-owned. Container quản lý **factory** không tự theo dõi mọi sản phẩm do factory thủ công tạo ngoài cơ chế đăng ký của nó. Ngược lại, một framework có thể quản lý lifecycle cho object được tạo theo registration cụ thể. Cần kiểm tra contract của **factory**, **binding** và **container đang sử dụng**.

### Tài nguyên đóng quá sớm cũng nguy hiểm

~~~java
// Pseudocode: sai nếu việc bất đồng bộ còn dùng session.
try (OrderSession session = factory.open()) {
    return CompletableFuture.runAsync(
            () -> session.insert(order));
}
// session có thể bị đóng trước khi tác vụ chạy.
~~~

Đây là đoạn minh họa trong phương thức giả định, không phải ví dụ Java chạy độc lập. `try-with-resources` chỉ biết phạm vi khối lệnh đồng bộ. Với async, thường cần **mở và đóng session trong chính tác vụ** hoặc có owner điều phối tới khi công việc cuối cùng hoàn tất.

## 6. Ma trận quyết định: rủi ro nào cần ưu tiên?

Không cần tranh luận trừu tượng “mọi singleton đều xấu” hoặc “mọi class phải có interface”. Hãy xem **chi phí thay đổi và hậu quả khi chọn sai**.

| Quyết định | Lợi ích | Chi phí/đánh đổi | Dấu hiệu phải kiểm tra thêm |
| --- | --- | --- | --- |
| Interface/port nhỏ | Thay adapter, test fake, ranh giới rõ | Thêm kiểu và hợp đồng cần bảo trì | Port chỉ bọc một class không có lý do biến động |
| Inject concrete class | Ít ceremony, dễ đọc | Khó thay khi concrete phụ thuộc hạ tầng | Test phải mở mạng/database thật |
| Manual composition root | Rõ wiring, không lệ thuộc framework | Root có thể dài khi ứng dụng lớn | Wiring bị lặp ở nhiều entrypoint |
| DI container | Tự động hóa binding/scope/lifecycle | Cấu hình ngầm, proxy, lỗi scope khó quan sát | Test chỉ chạy với container nên khó phân lập logic |
| Singleton/application scope | Giảm chi phí tạo, chia sẻ resource | State mutable, thread safety, cleanup | Có request/user state trong object |
| Per-operation instance | Cô lập trạng thái, vòng đời rõ | Chi phí tạo, cleanup mỗi lần | Mở socket thật liên tục thay vì dùng pool |
| Factory typed | Tạo khi cần, giữ abstraction | Ownership sản phẩm phải rõ | Provider trả borrowed instance nhưng caller đóng |
| Config object có kiểu | Nhóm giá trị liên quan, kiểm tra bất biến | Có thể thành “bag” nếu nhồi mọi thứ vào | Consumer nhận toàn bộ app settings không cần thiết |

**Ưu tiên review những lỗi có hậu quả nghiêm trọng**: lộ dữ liệu giữa request/tenant, double charge, mất audit, rò rỉ connection, đóng sai pool, hoặc chạy production với adapter mặc định không bền vững. Cải thiện tên interface/constructor là hữu ích nhưng không quan trọng hơn sự an toàn của trạng thái và resource.

## 7. Thực hành Java 17: quyết định cả bốn trục trong một object graph

Tình huống: service nhận đơn hàng, dùng một **session mới cho mỗi lần lưu**, phát biên nhận sau khi lưu, và lấy thời gian từ `Clock`. Hai lần gọi khác nhau có request context riêng; composition root tạo một pool giả dùng chung để cấp session. Ta cố ý dùng Java thuần để thấy rõ quyết định ở đâu.

Thiết kế:

| Thành phần | Contract | Scope | Owner |
| --- | --- | --- | --- |
| `OrderService` | Nhận `OrderSessionFactory`, `ReceiptPublisher` và `Clock` | Có thể dùng chung trong mô hình tuần tự này | Composition root |
| `InMemorySessionPool` | Factory cấp `OrderSession` và giữ dữ liệu | Một instance dùng chung trong ứng dụng demo | Composition root đóng |
| `OrderSession` | `insert(order)` và `close()` | Một instance cho mỗi lần xử lý đơn | `OrderService.accept()` đóng |
| `RequestContext` | Dữ liệu request, `requesterId` | Một giá trị cho từng lời gọi | Caller cung cấp, không cần `close()` |
| `RecordingPublisher` | Phát biên nhận, trong ví dụ chỉ ghi danh sách | Một fake dùng chung trong test | Test/composition root |
| `Clock` | Nguồn thời gian | Chia sẻ được trong ví dụ | Composition root |

~~~mermaid
flowchart LR
    Root["Composition root"] --> Pool["InMemorySessionPool"]
    Root --> Publisher["ReceiptPublisher"]
    Root --> Clock["Clock"]
    Pool --> Factory["OrderSessionFactory"]
    Factory --> Service["OrderService"]
    Publisher --> Service
    Clock --> Service
    Request["RequestContext theo lời gọi"] --> Service
    Service -->|"open/close mỗi lần"| Session["OrderSession"]
~~~

Lưu toàn bộ mã sau vào một tệp `Main.java`. Các kiểu ngoài `Main` được khai báo package-private để có thể chạy trong một file. Khi tách thành thư viện/ứng dụng thực, hãy chọn package và mức truy cập phù hợp cho API công khai.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

record Order(String id, int quantity) {
    Order {
        Objects.requireNonNull(id, "id");
        if (id.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }
    }
}

record RequestContext(String requesterId) {
    RequestContext {
        Objects.requireNonNull(requesterId, "requesterId");
        if (requesterId.isBlank()) {
            throw new IllegalArgumentException("Missing requester");
        }
    }
}

record Receipt(String orderId, String requesterId, Instant acceptedAt) {
    Receipt {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(requesterId, "requesterId");
        Objects.requireNonNull(acceptedAt, "acceptedAt");
    }
}

interface OrderSession extends AutoCloseable {
    void insert(Order order);

    @Override
    void close();
}

@FunctionalInterface
interface OrderSessionFactory {
    // Hợp đồng: open trả một session MỚI do caller sở hữu.
    OrderSession open();
}

@FunctionalInterface
interface ReceiptPublisher {
    void publish(Receipt receipt);
}

// Fake pool cho demo: giữ dữ liệu chung, cấp session ngắn hạn.
// Không có concurrency/transaction thật.
final class InMemorySessionPool implements AutoCloseable {
    private final Map<String, Order> rows = new HashMap<>();
    private int opened;
    private int released;
    private boolean closed;

    OrderSession open() {
        if (closed) {
            throw new IllegalStateException("Pool already closed");
        }
        opened++;
        return new OrderSession() {
            private boolean sessionClosed;

            @Override
            public void insert(Order order) {
                Objects.requireNonNull(order, "order");
                if (sessionClosed || closed) {
                    throw new IllegalStateException("Session unavailable");
                }
                if (rows.containsKey(order.id())) {
                    throw new IllegalArgumentException("Duplicate order");
                }
                rows.put(order.id(), order);
            }

            @Override
            public void close() {
                if (!sessionClosed) {
                    sessionClosed = true;
                    released++;
                }
            }
        };
    }

    Optional<Order> findById(String id) {
        return Optional.ofNullable(rows.get(id));
    }

    int openedCount() {
        return opened;
    }

    int releasedCount() {
        return released;
    }

    boolean isClosed() {
        return closed;
    }

    @Override
    public void close() {
        if (closed) {
            return;
        }
        if (opened != released) {
            throw new IllegalStateException(
                    "Outstanding sessions: " + (opened - released));
        }
        closed = true;
    }
}

final class RecordingPublisher implements ReceiptPublisher {
    private final List<Receipt> sent = new ArrayList<>();

    @Override
    public void publish(Receipt receipt) {
        sent.add(Objects.requireNonNull(receipt, "receipt"));
    }

    List<Receipt> sent() {
        return List.copyOf(sent);
    }
}

final class OrderService {
    private final OrderSessionFactory sessions;
    private final ReceiptPublisher publisher;
    private final Clock clock;

    OrderService(
            OrderSessionFactory sessions,
            ReceiptPublisher publisher,
            Clock clock) {
        this.sessions = Objects.requireNonNull(sessions, "sessions");
        this.publisher = Objects.requireNonNull(publisher, "publisher");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    Receipt accept(Order order, RequestContext request) {
        Objects.requireNonNull(order, "order");
        Objects.requireNonNull(request, "request");

        // Session caller-owned chỉ sống trong một lần xử lý.
        try (OrderSession session =
                     Objects.requireNonNull(sessions.open(), "session")) {
            session.insert(order);
        }

        // Dữ liệu request không được giữ trong field của service.
        Receipt receipt = new Receipt(
                order.id(), request.requesterId(), Instant.now(clock));
        publisher.publish(receipt);
        return receipt;
    }
}

public class Main {
    public static void main(String[] args) {
        Clock fixed = Clock.fixed(
                Instant.parse("2026-06-01T00:00:00Z"), ZoneOffset.UTC);
        RecordingPublisher notices = new RecordingPublisher();

        // Composition root sở hữu pool, không phải OrderService.
        InMemorySessionPool pool = new InMemorySessionPool();
        try (pool) {
            OrderSessionFactory factory = pool::open;
            OrderService service =
                    new OrderService(factory, notices, fixed);

            Order first = new Order("O-1", 2);
            Receipt accepted = service.accept(
                    first, new RequestContext("alice"));
            check(accepted.equals(new Receipt(
                    "O-1", "alice", Instant.parse("2026-06-01T00:00:00Z"))),
                    "Wrong receipt");
            check(pool.findById("O-1").equals(Optional.of(first)),
                    "Order must be saved");
            check(pool.openedCount() == 1 && pool.releasedCount() == 1,
                    "Session must be closed once");

            // Không lưu lại context của alice cho request tiếp theo.
            OrderService otherService =
                    new OrderService(factory, notices, fixed);
            Receipt second = otherService.accept(
                    new Order("O-2", 1), new RequestContext("bob"));
            check(second.requesterId().equals("bob"),
                    "Each request must have its own identity");
            check(pool.openedCount() == 2 && pool.releasedCount() == 2,
                    "Each operation needs its own closed session");

            // Đường lỗi: insert thất bại nhưng session vẫn được đóng.
            boolean duplicateRejected = false;
            try {
                service.accept(new Order("O-1", 3),
                        new RequestContext("carol"));
            } catch (IllegalArgumentException expected) {
                duplicateRejected = true;
            }
            check(duplicateRejected, "Duplicate must be rejected");
            check(pool.openedCount() == 3 && pool.releasedCount() == 3,
                    "Error path must close the session");
            check(notices.sent().size() == 2,
                    "Failed insert must not publish receipt");

            // Thiếu dữ liệu request bị chặn trước khi mở session.
            int before = pool.openedCount();
            boolean requestRejected = false;
            try {
                service.accept(new Order("O-3", 1), null);
            } catch (NullPointerException expected) {
                requestRejected = true;
            }
            check(requestRejected && pool.openedCount() == before,
                    "Invalid request must not open resources");

            // Root có quyền đóng pool sau khi các consumer đã xong.
            check(!pool.isClosed(), "Pool must be open inside root scope");
        }
        check(pool.isClosed(), "Composition root must close pool");
        check(pool.openedCount() == pool.releasedCount(),
                "All sessions must be returned");

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

### Đọc lại bốn quyết định qua ví dụ

**Contract.** `OrderService` chỉ nhận `OrderSessionFactory`, `ReceiptPublisher` và `Clock`. Nó không biết `InMemorySessionPool` là implementation cụ thể, cũng không nhận `ApplicationContext` để tự tìm repository. `RequestContext` là **tham số từng lần gọi**, không phải dependency sống cùng service.

**Composition root.** `Main` tạo pool, publisher và clock; chọn `pool::open` làm factory; tạo hai service dùng cùng factory. `OrderService` không tự tạo pool hay quyết định loại lưu trữ.

**Scope.** Pool được chia sẻ giữa hai service. Mỗi lần `accept` tạo **một session riêng** và xử lý request context tương ứng. Đoạn kiểm tra `openedCount() == releasedCount()` chứng minh số phiên đã được hoàn trả trong demo.

**Ownership.** `try (pool)` biểu diễn root sở hữu pool; `try (OrderSession session = ...)` biểu diễn service sở hữu session được factory cấp trong phạm vi thao tác. Khi đơn trùng, exception vẫn khiến `close()` của session chạy.

### Giới hạn và đánh đổi của mô hình

- `InMemorySessionPool` chỉ là **fake** dùng `HashMap` và bộ đếm; nó **không thread-safe**, không phải connection pool thật và không mô phỏng transaction. Không dùng trực tiếp mã này cho production.
- Sau khi `session.insert(order)` thành công, `publisher.publish(receipt)` vẫn có thể thất bại. Khi ấy đơn đã được ghi nhưng biên nhận chưa phát; DI và `try-with-resources` **không tạo transaction xuyên qua hai hệ thống**. Nếu cần tin cậy, hãy thiết kế transaction/outbox, retry và idempotency tùy yêu cầu.
- Session được đóng **trước** khi publish. Đây là một lựa chọn vòng đời trong ví dụ, không phải luật áp dụng cho mọi workflow: một số use case cần transaction bao một nhóm bước khác và phải thiết kế lại contract.
- Với HTTP/JDBC thật, factory thường cấp wrapper/session mà `close()` trả về pool, không nhất thiết hủy kết nối vật lý. Hợp đồng ownership vẫn yêu cầu caller hoàn tất cleanup đúng lúc.
- `Clock.fixed(...)` giúp test ổn định; production thường dùng đồng hồ hệ thống được composition root cấp.

## 8. Điểm kiểm tra trước khi viết DI container configuration

Một DI container có thể đăng ký nhiều object theo scope, nhưng **không nên chuyển sang container trước khi mô tả được các quyết định bằng ngôn ngữ độc lập framework**.

Một mẫu bản ghi quyết định (*decision record*) ngắn:

| Trường | Ví dụ cho OrderService |
| --- | --- |
| **Consumer** | `OrderService` |
| **Hợp đồng bắt buộc** | `OrderSessionFactory`, `ReceiptPublisher`, `Clock` |
| **Nguồn lựa chọn implementation** | Composition root của ứng dụng |
| **Phạm vi consumer** | Dùng chung nếu stateless và dependency phù hợp |
| **Phạm vi dependency dùng chung** | Pool theo application |
| **Phạm vi sản phẩm factory** | Một session mỗi thao tác |
| **Dữ liệu request** | `RequestContext` theo method parameter |
| **Owner/cleanup** | Root đóng pool; `accept` đóng session |
| **Đường lỗi** | Insert thất bại không publish; session vẫn đóng |
| **Rủi ro còn lại** | Publish thất bại sau khi insert; concurrency chưa được kiểm chứng |
| **Test cần có** | Behavior, duplicate/failure, scope identity, lifecycle, integration |

Khi chuyển sang container thật, có thể áp dụng singleton/application scope cho factory/pool nếu framework và implementation hỗ trợ; service có thể được tạo theo scope phù hợp; còn session vẫn được cấp theo từng thao tác hoặc transaction. **Không được tiêm một session caller-owned duy nhất làm singleton chỉ vì factory là singleton.**

Để tránh lỗi cấu hình ngầm, nên có một **wiring smoke test** tạo application context, resolve entrypoint chính, kiểm tra các dependency bắt buộc và xác minh callback teardown. Unit test của `OrderService` vẫn có thể dùng fake bằng Java thuần mà không cần container.

## 9. Checklist review theo mức ưu tiên

Với pull request có thay đổi DI, có thể dùng thứ tự kiểm tra sau:

### Mức 1 — Phải giải quyết trước khi hợp nhất

- **[ ] Không có rò rỉ dữ liệu giữa request/user/tenant** do chia sẻ sai instance.
- **[ ] Không có resource caller-owned bị bỏ quên hoặc resource dùng chung bị đóng sớm.**
- **[ ] Không có đường lỗi làm phát side effect thành công giả** (ví dụ lưu thất bại nhưng vẫn gửi xác nhận).
- **[ ] Không có fallback ngầm từ dependency production bắt buộc sang No-Op/in-memory** khi cấu hình sai.
- **[ ] Dependency ngắn hạn không bị singleton giữ lại ngoài vòng đời hợp lệ.**
- **[ ] Những thao tác đa luồng trên dependency dùng chung có hợp đồng thread safety.**

### Mức 2 — Cần chứng minh trước khi đưa vào vận hành

- **[ ] Constructor nêu rõ các dependency bắt buộc, không dùng dependency bag không giới hạn.**
- **[ ] Composition root xác minh config trước khi mở resource khi có thể.**
- **[ ] Factory/provider có hợp đồng tạo mới, cache, scope và ownership.**
- **[ ] Shutdown, lỗi khởi tạo dở, timeout và async cleanup có đường xử lý.**
- **[ ] Unit test bảo vệ behavior; wiring/integration test bảo vệ binding và resource thật.**

### Mức 3 — Cải thiện khả năng duy trì

- **[ ] Mỗi port có ranh giới nghiệp vụ rõ, không tạo abstraction vô ích.**
- **[ ] Constructor không dài do một class gánh quá nhiều trách nhiệm.**
- **[ ] Không phụ thuộc annotation/proxy khi một decorator hoặc Java thuần đơn giản là đủ.**
- **[ ] Các tradeoff được ghi lại để người sau hiểu vì sao chọn scope và owner.**
- **[ ] Có kế hoạch refactor theo bước nhỏ nếu mã cũ còn tự tạo dependency.**

Chia theo mức ưu tiên giúp nhóm không sa vào tranh luận tên interface trước khi xử lý một rủi ro thực sự như **cạn pool** hoặc **sai phạm vi trạng thái**.

## 10. Tình huống thường gặp và cách áp dụng checklist

### 10.1. Một service chỉ có một concrete collaborator

Nếu `TaxCalculator` thuần tính toán, không giữ state, không cần fake và không có khả năng thay implementation trong tương lai gần, inject concrete class có thể hợp lý. Constructor injection vẫn giúp thể hiện quan hệ phụ thuộc. Không cần tạo interface chỉ để đủ “DI”.

**Đổi quyết định khi:** thuật toán thuế phụ thuộc quốc gia/provider, cần giả lập lỗi hoặc cần thay implementation theo cấu hình.

### 10.2. Hai service cần cùng kho trạng thái trong bộ nhớ

Composition root nên tạo **một instance** và đưa đúng cùng reference vào cả hai nếu chia sẻ là chủ đích. Test wiring nên kiểm tra identity/trạng thái xuyên service. Không bắt buộc dùng Singleton pattern; scope do root/container quyết định.

**Rủi ro:** nếu kho mutable và phục vụ nhiều request, cần thread safety, isolation và giới hạn dữ liệu phù hợp.

### 10.3. Đưa một JDBC Connection vào constructor singleton service

Một connection/session có trạng thái transaction thường không phù hợp chia sẻ toàn ứng dụng. Có thể inject **DataSource/pool hoặc typed session factory** phù hợp, rồi mượn/trả connection cho từng thao tác theo contract.

**Rủi ro:** session bị giữ quá lâu, không trả về pool hoặc đóng nhầm pool.

### 10.4. Library muốn dùng lại giữa nhiều ứng dụng

Library nên công khai **port hoặc API cấu hình tường minh**, không tự đọc biến môi trường và tự quyết định backend của mọi caller. Ứng dụng chọn adapter tại composition root; library có thể tạo helper nội bộ.

**Rủi ro:** mutable global registry khiến hai application/test cấu hình khác nhau ảnh hưởng lẫn nhau.

### 10.5. Một service singleton cần dữ liệu người dùng hiện tại

Không giữ `RequestContext` của request đầu tiên trong constructor singleton. Truyền dữ liệu cần thiết qua **method parameter** hoặc dùng typed scoped provider/proxy nếu framework hỗ trợ.

**Rủi ro:** captive dependency, lẫn người dùng và truy cập resource đã đóng.

### 10.6. Muốn chọn giữa decorator và proxy

Decorator tường minh dễ nhìn tại root, dễ kiểm thử thuần Java. Framework proxy hữu ích cho chính sách cắt ngang được framework hỗ trợ, nhưng cần kiểm tra **đường gọi qua proxy**, self-invocation, thứ tự advice và scope.

**Rủi ro:** nghĩ annotation đã áp dụng nhưng gọi trực tiếp trên target hoặc gọi nội bộ khiến advice không chạy.

## 11. Những sai lầm khi dùng checklist

**Checklist không phải công thức tạo vô hạn abstraction.** Việc đánh dấu “có interface” không chứng minh contract được thiết kế tốt. Một interface khổng lồ hoặc bag có type vẫn có thể giấu nhu cầu.

**Scope không phải bài toán tối thiểu số instance.** Singleton giúp tái sử dụng resource đắt, nhưng state request không nên được chia sẻ chỉ để giảm khởi tạo.

**Lifecycle không kết thúc ở `close()`.** Đối tượng có callback/async task có thể tiếp tục dùng resource sau khi method trả về. Cần gắn cleanup với **lần sử dụng cuối cùng**.

**Test chỉ dùng fake chưa đủ.** Fake có thể không mô phỏng isolation, transaction hoặc lỗi mạng; khi dùng JDBC/HTTP thật cần contract/integration test.

**Cấu hình container không thay thế composition root có chủ đích.** Một DI container nhận registration mà application root đưa vào; nó không thể tự biết đâu là lựa chọn đúng cho scope, business constraint hoặc quyền sở hữu.

**Đừng mặc định mọi tài nguyên do container có tham chiếu đều được container đóng.** Ownership phụ thuộc cơ chế đăng ký, việc transfer instance và lifecycle contract của framework.

## 12. Bài tập thực hành

**Bài 1 — Điền ma trận bốn trục.** Một `ReportService` cần repository JDBC, formatter và đồng hồ; mỗi request có người dùng riêng. Chọn contract, nơi lắp ghép, scope của từng dependency và owner của connection pool/session. Giải thích vì sao formatter thuần có thể không cần interface.

**Bài 2 — Phát hiện captive dependency.** Một singleton `EmailService` nhận `RequestContext` vào constructor. Hãy chỉ ra rủi ro; thiết kế lại để request data không bị giữ quá scope.

**Bài 3 — Đổi factory thành session dùng chung.** Trong `Main.java`, giả sử root mở một `OrderSession` duy nhất rồi inject thẳng cho `OrderService`. Liệt kê các lỗi có thể xuất hiện khi hai request dùng đồng thời, khi một thao tác đóng session và khi root đóng pool.

**Bài 4 — Ownership khi lỗi.** Factory mở connection rồi khởi tạo encoder nhưng bước thứ hai ném ngoại lệ. Ai đóng connection chưa được trả cho caller? Thiết kế cơ chế cleanup để giữ ngoại lệ gốc.

**Bài 5 — Thêm test.** Mở rộng ví dụ để `ReceiptPublisher` ném ngoại lệ sau khi insert thành công. Xác định trạng thái thực tế và mô tả các lựa chọn giao dịch/outbox; không mặc định DI có rollback.

**Bài 6 — Quyết định có dùng container không.** Một CLI nhỏ có 5 service, không có request scope, chỉ dùng một client cần đóng. So sánh lợi ích/chi phí giữa manual DI với container. Đề xuất tiêu chí chuyển đổi khi ứng dụng lớn lên.

**Bài 7 — Viết decision record.** Với một use case thực tế trong dự án, ghi contract, implementation root, scope, owner, đường lỗi, test và rủi ro chưa giải quyết. Không chỉ ghi “dùng singleton” mà bỏ qua lý do.

## 13. Tự kiểm tra hiểu bài

**Câu 1.** Vì sao một thiết kế DI cần xem xét cả contract và scope? **Vì** nhận dependency đúng interface không bảo đảm instance được chia sẻ hoặc cô lập đúng theo trạng thái nghiệp vụ.

**Câu 2.** Constructor injection có cần mọi dependency đều là interface không? **Không.** Concrete class cũng có thể được inject; abstraction nên có lý do về trách nhiệm, khả năng thay thế hoặc test.

**Câu 3.** Một factory singleton-scoped trả session mới mỗi lần. Session có tự thành singleton không? **Không.** Scope của factory và sản phẩm được nó cấp là hai hợp đồng khác nhau.

**Câu 4.** Service dùng chung có nên giữ `RequestContext` trong field không? **Thường không** nếu context thuộc từng request; truyền qua method hoặc provider theo scope phù hợp.

**Câu 5.** Nếu composition root tạo pool và service mượn pool, ai đóng pool? **Composition root/lifecycle manager** theo hợp đồng; service không tự đóng resource dùng chung sau từng thao tác.

**Câu 6.** `try-with-resources` xử lý điều gì và không xử lý điều gì? **Nó đóng resource caller-owned** trong phạm vi khối lệnh đồng bộ, kể cả đường ngoại lệ; nó không tự giải quyết transaction xuyên hệ thống hoặc vòng đời của công việc bất đồng bộ chạy sau khối.

**Câu 7.** DI container có thay thế việc chọn ownership không? **Không.** Container chỉ quản lý vòng đời theo registration và contract đã cấu hình; tài nguyên tạo ngoài quản lý vẫn cần owner rõ.

**Câu 8.** Loại test nào kiểm tra identity và vòng đời các binding thật? **Wiring/integration test** ở composition root/container; unit test của consumer bảo vệ behavior khi đã được cấp dependency phù hợp.

## Ghi nhớ

- **Chọn contract theo nhu cầu thực** của consumer: port nhỏ khi có ranh giới thay đổi, concrete class khi đủ, typed factory cho resource theo tác vụ, tránh dependency bag và service locator trong domain.
- **Composition root** chọn và lắp ghép implementation, xác minh cấu hình, quyết định instance nào được dùng chung; DI container có thể tự động hóa nhưng không thay thế các quyết định này.
- **Scope** phải đi cùng trạng thái và thread safety: chia sẻ pool/factory không giống chia sẻ session; dữ liệu request không nên bị singleton giữ lại.
- **Ownership** phải tường minh ở cả factory, consumer và container: ai tạo, ai mượn, ai nhận chuyển giao, ai đóng khi thành công và khi lỗi.
- **Checklist chỉ có giá trị khi gắn với bằng chứng**: unit test cho behavior, wiring test cho identity/scope, integration test cho resource thật và một decision record ngắn cho những đánh đổi quan trọng.
