# Telemetry contract giữa service

Trong một hệ thống gồm nhiều Spring Boot service, một yêu cầu thường đi qua API gateway, service xử lý đơn hàng, service thanh toán, kho dữ liệu và các consumer bất đồng bộ. Mỗi service có thể tự xuất metrics, logs và traces, nhưng nếu mỗi nhóm đặt tên, truyền context và phân loại lỗi theo cách riêng thì dữ liệu rất khó ghép lại. Trace có thể bị đứt, dashboard không so sánh được, log không tìm thấy theo trace ID và một cảnh báo có ý nghĩa ở service này lại mang ý nghĩa khác ở service kia.

Telemetry contract là tập quy ước mà các service cùng tuân theo khi tạo, truyền và xuất dữ liệu observability. Hợp đồng này không thay thế API contract nghiệp vụ. Nó định nghĩa cách nhận diện service, cách truyền ngữ cảnh quan sát, cách mô tả thao tác và lỗi, cấu trúc metrics/logs, chính sách sampling và giao thức gửi dữ liệu đến hệ thống thu thập.

Một hợp đồng tốt giúp người vận hành theo dõi một luồng xử lý xuyên nhiều service mà không phải học lại quy ước ở từng repository.

## Vì sao cần hợp đồng telemetry liên service?

Giả sử checkout-service gọi payment-service, rồi payment-service gửi một message để receipt-worker tạo hóa đơn. Nếu mỗi thành phần tạo trace độc lập, người trực vận hành chỉ thấy ba hoạt động rời rạc. Nếu service truyền trace context đúng cách, các span có thể được nối thành một luồng:

~~~text
Client
└── checkout-service: HTTP server
    └── payment-service: HTTP server
        └── payment-service: database client
        └── receipt-worker: message consumer
~~~

Hợp đồng cần trả lời những câu hỏi sau:

- Dữ liệu này đến từ service, instance và môi trường nào?
- Context nào phải được truyền qua HTTP hoặc message broker?
- Span nào mô tả server, client, producer, consumer hay nghiệp vụ nội bộ?
- Metric nào có cùng ý nghĩa và đơn vị giữa các service?
- Log cần trường nào để liên kết với trace?
- Service nào quyết định sampling và cách quyết định đó được duy trì qua ranh giới?
- Các service và collector thống nhất endpoint, giao thức, xác thực và cách xử lý lỗi export ra sao?

Nếu thiếu những quy ước này, từng service vẫn có thể xuất dữ liệu nhưng toàn hệ thống không có một ngôn ngữ quan sát chung.

## Phạm vi và trách nhiệm của hợp đồng

Telemetry contract nên được quản lý như một chuẩn nền tảng dùng chung, có chủ sở hữu và phiên bản. Nhóm platform hoặc nhóm chịu trách nhiệm observability thường duy trì quy ước; nhóm sở hữu service triển khai và xác minh việc tuân thủ.

| Phần của hợp đồng | Service tạo telemetry phải làm | Service nhận context phải làm |
|---|---|---|
| Resource identity | Gắn tên service, phiên bản, môi trường và định danh instance | Giữ đúng identity của chính service khi tạo telemetry mới |
| Trace propagation | Gửi trace context qua giao thức được hỗ trợ | Tiếp tục trace hiện tại hoặc tạo trace mới khi không có context hợp lệ |
| Baggage | Chỉ truyền các trường đã được cho phép | Chỉ đọc và sử dụng trường đã được thống nhất |
| Span semantics | Dùng span kind, tên và thuộc tính có ngữ nghĩa ổn định | Tạo span ở ranh giới nhận request hoặc message theo cùng quy ước |
| Metrics | Dùng tên, đơn vị, loại instrument và tag đã định nghĩa | Không diễn giải lại cùng metric theo đơn vị hoặc ý nghĩa khác |
| Logs | Ghi log có cấu trúc và trường tương quan | Giữ trace context trong quá trình xử lý để log có thể liên kết |
| Sampling | Tuân theo chính sách trace đã thống nhất | Tôn trọng sampling decision được truyền theo trace context |
| Export | Gửi qua giao thức và endpoint được cấu hình | Collector tiếp nhận, xác thực, định tuyến và báo lỗi theo chính sách |

Hợp đồng cần tách rõ dữ liệu có thể truyền qua ranh giới service và dữ liệu chỉ thuộc nội bộ service. Ví dụ, payment-provider.request.id có thể là thuộc tính hữu ích trong span của payment service nhưng không nhất thiết cần truyền sang mọi service khác. Ngược lại, trace context phải được truyền để duy trì liên kết.

## 1. Resource identity: nhận diện service nhất quán

Resource attributes mô tả thực thể phát ra telemetry. Mọi service nên dùng cùng cách đặt tên cho các thuộc tính định danh:

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| service.name | Tên logic ổn định của service | checkout-service |
| service.namespace | Nhóm hoặc miền nghiệp vụ chứa service | commerce |
| service.version | Phiên bản artifact đang chạy | 2.8.1 |
| service.instance.id | Định danh duy nhất của một instance | checkout-7f9c8d6b5-x2k4p |
| deployment.environment.name | Môi trường triển khai | production |
| cloud.region | Vùng hạ tầng nếu có | ap-southeast-1 |

Các tên trên theo hướng dẫn resource semantic conventions của OpenTelemetry. Khi dùng Micrometer hoặc backend có quy ước riêng, có thể cần ánh xạ tên thuộc tính; việc ánh xạ phải được thống nhất để dashboard vẫn phân biệt được service, phiên bản và môi trường.

Một số nguyên tắc quan trọng:

- service.name phải ổn định qua các lần deploy. Không gắn pod ID hoặc hostname vào tên service.
- service.instance.id phân biệt các instance cùng một service. Giá trị cần duy nhất trong vòng đời instance.
- service.version nên phản ánh artifact thực sự đang chạy, không dùng một giá trị tùy ý giống nhau cho mọi bản build.
- Môi trường phải có tên chuẩn, ví dụ development, staging, production; tránh các biến thể prod, prd, live cùng chỉ một môi trường.
- Resource attributes nên được gắn tại lúc khởi tạo SDK hoặc registry/export pipeline, thay vì lặp lại thủ công trên từng span và log.

Ví dụ định danh cho một service có thể được hình dung như sau:

~~~text
service.name = checkout-service
service.namespace = commerce
service.version = 2.8.1
service.instance.id = checkout-7f9c8d6b5-x2k4p
deployment.environment.name = production
cloud.region = ap-southeast-1
~~~

Trong Spring Boot, spring.application.name là điểm khởi đầu hữu ích để đặt tên ứng dụng. Khi tích hợp Micrometer Tracing, OpenTelemetry SDK hoặc Java agent, hãy kiểm tra resource thực tế được exporter gửi đi để bảo đảm service.name, phiên bản và môi trường không bị thiếu hoặc bị ghi đè bởi cấu hình khác.

Không đưa các giá trị thay đổi theo từng request như user ID, order ID hoặc session ID vào resource attributes. Những giá trị đó không mô tả service; nếu thật sự cần để điều tra, hãy đặt chúng ở span/log theo chính sách dữ liệu và không biến chúng thành metric dimensions.

## 2. Trace context: nối một luồng xử lý xuyên service

### W3C Trace Context

Với giao tiếp HTTP, các service nên thống nhất sử dụng W3C Trace Context. Hai header quan trọng là:

- traceparent: mang trace ID, parent span ID và trace flags.
- tracestate: mang thông tin vendor-specific theo định dạng W3C, nếu được sử dụng.

Ví dụ một header traceparent:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Các thành phần trong header cho phép service phía sau biết request thuộc trace nào, span ngay trước nó là span nào và trace có được đánh dấu sampled hay không. Service nhận request tạo span mới cho ranh giới server và đặt span đó trong trace hiện tại.

Không tự tạo header riêng như X-Trace-Id để thay thế traceparent. Một hệ thống có thể giữ header tương thích cũ trong giai đoạn chuyển đổi, nhưng phải xác định rõ nguồn chuẩn và tránh tạo hai trace ID cạnh tranh. Trace ID do tracing system quản lý; không dùng request ID nghiệp vụ làm trace ID.

### Truyền context trong Spring Boot

Khi dùng các client builder được Spring Boot cấu hình, instrumentation có thể gắn Observation và truyền trace context tự động nếu tracing được bật và client được hỗ trợ. Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class CatalogClientConfiguration {

    @Bean
    RestClient catalogClient(RestClient.Builder builder) {
        return builder
                .baseUrl("http://catalog-service")
                .build();
    }
}
~~~

Service nên inject builder đã được framework cấu hình thay vì tự tạo client độc lập rồi bỏ qua ObservationRegistry hoặc tracing customizer. Với WebClient, RestTemplate hoặc thư viện HTTP khác, cần dùng cơ chế cấu hình và instrument tương ứng với phiên bản Spring Boot đang chạy.

Đối với lời gọi bất đồng bộ, context phải được giữ khi chuyển qua executor, scheduler hoặc message broker. Không giả định rằng trace context trong thread hiện tại tự động có mặt ở thread khác. Hãy dùng cơ chế context propagation của framework và instrumentation cho thư viện tương ứng; kiểm thử cả đường đi qua thread pool và message consumer.

### Message broker và xử lý bất đồng bộ

Khi producer gửi message, trace context cần được inject vào message headers. Consumer extract context từ headers và tạo consumer span liên quan đến trace đó. Với một số mô hình xử lý batch hoặc fan-in, quan hệ span có thể dùng links thay vì ép mọi message thành một chuỗi parent-child duy nhất.

~~~text
order-service
└── message producer span
    └── Kafka record headers: traceparent, tracestate

invoice-worker
└── message consumer span
    └── invoice.create Observation
~~~

Không chỉ truyền trace ID dưới dạng một chuỗi tùy ý. Dùng propagator phù hợp để bảo toàn trace ID, parent span ID, trace flags và trạng thái cần thiết. Với message được lưu lâu trong broker, context có thể đã cũ khi consumer xử lý; điều đó không làm mất ý nghĩa liên kết nhưng cần được tính đến khi phân tích độ trễ end-to-end.

## 3. Baggage: chỉ truyền ngữ cảnh cần thiết

Baggage là tập key-value được truyền cùng trace context qua ranh giới service. Nó phù hợp với thông tin ngữ cảnh nhỏ, có danh sách cho phép rõ ràng và có ích cho các service phía sau, chẳng hạn:

- tenant-tier nếu được chuẩn hóa thành một số ít nhóm.
- region hoặc sales-channel khi chúng cần cho xử lý và điều tra.
- Một mã phân loại đã được làm sạch, không phải dữ liệu định danh nhạy cảm.

Baggage không phải nơi chứa toàn bộ dữ liệu request. Mỗi trường được truyền thêm sẽ làm tăng kích thước header, chi phí mạng và phạm vi dữ liệu được chia sẻ. Không đưa access token, email, số điện thoại, thông tin thanh toán, session secret hoặc dữ liệu cá nhân vào baggage.

Cũng cần phân biệt baggage với span attributes và metric tags:

| Loại dữ liệu | Phạm vi | Cách sử dụng |
|---|---|---|
| Baggage | Có thể được truyền qua nhiều service trong trace | Chỉ chứa context nhỏ, an toàn và được allowlist |
| Span attribute | Gắn với một span cụ thể | Bổ sung chi tiết để điều tra thao tác |
| Metric tag/label | Tạo chiều phân nhóm cho time series | Chỉ dùng giá trị có cardinality thấp và được kiểm soát |
| Log attribute | Gắn với một sự kiện log | Thêm thông tin cần tìm kiếm, theo chính sách bảo vệ dữ liệu |

Một thuộc tính baggage có thể được copy vào span hoặc log ở service phía sau, nhưng không nên tự động biến mọi baggage key thành metric tag. Việc đó có thể tạo số lượng time series rất lớn.

Với Micrometer Tracing trong Spring Boot, các trường baggage cần truyền và các trường cần đưa vào MDC có thể được cấu hình riêng. Ví dụ cấu hình thường gặp:

~~~yaml
management:
  tracing:
    baggage:
      remote-fields:
        - region
      correlation:
        fields:
          - region
~~~

remote-fields xác định trường được truyền qua ranh giới, còn correlation.fields xác định trường cần đưa vào MDC để log có thể sử dụng. Cú pháp và khả năng cụ thể cần đối chiếu với phiên bản Spring Boot/Micrometer của ứng dụng. Chỉ thêm các trường đã được nhóm service và nhóm bảo mật chấp thuận.

## 4. Span semantics: cùng mô tả một công việc theo một cách

Span là đơn vị mô tả một thao tác có thời gian bắt đầu, kết thúc và ngữ cảnh. Hợp đồng nên thống nhất:

- Span kind: SERVER, CLIENT, PRODUCER, CONSUMER hoặc INTERNAL.
- Quy tắc đặt tên theo thao tác và ranh giới.
- Thuộc tính bắt buộc hoặc khuyến nghị.
- Cách thể hiện trạng thái lỗi và loại lỗi.
- Quan hệ parent-child hoặc span links trong xử lý bất đồng bộ.

Tên span nên ổn định và ít biến thiên. Với HTTP, dùng route template hoặc tên thao tác, không dùng URL đầy đủ có ID động. Ví dụ GET /orders/{orderId} phù hợp hơn GET /orders/ORD-948201. Với thao tác nghiệp vụ, tên như payment.authorize hoặc inventory.reserve mô tả rõ công việc.

Các service nên tuân theo semantic conventions tương ứng với giao thức. Với HTTP, các thuộc tính thường cần gồm method, route, response status code và server/client address phù hợp. Không tự định nghĩa nhiều tên thuộc tính cho cùng một khái niệm nếu semantic convention đã có trường chuẩn.

Một span nội bộ nghiệp vụ có thể được tạo bằng Micrometer Observation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
class PaymentService {

    private final ObservationRegistry registry;

    PaymentService(ObservationRegistry registry) {
        this.registry = registry;
    }

    PaymentResult authorize(String paymentMethod) {
        return Observation.createNotStarted("payment.authorize", registry)
                .lowCardinalityKeyValue("payment.method", paymentMethod)
                .observe(this::authorizeWithProvider);
    }

    private PaymentResult authorizeWithProvider() {
        // Gọi cổng thanh toán đã được instrument.
        return new PaymentResult("APPROVED");
    }
}
~~~

Ví dụ chỉ đưa payment.method vào low-cardinality key khi giá trị được giới hạn trong danh sách nhỏ, ví dụ card, wallet, bank_transfer. Không dùng payment ID, transaction ID hoặc customer ID làm low-cardinality key. Nếu cần mã định danh để tìm một giao dịch trong trace, có thể cân nhắc span attribute có cardinality cao theo chính sách bảo mật và retention; không dùng nó làm metric label.

Một Observation có thể được chuyển thành metric và span qua các handler tương ứng. Đây là nhiều tín hiệu từ cùng một thao tác, không phải hai lần instrument. Các service nên tránh tạo thêm span thủ công cho cùng lời gọi nếu HTTP client hoặc agent đã tạo span ở ranh giới đó.

## 5. Metrics contract: tên, đơn vị và cardinality

Metrics có ích khi các service dùng cùng ngữ nghĩa. Hợp đồng nên định nghĩa:

1. Tên metric và ý nghĩa chính xác.
2. Đơn vị đo, ví dụ seconds, bytes hoặc requests.
3. Loại instrument: Counter, Timer/Histogram, Gauge hoặc DistributionSummary.
4. Các tag được phép, kiểu dữ liệu và tập giá trị.
5. Histogram buckets hoặc quy tắc percentile nếu cần so sánh latency.
6. Quy tắc tổng hợp và cách diễn giải khi thiếu dữ liệu.

Ví dụ một contract metric cho nghiệp vụ thanh toán:

| Metric logic | Ý nghĩa | Đơn vị | Dimensions được phép |
|---|---|---|---|
| payment.authorization.duration | Thời gian xử lý một lần authorize | seconds | provider, result, payment_method |
| payment.authorization.count | Số lần authorize | requests | provider, result |
| payment.queue.depth | Số message đang chờ | messages | queue |

Tên metric thực tế có thể được Micrometer hoặc exporter chuẩn hóa theo naming convention của backend. Ví dụ metric Micrometer có tên http.server.requests có thể được chuyển thành tên theo quy ước Prometheus hoặc OpenTelemetry khi export. Điều quan trọng là mọi service hiểu cùng ý nghĩa, đơn vị và dimensions; không tạo hai metric khác tên nhưng cùng đo một đại lượng rồi cộng chúng trong dashboard.

Cardinality là một phần bắt buộc của contract. Nếu metric có tag order_id, mỗi order có thể tạo một time series mới. Nếu metric có tag result với tập giá trị approved, declined, error, số series dễ kiểm soát hơn. Trước khi thêm tag, hãy trả lời: tập giá trị có hữu hạn không, có giới hạn trên không, và có cần thiết cho dashboard hoặc alert không?

Không dùng các trường sau làm metric dimensions:

- User ID, order ID, payment ID hoặc session ID.
- URL đầy đủ có path parameter động.
- Exception message hoặc SQL query.
- Request payload, email hoặc dữ liệu tùy ý từ client.
- Trace ID hoặc span ID.

Trace ID có thể được dùng trong exemplar hoặc liên kết từ metric sang trace nếu backend hỗ trợ, nhưng không phải metric label thông thường.

### Quy ước histogram và SLO

Khi so sánh latency giữa service, các service phải thống nhất đơn vị và cách đọc histogram. Nếu checkout đo giây còn payment đo mili giây nhưng dashboard xử lý như cùng đơn vị, kết quả sẽ sai. Nếu các service có mục tiêu latency khác nhau, bucket boundaries có thể khác nhau, nhưng sự khác biệt cần được tài liệu hóa.

Không nên cộng percentile của nhiều service để tính percentile end-to-end. Percentile không có tính chất cộng. Để đánh giá luồng tổng thể, cần trace hoặc metric được thiết kế trực tiếp cho hành trình end-to-end; với latency phân phối, hãy dùng histogram buckets và phép tổng hợp phù hợp.

## 6. Logs contract: cấu trúc và tương quan

Logs nên được xuất dưới dạng cấu trúc để backend có thể lọc và tổng hợp. Hợp đồng tối thiểu nên thống nhất các trường:

| Trường | Ý nghĩa |
|---|---|
| timestamp | Thời điểm sự kiện |
| severity | Mức độ log theo quy ước thống nhất |
| body hoặc message | Nội dung dễ đọc |
| service.name | Service phát log |
| service.version | Phiên bản ứng dụng |
| deployment.environment.name | Môi trường |
| trace_id | Trace ID hiện hành nếu có |
| span_id | Span ID hiện hành nếu có |
| event.name | Tên sự kiện ổn định nếu có |
| error.type | Loại lỗi đã chuẩn hóa nếu có |

Tên trường cụ thể phụ thuộc log format và backend. OpenTelemetry Logs Data Model có các trường riêng như Timestamp, SeverityText, Body và TraceId; JSON log của ứng dụng có thể dùng tên tương ứng. Hợp đồng cần chỉ rõ mapping để người vận hành không phải đoán.

Log cần ghi đúng context ở thời điểm phát sinh. Khi một request được xử lý trong thread khác hoặc consumer bất đồng bộ, MDC và trace context phải được khôi phục hoặc truyền đúng cách. Nếu chỉ copy trace ID vào một biến static hoặc ThreadLocal không được quản lý, log có thể mang trace ID của request trước hoặc thiếu context hoàn toàn.

Không bắt buộc mọi log phải có trace ID. Log khởi động ứng dụng, health check độc lập hoặc sự kiện ngoài luồng có thể không thuộc một trace. Khi có trace context, log nên có cả trace ID và span ID để người vận hành mở đúng span.

Tránh ghi cùng một lỗi ở mọi tầng với cùng stack trace nếu mỗi log không bổ sung thông tin. Nên thống nhất tầng chịu trách nhiệm ghi lỗi cuối cùng, còn các tầng khác có thể trả lỗi hoặc thêm context vào span. Luôn loại bỏ secret, token và dữ liệu cá nhân khỏi log.

## 7. Sampling: giữ trace liên tục qua ranh giới

Sampling quyết định trace nào được giữ lại. Nếu mỗi service tự quyết định độc lập, một trace có thể có span ở service đầu nhưng mất span ở service sau. Hợp đồng nên định nghĩa:

- Sampler mặc định, ví dụ parent-based với xác suất đầu vào được cấu hình.
- Service phía sau phải tôn trọng sampling flag trong trace context.
- Cách xử lý khi trace context không hợp lệ hoặc không có.
- Các trường hợp cần điều chỉnh sampling, như lỗi hoặc luồng có giá trị điều tra cao.
- Nếu dùng tail sampling, collector nào nhận đủ span và thời gian chờ quyết định là bao lâu.

Với head sampling, quyết định thường được đưa ra sớm ở đầu trace và truyền qua trace flags. Parent-based sampler giúp các service phía sau tuân theo quyết định của parent. Cách này tiết kiệm tài nguyên và giữ tính nhất quán trong trace.

Tail sampling có thể quyết định giữ trace sau khi đã quan sát nhiều span, ví dụ ưu tiên trace có lỗi hoặc latency cao. Để làm được điều đó, collector phải nhận được các span liên quan trước khi ra quyết định. Việc chia trace qua nhiều collector độc lập hoặc định tuyến không nhất quán có thể khiến tail sampler thiếu dữ liệu. Hợp đồng cần mô tả routing và giới hạn bộ nhớ/thời gian chờ.

Không nên đặt xác suất sampling độc lập ở từng service mà không có parent-based behavior. Cũng không nên tăng sampling lên 100% trong production mà không đánh giá lưu lượng, chi phí lưu trữ và chính sách dữ liệu.

## 8. Export contract: giao thức, collector và bảo mật

Các service nên gửi telemetry qua một collector hoặc gateway được quản lý tập trung khi kiến trúc cho phép. Collector có thể nhận OTLP, thêm hoặc chuẩn hóa resource attributes, lọc dữ liệu nhạy cảm, định tuyến đến backend và áp dụng batching/retry.

Hợp đồng export cần ghi rõ:

- Giao thức OTLP dùng gRPC hay HTTP/protobuf.
- Endpoint theo từng môi trường và quy tắc discovery.
- TLS, chứng thư và cơ chế xác thực.
- Timeout, batch size, queue và retry policy.
- Cách xử lý khi collector không khả dụng.
- Quy tắc phân tuyến tenant, môi trường hoặc vùng dữ liệu.
- Quyền truy cập và retention ở backend.

Ví dụ cấu hình môi trường ở mức khái niệm:

~~~text
OTEL_EXPORTER_OTLP_ENDPOINT=https://otel-collector.internal:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_SERVICE_NAME=checkout-service
~~~

Các biến trên là ví dụ phổ biến cho OpenTelemetry SDK hoặc Java agent. Nếu ứng dụng dùng Micrometer OTLP registry/tracing exporter do Spring Boot cấu hình, tên property và cơ chế cấu hình có thể khác. Không trộn hai pipeline export cho cùng một signal nếu chưa có thiết kế rõ ràng, vì có thể gửi dữ liệu trùng hoặc tạo hai resource identity khác nhau.

Collector cần có chính sách backpressure. Khi backend chậm hoặc mất kết nối, queue có giới hạn có thể đầy và telemetry bị drop. Telemetry không nên làm request nghiệp vụ thất bại chỉ vì collector tạm thời không khả dụng; tuy nhiên, mức drop và tình trạng exporter phải được theo dõi bằng health metric hoặc log riêng. Hợp đồng nên định nghĩa mức mất dữ liệu có thể chấp nhận và cách cảnh báo.

## 9. Tương thích và quản lý phiên bản hợp đồng

Telemetry contract cũng cần quy tắc thay đổi. Dashboard, alert và truy vấn thường phụ thuộc vào tên metric, tag và thuộc tính span; đổi tên tùy tiện có thể làm hỏng khả năng quan sát mà không gây lỗi compile.

Nên phân loại thay đổi:

| Loại thay đổi | Ví dụ | Cách triển khai |
|---|---|---|
| Bổ sung tương thích | Thêm thuộc tính span tùy chọn hoặc metric mới | Có thể phát hành trước; cập nhật dashboard khi cần |
| Thay đổi ngữ nghĩa | Đổi ý nghĩa của result=success hoặc đơn vị metric | Cần phiên bản hóa hoặc tên mới; không âm thầm đổi |
| Loại bỏ trường | Xóa tag đang được dashboard sử dụng | Thông báo, giai đoạn chuyển tiếp và kiểm tra consumer |
| Thay đổi propagation | Đổi header hoặc propagator | Hỗ trợ song song trong thời gian chuyển đổi nếu cần |
| Thay đổi resource identity | Đổi service name hoặc environment label | Phải cập nhật dashboard, alert, routing và ownership |

Một cách an toàn là ưu tiên thay đổi additive: thêm trường mới trước, cập nhật consumer/dashboard, quan sát trong thời gian chuyển tiếp, rồi mới ngừng trường cũ. Không tái sử dụng một metric name cho ý nghĩa mới. Nếu metric cũ bị thay thế, đánh dấu deprecated trong tài liệu, cung cấp metric mới và mốc loại bỏ.

Mỗi contract nên có owner, version, ngày hiệu lực, danh sách service áp dụng và changelog. Không nhất thiết mọi thay đổi đều cần tăng major version; điều quan trọng là thay đổi phá vỡ tương thích phải được nhận diện và truyền đạt rõ.

## 10. Kiểm thử contract giữa các service

Kiểm thử ở một service riêng lẻ không chứng minh propagation hoạt động xuyên hệ thống. Cần có kiểm thử tích hợp ở ranh giới HTTP và messaging.

Một luồng kiểm thử mẫu:

1. Gửi request vào checkout-service với một trace context đã biết.
2. Cho checkout gọi payment-service bằng client đã được instrument.
3. Cho payment phát message và để receipt-worker nhận message.
4. Thu thập span từ test exporter hoặc collector test.
5. Xác minh các span có cùng trace ID, parent/link hợp lý và service identity đúng.
6. Xác minh baggage allowlist được truyền, còn trường không được phép không xuất hiện.
7. Xác minh metrics có tên, đơn vị và tag đúng contract.
8. Xác minh log có trace ID/span ID khi xử lý nằm trong trace.
9. Mô phỏng lỗi downstream và kiểm tra error status, error type cùng hành vi sampling.
10. Kiểm tra export failure không làm request nghiệp vụ bị treo vô hạn.

Các assertion quan trọng không chỉ là “có span”. Cần kiểm tra:

- HTTP server span được tạo một lần ở mỗi service nhận request.
- HTTP client span phản ánh đúng lời gọi ra ngoài.
- Span nghiệp vụ có tên ổn định và không tạo trùng span kỹ thuật.
- Consumer span được liên kết với producer context.
- service.name, service.version và environment đúng với từng service.
- Metric tag không chứa ID động.
- Log không làm lộ baggage hoặc dữ liệu nhạy cảm.
- Sampling decision nhất quán trên toàn trace.

Có thể dùng test exporter, in-memory registry hoặc collector chạy trong môi trường test. Với message broker, kiểm thử cần đi qua broker hoặc cơ chế mô phỏng có khả năng giữ headers để phát hiện lỗi inject/extract context. Khi nâng phiên bản Spring Boot, Micrometer, OpenTelemetry instrumentation hoặc Java agent, chạy lại contract tests vì cách instrument và propagation có thể thay đổi.

## Checklist triển khai cho một service Spring Boot

Trước khi đưa service vào hệ thống observability chung, hãy xác minh:

- [ ] Service có service.name, service.version, environment và instance identity đúng.
- [ ] Trace propagation dùng chuẩn đã thống nhất, ưu tiên W3C Trace Context.
- [ ] Client builder và messaging instrumentation giữ được context khi qua service hoặc thread.
- [ ] Baggage chỉ chứa trường được allowlist, không có secret hoặc dữ liệu cá nhân.
- [ ] Span names, kinds và attributes tuân theo semantic conventions của giao thức.
- [ ] Metric name, unit, instrument và dimensions khớp contract.
- [ ] Không có ID động trong metric tags.
- [ ] Logs có cấu trúc và tương quan đúng với trace khi context tồn tại.
- [ ] Sampling policy tôn trọng parent decision.
- [ ] Export dùng endpoint, protocol, TLS và authentication của môi trường.
- [ ] Collector/exporter có timeout, queue, retry và cảnh báo drop phù hợp.
- [ ] Contract tests xác minh luồng xuyên service và được chạy khi nâng dependency.

Telemetry contract chỉ có giá trị khi các service thực sự cùng tuân theo. Hãy đưa quy ước vào cấu hình dùng chung, thư viện nền tảng hoặc template service khi phù hợp; thêm kiểm thử tự động để phát hiện sai lệch sớm. Khi một service đổi tên metric, thêm baggage hoặc thay đổi propagation, thay đổi đó cần được review như một thay đổi ảnh hưởng đến toàn bộ khả năng quan sát của hệ thống.

