# Phân biệt CSRF, XSS và CORS trong ứng dụng reactive

## 1. Ba khái niệm thường bị nhầm thành một

Trong ứng dụng Spring Security reactive (Spring WebFlux), **CSRF**, **XSS** và **CORS** đều liên quan đến trình duyệt, HTTP request và ranh giới tin cậy. Nhưng chúng **không phải ba tên của cùng một lỗ hổng**, cũng không thể bật một tính năng để giải quyết cả ba.

- **CSRF — Cross-Site Request Forgery:** kẻ tấn công khiến trình duyệt của nạn nhân gửi **một request có tác động** tới hệ thống mà nạn nhân đã đăng nhập, lợi dụng credentials mà trình duyệt tự gửi (thường là session cookie). Mục tiêu là **thực hiện hành động trái ý muốn**, không nhất thiết đọc được response.
- **XSS — Cross-Site Scripting:** dữ liệu không đáng tin bị đưa vào ngữ cảnh HTML/JavaScript/DOM sai cách khiến **script của kẻ tấn công thực thi trong origin của ứng dụng**. Mục tiêu có thể là đọc thông tin hiển thị, thao tác DOM, gửi request thay nạn nhân hoặc đánh cắp token có thể đọc được.
- **CORS — Cross-Origin Resource Sharing:** một **cơ chế chính sách của trình duyệt** cho phép server quy định origin khác có thể dùng JavaScript để đọc response và gửi một số loại request xuyên origin như thế nào. **CORS không phải bộ máy xác thực, không phải cơ chế phân quyền và không phải giải pháp chống CSRF.**

Ba câu hỏi khác nhau:

| Câu hỏi | Công cụ/khái niệm |
| --- | --- |
| Có ai đang cố khiến browser của người đăng nhập gửi một thao tác không được ủy ý? | **CSRF**; xử lý bằng CSRF token, SameSite, origin checks và cấu trúc request thích hợp |
| Có dữ liệu người dùng nào bị diễn giải thành mã chạy trong trang không? | **XSS**; xử lý bằng output encoding theo ngữ cảnh, DOM API an toàn, HTML sanitization và CSP hỗ trợ |
| Script ở `https://app.example` có được đọc response từ `https://api.example` không? | **SOP/CORS**; xử lý bằng allowlist origin, methods, headers và credentials policy |

### Mục tiêu học tập

Sau bài học, bạn sẽ:
1. Giải thích được threat model và điểm khác nhau giữa CSRF, XSS, CORS, SOP và SameSite.
2. Nêu vì sao **tắt CORS không đồng nghĩa hết CSRF**, và **bật CORS không tự gây XSS**.
3. Phân biệt cookie được trình duyệt gửi tự động với Bearer token do ứng dụng chủ động gắn vào header.
4. Hiểu `CsrfWebFilter`, `ServerCsrfTokenRepository`, `ServerHttpSecurity.csrf(...)` và thứ tự xử lý CORS preflight trong Spring Security WebFlux.
5. Cấu hình CORS có allowlist cụ thể, không phản chiếu tùy tiện mọi origin có credentials.
6. Tránh XSS ở phía server/frontend bằng DTO, content type, context-aware encoding và DOM APIs an toàn.
7. Xây dựng ví dụ Java 17+ Spring Boot WebFlux có CORS, login session và CSRF đang bật; viết `WebTestClient` tests cho preflight, CSRF và xử lý dữ liệu XSS.
8. Thiết kế API/SPA cross-origin an toàn và chẩn đoán đúng lỗi 401/403/redirect/CORS.

## 2. Bức tranh tổng quan

~~~text
                       Trình duyệt nạn nhân
             ┌──────────────────────────────────┐
             │ Origin A: https://app.example     │
             │                                  │
             │ HTML / JavaScript / cookies      │
             └────────────┬─────────────────────┘
                          │
             ┌────────────┴─────────────┐
             ▼                          ▼
      Request từ trang            Script origin B
      của attacker                 muốn gọi API A
      (cross-site)                  rồi đọc response
             │                          │
             ▼                          ▼
   CSRF nguy hiểm nếu         SOP mặc định giới hạn;
   browser tự gửi cookie      CORS có thể nới điều kiện
   và server không xác minh   đọc response/loại request
   ý định thao tác             khi server cho phép
             │                          │
             └────────────┬─────────────┘
                          ▼
             Backend WebFlux/Spring Security
               CsrfWebFilter, CorsWebFilter,
               authN/authZ, controller
                          │
                          ▼
                      Response
                          │
         Dữ liệu chưa tin cậy được đưa
         vào HTML hoặc DOM qua innerHTML?
                          │
                  Có → nguy cơ XSS
                  Không + encode đúng → giảm XSS
~~~

**Lưu ý:** XSS có thể xuất phát từ dữ liệu phản hồi, trang HTML render trên server hoặc đoạn JS đọc JSON rồi đưa vào DOM. Việc JSON trả status 200 với content type đúng **không tự đảm bảo frontend an toàn** nếu frontend về sau dùng sink nguy hiểm.

## 3. CSRF: lợi dụng quyền gửi request của trình duyệt

### 3.1. Tình huống cơ bản

Nạn nhân đã đăng nhập `https://bank.example` và có cookie session. Họ mở một trang khác do attacker kiểm soát. Trang attacker gửi một form POST về `https://bank.example/transfer`. Trong điều kiện cookie policy cho phép, browser **có thể tự đính kèm cookie của bank.example** vào request được gửi tới bank.example.

Nếu server chỉ kiểm tra “có cookie session hợp lệ” mà không kiểm tra request này có nguồn gốc/ý định hợp lệ, thao tác chuyển tiền có thể được thực hiện mà nạn nhân không chủ động khởi tạo.

~~~text
Victim đang đăng nhập bank.example
         │
         ▼
Mở attacker.example
         │
         ▼
HTML form hoặc request từ trang attacker
         │
         ▼
POST https://bank.example/transfer
  Browser có thể kèm session cookie, tùy SameSite/cookie policy
         │
         ▼
Server chỉ xác minh user đã đăng nhập
         │
         ▼
Thay đổi trạng thái trái ý muốn: CSRF
~~~

Quan trọng:
- Attacker **không bắt buộc đọc được response** mới gây hại. Do đó một policy CORS không cho đọc response **không ngăn được mọi CSRF**.
- Browser chỉ tự gửi cookie trong những điều kiện tương ứng với `SameSite`, domain, path, Secure, loại navigation/request và chính sách browser. Không phải mọi cross-site POST đều chắc chắn mang cookie.
- Nếu một HTTP GET thay đổi trạng thái (xóa bản ghi, đặt hàng, logout nguy hiểm), request GET có thể bị khai thác trong nhiều ngữ cảnh mà chính sách token thường **không kiểm**. **GET/HEAD/OPTIONS/TRACE phải an toàn (safe methods): không thực hiện hành động thay đổi dữ liệu nghiệp vụ**.
- CSRF còn có thể xuất hiện trong môi trường HTTP Basic hoặc mTLS nếu trình duyệt tự gắn credentials; không chỉ session cookie.

### 3.2. Phương án chống CSRF

Với ứng dụng browser dùng session/cookie:
1. **CSRF token khó đoán, gắn với phiên hoặc bí mật của user**; server kiểm tra token trên các request thay đổi trạng thái.
2. **SameSite cookie** phù hợp để giảm tự động gửi cookie khi cross-site; đây là lớp phòng vệ bổ sung, không thay thế token trong mọi mô hình.
3. Kiểm tra **Origin/Referer** hoặc Fetch Metadata headers như `Sec-Fetch-Site` khi phù hợp; đây là lớp hỗ trợ cho một threat model rõ ràng, không tự tin tưởng headers không nhất quán ở mọi client/proxy.
4. Không dùng GET để sửa/xóa dữ liệu.
5. Đảm bảo API có authentication/authorization đúng, bảo vệ hành động nhạy cảm, có bước xác minh lại khi cần.
6. Test thiếu token/sai token đều bị từ chối, test token đúng nhưng thiếu quyền vẫn bị từ chối.

Trong Spring Security WebFlux, CSRF protection **được bật mặc định** khi dùng WebFlux security configuration, trừ khi người viết cấu hình vô hiệu hóa nó. Vì vậy, một POST không có token có thể nhận **403 Forbidden** trước khi được controller hoặc authentication manager xử lý.

### 3.3. CSRF token được gửi thế nào?

Với một HTML form do server render, form thường chứa input ẩn:

~~~html
<form method="post" action="/api/notes">
  <input type="hidden" name="_csrf" value="TOKEN_TỪ_SERVER" />
  <input name="text" />
  <button type="submit">Lưu</button>
</form>
~~~

**Đây là HTML mô tả cấu trúc; giá trị TOKEN_TỪ_SERVER không phải token thật và không dùng để chạy.** Server phải render token được tạo theo cơ chế Spring Security cho phiên đang xử lý, không hard-code một token chung hoặc lấy từ một phiên khác.

Với JavaScript POST, ứng dụng có thể gửi token qua header mà server đang nhận (thường là `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN` tùy `CsrfTokenRepository` / cấu hình). Cần xác định **repository, header name và request handler** thực tế thay vì sao chép một header từ ví dụ khác rồi kỳ vọng mọi cấu hình đều chấp nhận.

Spring Security 6.x còn có cơ chế xử lý token để giảm rủi ro BREACH khi token được nhúng vào HTML. Token hiển thị có thể khác representation lưu ở repository, nên không tự suy đoán token bằng việc so sánh một chuỗi cookie.

## 4. XSS: dữ liệu bị diễn giải thành mã trong origin đáng tin

### 4.1. XSS xảy ra tại đâu?

Ví dụ ứng dụng nhận tên người dùng và trả JSON:

~~~json
{
  "displayName": "<img src=x onerror=alert(1)>"
}
~~~

Dữ liệu này **tự nó chưa có nghĩa là script chạy** khi browser nhận JSON với content type chuẩn. Vấn đề phát sinh nếu frontend đưa chuỗi đó vào HTML parser:

~~~javascript
// SAI: chuyển dữ liệu chưa tin cậy thành HTML thực thi.
displayNode.innerHTML = data.displayName;

// ĐÚNG khi mục tiêu chỉ là hiển thị text:
displayNode.textContent = data.displayName;
~~~

Khi `innerHTML` nhận chuỗi chứa markup, browser có thể tạo các element/event handler nguy hiểm. `textContent` hiển thị dữ liệu như văn bản, không coi nó là HTML.

**XSS không nhất thiết cần thẻ script.** Event handlers, URL schemes, template injections hoặc những sink khác cũng có thể khiến mã chạy nếu ứng dụng không kiểm soát ngữ cảnh.

### 4.2. Các loại XSS

- **Reflected XSS:** tham số từ request được đưa ngay vào response HTML sai cách.
- **Stored XSS:** dữ liệu nguy hiểm được lưu trong database/comment/profile rồi hiện cho người khác.
- **DOM-based XSS:** JavaScript phía client dùng dữ liệu chưa tin cậy (URL fragment, postMessage, response JSON...) tại một DOM sink nguy hiểm như `innerHTML`, `insertAdjacentHTML` hoặc đánh giá JS động.

Một API WebFlux có thể trả DTO JSON hoàn toàn bình thường, nhưng UI ứng dụng vẫn bị DOM XSS nếu dùng sai API render. Ngược lại, một trang server-rendered Thymeleaf có thể an toàn khi dùng **escaped text expression** và mất an toàn khi render raw/unescaped HTML từ user mà không sanitize.

### 4.3. Cách bảo vệ

1. **Output encoding theo đúng ngữ cảnh**: HTML body, HTML attribute, JavaScript string, URL và CSS có quy tắc khác nhau; không dùng một hàm “escape tất cả” cho mọi nơi.
2. **Ưu tiên DOM API an toàn** như `textContent`, `createTextNode` và property assignment đúng kiểu thay vì ghép string HTML.
3. Nếu sản phẩm phải cho phép rich HTML, dùng **HTML sanitizer được duy trì và phù hợp policy**; không tự lọc bằng regex đơn giản.
4. Với template engine, dùng cơ chế **escaping mặc định**. Không dùng raw HTML expression cho dữ liệu người dùng trừ khi đã sanitize đúng mục đích.
5. Giới hạn nội dung theo business validation nhưng **input validation không thay thế output encoding**: chuỗi hợp lệ ở API này có thể nguy hiểm khi đi vào ngữ cảnh HTML khác.
6. Dùng **Content Security Policy (CSP)** làm phòng vệ bổ sung: hạn chế script sources, inline script, object sources, hạn chế nơi gửi dữ liệu. CSP không phải thay thế sửa XSS ở sink.
7. Giảm phạm vi token client-side; không lưu session ID/credentials vào HTML hoặc logs; dùng cookie flags phù hợp nhưng hiểu rằng XSS cùng origin vẫn có thể **gửi request thay người dùng**, kể cả cookie `HttpOnly` không bị JavaScript đọc trực tiếp.

### 4.4. XSS có thể phá vỡ bảo vệ CSRF như thế nào?

CSRF token chống attacker **ở origin ngoài** vì trang attacker bình thường không đọc được token bí mật của ứng dụng (nhờ SOP và thiết kế token). Nếu attacker có XSS **thực thi ngay trong origin ứng dụng**, script của họ có thể đọc DOM chứa token và gửi request cùng origin bằng cookie của nạn nhân. Vì vậy:

> Chống CSRF không thay thế chống XSS; XSS thành công có thể giúp attacker vượt qua nhiều rào cản CSRF trong cùng origin.

Không vì điều này mà tắt CSRF. **Cần cả hai**: CSRF chặn request giả mạo từ origin khác; output encoding/sanitization/CSP chặn việc attacker chạy script trong origin của chính ứng dụng.

## 5. SOP và CORS: ai được đọc response xuyên origin?

### 5.1. Origin gồm scheme + host + port

Các URL:

| URL | So với `https://app.example` |
| --- | --- |
| `https://app.example/profile` | Same-origin |
| `https://api.example/profile` | Cross-origin (khác host) |
| `http://app.example/profile` | Cross-origin (khác scheme) |
| `https://app.example:8443/profile` | Cross-origin (khác port) |

**Same-Origin Policy (SOP)** là mặc định an toàn của browser: script ở origin A bị hạn chế đọc dữ liệu từ origin B. CORS là cách server ở B tuyên bố một số trường hợp được phép đọc response xuyên origin. Không đồng nhất **origin** với **site** của cookie SameSite: “site” dùng phạm vi scheme/registrable domain phù hợp, còn origin xét cả port.

### 5.2. CORS response headers

Server có thể đáp:

~~~http
Access-Control-Allow-Origin: https://app.example
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Ý nghĩa:
- `Access-Control-Allow-Origin` cho biết origin JS nào được phép truy cập response theo CORS.
- `Access-Control-Allow-Credentials: true` cho browser biết response cross-origin có thể được expose khi client dùng credentials mode thích hợp, **với một origin được nêu cụ thể**.
- Không dùng `Access-Control-Allow-Origin: *` với credentialed response. Browser không cho wildcard kiểu đó đáp ứng yêu cầu có credentials.
- Với danh sách origin, server phải chọn origin được cho phép và trả header phù hợp, không tự phản chiếu Origin bất kỳ cùng `Allow-Credentials: true`.
- `Vary: Origin` quan trọng khi cache response thay đổi theo Origin để tránh cache lẫn policy.

### 5.3. Preflight OPTIONS có ý nghĩa gì?

Với một số request cross-origin, như POST JSON có `Content-Type: application/json` hoặc request chứa custom header, browser gửi **preflight**:

~~~http
OPTIONS /api/notes HTTP/1.1
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
~~~

Server phản hồi cho phép nếu origin/method/headers nằm trong chính sách:

~~~http
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type
Access-Control-Allow-Credentials: true
~~~

Sau preflight hợp lệ, browser mới gửi actual request trong các trường hợp phải preflight. **Preflight không tự chứng minh user có quyền hoặc có CSRF token.** Nó chỉ thể hiện browser được phép thử request theo chính sách CORS. Authentication, CSRF và authorization vẫn kiểm riêng trên request chính.

Preflight thường không mang cookie/session. Nếu CORS filter chạy sau một rule yêu cầu login, OPTIONS có thể bị 401/302/403 sai mục đích. Với Spring Security WebFlux, cần tích hợp CORS để nó được xử lý **trước** authentication/authorization thích hợp.

### 5.4. Vì sao tắt CORS không chống được CSRF?

Các **simple requests**, đặc biệt form HTML chuẩn từ origin khác, có thể được browser gửi mà không cần preflight. Nếu server trả response nhưng không có CORS headers, JavaScript bên attacker không đọc response được; điều đó **không xóa tác động POST đã được backend thực hiện**.

Bảng:

| Tình huống | CORS giúp gì? | CSRF cần gì? |
| --- | --- | --- |
| Form POST từ site khác | Không ngăn mọi form submit đơn giản | Token/Origin/SameSite và safe-method discipline |
| Fetch JSON xuyên origin | Policy CORS có thể yêu cầu preflight và kiểm response exposure | Nếu tự gửi cookie/session, vẫn cần chống CSRF theo threat model |
| Script tại chính origin ứng dụng | CORS không liên quan cho request same-origin | XSS có thể đọc token trong DOM; cần phòng XSS |
| Server-to-server request bằng curl | CORS không phải tường lửa; curl có thể gọi URL | Authentication, authorization và các biện pháp phía server |
| User truy cập hồ sơ người khác bằng ID | Không giải quyết IDOR | Object authorization/owner/tenant checks |

Đừng dựa vào CORS như cơ chế chặn client không đáng tin. Bất kỳ client ngoài browser nào cũng có thể tự gửi `Origin` giả hoặc không gửi Origin. Backend vẫn phải xác thực và phân quyền.

## 6. Cookie, SameSite, CSRF token và Bearer token

### 6.1. Session cookie được gửi tự động

Trình duyệt tự quyết định việc gửi cookie theo domain/path, Secure, SameSite và policies. Ứng dụng browser dùng session-based login phải coi một số request cross-site là có thể gây ảnh hưởng nếu cookie được gửi.

- `HttpOnly` làm JavaScript không đọc trực tiếp cookie; nó **không chặn** browser đính kèm cookie vào request.
- `Secure` yêu cầu cookie dùng trên HTTPS (có một số ngoại lệ hành vi local).
- `SameSite=Lax` giảm nhiều trường hợp gửi cookie ở cross-site subrequests, nhưng không là lá chắn tuyệt đối cho mọi CSRF/GET có side effect. SameSite cũng không trùng khái niệm với SOP/CORS.
- `SameSite=Strict` giảm cross-site cookie gửi đi hơn nữa nhưng có thể ảnh hưởng luồng điều hướng/login; cần đánh giá sản phẩm.
- `SameSite=None; Secure` thường cần cho một số mô hình cookie cross-site thật sự; do đó **không nên dựa riêng vào SameSite**.

### 6.2. Bearer token do JavaScript chủ động gắn header

Nếu API sử dụng OAuth2 Bearer token trong header `Authorization: Bearer ...` mà **browser không tự thêm** credentials này vào request cross-site từ trang attacker, rủi ro CSRF kinh điển có thể khác đáng kể so với cookie. Nhưng:
- XSS trên trang của ứng dụng có thể lấy/access token tùy chỗ lưu và có thể gửi request thay user.
- Nếu ứng dụng **vẫn dùng cookies** cho refresh token/session hoặc các endpoint khác, các endpoint đó có thể vẫn cần CSRF protection.
- HTTP Basic và client certificate có thể là ambient credentials trong browser; không suy luận “API = không cần CSRF”.
- Không tắt CSRF toàn cục chỉ vì một endpoint nhận Bearer token; phân tách security chains và kiểm tra credential delivery của từng nhóm route.

### 6.3. SPA ở origin khác cần ba lớp cấu hình độc lập

Ví dụ:
- Frontend: `http://localhost:5173`.
- Backend: `http://localhost:8080`.
- Backend dùng session cookie, không phải Bearer-only.

Muốn frontend gọi API có credentials:
1. **CORS allowlist** phải nêu đúng origin frontend; nếu có cookie thì bật allow-credentials và không dùng wildcard origin.
2. Client `fetch` phải cấu hình `credentials: "include"` (cùng với header/body phù hợp). CORS cho phép response được đọc khi các điều kiện browser thỏa.
3. **CSRF token** phải được frontend nhận một cách an toàn qua một cơ chế do backend thiết kế, rồi gửi vào header cho request POST/PUT/PATCH/DELETE. Chỉ bật CORS và credentials không tự cung cấp token CSRF.
4. Cookie SameSite/Secure/path/domain phải phù hợp. Cross-origin không nhất thiết là cross-site; hai origin khác port trên cùng hostname có thể thuộc cùng site theo mô hình của trình duyệt.
5. Server vẫn kiểm tra authentication, authorization, CSRF token và input.

Đoạn JS minh họa khi frontend **đã có token hợp lệ** (phần cấp token cần được xây riêng):

~~~javascript
async function createNote(text, csrfToken) {
  const response = await fetch("http://localhost:8080/api/notes", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-TOKEN": csrfToken
    },
    body: JSON.stringify({ text })
  });

  if (response.status === 401) {
    throw new Error("Cần đăng nhập lại");
  }
  if (response.status === 403) {
    throw new Error("Bị từ chối: quyền truy cập hoặc CSRF");
  }
  if (!response.ok) {
    throw new Error("Request thất bại");
  }
  return response.json();
}
~~~

**Đoạn minh họa không độc lập:** nó giả định user đã đăng nhập bằng cookie hợp lệ và CSRF token đã được frontend nhận theo cách đúng với repository/handler. Demo Java runnable bên dưới **chưa triển khai endpoint phát CSRF token riêng cho SPA**, vì mục tiêu là tách rạch ròi CORS và CSRF; dùng login page mặc định và Spring Security Test để kiểm chứng CSRF.

## 7. Spring Security WebFlux: các thành phần liên quan

| Thành phần | Vai trò |
| --- | --- |
| `ServerHttpSecurity` | DSL cấu hình WebFlux security chain |
| `SecurityWebFilterChain` | Chuỗi WebFilter xử lý request bảo mật |
| `CsrfWebFilter` | Kiểm tra CSRF trên các request cần được bảo vệ |
| `ServerCsrfTokenRepository` | Lưu/tải/tạo CSRF token theo chính sách |
| `WebSessionServerCsrfTokenRepository` | Repository session-based được dùng trong cấu hình CSRF WebFlux thông dụng |
| `CookieServerCsrfTokenRepository` | Tùy chọn repository theo cookie (thường trong các bài toán SPA); cần hiểu HttpOnly và request handler |
| `CorsWebFilter` / `ServerHttpSecurity.cors(...)` | Xử lý CORS/preflight theo nguồn cấu hình |
| `CorsConfigurationSource` | Cấu hình origins, methods, headers, credentials... |
| `AuthenticationWebFilter` | Thử xác thực thông tin đăng nhập ở các request phù hợp |
| `AuthorizationWebFilter` | Áp luật `authorizeExchange` theo danh tính/quyền |
| `ReactiveSecurityContextHolder` | Truy cập SecurityContext theo Reactor Context |

### 7.1. CSRF bật mặc định, ngoại lệ phải có lý do

Đoạn cấu hình:

~~~java
return http
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/public").permitAll()
        .anyExchange().authenticated()
    )
    .formLogin(Customizer.withDefaults())
    .build();
~~~

Spring Security WebFlux mặc định bảo vệ CSRF cho các HTTP methods không thuộc nhóm được xem là safe. Không thêm `.csrf(csrf -> csrf.disable())` chỉ để cho phép client POST mà không có token.

Nếu ứng dụng có một webhook/token endpoint cần ngoại lệ, hãy thiết kế **phạm vi cụ thể**, xác thực riêng bằng chữ ký/header phù hợp và test rằng các route session-cookie khác vẫn yêu cầu CSRF. Phạm vi matcher cần được review; đừng nhầm ngoại lệ CSRF với `permitAll`.

### 7.2. CORS chạy trước security authentication

Preflight `OPTIONS` thường không mang session cookie; nếu pipeline bắt login trước khi xử lý CORS thì browser báo lỗi preflight. Tích hợp CORS vào `ServerHttpSecurity` giúp CORS được xử lý đúng thứ tự theo cấu hình WebFlux.

Khi cấu hình:
- Allowlist origin có scheme + hostname + port chính xác.
- Chỉ cho phương thức và headers mà frontend cần.
- Bật `allowCredentials(true)` **chỉ khi** backend thực sự hỗ trợ request cookie/credentials cross-origin và origin được kiểm soát.
- Không phản chiếu bừa mọi origin hoặc dùng wildcard origin kèm allow-credentials.
- Test cả preflight được phép và bị từ chối, đặc biệt trên endpoint yêu cầu login.

### 7.3. CORS không thay thế HTTP authorization

Giả sử frontend được phép gọi `POST /api/notes`. User vẫn phải authenticated, CSRF token hợp lệ nếu cookie session, và có authority phù hợp nếu API yêu cầu quyền đặc biệt. Request từ origin được allow **không** đồng nghĩa được quyền vượt `authorizeExchange` hoặc quyền object-level.

CORS cũng không ngăn Postman/curl/server-to-server tự gọi API. Mọi access control quan trọng phải nằm ở server, không dựa vào browser.

## 8. Ví dụ Java 17+ chạy được: WebFlux có CSRF và CORS

Dự án dùng Spring Boot **3.3.13**, Java 17+ và Gradle 8.x. Phiên bản được cố định để bài học dùng cùng API; ứng dụng production cần phiên bản còn được hỗ trợ, nâng dependency và kiểm thử lại.

Ví dụ:
- `GET /api/public?name=...` mở cho anonymous, trả JSON; dữ liệu name có thể chứa markup nhưng API không render thành HTML.
- `GET /account` đòi session login; Spring Security sinh trang `/login` và xử lý form.
- `POST /api/notes` cần đăng nhập và **CSRF token hợp lệ**; trả JSON 201 Created.
- CORS chỉ cho `http://localhost:5173` gọi `/api/**` với GET, POST và một số headers cụ thể.
- Không disable CSRF.
- Test preflight, XSS boundary, POST có/không có CSRF và việc CORS không tạo authentication.

### 8.1. Cấu trúc dự án

~~~text
webflux-csrf-xss-cors/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── BrowserSecurityApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/demo/
        └── BrowserSecurityTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-csrf-xss-cors'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

- Spring Boot quản lý version Spring Security và Reactor phù hợp qua dependency management.
- Không thêm `spring-boot-starter-web` (Servlet MVC) vì mục tiêu là WebFlux reactive.
- `spring-security-test` cung cấp các test configurers như `mockUser()` và `csrf()`, không được dùng để cấp quyền giả trong production.

### 8.2. Lớp khởi động

`src/main/java/demo/BrowserSecurityApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BrowserSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(BrowserSecurityApplication.class, args);
    }
}
~~~

### 8.3. Cấu hình Spring Security WebFlux, CSRF và CORS

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(reader);
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration policy = new CorsConfiguration();

        // Scheme + host + PORT chính xác của frontend thử nghiệm.
        policy.setAllowedOrigins(List.of("http://localhost:5173"));
        policy.setAllowedMethods(List.of("GET", "POST"));
        policy.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
        policy.setAllowCredentials(true);
        policy.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", policy);
        return source;
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http, CorsConfigurationSource corsSource) {

        return http
            // CORS trước authN cho preflight OPTIONS.
            .cors(cors -> cors.configurationSource(corsSource))

            // KHÔNG disable CSRF. Mặc định bảo vệ POST/PUT/DELETE.
            .csrf(Customizer.withDefaults())

            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/account", "/api/notes").authenticated()
                .anyExchange().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            // Browser demo dùng form login, không cần HTTP Basic.
            .httpBasic(basic -> basic.disable())
            .build();
    }
}
~~~

**Điểm cần hiểu:**
1. `CorsConfigurationSource` dùng API reactive trong `org.springframework.web.cors.reactive`; không copy nhầm cấu hình Servlet MVC.
2. `http.cors(...)` tích hợp CORS vào Spring Security WebFlux. OPTIONS preflight hợp lệ có thể được trả lời mà không bắt buộc có session authenticated.
3. Origin chỉ được allow là `http://localhost:5173`. Origin khác như `https://malicious.example` không được tự cấp quyền. `AllowCredentials(true)` **không** đồng nghĩa mọi browser tự mang cookie; browser còn tuân thủ chính sách cookie/SameSite và client credentials mode.
4. Chúng ta chỉ đăng ký CORS cho `/api/**`. Trang `/login` và `/account` thuộc HTML navigation, không cần CORS cho script từ origin khác.
5. `csrf(Customizer.withDefaults())` cho thấy CSRF vẫn bật. Default WebFlux session-based login phù hợp với CSRF session repository.
6. `.formLogin(...)` bật trang login generated ở `GET /login` và xử lý `POST /login` (có CSRF token).
7. `authorizeExchange` bảo vệ `/account` và `/api/notes` bằng authentication; CORS không cấp quyền cho anonymous.
8. Mật khẩu demo được BCrypt hash; `reader-pass` chỉ dùng trong local sample, tuyệt đối không đưa vào production.
9. Với frontend thực dùng cookie/session cross-origin, cần thêm luồng cấp CSRF token thích hợp. CORS policy ở đây chỉ là **một phần**, không phải một ứng dụng SPA login hoàn chỉnh.

### 8.4. Controller: phân biệt JSON data với HTML thực thi

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
class DemoController {

    public record Greeting(String greeting) {}
    public record NoteInput(String text) {}
    public record NoteView(String text) {}

    // Chỉ trả JSON; KHÔNG ghép trực tiếp name thành trang HTML.
    @GetMapping("/api/public")
    Mono<Greeting> hello(
            @RequestParam(defaultValue = "guest") String name) {
        return Mono.just(new Greeting("Hello, " + name));
    }

    @GetMapping("/account")
    Mono<String> account() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx ->
                Mono.justOrEmpty(ctx.getAuthentication()))
            .map(Authentication::getName)
            .map(name -> "Hello " + name);
    }

    // Endpoint thay đổi trạng thái: yêu cầu session auth và CSRF.
    // Demo trả dữ liệu mới nhưng không lưu lâu dài vào database.
    @PostMapping("/api/notes")
    Mono<ResponseEntity<NoteView>> create(
            @RequestBody Mono<NoteInput> request) {

        return request.map(input -> {
            if (input.text() == null
                || input.text().isBlank()
                || input.text().length() > 200) {

                throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid note text");
            }

            return ResponseEntity.status(HttpStatus.CREATED)
                .body(new NoteView(input.text()));
        });
    }
}
~~~

Controller cố tình:
- Không chứa `@PostMapping("/login")` vì form login chuẩn đã được security filters xử lý.
- Không tin `origin` hay CORS để cấp identity/quyền.
- Không ghép user input thành HTML response. `Greeting` là JSON data: frontend phải render bằng `textContent`, không dùng `innerHTML`.
- Không trả raw password, cookie, SecurityContext hay token.
- `POST /api/notes` đòi cả authentication và CSRF token. Nếu CSRF sai, controller không được gọi, dù note text hợp lệ.
- Validation độ dài là hữu ích nhưng **không thay thế** escaping khi data được hiển thị trong HTML.
- Dữ liệu note không được lưu; dự án minh họa pipeline bảo mật, không phải persistence production.

### 8.5. Thử bằng browser

Chạy trong thư mục dự án với Java 17+ và Gradle 8.x:

~~~bash
gradle bootRun
~~~

Nếu có Gradle Wrapper dùng `./gradlew bootRun` (Linux/macOS) hoặc `gradlew.bat bootRun` (Windows). Server mặc định ở `http://localhost:8080`.

Thử:
1. Mở `http://localhost:8080/api/public?name=reader` → JSON `{"greeting":"Hello, reader"}`, không cần login.
2. Mở `http://localhost:8080/account` khi chưa đăng nhập → theo form-login entry point, thông thường redirect tới `/login`.
3. Trang `/login` được Spring Security tạo; đăng nhập bằng `reader` / `reader-pass`. Form mặc định đã tích hợp CSRF token.
4. Mở lại `/account` trong cùng session → nội dung `Hello reader`.
5. Với một POST thực sự tới `/api/notes`, browser phải gửi body JSON (hoặc media type mà handler chấp nhận), session cookie hợp lệ **và CSRF token hợp lệ**; bỏ CSRF sẽ bị 403.
6. Khi frontend `http://localhost:5173` chạy, preflight `OPTIONS /api/notes` với POST/Content-Type được allowlist chấp nhận. Nhưng origin được allow **không** làm `POST /api/notes` tự thành công nếu user chưa đăng nhập hoặc không có token.

**Lưu ý:** URL demo HTTP chỉ dùng local. Với browser cross-site production, cookie settings (Secure/SameSite) và CORS policy phải đồng bộ với HTTPS và threat model; tránh dùng cấu hình mở cho toàn bộ origin.

## 9. Kiểm thử tự động bằng `WebTestClient`

Spring Security Test cho reactive WebFlux hỗ trợ:
- `springSecurity()`: gắn các security filters vào mock WebTestClient bound với ApplicationContext.
- `mockUser()`: tạo user giả **chỉ trong test** để kiểm các lớp security khác; không chứng minh flow đăng nhập mật khẩu thật.
- `csrf()`: gửi CSRF token hợp lệ **chỉ trong test scope**, không disable CSRF production.
- Các request OPTIONS để kiểm CORS preflight, cùng Origin/method/headers.

`src/test/java/demo/BrowserSecurityTests.java`:

~~~java
package demo;

import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class BrowserSecurityTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicJsonIsAvailableWithoutLoginOrCsrf() {
        client.get().uri("/api/public?name=reader")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.greeting").isEqualTo("Hello, reader");
    }

    @Test
    void loginPageIsAvailableForBrowserSessionLogin() {
        client.get().uri("/login")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_HTML);
    }

    @Test
    void authenticatedUserStillNeedsCsrfForPost() {
        client.mutateWith(mockUser("reader"))
            .post().uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("text", "draft"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void validCsrfAllowsAuthenticatedPost() {
        client.mutateWith(mockUser("reader"))
            .mutateWith(csrf())
            .post().uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("text", "draft"))
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.text").isEqualTo("draft");
    }

    @Test
    void allowedOriginPreflightPassesWithoutLoginCookie() {
        client.options().uri("/api/notes")
            .header(HttpHeaders.ORIGIN, "http://localhost:5173")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "content-type")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .valueEquals(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "http://localhost:5173");
    }

    @Test
    void unknownOriginPreflightIsRejected() {
        client.options().uri("/api/notes")
            .header(HttpHeaders.ORIGIN, "https://unknown.example")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "content-type")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void allowedOriginCannotBypassCsrf() {
        client.mutateWith(mockUser("reader"))
            .post().uri("/api/notes")
            .header(HttpHeaders.ORIGIN, "http://localhost:5173")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("text", "change"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void xssLookingInputRemainsJsonDataNotHtmlResponse() {
        String input = "<img src=x onerror=alert(1)>";

        client.get().uri(uriBuilder -> uriBuilder
                .path("/api/public")
                .queryParam("name", input)
                .build())
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.greeting").isEqualTo("Hello, " + input);
    }
}
~~~

Các test được viết để chạy trong WebFlux mock server. Tám tình huống trên minh họa:

1. GET public không cần CSRF, trả JSON.
2. Trang login mặc định có thể truy cập.
3. **Đã có user** nhưng POST thiếu token vẫn bị CSRF filter từ chối 403.
4. User và token giả hợp lệ trong test cho POST đi tới controller, nhận 201.
5. CORS preflight từ origin được phép xử lý **trước auth**, không yêu cầu session cookie.
6. Preflight từ origin lạ bị từ chối.
7. Origin đã allow **không** thay CSRF token: POST vẫn 403.
8. Chuỗi trông giống HTML script được trả như JSON data, không phải response HTML thực thi. **Test này không chứng minh toàn bộ frontend chống XSS**: UI phải hiển thị bằng API DOM an toàn.

Chạy:

~~~bash
gradle test
~~~

Hoặc wrapper tương ứng nếu có. Kỳ vọng tám test pass trên dependency tương thích; cần biên dịch và chạy trong môi trường dự án để xác nhận thực tế. Không coi mock user là bằng chứng đã kiểm flow password/BCrypt; với hệ thống thật, bổ sung integration test login session và CSRF token thật.

### 9.1. Bảng test bắt buộc cho ứng dụng production

| Request | Kỳ vọng |
| --- | --- |
| GET public không cookie | 200 nếu rule `permitAll` |
| POST thay đổi dữ liệu với session thật nhưng không CSRF | 403 |
| POST với CSRF giả/sai phiên | 403 |
| POST với CSRF hợp lệ nhưng user anonymous | 401 hoặc redirect login theo entry point |
| POST với CSRF hợp lệ nhưng thiếu role | 403 |
| POST với CSRF và quyền hợp lệ | 2xx đúng contract |
| CORS preflight allowlisted | Trả origin/method/headers phù hợp; không bị login chặn |
| CORS preflight origin không được phép | Không expose access theo CORS (thường 403) |
| CORS preflight method/header không được phép | Từ chối chính sách CORS |
| GET public với chuỗi HTML ác ý | JSON là dữ liệu; frontend không dùng unsafe sink |
| Chèn dữ liệu vào HTML text/attribute/URL | Encode theo từng context, test XSS trên UI thật |
| API tài nguyên của user khác | Authorization/ownership chặn, bất kể Origin |
| POST có HTTP Basic/cookie từ browser | Đánh giá đúng CSRF threat model |
| GET có tác động dữ liệu | Đây là thiết kế sai, phải chuyển sang unsafe method có bảo vệ |

## 10. Khi nào CSRF bị tắt trong API stateless?

Câu trả lời không phải “mọi REST API đều phải disable CSRF”. Hãy xét **cách credentials đến backend**.

### Trường hợp thường có cơ sở để không dùng CSRF token

Một API chỉ dùng Bearer token, client tự gắn `Authorization: Bearer ...` và **không có ambient credential** nào được browser tự gửi; không có cookie session, remember-me cookie, Basic hoặc client certificate được dùng làm cơ sở xác thực trên cùng các endpoint. Khi đó, kẻ tấn công ở origin khác thường không thể khiến browser tự gửi Bearer token của nạn nhân bằng HTML form thuần.

Nhưng phải kiểm:
- Token có bị lộ cho origin ngoài hoặc XSS không?
- Có endpoint refresh/session/cookie dùng ambient credentials không?
- Có permissive CORS + exposed token/credential flow nào tạo rủi ro khác không?
- API có kiểm issuer, audience, expiration, scopes và object-level authorization không?
- Nếu cùng một domain phục vụ UI session và API Bearer, rule CSRF riêng cho từng chain/matcher có đúng không?

### Trường hợp vẫn cần CSRF

- Form login WebFlux dùng session cookie.
- Browser gọi API bằng cookie session.
- HTTP Basic trong browser mà browser có thể tự gửi lại credentials.
- Refresh-token cookie hoặc endpoint dùng credentials tự đính kèm.
- Bất kỳ state-changing endpoint nào chấp nhận ambient browser authentication.

**Sai lầm phổ biến:**

~~~java
// Nguy hiểm nếu ứng dụng vẫn xác thực bằng cookie/session.
http.csrf(csrf -> csrf.disable());
~~~

Đoạn code trên chỉ minh họa **anti-pattern**, không xuất hiện trong cấu hình chạy được của bài. Nếu bắt buộc loại trừ một webhook hay endpoint Bearer-only, ưu tiên phân vùng đường dẫn/security chain rõ ràng và policy riêng; đừng vô hiệu hóa toàn bộ chỉ để một POST chạy được.

## 11. Tình huống chẩn đoán thực tế

### 11.1. Browser báo “CORS policy blocked” khi frontend gọi API

Kiểm theo thứ tự:
1. Xác định chính xác **Origin** gồm scheme, host và port.
2. Kiểm preflight OPTIONS có xuất hiện không và server trả status gì.
3. Nếu có preflight, kiểm `Access-Control-Request-Method` và `Access-Control-Request-Headers` có nằm trong allowlist.
4. Kiểm server có trả `Access-Control-Allow-Origin` **đúng origin** không; `*` không được dùng cho credentialed response.
5. Với credentials, kiểm `Access-Control-Allow-Credentials`, JS `credentials: "include"`, cookie SameSite/Secure, path/domain.
6. Đảm bảo CORS filter được xử lý trước authentication: OPTIONS thường không có cookie.
7. Kiểm proxy/CDN có loại bỏ headers CORS hoặc cache sai theo Origin không.
8. Khi OPTIONS đã qua nhưng actual POST bị 403, kiểm **CSRF, authentication và quyền**; không sửa CORS bừa bãi.

### 11.2. POST 403 dù user đã login

Phân biệt:
- **CSRF 403:** thiếu/sai token trên unsafe method, token không gắn đúng session hoặc request handler.
- **Authorization 403:** đã authenticated nhưng thiếu authority/owner/tenant permission.
- **CORS 403:** preflight/actual CORS request từ origin/method/header không được phép, có thể bị CorsWebFilter từ chối.
- **Lỗi khác:** một filter/proxy/policy bảo mật khác trả 403.

Ghi log đã lọc thông tin (request ID, loại error, method, policy rule) nhưng không log session cookie, CSRF token hoặc Authorization header. Không đánh đồng mọi 403 với một nguyên nhân duy nhất.

### 11.3. GET JSON có chuỗi <img ...> có phải XSS chưa?

Chưa thể kết luận chỉ từ JSON. Nếu backend trả `Content-Type: application/json` và frontend dùng `textContent`, chuỗi chỉ là text. Nếu frontend đưa nó vào `innerHTML`, template raw output hoặc một sink giải mã HTML/JS, XSS có thể xảy ra.

Test cần bao phủ **điểm dữ liệu được đưa vào DOM** hoặc HTML view thực tế, không chỉ kiểm JSON serializer. Thêm CSP và sanitizer nơi cần HTML do user tạo.

### 11.4. SPA login có cookie nhưng API vẫn 401

Một phần nguyên nhân có thể là:
- Cookie không được gửi do SameSite, Secure, path, domain hoặc thiếu `credentials: "include"`.
- Session đã hết hạn hoặc không được lưu trên server.
- CORS policy từ chối response (browser console báo CORS, còn server có thể đã gửi status khác).
- Entry point redirect HTML khiến `fetch` đi theo và frontend cố parse như JSON.
- Cookie cross-site bị chặn bởi chính sách browser dù backend có Allow-Credentials.

Thiết kế rõ HTTP contract: navigation HTML có thể redirect tới login; API JSON nên có authentication entry point 401 phù hợp thay vì phản hồi HTML cho client tưởng JSON. CORS policy không thay việc xây contract 401.

## 12. Bộ so sánh nhanh để tránh nhầm lẫn

| Đặc điểm | CSRF | XSS | CORS |
| --- | --- | --- | --- |
| Là gì? | Lớp tấn công yêu cầu giả mạo thao tác | Lớp tấn công thực thi nội dung/script trong origin | Cơ chế browser cho phép truy cập xuyên origin theo policy |
| Mục tiêu attacker | Gửi hành động trái ý nạn nhân | Chạy mã trong origin nạn nhân | CORS misconfiguration có thể giúp script origin ngoài đọc dữ liệu |
| Điều kiện thường cần | Browser tự gửi credential; thiếu kiểm tra intent/token | Untrusted input vào HTML/JS/DOM sink nguy hiểm | Server cấu hình origin/method/header/credentials sai hoặc quá rộng |
| Có cần đọc response? | **Không** | Có thể đọc dữ liệu cùng origin nếu XSS chạy | Đọc response xuyên origin là phần trọng tâm CORS/SOP |
| Biện pháp chính | CSRF token, SameSite, origin checks, safe methods | Contextual escaping, safe DOM, sanitizer, CSP hỗ trợ | Allowlist origin, preflight handling, credential policy |
| Spring Security WebFlux | `CsrfWebFilter`, `ServerCsrfTokenRepository` | Header/CSP hỗ trợ; encoding chủ yếu tại template/UI | `CorsWebFilter`/`ServerHttpSecurity.cors` |
| Nếu user chưa login? | CSRF có thể vẫn nguy hiểm với login CSRF hoặc credential tự gửi | XSS vẫn có thể xảy ra ở trang public | CORS hoạt động cả request anonymous |
| CORS tắt có giải quyết? | **Không** | **Không** | Không cho JS cross-origin đọc response nếu không có chính sách khác |
| CSRF token có giải quyết XSS? | Không | **Không**; XSS cùng origin có thể đọc token | Không liên quan trực tiếp |

## 13. Lỗi thường gặp và cách sửa

| Lỗi | Tại sao nguy hiểm/sai | Cách sửa |
| --- | --- | --- |
| “Đã tắt CORS thì không cần CSRF” | Cross-site form POST vẫn có thể gửi và gây tác động | CSRF token và policy server-side cho unsafe methods |
| “CORS cho frontend này thì frontend tự có quyền” | CORS chỉ là browser policy, không xác thực user | AuthN, authZ và CSRF kiểm độc lập |
| `allowedOrigins("*")` với `allowCredentials(true)` | Wildcard không tương thích credentialed CORS; phản chiếu mọi origin cũng nguy hiểm | Allowlist các origin cụ thể và tối thiểu |
| Bắt đăng nhập trước preflight OPTIONS | OPTIONS thiếu cookie bị redirect/401 | Cấu hình Spring Security CORS trước auth |
| Dùng `permitAll` cho POST và tưởng CSRF bị bỏ | Authorization không tắt `CsrfWebFilter` | Cấu hình riêng matcher CSRF nếu có lý do, có test |
| Tắt CSRF toàn bộ khi dùng form login/session | Tạo cửa cho request state-changing bị giả mạo | Giữ CSRF, render token đúng repository |
| Chuyển mọi POST có CSRF thành GET cho dễ test | GET side effects dễ bị giả mạo, cache/crawler kích hoạt | Giữ unsafe methods và xử lý token |
| Lưu token CSRF hard-code trong JS | Token chung/dễ đoán không chống giả mạo | Cấp token gắn phiên/secret qua server |
| Nhầm cookie SameSite với CORS origin | Site và origin khác phạm vi; các chính sách giải quyết vấn đề khác | Thiết kế riêng cookie/CORS/CSRF |
| Dùng `innerHTML` cho dữ liệu API | DOM XSS | Dùng `textContent` hoặc sanitize HTML |
| Chỉ validate regex input và không escape output | Một input có thể đi vào ngữ cảnh render khác | Encode theo ngữ cảnh + DOM sink an toàn |
| Chỉ trả JSON nên coi frontend không có XSS | JS có thể inject JSON vào HTML | Test DOM end-to-end, tránh unsafe sink |
| Tin CSP thay sửa XSS | CSP có lỗ hổng/bypass/cấu hình không phù hợp | Fix output encoding, CSP defense-in-depth |
| Nghĩ `HttpOnly` khiến XSS không thể làm gì | JS cùng origin vẫn gửi request với cookie tự đính kèm | Chống XSS tại nguồn; HTTPOnly chỉ giảm đọc cookie |
| Log form password/CSRF token/cookie để debug | Lộ secrets trong logs | Log trace ID và loại lỗi, không raw credentials |
| Coi mọi 403 là CSRF failure | Có thể CORS/authorization/ownership | Phân loại theo filter, method, preflight, policy |
| Dùng `block()` để đọc token/security context trong WebFlux | Chặn event loop | Compose publisher reactive, trả `Mono` |
| Không kiểm CSRF token của session hiện tại | Token phiên khác có thể bị chấp nhận sai | Dùng `ServerCsrfTokenRepository` chuẩn và test mismatch |
| Coi Origin header là identity | Client không phải browser có thể giả Origin | Xác thực user/token độc lập |
| Không test preflight và actual request riêng | OPTIONS thành công nhưng POST thất bại hoặc ngược lại | Test hai bước, tách CORS/CSRF/auth |

## 14. Bài tập vận dụng

**Câu 1.** Attacker không thể đọc response do CORS, nhưng browser vẫn gửi POST chuyển tiền với cookie và server thực hiện. Đây là lỗ hổng gì?

**Đáp án:** CSRF. Không cần đọc response để gây tác động; phải bảo vệ intent bằng CSRF token/origin checks và cookie policy.

**Câu 2.** Trang user profile đọc `{"name":"<img ...>"}` rồi gán `element.innerHTML = name`. Đây là gì?

**Đáp án:** DOM-based XSS (có thể là stored/reflected tùy nguồn). Dùng `textContent` nếu chỉ hiển thị text; nếu cho HTML rich text cần sanitizer phù hợp.

**Câu 3.** Frontend `http://localhost:5173` gọi API `http://localhost:8080`. Vì sao khác origin?

**Đáp án:** Origin bao gồm port; 5173 và 8080 khác nhau dù đều localhost.

**Câu 4.** Preflight OPTIONS không có cookie nhưng API yêu cầu authenticated ở mọi route. Nên làm gì?

**Đáp án:** Để CORS xử lý preflight trước auth, giới hạn origin/method/header; actual request vẫn phải authenticated, authorized và có CSRF token nếu cần.

**Câu 5.** `Access-Control-Allow-Origin: *` và `Access-Control-Allow-Credentials: true` có phù hợp không?

**Đáp án:** Không. Browser không cho wildcard origin đáp ứng credentialed CORS; cấu hình phải allowlist origin cụ thể.

**Câu 6.** Một request từ origin đã allow nhưng thiếu CSRF token, user có session hợp lệ. POST có thành công không?

**Đáp án:** Không theo default CSRF WebFlux; unsafe POST sẽ bị kiểm CSRF, thường 403.

**Câu 7.** GET có cần CSRF token mặc định không?

**Đáp án:** Thông thường không, vì GET phải là safe method. Nếu GET gây side effect thì phải sửa thiết kế API, không chờ CSRF filter tự bảo vệ.

**Câu 8.** HTTP Basic có thể bị CSRF không?

**Đáp án:** Có thể nếu browser tự gửi credentials trong ngữ cảnh cross-site; quyết định dựa trên credential delivery, không chỉ tên cơ chế API.

**Câu 9.** Bearer token stateless chỉ do SPA gắn thủ công vào Authorization header có CSRF risk giống session-cookie không?

**Đáp án:** Không nhất thiết; ambient cookie khác header do JS chủ động gắn. Nhưng XSS và các endpoint refresh/cookie khác vẫn cần xem xét.

**Câu 10.** `HttpOnly` ngăn XSS thực hiện request với quyền user không?

**Đáp án:** Không. Nó làm JS không trực tiếp đọc cookie, nhưng browser vẫn có thể tự gửi cookie cho same-origin requests. XSS cần được chặn tại điểm render/DOM.

**Câu 11.** CORS có bảo vệ endpoint khỏi curl/Postman không?

**Đáp án:** Không. CORS là browser enforcement; server phải kiểm authentication, authorization và dữ liệu đầu vào.

**Câu 12.** Vì sao test JSON trả chuỗi `<script>` chưa đủ kết luận UI an toàn?

**Đáp án:** JSON là dữ liệu; nguy cơ xuất hiện khi UI dùng sink như `innerHTML`. Phải test đường render thật.

**Câu 13.** Browser bị redirect từ API sang `/login` rồi `response.json()` lỗi parse, có chắc CORS sai không?

**Đáp án:** Không. Có thể entry point form login trả HTML/redirect do chưa authenticated. Thiết kế API entry point 401 JSON khi phù hợp.

**Câu 14.** Có được tắt CSRF cho một webhook dùng chữ ký HMAC không?

**Đáp án:** Có thể thiết kế ngoại lệ có phạm vi rõ ràng cho endpoint không dùng ambient cookie, với xác minh chữ ký, replay protection và test. Không mở rộng ngoại lệ sang form login/session APIs.

**Câu 15.** CORS preflight OK nhưng actual POST 403 thì kiểm gì?

**Đáp án:** CSRF token đúng repository/session, authentication, quyền, cookies và các filters khác. OPTIONS thành công chỉ xác nhận CORS policy cho loại request đó.

## 15. Checklist triển khai an toàn

- [ ] Phân biệt rõ CSRF, XSS, CORS và SOP trong thiết kế; không coi một lớp thay thế lớp khác.
- [ ] CSRF protection bật cho flow dùng session/cookie/ambient credentials trên unsafe methods.
- [ ] Server cấp/kiểm CSRF token theo phiên và request handler đang cấu hình; có test thiếu/sai token.
- [ ] Không có endpoint GET thay đổi trạng thái nghiệp vụ.
- [ ] CORS allowlist chỉ gồm origin, method, header thực sự cần; preflight không bị auth chặn.
- [ ] Không dùng wildcard/reflected Origin + credentialed responses.
- [ ] Cookie `HttpOnly`, `Secure`, `SameSite`, path/domain được thiết kế phù hợp với browser flow.
- [ ] Nếu SPA cross-origin có cookie, có cơ chế cấp token cho frontend hợp đồng rõ ràng; không nghĩ CORS tự cấp token.
- [ ] Input dùng DTO, validation; output HTML được encode theo ngữ cảnh.
- [ ] DOM frontend ưu tiên `textContent` và tránh unsafe HTML sinks; rich HTML phải sanitize.
- [ ] CSP triển khai phù hợp, không thay thế sửa XSS; hạn chế script và exfiltration destinations.
- [ ] Authentication và HTTP/object authorization được kiểm ở backend, không dựa trên Origin/header do client tự gửi.
- [ ] API 401/403 và browser redirect có hợp đồng rõ ràng, tránh trả HTML cho client mong JSON.
- [ ] Có test allowed/disallowed preflight, POST thiếu CSRF, POST đủ CSRF, thiếu auth, thiếu quyền.
- [ ] Có test XSS ở điểm DOM/template thực tế, không chỉ nhìn JSON payload.
- [ ] Không log token, password, Authorization header, session cookie hoặc dữ liệu nhạy cảm.
- [ ] Không `block()` hoặc tự `subscribe()` để xử lý security context trong WebFlux.
- [ ] Cấu hình security khác nhau cho JWT stateless, HTML form/session và webhook đã được tách rõ, có security review.

## 16. Tài liệu tham khảo

- Spring Security — WebFlux CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security — Reactive CORS: https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive CSRF tests: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Framework — WebFlux CORS: https://docs.spring.io/spring-framework/reference/web/webflux-cors.html
- OWASP — CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP — XSS Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
- MDN — Cross-Origin Resource Sharing: https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS
- MDN — Same-Origin Policy: https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy

**Ghi nhớ:** **CSRF** là giả mạo thao tác bằng request mang credentials của nạn nhân; **XSS** là thực thi mã do dữ liệu không đáng tin bị render sai; **CORS** là cơ chế browser kiểm soát truy cập response và preflight giữa các origin. Với Spring Security reactive, phải cấu hình **CSRF, CORS, authentication/authorization và frontend output encoding như các lớp độc lập nhưng phối hợp**. Đừng dựa vào CORS để chống CSRF, và đừng dựa vào CSRF token để chữa XSS.
