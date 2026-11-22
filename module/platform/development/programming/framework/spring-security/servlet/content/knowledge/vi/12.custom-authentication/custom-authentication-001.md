# Chọn AuthenticationProvider, bộ chuyển đổi hay bộ lọc theo yêu cầu tích hợp

> **Phạm vi:** Spring Security 6 trên **Servlet stack**, Java 17+, Spring Boot 3.x. Bài này giúp chọn đúng điểm mở rộng khi tích hợp API key, hệ thống danh tính riêng, HTTP header đặc thù hoặc luồng đăng nhập không mặc định: khi nào dùng `AuthenticationProvider`, `AuthenticationConverter`, authentication filter có sẵn hay một `OncePerRequestFilter` tùy chỉnh. Trọng tâm là phân tách trách nhiệm, hạn chế tự viết lại cơ chế đã có, kiểm soát thành công/thất bại và bảo đảm mọi request đi qua đúng `SecurityFilterChain`. Spring WebFlux có các API tương ứng nhưng không dùng nguyên các lớp Servlet ở đây.

## 1. Quy tắc chọn nhanh: cần thay đổi điều gì?

Đừng bắt đầu bằng việc viết một filter mới. Hãy hỏi **điểm nào trong quy trình xác thực hiện tại không đáp ứng yêu cầu**.

| Nhu cầu thực tế | Điểm mở rộng ưu tiên | Lý do |
| --- | --- | --- |
| Có cách nhận credentials đã được framework hỗ trợ, nhưng cần xác minh ở một nguồn khác | `AuthenticationProvider` thích hợp, hoặc adapter cho `UserDetailsService` | Xác minh bí mật/danh tính thuộc tầng **provider**, không phải HTTP parsing |
| HTTP header/form/body khác chuẩn và cần chuyển thành yêu cầu xác thực | `AuthenticationConverter` hoặc converter của cơ chế có sẵn | Chuyển **HTTP request → Authentication chưa xác thực** |
| Cần kích hoạt xác thực tại URL cụ thể, quản lý thành công/thất bại, session và lưu context | `AuthenticationFilter` / `AbstractAuthenticationProcessingFilter` nếu phù hợp | Filter quản lý **thời điểm chạy và vòng đời HTTP** |
| Mỗi request chứa credentials riêng theo giao thức tùy chỉnh; filter chuẩn không phù hợp | `OncePerRequestFilter` mỏng, gọi converter + manager | Chỉ tự viết lớp **đọc request và nối luồng**, không nhét nghiệp vụ xác thực vào filter |
| Xác thực JWT chuẩn hoặc opaque bearer token | `oauth2ResourceServer().jwt()` / `opaqueToken()` | Tận dụng resource server, validators và entry point chuẩn; **đừng tự parse JWT** |
| OAuth2/OIDC đăng nhập qua nhà cung cấp danh tính | `oauth2Login()` và các extension points của client | Framework đã xử lý redirect, state, code exchange và nhiều biện pháp an ninh |
| Form login username/password thông thường | `formLogin()`, `DaoAuthenticationProvider`, `UserDetailsService`, `PasswordEncoder` | Không cần custom filter chỉ để đổi nơi lưu người dùng |
| Muốn dùng role/scope của danh tính đã xác thực để kiểm tra quyền | `GrantedAuthoritiesMapper`, JWT authorities converter, authorization rules | **Authorization** không phải lý do tự viết authentication filter mới |

**Tóm tắt:** Converter *đọc và đóng gói*, Provider *kiểm chứng*, Filter *quyết định lúc nào yêu cầu xác thực và cách tích hợp với HTTP*, `AuthenticationManager` *điều phối provider*. Bắt đúng tầng giúp tránh duplicate logic, tránh đọc sai credential và đơn giản hóa kiểm thử.

## 2. Ba trách nhiệm khác nhau trong kiến trúc Servlet

```text
HTTP request
    |
    v
Servlet container
    |
    v
DelegatingFilterProxy -> FilterChainProxy
                             |
                 chọn SecurityFilterChain đầu tiên match
                             |
                             v
                    Authentication filter
                             |
                   AuthenticationConverter
                   đọc header/body/cookie...
                             |
                             v
                Authentication token (chưa authenticated)
                             |
                             v
                    AuthenticationManager
                    (thường ProviderManager)
                             |
                  lựa chọn AuthenticationProvider
                             |
                 +-----------+-----------+
                 |                       |
          authenticate() OK      AuthenticationException
                 |                       |
                 v                       v
       Authentication hợp lệ       failure handler / 401
                 |
                 v
       tạo/đặt SecurityContext
       lưu nếu policy yêu cầu
                 |
                 v
       AuthorizationFilter / controller
```

Sơ đồ rút gọn: một số filter framework có thể đặt converter và logic xử lý vào những lớp khác nhau, và chi tiết thứ tự phụ thuộc `SecurityFilterChain`. Đối với authentication theo request, có những trường hợp **không lưu** ngữ cảnh qua nhiều request; đối với login session-based, có thể **cần lưu**.

### 2.1. Authentication là một yêu cầu và một kết quả

`Authentication` có thể biểu diễn:

- **Yêu cầu chưa xác thực:** principal hoặc credentials từ HTTP request, `isAuthenticated() == false`.
- **Kết quả đã xác thực:** principal đã được xác minh, authorities do server tin cậy cấp, `isAuthenticated() == true`.

Trong ví dụ tích hợp đối tác, converter tạo một token **chưa xác thực** mang API key; provider trả về token **đã xác thực** với principal `partner-A` và authority `ROLE_PARTNER` sau khi kiểm tra key. Không tin bất kỳ authority nào do client tự gửi trong header.

### 2.2. AuthenticationConverter: chỉ chuyển dữ liệu đầu vào

Interface `org.springframework.security.web.authentication.AuthenticationConverter` có phương thức:

```java
Authentication convert(HttpServletRequest request);
```

Đây là **chữ ký API minh họa**, không phải class Java độc lập. Converter có thể trả `null` khi request không chứa dạng credentials mà nó xử lý; có thể ném `AuthenticationException` khi dữ liệu hiện diện nhưng sai định dạng, tùy contract đã thiết kế.

Converter nên **không** tự gọi database, không tự xác minh mật khẩu/API key, không tự cấp `ROLE_ADMIN`, không tự mở session hay ghi HTTP response. Nếu converter phải đọc body, cần chú ý body stream chỉ đọc được một lần trừ khi đã có wrapper, và tránh phá form/multipart parsing của những thành phần tiếp theo.

### 2.3. AuthenticationProvider: chứng minh danh tính

Interface `org.springframework.security.authentication.AuthenticationProvider` thường có:

```java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;

boolean supports(Class<?> authentication);
```

`supports` mô tả **kiểu token** mà provider xử lý; việc trả `true` không bắt buộc provider luôn xác thực thành công. Provider có thể:

- trả về `Authentication` đã xác thực khi thông tin hợp lệ;
- ném `BadCredentialsException` hoặc loại `AuthenticationException` thích hợp khi thất bại;
- trả `null` nếu không thể xác thực token theo contract, cho phép `ProviderManager` thử provider khác trong cấu hình đa provider.

Provider không nên biết URL/controller cụ thể, tự đọc servlet request hay trực tiếp gửi response 401. Provider kiểm chứng dữ liệu từ token và cung cấp principal/authorities được tin cậy.

### 2.4. Filter: vòng đời trên HTTP

Một authentication filter có thể:

1. Kiểm tra request nào thuộc phạm vi cần xác thực.
2. Đưa request vào converter hoặc parse credentials theo contract.
3. Gọi `AuthenticationManager.authenticate(...)`.
4. Với thành công, tạo `SecurityContext` mới và gắn vào holder; lưu context nếu policy/flow cần.
5. Với thất bại, dọn context thích hợp, gọi `AuthenticationFailureHandler` hoặc trả entry point phù hợp.
6. Quyết định **tiếp tục filter chain** hay **kết thúc response** (ví dụ login endpoint trả JSON/redirect).

Một filter là điểm mở rộng quyền lực cao: viết sai thứ tự có thể bypass authorization, ghi đè người dùng đã xác thực, làm lộ bí mật trong log hoặc khiến client nhận 200 mặc dù authentication thất bại.

## 3. Decision tree: chọn tầng thấp nhất đáp ứng yêu cầu

```text
Yêu cầu tích hợp mới?
   |
   +-- Là OAuth2/OIDC/JWT/SAML2/LDAP/form login chuẩn?
   |      |
   |      +-- Có -> ưu tiên module tích hợp có sẵn,
   |                 custom converter/mapper/provider chỉ ở điểm được hỗ trợ
   |
   +-- HTTP credential format đã được framework hỗ trợ?
   |      |
   |      +-- Có, chỉ khác nơi xác minh -> provider / UserDetailsService
   |      |
   |      +-- Không, nhưng có filter nhận request phù hợp?
   |              |
   |              +-- Có -> bổ sung AuthenticationConverter
   |              +-- Không -> dùng AuthenticationFilter với request matcher,
   |                          hoặc OncePerRequestFilter mỏng
   |
   +-- Cần xác thực mỗi HTTP request hay một login exchange tạo session?
          |
          +-- Mỗi request -> stateless context, filter tiếp tục chain nếu thành công
          |
          +-- Login exchange -> success/failure handlers,
                                session strategy, saveContext, CSRF khi cần
```

**Quy tắc thực hành:** nếu chỉ cần xác minh mật khẩu từ database khác, đừng bắt đầu từ `OncePerRequestFilter`. Nếu chỉ đổi tên header chứa credential, đừng xây một `AuthenticationProvider` mới khi provider hiện có đã xác minh được đúng kiểu token. Nếu đang xử lý JWT, đừng viết lại kiểm chữ ký và kiểm tra `iss`/`aud`/`exp` bằng Java tự chế.

### Chọn theo kiểu tích hợp

| Trường hợp | Đề xuất | Cần tránh |
| --- | --- | --- |
| Người dùng đăng nhập bằng form, dữ liệu lưu ở hệ thống nội bộ | `UserDetailsService` hoặc provider đặc thù nếu logic xác minh vượt DAO | Đọc password trong custom filter rồi so string thủ công |
| Xác thực certificate/TLS client authentication | Cơ chế X.509 của Spring Security và cấu hình container/proxy | Tin header certificate do client tùy ý gửi |
| API key đối tác trong header riêng | Converter + provider + filter thích hợp, hoặc filter chuẩn có converter | Đặt `setAuthenticated(true)` ngay khi thấy header có chuỗi |
| JWT phát hành bởi IdP chuẩn | `oauth2ResourceServer().jwt()`, decoder/validators/authorities mapper | Tự giải mã Base64 payload rồi tin claim |
| Opaque token cần introspection | Resource server opaque token + introspector | Coi token không rỗng là hợp lệ |
| Login trả JSON và tạo session | `AuthenticationFilter`/filter tương đương với success/failure handlers và `SecurityContextRepository` | Login controller chỉ đặt `SecurityContextHolder` mà quên explicit save |
| Chỉ cần phân quyền tenant hoặc mapping role | Authorities mapper hoặc authorization policy | Đưa toàn bộ logic authorization vào provider |
| Thay đổi định dạng Authorization header | Converter hoặc authentication resolver phù hợp | Viết lại toàn bộ AuthenticationManager |

## 4. Cách phối hợp ProviderManager và nhiều AuthenticationProvider

`ProviderManager` là triển khai thường dùng của `AuthenticationManager`. Nó đi qua các provider được đăng ký, xem `supports` và thử authentication theo contract. Khi một provider trả kết quả hợp lệ, quá trình có thể kết thúc; nếu không có provider nào xử lý được token, hệ thống có thể ném `ProviderNotFoundException`.

Ví dụ minh họa:

```java
AuthenticationManager manager = new ProviderManager(
        new PartnerKeyAuthenticationProvider());
// Đây là fragment: class provider được định nghĩa trong ví dụ đầy đủ bên dưới.
```

Đừng chỉ viết một provider trả `true` cho mọi loại `Authentication`. Nếu provider claim xử lý toàn bộ token nhưng không thật sự kiểm chứng từng loại, bạn có nguy cơ chặn luồng đăng nhập khác hoặc vô tình cấp danh tính sai.

### Provider chỉ nhận đúng loại token

```java
@Override
public boolean supports(Class<?> type) {
    return PartnerKeyAuthenticationToken.class.isAssignableFrom(type);
}
```

**Cảnh báo:** `supports` không tự kiểm tra tính hợp lệ của credentials. Nó chỉ là điều kiện chọn provider. Logic `authenticate` vẫn phải xác minh secret/chữ ký, nguồn dữ liệu, thời hạn, trạng thái account và những ràng buộc nghiệp vụ liên quan.

### Không tạo Authentication hợp lệ từ dữ liệu chưa tin cậy

Sai về mặt an ninh:

```java
// ANTI-PATTERN; không phải mã Java độc lập.
String username = request.getHeader("X-User");
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(
        UsernamePasswordAuthenticationToken.authenticated(
                username, null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))));
SecurityContextHolder.setContext(context);
```

Nếu header có thể do client tự gửi, bất kỳ người dùng nào cũng có thể mạo danh admin. Ngay cả khi có reverse proxy xác thực phía trước, ứng dụng phải xác minh **trust boundary**: proxy tin cậy nào được phép thêm header, proxy có xóa header do client đưa vào không, kết nối giữa proxy và backend có được bảo vệ không, và dữ liệu có chống giả mạo hay không.

## 5. Chọn filter có sẵn hay tự viết OncePerRequestFilter?

### 5.1. AuthenticationFilter: thành phần tổng hợp dùng lại được

`org.springframework.security.web.authentication.AuthenticationFilter` nhận `AuthenticationManager` và `AuthenticationConverter`. Nó thích hợp khi cần xác thực tại một endpoint theo `RequestMatcher` rồi có success/failure handler rõ ràng, ví dụ một **login/exchange endpoint**.

```java
// Fragment minh họa trong cấu hình Spring Security, không phải file độc lập.
AuthenticationFilter filter =
        new AuthenticationFilter(authenticationManager, converter);

filter.setRequestMatcher(
        new AntPathRequestMatcher("/auth/exchange", "POST"));

filter.setSuccessHandler((request, response, authentication) -> {
    response.setStatus(HttpServletResponse.SC_OK);
});

filter.setFailureHandler((request, response, exception) -> {
    response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
});
```

Để sử dụng thực tế phải đặt filter vào đúng `SecurityFilterChain`, xem CSRF, error handling, security context persistence và session strategy. Các class cần import là `AuthenticationFilter`, `AntPathRequestMatcher`, `HttpServletResponse` cùng các dependency tương ứng.

**Điểm rất dễ nhầm:** một authentication filter dùng cho **login endpoint** có thể **kết thúc response ở success handler**, không mặc nhiên đi tiếp controller như một header filter cho tài nguyên ở mọi request. Nếu muốn request sau khi có credential được tiếp tục xử lý bởi `AuthorizationFilter` và controller, cần chọn filter có lifecycle phù hợp hoặc tự viết một adapter thật mỏng.

### 5.2. OncePerRequestFilter cho API request authentication đặc thù

`OncePerRequestFilter` giúp triển khai filter chạy một lần trong các điều kiện dispatch được framework quản lý. Nó **không tự** biết cách authenticate, save context hay trả lỗi bảo mật. Nếu dùng, hãy:

- Giới hạn registration chỉ trong chain/URL cần xử lý;
- Dùng converter riêng để parse;
- Gọi `AuthenticationManager` có provider chuyên trách;
- Chỉ đặt `SecurityContext` đã xác thực sau khi provider trả kết quả;
- Chọn stateful/stateless và repository tường minh;
- Xử lý `AuthenticationException` mà không lộ secret;
- Tiếp tục `FilterChain.doFilter` khi hợp lệ;
- Tránh đăng ký filter hai lần (vừa servlet filter toàn cục vừa security filter).

Dùng filter mỏng như một **adapter**, không biến nó thành service kiểm tra secret, user store hoặc authorization engine.

### 5.3. Kiểm soát vị trí filter

Authentication phải được thiết lập **trước khi** request tới bước authorization. Ví dụ:

```java
http.addFilterBefore(
        new PartnerKeyFilter(authenticationManager, converter),
        UsernamePasswordAuthenticationFilter.class);
```

Đây là một đoạn minh họa cấu hình, không phải một file độc lập. Chọn anchor dựa trên cấu hình filter thực tế; nếu chain không dùng form login, vẫn cần xác minh thứ tự và cơ chế framework định vị filter bằng lớp anchor. Đừng đặt custom authentication filter sau `AuthorizationFilter` vì khi đó việc xác thực có thể quá muộn để cấp quyền.

**Quan trọng:** Spring Boot có thể tự đăng ký một bean kiểu `jakarta.servlet.Filter` vào Servlet container. Nếu bạn đồng thời thêm nó bằng `http.addFilterBefore`, filter có thể chạy **hai lần ở hai cấp độ**. Ví dụ runnable sau **khởi tạo filter trực tiếp trong SecurityConfig, không khai báo nó là `@Component` hay `@Bean`**, để tránh auto-registration.

## 6. Ví dụ chạy được: đối tác gửi X-Partner-Key trên từng request

Ta triển khai một API demo có `GET /partner/me`. Client gửi secret qua HTTP header `X-Partner-Key`; converter chỉ đọc header, provider kiểm tra secret và trả principal `partner-A`, filter nối authentication vào request, và authorization cho phép endpoint bảo vệ.

**Mục tiêu học tập:** một ví dụ đầy đủ tách `AuthenticationConverter`, `AuthenticationProvider` và `OncePerRequestFilter`. Đừng lấy khóa hard-code của demo làm chiến lược production; API key thật cần entropy lớn, lưu giữ an toàn, rotate, rate limit và không bị lộ trong logs.

### 6.1. Cấu trúc project và Gradle

Cần **JDK 17+**, **Gradle 8.5** (hoặc wrapper phù hợp), Spring Boot **3.3.5** và Spring Security 6.x do Boot quản lý:

```text
partner-key-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    PartnerKeyAuthenticationToken.java
    PartnerKeyConverter.java
    PartnerKeyAuthenticationProvider.java
    PartnerKeyFilter.java
    SecurityConfig.java
    DemoController.java
  src/test/java/demo/
    PartnerAuthenticationTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'partner-key-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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

Đây là cấu hình Gradle Groovy DSL. Không cần thư viện JWT/OAuth2 cho demo vì nó chỉ minh họa tích hợp một **secret key riêng**; khi xử lý bearer JWT thật, nên dùng Spring Security Resource Server.

### 6.2. Lớp khởi động

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 6.3. Token có hai trạng thái: chưa xác thực và đã xác thực

`src/main/java/demo/PartnerKeyAuthenticationToken.java`:

```java
package demo;

import java.util.Collection;
import java.util.List;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class PartnerKeyAuthenticationToken
        extends AbstractAuthenticationToken {

    private final String principal;
    private final String credentials;

    private PartnerKeyAuthenticationToken(
            String principal,
            String credentials,
            Collection<? extends GrantedAuthority> authorities,
            boolean authenticated) {
        super(authorities);
        this.principal = principal;
        this.credentials = credentials;
        super.setAuthenticated(authenticated);
    }

    public static PartnerKeyAuthenticationToken presented(String rawKey) {
        return new PartnerKeyAuthenticationToken(
                null, rawKey, null, false);
    }

    public static PartnerKeyAuthenticationToken verified(String partnerId) {
        return new PartnerKeyAuthenticationToken(
                partnerId,
                null,
                List.of(new SimpleGrantedAuthority("ROLE_PARTNER")),
                true);
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public Object getCredentials() {
        return credentials;
    }
}
```

**Điểm thiết kế:** request token mang secret nhưng `isAuthenticated() == false`. Token kết quả chỉ được tạo bởi provider sau khi đối chiếu, có principal và role do **server** cấp, không trả lại secret dưới dạng credentials.

Trong ứng dụng thật, một lớp token có thể còn chứa issuer, tenant, credential identifier, scopes, expiration hoặc thông tin kiểm toán được xác minh. Nhưng đừng cho client tự đặt `authenticated=true` hay authority bằng dữ liệu không được kiểm tra.

### 6.4. Converter đọc đúng header nhưng không xác thực

`src/main/java/demo/PartnerKeyConverter.java`:

```java
package demo;

import java.util.Enumeration;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.AuthenticationConverter;

public final class PartnerKeyConverter implements AuthenticationConverter {

    @Override
    public Authentication convert(HttpServletRequest request) {
        Enumeration<String> headers =
                request.getHeaders("X-Partner-Key");

        if (!headers.hasMoreElements()) {
            return null;
        }

        String raw = headers.nextElement();

        if (headers.hasMoreElements()
                || raw == null
                || raw.isBlank()
                || raw.length() > 256) {
            throw new BadCredentialsException(
                    "Invalid integration credential");
        }

        return PartnerKeyAuthenticationToken.presented(raw);
    }
}
```

Converter từ chối header trống, quá dài hoặc nhiều giá trị riêng biệt để tránh ambiguity. Nó **không** truy vấn database và **không** tự cấp quyền. `null` khi header vắng mặt nghĩa là “converter không nhận được credential”, không có nghĩa request được `permitAll`: bước authorization sau đó vẫn có thể trả 401.

Một hệ thống thật còn phải quyết định quy tắc xử lý **nhiều giá trị gộp trong một header**, ký tự điều khiển, canonicalization, Unicode và giới hạn kích thước. Không tự log raw header khi gặp lỗi.

### 6.5. Provider xác minh bí mật và cấp danh tính

`src/main/java/demo/PartnerKeyAuthenticationProvider.java`:

```java
package demo;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;

public final class PartnerKeyAuthenticationProvider
        implements AuthenticationProvider {

    // Chỉ dành cho bài demo cục bộ. Không hard-code production secret!
    private static final byte[] EXPECTED =
            "dev-only-key-123".getBytes(StandardCharsets.UTF_8);

    @Override
    public Authentication authenticate(Authentication authentication)
            throws AuthenticationException {

        if (!(authentication instanceof PartnerKeyAuthenticationToken)) {
            return null;
        }

        Object candidate = authentication.getCredentials();

        if (!(candidate instanceof String raw)
                || !MessageDigest.isEqual(
                        raw.getBytes(StandardCharsets.UTF_8), EXPECTED)) {
            throw new BadCredentialsException(
                    "Invalid integration credential");
        }

        return PartnerKeyAuthenticationToken.verified("partner-A");
    }

    @Override
    public boolean supports(Class<?> authentication) {
        return PartnerKeyAuthenticationToken.class
                .isAssignableFrom(authentication);
    }
}
```

`MessageDigest.isEqual` giúp tránh so bí mật bằng `String.equals` trong ví dụ. Nó không thay chính sách giới hạn độ dài, rate limit hoặc lưu trữ API key một cách bảo mật; đặc biệt, việc kiểm tra header dài/bất thường phải thực hiện ở converter/proxy.

**Production cần khác ví dụ:** API key phải là secret ngẫu nhiên entropy cao, có vòng đời/expiry/revocation, có thể lưu bản hash hoặc dùng service xác minh đáng tin cậy, truyền qua HTTPS và không xuất hiện trong log. Đừng lấy việc có `MessageDigest.isEqual` làm chứng nhận hệ thống đủ an toàn.

Provider minh họa không đọc `HttpServletRequest`, không gửi response và không tự quyết định endpoint nào được truy cập. Điều đó giúp test provider độc lập với web layer.

### 6.6. Filter mỏng, tiếp tục chain nếu thành công

`src/main/java/demo/PartnerKeyFilter.java`:

```java
package demo;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.AuthenticationConverter;
import org.springframework.web.filter.OncePerRequestFilter;

public final class PartnerKeyFilter extends OncePerRequestFilter {

    private final AuthenticationManager manager;
    private final AuthenticationConverter converter;

    public PartnerKeyFilter(AuthenticationManager manager,
                            AuthenticationConverter converter) {
        this.manager = manager;
        this.converter = converter;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        try {
            Authentication candidate = converter.convert(request);

            if (candidate != null) {
                Authentication verified = manager.authenticate(candidate);

                SecurityContext context =
                        SecurityContextHolder.createEmptyContext();
                context.setAuthentication(verified);
                SecurityContextHolder.setContext(context);
            }

        } catch (AuthenticationException exception) {
            SecurityContextHolder.clearContext();
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
```

Filter chỉ nhận request, gọi converter/manager, đặt context và chuyển tiếp. Nó không chứa secret validation. **Với thiết kế stateless** trong phần 6.7, không gọi `saveContext` để lưu vào session; request sau phải tự cung cấp header. Khi thiếu header, filter không cấp `Authentication`, để `AuthorizationFilter`/entry point xử lý yêu cầu phải đăng nhập.

**Tại sao catch chỉ bao quanh converter + manager, không bao quanh toàn bộ chain?** Lỗi authentication ở thành phần downstream phải được cơ chế Spring Security phía sau xử lý đúng contract; không nên biến mọi exception phát sinh từ controller thành 401 của custom filter. Trong demo này, filter bắt `AuthenticationException` do chính nó thực hiện, rồi trả 401 không tiết lộ secret.

**Tại sao clear context cuối request?** Tránh giữ trạng thái xác thực tùy chỉnh khi luồng xử lý kết thúc. `SecurityContextHolderFilter` cũng quản lý lifecycle của holder; lệnh clear bổ sung này là tường minh trong bộ lọc demo, không phải thay thế framework. Với async dispatch hoặc logic truyền context ra background thread, cần thiết kế riêng theo `SecurityContextHolderStrategy` và công cụ propagation phù hợp, không dựa vào thread-local tồn tại mãi.

### 6.7. Đăng ký filter vào đúng SecurityFilterChain

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
public class SecurityConfig {

    @Bean
    AuthenticationManager partnerAuthenticationManager() {
        return new ProviderManager(
                new PartnerKeyAuthenticationProvider());
    }

    @Bean
    @Order(1)
    SecurityFilterChain partnerChain(
            HttpSecurity http,
            AuthenticationManager partnerAuthenticationManager)
            throws Exception {

        http.securityMatcher("/partner/**");

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        http.securityContext(context -> context
                .requireExplicitSave(true)
                .securityContextRepository(
                        new NullSecurityContextRepository()));

        http.requestCache(cache -> cache.disable());

        http.exceptionHandling(errors -> errors
                .authenticationEntryPoint((request, response, exception) ->
                        response.sendError(
                                HttpStatus.UNAUTHORIZED.value())));

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated());

        http.addFilterBefore(
                new PartnerKeyFilter(
                        partnerAuthenticationManager,
                        new PartnerKeyConverter()),
                UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .anyRequest().denyAll())
                .build();
    }
}
```

Cấu hình thể hiện hai chain:

- Chain ưu tiên 1 nhận `/partner/**`, **không** dùng session để lưu authentication, chạy `PartnerKeyFilter` trước authorization. Mọi endpoint partner yêu cầu người gọi đã xác thực.
- Chain cuối nhận phần còn lại; chỉ cho `/public` và từ chối tất cả URL khác. Không dùng fallback `permitAll` khiến URL mới tự nhiên thành public.
- `AuthenticationManager` của ví dụ chỉ có một provider chuyên nhận `PartnerKeyAuthenticationToken`. Không dùng nó để xác thực username/password của ứng dụng khác nếu chưa thiết kế multi-provider manager thích hợp.
- **Không khai báo `PartnerKeyFilter` là `@Component` hay `@Bean`.** Nó chỉ được tạo trong security chain để không bị Spring Boot auto-register lần thứ hai thành Servlet filter toàn cục.

Demo chỉ dùng GET endpoint. Nếu mở rộng POST/PUT/DELETE, phải thiết kế CSRF đúng với giao thức/client: không vô hiệu hóa CSRF toàn bộ ứng dụng chỉ vì có header riêng. Với API server-to-server không dựa cookie và được phân tích đúng threat model, có thể cân nhắc scope chính sách CSRF chỉ cho chain đó.

### 6.8. Controller trả danh tính do server xác minh

`src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/partner/me")
    public String partnerMe(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }
}
```

Controller **không đọc X-Partner-Key** và không tự xác minh secret. Nó chỉ nhận authentication đã được thiết lập bởi Spring Security. `getName()` trong demo trả `partner-A`, được provider ấn định, chứ không phải username khách gửi.

### 6.9. MockMvc kiểm thử từng ranh giới

`src/test/java/demo/PartnerAuthenticationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PartnerAuthenticationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAvailable() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void missingKeyIsUnauthorized() throws Exception {
        mvc.perform(get("/partner/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validKeyGetsServerAssignedIdentity() throws Exception {
        mvc.perform(get("/partner/me")
                        .header("X-Partner-Key", "dev-only-key-123"))
                .andExpect(status().isOk())
                .andExpect(content().string("partner-A"));
    }

    @Test
    void wrongKeyIsUnauthorized() throws Exception {
        mvc.perform(get("/partner/me")
                        .header("X-Partner-Key", "wrong-key"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void twoHeaderValuesAreRejected() throws Exception {
        mvc.perform(get("/partner/me")
                        .header("X-Partner-Key",
                                "dev-only-key-123", "other"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticationIsNotPersistedToNextRequest()
            throws Exception {
        mvc.perform(get("/partner/me")
                        .header("X-Partner-Key", "dev-only-key-123"))
                .andExpect(status().isOk());

        mvc.perform(get("/partner/me"))
                .andExpect(status().isUnauthorized());
    }
}
```

Kết quả dự kiến với cấu hình demo: **6 JUnit tests PASS**, gồm một public endpoint, thiếu header, header hợp lệ, secret sai, hai giá trị header và request mới không còn authentication. Test sau cùng chứng minh stateless behavior, không dựa vào kết quả của request thành công trước đó.

Để kiểm thử riêng provider, có thể khởi tạo nó trực tiếp và gọi `authenticate(PartnerKeyAuthenticationToken.presented(...))` trong unit test; còn MockMvc chứng minh filter/converter/manager/authorization đã nối với nhau qua HTTP. **Chỉ kiểm tra provider riêng lẻ không chứng minh filter đã được đăng ký đúng vị trí.**

### 6.10. Chạy demo và thử curl

Tại thư mục `partner-key-demo` sau khi cài JDK và Gradle tương thích:

```bash
gradle test
gradle bootRun
```

Nếu có wrapper, dùng `./gradlew test`/`./gradlew bootRun` (macOS/Linux) hoặc `.\gradlew.bat test`/`.\gradlew.bat bootRun` (Windows). Từ terminal khác:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/partner/me
curl -i -H 'X-Partner-Key: dev-only-key-123' \
     http://localhost:8080/partner/me
curl -i -H 'X-Partner-Key: wrong-key' \
     http://localhost:8080/partner/me
```

Kết quả dự kiến:

| Request | HTTP status | Body khi thành công |
| --- | --- | --- |
| `GET /public` | **200** | `public` |
| `GET /partner/me`, không có header | **401** | — |
| `GET /partner/me`, key đúng | **200** | `partner-A` |
| `GET /partner/me`, key sai | **401** | — |

Đây là key demo hard-code **không có giá trị bảo mật thật**. Trên môi trường production, truyền secret qua TLS, hạn chế log tại load balancer/APM, quản lý vòng đời credential, phân tách quyền theo đối tác và hạn chế rate. Không gửi API key thật cho dịch vụ không đáng tin cậy hay dán vào tài liệu công khai.

## 7. Nếu chọn AuthenticationFilter thay OncePerRequestFilter

Không có một đáp án “filter nào tốt hơn” cho mọi trường hợp. Chọn theo **hành vi HTTP cần thiết**:

### Login/exchange endpoint

Một request `POST /auth/exchange` có thể nhận chứng thực từ converter, provider xác minh, filter tạo session hoặc phát response tùy thiết kế. `AuthenticationFilter` với `RequestMatcher`, `AuthenticationSuccessHandler`, `AuthenticationFailureHandler` và `SecurityContextRepository` là lựa chọn đáng cân nhắc.

Các câu hỏi bắt buộc: success handler trả JSON hay redirect? Có cần session fixation protection? CSRF? Có cần save context explicit? Nếu login trả token, token ký thế nào và expire/revoke ra sao? Một `AuthenticationFilter` không tự biến custom token thành JWT đáng tin cậy.

### Mỗi request cần API key

Một filter theo request **phải** tiếp tục chain sau authentication thành công để controller nhận `Authentication`. Nếu dùng `AuthenticationFilter` cho flow này, cần hiểu lifecycle success handler vì nhiều success handler **kết thúc response**. Khi không có cách cấu hình phù hợp, một `OncePerRequestFilter` nhỏ như phần 6 có thể dễ kiểm tra hơn.

### Đã có bearer token chuẩn

Nếu request dùng `Authorization: Bearer <JWT>` do IdP uy tín phát hành, ưu tiên:

```java
// Fragment cấu hình Spring Security, cần dependencies OAuth2 Resource Server:
http.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
```

Resource server xử lý signature verification, expiration và các validators thích hợp, rồi tạo authentication thông qua cơ chế chuẩn. Tùy hạ tầng cần cấu hình `JwtDecoder`, issuer/audience validators và mapping roles/scopes. Đừng copy demo API key để tự “xác thực” JWT bằng cách giải mã payload Base64 mà bỏ qua chữ ký và claim validation.

### Tùy biến dữ liệu sau khi đã xác thực

Nếu integration chỉ cần ánh xạ claims/roles/tenant sau khi danh tính đã được xác thực, điểm mở rộng phù hợp thường là authorities converter/mapper hoặc một service authorization. Đừng tạo một second authentication filter có quyền thay danh tính chỉ để biến `scope=read` thành `ROLE_READER`.

## 8. Vòng đời SecurityContext và explicit save

`SecurityContextHolder` quản lý authentication đang được dùng ở request hiện tại. Với Spring Security 6, `SecurityContextHolderFilter` thường làm nhiệm vụ nạp từ `SecurityContextRepository` và dọn holder, không tự save mọi thay đổi context khi `requireExplicitSave(true)`.

### Stateless integration

Trong demo:

```java
http.sessionManagement(sm -> sm
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

http.securityContext(sc -> sc
        .securityContextRepository(new NullSecurityContextRepository()));
```

Không có session authentication được lưu. Request mới phải gửi header hợp lệ. `SecurityContextHolder` được đặt cho request hiện tại, authorization đọc được, nhưng không tồn tại như “đã đăng nhập” ở request sau. Đây là lựa chọn tự nhiên cho machine-to-machine header credentials và có thể phục vụ nhu cầu thu hồi khi server kiểm chứng lại key từng request, tùy cache/verification backend.

### Stateful login

Khi muốn custom login tạo session, ngoài xác thực thành công thường phải:

1. Chọn repository nạp/lưu phù hợp, ví dụ `HttpSessionSecurityContextRepository` hoặc `DelegatingSecurityContextRepository` có session.
2. Thực hiện session authentication strategy phù hợp, gồm bảo vệ session fixation và chính sách phiên.
3. Tạo `SecurityContext` mới, đặt `Authentication` đã được xác thực.
4. Gọi `securityContextRepository.saveContext(context, request, response)` **trước khi response commit** nếu flow không tự save.
5. Test request thứ hai chỉ có session cookie, không gửi lại credentials.

**Không** chỉ gọi `SecurityContextHolder.setContext(context)` rồi giả định được lưu vì có `SessionCreationPolicy.IF_REQUIRED`. Session policy và repository/save logic là hai quyết định riêng. Nếu dùng filter chuẩn, xem cơ chế nào nó đã cung cấp để tránh double-save hoặc duplicate session strategy.

## 9. AuthenticationException và lỗi HTTP: xử lý đúng tầng

Một provider có thể ném:

- `BadCredentialsException` khi key sai hoặc không được chấp nhận;
- `AuthenticationServiceException` khi hệ thống xác minh danh tính không thể hoạt động;
- `LockedException`/`DisabledException`/`CredentialsExpiredException` cho trạng thái account phù hợp;
- các `AuthenticationException` chuyên biệt khác khi hệ thống có nhiều bước xác thực.

Đừng phản hồi cho client bằng toàn bộ `exception.getMessage()`, raw header, token hoặc thông tin cho biết tài khoản tồn tại. Với API, thường dùng 401 chung cho credentials không hợp lệ; với lỗi hạ tầng, cần metric/telemetry nội bộ và một response theo contract (có thể là 5xx/503 tùy thiết kế) không lộ chi tiết.

### 401 khác 403

| Tình huống | Bản chất | HTTP trong API demo |
| --- | --- | --- |
| Không có credential nhưng URL yêu cầu authentication | Chưa xác thực | 401 |
| Có key nhưng key sai | Authentication failure | 401 |
| Key đúng, không có role yêu cầu | Authorization failure | Thường 403 |
| POST bị chặn vì thiếu CSRF token | CSRF protection | Thường 403 |
| Provider gặp lỗi data store | Lỗi hạ tầng xác thực | Theo policy; không nên giả dạng “password sai” trong telemetry |

`ExceptionTranslationFilter` và `AuthenticationEntryPoint` xử lý những trường hợp phát sinh ở đúng vị trí trong filter chain, nhưng **authentication filter tùy chỉnh có thể chạy trước chúng**. Vì vậy filter phải catch/định tuyến `AuthenticationException` của chính mình bằng failure handler hoặc response phù hợp. Đừng giả định mọi lỗi ném từ bất kỳ filter nào cũng tự chuyển thành 401.

### Bảo vệ thời gian xử lý và độ dài header

Đối với API key/secret, giới hạn kích thước input và sử dụng phép so sánh/verification phù hợp. Cần rate limiting, timeout cho external identity service, circuit breaker khi cần và tránh phản hồi phân biệt quá chi tiết. Không lạm dụng `MessageDigest.isEqual` như sự thay thế cho secret management; đó chỉ là một thành phần ở cấp phép so sánh.

## 10. Multi-chain, ordering và tránh bypass

Khi ứng dụng có nhiều `SecurityFilterChain`, `FilterChainProxy` chọn **chain đầu tiên có matcher phù hợp**. Nếu custom filter chỉ nằm trong chain `/partner/**`, nó sẽ không chạy trên `/admin/**` hay `/api/**` trừ khi được cấu hình ở chain khác.

```text
@Order(1) securityMatcher("/partner/**")
          -> PartnerKeyFilter -> authenticated()

@Order(2) matcher mọi request còn lại
          -> permitAll("/public") -> denyAll() các URL khác
```

Một số lỗi dễ gặp:

- Đặt fallback match-all **trước** chain partner khiến chain chuyên biệt không bao giờ được chọn.
- Cấu hình `requestMatchers("/partner/**")` chỉ trong authorization nhưng quên `securityMatcher` khi cần chính sách filter riêng.
- Đăng ký custom filter như `@Component` nên nó chạy ngoài `FilterChainProxy` hoặc chạy hai lần.
- Thêm filter ở vị trí sau authorization, khiến request bị 401 trước khi filter có cơ hội tạo Authentication.
- Chỉ bảo vệ `/partner/me` nhưng endpoint mới `/partner/admin` được tạo trong chain mặc định `permitAll()`.
- Dùng `web.ignoring()` thay vì `permitAll()` cho endpoint cần hưởng security headers/filter chain.
- Tin rằng converter luôn trả token; với header vắng mặt, converter thường trả `null` và authorization vẫn phải bảo vệ endpoint.

Bộ kiểm thử nên có endpoint **không tồn tại**, endpoint **mới thuộc prefix**, URL ngoài phạm vi partner, và request không có header. Không chỉ kiểm thử provider một cách độc lập.

## 11. So sánh sáu cách mở rộng qua bài toán cụ thể

### Tình huống A: Đổi nơi lưu account username/password

Từ H2 nội bộ sang LDAP hoặc một user database cũ nhưng vẫn nhận username/password chuẩn. Nếu chỉ đổi nguồn tìm user, thích hợp dùng `UserDetailsService`/provider có sẵn hoặc adapter. Không tự tạo filter cho form login khi request structure không đổi.

### Tình huống B: Secret header độc quyền và phải verify từng request

Cần converter đọc header, provider xác minh secret, filter đi tiếp sau thành công, policy stateless rõ. Đây là bài toán demo. Nếu upstream đã cung cấp một chuẩn phù hợp, ưu tiên module sẵn có hơn là tạo giao thức xác thực mới.

### Tình huống C: Token JWT từ Identity Provider

Cần xác minh chữ ký, issuer, audience, expiration, algorithm và key rotation. Dùng OAuth2 Resource Server `jwt()` và tùy biến decoder/validators/authority converter. Đừng tự gọi `Base64.getDecoder()` rồi tin `sub`/`roles`; Base64 chỉ mã hóa văn bản, không xác thực chữ ký.

### Tình huống D: Browser redirect đến nhà cung cấp OIDC

Dùng `oauth2Login()`, thiết lập client registration và handler thích hợp. Những bước `state`, redirect URI, authorization code, PKCE và session/CSRF có yêu cầu riêng. Không triển khai một header filter đơn giản để thay cả flow này.

### Tình huống E: Reverse proxy xác thực và cung cấp header người dùng

Một header như `X-Authenticated-User` chỉ đáng tin **sau khi** hạ tầng đảm bảo client không thể gửi giả, proxy luôn xóa/ghi đè header và backend chỉ nhận kết nối từ proxy được xác thực. Có thể cần pre-auth integration hay provider thích hợp, nhưng đây là trust boundary phải được kiểm chứng, không phải việc “nhìn thấy header nên cấp role”.

### Tình huống F: Chỉ cần cấp quyền nghiệp vụ sau xác thực

Nếu đã có principal đáng tin và cần kiểm tra “partner A có được sửa invoice X không?”, hãy triển khai authorization policy/service, không biến authentication provider thành nơi truy vấn mọi đối tượng nghiệp vụ. Authentication trả lời **ai**, authorization trả lời **được làm gì**.

## 12. Troubleshooting có hệ thống

Nếu client gửi key đúng nhưng nhận 401:

1. **Kiểm tra chain selection:** `/partner/me` có match đúng chain có `PartnerKeyFilter` không?
2. **Kiểm tra vị trí:** filter chạy trước `AuthorizationFilter` chứ? Có bị auto-register hai lần không?
3. **Kiểm tra converter:** tên header đúng, có bị proxy xóa/đổi hoặc header bị trùng không? Đừng log raw secret.
4. **Kiểm tra manager:** provider có đăng ký với đúng `AuthenticationManager` không?
5. **Kiểm tra `supports`:** token converter trả có đúng class provider nhận không?
6. **Kiểm tra provider:** secret verification, trạng thái đối tác, timeout store, expiry/rotation.
7. **Kiểm tra kết quả:** provider trả `Authentication.isAuthenticated() == true` và principal/authorities server cấp chưa?
8. **Kiểm tra context:** filter đã đặt authenticated token vào `SecurityContextHolder` trước khi chain đi tiếp chưa?
9. **Kiểm tra policy:** `authenticated()`/`hasRole(...)` của URL có đúng yêu cầu không?
10. **Kiểm tra response:** AuthenticationException được filter xử lý ở vị trí của nó chưa? 403 là authorization hoặc CSRF thay vì credentials?
11. **Kiểm tra request kế tiếp:** stateless nghĩa là mỗi request cần header, không được giữ user vì test trước đã gửi key.
12. **Kiểm tra deploy:** HTTPS, reverse proxy, duplicate filters, mapping dispatch, cluster secret rotation và permissions.

Một biến thể lỗi nguy hiểm là provider ném lỗi nhưng filter catch rồi **tiếp tục chain như thể thành công**. Luồng thất bại phải dừng hoặc chuyển vào failure handler đúng cách; tuyệt đối không tự set `authenticated=true` để “làm demo chạy”.

### Quan sát log đúng mức

Có thể tạm bật DEBUG cho Spring Security ở môi trường phát triển:

```properties
logging.level.org.springframework.security=DEBUG
```

Không bật log chứa credentials ở production. Log “Securing GET /partner/me” không chứng minh provider đã được gọi hay key đã được verify; dùng unit tests cho provider, MockMvc cho filter chain, và metrics server-side được thiết kế an toàn.

## 13. Checklist thiết kế và kiểm thử

| Câu hỏi | Tiêu chí đạt |
| --- | --- |
| Chỉ đổi nguồn xác minh hay đổi HTTP protocol? | Chọn provider/adapter nếu chỉ đổi backend; converter/filter nếu input HTTP khác |
| Có framework integration chuẩn không? | Tận dụng Spring Security modules trước khi tự viết |
| Converter làm gì? | Parse & validate cấu trúc input, trả token **chưa xác thực** hoặc null |
| Provider làm gì? | Kiểm chứng secret/danh tính, kiểm tra trạng thái, trả Authentication đáng tin hoặc exception |
| Token tự chế có đúng lifecycle không? | Client không tự xác lập `authenticated=true` và roles |
| Filter ở đâu? | Chỉ chạy chain cần thiết, trước authorization, không auto-register hai lần |
| Trường hợp thiếu header? | Không cấp Authentication; endpoint bảo vệ trả 401 theo entry point |
| Trường hợp sai/duplicate header? | Từ chối an toàn, không lộ secret |
| Trường hợp đúng? | Controller thấy principal/authority server cấp |
| Stateful hay stateless? | Chọn rõ repository, session policy, explicit save nếu cần, test request độc lập |
| Lỗi hạ tầng? | Có telemetry, timeout/failure strategy, response public an toàn |
| Giao thức và secret? | HTTPS, rate limit, key rotation/revocation, secret management, log redaction |
| Authorization? | Tách khỏi xác thực, test 403/role và deny-by-default |
| Migration/đổi provider? | Test cả token/provider cũ và mới, fail closed khi không nhận dạng |

## 14. Tự kiểm tra

1. **Muốn lấy password từ database khác nhưng vẫn dùng form login chuẩn thì chọn gì?** Thường bắt đầu ở `UserDetailsService` hoặc provider tương thích, không tự viết filter HTTP.
2. **AuthenticationConverter có được tự trả token đã xác thực không?** Không nên khi chỉ chuyển input không đáng tin; provider/manager phải kiểm chứng trước.
3. **AuthenticationProvider có nên đọc HttpServletRequest và ghi HTTP response không?** Không; provider nên độc lập transport.
4. **AuthenticationFilter có tự đi tiếp controller sau success trong mọi cấu hình không?** Không; success handler có thể kết thúc response, phù hợp login endpoint hơn một số kiểu per-request authentication.
5. **Khi nào OncePerRequestFilter có lý do tồn tại?** Khi không có filter chuẩn phù hợp, cần adapter HTTP mỏng để dùng converter/manager và đi tiếp chain.
6. **Tại sao không nên tự xử lý JWT bằng decode payload?** Payload đọc được không có nghĩa token đã được xác minh chữ ký, issuer, audience, thời hạn và algorithm.
7. **Thấy header X-User có nên cấp ROLE_ADMIN?** Không, trừ khi trust boundary đã chứng minh dữ liệu không thể bị client giả mạo và mapping quyền được xác minh.
8. **Custom filter có cần đăng ký như Servlet Filter bean nữa không?** Thường không; đã đưa vào SecurityFilterChain thì phải tránh auto-registration trùng.
9. **Stateless nghĩa là gì đối với authentication ở request thứ hai?** Phải cung cấp credential ở request mới; context trước đó không tự được lấy từ HttpSession.
10. **Session login custom có cần saveContext không?** Với explicit save, flow không tự save phải gọi `SecurityContextRepository.saveContext(...)` trước khi response commit.
11. **Provider trả BadCredentialsException nhưng filter tiếp tục chain như thành công có đúng không?** Sai; phải xử lý failure và không cho request đi qua với identity không đáng tin.
12. **Ứng dụng cần role/scope nghiệp vụ có nhất thiết viết provider mới không?** Không. Nhiều trường hợp chỉ cần authorities mapper hoặc authorization rules.

**Ghi nhớ:** Hãy mở rộng **tầng nhỏ nhất đáp ứng yêu cầu**: `AuthenticationConverter` chuyển HTTP input thành token chưa xác thực, `AuthenticationProvider` xác minh credentials và trả danh tính đáng tin, authentication filter điều phối vòng đời request/success/failure, `AuthenticationManager` chọn provider, còn authorization kiểm tra quyền. Ưu tiên tích hợp Spring Security chuẩn khi có; chỉ tự viết filter khi thật cần, giới hạn phạm vi, bảo vệ secrets, chọn session policy rõ và kiểm thử request thực qua filter chain.
