# Đổi URI, giữ alias và di chuyển client có kiểm soát

## 1. Đổi URI không chỉ là đổi tên route

API đang phục vụ đơn hàng qua `GET /api/v1/orders/ord-42` và muốn chuyển sang `GET /orders/ord-42`. Với server, thay route có thể rất dễ; nhưng URI cũ đã hiện diện trong mobile SDK, bookmark, ứng dụng đối tác, cache, webhook và scripts. Xóa ngay có thể tạo 404; redirect sai có thể đổi POST thành GET, mất body/credentials hoặc gây ghi trùng.

**Tiến hóa API phải bảo toàn danh tính tài nguyên, HTTP semantics, hợp đồng dữ liệu và quyền truy cập trong lúc di chuyển client.** Ba khái niệm chính:

- **Canonical URI:** đường dẫn được ưu tiên cho client mới.
- **Alias:** URI cũ tiếp tục định vị cùng resource/operation; có thể xử lý trực tiếp hoặc redirect được kiểm chứng.
- **Controlled migration:** công bố thay đổi, đo client còn dùng đường cũ, nâng SDK theo giai đoạn và chỉ sunset khi rủi ro chấp nhận được.

Bài thuộc chương **Tiến hóa API** của `INTEGRATION_API_REST`, vận dụng resource/URI, HTTP methods/status, cache, idempotency, OpenAPI, xác thực/phân quyền và kiểm thử Java/Spring.

**Mục tiêu:** phân biệt alias 200 với 3xx; chọn đúng 301/302/303/307/308; giữ query và liên kết canonical; không lặp side effect khi thay URI; áp dụng Deprecation/Sunset, Spring MVC, contract tests, telemetry và rollback.

## 2. Cần định nghĩa chính xác “cùng một resource”

Ví dụ:

```text
URI cũ: /api/v1/orders/ord-42
URI mới: /orders/ord-42
Resource: đơn hàng ord-42 thuộc tenant T
```

Hai URI được coi là alias trong bài này nếu cùng định vị **một định danh nghiệp vụ**, không phải hai bản sao dữ liệu. Những điểm cần giữ nhất quán:

| Thành phần | Yêu cầu khi dùng alias |
| --- | --- |
| Định danh và dữ liệu | Không sao chép thành hai đơn hàng có trạng thái độc lập |
| HTTP method | GET đọc, POST/PUT/PATCH/DELETE giữ ý nghĩa được công bố |
| Hợp đồng JSON | Không âm thầm đổi kiểu/required field chỉ vì đổi đường dẫn |
| Authorization | Cùng owner/tenant và quy tắc phân quyền |
| Side effect | Cùng service/transaction và cơ chế idempotency |
| Response | Status, lỗi, ETag, representation và URI kết quả được quy định rõ |
| Link liên quan | Ưu tiên trả **canonical URI** trong representation mới |
| Audit | Ghi nhận URI cũ/mới để đo migration, nhưng cùng domain operation |

**Đổi URI không đồng nghĩa đổi version của toàn bộ API.** Nếu ngoài URI còn thay mô hình domain hoặc response breaking, cần đánh giá thành một thay đổi hợp đồng riêng, có thể cần version, adapter tương thích hoặc endpoint mới thật sự. Không dùng “alias” để che một thay đổi hành vi khiến client cũ hiểu sai.

### Hai ví dụ có bản chất khác nhau

1. `/api/v1/orders/{id} → /orders/{id}`: có thể chỉ chuyển tên đường dẫn với payload/semantics giữ nguyên; alias tương đối dễ.
2. `/orders/{id} → /fulfillments/{id}`: có thể là **resource khác**, không chỉ rename; nếu danh tính, quyền và vòng đời khác nhau, không nên redirect mù quáng.

Một **canonical URI** là quy ước thiết kế và khám phá của API. HTTP không bắt buộc mỗi resource chỉ có một URI, nhưng nhiều địa chỉ gây thêm gánh nặng cache, logs, signatures và tài liệu, nên cần thống nhất đầu ra.

## 3. Alias 200 hay redirect? Hai cách phục vụ URI cũ

### A. Alias xử lý trực tiếp và trả 200

```http
GET /api/v1/orders/ord-42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store
ETag: "order-42-v17"
Link: </orders/ord-42>; rel="canonical"
Deprecation: @1799971200
Sunset: Thu, 01 Jul 2027 00:00:00 GMT

{"id":"ord-42","status":"CONFIRMED"}
```

Server nhận URI cũ, gọi **cùng service** như URI mới rồi trả response bình thường. Client cũ không phải hiểu redirect. `Link` với relation `canonical` cung cấp địa chỉ ưu tiên cho client có hỗ trợ relation đó, **không ép** mọi HTTP client tự chuyển sang URI mới.

`Deprecation` và `Sunset` là tín hiệu hỗ trợ kế hoạch chuyển đổi, không phải thứ làm response 200 tự đổi thành redirect. Trong ví dụ, `Deprecation: @1799971200` là thời điểm **15/01/2027 UTC** theo dạng ngày có cấu trúc; `Sunset` dự kiến ngừng hỗ trợ vào **01/07/2027 UTC**. Đây là **mốc giả định của bài học**, không phải chính sách của hệ thống nào.

**Ưu điểm:** tương thích tốt với SDK/crawler/client cũ, tránh đổi method hoặc mất token do redirect; rollback dễ. **Nhược điểm:** hai route cùng tồn tại, nguy cơ giữ mã nghiệp vụ tách đôi, nhiều cache keys, telemetry phân tán và chi phí duy trì lâu dài.

### B. Redirect từ URI cũ đến canonical URI

```http
GET /api/v1/orders/ord-42 HTTP/1.1
Host: api.example.test

HTTP/1.1 307 Temporary Redirect
Location: /orders/ord-42
Cache-Control: no-store
```

Client hiểu redirect sẽ gửi request tiếp theo đến `/orders/ord-42`. Với `307`, method không được đổi khi tự động redirect; với GET, việc này đơn giản. Tuy nhiên **không phải mọi client đều tự follow redirect**. SDK có thể trả nguyên status 307 cho caller, mobile HTTP stack có giới hạn redirects, hoặc gateway tự chặn.

**Ưu điểm:** server tập trung xử lý ở một URI, client có thể chuyển tới địa chỉ mới tự động. **Nhược điểm:** thêm round-trip, phụ thuộc client, cơ chế forward headers/body, cookie/CORS và caching của redirect. Với request ghi, những rủi ro này lớn hơn nhiều.

### So sánh

| Đặc điểm | Alias trực tiếp 200 | Redirect 307/308 |
| --- | --- | --- |
| Client không follow 3xx | Vẫn hoạt động | Có thể thất bại |
| POST có body | Dễ kiểm soát qua cùng service | Phụ thuộc redirect support, xác thực, replay body |
| Độ trễ | Không thêm vòng HTTP | Thêm một round-trip nếu không cache redirect |
| Thu thập lượt gọi URI cũ | Đếm ở alias | Đếm redirect, nhưng cache 308 có thể che mất lượt gọi sau |
| Rollback | Đổi routing tương đối dễ | Redirect permanent có thể bị cache dai |
| Cache representation | Có thể tạo hai keys | Redirect và target có chính sách cache riêng |
| Bảo mật | Phải kiểm tra quyền trên alias | Phải kiểm tra quyền ở đích và kiểm soát Location |

**Khuyến nghị thực hành:** trong giai đoạn chuyển tiếp ban đầu, ưu tiên **alias xử lý trực tiếp** cho những SDK chưa rõ mức hỗ trợ redirect và cho các thao tác ghi. Sau khi quan sát client thực tế, có thể cân nhắc redirect cho GET/HEAD nếu mang lại lợi ích rõ ràng.

## 4. Chọn đúng mã redirect theo HTTP method

Không thể đổi mọi URL bằng một status duy nhất mà bỏ qua semantics:

| Status | Tính chất | Khi client tự follow |
| --- | --- | --- |
| **301 Moved Permanently** | Địa chỉ mới lâu dài | Một số user agent có thể đổi POST thành GET theo tương thích lịch sử; không chọn nếu cần bảo toàn body/method |
| **302 Found** | Chuyển hướng tạm thời | Tương tự 301: một số client có thể đổi POST thành GET |
| **303 See Other** | Chỉ tới một tài nguyên khác để **xem bằng GET** (trừ xử lý HEAD) | Phù hợp mô hình POST thành công rồi chuyển tới kết quả; **không** dùng để chuyển tiếp nguyên thao tác ghi |
| **307 Temporary Redirect** | Chuyển tạm thời | Không đổi method khi tự follow; phải giữ ngữ nghĩa body |
| **308 Permanent Redirect** | Chuyển lâu dài | Không đổi method khi tự follow; nguy cơ cache/bám lâu nếu rollback |

Ví dụ khi muốn di chuyển **POST**:

```http
POST /api/v1/orders/ord-42/cancellation-requests HTTP/1.1
Content-Type: application/json
Idempotency-Key: "cancel-ord-42-8f6"

{"reason":"Đổi ý"}
```

Nếu server dùng 301/302, client có thể chuyển sang `GET /orders/ord-42/cancellation-requests`, khiến thao tác **không được thực hiện** hoặc trả sai kết quả. 307/308 bảo toàn method nhưng **không giải quyết** việc client có phát lại được body streaming, có giữ credentials và idempotency key hay không.

**Vì vậy, với write endpoints, giữ alias được xử lý nội bộ thường an toàn hơn** so với đặt cược vào hành vi redirect của toàn bộ client. Nếu bắt buộc dùng 307/308 cho thao tác ghi, hãy kiểm thử từng client/gateway thật trước khi áp dụng.

### 303 khác redirect khi đổi URI

Một POST tạo yêu cầu xuất báo cáo có thể trả `303 See Other` tới job/result resource mà client **GET** tiếp. Đó là chuyển sang một **hành động đọc khác**, không phải transparent migration của chính POST từ đường cũ sang đường mới. Không dùng 303 để thay thế POST ở canonical path.

### Vấn đề cache của “permanent”

301 và 308 có thể được cache theo HTTP semantics khi không có chỉ thị ngược lại; trình duyệt hoặc SDK cũng có thể nhớ địa chỉ mới. Một redirect 308 phát ra quá sớm có thể còn ảnh hưởng client **sau khi server rollback**. Khi thử nghiệm, cân nhắc 307 với cache policy bảo thủ, kiểm tra hành vi client, rồi mới quyết định 308. `Cache-Control: no-store` cho response redirect giúp yêu cầu HTTP cache không lưu, nhưng không phải cách chắc chắn buộc mọi ứng dụng xóa URL mà nó đã ghi lại.

## 5. URI mới: phải giữ danh tính, query và encoding

Một API không chỉ có đường dẫn đơn giản. Ví dụ:

```http
GET /api/v1/orders/ord-42?include=items&sort=createdAt HTTP/1.1
```

Nếu query parameters này vẫn có ý nghĩa tại canonical endpoint, URI mới cần giữ:

```http
Location: /orders/ord-42?include=items&sort=createdAt
```

Chuyển sang `/orders/ord-42` mà bỏ `include=items` có thể thay đổi representation mà client trông chờ. Với collection, bỏ `cursor`, `filter` hay `limit` có thể khiến client đọc lại trang đầu hoặc bỏ sót dữ liệu.

**Các trường hợp cần kiểm tra:**

- **Path variable:** ID hoặc slug có ký tự cần percent-encoding; không nối chuỗi URI thô bằng input không tin cậy.
- **Query:** giữ những tham số còn được hỗ trợ, nhiều giá trị cùng tên, dấu `+`, ký tự đã encode; không tự tiện bỏ filter quan trọng.
- **Fragment:** phần `#fragment` không được gửi tới server trong HTTP request; server không thể lấy fragment ban đầu để chuyển tiếp từ request.
- **Scheme/host:** nếu chuyển từ cùng origin sang origin mới, xác thực, CORS, TLS, cookie, signed URL và redirect policy đều cần kiểm chứng.
- **Trailing slash/case:** xác định canonicalization rõ; không tạo `/orders/42 → /orders/42/ → /orders/42` thành vòng lặp.
- **Base path và reverse proxy:** xử lý `Forwarded`/`X-Forwarded-*` qua proxy đáng tin khi tạo absolute URL; không tin header Host do client điều khiển để tạo redirect tới domain bất kỳ.

Ưu tiên dùng URI builder được framework hỗ trợ, với **đường đích/host cố định từ cấu hình**, thay vì sử dụng `next` hoặc `redirect` do caller cung cấp. Đây cũng là một biện pháp chống **open redirect**.

## 6. Hypermedia: hướng client mới tới URI chuẩn

Ngay khi canonical endpoint hoạt động, các response nên quảng bá URI mới trong các liên kết mà client có thể khám phá:

```json
{
  "id": "ord-42",
  "status": "CONFIRMED",
  "_links": {
    "self": {"href": "/orders/ord-42"},
    "collection": {"href": "/orders"},
    "items": {"href": "/orders/ord-42/items"}
  }
}
```

Đây là ví dụ theo phong cách HAL. Ngay cả khi client truy cập qua alias `/api/v1/orders/ord-42`, server có thể trả `_links.self` là canonical URI **nếu hợp đồng dành cho client cũ cho phép**. Client biết theo `rel="self"` sẽ dần dịch chuyển mà không cần ghép URL. Tuy nhiên, client cũ hard-code route hoặc xem `self` phải trùng URI request có thể cần giai đoạn tương thích riêng; đừng thay đổi không kiểm thử.

Các nguồn URI cần sửa đồng bộ: `Location` sau POST, `Link`/`_links` trong response, URL trong pagination `next/prev`, export/job status link, webhook event payload, OpenAPI `servers` và examples, client SDK cấu hình, email hoặc callback URL (khi liên quan). **Không nên để server phát URI cũ vô thời hạn** dù đã chuyển canonical path.

### Location khác Link và Content-Location

- `Location` trong 3xx chỉ URI redirect; trong 201 thường chỉ resource được tạo.
- `Link: <...>; rel="canonical"` mô tả liên hệ tới URI ưu tiên, **không khiến client tự động follow như 3xx**.
- `Content-Location` mô tả URI liên quan tới representation được gửi theo semantics HTTP; **không dùng nó như cơ chế redirect thay Location**.

Khi đổi URI nhưng vẫn phục vụ JSON qua alias, các liên kết do server công bố là công cụ migration đáng giá — với điều kiện client có hợp đồng hiểu chúng.

## 7. Deprecation, Sunset và tài liệu nâng cấp

Alias còn hoạt động **không có nghĩa được hỗ trợ mãi**. Công bố rõ thời gian:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| `Deprecation` response header | Khi endpoint bắt đầu/được dự kiến không khuyến nghị dùng |
| `Sunset` response header | Khi việc phục vụ URI cũ dự kiến kết thúc |
| `Link rel="canonical"` và link tài liệu | URI ưu tiên và hướng dẫn nâng cấp, không tự redirect |
| OpenAPI `deprecated: true` | Đánh dấu operation cũ trong contract/tooling |
| Changelog/SDK release notes | Thông báo chủ động tới client không đọc headers |

```http
HTTP/1.1 200 OK
Deprecation: @1799971200
Sunset: Thu, 01 Jul 2027 00:00:00 GMT
Link: </orders/ord-42>; rel="canonical"
Link: </docs/migrations/orders-uri>; rel="help"
```

`@1799971200` là mốc **15/01/2027 UTC** theo cú pháp ngày cấu trúc; `Sunset` theo HTTP-date là **01/07/2027 UTC**. Đây là mốc giả định của bài. Deprecation không lập tức chặn request; Sunset là kế hoạch, cần hỗ trợ, theo dõi client chưa chuyển và thông báo nếu điều chỉnh.

## 8. Kế hoạch migration theo giai đoạn, có tiêu chí dừng

Một thay đổi URI an toàn không phải là triển khai 308 vào một ngày cố định. Hãy tách thành các **giai đoạn có thể quan sát và rollback**:

| Giai đoạn | Server | Client/hợp đồng | Tiêu chí chuyển bước |
| --- | --- | --- | --- |
| **0. Khảo sát** | Kiểm kê routes, methods, ACL, caches, SDK, integrations | Xác định owner của các client cũ, phiên bản còn dùng | Có baseline traffic và danh sách rủi ro |
| **1. Song song** | Canonical mới + alias cũ cùng service; kiểm thử tương đương | Công bố OpenAPI mới, deprecation và tài liệu chuyển đổi | Không có chênh lệch hành vi/security đáng kể |
| **2. Di chuyển** | Phát canonical URI trong Location/links, đo đường cũ | Phát hành SDK, chuyển web/mobile/partner; cập nhật callback | Tỷ lệ traffic cũ giảm; không tăng 4xx/5xx |
| **3. Cảnh báo cuối** | Giữ tương thích; phát Sunset dự kiến | Nhắc các đối tác còn gọi route cũ; xử lý ngoại lệ | Đã kiểm kê các client chủ chốt và rủi ro còn lại |
| **4. Ngừng alias** | Theo chính sách, trả 410/404 hoặc chuyển hướng an toàn đã được chứng minh | Đảm bảo client mới không dùng route cũ | Có phương án xử lý sự cố và tài liệu hỗ trợ |

Các mốc trong bài là **minh họa**, không phải SLA chung. Nếu không thể quan sát client cũ (ví dụ ứng dụng ngoại tuyến lâu ngày), hãy đặt thời gian hỗ trợ tương ứng vòng đời ứng dụng thay vì đợi “traffic bằng 0 tuyệt đối”.

### Quyết định rollback

- Với **alias trực tiếp**, có thể giữ cả hai routes sau khi tạm ngừng thúc đẩy migration; tránh xóa dữ liệu hoặc đổi định danh.
- Với **307**, đổi lại response từ redirect sang 200 tương đối dễ; một số client có thể đã lưu canonical URL từ Location.
- Với **301/308**, client/cache có thể tiếp tục dùng URI mới dù server không còn redirect; rollback chỉ ở server chưa chắc đảo được sự thay đổi đã ghi nhớ ở client.
- Với **write endpoints**, rollback phải kiểm tra lại cơ chế chống trùng và mapping kết quả, không chỉ đảo route.

**Gating quan trọng:** một đợt rollout không hoàn thành chỉ vì test curl thành công. Cần theo dõi SDK cũ, mobile OS/browser, integration khách hàng, gateway và các thao tác ghi đã được xác nhận.

## 9. Thao tác ghi trên hai URI: idempotency phải theo ý định, không theo path

Giả sử request tạo yêu cầu hủy đi qua alias cũ rồi bị timeout. Client retry qua URI mới sau khi nhận tài liệu migration:

```http
POST /api/v1/orders/ord-42/cancellation-requests HTTP/1.1
Idempotency-Key: "cancel-ord-42-8f6"
Content-Type: application/json

{"reason":"Đổi ý"}
```

Sau đó:

```http
POST /orders/ord-42/cancellation-requests HTTP/1.1
Idempotency-Key: "cancel-ord-42-8f6"
Content-Type: application/json

{"reason":"Đổi ý"}
```

Nếu service lưu idempotency theo **raw URL** thì hai request có thể bị coi là hai thao tác khác nhau và tạo **hai cancellation requests**. Khi hai URI là alias của **cùng một operation**, chính sách idempotency phải định danh theo ý định đã chuẩn hóa, ví dụ:

```text
scope = tenantId + authenticatedPrincipal + logicalOperation
        + Idempotency-Key

fingerprint = canonicalizedRequestSemantics
logicalOperation = "create-cancellation-request"
```

Đây là mô hình gợi ý; phạm vi chính xác và TTL phải được công bố. Không trộn key của hai operation không tương đương. Payload khác dùng cùng key phải bị từ chối theo chính sách, thay vì tái sử dụng kết quả của một ý định khác.

**Cần bảo đảm:**

1. Cả hai paths gọi **cùng service/transaction**; không có hai bộ dữ liệu/queue độc lập.
2. Unique constraint hoặc transaction tránh race giữa hai request đồng thời từ hai URI.
3. `Location` của kết quả mới trỏ canonical URI, nhưng replay theo key vẫn trả cùng resource/status theo hợp đồng.
4. Authorization và quota được thực thi giống nhau, tránh alias cũ thành lối đi vòng.
5. Khi timeout, client kiểm tra trạng thái/idempotency trước khi retry request có side effects.

Với PUT/PATCH, còn phải giữ semantics của ETag và `If-Match`: version tài nguyên không nên biến thành **hai dòng phiên bản độc lập** chỉ vì route khác. Đổi URI cũng không nên âm thầm bỏ yêu cầu precondition hoặc thay định dạng PATCH.

## 10. Bảo mật khi di chuyển đường dẫn hoặc origin

URI migration đôi khi chuyển luôn host: từ `https://legacy-api.example.test/orders` sang `https://api.example.test/orders`. Đây không chỉ là đổi router. Các điểm phải review:

| Rủi ro | Tình huống | Kiểm soát |
| --- | --- | --- |
| **Mất Authorization** | Client HTTP chủ động loại header khi follow redirect sang origin khác | Thử với từng SDK; ưu tiên alias ở origin cũ hoặc cấu hình auth mới rõ ràng |
| **Rò credentials/body** | Redirect tới host không tin cậy hoặc bị điều khiển qua query/Host | Allowlist origin, TLS, cố định URL đích, không redirect raw input |
| **Cookie/CORS** | Domain, SameSite, preflight thay đổi | Thiết kế cookie scopes/CORS/CSRF; kiểm thử browser thực |
| **Bypass ACL** | Route cũ dùng filter cũ, route mới dùng filter mới | Dùng chung security policy; test cả hai paths |
| **Cache chia sẻ** | Alias và canonical có cache keys/policies khác nhau | Không để lộ dữ liệu riêng; thống nhất Cache-Control/Vary/ETag |
| **IDOR** | Redirect làm lộ ID của resource không được xem | Kiểm tra quyền trước khi tiết lộ nội dung nhạy cảm, không suy quyền từ URL |
| **Request signing** | HMAC ký cả method/path nên URI mới làm signature không khớp | Quy định canonical path trong signature, hỗ trợ giai đoạn kép có kiểm soát |
| **Webhook/callback** | Bên nhận có danh sách URL cho phép hoặc không follow 3xx | Cập nhật cấu hình/hợp đồng, không giả định webhook sender tự chuyển |

Một redirect 307/308 **bảo toàn method theo HTTP semantics**, nhưng điều đó không bảo đảm body stream có thể được gửi lại, token vẫn được đính kèm hay CSRF/cookie còn hợp lệ. Với API nhạy cảm, **ưu tiên xử lý alias trực tiếp** hoặc buộc client nâng cấp có xác nhận trước khi redirect write methods.

Không để URI cũ bỏ kiểm tra tenant vì “chỉ còn là compatibility layer”. Một alias tồn tại thêm sáu tháng vẫn là một endpoint production và chịu toàn bộ yêu cầu xác thực, phân quyền, quota, validation và audit.

## 11. Java/Spring: alias và canonical dùng chung service

Với Spring MVC/Java 17+, giữ hai GET routes nhưng **gộp logic nghiệp vụ và authorization** trong cùng service. Ví dụ bỏ qua imports/DI và các abstraction của dự án:
 
```java
record OrderView(UUID id, String status) {}
record VersionedOrder(OrderView body, String strongEtag) {}

@RestController
class OrderController {
    private final OrderQueryService queries;
    private final CancellationService commands;
    OrderController(OrderQueryService queries, CancellationService commands) {
        this.queries = queries;
        this.commands = commands;
    }

    @GetMapping("/orders/{id}")
    ResponseEntity<OrderView> current(@PathVariable UUID id,
                                      Authentication caller) {
        return render(id, caller, false);
    }

    @GetMapping("/api/v1/orders/{id}")
    ResponseEntity<OrderView> legacy(@PathVariable UUID id,
                                     Authentication caller) {
        return render(id, caller, true);
    }

    private ResponseEntity<OrderView> render(
            UUID id, Authentication caller, boolean legacy) {
        VersionedOrder o = queries.findAuthorized(id, caller);
        ResponseEntity.BodyBuilder response = ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .eTag(o.strongEtag());
        if (legacy) {
            response.header("Deprecation", "@1799971200")
                .header("Sunset", "Thu, 01 Jul 2027 00:00:00 GMT")
                .header(HttpHeaders.LINK,
                    "</orders/" + id + ">; rel=\"canonical\"");
        }
        return response.body(o.body());
    }

    @PostMapping(path = {
        "/orders/{id}/cancellation-requests",
        "/api/v1/orders/{id}/cancellation-requests"
    }, consumes = "application/json")
    ResponseEntity<Void> createCancellation(
            @PathVariable UUID id,
            @RequestHeader("Idempotency-Key") String key,
            @Valid @RequestBody CancellationBody body,
            Authentication caller) {
        UUID created = commands.createIdempotently(id, caller, key, body);
        return ResponseEntity.created(URI.create(
            "/orders/" + id + "/cancellation-requests/" + created)).build();
    }
}
record CancellationBody(@NotBlank String reason) {}
```

`findAuthorized` kiểm tra owner/tenant; `createIdempotently` kiểm tra trạng thái, quyền, fingerprint theo **logical operation**, unique constraint và transaction. Hai paths không tạo hai resource độc lập. `Location` sau POST trỏ URI chuẩn. Code sử dụng UUID thực, còn `ord-42` trong ví dụ HTTP là ID minh họa. ETag phải khớp representation; khi thêm conditional GET/304, phải áp dụng cùng quy tắc preconditions ở cả alias và canonical.

Nếu cần redirect GET trong một route khác, Spring có thể trả:
 
```java
return ResponseEntity.status(HttpStatus.TEMPORARY_REDIRECT)
    .location(URI.create("/catalog/items/" + validatedUuid))
    .cacheControl(CacheControl.noStore())
    .build();
```

Không gắn redirect này lên cùng mapping với alias 200 ở trên. Với query phức tạp, hãy dùng URI builder/allowlist tham số và encode đúng, không nối input thô. Đối với POST có body, tiếp tục xử lý alias nội bộ khi chưa xác minh client redirect; cấu hình gateway cũng phải tuân thủ cùng quy tắc auth, method và idempotency.

## 12. OpenAPI: một operation chuẩn, một operation cũ

Khi server còn phục vụ cả hai, **mô tả cả hai paths**. Đánh dấu `deprecated: true` ở operation cũ và dùng `operationId` khác để tránh xung đột trong codegen:
 
```yaml
openapi: 3.0.3
info: {title: Orders API, version: 1.0.0}
paths:
  /orders/{id}:
    get:
      operationId: getOrder
      parameters:
        - in: path
          name: id
          required: true
          schema: {type: string, format: uuid}
      responses:
        '200':
          description: Đơn hàng tại URI chuẩn
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Order'}
  /api/v1/orders/{id}:
    get:
      operationId: getOrderLegacy
      deprecated: true
      description: Alias tương thích, sunset dự kiến 2027-07-01
      parameters:
        - in: path
          name: id
          required: true
          schema: {type: string, format: uuid}
      responses:
        '200':
          description: Cùng resource, có thông tin migration
          headers:
            Deprecation: {schema: {type: string}}
            Sunset: {schema: {type: string}}
            Link: {schema: {type: string}}
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Order'}
components:
  schemas:
    Order:
      type: object
      required: [id, status]
      properties:
        id: {type: string, format: uuid}
        status: {type: string}
```

Trích đoạn chưa có security schemes, POST hay mọi status/error. Nếu route cũ chuyển sang 307, **đổi OpenAPI responses thành 307 + Location**, không vẫn tuyên bố trả 200. `deprecated: true` là metadata, không khiến Spring tự phát `Deprecation` header. Generated SDK mới có thể ẩn legacy method qua cấu hình generator, nhưng phải kiểm tra đường tương thích trên server.

## 13. Contract tests: đúng request, cùng ý định, không lộ quyền

Các nhóm test quan trọng:
 
| Ca | Khẳng định |
| --- | --- |
| GET cũ/mới | Cùng resource, payload/ETag nhất quán |
| GET alias | Có Deprecation, Sunset, Link tới canonical |
| Collection | Query filter/sort/cursor giữ nguyên |
| 307/308 khi dùng | Location đúng, không redirect loop, client xử lý được |
| Write cũ/mới | Cùng operation; Location kết quả là canonical |
| Idempotency | POST qua hai paths cùng key chỉ tạo một resource |
| Authorization | Alias không vượt qua quyền tenant/owner |
| Preconditions | If-Match/ETag giữ ý nghĩa ở cả hai |
| SDK/browser | Method, body, token, cookie không thất lạc khi redirect |
| Retirement | 404/410 và tài liệu theo chính sách, không rò ID |

### MockMvc: alias cùng dữ liệu

```java
@Test
void oldGetIsCompatibleWithNew() throws Exception {
    UUID id = seedOrderFor("owner");
    String expected = mockMvc.perform(get("/orders/{id}", id)
            .with(user("owner")))
        .andExpect(status().isOk()).andReturn()
        .getResponse().getContentAsString();

    mockMvc.perform(get("/api/v1/orders/{id}", id)
            .with(user("owner")))
        .andExpect(status().isOk())
        .andExpect(header().string("Deprecation", "@1799971200"))
        .andExpect(header().string("Link",
            containsString("rel=\"canonical\"")))
        .andExpect(content().json(expected));
}
```

### MockMvc: POST cùng key qua hai URI

```java
@Test
void legacyAndCanonicalPostDoNotDoubleCreate() throws Exception {
    UUID id = seedCancellableOrder();
    String key = "cancel-42-a";
    String body = "{\"reason\":\"Đổi ý\"}";

    String oldLocation = createCancellation(
        "/api/v1/orders/" + id + "/cancellation-requests", key, body);
    String newLocation = createCancellation(
        "/orders/" + id + "/cancellation-requests", key, body);

    assertEquals(oldLocation, newLocation);
    assertEquals(1, countCancellationRequests(id));
}
```

`createCancellation` là fixture giả định gọi MockMvc POST với caller được phép, assert 201 và trả `Location`. Bổ sung test hai requests **đồng thời** qua hai paths để xác minh unique constraint, cùng với negative test caller tenant khác. Chỉ so HTTP 201 không đủ: phải kiểm tra số row/event/số tác dụng phụ thực tế.

## 14. Quan sát và kết thúc alias

Trước khi đóng route cũ, đo **traffic theo route template, method, client type/SDK version**, tỷ lệ 2xx/3xx/4xx/5xx, redirect failures, 401/403, retry/idempotency collisions và latency. Tách client batch chỉ gọi mỗi tháng khỏi traffic hàng ngày; kiểm tra responses/links vẫn phát URI cũ. Không dùng resource ID, token, Cookie hoặc raw query nhạy cảm làm metric label.

Nếu route cũ **thật sự không còn khả dụng**, `410 Gone` có thể báo rõ điều đó:
 
```http
HTTP/1.1 410 Gone
Content-Type: application/problem+json
Cache-Control: no-store
Link: </docs/migrations/orders-uri>; rel="help"

{"type":"https://api.example.test/problems/legacy-uri-retired",
 "title":"Đường dẫn cũ đã ngừng hỗ trợ","status":410}
```

`410` không bắt buộc: dùng 404 khi policy cần che giấu việc resource từng tồn tại. Nếu giữ 308 thì vẫn có compatibility route cần duy trì và giám sát; không coi như đã xóa hoàn toàn. Chỉ ngừng alias khi client quan trọng đã chuyển, security/errors/idempotency ổn định, có người phụ trách support và phương án rollback. Ngày Sunset là kế hoạch có thể cần điều chỉnh theo tác động thực tế.

## 15. Bài thực hành: đổi URI bộ API đơn hàng

Migrating từ:
 
```text
GET  /api/v1/orders/{id}        -> GET  /orders/{id}
GET  /api/v1/orders?cursor=...  -> GET  /orders?cursor=...
POST /api/v1/orders/{id}/cancellation-requests
     -> POST /orders/{id}/cancellation-requests
```

Mobile cập nhật chậm, một đối tác không follow redirect POST, dữ liệu chia tenant. **Nhiệm vụ:**
 
1. Chọn alias 200 hoặc 307/308 cho từng endpoint; giải thích vì sao không dùng 301/302 cho POST.
2. Viết HTTP response alias có Deprecation/Sunset/Link và redirect GET giữ query/cursor.
3. Viết Spring controller dùng cùng service và cross-path idempotency key cho POST.
4. Thiết kế kiểm tra auth/tenant, CORS, cache, ETag, OpenAPI cũ/mới.
5. Lập timeline khảo sát → song song → migrate SDK → cảnh báo → sunset; nêu tiêu chí rollback.
6. Viết negative tests: caller tenant khác, redirect mất header, POST trùng khi retry qua URI mới.

**Thang điểm:** semantics URI/redirect 25; idempotency write 20; security/query/cache 20; Java/OpenAPI/tests 20; rollout/rollback 15.

## 16. Câu hỏi tự kiểm tra

1. Alias 200 và redirect 307 khác nhau thế nào với SDK không follow redirect?
2. Tại sao 301/302 có thể nguy hiểm với POST? 303 dùng để làm gì?
3. 307 và 308 khác nhau ở điểm nào khi rollback?
4. Vì sao idempotency scope theo raw path có thể tạo duplicate khi gọi cả URI cũ và mới?
5. Điều gì xảy ra nếu redirect bỏ `cursor` hoặc làm sai percent-encoding?
6. `Location`, `Link rel="canonical"` và `Content-Location` khác nhau thế nào?
7. Deprecation khác Sunset, và `deprecated: true` trong OpenAPI có tự phát header không?
8. Vì sao redirect sang origin mới có thể mất Authorization/cookie?
9. Test nào chứng minh alias không bypass tenant authorization?
10. Khi nào 410 hợp lý, khi nào cần 404? Cache 308 ảnh hưởng rollback ra sao?
11. Các metrics nào nên dùng để quyết định đóng route cũ?

**Điểm cần nhớ:** đổi URI là thay đổi **hợp đồng tích hợp**, không chỉ sửa router. Dùng **canonical URI + alias tương thích + thông báo deprecation/sunset + telemetry** để client chuyển dần. Với write requests, ưu tiên alias nội bộ và bảo toàn authorization, HTTP preconditions, idempotency; chỉ redirect khi đã kiểm chứng client. Cutover hoàn tất khi hệ sinh thái đã chuyển an toàn và vẫn có kế hoạch khắc phục sự cố.
