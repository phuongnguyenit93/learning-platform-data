# Correlation ID và liên kết lỗi với dữ liệu chẩn đoán

## 1. Từ một phản hồi lỗi đến nguyên nhân trong hệ thống phân tán

Một khách hàng gọi **POST /orders** để tạo đơn hàng và nhận lỗi **500 Internal Server Error**. Phía sau REST API có API gateway, dịch vụ đơn hàng, dịch vụ tồn kho, cơ sở dữ liệu và hàng đợi sự kiện. Người dùng chỉ biết yêu cầu không thành công; đội vận hành cần xác định yêu cầu nào, tại thời điểm nào, đi qua những thành phần nào và hỏng ở đâu.

Nếu mỗi service ghi một log riêng không có khóa liên hệ, kỹ sư phải dò theo timestamp, địa chỉ mạng hoặc dữ liệu người dùng. Cách này chậm, dễ nhầm khi hàng nghìn request chạy đồng thời và có thể dẫn đến việc thu thập quá nhiều dữ liệu nhạy cảm. **Correlation ID** giải quyết vấn đề tìm đúng nhóm sự kiện liên quan đến một yêu cầu hay một hoạt động.

Ví dụ một phản hồi có cấu trúc:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
X-Correlation-ID: 1cdb7c7a-e1cc-420a-9239-138aa1524cb7
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/internal-error",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "Không thể hoàn tất yêu cầu. Hãy thử lại theo hướng dẫn của dịch vụ.",
  "code": "INTERNAL_ERROR",
  "correlationId": "1cdb7c7a-e1cc-420a-9239-138aa1524cb7"
}
~~~

Khi liên hệ hỗ trợ, người dùng cung cấp **correlationId**. Kỹ sư tra cứu log và trace theo định danh đó, thấy nguyên nhân là lệnh gọi Inventory Service bị timeout. Mã lỗi dành cho client và chi tiết kỹ thuật trong hệ thống chẩn đoán có **vai trò khác nhau**: client có đủ thông tin để nhận biết sự cố và liên hệ hỗ trợ, nhưng không nhận stack trace, connection string hoặc dữ liệu người dùng khác.

Trong module **INTEGRATION_API_REST**, kiến thức này kết nối thiết kế resource/URI/phương thức HTTP, mã trạng thái, hợp đồng lỗi, OpenAPI, xác thực/phân quyền, idempotency, cache và kiểm thử API bằng Java/Spring. Correlation ID là **cơ chế quan sát và chẩn đoán**, không phải một mã trạng thái HTTP mới và cũng không thay thế xử lý lỗi đúng ngữ nghĩa.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **correlation ID, request ID, trace ID, span ID, error ID** và **idempotency key**.
2. Quy định điểm sinh, điểm tin cậy, cách truyền và thời gian tồn tại của định danh qua HTTP, service và tác vụ bất đồng bộ.
3. Thiết kế response theo **RFC 9457 Problem Details**, liên kết được tới log/trace mà không lộ dữ liệu nội bộ.
4. Thực hiện cơ chế correlation ID ở Java/Spring MVC bằng filter, MDC và exception handler.
5. Biết khi nào dùng **W3C Trace Context**, trace/span và OpenTelemetry thay vì chỉ ghi một header tùy biến.
6. Thiết kế truy vấn chẩn đoán, kiểm soát quyền, lưu trữ, sampling và hạn chế thông tin nhạy cảm.
7. Kiểm thử propagation, concurrency, retry, async processing và xử lý lỗi ở gateway lẫn ứng dụng.

## 2. Phân biệt các định danh và mục đích của chúng

Những định danh dưới đây có thể cùng xuất hiện trong một luồng, nhưng **không đồng nghĩa**:

| Định danh | Phạm vi thường dùng | Được tạo ở đâu? | Câu hỏi giải đáp |
|---|---|---|---|
| **Correlation ID** | Một chuỗi xử lý có liên hệ, thường bắt đầu từ request vào hệ thống | Gateway hoặc entrypoint đáng tin cậy | Những log/sự kiện nào thuộc cùng luồng xử lý? |
| **Request ID** | Một lần nhận hoặc xử lý HTTP request cụ thể | Gateway hoặc từng service | Đây là lần gọi HTTP nào, kể cả khi cùng hoạt động có nhiều lần gọi? |
| **Trace ID** | Một distributed trace gồm nhiều span | Thành phần khởi tạo trace theo hệ thống tracing | Toàn bộ hành trình nhân-quả được quan sát ở những span nào? |
| **Span ID** | Một đơn vị công việc trong một trace | Instrumentation ở service/client | Đoạn xử lý cụ thể nào bị chậm hoặc lỗi? |
| **Error/incident occurrence ID** | Một lần phát sinh lỗi hoặc hồ sơ chẩn đoán | Error handling hoặc hệ thống incident | Lỗi cụ thể nào cần điều tra? |
| **Idempotency key** | Một thao tác nghiệp vụ logic có thể bị gửi lại | Client theo hợp đồng API | Retry này là bản sao hay một thao tác mới? |
| **Business ID** | Một entity/process nghiệp vụ | Domain logic | Đơn hàng, thanh toán hay tài nguyên nào bị ảnh hưởng? |

**Ví dụ:** một người dùng nhấn “Thanh toán” một lần, mobile client gửi POST nhưng mất phản hồi rồi retry. Hệ thống có thể có **hai request ID** vì hai lần gửi HTTP, dùng **một idempotency key** để chống thu tiền trùng, và có một hoặc nhiều trace tùy chiến lược instrumentation. Correlation ID có thể giữ chung cho một chuỗi retry nếu hợp đồng/quy trình cho phép, hoặc được tạo mới ở mỗi lần request vào và liên hệ bằng idempotency key. **Phải định nghĩa phạm vi nhất quán**, không mặc định mọi định danh đều như nhau.

### 2.1. Correlation ID có phải trace ID không?

Không bắt buộc. Trong hệ thống đơn giản, một ứng dụng có thể chỉ dùng correlation ID để tìm log. Trong hệ thống có distributed tracing, **trace ID** đã liên kết các span; correlation ID là nhãn hỗ trợ tìm kiếm hoặc liên kết tới các sự kiện ngoài trace (audit, event, ticket hỗ trợ). Một tổ chức có thể chọn dùng trace ID làm correlation ID công khai, nhưng quyết định đó cần cân nhắc quyền riêng tư, cách sinh ID, sampling, vòng đời và việc một hoạt động có nhiều trace.

Không nên tự tạo trace ID bằng cách đổi tên một chuỗi tùy ý; chuẩn W3C yêu cầu định dạng trace ID và span ID cụ thể.

### 2.2. Correlation ID không phải token bảo mật

Correlation ID **không chứng minh danh tính**, không cấp quyền và không được dùng làm khóa bí mật để truy cập tài liệu chẩn đoán. Người biết correlation ID **không được tự động xem log, thông tin khách hàng hoặc dữ liệu của tenant khác**. Mọi endpoint nội bộ hỗ trợ tra cứu phải thực hiện xác thực, phân quyền và audit.

## 3. Phạm vi của ID trong kiến trúc REST

Một hệ thống nên thống nhất quy tắc tối thiểu:

1. Mỗi request đi vào từ bên ngoài có **một định danh công khai dùng cho hỗ trợ**, do entrypoint tin cậy phát hành hoặc chuẩn hóa.
2. Các service downstream nhận và ghi lại correlation ID trong ngữ cảnh xử lý, đồng thời truyền tới lời gọi nội bộ cần liên kết.
3. Mọi response lỗi do hệ thống kiểm soát có **correlation ID nhất quán** ở header và trong Problem Details khi hợp đồng công bố như vậy.
4. Trace context theo chuẩn được quản lý bởi instrumentation; không dùng correlation header thay thế ngữ cảnh cha/con của distributed trace.
5. Khi sinh job/event, correlation ID được lưu trong **metadata đáng tin cậy**, còn consumer tạo span hoặc trace liên quan theo cơ chế tracing phù hợp.
6. Khi lỗi xảy ra tại gateway/proxy trước ứng dụng, gateway vẫn cần phát mã lỗi và định danh để đội vận hành truy tìm ở **đúng lớp phát lỗi**.

~~~mermaid
flowchart LR
    USER[Web / Mobile Client] --> GW[API Gateway]
    GW --> API[Order API]
    API --> INV[Inventory Service]
    API --> DB[(Orders DB)]
    API --> BUS[[Event Bus]]
    BUS --> WK[Notification Worker]
    GW -. "Correlation ID / trace context" .-> API
    API -. "Context propagation" .-> INV
    API -. "Event metadata" .-> BUS
    GW --> OBS[(Logs / Traces / Metrics)]
    API --> OBS
    INV --> OBS
    WK --> OBS
    OBS --> SUP[Hệ thống chẩn đoán có phân quyền]
~~~

Một luồng có nhiều service không nhất thiết chỉ có một lỗi. Có thể có lỗi chính (Inventory Service timeout), nhiều lỗi dẫn xuất (Order API trả 503, worker không nhận event) và nhiều sự kiện vận hành cùng correlation ID. **Correlation ID chỉ gom nhóm**, còn trace/span, mã lỗi, timestamp và loại thao tác giúp dựng lại quan hệ nguyên nhân.

### 3.1. Chọn quy ước và phạm vi ổn định

| Chính sách | Gợi ý thực hành |
|---|---|
| Header công khai | Có thể dùng **X-Correlation-ID** theo hợp đồng sản phẩm; đây **không phải header HTTP chuẩn bắt buộc** |
| Hình thức ID | UUID v4 hoặc định dạng opaque, ngẫu nhiên, có giới hạn độ dài; không nhúng email, tên người dùng hay dữ liệu riêng |
| Điểm sinh | API gateway hoặc entrypoint đã xác thực được vai trò là nguồn phát hành |
| Client tự gửi ID | Chỉ chấp nhận từ bên tin cậy hoặc kiểm tra/chuẩn hóa; với client công khai có thể luôn thay bằng ID server |
| Header response | Trả lại ID đã xác lập; đủ để hỗ trợ tra cứu |
| Log | Gắn ID theo key có cấu trúc cho các sự kiện cần chẩn đoán |
| Bất đồng bộ | Truyền qua metadata message, không dựa vào thread-local sau khi request kết thúc |
| Retry | Xác định retry dùng ID mới hay giữ ID của hoạt động; lưu thêm request ID và idempotency key khi cần |
| Lưu trữ | Thời hạn và quyền tra cứu dựa trên yêu cầu vận hành/tuân thủ |

Nếu một hệ thống dùng header khác như **X-Request-ID**, tên đó cũng có thể hợp lệ theo hợp đồng riêng. Điều quan trọng là **tài liệu hóa và triển khai thống nhất** ở gateway, service, client và tài liệu hỗ trợ.

## 4. W3C Trace Context: truyền vết giữa các dịch vụ

Hệ thống tracing phân tán thường dựa trên **W3C Trace Context**, đặc biệt là header:

- **traceparent**: mang version, trace ID, parent span ID và trace flags.
- **tracestate**: dữ liệu trạng thái tracing của các nhà cung cấp theo quy tắc định dạng/giới hạn; không dùng để đặt dữ liệu nghiệp vụ nhạy cảm tùy tiện.

Ví dụ:

~~~http
GET /inventory/items/SKU-9 HTTP/1.1
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
X-Correlation-ID: 1cdb7c7a-e1cc-420a-9239-138aa1524cb7
~~~

Định dạng thông dụng của **traceparent**:

~~~text
version-trace-id-parent-id-trace-flags
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
   |--------------------------------|----------------|--|
      16 byte / 32 ký tự hex         8 byte / 16 hex  1 byte flags
~~~

Trong ví dụ, trace ID được dùng để tìm toàn bộ trace; **parent-id** đại diện span phát lệnh gọi. Service nhận tạo span của nó theo quan hệ cha/con mà công cụ tracing quản lý. Một trace có nhiều span ID nhưng cùng trace ID.

### 4.1. Không tự triển khai traceparent bằng nối chuỗi

Các SDK/tracing instrumentations của **OpenTelemetry**, Micrometer Tracing hoặc hệ thống tương đương có trách nhiệm parse, validate, propagate và tạo span. Tự ghép traceparent có thể gây sai định dạng, lẫn parent-id với current span-id, thay đổi trace ID ngoài ý muốn hoặc mất kết nối giữa các span.

Các header trace từ môi trường ngoài là **dữ liệu không đáng tin tuyệt đối**. Entry gateway cần có chính sách nhận/tạo lại context tại ranh giới tin cậy, giới hạn độ dài và định dạng. Không bao giờ cho phép client thay đổi trạng thái xác thực hay quyền nghiệp vụ thông qua traceparent/tracestate.

### 4.2. Baggage có phải nơi truyền mọi thuộc tính?

**W3C Baggage** cho phép lan truyền các thuộc tính dạng key/value giữa service, nhưng có thể đi qua nhiều ranh giới mạng, log và nhà cung cấp. Không đưa access token, password, email, số điện thoại, thông tin thanh toán hoặc dữ liệu nhạy cảm vào baggage. Chỉ truyền những thuộc tính thật sự cần, theo allowlist và chính sách quyền riêng tư.

Nếu cần **tenant ID**, cần dùng ngữ cảnh đã xác thực, có kiểm soát quyền và sự cô lập ở từng service; không coi baggage hoặc header client là bằng chứng tenant đang được phép truy cập.

## 5. Thiết kế phản hồi lỗi liên kết với chẩn đoán

### 5.1. Problem Details theo RFC 9457

RFC 9457 mô tả định dạng **application/problem+json** để diễn đạt lỗi HTTP API. Các trường cốt lõi gồm:

| Trường | Vai trò | Lưu ý |
|---|---|---|
| **type** | URI định danh **loại vấn đề** | Nên ổn định, có tài liệu khi được dereference |
| **title** | Tên ngắn, dễ hiểu của loại lỗi | Không cần nhúng dữ liệu riêng mỗi request |
| **status** | Mã HTTP tại thời điểm phát sinh | Phải phù hợp với status thực của response |
| **detail** | Diễn giải riêng của lần lỗi | Không lộ exception, SQL, secret hoặc dữ liệu nhạy cảm |
| **instance** | URI reference định danh **lần xuất hiện** của vấn đề | Có thể bỏ qua; không tự coi là đường dẫn public để tra log |
| **code** (mở rộng) | Mã lỗi nghiệp vụ có hợp đồng ổn định | Ví dụ **ORDER_CONFLICT** |
| **correlationId** (mở rộng) | Khóa hỗ trợ tìm bản ghi chẩn đoán | Không cấp quyền truy cập log |

RFC 9457 **không bắt buộc** dùng correlationId và code; đây là các **extension members** mà API cần công bố. Nếu muốn dùng **instance** như một URI duy nhất của lần lỗi, vẫn nên tách nó khỏi đường dẫn trang chẩn đoán nội bộ. Một URN dạng **urn:uuid:...** có thể được dùng nếu hợp đồng định nghĩa phù hợp, nhưng không bắt buộc.

### 5.2. Ví dụ lỗi nghiệp vụ có thể xử lý được

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
X-Correlation-ID: a45b0426-08be-4526-a762-e64e545269db
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/order-conflict",
  "title": "Order conflict",
  "status": 409,
  "detail": "Đơn hàng đã thay đổi. Hãy tải lại trạng thái trước khi cập nhật.",
  "code": "ORDER_CONFLICT",
  "correlationId": "a45b0426-08be-4526-a762-e64e545269db"
}
~~~

**409** giải thích trạng thái xung đột của tài nguyên/nghiệp vụ, còn **correlationId** giúp đội phát triển tìm các sự kiện liên quan. Trường code là hợp đồng ứng dụng; không thay thế status HTTP.

Các mã trạng thái khác vẫn phải đúng bản chất: **400** cho request không hợp lệ, **401/403** cho xác thực/phân quyền, **404** khi tài nguyên không tìm thấy, **412** cho điều kiện If-Match không đạt, **422** cho nội dung xử lý được nhưng vi phạm quy tắc, **429** khi rate limit, **503** khi tạm không phục vụ. Không biến mọi exception thành 500 chỉ để dễ gắn correlation ID.

### 5.3. Phân chia thông tin công khai và thông tin nội bộ

| Dữ liệu | HTTP response public | Log/trace nội bộ có phân quyền |
|---|---|---|
| HTTP status, mã lỗi ổn định | Có | Có |
| Correlation ID | Có theo hợp đồng | Có, để tra cứu |
| Thông báo hữu ích, không nhạy cảm | Có | Có thể ghi ở dạng mã |
| Stack trace, SQL query thô, connection string | Không | Chỉ khi cần, đã lọc secret và giới hạn truy cập |
| Access token, session, mật khẩu, private key | Không | **Không ghi** |
| Email/số điện thoại/nội dung tài liệu khách hàng | Tránh, chỉ khi nghiệp vụ thật sự cho phép | Hạn chế tối đa, làm sạch hoặc che theo chính sách |
| Link tới hệ thống log/trace nội bộ | Không | Có thể dùng trong công cụ hỗ trợ nội bộ |
| Trace ID/span ID | Tùy hợp đồng, không cần lộ | Có khi tracing đang hoạt động |

Thông điệp lỗi công khai nên đủ để người dùng hành động. Ví dụ **429** có thể bổ sung **Retry-After** khi phù hợp; **409/412** có thể hướng dẫn đọc lại tài nguyên; **500** nên tránh hứa rằng retry chắc chắn an toàn, nhất là với POST/PATCH có tác động cộng dồn.

## 6. Dữ liệu chẩn đoán cần lưu để tìm lỗi

Correlation ID chỉ hữu ích khi **log và telemetry đi kèm đủ ngữ cảnh** để tìm nguyên nhân. Một event log có cấu trúc minh họa:

~~~json
{
  "timestamp": "2026-11-18T09:12:44.125Z",
  "level": "ERROR",
  "service": "order-api",
  "environment": "prod",
  "event": "order.create.failed",
  "correlationId": "1cdb7c7a-e1cc-420a-9239-138aa1524cb7",
  "requestId": "req-845821",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "http.method": "POST",
  "http.route": "/orders",
  "http.status_code": 500,
  "error.code": "INVENTORY_TIMEOUT",
  "downstream.service": "inventory-service",
  "duration_ms": 2050
}
~~~

Các giá trị là ví dụ giả định. Trong môi trường thật nên dùng **route template** (như /orders/{id}) thay vì nguyên URI chứa ID, token hoặc query nhạy cảm. Log nên có timestamp có timezone, service, environment, event type, status, thời gian xử lý, mã lỗi và correlation/trace ID. Các trường như tenant ID, user ID hoặc resource ID chỉ ghi theo nguyên tắc tối thiểu, kiểm soát quyền và yêu cầu điều tra.

### 6.1. Log, trace, metric và audit giải quyết những câu hỏi khác nhau

| Dữ liệu | Dùng để tìm gì? | Giới hạn |
|---|---|---|
| **Structured logs** | Event, lỗi, kết quả kiểm tra nghiệp vụ, chi tiết thao tác | Có thể thiếu sự kiện, trùng log, hoặc bị giới hạn retention |
| **Distributed traces** | Đường đi service, span chậm/lỗi, quan hệ cha/con | Có thể bị **sampling**; không phải mọi request đều có trace được lưu |
| **Metrics** | Tỷ lệ lỗi, latency, throughput, saturation, xu hướng | Nhãn correlation ID trên mọi điểm đo gây cardinality rất cao |
| **Audit events** | Ai làm gì, lúc nào, trên tài nguyên nào, thay đổi nào được phép | Cần bảo vệ toàn vẹn, retention và quyền truy cập nghiêm ngặt |
| **Incident/ticket** | Diễn biến sự cố, người xử lý và kết luận | Không thay thế bằng chứng telemetry gốc |

Không dùng **correlationId làm nhãn cho mọi time-series metric**: mỗi ID mới tạo ra chuỗi thời gian mới, làm tăng cardinality và chi phí giám sát. Tập trung metric theo status, route template, service và nhóm lỗi; dùng log/trace cho truy vấn theo một ID cụ thể.

### 6.2. Liên kết các tầng khi tra cứu

Một công cụ chẩn đoán có thể cho phép kỹ sư:

1. Nhập correlation ID nhận từ khách hàng và khoảng thời gian ước lượng.
2. Tìm **gateway access log** để xác định route, status, request ID, vùng triển khai và trace ID.
3. Mở trace theo trace ID nếu có, tìm span bị lỗi hoặc chậm.
4. Tìm log của service downstream theo correlation ID/trace ID và thời điểm.
5. Đối chiếu với deployment version, dependency health, audit event và tình trạng DB/queue.
6. Ghi nhận kết luận bằng incident ID/ticket nội bộ; chỉ chia sẻ thông tin phù hợp với khách hàng.

**Thời điểm và service** vẫn rất quan trọng. Một correlation ID có thể được giữ qua nhiều retry, nhiều message hoặc các hệ thống không hoàn toàn đáng tin cậy. Không nên chỉ dựa vào một ID để gán trách nhiệm hoặc kết luận quan hệ nguyên nhân.

## 7. Java/Spring MVC: sinh correlation ID và đưa vào MDC

Với Spring MVC trên Servlet stack, một cách đơn giản là dùng **OncePerRequestFilter**. Filter chạy gần entrypoint, tạo một định danh do server kiểm soát, gắn vào request, response và **SLF4J MDC** để logger tự điền trong thời gian xử lý trên cùng thread.

### 7.1. Ví dụ filter

~~~java
import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class CorrelationIdFilter extends OncePerRequestFilter {
    public static final String HEADER = "X-Correlation-ID";
    public static final String ATTRIBUTE =
        CorrelationIdFilter.class.getName() + ".correlationId";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        // Biên public: tự phát hành ID để tránh tin header tùy ý từ client.
        String correlationId = UUID.randomUUID().toString();
        request.setAttribute(ATTRIBUTE, correlationId);
        response.setHeader(HEADER, correlationId);

        try (MDC.MDCCloseable ignored =
                 MDC.putCloseable("correlationId", correlationId)) {
            filterChain.doFilter(request, response);
        }
    }
}
~~~

Ví dụ này **cố ý tạo ID mới tại mỗi request public**. Nếu API gateway là nguồn phát hành ID đã được kiểm soát, service có thể nhận ID từ header **chỉ sau khi xác minh ranh giới tin cậy, định dạng và độ dài**. Tuyệt đối không dùng nguyên một giá trị client tự chọn đưa vào log: chuỗi quá dài, ký tự điều khiển hoặc nội dung giả mạo có thể gây **log injection, gây nhiễu truy vấn hoặc vượt giới hạn lưu trữ**.

**try-with-resources** bảo đảm gỡ key khỏi MDC khi filter kết thúc, tránh để thông tin của request A dính sang request B do thread pool tái sử dụng thread. MDC theo thread **không tự lan truyền an toàn** qua CompletableFuture, @Async, scheduler hoặc các luồng reactive; cần công cụ context propagation tương ứng.

### 7.2. Tạo response lỗi theo Problem Details

Một exception handler cho lỗi nghiệp vụ:

~~~java
import java.net.URI;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiErrorHandler {

    @ExceptionHandler(OrderConflictException.class)
    ResponseEntity<ProblemDetail> handleConflict(
            OrderConflictException ex,
            HttpServletRequest request) {

        ProblemDetail problem =
            ProblemDetail.forStatus(HttpStatus.CONFLICT);
        problem.setType(URI.create(
            "https://api.example.test/problems/order-conflict"));
        problem.setTitle("Order conflict");
        problem.setDetail(
            "Đơn hàng đã thay đổi. Hãy tải lại trước khi cập nhật.");
        problem.setProperty("code", "ORDER_CONFLICT");
        problem.setProperty(
            "correlationId",
            request.getAttribute(CorrelationIdFilter.ATTRIBUTE)
        );

        return ResponseEntity.status(HttpStatus.CONFLICT)
            .contentType(MediaType.valueOf("application/problem+json"))
            .body(problem);
    }
}
~~~

Ví dụ giả định đã có **OrderConflictException** và API dùng Spring Framework 6+/Spring Boot 3+. Cần đặt mã lỗi, exception mapping và chính sách response nhất quán cho những lỗi 4xx/5xx mà ứng dụng quản lý. Không mặc định thêm một handler **Exception.class** rồi luôn trả 500, vì cách đó có thể nuốt mất mã 400, 404, 405, 415 hoặc các lỗi validation do framework đã xác định.

Filter đã đặt header **X-Correlation-ID** trước khi gọi controller; handler lấy cùng giá trị để ghi vào body. Nếu lỗi sinh ở **reverse proxy, gateway hoặc servlet container trước filter**, Spring handler không nhận được request đó. Cần cấu hình correlation và error response tại lớp đã chặn request.

### 7.3. Log mà không lặp chi tiết hoặc để lộ dữ liệu

Trong service, sử dụng logger có cấu trúc. Ví dụ:

~~~java
private static final Logger log =
    LoggerFactory.getLogger(OrderService.class);

void createOrder(CreateOrderCommand command) {
    try {
        // Xử lý đơn hàng.
    } catch (InventoryUnavailableException ex) {
        log.error(
            "order.create.failed errorCode={} dependency={}",
            "INVENTORY_UNAVAILABLE",
            "inventory-service",
            ex
        );
        throw new OrderUnavailableException();
    }
}
~~~

Hệ thống logging phải được cấu hình để xuất key **correlationId** trong MDC ở mỗi event; chỉ đặt key bằng MDC không bảo đảm output đã có trường đó. Tránh logging cùng stack trace lặp lại ở **gateway, controller, service và repository** cho một lỗi; xác định nơi sở hữu log kỹ thuật chi tiết, các lớp khác dùng event ngắn gọn hoặc span status.

Không trả trực tiếp **ex.getMessage()** ra client nếu message chứa SQL, đường dẫn file, tên host, thông tin thư viện hoặc dữ liệu nhạy cảm. **Error code công khai** nên ổn định, trong khi chi tiết kỹ thuật có thể thay đổi theo implementation.

## 8. Propagation qua HTTP, event và async task

### 8.1. Gọi HTTP từ service sang service

Khi Order API gọi Inventory Service, cần có hai loại ngữ cảnh:

- **Trace context**: traceparent/tracestate do OpenTelemetry hoặc tracing instrumentation truyền để hình thành cây span.
- **Correlation ID**: nếu hợp đồng có header này, truyền cùng ID đã được phê duyệt tại biên nội bộ và log ở downstream.

Một lựa chọn là cấu hình interceptor/filter ở HTTP client (RestClient, WebClient, Feign hoặc thư viện tương ứng). Tránh lập lại đoạn tự thêm header ở mọi method nghiệp vụ vì rất dễ bỏ sót. Nếu service gọi nhà cung cấp bên ngoài, chỉ truyền header được hợp đồng cho phép, **không tự động gửi mọi nội bộ header**, thông tin tenant, baggage hoặc token.

### 8.2. Tác vụ bất đồng bộ và event

Khi publish một message:

~~~json
{
  "metadata": {
    "eventId": "evt-7ad2",
    "correlationId": "1cdb7c7a-e1cc-420a-9239-138aa1524cb7",
    "traceContext": "managed-by-instrumentation"
  },
  "data": {
    "orderId": "ord-1001",
    "eventType": "OrderPlaced"
  }
}
~~~

Ví dụ này mô tả **hợp đồng logic**, không phải schema chuẩn của một message broker. Trên Kafka, RabbitMQ hoặc hệ thống khác, tracing metadata thường nằm ở **headers/properties** do instrumentation quản lý; đừng ghép nguyên traceparent vào field bất kỳ khi đã dùng thư viện context propagation.

Consumer phải xác thực nguồn sự kiện và áp dụng quyền/tenant context theo cơ chế đáng tin cậy, sau đó gắn correlation ID vào log của lần xử lý. **Không để thread-local MDC của message trước rò sang message sau**. Một sự kiện có thể được delivery lại, nhiều consumer có thể xử lý độc lập và một batch có nhiều sự kiện nguồn; khi đó tracing có thể dùng **span links** hoặc trace riêng có liên hệ, thay vì ép tất cả span vào một cây cha/con thiếu chính xác.

### 8.3. Retry tạo quan hệ chứ không bảo đảm đúng nghiệp vụ

Giả sử client mất kết nối sau khi server đã tạo đơn hàng. Client retry:

- Correlation ID giúp tìm hai lần xử lý và xác định lần nào đã commit.
- **Idempotency-Key** mới giúp server phân biệt retry của cùng thao tác với đơn hàng khác và thực hiện chống xử lý trùng theo hợp đồng.
- **If-Match/ETag** bảo vệ cập nhật theo phiên bản tài nguyên, không thay thế khóa chống thực thi trùng.

Không bao giờ dùng correlation ID làm idempotency key một cách ngầm định: ID dùng để quan sát có thể được phát sinh mỗi lần nhận request, có phạm vi khác và không nhất thiết được lưu nguyên tử với trạng thái nghiệp vụ.

## 9. Liên kết lỗi với dữ liệu chẩn đoán mà không công khai hệ thống nội bộ

Mục tiêu không chỉ là đưa correlation ID vào response. Đội hỗ trợ cần **tra được bằng chứng** và có quy trình xử lý khi log hoặc trace bị thiếu.

### 9.1. Luồng chẩn đoán từ một ID

Giả sử khách hàng báo: “Lúc 16:10, POST /orders trả 503, mã yêu cầu là c87f...”.

~~~mermaid
sequenceDiagram
    participant U as Khách hàng
    participant S as Support
    participant Q as Công cụ tra cứu nội bộ
    participant L as Logs / Traces
    participant E as Engineering
    U->>S: HTTP status + correlationId + thời điểm
    S->>Q: Tra cứu ID theo quyền
    Q->>L: Tìm gateway log / trace / service log
    L-->>Q: Các sự kiện đã lọc và thông tin liên quan
    Q-->>S: Tóm tắt an toàn để hỗ trợ
    S->>E: Chuyển ticket + ID + bằng chứng nội bộ
    E->>L: Phân tích span lỗi / phụ thuộc / deployment
    E-->>S: Kết luận và hướng xử lý
    S-->>U: Thông báo phù hợp, không lộ dữ liệu nội bộ
~~~

Một màn hình tra cứu hữu ích có thể gồm:

| Thông tin | Tác dụng |
|---|---|
| Correlation ID, khoảng thời gian, môi trường, vùng | Khoanh đúng request và hệ thống |
| API route template, method, status, error code | Xác định hợp đồng HTTP bị ảnh hưởng |
| Gateway request ID và trace ID | Chuyển từ access log sang distributed trace |
| Timeline theo service/span, duration, dependency | Tìm nơi lỗi hoặc độ trễ phát sinh |
| Phiên bản triển khai và feature flag | Đối chiếu thay đổi gần thời điểm lỗi |
| Queue event IDs và consumer attempts | Xác định xử lý bất đồng bộ và retry |
| Mã incident/ticket và trạng thái | Liên kết xử lý hỗ trợ với bằng chứng |
| Quyền truy cập và audit hành động tra cứu | Bảo đảm chỉ người có thẩm quyền xem được |

**Không đưa URL truy vấn log nội bộ** vào Problem Details dành cho client. Một liên kết chẩn đoán có thể chứa tên cluster, ID người dùng, query có filter nhạy cảm hoặc cấu trúc hạ tầng. Hãy dựng liên kết đó **bên trong công cụ hỗ trợ**, sau khi kiểm tra quyền, dựa trên correlation ID đã nhận.

### 9.2. Khi không tìm thấy log thì sao?

Việc không có kết quả tra cứu không chứng minh request chưa chạy. Có thể:

- Gateway đã trả lỗi **trước khi service nhận request**.
- Log collector bị gián đoạn hoặc event đang chờ đẩy lên.
- Trace đã bị sampling và **không được lưu**.
- Service ghi log không có correlationId do thiếu cấu hình logging hoặc lỗi truyền context.
- Log đã hết thời hạn lưu; request ID dùng trên môi trường khác hoặc đồng hồ các hệ thống lệch nhau.
- Lỗi phát sinh ở job nền sau khi request trả về thành công, cần tìm bằng event ID hoặc business ID.

Runbook phải cho biết **nguồn tra cứu dự phòng**: gateway access log, application log theo route/time, APM trace, metrics, audit event, job event và incident log. Đừng hứa với khách hàng rằng chỉ cần ID là **chắc chắn** khôi phục mọi stack trace trong mọi điều kiện.

### 9.3. Chẩn đoán không đồng nghĩa với tiết lộ cho mọi người

Người hỗ trợ tuyến đầu có thể chỉ cần biết: lỗi được ghi nhận, trạng thái xử lý, loại lỗi, thời điểm và cách hướng dẫn khách hàng. Kỹ sư có quyền cao hơn mới cần trace/exception; người quản lý dữ liệu có thể phải phê duyệt truy cập sâu vào audit. Có thể áp dụng **RBAC/ABAC**, giới hạn tenant, ghi audit truy vấn và cơ chế cấp quyền có thời hạn.

**Correlation ID là khóa tìm kiếm, không phải khóa phân quyền.** Một ID bị đoán hoặc bị rò không được trở thành đường tắt để tải log hoặc dữ liệu khách hàng.

## 10. Bảo mật, quyền riêng tư và ranh giới tin cậy

### 10.1. Các nguy cơ thường gặp

| Nguy cơ | Tình huống | Biện pháp |
|---|---|---|
| **Giả mạo ID** | Client tự gửi correlation ID giống ID của yêu cầu khác | Tạo ID ở biên public; chỉ nhận ID từ nguồn tin cậy có xác minh |
| **Log injection** | Header chứa ký tự xuống dòng hoặc nội dung giả log | Validate format/length; log có cấu trúc; không dùng trực tiếp raw header |
| **DoS qua header** | Client gửi ID dài hàng megabyte | Giới hạn kích thước ở gateway và parser; tạo ID mới nếu không hợp lệ |
| **Rò dữ liệu nhạy cảm** | Ghi Authorization, URL có token, body lỗi hoặc exception message | Redact/minimize; dùng route template, error code và cấu trúc log |
| **Truy cập xuyên tenant** | ID của tenant A dùng để truy vấn log của tenant B | Kiểm tra quyền trên tenant và phạm vi dữ liệu chẩn đoán |
| **Header lan sang bên thứ ba** | Service tự động gửi baggage và ID nội bộ tới partner | Allowlist header theo đích, kiểm soát egress |
| **Lưu trữ quá lâu** | Log tồn tại vô hạn, chứa nhiều thông tin định danh | Chính sách retention, phân quyền, xóa và audit |
| **Cardinality cao** | Mọi correlation ID là nhãn metric | Dùng log/trace để tra cứu ID; metric tổng hợp theo route/status/service |

Định dạng UUID v4 có tính khó đoán tốt khi sinh đúng, nhưng **khó đoán không biến ID thành secret**. Không dùng correlation ID thay access token, CSRF token, chữ ký webhook hoặc idempotency key.

### 10.2. Xử lý header từ đối tác tin cậy

Nếu muốn nhận **X-Correlation-ID** do hệ thống upstream tạo, cần:

1. Xác định **ranh giới tin cậy**: gateway, service mesh, proxy hoặc API partner được kiểm soát bằng xác thực và chính sách truy cập.
2. Chặn hoặc loại bỏ header từ client công khai ở entrypoint nếu bên trong sẽ tin header upstream.
3. Chỉ chấp nhận định dạng trong allowlist, ví dụ UUID hợp lệ; giới hạn độ dài và ký tự.
4. Nếu thay ID, ghi quan hệ với **upstream request ID** ở log nội bộ khi thực sự cần, không đưa raw untrusted value vào log.
5. Phân biệt context tracing (traceparent) với correlation header và bảo vệ dữ liệu riêng tư trong từng loại.

Không dùng một danh sách “header nội bộ” được forward tự động tới mọi bên đích. HTTP client có thể gọi partner khác, vì vậy chính sách propagation cần theo endpoint và quan hệ tin cậy.

### 10.3. Phản hồi lỗi và cache

Với response lỗi có dữ liệu riêng người dùng hoặc thông tin xử lý sự cố, có thể dùng **Cache-Control: no-store** theo chính sách API. Không suy rằng tất cả lỗi 4xx/5xx đều không được cache theo HTTP: tính cache phụ thuộc status, header và ngữ cảnh. Việc chọn no-store cho Problem Details nhạy cảm là **quyết định bảo vệ dữ liệu** của ứng dụng.

Nếu client chạy trong browser và gọi API **cross-origin**, JavaScript có thể không đọc được header tùy biến nếu CORS không cho phép. Cấu hình response header **Access-Control-Expose-Headers: X-Correlation-ID** cho những origin được cho phép khi client cần lấy ID; cấu hình CORS phải đi cùng chính sách origin, credential và bảo mật hiện hành.

## 11. OpenAPI: công bố hợp đồng lỗi có thể hỗ trợ được

OpenAPI nên mô tả **response media type, error code, correlation ID ở header/body** và những status liên quan đến endpoint. Ví dụ OpenAPI 3.x rút gọn:

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: 1.0.0
paths:
  /orders:
    post:
      summary: Tạo đơn hàng
      description: >
        Khi có lỗi, client nhận correlation ID để cung cấp
        cho bộ phận hỗ trợ. Không dùng correlation ID làm
        idempotency key; nếu API hỗ trợ retry an toàn, xem
        hợp đồng Idempotency-Key riêng.
      responses:
        "201":
          description: Tạo đơn hàng thành công
        "409":
          description: Xung đột trạng thái đơn hàng
          headers:
            X-Correlation-ID:
              description: ID phục vụ tra cứu chẩn đoán
              schema:
                type: string
                format: uuid
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"
        "500":
          description: Lỗi không mong đợi
          headers:
            X-Correlation-ID:
              description: ID phục vụ tra cứu chẩn đoán
              schema:
                type: string
                format: uuid
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"
components:
  schemas:
    ApiProblem:
      type: object
      properties:
        type:
          type: string
          format: uri-reference
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
        instance:
          type: string
          format: uri-reference
        code:
          type: string
        correlationId:
          type: string
          format: uuid
      required: [type, title, status, code, correlationId]
~~~

Đây là **hợp đồng ví dụ**; RFC 9457 không yêu cầu mọi Problem Details có đủ các trường được đánh dấu required trong schema trên. Vì API đã chọn yêu cầu code và correlationId trong lỗi của mình, schema quy định chặt hơn định dạng chung. Nếu response 400, 401, 403, 404, 412, 422, 429 hoặc 503 cũng dùng cùng quy ước thì cần mô tả nhất quán, có thể tái sử dụng response components để tránh lặp cấu hình.

**Đừng đưa correlationId vào path của tài nguyên nghiệp vụ** như một cách định danh thay cho ID đơn hàng. Nó thuộc nhóm metadata xử lý request. Mã lỗi nghiệp vụ phải có hợp đồng độc lập với trace hay công cụ log dùng phía server.

### 11.1. SDK client nên làm gì?

Client có thể:

- Đọc X-Correlation-ID từ response (hoặc body Problem Details).
- Hiển thị tùy chọn “Sao chép mã yêu cầu” trong màn hình lỗi.
- Gửi mã cùng thời điểm, status và thao tác đã thực hiện khi tạo ticket hỗ trợ.
- Chỉ retry theo **ngữ nghĩa HTTP, Retry-After, idempotency key và hợp đồng endpoint**, không dựa vào correlation ID.
- Tránh gửi body lỗi chứa dữ liệu nhạy cảm tới hệ thống analytics phía client.

Một SDK cần xử lý **mã thiếu** vì network error có thể xảy ra trước khi có response, hoặc gateway chưa được cấu hình trả header. Có thể tạo **client diagnostic ID** riêng để liên hệ log phía client, đồng thời không coi nó là chứng cứ một request đã đến server.

## 12. Quan sát, sampling, retention và chi phí

### 12.1. Trace sampling không được làm mất khả năng hỗ trợ cơ bản

Trên hệ thống lưu lượng lớn, lưu **100% distributed traces** có thể tốn kém. Có thể dùng head-based hoặc tail-based sampling theo hệ thống tracing. Tuy nhiên:

- Trace của một request có thể không được lưu dù log lỗi vẫn tồn tại.
- Sampling trên nhiều service phải được cấu hình phù hợp để tránh mất quan hệ giữa các span cần phân tích.
- Khi có lỗi quan trọng, cần đủ **structured logs** ở những điểm quyết định để tìm status, error code và dependency; không nhất thiết ghi toàn bộ payload.
- Không hứa “nhập correlation ID sẽ luôn thấy trace đầy đủ”, vì telemetry có thể bị mất khi collector, mạng hoặc backend giám sát gặp sự cố.

Correlation ID nên là trường có thể **lọc/truy vấn** trong hệ thống log theo retention yêu cầu, nhưng không cần biến thành label cho mọi metric.

### 12.2. Chuẩn bị một chính sách retention cụ thể

Ví dụ tổ chức xác định:

| Loại dữ liệu | Quyết định cần ghi trong chính sách |
|---|---|
| Access logs | Thời hạn lưu, độ chi tiết, nơi lưu, quyền đọc, khả năng xóa |
| Error logs | Thời gian tối thiểu phục vụ tra cứu ticket và giới hạn thông tin nhạy cảm |
| Distributed traces | Mức sampling, thời hạn lưu, đường truy cập nội bộ |
| Audit logs | Quy định toàn vẹn, thời hạn lưu bắt buộc, quyền kiểm toán |
| Ticket/incident | Thời gian lưu các ID liên kết và dữ liệu đã được biên tập an toàn |

Không có **một thời hạn retention cố định** phù hợp cho mọi ứng dụng. Chọn theo hợp đồng, quy định, chi phí, mức độ nhạy cảm và nhu cầu chẩn đoán. Nếu log giữ 7 ngày nhưng ticket được báo sau 20 ngày, nhóm hỗ trợ cần biết giới hạn đó và sử dụng nguồn khác khi còn hợp lệ.

### 12.3. Tín hiệu để biết correlation đang hoạt động

Theo dõi một số chỉ số vận hành có ý nghĩa:

- Tỷ lệ response 4xx/5xx do ứng dụng/gateway kiểm soát có correlation ID theo hợp đồng.
- Tỷ lệ error log có correlation ID, service, environment và error code.
- Khả năng tra được trace ID từ gateway hoặc log ở các lỗi có tracing.
- Tỷ lệ message/worker event không có context khi cần liên kết, phân biệt loại job không có request gốc.
- Thời gian từ lúc nhận ID trong ticket đến khi xác định service lỗi đầu tiên.
- Tỷ lệ lỗi do logging/collector làm mất dữ liệu chẩn đoán.

Đây là **đề xuất thước đo**, không phải ngưỡng SLO bắt buộc. Mỗi đội cần chốt mức chấp nhận theo lưu lượng và nhu cầu hỗ trợ. Dùng đánh giá theo **route/service/status**, không gắn hàng triệu correlation ID khác nhau vào từng metric.

## 13. Ma trận kiểm thử Java/Spring và kiểm thử tích hợp

### 13.1. Kiểm thử HTTP API

| Kịch bản | Thao tác kiểm thử | Kết quả cần xác minh |
|---|---|---|
| Request thành công | GET/POST hợp lệ | ID có trong response khi hợp đồng quy định, có thể tra cứu ở log |
| Lỗi nghiệp vụ | Gây 409 hoặc 422 có kiểm soát | HTTP status đúng; code ổn định; header/body cùng correlation ID |
| Lỗi server | Giả lập dependency timeout | Client nhận thông báo an toàn; log chứa correlation ID và nguyên nhân hữu ích |
| Hai request đồng thời | Gửi song song từ hai client | ID không bị lẫn giữa request và log |
| Thread pool tái sử dụng | Gửi nhiều request liên tục trên ít worker | MDC được dọn; không mang ID cũ sang request tiếp theo |
| Client gửi header giả | Gửi X-Correlation-ID tùy ý/chuỗi dài | Entry public phát ID mới hoặc áp dụng chính sách kiểm tra; không log injection |
| CORS | Browser gọi API cross-origin hợp lệ | JavaScript có thể đọc ID nếu API đã khai báo expose header |
| Gateway từ chối sớm | Gửi body quá lớn, URI sai, header không hợp lệ | ID được phát ở tầng xử lý hoặc biết rõ giới hạn và cách tìm gateway log |
| Trace propagation | Order API gọi Inventory Service | Các span có trace relationship đúng, log downstream mang correlation ID |
| Async job | Phát event rồi worker xử lý | Event metadata và worker log liên kết đúng, không rò MDC giữa message |
| Retry HTTP | Timeout rồi retry một POST/PATCH | Correlation phục vụ tra cứu; idempotency bảo đảm không lặp nghiệp vụ nếu hợp đồng yêu cầu |
| Không có trace | Sampling loại bỏ trace | Log lỗi vẫn có dữ liệu tối thiểu để chẩn đoán |
| Exception chứa secret | Ném lỗi từ driver/SDK có chuỗi nhạy cảm | Problem Details không lộ secret/stack trace |

### 13.2. Ví dụ MockMvc kiểm tra correlation ID

Giả sử filter và handler ở phần 7 đã được nạp trong Spring MVC test context:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class CorrelationIdTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void responseUsesServerGeneratedCorrelationId() throws Exception {
        MvcResult result = mockMvc.perform(
                get("/health-check-example")
                    .header("X-Correlation-ID", "spoofed-value"))
            .andExpect(header().exists("X-Correlation-ID"))
            .andReturn();

        String id = result.getResponse()
            .getHeader("X-Correlation-ID");

        UUID.fromString(id);           // Phải là UUID hợp lệ.
        org.junit.jupiter.api.Assertions.assertNotEquals(
            "spoofed-value", id
        );
    }
}
~~~

**Ví dụ giả định** có endpoint **/health-check-example** trong test fixture. Nếu endpoint đó trả 404 vẫn có thể kiểm tra header từ filter, nhưng muốn assert status cụ thể phải cấu hình fixture tương ứng. Bài kiểm tra này mới chứng minh header được tạo; cần thêm test về **body Problem Details và log/MDC** để bảo đảm ID xuất hiện nhất quán.

Với request có lỗi nghiệp vụ:

~~~java
MvcResult result = mockMvc.perform(
        get("/orders/{id}", "conflict-fixture"))
    .andExpect(status().isConflict())
    .andExpect(header().exists("X-Correlation-ID"))
    .andReturn();

String responseId = result.getResponse()
    .getHeader("X-Correlation-ID");

// Kiểm tra JSON response ở test tích hợp:
// $.correlationId == responseId
// $.code == ORDER_CONFLICT
// Không có trường stackTrace, sql hay secret.
~~~

Ví dụ trên giả định fixture **/orders/conflict-fixture** cố ý ném OrderConflictException. Trong dự án thật, đừng thêm endpoint production chỉ để tạo lỗi kiểm thử; dùng repository/service test double hoặc dữ liệu thử hợp lệ. Chạy test end-to-end qua gateway để kiểm chứng trường hợp lỗi xảy ra **trước filter**.

### 13.3. Kiểm thử concurrency và observability

Unit test của filter không đủ để chứng minh tất cả bối cảnh. Nên thực hiện:

1. Bắn nhiều request đồng thời, ghi log có request ID và correlation ID; xác minh không có bản ghi sai ID.
2. Chuyển xử lý sang **@Async, executor, WebClient/Reactor hoặc message consumer**, kiểm tra context được truyền bằng cơ chế dành cho nền tảng đó.
3. Gửi HTTP tới downstream chạy thật hoặc test server; đối chiếu trace ID/span relationship và correlation header.
4. Tắt hoặc làm gián đoạn collector trong môi trường thử nghiệm; bảo đảm ứng dụng xử lý lỗi theo chính sách, không block vô hạn vì logging.
5. Kiểm tra correlation ID ở response lỗi từ gateway/WAF/ingress và cách tra cứu nó trong access logs.

Nếu đang dùng OpenTelemetry/Micrometer, **tránh tự triển khai context propagation thứ hai** gây lệch trace; tận dụng cơ chế instrumentation chính thức và chỉ bổ sung correlation metadata khi cần.

## 14. Case study: tìm nguyên nhân lỗi tạo đơn hàng

### 14.1. Bối cảnh

Một hệ thống bán hàng có:

- **API Gateway** nhận request của mobile client.
- **Order API** kiểm tra đơn và ghi database.
- **Inventory Service** xác nhận giữ tồn.
- **Event Bus** phát sự kiện OrderPlaced.
- **Notification Worker** gửi thông báo sau khi đơn được tạo.

Giả sử tại một thời điểm, người dùng thấy **503 Service Unavailable** khi tạo đơn. Phản hồi có correlation ID **c-a81f** trong ví dụ minh họa (production có thể dùng UUID).

### 14.2. Những log được tìm theo ID

| Thời điểm UTC | Service | Event / Span | Kết quả |
|---|---|---|---|
| 09:15:00.000 | gateway | request.received, POST /orders | request ID req-501, trace t-11 |
| 09:15:00.018 | order-api | order.create.started | Order validation thành công |
| 09:15:00.050 | order-api | inventory.reserve.requested | Gọi Inventory Service |
| 09:15:02.051 | order-api | inventory.reserve.timeout | Timeout sau 2 giây |
| 09:15:02.058 | order-api | order.create.failed | Mã INVENTORY_TIMEOUT |
| 09:15:02.064 | gateway | request.completed | HTTP 503, correlationId c-a81f |

Tất cả các dòng được **gắn cùng correlation ID**. Trace thể hiện span của Order API chờ Inventory Service; metrics cho thấy tỷ lệ timeout của Inventory tăng. Lúc này kỹ sư có cơ sở kết luận lỗi không phải do JSON request, mã hóa token hay đường đi đến gateway, nhưng vẫn cần kiểm tra **trạng thái đơn hàng/transaction** trước khi khuyên client retry.

### 14.3. Một lỗi có thể phát sinh sau khi response đã trả

Giả sử Order API ghi DB thành công, trả **201 Created** và enqueue OrderPlaced. Năm giây sau Notification Worker lỗi khi gửi email. Worker vẫn nên ghi **correlation ID hoặc event ID liên hệ** để truy vết, nhưng lỗi email **không được biến hồi tố** response 201 thành 500. Đây là lỗi **bất đồng bộ**, cần retry, dead-letter hoặc cảnh báo theo hợp đồng.

Ngược lại, nếu Order API trả timeout sau khi DB đã commit nhưng response 201 bị mất, client có thể gửi lại cùng POST. **Correlation ID giúp điều tra hai lần gọi**, còn **idempotency key** và transaction/outbox đúng mới ngăn tạo đơn trùng.

### 14.4. Bài học từ case study

Đội hỗ trợ chỉ cần chuyển cho kỹ thuật **correlation ID, thời điểm, endpoint, status và mô tả thao tác**. Đội kỹ thuật truy vấn log/trace có quyền, tìm nơi timeout, xác định trạng thái ghi DB, rồi đưa ra hướng xử lý. Không cần yêu cầu khách hàng gửi access token hoặc ảnh chụp thông tin nhạy cảm để điều tra.

## 15. Bài thực hành: thiết kế tuyến chẩn đoán cho REST API

**Đề bài.** Một nền tảng đặt lịch có hai endpoint:

- **POST /appointments** tạo lịch hẹn, trả **201** khi thành công.
- **PATCH /appointments/{id}** thay đổi trạng thái, yêu cầu If-Match.

Backend có API Gateway, Booking API, PostgreSQL và Payment Service; hệ thống gửi event đến SMS Worker. Mobile client có thể retry khi mất mạng. Ở production, một số lỗi xảy ra trong gateway và một số xảy ra sau khi message đã vào queue.

Hãy thiết kế:

1. Tên header correlation, **điểm sinh**, định dạng, ranh giới tin cậy và quy tắc nhận ID từ client.
2. Mẫu **application/problem+json** cho **412 Precondition Failed**, **503 Service Unavailable** và lỗi 500 không mong đợi, có mã lỗi và correlation ID.
3. Cách truyền correlation ID và W3C trace context qua Booking API → Payment Service → SMS Worker; phân biệt các event phát lại.
4. Bộ trường log đủ để tìm lỗi mà **không ghi token, body nhạy cảm hoặc SQL chứa dữ liệu cá nhân**.
5. Hành vi của client khi chỉ nhận **network timeout** và không có response; cách dùng idempotency key/If-Match để tránh trùng nghiệp vụ.
6. Ba phép thử concurrency, ba phép thử propagation và hai trường hợp mất dữ liệu quan sát.
7. Quy trình nhân viên hỗ trợ dùng ID để tạo ticket mà không có quyền xem mọi dữ liệu tenant.

### Gợi ý lời giải

Một thiết kế có thể dùng **X-Correlation-ID** do gateway sinh, response luôn trả khi tầng xử lý cho phép, Booking API gắn ID vào log có cấu trúc và metadata message. Traceparent được SDK tracing truyền ở các HTTP calls; consumer xử lý trace context theo cơ chế message instrumentation, dùng span link khi cần.

**412** nên giải thích ETag cũ, hướng dẫn GET lại và không tự retry vô hạn. **503** có thể hướng dẫn retry có kiểm soát nếu thao tác an toàn về ngữ nghĩa, kết hợp Retry-After khi phù hợp. **500** dùng thông điệp chung, tránh lộ implementation detail. Mỗi lỗi chứa mã ứng dụng ổn định và ID để tra cứu.

Đối với POST có khả năng tạo phí hoặc đặt lịch trùng, **idempotency key** nhận diện thao tác nghiệp vụ; correlation ID chỉ giúp tìm dấu vết. Với PATCH theo If-Match, status 412 không chứng minh retry trước đã thành công. Cần đọc lại trạng thái hoặc dùng cơ chế truy vấn kết quả phù hợp.

Ba phép thử concurrency có thể là: nhiều request đồng thời trên cùng thread pool, retry POST song song với cùng idempotency key, và worker xử lý message trùng/khác tenant. Các phép propagation gồm: HTTP downstream, event queue và exception handler. Hai tình huống observability bị mất gồm: trace bị sampling và collector log bị gián đoạn. Quy trình hỗ trợ phải giới hạn truy cập theo vai trò/tenant, có audit và không coi correlation ID là quyền.

## 16. Các phản mẫu thường gặp

| Phản mẫu | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng timestamp hoặc IP thay correlation ID | Dễ lẫn request đồng thời, IP có thể dùng chung | Cấp ID riêng và truyền thống nhất |
| Tin mọi X-Correlation-ID từ Internet | Header injection, giả mạo log, ID trùng | Phát ID ở biên public; xác minh upstream tin cậy |
| Dùng correlation ID làm token hoặc idempotency key | Sai mục đích, không chống trùng đúng, rủi ro quyền | Tách authentication, idempotency và observability |
| Chỉ gắn ID ở controller | Lỗi gateway, filter hoặc framework không có ID | Triển khai tại entrypoint và các tầng xử lý lỗi phù hợp |
| MDC không được dọn sau request | Log A có ID của B, lộ mối liên hệ | try/finally, kiểm thử thread reuse, async context |
| Tự copy MDC vào mọi thread không kiểm soát | Context sai hoặc rò sau tác vụ | Dùng framework propagation, gỡ context đúng vòng đời |
| Chỉ dựa vào trace, không có log lỗi | Trace sampling làm mất bằng chứng | Duy trì sự kiện lỗi tối thiểu có cấu trúc |
| Gắn correlationId làm nhãn metric | Bùng nổ cardinality và chi phí | Truy vấn ID trong log/trace; metric theo route/status |
| Trả stack trace và nội bộ log URL cho khách hàng | Lộ thông tin bảo mật và hạ tầng | Problem Details an toàn, công cụ tra cứu có phân quyền |
| Ghi mọi request/response body | Phơi lộ dữ liệu cá nhân, tốn chi phí | Redaction, allowlist trường, retention |
| Tất cả exception đều chuyển thành 500 | Client hiểu sai lỗi, retry không an toàn | Phân loại đúng 4xx/5xx và error code |
| Khi có ID thì chắc chắn tìm được mọi thứ | Log/trace có thể bị mất, chậm hoặc hết hạn | Runbook nguồn thay thế và cảnh báo thiếu telemetry |

## 17. Checklist trước khi đưa vào production

- [ ] Đã thống nhất correlation ID, request ID, trace ID, span ID và idempotency key là những khái niệm riêng.
- [ ] Entry gateway hoặc service đáng tin cậy phát hành/chuẩn hóa ID; không chấp nhận raw header tùy ý từ client công khai.
- [ ] HTTP response lỗi có status, error code ổn định và correlation ID theo hợp đồng đã công bố.
- [ ] Problem Details không lộ exception message, stack trace, token, connection string hoặc dữ liệu cá nhân.
- [ ] Structured logs của gateway và các service có correlation ID, route template, status, service/environment và thời điểm.
- [ ] W3C trace context được truyền bằng instrumentation hỗ trợ; không tự ghép header sai chuẩn.
- [ ] Async jobs, message retries và event consumers có metadata liên kết đáng tin cậy và dọn context đúng vòng đời.
- [ ] MDC được gỡ sau xử lý request và có kiểm thử với thread pool, @Async hoặc Reactor nếu sử dụng.
- [ ] Truy vấn chẩn đoán phải xác thực, phân quyền theo vai trò/tenant và có audit.
- [ ] Đã chốt quy tắc log redaction, retention, sampling, cardinality và chính sách CORS khi cần.
- [ ] Đã kiểm tra các lỗi bị gateway/WAF/container chặn trước khi tới Spring.
- [ ] Có runbook tra cứu bằng correlation ID, nguồn thay thế khi không có trace và cách chuyển ticket cho đội kỹ thuật.
- [ ] Có test end-to-end nối client → gateway → service → message consumer và đối chiếu ID trong dữ liệu chẩn đoán.

## 18. Ghi nhớ và tài liệu tham khảo

**Correlation ID kết nối một phản hồi lỗi với chuỗi dữ liệu chẩn đoán liên quan**, còn **trace ID/span ID** mô tả hành trình công việc, **request ID** nhận diện một lần HTTP call, và **idempotency key** bảo vệ thao tác nghiệp vụ khi gửi lại. Hãy phát ID ở ranh giới đáng tin cậy, truyền nó nhất quán, ghi log có cấu trúc và trả ID trong **Problem Details** khi phù hợp. Một hệ thống dễ hỗ trợ là hệ thống có thể tìm nguyên nhân mà vẫn **giữ đúng mã lỗi HTTP, bảo vệ dữ liệu và kiểm soát quyền xem telemetry**.

Tài liệu để đối chiếu:

- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): định dạng lỗi application/problem+json và extension members.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ngữ nghĩa phương thức, mã trạng thái, điều kiện và retry.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): cú pháp và cách truyền traceparent/tracestate.
- [W3C Baggage](https://www.w3.org/TR/baggage/): cơ chế truyền metadata giữa các dịch vụ và cân nhắc phạm vi.
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/): instrumentation, tracing và context propagation.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): ProblemDetail và xử lý lỗi trong Spring MVC.
