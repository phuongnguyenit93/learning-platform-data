# Token CSRF mới sau khi thay đổi trạng thái xác thực

## Mục tiêu và bối cảnh

Trong ứng dụng Spring Security dùng cookie/session, một luồng có thể trông hoàn toàn bình thường: người dùng mở form đăng nhập, gửi đúng mật khẩu, nhận phản hồi thành công; ngay sau đó SPA gọi **POST /api/profile** nhưng bị **403 Forbidden**. Một tình huống khác: người dùng vừa đăng xuất, bấm đăng nhập lại bằng form trong tab cũ, rồi gặp lỗi **CSRF token không hợp lệ**. Những lỗi này thường đến từ việc **token chống CSRF cũ không còn phù hợp sau khi trạng thái xác thực thay đổi**.

Bài thuộc chương **Đăng nhập và đăng xuất** của module **SPRING_SECURITY_HTTP_PROTECTION**, tập trung vào các lớp phòng vệ HTTP và trình duyệt của Spring Security. Chủ đề trực tiếp là **“Token CSRF mới sau khi thay đổi trạng thái xác thực”**; các ví dụ xét cả **Servlet/Spring MVC** và **Reactive/WebFlux**, đồng thời kết nối với session protection, cookie, CORS, security headers, OAuth2/OIDC và kiểm thử trong trình duyệt.

Sau bài học, bạn có thể:

1. Vẽ vòng đời **anonymous → login → authenticated → logout → anonymous** và xác định thời điểm token CSRF cũ bị loại bỏ.
2. Phân biệt **CSRF token được lưu trong repository**, **token được trả cho browser**, và **giá trị token được mask nhằm giảm nguy cơ BREACH**.
3. Hiểu trách nhiệm của **CsrfAuthenticationStrategy**, **CsrfLogoutHandler**, cơ chế **deferred/lazy CSRF token**, và các thành phần tương đương theo stack.
4. Thiết kế form login/logout truyền thống, SPA và BFF để **lấy token mới sau khi thay đổi trạng thái xác thực** mà không tắt CSRF.
5. Cấu hình **HttpSecurity/SecurityFilterChain** trên Servlet và **ServerHttpSecurity/SecurityWebFilterChain** trên WebFlux.
6. Chọn giữa **HttpSessionCsrfTokenRepository**, **CookieCsrfTokenRepository** và repository Reactive theo yêu cầu ứng dụng.
7. Chẩn đoán **403**, session ID rotation, cookie bị chặn, CORS preflight, nhiều tab và những luồng xác thực tùy chỉnh.
8. Kiểm thử rằng **token cũ không còn được chấp nhận trong kịch bản phải thu hồi**, token mới hoạt động, và backend vẫn kiểm tra quyền tài nguyên.

## 1. Nhìn từ một lỗi thực tế: POST sau login nhận 403

Giả sử SPA có các bước:

~~~text
[1] Browser chưa đăng nhập
    GET /csrf                → nhận token T0

[2] Browser gửi form đăng nhập
    POST /login + T0         → đúng mật khẩu, login thành công

[3] Frontend giữ T0 trong biến JS hoặc state manager
    POST /api/profile + T0   → 403 do token cũ không còn hợp lệ

[4] Frontend lấy token từ phiên hiện tại
    GET /csrf                → nhận token T1

[5] Frontend gửi lại thao tác đã được user chủ động khởi tạo
    POST /api/profile + T1   → vượt kiểm tra CSRF, vẫn cần authz/nghiệp vụ
~~~

Trong cấu hình Spring Security dùng CSRF protection và session-based authentication điển hình, **CSRF token cũ được làm sạch khi authentication thành công**. Khi frontend vẫn gửi T0, token có thể không còn khớp repository hoặc session hiện tại. Yêu cầu bị từ chối là **đúng mục đích bảo mật**, không phải bằng chứng cần tắt CsrfFilter.

Một lỗi tương tự thường xảy ra sau **POST /logout**: token của authenticated session bị xóa, nhưng trang hoặc JavaScript còn giữ token cũ và dùng nó để gọi một POST khác, bao gồm login lại.

### 1.1. Ba câu hỏi chẩn đoán

Đừng bắt đầu bằng cách hỏi “làm sao tắt CSRF?”. Hãy hỏi:

- **Request trước đó đã thay đổi trạng thái authentication chưa?** Đăng nhập, đăng xuất, auto-login, account switch hoặc một authentication flow tùy chỉnh có thể ảnh hưởng token/session.
- **Browser đang gửi token lấy từ giai đoạn nào?** Từ anonymous session trước login, từ authenticated session trước logout, hay từ một tab đang giữ dữ liệu cũ?
- **Token repository và cookie/session hiện tại có còn cùng ngữ cảnh?** Nếu session ID thay đổi hoặc token bị xóa, token được lưu ở frontend chưa chắc còn hợp lệ.

Một phản hồi **403** có thể đến từ CSRF, authorization hoặc filter khác. Phải xác minh log và request, không quy mọi lỗi 403 thành “token đã rotate”.

### 1.2. CSRF không phải authentication

CSRF token giúp server phân biệt request thay đổi trạng thái được gửi theo luồng hợp lệ với request mà một website ngoài cố khiến browser tự thực hiện bằng credential. Nó **không chứng minh danh tính người dùng** và **không cấp quyền sửa dữ liệu**.

| Cơ chế | Điều cần xác minh | Không được suy ra |
| --- | --- | --- |
| **Authentication** | Principal thực sự là ai? | User chủ động thực hiện mọi request có cookie. |
| **CSRF protection** | Request unsafe có token hợp lệ theo repository/handler không? | Principal được phép sửa mọi tài nguyên. |
| **Authorization** | Principal có quyền thao tác tài nguyên/tenant cụ thể không? | Token CSRF hiện diện là đủ. |
| **Session management** | Session ID và security context còn hiệu lực không? | Cookie còn trong browser nghĩa là phiên server còn. |
| **CORS** | JavaScript của origin nào được đọc response cross-origin? | Mọi POST không hợp lệ bị chặn trước server. |
| **CSP/XSS defense** | Script và dữ liệu được thực thi trong document ra sao? | Một script XSS cùng origin không thể gọi API. |

Vì thế một request POST với **CSRF token mới** vẫn có thể bị 401 (không xác thực), 403 (không đủ quyền) hoặc lỗi nghiệp vụ. Đây là những kết quả cần phân loại riêng.

## 2. Vòng đời token xuyên qua login và logout

Với một ứng dụng dùng cookie/session và cơ chế CSRF mặc định theo stack, mô hình tư duy hữu ích là:

~~~mermaid
sequenceDiagram
    participant B as Browser / SPA
    participant S as Spring Security
    participant R as CSRF repository / session store

    B->>S: GET /csrf khi anonymous
    S->>R: Load hoặc tạo token T0
    R-->>S: T0
    S-->>B: Trả token T0 + cookie phiên nếu cần

    B->>S: POST /login + T0 + credential
    S->>R: Xác minh T0
    S->>S: Xác thực thành công
    S->>R: Xóa token cũ theo authentication strategy
    S->>S: Session strategy xử lý session ID
    S-->>B: Login success + cookie/session mới nếu cần

    B->>S: GET /csrf ở trạng thái authenticated
    S->>R: Tải hoặc tạo token T1
    R-->>S: T1
    S-->>B: Trả token T1

    B->>S: POST /api/profile + T1
    S->>R: Xác minh T1
    S->>S: Kiểm tra authentication + authorization
    S-->>B: Response nghiệp vụ

    B->>S: POST /logout + T1
    S->>R: Xác minh token T1
    S->>S: Logout handlers xóa context/session/CSRF
    S-->>B: Logout success

    B->>S: GET /csrf sau logout nếu cần login lại
    S->>R: Tải hoặc tạo token T2 cho ngữ cảnh mới
    S-->>B: Trả token T2
~~~

**T0, T1, T2 là nhãn khái niệm**, không phải định dạng hoặc tên biến framework bắt buộc. Một số repository hoặc token handler có thể dùng cách lưu/biểu diễn khác. Khi đánh giá, trọng tâm không phải đòi mọi chuỗi token quan sát được đều khác nhau về mặt byte, mà là **token trước chuyển đổi có còn được chấp nhận đúng ngữ cảnh hay không**.

### 2.1. Những mốc cần nhớ

| Thời điểm | Người dùng / trạng thái | Token nên sử dụng | Ghi chú |
| --- | --- | --- | --- |
| Mở login page | Anonymous | T0 được cấp trước login | Form POST /login cũng cần CSRF token trong mô hình session-based. |
| Gửi POST /login | Anonymous tại thời điểm request bắt đầu | T0 | CSRF được kiểm tra trước khi authentication thành công. |
| Ngay sau login thành công | Authenticated | **Không tiếp tục mặc định dùng T0** | Authentication strategy có thể xóa CSRF token cũ. |
| GET /csrf hoặc render trang mới | Authenticated | T1 được cấp/tải theo repository | Deferred token cần được truy xuất để phát token thực cho client. |
| POST/PUT/PATCH/DELETE nghiệp vụ | Authenticated | T1 hợp lệ | Vẫn cần authorization theo đối tượng. |
| POST /logout | Authenticated | T1 | CSRF xác minh trước khi logout handlers dọn state. |
| Ngay sau logout | Anonymous | **Không tiếp tục dùng T1** | Logout cleanup thường xóa token và có thể invalidate session. |
| GET login page mới / GET /csrf | Anonymous | T2 | Chuẩn bị login tiếp theo với ngữ cảnh mới. |

### 2.2. Vì sao cần xóa token ở ranh giới authentication?

Trước login và sau login, browser có thể vẫn là **cùng thiết bị**, nhưng **ngữ cảnh quyền đã thay đổi**. Token CSRF được cấp khi anonymous không nên vô điều kiện trở thành bằng chứng cho mọi hành động sau khi user được xác thực.

Đối với logout, ngữ cảnh authenticated vừa chấm dứt. Nếu vẫn giữ token cũ không qua quản lý vòng đời, một trang hoặc tab có thể cố sử dụng lại nó sau khi session đã bị dọn. Việc xóa token giúp ràng buộc token với giai đoạn xác thực phù hợp, nhưng **không tự thay session invalidation hoặc authorization**.

### 2.3. Đổi session ID và xóa CSRF token là hai chuyện khác nhau

Sau login Servlet, Spring Security có thể gọi chiến lược chống **session fixation** (ví dụ changeSessionId) và chiến lược xóa token CSRF. Không đồng nhất:

- **Session fixation protection**: bảo vệ session identifier khi principal thay đổi.
- **CsrfAuthenticationStrategy**: xử lý CSRF token trước/sau authentication theo repository.
- **CsrfLogoutHandler**: dọn CSRF token khi logout qua cơ chế Spring Security.
- **SecurityContext**: lưu thông tin authentication đã xác minh.

Với repository lưu trong HttpSession, việc thay đổi ID hoặc invalidate session có tác động đến chỗ lưu token; nhưng nguyên nhân cụ thể cần được xác minh theo **session strategy và repository thực tế**. Với repository lưu token trong cookie, mối quan hệ giữa session ID và CSRF token càng không nên được suy đoán chỉ từ tên cookie.

## 3. Cơ chế Spring Security: xóa token khi authentication và logout

### 3.1. Servlet: CsrfAuthenticationStrategy

Trong một ứng dụng Servlet có CSRF protection, Spring Security có chiến lược **CsrfAuthenticationStrategy** phối hợp với quá trình authentication để **xóa CSRF token đang lưu**. Điều này có ý nghĩa:

~~~text
Login POST mang CSRF token cũ hợp lệ
  → CsrfFilter kiểm tra token
  → AuthenticationFilter xác thực principal
  → Authentication session strategy thực hiện
  → CSRF token cũ bị xóa theo cấu hình
  → Request unsafe tiếp theo phải dùng token phù hợp ngữ cảnh mới
~~~

Trong các thiết lập đăng nhập tiêu chuẩn của Spring Security, việc dọn token là hành vi phòng vệ dự kiến. Với **custom authentication filter**, **đăng nhập thủ công** hoặc **SecurityContextHolder tự tạo**, không được mặc định giả định mọi strategy đã chạy như formLogin. Phải kiểm tra chain và gọi đúng lifecycle hooks hoặc tích hợp cơ chế bảo mật tương đương.

### 3.2. Servlet: CsrfLogoutHandler

Khi yêu cầu logout hợp lệ đi qua **LogoutFilter**, chuỗi logout handlers có thể bao gồm **CsrfLogoutHandler**, nhằm xóa CSRF token đã lưu theo repository được cấu hình.

Thứ tự tư duy:

~~~text
POST /logout + cookie + token T1
  ↓
CsrfFilter kiểm tra T1
  ↓
LogoutFilter và các handlers:
  - Dọn Authentication / SecurityContext
  - Invalidate HttpSession nếu chính sách yêu cầu
  - Dọn CSRF token T1
  - Dọn remember-me / credential khác nếu cấu hình
  ↓
LogoutSuccessHandler redirect hoặc trả 204
~~~

Nếu ứng dụng dùng một controller tự viết chỉ xóa cookie và trả 200, nó có thể **bỏ qua CsrfLogoutHandler**, session invalidation và cleanup các credentials khác. Nên ưu tiên **logout DSL** và tích hợp handler bổ sung, thay vì thay thế toàn bộ pipeline bằng thao tác thủ công không đầy đủ.

### 3.3. Reactive/WebFlux: thành phần tương ứng

Trong WebFlux, Spring Security sử dụng **WebFilter**, **ServerCsrfTokenRepository** và các thành phần đăng nhập/đăng xuất reactive. Kết quả cần đạt tương tự: token CSRF được quản lý theo chuyển đổi authentication/logout và request sau đó nhận token phù hợp với WebSession/cookie repository.

Tuy nhiên, **không sao chép nguyên xi các class Servlet vào Reactive**: HttpSessionCsrfTokenRepository, CsrfFilter và HttpServletRequest không phải đối tượng của WebFlux. Với WebFlux, phải kiểm tra **ServerHttpSecurity**, cách tạo CSRF token qua **Mono<CsrfToken>**, WebSession và các handlers reactive liên quan.

### 3.4. Không tự tạo token mới bằng JavaScript

Một mẫu sai:

~~~javascript
// KHÔNG có tác dụng cấp CSRF token hợp lệ từ Spring Security.
const csrfToken = crypto.randomUUID();
await fetch("/api/profile", {
  method: "POST",
  headers: { "X-CSRF-TOKEN": csrfToken }
});
~~~

Một chuỗi ngẫu nhiên được frontend tự tạo **không phải token mà repository server đã cấp/chấp nhận**. CSRF token hợp lệ phải đi qua cơ chế đồng bộ với backend, ví dụ render từ template hoặc **GET /csrf** dùng CSRF protection của Spring Security.

### 3.5. Không đồng nhất token CSRF với access token

| Giá trị | Công dụng | Cách xử lý sau auth change |
| --- | --- | --- |
| **CSRF token** | Xác minh request unsafe từ browser theo repository/handler. | Có thể bị xóa khi login/logout; lấy lại token theo flow mới. |
| **Session cookie** | Định vị session có authentication context trên server. | Login có thể rotate ID; logout invalidates session. |
| **OAuth2 access token** | Gọi API cho đúng audience/scope. | Có lifetime/revocation riêng; không thay CSRF token. |
| **Refresh token** | Nhận access token mới khi được cho phép. | Có chính sách rotation/revocation riêng; thường sống lâu hơn. |
| **OIDC ID token** | Xác thực subject đối với client theo OIDC. | Không tự là token CSRF hoặc access token cho mọi API. |
| **OAuth2 state** | Liên kết authorization callback với request đã khởi tạo. | Hết hiệu lực theo OAuth login flow; không thay token CSRF form. |

Mỗi loại token có **bên cấp, người nhận, mục đích và vòng đời khác nhau**. Việc cùng xuất hiện từ “token” không cho phép dùng thay cho nhau.

## 4. Deferred CSRF token: đã xóa nhưng chưa tự xuất hiện token mới

Một điểm dễ bị bỏ sót từ Spring Security hiện đại là **deferred/lazy CSRF token**. Cơ chế này giúp tránh truy cập session/repository khi request không cần token.

### 4.1. Lazy không có nghĩa token không được bảo vệ

Khi một request GET không cần CSRF để được phép tiếp tục, CSRF token có thể **chưa được tải hoặc tạo ngay lập tức**. Framework có thể cung cấp một **Supplier/CsrfToken** chờ được sử dụng; chỉ khi code thực sự yêu cầu giá trị token thì repository mới cần tải/tạo và lưu theo cơ chế thích hợp.

Do đó:

~~~text
POST /login thành công → token cũ bị xóa
  ↓
HTTP response thành công không chắc chứa token mới
  ↓
Browser cần token cho POST kế tiếp
  ↓
GET /csrf hoặc render trang có form → code truy xuất token
  ↓
CSRF repository tạo/tải token phù hợp và trả cho browser
~~~

Nếu frontend mặc định rằng Spring Security luôn đặt token mới vào cookie **ngay trong response POST /login**, nó có thể tiếp tục giữ token cũ.

### 4.2. Khi nào token mới được materialize?

Các tình huống phổ biến:

- Một trang server-rendered chứa form POST và template thực sự lấy CSRF token để chèn hidden input.
- Controller **GET /csrf** nhận CsrfToken và gọi **getToken()**, khiến token được truy xuất.
- Một SPA tích hợp cookie repository đã cấu hình request handler để **force-load token** trong những request cần cập nhật CSRF cookie.
- Một code path được framework bảo đảm truy xuất deferred token do yêu cầu request handler.

Ngược lại, một GET /health hoặc GET /public không đụng CSRF token có thể không tạo/ghi token mới; đây là tối ưu bình thường, không phải lỗi nếu ứng dụng không cần token ở đó.

### 4.3. Một lời hứa có thể gây lỗi

Một success handler tùy chỉnh như:

~~~java
// Minh họa: handler trả thành công nhưng không tự cấp token.
response.setStatus(204);
~~~

không bảo đảm trả token mới cho SPA. **HTTP 204 không có body**, session cookie có thể bị thay đổi, nhưng frontend vẫn cần cơ chế lấy token hợp lệ cho request unsafe tiếp theo.

Hợp đồng API nên nói rõ: sau login/logout, frontend phải **invalidate CSRF token cache** và **fetch một token mới từ endpoint được server cấp**, trừ khi ứng dụng đã triển khai một cơ chế đồng bộ khác có kiểm thử đầy đủ.

## 5. BREACH masking và sự khác biệt giữa token gốc với token trình bày

Một điểm quan trọng trong Spring Security 6 là cơ chế mặc định có thể dùng **XOR masking** để giảm rủi ro **BREACH** khi CSRF token xuất hiện trong nội dung response chịu nén và có dữ liệu do attacker ảnh hưởng.

### 5.1. Vì sao token quan sát được có thể thay đổi dù session không đổi?

Giả sử repository lưu **raw token R**. Mỗi lần render một trang, request handler có thể tạo một **masked token** dựa trên R cộng với một giá trị ngẫu nhiên mới:

~~~text
Repository:
  Raw token R  ────────────────┐
                               │
Response GET /form lần 1       │  mask ngẫu nhiên N1 → visible token M1
Response GET /form lần 2       │  mask ngẫu nhiên N2 → visible token M2
Response GET /form lần 3       │  mask ngẫu nhiên N3 → visible token M3

M1, M2, M3 có thể khác nhau, dù raw token R chưa thay đổi.
~~~

Server có thể **giải mask** giá trị request gửi lại rồi so với raw token trong repository theo handler đã chọn.

**Kết luận:** Không dùng phép kiểm tra “chuỗi CSRF trả về từ hai lần GET khác nhau nên token chắc chắn đã rotate” làm bằng chứng. Mặt khác, cùng một masked token bị gửi lặp có thể vẫn hợp lệ trong cùng ngữ cảnh nếu repository chưa xóa token. Phải kiểm thử **tính hợp lệ sau state transition**, không chỉ so byte.

### 5.2. BREACH và XSS/CSRF là các lớp khác nhau

- **BREACH mitigation** nhắm tới nguy cơ suy luận bí mật qua đặc điểm nén/độ dài response trong điều kiện nhất định.
- **CSRF repository** xác định token nào được chấp nhận khi xử lý request.
- **XSS defense** ngăn script độc hại chạy cùng origin, có thể đọc trang và gửi request thay người dùng.
- **Authentication/authorization** xác minh principal/quyền nghiệp vụ.

Bật masking không tự chống XSS; một script XSS có quyền đọc response/form trong origin hợp lệ có thể lấy token hiển thị và gửi request.

### 5.3. Cookie token và token trong form có thể khác dạng

Nếu ứng dụng dùng **CookieCsrfTokenRepository**, cookie thường chứa **raw token**. Với handler mặc định có XOR masking, giá trị token được đưa vào request attribute/form có thể là **masked token**. SPA đọc token trực tiếp từ cookie rồi đưa raw value vào request header có thể bị từ chối nếu request handler mong đợi masked form token.

Đây là lý do một số cấu hình SPA của Spring Security 6 cần **CsrfTokenRequestHandler tùy chỉnh**, sử dụng cách resolve **raw header token** khi lấy từ cookie và vẫn hỗ trợ masked form parameter cho HTML forms.

**Không sửa lỗi bằng cách tắt CSRF hoặc vô hiệu hóa mọi masking một cách thiếu đánh giá.** Hãy chọn pattern được Spring Security hỗ trợ và kiểm thử theo đúng phiên bản framework.

## 6. Chọn CSRF repository: token nằm ở đâu?

Repository quyết định **nơi lưu raw token** và cách tải/xóa token. Hai lựa chọn Servlet thường gặp:

| Repository | Nơi lưu | Phù hợp | Điều cần lưu ý khi auth change |
| --- | --- | --- | --- |
| **HttpSessionCsrfTokenRepository** | Session phía server. | Form login/server-rendered hoặc API/session có endpoint cấp token. | Token liên hệ session; login/logout cleanup làm token trước đó mất hiệu lực theo flow. |
| **CookieCsrfTokenRepository** | Cookie browser, theo cơ chế double-submit được triển khai. | SPA cần đọc cookie hoặc frontend/edge có contract cookie CSRF. | Sau login/logout có thể xóa cookie token; deferred generation cần được trigger để nhận cookie mới. |
| **Custom CsrfTokenRepository** | Theo thiết kế riêng. | Khi có yêu cầu hạ tầng/tích hợp đặc biệt. | Phải bảo đảm khó đoán, integrity/scope và xóa/rotate token đúng luồng; không bỏ sót auth hooks. |

Repository **không thay thế session authentication**. Cookie chứa CSRF token không nhất thiết là cookie session; nếu CSRF cookie có thể đọc bằng JavaScript, nó phải được hiểu như **token chống CSRF**, không phải bằng chứng xác thực user.

### 6.1. CookieCsrfTokenRepository và HttpOnly

Mặc định nên hạn chế JavaScript đọc cookie nhạy cảm. Với **CookieCsrfTokenRepository**, một SPA có thể chủ động chọn cho JavaScript đọc CSRF cookie:

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

// Chỉ dùng khi frontend thật sự cần đọc CSRF cookie trong JavaScript.
CookieCsrfTokenRepository repo =
        CookieCsrfTokenRepository.withHttpOnlyFalse();
~~~

**withHttpOnlyFalse() không phải lựa chọn mặc định nên áp dụng cho session cookie.** Nó chỉ thay đổi khả năng đọc của **CSRF cookie** ở repository được nêu; session cookie chứa ID vẫn nên **HttpOnly**. Với endpoint **GET /csrf trả JSON**, frontend thường không cần đọc cookie CSRF trực tiếp nên có thể giữ chiến lược HttpSessionCsrfTokenRepository.

### 6.2. Cookie scope và cross-origin SPA

Cookie không phân vùng theo **port**, nhưng có **Domain/host, Path, Secure, SameSite**. Khi frontend **app.example.com** gọi API **api.example.com**, cookie host-only do api.example.com đặt **không tự xuất hiện trong document.cookie của app.example.com** dù hai host cùng site. Nếu SPA cần đọc CSRF cookie trực tiếp, phải thiết kế **scope và phân quyền** phù hợp, không mở Domain rộng chỉ để tiện vì có thể tăng nguy cơ từ subdomain không đáng tin.

Một phương án dễ kiểm soát là **SPA gọi GET /csrf qua CORS có credentials**, nhận token trong JSON và gửi nó trong header POST, không cần cho frontend đọc cookie của API qua document.cookie.

### 6.3. Token CSRF không nên tồn tại lâu tùy ý trong localStorage

Nếu frontend lưu CSRF token vào localStorage rồi dùng lại sau reload, đăng nhập/logout/account switch, token có thể **đã hết hiệu lực**. Đây không phải lý do dùng localStorage để “giữ đăng nhập”; token CSRF **không phải credential đăng nhập**.

Chiến lược đơn giản:

- Giữ token trong **bộ nhớ ứng dụng**, gắn với session và auth state hiện tại.
- **Xóa token cache** khi bắt đầu login/logout được xác nhận hoặc khi phát hiện session principal thay đổi.
- **Lấy lại token** sau khi auth state ổn định trước request unsafe.
- Nếu tab bị reload, khởi tạo token từ server thay vì tin token localStorage cũ.
- Không log token đầy đủ và không đưa token vào URL query/history/analytics.

Không giả định xóa localStorage hay cookie ở browser **thu hồi session**: đó là trách nhiệm khác.

## 7. Spring Security Servlet: mẫu chuẩn cho form login và token mới

Với **Spring Boot 3.x / Spring Security 6.x / Spring MVC/Servlet**, có thể giữ cấu hình CSRF mặc định và cung cấp một endpoint nhỏ cho frontend lấy token.

### 7.1. Cấu hình SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class FormLoginSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/assets/**").permitAll()
                        .requestMatchers("/csrf").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form.permitAll())
                .csrf(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionFixation(fixation ->
                                fixation.changeSessionId()))
                .logout(logout -> logout
                        .invalidateHttpSession(true)
                        .permitAll())
                .build();
    }
}
~~~

**Những điều kiện cần hiểu:**

- **POST /login** vẫn cần CSRF token. **permitAll** chỉ điều khiển authorization cho login, không bỏ kiểm tra CsrfFilter.
- **POST /logout** vẫn cần CSRF token khi CSRF bật. GET /logout của trang xác nhận mặc định không tự thực hiện logout trong mô hình cấu hình thông dụng.
- **changeSessionId()** bảo vệ session fixation; đây không phải hành động cấp token CSRF mới cho frontend.
- **/csrf** được cho anonymous truy cập vì token cần thiết **ngay trước login**. Endpoint không nên trả session ID hoặc token xác thực.
- Nếu dùng nhiều SecurityFilterChain, cần xác định chain xử lý các URL liên quan và không để một chain khác tắt CSRF trên /login hoặc /logout ngoài ý định.
- CSRF repository mặc định trên Servlet thường dùng session. Nếu ứng dụng thay repository/handler, cần thiết kế đúng cách cấp token mới tương ứng.

### 7.2. Endpoint GET /csrf cấp token

~~~java
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfTokenController {

    @GetMapping("/csrf")
    ResponseEntity<Map<String, String>> csrf(CsrfToken csrfToken) {
        // Truy xuất giá trị thực sự khiến deferred token được resolve.
        String value = csrfToken.getToken();

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                        "headerName", csrfToken.getHeaderName(),
                        "parameterName", csrfToken.getParameterName(),
                        "token", value));
    }
}
~~~

Endpoint này chỉ minh họa hợp đồng cấp CSRF token; response có thể bị chặn bởi authentication/CORS nếu ứng dụng chưa cấu hình đồng bộ. Trong một ứng dụng session-based, GET /csrf có thể khiến browser nhận một **anonymous HttpSession cookie** để lưu token trước đăng nhập.

**Không trả token cho mọi origin với credentials** và không đưa token vào URL query. GET /csrf nên có **Cache-Control: no-store** và policy cache/proxy phù hợp, vì response gắn với ngữ cảnh browser/session.

Trong Spring Security 6, giá trị do **getToken()** trả ra có thể là một **masked token** theo request handler; đó vẫn là giá trị hợp lệ để frontend gửi lại theo cơ chế đang cấu hình. Không thay bằng một giá trị cố định hoặc một token tự tạo ở JavaScript.

### 7.3. Luồng server-rendered với Thymeleaf

Với Spring MVC/Thymeleaf tích hợp đúng, form login có thể viết:

~~~html
<form th:action="@{/login}" method="post">
  <label for="username">Tài khoản</label>
  <input id="username" name="username" autocomplete="username">

  <label for="password">Mật khẩu</label>
  <input id="password" name="password" type="password"
         autocomplete="current-password">

  <button type="submit">Đăng nhập</button>
</form>
~~~

Khi dùng integration Spring MVC/Spring Security phù hợp, **RequestDataValueProcessor** có thể tự chèn hidden CSRF input cho form POST có **th:action**. Hãy kiểm tra HTML đã render trong browser, vì việc có field token phụ thuộc template engine và cấu hình thực tế.

Một dạng HTML cuối cùng được mong đợi:

~~~html
<form action="/login" method="post">
  <input name="username">
  <input name="password" type="password">
  <input type="hidden" name="_csrf"
         value="TOKEN_THUC_DO_SPRING_SECURITY_CAP">
  <button type="submit">Đăng nhập</button>
</form>
~~~

Giá trị ví dụ là **placeholder**. Không hard-code trong HTML production. Sau login thành công, một lần chuyển đến trang server-rendered mới có form cần token sẽ truy xuất token từ ngữ cảnh mới, giúp tránh dùng token của form trước login.

### 7.4. Trang sau login dùng token mới

Một ví dụ form POST thay đổi thông tin cá nhân:

~~~html
<form th:action="@{/profile}" method="post">
  <input name="displayName" autocomplete="nickname">
  <button type="submit">Lưu hồ sơ</button>
</form>
~~~

Nếu trang này được render **sau khi login** và engine chèn CSRF token đúng, request POST sẽ dùng token phù hợp authenticated session. Không sao chép hidden field **_csrf** từ trang login trước đó sang form được lưu ở client rồi dùng lại sau khi session đã thay đổi.

### 7.5. Logout và đăng nhập lại

Sau POST /logout hợp lệ, ứng dụng thường redirect về /login?logout hoặc trang tương đương. Trong quá trình render login page tiếp theo, Spring Security có thể cấp token mới cho **ngữ cảnh anonymous**.

Nếu ứng dụng thay logout success handler bằng **204 No Content**, browser sẽ không tự tải trang login mới. SPA phải chủ động **GET /csrf** trước lần POST /login tiếp theo; không tiếp tục giữ token trước logout trong JavaScript state.

### 7.6. Tùy chỉnh authentication: nguy cơ bỏ qua cleanup strategy

Một số ứng dụng không dùng formLogin tiêu chuẩn mà tự tạo controller:

~~~java
// Minh họa anti-pattern, KHÔNG phải flow đăng nhập hoàn chỉnh.
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

Việc tự đặt Authentication vào ThreadLocal **không tự bảo đảm** đã chạy mọi session strategy, CSRF authentication cleanup, SecurityContextRepository persistence, session fixation protection và các event/handlers liên quan. Từ Spring Security hiện đại, cơ chế lưu security context có thể đòi **lưu rõ ràng** tùy cấu hình.

Nếu bắt buộc triển khai authentication filter riêng, phải thiết kế đầy đủ:

1. CsrfFilter vẫn bảo vệ request login dùng session/cookie.
2. AuthenticationManager/provider xác minh credential thật.
3. SessionAuthenticationStrategy/CSRF cleanup phù hợp được gọi trong luồng thành công.
4. Session ID được bảo vệ trước fixation.
5. SecurityContext được lưu bằng repository thích hợp.
6. Success/failure handler không làm rò credential và không bỏ qua token refresh.
7. Có integration test chứng minh **token cũ không còn dùng được** khi authentication thành công theo policy.

Không dùng giải pháp “manual login được rồi” làm bằng chứng rằng token lifecycle của Spring Security còn nguyên.

## 8. SPA dùng session: hợp đồng lấy token trước và sau auth change

Một SPA có thể lưu token CSRF trong biến JavaScript, Redux/Pinia hoặc React state. Điều này thuận tiện, nhưng frontend phải **gắn token với trạng thái phiên hiện tại** thay vì giữ mãi một giá trị.

### 8.1. Hợp đồng frontend–backend đề xuất

| Endpoint | Method | Ai được phép gọi? | Kết quả | Liên quan CSRF |
| --- | --- | --- | --- | --- |
| **/csrf** | GET | Anonymous và authenticated theo chính sách | JSON token phù hợp session hiện tại; không cache công khai. | Trigger deferred token, lấy giá trị mới khi cần. |
| **/login** | POST | Anonymous, nhưng chỉ xử lý credential hợp lệ | Tạo authenticated session hoặc trả lỗi. | Dùng token lấy **trước login**; token đó có thể bị xóa sau thành công. |
| **/api/me** | GET | Authenticated | User/tenant hiện tại theo session. | Dùng để xác nhận principal sau login, không thay CSRF. |
| **/api/profile** | POST | Authenticated có quyền | Cập nhật thông tin. | Dùng token lấy **sau login**. |
| **/logout** | POST | Phiên hiện tại theo logout policy | Vô hiệu hóa trạng thái xác thực, trả 204 hoặc redirect. | Dùng token của phiên trước logout; token ấy có thể bị xóa sau thành công. |

**Lưu ý:** Đây là một hợp đồng minh họa. Spring Security mặc định có thể dùng redirect sau formLogin/logout; SPA nên thống nhất rõ một cách phản hồi (ví dụ 204 khi thành công) thay vì dựa vào 302 không rõ phía client.

### 8.2. Config Servlet cho SPA trả 204

~~~java
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.HttpStatusReturningLogoutSuccessHandler;

@Configuration
class SpaSessionSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/csrf", "/assets/**")
                            .permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .permitAll()
                        .successHandler((request, response, auth) ->
                                response.setStatus(
                                        HttpServletResponse.SC_NO_CONTENT))
                        .failureHandler((request, response, exception) ->
                                response.sendError(
                                        HttpServletResponse.SC_UNAUTHORIZED)))
                .csrf(Customizer.withDefaults())
                .logout(logout -> logout
                        .logoutSuccessHandler(
                                new HttpStatusReturningLogoutSuccessHandler(
                                        HttpStatus.NO_CONTENT))
                        .invalidateHttpSession(true)
                        .permitAll())
                .build();
    }
}
~~~

**Cấu hình này là phương án thay thế mục 7.1**, không khai báo hai filter chains trùng matcher trong cùng ứng dụng. Nó giữ **form parameters username/password** của formLogin mặc định và thay success/failure response cho SPA. Nếu frontend POST JSON, bạn phải triển khai authentication mechanism đọc JSON theo thiết kế; không tự suy ra formLogin mặc định phân tích JSON.

Backend cũng cần authentication provider, cookie/session settings, endpoint **GET /csrf**, quyền từng API, CORS nếu frontend khác origin và các security headers thích hợp.

### 8.3. Quy trình frontend có state token rõ ràng

Một ví dụ JavaScript chạy trên SPA, với API cùng origin hoặc đã cấu hình CORS phù hợp:

~~~javascript
const apiBase = "https://api.example.com";

let csrf = null;
let currentUser = null;

async function fetchCsrf() {
  const response = await fetch(apiBase + "/csrf", {
    credentials: "include",
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error("Không nhận được CSRF token cho phiên hiện tại");
  }

  const data = await response.json();
  if (typeof data.headerName !== "string" ||
      typeof data.token !== "string") {
    throw new Error("Phản hồi CSRF không hợp lệ");
  }
  csrf = data;
  return csrf;
}

async function login(username, password) {
  // Token cho anonymous phase.
  await fetchCsrf();

  const body = new URLSearchParams({ username, password });
  const response = await fetch(apiBase + "/login", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      [csrf.headerName]: csrf.token
    },
    body,
    redirect: "error"
  });

  if (!response.ok) {
    throw new Error("Đăng nhập thất bại");
  }

  // Không giữ token T0 của anonymous session.
  csrf = null;

  const me = await fetch(apiBase + "/api/me", {
    credentials: "include",
    cache: "no-store"
  });
  if (!me.ok) throw new Error("Không xác nhận được principal sau login");
  currentUser = await me.json();

  // Materialize token T1 của authenticated phase.
  await fetchCsrf();
  return currentUser;
}

async function saveProfile(payload) {
  if (!csrf) await fetchCsrf();

  const response = await fetch(apiBase + "/api/profile", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    throw new Error("Không lưu được hồ sơ: " + response.status);
  }
}

async function logout() {
  if (!csrf) await fetchCsrf();

  const response = await fetch(apiBase + "/logout", {
    method: "POST",
    credentials: "include",
    headers: {
      [csrf.headerName]: csrf.token
    },
    redirect: "error"
  });

  if (!response.ok) throw new Error("Logout chưa được xác nhận");

  // Token T1 không còn thuộc anonymous phase mới.
  csrf = null;
  currentUser = null;
  clearSensitiveClientState();

  // Nếu vẫn hiển thị form đăng nhập trong SPA:
  await fetchCsrf();
}
~~~

**clearSensitiveClientState()** là hàm do ứng dụng triển khai, không phải API của trình duyệt. Đoạn code giả định backend đã được cấu hình **trả 204** khi login/logout thành công; nếu backend dùng redirect, phải thống nhất contract hoặc xử lý điều hướng đúng.

Một số lưu ý quan trọng:

- Việc gọi GET /csrf **ngay sau login** nhằm đồng bộ token với session/auth state mới; không được suy ra chỉ từ HTTP 204 rằng token mới đã tồn tại.
- **Đừng lưu password hoặc CSRF token vào URL, log hay localStorage** không cần thiết.
- Trong trường hợp login hoặc logout **bị lỗi mạng sau khi server đã thay đổi state**, frontend chưa biết chắc trạng thái; phải xác minh session, không tự động retry thao tác nghiệp vụ tùy ý.
- Với **401/403 từ API**, phân loại rõ thiếu authentication, CSRF và authorization thay vì xoá token rồi gửi lại POST hàng loạt.
- Nếu backend dùng **CookieCsrfTokenRepository**, contract token/header và request handler có thể khác ví dụ nhận token qua JSON. Không trộn hai chiến lược khi chưa kiểm thử.

### 8.4. Nếu frontend dùng nhiều request unsafe liên tiếp

Khi người dùng gửi nhiều POST đồng thời, chỉ một giá trị token trong authenticated session có thể dùng cho những request đó **nếu repository và policy cho phép**. Không mặc định bắt buộc xoay token sau **mỗi POST**. Spring Security không đồng nghĩa với “one-time CSRF token cho mọi request”.

Ngược lại, nếu **một request trong loạt** làm authentication thay đổi (login/logout/account switching), các request unsafe còn lại có thể dùng token thuộc trạng thái cũ và bị từ chối, hoặc nguy hiểm hơn nếu triển khai custom token lifecycle sai.

Hãy thiết kế một **auth-transition barrier** ở frontend:

~~~text
Phát hiện user login/logout/account switch
  → tạm ngăn các mutation mới của session cũ
  → hoàn tất state transition
  → xóa token cache và stale user state
  → xác minh principal hiện tại
  → GET /csrf cho ngữ cảnh mới
  → cho phép mutation tiếp theo
~~~

Đây là nguyên tắc điều phối client, không phải một API Spring Security tên “barrier”. Nó giúp tránh race conditions nhưng backend vẫn phải bảo vệ session/quyền cho mọi request.

### 8.5. Lỗi mạng sau logout không đồng nghĩa logout thất bại

Một request logout có thể đã chạy thành công ở server nhưng response bị proxy/CORS chặn đọc hoặc mạng mất kết nối. Frontend không nên tuyên bố “chắc chắn còn đăng nhập” chỉ vì fetch throw. Có thể thử **GET /api/me** bằng cookies hiện tại để xác minh trạng thái, hoặc hiển thị trạng thái chưa xác định khi offline.

Tương tự, **không tự động thực hiện lại POST tạo đơn/chuyển tiền** chỉ vì CORS error sau khi login thay đổi. CSRF token refresh giải quyết lỗi token, không phải cơ chế bảo đảm idempotency nghiệp vụ.

## 9. SPA đọc cookie CSRF: khác token trả JSON

Một lựa chọn khác là cho SPA đọc cookie **XSRF-TOKEN** và gửi nó trong header **X-XSRF-TOKEN**, thường gặp khi frontend framework có tính năng hỗ trợ XSRF cookie.

### 9.1. Cấu hình cookie repository

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

// Đoạn bên trong HttpSecurity configuration:
http.csrf(csrf -> csrf
        .csrfTokenRepository(
                CookieCsrfTokenRepository.withHttpOnlyFalse()));
~~~

Đoạn trên cho JavaScript **đọc CSRF cookie**, không phải session cookie. **Không dùng withHttpOnlyFalse cho session cookie chứa ID**. Browser cookie scope vẫn phải hợp lệ, đặc biệt nếu frontend ở app.example.com nhưng API đặt host-only cookie trên api.example.com.

### 9.2. Vấn đề XOR masking với header lấy từ cookie

Spring Security 6 có thể dùng mặc định **XorCsrfTokenRequestAttributeHandler**. Trong khi cookie chứa raw token, một handler mặc định có thể chờ masked token được gửi từ form. Nếu SPA chỉ sao chép raw cookie token vào header mà không cấu hình handler phù hợp, request có thể bị CSRF 403.

Một pattern được tài liệu Spring Security mô tả là:

- Duy trì **XOR masking** cho token đặt vào request attribute/form để giảm rủi ro BREACH.
- Dùng **CsrfTokenRequestAttributeHandler** giải quyết raw token lấy từ header của SPA.
- Chủ động **load deferred token** để cookie được sinh lại sau khi token cũ đã bị xóa, thay vì chờ một form HTML dùng token.
- Sau login/logout, đảm bảo trình duyệt nhận **cookie token mới** qua một request phù hợp.

### 9.3. Ví dụ CsrfTokenRequestHandler cho SPA Servlet

~~~java
import java.util.function.Supplier;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;

final class SpaCsrfTokenRequestHandler implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plain =
            new CsrfTokenRequestAttributeHandler();

    private final CsrfTokenRequestHandler xor =
            new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            Supplier<CsrfToken> deferredCsrfToken) {

        // Giữ masked token trong request attribute cho HTML form.
        xor.handle(request, response, deferredCsrfToken);

        // Buộc deferred token được tải/khởi tạo khi cần phát cookie.
        deferredCsrfToken.get();
    }

    @Override
    public String resolveCsrfTokenValue(
            HttpServletRequest request,
            CsrfToken csrfToken) {

        String headerValue =
                request.getHeader(csrfToken.getHeaderName());

        // SPA gửi raw token trong header; HTML form dùng masked value.
        return (StringUtils.hasText(headerValue) ? plain : xor)
                .resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

Tích hợp handler với CookieCsrfTokenRepository:

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

// Đoạn trong cấu hình HttpSecurity:
http.csrf(csrf -> csrf
        .csrfTokenRepository(
                CookieCsrfTokenRepository.withHttpOnlyFalse())
        .csrfTokenRequestHandler(
                new SpaCsrfTokenRequestHandler()));
~~~

**Điều kiện áp dụng:** Ví dụ được xây dựng theo mô hình API của Spring Security 6.x; cần đối chiếu phiên bản cụ thể và kiểm thử đầy đủ trước khi dùng production. Việc buộc load token **trước authentication** không có nghĩa response login **luôn tự đặt cookie CSRF mới sau khi strategy xóa token**. SPA vẫn cần một request tiếp theo (ví dụ GET /csrf hoặc GET tài nguyên phù hợp) để token mới được phát/đọc sau khi trạng thái authentication thay đổi.

### 9.4. So sánh hai chiến lược SPA

| Tiêu chí | GET /csrf trả JSON | Cookie XSRF-TOKEN có thể đọc |
| --- | --- | --- |
| **CSRF cookie phải đọc được bằng JS?** | Không bắt buộc; có thể dùng session repository. | Có, nếu frontend đọc cookie trực tiếp. |
| **Giao tiếp lấy token** | Fetch tới endpoint cấp token được bảo vệ bằng policy. | Frontend đọc cookie sau response tạo/làm mới token. |
| **Khác origin nhưng cùng site** | Có thể cấu hình credentialed CORS và JSON response. | Cần xem kỹ cookie Domain/host vì JS chỉ đọc cookie đủ scope của document. |
| **Tương tác XOR masking** | Header dùng token theo response handler hiện hành. | Thường cần phân biệt raw header với masked form token. |
| **Sau login/logout** | Explicit GET /csrf để lấy token mới. | Cần bảo đảm cookie mới được phát sau khi token cũ bị xóa. |
| **Rủi ro XSS** | JS trong origin hợp lệ có thể đọc response token. | JS trong origin có quyền đọc cookie CSRF. |
| **Session cookie** | Nên giữ HttpOnly, Secure. | Vẫn phải giữ HttpOnly, Secure; CSRF cookie là giá trị riêng. |

Không có lựa chọn nào tự ngăn script XSS trong origin đáng tin sử dụng token. Cần **output encoding, CSP và kiểm soát script** cùng authorization server-side.

## 10. WebFlux/Reactive: làm mới CSRF token với WebSession

Spring Security WebFlux giữ cùng mục tiêu phòng vệ browser, nhưng sử dụng **ServerHttpSecurity**, **SecurityWebFilterChain**, **WebSession**, **ServerCsrfTokenRepository** và API Reactive.

### 10.1. Cấu hình SecurityWebFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ReactiveCsrfLifecycleSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/csrf", "/assets/**").permitAll()
                        .anyExchange().authenticated())
                .formLogin(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .logout(Customizer.withDefaults())
                .build();
    }
}
~~~

Điểm cốt lõi:

- **POST /login** và **POST /logout** dùng WebSession/cookie cần được bảo vệ bằng CSRF token.
- Endpoint **GET /csrf** phải cho browser anonymous gọi để nhận token trước login, và authenticated gọi để làm mới token sau login.
- WebFlux không dùng **HttpServletRequest, HttpSessionCsrfTokenRepository** hoặc SecurityFilterChain của Servlet.
- Cấu hình trên minh họa form login mặc định. SPA cần quy ước response login/logout phù hợp thay vì giả định fetch tự chuyển trang theo redirect.
- Nếu ứng dụng có nhiều security chains, cần xem matcher/ordering để không tạo một endpoint phụ vô tình tắt CSRF.

### 10.2. Lấy Mono<CsrfToken> từ ServerWebExchange

Trong WebFlux, Spring Security có thể đặt **Mono<CsrfToken>** trong attributes của ServerWebExchange. Một controller minh họa việc trả token đã resolve:

~~~java
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
class ReactiveCsrfTokenController {

    @GetMapping("/csrf")
    Mono<ResponseEntity<Map<String, String>>> csrf(
            ServerWebExchange exchange) {

        Mono<CsrfToken> csrfToken =
                exchange.getAttribute(CsrfToken.class.getName());

        if (csrfToken == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF token attribute is unavailable"));
        }

        return csrfToken.map(token ->
                ResponseEntity.ok()
                        .cacheControl(CacheControl.noStore())
                        .body(Map.of(
                                "headerName", token.getHeaderName(),
                                "parameterName", token.getParameterName(),
                                "token", token.getToken())));
    }
}
~~~

Đây là ví dụ cho **Spring Security WebFlux khi CSRF token được đặt ở ServerWebExchange attribute** theo cơ chế tương ứng. Nếu ứng dụng có custom request handler, security filter chain hoặc cách render form khác, cần đối chiếu attribute/token publisher thực tế. Không cố block Mono bằng **block()** trong reactive HTTP request path.

Việc **subscribe/resolve token publisher** là điểm quan trọng: chỉ giữ một Mono trong model mà không render/subscribe thì chưa chắc repository đã tạo/lưu token mới.

### 10.3. WebSession và CSRF token có vòng đời liên quan nhưng không đồng nhất

Trong mô hình WebFlux stateful:

~~~text
Anonymous WebSession / CSRF context
   → Token T0

Authentication thành công
   → SecurityContext/WebSession được cập nhật
   → CSRF token cũ được dọn theo cơ chế cấu hình

GET /csrf ở authenticated phase
   → Token T1 được materialize

Logout thành công
   → SecurityContext / CSRF token được dọn
   → WebSession có được invalidate toàn bộ hay không
      phụ thuộc logout handlers/session policy

GET /csrf ở anonymous phase mới
   → Token T2
~~~

Với WebFlux, cần xác nhận **WebSession có thật sự bị invalidate** nếu yêu cầu nghiệp vụ là xóa toàn bộ dữ liệu session. Việc xóa SecurityContext và CSRF token không nhất thiết chứng minh mọi dữ liệu WebSession tùy chỉnh đã bị dọn.

Khi muốn chủ động invalidate WebSession, Spring Security WebFlux có **WebSessionServerLogoutHandler** có thể kết hợp với **SecurityContextServerLogoutHandler**. Nếu thay thế logout handler mặc định, phải đảm bảo việc dọn CSRF repository/credential khác vẫn được giữ theo thiết kế.

### 10.4. Cookie ID của WebSession trên HTTPS

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration
class ReactiveSessionCookieConfig {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
                new CookieWebSessionIdResolver();

        resolver.setCookieName("__Host-APPSESSION");
        resolver.addCookieInitializer(cookie -> cookie
                .path("/")
                .secure(true)
                .httpOnly(true)
                .sameSite("Lax"));

        return resolver;
    }
}
~~~

Tiền tố **__Host-** yêu cầu Secure, Path=/ và không có Domain. Đây là cookie WebSession **trên HTTPS**, không phải thuộc tính **server.servlet.session.*** của Servlet. Nếu Spring Session Reactive hoặc ứng dụng đã có WebSessionIdResolver, tránh khai báo bean mâu thuẫn.

### 10.5. Kiểm tra form React/Thymeleaf với token publisher

Nếu WebFlux server-rendered page hiển thị form POST, cần chắc chắn token reactive đã được resolve để **hidden _csrf input** chứa giá trị hợp lệ. Một form hiển thị placeholder không đủ:

~~~html
<form method="post" action="/logout">
  <input name="_csrf" type="hidden"
         value="TOKEN_THUC_DUOC_RENDER_TU_REACTIVE_REPOSITORY">
  <button type="submit">Đăng xuất</button>
</form>
~~~

Nếu frontend hoàn toàn là SPA, dùng GET /csrf trả JSON như mục 10.2 và giữ token trong memory state theo cùng nguyên tắc Servlet.

### 10.6. Reactive client và pipeline bất đồng bộ

Không gọi GET /csrf rồi lập tức phát POST dựa trên token cũ trước khi kết quả GET hoàn tất. Trong frontend, cần **await**:

~~~javascript
const newCsrf = await fetchCsrfForCurrentSession();
await performMutationWithCsrf(newCsrf);
~~~

**fetchCsrfForCurrentSession** và **performMutationWithCsrf** là hàm ứng dụng, không phải API dựng sẵn. Trên backend, reactive filters và WebSession store có thể có quá trình lưu bất đồng bộ; test cần đợi response hoàn tất và tái sử dụng cookie jar đúng trước khi request tiếp theo.

Không giải quyết race condition bằng cách tắt CSRF hoặc bỏ kiểm tra session.

## 11. CORS và cookie khi SPA frontend khác origin

Một lỗi “CSRF token không mới” thực tế có thể là **browser không gửi cookie phiên mới** hoặc không đọc được GET /csrf response vì CORS.

Giả sử:

~~~text
Frontend HTML: https://app.example.com
API/session:   https://api.example.com
Attacker site: https://outside.test
~~~

**app.example.com** và **api.example.com** thường là **same-site nhưng cross-origin**. Dù SameSite=Lax cho cookie được gửi trong một số ngữ cảnh same-site, Fetch API mặc định **credentials: same-origin** nên frontend cần **credentials: include** cho cookie API cross-origin.

### 11.1. Cấu hình CORS Servlet

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletSpaCorsConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(
                List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/csrf", cors);
        source.registerCorsConfiguration("/login", cors);
        source.registerCorsConfiguration("/logout", cors);
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Trong Servlet SecurityFilterChain cần tích hợp CORS tương ứng:

~~~java
// Bổ sung vào HttpSecurity khi dùng CORS source ở trên:
http.cors(Customizer.withDefaults());
~~~

Đây là phần CORS **tách riêng cho ứng dụng dùng session**; không tạo hai bean cùng type với chính sách mâu thuẫn. Cấu hình đường dẫn **/csrf, /login, /logout** đặc biệt quan trọng vì token cần lấy trước login, sau login và sau logout.

### 11.2. CORS Reactive/WebFlux

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveSpaCorsConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(
                List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/csrf", cors);
        source.registerCorsConfiguration("/login", cors);
        source.registerCorsConfiguration("/logout", cors);
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Trong WebFlux SecurityWebFilterChain tích hợp:

~~~java
// Bên trong cấu hình ServerHttpSecurity tương ứng:
http.cors(cors -> cors.configurationSource(corsConfigurationSource()));
~~~

**Không dùng Servlet UrlBasedCorsConfigurationSource với WebFlux**. Ở cả hai stack, chỉ cấp quyền cho origin được duyệt; không trả **Access-Control-Allow-Origin: *** kết hợp **Access-Control-Allow-Credentials: true** cho credentialed response.

### 11.3. Preflight không phải CSRF token refresh

Một POST có custom header:

~~~http
POST /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Cookie: __Host-APPSESSION=opaque
X-CSRF-TOKEN: csrf-value
Content-Type: application/json
~~~

thường được browser kiểm tra preflight:

~~~http
OPTIONS /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

**OPTIONS preflight thường không mang cookie session** và **không có tác dụng làm mới CSRF token**. Nó chỉ hỏi browser có được tiếp tục request cross-origin hay không theo CORS. POST thực vẫn phải dùng token mới hợp lệ và qua authentication/authorization.

Đừng mở mọi endpoint **permitAll** chỉ vì OPTIONS bị 401. CORS phải được xử lý trước filter có thể từ chối preflight do thiếu cookie.

### 11.4. Phân biệt ba loại lỗi sau login

| Hiện tượng | Lớp nghi ngờ | Cách xác minh |
| --- | --- | --- |
| **GET /csrf trả 401** | Endpoint token bị yêu cầu authenticated hoặc session đã hết. | Cho anonymous đúng endpoint theo policy, xem SecurityFilterChain. |
| **GET /csrf không đọc được response** | CORS actual response, credentials, redirect hoặc CSP connect-src. | DevTools Network/Console, headers trên GET thực. |
| **GET /csrf thành công, POST 403** | Token cũ, cookie sai session, request handler, authorization. | So token/header theo repository, logs và principal. |
| **OPTIONS 403, POST không xuất hiện** | Preflight CORS/gateway/auth filter. | Cấu hình CORS path/method/header, thứ tự filters. |
| **POST đã chạy nhưng JS báo CORS** | Actual response thiếu CORS hoặc redirect sang origin khác. | Kiểm tra server state trước khi retry mutation. |
| **Token không tồn tại trong cookie sau login** | Deferred token chưa được load hoặc cookie bị xóa/không được lưu. | Gọi GET /csrf và xem Set-Cookie, cookie blocked reasons. |

### 11.5. CSP của frontend có thể chặn fetch /csrf

Nếu document HTML frontend có CSP:

~~~http
Content-Security-Policy: default-src 'self'; connect-src 'self'
~~~

thì fetch tới **https://api.example.com** có thể bị **connect-src** chặn trước khi gửi request. Khi đó không có phản hồi HTTP /csrf hợp lệ cho frontend, và lỗi không thuộc CSRF repository.

Cần cấu hình CSP tại **origin phục vụ HTML frontend**:

~~~http
Content-Security-Policy: default-src 'self'; connect-src 'self' https://api.example.com; script-src 'self'; object-src 'none'; base-uri 'self'
~~~

Đây chỉ là ví dụ cần tinh chỉnh theo tài nguyên hợp lệ. **CSP đặt trên response JSON của API** không tự áp dụng lên document ở host khác.

## 12. Nhiều tab, account switch và stale CSRF token

Mỗi tab có state JavaScript riêng, nhưng trong cùng browser profile thường chia sẻ cookie jar. Đây là nguồn race condition:

~~~text
Tab A: user đang authenticated, giữ token T1
Tab B: cùng browser thực hiện POST /logout với T1
Server: session/auth/token T1 bị dọn
Tab A: vẫn hiển thị UI và giữ T1 trong memory
Tab A: POST /api/orders với T1
      → phải bị từ chối nếu session/token cũ đã vô hiệu
~~~

Sau đó Tab B đăng nhập lại bằng tài khoản khác, token mới có thể được cấp. Nếu Tab A vẫn tin danh tính/CSRF token cũ, UI có thể hiển thị **tài khoản trước** trong khi request mới sử dụng **session hiện tại**.

### 12.1. Biện pháp frontend

- Không lưu token CSRF lâu dài trong localStorage theo kiểu “dùng mãi”.
- Sau login/logout/account switch, phát tín hiệu **auth state changed** cho các tab liên quan.
- Khi nhận tín hiệu, **xóa token cache và user state cũ**; tab lấy lại principal và CSRF token từ server khi cần.
- Khi tab được focus/visibilitychange hoặc sau long idle, revalidate session nếu sản phẩm yêu cầu.
- Không gửi token của account này tới account khác; token không phải định danh account, nhưng gắn với một **vòng đời phiên/auth state**.
- Trong lúc đang chuyển state, tạm khóa các mutation mới để tránh request cùng token cũ.
- Backend vẫn kiểm tra principal/quyền; BroadcastChannel không phải một security boundary.

Ví dụ:

~~~javascript
const authChannel = new BroadcastChannel("auth-state");

function notifyAuthChanged() {
  authChannel.postMessage({ type: "AUTH_CHANGED" });
}

authChannel.addEventListener("message", (event) => {
  if (event.data?.type !== "AUTH_CHANGED") return;

  csrf = null;               // State ứng dụng.
  currentUser = null;        // State ứng dụng.
  scheduleAuthRevalidation(); // Hàm ứng dụng tự triển khai.
});
~~~

BroadcastChannel chỉ liên lạc giữa các ngữ cảnh có điều kiện phù hợp, chủ yếu cùng origin; nó không chia sẻ tùy ý giữa **app.example.com** và **api.example.com**. Một tab bị treo hoặc offline có thể không nhận message. **Không broadcast CSRF token cho mọi tab nếu chỉ cần thông báo invalidation.**

### 12.2. Account switch phải xác định thay đổi authentication thật

Một ứng dụng có thể hỗ trợ chọn tenant/workspace mà **không đổi Authentication**, hoặc login sang user khác và **thay principal thực**. Hai trường hợp này có vòng đời khác nhau:

- **Đổi workspace**: token CSRF không nhất thiết phải rotate, nhưng server vẫn phải kiểm tra quyền của principal với workspace mới.
- **Đổi principal/authentication context**: có thể kích hoạt CSRF cleanup/session rotation; frontend nên lấy token mới.
- **Đăng nhập bằng OAuth2/OIDC qua redirect**: cần ràng buộc state và làm mới token theo session mới sau callback thành công.
- **Remember-me auto-login**: có thể thiết lập Authentication mà không qua POST /login như form thường; kiểm tra lifecycle thực và tính hợp lệ CSRF sau đó.
- **Refresh access token trong API stateless**: không đồng nghĩa đổi HttpSession hoặc CsrfTokenRepository. Không tự rotate CSRF token nếu kiến trúc không dùng nó.
- **Admin impersonation/switch user**: đây là thao tác có rủi ro cao; cần authorization, audit và ràng buộc CSRF/session phù hợp.

Đừng tự động xoay token mỗi khi một thuộc tính UI đổi, nhưng cũng đừng để một **authentication transition thật** vượt qua quy trình token cleanup.

### 12.3. 403 không được tự động retry mutation mù quáng

Giả sử POST /payments trả 403. Frontend **không được mặc định** rằng đây chỉ là token CSRF cũ rồi tự lấy token mới và gửi lại giao dịch không giới hạn.

Cần:

1. Phân loại lỗi từ server: CSRF, authorization, session expired hay validation.
2. Xác minh principal/session hiện tại.
3. Chỉ làm mới token khi có căn cứ phù hợp.
4. Với mutation nhạy cảm, có thể yêu cầu **người dùng xác nhận lại** nếu auth state đã thay đổi.
5. Sử dụng **idempotency key**/kiểm tra trạng thái với giao dịch có thể xử lý lặp.
6. Không retry nếu chưa biết server đã thực hiện request trước đó hay chưa, nhất là khi lỗi là network/CORS chứ không phải CSRF 403 được xác nhận.

### 12.4. Session cookie còn không bảo đảm token còn

Một cookie session có thể vẫn hiện trong DevTools sau login/logout, nhưng server session đã rotate hoặc invalidate; ngược lại, token CSRF cookie có thể bị xóa trong khi authentication cookie mới vừa được cấp.

Chẩn đoán cần xem **cả Cookie/Set-Cookie, session repository, response GET /csrf và principal hiện tại**, không chỉ một cookie name.

## 13. Kiểm thử vòng đời CSRF token qua từng chuyển đổi authentication

Các test cần chứng minh **hành vi của server**, không chỉ một status 200/403. Ưu tiên những luồng có cookie/session được tái sử dụng giữa các request, vì token repository thường liên quan đến phiên hiện tại.

### 13.1. Ma trận kiểm thử tối thiểu

| Bước | Trạng thái trước request | Request | Hành vi cần xác minh |
| --- | --- | --- | --- |
| 1 | Anonymous | GET /csrf | Nhận token T0 được server cấp cho context hiện tại. |
| 2 | Anonymous | POST /login thiếu token | Bị từ chối bởi CSRF; không tạo authenticated principal. |
| 3 | Anonymous | POST /login với token T0, mật khẩu sai | Không xác thực user; phản hồi lỗi theo hợp đồng. |
| 4 | Anonymous | POST /login với T0, mật khẩu đúng | Authenticated session được tạo; old token cleanup theo cấu hình. |
| 5 | Authenticated | POST /api/profile với T0 cũ | Bị CSRF từ chối nếu T0 đã bị thu hồi theo policy. |
| 6 | Authenticated | GET /csrf | Nhận token T1 phù hợp session/auth phase hiện tại. |
| 7 | Authenticated | POST /api/profile với T1 và user đủ quyền | Vượt CSRF; controller xử lý request hợp lệ. |
| 8 | Authenticated | POST /api/profile với T1 nhưng user không đủ quyền | Bị authorization từ chối, dù CSRF đúng. |
| 9 | Authenticated | POST /logout với T1 | Logout hợp lệ; session/security context/token được dọn. |
| 10 | Anonymous sau logout | POST /login dùng lại T1 | Bị từ chối nếu token T1 của phase cũ đã bị xóa. |
| 11 | Anonymous sau logout | GET /csrf | Nhận T2 cho phase mới. |
| 12 | Anonymous | POST /login với T2, credential hợp lệ | Đăng nhập lại bình thường. |

Lưu ý không khẳng định mọi token phải có byte khác nhau nếu **XOR masking** đang bật. Trong các bước 5 và 10, test phải kiểm tra **server từ chối token cũ trong đúng session/context sau chuyển đổi**, không chỉ so String.

### 13.2. MockMvc: kiểm tra đúng/sai CSRF trên Servlet

Với **spring-security-test**, có thể kiểm tra một POST unsafe:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfBasicMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/profile")
                .with(user("learner"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Test\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/profile")
                .with(user("learner"))
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Test\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfCanReachController() throws Exception {
        mvc.perform(post("/api/profile")
                .with(user("learner"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Test\"}"))
            .andExpect(status().isNoContent());
    }
}
~~~

**Giả định:** Endpoint POST /api/profile tồn tại, user test có quyền, controller trả **204** cho dữ liệu hợp lệ. Trong ứng dụng khác, expected status phải đổi theo hợp đồng. Test này chỉ chứng minh có **CSRF protection** và cho request hợp lệ đi tiếp; nó **chưa kiểm chứng T0 được xóa sau login**.

Lý do là **with(csrf())** là tiện ích của spring-security-test để mô phỏng request có token hợp lệ. Nó không tự xây dựng một hành trình browser thật với session cookie, login và rotation.

### 13.3. MockMvc: kiểm thử thực sự chuyển từ T0 sang T1

Với repository dựa trên **HttpSession**, một bài test có thể giữ cùng **MockHttpSession** qua các request. Đoạn minh họa:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpSession;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfRotationFlowMvcTest {

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;

    private String tokenFrom(MvcResult result) throws Exception {
        return json.readTree(
                result.getResponse().getContentAsString())
                .path("token").asText();
    }

    @Test
    void tokenBeforeLoginMustNotAuthorizePostAfterLogin()
            throws Exception {

        // GET tạo token cho anonymous session.
        MvcResult before = mvc.perform(get("/csrf"))
                .andExpect(status().isOk())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) before.getRequest().getSession(false);
        String t0 = tokenFrom(before);

        // Cần test user "learner" tồn tại trong UserDetailsService.
        MvcResult login = mvc.perform(post("/login")
                .session(session)
                .header("X-CSRF-TOKEN", t0)
                .param("username", "learner")
                .param("password", "test-secret"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        // Session hiện tại sau login (có thể đổi ID).
        MockHttpSession loggedInSession =
                (MockHttpSession) login.getRequest().getSession(false);

        mvc.perform(post("/api/profile")
                .session(loggedInSession)
                .header("X-CSRF-TOKEN", t0)
                .contentType("application/json")
                .content("{\"displayName\":\"After login\"}"))
            .andExpect(status().isForbidden());

        MvcResult after = mvc.perform(get("/csrf")
                .session(loggedInSession))
            .andExpect(status().isOk())
            .andReturn();
        String t1 = tokenFrom(after);

        mvc.perform(post("/api/profile")
                .session(loggedInSession)
                .header("X-CSRF-TOKEN", t1)
                .contentType("application/json")
                .content("{\"displayName\":\"After login\"}"))
            .andExpect(status().isNoContent());
    }
}
~~~

**Điều kiện quan trọng của ví dụ**:

- Cần có **UserDetailsService/AuthenticationProvider test** cho learner/test-secret và formLogin success handler **redirect**. Nếu SPA handler trả 204, sửa assertion.
- Cần endpoint **GET /csrf** như mục 7.2 và **POST /api/profile** trả 204 khi hợp lệ.
- Ví dụ dựa trên **HttpSessionCsrfTokenRepository** và MockMvc; nếu dùng CookieCsrfTokenRepository, cần giữ **cookie jar** và xử lý Set-Cookie phù hợp thay vì chỉ MockHttpSession.
- Khi dùng session fixation strategy khác (invalidate/migrateSession), cách truy xuất session sau login có thể phải điều chỉnh.
- Không in session ID/token thật trong log; đoạn code chỉ lưu token trong biến của test.
- Với các hệ thống proxy/session store bên ngoài, cần test bổ sung qua HTTP/browser thật để kiểm tra cookie và lưu trạng thái.

Nếu bạn không có một endpoint /csrf, có thể viết integration test bằng cách parse hidden token từ form HTML hoặc dùng CSRF repository test helper theo thiết kế. Cốt lõi vẫn là **một browser/session xuyên qua nhiều request**, không tự chế một token từ phía client.

### 13.4. Test logout rồi lấy T2

Sau login và khi đã có T1, luồng tiếp theo có thể được kiểm thử:

~~~java
// Pseudocode cho integration test có session/cookie được giữ đúng.
POST("/logout", session, csrf = T1)
  -> expect successful logout;
GET("/api/me", oldSession)
  -> expect not authenticated;
GET("/csrf", currentBrowserCookieJar)
  -> obtain T2;
POST("/login", currentBrowserCookieJar, csrf = T2, validCredentials)
  -> expect authenticated;
~~~

Đây **không phải cú pháp Java có thể biên dịch**, mà là mô tả luồng để triển khai trong test harness. Trong hệ thống nhiều instance, nên chạy thêm test qua proxy và session repository chung để xem token sau logout có được lưu/tạo đúng ở instance mới.

### 13.5. WebTestClient: kiểm tra CSRF filter trên WebFlux

Với spring-security-test WebFlux, có thể dùng **mockUser** và **csrf()**:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

// Đoạn bên trong test; webTestClient đã bind vào app.
webTestClient
    .mutateWith(mockUser("learner"))
    .post().uri("/api/profile")
    .exchange()
    .expectStatus().isForbidden();

webTestClient
    .mutateWith(mockUser("learner"))
    .mutateWith(csrf())
    .post().uri("/api/profile")
    .exchange()
    .expectStatus().isNoContent();
~~~

Ví dụ giả định endpoint và quyền user test phù hợp; assertion status tùy ứng dụng. Nó **không** chứng minh token trước/sau login thực sự được xoay trong WebSession. Để kiểm tra lifecycle Reactive cần test **GET /csrf → POST /login → GET /csrf → POST nghiệp vụ → POST /logout → GET /csrf**, giữ cookie/session qua HTTP requests, và đối chiếu trạng thái WebSession repository.

### 13.6. Test browser end-to-end: đừng chỉ dùng mock request

Một kịch bản browser thật có thể thực hiện:

1. Mở login page trong profile test sạch.
2. Quan sát GET /csrf hoặc hidden _csrf token trên form.
3. Đăng nhập bằng account test; xem **Set-Cookie** và session ID rotation nếu có.
4. Ngay sau login, thử một POST với **token trước login** trong test harness được phép: phải bị từ chối khi policy dọn token đúng.
5. GET /csrf từ browser hiện tại và dùng token mới cho POST hợp lệ.
6. Logout bằng POST với token hợp lệ.
7. Dùng session cũ gọi API đã bảo vệ: phải bị từ chối.
8. Tải lại trang login/GET /csrf và thử login lại bằng token mới.
9. Mở hai tab, logout ở tab B trong khi tab A giữ CSRF token cũ; kiểm tra request mới ở tab A không lấy được quyền cũ.
10. Thử qua CORS proxy/load balancer nếu frontend và API ở origin khác nhau.

Dùng user test và endpoint không có side effect thật. Với thao tác có thể tạo đơn/thanh toán, dùng dữ liệu giả và **idempotency checks**.

## 14. Chẩn đoán 403 sau khi login/logout

### 14.1. Ma trận triệu chứng và điều tra

| Triệu chứng | Nguyên nhân thường cần kiểm tra | Hướng giải quyết |
| --- | --- | --- |
| Login thành công, POST tiếp theo 403. | CSRF token trước login đã bị xóa; frontend giữ T0. | GET /csrf ở authenticated session, dùng token mới. |
| Logout thành công, login lại 403. | Token T1 của phiên cũ còn trong form/SPA cache. | Xóa cache và lấy T2 từ GET /csrf hoặc trang login mới. |
| Browser nhận Set-Cookie xóa XSRF-TOKEN sau login. | CsrfAuthenticationStrategy dọn token cookie. | Tạo/lấy token mới sau auth change; lưu ý deferred token. |
| XSRF cookie không được ghi lại sau login. | Token deferred chưa được materialize. | GET /csrf hoặc cấu hình handler force-load khi phù hợp. |
| GET /csrf 200 nhưng token string khác mọi lần. | XOR masking theo từng response. | Kiểm tra token có còn hợp lệ, không suy ra raw token đã rotate. |
| GET /csrf 200 nhưng POST gửi raw cookie token bị 403. | Default XOR handler mong đợi masked value. | Pattern SPA CsrfTokenRequestHandler phù hợp repository. |
| GET /csrf 401 trước login. | Endpoint cấp token bị yêu cầu authenticated. | Cho anonymous đúng /csrf, giữ CSRF trên POST /login. |
| POST /login trả 403. | Thiếu token T0 hoặc không cùng anonymous session. | Kiểm tra browser cookie, hidden field/header, repository. |
| POST /logout 403 dù user đang đăng nhập. | T1 thiếu/sai, token bị rotate hoặc cookie không gửi. | Token mới + session hiện tại; xem logs CsrfFilter. |
| OPTIONS preflight 401/403. | CORS bị xử lý sau authentication/gateway. | CORS policy và filter ordering; OPTIONS không phải POST. |
| Browser fetch /csrf báo CORS. | Actual response không cấp CORS với credentials. | CORS allowlist cho /csrf; không dùng wildcard. |
| Browser không gửi cookie API sau login. | credentials: include, Secure/SameSite/Domain/Path, third-party policy. | Network Cookie blocked reasons. |
| POST có CSRF đúng vẫn 403. | Authorization theo resource hoặc security matcher khác. | Xem log authorization, principal, tenant, method. |
| Browser vẫn gửi token cũ ở tab A. | Tab B logout/login, tab A không đồng bộ state. | Auth state notification, revalidate principal/token. |
| MockMvc with(csrf()) luôn pass nhưng SPA thật fail. | Mock csrf() không mô phỏng repository/rotation/cookie thật. | Integration test qua nhiều request với cookie jar. |
| Session được đổi ID nhưng token vẫn cũ. | Custom auth chưa gọi CSRF strategy hoặc repository khác. | Audit authentication/session lifecycle, kiểm tra token cũ có còn được chấp nhận. |
| Sau SSO callback, POST 403. | OIDC login thay đổi session/token mà SPA giữ giá trị cũ. | Revalidate principal và fetch token sau callback. |
| Token mới chỉ hoạt động ở một instance. | Session repository/CSRF repository không chia sẻ hoặc proxy routing sai. | Spring Session, Redis, load balancer/session ID. |
| GET /csrf bị chặn bởi CSP. | HTML frontend connect-src không cho API origin. | Chỉnh CSP trên HTML document theo allowlist. |
| POST bị xử lý nhưng frontend báo lỗi mạng/CORS. | Actual response hoặc redirect bị chặn đọc. | Kiểm tra server state, không retry mutation mù quáng. |
| Custom logout trả 204 nhưng token/session cũ vẫn hợp lệ. | Không gọi Spring logout handlers hoặc repository cleanup. | Tích hợp logout DSL, kiểm thử invalidation. |
| Stateless Bearer API chưa dùng CSRF token. | Không có credential browser tự gắn theo request trong mô hình đó. | Đánh giá threat model trước khi bật/tắt CSRF, xem refresh cookie. |

### 14.2. Thứ tự chẩn đoán có thể thực hiện ngay

1. **Xác định method, URL và security chain**: request đang vào POST /login, POST /logout hay POST nghiệp vụ? Có filter chain khác xử lý không?
2. **Kiểm tra auth state trước và sau request**: principal hiện tại và session có thay đổi?
3. **Xem response login/logout**: session cookie được tạo/rotate/clear hay bị browser từ chối?
4. **Kiểm tra nguồn CSRF token**: hidden field, JSON từ /csrf, cookie XSRF-TOKEN hay client cache?
5. **Xác định repository/handler đang dùng**: HttpSession, cookie, custom, XOR/default/plain handler?
6. **Tìm deferred token**: endpoint/token rendering đã thật sự truy xuất giá trị token mới chưa?
7. **So khớp request unsafe**: header/parameter name, token value, Cookie cùng session, content type?
8. **Phân biệt 403 CSRF và 403 authorization** qua security logs an toàn.
9. **Phân biệt network/CORS/CSP và server**: OPTIONS bị chặn hay POST thực đã tới server?
10. **Kiểm tra nhiều instance/tab** và refresh/remember-me/SSO nếu auth state có thể đổi ngoài ý định.
11. **Chạy test âm tính** token cũ bị từ chối khi cần và token mới được chấp nhận, không chỉ xem giá trị token string có đổi.
12. **Chỉ chỉnh policy sau khi xác định tầng lỗi**; không tắt CSRF toàn site để chữa symptom 403.

### 14.3. DevTools: những trường cần quan sát

Trong **Application → Cookies**, quan sát:

- **Session cookie**: tên, Domain/Path, Secure, HttpOnly, SameSite, Expires/Max-Age.
- **CSRF cookie** nếu dùng: có bị xóa hoặc tạo lại trên login/logout/GET token không?
- Cookie có bị **blocked** vì Secure, SameSite hoặc third-party cookie policy không?
- Browser đã gửi cookie nào trong **request thực**, không chỉ cookie nào còn trong Storage?

Trong **Network**, quan sát:

- GET /csrf trả body/header nào? Có **Cache-Control: no-store** không?
- POST /login có CSRF header/parameter cùng session cookie không?
- POST /api/profile dùng token trước hay sau authentication?
- Có OPTIONS preflight không, nó có bị authentication layer chặn không?
- Response POST thực có **Access-Control-Allow-Origin/Allow-Credentials** phù hợp không?
- Server trả 401/403/302/204 gì? Có redirect đến origin khác làm mất CORS hay session cookie không?

DevTools có thể hiển thị thông tin cookie HttpOnly cho người debug được phép, **không có nghĩa JavaScript thông thường đọc được cookie HttpOnly**.

### 14.4. Dùng curl để kiểm tra CORS, không suy ra browser behavior

Mô phỏng preflight trong môi trường kiểm thử:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Mô phỏng một origin không được phép:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://outside.test" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Origin không được phép không nên được server cấp credentialed CORS access theo policy. Nhưng **curl không thực thi SOP/CORS/SameSite/CSP** như browser, và một HTTP client có thể tự khai Origin hoặc Sec-Fetch-Site. Muốn xác minh request browser có gửi cookie và có đọc được response hay không, phải dùng browser thực.

### 14.5. Proxy, firewall, HSTS và cache

Trong môi trường production:

~~~text
Browser HTTPS
    → Reverse proxy / WAF
    → Spring Security
    → Session / CSRF repository
~~~

Những lỗi thường bị quy nhầm cho CSRF token rotation:

- Proxy chặn OPTIONS /csrf hoặc POST /login khác với app security chain.
- Proxy thay Host/X-Forwarded-Proto, gây redirect từ HTTPS sang HTTP hay cookie Secure sai.
- Session store dùng Redis ở nhiều instance nhưng TTL/namespace không nhất quán.
- Cookie Path/Domain của session và CSRF khác nhau khiến POST gửi thiếu một cookie.
- CSP **connect-src** trên HTML frontend chặn GET /csrf.
- HTTP firewall từ chối một URL/method được mã hóa bất thường trước CsrfFilter.
- Cache/CDN trả token của một session khác vì response token bị cache sai.
- Header **Clear-Site-Data** trên logout dọn storage rộng hơn dự kiến, làm SPA mất cả state cần thiết.

Thiết lập **trusted proxy chain**, host allowlist, TLS/HSTS và cache policy phù hợp. **HSTS không cấp token CSRF mới**, và HTTP firewall không thay xác minh token.

## 15. Bài tập tình huống

### Tình huống A — Login thành công rồi POST bị 403

SPA lấy token T0 trước login, dùng T0 để POST /login thành công, rồi tiếp tục POST /api/profile bằng T0 và bị 403. Có chắc CsrfFilter bị cấu hình sai không?

**Đáp án:** Không. Token cũ có thể đã bị **CsrfAuthenticationStrategy xóa** khi authentication thành công. Frontend phải lấy token mới phù hợp authenticated session, ví dụ GET /csrf, rồi gửi request hợp lệ. Đồng thời kiểm tra security logs để phân biệt CSRF 403 với authorization 403.

### Tình huống B — Login page cần token dù chưa có principal

Ứng dụng chỉ cho người dùng đã đăng nhập gọi GET /csrf. Login page không có token nên POST /login không thể vượt CsrfFilter. Có nên bỏ CSRF trên POST /login?

**Đáp án:** Không. **Login cũng là state transition** và có nguy cơ login CSRF. Cho phép anonymous nhận token qua GET /csrf hoặc render form hợp lệ, nhưng giữ CSRF validation trên POST /login.

### Tình huống C — Server trả 204 nhưng chưa gửi XSRF cookie mới

Sau login thành công server trả 204; cookie CSRF cũ bị xóa, nhưng browser chưa nhận cookie mới. Đây có nhất thiết là lỗi server không sinh token không?

**Đáp án:** Không. **Deferred CSRF token** có thể chưa được materialize trong login success response. Cần request tiếp theo có truy xuất token (ví dụ GET /csrf) hoặc cấu hình SPA request handler phù hợp để tạo lại cookie.

### Tình huống D — Hai lần GET /csrf cho hai token string khác nhau

Một tester gọi GET /csrf hai lần trong cùng session, nhận hai token string khác nhau và kết luận Spring đã rotate raw token sau mỗi GET. Kết luận có chắc không?

**Đáp án:** Không. **XOR masking** có thể làm masked token thay đổi trên mỗi response dù raw token trong repository giữ nguyên. Cần kiểm tra repository behavior hoặc request acceptance, không chỉ so chuỗi.

### Tình huống E — Cookie XSRF-TOKEN có raw value

SPA dùng CookieCsrfTokenRepository và đọc raw XSRF-TOKEN từ document.cookie rồi gắn X-XSRF-TOKEN. Spring Security mặc định dùng XOR handler, POST bị 403. Hướng giải quyết?

**Đáp án:** Dùng **CsrfTokenRequestHandler phù hợp SPA** để phân biệt raw header với masked form token, và bảo đảm deferred token được load khi cần. Không tắt CSRF hoặc nhầm vấn đề với mật khẩu/scope.

### Tình huống F — GET /csrf hoạt động nhưng session cookie không đi cùng POST

GET /csrf thành công từ app.example.com đến api.example.com, nhưng POST /api/profile không có session cookie vì fetch thiếu credentials: include. Token đúng có đủ không?

**Đáp án:** Không. CSRF token không thay authentication/session. Fetch cross-origin cần credentials mode phù hợp; cookie còn phải khớp Secure, Domain/Path, SameSite và policy browser.

### Tình huống G — OPTIONS bị 401

SPA POST JSON có X-CSRF-TOKEN tới API khác origin; OPTIONS preflight không mang cookie và bị 401. Developer muốn tắt CSRF. Đúng không?

**Đáp án:** Không. OPTIONS là **CORS preflight**, thường không có session cookie. CORS phải được xử lý trước filter có thể chặn vì thiếu authentication; POST thực vẫn phải qua CSRF token và quyền.

### Tình huống H — CORS trả 200 nhưng frontend không đọc được token

Server GET /csrf trả 200 với token hợp lệ nhưng actual response thiếu Allow-Origin/Allow-Credentials. Frontend thấy CORS error và nghĩ token chưa được tạo. Kết luận đúng không?

**Đáp án:** Chưa chắc. Token có thể đã được tạo tại server, nhưng JavaScript không được browser cho đọc response. Kiểm tra CORS actual response, cookie và proxy trước khi thay đổi CSRF repository.

### Tình huống I — Token cũ vẫn được chấp nhận sau custom login

Nhóm phát triển tự gọi SecurityContextHolder.setAuthentication rồi trả 200; token T0 trước login vẫn được chấp nhận cho POST sau login. Điều này nói lên rủi ro gì?

**Đáp án:** Custom auth có thể đã **bỏ qua authentication session strategy/CSRF cleanup**. Cần tích hợp đúng SecurityContext persistence, session fixation protection, token lifecycle và test old-token rejection theo chính sách.

### Tình huống J — Chỉ đổi session ID

Server rotate session ID sau login nhưng không chủ động xóa token CSRF của một custom repository. Có thể coi token đã được rotate vì session ID đổi không?

**Đáp án:** Không. Session ID rotation và CSRF token rotation/cleanup là **hai cơ chế khác nhau**. Phải kiểm tra repository và token acceptance thực tế.

### Tình huống K — Logout xong login lại bằng token T1

Người dùng logout bằng POST và T1 hợp lệ; trang SPA giữ T1 rồi gửi POST /login với credential đúng. Server trả 403. Nên làm gì?

**Đáp án:** Token trước logout có thể bị CsrfLogoutHandler xóa. Frontend cần **xóa CSRF cache, GET /csrf sau logout** để nhận token anonymous T2 rồi login lại.

### Tình huống L — POST /logout trả 204 nhưng session cũ vẫn truy cập API

Một controller custom trả 204 và xóa localStorage nhưng không dùng Spring logout handlers. Token cũ vẫn hợp lệ. Có phải endpoint logout đã đúng?

**Đáp án:** Không. Status 204 không chứng minh session/token cleanup. Cần dùng logout DSL hoặc xử lý đầy đủ **SecurityContext, session invalidation, CSRF cleanup và credential stores** theo chính sách.

### Tình huống M — Tab A dùng token cũ sau khi tab B logout

Hai tab cùng browser profile, tab B logout, tab A còn token T1 và UI của user cũ. Khi tab A POST, server phải làm gì?

**Đáp án:** Không được cấp quyền cũ nếu session đã bị invalidated. SPA nên đồng bộ auth state và lấy token/principal mới, nhưng backend phải là ranh giới phân quyền cuối cùng.

### Tình huống N — BroadcastChannel tự chứng minh token hợp lệ?

Tab B gửi BroadcastChannel event kèm token T2 cho tab A, và tab A dùng ngay mà không revalidate session. Có phải thiết kế tối ưu?

**Đáp án:** Không nên mặc định. BroadcastChannel chỉ là **kênh đồng bộ cùng origin**, không bảo đảm token/session hiện tại hoặc tab không bị XSS. Thường chỉ thông báo auth state changed, rồi mỗi tab lấy lại principal/CSRF token từ server.

### Tình huống O — Đổi tenant nhưng không đổi Authentication

User chọn workspace khác nhưng vẫn là cùng principal, session không đổi; SPA tự rotate CSRF token mỗi lần chọn workspace. Điều đó có bắt buộc không?

**Đáp án:** Không. CSRF rotation phụ thuộc authentication/session lifecycle và repository policy. **Đổi tenant là thay đổi quyền/ngữ cảnh nghiệp vụ** cần server kiểm tra, nhưng không đồng nghĩa token CSRF bắt buộc rotate nếu Authentication giữ nguyên.

### Tình huống P — OIDC callback xong token trước redirect bị từ chối

SPA bắt đầu OIDC login, browser redirect qua IdP rồi quay lại; token CSRF từ tab trước redirect không còn hợp lệ. Nên xử lý sao?

**Đáp án:** Sau callback thành công, revalidate principal và **lấy CSRF token mới cho session hiện tại**. OAuth2/OIDC state/PKCE/nonce bảo vệ login flow; chúng không thay token CSRF dùng cho POST nghiệp vụ sau login.

### Tình huống Q — State và CSRF token dùng thay nhau?

Ứng dụng dùng OAuth2 state của authorization callback làm header X-CSRF-TOKEN cho POST /api/profile. Có đúng không?

**Đáp án:** Không. **state** ràng buộc authorization response với request login ban đầu. **CSRF token** phục vụ request unsafe theo CsrfTokenRepository. Chúng có mục đích và vòng đời khác nhau.

### Tình huống R — Raw token trong cookie bị xóa sau login

Frontend đọc XSRF-TOKEN và thấy cookie bị xóa sau login. Developer thêm cookie cũ trở lại bằng document.cookie để không phải gọi GET /csrf. An toàn không?

**Đáp án:** Không. Việc tự phục hồi token cũ có thể phá mục đích cleanup và tạo trạng thái lệch với server. Phải để repository/handler cấp token mới theo luồng đã thiết kế.

### Tình huống S — Cache/CDN lưu response /csrf

Một CDN cache công khai response GET /csrf và phục vụ cùng token response cho nhiều browser. Có phù hợp không?

**Đáp án:** Không. Response CSRF gắn với repository/session/context riêng, không nên được cache công khai. Dùng **Cache-Control: no-store**, kiểm tra proxy/CDN và cookie caching policy.

### Tình huống T — Cookie CSRF HttpOnly=false có nghĩa session cookie cũng phải vậy?

Ứng dụng bật CookieCsrfTokenRepository.withHttpOnlyFalse() để SPA đọc token. Một thành viên đề nghị đặt HttpOnly=false cho session ID cookie để thống nhất. Nên chấp nhận không?

**Đáp án:** Không. **CSRF cookie** và **session cookie** khác vai trò. Session ID là credential xác thực và nên giữ HttpOnly/Secure, còn việc cho JS đọc CSRF cookie phải là một lựa chọn có đánh giá.

### Tình huống U — XSS đọc token mới

Ứng dụng có GET /csrf và cookie HttpOnly cho session. Một script XSS chạy trong document được frontend tin cậy vẫn gọi GET /csrf và gửi POST. Có mâu thuẫn với CSRF protection không?

**Đáp án:** Không. CSRF chủ yếu bảo vệ trước request từ **nguồn ngoài không có quyền đọc token hợp lệ**. Script XSS chạy trong origin có thể sử dụng quyền của trang; cần **output encoding, CSP, kiểm soát script, authorization** và nhiều lớp khác.

### Tình huống V — MockMvc with(csrf()) không phát hiện regression rotation

Mọi test dùng with(csrf()) đều pass, nhưng người dùng thật bị 403 sau login. Cần thêm test gì?

**Đáp án:** Một **integration test qua nhiều request cùng cookie/session**: GET token T0, POST login T0, thử POST cũ T0 phải bị từ chối, GET token T1, POST mới T1 phải vượt CSRF; lặp lại qua logout. Helper with(csrf()) không tự mô phỏng lifecycle này.

### Tình huống W — JWT-only API có cần token này không?

Một API stateless chỉ nhận Bearer token trong Authorization header do client chủ động gắn, không nhận session cookie hoặc credential browser tự gửi. Có bắt buộc GET /csrf mỗi lần refresh access token không?

**Đáp án:** Không nhất thiết. CSRF cần được đánh giá theo **credential có được browser tự gửi** và threat model. Nếu hệ thống có refresh cookie hoặc một endpoint dùng session, nó vẫn có thể cần CSRF riêng. Không tắt CSRF toàn bộ khi chưa phân loại endpoint.

### Tình huống X — Token mới đúng nhưng POST vẫn bị 403

Frontend GET /csrf mới sau login, gửi POST với token đó, nhưng server từ chối vì user không thuộc tenant của tài nguyên. Có phải token refresh thất bại?

**Đáp án:** Không. Token đã có thể vượt CSRF nhưng **authorization** vẫn phải kiểm tra quyền theo user/tenant. Cần xem server log và response contract để phân biệt CSRF 403 với quyền 403.

### Tình huống Y — Spring Session chạy nhiều instance

GET /csrf được phục vụ ở instance A, POST /login ở instance B; token không tìm thấy vì session store cục bộ không chia sẻ. Có nên xóa CSRF middleware?

**Đáp án:** Không. Cần **session repository dùng chung** hoặc routing nhất quán theo thiết kế (ví dụ Spring Session/Redis), xác minh TTL/session ID và cookie. Token lifecycle bị lệch do hạ tầng không phải lý do bỏ CSRF.

### Tình huống Z — Client tự retry POST đặt hàng sau 403

Một SPA nhận 403 và ngay lập tức GET /csrf rồi lặp lại POST tạo đơn không giới hạn. Có an toàn không?

**Đáp án:** Không. 403 có thể do authorization; lỗi network/CORS có thể xảy ra sau khi server đã xử lý request. Phải phân loại lỗi, xác minh principal, chỉ làm mới token có kiểm soát và dùng **idempotency** cho giao dịch có nguy cơ lặp.

## 16. Checklist triển khai và review

### 16.1. Xác định lifecycle thực tế

- [ ] Có sơ đồ **anonymous → login → authenticated → logout → anonymous** và những luồng tương đương như SSO, remember-me, account switch.
- [ ] Biết **đâu là Spring Security authentication transition thật**, đâu chỉ là thay đổi UI/workspace.
- [ ] Biết CSRF token cũ bị xóa bởi **authentication/logout strategies** nào trong phiên bản framework và cấu hình đang dùng.
- [ ] Biết **session ID rotation** có xảy ra hay không, và tách biệt nó khỏi CSRF token cleanup.
- [ ] Với custom authentication filter/controller, xác minh session strategy, context persistence và CSRF lifecycle được chạy.
- [ ] Biết khi nào **deferred token** được load/tạo và ở response nào client thực sự nhận token mới.

### 16.2. Chọn repository và request handler

- [ ] Chọn **HttpSessionCsrfTokenRepository** hoặc **CookieCsrfTokenRepository** dựa trên nhu cầu, không theo thói quen.
- [ ] Nếu SPA dùng endpoint GET /csrf, endpoint cho anonymous truy cập và trả token từ repository hiện hành.
- [ ] GET /csrf có **Cache-Control: no-store**, không làm lộ token qua log, URL hoặc cache chung.
- [ ] Nếu đọc raw cookie bằng JavaScript, cấu hình **CookieCsrfTokenRepository.withHttpOnlyFalse()** chỉ cho CSRF cookie, không phải session ID.
- [ ] Với Spring Security 6/XOR masking, đánh giá request handler cho raw header vs masked form parameter.
- [ ] Không dùng phép so String token trả ở hai GET làm bằng chứng raw token đã rotate.
- [ ] Cookie CSRF/session có scope Host/Domain/Path/Secure/SameSite thích hợp; không mở Domain chỉ để tiện JS ở subdomain khác đọc.

### 16.3. Servlet/Spring MVC

- [ ] POST /login và POST /logout vẫn có CSRF protection theo session-based model.
- [ ] Custom login page có hidden CSRF input được render đúng, không dùng placeholder.
- [ ] Khi form login thành công, request unsafe kế tiếp dùng **token của authenticated session**.
- [ ] Khi logout thành công, frontend không tái sử dụng token của session đã hết hiệu lực.
- [ ] Dùng **logout DSL/LogoutFilter** để giữ các handlers cần thiết thay vì chỉ trả HTTP status.
- [ ] Session cũ bị vô hiệu hóa, token cũ bị xóa và remember-me/refresh token được xử lý theo chính sách.
- [ ] Với nhiều filter chains, đúng chain áp dụng cho /csrf, /login, /logout và API nghiệp vụ.
- [ ] Backend phân quyền tài nguyên bất kể CSRF token đúng.

### 16.4. WebFlux/Reactive

- [ ] Dùng **ServerHttpSecurity/SecurityWebFilterChain**, không trộn Servlet classes.
- [ ] CSRF token **Mono<CsrfToken>** được resolve trước khi render form hoặc trả /csrf response.
- [ ] WebSession/token repository được quản lý theo auth/logout lifecycle và hạ tầng lưu trữ.
- [ ] Khi yêu cầu invalidating toàn WebSession, chọn logout handlers phù hợp; không mặc định chỉ dọn SecurityContext là đủ.
- [ ] Test HTTP request nhiều bước có cookie jar thực thay vì chỉ mockUser()/csrf().
- [ ] Cookie WebSession và CORS được cấu hình đúng cho HTTPS/Reactive frontend.

### 16.5. SPA, CORS và nhiều tab

- [ ] Token lưu trong memory state, được **invalidate** khi login/logout/account switch có thay đổi principal.
- [ ] Frontend fetch **GET /csrf sau auth change** hoặc có cơ chế tương đương đã được kiểm thử.
- [ ] Mỗi POST/PUT/PATCH/DELETE dùng token hợp lệ và cookie/session đúng; không tự tạo token trên browser.
- [ ] CORS allowlist bao gồm **/csrf, /login, /logout và API** nếu cần cross-origin.
- [ ] OPTIONS preflight được xử lý trước authentication nhưng POST thực vẫn qua CsrfFilter.
- [ ] Actual response của /csrf và POST có CORS chính xác; không dùng wildcard Allow-Origin với credentials.
- [ ] CSP **connect-src** của frontend HTML cho phép URL API cần dùng, không mở wildcard vô điều kiện.
- [ ] Nhiều tab được thông báo **auth state changed**, revalidate principal và token, không giả định token cache còn đúng.
- [ ] Auth transition làm tạm ngăn các mutation mới khi cần; không retry giao dịch vô hạn vì 403.
- [ ] Cookie session giữ **HttpOnly, Secure, SameSite** và phạm vi phù hợp, kể cả khi CSRF cookie phải JS-readable.

### 16.6. Các test âm tính cần có trước release

- [ ] POST /login thiếu/sai token bị từ chối trước khi tạo authenticated session.
- [ ] POST /login với token T0 hợp lệ và credential đúng tạo đúng principal.
- [ ] Token T0 **không tiếp tục được chấp nhận** ở authenticated phase nếu policy cleanup yêu cầu.
- [ ] GET /csrf sau login tạo/trả token T1 hợp lệ cho phiên hiện tại.
- [ ] POST nghiệp vụ với T1 và quyền phù hợp thành công; không đủ quyền vẫn bị từ chối.
- [ ] POST /logout với T1 dọn session/token theo chính sách.
- [ ] Token T1 trước logout không được tái sử dụng để login lại khi đã bị thu hồi.
- [ ] GET /csrf sau logout tạo/trả token T2 cho anonymous phase.
- [ ] MockMvc/WebTestClient tests có **session/cookie continuity** bổ sung ngoài with(csrf())/mockUser().
- [ ] Browser thật kiểm tra **Cookie/Set-Cookie, response CORS, deferred token, CSP và multi-tab**.
- [ ] Nhiều instance/load balancer không làm token repository mất đồng bộ.
- [ ] Logs/audit đủ để phân biệt **CSRF failure, authorization failure và lỗi network** mà không lộ secrets.

## 17. Ghi nhớ

1. **CSRF token gắn với vòng đời security context/repository** trong ứng dụng dùng cookie/session; không nên giữ token cũ vô hạn qua login/logout.
2. Trong Spring Security Servlet, **CsrfAuthenticationStrategy** và **CsrfLogoutHandler** giúp dọn token ở những chuyển đổi xác thực tương ứng; với custom auth/logout phải kiểm tra các hooks thực tế.
3. **Session fixation rotation** và **CSRF token cleanup** là hai việc khác nhau. Không suy ra token đã được xoay chỉ vì session ID đổi.
4. **Deferred CSRF token** có nghĩa sau login/logout token cũ bị xóa nhưng **token mới có thể chưa tự xuất hiện** cho đến khi frontend hoặc template thực sự truy xuất nó.
5. **XOR masking để giảm BREACH** có thể khiến token string trả cho browser thay đổi theo mỗi response mà raw repository token không đổi. Hãy kiểm tra tính hợp lệ sau transition thay vì so chuỗi.
6. Với **server-rendered form**, tích hợp template cần tạo hidden CSRF input từ session mới. Với **SPA**, có thể dùng **GET /csrf** và lưu token trong memory state, làm mới sau auth change.
7. Với **CookieCsrfTokenRepository**, CSRF cookie có thể chứa raw token; JavaScript đọc cookie cần handler phù hợp với XOR masking. **Đừng bật HttpOnly=false cho session cookie** chỉ vì CSRF cookie cần được đọc.
8. Với **WebFlux**, dùng **ServerHttpSecurity**, **ServerCsrfTokenRepository** và **WebSession/Mono<CsrfToken>** theo Reactive; không dùng Servlet classes cho Reactive flow.
9. **CORS preflight, SameSite, SOP, CSP và HSTS** không thay CSRF token hoặc server authentication/authorization. Khi frontend/API khác origin, phải kiểm tra cả **cookie, CORS actual response và CSP connect-src**.
10. **Nhiều tab, account switch, OAuth2/OIDC callback và remember-me** có thể đổi authentication ngoài thời điểm frontend kỳ vọng; các tab cần revalidate principal và token.
11. **403 không luôn là CSRF**. Kiểm tra request chain/logs để phân biệt token stale, session expiry, authorization, CORS, CSP và proxy.
12. **Test cốt lõi:** T0 trước login dùng để login; sau login lấy T1; T0 không còn quyền trong phase mới; sau logout lấy T2; token từ phase cũ không tiếp tục được chấp nhận khi đã bị thu hồi.

## Tài liệu tham khảo

Khi triển khai, đối chiếu Spring Security Reference tương ứng **đúng phiên bản** dự án, đặc biệt các mục về SPA, deferred CSRF token và BREACH protection:

- [Spring Security Reference — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security Reference — Servlet Authentication/Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [Spring Security Reference — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security Reference — Reactive Logout](https://docs.spring.io/spring-security/reference/reactive/authentication/logout.html)
- [Spring Security Reference — MockMvc CSRF testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)

**Nguyên tắc kết thúc bài:** Mỗi lần trạng thái xác thực của browser thay đổi, hãy biết **token nào vừa bị thu hồi, token mới được materialize khi nào, browser đã nhận token mới chưa và server vẫn kiểm tra danh tính/quyền nào cho request tiếp theo**.




