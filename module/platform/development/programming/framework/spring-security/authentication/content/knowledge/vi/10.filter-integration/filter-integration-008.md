# SessionAuthenticationStrategy sau khi xác thực thành công

Trong một ứng dụng Spring Security Servlet, kiểm đúng username/password **chưa phải toàn bộ quá trình đăng nhập an toàn**. Sau khi `AuthenticationManager` trả về `Authentication` đã xác thực, hệ thống còn có thể cần **đổi session ID** để phòng chống *session fixation*, **kiểm giới hạn phiên đồng thời**, **đăng ký session vào registry** và **đặt lại CSRF token** khi danh tính thay đổi.

Đây là công việc của hợp đồng `SessionAuthenticationStrategy`. Với bộ lọc đăng nhập có sẵn của Spring Security, chiến lược tương ứng thường được kích hoạt trong luồng xác thực chuẩn. Nhưng nếu lập trình viên viết **filter đăng nhập tùy chỉnh** mà chỉ gọi `authenticate(...)` rồi trả 200, các biện pháp bảo vệ phiên có thể bị bỏ qua dù mật khẩu vẫn được kiểm đúng.

Bài thuộc nhóm **Tích hợp bộ lọc** của chủ đề *Spring Security - authentication*; trọng tâm là **thời điểm và trách nhiệm gọi `SessionAuthenticationStrategy.onAuthentication(...)` sau khi xác thực thành công** trong Spring Security 6.x, cách tổ hợp chiến lược, thứ tự với `SecurityContextRepository.saveContext(...)` và response commit, ví dụ Java 17+/Spring Boot 3.x chạy được cùng kiểm thử.

**Quy tắc cốt lõi:** Đối với *custom authentication mechanism* tạo một phiên đăng nhập stateful, hãy để `AuthenticationManager`/provider xác minh credential trước; sau khi thành công, gọi **đúng một lần** chiến lược phiên phù hợp; chỉ khi được chấp nhận mới tạo/đặt/lưu `SecurityContext`; cuối cùng mới gọi success handler/redirect/ghi response. **Đừng tự gọi strategy trên request thất bại, trên mỗi request đã đăng nhập, hoặc lần nữa bên trong success handler khi framework đã gọi giúp.**

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Giải thích hợp đồng `SessionAuthenticationStrategy` và phân biệt nó với `AuthenticationManager`, `SecurityContextHolder`, `SecurityContextRepository` và `SessionManagementFilter`.
2. Nêu thứ tự authentication success: `attemptAuthentication` → `SessionAuthenticationStrategy` → `successfulAuthentication` → context/save → success handler, trong luồng `AbstractAuthenticationProcessingFilter`.
3. Hiểu thay đổi từ Spring Security 5 sang 6: các cơ chế xác thực **tự kích hoạt strategy**, không trông chờ `SessionManagementFilter` phát hiện authentication theo mặc định.
4. Chọn `ChangeSessionIdAuthenticationStrategy`, `SessionFixationProtectionStrategy`, `ConcurrentSessionControlAuthenticationStrategy`, `RegisterSessionAuthenticationStrategy`, `CsrfAuthenticationStrategy` hoặc `NullAuthenticatedSessionStrategy` theo yêu cầu.
5. Xây `CompositeSessionAuthenticationStrategy` với **thứ tự được kiểm soát** và hiểu lý do nếu một delegate ném `SessionAuthenticationException` thì không được gọi tiếp các delegate còn lại.
6. Cấu hình custom filter kế thừa `AbstractAuthenticationProcessingFilter` cùng `SessionAuthenticationStrategy` và `SecurityContextRepository`; tránh đăng ký filter hai lần.
7. Tự chạy demo Java 17+ và Spring Boot/MockMvc chứng minh: session ID thay đổi sau login thành công, login sai không làm phiên được nâng quyền, CSRF được kiểm, session được lưu và request kế tiếp nhận đúng principal.
8. Nhận diện giới hạn: session mới chưa tồn tại, session cookie, nhiều node, registry và token stateless không thể được “sửa” chỉ bằng một strategy.

## 2. Một tên interface, nhiều trách nhiệm bảo vệ phiên

`SessionAuthenticationStrategy` thuộc package:

```java
org.springframework.security.web.authentication.session.SessionAuthenticationStrategy
```

Hợp đồng Java cơ bản:

```java
void onAuthentication(
        Authentication authentication,
        HttpServletRequest request,
        HttpServletResponse response)
        throws SessionAuthenticationException;
```

**Diễn giải:** Khi một authentication mới thành công, chiến lược được gọi với kết quả `Authentication` đáng tin và request/response HTTP hiện tại, để thực hiện chức năng liên quan đến session. `SessionAuthenticationException` báo việc tiếp tục xác thực với phiên này không được chấp nhận, ví dụ đạt giới hạn số session.

Phương thức không có nhiệm vụ:

- Tự kiểm mật khẩu, OTP hoặc JWT signature.
- Tự cấp `ROLE_ADMIN`, xây principal từ dữ liệu client hoặc tự xác định tenant.
- Tự lưu `Authentication` thành `SecurityContext` cho request sau.
- Tự bảo đảm mọi phiên/JWT trên mọi máy chủ đều bị thu hồi.
- Được chạy trên mọi request `GET` của user đã đăng nhập.
- Thay thế CSRF filter, session-cookie policy hay authorization trên tài nguyên.

### 2.1 Các thành phần xung quanh

| Thành phần | Câu hỏi nó giải quyết | Ví dụ |
| --- | --- | --- |
| `AuthenticationManager` / `AuthenticationProvider` | Credential/token có hợp lệ không, ai là principal, authorities nào? | `DaoAuthenticationProvider`, `PasswordEncoder`. |
| **`SessionAuthenticationStrategy`** | Khi vừa xác thực thành công, cần xử lý phiên như thế nào? | Đổi session ID, giới hạn số phiên, CSRF token cleanup. |
| `SecurityContextHolderStrategy` | Context được gắn với execution/thread hiện tại ra sao? | `MODE_THREADLOCAL` mặc định Servlet. |
| `SecurityContextRepository` | Lưu/nạp `SecurityContext` giữa các HTTP requests ở đâu? | `HttpSessionSecurityContextRepository`. |
| `AuthenticationSuccessHandler` | Trả response/redirect nào sau khi thành công? | HTTP 204, redirect tới trang ban đầu. |
| `AuthenticationFailureHandler` | Phản hồi gì khi credential hoặc session policy bị từ chối? | HTTP 401, thông báo chung. |
| `SessionRegistry` | Hệ thống biết những session nào gắn với principal? | `SessionRegistryImpl` hoặc giải pháp distributed. |
| `ConcurrentSessionFilter` | Xử lý session đã được đánh dấu expired ở request sau. | Chặn session vượt hạn nếu cấu hình concurrency. |

**Đăng nhập thành công về mật khẩu** không đồng nghĩa **được phép tạo thêm session**: `ConcurrentSessionControlAuthenticationStrategy` có thể từ chối sau khi password đã đúng, và khi đó không nên lưu `SecurityContext` của phiên mới.

### 2.2 Không nhầm hai loại “session”

- **Servlet `HttpSession`**: phiên HTTP phía server, thường browser giữ cookie `JSESSIONID` để tham chiếu. `SessionAuthenticationStrategy` chủ yếu xử lý nó.
- **Security authentication state**: `Authentication` trong `SecurityContext`, có thể nằm trong HttpSession hoặc được tạo lại từ bearer token mỗi request.
- **OAuth2/OIDC session/authorization grant**: có vòng đời riêng ở IdP/authorization server, không tự chịu mọi tác động của session strategy Servlet.
- **Spring Session distributed store**: thay backend giữ `HttpSession`; không đồng nghĩa mọi `SessionRegistryImpl` tự thành registry toàn cụm máy.

## 3. Thời điểm onAuthentication trong chuỗi filter

Với filter dựa trên `AbstractAuthenticationProcessingFilter` của Spring Security 6.x, luồng cơ bản:

```text
POST /api/login
    |
    v
Spring Security FilterChainProxy
    |
    +--> CsrfFilter (trước xử lý POST đăng nhập khi bật CSRF)
    |
    v
Custom authentication filter / UsernamePasswordAuthenticationFilter
    |
    v
attemptAuthentication(request, response)
    |
    +--> Token chưa xác thực từ username/password
    +--> AuthenticationManager.authenticate(token)
    |
    +---- THẤT BẠI ---> unsuccessfulAuthentication(...)
    |                    -> failure handler, KHÔNG gọi strategy thành công
    |
    +---- CHƯA HOÀN TẤT (null) ---> kết thúc bước hiện tại
    |
    +---- THÀNH CÔNG: Authentication verified
                              |
                              v
            sessionStrategy.onAuthentication(verified, req, resp)
                    |                     |
                    | thành công           +--> SessionAuthenticationException
                    v                              |
            successfulAuthentication(...)          v
                    |                       failure handler
                    +--> context mới           KHÔNG save authenticated context
                    +--> setContext
                    +--> SecurityContextRepository.saveContext(...)
                    +--> RememberMeServices.loginSuccess (nếu có)
                    +--> success event/handler
                    +--> status/body/redirect
```

**Thứ tự ở đây áp dụng cho subclass tuân thủ contract của `AbstractAuthenticationProcessingFilter`**, không có nghĩa mọi custom `OncePerRequestFilter` được Spring tự động gọi strategy. Nếu bạn tự viết filter xử lý password, bạn phải thực hiện và kiểm thử các bước tương đương.

### 3.1 Vì sao strategy đứng sau xác thực?

Trước khi xác thực thành công, username/password/role do client gửi là **dữ liệu chưa tin cậy**. Nếu đổi session ID, tạo bản ghi registry hoặc cấp thêm session ngay cho mọi request sai mật khẩu, attacker có thể tạo session hàng loạt và gây tăng tải; còn có thể làm thay đổi phiên của nạn nhân không cần thiết.

`SessionAuthenticationStrategy.onAuthentication` phải nhận `Authentication` **đã được provider xác minh**, chỉ sau `AuthenticationManager.authenticate` thành công. Một lỗi session policy phải được xử lý như **login không được chấp nhận**, chứ không coi là login thành công rồi “ghi chú sẽ sửa sau”.

### 3.2 Vì sao strategy đứng trước success handler?

`AuthenticationSuccessHandler` có thể gửi redirect, HTTP 200/204, flush body hoặc bắt đầu stream. Những thao tác này có thể **commit response**. Session strategy có thể cần `request.changeSessionId()`, tạo session, invalidate CSRF token hoặc gắn thông tin session registry trước khi response hoàn tất.

Nếu response đã gửi trước khi strategy xử lý, browser có thể không nhận cookie session ID mới, còn registry có thể ghi ID cũ. Hãy hoàn tất các bước session trước success response.

### 3.3 Vì sao strategy không thay thế việc lưu SecurityContext?

Đổi session ID chỉ xử lý **session fixation**; nó không tự ghi authentication vừa thành công vào `HttpSession`. Với Spring Security 6 default explicit save, cần:

```java
Authentication verified = authenticationManager.authenticate(requested);

sessionAuthenticationStrategy.onAuthentication(
        verified, request, response);

SecurityContext context = strategy.createEmptyContext();
context.setAuthentication(verified);
strategy.setContext(context);

securityContextRepository.saveContext(
        context, request, response);

// Chỉ sau đây mới sendRedirect/flush/return body.
```

Đây là **mẫu tích hợp**, không phải class Java độc lập. Trong `AbstractAuthenticationProcessingFilter`, bước `successfulAuthentication` có thể lưu qua repository **nếu đã gọi `setSecurityContextRepository(...)`** cho filter; không nên tự save lại một lần nữa. Nếu tự viết controller thì bạn chịu trách nhiệm gọi save.

## 4. Spring Security 5 so với 6: không dựa vào SessionManagementFilter mặc định

### 4.1 Cơ chế của phiên bản cũ

Trong luồng điển hình của Spring Security 5, `SessionManagementFilter` có thể so `SecurityContextHolder` hiện tại với `SecurityContextRepository` để phát hiện vừa có authentication mới. Khi thấy auth mới mà repository chưa lưu, filter sẽ gọi `SessionAuthenticationStrategy`.

Đổi lại, cách này thường phải **đọc HttpSession ở mỗi request** để biết có authentication mới hay không, ngay cả khi không có sự kiện login.

### 4.2 Cơ chế Spring Security 6

Theo tài liệu Spring Security 6, mặc định **không thêm `SessionManagementFilter`** vào chain để phát hiện login mới. Thay vào đó, **authentication mechanism tự gọi `SessionAuthenticationStrategy` khi thích hợp**. Kết quả là giảm việc truy cập `HttpSession` chỉ để dò login event.

Đồng thời, `SecurityContextHolderFilter` trong cấu hình default chủ yếu **nạp** context, không tự save mọi thay đổi; custom auth muốn giữ context qua request cần explicit save. Hai thay đổi này có liên quan nhưng **không phải cùng một trách nhiệm**:

- `SessionAuthenticationStrategy`: xử lý tác vụ session **khi login mới thành công**.
- `SecurityContextRepository.saveContext`: lưu `SecurityContext` qua request.
- `SecurityContextHolderFilter`: nạp context cho request đang xử lý.
- `AuthenticationSuccessHandler`: hoàn tất HTTP response.

### 4.3 Điều gì xảy ra khi nâng cấp code cũ?

Một filter custom chỉ làm:

```java
Authentication result = manager.authenticate(untrustedToken);
SecurityContextHolder.getContext().setAuthentication(result);
chain.doFilter(request, response);
```

có thể trước đây tình cờ được filter khác nhận diện login, kích hoạt strategy hoặc save context. Trên Spring Security 6 mặc định, cách viết này không đủ để đảm bảo đổi session ID, giới hạn session, lưu context hay response success chuẩn.

**Cách sửa:** Dùng `AbstractAuthenticationProcessingFilter` với cấu hình strategy/repository rõ; hoặc khi tự viết `OncePerRequestFilter`/controller, gọi strategy và save đúng thứ tự, rồi dùng success/failure response rõ ràng.

**Không** thêm `SessionManagementFilter` và `SecurityContextPersistenceFilter` bằng tay chỉ để tái tạo hiệu ứng phụ từ code cũ; hai filter có thể gây duplicate handling, đọc session không cần thiết hoặc phát sinh race nếu cấu hình sai.

### 4.4 Cấu hình DSL nào chưa đủ?

Việc thêm:

```java
http.sessionManagement(session -> session
        .sessionFixation(fixation -> fixation.changeSessionId()));
```

có thể có ích với các cơ chế đăng nhập tích hợp được cấu hình bằng DSL; **không có nghĩa custom filter tạo riêng đã chắc dùng strategy đó**. Nếu bạn xây một `AbstractAuthenticationProcessingFilter` bằng `new`, hãy truyền/thiết lập `setSessionAuthenticationStrategy(...)` lên chính filter. Spring Security 6 không mặc định dựa vào SessionManagementFilter để “bù” giúp filter tùy chỉnh.

Đối với một số tùy chọn `sessionManagement` DSL liên quan tới `SessionManagementFilter` như `sessionAuthenticationStrategy(...)`, Spring Security 6 có thay đổi và có thể từ chối dùng theo cách cũ. Đọc tài liệu phiên bản thực tế; ưu tiên **cấu hình strategy trực tiếp trên authentication mechanism**.

## 5. Các triển khai SessionAuthenticationStrategy và đúng việc của từng lớp

| Class | Công việc | Khi nào chọn |
| --- | --- | --- |
| `ChangeSessionIdAuthenticationStrategy` | Sử dụng `HttpServletRequest.changeSessionId()` trên Servlet 3.1+ để đổi ID của session hiện có, bảo vệ trước fixation. | Mặc định hợp lý trên Servlet container hiện đại khi login stateful. |
| `SessionFixationProtectionStrategy` | Invalidate session cũ, tạo session mới và có thể chuyển attributes theo cấu hình. | Cần chính sách migrate/newSession cụ thể hoặc môi trường cũ. |
| `ConcurrentSessionControlAuthenticationStrategy` | Kiểm số session active theo `SessionRegistry` và giới hạn được cấu hình. | Hạn chế đăng nhập đồng thời, có chính sách reject hoặc expire phiên cũ. |
| `RegisterSessionAuthenticationStrategy` | Đăng ký session đã thành công với `SessionRegistry`. | Thường đi cùng concurrent-session control. |
| `CsrfAuthenticationStrategy` | Xóa/đặt lại CSRF token đã lưu khi principal vừa xác thực, để tránh giữ token cũ qua đổi danh tính. | Browser cookie-session có CSRF protection. |
| `CompositeSessionAuthenticationStrategy` | Gọi lần lượt các chiến lược con theo thứ tự; dừng khi gặp `SessionAuthenticationException`. | Kết hợp concurrent check, fixation, registry, CSRF. |
| `NullAuthenticatedSessionStrategy` | Không thay đổi session. | Chỉ khi policy không yêu cầu session work, hoặc flow stateless có cơ chế khác. |

**Có class không có nghĩa mặc định được bật đúng.** Chỉ cấu hình object hoặc bean `SessionAuthenticationStrategy` mà không gắn nó với **filter đăng nhập thực tế** sẽ không bảo đảm có tác dụng. Ngược lại, gọi cùng chiến lược **hai lần** có thể đổi ID hai lần, tạo registry entry dư hoặc xóa token CSRF ngoài ý định.

### 5.1 ChangeSessionIdAuthenticationStrategy

Với Servlet 3.1+, `HttpServletRequest.changeSessionId()` yêu cầu container thay ID của `HttpSession` **đang tồn tại** mà không phải tạo một session mới và copy mọi thuộc tính theo cách thủ công.

```text
Trước login:
  HttpSession id = S1
  có thể chứa CSRF token, saved request, giỏ hàng...

Login/password verified:
  ChangeSessionIdAuthenticationStrategy.onAuthentication(...)

Sau khi đổi:
  Cùng logical session với ID mới S2
  S1 không còn được phép định danh session vừa authenticated.
```

Không giả định strategy luôn tạo session từ hư không. Nếu login request chưa có session, `ChangeSessionIdAuthenticationStrategy` **không cần làm gì để đổi một ID vốn chưa tồn tại**. `HttpSessionSecurityContextRepository` có thể tạo session sau đó khi lưu context, tùy cấu hình session creation; kết quả là login vẫn có thể persist session nhưng không có sự kiện “đổi ID của pre-login session”.

### 5.2 SessionFixationProtectionStrategy: newSession và migrateSession

Một phương án khác là invalidate session cũ rồi tạo session mới. Khi đó có câu hỏi: **thuộc tính session trước login nào được giữ?** Saved request, CSRF, giỏ hàng hay state khác có thể được migrate theo cấu hình. Copy mọi attribute một cách mù quáng có thể giữ dữ liệu pre-auth không nên dùng sau login; xóa sạch có thể làm mất dữ liệu UX hợp lệ.

- `changeSessionId`: đổi ID của session hiện có, không cần copy attributes thủ công; thường là default Servlet hiện đại.
- `newSession`: tạo phiên mới tương đối sạch, vẫn có một số state framework cần thiết.
- `migrateSession`: chuyển attributes từ session cũ sang session mới theo policy.
- `none`: tắt chống session fixation; **không khuyến nghị** cho browser session login.

Đừng tự gọi `request.getSession().invalidate()` rồi `getSession(true)` sau authentication nếu không hiểu lifecycle/registry/cookie: framework đã có strategies và event handling cho việc này.

### 5.3 ConcurrentSessionControlAuthenticationStrategy

Được cấu hình với `SessionRegistry`, chiến lược đọc số session active của principal và quyết định:

- Khi `exceptionIfMaximumExceeded=true` và đã đạt giới hạn, ném `SessionAuthenticationException` để **từ chối login mới**.
- Khi để chế độ expire-session theo policy, có thể đánh dấu những phiên cũ vượt giới hạn là expired, cho login mới tiếp tục; phiên cũ được xử lý ở request sau nhờ các filter/cơ chế tương ứng.
- `maximumSessions=1` không có nghĩa cùng browser mở hai tab là hai session: nếu cùng `JSESSIONID`, server nhìn thấy **một session**.
- `SessionRegistry` phải được cập nhật khi session tạo/xóa; registry cục bộ trong một JVM không tự đồng bộ trên cluster.

**Không chỉ kiểm một lần rồi tự gọi `RegisterSessionAuthenticationStrategy` trước concurrent check.** Thứ tự sai có thể khiến chính session đang tạo bị tính vào giới hạn và gây hành vi khác mong muốn.

### 5.4 RegisterSessionAuthenticationStrategy

Sau khi login được chấp nhận và session ID cuối đã được quyết định, chiến lược này đăng ký mapping giữa principal và session ID trong `SessionRegistry`. Nó không tự **giới hạn** số phiên; cần `ConcurrentSessionControlAuthenticationStrategy` nếu muốn quyết định giới hạn.

Nếu đăng ký **trước** bước thay session ID, registry có thể giữ ID cũ hoặc phải phụ thuộc event cập nhật; quy ước tổ hợp được Javadoc khuyến nghị là **control → fixation → register**.

### 5.5 CsrfAuthenticationStrategy

Đổi danh tính là một trust boundary: CSRF token cũ được tạo trước login có thể cần invalidation. `CsrfAuthenticationStrategy` làm việc với `CsrfTokenRepository` để xóa token cũ sau authentication. Nó **không thay thế `CsrfFilter` kiểm token ở request POST**; nên giữ cả hai thành phần nếu browser xác thực bằng cookie session.

Với mô hình CSRF token deferred ở Spring Security 6, việc token bị invalidate sau login có thể khiến SPA phải fetch token **mới** trước POST tiếp theo. Không lấy token trước login rồi tái sử dụng mãi sau login và tưởng đó là lỗi session registry.

## 6. CompositeSessionAuthenticationStrategy: thứ tự không phải trang trí

Khi có yêu cầu chống fixation, giới hạn phiên và đăng ký registry, một thứ tự phổ biến được Javadoc Spring Security khuyến nghị:

```text
AuthenticationManager.authenticate(...) trả verified
                 |
                 v
ConcurrentSessionControlAuthenticationStrategy
   +-- kiểm tối đa phiên; có thể TỪ CHỐI login ngay
                 |
                 v
ChangeSessionIdAuthenticationStrategy
   +-- đổi session ID nếu có pre-login HttpSession
                 |
                 v
RegisterSessionAuthenticationStrategy
   +-- lưu ID cuối và principal vào SessionRegistry
                 |
                 v
CsrfAuthenticationStrategy
   +-- xóa token CSRF cũ khi identity thay đổi
                 |
                 v
SecurityContext tạo/được gắn/lưu, rồi success response
```

Ví dụ **mảnh cấu hình** (không phải ứng dụng Java độc lập):

```java
SessionRegistry registry = new SessionRegistryImpl();

ConcurrentSessionControlAuthenticationStrategy concurrent =
        new ConcurrentSessionControlAuthenticationStrategy(registry);
concurrent.setMaximumSessions(1);
concurrent.setExceptionIfMaximumExceeded(true);

SessionAuthenticationStrategy sessionStrategy =
        new CompositeSessionAuthenticationStrategy(List.of(
                concurrent,
                new ChangeSessionIdAuthenticationStrategy(),
                new RegisterSessionAuthenticationStrategy(registry),
                new CsrfAuthenticationStrategy(csrfTokenRepository)));
```

Để chạy đoạn này cần imports của `SessionRegistry`, `SessionRegistryImpl`, `CsrfTokenRepository` và các strategies cùng một ứng dụng Servlet có session/CSRF/registry được cấu hình. Đây chỉ là **mẫu thứ tự**; production còn cần `HttpSessionEventPublisher` hoặc cơ chế nhận lifecycle events phù hợp, quản lý registry đa node và filter xử lý expired sessions khi dùng chế độ expire thay vì reject.

### 6.1 “Short-circuit” khi strategy ném exception

`CompositeSessionAuthenticationStrategy` gọi delegates theo thứ tự đã cấp và **ngừng khi một delegate ném `SessionAuthenticationException`**. Nếu concurrent check từ chối:

- Không gọi fixation strategy phía sau chỉ để đổi session ID.
- Không đăng ký session mới.
- Không lưu authenticated `SecurityContext` của phiên bị từ chối.
- Authentication mechanism chuyển sang failure flow/handler, không gọi success response.
- Không thông báo public bằng chi tiết nhạy cảm về số thiết bị khác nếu policy chống account enumeration yêu cầu.

Nếu tự viết wrapper mà **bắt mọi exception rồi tiếp tục**, bạn có thể vô hiệu cơ chế giới hạn phiên. Luôn xử lý session-authentication rejection như một **authentication failure** theo contract, không biến thành warning rồi trả 200.

### 6.2 “Exactly once” quan trọng hơn số bean

Một application có thể có:

- Strategy do DSL `sessionManagement()` sinh ra cho built-in filter.
- Một `SessionAuthenticationStrategy` bean để custom controller gọi.
- Một filter tự viết gọi `onAuthentication`.
- Một success handler vô tình gọi `onAuthentication` lần nữa.

Khi cả bốn không được điều phối, cùng một login event có thể đổi session ID hai lần hoặc gửi event đăng ký/CSRF cleanup dư. Thiết kế nên có **một nơi sở hữu authentication success lifecycle**. Với `AbstractAuthenticationProcessingFilter`, gắn strategy qua `setSessionAuthenticationStrategy` và **không tự gọi lại trong `successfulAuthentication`**. Với MVC controller tự xác thực, gọi nó một lần ngay sau `authenticate`.

### 6.3 Khi nào không nên đặt strategy tạo session?

Nếu API hoàn toàn stateless dùng bearer JWT ở header trên mọi request, việc tự tạo `HttpSession` sau mỗi JWT validation có thể làm tăng cookie/session, giảm scale và mâu thuẫn `SessionCreationPolicy.STATELESS`. Đừng gọi các session creation/fixation strategies trên mỗi request đã được xác thực bằng JWT. SessionAuthenticationStrategy chủ yếu phục vụ **một sự kiện đăng nhập mới** của Servlet stateful flow; quản lý refresh token/JWT grants là hợp đồng khác.

## 7. Ví dụ Java 17 thuần: chứng minh đúng thứ tự và short-circuit

Trước khi dùng Spring, có thể chạy một chương trình nhỏ để thấy logic “credential đúng → control → fixation → register” và trường hợp bị từ chối không thực hiện bước sau. Đây là **mô phỏng thứ tự** bằng Java 17, không thay cho `SessionAuthenticationStrategy`/Servlet thật.

File `SuccessSessionOrderDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public final class SuccessSessionOrderDemo {

    static List<String> flow(boolean passwordOk, boolean sessionAllowed) {
        List<String> steps = new ArrayList<>();
        steps.add("authenticate");

        if (!passwordOk) {
            steps.add("authentication-failure");
            return steps;
        }

        steps.add("concurrent-control");
        if (!sessionAllowed) {
            steps.add("session-rejected");
            return steps;
        }

        steps.add("change-session-id");
        steps.add("register-session");
        steps.add("csrf-cleanup");
        steps.add("save-security-context");
        steps.add("success-response");
        return steps;
    }

    public static void main(String[] args) {
        System.out.println("ok=" + flow(true, true));
        System.out.println("wrong-password=" + flow(false, true));
        System.out.println("limit-rejected=" + flow(true, false));
    }
}
```

Chạy bằng JDK 17+:

```bash
javac SuccessSessionOrderDemo.java
java SuccessSessionOrderDemo
```

Stdout **chính xác**:

```text
ok=[authenticate, concurrent-control, change-session-id, register-session, csrf-cleanup, save-security-context, success-response]
wrong-password=[authenticate, authentication-failure]
limit-rejected=[authenticate, concurrent-control, session-rejected]
```

Chương trình không có Spring/Servlet HTTP, nên mục đích của nó là **kiểm tư duy thứ tự và short-circuit**, không mô phỏng cookie, session IDs thật hay `SecurityContextRepository`. Ví dụ Spring Boot tiếp theo mới kiểm qua security filter chain.

## 8. Spring Boot 3.x chạy được: filter đăng nhập tùy chỉnh có SessionAuthenticationStrategy

Ứng dụng học tập dùng Java 17+, Spring Boot 3.3.13, Spring Security 6.x và MockMvc. Mục tiêu:

- `POST /api/login` nhận form-urlencoded `username` và `password`, được xử lý bởi **filter tùy chỉnh kế thừa `AbstractAuthenticationProcessingFilter`** chứ không phải MVC controller.
- Filter gọi `AuthenticationManager`, **framework gọi strategy sau khi auth thành công**, rồi `successfulAuthentication` lưu `SecurityContext` qua repository đã cấu hình.
- Strategy là `CompositeSessionAuthenticationStrategy` gồm `ChangeSessionIdAuthenticationStrategy` và `CsrfAuthenticationStrategy`.
- `GET /api/me` chứng minh request mới có thể nạp phiên authenticated.
- `GET /api/admin` đòi `ROLE_ADMIN`, không tự cho mọi account đã login quyền admin.
- Test kiểm pre-login session ID đổi; password sai không nâng session; CSRF thiếu bị từ chối.

**Vì sao demo chưa bật concurrent-session control?** Cần thêm registry, event lifecycle và xử lý expired sessions mới đánh giá được đúng concurrency. Bài vẫn hướng dẫn cách bổ sung ở mục 10; bản demo cốt lõi ưu tiên runnable rõ và không tuyên bố đã có tính năng mà chưa cài đủ.

### 8.1 Cấu trúc Gradle

```text
session-strategy-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/SessionStrategyApplication.java
    └── test/java/demo/SessionStrategyTest.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'session-strategy-lab'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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
```

Phiên bản được ghim **để tái lập bài học**, không phải khuyến nghị dùng nhánh đã hết hỗ trợ trong production mới. Ứng dụng production cần chọn dòng Boot/Security đang được hỗ trợ và cập nhật theo tư liệu/Javadoc phiên bản đó.

### 8.2 Ứng dụng, filter và cấu hình

File `src/main/java/demo/SessionStrategyApplication.java`:

```java
package demo;

import java.io.IOException;
import java.util.List;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AbstractAuthenticationProcessingFilter;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SessionStrategyApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionStrategyApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("local-alice-password"))
                        .roles("USER")
                        .build(),
                User.withUsername("bob")
                        .password(encoder.encode("local-bob-password"))
                        .roles("USER", "ADMIN")
                        .build());
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());
    }

    @Bean
    CsrfTokenRepository csrfTokenRepository() {
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy(
            CsrfTokenRepository csrfRepository) {
        // Trong demo chưa bật kiểm số phiên đồng thời.
        return new CompositeSessionAuthenticationStrategy(List.of(
                new ChangeSessionIdAuthenticationStrategy(),
                new CsrfAuthenticationStrategy(csrfRepository)));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager manager,
            SecurityContextRepository repository,
            CsrfTokenRepository csrfRepository,
            SessionAuthenticationStrategy sessionStrategy)
            throws Exception {

        ParameterLoginFilter loginFilter = new ParameterLoginFilter(manager);

        // Quan trọng: gắn strategy TRỰC TIẾP lên custom filter.
        loginFilter.setSessionAuthenticationStrategy(sessionStrategy);

        // AbstractAuthenticationProcessingFilter cần repository để
        // save context sau successfulAuthentication trong Security 6.
        loginFilter.setSecurityContextRepository(repository);

        // Handler chỉ hoàn tất response; KHÔNG gọi strategy lần nữa.
        loginFilter.setAuthenticationSuccessHandler(
                (request, response, authentication) ->
                        response.setStatus(
                                HttpServletResponse.SC_NO_CONTENT));

        loginFilter.setAuthenticationFailureHandler(
                (request, response, failure) ->
                        response.sendError(
                                HttpServletResponse.SC_UNAUTHORIZED));

        return http
                .securityContext(context -> context
                        .requireExplicitSave(true)
                        .securityContextRepository(repository))
                .csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.POST, "/api/login")
                            .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/me")
                            .authenticated()
                        .requestMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .anyRequest().denyAll())
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(
                                (request, response, exception) ->
                                        response.sendError(
                                                HttpServletResponse.SC_UNAUTHORIZED)))
                .formLogin(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .addFilterAt(
                        loginFilter,
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }

    static final class ParameterLoginFilter
            extends AbstractAuthenticationProcessingFilter {

        ParameterLoginFilter(AuthenticationManager manager) {
            super(new AntPathRequestMatcher("/api/login", "POST"), manager);
        }

        @Override
        public Authentication attemptAuthentication(
                HttpServletRequest request,
                HttpServletResponse response) {

            String username = request.getParameter("username");
            String password = request.getParameter("password");

            if (username == null || username.isBlank()
                    || username.length() > 128
                    || password == null
                    || password.length() > 256) {
                throw new BadCredentialsException("Bad credentials");
            }

            // Input client CHƯA authenticated; không tự tạo role.
            UsernamePasswordAuthenticationToken candidate =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            username, password);
            candidate.setDetails(
                    this.authenticationDetailsSource.buildDetails(request));

            return getAuthenticationManager().authenticate(candidate);
        }
    }
}

@RestController
class SessionStrategyController {

    @GetMapping("/api/me")
    Map<String, Object> me(Authentication authentication) {
        return Map.of(
                "name", authentication.getName(),
                "roles", authentication.getAuthorities().stream()
                        .map(authority -> authority.getAuthority())
                        .sorted()
                        .toList());
    }

    @GetMapping("/api/admin")
    String adminOnly() {
        return "admin";
    }
}
```

**Mã và lớp trong file:** Một file có đúng một public class `SessionStrategyApplication`. `ParameterLoginFilter` là static nested class; `SessionStrategyController` package-private. Spring Boot có thể tìm `@RestController` trong cùng package `demo`.

### 8.3 Vì sao cấu hình này đúng vị trí?

**Filter chỉ match POST /api/login.** `AntPathRequestMatcher("/api/login","POST")` giúp logic login không bị gọi ở mọi request `GET /api/me`. Chỉ khi `attemptAuthentication(...)` thực hiện thành công, superclass mới kích hoạt `sessionStrategy.onAuthentication(...)`.

**Token chưa xác thực đi qua manager.** `UsernamePasswordAuthenticationToken.unauthenticated` không cấp quyền trước; `DaoAuthenticationProvider` nạp account, kiểm password hash và trạng thái, rồi trả kết quả verified. Trả 204 chỉ sau khi cả provider và session strategy chấp nhận.

**Cùng một repository cho chain và filter.** `SecurityContextHolderFilter` của chain đọc từ bean `SecurityContextRepository`, còn `AbstractAuthenticationProcessingFilter` lưu vào bean đó sau success. Tránh lỗi save vào repo A nhưng request sau đọc từ repo B/`NullSecurityContextRepository`.

**Composite có hai thành phần rõ ràng.** Khi pre-login `HttpSession` đã có, `ChangeSessionIdAuthenticationStrategy` đổi ID. `CsrfAuthenticationStrategy` xóa token cũ, tránh tái sử dụng token trước login. Demo chưa kiểm giới hạn số phiên: đừng tưởng đã có `maximumSessions=1`.

**Không tự ghi response trước session policy.** Success handler chỉ gọi `response.setStatus(204)`; superclass gọi nó sau strategy/context save. Tránh gọi `sendRedirect`/`flushBuffer` trong `attemptAuthentication` trước session processing.

**Không đăng ký filter hai lần.** `ParameterLoginFilter` được tạo ngay trong `securityFilterChain` và `addFilterAt`. Nó **không** có `@Component`/`@Bean Filter` để Spring Boot tự đưa vào Servlet container ở ngoài `FilterChainProxy`; nếu làm cả hai, có thể có double authentication/duplicate strategies.

**CSRF vẫn bật.** Vì đây là cookie-session login, `CsrfFilter` vẫn chặn POST thiếu token. MockMvc dùng helper `csrf()`, không tắt security rule chỉ để test chạy.

### 8.4 Integration test cho chính luồng SessionAuthenticationStrategy

File `src/test/java/demo/SessionStrategyTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

@SpringBootTest
@AutoConfigureMockMvc
class SessionStrategyTest {

    @Autowired
    MockMvc mvc;

    private MvcResult login(String username, String password)
            throws Exception {
        return mvc.perform(post("/api/login")
                        .with(csrf())
                        .param("username", username)
                        .param("password", password))
                .andReturn();
    }

    @Test
    void successPersistsContextForNextRequest() throws Exception {
        MvcResult response = login("alice", "local-alice-password");
        assertEquals(204, response.getResponse().getStatus());

        MockHttpSession session =
                (MockHttpSession) response.getRequest().getSession(false);
        assertNotNull(session);

        SecurityContext saved = (SecurityContext) session.getAttribute(
                HttpSessionSecurityContextRepository
                        .SPRING_SECURITY_CONTEXT_KEY);
        assertNotNull(saved);
        assertEquals("alice", saved.getAuthentication().getName());

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"));

        mvc.perform(get("/api/admin").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void preLoginSessionIdChangesOnSuccess() throws Exception {
        MockHttpSession previous = new MockHttpSession();
        String idBefore = previous.getId();

        MvcResult response = mvc.perform(post("/api/login")
                        .session(previous)
                        .with(csrf())
                        .param("username", "bob")
                        .param("password", "local-bob-password"))
                .andExpect(status().isNoContent())
                .andReturn();

        MockHttpSession current =
                (MockHttpSession) response.getRequest().getSession(false);
        assertNotNull(current);
        assertNotEquals(idBefore, current.getId());

        mvc.perform(get("/api/admin").session(current))
                .andExpect(status().isOk());
    }

    @Test
    void wrongPasswordDoesNotCreateAuthenticatedContext()
            throws Exception {
        MvcResult response = login("alice", "wrong-password");
        assertEquals(401, response.getResponse().getStatus());

        MockHttpSession session =
                (MockHttpSession) response.getRequest().getSession(false);
        if (session != null) {
            assertNull(session.getAttribute(
                    HttpSessionSecurityContextRepository
                            .SPRING_SECURITY_CONTEXT_KEY));
        }

        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void csrfRequiredForCookieBasedLogin() throws Exception {
        mvc.perform(post("/api/login")
                        .param("username", "alice")
                        .param("password", "local-alice-password"))
                .andExpect(status().isForbidden());
    }
}
```

**Các test kiểm những ranh giới khác nhau:**

- `successPersistsContextForNextRequest` xác nhận filter/manager/strategy/success/save kết hợp và request kế tiếp thực sự thấy context của Alice. Không chỉ nhìn status 204 của login.
- `preLoginSessionIdChangesOnSuccess` chứng minh lớp `ChangeSessionIdAuthenticationStrategy` có tác động trên session đã tồn tại; Bob vẫn nhận đúng role ở request sau. Test bằng MockHttpSession và không giả định có sự kiện change-ID nếu login không có session trước.
- `wrongPasswordDoesNotCreateAuthenticatedContext` xác nhận một failure authentication không lưu principal của Alice. CSRF helper có thể ảnh hưởng session/token, nhưng **không phải context authenticated**.
- `csrfRequiredForCookieBasedLogin` xác nhận thiếu CSRF chặn request **trước** login filter; HTTP 403 ở đây không phải password sai.

**Lưu ý QA:** Kết quả trên là **kỳ vọng từ thiết kế**, không phải claim đã thực thi Gradle trong môi trường người đọc. Nếu test thực tế khác, kiểm filter registration/order, CSRF repository, session ID mock, repo và phiên bản Spring Security, không bỏ cơ chế bảo vệ để khiến test “xanh”.

### 8.5 Chạy dự án

Nếu có Gradle wrapper:

```bash
./gradlew test
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
```

Nếu chưa tạo wrapper nhưng đã cài Gradle tương thích, chạy `gradle test` / `gradle bootRun`. Không chạy `javac SessionStrategyApplication.java` đơn lẻ vì project cần Spring Boot/Security classpath.

Kết quả mong đợi khi chạy bốn integration tests là **4 test thành công**. Khi chạy app, browser muốn POST `/api/login` cần một CSRF token hợp lệ ràng buộc với session/cookie của nó. Demo không phát endpoint `GET /api/csrf` công khai; vì vậy dùng MockMvc tests để thử đầy đủ thay vì hardcode chuỗi CSRF hoặc tắt CSRF toàn ứng dụng. Với sản phẩm SPA thực tế, hãy thiết kế endpoint token và chính sách same-site/CORS/credentials rõ.

### 8.6 Thêm một test quan trọng cho “strategy chỉ khi thành công”

Để kiểm thêm về unit scope, có thể gắn một `SessionAuthenticationStrategy` spy trong một test riêng và đếm số lần `onAuthentication` được gọi:

```text
POST login sai mật khẩu  -> 0 lần strategy
POST login đúng           -> 1 lần strategy
GET /api/me với cookie    -> 0 lần strategy mới
POST login đúng lần nữa   -> 1 lần cho sự kiện login mới
```

Đây là kỳ vọng **theo hợp đồng thành công của filter**, không có nghĩa mọi API authentication (JWT Basic per request) nên coi mỗi request là một “login mới”. Khi dùng Mockito spy, phải chắc filter đang giữ đúng **instance spy** được inject; nếu spy một bean mà filter dùng instance khác, phép đếm không có ý nghĩa.

## 9. Tự viết OncePerRequestFilter: các bước phải do bạn quản lý

Không phải mọi authentication mechanism đều kế thừa `AbstractAuthenticationProcessingFilter`. Nếu chọn `OncePerRequestFilter` tùy biến, bạn cần tự thực hiện:

```java
// PSEUDOCODE tích hợp: cần matcher, imports, catch/failure handlers,
// repository/strategy beans và CSRF thích hợp của ứng dụng.
if (isLoginRequest(request)) {
    Authentication candidate =
            UsernamePasswordAuthenticationToken.unauthenticated(
                    usernameFromForm, rawPasswordFromForm);

    Authentication verified = authenticationManager.authenticate(candidate);

    sessionAuthenticationStrategy.onAuthentication(
            verified, request, response);

    SecurityContext context = securityContextHolderStrategy
            .createEmptyContext();
    context.setAuthentication(verified);
    securityContextHolderStrategy.setContext(context);

    securityContextRepository.saveContext(context, request, response);

    successHandler.onAuthenticationSuccess(
            request, response, verified);
    return;
}

filterChain.doFilter(request, response);
```

**Không phải file Java chạy độc lập**: các biến trong pseudocode phải được cung cấp bởi cấu hình thật. Nó cố ý không viết catch flow, request parsing hay filter lifecycle để nhấn mạnh **thứ tự**. Trong code production cần xử lý `AuthenticationException`/`SessionAuthenticationException` bằng failure handler, bảo vệ CSRF, session fixation, clear context khi thất bại, giới hạn rate và chỉ save sau khi strategy chấp nhận.

Nếu custom filter chỉ xử lý bearer JWT cho mọi request và không tạo `HttpSession`, **không được copy nguyên pseudocode trên** để gọi fixation/registry cho từng token. Mục đích là sự kiện login/session mới, không phải tất cả request đã authenticated.

### 9.1 Sai lầm thường gặp với OncePerRequestFilter

```java
// SAI: tạo phiên/đổi ID trước khi kiểm credential.
sessionStrategy.onAuthentication(
        userSuppliedAuthentication, request, response);
Authentication verified = manager.authenticate(candidate);
```

Một request sai password không nên gây session-authentication success. Cũng không được truyền một `Authentication` tự set `authenticated=true` từ input vào strategy.

### 9.2 Strategy từ chối nhưng code vẫn save

```java
// SAI: anti-pattern.
try {
    strategy.onAuthentication(verified, request, response);
} catch (SessionAuthenticationException ignored) {
    // "Chỉ là lỗi session, vẫn login" -> lỗi an toàn nghiêm trọng.
}
repository.saveContext(contextWithVerified, request, response);
```

Nếu policy từ chối login do quá nhiều session, việc tiếp tục lưu context tạo một phiên đã authenticated **vượt giới hạn**. Trong failure path phải dừng, không trả success, không persist context mới; log reason đã làm sạch và metric nội bộ.

### 9.3 Gọi strategy ngay trên request protected đã authenticated

```java
// SAI: filter chạy ở mọi URL, không phân biệt login event.
Authentication current =
        SecurityContextHolder.getContext().getAuthentication();
if (current != null) {
    sessionStrategy.onAuthentication(current, request, response);
}
```

Điều này có thể làm session ID đổi ở **mỗi API call**, CSRF token liên tục bị xóa, registry bị cập nhật sai và session limit behavior khó hiểu. Strategy chạy khi *new authentication* được chấp nhận bởi authentication mechanism, không phải vì context đang có principal từ session cũ.

## 10. Muốn giới hạn số session đồng thời: phải đủ bộ linh kiện

Trong phần demo, Composite chỉ gồm fixation + CSRF. Để thêm giới hạn ví dụ một session cho user, cần:

1. `SessionRegistry` theo dõi principal ↔ session IDs, có lifecycle cleanup.
2. `ConcurrentSessionControlAuthenticationStrategy` quyết định reject/expire.
3. Fixation strategy đổi ID trước khi đăng ký.
4. `RegisterSessionAuthenticationStrategy` đăng ký ID cuối.
5. `ConcurrentSessionFilter` hoặc xử lý expiration tương đương nếu chọn chế độ expire old sessions.
6. `HttpSessionEventPublisher` / `HttpSessionIdListener` hoặc tích hợp Spring Session tương ứng cho thông tin destroy/change ID.
7. Store/registry phù hợp **nhiều node**; `SessionRegistryImpl` cục bộ không tự thành chính sách toàn hệ thống.
8. Custom login filter thật phải sử dụng Composite đó, không chỉ có bean nằm không.

Mẫu cấu hình riêng, **không đặt cạnh sample demo mà không điều chỉnh chain**:

```java
@Bean
SessionRegistry sessionRegistry() {
    return new SessionRegistryImpl();
}

@Bean
SessionAuthenticationStrategy sessionStrategyWithLimit(
        SessionRegistry registry,
        CsrfTokenRepository csrfRepository) {

    ConcurrentSessionControlAuthenticationStrategy concurrent =
            new ConcurrentSessionControlAuthenticationStrategy(registry);
    concurrent.setMaximumSessions(1);

    // true: từ chối login mới khi đã đạt giới hạn.
    // false: có thể đánh dấu những phiên cũ expired theo policy.
    concurrent.setExceptionIfMaximumExceeded(true);

    return new CompositeSessionAuthenticationStrategy(List.of(
            concurrent,
            new ChangeSessionIdAuthenticationStrategy(),
            new RegisterSessionAuthenticationStrategy(registry),
            new CsrfAuthenticationStrategy(csrfRepository)));
}
```

**Khi áp dụng:** thay đúng bean strategy mà filter đang inject; kiểm `SessionRegistry` và events; với nhiều app contexts, tránh trùng bean `SessionAuthenticationStrategy` gây ambiguity. Nếu yêu cầu “chỉ một phiên”, test bằng **hai cookie jars/session IDs độc lập**, không dùng hai tab cùng browser session. Khi chế độ reject=true, user thứ hai cùng account trong session khác phải bị từ chối; nếu cùng session ID login lại, behavior có thể khác và phải kiểm contract registry.

### 10.1 Vì sao phải đăng ký sau fixation?

`ChangeSessionIdAuthenticationStrategy` có thể thay ID từ `S1` sang `S2`. Nếu đăng ký `S1` rồi filter/session store dùng `S2`, registry có thể giữ thông tin không còn tương ứng. Thứ tự chuẩn **concurrent → fixation → register** giúp registry dùng session ID cuối.

### 10.2 Vì sao `ConcurrentSessionFilter` vẫn quan trọng?

Khi policy chọn expire phiên cũ, `ConcurrentSessionControlAuthenticationStrategy` đánh dấu `SessionInformation` expired. Việc đó không tự cắt mọi request đang chạy. `ConcurrentSessionFilter` kiểm session expired ở request sau và gọi logout/expired handler theo cấu hình. Nếu chỉ đánh dấu mà không có cơ chế thực thi, user của phiên cũ có thể tiếp tục như chưa bị hạn chế.

Với `exceptionIfMaximumExceeded=true`, login mới có thể bị từ chối trước khi tạo phiên, nhưng vẫn cần registry cleanup để tránh session đã chết bị tính mãi vào quota.

### 10.3 Principal identity và session registry

Một `SessionRegistryImpl` thường dùng principal object làm key; custom principal không có `equals/hashCode` ổn định có thể khiến hai lần login của **cùng account** bị coi là hai người khác, làm sai giới hạn. Dùng identity ổn định và kiểm contract, hoặc registry mapping theo account ID thích hợp, không dùng một object entity mutable/credential làm key một cách tùy tiện.

Khi user có nhiều tenant, phải quyết định giới hạn tính theo **identity toàn cục**, **account trong tenant**, hay **membership/session grant**. `SessionAuthenticationStrategy` không tự hiểu tenant semantics; policy do ứng dụng xác định.

## 11. SessionFixationProtection cần hiểu sâu hơn một dòng cấu hình

### 11.1 Kịch bản tấn công

```text
Attacker biết session ID S1 trước khi nạn nhân login
           |
           v
Nạn nhân đăng nhập thành công nhưng app GIỮ S1
           |
           v
Attacker có thể cố tái dùng S1 đã được nâng quyền
           |
           v
Session fixation vulnerability

Biện pháp:
  Khi login verified -> đổi ID S1 thành S2
  Không tiếp tục chấp nhận S1 như session authenticated
```

Spring Security thường bật protection tự động cho built-in form login. Nhưng custom authentication flow phải bảo đảm strategy phù hợp đã được kích hoạt. Một password check đúng không chặn được tấn công nếu cookie pre-login bị cố định và ID không đổi sau login.

### 11.2 Chú ý event và listener

Khi session ID đổi, có thể phát `SessionFixationProtectionEvent` và servlet `HttpSessionIdListener` notifications (tùy strategy/container). Nếu có listener quản lý state theo session ID, nó phải xử lý event đúng, không vô tình tạo hai bản ghi cho session cũ/mới.

Nếu session chứa dữ liệu cá nhân/saved request/CSRF token, phải cân nhắc policy giữ hay xóa thuộc tính đó khi identity đổi. `ChangeSessionIdAuthenticationStrategy` chủ yếu thay ID, còn `CsrfAuthenticationStrategy` xử lý CSRF token cũ. Đây là **hai trách nhiệm**.

### 11.3 Khi login lần đầu chưa có session

Nếu request đầu tiên không mang cookie phiên và cũng chưa có `HttpSession`, strategy đổi ID có thể không làm gì. Sau đó `SecurityContextRepository.saveContext` có thể tạo session mới để persist login; cookie mới được gửi khi response chưa commit. Đó không phải “lỗi không đổi session”: không có ID trước login để đổi.

Đừng sửa bằng cách bắt buộc `getSession(true)` trước mọi login nếu business không cần; nó có thể tăng session allocations. Khi có yêu cầu session ID bảo mật, cần test cả **pre-login session có ID** và **login không có session**.

## 12. CSRF khi thay đổi danh tính

`CsrfFilter` kiểm CSRF token cho unsafe HTTP methods theo policy; `CsrfAuthenticationStrategy` xử lý cleanup token khi một authentication mới thành công. Hai lớp này có thời điểm khác nhau:

```text
1. POST /api/login mang CSRF token hợp lệ.
2. CsrfFilter xác minh token (nếu endpoint chịu bảo vệ).
3. AuthenticationManager xác minh password.
4. SessionAuthenticationStrategy:
   - đổi session ID (nếu có)
   - xóa token CSRF trước login theo CsrfAuthenticationStrategy
5. SecurityContextRepository lưu context.
6. Response thành công.
7. SPA cần lấy CSRF token MỚI trước unsafe request tiếp theo
   nếu cookie/header chưa cập nhật.
```

Không vô hiệu CSRF chỉ vì post-login XHR đầu tiên trả 403. Nguyên nhân có thể là frontend tái dùng token đã bị invalidated theo thiết kế. Tạo endpoint/flow lấy token mới đúng origin/session hoặc dùng integration SPA của Spring Security.

Với bearer API không dựa trên browser auto-sent cookie, CSRF threat model khác; tuy nhiên không đồng nghĩa “mọi ứng dụng REST đều có thể tắt CSRF” mà không phân tích cơ chế mang credential.

## 13. Phân biệt session registration với session persistence

| Hành động | API/cơ chế | Dữ liệu đích | Kết quả |
| --- | --- | --- | --- |
| Kiểm giới hạn phiên | `ConcurrentSessionControlAuthenticationStrategy` | `SessionRegistry` | Có cho phép login mới không. |
| Đổi session ID | `ChangeSessionIdAuthenticationStrategy` | Servlet `HttpSession` | ID mới để giảm fixation. |
| Đăng ký phiên | `RegisterSessionAuthenticationStrategy` | `SessionRegistry` | Theo dõi principal/session cho concurrency. |
| Lưu auth | `SecurityContextRepository.saveContext` | Session/repository | Request sau có thể khôi phục `Authentication`. |
| Hiển thị login thành công | `AuthenticationSuccessHandler` | HTTP response | 200/204/302 và cookie tùy repo/container. |

**Nhầm lẫn nguy hiểm:** Có session registry entry **không chứng minh** `SecurityContext` đã được lưu vào `HttpSession`. Ngược lại, một user có context lưu trong session **không chứng minh** session đã được đăng ký cho concurrent-session control.

Các kiểm thử phải xác nhận **cả hai hệ thống** khi sản phẩm yêu cầu chúng, đặc biệt trên nhiều server và sau logout/timeouts.

## 14. Thứ tự với SecurityContextRepository và response commit

Với Spring Security 6 explicit save, `SecurityContextHolderFilter` không tự persist khi bạn thay context. Một custom authentication mechanism phải save sau khi strategy đã chấp nhận, **trước khi response commit**.

Sai:

```java
Authentication verified = manager.authenticate(candidate);
response.sendRedirect("/app");

// Quá muộn: session ID/cookie mới không được bảo đảm.
sessionStrategy.onAuthentication(verified, request, response);
repository.saveContext(context, request, response);
```

Đúng:

```java
Authentication verified = manager.authenticate(candidate);

sessionStrategy.onAuthentication(verified, request, response);

SecurityContext context = holderStrategy.createEmptyContext();
context.setAuthentication(verified);
holderStrategy.setContext(context);
repository.saveContext(context, request, response);

response.sendRedirect("/app");
```

**Đoạn trên là pseudocode tích hợp**: các biến phải được xác định, lỗi được xử lý đúng và strategy chỉ gọi khi verified. Đừng gọi `saveContext` trong `finally` sau khi output stream đã flush. Với `AbstractAuthenticationProcessingFilter` đã được set repo, superclass có trách nhiệm làm việc này trong success path; success handler của bạn không cần tự save.

Response có thể commit bởi `sendRedirect`, `sendError`, `flushBuffer`, việc ghi body vượt buffer, streaming hoặc flush writer. Nếu cookie/session ID cần được gửi, hoàn tất strategy và save trước những thao tác này. Một test login trả 204/302 **chưa đủ**; phải thử request thứ hai mang cookie.

## 15. SessionAuthenticationException: phải xử lý như một đăng nhập không được chấp nhận

`onAuthentication` có thể ném `SessionAuthenticationException`, ví dụ vượt maximum sessions. Khi đó:

1. Không đặt/lưu `Authentication` vừa xác minh vào session của request mới.
2. Không gọi `AuthenticationSuccessHandler`.
3. Chuyển qua flow failure tương ứng, trả mã/UX phù hợp và log nội bộ đã lọc.
4. Không tiết lộ quá mức account/session state cho client nếu có rủi ro enumeration.
5. Không để một phần phiên mới được đăng ký sau failure, đặc biệt nếu custom composite có side effects.
6. Không phản hồi 200 “login OK” rồi ghi chú “không ghi được session” — trạng thái như vậy gây hiểu nhầm và có thể mở lỗ hổng.

Với `AbstractAuthenticationProcessingFilter`, contract của `doFilter` nêu rõ: auth trả về → strategy được gọi → success; exception → unsuccessful flow; return `null` → authentication chưa hoàn tất. Nếu tự viết filter không kế thừa class này, bạn phải giữ semantics tương đương.

### 15.1 Không tự suy ra HTTP code cố định từ SessionAuthenticationException

Chiến lược có thể từ chối vì concurrency. `AuthenticationFailureHandler` của bạn quyết định phản hồi, có thể là 401, 403 hoặc trang thông báo riêng tùy API contract. Đừng tuyên bố framework luôn trả một HTTP code cố định khi session strategy từ chối. Quan trọng là **không cấp phiên authenticated** khi policy đã từ chối.

### 15.2 Vì sao không wrap mọi exception thành BadCredentialsException?

Nếu quá quota phiên, không phải password sai. Public response có thể vẫn chung, nhưng audit/metric nội bộ cần phân biệt `bad_credentials` và `session_policy_denied`. Nếu không, vận hành sẽ tưởng có brute force trong khi thực tế là lỗi SessionRegistry hoặc quota.

## 16. HTTP Basic, JWT, remember-me, MFA và login nhiều bước

### 16.1 HTTP Basic

HTTP Basic thường gửi username/password ở mỗi request. Không nên ngầm coi mọi request Basic như một sự kiện tạo `HttpSession` mới rồi đổi ID/ghi registry. Nếu server dùng flow stateless, session strategy tạo phiên có thể không phù hợp. Chọn cơ chế dựa trên sản phẩm; Basic chỉ truyền Base64 nên **bắt buộc TLS**.

### 16.2 JWT Resource Server

Bearer JWT được verify ở từng request, thường không tạo HttpSession. Chính sách về `exp`, issuer, audience, revocation, grants không nằm trong `SessionAuthenticationStrategy` Servlet. Đừng gọi `ChangeSessionIdAuthenticationStrategy` cho mỗi JWT. Nếu có refresh-token login flow ở Authorization Server, nó có chính sách riêng.

### 16.3 Remember-me

Một remember-me cookie có thể xác thực user khi HttpSession không còn. Liệu có gọi session strategy không phụ thuộc authentication mechanism và cấu hình; đừng đánh đồng với browser form login có username/password. Nếu session registry/concurrent policy cần quản lý remember-me sessions, hãy kiểm luồng cụ thể và test, không trông đợi `SessionManagementFilter` mặc định Spring Security 6 sẽ phát hiện mọi sự kiện.

### 16.4 MFA, OTP và login nhiều bước

Trong flow nhiều bước, việc provider đầu tiên nhận diện username **chưa chắc** là thời điểm cuối để tạo phiên fully authenticated. Tránh đổi session ID/đăng ký authenticated session quá sớm khi chưa hoàn tất MFA/step-up theo chính sách. Xác định rõ sự kiện nào mới được xem là **login được phép**; có thể lưu trạng thái pre-auth hạn chế riêng nhưng không cho nó quyền protected resource.

### 16.5 Re-authentication trong cùng session

Nếu user đã login và xác thực lại để nâng quyền (step-up), phải quy định có gọi strategy lần nữa không. Đổi session ID có thể hữu ích tại thay đổi mức tin cậy, nhưng đăng ký/đếm phiên đồng thời không được tạo duplicate entry sai. Không đơn giản gọi lại mọi delegate vô điều kiện: xem contract của principal, session registry và thời điểm cấp quyền.

## 17. Triển khai production: những giới hạn quan trọng

### 17.1 Cookie và HTTPS

Chiến lược có đổi ID thành công nhưng client vẫn gửi cookie cũ thì request sau có thể anonymous. Kiểm `Set-Cookie` và `Cookie` trên HTTP thực, cùng cấu hình `Secure`, `HttpOnly`, `SameSite`, `Domain`, `Path`, reverse proxy và CORS credentials. Không log toàn bộ session ID/cookie vào production logs.

### 17.2 Session store phân tán

Một `SessionRegistryImpl` in-memory không tự biết sessions trên node khác. Với Spring Session Redis hoặc store phân tán, cần registry/lifecycle events và concurrency mechanisms phù hợp. Test: login node A, login node B cùng account, logout/timeout node C, xác nhận quota và phiên cũ thực sự bị xử lý theo policy.

### 17.3 In-flight requests

Đổi session ID hoặc expire old session **không tự dừng mọi request đang chạy** trên ID cũ. Nếu một thao tác quan trọng đã đi qua filter, cần authorization/freshness check tại service/transaction theo risk policy. `SessionAuthenticationStrategy` xử lý **event login**, không phải revocation tức thời mọi giao dịch.

### 17.4 Session timeout và thay đổi quyền

Một phiên được tạo hợp lệ lúc 09:00 có thể giữ authorities snapshot sau khi admin thu hồi role lúc 09:05. Session authentication strategy chỉ chạy lúc login mới; **không phải revalidation mỗi request**. Nếu sản phẩm yêu cầu disable/revoke role có hiệu lực nhanh, cần auth version/session invalidation/per-request checks phù hợp.

### 17.5 Quan hệ với multi-tenancy

Nếu user thuộc nhiều tenant, session registry và principal equality phải dùng đúng namespace; ví dụ account ID scoped theo tenant hoặc global identity ID ổn định. Không lấy `tenant_id` từ header client rồi dùng để “đổi phiên đang authenticated” khi chưa kiểm membership và quyền. Session fixation strategy không tự cung cấp tenant isolation.

### 17.6 Không log credential

Debug nên dùng request ID, principal ID đã kiểm, strategy class, success/failure outcome, session event type, không log raw password, JWT, session cookie, full serialized `SecurityContext` hoặc password hash. `Authentication.getCredentials()` và session IDs là dữ liệu nhạy cảm.

## 18. Các anti-pattern phổ biến

**A. Chỉ authenticate rồi trả 200.**

```java
// SAI nếu custom stateful login có session policy/persistence.
Authentication auth = manager.authenticate(candidate);
return ResponseEntity.ok("success");
```

Password check có thể đúng nhưng fixation/concurrency/context persistence chưa được thực hiện. Với `AbstractAuthenticationProcessingFilter`, gắn strategy và repo; với controller, gọi đúng lifecycle thủ công.

**B. Gọi onAuthentication trước authenticate.**

```java
// SAI: user/client chưa được chứng minh.
sessionStrategy.onAuthentication(candidate, request, response);
Authentication verified = manager.authenticate(candidate);
```

**C. Gọi hai lần sau login.**

```java
// SAI: superclass đã gọi strategy nhưng success handler lại gọi tiếp.
filter.setSessionAuthenticationStrategy(sessionStrategy);
filter.setAuthenticationSuccessHandler((req, resp, auth) -> {
    sessionStrategy.onAuthentication(auth, req, resp); // DOUBLE CALL
    resp.setStatus(204);
});
```

**D. Đăng ký trước khi đổi session ID.**

```text
SAI: register(S1) -> change ID S1 thành S2
ĐÚNG: concurrent check -> fixation (S2) -> register(S2)
```

**E. Bỏ qua exception vì password đúng.**

```java
// SAI: session policy đã từ chối nhưng vẫn lưu auth.
try {
    sessionStrategy.onAuthentication(auth, request, response);
} catch (SessionAuthenticationException ignored) {
}
repository.saveContext(context, request, response);
```

**F. Dùng ChangeSessionId như bộ tạo session bắt buộc.**

```text
Login chưa có HttpSession: không có ID cũ để đổi.
Khi cần persist, repository/cấu hình session sẽ quyết định tạo session.
```

**G. Chỉ dùng SessionRegistry để giữ login.** Registry không phải `SecurityContextRepository`; request tiếp theo vẫn cần đúng context/token.

**H. Kích hoạt trên mọi request JWT/Basic.** Có thể gây session churn/CSRF token churn và đánh sai quota; strategy dùng khi auth event phù hợp, không phải mỗi lần nhìn thấy `Authentication`.

**I. Thêm filter dưới dạng `@Component` và `http.addFilterAt` cùng lúc.** Có thể dẫn tới chạy hai lần trong container/chain; phải có một đường đăng ký duy nhất.

**J. Tắt CSRF hoặc fixation để tránh lỗi integration test.** Điều này có thể làm test pass bằng cách xóa bảo vệ; thay vào đó kiểm flow, token và session lifecycle đúng.

## 19. Checklist debug khi custom login không ổn

1. Request có đi qua **đúng SecurityFilterChain** không? Các matchers/filters có đè nhau không?
2. Custom filter nào nhận `POST /api/login`? Nó kế thừa `AbstractAuthenticationProcessingFilter` hay tự làm từ `OncePerRequestFilter`?
3. `AuthenticationManager.authenticate` có trả kết quả verified hay ném `AuthenticationException`?
4. Nếu filter là `AbstractAuthenticationProcessingFilter`, đã gọi `setSessionAuthenticationStrategy` với instance đúng chưa? Mặc định chưa cấu hình có thể là no-op.
5. Có bị gọi strategy **hai lần** do success handler/controller hoặc SessionManagementFilter custom không?
6. Composite delegates có đúng thứ tự **concurrent → fixation → register → CSRF** theo policy không?
7. `SessionAuthenticationException` có bị nuốt/biến thành success không?
8. Pre-login request có HttpSession thật không? Nếu không, không thể yêu cầu change-ID event.
9. `SecurityContextRepository` của login filter có đúng với repository của chain không? `saveContext` có chạy **trước response commit** không?
10. `SecurityContext` có được nạp ở request tiếp theo mang cookie không? Cookie attributes/proxy/session store đúng chưa?
11. `SessionRegistry` có nhận session destroy/change events không, có đủ nhiều node không?
12. Nếu csrf()/login POST trả 403, có phải `CsrfFilter` chặn trước filter không?
13. Nếu token CSRF sau login không còn hợp lệ, client đã fetch token mới chưa?
14. Filter có được đăng ký hai lần dưới dạng Servlet filter và Security filter không?
15. Log có chứa raw secret/session cookie không? Nếu có, giảm/chặn thông tin nhạy cảm.

Để xác minh chính xác, nên bật logging framework bảo mật **ở môi trường test cô lập**, dùng request ID, quan sát thứ tự sự kiện với không có credential leak; tránh in full security context ra console.

## 20. Ma trận kiểm thử cần có

| Tình huống | Bằng chứng cần thấy |
| --- | --- |
| Password đúng với session đã có | `onAuthentication` chạy và session ID thay đổi; login thành công. |
| Password đúng không có session ban đầu | Login vẫn lưu context nếu repo cho phép tạo session; không nhất thiết có change-ID event. |
| Password sai | Strategy không chạy, không authenticated context, failure response. |
| Account disabled/locked | Provider từ chối; session strategy không được áp dụng cho login mới. |
| Thiếu CSRF trên login cookie flow | `CsrfFilter` từ chối trước authentication. |
| Login thành công với CSRF trước login | CSRF token cũ được invalidated theo policy; token mới có thể lấy lại. |
| Request sau với session cookie mới | SecurityContextRepository nạp principal đúng. |
| Request sau không cookie | Không được thừa hưởng principal của thread/request trước. |
| Role USER gọi ADMIN | 403 dù đã login thành công. |
| Role ADMIN gọi ADMIN | 200 nếu authorization tương ứng. |
| Hai user khác nhau trên thread pool | Không lẫn principal/HttpSession/authorities. |
| Số session đã đạt max, reject mode | `SessionAuthenticationException` ngăn login mới, không save context. |
| Số session đã đạt max, expire-old mode | Phiên cũ bị đánh dấu và xử lý ở request sau theo filter/policy. |
| Composite bị reject ở delegate đầu | Fixation/register/success không chạy tiếp. |
| Đổi session ID trước register | Registry lưu ID cuối đúng. |
| Session hết hạn/logout | Registry cleanup, quota không bị kẹt và request cũ không được vào. |
| Login node A, gọi API node B | Context và registry vẫn đúng theo kiến trúc distributed. |
| MFA chưa hoàn tất | Không tạo session fully authenticated trước khi policy cho phép. |
| Response redirect trước save | Test phát hiện cookie/session persistence lỗi. |
| Stateless JWT request | Không tự tạo session/đổi ID chỉ vì token hợp lệ. |
| Role bị thu hồi khi session cũ còn sống | Freshness/revalidation policy riêng có tác dụng. |
| Cookie Secure/SameSite/path | Client nhận/gửi cookie đúng, không leak token trong log. |

## 21. Bài tập tư duy có lời giải

**Câu 1.** Một custom login filter gọi `AuthenticationManager.authenticate` thành công, nhưng không gọi session strategy. Người dùng vẫn đọc được `/api/me` bằng session. Hệ thống đã đủ an toàn chưa?

**Đáp án:** Chưa chắc. Authentication và context persistence có thể hoạt động, nhưng session fixation/concurrency/CSRF token rotation vẫn có thể bị bỏ. Cần kiểm strategy nào thật sự đã chạy và test những bảo vệ yêu cầu.

**Câu 2.** Với `AbstractAuthenticationProcessingFilter` trong Spring Security 6, strategy chạy trước hay sau `successfulAuthentication`?

**Đáp án:** **Sau** khi `attemptAuthentication` trả `Authentication` thành công, **trước** `successfulAuthentication`. Nếu lỗi/return null, không đi vào success lifecycle như một authentication hoàn chỉnh.

**Câu 3.** Vì sao một user sai password không được đổi session ID chỉ bởi việc submit login?

**Đáp án:** Session strategy cho **login thành công**. Nếu mọi login sai đều thay ID/đăng ký session, attacker có thể gây session churn hoặc tác động các session mà không cần chứng minh identity.

**Câu 4.** Bật `MODE_GLOBAL` để giữ context giữa requests có giải quyết SessionAuthenticationStrategy không?

**Đáp án:** Không. Global context có nguy cơ rò principal giữa users. Session strategy và repository giải quyết các nhiệm vụ khác; Servlet nên dùng holder strategy mặc định.

**Câu 5.** Composite có concurrent check, fixation, register. Thứ tự đúng là gì?

**Đáp án:** `ConcurrentSessionControlAuthenticationStrategy` → `ChangeSessionIdAuthenticationStrategy` hoặc fixation strategy phù hợp → `RegisterSessionAuthenticationStrategy`. CSRF cleanup có thể đặt sau đó theo policy. Nếu concurrent check từ chối, các bước sau không chạy.

**Câu 6.** Admin đặt max sessions = 1, user mở hai tab cùng browser. Vì sao chưa chắc bị giới hạn?

**Đáp án:** Hai tab có thể chia sẻ **cùng cookie `JSESSIONID`** và do đó cùng một `HttpSession`. Muốn test hai phiên, dùng hai cookie stores/thiết bị hoặc trình duyệt độc lập.

**Câu 7.** `ConcurrentSessionControlAuthenticationStrategy` ném `SessionAuthenticationException` nhưng code bắt rồi lưu `SecurityContext`. Sai ở đâu?

**Đáp án:** Login mới đã bị policy từ chối; lưu context authenticated làm vượt giới hạn. Phải chấm dứt success flow và phản hồi failure.

**Câu 8.** Chỉ gọi `RegisterSessionAuthenticationStrategy` có tự giữ user đăng nhập ở HTTP request sau không?

**Đáp án:** Không. Nó ghi vào `SessionRegistry`, còn persistence của `Authentication` qua requests cần `SecurityContextRepository`/session hoặc cơ chế token tương ứng.

**Câu 9.** Một request login đầu tiên không có HttpSession trước auth. `ChangeSessionIdAuthenticationStrategy` không đổi ID, nhưng sau đó user vẫn login được. Có mâu thuẫn không?

**Đáp án:** Không có ID cũ để đổi. Repository có thể tạo session mới khi save context, tùy policy; phải kiểm cookie và request sau, không lấy việc “không có change event” làm kết luận không bảo vệ.

**Câu 10.** Frontend POST thay đổi dữ liệu ngay sau login và bị CSRF 403 dù login thành công. Vì sao?

**Đáp án:** `CsrfAuthenticationStrategy` có thể đã xóa token CSRF trước login; frontend đang dùng token cũ. Cần lấy token mới theo thiết kế SPA/cookie flow sau khi authentication state đổi.

**Câu 11.** Bộ lọc custom đã gắn strategy vào superclass, success handler lại gọi strategy. Có ổn không?

**Đáp án:** Không. Superclass đã kích hoạt trên success, nên gọi thêm có thể thay đổi session/CSRF/registry lặp. Loại bỏ gọi trùng ở success handler.

**Câu 12.** User dùng JWT stateless, mỗi request đều có `JwtAuthenticationToken`. Có nên gọi `ChangeSessionIdAuthenticationStrategy` mỗi request?

**Đáp án:** Không. JWT Resource Server phải kiểm token theo cơ chế bearer, thường không có session login cần đổi ID. Nếu có một OAuth2 interactive login flow riêng, xác định session policy riêng của nó.

**Câu 13.** Nếu đã dùng strategy chống fixation, có cần `SecurityContextRepository.saveContext` không?

**Đáp án:** Có nếu cần stateful login qua request mới và dùng explicit-save. Chống fixation xử lý session ID; repository save mới persist context. Built-in filter có thể save giúp nếu đã được cấu hình repository đúng.

**Câu 14.** Tại sao test concurrency phải kiểm cả logout/session destroy?

**Đáp án:** Registry giữ mapping active sessions. Nếu không cleanup khi session bị hủy, user có thể bị từ chối login dù không còn phiên sống. Cần listener/shared registry và test lifecycle.

## 22. Checklist triển khai production

1. **Xác định auth event**: request nào thực sự tạo login mới, không chạy strategy trên mọi request authenticated.
2. **Provider đáng tin**: login credential/MFA/identity được xác minh trước session strategy.
3. **Owner của lifecycle**: built-in `AbstractAuthenticationProcessingFilter` gọi strategy; custom controller/filter tự viết phải gọi, nhưng không duplicate.
4. **Chọn fixation protection**: `changeSessionId` trên Servlet container hiện đại; không dùng `none` tùy tiện.
5. **Composite đúng thứ tự**: concurrent check → fixation → register → CSRF; fail short-circuit.
6. **Session registry**: principal ID ổn định, session lifecycle cleanup, concurrency policy reject/expire được định nghĩa, cluster semantics rõ.
7. **Context persistence**: cùng `SecurityContextRepository` ở chain và login; explicit save trước response commit.
8. **Cookie policy**: HTTPS, Secure, HttpOnly, SameSite, Domain/Path, proxy/CORS và session timeout.
9. **CSRF**: giữ CsrfFilter cho cookie-auth, xử lý token refresh sau login.
10. **Errors**: `SessionAuthenticationException` và password failure không được trở thành success; public message không rò secrets.
11. **Filter registration**: không đăng ký hai lần; match URL/method đúng; kiểm thứ tự CsrfFilter/authentication.
12. **Stateful vs stateless**: không tạo HttpSession cho mọi JWT request; OAuth grants/refresh token có policy riêng.
13. **MFA/step-up**: định nghĩa thời điểm cấp fully authenticated session, không cấp quyền trước khi đủ yếu tố.
14. **Kiểm thử**: success/failure, before/after ID, saved context, concurrent sessions, CSRF, cookie, logout, multiple nodes.
15. **Freshness**: role revoked/account disabled sau login cần cơ chế reauthorization/revocation khác, không trông chờ session strategy.
16. **Security review**: audit session lifecycle, không log token/password/session IDs và theo dõi metric auth failure/session denial.

## 23. Tài liệu chính thức để kiểm chứng

- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): giải thích `SessionManagementFilter`, thay đổi Spring Security 6, session fixation, concurrency, explicit save.
- [Spring Security 6.5 — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): trình tự auth success, strategy, context, repository và success handlers.
- [Spring Security 6.5 — AbstractAuthenticationProcessingFilter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html): strategy được gọi ngay sau `attemptAuthentication` thành công; `setSessionAuthenticationStrategy`, `setSecurityContextRepository`.
- [Spring Security 6.5 — SessionAuthenticationStrategy Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/SessionAuthenticationStrategy.html): hợp đồng `onAuthentication` và `SessionAuthenticationException`.
- [Spring Security 6.5 — CompositeSessionAuthenticationStrategy Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/CompositeSessionAuthenticationStrategy.html): ordering khuyến nghị và short-circuit.
- [Spring Security 6.5 — ChangeSessionIdAuthenticationStrategy Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/ChangeSessionIdAuthenticationStrategy.html): `HttpServletRequest.changeSessionId` và fixation.
- [Spring Security 6.5 — ConcurrentSessionControlAuthenticationStrategy Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/ConcurrentSessionControlAuthenticationStrategy.html): maximum sessions, reject hoặc expire sessions cũ.
- [Spring Security 6.5 — RegisterSessionAuthenticationStrategy Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/RegisterSessionAuthenticationStrategy.html): thêm session vào registry sau khi ID cuối đã có.
- [Spring Security 6.5 — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): kiểm CSRF và reset token sau authentication.
- [Spring Security 6.5 — Session Management Migrations](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html): explicit-save và thay đổi migration từ Spring Security 5.
- [Spring Security 6.5 — MockMvc Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc.html): `csrf()` và security integration tests.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookie, fixation, timeout, session lifecycle.

**Kết luận:** `SessionAuthenticationStrategy` là **bước chính sách phiên của một sự kiện xác thực mới thành công**, không phải bộ xác minh credential và không phải nơi lưu `SecurityContext` giữa mọi request. Trong Spring Security 6, authentication mechanism phải gọi chiến lược phù hợp. Với `AbstractAuthenticationProcessingFilter`, hãy cấu hình nó qua `setSessionAuthenticationStrategy` để framework gọi **sau `attemptAuthentication` và trước `successfulAuthentication`**. Với custom controller/`OncePerRequestFilter`, hãy tự gọi **đúng một lần sau khi credential được xác minh**, chấp nhận rejection như failure, sau đó tạo/lưu context trước response commit. Giữ thứ tự **concurrent check → fixation → register → CSRF**, kiểm bằng login request và request có cookie tiếp theo, đồng thời tách bạch policy session với JWT/stateless và authorization.