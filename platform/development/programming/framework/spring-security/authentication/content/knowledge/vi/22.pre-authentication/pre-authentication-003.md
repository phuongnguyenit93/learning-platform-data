# PreAuthenticatedAuthenticationProvider và việc nạp quyền ứng dụng

Trong **tiền xác thực** (*pre-authentication*), một hệ thống đáng tin cậy ở bên ngoài ứng dụng đã kiểm tra danh tính người dùng. Khi request tới ứng dụng Spring Security, câu hỏi chính không còn là “mật khẩu có đúng không?” mà là: **danh tính này có đáng tin không, người dùng tương ứng trong ứng dụng là ai và họ được phép làm gì?** `PreAuthenticatedAuthenticationProvider` là một thành phần giải quyết phần **nạp thông tin người dùng và quyền ứng dụng** sau khi danh tính bên ngoài đã được xác thực.

Bài học tập trung vào luồng pre-authentication cho **Spring Security Servlet**, cụ thể là vai trò của `PreAuthenticatedAuthenticationToken`, `PreAuthenticatedAuthenticationProvider`, `AuthenticationUserDetailsService`, `UserDetailsService` và `GrantedAuthority`. Ví dụ minh họa dùng Java 17+, Spring Boot 3.x và Spring Security 6.x; cơ chế nhận danh tính từ upstream phải được triển khai và bảo vệ riêng.

## 1. Bài toán: danh tính từ bên ngoài, quyền từ bên trong

Giả sử công ty dùng một hệ thống đăng nhập trung tâm (reverse proxy SSO, hệ thống xác thực của servlet container hoặc một gateway đáng tin cậy). Sau khi đăng nhập thành công ở đó, request đến ứng dụng mang theo danh tính chuẩn hóa, chẳng hạn `linh`.

Ứng dụng có quy tắc riêng:

- `linh` được xem báo cáo và xem hồ sơ;
- `minh` được quản trị báo cáo;
- người tồn tại trong hệ thống SSO **chưa chắc** có tài khoản hoặc quyền trong ứng dụng này.

Tách hai trách nhiệm:

| Việc cần làm | Nơi chịu trách nhiệm chính |
| --- | --- |
| Kiểm tra mật khẩu, chứng thư, MFA hoặc phiên đăng nhập ban đầu | Hệ thống xác thực bên ngoài |
| Bảo đảm danh tính truyền tới ứng dụng không bị giả mạo | Hạ tầng kết nối/trust boundary và cơ chế tích hợp |
| Chuyển danh tính đã xác minh thành `Authentication` của Spring Security | Pre-authentication filter + authentication provider |
| Tra cứu người dùng cục bộ, trạng thái, vai trò và quyền nghiệp vụ | `AuthenticationUserDetailsService`/`UserDetailsService` và nguồn dữ liệu ứng dụng |
| Chặn hoặc cho phép truy cập endpoint | Cơ chế authorization, ví dụ `hasAuthority`/`hasRole` |

**Chứng thực danh tính thành công không tự động đồng nghĩa được cấp mọi quyền.** Nếu ứng dụng chỉ nhận username mà không nạp đúng quyền, endpoint có thể bị từ chối hoặc, nguy hiểm hơn, được cấp quyền rộng hơn dự kiến. Spring Security không tự suy ra `ROLE_ADMIN` chỉ vì danh tính đến từ SSO.

### Thuật ngữ cần phân biệt

- **Principal:** danh tính đã được upstream xác minh, thường là username, email đã chuẩn hóa, hoặc subject ID ổn định.
- **Credentials:** đối tượng/chỉ dấu dùng trong token pre-authentication. Không phải mật khẩu cần kiểm tra lần nữa; nhiều filter dùng một giá trị giả như `N/A`.
- **Authentication:** đối tượng chứa principal, credentials, trạng thái xác thực và tập `GrantedAuthority`.
- **GrantedAuthority:** quyền cụ thể mà Spring Security đọc khi kiểm tra truy cập, ví dụ `REPORT_READ` hoặc `ROLE_ADMIN`.
- **UserDetails:** thông tin người dùng mà ứng dụng tự nạp, có thể gồm username, trạng thái tài khoản và authorities.

Không đồng nhất “đã xác thực ở ngoài” với “đã được ủy quyền trong app”.

## 2. Luồng xử lý từ request tới quyền ứng dụng

Sơ đồ logic:

~~~text
Người dùng
  │ đăng nhập qua upstream/SSO
  ▼
Hệ thống xác thực bên ngoài
  │ chuyển danh tính đã bảo vệ: "linh"
  ▼
Ứng dụng: AbstractPreAuthenticatedProcessingFilter
  │ tạo PreAuthenticatedAuthenticationToken
  │ principal="linh", credentials="N/A"
  ▼
AuthenticationManager (thường là ProviderManager)
  │ chọn AuthenticationProvider hỗ trợ kiểu token
  ▼
PreAuthenticatedAuthenticationProvider
  │ delegate loadUserDetails(token)
  ▼
AuthenticationUserDetailsService
  │ tìm user/role từ dữ liệu ứng dụng
  ▼
UserDetails(username="linh", authorities=[REPORT_READ, PROFILE_VIEW])
  │ trả kết quả
  ▼
Authentication đã xác thực + GrantedAuthority
  │ được đặt trong SecurityContext
  ▼
Authorization: hasAuthority("REPORT_READ")
  ├── có quyền  → cho phép
  └── thiếu quyền → 403 Forbidden
~~~

Các bước quan trọng:

1. **Bảo đảm request thật sự đi qua tầng xác thực đáng tin.** Đây là tiên quyết ngoài phạm vi provider.
2. **Filter lấy principal.** Ví dụ `J2eePreAuthenticatedProcessingFilter` đọc tên từ `HttpServletRequest.getUserPrincipal()` do servlet container đã xác thực. Một filter khác có thể lấy thông tin từ request attribute hoặc header do gateway kiểm soát.
3. **Filter tạo token chưa xác thực** dạng `PreAuthenticatedAuthenticationToken(principal, credentials)` và chuyển đến `AuthenticationManager`.
4. **`ProviderManager` chọn `PreAuthenticatedAuthenticationProvider`**, vì provider này hỗ trợ `PreAuthenticatedAuthenticationToken`.
5. **Provider gọi `AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>`** để nạp `UserDetails` tương ứng. Ứng dụng có thể kiểm tra trạng thái và chính sách tài khoản trong bước này.
6. **Provider tạo kết quả authenticated** với danh tính và authorities từ user details; filter chuyển kết quả vào `SecurityContext`.
7. **Bước authorization áp dụng quyền đã nạp.** Các điều kiện `authenticated()`, `hasAuthority(...)` và `hasRole(...)` kiểm tra kết quả đó.

Một request pre-authentication hợp lệ có thể bị từ chối khi tài khoản trong ứng dụng không tồn tại, bị khóa hoặc thiếu quyền. Đây là hành vi cần có nếu yêu cầu nghiệp vụ là “chỉ người đã được cấp quyền nội bộ mới vào được”.

## 3. PreAuthenticatedAuthenticationProvider thực sự làm gì?

`PreAuthenticatedAuthenticationProvider` là một `AuthenticationProvider` cho loại token `PreAuthenticatedAuthenticationToken`. Hành vi cốt lõi của nó **khác** `DaoAuthenticationProvider`:

| Tiêu chí | `PreAuthenticatedAuthenticationProvider` | `DaoAuthenticationProvider` |
| --- | --- | --- |
| Tình huống | Danh tính đã được hệ thống ngoài xác thực | Đăng nhập username/password ngay trong app |
| Token đầu vào thường gặp | `PreAuthenticatedAuthenticationToken` | `UsernamePasswordAuthenticationToken` |
| Kiểm tra mật khẩu người dùng | **Không** | Thường kiểm tra qua `PasswordEncoder` |
| Nạp user/authority | Qua `AuthenticationUserDetailsService` | Qua `UserDetailsService` |
| Nguồn bảo đảm danh tính | Hệ thống upstream, filter và trust boundary | Bằng chứng credential do provider kiểm tra |
| Kết quả | `Authentication` chứa principal và quyền ứng dụng | `Authentication` chứa principal và quyền sau khi kiểm tra credential |

Provider không xác minh chữ ký SSO, không gọi IdP để kiểm tra lại session, không xác thực request header và không biến mọi username thành danh tính đáng tin. Nếu một thành phần không đáng tin tự tạo `PreAuthenticatedAuthenticationToken("admin", "N/A")` rồi được đưa tới provider, provider có thể nạp quyền admin. **Vì thế kiểm soát nguồn tạo token là điều kiện bảo mật bắt buộc.**

### Các thành phần cấu hình

- `setPreAuthenticatedUserDetailsService(...)`: bắt buộc cung cấp cách nạp `UserDetails` từ token; nếu không, provider không đủ cấu hình để hoạt động.
- `setThrowExceptionWhenTokenRejected(true)`: khi token không có principal hoặc credentials, provider ném `BadCredentialsException` thay vì bỏ qua để provider khác thử. Đây là lựa chọn quan trọng trong mô hình chỉ chấp nhận pre-auth.
- `setUserDetailsChecker(...)`: thay đổi cách kiểm tra trạng thái `UserDetails` sau khi nạp; mặc định có trình kiểm tra các trạng thái tài khoản thường dùng. Không tự bỏ qua trạng thái khóa/vô hiệu hóa.
- `supports(PreAuthenticatedAuthenticationToken.class)`: provider nhận diện loại token mình hỗ trợ, không dùng để kiểm chứng tin cậy của principal.

Một `AuthenticationManager` có thể chứa nhiều provider. Nếu phối hợp pre-auth với form login hoặc HTTP Basic, cần thiết kế rõ entrypoint, thứ tự filter, cách fallback và đường không được phép vượt qua SSO. Mô hình dưới đây cố ý tập trung vào pre-auth.

### Vì sao credentials có thể là "N/A"?

Filter như `J2eePreAuthenticatedProcessingFilter` không có mật khẩu gốc để gửi cho provider và sử dụng một giá trị giả. Điều này hợp lý: upstream đã xác minh bằng chứng; provider chỉ nạp user và authority. Tuy nhiên, đối tượng credentials thường **không được để null** ở yêu cầu hợp lệ vì provider có thể xem token như không hợp lệ. Không biến giá trị `N/A` thành mật khẩu có ý nghĩa bảo mật.

## 4. Nạp quyền từ dữ liệu ứng dụng

Hai cách phổ biến:

### 4.1. UserDetailsByNameServiceWrapper — cách dùng cho quyền cục bộ

Spring Security có `UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>`. Wrapper nhận token, lấy tên principal và gọi một `UserDetailsService` bình thường:

~~~text
PreAuthenticatedAuthenticationToken("linh", "N/A")
            │
            ▼
UserDetailsByNameServiceWrapper
            │ loadUserByUsername("linh")
            ▼
UserDetailsService ── repository của ứng dụng
            │
            ▼
UserDetails(username="linh", authorities=[REPORT_READ])
~~~

Ưu điểm: có thể tái sử dụng repository và chính sách mapping quyền hiện có. Ví dụ bảng nghiệp vụ:

| user_id | external_subject | enabled | application_permission |
| --- | --- | --- | --- |
| 17 | `linh` | `true` | `REPORT_READ` |
| 17 | `linh` | `true` | `PROFILE_VIEW` |
| 28 | `minh` | `true` | `REPORT_ADMIN` |

Các quyền ở bảng là **dữ liệu của ứng dụng**, không phải bằng chứng xác thực. Trong môi trường thực tế, `UserDetailsService` cần truy xuất user theo khóa đã xác minh, kiểm tra trạng thái, rồi ánh xạ quyền thành `GrantedAuthority`. Nếu upstream dùng subject ID bền vững thay vì username dễ đổi, lớp tích hợp nên ánh xạ ID đó sang tài khoản nội bộ theo quy tắc rõ ràng.

Với người không được cấp quyền ứng dụng, nên ném `UsernameNotFoundException` hoặc trả user bị vô hiệu hóa để hệ thống từ chối truy cập theo chính sách; **không tự cấp role mặc định rộng** hoặc tự tạo tài khoản có quyền.

### 4.2. PreAuthenticatedGrantedAuthoritiesUserDetailsService — quyền do upstream chuyển vào

`PreAuthenticatedGrantedAuthoritiesUserDetailsService` lấy authorities từ `token.getDetails()` **khi details triển khai `GrantedAuthoritiesContainer`**. Nó khác cách tải từ repository: nguồn authority chính là dữ liệu gắn vào request token, không phải bảng quyền ứng dụng.

~~~text
Trusted upstream roles
    → pre-auth filter/details source
    → token.details implements GrantedAuthoritiesContainer
    → PreAuthenticatedGrantedAuthoritiesUserDetailsService
    → UserDetails + authorities
~~~

Nếu details chỉ là `WebAuthenticationDetails` thông thường, không chứa `GrantedAuthoritiesContainer` theo cách API yêu cầu, không thể mặc định rằng provider sẽ đọc được role từ đó. Có thể dùng `PreAuthenticatedGrantedAuthoritiesWebAuthenticationDetails` hoặc một details source phù hợp để cung cấp dữ liệu, nhưng chỉ khi **nguồn roles được bảo vệ và ánh xạ minh bạch**. Việc nhận thẳng header `X-Role: ADMIN` từ client là không an toàn.

**Chọn cách nào?** Nếu ứng dụng sở hữu quyết định cấp quyền, ưu tiên wrapper + `UserDetailsService` dựa trên kho dữ liệu của app. Nếu quyền upstream đã được quản trị thống nhất và ứng dụng có hợp đồng tin cậy cụ thể, có thể đọc quyền từ pre-auth details nhưng vẫn kiểm tra tên quyền, tenant, thời hạn và trạng thái quyền. Không trộn hai nguồn bằng phép cộng quyền mặc định mà thiếu quy tắc ưu tiên/thu hồi.

## 5. Ví dụ cấu hình Java: container xác thực, ứng dụng nạp quyền

Ví dụ này sử dụng **Spring Security Servlet**. Giả định container/kiến trúc deploy đã xác thực request, nên `request.getUserPrincipal()` chứa danh tính được container cấp. Nếu chỉ chạy Spring Boot embedded server chưa cấu hình container authentication, principal có thể là `null` và mọi route bảo vệ sẽ bị chặn. Ví dụ **không tự cung cấp một màn hình đăng nhập SSO**.

### 5.1. Dependencies

Trong một ứng dụng Spring Boot 3.x sử dụng Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Ứng dụng cần plugin Spring Boot, dependency management và Java toolchain tương ứng do project quản lý. `spring-boot-starter-security` cung cấp Spring Security cho servlet web và `PreAuthenticatedAuthenticationProvider`; không cần thêm một thư viện “preauth provider” riêng.

### 5.2. Lớp cấu hình

Tệp `src/main/java/example/preauth/PreAuthSecurityConfig.java`:

~~~java
package example.preauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.Http403ForbiddenEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.j2ee.J2eePreAuthenticatedProcessingFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration(proxyBeanMethods = false)
public class PreAuthSecurityConfig {

    @Bean
    UserDetailsService applicationUserDetailsService() {
        // Dữ liệu minh họa. Production: thay bằng repository quyền ứng dụng.
        return username -> {
            if ("linh".equals(username)) {
                return User.withUsername(username)
                        .password("{noop}not-used")
                        .authorities("REPORT_READ", "PROFILE_VIEW")
                        .build();
            }
            if ("minh".equals(username)) {
                return User.withUsername(username)
                        .password("{noop}not-used")
                        .authorities("REPORT_ADMIN")
                        .build();
            }
            throw new UsernameNotFoundException("No application account");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService applicationUserDetailsService)
            throws Exception {

        PreAuthenticatedAuthenticationProvider provider =
                new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(
                new UserDetailsByNameServiceWrapper<>(
                        applicationUserDetailsService));
        provider.setThrowExceptionWhenTokenRejected(true);

        AuthenticationManager preAuthManager = new ProviderManager(provider);

        J2eePreAuthenticatedProcessingFilter preAuthFilter =
                new J2eePreAuthenticatedProcessingFilter();
        preAuthFilter.setAuthenticationManager(preAuthManager);

        // Kiểm tra danh tính lại trên từng request; không lưu trong session.
        NullSecurityContextRepository contextRepository =
                new NullSecurityContextRepository();
        preAuthFilter.setSecurityContextRepository(contextRepository);
        http.securityContext(context -> context
                .securityContextRepository(contextRepository));
        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        // Chỉ đăng ký filter bên trong SecurityFilterChain.
        http.addFilterBefore(preAuthFilter,
                UsernamePasswordAuthenticationFilter.class);

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/reports/**").hasAuthority("REPORT_READ")
                .requestMatchers("/manage/**").hasAuthority("REPORT_ADMIN")
                .anyRequest().authenticated());
        http.exceptionHandling(errors -> errors
                .authenticationEntryPoint(new Http403ForbiddenEntryPoint()));

        return http.build();
    }
}
~~~

**Giải thích theo từng lớp trách nhiệm:**

1. `applicationUserDetailsService()` ánh xạ một principal đã được xác minh thành tài khoản + danh sách quyền nghiệp vụ. Hai người trong ví dụ chỉ mô phỏng repository. `password("{noop}not-used")` là giá trị bắt buộc của đối tượng `UserDetails` trong ví dụ, **không dùng để xác thực password**.
2. `UserDetailsByNameServiceWrapper` thích nghi `UserDetailsService` thành `AuthenticationUserDetailsService` mà `PreAuthenticatedAuthenticationProvider` cần.
3. `ProviderManager(provider)` chỉ chứa provider dành cho pre-auth. Ứng dụng này không kích hoạt form login hoặc Basic như một cơ chế truy cập thay thế.
4. `J2eePreAuthenticatedProcessingFilter` đọc `HttpServletRequest.getUserPrincipal()` của servlet container. Filter không tự xác thực mật khẩu hoặc token SSO. Tên principal do container cung cấp phải được thiết lập bởi tầng xác thực đáng tin cậy.
5. `NullSecurityContextRepository` và `SessionCreationPolicy.STATELESS` giúp ví dụ kiểm tra danh tính và nạp authorities theo từng request thay vì giữ một session đăng nhập của ứng dụng. Chi phí truy vấn dữ liệu sẽ tăng; cần cache có chính sách thu hồi phù hợp nếu lưu lượng lớn.
6. `addFilterBefore(..., UsernamePasswordAuthenticationFilter.class)` đặt filter ở pha xác thực trong Security Filter Chain. Vì chỉ tạo filter như biến cục bộ trong cấu hình, ví dụ tránh vô tình đăng ký cùng filter hai lần qua cơ chế auto-registration servlet của Spring Boot.
7. `hasAuthority("REPORT_READ")` kiểm tra đúng chuỗi quyền. `hasAuthority("REPORT_ADMIN")` cũng vậy, không tự thêm `ROLE_`. Nếu chỉ có `REPORT_ADMIN` nhưng thiếu `REPORT_READ`, tài khoản `minh` **không tự động được xem `/reports/**`** theo cấu hình này.
8. `Http403ForbiddenEntryPoint` trả 403 khi request chưa được xác thực mà truy cập tài nguyên bảo vệ; khi đã xác thực nhưng thiếu authority, Spring Security cũng chặn với 403. Cần kiểm thử cụ thể nếu hệ thống muốn phân biệt 401 và 403.

**Điểm giới hạn của ví dụ:** không có cơ chế xác thực container được cấu hình trong mã trên. Khi chạy đơn lẻ trên một embedded Tomcat mặc định, một request như `curl http://localhost:8080/reports/summary` **không chứng minh pre-auth thành công**, vì chưa có principal từ container và cũng chưa định nghĩa controller. Muốn chạy end-to-end, phải tích hợp SSO/container authentication thật hoặc triển khai test harness mô phỏng principal tại ranh giới tin cậy.

### 5.3. Nạp quyền từ database thay vì hard-code

Trong ứng dụng thật, phần lõi trong `UserDetailsService` có thể như sau; đây là **pseudocode Java có API repository do ứng dụng tự định nghĩa**, không phải class độc lập chạy ngay:

~~~java
return verifiedSubject -> {
    ApplicationAccount account = accountRepository
            .findByExternalSubject(verifiedSubject)
            .orElseThrow(() ->
                    new UsernameNotFoundException("No application account"));

    if (!account.isEnabled()) {
        throw new DisabledException("Application account disabled");
    }

    var authorities = permissionRepository
            .findPermissionCodesByAccountId(account.getId())
            .stream()
            .map(SimpleGrantedAuthority::new)
            .toList();

    return User.withUsername(account.getExternalSubject())
            .password("{noop}not-used")
            .authorities(authorities)
            .build();
};
~~~

Các class `ApplicationAccount`, `accountRepository`, `permissionRepository` và import `DisabledException`/`SimpleGrantedAuthority` do project cung cấp. Trong thực tế, cần xử lý user bị xóa, quyền hết hạn, tenant, bản ghi trùng và cache nhất quán. Khi dùng `UserDetailsService`, đừng suy ra quyền từ username như `username.startsWith("admin")`.

Để tránh gán nhầm tài khoản, định danh dùng làm khóa tra cứu cần được upstream thống nhất và duy nhất trong miền phù hợp. Email có thể thay đổi hoặc trùng giữa các tenant; khi SSO cung cấp subject ID ổn định, có thể ghép `issuer + subject` để định danh thay vì chỉ dựa vào tên hiển thị.

## 6. Kiểm tra trực tiếp logic của provider bằng JUnit

Vì việc xác thực upstream phụ thuộc hạ tầng, có thể kiểm tra độc lập phần **nạp quyền ứng dụng** bằng unit test: tạo token pre-auth giả lập sau bước xác minh bên ngoài, gọi provider và kiểm tra authorities trả về. Test này kiểm tra provider/role mapping; **không thay thế** test bảo mật ranh giới upstream.

Tệp `src/test/java/example/preauth/PreAuthProviderTest.java`:

~~~java
package example.preauth;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;

import static org.junit.jupiter.api.Assertions.*;

class PreAuthProviderTest {

    private PreAuthenticatedAuthenticationProvider provider() {
        UserDetailsService userStore = username -> {
            if (!"linh".equals(username)) {
                throw new UsernameNotFoundException("Not registered in app");
            }
            return User.withUsername(username)
                    .password("{noop}not-used")
                    .authorities("REPORT_READ", "PROFILE_VIEW")
                    .build();
        };

        PreAuthenticatedAuthenticationProvider provider =
                new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(
                new UserDetailsByNameServiceWrapper<>(userStore));
        provider.setThrowExceptionWhenTokenRejected(true);
        return provider;
    }

    @Test
    void existingApplicationUserReceivesApplicationPermissions() {
        Authentication token =
                new PreAuthenticatedAuthenticationToken("linh", "N/A");

        Authentication result = provider().authenticate(token);

        assertNotNull(result);
        assertTrue(result.isAuthenticated());
        assertEquals("linh", result.getName());
        Set<String> actual = result.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.toSet());
        assertEquals(Set.of("REPORT_READ", "PROFILE_VIEW"), actual);
    }

    @Test
    void unknownApplicationUserIsRejected() {
        Authentication token =
                new PreAuthenticatedAuthenticationToken("stranger", "N/A");

        assertThrows(UsernameNotFoundException.class,
                () -> provider().authenticate(token));
    }

    @Test
    void missingCredentialsIsRejected() {
        Authentication token =
                new PreAuthenticatedAuthenticationToken("linh", null);

        assertThrows(BadCredentialsException.class,
                () -> provider().authenticate(token));
    }
}
~~~

Chạy trong project Spring Boot Gradle có JUnit Platform:

~~~bash
./gradlew test --tests example.preauth.PreAuthProviderTest
~~~

Trên Windows dùng `gradlew.bat test --tests example.preauth.PreAuthProviderTest`. Khi chạy thành công, Gradle báo `BUILD SUCCESSFUL`; số lượng và nội dung dòng log phụ thuộc Gradle/project, nên không khẳng định một stdout cố định. Ba test xác minh: user hợp lệ được nạp hai quyền, user chưa được ứng dụng cấp tài khoản bị từ chối, token thiếu credentials bị từ chối khi cài `throwExceptionWhenTokenRejected`.

**Giới hạn kiểm thử:** bất cứ ai trong cùng tiến trình có thể tạo token `("linh", "N/A")`. Test chủ động làm vậy để cô lập logic provider. Không được suy luận rằng điều này chứng minh request từ internet đã qua SSO.

## 7. hasAuthority, hasRole và phạm vi quyền

Trong Spring Security, authority là một chuỗi; `hasAuthority("REPORT_READ")` kiểm tra một authority bằng đúng tên đó. Trong khi đó, `hasRole("ADMIN")` theo cấu hình mặc định kiểm tra authority mang tiền tố `ROLE_ADMIN`.

Ví dụ:

| Authorities trong `Authentication` | Rule | Kết quả |
| --- | --- | --- |
| `REPORT_READ`, `PROFILE_VIEW` | `hasAuthority("REPORT_READ")` | Cho phép |
| `REPORT_READ` | `hasRole("ADMIN")` | Từ chối, không có `ROLE_ADMIN` |
| `ROLE_ADMIN` | `hasRole("ADMIN")` | Cho phép |
| `REPORT_ADMIN` | `hasAuthority("REPORT_READ")` | Từ chối nếu không bổ sung `REPORT_READ` |
| Không có authority | `authenticated()` | Có thể cho phép nếu principal đã xác thực, nhưng các rule quyền chi tiết vẫn từ chối |

Một tài khoản đã authenticated nhưng thiếu `REPORT_READ` cần nhận 403 khi truy cập tài nguyên đòi `REPORT_READ`. Nếu có `@PreAuthorize("hasAuthority('REPORT_READ')")` ở tầng method, phải bật `@EnableMethodSecurity`; cấu hình URL và method là hai nơi kiểm tra khác nhau.

Không nên sử dụng tất cả nhóm từ IdP làm role trực tiếp mà chưa chuẩn hóa. Ví dụ nhóm `finance-team` ở IdP có thể được ánh xạ thành quyền ứng dụng `INVOICE_READ` theo chính sách có chủ sở hữu, thay vì cấp mặc định `ROLE_ADMIN`.

## 8. Tình huống an toàn khi tích hợp với gateway SSO

Pre-auth dựa trên giả định **caller của ứng dụng không thể tự chọn danh tính đáng tin**. Đây là phần dễ sai nhất khi tích hợp thực tế.

### Trường hợp nhận username bằng HTTP header

`RequestHeaderAuthenticationFilter` có thể đọc một header như `SM_USER` hoặc `X-Verified-User`. Nó **chỉ đọc header, không tự kiểm tra chữ ký, mật khẩu hay phiên**. Nếu một request trực tiếp gửi:

~~~http
GET /manage/overview HTTP/1.1
Host: app.example.org
X-Verified-User: minh
~~~

thì filter có thể coi `minh` là principal nếu không có lớp bảo vệ bên ngoài. Vì vậy không dùng header do client tự gửi để tạo pre-auth token. Khi hệ thống dùng gateway tin cậy, cần:

1. Chặn mọi đường truy cập trực tiếp từ client đến ứng dụng backend; chỉ cho phép qua gateway hoặc mạng/identity được kiểm soát.
2. Gateway phải xóa mọi header danh tính do client gửi trước khi tự đặt header từ một session/token đã xác minh.
3. Bảo vệ kết nối gateway → ứng dụng bằng TLS/mTLS hoặc biện pháp mạng tương đương theo mô hình đe dọa.
4. Xác định rõ identity format, issuer, tenant và quy tắc chống trùng/giả mạo.
5. Kiểm thử request không có danh tính, header giả, request đi vòng gateway, session upstream đã logout, và user bị thu hồi.

Có thể dùng cơ chế dựa trên `HttpServletRequest.getUserPrincipal()` nếu servlet container thật sự đảm bảo tính xác thực của principal; không coi một request attribute tùy ý là bằng chứng an toàn chỉ vì nó được gán từ một component trong app.

### Session, cache và thay đổi quyền

Nếu nạp quyền từ database sau mỗi request như cấu hình stateless trong ví dụ, việc thay đổi quyền có thể có hiệu lực ở lần request tiếp theo (tùy cache). Nếu dùng `HttpSessionSecurityContextRepository` hay cache `UserDetails`, quyền cũ có thể tồn tại đến khi session/cache hết hạn hoặc bị vô hiệu hóa. Cần thiết kế rõ:

- thời điểm áp dụng thay đổi cấp/thu hồi quyền;
- khả năng khóa tài khoản ngay sau khi SSO đã đăng nhập;
- kiểm tra thay đổi principal giữa các request, nhất là khi chia sẻ cùng browser/session;
- chính sách TTL, invalidate session, cache eviction và nguồn dữ liệu đáng tin.

`AbstractPreAuthenticatedProcessingFilter` có tùy chọn `setCheckForPrincipalChanges(true)` để kiểm tra thay đổi principal đối với một `Authentication` hiện có; đây không tự giải quyết việc quyền trong database thay đổi mà principal vẫn giữ nguyên. Đừng coi session của Spring Security thay thế cho thời hạn và kiểm tra trạng thái session của IdP.

## 9. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Kiểm tra/cách xử lý |
| --- | --- | --- |
| Luôn bị 403 trước khi vào ứng dụng | Servlet container không cấp principal; đường request chưa đi qua SSO | Xác minh `getUserPrincipal()` ở biên nhận request, thiết kế upstream, cấu hình entrypoint |
| Principal hợp lệ nhưng `UsernameNotFoundException` | App chưa có user mapping, username khác định dạng, tenant không khớp | Kiểm tra subject→account mapping, normalization, active status |
| App nhận đúng user nhưng thiếu role | `UserDetailsService` không trả authorities, mapping sai hoặc cache cũ | Kiểm tra `result.getAuthorities()` trong test/log an toàn, quyền DB và chính sách cache |
| `hasRole("ADMIN")` luôn từ chối | DB trả `ADMIN`/`REPORT_ADMIN` trong khi rule đòi `ROLE_ADMIN` | Chuẩn hóa prefix hoặc dùng `hasAuthority` chính xác |
| Provider không nhận request | Token không phải `PreAuthenticatedAuthenticationToken` hoặc manager không gắn provider | Kiểm tra class token, `supports` và cấu hình `ProviderManager` |
| Provider lỗi vì principal/credentials null | Filter không lấy được identity hoặc trả null credentials | Sửa nguồn danh tính tin cậy; với pre-auth hợp lệ dùng credentials marker không null |
| Lệnh gọi bypass SSO vẫn được nhận | Backend mở trực tiếp hoặc proxy không loại bỏ header giả | Khóa backend, thiết lập trusted ingress, viết kiểm thử giả header |
| Quyền bị thu hồi nhưng request vẫn cho phép | Session/cache giữ authorities cũ | Kiểm tra SecurityContextRepository, TTL, invalidation/reload |
| Tài khoản disabled vẫn dùng được | Nguồn user không cập nhật trạng thái hoặc tùy chỉnh checker sai | Đảm bảo trạng thái account được nạp và kiểm tra trước khi cấp authentication |

Chẩn đoán theo thứ tự: **upstream có xác thực và bảo vệ danh tính không → filter lấy được principal không → token đúng loại/không null không → provider có gọi user details service không → app trả đúng authorities không → rule authorization đang kiểm tra quyền nào**. Ở production không ghi log token gốc, cookie, credential hoặc header bí mật; chỉ log sự kiện và mã lỗi được kiểm soát.

## 10. Tự kiểm tra kiến thức

1. Vì sao `PreAuthenticatedAuthenticationProvider` không thể thay thế việc xác minh session/chữ ký của IdP?
2. Trong luồng pre-auth, tại sao người đã đăng nhập ở SSO vẫn có thể không truy cập được `/reports/**`?
3. Khi nào dùng `UserDetailsByNameServiceWrapper`, khi nào dùng `PreAuthenticatedGrantedAuthoritiesUserDetailsService`?
4. Nếu user có quyền `REPORT_ADMIN` nhưng endpoint yêu cầu `REPORT_READ`, truy cập có thành công không? Vì sao?
5. Provider nhận token principal `linh` và credentials `N/A`. Giá trị `N/A` có chứng minh user là `linh` không?
6. Nêu hai lý do khiến quyền đã bị thu hồi vẫn tồn tại trong request tiếp theo.

**Gợi ý đáp án:** (1) Provider tin vào bằng chứng đã được tầng ngoài kiểm tra; (2) app chưa nạp được user hoặc quyền; (3) quyền từ DB ứng dụng versus authorities được upstream cấp qua details hợp lệ; (4) không, vì `hasAuthority` so chuỗi đúng tên; (5) không, giá trị giả chỉ thỏa cấu trúc token; (6) session/cache cũ và chưa áp dụng chính sách reload/eviction.

## 11. Checklist trước khi đưa vào vận hành

- [ ] Có hợp đồng tin cậy rõ ràng với hệ thống upstream, gồm principal, issuer/tenant và cách chống giả mạo.
- [ ] Backend không thể bị client truy cập vòng qua gateway hoặc tự tạo principal/header được tin cậy.
- [ ] Filter tạo token `PreAuthenticatedAuthenticationToken` chỉ từ danh tính đã được xác minh.
- [ ] Provider được gắn đúng `AuthenticationManager` và nạp `UserDetails` qua nguồn quyền dự kiến.
- [ ] User vắng mặt/disabled/locked bị từ chối; không tự tạo quyền rộng.
- [ ] Quyền từ ứng dụng được chuẩn hóa, có test `hasAuthority`/`hasRole` đúng prefix.
- [ ] Có phương án thu hồi quyền, vô hiệu hóa session/cache và xử lý đổi principal.
- [ ] Có test tích hợp request không có danh tính, header giả, user không có quyền và user có quyền.
- [ ] Ghi log vừa đủ để chẩn đoán nhưng không ghi credential hay dữ liệu nhạy cảm.

## 12. Tài liệu tham khảo

- [Spring Security Reference: Pre-Authentication Scenarios](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/preauth.html)
- [PreAuthenticatedAuthenticationProvider API (6.5)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html)
- [AbstractPreAuthenticatedProcessingFilter API (6.5)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html)
- [J2eePreAuthenticatedProcessingFilter API (6.5)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/j2ee/J2eePreAuthenticatedProcessingFilter.html)
- [UserDetailsByNameServiceWrapper API (6.5)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsByNameServiceWrapper.html)
- [PreAuthenticatedGrantedAuthoritiesUserDetailsService API (6.5)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedGrantedAuthoritiesUserDetailsService.html)
