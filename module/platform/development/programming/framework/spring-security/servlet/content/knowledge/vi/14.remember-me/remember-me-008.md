# Rủi ro đánh cắp cookie và kiểm thử token hết hạn, bị sửa hoặc bị phát lại — Spring Security Servlet

## Mục tiêu và bối cảnh

Trong ứng dụng Spring Security chạy trên **Servlet / Spring MVC**, tính năng **“Ghi nhớ đăng nhập” (remember-me)** cho phép người dùng quay lại ứng dụng mà không phải nhập mật khẩu ở mỗi lần mở trình duyệt. Để làm được điều này, server có thể phát một **remember-me cookie** mang dữ liệu xác thực được kiểm tra ở những request tiếp theo khi chưa có một authentication hiện hành phù hợp.

Lợi ích tiện dụng đi kèm rủi ro: **ai sở hữu cookie còn hiệu lực có thể có cơ hội dùng nó để được nhận diện như người dùng**, không cần biết mật khẩu. Nếu cookie bị sao chép qua thiết bị khác, rò từ log, đường truyền không bảo vệ hoặc sự cố trình duyệt, đó có thể là một credential có giá trị.

Bài học tập trung đúng ba thử nghiệm và ý nghĩa an toàn:

1. **Token hết hạn:** browser ngừng gửi cookie vì `Max-Age/Expires`; nếu ai đó cố gửi lại chuỗi cookie cũ, server có từ chối theo hạn sử dụng của token không?
2. **Token bị sửa:** dữ liệu cookie bị thay đổi dù chỉ một ký tự; server có xác minh chữ ký hoặc đối chiếu token trong kho tin cậy, thay vì tin vào nội dung do client gửi không?
3. **Token bị phát lại (replay):** chính giá trị cookie đã được chấp nhận một lần bị gửi lại; cơ chế có phát hiện token cũ đã được xoay hay đơn giản chấp nhận cho đến lúc hết hạn?

Cần phân biệt **remember-me cookie**, **session cookie** và **access token**. Chúng có thể cùng được trình duyệt gửi tự động, nhưng được phát hành và kiểm chứng theo các hợp đồng khác nhau. Ví dụ dưới đây nhắm tới **Spring Security Servlet 6.x / Spring Boot 3.x / Java 17+**, không áp dụng trực tiếp cho Spring Security WebFlux hoặc JWT Resource Server.

**Ghi nhớ:** một token đã bị đánh cắp có thể được sử dụng thành công *trước khi* có dấu hiệu phát lại. Chữ ký, thời hạn, token rotation và cookie flags đều giảm rủi ro theo cách khác nhau; **không có cơ chế nào trong số đó tự bảo đảm “không bao giờ bị chiếm quyền truy cập”**.

## 1. Remember-me tham gia luồng authentication ở đâu?

Một website form login có thể có hai con đường hình thành authentication:

```text
Trình duyệt POST /login (username + password + CSRF token)
    |
UsernamePasswordAuthenticationFilter -> AuthenticationManager
    |
Đăng nhập thành công và người dùng chọn "remember-me"
    |
RememberMeServices.loginSuccess(...)
    |
Server trả Set-Cookie: remember-me=...
    |
----------------- REQUEST MỚI -----------------
    |
Browser gửi cookie (và có thể gửi session cookie)
    |
SecurityContextRepository nạp authentication từ session nếu có
    |
Nếu SecurityContext còn chưa có người dùng phù hợp:
    |
RememberMeAuthenticationFilter -> RememberMeServices.autoLogin(...)
    |
Đọc cookie -> xác minh chữ ký/token và hạn dùng
    |
RememberMeAuthenticationToken / AuthenticationManager
    |
SecurityContextHolder <- Authentication
    |
AuthorizationFilter / Controller
```

Sơ đồ chỉ mô tả trường hợp thông dụng; filter order và việc lưu context phụ thuộc cấu hình. Nếu một HTTP session đã có authentication hợp lệ, Spring Security thường không cần dùng remember-me cookie để xác thực lại trong request đó. Khi kiểm thử remember-me, **cố ý gửi request mới chỉ với cookie remember-me và không mang HTTP session đã đăng nhập**, nếu không kết quả có thể là session authentication chứ không phải remember-me.

`RememberMeServices` xử lý các hành động quan trọng:

- `loginSuccess(...)`: sau đăng nhập tương tác thành công, có thể phát remember-me cookie nếu người dùng yêu cầu và cấu hình cho phép.
- `autoLogin(...)`: đọc cookie từ request kế tiếp và khôi phục một authentication theo chính sách.
- `loginFail(...)`: xử lý/clear cookie phù hợp khi authentication flow thất bại.
- `logout(...)`: tham gia hủy cookie và xử lý token lưu phía server tùy implementation.

`RememberMeAuthenticationFilter` dùng dịch vụ này khi cần. Nó không tự định nghĩa thuật toán token. Trong Spring Security, hai implementation cần phân biệt là `TokenBasedRememberMeServices` và `PersistentTokenBasedRememberMeServices`.

## 2. Remember-me cookie khác HTTP session cookie

| Tiêu chí | Session cookie, thường là `JSESSIONID` | Remember-me cookie, thường là `remember-me` |
|---|---|---|
| Mục đích | Trỏ tới HTTP session hiện tại trên server | Cho phép khôi phục authentication khi không còn phiên tương tác hợp lệ |
| Giá trị thường mang | Session identifier | Token có chữ ký hoặc cặp series/token, tùy remember-me implementation |
| Phạm vi | Gắn với vòng đời server-side session và cookie | Có thể có thời hạn dài hơn session, nếu policy cho phép |
| Kiểm chứng | Servlet session store / session management | `RememberMeServices` và logic signature/repository |
| Thu hồi | Invalidate/delete server-side session, cấu hình logout | Clear cookie và/hoặc xóa bản ghi token tương ứng tùy implementation |
| Nếu bị lấy cắp | Người khác có thể thử chiếm phiên | Người khác có thể thử tự đăng nhập lại mà không cần password |
| Sau đổi mật khẩu | Không mặc nhiên xóa mọi session | Tùy loại remember-me; token-based có thể phụ thuộc password hash, persistent cần xóa record riêng |

Cookie chứa session identifier **không phải** là mật khẩu gốc. Nhưng cookie phiên cũng có giá trị như một credential trong khi session còn hoạt động. Việc bảo vệ remember-me không thay thế các kiểm soát session fixation, timeout, logout hoặc thu hồi phiên đang đăng nhập.

**Không nhầm with CSRF:** một cookie được browser tự gắn vào request có thể khiến hệ thống có rủi ro CSRF; remember-me là tiện ích authentication, không phải CSRF token. Với website cookie-based, cần giữ CSRF protection phù hợp, nhất là POST/PUT/PATCH/DELETE.

## 3. Hai kiểu remember-me trong Spring Security

### 3.1. TokenBasedRememberMeServices: cookie có thể tự kiểm chứng

`TokenBasedRememberMeServices` tạo một remember-me token có hạn sử dụng và **chữ ký dựa vào khóa server**, thông tin user và dữ liệu xác thực cần thiết. Format chi tiết đã thay đổi qua các thế hệ và phiên bản thuật toán; trong Spring Security 6.x hiện đại có thể gặp các trường như username, expiration time, tên thuật toán và chữ ký trong chuỗi được Base64-encode.

Ý tưởng:

```text
username + thời điểm hết hạn + metadata thuật toán + signature
                    |
             Base64 encode
                    |
               cookie value
                    |
Request mới: decode -> kiểm tra hạn -> load user -> xác minh signature
```

**Base64 không phải encryption.** Đọc được cookie không mặc nhiên có password, nhưng nội dung có thể chứa thông tin user/expiration/metadata không nên coi là bí mật. An toàn đến từ việc không thể tự tạo chữ ký hợp lệ khi không biết secret và dữ liệu liên quan, không đến từ Base64.

Điểm cần nhớ:

- **Sửa cookie:** signature phải không còn hợp lệ, server không tin phần username/expiration do client tự thay.
- **Hết hạn:** server kiểm tra expiration; cookie cũ không được chấp nhận dù client cố gửi.
- **Phát lại trước khi hết hạn:** một token còn hợp lệ **có thể được dùng nhiều lần**, vì cơ chế này không duy trì một danh sách token một lần dùng trong database. Signature không tự chống replay.
- **Thu hồi:** xoay khóa dùng để ký hoặc thay đổi dữ liệu user ảnh hưởng phép ký có thể vô hiệu một tập token, nhưng tác động khác nhau theo phiên bản. Không xem đây là cách per-device revocation đầy đủ.
- **Giảm tải:** không cần lưu từng remember-me token ở DB riêng, nhưng vẫn thường phải nạp user để xác minh thông tin và trạng thái phù hợp.

Token-based thường dễ triển khai, nhưng khó thu hồi có chọn lọc **một thiết bị duy nhất** nếu không bổ sung state hoặc chuyển sang persistent-token scheme.

### 3.2. PersistentTokenBasedRememberMeServices: series/token lưu server-side

`PersistentTokenBasedRememberMeServices` tạo **series identifier** và **token ngẫu nhiên**. Remember-me cookie thường chứa cặp `series:token` đã được encode. Server giữ một bản ghi liên kết series, token hiện hành, username và thời điểm sử dụng trong `PersistentTokenRepository`.

```text
Lúc đăng nhập:
  browser cookie: Base64(series-7 : token-A)
  server DB:      series-7 -> (alice, token-A, lastUsed)

Request auto-login với token-A:
  lấy record của series-7 từ DB
  so sánh presented token-A với stored token-A
  nếu khớp: phát token-B mới, lưu token-B vào DB
  browser nhận cookie: Base64(series-7 : token-B)

Ai đó gửi lại cookie cũ Base64(series-7 : token-A):
  series-7 còn tồn tại nhưng stored token là token-B
  -> token không khớp -> dấu hiệu bị đánh cắp/phát lại
  -> Spring Security persistent service có thể xóa các
     persistent remember-me tokens của user và từ chối.
```

Đây là chiến lược **token rotation + replay/theft detection**. Nó làm tăng khả năng phát hiện cookie bị sao chép, nhưng không bảo đảm kẻ tấn công không truy cập được trong lần sử dụng đầu tiên: nếu người cầm cookie đánh cắp gửi request trước, request đó có thể được chấp nhận và xoay token. Khi người dùng thật dùng bản cũ, hệ thống mới phát hiện bất thường.

**Không suy rộng hơn thực tế:** thao tác phát hiện token cũ và xóa persistent remember-me tokens **không đương nhiên hủy mọi HTTP sessions, refresh tokens hay JWT đang tồn tại**. Nếu cần “logout all devices”, ứng dụng phải có thêm chính sách thu hồi tương ứng.

### 3.3. So sánh kiểm chứng cookie

| Tình huống | Token-based có chữ ký | Persistent series/token |
|---|---|---|
| Cookie bị sửa nội dung | Chữ ký không hợp lệ, từ chối | Token/series không khớp hoặc không tồn tại, từ chối |
| Cookie hết hạn | Server kiểm tra hạn token | Server kiểm tra tuổi token/bản ghi theo policy |
| Replay cùng cookie trước hạn | Thường vẫn được chấp nhận nếu token đúng | Sau khi token đã được xoay, bản cũ có thể bị phát hiện |
| Server lưu token riêng | Thường không | Có: `PersistentTokenRepository` |
| Thu hồi riêng một token/thiết bị | Cần cơ chế bổ sung | Có thể xóa record theo series nếu có API/thiết kế quản trị phù hợp |
| Rủi ro khi DB token bị lộ | Không lưu list cookie token theo kiểu này | Lộ store có thể tạo rủi ro; phải bảo vệ token records và backup |
| Độ phức tạp | Ít state, đơn giản hơn | DB/store, rotate, concurrency, cleanup, incident response |
| Bảo đảm chống trộm cookie | Không ngăn người sở hữu cookie hợp lệ sử dụng nó | Có khả năng phát hiện replay sau rotate, không chặn được lần dùng đầu |

**Lưu ý concurrency:** hai request gần nhau dùng cùng một cookie persistent token có thể tranh đua việc xoay token, đặc biệt khi cookie chưa đến client kịp. Một request đến sau có thể trông như reuse token đã xoay. Vì vậy hệ thống production cần xem xét luồng browser song song, transactional update, logging, trải nghiệm xử lý nghi ngờ theft và cách giảm false positives. Đừng chỉ quan sát hai request đơn luồng rồi khẳng định không còn tình huống race.

## 4. Các con đường đánh cắp cookie

Rủi ro không chỉ xuất hiện khi ứng dụng có XSS; cần đánh giá toàn bộ đường đi của credential.

1. **XSS hoặc script độc hại:** có thể đọc cookie thiếu `HttpOnly`; ngay cả khi `HttpOnly`, XSS vẫn có thể gửi request từ trình duyệt đang đăng nhập hoặc thực hiện hành vi khác trong cùng origin.
2. **HTTP không được bảo vệ:** khi cookie không có `Secure` hoặc client sử dụng HTTP, attacker trên đường truyền có thể khai thác rủi ro rò credential. Production nên dùng HTTPS, HSTS phù hợp và cookie `Secure`.
3. **Logs, traces và proxy:** log request header `Cookie`, response header `Set-Cookie` hoặc full HTTP capture có thể ghi lại raw bearer credential.
4. **Trình duyệt, extension hoặc thiết bị bị xâm nhập:** một extension có quyền cao, malware hoặc cấu hình profile bị đánh cắp có thể làm lộ cookie dù có nhiều cờ bảo vệ.
5. **Sao lưu/công cụ hỗ trợ:** export HAR, screenshot DevTools, ticket support hoặc crash report có thể vô tình chứa cookie.
6. **Cookie domain/path sai:** scope quá rộng làm cookie xuất hiện ở subdomain hoặc endpoint không cần thiết. Một subdomain kém tin cậy có thể mở rộng bề mặt tấn công.
7. **Session fixation và cookie injection:** đặt tên/path/domain cookie không nhất quán có thể làm hệ thống xử lý nhầm nhiều cookie cùng tên hoặc tin cookie do context khác tạo.
8. **Thời hạn quá dài:** càng nhiều ngày một token còn hiệu lực, cửa sổ cho kẻ đã lấy cookie càng rộng.
9. **Không xóa persistent tokens:** logout trên UI nhưng record còn được chấp nhận ở server có thể làm cookie đánh cắp tiếp tục có giá trị.
10. **Chấp nhận token dù user bị khóa hoặc bị xóa:** nếu server không kiểm tra user status và không revoke cookie, chính sách khóa tài khoản có thể không thực sự có hiệu lực.

Không bao giờ yêu cầu người dùng gửi nguyên cookie để “hỗ trợ debug”. Nếu cần điều tra, dùng ID nội bộ, mã tương quan và những dấu vết đã được kiểm soát; tránh lưu raw secret/token/signature.

## 5. Cookie flags giúp gì và không giúp gì?

| Thuộc tính | Tác dụng | Giới hạn |
|---|---|---|
| `Secure` | Browser chỉ gửi cookie qua kết nối HTTPS phù hợp | Không sửa được lỗi XSS, extension độc hại hoặc cookie đã bị copy |
| `HttpOnly` | Hạn chế truy cập cookie bằng client-side JavaScript thông thường | XSS vẫn có thể điều khiển request, không chống CSRF hay browser compromise |
| `SameSite=Lax/Strict/None` | Điều chỉnh việc cookie được gửi trong ngữ cảnh cross-site | Không thay thế CSRF token và cần tương thích flow OAuth/cross-site thực tế |
| `Path` | Giới hạn path được browser gửi cookie | Không phải hàng rào authorization mạnh, không chặn mọi tình huống cùng origin |
| `Domain` | Giới hạn host/domain scope | Domain quá rộng có thể làm tăng rủi ro từ subdomain |
| `Max-Age/Expires` | Giới hạn thời gian browser giữ cookie | Server **vẫn phải tự kiểm tra hạn token** nếu client cố gửi dữ liệu đã cũ |

Cần thiết kế đồng bộ: HTTPS, reverse proxy forwarding headers, HSTS, CSP/XSS prevention, CSRF protection, logout và kiểm soát truy cập vào session/token repository. Không chỉ bật `HttpOnly` rồi tuyên bố “cookie không thể bị đánh cắp”.

**Đừng nhầm lifetime:** thời gian sống của HTTP session, thời hạn cookie remember-me và thời gian tồn tại token trong persistent repository có thể khác nhau. Nếu ràng buộc “ghi nhớ 14 ngày”, server phải có policy expiry phù hợp và dọn record hết hạn; riêng browser Max-Age không đủ.

## 6. Kiểm thử token hết hạn: browser expiry khác server expiry

Một bài test thủ công thường chỉ đợi cookie biến mất khỏi browser, rồi xác nhận user phải login lại. Test đó hữu ích, nhưng **chưa chứng minh server từ chối token cũ** vì browser có thể chỉ đơn giản là không gửi nó nữa.

Test mạnh hơn:

1. Đăng nhập thành công, chọn remember-me và ghi nhận cookie **trong môi trường test**.
2. Kiểm tra một request mới chỉ mang remember-me cookie trước hạn: được khôi phục đúng.
3. Giữ lại chuỗi token trong bộ nhớ test, đợi thời hạn server đã cấu hình đi qua.
4. Tạo request mới **cố ý gửi lại cookie cũ**, mô phỏng client bất thường không tuân thủ Max-Age.
5. Xác nhận server không khôi phục authentication: tài nguyên private trả 401 hoặc redirect tới login tùy entry point.
6. Xác nhận thất bại không gây HTTP 500, không tạo quyền và không in secret ra log.

Với một số thư viện, có thể dùng clock được inject hoặc fake clock để tránh `Thread.sleep`. Ví dụ MockMvc ở mục 10 cố định thời hạn **2 giây** chỉ để chạy nhanh nên dùng sleep có khoảng đệm. Production không nên đặt remember-me TTL ngắn như vậy, và test thời gian dài nên thay bằng clock được kiểm soát khi API hỗ trợ.

**Thời gian trong cookie không được là nguồn đáng tin độc lập.** Với token-based, expiration nằm trong nội dung đã được ký. Với persistent-token, server dùng thời điểm lưu trong repository/TTL có kiểm soát. Nếu chỉ đọc `expires=...` do client truyền mà không kiểm chứng tính toàn vẹn, attacker có thể tự kéo dài hạn.

## 7. Kiểm thử token bị sửa: xác thực tính toàn vẹn

Chọn một cookie hợp lệ, sau đó **thay đổi phần token/signature mà vẫn giữ format hợp lệ**. Ví dụ persistent cookie gồm dữ liệu Base64 của `series:token`:

```text
Gốc, được phát hành từ server:
  Base64(series-123:token-ABC)

Cookie bị sửa (không phải token được server cấp):
  Base64(series-123:token-XYZ)
```

Test đúng cần bảo đảm:

- Trước sửa, cookie thực sự được auto-login thành công nếu gửi không kèm session.
- Sau sửa, request private **không được xác thực**.
- Service không bỏ qua bước kiểm tra chỉ vì Base64 parse thành công; decode không đồng nghĩa verify.
- Response là từ chối/redirect có kiểm soát, không crash do parse hoặc lỗi mảng.
- Với persistent scheme, thay một token ở series hợp lệ có thể được xem là **theft/replay signal** và làm toàn bộ remember-me tokens của user bị xóa theo implementation. Test nên dùng dữ liệu cô lập vì thao tác này có side effect.
- Với token-based, sửa chữ ký hoặc thời hạn phải làm kiểm tra signature thất bại; test cụ thể cần theo format của phiên bản đang chạy, không tự lấy mẫu cookie của phiên bản cũ rồi coi là tương thích vĩnh viễn.

Một test chỉ gửi chuỗi không phải Base64 rồi nhận 401 **chưa đủ để chứng minh signature verification**: có thể server chỉ từ chối vì parse error. Hãy có cả case **format đúng nhưng token không khớp**, và case malformed/missing fields để đảm bảo handler robust.

## 8. Kiểm thử replay: hai mô hình có kết quả khác nhau

“Phát lại” là **gửi lại một credential đã từng hợp lệ**, không phải sửa nội dung nó. Với bearer credential, người giữ token thực sự có thể dùng nó mà không cần biết mật khẩu; vì vậy không thể luôn phân biệt replay hợp pháp với token bị copy bằng một phép hash.

### 8.1. Replay với token-based

Nếu signed token vẫn hợp lệ, chưa hết hạn và không thay đổi các dữ liệu làm signature vô hiệu, **gửi lại cùng remember-me cookie thường vẫn xác thực thành công**. Đây là trade-off của cơ chế stateless/token-based. Chữ ký chống **tampering**, không tự chống **replay**.

Hãy coi test “replay hai lần đều thành công” là bằng chứng để chọn policy phù hợp, không coi nó là bug của signature. Nếu yêu cầu revoke một thiết bị hoặc phát hiện reuse, cần state phía server hoặc một cơ chế khác.

### 8.2. Replay với persistent token đã được xoay

Các bước:

```text
POST login -> cookie A = (series S, token T1), DB stores T1

GET private với cookie A:
  -> 200
  -> DB rotates T1 -> T2
  -> response Set-Cookie B = (series S, token T2)

GET private với cookie A một lần nữa:
  -> presented T1, stored T2
  -> mismatch, suspected cookie theft/replay
  -> reject, server removes persistent tokens for user

GET private với cookie B:
  -> có thể bị từ chối vì records đã bị xóa sau replay
```

**Cảnh báo rất quan trọng:** request đầu tiên dùng cookie bị đánh cắp **có thể thành công và nhận cookie T2**. Rotation giúp phát hiện sự cố khi có reuse bản cũ, nhưng **không giúp server biết ai là chủ cookie hợp pháp**. Nếu attacker có khả năng tiếp tục đọc cookie mới của nạn nhân thì việc xoay token không giải quyết tận gốc.

Dựa trên nguồn phát hiện replay, một hệ thống cần cơ chế phản ứng: ghi audit không chứa secrets, yêu cầu user đăng nhập lại, thu hồi các loại token khác theo risk policy, thông báo người dùng qua kênh độc lập khi phù hợp, và giám sát nhiều node/thiết bị. Không đưa địa chỉ IP vào logic “chỉ IP cũ mới được dùng” một cách cứng nhắc, vì roaming/mobile/NAT/proxy có thể thay đổi IP hợp lệ.

## 9. Phân biệt authentication được nhớ và fully authenticated

Spring Security có thể sử dụng `RememberMeAuthenticationToken` cho người dùng được nhận diện qua remember-me cookie. Điều này thường **yếu hơn** một lần login tương tác gần đây, vì cookie có thể bị sao chép và không chứng minh người dùng vừa nhập credential/MFA.

Có thể dùng rule phân quyền khác nhau:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/sensitive").fullyAuthenticated()
    .anyRequest().authenticated())
```

Đây là mảnh cấu hình `HttpSecurity`. Với request chỉ được nhận diện bằng remember-me, `authenticated()` có thể đủ cho trang thông thường nhưng `fullyAuthenticated()` yêu cầu authentication không phải anonymous/remember-me; khi đó ứng dụng có thể yêu cầu login tương tác thay vì cho thực hiện thao tác nhạy cảm.

**Không nhầm fullyAuthenticated với xác thực MFA đầy đủ.** Điều kiện này phân biệt remember-me/anonymous với authentication tương tác theo Spring Security; yêu cầu MFA hoặc xác thực nâng cao cần policy và flow riêng.

Một trang nội bộ như danh sách tin tức có thể cho dùng remember-me, nhưng đổi email, đổi password, xem bí mật, thực hiện thanh toán hoặc cấp quyền admin nên đòi reauthentication/step-up theo mức rủi ro.

## 10. Demo Spring Boot Servlet có test expiry, tamper và replay

Ví dụ sau dùng **Spring Boot 3.3.5 (Spring Security 6 do Boot quản lý), Java 17 và Maven** làm mốc học tập ổn định, **không khẳng định là phiên bản mới nhất hoặc còn trong vòng hỗ trợ**. Khi xây sản phẩm thực tế, dùng phiên bản còn được hỗ trợ và đối chiếu API tương ứng.

Demo cố ý sử dụng `InMemoryTokenRepositoryImpl` để kiểm chứng thuật toán **persistent remember-me**. Nó không bền sau restart và **không dùng cho production/cluster**. Production nên dùng một implementation lưu trữ đáng tin, ví dụ JDBC với schema phù hợp, có backup/retention/access control và hỗ trợ nhiều node.

**Giới hạn khác:** key demo hard-coded chỉ phục vụ fixture. Product phải lấy bí mật từ secret manager/config an toàn, đủ entropy, có chính sách rotation. Tài khoản/mật khẩu mẫu cũng không được đưa lên Internet.

### 10.1. Cấu trúc

```text
remember-me-security-demo/
├── pom.xml
└── src/
    ├── main/java/example/rememberme/
    │   ├── RememberMeApplication.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/example/rememberme/
        └── RememberMeSecurityTest.java
```

### 10.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>remember-me-security-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.3. Entry point

Tạo `src/main/java/example/rememberme/RememberMeApplication.java`:

```java
package example.rememberme;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RememberMeApplication {
    public static void main(String[] args) {
        SpringApplication.run(RememberMeApplication.class, args);
    }
}
```

### 10.4. SecurityConfiguration

Tạo `src/main/java/example/rememberme/SecurityConfiguration.java`:

```java
package example.rememberme;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.rememberme.InMemoryTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-only-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    PersistentTokenRepository tokenRepository() {
        return new InMemoryTokenRepositoryImpl();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            PersistentTokenRepository tokenRepository) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/error").permitAll()
                .requestMatchers("/sensitive").fullyAuthenticated()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/private", true)
                .permitAll())
            .rememberMe(remember -> remember
                .key("demo-only-long-fixed-key-not-for-production")
                .tokenRepository(tokenRepository)
                .tokenValiditySeconds(2))
            .build();
    }
}
```

Đây là cấu hình **persistent remember-me** vì đã cung cấp `PersistentTokenRepository`. Không có token repository, cấu hình mặc định có thể chọn token-based remember-me tùy cách Spring Security được cấu hình; việc chọn chế độ cần kiểm tra thật qua chain và cookie.

Trong demo, token validity chỉ **2 giây** để kiểm tra expiry. Khi triển khai thật, phải chọn thời hạn theo phân tích rủi ro và yêu cầu người dùng; không sao chép số 2 giây này. Authentication form login vẫn dùng HTTP session thông thường; remember-me cookie là lựa chọn thêm qua form parameter `remember-me=on`.

**Bảo mật cần bổ sung ở production:** HTTPS, cookie Secure/HttpOnly/SameSite phù hợp, secret management, token repository dùng chung, giới hạn các luồng nhạy cảm chỉ cho `fullyAuthenticated`, kiểm tra account lock/disable và logout/revocation.

### 10.5. Controller

Tạo `src/main/java/example/rememberme/DemoController.java`:

```java
package example.rememberme;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "PUBLIC_OK";
    }

    @GetMapping("/private")
    public String privatePage(Principal principal) {
        return "Hello, " + principal.getName();
    }

    @GetMapping("/sensitive")
    public String sensitive(Principal principal) {
        return "SENSITIVE: " + principal.getName();
    }
}
```

Trang `/private` chỉ yêu cầu authenticated. Trang `/sensitive` yêu cầu `fullyAuthenticated()` nên người dùng chỉ có remember-me cookie phải được yêu cầu đăng nhập tương tác.

### 10.6. JUnit + MockMvc tests

Tạo `src/test/java/example/rememberme/RememberMeSecurityTest.java`:

```java
package example.rememberme;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RememberMeSecurityTest {

    @Autowired
    MockMvc mvc;

    private Cookie loginAndGetRememberMeCookie() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only-password")
                .param("remember-me", "on"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/private"))
            .andReturn();

        Cookie cookie = login.getResponse().getCookie("remember-me");
        assertThat(cookie).isNotNull();
        assertThat(cookie.getValue()).isNotBlank();
        return cookie;
    }

    private Cookie tamperPersistentToken(Cookie cookie) {
        String decoded = new String(
            Base64.getDecoder().decode(cookie.getValue()),
            StandardCharsets.UTF_8
        );
        String[] fields = decoded.split(":", -1);
        assertThat(fields).hasSize(2);

        String oldToken = fields[1];
        assertThat(oldToken).isNotEmpty();
        String alteredToken = (oldToken.startsWith("A") ? "B" : "A")
            + oldToken.substring(1);

        String forgedPayload = fields[0] + ":" + alteredToken;
        String forgedValue = Base64.getEncoder().encodeToString(
            forgedPayload.getBytes(StandardCharsets.UTF_8)
        );
        return new Cookie("remember-me", forgedValue);
    }

    @Test
    void publicRequestDoesNotNeedLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void withoutRememberMeCookiePrivateRequiresLogin() throws Exception {
        mvc.perform(get("/private"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void rememberMeIsOptInForTheForm() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        assertThat(login.getResponse().getCookie("remember-me")).isNull();
    }

    @Test
    void validCookieRestoresAuthenticationWithoutAnOldHttpSession()
            throws Exception {
        Cookie cookie = loginAndGetRememberMeCookie();

        mvc.perform(get("/private").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello, alice"));
    }

    @Test
    void expiredCookieIsRejectedByServerEvenIfClientResendsIt()
            throws Exception {
        Cookie cookie = loginAndGetRememberMeCookie();

        // TTL demo là 2 giây; cố tình gửi cookie cũ sau lúc hết hạn.
        Thread.sleep(2800L);

        mvc.perform(get("/private").cookie(cookie))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void modifiedTokenWithValidBase64FormatIsRejected()
            throws Exception {
        Cookie cookie = loginAndGetRememberMeCookie();
        Cookie modified = tamperPersistentToken(cookie);

        mvc.perform(get("/private").cookie(modified))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void replayOfOldTokenAfterRotationIsDetected() throws Exception {
        Cookie original = loginAndGetRememberMeCookie();

        MvcResult firstAutoLogin = mvc.perform(
                get("/private").cookie(original))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello, alice"))
            .andReturn();

        Cookie rotated = firstAutoLogin.getResponse().getCookie("remember-me");
        assertThat(rotated).isNotNull();
        assertThat(rotated.getValue()).isNotEqualTo(original.getValue());

        // Gửi lại token T1 sau khi repository đã thay bằng T2.
        mvc.perform(get("/private").cookie(original))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));

        // Persistent-token service đã xóa tokens của user khi nghi theft.
        mvc.perform(get("/private").cookie(rotated))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void rememberMeDoesNotSatisfyFullyAuthenticated()
            throws Exception {
        Cookie cookie = loginAndGetRememberMeCookie();

        mvc.perform(get("/sensitive").cookie(cookie))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }
}
```

**Giải thích cách test phân biệt cơ chế thật:**

- Các request `get("/private").cookie(cookie)` cố ý **không gọi `.session(...)`**. Nhờ đó, kết quả không dựa vào HTTP session được tạo khi POST login, mà kiểm tra chính `RememberMeAuthenticationFilter`/persistent cookie.
- Test expired **cố tình đưa cookie đã quá hạn vào request**; browser thật có thể không gửi cookie đó, nhưng server vẫn phải bác bỏ.
- Test tamper sửa **token nhưng giữ Base64 và series hợp lệ**, do đó đi xa hơn việc kiểm tra một chuỗi format lỗi. Persistent repository phát hiện token khác giá trị lưu.
- Test replay có một lần auto-login đầu tiên được chấp nhận và **xoay token**, sau đó cố phát lại cookie cũ. Đây là tình huống chính mà persistent-token design có thể phát hiện.
- Sau replay, code của Spring Security persistent service có thể xóa các record remember-me của user; assertion cuối xác nhận cookie mới cũng không còn đủ để khôi phục authentication trong demo. Đây không phải cam kết rằng mọi HTTP session hay bearer token khác trên server đều đã bị hủy.
- Test `fullyAuthenticated()` chứng minh nhớ đăng nhập không đủ điều kiện cho endpoint nhạy cảm; vì vậy không phải endpoint nào cũng nên cho cookie remember-me tự khôi phục phiên.

**Kết quả dự kiến:** 8 JUnit tests thành công khi code, dependencies và phiên bản đúng như mô tả. Trong một môi trường nhiều requests đồng thời, rotation/replay có thể gặp race; test MockMvc tuần tự **không thay thế** test concurrency hoặc real browser. Ví dụ chưa được chạy trên máy thật trong tài liệu này.

### 10.7. Chạy ứng dụng và kiểm tra bằng trình duyệt

Từ thư mục `remember-me-security-demo`, cần JDK 17+ và Maven có thể resolve dependencies:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Khi server đang chạy ở cổng 8080 mặc định, mở `http://localhost:8080/login` trên **máy phát triển** và dùng tài khoản demo `alice / demo-only-password`. Bật ô remember-me trên form (nếu trang login hiện tùy chọn tương ứng) rồi quan sát cookie được phát.

**Không đưa ứng dụng có key/mật khẩu mẫu hoặc lưu token trong memory này lên mạng công khai.** Ở production phải dùng HTTPS và cookie flags đúng cấu hình; đường dẫn HTTP ở đây chỉ phục vụ localhost để học.

Khi kiểm tra thủ công, đừng copy giá trị cookie thật lên chat, issue tracker hoặc screenshot. Dùng DevTools trên máy được kiểm soát để xem tên cookie, các cờ Secure/HttpOnly/SameSite, Path và Max-Age — không chia sẻ secret value.

## 11. Kiểm thử token-based nếu không dùng persistent repository

Mục 10 dùng persistent token để thấy khả năng phát hiện replay. Còn nếu ứng dụng sử dụng `TokenBasedRememberMeServices` (không lưu mỗi token trong DB), các kỳ vọng khác nhau:

- **Hết hạn:** cookie dù có chữ ký đúng nhưng expiration đã qua phải bị từ chối.
- **Bị sửa:** thay username, expiration, algorithm hoặc signature rồi Base64 lại vẫn không tạo chữ ký hợp lệ; server phải từ chối.
- **Replay trước hạn:** cùng cookie hợp lệ có thể được chấp nhận nhiều lần, vì server không có record “token này đã dùng rồi”. Test phải phản ánh đúng đặc tính; không ép assert 401 cho mọi replay nếu design không có state.
- **Xoay khóa:** có thể vô hiệu nhiều token đang lưu ở browser; đòi hỏi kế hoạch rollout và hỗ trợ user.
- **Thay hash mật khẩu:** token-based verification có thể chịu tác động bởi giá trị password từ UserDetails trong chữ ký, tùy version; cần test riêng. Không giả định đổi mật khẩu cũng vô hiệu mọi `HttpSession` hoặc persistent cookie.

Một bài test chống replay cho token-based có thể **chứng minh giới hạn**, thay vì chứng minh server không chấp nhận lại. Nếu sản phẩm cần phát hiện stolen-cookie reuse, hãy chọn thiết kế có server-side state và rotation theo yêu cầu; đừng tự chế cơ chế nonce/counter trong cookie mà không xem xét concurrency và revocation.

## 12. Logout, khóa tài khoản và thu hồi remember-me cookie

Khi người dùng nhấn logout, có ít nhất hai nơi trạng thái có thể tồn tại:

1. **HTTP session** đang giữ `SecurityContext`.
2. **Remember-me cookie và persistent token store** có thể giúp khôi phục authentication sau khi session không còn.

Nếu logout chỉ invalidate session mà vẫn để remember-me token hợp lệ, request mới có thể được tự đăng nhập lại bằng cookie. Trong flow chuẩn, cần đảm bảo `RememberMeServices` tham gia logout để clear cookie và xử lý persistent records theo implementation. Với yêu cầu “logout all devices”, thiết kế thêm cơ chế xóa mọi series của user hoặc invalidation marker tương đương; **xóa một cookie trên thiết bị hiện tại không xóa bản copy của nó ở thiết bị khác**.

Với account bị khóa/disabled hoặc bị phát hiện rủi ro:

- Chặn đăng nhập mới tại provider/checker.
- Thu hồi persistent remember-me tokens theo user/series và làm token-based cookies không còn đủ điều kiện được chấp nhận khi cần.
- Xem xét tất cả HTTP sessions đã đăng nhập, không chỉ remember-me.
- Thu hồi refresh tokens, remember-me/SSO sessions bên ngoài hoặc các credentials khác theo policy.
- Đảm bảo các request đang chạy và cache quyền/role không tiếp tục cho phép thao tác nhạy cảm trái quyền.
- Audit và thông báo sự cố theo chính sách bảo mật, không gửi token/raw cookie trong email.

Với persistent remember-me, xóa record theo user có thể làm các cookie đó mất tác dụng ở lần tự đăng nhập sau. Tuy nhiên request đã nạp Authentication trước lúc xóa record **không tự bị dừng**; với tác vụ nhạy cảm cần revalidation và authorization ở business boundary.

## 13. Lỗi thực tế thường gặp

| Triệu chứng | Cần phân biệt | Hướng điều tra |
|---|---|---|
| Người dùng hết session nhưng vẫn tự đăng nhập | Remember-me cookie còn hợp lệ | Đây có thể là tính năng đúng; kiểm tra policy và fullyAuthenticated cho tác vụ nhạy cảm |
| Xóa cookie ở browser nhưng máy khác vẫn login | Chỉ cookie hiện tại bị xóa, token copy/server record còn | Thực hiện server-side revocation khi cần |
| Cookie bị sửa nhưng request vẫn 200 | Có thể request đang có **HTTP session** hợp lệ | Test lại request chỉ với remember-me cookie, không kèm session |
| Cookie hết hạn nhưng request vẫn được phép | Có session khác, clock lệch, expiry chỉ ở browser hoặc server không kiểm tra | Test resend cookie cũ ở request không có session và kiểm tra logic server |
| Token-based cookie được replay nhiều lần trước hạn | Stateless signed token cho phép reuse | Không coi signature là one-time token; đổi thiết kế khi cần phát hiện replay |
| Persistent token cũ bị reuse và user phải login lại trên mọi thiết bị | Theft detection loại bỏ tokens của user | Điều tra cookie theft/concurrent requests, audit và hướng dẫn re-login |
| Nhiều tab cùng lúc gây lỗi cookie theft giả | Two requests cùng token trước khi rotation tới client | Kiểm tra race/transaction/update/token-rotation policy |
| Sau đổi mật khẩu, remember-me vẫn hoạt động | Persistent token chưa bị revoke hoặc cơ chế logout khác | Xóa record, kiểm tra chính sách thay password |
| Sau logout, trang mới vẫn authenticated | Cookie nhớ đăng nhập hoặc session chưa bị hủy đúng | Kiểm tra logout handler, Set-Cookie, store và request sau |
| Test dùng `@WithMockUser` pass dù cookie hỏng | Mock user bypass remember-me authentication | Dùng MockMvc request thực sự có cookie và không có session |
| Cookie có `HttpOnly` nhưng vẫn bị lạm dụng | XSS có thể gửi request, thiết bị/extension bị chiếm | CSP, chống XSS, CSRF, endpoint reauth, session policy |
| Production ghi token vào HTTP access log | Logging `Cookie`/`Set-Cookie` chưa được redact | Ẩn secret ở reverse proxy/APM và kiểm toán log retention |

Một lỗi phổ biến khác là **server có hai remember-me configs khác nhau** trên các `SecurityFilterChain` hoặc instance: khóa ký/thuật toán/cookie name/repository không thống nhất. Khi đó người dùng gặp đăng nhập lúc được lúc không. Cần thống nhất cấu hình trong đúng chain, nhưng không bao giờ ghép toàn bộ cluster vào một session registry in-memory rồi cho rằng đã có revocation toàn cục.

## 14. Kiểm thử vận hành ngoài MockMvc

Unit/integration tests ở mục 10 giúp kiểm tra contract nhưng không bao quát mọi biên:

1. **Trình duyệt thật:** kiểm tra Secure, HttpOnly, SameSite, Domain, Path, thời hạn browser giữ cookie, HTTP→HTTPS redirect và HSTS.
2. **Nhiều thiết bị:** hai browser profiles/cookie jars riêng; đăng xuất một thiết bị và chọn “đăng xuất tất cả” phải có kết quả theo chính sách.
3. **Nhiều tab đồng thời:** gửi hai request mang cùng persistent token song song để đánh giá nguy cơ false-positive theft detection.
4. **Nhiều node:** login ở A, auto-login ở B, revoke ở C; token repo phải dùng chung và nhất quán.
5. **Clock và TTL:** kiểm tra đúng ranh giới hết hạn, clock skew và cleanup record; ưu tiên clock có thể điều khiển trong bộ test chuyên sâu.
6. **Mạng lỗi/retry:** khi server xoay token nhưng response Set-Cookie không đến browser, request sau có thể mang token cũ. Xem xét phản ứng với missing acknowledgment.
7. **Đổi mật khẩu, khóa tài khoản, giảm quyền:** phải xác minh session còn hoạt động và remember-me tokens cùng tuân theo policy.
8. **CSRF/XSS:** thao tác nguy hiểm không chỉ phụ thuộc cookie; kiểm tra CSRF token, output encoding và CSP.
9. **Quan sát/audit:** log các sự kiện hết hạn, token malformed, suspected replay theo mức cần thiết; không ghi raw credential/cookie.
10. **Cleanup:** xóa record hết hạn và tránh để token table tăng vô hạn, không làm mất tính nhất quán khi dùng background cleanup.

Không nên cố gắng “bắt mọi lần phát lại” bằng cách khóa người dùng theo IP/User-Agent bất kỳ thay đổi nào. Thông số đó có thể là tín hiệu điều tra, nhưng không phải bằng chứng nhận diện đáng tin; người dùng hợp lệ chuyển Wi-Fi/di động và các thiết bị sau NAT rất thường xuyên.

## 15. Checklist thiết kế và phát hành remember-me an toàn

- [ ] Đã chọn rõ `TokenBasedRememberMeServices` hay `PersistentTokenBasedRememberMeServices` và hiểu trade-off replay/revocation.
- [ ] Remember-me là **opt-in** theo yêu cầu sản phẩm; không tự ghi nhớ mọi login nếu chưa có cơ sở.
- [ ] Thời gian tồn tại được định nghĩa ở **server**, không chỉ qua Max-Age của browser.
- [ ] Cookie dùng HTTPS + Secure, HttpOnly, SameSite, Path, Domain đúng phạm vi; không leak trong URL/log/HAR.
- [ ] Secret signing key có entropy, bảo vệ và rotation policy phù hợp; không hard-code bí mật sản xuất.
- [ ] Persistent token store có access control, backup/retention, chỉ mục/transaction và hỗ trợ cluster đúng cách.
- [ ] Token bị sửa hoặc hết hạn không xác thực được **khi gửi lại không kèm session**, và không gây HTTP 500.
- [ ] Replay token đã được xoay được xử lý theo policy; có test race và phản ứng với suspected theft.
- [ ] Không đánh đồng replay detection với khả năng ngăn **lần dùng đầu tiên** của cookie bị đánh cắp.
- [ ] Endpoint nhạy cảm cần `fullyAuthenticated()` hoặc MFA/reauthentication, không chỉ `authenticated()` khi remember-me là yếu.
- [ ] CSRF protection vẫn áp dụng theo mô hình browser cookie; không xem SameSite là thay thế tuyệt đối.
- [ ] Logout và “logout all devices” thu hồi đúng remember-me token records cùng HTTP sessions và credentials khác khi cần.
- [ ] Khóa user, đổi password, hạ quyền được kiểm thử với cookie nhớ đăng nhập và session có từ trước.
- [ ] Tests bao gồm opt-out, auto-login thành công, expired, malformed, tampered, replay, rotated token và thiếu fully-authenticated.
- [ ] Đã kiểm tra behavior trên real browser/container, multi-tab, multi-node, đồng hồ lệch và lỗi mạng.
- [ ] Không dùng key/mật khẩu/token mẫu của bài tập trên hệ thống có dữ liệu thật.

### Câu hỏi tự kiểm tra

**1.** Browser tự xóa remember-me cookie hết hạn; điều đó đủ chứng minh server kiểm tra expiry chưa?  
**Đáp án:** Chưa. Cần thử cố tình gửi lại token cũ sau hạn trong request không có session và kiểm tra server từ chối.

**2.** Base64 có bảo vệ nội dung cookie khỏi bị sửa không?  
**Đáp án:** Không. Base64 chỉ chuyển biểu diễn bytes sang chuỗi; chống sửa phải dựa vào chữ ký hoặc phép đối chiếu token tin cậy ở server.

**3.** Token-based remember-me có chữ ký hợp lệ sẽ tự từ chối lần dùng thứ hai không?  
**Đáp án:** Thông thường không. Chữ ký chứng minh tính toàn vẹn, không biến token thành one-time token.

**4.** Persistent token đã xoay từ T1 sang T2, T1 bị gửi lại. Ý nghĩa?  
**Đáp án:** Đó có thể là dấu hiệu cookie bị đánh cắp/phát lại hoặc race giữa các request; implementation có thể xóa tokens của user và yêu cầu đăng nhập lại.

**5.** Nếu attacker dùng cookie bị đánh cắp **trước** người dùng thật, rotation có chắc ngăn attacker không?  
**Đáp án:** Không. Lần dùng đầu có thể thành công; rotation giúp phát hiện khi bản cũ được dùng sau đó, không xác minh được ai là chủ cookie thật.

**6.** Vì sao `HttpOnly` không giải quyết hết XSS?  
**Đáp án:** Nó hạn chế script thông thường đọc cookie, nhưng script chạy trong origin bị xâm nhập vẫn có thể thực hiện các request dưới ngữ cảnh browser.

**7.** Vì sao nên yêu cầu `fullyAuthenticated()` ở URL đổi mật khẩu hoặc thao tác nhạy cảm?  
**Đáp án:** Remember-me là bằng chứng yếu hơn đăng nhập tương tác. Endpoint nhạy cảm cần reauthentication/step-up theo policy, không chỉ cookie có thể bị sao chép.

**8.** Xóa persistent remember-me records có tự đăng xuất mọi HTTP session đang hoạt động không?  
**Đáp án:** Không. Session, remember-me tokens và các loại credentials khác cần policy thu hồi riêng; request đang chạy cũng có vòng đời độc lập.

**Kết luận:** Remember-me cookie là một **bearer credential có thời hạn**. Kiểm tra hết hạn cần có logic ở server; kiểm tra sửa token cần chữ ký hoặc kho token tin cậy; phát hiện replay cần state/rotation và vẫn không bảo đảm ngăn lần dùng đầu của cookie bị đánh cắp. Kết hợp HTTPS, cookie flags, CSRF/XSS prevention, fully-authenticated/step-up, thu hồi server-side và kiểm thử request **không mang session** mới có thể đánh giá đúng mức an toàn của tính năng ghi nhớ đăng nhập.