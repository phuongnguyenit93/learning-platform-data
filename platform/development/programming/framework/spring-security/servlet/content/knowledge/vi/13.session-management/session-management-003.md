# Vòng đời phiên từ đăng nhập đến hết hạn hoặc bị thu hồi trong Spring Security Servlet

## 1. Bức tranh tổng thể

Trong ứng dụng web dùng **Spring Security Servlet** và đăng nhập bằng biểu mẫu, phiên HTTP giúp trình duyệt không phải gửi lại mật khẩu ở mỗi request. Tuy nhiên, “đang có cookie”, “server còn HttpSession”, “đã có Authentication”, “chưa hết hạn” và “chưa bị thu hồi” **không phải cùng một trạng thái**.

Một phiên có thể đi qua các giai đoạn:

```text
Browser chưa đăng nhập
      |
      | GET trang công khai / request bị chặn
      v
HttpSession có thể chưa có, hoặc đã được tạo cho CSRF / saved request
      |
      | POST /login + CSRF token + thông tin đăng nhập
      v
Authentication thành công
      |
      +--> session fixation protection (đổi session ID theo policy)
      +--> lưu SecurityContext vào repository/session phù hợp
      +--> browser nhận/duy trì cookie phiên
      |
      v
Phiên đã xác thực
      |
      +--> mỗi request hợp lệ: nhận diện session,
      |    nạp SecurityContext, authorization, cập nhật truy cập
      |
      +--> không hoạt động quá lâu: hết hạn do timeout
      |
      +--> người dùng POST /logout: logout/invalidate
      |
      +--> quản trị / security incident: thu hồi phiên
      |
      +--> policy concurrent sessions: đánh dấu phiên cũ hết hiệu lực
      |
      v
Request sau khi phiên không còn hợp lệ:
      anonymous / entry point / login lại (tùy cấu hình)
```

Mục tiêu bài học:

1. Phân biệt **Servlet HttpSession**, **session cookie**, **SecurityContext**, **Authentication** và **SessionRegistry**.
2. Theo dõi chính xác phiên từ lúc được tạo, qua login, các request kế tiếp, đến logout, timeout hoặc thu hồi.
3. Hiểu **session fixation protection**, session ID rotation, idle timeout và chính sách concurrent sessions.
4. Phân biệt **xóa session thật sự** với **đánh dấu SessionInformation là expired**.
5. Cấu hình và kiểm thử vòng đời session trong Spring Boot 3 / Spring Security 6 / Java 17.
6. Tránh các lỗi bảo mật: cookie không an toàn, logout bằng GET, nhận diện session sai, quản trị nhiều node và khôi phục xác thực ngoài ý muốn.

Phạm vi chính là **form login dựa trên HTTP session**. HTTP Basic hoặc bearer token stateless có thể không cần lưu `Authentication` vào session theo cơ chế này.

## 2. Năm đối tượng dễ bị nhầm lẫn

| Thành phần | Vai trò | Điều không nên suy luận |
| --- | --- | --- |
| `HttpSession` | Kho trạng thái phiên Servlet phía server, có session ID, thuộc tính, timeout | Có session không có nghĩa đã đăng nhập. |
| `JSESSIONID` hoặc cookie session khác | Cách browser mang định danh session giữa request | Cookie chỉ là định danh; một cookie cũ không bảo đảm session còn tồn tại. |
| `Authentication` | Thông tin principal, trạng thái xác thực và authorities | Không đồng nghĩa session hoặc cookie. |
| `SecurityContext` | Chứa Authentication được sử dụng khi xử lý request | Thread-local hiện tại không tự kéo dài sang request mới. |
| `SecurityContextRepository` | Tải/lưu SecurityContext ở nơi phù hợp, thường có session-backed delegate | Không tự quản lý toàn bộ logout, concurrent sessions và chính sách thu hồi. |
| `SessionRegistry` (nếu dùng) | Theo dõi thông tin session để áp dụng concurrent-session policy | Một registry không tự xóa mọi HTTP session ngay tại thời điểm gọi `expireNow()`. |

### 2.1. HttpSession là khái niệm của Servlet, không phải của riêng Spring Security

`HttpSession` thuộc `jakarta.servlet.http`. Container Servlet như Tomcat, Jetty hoặc Undertow quản lý vòng đời session. Các thao tác điển hình:

```java
HttpSession existing = request.getSession(false);
HttpSession createdIfNeeded = request.getSession(true);
int idleSeconds = createdIfNeeded.getMaxInactiveInterval();
long lastAccessedMillis = createdIfNeeded.getLastAccessedTime();
```

Đây là **đoạn minh họa đặt trong mã có sẵn biến `HttpServletRequest request`**, không phải lớp Java chạy độc lập.

- `getSession(false)` trả session hiện có nếu tồn tại và hợp lệ, nếu không là `null`; không tự tạo session.
- `getSession(true)` tạo session nếu chưa có.
- `getMaxInactiveInterval()` trả số giây khoảng không hoạt động tối đa theo policy hiện hành; giá trị âm thường biểu thị không tự timeout theo inactivity.
- `getLastAccessedTime()` là thời điểm lần truy cập gần nhất theo container; không dùng như bằng chứng tuyệt đối về hoạt động của người dùng, và không đủ để xác thực phiên.

### 2.2. Authentication và SecurityContext tồn tại trong request hiện tại

Spring Security thường đọc ngữ cảnh từ `SecurityContextRepository` tại đầu đường xử lý rồi làm `Authentication` có sẵn qua `SecurityContextHolder`. Khi request hoàn tất, holder của thread xử lý phải được dọn theo cơ chế framework.

Ví dụ, một user đã đăng nhập gửi:

```text
GET /account
Cookie: JSESSIONID=<id>

Servlet container tìm HttpSession
    |
    v
SecurityContextRepository nạp SecurityContext
    |
    v
SecurityContextHolder cho request hiện tại thấy Authentication
    |
    v
AuthorizationFilter kiểm tra quyền
    |
    v
Controller nhận principal
    |
    v
SecurityContextHolder được clear khi hoàn tất xử lý
```

`SecurityContextHolder` mặc định dựa vào thread-local; nó **không thay thế repository**. Nếu tạo Authentication trong một custom login handler mà không lưu context theo cơ chế explicit-save phù hợp, request hiện tại có thể thành công nhưng request sau bị coi là anonymous.

### 2.3. Session cookie không chứa toàn bộ hồ sơ user

Trong mô hình thông dụng, browser giữ một session identifier, còn state được giữ phía server. Không nhét password, secret hoặc dữ liệu đặc quyền vào cookie. Kẻ có session ID hợp lệ có thể chiếm quyền sử dụng phiên, nên session ID/cookie cần được bảo vệ như một bí mật.

Với API dùng JWT tự mang claims hoặc token khác, cơ chế lifecycle/revocation có thể hoàn toàn khác; không áp đặt logic `HttpSession.invalidate()` cho token độc lập.

## 3. Trước khi đăng nhập: session có thể đã tồn tại

Một sai lầm phổ biến là “chỉ khi login thành công thì HttpSession mới được tạo”. Trong nhiều ứng dụng Servlet, session có thể xuất hiện **trước authentication**.

Ví dụ:

1. Browser mở `GET /private` khi chưa đăng nhập.
2. `ExceptionTranslationFilter` có thể lưu URL gốc bằng `RequestCache`, ví dụ `HttpSessionRequestCache`.
3. Trang form có thể cần CSRF token; tùy `CsrfTokenRepository` và cách sử dụng, session cũng có thể được tạo để giữ token.
4. Browser nhận cookie session dù chưa có `Authentication` được xác thực.

Do đó, dùng biểu thức “có `JSESSIONID` = đã đăng nhập” sẽ gây lỗi. Authorization phải dựa vào `Authentication` và policy, không dựa vào sự hiện diện của cookie.

Một ví dụ hai request trước login:

```text
GET /private
    -> 302 /login
    -> có thể có HttpSession để giữ SavedRequest

GET /login
    -> 200 form login
    -> có thể tạo/lấy CSRF token từ session
    -> user vẫn chưa authenticated
```

Các từ **“có thể”** là chủ ý: chính sách session, lazy CSRF handling, RequestCache, container và loại authentication ảnh hưởng việc session được tạo ở thời điểm nào.

## 4. Từ POST /login đến một phiên đã xác thực

Giả sử ứng dụng bật form login mặc định:

```text
POST /login
  username=reader
  password=...
  _csrf=...

UsernamePasswordAuthenticationFilter
       |
       v
AuthenticationManager / AuthenticationProvider
       |
       +-- sai thông tin: authentication failure
       |   thường redirect /login?error
       |
       +-- đúng thông tin:
            |
            v
       SessionAuthenticationStrategy
         session fixation protection /
         concurrent-session handling nếu được cấu hình
            |
            v
       Tạo SecurityContext chứa Authentication
            |
            v
       Lưu context bằng SecurityContextRepository
            |
            v
       AuthenticationSuccessHandler
         redirect về SavedRequest hoặc default success target
```

Đây là luồng **khái niệm**. Thứ tự chi tiết giữa các strategy hoặc filter tùy phiên bản và cấu hình. Điểm cần nhớ: xác thực thành công là **một sự kiện**, còn việc ghi state, bảo vệ session ID và redirect là những bước liên quan nhưng khác nhau.

### 4.1. Session fixation protection: vì sao đổi session ID?

Session fixation là tấn công trong đó attacker cố khiến nạn nhân dùng session ID mà attacker đã biết trước khi login. Nếu server giữ nguyên ID đó khi biến session chưa xác thực thành session có quyền, attacker có thể tiếp tục dùng ID đã biết.

Với Servlet hỗ trợ phù hợp, Spring Security có thể gọi chiến lược **`changeSessionId()`** sau xác thực thành công để thay đổi định danh session mà vẫn duy trì dữ liệu cần thiết của session.

```text
Before login:
  HttpSession ID = S_old
  authenticated = false

Successful login:
  session fixation protection

After login:
  HttpSession ID = S_new
  authenticated = true
  S_old không còn là ID đang hợp lệ của session đó
```

**Đừng hardcode hoặc ghi session ID vào log.** Nó là credential hiệu lực của browser. Trong test, có thể xác minh session ID đã thay đổi khi cấu hình/container hỗ trợ; không nên dựa vào một chuỗi ID cố định.

### 4.2. Các chiến lược và đánh đổi

Những lựa chọn thông dụng trong Spring Security Servlet:

- `changeSessionId`: dùng cơ chế Servlet đổi ID của session hiện có; thường phù hợp với Servlet hiện đại.
- `migrateSession`: tạo session khác, chuyển các thuộc tính theo chiến lược của framework.
- `newSession`: tạo session mới và tránh sao chép tùy tiện các attributes ứng dụng cũ (chi tiết tùy implementation).
- `none`: vô hiệu hóa session fixation protection; **không nên chọn mặc định** vì có thể làm tăng rủi ro fixation.

Không bật `none` chỉ để giữ nguyên ID trong test. Khi migratation có các thuộc tính trong session như giỏ hàng, ngôn ngữ hoặc saved request, cần test thực tế chiến lược đã chọn để tránh mất state hoặc mang dữ liệu không mong muốn sang session mới.

### 4.3. Lưu context khác với lưu session ID

`SecurityContextRepository` có thể lưu `SecurityContext` vào `HttpSession`. `SessionAuthenticationStrategy` hỗ trợ chính sách session khi login. Cookie/ID do Servlet container xử lý. Ba cơ chế phối hợp, nhưng không phải cùng một API.

Trong Spring Security 6, `SecurityContextHolderFilter` thường liên quan **explicit save**; với form login chuẩn, authentication filter của framework có logic lưu context. Nếu tự viết custom authentication, cần bảo đảm `SecurityContextHolder.setContext` và `securityContextRepository.saveContext(context, request, response)` được thực hiện đúng lúc trước response commit.

## 5. Phiên được sử dụng và làm mới hoạt động thế nào?

Sau login, browser gửi cookie session trong những request tiếp theo cùng phạm vi cookie:

```text
GET /account  Cookie: JSESSIONID=<id>
  |
  +--> container tìm session
  +--> SecurityContextRepository nạp Authentication
  +--> Spring Security quyết định có đủ quyền không
  +--> controller trả response
  +--> container cập nhật last access theo semantics của nó
```

Vòng đời này thường là **sliding idle timeout**: mỗi lần request truy cập session đúng cách có thể kéo dài thời điểm hết hạn do không hoạt động. Tuy nhiên:

- Không phải mọi request asset hoặc background polling đều nhất thiết truy cập cùng session.
- Một request liên tục của SPA có thể vô tình giữ session sống quá lâu, tùy routing và policy.
- Hết hạn vì inactivity không phải “đúng 30 phút kể từ khi login” nếu session liên tục được sử dụng.
- `HttpSession` không mặc định có **absolute maximum lifetime**; nếu sản phẩm cần phiên kết thúc sau một khoảng thời gian tuyệt đối, phải có policy bổ sung.
- JavaScript timer hoặc đồng hồ UI không phải nguồn sự thật; server/container mới quyết định session có hợp lệ hay không.

### 5.1. Idle timeout khác absolute timeout

Ví dụ:

```text
Policy idle timeout = 30 phút

10:00  login
10:10  GET /account        -> được truy cập
10:25  GET /notifications  -> nếu truy cập session, idle timer lại được cập nhật
10:50  GET /account        -> có thể vẫn hợp lệ vì lần trước là 10:25
11:21  GET /account        -> có thể hết hạn do 31 phút không hoạt động
```

**Đây là ví dụ giả định**: timestamp chính xác và thời điểm container quét/invalidate session phụ thuộc triển khai, môi trường và cách session được truy cập. Không bảo đảm session bị xóa đúng tại giây thứ 1.800 nếu không có request.

**Absolute timeout** đặt giới hạn từ sự kiện phát sinh (login hoặc tạo session), ví dụ không chấp nhận quá 8 giờ dù user liên tục hoạt động. Đây là yêu cầu riêng và không được bảo đảm chỉ bằng `server.servlet.session.timeout`.

### 5.2. Quan sát timeout bằng Servlet API

Trong mã đã có `HttpSession session`:

```java
int seconds = session.getMaxInactiveInterval();
session.setMaxInactiveInterval(30 * 60);
```

Đây là ví dụ về thiết lập **idle timeout theo giây cho một session**, không phải lớp độc lập. Cần chắc chắn không vô tình ghi đè chính sách session chung trong code nghiệp vụ.

## 6. Những con đường khiến phiên không còn sử dụng được

### 6.1. Hết hạn vì không hoạt động (idle expiration)

Container hoặc session store không còn coi session là hợp lệ vì thời gian từ lần truy cập gần nhất vượt ngưỡng. Browser có thể vẫn gửi cookie ID cũ, nhưng server không còn nạp được Authentication tương ứng; request thường bị xem là chưa đăng nhập.

Timeout **không phải** logout do người dùng chủ động; không dựa vào sự kiện logout để phát hiện mọi phiên hết hạn.

### 6.2. Logout do chủ phiên yêu cầu

Một POST logout hợp lệ có thể chạy `LogoutFilter` và các `LogoutHandler`, clear authentication, invalidate HttpSession, dọn SecurityContext repository và xóa cookie theo cấu hình. Sau đó, session cũ không nên còn là căn cứ chứng minh user đã đăng nhập.

**Gửi yêu cầu POST + CSRF token** là cách mặc định phổ biến khi CSRF bật. Không biến GET `/logout` thành lệnh logout gây side effect mà không đánh giá CSRF.

### 6.3. Thu hồi bởi quản trị viên hoặc chính sách an ninh

Ví dụ account bị khóa, người dùng báo mất thiết bị, mật khẩu bị lộ, hoặc hệ thống phát hiện hoạt động bất thường. Cần khả năng làm một hay nhiều phiên không còn sử dụng được.

Có nhiều cấp độ:

1. **Đánh dấu phiên expired** trong `SessionRegistry`; cấu hình concurrent session control có thể phát hiện và chấm dứt request khi phiên được dùng lại.
2. **Xóa/invalidate session thực tế** trong kho lưu session phù hợp để lần request mới không khôi phục được Authentication.
3. **Thu hồi token độc lập** như remember-me token hay bearer token, nếu ứng dụng có dùng. Hủy HttpSession không mặc nhiên thu hồi mọi token.

Nói “đã revoke” nhưng chỉ cập nhật một boolean trong bảng accounts mà mọi session cũ vẫn được tin tưởng là **chưa đủ** nếu yêu cầu là chặn ngay tất cả request sau đó.

### 6.4. Hết hiệu lực vì chính sách concurrent sessions

Ví dụ tài khoản chỉ được dùng tối đa một phiên. Khi login từ browser khác, server có thể từ chối login mới hoặc đánh dấu phiên cũ expired tùy policy. Phần này **khác** idle timeout và khác lệnh logout thủ công.

### 6.5. Restart, failover hoặc lỗi session store

Nếu session được lưu trong bộ nhớ của một JVM, restart có thể làm mất session. Trong hệ thống nhiều node, cookie có thể đưa request tới node khác không biết session nếu không có sticky routing hoặc kho session chia sẻ. Đó là **mất khả năng khôi phục phiên**, không đồng nghĩa user đã chủ động logout.

## 7. Expired, invalid, revoked và logged out: không đánh đồng

| Trạng thái / hiện tượng | Cơ chế thường gặp | Có thể quan sát khi request tiếp theo | Lưu ý |
| --- | --- | --- | --- |
| Idle timeout | Servlet container/session store hết hạn do không hoạt động | Session ID không được chấp nhận, user anonymous hoặc redirect login | Thời điểm cleanup có thể không trùng đúng một mốc trên đồng hồ. |
| Logout | `LogoutFilter` / logout handlers invalidate session và clear context | Không khôi phục user từ session đã hủy | Browser có thể còn cookie stale nếu cookie clearing không khớp path/domain. |
| SessionInformation.expireNow | `SessionRegistry` đánh dấu thông tin session là expired | `ConcurrentSessionFilter` có thể xử lý phiên expired khi request sau đi qua | Đánh dấu không phải xóa session lưu trong mọi hệ thống tức thì. |
| Xóa session trong kho phân tán | API session store như `SessionRepository` phù hợp | Request sau không đọc được session | Cần kiểm tra cache, replication, race request đang chạy. |
| Cookie/session ID stale | Client gửi định danh server không còn biết | Anonymous, invalid session handling tùy cấu hình | Không dùng cookie tồn tại làm bằng chứng quyền. |
| User bị khóa trong DB | Thay trạng thái account | Login mới thường bị từ chối; session cũ có thể vẫn hoạt động | Cần policy revalidation/revocation cho session hiện hành. |
| Xóa access token riêng | Blacklist/revocation theo cơ chế token | Kết quả tùy token verifier | Không xử lý bằng `HttpSession.invalidate()` nếu token độc lập. |

### 7.1. "Invalid session" không nhất thiết có nghĩa user vừa logout

Một cấu hình `invalidSessionUrl("/session-invalid")` có thể xử lý khi client gửi ID phiên cũ không còn hợp lệ. Nhưng sau logout, browser đôi khi vẫn mang cookie cũ; nếu cấu hình không xét kỹ, người dùng có thể thấy trang “invalid session” dù họ vừa logout bình thường.

**Đừng trộn** trang thông báo “session expired”, “session invalid” và “logout success” thành một phỏng đoán về nguyên nhân sự kiện. Việc phân biệt chính xác cần trạng thái phía server, policy cookie/session và event logs.

## 8. Logout đúng cách trong Spring Security Servlet

Với form login, cấu hình logout là một phần của security chain:

```java
http.logout(logout -> logout
    .logoutUrl("/logout")
    .logoutSuccessUrl("/login?logout")
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("JSESSIONID")
);
```

Đây là **đoạn cấu hình** bên trong bean `SecurityFilterChain` có `HttpSecurity http`. Nó không phải chương trình chạy độc lập.

Giải thích:

- `logoutUrl("/logout")` chỉ định đường xử lý logout.
- `logoutSuccessUrl("/login?logout")` quyết định nơi redirect sau khi logout thành công trong website.
- `invalidateHttpSession(true)` yêu cầu invalidate session hiện tại.
- `clearAuthentication(true)` dọn Authentication khỏi security context trong luồng logout.
- `deleteCookies("JSESSIONID")` cố yêu cầu browser xóa cookie tương ứng trong response; cookie deletion phụ thuộc tên/path/domain thực tế.

Spring Security có các logout handlers mặc định quản lý `SecurityContext`; không nên tự thực hiện chỉ `SecurityContextHolder.clearContext()` trong controller rồi gọi đó là logout, vì session cũ hoặc repository có thể vẫn chứa Authentication.

**CSRF:** với CSRF protection bật, POST `/logout` cần token hợp lệ. GET `/logout` trong cấu hình mặc định thường phục vụ xác nhận logout thay vì tự logout; chi tiết tùy Spring Security phiên bản và giao diện.

### 8.1. Redirect logout không phải bằng chứng session đã invalidated

Response 302 đến `/login?logout` chỉ thể hiện flow điều hướng. Muốn kiểm chứng server đã invalidate session, test `MockHttpSession.isInvalid()` sau khi POST logout, hoặc quan sát session store/event có kiểm soát.

Ngược lại, nếu cookie không xóa được do Path/Domain, **server-side invalidation** vẫn là yếu tố chính. Cookie stale không được cấp lại quyền chỉ vì còn trong browser.

### 8.2. Logout có thu hồi toàn bộ thiết bị không?

Không. Logout mặc định thường xử lý **phiên của request hiện tại**. Nếu user có session trên laptop và điện thoại, logout trên laptop không tự bảo đảm xóa phiên trên điện thoại.

Yêu cầu “logout all devices” cần một bước thiết kế riêng: quản lý danh sách session, thu hồi trong repository hoặc registry tương ứng, policy đối với remember-me/token, và đảm bảo nhiều node hiểu cùng trạng thái.

## 9. Thu hồi phiên qua SessionRegistry và concurrent sessions

### 9.1. SessionRegistry lưu thứ gì?

Spring Security Servlet có `SessionRegistry` để theo dõi session trong một số cơ chế concurrent-session management. Một implementation thường gặp là `SessionRegistryImpl`.

Các thao tác tiêu biểu:

- `getAllPrincipals()`: tra cứu principal đang được registry theo dõi.
- `getAllSessions(principal, includeExpiredSessions)`: lấy các `SessionInformation` đã đăng ký cho principal.
- `SessionInformation.expireNow()`: **đánh dấu** thông tin session hết hiệu lực.
- `refreshLastRequest(sessionId)` hoặc việc quản lý lifecycle registry trong framework: cập nhật/tracking metadata theo cơ chế phù hợp.

Ví dụ **mã minh họa** với `sessionRegistry` và `principal` đã được xác minh trong application service quản trị:

```java
List<SessionInformation> sessions =
    sessionRegistry.getAllSessions(principal, false);

for (SessionInformation info : sessions) {
    info.expireNow();
}
```

Imports nằm trong `org.springframework.security.core.session` cho `SessionRegistry` và `SessionInformation`, cùng `java.util.List`. Đoạn này **không phải REST controller đầy đủ** và không chứng minh đã thu hồi ngay mọi request hiện đang chạy.

### 9.2. Vì sao expireNow chưa phải xóa session tức thì?

`expireNow()` đánh dấu trong registry. Với `ConcurrentSessionFilter` và chiến lược expired-session phù hợp, **request kế tiếp** của phiên bị đánh dấu có thể bị xử lý, logout/invalidate và redirect theo cấu hình.

Rủi ro cần nhớ:

- Một request đã bắt đầu trước khi bị đánh dấu có thể vẫn tiếp tục nếu không có điểm kiểm tra thêm.
- Nếu request không đi qua chain chứa `ConcurrentSessionFilter`, dấu hiệu expired có thể không được xử lý theo cách bạn mong đợi.
- Registry chỉ nằm trong bộ nhớ của một node có thể không bao phủ các session đang ở node khác.
- Một session không được đăng ký hoặc principal equality không phù hợp sẽ không xuất hiện đúng trong truy vấn.
- Timeout/invalidation event cần được phản ánh vào registry, nếu không dữ liệu có thể stale.

Vì vậy, nếu yêu cầu **thu hồi gần như ngay lập tức và xuyên nhiều node**, cần thiết kế kho session chung hoặc kiểm tra trạng thái revocation ở request boundary phù hợp, thay vì chỉ gọi `expireNow` và khẳng định mọi phiên biến mất ngay.

### 9.3. Giới hạn số phiên đồng thời

Một cấu hình ví dụ có thể thêm vào **web chain**:

```java
http.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(false)
    .expiredUrl("/session-expired")
);
```

Khi `maximumSessions(1)`, mục tiêu là giới hạn một session đăng nhập đồng thời theo principal. Với `maxSessionsPreventsLogin(false)`, một lần login mới có thể khiến phiên cũ bị đánh dấu expired thay vì từ chối login mới. `expiredUrl` là URL điều hướng của expired-session strategy khi yêu cầu bị phát hiện hết hiệu lực.

Đây là **mảnh cấu hình** để học, không phải hành vi đã được bật trong ứng dụng hoàn chỉnh bên dưới. Muốn dùng production cần xem thêm `SessionRegistry`, `HttpSessionEventPublisher`, topology và cách xử lý session expiration.

Có thể đăng ký publisher để xử lý sự kiện lifecycle HTTP session trong cấu hình Servlet phù hợp:

```java
@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
```

Các kiểu tương ứng ở `org.springframework.security.web.session.HttpSessionEventPublisher` và `org.springframework.context.annotation.Bean`. Khi dùng Spring Boot, cần xác nhận listener được đăng ký và nhận event trong môi trường chạy thực tế. Không có publisher/event tracking phù hợp, registry có thể lưu session đã bị invalidate như thể chúng còn tồn tại.

### 9.4. Khác nhau giữa kiểm soát concurrent và absolute lifetime

`maximumSessions` giới hạn số session theo policy, **không** thay thế idle timeout hoặc giới hạn tồn tại tuyệt đối. Một session duy nhất vẫn có thể sống rất lâu nếu được truy cập liên tục và không có absolute-expiry policy.

## 10. Thu hồi phiên trong hệ thống nhiều instance

Mô hình triển khai đơn giản:

```text
Browser JSESSIONID=S1
        |
        v
Load balancer
    |         |
  Node A    Node B
    |         |
  Local      Local
  session    session
  store      store
```

Nếu Node A và Node B có session store độc lập, Node B có thể không tìm được session S1. Hệ thống có thể dùng sticky routing để giảm tình trạng này, nhưng sticky routing tự nó không tạo cơ chế revoke toàn cục, cũng không bảo đảm sống sót khi node bị mất.

Một thiết kế khác sử dụng session repository chia sẻ, ví dụ **Spring Session** với một backend thích hợp:

```text
Browser session ID
      |
   Load balancer
      |
   +-- Node A ----+
   |              |
   +-- Node B ----+---- Shared Session Store
   |              |
   +-- Node C ----+
```

Trong mô hình đó, ứng dụng có thể triển khai thu hồi bằng API của session store, ví dụ tìm session ID thuộc user rồi xóa session qua `SessionRepository` khi đã xác minh quyền. Cần tính tới caches, eventual consistency, transaction và các request đang thực thi.

**Không xây dựng endpoint “DELETE /session/{id}” công khai** cho client tùy ý xóa ID. Chức năng quản lý phiên cần authentication mạnh, authorization theo chủ sở hữu/admin, rate limiting, audit và tránh lộ session ID.

### 10.1. Thu hồi khi mật khẩu đổi hoặc tài khoản bị khóa

Có hai cách thường được cân nhắc:

- **Chặn ngay request sau:** xóa/revoke session đang hoạt động hoặc kiểm tra security stamp/version tại request boundary.
- **Chặn khi người dùng login mới:** chỉ cập nhật account flags/password trong DB.

Hai lựa chọn này có mức bảo vệ khác nhau. Nếu policy nói “đổi mật khẩu phải đăng xuất tất cả thiết bị”, cần thực hiện hoặc chứng minh cơ chế thực sự thu hồi các session cũ; đổi hash password **không tự làm mất hiệu lực Authentication** đã lưu trong session hiện hành.

### 10.2. Nhớ tới remember-me và token phụ

Nếu ứng dụng bật remember-me hoặc phát hành bearer token riêng, browser có thể được xác thực lại sau khi HTTP session hết hạn tùy cấu hình. Logout/thu hồi phải xử lý token đó theo policy; nếu không, phiên có thể “quay lại” do auto-login.

Đừng dùng `SessionRegistry` để tuyên bố đã thu hồi JWT stateless nếu mỗi request chỉ kiểm chữ ký/hạn token và không có revocation check.

## 11. Ứng dụng runnable Spring Boot 3.3.5 + Java 17

Ví dụ dưới đây tập trung vào vòng đời session thông thường với **form login, session fixation protection, timeout cấu hình và logout**. Phần **concurrent-session control** và **thu hồi toàn bộ thiết bị** được tách khỏi ứng dụng runnable vì cần registry, policy và topology riêng.

### 11.1. Cấu trúc

```text
session-lifecycle-demo/
  pom.xml
  src/
    main/
      java/example/session/
        SessionDemoApplication.java
        SecurityConfig.java
        SessionController.java
      resources/
        application.properties
    test/
      java/example/session/
        SessionLifecycleTest.java
```

### 11.2. Cấu hình Maven

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>session-lifecycle-demo</artifactId>
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

### 11.3. Main class

File `src/main/java/example/session/SessionDemoApplication.java`:

```java
package example.session;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionDemoApplication.class, args);
    }
}
```

### 11.4. SecurityConfig: session-aware form login và logout

File `src/main/java/example/session/SecurityConfig.java`:

```java
package example.session;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("training-only"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                .sessionFixation(fixation -> fixation.changeSessionId()))
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID"));

        return http.build();
    }
}
```

Lưu ý:

1. `IF_REQUIRED` cho phép Spring Security sử dụng session khi cần; nó không đòi tạo session cho mọi request.
2. `changeSessionId` bật bảo vệ session fixation theo cơ chế Servlet tương ứng.
3. `formLogin(Customizer.withDefaults())` dùng trang `/login` do Spring Security cung cấp, không cần tự viết controller xử lý POST login.
4. `logout` bảo đảm có luồng hủy session hiện tại; **POST `/logout` cần CSRF** khi CSRF được bật.
5. Tài khoản/mật khẩu minh họa chỉ dùng trên localhost học tập. Sản xuất cần user store phù hợp, HTTPS, secret management và kiểm soát login abuse.
6. Không cấu hình `SessionCreationPolicy.STATELESS` vì bài này cần lưu Authentication qua HTTP session.

### 11.5. Controller có endpoint được bảo vệ

File `src/main/java/example/session/SessionController.java`:

```java
package example.session;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionController {

    @GetMapping("/")
    String publicHome() {
        return "home";
    }

    @GetMapping("/account")
    String account(Authentication authentication) {
        return "hello " + authentication.getName();
    }
}
```

`GET /account` chỉ chạy sau khi request được xác thực. Dù controller không truy cập trực tiếp `HttpSession`, Spring Security đã xử lý việc nạp Authentication từ repository trong security filter chain.

### 11.6. Idle timeout và cookie policy (application.properties)

File `src/main/resources/application.properties`:

```properties
server.servlet.session.timeout=30m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

Trong ví dụ, `30m` là **thời gian không hoạt động** mong muốn, không phải absolute 30 phút sau khi login. Giá trị thực có thể chịu ảnh hưởng của container/session repository và cấu hình triển khai. `HttpOnly` hạn chế JavaScript đọc cookie, `SameSite=Lax` hỗ trợ giảm một số rủi ro cross-site; **cả hai không thay thế CSRF token và authorization**.

Trong production chạy HTTPS nên cấu hình thuộc tính `Secure` cho cookie và thiết lập reverse-proxy/trust headers đúng cách. Không ép `Secure` trong mẫu localhost chạy HTTP vì browser có thể không gửi cookie trên kết nối không phù hợp. Thực tế cần cân nhắc cookie `Path`, `Domain`, chính sách SameSite, TLS và load balancer.

### 11.7. MockMvc tests: login, sử dụng phiên, logout, CSRF

File `src/test/java/example/session/SessionLifecycleTest.java`:

```java
package example.session;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionLifecycleTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicHomeDoesNotRequireLogin() throws Exception {
        mvc.perform(get("/"))
            .andExpect(status().isOk())
            .andExpect(content().string("home"));
    }

    @Test
    void protectedPageRedirectsAnonymousToLogin() throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("http://localhost/login"));
    }

    @Test
    void loginCreatesAuthenticatedSessionForNextRequest()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "training-only"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        HttpSession raw = login.getRequest().getSession(false);
        assertNotNull(raw);

        MockHttpSession session = (MockHttpSession) raw;

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("hello learner"));
    }

    @Test
    void wrongPasswordDoesNotAuthenticate() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "wrong-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void logoutInvalidatesCurrentSession() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "training-only"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        assertTrue(session.isInvalid());

        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutWithoutCsrfIsRejected() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "training-only"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        assertTrue(!session.isInvalid());
    }
}
```

Giải thích:

- Test public không cần session đăng nhập.
- Test anonymous chỉ kiểm tra route bảo vệ dẫn tới login. **Lưu ý:** redirect URL có thể là absolute hoặc relative tùy entry point/test environment; test này dùng default servlet login entry point trong Spring Boot 3.3.x và kỳ vọng `http://localhost/login`. Nếu proxy/base URL đổi, nên kiểm tra đích tương đương thay vì hardcode host.
- Test login dùng POST với CSRF token hợp lệ, lấy `MockHttpSession` sau xác thực rồi sử dụng ở GET tiếp theo.
- Test logout dùng POST với CSRF, kiểm tra `session.isInvalid()` thay vì chỉ chấp nhận redirect 302.
- Test thiếu CSRF bị 403 và session không tự logout; việc “test thất bại CSRF” không phải kiểm tra mật khẩu.
- Test không giả lập thời gian thực trôi qua 30 phút; timeout thuộc container/session store và nên có integration test riêng hoặc controlled clock/test environment.

### 11.8. Chạy thử

Trong thư mục `session-lifecycle-demo` với Maven/JDK 17+:

```bash
mvn test
mvn spring-boot:run
```

Nếu dependencies và môi trường phù hợp, **sáu bài test dự kiến pass**. Stdout Maven sẽ khác theo máy, timestamp và runtime; đừng lấy một chuỗi log giả làm kết quả thực.

Khi chạy local, mở:

```text
http://localhost:8080/
http://localhost:8080/account
http://localhost:8080/login
```

Bạn có thể theo dõi vòng đời bằng browser devtools: request login tạo/đổi session ID tùy policy, request tiếp theo gửi cookie, logout trả response xóa cookie/redirect và session bị hủy phía server. **Không chụp/chia sẻ giá trị cookie phiên hoặc paste vào log công khai.**

## 12. Java 17 độc lập: mô hình trạng thái để phân biệt timeout, revoke và logout

Ví dụ sau cố ý không cần Spring; dùng thời gian giả định để tạo stdout **xác định**. Đây là **mô hình giáo dục**, không phải thuật toán của Servlet container hay `SessionRegistry`.

Tạo `SessionLifecycleModel.java`:

```java
public class SessionLifecycleModel {

    enum State {
        ACTIVE, IDLE_EXPIRED, REVOKED, LOGGED_OUT
    }

    record Session(long lastAccessMillis,
                   boolean revoked,
                   boolean loggedOut) {}

    static State stateAt(Session session, long nowMillis,
                         long idleTimeoutMillis) {
        if (session.loggedOut()) {
            return State.LOGGED_OUT;
        }
        if (session.revoked()) {
            return State.REVOKED;
        }
        if (nowMillis - session.lastAccessMillis() >= idleTimeoutMillis) {
            return State.IDLE_EXPIRED;
        }
        return State.ACTIVE;
    }

    public static void main(String[] args) {
        long minute = 60_000L;
        long idleTimeout = 30 * minute;

        Session initial = new Session(0, false, false);
        System.out.println("just logged in: " +
            stateAt(initial, 0, idleTimeout));

        System.out.println("31 min idle: " +
            stateAt(initial, 31 * minute, idleTimeout));

        Session recentlyUsed = new Session(20 * minute, false, false);
        System.out.println("used recently: " +
            stateAt(recentlyUsed, 31 * minute, idleTimeout));

        Session revoked = new Session(20 * minute, true, false);
        System.out.println("revoked: " +
            stateAt(revoked, 31 * minute, idleTimeout));

        Session loggedOut = new Session(20 * minute, false, true);
        System.out.println("logged out: " +
            stateAt(loggedOut, 31 * minute, idleTimeout));
    }
}
```

Biên dịch/chạy:

```bash
javac SessionLifecycleModel.java
java SessionLifecycleModel
```

Stdout **chính xác** trên Java 17+:

```text
just logged in: ACTIVE
31 min idle: IDLE_EXPIRED
used recently: ACTIVE
revoked: REVOKED
logged out: LOGGED_OUT
```

Mô hình cho thấy bốn nguyên nhân khác nhau làm trạng thái hiện tại thay đổi. Ở Servlet thật, “idle expired” có thể do container/remote store quyết định và xử lý khi quét hoặc khi request tiếp theo đến; “revoked” có thể là đánh dấu registry hoặc xóa store. Mô hình không tạo cookie, session ID, thread-local hay HTTP filters.

## 13. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách hiểu / khắc phục |
| --- | --- | --- |
| “Có JSESSIONID nghĩa là đã login” | Session anonymous/CSRF vẫn bị coi authenticated | Dựa vào Authentication/authorization và server-side state. |
| “Không có session trước POST login” | Nhầm session dùng cho CSRF hoặc SavedRequest | Session có thể được tạo trước login. |
| “Login thành công giữ nguyên session ID là luôn ổn” | Nguy cơ session fixation | Dùng session fixation protection thích hợp. |
| “Đổi session ID là xóa mọi state cũ” | Có thể dự đoán sai migration attributes | Kiểm thử chiến lược changeSessionId/migrate/newSession. |
| “Đặt timeout=30m là logout sau đúng 30m từ login” | Nhầm inactivity với absolute lifetime | Phân biệt idle và absolute timeout. |
| “Cookie hết hạn là đã xóa state server” | Server có thể vẫn giữ session một thời gian | Quản lý lifecycle phía server, không chỉ UI/cookie. |
| “Xóa JSESSIONID bằng JS là logout” | Server vẫn có thể giữ session hợp lệ nếu ID còn được biết | POST logout được bảo vệ, invalidate/clear context server-side. |
| “clearContext là đủ” | Context trong session/repository có thể vẫn còn | Dùng LogoutFilter/logout handlers chuẩn. |
| “Logout GET luôn an toàn” | Có thể bị kích hoạt ngoài ý muốn/CSRF | Giữ CSRF protection cho thao tác logout. |
| “expireNow() hủy session ngay trên mọi node” | Chỉ đánh dấu registry, request khác có thể còn sống | Thiết kế request-time enforcement hoặc xóa shared store. |
| “Khóa user trong DB làm mọi session lập tức hết hạn” | Authentication cũ trong session vẫn có thể dùng | Có cơ chế revoke/revalidation cho session đang tồn tại. |
| “maximumSessions(1) đồng nghĩa absolute timeout” | Phiên duy nhất có thể sống lâu nếu hoạt động | Thêm absolute policy riêng nếu cần. |
| “SessionRegistryImpl chung toàn cluster” | Session/expiration giữa node không đồng bộ | Dùng shared registry/store phù hợp hoặc thiết kế phân tán khác. |
| “Logout một thiết bị cũng logout mọi thiết bị” | Session khác chưa được hủy | Quản lý danh sách session và chức năng revoke all có quyền/audit. |
| “HttpOnly tự ngăn CSRF” | Browser vẫn tự đính kèm cookie | Dùng CSRF protection, SameSite và threat model phù hợp. |
| “SameSite là thay thế CSRF token” | Có browser/tình huống không được bảo vệ đủ | Thiết kế phòng vệ nhiều lớp. |
| “Đã hủy session thì token/JWT cũng chết” | Token độc lập có thể vẫn hợp lệ | Quản lý revoke/token expiry riêng. |
| “MockMvc redirect 302 chứng minh session đã logout” | Redirect có thể xảy ra mà session chưa invalidated | Assert server-side invalidation/session store. |
| “Đưa session ID vào analytics log giúp debug an toàn” | Lộ credential có thể chiếm phiên | Không log raw session identifier; dùng trace ID thay thế. |

## 14. Bảo mật session và ứng phó sự cố

### 14.1. Cookie và transport

- Bắt buộc HTTPS trong production; cookie phiên có `Secure` và `HttpOnly` phù hợp.
- Thiết lập `SameSite` theo nhu cầu chính đáng của ứng dụng và chính sách CSRF.
- Giới hạn `Domain` và `Path` để tránh gửi cookie không cần thiết tới ứng dụng/subdomain khác.
- Không đưa ID phiên vào URL để tránh lộ qua history, log, Referer hoặc copy link.
- Có chiến lược session fixation protection; không hardcode hoặc tự cấp session ID bằng chuỗi dễ đoán.
- Không xuất cookie session trong response body hoặc metric labels.

### 14.2. Phòng vệ khi phiên bị chiếm quyền

Dấu hiệu bất thường như session dùng ở thiết bị lạ, thay đổi IP/thiết bị đột ngột hoặc account takeover cần được đánh giá với false-positive phù hợp. Hệ thống có thể yêu cầu reauthentication cho tác vụ nhạy cảm, rotate session ID ở thời điểm phù hợp, revoke session và audit.

**Reauthentication** không phải việc chỉ kiểm tra `SecurityContextHolder.getContext().getAuthentication().isAuthenticated()`: trạng thái authenticated từ session đã có thể cũ. Với tác vụ nhạy cảm, cần chính sách kiểm tra lại credential/MFA hoặc độ mới authentication có kiểm soát.

### 14.3. Request đang chạy khi thu hồi

Không có gì bảo đảm lệnh revoke ở thời điểm T có thể “rút quyền” khỏi một request đã được authorize trước T. Những thao tác nhạy cảm có thể cần kiểm tra trạng thái account/permission tại giao dịch thực hiện hoặc điểm commit, đặc biệt khi policy yêu cầu chặn tức thời.

Đây là khác biệt giữa **ngừng cho request mới truy cập** và **hủy tất cả công việc đang thực hiện**. Session invalidation thường giải quyết phần đầu; tác vụ dài, async, stream hoặc WebSocket cần xem xét thêm.

### 14.4. Bảo vệ endpoint quản lý phiên

Chức năng “xem phiên đang đăng nhập”, “đăng xuất thiết bị khác” hoặc “thu hồi toàn bộ phiên” phải:

1. Kiểm tra identity của chủ phiên và quyền admin nếu áp dụng.
2. Có CSRF protection hoặc cơ chế authentication của API phù hợp với threat model.
3. Không để user tùy ý chọn/bẻ khóa định danh session người khác.
4. Audit sự kiện quan trọng nhưng không ghi session ID thật vào log.
5. Đặt rate limiting để tránh bị lợi dụng làm gián đoạn tài khoản khác.
6. Làm rõ việc revoke các remember-me token, refresh token hoặc các phiên trên ứng dụng khác.

## 15. Chẩn đoán theo triệu chứng

### 15.1. Đăng nhập thành công nhưng request tiếp theo lại anonymous

Kiểm tra lần lượt:

1. HTTP `POST /login` có thực sự thành công hay chỉ redirect về `/login?error`?
2. Session fixation protection có thay ID; browser/test có sử dụng cookie/session mới?
3. `SecurityContextRepository` có lưu Authentication sau login không? Custom login handler có quên explicit save?
4. Cookie có đúng Domain/Path/SameSite/Secure với môi trường HTTPS/proxy không?
5. Browser có gửi cookie ở request tiếp theo? Có chặn third-party cookie hoặc chuyển domain?
6. Ứng dụng có cấu hình `SessionCreationPolicy.STATELESS` hoặc `NullSecurityContextRepository` cho route đó không?
7. Request có đi qua một `SecurityFilterChain` khác không?
8. Session store có bị mất do restart, failover hoặc timeout quá ngắn không?

### 15.2. Người dùng bị logout bất ngờ

Có thể là idle timeout, concurrent-session expired strategy, logout thực sự, session store mất kết nối, deploy/restart hoặc cookie bị gửi sai. Cần phân biệt bằng event logs/metrics phù hợp, không chỉ dựa vào client thấy màn hình login.

### 15.3. Người dùng đã logout nhưng vào lại vẫn authenticated

Kiểm tra:

- Request có thật sự gọi đúng `POST /logout`, CSRF hợp lệ và đi vào đúng security chain?
- Có handler tùy biến chỉ redirect chứ không invalidate session?
- `SecurityContextRepository` có còn lưu Authentication do custom code không?
- Cookie cũ có còn gắn với một session server hợp lệ?
- Có remember-me, SSO hoặc token tự động đăng nhập lại không?
- Có các phiên khác trên thiết bị khác vẫn đang hợp lệ không?

### 15.4. Thu hồi một phiên nhưng request từ node khác vẫn thành công

Đánh giá session store dùng chung hay local, cập nhật `SessionRegistry` trên node nào, shared registry/replication, cache và request-time revocation check. Xem chính sách race conditions và session expiration events trước khi kết luận một lệnh `expireNow()` là đủ.

### 15.5. Bật log đúng mức

Trong môi trường phát triển có thể dùng:

```properties
logging.level.org.springframework.security=DEBUG
```

Log DEBUG giúp quan sát security chain, authentication và một số quyết định filter; không có nghĩa framework sẽ luôn log mọi session event. Để xác nhận timeout và revoke, xem container/session repository metrics, event listener và integration test. **Không log password, raw session ID, cookie, bearer token**.

## 16. Bài tập suy luận và đáp án

**1.** User chưa đăng nhập nhưng browser nhận `JSESSIONID` sau khi mở `/login`. Đó có phải lỗi không?

**Đáp án:** Không nhất thiết. Session có thể được tạo để giữ CSRF token hoặc saved request, dù user vẫn anonymous.

**2.** Browser được cấp session ID mới khi login thành công. Vì sao?

**Đáp án:** Session fixation protection giúp giảm khả năng attacker tái sử dụng ID được biết trước khi victim đăng nhập. Nó không phải dấu hiệu user tự logout.

**3.** Cấu hình idle timeout 30 phút. User gọi `/account` mỗi 10 phút suốt 2 giờ. Phiên có chắc hết hạn sau 30 phút kể từ login không?

**Đáp án:** Không. Idle timeout phụ thuộc khoảng không hoạt động, không phải absolute maximum lifetime. Request có truy cập session đúng cách có thể cập nhật last-access.

**4.** Sau POST logout với CSRF hợp lệ, browser vẫn gửi cookie `JSESSIONID` cũ. User có chắc còn đăng nhập không?

**Đáp án:** Không. Nếu session server đã invalidated, cookie stale không thể chứng minh Authentication hợp lệ. Kiểm tra server-side state.

**5.** Admin gọi `SessionInformation.expireNow()`, trong khi browser đang gửi một request dài. Request đó có bị dừng tức thì không?

**Đáp án:** Không có bảo đảm. Dấu expired có thể được xử lý ở request sau bởi cơ chế concurrent session; request đã authorize trước đó có thể tiếp tục. Cần policy kiểm tra bổ sung cho thao tác nhạy cảm.

**6.** Một tài khoản có hai phiên A và B. Người dùng POST logout trên A. B có bị xóa không?

**Đáp án:** Không mặc định. Logout hiện tại thường chỉ xử lý session của request; revoke all devices cần cơ chế riêng.

**7.** Account bị khóa sau khi login. Session đã có Authentication có tự mất hiệu lực không?

**Đáp án:** Không được giả định. Nếu business policy cần chặn request sau khi khóa, phải có session revocation/revalidation rõ ràng.

**8.** Session có `HttpOnly` và `SameSite=Lax`. Có thể bỏ mọi CSRF protection không?

**Đáp án:** Không. `HttpOnly` không chặn browser đính kèm cookie; SameSite giảm một số dạng cross-site request nhưng không luôn thay thế CSRF token và các kiểm soát khác.

**9.** Với hệ thống nhiều node, gọi `expireNow()` trên registry local của Node A có bảo đảm Node B từ chối phiên đó không?

**Đáp án:** Không. Cần chia sẻ state hoặc có thiết kế revoke được enforce trên mọi node, và hiểu độ trễ đồng bộ.

**10.** Vì sao test chỉ assert redirect `/login?logout` chưa chứng minh logout an toàn?

**Đáp án:** Redirect chỉ là điều hướng. Cần xác minh session server bị invalidated và context không còn khôi phục ở request tiếp theo; đồng thời phân tích token phụ.

## 17. Tóm tắt thực hành

- **Trước login**, HttpSession có thể đã được tạo cho CSRF/SavedRequest; có cookie không đồng nghĩa có Authentication.
- **Sau login**, Spring Security xác thực, áp dụng session fixation protection, lưu SecurityContext và phản hồi; browser dùng session cookie trong các request kế tiếp.
- **Trong phiên**, mỗi request vẫn qua authentication context loading và authorization; idle timeout phụ thuộc last access, không phải absolute expiry từ lúc login.
- **Logout** cần chạy luồng LogoutFilter phù hợp, thường là POST kèm CSRF, invalidate HttpSession và clear context; không thay bằng xóa cookie ở JavaScript.
- **Hết hạn do inactivity**, **logout**, **concurrent-session expired** và **thu hồi có chủ đích** khác nhau về nguyên nhân và cơ chế.
- `SessionInformation.expireNow()` **đánh dấu** session trong registry; không nên tuyên bố nó xóa tức thì session trên mọi node hoặc chặn request đã chạy.
- Đối với **logout all devices / account compromise**, cần registry hoặc shared session store, kiểm soát quyền, audit, và quản lý token phụ ngoài HTTP session.
- Kiểm thử tối thiểu: anonymous không vào trang bảo vệ, login tạo phiên xác thực, request kế tiếp sử dụng đúng phiên, logout thật sự invalidate session, và logout không CSRF bị chặn.
