# Ví dụ lỗi, retry, cache và yêu cầu có điều kiện

## 1. Tài liệu API phải chỉ cho client cách xử lý khi mọi thứ không hoàn hảo

Một trang tài liệu REST API chỉ có **GET /orders → 200 OK** và **POST /orders → 201 Created** chưa đủ để một đối tác tích hợp an toàn. Trong thực tế, token hết hạn, hai nhân viên cùng sửa một đơn, gateway trả 429, mạng rớt sau khi server đã tạo order, hoặc cache giữ representation cũ. Nếu tài liệu không nói rõ **client phải gửi header nào, được retry trường hợp nào, xử lý 304/412 ra sao**, mỗi đội tự suy đoán và thường gây lỗi trùng đơn, ghi đè dữ liệu hoặc retry storm.

Bài thuộc chương **Tài liệu và trải nghiệm** của module **INTEGRATION_API_REST**: thiết kế REST dựa trên resource, URI, phương thức và mã trạng thái HTTP, hợp đồng dữ liệu, phân trang, cache, idempotency, OpenAPI, xác thực/phân quyền, lỗi và kiểm thử với Java/Spring. Trọng tâm là **viết các ví dụ tích hợp nhất quán, kiểm thử được**, không chỉ liệt kê định nghĩa từng mã HTTP.

Sau bài học, bạn sẽ biết cung cấp ví dụ về:

- **Lỗi** theo Problem Details, phân biệt validation, authentication, authorization, conflict, precondition và overload.
- **Retry** có giới hạn, backoff/jitter, Retry-After, deadline và idempotency key.
- **Cache** có Cache-Control, ETag, Vary, 304 Not Modified và yêu cầu bảo vệ dữ liệu người dùng.
- **Yêu cầu có điều kiện** với If-Match, If-None-Match, 412 và 428 để tránh ghi đè thay đổi của người khác.
- **OpenAPI, Java/Spring và contract tests** bảo đảm tài liệu không trôi khỏi hành vi thật của hệ thống.

## 2. Bối cảnh cố định để mọi ví dụ có thể kết nối với nhau

Giả sử API công khai tại **https://api.example.com**. Một đơn hàng thuộc tenant đã xác thực, có ID **11111111-1111-4111-8111-111111111111** và phiên bản tăng dần sau mỗi thay đổi. Để tài liệu dễ đọc, giả sử currency và giá trị tiền được mô tả theo đơn vị nhỏ nhất:

~~~json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "status": "CREATED",
  "totalMinorUnit": 125000,
  "currency": "VND",
  "version": 7
}
~~~

**Giả định thiết kế dùng xuyên bài:**

| Chủ đề | Quy ước minh họa | Trách nhiệm client |
| --- | --- | --- |
| Authentication | **Authorization: Bearer** access token với issuer/audience/scope được API chấp nhận. | Không gửi ID token thay access token; bảo vệ token, không log. |
| Authorization | Order được lọc theo actor/tenant trên server. | Không suy từ ID đoán quyền; 403/404 không được bypass. |
| Tạo order | **POST /api/orders**, hỗ trợ **Idempotency-Key**. | Giữ cùng key cho cùng một lệnh khi retry. |
| Đọc order | **GET /api/orders/{id}**, trả **ETag** cho representation. | Gửi If-None-Match khi revalidate cache. |
| Sửa order | **PATCH /api/orders/{id}**, yêu cầu **If-Match** để tránh lost update. | Đọc lại/giải quyết xung đột khi nhận 412. |
| Lỗi | **application/problem+json** theo RFC 9457. | Dùng status/type/code ổn định, không parse message tự do. |
| Quá tải | **429/503**, có thể kèm **Retry-After**. | Tôn trọng budget, backoff và chính sách retry. |

Các host, UUID, token và ETag đều là **dữ liệu ví dụ**. Một response từ API thật chỉ có các header/field đã được triển khai và định nghĩa trong contract. Không dùng địa chỉ hoặc secret production trong snippet có thể sao chép.

### 2.1. Bản đồ vòng đời một request

~~~mermaid
flowchart TD
    A["Client gửi method + URI + headers"] --> B{"Đã xác thực và có quyền?"}
    B -->|"401/403/404"| E["Problem Details / Bearer challenge"]
    B -->|"Có"| C{"Precondition / idempotency hợp lệ?"}
    C -->|"428/412/409"| E
    C -->|"Có"| D{"Xử lý nghiệp vụ và tải hệ thống"}
    D -->|"200/201/204"| S["Representation / ETag / Location"]
    D -->|"429/503"| E
    S --> R["Cache, lưu ETag; retry chỉ theo contract"]
    E --> R
~~~

Sơ đồ chỉ mang tính quyết định tích hợp; **thứ tự filter/thực thi thực tế** có thể khác nhau. Không suy rằng mọi lỗi 403 đều là lỗi quyền tài nguyên: khi API dùng cookie, 403 còn có thể do CSRF; ví dụ ở đây giả định Bearer header.

## 3. Ví dụ lỗi: Problem Details là contract, không phải stack trace

**Problem Details** theo RFC 9457 dùng media type **application/problem+json**, với các thành phần thông dụng **type, title, status, detail, instance**. Field **type** là định danh loại lỗi ổn định; **detail** là thông điệp hướng đến người đọc và có thể thay đổi/ngôn ngữ hóa, không phải khóa để client quyết định retry.

### 3.1. Validation error: 400 với thông tin đủ để sửa request

~~~http
POST /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <redacted>
Idempotency-Key: 893c5e76-9b44-4db0-81cc-8fcdba22e053
Content-Type: application/json
Accept: application/problem+json

{"customerId":"not-a-uuid","totalMinorUnit":-100}

HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-ID: req-demo-001

{
  "type": "https://api.example.com/problems/validation",
  "title": "Invalid request",
  "status": 400,
  "detail": "Một số trường dữ liệu không hợp lệ.",
  "instance": "/api/orders",
  "errors": [
    {"field": "customerId", "code": "invalid_format"},
    {"field": "totalMinorUnit", "code": "min_value"}
  ],
  "requestId": "req-demo-001"
}
~~~

**errors** và **requestId** là **extension fields** của ứng dụng, không phải trường bắt buộc của RFC 9457. **instance** nhận dạng sự cố, có thể là URI/relative reference theo cách triển khai; không chứa thông tin nhạy cảm. Với lỗi validation, client cần **sửa request**, không tự retry y nguyên. Nếu API chọn **422 Unprocessable Content** cho dữ liệu parse được nhưng vi phạm luật domain, phải định nghĩa ranh giới 400/422 nhất quán trong OpenAPI và ví dụ.

### 3.2. Lỗi xác thực và phân quyền: 401 khác 403

~~~http
GET /api/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Authorization: Bearer <expired-token>

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/authentication",
  "title": "Authentication failed",
  "status": 401
}
~~~

Khi không có credential, **WWW-Authenticate** có thể chỉ chứa challenge **Bearer** không kèm error; với token hết hạn/sai chữ ký/sai issuer hoặc audience, máy chủ có thể thêm **invalid_token** theo cấu hình. Client không nên retry 401 vô hạn: chỉ thử refresh access token **qua authorization server** nếu flow cho phép, với giới hạn một lần rồi yêu cầu xác thực lại. **Không gửi refresh token tới Orders API**.

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/forbidden",
  "title": "Access denied",
  "status": 403
}
~~~

**403** nói rằng danh tính đã có nhưng không được phép thực hiện thao tác. **404** có thể được dùng thay 403 khi chính sách yêu cầu không tiết lộ sự tồn tại của order thuộc tenant khác. Cả hai đều **không cho phép tự động retry với cùng credential**. Tránh đưa tên chủ đơn, customer email, role chi tiết hoặc dữ liệu từ tenant khác vào Problem Details.

### 3.3. Các loại lỗi thường bị trộn với nhau

| Status | Ngữ nghĩa | Hành động client mặc định |
| --- | --- | --- |
| **400** | JSON/path/query/header không hợp lệ theo contract. | Sửa request, không retry y nguyên. |
| **401** | Thiếu/không hợp lệ credential; có Bearer challenge khi áp dụng. | Xử lý auth flow có giới hạn. |
| **403** | Không đủ quyền; hoặc lỗi security như CSRF ở route cookie. | Không retry nguyên trạng. |
| **404** | Không tìm thấy/không được tiết lộ resource. | Kiểm ID/quyền, không suy có thể enumeration. |
| **409** | Xung đột domain, idempotency key đang xử lý hoặc cùng key khác payload tùy contract. | Giải quyết trạng thái; không retry mù. |
| **412** | Conditional request không thỏa **If-Match/If-None-Match**. | Lấy representation mới, quyết định merge/retry. |
| **428** | Server yêu cầu gửi precondition nhưng request không có. | Đọc ETag rồi gửi If-Match hợp lệ. |
| **429** | Quota/rate limit; có thể có Retry-After. | Backoff có jitter trong budget. |
| **500** | Lỗi server không phân loại được; outcome của write có thể chưa rõ. | Không mặc định retry POST với key mới. |
| **502/503/504** | Lỗi trung gian, dịch vụ tạm không sẵn sàng hoặc gateway timeout. | Có thể retry an toàn theo điều kiện, deadline và idempotency. |

**status** quyết định nhóm xử lý HTTP; **type** hoặc **code ứng dụng đã công bố** giúp client phân nhánh chi tiết. Một client không nên dựa vào chuỗi **detail** vì nó có thể thay đổi khi dịch thuật/sửa thông điệp.

### 3.4. Quy tắc an toàn cho ví dụ lỗi

Không ghi **Authorization, cookie, refresh token, password, SQL bind parameters, stack trace** vào response hoặc ví dụ tài liệu. Trả **X-Request-ID** hoặc trace correlation ID dạng an toàn để hỗ trợ đối soát; không đặt IDs có độ đa dạng cao vào metric labels. Nếu một lỗi không được công bố (exception DB, config), mapping thành Problem Details **5xx chung** và log nội bộ đã redact, không biến thành 400 để “trông thân thiện”.

## 4. Retry: hướng dẫn khi nào thử lại, và khi nào tuyệt đối không

**Retry** nghĩa là gửi lại một yêu cầu do lỗi hoặc thời gian chờ. Retry có thể cải thiện tính sẵn sàng khi lỗi ngắn hạn, nhưng cũng có thể làm **quá tải nặng hơn** hoặc thực thi một command hai lần. Tài liệu API phải nói rõ tính **safe/idempotent** của HTTP method, **idempotency contract** của endpoint, lỗi nào có thể retry và giới hạn thời gian/attempts.

### 4.1. Method semantics không giống việc mọi request đều an toàn retry

| Method | Tính chất HTTP | Ví dụ | Quy tắc retry |
| --- | --- | --- | --- |
| **GET/HEAD** | Safe và idempotent theo hợp đồng phương thức. | Đọc order, metadata. | Có thể retry lỗi tạm thời, vẫn giới hạn tổng tải/thời gian. |
| **PUT** | Idempotent về **tác động dự định** khi lặp cùng request. | Thay toàn bộ representation ở URI cố định. | Có thể retry theo contract và preconditions; response/status qua các lần không buộc giống hệt. |
| **DELETE** | Idempotent về tác động dự định. | Xóa một resource. | Retry có thể trả 204 lần đầu, 404 lần sau; không giả định response giống nhau. |
| **PATCH** | Không tự bảo đảm idempotent; phụ thuộc nội dung patch. | Set status=PAID vs increment amount. | Chỉ retry khi command được thiết kế idempotent hoặc có key/condition tương ứng. |
| **POST** | Không idempotent mặc định. | Tạo order/thu tiền. | **Không retry mù sau timeout**; dùng Idempotency-Key nếu API hỗ trợ. |

“Idempotent” là tác động dự định lên trạng thái hệ thống sau **n lần lặp** tương đương **một lần**, không có nghĩa HTTP response hay audit log phải giống hệt. Ví dụ một PUT theo version đã commit có thể trả **412** khi lặp với If-Match cũ; đây không phủ nhận mục tiêu ngăn ghi đè.

### 4.2. Retry-After với 429 và 503

~~~http
GET /api/orders?limit=50 HTTP/1.1
Authorization: Bearer <redacted>
Accept: application/json

HTTP/1.1 429 Too Many Requests
Retry-After: 5
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/rate-limited",
  "title": "Too many requests",
  "status": 429,
  "detail": "Giới hạn yêu cầu tạm thời đã đạt."
}
~~~

**Retry-After: 5** nghĩa là **5 giây**, không phải mili giây. Header cũng có thể chứa **HTTP-date**; client phải parse cả hai dạng theo contract. Với ngày HTTP, đồng hồ client/server có thể lệch; đừng tạo lịch retry vô hạn từ timestamp lỗi. Nếu server có các header mô tả quota/rate limit bổ sung, document rõ **scope, cửa sổ tính, ý nghĩa và tương tác với Retry-After**, không suy đoán từ tên header tự chế.

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 10
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/temporarily-unavailable",
  "title": "Service temporarily unavailable",
  "status": 503
}
~~~

**503** báo dịch vụ tạm không có khả năng phục vụ; khác **429** (giới hạn/quota), nhưng cả hai đều có thể yêu cầu chờ. **502 Bad Gateway**, **504 Gateway Timeout** hoặc network timeout cũng có thể là transient, tuy nhiên **kết quả một write có thể đã được commit**. Không đồng nhất 504 với “server chắc chắn chưa làm gì”.

### 4.3. Thuật toán retry có trách nhiệm

~~~text
Thử tối đa 3 attempts cho một logical request:
  - Chỉ retry lỗi được endpoint công bố là transient.
  - Không vượt deadline tổng của user/request.
  - Nếu có Retry-After hợp lệ, dùng nó như thời gian chờ tối thiểu
    phù hợp budget; nếu thời gian chờ vượt budget, dừng.
  - Nếu không có Retry-After, exponential backoff + jitter
    và giới hạn max delay.
  - Giữ nguyên idempotency key và payload cho cùng một POST logic.
  - Không retry validation/auth/permission/precondition conflict
    nếu không có thay đổi đầu vào/trạng thái.
~~~

Ví dụ giới hạn **base 200 ms, max 2 s, tối đa 3 attempts** chỉ có ý nghĩa khi kết hợp **total deadline** và SLO tương ứng. Nếu request gần hết deadline, thêm một retry tốn connection/queue và có thể tạo retry storm. Một cách thực hiện jitter là rút ngẫu nhiên trong khoảng từ 0 đến **min(maxDelay, base × 2^attempt)**, giới hạn số attempts. Không để SDK và API gateway **cùng retry 3 lần** mà không phối hợp; fan-out nhiều tầng có thể khuếch đại mạnh tải lên backend.

**Không tự động retry:**

- **400/401/403/404/412/428** nếu không có thay đổi ngữ nghĩa: sửa input, xác thực, quyền, precondition hoặc quyết định nghiệp vụ.
- **409** nếu là collision/version conflict không tự giải quyết được; riêng trạng thái “idempotency key đang xử lý” có thể được công bố là retryable sau chờ.
- **POST/PATCH có side effect** khi không có idempotency/confirmation hợp lệ; nếu response mất, client không biết chắc đã commit hay chưa.

### 4.4. Java HttpClient: ví dụ retry GET có deadline

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;

public final class OrdersReadClient {
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();

    public String getOrder(URI uri, String accessToken)
            throws IOException, InterruptedException {
        int maxAttempts = 3;
        long start = System.nanoTime();
        long budgetNanos = Duration.ofSeconds(8).toNanos();

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            long left = budgetNanos - (System.nanoTime() - start);
            if (left <= 0) throw new IOException("Request deadline exceeded");

            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofNanos(left))
                    .header("Authorization", "Bearer " + accessToken)
                    .header("Accept", "application/json")
                    .GET().build();
            try {
                HttpResponse<String> response = client.send(
                        request, HttpResponse.BodyHandlers.ofString());
                if (response.statusCode() == 200) return response.body();

                // 429 và 503 có thể transient; khác lỗi 4xx nói chung.
                boolean transientStatus = response.statusCode() == 429
                        || response.statusCode() == 503;
                if (!transientStatus || attempt == maxAttempts)
                    throw new IOException(
                            "GET failed: HTTP " + response.statusCode());
            } catch (java.net.http.HttpTimeoutException ex) {
                if (attempt == maxAttempts) throw ex;
            }

            long delayMillis = Math.min(200L << (attempt - 1), 1000L);
            long delayNanos = Duration.ofMillis(delayMillis).toNanos();
            if (budgetNanos - (System.nanoTime() - start) <= delayNanos)
                throw new IOException("No time left to retry");
            Thread.sleep(delayMillis); // Đơn giản hóa: chưa có jitter.
        }
        throw new IOException("Retry attempts exhausted");
    }
}
~~~

**Giới hạn rõ ràng của snippet:** đây là mẫu minh họa cách giới hạn attempt và deadline, **chưa đọc Retry-After**, chưa thêm jitter, chưa kiểm content-type/response size, chưa thực thi circuit breaker, chưa xử lý 502/504 tùy contract và chưa phân loại lỗi I/O ngoài HttpTimeoutException. Trong SDK production, viết một retry policy riêng, parse Retry-After delta-seconds/HTTP-date, honor cancellation/interrupt, kiểm URI đích được allowlist và tránh tạo HttpClient mỗi request. Không dùng mã này nguyên trạng cho POST có side effect.

## 5. Idempotency-Key: ví dụ bắt buộc với POST có thể bị gửi lại

Mạng có thể rớt **sau khi server commit nhưng trước khi client nhận 201**. Không có cơ chế dedupe, client retry POST có thể tạo **hai đơn**. Một contract ổn định có thể dùng **Idempotency-Key** do client sinh cho **một logical create command**:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <redacted>
Content-Type: application/json
Idempotency-Key: "create-order-4e519c0e-6d85-4451-86ce-a0a6696324e1"

{"customerId":"22222222-2222-4222-8222-222222222222","totalMinorUnit":125000}

HTTP/1.1 201 Created
Location: /api/orders/11111111-1111-4111-8111-111111111111
Content-Type: application/json
Cache-Control: no-store

{
  "id":"11111111-1111-4111-8111-111111111111",
  "status":"CREATED",
  "version":7
}
~~~

**Cú pháp Idempotency-Key trong ví dụ** là **Structured Field String** được bao bằng dấu nháy kép theo Internet-Draft/chuẩn mà API lựa chọn. Nhiều hệ thống hoặc SDK có hợp đồng riêng về giá trị header này; tài liệu thực tế phải cố định **syntax, độ dài, allowed characters, scope và TTL** thay vì giả định mọi đối tác hiểu một format. Ví dụ client giữ nguyên key, **không tạo key mới sau network timeout**.

### 5.1. Cùng key, cùng payload; cùng key, payload khác

Giả sử lần đầu đã commit:

~~~http
POST /api/orders HTTP/1.1
Idempotency-Key: "create-order-4e519c0e-6d85-4451-86ce-a0a6696324e1"
Content-Type: application/json

{"customerId":"22222222-2222-4222-8222-222222222222","totalMinorUnit":125000}

HTTP/1.1 201 Created
Location: /api/orders/11111111-1111-4111-8111-111111111111
Content-Type: application/json
Cache-Control: no-store

{"id":"11111111-1111-4111-8111-111111111111","status":"CREATED","version":7}
~~~

Trong ví dụ này API chọn **replay cùng kết quả 201, Location và body** khi duplicate đã hoàn tất. API khác có thể quy định trả 200 hoặc trường riêng, nhưng **phải công bố và kiểm thử**. Nếu key đã được dùng với **payload khác**, trả **409 Conflict** theo contract:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type":"https://api.example.com/problems/idempotency-key-conflict",
  "title":"Idempotency key already used with different request",
  "status":409
}
~~~

Nếu hai request **cùng key** tới đồng thời mà request đầu **chưa hoàn tất**, API phải quy định rõ cách xử lý, chẳng hạn **409 in_progress** và **Retry-After**, hoặc cơ chế theo dõi lệnh phù hợp. Tránh làm client tin rằng 409 luôn có thể retry; **type/code** mới quyết định. Không coi **idempotency key** là yêu cầu có điều kiện If-Match: key chống **lặp cùng command**, còn If-Match chống **ghi đè khi resource đã đổi**.

### 5.2. Ràng buộc implement để tài liệu đáng tin

Server cần lưu kết quả dedupe theo **tenant/principal hoặc namespace hợp lý + method + endpoint/operation + key**, kèm fingerprint của những tham số ảnh hưởng hành vi. **Claim key, thực thi command và lưu trạng thái/kết quả** phải có ranh giới transaction/commit an toàn. Nếu kết quả đã được cache nhưng business transaction rollback, sẽ phát sinh “success giả”; nếu business commit mà dedupe record không durable, retry có thể tạo resource thứ hai.

Định nghĩa **TTL/retention** của key, giới hạn kích thước/entropy, chính sách key reuse sau expiry và cách xử lý request đang xử lý/không rõ kết quả. Không log key tùy ý nếu chứa PII; không cho caller của tenant B lấy response đã lưu của tenant A dù đoán được key. Idempotency-key bản thân **không thay authentication, authorization, unique constraints hoặc transaction**.

## 6. Tài liệu retry phải cho client quyết định trên cả status và outcome

Đề xuất bảng hành động có thể đưa ngay vào SDK:

| Kết quả | Safe GET | POST có Idempotency-Key được hỗ trợ | POST không có key |
| --- | --- | --- | --- |
| **200/201/204** | Hoàn tất. | Hoàn tất, lưu resource ID/Location. | Hoàn tất. |
| **304** sau conditional GET | Dùng body đã cache hợp lệ. | Không áp dụng cho POST thường. | Không áp dụng. |
| **400/401/403/404** | Không retry y nguyên. | Không retry y nguyên, xử lý input/auth/permission. | Không retry y nguyên. |
| **409/412/428** | Xử lý contract cụ thể. | Đọc trạng thái, sửa precondition hoặc key conflict. | Không gửi lại mù quáng. |
| **429/503 + Retry-After** | Có thể chờ rồi retry với budget. | Có thể retry **cùng key + payload**, theo contract. | Cần xác minh outcome trước khi lặp. |
| **Timeout/mất kết nối sau gửi** | Retry có giới hạn. | Retry **cùng key** hoặc tra cứu operation/resource. | Outcome không rõ, không tạo key mới chỉ để thử lại. |

**Điểm cần ghi ngay dưới bảng trong tài liệu:** status code không mô tả đầy đủ tác động của write khi response bị mất; client phải dựa vào tính idempotent và cơ chế tra cứu/đối soát. Nếu gateway thực hiện retry thay client, cần một **policy chung** để không khuếch đại attempts và không làm lộ access token qua redirect.

## 7. Cache và ETag: đọc lại mà không tải body không cần thiết

**Cache** chỉ hữu ích khi client hiểu **representation nào được lưu, còn mới bao lâu và khi nào phải revalidate**. Tài liệu nên có **Cache-Control**, **ETag**, **Vary** và response **304**, không chỉ ghi “API hỗ trợ cache”.

### 7.1. Lần GET đầu: lưu body cùng validator

~~~http
GET /api/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-cache
ETag: "order-11111111-v7-json"
Vary: Accept, Accept-Encoding

{
  "id": "11111111-1111-4111-8111-111111111111",
  "status": "CREATED",
  "totalMinorUnit": 125000,
  "currency": "VND",
  "version": 7
}
~~~

**private** chỉ cho phép cache riêng tư (không cho shared cache lưu); **no-cache** trong HTTP **không nghĩa là “cấm lưu”**, mà yêu cầu **revalidation trước khi dùng lại**. Với dữ liệu nhạy cảm không được lưu, dùng **Cache-Control: no-store**. Nếu dùng no-store, không nên đồng thời quảng cáo khả năng tái sử dụng cached body cho chính response đó.

**ETag** là validator của **representation cụ thể**, không đơn thuần là version row DB. Ví dụ ETag ở trên là token minh họa: để là **strong ETag**, server phải bảo đảm cùng tag chỉ dùng cho representation đáp ứng yêu cầu strong comparison; thay đổi byte của JSON, encoding hoặc variant có thể cần ETag khác. Không dùng tag mạnh của JSON cho XML hoặc response có field bị ẩn/hiện khác nhau.

### 7.2. Lần GET tiếp: revalidate với If-None-Match

~~~http
GET /api/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Accept: application/json
If-None-Match: "order-11111111-v7-json"

HTTP/1.1 304 Not Modified
ETag: "order-11111111-v7-json"
Cache-Control: private, no-cache
Vary: Accept, Accept-Encoding
~~~

**304 không có message body**. Cache/client được dùng **body đã lưu tương ứng** và cập nhật metadata theo quy tắc HTTP caching. **Validator khớp không bỏ qua authentication/tenant/object authorization**: không trả 304 cho actor đã mất quyền chỉ vì họ giữ ETag cũ.

Nếu order thay đổi, trả **200 với body và ETag mới**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-11111111-v8-json"
Cache-Control: private, no-cache

{
  "id": "11111111-1111-4111-8111-111111111111",
  "status": "PAID",
  "totalMinorUnit": 125000,
  "currency": "VND",
  "version": 8
}
~~~

**If-None-Match** dùng **weak comparison** theo GET/HEAD revalidation; weak validator **W/"..."** có thể phù hợp với caching nếu được định nghĩa đúng. **If-Match** cho cập nhật dùng **strong comparison** (phần 8): weak ETag **không thỏa** If-Match. Không đánh đồng hai cơ chế.

### 7.3. Cache-Control và Vary thuộc về hợp đồng

| Header/mẫu | Ý nghĩa | Lỗi thường gặp |
| --- | --- | --- |
| **Cache-Control: no-store** | Không lưu response trong cache theo quy tắc HTTP. | Gọi đây là “cache trong 5 phút”. |
| **Cache-Control: private, no-cache** | Cache riêng có thể lưu, phải revalidate trước khi dùng. | Nghĩ no-cache đồng nghĩa không lưu. |
| **Cache-Control: private, max-age=60** | Cache riêng dùng lại tối đa 60 giây khi còn fresh theo policy. | Hứa read-your-write tuyệt đối trong cửa sổ stale. |
| **ETag / If-None-Match** | Revalidate body đã lưu. | Trả 304 từ Redis stale, không so với nguồn đúng. |
| **Vary: Accept, Accept-Encoding** | Phân biệt các headers ảnh hưởng representation. | Trộn JSON/XML/encoded variants. |
| **Authorization + private** | Tránh shared caching nhầm dữ liệu riêng tư. | Public CDN cache trả dữ liệu tenant khác. |

**Vary: Authorization** không thay thế thiết kế authorization/cache scope. Nếu body thay theo role, locale, feature flag hay tenant, cache key/ETag phải tính những variants ấy; không trả body của user A cho B. Với GET collection có filter/sort/pagination, query params là phần cache key và representation: không tái sử dụng ETag GET một order cho mọi trang danh sách.

### 7.4. Redis, CDN và HTTP cache là những tầng khác nhau

Redis cache-aside, CDN shared cache, browser cache và HTTP conditional requests có trách nhiệm khác nhau. Redis entry stale hoặc replica DB đang lag **không chứng minh representation chưa đổi**. Nếu API hứa read-your-writes sau PATCH, GET cần nguồn đúng version hoặc đọc primary; **ETag chỉ tốt bằng dữ liệu dùng để tính nó**. Với thông tin đơn hàng riêng tư, dùng **private** hoặc **no-store** và kiểm đúng tenant/representation thay vì tối ưu public CDN cache trước khi có security review.

## 8. If-Match: ví dụ ngăn hai client ghi đè thay đổi của nhau

Hai nhân viên cùng đọc order v7. A cập nhật lên v8; B vẫn giữ v7 rồi PATCH. Nếu chỉ ghi theo ID, B có thể âm thầm ghi đè A. **Conditional requests** cho phép server kiểm version trước khi thực hiện lệnh.

### 8.1. PATCH với strong ETag hiện tại

~~~http
PATCH /api/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Content-Type: application/merge-patch+json
If-Match: "order-11111111-v7-json"

{"status":"PAID"}

HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-11111111-v8-json"
Cache-Control: private, no-store

{
  "id": "11111111-1111-4111-8111-111111111111",
  "status": "PAID",
  "totalMinorUnit": 125000,
  "currency": "VND",
  "version": 8
}
~~~

Đây là **JSON Merge Patch** theo **application/merge-patch+json**; server phải định nghĩa rõ trường có thể patch, state transitions và cách xử lý null. Không cho caller thay đổi tenantId, ownerId hoặc price do DB tin cậy chỉ vì payload là JSON. Một strong ETag đúng phải đại diện **selected representation** của order, không được tái sử dụng qua representations khác nhau có bytes khác.

### 8.2. ETag cũ → 412 Precondition Failed

~~~http
PATCH /api/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/merge-patch+json
If-Match: "order-11111111-v7-json"

{"status":"CANCELLED"}

HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/precondition-failed",
  "title": "Resource changed since last read",
  "status": 412,
  "detail": "Hãy tải phiên bản mới và quyết định cập nhật lại."
}
~~~

**412** nói precondition HTTP không thỏa: **không thực thi PATCH**. Client GET lại representation, hiển thị xung đột/merge hoặc yêu cầu người dùng quyết định. **Không tự thay If-Match bằng ETag mới rồi retry cùng payload** nếu có rủi ro mất cập nhật. **409** dành cho xung đột nghiệp vụ riêng, như trạng thái PAID không thể CANCELLED theo policy; không thay 412 cho mismatched If-Match chỉ vì hai lỗi đều là conflict.

### 8.3. Thiếu If-Match → 428 Precondition Required

~~~http
PATCH /api/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/merge-patch+json

{"status":"PAID"}

HTTP/1.1 428 Precondition Required
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type":"https://api.example.com/problems/precondition-required",
  "title":"If-Match is required",
  "status":428
}
~~~

**428** là chính sách API bắt buộc điều kiện; client phải lấy ETag mới rồi gửi If-Match. Có điều kiện nhưng **sai** → **412**, không phải 428. Ghi yêu cầu If-Match trong OpenAPI, tài liệu từng operation và SDK, thay vì chỉ trả lỗi lúc runtime.

### 8.4. Phải kiểm precondition và ghi DB một cách nguyên tử

Sai về concurrency:

~~~text
GET order version=7
if (ifMatch == "v7") {
    // Transaction khác đã commit version=8 trong lúc này.
    UPDATE orders SET status='PAID' WHERE id=42;
}
~~~

Đúng về nguyên tắc là **compare-and-swap trong transaction**:

~~~sql
UPDATE orders
SET status = :status, version = version + 1
WHERE id = :id
  AND tenant_id = :trustedTenant
  AND version = :expectedVersion;
-- affected_rows = 0: không thay đổi resource;
-- phân loại không tồn tại/không có quyền/version sai theo policy.
~~~

Controller cần so sánh **strong ETag** của selected representation rồi ánh xạ tới expectedVersion; DB cập nhật theo version và tenant một cách atomic. Không xử lý If-Match bằng cách bỏ hai dấu nháy rồi tin giá trị: HTTP hỗ trợ **entity-tag list, wildcard, weak/strong semantics**; dùng parser và precondition evaluator được kiểm thử. **If-Match: \*** đòi resource tồn tại, không chứng minh version của client còn mới. Nếu API còn policy chống lost update, đừng dùng wildcard để bỏ qua mọi kiểm soát concurrency.

### 8.5. Tạo tài nguyên “chỉ nếu chưa tồn tại”

Với **PUT** có ID do client chọn, **If-None-Match: \*** có thể diễn đạt **create-if-absent**: resource đã tồn tại → **412**. Đây là cơ chế khác Idempotency-Key của POST. Client chỉ được chọn ID và truy cập resource nếu API cấp quyền; URI theo tenant cũng phải được kiểm tra. Với **If-Unmodified-Since**, tính chính xác phụ thuộc độ phân giải timestamp; khi có strong ETag, ưu tiên nó cho concurrency nhạy cảm. Các preconditions phải được đánh giá theo thứ tự HTTP quy định.

## 9. Chọn ETag, Idempotency-Key hay cả hai?

| Mục tiêu | Cơ chế phù hợp | Ví dụ |
| --- | --- | --- |
| Giảm dữ liệu GET không đổi | **ETag + If-None-Match → 304** | GET cùng order sau 5 giây. |
| Tránh lost update | **Strong ETag + If-Match → 200/412/428** | Hai nhân viên PATCH cùng order. |
| Chỉ tạo resource nếu URI chưa tồn tại | **If-None-Match: \*** trên PUT/operation tương ứng | PUT order ID do client chọn. |
| Tránh POST được thực thi hai lần khi mất response | **Idempotency-Key** có dedupe bền vững | POST tạo order sau network timeout. |
| Đợi hệ thống bớt quá tải | **Retry-After + backoff/jitter + deadline** | GET nhận 429 hoặc 503. |

**Không nhầm** HTTP ETag với versioning event/outbox, không coi retry key là quyền truy cập và không lấy header client làm thay thế business authorization. Chúng giải quyết các failure modes khác nhau. Một API có thể đồng thời dùng **Idempotency-Key** để dedupe command và **If-Match** để kiểm version của resource mà command tác động, với thứ tự kiểm tra và replay behavior được tài liệu hóa rõ.

## 10. Java/Spring: minh họa giữ contract trong controller và domain

**Tài liệu tốt không bắt client đoán ETag được tính thế nào.** Controller đọc resource đã được phân quyền, xử lý điều kiện HTTP; service cập nhật version và business rules **trong transaction**. Ví dụ Spring Boot 3 / Spring MVC tập trung vào sự phân chia trách nhiệm; repository và parser HTTP entity-tags là thành phần cần triển khai riêng.

### 10.1. GET và conditional GET

~~~java
import java.util.UUID;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.context.request.WebRequest;
import org.springframework.security.core.Authentication;

record OrderView(UUID id, String status, long version) {}
record OrderSnapshot(OrderView view, String strongEtag,
                     long version) {}

interface OrderApplicationService {
    OrderSnapshot readAuthorized(Authentication actor, UUID id);
    OrderSnapshot changeAuthorized(
            Authentication actor, UUID id,
            long expectedVersion, String newStatus);
}

@RestController
@RequestMapping("/api/orders")
class OrderHttpController {
    private final OrderApplicationService service;
    private final EntityTagPolicy tagPolicy;

    OrderHttpController(OrderApplicationService service,
                        EntityTagPolicy tagPolicy) {
        this.service = service;
        this.tagPolicy = tagPolicy;
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderView> get(
            @PathVariable UUID id, Authentication actor,
            WebRequest request) {
        // Authorize trước khi trả 200 hoặc 304.
        OrderSnapshot snapshot = service.readAuthorized(actor, id);
        String etag = snapshot.strongEtag();
        CacheControl cache = CacheControl.noCache().cachePrivate();

        if (request.checkNotModified(etag)) {
            return ResponseEntity.status(HttpStatus.NOT_MODIFIED)
                    .eTag(etag)
                    .cacheControl(cache)
                    .build();
        }
        return ResponseEntity.ok()
                .eTag(etag)
                .cacheControl(cache)
                .body(snapshot.view());
    }

    record StatusPatch(String status) {}

    @PatchMapping(path = "/{id}",
            consumes = "application/merge-patch+json")
    ResponseEntity<OrderView> patch(
            @PathVariable UUID id,
            @RequestHeader(name = HttpHeaders.IF_MATCH,
                    required = false) String ifMatch,
            @RequestBody StatusPatch patch,
            Authentication actor) {
        if (ifMatch == null) throw new MissingPreconditionException();

        OrderSnapshot before = service.readAuthorized(actor, id);
        if (!tagPolicy.strongIfMatch(ifMatch, before.strongEtag()))
            throw new StalePreconditionException();

        // BẮT BUỘC CAS nguyên tử trên expectedVersion trong DB:
        // nếu race sau bước đọc, service cũng phải từ chối.
        OrderSnapshot after = service.changeAuthorized(
                actor, id, before.version(), patch.status());
        return ResponseEntity.ok()
                .eTag(after.strongEtag())
                .cacheControl(CacheControl.noStore())
                .body(after.view());
    }
}

interface EntityTagPolicy {
    // Parser đúng RFC: entity-tag list, wildcard, weak/strong comparison.
    boolean strongIfMatch(String headerValue, String currentStrongTag);
}

class MissingPreconditionException extends RuntimeException {}
class StalePreconditionException extends RuntimeException {}
~~~

**Đưa vào production:** **EntityTagPolicy** phải parse If-Match theo HTTP, versioning phản ánh đúng selected representation; status patch dùng enum/Bean Validation + business transition checks. Service kiểm tenant/object authorization, transaction và CAS atomic. **WebRequest.checkNotModified** trên GET hỗ trợ đánh giá conditional requests trong Spring, nhưng phải test **Vary/Content-Encoding/representation variants** và bảo đảm validator phản ánh version thật, không phải stale Redis.

**Không đặt query thay đổi trạng thái trong GET**; 304 chỉ dành cho conditional retrieval. Khi controller nhận If-Match đúng nhưng có concurrent writer giữa read và update, service **bắt buộc** từ chối từ kết quả CAS = 0, nếu không bước check riêng ở controller vẫn tạo race.

### 10.2. ProblemDetail handlers: cùng ngữ nghĩa, cùng response

~~~java
import java.net.URI;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestControllerAdvice
class OrdersProblemAdvice {
    @ExceptionHandler(MissingPreconditionException.class)
    ResponseEntity<ProblemDetail> missing(
            MissingPreconditionException ex) {
        return problem(HttpStatus.PRECONDITION_REQUIRED,
                "precondition-required", "If-Match is required");
    }

    @ExceptionHandler(StalePreconditionException.class)
    ResponseEntity<ProblemDetail> stale(
            StalePreconditionException ex) {
        return problem(HttpStatus.PRECONDITION_FAILED,
                "precondition-failed", "Resource version changed");
    }

    private ResponseEntity<ProblemDetail> problem(
            HttpStatus status, String code, String title) {
        ProblemDetail detail = ProblemDetail.forStatus(status);
        detail.setTitle(title);
        detail.setType(URI.create(
                "https://api.example.com/problems/" + code));
        return ResponseEntity.status(status)
                .cacheControl(CacheControl.noStore())
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(detail);
    }
}
~~~

Advice chỉ xử lý **428/412**, không thay handlers 400/401/403/404/409/429/503 của API. **401/403 từ Spring Security** thường được xử lý qua authentication entry point/AccessDeniedHandler, không tự động đi vào RestControllerAdvice. Contract tests phải kiểm cả hai đường. Nếu API dùng canonical host khác example.com, lấy **Problem type URI** từ cấu hình tin cậy, không suy ra Host/X-Forwarded-Host thô.

### 10.3. Logic dedupe cho POST: transaction, không chỉ cache RAM

~~~text
POST /api/orders với Idempotency-Key:
  1. Authenticate, kiểm scope và tenant.
  2. Validate key/payload, tính fingerprint ổn định.
  3. Atomic claim (tenant + operation + key) trong durable store.
  4. Key hoàn tất và fingerprint trùng: replay documented result.
  5. Key trùng nhưng fingerprint khác: 409.
  6. Key in-progress: 409/Retry-After hoặc status theo contract.
  7. Key mới: tạo order trong transaction, lưu outcome dedupe.
  8. Commit; trả 201 với Location, body, cache policy.
~~~

Trong cùng DB, claim/dedupe record và order cần **unique constraint + transaction/race policy**; chỉ một concurrent request được thực hiện command. Nếu không thể atomic giữa command và dedupe store, dùng durable state machine/outbox/reconciliation để tránh kết quả giả hoặc trùng. **synchronized trong một JVM không đủ** khi có nhiều replicas.

## 11. OpenAPI 3.1: ví dụ phải nằm trong contract máy đọc được

Không chỉ có prose trên wiki: **OpenAPI** chỉ ra request/response headers, media types, example values và status codes để SDK, mock server, contract tests đọc được. Mảnh dưới minh họa hai operations quan trọng; schema production cần mở rộng đầy đủ.

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
servers:
  - url: https://api.example.com
security:
  - bearerAuth: []
paths:
  /api/orders/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    get:
      operationId: getOrder
      parameters:
        - name: If-None-Match
          in: header
          required: false
          schema: { type: string }
          description: Entity-tag từ GET trước để revalidate.
      responses:
        '200':
          description: Representation hiện tại
          headers:
            ETag:
              schema: { type: string }
            Cache-Control:
              schema: { type: string }
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
              example:
                id: 11111111-1111-4111-8111-111111111111
                status: CREATED
                version: 7
        '304':
          description: Không đổi; không có response body
          headers:
            ETag:
              schema: { type: string }
        '401':
          $ref: '#/components/responses/Unauthorized'
        '403':
          $ref: '#/components/responses/Forbidden'
        '404':
          $ref: '#/components/responses/NotFound'
    patch:
      operationId: updateOrderStatus
      parameters:
        - name: If-Match
          in: header
          required: true
          schema: { type: string }
          description: Strong ETag của selected representation.
      requestBody:
        required: true
        content:
          application/merge-patch+json:
            schema:
              type: object
              properties:
                status:
                  type: string
                  enum: [CREATED, PAID, CANCELLED]
      responses:
        '200':
          description: Cập nhật thành công
          headers:
            ETag:
              schema: { type: string }
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '412':
          $ref: '#/components/responses/PreconditionFailed'
        '428':
          $ref: '#/components/responses/PreconditionRequired'
        '403':
          $ref: '#/components/responses/Forbidden'
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
  schemas:
    Order:
      type: object
      required: [id, status, version]
      properties:
        id: { type: string, format: uuid }
        status: { type: string }
        version: { type: integer, format: int64 }
    Problem:
      type: object
      properties:
        type: { type: string, format: uri-reference }
        title: { type: string }
        status: { type: integer }
        detail: { type: string }
  responses:
    Unauthorized:
      description: Access token thiếu hoặc không hợp lệ
      headers:
        WWW-Authenticate:
          schema: { type: string }
    Forbidden:
      description: Không có quyền
    NotFound:
      description: Resource không tồn tại hoặc không được tiết lộ
    PreconditionFailed:
      description: If-Match không khớp
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
    PreconditionRequired:
      description: Thiếu If-Match
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
~~~

**Đây chưa phải spec đầy đủ:** cần thêm POST với Idempotency-Key/201/409/429/503, requestBody/errors/examples, patch transitions, quyền, 400/415 và cache headers của 304. OpenAPI mô tả **bề mặt hợp đồng**, không tự thực thi strong ETag validation, CAS hoặc dedupe. **Không khai báo required If-Match rồi để server âm thầm bỏ qua**; phải kiểm bằng contract tests.

### 11.1. Kiểm tính nhất quán giữa prose và OpenAPI

| Tài liệu cho developer | Vị trí trong OpenAPI | Cần test |
| --- | --- | --- |
| Gửi **If-Match** trên PATCH. | Parameter in header, required. | Thiếu → 428, stale → 412. |
| GET trả ETag/Cache-Control. | Response headers 200/304. | Validator, cache directive và 304 không body. |
| POST hỗ trợ key chống duplicate. | Request header + status/response examples. | Cùng key/payload không tạo thêm resource. |
| Validation lỗi có Problem Details. | Response content application/problem+json, example. | Content-Type, type, status, extension contract. |
| Rate limit có Retry-After. | Header trên 429/503 tương ứng. | Delta-seconds/HTTP-date và status chính xác. |
| 401 yêu cầu auth challenge. | Response header WWW-Authenticate. | Thiếu/expired token → 401, scope thiếu → 403. |

Không gắn một example GET trả status PAID trong schema mà response thực tế trả CREATED nếu fixture chưa cập nhật; dùng **deterministic fixtures** và kiểm ví dụ trên môi trường test. Khi version API thay đổi, update đồng thời docs, SDK, examples và tests; không để snippets cũ dẫn người tích hợp tới lỗi security mới.

## 12. Contract tests: chứng minh ví dụ tài liệu đúng với HTTP thật

**Đọc được OpenAPI không chứng minh runtime thực thi đúng.** Một regression suite nên gửi chính các request đã mô tả, kiểm **status, headers, media type, body, ETag và state trong DB**. Đối với negative tests, còn phải chứng minh side effects không xảy ra.

### 12.1. Ma trận tối thiểu

| Mã | Bối cảnh | Assert quan trọng |
| --- | --- | --- |
| D01 | POST thiếu field / kiểu sai | **400**, Problem Details đúng type, không tạo order. |
| D02 | Access token hết hạn/sai aud/sai signature | **401**, Bearer challenge; không trả dữ liệu. |
| D03 | Token hợp lệ nhưng không có quyền tenant | **403/404** theo policy, không lộ resource. |
| D04 | GET không If-None-Match | **200** + body + ETag, Cache-Control, Vary phù hợp. |
| D05 | GET If-None-Match khớp | **304 không body**, ETag/cache metadata nhất quán. |
| D06 | GET If-None-Match cũ | **200 với body/tag mới**, không stale 304. |
| D07 | PATCH không If-Match | **428**, không thay DB. |
| D08 | PATCH với If-Match stale/weak không hợp lệ | **412** hoặc lỗi parser phù hợp, không thay DB. |
| D09 | Hai PATCH đồng thời cùng ETag | Chỉ **một** CAS thành công; yêu cầu còn lại 412. |
| D10 | POST cùng key/payload hai lần | Chỉ **một resource**, replay đúng response đã công bố. |
| D11 | POST cùng key nhưng payload khác | **409** có type ổn định; không thay dữ liệu đã tạo. |
| D12 | Mất ACK sau commit, retry cùng key | Không tạo order thứ hai, kết quả có thể đối soát. |
| D13 | Rate limit/overload | **429/503**, Retry-After hợp đồng, không lộ chi tiết hạ tầng. |
| D14 | Client thực hiện retry khi hết deadline | Dừng sau budget; không tạo vòng lặp request. |
| D15 | Cache/response theo hai tenants | Không trả body/304 validator của tenant khác. |

### 12.2. MockMvc: kiểm conditional GET và thiếu precondition

Giả sử **Spring Boot, Spring Security Test** và test DB đã chuẩn bị order v7 thuộc actor được cấp quyền. Ví dụ minh họa:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrderConditionalIT {
    private static final String ORDER_ID =
            "11111111-1111-4111-8111-111111111111";

    @Autowired MockMvc mvc;

    @Test
    void conditionalGetReturns304WithoutBody() throws Exception {
        String etag = mvc.perform(get("/api/orders/{id}", ORDER_ID)
                    .with(jwt()))
                .andExpect(status().isOk())
                .andExpect(header().exists(HttpHeaders.ETAG))
                .andReturn().getResponse().getHeader(HttpHeaders.ETAG);
        assertNotNull(etag);

        mvc.perform(get("/api/orders/{id}", ORDER_ID)
                    .with(jwt())
                    .header(HttpHeaders.IF_NONE_MATCH, etag))
                .andExpect(status().isNotModified())
                .andExpect(content().string(""));
    }

    @Test
    void patchWithoutIfMatchReturns428() throws Exception {
        mvc.perform(patch("/api/orders/{id}", ORDER_ID)
                    .with(jwt())
                    .contentType(MediaType.valueOf(
                            "application/merge-patch+json"))
                    .content("{\"status\":\"PAID\"}"))
                .andExpect(status().isPreconditionRequired());
    }
}
~~~

**Cần chuẩn bị fixture trước khi chạy:** principal của **jwt()** phải được service ánh xạ tới tenant có order, các scopes phù hợp phải có, và ứng dụng phải có security chain cho route. **jwt() trong Spring Security Test tạo authentication giả**, không xác minh chữ ký/issuer/audience; nhóm test JWT thật cần decoder với khóa test riêng. Test **428** cũng nên đọc lại DB, xác minh version không đổi. Nếu endpoint cho phép anonymous GET, dùng fixture tương ứng thay vì ngầm cho mọi token đọc được.

### 12.3. Test concurrency và idempotency cần lưu trữ thật

**Hai request đồng thời** có cùng If-Match phải chạy trên DB thực hoặc transaction engine tương đương; mock service tự trả 412 chỉ kiểm controller mapping, **không chứng minh CAS**. Test nên có barrier/synchronization để hai request đọc cùng version, sau đó xác nhận **chỉ một UPDATE được commit**. Với POST key, gửi đồng thời cùng key, rồi kiểm **COUNT orders = 1**, dedupe record trạng thái hoàn tất và body/Location replay; kết hợp fault injection **commit rồi mất response**.

**Test 304 phải kiểm cả quyền và freshness:** actor tenant B gửi If-None-Match lấy từ tenant A không được nhận representation hoặc thông tin xác nhận tồn tại. Sau PATCH thật, GET với tag cũ phải trả **200 + ETag mới**, không được trả 304 do Redis/replica stale nếu hợp đồng yêu cầu dữ liệu vừa commit.

### 12.4. Test retry policy ngoài server

Mock HTTP server cho SDK trả tuần tự:

~~~text
GET: 503 Retry-After: 1 -> 200
    => chờ hợp lý rồi thành công, tối đa attempts đã công bố.

GET: 401 -> không retry mù, chuyển qua auth flow.

POST có key: timeout sau khi mock server ghi nhận commit -> replay 201
    => cùng key, cùng payload, chỉ một command được thực hiện.

GET: 429 Retry-After vượt remaining deadline
    => dừng, trả lỗi có thể xử lý, không đợi quá budget.

PATCH: 412
    => không tự ghi đè bằng ETag mới.
~~~

Đo **số attempts, thời gian chờ, key/header của từng attempt và trạng thái cuối**, không chỉ boolean “test passed”. Retry ở gateway, SDK và consumer background có thể cộng dồn; kiểm một tầng không thay kiểm end-to-end. Tránh đưa actual access token vào test logs, và dùng fake billing/notification service để không tạo giao dịch thật.

## 13. Trải nghiệm developer: một trang mẫu nên có gì?

Người tích hợp cần **trả lời được câu hỏi “sau response này làm gì?”** mà không đọc nhiều trang rời nhau. Với mỗi endpoint chính, tài liệu nên đặt cạnh nhau:

1. **Purpose + side effect:** request có tạo/sửa dữ liệu không, có an toàn retry không.
2. **Authentication/scope/tenant:** Bearer, audience, quyền trên resource, không dùng ID token.
3. **Required request headers:** Content-Type, Accept, If-Match, Idempotency-Key, yêu cầu nào là bắt buộc.
4. **Request/response samples đầy đủ:** method, URI, headers, body, status, Location/ETag/Cache-Control.
5. **Error table cùng action:** 400/401/403/404/409/412/428/429/503 với Problem Details và quy tắc retry.
6. **Công thức phục hồi:** network timeout sau POST, mất token, conflict, cache revalidation, rate limit.
7. **Tham số vận hành:** max payload, pagination, retry deadline, quota, TTL của key, timeouts, freshness.
8. **Code samples/test fixtures:** curl, Java/Spring hoặc SDK tương ứng, UUID/token giả và contract tests.

Một ví dụ curl an toàn cho môi trường test, dùng biến đã được cung cấp bằng cách không lộ secret trong tài liệu:

~~~bash
curl -i "$BASE_URL/api/orders/$ORDER_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json" \
  -H 'If-None-Match: "order-11111111-v7-json"'
~~~

Đừng dùng token production trong command được lưu vào CI logs hoặc shell history; sử dụng token test có scope tối thiểu và thời hạn ngắn. Khi viết ví dụ lỗi, trả message đủ hướng dẫn nhưng **không chép stack trace**. Với retry, công bố cả trường hợp không nên thử lại; “mọi lỗi 5xx retry ba lần” không phải chính sách an toàn cho POST.

### 13.1. Đừng mâu thuẫn giữa trang hướng dẫn và SDK

Nếu OpenAPI ghi response **304 không body** nhưng SDK ép JSON deserialize body cho mọi 2xx/3xx, người dùng sẽ gặp lỗi. Nếu trang hướng dẫn bắt buộc If-Match nhưng SDK không expose header, đó là lỗi Developer Experience thực sự. Kiểm **generated SDK**, mock server và examples cùng một bộ contract; version hóa thay đổi retry semantics, enum errors, ETag và idempotency behavior như thay đổi hành vi API khác.

## 14. Bài tập tình huống: điều tra retry trùng đơn và cache không cập nhật

**Bối cảnh:** một mobile client gửi POST tạo order. Server commit order và trả 201, nhưng kết nối đứt nên client không nhận response. Client tự tạo **Idempotency-Key mới** rồi retry; DB có hai orders. Sau đó hai nhân viên sửa cùng một order nhưng API không yêu cầu If-Match; người thứ hai ghi đè người thứ nhất. GET lại có khi trả 304 dù bản ghi đã đổi vì service dùng ETag từ cache cũ. Khi hệ thống bận, client retry 429 mỗi 50 ms và làm tải tăng.

**Yêu cầu:**

1. Chỉ ra bốn failure modes độc lập, đề xuất cơ chế đúng cho từng lỗi.
2. Viết ví dụ HTTP cho POST có key, PATCH với If-Match, GET với If-None-Match và 429 có Retry-After.
3. Giải thích vì sao **Idempotency-Key không thay If-Match**, và vì sao **304 không chứng minh actor có quyền**.
4. Đề xuất logic server để chỉ tạo một order khi client gửi cùng key hai lần; nêu dữ liệu dedupe store và scope tenant.
5. Nêu sáu test chứng minh không duplicate, không lost update, không stale 304, không retry storm và không lộ dữ liệu tenant.

**Hướng giải:** POST retry **cùng key/cùng payload**, server atomic dedupe claim và lưu outcome; client có cơ chế lookup nếu timeout. PATCH yêu cầu **strong ETag/If-Match** và CAS atomic trong DB, sai → 412; thiếu → 428. GET dùng ETag của **selected representation hiện hành** để đánh giá If-None-Match, không lấy Redis stale làm bằng chứng; vẫn authenticate/authorize. 429 ghi rõ Retry-After, client **exponential backoff + jitter + total deadline**. Test hai concurrent POST cùng key, hai PATCH cùng ETag, GET sau cập nhật, actor khác tenant, 429 với delay lớn và timeout sau commit.

## 15. Checklist review trước khi công bố tài liệu

- [ ] Mọi ví dụ có **method, URI, headers cần thiết, body, HTTP status và Content-Type** đúng.
- [ ] **Problem Details** có type/status ổn định, không lộ tokens, PII, SQL hoặc stack trace.
- [ ] Phân biệt **401 Bearer challenge**, 403 quyền/CSRF, 404 không tiết lộ, 409 conflict, 412/428 conditional.
- [ ] Mô tả **Retry-After** (seconds hoặc HTTP-date), retryable statuses, deadline, backoff/jitter và max attempts.
- [ ] **POST retry có Idempotency-Key** giữ cùng key/payload, scope/TTL được công bố và test duplicate.
- [ ] **GET ETag + Cache-Control + Vary + 304 không body** được kiểm; 304 không bỏ qua authorization.
- [ ] **PATCH/PUT If-Match** dùng strong ETag, CAS atomic; thiếu → 428, stale → 412.
- [ ] Cache policies không làm lộ dữ liệu tenant hoặc phản hồi stale trái hợp đồng; no-cache khác no-store.
- [ ] OpenAPI định nghĩa headers, errors và examples tương thích với runtime, SDK và snippets.
- [ ] Regression tests kiểm **state DB không đổi khi lỗi**, đồng thời kiểm header/status/body của từng tình huống.
- [ ] Ví dụ dùng domain/UUID/tokens test; không có secrets production hoặc callback URL giả mạo.
- [ ] Có hướng dẫn **cách phục hồi**, không chỉ mô tả response thành công.

**Kết luận:** tài liệu REST API đáng tin không dừng ở các response 2xx. Nó phải dạy client **cách xử lý lỗi có thể dự đoán**, **retry đúng và không nhân đôi side effects**, **dùng ETag để cache/revalidate an toàn** và **dùng preconditions để tránh lost updates**. Các ví dụ HTTP, mã Java/Spring, OpenAPI và contract tests phải thể hiện **cùng một hợp đồng**, gồm cả quyền tenant và giới hạn vận hành.
