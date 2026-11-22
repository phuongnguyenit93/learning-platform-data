# API của host

## 1. API của host trong tích hợp ứng dụng DSL là gì?

Trong một ứng dụng có nhúng ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL), **host** là ứng dụng hoặc nền tảng chứa DSL runtime, compiler, editor hay plugin engine. Host có thể là một IDE, server, desktop application, workflow platform hoặc một dịch vụ nghiệp vụ.

**API của host (host API)** là tập hợp interface, service, context, event và capability mà host cung cấp để chương trình DSL, plugin hoặc extension tương tác với ứng dụng chủ.

Ví dụ, một workflow DSL được nhúng trong ứng dụng quản lý đơn hàng có thể cần:

- Đọc thông tin đơn hàng.
- Kiểm tra quyền của người dùng.
- Ghi một quyết định vào hệ thống.
- Phát event để các thành phần khác xử lý.
- Ghi log và báo tiến độ.
- Truy cập cấu hình hoặc tài nguyên được host quản lý.

Thay vì cho mã DSL truy cập trực tiếp database, file system hoặc object nội bộ của ứng dụng, host công bố các capability có kiểm soát:

~~~text
DSL source
    |
    v
Parser / Compiler
    |
    v
DSL runtime
    |
    v
Host API boundary
    |
    +---- Order service
    +---- Authorization service
    +---- Event publisher
    +---- Audit service
    +---- Resource resolver
~~~

Host API là hợp đồng giữa DSL runtime và ứng dụng chủ. Nó cho phép DSL thực hiện công việc trong môi trường thực tế, đồng thời giúp host kiểm soát quyền, vòng đời, dữ liệu và tác dụng phụ.

## 2. Vai trò của host và DSL runtime

Host và DSL runtime có trách nhiệm khác nhau.

| Thành phần | Trách nhiệm chính |
|---|---|
| Host application | Quản lý người dùng, tài nguyên, cấu hình và dịch vụ của ứng dụng |
| DSL compiler | Phân tích, kiểm tra kiểu và biên dịch source DSL |
| DSL runtime | Thực thi chương trình hoặc process đã biên dịch |
| Host API | Cung cấp capability cho runtime và extension |
| Adapter | Chuyển contract DSL sang API/service cụ thể của host |
| Plugin/extension | Bổ sung cú pháp, hàm, validator hoặc hành vi được cho phép |

Host không nhất thiết phải biết chi tiết mọi câu lệnh DSL. Runtime cũng không nên phụ thuộc vào implementation nội bộ của ứng dụng chủ.

### 2.1 Host chịu trách nhiệm gì?

Host thường chịu trách nhiệm:

- Khởi tạo và đóng runtime.
- Cấp configuration và service.
- Xác thực danh tính và kiểm tra quyền.
- Quản lý transaction hoặc resource scope.
- Cung cấp clock, logging và tracing.
- Phát và nhận event.
- Quản lý cancellation, timeout và quota.
- Cô lập execution context giữa các request hoặc tenant.
- Lưu kết quả và audit theo chính sách của ứng dụng.

### 2.2 DSL runtime chịu trách nhiệm gì?

Runtime chịu trách nhiệm:

- Chạy semantics đã định nghĩa của DSL.
- Quản lý variable, scope và evaluation.
- Gọi capability qua host API contract.
- Trả kết quả và diagnostic theo kiểu đã công bố.
- Tuân thủ cancellation và execution budget.

Runtime không nên tự suy đoán quyền truy cập chỉ từ tên hàm hoặc biến trong source DSL.

## 3. Xác định ranh giới host API

Trước khi thiết kế interface, cần xác định những phần nào được phép đi qua ranh giới.

Một số ví dụ:

| Nhu cầu của DSL | Host API phù hợp |
|---|---|
| Tra cứu đơn hàng | OrderReader |
| Cập nhật trạng thái | OrderCommands |
| Kiểm tra quyền | Authorization |
| Gửi thông báo | NotificationPublisher |
| Ghi audit | AuditSink |
| Lấy thời gian hiện tại | Clock |
| Đọc file được cấp quyền | ResourceResolver |
| Phát event | EventPublisher |

### 3.1 API theo capability

Nên cấp cho runtime những capability cụ thể cần thiết. Ví dụ, một policy DSL chỉ cần đọc thông tin đơn hàng có thể nhận OrderReader mà không cần OrderWriter.

### 3.2 API theo miền nghiệp vụ

Tên interface nên phản ánh domain, chẳng hạn PaymentService, CustomerDirectory hoặc InventoryReservation. Tránh công bố một interface tổng quát như ApplicationUtils với hàng trăm method không liên quan.

### 3.3 Giữ implementation phía sau interface

Host có thể thay database, message broker hoặc framework nội bộ mà không đổi DSL contract nếu interface công khai vẫn giữ nguyên semantics.

### 3.4 Tránh rò rỉ implementation

Không nên để API công khai trả về ORM entity, servlet request, UI widget hoặc object nội bộ của framework nếu DSL runtime không cần các chi tiết đó. Dùng DTO hoặc domain value object ổn định.

## 4. Thiết kế interface của host API

Một host API nên nhỏ, có kiểu rõ, mô tả đúng hành vi và dễ mock khi kiểm thử.

Ví dụ:

~~~java
public interface OrderReader {
    Optional<OrderView> findById(OrderId id);
}

public interface OrderCommands {
    OrderUpdateResult changeStatus(
        OrderId id,
        OrderStatus newStatus,
        CommandContext context
    );
}
~~~

### 4.1 Interface nhỏ và tập trung

Tách thao tác đọc và ghi giúp cấp quyền theo nhu cầu. Interface nhỏ cũng giúp test doubles đơn giản và hạn chế dependency.

### 4.2 Dùng kiểu miền

OrderId, Money, CustomerId và OrderStatus diễn đạt ý nghĩa rõ hơn string hoặc number chung. Kiểu miền giúp compiler và API phát hiện nhầm lẫn sớm.

### 4.3 Trả kết quả có kiểu

Một thao tác nghiệp vụ có thể trả:

~~~java
public sealed interface OrderUpdateResult {
    record Updated(OrderView order) implements OrderUpdateResult {}
    record Rejected(String reasonCode) implements OrderUpdateResult {}
    record NotFound() implements OrderUpdateResult {}
    record Conflict(long currentVersion) implements OrderUpdateResult {}
}
~~~

Kiểu kết quả tường minh giúp DSL xử lý các outcome đã biết. Lỗi hạ tầng có thể được biểu diễn bằng exception hoặc error result theo contract thống nhất.

### 4.4 Không trả null mơ hồ

Nếu không tìm thấy tài nguyên, dùng Optional hoặc result type. Null không nên đồng thời có nghĩa không tìm thấy, không có quyền, dữ liệu thiếu và service lỗi.

### 4.5 API đồng bộ và bất đồng bộ

Nếu thao tác có thể chờ I/O lâu, host API có thể dùng CompletionStage, Future hoặc abstraction async riêng:

~~~java
CompletionStage<Optional<OrderView>> findById(OrderId id);
~~~

Runtime cần định nghĩa cách await, cancellation và timeout cho lời gọi bất đồng bộ.

## 5. Host context và execution context

DSL runtime thường cần một context cho mỗi lần thực thi. Context chứa thông tin về lần chạy hiện tại và những capability được phép sử dụng.

Ví dụ:

~~~java
public interface HostContext {
    String executionId();
    String tenantId();
    Principal principal();
    Clock clock();
    CancellationToken cancellation();
    <T> T service(Class<T> serviceType);
}
~~~

Đây là interface minh họa; API thực tế có thể dùng dependency injection thay cho service lookup.

### 5.1 Execution identity

executionId định danh một lần chạy DSL. Nó giúp liên kết log, trace, task, event và audit record.

### 5.2 Tenant context

Ứng dụng nhiều tenant cần giữ tenant identity xuyên suốt execution. Runtime không được dùng context của tenant khác khi tái sử dụng worker hoặc thread.

### 5.3 Principal

Principal biểu diễn người dùng hoặc service identity mà lần chạy đại diện. Host cần phân biệt người khởi tạo execution với identity mà handler dùng để truy cập tài nguyên.

### 5.4 Clock

Tiêm Clock giúp DSL có thời gian nhất quán và kiểm thử được. Không nên để mỗi hàm tự gọi system clock nếu kết quả cần tái lập.

### 5.5 Cancellation token

Runtime có thể kiểm tra token trước hoặc trong thao tác dài. Host cần định nghĩa task nào hỗ trợ cancellation và cách báo trạng thái khi bị hủy.

### 5.6 Context scope

Context nên có phạm vi rõ: application, tenant, session, process hoặc request. Không lưu dữ liệu request-specific trong singleton service.

## 6. Cung cấp service cho DSL runtime

Host cần một cơ chế để runtime tìm và gọi service.

### 6.1 Constructor injection

Với số service cố định, constructor injection là cách đơn giản và dễ kiểm tra:

~~~java
public final class WorkflowRuntime {
    private final OrderReader orders;
    private final Authorization authorization;

    public WorkflowRuntime(
        OrderReader orders,
        Authorization authorization
    ) {
        this.orders = orders;
        this.authorization = authorization;
    }
}
~~~

### 6.2 Service registry

Một registry có thể đăng ký capability theo type hoặc ID:

~~~java
registry.register(OrderReader.class, orderReader);
registry.register(Authorization.class, authorization);
~~~

Registry hữu ích khi host cho phép extension hoặc service thay đổi theo tenant. Cần kiểm tra service type, scope và quyền trước khi cấp.

### 6.3 Dependency injection container

Host có thể dùng DI container sẵn có để tạo adapter và runtime. Tuy nhiên, không nên để DSL runtime phụ thuộc trực tiếp vào container cụ thể nếu muốn giữ tính portable.

### 6.4 Không dùng global service locator tùy tiện

Global static registry khiến dependency khó nhìn thấy, khó cô lập trong test và dễ rò rỉ giữa execution. Nếu cần registry, hãy gắn nó vào context hoặc runtime instance có lifecycle rõ.

### 6.5 Service scope

Service có thể là singleton, tenant-scoped, session-scoped hoặc execution-scoped. Chọn scope phù hợp với state và thread safety của service.

## 7. Ánh xạ DSL function tới host service

DSL thường biểu diễn lời gọi host API dưới dạng function hoặc action.

Ví dụ source DSL:

~~~text
let order = host.orders.find(orderId)

if order.status == "PENDING" {
  host.orders.approve(order.id)
}
~~~

Compiler có thể resolve host.orders.find thành một function descriptor đã đăng ký. Runtime gọi implementation thông qua một adapter.

~~~text
DSL call
   |
   v
Symbol resolution
   |
   v
Function descriptor
   |
   v
Runtime adapter
   |
   v
Host service
~~~

### 7.1 Function descriptor

Descriptor có thể chứa:

- Tên hoặc ID ổn định.
- Kiểu tham số.
- Kiểu kết quả.
- Capability cần thiết.
- Tính thuần hoặc side effect.
- Async/sync behavior.
- Timeout và cancellation support.
- Phiên bản contract.

### 7.2 Static type checking

Nếu function nhận OrderId, compiler nên từ chối truyền CustomerId. Kiểm tra trước execution giúp phát hiện lỗi cấu hình sớm và cung cấp source location.

### 7.3 Overload resolution

Nếu có nhiều function cùng tên, DSL cần quy tắc overload rõ ràng. Không nên chọn theo reflection order hoặc cách ép kiểu ngầm không xác định.

### 7.4 Host namespace

Namespace như host.orders hoặc app.notifications giúp phân biệt function tích hợp với function built-in của ngôn ngữ.

### 7.5 Không cho phép gọi tùy ý

Không nên cho source DSL truyền tên class hoặc method bất kỳ để reflection gọi trực tiếp. Chỉ những function đã được đăng ký và cấp quyền mới được resolve.

## 8. Dữ liệu qua host API

Host API cần xác định cách chuyển dữ liệu giữa DSL type system và domain model.

### 8.1 DTO và domain object

DTO là cấu trúc dữ liệu trao đổi. Domain object có thể chứa behavior, invariant và dependency nội bộ. Thường nên trả DTO hoặc immutable view thay vì để DSL sửa trực tiếp entity đang được quản lý bởi ORM.

### 8.2 Mapping

Adapter chịu trách nhiệm chuyển:

- DSL primitive sang kiểu miền.
- DSL record sang request DTO.
- Host result sang DSL value.
- Host error sang error type của runtime.

### 8.3 Null và missing

Contract phải phân biệt field không có, null và giá trị mặc định nếu chúng có semantics khác nhau.

### 8.4 Decimal và tiền tệ

Không nên dùng floating-point cho phép tính tiền cần chính xác. Dùng Money hoặc decimal type có currency, scale và rounding policy.

### 8.5 Date, time và timezone

Phân biệt Instant, LocalDate, LocalDateTime và ZonedDateTime. Host API cần công bố timezone và precision.

### 8.6 Collection và pagination

Không nên trả toàn bộ tập dữ liệu lớn trong một lần gọi. Dùng page/cursor hoặc stream với giới hạn và cancellation.

### 8.7 Immutable data

Giá trị trả về nên immutable hoặc có ownership rõ. Nếu DSL sửa object chia sẻ với host, có thể phá invariant và tạo race condition.

## 9. Giao dịch và tác dụng phụ

Một function host có thể chỉ đọc dữ liệu hoặc tạo side effect.

| Loại thao tác | Ví dụ | Cân nhắc |
|---|---|---|
| Read-only | Đọc đơn hàng | Snapshot, quyền đọc, cache |
| Pure computation | Tính phí | Determinism |
| Local write | Cập nhật trạng thái | Transaction, validation |
| External effect | Gửi email | Retry, idempotency |
| Event publication | Phát OrderApproved | Outbox, ordering |

### 9.1 Read/write separation

Tách query và command giúp API thể hiện rõ thao tác nào có side effect. Có thể áp dụng nguyên tắc CQRS khi phù hợp, nhưng không cần áp dụng một kiến trúc phức tạp cho mọi DSL.

### 9.2 Transaction boundary

Host cần quyết định transaction bao quanh một function, một task, một process step hay toàn bộ execution. Một transaction dài qua nhiều lời gọi mạng thường không phù hợp.

### 9.3 Không giữ transaction trong lúc chờ người dùng

Nếu workflow có bước phê duyệt kéo dài, không giữ database transaction mở suốt thời gian đó. Lưu trạng thái và mở transaction mới khi tiếp tục.

### 9.4 Idempotency

Với command có thể được retry, dùng idempotency key gắn với execution hoặc business operation. Host cần xác định cùng key nhưng payload khác nhau được xử lý thế nào.

### 9.5 Outbox

Nếu cập nhật database và phát event phải nhất quán, host có thể ghi event vào outbox trong cùng transaction rồi publisher phát sau.

## 10. Events và callback từ host

Host có thể thông báo thay đổi cho runtime hoặc extension qua event.

Ví dụ:

~~~java
public interface HostEventListener {
    void onEvent(HostEvent event);
}
~~~

Event có thể gồm:

- ApplicationStarted.
- WorkspaceOpened.
- DocumentChanged.
- ConfigurationUpdated.
- UserSignedOut.
- ResourceDeleted.
- ExecutionCancelled.

### 10.1 Event contract

Event nên có ID, type, timestamp, schema version, source và payload có kiểu.

### 10.2 Subscribe và unsubscribe

Extension cần đăng ký listener và hủy đăng ký khi dispose. Nếu không, host có thể giữ reference đến plugin đã đóng, gây memory leak.

### 10.3 Event ordering

Nếu thứ tự quan trọng, contract cần nói rõ ordering guarantee và scope, chẳng hạn theo document hoặc aggregate.

### 10.4 Duplicate event

Event có thể được phát lại. Listener nên xử lý idempotent hoặc deduplicate khi event có side effect.

### 10.5 Không chặn event thread

Callback không nên thực hiện I/O dài trên UI thread hoặc event dispatch thread. Host cần quy định callback chạy trên executor nào.

### 10.6 Backpressure

Nếu event đến nhanh hơn consumer xử lý, cần queue limit, coalescing, dropping policy hoặc flow control.

## 11. Đồng bộ, bất đồng bộ và concurrency

Host API có thể được gọi từ nhiều execution cùng lúc.

### 11.1 Thread-safety contract

Mỗi service cần công bố có thread-safe hay không. Nếu không, runtime phải serialize lời gọi hoặc tạo instance riêng theo execution.

### 11.2 Không chia sẻ mutable context

Không dùng một mutable context chung cho mọi process. Mỗi execution cần state riêng hoặc immutable snapshot.

### 11.3 Async API

Lời gọi async giúp runtime không chặn worker trong lúc chờ I/O:

~~~java
CompletionStage<PaymentResult> charge(
    PaymentRequest request,
    CommandContext context
);
~~~

### 11.4 Executor ownership

Host nên quy định ai quản lý thread pool và lifecycle của executor. Plugin không nên tự tạo thread không giới hạn.

### 11.5 Cancellation propagation

Nếu process bị cancel, runtime cần truyền cancellation tới async operation và host service. Service phải nói rõ cancellation có thể dừng operation thật hay chỉ dừng chờ kết quả.

### 11.6 Timeout

Timeout ở runtime không bảo đảm server ngoài đã dừng xử lý. Command có side effect vẫn cần idempotency.

### 11.7 Reentrancy

Host callback có thể gọi lại runtime hoặc kích hoạt event khác. Cần xác định API có hỗ trợ reentrant call không để tránh deadlock hoặc recursion không giới hạn.

## 12. Lifecycle của host API và runtime

Host API thường được sử dụng trong nhiều giai đoạn:

~~~text
Host startup
    |
    v
Create API services
    |
    v
Create DSL runtime
    |
    v
Register functions / extensions
    |
    v
Execute programs
    |
    v
Cancel / drain executions
    |
    v
Dispose runtime and services
    |
    v
Host shutdown
~~~

### 12.1 Initialization

Service cần được khởi tạo trước khi runtime có thể gọi. Nếu service phụ thuộc vào configuration hoặc credential, initialization phải báo lỗi rõ khi thiếu.

### 12.2 Registration

Host đăng ký function, type, event listener và capability trước khi compile hoặc execute chương trình cần chúng.

### 12.3 Activation

Extension có thể có bước activate sau khi host kiểm tra dependency và permission.

### 12.4 Shutdown

Host nên ngừng nhận execution mới, yêu cầu execution đang chạy hoàn tất hoặc cancel theo deadline, sau đó dispose resource.

### 12.5 Idempotent dispose

Dispose nên an toàn khi được gọi lặp theo contract, hoặc runtime phải bảo đảm chỉ gọi đúng một lần.

### 12.6 Long-running process

Một process DSL có thể tồn tại lâu hơn một phiên bản service. Host cần quyết định process tiếp tục dùng API snapshot cũ, được migrate hay dừng an toàn khi deploy.

## 13. Error handling qua host boundary

Lỗi từ host service cần được chuyển thành dạng mà DSL runtime hiểu.

### 13.1 Error categories

Có thể phân loại:

- Validation error.
- Not found.
- Permission denied.
- Conflict.
- Rate limited.
- Timeout.
- Dependency unavailable.
- Internal host error.

### 13.2 Stable error code

DSL nên dựa vào error code ổn định thay vì parse message. Message có thể được dịch hoặc thay đổi để dễ hiểu hơn.

### 13.3 Recoverable và fatal

Một lỗi validation có thể được xử lý bằng nhánh nghiệp vụ. Một lỗi runtime corruption có thể buộc dừng execution. Contract phải phân biệt.

### 13.4 Không nuốt lỗi

Adapter không nên bắt mọi exception rồi trả null hoặc success mặc định. Cần chuyển đổi lỗi có chủ ý và giữ nguyên cause/correlation.

### 13.5 Error isolation

Lỗi của một extension không nên làm hỏng toàn bộ host nếu extension được thiết kế để chạy cô lập. Host cần xác định lỗi nào được phép propagate.

### 13.6 Diagnostics

Diagnostic nên liên kết function call với source location trong DSL, function ID, error code và execution ID.

## 14. Security và capability control

Host API là một ranh giới bảo mật quan trọng vì DSL có thể chạy source do người dùng hoặc tenant cung cấp.

### 14.1 Least privilege

Chỉ cấp capability cần thiết. DSL dùng để tính giá không cần quyền xóa customer hoặc đọc file hệ thống.

### 14.2 Authentication và authorization

Host xác định principal, sau đó kiểm tra quyền trên từng resource/action. Có thể kiểm tra ở thời điểm compile để phát hiện sớm và kiểm tra lại khi execute để bảo vệ tài nguyên.

### 14.3 Capability allowlist

Một execution có thể nhận danh sách function được phép:

~~~text
allowedCapabilities:
  - orders.read
  - pricing.calculate
  - audit.write
~~~

Compiler có thể báo lỗi nếu source tham chiếu function ngoài allowlist; runtime vẫn phải kiểm tra quyền để tránh bypass.

### 14.4 Tenant isolation

Mọi truy vấn phải được giới hạn theo tenant context. Không chỉ tin tenantId do source DSL truyền vào; host cần xác thực tenant từ execution identity.

### 14.5 Resource limits

Giới hạn thời gian, số lần gọi API, số record đọc, kích thước payload, memory và concurrency để tránh abuse.

### 14.6 Secret handling

Không expose secret như biến DSL thông thường. Host nên cung cấp reference hoặc operation chuyên biệt, che dữ liệu trong log và giới hạn scope.

### 14.7 Sandboxing

Host API capability control không thay thế sandbox nếu DSL cho phép chạy script hoặc native code. Cần cô lập process/runtime khi threat model yêu cầu.

### 14.8 Audit

Ghi nhận ai hoặc service nào khởi chạy execution, function/capability nào được gọi, resource bị tác động và kết quả ở mức cần thiết. Không ghi secret hoặc payload nhạy cảm không cần thiết.

## 15. API cho editor và Language Server

Trong ứng dụng IDE, host API có thể cung cấp chức năng cho DSL editor.

Ví dụ:

- Lấy nội dung document và URI.
- Truy cập workspace/project.
- Đăng diagnostics.
- Cung cấp completion items.
- Hiển thị hover và code actions.
- Đọc configuration.
- Theo dõi document change.
- Resolve symbol và navigation.

### 15.1 Editor context

API nên cung cấp document snapshot có version. Khi xử lý async, server cần kiểm tra document version trước khi publish diagnostics để tránh kết quả cũ ghi đè kết quả mới.

### 15.2 UI thread

Thao tác cập nhật UI phải chạy trên UI thread theo contract của host. Parsing và semantic analysis nặng nên chạy ngoài UI thread.

### 15.3 Workspace scope

Một editor có thể mở nhiều project. Service cần nhận workspace/project context rõ ràng thay vì dùng active project toàn cục.

### 15.4 Capability negotiation

Language Server chỉ nên dùng extension method mà client đã quảng bá. Host API có thể cung cấp abstraction chung để runtime không phụ thuộc một editor cụ thể.

## 16. API cho ứng dụng server và workflow platform

Trong server, host API thường kết nối DSL với domain service và infrastructure.

### 16.1 Request-scoped context

Một lần thực thi có thể nhận request ID, tenant, principal, locale, deadline và correlation ID.

### 16.2 Service identity

Execution nền có thể chạy sau khi HTTP request ban đầu đã kết thúc. Host cần xác định service identity hoặc delegation token có thời hạn, không giữ session object không còn hợp lệ.

### 16.3 Transaction và workflow boundary

Host cần phối hợp transaction với process step. Không giữ transaction mở trong suốt một workflow kéo dài.

### 16.4 Queue và background execution

Host API có thể cho runtime enqueue task, lưu execution state và resume sau khi worker restart.

### 16.5 Multi-instance deployment

Nếu nhiều host instance cùng xử lý, context và service registry phải phù hợp với phân tán. Không giả định singleton trong memory được chia sẻ toàn cluster.

## 17. API cho desktop và embedded application

Ứng dụng desktop có thể cung cấp API để DSL điều khiển tài liệu, project hoặc thiết bị ngoại vi.

### 17.1 Native resource wrapper

Không nên expose native handle tùy ý cho DSL. Dùng wrapper có ownership và lifecycle rõ.

### 17.2 UI action

DSL có thể yêu cầu host mở dialog hoặc thông báo, nhưng cần xác định action có blocking hay async và có thể chạy khi ứng dụng ở background không.

### 17.3 File access

File API nên dùng URI hoặc resource handle được cấp quyền thay vì path tuyệt đối tùy ý.

### 17.4 Device access

Nếu host tích hợp máy in, camera hoặc thiết bị, cần permission, timeout, resource cleanup và xử lý thiết bị mất kết nối.

## 18. Host API và plugin architecture

Host có thể mở rộng API bằng plugin:

~~~text
Host
 |
 +-- Core services
 |
 +-- Plugin registry
       |
       +-- Finance extension
       +-- Reporting extension
       +-- Editor extension
~~~

### 18.1 Extension descriptor

Plugin descriptor có thể khai báo ID, version, API compatibility range, dependencies, capabilities và configuration schema.

### 18.2 Registration contract

Plugin đăng ký function, type, event listener hoặc service thông qua API được host cung cấp.

### 18.3 Dependency resolution

Host cần kiểm tra plugin dependency và version range trước activation. Không activate plugin nếu capability bắt buộc không có.

### 18.4 Failure isolation

Host cần xác định plugin lỗi khi khởi tạo thì có làm ứng dụng không khởi động hay chỉ disable extension đó.

### 18.5 Unload

Khi unload plugin, cần hủy listener, task, thread, cache và reference. Nếu plugin có execution đang chạy, host phải drain hoặc cancel theo policy.

## 19. Versioning của host API

Host API có thể được dùng bởi nhiều phiên bản runtime và plugin. Vì vậy, cần chính sách versioning rõ.

### 19.1 API version riêng

Version của host API không nhất thiết trùng với version của ứng dụng. Có thể công bố API level hoặc capability set riêng.

### 19.2 Semantic versioning

Nếu dùng SemVer:

- MAJOR cho breaking changes.
- MINOR cho capability mới tương thích.
- PATCH cho sửa lỗi không đổi contract.

Phải định nghĩa public API surface để biết phần nào được bảo đảm.

### 19.3 Capability negotiation

Thay vì chỉ kiểm tra version number, runtime/plugin có thể hỏi host hỗ trợ capability nào:

~~~java
if (host.supports("orders.read.v2")) {
    // Use the newer contract.
}
~~~

Capability nên có ID ổn định và semantics được tài liệu hóa.

### 19.4 Deprecation

Khi thay API:

1. Giới thiệu API mới.
2. Duy trì API cũ trong support window.
3. Đánh dấu deprecated và cung cấp adapter.
4. Theo dõi usage.
5. Loại bỏ theo major release hoặc lịch đã công bố.

### 19.5 Long-lived execution

Process đã khởi chạy có thể tham chiếu function descriptor cũ. Host cần giữ implementation tương thích, snapshot contract hoặc migrate execution ở checkpoint an toàn.

## 20. Adapter và anti-corruption layer

Host API không nhất thiết phản chiếu trực tiếp API của hệ thống ngoài. Adapter chuyển đổi giữa hai mô hình.

~~~text
DSL runtime
    |
    v
Stable host API
    |
    v
Adapter
    |
    v
External system API
~~~

Ví dụ, DSL gọi OrderReader.findById. Adapter có thể lấy dữ liệu từ REST service hôm nay và database repository ngày mai mà DSL không cần thay đổi.

### 20.1 Mapping types

Adapter chuyển domain value, DTO và error giữa hai contract.

### 20.2 Mapping errors

HTTP 404 có thể chuyển thành NotFound; HTTP 429 thành RateLimited; timeout thành DependencyUnavailable hoặc Timeout theo contract.

### 20.3 Retry và circuit breaker

Adapter có thể áp dụng retry có chọn lọc, timeout và circuit breaker. Không retry lỗi nghiệp vụ hoặc command không idempotent một cách mù quáng.

### 20.4 Anti-corruption layer

Nếu hệ thống ngoài có mô hình dữ liệu hoặc thuật ngữ khác, adapter giữ sự khác biệt đó khỏi DSL domain model.

### 20.5 Tránh adapter làm mất semantics

Không chuyển mọi lỗi thành false hoặc mọi giá trị thiếu thành empty string. Giữ lại distinction quan trọng của nguồn.

## 21. Configuration của host API

Host API có thể phụ thuộc endpoint, timeout, quota hoặc feature.

### 21.1 Configuration model

~~~java
public record HostApiConfiguration(
    Duration requestTimeout,
    int maximumCallsPerExecution,
    URI serviceEndpoint
) {}
~~~

### 21.2 Configuration scope

Phân biệt application-wide, tenant-specific và execution-specific configuration. Không đặt secret hoặc user context vào global configuration.

### 21.3 Immutable snapshot

Mỗi execution có thể dùng một configuration snapshot để hành vi nhất quán trong suốt lần chạy.

### 21.4 Dynamic update

Nếu host hỗ trợ reload, cần quy định execution đang chạy dùng snapshot cũ hay nhận thay đổi mới.

### 21.5 Secret provider

Credential nên được resolve từ secret manager theo service identity và scope cần thiết. Không lưu credential thô trong DSL source hoặc plugin descriptor.

## 22. Observability và diagnostics

Host API cần giúp người vận hành hiểu runtime đã gọi service nào và kết quả ra sao.

### 22.1 Structured logs

Log có thể gồm:

- executionId.
- tenantId.
- functionId.
- serviceName.
- duration.
- result category.
- errorCode.
- correlationId.

Không log toàn bộ argument nếu chúng chứa thông tin nhạy cảm.

### 22.2 Metrics

Metrics hữu ích gồm số lần gọi theo function, latency, error rate, timeout, retry, quota rejection, active execution và queue depth.

### 22.3 Distributed tracing

Một trace có thể nối DSL execution, host adapter và lời gọi service ngoài. Propagate trace context qua async boundary.

### 22.4 Source mapping

Khi host call thất bại, diagnostic nên trỏ về function call trong source DSL bằng source range đã lưu từ compiler.

### 22.5 Audit trail

Với command nhạy cảm, ghi ai gọi, function nào, resource nào, outcome và execution identity. Giữ audit payload ở mức tối thiểu cần thiết.

## 23. Kiểm thử host API

Host API nên được kiểm thử ở cấp interface, adapter và tích hợp với runtime.

### 23.1 Unit test cho adapter

Kiểm tra mapping request/response, type conversion, error conversion, timeout và cancellation.

### 23.2 Contract test

Kiểm tra implementation tuân thủ interface contract: kiểu, outcome, error code, thread-safety assumptions và idempotency behavior.

### 23.3 Runtime integration test

Chạy chương trình DSL gọi host function và xác nhận:

- Function được resolve đúng.
- Input được kiểm tra kiểu.
- Capability được kiểm tra.
- Output được map về DSL value.
- Source location xuất hiện trong diagnostic.

### 23.4 Security test

Kiểm tra permission denied, tenant isolation, function ngoài allowlist, secret redaction và resource limits.

### 23.5 Concurrency test

Chạy nhiều execution đồng thời để phát hiện context leakage, shared mutable state và race condition.

### 23.6 Lifecycle test

Kiểm tra startup, partial initialization failure, cancellation, shutdown và plugin unload.

### 23.7 Compatibility test

Chạy plugin/runtime version cũ với host API mới trong ma trận version được hỗ trợ.

## 24. Những sai lầm thường gặp

### Expose toàn bộ application object

DSL có thể truy cập quá nhiều chi tiết nội bộ và bị khóa vào framework của host.

**Cách khắc phục:** công bố interface nhỏ theo capability và domain.

### Dùng global mutable context

Execution của tenant hoặc người dùng này có thể nhìn thấy dữ liệu của execution khác.

**Cách khắc phục:** tạo context theo scope và truyền tường minh.

### Dùng reflection để gọi method tùy ý

Source DSL có thể gọi cả method nội bộ hoặc không an toàn.

**Cách khắc phục:** function registry, descriptor và allowlist.

### Không định nghĩa lifecycle

Service bị dispose quá sớm hoặc listener/plugin bị giữ lại sau shutdown.

**Cách khắc phục:** công bố initialization, activation, drain và dispose semantics.

### Không xác định thread model

Callback cập nhật UI từ background thread hoặc service không thread-safe bị gọi đồng thời.

**Cách khắc phục:** định nghĩa executor, thread safety và async contract.

### Trả null hoặc exception không có cấu trúc

DSL không phân biệt not found, permission denied và service unavailable.

**Cách khắc phục:** result type và error code ổn định.

### Không giới hạn capability

Một script hoặc plugin có thể truy cập tài nguyên vượt phạm vi nghiệp vụ.

**Cách khắc phục:** least privilege, capability allowlist và tenant isolation.

### Adapter che giấu lỗi

Adapter trả default khi service ngoài lỗi, khiến quyết định nghiệp vụ sai.

**Cách khắc phục:** mapping error tường minh và không biến lỗi thành success giả.

### Không version hóa API

Plugin cũ không chạy sau khi host nâng cấp.

**Cách khắc phục:** API version, capability negotiation, compatibility matrix và deprecation policy.

## 25. Quy trình thiết kế host API

Khi tích hợp DSL vào ứng dụng, có thể thực hiện:

1. **Xác định use case:** DSL cần đọc, ghi hoặc phát sinh hành động gì?
2. **Xác định trust boundary:** ai viết source, ai khởi chạy và dữ liệu nào không tin cậy?
3. **Chọn capability:** chỉ công bố service cần thiết.
4. **Thiết kế contract:** kiểu, input/output, errors, nullability và semantics.
5. **Định nghĩa context:** execution, tenant, principal, clock, deadline và cancellation.
6. **Chọn service scope:** singleton, tenant, session hoặc execution.
7. **Thiết kế function registry:** ID, type signature, permissions và side-effect metadata.
8. **Xác định transaction:** command boundary, idempotency và event publication.
9. **Định nghĩa async/thread model:** executor, timeout, cancellation và backpressure.
10. **Thiết kế lifecycle:** startup, registration, activation, drain và disposal.
11. **Bảo vệ API:** authentication, authorization, allowlist, quotas và secret handling.
12. **Version hóa:** API level, capability negotiation và deprecation.
13. **Bổ sung observability:** logs, metrics, traces, diagnostics và audit.
14. **Kiểm thử:** adapter, contract, runtime, security, concurrency và compatibility.

## 26. Ví dụ tổng hợp: host API cho DSL xử lý đơn hàng

Một ứng dụng thương mại điện tử nhúng DSL để mô tả chính sách phê duyệt.

### 26.1 Host contracts

~~~java
public interface OrderReader {
    Optional<OrderView> find(OrderId id);
}

public interface OrderCommands {
    ApprovalResult approve(
        OrderId id,
        ApprovalContext context
    );
}

public interface AuditSink {
    void record(AuditEvent event);
}
~~~

Host chỉ cấp OrderReader, OrderCommands và AuditSink cho policy runtime.

### 26.2 DSL source

~~~text
let order = host.orders.find(input.orderId)

if order.isEmpty {
  return decision.reject("ORDER_NOT_FOUND")
}

if order.value.total > 10000000 {
  return decision.requireReview("HIGH_VALUE_ORDER")
}

host.orders.approve(order.value.id)
host.audit.record("ORDER_APPROVED")
return decision.approve()
~~~

Đây là cú pháp minh họa. Compiler cần resolve các host function và kiểm tra kiểu trước khi execution.

### 26.3 Runtime flow

~~~text
User submits order
       |
       v
Host authenticates principal
       |
       v
Host creates execution context
       |
       v
DSL runtime evaluates policy
       |
       +---- OrderReader
       |
       +---- Authorization check
       |
       +---- OrderCommands
       |
       +---- AuditSink
       |
       v
Host records decision and result
~~~

### 26.4 Security

Host kiểm tra principal có quyền đọc và approve order tương ứng. DSL không được tự chọn tenant khác bằng cách truyền một tenantId tùy ý.

### 26.5 Transaction

Approval command và audit record cần consistency theo yêu cầu nghiệp vụ. Host có thể ghi quyết định và outbox event trong một transaction; không nên để DSL tự mở connection database.

### 26.6 Failure handling

Nếu OrderReader không khả dụng, runtime trả DependencyUnavailable. Không được coi lỗi đó là order không tồn tại hoặc tự động approve.

### 26.7 Observability

Log và trace liên kết executionId, orderId, principal, functionId và correlationId. Audit ghi outcome nhưng không lưu toàn bộ input nhạy cảm.

## 27. Câu hỏi tự kiểm tra

1. Host và DSL runtime có trách nhiệm khác nhau như thế nào?
2. Host API là hợp đồng giữa những thành phần nào?
3. Vì sao nên công bố capability nhỏ thay vì toàn bộ application object?
4. Constructor injection và service registry có ưu nhược điểm gì?
5. Execution context cần những thông tin nào?
6. Function descriptor hỗ trợ compiler và runtime ra sao?
7. Vì sao không nên cho DSL gọi method tùy ý bằng reflection?
8. DTO và domain entity nên được sử dụng qua boundary như thế nào?
9. Host API cần xử lý null, money, time và pagination ra sao?
10. Transaction boundary và idempotency có vai trò gì?
11. Event listener cần unsubscribe khi nào?
12. Thread safety, executor ownership và cancellation cần được định nghĩa ra sao?
13. Host runtime nên shutdown theo thứ tự nào?
14. Error code ổn định giúp DSL xử lý lỗi như thế nào?
15. Capability allowlist và tenant isolation bảo vệ host ra sao?
16. Host API cho editor khác host API cho server ở những điểm nào?
17. Plugin API cần công bố lifecycle và capability nào?
18. Versioning và capability negotiation giúp hỗ trợ plugin cũ như thế nào?
19. Adapter và anti-corruption layer có tác dụng gì?
20. Cần những loại test nào để kiểm tra host API?

API của host là cầu nối có kiểm soát giữa DSL và ứng dụng chủ. Khi capability, context, dữ liệu, lifecycle, error, concurrency, security và versioning được định nghĩa rõ, DSL có thể tích hợp sâu với ứng dụng mà vẫn giữ được ranh giới ổn định, dễ kiểm thử và dễ tiến hóa.
