# Truyền ngữ cảnh dấu vết qua HTTP, RPC và thông điệp

Một yêu cầu trong hệ thống microservices hiếm khi chỉ chạy trong một tiến trình. Nó có thể đi từ API Gateway đến một service qua HTTP, gọi service khác bằng gRPC, rồi phát sự kiện vào Kafka hoặc RabbitMQ để worker xử lý. Mỗi thành phần đều có thể tạo log và span, nhưng nếu **ngữ cảnh dấu vết (trace context)** không được chuyển qua ranh giới mạng và ranh giới bất đồng bộ thì các dữ liệu quan sát sẽ bị tách thành nhiều mảnh.

**Trace context propagation** là cơ chế chuyển thông tin nhận dạng một chuỗi thực thi từ thành phần gửi sang thành phần nhận. Thành phần nhận dùng thông tin đó để tạo span có quan hệ nhân quả với công việc phía trước, giúp trace thể hiện đường đi từ đầu đến cuối.

Bài này tập trung vào cách mô hình hóa và truyền context nhất quán qua **HTTP, RPC và message broker**, kể cả những trường hợp một thông điệp được xử lý lâu sau khi request ban đầu đã kết thúc.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt trace, span, span context, baggage, correlation ID và metadata truyền qua mạng.
2. Giải thích sự khác nhau giữa việc **tạo span** và **truyền span context**.
3. Mô tả thao tác `inject` ở phía gửi và `extract` ở phía nhận cho HTTP, RPC và message headers.
4. Sử dụng định dạng W3C Trace Context và hiểu mục đích của `traceparent`, `tracestate` và `baggage`.
5. Chọn quan hệ **parent–child** hoặc **span link** phù hợp với đường xử lý đồng bộ, message đơn, batch và fan-in.
6. Nhận ra điểm mất context khi qua executor, reactive pipeline, retry, gateway, proxy và hàng đợi.
7. Kiểm chứng tính liên thông của trace bằng request thực tế, trace viewer và log có trace ID.

## 2. Vì sao tạo span ở từng service vẫn chưa đủ?

Xét hệ thống bán hàng:

~~~text
Client
  |
  | HTTP POST /orders
  v
API Gateway
  |
  | HTTP
  v
Order Service
  | \
  |  \ gRPC CheckStock
  |   v
  |  Inventory Service
  |
  | publish "OrderCreated"
  v
Message Broker
  |
  | deliver (có thể sau vài giây)
  v
Notification Worker
  |
  | HTTP
  v
Email Provider
~~~

Nếu tất cả thành phần tự khởi tạo trace mới, giao diện tracing có thể hiển thị bốn trace rời rạc:

~~~text
Trace A: Gateway -> Order Service
Trace B: Inventory Service
Trace C: Broker producer
Trace D: Notification Worker -> Email Provider
~~~

Chúng có thể có cùng business order ID nhưng không thể suy ra trực tiếp quan hệ thực thi từ cấu trúc trace. Khi propagation hoạt động, các bước có thể liên hệ như sau:

~~~text
Trace T
  Gateway SERVER span
    Order Service SERVER span
      Inventory gRPC CLIENT span
        Inventory gRPC SERVER span
      OrderCreated PRODUCER span
        Notification CONSUMER span
          Email HTTP CLIENT span
~~~

Sơ đồ trên biểu diễn phương án **consumer là con của producer** khi có một thông điệp và quan hệ nhân quả rõ ràng. Với workflow bất đồng bộ độc lập, nhiều nguồn hoặc batch, phương án chính xác hơn có thể là **trace riêng có span link** tới span context của thông điệp. Không bắt buộc mọi công việc liên quan cùng chia sẻ một `traceId` mới gọi là được liên kết: các trace khác nhau vẫn có thể được nối bằng link và khóa nghiệp vụ.

Điểm cốt lõi: propagation mang **context để dựng quan hệ**, còn collector/exporter vận chuyển **dữ liệu telemetry** đến hệ thống quan sát. Hai việc này độc lập.

## 3. Các khái niệm nền tảng

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| **Trace** | Cấu trúc mô tả các hoạt động liên quan của một luồng thực thi. | Tạo đơn hàng và phát sự kiện. |
| **Trace ID** | Mã 128-bit nhận diện trace; các span trong cùng trace dùng cùng trace ID. | `4bf92f3577b34da6a3ce929d0e0e4736` |
| **Span** | Đơn vị công việc có tên, thời gian, thuộc tính, trạng thái và quan hệ. | `POST /orders`, `grpc.Inventory/CheckStock`. |
| **Span ID** | Mã 64-bit nhận diện span trong trace. | `00f067aa0ba902b7` |
| **Parent span** | Span mà span hiện tại xuất phát từ đó trong mô hình parent–child. | Service SERVER span là con của HTTP CLIENT span. |
| **Span context** | Thông tin đủ để tham chiếu span qua ranh giới tiến trình: trace ID, span ID, flags và trace state. | Context nhận từ HTTP header. |
| **Propagation** | Mang context vào carrier ở phía gửi và khôi phục tại phía nhận. | Headers, gRPC metadata, message headers. |
| **Baggage** | Metadata dạng khóa–giá trị có thể lan truyền cùng request nhưng không đồng nghĩa với span attributes. | `deployment.region=apac` sau khi được cho phép. |
| **Span link** | Quan hệ tham chiếu giữa span hiện tại với một span context khác mà không buộc thành parent. | Worker batch xử lý 10 thông điệp từ nhiều traces. |
| **Correlation ID** | Mã liên kết cấp ứng dụng; có thể cùng tồn tại với tracing. | `orderId`, `requestId`. |

Một span thường có `SpanKind` như `SERVER`, `CLIENT`, `PRODUCER`, `CONSUMER` hoặc `INTERNAL`. Span kind cho biết vai trò chứ không tự tạo quan hệ: quan hệ đến từ context được truyền và cách tạo span.

### Trace context khác gì log context?

- Trace context định danh span/trace và mang thông tin phục vụ propagation.
- Logging context như SLF4J MDC hỗ trợ đưa `trace_id`, `span_id` vào từng log line.
- MDC chỉ là cơ chế lưu dữ liệu log tại tiến trình; **copy MDC sang một thread không thay thế được trace context propagation**.
- Business correlation ID có thể tồn tại lâu hơn một trace, ví dụ `orderId` nối nhiều workflow chạy vào các ngày khác nhau; đó là khóa điều tra bổ trợ.

## 4. Mô hình chung: inject, transport, extract và tạo span

Bất kể transport nào, một lời gọi có hướng đi đều có bốn thao tác:

~~~text
Bên gửi
  1. Có Context hiện tại, chứa SpanContext hợp lệ.
  2. Tạo CLIENT hoặc PRODUCER span cho lần gửi (nếu phù hợp).
  3. INJECT context đang active vào carrier.
  4. Gửi HTTP request / RPC / message.

Transport
  5. Mang các header/metadata tương ứng tới đích.

Bên nhận
  6. EXTRACT context từ carrier.
  7. Tạo SERVER hoặc CONSUMER span, chọn parent/link theo semantics.
  8. Kích hoạt context của span khi xử lý nghiệp vụ.
  9. Kết thúc span, ghi lỗi/trạng thái và export telemetry nếu được cấu hình.
~~~

**Inject** nghĩa là ghi thông tin context vào các trường của carrier, ví dụ HTTP headers hoặc record headers. **Extract** nghĩa là đọc các trường đó, kiểm tra và tạo ra một context có thể dùng làm parent hoặc link cho công việc mới.

Quy tắc thực hành:

- Ở phía gửi, inject **sau khi span đại diện cho lời gọi gửi đã được active**; không inject context quá cũ của span cha nếu bạn muốn thể hiện đúng hop.
- Ở phía nhận, extract trước khi tạo SERVER/CONSUMER span và giữ context được extract trong phạm vi xử lý.
- Thư viện instrumentation có thể làm tự động qua interceptor/middleware. Không chồng thêm logic inject/extract thủ công vào cùng điểm mà không biết cơ chế hiện có, vì dễ tạo span trùng hoặc parent sai.
- Kết thúc span hay gọi exporter không tự động đưa context tới service tiếp theo; propagation vẫn cần được cấu hình rõ.

## 5. Chuẩn W3C Trace Context

Định dạng phổ biến cho trace context trên HTTP là chuẩn **W3C Trace Context**, với hai trường chính:

- `traceparent`: chứa phiên bản định dạng, trace ID, ID của span tại phía gửi và các trace flags.
- `tracestate`: mang trạng thái bổ sung theo vendor hoặc hệ thống tracing, phục vụ tính tương thích; có thể không xuất hiện.

Ví dụ HTTP request:

~~~http
GET /inventory/items/42 HTTP/1.1
Host: inventory.internal
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: acme=route1
~~~

Cấu trúc `traceparent` phiên bản `00`:

~~~text
00 - 4bf92f3577b34da6a3ce929d0e0e4736 - 00f067aa0ba902b7 - 01
│                 │                         │              │
│                 │                         │              └─ trace flags
│                 │                         └──────────────── span ID phía gửi
│                 └────────────────────────────────────────── trace ID (16 byte)
└──────────────────────────────────────────────────────────── version
~~~

- `00` là version của định dạng, không phải ID hệ thống.
- Trace ID gồm 32 ký tự hex (128-bit), không hợp lệ nếu toàn số 0.
- Parent ID trong header gồm 16 ký tự hex (64-bit), không hợp lệ nếu toàn số 0. Nó đại diện cho span phía gửi để receiver dùng làm **remote parent**.
- Trace flags có 2 ký tự hex; bit thấp `01` thể hiện cờ `sampled`. Cờ sampled **không bảo đảm** dữ liệu span cuối cùng đã được xuất hay lưu trong backend.
- `tracestate` không phải nơi lưu dữ liệu nghiệp vụ tự do; định dạng và kích thước của nó có ràng buộc theo chuẩn.

Các trường truyền trên wire có thể thay đổi ở mỗi hop: **trace ID giữ nguyên** khi cùng một trace được tiếp nối bằng parent–child, còn **parent ID thay đổi** theo span của hop gửi tiếp theo. Vì vậy không nên chép nguyên `traceparent` của request đến mọi downstream nếu đang tạo CLIENT span mới.

### Baggage là trường riêng

W3C Baggage dùng header `baggage`, ví dụ:

~~~http
baggage: rollout.group=canary,region=apac
~~~

Baggage hỗ trợ chuyển một ít ngữ cảnh cấp ứng dụng qua nhiều hop nhưng có thể lan rất xa và bị gửi tới bên thứ ba nếu instrumentation không được kiểm soát. Baggage **không tự động** tạo span attributes và cũng không phải một kênh bảo mật. Không đặt access token, cookie, dữ liệu cá nhân, thông tin thanh toán, nội dung thông điệp hoặc dữ liệu khách hàng vào baggage. Giới hạn khóa, kích thước, phạm vi truyền và độ tin cậy từ ingress.

## 6. Propagation qua HTTP

Một request đồng bộ thường trải qua ba lớp: inbound HTTP server, ứng dụng, outbound HTTP client.

### 6.1. Ở HTTP server

Middleware hoặc server instrumentation nên:

1. Đọc `traceparent`/`tracestate` hợp lệ từ header đến (nếu có).
2. Tạo SERVER span có remote parent từ context nhận được; nếu không có context hợp lệ, bắt đầu một trace mới.
3. Kích hoạt span trong phạm vi request; các span ở handler, repository và downstream client sẽ trở thành con khi kế thừa đúng context.
4. Ghi trạng thái HTTP, lỗi và thời gian; kết thúc span khi request xử lý xong.

Không nên dùng incoming `traceId` làm bằng chứng danh tính người dùng. Caller có thể tự tạo hoặc sửa các header này; xử lý chúng như dữ liệu quan sát không đáng tin, theo chính sách của gateway.

### 6.2. Ở HTTP client

Trước outbound call:

1. Tạo CLIENT span, hoặc để HTTP instrumentation làm việc này.
2. Inject context của CLIENT span vào request headers.
3. Thực hiện network call.
4. Ghi status, exception, duration; kết thúc span dù thành công hay thất bại.

Receiver sẽ tạo SERVER span mới với parent là CLIENT span phía gửi. Hai span dùng cùng trace ID nếu tiếp nối một trace.

~~~text
Order Service
  SERVER span: POST /orders
    CLIENT span: GET /inventory  --------- HTTP headers -------->
                                                 Inventory Service
                                                   SERVER span: GET /inventory
                                                     INTERNAL span: queryStock
~~~

### 6.3. Cần quan sát những thành phần trung gian nào?

- **API Gateway, CDN, ingress, load balancer:** có thể tạo SERVER/CLIENT spans của riêng mình, bắt đầu trace mới hoặc lọc header.
- **Proxy và service mesh:** cần kiểm tra việc forwarding `traceparent` và `tracestate`; route timeout/retry có thể tạo nhiều downstream attempts.
- **HTTP client khác nhau:** WebClient, RestClient, Feign, Java HttpClient, OkHttp có cơ chế instrumentation khác nhau; cấu hình một lần tại nơi thống nhất.
- **Gateway đến dịch vụ bên ngoài:** quyết định có propagate trace headers hay không theo chính sách tin cậy và quyền riêng tư. Trace context có thể là metadata nhạy cảm về topology; không gửi baggage nội bộ ra ngoài một cách mặc định.

Một request thất bại có thể vẫn có trace hoàn chỉnh; propagation và xử lý lỗi là hai nhiệm vụ riêng. Hãy gắn error status/exception vào span thay vì mất context khi exception được throw.

## 7. Propagation qua RPC, đặc biệt gRPC

RPC là lời gọi thủ tục giữa các service, nhưng về tracing vẫn cần **inject ở client → transport metadata → extract ở server**. Với gRPC, carrier phổ biến là metadata. Interceptor thường là vị trí phù hợp để xử lý propagation:

~~~text
Order Service
  gRPC client interceptor
     -> tạo CLIENT span
     -> inject context vào gRPC metadata
     -> gọi CheckStock(request)
                 |
                 v
         Inventory gRPC server interceptor
           -> extract context từ metadata
           -> tạo SERVER span với remote parent
           -> kích hoạt context
           -> chạy handler
~~~

Về mặt logic, các trường W3C có thể xuất hiện như metadata text dạng `traceparent` và `tracestate` khi hai đầu đã thống nhất propagator. Một số stack còn hỗ trợ định dạng riêng; không mặc định mọi gRPC client/server hay thư viện tracing cùng dùng một định dạng. **Tương thích propagator phải được kiểm tra ở cả hai phía**.

Một số lưu ý:

- Metadata gRPC có quy tắc về key, encoding và kích thước; đừng tự chuyển nguyên HTTP request headers không kiểm soát vào RPC metadata.
- Deadline gRPC và trace context là hai khái niệm khác nhau. Trace propagation không tự truyền deadline nghiệp vụ hay ngược lại.
- Unary RPC có một lần nhận/trả, dễ mô hình CLIENT–SERVER. Streaming RPC có nhiều message trong một stream; cần quyết định span nào bao trùm stream và có cần tạo span/event cho từng message hay không, tránh số span vô hạn.
- Retry ở gRPC client hoặc mesh có thể tạo nhiều attempt. Instrumentation cần giúp phân biệt logical RPC với từng attempt nếu ứng dụng cần phân tích retry.
- Server interceptor cần kích hoạt và đóng scope an toàn để tránh context của request A rò sang request B trên thread tái sử dụng.

Không nên tự viết interceptor khi Java agent hoặc instrumentation của framework đã tạo đúng spans; trước hết xác minh trace qua một RPC thực.

## 8. Propagation qua message broker

Thông điệp khác HTTP/RPC ở chỗ **producer và consumer không nhất thiết chạy đồng thời**. Broker có thể lưu message hàng phút, gửi lại, gửi đến nhiều consumer hoặc gom batch. Dẫu vậy, mỗi thông điệp vẫn có thể mang span context trong metadata:

~~~text
Order Service
  PRODUCER span: publish OrderCreated
     ├─ payload: {orderId, ...}
     └─ headers:
          traceparent = ...
          tracestate  = ...
          baggage     = ... (nếu được phép)
                    |
                    v
               Kafka / RabbitMQ
                    |
                    v
Notification Worker
  extract(headers)
  CONSUMER span: process OrderCreated
    INTERNAL span: render template
    CLIENT span: send email
~~~

**Không chèn trace context vào phần dữ liệu nghiệp vụ nếu broker đã có metadata headers** và cả producer lẫn consumer hỗ trợ trường đó. Payload nên tuân theo schema nghiệp vụ; tracing metadata có lifecycle và chính sách khác với nội dung business.

### 8.1. Producer làm gì?

- Tạo một PRODUCER span cho hành động gửi (hoặc dùng instrumentation sẵn có).
- Inject context tại thời điểm tạo message, khi PRODUCER span đang active.
- Ghi trace context vào **headers của từng record/message**.
- Chỉ kết thúc producer span tại mốc phù hợp với hợp đồng gửi (ví dụ broker đã xác nhận), không đợi consumer xử lý xong.
- Với retry gửi, quản lý idempotency của broker và tránh hiểu nhầm rằng mỗi lần gửi đều đại diện cho một event nghiệp vụ mới.

Ở Kafka, headers gắn với record. Ở RabbitMQ/AMQP, application headers có thể thuộc message properties. API cụ thể khác nhau nhưng thao tác ngữ nghĩa giống nhau.

### 8.2. Consumer làm gì?

- Đọc headers **của đúng message đang xử lý**.
- Extract context rồi chọn parent hay link cho CONSUMER/processing span.
- Kích hoạt context khi xử lý, kể cả các outbound HTTP/RPC và producer span phát event tiếp theo.
- Ghi exception, retry, reject/dead-letter và kết thúc span trước khi release scope.
- Acknowledge message theo yêu cầu nghiệp vụ và broker; ack không tự đồng nghĩa với hoàn tất trace.

Nếu message thiếu header hoặc context không hợp lệ, consumer vẫn xử lý theo nghiệp vụ, thường bắt đầu trace mới và ghi metric về trường hợp mất propagation.

### 8.3. Redelivery và retry

Một message được giao lại không phải request HTTP chạy lại từ đầu. Hai lần tiêu thụ có thể có:

- Cùng message ID và cùng trace context của producer.
- Hai CONSUMER spans riêng, mỗi span mô tả một delivery/processing attempt.
- Thời điểm nhận, nguyên nhân retry và trạng thái thành công khác nhau.

Không được dùng trace ID để chống xử lý trùng. Idempotency và deduplication cần khóa nghiệp vụ/message ID cùng trạng thái xử lý bền vững. Trace phục vụ quan sát, không thay thế cơ chế đúng đắn dữ liệu.

## 9. Chọn parent–child hay span link

Hai loại quan hệ thường được dùng sai nhất ở message-driven systems.

### Parent–child

Dùng khi một hoạt động trực tiếp tiếp tục công việc của **một context cha rõ ràng**.

Ví dụ: HTTP client → HTTP server; gRPC client → gRPC server; producer message đơn → consumer process khi bạn quyết định nối trace và chỉ có một nguồn.

~~~text
Trace 1
  create order
    publish order-created
      consume order-created
        send email
~~~

Ưu điểm: giao diện trace nhìn thấy chuỗi thực thi trong một trace, tiện phân tích mối quan hệ tuyến tính. Cần cân nhắc độ dài trace và sự phụ thuộc vào thời gian lưu trữ/sampling nếu message xử lý rất lâu.

### Span link

Dùng khi có **nhiều nguyên nhân**, quá trình được khởi động thành trace độc lập, hoặc không phù hợp chọn một upstream làm parent.

Ví dụ batch consumer xử lý ba messages từ ba producers:

~~~text
Trace A: Producer A ----\
Trace B: Producer B -----+----> Trace D: batch processing span
Trace C: Producer C ----/                (3 links)
~~~

Một span có **một parent** nhưng có thể có **nhiều links**. Nếu chọn Producer A làm parent của cả batch, sự thật rằng B và C cũng gây ra batch có thể bị che khuất. Links biểu diễn đầy đủ quan hệ mà không ép trace khác chung một cây.

Phân biệt:

| Trường hợp | Quan hệ gợi ý | Lý do |
|---|---|---|
| HTTP request gọi service khác | Parent–child | Một lời gọi đồng bộ có remote parent rõ. |
| Unary gRPC call | Parent–child | Một request RPC tương ứng một parent. |
| Consumer xử lý đúng một message | Parent–child **hoặc** link theo chiến lược instrumentation | Có quan hệ trực tiếp; cân nhắc cách nối trace bất đồng bộ. |
| Batch gồm nhiều messages | Links đến từng message context | Có nhiều nguồn gây ra cùng một batch. |
| Workflow mới được kích hoạt từ event nhiều giờ trước | Trace mới + link thường hợp lý | Vòng đời quan sát độc lập, vẫn giữ quan hệ nhân quả. |
| Một request HTTP phát nhiều events | Mỗi PRODUCER span có parent hiện tại | Nhiều nhánh phát sinh từ cùng tác vụ. |
| Retry processing cùng một message | Các attempt spans riêng, cùng context nguồn có thể được link | Phân biệt lần thử mà vẫn theo được nguyên nhân. |

**Không có quy tắc tuyệt đối rằng mọi consumer bắt buộc là con của producer.** Chọn theo semantic convention, instrumentation đang dùng và điều bạn cần quan sát. Với batch, nên tạo links **ngay lúc khởi tạo span** để sampler có thể cân nhắc thông tin link khi quyết định sampling, nếu implementation hỗ trợ.

## 10. Java/OpenTelemetry: inject và extract không phụ thuộc transport

OpenTelemetry Java cung cấp API để biểu diễn `Context`, `Span` và `TextMapPropagator`. Ví dụ dưới đây dùng một `Map<String,String>` làm carrier minh họa; tại HTTP/gRPC/message broker thực tế, bạn cần adapter đọc/ghi header/metadata của transport.

Ví dụ giả định dự án đã thiết lập OpenTelemetry SDK/propagator phù hợp (thông qua Java agent hoặc cấu hình ứng dụng). Nếu chưa cấu hình SDK, API có thể hoạt động theo chế độ no-op và không tạo trace có thể quan sát.

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import io.opentelemetry.context.propagation.TextMapGetter;
import io.opentelemetry.context.propagation.TextMapPropagator;

import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

public final class MessageTracePropagation {
    private static final OpenTelemetry OTEL =
            GlobalOpenTelemetry.get();

    private static final Tracer TRACER =
            OTEL.getTracer("example.message-worker");

    private static final TextMapPropagator PROPAGATOR =
            OTEL.getPropagators().getTextMapPropagator();

    private static final TextMapGetter<Map<String, String>> GETTER =
            new TextMapGetter<>() {
                @Override
                public Iterable<String> keys(Map<String, String> carrier) {
                    return carrier.keySet();
                }

                @Override
                public String get(Map<String, String> carrier, String key) {
                    if (carrier == null) {
                        return null;
                    }
                    for (Map.Entry<String, String> entry : carrier.entrySet()) {
                        if (entry.getKey().equalsIgnoreCase(key)) {
                            return entry.getValue();
                        }
                    }
                    return null;
                }
            };

    // Gọi sau khi producer span đã được kích hoạt.
    public static Map<String, String> headersForPublish() {
        Map<String, String> headers = new HashMap<>();
        PROPAGATOR.inject(Context.current(), headers, Map::put);
        return headers;
    }

    // Cần gọi trong phạm vi nhận/xử lý một message cụ thể.
    public static void processMessage(
            Map<String, String> receivedHeaders,
            Runnable businessHandler) {

        Context remoteParent = PROPAGATOR.extract(
                Context.root(),
                receivedHeaders,
                GETTER
        );

        Span consumerSpan = TRACER.spanBuilder("message.process")
                .setSpanKind(SpanKind.CONSUMER)
                .setParent(remoteParent)
                .startSpan();

        // Dùng remoteParent.with(span) để giữ các phần context đã extract.
        try (Scope scope = remoteParent.with(consumerSpan).makeCurrent()) {
            businessHandler.run();
        } catch (RuntimeException ex) {
            consumerSpan.recordException(ex);
            consumerSpan.setStatus(StatusCode.ERROR);
            throw ex;
        } finally {
            consumerSpan.end();
        }
    }
}
~~~

Để thể hiện đầy đủ producer, luồng gọi nên là:

~~~java
Span producerSpan = TRACER.spanBuilder("order-created.publish")
        .setSpanKind(SpanKind.PRODUCER)
        .startSpan();

try (Scope scope = producerSpan.makeCurrent()) {
    Map<String, String> headers = headersForPublish();
    // brokerClient.publish(payload, headers);
} finally {
    producerSpan.end();
}
~~~

Trong đoạn producer rút gọn này, `TRACER` và `headersForPublish` là các thành phần đã khai báo ở class minh họa; khi đưa vào mã thật, gọi qua class hoặc giữ trong cùng class cho đúng phạm vi. Với API gửi async, thời điểm kết thúc span cần gắn với completion của thao tác gửi; ví dụ trên cố ý chỉ minh họa **thứ tự span → inject → publish**.

Các điểm thiết kế cần nhớ:

- `Context.root()` giúp tránh vô tình kế thừa một context còn active không liên quan trên thread consumer.
- `setParent(remoteParent)` chỉ định parent span từ header nhận được. Nếu không có remote span hợp lệ, instrumentation có thể bắt đầu trace mới theo chính sách.
- `remoteParent.with(consumerSpan).makeCurrent()` đặt consumer span vào context đã extract, bảo toàn các thành phần context phù hợp như baggage.
- `Scope` phải được đóng bằng `try-with-resources`, đặc biệt trong thread pool.
- `TextMapPropagator` phù hợp các carrier dạng text; gRPC binary metadata, message headers có byte-array, hoặc transport riêng có thể cần adapter/codec khác.
- Nếu workflow muốn **trace mới + link** thay cho parent–child, tạo span root theo đúng API và thêm `SpanLink` bằng context nhận được khi bắt đầu span; không dùng đoạn `setParent` nguyên xi.

Ví dụ không cài đặt exporter, sampler, authentication hoặc broker adapter. Trong ứng dụng Spring Boot, có thể dùng instrumentation tự động rồi bổ sung span nghiệp vụ ở các điểm cần thiết; quan trọng nhất là kiểm tra rằng context được truyền qua ranh giới thực tế.

## 11. Context qua thread pool và xử lý bất đồng bộ trong một service

Propagation qua network có thể đúng, nhưng context vẫn bị mất **trước khi gửi** nếu công việc chuyển thread.

Ví dụ:

~~~java
// Rủi ro: task sẽ chạy sau trên thread khác.
executor.submit(() -> callInventory());
~~~

Nhiều hệ thống lưu current context theo thread-local hoặc cơ chế tương đương. Task ở executor không mặc nhiên có cùng active span với request thread. Nếu `callInventory()` bắt đầu CLIENT span từ context trống, nó có thể tạo trace mới.

Cách minh họa với OpenTelemetry Context:

~~~java
Context captured = Context.current();

executor.submit(() -> {
    try (Scope ignored = captured.makeCurrent()) {
        callInventory();
    }
});
~~~

Một số thư viện hỗ trợ `Context.taskWrapping(executor)` hoặc instrumentation cho executors để tự động nắm/khôi phục context. Cần chọn một đường nhất quán; không tự bọc lặp lại khi đã được instrumentation tự động.

Trong Reactor/WebFlux, Kotlin coroutine hoặc reactive streams, thread có thể thay đổi nhiều lần; không đơn giản giả định một thread-local được giữ xuyên suốt toàn pipeline. Dùng tích hợp context propagation đúng framework, và kiểm thử ở các ranh giới `publishOn`, `subscribeOn`, callback, scheduled task.

Đặc biệt lưu ý:

- **Capture context vào lúc lên lịch**, không phải lúc task bắt đầu sau đó.
- **Đóng scope** cả khi task throw exception, timeout hoặc bị hủy.
- **Không lưu Context làm singleton** cho nhiều request; như vậy dễ trộn trace của hai khách hàng.
- **Không chỉ copy MDC** vì MDC giúp log có ID nhưng không tạo đúng parent của outbound spans.
- **Không nối trace một cách giả tạo** cho job nền chỉ tình cờ được cùng thread xử lý; phải có causal context thực sự.

## 12. Tracing khi request phát event rồi kết thúc

Một HTTP request có thể trả `202 Accepted` sau khi ghi message vào broker. Consumer xử lý sau đó 30 giây hoặc vài phút.

~~~text
T=0 ms:    POST /exports
T=75 ms:   HTTP trả 202 + jobId
T=4 s:     Consumer lấy message
T=25 s:    Export xong và ghi object storage
~~~

Nếu dùng parent–child, span consumer có thể bắt đầu sau khi span HTTP cha đã kết thúc; **span không bắt buộc phải nằm trọn trong khoảng thời gian của span cha** để có causal relationship. Tuy nhiên, backend hiển thị trace và cơ chế sampling/retention phải hỗ trợ trường hợp span đến muộn.

Nếu xử lý rất dài hoặc có nhiều job/retry độc lập, tạo trace riêng cho job và link tới message producer thường phản ánh lifecycle tốt hơn. Để điều tra xuyên suốt, lưu thêm `jobId` hoặc `orderId` trong log/attributes có kiểm soát, và hỗ trợ truy vấn theo khóa nghiệp vụ.

**Dữ liệu nghiệp vụ** như order ID và message ID là nguồn tin về ý nghĩa công việc; **trace ID** chỉ là khóa quan sát. Không dùng trace context làm record bền vững duy nhất để tái dựng trạng thái quy trình hoặc quyết định idempotency.

## 13. Fan-out, fan-in và xử lý batch

### Fan-out: một request gọi nhiều downstream

~~~text
Order Service SERVER span
  |---- Inventory CLIENT span -> Inventory SERVER span
  |---- Pricing CLIENT span   -> Pricing SERVER span
  └---- Fraud CLIENT span     -> Fraud SERVER span
~~~

Ba lời gọi có thể chạy song song. Chúng dùng cùng trace ID nhưng mỗi CLIENT span có span ID riêng, và phía nhận tạo SERVER span có remote parent tương ứng. Thứ tự timeline và parent relationship giúp phát hiện nhánh chậm mà không cần ghép log thủ công.

### Fan-out: một event đến nhiều subscribers

~~~text
PRODUCER span: OrderCreated
  |---- Email CONSUMER span
  |---- Analytics CONSUMER span
  └---- Loyalty CONSUMER span
~~~

Mỗi subscriber xử lý riêng và có thể chọn parent–child hoặc link theo chính sách; không tạo **một span CONSUMER dùng chung** cho các process khác nhau. Nếu các consumer độc lập và chạy lâu, links có thể rõ hơn.

### Fan-in: gom nhiều thông điệp thành batch

~~~text
Producer of A ----\
Producer of B -----+--> Batch process span
Producer of C ----/        link(A), link(B), link(C)
~~~

Hệ thống cần phân biệt:

- Batch có bao nhiêu records.
- Mỗi record đến từ trace nào.
- Batch span là root hay có parent của worker scheduler.
- Bao nhiêu links được giữ trong giới hạn mà SDK/backend cho phép.
- Nếu xử lý lỗi một phần, record nào retry và record nào đã được xử lý.

Khi dùng instrumentation mặc định, hãy xem semantics của từng thư viện thay vì suy luận chỉ từ tên span. Một batch processing span có thể có cấu trúc parent/link khác hẳn consumer xử lý một record.

## 14. Sampling và propagation: vì sao span vẫn có thể không xuất hiện?

Một trace có thể bị thiếu trong giao diện quan sát dù header được truyền đúng.

**Head-based sampling** quyết định lấy mẫu sớm, thường dựa trên thông tin trong context; các downstream có thể tôn trọng cờ sampled nhưng cần chính sách nhất quán. **Tail-based sampling** quyết định khi collector đã quan sát thêm các span và có thể giữ trace có lỗi hoặc độ trễ cao, tùy cấu hình.

Nguyên nhân trace thiếu thường gồm:

1. **Propagation thất bại:** receiver không extract hoặc carrier bị proxy/broker bỏ.
2. **Span chưa được tạo:** thư viện chưa instrument loại HTTP/gRPC/broker đang sử dụng.
3. **Context bị mất trong thread/reactive boundary:** outbound span bắt đầu trace khác.
4. **Sampling drop:** một hoặc nhiều spans không được ghi nhận/xuất.
5. **Exporter/collector lỗi:** buffer đầy, quá tải, mạng gián đoạn hoặc backend từ chối.
6. **Trace đến muộn:** consumer xử lý sau request, backend hay giao diện chưa hiển thị đủ spans.
7. **Sai relationship:** trace khác nhau có links nhưng giao diện chỉ hiển thị parent–child.

Đừng kết luận propagation hỏng chỉ vì thiếu span trong một bản trace sampled. Xác minh carrier ở môi trường test an toàn, kiểm tra active/extracted span context và cấu hình collector trước khi sửa middleware.

## 15. Bảo mật, quyền riêng tư và giới hạn tin cậy

Trace context đến từ network là **dữ liệu do phía gửi cung cấp**, không phải chứng thực.

- Không dùng `traceId`, `spanId`, baggage hoặc `tracestate` để cấp quyền, xác thực request hoặc xác định tenant đáng tin cậy.
- Ở ingress, quyết định tiếp nhận hay bắt đầu trace mới theo chính sách; xử lý header sai định dạng, quá dài hoặc quá nhiều trường một cách an toàn.
- Không đưa bí mật, thông tin cá nhân, access token, cookie, nội dung request body hay thông tin thanh toán vào baggage/trace attributes.
- Khi đi qua ranh giới tổ chức, kiểm tra việc forward metadata: có thể cần xóa baggage, lọc tracestate hoặc bắt đầu trace mới và lưu một liên kết nội bộ phù hợp.
- Áp dụng giới hạn kích thước headers và số attributes/links; tránh phụ thuộc vào key có cardinality cao để làm metric labels.
- Không log toàn bộ incoming headers khi tìm lỗi propagation ở môi trường production vì có thể chứa dữ liệu nhạy cảm.
- Nếu cần quan sát theo tenant, dùng thuộc tính đã được chuẩn hóa/ẩn danh theo chính sách, không tin giá trị tenant đến từ header không xác thực.

Mục tiêu của propagation là nhìn thấy quan hệ nhân quả mà không biến hệ thống telemetry thành kênh truyền dữ liệu tùy ý giữa những service.

## 16. Chiến lược triển khai trên Spring Boot/microservices

Một cách triển khai có kiểm soát:

**Bước 1 — Chọn chuẩn chung.** Thống nhất định dạng W3C Trace Context cho các đường text headers; xác định rõ khi nào truyền baggage và các ngoại lệ ở external boundaries.

**Bước 2 — Chọn stack instrumentation.** Với ứng dụng Java/Spring Boot, xem xét OpenTelemetry Java agent hoặc instrumentation/observability đã tích hợp. Mỗi service phải có cấu hình exporter, resource attributes và tên service có ý nghĩa. Tránh tạo span trùng nếu chạy đồng thời nhiều cơ chế.

**Bước 3 — Gắn inbound.** Server instrumentation phải extract context ở HTTP controller và gRPC server; consumer phải extract metadata từ mỗi message.

**Bước 4 — Gắn outbound.** HTTP/gRPC client instrumentation phải inject context; producer broker phải inject đúng record/message headers. Đừng chỉ thêm tracing vào controller rồi quên client.

**Bước 5 — Xử lý async boundaries.** Executor, scheduled task, reactive framework, callback và message worker phải capture/restore context theo thiết kế.

**Bước 6 — Xác định parent/link cho messaging.** Tài liệu hóa một message, batch, redelivery, long-running workflow và fan-in. Bảo đảm trace không xuyên ranh giới nghiệp vụ không mong muốn.

**Bước 7 — Bổ sung correlation.** Log có `trace_id`/`span_id`; thuộc tính nghiệp vụ hữu ích như `messaging.message.id` hoặc `order.id` được sử dụng theo convention/chính sách riêng. Không tự coi mọi tên ví dụ là semantic convention bắt buộc của OpenTelemetry.

**Bước 8 — Kiểm thử trên hệ thống chạy thật.** Tạo một request đi qua ít nhất một HTTP hop, một RPC hop, một message producer và một consumer; kiểm tra quan hệ được biểu diễn trong UI.

## 17. Thiết kế kiểm thử propagation

| Tình huống | Điều cần quan sát |
|---|---|
| HTTP A gọi HTTP B | Trace ID liên tục, SERVER span của B có quan hệ đúng với CLIENT span của A. |
| HTTP B gọi gRPC C | gRPC metadata mang context; C tạo SERVER span từ remote parent. |
| Producer gửi một message | Record headers có trace context và không lẫn dữ liệu nghiệp vụ nhạy cảm. |
| Consumer xử lý một message | Processing span có parent hoặc link tới đúng message context theo chiến lược đã chọn. |
| Hai messages từ hai traces tạo một batch | Batch span giữ links tới cả hai context, không gán sai một message thành nguồn duy nhất. |
| Message không có context | Consumer vẫn chạy, tạo trace mới khi cần và có metric/log chẩn đoán. |
| Context malformed/oversized | Không làm crash handler; áp dụng validation và trust boundary. |
| Request chuyển sang executor | Span tạo trong task liên hệ đúng request gốc; scope được đóng. |
| Retry hoặc redelivery | Tách được từng attempt, message ID và kết quả xử lý. |
| Trace lấy mẫu hoặc collector ngắt | Ứng dụng vẫn hoạt động; phân biệt lỗi sampling/export với lỗi propagation. |
| Message tới sau nhiều phút | Span/link vẫn thể hiện causal relationship hoặc giải thích được giới hạn backend. |

Thực hiện một phép thử thực tế:

1. Tạo request có ID nghiệp vụ test duy nhất.
2. Gọi qua Gateway → Order (HTTP) → Inventory (gRPC).
3. Cho Order phát một event vào broker, sau đó worker tiêu thụ event.
4. Từ trace viewer, mở root span của request và tìm HTTP SERVER, RPC CLIENT/SERVER, PRODUCER và CONSUMER.
5. Nếu consumer nằm ở trace khác, kiểm tra link từ processing span tới span context của producer.
6. Đối chiếu log của từng service theo trace ID và business ID; không chỉ kiểm tra text xuất hiện trong log.
7. Inject lỗi/độ trễ ở Inventory hoặc consumer để xác nhận các span lỗi vẫn liên hệ đúng nguồn.

Ở mức unit test, có thể dùng propagator/SDK test in-memory và carrier map để kiểm chứng inject/extract. Ở mức integration, cần ít nhất một test chạy qua network và broker thật hoặc test container tương đương, bởi propagation dễ hỏng do interceptor và adapter.

## 18. Phát hiện và sửa lỗi propagation phổ biến

### Lỗi 1: Mỗi service xuất hiện là một root trace

**Triệu chứng:** Gateway, Order, Inventory đều có trace ID khác; không có liên hệ parent/link.

**Khả năng:** outbound chưa inject, server chưa extract, propagator không tương thích hoặc middleware reset context. Kiểm tra một đường gọi ngắn với carrier đã biết trước khi xem toàn hệ thống.

### Lỗi 2: Trace đúng đến Order nhưng mất ở gRPC

**Khả năng:** ứng dụng chỉ cấu hình HTTP instrumentation; gRPC interceptor không có, dùng định dạng metadata khác, hoặc RPC được gọi từ thread mất context. Quan sát active context ngay trước gRPC call và context extracted ở handler test.

### Lỗi 3: Trace đứt ngay tại broker

**Khả năng:** producer inject vào application object nhưng không vào message headers; consumer bỏ headers khi deserialize; batch processing không khôi phục từng record context. Dùng adapter tại record boundary và chọn parent/link có chủ đích.

### Lỗi 4: Hai request khác nhau bị nối vào một trace

**Khả năng:** giữ context trong singleton/static field, quên đóng Scope hoặc dùng shared mutable carrier giữa concurrent requests. Context phải theo request/message, scope phải đóng sau từng tác vụ.

### Lỗi 5: Log có trace ID nhưng trace UI không nối

**Khả năng:** copy MDC mà không copy OpenTelemetry Context, hoặc gửi một correlation ID giống nhau nhưng các span vẫn khác trace. Phân biệt thông tin log và remote parent thực sự.

### Lỗi 6: Consumer có trace mới dù instrumentation đã hoạt động

Không phải lúc nào cũng là lỗi. Hãy kiểm tra **span links**: một trace mới có link đúng tới producer có thể là thiết kế phù hợp cho message asynchronous/batch. Sửa chỉ khi không có quan hệ như mong muốn.

### Lỗi 7: Trace có context nhưng mất spans

Kiểm tra sampling, exporter, collector, backend retention và spans đến muộn. Propagation không đồng nghĩa với việc mọi span luôn được lưu.

## 19. Bài tập áp dụng

Hệ thống có đường đi:

~~~text
POST /checkout
    |
    v
Checkout Service
    |-- gRPC -> Fraud Service
    |
    |-- publish PaymentRequested (message M1)
    v
Broker
    |
    v
Payment Worker
    |-- HTTP -> Payment Provider
    |-- publish PaymentCompleted (message M2)
    v
Reporting Consumer
~~~

Giả sử Checkout nhận `traceparent` hợp lệ từ Gateway, Fraud chạy trên một server khác, và Payment Worker xử lý M1 sau 20 giây.

**Câu hỏi:**

1. Context cần đi qua những carrier nào?
2. Nếu Fraud tạo trace mới, nên kiểm tra điểm inject hay extract nào đầu tiên?
3. Payment Worker có bắt buộc phải giữ cùng trace ID của Checkout không?
4. Nếu Reporting Consumer xử lý một batch gồm M2 của 20 giao dịch, parent–child hay links thể hiện rõ nguyên nhân hơn?
5. Trace ID có thể thay thế idempotency key cho Payment Provider không?
6. Nếu log có request ID nhưng không thấy liên kết span trong trace viewer, cần phân biệt hai loại context nào?

**Gợi ý tự đối chiếu:**

- Carrier lần lượt là incoming HTTP headers, gRPC metadata, headers của M1, outbound HTTP headers của Payment Provider (theo trust policy), headers của M2 và metadata của batch.
- Với Fraud, kiểm tra context active ở gRPC client rồi việc inject vào metadata; tiếp theo kiểm tra interceptor server extract và tạo remote parent. Đồng thời xét việc chuyển thread.
- Payment Worker có thể nối trace bằng parent–child, hoặc tạo trace mới với link tới producer của M1; lựa chọn phụ thuộc chiến lược tracing asynchronous.
- Batch 20 messages có nhiều nguyên nhân; một batch processing span với links đến từng message context thường rõ hơn việc gán một message làm parent.
- Trace ID không bảo đảm duy nhất cho mỗi giao dịch và không có semantics idempotency; dùng khóa giao dịch do nghiệp vụ quản lý.
- Request/correlation ID trong log khác với `SpanContext` được truyền để thiết lập parent/link.

## 20. Ghi nhớ

Để trace đi xuyên microservices, mỗi ranh giới phải có **hai đầu nhất quán**: bên gửi inject context vào carrier và bên nhận extract nó trước khi tạo span. Với HTTP và unary RPC, quan hệ parent–child thường trực tiếp. Với message đơn, batch, fan-in và workflow xử lý muộn, cần chủ động chọn parent–child hoặc links theo quan hệ nhân quả và lifecycle thực tế.

Propagation chỉ giải quyết kết nối ngữ cảnh; chất lượng quan sát còn phụ thuộc instrumentation, scope qua async/thread boundaries, sampling, exporter, chính sách bảo mật và khả năng của backend tracing. Khi chẩn đoán sự cố, hãy lần theo **trace ID, span ID, parent/link và carrier tại từng hop** để tìm đúng chỗ đứt mạch.
