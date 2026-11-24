# Token trong cookie

> **Chương:** Storage security  
> **Học phần:** Application Security — Browser Security (SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY)

Cookie là một cách phổ biến để browser lưu và gửi thông tin phiên đăng nhập. Ứng dụng có thể đặt một session identifier hoặc token trong cookie để server nhận diện người dùng ở các request tiếp theo. Cách làm này tận dụng các thuộc tính bảo mật của cookie như Secure, HttpOnly và SameSite, nhưng cũng tạo ra một đặc điểm quan trọng: browser tự động đính kèm cookie phù hợp vào request. Vì vậy, token trong cookie cần được thiết kế cùng cơ chế chống Cross-Site Request Forgery (CSRF).

HttpOnly ngăn JavaScript đọc giá trị cookie qua các API như document.cookie, giúp giảm nguy cơ đánh cắp token trực tiếp khi xảy ra XSS. Tuy nhiên, script độc hại chạy trong origin của ứng dụng vẫn có thể gửi request cùng cookie và thực hiện hành động dưới phiên của người dùng. HttpOnly giảm khả năng trích xuất credential, không biến XSS thành vô hại. Tương tự, SameSite giúp giảm một số request cross-site nhưng không thay thế CSRF token, kiểm tra Origin hoặc authorization phía server.

Bài học này phân tích cách đặt token trong cookie, chọn thuộc tính cookie, kiểm soát CSRF, quản lý vòng đời token và kiểm thử hành vi thực tế trong browser.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt session identifier, opaque token và JWT khi được lưu trong cookie.
2. Giải thích cách browser gửi cookie và phạm vi host/domain/path.
3. Cấu hình Secure, HttpOnly, SameSite và cookie prefix phù hợp.
4. Hiểu vì sao HttpOnly giảm nguy cơ đánh cắp token nhưng không ngăn XSS thực hiện hành động.
5. Nhận diện CSRF phát sinh từ cơ chế tự động gửi cookie.
6. Kết hợp SameSite, CSRF token, kiểm tra Origin và Fetch Metadata.
7. Phân biệt cookie credential với Authorization bearer header.
8. Thiết kế access token, refresh token, rotation, expiration và revocation.
9. Xử lý fetch credentials, CORS và third-party cookie restrictions.
10. Xây checklist và bài kiểm thử cho token trong cookie.

## 2. Token trong cookie là gì?

Cookie là một cặp tên/giá trị do server đặt qua response Set-Cookie. Browser lưu cookie theo các thuộc tính của nó và gửi lại trong request phù hợp. Giá trị có thể là:

- **Session identifier:** chuỗi ngẫu nhiên khó đoán, dùng tra cứu session ở server.
- **Opaque access token:** chuỗi không mang ý nghĩa trực tiếp, server tra cứu hoặc xác minh bằng trạng thái riêng.
- **JWT:** token có cấu trúc claim được ký, server xác minh chữ ký và các claim cần thiết.

Ví dụ:

~~~http
Set-Cookie: __Host-session=RANDOM_OPAQUE_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=1800
~~~

Ở request tiếp theo, browser có thể gửi:

~~~http
Cookie: __Host-session=RANDOM_OPAQUE_VALUE
~~~

JavaScript không cần đọc giá trị cookie để browser gửi nó. Đây là ưu điểm cho mô hình session cookie HttpOnly, đồng thời là nguyên nhân cookie cần phòng CSRF: request có thể mang credential ngay cả khi được kích hoạt từ trang khác.

## 3. Session identifier, opaque token và JWT

| Loại giá trị | Server xử lý | Ưu điểm | Trade-off |
| --- | --- | --- | --- |
| Session identifier ngẫu nhiên | Tra cứu session ở server | Thu hồi, xoay vòng và kiểm soát session thuận tiện | Cần lưu trạng thái session ở server hoặc hệ thống session store |
| Opaque token | Tra cứu hoặc introspection theo token | Không để lộ claim cho client; có thể thu hồi tập trung | Cần trạng thái hoặc dịch vụ xác minh |
| JWT ký | Kiểm tra chữ ký và claim | Có thể xác minh mà không tra cứu session cho mọi request | Thu hồi khó hơn nếu không có denylist/version/session state; claim có thể cũ cho tới khi token hết hạn |

JWT thường được ký chứ không mặc nhiên được mã hóa. Người có token thường có thể giải mã phần header/payload và đọc claim. Không đặt password, secret hoặc dữ liệu cá nhân không cần thiết vào JWT với giả định chữ ký sẽ che giấu nội dung.

Đặt JWT trong HttpOnly cookie không làm JWT trở thành opaque token. Nó chỉ thay đổi cách browser lưu và gửi credential. Server vẫn phải xác minh thuật toán được cho phép, chữ ký, issuer, audience, thời hạn và các claim cần thiết.

## 4. Browser tự động gửi cookie

Khi gửi request, browser chọn cookie dựa trên host/domain, path, Secure, SameSite, partitioning và các điều kiện khác. Ứng dụng không cần JavaScript gắn thủ công token vào từng request.

Điều này tiện cho session-based web app và Backend for Frontend (BFF). Nhưng nếu một trang độc hại khiến browser gửi request tới ứng dụng, cookie vẫn có thể được đính kèm nếu request phù hợp với quy tắc cookie. Server không thể kết luận rằng request có cookie nghĩa là người dùng đã chủ động bấm nút trong ứng dụng.

Đây là mô hình đe dọa chính của CSRF. Hãy coi cookie là credential được browser tự động vận chuyển và xác minh ý định của request thay bằng một lớp chống CSRF phù hợp.

## 5. Phạm vi cookie: host, Domain, Path và port

Cookie không được phân vùng theo origin tuple giống localStorage:

| Thuộc tính | Tác động |
| --- | --- |
| Host-only (không có Domain) | Cookie chỉ được gửi tới host đã đặt cookie |
| Domain | Cho phép cookie áp dụng cho domain và subdomain phù hợp |
| Path | Giới hạn request path được gửi cookie; không phải ranh giới bảo mật mạnh |
| Port | Không phải thành phần scope của cookie |
| Secure | Giới hạn gửi cookie qua secure transport theo quy tắc browser |

Nếu ứng dụng đặt Domain=example.com, các subdomain phù hợp có thể nhận cookie. Điều này làm tăng phạm vi tin cậy: một subdomain cũ, bị takeover hoặc do bên thứ ba kiểm soát có thể ảnh hưởng tới cookie domain-wide trong một số tình huống.

Ưu tiên host-only cookie bằng cách bỏ thuộc tính Domain. Không dùng Path như cơ chế cô lập bí mật giữa hai ứng dụng trên cùng host; Path chủ yếu quyết định request nào mang cookie.

## 6. Secure

Thuộc tính Secure yêu cầu browser chỉ gửi cookie qua secure transport theo quy tắc cookie:

~~~http
Set-Cookie: session=opaque; Secure
~~~

Cookie xác thực production nên có Secure. Điều này vẫn cần thiết khi website đã bật HSTS, vì cookie có thể tồn tại trên host hoặc môi trường khác ngoài phạm vi HSTS, và HSTS không thay thế thuộc tính cookie.

Không bỏ Secure để sửa lỗi đăng nhập trên HTTP. Hãy sửa môi trường HTTPS, certificate, proxy hoặc URL callback. Trong local development, dùng HTTPS local hoặc cấu hình môi trường phát triển có chủ đích; không sao chép cookie insecure sang production.

## 7. HttpOnly

HttpOnly ngăn JavaScript truy cập cookie qua document.cookie:

~~~http
Set-Cookie: session=opaque; Secure; HttpOnly
~~~

Nếu ứng dụng có XSS, script chạy trong origin có thể đọc localStorage hoặc cookie không có HttpOnly. HttpOnly ngăn script đọc trực tiếp cookie phiên, làm giảm khả năng attacker lấy credential để dùng ở một thiết bị khác.

Nhưng HttpOnly không chặn script đó:

- Gửi fetch hoặc form request tới server cùng origin.
- Gọi API dưới phiên đăng nhập hiện tại.
- Đọc response mà origin cho phép script đọc.
- Thay đổi nội dung trang hoặc thao túng người dùng.
- Thực hiện các thao tác mà người dùng hiện tại được phép thực hiện nếu server không có bước xác nhận bổ sung.

Vì vậy, HttpOnly giảm nguy cơ token exfiltration; phòng XSS vẫn cần output encoding, safe DOM APIs, CSP, Trusted Types và kiểm soát dependency. Hành động nhạy cảm có thể cần xác thực lại hoặc step-up authentication.

JavaScript cũng không thể đọc header Set-Cookie từ fetch response vì đây là forbidden response header. Không thiết kế frontend dựa vào việc lấy giá trị HttpOnly cookie từ response.

## 8. SameSite

SameSite điều khiển việc browser gửi cookie trong các request theo ngữ cảnh site:

| Giá trị | Hành vi khái quát | Cân nhắc |
| --- | --- | --- |
| Strict | Không gửi cookie trong ngữ cảnh cross-site | Bảo vệ mạnh hơn nhưng có thể làm gián đoạn liên kết ngoài, SSO hoặc callback |
| Lax | Cho phép cookie trong một số điều hướng top-level cross-site an toàn, thường là GET; hạn chế nhiều subresource và iframe cross-site | Lựa chọn mặc định hợp lý cho nhiều session cookie |
| None | Cho phép gửi trong ngữ cảnh cross-site nếu các điều kiện khác đáp ứng | Bắt buộc đi cùng Secure; vẫn có thể bị third-party cookie policy chặn hoặc partition |

SameSite dựa trên khái niệm site, không phải origin. Hai subdomain khác nhau có thể là cross-origin nhưng same-site nếu schemeful site phù hợp. Vì vậy, SameSite không ngăn mọi request từ origin khác; một subdomain cùng site nhưng không đáng tin có thể vẫn nằm trong ngữ cảnh same-site.

Hãy khai báo SameSite tường minh thay vì dựa vào default khác nhau giữa browser hoặc thay đổi tương thích. Đừng dùng SameSite=None chỉ để sửa lỗi mà chưa đánh giá nhu cầu nhúng cross-site và third-party cookie policy.

## 9. SameSite và điều hướng top-level

Với Lax, cookie thường được gửi trong điều hướng top-level cross-site dùng phương thức an toàn như GET, nhưng không được gửi trong nhiều request cross-site dạng subresource, iframe hoặc POST. Một số browser có hành vi tương thích tạm thời cho cookie không khai báo SameSite trong tình huống POST ngay sau khi tạo; không dựa vào ngoại lệ này như hợp đồng bảo mật.

Điều này dẫn tới hai nguyên tắc:

- Không bao giờ dùng GET để thay đổi trạng thái như chuyển tiền, xóa tài khoản, đổi email hoặc cập nhật quyền.
- Kiểm thử callback đăng nhập, OAuth/OIDC, SSO và luồng thanh toán với SameSite thực tế; một callback cross-site POST có thể không mang cookie Lax như ứng dụng cũ mong đợi.

Nếu một luồng cần cross-site cookie, thiết kế cookie riêng có SameSite=None; Secure và bổ sung state/nonce, CSRF protection cùng kiểm tra origin phù hợp. Không hạ SameSite của toàn bộ session cookie chỉ để một endpoint callback hoạt động.

## 10. Cookie prefix __Host- và __Secure-

Browser hiện đại hỗ trợ cookie prefix để áp đặt một số điều kiện:

| Prefix | Điều kiện chính | Lợi ích |
| --- | --- | --- |
| __Secure- | Cookie phải có Secure và được đặt từ secure context | Giảm nguy cơ cookie cùng tên bị đặt qua kết nối không an toàn |
| __Host- | Phải có Secure, Path=/ và không có Domain | Ràng buộc cookie vào host đã đặt, không cho domain cookie rộng hơn |

Ví dụ session cookie:

~~~http
Set-Cookie: __Host-session=opaque; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=1800
~~~

Không thêm Domain vào cookie __Host-. Prefix có thể bị bỏ qua bởi browser cũ không hỗ trợ, nên vẫn cần cấu hình cookie đúng và kiểm thử browser matrix.

## 11. Cấu hình cookie session khuyến nghị

Với ứng dụng web HTTPS dùng session cookie host-only, một điểm khởi đầu hợp lý:

~~~http
Set-Cookie: __Host-session=RANDOM_OPAQUE_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=1800
~~~

Ý nghĩa:

- __Host-session: cookie có prefix yêu cầu host-only, Secure và Path=/.
- RANDOM_OPAQUE_VALUE: session identifier ngẫu nhiên, không phải thông tin có thể đoán.
- Path=/: gửi tới các route của host.
- Secure: chỉ gửi qua secure transport.
- HttpOnly: JavaScript không đọc trực tiếp giá trị.
- SameSite=Lax: giảm một số request cross-site mang cookie.
- Max-Age=1800: thời hạn browser lưu cookie là 30 phút; server vẫn phải kiểm tra session expiry riêng.

Nếu session cần timeout idle và absolute lifetime, lưu các mốc thời gian ở server. Không chỉ dựa vào Max-Age của browser để quyết định session còn hợp lệ hay không.

## 12. Ví dụ đặt cookie trong Express

Ví dụ dùng session identifier opaque:

~~~js
app.post("/login", async (req, res) => {
  const user = await authenticate(req.body);
  if (!user) {
    return res.status(401).json({ error: "invalid_credentials" });
  }

  // Tạo session mới phía server sau khi xác thực thành công.
  const sessionId = await createServerSession(user.id);

  res.cookie("__Host-session", sessionId, {
    path: "/",
    secure: true,
    httpOnly: true,
    sameSite: "lax",
    maxAge: 30 * 60 * 1000
  });

  return res.status(204).end();
});
~~~

Không đặt Domain để giữ cookie host-only. sessionId cần được tạo bằng nguồn ngẫu nhiên mật mã, có entropy đủ lớn, được lưu/tra cứu an toàn và không tái sử dụng session trước đăng nhập. Sau khi xác thực, hãy rotate session identifier để giảm session fixation.

Ví dụ minh họa luồng; ứng dụng thật cần rate limiting, kiểm soát đăng nhập, CSRF cho endpoint phù hợp, quản lý lỗi và lưu session an toàn.

## 13. Token trong cookie và CSRF

CSRF xảy ra khi website khác khiến browser gửi request tới ứng dụng đang đăng nhập. Vì browser tự động gửi cookie phù hợp, server có thể nhận request mang session hợp lệ dù người dùng không chủ động thực hiện hành động trên ứng dụng.

Ví dụ nguy hiểm:

~~~html
<form action="https://bank.example.test/transfer" method="POST">
  <input name="to" value="attacker">
  <input name="amount" value="100">
  <button type="submit">Continue</button>
</form>
~~~

Nếu endpoint dựa hoàn toàn vào session cookie và không có kiểm tra CSRF phù hợp, browser có thể gửi cookie cùng form request. Việc attacker không đọc được response do SOP/CORS không ngăn request gây side effect được gửi.

Mọi endpoint thay đổi trạng thái cần kiểm tra ý định hợp lệ, dùng method phù hợp và không dựa vào việc request có cookie.

## 14. Phòng CSRF bằng synchronizer token

Với session server-side, mô hình synchronizer token thường dễ kiểm soát:

1. Server tạo CSRF token gắn với session.
2. Token được render trong HTML hoặc trả về qua endpoint cùng origin.
3. Frontend gửi token trong hidden form field hoặc custom header.
4. Server so sánh token nhận được với token gắn session.
5. Request thiếu/sai token bị từ chối.

Ví dụ form:

~~~html
<form method="POST" action="/profile/email">
  <input type="hidden" name="csrfToken" value="TOKEN_FROM_SERVER">
  <input type="email" name="email">
  <button type="submit">Cập nhật email</button>
</form>
~~~

Ví dụ kiểm tra ở server:

~~~js
const { timingSafeEqual } = require("node:crypto");

function constantTimeTokenEqual(expected, supplied) {
  const expectedBytes = Buffer.from(expected, "utf8");
  const suppliedBytes = Buffer.from(supplied, "utf8");
  return expectedBytes.length === suppliedBytes.length &&
    timingSafeEqual(expectedBytes, suppliedBytes);
}

function verifyCsrf(req, res, next) {
  const expected = req.session?.csrfToken;
  const supplied = req.body?.csrfToken || req.get("X-CSRF-Token");

  if (typeof expected !== "string" || typeof supplied !== "string" ||
      !constantTimeTokenEqual(expected, supplied)) {
    return res.status(403).json({ error: "csrf_validation_failed" });
  }
  next();
}
~~~

Ví dụ chuyển hai token thành Buffer và kiểm tra độ dài trước khi gọi primitive timingSafeEqual của Node.js. Token phải đủ ngẫu nhiên, gắn với session và không được lấy từ một nguồn attacker có thể điều khiển. Middleware thực tế cần được đặt sau body parser và session middleware.

## 15. Double-submit cookie pattern

Một lựa chọn khác là double-submit cookie: server đặt một CSRF token riêng trong cookie và client gửi cùng giá trị trong custom header hoặc form field. Server kiểm tra hai giá trị khớp nhau.

Mô hình đơn giản:

~~~http
Set-Cookie: __Host-csrf=RANDOM_CSRF_VALUE; Path=/; Secure; SameSite=Lax
~~~

~~~http
POST /api/profile
Cookie: __Host-session=...; __Host-csrf=RANDOM_CSRF_VALUE
X-CSRF-Token: RANDOM_CSRF_VALUE
~~~

CSRF cookie trong ví dụ không có HttpOnly để JavaScript có thể đọc và chép vào header; một thiết kế khác có thể bootstrap token qua response body. Không dùng lại session token làm CSRF token.

Double-submit ngây thơ có thể gặp cookie injection hoặc subdomain compromise. Ưu tiên signed double-submit token được ràng buộc với session, hoặc synchronizer token khi server có session state. So sánh token phía server và kiểm tra format/nguồn token; chỉ so sánh hai chuỗi tùy ý chưa đủ cho mọi threat model.

## 16. Kiểm tra Origin, Referer và Fetch Metadata

Đối với request thay đổi trạng thái, server có thể kiểm tra Origin header theo allowlist origin chính xác. Nếu Origin không có trong một số loại request, có thể dùng Referer theo chính sách phù hợp và xử lý trường hợp thiếu một cách rõ ràng.

Fetch Metadata cung cấp các header như Sec-Fetch-Site, Sec-Fetch-Mode và Sec-Fetch-Dest để server nhận diện ngữ cảnh request:

~~~http
Sec-Fetch-Site: cross-site
Sec-Fetch-Mode: navigate
Sec-Fetch-Dest: document
~~~

Ví dụ, server có thể từ chối request cross-site tới endpoint nhạy cảm nếu nghiệp vụ không cần luồng đó. Tuy nhiên, Fetch Metadata là lớp bổ sung; cần có fallback cho browser/client không gửi header và allowlist ngoại lệ có kiểm soát cho OAuth, payment hoặc tích hợp hợp lệ.

Không kiểm tra Origin bằng so sánh chuỗi con như endsWith("example.com"). Hãy parse URL và so sánh scheme, host, port với origin tin cậy chính xác.

## 17. SameSite là lớp phòng vệ bổ sung

SameSite=Lax hoặc Strict có thể giảm request cookie trong nhiều ngữ cảnh cross-site. Nhưng không nên coi đây là lớp chống CSRF duy nhất:

- Same-site cross-origin vẫn có thể tồn tại giữa các subdomain.
- Một subdomain cùng site bị takeover hoặc có XSS có thể tạo request same-site.
- Một số luồng điều hướng top-level vẫn gửi cookie Lax.
- SameSite=None cần thiết cho một số tích hợp cross-site và làm tăng yêu cầu CSRF.
- Browser có thể áp dụng third-party cookie blocking hoặc partitioning khác nhau.

Kết hợp SameSite với CSRF token, Origin/Referer validation, Fetch Metadata và quy tắc không thay đổi trạng thái qua GET. Chọn SameSite theo luồng sản phẩm, không dùng nó thay cho mô hình chống CSRF.

## 18. CORS không thay thế CSRF protection

CORS quyết định JavaScript ở origin khác có được đọc response cross-origin hay không. Nó không phải cơ chế bảo đảm rằng request thay đổi trạng thái không được gửi.

Một form HTML cross-site có thể gửi request đơn giản tới server dù browser không cho trang attacker đọc response. Do đó:

- Không dựa vào CORS để ngăn mọi CSRF.
- Không bật Access-Control-Allow-Origin rộng cho API có credential.
- Với credentialed CORS, dùng origin cụ thể và Access-Control-Allow-Credentials: true.
- Kiểm tra CSRF độc lập với CORS.

Nếu API cho phép credentialed cross-origin fetch, cấu hình CORS phải dùng allowlist origin chính xác. Wildcard * không hợp lệ cho response credentialed. Nhưng ngay cả cấu hình CORS chặt vẫn không thay thế CSRF token cho request có thể được gửi qua form hoặc navigation.

## 19. XSS và token HttpOnly

Đặt token trong HttpOnly cookie có lợi thế so với lưu token trong localStorage: script không thể đọc trực tiếp giá trị cookie qua JavaScript. Điều này làm khó việc trích xuất token để attacker sử dụng từ nơi khác.

Tuy nhiên, XSS vẫn có thể:

- Gửi request cùng origin và browser tự gắn cookie.
- Đọc response API mà script cùng origin được phép đọc.
- Thay đổi thông tin người dùng, gửi nội dung hoặc thực hiện giao dịch nếu không có xác nhận bổ sung.
- Chờ người dùng mở trang và thao tác trong phiên bị xâm nhập.

Vì vậy, cookie HttpOnly là biện pháp giảm thiệt hại credential theft, không phải biện pháp phòng XSS. Cần ngăn XSS bằng output encoding, safe DOM APIs, CSP, Trusted Types và kiểm soát dependency; đồng thời yêu cầu re-authentication/step-up cho hành động rủi ro cao.

## 20. Cookie token và Authorization bearer header

Hai cách truyền credential có đặc tính khác nhau:

| Tiêu chí | Token trong cookie | Authorization: Bearer |
| --- | --- | --- |
| Ai đính kèm credential | Browser tự động theo cookie rules | Ứng dụng/client chủ động đặt header |
| CSRF | Có rủi ro vì cookie tự gửi | Ít chịu CSRF kiểu cookie tự gửi nếu token không tự động được browser đính kèm |
| XSS đọc credential | HttpOnly ngăn đọc trực tiếp cookie | Nếu token nằm trong JS memory/storage, XSS có thể lấy hoặc sử dụng token |
| CORS | Có thể cần credentialed CORS khi cross-origin | CORS vẫn áp dụng; Authorization thường kích hoạt preflight trong cross-origin request |
| Phù hợp | Web app/BFF, session cookie | Native client, service-to-service hoặc SPA có kiến trúc token rõ ràng |

Không có một lựa chọn đúng cho mọi hệ thống. Với web app cùng origin, BFF + HttpOnly session cookie thường giảm nhu cầu để JavaScript quản lý token. Với API client cần bearer token, phải quản lý token lifetime, storage và XSS threat model cẩn thận.

## 21. Access token và refresh token

Nếu kiến trúc dùng token, hãy phân biệt vòng đời:

- **Access token:** thời hạn ngắn, dùng gọi API với quyền và audience cụ thể.
- **Refresh token:** thời hạn dài hơn, chỉ dùng để xin access token mới và cần bảo vệ nghiêm ngặt.

Một thiết kế có thể đặt refresh token trong HttpOnly Secure cookie và giữ access token ngắn hạn trong bộ nhớ của BFF/client theo kiến trúc. Với BFF, browser có thể chỉ giữ session cookie; server-side BFF giữ hoặc quản lý token tới API phía sau.

Không đặt refresh token dài hạn trong localStorage chỉ vì tiện. Nếu refresh token bị lộ, attacker có thể duy trì quyền truy cập lâu hơn. Server cần rotation, reuse detection, revocation và ràng buộc token với client/session phù hợp.

## 22. Refresh token rotation và reuse detection

Với refresh token dạng opaque hoặc token family, một luồng rotation điển hình:

1. Client gửi refresh token hiện tại tới endpoint refresh.
2. Server xác minh token còn hiệu lực và chưa bị dùng lại.
3. Server phát hành token mới và vô hiệu hóa token cũ trong cùng một thao tác logic.
4. Server ghi nhận quan hệ token family/session.
5. Nếu token cũ đã bị dùng lại, server coi đó là dấu hiệu có thể token bị đánh cắp và thu hồi family/session theo chính sách.

Endpoint refresh vẫn nhận cookie tự động, vì vậy cần CSRF protection. Dùng POST, CSRF token hoặc cơ chế xác minh request phù hợp, kiểm tra Origin/Fetch Metadata và không để endpoint refresh trở thành một CSRF primitive.

Rotation cần xử lý request đồng thời và retry mạng. Nếu client gửi hai refresh request cùng lúc, server cần thiết kế concurrency/idempotency để tránh coi retry hợp lệ là reuse attack hoặc phát hành nhiều nhánh token không kiểm soát.

## 23. JWT trong cookie

Nếu đặt JWT trong cookie, server cần kiểm tra:

- Chữ ký bằng key đúng và thuật toán nằm trong allowlist.
- Issuer và audience đúng với API đang nhận token.
- exp, nbf và các giới hạn thời gian.
- Token type/use phù hợp, không nhầm access token với ID token.
- Scope/role được kiểm tra cho hành động cụ thể.
- Key rotation và cách xử lý key bị lộ.
- Revocation hoặc session version nếu cần vô hiệu hóa trước exp.

JWT ký không được mã hóa mặc định. Cookie HttpOnly bảo vệ việc đọc bằng JavaScript nhưng không thay thế xác minh JWT. Không tin claim chỉ vì token được decode thành công; phải xác minh chữ ký và claim ở server.

Với ứng dụng cần logout tức thời, thu hồi session hoặc phản ứng nhanh khi tài khoản bị khóa, opaque session identifier có trạng thái phía server thường dễ vận hành hơn JWT stateless dài hạn.

## 24. Expiration, logout và revocation

Cookie expiration và token/session expiration là hai lớp khác nhau:

- Max-Age/Expires điều khiển thời gian browser giữ cookie.
- exp hoặc expiry trong session store điều khiển server có chấp nhận credential không.
- Idle timeout giới hạn thời gian không hoạt động.
- Absolute lifetime giới hạn tổng thời gian session tồn tại.
- Revocation vô hiệu hóa session/token trước khi hết hạn tự nhiên.

Khi logout:

1. Server vô hiệu hóa session hoặc refresh token family.
2. Server trả Set-Cookie cùng tên với Max-Age=0 hoặc Expires trong quá khứ.
3. Cookie deletion phải khớp scope cần xóa, đặc biệt là Path và Domain.
4. Xóa dữ liệu client-side liên quan và cache chứa thông tin tài khoản.
5. Xử lý các request đang chạy và token refresh đồng thời theo chính sách.

Ví dụ xóa host-only cookie:

~~~http
Set-Cookie: __Host-session=; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=0
~~~

Chỉ xóa cookie ở browser không thu hồi một token đã bị sao chép trước đó. Server phải vô hiệu hóa session/token nếu cần logout có hiệu lực bảo mật.

## 25. Fetch credentials và cookie

Fetch mặc định dùng credentials same-origin. Khi gọi API ở origin khác, ứng dụng có thể cần credentials: "include":

~~~js
const response = await fetch("https://api.example.net/profile", {
  method: "GET",
  credentials: "include"
});
~~~

Browser vẫn áp dụng SameSite, Secure, domain/path, third-party cookie policy và partitioning. credentials: "include" không buộc browser gửi cookie bị SameSite hoặc privacy policy chặn.

Nếu frontend cần đọc response credentialed cross-origin, API cần CORS phù hợp:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Không dùng Access-Control-Allow-Origin: * với credentialed request. Nếu có thể, ưu tiên BFF hoặc API cùng origin để giảm độ phức tạp cookie/CORS và tránh chia sẻ cookie domain-wide giữa nhiều subdomain.

## 26. Token cookie trong iframe và third-party context

Nếu ứng dụng được nhúng trong iframe cross-site, cookie có thể chịu SameSite=None; Secure, third-party cookie blocking, partitioning hoặc Storage Access API. Chỉ đặt SameSite=None không bảo đảm cookie luôn được gửi.

Với widget cần session trong iframe:

- Xác định rõ có thật sự cần đăng nhập trong third-party context không.
- Xem xét cookie partitioned (CHIPS) nếu mô hình sản phẩm phù hợp và browser hỗ trợ.
- Nếu cần truy cập state không partition, đánh giá Storage Access API và điều kiện user interaction.
- Không gửi refresh token hoặc access token dài hạn qua query string hay postMessage.
- Kiểm tra CSRF trên mọi endpoint nhận cookie.
- Cân nhắc chuyển luồng đăng nhập lên top-level hoặc dùng BFF nếu khả thi.

Cookie partitioned có thể giúp widget có state riêng theo top-level site, nhưng không phải giải pháp chia sẻ session toàn cục và không thay authorization. Hãy kiểm tra browser matrix, privacy settings và trải nghiệm đăng nhập.

## 27. WebSocket và các request đặc biệt

Cookie có thể được gửi trong WebSocket handshake nếu cookie rules phù hợp. Vì vậy, endpoint WebSocket dùng cookie session vẫn cần kiểm tra Origin và xác thực kết nối; không cho rằng WebSocket nằm ngoài CSRF threat model.

Với các giao thức hoặc endpoint khác:

- Xác minh Origin/Host theo thiết kế.
- Kiểm tra quyền user trước khi subscribe hoặc gửi dữ liệu.
- Dùng token ngắn hạn hoặc ticket một lần nếu cần.
- Không đưa token dài hạn vào URL vì URL có thể xuất hiện trong log và telemetry.
- Có rate limit và kiểm soát kết nối.

## 28. Bảo vệ response và log

Response chứa dữ liệu tài khoản hoặc trạng thái session nên có cache policy phù hợp, thường cân nhắc:

~~~http
Cache-Control: no-store
~~~

Không ghi giá trị Cookie, Set-Cookie, Authorization hoặc refresh token vào application log, reverse proxy log, analytics hay error tracking. Nếu cần correlation, dùng session identifier đã hash hoặc mã tham chiếu không thể dùng làm credential.

Giới hạn kích thước cookie; browser và server có giới hạn triển khai riêng, thường khoảng vài kilobyte cho mỗi cookie. Không lưu profile, payload lớn hoặc JWT chứa nhiều dữ liệu vào cookie. Cookie được gửi trên nhiều request phù hợp, làm tăng header overhead và có thể vượt giới hạn proxy/server.

## 29. Kiểm thử và chẩn đoán

Khi kiểm tra token trong cookie, ghi nhận browser/version, scheme, top-level site, origin, frame tree, cookie attributes và request method.

Trong DevTools:

1. Application/Storage → Cookies: kiểm tra Name, Domain/Host, Path, Secure, HttpOnly, SameSite, Expires/Max-Age và Partitioned nếu có.
2. Network → login response: kiểm tra Set-Cookie có được browser chấp nhận hay bị cảnh báo.
3. Network → API request: kiểm tra cookie có được gửi trong request hay không; không copy giá trị cookie vào ticket/log.
4. Console: tìm cảnh báo SameSite, third-party cookie, Secure context hoặc cookie bị chặn.
5. Kiểm tra response logout có xóa đúng cookie scope và server có revoke session.

Phân biệt các tình huống:

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Login thành công nhưng request sau không có cookie | Domain/Path/Secure/SameSite hoặc browser policy | Kiểm tra cookie jar và request URL |
| Cookie có trong DevTools nhưng JavaScript không đọc được | HttpOnly đang hoạt động | Đây là hành vi mong muốn cho session cookie |
| Iframe không nhận cookie | SameSite, third-party blocking hoặc partitioning | Kiểm tra top-level site, cookie attributes và browser settings |
| API cross-origin không đọc được response | CORS sai hoặc credentials config không hợp lệ | Kiểm tra ACAO, ACAC, Vary và fetch credentials |
| Request có cookie nhưng bị 403 | CSRF token, Origin hoặc authorization thất bại | Kiểm tra CSRF middleware và quyền server-side |
| Logout xong vẫn dùng được token cũ | Server chưa revoke hoặc JWT còn hiệu lực | Kiểm tra session store, token family và revocation |
| Subdomain nhận cookie ngoài dự kiến | Domain attribute quá rộng | Bỏ Domain, ưu tiên host-only/__Host- |

## 30. Lab A — Quan sát HttpOnly

Chỉ dùng ứng dụng lab và session giả.

1. Đăng nhập để server đặt cookie có Secure, HttpOnly, SameSite=Lax.
2. Mở DevTools → Application → Cookies để xem thuộc tính.
3. Trong Console của đúng origin, chạy document.cookie.
4. Gửi một request same-origin tới endpoint lab yêu cầu đăng nhập.

**Kỳ vọng:** Cookie HttpOnly không xuất hiện trong document.cookie, nhưng browser vẫn gửi cookie trong request phù hợp. Điều này chứng minh HttpOnly chặn đọc trực tiếp chứ không chặn sử dụng phiên.

## 31. Lab B — Kiểm tra SameSite và CSRF

Tạo hai site lab: app.lab.example và attacker.lab.other. Trên app, tạo endpoint POST thay đổi một giá trị giả. Dùng form từ site attacker gửi request tới app.

Thử cookie lần lượt với SameSite=Strict, Lax và None; Secure. Quan sát cookie trong Network request và kết quả server.

**Kỳ vọng:** Hành vi gửi cookie thay đổi theo SameSite và loại request. Khi endpoint có CSRF token/Origin validation, request thiếu bằng chứng hợp lệ phải bị từ chối ngay cả khi cookie được gửi.

## 32. Lab C — CSRF token

1. Tạo session lab và CSRF token gắn session.
2. Render form có hidden token hoặc lấy token từ endpoint same-origin.
3. Gửi POST hợp lệ có token.
4. Gửi lại POST không có token và token sai.
5. Thử gửi form từ origin lab thứ hai.

**Kỳ vọng:** Request hợp lệ được chấp nhận; request thiếu/sai token bị từ chối. Không log session cookie hoặc token thật.

## 33. Lab D — Cookie scope và prefix

Thử đặt cookie host-only, cookie có Domain=.example.test và cookie __Host-session trên các host lab. So sánh request tới app.example.test và sub.example.test; thử cấu hình __Host- sai bằng cách thêm Domain hoặc bỏ Path=/.

**Kỳ vọng:** Host-only cookie không tự chia sẻ sang subdomain; Domain cookie có phạm vi rộng hơn; browser từ chối cookie __Host- nếu vi phạm điều kiện prefix. Cookie không được phân vùng theo port.

## 34. Lab E — Fetch credentials và CORS

Chạy frontend và API trên hai origin lab. Thử fetch mặc định rồi fetch với credentials: "include". Cấu hình API với ACAO origin cụ thể, ACAC true và Vary: Origin; sau đó thử wildcard.

**Kỳ vọng:** Cookie cross-origin chỉ được gửi nếu cookie rules cho phép và request bật credentials phù hợp. Response credentialed không được dùng ACAO wildcard. CORS failure không chứng minh request chưa được gửi; kiểm tra Network và server log.

## 35. Lab F — Logout và token revocation

Tạo session opaque lab có trạng thái server-side. Đăng nhập, xác nhận request được xác thực, sau đó gọi logout để server revoke session và xóa cookie. Thử gửi lại cookie cũ từ một client test.

**Kỳ vọng:** Cookie bị xóa ở browser và session cũ bị server từ chối. Chỉ xóa cookie ở client mà không revoke session sẽ không đáp ứng yêu cầu thu hồi credential đã bị sao chép.

## 36. Các lỗi thiết kế thường gặp

| Lỗi | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Lưu token cookie không có Secure | Có thể gửi qua HTTP ngoài ý muốn | Bật Secure và triển khai HTTPS |
| Bỏ HttpOnly cho session cookie | XSS có thể đọc trực tiếp token | Dùng HttpOnly; xử lý XSS độc lập |
| Nghĩ HttpOnly ngăn XSS thực hiện hành động | Script vẫn có thể gửi request cùng cookie | Phòng XSS và bảo vệ hành động nhạy cảm |
| Dùng SameSite=None mà thiếu Secure | Cookie không đáp ứng yêu cầu browser hiện đại | Thêm Secure và đánh giá third-party policy |
| Chỉ dựa vào SameSite để chống CSRF | Same-site cross-origin và một số navigation vẫn có thể mang cookie | Kết hợp CSRF token, Origin và Fetch Metadata |
| Dùng GET để thay đổi dữ liệu | Điều hướng/link có thể kích hoạt hành động | Dùng method thay đổi trạng thái và CSRF validation |
| Đặt Domain quá rộng | Cookie bị chia sẻ cho nhiều subdomain | Ưu tiên host-only và __Host- |
| Dùng Path như ranh giới bảo mật | Path không cô lập ứng dụng cùng host | Dùng host/origin riêng khi cần boundary |
| Không rotate session sau login | Tăng rủi ro session fixation | Tạo session identifier mới sau xác thực |
| Chỉ xóa cookie khi logout | Token đã bị sao chép vẫn có thể dùng | Revoke session/token phía server |
| JWT dài hạn không có revocation | Token có thể còn hiệu lực sau logout/khóa tài khoản | Dùng expiry ngắn, version/denylist hoặc opaque session |
| Dùng CORS thay CSRF token | Form request vẫn có thể gửi cookie | Thiết kế CSRF protection riêng |
| Log Cookie/Set-Cookie | Lộ credential trong hệ thống quan sát | Redact và dùng correlation ID an toàn |
| Gửi token trong URL | Token có thể rò qua history/log/referrer | Dùng cookie/header theo kiến trúc |

## 37. Checklist review token trong cookie

- [ ] Chọn rõ session identifier, opaque token hay JWT và lý do.
- [ ] Cookie xác thực có Secure và HttpOnly.
- [ ] SameSite được khai báo tường minh theo luồng nghiệp vụ.
- [ ] Ưu tiên host-only; cân nhắc __Host- với Path=/ và không có Domain.
- [ ] Không dùng Path như ranh giới bảo mật.
- [ ] Session identifier có entropy cao và được rotate sau login/đổi quyền.
- [ ] Server kiểm tra expiry, idle timeout, absolute lifetime và revocation.
- [ ] Endpoint thay đổi trạng thái không dùng GET.
- [ ] Có CSRF token hoặc cơ chế chống CSRF tương đương.
- [ ] Có kiểm tra Origin/Referer và cân nhắc Fetch Metadata.
- [ ] SameSite được xem là defense in depth, không phải lớp duy nhất.
- [ ] HttpOnly không bị hiểu nhầm là biện pháp ngăn mọi tác động của XSS.
- [ ] JWT được xác minh chữ ký, issuer, audience, expiry và algorithm allowlist.
- [ ] Refresh token có rotation, reuse detection và revocation.
- [ ] Fetch credentials/CORS được cấu hình chính xác nếu API cross-origin.
- [ ] Third-party cookie blocking/partitioning được kiểm thử nếu có iframe.
- [ ] Logout revoke session phía server và xóa cookie đúng scope.
- [ ] Cookie, token và Authorization header được redacted khỏi log.
- [ ] Có kiểm thử browser cho cookie acceptance, request attachment và CSRF failure.

## 38. Câu hỏi tự kiểm tra

1. Token trong cookie khác token trong localStorage ở cách browser gửi credential như thế nào?
2. Vì sao HttpOnly giảm token theft nhưng không ngăn XSS thực hiện request?
3. Secure, HttpOnly và SameSite giải quyết những vấn đề khác nhau nào?
4. SameSite dựa trên site hay origin? Điều này ảnh hưởng subdomain ra sao?
5. Vì sao cookie tự động gửi làm phát sinh CSRF?
6. Synchronizer token và double-submit cookie khác nhau thế nào?
7. Vì sao CORS không thay thế CSRF protection?
8. __Host- yêu cầu những thuộc tính nào?
9. Opaque session identifier khác JWT về revocation và trạng thái server ra sao?
10. Refresh token rotation và reuse detection giúp giảm rủi ro nào?
11. Vì sao xóa cookie ở browser không đủ để revoke token đã bị sao chép?
12. Cần kiểm tra những gì khi token cookie không được gửi trong iframe cross-site?

## 39. Ghi nhớ

Token trong cookie tận dụng cơ chế browser tự động gửi credential và các thuộc tính như Secure, HttpOnly, SameSite. Với session web, host-only cookie có Secure, HttpOnly, SameSite phù hợp và prefix __Host- là điểm khởi đầu tốt. HttpOnly giảm khả năng XSS đọc/trích xuất token, nhưng script độc hại cùng origin vẫn có thể thực hiện request dưới phiên hiện tại.

Vì cookie tự động đi cùng request, hãy bảo vệ endpoint thay đổi trạng thái bằng CSRF token, kiểm tra Origin/Fetch Metadata và không dùng GET cho side effect. Quản lý token phía server với expiry, rotation, revocation và logout; kiểm thử CORS, SameSite và third-party cookie behavior trong browser mục tiêu. **Cookie bảo vệ cách credential được lưu và vận chuyển; CSRF protection xác minh ý định request; XSS defense bảo vệ code chạy trong origin.**
