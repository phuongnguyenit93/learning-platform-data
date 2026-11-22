# Thay đổi mật khẩu, thu hồi phiên và xử lý trạng thái tài khoản đã thay đổi — Spring Security reactive

## 1. Mục tiêu và vấn đề cốt lõi

Đối với ứng dụng **Spring WebFlux + Spring Security**, việc cập nhật password trong cơ sở dữ liệu là một sự kiện quan trọng nhưng **không tự động bảo đảm** mọi trình duyệt, thiết bị, phiên đăng nhập và access token trước đó đều mất hiệu lực. Tương tự, khóa tài khoản hoặc thu hồi một vai trò không đồng nghĩa các `SecurityContext` đã lưu trong phiên sẽ tự tải lại `UserDetails`.

Sau bài này, bạn cần có thể:

1. Thiết kế luồng thay đổi mật khẩu có xác minh danh tính, kiểm tra mật khẩu cũ, lưu mật khẩu mới bằng `PasswordEncoder` và thông báo an toàn.
2. Phân biệt việc **không chấp nhận mật khẩu cũ ở lần đăng nhập mới** với việc **thu hồi phiên/cookie hoặc token đã cấp**.
3. Xử lý **WebSession hiện tại**, **tất cả phiên đã đăng ký**, **access token JWT**, **refresh token**, và trạng thái account/role thay đổi theo cơ chế phù hợp.
4. Hiểu các API reactive như `ReactiveUserDetailsService`, `ReactiveSessionRegistry`, `WebSessionStore`, `ReactiveSecurityContextHolder` và `WebSessionServerLogoutHandler`.
5. Chạy ví dụ Java 17+ trên WebFlux, kiểm chứng mật khẩu mới có hiệu lực, người dùng bị khóa không còn đăng nhập được và token CSRF mới được tạo sau khi WebSession bị vô hiệu hóa.

**Nguyên tắc thiết kế:** thay đổi credential và thay đổi quyền truy cập là hai sự kiện liên quan nhưng có vòng đời khác nhau. Muốn thu hồi truy cập có hiệu lực trên các request tiếp theo, phải xác định nơi nào đang lưu dữ liệu xác thực và nơi nào đang kiểm tra tính hợp lệ.

## 2. Phân biệt năm thứ có thể vẫn còn hiệu lực

| Thành phần | Chứa gì? | Khi thay password hoặc khóa account có tự mất hiệu lực không? |
| --- | --- | --- |
| **Password hash trong kho user** | Bản mã hóa một chiều để so sánh password khi xác thực | Có thay đổi khi lưu đúng; password cũ phải thất bại ở **lần xác thực tiếp theo** |
| **HTTP Basic credentials** | Username/password được client gửi lại với mỗi request | Nếu server kiểm tra từ kho user mới ở mỗi request, password cũ bị từ chối; không phải session login |
| **WebSession và SecurityContext** | Session ID/cookie cùng authentication đã lưu tại server | **Không nhất thiết**; session cũ có thể giữ principal và authorities đã xác thực trước đó |
| **Access token JWT** | Claims đã ký, ví dụ subject, scope, expiration | **Không tự bị thu hồi** chỉ vì password hash đổi; resource server thường kiểm tra signature/time/issuer |
| **Refresh token / OAuth2 login tại IdP** | Quyền xin access token mới hoặc phiên tại nhà cung cấp danh tính | Phải dùng cơ chế thu hồi của token store/authorization server/IdP; logout tại ứng dụng chưa chắc logout khỏi IdP |

**Đặc biệt:** Spring Security reactive dùng `Reactor Context` để cung cấp `SecurityContext` cho chuỗi xử lý request. Đây không phải kho phiên lâu dài. Muốn giữ context **giữa các request**, một `ServerSecurityContextRepository` như `WebSessionServerSecurityContextRepository` phải lưu/đọc nó. Còn với API thuần Bearer JWT, security context thông thường được tạo lại từ token mỗi request và không tự lưu session xác thực.

## 3. Một sơ đồ vòng đời

~~~text
Người dùng đã đăng nhập trên thiết bị A và B
       |                             |
       v                             v
WebSession A + SecurityContext   WebSession B + SecurityContext
       |                             |
       +------------+----------------+
                    |
Người dùng đổi password hợp lệ
                    |
                    v
Xác minh mật khẩu hiện tại / recent authentication
                    |
                    v
Hash password mới -> lưu bền vững -> tăng securityVersion
                    |
            +-------+-----------------------+
            |                               |
            v                               v
Vô hiệu hóa phiên cần thu hồi        Thu hồi refresh token/điểm phát JWT
            |                               |
            v                               v
Request tiếp theo cần login mới      JWT cũ: tùy TTL và cơ chế kiểm tra
                    |
                    v
Kiểm tra trạng thái tài khoản mới ở ranh giới request
                    |
              Enabled, locked, roles, tenant, version...
~~~

Đây là kiến trúc khái niệm. Việc truy xuất tất cả phiên, cập nhật password và thu hồi token có thể nằm ở các dịch vụ khác nhau; một database transaction đơn lẻ không tự bao trùm toàn bộ chúng. Khi cần bảo đảm thu hồi, phải có **trạng thái thu hồi dùng chung** và kiểm tra tại request, hoặc cách phối hợp có thể phục hồi sau lỗi từng bước.

## 4. Luồng thay đổi mật khẩu an toàn

### 4.1. Nhận yêu cầu đúng phương thức và đúng chủ thể

Một endpoint thông thường dùng `POST /account/password` hoặc `PUT /account/password`. Không dùng GET để đổi password, khóa user hoặc logout vì GET có thể bị trình duyệt, crawler, cache hoặc prefetch gọi ngoài ý muốn.

Yêu cầu cần xuất phát từ principal đang được xác thực; lấy tên/id từ `Authentication` do Spring Security cung cấp, **không tin một username do client tùy ý gửi để chọn account đích**. Tùy mức nhạy cảm có thể yêu cầu **xác thực lại gần đây** hoặc MFA, kể cả khi session hiện tại vẫn hợp lệ.

Với giao diện web dựa cookie/session, phải dùng token CSRF cho request thay đổi trạng thái. Spring Security WebFlux có CSRF protection mặc định; `WebSessionServerCsrfTokenRepository` thường giữ token trong WebSession. Một API stateless Bearer có đặc tính khác, nhưng chỉ cân nhắc tắt CSRF sau khi đánh giá cả cookie và hành vi gửi credentials tự động của trình duyệt.

### 4.2. Xác minh mật khẩu cũ

Nạp user hiện tại từ nguồn dữ liệu đáng tin cậy. Dùng:

~~~java
boolean oldPasswordMatches =
        passwordEncoder.matches(currentPassword, account.passwordHash());
~~~

Đây là **snippet nằm trong service**, các biến `currentPassword`, `account` và `passwordEncoder` cần được khai báo. Không so sánh plaintext với hash bằng `String.equals`, không giải mã hash để lấy lại mật khẩu cũ. Password hash phải là kết quả của thuật toán thích hợp qua `PasswordEncoder`, ví dụ `PasswordEncoderFactories.createDelegatingPasswordEncoder()`.

Tuy nhiên, nếu phương thức đặt lại mật khẩu qua email/recovery token không có mật khẩu cũ thì phải dùng quy trình **reset password** độc lập: token dùng một lần, giới hạn thời gian, liên kết đúng account, có chống replay và thu hồi token sau thành công. Không làm giả điều kiện “mật khẩu cũ đúng” để dùng chung flow.

### 4.3. Kiểm tra mật khẩu mới

Cần kiểm tra password mới trước khi lưu:

- Không null/trống, đáp ứng chính sách độ dài phù hợp và không trùng password hiện tại; có thể kiểm tra lịch sử mật khẩu theo quy định.
- Ưu tiên độ dài, passphrase, chống mật khẩu bị lộ và khả năng tương thích password manager. Không dựa vào quy tắc khó nhớ chỉ để “có chữ hoa, ký tự đặc biệt”.
- Với môi trường yêu cầu cao, kiểm tra danh sách mật khẩu phổ biến/bị lộ. Spring Security có `ReactiveCompromisedPasswordChecker` cho những tích hợp phù hợp; phải xử lý timeout và không log plaintext.
- Giới hạn tốc độ và số lần thử kiểm tra mật khẩu cũ. Không tiết lộ thêm thông tin nhạy cảm trong response.

**Không lưu mật khẩu plaintext.** Nếu sử dụng `DelegatingPasswordEncoder`, hash lưu có thể có tiền tố định danh encoder như `{bcrypt}`; đừng xóa tiền tố này khi lưu/đọc bằng cùng cơ chế.

### 4.4. Ghi nhận thay đổi có tính nhất quán

Flow khuyến nghị trong hệ thống thật:

1. Xác minh user hiện tại và mật khẩu cũ; kiểm tra account chưa bị khóa hoặc thu hồi quyền tự đổi mật khẩu.
2. Sinh hash mới và cập nhật record có kiểm soát đồng thời, dùng transaction hoặc optimistic locking theo version.
3. Tăng `securityVersion`/`credentialsChangedAt` **cùng lần ghi** để request phía sau có thể nhận ra credential cũ.
4. Sau khi commit thành công, kích hoạt thu hồi các phiên cần thiết, refresh token, remembered devices hoặc token theo chính sách.
5. Ghi audit event (user id, thời điểm, request id, nguồn yêu cầu; **không ghi password hoặc token**) và gửi thông báo cho chủ tài khoản.
6. Nếu một bước thu hồi từ xa thất bại, đánh dấu công việc cần retry và duy trì cơ chế kiểm tra version/denylist ở request để tránh cửa sổ truy cập còn hiệu lực.

Đừng xóa session **trước khi chắc chắn cập nhật password đã commit** nếu điều đó làm người dùng bị logout dù mật khẩu chưa thay đổi. Nhưng cũng không tuyên bố “đã đăng xuất mọi thiết bị” khi chưa thu hồi được các session/token tương ứng.

## 5. Thay password không tự vô hiệu hóa phiên đã xác thực

### 5.1. WebSession và SecurityContext

Với form login hoặc cơ chế session-based, `WebSessionServerSecurityContextRepository` có thể giữ authentication bên trong WebSession. Sau khi đăng nhập, các request tiếp theo mang cookie session có thể dùng context lưu trước đó **mà không cần kiểm tra lại mật khẩu từ database**.

Giả sử lúc 09:00 user đăng nhập và có `ROLE_ADMIN`. Lúc 10:00 admin khác gỡ vai trò `ADMIN` của user. Nếu request lúc 10:01 chỉ đọc authorities từ SecurityContext cũ, có nguy cơ user vẫn được truy cập theo role cũ. Tình huống tương tự xảy ra khi account bị khóa hoặc password đã đổi.

**Biện pháp:** thu hồi session và/hoặc kiểm tra trạng thái account mới ở request tiếp theo. Chỉ thay hash trong database là không đủ cho các context đã được xác thực trước khi thay đổi.

### 5.2. Vô hiệu hóa WebSession hiện tại

Trong handler reactive đã có `ServerWebExchange exchange`:

~~~java
return exchange.getSession()
        .flatMap(WebSession::invalidate);
~~~

Đây là **snippet trong method trả `Mono<Void>`**, cần import `org.springframework.web.server.WebSession`. Nó chỉ vô hiệu hóa **WebSession của request hiện tại**, không có nghĩa tất cả browser session hoặc JWT của cùng user đã bị hủy.

Với logout dùng cơ chế Spring Security reactive, có thể cấu hình các logout handler:

~~~java
DelegatingServerLogoutHandler handlers =
        new DelegatingServerLogoutHandler(
                new SecurityContextServerLogoutHandler(),
                new WebSessionServerLogoutHandler());

http.logout(logout -> logout.logoutHandler(handlers));
~~~

Đây là **đoạn cấu hình thêm trong method tạo `SecurityWebFilterChain`**, cần import ba class từ `org.springframework.security.web.server.authentication.logout`. `SecurityContextServerLogoutHandler` xóa context qua repository; `WebSessionServerLogoutHandler` vô hiệu hóa WebSession hiện tại. Theo tài liệu reactive, logout mặc định xử lý **POST /logout** có CSRF token khi CSRF được bật. Không dùng GET logout làm hành động thay đổi trạng thái.

### 5.3. Đăng xuất một phiên hay tất cả các phiên?

| Yêu cầu sản phẩm | Điều cần làm |
| --- | --- |
| “Đăng xuất khỏi thiết bị này” | Xóa SecurityContext và vô hiệu hóa WebSession hiện tại; dọn cookie phía client khi phù hợp |
| “Đăng xuất mọi thiết bị” | Tìm và thu hồi tất cả session của principal từ registry/store phù hợp, kể cả phiên ở node khác |
| “Đổi mật khẩu thì bắt tất cả đăng nhập lại” | Cập nhật password + version, rồi thu hồi session/token liên quan; bảo đảm request mới kiểm tra trạng thái thu hồi |
| “Khóa tài khoản ngay” | Dừng xác thực mới và chặn session/token cũ bằng revocation hoặc kiểm tra account state ở mỗi request |
| “Chỉ gỡ role” | Không chỉ sửa database; refresh authorities hoặc hủy context và yêu cầu xác thực lại |

Đừng nhầm logout của **ứng dụng** với logout tại **Identity Provider** nếu đăng nhập OAuth2/OIDC.

## 6. Thu hồi tất cả phiên reactive bằng Session Registry

Spring Security có **Reactive Concurrent Sessions Control** và `ReactiveSessionRegistry` (Spring Security 6.3+). Khi bật theo cách hỗ trợ, các phiên từ những cơ chế như form login, OAuth2 login và HTTP Basic có thể được đăng ký qua các success handler. `InMemoryReactiveSessionRegistry` là một implementation đơn giản trong một process.

Ví dụ cấu hình registry **bổ sung cho ứng dụng session-based**, không áp vào ví dụ Basic stateless ở phần 9:

~~~java
@Bean
ReactiveSessionRegistry reactiveSessionRegistry() {
    return new InMemoryReactiveSessionRegistry();
}

@Bean
SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex.anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .sessionManagement(sessions -> sessions
                    .concurrentSessions(concurrency -> concurrency
                            .maximumSessions(SessionLimit.of(2))))
            .build();
}
~~~

Đây là đoạn trong lớp `@Configuration` có import phù hợp, **chưa là một project hoàn chỉnh**. Dùng `SessionLimit.of(2)` để minh họa tối đa hai phiên. Nếu ứng dụng chỉ muốn **theo dõi và thu hồi** mà không giới hạn số phiên, dùng cấu hình giới hạn không hạn chế theo API phiên bản đang sử dụng; không tự suy rằng việc khai báo bean registry một mình đã đăng ký tất cả phiên.

Khi registry đã thực sự ghi nhận session của user, tài liệu Spring Security minh họa cách thu hồi các session:

~~~java
final class SessionRevocationService {
    private final ReactiveSessionRegistry registry;
    private final WebSessionStore store;

    SessionRevocationService(
            ReactiveSessionRegistry registry, WebSessionStore store) {
        this.registry = registry;
        this.store = store;
    }

    Mono<Void> revokeRegisteredSessions(String username) {
        return registry.getAllSessions(username)
                .flatMap(session -> session.invalidate()
                        .then(store.removeSession(session.getSessionId()))
                        .then(registry.removeSessionInformation(session.getSessionId()))
                        .then())
                .then();
    }
}
~~~

Đây là **class ví dụ cần thêm package/import và bean wiring**, không phải module build độc lập. Import:

~~~java
import org.springframework.security.core.session.ReactiveSessionRegistry;
import org.springframework.web.server.session.WebSessionStore;
import reactor.core.publisher.Mono;
~~~

Giải thích:

1. `getAllSessions(username)` lấy các phiên mà registry **đang theo dõi** cho principal; phải chắc chắn khóa principal trùng cách registry đăng ký.
2. `session.invalidate()` đánh dấu session bị thu hồi trong registry.
3. `store.removeSession(session.getSessionId())` xóa phiên thực tế trong backing store tương ứng.
4. `registry.removeSessionInformation(...)` dọn mục đăng ký; với một số implementation backing bởi Spring Session, cần xem chính xác hành vi của chúng trước khi sử dụng.
5. `then()` bảo đảm publisher chỉ hoàn tất khi toàn bộ thao tác reactive đã hoàn tất; chỉ **tạo một Mono nhưng không subscribe/return** không thực hiện hành động.

**Giới hạn:** InMemory registry và WebSessionStore in-memory chỉ bảo đảm trong instance hiện tại. Với cluster/multi-instance, cần session store dùng chung và registry được đồng bộ hoặc Spring Session-backed registry phù hợp. Nếu có phiên chưa được ghi nhận, registry không thể thu hồi phiên không biết đến. Hãy test trên nhiều node.

Tài liệu chính thức cảnh báo concurrent-session control không tự biết phiên ở OAuth2 Identity Provider; logout từ ứng dụng có thể cần lời gọi thu hồi riêng tới IdP.

## 7. JWT, refresh token và stateless authentication

### 7.1. Vì sao thay password không tự hủy JWT?

JWT access token chứa claims đã ký và hạn sử dụng. Spring Security reactive resource server thông thường kiểm tra chữ ký, `exp`, `nbf` và issuer theo cấu hình. **Không mặc nhiên truy vấn password hash mới mỗi lần decode JWT.** Do đó JWT đã cấp **vẫn có thể hợp lệ cho tới khi hết hạn** nếu không triển khai thêm cơ chế thu hồi.

Ba hướng phổ biến:

1. **Access token TTL ngắn + refresh token có thể thu hồi:** giới hạn thời gian token cũ tồn tại; khi password đổi/khóa account, thu hồi refresh token của account.
2. **Denylist bằng `jti` hoặc token identifier:** mỗi request kiểm tra tập token đã bị thu hồi, có TTL tới lúc token hết hạn; yêu cầu kho dùng chung và chính sách xử lý khi kho lỗi.
3. **Version/epoch theo user:** ghi `securityVersion` hoặc `credentialsChangedAt` trong claims lúc cấp token; resource server kiểm tra version token so với record hiện tại hoặc cache có khả năng cập nhật. Khi version thay đổi, token cũ bị từ chối.

Một số hệ thống chọn **opaque token + introspection**, cho phép auth server quyết định hiệu lực tập trung, nhưng có chi phí network/cache. Nếu cần thu hồi gần như tức thời, không thể chỉ dựa vào JWT ký hợp lệ có thời gian sống dài và kiểm tra offline.

### 7.2. Cẩn thận với race và cache

Nếu tăng `securityVersion` và cập nhật password cùng transaction, token mới cấp phải mang version mới. Nếu token issuer hoặc resource server cache account state, phải giới hạn độ trễ hoặc có cơ chế phát sự kiện invalidation. Khi có request đang chạy trong lúc khóa account, không giả định có thể hủy kết quả của request đã qua bước kiểm tra; cần đánh giá nghiệp vụ nhạy cảm và có chốt quyền ngay trước thao tác quan trọng khi cần.

Không dùng blacklist vô thời hạn cho mọi token; lưu `jti` cùng TTL tương ứng và bảo vệ kho tra cứu. Phải có chiến lược fail closed/fail open rõ ràng khi kho trạng thái không truy cập được, theo mức rủi ro của API.

### 7.3. Refresh token và IdP

Sau đổi password:

- Thu hồi refresh token trong kho server hoặc gọi endpoint thu hồi do OAuth2 provider hỗ trợ.
- Với refresh token rotation, chặn dùng lại token cũ và phát hiện replay.
- Với OIDC/OAuth2 login, đăng xuất WebSession ứng dụng không tự logout session của IdP; cân nhắc RP-initiated logout/back-channel logout nếu provider hỗ trợ.
- Nếu IdP quản lý password, thay password phải được thực hiện theo quy trình tại IdP, không ghi thay vào database ứng dụng rồi cho rằng mọi SSO đã bị thu hồi.

## 8. Trạng thái tài khoản đã thay đổi: enabled, locked, role và tenant

### 8.1. Chặn lần xác thực mới

`ReactiveUserDetailsService` nạp `UserDetails` để authentication manager kiểm tra user hiện tại. Với `UserDetails`, những cờ điển hình gồm:

- `isEnabled()`: account được phép hoạt động không.
- `isAccountNonLocked()`: account có bị khóa không.
- `isAccountNonExpired()`: account còn hiệu lực không.
- `isCredentialsNonExpired()`: credentials còn hiệu lực không.

Nếu kho dữ liệu cập nhật các cờ và manager thực sự nạp lại user, **lần đăng nhập mới** có thể bị từ chối theo trạng thái mới. Đừng lấy điều này làm bằng chứng session cũ đã bị vô hiệu hóa.

### 8.2. Chặn quyền cũ ở request tiếp theo

Ví dụ 10:00 user mất role admin nhưng session vẫn lưu `ROLE_ADMIN`. Có ba giải pháp:

1. **Thu hồi session khi role/lock thay đổi** và buộc đăng nhập lại.
2. **Custom authorization** kiểm tra quyền hiện hành từ nguồn dữ liệu reactive đáng tin cho những endpoint nhạy cảm.
3. **Security version** lưu trong context/token và so với account version hiện tại trên mỗi request cần bảo vệ; nếu không khớp, từ chối và yêu cầu xác thực lại.

Việc thực hiện kiểm tra ở ranh giới request phải nằm đúng security chain và hoạt động với Reactor Context. Không dựa `ThreadLocal` kiểu Servlet để lấy authentication. Với thay đổi tenant hoặc ownership, kiểm tra ở tầng service/data cũng cần thiết; URL authorization đơn thuần không bảo vệ đầy đủ mọi đối tượng nghiệp vụ.

### 8.3. Không chỉ kiểm tra user theo tên

Tên đăng nhập có thể đổi hoặc được tái sử dụng; với hệ thống thật, dùng **user ID bất biến** để liên kết phiên, token và audit. Khi username được dùng bởi `ReactiveSessionRegistry.getAllSessions(...)`, phải chắc cách registry ánh xạ principal khớp với lúc tạo session. Nếu không, báo cáo “không thấy session” có thể chỉ là sai key.

### 8.4. Trạng thái và quyết định

| Sự kiện | Xác thực mới | Phiên/token cũ | Hành động khuyến nghị |
| --- | --- | --- | --- |
| Password đổi | Password cũ phải thất bại | Có thể còn hiệu lực | Thu hồi theo chính sách, kiểm tra version |
| Account disabled/locked | Bị từ chối nếu service đọc trạng thái mới | Có thể còn hiệu lực | Thu hồi ngay, thêm kiểm tra account state ở request |
| Vai trò `ADMIN` bị gỡ | Xác thực vẫn có thể thành công, role mới giảm | Context/token cũ có thể giữ role | Refresh authorities hoặc revoke; kiểm tra quyền nguồn |
| User bị xóa | Không thể đăng nhập mới | Session/token cũ có thể còn | Revoke mọi credential và cleanup hợp lệ |
| Password reset qua email | Password cũ bị thay nếu reset thành công | Phụ thuộc chính sách | Thu hồi refresh/session, audit và thông báo |
| MFA factor bị đổi | Password không nhất thiết đổi | Session với mức bảo đảm cao có thể còn | Reassess authentication assurance, revoke session nhạy cảm |

## 9. Ví dụ chạy được: đổi mật khẩu và khóa tài khoản bằng WebFlux

Ví dụ này dùng **HTTP Basic cho request API** để nhìn thấy rõ rằng password đổi/disabled có tác dụng ở lần xác thực mới. Chúng ta **không lưu SecurityContext trong session** của HTTP Basic; một `WebSession` riêng vẫn được dùng cho CSRF và bị vô hiệu hóa sau khi thay password. Vì vậy, nó **không phải demo thu hồi mọi phiên login bằng cookie**; phần 6 giải quyết chức năng đó.

### 9.1. Cấu hình project

Tạo Maven project với Java **17+**, group `com.example`, artifact `account-state-demo`, dependencies **Spring Reactive Web** và **Spring Security** trên [Spring Initializr](https://start.spring.io/). File `pom.xml` tối giản đầy đủ (Spring Boot 4.1.2):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>account-state-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
~~~

Không thêm `spring-boot-starter-web`/MVC và không tự gán version cho Spring Security hoặc Reactor; BOM của Boot quản lý các thư viện phù hợp.

### 9.2. Mã Java đầy đủ

Tạo file `src/main/java/com/example/accountstate/AccountStateDemoApplication.java`:

~~~java
package com.example.accountstate;

import java.security.Principal;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
@EnableWebFluxSecurity
public class AccountStateDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AccountStateDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    Accounts accounts(PasswordEncoder encoder) {
        return new Accounts(encoder);
    }

    @Bean
    ReactiveUserDetailsService users(Accounts accounts) {
        return username -> Mono.defer(
                () -> Mono.justOrEmpty(accounts.find(username)));
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users, PasswordEncoder encoder) {
        UserDetailsRepositoryReactiveAuthenticationManager manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http, ReactiveAuthenticationManager manager) {
        return http
                .authenticationManager(manager)
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/csrf").permitAll()
                        .pathMatchers(HttpMethod.POST, "/account/password")
                            .authenticated()
                        .pathMatchers(HttpMethod.POST, "/admin/lock/**")
                            .hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    record ChangePassword(String oldPassword, String newPassword) { }

    record State(String hash, boolean disabled, String role, long version) { }

    static final class Accounts {
        private final PasswordEncoder encoder;
        private final Map<String, State> data = new ConcurrentHashMap<>();

        Accounts(PasswordEncoder encoder) {
            this.encoder = encoder;
            data.put("learner", new State(
                    encoder.encode("learnerOld123!"), false, "USER", 0));
            data.put("admin", new State(
                    encoder.encode("adminSecret123!"), false, "ADMIN", 0));
        }

        synchronized UserDetails find(String username) {
            State state = data.get(username);
            if (state == null) {
                return null;
            }
            return User.withUsername(username)
                    .password(state.hash())
                    .roles(state.role())
                    .disabled(state.disabled())
                    .build();
        }

        synchronized boolean change(String username, ChangePassword input) {
            State old = data.get(username);
            if (old == null || old.disabled() || input == null
                    || input.oldPassword() == null
                    || input.newPassword() == null
                    || input.newPassword().length() < 12
                    || !encoder.matches(input.oldPassword(), old.hash())
                    || encoder.matches(input.newPassword(), old.hash())) {
                return false;
            }
            data.put(username, new State(
                    encoder.encode(input.newPassword()),
                    false, old.role(), old.version() + 1));
            return true;
        }

        synchronized boolean lock(String username) {
            State old = data.get(username);
            if (old == null) {
                return false;
            }
            data.put(username, new State(
                    old.hash(), true, old.role(), old.version() + 1));
            return true;
        }
    }

    @RestController
    static final class Api {
        private final Accounts accounts;

        Api(Accounts accounts) {
            this.accounts = accounts;
        }

        @GetMapping("/csrf")
        Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
            Mono<CsrfToken> token =
                    exchange.getAttribute(CsrfToken.class.getName());
            return token.map(value -> Map.of(
                    "headerName", value.getHeaderName(),
                    "token", value.getToken()));
        }

        @GetMapping("/me")
        Mono<String> me(Principal principal) {
            return Mono.just("ME:" + principal.getName());
        }

        @PostMapping("/account/password")
        Mono<ResponseEntity<String>> changePassword(
                Principal principal,
                @RequestBody ChangePassword input,
                ServerWebExchange exchange) {
            return Mono.fromCallable(
                    () -> accounts.change(principal.getName(), input))
                .subscribeOn(Schedulers.boundedElastic())
                .flatMap(changed -> changed
                    ? exchange.getSession()
                        .flatMap(WebSession::invalidate)
                        .thenReturn(ResponseEntity.ok("PASSWORD_CHANGED"))
                    : Mono.just(ResponseEntity.badRequest()
                        .body("PASSWORD_NOT_CHANGED")));
        }

        @PostMapping("/admin/lock/{username}")
        Mono<ResponseEntity<String>> lock(@PathVariable String username) {
            return Mono.fromSupplier(() -> accounts.lock(username))
                    .map(ok -> ok
                        ? ResponseEntity.ok("ACCOUNT_LOCKED")
                        : ResponseEntity.notFound().<String>build());
        }
    }
}
~~~

**Ý nghĩa đoạn code:**

- `Accounts` lưu password hash bằng `DelegatingPasswordEncoder`, giữ cờ `disabled` và tăng `version` khi password/trạng thái thay đổi. Dữ liệu chỉ nằm trong RAM; khởi động lại ứng dụng sẽ khôi phục tài khoản demo, **không phải repository production**.
- `ReactiveUserDetailsService` trả UserDetails mới mỗi khi manager cần xác thực. Khi `disabled` đã đổi, lần xác thực Basic sau đó bị từ chối.
- `UserDetailsRepositoryReactiveAuthenticationManager` dùng cùng `PasswordEncoder` để kiểm tra password. Không tự so sánh password trong controller.
- `NoOpServerSecurityContextRepository` tránh lưu authentication Basic giữa các request. Đây là ví dụ API tự kiểm tra credentials mỗi lần; `WebSession` vẫn có thể được CSRF dùng riêng.
- `POST /account/password` lấy tên user từ `Principal` đã xác thực, không tin username trong payload. Sau cập nhật thành công, hủy WebSession hiện tại — không liên quan đến việc thu hồi mọi thiết bị hay JWT.
- `POST /admin/lock/{username}` chỉ được gọi với `ROLE_ADMIN`. Trạng thái locked/disabled chỉ có tác dụng ở request tiếp theo dùng account đó trong demo.
- Sử dụng `Schedulers.boundedElastic()` cho đoạn `PasswordEncoder.matches/encode` của thao tác thay password, tránh chạy chi phí CPU ấy trực tiếp trên event loop. Với ứng dụng production, dùng repository reactive, cơ chế cạnh tranh/transaction và điều chỉnh scheduler phù hợp.
- Mật khẩu mẫu nằm trong source để dễ kiểm thử; **không triển khai chúng trong môi trường thật**. Không log JSON request chứa password.

**Giới hạn cần hiểu:** do dùng Basic, thông tin username/password vẫn được gửi lại khi client thực hiện request. Cơ chế hủy WebSession ở ví dụ chỉ chủ yếu tác động phiên dùng cho CSRF; để minh họa cookie login đã xác thực tồn tại giữa request và việc thu hồi nhiều phiên, dùng mô hình session ở phần 5–6.

### 9.3. Chạy ứng dụng

Tại thư mục có `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows dùng `.\mvnw.cmd spring-boot:run`; nếu không có Maven wrapper, dùng `mvn spring-boot:run`. Ứng dụng nghe `http://localhost:8080` nếu cổng mặc định chưa bị thay đổi.

Thử GET không làm đổi trạng thái:

~~~bash
curl -i -u 'learner:learnerOld123!' http://localhost:8080/me
curl -i -u 'learner:wrong' http://localhost:8080/me
~~~

Kết quả mong đợi: request đầu HTTP **200**, body `ME:learner`; request thứ hai HTTP **401**. Trên PowerShell, có thể dùng `curl.exe` để tránh alias `Invoke-WebRequest`.

### 9.4. Đổi password mà vẫn giữ CSRF protection

Spring Security reactive bật CSRF mặc định. Không tắt CSRF chỉ để thao tác `POST` thuận tiện. Đầu tiên lấy token và cookie phiên:

~~~bash
curl -i -c cookies.txt http://localhost:8080/csrf
~~~

Response body chứa JSON với `headerName` và `token`; thông thường header cần gửi là `X-CSRF-TOKEN`. Lưu **giá trị token thực tế của response** và dùng file cookie vừa được tạo. Nếu token được lưu trong WebSession, request tiếp theo phải dùng **đúng cookie** đi kèm token; gửi token không ghép với cookie sẽ không qua kiểm tra.

Sau đó (thay `TOKEN_FROM_CSRF_RESPONSE` bằng token đã nhận):

~~~bash
curl -i -b cookies.txt \
  -u 'learner:learnerOld123!' \
  -H 'Content-Type: application/json' \
  -H 'X-CSRF-TOKEN: TOKEN_FROM_CSRF_RESPONSE' \
  -d '{"oldPassword":"learnerOld123!","newPassword":"learnerNew123!"}' \
  http://localhost:8080/account/password
~~~

Với terminal Windows không hỗ trợ backslash xuống dòng, đặt toàn bộ câu lệnh trên **một dòng**; quote JSON phù hợp shell. Kết quả mong đợi là **HTTP 200** cùng body `PASSWORD_CHANGED`. Trong response này WebSession hiện tại đã được invalidate; token/cookie CSRF cũ không còn là cơ sở cho request POST tiếp theo.

Kiểm chứng password cũ và password mới:

~~~bash
curl -i -u 'learner:learnerOld123!' http://localhost:8080/me
curl -i -u 'learner:learnerNew123!' http://localhost:8080/me
~~~

Kết quả mong đợi: password cũ **401**, password mới **200** và body `ME:learner`. Đây là vì Basic thực hiện **authentication mới ở mỗi request**, không phải bằng chứng rằng tất cả login session đã bị thu hồi.

### 9.5. Khóa tài khoản và quan sát

Gọi lại `GET /csrf` để lấy token/cookie mới sau phiên cũ đã bị invalidate; nếu muốn dùng cùng command line, ghi vào `cookies.txt` rồi thay token placeholder. Với Basic user admin có `ROLE_ADMIN`:

~~~bash
curl -i -b cookies.txt \
  -u 'admin:adminSecret123!' \
  -H 'X-CSRF-TOKEN: TOKEN_FROM_NEW_CSRF_RESPONSE' \
  -X POST http://localhost:8080/admin/lock/learner
~~~

Kết quả mong đợi **HTTP 200** và body `ACCOUNT_LOCKED`. Bây giờ:

~~~bash
curl -i -u 'learner:learnerNew123!' http://localhost:8080/me
~~~

Kết quả mong đợi **401** vì tài khoản đã disabled. Không thực hiện hành động khóa admin trong bài demo trừ khi chủ ý thử cách hệ thống tự ngắt quyền admin. Vì state chỉ trong RAM, restart sẽ trở về credential ban đầu.

### 9.6. Vì sao ví dụ vẫn chưa phải production?

Ví dụ không có database, audit bền vững, rate limiting, MFA, policy password đầy đủ, distributed session, reset token, refresh token, event-driven revocation hoặc quản lý khóa bí mật. Nó cho phép quan sát **cơ chế kiểm tra UserDetails mới**. Khi chuyển sang triển khai thật, thêm transaction/optimistic locking, giới hạn concurrency, xử lý lỗi kho dữ liệu và kiểm thử song song đổi password/đăng nhập.

## 10. Thiết kế triển khai production theo từng mô hình

### 10.1. WebFlux + form login + cookie WebSession

- Dùng một `ServerSecurityContextRepository` phù hợp (thường `WebSessionServerSecurityContextRepository`) để lưu authentication giữa request.
- Khi user tự logout, xóa SecurityContext và invalidate WebSession hiện tại qua logout handler.
- Khi password đổi, tài khoản bị khóa hoặc quyền thay đổi, **tìm mọi session đã đăng ký và thu hồi**; tại các endpoint nhạy cảm có thể thêm kiểm tra account version/role hiện hành.
- Nếu nhiều instance, sử dụng session store chia sẻ và registry tương thích Spring Session; không dựa vào map của một node.
- Giữ CSRF cho các request thay đổi trạng thái; gán `Secure`/`HttpOnly`/`SameSite` cho cookie theo ngữ cảnh.
- Sau logout hoặc password change, cookie session cũ không còn cấp quyền; thông báo người dùng đăng nhập lại.

### 10.2. API HTTP Basic

- Mỗi request gửi username/password; manager cần đọc trạng thái user hiện hành.
- Password cũ bị từ chối ở lần auth mới; account disabled cũng bị từ chối.
- Không có “JWT/session đăng nhập Basic” để revoke nếu ứng dụng không lưu SecurityContext qua session.
- Nếu Basic được dùng trong trình duyệt, cần cân nhắc nguy cơ CSRF vì browser có thể tự gửi credentials đã cache.
- Ưu tiên cơ chế token phù hợp cho hệ thống hiện đại thay vì giữ password trên mỗi request khi không cần thiết.

### 10.3. API Bearer JWT

- Resource server xác thực signature, issuer, thời gian hiệu lực và các claim theo cấu hình.
- Cập nhật password/account không tự viết lại JWT đang lưu phía client.
- Dùng TTL ngắn + refresh revocation, hoặc kiểm tra token version/denylist trên mỗi request; với yêu cầu thu hồi gần tức thì cần kho trạng thái chia sẻ hoặc introspection.
- Nếu role/scope trong token đã cũ, phải tái đánh giá quyền hoặc thu hồi token; không tin mãi một claim cũ.
- Kiểm tra cả auth server và các resource server, vì thay password tại một dịch vụ không đủ nếu dịch vụ khác vẫn tin token cũ.

### 10.4. OAuth2/OIDC và quản lý phiên ngoài ứng dụng

- Logout ở relying party chỉ có thể xóa session ứng dụng; IdP có thể còn phiên SSO.
- Dùng tính năng logout/revocation được nhà cung cấp danh tính hỗ trợ, có kiểm tra callback/bảo mật request.
- Nếu password do IdP quản lý, quy trình đổi/reset phải diễn ra tại IdP.
- Xác minh tác động đối với refresh token, device session, browser session và các ứng dụng dùng chung IdP.

## 11. Những lỗi thực tế thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Password cũ vẫn đăng nhập được | Hash chưa commit, cache user cũ, sai kho dữ liệu, login manager không đọc state mới | Kiểm tra transaction, source of truth, cache và authentication manager |
| Password đổi nhưng tab đang đăng nhập vẫn truy cập | SecurityContext đã lưu trong WebSession | Kiểm tra session repository và cơ chế invalidate |
| Xóa cookie nhưng token Bearer còn chạy | JWT độc lập với cookie | Kiểm tra token TTL, `jti`, version/introspection |
| Khóa user nhưng vẫn có `ROLE_ADMIN` | Session/token cũ giữ authorities | Revoke context/token hoặc kiểm tra quyền hiện hành mỗi request |
| POST đổi mật khẩu trả 403 | Có thể thiếu CSRF token/cookie hoặc user thiếu role | Kiểm tra `CsrfWebFilter`, challenge và rule authorization |
| “Revoke all sessions” chỉ ảnh hưởng một node | Registry/store in-memory theo instance | Dùng distributed store và đồng bộ index principal |
| Logout ở app nhưng đăng nhập lại tự động | IdP SSO session còn tồn tại | Kiểm tra RP/IdP logout và refresh token |
| Mật khẩu mới dùng được nhưng thông báo “thu hồi thất bại” | Password commit xong, một bước revoke từ xa lỗi | Audit, retry có idempotency và per-request version checks |
| 401 thay vì 403 sau khi account bị khóa | Authentication của Basic thất bại trước authorization | Phân biệt authentication failure với role denial |

### 11.1. Cảnh báo với cache

Một service có thể cache `UserDetails` hoặc kết quả phân quyền. Khi password/role/disabled thay đổi, phải xử lý invalidation thích hợp. Cache TTL dài có thể duy trì quyền sai trong vài phút; nếu truy cập nhạy cảm cần nhất quán mạnh hơn, kiểm tra bản ghi hoặc version mới khi request tới.

### 11.2. Race condition

Nếu request A xác thực bằng password cũ **đồng thời** request B thay password, có thể A đã vượt bước xác thực trước khi update hoàn tất. Không thể giả định hủy được mọi request đang chạy; xác định rõ guarantee như “mọi request mới sau commit phải kiểm tra version mới”, và với thao tác nhạy cảm hãy kiểm tra quyền một lần nữa gần điểm commit nghiệp vụ.

### 11.3. Đừng nuốt lỗi revoke

Tránh mẫu:

~~~java
return updatePassword()
        .then(revokeAllSessions())
        .onErrorResume(error -> Mono.empty());
~~~

Đây là snippet với các method giả định. Nó che đi lỗi thật, khiến API có thể báo thành công dù chưa thu hồi. Hãy tách trạng thái password commit và trạng thái revoke, audit và retry có giới hạn; nếu cần guarantee mạnh, dựa thêm vào version check của request.

## 12. Kế hoạch kiểm thử

Đừng kiểm thử chỉ một login thành công. Bộ case tối thiểu:

1. **Password change đúng:** old password được xác minh, hash mới được lưu, password cũ thất bại, password mới thành công.
2. **Password change sai:** mật khẩu cũ sai hoặc password mới không hợp lệ; không cập nhật hash hay securityVersion.
3. **CSRF:** POST đổi password thiếu token/cookie hợp lệ bị chặn khi dùng session/cookie authentication.
4. **Current session revocation:** sau logout/password change theo policy, cookie session cũ không còn cấp quyền.
5. **Other device revocation:** đăng nhập ở thiết bị A/B, đổi password ở A; nếu policy yêu cầu all-session revocation thì B phải bị buộc xác thực lại.
6. **Account disabled/locked:** login mới thất bại; session/token đã cấp cũng bị chặn trong giới hạn thời gian đã công bố.
7. **Role changed:** `ROLE_ADMIN` bị gỡ, request đặc quyền bị deny dù session/token cũ còn tồn tại.
8. **JWT/refresh:** access token cũ tuân theo TTL/version/denylist, refresh token cũ không xin thêm access token sau revoke.
9. **Nhiều node:** thu hồi ở node A phải được node B nhìn thấy trong khoảng trễ cho phép.
10. **Lỗi giữa chừng:** update password thành công nhưng một backend revoke timeout; retry và audit không làm mất quyền kiểm soát.
11. **Race:** cùng lúc có hai request đổi password hoặc lock+login; kết quả theo version/transaction rõ ràng.
12. **Thông tin nhạy cảm:** password/token không xuất hiện trong server log, metrics label, tracing tag, URL query hoặc thông báo lỗi trả client.

Với WebFlux, dùng `WebTestClient`, hỗ trợ Spring Security test và `StepVerifier` cho các publisher. Khi kiểm tra “logout mọi thiết bị” cần cookie jar độc lập cho nhiều client, thay vì dùng một cookie cho hai cửa sổ.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Đã đổi password trong database nhưng cookie WebSession cũ vẫn truy cập được. Có phải password update thất bại?

**Trả lời:** Không nhất thiết. Login session có thể dùng SecurityContext đã lưu, không kiểm tra lại password mỗi request. Cần thu hồi session hoặc kiểm tra security version/current account state.

**Câu 2.** HTTP Basic và JWT khác nhau thế nào sau khi đổi password?

**Trả lời:** Basic thường kiểm tra username/password mỗi request nên password cũ bị từ chối ngay khi nguồn user được cập nhật. JWT có thể được xác thực offline mà không đọc password hash; phải có TTL/revocation/version để giảm thời gian token cũ hợp lệ.

**Câu 3.** `WebSessionServerLogoutHandler` có xóa mọi session của user không?

**Trả lời:** Không. Nó vô hiệu hóa WebSession đang xử lý logout; muốn tất cả phiên phải dùng registry/store phù hợp và kiểm tra phạm vi bao phủ.

**Câu 4.** Vì sao giảm role trong database không đủ?

**Trả lời:** SecurityContext hoặc JWT cũ có thể giữ authorities cũ. Phải refresh hoặc revoke, hoặc tra quyền hiện tại cho request cần kiểm soát.

**Câu 5.** Tại sao POST đổi password cần CSRF khi sử dụng cookie?

**Trả lời:** Browser có thể tự gửi cookie đến trang đích; kẻ tấn công có thể lợi dụng hành vi đó. CSRF token làm request thay đổi trạng thái phải mang dữ liệu mà trang bên ngoài không tự có.

**Câu 6.** Nếu session registry báo không có phiên, có thể chắc user đã logout hết không?

**Trả lời:** Không. Có thể một số phiên chưa được đăng ký, registry không chia sẻ giữa các node, hoặc lookup principal sai. Cần bảo đảm registry/store thực sự bao phủ phiên và có request-side revocation check khi yêu cầu bảo đảm mạnh.

## 14. Nguồn tài liệu chính thức

- [Spring Security — Reactive Concurrent Sessions Control](https://docs.spring.io/spring-security/reference/reactive/authentication/concurrent-sessions-control.html)
- [Spring Security — Reactive Logout](https://docs.spring.io/spring-security/reference/reactive/authentication/logout.html)
- [Spring Security — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — Reactive HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/reactive/authentication/basic.html)
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Security API — ReactiveSessionRegistry](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/session/ReactiveSessionRegistry.html)
- [Spring Security API — WebSessionServerLogoutHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/logout/WebSessionServerLogoutHandler.html)
- [Spring Security API — WebSessionServerSecurityContextRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html)
- [Spring Security API — UserDetailsRepositoryReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html)
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Session — WebSession Integration](https://docs.spring.io/spring-session/reference/web-session.html)
