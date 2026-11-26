# Vai trò riêng của CORS, CSRF và phân quyền phía máy chủ

## 1. Một API có ba câu hỏi bảo mật độc lập

Giả sử ứng dụng giao dịch có:

- Giao diện chính thức: `https://app.example.com`.
- API Spring Security: `https://api.example.com`.
- Trang không tin cậy: `https://evil.example.org`.
- Người dùng Alice và Bob, mỗi người sở hữu tài khoản riêng.

Alice đăng nhập API và trình duyệt lưu session cookie. JavaScript ở giao diện chính thức cần đọc số dư, còn một trang do kẻ tấn công kiểm soát có thể cố làm thay đổi dữ liệu hoặc đọc thông tin của Alice.

Ba câu hỏi xuất hiện:

1. **CORS — ai được trình duyệt chia sẻ response?** JavaScript đang chạy tại origin nào có được đọc response cross-origin từ API không?
2. **CSRF — thao tác có thực sự được người dùng/chương trình hợp lệ khởi tạo?** Một trang lạ có lợi dụng credentials mà trình duyệt tự gửi để kích hoạt POST/PUT/DELETE không?
3. **Phân quyền — user/client được phép thao tác với tài nguyên nào?** Alice có quyền xem hoặc sửa tài khoản của Bob không, dù request đến từ giao diện chính thức?

Đây là ba ranh giới khác nhau. Một cấu hình CORS hoàn hảo không thay thế token CSRF. Một CSRF token hợp lệ không cho user quyền sửa dữ liệu của người khác. Một backend có phân quyền đúng cũng không nên cấp quyền CORS credentials quá rộng để JavaScript ở origin không tin cậy đọc thông tin phiên.

Trong mô-đun **SPRING_SECURITY_HTTP_PROTECTION**, những kiểm tra trên cần phối hợp với authentication, security headers, CSP, HSTS, HTTP firewall và bảo vệ session, trên cả **Servlet** và **Reactive/WebFlux**.

### Kết quả học tập

Sau bài học, người học có thể:

- Giải thích rõ **CORS, CSRF, authentication và authorization** bảo vệ các khía cạnh nào, ở lớp browser hay server.
- Chỉ ra vì sao trang lạ vẫn có thể gây request tới API ngay cả khi CORS không cấp quyền đọc response.
- Phân tích vai trò `SameSite`, `HttpOnly`, `Secure`, `credentials: "include"` và preflight trong các kịch bản dựa trên cookie.
- Phát hiện lỗ hổng **Broken Object Level Authorization (BOLA)/IDOR** bất kể origin hay CSRF token hợp lệ.
- Cấu hình Spring Security Servlet/Reactive để preflight được xử lý đúng, actual request vẫn qua CSRF và authorization.
- Viết test mô phỏng ba loại thất bại riêng: CORS bị từ chối, request bị CSRF chặn, user thiếu quyền tài nguyên.

Các địa chỉ thuộc `example.com` và `example.org` là tên miền ví dụ.

## 2. So sánh nhanh ba lớp phòng vệ

| Câu hỏi | CORS | CSRF protection | Server-side authorization |
| --- | --- | --- | --- |
| Đối tượng cần kiểm soát | Quyền chia sẻ **response** với JavaScript ở origin khác; quyền preflight cho actual request | Tính hợp lệ của **thao tác thay đổi trạng thái** trong ngữ cảnh xác thực dễ bị CSRF | Quyền truy cập **endpoint, hành động, bản ghi/tài nguyên** |
| Nơi quyết định cuối cùng | Server phát CORS headers; **browser thực thi** quyền đọc | **Server kiểm tra** token hoặc biện pháp chống CSRF | **Server kiểm tra** principal, role, scope, ownership và chính sách |
| Dữ liệu thường dùng | `Origin`, method, request headers, allowlist | CSRF token, session/request, Origin/Referer khi áp dụng, cookie policy | Authentication, danh tính tài nguyên, quyền nghiệp vụ |
| Nếu thiếu | Trang khác origin có thể **không đọc được response**, nhưng một số request vẫn đến server | Một trang không tin cậy có thể kích hoạt hành động dùng credentials tự gắn | User hợp lệ có thể đọc/sửa tài nguyên không thuộc quyền mình |
| Có thay cho authentication? | Không | Không | Không; authorization cần một principal được xác thực phù hợp |
| Có chặn `curl`/HTTP client tùy ý? | Không; client ngoài browser không áp dụng SOP | Tùy chính sách server, không phải biện pháp xác thực client chung | Có thể từ chối request nếu kiểm tra quyền đúng |
| Ví dụ lỗi | Browser báo ACAO mismatch | Actual POST bị 403 vì thiếu CSRF token | Alice gọi `/accounts/bob` bị 403 |
| Mục tiêu kiểm thử | Origin hợp lệ/bị từ chối; OPTIONS và actual response | POST/PUT/PATCH/DELETE với/không token hợp lệ | User A/B, vai trò, ownership, tenant và object ID |

**Authentication** trả lời “ai đang gửi request”, còn **authorization** trả lời “danh tính đó được phép làm gì”. Hai khái niệm cũng cần tách biệt: xác thực thành công không có nghĩa user có toàn quyền.

### 2.1. Tưởng tượng ba cổng

~~~mermaid
flowchart TD
    A["Trang web hoặc HTTP client gửi request"] --> B["Browser: có cần CORS preflight?"]
    B --> C["Server: xử lý preflight theo CORS policy"]
    C --> D["Actual request đến API"]
    D --> E["Authentication: nhận diện principal"]
    E --> F["CSRF protection: kiểm tra thao tác khi cần"]
    F --> G["Authorization: quyền trên hành động và tài nguyên"]
    G --> H["Business handler có thể thực thi"]
    H --> I["Response về browser"]
    I --> J["Browser: kiểm tra CORS để JS được đọc"]
~~~

Sơ đồ là **các trách nhiệm logic**, không phải thứ tự cứng của tất cả Spring Security filters. Một actual request không cần preflight vẫn đi tới API; request lỗi có thể bị chặn trước handler; một số loại authentication và CSRF có thứ tự xử lý cụ thể khác nhau. Ý chính: mỗi lớp giải quyết một câu hỏi riêng và phải được kiểm thử độc lập.

## 3. CORS bảo vệ quyền đọc response, không phải toàn bộ endpoint

Browser áp dụng **Same-Origin Policy (SOP)** với JavaScript. Origin được xác định bằng `scheme + host + port`:

- `https://app.example.com` và `https://api.example.com`: khác origin.
- `https://app.example.com` và `https://app.example.com:8443`: khác origin.
- `https://app.example.com/one` và `https://app.example.com/two`: cùng origin.

Khi JavaScript ở `https://app.example.com` gọi API:

~~~javascript
const res = await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
const profile = await res.json();
~~~

API muốn trình duyệt chia sẻ response trong credentials mode `include` cần trả quyền CORS phù hợp:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json

{"username":"alice"}
~~~

`Access-Control-Allow-Origin` cấp quyền đọc cho **origin frontend cụ thể**. `Access-Control-Allow-Credentials: true` là điều kiện bổ sung khi request dùng credentials mode `include`. `Vary: Origin` quan trọng với HTTP caches khi ACAO được chọn theo Origin.

### 3.1. CORS không nói rằng user có quyền xem dữ liệu

Nếu request của Alice hỏi tài khoản của Bob, server phải từ chối do **authorization**, ngay cả khi `Origin: https://app.example.com` hợp lệ.

~~~http
GET /api/accounts/2002 HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Cookie: SESSION=<alice-session>
~~~

Response có thể là:

~~~http
HTTP/1.1 403 Forbidden
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Content-Type: application/json

{"error":"forbidden"}
~~~

Đây là hành vi **đúng**: browser cho frontend tin cậy đọc status 403, còn server không trao dữ liệu tài khoản Bob cho Alice.

### 3.2. CORS bị từ chối không có nghĩa request chưa đến server

Một JavaScript từ origin lạ có thể gửi GET thông thường. API xử lý request rồi trả 200/401/403; browser sau đó quyết định **không chia sẻ response** cho JavaScript nếu thiếu quyền CORS.

Ví dụ response không có ACAO cho `https://evil.example.org`:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"value":"..."}
~~~

JavaScript tại origin lạ không được đọc nội dung đó theo SOP/CORS. Nhưng không thể suy ra rằng server đã ngăn request trước khi xử lý.

**Quy tắc:** đừng dựa vào CORS để ngăn thực hiện một thao tác thay đổi trạng thái. Không có ACAO không đồng nghĩa không có tác động nghiệp vụ.

### 3.3. Wildcard với credentials

Kết hợp sau không hợp lệ để JavaScript đọc response ở credentials mode `include`:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Browser yêu cầu origin cụ thể. Tuy nhiên chỉ đổi `*` thành cách **phản chiếu bất kỳ `Origin` nào** cũng không an toàn:

~~~java
// Phản ví dụ: KHÔNG dùng cho API có dữ liệu phiên.
response.setHeader(
    "Access-Control-Allow-Origin",
    request.getHeader("Origin")
);
response.setHeader("Access-Control-Allow-Credentials", "true");
~~~

Nếu một origin của kẻ tấn công được cấp quyền đọc response với cookie người dùng, CORS đã trở thành một đường rò rỉ dữ liệu. Hãy dùng allowlist frontend thực sự tin cậy.

### 3.4. Origin không phải bằng chứng xác thực

Một script trong browser thông thường không thể tùy ý giả lập origin của trang khác, nhưng `curl` hoặc HTTP client ngoài browser có thể tự gửi:

~~~bash
curl -i "https://api.example.com/api/me" \
  -H "Origin: https://app.example.com"
~~~

Server không được xem header này là bằng chứng người gọi là Alice, hoặc request phát sinh từ một frontend được vận hành an toàn. **CORS không phải cơ chế xác thực hay phân quyền server-side.**

## 4. CSRF: khi trình duyệt tự mang credentials tới server

**Cross-Site Request Forgery (CSRF)** là nguy cơ một website không tin cậy khiến browser của nạn nhân gửi request làm thay đổi trạng thái đến dịch vụ mà nạn nhân đã đăng nhập.

Một đặc điểm quan trọng: browser có thể tự gắn **cookie phiên** trong request phù hợp, không cần trang gửi request biết giá trị cookie. Kẻ tấn công tận dụng cơ chế đó để làm request được server nhận diện là thuộc phiên của nạn nhân.

### 4.1. Ví dụ form có thể gửi mà không cần CORS

Giả sử người dùng đã đăng nhập vào API và cookie được browser phép gửi trong tình huống này. Trang lạ đặt:

~~~html
<form method="POST"
      action="https://api.example.com/api/profile/email">
  <input type="hidden" name="email" value="attacker@example.org">
  <button type="submit">Tiếp tục</button>
</form>
~~~

Browser có thể gửi request form POST cross-origin mà không cần server cấp quyền CORS để JavaScript đọc response:

~~~http
POST /api/profile/email HTTP/1.1
Host: api.example.com
Content-Type: application/x-www-form-urlencoded
Cookie: SESSION=<victim-session-if-allowed>

email=attacker%40example.org
~~~

Điều kiện **“if allowed”** rất quan trọng. Cookie `SameSite=Lax` hoặc `Strict`, `Secure`, Domain/Path và third-party-cookie policy có thể ngăn hoặc giới hạn việc đính cookie tùy ngữ cảnh. Nhưng **CORS không tự chặn form submission**. Nếu backend chấp nhận thao tác chỉ dựa vào session cookie mà thiếu CSRF protection, thay đổi có thể xảy ra dù trang lạ không đọc được response.

Trong thực tế, browser có thể chuyển trang do form submission, và kết quả của response là một navigation chứ không phải JavaScript được chia sẻ body qua Fetch.

### 4.2. SameSite hỗ trợ nhưng không thay thế kiểm tra CSRF

Cookie có thể được phát như sau:

~~~http
Set-Cookie: SESSION=<opaque-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- `HttpOnly` ngăn JavaScript đọc cookie trực tiếp qua `document.cookie`.
- `Secure` hạn chế gửi cookie tới kết nối bảo mật theo quy tắc browser.
- `SameSite=Lax` giúp giảm các tình huống gửi cookie cross-site không mong muốn.
- `SameSite=Strict` hạn chế hơn; `SameSite=None; Secure` cho phép nhiều ngữ cảnh cross-site hơn nhưng chịu chính sách cookie của browser.

**Cross-origin không đồng nghĩa cross-site.** `https://app.example.com` và `https://api.example.com` là hai origin khác nhau nhưng thường cùng site; port khác nhau cũng không tự tạo cross-site. Đặc biệt, trang do kẻ tấn công kiểm soát tại `https://evil-subdomain.example.com` có thể vẫn **same-site** với API, dù là origin không tin cậy.

Vì vậy cookie `SameSite=Lax` không phải lá chắn tuyệt đối trước các subdomain bị chiếm, user-controlled hosting hoặc XSS. Không nên coi việc bật SameSite là lý do bỏ toàn bộ CSRF protection trong ứng dụng xác thực dựa trên session.

### 4.3. CSRF token giải quyết điều gì?

Với mô hình phổ biến là **synchronizer CSRF token**, server tạo token khó đoán gắn với ngữ cảnh phiên hoặc trạng thái bảo vệ phù hợp. Client hợp lệ nhận token qua một kênh được phép và gửi lại trong request thay đổi trạng thái.

Ví dụ actual PUT:

~~~http
PUT /api/profile HTTP/1.1
Host: api.example.com
Cookie: SESSION=<session-id>
Content-Type: application/json
X-CSRF-TOKEN: <valid-token>

{"displayName":"Lan"}
~~~

Backend kiểm tra token **cùng** phiên/ngữ cảnh hợp lệ theo cơ chế cấu hình. Trang không tin cậy không nên có cách đọc token từ API qua SOP/CORS. Nếu token thiếu hoặc không hợp lệ, actual request bị từ chối.

Các phương thức chống CSRF khác có thể dựa trên double-submit cookie được ràng buộc đúng cách, hoặc bổ sung Origin/Referer/Fetch Metadata checking. Cần hiểu và triển khai đúng mô hình, không chỉ kiểm tra sự tồn tại của một header tên `X-CSRF-TOKEN`.

### 4.4. Vì sao preflight không phải CSRF token?

Browser có thể gửi:

~~~http
OPTIONS /api/profile HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Preflight **chỉ chứa tên header** `x-csrf-token`, không chứa token thật. Browser thường không gắn credentials của actual request vào preflight. Nếu `OPTIONS` được chấp nhận, actual PUT vẫn phải có token CSRF hợp lệ khi backend yêu cầu.

Một số request HTML form hoặc POST có content type safelisted không cần preflight. Vì thế luận điểm “mọi request nguy hiểm đều bị preflight kiểm tra” là sai.

## 5. Phân quyền: danh tính và ownership không phụ thuộc browser

**Authentication** xác minh principal, ví dụ Alice đã đăng nhập. **Authorization** quyết định Alice được phép xem/sửa dữ liệu nào. CORS và CSRF không tự kiểm tra quyền này.

Một lỗi phổ biến là Broken Object Level Authorization (BOLA), cũng hay được nhắc đến dưới tên IDOR: endpoint lấy đối tượng theo ID nhưng không xác minh user hiện tại có quyền với đối tượng đó.

### 5.1. Mã nghiệp vụ thiếu kiểm tra quyền

Đây là **phản ví dụ**:

~~~java
@PutMapping("/api/accounts/{accountId}/name")
public void rename(
    @PathVariable long accountId,
    @RequestBody RenameRequest request
) {
    // SAI: chỉ tìm theo ID mà không kiểm tra ai sở hữu account.
    accountService.renameWithoutOwnershipCheck(
        accountId, request.newName()
    );
}
~~~

Dù request đến từ `https://app.example.com`, có session hợp lệ và CSRF token hợp lệ, Alice vẫn có thể đổi `accountId` thành ID của Bob nếu backend không kiểm tra ownership. **Không lớp CORS hoặc CSRF nào tự ngăn BOLA.**

### 5.2. Kiểm tra quyền tại server, gắn với principal

Mẫu tư duy an toàn hơn:

~~~java
@PutMapping("/api/accounts/{accountId}/name")
public void rename(
    @PathVariable long accountId,
    @RequestBody RenameRequest request,
    Authentication authentication
) {
    // Phải kiểm tra tài khoản theo principal đã xác thực.
    accountService.renameOwnedAccount(
        authentication.getName(), accountId, request.newName()
    );
}
~~~

Và ở tầng service, logic phải có điều kiện quyền rõ ràng:

~~~java
// Pseudocode nghiệp vụ; tên repository/entity tùy dự án.
void renameOwnedAccount(
    String authenticatedUsername,
    long accountId,
    String newName
) {
    Account account = accountRepository.findById(accountId)
        .orElseThrow(() -> new NotFoundException());

    if (!account.ownerUsername()
            .equals(authenticatedUsername)) {
        throw new AccessDeniedException("Forbidden");
    }

    account.rename(newName);
    accountRepository.save(account);
}
~~~

Ví dụ này mô tả **điểm bắt buộc kiểm tra ownership**, không phải một implementation hoàn chỉnh của repository/entity. Ứng dụng thực còn cần xử lý tenant, trạng thái tài khoản, quyền chức năng, transaction, chống race condition và audit.

Có thể dùng `@PreAuthorize` và method security như một lớp bổ sung, nhưng rule cấp role (ví dụ `hasRole('USER')`) thường **không đủ** để kiểm tra tài khoản cụ thể có thuộc về user đang gọi không.

### 5.3. Phân quyền không được dựa trên Origin

Header `Origin: https://admin.example.com` không chứng minh caller là admin. Frontend admin có thể có user không đủ role; đồng thời client ngoài browser có thể giả lập Origin. Vì vậy:

- CORS allowlist admin kiểm soát browser nào được đọc response.
- Authentication xác định user/client.
- Authorization kiểm tra user có role/scope phù hợp và quyền trên đối tượng cụ thể.
- CSRF kiểm tra tính hợp lệ của thao tác dựa trên credentials tự gửi, khi mô hình ứng dụng đòi hỏi.

## 6. Ma trận tấn công: ba cơ chế sẽ làm gì?

| Kịch bản | CORS | CSRF | Authorization |
| --- | --- | --- | --- |
| Trang lạ gửi `fetch` để đọc `GET /api/me` | Chặn JavaScript đọc nếu origin không được phép | Thường không phải thao tác cần CSRF | Yêu cầu authenticated principal nếu endpoint private |
| Trang lạ nộp form POST đổi email bằng cookie | Không ngăn form gửi chỉ vì không có ACAO | Phải từ chối thiếu token/chứng cứ hợp lệ trong mô hình cần chống CSRF | Cần xác minh account đích thuộc user |
| Frontend chính thức POST đổi email, thiếu CSRF token | Origin được phép | Từ chối actual request | Dù user có quyền vẫn không được bỏ CSRF |
| Frontend chính thức gửi PUT có CSRF token nhưng sửa tài khoản Bob | Có thể cho đọc response | Token có thể hợp lệ | Từ chối vì thiếu ownership |
| User chưa login gọi `GET /api/me` từ origin đúng | Có thể cho JS đọc response lỗi | Thường không liên quan | Authentication phải từ chối |
| Origin không tin cậy nhưng HTTP client tự đặt `Origin` hợp lệ | CORS không ngăn HTTP client tùy ý | Phụ thuộc cơ chế CSRF phía server | Authentication/authorization vẫn cần |
| Trang cùng site nhưng khác origin, do kẻ tấn công kiểm soát | Phải không cấp CORS đọc dữ liệu | SameSite có thể không chặn cookie; CSRF vẫn cần | Kiểm tra quyền thao tác |
| XSS chạy trong frontend chính thức | Origin hợp lệ nên CORS có thể cho đọc | XSS có thể dùng token theo quyền script | Backend vẫn cần authorization; CSP/chống XSS là lớp bổ sung |
| Preflight OPTIONS không có cookie | Kiểm tra origin/method/headers | Không nên yêu cầu token CSRF của actual request | Không nên đòi session user cho preflight |
| Actual PUT bị 403 sau OPTIONS hợp lệ | Preflight đã qua; actual response cần ACAO phù hợp | Có thể do token sai | Hoặc do user thiếu quyền |
| API cho phép `Access-Control-Allow-Origin: *` với `credentials: "include"` | Browser từ chối đọc response | Không tự kiểm tra CSRF | Không tự kiểm tra quyền |
| CDN cache nhầm phản hồi riêng tư giữa Alice và Bob | CORS có thể vẫn khớp Origin | Không giải quyết cache dữ liệu | Authorization đã bị vô hiệu hóa bởi cách phát cache sai; cần cache control phù hợp |

**Một test CORS pass không bao giờ là bằng chứng CSRF/authorization pass.** Cần test riêng từng ranh giới.

## 7. Preflight và actual request là hai bước độc lập

Frontend gửi:

~~~javascript
const res = await fetch("https://api.example.com/api/accounts/1001", {
  method: "PUT",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ displayName: "Alice" })
});
~~~

Browser thường tạo preflight:

~~~http
OPTIONS /api/accounts/1001 HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Response hợp lệ:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST,PUT
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Sau đó browser gửi actual request có credentials nếu cookie policy cho phép:

~~~http
PUT /api/accounts/1001 HTTP/1.1
Origin: https://app.example.com
Cookie: SESSION=<alice-session>
Content-Type: application/json
X-CSRF-TOKEN: <valid-token>

{"displayName":"Alice"}
~~~

Thứ tự logic:

1. **CORS** trả lời preflight nếu origin, method, headers và path phù hợp; bước này thường **không có cookie/token của actual request**.
2. **Browser** mới gửi actual PUT.
3. **Authentication** xác minh phiên của Alice.
4. **CSRF** kiểm tra token của actual PUT khi policy yêu cầu.
5. **Authorization** xác minh Alice có quyền thay đổi tài khoản 1001.
6. **Business logic** cập nhật hoặc từ chối; actual response có CORS headers nếu frontend tin cậy cần đọc status/body.

Các bước ở server có thể thực hiện theo thứ tự filter khác nhau hoặc dừng sớm khi thất bại. Điều bắt buộc không thay đổi là **không dùng việc preflight thành công để bỏ qua các kiểm tra actual request**.

### 7.1. Vì sao permitAll OPTIONS không tự giải quyết CORS?

Một rule:

~~~java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~

chỉ nói với authorization rằng OPTIONS được phép qua trong phạm vi rule. Nó **không tự tạo** `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods` hay `Access-Control-Allow-Headers`. Nếu preflight chỉ trả HTTP 200 nhưng thiếu các header CORS, browser vẫn không gửi actual request.

Cách phù hợp là **bật xử lý CORS trước các filter bắt authentication**, đồng thời vẫn kiểm tra allowlist origin/method/header.

## 8. Thiết kế khi dùng session cookie

### 8.1. CORS không tự tạo cookie

Fetch mặc định dùng `credentials: "same-origin"`. Khi frontend tại `https://app.example.com` gọi API ở `https://api.example.com` và muốn browser gửi session cookie:

~~~javascript
await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
~~~

Điều này mới cho browser **cân nhắc** gửi cookie; cookie còn phải đáp ứng Domain/Path, `Secure`, `SameSite` và chính sách quyền riêng tư.

Phản hồi CORS cho credentials mode `include` phải dùng origin cụ thể và `Access-Control-Allow-Credentials: true` để JS được đọc. Một `Set-Cookie` không trở thành header mà JavaScript được đọc chỉ bằng `Access-Control-Expose-Headers`.

### 8.2. Phát và nhận CSRF token cho SPA

Một mô hình triển khai có thể là:

1. Người dùng được xác thực bằng session cookie.
2. Frontend đáng tin cậy lấy CSRF token từ một endpoint được bảo vệ, hoặc từ HTML do server tạo, theo cơ chế CSRF của ứng dụng.
3. Frontend gửi token đó trong request header của các thao tác thay đổi trạng thái.
4. Backend xác thực token cùng trạng thái phiên/ngữ cảnh.
5. CORS chỉ cho phép origin của frontend tin cậy đọc response cấp token; kẻ tấn công từ origin khác không được đọc token chỉ vì biết URL.

Ví dụ frontend khi API cung cấp endpoint lấy token theo cách được thiết kế:

~~~javascript
async function loadCsrfToken() {
  const res = await fetch("https://api.example.com/api/csrf", {
    credentials: "include"
  });

  if (!res.ok) {
    throw new Error("Không tải được CSRF token");
  }

  const body = await res.json();
  return body.token;
}

async function updateProfile(csrfToken, displayName) {
  const res = await fetch("https://api.example.com/api/profile", {
    method: "PUT",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-TOKEN": csrfToken
    },
    body: JSON.stringify({ displayName })
  });

  return res;
}
~~~

Đây là **quy ước API minh họa**: endpoint `/api/csrf` và trường JSON `token` phải được triển khai thực tế; không phải Spring tự sinh sẵn endpoint đó. CSRF token cần được quản lý trong bộ nhớ ứng dụng/phương thức phù hợp, tránh ghi log hoặc lộ sang origin không tin cậy. Khi dùng Spring Security phiên bản mới với deferred CSRF token/BREACH protection, cách tạo và giải mã token cho SPA cần phù hợp với `CsrfTokenRequestHandler`/repository được chọn.

**Không được nhầm**: frontend `app.example.com` thường không thể đọc cookie host-only `api.example.com` bằng `document.cookie`. Đừng mở rộng Domain của session cookie chỉ để script đọc nó; session cookie nên dùng `HttpOnly` khi phù hợp. Token CSRF có thể được cấp qua một kênh riêng.

### 8.3. SameSite và ranh giới subdomain

Một subdomain `https://user-content.example.com` có thể chứa JavaScript do user tải lên. Nó khác origin với `https://api.example.com` nhưng vẫn có thể cùng site theo quy tắc schemeful same-site. Vì vậy `SameSite=Lax` có thể không ngăn browser gửi cookie tới API trong những request same-site phù hợp.

Kết hợp phòng vệ:

- Không cho phép origin user-controlled đọc dữ liệu CORS có credentials.
- Duy trì CSRF protection cho thao tác thay đổi trạng thái dựa trên session.
- Giữ authorization tại tài nguyên.
- Quản lý cookie host-only, `Secure`, `HttpOnly`, `SameSite` phù hợp.
- Chống XSS và áp dụng CSP theo mô hình frontend.

### 8.4. Không dựa vào CSRF để bảo vệ GET nhạy cảm

CSRF thường nhắm đến **thay đổi trạng thái**, không phải cách bảo mật tính bí mật của mọi GET response. GET private cần authentication/authorization, không cache công khai và chỉ cấp CORS đọc cho origin tin cậy.

Đồng thời, endpoint GET **không nên thay đổi trạng thái nghiệp vụ**. Nếu GET kích hoạt chuyển tiền hoặc xóa dữ liệu, ứng dụng đã phá vỡ kỳ vọng về safe methods, khiến bảo vệ CSRF và trình duyệt khó dự đoán.

## 9. Khi dùng bearer token thay cho cookie

Một SPA có thể gửi:

~~~javascript
await fetch("https://api.example.com/api/me", {
  method: "GET",
  credentials: "omit",
  headers: {
    "Authorization": "Bearer <access-token>"
  }
});
~~~

Lúc này header `Authorization` do JavaScript chủ động đặt thường kích hoạt **preflight**. CORS cần cho phép tên header `Authorization` khi request cross-origin. API vẫn phải xác thực token và kiểm tra scope/role/ownership.

Về CSRF:

- Nếu **chỉ** xác thực bằng bearer token được JavaScript chủ động gửi và browser không tự gắn credentials tương đương, mô hình CSRF truyền thống dựa trên cookie có thể giảm đáng kể hoặc không áp dụng cùng cách.
- Nhưng nếu ứng dụng **còn chấp nhận cookie phiên, HTTP authentication tự gắn, hoặc cơ chế credentials browser-managed khác**, vẫn phải đánh giá CSRF.
- XSS và rò rỉ token có thể là rủi ro chính của mô hình bearer token; không coi việc tắt CSRF là đủ để chống XSS.
- Token hợp lệ vẫn cần authorization theo scope, quyền và từng object.

Không nên cấu hình `csrf.disable()` theo công thức “REST API thì tắt CSRF”. Quyết định phải dựa trên **cơ chế xác thực thực tế** và các request có thể được browser tự gửi thay mặt người dùng.

## 10. Cấu hình Spring Security Servlet: giữ ba lớp riêng biệt

Ví dụ Spring MVC và Spring Security với CORS allowlist cụ thể, authentication cần thiết cho API và CSRF **giữ bật**:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletProtectionConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of(
            "https://app.example.com"
        ));
        cors.setAllowedMethods(List.of(
            "GET", "POST", "PUT", "DELETE"
        ));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN", "Authorization"
        ));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        CorsConfigurationSource corsConfigurationSource
    ) throws Exception {
        return http
            // CORS preflight được kiểm tra trước auth bắt session/token.
            .cors(cors -> cors.configurationSource(corsConfigurationSource))
            // Giữ CSRF protection cho mô hình dùng cookie/session.
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .build();
    }
}
~~~

**Điểm cần hiểu:**

1. `CorsConfigurationSource` cho browser biết những frontend/method/header nào được chia sẻ response.
2. `http.cors(...)` tích hợp CORS đủ sớm để preflight không bị auth chặn chỉ vì không có cookie.
3. `csrf(Customizer.withDefaults())` giữ cơ chế chống CSRF thay vì tắt nó để POST chạy qua.
4. `authenticated()` bảo vệ các endpoint private nhưng **không thay thế authorization theo từng object**.
5. API thật cần thêm cơ chế login/session hoặc resource server và các rule quyền phù hợp. Mã trên là ví dụ về **các lớp cấu hình**, không phải một ứng dụng xác thực hoàn chỉnh.

### 10.1. Cấp token trong Spring MVC: minh họa một endpoint

Với cơ chế CSRF mặc định được cấu hình phù hợp, có thể triển khai endpoint trả token cho frontend tin cậy:

~~~java
import java.util.Map;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfTokenController {

    @GetMapping("/api/csrf")
    Map<String, String> csrf(
        @RequestAttribute("_csrf") CsrfToken csrfToken
    ) {
        return Map.of(
            "headerName", csrfToken.getHeaderName(),
            "token", csrfToken.getToken()
        );
    }
}
~~~

Đây là ví dụ cho **một cơ chế phân phối token**. Cần kiểm thử với phiên bản Spring Security, repository và request handler thực tế, nhất là khi CSRF token được deferred hoặc mã hóa để chống BREACH. Endpoint được bảo vệ theo security chain `/api/**`; frontend khác origin chỉ đọc được JSON nếu CORS cho phép. Không nên coi `GET /api/csrf` là endpoint cần cho mọi loại ứng dụng.

### 10.2. Phân quyền object-level ở service

Một endpoint `/api/accounts/{id}` phải đối chiếu `id` với principal; có thể dùng `@PreAuthorize` khi bật method security hoặc thực hiện kiểm tra rõ ràng trong service.

~~~java
// Mã minh họa interface nghiệp vụ và ngữ cảnh quyền.
void updateAccount(
    Authentication principal,
    long targetAccountId,
    UpdateAccountRequest request
) {
    Account account = repository.findById(targetAccountId)
        .orElseThrow(NotFoundException::new);

    if (!authorizationService.canEdit(principal, account)) {
        throw new AccessDeniedException("Forbidden");
    }

    account.applyChanges(request);
    repository.save(account);
}
~~~

Các lớp `Account`, `UpdateAccountRequest`, `NotFoundException` và repository do dự án định nghĩa. Nội dung cốt lõi là **authorization phải kiểm tra tài nguyên đích trên server**, không lấy `accountId` hoặc role do frontend tự khai báo làm sự thật.

### 10.3. Không tắt CSRF do lỗi preflight

Nếu `OPTIONS` nhận 401/403:

- Kiểm tra `http.cors(...)` và nguồn CORS thực tế.
- Kiểm tra `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`.
- Kiểm tra proxy/gateway hoặc custom filter có chặn trước Spring Security không.
- **Không** bỏ `csrf()` trên actual POST/PUT chỉ để sửa preflight.

Nếu `OPTIONS` thành công nhưng actual PUT trả 403, mới điều tra CSRF token và authorization riêng.

## 11. Cấu hình Spring Security Reactive / WebFlux

Với WebFlux, cấu hình tương ứng dùng `ServerHttpSecurity` và nguồn CORS reactive:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveProtectionConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of(
            "https://app.example.com"
        ));
        cors.setAllowedMethods(List.of(
            "GET", "POST", "PUT", "DELETE"
        ));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN", "Authorization"
        ));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);

        return http
            .cors(spec -> spec.configurationSource(source))
            .csrf(Customizer.withDefaults())
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll())
            .build();
    }
}
~~~

Ở đây `UrlBasedCorsConfigurationSource` thuộc `org.springframework.web.cors.reactive`, khác lớp Servlet có tên tương tự. Spring Security Reactive dùng `SecurityWebFilterChain`; nếu chọn `CorsWebFilter` độc lập, cần đảm bảo chạy đủ sớm so với authentication và không trùng chính sách với `ServerHttpSecurity.cors(...)`.

CSRF trong Reactive sử dụng các cơ chế/token repository phù hợp với WebFlux; không sao chép nguyên servlet `HttpSessionCsrfTokenRepository` và giả định nó hoạt động như `WebSession`. Ví dụ giữ CSRF enabled, nhưng chưa trình bày đầy đủ luồng nhận token Reactive theo phiên bản ứng dụng.

**Phân quyền object-level vẫn cần thực hiện ở server**, chẳng hạn reactive service kiểm tra ownership bằng principal và dữ liệu tài nguyên trước khi cập nhật. CORS và CSRF không kiểm tra tenant hoặc object ID thay cho code nghiệp vụ.

## 12. Kiểm thử: chứng minh mỗi lớp hoạt động độc lập

Cần lập test cho **hai loại ranh giới**: browser CORS và kiểm tra an ninh của actual request.

### 12.1. Ma trận kiểm thử bắt buộc

| Test | Origin | Auth | CSRF token | Object permission | Kỳ vọng |
| --- | --- | --- | --- | --- | --- |
| OPTIONS cho PUT JSON | App tin cậy | Không gửi credentials của actual request | Không gửi token giá trị thật | Không áp dụng ở preflight | CORS preflight thành công |
| OPTIONS từ origin lạ | Không tin cậy | Không cần auth | Không có | Không áp dụng | CORS từ chối |
| Actual PUT của Alice, không session | App tin cậy | Không có | Không có | Chưa xét | Bị Security từ chối |
| Actual PUT của Alice, session hợp lệ, thiếu CSRF | App tin cậy | Có | Thiếu | Có quyền | Bị CSRF từ chối |
| Actual PUT của Alice, session + CSRF hợp lệ, sửa tài khoản Bob | App tin cậy | Có | Hợp lệ | Không có quyền | Bị authorization từ chối |
| Actual PUT của Alice, token hợp lệ, sửa tài khoản Alice | App tin cậy | Có | Hợp lệ | Có quyền | Được xử lý nếu nghiệp vụ hợp lệ |
| Actual GET private từ origin lạ | Không tin cậy | Có thể có cookie | Không áp dụng | Có thể có quyền | JS không đọc được nếu CORS không cấp quyền |
| HTTP client tự đặt Origin của app | Tùy ý | Thiếu hoặc token sai | Tùy endpoint | Thiếu quyền | Server vẫn phải từ chối |
| Actual response 403 từ app tin cậy | App tin cậy | Có | Có thể sai | Có thể sai | JS đọc được status 403 nếu CORS đúng |

Không coi 200 ở preflight là bằng chứng actual request đã được authenticated. Cũng không coi mọi 403 là lỗi CORS: phải xem **method của request bị từ chối** và status/body/log.

### 12.2. MockMvc: preflight và CSRF là hai bài test khác nhau

Với Spring Boot, Spring Security và cấu hình CORS Servlet ở mục 10:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsCsrfSecurityBoundaryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void preflightDoesNotRequireSessionOrCsrfToken() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "https://app.example.com")
                .header("Access-Control-Request-Method", "PUT")
                .header("Access-Control-Request-Headers",
                    "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", "https://app.example.com"));
    }

    @Test
    void preflightRejectsUntrustedOrigin() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "https://evil.example.org")
                .header("Access-Control-Request-Method", "PUT"))
            .andExpect(status().isForbidden());
    }

    @Test
    void actualPutNeedsCsrfEvenWhenAuthenticated() throws Exception {
        mvc.perform(put("/api/profile")
                .with(user("alice"))
                .header("Origin", "https://app.example.com")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Alice\"}"))
            .andExpect(status().isForbidden());
    }
}
~~~

Test thứ ba gửi actual PUT có principal giả lập nhưng **không có token CSRF**, kỳ vọng `403` khi cơ chế CSRF đang bật. Kết quả này phụ thuộc context và Security filters phù hợp; ví dụ **chưa chạy** trên dự án cụ thể.

Muốn test đường thành công, có thể dùng `.with(csrf())` của `spring-security-test` cùng endpoint nghiệp vụ hiện hữu. Nhưng chỉ CSRF token hợp lệ **không đủ** để khẳng định request sẽ thành công; handler vẫn phải xét ownership và các điều kiện business.

### 12.3. Test authorization theo object ID

Đây là **mẫu tình huống bổ sung cần triển khai** trong ứng dụng có repository và tài khoản thật:

~~~java
// Pseudocode kiểm thử nghiệp vụ:
//
// Given: user alice sở hữu account 1001; user bob sở hữu 2002.
// When: alice gửi PUT /api/accounts/2002/name
//       với session hợp lệ và CSRF token hợp lệ.
// Then: HTTP 403 hoặc kết quả từ chối thích hợp;
//       dữ liệu account 2002 không thay đổi.
//
// Khi đổi target sang 1001 và điều kiện nghiệp vụ hợp lệ,
// request được xử lý. CORS Origin không làm thay đổi ownership.
~~~

Bài test này có thể nằm ở service layer, method security hoặc integration test tùy kiến trúc; cần kiểm tra dữ liệu **không bị thay đổi** chứ không chỉ dựa vào status.

### 12.4. WebTestClient: preflight và actual request trên Reactive

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.http.HttpHeaders.*;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveCorsCsrfBoundaryTest {

    @Autowired
    WebTestClient client;

    @Test
    void preflightAllowedWithoutAuthentication() {
        client.options()
            .uri("/api/profile")
            .header(ORIGIN, "https://app.example.com")
            .header(ACCESS_CONTROL_REQUEST_METHOD, "PUT")
            .header(ACCESS_CONTROL_REQUEST_HEADERS,
                "content-type,x-csrf-token")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                ACCESS_CONTROL_ALLOW_ORIGIN, "https://app.example.com");
    }

    @Test
    void actualPutWithoutCsrfIsForbidden() {
        client.mutateWith(mockUser("alice"))
            .put()
            .uri("/api/profile")
            .header(ORIGIN, "https://app.example.com")
            .bodyValue("{\"displayName\":\"Alice\"}")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Các test mang tính hướng dẫn và cần điều chỉnh theo cấu hình WebFlux thật, dependency `spring-security-test`, endpoint và cách tạo principal. `WebTestClient`/`MockMvc` không hoàn toàn mô phỏng browser SOP, cookie `SameSite` hoặc third-party-cookie restrictions; để chứng minh quyền đọc response thực tế cần thêm test trên browser.

## 13. Thực nghiệm với curl và DevTools

### 13.1. Kiểm tra preflight riêng

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Không gắn cookie hay bearer token vào lệnh này. Đây là cách kiểm tra preflight không cần thông tin xác thực của actual request.

Một origin khác:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://evil.example.org" \
  -H "Access-Control-Request-Method: PUT"
~~~

CORS nên từ chối origin không tin cậy. Với bộ xử lý mặc định của Spring, preflight không phù hợp thường trả `403 Invalid CORS request`.

### 13.2. Kiểm tra actual request và bảo mật server

~~~bash
curl -i -X PUT "https://api.example.com/api/profile" \
  -H "Origin: https://app.example.com" \
  -H "Content-Type: application/json" \
  --data '{"displayName":"Alice"}'
~~~

Không có phiên đăng nhập/CSRF token, endpoint private phải bị từ chối theo security policy. Nếu gửi session thử nghiệm, tránh lộ ID phiên vào shell history, logs và transcript công khai.

Nếu actual response là 401/403 nhưng thiếu CORS headers cho app được phép, browser có thể báo lỗi CORS và không đọc được status. Đó là **hai vấn đề riêng**: security đã từ chối request và response CORS chưa được áp dụng nhất quán.

### 13.3. DevTools giúp phân loại lỗi

1. Xác định **Origin** của trang đang chạy và URL API.
2. Kiểm tra có OPTIONS preflight không; nếu có, xem `Access-Control-Request-Method` và `Access-Control-Request-Headers`.
3. Nếu OPTIONS 401/403, kiểm tra CORS source, filter ordering, gateway và security chain trước khi thay đổi CSRF.
4. Nếu OPTIONS thành công, kiểm tra actual PUT/POST có xuất hiện không.
5. Nếu actual 401, kiểm tra session/token và authentication.
6. Nếu actual 403, kiểm tra CSRF token, role/scope, ownership và tenant.
7. Nếu actual 200 nhưng JS thấy lỗi CORS, kiểm tra ACAO/ACAC và response cuối qua proxy.
8. Kiểm tra cookie bị chặn trong tab Cookies khi dùng `credentials: "include"`.
9. Nếu yêu cầu đáng ngờ từ subdomain same-site, xem lại CSRF và quyền CORS của các origin có khả năng chạy JavaScript không tin cậy.

`curl` không thực thi CORS/SOP của browser; nó chỉ giúp quan sát HTTP response. Không dùng `mode: "no-cors"` để “sửa” frontend: chế độ này tạo response opaque, không cho JS đọc JSON như mong đợi.

## 14. Những sai lầm thiết kế thường gặp

| Sai lầm | Vì sao sai? | Hướng đúng |
| --- | --- | --- |
| “Không bật CORS là API không bị CSRF” | Form/navigation có thể gây request; CORS chủ yếu kiểm soát quyền đọc response | Duy trì CSRF protection cho các thao tác phù hợp |
| “Preflight được phép nên PUT chắc chắn được phép” | Preflight chỉ xét Origin/method/headers; không xét user ownership | Giữ auth, CSRF và authorization cho actual request |
| “CSRF token đúng thì user được sửa mọi bản ghi” | Token không mang quyền sở hữu tài nguyên | Kiểm tra object-level authorization ở service |
| “Origin là app chính thức nên request là admin” | Origin không phải principal; client ngoài browser có thể giả Origin | Authentication và role/scope/ownership tại server |
| “Dùng `SameSite=Lax` thì mọi CSRF biến mất” | Cross-origin same-site vẫn có thể gửi cookie; có các tình huống browser khác | SameSite là lớp bổ sung, không thay thế CSRF |
| “`HttpOnly` ngăn browser gửi cookie trong request giả mạo” | HttpOnly ngăn JS đọc cookie, không ngăn browser tự gửi | CSRF token, SameSite và policy phù hợp |
| “REST API luôn có thể tắt CSRF” | Phụ thuộc có browser-managed credentials hay không | Đánh giá toàn bộ các đường xác thực |
| “`allowedOrigins("*")` + credentials là tiện lợi” | Không hợp lệ cho response `credentials: "include"` | Origin allowlist cụ thể |
| “Phản chiếu mọi Origin là an toàn vì có CSRF” | Có thể cho trang lạ đọc dữ liệu GET private | CORS allowlist chặt và auth riêng |
| “OPTIONS 403 thì tắt CSRF” | Có thể là CORS processor hoặc gateway từ chối preflight | Kiểm tra method/headers/chain thực tế |
| “Frontend ẩn nút xóa là đủ” | Client có thể sửa request/ID | Server kiểm tra quyền thao tác |
| “GET /api/delete là tiện” | GET không nên có side effect thay đổi trạng thái | Dùng method đúng và CSRF/authorization phù hợp |
| “Browser báo CORS nghĩa là backend không xử lý gì” | Actual request có thể đã được xử lý rồi bị browser chặn đọc response | Kiểm tra Network và server audit logs |
| “Không cần bảo vệ nếu có CSP” | CSP hạn chế nguồn script/tài nguyên, không thay auth/CSRF/authorization | Phòng vệ nhiều lớp |

## 15. Kết hợp cùng các lớp HTTP protection khác

Trong kiến trúc Spring Security, CORS, CSRF và authorization không hoạt động đơn độc.

| Lớp bổ sung | Mục tiêu |
| --- | --- |
| **TLS + HSTS** | Giảm rủi ro truy cập không bảo mật; giữ cookie `Secure` và đường truyền HTTPS |
| **Session fixation protection** | Hạn chế nguy cơ kẻ tấn công áp đặt session ID trước đăng nhập |
| **Cookie attributes** | `HttpOnly`, `Secure`, `SameSite`, Domain/Path giúp thu hẹp cách sử dụng cookie |
| **CSP** | Hạn chế nơi script tải/chạy và các kết nối được phép qua `connect-src`, giảm một số đường XSS |
| **HTTP firewall và request validation** | Từ chối các request bất thường trước lớp routing/bảo mật khi thích hợp |
| **Authorization cấp object/tenant** | Chặn BOLA/IDOR, thực thi quyền thật theo dữ liệu server |
| **Cache-Control và CDN policy** | Tránh shared cache làm lộ dữ liệu của user này cho user khác |
| **Logging/audit** | Cho phép phân biệt preflight bị chặn, CSRF thất bại, request thiếu quyền và thao tác thành công |

**XSS là điểm đặc biệt quan trọng.** Nếu attacker chạy được JavaScript bên trong frontend **được CORS tin cậy**, script đó có thể tận dụng các API và CSRF token mà frontend được phép sử dụng. CSP và chống XSS là phòng vệ riêng; CORS/CSRF không thay thế chúng. Authorization vẫn phải hạn chế tác động ở mức user/role/tài nguyên.

## 16. Bài tập tình huống và lời giải

**Tình huống 1 — Form không cần CORS.** Trang lạ đặt form POST tới `https://api.example.com/api/profile/email`. Server không bật CORS cho trang đó. Điều này có bảo đảm email không bị sửa không?

**Lời giải:** Không. Browser có thể gửi form cross-origin mà không cần quyền CORS đọc response. Nếu cookie được gửi và backend thiếu CSRF protection, thay đổi có thể xảy ra. Server phải kiểm tra CSRF và quyền thực hiện thao tác.

**Tình huống 2 — Preflight thành công, PUT bị 403.** OPTIONS từ app trả 200 với ACAO/ACAC/Allow-Methods/Allow-Headers đúng. Actual PUT của Alice bị 403. Có cần mở rộng CORS không?

**Lời giải:** Không nên. CORS đã qua; cần kiểm tra authentication, CSRF token và authorization/ownership ở actual request.

**Tình huống 3 — CSRF token đúng, tài nguyên sai chủ.** Alice gửi token hợp lệ nhưng đổi ID tài khoản từ 1001 sang 2002 của Bob. Server kiểm tra CSRF rồi cập nhật ngay. Lỗ hổng thuộc lớp nào?

**Lời giải:** **Broken Object Level Authorization/IDOR**. Backend thiếu kiểm tra ownership của account 2002 theo principal Alice.

**Tình huống 4 — Same-site subdomain không tin cậy.** Trang tại `https://usercontent.example.com` do khách hàng kiểm soát. Cookie phiên API dùng `SameSite=Lax`. Có thể bỏ CSRF vì mọi trang khác origin đã bị CORS chặn không?

**Lời giải:** Không. Các subdomain HTTPS có thể cùng site; SameSite không phải ranh giới giữa origin tin cậy và user-controlled origin. CORS không chặn mọi form request. Phải giữ CSRF và không cấp quyền CORS credentials cho subdomain không tin cậy.

**Tình huống 5 — Bearer token.** API chỉ chấp nhận bearer token được SPA đặt chủ động trong `Authorization`; không có cơ chế xác thực tự đính kèm bởi browser. Có phải cùng mức nguy cơ CSRF như session cookie?

**Lời giải:** Không nhất thiết. Nguy cơ CSRF truyền thống có thể khác đáng kể; nhưng vẫn phải xem có đường xác thực browser-managed khác không, và xử lý XSS, lưu trữ token, CORS, authorization đầy đủ.

**Tình huống 6 — Origin giả.** Curl gửi `Origin: https://admin.example.com` và một request xóa user. Có thể cho phép vì header ghi “admin” không?

**Lời giải:** Không. Origin không xác thực danh tính và client ngoài browser có thể tự đặt. Server phải kiểm tra user/role/scope/quyền thao tác.

**Tình huống 7 — Lỗi CORS che 403.** API từ chối PUT vì CSRF nhưng frontend thấy `TypeError: Failed to fetch`. Tại sao?

**Lời giải:** Actual error response có thể thiếu ACAO/ACAC phù hợp, hoặc gateway/filter đã sửa headers. Cần kiểm tra actual status qua Network/log và cấu hình CORS cả trên response lỗi.

**Tình huống 8 — Giấu nút quản trị.** Frontend không hiển thị nút xóa user cho role USER nhưng `DELETE /admin/users/{id}` không kiểm tra role ở server. CORS chỉ cho admin origin. Có đủ an toàn không?

**Lời giải:** Không. Client có thể gọi endpoint trực tiếp hoặc thao túng request, và CORS không bảo vệ trước HTTP client ngoài browser. Server phải kiểm tra quyền quản trị.

**Tình huống 9 — OPTIONS 401.** Browser gửi OPTIONS cho `PUT application/json`; API đòi session ngay trên OPTIONS nên trả 401. Cần thêm CSRF token vào preflight không?

**Lời giải:** Không. Browser tạo preflight riêng, thường không mang credentials/token của actual request. Tích hợp CORS đủ sớm trước authentication; actual PUT vẫn kiểm tra CSRF.

**Tình huống 10 — GET bí mật.** Endpoint `GET /api/me` yêu cầu login, nhưng cho phép mọi Origin bằng cách phản chiếu ACAO cùng `Access-Control-Allow-Credentials: true`. CSRF có ngăn trang lạ đọc dữ liệu không?

**Lời giải:** Không. CSRF thường bảo vệ thao tác thay đổi trạng thái, không phải cơ chế giữ bí mật GET response. Khi cookie được browser gửi và CORS cấp quyền cho origin lạ, JavaScript của trang lạ có thể đọc dữ liệu. Cần thu hẹp CORS allowlist.

---

**Ghi nhớ:** **CORS quản lý việc browser chia sẻ response cross-origin; CSRF bảo vệ thao tác dễ bị kích hoạt trái ý muốn bằng credentials tự gửi; authorization kiểm soát người dùng được thao tác với tài nguyên nào.** Ba cơ chế không thay thế nhau. Trong Spring Security, hãy cho preflight qua CORS đúng thứ tự, giữ CSRF phù hợp với session/bearer model, và kiểm tra quyền **trên server theo từng object/tenant**. Kết hợp cookie security, CSP, TLS/HSTS, HTTP firewall và kiểm thử độc lập cả trên Servlet lẫn WebFlux.
