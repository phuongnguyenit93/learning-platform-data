# Đối chiếu bằng chứng với nguồn danh tính đáng tin cậy trong AuthenticationProvider tùy chỉnh

> **Mục tiêu:** Khi tự viết **AuthenticationProvider** cho Spring Security, phải xác minh bằng chứng do client cung cấp với **nguồn danh tính do phía server tin cậy và quản lý**, sau đó mới tạo **Authentication đã xác thực**. Việc client tự khai username, user ID, role hoặc token trông có vẻ hợp lệ **không đủ** để kết luận người đó là ai.

## 1. “Bằng chứng” và “nguồn danh tính đáng tin cậy” là gì?

**Bằng chứng xác thực (authentication evidence/credential)** là dữ liệu mà bên muốn đăng nhập cung cấp để chứng minh quyền sở hữu hoặc quyền kiểm soát một danh tính. Tùy cơ chế, đó có thể là mật khẩu, API key, assertion có chữ ký, token truy cập, chứng chỉ client hoặc mã OTP.

**Nguồn danh tính đáng tin cậy (trusted identity source)** là nơi phía server có căn cứ để biết danh tính và trạng thái của chủ thể: bảng tài khoản do server quản trị, kho mật khẩu đã băm, LDAP/AD được bảo vệ, IdP, kho khóa xác minh chữ ký, hệ thống quản lý chứng chỉ hoặc dịch vụ xác thực nội bộ có hợp đồng và kết nối an toàn. “Đáng tin cậy” đòi hỏi kiểm soát **nguồn gốc, tính toàn vẹn, cách cập nhật, quyền truy cập, độ mới và trạng thái thu hồi**. Một JSON payload do client gửi, một header tự khai **X-User-Id**, hoặc kết quả giải mã Base64 không tự trở thành nguồn tin cậy.

Ví dụ: client gửi cặp **alice / demo-pass**. Server tra cứu bản ghi tài khoản **alice** ở kho được quản lý, lấy **password hash** và trạng thái tài khoản, rồi dùng **PasswordEncoder.matches(raw, storedHash)**. Chỉ khi so khớp đúng và tài khoản được phép hoạt động, provider mới tạo principal và authorities **từ dữ liệu phía server**. Nếu client gửi thêm **ROLE_ADMIN**, provider phải bỏ qua quyền tự khai ấy.

### Điều gì được kiểm tra?

| Câu hỏi | Nếu có kiểm tra đúng | Nếu bị bỏ qua |
| --- | --- | --- |
| Bằng chứng này thuộc về danh tính nào? | Lookup hoặc verify gắn bằng chứng với subject có định danh ổn định | Kẻ tấn công có thể tự nhận subject khác |
| Bằng chứng có hợp lệ về mặt kỹ thuật? | So khớp hash, chữ ký, chứng chỉ hoặc giao thức xác thực thích hợp | Chấp nhận dữ liệu chưa được kiểm chứng |
| Ai cấp/phát hành bằng chứng? | Chỉ tin issuer, server, directory hoặc khóa nằm trong trust configuration | Tin token do bất kỳ ai tạo |
| Bằng chứng có dành cho ứng dụng này? | Kiểm tra audience, mục đích sử dụng và ngữ cảnh theo loại token | Nhận token cấp cho dịch vụ khác |
| Bằng chứng còn hiệu lực? | Kiểm tra hết hạn, chưa có hiệu lực, thu hồi, trạng thái chủ thể | Dùng credential quá hạn hoặc bị khóa |
| Chủ thể được quyền gì? | Lấy role/permission từ nguồn có thẩm quyền | Leo thang quyền nhờ trường do client tự gửi |
| Nguồn tin cậy có truy cập được không? | Từ chối xác thực an toàn và báo sự cố phù hợp | Tự động cho phép hoặc dùng dữ liệu chưa xác minh |

**Authentication** (xác định “ai”) và **authorization** (quyết định “được làm gì”) là hai bước khác nhau. Provider phải tạo danh tính đáng tin để các bước phân quyền dùng; không coi việc đã chứng minh danh tính là được phép truy cập mọi tài nguyên.

## 2. Cơ chế trong Spring Security: filter → manager → provider

~~~text
HTTP request
  |
  | Username/password, token hoặc credential phù hợp
  v
Authentication filter
  |
  | Tạo Authentication yêu cầu xác thực
  | (thường isAuthenticated=false)
  v
AuthenticationManager / ProviderManager
  |
  | Chọn AuthenticationProvider qua supports(...)
  v
Custom AuthenticationProvider
  |
  +--> Kiểm tra loại token và định dạng bằng chứng
  |
  +--> Tra nguồn danh tính server kiểm soát
  |       +--> nguồn lỗi/không tin cậy --> thất bại an toàn
  |
  +--> Đối chiếu bằng chứng với dữ liệu tin cậy
  |       +--> không khớp / tài khoản khóa --> AuthenticationException
  |
  +--> Lấy subject và authorities đã xác minh từ nguồn tin cậy
  |
  +--> Trả Authentication đã xác thực
  v
SecurityContext / Security filter chain
  |
  v
Authorization: kiểm tra ROLE_/authority của endpoint
~~~

Trong Spring Security Servlet:

- **Authentication** chứa principal, credentials, authorities, details và trạng thái xác thực. Ở đầu vào, các trường có thể do client hoặc filter xây dựng, nên chưa được tin cậy.
- **AuthenticationProvider.supports(Class<?>)** xác định provider có khả năng xử lý loại Authentication nào. Nó **không** có nghĩa credential đã hợp lệ.
- **AuthenticationProvider.authenticate(Authentication)** thực hiện kiểm tra. Khi thành công, trả một Authentication đã xác thực, thường mang principal và authorities đã xác minh; khi sai, ném **AuthenticationException** phù hợp; khi provider không xử lý được kiểu token, có thể trả null để manager thử provider khác.
- **ProviderManager** có thể phối hợp nhiều provider. Không nên cấu hình một provider “dự phòng” chấp nhận mọi credential khi provider chính lỗi, vì việc đó mở đường vượt xác thực.
- **SecurityContextHolder** giữ Authentication mà filter hoặc code ứng dụng đặt vào ngữ cảnh sau khi xác thực thành công. Tự đưa một Authentication được đánh dấu đã xác thực vào context mà không kiểm tra bằng chứng là lỗi bảo mật nghiêm trọng.

**Bất biến quan trọng:** chỉ nhánh đã xác minh hợp lệ mới tạo Authentication có **isAuthenticated() == true**. Danh tính và role đưa vào Authentication phải đến từ nguồn tin cậy, không sao chép authority ở request.

### Phân biệt các kết quả của provider

| Kết quả | Nghĩa | Cách xử lý |
| --- | --- | --- |
| Trả Authentication đã xác thực | Bằng chứng hợp lệ, danh tính được phép đăng nhập | Tiếp tục phân quyền |
| Ném **BadCredentialsException** | Mật khẩu/credential không đúng hoặc không thể xác nhận danh tính; phản hồi ngoài thường dùng thông điệp chung | Từ chối đăng nhập, theo dõi thử sai |
| Ném **DisabledException** hoặc **LockedException** | Trạng thái tài khoản không cho phép đăng nhập, nếu hợp đồng cho phép phân biệt nội bộ | Từ chối; tránh làm lộ sự tồn tại của username ra client |
| Ném **AuthenticationServiceException** | Không thể kiểm tra với nguồn tin cậy do sự cố hệ thống | Từ chối an toàn, ghi nhận sự cố và xử lý lỗi dịch vụ |
| Trả **null** | Provider không quyết định đối với token này | Manager có thể thử provider khác |
| **ProviderNotFoundException** | Không provider nào hỗ trợ token | Kiểm tra cấu hình manager/provider và kiểu token |

Không nên bắt mọi exception rồi trả “đăng nhập thành công”; cũng không nên biến lỗi mất kết nối directory thành “mật khẩu sai” trong log nội bộ. **Phản hồi HTTP** phụ thuộc filter và **AuthenticationEntryPoint**: ví dụ HTTP Basic mặc định có thể trả 401 cho cả lỗi AuthenticationServiceException. Nếu ứng dụng muốn trả 503 khi kho danh tính gián đoạn, phải cấu hình rõ entry point và hợp đồng API, thay vì giả định exception tự động thành 503.

## 3. Ví dụ hoàn chỉnh: custom provider kiểm tra password với trusted directory

Ví dụ sử dụng **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC (Servlet)**. Ứng dụng tạo từ Spring Initializr với dependency **Spring Web**, **Spring Security** và **Spring Boot Starter Test** để chạy bài kiểm thử. Mã nguồn mẫu dùng package **com.example.demo**; lưu mỗi public class/record/interface vào đúng tên file dưới **src/main/java/com/example/demo/**. Class **DemoApplication** do Initializr tạo sẵn.

Để tập trung vào cách kiểm tra bằng chứng, ta dùng **HTTP Basic** làm phương tiện nhận username/password rồi chuyển sang **AuthenticationManager**. Trong production, phải dùng **HTTPS** cho tất cả request mang mật khẩu; HTTP ở localhost phía dưới chỉ dành cho thực hành. Provider được viết có thể phục vụ cơ chế nhận username/password khác khi filter tạo đúng loại token.

**Thiết kế ví dụ:** một **TrustedIdentitySource** ở phía server lưu bản ghi chứa subject ID, username, BCrypt hash, trạng thái active và authorities. Client chỉ biết username/password. Custom provider so khớp bằng chứng và lấy quyền từ bản ghi đáng tin.

### 3.1. Mô hình bản ghi danh tính

Tệp **TrustedIdentity.java**:

~~~java
package com.example.demo;

import java.util.Set;

public record TrustedIdentity(
        String subjectId,
        String username,
        String passwordHash,
        boolean active,
        Set<String> authorities) {
}
~~~

**subjectId** là khóa nội bộ ổn định. **username** có thể đổi theo chính sách; không nên dùng username làm khóa bất biến cho mọi quan hệ dữ liệu. **passwordHash** là kết quả băm do server lưu, không phải giá trị client gửi. **authorities** phải do nguồn tin cậy cung cấp, ví dụ **ROLE_READER**. Chỉ đánh dấu **active=true** khi trạng thái tài khoản được phép xác thực.

Định nghĩa hợp đồng truy vấn trong **TrustedIdentitySource.java**:

~~~java
package com.example.demo;

import java.util.Optional;

public interface TrustedIdentitySource {
    Optional<TrustedIdentity> findByUsername(String username);
}
~~~

Tên interface nhấn mạnh ranh giới trách nhiệm: provider hỏi nguồn danh tính có thẩm quyền; source có thể dùng database, directory hoặc adapter tới dịch vụ nội bộ. **Optional.empty()** đại diện không tìm thấy người dùng. Lỗi nguồn truy cập không được giả thành một bản ghi hợp lệ.

### 3.2. Nguồn dữ liệu demo chỉ do server quản lý

Tệp **InMemoryTrustedIdentitySource.java**:

~~~java
package com.example.demo;

import java.util.Map;
import java.util.Optional;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public class InMemoryTrustedIdentitySource
        implements TrustedIdentitySource {

    private final Map<String, TrustedIdentity> identities;

    public InMemoryTrustedIdentitySource(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String demoPassword) {

        TrustedIdentity alice = new TrustedIdentity(
                "user-1001",
                "alice",
                encoder.encode(demoPassword),
                true,
                Set.of("ROLE_READER"));

        identities = Map.of("alice", alice);
    }

    @Override
    public Optional<TrustedIdentity> findByUsername(String username) {
        return Optional.ofNullable(identities.get(username));
    }
}
~~~

**InMemoryTrustedIdentitySource** chỉ là mô phỏng một nguồn được server quản lý, để bài học không cần database hoặc LDAP. Trong ứng dụng thật, bản ghi đến từ kho dữ liệu được bảo vệ và kiểm soát ai có quyền tạo/sửa tài khoản, trạng thái và quyền. Không dùng biến môi trường mật khẩu demo làm hệ thống lưu trữ tài khoản thực tế; với database, lưu **hash** chứ không lưu mật khẩu rõ.

**Lưu ý về trust boundary:** **username** dùng làm khóa tra cứu là một đầu vào chưa được tin, nhưng **bản ghi trả về** mới là nguồn chứa subject, hash và authorities có thẩm quyền. Không bao giờ đưa một trường **authorities** từ body/header của client thành role chỉ vì source trả về user trùng tên.

### 3.3. Principal chỉ chứa danh tính đã xác minh

Tệp **VerifiedPrincipal.java**:

~~~java
package com.example.demo;

import java.security.Principal;

public record VerifiedPrincipal(
        String subjectId, String username) implements Principal {

    @Override
    public String getName() {
        return username;
    }
}
~~~

Principal không giữ mật khẩu rõ, hash, API key hoặc các trường nội bộ không cần thiết. Vì implementing **Principal**, nó cung cấp tên được **Authentication.getName()** sử dụng; subjectId giúp ứng dụng tham chiếu danh tính ổn định.

### 3.4. Viết AuthenticationProvider thực hiện đối chiếu

Tệp **TrustedPasswordAuthenticationProvider.java**:

~~~java
package com.example.demo;

import java.util.Optional;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public class TrustedPasswordAuthenticationProvider
        implements AuthenticationProvider {

    private final TrustedIdentitySource identities;
    private final PasswordEncoder encoder;

    public TrustedPasswordAuthenticationProvider(
            TrustedIdentitySource identities,
            PasswordEncoder encoder) {
        this.identities = identities;
        this.encoder = encoder;
    }

    @Override
    public Authentication authenticate(Authentication request)
            throws AuthenticationException {

        // Chỉ nhận token username/password; không tự tin kiểu token khác.
        if (!(request instanceof UsernamePasswordAuthenticationToken)) {
            return null;
        }

        String username = request.getName();
        Object credential = request.getCredentials();

        if (username == null
                || username.isBlank()
                || username.length() > 128
                || !(credential instanceof String rawPassword)
                || rawPassword.isBlank()) {
            throw new BadCredentialsException("Invalid credentials");
        }

        // Dữ liệu này phải đến từ source do server kiểm soát.
        Optional<TrustedIdentity> found;
        try {
            found = identities.findByUsername(username);
        } catch (RuntimeException ex) {
            // Lỗi nguồn danh tính không phải bằng chứng đăng nhập hợp lệ.
            throw new AuthenticationServiceException(
                    "Trusted identity source unavailable", ex);
        }

        if (found.isEmpty()) {
            throw new BadCredentialsException("Invalid credentials");
        }

        TrustedIdentity identity = found.get();

        if (!identity.active()
                || !encoder.matches(rawPassword, identity.passwordHash())) {
            throw new BadCredentialsException("Invalid credentials");
        }

        // Chỉ dùng quyền từ bản ghi đã xác minh, bỏ qua role ở đầu vào.
        var authorities = identity.authorities().stream()
                .map(SimpleGrantedAuthority::new)
                .toList();

        var verified = UsernamePasswordAuthenticationToken.authenticated(
                new VerifiedPrincipal(
                        identity.subjectId(), identity.username()),
                null,
                authorities);

        verified.setDetails(request.getDetails());
        return verified;
    }

    @Override
    public boolean supports(Class<?> tokenType) {
        return UsernamePasswordAuthenticationToken.class
                .isAssignableFrom(tokenType);
    }
}
~~~

**Diễn giải theo đúng thứ tự bảo mật:**

1. **supports(...)** và kiểm tra kiểu token trong **authenticate(...)** xác nhận provider đang xử lý loại bằng chứng đã thiết kế. Đây chưa phải xác thực danh tính.
2. Kiểm tra username/password đủ cấu trúc trước khi đụng tới nguồn bên ngoài. Giới hạn độ dài username là ví dụ để tránh đầu vào bất thường; chính sách thực tế phải nhất quán với hệ thống quản lý username.
3. **identities.findByUsername(...)** hỏi đúng nguồn phía server. Nếu nguồn không hoạt động, ném **AuthenticationServiceException** để fail closed. Không tự bỏ qua kiểm tra.
4. Không tìm thấy người dùng, tài khoản bị vô hiệu hoặc mật khẩu không khớp đều bị từ chối qua **BadCredentialsException** có nội dung chung. Ứng dụng thực tế cần chú ý khác biệt thời gian xử lý có thể tiết lộ trạng thái tài khoản; có thể dùng đường kiểm tra giả hợp lý và rate limiting sau khi đánh giá tải.
5. **encoder.matches(rawPassword, identity.passwordHash())** dùng mật khẩu do client nhập so sánh với **BCrypt hash** do source lưu. Không so sánh trực tiếp password rõ với string hash.
6. **authorities** được tạo từ **identity.authorities()**. Provider không sao chép **request.getAuthorities()**, không tin quyền client tự gửi.
7. Chỉ sau khi mọi bước qua kiểm tra, provider tạo **UsernamePasswordAuthenticationToken.authenticated(...)** và gắn **VerifiedPrincipal** với credentials là **null**. Điều này hạn chế giữ lại mật khẩu trong object sau xác thực.

**Vì sao trả null khi không hỗ trợ kiểu token?** Theo hợp đồng AuthenticationProvider, provider có thể để manager thử provider khác. Trong hệ thống nhiều cơ chế, phải kiểm soát kỹ nhà cung cấp tiếp theo. Đặc biệt, một provider đã nhận token username/password nhưng credential sai phải **ném AuthenticationException**, không được trả null tùy tiện chỉ để provider yếu hơn chấp nhận.

**Giới hạn của đoạn code:** Trường hợp không tìm thấy username bị từ chối sớm, khác biệt thời gian so với BCrypt là điều cần đánh giá khi triển khai thật. Ví dụ cũng chưa có rate limiting, lockout, auditing, connection timeout vì chưa dùng remote directory; đây là các lớp bảo vệ cần bổ sung ở môi trường thực.

### 3.5. Đăng ký provider vào SecurityFilterChain

Tệp **SecurityConfig.java**:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            TrustedPasswordAuthenticationProvider provider)
            throws Exception {
        return http
                .authenticationProvider(provider)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .build();
    }
}
~~~

**http.authenticationProvider(provider)** đăng ký provider vào cơ chế AuthenticationManager dành cho security chain. **httpBasic(...)** thêm filter chuyển header Basic thành **UsernamePasswordAuthenticationToken** để manager gửi tới provider. **hasRole("ADMIN")** kiểm tra quyền **ROLE_ADMIN**; người dùng mẫu chỉ có **ROLE_READER**, do đó gọi API admin phải bị **403** dù mật khẩu đúng. Cấu hình không tắt CSRF; những HTTP method thay đổi trạng thái còn cần đánh giá CSRF, đặc biệt khi client là trình duyệt.

**Không dùng** cấu hình tạo tài khoản mặc định, không gắn vai trò **ROLE_ADMIN** tùy tiện và không tạo **Authentication** đã được xác thực trong controller từ input chưa kiểm chứng.

### 3.6. API xác nhận principal và quyền

Tệp **ProfileController.java**:

~~~java
package com.example.demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    public record Profile(String subjectId, String username) {}

    @GetMapping("/api/me")
    public Profile me(Authentication authentication) {
        VerifiedPrincipal user =
                (VerifiedPrincipal) authentication.getPrincipal();

        return new Profile(user.subjectId(), user.username());
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin ok";
    }
}
~~~

Trong ví dụ, mọi request tới **/api/me** đã phải qua xác thực, nên **getPrincipal()** là VerifiedPrincipal do provider tạo. Khi có nhiều cơ chế đăng nhập trong một ứng dụng, đừng giả định mọi principal luôn cùng kiểu; adapter/controller nên xử lý kiểu hợp lệ theo thiết kế.

### 3.7. Khởi động và kiểm tra bằng curl

Trong **src/main/resources/application.properties**:

~~~properties
server.port=8080
demo.user.password=${DEMO_USER_PASSWORD}
~~~

Ở Linux/macOS:

~~~bash
export DEMO_USER_PASSWORD=demo-pass
./mvnw spring-boot:run
~~~

Ở Windows PowerShell:

~~~powershell
$env:DEMO_USER_PASSWORD = "demo-pass"
.\mvnw.cmd spring-boot:run
~~~

Các lệnh dưới đây dùng mật khẩu giả **demo-pass** và HTTP ở **localhost** để minh họa. Với môi trường thật, phải sử dụng HTTPS, bảo vệ biến môi trường/secret, không để mật khẩu thật xuất hiện trong shell history hoặc process list; có thể dùng cơ chế nhập mật khẩu không hiện lộ của công cụ client.

Yêu cầu hợp lệ:

~~~bash
curl -i -u alice:demo-pass http://localhost:8080/api/me
~~~

Kỳ vọng **200 OK** với JSON có nội dung:

~~~json
{
  "subjectId": "user-1001",
  "username": "alice"
}
~~~

Sai mật khẩu:

~~~bash
curl -i -u alice:wrong http://localhost:8080/api/me
~~~

Kỳ vọng **401 Unauthorized** (HTTP Basic yêu cầu chứng thực lại). Một username không tồn tại cũng phải không được xác thực, ví dụ:

~~~bash
curl -i -u unknown:demo-pass http://localhost:8080/api/me
~~~

Kỳ vọng **401 Unauthorized**, không phát sinh principal đáng tin. Mặc dù cùng mã status, thời gian thực thi giữa username không tồn tại và password sai có thể khác trong ví dụ; đây là lý do cần kiểm thử enumeration và bổ sung kiểm soát khi đưa vào production.

Dùng credential hợp lệ nhưng không có quyền admin:

~~~bash
curl -i -u alice:demo-pass http://localhost:8080/api/admin
~~~

Kỳ vọng **403 Forbidden**. Đây là khác biệt cốt lõi giữa *đã xác thực đúng danh tính* và *được cấp quyền thực hiện thao tác*. HTTP Basic còn có thể trả **WWW-Authenticate** khi báo 401; header này là đặc điểm giao thức, không phải dấu hiệu token đã được xác minh.

### 3.8. Kiểm thử provider độc lập bằng JUnit

Nếu project có **spring-boot-starter-test**, thêm tệp **src/test/java/com/example/demo/TrustedPasswordAuthenticationProviderTest.java**:

~~~java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@SpringBootTest(properties = "demo.user.password=demo-pass")
class TrustedPasswordAuthenticationProviderTest {

    @Autowired
    TrustedPasswordAuthenticationProvider provider;

    @Test
    void validEvidenceCreatesTrustedPrincipal() {
        var request = UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-pass");

        var result = provider.authenticate(request);

        assertNotNull(result);
        assertTrue(result.isAuthenticated());
        assertEquals("alice", result.getName());
        assertEquals("user-1001",
                ((VerifiedPrincipal) result.getPrincipal()).subjectId());
        assertNull(result.getCredentials());
        assertTrue(result.getAuthorities().stream()
                .anyMatch(a -> a.getAuthority().equals("ROLE_READER")));
    }

    @Test
    void invalidPasswordIsRejected() {
        var request = UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "wrong");

        assertThrows(BadCredentialsException.class,
                () -> provider.authenticate(request));
    }

    @Test
    void missingUserIsRejected() {
        var request = UsernamePasswordAuthenticationToken.unauthenticated(
                "unknown", "demo-pass");

        assertThrows(BadCredentialsException.class,
                () -> provider.authenticate(request));
    }

    @Test
    void ClientCannotChooseTheirOwnRole() {
        var forged = new UsernamePasswordAuthenticationToken(
                "alice",
                "demo-pass",
                List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));

        var result = provider.authenticate(forged);

        assertNotNull(result);
        assertTrue(result.getAuthorities().stream()
                .noneMatch(a -> a.getAuthority().equals("ROLE_ADMIN")));
        assertTrue(result.getAuthorities().stream()
                .anyMatch(a -> a.getAuthority().equals("ROLE_READER")));
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

PowerShell dùng **.\mvnw.cmd test**. Test cuối tạo một request token đã mang quyền giả **ROLE_ADMIN**. Provider vẫn lấy quyền từ trusted source nên kết quả chỉ là **ROLE_READER**. Đây là kiểm tra trực tiếp chống việc tin dữ liệu quyền do bên gọi tự khai. Test này kiểm chứng chính provider; ở luồng request thực tế, filter phải tạo token đầu vào đúng loại và không cho client tự quyết định đối tượng Authentication.

Nếu đã có hệ thống test với **MockMvc** và **spring-security-test**, nên bổ sung kiểm thử HTTP end-to-end: đúng credential → 200, sai credential → 401, đúng credential nhưng thiếu role → 403, lỗi source → không bao giờ 200.

## 4. Thay nguồn dữ liệu demo bằng nguồn danh tính thực

Cách kiểm chứng phụ thuộc loại **bằng chứng**, không phải cứ dùng một hàm so sánh chuỗi là đủ.

| Bằng chứng | Nguồn tin cậy | Kiểm tra đúng | Tránh sai lầm |
| --- | --- | --- | --- |
| **Username/password** | Bản ghi tài khoản/LDAP có quyền truy cập kiểm soát | Với hash server lưu: **PasswordEncoder.matches**; với LDAP dùng cơ chế xác thực directory phù hợp | So sánh plaintext hoặc tin flag “passwordValid” do client gửi |
| **API key** | Kho key do server cấp, quản lý chủ thể, scope và trạng thái | Lookup an toàn, đối chiếu giá trị/hash theo thiết kế, hết hạn/thu hồi | Để key trong log, URL; coi key ID như key bí mật |
| **JWT access token** | Issuer có thẩm quyền, bộ khóa ký/cấu hình trust đáng tin | Kiểm tra chữ ký, thuật toán cho phép, issuer, audience, thời gian, phạm vi sử dụng và chính sách thu hồi khi cần | Chỉ Base64-decode payload, bỏ qua chữ ký hoặc chấp nhận alg không mong muốn |
| **OIDC ID token** | OpenID Provider đáng tin | Xác minh các điều kiện đặc thù ID token theo flow, client, nonce khi áp dụng | Dùng ID token làm access token của API tùy tiện |
| **SAML assertion** | Identity Provider đã thiết lập trust | Kiểm tra chữ ký, issuer, audience, thời gian, recipient, replay theo profile | Lấy NameID từ XML chưa được xác minh |
| **mTLS client certificate** | Chuỗi CA tin cậy và mapping danh tính server quản lý | TLS xác minh cert; ánh xạ SAN/subject theo chính sách, trạng thái chứng chỉ khi cần | Tin header chứng chỉ tự khai từ Internet |
| **OTP / mã xác nhận** | Secret/challenge do server phát hành và lưu an toàn | Thời gian hiệu lực, gắn đúng user và giao dịch, chống replay, giới hạn thử sai | Chấp nhận OTP không gắn subject hoặc cho dùng lại |

Đối với JWT/OIDC/SAML, ưu tiên **thành phần thư viện và cấu hình chuẩn** của Spring Security hoặc middleware chuyên trách. Tự viết mã kiểm tra chữ ký và thuật toán mật mã rất dễ tạo lỗ hổng. Với LDAP, thường nên dùng **LdapAuthenticationProvider** và cấu hình LDAPS/StartTLS đúng cách thay vì viết lại phương thức bind. Custom provider phù hợp khi giao thức bằng chứng, nguồn danh tính hoặc quy tắc kiểm chứng thực sự khác các provider có sẵn.

### 4.1. Ví dụ trust boundary với JWT

Một JWT gồm ba phần ngăn bởi dấu chấm, phần payload có thể được bất kỳ ai **decode** để đọc claims. Ví dụ claim:

~~~json
{
  "sub": "user-1001",
  "iss": "https://idp.example.com",
  "aud": "my-api",
  "role": "ADMIN",
  "exp": 1900000000
}
~~~

Các giá trị đó chỉ trở thành dữ liệu đáng tin **sau** khi server xác minh chữ ký bằng khóa đúng, chính sách thuật toán, issuer, audience, thời gian và các điều kiện liên quan. Đừng cấp quyền ADMIN chỉ vì payload có trường **role**. Cần thêm một quy tắc mapping authority được tin cậy và đánh giá có cho phép issuer cấp role đó hay không.

JWT có thể được ký bằng khóa hợp lệ nhưng phát hành cho **dịch vụ khác**; nếu không kiểm tra **audience**, API có thể chấp nhận token không dành cho mình. Một khóa JWKS lấy từ URL do client chỉ định cũng không phải trust anchor; server phải kiểm soát issuer/JWKS URL hợp lệ qua cấu hình đã kiểm chứng.

### 4.2. Ví dụ trust boundary với nguồn remote

Khi **TrustedIdentitySource** gọi một hệ thống danh tính qua HTTP/gRPC:

1. Xác thực **đúng endpoint nguồn** bằng TLS/certificate; nếu cần dùng mTLS hoặc credential máy–máy để xác nhận quyền gọi.
2. Đặt timeout kết nối và timeout phản hồi; giới hạn retry, đặc biệt không retry vô hạn đối với một request login.
3. Xác minh hợp đồng response: subject ID, active/locked, version, authorities và nguồn phát hành không thể chỉ là dữ liệu do client truyền qua.
4. Mất kết nối, lỗi 5xx hoặc response không xác minh được phải **fail closed**. Không có “fallback accept” hoặc đọc role từ request để tiếp tục.
5. Phân biệt lỗi **invalid credentials** với lỗi **identity service unavailable** trong telemetry; response công khai không nên làm lộ bí mật hay cấu trúc hệ thống.
6. Dữ liệu cache có thể làm role/quyền bị cũ; quyết định TTL, xử lý revoke/disable và tính nhất quán theo rủi ro. Không cache raw password hoặc token có thể bị tái sử dụng.

Nguồn tin cậy không có nghĩa luôn sẵn sàng. Cần giám sát độ trễ, tỷ lệ từ chối, tỷ lệ lỗi nguồn, timeout, khối lượng thử mật khẩu và chính sách khóa/khôi phục. Một lần từ chối vì mạng lỗi không được tính nhầm thành bằng chứng mật khẩu sai nếu hệ thống thực thi lockout theo số lần sai.

## 5. Các ràng buộc bảo mật không thể bỏ qua

### 5.1. Bảo vệ bí mật khi truyền và khi lưu

- Dùng **HTTPS/TLS** với chứng chỉ hợp lệ cho client → server và kết nối tới directory/IdP. Base64 trong HTTP Basic không mã hóa mật khẩu.
- Chỉ lưu hash mật khẩu theo thuật toán phù hợp (BCrypt, Argon2id hoặc lựa chọn được bộ phận bảo mật chấp thuận); sử dụng encoder để so khớp. Không tự hash một lần bằng SHA-256 rồi coi là password hashing đủ mạnh.
- Không log **Authorization**, raw password, access token, API key, hash bí mật hoặc dữ liệu nhạy cảm trong exception, trace và audit event.
- Áp dụng rate limiting, theo dõi credential stuffing, chính sách khóa thích hợp; tránh để BCrypt workload trở thành điểm bị lạm dụng từ chối dịch vụ.
- Loại bỏ credential khỏi Authentication sau xác thực; nếu dùng ProviderManager, hiểu cơ chế **eraseCredentialsAfterAuthentication** và tránh chia sẻ mutable credentials với cache.

### 5.2. Chống user enumeration và timing oracle

Đừng gửi ra ngoài thông báo khác nhau như **“Username không tồn tại”** và **“Password sai”** nếu việc đó giúp attacker đoán tài khoản. Cùng trả mã/thông điệp chung cho credential không hợp lệ và tài khoản không được phép đăng nhập nếu chính sách yêu cầu. Tuy nhiên, chỉ thống nhất message **chưa đủ**: khác biệt thời gian lookup và băm có thể tiết lộ trạng thái. Đánh giá dùng hash giả/constant-work khi hợp lý, kết hợp rate limiting, và không mở một phép tính băm đắt đỏ không kiểm soát cho mọi yêu cầu.

### 5.3. Tránh lỗ hổng do chuỗi provider

Nếu nhiều provider cùng hỗ trợ **UsernamePasswordAuthenticationToken**, manager có thể thử tiếp tùy kết quả, loại exception và cấu hình. Đảm bảo không có provider yếu hơn chấp nhận bằng chứng mà provider an toàn đã từ chối. Khi cơ chế khác nhau thực sự, nên dùng **Authentication token type riêng** với supports chính xác và tránh thiết lập parent AuthenticationManager ngoài dự kiến.

Provider không được đánh dấu thành công chỉ vì request đã có **isAuthenticated=true** hay principal có tên hợp lệ; request token là đầu vào chưa tin. Ví dụ ở phần 3 vẫn kiểm tra credential ngay cả khi request giả có sẵn authorities.

### 5.4. Đừng bỏ qua trạng thái thu hồi

Một mật khẩu đúng không tự có nghĩa tài khoản vẫn được phép đăng nhập. Kiểm tra trạng thái **active/locked/expired**, chính sách hết hạn mật khẩu nếu áp dụng, quyền còn hiệu lực và tình trạng credential bị thu hồi. Với token có hạn dùng ngắn, cân bằng khả năng thu hồi với chi phí truy vấn; với session có tuổi thọ dài, đánh giá refresh authorities hoặc invalidate khi tài khoản bị khóa.

### 5.5. Không trộn xác thực và phân quyền

Provider xác minh ai đang gọi; **AuthorizationFilter** hoặc cơ chế method security quyết định họ được phép gọi gì. Role trả về phải gắn với subject đã kiểm tra. Không nâng quyền dựa trên một request parameter như **isAdmin=true**. Không cấp mọi authority cho mọi user “để endpoint chạy được”.

### 5.6. Giữ audit hữu ích nhưng không lộ bí mật

Nên log một event với request/correlation ID, cơ chế xác thực, mã kết quả, thời gian, định danh tài khoản đã chuẩn hóa hoặc ID nội bộ theo chính sách riêng tư. Không log mật khẩu hay token. Tách metric **credential sai**, **account disabled**, **source unavailable** để chẩn đoán; hạn chế trả trạng thái nội bộ đó ra client khi có nguy cơ user enumeration.

## 6. Cách kiểm tra một AuthenticationProvider tùy chỉnh trước production

Dùng checklist sau để rà soát trust boundary và hành vi provider:

| Tình huống | Provider phải làm gì? |
| --- | --- |
| Bằng chứng hợp lệ, source có account active | Tạo principal và quyền từ nguồn tin cậy |
| Mật khẩu sai hoặc người dùng không tồn tại | Từ chối, không trả authenticated Authentication |
| Tài khoản disabled/locked | Từ chối, không cấp authorities |
| Source timeout/response bị lỗi | Fail closed, báo lỗi dịch vụ nội bộ; không fallback chấp nhận |
| Client tự gắn ROLE_ADMIN | Bỏ qua role tự khai; chỉ trả authority do source cấp |
| Provider nhận token loại khác | Không nhận nhầm; supports chính xác |
| Token ký sai hoặc issuer/audience sai | Từ chối; không tin payload decode được |
| Credential hết hạn hoặc đã revoke | Từ chối; xác minh tính mới theo loại bằng chứng |
| User đã đăng nhập nhưng thiếu quyền API | Authentication có thể thành công, authorization trả 403 |
| Source bị thay đổi quyền/khóa account | Phiên/cache hiện hành tuân thủ chính sách cập nhật/thu hồi đã thiết kế |
| Có nhiều provider | Không có đường fallback bỏ qua bước xác minh |
| Có log và giám sát | Không ghi bí mật; phân loại được lỗi thực để điều tra |

Một bài kiểm thử chất lượng cần xem **kết quả từ AuthenticationManager và SecurityFilterChain**, không chỉ gọi trực tiếp một hàm so sánh password. Kiểm tra tình huống chứng cứ sai, lỗi nguồn, đổi quyền, thu hồi, đóng kết nối và phát hiện credential stuffing theo phạm vi hệ thống.

## 7. Lỗi thường gặp

**Lỗi 1 — Tin trường role do client gửi.** Client gửi **{"username":"alice","role":"ADMIN"}** không chứng minh quyền ADMIN. Sửa bằng cách chỉ xây authorities từ nguồn server hoặc token đã được xác minh đầy đủ.

**Lỗi 2 — So khớp password bằng String.equals với hash lưu sẵn.** Mật khẩu rõ không giống hash. Dùng **PasswordEncoder.matches** với cấu hình hash được quản lý đúng.

**Lỗi 3 — Không tìm thấy user thì tự tạo user mới.** Login là quá trình kiểm tra danh tính hiện có, không phải quy trình đăng ký. Đăng ký phải có yêu cầu và kiểm soát riêng.

**Lỗi 4 — Nguồn danh tính lỗi vẫn cho phép truy cập.** Đây là hành vi **fail open**, có thể biến sự cố remote thành lỗ hổng. Đúng là trả thất bại tạm thời và điều tra.

**Lỗi 5 — Nhầm decode JWT với verify JWT.** Ai cũng có thể tạo payload Base64 hợp lệ; phải kiểm tra chữ ký và các claim quan trọng bằng thư viện đáng tin, với cấu hình issuer/audience từ server.

**Lỗi 6 — Chỉ kiểm tra password mà không kiểm tra active/locked.** Credential chính xác của tài khoản đã bị vô hiệu vẫn phải bị từ chối theo chính sách.

**Lỗi 7 — Tự gán setAuthenticated(true) cho Authentication do request gửi.** Chỉ tạo object authenticated sau khi bằng chứng hợp lệ; không chuyển trạng thái bằng thao tác đánh dấu đơn thuần.

**Lỗi 8 — Coi mọi AuthenticationException là “sai mật khẩu”.** Mất kết nối source và credential sai có nguyên nhân khác nhau. Cần có logging/metrics và response phù hợp mà không để lộ thông tin nội bộ.

**Lỗi 9 — Provider hỗ trợ quá rộng hoặc đặt fallback lỏng lẻo.** Một token có thể được provider khác chấp nhận không đúng ngữ cảnh. Xác định kiểu token và danh sách provider chính xác; test thứ tự và điều kiện fallback.

## 8. Câu hỏi tự kiểm tra

**1. Vì sao không được lấy role từ request để trả về trong Authentication?** Vì role do client tự khai là dữ liệu chưa tin. Role phải đến từ nguồn có thẩm quyền và liên kết với danh tính đã xác minh.

**2. AuthenticationProvider có thể làm gì khi không hỗ trợ loại token được truyền vào?** **supports(...)** trả false; nếu được gọi với token không phù hợp, **authenticate(...)** có thể trả null để manager xem xét provider khác.

**3. Nếu kho danh tính bị timeout nhưng password gửi lên trông đúng thì sao?** Không thể xác minh nên phải từ chối an toàn. Không được suy đoán “đúng” từ chuỗi người dùng gửi; xử lý sự cố dịch vụ.

**4. Chỉ cần dùng BCrypt là đã có nguồn danh tính đáng tin chưa?** Chưa. BCrypt hỗ trợ so sánh password với hash. Còn cần tin cậy dữ liệu hash, quy trình cập nhật, trạng thái tài khoản, role, bảo vệ nguồn và cách vận chuyển dữ liệu.

**5. Đăng nhập đúng nhưng GET /api/admin bị 403 có hợp lý không?** Có. User đã được xác thực, nhưng chưa được cấp **ROLE_ADMIN**. Đó là phân quyền từ chối, không phải xác thực thất bại.

**6. JWT có payload ghi issuer đáng tin và role ADMIN; có được tin ngay không?** Không. Phải xác minh chữ ký bằng khóa được cấu hình đáng tin, issuer, audience, hiệu lực, chính sách token và mapping quyền.

## 9. Tài liệu chính thức

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): Authentication, ProviderManager và AuthenticationProvider.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): mẫu chuẩn cho UserDetailsService + PasswordEncoder.
- [Spring Security 6.5 — Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html): chuyển username/password từ header sang AuthenticationManager.
- [Spring Security 6.5 — Java Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): cấu hình SecurityFilterChain.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác minh chữ ký và các điều kiện của JWT khi dùng thành phần chuẩn.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): phản hồi đăng nhập, bảo vệ credential và chống user enumeration.
