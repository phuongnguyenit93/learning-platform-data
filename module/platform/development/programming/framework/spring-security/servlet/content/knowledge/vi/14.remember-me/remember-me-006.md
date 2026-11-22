# Remember-me, anonymous và fullyAuthenticated trong quyết định phân quyền (Spring Security Servlet)

## 1. Vì sao “đã xác thực” vẫn chưa chắc đủ quyền?

Trong một ứng dụng Spring Security Servlet, người dùng có thể có một `Authentication` ở những trạng thái tin cậy khác nhau:

- **Anonymous**: chưa đăng nhập theo nghĩa thông thường, nhưng framework có thể tạo `AnonymousAuthenticationToken` để biểu diễn danh tính anonymous trong request.
- **Remember-me**: browser có một remember-me cookie còn hiệu lực; khi session đăng nhập tương tác không còn, Spring Security có thể xác thực tự động và tạo `RememberMeAuthenticationToken`.
- **Fully authenticated**: người dùng đã xác thực bằng cơ chế được coi là đầy đủ theo `AuthenticationTrustResolver`, ví dụ form login với username/password, chứ **không phải chỉ thông qua remember-me**.

Ba loại này ảnh hưởng trực tiếp đến việc một đường dẫn được cho phép bởi:

```java
.requestMatchers("/account").authenticated()
.requestMatchers("/sensitive").fullyAuthenticated()
.requestMatchers("/guest").anonymous()
.requestMatchers("/remembered").rememberMe()
```

Đây là những **mảnh cấu hình** trong `authorizeHttpRequests`, không phải chương trình Java độc lập.

**Điểm mấu chốt:**

1. `authenticated()` thường chấp nhận cả người dùng đăng nhập tương tác và người dùng được xác thực bằng remember-me; nó loại anonymous.
2. `fullyAuthenticated()` chấp nhận xác thực “đầy đủ” nhưng **loại remember-me và anonymous**.
3. `rememberMe()` yêu cầu trạng thái được nhận diện là remember-me; người đăng nhập tương tác thông thường **không tự động thỏa** matcher chuyên biệt này.
4. `anonymous()` chỉ chấp nhận anonymous; nó không giống `permitAll()`.
5. `hasRole("ADMIN")` chỉ kiểm tra authority. **Không mặc nhiên bắt buộc fullyAuthenticated**. Với thao tác nhạy cảm, cần đánh giá cả độ tin cậy của authentication.

Bài này giải thích cơ chế, giới hạn an toàn, policy phân quyền và kiểm thử thực tế, không gộp “remember-me” với việc lưu session thông thường.

## 2. Phân biệt Authentication, session và remember-me cookie

`Authentication` là dữ liệu Spring Security dùng để biểu diễn principal, authorities và tình trạng xác thực của request. Trong hệ thống form login, sau khi đăng nhập thành công, `Authentication` thường được lưu trong `SecurityContext`; ngữ cảnh có thể được giữ trong `HttpSession` qua `SecurityContextRepository`.

**Remember-me** là một cơ chế khác: browser có thể giữ cookie lâu hơn session. Khi trình duyệt quay lại mà không có session chứa authentication, `RememberMeAuthenticationFilter` có thể gọi `RememberMeServices.autoLogin(...)` để xác minh cookie và đặt authentication loại remember-me.

```text
Browser
    |
    +-- Có HTTP session còn chứa SecurityContext?
    |      |
    |      +-- Có: sử dụng Authentication đã khôi phục
    |      |        (thường là full sau form login)
    |      |
    |      +-- Không: xem xét cơ chế remember-me (nếu bật)
    |                 |
    |                 +-- Cookie remember-me hợp lệ:
    |                 |      RememberMeAuthenticationToken
    |                 |
    |                 +-- Không có/không hợp lệ:
    |                        anonymous (nếu bật anonymous)
    |
    v
AuthorizationFilter
    |
    +-- authenticated / fullyAuthenticated / anonymous / rememberMe
    +-- hasRole / hasAuthority / authorization policy khác
    |
    v
Controller hoặc response từ chối/challenge/redirect
```

Sơ đồ là **mô hình khái niệm**: thời điểm filter chạy, cách repository đọc/lưu và success/failure handling còn phụ thuộc security chain và phiên bản. Không bảo đảm rằng mọi request có remember-me cookie đều được khôi phục thành remember-me: nếu một authentication khác đã có sẵn, remember-me auto-login thường không thay thế nó.

### 2.1. Cookie session và cookie remember-me khác nhau

| Thuộc tính | Cookie session (thường `JSESSIONID`) | Remember-me cookie (thường `remember-me`) |
| --- | --- | --- |
| Mục đích | Liên kết request với `HttpSession` ở server | Cho phép tự xác thực lại khi thiếu session đăng nhập |
| Có chứa password gốc? | Không nên | Không nên |
| Có phải `Authentication`? | Không | Không |
| Thời hạn | Theo session/cookie/container | Theo cấu hình remember-me và loại token |
| Tạo ra khi nào? | Có thể trước hoặc sau login | Thường khi đăng nhập thành công và người dùng chọn ghi nhớ |
| Quyền của request | Dựa vào SecurityContext và policy | Sau khi hợp lệ có thể sinh remember-me Authentication, vẫn cần authorization |
| Logout | Thường invalidate session | Thường yêu cầu xóa cookie; thu hồi phía server tùy loại remember-me |

Một remember-me cookie là credential có giá trị. **Không coi nó là “cookie tiện ích vô hại”**: nếu bị đánh cắp, nó có thể được phát lại tới lúc hết hạn hoặc bị vô hiệu hóa tùy thiết kế.

### 2.2. AnonymousAuthenticationToken không có nghĩa đã đăng nhập

Spring Security có thể đặt `AnonymousAuthenticationToken` trong `SecurityContextHolder` cho một request chưa đăng nhập. Token này giúp code xử lý nhất quán với một đối tượng authentication, nhưng không phải một user đã được xác minh.

Đặc biệt, `AnonymousAuthenticationToken.isAuthenticated()` có thể trả `true` theo API token, nên **không dùng duy nhất cờ `Authentication.isAuthenticated()`** để suy ra “người dùng thật đã đăng nhập”. Các authorization manager của Spring Security dùng `AuthenticationTrustResolver` để phân biệt.

Nếu ứng dụng tắt anonymous authentication hoặc dùng cơ chế custom, quan sát cụ thể có thể khác. Không hardcode giả định tất cả request không login đều luôn có một `AnonymousAuthenticationToken`.

## 3. AuthenticationTrustResolver và các cấp độ tin cậy

`AuthenticationTrustResolver` (thường `AuthenticationTrustResolverImpl`) cung cấp các phép phân loại authentication. Các phương thức quan trọng trong Spring Security 6 gồm:

```java
boolean isAnonymous(Authentication authentication);
boolean isRememberMe(Authentication authentication);
boolean isAuthenticated(Authentication authentication);
boolean isFullyAuthenticated(Authentication authentication);
```

Đây là **các chữ ký khái niệm của interface**, không phải định nghĩa trọn vẹn để copy thay thế thư viện.

Với các token chuẩn:

- `AnonymousAuthenticationToken` → anonymous.
- `RememberMeAuthenticationToken` → remember-me.
- `UsernamePasswordAuthenticationToken` đã được xác thực qua form login → được xem là fully authenticated, miễn không bị resolver phân loại là anonymous/remember-me.

Một ý tưởng so sánh dễ hiểu:

```text
isAuthenticated(authentication)
    ~ authentication tồn tại, isAuthenticated() true, KHÔNG anonymous

isFullyAuthenticated(authentication)
    ~ authenticated, KHÔNG remember-me
```

Ký hiệu `~` biểu diễn **logic khái niệm**, không phải mã nguồn chính xác theo mọi phiên bản hoặc resolver tùy biến. Chính framework là nguồn quyết định cuối cùng khi các `AuthorizationManager` áp dụng quy tắc.

### 3.1. “Fully authenticated” không đồng nghĩa MFA

Spring Security gọi “fully” trong bối cảnh trust resolver để **phân biệt remember-me với authentication khác**. Nó không tự chứng minh:

- người dùng đã làm MFA;
- người dùng vừa nhập lại mật khẩu trong 5 phút;
- thiết bị không bị đánh cắp;
- session hiện tại không bị chiếm quyền;
- các quyền trong `Authentication` còn đồng bộ với database;
- request đã đi qua “step-up authentication” cho giao dịch nhạy cảm.

Nếu nghiệp vụ yêu cầu MFA hoặc xác thực lại gần đây trước khi đổi email, chuyển tiền hay xem dữ liệu nhạy cảm, phải có **policy bổ sung về độ mới của xác thực và yếu tố xác thực**, không chỉ gọi `fullyAuthenticated()`.

### 3.2. Trust resolver không tự quyết định mọi authorization

Các biểu thức `authenticated`, `fullyAuthenticated`, `rememberMe`, `anonymous` là một phần của policy. Quyết định cuối cùng còn có thể phụ thuộc:

- authority/role;
- resource ownership, tenant và trạng thái account;
- method security hoặc business service policy;
- CSRF validation;
- matching filter chain;
- session/token validity;
- yêu cầu MFA và điều kiện rủi ro.

Không nên coi “fullyAuthenticated trả true” là quyền truy cập mặc định vào mọi tài nguyên.

## 4. Bảng quyết định: anonymous, remember-me và full login

Giả sử một security chain web có Spring Security anonymous + form login + remember-me chuẩn:

| Rule authorization | Anonymous | Remember-me hợp lệ | Form login đầy đủ |
| --- | --- | --- | --- |
| `permitAll()` | Cho phép | Cho phép | Cho phép |
| `denyAll()` | Từ chối | Từ chối | Từ chối |
| `anonymous()` | Cho phép | Từ chối | Từ chối |
| `rememberMe()` | Từ chối | Cho phép | Từ chối |
| `authenticated()` | Từ chối | Cho phép | Cho phép |
| `fullyAuthenticated()` | Từ chối | Từ chối | Cho phép |
| `hasRole("READER")` | Thường không có role này | Cho phép nếu remembered principal có `ROLE_READER` | Cho phép nếu full principal có `ROLE_READER` |

Bảng nói về **quyết định tại rule**. HTTP response cuối (401, 302 redirect hay 403) phụ thuộc authentication entry point, access denied handler và loại authentication hiện tại. Với form login:

- Anonymous truy cập `/account` cần xác thực → thường redirect `/login` (302).
- Remember-me truy cập `/sensitive` yêu cầu fully authenticated → có thể bị yêu cầu đăng nhập lại qua entry point để nâng cấp độ tin cậy.
- Full-login user truy cập một route `rememberMe()` chỉ dành riêng cho remember-me → bị từ chối theo rule, dù đã có xác thực mạnh hơn.

Điều cuối có vẻ ngược trực giác: `rememberMe()` không phải “ít nhất mức remember-me”. Nó là một **kiểm tra phân loại chính xác**. Nếu ý định là “chấp nhận cả remembered và full”, chọn `authenticated()` thay vì `rememberMe()`.

### 4.1. Chọn đúng rule theo yêu cầu sản phẩm

| Yêu cầu | Rule phù hợp |
| --- | --- |
| Trang giới thiệu, trợ giúp, home công khai | `permitAll()` |
| Chỉ người chưa đăng nhập xem trang khởi tạo onboarding | `anonymous()`, nếu sản phẩm thật sự muốn chặn người đã xác thực |
| Trang tài khoản cá nhân, cần danh tính đã nhận diện; remember-me được chấp nhận | `authenticated()` và kiểm tra quyền sở hữu dữ liệu |
| Trang “xác thực tự động bằng cookie” dành cho mục đích test/giải thích | `rememberMe()` |
| Đổi mật khẩu hoặc xác nhận thao tác nhạy cảm | Ít nhất `fullyAuthenticated()`, và có thể cần recent reauthentication/MFA |
| Xem dữ liệu quản trị | `hasRole("ADMIN")` **và** policy độ tin cậy phù hợp nếu nhạy cảm |
| Khóa hoàn toàn một endpoint | `denyAll()` |

Điều kiện authentication và điều kiện authority là **hai trục khác nhau**. Một admin đã được khôi phục bằng remember-me có thể vẫn mang `ROLE_ADMIN` trong authorities. Nếu endpoint admin chỉ kiểm tra `hasRole("ADMIN")`, đừng giả định rule đó yêu cầu full login.

## 5. Cơ chế RememberMeServices trong Servlet

Spring Security Servlet thường sử dụng các thành phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| `RememberMeServices` | Hợp đồng auto-login, login success và login fail |
| `RememberMeAuthenticationFilter` | Khi chưa có Authentication phù hợp, thử auto-login từ cookie |
| `TokenBasedRememberMeServices` | Remember-me dựa vào token được bảo vệ bằng chữ ký, không bắt buộc lưu token cho từng thiết bị trong database |
| `PersistentTokenBasedRememberMeServices` | Remember-me dựa trên chuỗi token lưu ở kho server, phục vụ quản lý token lâu dài |
| `PersistentTokenRepository` | Giao diện lưu/đọc/cập nhật/xóa persistent login tokens |
| `JdbcTokenRepositoryImpl` | Một implementation qua JDBC, cần schema tương ứng |
| `RememberMeAuthenticationToken` | Authentication được tạo khi auto-login remember-me thành công |
| `UserDetailsService` | Tra cứu người dùng và dữ liệu account khi dịch vụ remember-me cần đối chiếu |

Một luồng thông dụng:

```text
[1] Browser POST /login
    username/password + CSRF token + remember-me checkbox
       |
       +-- Xác thực sai:
       |      RememberMeServices.loginFail(...)
       |      (có thể xóa cookie remember-me cũ)
       |
       +-- Xác thực đúng:
              RememberMeServices.loginSuccess(...)
              có thể gửi Set-Cookie: remember-me=...
              Authentication từ form login là full

[2] Session đăng nhập mất/không được gửi
    Browser GET /account
    Cookie: remember-me=...
       |
       v
    RememberMeAuthenticationFilter
       |
       v
    RememberMeServices.autoLogin(...)
       |
       +-- không hợp lệ: không tạo remembered Authentication
       |
       +-- hợp lệ: RememberMeAuthenticationToken
                      |
                      v
               AuthorizationFilter
               authenticated() có thể cho qua
               fullyAuthenticated() sẽ không cho qua
```

**Không phải mọi remember-me cookie đều đủ điều kiện**: phải chưa hết hạn, đúng chữ ký hoặc khớp persistent token, user còn hợp lệ theo validation của dịch vụ và chính sách. Nếu account bị khóa hoặc password đổi, hành vi còn phụ thuộc dịch vụ/algorithm/configuration.

### 5.1. Cookie được đặt khi người dùng chọn remember-me

Với form login thông thường, request có tham số `remember-me` theo cấu hình; khi checkbox được chọn và login thành công, dịch vụ nhớ đăng nhập có thể gửi remember-me cookie.

Ví dụ form HTML (chỉ minh họa một phần nội dung form):

```html
<label>
  <input type="checkbox" name="remember-me" value="on">
  Ghi nhớ đăng nhập
</label>
```

Đây **không phải form đăng nhập hoàn chỉnh**: còn cần username, password, CSRF token, action và method phù hợp. Ví dụ chạy được ở phần 9 dùng trang login mặc định do Spring Security tạo, và test gửi tham số `remember-me` qua MockMvc.

Không nên bật remember-me mặc định cho mọi user mà không giải thích về nguy cơ khi thiết bị dùng chung.

### 5.2. Không có session không có nghĩa không có authentication

Một browser mất session login vẫn có thể gửi remember-me cookie. Hệ thống có thể tự tạo một `RememberMeAuthenticationToken` và cho phép `authenticated()`. Điều này đúng với thiết kế remember-me; nếu một khu vực nhạy cảm không được phép phục hồi bằng cookie, dùng `fullyAuthenticated()` hoặc cơ chế step-up.

Ngược lại, nếu session còn và chứa full Authentication, việc browser gửi thêm remember-me cookie thường không làm full Authentication tự biến thành remember-me. **Ưu tiên đường nạp authentication hiện tại** có ý nghĩa quan trọng cho test.

## 6. Token-based và persistent remember-me khác nhau như thế nào?

### 6.1. TokenBasedRememberMeServices

Token-based remember-me thường ký thông tin liên quan tới username, thời hạn, dữ liệu cần kiểm tra và secret key của ứng dụng. Tùy Spring Security version, format có thể có algorithm và những trường khác. Không phụ thuộc vào chuỗi cookie cụ thể trong application code.

Ưu điểm:

- Không nhất thiết cần bảng database cho từng remember-me token.
- Dễ trình diễn và triển khai với cấu hình ít thành phần.
- Cookie hết hạn theo policy và có thể không hợp lệ khi các dữ liệu dùng kiểm tra chữ ký thay đổi, ví dụ password hash.

Nhược điểm cần nhận thức:

- Nếu ai đó **đã sao chép một cookie hợp lệ**, chỉ xóa cookie phía browser sau logout thường **không tạo cơ chế thu hồi bản sao** đã bị đánh cắp.
- Thu hồi toàn bộ token có thể cần rotate secret key, đổi dữ liệu xác minh hoặc chiến lược khác; rotate key có thể ảnh hưởng nhiều người dùng.
- Khó quản lý từng thiết bị/token nếu không có state phía server.

**Không tuyên bố logout token-based remember-me đã thu hồi mọi bản sao cookie trên toàn mạng.**

### 6.2. PersistentTokenBasedRememberMeServices

Persistent-token implementation sử dụng kho server để lưu chuỗi token, thường có khái niệm **series** và **token**. Khi tự login thành công, token có thể được thay mới/luân chuyển. Một chuỗi token bị dùng sai có thể là dấu hiệu bị đánh cắp hoặc conflict.

Các khả năng hữu ích:

- Có thể quản lý token theo user/series ở backend.
- Có thể xóa token phía server để vô hiệu hóa một lần remember-me trong tương lai.
- Có thể thiết kế chức năng “đăng xuất tất cả thiết bị” nếu mapping và policy đầy đủ.

Nhưng cần:

- Schema/persistence phù hợp, ví dụ `persistent_logins` khi dùng JDBC implementation mặc định.
- Xử lý concurrency (hai request đồng thời cùng một cookie có thể tranh chấp token rotation).
- Transaction, consistency, audit, TTL cleanup và phân biệt token theft với race condition.
- Chính sách bảo vệ dữ liệu trong kho token.
- Quy trình thu hồi cả session hiện có nếu yêu cầu “đăng xuất mọi nơi”, vì xóa persistent token không tự hủy mọi session đã xác thực.

### 6.3. So sánh chiến lược

| Tiêu chí | Token-based | Persistent-token |
| --- | --- | --- |
| Lưu per-device token trong DB | Không bắt buộc | Có |
| Có server-side revocation theo token | Không có mặc định với token thuần stateless | Có thể triển khai bằng xóa/cập nhật token repository |
| Có thể phát hiện token bất thường | Hạn chế nếu chỉ dựa vào chữ ký | Có thể có cơ chế phát hiện misuse theo series/token |
| Chi phí vận hành | Ít state hơn | Cần storage, transaction và cleanup |
| Logout xóa browser cookie | Có thể | Có thể |
| Quản lý nhiều thiết bị | Khó hơn | Linh hoạt hơn nếu thiết kế mapping phù hợp |
| Mức độ xác thực sau auto-login | Remember-me | Remember-me |

Cả hai đều tạo xác thực **remember-me**, không tự biến thành full login sau khi session gốc biến mất.

## 7. Anonymous, remembered và fully authenticated có phải bậc thang quyền?

Có thể hình dung **mức độ tin cậy** theo thứ tự:

```text
Anonymous
   |
   | login / cookie hợp lệ
   v
Remember-me
   |
   | người dùng xác thực tương tác lại (ví dụ form login)
   v
Fully authenticated
```

Nhưng hình vẽ **không** diễn tả rằng khi đã ở bậc cao hơn thì mọi predicate của bậc thấp hơn đều đúng:

- `authenticated()` đúng với remember-me và full.
- `fullyAuthenticated()` chỉ đúng với full.
- `rememberMe()` thường chỉ đúng với remember-me, không đúng với full.
- `anonymous()` chỉ đúng với anonymous, không đúng với remembered hoặc full.
- `permitAll()` không quan tâm các trạng thái đó.

Đây là lý do cần tách hai ý: **độ tin cậy theo nghiệp vụ** và **predicate chính xác của framework**.

### 7.1. Một số trường hợp lạ nhưng hợp lý

**Trường hợp A:** Người dùng mở trang `/guest` chỉ dành anonymous sau khi đăng nhập đầy đủ. Họ bị từ chối dù xác thực mạnh hơn. Đây là kết quả đúng của `anonymous()`. Nếu trang phải hiển thị cho tất cả, dùng `permitAll()`.

**Trường hợp B:** Người dùng remembered mở `/account` được phép, nhưng mở `/sensitive` bị yêu cầu xác thực tương tác. Đó là mục tiêu của việc tách `authenticated` và `fullyAuthenticated`.

**Trường hợp C:** Người dùng full login mở `/remembered` thì bị từ chối, vì endpoint chỉ dành riêng cho remembered users. Trong sản phẩm thực, route chỉ dành remember-me rất hiếm khi cần; dùng nó chủ yếu để kiểm thử hoặc thiết kế UX rõ ràng.

**Trường hợp D:** Người dùng remembered có authority `ROLE_READER` mở `/reader`. Nếu rule chỉ `hasRole("READER")`, request có thể được phép. Muốn bắt full login tại khu vực nhạy cảm, policy phải kết hợp điều kiện full và role, không đoán quyền từ tên role.

## 8. Kết hợp authentication strength và quyền nghiệp vụ

Một cách mô hình hóa ranh giới:

```text
Decision = identity/trust conditions
         + authorities/roles
         + resource ownership/tenant
         + session/token/account state
         + step-up / recent MFA nếu cần
```

Đây là sơ đồ tư duy, không phải phương trình Spring Security tự tính bằng phép cộng. Các điều kiện có thể kết hợp bằng Spring Security `AuthorizationManager`, method security hoặc kiểm tra nghiệp vụ trong service.

### 8.1. hasRole không tự yêu cầu full

Ví dụ:

```java
// Mảnh rule — chỉ kiểm tra authority:
.requestMatchers("/admin").hasRole("ADMIN")
```

Nếu remembered Authentication mang `ROLE_ADMIN`, rule này tự thân không yêu cầu người đó nhập lại password. Khi route admin là nhạy cảm, nên thiết kế **role AND fully authenticated**, chẳng hạn bằng authorization manager kết hợp hoặc method security có biểu thức phù hợp, và kiểm thử đường remembered.

Không dùng mẹo đổi vai trò remembered thành ROLE_GUEST để ép chặn mọi tài nguyên nếu điều đó làm mất kiểm soát policy thật. Giữ authorities phản ánh domain, rồi áp dụng authentication trust ở nơi cần.

### 8.2. FullyAuthenticated vẫn không thay thế step-up MFA

Ngay cả khi `fullyAuthenticated()` đúng, tài khoản có thể đã đăng nhập từ lâu. Một giao dịch chuyển tiền hoặc thay đổi thông tin bảo mật có thể cần thêm authentication mới, challenge MFA, xác nhận giao dịch hoặc risk evaluation.

Những yêu cầu này phải có bằng chứng và timestamp/phương thức riêng. Không suy luận token type `UsernamePasswordAuthenticationToken` đủ để bảo đảm user vừa nhập mật khẩu.

### 8.3. Quyền riêng tư và remember-me trên máy công cộng

Nếu người dùng chọn remember-me trên thiết bị dùng chung, người khác có thể mở website sau khi session browser cũ mất mà vẫn được khôi phục thành remembered user. Vì thế việc chỉ cho phép những trang rủi ro thấp ở mức remembered và yêu cầu step-up cho dữ liệu nhạy cảm là ranh giới hữu ích.

Không thể tuyệt đối phân loại mọi trang “an toàn” hoặc “nhạy cảm” chỉ từ URL; cần threat model sản phẩm cụ thể và kiểm tra quyền sở hữu dữ liệu ở tầng service.

## 9. Ví dụ Spring Boot 3.3.5 / Java 17: bốn trạng thái phân quyền

Bài thực hành dùng **Servlet stack**, Maven, JDK 17 và Spring Security. Các endpoint:

| Route | Chính sách | Với anonymous | Với remembered | Với full login |
| --- | --- | --- | --- | --- |
| `GET /public` | `permitAll` | 200 | 200 | 200 |
| `GET /guest` | `anonymous` | 200 | Không được phép | Không được phép |
| `GET /account` | `authenticated` | Redirect login | 200 | 200 |
| `GET /remembered` | `rememberMe` | Không được phép | 200 | Không được phép |
| `GET /sensitive` | `fullyAuthenticated` | Redirect login | Yêu cầu login tương tác | 200 |
| `GET /reader` | `hasRole("READER")` | Không được phép | Có thể 200 nếu có authority | Có thể 200 nếu có authority |

Đây là **kỳ vọng với cấu hình cụ thể**; HTTP status chính xác khi bị từ chối phụ thuộc entry point và access denied handler, vì thế bảng dùng “không được phép” ở những vị trí phù hợp.

### 9.1. Cấu trúc dự án

```text
remember-me-auth-levels/
  pom.xml
  src/
    main/java/demo/remember/
      RememberMeDemoApplication.java
      SecurityConfig.java
      DemoController.java
    test/java/demo/remember/
      RememberMeAuthorizationTest.java
```

### 9.2. pom.xml

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
    <groupId>demo</groupId>
    <artifactId>remember-me-auth-levels</artifactId>
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

### 9.3. Lớp khởi động

File `src/main/java/demo/remember/RememberMeDemoApplication.java`:

```java
package demo.remember;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RememberMeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RememberMeDemoApplication.class, args);
    }
}
```

### 9.4. SecurityConfig: nhớ đăng nhập và các rule khác nhau

File `src/main/java/demo/remember/SecurityConfig.java`:

```java
package demo.remember;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
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
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("training-pass"))
            .roles("READER")
            .build();

        return new InMemoryUserDetailsManager(reader);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService users) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login", "/error").permitAll()
                .requestMatchers("/guest").anonymous()
                .requestMatchers("/account").authenticated()
                .requestMatchers("/remembered").rememberMe()
                .requestMatchers("/sensitive").fullyAuthenticated()
                .requestMatchers("/reader").hasRole("READER")
                .anyRequest().authenticated())
            .formLogin(form -> form.permitAll())
            .rememberMe(remember -> remember
                // Secret cố định CHỈ cho demo; production dùng secret bảo mật.
                .key("demo-only-remember-me-signing-key-change-me")
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(7 * 24 * 60 * 60)
                .userDetailsService(users))
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
```

**Giải thích:**

1. `UserDetailsService` cung cấp user và password hash BCrypt. Cơ chế login tương tác kiểm tra mật khẩu và xây dựng full Authentication theo luồng DAO thông thường.
2. `formLogin(form -> form.permitAll())` bật form login, bao gồm đường xử lý `POST /login`. `GET /login` dùng trang generated mặc định khi không tự chỉ định login page.
3. `rememberMe(...)` bật remember-me; cấu hình tên tham số checkbox, thời hạn token và service tra cứu user.
4. `key(...)` trong ví dụ là **secret demo**. Sản xuất phải lấy key mạnh, bí mật, cố định qua restart, phân phối phù hợp giữa các node và quản lý rotation. Không commit secret thật vào source code.
5. `rememberMe()` trong authorization **không phải** đoạn bật tính năng remember-me. Tính năng được bật bằng `http.rememberMe(...)`; predicate `rememberMe()` chỉ dùng để **quyết định truy cập**.
6. `requestMatchers("/reader").hasRole("READER")` cố ý minh họa rằng role check **không tự yêu cầu full**.
7. `anyRequest().authenticated()` là fallback; ứng dụng thật cần review cụ thể toàn bộ routes và nguyên tắc least privilege.
8. Web form login giữ **CSRF protection mặc định**. Chỉ dùng `POST /login` cùng CSRF hợp lệ trong test, không tắt CSRF để “làm test pass”.

**Không dùng mật khẩu và remember-me key demo trong sản xuất.** Cookie remember-me là credential nên cần HTTPS, cookie flags phù hợp và cách revoke theo threat model.

### 9.5. Controller để quan sát quyết định

File `src/main/java/demo/remember/DemoController.java`:

```java
package demo.remember;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/guest")
    String guestPage() {
        return "guest";
    }

    @GetMapping("/account")
    String account(Authentication authentication) {
        return "account:" + authentication.getName();
    }

    @GetMapping("/remembered")
    String remembered(Authentication authentication) {
        return "remembered:" + authentication.getName();
    }

    @GetMapping("/sensitive")
    String sensitive(Authentication authentication) {
        return "sensitive:" + authentication.getName();
    }

    @GetMapping("/reader")
    String reader(Authentication authentication) {
        return "reader:" + authentication.getName();
    }
}
```

Các method trả chuỗi đơn giản để kiểm tra authorization. Chúng **không tự nhận diện token class rồi quyết định quyền bằng if/else**; security filter chain đã đưa ra quyết định trước khi controller chạy.

### 9.6. MockMvc: kiểm chứng remember-me bằng cookie thật

File `src/test/java/demo/remember/RememberMeAuthorizationTest.java`:

```java
package demo.remember;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
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
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RememberMeAuthorizationTest {

    @Autowired
    MockMvc mvc;

    private MvcResult login(boolean remember) throws Exception {
        MockHttpServletRequestBuilder request = post("/login")
            .with(csrf())
            .param("username", "reader")
            .param("password", "training-pass");

        if (remember) {
            request.param("remember-me", "on");
        }

        return mvc.perform(request)
            .andExpect(status().is3xxRedirection())
            .andReturn();
    }

    private Cookie rememberCookie() throws Exception {
        Cookie cookie = login(true).getResponse().getCookie("remember-me");
        assertNotNull(cookie);
        return cookie;
    }

    @Test
    void anonymousCanVisitPublicAndGuest() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/guest"))
            .andExpect(status().isOk())
            .andExpect(content().string("guest"));
    }

    @Test
    void anonymousCannotVisitAuthenticatedAccount()
            throws Exception {
        MvcResult result = mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        assertNotNull(result.getResponse().getRedirectedUrl());
        assertTrue(result.getResponse().getRedirectedUrl()
            .contains("/login"));
    }

    @Test
    void interactiveLoginSatisfiesFullyAuthenticated()
            throws Exception {
        MvcResult result = login(false);
        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("account:reader"));

        mvc.perform(get("/sensitive").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("sensitive:reader"));
    }

    @Test
    void fullLoginDoesNotMatchRememberMeOnly() throws Exception {
        MvcResult result = login(false);
        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/remembered").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void rememberCookieAuthenticatesWithoutWebSession()
            throws Exception {
        Cookie cookie = rememberCookie();

        // Không truyền .session(...): tạo request mới chỉ có remember-me cookie.
        mvc.perform(get("/account").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("account:reader"));
    }

    @Test
    void rememberedOnlyRouteRecognizesRememberMe()
            throws Exception {
        Cookie cookie = rememberCookie();

        mvc.perform(get("/remembered").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("remembered:reader"));
    }

    @Test
    void rememberCookieIsNotFullyAuthenticated()
            throws Exception {
        Cookie cookie = rememberCookie();

        MvcResult result = mvc.perform(get("/sensitive")
                .cookie(cookie))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        assertNotNull(result.getResponse().getRedirectedUrl());
        assertTrue(result.getResponse().getRedirectedUrl()
            .contains("/login"));
    }

    @Test
    void rememberedUserCannotUseAnonymousOnlyPage()
            throws Exception {
        Cookie cookie = rememberCookie();

        int responseStatus = mvc.perform(get("/guest").cookie(cookie))
            .andReturn().getResponse().getStatus();

        assertNotEquals(200, responseStatus);
    }

    @Test
    void hasRoleAloneCanPermitRememberedPrincipal()
            throws Exception {
        Cookie cookie = rememberCookie();

        mvc.perform(get("/reader").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("reader:reader"));
    }

    @Test
    void wrongPasswordDoesNotGrantRememberMe()
            throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "reader")
                .param("password", "incorrect")
                .param("remember-me", "on"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        // Một số failure handlers có thể gửi cookie xóa token.
        Cookie cookie = result.getResponse().getCookie("remember-me");
        assertTrue(cookie == null || cookie.getMaxAge() == 0);
    }
}
```

Các test dùng request thật qua **Spring Security filter chain**, không dùng `.with(user(...))` hoặc tự dựng `RememberMeAuthenticationToken` để tuyên bố đã test cookie. Lệnh `.with(user(...))` sẽ đặt principal thử nghiệm và có thể bỏ qua chính cơ chế remember-me cần quan sát.

Quan trọng nhất là **`rememberCookie()`**: nó lấy cookie từ response của một `POST /login` thành công có checkbox, rồi gọi API ở request mới **không gửi session**. Lúc đó remember-me filter mới có cơ hội tự tạo RememberMeAuthenticationToken.

Test `hasRoleAloneCanPermitRememberedPrincipal` là **minh họa một điều phải chú ý khi thiết kế bảo mật**, không phải lời khuyên để dùng remember-me cho giao dịch có độ nhạy cảm cao.

### 9.7. Lệnh chạy và kết quả kỳ vọng

Từ thư mục dự án `remember-me-auth-levels`, dùng JDK 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

**Mười test dự kiến pass** với dependencies/cấu hình tương ứng. Đây là dự kiến dựa trên source, không phải kết quả đã chạy; không có stdout Maven cố định vì thời gian, version và hệ thống khác nhau.

Kết quả quan trọng:

| Tình huống | Dự kiến |
| --- | --- |
| Anonymous GET `/public` | 200 `public` |
| Anonymous GET `/guest` | 200 `guest` |
| Anonymous GET `/account` | Redirect login |
| Form login đầy đủ, GET `/sensitive` có session | 200 `sensitive:reader` |
| Form login đầy đủ, GET `/remembered` có session | 403 (không phải remember-me authentication) |
| Request không session nhưng có remember-me cookie, GET `/account` | 200 `account:reader` |
| Cùng remember-me cookie, GET `/remembered` | 200 `remembered:reader` |
| Cùng remember-me cookie, GET `/sensitive` | Redirect login vì cần full authentication |
| Remembered GET `/guest` | Không được phép |
| Remembered GET `/reader` | 200 nếu có `ROLE_READER` |
| Login sai password và chọn remember-me | Không có cookie mới hợp lệ |

**Không lưu hoặc in cookie remember-me lên log/test report công khai**. Nó có thể cho phép người khác xác thực như tài khoản chủ cookie.

## 10. Đoạn Java 17 độc lập: mô hình predicate xác thực

Spring Security dựa trên token classes và `AuthenticationTrustResolver`, không phải một enum như bên dưới. Tuy nhiên, mô hình Java 17 độc lập này giúp nhìn rõ kết quả Boolean của từng predicate.

Tạo `AuthenticationLevelsDemo.java`:

```java
public class AuthenticationLevelsDemo {

    enum Level {
        ANONYMOUS,
        REMEMBER_ME,
        FULL
    }

    static boolean authenticated(Level level) {
        return level != Level.ANONYMOUS;
    }

    static boolean fullyAuthenticated(Level level) {
        return level == Level.FULL;
    }

    static boolean rememberMe(Level level) {
        return level == Level.REMEMBER_ME;
    }

    static boolean anonymous(Level level) {
        return level == Level.ANONYMOUS;
    }

    public static void main(String[] args) {
        for (Level level : Level.values()) {
            System.out.printf(
                "%s authenticated=%s fully=%s rememberMe=%s anonymous=%s%n",
                level,
                authenticated(level),
                fullyAuthenticated(level),
                rememberMe(level),
                anonymous(level)
            );
        }
    }
}
```

Biên dịch và chạy:

```bash
javac AuthenticationLevelsDemo.java
java AuthenticationLevelsDemo
```

Stdout **chính xác** với Java 17:

```text
ANONYMOUS authenticated=false fully=false rememberMe=false anonymous=true
REMEMBER_ME authenticated=true fully=false rememberMe=true anonymous=false
FULL authenticated=true fully=true rememberMe=false anonymous=false
```

Đây là mô hình học tập: không tạo Spring `Authentication`, không xác thực credentials, không đọc cookie, không tính authority và không biểu diễn custom authentication resolver. Phần 9 kiểm thử behavior Servlet thực tế của Spring Security.

## 11. Vì sao nhớ đăng nhập có thể thành công dù session hết hạn?

Một vòng đời phổ biến:

```text
10:00 Form login thành công và chọn remember-me
       |
       +-- HttpSession đang chứa full Authentication
       +-- Browser có JSESSIONID
       +-- Browser có remember-me cookie
       |
12:00 HttpSession hết hạn do không hoạt động
       |
12:10 Browser GET /account
       |
       +-- Session cookie cũ không còn khôi phục Authentication
       +-- Remember-me cookie còn hợp lệ
       +-- RememberMeAuthenticationFilter autoLogin
       +-- RememberMeAuthenticationToken
       |
       +-- /account authenticated() --> có thể cho phép
       +-- /sensitive fullyAuthenticated() --> yêu cầu login tương tác
```

Thời gian trong sơ đồ là **giả định**, không phải một con số timeout mặc định. Việc session có hết hạn sau 2 giờ hay không phụ thuộc cấu hình Servlet session store; remember-me cookie có thời gian sống riêng.

### 11.1. Không được dựa vào “có remember-me cookie” để luôn cho phép

Cookie có thể:

- hết hạn;
- không đúng chữ ký/key;
- thuộc username không còn tồn tại;
- bị thu hồi trong persistent-token repository;
- không khớp dữ liệu mà implementation cần đối chiếu;
- không được gửi do Domain/Path/SameSite/Secure;
- bị xóa sau logout;
- bị browser chặn hoặc thay thế.

Chỉ khi remember-me services xác thực token thành công thì framework mới có Authentication phù hợp cho request. Đừng tự lấy giá trị cookie rồi tin username trong chuỗi đó.

### 11.2. Không mặc định nâng cấp quyền bằng cách chỉ redirect login

Redirect `/login` là cách đưa user tới bước xác thực tương tác khi cần. Nhưng bước “đã có full Authentication” sau login **chưa đảm bảo** thỏa yêu cầu MFA hoặc kiểm tra lại mật khẩu đủ mới. Với giao dịch nhạy cảm phải tích hợp step-up policy ở service/authorization layer.

## 12. Logout, thu hồi và đổi mật khẩu

### 12.1. Logout thường cần xử lý cả session lẫn remember-me

Một form logout chuẩn của Spring Security có thể invalidate session và thông qua `RememberMeServices.logout(...)` để xóa remember-me cookie ở browser. Tuy nhiên:

- **Xóa browser cookie** ngăn browser đó tiếp tục tự gửi token.
- **Thu hồi token phía server** có thể cần thiết với persistent-token remember-me.
- Nếu dùng token-based thuần có chữ ký, **một bản sao cookie đã bị đánh cắp** có thể vẫn hợp lệ khi secret key và dữ liệu xác minh vẫn chưa thay đổi, cho tới khi hết hạn.
- Logout trên một thiết bị không nhất thiết logout mọi thiết bị.
- Việc đổi password hash có thể làm token-based remember-me không còn khớp ở một số implementation; không suy rộng điều này sang mọi token hoặc session.

Trước khi quảng bá “logout all devices”, cần test cả session trong nhiều browser, remember-me tokens, các node và các token phụ/SSO.

### 12.2. Thu hồi remember-me không đồng nghĩa thu hồi HTTP session đang có

Một người có thể đã khôi phục remember-me thành Authentication và tiếp tục dùng session, tùy cấu hình. Việc xóa dòng persistent token trong DB không tự động invalidates tất cả session đã đăng nhập trước đó.

Muốn thu hồi toàn diện sau sự cố account compromise, nên quản lý riêng: session store/registry, remember-me token repository, bearer/refresh tokens, external SSO và các request đang chạy.

### 12.3. Cookie security

Trong sản xuất:

- Dùng **HTTPS**, đặt Secure/HttpOnly phù hợp; `SameSite` theo threat model, không coi SameSite là thay thế hoàn toàn CSRF.
- Không đặt remember-me token vào URL hoặc log.
- Không lưu raw token trong analytics event hoặc metric label.
- Hạn chế thời gian sống phù hợp mức rủi ro; nhớ đăng nhập nhiều tháng cần được xem xét về an ninh và trải nghiệm.
- Không sử dụng static signing key demo trong code thật; có secret management, key rotation strategy và phân phối nhất quán qua nodes.
- Với thiết bị dùng chung, trình bày rõ checkbox remember-me, cho phép người dùng bỏ chọn và thu hồi phiên/token.

### 12.4. CSRF với remember-me

Remember-me dựa trên cookie, browser có thể tự gửi cookie trên request. Vì vậy tác vụ POST/PUT/DELETE dựa vào cookie-authenticated request cần **CSRF protection phù hợp**, chứ không chỉ authentication.

Đặt `fullyAuthenticated()` cho route nhạy cảm có thể giảm một số rủi ro, nhưng **không thay thế kiểm soát CSRF**. CSRF và mức độ tin cậy của authentication giải quyết hai vấn đề khác nhau.

## 13. Các lỗi thường gặp khi quyết định phân quyền

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dựa vào `authentication.isAuthenticated()` để nhận biết user không anonymous | `AnonymousAuthenticationToken` có thể báo true | Dùng authorization rules/trust resolver đúng nghĩa |
| Cho rằng `authenticated()` luôn yêu cầu nhập mật khẩu hiện tại | Remember-me có thể được chấp nhận | Dùng `fullyAuthenticated()` cho ranh giới full login |
| Cho rằng `fullyAuthenticated()` chứng minh MFA đã thành công | Có thể cho phép session login cũ chưa MFA | Thêm step-up/recent authentication/MFA policy |
| Cho rằng `rememberMe()` chấp nhận full login “vì full mạnh hơn” | Full token không được phân loại remember-me | Dùng `authenticated()` nếu chấp nhận cả hai |
| Dùng `anonymous()` thay `permitAll()` cho trang public | Người đã login bị chặn khỏi trang công khai | Chọn `permitAll()` khi cần mọi người xem |
| Chỉ dùng `hasRole("ADMIN")` cho thao tác nhạy cảm | Remembered admin có thể giữ authority đủ quyền | Kết hợp authority và authentication trust/step-up |
| Lẫn `rememberMe` config với `rememberMe()` authorization rule | Bật cơ chế và kiểm tra quyền là hai nhiệm vụ khác nhau | Cấu hình remember-me ở `http.rememberMe(...)`, rule ở `authorizeHttpRequests` |
| Cho rằng JSESSIONID và remember-me là cùng một cookie | Sai thời hạn và cơ chế auto login | Phân biệt session state với remember-me credential |
| Test remembered bằng `.with(user(...))` | Test có thể không đi qua RememberMeAuthenticationFilter | Lấy cookie từ form login thật rồi gửi request mới không session |
| Chỉ kiểm tra status 200 của `/account` | Có thể không biết xác thực qua session hay remember-me | Thêm test cho `fullyAuthenticated` và `rememberMe` route |
| Xóa cookie và tuyên bố server đã revoke token bị sao chép | Token-based stateless có thể còn hợp lệ | Thiết kế revocation thực sự cho yêu cầu bảo mật |
| Cho rằng đổi mật khẩu luôn kill mọi active sessions | SecurityContext trong session có thể vẫn hợp lệ | Có policy revoke sessions riêng |
| Lưu remember-me key trong source code production | Lộ key có thể làm giả token hợp lệ | Dùng secret manager, key rotation và scopes phù hợp |
| Đặt remember-me cookie expiry quá dài không đánh giá risk | Tăng khoảng thời gian token bị lộ có thể bị lạm dụng | Chọn TTL theo threat model, hỗ trợ revoke |
| Tắt CSRF vì “đã có remember-me cookie” | Browser tự gửi cookie dẫn đến nguy cơ CSRF | Giữ CSRF cho thao tác state-changing có cookie authentication |
| Custom `Authentication` không được trust resolver phân loại phù hợp | Rule `fullyAuthenticated/rememberMe` có thể sai kỳ vọng | Test token class/trust resolver và policy |
| Hiểu login redirect 302 là “đăng nhập thất bại” | Remembered user có thể cần step-up | Phân biệt yêu cầu full authentication với bad password |

## 14. Debug một request bị chặn dù có remember-me cookie

Hãy đi theo từng bước:

1. **Đúng `SecurityFilterChain` chưa?** Nếu API stateless/Basic hoặc JWT chain không bật remember-me, cookie đó có thể bị bỏ qua theo thiết kế.
2. **Có session authentication nào đang tồn tại?** Nếu đã có full Authentication trong session, remember-me filter thường không tạo token mới.
3. **Request có gửi cookie remember-me không?** Kiểm tra cookie name, Path, Domain, Secure và SameSite; tránh log giá trị cookie.
4. **RememberMeServices nào được dùng?** `TokenBasedRememberMeServices` hay `PersistentTokenBasedRememberMeServices`, key/repository tương ứng?
5. **Token có hợp lệ không?** Kiểm tra TTL, key rotation, user state, password hash thay đổi hoặc persistent token repo, không in token.
6. **Principal có authorities nào?** Rule `hasRole` có thể chặn dù remember-me thành công.
7. **Policy route là gì?** `authenticated`, `fullyAuthenticated`, `rememberMe`, `anonymous` có nghĩa khác nhau.
8. **Nếu có redirect login**, có thể đơn giản là remembered principal không thỏa `fullyAuthenticated`, không nhất thiết cookie hỏng.
9. **Nếu response là 403**, kiểm tra authorization denied vs CSRF denied; không gộp mọi 403 thành sai quyền.
10. **Có custom AuthorizationManager/trust resolver không?** Xem nó phân loại RememberMeAuthenticationToken và AnonymousAuthenticationToken ra sao.
11. **Nếu logout xong mà cookie sao chép vẫn dùng được**, đó có thể là giới hạn của token-based strategy và thiếu server-side revocation.
12. **Nếu chỉ một số node nhận token**, kiểm tra key/repository/clock/config consistency qua cluster.

Ở môi trường phát triển, có thể bật:

```properties
logging.level.org.springframework.security=DEBUG
```

Không bật ghi raw `Authorization` header, password, remember-me cookie hoặc token vào logs. Tập trung vào chain, filter, route, kết quả authentication, status HTTP và trace ID.

## 15. Bài tập tình huống

**Câu 1.** Anonymous mở `/public`, route đặt `permitAll()`. Có cần tồn tại `Authentication` không?

**Đáp án:** Không yêu cầu người dùng phải đăng nhập. Một `AnonymousAuthenticationToken` có thể xuất hiện do anonymous filter, nhưng quyết định `permitAll` không đòi danh tính được xác minh.

**Câu 2.** Một người đăng nhập bằng form và chỉ có `ROLE_READER`. Khi session mất, remember-me cookie còn hợp lệ. Route `authenticated()` có cho phép họ vào `/account` không?

**Đáp án:** Có thể cho phép, vì RememberMeAuthenticationToken hợp lệ được tính là authenticated theo trust resolver; vẫn phải kiểm tra chính sách tài nguyên/authority khác nếu có.

**Câu 3.** Vì sao `fullyAuthenticated()` chặn một RememberMeAuthenticationToken dù `isAuthenticated()` của token là true?

**Đáp án:** Trust resolver phân biệt remember-me với full authentication. `fullyAuthenticated` cần authentication không phải anonymous và không phải remember-me.

**Câu 4.** Người vừa nhập đúng password và có full Authentication mở route `rememberMe()`. Có được phép không?

**Đáp án:** Không theo predicate remember-me chính xác: full token không được phân loại là RememberMeAuthenticationToken. Nếu muốn cả hai, dùng `authenticated()`.

**Câu 5.** Route `/admin` chỉ có `hasRole("ADMIN")`. Admin từng login và có cookie remember-me hợp lệ, session cũ đã mất. Họ có thể truy cập không?

**Đáp án:** Có thể, nếu remember-me Authentication mang authority `ROLE_ADMIN` và không có điều kiện khác. Với thao tác nhạy cảm cần kết hợp full/recent authentication hoặc MFA theo policy.

**Câu 6.** `fullyAuthenticated()` có tự buộc người dùng nhập MFA mới trong vòng 5 phút không?

**Đáp án:** Không. Nó loại anonymous và remember-me, nhưng không mã hóa yêu cầu về MFA hay thời gian xác thực gần nhất.

**Câu 7.** User logout, server gửi Set-Cookie xóa remember-me. Kẻ tấn công đã sao chép cookie token-based từ trước có chắc bị chặn không?

**Đáp án:** Không có bảo đảm nếu server không có revocation state và cookie ký còn hiệu lực. Cần threat model, chọn persistent-token/revocation hoặc giải pháp khác thích hợp.

**Câu 8.** User đã full login mở `/guest` có rule `anonymous()`, bị 403. Đó là bug không?

**Đáp án:** Không nhất thiết: rule chỉ cho anonymous. Nếu nội dung thật sự công khai, hãy đổi thành `permitAll()`.

**Câu 9.** Dùng `MockMvc .with(user("reader"))` để test `rememberMe()` có đủ không?

**Đáp án:** Không. Nó giả lập principal và có thể không tạo RememberMeAuthenticationToken từ cookie. Dùng form login thật, lấy remember-me cookie và gửi request mới không session.

**Câu 10.** App sử dụng cùng remember-me cookie ở môi trường staging và production với key khác nhau. Có nên cho rằng cookie hoạt động ở cả hai không?

**Đáp án:** Không. Chữ ký/key và phạm vi cookie quyết định tính hợp lệ; môi trường khác nhau cần tách secrets, domain và cấu hình.

## 16. Checklist áp dụng vào sản phẩm

### 16.1. Kiểm tra trước khi bật remember-me

- Có thật sự cần “ghi nhớ đăng nhập” không, hay session timeout đủ cho trải nghiệm?
- Người dùng có quyền chọn bật/tắt remember-me, và có cảnh báo trên thiết bị dùng chung không?
- Token-based hay persistent-token phù hợp yêu cầu thu hồi, multi-device và audit?
- Secret/key có được quản lý và xoay vòng đúng cách không?
- Cookie có Secure/HttpOnly/Path/Domain/SameSite hợp lý theo HTTPS/threat model?
- Login/remember-me có rate limiting và phát hiện abuse phù hợp không?
- Logout có xóa cookie và revoke server-side token khi cần không?
- Đổi mật khẩu, khóa tài khoản và logout-all có xử lý cả session hiện hành lẫn remember-me không?

### 16.2. Kiểm tra từng route trước release

- Đây là public (`permitAll`), anonymous-only, remembered-only, authenticated hay fullyAuthenticated?
- Nếu có role/authority, remembered principal có thể giữ những quyền nào?
- Route có chứa thông tin nhạy cảm hoặc thao tác có side effect cần full/recent authentication/MFA không?
- Có business ownership check, tenant check và method security khi cần không?
- Có xử lý CSRF cho request dùng cookie auth không?
- Nếu user remembered truy cập route full, UX có redirect đến form login/step-up hợp lý không?
- Có test full login **và** remember cookie không session cho cả các đường nhạy cảm và ít nhạy cảm?
- Có test anonymous, login sai và logout/expiration đúng kỳ vọng không?

### 16.3. Các quan sát khi vận hành

- Tách metric anonymous/remember-me/full cho điều tra an ninh nếu chính sách cho phép, không đưa token vào metric.
- Theo dõi tỉ lệ auto-login thất bại sau key rotation, thay user store, deploy hoặc clock drift.
- Giám sát login abuse, sử dụng token bất thường và các dấu hiệu account takeover.
- Đảm bảo số liệu không lộ thông tin xác thực/khách hàng nhạy cảm.

## 17. Ghi nhớ cốt lõi

- Remember-me là **cơ chế tự xác thực bằng cookie**, không chỉ là kéo dài HttpSession.
- `AnonymousAuthenticationToken` có thể tồn tại dù user chưa đăng nhập; đừng chỉ xem `Authentication.isAuthenticated()` để suy ra user thật.
- `AuthenticationTrustResolver` phân biệt anonymous, remember-me và fully authenticated; các authorization rules dựa vào phân loại đó.
- `authenticated()` nhận remember-me hoặc full; `fullyAuthenticated()` loại remember-me; `anonymous()` chỉ nhận anonymous; `rememberMe()` chỉ nhận remember-me; `permitAll()` nhận mọi trạng thái.
- Role/authority không tự chứng minh full login. Với thông tin hoặc hành động nhạy cảm, phối hợp điều kiện trust với authorization domain và step-up/MFA khi cần.
- Token-based và persistent-token remember-me có khả năng revoke khác nhau. Xóa cookie không tự bảo đảm bản sao token bị vô hiệu hóa.
- Kiểm thử xác thực tự động bằng **cookie thật từ form login**, gửi request mới **không session**, rồi so sánh `authenticated`, `fullyAuthenticated`, `rememberMe`, `anonymous` và `hasRole` trên các route.
