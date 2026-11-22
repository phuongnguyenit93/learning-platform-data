# Sunset header và lịch ngừng phục vụ phiên bản

## 1. Vấn đề: API v1 vẫn chạy hôm nay nhưng sẽ ngừng vào ngày nào?

Một REST API có `/api/v1/orders` và `/api/v2/orders`. Nhiều client cũ vẫn dùng v1 dù v2 đã phát hành. Tắt v1 đột ngột gây lỗi; duy trì mãi làm tăng chi phí bảo mật, kiểm thử và vận hành. Vì vậy API cần **lịch cảnh báo, hướng dẫn chuyển đổi và quyết định retirement có kiểm chứng**.

Trong chương **Tiến hóa API** của module **INTEGRATION_API_REST**, bài học kết nối resource/URI, HTTP methods/status, cache, idempotency, OpenAPI, authentication/authorization và kiểm thử Java/Spring. Trọng tâm là **`Sunset` theo RFC 8594**, so sánh **`Deprecation` theo RFC 9745**.

Bạn sẽ học cách phát header đúng format và scope; lập lịch announce–migrate–sunset–retire; thực hiện cutover, quan sát client còn phụ thuộc và tránh phá giao dịch.

> **`Sunset` là tín hiệu dự kiến resource sẽ không còn đáp ứng sau một mốc thời gian**, không phải lệnh tự tắt route, TTL cache hoặc cam kết server sẽ trả mã HTTP cố định.

## 2. Bốn mốc vòng đời không được đánh đồng

~~~mermaid
flowchart LR
    A["Thông báo"] --> B["Deprecated"]
    B --> C["Migration window"]
    C --> D["Sunset dự kiến"]
    D --> E["Retire thực tế"]
~~~

| Mốc | Ý nghĩa |
|---|---|
| **Announcement** | Công bố v2, tài liệu đổi hợp đồng và lịch hỗ trợ |
| **Deprecation** | Không nên tạo tích hợp mới phụ thuộc v1; v1 vẫn có thể hoạt động |
| **Sunset** | Thời điểm **dự kiến** v1/resource không còn đáp ứng |
| **Retirement/EOL** | Quyết định vận hành thực sự ngừng route/hỗ trợ |

Theo **RFC 9745**, deprecation **không tự đổi hành vi resource**. **RFC 8594** xem Sunset là **gợi ý**, không bảo đảm tài nguyên còn phục vụ đến mốc đó hoặc luôn ngừng đúng mốc. Ngày kết thúc hỗ trợ, ngừng ghi, tắt route và **retention của dữ liệu** có thể khác nhau; cần ghi rõ thay vì chỉ gọi chung “EOL”.

## 3. `Sunset` theo RFC 8594: cú pháp, ý nghĩa và giới hạn

`Sunset` là **response header field** với giá trị **một HTTP-date**:

~~~http
GET /api/v1/orders/913 HTTP/1.1
Host: api.example.test
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
Sunset: Sat, 01 Jan 2028 00:00:00 GMT
Link: <https://developer.example.test/migrations/v1-to-v2>; rel="sunset"; type="text/html"

{"id":"913","status":"PAID"}
~~~

Trong ví dụ, v1 **dự kiến không còn được phục vụ từ 00:00:00 UTC ngày 01/01/2028**. Dòng `Sunset` có định dạng **HTTP-date**, không phải ISO 8601 hay Unix timestamp:

| Giá trị | Dùng cho `Sunset` được không? | Lý do |
|---|---|---|
| `Sat, 01 Jan 2028 00:00:00 GMT` | **Có** | HTTP-date, giờ GMT/UTC rõ ràng |
| `2028-01-01T00:00:00Z` | **Không** | ISO 8601 không phải cú pháp Sunset |
| `@1830297600` | **Không** | Đây là dạng Structured Field Date, không phải HTTP-date |
| `2028-01-01` | **Không** | Thiếu ngày giờ và cú pháp HTTP |

RFC 8594 khuyến nghị timestamp Sunset **nằm trong tương lai**. Nếu client gặp ngày Sunset đã qua, cách an toàn là coi resource **có thể trở nên không khả dụng bất kỳ lúc nào**, thay vì tự động cho rằng server đã ngừng hoạt động.

### `Sunset` chỉ là metadata, không thay hợp đồng khác

- Không làm một request **GET/POST/PATCH** tự động thất bại.
- Không đổi **media type**, JSON schema hay ý nghĩa của mã HTTP 200/201/204.
- Không yêu cầu mọi client tự động chuyển sang v2.
- Không tự đặt `Cache-Control`, TTL, CORS hay tắt một route trong Spring/gateway.
- Không bảo đảm tất cả các URI cùng tiền tố `/api/v1/` sẽ ngừng nếu API không công bố phạm vi đó.

### Link relation `sunset` cung cấp điều gì?

**RFC 8594** đăng ký link relation **`sunset`** để trỏ đến tài liệu về **chính sách retirement** và phương án migration:

~~~http
Link: <https://developer.example.test/migrations/v1-to-v2>; rel="sunset"; type="text/html"
~~~

URI trong `Link` thường dẫn đến trang hướng dẫn, ngày cắt, affected endpoints, mapping v1→v2 và liên hệ hỗ trợ; nó **không tự là endpoint thay thế của resource**. Không tự gửi POST đến URL tài liệu này.

## 4. `Deprecation` theo RFC 9745: biết khi nào không nên phụ thuộc mới

Nhiều nhóm từng dùng header tự đặt như `X-Deprecated: true`. Hiện có **RFC 9745 (2025)** chuẩn hóa `Deprecation` response header. Giá trị của nó là **Structured Field Date**, ký hiệu **`@<Unix-seconds>`**:

~~~http
Deprecation: @1798761600
~~~

Giá trị trên tương ứng **01/01/2027 00:00:00 UTC**. Nó mô tả **ngày deprecation bắt đầu** (có thể ở quá khứ hoặc tương lai), **không phải ngày server ngừng trả response**.

Một response có cả hai header:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Deprecation: @1798761600
Sunset: Sat, 01 Jan 2028 00:00:00 GMT
Link: <https://developer.example.test/deprecations/v1>; rel="deprecation"; type="text/html"
Link: <https://developer.example.test/migrations/v1-to-v2>; rel="sunset"; type="text/html"

{"id":"913","status":"PAID"}
~~~

**Cách đọc:** v1 được xem là deprecated từ **01/01/2027**, dự kiến sunset từ **01/01/2028**. Theo RFC 9745, nếu phát cả `Deprecation` và `Sunset`, **timestamp Sunset MUST NOT sớm hơn Deprecation**. Hai trường khác định dạng; công cụ kiểm thử phải parse từng trường đúng chuẩn.

| Tiêu chí | `Deprecation` | `Sunset` |
|---|---|---|
| Chuẩn | RFC 9745 | RFC 8594 |
| Dữ liệu | Structured Field Date, ví dụ `@1798761600` | HTTP-date, ví dụ `Sat, 01 Jan 2028 00:00:00 GMT` |
| Ý nghĩa | Resource sẽ/đã deprecated | Resource được dự kiến ngừng đáp ứng |
| Hành vi runtime tự thay đổi? | **Không** | **Không** |
| Link relation bổ sung | `rel="deprecation"` | `rel="sunset"` |
| Mục đích tài liệu | Lý do deprecate, đường thay thế, chính sách | Lịch retire, phạm vi và migration |

`Link rel="deprecation"` có thể cung cấp **tài liệu chính sách ngay cả trước ngày deprecated**. Việc công bố một link như vậy **không có nghĩa resource đã deprecated** nếu chưa có thông báo thời điểm/điều kiện tương ứng.

**Không** viết `Deprecation: true` hay `Deprecation: Fri, 01 Jan 2027 ... GMT` nếu muốn tuân RFC 9745. Cũng không ghi `Sunset: @1830297600`: hai chuẩn dùng cú pháp ngày riêng.

## 5. Phạm vi: Sunset một resource không tự bao trùm toàn bộ v1

Theo mặc định, `Sunset`/`Deprecation` áp dụng cho **resource được xác định bởi response**. API có thể định nghĩa phạm vi lớn hơn nếu **công bố rõ**:

- **Theo route:** chỉ `/api/v1/reports` nghỉ phục vụ.
- **Theo nhóm:** mọi method trên `/api/v1/orders/**`.
- **Theo phiên bản:** các resource được liệt kê trong policy v1 cùng có lịch retirement.

Header từ `GET /api/v1` **không tự đặt lịch chuẩn cho mọi URI con**. Client không biết quy tắc scope riêng sẽ hiểu header theo nghĩa chuẩn tại resource hiện tại.

Khi thực hiện, kiểm tra **GET/POST/PATCH/DELETE**, response 200/201/204 và **lỗi từ security filter/gateway**; kiểm tra nhiều region/representation và đừng gắn lịch v1 cho v2. Tránh nhầm ngày Sunset **phiên bản** với ngày hết hạn của token, hồ sơ hay tài nguyên cá nhân.

## 6. Lịch ngừng phục vụ minh họa và tài liệu chuyển đổi

Một lộ trình có thể công bố từ **15/12/2026** (ví dụ, không phải thời hạn RFC bắt buộc):

| Mốc UTC | Hành động |
|---|---|
| **15/12/2026** | Announce v2, changelog và migration guide |
| **01/01/2027** | Deprecation bắt đầu, phát `Deprecation: @1798761600` |
| **01/03/2027** | Đo client v1, liên hệ partners, hỗ trợ nâng SDK |
| **01/07/2027** | Contract tests, canary và đánh giá các client trọng yếu |
| **01/11/2027** | Final notice, xác nhận kế hoạch go/no-go |
| **01/01/2028 00:00 UTC** | Sunset dự kiến; **quyết định retire bằng policy/gateway** |
| **Sau đó** | Theo dõi lỗi v1, hỗ trợ đối soát và lưu tài liệu |

Có thể phát **Deprecation date tương lai và Sunset cùng lúc** để client lập kế hoạch. Thời gian thông báo phải tính đến **mobile release cycles, đối tác triển khai chậm, ràng buộc SLA và độ phức tạp breaking changes**.

Migration guide tối thiểu phải nêu **scope route/method/version; mapping v1→v2 (URI, payload, enum, error/status, pagination); OAuth scopes và secret rotation; retry/idempotency; SDK/sandbox; lịch support/sunset; owner và kênh hỗ trợ**. Một thông báo “v1 will be removed” không ngày, không đường chuyển là chưa đủ.

## 7. Chuyển v1 sang v2: thay URI không phải toàn bộ migration

So sánh một hợp đồng v1 và v2:

~~~http
GET /api/v1/orders/913 HTTP/1.1
Host: api.example.test
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
Deprecation: @1798761600
Sunset: Sat, 01 Jan 2028 00:00:00 GMT

{"id":"913","total":150000,"status":"PAID"}
~~~

~~~http
GET /api/v2/orders/913 HTTP/1.1
Host: api.example.test
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "913",
  "total": {"amountMinor": 150000, "currency": "VND"},
  "state": "PAID"
}
~~~

Nếu client chỉ đổi `/v1/` thành `/v2/` nhưng vẫn đọc `total` ở cấp root, phép chuyển đổi **sẽ sai**. Cần kiểm tra cả:

| Khía cạnh | Câu hỏi migration |
|---|---|
| **Resource/URI** | Resource ID có giữ nguyên? Link relation, location và URI template đổi không? |
| **HTTP method** | POST/PUT/PATCH có còn cùng tác động? Có chuyển thành job 202? |
| **Payload** | Required/nullability, enum, money/timezone/decimal semantics thay đổi ra sao? |
| **Pagination** | Offset sang cursor? Client xử lý next link và trang cuối thế nào? |
| **Caching** | Cache keys, ETag, Last-Modified và `Vary` có giữ nguyên? |
| **Error contract** | 400/409/412/422/429 và Problem Details có khác? |
| **Security** | OAuth scope, resource authorization, token audience có đổi? |
| **Retry** | `Idempotency-Key` scope theo version? Lệnh ghi từ v1 và v2 có thể bị thực thi trùng không? |

**Không tự động chuyển toàn bộ POST từ v1 sang v2 bằng redirect** nếu chưa chứng minh method, body, quyền và idempotency tương thích. HTTP 301/302 có lịch sử làm một số client đổi method trong tình huống nhất định; 307/308 bảo toàn method, nhưng **không** bảo đảm request body, token, schema v2 và nghiệp vụ đều tương thích. Thay đổi target origin còn có rủi ro lộ credentials. Migration cho thao tác có side effect thường nên **sửa client theo hợp đồng mới**, không trông chờ redirect ngầm.

## 8. Ngừng phục vụ thực tế: 410, 404 hay lỗi khác?

Khi tổ chức **đã quyết định retire** v1, gateway/server phải triển khai hành vi riêng; `Sunset` một mình không làm việc đó. Một lựa chọn khi URI **đã biết từng tồn tại và không còn khả dụng lâu dài** là **410 Gone**:

~~~http
GET /api/v1/orders/913 HTTP/1.1
Host: api.example.test

HTTP/1.1 410 Gone
Content-Type: application/problem+json
Cache-Control: no-store
Link: <https://developer.example.test/migrations/v1-to-v2>; rel="sunset"; type="text/html"

{
  "type": "https://api.example.test/problems/api-version-retired",
  "title": "API version retired",
  "status": 410,
  "detail": "Phiên bản v1 đã ngừng phục vụ. Hãy chuyển sang hợp đồng v2.",
  "code": "API_VERSION_RETIRED"
}
~~~

**410** thích hợp khi server biết URI không còn khả dụng và tình trạng có khả năng lâu dài. **404 Not Found** có thể phù hợp nếu server không duy trì thông tin resource cũ hoặc không muốn tiết lộ sự tồn tại; cần nhất quán với security policy. **503** thể hiện tạm không phục vụ và không phải dấu hiệu tương đương vĩnh viễn với sunset. **426 Upgrade Required** liên quan nâng cấp giao thức theo HTTP, **không phải mã mặc định để ép client đổi API v1 sang v2**.

Sau retirement, không nên mặc định xóa database hay từ chối **truy vấn kế toán/đối soát hợp pháp**: lưu giữ dữ liệu, truy cập audit, export, legal hold và chính sách bảo vệ dữ liệu có vòng đời riêng.

### Cutover/rollback cần phân biệt với thông báo Sunset

Trong migration, có thể triển khai canary từng nhóm khách, chuyển đọc trước rồi chuyển ghi, hỗ trợ song song hai API trong giới hạn và rollback khi phát hiện lỗi. Nhưng nếu đã **phát sinh side effects trên v2** (thanh toán, hoàn tiền, sự kiện), rollback code/route **không hoàn tác** những thao tác đó. Cần business reconciliation và thiết kế mapping ID/idempotency trước khi cutover.

## 9. Spring Boot 3: gắn header đúng scope của v1

Một cách triển khai là **Servlet Filter** gắn metadata lên response của `/api/v1` và `/api/v1/**`. Ví dụ này phù hợp mô hình **Spring Boot 3 / Jakarta Servlet** và giả định chính sách v1 thống nhất:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class V1LifecycleHeadersFilter extends OncePerRequestFilter {
    private static final Instant DEPRECATION =
            Instant.parse("2027-01-01T00:00:00Z");
    private static final Instant SUNSET =
            Instant.parse("2028-01-01T00:00:00Z");
    // IMF-fixdate yêu cầu dd gồm hai chữ số (RFC 9110).
    private static final DateTimeFormatter HTTP_DATE =
            DateTimeFormatter.ofPattern(
                    "EEE, dd MMM yyyy HH:mm:ss 'GMT'", Locale.US)
                    .withZone(ZoneOffset.UTC);

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getServletPath();
        return !(path.equals("/api/v1") || path.startsWith("/api/v1/"));
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        // RFC 9745: Structured Field Date = @ + Unix epoch seconds.
        response.setHeader("Deprecation",
                "@" + DEPRECATION.getEpochSecond());

        // RFC 8594: HTTP-date in GMT.
        response.setHeader("Sunset",
                HTTP_DATE.format(SUNSET));

        response.addHeader("Link",
                "<https://developer.example.test/deprecations/v1>"
                + "; rel=\"deprecation\"; type=\"text/html\"");
        response.addHeader("Link",
                "<https://developer.example.test/migrations/v1-to-v2>"
                + "; rel=\"sunset\"; type=\"text/html\"");

        chain.doFilter(request, response);
    }
}
~~~

**Những giới hạn cần hiểu khi dùng trong production:**

1. Filter chỉ **thêm metadata**; nó **không tự retire** `/api/v1/**`. Thay đổi route/gateway để trả 410/404 phải là quyết định triển khai riêng.
2. Những ngày cứng trong code chỉ để học. Thực tế nên dùng **configuration được kiểm soát**, xác nhận `sunset >= deprecation`, có change review và đồng bộ giữa node/region.
   Lưu ý `DateTimeFormatter.RFC_1123_DATE_TIME` của Java có thể xuất ngày tháng bằng **một chữ số**; ví dụ dùng formatter IMF-fixdate với `dd` để phát đúng `Sat, 01 Jan ... GMT`.
3. `request.getServletPath()` phù hợp ví dụ ứng dụng mapping theo servlet path; nếu có **context path, gateway rewrite, forward/error dispatch**, phải test đúng đường public và các response đi qua security/gateway.
4. `@Component` filter được đăng ký theo cơ chế servlet, nhưng một **401/403 sinh từ security filter** hoặc response lỗi ở gateway có thể bị xử lý/ghi lại khác tùy filter ordering. Kiểm chứng bằng integration tests thực; không tuyên bố mọi lỗi đều có header chỉ từ snippet này.
5. Dùng `addHeader("Link", ...)` để giữ nhiều relation, nhưng nếu proxy đã phát `Link` riêng cần bảo đảm không tạo bản trùng/mâu thuẫn. Không ghi đè cache/security headers ngoài ý muốn.

### CORS khi frontend cần đọc header

Với JavaScript chạy cross-origin, nếu UI cần đọc lifecycle headers, server có thể cần:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Expose-Headers: Deprecation, Sunset, Link
Vary: Origin
~~~

Phải dùng chính sách **allowed origins/credentials** phù hợp; CORS không thay authorization và không cho mọi origin đọc các response có thông tin cá nhân. Nếu response còn biến đổi theo `Accept` hay `Accept-Language`, `Vary` phải phản ánh các yếu tố đó theo đúng logic cache.

## 10. Cache/CDN và độ tin cậy của thông báo

`Sunset` **không phải `Expires`, `Cache-Control: max-age` hay validator**. Nó chỉ mô tả **vòng đời khả dụng**. Một response có:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, max-age=60
ETag: "orders-913-v6"
Sunset: Sat, 01 Jan 2028 00:00:00 GMT

{"id":"913","status":"PAID"}
~~~

Cache có thể tái sử dụng response theo **freshness** nếu các quy tắc HTTP caching cho phép. Việc xuất hiện Sunset **không tự thay TTL**. Khi ngày Sunset được thay đổi, một cache còn giữ response cũ có thể tiếp tục phát **lịch cũ** tới client cho đến khi revalidation/invalidation xảy ra.

Vì vậy:

- Chọn TTL dựa trên **dữ liệu nghiệp vụ và tần suất cập nhật lịch**; giảm TTL hoặc purge khi thay ngày nếu cần lan truyền nhanh.
- Đảm bảo **CDN, gateway, WAF và reverse proxy** không vô ý loại bỏ `Sunset`, `Deprecation` hay `Link`.
- Nếu các representation khác nhau theo `Accept/Accept-Language/Origin`, giữ `Vary` đúng để tránh trộn bản.
- Với response riêng tư, áp `private` hoặc `no-store` theo đánh giá dữ liệu, **không dùng Sunset để ra quyết định cache privacy**.
- Khi endpoint retired, phải đảm bảo 410/404 từ gateway không bị cache dưới điều kiện sai, nhất là khi kế hoạch có rollback.

`Date`/UTC, giờ hệ thống và lịch tại nhiều region phải thống nhất. Tránh tự tạo `Sunset` theo timezone địa phương mà không chuyển thành GMT; một thay đổi ngày vài giờ có thể ảnh hưởng batch job của đối tác.

## 11. OpenAPI: `deprecated: true` không thay thế Sunset

OpenAPI có trường **`deprecated: true`** ở **Operation Object** để mô tả rằng operation không nên dùng cho tích hợp mới:

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /api/v1/orders/{orderId}:
    get:
      operationId: getLegacyOrder
      deprecated: true
      summary: Đọc đơn hàng qua v1 (sắp ngừng phục vụ)
      description: >
        Chuyển sang GET /api/v2/orders/{orderId}.
        Deprecation từ 2027-01-01T00:00:00Z,
        Sunset dự kiến 2028-01-01T00:00:00Z.
      parameters:
        - name: orderId
          in: path
          required: true
          schema: {type: string}
      responses:
        '200':
          description: Đơn hàng v1
          headers:
            Deprecation:
              description: RFC 9745 Structured Field Date
              schema: {type: string}
              example: '@1798761600'
            Sunset:
              description: RFC 8594 HTTP-date
              schema: {type: string}
              example: 'Sat, 01 Jan 2028 00:00:00 GMT'
            Link:
              description: rel=deprecation và rel=sunset
              schema: {type: string}
          content:
            application/json:
              schema:
                type: object
                properties:
                  id: {type: string}
                  status: {type: string}
        '410':
          description: URI v1 không còn khả dụng sau retirement
          content:
            application/problem+json:
              schema:
                type: object
~~~

**Giới hạn của OpenAPI:**

- `deprecated: true` **không chứa một ngày Sunset chuẩn cho toàn bộ API**.
- Header definitions trong một response mô tả **điều có thể xuất hiện**, không tự khiến runtime phát header.
- Một v1 có nhiều operation phải có **phạm vi, lịch và schema cũ** được duy trì chính xác; không sửa tài liệu v1 thành schema v2 chỉ vì muốn giảm file.
- Nếu gateway phát header cả trên lỗi 401/403/404, có thể bổ sung mô tả hoặc conventions cho các response đó thay vì chỉ liệt kê dưới 200.
- Một tổ chức có thể dùng **vendor extensions** để phục vụ tooling nội bộ, nhưng extension không phải chuẩn thay thế RFC 8594/9745.

Khi tiến hóa API, pipeline nên **diff OpenAPI v1/v2**: tìm breaking changes ở method, path, schema, status, validation và security, rồi xác định migration guide/SDK tương ứng.

## 12. Bảo mật và quản trị lịch ngừng phục vụ

- **Auth không thay đổi chỉ vì deprecated:** v1 vẫn kiểm tra bearer token, tenant, object-level authorization, rate limit và audit cho tới lúc retire.
- **Link migration:** dùng HTTPS và domain đáng tin; client không chuyển Authorization, thông tin thanh toán hoặc token sang URL lạ.
- **Response riêng tư:** header có thể tiết lộ vòng đời một đối tượng nhạy cảm, nên cần chọn phạm vi/scope phù hợp.
- **Redirect unsafe methods:** POST chuyển host hoặc đổi schema dễ gây lộ credential/side effect trùng; không auto-follow thiếu allowlist và idempotency.
- **Cấu hình lịch:** quản lý bằng change review, audit và triển khai nhất quán giữa gateway, app, docs, cache/region.
- **Retirement:** vẫn tuân privacy/BOLA; 410/404 không tiết lộ tài nguyên của tenant khác.
 
Nếu phát hiện lỗ hổng nghiêm trọng có thể phải ngừng trước Sunset, vì header không bảo đảm availability tuyệt đối. Đây là **incident/ngoại lệ cần thông báo**, không phải lý do tùy tiện rút ngắn lịch đã công bố.

## 13. Kiểm thử Spring/HTTP và pipeline trước cutover

Mục tiêu kiểm thử không phải chỉ kiểm tra header tồn tại, mà là **đúng cú pháp, đúng scope, đúng mốc và đúng hành vi sau retirement**.

### MockMvc: v1 có Sunset, v2 không bị nhiễm lịch v1

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ApiLifecycleHeadersTest {
    @Autowired MockMvc mvc;

    @Test
    void v1AdvertisesDatesAndLinks() throws Exception {
        // Fixture: endpoint v1 và principal có quyền.
        mvc.perform(get("/api/v1/orders/913"))
           .andExpect(status().isOk())
           .andExpect(header().string("Deprecation", "@1798761600"))
           .andExpect(header().string(
                   "Sunset", "Sat, 01 Jan 2028 00:00:00 GMT"))
           .andExpect(header().stringValues("Link",
                   "<https://developer.example.test/deprecations/v1>"
                   + "; rel=\"deprecation\"; type=\"text/html\"",
                   "<https://developer.example.test/migrations/v1-to-v2>"
                   + "; rel=\"sunset\"; type=\"text/html\""));
    }

    @Test
    void v2DoesNotInheritV1Sunset() throws Exception {
        mvc.perform(get("/api/v2/orders/913"))
           .andExpect(status().isOk())
           .andExpect(header().doesNotExist("Sunset"))
           .andExpect(header().doesNotExist("Deprecation"));
    }
}
~~~

Test là **khung minh họa** cần controller, fixtures, authentication và filter order như ứng dụng thật; không khẳng định đã được chạy. `header().stringValues("Link", ...)` giả định filter phát **hai field values** theo cách MockMvc quan sát; proxy có thể gộp chúng thành một field theo HTTP, nên kiểm thử qua gateway cần **parse Link header theo cú pháp**, không chỉ so raw header bytes.

### Ma trận kiểm thử khuyến nghị

| Trường hợp | Bất biến cần chứng minh |
|---|---|
| **RFC syntax** | `Sunset` parse HTTP-date; `Deprecation` parse Structured Field Date |
| **Ordering** | Sunset không sớm hơn Deprecation; config sai fail deployment/check |
| **Resource scope** | v1 routes có metadata; v2 không bị gắn nhầm |
| **Methods/status** | GET/POST/PATCH/DELETE và 200/201/204/4xx được xử lý theo policy |
| **Gateway/WAF** | Header không bị strip; date và link giống ở region khác |
| **Cache** | Thay ngày/policy được lan truyền sau purge hoặc hết TTL |
| **CORS** | Frontend origin được phép đọc Deprecation/Sunset/Link |
| **Authorization** | 401/403 và object-level access không bị bỏ qua bởi filter |
| **Before Sunset** | v1 còn thực hiện đúng hợp đồng trong giai đoạn hỗ trợ |
| **After retirement** | 410/404 được áp đúng route; v2, health, docs không ảnh hưởng |
| **Unsafe migration** | Retry POST với idempotency key không tạo tác động trùng khi chạy song song |
| **OpenAPI drift** | `deprecated: true`, tài liệu lịch, response headers khớp runtime |

Có thể dùng **clock injection** trong code kiểm soát retirement để test **trước/sau mốc** mà không đổi đồng hồ máy CI. Tránh dùng `Thread.sleep` chờ đến ngày 01/01/2028. Ví dụ filter chỉ viết metadata, nên test 410 cần một **router/gateway policy riêng** trong môi trường thử nghiệm.

## 14. Đo adoption và quyết định go/no-go

Không nên chỉ nhìn ngày trên lịch. Trước cutover, đo:

| Metric | Ý nghĩa |
|---|---|
| **Request v1/v2 theo route/method/region** | Những luồng nào chưa chuyển? |
| **Client/partner/SDK version còn dùng v1** | Ai cần liên hệ, có release cycle dài? |
| **POST/PATCH/DELETE và volume giao dịch v1** | Có còn side effect nhạy cảm? |
| **4xx/5xx, latency, security failure trên v2** | Migration đã ổn định chưa? |
| **Sau retire: 410/404 v1 và support tickets** | Có client bị bỏ lại? |

Không dùng raw access token, idempotency key hoặc user ID làm metric labels. Thông tin nhận diện partner để hỗ trợ migration cần quyền truy cập/audit phù hợp.

**Go/no-go:** API owner, SRE, security và hỗ trợ khách hàng cùng kiểm tra OpenAPI/SDK/sandbox, số consumer chưa chuyển, test canary/rollback, dữ liệu cần retention và ngưỡng dừng rollout. Nếu lùi Sunset, cập nhật **headers + policy + docs + OpenAPI + gateway/CDN** đồng bộ, thông báo lại cho clients.

## 15. Bài tập: ngừng API thanh toán v1

Giả sử `POST /api/v1/payments` và `POST /api/v2/payments` có payload khác nhau: v1 dùng `amount` thập phân, v2 dùng `amountMinor` nguyên và OAuth scope mới. Ba partners vẫn dùng v1, một partner chỉ nâng cấp ứng dụng hai lần/năm. Nhóm công bố **Deprecation 01/01/2027**, **Sunset 01/01/2028 UTC**, nhưng mới chỉ thêm `deprecated: true` vào OpenAPI v1.

**Câu hỏi:** (1) Viết headers và link chuẩn; (2) vì sao OpenAPI chưa đủ; (3) nêu năm nội dung migration quan trọng; (4) Sunset có tự trả 410 không; (5) rủi ro redirect POST; (6) đề xuất test và metrics.

### Đáp án gợi ý

**1.** 
~~~http
Deprecation: @1798761600
Sunset: Sat, 01 Jan 2028 00:00:00 GMT
Link: <https://developer.example.test/migrations/payments-v1-to-v2>; rel="sunset"; type="text/html"
~~~

Có thể thêm `Link rel="deprecation"`. **2.** `deprecated: true` là metadata OAS, không phát header, không định nghĩa thời hạn hay tự tắt route. **3.** Phải có schema money/conversion, OAuth scope, status/Problem Details, mapping ID, idempotency/reconciliation, lịch và partner support. **4.** Không: tổ chức phải triển khai **410 Gone/404 theo policy** sau quyết định retire. **5.** Redirect không chuyển đổi schema/scope và có thể lộ token, gây double-charge khi timeout/retry. **6.** Test syntax/date, v1/v2 scope, 401/403, retirement behavior, POST idempotency và CDN; đo request theo client/version, unsafe operations, adoption, 410 và payment mismatch.

## 16. Phản mẫu và checklist triển khai

| Phản mẫu | Sửa đúng |
|---|---|
| `Sunset: 2028-01-01`, `Deprecation: true` | Dùng HTTP-date cho Sunset, Structured Field Date `@...` cho Deprecation |
| Sunset sớm hơn Deprecation | Validate thứ tự theo RFC 9745 trước deploy |
| Coi Sunset là lệnh tắt route | Tách header thông báo khỏi retirement policy/gateway |
| Chỉ gắn GET 200, không kiểm tra lỗi | Test methods/status, security và gateway |
| Chỉ đánh dấu `deprecated: true` | Bổ sung HTTP headers, policy/migration guide |
| Redirect POST v1 sang v2 | Chuyển client theo contract, bảo vệ credential/idempotency |
| Lùi lịch nhưng CDN còn header cũ | Đồng bộ thông báo và purge/revalidate |
| Ngừng route mà chưa biết client còn dùng | Metrics + owners + go/no-go |
| Xóa dữ liệu ngay lúc retire | Data retention và audit là quy trình riêng |

**Checklist:**

- [ ] Scope version/route/method rõ; `Sunset`/ `Deprecation` đúng format và thứ tự.
- [ ] Link `rel="sunset"`/`rel="deprecation"` trỏ tài liệu HTTPS có owner.
- [ ] Có ngày announce, deprecate, final notice, sunset, retirement và chính sách lùi lịch.
- [ ] Migration guide nêu URI/schema, auth, retry/idempotency, error contract, SDK/sandbox.
- [ ] Test Spring/gateway, HTTP status, CORS, CDN và v1/v2 không bị trộn header.
- [ ] Retirement 410/404 triển khai riêng, không ảnh hưởng v2.
- [ ] Theo dõi consumer v1, unsafe operations, quyết định go/no-go và hậu cutover.
- [ ] Không trộn retirement API với lưu giữ/xóa dữ liệu nghiệp vụ.

**Kết luận:** `Sunset` thông báo thời điểm resource **dự kiến** ngừng đáp ứng, còn `Deprecation` báo khi nào không nên phát triển phụ thuộc mới. Một retirement an toàn cần **header chuẩn, migration guide, đo adoption, kiểm thử và quyết định vận hành minh bạch**, thay vì chỉ thêm ngày vào HTTP response.

### Tài liệu nền

- **RFC 8594:** Sunset HTTP-date, scope, `sunset` link relation.
- **RFC 9745:** Deprecation Structured Field Date, `deprecation` link relation.
- **RFC 9110, RFC 8288, RFC 9457:** HTTP semantics, Web Linking, Problem Details.
- **OpenAPI Specification 3.1 / Spring Framework:** mô tả deprecated và triển khai kiểm thử.


