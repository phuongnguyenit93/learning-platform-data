# Thứ tự bộ lọc, endpoint thông báo và phạm vi miễn CSRF cần thiết

> **Chủ đề:** Spring Security – federation. **Nhóm kiến thức:** Đăng xuất CAS. Bài học tập trung vào **CAS Single Logout (SLO)** khi CAS Server gửi thông báo để một ứng dụng Spring Security hủy `HttpSession` đã đăng nhập, cách sắp xếp `SingleSignOutFilter` trước các bộ lọc có thể từ chối thông báo, cách xác định endpoint tiếp nhận và **miễn kiểm tra CSRF ở phạm vi hẹp nhất có thể**. Ví dụ dành cho Java 17+, Spring Boot 3.x, Spring Security 6.x/Servlet và Apereo Java CAS Client tương thích Jakarta Servlet; các API phải được xác nhận với BOM/version đang triển khai.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **local logout** trên ứng dụng, **CAS SSO logout** tại CAS Server và **Single Logout notification** đến nhiều service.
2. Giải thích vì sao `SingleSignOutFilter` cần quan sát **cả request login có Service Ticket và request logout do CAS gửi**.
3. Biết vai trò khác nhau của `SingleSignOutFilter`, `SingleSignOutHttpSessionListener`, `CasAuthenticationFilter`, `CsrfFilter`, `LogoutFilter` và `AuthorizationFilter`.
4. Xác định nơi CAS gửi SLO: **service URL ban đầu** hoặc `logoutUrl` riêng đã được định nghĩa trong CAS registered-service.
5. Cấu hình endpoint riêng như `POST /cas/slo` khi CAS Server hỗ trợ `logoutUrl` và biết khi nào phải dùng callback mặc định `/login/cas`.
6. Áp dụng một trong hai chiến lược nhất quán: **SLO filter ở lớp Servlet trước Spring Security** hoặc **SLO filter trong SecurityFilterChain trước CsrfFilter**; không đăng ký trùng lặp.
7. Hiểu vì sao `permitAll()` **không** thay thế `csrf.ignoringRequestMatchers(...)` nếu request POST vẫn đi qua `CsrfFilter`.
8. Tránh tắt CSRF toàn ứng dụng; **browser POST /logout vẫn phải có CSRF token**.
9. Xác minh mapping `Service Ticket → HttpSession`, cleanup, session fixation, cluster và các sự cố thông báo đến node khác.
10. Kiểm thử success/failure: SLO back-channel có/không có CSRF token, request giả, không tìm session, token đã dùng, request không đúng path/method, front-channel, ingress/HTTPS và concurrency.

**Nguyên tắc trọng tâm:** Thông báo CAS SLO là một **thông điệp giao thức từ hệ thống SSO**, không phải biểu mẫu POST do người dùng browser điền. Vì CAS Server thường **không có CSRF token của session ứng dụng**, đừng bắt nó nộp token như người dùng. Nhưng hãy giới hạn ngoại lệ về **đường dẫn, HTTP method và nguồn được phép**, đồng thời không biến `POST /logout` thường thành endpoint không CSRF.

## 2. Ba thao tác logout — không phải cùng một endpoint

| Hành động | Ai khởi tạo? | Endpoint | Kết quả trực tiếp | CSRF? |
| --- | --- | --- | --- | --- |
| **Local application logout** | Browser của người dùng | `POST https://app.example.org/logout` | Xóa `HttpSession`/`SecurityContext` ở ứng dụng A | **Có**, theo Spring Security khi dùng session cookie |
| **CAS SSO logout** | Browser truy cập CAS Server | `https://sso.example.org/cas/logout` | Xóa/thu hồi phiên SSO CAS (TGT/TGC) theo policy | Được CAS Server tự bảo vệ theo thiết kế riêng |
| **CAS Single Logout notification** | CAS Server gửi tới service | Thường `POST https://app.example.org/login/cas` hoặc endpoint riêng `/cas/slo` | CAS client tìm và invalidate phiên A đã gắn với Service Ticket | Không thể đòi CSRF token của browser A; cần bảo vệ nguồn/protocol riêng |
| **SLO front-channel (nếu hỗ trợ)** | CAS Server thông qua browser | Có thể là GET/JSONP tới service URL theo cấu hình CAS | Yêu cầu service xử lý logout qua browser; phụ thuộc cookie/browser | GET không mặc định cần CSRF; phải đánh giá hỗ trợ/integrity |
| **CAS login callback** | Browser sau CAS login | `GET /login/cas?ticket=ST-...` | `CasAuthenticationFilter` validate ST, tạo local Authentication | GET, nhưng có CAS service binding và ticket validation |
| **CAS service ticket validation** | Backend ứng dụng | `GET /cas/serviceValidate` trên CAS Server | Kiểm ST đúng `service`, còn hiệu lực/dùng một lần | Không phải endpoint CSRF của App A |

**Điểm dễ nhầm:** CAS Server `/cas/logout` không phải Spring Security `/logout`, và thông báo SLO **không phải yêu cầu người dùng logout qua trang web**. CAS có thể kết thúc SSO session rồi gửi một POST không có cookie tới ứng dụng; ứng dụng phải xử lý dựa trên **ticket–session mapping** được tạo từ login trước đó.

## 3. Luồng đăng nhập và vì sao cần bắt request chứa Service Ticket

Muốn logout một session sau này, CAS client phải nhớ **HttpSession nào được tạo nhờ Service Ticket nào**.

```text
Browser                  Spring Application                CAS Server
  |                             |                              |
  | GET /private                |                              |
  |---------------------------->|                              |
  |<-- 302 CAS /login?service=...                              |
  |------------------------------------------------------------>|
  |<------- 302 /login/cas?ticket=ST-abc ----------------------|
  |                             |                              |
  | GET /login/cas?ticket=ST-abc|                              |
  |---------------------------->|                              |
  |                    [SingleSignOutFilter]
  |                    ghi nhận ST-abc -> HttpSession A
  |                             |
  |                    [CasAuthenticationFilter]
  |                    validate ST với CAS Server              |
  |                             |----------------------------->|
  |                             |<-----------------------------|
  |                    [SecurityContext + HttpSession A]
  |<---- 302 /private ----------|
  | GET /private, cookie A      |
  |---------------------------->|
  |<--- dữ liệu nếu có quyền ---|
```

Khi CAS SSO session bị hủy:

```text
CAS Server                   Spring Application
    |                                |
    | POST /cas/slo                  |
    | Content-Type: application/x-www-form-urlencoded
    | logoutRequest=<SAML LogoutRequest>
    |------------------------------->|
    |                    [SingleSignOutFilter]
    |                      parse/logoutRequest
    |                      lấy SessionIndex/ST-abc
    |                      tra mapping -> HttpSession A
    |                      session.invalidate()
    |<-------------------------------|
    |                    HttpSession A không còn hợp lệ
```

**Điều cốt lõi:** Nếu bạn chỉ cho SLO filter chạy trên `/cas/slo` mà **không cho nó thấy request `GET /login/cas?ticket=...`**, bộ lọc mặc định có thể **không có mapping** để biết ST nào liên kết với HttpSession. Vì thế Apereo Java CAS Client mô tả `SingleSignOutFilter` được map `/*` ở cấp Servlet; endpoint logout riêng chỉ **giới hạn vị trí xử lý logout message**, không nhất thiết giới hạn toàn bộ nơi filter được chạy.

### 3.1. SessionIndex dùng trong SLO là gì?

CAS Server thường gửi **CAS Service Ticket ID** của lần user đăng nhập như một session identifier trong SAML-style `LogoutRequest`. Apereo CAS Client sử dụng giá trị đó để tìm session đã được ghi nhận:

```text
ticket đăng nhập ST-abc --> mapping tại client --> HttpSession A
LogoutRequest/SessionIndex = ST-abc
                                      |
                                      v
                              invalidate HttpSession A
```

Không coi `SessionIndex` này là `JSESSIONID` browser hoặc một ID tùy ý có thể dùng để xóa session. Không lấy `NameID` trong LogoutRequest để tìm và xóa **mọi session** của cùng username nếu hệ thống/tenant không có chính sách global revocation riêng. Mapping theo đúng ticket giúp hạn chế việc hủy nhầm session khác.

### 3.2. `SingleSignOutHttpSessionListener` làm gì?

Apereo Java CAS Client cung cấp `SingleSignOutHttpSessionListener` để dọn `SessionMappingStorage` khi `HttpSession` bị hủy vì logout, timeout hoặc invalidate bởi ứng dụng. Nếu thiếu listener, mapping có thể giữ tham chiếu phiên đã chết, tăng leak/bất nhất hoặc làm chẩn đoán SLO khó hơn.

Listener **không thay thế SLO filter**: nó chỉ phản ứng vòng đời HttpSession, không nhận POST `logoutRequest` từ CAS. Cần cả hai thành phần trong cấu hình CAS client kiểu servlet.

## 4. SLO back-channel và front-channel cần được phân biệt

### 4.1. Back-channel: CAS Server gọi thẳng service

Theo Apereo CAS, `LogoutType.BACK_CHANNEL` thường là kiểu mặc định của CAS registered-service. CAS thực hiện **HTTP POST trực tiếp** tới service; request chứa `logoutRequest`, bên trong là **SAML `LogoutRequest`** có `SessionIndex` dùng tương quan. Kết nối không phụ thuộc browser gửi cookie của ứng dụng.

Ưu điểm: ít bị hạn chế bởi third-party cookies/iframe, có thể hoạt động khi người dùng đã đóng tab ứng dụng. Nhược điểm: CAS Server phải nhìn thấy callback service qua mạng, TLS và ingress; ứng dụng phải lưu đúng ticket–session mapping trên các node và có khả năng invalidation.

### 4.2. Front-channel: CAS điều phối qua browser

Một số cấu hình CAS dùng browser gửi `GET`/JSONP logout request đến các services. Nó chịu ảnh hưởng từ JavaScript, frame/browser privacy và hỗ trợ của từng CAS client. **Không giả định rằng mọi Spring Security CAS client đều nhận dạng SLO GET**; kiểm thử đúng Apereo Java CAS Client, CAS Server và trình duyệt đang dùng.

Nếu đã chọn back-channel POST, **không mở ngoại lệ CSRF cho mọi GET** vì GET vốn không được Spring yêu cầu CSRF theo mặc định, và đặc biệt không cấu hình `GET /logout` thực hiện local logout không xác nhận.

### 4.3. Một CAS server có thể dùng SAML protocol khác CAS protocol

Apereo CAS có thể làm IdP OIDC/SAML2, nhưng `SingleSignOutFilter` nói ở đây là **Apereo Java CAS Client của CAS protocol**, không tự thay thế `saml2Logout` hoặc OIDC Back-Channel Logout. SAML2 logout dùng request signature, issuer, destination và profile validation riêng; OIDC logout có Logout Token JWT theo chuẩn riêng. Không ghép filter, callback và miễn CSRF của ba giao thức chỉ vì endpoint đều chứa chữ “logout”.

## 5. CAS gửi thông báo vào URL nào?

Apereo CAS có hai cơ chế cần phân biệt.

### 5.1. Mặc định: URL service lúc cấp ticket

Nếu service của App A được cấu hình:

```text
ServiceProperties.service =
  https://app.example.org/login/cas
```

và CAS registered-service **không đặt `logoutUrl` riêng**, SLO notification thường được gửi tới **URL service mà CAS đã ghi nhận lúc xác thực**, ví dụ:

```http
POST /login/cas HTTP/1.1
Host: app.example.org
Content-Type: application/x-www-form-urlencoded

logoutRequest=<URL-encoded XML>
```

Cùng path `/login/cas` có thể xử lý **hai loại request**: browser `GET` chứa `ticket` thì CAS authentication filter validate; CAS Server `POST` chứa `logoutRequest` thì SLO filter xử lý. **Thứ tự bộ lọc rất quan trọng**: SLO POST phải được nhận trước khi CsrfFilter chặn hoặc CasAuthenticationFilter hiểu sai.

### 5.2. Khuyến nghị cho triển khai mới: registered `logoutUrl` chuyên dụng

Apereo CAS cho phép service có `logoutUrl` khác với URL service ban đầu. Ví dụ chính sách minh họa trong CAS service registry:

```json
{
  "@class": "org.apereo.cas.services.CasRegisteredService",
  "serviceId": "^https://app\\.example\\.org/login/cas$",
  "name": "reports-app",
  "id": 1200,
  "logoutType": "BACK_CHANNEL",
  "logoutUrl": "https://app.example.org/cas/slo"
}
```

Đây là **minh họa cấu hình theo kiểu Apereo CAS registered-service**, không phải file có thể dán vào mọi phiên bản CAS mà không kiểm schema/serializer. Xác nhận field `logoutType`, `logoutUrl` và class name với **CAS Server đang chạy**, đồng thời bảo đảm service ID regex/route đã được phê duyệt.

Cấu hình này tách bạch:

```text
CAS login/ST callback:
  GET  https://app.example.org/login/cas?ticket=ST-abc

CAS SLO notification:
  POST https://app.example.org/cas/slo
  body: logoutRequest=<encoded SAML LogoutRequest>

Browser local logout:
  POST https://app.example.org/logout
  body: _csrf=<browser-session-csrf-token>
```

Một endpoint riêng giúp đặt policy ingress/mTLS/rate limit và phạm vi CSRF exception **chỉ cho `POST /cas/slo`**; không tác động thao tác logout browser. Tuy nhiên, vì SLO filter cần ghi ticket–session mapping khi login, **bản thân filter vẫn phải chạy đủ rộng trên request login**.

**Nếu CAS Server không hỗ trợ hoặc chưa cấu hình `logoutUrl`:** Đừng tự tạo `/cas/slo` rồi đợi CAS tự gửi tới đó. Phải dùng endpoint mặc định thật (thường `/login/cas`) và giới hạn ngoại lệ **POST trên path đó** khi cần. Chỉ xác định URL bằng cách xem CAS registered-service + access logs + test SLO, không đoán.

### 5.3. Chọn path bảo mật và ổn định

- Cố định **HTTPS public canonical**; không dùng URL nội bộ `http://app:8080` nếu CAS Server không truy cập được.
- Không dùng `/logout` của browser làm CAS callback nếu còn có thể đặt endpoint riêng.
- Không dùng wildcard `/logout/**` cho tất cả giao thức và tenants.
- Nếu ứng dụng có `context-path=/portal`, public callback có thể là `https://app.example.org/portal/cas/slo`, nhưng servlet path matcher thường là `/cas/slo` bên trong context. Kiểm tra thực tế.
- CAS Server gọi endpoint từ **mạng CAS**, không có cookie session browser; bỏ authentication gateway bắt đăng nhập trên đúng callback.
- Reverse proxy phải giữ `POST`, body `application/x-www-form-urlencoded`, `logoutRequest` và encoding; không rewrite path/method.
- Nếu mỗi tenant có CAS Server khác hoặc registered-service khác, callback routing/trust store/session mapping phải phân vùng đúng tenant, không để SLO tenant A hủy session tenant B.

## 6. Thứ tự bộ lọc: hai tầng cần nhìn tách biệt

Ứng dụng Servlet có **hai tầng filter chain**:

```text
Servlet Container Filter Chain
    |
    +--> CharacterEncodingFilter (tùy topology, nhưng nên sớm)
    |
    +--> Apereo SingleSignOutFilter        <--- phương án 1: trước Spring
    |
    +--> DelegatingFilterProxy("springSecurityFilterChain")
             |
             +--> FilterChainProxy
                    |
                    +--> SecurityContextHolderFilter
                    +--> HeaderWriterFilter
                    +--> CsrfFilter
                    +--> LogoutFilter
                    +--> CasAuthenticationFilter
                    +--> ...
                    +--> AuthorizationFilter
    |
    +--> DispatcherServlet / MVC Controller
```

Từng FilterChainProxy có thứ tự được Spring Security thiết lập. Khi thêm custom filter, **đừng nhìn thứ tự `@Bean` trong code** rồi tưởng đó là thứ tự HTTP request. Phải xem **thứ tự thực tế** trong log hoặc integration tests.

### 6.1. Phương án A: đặt Apereo SLO filter trước toàn bộ Spring Security chain

Đây là lựa chọn dễ hiểu cho **Apereo Java CAS Client SLO kiểu Servlet Filter**:

1. `CharacterEncodingFilter` dùng UTF-8 được đặt sớm, tránh decode lỗi body XML/form khi cần.
2. `SingleSignOutFilter` được đăng ký **một lần** ở Servlet chain với URL pattern `/*` để thấy request mang `ticket`, đồng thời phát hiện `logoutRequest`.
3. `DelegatingFilterProxy`/Spring Security chain chạy sau cho request bình thường; valid SLO callback được Apereo filter xử lý trước khi tới `CsrfFilter`.
4. `CasAuthenticationFilter` nằm trong Spring Security chain để validate ST và tạo authenticated session.
5. `SingleSignOutHttpSessionListener` cleanup mapping khi HttpSession bị hủy.

**Hệ quả CSRF:** Nếu `SingleSignOutFilter` xử lý hoàn chỉnh CAS POST **trước** Spring Security `CsrfFilter`, **không cần tắt CSRF hay thêm `csrf.ignoringRequestMatchers`** để thông báo đó được nhận. Các request POST khác tiếp tục qua Spring Security và phải có CSRF token như bình thường.

**Điều kiện:** Phải **đo và kiểm chứng thứ tự Servlet Filter thực tế**; nếu SLO filter bị Boot đăng ký **sau** Spring Security, một POST logoutRequest không có CSRF có thể bị `CsrfFilter` chặn `403` trước khi SLO filter nhìn thấy. Nếu bộ lọc ở tầng ingress/WAF chặn trước, thứ tự trong Spring cũng không cứu được.

### 6.2. Phương án B: thêm SLO filter bên trong SecurityFilterChain

Có thể thêm `SingleSignOutFilter` với `http.addFilterBefore(singleSignOutFilter, CsrfFilter.class)` để CAS logout POST được xử lý trước `CsrfFilter` và `CasAuthenticationFilter`. Nếu filter được add với `before="CAS_FILTER"` theo ví dụ XML cũ, vẫn cần **kiểm chứng có đứng trước `CsrfFilter` hay không**, vì `CsrfFilter` thông thường xuất hiện trước authentication filters.

Ví dụ cấu trúc, **không chạy song song với Servlet registration trong phương án A**:

```java
// Phương án thay thế: chỉ khi SingleSignOutFilter
// được Spring CAS/Jakarta version của bạn hỗ trợ và
// chưa đăng ký làm Servlet Filter.
SingleSignOutFilter slo = new SingleSignOutFilter();

http.addFilterBefore(slo, CsrfFilter.class);
// Còn cần listener SessionMapping, encoding,
// đúng URL logout callback, và CAS auth filter.
```

**Không đồng thời** đăng ký một `SingleSignOutFilter` ở Servlet container và một instance trong Spring chain. Việc chạy hai lần có thể đọc body/ticket hai lần, ghi duplicate mapping hoặc invalidation nhầm, rất khó chẩn đoán.

### 6.3. `LogoutFilter` không phải `SingleSignOutFilter`

- **Spring `LogoutFilter`:** xử lý **local logout** ở `POST /logout` với các `LogoutHandler`, bao gồm invalidate HttpSession, clear SecurityContext, CSRF cleanup.
- **Apereo `SingleSignOutFilter`:** nhận **CAS protocol SLO notifications**, tra ticket→HttpSession và invalidate session đó.
- **Spring `CasAuthenticationFilter`:** nhận CAS Service Ticket sau login, gọi CAS Server để validate rồi tạo Authentication.
- **`CsrfFilter`:** chống cross-site request forgery cho unsafe HTTP methods khi request đi qua nó, trừ rule được miễn.
- **`AuthorizationFilter`:** phân quyền sau authentication; `permitAll` không giúp request vượt qua CsrfFilter nếu nó đã bị từ chối trước.

Không chuyển một `POST logoutRequest` của CAS thành POST `/logout` browser để “tái sử dụng” LogoutFilter; sẽ làm mất ticket–session correlation và có nguy cơ logout sai session.

## 7. CSRF: khi nào phải miễn và miễn chính xác cái gì?

### 7.1. Vì sao CAS không có CSRF token của ứng dụng?

`CsrfFilter` dùng CSRF token gắn với browser session/cookie khi ứng dụng xử lý các POST do browser gửi. Back-channel CAS SLO đến từ **CAS HTTP client** trên server khác, thường không biết `JSESSIONID` hoặc CSRF token của user trên App A. Nếu ép CAS gửi `_csrf` của phiên A, nó không thể làm được.

Bởi vậy chỉ có hai cách đúng:

- **SLO filter xử lý trước CsrfFilter**: không cần riêng một quy tắc ignore CSRF trong Spring Security.
- **SLO POST bắt buộc đi qua CsrfFilter** do kiến trúc: miễn đúng **method + endpoint** thực sự nhận CAS, và áp dụng kiểm tra nguồn/protocol riêng.

**Không có cơ sở để làm:** `http.csrf(csrf -> csrf.disable())` cho toàn web app chỉ vì CAS SLO. Điều đó mở nguy cơ CSRF ở `/logout` browser, sửa hồ sơ, chuyển tiền, thay role và các POST khác.

### 7.2. Phạm vi miễn theo method và exact path

Nếu CAS registered-service dùng `logoutUrl=https://app.example.org/cas/slo`, matcher hẹp nên là:

```text
POST /cas/slo        --> không bắt CSRF token browser,
                        nhưng CHỈ SLO protocol handler được xử lý
POST /logout         --> PHẢI có CSRF token
POST /api/orders     --> PHẢI có CSRF token nếu API dùng cookie session
POST /cas/slo-extra  --> PHẢI có CSRF token
PUT  /cas/slo        --> PHẢI có CSRF token
GET  /cas/slo        --> không yêu cầu CSRF theo mặc định,
                        nhưng KHÔNG được xử lý như SLO POST
```

Nếu đang dùng callback mặc định `POST /login/cas`, chỉ miễn `POST /login/cas` khi đã xác nhận CAS Server thực sự gửi SLO tới đó. **GET /login/cas?ticket=ST` là CAS login callback**, không cần mở thêm CSRF exception vì GET không thuộc unsafe methods mặc định.

### 7.3. Spring Security 6.x: đoạn cấu hình ignore **chỉ khi cần**

Trong ứng dụng có `HttpSecurity http`, nếu một SLO handler hợp lệ phải đi **qua `CsrfFilter` trước khi được xử lý**, có thể dùng `RequestMatcher` giới hạn phương thức và đường dẫn:

```java
import org.springframework.security.web.util.matcher.RequestMatcher;

// Đường local bên trong servlet context, không chứa query string.
// Chỉ dùng khi CAS thực sự gửi back-channel SLO tới /cas/slo.
RequestMatcher casSloPost = request ->
    "POST".equals(request.getMethod())
        && "/cas/slo".equals(request.getServletPath());

http.csrf(csrf -> csrf.ignoringRequestMatchers(casSloPost));
```

Nếu dùng Ant matcher trong Spring Security 6.x, mô hình tương đương là:

```java
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

http.csrf(csrf -> csrf.ignoringRequestMatchers(
    new AntPathRequestMatcher("/cas/slo", "POST")));
```

Hai đoạn là **hai cách lựa chọn một**, không cần dùng đồng thời. Spring Security 7.x có migration sang API `PathPatternRequestMatcher`; kiểm tra version/Javadoc thay vì copy class deprecated không biên dịch. Nếu Servlet mapping khác `/` hoặc có context path, xác minh `request.getServletPath()` và matcher thực tế bằng integration test.

**Lưu ý:** Mẫu chính ở mục 8 sẽ đăng ký SLO filter **trước Spring Security**, vì vậy **không cần** dòng `csrf.ignoringRequestMatchers(...)` trong `SecurityFilterChain` đó. Đừng thêm cả hai chỉ vì “phải có exemption”: một exemption thừa sẽ tạo bề mặt không được bảo vệ nếu filter không chạy.

### 7.4. `permitAll` không phải CSRF exemption

Hai dòng:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/cas/slo").permitAll())
.csrf(csrf -> csrf.ignoringRequestMatchers(casSloPost))
```

giải quyết hai bài toán **khác nhau**:

1. `permitAll`: nếu request đi tới `AuthorizationFilter`, không cần Authentication browser tại endpoint ấy.
2. `ignoringRequestMatchers`: nếu request đi qua `CsrfFilter`, **không yêu cầu CSRF token browser** cho matcher đó.

Nếu CAS request bị CsrfFilter chặn ở đầu chain, `permitAll` **không giúp**. Ngược lại, nếu CAS request bypass CsrfFilter nhưng bị authorization rule `authenticated()` chặn, cần sửa policy/handler theo kiến trúc.

**Không đồng nghĩa “anonymous được phép hủy session”.** Một endpoint SLO phải thực thi giao thức đúng và được kiểm tra nguồn/correlation, không chỉ trả 200 cho mọi POST bất kỳ.

### 7.5. CSRF exemption không phải bằng chứng authenticity

Việc exempt một `POST /cas/slo` khỏi CSRF token **không làm thông báo đáng tin**. Callback cần defense-in-depth:

- Chỉ CAS Server/ingress được phê duyệt có thể gửi theo policy, có thể dùng mTLS/network policies/allowed source CIDR khi phù hợp.
- Chấp nhận đúng `Content-Type`, method, request size, encoding, tên `logoutRequest`; không parse XML tùy tiện bằng bộ parser XXE-unsafe tự viết.
- Dùng Apereo Java CAS Client đã được cập nhật và triển khai theo contract. **Không mặc nhiên cho rằng mọi biến thể logoutRequest đều có chữ ký được xác minh**; kiểm xem server/client thực hỗ trợ kiểm xác thực message ở cấp protocol nào.
- Không lấy `SessionIndex` từ XML chưa kiểm soát rồi tùy tiện invalidate mọi user sessions.
- Ràng buộc ticket đã được ghi nhận lúc CAS login với local HttpSession, tenant/registration và CAS source phù hợp.
- Rate limit/audit các request bất thường, chống logout denial-of-service (logout CSRF mở rộng).
- Ngăn request giả từ browser tới SLO endpoint bằng network boundary khi có thể; nếu SLO endpoint phải public, dùng policy xác thực nguồn phù hợp và không chứa thông tin nhạy cảm trong phản hồi.
- Luôn giữ CSRF cho `POST /logout` của user và tất cả business actions dựa trên cookie session.

**Không coi `Origin`/`Referer` vắng mặt là dấu hiệu chắc chắn đến từ CAS Server**: server-side HTTP client có thể không gửi chúng, và attacker cũng có thể giả mạo headers ngoài browser.

## 8. Ví dụ Spring Boot 3.x: SLO Servlet filter đứng trước Spring Security

Ví dụ này chọn **phương án A**: Apereo `SingleSignOutFilter` là **Servlet filter** đứng trước `springSecurityFilterChain`; `CasAuthenticationFilter` là **Spring Security filter**. Đây là kiến trúc dễ kiểm tra và giữ CSRF cho các request thông thường.

### 8.1. Dependencies và điều kiện build

Trong dự án Spring Boot 3.x quản lý dependencies bằng BOM, Java 17+, thêm:

```xml
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
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-cas</artifactId>
  </dependency>
</dependencies>
```

Đây là fragment `pom.xml`, không phải POM độc lập. `spring-security-cas` sử dụng Apereo Java CAS Client; vì Spring Boot 3.x dùng **`jakarta.servlet`**, phải chọn artifact/client version có Jakarta Servlet API tương thích. Kiểm:

```bash
./mvnw dependency:tree
./mvnw test
```

Đừng trộn một `SingleSignOutFilter` biên dịch cho `javax.servlet.Filter` cũ với Spring Boot 3 Jakarta rồi ép cast; nếu version không phù hợp, nâng CAS Client/Spring BOM theo hướng dẫn tương thích. Không đặt nhiều phiên bản `java-cas-client` vào classpath.

### 8.2. Cấu hình URLs ở `application.yml`

```yaml
server:
  port: 8080
  forward-headers-strategy: framework
  servlet:
    session:
      timeout: 30m
      cookie:
        secure: true
        http-only: true
        same-site: lax

app:
  cas:
    server-base-url: https://sso.example.org/cas
    login-url: https://sso.example.org/cas/login
    service-url: https://app.example.org/login/cas
    slo-path: /cas/slo
```

**Giả định:** App public qua reverse proxy HTTPS 443, backend HTTP port 8080, CAS Server đã đăng ký `service-url` để login và `logoutUrl=https://app.example.org/cas/slo` để gửi back-channel SLO. Domain `example.org` chỉ minh họa, không phải môi trường CAS sẵn chạy.

`forward-headers-strategy` chỉ an toàn nếu proxy **xóa/ghi đè** forwarded headers từ client rồi mới chuyển vào Spring. Dù vậy, tốt nhất đặt `service-url` và `logoutUrl` trong cấu hình tin cậy cố định, không dựng bằng raw `Host`/`X-Forwarded-Host`.

### 8.3. Đăng ký SLO filter và session listener ở cấp Servlet

File `src/main/java/com/example/caslogout/CasSloServletConfig.java`:

```java
package com.example.caslogout;

import org.apereo.cas.client.session.SingleSignOutFilter;
import org.apereo.cas.client.session.SingleSignOutHttpSessionListener;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletListenerRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
public class CasSloServletConfig {

    @Bean
    FilterRegistrationBean<SingleSignOutFilter>
            casSingleSignOutFilterRegistration() {

        SingleSignOutFilter filter = new SingleSignOutFilter();

        FilterRegistrationBean<SingleSignOutFilter> reg =
            new FilterRegistrationBean<>(filter);

        reg.setName("casSingleSignOutFilter");
        // Bao trùm ticket-bearing login requests + CAS SLO callback.
        reg.addUrlPatterns("/*");

        // Cụ thể hóa endpoint nhận logoutRequest.
        // Đảm bảo CAS Server registered-service gửi tại /cas/slo.
        reg.addInitParameter("logoutCallbackPath", "/cas/slo");

        // Servlet filter phải thực sự chạy trước
        // springSecurityFilterChain / DelegatingFilterProxy.
        reg.setOrder(Ordered.HIGHEST_PRECEDENCE + 20);
        return reg;
    }

    @Bean
    ServletListenerRegistrationBean<SingleSignOutHttpSessionListener>
            casSingleSignOutSessionListener() {
        return new ServletListenerRegistrationBean<>(
            new SingleSignOutHttpSessionListener());
    }
}
```

**Giải thích:**

- `FilterRegistrationBean` chỉ có một filter instance. **Không** khai báo thêm `@Bean SingleSignOutFilter` rồi cũng gọi `http.addFilterBefore`; tránh duplicate registration.
- `addUrlPatterns("/*")` để filter quan sát **GET mang `ticket`** khi browser trở lại từ CAS và **POST mang `logoutRequest`** do CAS gửi. Dùng chỉ `/cas/slo` sẽ bỏ mất ticket–session mapping nếu client mặc định phụ thuộc vào tracking của filter trên callback login.
- `logoutCallbackPath=/cas/slo` yêu cầu CAS client nhận dạng logout request trên endpoint được định nghĩa. Kiểm behavior/matcher của Apereo Client version thực tế, đặc biệt khi có servlet context path.
- `Ordered.HIGHEST_PRECEDENCE + 20` là một mức ưu tiên **rất sớm**, thường trước `springSecurityFilterChain` của Boot; không đủ để khẳng định thứ tự trong mọi custom bootstrap. Phải **xem filter registration/order thực tế và test POST SLO**.
- `SingleSignOutHttpSessionListener` cleanup mapping khi HttpSession hết hạn; không tự xác minh ticket, và không nhận SLO request nếu filter thiếu.
- `CharacterEncodingFilter` nên chạy sớm/được Boot cấu hình UTF-8; kiểm encoding với POST SLO XML form, không khởi tạo thêm một filter encoding trùng lặp nếu Boot đã cung cấp.
- Endpoint SLO không cần MVC controller. `SingleSignOutFilter` xử lý request; một controller trả `200` đơn thuần **không** xác nhận session đã invalidate.
- CAS callback thường là một POST từ server không có browser cookie; filter sớm cần đủ quyền truy cập mapping session trong process/cluster.

**Lưu ý version:** Tên class và init parameter nêu trên thuộc Apereo Java CAS Client; các version khác nhau có thể thay đổi kiểu Servlet API, callback handling hoặc parser. Các ví dụ là mã nguồn cho một Spring Boot project đã có dependencies và CAS test server; không biên dịch bằng `javac` thuần.

### 8.4. CAS login filter và Spring Security logout cùng tồn tại

File `src/main/java/com/example/caslogout/CasWebSecurityConfig.java`:

```java
package com.example.caslogout;

import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.apereo.cas.client.validation.TicketValidator;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class CasWebSecurityConfig {

    @Bean
    ServiceProperties serviceProperties(
        @Value("${app.cas.service-url}") String service) {
        ServiceProperties props = new ServiceProperties();
        props.setService(service);
        props.setSendRenew(false);
        return props;
    }

    @Bean
    TicketValidator ticketValidator(
        @Value("${app.cas.server-base-url}") String casBase) {
        return new Cas20ServiceTicketValidator(casBase);
    }

    @Bean
    UserDetailsService userDetailsService() {
        // Chỉ là user fixture của phòng lab CAS.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}unused-by-cas")
                .roles("USER")
                .build());
    }

    @Bean
    CasAuthenticationProvider casAuthenticationProvider(
        ServiceProperties props,
        TicketValidator validator,
        UserDetailsService users) {

        CasAuthenticationProvider provider =
            new CasAuthenticationProvider();
        provider.setServiceProperties(props);
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(users);
        provider.setKey("cas-slo-example-v1");
        return provider;
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SecurityFilterChain casWeb(
        HttpSecurity http,
        ServiceProperties props,
        CasAuthenticationProvider provider,
        SecurityContextRepository contextRepository,
        @Value("${app.cas.login-url}") String casLoginUrl)
            throws Exception {

        CasAuthenticationEntryPoint entryPoint =
            new CasAuthenticationEntryPoint();
        entryPoint.setLoginUrl(casLoginUrl);
        entryPoint.setServiceProperties(props);

        CasAuthenticationFilter casFilter =
            new CasAuthenticationFilter();
        casFilter.setServiceProperties(props);
        casFilter.setFilterProcessesUrl("/login/cas");
        casFilter.setAuthenticationManager(
            new ProviderManager(provider));
        casFilter.setSecurityContextRepository(contextRepository);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error",
                    "/signed-out").permitAll()
                .requestMatchers("/reports/**").hasRole("USER")
                .anyRequest().authenticated())

            // Giữ CSRF mặc định cho POST /logout và web forms.
            // SLO POST đã được Servlet SingleSignOutFilter xử lý
            // trước khi đến Spring Security chain.
            .csrf(Customizer.withDefaults())

            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint))
            .securityContext(context -> context
                .securityContextRepository(contextRepository))
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/signed-out")
                .invalidateHttpSession(true)
                .clearAuthentication(true));

        // CAS auth filter chỉ đăng ký trong SecurityFilterChain.
        http.addFilterAt(casFilter, CasAuthenticationFilter.class);
        return http.build();
    }
}
```

**Những gì cấu hình này bảo đảm và không bảo đảm:**

- `CasAuthenticationFilter` xử lý Service Ticket từ browser tại `GET /login/cas?ticket=...`, dùng provider để validate ticket qua CAS Server.
- `SingleSignOutFilter` của Apereo ở tầng Servlet nhìn thấy ticket-bearing request trước rồi có thể ghi mapping tới session; khi CAS gửi SLO, nó tra và invalidate session.
- Spring `LogoutFilter` giữ local logout với CSRF theo mặc định; `POST /logout` phải chứa token CSRF đúng nếu người dùng logout từ trình duyệt.
- `HttpSessionSecurityContextRepository` lưu local Authentication theo session; việc session bị invalidate sẽ khiến request tiếp theo không còn authenticated.
- Không có `csrf.disable()` và cũng **không có CSRF ignore** vì SLO filter đã chạy trước CsrfFilter.
- Không có `@GetMapping("/cas/slo")` hay `@PostMapping("/cas/slo")`; nếu SLO filter không xử lý đúng, việc còn lại có thể là 401/404/403 — đó là lỗi cần sửa, không phải lúc tạo controller “200 OK”.
- `alice` với `{noop}unused-by-cas` chỉ là fixture để demo local roles; xác thực mật khẩu thực sự diễn ra trên CAS Server. Production dùng user repository/tenant authorization thật.
- Cấu hình **không tự redirect browser đến CAS `/logout`** sau local logout. Cần một quyết định UX/policy riêng về global logout (mục 11).
- Nếu app đã có `SecurityFilterChain` khác, phải tích hợp thay vì tạo hai chains đều match toàn bộ request; bảo đảm callback ticket và business URLs thuộc chain phù hợp.

### 8.5. Spring Boot application và trang minh họa

File `src/main/java/com/example/caslogout/CasSloDemoApplication.java`:

```java
package com.example.caslogout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CasSloDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CasSloDemoApplication.class, args);
    }
}
```

File `src/main/java/com/example/caslogout/DemoController.java`:

```java
package com.example.caslogout;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of("message", "Public CAS SLO demo");
    }

    @GetMapping("/reports")
    public Map<String, String> reports(Authentication user) {
        return Map.of("message", "Protected data",
                      "user", user.getName());
    }

    @GetMapping("/signed-out")
    public Map<String, String> signedOut() {
        return Map.of("status", "Local application logout done");
    }
}
```

Endpoint SLO `/cas/slo` **không có controller**. Trang `/signed-out` chỉ xác nhận **local logout**, không khẳng định CAS Server hoặc mọi app đã hủy sessions.

### 8.6. Điều kiện thực nghiệm để ví dụ hoạt động

Ngoài project đã biên dịch, cần:

1. CAS Server HTTPS hoạt động, chứng chỉ do client JVM tin.
2. CAS user test `alice` và registered service `https://app.example.org/login/cas`.
3. Registered service cho back-channel SLO với `logoutUrl=https://app.example.org/cas/slo`; nếu không hỗ trợ custom URL, thay thiết kế/matcher theo default `/login/cas`.
4. CAS Server truy cập được App A callback từ pod/VM thực; ingress forward POST/body đúng.
5. Spring Boot được expose qua HTTPS đúng public host, browser giữ session cookie.
6. `SingleSignOutFilter`/listener dependency đúng Jakarta Servlet API; log thứ tự filter cho thấy nó chạy trước Spring Security.
7. User Details fixture có đúng username được CAS phát.
8. Có test browser và CAS Server logs để xác định mapping ticket→session/invalidate, không chỉ thấy CAS logout page.

## 9. Khi dùng endpoint mặc định `/login/cas` cho cả login và SLO

Không phải CAS Server nào cũng có registered `logoutUrl` riêng; trường hợp mặc định thường POST `/login/cas`.

Nếu **phương án Servlet filter sớm** ở mục 8 được giữ nguyên, đổi:

```java
reg.addInitParameter("logoutCallbackPath", "/login/cas");
```

Và xác định registered-service gửi SLO đến đúng `https://app.example.org/login/cas`. **Không cần bỏ CSRF** vì SLO filter vẫn chạy trước Spring Security. Browser `GET /login/cas?ticket` tiếp tục dùng CAS auth filter; CAS `POST /login/cas` được SLO filter nhận.

Nếu **phương án SLO handler nằm sau CsrfFilter** đang được triển khai, matcher exempt phải là:

```java
RequestMatcher casSloPost = request ->
    "POST".equals(request.getMethod())
      && "/login/cas".equals(request.getServletPath());

http.csrf(csrf -> csrf.ignoringRequestMatchers(casSloPost));
```

**Không miễn toàn `/login/**`**, không miễn `GET /login/cas` vì GET vốn không cần token theo mặc định, và không miễn bất cứ request nào có query parameter `logoutRequest` ở path bất kỳ. Đặt giới hạn method + exact callback path phù hợp với CAS config đã quan sát được.

## 10. Đăng nhập ghi mapping ở đâu? Filter order và session fixation

Với phiên Servlet hiện đại, Spring Security thường kích hoạt **session fixation protection** (ví dụ `changeSessionId` sau login). Vì CAS SLO sử dụng tham chiếu HttpSession, cần kiểm test mapping trong đúng lifecycle:

```text
GET /login/cas?ticket=ST-1
    |
SingleSignOutFilter lưu ST-1 -> HttpSession object
    |
CasAuthenticationFilter validate ticket
    |
Spring Security session fixation strategy (change session id)
    |
App session authenticated và tiếp tục sử dụng
    |
CAS POST /cas/slo, SessionIndex=ST-1
    |
SingleSignOutFilter tra mapping
    |
invalidate đúng HttpSession đã authenticated
```

Nếu config đổi từ `changeSessionId` sang `newSession`/`migrateSession`, hoặc application tái tạo session theo custom code, mapping có thể không còn tham chiếu tới session cuối cùng nếu integration không cập nhật. **Không tắt session fixation protection chỉ để SLO hoạt động**; điều đúng là kiểm chiến lược fixation, test session identity và dùng library/session mapper tương thích.

### 10.1. Lỗi hiển thị “SLO nhận 200 nhưng user vẫn login”

Các khả năng:

- SLO callback filter trả 200 nhưng **không tìm được ST trong SessionMappingStorage**.
- Filter chỉ map `/cas/slo` nên không bắt được `GET /login/cas?ticket=...` để tạo mapping.
- CAS Server gửi `SessionIndex` không tương ứng ST mà client lưu.
- Local HttpSession sau authentication đã đổi theo cách mapping không bám theo.
- User có **một session khác** trên browser/tab/node hoặc vừa SSO lại sau khi session bị invalidate.
- Cùng account có nhiều local sessions; SLO message chỉ nhắm tới những session liên quan với ticket đó.
- Browser đang hiển thị HTML cũ trong cache, nhưng request tiếp theo đã không authenticated.
- CAS request vào node B trong khi map ở node A; storage không shared.
- Reverse proxy nhận 200 từ một endpoint giả (MVC/WAF) thay vì SLO filter.

**Bằng chứng phải thu:** local HttpSession ID đã được pseudonymize, ticket correlation ID dạng hash/trace không tiết lộ raw ST, event invalidate, HTTP request mới tới resource, kết quả auth server; không chỉ nhìn trang “logged out” hoặc HTTP 200.

## 11. Local logout và “logout mọi ứng dụng”: thứ tự thao tác UX

Spring Security `POST /logout` thường:

- Invalidate local `HttpSession`.
- Clear `SecurityContextHolder` và context repository.
- Dọn CSRF/remember-me state theo `LogoutHandler`.
- Redirect tới local logout success page hoặc URL được cấu hình.

**Không tự hủy CAS TGT/TGC**. Do đó nếu user ngay lập tức quay lại một URL bảo vệ, CAS SSO session còn có thể phát **ST mới** và ứng dụng login lại. Đây không phải tự động lỗi local logout.

Muốn kết thúc CAS SSO:

```text
(1) Browser POST /logout tại App A
    kèm CSRF token của App A
    => A session invalidated

(2) App chuyển browser đến CAS /cas/logout
    bằng URL server-side fixed/đã duyệt
    => CAS TGT/TGC kết thúc

(3) CAS gửi SLO notifications tới các services đã xác thực
    => Các CAS clients dùng SLO filter invalidates local sessions

(4) Browser đến signed-out page phù hợp;
    không tuyên bố mọi service đã logout nếu SLO có lỗi.
```

Có thể cho người dùng chọn **“Đăng xuất khỏi ứng dụng này”** và **“Đăng xuất khỏi SSO”** tùy policy. Nếu tự động redirect đến CAS logout sau local POST, phải bảo đảm URL cố định hoặc logout post-redirect service đã đăng ký; **không nhận `?returnTo=https://evil...`** thành open redirect.

### 11.1. Vì sao Spring reference có thêm một `LogoutFilter` trước LOGOUT_FILTER?

Tài liệu CAS của Spring Security đưa ví dụ XML cũ đặt một `requestSingleLogoutFilter` để redirect browser đến CAS logout endpoint, cùng `singleLogoutFilter` nhận thông báo từ CAS. Đây là **hai chức năng khác**:

1. Browser request local/global logout để yêu cầu CAS Server kết thúc SSO.
2. CAS Server gửi logoutRequest trở lại ứng dụng để thông báo cần invalidate session.

**Không copy cơ học thứ tự filter XML cũ sang Spring Boot 3.x** nếu không kiểm thứ tự `CsrfFilter` và điều kiện POST CSRF. Tùy app, có thể triển khai browser redirect qua `LogoutSuccessHandler` an toàn hoặc trang success có liên kết CAS logout, thay vì tự bổ sung một `LogoutFilter` không rõ matcher.

### 11.2. Không nhận SLO message qua `POST /logout`

`POST /logout` là browser action có CSRF token. CAS back-channel SLO mang `logoutRequest` có SessionIndex, không có local browser cookie/CSRF. Trộn cả hai ở một endpoint làm giảm khả năng giới hạn exemptions và có thể mở logout CSRF/DoS. Nếu CAS Server có `logoutUrl` riêng, chọn `/cas/slo` như ví dụ. Nếu buộc dùng `/login/cas` mặc định, vẫn tách khỏi `/logout` browser.

## 12. Bảo vệ endpoint nhận SLO không dùng CSRF browser

CSRF là một lớp bảo vệ cho **browser cookie workflows**; CAS SLO back-channel cần cơ chế tin cậy **server-to-server**.

### 12.1. Network và TLS

- CAS Server gọi `https://app.example.org/cas/slo` qua HTTPS; certificate/hostname/trust chain phải hợp lệ ở phía CAS HTTP client.
- Tại ingress, chỉ cho route `POST /cas/slo` tới service handler đúng, giữ form body; không cho request từ unknown service mạng tùy ý nếu có thể giới hạn.
- Khi triển khai sau CDN/WAF, đừng để CAPTCHA/bot challenge hoặc trang login thay thế callback.
- mTLS hoặc private networking với CAS là lựa chọn tăng độ tin cậy khi client/server hỗ trợ; không tuyên bố Apereo Java CAS Client mặc định kiểm mTLS trên SLO.
- IP allowlist cần xét NAT/egress gateway/HA/DR của CAS, không phụ thuộc duy nhất header do client đưa. CAS origin đôi khi là tập nhiều node.
- Bảo đảm proxy không ghi raw `logoutRequest` vào access log hoặc analytics; XML có thể chứa NameID/SessionIndex nhạy cảm.
- Đặt request body size/timeouts phù hợp để giảm XML DoS, giới hạn lượng callback bất thường.

### 12.2. Tính toàn vẹn và xác thực thông báo

Một SAML-style LogoutRequest trong CAS protocol **không mặc nhiên tương đương** một SAML 2.0 Single Logout request có chữ ký được framework SAML xác minh. Không suy rằng chỉ cần body có XML `LogoutRequest` là đáng tin.

Cần xác định rõ trong phiên bản CAS Server + Java CAS Client:

1. Filter hỗ trợ cơ chế kiểm integrity/authenticity nào đối với SLO payload?
2. Có validate `Issuer`, destination, time, XML signature (nếu profile/sản phẩm yêu cầu) hay không?
3. Có quản lý replay/deduplication, mapping ST→session và phạm vi tenant/issuer không?
4. Có thể hạn chế ingress source hoặc dùng mTLS để xác thực CAS Server không?
5. Request giả cùng `SessionIndex` đã biết có thể gây logout DoS không, và cách ngăn?
6. Callback có dùng đúng registered-service `logoutType=BACK_CHANNEL` và URL approved không?

**Không tự viết parser XML với XXE enabled**, không lấy một chuỗi SessionIndex do browser gửi rồi gọi `session.invalidate()` trên những session tùy ý. Nếu phiên bản Apereo Java CAS Client thiếu authentication/integrity cần thiết cho một threat model nghiêm ngặt, cân nhắc lớp xác thực mạng/mTLS hoặc thiết kế một protocol profile khác hỗ trợ signed logout notifications đã được thỏa thuận, không bỏ qua yêu cầu bảo mật.

### 12.3. Không cho một CAS Server của tenant A hủy phiên tenant B

Trong ứng dụng multi-tenant/multi-CAS:

- Mỗi CAS Server có trust domain/registered-service/callback policy riêng.
- Một `SessionIndex` có thể không đủ để phân biệt nếu mapping không namespace CAS source, application, tenant và ticket.
- Nếu một user thuộc nhiều tenants, SLO của một CAS issuer không tự phải hủy tất cả sessions ở các issuers khác.
- Admin tắt account ở tenant A cần policy revocation theo tenant; đừng đồng nhất với global logout mọi account.
- Không dùng global static map mà không có kế hoạch HA/isolation.
- Khi callback không nêu registrationId riêng, dùng source routing và verified CAS trust từ ingress/server configuration để xác định context, không từ email, raw Host hoặc untrusted XML.

## 13. Java 17 chạy độc lập: kiểm phạm vi CSRF và thứ tự xử lý

Ví dụ sau là **mô hình logic** chạy bằng JDK 17, không phụ thuộc Spring/CAS. Nó không nhận ST thật, không parse SAML, không kiểm TLS, không invalidate HttpSession production; nó chỉ cho thấy vì sao **chỉ POST đúng endpoint SLO** được exempt CSRF và **SLO filter chạy trước CSRF** vẫn giữ nguyên bảo vệ local logout.

File `SloCsrfBoundaryDemo.java`:

```java
public final class SloCsrfBoundaryDemo {

    record Request(String method, String servletPath,
                   boolean csrfTokenValid) { }

    static boolean safeMethod(String method) {
        return "GET".equals(method) || "HEAD".equals(method)
            || "OPTIONS".equals(method) || "TRACE".equals(method);
    }

    static boolean isBackChannelSloPath(Request request) {
        return "POST".equals(request.method())
            && "/cas/slo".equals(request.servletPath());
    }

    // Mô phỏng chiến lược B: nếu request đi qua CsrfFilter,
    // bỏ yêu cầu CSRF token chỉ cho POST /cas/slo.
    static boolean csrfRequired(Request request) {
        return !safeMethod(request.method())
            && !isBackChannelSloPath(request);
    }

    // trustedCasMessage là một giả định của mô hình.
    // Trong hệ thống thật, cần lớp xác thực nguồn/protocol.
    static String dispatch(Request request,
                           boolean trustedCasMessage) {

        // Tượng trưng SingleSignOutFilter ở trước CsrfFilter.
        if (isBackChannelSloPath(request) && trustedCasMessage) {
            return "SLO_HANDLED";
        }

        if (csrfRequired(request) && !request.csrfTokenValid()) {
            return "CSRF_403";
        }

        if ("POST".equals(request.method())
                && "/logout".equals(request.servletPath())) {
            return "LOCAL_LOGOUT";
        }

        // Request không được coi là logout nếu không đúng
        // endpoint/method; các route thật còn cần authorization.
        return "NOT_LOGOUT";
    }

    public static void main(String[] args) {
        Request slo = new Request(
            "POST", "/cas/slo", false);
        Request local = new Request(
            "POST", "/logout", false);
        Request localValid = new Request(
            "POST", "/logout", true);
        Request near = new Request(
            "POST", "/cas/slo-extra", false);
        Request wrongMethod = new Request(
            "PUT", "/cas/slo", false);
        Request getSlo = new Request(
            "GET", "/cas/slo", false);

        System.out.println("sloExempt=" + !csrfRequired(slo));
        System.out.println("localExempt=" + !csrfRequired(local));
        System.out.println("nearExempt=" + !csrfRequired(near));
        System.out.println("putExempt=" + !csrfRequired(wrongMethod));

        System.out.println("slo=" + dispatch(slo, true));
        System.out.println("localMissingCsrf=" +
            dispatch(local, false));
        System.out.println("localWithCsrf=" +
            dispatch(localValid, false));
        System.out.println("nearPath=" +
            dispatch(near, false));
        System.out.println("putOnSloPath=" +
            dispatch(wrongMethod, false));
        System.out.println("getSlo=" +
            dispatch(getSlo, false));
        System.out.println("untrustedSlo=" +
            dispatch(slo, false));
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac --release 17 SloCsrfBoundaryDemo.java
java SloCsrfBoundaryDemo
```

Kết quả stdout **xác định**:

```text
sloExempt=true
localExempt=false
nearExempt=false
putExempt=false
slo=SLO_HANDLED
localMissingCsrf=CSRF_403
localWithCsrf=LOCAL_LOGOUT
nearPath=CSRF_403
putOnSloPath=CSRF_403
getSlo=NOT_LOGOUT
untrustedSlo=NOT_LOGOUT
```

**Giải thích kết quả:**

- Chỉ `POST /cas/slo` được thiết kế có CSRF exception; `POST /cas/slo-extra`, `PUT /cas/slo` và `POST /logout` đều không.
- `slo=SLO_HANDLED` giả định callback **đã qua kiểm nguồn/protocol**; đây là mô phỏng bộ lọc giao thức, không chứng minh callback HTTP có thật là CAS.
- Browser `POST /logout` thiếu CSRF bị từ chối; có CSRF token thì được thực hiện local logout.
- `GET /cas/slo` vốn là safe method nên không cần CSRF nhưng **không được xử lý như SLO POST**.
- `untrustedSlo` trong demo trả `NOT_LOGOUT` dù được exempt CSRF; **không được hiểu là thực tế Apereo filter tự kiểm mọi chứng thực tương đương**. Production phải dùng network/integrity controls và contract của thư viện.
- Trong **phương án Servlet filter sớm**, callback SLO được xử lý trước CsrfFilter nên không cần CSRF exception. `csrfRequired()` mô tả **phương án B**, giúp hiểu ranh giới nếu phải cấu hình ngoại lệ.

**Về runnable:** Đây là chương trình Java 17 độc lập với `record`, không có dependency bên ngoài. Mã Spring ở mục 8 cần dependency Spring Boot/Security/Apereo; không chạy bằng `javac` thuần khi thiếu classpath.

## 14. Ma trận kiểm thử: phải xác nhận session thật bị thu hồi

### 14.1. Trường hợp thành công

| Test | Bước kiểm | Kết quả cần thấy |
| --- | --- | --- |
| CAS login tạo mapping | User login, browser GET `/login/cas?ticket=ST-...` | SLO filter đã quan sát request và mapping tới HttpSession thật |
| Back-channel CAS SLO | Kết thúc TGT tại CAS Server, CAS POST `/cas/slo` | Filter nhận và invalidate đúng app session |
| Session không còn dùng được | Sau SLO, dùng browser session cookie cũ GET API bảo vệ | Không trả dữ liệu cũ, bắt đầu auth mới hoặc 401/302 theo policy |
| Local logout có CSRF | Browser POST `/logout` kèm token | Local session invalidated; không lỗi 403 |
| Local logout không CSRF | Browser POST `/logout` không token | 403, không tự xử lý logout |
| CAS không có browser cookie | CAS HTTP client gửi POST SLO không kèm JSESSIONID | SLO vẫn xử lý nhờ ticket→session mapping |
| Callback chuyên dụng | CAS registered-service `logoutUrl=/cas/slo` | Thực sự gửi tới đúng URL, không phải mặc định `/login/cas` |
| Cleanup listener | Local session timeout/invalidate | Entry mapping được dọn theo listener |
| Multi-node | Login tại pod A, SLO callback đến pod B | Có shared mapping hoặc cơ chế đưa invalidate đến đúng session owner |
| Front channel nếu được dùng | CAS configured FRONT_CHANNEL và Java client support | Browser flow được xử lý đúng; không suy tự hoạt động |
| Logout 2 lần | CAS gửi duplicate notification | Không invalidate sai phiên khác, xử lý idempotent/benign |
| Cùng user 2 sessions | User login từ hai browser riêng | Phạm vi sessions bị hủy theo CAS event/policy, không hủy nhầm ngoài phạm vi |

### 14.2. Trường hợp thất bại cần cô lập

| Kịch bản | Kỳ vọng bảo mật | Chẩn đoán |
| --- | --- | --- |
| SLO filter đăng ký sau Spring Security | CAS POST không CSRF bị 403 | Kiểm Servlet Filter order, đặt SLO trước chain |
| SLO filter chỉ map `/cas/slo` | Không có mapping từ GET `/login/cas?ticket` | Map filter `/*` nhưng giới hạn logoutCallbackPath |
| Registered-service chưa đặt logoutUrl | CAS POST vào `/login/cas`, không phải `/cas/slo` | Đối chiếu service registry/log CAS |
| `permitAll("/cas/slo")` nhưng CsrfFilter chạy trước | CAS POST vẫn 403 | Dùng filter sớm hoặc exact CSRF matcher, không chỉ permitAll |
| Global `csrf.disable()` | Browser POST actions không còn được bảo vệ | Khôi phục CSRF, chỉ exempt endpoint CAS khi cần |
| `csrf.ignoringRequestMatchers("/**")` | Mọi POST đều exempt | Thu hẹp path+method, dùng integration tests |
| Exempt `/logout` để nhận CAS SLO | Logout CSRF có thể xảy ra | Tách CAS callback và browser logout |
| CAS SLO GET/POST bị WAF block | Không có event ở ứng dụng | Rà soát ingress/payload/method/TLS |
| CAS SLO POST gửi đến HTTP internal URL | CAS không route đúng, rủi ro confidentiality | Dùng public canonical HTTPS URL |
| SessionIndex không khớp | HTTP 200 nhưng session còn | Kiểm ticket→session mapping/actual CAS ST |
| Duplicated SingleSignOutFilter | Không ổn định/đọc body trùng | Chỉ đăng ký một filter ở một tầng |
| Listener không được đăng ký | Mapping stale sau timeout/invalidate | Đăng ký SingleSignOutHttpSessionListener |
| Session fixation tạo session khác | SLO hủy session cũ, authenticated session còn | Test session lifecycle; không tắt fixation |
| Request body form bị chuyển encoding | Không đọc được `logoutRequest` | Bật UTF-8/verify raw form parser & WAF |
| Hai pod, in-memory map | CAS callback tới node không giữ mapping | Thiết kế distributed mapping/target node |
| Callback trả 200 từ MVC fallback | App không invalidate HttpSession | Bỏ controller giả, kiểm Apereo filter được gọi |
| LogoutRequest giả từ internet | Có thể logout DoS nếu ticket lộ/policy yếu | Kiểm nguồn/mTLS/network/signature policy/replay |
| User vừa SSO lại | Browser lại có session mới sau SLO | So session IDs và network redirects, không kết luận SLO hỏng |
| Browser vẫn xem trang cache | Có HTML cũ nhưng APIs đã deny | Reload/request mới, Cache-Control cho dữ liệu nhạy cảm |
| CAS 5/6/7/8 có logout behavior khác | Mismatch path/format/front channel | Khóa version và kiểm docs + actual test |
| CAS as SAML/OIDC broker | Client CAS Filter không xử lý protocol logout khác | Dùng giao thức logout thích hợp |
| Cross-tenant session mapping | SLO tenant A hủy session tenant B | Namespace issuer/service/tenant và authorization checks |

**Không chỉ dựa trên HTTP 200.** Tiêu chí PASS phải gồm **session đã được invalidate**, token/cookie cũ không còn truy cập dữ liệu bảo vệ, mapping được cleanup, không ảnh hưởng sessions khác và browser local logout vẫn giữ CSRF.

### 14.3. Tạo integration tests đúng cách

Với CAS staging:

1. Đăng nhập qua CAS thật để nhận Service Ticket mới, không tự tạo chuỗi `ST-TEST` rồi kỳ vọng CAS validate.
2. Ghi mapping bằng trace ID **không chứa ST thô**.
3. Kết thúc CAS SSO session qua giao diện/endpoint hỗ trợ và quan sát notification CAS phát, không POST XML giả để tự nhận là đã test end-to-end.
4. Xác nhận app session có `SecurityContext` đã bị hủy: GET endpoint bảo vệ với cookie cũ yêu cầu xác thực mới/deny.
5. Kiểm browser tab thứ hai, session B của user khác, sessions khác trong tenant; không được invalidated sai.
6. Thử local POST `/logout` có/không CSRF token và các POST business actions.
7. Thử disabled SLO, network outage, timeout, CAS retry, pod failover, session fixation strategies.
8. Test CAS `logoutUrl` riêng và default `service URL` trên hai cấu hình **khác nhau**, không mix assumption.
9. Đổi forwarded headers/context path/ingress route và chạy lại regression.
10. Đo callback success/failed/silent mismatch và số sessions invalidated, không chỉ đếm logout request.

**Spring Security MockMvc** có thể dùng để kiểm CSRF rule ứng dụng, nhưng **không thay thế** CAS Server end-to-end: `csrf()` test support kiểm POST browser; một POST `logoutRequest` giả với MockMvc chỉ test matcher/filter path, không chứng minh CAS real session mapping và logout authenticity.

## 15. Bảng chẩn đoán vận hành theo hiện tượng

| Dấu hiệu | Có thể do | Hướng xử lý |
| --- | --- | --- |
| User bấm “logout all” nhưng App A vẫn login | CAS SLO không gửi hoặc A không xử lý | Kiểm CAS logoutType, logoutUrl, filter order, mapping |
| CAS ghi SLO POST 200 nhưng session A còn | Filter/controller không invalidate hoặc map miss | Kiểm ST→HttpSession, session fixation và node |
| CAS SLO 403 | CsrfFilter chặn, authorization/gateway, WAF | SLO filter sớm hoặc exact CSRF exemption/permitAll nếu cần, kiểm ingress |
| CAS SLO 404 | CAS gọi sai path hoặc filter không map | Đối chiếu registered logoutUrl/service URL và servlet path |
| CAS SLO 302 sang CAS login | Endpoint bị AuthenticationEntryPoint/gateway yêu cầu login | Cho protocol filter xử lý trước, không cần browser cookie |
| CAS SLO 400/415 | Form encoding/content-type/body parser không tương thích | Dùng `application/x-www-form-urlencoded` theo CAS client, UTF-8 |
| SLO chỉ hoạt động trên một pod | Static mapping trong JVM hoặc sticky routing sai | Distributed session mapping/HA design |
| SLO hủy sai session | Mapping dùng username thay ST/tenant, collision | Kiểm SessionIndex/ST và tenant-aware source scope |
| Local logout 403 | Browser POST thiếu CSRF token | Đọc CSRF token đúng, không tắt CSRF |
| Login loop sau local logout | CAS TGT/TGC còn, ứng dụng SSO lại | Phân biệt local vs CAS global logout |
| Login loop sau SLO | Browser đã SSO lại hoặc session không được invalidate đúng | Kiểm trace request và session ID mới/cũ |
| Chỉ còn thấy trang đã tải | Browser cache | Network refresh và API mới để xác nhận |
| CAS callback không có cookie | Hoàn toàn bình thường với back-channel | Dùng ticket–session map, không đòi JSESSIONID |
| Request `logoutRequest` bất thường | Có thể là scan, giả mạo, replay/DoS | Kiểm nguồn, method/path/size/policy và audit |
| Servlet Filter không xuất hiện trong debug chain | Filter ở tầng Servlet, không thuộc FilterChainProxy | Xem Servlet filter registration/order, không chỉ Spring Security debug |
| Thêm filter bằng `addFilterAt` mà order lạ | Đặt tại vị trí CasAuthenticationFilter hoặc tương đương | Dùng trước CsrfFilter/CAS filter theo kiến trúc, test |
| Token `logoutRequest` bị log | Access log ghi query/form body nhạy cảm | Redact/retention, không log raw |
| Filter chạy hai lần | Double registration ở Servlet và Spring | Loại một registration, kiểm Boot auto-registration |
| Callback đổi từ `/login/cas` sang `/cas/slo` không có tác dụng | CAS registered-service chưa cập nhật `logoutUrl` | Cập nhật registry và test từ CAS Server thật |

### 15.1. Cây quyết định theo request

```text
CAS đã phát SLO notification chưa?
    |
    +-- KHÔNG -> kiểm TGT logout, CAS registered-service,
    |             logoutType, service registry, CAS logs.
    |
    +-- CÓ -> URL/method là gì?
               |
               +-- POST /login/cas  -> CAS default service URL?
               |
               +-- POST /cas/slo    -> CAS logoutUrl riêng?
               |
               +-- GET JSONP       -> FRONT_CHANNEL; client hỗ trợ?
               |
               +-- Không khớp      -> sửa CAS service config.
                         |
                         v
             Request có tới App ingress và Spring?
                         |
             +-- 404/502/network -> route, TLS, WAF, CAS egress.
             |
             +-- 403 -> CsrfFilter hay auth gateway?
                        |
                        +-- CsrfFilter -> SLO filter order/exception hẹp.
                        +-- Gateway -> bypass đúng callback, xác thực nguồn.
             |
             +-- 200 -> SingleSignOutFilter xử lý thật chưa?
                        |
                        +-- Chưa -> controller fake/duplicate/wrong path.
                        |
                        +-- Rồi -> ticket→HttpSession mapping hit?
                                   |
                                   +-- Miss -> callback login, listener,
                                   |          fixation, cluster/storage.
                                   |
                                   +-- Hit -> session.invalidate thực?
                                              |
                                              +-- Có -> test GET API với
                                              |        cookie cũ, kiểm SSO lại.
                                              +-- Không -> sửa client/provider.
```

## 16. Checklist bảo mật/QA trước production

- [ ] Tài liệu kiến trúc phân biệt local `POST /logout`, CAS `/cas/logout` và CAS back-channel SLO callback.
- [ ] `ServiceProperties.service` đúng public CAS login callback; `logoutUrl` riêng được đăng ký nếu dùng `/cas/slo`.
- [ ] `logoutType=BACK_CHANNEL`/`FRONT_CHANNEL` được chọn theo khả năng CAS Server và Java CAS client, có end-to-end test.
- [ ] `SingleSignOutFilter` nhìn thấy cả ticket-bearing login request và SLO notification; registration pattern/order đã xác minh.
- [ ] `SingleSignOutHttpSessionListener` được đăng ký đúng một lần để dọn mappings.
- [ ] Không đăng ký `SingleSignOutFilter` đồng thời ở Servlet và Spring Security chain.
- [ ] Nếu SLO Servlet filter trước Spring chain, không thêm CSRF exemption thừa.
- [ ] Nếu SLO phải đi qua CsrfFilter, chỉ exempt chính xác `POST` + local callback path thực tế; không disable CSRF global.
- [ ] Browser `POST /logout` và mọi hành động có state vẫn bắt buộc CSRF token khi sử dụng cookie session.
- [ ] `permitAll`/`csrf.ignoringRequestMatchers` được hiểu là hai controls khác nhau, áp theo đường filter thực tế.
- [ ] SLO callback không yêu cầu cookie browser; CSRF exemption được bù bằng network/TLS/integrity/session-correlation controls.
- [ ] CAS HTTP client thực sự tới được HTTPS callback, ingress/WAF giữ method/form body/encoding.
- [ ] Không trả 200 giả bằng MVC controller cho request SLO chưa được filter xử lý.
- [ ] Không dùng `logoutRequest` từ query/body chưa được kiểm soát để tự xóa sessions tùy ý.
- [ ] Mapping ST→HttpSession đúng với session fixation strategy và local SecurityContext.
- [ ] Môi trường multi-node có mapping/invalidation phù hợp, cleanup và SLA; test callback tới node không giữ session.
- [ ] Multi-tenant/multi-CAS có isolation giữa issuers/services/tenant memberships.
- [ ] Duplicate/replayed/malformed SLO messages được xử lý an toàn, không hủy nhầm users.
- [ ] Có logging/audit theo event/trace IDs, không ghi raw ST, SessionIndex, SAML LogoutRequest, JSESSIONID hoặc secrets.
- [ ] Test browser local logout có/không CSRF token, SLO POST không có CSRF, wrong path, wrong method và auth gateway.
- [ ] Test SLO từ CAS thật, xác nhận session invalidated và protected API không trả dữ liệu với session cũ.
- [ ] Test IdP SSO/session reuse sau local logout để không nhầm “đăng nhập lại ngay” là SLO fail.
- [ ] CSRF exceptions và filter chain order được review khi nâng Spring Security/CAS Client, đặc biệt Servlet Jakarta và Spring Security 7.
- [ ] Kịch bản HA, certificate rotation, ingress change và CAS outage đều có regression test/runbook.

**Kết luận:** Với **Đăng xuất CAS**, thứ tự bộ lọc quyết định thông báo có được xử lý hay bị Spring Security `CsrfFilter` từ chối. Cấu hình đáng tin cậy cần `SingleSignOutFilter` thấy cả **Service Ticket lúc đăng nhập** và **SLO notification** để invalidate đúng `HttpSession`. CAS Server có thể gửi back-channel POST tới **service URL ban đầu** hoặc `logoutUrl` riêng như `/cas/slo`. Nếu SLO filter nằm **trước CsrfFilter**, không cần miễn CSRF thêm; nếu callback phải đi qua CsrfFilter, chỉ miễn **POST của đúng callback SLO**, giữ nguyên CSRF cho `POST /logout` và nghiệp vụ. Không được đánh đổi khả năng nhận logout bằng cách tắt CSRF toàn ứng dụng hoặc bỏ xác minh nguồn/correlation của thông báo.

## 17. Tài liệu tham khảo

1. [Spring Security — CAS Authentication, Single Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html) — ví dụ `SingleSignOutFilter` trước CAS filter, local logout và request global logout.
2. [Spring Security 6.5 — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html) — `CsrfFilter`, `ignoringRequestMatchers` và yêu cầu CSRF cho POST logout.
3. [Spring Security — Handling Logouts (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html) — `LogoutFilter`, `LogoutHandler`, `SecurityContextLogoutHandler` và local logout.
4. [Spring Security 6.5 — Servlet Security Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html) — `FilterChainProxy`, `addFilterBefore` và kiểm thứ tự filters.
5. [Apereo Java CAS Client — Configuring Single Sign Out](https://github.com/apereo/java-cas-client#configuring-single-sign-out) — `SingleSignOutFilter`, `SingleSignOutHttpSessionListener`, `logoutCallbackPath`, URL pattern `/*`, lưu mappings.
6. [Apereo CAS 7.3 — Logout & Single Logout](https://apereo.github.io/cas/7.3.x/installation/Logout-Single-Signout.html) — `logoutType`, back-channel POST/front-channel GET, `logoutUrl`/service URL và CAS SLO session correlation.
7. [Apereo CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html) — CAS /login, /logout, service ticket, TGT/TGC và service registration.
8. [Spring Security — Authentication Persistence](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html) — SecurityContextRepository và HttpSession.
9. [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html) — session fixation strategies và local sessions.
10. [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) — giới hạn CSRF exceptions, logout CSRF và cookie-based session workflows.
11. [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) — session invalidation, logout và session ID.
12. [OWASP XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html) — khi tích hợp XML SLO, tránh XXE parser tự viết.
