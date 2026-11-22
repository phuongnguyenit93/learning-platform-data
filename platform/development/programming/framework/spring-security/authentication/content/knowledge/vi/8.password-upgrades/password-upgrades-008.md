# Thu hồi phiên, remember-me hoặc token liên quan sau đổi mật khẩu

> **Ngữ cảnh:** Spring Security – authentication, nhóm **Nâng cấp mật khẩu**. Bài học trình bày cách khiến các thông tin đăng nhập đã được cấp trước đó mất hiệu lực sau khi đổi hoặc reset mật khẩu: HTTP session, remember-me cookie, refresh token và access token. Nội dung tập trung vào hành vi thật của Spring Security/Spring Session, chính sách thu hồi nhiều thiết bị, tính nhất quán khi có nhiều máy chủ và các tình huống kiểm thử. Ví dụ chạy độc lập dùng **Java 17+** để kiểm chứng logic thu hồi; các đoạn tích hợp Spring được đánh dấu rõ phạm vi phụ thuộc.

## 1. Đổi mật khẩu không tự động đăng xuất mọi thiết bị

Giả sử tài khoản An đã đăng nhập ở ba nơi:

- Laptop A giữ một `JSESSIONID` trỏ tới HTTP session.
- Điện thoại B dùng remember-me cookie để tự đăng nhập khi session hết hạn.
- Một ứng dụng di động C giữ access token và refresh token.

An phát hiện mật khẩu có thể bị lộ, đổi mật khẩu từ laptop A. Database đã ghi **hash mật khẩu mới**. Điều này là cần thiết nhưng chưa đủ để bảo đảm B và C mất quyền truy cập.

**Vì sao?** Sau lần đăng nhập đầu, hệ thống thường sử dụng các **credential thứ cấp** để xác định request tiếp theo: session ID, remember-me token, refresh token, access token hoặc API key. Chúng có vòng đời và nơi lưu khác với password hash.

```text
Password cũ --(đăng nhập hợp lệ)--> Credential thứ cấp
                                      |
             +------------------------+------------------------+
             |                        |                        |
          HTTP session          Remember-me cookie       OAuth2/OIDC token
             |                        |                        |
     SecurityContext trong       TokenBased /          Access token / refresh
     session store              PersistentToken        token / authorization
             |                        |                        |
             +------------------------+------------------------+
                                      |
                            Đổi mật khẩu trong DB
                                      |
                     Các credential cũ có bị từ chối không?
                   -> Chỉ nếu cơ chế tương ứng có kiểm tra
                      hoặc quy trình thu hồi đã thực thi.
```

Một ứng dụng có thể cho phép tiếp tục giữ session hiện tại sau khi đổi mật khẩu thành công; một ứng dụng khác chọn **đăng xuất khỏi mọi thiết bị**. Đây là quyết định sản phẩm/bảo mật. Tuy nhiên, nếu đổi mật khẩu do nghi ngờ bị chiếm đoạt, reset thông qua quên mật khẩu hoặc quản trị viên cưỡng chế, chính sách mạnh thường yêu cầu thu hồi các hình thức truy cập liên quan, không chỉ thay mật khẩu để chặn login bằng password cũ.

**Phạm vi bài:** nói về **thay đổi credential do người dùng hoặc quy trình bảo mật xác minh**. Việc tự động rehash password từ cost BCrypt cũ sang cost mới bằng `upgradeEncoding` **không đồng nghĩa người dùng đã đổi mật khẩu**; thông thường không cần đăng xuất mọi thiết bị chỉ vì một lần nâng cấp hash kỹ thuật.

## 2. Phân loại credential trước khi chọn cách thu hồi

| Cơ chế | Client đang giữ gì? | Server kiểm tra gì ở lần dùng tiếp theo? | Cách thu hồi tiêu biểu |
| --- | --- | --- | --- |
| HTTP session | Session ID trong cookie | Session còn tồn tại và chứa SecurityContext phù hợp | Xóa/invalidate session; hoặc kiểm tra phiên bản bảo mật của account |
| Token-based remember-me | Cookie mang dữ liệu và chữ ký | Chữ ký dựa trên username, expiry, password từ `UserDetails` và secret key | Đổi password hash làm chữ ký cũ không khớp nếu dữ liệu được nạp mới; xóa cookie hiện tại |
| Persistent remember-me | Cookie chứa series/token | Bản ghi token tại `PersistentTokenRepository` | `removeUserTokens(username)` để xóa các token của user; xóa cookie trên client hiện tại |
| JWT access token | Token tự chứa, đã ký | Chữ ký, issuer, audience, expiry, policy | TTL ngắn; denylist `jti`, account security version/epoch, introspection hoặc gateway policy |
| Opaque access token | Token tham chiếu | Token store/introspection | Revoke hoặc đánh dấu inactive trong authorization/token store |
| Refresh token | Refresh credential | Token store, rotation, token family | Revoke refresh token hoặc cả token family/authorization |
| API key riêng | Khóa ứng dụng cấp | API key repository | Thu hồi/rotate key qua chính sách riêng |
| SSO/IdP session | Cookie hoặc token ở nhà cung cấp danh tính | Chính sách phiên của Identity Provider | Phối hợp logout/revoke với IdP; local logout không tự làm IdP logout |

**Thu hồi** có hai dạng cần phân biệt: **vật lý** (xóa bản ghi token/session) và **logic** (giữ dữ liệu nhưng request bị từ chối vì phiên bản account hoặc timestamp không còn hợp lệ). Hai dạng có thể phối hợp để đạt hiệu lực nhanh và dọn rác sau đó.

### Không nhầm các loại token

Một refresh token không phải access token; xóa refresh token **ngăn cấp access token mới** nhưng access token đã cấp có thể vẫn hợp lệ đến hạn. Một ID token OIDC mang thông tin đăng nhập của user và không mặc nhiên là bearer credential để gọi API. Remember-me cookie không giống session cookie, dù một client có thể giữ cả hai.

### Thu hồi là một yêu cầu kiểm chứng được

Không chỉ viết “logout thành công”. Cần định nghĩa:

- **Những loại credential nào** phải mất hiệu lực?
- Thu hồi **tất cả thiết bị** hay **chỉ các thiết bị khác**?
- **Khi nào** không còn truy cập được: sau commit đổi password, ở request kế tiếp, hay sau TTL?
- Dịch vụ nhiều node có nhìn cùng trạng thái thu hồi không?
- Request **đang chạy** tại thời điểm đổi password được xử lý thế nào?
- Có cấp lại session/token mới bằng password mới hay bắt đăng nhập lại?
- Nếu bước xóa token bị lỗi mạng, hệ thống có còn bảo đảm hiệu lực chính sách không?

Những câu hỏi này là hợp đồng bảo mật, không nên để framework tự lựa chọn ngầm.

## 3. Hai nhóm đổi mật khẩu và chính sách mặc định

Không phải mọi thay đổi hash có cùng ý nghĩa.

### 3.1. Đổi mật khẩu chủ động khi đang đăng nhập

Người dùng đã đăng nhập, cung cấp password cũ hoặc một bước xác minh mạnh tương đương rồi chọn password mới. Hệ thống có thể áp chính sách:

- **A – Thu hồi tất cả, kể cả thiết bị hiện tại:** đơn giản để giải thích, thích hợp khi sản phẩm muốn bảo vệ mạnh. Sau khi đổi thành công, yêu cầu đăng nhập lại.
- **B – Thu hồi các thiết bị khác, giữ thiết bị hiện tại:** thuận tiện hơn, nhưng phải bảo đảm request hiện tại được xác minh lại, phiên hiện tại được gia hạn/rotate phù hợp, và không tái cấp quyền nhờ cookie cũ.
- **C – Chỉ thu hồi một số token:** chỉ phù hợp khi threat model và contract sản phẩm giải thích rõ ràng; không nên để mặc định vô tình.

### 3.2. Reset password hoặc đổi do nghi ngờ chiếm đoạt

Khi user dùng luồng quên mật khẩu, administrator bắt buộc reset, hoặc điều tra cho thấy credential có thể bị lộ, nên đánh giá mức độ rủi ro cao hơn. Thường cần **thu hồi tất cả các phiên, remember-me và refresh token thuộc user**, cùng chính sách để access token cũ bị từ chối nhanh.

Reset password phải có quy trình chứng minh quyền sở hữu qua kênh phù hợp. **Không được** cho phép một token reset password được sử dụng như access token để gọi API thông thường, và không giữ token reset có thể replay sau khi dùng.

### 3.3. Tự động rehash khi login

`DaoAuthenticationProvider` có thể dùng `PasswordEncoder.upgradeEncoding` và `UserDetailsPasswordService` để lưu hash theo tham số mới. Nếu **raw password không thay đổi**, đây là nâng cấp lưu trữ, không nhất thiết là sự kiện cần logout. Nếu dùng một listener “bất kỳ thay đổi ở cột password_hash đều thu hồi session”, hãy cân nhắc tách sự kiện **PASSWORD_CHANGED** và **PASSWORD_HASH_UPGRADED**; nếu không, mỗi đợt nâng BCrypt cost có thể tự động đăng xuất hàng loạt user ngoài ý muốn.

## 4. Luồng nghiệp vụ chuẩn sau khi xác minh password mới

Một luồng đổi mật khẩu an toàn nên có các bước theo thứ tự và ranh giới rõ:

```text
POST /account/change-password (CSRF-protected nếu dùng session)
       |
       v
Xác minh caller + bước re-authentication cần thiết
       |
       v
Kiểm tra new password policy, password history/risk (nếu có)
       |
       v
PasswordEncoder.encode(newRawPassword)
       |
       v
TRANSACTION có thẩm quyền:
  - bảo đảm account và credential version vẫn đúng
  - cập nhật password_hash
  - tăng security_epoch / credential_version
  - vô hiệu hóa token/reset/refresh thuộc cùng nguồn nếu cùng DB
  - ghi audit/outbox event để cleanup hệ thống khác
COMMIT
       |
       v
Thu hồi session/remember-me/refresh token ở những kho liên quan
       |
       v
Xóa SecurityContext và cookie của request hiện tại nếu policy logout all
       |
       v
Trả kết quả: yêu cầu đăng nhập lại
```

**Lưu ý quan trọng:** nếu xóa session/refresh token nằm ở một kho khác hoặc dịch vụ khác, không thể coi tất cả thao tác là một transaction SQL duy nhất. Khi yêu cầu “ngay sau commit, credential cũ không được dùng nữa”, một thiết kế tốt dùng **security epoch/credential version làm kiểm tra có thẩm quyền** trên đường truy cập, còn việc xóa vật lý bằng event/outbox có thể hoàn tất sau. Nếu không có kiểm tra này mà chỉ phụ thuộc worker async, phải chấp nhận và công bố **cửa sổ trễ thu hồi**, không tuyên bố thu hồi tức thì.

### Không bỏ qua khả năng request đã đi qua authorization

Một request đang xử lý đã được Spring Security chấp nhận **trước** lúc đổi password có thể tiếp tục chạy nếu business service không kiểm tra phiên bản bảo mật lần nữa. Khi nghiệp vụ yêu cầu thu hồi thật nghiêm ngặt, ví dụ chuyển tiền hoặc cập nhật quyền admin, cần chính sách kiểm tra tại thời điểm thực hiện giao dịch. Không có thao tác “xóa mọi session” nào có thể đảo ngược những thay đổi đã được commit bởi request cũ.

## 5. Thu hồi HTTP session hiện tại

Spring Security Servlet thường lưu `SecurityContext` trong HTTP session sau form login. Cookie `JSESSIONID` chỉ là **khóa tham chiếu tới session**; xóa cookie trên trình duyệt không tự bảo đảm server đã xóa bản ghi session.

Khi user đổi password xong và chính sách yêu cầu logout thiết bị hiện tại, có thể gọi `SecurityContextLogoutHandler` để invalidate session hiện tại, xóa authentication/context. Trong các flow logout chuẩn, Spring Security còn chạy các handler cho remember-me, CSRF và sự kiện.

Đoạn dưới là **mảnh tích hợp** trong MVC controller có `request`, `response`, `authentication` và một password-change service đã xử lý cập nhật an toàn:

```java
SecurityContextLogoutHandler logout =
        new SecurityContextLogoutHandler();

logout.logout(request, response, authentication);
```

Import `org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler`, các kiểu request/response từ `jakarta.servlet.http` và `Authentication`. Cần chọn thời điểm gọi **sau khi** thay đổi password đã commit thành công; nếu call trước và transaction đổi password lỗi, user có thể bị logout không cần thiết và nhận kết quả khó hiểu.

### Vì sao nên dùng thành phần logout của Spring Security?

`HttpSession.invalidate()` chỉ xử lý một session servlet. `SecurityContextLogoutHandler` ngoài việc invalidate session còn xử lý `SecurityContextHolder` và `SecurityContextRepository` theo cấu hình. Với Spring Security 6/7, cần chú ý cơ chế save/clear context rõ ràng, đặc biệt nếu ứng dụng có custom security context repository.

Khi có remember-me cookie, chỉ gọi `SecurityContextLogoutHandler` **chưa đủ** để bảo đảm toàn bộ remember-me cookie/token được dọn. Logout chain chuẩn của Spring Security có thể gọi handler remember-me; với custom controller tự gọi logout handler, cần thực hiện thêm các phần thích hợp.

### Ưu tiên logout URL đã cấu hình khi có thể

Spring Security cung cấp `POST /logout` với CSRF protection và một chuỗi `LogoutHandler`. Một thay đổi password đặc biệt đôi khi phải thực hiện trong endpoint riêng, nhưng không nên tự bỏ mất các bước cleanup của logout chain.

Một fragment cấu hình hợp lệ trong `HttpSecurity`, nếu cần success HTTP status thay vì redirect:

```java
.logout(logout -> logout
        .logoutSuccessHandler(
                new HttpStatusReturningLogoutSuccessHandler()))
```

Đây **không** phải toàn bộ `SecurityFilterChain`; import `HttpStatusReturningLogoutSuccessHandler` từ package `org.springframework.security.web.authentication.logout`. Nên dùng logout qua HTTP POST và CSRF token phù hợp; GET làm thao tác thay đổi trạng thái là rủi ro.

### Xóa cookie không đồng nghĩa xóa phía server

Cookie `JSESSIONID` thường có `HttpOnly` và `Secure` trong môi trường HTTPS. Khi logout, application có thể gửi `Set-Cookie` hết hạn, nhưng phải kiểm tra path/domain của cookie và hành vi container/proxy. Cookie còn trên client có thể gây request “invalid session”, nhưng **quyền truy cập phải dựa vào trạng thái server**, không dựa vào sự tin tưởng rằng browser đã thực sự xóa cookie.

## 6. Thu hồi mọi HTTP session của một account

Đây là phần khác với logout hiện tại. `SecurityContextLogoutHandler.logout(...)` chỉ xử lý session gắn với **request hiện tại**. Nó không tự biết các session trên điện thoại hoặc browser khác.

Có hai hướng thường gặp.

### 6.1. Spring Session và repository có index theo principal

Nếu ứng dụng dùng Spring Session Redis/JDBC và implementation hỗ trợ `FindByIndexNameSessionRepository`, có thể tìm các session theo principal rồi xóa từng bản ghi:

```java
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

@Service
class AccountSessionRevoker {

    private final FindByIndexNameSessionRepository<? extends Session>
            sessions;

    AccountSessionRevoker(
            FindByIndexNameSessionRepository<? extends Session> sessions) {
        this.sessions = sessions;
    }

    void revokeAllForPrincipal(String principalName) {
        var found = sessions.findByPrincipalName(principalName);

        for (String sessionId : found.keySet()) {
            sessions.deleteById(sessionId);
        }
    }
}
```

Đây là **class Java có thể tích hợp** khi đã có Spring Session indexed repository được cấu hình; nó không phải app chạy độc lập vì cần Spring Session/Redis hoặc JDBC backing store. `findByPrincipalName` phụ thuộc **index principal** đã được ghi cho các session. Nếu app dùng custom principal, multi-tenant hoặc session không được index đúng, hàm có thể không tìm thấy hết session. Trong production nên dùng **account ID bền vững** và một cơ chế index tương ứng để tránh username đổi hoặc trùng giữa các tenant; method theo username ở đây chỉ minh họa API mặc định.

`deleteById` xóa bản ghi session từ store. Client giữ cookie cũ sẽ không còn truy xuất được session đó trên request kế tiếp. Với nhiều node dùng chung repository, chiến lược này phù hợp hơn danh sách session chỉ nằm trong RAM mỗi node. Phải kiểm thử độ trễ nhất quán, cache và các request đang chạy.

### 6.2. SessionRegistry/ConcurrentSessionFilter

Khi ứng dụng đã bật quản lý session đồng thời, Spring Security có thể theo dõi session bằng `SessionRegistry`. Có thể đánh dấu những session được đăng ký là hết hạn:

```java
for (SessionInformation info :
        sessionRegistry.getAllSessions(principal, false)) {
    info.expireNow();
}
```

Đây là **mảnh mã** cần `SessionRegistry`, `SessionInformation`, một `principal` đúng theo key của registry và cơ chế đăng ký/session listener. `expireNow()` thường **đánh dấu** session là expired; `ConcurrentSessionFilter` hoặc các thành phần quản lý liên quan phát hiện và xử lý khi request sau tới. Không nên mô tả nó là “xóa vật lý ngay mọi session trên mọi node”. Registry in-memory cũng không tự đồng bộ sang các máy chủ khác.

**Bẫy thường gặp:** nếu custom `UserDetails` không có `equals()/hashCode()` ổn định, hoặc các authentication mechanism không đăng ký session với registry, danh sách nhận được có thể thiếu. Nếu một app sử dụng Spring Session repository, cần quyết định một nguồn điều phối session rõ ràng thay vì giả định mọi registry đều biết nhau.

### 6.3. Session version/epoch như lớp phòng vệ

Bên cạnh xóa vật lý, có thể lưu:

```text
accounts:
  account_id
  password_hash
  security_epoch       BIGINT
```

Khi login bằng password, principal/session mang `securityEpochAtAuthentication`. Sau khi đổi password hợp lệ, transaction tăng `security_epoch`. Với mỗi request đã authenticated, filter/policy so sánh epoch trong session với epoch hiện hành ở nguồn tin cậy.

```text
sessionEpoch == account.securityEpoch  -> có thể tiếp tục
sessionEpoch != account.securityEpoch  -> từ chối, logout session
```

Điều này giúp từ chối session cũ kể cả khi một job xóa session bị chậm. Tuy nhiên, **nếu kiểm tra epoch bằng cache có TTL dài**, nó cũng có cửa sổ trễ; muốn “hiệu lực ngay”, phải định nghĩa consistency và cách fail closed khi nguồn phiên bản không khả dụng.

## 7. Remember-me có hai loại và cách thu hồi khác nhau

Remember-me giúp user trở lại trạng thái authenticated mà không nhập password ở lần ghé thăm sau. Spring Security hỗ trợ hai cách chính: token có chữ ký dựa trên thông tin user và token lưu ở repository. Chúng không giống nhau.

### 7.1. TokenBasedRememberMeServices: chữ ký gắn với password

Trong cơ chế token-based, remember-me cookie chứa thông tin như username, hạn dùng, tên thuật toán và chữ ký dựa trên password hiện tại từ `UserDetails` cộng secret key. Theo tài liệu Spring Security, khi password hoặc key thay đổi, cookie cũ không còn xác minh được chữ ký.

Điều kiện thực tế để điều đó đúng:

- `UserDetailsService` lần auto-login sau phải tải **password hash mới** từ nguồn tin cậy, không dùng cache cũ vô thời hạn.
- Secret key của remember-me phải được quản lý an toàn và nhất quán trên các node.
- Cookie cũ bị từ chối khi lần auto-login sau diễn ra; một **HTTP session đã được cấp trước đó** vẫn cần thu hồi riêng.
- Password hash được thay đổi do **rehash kỹ thuật** cũng có thể khiến chữ ký remember-me dựa trên hash cũ không khớp. Đây là một tác dụng phụ cần kiểm thử khi bật nâng cấp password hash tự động.

Không có cơ chế “xóa riêng một cookie ở browser B” từ phía server nếu token-based không có kho token theo series. Đổi password/hash hoặc rotate key ảnh hưởng chữ ký theo phạm vi tương ứng; với toàn bộ key chung, rotate key có thể vô hiệu hóa remember-me cookie của **mọi user**.

### 7.2. PersistentTokenBasedRememberMeServices: token có bản ghi phía server

Khi dùng persistent remember-me, cookie chứa series/token; server truy vấn `PersistentTokenRepository`. **Đổi password hash không tự xóa các bản ghi persistent token**. Nếu policy yêu cầu revoke toàn bộ remember-me token sau đổi password, hãy xóa chúng.

API chính thức:

```java
persistentTokenRepository.removeUserTokens(username);
```

Đây là **mảnh tích hợp**, với bean có type `org.springframework.security.web.authentication.rememberme.PersistentTokenRepository` và `username` xuất phát từ identity đã xác minh. `removeUserTokens(String username)` thu hồi các persistent login tokens của user theo contract repository.

Sau khi xóa, cookie còn lại trên một thiết bị khác không thể được chấp nhận nếu không có bản ghi tương ứng. Tuy nhiên, **cookie tại thiết bị hiện tại** cũng nên được xóa qua logout/remember-me handler và response phù hợp, để client không liên tục gửi token đã hỏng. Việc xóa remember-me token **không tự xóa** session hiện có.

### Ví dụ bảng persistent remember-me

```sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
```

Đây là schema tham khảo từ tài liệu, không phải schema bắt buộc cho mọi ứng dụng. Với username thay đổi, multi-tenant, yêu cầu audit hoặc token hash-at-rest, cần một thiết kế repository/domain phù hợp. Không gửi raw persistent token vào log, analytics hoặc support ticket.

### Có nên bật remember-me cho mọi ứng dụng?

Ứng dụng có dữ liệu nhạy cảm có thể chọn không dùng remember-me hoặc yêu cầu reauthentication cho hành động quan trọng. Remember-me là một loại credential kéo dài khả năng đăng nhập, làm tăng bề mặt bị đánh cắp cookie; không phải tính năng bắt buộc của Spring Security.

## 8. Access token JWT: thay password không làm chữ ký biến mất

JWT access token thường là đối tượng đã ký và tự chứa claims như `sub`, `iss`, `aud`, `iat`, `exp`, `jti`. Resource server có thể xác minh chữ ký và expiry **mà không truy vấn database tài khoản**. Do đó:

> Nếu JWT được phát hành trước lúc đổi mật khẩu nhưng chưa hết hạn, đổi password hash trên DB **không tự làm JWT thất bại trong bước kiểm chứng chữ ký**.

Các cách giới hạn ảnh hưởng:

1. **TTL access token ngắn:** giảm cửa sổ token cũ còn dùng được, nhưng không cho hiệu lực thu hồi tức thì.
2. **Denylist theo `jti`:** lưu ID token bị thu hồi đến thời điểm `exp`, kiểm tra ở resource server. Cần datastore/TTL, chống cache stale và chính sách fail closed.
3. **Account security epoch/credential version:** issuer đưa phiên bản vào claim được ký; resource server đối chiếu với phiên bản account hiện hành. Token mang phiên bản cũ bị từ chối, kể cả chữ ký/expiry vẫn hợp lệ.
4. **`valid_after`/`tokensValidAfter` timestamp:** từ chối token có thời điểm phát hành trước mốc đó. Cần chú ý độ phân giải `iat` (thường tính theo giây), lệch đồng hồ và request phát token đúng lúc thay đổi.
5. **Opaque token hoặc introspection:** server có quyền đánh dấu token inactive; resource server phải thực sự introspect hoặc có cache với TTL phù hợp.
6. **Gateway/policy service:** kiểm tra revocation tại một điểm trung tâm, nhưng mọi đường đi tới resource phải chịu cùng chính sách.

**Không tự đọc `sub` hay `credential_version` từ một JWT chưa được xác minh.** Decoder cần kiểm tra signature, issuer, audience và thời hạn theo đúng hợp đồng token. Claim chỉ đáng tin sau khi token được xử lý bởi cơ chế xác thực hợp lệ. Truy vấn phiên bản phải ràng buộc đúng issuer/account/tenant, tránh collision danh tính.

### Vì sao không chỉ dựa vào jti nếu cần “thu hồi tất cả”?

Nếu một user có hàng trăm JWT đã phát hành và hệ thống không lưu danh sách `jti`, khó biết toàn bộ token cần đưa vào denylist. Security epoch theo account giúp logic revoke tất cả token thuộc epoch cũ mà không liệt kê từng token. Ngược lại, denylist `jti` hữu ích khi chỉ thu hồi **một token cụ thể**.

### Request đã vào resource server trước khi epoch thay đổi

Dù resource server kiểm tra security epoch mỗi request, một request được chấp nhận trước lúc đổi password có thể đã đi vào business service. Nếu cần giới hạn nghiêm ngặt, hãy kiểm tra lại version/risk ở boundary của thao tác nhạy cảm; không hứa rằng thay password sẽ đảo ngược giao dịch đã được xác nhận.

## 9. Refresh token và token family: cần revoke riêng

Refresh token được dùng để lấy access token mới. Khi đổi password vì nghi ngờ credential bị lộ, nếu refresh token còn hoạt động thì client cũ vẫn có thể xin access token mới mà không cần password hiện tại.

Vì vậy, một chính sách logout-all thường cần:

- Thu hồi refresh token của user trong authorization/token store có thẩm quyền.
- Thu hồi **token family** khi ứng dụng có refresh token rotation và phát hiện replay/risk.
- Ngăn phát hành token mới từ grant/cookie/session cũ đã mất hiệu lực.
- Xác định cách xử lý access token đã phát hành: chờ TTL, denylist hoặc version check.
- Nếu hệ thống có nhiều client/tenant, ràng buộc phạm vi thu hồi cho đúng user và mục tiêu; không vô tình revoke toàn bộ khách hàng khác.

Spring Authorization Server sử dụng `OAuth2AuthorizationService` để lưu/truy vấn authorization và token theo giao thức. Nó **không cung cấp một lệnh chung đảm bảo “đổi password của username này thì mọi authorization trên mọi hệ thống đều bị xóa”**. Cần thiết kế quan hệ user – client – authorization trong storage, truy vấn đúng đối tượng, chính sách revoke và hiệu lực khi resource server tiếp tục dùng token.

Nếu token do **một Identity Provider bên ngoài** phát hành, ứng dụng của bạn không sở hữu datastore refresh token của họ. Cần sử dụng cơ chế revoke/logout do provider hỗ trợ và tuân theo phạm vi quyền quản trị. Không giả định revoke thành công nếu provider không xác nhận.

### Refresh rotation không thay thế password-change revocation

Rotation cấp refresh token mới sau mỗi lần sử dụng, giảm khả năng reuse token cũ. Nhưng một token family hiện còn hợp lệ vẫn có thể tạo access token sau khi password đã đổi nếu issuer không gắn grant với sự kiện credential change. Phải có policy dừng family hoặc ép xác thực lại.

## 10. OAuth2 Login và OIDC: logout local khác logout ở IdP

Trong Spring Security `oauth2Login`, user có thể giữ một **local HTTP session** chứa kết quả đăng nhập. Identity Provider còn có session/cookie hoặc refresh token riêng.

- **Local logout**: xóa session, SecurityContext, cookie của ứng dụng.
- **RP-Initiated Logout / provider logout**: yêu cầu IdP kết thúc phiên theo giao thức và khả năng provider.
- **Back-channel logout / front-channel logout**: các cơ chế IdP có thể thông báo các phiên liên quan, nếu được hỗ trợ và cấu hình.
- **Refresh token revoke**: yêu cầu token store của issuer làm invalid credential cấp lại token.

**Đổi mật khẩu ở IdP không tự động đảm bảo mọi local session của mọi ứng dụng Relying Party đã bị xóa**, trừ khi IdP và các RP phối hợp một cơ chế đáng tin và đã được kiểm thử. Tương tự, logout local có thể không làm IdP logout; user có thể đăng nhập lại nhờ SSO cookie còn hợp lệ.

Đối với hệ thống đa ứng dụng, nên xác định nơi có thẩm quyền phát sự kiện password change, định danh account chung, cách chuyển sự kiện revoke, và mức trễ tối đa được phép.

## 11. Security epoch/credentialVersion: thu hồi logic toàn account

Một mô hình hữu ích là có trường tăng dần theo sự kiện bảo mật:

```text
accounts
--------
id                  UUID
password_hash       VARCHAR
security_epoch      BIGINT
enabled             BOOLEAN
...

session/token
-------------
account_id          UUID
epoch_at_issue      BIGINT
issued_at           timestamp
...
```

Khi đổi/reset password hợp lệ, trong cùng transaction với cập nhật hash, tăng `security_epoch` từ 6 lên 7. Session/token được cấp trước mang epoch 6. Khi request dùng chúng:

```text
verify signature/session integrity
             |
             v
resolve trusted account ID
             |
             v
read current security_epoch from authoritative source
             |
             +-- equal: tiếp tục authorization
             |
             +-- different: reject + clear local context/token
```

**Không nhận account ID và epoch từ một request query tự khai để ra quyết định.** Epoch của token phải là claim đã được ký và xác minh hoặc metadata của server-side session; ID phải được ràng buộc với principal thực.

### Tại sao dùng version thay vì chỉ timestamp?

Một số token dùng `iat` độ phân giải giây, nên hai sự kiện gần nhau có thể có cùng giây; nhiều máy có đồng hồ lệch. Version tăng atomically theo account giúp diễn đạt “credential mới hơn” mà không lệ thuộc trực tiếp vào clock. Tuy vậy, dùng security epoch đòi hỏi resource server tra phiên bản hiện hành hoặc một nguồn cache được cập nhật đủ nhanh.

### Trạng thái sau khi đổi password

Một số chính sách tách nhiều version:

- `credential_version` tăng khi password/key thay đổi.
- `session_revoked_before` hoặc `security_epoch` tăng khi người dùng chọn logout all.
- `role_version` tăng khi authority bị revoke, nếu có yêu cầu thu hồi quyền tức thì.
- `mfa_version` hoặc `reauth_at` phục vụ step-up authentication.

Không nhất thiết phải có nhiều field từ đầu. Chọn mô hình tối giản có contract rõ, tránh tăng mọi version khi background migration chỉ rehash cùng plaintext, vì điều đó có thể vô tình logout không đúng ý định.

## 12. Ví dụ Java 17+ chạy được: thu hồi session, remember-me, refresh và JWT cũ

Để tập trung vào **ngữ nghĩa thu hồi**, ví dụ này dùng **Java thuần không cần Spring**. Nó **không phải hệ thống authentication thật**: không băm password, không tạo chữ ký JWT, không phát cookie mạng. Nó giả lập các grant đã được cấp và một thao tác `afterVerifiedPasswordChange` được gọi **chỉ sau khi** password service xác minh và commit thay đổi. Mục tiêu là chứng minh rằng khi version tăng và token records bị xóa, các credential cũ bị từ chối, dù JWT cũ vẫn có thể hợp lệ về chữ ký/expiry trong mô hình stateless.

Tạo file **`RevocationModelDemo.java`**:

```java
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;

public class RevocationModelDemo {

    record Grant(String userId, long securityEpoch) {}

    record SimulatedJwt(
            String userId,
            long securityEpoch,
            Instant expiresAt) {}

    static final class Store {
        private final Map<String, Long> epochs = new HashMap<>();
        private final Map<String, Grant> sessions = new HashMap<>();
        private final Map<String, Grant> rememberMe = new HashMap<>();
        private final Map<String, Grant> refreshTokens = new HashMap<>();

        synchronized long currentEpoch(String userId) {
            return epochs.getOrDefault(userId, 0L);
        }

        synchronized void issueSession(String id, String userId) {
            sessions.put(id, new Grant(userId, currentEpoch(userId)));
        }

        synchronized void issueRememberMe(String id, String userId) {
            rememberMe.put(id, new Grant(userId, currentEpoch(userId)));
        }

        synchronized void issueRefresh(String id, String userId) {
            refreshTokens.put(id,
                    new Grant(userId, currentEpoch(userId)));
        }

        synchronized SimulatedJwt issueJwt(
                String userId, Instant expiration) {
            return new SimulatedJwt(
                    userId, currentEpoch(userId), expiration);
        }

        private boolean validGrant(
                Map<String, Grant> store, String id) {
            Grant grant = store.get(id);
            return grant != null
                    && grant.securityEpoch()
                            == currentEpoch(grant.userId());
        }

        synchronized boolean sessionValid(String id) {
            return validGrant(sessions, id);
        }

        synchronized boolean rememberMeValid(String id) {
            return validGrant(rememberMe, id);
        }

        synchronized boolean refreshValid(String id) {
            return validGrant(refreshTokens, id);
        }

        synchronized boolean jwtAllowed(
                SimulatedJwt token,
                boolean signatureAlreadyVerified,
                Instant now) {

            return signatureAlreadyVerified
                    && now.isBefore(token.expiresAt())
                    && token.securityEpoch()
                            == currentEpoch(token.userId());
        }

        // Chỉ gọi SAU KHI credential change đã được xác minh và
        // commit. Không nhận lệnh thu hồi từ input public chưa tin cậy.
        synchronized void afterVerifiedPasswordChange(String userId) {
            long next = currentEpoch(userId) + 1;
            epochs.put(userId, next);

            sessions.values().removeIf(
                    grant -> grant.userId().equals(userId));
            rememberMe.values().removeIf(
                    grant -> grant.userId().equals(userId));
            refreshTokens.values().removeIf(
                    grant -> grant.userId().equals(userId));
        }
    }

    public static void main(String[] args) {
        Store store = new Store();
        String user = "account-17";
        Instant now = Instant.parse("2026-01-01T00:00:00Z");

        // Giả lập một lần login ĐÃ được xác minh hợp lệ.
        store.issueSession("session-old", user);
        store.issueRememberMe("remember-old", user);
        store.issueRefresh("refresh-old", user);

        SimulatedJwt oldJwt =
                store.issueJwt(user, now.plusSeconds(3600));

        System.out.println("before-session="
                + store.sessionValid("session-old"));
        System.out.println("before-remember="
                + store.rememberMeValid("remember-old"));
        System.out.println("before-refresh="
                + store.refreshValid("refresh-old"));
        System.out.println("before-jwt="
                + store.jwtAllowed(oldJwt, true, now));

        // Trình tự thực tế bắt buộc:
        // xác minh quyền đổi -> ghi password mới -> commit -> revoke.
        store.afterVerifiedPasswordChange(user);

        System.out.println("after-session="
                + store.sessionValid("session-old"));
        System.out.println("after-remember="
                + store.rememberMeValid("remember-old"));
        System.out.println("after-refresh="
                + store.refreshValid("refresh-old"));

        // JWT cũ trong ví dụ vẫn chưa hết hạn, và giả định
        // signature đã được verify. Epoch mới làm request bị từ chối.
        System.out.println("old-jwt-still-not-expired="
                + now.isBefore(oldJwt.expiresAt()));
        System.out.println("after-jwt-with-epoch-check="
                + store.jwtAllowed(oldJwt, true, now));

        // Giả lập user xác thực lại bằng credential MỚI hợp lệ.
        store.issueSession("session-new", user);
        SimulatedJwt newJwt =
                store.issueJwt(user, now.plusSeconds(3600));

        System.out.println("new-session="
                + store.sessionValid("session-new"));
        System.out.println("new-jwt="
                + store.jwtAllowed(newJwt, true, now));
    }
}
```

### Chạy bằng javac/java thật

Với JDK 17+ và file có tên đúng `RevocationModelDemo.java`:

```bash
javac RevocationModelDemo.java
java RevocationModelDemo
```

**Stdout chính xác của ví dụ:**

```text
before-session=true
before-remember=true
before-refresh=true
before-jwt=true
after-session=false
after-remember=false
after-refresh=false
old-jwt-still-not-expired=true
after-jwt-with-epoch-check=false
new-session=true
new-jwt=true
```

Không có ngẫu nhiên/clock hệ thống trong logic; timestamp được cố định nên kết quả deterministic.

### Bài học từ kết quả

- Session, remember-me và refresh token cũ bị loại khỏi server-side store.
- JWT cũ vẫn **chưa hết hạn**, nhưng bị từ chối **nếu** resource server kiểm tra epoch sau khi xác minh token.
- User được xác minh lại có thể nhận session/JWT mới mang epoch mới.
- Việc giữ tham số `signatureAlreadyVerified=true` trong demo chỉ mô phỏng kết quả kiểm tra chữ ký bởi một JWT decoder thật. **Không sử dụng input boolean do client tự gửi để thay thế xác thực chữ ký.**
- `synchronized` và `HashMap` chỉ đủ minh họa trong một JVM. Production phải dùng nguồn có thẩm quyền/transaction/distributed cache, và thực hiện thêm password authentication, token hashing, expiry, crypto signing/verification và audit. Những chuỗi `session-old` không phải credential bí mật thật.

## 13. Ánh xạ ví dụ thành kiến trúc Spring Security

Trong ứng dụng thực, mỗi trách nhiệm nên nằm ở component thích hợp:

| Component | Trách nhiệm |
| --- | --- |
| `PasswordChangeService` | Kiểm tra người được quyền đổi, password cũ/reauth, policy mới; encode và commit |
| `AccountRepository` | Lưu password hash và security epoch theo account ID |
| `SecurityContextLogoutHandler` | Logout session hiện tại và clear authentication/context |
| `FindByIndexNameSessionRepository` | Tìm/xóa các session cũ ở kho Spring Session hỗ trợ index |
| `PersistentTokenRepository` | Xóa persistent remember-me token của user |
| `RefreshTokenService` hoặc issuer store | Revoke refresh token / token family |
| `AccessTokenRevocationPolicy` | Kiểm tra `jti`/epoch/introspection cho access token |
| `SecurityEpochAuthorizationFilter` hoặc domain policy | So epoch của principal/token đã xác minh với nguồn có thẩm quyền |
| Audit/outbox | Ghi sự kiện và phối hợp cleanup khi dùng nhiều dịch vụ |

Một thứ tự tích hợp dạng **mã phác thảo** (không phải file Java độc lập, các service là abstraction do ứng dụng định nghĩa):

```java
PasswordChangeResult result = passwordChangeService
        .changePasswordAndAdvanceEpoch(
                trustedAccountId, oldRawPassword, newRawPassword);

// Transaction cập nhật hash + epoch đã commit thành công.
// Các cleanup dưới đây cần retry/idempotency nếu ở kho khác:
sessionRevoker.revokeAll(result.accountId());
rememberMeRevoker.revokeAll(result.accountId());
refreshTokenRevoker.revokeAll(result.accountId());

securityContextLogoutHandler.logout(
        request, response, authentication);
```

**Không biến đoạn này thành lời hứa atomic cross-service:** sau commit epoch có thể có lỗi mạng khi xóa session/token vật lý. Nếu resource server/session filter kiểm tra epoch có thẩm quyền thì credential cũ vẫn có thể bị từ chối logic. Nếu không có gate này, phải có chính sách xử lý thất bại rõ (outbox, retry, cảnh báo, giới hạn trễ, fail closed cho hành động rủi ro cao).

### Trường hợp “giữ phiên hiện tại”

Nếu chính sách giữ thiết bị đang đổi password, cần cấp **phiên bản bảo mật mới chỉ cho phiên được xác minh đủ mạnh**, đồng thời invalidate các phiên khác. Không cập nhật epoch tất cả session trong store; làm vậy sẽ vô tình hồi sinh các phiên cần thu hồi. Cần đánh giá việc đổi session ID, cập nhật SecurityContext và CSRF token sau reauthentication, quyền trong session và yêu cầu step-up cho tác vụ nhạy cảm.

### Đừng để endpoint đổi mật khẩu thiếu CSRF protection

Ứng dụng form login + session/cookie thường cần CSRF token cho POST đổi mật khẩu. Việc đã có authenticated session **không ngăn** CSRF nếu trình duyệt tự gửi cookie. Giữ Spring Security CSRF protection phù hợp; không tắt toàn cục chỉ vì API test thiếu token.

Đối với reset password qua email, reset token phải được xác minh, giới hạn thời gian và chỉ dùng một lần. Không cho request reset được phép đặt arbitrary account ID hoặc token version để thu hồi/người dùng khác.

## 14. Khi dùng session version, đặt filter ở đâu?

Với cơ chế dựa vào SecurityContext, một filter kiểm tra epoch phải chạy **sau** khi authentication mechanism đã khôi phục/tạo `Authentication` cho request và **trước** khi controller hoặc authorization-sensitive business code chạy.

Ý tưởng logic:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication != null
        && authentication.isAuthenticated()
        && authentication.getPrincipal() instanceof VersionedPrincipal p) {

    long currentEpoch =
            accountSecurityService.currentEpoch(p.accountId());

    if (p.securityEpochAtAuthentication() != currentEpoch) {
        securityContextLogoutHandler.logout(
                request, response, authentication);
        response.setStatus(401);
        return;
    }
}

filterChain.doFilter(request, response);
```

Đây là **mảnh logic của filter**, không phải một lớp `OncePerRequestFilter` đầy đủ: `VersionedPrincipal`, `accountSecurityService`, request/response, filterChain và import phải được triển khai. Với anonymous hoặc các loại principal khác, cần **chính sách rõ**; đừng bỏ qua kiểm tra token chỉ vì nó không implement interface tự chế. Khi store epoch bị lỗi mạng, phải xác định fail closed hoặc bảo vệ đường nhạy cảm, không mặc định chấp nhận mọi token.

**Vị trí filter rất quan trọng.** Nếu đặt trước một remember-me filter có thể tự tạo `Authentication`, request remember-me sẽ chưa được kiểm tra. Một thiết kế có thể đặt filter trước `AuthorizationFilter` sau các filter authentication thích hợp, hoặc đưa check vào custom `AuthorizationManager`/policy. Hãy kiểm tra thứ tự filter thực tế bằng test framework; đừng suy luận bằng vị trí trong source file.

Cũng cần bảo đảm user đã thay đổi password không thể tạo **session mới từ password cũ** nhờ race giữa bước verify và bước cấp session. Principal/token phải mang epoch đã quan sát **trong lúc xác thực**, không lấy epoch mới sau đó rồi gắn cho một login đã kiểm tra hash cũ. Nếu nguồn account thay đổi trong lúc login, authentication cần kiểm tra tính nhất quán hoặc từ chối.

## 15. Tính nhất quán và thứ tự khi nhiều hệ thống cùng tham gia

Một ứng dụng nhiều node có thể dùng:

- RDBMS giữ password hash và security epoch.
- Redis/Spring Session giữ HTTP session.
- Database riêng chứa persistent remember-me.
- Authorization server giữ refresh tokens.
- Resource server xác minh JWT bằng key public.
- Queue/outbox phát sự kiện `PASSWORD_CHANGED`.

Nếu password đổi được commit ở DB nhưng queue/outbox có trễ, session/token cleanup có thể chưa xong. Chọn một mô hình:

**Mô hình A — Thu hồi vật lý đồng bộ:** mọi kho token/session phải xác nhận xóa trước khi báo hoàn tất. Khó duy trì atomicity giữa nhiều hệ thống; timeout/retry có thể làm response bị trễ hoặc thất bại từng phần.

**Mô hình B — Epoch có thẩm quyền + cleanup bất đồng bộ:** commit hash + epoch trong một transaction; mọi request bảo vệ dùng epoch có tính nhất quán phù hợp. Cleanup vật lý qua outbox/event có thể retry độc lập. Thường dễ chứng minh điều kiện từ chối truy cập hơn nếu mọi consumer thực thi gate.

**Mô hình C — TTL và độ trễ thu hồi được chấp nhận:** một số access token có thể tiếp tục dùng đến hạn ngắn; dùng khi yêu cầu sản phẩm cho phép. Phải ghi rõ độ trễ tối đa và không quảng bá là thu hồi ngay lập tức.

### Giao thức event thu hồi

Một event có thể chứa:

```json
{
  "type": "PASSWORD_CHANGED",
  "account_id": "account-17",
  "new_security_epoch": 7,
  "occurred_at": "2026-11-05T12:00:00Z",
  "event_id": "event-abcdef"
}
```

Đây là **mẫu event**, không phải quy ước bắt buộc. Không chứa password thô, password hash, refresh token hoặc remember-me cookie. Consumer phải kiểm tra nguồn event đáng tin, hỗ trợ retry/idempotency, và không áp một event **epoch thấp hơn** để hạ trạng thái của account. Timestamp minh họa không thay thế version có thẩm quyền.

### Xử lý lỗi thất bại từng phần

Giả sử commit password thành công nhưng xóa persistent token lỗi. Nếu epoch gate không được dùng cho remember-me, cookie có thể tiếp tục cấp authentication. Vì thế cần cảnh báo, retry và một phương án đóng đường nguy hiểm (chẳng hạn token store trả inactive trong lúc thay đổi trạng thái), thay vì im lặng báo “đã đăng xuất mọi thiết bị”.

Nếu credential change không commit, **không** phát sự kiện `PASSWORD_CHANGED` như thể đã thành công. Transactional outbox giúp gắn việc ghi event với commit ở cùng database; consumer bên ngoài vẫn phải xử lý at-least-once/idempotency.

## 16. Bộ ca kiểm thử phải chứng minh mất quyền thực sự

Không chỉ test status của endpoint đổi password. Nên giữ **cookie/token đã phát hành trước khi đổi** và thử lại chúng sau commit.

| Ca kiểm thử | Điều cần chứng minh |
| --- | --- |
| Password cũ sau đổi | Đăng nhập mới bằng password cũ bị từ chối |
| Password mới | Có thể đăng nhập mới theo policy, không khôi phục token cũ |
| Session trên thiết bị A | Bị invalidate hoặc được giữ nếu policy ghi rõ |
| Session trên thiết bị B | Không được truy cập protected resource sau revoke |
| Session còn trên node khác | Repository/epoch check từ chối nhất quán |
| Remember-me token-based | Cookie cũ không thể auto-login sau khi password hash thay đổi và cache đã refresh |
| Persistent remember-me | Token record bị xóa, cookie cũ không tạo session mới |
| Refresh token | Token/family cũ không xin access token mới |
| JWT access token | Vẫn có thể hợp lệ chữ ký/exp nhưng bị từ chối nếu policy đòi epoch/denylist |
| Opaque access token | Introspection/token store báo inactive theo thời điểm yêu cầu |
| Access token đang còn hạn nhưng không có revoke check | Phải ghi nhận TTL window, không tuyên bố revoke tức thì |
| SSO/IdP | Local logout và IdP logout/revoke được test như hai hệ khác nhau |
| Account khác | Session/token của user khác **không** bị thu hồi |
| Rehash kỹ thuật | Không tự logout nếu chính sách không định nghĩa rehash là credential change |
| Reset password đã xác minh | Revoke all đúng policy, reset token một lần |
| Change password không qua CSRF token | Request bị chặn khi dùng session-based browser |
| Hai request đổi password đồng thời | Không lost update, version tăng nhất quán |
| Login cũ đang diễn ra khi đổi password | Không phát session mang epoch mới dựa trên password cũ |
| Store revocation tạm lỗi | Có retry/fail closed/cảnh báo theo hợp đồng |
| Cache phiên bản cũ | Không làm hồi sinh session/token đã bị thu hồi |
| Request đã bắt đầu trước revoke | Kiểm tra chỗ cần reauthorization trong transaction nhạy cảm |

### Test hai trình duyệt thật

1. Mở browser A, đăng nhập và lưu session cookie A.
2. Mở browser B hoặc profile riêng, đăng nhập cùng account, lưu cookie B.
3. Nếu app có remember-me, bật ở B và giữ cookie đó khi session B bị xóa.
4. Ở A, đổi password theo luồng xác minh. Chọn chính sách logout-all.
5. Thử lại protected endpoint bằng cookie A và B, rồi thử auto-login từ remember-me cũ.
6. Nếu có OAuth2, thử refresh token cũ và access token cũ.
7. Đăng nhập lại bằng password **mới**; không chấp nhận password cũ.
8. Kiểm tra audit và metrics, không chỉ giao diện “Đổi mật khẩu thành công”.

Trong test session, đừng vô tình **đăng nhập lại** bằng HTTP Basic ở mỗi request vì Basic có thể tái xác thực credentials; nó không mô phỏng đúng một session cookie lâu dài. Form login/session-based client hoặc Spring Security MockMvc test phù hợp hơn.

### Phân biệt “401/403/redirect” với quyền truy cập thật

Form login có thể redirect tới `/login`, API Basic có thể trả 401, token resource server có thể trả `invalid_token`/401, còn authenticated user thiếu quyền nhận 403. Cần test rằng **protected operation bị từ chối**, không ép mọi cơ chế phải có cùng status/body. Không trả tên account/token state nhạy cảm ra endpoint công khai.

## 17. Lỗi thường gặp và hậu quả

| Sai lầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Chỉ update `password_hash` | Session/token cũ còn quyền | Lập kế hoạch revoke cho mọi credential liên quan |
| Gọi `HttpSession.invalidate()` rồi coi mọi thiết bị đã logout | Chỉ ảnh hưởng session hiện tại | Spring Session/session registry/epoch |
| Xóa `JSESSIONID` cookie mà không xóa server session | Cookie bị đánh cắp vẫn có thể dùng | Thu hồi trạng thái server |
| Xóa session nhưng quên remember-me | Cookie có thể tự đăng nhập lại | Revoke remember-me + clear cookie |
| Dựa vào đổi hash để xóa persistent remember-me | Token record vẫn còn | `removeUserTokens` |
| Revoke refresh token rồi coi JWT cũ đã chết | JWT đã phát hành có thể còn hạn | TTL/denylist/epoch |
| Chỉ logout local khi dùng OIDC | IdP session có thể còn | Phối hợp provider logout/revoke |
| Dùng `SessionRegistry` in-memory cho cluster | Không thấy session trên node khác | Indexed shared store / epoch |
| Dùng username mutable làm khóa revoke lâu dài | Sai phạm vi khi rename/tenant | Internal account ID, index phù hợp |
| Đặt epoch filter trước remember-me/auth filter | Token mới tạo trong request lọt qua | Kiểm tra filter order / policy |
| Gắn epoch mới cho login đã verify password cũ | Hồi sinh login cũ sau revoke | Ràng buộc epoch vào snapshot xác thực |
| Cache epoch không TTL/invalidations | Revoke bị trì hoãn | Consistency được xác định |
| Coi cleanup async là “ngay lập tức” | Cửa sổ truy cập trái phép | Authoritative gate hoặc báo rõ lag |
| Tăng epoch do mọi BCrypt rehash | Logout hàng loạt ngoài ý muốn | Tách security event theo ý nghĩa |
| Quên CSRF ở password change session endpoint | Password change qua cross-site request | Giữ CSRF protection |
| Ghi raw token/password vào audit event | Rò secrets | Log metadata tối thiểu |
| Tạo GET /change-password | Dễ bị kích hoạt ngoài ý muốn | Dùng POST/PATCH + kiểm soát CSRF |
| Quên reset token one-time | Replay reset password | Revoke sau khi dùng |
| Không test nhiều thiết bị | “Logout all” có thể không thật | Integration end-to-end |
| Không có fallback khi token store lỗi | Đăng xuất chỉ hoàn tất một phần | Fail closed/retry/alert theo policy |

## 18. Checklist thiết kế để bàn giao production

1. Xác định rõ sự kiện **password change** khác **hash rehash** tự động.
2. Quy định logout-current, logout-other-devices hay logout-all cho từng loại sự kiện.
3. Xác minh quyền thực hiện và password cũ/MFA theo mức rủi ro; reset token có TTL, single-use.
4. Encode password mới bằng encoder hiện hành; không lưu plaintext.
5. Update hash + security epoch atomically theo account ID bất biến.
6. Thiết kế xử lý concurrent change/reset; không để login cũ mint session mới mang epoch mới.
7. Nếu dùng Spring Session, xác minh principal index, shared repository, delete/invalidate và multi-node behavior.
8. Nếu dùng `SessionRegistry`, kiểm tra session registrations, principal equality và `ConcurrentSessionFilter`.
9. Với remember-me, phân biệt token-based và persistent; xóa đúng token records/cookie.
10. Revoke refresh token/token family và xác định chính sách với access token chưa hết hạn.
11. Nếu có JWT version check, validate issuer/audience/signature, đọc epoch tin cậy và xử lý outage.
12. Với OIDC/SSO, phối hợp IdP logout/revoke ngoài local session.
13. Không nhận user ID, token ID hoặc scope thu hồi tùy ý từ client chưa được kiểm chứng.
14. Giữ CSRF protection, cookie flags, HTTPS và chính sách CORS phù hợp.
15. Áp dụng audit/outbox/retry idempotent, telemetry revocation lag và alert khi lỗi.
16. Kiểm thử hai browser, nhiều node, token cũ, reset, simultaneous login/change và cache stale.
17. Không ghi password hash, bearer/refresh token, remember-me cookie hoặc session cookie vào logs.
18. Ghi rõ khoảng thời gian tối đa mà credential cũ có thể còn hiệu lực theo thiết kế và SLA.

## 19. Tự kiểm tra kiến thức

**Câu 1.** Đổi mật khẩu trong database có tự làm `JSESSIONID` của browser khác mất hiệu lực không?  
**Đáp án:** Không. HTTP session giữ `SecurityContext` riêng; cần invalidate/revoke session hoặc kiểm tra security epoch.

**Câu 2.** Gọi `SecurityContextLogoutHandler.logout(...)` trong request A có xóa mọi session ở thiết bị B không?  
**Đáp án:** Không. Handler mặc định xử lý ngữ cảnh và session của request hiện tại.

**Câu 3.** `SessionInformation.expireNow()` có giống xóa bản ghi session tức thì ở shared database không?  
**Đáp án:** Không. Nó đánh dấu session hết hạn trong registry; enforcement/cleanup theo filter và cơ chế quản lý phiên tương ứng.

**Câu 4.** Đổi password hash có tự xóa `persistent_logins` của Spring Security không?  
**Đáp án:** Không. Với persistent remember-me, cần `PersistentTokenRepository.removeUserTokens(username)` hoặc phương án thu hồi tương đương.

**Câu 5.** Vì sao token-based remember-me cookie có thể mất hiệu lực sau đổi password?  
**Đáp án:** Chữ ký gắn với password từ `UserDetails`; khi nguồn tải hash mới, chữ ký từ cookie cũ không còn khớp.

**Câu 6.** Nếu access token JWT đã ký chưa hết hạn thì đổi password có khiến chữ ký của nó sai không?  
**Đáp án:** Không. Muốn từ chối sớm, cần revocation policy như epoch, `jti` denylist hoặc introspection.

**Câu 7.** Thu hồi refresh token có luôn làm access token đã cấp mất hiệu lực ngay không?  
**Đáp án:** Không. Access token có vòng đời riêng; cần chính sách bổ sung.

**Câu 8.** Nếu hệ thống SSO có IdP session, local logout có bảo đảm IdP logout không?  
**Đáp án:** Không. Phải phối hợp với khả năng logout/revoke của IdP.

**Câu 9.** Vì sao dùng `credential_version` hữu ích cho logout-all?  
**Đáp án:** Token/session cũ mang version cũ, và resource server/authorization check có thể từ chối theo version hiện hành mà không phải liệt kê từng token.

**Câu 10.** Vì sao không nên nâng epoch trong mọi lần `upgradeEncoding` tự động?  
**Đáp án:** Rehash kỹ thuật không nhất thiết là thay credential do user; tăng epoch có thể gây logout hàng loạt ngoài ý muốn.

**Câu 11.** Có thể bảo đảm mọi request đã được cho phép trước đổi mật khẩu tự động bị hủy không?  
**Đáp án:** Không. Những request đang chạy có thể tiếp tục; thao tác nhạy cảm cần recheck ở boundary thích hợp.

**Câu 12.** Tại sao “xóa cookie” chưa chứng minh token bị thu hồi?  
**Đáp án:** Vì cookie ở thiết bị khác/đã bị sao chép vẫn tồn tại; server phải từ chối credential đó.

**Câu 13.** Khi password change service commit nhưng Redis session cleanup đang lỗi, có thể tuyên bố logout-all hoàn thành ngay không?  
**Đáp án:** Chỉ nếu một authoritative revocation gate đã bảo đảm các credential cũ không được chấp nhận. Nếu không, phải xử lý failure và độ trễ rõ ràng.

**Câu 14.** Có cần chống CSRF cho endpoint đổi mật khẩu khi app dùng session cookie không?  
**Đáp án:** Có, trong mô hình browser session-based cần bảo vệ tương ứng và không tắt chỉ vì test khó lấy token.

**Câu 15.** Khi nào được cấp một session/token mới sau khi đã thu hồi tất cả?  
**Đáp án:** Sau khi caller xác thực lại bằng credential mới hoặc cơ chế reauthentication được policy chấp nhận, và token/session mới mang epoch hiện hành.

## Kết luận

Thay password hash chỉ chặn khả năng tiếp tục xác minh password cũ; **không phải một thao tác thu hồi mọi credential thứ cấp**. Muốn bảo vệ tài khoản sau đổi/reset mật khẩu cần lựa chọn chính sách cho từng loại: logout session hiện tại và các session khác, làm vô hiệu remember-me, revoke refresh token/token family, và quyết định cách từ chối access token còn hạn.

Trong Spring Security, `SecurityContextLogoutHandler` giải quyết session hiện tại; Spring Session hoặc một registry/index phù hợp giúp quản lý các session khác; `PersistentTokenRepository.removeUserTokens` xử lý persistent remember-me; còn JWT/OAuth2 cần chính sách issuer/resource server riêng. Security epoch được cập nhật cùng password hash là một mô hình hữu ích để thu hồi logic khi cleanup vật lý ở nhiều hệ thống không thể hoàn tất atomically.

**Quy tắc nhớ:** *Đổi password để chặn password cũ. Thu hồi session, remember-me và token để chặn các quyền truy cập **đã được cấp trước đó**. Hai việc liên quan nhưng không phải một.*

### Tài liệu chính thức

- [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/rememberme.html)
- [Spring Security — PersistentTokenRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenRepository.html)
- [Spring Security — PersistentTokenBasedRememberMeServices API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenBasedRememberMeServices.html)
- [Spring Session — API: FindByIndexNameSessionRepository](https://docs.spring.io/spring-session/reference/api.html)
- [Spring Session — Redis: Finding Sessions of a Specific User](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Security — OAuth2 Authorization Server Core Model Components](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/core-model-components.html)
