# Phân biệt cookie với Authorization header

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt cookie xác thực với thông tin xác thực gửi qua header Authorization.
- Giải thích cách trình duyệt tự gửi cookie theo cookie policy và cách client chủ động gắn Bearer token vào request.
- Phân tích HttpOnly, Secure, SameSite, Domain, Path, CORS và CSRF khi chọn phương thức xác thực.
- Dùng Spring REST Docs mô tả cookie bằng requestCookies/responseCookies và Authorization bằng requestHeaders.
- Viết HTTP test cho endpoint dùng session cookie và endpoint dùng Bearer token; kiểm tra credential thiếu hoặc sai.
- Che session ID/token trong snippet nhưng giữ cấu trúc cần thiết để consumer hiểu cách tích hợp.

## 1. Hai cách mang thông tin xác thực trong HTTP

Cookie và Authorization header đều có thể mang thông tin giúp server xác định người gọi. Tuy nhiên, chúng khác nhau ở cách được tạo, lưu trữ, gửi đi và cách trình duyệt xử lý.

**Xác thực bằng cookie phiên:**

```http
GET /api/profile HTTP/1.1
Host: api.example.test
Cookie: SESSION=<session-id>
Accept: application/json
```

Server thường cấp cookie sau khi đăng nhập bằng response header Set-Cookie. Trình duyệt lưu cookie và tự gửi lại trong những request phù hợp với Domain, Path, Secure, SameSite và các quy tắc cookie khác.

**Xác thực bằng Bearer token:**

```http
GET /api/profile HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
```

Client lấy access token qua một quy trình xác thực, sau đó chủ động gắn token vào Authorization header cho các request cần credential. Trình duyệt không tự lấy một token tùy ý từ local storage rồi tự động đưa vào header này; ứng dụng client phải thực hiện điều đó.

Hai ví dụ đều dùng placeholder. Không đưa session ID, access token hoặc refresh token có hiệu lực vào tài liệu công khai.

## 2. So sánh cookie và Authorization header

| Khía cạnh | Cookie xác thực | Authorization: Bearer |
| --- | --- | --- |
| Cách gửi | Browser tự đính kèm cookie phù hợp với URL và cookie policy | Client chủ động đặt header cho request |
| Nơi lưu thường gặp | Cookie jar của browser hoặc cookie store của HTTP client | Memory/token manager của client; cách lưu phụ thuộc ứng dụng |
| Credential | Thường là session ID opaque hoặc token trong cookie | Thường là access token dạng Bearer |
| JavaScript đọc được? | Cookie có HttpOnly không thể được JavaScript đọc qua document.cookie | Nếu token nằm trong memory thì code ứng dụng có thể truy cập; token ở nơi lưu khác có rủi ro riêng |
| CSRF | Có rủi ro vì browser tự gửi cookie theo điều kiện phù hợp | Ít chịu kiểu CSRF dựa trên auto-attach cookie nếu token chỉ được gắn rõ ràng bởi code client; XSS vẫn có thể đánh cắp hoặc sử dụng token |
| CORS | Cross-origin credentialed request cần cấu hình credentials và origin phù hợp | Authorization thường làm request không còn là CORS-safelisted request và có thể dẫn đến preflight |
| Thu hồi | Có thể vô hiệu hóa session phía server; cần xử lý cookie ở client | Có thể revoke token hoặc dùng access token ngắn hạn/refresh flow tùy thiết kế |
| REST Docs | Cookie có descriptor/snippet riêng | Header được mô tả bằng requestHeaders |

Không có phương pháp nào luôn tốt hơn. Lựa chọn phụ thuộc loại client, threat model, hạ tầng xác thực, yêu cầu browser và chính sách bảo mật của hệ thống.

## 3. Cookie xác thực hoạt động như thế nào?

Một quy trình session cookie điển hình:

1. Client gửi thông tin đăng nhập qua endpoint login.
2. Server xác minh thông tin, tạo session phía server.
3. Server trả Set-Cookie chứa session identifier và thuộc tính cookie.
4. Browser lưu cookie trong cookie jar.
5. Ở request sau, browser tự gửi Cookie nếu URL và chính sách cookie phù hợp.
6. Server đọc session identifier, tra cứu session và xác định principal/permissions.
7. Khi logout hoặc session hết hạn, server vô hiệu hóa session và có thể trả Set-Cookie để xóa cookie ở client.

Ví dụ response login:

```http
HTTP/1.1 200 OK
Set-Cookie: SESSION=<REDACTED>; Path=/; HttpOnly; Secure; SameSite=Lax
Content-Type: application/json

{"authenticated":true}
```

Request tiếp theo:

```http
GET /api/profile HTTP/1.1
Cookie: SESSION=<REDACTED>
Accept: application/json
```

Một session cookie thường là opaque identifier. Dữ liệu trạng thái phiên có thể được giữ phía server, trong database, cache hoặc session store phân tán. Cookie không nhất thiết chứa toàn bộ thông tin người dùng.

### 3.1. Các thuộc tính cookie cần hiểu

| Thuộc tính | Ý nghĩa |
| --- | --- |
| HttpOnly | JavaScript không đọc được cookie qua API document.cookie; browser vẫn có thể gửi cookie theo quy tắc |
| Secure | Browser chỉ gửi cookie qua kết nối an toàn theo quy tắc cookie |
| SameSite | Kiểm soát việc cookie được gửi trong một số ngữ cảnh same-site/cross-site |
| Domain | Xác định phạm vi host được phép nhận cookie |
| Path | Giới hạn đường dẫn request mà cookie áp dụng |
| Max-Age | Thời gian sống tính bằng giây; giá trị 0 hoặc âm có thể dùng để xóa cookie |
| Expires | Thời điểm hết hạn của cookie |

HttpOnly không ngăn cookie bị gửi qua HTTP request và không tự bảo vệ ứng dụng khỏi mọi XSS. Secure không thay thế TLS cho toàn bộ hệ thống. SameSite là một lớp kiểm soát CSRF, nhưng không nên coi nó là biện pháp duy nhất trong mọi threat model.

## 4. Authorization header và Bearer token hoạt động như thế nào?

Với Bearer authentication, client gắn credential vào mỗi request cần xác thực:

```http
GET /api/orders HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json
```

Server hoặc resource server xác minh token và áp dụng chính sách quyền. Với JWT, kiểm tra có thể bao gồm chữ ký, issuer, audience, thời gian hiệu lực và claims. Với opaque token, server có thể tra cứu qua authorization server hoặc token introspection/cache.

Bearer nghĩa là bên sở hữu token có thể sử dụng token theo phạm vi quyền của nó. Vì vậy:

- Truyền token qua TLS.
- Không ghi token vào log/snippet không được kiểm soát.
- Cấp scope/quyền tối thiểu.
- Giữ access token trong thời gian ngắn theo thiết kế.
- Có quy trình refresh/revoke phù hợp.
- Tránh đặt token trong URL query string vì URL dễ xuất hiện trong log, browser history và telemetry.

### 4.1. Access token và refresh token

Access token thường được gửi trong Authorization header đến resource server. Refresh token được dùng ở token endpoint để xin access token mới; nó không nên được gửi cho mọi API resource.

Ví dụ:

```http
POST /oauth/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<REDACTED>
```

Định dạng chính xác phụ thuộc authorization server và OAuth flow. Ví dụ trên chỉ minh họa refresh request; đừng dùng nó như một cấu hình OAuth hoàn chỉnh.

## 5. CSRF và XSS: rủi ro khác nhau giữa hai cách

### 5.1. Vì sao cookie thường cần quan tâm CSRF?

Browser tự gửi cookie phù hợp khi request đáp ứng các quy tắc cookie. Một trang độc hại có thể tìm cách khiến browser của người dùng gửi request đến một site khác; nếu cookie xác thực được tự động đính kèm, request có thể mang theo session của người dùng.

Đó là nền tảng của Cross-Site Request Forgery (CSRF). Các biện pháp thường phối hợp:

- SameSite cookie phù hợp với flow.
- CSRF token được kiểm tra ở server.
- Kiểm tra Origin/Referer trong bối cảnh thích hợp.
- Không dùng GET cho thao tác thay đổi trạng thái.
- Cấu hình CORS và cookie credentials đúng mục đích.

Không giả định SameSite luôn đủ. Luồng SSO, cross-site frontend/API hoặc yêu cầu tương thích browser có thể cần thiết kế CSRF cụ thể.

### 5.2. Bearer token không loại bỏ rủi ro XSS

Nếu ứng dụng browser giữ access token trong nơi JavaScript truy cập được, XSS có thể đọc token hoặc thực hiện request dưới quyền người dùng. Nếu token không thể đọc được nhưng mã độc chạy trong origin vẫn có thể thao tác giao diện và gửi request từ context của người dùng.

Do đó, bearer header không phải giải pháp tự động an toàn hơn cookie. Cần bảo vệ XSS, kiểm soát nội dung, CSP phù hợp, tránh đưa token vào nơi lưu trữ dễ bị lấy cắp và cân nhắc mô hình backend-for-frontend nếu kiến trúc cần giữ token phía server.

## 6. CORS và hành vi browser

Cookie và Authorization header có ảnh hưởng khác nhau đến CORS:

- Request cross-origin dùng cookie cần browser cho phép credentials; client fetch thường cần credentials: include trong tình huống cross-origin.
- Server cần trả Access-Control-Allow-Credentials: true và Access-Control-Allow-Origin phải là origin cụ thể phù hợp; không thể dùng wildcard * cho credentialed response.
- Authorization không phải CORS-safelisted request header; browser thường gửi preflight OPTIONS để server xác nhận header được phép.
- Với cookie cross-site, thuộc tính SameSite và Secure cũng ảnh hưởng việc browser có gửi cookie hay không.

Ví dụ fetch dùng cookie:

```javascript
fetch("https://api.example.test/api/profile", {
  method: "GET",
  credentials: "include"
});
```

Ví dụ client chủ động gắn bearer token:

```javascript
fetch("https://api.example.test/api/profile", {
  method: "GET",
  headers: {
    "Authorization": "Bearer " + accessToken
  }
});
```

Đây là minh họa phía browser. Một HTTP client không phải browser có thể không áp dụng CORS hoặc cookie policy giống browser; vì thế kết quả test MockMvc không chứng minh browser cross-origin behavior.

## 7. Tài liệu hóa cookie và Authorization bằng Spring REST Docs

Spring REST Docs có API descriptor riêng cho cookie và header:

| Thành phần HTTP | REST Docs API |
| --- | --- |
| Request cookie | requestCookies(cookieWithName(...)) |
| Response cookie | responseCookies(cookieWithName(...)) |
| Request Authorization header | requestHeaders(headerWithName("Authorization")...) |
| Response header | responseHeaders(headerWithName(...)) |

Cookie được truyền qua header HTTP trên wire, nhưng REST Docs có thể tạo snippet cookie riêng để mô tả từng cookie dễ đọc hơn. Không cần mô tả một cookie đồng thời như một request header Cookie và một request cookie descriptor trong cùng bảng nếu điều đó tạo nội dung trùng lặp; chọn snippet phản ánh mục tiêu trang.

### 7.1. Mô tả request cookie

```java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;

document("profile-cookie",
    requestCookies(
        cookieWithName("SESSION")
            .description("Session identifier do server cấp sau khi đăng nhập")
    )
)
```

### 7.2. Mô tả response cookie

```java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;

document("login-cookie",
    responseCookies(
        cookieWithName("SESSION")
            .description("Session cookie; client gửi lại trong request cần xác thực")
    )
)
```

Cookie descriptor mô tả tên và ý nghĩa cookie. Các thuộc tính như Path, HttpOnly, Secure, SameSite vẫn cần được thể hiện qua response header/snippet hoặc phần giải thích bổ sung, tùy cách bố trí tài liệu.

### 7.3. Mô tả Authorization header

```java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;

document("orders-bearer",
    requestHeaders(
        headerWithName(HttpHeaders.AUTHORIZATION)
            .description("Bearer access token; bắt buộc để gọi endpoint")
    )
)
```

Đây là request header, không phải cookie descriptor. requestHeaders(...) mô tả field Authorization; nó không tự xác thực token hay cấu hình Spring Security.

## 8. Thực hành MockMvc: xác thực bằng session cookie

Giả sử endpoint /api/profile dùng session cookie tên SESSION. Ví dụ test:

```java
@Test
void returnsProfileForValidSession() throws Exception {
    mockMvc.perform(get("/api/profile")
                    .cookie(new Cookie("SESSION", "documentation-session"))
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("user-42"))
            .andDo(document("profile-cookie",
                    preprocessRequest(
                            modifyHeaders(headers ->
                                    headers.set("Cookie", "SESSION=<REDACTED>"))
                    ),
                    requestCookies(
                            cookieWithName("SESSION")
                                    .description("Session identifier do server cấp")
                    ),
                    responseFields(
                            fieldWithPath("id").description("Mã người dùng")
                    )
            ));
}
```

Test dùng cookie giả và che nó trong snippet. Với Spring Security thực tế, cần bảo đảm MockMvc được cấu hình với security filter chain và session repository phù hợp. Nếu dùng standalone controller test không có security context thật, test không chứng minh được xác thực bằng session.

Test trường hợp thiếu cookie:

```java
@Test
void rejectsMissingSessionCookie() throws Exception {
    mockMvc.perform(get("/api/profile")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
}
```

Status ở ví dụ là hợp đồng giả định. Một ứng dụng có thể redirect đến login page hoặc trả lỗi khác tùy loại client và cấu hình security. Hãy assert behavior thực tế.

## 9. Thực hành MockMvc: xác thực bằng Bearer token

Với endpoint dùng Resource Server/JWT hoặc cơ chế Bearer riêng, client gửi Authorization header:

```java
@Test
void returnsOrdersForValidBearerToken() throws Exception {
    mockMvc.perform(get("/api/orders")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer documentation-token")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andDo(document("orders-bearer",
                    preprocessRequest(
                            replacePattern(
                                    Pattern.compile("Bearer [^\\\\s]+"),
                                    "Bearer <REDACTED>")
                    ),
                    requestHeaders(
                            headerWithName(HttpHeaders.AUTHORIZATION)
                                    .description("Bearer access token; bắt buộc")
                    ),
                    responseFields(
                            fieldWithPath("content").description("Danh sách đơn hàng")
                    )
            ));
}
```

Để test security có ý nghĩa, token giả phải được chấp nhận bởi test security setup hoặc dùng cơ chế test support phù hợp. Ví dụ này không tự tạo JWT hợp lệ; nếu application kiểm tra chữ ký JWT thực, hãy cấp token test hợp lệ hoặc dùng test decoder/converter được cấu hình có chủ đích.

Test token thiếu:

```java
@Test
void rejectsMissingBearerToken() throws Exception {
    mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
}
```

Và có thể thêm test cho token không đủ scope:

```java
@Test
void rejectsTokenWithoutRequiredScope() throws Exception {
    mockMvc.perform(get("/api/admin/reports")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer token-without-report-scope"))
            .andExpect(status().isForbidden());
}
```

401 và 403 trong ví dụ minh họa các tình huống xác thực và phân quyền khác nhau. Mapping thực tế phải theo security configuration và API error contract.

## 10. So sánh tài liệu cho hai endpoint

Giả sử API cung cấp hai nhóm endpoint:

| Endpoint | Cơ chế | Nội dung cần tài liệu hóa |
| --- | --- | --- |
| GET /browser/profile | Session cookie | Cookie SESSION, quy trình login, thuộc tính Set-Cookie, logout/expiry, CSRF nếu có |
| GET /service/orders | Bearer token | Authorization scheme, cách lấy access token, scope, expiry, refresh flow ở token endpoint |

Không nên gom hai cơ chế vào một câu “gửi token để xác thực”. Client cần biết credential được gửi ở đâu và ai chịu trách nhiệm gửi nó:

- Browser tự gửi cookie theo policy cookie.
- Client bearer chủ động gắn Authorization header.
- Cookie cần giải thích SameSite/CSRF trong browser flow.
- Bearer token cần giải thích scope, expiry, refresh và cách lưu an toàn.

Nếu một ứng dụng hỗ trợ cả hai cơ chế cho cùng API, tài liệu phải giải thích precedence và behavior khi request chứa cả cookie lẫn Authorization. Không để server âm thầm chọn credential theo thứ tự không được công bố.

## 11. Tiền xử lý và bảo vệ snippet

Cookie và Authorization thường chứa thông tin xác thực. Dùng dữ liệu giả và preprocessor để không lưu giá trị credential vào artifact.

Với Authorization:

```java
preprocessRequest(
    replacePattern(
        Pattern.compile("Bearer [^\\\\s]+"),
        "Bearer <REDACTED>"
    )
)
```

Với Cookie, nếu snippet cần thể hiện cơ chế session:

```text
Cookie: SESSION=<REDACTED>
```

Với Set-Cookie, giữ lại thuộc tính bảo mật:

```text
Set-Cookie: SESSION=<REDACTED>; Path=/; HttpOnly; Secure; SameSite=Lax
```

Nếu xóa hẳn Cookie hoặc Authorization khỏi exchange được tiền xử lý, descriptor tương ứng có thể không còn tìm thấy header/cookie trong snippet. Nếu muốn người đọc thấy cách xác thực, hãy thay giá trị chứ không xóa tên credential.

Kiểm tra toàn bộ artifact, không chỉ bảng cookie/header: credential có thể xuất hiện trong http-request, http-response, curl-request, log hoặc file debug.

## 12. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Browser gửi cookie nhưng MockMvc không xác thực | Test context thiếu security/session configuration hoặc cookie name không đúng | Kiểm tra filter chain, session repository và cookie thực tế |
| Browser không gửi cookie cross-site | SameSite, Secure, Domain, Path hoặc credentials/CORS chưa phù hợp | Kiểm tra cookie attributes và CORS policy ở browser |
| Authorization có trong code nhưng server trả 401 | Token hết hạn, sai issuer/audience/signature hoặc header format sai | Xác minh token và resource server configuration |
| REST Docs không tìm thấy Cookie descriptor | Preprocessor đã xóa Cookie trước khi tạo snippet | Thay giá trị hoặc bỏ descriptor nếu không công bố cookie |
| Header snippet lộ Bearer token | Thiếu request preprocessor hoặc regex không khớp | Dùng token giả, kiểm tra pattern và quét artifact |
| Hai cơ chế cùng được gửi nhưng behavior không rõ | API chưa định nghĩa credential precedence | Định nghĩa và test trường hợp cookie + Authorization cùng có |
| Cookie HttpOnly bị JavaScript đọc thất bại | Đây là behavior được thiết kế | Dùng request browser để gửi cookie; không đọc bằng document.cookie |
| Tài liệu bỏ sót CSRF | Chỉ mô tả cookie mà không giải thích browser auto-send | Bổ sung CSRF flow và test tương ứng |

## 13. Checklist chọn và tài liệu hóa cơ chế xác thực

- [ ] Xác định endpoint dùng session cookie, Bearer token hay cả hai.
- [ ] Mô tả credential được tạo/cấp như thế nào và client gửi ở đâu.
- [ ] Với cookie, nêu tên cookie và thuộc tính Path, Domain, Secure, HttpOnly, SameSite, expiry khi cần.
- [ ] Với Bearer, nêu scheme, cách lấy token, scope, expiry và refresh flow.
- [ ] Phân tích CSRF cho cookie và XSS/token theft cho client giữ Bearer token.
- [ ] Xác định CORS/credentials nếu browser gọi cross-origin.
- [ ] Dùng requestCookies/responseCookies cho cookie; requestHeaders cho Authorization.
- [ ] Có test credential hợp lệ, thiếu, sai và thiếu quyền.
- [ ] Che session/token trong snippet nhưng giữ mô tả cần thiết cho consumer.
- [ ] Nếu cùng endpoint hỗ trợ hai cơ chế, định nghĩa precedence rõ ràng.
- [ ] Kiểm tra snippet thô và tài liệu render trước khi phát hành.

## 14. Bài tập thực hành

Một hệ thống có:

- Web app dùng session cookie SESSION với HttpOnly, Secure và SameSite=Lax.
- API dành cho service-to-service dùng Authorization: Bearer access token.
- Endpoint /api/profile chỉ dùng session cookie.
- Endpoint /api/jobs chỉ dùng Bearer token với scope JOBS_READ.

Hãy thực hiện:

1. Viết tài liệu login giải thích response Set-Cookie và thuộc tính cookie.
2. Dùng requestCookies(...) để mô tả SESSION trong test /api/profile.
3. Viết test thiếu SESSION và session không hợp lệ; ghi lại behavior thực tế.
4. Dùng requestHeaders(...) để mô tả Authorization trong test /api/jobs.
5. Viết test thiếu token, token sai và token thiếu scope; phân biệt 401 với 403 theo contract.
6. Che giá trị SESSION và Bearer token trong snippet; giữ tên cookie/header và thuộc tính an toàn cần công bố.
7. Viết phần giải thích CSRF cho browser cookie flow và scope/expiry cho bearer flow.
8. Nếu web app gọi API cross-origin, kiểm tra credentials, SameSite và CORS bằng browser integration test phù hợp.

**Câu hỏi tự kiểm tra:** Có thể coi session cookie và Bearer token là giống nhau vì cả hai đều đại diện cho người dùng không? Không. Chúng có thể cùng xác thực principal nhưng được gửi và bảo vệ theo cách khác nhau. Browser tự đính kèm cookie theo policy, trong khi Bearer header thường do client chủ động thêm; vì vậy cách xử lý CSRF, CORS, lưu credential và tài liệu hóa cũng khác.

## Kết luận

Cookie và Authorization header đều có thể mang credential nhưng không thể tài liệu hóa như cùng một cơ chế. Cookie thường được browser tự gửi theo Domain, Path, Secure và SameSite; vì vậy cần mô tả vòng đời session, thuộc tính cookie và bảo vệ CSRF. Bearer token được client chủ động đặt trong Authorization header; tài liệu cần giải thích scheme, token acquisition, scope, expiry và refresh, đồng thời lưu ý nguy cơ lộ token/XSS. Trong Spring REST Docs, dùng requestCookies/responseCookies cho cookie và requestHeaders cho Authorization. HTTP test phải chứng minh credential hợp lệ, thiếu và sai; snippet phải che giá trị thực nhưng vẫn giữ đủ thông tin để consumer tích hợp chính xác.
