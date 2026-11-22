# Tác động của proxy, scope và callback vòng đời tới cách dùng phụ thuộc

**Dependency Injection (DI)** trong framework không chỉ là việc tự động gọi constructor. Khi container cung cấp một service, tham chiếu nhận được có thể là **proxy** thay vì đối tượng triển khai trực tiếp; đối tượng đó có thể sống theo **scope** toàn ứng dụng, từng request hoặc từng công việc; đồng thời các **callback vòng đời** có thể chạy trước khi service được sử dụng hoặc khi scope kết thúc.

Ba yếu tố này ảnh hưởng trực tiếp đến cách gọi phương thức, tính nhất quán của trạng thái, việc kiểm thử và quyền sở hữu tài nguyên. Ví dụ, phương thức gắn `@Transactional` có thể hoạt động khi được gọi **qua proxy** nhưng không áp dụng cùng cách khi lớp tự gọi phương thức của chính mình. Một service singleton có thể vô tình giữ trạng thái của request đầu tiên nếu được inject sai scope. Một callback khởi tạo có thể chạy trước khi proxy sẵn sàng để áp dụng các hành vi được chặn.

Bài học thuộc chương **DI trong framework** của module **Dependency Injection / Inversion of Control (IoC)**. Ta sẽ dùng các khái niệm của Spring để minh họa một số cơ chế phổ biến, đồng thời giữ trọng tâm ở các nguyên lý áp dụng được cho nhiều DI container. Phần thực hành dùng **Java 17 thuần**: tự tạo decorator, scope và vòng đời để thấy chính xác điều container có thể tự động hóa.

Sau bài này, bạn có thể:

- Phân biệt **proxy**, **target** và dependency mà bên sử dụng thật sự giữ.
- Giải thích vì sao lời gọi **đi qua proxy** khác với lời gọi **nội bộ trên `this`**.
- Phân tích lỗi ghép scope dài–ngắn, scoped proxy và provider.
- Đặt callback khởi tạo/hủy đúng giai đoạn và tránh dựa vào behavior chưa được thiết lập.
- Viết ví dụ Java thuần mô phỏng proxy, request scope và lifecycle; kiểm thử danh tính instance, thời điểm gọi và đóng tài nguyên.
- Biết những rủi ro khi chuyển code constructor injection thủ công sang container của framework.

## 1. Điều gì thay đổi khi đưa service vào framework?

Với DI thủ công, composition root thường làm việc trực tiếp với instance:

~~~java
OrderRepository orders = new InMemoryOrderRepository();
CheckoutService checkout = new CheckoutService(orders);
~~~

Nếu dùng một DI framework, bootstrap đăng ký cách tạo `OrderRepository` và `CheckoutService`, sau đó container quyết định **cấp instance nào**, có cần bao bởi proxy hay không, và khi nào kết thúc vòng đời.

~~~mermaid
flowchart LR
    Client["Bên sử dụng service"] -->|"giữ tham chiếu được inject"| Handle["Proxy hoặc target"]
    Handle -->|"ủy quyền khi có proxy"| Target["Target thực hiện nghiệp vụ"]
    Target --> Port["Dependency qua constructor"]
    Container["DI container"] -.->|"tạo, nối, quản lý scope"| Handle
    Container -.->|"quản lý vòng đời"| Target
~~~

Trong nhiều trường hợp, client nhận trực tiếp target. Khi có AOP, scope proxy hoặc cơ chế khác, client có thể nhận một **đối tượng trung gian**. Chỉ nhìn tên interface hoặc annotation injection không đủ để kết luận có bao nhiêu instance, loại proxy nào hay lời gọi được chặn ở đâu.

Ba trục cần xem riêng:

| Trục | Câu hỏi thiết kế | Ví dụ rủi ro |
| --- | --- | --- |
| **Proxy** | Lời gọi có đi qua lớp trung gian cần thiết không? | `@Transactional` không được áp dụng cho lời gọi nội bộ |
| **Scope** | Tham chiếu này đại diện cho instance nào, sống bao lâu? | Singleton giữ request context quá lâu |
| **Lifecycle** | Đối tượng được khởi tạo/đóng ở thời điểm nào? | Callback sử dụng dependency hoặc proxy khi chưa sẵn sàng |

**Container không xóa ranh giới kiến trúc.** Constructor injection vẫn nên cho thấy dependency bắt buộc; composition root/binding vẫn phải chọn đúng adapter, scope và lifecycle; test nghiệp vụ vẫn có thể dùng Java thuần trước khi dùng container ở mức integration.

## 2. Proxy là gì trong đồ thị đối tượng?

**Proxy** là đối tượng đứng trước một target và nhận lời gọi thay mặt target. Nó có thể bổ sung hành vi trước/sau lời gọi hoặc quyết định target nào cần gọi.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy
    participant T as Target
    C->>P: execute()
    P->>P: Kiểm tra / mở transaction / logging
    P->>T: execute()
    T-->>P: Kết quả
    P->>P: Commit / xử lý lỗi / đo thời gian
    P-->>C: Kết quả
~~~

Các lý do dùng proxy phổ biến gồm:

- **Cross-cutting concerns:** transaction, caching, logging, metrics, security.
- **Scope delegation:** tham chiếu ổn định trỏ đến target khác nhau theo request/job.
- **Lazy resolution:** trì hoãn lấy hoặc khởi tạo target cho đến khi cần.
- **Remote proxy:** chuyển lời gọi sang một hệ thống khác, với hợp đồng khác về lỗi và độ trễ.

Không phải mọi cơ chế framework đều dùng proxy; annotation có thể được thực thi bằng interceptor, code generation, bytecode weaving hoặc các cách khác. Khi nói về hiện tượng **self-invocation không được intercept**, ta đang nói đến **mô hình proxy-based interception**.

### JDK dynamic proxy và class-based proxy

Trong hệ sinh thái Java, hai chiến lược thường gặp là:

| Kiểu proxy | Cách hoạt động khái quát | Điều cần kiểm tra |
| --- | --- | --- |
| **Interface-based proxy** | Đối tượng proxy triển khai interface và chuyển lời gọi tới target | Consumer cần gọi qua interface; phương thức chỉ có trên concrete class có thể không được proxy phơi ra |
| **Class-based proxy** | Tạo lớp con/biến thể để chặn các phương thức có thể override | `final` class/method và giới hạn visibility có thể làm phương thức không thể được chặn theo cơ chế subclass |

Trong Spring AOP, lựa chọn proxy dựa trên interface hay dựa trên lớp phụ thuộc cấu hình và điều kiện cụ thể. Không nên thiết kế service chỉ dựa vào giả định mọi phương thức đều có thể bị chặn. Đặc biệt, một phương thức `final` không thể được override bằng class-based proxy thông thường; một phương thức `private` không thể bị override từ lớp con.

Đừng trói mã nghiệp vụ vào việc đoán class runtime từ `getClass()` hay cast sang implementation cụ thể nếu dependency được khai báo qua interface: proxy có thể là một kiểu runtime khác target. Ngoài ra, **danh tính proxy không tự đồng nghĩa danh tính target**; với scoped proxy, target có thể thay đổi theo scope mặc dù tham chiếu proxy được giữ nguyên.

## 3. Self-invocation: gọi cùng một phương thức nhưng đi đường khác

Giả sử một service có phương thức gọi nội bộ đến phương thức cần transaction:

~~~java
// Ví dụ Spring mang tính minh họa; cần các dependency của Spring.
@Service
class InvoiceService {
    public void runBatch() {
        processOne(); // tương đương this.processOne()
    }

    @Transactional
    public void processOne() {
        // Lưu một hóa đơn.
    }
}
~~~

Khi một thành phần khác gọi `invoiceService.processOne()` **qua transactional proxy**, interceptor có cơ hội mở/đóng transaction theo cấu hình. Khi `runBatch()` của target gọi `this.processOne()`, lời gọi nội bộ **không đi qua proxy**, nên annotation `@Transactional` trên `processOne()` **không được áp dụng chỉ bởi lời gọi đó** trong proxy mode.

**Không nên diễn giải thành “chắc chắn không có transaction”.** Nếu `runBatch()` đã được gọi trong một transaction khác, `processOne()` có thể chạy trong transaction đang có; điều bị bỏ qua là **lớp interception riêng dành cho lời gọi nội bộ**. Điều tương tự đặc biệt quan trọng với yêu cầu `REQUIRES_NEW`, caching hoặc async.

~~~mermaid
flowchart TD
    External["Lời gọi từ bên ngoài"] --> Proxy["Proxy"]
    Proxy --> Target["Target.processOne(): interception áp dụng"]
    Other["Target.runBatch()"] --> Self["this.processOne()"]
    Self --> Bypass["Bỏ qua proxy: không áp dụng advice riêng cho lời gọi đó"]
~~~

Hướng xử lý là xem lại **ranh giới hành vi**, không tự động tìm mẹo để gọi proxy qua chính nó:

1. Nếu `runBatch()` thực sự phải chịu một transaction, khai báo transaction ở **entry point đúng** và hiểu phạm vi giao dịch.
2. Nếu `processOne()` cần chính sách riêng, tách chức năng sang một collaborator khác và inject collaborator đó qua constructor, để lời gọi đi qua ranh giới service.
3. Cân nhắc một API điều phối cấp trên thay vì gắn annotation lên nhiều phương thức nội bộ.
4. Chỉ dùng truy cập proxy từ bên trong, self-injection hoặc weaving khi thật sự hiểu kỹ thuật và đánh đổi; đó thường không phải lời giải mặc định cho thiết kế.

**Khả năng bị intercept phụ thuộc cơ chế thực thi.** Với AspectJ weaving hoặc các cơ chế không dựa trên proxy, hành vi self-invocation có thể khác. Khi cần kết luận về một annotation cụ thể, phải kiểm tra phương thức thực sự được framework intercept theo cấu hình hiện tại.

## 4. Proxy và phương thức bất đồng bộ, caching, security

Cùng một lỗi ranh giới có thể xuất hiện ở nhiều hành vi do framework bổ sung:

| Mục đích | Kỳ vọng khi gọi qua proxy | Rủi ro khi tự gọi trong target |
| --- | --- | --- |
| Transaction | Interceptor thiết lập/kết thúc transaction | Lời gọi nội bộ bỏ qua advice transaction của phương thức được gọi |
| Caching | Advice tra cache/ghi cache | Lời gọi nội bộ có thể chạy thẳng logic, không đi qua cache |
| Async | Advice chuyển công việc sang executor | Lời gọi nội bộ có thể chạy đồng bộ trên thread hiện tại |
| Security | Advice kiểm tra quyền trước khi gọi | Lời gọi nội bộ có thể bỏ qua kiểm tra ở proxy boundary |
| Metrics/retry | Advice đếm, đo, retry | Lời gọi nội bộ không chịu chính sách advice mong đợi |

Bảng trên áp dụng khi chức năng được thực thi **qua proxy**. Framework có thể dùng cơ chế khác hoặc quy định khác về vị trí chặn. Đừng coi annotation là lời hứa áp dụng ở mọi kiểu lời gọi.

Một hệ quả thiết kế: **nếu một chính sách bảo mật là bất biến bắt buộc của nghiệp vụ, không nên chỉ phụ thuộc vào giả định mọi lời gọi đều đi qua một proxy duy nhất**. Cần bảo đảm điểm kiểm tra quyền được đặt tại ranh giới có thể kiểm soát và được kiểm thử qua các đường gọi thực tế.

## 5. Scope: ai đang chia sẻ object nào?

**Scope** quy định khoảng thời gian hoặc ngữ cảnh mà container tái sử dụng instance. Các phạm vi điển hình:

| Scope | Cách hiểu | Lưu ý |
| --- | --- | --- |
| **Singleton của container** | Một instance cho một bean definition trong một container/application context, theo quy tắc framework | Không đồng nghĩa một instance trong toàn JVM, và không mặc định thread-safe |
| **Prototype/transient** | Container tạo instance mới khi có yêu cầu resolve tương ứng | Nếu inject một lần vào singleton, singleton thường giữ chính instance đó; không tự đổi mới theo từng lần gọi phương thức |
| **Request-scoped** | Cùng instance trong một request, khác instance giữa các request | Không phải mọi luồng bất đồng bộ đều tự có request context |
| **Session-/job-/custom-scoped** | Chia sẻ theo session hoặc đơn vị công việc được framework định nghĩa | Phải xác định scope bắt đầu/kết thúc, trách nhiệm đóng và isolation |

Một nhầm lẫn quen thuộc là **singleton + prototype**:

~~~java
// Minh họa ý tưởng: dependency được resolve một lần khi tạo consumer.
final class ReportScheduler {
    private final ReportWorker worker;

    ReportScheduler(ReportWorker worker) {
        this.worker = worker;
    }

    void run() {
        worker.execute();
    }
}
~~~

Nếu `ReportScheduler` sống toàn ứng dụng và `ReportWorker` được truyền vào constructor **một lần**, thì scheduler tiếp tục dùng **cùng tham chiếu worker** qua nhiều lần `run()`. Đăng ký worker là prototype ở container **không tự khiến mỗi lần gọi `run()` tạo worker mới**.

Khi cần **một worker cho mỗi lần chạy**, hãy thiết kế một factory/provider được inject:

~~~java
import java.util.Objects;
import java.util.function.Supplier;

final class ReportScheduler {
    private final Supplier<ReportWorker> workers;

    ReportScheduler(Supplier<ReportWorker> workers) {
        this.workers = Objects.requireNonNull(workers);
    }

    void run() {
        ReportWorker worker = Objects.requireNonNull(workers.get());
        worker.execute();
    }
}
~~~

Ở đây, factory/provider phải có **hợp đồng tạo mới theo job**, chứ không chỉ có kiểu `Supplier<ReportWorker>`. Nếu worker giữ tài nguyên, caller hoặc owner của job còn cần đóng nó đúng lúc. Provider có thể trả object dùng chung hoặc scoped object tùy cách cấu hình; bản thân `get()` không cam kết “mới”.

## 6. Scoped proxy: một tham chiếu, nhiều target theo ngữ cảnh

Giả sử một controller/service dùng chung toàn ứng dụng cần lấy `RequestContext` riêng của từng HTTP request. Tiêm trực tiếp target request-scoped vào singleton ở thời điểm tạo singleton có thể không phù hợp hoặc thất bại khi scope chưa hoạt động.

Một **scoped proxy** có thể giải quyết việc **trì hoãn lựa chọn target**: singleton giữ một proxy, và mỗi lần gọi phương thức, proxy tìm target của request hiện tại.

~~~mermaid
flowchart TB
    Singleton["Singleton ReportFacade"] --> P["RequestContext proxy (cùng reference)"]
    P -->|"Request A"| A["RequestContext target A"]
    P -->|"Request B"| B["RequestContext target B"]
~~~

Những điều quan trọng:

- **Proxy được inject có thể giữ cùng tham chiếu** trong singleton, nhưng target đằng sau có thể là **instance khác nhau ở request khác nhau**.
- Gọi proxy **ngoài scope hợp lệ** có thể gây lỗi hoặc hành vi riêng của framework; không được mặc định có request context ở một background thread.
- Lưu **target request-scoped** vào field singleton khác với lưu **proxy**. Nếu lấy target của request A rồi giữ lâu dài, có thể làm rò dữ liệu giữa request hoặc dùng object sau khi request kết thúc.
- Proxy không làm dữ liệu request trở thành thread-safe; khi async, cơ chế truyền scope/context cần được framework và ứng dụng xác định rõ.
- Dùng proxy khi cần **resolve theo scope hiện tại**. Nếu chỉ cần một giá trị như request ID, truyền nó làm **tham số phương thức** có thể đơn giản hơn.

Ví dụ Spring mang tính định hướng (không chạy bằng Java thuần):

~~~java
@Component
@Scope(
    value = WebApplicationContext.SCOPE_REQUEST,
    proxyMode = ScopedProxyMode.TARGET_CLASS
)
class RequestContext {
    String requestId() {
        // Giá trị gắn với request hiện tại.
        return "...";
    }
}
~~~

Trong Spring còn có các annotation và cách cấu hình request scope khác. Đoạn code chỉ minh họa cơ chế **proxyMode**, không mô tả đầy đủ cách lấy request ID thật hoặc bảo đảm có request đang hoạt động.

### Provider và scoped proxy khác nhau thế nào?

Scoped proxy khiến việc **lấy target** có thể được ẩn sau một phương thức gọi trên proxy. Provider như `ObjectProvider<RequestContext>` của Spring khiến hành động **lấy target** được thể hiện rõ ở thời điểm gọi `getObject()`.

Cả hai đều có thể phù hợp, nhưng không phải hoán đổi mà không xét ràng buộc:

- **Scoped proxy** thuận tiện khi consumer dùng một API thông thường và mọi lời gọi diễn ra trong scope.
- **Provider/factory** rõ ràng hơn khi cần chủ động quyết định lúc nào lấy hoặc tạo một dependency, hoặc cần xử lý trường hợp scope chưa có.
- **Truyền context vào phương thức** thường rõ nhất khi nó chỉ là dữ liệu của một lần chạy, không phải collaborator lâu dài.

Không nên dùng scoped proxy/provider chỉ để che vòng phụ thuộc A → B → A. Nếu quan hệ nghiệp vụ vẫn có vòng, việc khởi tạo qua container thành công không có nghĩa thiết kế đã hợp lý.

## 7. Lifecycle callback: lúc nào dependency thực sự sẵn sàng?

Ngoài constructor, container có thể hỗ trợ callback ở các giai đoạn **sau khởi tạo** và **trước hủy**. Trong hệ sinh thái Java, các annotation thường gặp là `@PostConstruct` và `@PreDestroy` (phụ thuộc thư viện/API của framework).

Một vòng đời khái quát của target do container quản lý có thể hình dung:

~~~mermaid
flowchart TD
    A["Tạo instance qua constructor"] --> B["Cấp dependency còn lại, nếu có"]
    B --> C["Callback / xử lý khởi tạo"]
    C --> D["Áp dụng post-processing, proxy theo cơ chế framework"]
    D --> E["Bàn giao object/proxy để sử dụng"]
    E --> F["Kết thúc scope hoặc đóng container"]
    F --> G["Callback hủy và giải phóng tài nguyên"]
~~~

**Đây là sơ đồ khái niệm, không phải thứ tự cứng cho mọi framework.** Thứ tự giữa callback, bean post-processor và tạo proxy có thể có những pha khác nhau; một số proxy có thể xuất hiện trong quá trình xử lý đặc biệt. Người viết code nên dựa trên **hợp đồng lifecycle của framework cụ thể**, không tự suy rằng mọi advice đã có hiệu lực ngay trong callback khởi tạo.

### Constructor: thiết lập invariant, chưa phải nơi dùng hết tính năng container

Đối với dependency **bắt buộc**, constructor injection cho phép kiểm tra `null` và giữ field `private final`:

~~~java
final class InvoiceService {
    private final InvoiceRepository repository;

    InvoiceService(InvoiceRepository repository) {
        this.repository = java.util.Objects.requireNonNull(repository);
    }
}
~~~

Trong trường hợp dependency được field/setter injection, constructor của target có thể chạy **trước** khi những field đó được container inject. Không gọi phương thức phụ thuộc vào field-injected collaborator từ constructor nếu chưa có bảo đảm phù hợp.

Đừng làm việc nặng, khởi tạo thread nền hoặc phát ra event từ constructor chỉ vì container đang tạo object: đối tượng có thể chưa hoàn tất wiring, và nếu bootstrap thất bại, tài nguyên đang chạy có thể khó được dọn.

### `@PostConstruct`: công việc khởi tạo có kiểm soát

Một callback sau khi dependency đã được cung cấp thường thích hợp để kiểm tra cấu hình hoặc chuẩn bị **tài nguyên do bean sở hữu**, khi đó là hợp đồng được framework hỗ trợ:

~~~java
// Ví dụ framework: cần import và dependency phù hợp.
@Component
class LookupAdapter {
    private final DataClient client;

    LookupAdapter(DataClient client) {
        this.client = client;
    }

    @PostConstruct
    void initialize() {
        // Kiểm tra hoặc chuẩn bị trạng thái cục bộ cần thiết.
    }
}
~~~

Cần tránh:

- Gọi business workflow hoặc truy cập hệ thống ngoài với tác dụng phụ khó retry mà không có chính sách rõ ràng.
- Gọi một phương thức cần `@Transactional`, `@Async` hoặc `@Cacheable` bằng `this.method()` rồi mặc định proxy sẽ intercept.
- Giả định tất cả listener/bean khác đã sẵn sàng ở đúng thời điểm callback của bean hiện tại chạy.
- Tạo thread mà không quản lý cách dừng và liên hệ với scope.

Nếu khởi tạo cần dựa vào **toàn bộ ứng dụng đã sẵn sàng**, có thể cần một sự kiện lifecycle cao hơn (ví dụ application-ready hook) theo framework, thay vì callback riêng của từng bean.

### `@PreDestroy`: thu hồi đúng tài nguyên được sở hữu

Một bean tạo thread pool, socket, client hoặc timer thường cần xác định **ai đóng** và **khi nào**:

~~~java
// Minh họa framework; không phải chương trình Java thuần độc lập.
@Component
class PollingAdapter {
    private final ManagedScheduler scheduler;

    @PreDestroy
    void shutdown() {
        // Chỉ đóng nếu bean thật sự là owner của scheduler.
    }
}
~~~

`@PreDestroy` phụ thuộc scope và cơ chế quản lý của framework. Ví dụ trong Spring, việc tự động gọi destruction callback cho **prototype-scoped bean** không giống singleton: container thường tạo và bàn giao prototype, còn client cần tự quản lý hủy/giải phóng sau đó. Không được mặc định mọi instance do container tạo đều có callback hủy được gọi tự động.

Nếu dependency được **inject để sử dụng** nhưng do application runtime hoặc bean khác sở hữu, consumer **không nên tự đóng nó** chỉ vì consumer đang bị hủy. Việc đóng nhầm tài nguyên dùng chung có thể gây lỗi cho các đối tượng còn sống.

## 8. Kết hợp proxy, scope và lifecycle: các trường hợp dễ sai

Ba cơ chế có thể tác động lên nhau.

| Tình huống | Điều tưởng đúng | Điều thực tế cần xác minh |
| --- | --- | --- |
| Singleton được inject proxy đến request bean | “Singleton giữ một request bean mãi” | Tham chiếu proxy có thể giữ nguyên nhưng target thay theo request |
| Singleton giữ concrete request bean lấy một lần | “Container tự đổi target” | Nếu không có scoped proxy/provider đúng cách, singleton có thể giữ một instance cũ |
| Method `@Transactional` gọi bằng `this` | “Annotation luôn tạo transaction” | Trong proxy mode, self-invocation không đi qua transactional advice |
| `@PostConstruct` gọi method có advice | “Bean đã được framework quản lý nên advice chắc chắn chạy” | Pha initialization có thể chưa ở ranh giới proxy như lúc client gọi |
| Bean prototype được inject vào singleton một lần | “Prototype nghĩa là mới mỗi lần gọi method” | Singleton giữ tham chiếu đã inject; muốn mới theo thao tác phải dùng factory/provider |
| Bean đóng container nhưng tài nguyên còn được dùng ở thread khác | “Callback hủy chỉ chạy khi hết mọi lời gọi” | Shutdown và tác vụ đồng thời cần điều phối rõ |
| Request scope được dùng trong background task | “Task luôn tự có request context” | Scope/context propagation phải có cơ chế cụ thể, có thể không tồn tại |
| Scoped proxy có identity ổn định | “Proxy = cùng target ở mọi request” | Identity của proxy và target là hai chuyện khác nhau |

Một ví dụ nguy hiểm hơn: business service singleton giữ một `RequestContext` mutable của request đầu tiên. Kể cả có đồng bộ hóa mọi phương thức, **lỗi scope** vẫn tồn tại vì object về mặt nghiệp vụ gắn với request sai. Thread-safety không thay thế quyết định đúng về lifetime.

## 9. Thực hành Java 17: decorator proxy, request scope và callback thủ công

Để nhìn rõ cơ chế, ta tự viết một chương trình Java thuần gồm:

- Một **ReportStore** dùng chung, có `start()` và `close()` để minh họa callback khởi tạo/hủy.
- Một **RequestContext** chỉ hợp lệ khi unit/request còn mở.
- Một **ReportService** nhận dependencies qua constructor.
- Một **TracingProxy** triển khai cùng interface, chặn lời gọi từ bên ngoài nhưng **không chặn lời gọi `this.render(...)` bên trong target**.
- Một **RequestScope** tạo proxy theo request, trả cùng proxy trong scope và khác proxy giữa các scope.
- Một composition root tạo store dùng chung, mở/đóng request scope và đóng store khi kết thúc.

**Đây là mô phỏng bằng Java thuần, không phải bản cài đặt Spring AOP hay request scope của một framework thật.** Nó cho phép quan sát những nguyên lý có liên quan trước khi học cú pháp của DI container.

Lưu toàn bộ mã dưới đây vào `Main.java`; yêu cầu **Java 17 trở lên**:

~~~java
import java.util.Objects;

// Hợp đồng hạ tầng có phạm vi toàn ứng dụng trong ví dụ console.
interface ReportStore {
    String save(String requestId, String reportName);
}

// Tài nguyên cần được khởi tạo và đóng bởi composition root.
final class LifecycleReportStore implements ReportStore, AutoCloseable {
    private boolean started;
    private boolean closed;
    private int savedCount;

    void start() {
        if (started || closed) {
            throw new IllegalStateException("Store cannot start");
        }
        started = true;
        System.out.println("STORE STARTED");
    }

    @Override
    public String save(String requestId, String reportName) {
        if (!started || closed) {
            throw new IllegalStateException("Store is not active");
        }
        savedCount++;
        return requestId + ":" + reportName + ":" + savedCount;
    }

    int savedCount() {
        return savedCount;
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            System.out.println("STORE CLOSED");
        }
    }
}

// Dữ liệu có vòng đời ngắn; bị từ chối sử dụng khi request đã kết thúc.
final class RequestContext implements AutoCloseable {
    private final String requestId;
    private boolean active = true;

    RequestContext(String requestId) {
        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException("Invalid request id");
        }
        this.requestId = requestId;
    }

    String id() {
        if (!active) {
            throw new IllegalStateException("Request scope is closed");
        }
        return requestId;
    }

    @Override
    public void close() {
        active = false;
    }
}

interface ReportOperations {
    String render(String reportName);
    String renderTwice(String reportName);
}

// Target nghiệp vụ: không biết proxy hoặc container.
final class ReportService implements ReportOperations {
    private final RequestContext context;
    private final ReportStore store;

    ReportService(RequestContext context, ReportStore store) {
        this.context = Objects.requireNonNull(context, "context");
        this.store = Objects.requireNonNull(store, "store");
    }

    @Override
    public String render(String reportName) {
        if (reportName == null || reportName.isBlank()) {
            throw new IllegalArgumentException("Invalid report name");
        }
        return store.save(context.id(), reportName);
    }

    @Override
    public String renderTwice(String reportName) {
        // Gọi vào chính target, KHÔNG đi qua TracingProxy.
        return render(reportName) + " | " + render(reportName);
    }
}

// Decorator đóng vai trò proxy minh họa: chặn lời gọi bên ngoài.
final class TracingProxy implements ReportOperations {
    private final ReportOperations target;
    private int interceptedCalls;

    TracingProxy(ReportOperations target) {
        this.target = Objects.requireNonNull(target, "target");
    }

    int interceptedCalls() {
        return interceptedCalls;
    }

    @Override
    public String render(String reportName) {
        interceptedCalls++;
        System.out.println("TRACE render");
        return target.render(reportName);
    }

    @Override
    public String renderTwice(String reportName) {
        interceptedCalls++;
        System.out.println("TRACE renderTwice");
        return target.renderTwice(reportName);
    }
}

// Mỗi RequestScope cấp cùng proxy; request mới cấp proxy khác.
final class RequestScope implements AutoCloseable {
    private final RequestContext context;
    private final ReportStore store;
    private ReportOperations reportProxy;
    private boolean closed;

    RequestScope(String requestId, ReportStore store) {
        this.context = new RequestContext(requestId);
        this.store = Objects.requireNonNull(store, "store");
    }

    ReportOperations reports() {
        if (closed) {
            throw new IllegalStateException("Scope is closed");
        }
        if (reportProxy == null) {
            ReportService target = new ReportService(context, store);
            reportProxy = new TracingProxy(target);
        }
        return reportProxy;
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            context.close();
            reportProxy = null;
        }
    }
}

// Composition root: quản lý tài nguyên ứng dụng và từng scope riêng.
public class Main {
    public static void main(String[] args) {
        try (LifecycleReportStore store = new LifecycleReportStore()) {
            // Tương tự init callback, do bootstrap gọi rõ ràng.
            store.start();

            ReportOperations fromFirstRequest;

            try (RequestScope first = new RequestScope("REQ-A", store)) {
                fromFirstRequest = first.reports();

                System.out.println(
                        "Same proxy in A: "
                                + (fromFirstRequest == first.reports()));

                System.out.println(fromFirstRequest.render("daily"));
                System.out.println(
                        fromFirstRequest.renderTwice("weekly"));

                System.out.println(
                        "Intercepted in A: "
                        + ((TracingProxy) fromFirstRequest)
                                .interceptedCalls());
            }

            try (RequestScope second = new RequestScope("REQ-B", store)) {
                ReportOperations fromSecondRequest = second.reports();

                System.out.println(
                        "Different across scopes: "
                        + (fromFirstRequest != fromSecondRequest));

                System.out.println(
                        fromSecondRequest.render("monthly"));
            }

            System.out.println("Saved reports: " + store.savedCount());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Main.java
java Main
~~~

Đầu ra dự kiến:

~~~text
STORE STARTED
Same proxy in A: true
TRACE render
REQ-A:daily:1
TRACE renderTwice
REQ-A:weekly:2 | REQ-A:weekly:3
Intercepted in A: 2
Different across scopes: true
TRACE render
REQ-B:monthly:4
Saved reports: 4
STORE CLOSED
~~~

### Phân tích những gì đã xảy ra

1. **Lifecycle:** composition root tạo store và gọi `start()` trước khi lắp service; `try-with-resources` đóng store cuối chương trình. Trong framework, callback khởi tạo/hủy có thể được điều phối bằng cơ chế lifecycle.
2. **Constructor injection:** `ReportService` yêu cầu `RequestContext` và `ReportStore` ngay tại constructor. Service không biết chúng được tạo bằng tay hay từ container.
3. **Scope:** `RequestScope.reports()` trả cùng một proxy khi được gọi nhiều lần trong request A; scope B tạo proxy/target riêng. `ReportStore` vẫn là đối tượng dùng chung ở cả hai scope.
4. **Proxy boundary:** `fromFirstRequest.render("daily")` đi qua `TracingProxy` nên tăng bộ đếm chặn một lần.
5. **Self-invocation:** `renderTwice("weekly")` chỉ đi qua proxy **một lần** ở entry call. Hai lời gọi `render(...)` nằm trong `ReportService`, nên không chạy `TracingProxy.render`; tổng số thao tác lưu tăng thêm hai nhưng số lượt intercept chỉ tăng thêm một.
6. **Tài nguyên và ranh giới scope:** request mới không tự giữ tham chiếu tới target request cũ. Store được đóng sau các request, không bị đóng khi một request kết thúc.

**Lưu ý:** ví dụ tạo **proxy khác cho từng request**. Một scoped proxy do container cung cấp có thể dùng **cùng proxy được inject vào singleton** nhưng đổi **target theo request**, như mô tả ở phần 6. Mô hình Java thuần ở đây tập trung vào cùng identity trong một scope và thao tác ủy quyền; không sao chép chính xác toàn bộ hành vi scoped proxy của Spring.

Ví dụ dùng trạng thái mutable không có đồng bộ và chủ động chạy **tuần tự một luồng**. Không thể suy từ ví dụ rằng `LifecycleReportStore`, `RequestScope` hay `TracingProxy` an toàn nếu nhiều thread truy cập đồng thời.

## 10. Kiểm thử: nhận diện boundary, identity và lifecycle

Có thể viết kiểm thử không cần DI framework để chứng minh cơ chế proxy và scope dự kiến, rồi kiểm thử tích hợp riêng để xác nhận cấu hình framework thực sự tạo đúng proxy/scoped target.

Lưu đoạn sau vào `FrameworkDiSemanticsTest.java` trong cùng thư mục với `Main.java`:

~~~java
public class FrameworkDiSemanticsTest {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        LifecycleReportStore store = new LifecycleReportStore();

        // Store phải được init trước khi dùng.
        boolean beforeStartRejected = false;
        try {
            store.save("R", "report");
        } catch (IllegalStateException expected) {
            beforeStartRejected = true;
        }
        check(beforeStartRejected, "Store must reject use before init");

        store.start();

        ReportOperations oldProxy;
        try (RequestScope one = new RequestScope("TEST-A", store)) {
            oldProxy = one.reports();
            check(oldProxy == one.reports(),
                    "Within one scope the proxy must be identical");

            TracingProxy trace = (TracingProxy) oldProxy;

            String result = oldProxy.renderTwice("summary");
            check(result.equals(
                    "TEST-A:summary:1 | TEST-A:summary:2"),
                    "Target must perform two writes");

            // Self-invocation: 2 target calls nhưng 1 proxy entry.
            check(trace.interceptedCalls() == 1,
                    "Inner render() must bypass this decorator");

            check(store.savedCount() == 2,
                    "Two target saves expected");
        }

        // Bên ngoài scope, target cũ không còn hợp lệ.
        boolean expiredRejected = false;
        try {
            oldProxy.render("late");
        } catch (IllegalStateException expected) {
            expiredRejected = true;
        }
        check(expiredRejected, "Expired request context must fail");

        try (RequestScope two = new RequestScope("TEST-B", store)) {
            ReportOperations next = two.reports();
            check(next != oldProxy,
                    "Different scopes must not share this proxy");
            check(next.render("new").equals("TEST-B:new:3"),
                    "Second scope must have distinct request id");
        }

        check(store.savedCount() == 3,
                "Application-scoped store must retain all writes");

        store.close();

        boolean afterCloseRejected = false;
        try {
            store.save("R", "report");
        } catch (IllegalStateException expected) {
            afterCloseRejected = true;
        }
        check(afterCloseRejected, "Store must reject use after close");

        System.out.println("PASS");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Main.java FrameworkDiSemanticsTest.java
java FrameworkDiSemanticsTest
~~~

Dòng kết thúc kỳ vọng: `PASS` (trước đó sẽ có dòng `STORE STARTED`, một số dòng `TRACE ...` và `STORE CLOSED`).

Test xác minh:

- Store chưa khởi tạo hoặc đã đóng không được dùng.
- Một request nhận lại cùng proxy; request khác nhận proxy khác trong mô hình minh họa.
- Một lời gọi `renderTwice` tạo hai thao tác target nhưng chỉ một lời chặn ở entry proxy.
- Tham chiếu target thuộc request đã đóng không được dùng tiếp.
- Store chung giữ dữ liệu qua nhiều request và được đóng riêng.

**Giới hạn:** test này kiểm tra các lớp **tự viết bằng Java thuần**; nó không chứng minh Spring sẽ cấu hình đúng `@Transactional`, `@Async`, request scope hoặc `@PostConstruct`. Những hành vi phụ thuộc framework cần integration test với container thực, scope thực và interceptor đúng cấu hình.

## 11. Kiểm thử DI trong framework: phân tầng theo câu hỏi

Nên tách ba loại kiểm thử để tránh vừa chậm vừa khó xác định nguyên nhân lỗi.

| Loại kiểm thử | Câu hỏi chính | Cách làm |
| --- | --- | --- |
| **Unit test nghiệp vụ** | Service tính toán/điều phối đúng khi dependency đáp ứng hợp đồng? | Tạo service bằng constructor, cấp fake; **không cần container** |
| **Wiring/lifecycle test** | Bean có được đăng ký đúng, scope, callback và resource owner có hoạt động? | Khởi động context thử nghiệm, resolve bean, mở/đóng scope theo framework |
| **Proxy/AOP integration test** | Transaction/cache/async/security advice có áp dụng cho đường gọi thật? | Gọi qua bean/proxy do container cấp; kiểm tra tác dụng có thể quan sát |

Một lưu ý quan trọng: nếu unit test tạo target bằng `new Service(...)` rồi gọi method có `@Transactional`, test đó **không kiểm chứng transaction advice**. Muốn xác nhận interception, phải lấy object từ container được cấu hình thật hoặc mô phỏng tường minh behavior cần kiểm tra, và gọi qua đúng ranh giới proxy.

Đối với scope, nên có test có **ít nhất hai request/job** để xác nhận không giữ state request trước đó. Đối với vòng đời, test cả khởi tạo thành công, lỗi giữa quá trình bootstrap và shutdown; đồng thời xác minh tài nguyên dùng chung không bị consumer đóng sớm.

## 12. Những lỗi thường gặp khi áp dụng proxy, scope và callback

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Method có `@Transactional` nhưng không tạo transaction riêng như mong đợi | Self-invocation bỏ qua advice trong proxy mode | Kiểm tra call graph và entry point đi qua proxy |
| `@Cacheable` không cache khi gọi trong cùng class | Lời gọi nội bộ không đi qua proxy | Tách ranh giới method/bean hoặc kiểm tra cơ chế interception |
| `@Async` vẫn chạy đồng bộ | Gọi nội bộ hoặc executor/advice không được kích hoạt | Kiểm tra proxy, cấu hình và thread thực thi |
| Dependency được inject nhưng `getClass()` khác implementation | Container cung cấp proxy | Dùng interface/hợp đồng, tránh cast vào concrete khi không cần |
| Method `final` không được class-based proxy chặn | Không thể override phương thức đó | Đọc quy tắc proxy và chọn điểm interception phù hợp |
| Singleton giữ request data cũ | Inject nhầm target scope ngắn hoặc lưu lại target | Dùng scoped proxy/provider hoặc truyền dữ liệu request |
| Prototype worker vẫn là một instance khi scheduler chạy nhiều lần | Prototype được inject một lần vào singleton | Inject factory/provider và gọi tại đầu mỗi job |
| `@PostConstruct` gọi method có advice nhưng behavior không xuất hiện | Callback không đi qua proxy như external call | Tránh dựa vào interception trong init callback |
| `@PreDestroy` không chạy cho object dùng xong | Đối tượng không do container quản lý destruction hoặc thuộc prototype scope | Xác định owner và cơ chế dispose của scope |
| Background thread không lấy được request bean | Scope không được truyền sang thread | Thiết kế context propagation hoặc truyền dữ liệu rõ ràng |
| Tắt app rồi mới có tác vụ truy cập client | Shutdown thiếu điều phối các tác vụ đang chạy | Dừng nhận việc, chờ/cancel phù hợp, sau đó đóng resource |

## 13. Checklist thiết kế và vận hành

Trước khi chuyển một service Java thuần vào DI framework, nên kiểm tra:

1. **Hợp đồng constructor:** những dependency bắt buộc có hiện rõ và được kiểm tra `null` không?
2. **Ranh giới proxy:** các phương thức cần transaction/cache/async/security có được gọi thông qua object do container cấp không?
3. **Self-invocation:** có phương thức nào gọi `this.method()` rồi kỳ vọng advice của method đó không?
4. **Kiểu proxy:** interface-based hay class-based? Có `final`, `private`, cast concrete hoặc phụ thuộc `getClass()` không?
5. **Scope mong muốn:** đối tượng dùng chung, theo request, theo job hay tạo mới mỗi lần resolve? Có dependency ngắn hạn bị giữ trong singleton không?
6. **Danh tính proxy/target:** đang so sánh `==` trên proxy hay trên target? Kết quả có thực sự thể hiện scope cần kiểm chứng không?
7. **Provider:** `get()` có hứa tạo mới hay resolve theo scope? Ai đóng object được trả về?
8. **Khởi tạo:** callback có dùng dependency trước khi wiring xong, mở transaction ngầm hoặc kích hoạt thread quá sớm không?
9. **Hủy:** ai sở hữu và đóng tài nguyên, khi nào scope kết thúc, prototype có cơ chế cleanup gì?
10. **Bất đồng bộ:** request context, transaction context và tài nguyên có được truyền đúng ranh giới thread không?
11. **Kiểm thử:** unit test không container cho nghiệp vụ; integration test có container cho proxy/scope/lifecycle.
12. **Chẩn đoán:** nếu hành vi khác giữa môi trường test và production, kiểm tra object được gọi thực tế, scope, proxy strategy và cấu hình callback.

### Câu hỏi tự kiểm tra

**Tình huống A:** Controller được inject `InvoiceService` từ Spring rồi gọi `invoiceService.processOne()` qua proxy. Tại sao lời gọi `this.processOne()` từ `runBatch()` có thể khác?

Vì trong mô hình proxy-based AOP, lời gọi trực tiếp từ controller **đi qua proxy**, còn lời gọi `this` trong target **không đi qua proxy**. Interceptor gắn với `processOne` vì vậy không tự chạy ở đường gọi nội bộ.

**Tình huống B:** `ReportScheduler` singleton nhận một `ReportWorker` prototype qua constructor. Mỗi lần scheduler gọi `worker.execute()` có tự nhận worker mới không?

**Không.** Constructor được gọi một lần cho scheduler đã giữ tham chiếu. Muốn worker mới mỗi job phải dùng một factory/provider có hợp đồng tạo mới tại đầu job.

**Tình huống C:** Một singleton được inject request-scoped proxy. Hai request thấy cùng proxy `==` nên có thể kết luận target cũng cùng một instance?

**Không.** Proxy có thể là cùng tham chiếu nhưng resolve sang các target khác nhau theo request.

**Tình huống D:** Trong `@PostConstruct`, bean gọi phương thức khác có `@Transactional`. Có thể mặc định giao dịch chắc chắn được thiết lập theo annotation ấy không?

**Không.** Callback khởi tạo và lời gọi nội bộ có thể không đi qua ranh giới proxy cần thiết. Hãy đưa công việc cần transaction sang một entry point được gọi qua proxy sau khi initialization phù hợp, hoặc chọn cơ chế giao dịch rõ ràng.

**Tình huống E:** Một bean request-scoped mở tài nguyên nhưng bị giữ lại sau khi request kết thúc. Có thể tiếp tục dùng vì object vẫn còn trong heap?

**Không nên.** Object còn được tham chiếu không có nghĩa scope/lifecycle hợp lệ. Cần giải phóng theo owner và không dùng dependency đã hết scope.

**Tình huống F:** Unit test bằng `new Service(fake)` xác nhận logic đúng, nhưng production có lỗi cache. Test có sai không?

Không nhất thiết. Unit test xác nhận **logic nghiệp vụ**, không kiểm tra **caching advice**. Cần test riêng gọi service **qua proxy/container** và quan sát hành vi cache trong cấu hình thật.

## Ghi nhớ

**Proxy quyết định đường đi của lời gọi; scope quyết định target nào được dùng và trong bao lâu; lifecycle callback quyết định lúc nào đối tượng được chuẩn bị và thu hồi.** Trong DI framework, ba cơ chế này có thể khiến tham chiếu nhận từ container hoạt động khác với target được tạo trực tiếp bằng `new`. Hãy giữ dependency bắt buộc tường minh qua **constructor injection**, quản lý binding tại **composition root**, không dựa vào advice khi gọi bằng `this` trong proxy mode, và bảo đảm object sống đúng scope. Kiểm thử nghiệp vụ bằng Java thuần rồi kiểm thử proxy, scope và callback trên container thật để xác nhận hành vi của framework.
