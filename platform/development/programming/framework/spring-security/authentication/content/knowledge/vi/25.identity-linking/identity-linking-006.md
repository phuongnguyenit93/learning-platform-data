# JAAS và vai trò tích hợp Subject với mô hình Spring Security

> **Phạm vi:** JAAS (Java Authentication and Authorization Service) cung cấp `LoginContext`, `LoginModule`, `Subject` và các `Principal`. Spring Security dùng `AuthenticationManager`, `AuthenticationProvider`, `Authentication`, `SecurityContext` và `GrantedAuthority`. Bài học giải thích ranh giới giữa hai mô hình, cách xác thực qua JAAS rồi ánh xạ quyền vào Spring, khi nào phải chạy mã kế thừa dưới JAAS Subject và những giới hạn về vòng đời/ngữ cảnh thực thi. Ví dụ Java dùng JDK 17+; phần Spring minh họa Spring Security 6.x trên Servlet stack.

## 1. Bạn cần nắm được điều gì?

Sau bài này, bạn có thể:

1. Mô tả vai trò của `Configuration`, `LoginContext`, `LoginModule`, `CallbackHandler`, `Subject` và `Principal`.
2. Phân biệt **JAAS Subject** với **Spring Security Authentication**; biết vì sao hai đối tượng không thay thế trực tiếp cho nhau.
3. Chọn `DefaultJaasAuthenticationProvider` hoặc `JaasAuthenticationProvider` để đưa LoginModule hiện hữu vào chuỗi xác thực của Spring Security.
4. Ánh xạ JAAS principal nhóm thành `GrantedAuthority` thông qua `AuthorityGranter` theo chính sách tường minh.
5. Nhận biết trường hợp cần `JaasApiIntegrationFilter` hoặc `Subject.doAs` cho thư viện yêu cầu current Subject.
6. Kiểm soát lỗi, credential, login/logout, session, rò rỉ ngữ cảnh giữa thread và các giới hạn của WebFlux.

JAAS hữu ích khi tổ chức đã có **Kerberos login module, thư viện doanh nghiệp hoặc lớp tích hợp cũ** phụ thuộc cơ chế JAAS. JAAS không phải thành phần bắt buộc cho mọi ứng dụng Spring và không tự cung cấp OAuth2/OIDC login, ánh xạ LDAP group hay chính sách authorization của ứng dụng.

## 2. Bản chất JAAS: Subject và nhiều Principal

| Thành phần | Công dụng | Lưu ý |
| --- | --- | --- |
| `LoginContext` | Đọc tên cấu hình, chạy `LoginModule`, gọi `login()`/`logout()` và trả `Subject` | Không phải `SecurityContext` của Spring |
| `LoginModule` | Plugin thực hiện xác thực cụ thể, ví dụ Kerberos hoặc backend doanh nghiệp | Không đồng nghĩa với Spring `AuthenticationProvider` |
| `CallbackHandler` | Đưa username/password/OTP hoặc dữ liệu khác cho LoginModule qua các callback | Không nên hỏi mật khẩu lần nữa khi Spring đã thu thập |
| `Configuration` | Danh sách module và các cờ `REQUIRED`, `REQUISITE`, `SUFFICIENT`, `OPTIONAL` | Cờ quyết định cách nhiều module phối hợp |
| `Subject` | Tập hợp danh tính và credentials của chủ thể | Có nhiều `Principal` chứ không chỉ một username |
| `Principal` | Một định danh: user, nhóm, service principal hoặc định danh Kerberos | Principal chưa tự động là role Spring |
| `Subject.getPrivateCredentials()` | Các credentials có tính nhạy cảm | Không log/serialize hoặc đẩy vào session tùy tiện |

Một `Subject` có thể có các principal như `UserPrincipal("mai")`, `GroupPrincipal("report-readers")` và Kerberos principal cùng tồn tại. Mỗi principal biểu diễn một khía cạnh danh tính. **Đừng lấy một chuỗi `principal.getName()` bất kỳ rồi tự hiểu là quyền quản trị.** Cần biết chính xác kiểu principal, LoginModule nào cung cấp và chính sách ủy quyền nào được tổ chức phê duyệt.

### Hai pha login/commit của JAAS

~~~text
Ứng dụng gọi LoginContext.login()
         |
         v
Configuration tìm LoginModule theo tên context
         |
         v
LoginModule.initialize(subject, callbackHandler, sharedState, options)
         |
         +-- login()  : kiểm tra credentials, ghi kết quả tạm
         |
         +-- commit() : khi tổng thể xác thực thành công, gắn Principal
         |
         +-- abort()  : khi thất bại, thu hồi trạng thái tạm
         |
         v
LoginContext.getSubject() sau khi login thành công
         |
         +-- logout() : gọi cleanup của từng LoginModule
~~~

`LoginContext` phối hợp các module theo control flag. Module có thể trả `false` (không tham gia), trả `true` (thành công) hoặc ném `LoginException`. Khi đăng nhập tổng thể thành công, các module thành công thực hiện `commit()` và đưa principal/credential hợp lệ vào Subject. Khi thất bại, `abort()` phải dọn trạng thái; không được để một Subject chưa xác thực mang role như đã đăng nhập.

## 3. So sánh JAAS với Spring Security

| JAAS | Spring Security | Cách hiểu |
| --- | --- | --- |
| `Subject` chứa nhiều `Principal` và credentials | `Authentication` mang principal, credentials, authorities, trạng thái authenticated | Không có phép ép kiểu trực tiếp |
| `LoginContext.login()` | `AuthenticationManager.authenticate(...)` | Một bên là API xác thực JAAS; một bên là API điều phối provider Spring |
| `LoginModule` | `AuthenticationProvider` | Spring có provider cầu nối để gọi LoginModule |
| `Subject.getPrincipals()` | `Authentication.getPrincipal()` | Spring có principal chính; JAAS có thể có nhiều loại principal |
| Group principal của JAAS | `GrantedAuthority` như `ROLE_REPORT_READER` | Cần ánh xạ bằng policy rõ ràng |
| `Subject.doAs`/current Subject | `SecurityContextHolder` hoặc `ReactiveSecurityContextHolder` | Hai cơ chế ngữ cảnh độc lập |
| `LoginContext.logout()` | Session invalidation, logout handler, context clearing | Cần phối hợp vòng đời |

Sau khi Spring xác thực thành công, `SecurityContextHolder.getContext().getAuthentication()` chứa Spring Authentication trong Servlet request hiện tại. Với provider JAAS, token thành công thường là `JaasAuthenticationToken` và giữ `LoginContext`; nếu cần Subject, lấy từ `token.getLoginContext().getSubject()`. **`Authentication.getPrincipal()` không mặc nhiên trả về `Subject`.**

Vấn đề có hai bước tách biệt: **authentication** chứng minh user là ai; **authorization** quyết định user có quyền gì. Subject có group principal không có nghĩa tất cả group đó được cấp tự động vào Spring authorities.

## 4. Dòng dữ liệu khi Spring xác thực bằng JAAS

~~~text
Browser / API
    |
    v
Spring Security authentication filter
    |
    v
UsernamePasswordAuthenticationToken(username, password)
    |
    v
AuthenticationManager / ProviderManager
    |
    v
DefaultJaasAuthenticationProvider hoặc JaasAuthenticationProvider
    |
    +-- JaasNameCallbackHandler / JaasPasswordCallbackHandler
    |                          |
    |                     LoginContext.login()
    |                          |
    |                     LoginModule(s)
    |                          |
    |                     Subject.getPrincipals()
    |                          |
    +------------------> AuthorityGranter(s)
                               |
                               v
                     JaasGrantedAuthority
                               |
                               v
                     JaasAuthenticationToken
                               |
                               v
                    Spring SecurityContext
                               |
                               v
                     hasRole / hasAuthority
~~~

Những lớp quan trọng:

- `AbstractJaasAuthenticationProvider` là nền cho các provider JAAS của Spring, hỗ trợ xác thực token username/password và tương tác với `LoginContext`.
- `DefaultJaasAuthenticationProvider` nhận trực tiếp `javax.security.auth.login.Configuration`, thích hợp cho cấu hình trong Spring và các test có thể cô lập.
- `JaasAuthenticationProvider` dựa vào cấu hình JAAS dạng tệp/Java provider; thích hợp khi ứng dụng đã có `login.conf` và quy trình quản trị tương ứng.
- `JaasNameCallbackHandler` và `JaasPasswordCallbackHandler` chuyển các trường username/password đã có trong Spring token thành callback JAAS. Với OTP, smartcard, certificate hoặc cơ chế khác có thể cần handler riêng.
- `AuthorityGranter.grant(Principal)` đánh giá từng principal của Subject sau đăng nhập thành công và trả tập authority string; Spring tạo `JaasGrantedAuthority` tương ứng.

Spring vẫn chịu trách nhiệm thiết lập `SecurityFilterChain`, CSRF, session, endpoint authorization, error responses và logging. Provider chỉ là **cầu nối xác thực**, không thay thế toàn bộ security architecture.

## 5. Ví dụ Java 17 chạy độc lập: LoginModule tạo Subject

Ví dụ này cố ý dùng một user/password giả trong **môi trường học tập**, không kết nối hệ định danh thật và không có password policy production. Nó minh họa trực tiếp hai pha `login/commit`, đọc principal, rồi logout.

Tạo tệp `JaasSubjectDemo.java`:

~~~java
import java.io.IOException;
import java.security.Principal;
import java.util.Arrays;
import java.util.Map;
import javax.security.auth.Subject;
import javax.security.auth.callback.Callback;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.callback.NameCallback;
import javax.security.auth.callback.PasswordCallback;
import javax.security.auth.callback.UnsupportedCallbackException;
import javax.security.auth.login.AppConfigurationEntry;
import javax.security.auth.login.Configuration;
import javax.security.auth.login.FailedLoginException;
import javax.security.auth.login.LoginContext;
import javax.security.auth.login.LoginException;
import javax.security.auth.spi.LoginModule;

public final class JaasSubjectDemo {

    public record UserPrincipal(String name) implements Principal {
        @Override
        public String getName() {
            return name;
        }
    }

    public record GroupPrincipal(String name) implements Principal {
        @Override
        public String getName() {
            return name;
        }
    }

    public static final class DemoLoginModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private UserPrincipal user;
        private GroupPrincipal group;
        private boolean authenticated;

        public DemoLoginModule() {
        }

        @Override
        public void initialize(Subject subject, CallbackHandler handler,
                Map<String, ?> sharedState, Map<String, ?> options) {
            this.subject = subject;
            this.handler = handler;
        }

        @Override
        public boolean login() throws LoginException {
            if (handler == null) {
                throw new LoginException("CallbackHandler required");
            }
            NameCallback name = new NameCallback("User: ");
            PasswordCallback password = new PasswordCallback("Password: ", false);
            char[] received = null;
            try {
                handler.handle(new Callback[] {name, password});
                received = password.getPassword();
                boolean valid = "mai".equals(name.getName())
                        && Arrays.equals(received,
                                new char[] {'d', 'e', 'm', 'o'});
                if (!valid) {
                    throw new FailedLoginException("Invalid credentials");
                }
                user = new UserPrincipal("mai");
                group = new GroupPrincipal("report-readers");
                authenticated = true;
                return true;
            } catch (IOException | UnsupportedCallbackException ex) {
                throw new LoginException("Cannot process callbacks");
            } finally {
                if (received != null) {
                    Arrays.fill(received, '\0');
                }
                password.clearPassword();
            }
        }

        @Override
        public boolean commit() {
            if (!authenticated) {
                return false;
            }
            subject.getPrincipals().add(user);
            subject.getPrincipals().add(group);
            return true;
        }

        @Override
        public boolean abort() {
            return logout();
        }

        @Override
        public boolean logout() {
            if (user != null) {
                subject.getPrincipals().remove(user);
            }
            if (group != null) {
                subject.getPrincipals().remove(group);
            }
            user = null;
            group = null;
            authenticated = false;
            return true;
        }
    }

    public static void main(String[] args) throws LoginException {
        Configuration configuration = new Configuration() {
            @Override
            public AppConfigurationEntry[] getAppConfigurationEntry(String name) {
                if (!"Demo".equals(name)) {
                    return null;
                }
                return new AppConfigurationEntry[] {
                    new AppConfigurationEntry(
                            DemoLoginModule.class.getName(),
                            AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                            Map.of())
                };
            }
        };

        CallbackHandler callbacks = values -> {
            for (Callback callback : values) {
                if (callback instanceof NameCallback name) {
                    name.setName("mai");
                } else if (callback instanceof PasswordCallback password) {
                    password.setPassword(new char[] {'d', 'e', 'm', 'o'});
                } else {
                    throw new UnsupportedCallbackException(callback);
                }
            }
        };

        LoginContext context = new LoginContext("Demo", null,
                callbacks, configuration);
        context.login();

        Subject subject = context.getSubject();
        System.out.println("Login: OK");
        System.out.println("Principals: " + subject.getPrincipals().size());
        System.out.println("User: " + subject.getPrincipals(UserPrincipal.class)
                .iterator().next().getName());
        System.out.println("Group: " + subject.getPrincipals(GroupPrincipal.class)
                .iterator().next().getName());

        context.logout();
        System.out.println("After logout: " + subject.getPrincipals().size());
    }
}
~~~

Biên dịch/chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac JaasSubjectDemo.java
java JaasSubjectDemo
~~~

Kết quả stdout đúng với ví dụ:

~~~text
Login: OK
Principals: 2
User: mai
Group: report-readers
After logout: 0
~~~

Giải thích: `LoginContext` chọn `DemoLoginModule` theo tên cấu hình. `login()` đọc callback và xác thực dữ liệu giả; `commit()` chỉ đưa hai principal vào Subject khi xác thực thành công. `logout()` xóa đúng principal do module tạo, vì vậy Subject của ví dụ chỉ còn 0 principal. Trong một hệ nhiều module, không xóa bừa principal do module khác quản lý.

**Giới hạn:** Đây là ví dụ JAAS thuần JDK. Nó **chưa** tạo Spring Authentication hay authority Spring, không thực hiện kiểm chứng Kerberos/LDAP và không có cơ chế lưu password an toàn. Không triển khai `DemoLoginModule` trong sản phẩm thật.

## 6. AuthorityGranter: chuyển principal nhóm thành quyền Spring

Khi `LoginContext.login()` đã thành công, Spring JAAS provider lấy `LoginContext.getSubject().getPrincipals()` rồi hỏi các `AuthorityGranter`. Chỉ các role được chấp nhận mới được chuyển thành `JaasGrantedAuthority`.

Ví dụ một ứng dụng chỉ muốn cho phép hai nhóm đã xác minh:

~~~java
import java.security.Principal;
import java.util.Set;
import org.springframework.security.authentication.jaas.AuthorityGranter;

public final class TrustedGroupAuthorityGranter implements AuthorityGranter {

    @Override
    public Set<String> grant(Principal principal) {
        if (!(principal instanceof JaasSubjectDemo.GroupPrincipal group)) {
            return Set.of();
        }
        return switch (group.getName()) {
            case "report-readers" -> Set.of("ROLE_REPORT_READER");
            case "report-writers" -> Set.of("ROLE_REPORT_WRITER");
            default -> Set.of();
        };
    }
}
~~~

Đây là mảnh lớp Spring Security **dùng chung source/package với `JaasSubjectDemo` ở ví dụ trước**, hoặc phải import kiểu principal tương ứng. Với LoginModule sản xuất, hãy thay `JaasSubjectDemo.GroupPrincipal` bằng **class principal nhóm thật do module tin cậy phát ra**. Không map quyền chỉ theo `principal.getName()`, vì một user principal có thể trùng tên nhóm.

| Principal | Kết quả map | Phương thức Spring |
| --- | --- | --- |
| Group principal `report-readers` | `ROLE_REPORT_READER` | `hasRole("REPORT_READER")` |
| Group principal `report-writers` | `ROLE_REPORT_WRITER` | `hasAuthority("ROLE_REPORT_WRITER")` |
| User principal có tên `report-readers` | Tập rỗng | Không tự thành role nhóm |
| Group ngoài allowlist | Tập rỗng | Không được cấp quyền |
| Service principal/Kerberos principal | Tùy chính sách riêng; mặc định không map | Phải kiểm chứng kiểu và xuất xứ |

Trong cấu hình Spring mặc định, `hasRole("REPORT_READER")` kiểm tra authority `ROLE_REPORT_READER`. `AuthorityGranter` không phải phương thức tự tạo danh tính mới; nó chỉ ánh xạ **quyền** từ các principal JAAS đã có sau xác thực.

**Giữ nguyên nguyên tắc least privilege:** chưa xác minh group không được gán `ROLE_USER` một cách tùy tiện. Người dùng có thể đã xác thực thành công nhưng không có role cần thiết; Spring trả từ chối quyền phù hợp thay vì thay đổi kết quả login.

## 7. Tích hợp LoginModule có sẵn bằng DefaultJaasAuthenticationProvider

Khi doanh nghiệp đã có `LoginModule` được phê duyệt và có trên classpath, có thể dùng `DefaultJaasAuthenticationProvider` để tránh tự viết lại xác thực.

Dependencies Gradle Groovy trong ứng dụng Spring Boot Servlet:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

JAAS thuộc JDK, Spring JAAS adapter thuộc Spring Security. Nếu LoginModule nằm trong thư viện nội bộ, phải thêm dependency của thư viện đó và xác định callback/option theo hợp đồng của nó.

Tệp `JaasBridgeConfiguration.java` (mảnh cấu hình trong dự án Spring):

~~~java
package example.security;

import java.util.Map;
import javax.security.auth.login.AppConfigurationEntry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.authentication.jaas.AuthorityGranter;
import org.springframework.security.authentication.jaas.DefaultJaasAuthenticationProvider;
import org.springframework.security.authentication.jaas.memory.InMemoryConfiguration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class JaasBridgeConfiguration {

    @Bean
    DefaultJaasAuthenticationProvider jaasProvider(
            Environment properties, AuthorityGranter trustedGroupGranter) {
        String loginModuleClass =
                properties.getRequiredProperty("app.jaas.login-module-class");

        AppConfigurationEntry entry = new AppConfigurationEntry(
                loginModuleClass,
                AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                Map.of());

        DefaultJaasAuthenticationProvider provider =
                new DefaultJaasAuthenticationProvider();
        provider.setLoginContextName("LegacyBridge");
        provider.setConfiguration(new InMemoryConfiguration(
                Map.of("LegacyBridge", new AppConfigurationEntry[] {entry})));
        provider.setAuthorityGranters(
                new AuthorityGranter[] {trustedGroupGranter});
        return provider;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            DefaultJaasAuthenticationProvider jaasProvider) throws Exception {
        return http
                .authenticationProvider(jaasProvider)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**", "/login", "/error")
                        .permitAll()
                        .requestMatchers("/reports/**")
                        .hasRole("REPORT_READER")
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

Cách sử dụng:

- `app.jaas.login-module-class` là cấu hình triển khai chứa **tên đầy đủ của LoginModule thật**, chỉ do quản trị cung cấp; không lấy từ request/query. Module phải có constructor không đối số và triển khai `javax.security.auth.spi.LoginModule`.
- Bean `AuthorityGranter` do ứng dụng đăng ký thêm (ví dụ đánh dấu `@Component` trên lớp ánh xạ ở mục 6, sau khi điều chỉnh đúng package). Module thực tế phải trả về đúng kiểu group principal mà granter kiểm tra.
- `InMemoryConfiguration` định nghĩa tên context `LegacyBridge`; tên này cần trùng `provider.setLoginContextName("LegacyBridge")`. Cơ chế giúp inject cấu hình JAAS riêng thay vì phụ thuộc toàn bộ cấu hình JVM.
- Spring `formLogin` gửi `UsernamePasswordAuthenticationToken` vào chuỗi provider. Provider JAAS dùng tên/password callback để gọi `LoginContext.login()` rồi chuyển principal/authority thành token xác thực của Spring.
- `requestMatchers("/reports/**").hasRole("REPORT_READER")` chỉ cấp quyền khi thực sự có `ROLE_REPORT_READER`. Authentication thành công mà thiếu role vẫn bị từ chối.

Ví dụ bean này chưa phải chương trình chạy độc lập: nó **đòi LoginModule sản xuất, callback phù hợp, nguồn credential, chính sách authority và một Spring Boot application**. Không ghép module demo dùng password cố định vào production chỉ để kiểm tra flow.

### JaasAuthenticationProvider khi có tệp cấu hình JAAS

Một tệp `login.conf` truyền thống có thể có dạng:

~~~text
LegacyBridge {
    company.security.EnterpriseLoginModule required;
};
~~~

`company.security.EnterpriseLoginModule` trong mẫu là **tên lớp do tổ chức cung cấp**, không phải lớp có sẵn trong JDK. `JaasAuthenticationProvider` có `setLoginConfig(Resource)` và `setLoginContextName(...)` cho tích hợp dạng tệp. Với hệ chạy nhiều ứng dụng, cấu hình JAAS toàn JVM có thể khó cô lập; cần xác minh nơi lấy config, quyền sửa file và tác động lên các module khác.

## 8. JAAS LoginException không tự động là BadCredentialsException

JAAS thường báo lỗi xác thực hoặc hạ tầng qua `javax.security.auth.login.LoginException`, gồm subclass `FailedLoginException`. Spring yêu cầu `AuthenticationException` để xử lý. Trong Spring Security JAAS, `DefaultLoginExceptionResolver` **mặc định bọc lỗi JAAS thành `AuthenticationServiceException`**, nên không được mặc định rằng password sai luôn biến thành `BadCredentialsException`.

Có thể thêm một `LoginExceptionResolver` khi module có hợp đồng lỗi rõ ràng:

~~~java
import javax.security.auth.login.FailedLoginException;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.jaas.LoginExceptionResolver;

LoginExceptionResolver resolver = exception -> {
    if (exception instanceof FailedLoginException) {
        return new BadCredentialsException("Invalid credentials");
    }
    return new AuthenticationServiceException("JAAS login service failed",
            exception);
};
~~~

Đưa resolver vào bean provider bằng `provider.setLoginExceptionResolver(resolver)`. Mảnh mã này chỉ đúng nếu **LoginModule cụ thể dùng `FailedLoginException` nhất quán cho credentials không hợp lệ**. Một module dùng subclass đó cho mất KDC/network sẽ cần sửa phân loại ở module. Không dò chuỗi `exception.getMessage()` rồi quyết định quyền.

Bảng ngữ nghĩa:

| Kết quả thật | Xử lý Spring mong muốn |
| --- | --- |
| Username/password sai theo backend | `BadCredentialsException` nếu hợp đồng module xác nhận |
| Tài khoản bị khóa/hết hạn | Exception trạng thái phù hợp nếu module phân biệt được |
| Kerberos KDC lỗi, directory unavailable, timeout | `AuthenticationServiceException` hoặc loại infrastructure error |
| Module không tồn tại, sai tên login context, callback không hỗ trợ | Lỗi cấu hình/hệ thống, không cấp authenticated token |
| Login thành công nhưng group không được cho phép | Xác thực thành công, authorization chặn quyền thiếu |
| Exception bất kỳ khi đang xác thực | **Fail closed**: không tự cấp principal/role |

HTTP 401/403/5xx thực tế phụ thuộc login failure handler/entry point và quy tắc của API. Không xuất raw exception message, password, Kerberos ticket, Subject, stack trace hoặc private credential cho người dùng.

## 9. Subject.doAs và JaasApiIntegrationFilter

Một số thư viện kế thừa không nhận tham số user trực tiếp mà đọc **current JAAS Subject** trong lúc xử lý dữ liệu. Trường hợp này, Spring Authentication chỉ là bước xác thực/ủy quyền ở framework; code legacy vẫn có thể cần Subject.

Ví dụ JDK 17 trong **đoạn mã nằm trong một phương thức đã có biến subject và legacyService**:

~~~java
import java.security.PrivilegedAction;
import javax.security.auth.Subject;

String output = Subject.doAs(subject,
        (PrivilegedAction<String>) () -> legacyService.readData());
~~~

`Subject.doAs` tạo phạm vi thực thi đồng bộ dưới Subject đã có. Nó **không** biến Spring `SecurityContext` thành Subject và không tự gán role Spring. Trong Java 17, API này còn dùng được; từ JDK 18 nó được đánh dấu deprecated-for-removal. `Subject.getSubject(AccessController.getContext())` bị deprecated-for-removal từ JDK 17. JDK 18+ bổ sung `Subject.current()` và `Subject.callAs(...)`; khi nâng JDK cần kiểm tra cách thư viện legacy truy cập Subject và khả năng tương thích, không dựa vào Java Security Manager như một tính năng bảo mật luôn sẵn có.

### Filter tích hợp Subject với Servlet

Spring Security có `org.springframework.security.web.jaasapi.JaasApiIntegrationFilter`. Filter tìm Subject của `JaasAuthenticationToken` hiện tại và cố gắng chạy phần `FilterChain` phía sau dưới Subject đó, cho phép cả:

~~~text
Spring SecurityContext: Authentication + GrantedAuthority
JAAS current Subject:  UserPrincipal + GroupPrincipal (+ credentials)
~~~

Filter là **tùy chọn**; chỉ cần khi mã downstream thực sự đòi current Subject. Phải đặt trong `SecurityFilterChain` ở vị trí sao cho Spring đã xác thực trước khi mã legacy dùng Subject, và kiểm thử với request thật. Nếu request chưa có token JAAS, filter không thể tự dựng một Subject đã xác thực.

Với WebFlux, `JaasApiIntegrationFilter` là Servlet `Filter`, không phải `WebFilter`. Không đặt nó vào reactive stack và hy vọng Reactor tự giữ Subject khi đổi scheduler.

## 10. Giới hạn truyền ngữ cảnh qua thread, reactive và job

Phạm vi Subject trong `doAs` liên quan đến ngữ cảnh thực thi Java; Spring `SecurityContextHolder` trên Servlet thường gắn vào thread, còn `ReactiveSecurityContextHolder` gắn vào Reactor Context. Các cơ chế này **khác nhau**.

~~~text
Thread HTTP đã xác thực
    |
    +-- Subject.doAs(subject, code đồng bộ)
    |       -> legacy API có thể đọc current Subject
    |
    +-- CompletableFuture / ExecutorService
    |       -> thread khác; không bảo đảm có Subject hoặc SecurityContext
    |
    +-- WebFlux / Reactor publishOn
            -> thread khác; Reactor Context không tự là JAAS Subject
~~~

Có wrapper `DelegatingSecurityContextRunnable`/`DelegatingSecurityContextExecutor` để mang **Spring SecurityContext** trong một số trường hợp Servlet async, nhưng chúng không tự bảo đảm mang cả JAAS Subject. Muốn kế thừa Subject qua nhiệm vụ async, phải định nghĩa cách truyền một cách có kiểm soát, vòng đời và cleanup; tránh sao chép private credentials vào thread pool hoặc message queue.

Một `LoginModule` cũ có thể đồng bộ và chờ mạng (KDC, LDAP, HTTP). Trong WebFlux, đặt login blocking trực tiếp lên event-loop sẽ làm nghẽn request; muốn tích hợp phải cô lập blocking bằng scheduler thích hợp, có timeout và giới hạn tải. `Mono.just(loginContext.login())` không biến lời gọi blocking thành non-blocking. Thường chỉ nên dùng JAAS bridge khi có nhu cầu legacy cụ thể; ứng dụng reactive mới cần cân nhắc các authentication manager và driver tương thích reactor.

## 11. Vòng đời logout và dọn tài nguyên

Một `LoginContext` thường phục vụ **một lần đăng nhập**. Các `LoginModule` có thể tạo principal, session hoặc ticket; `LoginContext.logout()` được dùng để gọi cleanup. Đăng xuất khỏi Spring và đăng xuất khỏi JAAS là hai hợp đồng liên quan nhưng cần xác minh riêng.

Spring JAAS provider có xử lý `SessionDestroyedEvent`: với session hủy mà tìm được context chứa `JaasAuthenticationToken`, provider có thể gọi `LoginContext.logout()`. Tuy nhiên không được coi rằng đóng tab, xóa một cookie hoặc mọi cấu hình stateless/JWT đều kích hoạt cleanup giống nhau. Hãy test thực tế logout, session expiration, session registry, event publisher và hành vi của LoginModule.

Những rủi ro cần kiểm soát:

- Một Subject hoặc LoginContext bị chia sẻ giữa hai user trong thread pool.
- Credentials/ticket vẫn còn trong bộ nhớ quá lâu sau khi hết phiên.
- Logout một session làm hỏng session khác vì module quản lý tài nguyên process-wide.
- LoginModule thêm principal khi `login()` thất bại hoặc `abort()` không dọn.
- Spring session được xóa nhưng thư viện legacy vẫn giữ một reference Subject có quyền cao.
- Việc đổi group trong directory không ảnh hưởng session cũ vì authorities được cache đến hết phiên.

## 12. Khi nào nên dùng JAAS, khi nào chọn tích hợp khác?

| Tình huống | Lựa chọn phù hợp |
| --- | --- |
| Có LoginModule chuẩn JAAS bắt buộc tái sử dụng | `DefaultJaasAuthenticationProvider`/`JaasAuthenticationProvider` |
| Thư viện Kerberos/legacy cần current Subject | Cầu nối JAAS + phạm vi Subject được kiểm soát |
| Ứng dụng mới đăng nhập qua OIDC | `oauth2Login`/OIDC, không mặc định chuyển qua JAAS |
| REST API bảo vệ bằng access token | Spring OAuth2 Resource Server, xác minh token |
| Xác thực user/password qua JDBC hoặc LDAP thông thường | AuthenticationProvider chuyên dụng nếu phù hợp |
| WebFlux end-to-end non-blocking | Reactive AuthenticationManager và driver tương ứng; cân nhắc chi phí của legacy JAAS blocking |
| Chỉ muốn gắn role vào user | Dùng `GrantedAuthority` và policy Spring; không tạo Subject giả để đạt mục tiêu này |

JAAS chủ yếu giải quyết tích hợp một **cơ chế đăng nhập/caller identity có sẵn**, còn Spring Security vẫn là nơi điều phối security của HTTP request, method security và các authorization rules.

## 13. Kiểm thử đúng ranh giới và tránh cấp quyền nhầm

**Kiểm thử JAAS (độc lập Spring):**

- `LoginContext.login()` thành công với credentials test hợp lệ; Subject chứa các principal mong đợi.
- Credentials sai tạo lỗi, không có principal hay credential hợp lệ sau `abort()`.
- Mỗi user có Subject/LoginContext độc lập khi chạy song song.
- `logout()` loại đúng principal do module tạo; không xóa trạng thái thuộc module khác.
- Cấu hình sai tên context/module/class tạo lỗi cấu hình, không tự cho đăng nhập.

**Kiểm thử Spring JAAS bridge:**

- `AuthenticationManager.authenticate(...)` trả token đúng; `JaasAuthenticationToken` giữ LoginContext với Subject hợp lệ.
- `AuthorityGranter` chỉ cấp quyền cho đúng class principal **và** group trong allowlist, không cấp role từ username trùng tên group.
- Cùng một user: có thể đăng nhập thành công nhưng nhận 403 khi thiếu `ROLE_REPORT_READER`.
- Sai password và lỗi KDC/backend được phân loại đúng theo hợp đồng module, không bị gộp làm một lỗi.
- Kiểm tra login failure handler, session fixation protection, logout, expiry, concurrent sessions, audit và không rò credentials.
- Nếu bật `JaasApiIntegrationFilter`, downstream legacy API nhận Subject của đúng user, không có Subject đặc quyền cho anonymous request.
- Nếu có executor hoặc WebFlux, test context propagation và bảo đảm không lẫn danh tính giữa hai request.

Ví dụ unit test JUnit 5 cho granter ở mục 6, đặt cùng package/source test phù hợp:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TrustedGroupAuthorityGranterTest {
    private final TrustedGroupAuthorityGranter granter =
            new TrustedGroupAuthorityGranter();

    @Test
    void onlyTrustedGroupGetsRole() {
        assertEquals(java.util.Set.of("ROLE_REPORT_READER"),
                granter.grant(new JaasSubjectDemo.GroupPrincipal("report-readers")));
        assertTrue(granter.grant(
                new JaasSubjectDemo.UserPrincipal("report-readers")).isEmpty());
        assertTrue(granter.grant(
                new JaasSubjectDemo.GroupPrincipal("unknown")).isEmpty());
    }
}
~~~

Trong dự án đã có JUnit 5 và Gradle wrapper:

~~~bash
./gradlew test --tests TrustedGroupAuthorityGranterTest
~~~

Nếu các lớp nằm trong package `example.security`, phải khai báo package/import tương ứng và dùng tên test đầy đủ. Kết quả mong đợi: JUnit pass, không có stdout bắt buộc. Unit test này chỉ chứng minh phép map allowlist; vẫn cần integration test với LoginModule thật, JAAS provider, HTTP filter và backend.

## 14. Checklist production

- [ ] Thực sự có nhu cầu JAAS; đã xác định đúng LoginModule, callback, package/class và cách tạo Subject.
- [ ] LoginModule có nguồn danh tính đáng tin, không dùng hardcoded password hay module demo cho người dùng thật.
- [ ] Context name và `Configuration` cố định theo cấu hình triển khai tin cậy; không nhận tên LoginModule qua request.
- [ ] Không cấp role từ `Principal.getName()` khi chưa kiểm tra kiểu principal và allowlist group.
- [ ] `AuthorityGranter`, `hasRole`/`hasAuthority`, login failure và session policy được test cùng nhau.
- [ ] `LoginExceptionResolver` phản ánh đúng nguyên nhân: credentials, trạng thái account, lỗi backend/cấu hình; mọi lỗi đều fail closed.
- [ ] Current JAAS Subject chỉ được cung cấp khi thực sự cần, với filter/`doAs` tại đúng phạm vi.
- [ ] Nếu có async/WebFlux, không giả định truyền Subject hoặc Spring SecurityContext qua thread một cách tự động.
- [ ] Đã kiểm thử logout/session destroy/timeout và cleanup của LoginModule cho cả thành công/thất bại.
- [ ] Không log, serialize hoặc trả ra private credentials, password callback, ticket Kerberos hay Subject toàn bộ.
- [ ] Đã rà soát API JAAS bị deprecate khi cập nhật JDK và đo hiệu năng của LoginModule blocking.

**Điểm ghi nhớ:** JAAS **xác thực thông qua LoginModule và tạo Subject chứa nhiều Principal**; Spring Security **bảo vệ request bằng Authentication và GrantedAuthority**. `DefaultJaasAuthenticationProvider`/`JaasAuthenticationProvider` cùng `AuthorityGranter` tạo cầu nối giữa hai mô hình. `JaasApiIntegrationFilter` chỉ cần cho ứng dụng legacy thật sự sử dụng current JAAS Subject. Tính an toàn đến từ nguồn principal đáng tin, mapping có giới hạn, quản lý vòng đời và ngữ cảnh thực thi.

## Tài liệu đối chiếu

- [Spring Security 6.5 — JAAS Authentication Provider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/jaas.html)
- [Spring Security 6.5 — AbstractJaasAuthenticationProvider API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authentication/jaas/AbstractJaasAuthenticationProvider.html)
- [Spring Security 6.5 — DefaultJaasAuthenticationProvider API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authentication/jaas/DefaultJaasAuthenticationProvider.html)
- [Spring Security 6.5 — AuthorityGranter API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authentication/jaas/AuthorityGranter.html)
- [Spring Security 6.5 — DefaultLoginExceptionResolver API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authentication/jaas/DefaultLoginExceptionResolver.html)
- [Java 17 — LoginContext API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/LoginContext.html)
- [Java 17 — LoginModule API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/spi/LoginModule.html)
- [Java 21 — Subject API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/Subject.html)
