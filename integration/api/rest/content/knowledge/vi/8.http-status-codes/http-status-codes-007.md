# 401, WWW-Authenticate và khác biệt với 403

Khi thiết kế REST API, mã trạng thái HTTP không chỉ biểu diễn kết quả kỹ thuật mà còn là một phần của **hợp đồng giữa client và server**. Một client nhận `401 Unauthorized` thường cần cung cấp hoặc làm mới thông tin xác thực; client nhận `403 Forbidden` thường cần dừng thao tác và xử lý vấn đề quyền truy cập. Nếu API dùng hai mã này tùy tiện, ứng dụng web/mobile có thể lặp vô hạn việc làm mới token, tự đăng xuất khi không cần thiết hoặc hiển thị sai thông báo cho người dùng.

Bài này thuộc chương **Mã trạng thái** trong lộ trình **INTEGRATION_API_REST**. Trọng tâm là ý nghĩa HTTP của `401`, quy tắc dùng response header `WWW-Authenticate`, cách phân biệt với `403`, các trường hợp cần cân nhắc `404` và cách triển khai, mô tả bằng OpenAPI, kiểm thử với Java/Spring Security hoặc công nghệ tương đương. Ví dụ sử dụng OAuth 2.0 Bearer token, nhưng nguyên tắc HTTP áp dụng rộng hơn một framework.

## 1. Hiểu đúng câu hỏi mà mỗi mã trả lời

| Phản hồi | Câu hỏi cốt lõi | Ý nghĩa thường gặp ở REST API bảo vệ bằng Bearer token | Hành động phù hợp của client |
|---|---|---|---|
| **401 Unauthorized** | Có thông tin xác thực hợp lệ cho tài nguyên đích chưa? | Thiếu token, token hết hạn, sai chữ ký, sai issuer/audience hoặc token không được chấp nhận. | Cung cấp token hợp lệ, thử làm mới phiên **có giới hạn** hoặc yêu cầu đăng nhập. |
| **403 Forbidden** | Server có cho phép thực hiện hành động này không? | Token có thể hợp lệ nhưng thiếu quyền/scope, không thuộc tenant hoặc bị chính sách từ chối. | Không lặp lại cùng yêu cầu một cách vô ích; thông báo thiếu quyền hoặc dùng tài khoản phù hợp. |
| **404 Not Found** | Có thể công bố tài nguyên này cho client hay không? | Tài nguyên không tồn tại; đôi khi được dùng để **che giấu sự tồn tại** của tài nguyên bị cấm. | Xử lý như tài nguyên không tìm thấy theo hợp đồng; không suy diễn chắc chắn về quyền. |

Tên lý do chuẩn `Unauthorized` của `401` dễ gây nhầm lẫn: trong thực hành API, đây chủ yếu là tình huống **cần xác thực hợp lệ**. Ngược lại, `403` nói rằng server đã hiểu yêu cầu nhưng từ chối thực hiện. `403` **không bắt buộc** phải có một người dùng đã đăng nhập: server cũng có thể từ chối một request công khai vì chính sách độc lập với danh tính. Bảng trên là quy tắc thiết kế thường dùng, không phải định nghĩa tuyệt đối rằng “401 chưa đăng nhập, 403 đã đăng nhập”.

## 2. Ngữ nghĩa 401 theo HTTP

Theo HTTP Semantics (RFC 9110), `401 Unauthorized` cho biết yêu cầu chưa có thông tin xác thực hợp lệ cho tài nguyên đích. Khi trả `401`, server **phải** gửi ít nhất một challenge áp dụng cho tài nguyên đó trong header **`WWW-Authenticate`**.

Ví dụ yêu cầu đọc đơn hàng cần Bearer token nhưng client chưa gửi token:

```http
GET /api/v1/orders/ord-1001 HTTP/1.1
Host: api.example.com
Accept: application/json
```

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders"
Cache-Control: no-store
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/authentication-required",
  "title": "Authentication required",
  "status": 401,
  "detail": "A valid access token is required."
}
```

Điểm cần nhận ra:

- Header `WWW-Authenticate` nằm trong **response** và cho biết server chấp nhận cơ chế xác thực nào cho tài nguyên.
- Header `Authorization` nằm trong **request** và mang thông tin xác thực mà client gửi lên, ví dụ `Authorization: Bearer <access_token>`.
- `realm="orders"` là một tham số của challenge để mô tả phạm vi bảo vệ; nó **không phải** tên tenant, danh sách quyền và cũng không chứng minh danh tính người dùng.
- Body JSON có thể giúp client hiển thị lỗi; nhưng body **không thay thế** nghĩa vụ gửi header `WWW-Authenticate` trong phản hồi `401`.
- `Cache-Control: no-store` là lựa chọn thận trọng cho phản hồi liên quan tới danh tính hoặc dữ liệu nhạy cảm. Chính sách cache cho các response khác cần được thiết kế theo từng tài nguyên.

Nếu token có mặt nhưng không còn hợp lệ, client vẫn có thể nhận `401`:

```http
GET /api/v1/orders/ord-1001 HTTP/1.1
Host: api.example.com
Authorization: Bearer <expired_access_token>
```

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
Cache-Control: no-store
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/invalid-token",
  "title": "Invalid access token",
  "status": 401,
  "detail": "Supply a valid access token."
}
```

Không gửi lại token gốc, chữ ký, thông tin định danh nhạy cảm hoặc chi tiết triển khai kiểm tra mật mã trong thông báo lỗi. Client chỉ cần biết token không được chấp nhận và cách tiếp tục theo hợp đồng.

## 3. WWW-Authenticate là gì và vì sao quan trọng?

`WWW-Authenticate` là **HTTP authentication challenge**. Một challenge gồm tên **authentication scheme** và có thể kèm tham số; nó mô tả cách client có thể thỏa mãn yêu cầu xác thực.

| Ví dụ challenge | Diễn giải | Ghi chú triển khai |
|---|---|---|
| `WWW-Authenticate: Bearer realm="orders"` | Endpoint chấp nhận Bearer access token. | Phù hợp API dùng OAuth 2.0 Bearer token; `realm` chỉ là thông tin hỗ trợ. |
| `WWW-Authenticate: Bearer realm="orders", error="invalid_token"` | Bearer token đã gửi không hợp lệ/không được chấp nhận. | Thường đi cùng `401`. |
| `WWW-Authenticate: Bearer realm="orders", error="insufficient_scope", scope="orders:write"` | Phạm vi quyền token không đủ; server mô tả scope cần thiết nếu chính sách cho phép công bố. | Theo OAuth 2.0 Bearer, thường đi cùng **`403`**. |
| `WWW-Authenticate: Basic realm="internal-tools", charset="UTF-8"` | Yêu cầu HTTP Basic authentication. | Chỉ quảng bá nếu dịch vụ thật sự hỗ trợ Basic; phải dùng TLS để bảo vệ credential trên đường truyền. |

Server có thể đưa ra nhiều challenge nếu hỗ trợ nhiều cơ chế, nhưng cần tuân theo cú pháp của HTTP và tránh để client hiểu lầm rằng API hỗ trợ một scheme không tồn tại. **Không tự thêm Basic challenge** vào REST API chỉ vì một thư viện có sẵn khả năng Basic; trình duyệt có thể hiện hộp thoại đăng nhập ngoài ý muốn.

### 3.1. Những điều header này không làm

`WWW-Authenticate` không tự phát hành token, không tự làm mới phiên, không xác định người dùng thuộc role nào và không thay thế kiểm tra quyền tài nguyên. Đây là **mô tả phương thức xác thực cần đáp ứng**, không phải một cơ chế phân quyền.

Một số API dùng cookie/session hoặc tự xây xác thực có thể trả `401` mà không có challenge. Điều đó thường thấy trong thực tế nhưng **không phù hợp yêu cầu của HTTP đối với phản hồi 401**. Với API mới, nên thiết kế scheme/challenge rõ ràng; nếu giao diện web dựa vào chuyển hướng tới trang đăng nhập, cần phân biệt luồng điều hướng của trình duyệt với hợp đồng HTTP của API.

### 3.2. Phân biệt với proxy authentication

`407 Proxy Authentication Required` dùng khi **proxy** yêu cầu xác thực; cơ chế challenge tương ứng là `Proxy-Authenticate`. Server ứng dụng yêu cầu đăng nhập để truy cập đơn hàng dùng `401` + `WWW-Authenticate`, không dùng `407`.

## 4. Khi nào dùng 403 Forbidden?

Theo HTTP Semantics, `403 Forbidden` cho biết server hiểu request nhưng **từ chối thực hiện**. Nếu request đã có credential, `403` thường diễn đạt rằng credential đó không đủ để được phép làm hành động đang yêu cầu. Gửi lại **chính request với cùng credential** thường không giúp giải quyết.

Ví dụ người dùng có token hợp lệ cho `orders:read` nhưng cố thực hiện thao tác cần `orders:write`:

```http
PATCH /api/v1/orders/ord-1001 HTTP/1.1
Host: api.example.com
Authorization: Bearer <valid_read_only_access_token>
Content-Type: application/json

{"note": "Giao trước 17:00"}
```

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders", error="insufficient_scope", scope="orders:write"
Cache-Control: no-store
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/insufficient-permission",
  "title": "Insufficient permission",
  "status": 403,
  "detail": "Your account cannot perform this action."
}
```

Trong ví dụ này, `WWW-Authenticate` trên phản hồi `403` là **thông tin lỗi Bearer token theo RFC 6750**, giúp client biết thiếu scope; quy tắc HTTP bắt buộc challenge áp dụng cho **401**, không bắt buộc mọi 403 đều có header này.

Một ví dụ khác: user thuộc tenant A, có quyền `orders:read`, nhưng request lại nhắm vào đơn hàng thuộc tenant B. Token **không hỏng** và scope **không nhất thiết thiếu**; lỗi xảy ra ở **phân quyền theo tài nguyên/tenant**. API có thể trả `403`, hoặc `404` nếu muốn che giấu sự tồn tại của đơn hàng. Không nên tùy tiện gắn `error="insufficient_scope"` nếu vấn đề thực sự là ownership hoặc tenant boundary.

### 4.1. Các nguyên nhân 403 không liên quan trực tiếp đến scope

Một request có thể bị từ chối do:

- Người dùng không thuộc tenant hoặc workspace của tài nguyên.
- Vai trò đủ để đọc nhưng không được sửa, xóa hoặc xuất dữ liệu.
- Hành động nhạy cảm yêu cầu phê duyệt riêng hoặc chính sách phân tách nhiệm vụ.
- Chính sách của tổ chức hạn chế truy cập theo điều kiện thiết bị, mạng hoặc trạng thái tài khoản.
- Một quy tắc bảo vệ CSRF từ chối thao tác gửi từ trình duyệt; cần phân biệt với lỗi xác thực session.

Không có quy tắc bắt buộc rằng mọi lỗi nghiệp vụ đều là `403`. Ví dụ tạo đơn ở trạng thái đã khóa có thể phù hợp `409 Conflict` hơn; request không hợp lệ về cú pháp có thể cần `400 Bad Request`. Hãy chọn mã theo **nguyên nhân HTTP và hợp đồng nghiệp vụ**, không theo thói quen “cứ thất bại là 403”.

## 5. Bảng quyết định 401, 403 và các mã dễ nhầm

| Tình huống | Mã thường phù hợp | Lý do và lưu ý |
|---|---|---|
| Tài nguyên công khai, không cần đăng nhập | `200` hoặc mã thành công thích hợp | Không bắt buộc xác thực cho mọi endpoint. |
| API bảo vệ, client không gửi token | **`401`** + `WWW-Authenticate` | Chưa có credential hợp lệ; thiếu token không phải thiếu quyền đã xác minh. |
| Token sai chữ ký, hết hạn, bị từ chối, sai `iss`/`aud` | **`401`** + challenge (Bearer có thể kèm `invalid_token`) | Không nên biến token không hợp lệ thành 403. |
| Token hợp lệ nhưng thiếu scope cần thiết | **`403`**; Bearer có thể kèm `insufficient_scope` | Danh tính được xác thực nhưng hành động bị cấm. |
| Token hợp lệ, scope đủ nhưng actor không thuộc tenant của bản ghi | **`403`** hoặc **`404`** theo chính sách | Cần kiểm tra quyền ở service sở hữu dữ liệu; có thể che giấu sự tồn tại. |
| Tài nguyên không tồn tại | **`404`** | Không tự suy diễn là thiếu quyền. |
| Body JSON sai cấu trúc hoặc tham số request không hợp lệ | `400` (hoặc `422` tùy trường hợp đã định nghĩa) | Khác lỗi xác thực hoặc phân quyền. |
| Token hợp lệ, bản ghi được phép nhưng không thể sửa do xung đột phiên bản/trạng thái | `409 Conflict` | Lỗi trạng thái tài nguyên, không tự động là 403. |
| Vượt giới hạn số request | `429 Too Many Requests` | Có thể gửi `Retry-After`; không giải quyết bằng refresh token. |
| Proxy cần thông tin xác thực | `407` + `Proxy-Authenticate` | Khác bảo vệ tài nguyên của origin server. |
| API hay service tạm thời không sẵn sàng | `503 Service Unavailable` | Không báo thiếu quyền khi thật sự lỗi hạ tầng. |

Sơ đồ dưới đây là đường quyết định tham khảo cho **endpoint có yêu cầu xác thực**:

```mermaid
flowchart TD
  R[Client gửi request] --> P{Route có yêu cầu xác thực?}
  P -- Không --> Public[Xử lý tài nguyên công khai]
  P -- Có --> A{Credential hợp lệ?}
  A -- Không --> C401[401 + WWW-Authenticate]
  A -- Có --> S{Đủ scope / quyền hành động?}
  S -- Không --> C403[403; Bearer có thể báo insufficient_scope]
  S -- Có --> O{Được truy cập tài nguyên và tenant?}
  O -- Không --> H[403 hoặc 404 theo chính sách]
  O -- Có --> B[Thực thi nghiệp vụ]
  B --> Z[Trả trạng thái phù hợp với kết quả]
```

Sơ đồ đơn giản hóa thứ tự xử lý: thực tế có thể kiểm tra điều kiện sở hữu tài nguyên trong cùng truy vấn database, hoặc dùng chính sách quyết định quyền tập trung. Kết quả cuối vẫn phải đảm bảo **không đọc, sửa hay lộ dữ liệu không được cấp phép**.

## 6. Quy tắc Bearer token theo RFC 6750

OAuth 2.0 Bearer Token Usage (RFC 6750) định nghĩa cả cách dùng `Authorization: Bearer ...` và cách resource server mô tả lỗi trong `WWW-Authenticate`.

| Tình trạng | HTTP status theo ngữ cảnh thông dụng | Challenge phù hợp |
|---|---|---|
| Chưa có thông tin xác thực | `401` | `Bearer realm="orders"`. Khi client chưa gửi token, thường không thêm mã `error`. |
| Token được gửi nhưng không hợp lệ hoặc đã hết hạn | `401` | `Bearer realm="orders", error="invalid_token"`. |
| Token hợp lệ nhưng thiếu scope | `403` | `Bearer realm="orders", error="insufficient_scope", scope="orders:write"` khi được phép công bố scope. |
| Request truyền token sai định dạng hoặc vi phạm cách gửi token | Thường `400` với `invalid_request` theo lỗi cụ thể RFC 6750 | Không đánh đồng lỗi định dạng request với credential hết hạn. |

Ba giá trị lỗi tiêu biểu là `invalid_request`, `invalid_token` và `insufficient_scope`. Có thể kèm `error_description` hoặc `error_uri` với cú pháp hợp lệ. Mô tả phải ngắn gọn và **không tiết lộ** token, bí mật, cấu hình nội bộ hay thông tin tài nguyên mà client không được phép biết.

Điều quan trọng là **scope không phải toàn bộ chính sách phân quyền**. Token mang `orders:read` vẫn không được phép đọc bất kỳ đơn hàng nào trên hệ thống. Dịch vụ nghiệp vụ phải kiểm tra đối tượng, chủ sở hữu, membership, tenant, trạng thái và chính sách liên quan.

### 6.1. JWT là một định dạng token, không phải cơ chế phân quyền

Access token có thể là JWT hoặc opaque token. Khi chấp nhận JWT, API thường cần kiểm tra:

- Chữ ký và thuật toán được cho phép, chọn khóa xác minh từ nguồn tin cậy.
- `iss` (issuer), `aud` (audience), `exp` (expiry), `nbf` (not before) và các claim bắt buộc theo hợp đồng.
- Scope/authority và bối cảnh client, tenant hoặc policy nếu hệ thống sử dụng.
- Chính sách thu hồi, thay đổi thành viên hoặc tắt tài khoản với độ trễ chấp nhận được.

Nếu token sai chữ ký hoặc dành cho API khác, **không xác thực thành công rồi trả 403**; token phải bị từ chối ở bước xác thực. Nếu token hợp lệ nhưng quyền không đủ, phân quyền mới quyết định `403`/`404`. Việc giải mã được payload JWT không chứng minh chữ ký hợp lệ.

## 7. Một luồng request được xử lý như thế nào?

```mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway / Security Filter
    participant S as Order Service
    C->>G: GET /api/v1/orders/ord-1001 (không token)
    G-->>C: 401 + WWW-Authenticate: Bearer
    Note over C: Client lấy access token qua luồng hợp lệ
    C->>G: GET + Authorization: Bearer <token hợp lệ>
    G->>G: Xác minh token, issuer, audience, expiry
    G->>S: Chuyển danh tính/ngữ cảnh đã xác minh an toàn
    S->>S: Kiểm tra scope, membership, quyền đơn hàng
    alt Không có quyền
      S-->>C: 403 hoặc 404
    else Được phép
      S-->>C: 200 + dữ liệu đơn hàng
    end
```

Luồng có thể không cần gateway riêng: cùng các bước kiểm tra có thể nằm trong ứng dụng Java/Spring. Sơ đồ **không** ngụ ý phải đăng nhập lại cho từng request. Access token có thể được lấy từ một luồng đăng nhập trước đó; cơ chế refresh phải tuân theo chính sách của Identity Provider.

### 7.1. Trường hợp client gửi Bearer token của tenant A để đọc đơn của B

Giả sử user đã đăng nhập đúng, token có `orders:read`, nhưng đơn `ord-2002` thuộc tenant B trong khi người dùng chỉ thuộc A. Server không được tin vào `tenantId=B` do client tự thêm trong URL, header hoặc JSON. Service cần ràng buộc truy vấn với membership đã xác minh và kiểm tra quyền trên chính đơn hàng.

Hai hợp đồng hợp lệ:

- `403 Forbidden`: công bố rõ yêu cầu bị từ chối do không có quyền, nếu chính sách cho phép.
- `404 Not Found`: không xác nhận tài nguyên có tồn tại; hữu ích khi cần hạn chế lộ dữ liệu thông qua ID đoán được.

Nếu chọn 404 để che giấu, cần nhất quán ở body, response size, đường liệt kê, search, cache và các tín hiệu khác. **Không dùng 404 thay cho kiểm tra quyền**; hệ thống vẫn phải từ chối thật sự việc đọc dữ liệu.

## 8. Dùng mã trạng thái đúng cho ứng dụng web, mobile và máy gọi API

### 8.1. Ứng dụng web

Với SPA hoặc frontend gọi JSON API bằng Bearer token, `401` là tín hiệu để kiểm tra tình trạng xác thực, thực hiện tối đa một luồng refresh/đăng nhập phù hợp rồi gửi lại yêu cầu khi an toàn. Với server-rendered web app dùng cookie/session, trình duyệt có thể được chuyển hướng tới trang đăng nhập trong **luồng điều hướng trang**; nhưng nếu endpoint được công bố là JSON API thì trả HTML login với `200` hoặc redirect âm thầm thường làm client khó xử lý.

Với xác thực dựa trên cookie, cần kiểm tra CSRF cho thao tác ghi, cookie `Secure`/`HttpOnly`/`SameSite` theo kiến trúc và bảo vệ phiên. Mã 403 do CSRF failure cần được phân tích khác với 403 do thiếu scope; log phía server nên có mã lý do nội bộ phù hợp.

### 8.2. Ứng dụng mobile

Ứng dụng mobile là public client, thường dùng Authorization Code + PKCE để lấy token. Khi nhận 401 do token hết hạn, có thể làm mới token theo cơ chế IdP hỗ trợ; khi nhận 403 do thiếu quyền, nên đưa ra hướng dẫn truy cập phù hợp, tránh tự xóa phiên hợp lệ. Trên mạng di động không ổn định, cần tránh vừa retry lỗi mạng vừa refresh token nhiều lần cho một thao tác ghi.

### 8.3. Server-to-server

Một service gọi API bằng OAuth client credentials hoặc workload identity cũng cần phân biệt:

- `401`: credential không hợp lệ hoặc token dành cho audience khác; kiểm tra quá trình cấp, lưu và xoay vòng token.
- `403`: service principal không được cấp scope hoặc quyền với tài nguyên đích; cần sửa policy/cấu hình cấp quyền theo quy trình, không retry vô hạn.

Không nên cấp scope quản trị toàn hệ thống chỉ để né 403. Ưu tiên quyền tối thiểu và chia phạm vi theo hành động/tài nguyên.

## 9. Cấu trúc phản hồi lỗi nhất quán với Problem Details

RFC 9457 định nghĩa định dạng **Problem Details** cho API HTTP, thường sử dụng media type `application/problem+json`. Có thể dùng chung cấu trúc `type`, `title`, `status`, `detail` và `instance` để client phân loại lỗi rõ ràng.

Ví dụ `403` do tài nguyên không thuộc quyền:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-ID: req-7c15

{
  "type": "https://api.example.com/problems/access-denied",
  "title": "Access denied",
  "status": 403,
  "detail": "This action is not allowed.",
  "instance": "/api/v1/orders/ord-2002",
  "code": "ACCESS_DENIED"
}
```

`code` là **extension do API tự định nghĩa**, không phải field bắt buộc của RFC 9457. Một số nguyên tắc:

1. HTTP status thực tế là nguồn thông tin chính; field `status` trong body phải nhất quán với nó khi có mặt.
2. `type` nên định danh loại lỗi ổn định; `title` ngắn gọn; `detail` hữu ích nhưng không lộ thông tin nhạy cảm.
3. `X-Request-ID` hoặc trace ID hỗ trợ tra cứu log; giá trị phải do hệ thống kiểm soát và không tiết lộ bí mật.
4. Không gửi danh sách role nội bộ, tên policy, ID tenant khác hoặc chi tiết kiểm tra chữ ký cho người gọi không có quyền.
5. Ưu tiên mã lỗi ứng dụng ổn định để client quyết định hiển thị; không bắt client phân tích chuỗi `detail`.

`WWW-Authenticate` vẫn cần xuất hiện ở response `401` dù body đã dùng Problem Details.

## 10. Ví dụ triển khai với Spring Boot và Spring Security

Ví dụ dùng **Spring Boot 3 / Spring Security 6** theo phong cách cấu hình hiện đại. Ứng dụng là REST API **stateless**, chỉ chấp nhận Bearer token trong `Authorization` và không đăng nhập bằng cookie. Cần các dependency tương ứng với Web, Security và OAuth2 Resource Server.

### 10.1. Cấu hình Resource Server

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
```

`issuer-uri` giúp Resource Server khám phá cấu hình và xác minh issuer theo thiết lập framework. **Phải xác minh audience** thích hợp cho chính API qua cấu hình/validator tương ứng nếu cấu hình mặc định chưa kiểm tra `aud`. Ứng dụng thật cũng cần cấu hình HTTPS, công khai endpoint phù hợp và chính sách khóa/thu hồi token.

Ví dụ cấu hình filter chain:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/v1/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.PATCH, "/api/v1/orders/**")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
```

**Giới hạn của ví dụ:** tắt CSRF chỉ hợp lý với API stateless nhận credential qua `Authorization`, không sử dụng cookie tự động đính kèm để xác thực các request ghi. Nếu ứng dụng cũng đăng nhập bằng cookie/session, phải thiết kế lại CSRF protection thay vì sao chép dòng cấu hình đó. Trong Spring Security, prefix `SCOPE_` là quy ước thường dùng khi chuyển claim scope thành authority; cần kiểm tra ánh xạ phù hợp với token do IdP phát hành.

Trong luồng cấu hình Resource Server thông dụng:

- Không có Bearer token hoặc token không hợp lệ: tầng xác thực phản hồi `401` kèm Bearer challenge.
- Token hợp lệ nhưng không có `SCOPE_orders:write` khi gọi PATCH: tầng phân quyền trả `403`; handler cho Bearer có thể đưa `insufficient_scope` vào challenge.
- Token có scope đọc vẫn phải qua kiểm tra quyền trên từng đơn hàng trong service. **Không thể chỉ dựa vào request matcher** để bảo vệ tenant và ownership.

### 10.2. Kiểm tra quyền tài nguyên ở lớp nghiệp vụ

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/v1/orders/{orderId}")
    public OrderDto getOrder(
            @PathVariable String orderId,
            JwtAuthenticationToken authentication) {
        String subject = authentication.getName();

        // findVisibleTo phải kiểm tra membership, tenant và quyền trên order.
        return orderService.findVisibleTo(subject, orderId)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
```

`OrderService` và `OrderDto` ở đây là các abstraction minh họa của ứng dụng. Trong triển khai thực tế, hàm `findVisibleTo` phải dựa trên danh tính đã được xác minh và dữ liệu quyền tin cậy; có thể dùng truy vấn giới hạn tenant hoặc chính sách tập trung, rồi quyết định 404 nếu không tìm thấy **hoặc không được công bố**. Không lấy `tenantId` trong body/header do client tự gửi để lọc dữ liệu.

Không nên viết code xử lý token thủ công trong từng controller khi framework đã có filter xác thực. Cũng không nên dùng `try/catch (Exception)` toàn cục rồi luôn trả 401: điều này che giấu lỗi database, lỗi lập trình và lỗi nghiệp vụ.

### 10.3. Phân biệt AuthenticationEntryPoint và AccessDeniedHandler

Trong Spring Security, hai điểm mở rộng thường gặp:

| Thành phần | Trường hợp | Mục đích |
|---|---|---|
| `AuthenticationEntryPoint` | Cần bắt đầu quá trình xác thực hoặc token không hợp lệ | Tạo phản hồi `401` kèm challenge phù hợp. |
| `AccessDeniedHandler` | Yêu cầu bị từ chối sau khi đã có ngữ cảnh bảo mật phù hợp | Tạo phản hồi `403`; với Bearer có thể trả thông tin `insufficient_scope`. |

Nếu dùng Resource Server, ưu tiên cơ chế mặc định Bearer của Spring Security trước khi tùy biến. Khi muốn bổ sung `application/problem+json`, phải **giữ nguyên ngữ nghĩa mã trạng thái và header challenge**, đồng thời kiểm tra hành vi thực tế của entry point/handler. Một exception handler tùy biến không đúng thứ tự filter có thể làm mất `WWW-Authenticate`.

## 11. Mô tả hợp đồng 401/403 trong OpenAPI

Khi công bố API, nên mô tả scheme xác thực và hai trường hợp lỗi riêng biệt, thay vì chỉ ghi “authentication error”.

```yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /api/v1/orders/{orderId}:
    get:
      summary: Read an order visible to the caller
      security:
        - bearerAuth: []
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Authorized order representation
        "401":
          description: Missing or invalid access token
          headers:
            WWW-Authenticate:
              description: Bearer authentication challenge
              schema:
                type: string
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"
        "403":
          description: The caller is not allowed to access the resource
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"
        "404":
          description: Order is absent or hidden by access policy
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
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
```

`bearerFormat: JWT` chỉ là gợi ý tài liệu cho công cụ, không buộc mọi Bearer token phải là JWT. Nếu API thật có OAuth 2.0 authorization flows và scopes được mô tả trong OpenAPI, có thể dùng `type: oauth2` cùng flows và scope tương ứng. Trong thiết kế trên, REST API chấp nhận Bearer access token và minh họa phản hồi khi token thiếu hoặc quyền không đủ; ràng buộc chi tiết trên tài nguyên vẫn được triển khai phía server.

Nếu dùng generator cho client, kiểm tra rằng SDK giữ khả năng đọc HTTP status và response headers; không chuyển tất cả `4xx` thành cùng một exception không phân loại.

## 12. Ứng dụng client nên phản ứng thế nào?

Một chiến lược client thực tế có thể được mô tả như sau:

```text
Nhận response:
  2xx/3xx theo hợp đồng  -> tiếp tục luồng tương ứng
  401                    -> nếu có refresh hợp lệ và chưa thử:
                              làm mới token một lần, đồng bộ refresh
                              gửi lại request nếu an toàn
                           nếu không:
                              yêu cầu đăng nhập lại
  403                    -> dừng tự động retry vì thiếu quyền
                           hiển thị thông báo phù hợp hoặc hướng dẫn xin quyền
  404                    -> hiển thị không tìm thấy/không được công bố
  429                    -> xử lý Retry-After/backoff khi phù hợp
  5xx                    -> theo chính sách retry và idempotency của thao tác
```

**Không refresh token trên mọi 403.** Token có thể hoàn toàn hợp lệ nhưng thiếu scope hoặc không thuộc tenant. Refresh liên tục không làm quyền thay đổi. **Không lặp vô hạn 401.** Một trình duyệt có nhiều request đồng thời nên dùng cơ chế single-flight/khóa refresh để tránh hàng chục request cùng làm mới và ghi đè token mới.

Với `POST`/`PATCH` có side effect, cần đánh giá idempotency trước khi replay. Nếu gửi request lần đầu đã tạo đơn nhưng client mất kết nối trước khi nhận response, retry có thể tạo trùng; khi phù hợp, sử dụng idempotency key và chính sách xử lý ở server. Với lỗi xác thực bị chặn trước khi thực thi nghiệp vụ, retry sau refresh có thể hợp lý, nhưng không được giả định mọi tầng trung gian đều không có tác dụng phụ trong mọi trường hợp.

### 12.1. CORS và việc đọc header trong trình duyệt

Với API khác origin, trình duyệt áp dụng CORS cho cả phản hồi lỗi. Nếu CORS cấu hình sai, JavaScript có thể thấy lỗi CORS/network thay vì đọc được response status và Problem Details. Nếu frontend cần đọc giá trị `WWW-Authenticate`, server phải cân nhắc công khai header đó qua:

```http
Access-Control-Expose-Headers: WWW-Authenticate
```

Đồng thời phải cho phép đúng origin, phương thức và request headers cần thiết. CORS **không phải xác thực hoặc phân quyền**; mở `Access-Control-Allow-Origin` không cấp quyền đọc đơn hàng nếu server đã kiểm tra auth đúng, và chặn origin cũng không bảo vệ được API trước client ngoài trình duyệt.

### 12.2. Vấn đề cache và log

Không nên cache công khai phản hồi chứa thông tin riêng tư hoặc trạng thái quyền theo user/tenant. Với lỗi xác thực và phân quyền nhạy cảm, `Cache-Control: no-store` giúp giảm nguy cơ tái sử dụng sai response; nếu có cache theo danh tính, phải cấu hình khóa cache và quy tắc Authorization chặt chẽ. Không log raw `Authorization` header, cookie phiên, refresh token hoặc thông điệp lỗi chứa thông tin bí mật.

## 13. Kiểm thử bằng HTTP và Spring Security

### 13.1. Kiểm tra thủ công qua curl

```bash
# Không gửi credential: kỳ vọng 401 và WWW-Authenticate có Bearer.
curl -i https://api.example.com/api/v1/orders/ord-1001

# Credential không hợp lệ: kỳ vọng 401, Bearer invalid_token.
curl -i \
  -H "Authorization: Bearer invalid-example-token" \
  https://api.example.com/api/v1/orders/ord-1001

# Credential hợp lệ nhưng thiếu quyền: kỳ vọng 403 theo policy.
# Trong terminal thật, lấy token từ cơ chế bảo mật được phép.
curl -i \
  -H "Authorization: Bearer <valid_read_only_token>" \
  -X PATCH \
  -H "Content-Type: application/json" \
  -d '{"note":"updated"}' \
  https://api.example.com/api/v1/orders/ord-1001
```

Ví dụ dùng URL và token giả định, không phải API thật. Không đưa token thật vào lịch sử lệnh, log chia sẻ hoặc tài liệu; khi chạy kiểm thử cần quản lý credential theo môi trường.

### 13.2. Ma trận test đầu vào và đầu ra

| Mã test | Đầu vào | HTTP status mong đợi | Header/body cần xác minh |
|---|---|---|---|
| AUTH-01 | Không có Authorization trên endpoint bảo vệ | `401` | Có `WWW-Authenticate: Bearer...`; body lỗi không lộ dữ liệu. |
| AUTH-02 | Token hết hạn | `401` | Có challenge và `invalid_token` nếu dùng quy ước Bearer. |
| AUTH-03 | Token sai chữ ký | `401` | Không được thực thi nghiệp vụ; không trả nguyên nhân mật mã nhạy cảm. |
| AUTH-04 | Token đúng chữ ký nhưng sai audience | `401` | Không chấp nhận token dành cho API khác. |
| AUTH-05 | Token hợp lệ có `orders:read` đọc đơn được phép | `200` | Body đúng dữ liệu của actor/tenant. |
| AUTH-06 | Token chỉ có `orders:read` gọi PATCH cần `orders:write` | `403` | Có thể kèm `insufficient_scope`; dữ liệu không đổi. |
| AUTH-07 | Token có `orders:read` nhưng truy cập đơn của tenant khác | `403` hoặc `404` | Theo contract; không lộ nội dung/metadata khác tenant. |
| AUTH-08 | User mất membership tenant sau khi token được cấp | Theo chính sách thu hồi | Không cho truy cập quá thời hạn cho phép; test cache/TTL quyền. |
| AUTH-09 | Route công khai gọi không token | Mã thành công phù hợp | Không nhầm mọi request thiếu token thành 401. |
| AUTH-10 | Header có token sai định dạng hoặc lặp phương thức truyền token | `400`/`401` theo lỗi và RFC 6750 | Kiểm tra hợp đồng parsing và challenge; không tạo lỗi 500. |
| AUTH-11 | Proxy yêu cầu xác thực | `407` | Có `Proxy-Authenticate` tại proxy; không gắn nhầm origin server. |
| AUTH-12 | CORS preflight và response 401/403 trên web app | Theo endpoint/cấu hình CORS | Client đọc được status/error khi origin được phép; không tạo CORS bypass. |

Khi kiểm thử 403 và 404, cần xác minh **trạng thái dữ liệu sau yêu cầu**, không chỉ nhìn HTTP status. Một request có thể bị trả 403 sau khi side effect đã xảy ra nếu phân quyền được đặt sai chỗ; đây là lỗi nghiêm trọng.

### 13.3. Ví dụ MockMvc

Nếu dùng `spring-security-test`, có thể viết test cho hành vi filter:

```java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderApiSecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void anonymousRequestGets401WithChallenge() throws Exception {
        mvc.perform(get("/api/v1/orders/ord-1001"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE, containsString("Bearer")));
    }

    @Test
    void validTokenWithoutRequiredScopeGets403() throws Exception {
        mvc.perform(get("/api/v1/orders/ord-1001")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_profile:read"))))
            .andExpect(status().isForbidden());
    }
}
```

`jwt()` trong Spring Security Test **tạo ngữ cảnh JWT giả lập**, hữu ích để kiểm thử phân quyền nhưng **không tự chứng minh** rằng hệ thống production thực sự xác minh chữ ký, issuer và audience đúng. Cần test tích hợp/contract riêng với token sai chữ ký, sai audience, hết hạn và cấu hình decoder thực. Tương tự, test thiếu scope ở filter không thay thế test từ chối đọc dữ liệu khác tenant trong Order Service.

## 14. Những lỗi thiết kế thường gặp

1. **Trả 403 khi hết hạn token:** client không biết cần làm mới phiên, dễ hiển thị “không có quyền” sai bản chất. Nên trả 401 kèm challenge phù hợp.
2. **Trả 401 khi thiếu role hoặc không sở hữu bản ghi:** client liên tục làm mới token nhưng vẫn bị từ chối; dùng 403 hoặc 404 theo chính sách.
3. **Trả 401 không có WWW-Authenticate:** bỏ mất challenge mà HTTP yêu cầu; client/gateway hoặc công cụ tiêu chuẩn khó nhận biết cơ chế xác thực.
4. **Dùng 403 để che mọi lỗi server:** backend kết nối database thất bại nhưng ghi nhận “forbidden” khiến vận hành không thấy sự cố. Phân loại lỗi đúng nguyên nhân.
5. **Nhầm 401/403 với CORS:** frontend không đọc được response do CORS thiếu cấu hình, hoặc 403 do CSRF, rồi kết luận sai rằng Bearer token thiếu quyền. Kiểm tra cả network response, server log và auth flow.
6. **Chỉ kiểm tra scope tại gateway:** token có scope đọc nhưng tự đổi ID truy cập tài nguyên tenant khác. Kiểm tra quyền đối tượng và tenant tại service/data layer.
7. **Đưa nội dung nhạy cảm vào `error_description`:** vô tình tiết lộ cấu hình verifier, danh sách tenant, token hoặc policy nội bộ. Dùng mã lỗi ổn định và thông báo tổng quát.
8. **Auto-refresh trên mọi 4xx:** gây bão request, retry thao tác ghi không an toàn và che giấu vấn đề phân quyền. Phân biệt lỗi trước khi thử lại.
9. **OpenAPI chỉ mô tả 200:** client generator bỏ qua contract cho 401/403, không kiểm tra header và không có phương án xử lý lỗi rõ ràng.
10. **Đồng nhất 403 với đã đăng nhập:** 403 biểu diễn server từ chối yêu cầu; có những chính sách cấm áp dụng ngay cả khi không có danh tính. Cần đọc semantics và context của endpoint.

## 15. Bài tập thực hành: thiết kế và kiểm chứng hợp đồng lỗi

### Đề bài

Một REST API quản lý tài liệu có ba quyền: `documents:read`, `documents:write`, `documents:share`. Mỗi tài liệu thuộc một workspace. User Lan là Viewer trong workspace A; user Minh là Editor trong workspace B. API có:

- `GET /api/v1/documents/{documentId}`: xem tài liệu.
- `PATCH /api/v1/documents/{documentId}`: sửa nội dung.
- `POST /api/v1/documents/{documentId}/shares`: cấp quyền chia sẻ.

Lúc đầu server trả `403` cho mọi trường hợp token hết hạn, token thiếu scope và truy cập tài liệu khác workspace. Frontend cứ gặp 403 là chuyển người dùng đến trang đăng nhập; sau khi đăng nhập lại vẫn không xem được tài liệu của workspace khác.

**Yêu cầu:**

1. Thiết kế lại hợp đồng `401` và `403` (cùng chính sách `404` để che giấu ID nếu cần), nêu rõ lý do mỗi mã.
2. Viết HTTP response có `WWW-Authenticate` cho trường hợp không có token, token hết hạn và thiếu scope `documents:share`.
3. Chỉ ra nơi kiểm tra scope và nơi kiểm tra membership/ownership; nếu dùng gateway, service vẫn cần kiểm tra điều gì?
4. Đề xuất cách frontend phân biệt thiếu xác thực, thiếu quyền và tài nguyên không công bố; quy tắc refresh và retry.
5. Viết tối thiểu sáu testcase (gồm positive/negative), test trạng thái dữ liệu sau request PATCH/POST.
6. Mô tả response lỗi bằng OpenAPI và xác minh header tương ứng.

### Gợi ý đáp án

| Request | Kết quả gợi ý | Tại sao |
|---|---|---|
| Không token gọi GET tài liệu cần bảo vệ | `401` + `WWW-Authenticate: Bearer realm="documents"` | Không có thông tin xác thực hợp lệ. |
| Token hết hạn gọi PATCH | `401` + Bearer `error="invalid_token"` | Token không được chấp nhận trước bước phân quyền. |
| Token hợp lệ có read nhưng gọi endpoint share | `403` + Bearer `error="insufficient_scope"`, có thể kèm `scope="documents:share"` | Thiếu quyền hành động. |
| Lan có read nhưng gọi tài liệu thuộc workspace B | `403` hoặc `404` theo policy | Scope không tự cấp quyền trên tài liệu cụ thể. |
| Minh sửa tài liệu thuộc B khi có write và đủ điều kiện nghiệp vụ | `200` hoặc mã thành công phù hợp | Đã vượt cả xác thực, scope và kiểm tra quyền tài nguyên. |
| ID tài liệu không tồn tại | `404` | Không có tài nguyên để trả. |

Kiểm tra kết quả không dừng ở mã HTTP: tài liệu của B **không bị thay đổi** bởi request của Lan; hoạt động chia sẻ không tạo quyền ngầm cho user khác; log audit không công bố dữ liệu của workspace khác.

## 16. Checklist trước khi phát hành REST API

- [ ] Mỗi endpoint biết rõ có yêu cầu xác thực hay là tài nguyên công khai.
- [ ] 401 dùng khi không có credential hợp lệ, kèm ít nhất một `WWW-Authenticate` challenge phù hợp.
- [ ] Với Bearer token, phân biệt `invalid_token` (thường 401), `insufficient_scope` (thường 403) và `invalid_request` theo ngữ cảnh RFC 6750.
- [ ] 403 dùng cho hành động bị từ chối theo quyền/chính sách; không kích hoạt refresh token vô hạn.
- [ ] Có chính sách rõ ràng cho trường hợp dùng 404 để không tiết lộ sự tồn tại của tài nguyên.
- [ ] Xác minh chữ ký, issuer, audience, thời hạn và chính sách token thực tế; scope không thay thế quyền trên tài nguyên và tenant.
- [ ] Lỗi được biểu diễn nhất quán (ví dụ Problem Details), không rò thông tin nhạy cảm.
- [ ] OpenAPI mô tả security scheme, 401/403/404, phản hồi lỗi và `WWW-Authenticate`.
- [ ] Frontend/mobile/backend client có logic refresh một lần, retry an toàn, không làm mới token trên mọi 403.
- [ ] Đã kiểm tra response header, CORS, cache và quyền dữ liệu bằng test tích hợp, không chỉ mock authorization.
- [ ] Hệ thống giám sát tách tỷ lệ 401/403, lỗi xác thực, lỗi phân quyền và 5xx để phát hiện sai cấu hình hoặc tấn công.

## 17. Tài liệu tiêu chuẩn để đối chiếu

- **RFC 9110 — HTTP Semantics:** định nghĩa mã trạng thái và yêu cầu `WWW-Authenticate` trên phản hồi 401, cùng semantics của 403/404/407. Xem https://www.rfc-editor.org/rfc/rfc9110.html.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** định nghĩa Bearer challenge và các lỗi `invalid_request`, `invalid_token`, `insufficient_scope`. Xem https://www.rfc-editor.org/rfc/rfc6750.html.
- **RFC 9457 — Problem Details for HTTP APIs:** định dạng lỗi máy đọc được với `application/problem+json`. Xem https://www.rfc-editor.org/rfc/rfc9457.html.
- **OpenAPI Specification 3.1:** cấu trúc `securitySchemes` và mô tả các response/header. Xem https://spec.openapis.org/oas/v3.1.0.

**Điểm cần nhớ:** `401` nghĩa là **chưa có credential hợp lệ cho tài nguyên được bảo vệ** và phải đi kèm challenge `WWW-Authenticate`; `403` nghĩa là **server từ chối thực hiện** yêu cầu, thường do thiếu quyền dù token đã hợp lệ. Với hệ thống REST API an toàn, lựa chọn mã đúng chỉ là bước đầu: phải xác minh token, kiểm tra scope, quyền trên tài nguyên/tenant, bảo vệ dữ liệu và kiểm thử cả hành vi client.
