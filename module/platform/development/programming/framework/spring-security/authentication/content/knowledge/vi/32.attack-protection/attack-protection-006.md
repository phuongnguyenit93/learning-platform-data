# CSRF ở đăng nhập, đăng xuất và các cơ chế được trình duyệt tự gửi

## 1. Bài toán: trình duyệt có thể gửi quyền của người dùng mà người dùng không hề chủ động

**Cross-Site Request Forgery (CSRF)** là kiểu tấn công trong đó một website/trang không đáng tin cậy khiến **trình duyệt của nạn nhân** gửi request đến một ứng dụng khác. Nếu trình duyệt **tự đính kèm credential** mà ứng dụng đích chấp nhận và request có hành động thay đổi trạng thái, máy chủ có thể tưởng đây là yêu cầu hợp lệ của nạn nhân.

Ví dụ An đã đăng nhập `https://app.example.com` bằng cookie phiên. An mở một trang ngoài do attacker kiểm soát. Trang đó cố tạo một form `POST` tới `https://app.example.com/settings/email`. Nếu browser tự gửi cookie và server không có cơ chế xác minh nguồn/giao dịch, attacker có thể khiến tài khoản An bị thay đổi khi đủ điều kiện gửi cookie. Attacker **không cần đọc cookie hoặc biết mật khẩu** để thử CSRF.

CSRF không chỉ liên quan đến “chuyển tiền” hay cập nhật hồ sơ. Trong ứng dụng Spring Security còn có **login CSRF**, **logout CSRF** và các request dùng credential trình duyệt tự gửi như session cookie, remember-me cookie, một số trường hợp HTTP Basic hoặc xác thực client certificate.

Sau bài học bạn sẽ:
1. Phân biệt CSRF với XSS, CORS và session hijacking.
2. Giải thích tại sao **POST đăng nhập chưa có phiên xác thực vẫn cần bảo vệ CSRF**.
3. Giải thích tại sao **đăng xuất nên dùng POST + CSRF token**, không dùng GET làm thao tác logout.
4. Xác định CSRF theo cơ chế credential có **tự động đi cùng request** hay không, không theo nhãn “REST”, “JWT”, “stateless”.
5. Cấu hình và kiểm thử Spring Security Servlet 6.x với Java 17+, Spring Boot 3.x, `CsrfFilter` và `MockMvc`.
6. Phân biệt **SameSite cookie, CORS, Origin/Referer, Fetch Metadata** với cơ chế synchronizer CSRF token.
7. Xử lý đúng HTML form, JavaScript SPA, browser redirect/SSO, reverse proxy và endpoint chỉ dùng Bearer token thủ công.

**Phạm vi:** ứng dụng **Spring Security Servlet/Spring MVC**. Với WebFlux, cần `ServerHttpSecurity` và reactive CSRF repository/filter, không sao chép trực tiếp `HttpSecurity` hay `SecurityFilterChain` của ví dụ.

## 2. Mô hình tấn công: dữ liệu nào được trình duyệt tự gửi?

Một CSRF điển hình cần các điều kiện:
- Nạn nhân đã có một **quan hệ xác thực/trạng thái** ở trang mục tiêu.
- Trình duyệt gửi một credential dùng được tới trang mục tiêu **mà không cần attacker biết nó**, tùy cookie policy, domain/scheme, request context và cơ chế auth.
- Attacker có thể khởi phát một request thay đổi trạng thái theo một đường cho phép.
- Server không xác minh được request do trang/phiên giao dịch hợp lệ khởi phát, chẳng hạn thiếu CSRF token phù hợp.

Sơ đồ:

~~~text
An đăng nhập app.example.com
    |
    | Browser giữ session cookie
    v
Nạn nhân truy cập trang attacker.example
    |
    | Trang đó tạo form POST đến app.example.com/settings/email
    v
Browser quyết định có gửi cookie kèm request hay không
    |
    | Nếu credential được đính kèm và không có CSRF defense
    v
Server có thể thực hiện cập nhật trái ý An
~~~

**Lưu ý quan trọng:** cookie không phải lúc nào cũng đi cùng cross-site POST. `SameSite=Strict/Lax/None`, browser, loại navigation và thuộc tính cookie quyết định khả năng gửi. Ví dụ chỉ mô tả một lớp tấn công **khi browser thực sự đính kèm credential**. Không suy ra mọi cross-site POST chắc chắn mang cookie.

### 2.1. CSRF không đồng nghĩa với việc attacker đọc response

Kể cả khi Same-Origin Policy/CORS ngăn JavaScript ở trang độc đọc response, attacker vẫn có thể tạo request bằng các cơ chế browser cho phép: HTML form, navigation, một số loại request đơn giản. **Không đọc được kết quả** không đồng nghĩa **không gây được side effect**.

Các trường hợp hay nhầm:

| Khái niệm | Mối nguy chính | Liên hệ với CSRF |
| --- | --- | --- |
| **CSRF** | Dùng ngữ cảnh xác thực tự động của nạn nhân để làm hành động trái ý | Cần defense ở request thay đổi trạng thái |
| **XSS** | Script độc hại chạy trong origin tin cậy, có thể truy cập DOM, gửi request cùng origin | XSS có thể vượt qua nhiều CSRF defense; vẫn phải chống XSS |
| **CORS** | Kiểm soát quyền truy cập cross-origin của JavaScript và preflight | Không tự chặn mọi HTML form/navigation; không thay CSRF |
| **Session hijacking** | Attacker đánh cắp/chiếm session hoặc credential | CSRF có thể không cần đánh cắp session |
| **Clickjacking** | Dụ người dùng thao tác trên UI bị che/phủ | Cơ chế khác; có thể cần CSP `frame-ancestors` |
| **Login CSRF** | Ép browser đăng nhập vào tài khoản attacker kiểm soát | Có thể xảy ra **trước khi user có phiên đăng nhập** |
| **Logout CSRF** | Ép browser kết thúc session trái ý user | Có thể ảnh hưởng workflow/bảo mật dù không đánh cắp dữ liệu |

### 2.2. Minh họa một request giả mạo

Ví dụ HTML sau chỉ minh họa phương thức tấn công (endpoint, hostname và dữ liệu đều là giả):

~~~html
<form action="https://app.example.com/settings/email" method="post">
  <input name="newEmail" value="attacker-controlled@example.test">
  <button type="submit">Submit</button>
</form>
~~~

Một trang khác có thể hiển thị nút này cho người dùng bấm hoặc dùng các cơ chế khác để kích hoạt form. Từ góc độ server, request có thể giống request cập nhật hợp lệ nếu **chỉ kiểm tra cookie** mà không có bằng chứng ý định/nguồn hợp lệ. Một CSRF token mà attacker không biết sẽ làm request thiếu bằng chứng đó và bị chặn.

## 3. Những credential trình duyệt có thể tự gửi

**Quyết định CSRF dựa trên cách credential được gửi**, không dựa trên tên công nghệ.

| Cơ chế | Browser có thể tự gửi vào request không? | Có phải đánh giá CSRF? |
| --- | --- | --- |
| Cookie session như `JSESSIONID` | Có, theo Domain/Path/SameSite/Secure và request context | **Có**, với thao tác thay đổi trạng thái |
| Cookie remember-me | Có, tương tự cookie session | **Có** |
| JWT/opaque token **nằm trong cookie** | Có; định dạng JWT không thay đổi cookie behavior | **Có** |
| HTTP Basic/Digest đã được browser lưu hoặc cache | Có thể, phụ thuộc browser và authentication context | **Có** nếu browser tự đính kèm credential |
| TLS client certificate (mTLS) đã được chọn cho site | Browser/client có thể dùng tự động cho kết nối phù hợp | **Có thể**; cần đánh giá browser request context |
| Access token trong `Authorization: Bearer ...` do client JS chủ động gắn | Browser không tự gắn token đó từ một biến JS ở origin khác | Rủi ro CSRF truyền thống thấp hơn nếu **chỉ** dựa vào header do trusted client gắn |
| API key do backend service chủ động gắn header | Trình duyệt nạn nhân không tự phát API key | Thường không có dạng browser CSRF nếu API chỉ chấp nhận cơ chế này |
| Không có credential, public POST | Không có phiên auth để lạm dụng | Vẫn cần chống abuse, automation, login CSRF và side effects tùy nghiệp vụ |

**Ví dụ dễ nhầm:** “API của tôi dùng JWT nên có thể tắt CSRF.” Nếu JWT được đặt trong `HttpOnly` cookie, browser vẫn tự gửi cookie khi chính sách cho phép. JWT có ký hợp lệ nhưng server không biết người dùng có thực sự muốn đổi địa chỉ giao hàng hay không. **CSRF vẫn là rủi ro.**

Ngược lại, nếu một API **chỉ** chấp nhận Bearer token gửi thủ công qua `Authorization` header từ client được kiểm soát, không nhận cookie/Basic hay cơ chế browser tự gửi, thì có thể đánh giá bỏ CSRF token cho phạm vi API ấy. **Phải kiểm chứng điều kiện này trên toàn bộ filter chain**, không chỉ ở một controller.

## 4. Login CSRF: tại sao POST /login cũng cần token?

CSRF thường được mô tả là tấn công user **đã đăng nhập**. Nhưng **đăng nhập cũng thay đổi trạng thái xác thực** của trình duyệt.

Một kịch bản *login CSRF*:
1. Attacker tạo một account `attacker-account` trong ứng dụng.
2. Attacker chuẩn bị request login có username/password của **account attacker**.
3. Attacker cố khiến browser nạn nhân gửi POST login đó tới ứng dụng.
4. Nếu request được chấp nhận mà không xác minh CSRF, trình duyệt nạn nhân có thể bắt đầu session **dưới tài khoản attacker**.
5. Nạn nhân tưởng đang dùng account của mình, sau đó nhập thông tin cá nhân, tài liệu hoặc giao dịch vào account do attacker kiểm soát; attacker có thể truy cập dữ liệu của chính account đó.

Đây **không** phải tấn công đoán mật khẩu nạn nhân. Mật khẩu được attacker biết là **mật khẩu account attacker**; mục tiêu là ép nạn nhân sử dụng nhầm danh tính.

Hậu quả tùy chức năng ứng dụng, nhưng bài học rõ: **login POST cần được bảo vệ CSRF ngay cả trước khi có `Authentication` của nạn nhân**.

Spring Security Servlet có CSRF protection mặc định cho phương thức unsafe và áp dụng cho `POST /login`. Nếu sử dụng form login mặc định, trang GET `/login` của Spring Security sinh form và chứa CSRF token phù hợp. Nếu bạn dựng **custom login form**, phải render CSRF token đúng vào form hoặc gửi bằng cơ chế được backend chấp nhận.

### 4.1. Token dùng trước khi đăng nhập có thể tồn tại như thế nào?

Trình duyệt có thể chưa authenticated nhưng đã có session vô danh/pre-auth để giữ state của CSRF token, hoặc ứng dụng dùng một CSRF token repository được cấu hình khác. `CsrfTokenRepository` lưu/tra token dự kiến; `CsrfFilter` kiểm tra request.

**Đừng chỉ bật CSRF cho `request.isUserInRole(...)` hoặc các endpoint sau login**. Nếu exempt `POST /login`, bạn bỏ qua lớp bảo vệ quan trọng.

Sau khi login thành công, Spring Security có thể **xóa/luân chuyển CSRF token cũ** theo `CsrfAuthenticationStrategy`. Ứng dụng JS cần lấy token mới trước lần POST tiếp theo. Token trước login không mặc nhiên dùng mãi trong session sau login.

## 5. Logout CSRF: vì sao GET /logout không nên đăng xuất?

Nếu ứng dụng cho phép `GET /logout` thực sự xóa session, một link, ảnh hoặc navigation được trang ngoài khởi phát có thể khiến user bị đăng xuất mà không chủ động chọn thao tác. Điều này có thể làm mất tác vụ chưa lưu, phá luồng ứng dụng hoặc tạo cơ hội nhầm lẫn giữa các bước đăng nhập.

**Thiết kế đúng:** thao tác logout thay đổi trạng thái → dùng **POST** (hoặc phương thức unsafe được thiết kế phù hợp) và yêu cầu CSRF token. Spring Security 6.x khi bật CSRF mặc định:
- `GET /logout` hiển thị **trang xác nhận logout**, không thực sự thực thi logout.
- `POST /logout` với CSRF token hợp lệ mới chạy `LogoutFilter`, invalidate session, clear security context và CSRF token theo cấu hình.
- `POST /logout` thiếu/sai CSRF token bị chặn, thường là HTTP **403**.
- Khi logout thành công, mặc định redirect tới `/login?logout`.

Đối với một trang dùng form HTML:

~~~html
<!-- Mảnh template Thymeleaf trong ứng dụng Spring MVC có tích hợp CSRF. -->
<form th:action="@{/logout}" method="post">
    <button type="submit">Đăng xuất</button>
</form>
~~~

Khi Spring MVC/Thymeleaf integration đúng, `RequestDataValueProcessor` tự thêm trường CSRF token cho form có `th:action` POST. Nếu không dùng tích hợp đó, phải tự render trường có `parameterName` và `token` do server cấp; **không hardcode giá trị token**. Một link thuần `<a href="/logout">` chỉ nên dẫn tới trang confirmation GET, **không** thực hiện logout.

**Cảnh báo:** các ví dụ hướng dẫn tắt CSRF để “GET /logout hoạt động” đang đánh đổi bảo vệ logout chỉ để tiện UI. Hãy giữ POST và token; JavaScript có thể submit hidden form nếu muốn nút/link giao diện.

### 5.1. Đăng xuất ứng dụng và đăng xuất IdP không hoàn toàn giống nhau

Nếu đang dùng OIDC/SAML SSO, cần phân biệt:
- **Local logout:** kết thúc session/cookie của ứng dụng RP/SP.
- **Federated logout:** có thể còn cần thông báo/truyền flow tới authorization server hoặc IdP theo protocol.
- **CSRF bảo vệ local action:** POST logout local vẫn phải yêu cầu bằng chứng hợp lệ theo threat model; giao thức federated có thêm state, return URL, issuer, signature/binding riêng.

Không tự suy luận rằng redirect tới IdP để logout xong thì các thao tác local luôn được bảo vệ CSRF. Đồng thời, các endpoint callback từ IdP theo giao thức có thể có đặc thù xác minh riêng, không được bỏ CSRF hàng loạt cho toàn bộ ứng dụng.

## 6. SameSite: lớp phòng thủ bổ sung, không phải lời giải cho mọi CSRF

Cookie có các thuộc tính liên quan bảo mật:

~~~http
Set-Cookie: JSESSIONID=sample; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

| Thuộc tính | Công dụng chính | Không đảm bảo |
| --- | --- | --- |
| `Secure` | Browser chỉ gửi cookie qua secure transport phù hợp | Không ngăn CSRF khi cookie vẫn được gửi qua HTTPS |
| `HttpOnly` | JavaScript không được đọc cookie trực tiếp | Không ngăn browser **tự gửi cookie** |
| `SameSite=Strict` | Hạn chế cookie trong yêu cầu cross-site | Có thể ảnh hưởng trải nghiệm navigation/SSO |
| `SameSite=Lax` | Thường cho cookie vào top-level navigation bằng safe method; hạn chế các cross-site unsafe requests | GET có side effect vẫn nguy hiểm; same-site subdomain chưa chắc được tin |
| `SameSite=None; Secure` | Cho phép cookie trong cross-site context theo browser policy | Không phải CSRF defense; yêu cầu bảo vệ khác |
| `Path` / `Domain` | Giới hạn phạm vi cookie được trình duyệt gửi | Không thay thế xác thực request origin/CSRF token |

**Same-site không đồng nghĩa same-origin.** Hai origin `https://app.example.com` và `https://blog.example.com` khác hostname nhưng thường cùng site theo registrable domain/scheme. Nếu blog có nội dung do người dùng hoặc bên thứ ba quản lý, `SameSite` có thể không chặn một số yêu cầu từ blog tới app theo cách bạn kỳ vọng. Đánh giá tất cả subdomain có trust level khác nhau.

Không dựa vào `SameSite=Lax` để cho phép một GET thay đổi trạng thái. Theo HTTP semantics, **GET/HEAD/OPTIONS/TRACE phải an toàn**; Spring Security mặc định không buộc CSRF token cho các phương thức safe. Nếu một URL như `GET /delete-account` thực sự xóa tài khoản, bạn đã tạo đường vòng nguy hiểm.

**Các browser có chính sách/phần ngoại lệ lịch sử khác nhau**, nhất là cookie không khai báo SameSite và cách xử lý top-level POST mới tạo. Trong production đặt thuộc tính rõ ràng, test trên browser hỗ trợ và vẫn dùng CSRF token cho session-based unsafe actions.

## 7. Synchronizer token pattern: bằng chứng không được browser tự gửi

CSRF protection trong Spring Security Servlet mặc định thường dựa trên **synchronizer token pattern**:

1. Server tạo giá trị CSRF khó đoán, gắn với ngữ cảnh session và lưu giá trị kỳ vọng qua `HttpSessionCsrfTokenRepository`.
2. Server gửi token tới client tin cậy trong HTML form hoặc phương thức cho phép đọc từ **cùng origin**.
3. Khi client chủ động submit POST/PUT/PATCH/DELETE, form hoặc JavaScript gửi lại token ở **request parameter** hoặc **custom header**, ví dụ `_csrf` / `X-CSRF-TOKEN`.
4. `CsrfFilter` tìm token request và so với token kỳ vọng. Thiếu/sai → chặn **trước khi controller thay đổi dữ liệu**.

Vì browser **không tự trích một hidden form field/JS header hợp lệ từ trang mục tiêu để gắn vào form do attacker tạo**, attacker có thể kích hoạt request nhưng thường **không có CSRF token hợp lệ**. Cookie phiên tự gửi là phần server phải coi là chưa đủ.

Ví dụ form Spring MVC render token từ `CsrfToken`:

~~~html
<form method="post" action="/profile/display-name">
    <label for="name">Tên hiển thị</label>
    <input id="name" type="text" name="value">
    <!-- Các giá trị name/value phải được server render/escape. -->
    <input type="hidden" name="_csrf" value="TOKEN_DO_SERVER_RENDER">
    <button type="submit">Lưu</button>
</form>
~~~

Chuỗi `TOKEN_DO_SERVER_RENDER` chỉ mô tả vị trí template chèn giá trị, **không phải token hợp lệ**. Trong production, lấy `csrfToken.getParameterName()` và `csrfToken.getToken()` từ request/template integration (hoặc để Thymeleaf tự chèn). Tuyệt đối không đặt token trong URL/query string vì log/history/Referer có thể lưu nó.

### 7.1. Default Spring Security 6.x và BREACH/deferred token

Spring Security 6 sử dụng token **deferred loading** và cơ chế che token trên response để giảm rủi ro **BREACH**, nên không nhất thiết mỗi GET đều đọc session/tạo token ngay. Các integration tự viết JS cần hiểu:
- Default repository: `HttpSessionCsrfTokenRepository`.
- `CsrfTokenRequestHandler` quyết định cách đưa/resolving token vào request.
- CSRF token được xóa/đổi sau login/logout; JS phải lấy token mới.
- `CookieCsrfTokenRepository` khác session repository; nếu JS đọc token từ cookie, phải xét cơ chế `XorCsrfTokenRequestAttributeHandler`/plain token và flow refresh token theo đúng Spring Security version.

Không tự đặt một cookie `XSRF-TOKEN` rồi so header bằng chuỗi thủ công và cho rằng đã làm đầy đủ CSRF. Với mô hình stateless, OWASP khuyến nghị **signed double-submit cookie** ràng buộc với session, chống cookie injection, chứ không chỉ so “cookie == header”.

### 7.2. Cookie token không phải cookie session

Trong ứng dụng JavaScript:
- Cookie **xác thực** (ví dụ `JSESSIONID`) nên là `HttpOnly` và `Secure`; server kiểm tra nó để xác định session.
- Một cookie dùng **chuyển CSRF token** cho JS có thể cần JS đọc được (`HttpOnly=false`) nếu theo pattern của SPA; đó là dữ liệu CSRF cần dùng để tạo header, **không** phải cookie auth.
- Khi dùng cookie-to-header, backend phải kiểm tra header/param do client chủ động gửi, không chỉ kiểm tra token cookie **vốn được browser tự gửi**.

Việc để JavaScript đọc CSRF cookie không tương đương với việc để JavaScript đọc session cookie. Tuy nhiên XSS chạy cùng origin vẫn có thể lấy token/khởi phát hành động nên **CSRF token không chữa được XSS**.

## 8. Login, logout và endpoint nghiệp vụ: ma trận quyết định

| Request | Có thay đổi trạng thái? | CSRF với session-cookie auth? | Ghi chú |
| --- | --- | --- | --- |
| `GET /login` | Không, chỉ render form | Không yêu cầu token cho GET | Form trả về chứa token cho POST |
| `POST /login` | Có, tạo authentication/session | **Có** | Chống login CSRF |
| `GET /logout` | Không nên thực sự logout | Không cho GET làm side effect | Spring mặc định hiển thị confirmation |
| `POST /logout` | Có, invalidate session | **Có** | Chống forced logout |
| `GET /profile` | Chỉ đọc | Không theo default matcher | Không được lén update viewedAt/setting có tác động nghiệp vụ quan trọng |
| `POST /profile/display-name` | Có, sửa hồ sơ | **Có** | Cookie auth không đủ |
| `PUT /profile` / `DELETE /resource` | Có | **Có** | Method unsafe |
| `POST /login/webauthn` / đăng ký passkey | Tạo phiên hoặc credential | **Đánh giá và bảo vệ** | WebAuthn ceremony có challenge, session/correlation và chính sách riêng |
| Browser POST đến API nhận cookie JWT | Có | **Có** | JWT ký hợp lệ không thay CSRF |
| API POST chỉ nhận Bearer header do client chủ động set | Có | Có thể miễn **trong phạm vi chỉ Bearer** | Không được chấp nhận cookie/Basic như đường phụ |
| Public POST đăng ký tài khoản | Có | Tùy flow; bảo vệ phù hợp | CSRF, rate limit, anti-automation và email verification là các lớp khác nhau |

Không dựa vào tên `/api/**` để tự miễn CSRF. Một ứng dụng có thể phục vụ `/api/**` bằng cookie session, và vì vậy vẫn cần protection.

## 9. Ví dụ Spring Boot 3.3.x Java 17+: form login + POST logout + cập nhật hồ sơ có CSRF

Ví dụ tập trung vào **quan sát behavior mặc định** của Spring Security. Dùng Java 17+, Spring Boot **3.3.12**, Spring Security Servlet cùng `spring-security-test`. Trình duyệt có thể đăng nhập bằng trang mặc định của Spring Security; endpoint cập nhật profile chỉ được thay đổi qua request có session auth **và CSRF token**.

Để ví dụ tự chứa, hồ sơ được lưu bằng `AtomicReference` cho **một** tài khoản giả lập. Không phải cách lưu dữ liệu nhiều user ở production.

### 9.1. Cấu trúc và Gradle

~~~text
csrf-browser-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/csrf/
    │   ├── CsrfDemoApplication.java
    │   ├── SecurityConfig.java
    │   ├── ProfileStore.java
    │   └── ProfileController.java
    └── test/java/demo/csrf/
        └── CsrfSecurityTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'csrf-browser-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.12'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 9.2. Ứng dụng

`src/main/java/demo/csrf/CsrfDemoApplication.java`:

~~~java
package demo.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfDemoApplication.class, args);
    }
}
~~~

`src/main/java/demo/csrf/ProfileStore.java`:

~~~java
package demo.csrf;

import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Component;

@Component
public class ProfileStore {
    private final AtomicReference<String> displayName =
            new AtomicReference<>("Initial");

    public String get() {
        return displayName.get();
    }

    public void set(String value) {
        displayName.set(value);
    }

    public void reset() {
        displayName.set("Initial");
    }
}
~~~

**Giới hạn lab:** biến toàn cục này chỉ mô phỏng side effect để test. Production phải lưu hồ sơ theo account ID/tenant, authorization và transaction, không cho tất cả user chia sẻ một `displayName`.

`src/main/java/demo/csrf/ProfileController.java`:

~~~java
package demo.csrf;

import java.security.Principal;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ProfileController {
    private final ProfileStore store;

    public ProfileController(ProfileStore store) {
        this.store = store;
    }

    @GetMapping("/profile")
    public Map<String, String> profile(Principal principal) {
        return Map.of(
                "username", principal.getName(),
                "displayName", store.get());
    }

    @PostMapping("/profile/display-name")
    public Map<String, String> changeName(
            @RequestParam String value, Principal principal) {
        if (value.isBlank() || value.length() > 80) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid display name");
        }

        store.set(value);
        return Map.of(
                "username", principal.getName(),
                "displayName", store.get());
    }
}
~~~

Controller **không tự đọc CSRF token**; `CsrfFilter` chặn trước khi request thiếu token tới method `changeName`. Kiểm tra validation/authorization nghiệp vụ vẫn cần làm, ngay cả khi CSRF token hợp lệ.

### 9.3. SecurityFilterChain: giữ CSRF cho login, logout và state changes

`src/main/java/demo/csrf/SecurityConfig.java`:

~~~java
package demo.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("student")
                        .password(encoder.encode("local-test-password-123"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form.permitAll())
                .logout(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
~~~

Đây là cấu hình **có thể biên dịch** trong project ở trên:
- `formLogin()` tạo trang GET `/login` mặc định và xử lý `POST /login`.
- `logout()` duy trì behavior POST `/logout`; GET `/logout` hiển thị confirmation khi CSRF bật.
- `csrf(Customizer.withDefaults())` **giữ CSRF enabled** (đây cũng là mặc định của Spring Security).
- `/profile`, `/profile/display-name` đều yêu cầu authentication; GET chỉ đọc, POST thay đổi trạng thái.
- Password đã được mã hóa bằng DelegatingPasswordEncoder; password demo chỉ dùng cục bộ, không phải secret production.

**Không có `csrf.disable()`, `ignoringRequestMatchers("/login", "/logout")` hoặc đổi logout sang GET**. Đây là những đường tắt có thể vô hiệu hóa đúng phần cần bảo vệ trong bài.

### 9.4. MockMvc: thực nghiệm có/không có CSRF token

`src/test/java/demo/csrf/CsrfSecurityTest.java`:

~~~java
package demo.csrf;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfSecurityTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    ProfileStore profiles;

    @BeforeEach
    void reset() {
        profiles.reset();
    }

    @Test
    void loginPageIsPublicAndHasCsrfForm() throws Exception {
        mvc.perform(get("/login"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        org.hamcrest.Matchers.containsString("_csrf")));
    }

    @Test
    void loginWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "student")
                        .param("password", "local-test-password-123"))
                .andExpect(status().isForbidden());
    }

    @Test
    void loginWithCsrfIsProcessed() throws Exception {
        mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "student")
                        .param("password", "local-test-password-123"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void unsafeProfilePostNeedsCsrfToken() throws Exception {
        mvc.perform(post("/profile/display-name")
                        .with(user("student"))
                        .param("value", "Forged"))
                .andExpect(status().isForbidden());

        org.junit.jupiter.api.Assertions.assertEquals(
                "Initial", profiles.get());
    }

    @Test
    void validCsrfAllowsAuthenticatedUpdate() throws Exception {
        mvc.perform(post("/profile/display-name")
                        .with(user("student"))
                        .with(csrf())
                        .param("value", "Approved"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value("Approved"));

        org.junit.jupiter.api.Assertions.assertEquals(
                "Approved", profiles.get());
    }

    @Test
    void invalidCsrfTokenIsRejected() throws Exception {
        mvc.perform(post("/profile/display-name")
                        .with(user("student"))
                        .with(csrf().useInvalidToken())
                        .param("value", "Forged"))
                .andExpect(status().isForbidden());

        org.junit.jupiter.api.Assertions.assertEquals(
                "Initial", profiles.get());
    }

    @Test
    void logoutNeedsCsrfToken() throws Exception {
        mvc.perform(post("/logout")
                        .with(user("student")))
                .andExpect(status().isForbidden());

        mvc.perform(post("/logout")
                        .with(user("student"))
                        .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?logout"));
    }

    @Test
    void profileReadRequiresAuthentication() throws Exception {
        mvc.perform(get("/profile"))
                .andExpect(status().is3xxRedirection());

        mvc.perform(get("/profile").with(user("student")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value("Initial"));
    }
}
~~~

Các điểm cần đọc khi chạy test:
- `.with(csrf())` là tiện ích của `spring-security-test`; nó đưa **token hợp lệ cho request test**, không phải cách browser “tự có token”.
- `.with(csrf().useInvalidToken())` mô phỏng token sai; kết quả phải là 403 và **không có side effect**.
- `.with(user("student"))` **mô phỏng Authentication trong MockMvc** để cô lập kiểm thử CSRF; nó không thực hiện password login. Hai test `/login` kiểm tra trực tiếp flow form login.
- `POST /logout` thiếu CSRF token không được thực thi; POST hợp lệ redirect theo default Spring Security.
- GET `/profile` không cần CSRF token vì là read-only, nhưng vẫn cần authentication.

Chạy:

~~~bash
# Khi có Gradle phù hợp:
gradle test

# Nếu dự án có Gradle Wrapper:
./gradlew test
# Windows:
# gradlew.bat test
~~~

**Kỳ vọng:** 8 test pass. Không giả định một chuỗi stdout Gradle cố định vì output thay đổi theo version và môi trường. Nếu muốn quan sát bằng browser, chạy `gradle bootRun` rồi mở `http://localhost:8080/login` với username `student` / password `local-test-password-123`. Chỉ dùng HTTP và password giả trên localhost; với triển khai thực phải dùng HTTPS. Trang login/logout mặc định của Spring Security cho bạn xem cách token được render mà không phải tự xây form.

### 9.5. Vì sao test thiếu token trả 403, không phải 401?

`CsrfFilter` kiểm tra token trên request unsafe trước khi controller xử lý. Nếu thiếu/sai token, Spring Security thường phản hồi **403 Forbidden**; đây **không** phải lỗi “username/password sai”. Một endpoint không có authentication có thể redirect login hoặc trả 401/403 tùy configuration và thứ tự xử lý, nên phải phân biệt **CSRF rejection** với **authentication failure**.

Trong ứng dụng có nhiều `SecurityFilterChain`, phải xác định đúng chain nào match request; nếu một chain bỏ CSRF hoặc chỉ match một phần path, test có thể đang gọi nhầm chain.

## 10. Form HTML và JavaScript SPA lấy token như thế nào?

### 10.1. HTML form server-rendered

Với một app Spring MVC dùng template engine có tích hợp Spring Security:
- GET `/login` hoặc trang form sẽ render một CSRF token vào hidden input.
- Form POST giữ cùng cookie session và gửi trường `_csrf` trong body; `CsrfFilter` kiểm tra.
- Form logout cũng phải POST với token, không dùng link GET thực sự logout.
- CSRF token **không phải mật khẩu** và không thay thế session authentication; form vẫn cần credential/quyền hợp lệ.

Thymeleaf `th:action` tích hợp với Spring MVC `RequestDataValueProcessor` có thể tự chèn hidden CSRF field. Nếu bạn dùng HTML tĩnh, React form tự tạo hoặc một template engine không có integration, bạn phải chủ động cung cấp token.

### 10.2. SPA dùng cookie session

SPA thường gửi `fetch`/Axios tới API bằng cookie được browser quản lý. Với Spring Security 6, phải xét **deferred token, BREACH masking và token clearing** sau authentication/logout.

Một hướng dẫn chính thức hỗ trợ `GET /csrf` để client nhận token theo yêu cầu:

~~~java
// Minh họa controller trong dự án Spring MVC có CSRF enabled.
package demo.csrf;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfTokenController {
    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }
}
~~~

Nếu cần lấy token **trước login**, cho phép `GET /csrf` trong `authorizeHttpRequests`, nhưng **không** mở CORS tùy tiện cho token endpoint, không cache token và áp dụng chính sách phiên phù hợp. Đây là **phần mở rộng tùy chọn** cho dự án có frontend JS, không bắt buộc cho demo form login mặc định.

Một SPA cùng origin có thể:
1. `GET /csrf` qua kết nối đúng origin để lấy token và tên header (mặc định `X-CSRF-TOKEN`).
2. Khi cần POST/PUT/PATCH/DELETE, gửi `X-CSRF-TOKEN` trong header cùng session cookie hợp lệ.
3. Sau login/logout thành công, **lấy token mới** vì Spring Security có thể xóa token cũ.
4. Khi lỗi 403 do token hết hạn/đã rotate, tái đồng bộ theo policy; **không** tự tắt CSRF để retry vô hạn.
5. Không gắn CSRF token vào request gửi tới domain thứ ba, không đưa token vào query/log hoặc global HTTP interceptor áp dụng không giới hạn.

Ví dụ client-side **mô tả cách gửi** (giả sử biến `csrfToken` đã được lấy bằng phương thức cùng origin):

~~~javascript
async function changeDisplayName(csrfToken, value) {
  const body = new URLSearchParams({ value });
  const response = await fetch("/profile/display-name", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "X-CSRF-TOKEN": csrfToken
    },
    body
  });
  if (!response.ok) {
    throw new Error("Request rejected: " + response.status);
  }
  return response.json();
}
~~~

JS này chỉ minh họa logic gửi token, **không phải cả app JavaScript độc lập**. `credentials:"same-origin"` giúp gửi cookie cho request cùng origin; bảo vệ thực tế vẫn do server xác minh token. Nếu frontend/API thực sự ở hai origin khác nhau, cần CORS và cookie policy rõ ràng **cùng CSRF protection**, không thay bằng `credentials:"include"` cho mọi nơi.

### 10.3. Cookie-to-header integration

Spring Security cung cấp `CookieCsrfTokenRepository`. Một số SPA muốn JS đọc token từ cookie `XSRF-TOKEN` rồi gửi lại qua `X-XSRF-TOKEN`. Để JS đọc cookie đó, có thể sử dụng `CookieCsrfTokenRepository.withHttpOnlyFalse()` **trong pattern được thiết kế đúng**.

**Không copy một dòng đó rồi xem là đủ trong Spring Security 6.x**: Spring Security 6 có BREACH/XOR request handler và deferred loading; frontend gửi plain cookie token qua header cần request handler tương ứng, đồng thời phải làm mới token sau login/logout. Xem ví dụ SPA chính thức của **đúng phiên bản framework** và kiểm tra browser E2E.

Không cấu hình `HttpOnly=false` cho **session cookie** chỉ vì CSRF cookie cần đọc được. Session cookie vẫn nên `Secure`, `HttpOnly`, `SameSite` theo threat model.

## 11. Chia tách API dùng Bearer token và ứng dụng dùng cookie session

Một hệ thống có thể có:
- `/web/**` dùng session cookie, login/logout qua browser.
- `/api/**` chỉ nhận OAuth2 access token được client tự đưa vào `Authorization` header.

Nếu thật sự cô lập, một API chỉ Bearer có thể không cần synchronizer CSRF token vì browser khác origin **không tự đính kèm Bearer access token**. Nhưng cần chứng minh:
- API **không** chấp nhận session cookie/remember-me/Basic làm credential thay thế.
- `SecurityFilterChain` cho API match chính xác mọi endpoint API.
- Gateway/proxy không tự “nâng quyền” dựa vào cookie ở upstream.
- CORS không mở tùy tiện request cross-origin có credential.
- JWT/opaque access token được xác thực issuer/audience/expiry/scope đầy đủ.
- XSS và token theft vẫn được phòng chống; bỏ CSRF không đồng nghĩa không còn lỗ hổng trình duyệt.

**Minh họa cấu hình ranh giới, không phải project biên dịch độc lập:**

~~~java
// Trong ứng dụng Spring Boot có OAuth2 Resource Server
// và hai SecurityFilterChain tách riêng theo @Order.
@Bean
@Order(1)
SecurityFilterChain bearerApi(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .sessionManagement(s ->
            s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .csrf(AbstractHttpConfigurer::disable)
        .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))
        .authorizeHttpRequests(a ->
            a.anyRequest().authenticated())
        .build();
}

// Chain còn lại phục vụ browser HTML forms:
@Bean
@Order(2)
SecurityFilterChain browserWeb(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .csrf(Customizer.withDefaults())
        .build();
}
~~~

Code trên chỉ là **mảnh pattern**: cần đầy đủ imports, dependency Resource Server, JWT decoder/issuer config, chính sách login/logout và review precedence/entry points. Tắt CSRF trên `/api/**` chỉ an toàn nếu endpoint ấy **thật sự chỉ** chấp nhận credential không tự gửi. Nếu một `/api/**` cũng nhận cookie session, phải giữ hoặc thiết kế lại CSRF defense.

**Bẫy phổ biến:** dùng `csrf(csrf -> csrf.ignoringRequestMatchers("/api/**"))` vì “REST API”, trong khi các API đó vẫn dùng `JSESSIONID`. Tên đường dẫn không chứng minh absence of CSRF risk.

## 12. CORS, Origin/Referer, Fetch Metadata và defense in depth

### 12.1. CORS không phải cơ chế CSRF hoàn chỉnh

Một browser có thể gửi HTML form cross-origin thuộc loại *simple request* mà không cần preflight. Browser không cho JavaScript attacker đọc response theo Same-Origin Policy vẫn có thể gửi request tới server.

Đối với request có custom header như `X-CSRF-TOKEN`, browser thường cần CORS preflight khi cross-origin. Đó là lớp hữu ích, nhưng:
- Preflight có thể được cho phép nhầm do wildcard/trust subdomain yếu.
- Không phải mọi request do browser gửi đều là AJAX có custom header.
- Server vẫn phải xác minh **token thật** nếu sử dụng pattern synchronizer.
- Có client-side CSRF khi chính JS tin cậy bị dụ gửi request tới URL do attacker điều khiển; JS lúc này có thể đính kèm token thật.

Không dựa duy nhất vào `@CrossOrigin`/CORS để bảo vệ POST thay đổi trạng thái của browser session.

### 12.2. Kiểm tra Origin/Referer

Server có thể xác định origin khởi phát qua HTTP `Origin` hoặc `Referer` để hỗ trợ defense in depth. Phải:
- So chính xác scheme/host/port với origin được tin, không dùng kiểm tra chuỗi suffix yếu.
- Xử lý absent/null header theo policy; **không** xem thiếu header là bằng chứng cùng origin.
- Cẩn thận reverse proxy: public host khác host nội bộ, chỉ tin forwarding headers từ proxy đã kiểm soát.
- Không ghi full Referer/query chứa token nhạy cảm vào log.

Origin check hữu ích nhưng không tự thay mọi CSRF token trong ứng dụng có nhiều browser/legacy clients hoặc lỗ hổng same-site subdomain.

### 12.3. Fetch Metadata

Các header như `Sec-Fetch-Site` (`same-origin`, `same-site`, `cross-site`, `none`), `Sec-Fetch-Mode` và `Sec-Fetch-Dest` giúp server phân loại request theo ngữ cảnh trình duyệt.

Ví dụ một policy có thể chặn phần lớn **cross-site unsafe requests** khi `Sec-Fetch-Site=cross-site`, nhưng cần:
- Fallback cho browser không gửi Fetch Metadata, đồng thời xét Origin/Referer/token.
- Ngoại lệ được tài liệu hóa cho OAuth redirect/callback hoặc các flow cross-origin hợp lệ.
- Không mặc định coi `same-site` như `same-origin` khi có subdomain không tin cậy.
- Kiểm thử browser, proxy, bot/API client và compatibility trước khi enforcement.

**CSRF token + SameSite cookie + Origin/Fetch Metadata + kiểm tra reauthentication ở hành động nhạy cảm** là defense in depth. Không một header đơn lẻ thay thế toàn bộ threat model.

## 13. Những tác vụ nhạy cảm cần bảo vệ bổ sung

Ngay cả khi CSRF token hợp lệ, có thể vẫn cần **reauthentication/MFA/transaction confirmation** để đổi email khôi phục, thêm passkey, chuyển tiền, thay đổi MFA hoặc xóa tài khoản. Vì:
- Một script XSS chạy cùng origin có thể gửi CSRF token hợp lệ.
- Người dùng có thể đang trong session lâu và thao tác nhạy cảm đòi xác nhận mới.
- CSRF token không xác nhận user đang nhìn đúng nội dung giao dịch nếu UI bị lừa.
- Same-site subdomain yếu có thể có đường tấn công ngoài trường hợp cross-site chuẩn.

Tùy mức nhạy cảm, có thể yêu cầu password/passkey/MFA gần thời điểm hành động, one-time transaction token gắn với action parameters, xác nhận qua kênh độc lập và audit. **CAPTCHA** chỉ hỗ trợ chống bot, **không phải** biện pháp CSRF cốt lõi.

## 14. Login/logout với OAuth2, OIDC, SAML và passkey

Có những protocol login dùng browser redirect hoặc POST callback, nên không thể áp một quy tắc “mọi callback POST đều phải chứa form `_csrf`” mà bỏ các ràng buộc giao thức.

| Luồng | Dữ liệu ràng buộc cần kiểm tra | Ghi nhớ |
| --- | --- | --- |
| Form username/password | CSRF token ở `POST /login`; policy session | Login CSRF có thể tạo phiên account attacker |
| Logout form | CSRF token ở `POST /logout` | GET logout không nên có side effect |
| OAuth2 Authorization Code | `state`, request correlation, redirect URI, PKCE, issuer/audience và ID token checks khi OIDC | `state` giúp chống CSRF cho callback, **không** miễn CSRF cho mọi POST nội bộ |
| OIDC RP-initiated logout | State/return URL, session và provider-specific rules | Local logout và OP logout là hai hoạt động có scope khác nhau |
| SAML Web Browser SSO | Signature, issuer, audience, recipient, `InResponseTo`, replay protection | SAML POST/ACS có cơ chế xác thực riêng; không blanket-exempt các URL khác |
| WebAuthn/passkey | Challenge, origin, RP ID hash, chữ ký, user verification, session/account binding | Không bỏ CSRF cho credential registration/account linking chỉ vì dùng passkey |
| Remember-me | Cookie tự gửi, token được quản lý riêng | Vẫn có CSRF risk đối với unsafe methods |

**Đặc biệt với SAML/OIDC:** các endpoint callback được IdP/AS gọi qua trình duyệt có thể không mang CSRF token của ứng dụng và có cơ chế xác minh khác. Chỉ exempt **đúng endpoint/protocol cần thiết**, với cấu hình Spring Security thích hợp, không dùng `csrf.disable()` toàn ứng dụng. Cần bảo vệ login initiation, account linking, logout và các action nội bộ theo policy riêng.

## 15. Kiểm thử các đường đi thực tế

### 15.1. Ma trận Spring Security

| Test | Request | Kỳ vọng |
| --- | --- | --- |
| Login page | `GET /login` | 200, render token cho form |
| Login giả mạo | `POST /login` thiếu CSRF | 403; không tạo session authenticated |
| Login hợp lệ | `POST /login` có CSRF, credential đúng | Xác thực/redirect theo cấu hình |
| Logout giả mạo | `POST /logout` thiếu CSRF | 403; không chạy logout |
| Logout hợp lệ | `POST /logout` có CSRF | Invalidate session/clear context, redirect |
| Logout GET | `GET /logout` | Trang confirmation, **không** logout ngay |
| POST thay đổi hồ sơ | Cookie/session auth nhưng không CSRF | 403, không side effect |
| POST có token sai | Sai token | 403, không side effect |
| POST có token đúng | Authentication + CSRF hợp lệ | Tiếp tục authorization/validation nghiệp vụ |
| API cookie JWT | Browser tự gửi cookie | Vẫn phải bảo vệ CSRF |
| API Bearer-only | Header access token thủ công | Xác minh access token; quyết định CSRF theo auth transport |
| Side effect qua GET | `GET /delete` | Đây là lỗi thiết kế: đổi thành unsafe method có CSRF |

### 15.2. Kiểm thử trình duyệt thực

Dùng browser DevTools + môi trường thử nghiệm:
1. Xác định session cookie có `Secure`, `HttpOnly`, `SameSite` đúng.
2. Mở GET login, xem form có hidden `_csrf` hoặc cơ chế header token hợp lệ.
3. Gửi POST login/logout không token/sai token ở môi trường lab, xác nhận phản hồi từ chối và trạng thái phiên không bị thay đổi.
4. Kiểm tra token sau khi login/logout (đặc biệt SPA) và retry logic không tắt CSRF.
5. Thử cross-site/same-site subdomain theo threat model; xác nhận cookie thực tế có/không được browser gửi.
6. Kiểm tra reverse proxy, CORS và Fetch Metadata: không có đường bypass do origin/Host/forwarding headers tự khai.
7. Xác nhận `GET`/`HEAD` và các route được coi là safe **không thực hiện thay đổi nghiệp vụ**.
8. Kiểm tra các luồng federated login/logout theo state/issuer/signature/callback riêng.
9. Đảm bảo CSRF token không được gắn vào URL, support ticket, log, analytics hoặc domain thứ ba.
10. Chạy kiểm thử account recovery, đổi email, password, passkey enrollment vì đây là những action rủi ro cao.

## 16. Sai lầm thường gặp

1. **“CSRF chỉ xảy ra khi user đã login.”** Sai: login CSRF có thể ép browser dùng account attacker.
2. **“GET /logout tiện hơn POST.”** Sai: link/navigation có thể ép logout; nên dùng POST + CSRF.
3. **“HttpOnly cookie đã chống CSRF.”** Sai: browser vẫn **gửi cookie**, chỉ JS không đọc được.
4. **“JWT ký đúng nên không có CSRF.”** Sai nếu JWT được browser tự gửi qua cookie.
5. **“App dùng REST JSON nên không cần CSRF.”** Sai nếu API vẫn nhận credential tự gửi và có đường simple request/misconfigured content types.
6. **“CORS không cho đọc response nên POST không chạy.”** Sai: form/navigation có thể gửi side effect.
7. **“SameSite=Lax là bảo đảm tuyệt đối.”** Sai với GET side effect, same-site subdomain và các khác biệt browser.
8. **“CSRF token có thể đặt trong query URL.”** Sai: có thể rò qua logs/Referer/history.
9. **“Tắt CSRF để sửa lỗi 403 ở POST login.”** Sai: phải đưa token vào form và kiểm tra request.
10. **“Bỏ CSRF cho tất cả `/api/**`.”** Sai khi API chấp nhận cookie/Basic/remember-me.
11. **“Thêm header `X-CSRF-TOKEN` bất kỳ là đủ.”** Sai: nếu dùng token pattern phải kiểm tra giá trị so với expected token, không chỉ tên header.
12. **“Bật CORS `*` giúp chống CSRF.”** Sai; có thể mở rộng bề mặt tấn công.
13. **“Sau logout SPA dùng mã CSRF cũ mãi.”** Sai: token có thể bị clear, cần lấy mới.
14. **“CSRF token chữa XSS.”** Sai: XSS cùng origin có thể thao tác token và request.
15. **“Browser HTTP Basic không cần CSRF.”** Sai nếu browser tự gắn credential vào cross-site request phù hợp.
16. **“Origin header không có nghĩa request cùng origin.”** Đúng: thiếu Origin không chứng minh an toàn; cần policy rõ.
17. **“POST là an toàn miễn có CSRF token.”** Sai: vẫn phải authentication, authorization, input validation và chống replay/abuse ở lớp nghiệp vụ.
18. **“Test `.with(user())` xác minh luôn login/password.”** Sai: test helper này chèn Authentication, phải test `POST /login` riêng.

## 17. Bài tập tự kiểm tra

**Câu 1.** User mở `GET /logout` và bị đăng xuất ngay. Đây có thể là vấn đề gì?  
**Đáp án:** Có thể bị forced logout do request safe method có side effect. Với Spring Security mặc định bật CSRF, GET chỉ nên hiển thị trang xác nhận; POST + token mới logout.

**Câu 2.** POST `/login` chưa có `JSESSIONID` nhưng thiếu CSRF token. Có nên cho qua vì “user chưa đăng nhập”?  
**Không.** Login thay đổi authentication state; login CSRF là rủi ro riêng, Spring Security bảo vệ mặc định.

**Câu 3.** API dùng JWT nhưng token nằm trong cookie `HttpOnly`; CSRF có biến mất?  
**Không.** Browser vẫn có thể tự gửi cookie khi policy cho phép. Server cần CSRF defense tương ứng.

**Câu 4.** API chỉ nhận OAuth access token trong `Authorization` header do JS trusted client chủ động đưa vào; không nhận cookie/Basic. Có nhất thiết dùng synchronizer token?  
**Không nhất thiết**, nếu threat model và filter chain chứng minh đúng thiết kế. Vẫn cần chống XSS, token theft, CORS misconfiguration và authorization.

**Câu 5.** `SameSite=Strict` có thay thế permission check cho việc xóa tài khoản?  
**Không.** SameSite giảm cross-site cookie sending; permission, re-authentication và CSRF/transaction defense vẫn quan trọng.

**Câu 6.** SPA gửi POST có CSRF token trước khi login, sau login lại bị 403. Nên làm gì?  
**Lấy CSRF token mới** theo integration của Spring Security, vì strategy có thể clear token khi Authentication thành công; không tắt CSRF để “sửa”.

**Câu 7.** Hai origin `https://app.example.com` và `https://blog.example.com` có thể same-site không?  
**Có**, nhưng khác origin. Nếu blog không tin cậy, SameSite không phải ranh giới origin an toàn.

**Câu 8.** `MockMvc.post("/settings").with(user("student"))` thiếu `csrf()` bị 403; đây có phải lỗi mật khẩu?  
**Không.** `user()` đã mô phỏng authenticated principal; 403 do `CsrfFilter` chặn request unsafe.

### Checklist go-live

- [ ] Các form login/logout và state-changing POST có CSRF defense.
- [ ] Logout thực thi bằng POST + token, GET chỉ confirmation/read-only.
- [ ] Không có GET/HEAD/OPTIONS/TRACE endpoint làm side effect nghiệp vụ.
- [ ] Đã kiểm kê cookie, Basic/Digest, remember-me, mTLS, bearer header và mọi phương thức credential tự gửi.
- [ ] Session cookies có Secure/HttpOnly/SameSite phù hợp; CSRF token không nằm URL/log.
- [ ] Spring Security `CsrfFilter` enabled cho browser session routes; không miễn tràn lan `/api/**`.
- [ ] Form/SPA lấy và submit CSRF token đúng Spring Security version, refresh token sau login/logout.
- [ ] CORS, Origin/Referer, Fetch Metadata là các lớp hỗ trợ, không mặc định thay CSRF token.
- [ ] Browser/API chains tách ranh giới chính xác khi miễn CSRF cho bearer-only endpoints.
- [ ] XSS/CSP, session fixation protection, re-authentication cho thao tác nhạy cảm được đánh giá.
- [ ] Test login/logout CSRF, token sai, token thiếu, negative cases và **không có side effect**.
- [ ] Các callback OAuth/OIDC/SAML có state/signature/correlation riêng và chỉ exempt đúng phạm vi cần thiết.

## 18. Nguồn học tập

- [Spring Security 6.5 — Cross Site Request Forgery (CSRF)](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CsrfFilter, session/cookie repositories, login/logout, SPA token rotation và JavaScript integration.
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): GET login page, UsernamePasswordAuthenticationFilter và custom form.
- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): GET confirmation, POST logout, session invalidation và redirect mặc định.
- [Spring Security 6.5 — Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html): `with(csrf())`, `asHeader()` và `useInvalidToken()`.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): synchronizer token, signed double-submit cookie, SameSite, Fetch Metadata, Origin/Referer và client-side CSRF.
- [MDN — SameSite cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie#samesitesamesite-value): thuộc tính cookie và ranh giới cross-site.

**Ghi nhớ:** CSRF là vấn đề của **credential browser tự gửi** và **hành động làm thay đổi trạng thái**. Bảo vệ cả **POST login** lẫn **POST logout**, tránh logout bằng GET; giữ CSRF token cho browser cookie/session, dùng SameSite/CORS/Origin/Fetch Metadata như các lớp bổ sung, và chỉ miễn CSRF cho API thật sự không chấp nhận credential tự động sau khi đánh giá ranh giới đầy đủ.