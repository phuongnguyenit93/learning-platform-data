# Phát hiện bên sử dụng còn phụ thuộc hợp đồng cũ

## 1. Vì sao API vẫn “có người dùng” sau khi đã công bố phiên bản mới?

Nhóm phát triển Orders API muốn ngừng **GET /v1/orders** và thay bằng **GET /v2/orders**. Tài liệu, SDK và màn hình quản trị nội bộ đều đã dùng v2; dashboard báo không còn nhiều request v1. Nhưng ngay sau khi tắt v1, một đối tác giao vận ngừng đồng bộ đơn hàng ban đêm. Đối tác không gọi API trực tiếp từ ứng dụng web: một batch job cũ chỉ chạy vào ngày cuối tháng và vẫn phụ thuộc **response field customerCode** đã bị đổi tên thành **customerId**.

Sự cố này cho thấy **không phát hiện request gần đây không đồng nghĩa không còn consumer**. Bên sử dụng có thể là ứng dụng, SDK, mobile client phiên bản cũ, tác vụ định kỳ, đối tác, webhook receiver hoặc dịch vụ trung gian. Một client cũng có thể chuyển sang URI mới nhưng **vẫn phụ thuộc hành vi cũ**: mã lỗi, thứ tự sắp xếp, tính nullable, pagination, cache hoặc yêu cầu có điều kiện.

Mục tiêu của bài trong module **INTEGRATION_API_REST** là xây **bằng chứng đủ tin cậy trước khi bỏ một hợp đồng REST API**, dựa vào HTTP traffic, consumer identity, telemetry ở tầng ứng dụng, kiểm thử hợp đồng và kế hoạch chuyển đổi. Bài không hướng dẫn chọn mọi chiến lược versioning; trọng tâm là **tìm ai còn phụ thuộc phần cũ, ở đâu, bằng cách nào và còn thiếu bằng chứng gì**.

### Sau bài học, bạn có thể

- Xác định thế nào là một **consumer thực sự phụ thuộc hợp đồng cũ**, khác với chỉ gọi một URI cũ.
- Thu thập usage evidence ở gateway, server, SDK và quy trình batch mà không làm lộ dữ liệu.
- Phân biệt **đếm request**, **đếm consumer duy nhất**, **phụ thuộc vào response field** và **khả năng phát hiện**.
- Thiết kế deprecation signals bằng HTTP và OpenAPI, nhưng không coi chúng là chứng cứ client đã nâng cấp.
- Gắn telemetry an toàn trong Java/Spring, viết contract/integration tests và sử dụng số liệu để quyết định ngừng hỗ trợ.

## 2. “Phụ thuộc hợp đồng cũ” có những hình thức nào?

**Consumer** là phần mềm hoặc tổ chức sử dụng API để hoàn thành một công việc. **Hợp đồng** gồm URI, HTTP method, media type, request/response schema, status, header và những ngữ nghĩa ứng dụng mà API đã công bố hoặc đã tạo kỳ vọng ổn định.

| Dạng phụ thuộc | Ví dụ | Có thể nhận biết chỉ từ access log không? |
|---|---|---|
| **URI/phiên bản** | GET /v1/orders, Accept: application/vnd.shop.v1+json | **Thường có**, nếu lưu method, route và header được phép |
| **Request field/parameter** | ?page=3 thay cho cursor; JSON chứa legacyCustomerCode | **Có thể**, khi parser ghi nhận sự hiện diện field hoặc phiên bản hợp đồng |
| **Response field** | Client vẫn đọc customerCode hoặc chờ totalPages | **Không chắc**: server biết đã gửi field, không biết client có dùng |
| **HTTP status/header** | Client chỉ xử lý 200, không hiểu 202 hoặc 304; phụ thuộc X-Next-Page | **Không đủ** nếu chỉ quan sát request |
| **Ngữ nghĩa hành vi** | Mong GET luôn có sort mặc định hoặc lỗi 404 cho tập hợp rỗng | **Cần thêm test/telemetry** và trao đổi với consumer |
| **Xử lý nền/tích hợp ngoài** | Mobile offline sync, cron cuối tháng, webhook callback | **Dễ bỏ sót** trong cửa sổ đo ngắn |

### 2.1. Phân biệt “có dùng” và “cần dùng”

Một SDK có thể gọi **/v1/orders** vì cấu hình mặc định mặc dù consumer không sử dụng field bị loại bỏ; đó là **sử dụng route cũ** nhưng chưa chứng minh phụ thuộc vào **mọi chi tiết** của response v1. Ngược lại, consumer gọi **/v2/orders** nhưng vẫn dùng trường **legacyCustomerCode** mà server tạm giữ để tương thích thì **vẫn còn phụ thuộc ngữ nghĩa cũ**.

Do vậy, nên lập danh sách **contract elements to retire**, ví dụ:

1. Bỏ route **GET /v1/orders**.
2. Bỏ query parameter **page** trên route tương thích.
3. Bỏ property **customerCode** trong representation v2.
4. Chuyển mã lỗi tự chế sang **application/problem+json**.

Mỗi hạng mục cần **tín hiệu phát hiện riêng** và tiêu chí bỏ hỗ trợ riêng. Không dùng một số liệu chung như “request v1 dưới 1%” để quyết định bỏ mọi field cũ.

## 3. Chọn bằng chứng, không chỉ thu thập thật nhiều log

### 3.1. Bốn mức độ bằng chứng

| Nguồn | Cho biết | Không cho biết chắc chắn |
|---|---|---|
| **Gateway/access logs** | Ai gọi route/method/version nào, bao lâu một lần, status/latency | Client có thực sự đọc property cũ trong body không |
| **Server field telemetry** | Request có tham số/field cũ, nhánh tương thích nào được kích hoạt | Client dùng property **chỉ xuất hiện trong response** hay không |
| **SDK/client instrumentation** | Phiên bản SDK/app, tính năng nào đang đọc/parse field, migration flag | Bao phủ mọi client tự viết hoặc offline hay không |
| **Consumer-owned contract tests/xác nhận đối tác** | Bài toán tích hợp nào phụ thuộc schema/status/hành vi; lộ trình nâng cấp | Chắc chắn không có client ẩn chưa đăng ký hay không |

Kết hợp nhiều nguồn thành **bằng chứng tam giác**: telemetry server cho mức sử dụng thực, ứng dụng/SDK cho dependency ở phía nhận, và xác nhận trực tiếp từ chủ sở hữu consumer. Không chỉ dựa vào lời khẳng định “đã nâng cấp” mà thiếu giao dịch thử trên v2.

### 3.2. Nên ghi những trường nào?

Một sự kiện sử dụng route cũ có thể có:

~~~json
{
  "event": "api.legacy_contract_used",
  "contract": "orders-v1",
  "route": "GET /v1/orders",
  "consumerId": "registered-client-27",
  "tenantScope": "tenant-group-3",
  "detectedSignals": ["legacy_route", "page_parameter"],
  "statusCode": 200,
  "timestamp": "2026-11-18T09:00:00Z",
  "correlationId": "c4e5b0d8-8eb6-4a2b-9181-1eb91065c319"
}
~~~

Đây là sự kiện **giả**. **consumerId** phải xuất phát từ thông tin đăng ký/xác thực đáng tin cậy và được bảo vệ theo chính sách privacy. Nếu cần mã hóa một chiều để phân tích, áp dụng khóa bí mật và quản lý quyền truy cập; không đưa danh tính chi tiết vào metric labels. Dùng **route template** như **/orders/{id}** thay vì path chứa ID thực. Tránh lưu **Authorization**, Cookie, full body, query chứa PII, token và nội dung đơn hàng.

### 3.3. Không phải mọi request đều đi qua cùng một điểm

~~~mermaid
flowchart LR
    WEB[Web/Mobile SDK] --> GW[API Gateway]
    PARTNER[Đối tác / cron] --> GW
    LEGACY[Internal batch / service] --> API[REST API]
    GW --> API
    API --> DATA[(Orders DB)]
    GW -. route/status metrics .-> OBS[(Observability)]
    API -. field/branch events .-> OBS
    WEB -. opt-in client telemetry .-> OBS
    PARTNER -. owner confirmation .-> INV[(Consumer inventory)]
    OBS --> INV
~~~

Nếu dịch vụ nội bộ gọi origin trực tiếp, log ở CDN **không chứa toàn bộ traffic**. Nếu CDN trả cached response, log ở application **không thấy cache hit**. Nếu client offline, cửa sổ 7 ngày không phản ánh lần sync tới. Phải liệt kê **các đường đi thực tế**, kể cả staging/batch/partner, rồi mới giải thích số liệu.

## 4. Lập consumer inventory có thể hành động

Một bảng dùng cho kế hoạch migration:

| Consumer | Định danh tin cậy | Hợp đồng cũ còn dùng | Lần cuối thấy | Nhịp hoạt động | Chủ sở hữu / trạng thái |
|---|---|---|---|---|---|
| Web Shop | OAuth client web-shop | /v1/orders, page | 18/11/2026 | Hằng ngày | Team Web, đang chuyển |
| Mobile 4.x | app build + client registration | customerCode response | 17/11/2026 | Offline, không đều | Mobile, còn phiên bản cũ |
| Logistics Batch | service principal logistics-batch | /v1/orders | 31/10/2026 | Cuối tháng | Đối tác, lịch test v2 |
| Unknown Client | Không xác định được | /v1/orders | 01/11/2026 | Chưa rõ | Cần điều tra thêm |

**User-Agent** và **X-Client-Version** có ích cho việc phân nhóm khi client hợp tác, nhưng là **thông tin client tự khai**, không đủ để xác thực danh tính. Chọn thứ tự ưu tiên: **registered OAuth client_id / service principal / mTLS identity**, rồi mới tới app version được báo cáo, request metadata hoặc liên hệ đối tác. Một token có thể đại diện cho nhiều người dùng/thiết bị; **client_id không đồng nghĩa một người dùng duy nhất**.

Các trường inventory cần duy trì thêm: phiên bản mục tiêu, traffic theo thời gian, danh sách contract elements, owner/contact, kế hoạch release, deadline đã thống nhất, tình trạng contract test, trường hợp ngoại lệ và rủi ro.

### 4.1. Không đánh đồng “không thấy” với “không có”

Một đường traffic về 0 có thể do:

- Thiết bị offline, batch chạy theo tháng/quý.
- Gateway thay đổi sampling, route hoặc pipeline log bị lỗi.
- Cached responses được phục vụ ở CDN, không chạm origin.
- Một client mới dùng credential dùng chung nên bị gộp với client khác.
- Giao dịch chỉ chạy khi có sự kiện hiếm, sự cố hoặc xử lý khẩn cấp.

Định nghĩa **cửa sổ quan sát theo chu kỳ sử dụng** và báo cáo **coverage**: phần traffic không định danh được, phần route không được instrument, tỷ lệ log bị drop và những consumer chưa có owner. Không tuyên bố “zero consumers” chỉ từ “zero requests trong 7 ngày”.

## 5. Phát tín hiệu ngừng hỗ trợ qua HTTP và OpenAPI

Phát hiện consumer cần được thực hiện song song với **thông báo rõ đường chuyển đổi**. Không nên để các đối tác chỉ biết mình phụ thuộc vào v1 sau khi server trả 404.

### 5.1. Deprecation và Sunset làm gì?

**Deprecation** theo RFC 9745 là trường HTTP báo một tài nguyên hoặc ngữ cảnh API đã/sẽ được đánh dấu không còn được khuyến nghị. Giá trị của **Deprecation** là một Structured Field Date, biểu thị thời điểm deprecation, ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Deprecation: @1767225600
Sunset: Fri, 31 Dec 2027 23:59:59 GMT
Link: <https://api.example.test/docs/migrate-orders-v2>; rel="deprecation"
Cache-Control: private, no-store

{"items":[]}
~~~

Trong ví dụ, **@1767225600** tương ứng **01/01/2026 UTC**; **Sunset** (RFC 8594) biểu thị thời điểm dự kiến tài nguyên/ngữ cảnh trở nên không còn khả dụng. **Deprecation không đồng nghĩa API đã bị tắt**, còn **Sunset không tự động làm server ngừng route**. Khi đặt chúng trên response, cần đảm bảo ngày, thông báo, tài liệu migration và lịch triển khai thực tế nhất quán.

**Link** với quan hệ **deprecation** dẫn tới hướng dẫn chuyển đổi. Có thể chỉ ra tài liệu thay thế, ví dụ request/response v2 và liên hệ hỗ trợ; không chuyển hướng POST/PATCH sang endpoint mới một cách tùy tiện vì có thể thay đổi semantics, authentication hoặc side effects.

### 5.2. Tài liệu OpenAPI đánh dấu đúng thành phần đã cũ

~~~yaml
paths:
  /v1/orders:
    get:
      deprecated: true
      summary: Danh sách đơn v1, sẽ ngừng hỗ trợ
      externalDocs:
        description: Cách chuyển sang v2
        url: https://api.example.test/docs/migrate-orders-v2
      responses:
        "200":
          description: Response tương thích cũ
          headers:
            Deprecation:
              description: HTTP Structured Field Date
              schema: {type: string}
            Sunset:
              description: HTTP-date dự kiến kết thúc hỗ trợ
              schema: {type: string}
            Link:
              description: Link tới tài liệu deprecation
              schema: {type: string}
~~~

**deprecated: true** trên operation/parameter/property phù hợp giúp công cụ tài liệu và code generation cảnh báo tại chỗ. Nó **không tự tạo Deprecation HTTP header**, không chủ động liên hệ consumer và không chứng minh SDK cũ đã biến mất. Nếu chỉ **customerCode** bị loại bỏ, nên đánh dấu **property đó deprecated** thay vì đánh dấu cả API v2 không còn được khuyến nghị.

## 6. Phát hiện việc dùng request cũ và giới hạn quan sát response

### 6.1. Route cũ và header phiên bản

Những tín hiệu có thể thu ở gateway/server:

- **Method + route template + API version** như GET /v1/orders, tránh gắn nguyên ID/path vào metric.
- Media type có version trong **Accept** hoặc **Content-Type** nếu API thực sự dùng content negotiation.
- **Query parameter cũ** như page, offset hoặc legacySort; cần biết nó được chấp nhận hay bị từ chối.
- **Header đặc thù cũ** nếu còn được hỗ trợ, chẳng hạn X-Api-Version.
- Trạng thái **200/4xx/5xx**, client identity đã xác thực, thời điểm và kết quả xử lý.

Nếu một yêu cầu gửi cả tham số cũ lẫn mới, phải định nghĩa precedence ở hợp đồng. Đừng âm thầm bỏ qua legacy parameter rồi đếm request là “đã migrate” chỉ vì URI v2.

### 6.2. Request JSON: phát hiện tại bộ giải mã hoặc điểm chuyển đổi

Ví dụ API từng nhận **customerCode**, nay dùng **customerId**:

~~~json
{"customerCode":"C-100","amount":250000}
~~~

Nếu còn duy trì compatibility adapter, có thể ghi **sự kiện “legacy field present”** khi bộ giải mã thấy property customerCode trước khi chuyển sang DTO mới. Không nên log cả request body. Sự hiện diện field **không chứng minh nội dung hợp lệ hoặc được sử dụng**: cần phân biệt **present**, **validated**, **converted**, **rejected**.

Trong Java, nếu bind trực tiếp vào DTO rồi bỏ field cũ, bộ giải mã có thể không biết một client đã gửi property deprecated. Một bước parse **JsonNode** có kiểm soát, custom deserializer hoặc adapter có thể ghi telemetry tại đúng nơi field được đọc. Không nên dựng một filter đọc raw InputStream để soi mọi JSON request rồi quên xử lý multipart, streaming, encoding và giới hạn body.

### 6.3. Response field: tại sao server không biết client có đọc?

Server phát:

~~~json
{
  "customerCode": "C-100",
  "customerId": "cust-100"
}
~~~

Access log chỉ xác nhận response có/không có trường; HTTP **không có cơ chế mặc định để biết consumer đã parse hoặc sử dụng trường nào**. Phát hiện dependency cần kết hợp:

1. **Client/SDK telemetry** có sự đồng ý và được thiết kế riêng: ví dụ event khi getter deprecated được gọi, không gửi nội dung field.
2. **Consumer contract tests** do partner/client sở hữu, xác minh khả năng chạy khi bỏ field.
3. **Canary/opt-in phiên bản mới** trong môi trường kiểm soát, quan sát lỗi schema parsing và hành vi nghiệp vụ; có rollback.
4. **Trao đổi owner** và kiểm tra pipeline cũ/cron mà telemetry không bao phủ.

Đừng tự kết luận “không còn phụ thuộc customerCode” chỉ vì request không chứa **customerCode**; đó là **response property**, không xuất hiện trong request.

### 6.4. Những hành vi khó phát hiện qua schema

Consumer có thể phụ thuộc vào:

- **200 với []** thay vì **204**, hoặc lỗi có **code** ổn định.
- Thứ tự bản ghi mặc định, pagination offset/cursor, cách tính totalItems.
- **ETag/If-Match/If-None-Match** và sự khác biệt **304/412/428**.
- Retry và idempotency của POST, cách xử lý duplicate request.
- Thời hạn cache, **Cache-Control** hoặc cấu trúc error body.

Những dependency này cần **contract scenarios** và negative tests, không chỉ so diff OpenAPI rồi tin rằng schema tương thích là toàn bộ semantics tương thích.

## 7. Đo lường và quyết định mức độ chắc chắn

### 7.1. Đừng dùng request count làm đại diện cho số consumer

Giả sử tuần trước có **60.000 request v1** nhưng chỉ đến từ **một cron job**, trong khi **ba đối tác khác** không chạy trong tuần đó. Cả ba phép đo đều có ích nhưng khác nhau:

| Chỉ số | Câu hỏi trả lời | Điểm cần lưu ý |
|---|---|---|
| **Request volume per legacy contract** | Có bao nhiêu lần sử dụng route/field cũ? | Một client có thể phát nhiều request |
| **Distinct registered consumers** | Có bao nhiêu client identity tin cậy vẫn gọi? | Shared credentials có thể che nhiều ứng dụng |
| **Last seen + frequency** | Consumer hoạt động vào lúc nào, chu kỳ ra sao? | Chưa đủ cho batch hiếm/offline |
| **Unknown identity percentage** | Bao nhiêu traffic chưa thể gắn owner? | Tỷ lệ cao làm giảm độ chắc chắn |
| **Coverage of routes/edges** | Nơi nào chưa được đo? | Gateway và origin có thể thấy traffic khác nhau |
| **Contract test adoption** | Bao nhiêu consumer đã chứng minh chạy được v2? | Test cần đại diện cho workflow thực |
| **Error rate on v2 canary** | Migration gây lỗi parsing/nghiệp vụ không? | Cần xem cả status và business outcome |

### 7.2. Một bảng go/no-go minh họa

| Nhóm | Tín hiệu | Hành động |
|---|---|---|
| **Đã chuyển** | Không còn gọi v1 trong cửa sổ phù hợp, test v2 đạt, owner xác nhận | Giữ theo dõi cho đến hết kế hoạch sunset |
| **Còn phụ thuộc** | Vẫn gọi route/field cũ hoặc test bỏ field thất bại | Liên hệ owner, lập deadline, không tắt bất ngờ |
| **Chưa xác định** | Credential dùng chung, không có log hoặc offline dài | Mở rộng quan sát, kiểm owner, hoãn quyết định có rủi ro |
| **Không thể chuyển ngay** | Có ràng buộc vendor/thiết bị không hỗ trợ update | Đánh giá ngoại lệ, compatibility shim giới hạn thời gian |

Đặt ngưỡng theo **rủi ro cụ thể** thay vì lấy một con số chung cho mọi hệ thống. Với endpoint thanh toán, “1 consumer hiếm” vẫn có thể quan trọng hơn “1 triệu request thành công ở v2”. Trong báo cáo, cần phân biệt **đã đo không thấy** và **không có cách đo**.

## 8. Java/Spring: thu tín hiệu sử dụng hợp đồng cũ có kiểm soát

Ví dụ Spring Boot 3 / Spring MVC dùng **HandlerInterceptor** để đếm request:

- Gọi **GET /v1/orders** — route deprecated.
- Gọi **GET /orders?page=...** — query parameter cũ còn được compatibility adapter hỗ trợ.

Chỉ dùng **tên route cố định và signal có tập giá trị hữu hạn** để tránh metrics cardinality cao. Giới hạn ví dụ: các lỗi bị chặn ở CDN/gateway hoặc Spring Security filter trước khi đến MVC **sẽ không xuất hiện** trong interceptor này.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.HandlerMapping;

@Component
final class LegacyContractInterceptor implements HandlerInterceptor {
    private final MeterRegistry meterRegistry;

    LegacyContractInterceptor(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler, Exception exception) {

        Object matched = request.getAttribute(
            HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
        if (!(matched instanceof String route)) {
            return;
        }

        // Một contract có thể chứa nhiều nhánh compatibility.
        if ("GET".equals(request.getMethod())
                && "/v1/orders".equals(route)) {
            count("legacy-route", "GET /v1/orders");
        }

        if ("GET".equals(request.getMethod())
                && "/orders".equals(route)
                && request.getParameterMap().containsKey("page")) {
            count("legacy-page", "GET /orders");
        }
    }

    private void count(String signal, String route) {
        meterRegistry.counter(
            "api.legacy.usage",
            "contract", "orders-v1",
            "signal", signal,
            "route", route
        ).increment();
    }
}
~~~

Đăng ký interceptor:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class LegacyTelemetryConfig implements WebMvcConfigurer {
    private final LegacyContractInterceptor interceptor;

    LegacyTelemetryConfig(LegacyContractInterceptor interceptor) {
        this.interceptor = interceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(interceptor)
            .addPathPatterns("/v1/orders", "/orders");
    }
}
~~~

**Micrometer counter chỉ đo tổng số**, không cung cấp inventory từng client. Để liên hệ consumer, ứng dụng cần một **event/audit stream có phân quyền**, gắn registered client_id/service principal **được xác minh**, không dùng giá trị tự khai như X-Client-ID làm danh tính mặc định. **Không** đưa consumerId, tenantId, token, raw URI, query values, order ID hoặc correlation ID làm metric tags vì nguy cơ rò thông tin và tăng cardinality.

### 8.1. Ghi nhận field cũ ở đúng điểm chuyển đổi

Khi một endpoint còn chấp nhận request JSON cũ:

~~~java
import com.fasterxml.jackson.databind.JsonNode;

void adaptRequest(JsonNode payload, TrustedClientContext caller) {
    boolean legacyFieldPresent = payload.has("customerCode");

    if (legacyFieldPresent) {
        // Event chỉ chứa signal + identity đã xác thực và
        // được bảo vệ, KHÔNG chứa customerCode/raw payload.
        legacyUsageRecorder.record(
            "orders.customerCode.request", caller.registeredClientId());
    }

    // Validate, phân quyền, sau đó chuyển đổi field cũ
    // sang model mới theo quy tắc đã công bố.
}
~~~

**legacyUsageRecorder** và **TrustedClientContext** là abstraction giả định của ứng dụng. Ví dụ này dùng **has** để phát hiện property có mặt, kể cả khi JSON value là null; cần đo riêng **được sử dụng sau khi validate/convert** nếu muốn biết phụ thuộc thực tế. Một adapter phải từ chối tổ hợp trường mâu thuẫn theo hợp đồng, không tự ưu tiên field cũ và mới một cách im lặng.

### 8.2. Trả header deprecation từ endpoint cũ

~~~java
import java.time.Instant;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;

ResponseEntity<OrderPage> legacyList(OrderPage page) {
    String deprecatedAt = "@" +
        Instant.parse("2026-01-01T00:00:00Z").getEpochSecond();

    return ResponseEntity.ok()
        .header("Deprecation", deprecatedAt)
        .header("Sunset", "Fri, 31 Dec 2027 23:59:59 GMT")
        .header(HttpHeaders.LINK,
            "<https://api.example.test/docs/migrate-orders-v2>;" +
            " rel=\"deprecation\"")
        .cacheControl(CacheControl.noStore())
        .body(page);
}
~~~

Đây là **phương thức minh họa**, không phải class controller hoàn chỉnh. Ngày tháng, chính sách cache và URL phải đi từ **cấu hình versioning được review**, không hardcode rải khắp controller. Nếu gateway có cache/route rewriting hoặc security filter tạo response sớm, kiểm thử phải xác minh header **trên response cuối cùng**.

## 9. Kiểm thử và đối chiếu số liệu trước khi tắt v1

### 9.1. MockMvc cho tín hiệu route và field

Test HTTP có thể xác minh status/header và counter:

~~~java
// Giả định MockMvc, fixture Orders, SimpleMeterRegistry
// và một principal có quyền đã được cấu hình.
mockMvc.perform(get("/v1/orders")
        .with(user("partner-test")))
    .andExpect(status().isOk())
    .andExpect(header().exists("Deprecation"))
    .andExpect(header().exists("Sunset"))
    .andExpect(header().string(
        "Link", org.hamcrest.Matchers.containsString(
            "rel=\"deprecation\"")));

double legacyRouteCount = meterRegistry
    .get("api.legacy.usage")
    .tag("contract", "orders-v1")
    .tag("signal", "legacy-route")
    .tag("route", "GET /v1/orders")
    .counter().count();
assertEquals(1.0, legacyRouteCount);
~~~

Trong test thật, dùng **MeterRegistry mới cho mỗi fixture/test** hoặc đo chênh lệch trước–sau, tránh assert bằng 1 khi test khác đã ghi counter. Phần import của MockMvc, JUnit, Hamcrest và Spring Security Test được lược bỏ; đây là **trích đoạn trong phương thức test**, không phải class Java độc lập.

Test thêm trường hợp:

- GET **/orders?page=2** tạo signal **legacy-page**, GET **/orders?cursor=...** không tạo signal đó.
- POST JSON có **customerCode** kích hoạt adapter telemetry; cùng payload chỉ có **customerId** không kích hoạt.
- Response 401/403 do security filter từ chối không được hiểu là **consumer đã dùng thành công v1**.
- Gateway/CDN không làm mất Deprecation/Sunset/Link và không làm lộ response riêng tư.

### 9.2. Contract tests của consumer mới là bằng chứng quan trọng

Không phải mọi phụ thuộc đều đo được từ server. Một contract test thực dụng của đối tác có thể:

1. Cấu hình SDK hoặc HTTP client gọi **v2**.
2. Xóa trường **customerCode** khỏi response fixture, chỉ giữ **customerId**.
3. Thay **page/totalPages** bằng hợp đồng **cursor/hasNext** đã công bố.
4. Gửi lại **400/404/409/412** với Problem Details mới để kiểm tra error handling.
5. Chạy workflow **đồng bộ đơn, tạo nhãn và hủy đơn**, không chỉ assert JSON parse.
6. Báo kết quả theo **consumer version + test suite version** để đối chiếu với traffic.

**Schema diff chỉ phát hiện một phần rủi ro.** Bỏ một trường optional có thể là thay đổi phá vỡ client thực nếu logic của họ đang truy cập trường đó. Ngược lại, thêm một field chưa chắc phá vỡ client nhưng những parser cấu hình “reject unknown fields” có thể lỗi; cần kiểm tra hành vi thực.

### 9.3. Một ma trận QA kết hợp telemetry và migration

| Test | Điều cần chứng minh |
|---|---|
| Client v1 gửi request | Có signal usage và phản hồi tương thích trong thời gian hỗ trợ |
| Client v2 gửi request đúng | Không phát legacy signal; hợp đồng response đúng |
| Field cũ trong request | Adapter phát hiện đúng, không log giá trị nhạy cảm |
| Field cũ chỉ trong response | Có test/SDK evidence, không kết luận từ server access log |
| Cùng route qua CDN và trực tiếp origin | Nguồn log không đếm thiếu hoặc đếm đôi không giải thích |
| Consumer không được phép | Không tiết lộ dữ liệu hoặc version/ETag; log có kiểm soát |
| Canary v2 thất bại | Có rollback và biết consumer nào bị ảnh hưởng |
| Consumer batch ngoài cửa sổ 7 ngày | Có lịch test theo chu kỳ và chủ sở hữu xác nhận |

## 10. Quy trình ra quyết định bỏ hợp đồng cũ

Một migration có kiểm soát thường đi qua năm bước:

1. **Khoanh vùng thay đổi:** chỉ rõ route, field, status/header hoặc semantics nào sắp bị bỏ; ghi thời điểm và rủi ro.
2. **Đo và xác định owner:** bật route/field telemetry, phân loại client identity, kiểm tra coverage, cập nhật consumer inventory.
3. **Thông báo và hỗ trợ:** dùng Deprecation, Sunset, tài liệu migration, thông báo trực tiếp; cung cấp v2 và test fixture.
4. **Chuyển đổi và thử có kiểm soát:** consumer chạy contract tests trên v2, chuyển traffic thực theo canary/opt-in, giám sát lỗi và business outcomes.
5. **Ra quyết định có bằng chứng:** so usage còn lại, unknown clients, batch chu kỳ dài, ngoại lệ, an toàn bảo mật và kế hoạch rollback. Chỉ ngừng hỗ trợ khi tiêu chí đã duyệt.

Nếu việc bỏ route khiến client cũ tiếp tục gọi, **410 Gone** có thể diễn đạt resource đã bị loại bỏ có chủ đích khi API muốn thông báo; **404 Not Found** cũng có thể phù hợp theo chính sách và không tiết lộ sự tồn tại. Không dùng **426 Upgrade Required** chỉ để yêu cầu client đổi phiên bản JSON API: 426 gắn với nâng cấp giao thức truyền thông HTTP, không phải mã chung cho ngừng v1.

### 10.1. Case study: lỗi đồng bộ vào cuối tháng

Đội Orders API quan sát 30 ngày: v1 còn một ít request, nhưng dashboard hằng ngày gần như bằng 0. Tìm trong inventory thấy **logistics-batch** có lịch chạy **ngày cuối tháng**; test fixture phát hiện đối tác vẫn parse **customerCode**. Nhóm làm ba việc:

- Giữ v1 đến khi batch chạy thử đủ một chu kỳ với v2; thống nhất owner và thời hạn migration.
- Bổ sung contract test loại bỏ customerCode, thêm cursor pagination và kiểm status/error handler.
- Sau khi canary đạt, theo dõi cả route usage, **business outcome** (số đơn đồng bộ đủ) và khả năng rollback; không chỉ tỷ lệ 2xx.

**Bài học:** lịch sử request giúp tìm consumer; **workflow và contract test** mới chứng minh họ không còn phụ thuộc dữ liệu cũ.

## 11. Bài thực hành

Một API hóa đơn dự kiến bỏ **GET /v1/invoices**, trường response **legacyTaxCode**, và query **page** để chuyển sang cursor. Tổ chức có web app, mobile app offline và đối tác chạy cron ngày 01 hằng tháng.

**Yêu cầu:** (1) đề xuất hai loại telemetry tại gateway/server và một bằng chứng phía consumer; (2) chọn danh tính client tin cậy và trường không được log; (3) viết Deprecation/Sunset/Link cho v1 và đánh dấu OpenAPI; (4) thiết kế 3 contract tests về pagination, lỗi và legacyTaxCode; (5) quyết định có thể tắt v1 sau 14 ngày không thấy request hay không.

**Gợi ý:** đo **method + route template + version**, sự hiện diện **page** tại adapter, client identity đã xác thực; response field cần **client test/SDK telemetry**. Log không chứa token, raw invoice payload, IP hay tài khoản nhạy cảm tùy tiện. Thử **200 items: []**, cursor continuation, Problem Details và fixture **không còn legacyTaxCode**. **Không tắt v1 chỉ vì 14 ngày bằng 0**, vì cron tháng và mobile offline chưa được quan sát đủ; cần owner confirmation, một chu kỳ thực và đường rollback.

## 12. Checklist và tài liệu tham khảo

- [ ] Danh sách **contract elements** sắp bỏ rõ ràng: route, parameter, field, status, header, hành vi.
- [ ] Có telemetry server/gateway, coverage, unknown-client ratio và cửa sổ phù hợp **batch/offline**.
- [ ] Consumer inventory có **identity đã xác thực, owner, last seen, cadence, version và kế hoạch**.
- [ ] Không nhầm **request sử dụng field cũ** với **response field được consumer đọc**.
- [ ] Deprecation/Sunset và OpenAPI được công bố đúng ngữ nghĩa, tài liệu migration có ví dụ HTTP thực.
- [ ] Metric labels cardinality thấp; log/audit và retention bảo vệ PII, token và dữ liệu tenant.
- [ ] Java/Spring instrumentation không làm thay đổi transaction hoặc availability khi telemetry lỗi.
- [ ] Contract/consumer tests chứng minh v2 chạy được cả **schema và hành vi nghiệp vụ**.
- [ ] Canary, rollback, tiêu chí go/no-go và ngoại lệ được owner phê duyệt trước khi sunset.

Tài liệu tham khảo: [RFC 9745 — The Deprecation HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9745); [RFC 8594 — The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594); [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110); [OpenAPI Specification](https://spec.openapis.org/oas/latest.html); [Spring MVC Interceptors](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html); [Micrometer](https://docs.micrometer.io/micrometer/reference/).

**Ghi nhớ:** Muốn bỏ một hợp đồng REST cũ an toàn, hãy tìm **consumer cụ thể và phần hợp đồng họ thực sự phụ thuộc**, đánh giá khoảng trống telemetry, xác nhận hành vi bằng kiểm thử và ra quyết định dựa trên mức rủi ro. **Không thấy request không có nghĩa không còn consumer.**
