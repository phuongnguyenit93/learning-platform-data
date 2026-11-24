# Cookie prefix — Tiền tố cookie và bảo vệ cookie xác thực

## 1. Cookie prefix là gì?

**Cookie prefix** (tiền tố cookie) là quy ước đặt tên cookie để trình duyệt hỗ trợ có thể áp dụng thêm điều kiện khi cookie được tạo hoặc cập nhật. Một số tiền tố phổ biến là **__Secure-** và **__Host-**; một số trình duyệt còn hỗ trợ **__Http-** và **__Host-Http-**. Các tiền tố này giúp ràng buộc cookie với ngữ cảnh HTTPS, phạm vi host và khả năng chỉ được đặt qua HTTP response header.

Ví dụ, ứng dụng có thể đặt cookie phiên:

~~~http
Set-Cookie: __Host-session=<opaque-random-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Trong trình duyệt hỗ trợ quy tắc **__Host-**, cookie này phải được đặt từ secure origin, có thuộc tính **Secure**, **Path=/** và **không có thuộc tính Domain**. Nhờ vậy, cookie là host-only và không được chia sẻ cho các subdomain. Đây là lựa chọn hữu ích cho session cookie của một ứng dụng web chạy trên một hostname cụ thể.

Trong chương **Cookie và browser** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, cookie prefix liên hệ trực tiếp với session identifier, token, credential, MFA và bảo vệ phiên sau đăng nhập. Người học cần hiểu trình duyệt áp dụng quy tắc prefix như thế nào, tiền tố nào phù hợp với cookie xác thực, và những rủi ro nào vẫn cần xử lý bằng TLS, HttpOnly, SameSite, CSRF protection, XSS prevention và kiểm tra session phía server.

**Prefix không phải một loại mã hóa hoặc chữ ký.** Nó là quy tắc do user agent thực thi khi nhận lệnh Set-Cookie. Prefix không làm giá trị cookie khó đoán hơn, không tự xác thực người dùng và không thay thế việc kiểm tra session/token ở server.

## 2. Các prefix thường gặp

Các quy tắc dưới đây áp dụng **trong trình duyệt có hỗ trợ prefix tương ứng**:

| Prefix | Điều kiện chính khi đặt cookie | Ý nghĩa |
| --- | --- | --- |
| **__Secure-** | Cookie được đặt từ secure origin và có thuộc tính Secure. | Chỉ cho phép cookie mang prefix này được tạo trong ngữ cảnh bảo mật và chỉ gửi qua kết nối an toàn. |
| **__Host-** | Secure origin, có Secure, Path=/ và **không có Domain**. | Tạo cookie host-only, áp dụng toàn bộ path của host và ngăn cookie được mở rộng tới domain cha. |
| **__Http-** | Secure origin, có Secure và HttpOnly. | Trong trình duyệt hỗ trợ, cookie phải được đặt bằng HTTP Set-Cookie, không thể tạo bằng JavaScript document.cookie. |
| **__Host-Http-** | Secure origin, có Secure, HttpOnly, Path=/ và không có Domain. | Kết hợp ràng buộc host-only của __Host- với yêu cầu chỉ được đặt qua HTTP response của __Http-. |

### Hai prefix nền tảng

**__Secure-** phù hợp khi cần bảo đảm cookie chỉ được đặt trong secure context và có thuộc tính Secure. Prefix này **không cấm thuộc tính Domain**; cookie vẫn có thể được chia sẻ cho subdomain nếu server đặt Domain=example.org.

**__Host-** đặt ràng buộc chặt hơn: không có Domain, Path=/ và Secure. Trình duyệt hỗ trợ sẽ từ chối cookie mang prefix này nếu thiếu điều kiện. Vì không có Domain, cookie chỉ được gửi tới host đã đặt nó. Điều này giảm nguy cơ một subdomain tạo cookie cùng tên với phạm vi domain cha (*cookie tossing*).

### Hai prefix bổ sung

**__Http-** và **__Host-Http-** được hỗ trợ trong một số trình duyệt hiện đại. Chúng bổ sung yêu cầu HttpOnly, giúp chứng minh cookie được đặt qua HTTP response header thay vì JavaScript. Hãy kiểm tra ma trận tương thích trình duyệt trước khi phụ thuộc vào các prefix này trong ứng dụng production; không giả định mọi browser hoặc embedded webview đều hỗ trợ như nhau.

Prefix được nhận diện theo **chuỗi chính xác và phân biệt chữ hoa/chữ thường**. Ví dụ **__Host-session** là tên có prefix, còn **__host-session** không phải cùng prefix theo quy tắc này. Hãy giữ cách viết thống nhất trong server và client.

## 3. Cookie prefix được trình duyệt kiểm tra ở đâu?

Cookie prefix được kiểm tra khi trình duyệt nhận một cookie mới hoặc cookie được cập nhật, thường từ response header Set-Cookie. Nếu tên cookie bắt đầu bằng prefix được hỗ trợ nhưng thuộc tính không đáp ứng yêu cầu, browser sẽ từ chối lưu cookie đó.

~~~mermaid
sequenceDiagram
    participant A as Application server
    participant B as Browser
    participant S as Session store
    A->>S: Tạo session ID mới
    S-->>A: Session ID
    A-->>B: Set-Cookie: __Host-session=...; Secure; HttpOnly; Path=/; SameSite=Lax
    B->>B: Kiểm tra prefix và thuộc tính
    alt Điều kiện hợp lệ
        B->>B: Lưu cookie host-only
    else Thiếu điều kiện bắt buộc
        B->>B: Từ chối cookie
    end
    B->>A: Request tiếp theo + Cookie: __Host-session=...
    A->>S: Xác minh session ID
    S-->>A: Principal và trạng thái phiên
~~~

Server phải tạo cookie đúng ngay từ đầu. Nếu browser từ chối cookie do thiếu Secure hoặc sai Path, người dùng có thể bị đăng xuất ngay sau đăng nhập, hoặc ứng dụng có thể rơi vào luồng lỗi khó phát hiện.

### Thuộc tính nào được gửi ngược về server?

Trong request, trình duyệt thường gửi header:

~~~http
Cookie: __Host-session=<opaque-random-id>; theme=dark
~~~

Các thuộc tính như Secure, HttpOnly, SameSite, Path và Domain **không được gửi lại như metadata trong Cookie header**. Chúng là chỉ dẫn để browser quyết định lưu và gửi cookie. Server phải cấu hình chúng trong Set-Cookie; không thể nhìn request rồi kết luận browser đã thực thi đúng mọi thuộc tính.

Do đó, prefix giúp browser kiểm soát việc tạo cookie ở client, còn server vẫn phải xác minh session ID và thực thi authorization cho từng request.

## 4. Prefix __Secure- chi tiết

Cookie có tên bắt đầu bằng **__Secure-** phải được đặt trong secure context và có thuộc tính Secure:

~~~http
Set-Cookie: __Secure-session=<random-id>; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

Ví dụ này hợp lệ với quy tắc prefix trong browser hỗ trợ. Cookie có thể dùng thuộc tính Domain nếu ứng dụng cần chia sẻ giữa một số subdomain:

~~~http
Set-Cookie: __Secure-sso=<value>; Domain=example.org; Path=/; Secure; HttpOnly; SameSite=None
~~~

Việc chia sẻ Domain cần được cân nhắc kỹ: mọi subdomain phù hợp có thể tham gia phạm vi cookie, làm tăng bề mặt tin cậy. **__Secure-** không tạo ra host-only cookie và không ngăn subdomain có khả năng phù hợp can thiệp vào cookie domain-wide.

### Khi nào dùng?

- Cookie cần Secure và ứng dụng có lý do hợp lệ để dùng phạm vi Domain.
- Cookie tích hợp nhiều subdomain đã được quản trị như một trust domain.
- Muốn browser hỗ trợ kiểm tra tên prefix cùng thuộc tính Secure.

### Giới hạn

- Không bắt buộc HttpOnly; ứng dụng vẫn phải đặt thuộc tính này riêng cho cookie bí mật.
- Không cấm Domain; không thay thế host-only scope.
- Không chống CSRF, XSS hoặc session hijacking nếu bearer value bị đánh cắp.
- Không thay thế TLS, session rotation, expiration và revocation.

## 5. Prefix __Host- chi tiết

Cookie có tên bắt đầu bằng **__Host-** phải thỏa các điều kiện:

1. Được đặt từ secure origin.
2. Có thuộc tính Secure.
3. Có Path=/.
4. **Không được có thuộc tính Domain**, kể cả khi Domain trùng với hostname hiện tại.

Ví dụ cookie phiên phù hợp:

~~~http
Set-Cookie: __Host-session=<opaque-random-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Không viết:

~~~http
Set-Cookie: __Host-session=<id>; Domain=app.example.org; Path=/; Secure; HttpOnly
~~~

Browser hỗ trợ sẽ từ chối cookie thứ hai vì có thuộc tính Domain. Dù Domain có vẻ chỉ đúng hostname, sự hiện diện của thuộc tính này vẫn vi phạm quy tắc __Host-.

### Host-only cookie có lợi gì?

Giả sử ứng dụng chính chạy tại app.example.org, còn một subdomain khác chạy dịch vụ nội dung do nhóm khác quản lý. Cookie host-only của app.example.org chỉ được gửi tới host đó. Subdomain không thể yêu cầu browser đặt một cookie __Host-session có Domain là example.org để mở rộng phạm vi tới ứng dụng chính trong browser hỗ trợ quy tắc này.

~~~mermaid
flowchart TD
    R["example.org"]
    A["app.example.org<br/>đặt __Host-session"]
    B["docs.example.org<br/>subdomain khác"]
    A -->|"Host-only cookie<br/>Domain attribute bị cấm"| A
    B -.->|"Không thể đặt __Host-session<br/>cho Domain=example.org"| A
~~~

Điều này giúp giảm **cookie tossing** và một số rủi ro liên quan cookie domain-wide. Tuy nhiên, nó không cô lập các ứng dụng chạy cùng một host/origin. Nếu nhiều ứng dụng không tin cậy cùng chạy trên app.example.org, cần phân tách host hoặc thiết kế bảo mật ở tầng ứng dụng.

### Vì sao Path=/?

Prefix __Host- yêu cầu cookie áp dụng toàn bộ path của host. Thuộc tính Path giúp browser quyết định request nào nhận cookie, nhưng **không nên được xem là ranh giới bảo mật giữa các ứng dụng**. Các ứng dụng cùng host có thể có tương tác phức tạp; dùng host riêng cho ranh giới tin cậy là rõ ràng hơn.

## 6. Prefix __Http- và __Host-Http-

Các prefix này bổ sung yêu cầu HttpOnly:

~~~http
Set-Cookie: __Http-session=<random-id>; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

Trong browser hỗ trợ, cookie __Http- phải được tạo bằng header Set-Cookie trong secure context, có Secure và HttpOnly. JavaScript không thể đặt thuộc tính HttpOnly bằng document.cookie, nên prefix bổ sung một quy tắc xác nhận nguồn tạo cookie.

Prefix kết hợp:

~~~http
Set-Cookie: __Host-Http-session=<random-id>; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

Cookie __Host-Http- còn phải không có Domain và có Path=/, tương tự điều kiện host-only. Đây là cấu hình chặt cho session cookie nếu browser mục tiêu hỗ trợ.

### Lưu ý tương thích

- Các prefix này không có mức hỗ trợ đồng nhất giữa mọi trình duyệt, phiên bản, webview hoặc client HTTP.
- Một user agent không hiểu prefix có thể xử lý tên cookie như tên bình thường và không áp dụng các điều kiện bổ sung.
- Không được dựa vào prefix để thay thế thuộc tính thực tế: vẫn đặt Secure, HttpOnly, Path và SameSite đầy đủ.
- Kiểm thử browser support và luồng đăng nhập/SSO trước khi triển khai.

Nếu ứng dụng cần tương thích rộng, __Host- với các thuộc tính chuẩn và cấu hình server-side nghiêm ngặt thường là lựa chọn thực tế hơn so với phụ thuộc vào prefix mới hơn chưa được hỗ trợ đồng đều.

## 7. Chọn prefix nào cho session cookie?

Đối với cookie chứa session ID của ứng dụng web trên một hostname, lựa chọn thường phù hợp là **__Host-**:

~~~http
Set-Cookie: __Host-session=<opaque-random-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Lý do:

- Secure buộc browser chỉ gửi cookie qua HTTPS.
- HttpOnly ngăn JavaScript thông thường đọc trực tiếp session ID.
- SameSite=Lax giảm một số trường hợp cookie tự động được gửi trong request cross-site; vẫn cần CSRF protection theo luồng.
- Path=/ thỏa quy tắc prefix và áp dụng cookie trên toàn host.
- Không có Domain làm cookie host-only, giảm nguy cơ cookie domain-wide bị subdomain can thiệp.

Nếu cần một cookie dùng chung cho nhiều subdomain, __Host- không phù hợp vì nó cấm Domain. Có thể cân nhắc __Secure- cùng Domain nếu kiến trúc thực sự cần chia sẻ, nhưng phải đánh giá mọi subdomain trong phạm vi tin cậy. Một lựa chọn khác là dùng host riêng cho từng ứng dụng và trao đổi đăng nhập qua OIDC/SAML thay vì chia sẻ session cookie giữa các host.

### Không phải cookie nào cũng cần cùng prefix

| Loại cookie | Ví dụ cấu hình | Ghi chú |
| --- | --- | --- |
| Session xác thực | **__Host-session** | Ưu tiên host-only, Secure, HttpOnly và SameSite phù hợp. |
| Cookie CSRF | Tùy mô hình double-submit hoặc synchronizer token | Không nhầm CSRF token với session ID; tránh làm token dễ bị cookie tossing. |
| Tùy chọn giao diện | Cookie không nhạy cảm, ví dụ theme | Có thể không cần HttpOnly; vẫn cần cân nhắc scope và SameSite. |
| SSO cross-subdomain | Có thể cần **__Secure-** với Domain | Chỉ dùng khi trust boundary giữa subdomain được quản trị rõ. |

Không gắn prefix chỉ để “trông an toàn”. Hãy chọn theo chức năng, phạm vi và khả năng hỗ trợ của user agent.

## 8. Cookie prefix và thuộc tính bảo mật khác

Prefix bổ sung quy tắc đặt cookie, còn các thuộc tính khác giải quyết những khía cạnh riêng:

| Cơ chế | Bảo vệ chính | Không thay thế |
| --- | --- | --- |
| **Secure** | Chỉ gửi cookie qua HTTPS. | HttpOnly, SameSite, CSRF token hoặc XSS prevention. |
| **HttpOnly** | JavaScript thông thường không đọc giá trị cookie. | Ngăn script XSS gửi request bằng phiên. |
| **SameSite** | Hạn chế gửi cookie trong một số ngữ cảnh cross-site. | Toàn bộ CSRF defense hoặc XSS defense. |
| **Path/Domain** | Xác định phạm vi gửi cookie theo host/path. | Authorization hoặc ranh giới bảo mật giữa ứng dụng cùng host. |
| **Cookie prefix** | Browser hỗ trợ kiểm tra một số điều kiện khi cookie được đặt. | TLS, session validation, token revocation hoặc quyền API. |
| **CSP/output encoding** | Giảm khả năng thực thi script không tin cậy. | Bảo vệ khỏi mọi loại XSS hoặc đánh cắp thiết bị. |
| **CSRF token/Origin check** | Xác minh request thay đổi trạng thái được khởi tạo hợp lệ. | Xác thực người dùng hoặc bảo vệ cookie khỏi malware. |

Một cookie __Host-session vẫn có thể bị đánh cắp qua malware hoặc thiết bị bị xâm nhập. XSS có thể không đọc được cookie HttpOnly nhưng vẫn có thể thực hiện request cùng origin và đọc dữ liệu mà trang được phép truy cập. Vì vậy, prefix cần nằm trong defense-in-depth.

## 9. Cookie tossing và cookie shadowing

**Cookie tossing** là tình huống một host/subdomain cố đặt cookie cùng tên với cookie của ứng dụng khác, thường bằng cách dùng thuộc tính Domain rộng. **Cookie shadowing** là cách cookie cùng tên nhưng khác Path/Domain có thể tạo ra nhiều giá trị trong request, làm server xử lý nhầm cookie nào là chính.

Ví dụ:

~~~http
Set-Cookie: session=attacker-value; Domain=example.org; Path=/
Set-Cookie: session=legitimate-value; Path=/admin
~~~

Khi request phù hợp, browser có thể gửi nhiều cookie cùng tên theo quy tắc cookie. Server/framework có thể chọn giá trị đầu, cuối hoặc xử lý khác nhau; nếu các thành phần trong hệ thống parse khác nhau, có thể phát sinh lỗi bảo mật.

### Prefix giúp gì?

- __Host- ngăn browser hỗ trợ chấp nhận cookie mang prefix đó với Domain attribute, giảm khả năng subdomain đặt cookie domain-wide cùng tên.
- __Secure- yêu cầu Secure nhưng vẫn cho phép Domain, nên không giải quyết triệt để cookie tossing từ subdomain.
- __Host-Http- kết hợp host-only và HttpOnly trong browser hỗ trợ.

### Server vẫn cần làm gì?

- Dùng tên cookie riêng, khó nhầm với cookie không xác thực.
- Chọn host-only cookie cho session khi có thể.
- Xử lý cookie trùng tên một cách xác định; với session cookie, cân nhắc từ chối request có nhiều giá trị cùng tên thay vì chọn tùy tiện.
- Dùng framework/parser cookie được duy trì và kiểm thử cách xử lý duplicate names.
- Không cho subdomain không tin cậy chia sẻ cookie domain-wide.
- Không dùng cookie value do client tự đặt làm nguồn principal; phải tra session phía server.

## 10. Cookie prefix không thay thế kiểm tra session

Browser chỉ áp dụng các ràng buộc prefix khi đặt cookie. Khi request tới server, server nhận giá trị cookie và phải tự xác minh:

1. Session ID có tồn tại trong session store không?
2. Session có active, chưa hết hạn và chưa bị thu hồi không?
3. Session gắn với principal và tenant nào?
4. Tài khoản còn hoạt động không?
5. Mức assurance có đủ cho hành động yêu cầu không?
6. Principal có quyền truy cập resource/action không?

~~~mermaid
flowchart TD
    A["Request có cookie __Host-session"] --> B["Parse cookie nghiêm ngặt"]
    B --> C{"Thiếu hoặc trùng tên?"}
    C -->|"Có"| X["Từ chối / yêu cầu đăng nhập lại"]
    C -->|"Không"| D["Tra session store"]
    D --> E{"Active, chưa hết hạn,<br/>chưa revoke?"}
    E -->|"Không"| X
    E -->|"Có"| F["Xác định principal + assurance"]
    F --> G{"Được phép resource/action?"}
    G -->|"Không"| H["403 / từ chối theo policy"]
    G -->|"Có"| I["Xử lý request"]
~~~

Không được coi tên __Host-session là bằng chứng cookie hợp lệ. Client không thể tự tạo một session server-side chỉ bằng cách gửi một chuỗi có đúng prefix. Server chỉ chấp nhận ID do chính hệ thống phát hành và còn hiệu lực.

## 11. Cookie prefix, XSS và CSRF

### XSS

Cookie xác thực nên có HttpOnly; nếu dùng prefix __Host-Http- trên browser hỗ trợ, browser còn kiểm tra cookie được đặt qua HTTP response. Tuy vậy:

- HttpOnly ngăn JavaScript thông thường đọc giá trị cookie.
- XSS vẫn có thể gửi request cùng origin; browser tự đính kèm cookie.
- XSS có thể đọc nội dung response mà trang được phép đọc, thay đổi giao diện hoặc thực hiện hành động trong phiên.
- Prefix không sửa lỗi output encoding, sanitizer hoặc dependency script.

Vì vậy, cần output encoding theo ngữ cảnh, tránh HTML injection, CSP, kiểm soát script bên thứ ba và kiểm thử XSS.

### CSRF

Cookie thường được browser gửi tự động theo phạm vi và SameSite. Kẻ tấn công có thể khiến trình duyệt nạn nhân gửi request tới ứng dụng mà không cần biết cookie value. Prefix không thay đổi nguyên lý này.

Với endpoint thay đổi trạng thái:

- Dùng CSRF token gắn với session/giao dịch.
- Kiểm tra Origin và Referer theo chính sách.
- Chọn SameSite phù hợp; không coi Lax/Strict là lý do bỏ mọi kiểm soát khác.
- Không dùng GET để thay đổi trạng thái.
- Yêu cầu step-up cho thao tác nhạy cảm như thêm passkey, đổi email khôi phục hoặc tạo API key.

## 12. SSO và cookie prefix

Luồng đăng nhập liên kết OIDC/SAML thường chuyển hướng qua nhiều host. Cookie của RP, IdP và ứng dụng có phạm vi riêng. Không nên chia sẻ một session cookie domain-wide chỉ để làm SSO dễ hơn.

Một mô hình tốt hơn:

1. Người dùng xác thực tại IdP qua luồng OIDC/SAML.
2. RP kiểm tra state, nonce, issuer, audience, chữ ký và các ràng buộc giao thức.
3. RP tạo **session riêng** cho host của mình.
4. RP đặt session cookie host-only, ví dụ **__Host-session**.
5. Khi người dùng mở ứng dụng khác, ứng dụng đó thực hiện luồng federation riêng và tạo session riêng sau khi xác minh kết quả.

Cookie SameSite có thể ảnh hưởng callback cross-site. Cần chọn cấu hình phù hợp với response mode và luồng OIDC/SAML thực tế, kiểm thử trên browser mục tiêu. Không bỏ Secure hoặc mở rộng Domain rộng chỉ để khắc phục lỗi callback.

## 13. Ví dụ cấu hình đúng và sai

### Cookie session host-only

~~~http
Set-Cookie: __Host-session=RANDOM_OPAQUE_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Trong browser hỗ trợ __Host-, cấu hình này đáp ứng các điều kiện prefix. Server vẫn cần quản lý TTL, rotation và revocation.

### Cookie secure có Domain

~~~http
Set-Cookie: __Secure-sso=OPAQUE_VALUE; Domain=example.org; Path=/; Secure; HttpOnly; SameSite=None
~~~

Cấu hình này có thể phù hợp nếu thực sự cần chia sẻ cookie giữa subdomain và mọi subdomain trong phạm vi đều đáng tin cậy. Prefix __Secure- không biến cookie thành host-only.

### Ví dụ bị browser hỗ trợ từ chối

~~~http
# Thiếu Secure
Set-Cookie: __Secure-session=abc; Path=/; HttpOnly

# __Host- có Domain
Set-Cookie: __Host-session=abc; Domain=app.example.org; Path=/; Secure; HttpOnly

# __Host- thiếu Path=/
Set-Cookie: __Host-session=abc; Path=/admin; Secure; HttpOnly

# __Host-Http- thiếu HttpOnly
Set-Cookie: __Host-Http-session=abc; Path=/; Secure
~~~

Kết quả cụ thể phụ thuộc browser có hỗ trợ prefix tương ứng hay không. Ở browser không hỗ trợ, tên cookie có thể được xem như tên bình thường; vì thế server phải luôn đặt đủ thuộc tính đúng và kiểm thử user agent.

## 14. Kiểm thử cookie prefix

Một bộ kiểm thử nên xác minh cả trường hợp được chấp nhận và bị từ chối:

| Tình huống | Kết quả mong đợi trên browser hỗ trợ |
| --- | --- |
| __Secure-id từ HTTPS có Secure | Được chấp nhận nếu các điều kiện cookie khác hợp lệ. |
| __Secure-id thiếu Secure | Bị từ chối. |
| __Secure-id được đặt từ HTTP không an toàn | Bị từ chối theo quy tắc secure origin. |
| __Host-id có Secure, Path=/, không Domain | Được chấp nhận như host-only cookie. |
| __Host-id có Domain, kể cả trùng hostname | Bị từ chối. |
| __Host-id có Path khác / | Bị từ chối. |
| __Host-id thiếu Secure | Bị từ chối. |
| __Http-id thiếu HttpOnly hoặc Secure | Bị từ chối trên browser hỗ trợ prefix này. |
| __Host-Http-id có Domain hoặc thiếu Path=/ | Bị từ chối trên browser hỗ trợ prefix này. |
| JavaScript thử tạo cookie HttpOnly bằng document.cookie | Không thể đặt thuộc tính HttpOnly; browser hỗ trợ prefix Http cũng áp dụng điều kiện riêng. |
| Browser cũ không hỗ trợ prefix | Không dựa vào prefix enforcement; kiểm tra cookie attributes và server-side validation độc lập. |
| Subdomain thử đặt Domain cookie cùng tên __Host- | Browser hỗ trợ từ chối cookie vi phạm quy tắc prefix. |
| Request chứa hai cookie cùng tên session | Parser xử lý xác định hoặc từ chối; không chọn ngẫu nhiên giá trị. |

### Kiểm thử ứng dụng

- Kiểm tra header Set-Cookie thực tế ở mọi response đăng nhập, refresh và rotation.
- Xác nhận cookie không xuất hiện trong URL, log hoặc analytics.
- Kiểm tra callback SSO và các luồng cross-site với SameSite đã chọn.
- Xác nhận logout thu hồi session phía server, không chỉ xóa cookie.
- Kiểm tra browser support trên desktop, mobile và embedded webview được hỗ trợ.
- Kiểm tra session ID khó đoán, TTL, rotation và authorization độc lập với prefix.

## 15. Checklist triển khai

- [ ] Chọn prefix theo phạm vi host và yêu cầu tương thích.
- [ ] Với session cookie host-only, ưu tiên __Host- nếu browser mục tiêu hỗ trợ.
- [ ] Luôn đặt Secure cho cookie xác thực.
- [ ] Đặt HttpOnly cho session ID và token không cần JavaScript truy cập.
- [ ] Đặt Path=/ và bỏ hẳn Domain khi dùng __Host-.
- [ ] Chọn SameSite theo luồng ứng dụng/SSO và có CSRF protection phù hợp.
- [ ] Không chia sẻ cookie domain-wide giữa các subdomain không cùng trust domain.
- [ ] Kiểm tra duplicate cookie names và dùng parser có hành vi xác định.
- [ ] Không coi prefix là bằng chứng xác thực; server phải tra session/token.
- [ ] Kiểm thử browser support, webview và các luồng đăng nhập thực tế.
- [ ] Có session rotation, idle/absolute timeout, logout và revocation phía server.
- [ ] Có XSS prevention, CSP, output encoding và bảo vệ CSRF.
- [ ] Không ghi cookie value hoặc token thô vào log, trace, URL và telemetry.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao __Host-session phải có Path=/ và không được có Domain?

**Gợi ý:** Đây là điều kiện của prefix để cookie host-only, không mở rộng tới domain cha và áp dụng toàn host trong browser hỗ trợ.

**Câu 2.** __Secure- có ngăn cookie được chia sẻ cho subdomain không?

**Gợi ý:** Không. Prefix này yêu cầu secure origin và Secure; Domain vẫn có thể được đặt. Muốn host-only cần quy tắc __Host-.

**Câu 3.** Nếu browser không hỗ trợ cookie prefix, server có thể dựa vào tên __Host-session để kết luận cookie được tạo đúng không?

**Gợi ý:** Không. Browser cũ có thể coi prefix là tên thông thường. Server phải đặt thuộc tính đúng và xác minh session ở phía server.

**Câu 4.** HttpOnly có ngăn XSS thực hiện request bằng session không?

**Gợi ý:** Không. Nó ngăn JavaScript đọc giá trị cookie; browser vẫn tự gửi cookie trong request cùng origin phù hợp.

**Câu 5.** Cookie prefix có thay thế CSRF token không?

**Gợi ý:** Không. Prefix không chứng minh ý định của người dùng và không thay đổi việc browser tự gửi cookie.

**Câu 6.** Vì sao không nên dùng một cookie session domain-wide chỉ để chia sẻ đăng nhập giữa mọi subdomain?

**Gợi ý:** Mỗi subdomain mở rộng phạm vi tin cậy; subdomain yếu có thể làm tăng nguy cơ cookie injection/tossing. SSO có thể tạo session riêng ở từng host.

## 17. Ghi nhớ

**Cookie prefix là quy tắc tên giúp browser hỗ trợ kiểm tra điều kiện khi cookie được đặt.** __Secure- yêu cầu secure origin và Secure; __Host- bổ sung Path=/ và cấm Domain để tạo host-only cookie; __Http- và __Host-Http- bổ sung HttpOnly trên các browser hỗ trợ. Với session cookie của một host, __Host-session cùng Secure, HttpOnly, SameSite phù hợp là lựa chọn mạnh. Tuy vậy, prefix không mã hóa hay xác thực session, không ngăn toàn bộ XSS/CSRF và không thay thế TLS, session validation, rotation, revocation hoặc authorization phía server.
