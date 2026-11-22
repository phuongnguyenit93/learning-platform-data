# Vai trò trình duyệt trong chuyển hướng và trao đổi thông điệp của SSO

## 1. Mục tiêu và phạm vi

Trong Single Sign-On (SSO), trình duyệt (browser, hay *user agent*) là tác nhân đưa người dùng qua lại giữa ứng dụng và hệ thống định danh. Nó thực hiện điều hướng HTTP, gửi cookie đúng miền, hiển thị trang đăng nhập và đôi khi chuyển tiếp thông điệp giao thức. **Trình duyệt không tự quyết định người dùng đã được xác thực**: ứng dụng và nhà cung cấp danh tính (Identity Provider, IdP) phải kiểm tra những bằng chứng tương ứng theo giao thức.

Sau bài học, bạn có thể:
- Giải thích vì sao SSO trên web cần trình duyệt tham gia và phân biệt phiên đăng nhập ở IdP với phiên tại ứng dụng.
- Đọc luồng chuyển hướng OIDC Authorization Code và SAML 2.0 Web Browser SSO, xác định thông điệp đi qua browser và thông điệp đi trực tiếp giữa máy chủ.
- Nêu ý nghĩa của `state`, `nonce`, PKCE, `SAMLRequest`, `SAMLResponse`, `RelayState`, cookie và endpoint callback.
- Phân tích lỗi về redirect URI, SameSite cookie, callback, CORS, bảo vệ chống giả mạo và kiểm tra chữ ký.
- Liên hệ được luồng giao thức với các endpoint mặc định của Spring Security trên ứng dụng Servlet.

Trong bài, “ứng dụng” có thể là OAuth/OIDC Relying Party (RP) hoặc SAML Service Provider (SP). IdP có thể là OpenID Provider (OP) trong OIDC hoặc SAML Asserting Party trong SAML. Các ví dụ URL sử dụng miền giả định `.example`.

## 2. Ai làm gì trong một lần SSO?

| Thành phần | Trách nhiệm chính | Điều không được tự suy ra |
| --- | --- | --- |
| Người dùng | Khởi tạo truy cập, nhập thông tin đăng nhập hoặc xác nhận MFA/consent tại IdP | Việc thấy trang “đăng nhập thành công” không có nghĩa ứng dụng đã tạo phiên |
| Browser | Theo `Location` trong 302/303, gửi GET/POST, tải form, đính cookie theo luật miền/SameSite, nhận cookie phiên | Browser không phải nơi tin cậy để xác minh danh tính, chữ ký hay quyền |
| Ứng dụng RP/SP | Khởi tạo yêu cầu đăng nhập, giữ trạng thái tương quan, xử lý callback/ACS, xác minh phản hồi, thiết lập phiên cục bộ | Không nên tin mọi giá trị chỉ vì callback đến từ URL dự kiến |
| IdP/OP | Xác thực người dùng, duy trì phiên IdP và phát hành phản hồi theo giao thức | IdP không sở hữu trực tiếp cookie phiên của ứng dụng ở miền khác |
| Token endpoint / metadata / JWKS | Cung cấp điểm trao đổi mã lấy token và khóa/thông tin phục vụ xác minh khi áp dụng | Không phải mọi tương tác này đều phải đi qua browser |

SSO thường xuất hiện khi người dùng đã có **phiên IdP** từ ứng dụng A rồi truy cập ứng dụng B. Browser điều hướng tới IdP và mang cookie IdP trong yêu cầu hợp lệ; IdP nhận ra phiên sẵn có nên có thể phát phản hồi cho B mà không yêu cầu nhập lại mật khẩu. B vẫn phải xác minh phản hồi và tạo **phiên B** riêng. SSO không đồng nghĩa hai ứng dụng dùng chung cookie.

## 3. Front-channel, back-channel và ranh giới tin cậy

**Front-channel** là phần trao đổi đi *qua user agent*: chuyển hướng đến IdP, quay về callback, hoặc form tự POST phản hồi SAML. Browser tham gia đường đi, vì vậy URL, form, lịch sử điều hướng, extension và công cụ developer có thể quan sát một phần dữ liệu. Dù HTTP chạy qua HTTPS, giá trị do browser gửi vẫn là dữ liệu đầu vào chưa đáng tin cậy với RP/SP.

**Back-channel** là giao tiếp trực tiếp giữa các thành phần máy chủ trong kiến trúc web phía server: ví dụ Spring Security gửi authorization code tới token endpoint của OP qua HTTPS để nhận token; hoặc lấy metadata/JWKS từ nhà cung cấp. Browser không làm trung gian cho lời gọi HTTP đó. Thuật ngữ front-channel/back-channel nói về **đường truyền thực tế**, không chỉ về loại endpoint: trong một SPA thuần trình duyệt, lời gọi token endpoint bằng JavaScript cũng xuất phát từ browser.

| Mục đích | Thường qua browser | Thường qua máy chủ |
| --- | --- | --- |
| Mở trang đăng nhập IdP | OIDC/SAML: điều hướng top-level | Không |
| Trả OAuth/OIDC authorization code | OIDC: callback qua query trong top-level redirect | RP server đổi code tại token endpoint trong kiến trúc server-side |
| Trả bằng chứng SAML | SAML POST binding: form có `SAMLResponse` về ACS; Redirect binding thường dùng cho `AuthnRequest` | SAML Artifact binding có thể dùng back-channel để phân giải artifact nếu cấu hình |
| Kiểm tra danh tính/thiết lập phiên | Browser mang request và nhận cookie | RP/SP thực hiện xác minh và quyết định xác thực |
| Gọi API nghiệp vụ | Browser có thể gọi theo kiến trúc | Backend có thể gọi API dùng access token |

**Quy tắc quan trọng:** redirect chỉ chuyển người dùng đến URL mới; nó không tự trao token giữa backend ứng dụng và backend IdP. Khi server trả `302 Location: https://idp.example/...`, browser mới là bên tạo HTTP request tiếp theo đến IdP.

## 4. Các thao tác HTTP mà browser thực sự thực hiện

1. **Điều hướng top-level:** sau `HTTP 302 Found` hoặc `303 See Other`, browser đọc `Location` và đi tới địa chỉ đích. Phương thức khi theo redirect phụ thuộc status và quy tắc HTTP; với callback đăng nhập thường quan sát GET. Không suy rằng mọi 307/308 đều đổi POST thành GET.
2. **Gửi form:** IdP có thể trả HTML chứa form và script tự submit, khiến browser thực hiện POST tới ACS của SP. Trường form `SAMLResponse` là dữ liệu được chuyên chở, không phải “kết quả xác minh” của browser.
3. **Gửi cookie theo đích:** trong request tới `idp.example`, browser gửi cookie phù hợp của IdP; trong request tới `app.example`, nó gửi cookie phù hợp của ứng dụng. Browser không tự gửi cookie của miền A sang miền B.
4. **Nhận Set-Cookie và duy trì phiên:** ứng dụng sau khi xác thực có thể trả cookie phiên như `JSESSIONID`; các request sau đó gửi cookie theo luật của trình duyệt.
5. **Hiển thị giao diện:** người dùng thường nhập mật khẩu, passkey hoặc mã MFA trên nguồn gốc (origin) của IdP. Ứng dụng bên thứ ba không cần và không nên thu mật khẩu IdP để thực hiện federation.

Ví dụ trao đổi rút gọn (không phải toàn bộ luồng):

~~~http
GET /private HTTP/1.1
Host: app.example

HTTP/1.1 302 Found
Location: /oauth2/authorization/corp

GET /oauth2/authorization/corp HTTP/1.1
Host: app.example

HTTP/1.1 302 Found
Location: https://idp.example/authorize?response_type=code&client_id=corp-web&state=XYZ...
~~~

Dòng `Location` là hướng dẫn điều hướng; request sau đó là yêu cầu HTTP **mới do browser gửi**. URL có dấu `...` ở đây chỉ mô tả hình dạng, không phải URL thật có thể truy cập.

## 5. Luồng OIDC Authorization Code qua browser

Xét Spring Security MVC/Servlet chạy tại `https://app.example`, đăng nhập qua OP `https://idp.example` với registration ID `corp`.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant R as RP (Spring Security)
    participant I as IdP / OP
    B->>R: GET /private
    R-->>B: 302 tới login / oauth2 authorization
    B->>R: GET /oauth2/authorization/corp
    R-->>B: 302 tới OP /authorize (state, PKCE...)
    B->>I: GET /authorize
    I-->>B: Trang login hoặc dùng phiên IdP sẵn có
    B->>I: Đăng nhập/MFA nếu cần
    I-->>B: 302 về RP callback (code, state)
    B->>R: GET /login/oauth2/code/corp?code=...&state=...
    R->>I: POST /token (code, client authentication/PKCE)
    I-->>R: Token response (ID token, access token...)
    R->>R: Kiểm tra kết quả và tạo Authentication/phiên
    R-->>B: Set-Cookie phiên; redirect về /private
    B->>R: GET /private kèm cookie RP
~~~

Các bước cần hiểu đúng:

1. **Phát hiện chưa xác thực:** browser yêu cầu tài nguyên bảo vệ. `AuthorizationFilter` cùng cơ chế xử lý exception/login của Spring Security dẫn tới trang đăng nhập hoặc trực tiếp điểm khởi tạo OIDC tùy cấu hình.
2. **Tạo authorization request:** Spring Security xử lý `/oauth2/authorization/corp`, chọn cấu hình `ClientRegistration`, tạo URL đến OP authorization endpoint. Thường có `response_type=code`, `client_id`, `scope=openid`, `redirect_uri`, `state`; `nonce` dùng theo yêu cầu và cơ chế OIDC, PKCE gồm `code_challenge` khi bật/áp dụng.
3. **Browser chuyển sang IdP:** OP tự quyết định có cần login/MFA hay không. Cookie của IdP quyết định liệu người dùng đang có phiên tại IdP; cookie này khác cookie của RP.
4. **IdP quay lại ứng dụng:** OP trả redirect về URI callback đã đăng ký, thường `/login/oauth2/code/corp?code=...&state=...`. Browser mang **authorization code**, không tự suy từ code rằng người dùng đã đăng nhập.
5. **RP xử lý callback:** Spring Security đối chiếu `state` với yêu cầu đã lưu, đổi code tại token endpoint bằng HTTP từ server, dùng xác thực client và/hoặc PKCE theo loại client và cấu hình. Với OIDC, RP xác minh ID token và những ràng buộc liên quan trước khi chấp nhận principal. Sau đó RP tạo `Authentication`, thường lưu trong phiên HTTP và điều hướng về URL ban đầu.
6. **Đến tài nguyên ban đầu:** browser nhận/gửi lại cookie của RP; Spring Security dựa vào phiên RP cho các request sau, không buộc IdP xuất hiện trên mỗi lần tải trang.

Phân biệt ba thứ dễ nhầm: **authorization code** là mã ngắn hạn dùng một lần để đổi token; **ID token** mô tả sự kiện xác thực/người dùng cho RP; **access token** được dùng để truy cập tài nguyên có quyền. ID token không phải “mật khẩu thay thế”, và access token không nên mặc nhiên được dùng làm bằng chứng login chỉ vì có chữ ký.

Trong kiến trúc **server-side RP/BFF** kể trên, ID token và access token đi từ token endpoint về server RP nên không cần lộ ra URL callback của browser. Trong **SPA public client**, JavaScript có thể trực tiếp dùng Authorization Code + PKCE và thực hiện token request; khi đó phải thiết kế bảo vệ token phù hợp với rủi ro của browser. Không đánh đồng hai kiến trúc.

## 6. Vai trò của state, nonce, PKCE trong đường đi OIDC

| Dữ liệu | Ai tạo / ai kiểm tra? | Vấn đề được giải quyết |
| --- | --- | --- |
| `state` | Client/RP tạo và lưu gắn với giao dịch browser; callback trả về rồi RP so sánh | Tương quan callback với yêu cầu đã khởi tạo; hỗ trợ chống login CSRF |
| `nonce` | RP tạo theo luồng OIDC; OP đưa vào ID token; RP kiểm tra theo ngữ cảnh | Gắn ID token với yêu cầu và giảm nguy cơ token replay/injection |
| PKCE `code_verifier` / `code_challenge` | Client giữ verifier, gửi challenge ở authorization request và verifier khi đổi code | Giảm khả năng kẻ lấy cắp code đổi được token; đặc biệt bắt buộc quan trọng với public client |
| `redirect_uri` | RP đăng ký và OP đối chiếu chính xác theo chính sách chuẩn | Giới hạn nơi OP trả code, tránh code bị chuyển sang đích tùy ý |
| `iss`, `aud`, `exp`, chữ ký ID token | OP phát hành, RP xác minh | Kiểm soát nguồn phát hành, đối tượng nhận, thời hạn và tính toàn vẹn |

`state` **không phải** token định danh và không được cấp quyền chỉ dựa trên việc nó xuất hiện. `nonce` không thay cho bước xác minh chữ ký, issuer và audience. PKCE không thay thế xác thực người dùng. Khi RP làm việc với nhiều OP, cần chống *authorization server mix-up* bằng cơ chế nhận biết issuer/phân biệt callback phù hợp.

Ví dụ callback không khớp `state` phải bị từ chối, ngay cả khi URL trông đúng và `code` hợp lệ về mặt cú pháp. Browser không thể xác minh các giá trị này thay RP.

## 7. Luồng SAML 2.0 Web Browser SSO

SAML 2.0 thường dùng **HTTP-Redirect binding** để đưa `AuthnRequest` từ SP sang IdP và **HTTP-POST binding** để đưa `SAMLResponse` từ IdP về Assertion Consumer Service (ACS). Binding thực tế có thể thay đổi theo cấu hình; đây là trường hợp phổ biến của SP-initiated SSO.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant S as SP (Spring Security)
    participant I as SAML IdP
    B->>S: GET /private
    S-->>B: Bắt đầu SAML login
    B->>S: GET /saml2/authenticate/corp
    S-->>B: Redirect đến IdP?SAMLRequest=...&RelayState=...
    B->>I: GET SSO IdP mang AuthnRequest
    I-->>B: Login/MFA hoặc dùng IdP session
    I-->>B: HTML form chứa SAMLResponse, RelayState
    B->>S: POST /login/saml2/sso/corp (form)
    S->>S: Xác minh SAML và tương quan request
    S-->>B: Cookie phiên SP; redirect tài nguyên
    B->>S: GET /private kèm cookie SP
~~~

**Từng giai đoạn:**

1. SP tạo `<saml2:AuthnRequest>` có ID và các thông tin cần thiết rồi đưa sang IdP qua browser; với Redirect binding, nó thường được nén DEFLATE, Base64 và URL-encode thành query `SAMLRequest`. Chữ ký gửi kèm có thể phụ thuộc cấu hình; chỉ mã hóa Base64 **không** làm nội dung bí mật hoặc đáng tin.
2. IdP xử lý yêu cầu, xác thực người dùng hoặc dùng phiên SSO có sẵn, phát hành `SAMLResponse` chứa một hoặc nhiều assertion theo chính sách.
3. Với POST binding, IdP trả trang HTML có form; browser submit form tới ACS của SP. Form có `SAMLResponse` và có thể có `RelayState`. **Browser vận chuyển XML đã encode; browser không xác minh chữ ký của assertion.**
4. Spring Security tại ACS giải mã/parse response, kiểm tra chữ ký theo khóa tin cậy, issuer, audience, destination/recipient, thời gian hiệu lực, điều kiện SubjectConfirmation, tình trạng tương quan `InResponseTo` khi thích hợp và phòng chống replay. Chỉ sau khi xác minh thành công mới tạo `Saml2Authentication`/phiên SP.
5. `RelayState` giúp liên hệ luồng/quay lại trang đích, nhưng không được dùng như URL chuyển hướng mở không kiểm tra. Tính hợp lệ của `RelayState` một mình không chứng minh tính xác thực của `SAMLResponse`.

Minh họa form mà browser có thể nhận (giá trị response đã rút gọn; không phải assertion thật):

~~~html
<form method="post" action="https://app.example/login/saml2/sso/corp">
  <input type="hidden" name="SAMLResponse" value="BASE64_ENCODED_SAML_RESPONSE">
  <input type="hidden" name="RelayState" value="CORRELATION_VALUE">
  <button type="submit">Continue</button>
</form>
~~~

Trong thực tế IdP thường dùng JavaScript để tự submit form, nhưng cơ chế giao thức là POST từ browser đến ACS. Vì form là do IdP cung cấp và browser chỉ chuyển tiếp, SP phải kiểm tra phản hồi trên server. SAML Response thường chứa thông tin định danh hoặc thuộc tính cá nhân; **Base64 không phải mã hóa bảo mật**, vì thế không ghi raw response lên log công khai.

**IdP-initiated SSO:** browser có thể bắt đầu từ trang IdP và POST một response không tương ứng với AuthnRequest của SP. Cần chính sách riêng để nhận/khước từ unsolicited response và giảm rủi ro login CSRF; không mặc định cho rằng SP-initiated và IdP-initiated có cùng mức độ tương quan.

**SAML Artifact binding:** browser có thể chỉ mang một artifact tham chiếu; SP sau đó liên hệ IdP trực tiếp để nhận message. Điều này minh họa rằng việc “toàn bộ SAML assertion luôn qua browser” không đúng trong mọi binding.

## 8. So sánh dấu vết browser trong OIDC và SAML

| Tiêu chí | OIDC Authorization Code (RP server-side) | SAML Web Browser SSO (Redirect + POST) |
| --- | --- | --- |
| Yêu cầu đến IdP | Authorization request trên URL/redirect | AuthnRequest được encode trong `SAMLRequest` |
| Phản hồi đi qua browser | Mã `code`, `state` ở callback GET | `SAMLResponse` và `RelayState` qua form POST |
| Chứng cứ RP/SP sử dụng | ID token từ token endpoint, qua bước xác minh | SAML assertion/response trong ACS, qua bước xác minh |
| Giao tiếp server trực tiếp đặc trưng | Code đổi lấy token, metadata/JWKS | Metadata/certificate; có artifact resolution với artifact binding |
| Chống giả mạo/tương quan | `state`, `nonce`, PKCE theo vai trò | Request ID/`InResponseTo`, `RelayState` và phòng replay |
| Trường hợp cookie nhạy cảm | Callback GET cross-site và phiên RP | Callback ACS thường là cross-site POST |
| Endpoint Spring Security phổ biến | `/oauth2/authorization/{registrationId}` và `/login/oauth2/code/{registrationId}` | `/saml2/authenticate/{registrationId}` và `/login/saml2/sso/{registrationId}` |

Điểm chung: người dùng có thể nhận diện “đang đăng nhập một lần” nhờ phiên tại IdP, nhưng mỗi SP/RP vẫn chịu trách nhiệm xác minh thông điệp và thiết lập phiên của chính mình.

## 9. Cookie, SameSite và giới hạn do browser áp đặt

Cookie là mắt xích khiến điều hướng liên miền ảnh hưởng trực tiếp đến thành công của SSO. Hãy phân biệt:
- **Cookie IdP:** được browser gửi khi request đủ điều kiện tới miền IdP. Nó có thể giúp IdP tái sử dụng phiên SSO.
- **Cookie RP/SP:** được browser gửi khi request đủ điều kiện tới ứng dụng, có thể giữ trạng thái authorization request/SAML request và phiên sau login.
- **Cookie không tự chia sẻ qua miền:** hai hệ thống cùng nhận diện một người vẫn có session và cookie tách biệt.

Các thuộc tính quan trọng:
- `Secure`: cookie chỉ đi trên HTTPS (ngoại lệ cục bộ phụ thuộc browser); nên bật ở môi trường thật.
- `HttpOnly`: JavaScript không đọc được cookie, giảm tác động đánh cắp cookie bởi script, nhưng không tự chống mọi XSS/CSRF.
- `Domain`, `Path`: giới hạn nơi browser gửi cookie; cookie host-only thường chặt chẽ hơn khi không cần chia sẻ subdomain.
- `SameSite=Strict`: không gửi cookie trong request cross-site, dễ phá tương quan login qua redirect.
- `SameSite=Lax`: cho phép cookie trong điều hướng top-level từ site khác **khi phương thức an toàn như GET**; không dựa vào Lax cho cross-site POST.
- `SameSite=None; Secure`: cho phép gửi cookie cả trong nhiều request cross-site, nhưng tăng phạm vi CSRF cần kiểm soát; còn phụ thuộc chính sách chặn cookie của trình duyệt.

**Tình huống hay gặp:** SP lưu `AuthnRequest` trong HTTP session, nhưng IdP POST `SAMLResponse` về ACS ở request cross-site. Nếu browser không đính kèm cookie session SP vì `SameSite=Lax`, SP không thấy request đã lưu và báo lỗi không tương quan. Giải pháp phải dựa trên thiết kế phiên/response repository và chính sách cookie đã đánh giá (ví dụ cấu hình `SameSite=None; Secure` cho cookie phù hợp hoặc dùng cơ chế lưu tương quan khác); không tắt toàn bộ xác minh `InResponseTo` để “chữa” lỗi.

Một số browser có ngoại lệ tạm thời khi cookie **không được khai báo SameSite**; không dựa vào ngoại lệ đó làm thiết kế ổn định. Các iframe, silent login hay embedded IdP còn chịu hạn chế third-party cookie khác với điều hướng top-level; lỗi iframe không khẳng định toàn bộ SSO bằng redirect bị hỏng.

## 10. Ranh giới điều hướng, form POST, CORS và CSRF

**Top-level navigation khác `fetch()`:** việc browser điều hướng từ `app.example` sang `idp.example` bằng `Location` không vận hành như một XHR/fetch đọc dữ liệu cross-origin. CORS chủ yếu chi phối JavaScript đọc response cross-origin; thêm CORS headers thường **không sửa được** callback SAML thiếu session hay lỗi redirect URI. Nếu SPA chủ động gọi token endpoint bằng `fetch()`, CORS của endpoint đó mới có thể là ràng buộc thực tế.

**SAML POST khác submit form dữ liệu nghiệp vụ:** ACS nhận POST từ IdP, nên một quy tắc CSRF chung đòi token của ứng dụng có thể chặn request trước khi SAML xử lý. Spring Security/SAML cần cấu hình phù hợp cho đúng ACS cùng với việc xác minh chữ ký, tương quan và replay. Không vô hiệu hóa CSRF toàn bộ ứng dụng chỉ để cho phép ACS.

**Không tin dữ liệu browser:** query, fragment, form body, cookie và `Referer` có thể thiếu hoặc bị thay đổi. HTTPS bảo vệ dữ liệu trên đường truyền nhưng **không** đảm bảo callback do đúng giao dịch mong đợi tạo ra. Backend phải tự đối chiếu và xác minh.

**URL và lịch sử:** mã/giá trị xuất hiện trong query có thể lưu ở lịch sử, log proxy, monitoring hoặc rò rỉ qua những cơ chế khác nếu cấu hình sai. Hạn chế mã nhạy cảm trong URL, không đặt token dài hạn vào query, tránh open redirect, giới hạn referrer và không ghi nguyên callback chứa mã lên log không cần thiết.

## 11. Spring Security nhìn luồng này ở đâu?

Với Servlet stack, các endpoint mặc định giúp liên hệ Network tab với filter chain:

| Việc | Endpoint thường gặp | Chủ thể xử lý |
| --- | --- | --- |
| Khởi tạo OIDC/OAuth2 login | `GET /oauth2/authorization/corp` | `OAuth2AuthorizationRequestRedirectFilter` tạo authorization request, redirect tới OP |
| Nhận authorization code | `GET /login/oauth2/code/corp?code=...&state=...` | `OAuth2LoginAuthenticationFilter` xử lý callback |
| Khởi tạo SAML AuthnRequest | `GET /saml2/authenticate/corp` | `Saml2WebSsoAuthenticationRequestFilter` |
| Nhận SAML Response | `POST /login/saml2/sso/corp` | `Saml2WebSsoAuthenticationFilter` và authentication provider |

Ví dụ **cấu hình Spring Security Java (Servlet) minh họa cơ chế OAuth2/OIDC** trong một dự án Spring Boot có `spring-boot-starter-security`, `spring-boot-starter-oauth2-client` và `ClientRegistration` hợp lệ. Đây là một lớp cấu hình trong dự án, **không phải chương trình Java độc lập chạy bằng `javac SecurityConfig.java`**:

~~~java
package com.example.sso;

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
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

- `anyRequest().authenticated()` khiến truy cập chưa xác thực kích hoạt cơ chế login.
- `oauth2Login(...)` bổ sung flow Authorization Code, endpoint khởi tạo và callback theo `ClientRegistration`.
- `ClientRegistration` phải chỉ đúng issuer/authorization endpoint, token endpoint, client ID, redirect URI, scope; muốn OIDC cần scope `openid`. Việc dùng PKCE còn phụ thuộc loại client và cấu hình tương ứng.
- Không có stdout cố định cho lớp trên: kết quả là chuỗi response HTTP khi ứng dụng chạy và kết nối với OP hợp lệ.

Nếu ứng dụng chọn SAML 2.0, thay cơ chế login bằng `.saml2Login(Customizer.withDefaults())` trong một cấu hình tương ứng và cung cấp `RelyingPartyRegistration`, metadata/chứng chỉ IdP cùng dependency SAML 2.0 Service Provider. Không bật SAML chỉ bằng một redirect tự viết: xác minh response, chữ ký, thời gian, audience và ACS mới là phần bảo mật trọng yếu.

Ví dụ hai đoạn HTTP *mang tính minh họa*, không phải bằng chứng login thành công:

~~~http
HTTP/1.1 302 Found
Location: https://idp.example/authorize?response_type=code&state=...&client_id=...

HTTP/1.1 302 Found
Location: https://app.example/login/oauth2/code/corp?code=...&state=...
~~~

Mọi URI callback do reverse proxy/TLS termination tạo ra phải khớp URI đã đăng ký tại IdP; sai scheme `http`/`https`, host hoặc port đều có thể khiến IdP từ chối hoặc làm browser quay về sai nơi.

## 12. Điều gì xảy ra khi browser không đi đúng đường?

| Triệu chứng trong browser / server | Khả năng cần kiểm tra | Hướng xác minh |
| --- | --- | --- |
| Redirect loop giữa app và IdP | Cookie RP không được lưu/gửi, login session không tồn tại, proxy sai URL | Xem chuỗi 302, `Set-Cookie` và request `Cookie`, scheme/host/port |
| OP trả “invalid redirect_uri” | Callback đăng ký không khớp URI gửi lên | So sánh URI chính xác; xem cấu hình proxy forwarded headers |
| Callback OIDC báo “invalid state” | Browser mất session, nhiều tab/race, state bị đổi, request lưu sai | So state gửi đi/nhận về và nơi lưu authorization request; không bỏ kiểm tra |
| Token endpoint từ chối `invalid_grant` | Code hết hạn/đã dùng, verifier PKCE sai, redirect URI không khớp | Kiểm tra log server đã khử nhạy cảm và request token, không ghi secret |
| SAML ACS báo missing AuthnRequest/InResponseTo | Cookie session không qua POST cross-site; request repository không tìm thấy | Kiểm tra SameSite, POST ACS, cookie SP và dữ liệu tương quan |
| SAML báo invalid signature/audience/recipient | IdP metadata/cert sai, ACS URL sai, response không hợp lệ | Kiểm tra issuer, certificate, entity ID, ACS, thời gian và chữ ký |
| Browser dừng ở IdP dù login xong | Không có redirect/form trả về; URL/callback lỗi hoặc bị chặn | Network tab: sau IdP login có 302 hay HTML form POST? |
| SSO hoạt động khi mở tab nhưng lỗi trong iframe | Browser hạn chế third-party cookie/embedded context | Thử top-level redirect; đối chiếu cơ chế embedded login |
| Lỗi 403 tại ACS | Quy tắc CSRF, request matcher hoặc security filter ngăn POST | Xác nhận endpoint/method rồi rà soát cấu hình bảo vệ đúng phạm vi |
| API fetch báo CORS | Frontend đang gọi cross-origin bằng JS | Phân biệt fetch với top-level login; sửa CORS đúng endpoint được gọi |

Đừng “sửa” lỗi bằng cách bỏ validation chữ ký SAML, bỏ so khớp `state`, cho phép mọi redirect URI hoặc tắt CSRF toàn hệ thống. Những thay đổi đó có thể biến lỗi vận hành thành lỗ hổng xác thực.

## 13. Cách đọc luồng trên Developer Tools

Thực hành với môi trường thử nghiệm có tài khoản riêng và IdP được phép kiểm tra:

1. Mở tab **Network**, bật **Preserve log**, chọn nhóm **Document** (và xem các request khác khi cần). Tắt cache nếu muốn kiểm tra mới.
2. Truy cập một URL được bảo vệ khi chưa đăng nhập. Ghi lại URL đầu, các status 302/303, `Location`, request method và origin từng bước.
3. Xác định request đến IdP có phải `/authorize` (OIDC) hoặc URL có `SAMLRequest` (SAML). Kiểm tra có `state`/`RelayState` tương ứng nhưng tránh sao chép nguyên giá trị.
4. Sau đăng nhập, xác định callback: OIDC thường GET tới `/login/oauth2/code/...` có `code`; SAML thường POST đến `/login/saml2/sso/...` có form field `SAMLResponse`.
5. So sánh cookie RP/SP có được gửi ở callback và request tiếp theo; đặc biệt quan sát `SameSite`, `Secure`, `Domain` và cảnh báo cookie bị block.
6. Kiểm tra sau callback có redirect đến trang ban đầu không. Nếu callback thất bại, phân biệt lỗi do browser không gửi request/cookie và lỗi do server từ chối xác minh thông điệp.
7. Ghi sơ đồ tối thiểu `Browser → App → IdP → Browser → App`; đánh dấu rõ server gọi token endpoint ở OIDC là một nhánh khác, thường **không nằm trong Network tab của browser**.

**Lưu ý bảo mật khi debug:** không xuất/chia sẻ HAR đầy đủ chứa cookie, authorization code, SAML assertion, access token hoặc dữ liệu cá nhân. Khi cần cung cấp chứng cứ, làm mờ URL query, body, cookie và header nhạy cảm nhưng vẫn giữ method, path, status, domain và thứ tự thời gian.

## 14. Tình huống thực tế: vì sao “đã login ở IdP” vẫn chưa vào được app?

Giả sử browser đã có cookie IdP và truy cập SP. IdP nhận diện người dùng và trả SAMLResponse về ACS. Browser thực hiện POST nhưng không đính cookie phiên SP do SameSite. Vì SP đã lưu AuthnRequest trong phiên đó, SP không tìm thấy giao dịch ban đầu để so `InResponseTo` và từ chối. **IdP đã xác thực thành công nhưng SP vẫn chưa thể tin response**.

Cách phân tích:
- Có phản hồi SAML từ IdP không? Nếu có, chứng tỏ giai đoạn login IdP đã đi qua.
- Form có POST tới đúng ACS không? Nếu không, xem URL/binding.
- Cookie SP có hiện trong request POST không? Nếu không, xem SameSite/Domain/Secure và chính sách browser.
- SP có đối chiếu được request ID và chữ ký assertion không? Nếu không, sửa lưu trạng thái hoặc cấu hình giao thức, không bỏ kiểm tra.
- Sau khi hợp lệ, SP mới phát phiên của chính nó và redirect người dùng về tài nguyên.

Đổi sang OIDC Authorization Code có thể khiến callback là top-level GET và vì vậy cookie `SameSite=Lax` thường được gửi khi điều kiện phù hợp. **Đó là khác biệt về đường đi HTTP**, không phải bằng chứng rằng OIDC luôn an toàn hơn SAML hay rằng mọi SAML đều cần `SameSite=None`. Kiến trúc và cấu hình cụ thể quyết định.

## 15. Các sai lầm khái niệm thường gặp

1. **“302 nghĩa là backend app gọi IdP.”** Sai: server tạo response; browser theo `Location` và tạo request mới.
2. **“Browser biết ID token/SAML Response nên tự xác thực.”** Sai: server RP/SP phải xác minh. Browser chỉ vận chuyển/hiển thị; SPA có trách nhiệm xử lý token theo kiến trúc riêng.
3. **“Đăng nhập IdP thành công là mọi ứng dụng đã login.”** Sai: mỗi ứng dụng thiết lập phiên và quyền truy cập riêng sau khi chấp nhận phản hồi.
4. **“Base64 SAMLResponse là đã mã hóa.”** Sai: Base64 chỉ encoding; cần HTTPS, chữ ký và cơ chế bảo mật assertion thích hợp.
5. **“`state` hoặc `RelayState` là chữ ký định danh.”** Sai: chúng phục vụ tương quan/khôi phục trạng thái; phải có bước xác minh giao thức riêng.
6. **“CORS gây mọi lỗi login liên miền.”** Sai: CORS cho fetch/XHR khác với điều hướng top-level và form POST.
7. **“Cookie SameSite=Lax hoạt động như nhau cho GET và POST liên site.”** Sai: request cross-site POST thường không được gửi cookie Lax; không dựa vào ngoại lệ ngắn hạn của browser.
8. **“Logout app tự logout IdP và các app khác.”** Sai: logout cục bộ và Single Logout / OIDC logout là các quy trình riêng; còn tùy giao thức và tích hợp.
9. **“Chỉ cần thấy URL callback là hợp lệ.”** Sai: phải kiểm tra state/PKCE/nonce ở OIDC hoặc chữ ký/tương quan/thời hạn/audience ở SAML; chống replay và open redirect.
10. **“Mọi token trao đổi trong browser.”** Sai trong RP server-side OIDC Code; token endpoint là back-channel. Nhưng SPA có cách xử lý khác, nên luôn xác định loại client.

## 16. Bài tập tự kiểm tra

**Bài 1.** Trong Network tab bạn thấy `GET /login/oauth2/code/corp?code=...&state=...`; không thấy request `POST /token`. Có phải thiếu bước đổi token?  
**Gợi ý trả lời:** chưa thể kết luận. Nếu RP là ứng dụng Spring Security Servlet, token request thường do backend RP gửi tới OP, nằm ngoài Network tab của browser. Cần xem log/trace backend đã lọc secret.

**Bài 2.** Browser POST `SAMLResponse` tới ACS, nhưng server báo không tìm thấy `AuthnRequest`. Liệt kê ba thứ phải kiểm tra.  
**Gợi ý trả lời:** (1) cookie phiên SP trong POST và SameSite, (2) endpoint ACS/registrationId cùng request repository, (3) quan hệ `InResponseTo`/`RelayState` và ID yêu cầu đã lưu. Không bỏ so khớp để cho pass.

**Bài 3.** Người dùng đăng nhập ở ứng dụng A, vào ứng dụng B không phải nhập lại mật khẩu nhưng vẫn nhận cookie mới của B. Vì sao?  
**Gợi ý trả lời:** IdP dùng lại phiên của người dùng khi browser điều hướng tới nó; B xác minh phản hồi federation và tạo phiên cục bộ. Cookie A, B và IdP có phạm vi riêng.

**Bài 4.** Một callback OIDC có authorization code hợp lệ nhưng `state` khác giá trị đã lưu. Có nên gọi token endpoint?  
**Gợi ý trả lời:** không. Phải từ chối giao dịch vì không khớp trạng thái tương quan, tránh chấp nhận phản hồi không thuộc luồng browser đã khởi tạo.

## 17. Ghi nhớ để vận dụng

Browser là **phương tiện điều hướng và chuyển tiếp thông điệp của front-channel**; IdP là nơi xác thực người dùng; RP/SP là nơi **xác minh bằng chứng và tạo phiên của ứng dụng**. Để giải quyết một lỗi SSO, hãy xác định đúng ba đường đi: (1) browser đến IdP, (2) browser quay về callback/ACS, (3) trao đổi trực tiếp máy chủ nếu giao thức/kiến trúc có dùng. Sau đó kiểm tra tương quan yêu cầu, cookie, chữ ký/token và endpoint trên đúng đường đi.

### Tài liệu kỹ thuật để đối chiếu
- Spring Security — OAuth 2.0 Login (Servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — Producing SAML AuthnRequests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- OpenID Connect Core — Authorization Code Flow: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Security Best Current Practice (RFC 9700): https://www.rfc-editor.org/rfc/rfc9700
- MDN — Set-Cookie / SameSite: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie
