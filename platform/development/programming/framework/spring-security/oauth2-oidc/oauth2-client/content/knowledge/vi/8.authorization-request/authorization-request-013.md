# 8.13. Giới hạn dữ liệu, thông tin nhạy cảm và URL trong authorization request

Trong **Spring Security OAuth 2.0/OIDC Client**, bước bắt đầu đăng nhập thường là một **authorization request**: Spring tạo URL đến Authorization Endpoint của nhà cung cấp danh tính, rồi trả HTTP redirect để trình duyệt mở URL đó. Request có thể chứa `client_id`, `redirect_uri`, `scope`, `state`, `nonce` (OIDC), `code_challenge` (PKCE) và các tham số do ứng dụng tùy biến.

Vì authorization request đi qua **trình duyệt**, mọi dữ liệu được đưa vào URL cần được xem xét theo hai chiều: **bảo mật thông tin** và **giới hạn kỹ thuật về chiều dài request URL**. Một URL đủ dài có thể bị web server, reverse proxy, trình duyệt hoặc WAF từ chối. Một URL chứa dữ liệu nhạy cảm có thể xuất hiện trong lịch sử truy cập, log, hệ thống giám sát, công cụ hỗ trợ hoặc Referer tùy môi trường.

Mục tiêu của bài học là hiểu dữ liệu nào nên xuất hiện trong authorization request, dữ liệu nào tuyệt đối không nên được đưa lên URL, cách giới hạn kích thước, và cách Spring Security giữ an toàn cho flow khi ứng dụng cần thêm tham số tùy chỉnh.

## 1. Authorization request là gì và được truyền qua đâu?

Với Authorization Code Flow, Spring Security có thể bắt đầu đăng nhập qua endpoint nội bộ:

```text
GET https://app.example.test/oauth2/authorization/company
```

Spring dùng `ClientRegistration` để tạo một authorization request rồi chuyển hướng trình duyệt sang Authorization Endpoint của IdP:

```http
HTTP/1.1 302 Found
Location: https://login.example.test/oauth2/authorize?response_type=code&client_id=web-client&redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&scope=openid%20profile%20email&state=EXAMPLE_RANDOM_STATE&code_challenge=EXAMPLE_PKCE_CHALLENGE&code_challenge_method=S256
```

Nếu là OIDC, request còn có thể chứa `nonce` và các tham số OIDC khác tùy flow. URL trên chỉ dùng ví dụ; các giá trị mang tiền tố `EXAMPLE_` không phải mã ngẫu nhiên đủ an toàn để dùng trong ứng dụng thật.

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Trình duyệt
    participant C as Spring Security Client
    participant AS as Authorization Server / OP

    U->>B: Chọn đăng nhập
    B->>C: GET /oauth2/authorization/company
    C->>C: Tạo state, nonce/PKCE khi áp dụng
    C->>C: Lưu authorization request để đối chiếu
    C-->>B: 302 Location: Authorization Endpoint?...
    B->>AS: GET /authorize?client_id=...&scope=...&state=...
    AS->>U: Xác thực, xác nhận quyền khi cần
    AS-->>B: 302 về Redirect URI?code=...&state=...
    B->>C: GET /login/oauth2/code/company?code=...&state=...
    C->>C: Kiểm tra state/flow đã lưu
    C->>AS: POST Token Endpoint với code và verifier nếu có PKCE
    AS-->>C: Token response
    C->>C: Xác minh OIDC, tạo Authentication
```

Các điểm cần phân biệt:

- **Authorization request URL** được gửi qua front channel của trình duyệt. Query string là phần có thể quan sát được ở nhiều lớp của hệ thống.
- **Redirect URI** là callback của Client, chẳng hạn `https://app.example.test/login/oauth2/code/company`. URL này được đưa vào authorization request dưới dạng tham số `redirect_uri`.
- **Authorization response URL** là URL callback sau khi IdP xử lý, thường có `code` và `state`. Nó cũng cần được bảo vệ khỏi việc log hoặc chuyển tiếp không kiểm soát.
- **Token request** được Spring gửi trực tiếp tới Token Endpoint qua back channel. `client_secret` và `code_verifier` (nếu có) thuộc kênh này; không được chuyển lên URL trong trình duyệt.

Không phải mọi dữ liệu xuất hiện trong authorization URL đều là bí mật. Tuy nhiên, **một giá trị không được coi là secret vẫn có thể cần bảo vệ khỏi lộ ngoài ý muốn**, ví dụ `state`, `nonce` hoặc một tham số liên quan danh tính.

## 2. Phân loại dữ liệu trước khi thêm vào authorization URL

| Dữ liệu / tham số | Có thường xuất hiện ở authorization request? | Có phải secret? | Nguyên tắc |
|---|---|---|---|
| `response_type=code` | Có | Không | Chỉ định Authorization Code Flow |
| `client_id` | Có | Không | Định danh Client, không phải client secret |
| `redirect_uri` | Có | Không phải secret nhưng ảnh hưởng an toàn | Phải khớp callback được IdP cho phép |
| `scope` | Có | Thường không | Xin đúng scope tối thiểu; tên scope vẫn có thể bộc lộ mục đích truy cập |
| `state` | Có | Không phải chứng chỉ xác thực, nhưng là giá trị chống CSRF | Phải ngẫu nhiên/khó đoán, kiểm tra khi callback; không nhét PII hoặc secret |
| `nonce` (OIDC) | Thường có khi flow áp dụng | Không phải secret token | Giá trị ngẫu nhiên liên kết ID Token với yêu cầu; không tái sử dụng |
| `code_challenge` | Có khi dùng PKCE | Không phải `code_verifier` | Dùng S256; challenge có thể qua front channel |
| `code_challenge_method=S256` | Có khi dùng PKCE | Không | Không tự hạ xuống `plain` |
| `prompt`, `max_age`, `ui_locales` | Tùy nhu cầu OIDC | Thường không | Chỉ thêm khi provider hỗ trợ |
| `login_hint` | Có thể có | Có thể là **dữ liệu cá nhân** | Tránh hoặc giảm dùng; cân nhắc lộ email/username trong URL |
| `claims` | Tùy OIDC/provider | Có thể tiết lộ yêu cầu nhạy cảm | Dễ tăng URL; không nhúng dữ liệu cá nhân không cần thiết |
| `id_token_hint` | Một số flow OIDC | **Nhạy cảm**, vì có thể là ID Token thật | Không tự ý đưa vào URL; cần cơ chế truyền và bảo vệ phù hợp theo provider |
| `client_secret` | **Không** | **Có** | Không gửi trong authorization URL; chỉ dùng ở kênh xác thực Client phù hợp |
| `code_verifier` | **Không** | **Có/giữ bí mật trong flow** | Lưu phía Client, gửi tại Token Endpoint |
| `access_token`, `refresh_token` | **Không** với Authorization Code Flow thông thường | **Có** | Không đặt trong URL hay tham số bổ sung |
| Mật khẩu, OTP, API key, session cookie | **Không** | **Có** | Không đưa vào query, fragment hoặc dữ liệu chuyển hướng |
| Địa chỉ, số điện thoại, mã định danh cá nhân | Không nên | **PII** | Không đưa vào authorization request khi không thật sự cần |

**PII** (*personally identifiable information*) là dữ liệu có thể liên quan đến một người, như email, số điện thoại, địa chỉ hoặc mã định danh. Không phải mọi giá trị PII đều là secret, nhưng việc đặt chúng lên URL có thể vi phạm nguyên tắc tối thiểu hóa dữ liệu và mở rộng phạm vi truy cập trong log.

Một lỗi đặc biệt nguy hiểm là nhầm **`client_id`** với **`client_secret`**. `client_id` thường phải gửi trong authorization request; `client_secret` không được lộ tại đó. Tương tự, `code_challenge` được gửi ở authorization request, còn `code_verifier` chỉ xuất hiện ở bước đổi authorization code lấy token.

## 3. URL không phải nơi an toàn để chứa dữ liệu bí mật

HTTPS mã hóa lưu lượng **trong quá trình truyền trên mạng** giữa các bên, nhưng không biến URL thành một kho lưu trữ bí mật. Tùy kiến trúc, URL có thể được ghi nhận ở:

- **Lịch sử và thanh địa chỉ trình duyệt**; người dùng có thể sao chép/chia sẻ đường dẫn hoặc gửi ảnh chụp màn hình.
- **Reverse proxy, load balancer, gateway, WAF**: access log thường chứa HTTP request target hoặc đường dẫn có query.
- **Web server/IdP**: authorization endpoint có thể ghi request URL để phục vụ chẩn đoán.
- **APM, tracing, metrics, error monitoring**: công cụ tự động thu URL và các request attributes.
- **Browser extension hoặc môi trường máy dùng chung**: URL có thể bị quan sát bởi thành phần có quyền truy cập.
- **Referer header**: khi một trang có điều hướng hoặc tải tài nguyên, browser có thể gửi thông tin URL nguồn theo `Referrer-Policy` và chính sách trình duyệt.
- **Ticket hỗ trợ và báo cáo lỗi**: người dùng/nhân viên có thể dán nguyên URL vào hệ thống khác.

### 3.1. HTTPS có bảo vệ query string trên đường truyền không?

Có: đối với HTTPS, path và query được mã hóa khi truyền qua TLS giữa các endpoint TLS phù hợp. Tuy nhiên, bên **kết thúc TLS**, chẳng hạn load balancer hoặc reverse proxy của hệ thống, có thể thấy toàn bộ request-target để định tuyến hoặc ghi log. Trình duyệt và máy chủ đích cũng thấy URL.

Do đó nguyên tắc vẫn là **không gửi secret/token/PII không cần thiết qua URL**, kể cả khi URL dùng HTTPS.

### 3.2. Vì sao `Referer` đáng quan tâm?

Giả sử sau callback ứng dụng hiển thị trang hoặc chuyển tiếp qua một route chứa query nhạy cảm. Nếu route đó tải tài nguyên từ bên thứ ba, việc gửi Referer phụ thuộc vào browser và chính sách.

Các browser hiện đại thường giới hạn Referer giữa các origin theo chính sách mặc định, nhưng không thể dựa vào quy tắc mặc định chung để tuyên bố query string sẽ không bao giờ lộ. Chính sách có thể khác nhau theo browser, cấu hình server, ứng dụng và những bước redirect tiếp theo.

Một chính sách bảo vệ chặt hơn cho trang xử lý login/callback hoặc trang có URL nhạy cảm có thể là:

```http
Referrer-Policy: no-referrer
```

Hoặc chính sách `strict-origin-when-cross-origin` trong bối cảnh phù hợp. Các header này hỗ trợ hạn chế rò thông tin qua Referer, nhưng **không thay thế việc không đưa secret vào URL ngay từ đầu**. Nên tránh hiển thị nội dung bên thứ ba trên trang callback nhạy cảm.

### 3.3. `Cache-Control` giải quyết vấn đề gì?

Đối với phản hồi chứa thông tin đăng nhập hoặc dữ liệu cá nhân, có thể dùng cache headers phù hợp, ví dụ:

```http
Cache-Control: no-store
```

Tuy nhiên, `Cache-Control` kiểm soát cách lưu trữ response theo các quy tắc HTTP cache; nó **không xóa** URL khỏi tất cả browser history, web server logs hoặc hệ thống tracing. Không được xem `no-store` là biện pháp duy nhất ngăn lộ thông tin từ query.

## 4. Giới hạn kích thước URL: không có một con số chung cho mọi hệ thống

Authorization request theo kiểu browser redirect thường dùng URL có query parameters. Khi thêm nhiều scope, `claims` JSON, hints hoặc extension parameters, URL tăng nhanh về độ dài.

**Không tồn tại một giới hạn URL duy nhất mà mọi browser, proxy, gateway, IdP đều tuân thủ như nhau.** Giới hạn có thể đặt tại từng thành phần; một URL có thể đi qua browser A nhưng bị từ chối tại load balancer B.

Một số mốc thực tế cần hiểu:

- **RFC 9110** khuyến nghị HTTP implementations hỗ trợ request-line dài ít nhất **8.000 octets** đối với HTTP/1.1. Đây **không phải bảo đảm** rằng mọi hệ thống OAuth2 có thể chấp nhận authorization URL dài đến mức đó hoặc vượt qua mọi lớp trung gian.
- Các tài liệu cũ thường nhắc mốc **2.048 ký tự** cho URL. Đó không phải giới hạn chuẩn chung của OAuth2/OIDC và không nên dùng như một con số tuyệt đối cho mọi browser.
- Web server, reverse proxy, WAF hoặc IdP có thể có giới hạn request-target, header, query parameter count hoặc tổng chiều dài request riêng.
- Độ dài **ký tự hiển thị** không bằng số **byte** trên đường truyền: URL encoding và Unicode có thể làm tăng kích thước đáng kể.

### 4.1. Phân biệt byte và ký tự

Ví dụ:

```text
Trước URL encoding:
login_hint=nguyễn@example.test

Sau URL encoding (minh họa):
login_hint=nguy%E1%BB%85n@example.test
```

Các ký tự Unicode khi được mã hóa UTF-8 và percent-encoding có thể chiếm nhiều byte hơn một ký tự ASCII. Trong khi đó các ký tự `:`, `/` trong `redirect_uri` cũng phải URL-encode khi nằm **bên trong tham số query**.

Ví dụ:

```text
Callback gốc:
https://app.example.test/login/oauth2/code/company

Giá trị query sau encoding:
https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany
```

Nếu chỉ đếm số ký tự trong `application.yml`, bạn sẽ chưa thấy độ dài URL cuối cùng sau khi Spring mở rộng template và URL-encode tham số.

### 4.2. Các yếu tố khiến authorization URL phình to

| Thành phần | Vì sao tăng độ dài? | Hướng xử lý |
|---|---|---|
| `redirect_uri` | Callback chứa host, port, context path dài; sau đó được percent-encode | Dùng callback đơn giản, cố định và phù hợp cấu hình IdP |
| `scope` | Nhiều scope dài, URI-style scopes | Chỉ xin scope cần; xem cơ chế cấp quyền theo giai đoạn |
| `state` | Ứng dụng tự nhét JSON/base64 lớn vào state | Dùng state ngẫu nhiên ngắn đủ an toàn, lưu ngữ cảnh phía server |
| `nonce` | Chuỗi ngẫu nhiên | Sinh đủ entropy; không nối thêm dữ liệu khác |
| `claims` | JSON mô tả nhiều claim/essential requirement | Giảm claim yêu cầu, cân nhắc request object/PAR nếu hỗ trợ |
| `login_hint`, `ui_locales`, `acr_values` | Dữ liệu tùy biến | Chỉ gửi khi thực sự cần |
| Custom parameters | Duplicated/serialized object quá lớn | Thiết kế danh sách tham số có giới hạn rõ |
| `request` (JAR request object) | JWT có thể dài đáng kể | Cân nhắc PAR hoặc `request_uri` khi server hỗ trợ |

### 4.3. Triệu chứng khi vượt giới hạn

Các lỗi phụ thuộc thành phần từ chối request:

- **HTTP 414 URI Too Long** ở reverse proxy hoặc Authorization Server.
- **HTTP 400 Bad Request** khi URL/query không được provider chấp nhận.
- **HTTP 431 Request Header Fields Too Large** nếu vấn đề nằm ở header, thường cần phân biệt với URL dài.
- URL bị chặn bởi WAF, gateway hoặc browser; một số môi trường có thể trả trang lỗi mà ứng dụng Spring không thấy.
- Provider báo `invalid_request` hoặc lỗi tùy hệ thống vì tham số quá lớn/không hợp lệ.

Không quy mọi lỗi 400 thành “URL quá dài”: scope sai, redirect URI không khớp, chữ ký request object sai hay thiếu tham số bắt buộc cũng có thể gây lỗi.

### 4.4. Cách xác định chính xác điểm nghẽn

1. Xem `Location` header do Spring trả về khi bắt đầu login (che giá trị nhạy cảm).
2. Xác định URL mà browser gửi tới Authorization Endpoint.
3. So sánh kích thước request-target sau URL encoding với giới hạn tại browser/proxy/WAF/IdP.
4. Kiểm tra mã phản hồi và **hệ thống phát sinh** lỗi: reverse proxy, WAF hay IdP.
5. Loại bớt các tham số tùy chọn không cần thiết; nếu vẫn quá dài, đánh giá cơ chế authorization request qua back channel như **PAR** khi nhà cung cấp hỗ trợ.

Không tự đặt một quy tắc “mọi authorization URL phải dưới 2.048 ký tự” mà không xem hệ thống triển khai. Tuy nhiên, vẫn nên đặt **ngưỡng vận hành nội bộ thận trọng** dựa trên chuỗi hạ tầng thực tế và thử flow đầy đủ.

## 5. `state`: giữ ngẫu nhiên, tối thiểu và không chứa dữ liệu người dùng

`state` giúp Client liên kết callback với authorization request ban đầu, chống những tình huống như login CSRF và response bị gán nhầm phiên. Spring Security có cơ chế sinh/lưu/kiểm tra `state` cho OAuth2 Login.

Một thiết kế đúng cho state là **giá trị không đoán được** để đối chiếu với thông tin Client đã lưu:

```text
state = random opaque value
Session/server-side store:
  state -> authorization request + flow-specific context
```

Không nên tự thay state thành JSON chứa toàn bộ ngữ cảnh:

```json
{
  "email": "user@example.test",
  "phone": "+84901234567",
  "address": "Sample address",
  "next": "https://external.example.test/landing"
}
```

Nếu đóng gói object này bằng Base64 rồi đặt vào `state`, dữ liệu **không được mã hóa**: Base64 chỉ là biểu diễn ký tự, ai có URL cũng có thể giải mã. Kể cả dùng chữ ký để chống sửa dữ liệu, chữ ký **không che nội dung**. Ngoài vấn đề riêng tư, JSON/Base64 làm URL dài hơn.

### 5.1. Muốn nhớ trang đích sau login thì làm gì?

Trong ứng dụng Spring MVC có session, có thể dùng **`RequestCache` / saved request** của Spring Security để nhớ trang mà người dùng đang truy cập trước khi đăng nhập. Nó khác với `AuthorizationRequestRepository` dùng lưu authorization request và `state`.

Ví dụ:

```text
User vào /orders/123?tab=history
    -> Spring lưu saved request /orders/123?tab=history
    -> Browser được chuyển sang IdP với state ngẫu nhiên
    -> Callback hợp lệ, login thành công
    -> Success handler đưa người dùng về saved request
```

Nếu ứng dụng cần một workflow context riêng, hãy giữ ngữ cảnh này **phía server** dưới một khóa opaque, có thời gian sống ngắn, gắn với session hoặc luồng xác thực. Không đưa trực tiếp thông tin nhạy cảm vào `state`, `redirect_uri` hoặc các custom query parameters.

### 5.2. Không tự viết state nếu không cần thiết

Một số developer muốn thêm `state=tenantId|returnUrl` để tiện routing. Việc tùy biến `state` thiếu cơ chế lưu/đối chiếu có thể làm Spring từ chối callback hoặc tạo lỗ hổng CSRF. Khi cần tùy chỉnh authorization request, nên giữ nguyên việc sinh và kiểm tra state của Spring, chỉ thêm các tham số do provider cho phép và có chính sách riêng.

## 6. `nonce` và PKCE: những gì có thể/không thể đưa lên URL

### 6.1. `nonce` của OIDC

OIDC dùng `nonce` để ràng buộc ID Token với authentication request trong những flow/ngữ cảnh áp dụng. `nonce` cần được sinh ngẫu nhiên và đối chiếu đúng khi nhận token. Nó có thể xuất hiện trong authorization URL theo giao thức, nhưng không nên gắn PII hoặc dùng chuỗi cố định.

Không dùng `nonce` như một kho lưu trạng thái tùy ý thay cho session.

### 6.2. PKCE: challenge trong front channel, verifier trong back channel

PKCE sinh ra `code_verifier` ngẫu nhiên và tính:

```text
code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
```

Thông tin đi qua hai bước:

| Bước | Giá trị xuất hiện | Kênh |
|---|---|---|
| Authorization Endpoint | `code_challenge`, `code_challenge_method=S256` | Trình duyệt/front channel |
| Token Endpoint | `code_verifier` | Kết nối trực tiếp tới token endpoint/back channel |

`code_challenge` theo S256 không tiết lộ trực tiếp verifier với xác suất thực tế khi verifier đủ mạnh. Nhưng nếu developer đặt thẳng `code_verifier` lên authorization URL, lợi ích của PKCE bị phá hủy.

Với confidential client, cũng không gửi `client_secret` trên authorization URL. Secret đó dùng theo phương thức Client authentication đã đăng ký ở Token Endpoint.

### 6.3. Đừng tự thêm trùng tham số bảo mật

Spring Security thường đã quản lý `state` và những dữ liệu OIDC/PKCE phù hợp với flow. Khi dùng custom resolver, đừng tự thêm phiên bản thứ hai của `state`, `nonce`, `redirect_uri` hoặc `code_challenge` bằng query string thủ công.

Một URL có nhiều bản sao cùng tên tham số có thể bị các thành phần parse khác nhau theo quy tắc khác nhau, gây lỗi hoặc tạo cơ hội tấn công kiểu parameter pollution. Hãy sử dụng API builder/resolver của Spring và bảo đảm mỗi tham số có đúng nghĩa giao thức.

## 7. Redirect URI không phải nơi gửi dữ liệu nghiệp vụ

`redirect_uri` là **callback URL của Client**. Ví dụ mặc định:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
```

Với request đến `https://app.example.test`, giá trị được mở rộng thành:

```text
https://app.example.test/login/oauth2/code/company
```

Bên IdP cần cho phép đúng URL này. Không tự thêm dữ liệu cá nhân hay đích điều hướng vào callback:

```text
KHÔNG NÊN:
https://app.example.test/login/oauth2/code/company?email=user@example.test
https://app.example.test/login/oauth2/code/company?returnTo=https://external.example.test
```

Các thay đổi ở query có thể khiến URI không trùng danh sách được IdP đăng ký; ngoài ra còn tạo điểm rò rỉ dữ liệu hoặc open redirect.

### 7.1. Ba URL cần phân biệt

| URL | Ví dụ | Mục đích |
|---|---|---|
| Spring login initiation | `/oauth2/authorization/company` | Bắt đầu OAuth2 Login |
| OAuth2 Redirect URI | `/login/oauth2/code/company` | Nhận authorization response chứa `code` và `state` |
| Success target | `/dashboard` hoặc URL saved request | Trang người dùng tới sau khi login thành công |

Muốn đưa người dùng về trang họ đang xem trước login, sử dụng cơ chế saved request/success handler phù hợp. **Đừng coi callback URL là nơi lưu `returnTo` hoặc dữ liệu phiên**.

### 7.2. Proxy và nguy cơ host header poisoning

Mẫu `{baseUrl}` phụ thuộc địa chỉ công khai mà Spring nhận biết. Với ứng dụng phía sau reverse proxy, Spring có thể nhận kết nối nội bộ `http://service:8080` trong khi URL công khai là `https://app.example.test`.

Khi cần xử lý forwarded headers, cấu hình Spring Boot có thể bao gồm:

```yaml
server:
  forward-headers-strategy: framework
```

Tuy nhiên, chỉ tin các header `Forwarded` hoặc `X-Forwarded-*` từ **reverse proxy đáng tin**. Nếu Client ngoài có thể giả mạo host/scheme rồi khiến Spring mở rộng `{baseUrl}` thành domain do kẻ tấn công điều khiển, rủi ro lớn hơn một lỗi redirect thông thường.

Cần đặt rule canonical host, proxy allowlist và đăng ký Redirect URI cụ thể tại IdP. Khi môi trường chỉ có một public origin, có thể cân nhắc cấu hình Redirect URI cố định theo từng môi trường:

```yaml
redirect-uri: "https://app.example.test/login/oauth2/code/company"
```

Lựa chọn này cũng phải được IdP chấp thuận và ứng dụng phải thực sự xử lý đường dẫn đó.

## 8. Tham số tùy chọn: có ích nhưng cần chọn lọc

OIDC và các provider thường cho phép thêm tham số authorization request. Ví dụ:

| Tham số | Mục đích | Rủi ro hoặc giới hạn |
|---|---|---|
| `prompt=login` | Yêu cầu provider chủ động xác thực lại theo quy tắc của họ | Có thể gây nhiều bước đăng nhập hơn |
| `prompt=select_account` | Gợi ý hiển thị chọn tài khoản nếu provider hỗ trợ | Phụ thuộc provider |
| `max_age=300` | Quy định tuổi xác thực tối đa trong yêu cầu OIDC | Cần hiểu việc provider trả `auth_time` và kiểm tra tương ứng |
| `ui_locales=vi en` | Gợi ý ngôn ngữ giao diện | Chỉ là gợi ý; không ép provider hỗ trợ |
| `acr_values` | Yêu cầu mức/ngữ cảnh xác thực | Cú pháp và hỗ trợ tùy provider; không tự đồng nghĩa đã có MFA |
| `login_hint=user@example.test` | Gợi ý tài khoản người dùng | **Lộ email/username qua URL**, có thể không cần |
| `domain_hint` hoặc tenant hint | Gợi ý tenant/provider | Vendor-specific; cần validate giá trị |
| `claims` | Đề nghị claim chi tiết trong OIDC | Có thể chứa PII/ngữ cảnh nhạy cảm và làm URL dài |
| `resource`, `audience` | Chỉ ra tài nguyên/API đích nếu server hỗ trợ | Không phải tham số phổ quát cho mọi Authorization Server |

Tránh đưa cả object tài khoản, danh sách quyền nội bộ hoặc session state vào một tham số “tiện tay”. Với `login_hint`, dù tham số được OIDC định nghĩa, việc gửi email trong URL vẫn là **một lựa chọn có hậu quả về quyền riêng tư**: cần có mục đích cụ thể và đánh giá xem có thể bỏ không.

### 8.1. Một request vừa đủ

Ví dụ Authorization Code OIDC Login:

```text
response_type=code
client_id=portal-web
redirect_uri=https://app.example.test/login/oauth2/code/company
scope=openid profile email
state=<opaque, random>
nonce=<opaque, random, nếu áp dụng>
code_challenge=<S256 challenge, nếu áp dụng>
code_challenge_method=S256
```

Không có `password`, `client_secret`, `access_token`, `refresh_token` hoặc dữ liệu hồ sơ chi tiết.

### 8.2. Một request nên tránh

```text
response_type=code
client_id=portal-web
client_secret=plaintext-secret
state=BASE64_OF_EMAIL_PHONE_ADDRESS
redirect_uri=https://app.example.test/login/oauth2/code/company?next=https://evil.example.test
login_hint=user@example.test
custom_user_profile=VERY_LARGE_JSON_OBJECT
code_verifier=SECRET_PKCE_VERIFIER
```

Ví dụ này minh họa các thiết kế **không an toàn hoặc không phù hợp**; không được áp dụng để thử với secret thật. Có nhiều vấn đề cùng lúc: lộ Client secret và verifier, chứa PII trong state, callback có đích chuyển tiếp ngoài, hint có email và dữ liệu lớn gây tăng URL.

## 9. Cấu hình Spring Boot: giữ authorization request đơn giản

Với Spring Boot sử dụng Spring Security OAuth2 Client và một OIDC Provider có discovery, cấu hình cơ bản có thể là:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          company:
            issuer-uri: https://login.example.test/realms/company
```

Tên miền `example.test` và biến `OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` chỉ để minh họa. Trong ứng dụng thật, cần nhập issuer và Client registration đúng của provider, đồng thời đăng ký callback tương ứng tại IdP.

Một cấu hình SecurityFilterChain Servlet phổ biến:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

Spring Security sẽ tạo authorization request từ `ClientRegistration`. Người viết ứng dụng không cần tự nối chuỗi URL `?client_id=...&scope=...&state=...` trong controller. Việc dùng filter và resolver có sẵn giúp các giá trị liên quan đến giao thức được tạo, lưu và đối chiếu thống nhất.

### 9.1. Scope tối thiểu giúp giảm URL và giảm dữ liệu xin truy cập

Nếu ứng dụng chỉ cần xác thực danh tính để tạo session, có thể bắt đầu bằng scope `openid` khi provider hỗ trợ. Nếu cần hiển thị tên/email, yêu cầu thêm `profile` và `email` theo nhu cầu. Không tự động thêm `address`, `phone` hoặc `offline_access` nếu không dùng.

Lưu ý: **giảm scope không đồng nghĩa với thay đổi Authorization Code Flow**. `scope` mô tả quyền/claim muốn xin; `authorization-grant-type=authorization_code` mô tả cách nhận code và đổi token.

### 9.2. Chỉ chứa URI cần thiết

`redirect-uri` nên giữ ở URL callback cụ thể mà Spring Security xử lý. Đừng đặt một URL hoàn chỉnh khác vào `scope`, `state` hoặc custom parameters để vòng qua việc đăng ký callback với provider.

Khi có nhiều môi trường, dùng cấu hình tách biệt cho local/staging/production với URL công khai tương ứng và chỉ đăng ký callback thực sự cần.

## 10. Tùy biến authorization request bằng Spring Security đúng cách

Thỉnh thoảng provider yêu cầu một tham số như `prompt=select_account`. Trong Servlet Spring Security, có thể dùng `DefaultOAuth2AuthorizationRequestResolver` và customizer của builder thay vì tự viết controller ghép URL.

Ví dụ dưới đây chỉ thêm một tham số cố định, không chứa PII:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;

@Configuration
public class OAuth2AuthorizationRequestConfig {

    @Bean
    OAuth2AuthorizationRequestResolver authorizationRequestResolver(
            ClientRegistrationRepository registrations) {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
            registrations, "/oauth2/authorization"
        );

        resolver.setAuthorizationRequestCustomizer(builder ->
            builder.additionalParameters(parameters ->
                parameters.put("prompt", "select_account")
            )
        );

        return resolver;
    }
}
```

Đăng ký resolver vào `oauth2Login`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OAuth2AuthorizationRequestResolver requestResolver) throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(requestResolver)
                )
            );

        return http.build();
    }
}
```

Trong thực tế hai class ví dụ thuộc cùng ứng dụng, và `SecurityConfig` phải dùng bean resolver đã khai báo. `prompt=select_account` chỉ nên gửi nếu provider chấp nhận giá trị này. Với nhiều registration khác nhau, customizer có thể cần chính sách riêng theo provider thay vì áp dụng một tham số cho tất cả.

### 10.1. Vì sao chọn `additionalParameters`?

- Spring vẫn quản lý các tham số OAuth2 cốt lõi như `client_id`, `redirect_uri`, `state` và những thuộc tính của authorization request.
- Không cần encode thủ công từng ký tự trong URL.
- Có một vị trí để giới hạn danh sách tham số tùy biến.
- Dễ phân biệt **tham số giao thức do Spring quản lý** với **extension parameter do provider yêu cầu**.

Dù vậy, **builder không tự kiểm tra mọi rủi ro về riêng tư của giá trị bạn thêm**. Nếu thêm `login_hint`, `claims` hoặc một tham số lấy từ HTTP request, trách nhiệm kiểm soát giá trị vẫn thuộc về ứng dụng.

### 10.2. Không chuyển dữ liệu request chưa xác thực trực tiếp vào URL

Ví dụ rủi ro:

```java
// KHÔNG NÊN: user input được đưa thẳng lên URL authorization.
String hint = request.getParameter("login_hint");
builder.additionalParameters(params -> params.put("login_hint", hint));
```

Nguy cơ gồm: lộ PII, gửi dữ liệu ngoài dự kiến sang IdP, vượt độ dài URL, ký tự điều khiển/định dạng bất thường, hoặc ép người dùng vào luồng tenant/tài khoản không phù hợp.

Nếu sản phẩm có nhu cầu hợp lệ dùng hint, cần có những ràng buộc tương ứng:

1. Giá trị phải thuộc mục đích rõ ràng; cân nhắc có thể bỏ hint không.
2. Giới hạn độ dài và danh sách ký tự/định dạng.
3. Chỉ lấy từ dữ liệu mà ứng dụng có lý do tin cậy và được phép chia sẻ.
4. Không nhận URL đích hoặc issuer tùy ý rồi gửi sang nhà cung cấp khác.
5. Không ghi hint nhạy cảm vào log; nêu rõ tác động riêng tư nếu sử dụng.

### 10.3. Không ghi đè `state`, `nonce` hoặc PKCE bằng extension parameter

Khi áp dụng customizer, tránh sửa các tham số bảo vệ flow. Nếu yêu cầu PKCE `S256`, dùng API hỗ trợ PKCE của Spring Security trên cùng builder phù hợp với phiên bản ứng dụng, không tự xây `code_verifier` rồi đưa nó lên front channel.

Tham số tự thêm chỉ nên dành cho tính năng provider mở rộng và được phép. Trong một ứng dụng có nhiều ClientRegistration, customizer phải phân biệt provider nào hỗ trợ tham số nào.

## 11. Khi URL thật sự quá dài: giảm yêu cầu hoặc dùng PAR

Trong một số hệ thống, authorization request cần nhiều trường ngoài các tham số cơ bản. Ví dụ OIDC `claims` yêu cầu nhiều claim cụ thể, `authorization_details` của một extension đòi dữ liệu có cấu trúc, hoặc provider quy định request object.

Trước khi áp dụng cơ chế đặc biệt, nên **giảm yêu cầu**: bỏ scope dư, không gửi PII, không tự nhét state JSON, loại extension parameters không cần thiết. Nếu request vẫn lớn hoặc đòi mức bảo mật cao, có thể cân nhắc những chuẩn sau khi Authorization Server hỗ trợ.

### 11.1. Pushed Authorization Requests (PAR)

**PAR — RFC 9126** cho phép Client đẩy các tham số authorization request trực tiếp đến Authorization Server qua một endpoint back channel, thường là HTTP POST. Sau khi nhận yêu cầu, server trả về `request_uri` tham chiếu tới authorization request đã được lưu tạm.

Một luồng minh họa:

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client backend
    participant AS as Authorization Server
    participant B as Browser

    C->>AS: POST Pushed Authorization Request Endpoint
    Note over C,AS: response_type, scope, redirect_uri, state, PKCE...
    AS-->>C: request_uri + expires_in
    C-->>B: 302 tới /authorize?client_id=...&request_uri=...
    B->>AS: Authorization request với request_uri
    AS->>AS: Tra cứu yêu cầu đã được push
    AS-->>B: 302 callback?code=...&state=...
```

Ví dụ rút gọn về hình thức:

```http
POST /oauth2/par HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic EXAMPLE_CLIENT_AUTHENTICATION

response_type=code&
client_id=web-client&
redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&
scope=openid%20profile%20email&
state=EXAMPLE_RANDOM_STATE&
code_challenge=EXAMPLE_PKCE_CHALLENGE&
code_challenge_method=S256
```

Authorization Server có thể trả:

```json
{
  "request_uri": "urn:ietf:params:oauth:request_uri:EXAMPLE_REFERENCE",
  "expires_in": 90
}
```

Trình duyệt sau đó được điều hướng tới URL ngắn hơn:

```text
https://login.example.test/oauth2/authorize?client_id=web-client&request_uri=urn%3Aietf%3Aparams%3Aoauth%3Arequest_uri%3AEXAMPLE_REFERENCE
```

Ưu điểm:

- Giảm số lượng/thời lượng tham số xuất hiện trên URL front channel.
- Có thể giảm rủi ro rò PII từ các authorization request phức tạp.
- Giúp tránh một số giới hạn chiều dài URL của trình duyệt/proxy.
- Authorization Server có cơ hội xác thực Client và kiểm tra request sớm theo chính sách PAR.

Giới hạn:

- **PAR phải được Authorization Server hỗ trợ.** Không phải mọi IdP đều công bố PAR endpoint.
- `request_uri` là một tham chiếu có thời gian sống và ràng buộc nhất định; không tự tạo chuỗi này rồi coi là hợp lệ.
- PAR không có nghĩa Client được bỏ xác minh `state`, PKCE, redirect URI, issuer hay ID Token.
- **Spring Security có hỗ trợ cấu hình và luồng PAR tùy phiên bản**; cần đọc tài liệu của đúng phiên bản để xác định cách bật hoặc tích hợp. Không giả định mọi cấu hình `oauth2Login` mặc định đều tự chuyển GET authorization request thành PAR.

### 11.2. JWT-Secured Authorization Request (JAR)

**JAR — RFC 9101** cho phép đóng gói các tham số authorization request trong một **request object** dạng JWT có thể được ký và, tùy bối cảnh, được mã hóa.

Có hai cách thường thấy theo hỗ trợ của provider:

- Truyền request object trực tiếp bằng tham số `request`: chữ ký giúp bảo vệ tính toàn vẹn, nhưng JWT có thể **rất dài** và nếu chỉ ký mà không mã hóa thì payload vẫn đọc được.
- Truyền tham chiếu bằng `request_uri` theo cơ chế server cho phép: giảm URL nếu object được lưu ở nơi phù hợp và chỉ tham chiếu qua front channel.

**JAR không tự giải quyết giới hạn URL** nếu truyền một JWT lớn bằng `request` ngay trên query. Cũng không nên nhầm JAR với PAR: PAR là cơ chế **đẩy tham số qua back channel**, còn JAR là cơ chế **biểu diễn/bảo vệ nội dung request**. Hai cơ chế có thể được kết hợp nếu server hỗ trợ.

### 11.3. Authorization endpoint có nhận POST không?

OAuth 2.0 cho phép Authorization Endpoint hỗ trợ những hình thức request theo chuẩn, nhưng Spring Security OAuth2 Login dạng web thường bắt đầu bằng **browser redirect với authorization URL**. Không thể chỉ đổi redirect 302 thành một POST tùy ý rồi mặc định mọi provider và Spring callback sẽ xử lý đúng.

Nếu muốn giảm URL hoặc chuyển dữ liệu nhạy cảm khỏi front channel, ưu tiên cơ chế chuẩn mà **provider xác nhận hỗ trợ** như PAR, thay vì tự xây form POST chứa client secret hoặc token trên trình duyệt.

## 12. Quản lý log và quan sát flow mà không làm lộ dữ liệu

Điều tra lỗi OAuth2 thường cần biết Client đã gửi request nào. Nhưng cách bật log có thể vô tình khiến chính dữ liệu cần bảo vệ bị thu thập.

### 12.1. Dữ liệu có thể ghi và dữ liệu cần tránh

| Có thể ghi ở mức khái quát | Không nên ghi nguyên giá trị |
|---|---|
| `registrationId` đã được cấu hình | `client_secret` |
| Tên provider/issuer tin cậy | `access_token`, `refresh_token`, `id_token` |
| Thông tin rằng authorization request đã được tạo | `code_verifier`, `authorization_code` |
| Tên tham số và tổng độ dài URL | `state`, `nonce`, session cookie |
| HTTP status và phân loại lỗi | URL đầy đủ có email, token, user ID nhạy cảm |
| Nguyên nhân lỗi do proxy/IdP trả về sau khi lọc | Raw `Authorization` header hoặc Set-Cookie |
| Latency và correlation ID nội bộ an toàn | Body token response |

Một correlation ID vận hành được sinh ngẫu nhiên và không mang dữ liệu cá nhân có thể hữu ích để kết nối log giữa các lớp. **Không dùng `state` hoặc token như correlation ID trong log** chỉ vì chúng xuất hiện sẵn.

### 12.2. URL redaction tại proxy và APM

Nếu access log có dạng:

```text
GET /oauth2/authorize?client_id=...&state=...&login_hint=... HTTP/1.1
```

cần cấu hình log pipeline để **không ghi query string** hoặc để redaction/allowlist có hiệu lực ở lớp đầu tiên nhận request. Chỉ che ở dashboard cuối nhưng vẫn gửi raw URL vào pipeline có thể không đạt yêu cầu bảo vệ dữ liệu.

Với ứng dụng Spring Client, authorization request được gửi đến IdP, vì vậy hệ thống của IdP/proxy của IdP cũng có thể ghi URL. Hãy hạn chế dữ liệu ngay tại nguồn; bạn không thể kiểm soát mọi hệ thống log ở phía nhà cung cấp.

### 12.3. Không chia sẻ HAR/network export chưa được làm sạch

Khi cần hỗ trợ chẩn đoán login, HAR và ảnh chụp Developer Tools có thể chứa:

- Authorization URL với `state`, `nonce` và hints.
- Callback URL chứa authorization code.
- Cookie phiên và header nhạy cảm.
- Token response hoặc metadata tài khoản.

Trước khi chia sẻ, xóa hoặc che những giá trị này. Trong tài liệu, chỉ dùng placeholder như `EXAMPLE_STATE`, không dùng mã/code/token lấy từ phiên thật.

## 13. Ví dụ Java: kiểm soát độ dài URL mà không tiết lộ nội dung

Để quan sát vấn đề **giới hạn kỹ thuật**, có thể dùng một decorator/resolver nội bộ hoặc metrics ở tầng phù hợp để đo **độ dài authorization request URI**. Chỉ báo cáo tổng số byte hoặc cảnh báo khi vượt ngưỡng vận hành, không in nguyên URL.

Ví dụ một hàm tiện ích đơn giản:

```java
import java.nio.charset.StandardCharsets;

public final class AuthorizationUrlMetrics {

    private AuthorizationUrlMetrics() {}

    public static int utf8Bytes(String authorizationRequestUri) {
        if (authorizationRequestUri == null) {
            return 0;
        }
        return authorizationRequestUri
            .getBytes(StandardCharsets.UTF_8)
            .length;
    }

    public static boolean exceedsOperationalLimit(
            String authorizationRequestUri,
            int maxBytes) {

        return utf8Bytes(authorizationRequestUri) > maxBytes;
    }
}
```

Sử dụng:

```java
int actualSize = AuthorizationUrlMetrics.utf8Bytes(authorizationUri);

if (AuthorizationUrlMetrics.exceedsOperationalLimit(
        authorizationUri, configuredMaxBytes)) {
    // Không ghi toàn bộ authorizationUri vào log.
    logger.warn("Authorization request URI exceeded configured size limit");
}
```

Ở đây `authorizationUri` và `logger` là các biến được cung cấp từ context tích hợp/quan sát của ứng dụng; `configuredMaxBytes` là ngưỡng nội bộ do nhóm xác định dựa trên hạ tầng thực tế. Không xem đoạn code này là một bộ lọc bảo mật có thể áp dụng nguyên trạng vào `SecurityFilterChain`.

**Lưu ý kỹ thuật:** `String#getBytes(UTF_8)` đo số byte khi UTF-8 encode một chuỗi Java. Nếu cần đo đúng request-target đã percent-encode trên wire, nên đo **URI cuối cùng mà Spring/browser sẽ dùng** sau encoding; không đo chuỗi trước khi resolver tạo URL. Việc log chỉ một số tổng có thể giúp tìm thay đổi bất thường mà không thu thập giá trị query.

### 13.1. Tránh bắt lỗi bằng cách bỏ tham số bắt buộc

Nếu URI quá dài, không được “cắt bớt chuỗi” bằng cách xóa ký tự cuối hoặc bỏ đại `state`, `nonce`, `redirect_uri`, `code_challenge`. Hành động đó sẽ phá các ràng buộc OAuth2/OIDC, có thể gây lỗi hoặc làm suy giảm bảo mật.

Cách đúng là giảm tham số tùy chọn, yêu cầu ít dữ liệu hơn, hoặc chuyển sang cơ chế provider hỗ trợ như PAR.

## 14. Tình huống lỗi thực tế

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra phù hợp |
|---|---|---|
| Browser báo URL quá dài | URL authorization chứa quá nhiều tham số/custom JSON | Đo URI cuối sau encoding; rà lại `scope`, `claims`, `state` |
| IdP trả HTTP 414 | Proxy/IdP giới hạn request-target | Xác định lớp trả lỗi; so sánh kích thước request với cấu hình giới hạn |
| IdP trả `invalid_request` | Tham số thiếu, sai hoặc quá lớn | Đọc thông báo provider đã lọc, xem danh sách tham số |
| Đăng nhập lỗi `invalid_scope` | Scope không được provider cho phép | Loại scope dư hoặc xin quyền thích hợp; không đổ lỗi URL size |
| Callback lỗi `state` mismatch | State do custom code ghi đè hoặc session bị mất | Kiểm tra resolver, AuthorizationRequestRepository, session/cookie |
| Token Endpoint trả `invalid_grant` | Code hết hạn, PKCE verifier sai, redirect_uri không khớp | Kiểm tra flow/state/PKCE và callback; tránh log code |
| Login thành công nhưng email xuất hiện trên URL của IdP | Đã gửi `login_hint` hoặc PII ở `state` | Rà custom authorization parameters và bỏ dữ liệu không cần |
| Callback redirect sang host khác | `redirect_uri` sai hoặc proxy headers bị tin không đúng | Kiểm tra host/scheme công khai, allowlist URI tại IdP |
| Có dấu hiệu PII trong APM | Pipeline thu raw URL/query | Thay chính sách instrumentation, redaction ngay tại nguồn |
| Chuyển sang JAR mà URL càng dài | Dùng tham số `request` chứa JWT lớn | Đánh giá PAR hoặc `request_uri` nếu server hỗ trợ |
| Ứng dụng ở proxy A hoạt động nhưng proxy B lỗi | Hai nơi có giới hạn request-target/WAF khác nhau | So sánh cấu hình proxy, gateway, header và location của lỗi |
| Người dùng login qua nhiều tab gặp flow lỗi | State/session/authorization request cạnh tranh hoặc custom handling sai | Kiểm tra session và repository phù hợp, không sửa state thủ công |

Một hướng debug có ích là tách vấn đề theo **giai đoạn**:

1. Không chuyển được từ Spring sang IdP: kiểm tra tạo URL, encoding, redirect và giới hạn browser/proxy.
2. Đã tới IdP nhưng bị từ chối: kiểm tra Client registration, scope, redirect URI, tham số tùy chọn và chính sách IdP.
3. IdP redirect về callback nhưng Spring từ chối: kiểm tra `state`, session, authorization request repository và PKCE.
4. Đổi code thành công nhưng xác thực thất bại: kiểm tra issuer, audience, chữ ký/nonce của ID Token, không liên hệ nhầm với kích thước authorization URL.
5. Login thành công nhưng có dữ liệu nhạy cảm trong log: xử lý cấu hình quan sát và nguồn tham số, không thay đổi flow theo cách làm lộ thêm dữ liệu.

## 15. Bài tập thực hành

### Bài tập 1: Nhận diện dữ liệu không nên gửi

Một developer muốn thêm custom parameters:

```json
{
  "login_hint": "user@example.test",
  "client_secret": "secret-value",
  "code_verifier": "verifier-value",
  "prompt": "select_account"
}
```

**Câu hỏi:** những trường nào không được đưa vào authorization URL?

**Gợi ý đáp án:** `client_secret` và `code_verifier` không được gửi lên front channel. `login_hint` có thể là tham số OIDC hợp lệ nhưng chứa PII; chỉ dùng nếu thực sự cần và đã đánh giá rủi ro. `prompt=select_account` là ví dụ extension parameter ít rủi ro nếu provider hỗ trợ.

### Bài tập 2: Base64 có bảo vệ email trong `state` không?

Ứng dụng tạo:

```text
state = BASE64({"email":"user@example.test","next":"/reports"})
```

**Gợi ý đáp án:** không. Base64 không mã hóa nội dung. State còn có thể phình to và bị ghi vào URL/log. Nên dùng state ngẫu nhiên, lưu context phía server và dùng saved request/success handler cho URL đích.

### Bài tập 3: URL được mã hóa làm dài thêm bao nhiêu?

Cho callback `https://app.example.test/login/oauth2/code/company` và một danh sách scope dài. Hãy so sánh URI gốc, URI sau khi đưa làm giá trị `redirect_uri`, và URL authorization hoàn chỉnh sau encoding.

**Gợi ý:** dấu `:` và `/` trong callback thường được mã hóa thành `%3A` và `%2F` khi nằm trong query. Các giá trị Unicode có thể còn làm URL dài thêm. Không đo riêng chiều dài URI trong YAML.

### Bài tập 4: Cần gửi nhiều yêu cầu claim

Một hệ thống đòi `claims` JSON phức tạp, authorization URL vượt giới hạn WAF.

**Gợi ý đáp án:** trước tiên giảm claim không cần và tránh gửi PII; nếu yêu cầu thực sự cần nhiều tham số, kiểm tra IdP có hỗ trợ PAR không. Không cắt chuỗi ngẫu nhiên hoặc xóa `state`/PKCE để URI ngắn lại.

### Bài tập 5: Chọn cách debug an toàn

Một kỹ sư yêu cầu copy toàn bộ HAR gồm callback `code`, cookie phiên và token response để phân tích.

**Gợi ý đáp án:** chỉ cung cấp dữ liệu đã che hoặc bộ mô phỏng bằng placeholder; có thể báo status code, tên endpoint, tên tham số, tổng độ dài URL và nhóm lỗi. Không chia sẻ mã/code/token/cookie thật.

## 16. Các nguyên tắc triển khai cần ghi nhớ

- **Authorization URL là front channel**: dữ liệu có thể quan sát trong browser, proxy, IdP log, hệ thống phân tích hoặc quá trình hỗ trợ.
- **Không đặt secret/token trên URL**: đặc biệt là `client_secret`, `code_verifier`, `access_token`, `refresh_token`, mật khẩu và cookie.
- **`state` và `nonce` dùng giá trị ngẫu nhiên, không nhét PII**; không thay state của Spring bằng chuỗi JSON/Base64 chứa dữ liệu phiên.
- **`code_challenge` có thể gửi qua front channel; `code_verifier` phải giữ để dùng trong token exchange**. Ưu tiên PKCE `S256`.
- **`redirect_uri` là callback cụ thể được IdP cho phép**; không lồng dữ liệu nghiệp vụ hoặc external return URL tùy ý vào callback.
- **Chỉ yêu cầu scope và tham số cần thiết**. `login_hint`/`claims` có thể tiết lộ thông tin hoặc làm URL tăng kích thước.
- **Không có con số giới hạn URL áp dụng toàn cầu**. Kiểm tra byte thực tế sau encoding qua browser, proxy, WAF và IdP.
- **Dùng API resolver/customizer của Spring Security** khi provider thật sự đòi thêm tham số, tránh tự ghép URL hoặc làm mất `state`, PKCE.
- **Giảm dữ liệu ở nguồn và redaction trong log**. HTTPS và `Referrer-Policy` là các lớp bảo vệ, không phải lý do để đưa secret vào URL.
- **Cân nhắc PAR** khi authorization request phức tạp hoặc URL quá dài, với điều kiện nhà cung cấp và phiên bản Client hỗ trợ.

## 17. Tài liệu tham khảo

- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization request, `state`, `redirect_uri` và token exchange.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): `code_verifier`, `code_challenge` và `S256`.
- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126): PAR endpoint và `request_uri`.
- [RFC 9101 — The OAuth 2.0 Authorization Framework: JWT-Secured Authorization Request (JAR)](https://www.rfc-editor.org/rfc/rfc9101): request object được ký/mã hóa và cách chuyển yêu cầu.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): URI, request semantics và lưu ý về độ dài request.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): authorization request, `nonce`, `claims`, `login_hint` và các tham số OIDC.
- [Spring Security Reference — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): ClientRegistration, flow và callback trong Servlet.
- [Spring Security Reference — Advanced OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): tùy biến authorization endpoint/resolver.
- [Spring Security API — DefaultOAuth2AuthorizationRequestResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizationRequestResolver.html): customizer để bổ sung tham số authorization request.

Với Spring Security OAuth2/OIDC Client, một authorization request tốt phải **đủ thông tin giao thức để IdP xác thực và cấp quyền**, nhưng **không mang dữ liệu bí mật hoặc dữ liệu cá nhân dư thừa qua URL**. Giữ request gọn, kiểm soát redirect URI, để Spring xử lý các tham số bảo vệ flow và chỉ mở rộng bằng cơ chế chuẩn khi thật sự cần là nền tảng cho quá trình đăng nhập vừa tin cậy vừa dễ vận hành.
