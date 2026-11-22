# Giới hạn của MVC trước các quyết định tích hợp và triển khai

Model–View–Controller (MVC) giúp tổ chức cách ứng dụng web tiếp nhận request, xử lý trạng thái và trình bày kết quả. Pattern này làm rõ vai trò của Controller, Model và View, nhưng không trả lời toàn bộ câu hỏi kiến trúc của một hệ thống: ứng dụng sẽ gọi dịch vụ ngoài như thế nào, dữ liệu được đồng bộ ra sao, triển khai thành một hay nhiều đơn vị, mở rộng tải ở đâu, xử lý sự cố mạng thế nào và ai sở hữu dữ liệu.

Với ứng dụng web, MVC là một phần của bức tranh lớn hơn. Một Controller có thể gọi application service, service có thể truy cập database hoặc gọi API khác, còn View có thể được render ở server hay nhận dữ liệu từ một frontend riêng. Các quyết định đó cần những nguyên tắc kiến trúc và cơ chế vận hành bổ sung.

Bài học này xác định rõ phạm vi MVC, phân tích những vấn đề MVC không tự giải quyết và trình bày cách kết hợp MVC với hợp đồng tích hợp, giao tiếp đồng bộ/bất đồng bộ, quản lý transaction, bảo mật, khả năng chịu lỗi, triển khai và quan sát hệ thống. Mục tiêu là biết khi nào MVC đủ cho tầng web và khi nào cần thêm một quyết định kiến trúc khác.

## 1. MVC giải quyết vấn đề gì?

MVC là pattern tổ chức tương tác trong ứng dụng. Ba vai trò cốt lõi thường được hiểu như sau:

- **Model:** biểu diễn trạng thái và hành vi mà ứng dụng cần xử lý. Tùy cách triển khai, Model có thể gồm domain object, application data hoặc view model.
- **View:** trình bày dữ liệu cho người dùng, thường là HTML, template hoặc một dạng representation.
- **Controller:** tiếp nhận input, chuyển đổi request thành lời gọi ứng dụng và chọn response phù hợp.

Trong ứng dụng Spring MVC, một request thường đi qua DispatcherServlet, được ánh xạ đến Controller, rồi Controller gọi dịch vụ ứng dụng. Kết quả được đưa vào model để render View hoặc được chuyển thành response body cho API.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Router as MVC Dispatcher
    participant C as Controller
    participant A as Application Service
    participant V as View / Response

    User->>Router: HTTP request
    Router->>C: Route và bind input
    C->>A: Gọi use case
    A-->>C: Kết quả
    C->>V: Chuẩn bị model / response
    V-->>User: HTTP response
~~~

MVC giúp tránh để mã tiếp nhận HTTP, quy tắc nghiệp vụ và trình bày dồn vào một chỗ. Tuy nhiên, sơ đồ này chỉ mô tả một luồng trong ứng dụng. Nó chưa cho biết Application Service lưu dữ liệu ở đâu, gọi dịch vụ nào, transaction kéo dài bao lâu, hay ứng dụng được triển khai trên hạ tầng nào.

## 2. MVC không phải kiến trúc tổng thể của hệ thống

MVC là pattern ở ranh giới tương tác và trình bày. Nó không tự quyết định:

- Ứng dụng là monolith, modular monolith hay microservices.
- Các lớp bên trong có dùng layered architecture, hexagonal architecture hay clean architecture.
- Database nào được sử dụng và mô-đun nào sở hữu dữ liệu.
- Các hệ thống tích hợp giao tiếp qua HTTP, message broker, file hay giao thức khác.
- Quy trình nhiều bước dùng transaction, Saga hay eventual consistency.
- Ứng dụng chạy trên một máy, nhiều instance hay nhiều vùng triển khai.
- Hệ thống xử lý timeout, retry, circuit breaker và sự cố dependency thế nào.
- Cách quản lý secret, cấu hình, observability và release.

Một hệ thống có thể dùng MVC trong monolith, trong từng service của microservices hoặc trong một backend-for-frontend. Vì vậy, câu hỏi “có dùng MVC không?” không thay thế cho câu hỏi “hệ thống được tổ chức và vận hành như thế nào?”.

| Câu hỏi | MVC có giải quyết trực tiếp? | Quyết định/cơ chế bổ sung |
|---|---|---|
| Route request đến Controller nào? | Có | Routing và dispatcher của framework |
| Controller chuyển input thành lời gọi ứng dụng thế nào? | Có | Binding, DTO và application service |
| Dữ liệu được trình bày ra sao? | Có | View, template hoặc response serializer |
| Database nào được dùng? | Không | Persistence architecture |
| Dịch vụ khác được gọi ra sao? | Không | Integration architecture |
| Transaction xuyên nhiều hệ thống thế nào? | Không | Transaction design, Saga, outbox |
| Ứng dụng triển khai thành bao nhiêu đơn vị? | Không | Deployment architecture |
| Làm sao chịu lỗi khi dependency ngừng hoạt động? | Không | Resilience patterns |
| Làm sao theo dõi request xuyên hệ thống? | Không | Logging, metrics và distributed tracing |

## 3. Tách luồng web khỏi quyết định tích hợp

Controller nên biết giao thức HTTP và use case mà nó phục vụ. Nó không nên tự quản lý mọi chi tiết của dịch vụ bên ngoài, chẳng hạn URL, header xác thực, retry, chuyển đổi lỗi và parsing response.

Ví dụ Controller gọi trực tiếp một HTTP client:

~~~java
@PostMapping("/orders")
public String createOrder(@ModelAttribute OrderForm form) {
    // Controller tự gọi dịch vụ thanh toán, tự xử lý HTTP,
    // tự phân tích response và tự quyết định retry.
    paymentHttpClient.postForEntity(
            "https://payments.internal/charge",
            form,
            PaymentResult.class
    );
    return "redirect:/orders";
}
~~~

Đoạn code trên trộn trách nhiệm web với giao tiếp tích hợp. Khi endpoint thanh toán đổi, timeout xảy ra hoặc cần thay nhà cung cấp, Controller phải thay đổi theo.

Có thể đặt một port hoặc application service ở giữa:

~~~java
@PostMapping("/orders")
public String createOrder(
        @Valid @ModelAttribute("form") OrderForm form,
        BindingResult errors,
        RedirectAttributes redirect
) {
    if (errors.hasErrors()) {
        return "orders/create";
    }

    OrderId orderId = createOrderUseCase.execute(form.toCommand());
    redirect.addFlashAttribute("notice", "Đơn hàng đã được tạo.");
    return "redirect:/orders/" + orderId.value();
}
~~~

Application use case điều phối nghiệp vụ. Một adapter tích hợp chịu trách nhiệm gọi payment provider:

~~~java
public interface PaymentGateway {
    PaymentResult authorize(PaymentCommand command);
}
~~~

~~~java
@Component
public class HttpPaymentGateway implements PaymentGateway {
    private final PaymentHttpClient client;

    public HttpPaymentGateway(PaymentHttpClient client) {
        this.client = client;
    }

    @Override
    public PaymentResult authorize(PaymentCommand command) {
        // Chuyển command nội bộ thành request của nhà cung cấp,
        // gọi HTTP với timeout đã cấu hình và ánh xạ response/lỗi.
        return client.authorize(command);
    }
}
~~~

Ví dụ rút gọn cho thấy Controller chỉ biết use case. Chi tiết HTTP, xác thực với nhà cung cấp, mapping mã lỗi và telemetry thuộc adapter tích hợp. Đây là một cách kết hợp MVC với nguyên tắc ports and adapters; không bắt buộc mọi dự án phải dùng interface cho mọi lời gọi.

## 4. Hợp đồng tích hợp không tự xuất hiện từ Model hoặc DTO của MVC

DTO của một form hoặc View Model được thiết kế cho nhu cầu của màn hình. Nó không mặc nhiên là hợp đồng phù hợp cho API công khai hoặc dịch vụ khác.

Ví dụ, form tạo đơn có thể chứa:

- Mã sản phẩm người dùng chọn.
- Số lượng.
- Địa chỉ giao hàng đã nhập.
- Ghi chú hiển thị trên đơn.

Nhưng payment provider cần một hợp đồng khác, gồm mã giao dịch, số tiền theo đơn vị nhỏ nhất, loại tiền, idempotency key và URL callback theo giao thức của nhà cung cấp.

Không nên gửi nguyên OrderForm hoặc entity Order sang hệ thống ngoài. Hãy định nghĩa request/response riêng cho tích hợp:

~~~java
public record PaymentAuthorizationRequest(
        String merchantReference,
        long amountMinorUnits,
        String currency,
        String idempotencyKey
) {}

public record PaymentAuthorizationResponse(
        String providerReference,
        PaymentProviderStatus status
) {}
~~~

Hợp đồng tích hợp cần làm rõ:

- Trường bắt buộc, kiểu dữ liệu, giới hạn và đơn vị đo.
- Phiên bản và quy tắc tương thích.
- Xác thực và quyền gọi.
- Timeout, lỗi, retry và idempotency.
- Quy tắc bảo mật và dữ liệu không được truyền.
- Ý nghĩa trạng thái và cách xử lý response không xác định.

## 5. Phiên bản API và tương thích giữa các hệ thống

MVC framework có thể ánh xạ route và serialize response, nhưng không tự quản lý vòng đời hợp đồng với client hoặc hệ thống tích hợp.

Khi API được sử dụng bởi một frontend độc lập, ứng dụng di động hoặc đối tác, cần cân nhắc:

- Thêm trường mới có tương thích với client cũ không?
- Đổi tên hoặc xóa trường ảnh hưởng consumer nào?
- Enum mới có làm client cũ lỗi khi parse không?
- Có cần version trong URL, header hoặc media type không?
- Bao lâu trước khi ngừng hỗ trợ phiên bản cũ?
- Có contract test để xác minh producer và consumer không?

Ưu tiên thay đổi tương thích ngược khi có thể, chẳng hạn thêm trường optional. Với thay đổi phá vỡ hợp đồng, cần kế hoạch versioning, thời gian chuyển đổi và thông báo cho consumer.

Không dùng entity persistence làm API contract. Entity có thể thay đổi vì tối ưu database, trong khi API cần ổn định theo nhu cầu client.

## 6. Giao tiếp đồng bộ và bất đồng bộ

MVC thường xử lý một HTTP request/response. Nhưng một use case có thể cần gọi dịch vụ khác ngay hoặc gửi công việc để xử lý sau.

### 6.1. Giao tiếp đồng bộ

Trong giao tiếp đồng bộ, bên gọi chờ kết quả từ bên được gọi. HTTP/REST và gRPC thường được dùng theo cách này.

Phù hợp khi:

- Cần kết quả ngay để quyết định response.
- Thao tác ngắn và có giới hạn thời gian rõ.
- Dependency có mức sẵn sàng phù hợp.
- Người dùng cần biết kết quả trước khi tiếp tục.

Hạn chế:

- Độ trễ cộng dồn qua nhiều lần gọi.
- Dependency chậm có thể giữ request thread hoặc tài nguyên.
- Dependency lỗi có thể làm use case thất bại.
- Chuỗi gọi dài làm tăng coupling về thời gian hoạt động.

### 6.2. Giao tiếp bất đồng bộ

Trong giao tiếp bất đồng bộ, ứng dụng gửi message hoặc event và xử lý kết quả sau. HTTP request có thể trả 202 Accepted cùng mã công việc.

Phù hợp khi:

- Tác vụ mất nhiều thời gian.
- Không cần kết quả ngay trên cùng request.
- Cần hấp thụ tải đột biến qua queue.
- Muốn tách thời gian hoạt động của bên gửi và bên xử lý.

Ví dụ:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant C as MVC Controller
    participant A as Application Service
    participant Q as Message Broker
    participant W as Worker

    User->>C: POST /reports
    C->>A: requestReport(command)
    A->>Q: Publish ReportRequested
    Q-->>A: Accepted
    A-->>C: Job ID
    C-->>User: 202 Accepted + Job ID
    Q->>W: Deliver message
    W->>W: Generate report
    W->>Q: Publish ReportReady
~~~

Khi trả 202, giao diện cần biết cách xem trạng thái công việc hoặc nhận thông báo hoàn tất. Không nên trả 202 nếu message chưa được chấp nhận bền vững theo cam kết của hệ thống.

## 7. MVC không giải quyết consistency giữa nhiều hệ thống

Một thao tác đặt hàng có thể liên quan đến Ordering, Inventory và Payment. Mỗi hệ thống có thể có database hoặc transaction riêng. Transaction database cục bộ không tự bảo đảm tất cả bước thành công hoặc cùng rollback.

Ví dụ:

1. Tạo đơn hàng.
2. Giữ tồn kho.
3. Yêu cầu thanh toán.
4. Xác nhận đơn.

Nếu thanh toán thành công nhưng ứng dụng lỗi trước khi cập nhật đơn, trạng thái giữa các hệ thống có thể không đồng nhất. Đây là vấn đề consistency và điều phối nghiệp vụ, không phải vấn đề của Controller.

Các hướng xử lý:

- **Saga:** chia quy trình thành các bước có hành động bù trừ khi thất bại.
- **Transactional outbox:** lưu thay đổi dữ liệu và sự kiện cần publish trong cùng transaction cục bộ, sau đó một publisher gửi sự kiện.
- **Idempotency:** bảo đảm xử lý lặp không tạo tác dụng phụ trùng.
- **Reconciliation:** đối soát trạng thái giữa các hệ thống khi có kết quả không xác định.
- **State machine:** mô hình hóa trạng thái và chuyển trạng thái hợp lệ của quy trình.

~~~mermaid
flowchart TD
    A[Create order: PENDING] --> B[Reserve inventory]
    B --> C{Reserved?}
    C -->|No| D[Order REJECTED]
    C -->|Yes| E[Authorize payment]
    E --> F{Payment result}
    F -->|Approved| G[Order CONFIRMED]
    F -->|Declined| H[Release inventory]
    F -->|Unknown / timeout| I[Reconcile payment status]
    H --> J[Order PAYMENT_FAILED]
    I --> G
    I --> H
~~~

Controller chỉ khởi tạo use case và trả trạng thái phù hợp. Application layer hoặc process manager chịu trách nhiệm điều phối, lưu trạng thái và xử lý bù trừ.

## 8. Quyền sở hữu dữ liệu và ranh giới persistence

MVC không xác định database schema hay quyền ghi dữ liệu. Nếu nhiều phần ứng dụng cùng sửa một bảng hoặc cùng chia sẻ entity, thay đổi ở một phần có thể gây ảnh hưởng ngoài dự kiến.

Một số nguyên tắc:

- Xác định mô-đun hoặc dịch vụ sở hữu từng nhóm dữ liệu.
- Chỉ chủ sở hữu chịu trách nhiệm cập nhật trạng thái của dữ liệu đó.
- Cung cấp query API hoặc read model cho bên cần đọc.
- Không truyền entity ORM qua ranh giới tích hợp.
- Dùng DTO hoặc event schema có hợp đồng rõ.
- Với báo cáo liên miền, thiết kế projection/read model thay vì để mọi phần tùy ý truy cập bảng nội bộ.

Một modular monolith có thể dùng chung database vật lý nhưng vẫn giữ quyền sở hữu bảng theo mô-đun. Trong microservices, mỗi service thường sở hữu dữ liệu và giao tiếp qua API/event thay vì truy vấn trực tiếp database của service khác.

## 9. Quyết định triển khai nằm ngoài MVC

MVC không yêu cầu ứng dụng phải triển khai theo một topology cụ thể. Một hệ thống MVC có thể chạy:

- Trong một tiến trình monolith.
- Trong một modular monolith với nhiều module nghiệp vụ.
- Trong nhiều instance giống nhau phía sau load balancer.
- Trong một microservice là một phần của hệ thống phân tán.
- Với frontend tách riêng và backend MVC cung cấp API.

Việc chọn topology phụ thuộc vào quy mô, yêu cầu triển khai độc lập, cách chia đội ngũ, mức độ cô lập, khả năng vận hành và chi phí.

| Kiểu triển khai | Đặc điểm | Trade-off chính |
|---|---|---|
| Monolith | Một đơn vị build/deploy | Đơn giản vận hành ban đầu, nhưng các phần có thể coupling |
| Modular monolith | Một đơn vị deploy, module boundary rõ | Giữ triển khai đơn giản và kiểm soát code tốt hơn; module boundary cần được thực thi |
| Microservices | Nhiều đơn vị deploy độc lập | Scale/release độc lập; tăng độ phức tạp mạng, consistency và vận hành |
| Frontend riêng + MVC API | UI và backend triển khai độc lập | Linh hoạt client; cần quản lý API, CORS, auth và versioning |

Không nên tách microservice chỉ vì MVC Controller đã trở nên lớn. Trước tiên cần xác định vấn đề nằm ở trách nhiệm Controller, ranh giới nghiệp vụ hay nhu cầu triển khai độc lập.

## 10. Mở rộng tải và trạng thái phiên

Một ứng dụng MVC chạy nhiều instance phía sau load balancer cần xem xét trạng thái giữa các request.

Nếu session chỉ được lưu trong bộ nhớ của một instance:

- Request đầu có thể vào instance A và tạo session.
- Request tiếp theo vào instance B không tìm thấy session.
- Người dùng có thể bị đăng xuất hoặc mất trạng thái.

Các lựa chọn:

- Dùng session store dùng chung như Redis.
- Dùng sticky session khi phù hợp, nhưng hiểu giới hạn khi instance lỗi hoặc scale.
- Thiết kế ứng dụng stateless và lưu trạng thái cần thiết ở database/cache.
- Dùng token có thiết kế phù hợp cho API, kèm cơ chế thu hồi và thời hạn.

~~~mermaid
flowchart LR
    U[Browser] --> LB[Load Balancer]
    LB --> A[MVC Instance A]
    LB --> B[MVC Instance B]
    A --> S[(Shared Session Store)]
    B --> S
    A --> DB[(Database)]
    B --> DB
~~~

MVC không tự làm ứng dụng stateless. Cần xác định dữ liệu nào nằm trong request, session, cache hoặc database và cách các instance chia sẻ dữ liệu đó.

## 11. Khả năng chịu lỗi khi gọi dependency

Khi MVC application gọi API bên ngoài, mạng có thể chậm, mất kết nối hoặc trả lỗi. Không nên để một request chờ vô hạn.

Các cơ chế thường cần:

- **Timeout:** giới hạn thời gian chờ kết nối và phản hồi.
- **Retry:** thử lại lỗi tạm thời theo chính sách có giới hạn.
- **Circuit breaker:** tạm ngừng gọi dependency đang lỗi liên tục để tránh làm hệ thống quá tải.
- **Bulkhead:** giới hạn tài nguyên dành cho từng nhóm dependency.
- **Fallback:** cung cấp hành vi thay thế an toàn khi phù hợp.
- **Rate limiting:** giới hạn tốc độ request để bảo vệ dịch vụ.

Retry phải được dùng cẩn thận. Nếu request tạo thanh toán đã đến nhà cung cấp nhưng response bị mất, gửi lại không có idempotency có thể tạo giao dịch trùng. Retry chỉ phù hợp với thao tác có thể lặp an toàn hoặc có cơ chế idempotency.

Fallback cũng không nên bịa ra kết quả thành công. Nếu không thể xác nhận thanh toán, giao diện nên hiển thị trạng thái chưa xác định và hướng dẫn kiểm tra lại, thay vì thông báo thất bại chắc chắn.

Ví dụ cấu hình timeout cho HTTP client cần được đặt ở adapter tích hợp. Giá trị cụ thể phụ thuộc SLA, mạng, dependency và trải nghiệm người dùng; không có một con số phù hợp cho mọi API.

## 12. Bảo mật và ranh giới tin cậy

MVC framework có thể hỗ trợ authentication, authorization, CSRF và binding an toàn, nhưng không tự xác định chính sách bảo mật đầy đủ của hệ thống.

Các câu hỏi cần trả lời:

- Request đến từ browser, mobile app, đối tác hay service nội bộ?
- Identity được xác minh ở gateway hay ứng dụng?
- Quyền được kiểm tra ở endpoint và trên từng đối tượng ra sao?
- Secret của dịch vụ ngoài được lưu và xoay vòng ở đâu?
- Dữ liệu nào được phép đi qua ranh giới tổ chức?
- Callback/webhook được xác minh chữ ký và chống replay thế nào?
- CORS cho phép origin nào và header nào?
- Log/trace có loại bỏ token và dữ liệu cá nhân không?

Một request được xác thực ở Controller vẫn cần kiểm tra quyền trên tài nguyên cụ thể trong application/domain layer. Không tin user ID, tenant ID hoặc role do client tự gửi. Không truyền credential của người dùng sang dịch vụ ngoài nếu hợp đồng không yêu cầu.

Với webhook, cần xác minh chữ ký hoặc cơ chế xác thực do nhà cung cấp quy định, kiểm tra timestamp/nonce nếu có và xử lý sự kiện lặp một cách idempotent. Chỉ dựa vào URL khó đoán không phải cơ chế xác thực đầy đủ.

## 13. Quan sát hệ thống xuyên qua ranh giới tích hợp

Log trong Controller có thể cho biết request đã vào ứng dụng, nhưng không đủ để giải thích thời gian chờ ở payment provider hoặc worker. Cần phối hợp:

- **Logs:** sự kiện có ngữ cảnh và mã tương quan.
- **Metrics:** tỷ lệ lỗi, latency, throughput, queue depth và số lần retry.
- **Distributed traces:** đường đi của request qua các service và dependency.

Một request nên có trace context được truyền qua HTTP client và message broker nếu các thành phần hỗ trợ. Correlation ID nghiệp vụ có thể liên kết các trace riêng của một quy trình dài.

Không dùng trace ID hoặc user ID làm label metric có cardinality cao. Không đưa token, password, session ID hoặc PII không cần thiết vào log, span attribute hay baggage.

MVC có thể tạo request log ở ranh giới web, nhưng instrumentation cho database, HTTP client, queue và worker cần được cấu hình riêng. Observability là một năng lực xuyên suốt, không phải chức năng chỉ thuộc Controller.

## 14. Cấu hình và secret theo môi trường

URL của payment provider, database credentials, API key, timeout và feature flag không nên được hard-code trong Controller hoặc domain model.

Hãy tách:

- Cấu hình ứng dụng không bí mật như timeout, base URL và feature setting.
- Secret như API key, private key, password và certificate.
- Cấu hình theo môi trường phát triển, kiểm thử, staging và production.

Một số nguyên tắc:

- Dùng environment/configuration provider hoặc secret manager phù hợp.
- Không commit secret vào source control.
- Có quy trình rotate và revoke credential.
- Không ghi secret vào log hoặc error response.
- Kiểm tra cấu hình bắt buộc khi ứng dụng khởi động.
- Tránh để giá trị mặc định yếu được dùng trong production.

Controller không nên biết cách lấy secret. Adapter tích hợp nhận dependency đã được cấu hình từ composition root hoặc framework.

## 15. Triển khai và thay đổi schema an toàn

MVC không quyết định quy trình release. Khi ứng dụng có nhiều instance hoặc nhiều service, deploy có thể diễn ra trong lúc request vẫn đang được xử lý.

Database migration cần tương thích với phiên bản ứng dụng cũ và mới trong khoảng thời gian chuyển tiếp. Một chiến lược thường dùng là expand-and-contract:

1. Thêm cột hoặc cấu trúc mới mà code cũ vẫn hoạt động.
2. Deploy code có thể đọc/ghi cấu trúc mới và cũ theo giai đoạn.
3. Backfill dữ liệu nếu cần.
4. Chuyển toàn bộ luồng sang cấu trúc mới.
5. Chỉ xóa cấu trúc cũ khi mọi instance/consumer đã ngừng sử dụng.

Với API/event contract, cũng cần thay đổi theo hướng tương thích trước khi xóa trường hoặc đổi ý nghĩa. Không nên deploy đồng thời nhiều thành phần với giả định tất cả cập nhật cùng một thời điểm.

## 16. Backend-for-Frontend và MVC

Khi giao diện web, mobile và đối tác có nhu cầu khác nhau, một backend MVC có thể cung cấp API chung hoặc dùng Backend-for-Frontend (BFF) để phục vụ từng loại client.

BFF là lớp backend tối ưu response và điều phối dữ liệu cho một loại giao diện. Nó có thể dùng MVC Controller để tiếp nhận HTTP, nhưng BFF không phải một phần bắt buộc của MVC.

Có thể cần BFF khi:

- Web và mobile cần payload khác nhau.
- Giao diện cần tổng hợp dữ liệu từ nhiều service.
- Muốn giữ token/service credential ở server.
- Cần giảm số lần gọi từ client.
- Có chính sách caching hoặc rate limiting riêng cho từng client.

Không nên tạo BFF nếu nó chỉ chuyển tiếp request mà không có nhu cầu composition, bảo mật hoặc tối ưu client rõ ràng. Một tầng trung gian không cần thiết làm tăng latency và số thành phần cần vận hành.

## 17. Chọn cơ chế bổ sung theo vấn đề thực tế

| Vấn đề | Cơ chế nên xem xét | Vai trò của MVC |
|---|---|---|
| Controller chứa logic nghiệp vụ | Application service/domain model | Tiếp nhận và điều phối request |
| Gọi API ngoài khó thay thế | Port và adapter tích hợp | Gọi use case |
| API thay đổi gây lỗi client | Versioning và contract tests | Expose hợp đồng HTTP |
| Quy trình nhiều hệ thống không đồng bộ | Saga, outbox, idempotency | Khởi tạo use case và trả trạng thái |
| Request chậm do dependency | Timeout, circuit breaker, async | Trả phản hồi phù hợp |
| Nhiều instance mất session | Shared session store hoặc stateless design | Xử lý request theo trạng thái được cung cấp |
| Module truy cập dữ liệu của nhau | Data ownership và module API | Dùng application contract |
| Khó điều tra lỗi xuyên service | Correlation ID, logs, metrics, traces | Gắn ngữ cảnh tại HTTP boundary |
| Release gây lỗi schema/API | Expand-and-contract, compatibility policy | Duy trì route/response tương thích |
| Nhiều client cần payload khác nhau | BFF hoặc API composition | Làm adapter HTTP cho client |

Không nên áp dụng tất cả pattern chỉ vì chúng tồn tại. Chọn cơ chế dựa trên failure mode, yêu cầu nghiệp vụ và chi phí vận hành cụ thể.

## 18. Ví dụ kết hợp MVC với kiến trúc tích hợp

Một ứng dụng đặt hàng có thể được tổ chức như sau:

~~~mermaid
flowchart TB
    UI[Browser / Mobile] --> GW[Gateway / MVC Web Adapter]
    GW --> APP[Order Application Use Case]
    APP --> DOM[Order Domain]
    APP --> CAT[Catalog Port]
    APP --> INV[Inventory Port]
    APP --> PAY[Payment Port]
    APP --> REPO[Order Repository Port]
    CAT --> CATAPI[Catalog Adapter]
    INV --> INVAPI[Inventory Adapter]
    PAY --> PAYAPI[Payment Adapter]
    REPO --> DB[(Order Database)]
    CATAPI --> CATSVC[Catalog Service]
    INVAPI --> INVSVC[Inventory Service]
    PAYAPI --> PAYSVC[Payment Provider]
    APP --> OUT[Outbox / Event Publisher]
    OUT --> Q[Message Broker]
    Q --> W[Background Worker]
    GW -. telemetry .-> OBS[Logs / Metrics / Traces]
    APP -. telemetry .-> OBS
    CATAPI -. telemetry .-> OBS
    PAYAPI -. telemetry .-> OBS
~~~

Trong thiết kế này:

- MVC web adapter xử lý HTTP, binding, validation và response.
- Application use case điều phối quy trình đặt hàng.
- Domain bảo vệ trạng thái và quy tắc của đơn.
- Các port mô tả nhu cầu tích hợp của ứng dụng.
- Adapter chuyển hợp đồng nội bộ thành giao thức của dịch vụ ngoài.
- Repository lưu trạng thái thuộc quyền sở hữu của Ordering.
- Outbox/message broker hỗ trợ công việc cần xử lý bất đồng bộ.
- Observability kết nối log, metric và trace xuyên các ranh giới.

Sơ đồ là một ví dụ kiến trúc, không phải cấu hình bắt buộc. Một ứng dụng nhỏ có thể chưa cần gateway, broker hoặc nhiều service riêng. Chỉ thêm thành phần khi nhu cầu thực tế biện minh cho chi phí của nó.

## 19. Quy trình đưa ra quyết định ngoài phạm vi MVC

Khi một yêu cầu mới xuất hiện, có thể đi theo trình tự:

1. **Xác định hành vi web:** người dùng gửi request nào và cần response gì?
2. **Xác định use case:** quy tắc nghiệp vụ nào phải được bảo vệ?
3. **Xác định dependency:** dữ liệu hoặc hành động nào thuộc hệ thống khác?
4. **Chọn kiểu giao tiếp:** cần kết quả ngay hay có thể xử lý bất đồng bộ?
5. **Xác định consistency:** có transaction cục bộ hay quy trình nhiều bước cần bù trừ?
6. **Xác định quyền sở hữu dữ liệu:** ai được ghi và ai chỉ được đọc?
7. **Xác định failure mode:** timeout, retry, duplicate, partial failure và fallback.
8. **Xác định trust boundary:** identity, secret, dữ liệu và quyền gọi được kiểm tra ở đâu?
9. **Xác định topology:** một đơn vị triển khai hay cần scale/release độc lập?
10. **Xác định vận hành:** metrics, logs, traces, alert và quy trình khôi phục.
11. **Kiểm thử hợp đồng và luồng:** xác minh cả thành công, lỗi và kết quả không xác định.

Quy trình này giữ MVC ở đúng vị trí: nó tổ chức giao tiếp HTTP, còn các quyết định về tích hợp và triển khai được đưa ra theo yêu cầu hệ thống.

## 20. Những lỗi thiết kế thường gặp

### Xem MVC như kiến trúc đầy đủ

Có Controller, Model và View không có nghĩa hệ thống đã có ranh giới dữ liệu, transaction, tích hợp và vận hành phù hợp. Cần xác định những phần MVC không bao phủ.

### Để Controller gọi trực tiếp mọi dịch vụ ngoài

Controller trở nên phụ thuộc vào URL, authentication, retry và response format của từng nhà cung cấp. Hãy đặt adapter tích hợp ở tầng phù hợp.

### Dùng View DTO làm hợp đồng API cho mọi nơi

View Model phục vụ màn hình; API contract phục vụ consumer. Hai loại có thể giống nhau trong trường hợp đơn giản nhưng không nên mặc định đồng nhất.

### Giữ transaction mở trong khi gọi dịch vụ ngoài

Lời gọi mạng chậm có thể giữ connection và lock lâu. Cần cân nhắc transaction boundary, outbox hoặc Saga.

### Retry mọi lỗi

Retry thao tác không idempotent có thể tạo dữ liệu hoặc giao dịch trùng. Phân loại lỗi và đặt giới hạn retry rõ.

### Dùng message broker khi chưa cần bất đồng bộ

Broker thêm vận hành, retry, ordering và xử lý duplicate. Nếu use case cần kết quả ngay và lời gọi đơn giản, giao tiếp đồng bộ có thể phù hợp hơn.

### Cho rằng scale ngang chỉ cần tăng instance

Session cục bộ, cache cục bộ, file tạm và tác vụ nền trong bộ nhớ có thể làm nhiều instance hoạt động không nhất quán. Cần thiết kế trạng thái và tài nguyên dùng chung.

### Dùng trace ID làm mã xác thực

Trace context phục vụ quan sát, không cấp quyền. Authentication và authorization vẫn phải được kiểm tra độc lập.

### Tách microservice chỉ vì ứng dụng lớn

Số lượng lớp hoặc Controller không phải tiêu chí duy nhất. Cần có lý do về ownership, scale, release, bảo mật hoặc vận hành trước khi tách.

## 21. Checklist review giới hạn MVC và quyết định kiến trúc

- [ ] MVC chỉ chịu trách nhiệm tiếp nhận request, điều phối và trình bày.
- [ ] Quy tắc nghiệp vụ nằm ở domain/application layer phù hợp.
- [ ] Controller không chứa chi tiết giao tiếp với từng nhà cung cấp.
- [ ] Hợp đồng tích hợp tách khỏi form DTO, View Model và entity ORM.
- [ ] API/event có versioning và quy tắc tương thích rõ.
- [ ] Giao tiếp đồng bộ/bất đồng bộ được chọn theo nhu cầu use case.
- [ ] Transaction và consistency nhiều hệ thống có thiết kế rõ.
- [ ] Retry có giới hạn và chỉ áp dụng an toàn với idempotency phù hợp.
- [ ] Dữ liệu có chủ sở hữu; mô-đun khác đi qua hợp đồng công khai.
- [ ] Deployment topology dựa trên yêu cầu vận hành cụ thể.
- [ ] Session và trạng thái được thiết kế cho số instance dự kiến.
- [ ] Timeout, circuit breaker, bulkhead và fallback được cân nhắc theo dependency.
- [ ] Authentication, authorization và secret có ranh giới tin cậy rõ.
- [ ] Logs, metrics và traces có thể liên kết xuyên dịch vụ.
- [ ] Schema migration và API release tương thích với các phiên bản đang chạy.
- [ ] Có test cho contract, failure mode, duplicate và partial failure.

## Kết luận

MVC tổ chức luồng tương tác web giữa request, nghiệp vụ và trình bày, nhưng không quyết định kiến trúc tích hợp hoặc triển khai của toàn hệ thống. Những vấn đề như hợp đồng API, giao tiếp đồng bộ/bất đồng bộ, consistency nhiều database, quyền sở hữu dữ liệu, scaling, resilience, security boundary và observability cần được giải quyết bằng các quyết định kiến trúc bổ sung. Hãy giữ Controller tập trung vào HTTP và use case, đặt tích hợp trong adapter có hợp đồng rõ, thiết kế transaction và failure mode theo nghiệp vụ, rồi chọn topology theo nhu cầu vận hành thực tế. Khi hiểu giới hạn của MVC, nhóm có thể dùng pattern đúng phạm vi và tránh kỳ vọng nó tự giải quyết những vấn đề nằm ngoài tầng trình bày.
