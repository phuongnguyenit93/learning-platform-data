# Xử lý tài khoản bị khóa, hết hạn hoặc bị vô hiệu hóa

## 1. Bối cảnh: vì sao trạng thái tài khoản quan trọng với Authorization Server?

Trong ứng dụng Spring Boot dùng **Spring Security** và **Spring Authorization Server** để cung cấp OAuth 2.0/OpenID Connect (OIDC), Authorization Server không chỉ kiểm tra mật khẩu hoặc phương thức xác thực khác. Trước khi cho người dùng hoàn tất đăng nhập và chấp thuận một yêu cầu ủy quyền, hệ thống còn phải quyết định **tài khoản có được phép hoạt động tại thời điểm đó hay không**.

Ví dụ: Alice đăng nhập vào Authorization Server để ứng dụng <code>orders-web</code> xin Authorization Code và access token cho Orders API. Alice nhập đúng mật khẩu nhưng tài khoản đang bị khóa vì hoạt động bất thường. Nếu hệ thống chỉ so khớp mật khẩu rồi phát hành authorization code, việc khóa tài khoản không đạt mục đích. Ngược lại, nếu Alice đã đăng nhập từ hôm qua rồi hôm nay bị vô hiệu hóa, việc chặn những lần đăng nhập mới **chưa chắc đã chặn phiên đăng nhập và token hiện có**.

Bài học này tập trung vào cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành quy trình xử lý **tài khoản bị khóa (locked), hết hạn (account expired), hết hạn thông tin đăng nhập (credentials expired) hoặc bị vô hiệu hóa (disabled)** trong Spring Security, cùng tác động của những trạng thái đó đến các luồng OAuth 2.0/OIDC.

Sau bài học, bạn cần có thể:

1. Phân biệt bốn trạng thái tài khoản mà <code>UserDetails</code> hỗ trợ, các exception tương ứng và thứ tự kiểm tra khi xác thực bằng <code>DaoAuthenticationProvider</code>.
2. Ánh xạ trạng thái nghiệp vụ từ database sang <code>UserDetails</code> mà không nhầm account expiration với credentials expiration.
3. Cấu hình đăng nhập tương tác của Authorization Server bằng <code>SecurityFilterChain</code>, hiểu khi nào request cần chuyển đến trang login.
4. Xử lý thay đổi trạng thái khi **người dùng đã có session, authorization code, access token hoặc refresh token**.
5. Thiết kế chính sách khóa/mở khóa, vô hiệu hóa, khôi phục và giám sát không làm lộ thông tin tài khoản.
6. Viết unit test và integration test cho các trạng thái, request OAuth/OIDC và thu hồi quyền truy cập.

## 2. Phân biệt bốn trạng thái trong Spring Security

### 2.1. Hợp đồng <code>UserDetails</code>

<code>UserDetails</code> biểu diễn một principal được hệ thống xác thực bằng username/password qua <code>UserDetailsService</code> và các provider tương ứng. Bốn phương thức dưới đây trả về **<code>true</code> khi điều kiện sử dụng tài khoản vẫn hợp lệ**:

| Phương thức | <code>false</code> nghĩa là gì? | Exception thường gặp khi dùng provider mặc định |
| --- | --- | --- |
| <code>isAccountNonLocked()</code> | Tài khoản đang bị khóa. | <code>LockedException</code> |
| <code>isAccountNonExpired()</code> | Tài khoản đã hết hạn. | <code>AccountExpiredException</code> |
| <code>isCredentialsNonExpired()</code> | Thông tin đăng nhập, như mật khẩu, đã hết hạn. | <code>CredentialsExpiredException</code> |
| <code>isEnabled()</code> | Tài khoản đã bị vô hiệu hóa. | <code>DisabledException</code> |

Điểm dễ sai là tên ba phương thức đầu mang nghĩa phủ định kép: <code>isAccountNonLocked() == false</code> mới biểu thị tài khoản bị khóa. Khi dùng builder của Spring Security, các setter như <code>accountLocked(true)</code>, <code>accountExpired(true)</code>, <code>credentialsExpired(true)</code> và <code>disabled(true)</code> lại diễn đạt trực tiếp trạng thái bất lợi.

### 2.2. Bốn trạng thái có mục đích nghiệp vụ khác nhau

| Trạng thái | Tình huống điển hình | Đường xử lý phù hợp |
| --- | --- | --- |
| **Locked** | Nhiều lần xác thực sai, nghi ngờ chiếm đoạt tài khoản hoặc nhân viên an ninh tạm khóa. | Không cấp phiên mới; giới hạn thử lại, điều tra hoặc mở khóa sau thời gian/chính sách. |
| **Account expired** | Tài khoản hợp đồng/thử nghiệm có ngày kết thúc hoặc quyền sử dụng đã hết hiệu lực. | Không cho đăng nhập bình thường; gia hạn qua quy trình có kiểm soát. |
| **Credentials expired** | Mật khẩu quá hạn, khóa xác thực cần xoay hoặc cần đặt lại credential. | Không hoàn tất đăng nhập tiêu chuẩn; chuyển tới quy trình thay credential được bảo vệ riêng. |
| **Disabled** | Quản trị viên vô hiệu hóa tài khoản, người dùng nghỉ việc, vi phạm chính sách hoặc tài khoản đang chờ kích hoạt. | Chặn sử dụng, xử lý thu hồi phiên/token và chỉ kích hoạt lại khi được phép. |

Không nên xem <code>locked</code>, <code>expired</code> và <code>disabled</code> là một cờ duy nhất. Một tài khoản có thể vừa bị khóa, vừa hết hạn; việc xử lý phục hồi, giám sát và kiểm toán vẫn cần phân biệt nguyên nhân.

**Lưu ý:** Các phương thức trên thuộc mô hình xác thực **End-User**. Chúng không phải trạng thái của <code>RegisteredClient</code> và không tự thay thế kiểm tra <code>client_secret</code>, <code>client_secret_expires_at</code> hay cơ chế client authentication của OAuth 2.0.

### 2.3. Thứ tự kiểm tra của <code>DaoAuthenticationProvider</code>

Với cách xác thực username/password thông thường, <code>DaoAuthenticationProvider</code> kế thừa luồng xử lý của <code>AbstractUserDetailsAuthenticationProvider</code>:

1. Tìm <code>UserDetails</code> qua <code>UserDetailsService</code>.
2. Thực hiện **pre-authentication checks**: tài khoản không bị khóa, đã được bật và chưa hết hạn.
3. Kiểm tra credential (ví dụ so sánh mật khẩu bằng <code>PasswordEncoder</code>).
4. Thực hiện **post-authentication checks**, trong đó kiểm tra credential chưa hết hạn.
5. Chỉ tạo kết quả <code>Authentication</code> thành công nếu toàn bộ điều kiện cần đều đạt.

Với implementation mặc định, pre-check thường xét **locked → disabled → account expired**; post-check xét **credentials expired**. Nếu một tài khoản có nhiều cờ bất lợi, exception nhìn thấy có thể phản ánh điều kiện được kiểm tra trước. Không dùng thứ tự exception như một chính sách ưu tiên nghiệp vụ lâu dài hoặc như toàn bộ nội dung trả về cho người dùng.

Đây là hành vi của **provider kiểu username/password có kiểm tra <code>UserDetails</code>**. Một custom <code>AuthenticationProvider</code>, đăng nhập qua hệ thống liên kết, pre-authenticated principal hay một cơ chế không dùng <code>DaoAuthenticationProvider</code> **không tự động** kế thừa tất cả bước kiểm tra này.

## 3. Mô hình trạng thái trong database

### 3.1. Không lưu bốn boolean mà bỏ qua nguyên nhân và thời điểm

Một mô hình người dùng thực tế có thể có:

| Trường dữ liệu | Ý nghĩa | Gợi ý |
| --- | --- | --- |
| <code>user_id</code> | Định danh bất biến của chủ thể. | Dùng định danh ổn định, đặc biệt trong hệ thống đa tenant. |
| <code>enabled</code> | Người dùng có được phép sử dụng tài khoản hay không. | Quản lý qua workflow kích hoạt/vô hiệu hóa. |
| <code>manually_locked</code> | Khóa thủ công vì lý do vận hành/bảo mật. | Cần reason, actor và audit. |
| <code>locked_until</code> | Mốc kết thúc khóa tạm thời. | So sánh bằng clock UTC đáng tin cậy. |
| <code>account_expires_at</code> | Thời điểm tài khoản hết hạn. | Không nhầm với tuổi mật khẩu/token. |
| <code>credentials_expires_at</code> | Thời điểm credential hết hạn. | Chính sách thay đổi mật khẩu/credential. |
| <code>failed_login_count</code> | Bộ đếm xác thực thất bại. | Cần xử lý đồng thời và cơ chế reset. |
| <code>status_reason</code>, <code>status_changed_at</code> | Lý do, thời điểm thay đổi. | Dùng cho hỗ trợ, kiểm toán và ứng phó sự cố. |

Đây là **gợi ý mô hình domain**, không phải schema do Spring Authorization Server tự tạo. Trong hệ thống thật, cần xác định rõ các mốc hết hạn có được xét tại thời điểm bằng mốc hay không; quy ước thường là <code>now >= expiresAt</code> nghĩa là đã hết hạn.

Tránh chỉ dùng <code>username</code> hoặc email làm khóa an toàn khi người dùng có thể đổi tên/email hay nhiều tenant có cùng login name. Nếu <code>principalName</code> của Authorization Server vẫn là username hiển thị, cần ánh xạ sang ID bất biến nhất quán khi phát hành token, thu hồi phiên và truy vấn quyền.

### 3.2. Ánh xạ dữ liệu nghiệp vụ sang <code>UserDetails</code>

Ví dụ dùng một repository domain do ứng dụng tự triển khai, với các getter tương ứng cho bản ghi tài khoản:

~~~java
@Configuration
class UserAccountAuthenticationConfig {

    @Bean
    Clock securityClock() {
        return Clock.systemUTC();
    }

    @Bean
    UserDetailsService userDetailsService(
            UserAccountRepository accounts,
            Clock securityClock) {

        return login -> {
            UserAccount account = accounts.findByLogin(login)
                .orElseThrow(() ->
                    new UsernameNotFoundException("Account not found"));

            Instant now = securityClock.instant();

            boolean locked =
                account.isManuallyLocked()
                || (account.getLockedUntil() != null
                    && now.isBefore(account.getLockedUntil()));

            boolean accountExpired =
                account.getAccountExpiresAt() != null
                && !now.isBefore(account.getAccountExpiresAt());

            boolean credentialsExpired =
                account.getCredentialsExpiresAt() != null
                && !now.isBefore(account.getCredentialsExpiresAt());

            return User.withUsername(account.getLogin())
                .password(account.getPasswordHash())
                // Demo: ứng dụng thực phải lấy roles/authorities từ policy.
                .authorities("ROLE_USER")
                .disabled(!account.isEnabled())
                .accountLocked(locked)
                .accountExpired(accountExpired)
                .credentialsExpired(credentialsExpired)
                .build();
        };
    }
}
~~~

Trong đoạn mã:

- <code>UserAccount</code>, <code>UserAccountRepository</code> và các getter là **kiểu domain minh họa**, không phải class do Spring Security cung cấp sẵn.
- <code>Clock</code> được inject để có thể kiểm thử đúng tại thời điểm trước/sau <code>locked_until</code> hoặc các ngày hết hạn.
- <code>locked_until == null</code> nghĩa là không có khóa theo thời gian; <code>manually_locked</code> có thể giữ khóa cho đến khi được thao tác thủ công.
- <code>passwordHash</code> phải phù hợp với <code>PasswordEncoder</code> của provider, chẳng hạn BCrypt/Argon2 được triển khai đúng. Không lưu mật khẩu gốc.
- Việc dùng authority <code>ROLE_USER</code> cố định chỉ minh họa; ứng dụng thực phải giải quyết role, tenant, scope và quyền theo mô hình riêng.

Khi thay đổi một trạng thái, yêu cầu đăng nhập **mới** thường được provider lấy từ nguồn dữ liệu tại thời điểm xác thực. Tuy nhiên, nếu sử dụng cache <code>UserDetails</code> hoặc session có principal đã được xác thực, trạng thái mới có thể **chưa** được áp dụng ngay. Đây là vấn đề vòng đời được xử lý ở phần 7.

### 3.3. Provider và password encoder

Spring Security sử dụng <code>UserDetailsService</code> cùng <code>DaoAuthenticationProvider</code> cho một thiết kế username/password điển hình. Có thể khai báo <code>PasswordEncoder</code>:

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
~~~

<code>DelegatingPasswordEncoder</code> sử dụng tiền tố như <code>{bcrypt}</code> để xác định cách xác minh hash đã lưu. Trong hệ thống thực cần thiết kế migration password hash, cơ chế tăng độ khó hash và bảo vệ credential. Không đặt <code>{noop}</code> hoặc mật khẩu plaintext trong dữ liệu sản xuất.

Nếu ứng dụng tự đăng ký <code>AuthenticationManager</code>, <code>AuthenticationProvider</code> hoặc dùng nhiều nguồn xác thực, hãy kiểm tra provider **thực sự được chọn** có thực hiện các bước trạng thái phù hợp. Không giả định chỉ cần bean <code>UserDetailsService</code> thì mọi phương thức login đều sẽ dùng nó.

## 4. Luồng đăng nhập của người dùng trong OAuth 2.0/OIDC

### 4.1. Chọn đúng security filter chain

Spring Authorization Server có các endpoint giao thức như <code>/oauth2/authorize</code>, <code>/oauth2/token</code> và những endpoint OIDC khi được bật. Trang đăng nhập dùng username/password thường thuộc **chain web riêng**, có form login và session phù hợp.

~~~java
@Configuration
@EnableWebSecurity
class SecurityChainsConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                server.oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .exceptionHandling(exceptions -> exceptions
                .defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)))
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurityFilterChain(
            HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đây là cấu hình **minh họa cho Spring Authorization Server với API Java DSL tương thích**; import và các bean nền tảng được lược bỏ. Dự án thực cần <code>RegisteredClientRepository</code>, authorization service, khóa/JWK, <code>JwtDecoder</code> khi dùng OIDC, nguồn người dùng, encoder và các thành phần cần thiết khác.

<code>@Order(1)</code> đặt chain Authorization Server trước; <code>getEndpointsMatcher()</code> bao phủ các endpoint mà configurer quản lý. Khi trình duyệt gửi authorization request mà chưa đăng nhập, entry point có thể chuyển sang <code>/login</code>, nơi chain web xử lý form. **Một request chỉ đi qua chain đầu tiên khớp**, không lần lượt đi qua cả hai.

Đoạn mã không tắt CSRF toàn ứng dụng. Request <code>POST /login</code> dựa trên cookie/session phải giữ kiểm soát CSRF phù hợp. Một lỗi credentials không phải lý do để mở công khai token endpoint hoặc tắt client authentication.

### 4.2. Đường đi khi tài khoản bị khóa

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser của Alice
    participant AS as Authorization Server endpoint
    participant W as Web login chain
    participant P as DaoAuthenticationProvider
    participant D as UserDetailsService/Database
    B->>AS: GET /oauth2/authorize (client_id, scope, state, PKCE)
    AS-->>B: Redirect /login nếu chưa có Authentication
    B->>W: POST /login + username/password + CSRF
    W->>P: UsernamePasswordAuthenticationToken
    P->>D: loadUserByUsername(alice)
    D-->>P: UserDetails: accountNonLocked=false
    P-->>W: LockedException
    W-->>B: Login failure, không tạo phiên thành công
    Note over W,AS: Không hoàn tất authorization code hoặc ID Token chỉ nhờ mật khẩu đúng
~~~

Trong <code>DaoAuthenticationProvider</code>, tài khoản bị khóa có thể bị từ chối **trước khi so sánh mật khẩu**, tùy thứ tự pre-check. Vì vậy không nên dựa vào câu “mật khẩu đúng nhưng locked” để suy ra thực tế password đã được kiểm tra trong cùng lần xử lý.

Với OAuth 2.0 Authorization Code/OIDC, người dùng chưa xác thực thành công sẽ không được hoàn tất các bước đòi hỏi End-User authentication. Màn hình login có thể chỉ hiển thị thông báo chung. Không ép mọi lỗi login thành OAuth <code>invalid_grant</code>: lỗi tài khoản thường xuất hiện ở bước tương tác với login, còn token endpoint có bộ lỗi giao thức riêng.

### 4.3. Luồng cho ba loại trạng thái còn lại

~~~mermaid
flowchart TD
    A["POST /login"] --> B["Tìm UserDetails"]
    B --> C{"Tài khoản đang locked?"}
    C -- Có --> X["LockedException"]
    C -- Không --> D{"enabled = true?"}
    D -- Không --> Y["DisabledException"]
    D -- Có --> E{"Account chưa hết hạn?"}
    E -- Không --> Z["AccountExpiredException"]
    E -- Có --> F{"Credential hợp lệ?"}
    F -- Không --> G["BadCredentialsException hoặc lỗi credential tương ứng"]
    F -- Có --> H{"Credential chưa hết hạn?"}
    H -- Không --> J["CredentialsExpiredException"]
    H -- Có --> K["Authentication thành công; tiếp tục policy OAuth/OIDC"]
~~~

Sơ đồ phản ánh **nhóm kiểm tra của provider username/password mặc định**, không phải cam kết thứ tự thực thi của mọi cơ chế xác thực. Khi dùng WebAuthn, LDAP, federation hoặc custom provider, phải bảo đảm chính sách trạng thái cũng được thực thi ở điểm xác thực tương ứng.

## 5. Xử lý lỗi xác thực an toàn và hữu ích

### 5.1. Exception, phản hồi giao diện và chính sách hiển thị

| Exception phía server | Điều kiện thường gặp | Thông tin trả cho người dùng |
| --- | --- | --- |
| <code>LockedException</code> | <code>isAccountNonLocked() == false</code> | Thông báo an toàn, đường khôi phục hoặc hỗ trợ; tránh tiết lộ chi tiết điều tra. |
| <code>DisabledException</code> | <code>isEnabled() == false</code> | Thông báo phù hợp chính sách; có thể hướng dẫn liên hệ hỗ trợ. |
| <code>AccountExpiredException</code> | <code>isAccountNonExpired() == false</code> | Quy trình gia hạn hoặc hỗ trợ theo tổ chức. |
| <code>CredentialsExpiredException</code> | <code>isCredentialsNonExpired() == false</code> | Quy trình thay credential được bảo vệ. |
| <code>BadCredentialsException</code> | Sai username/password hoặc được che giấu như vậy. | Lỗi đăng nhập chung, không xác nhận tài khoản có tồn tại. |
| <code>UsernameNotFoundException</code> | Không tìm được người dùng. | Thông thường không phân biệt công khai với sai credential. |

Spring Security thường che dấu lỗi username không tồn tại trong luồng <code>DaoAuthenticationProvider</code> bằng lỗi credential chung. Các exception trạng thái vẫn có thể được ghi nhận nội bộ. **Thông tin kỹ thuật chi tiết không nên tự động hiện ra ở public login page**, bởi kẻ tấn công có thể lợi dụng sự khác biệt để dò tài khoản, chính sách khóa hoặc thời gian tài khoản hết hạn.

Thiết kế khuyến nghị:

- **Bên ngoài:** thông báo chung như “Không thể đăng nhập. Kiểm tra thông tin hoặc sử dụng phương thức khôi phục tài khoản”, kèm hướng dẫn hỗ trợ khi phù hợp.
- **Bên trong:** lưu mã lỗi phân loại, ID tài khoản ổn định, request correlation ID và thời điểm; tuyệt đối không log password, mã MFA, authorization code, access token hoặc refresh token.
- **Kênh khôi phục đã xác minh danh tính:** có thể cung cấp hướng dẫn cụ thể hơn sau khi người dùng chứng minh quyền kiểm soát tài khoản.

Không cố định “mọi trạng thái phải trả HTTP 401” cho mọi endpoint. Form login thường trả **302 về trang login với chỉ dấu lỗi**, API trả JSON 401/403 theo cơ chế, còn OAuth 2.0/OIDC endpoint sử dụng response/error theo giao thức. Cần kiểm tra hành vi thực của từng chain.

### 5.2. <code>AuthenticationFailureHandler</code> cho form login

Một handler có thể thống nhất phản hồi trên giao diện:

~~~java
@Bean
AuthenticationFailureHandler safeLoginFailureHandler() {
    return (request, response, exception) -> {
        // Audit nội bộ có phân loại; không trả tên exception cho browser.
        response.sendRedirect(
            request.getContextPath() + "/login?error");
    };
}
~~~

Khi tự cấu hình handler, gắn nó vào chain web:

~~~java
http.formLogin(form -> form
    .failureHandler(safeLoginFailureHandler)
);
~~~

Đây là hai đoạn mã **cùng một ví dụ**; biến <code>safeLoginFailureHandler</code> trong đoạn thứ hai đại diện cho bean đã inject vào cấu hình, không phải tên biến local tự có. Ứng dụng cần chống open redirect, encoding URL đúng theo context path và kế hoạch thông báo UX. Đừng truyền <code>exception.getMessage()</code> ra query parameter hoặc nội dung HTML.

Tại backend, chỉ đếm **lỗi credential thực sự** cho chính sách failed-attempt counter. Không tăng counter do <code>LockedException</code>, <code>AccountExpiredException</code> hoặc sự cố hệ thống theo cách khiến tài khoản càng khó được phục hồi.

### 5.3. Audit và event xác thực

Spring Security có các authentication events như <code>AuthenticationFailureBadCredentialsEvent</code>, <code>AuthenticationFailureLockedEvent</code>, <code>AuthenticationFailureDisabledEvent</code> và những event cho account/credential expiration. Tùy thiết lập, bạn có thể dùng <code>DefaultAuthenticationEventPublisher</code> để phát event tương ứng với các <code>AuthenticationException</code> đã được cấu hình ánh xạ.

Event là nguồn tín hiệu hữu ích cho audit, cảnh báo và giám sát. Tuy nhiên, **đừng xây chính sách khóa chính chỉ dựa vào listener bất đồng bộ không bảo đảm thứ tự hoặc độ bền sự kiện**. Đối với giới hạn số lần thử, nguồn trạng thái phải hỗ trợ cập nhật an toàn khi nhiều request đồng thời, nhiều instance hoặc có retry.

## 6. Chính sách khóa, hết hạn và mở khóa

### 6.1. Khóa tạm thời sau nhiều lần xác thực sai

Ví dụ chính sách minh họa:

~~~text
Trong một cửa sổ thời gian:
  5 lần xác thực sai liên tiếp -> locked_until = now + 15 phút
  Những lần thử khi đang khóa -> từ chối, không phát session
  Sau mốc locked_until -> cho thử lại theo chính sách
  Đăng nhập thành công -> đặt lại bộ đếm thất bại nếu phù hợp
~~~

Các con số trên **chỉ là ví dụ**, không phải mặc định của Spring Security. Framework không tự động khóa tài khoản theo đúng ngưỡng này chỉ vì bạn sử dụng <code>DaoAuthenticationProvider</code>.

Điểm triển khai quan trọng:

1. **Chuẩn hóa định danh** theo chính sách (Unicode/case/tenant), nhưng không vô tình gộp hai account khác nhau.
2. Cập nhật <code>failed_login_count</code> và <code>locked_until</code> một cách **atomic/transactional** để các request đồng thời không làm mất lượt đếm.
3. Kết hợp **rate limiting theo IP/device/ASN/risk**, thay vì chỉ khóa account; kẻ tấn công có thể cố ý nhập sai để làm gián đoạn tài khoản của người khác.
4. Phân biệt tài khoản không tồn tại và sai mật khẩu trong telemetry nội bộ; giữ phản hồi công khai đủ đồng nhất để hạn chế user enumeration.
5. Chính sách mở khóa tự động chỉ áp dụng cho khóa có thời hạn; **không tự xóa khóa thủ công** do sự cố bảo mật.
6. Duy trì lịch sử lý do khóa, actor và thời điểm phục vụ kiểm toán.

Đối với hệ thống có MFA/WebAuthn, số lần xác thực sai ở từng yếu tố cần chính sách riêng. “Đúng mật khẩu” chưa đồng nghĩa đăng nhập thành công nếu còn bước xác thực bổ sung.

### 6.2. Account expiration

Account expiration nên được suy từ nguồn có thẩm quyền, ví dụ hợp đồng của nhân viên, thành viên tổ chức hoặc giới hạn tài khoản thử nghiệm. So sánh thời gian theo <code>Instant</code>/UTC thay vì lệ thuộc múi giờ trên máy ứng dụng. Khi gia hạn, cần xác định ai có quyền gia hạn, có cần phê duyệt hay không và khi nào trạng thái có hiệu lực trên các instance.

Không dùng <code>account_expires_at</code> để biểu diễn **ngày hết hạn access token**. Account là danh tính/chủ thể; <code>exp</code> trên JWT access/ID Token là thuộc tính của từng token cụ thể, có vòng đời riêng.

### 6.3. Credentials expiration

Khi password/credential hết hạn, <code>DaoAuthenticationProvider</code> có thể ném <code>CredentialsExpiredException</code> thay vì tạo <code>Authentication</code> thành công. Nếu ứng dụng cần luồng “Buộc đổi mật khẩu”, hãy thiết kế **đường phục hồi riêng**:

- Người dùng phải chứng minh danh tính theo cơ chế đã được phê duyệt, có thể bằng recovery challenge, MFA hoặc phiên giới hạn chức năng.
- Chỉ cấp quyền đổi credential trong giới hạn và thời gian phù hợp; không vì cần đổi mật khẩu mà cấp access token có đầy đủ scope.
- Mật khẩu mới phải qua chính sách độ mạnh, không tái sử dụng nếu có yêu cầu, lưu bằng password encoder an toàn.
- Sau khi đổi credential, cập nhật trạng thái, vô hiệu hóa recovery challenge và xử lý session/token cũ theo chính sách.

Không đưa một endpoint đổi mật khẩu không kiểm tra chủ sở hữu vào <code>permitAll()</code> chỉ vì tài khoản đang bị provider từ chối. Trạng thái credentials expired không chứng minh người đang gửi request là chủ tài khoản.

### 6.4. Disabled account

Vô hiệu hóa thường là quyết định quản trị hoặc lifecycle của tổ chức. Nên có thao tác backend với phân quyền mạnh, xác thực lại khi cần, ghi audit và cơ chế tránh người quản trị tự vô hiệu hóa nhầm toàn bộ tài khoản quản trị.

Khi bị disabled, tài khoản không được đăng nhập mới; nếu yêu cầu sản phẩm là **cắt quyền truy cập ngay**, còn cần xử lý session, refresh token và các access token đang lưu hành. Chỉ đặt <code>enabled=false</code> trong database không đủ để đạt yêu cầu tức thời đó.

## 7. Điểm khó nhất: tài khoản đổi trạng thái khi đã đăng nhập

### 7.1. Session hiện có không tự động đọc lại <code>UserDetails</code>

Sau lần form login thành công, <code>SecurityContext</code> có thể được lưu trong HTTP session. Ở request tiếp theo, Spring Security có thể khôi phục principal đã xác thực từ session mà **không gọi lại <code>UserDetailsService.loadUserByUsername()</code>**.

Do đó, khi quản trị viên đặt <code>enabled=false</code> hoặc khóa tài khoản:

~~~mermaid
flowchart TD
    A["User đã đăng nhập, có session"] --> B["Admin khóa/vô hiệu hóa account trong DB"]
    B --> C{"Có cơ chế làm hết hiệu lực session?"}
    C -- Không --> D["Session có thể tiếp tục chứa Authentication cũ"]
    C -- Có --> E["Invalidation / expiry / revalidation theo thiết kế"]
    D --> F{"Authorization endpoint có kiểm tra status hiện tại?"}
    F -- Không --> G["Nguy cơ tiếp tục cấp authorization mới"]
    F -- Có --> H["Từ chối khi status hiện tại không hợp lệ"]
    E --> H
~~~

<code>authorizeHttpRequests().anyRequest().authenticated()</code> chỉ xác nhận Authentication được xem là đã đăng nhập theo security context; nó **không bảo đảm tài khoản vẫn enabled trong database tại mọi request**.

Giải pháp tùy yêu cầu nhất quán và hạ tầng:

- **Vô hiệu hóa các session đang hoạt động:** dùng cơ chế session registry hoặc Spring Session với khả năng truy vấn session theo principal, cùng chính sách nhiều node.
- **Kiểm tra trạng thái tại các điểm phát hành authorization mới:** xác thực lại account status trước khi chấp nhận authorization request/consent và trước khi phát hành token khi yêu cầu.
- **Ngắn hạn hơn và phát hiện bất thường:** giới hạn tuổi session, yêu cầu reauthentication cho thao tác nhạy cảm, phát sự kiện trạng thái tới các node, cân bằng tải DB/cache.

Một session có thể bị đánh dấu “expire” rồi chỉ thực sự bị từ chối ở **request kế tiếp**; kết thúc session không xóa lập tức một access token đã phát hành. Khi sử dụng session registry, principal key phải ổn định và đồng nhất; ứng dụng nhiều node cần kho/session events phù hợp.

### 7.2. Authorization Code đã phát hành và token endpoint

Giả sử Alice đã được cấp authorization code rồi bị vô hiệu hóa **trước khi client đổi code lấy token**. Theo cấu hình thuần túy, token endpoint có thể xử lý code dựa vào authorization đã lưu và xác thực client, chứ không nhất thiết truy vấn lại tài khoản Alice.

Nếu chính sách yêu cầu chặn cấp token ngay sau khi khóa/vô hiệu hóa, cần đặt enforcement tại **những điểm cấp quyền và phát hành token**:

1. Khi xử lý authorization request cho người dùng đã có session.
2. Khi xử lý consent và cấp authorization code, nếu có khả năng trạng thái thay đổi trong luồng.
3. Khi đổi authorization code lấy token, nếu chính sách cần kiểm tra trạng thái End-User lúc đó.
4. Khi dùng refresh token để cấp access token mới.
5. Khi thực hiện token exchange hoặc grant mở rộng đại diện cho End-User (nếu hệ thống triển khai).

Đây là chính sách mà dự án phải thiết kế/tích hợp với các authentication provider, authorization service hoặc hook thích hợp của **phiên bản Spring Authorization Server đang chạy**. Không coi việc viết một <code>OAuth2TokenCustomizer&lt;JwtEncodingContext&gt;</code> là giải pháp đầy đủ: customizer có thể chỉ chạy đối với một loại token/định dạng nhất định và không tự hủy authorization/refresh token.

### 7.3. Refresh token vẫn có thể phát hành token mới

<code>refresh_token</code> grant dùng token đã phát hành trước đó cùng client authentication và chính sách của Authorization Server; nó **không phải một lần đăng nhập lại bằng mật khẩu của End-User**.

Vì vậy:

- Một tài khoản disabled **không đồng nghĩa** refresh token tự bị xóa.
- Một tài khoản locked **không bảo đảm** mọi yêu cầu refresh sẽ gọi lại <code>UserDetailsService</code>.
- Muốn chặn cấp token mới, cần **thu hồi refresh token/authorization liên quan** hoặc kiểm tra trạng thái End-User trong đường refresh theo chính sách.
- Với Client Credentials, access token đại diện **client/service**, thường không có End-User; không áp quy tắc disabled-user lên mọi <code>sub</code> mà thiếu phân biệt grant type.

<code>OAuth2AuthorizationService</code> lưu trạng thái authorization/token nhưng giao diện tiêu chuẩn **không có phương thức tổng quát “find all tokens by username and revoke all”**. Muốn thu hồi toàn bộ authorization của một người dùng cần thiết kế truy vấn phù hợp, thao tác đồng nhất và chiến lược xử lý race condition giữa refresh/revocation.

### 7.4. JWT access token đã phát hành

Resource Server xác minh JWT self-contained thường chỉ kiểm tra chữ ký, issuer, audience, thời hạn và quyền scope. Nếu JWT còn hạn, tài khoản Alice vừa bị disabled trong database của Authorization Server **không tự khiến JWT mất hiệu lực**.

| Cơ chế | Ảnh hưởng khi account bị disabled | Điều cần bổ sung nếu cần khóa truy cập sớm |
| --- | --- | --- |
| JWT access token, xác minh offline | Token còn hạn vẫn có thể được chấp nhận. | TTL ngắn, kiểm tra trạng thái tập trung hoặc denylist/revocation theo thiết kế. |
| Opaque/reference token với introspection | Introspection có thể kiểm tra trạng thái token tại server. | Bảo đảm trạng thái authorization/account được phản ánh vào <code>active</code> hoặc policy xác minh. |
| Refresh token | Có thể tiếp tục được sử dụng nếu còn hợp lệ. | Thu hồi refresh token và/hoặc kiểm tra account status khi refresh. |
| Session trình duyệt | Có thể còn Authentication cũ. | Session invalidation hoặc revalidation trên các request quan trọng. |
| Authorization mới | Có thể dựa vào session cũ nếu thiếu kiểm tra. | Re-check status trước khi cấp quyền/token phù hợp. |

Không hứa “disable tài khoản là ngắt quyền tức thì trên mọi API” nếu hệ thống chỉ dựa vào JWT xác minh offline và không có cơ chế kiểm tra trạng thái/thu hồi tức thời.

### 7.5. OIDC: ID Token, UserInfo và phiên đăng nhập

OIDC dùng ID Token để client biết về sự kiện xác thực End-User. Tài khoản bị disabled sau khi ID Token phát hành **không thể làm claim trong token cũ tự đổi**. Client có thể còn local session hoặc session tại bên thứ ba.

Cần phân biệt:

- **Authorization Server session**: phiên của người dùng tại nhà cung cấp định danh.
- **Relying Party (OIDC Client) session**: phiên mà ứng dụng client tự tạo sau khi nhận ID Token.
- **Access token/refresh token**: token OAuth có vòng đời riêng.

Việc logout ở Authorization Server, OIDC RP-Initiated Logout hay cơ chế front-channel/back-channel logout có thể giúp đồng bộ phiên **khi các bên thực sự hỗ trợ và cấu hình đúng**. Logout session không mặc nhiên thu hồi mọi access token, và chỉ đổi <code>enabled</code> không tự phát thông điệp logout đến mọi client.

## 8. Thiết kế nghiệp vụ thay đổi trạng thái tài khoản

### 8.1. Quy trình khóa hoặc vô hiệu hóa

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Admin/Security Policy
    participant S as Account Lifecycle Service
    participant DB as Account Database
    participant H as Session Manager
    participant T as Authorization/Token Store
    participant API as Resource Server
    A->>S: Khóa hoặc disable user-42 (reason)
    S->>S: Kiểm tra quyền, quyết định, idempotency
    S->>DB: Cập nhật status, version, audit
    DB-->>S: Thành công
    S->>H: Expire/invalidate phiên theo principal
    S->>T: Thu hồi authorization/refresh token theo chính sách
    S->>API: Phát tín hiệu hoặc cập nhật trạng thái từ chối nếu cần
    S-->>A: Kết quả + trạng thái các bước đã áp dụng
~~~

Sơ đồ là **thiết kế nghiệp vụ**; Spring Authorization Server không tự cung cấp một API sẵn “disable user rồi revoke mọi token ở mọi Resource Server”. Nếu các thành phần ở nhiều hệ thống, việc cập nhật database, session store, token store và denylist **không tự cùng một transaction**. Phải thiết kế retry, idempotency, audit, reconciliation và trạng thái lỗi một phần.

Với một policy bảo mật yêu cầu cắt quyền ngay, quy trình phải xác định thứ tự, ranh giới thời gian chấp nhận và hành vi fail closed. Ví dụ, trước khi báo “đã chặn toàn bộ truy cập”, phải biết các API đã nhận trạng thái khóa hay chưa hoặc còn JWT nào có thể dùng offline.

### 8.2. Phục hồi và mở khóa

Mở khóa không nên đồng nghĩa “khôi phục mọi refresh token và session cũ”:

1. Kiểm tra lý do khóa và điều kiện phục hồi (thời gian, xác minh danh tính, hỗ trợ, MFA, quản trị viên có quyền).
2. Cập nhật account status bằng thay đổi có audit; xác định có reset failed-attempt counter và credential flags không.
3. Nếu credential đã bị lộ, yêu cầu thay credential và thu hồi session/token cũ.
4. Yêu cầu đăng nhập mới khi cần; không tự cấp lại token bị thu hồi.
5. Kiểm tra consent OIDC/OAuth chỉ được tái sử dụng trong phạm vi còn hợp lệ; chính sách user/account hiện tại phải được áp dụng lại.

Một tài khoản có thể được mở khóa trong khi vẫn <code>disabled=true</code> hoặc đã hết hạn. Giao diện quản trị cần hiển thị **các điều kiện độc lập** để tránh “unlock” nhầm thành “fully active”.

### 8.3. State machine ở mức nghiệp vụ

Nên mô tả hành vi bằng **trạng thái tổng hợp** thay vì ép bốn cờ vào một enum duy nhất:

~~~text
ACTIVE:
  enabled=true
  manuallyLocked=false
  now >= lockedUntil (nếu có)
  now < accountExpiresAt (nếu có)
  now < credentialsExpiresAt (nếu có)

AUTHENTICATION_DENIED:
  disabled OR locked OR accountExpired OR credentialsExpired

RESTORED:
  Phải đánh giá lại tất cả điều kiện;
  không mặc nhiên khôi phục session/token đã thu hồi.
~~~

Các quy tắc trong block là ký hiệu khái niệm. Riêng <code>credentialsExpired</code>, một hệ thống có thể có **recovery session giới hạn** để đổi credential; việc này là một luồng bảo mật khác với session đăng nhập bình thường.

## 9. Tính nhất quán, cache và vận hành nhiều instance

Tài khoản có thể bị disable ở node A, trong khi node B giữ cached <code>UserDetails</code> hoặc security context cũ. Những lựa chọn triển khai cần được quyết định theo yêu cầu độ trễ chặn quyền:

| Cách triển khai | Điểm mạnh | Giới hạn |
| --- | --- | --- |
| Truy vấn trạng thái account tại mỗi authorization/refresh quan trọng | Đọc trạng thái mới từ nguồn tin cậy. | Tăng tải và độ trễ; cần xử lý lỗi DB. |
| Cache account status với TTL ngắn + invalidate theo sự kiện | Giảm tải, có thể phản ánh thay đổi nhanh. | Rủi ro cache/event không nhất quán; cần giới hạn khoảng stale. |
| Session registry/session store tập trung | Có thể expire nhiều phiên trên nhiều node. | Không tự xử lý token đã phát hành; cần principal index chính xác. |
| Reference token + introspection | Có điểm quyết định tập trung hơn JWT offline. | Tăng coupling, độ trễ và rủi ro hạ tầng introspection. |
| JWT ngắn hạn + chặn refresh | Đơn giản hơn cho nhiều API. | JWT đã phát hành vẫn có cửa sổ hợp lệ đến khi hết hạn. |

Khi database hoặc hệ thống policy không khả dụng, cần quyết định rõ **fail-open/fail-closed** theo tính chất endpoint. Đối với hành động nhạy cảm hoặc phát hành quyền mới, không nên âm thầm coi trạng thái “không biết” là active. Tuy nhiên, chiến lược fail closed phải đi kèm khả năng vận hành và giám sát để tránh sự cố diện rộng.

Thao tác khóa theo ngưỡng failed attempts và thao tác mở khóa cũng cần kiểm soát **race condition**. Ví dụ, hai lần xác thực sai đồng thời không được cùng đọc bộ đếm 3 rồi cùng ghi thành 4 khi kết quả đúng cần là 5; sử dụng atomic increment/optimistic lock hoặc transaction với khóa phù hợp.

## 10. Kiểm thử: từ <code>UserDetails</code> đến OAuth2/OIDC

### 10.1. Unit test mapping trạng thái theo thời gian

Kiểm thử <code>UserDetailsService</code> bằng clock cố định và repository giả lập để chứng minh:

| Dữ liệu domain | <code>UserDetails</code> mong đợi |
| --- | --- |
| <code>enabled=false</code> | <code>isEnabled()==false</code> |
| <code>manually_locked=true</code> | <code>isAccountNonLocked()==false</code> |
| <code>locked_until</code> ở tương lai | <code>isAccountNonLocked()==false</code> |
| <code>locked_until</code> đã qua, không khóa thủ công | <code>isAccountNonLocked()==true</code> |
| <code>account_expires_at <= now</code> | <code>isAccountNonExpired()==false</code> |
| <code>credentials_expires_at <= now</code> | <code>isCredentialsNonExpired()==false</code> |
| Không có hạn/khóa và enabled | Cả bốn điều kiện đều hợp lệ |

Nên có test biên **đúng thời điểm hết hạn**, test thời điểm vượt qua DST/múi giờ và test các tổ hợp cờ trạng thái. <code>Clock.fixed(...)</code> giúp các test không phụ thuộc thời gian máy chạy.

### 10.2. Unit test provider trả đúng exception

Giả sử test đã tạo một <code>AuthenticationManager</code> thực sự sử dụng <code>DaoAuthenticationProvider</code> với user <code>alice</code> có <code>accountLocked(true)</code>:

~~~java
@Test
void lockedAccountCannotAuthenticateWithCorrectPassword() {
    assertThatThrownBy(() -> authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            "alice", "correct-password")))
        .isInstanceOf(LockedException.class);
}
~~~

Test ở mức provider cần dùng <code>PasswordEncoder</code> đúng với password hash và nên lặp lại với <code>DisabledException</code>, <code>AccountExpiredException</code>, <code>CredentialsExpiredException</code>. Không sử dụng mock <code>Authentication</code> được đánh dấu <code>authenticated=true</code> làm bằng chứng rằng provider đã kiểm tra account status.

### 10.3. Integration test form login

Với cấu hình Spring Security mặc định sử dụng trang <code>/login</code> và <code>failureUrl</code> mặc định, có thể kiểm tra request không thành công:

~~~java
@Test
void disabledAccountCannotCreateLoginSession() throws Exception {
    mockMvc.perform(post("/login")
            .with(csrf())
            .param("username", "alice")
            .param("password", "correct-password"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/login?error"));
}
~~~

Đây là **ví dụ theo default formLogin**; nếu dự án dùng custom login page/failure handler, hãy kiểm tra URL hoặc kiểu response tương ứng. Test còn phải xác nhận **không tạo Authentication thành công** và không hoàn tất yêu cầu <code>/oauth2/authorize</code> đang chờ. Chỉ kiểm tra redirect URL mà không kiểm tra security state là chưa đủ.

### 10.4. Ma trận integration test toàn luồng

| Tình huống | Kỳ vọng |
| --- | --- |
| Alice active, đúng credential | Đăng nhập thành công; authorization request tiếp tục theo grant, scope và consent. |
| Alice locked, đúng credential | Không tạo phiên login thành công; không hoàn tất authorization mới. |
| Alice disabled, đúng credential | Từ chối như chính sách; audit nguyên nhân ở backend. |
| Account expired | Không đăng nhập thường; chỉ đi qua quy trình gia hạn được phép. |
| Credentials expired | Không phát phiên/toàn bộ token như tài khoản active; có recovery flow an toàn nếu thiết kế. |
| Sai mật khẩu liên tiếp đến ngưỡng | Bộ đếm và khóa cập nhật đúng, không mất lượt khi đồng thời. |
| Khóa tạm thời đã hết hạn | Kiểm tra theo clock; vẫn từ chối nếu disabled/expired. |
| Một tài khoản bị khóa và disabled cùng lúc | Không thể bypass bằng thao tác mở khóa một cờ duy nhất. |
| Đang có browser session rồi bị disabled | Session bị expire/revalidate theo SLA; không tạo authorization mới. |
| Bị disabled sau khi đã cấp authorization code | Token exchange bị từ chối nếu policy yêu cầu kiểm tra End-User hiện tại. |
| Có refresh token trước khi bị disabled | Không cấp access token mới nếu policy yêu cầu khóa ngay; kiểm tra revocation. |
| Có JWT access token trước khi bị disabled | Xác nhận chính xác hành vi Resource Server theo chiến lược revoke/TTL. |
| Hai instance dùng chung account và session store | Trạng thái được đồng bộ trong giới hạn nhất quán đã định. |
| Client Credentials của service không có End-User | Không nhầm trạng thái tài khoản người dùng với xác thực client. |
| Người dùng thuộc tenant A, user trùng tên ở tenant B | Khóa ở tenant A không vô tình khóa nhầm tenant B. |
| Đã mở khóa nhưng credentials expired | Vẫn phải xử lý expiry credential, không auto grant. |

Đối với OAuth2/OIDC, nên có integration test thực sự đi qua authorization endpoint, login handler, client registration, authorization service và token endpoint. Kiểm tra response giao thức, session, token issuance và quyền ở Resource Server; các unit test <code>UserDetails</code> đơn lẻ không chứng minh những điểm phát hành token đã áp dụng trạng thái mới.

## 11. Lỗi thiết kế thường gặp

### Lỗi 1: So sánh mật khẩu trước rồi mới xem trạng thái

Tự viết logic <code>if (passwordMatches) authenticated = true</code> mà không kiểm tra <code>enabled</code>, <code>locked</code>, <code>accountExpired</code>, <code>credentialsExpired</code> có thể cho người dùng bị chặn đăng nhập. Tái sử dụng provider an toàn của Spring Security khi có thể; nếu dùng custom provider thì phải kiểm tra trạng thái và policy tương đương.

### Lỗi 2: Hiểu ngược boolean

Đặt <code>accountNonLocked=false</code> cho tài khoản đang active hoặc đặt <code>disabled=false</code> khi thực ra admin đã vô hiệu hóa làm sai hành vi. Viết test biên cho cả bốn cờ và đặt tên field domain rõ nghĩa.

### Lỗi 3: Cho rằng <code>isEnabled=false</code> thu hồi mọi token

<code>isEnabled()</code> được provider kiểm tra khi chạy quy trình username/password tương ứng. Nó không tự xóa session hiện tại, authorization đã cấp hay JWT access token. Phải bổ sung chính sách session/token lifecycle ở điểm thích hợp.

### Lỗi 4: Chỉ bảo vệ <code>/login</code> mà bỏ qua <code>/oauth2/authorize</code>

Khi người dùng có session cũ, họ có thể không đi qua login lần nữa. Nếu hệ thống đòi hỏi chặn cấp authorization ngay sau khi account disabled, phải revalidate tại authorization flow và xử lý các session cũ.

### Lỗi 5: Refresh token bỏ qua trạng thái tài khoản

Refresh grant thường không nhập lại mật khẩu; nếu chỉ kiểm tra account trong login provider, hệ thống có thể tiếp tục cấp access token mới sau khi disable. Hãy có revocation và/hoặc status validation trong đường refresh.

### Lỗi 6: Trả rõ “tài khoản này tồn tại nhưng đã khóa” cho mọi caller

Phản hồi quá chi tiết, timing khác biệt, thông báo khác nhau theo username có thể giúp user enumeration. Ghi trạng thái chính xác ở backend và dùng recovery flow đã xác minh để cung cấp thông tin cần thiết.

### Lỗi 7: Khóa sau N lần sai nhưng chỉ dùng biến trong RAM

Một counter in-memory đơn giản không nhất quán khi có nhiều instance, mất khi restart và không an toàn trước concurrency. Sử dụng storage/atomic operation phù hợp cùng rate limiting và policy chống DoS.

### Lỗi 8: Cho phép đặt lại credential qua endpoint công khai thiếu challenge

Tài khoản có credentials expired không chứng minh request đổi mật khẩu là hợp lệ. Phải xác minh quyền kiểm soát tài khoản, ràng buộc reset token/challenge với người dùng, hết hạn và dùng một lần.

### Lỗi 9: Nhầm user với OAuth client

Trạng thái <code>UserDetails.enabled</code> và tình trạng secret của <code>RegisteredClient</code> là hai đường xác thực khác nhau. Một máy batch có <code>client_credentials</code> có thể không có End-User; phải kiểm tra client registration, method, grant và scope riêng.

## 12. Checklist thiết kế trước khi đưa vào production

| Lĩnh vực | Câu hỏi cần trả lời |
| --- | --- |
| Chính sách trạng thái | Locked/disabled/accountExpired/credentialsExpired có được định nghĩa và ưu tiên rõ? |
| Dữ liệu | Có actor, lý do, mốc thời gian, tenant, ID bất biến, version và audit? |
| Provider | Mọi loại đăng nhập có thực sự kiểm tra trạng thái theo policy? |
| Form login | Có CSRF, session fixation protection, timeout và failure handler an toàn? |
| Session đang hoạt động | Khi disable, session cũ bị expire/revalidate trên mọi instance như thế nào? |
| Authorization mới | Tài khoản disabled/locked có còn tạo authorization code khi có session cũ không? |
| Token/refresh | Có xử lý refresh token, authorization đã lưu và JWT access token hiện có? |
| SLA thu hồi | Có công bố thời gian tối đa token bị ngắt và test ở Resource Server? |
| Khôi phục | Có phân quyền quản trị, recovery challenge, MFA và xử lý reset credential? |
| Chống abuse | Có rate limit, counter atomic, lockout policy không dễ gây DoS? |
| Quan sát | Có audit theo ID ổn định và log đã ẩn dữ liệu nhạy cảm? |
| Kiểm thử | Có test status flags, provider exception, request OAuth, refresh, session và nhiều node? |

## 13. Bài tập ứng dụng

Bạn cần vận hành Authorization Server dùng chung cho ứng dụng <code>sales-portal</code> và <code>reporting-ui</code>. Người dùng có thể đăng nhập qua form, được cấp Authorization Code và OIDC ID Token. Hệ thống lưu account ở PostgreSQL, authorization/refresh token ở kho riêng, còn Resource Server xác minh JWT access token offline.

1. Thiết kế bảng account có <code>enabled</code>, <code>manually_locked</code>, <code>locked_until</code>, <code>account_expires_at</code>, <code>credentials_expires_at</code>, các trường audit và khóa định danh ổn định.
2. Viết <code>UserDetailsService</code> ánh xạ đúng bốn phương thức <code>UserDetails</code>. Dùng <code>Clock.fixed(...)</code> để kiểm thử thời điểm trước, đúng và sau <code>locked_until</code>.
3. Khi Bob nhập sai mật khẩu năm lần trong một phút, đề xuất chính sách counter atomic, rate limit và cách chống kẻ tấn công cố ý khóa tài khoản Bob.
4. Bob đăng nhập thành công hôm qua nhưng hôm nay bị disable. Vẽ đường đi của <code>GET /oauth2/authorize</code> khi session vẫn tồn tại và đề xuất điểm revalidation.
5. Bob đã có refresh token. Giải thích vì sao chỉ đặt <code>enabled=false</code> không đủ và chọn chiến lược chặn refresh/thu hồi authorization.
6. Orders API chỉ kiểm tra JWT offline. Xác định khoảng thời gian token cũ vẫn có thể hợp lệ và đề xuất giải pháp nếu cần chặn truy cập trong vòng vài giây.
7. Thiết kế luồng reset mật khẩu cho <code>CredentialsExpiredException</code> nhưng không cấp toàn bộ quyền OAuth trước khi Bob thay password.
8. Viết test xác minh locked, disabled, account-expired và credentials-expired đều không thể hoàn tất luồng đăng nhập mới; thêm integration test để kiểm tra thay đổi trạng thái sau khi có session và authorization code.

Một thiết kế đạt yêu cầu phải trả lời được **trạng thái tài khoản được kiểm tra ở đâu, khi nào bị thay đổi, cần thu hồi những gì, trong bao lâu hiệu lực và hệ thống xử lý lỗi ra sao**.

## 14. Tài liệu đối chiếu

- [Spring Security — UserDetails](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html): vai trò <code>UserDetailsService</code> và cách lấy thông tin người dùng.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): xác thực username/password và <code>PasswordEncoder</code>.
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html): form login, failure handling và filter đăng nhập.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): security context, session lifecycle và concurrency.
- [Spring Security — Authentication Events](https://docs.spring.io/spring-security/reference/servlet/authentication/events.html): authentication failure/success events và event publisher.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): lưu credential bằng password encoders an toàn.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): chuỗi filter và thành phần OAuth 2.0/OIDC.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): <code>OAuth2Authorization</code>, authorization service, client registration và consent.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization code, token endpoint và refresh token.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token và những giới hạn khi áp dụng.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): xác thực End-User, ID Token và liên hệ với OAuth 2.0.
