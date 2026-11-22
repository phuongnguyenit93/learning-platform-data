# Kiểm thử AuthenticationConverter, JSON sai và thông tin đầu vào thiếu

## 1. Vì sao AuthenticationConverter cần bộ kiểm thử riêng?

Trong ứng dụng Spring Security có **đăng nhập bằng JSON**, một request như `POST /auth/login` có thể mang body:

~~~json
{
  "username": "alice",
  "password": "correct-password"
}
~~~

Tuy nhiên, request thực tế không phải lúc nào cũng có JSON đúng. Client có thể gửi body rỗng, dấu ngoặc thiếu, JSON array thay cho object, `username` vắng mặt, `password` bằng `null`, giá trị dạng số, trường thừa hoặc một JSON object chứa **hai trường trùng tên**. Khi đó, hệ thống nên xử lý **trước khi** chuyển sang bước kiểm tra mật khẩu.

`AuthenticationConverter` là một điểm mở rộng ở **Spring Security Servlet**: nó chuyển `HttpServletRequest` thành đối tượng `Authentication` **chưa được xác thực**, hoặc từ chối request không hợp lệ. `AuthenticationManager`/`AuthenticationProvider` mới kiểm chứng password, token, tài khoản và trạng thái; converter **không nên tự xác nhận đăng nhập thành công**.

Nếu không kiểm thử converter:
- JSON lỗi có thể gây `500` thay vì một lỗi có kiểm soát.
- Body thiếu password có thể tạo token với `credentials=null` hoặc chuỗi rỗng.
- Một JSON parser có thể ngầm ép số thành chuỗi hoặc bỏ qua trường trùng, khiến kiểm tra đầu vào mơ hồ.
- Converter có thể nuốt exception rồi trả `null`, làm `AuthenticationFilter` **bỏ qua** nỗ lực đăng nhập thay vì trả lỗi.
- Một URL không phải endpoint login có thể bị converter đọc body hoặc thử xác thực ngoài ý muốn.
- Test chỉ kiểm tra response `200` nên không biết converter đã tạo đúng loại `Authentication`, có còn `authenticated=false` hay đã làm rò password vào log.

**Sau bài này, bạn có thể:**
1. Phân biệt ba kết quả hợp lệ của converter: `null`, `Authentication` chưa authenticated và `AuthenticationException`.
2. Viết unit test với `MockHttpServletRequest`, JUnit 5 và AssertJ cho JSON hợp lệ, sai cú pháp, sai kiểu, thiếu trường, trùng trường và dư dữ liệu.
3. Viết integration test với `AuthenticationFilter` + `MockMvc` để kiểm tra đúng đường phản hồi `400` / `401` / `200`.
4. Đảm bảo JSON không hợp lệ không gọi `AuthenticationManager`.
5. Đặt giới hạn body/Content-Type, không parse credential ở sai endpoint và không lộ credential trong error.
6. Hiểu khác biệt giữa **payload validation**, **authentication** và **authorization**; biết trường hợp nào cần CSRF, rate limit, chống brute force.
7. Chạy một project Java 17/Spring Boot 3.3.x có code minh họa khép kín, các lệnh build/test và kỳ vọng kết quả đáng tin.

> **Phạm vi:** Spring MVC/Servlet với `org.springframework.security.web.authentication.AuthenticationConverter`. Với WebFlux, API tương ứng là `ServerAuthenticationConverter` nhận `ServerWebExchange` và trả `Mono<Authentication>`; không được áp dụng nguyên code Servlet cho reactive.

## 2. AuthenticationConverter nằm ở đâu trong luồng xác thực?

Sơ đồ:

~~~text
HTTP POST /auth/login
        |
        v
SecurityFilterChain
        |
        v
AuthenticationFilter + RequestMatcher
        |
        +-- Request KHÔNG match -> bỏ qua filter, tiếp tục chain
        |
        v
AuthenticationConverter.convert(request)
        |
        +-- null -> không thử xác thực, tiếp tục chain
        |
        +-- AuthenticationException -> failure handler, không gọi Manager
        |
        +-- UsernamePasswordAuthenticationToken.unauthenticated(...)
                              |
                              v
                        AuthenticationManager
                              |
                 +------------+-------------+
                 |                          |
           Sai credentials               Đúng credentials
                 |                          |
                 v                          v
         AuthenticationException      Authenticated token
                 |                          |
                 v                          v
           Failure handler             Success handler
                 |                          |
                 v                          v
         401 / lỗi chung               200 / kết quả login
~~~

Theo Java API Spring Security, `AuthenticationConverter` định nghĩa:

~~~java
@FunctionalInterface
public interface AuthenticationConverter {
    Authentication convert(HttpServletRequest request);
}
~~~

Đây là **dạng rút gọn để giải thích hợp đồng**, không phải mã nguồn nguyên văn của framework. Chữ ký thực tế có thể có annotation nullability và `@FunctionalInterface` tùy phiên bản. Giá trị `null` biểu thị **không tạo authentication attempt**; một `AuthenticationException` có thể báo credential scheme/payload không hợp lệ.

### 2.1. Phân biệt ba kết quả

| Request | Kết quả converter nên tạo | Bước tiếp theo |
| --- | --- | --- |
| `GET /public`, không thuộc endpoint login | `null` | Filter không xử lý login |
| `POST /auth/login` với đúng contract | `Authentication` **isAuthenticated=false** | `AuthenticationManager` kiểm chứng |
| `POST /auth/login` JSON thiếu field/sai kiểu | Ném `AuthenticationException` chuyên biệt | Failure handler trả lỗi có kiểm soát |
| `POST /auth/login` chứa password đúng nhưng account disabled | Converter tạo token chưa xác thực | Manager/provider từ chối dựa trên account status |
| `POST /auth/login` username hợp lệ, password sai | Converter tạo token chưa xác thực | Manager/provider từ chối, không để converter tự xử lý |
| `POST /auth/login` gửi JWT/Bearer header nhưng contract là JSON username/password | Không tự fallback sang cơ chế khác | Chính sách chain xác định được dùng hay không |

**Chỉ trả `null` khi không có nỗ lực xác thực mà converter phụ trách**, chẳng hạn đường dẫn/phương thức không match. Nếu endpoint đã được chọn và body **sai**, nên báo lỗi rõ ràng thay vì nuốt lỗi rồi return null.

### 2.2. Các thành phần phải test ở đúng tầng

- **Converter unit test:** request → Authentication/exception. Không cần database, password hashing thật, servlet server hoặc Spring application context.
- **AuthenticationManager/Provider test:** credential + user store → Authentication thành công/thất bại. Không cần JSON body.
- **Filter test:** converter result → Manager được gọi hoặc không; success/failure handler, status, SecurityContext.
- **MockMvc integration test:** gửi HTTP POST thực tế qua `SecurityFilterChain`, kiểm tra HTTP status/body/header, không có session ngầm hoặc auth bypass.
- **Browser/E2E test:** cookie/session, CSRF, CORS và frontend behavior khi có trình duyệt thật; `MockMvc` không thay toàn bộ browser.

## 3. Thiết kế contract cho JSON login

Chọn trước contract thay vì để parser tự suy đoán:

~~~http
POST /auth/login HTTP/1.1
Host: api.example.org
Content-Type: application/json; charset=UTF-8

{"username":"alice","password":"correct-password"}
~~~

Contract mẫu trong bài:

| Thành phần | Quy tắc lab | Vì sao |
| --- | --- | --- |
| Method/path | Chính xác `POST /auth/login` | Không biến request khác thành login |
| Content-Type | `application/json`, UTF-8 | Không parse form-data hay `text/plain` như JSON |
| Body size | Tối đa **4096 byte** | Tránh đọc body khổng lồ để thử đăng nhập |
| Root JSON | Một **object**, không phải array/string/number | Dễ xác minh schema |
| `username` | String, 3–64 ký tự, mẫu `[A-Za-z0-9._@-]+` | Quy tắc lab rõ ràng, không dùng coerced types |
| `password` | String, 8–128 ký tự, không blank | Không cấp token thiếu credential |
| Field khác | Không cho phép trong lab | Chặn mass assignment và request mơ hồ |
| JSON duplicate key | Từ chối | Không chọn “first wins” hoặc “last wins” |
| Dư token JSON sau object | Từ chối | Tránh parser chấp nhận phần đầu và bỏ phần sau |
| Lỗi schema/syntax | `400 Bad Request` | Client đã gửi login request nhưng sai contract |
| Password/username không hợp lệ | `401` với thông báo chung | Không tiết lộ account có tồn tại hay không |
| Đúng credential | `200` trong lab | Chỉ là demo thành công, chưa cấp session/token production |

**Không coi bảng này là password policy tiêu chuẩn cho tất cả sản phẩm.** Username có thể là email Unicode, số điện thoại, UUID hoặc user handle; password policy cần hỗ trợ độ dài, passphrase, Unicode và cơ chế kiểm tra mật khẩu bị lộ theo nhu cầu sản phẩm. Ở đây chỉ cố định input để test dễ lặp lại.

### 3.1. JSON lỗi có nhiều loại

**Sai cú pháp**:

~~~json
{"username":"alice","password":
~~~

**Thiếu trường**:

~~~json
{"username":"alice"}
~~~

**Sai kiểu**:

~~~json
{"username":42,"password":"correct-password"}
~~~

**Giá trị null**:

~~~json
{"username":"alice","password":null}
~~~

**Trường lặp**:

~~~json
{"username":"alice","password":"first","password":"second"}
~~~

**Root sai dạng**:

~~~json
["alice","correct-password"]
~~~

**Dư field**:

~~~json
{"username":"alice","password":"correct-password","role":"ADMIN"}
~~~

Các mẫu có thể là JSON sai schema hoặc đúng JSON về cú pháp. Đừng chỉ test `JsonParseException`, vì một object thiếu field vẫn là JSON **hợp lệ về cú pháp**. Các rủi ro authentication phụ thuộc cả syntax, schema và business validation.

## 4. Chọn status code và exception đúng tầng

Một converter **không nên tự ghi HTTP response**. Nó chỉ trả Authentication hoặc ném `AuthenticationException`. Một `AuthenticationFailureHandler` có thể phân loại:

| Kết quả | Loại exception | HTTP mẫu |
| --- | --- | --- |
| Bad JSON / thiếu trường / Content-Type sai | `InvalidLoginRequestException` (subclass `AuthenticationException`) | 400 |
| Username không có hoặc password sai | `BadCredentialsException` từ Provider | 401 |
| Account disabled/locked | `DisabledException` / `LockedException` | 401 hoặc policy tương ứng; response không tiết lộ chi tiết |
| Thành công | Authenticated result từ Manager | 200 trong lab |
| Converter được gọi nhầm endpoint | Trả `null` (không phải lỗi JSON) | Endpoint ngoài login xử lý theo chain |
| Server thật sự gặp lỗi không lường trước | Lỗi hệ thống được log an toàn | 5xx, không giả làm 400 rồi giấu lỗi |

Trong lab, lỗi payload trả body cố định `{"error":"INVALID_REQUEST"}`, lỗi credential trả `{"error":"BAD_CREDENTIALS"}`. Không echo username/password, raw body, parsing stack trace hoặc hash password vào response. Không kể “account đã tồn tại” khi credential sai.

**Lưu ý HTTP authentication:** HTTP `401` thường đi kèm `WWW-Authenticate` challenge nếu API dùng một HTTP authentication scheme. JSON-login credential exchange là một contract ứng dụng cụ thể; nếu triển khai hệ thống tuân theo HTTP challenge–response hoặc kết hợp Basic/Bearer, hãy định nghĩa/giữ đúng challenge theo RFC 9110 và filter chain thực tế. Đừng trả `401` giả dạng `Bearer invalid_token` khi vấn đề là password JSON.

## 5. Một project Spring Boot 3.3.12 / Java 17 tự chứa

Project lab nhận JSON login và chỉ minh họa **authentication step**; không phát access token hay cookie đăng nhập. Điều này giúp bộ test tập trung vào converter và filter. Cấu hình mẫu dùng `SessionCreationPolicy.STATELESS`, tắt form login/Basic và chỉ cho phép `POST /auth/login`.

Cấu trúc:

~~~text
json-converter-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/jsonauth/
    │   ├── JsonAuthApplication.java
    │   ├── JsonLoginAuthenticationConverter.java
    │   └── SecurityConfig.java
    └── test/java/demo/jsonauth/
        ├── JsonLoginAuthenticationConverterTest.java
        ├── AuthenticationFilterTest.java
        └── JsonLoginHttpTest.java
~~~

### 5.1. Gradle và dependencies

`settings.gradle`:

~~~groovy
rootProject.name = 'json-converter-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.12'
    id 'io.spring.dependency-management' version '1.1.7'
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
~~~

Spring Boot starter Web mang Jackson cho JSON parsing, Starter Security mang `AuthenticationFilter`/`AuthenticationConverter`, Spring Security Test và starter-test mang MockMvc/JUnit/AssertJ/Mockito. **Không cần tự thêm Jackson ở version khác** trừ khi BOM của project được quản trị phù hợp.

`src/main/java/demo/jsonauth/JsonAuthApplication.java`:

~~~java
package demo.jsonauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonAuthApplication.class, args);
    }
}
~~~

## 6. Viết JsonLoginAuthenticationConverter

**Yêu cầu thực thi:**
- Chỉ nhận một POST JSON đúng đường dẫn; sai path/method → `null`, không đọc body.
- Không sử dụng `request.getParameter("username")` như fallback: dữ liệu nằm trong JSON body.
- Đọc **tối đa 4097 byte** để phát hiện payload quá 4096 byte.
- Bật duplicate-key detection, kiểm tra root object và **trailing tokens**.
- Kiểm tra type, size, field chính xác. Không tạo Authentication khi payload không đạt.
- Trả `UsernamePasswordAuthenticationToken.unauthenticated(...)` để Provider thực hiện authentication.
- Không log dữ liệu raw request, password hay exception detail vào response.

`src/main/java/demo/jsonauth/JsonLoginAuthenticationConverter.java`:

~~~java
package demo.jsonauth;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletRequest;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.http.MediaType;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationConverter;

public final class JsonLoginAuthenticationConverter
        implements AuthenticationConverter {

    private static final int MAX_BODY_BYTES = 4096;
    private static final String LOGIN_PATH = "/auth/login";
    private final ObjectMapper mapper;

    public JsonLoginAuthenticationConverter(ObjectMapper objectMapper) {
        // ObjectMapper phải được cấu hình xong trước khi chia sẻ giữa threads.
        // copy() để không thay đổi ObjectMapper toàn ứng dụng.
        this.mapper = objectMapper.copy()
                .enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);
    }

    @Override
    public Authentication convert(HttpServletRequest request)
            throws AuthenticationException {

        // Không nhận request thuộc đường dẫn hay phương thức khác.
        if (!"POST".equals(request.getMethod())
                || !LOGIN_PATH.equals(request.getServletPath())) {
            return null;
        }

        final MediaType mediaType;
        try {
            mediaType = MediaType.parseMediaType(
                    request.getContentType() == null
                            ? "" : request.getContentType());
        } catch (IllegalArgumentException invalidContentType) {
            throw invalid();
        }

        if (!MediaType.APPLICATION_JSON.isCompatibleWith(mediaType)
                || (mediaType.getCharset() != null
                    && !StandardCharsets.UTF_8.equals(mediaType.getCharset()))) {
            throw invalid();
        }

        final byte[] bytes;
        try {
            // readNBytes(4097) cấp phát tối đa 4097 byte cho body,
            // đủ để phát hiện body vượt quá giới hạn lab.
            bytes = request.getInputStream()
                    .readNBytes(MAX_BODY_BYTES + 1);
        } catch (IOException readFailure) {
            throw invalid();
        }

        if (bytes.length == 0 || bytes.length > MAX_BODY_BYTES) {
            throw invalid();
        }

        final JsonNode root;
        try (JsonParser parser = mapper.getFactory().createParser(bytes)) {
            root = mapper.readTree(parser);

            // Không được chỉ parse object đầu rồi bỏ qua phần dư.
            if (root == null || !root.isObject()
                    || parser.nextToken() != null) {
                throw invalid();
            }
        } catch (JsonProcessingException malformedJson) {
            throw invalid();
        } catch (IOException parserFailure) {
            throw invalid();
        }

        // Hợp đồng lab chỉ cho phép đúng hai thuộc tính.
        JsonNode usernameNode = root.get("username");
        JsonNode passwordNode = root.get("password");

        if (root.size() != 2 || usernameNode == null
                || passwordNode == null
                || !usernameNode.isTextual()
                || !passwordNode.isTextual()) {
            throw invalid();
        }

        String username = usernameNode.textValue();
        String password = passwordNode.textValue();

        if (!username.matches("[A-Za-z0-9._@-]{3,64}")
                || password.length() < 8 || password.length() > 128
                || password.isBlank()) {
            throw invalid();
        }

        // Đây chỉ là Authentication CHƯA xác thực.
        // Không setAuthenticated(true), không hash/compare password ở đây.
        return UsernamePasswordAuthenticationToken.unauthenticated(
                username, password);
    }

    private static InvalidLoginRequestException invalid() {
        return new InvalidLoginRequestException();
    }

    public static final class InvalidLoginRequestException
            extends AuthenticationException {
        public InvalidLoginRequestException() {
            // Message cố định; không chèn raw body hay credential.
            super("Invalid login request");
        }
    }
}
~~~

### 6.1. Đọc kỹ tính đúng đắn của từng nhánh

**Nhánh A — không match:** `GET /auth/login` hoặc `POST /other` trả `null` trước khi parser chạm vào body. `AuthenticationFilter` có `RequestMatcher` riêng, nhưng việc converter tự kiểm tra method/path cũng hữu ích khi unit test hoặc tái sử dụng converter ở một nơi khác.

**Nhánh B — Content-Type sai:** `text/plain`, `application/x-www-form-urlencoded` hoặc thiếu Content-Type đều là lỗi 400 theo contract lab. Không phân tích body như một loại khác hoặc fallback form parameter. `MediaType.parseMediaType` hỗ trợ `application/json;charset=UTF-8`; request `application/json;charset=ISO-8859-1` bị lab từ chối.

**Nhánh C — dữ liệu lớn:** `readNBytes(MAX_BODY_BYTES + 1)` kiểm soát số byte mà converter giữ trong memory. Giới hạn web server/gateway request size cần cấu hình độc lập; đừng tưởng đoạn này tự ngăn mọi chi phí streaming/DoS ở các lớp trước converter. Nên có rate limit ở ingress và timeout.

**Nhánh D — Jackson:** bật `STRICT_DUPLICATE_DETECTION` để phát hiện JSON object có hai `password`; kiểm tra `parser.nextToken()` để phát hiện một JSON document thứ hai đính ngay sau document đầu. Nếu parser không bật chế độ strict, behavior mặc định có thể là giá trị cuối **ghi đè** giá trị trước, không phải một contract an toàn cho authentication.

**Nhánh E — schema:** `root.size()==2` và `isTextual()` chặn trường thiếu, null, object/array/number/boolean, trường thừa như `role`. JSON `{"username":"alice","password":null}` không được xem là password chuỗi `"null"`.

**Nhánh F — token chưa xác thực:** `UsernamePasswordAuthenticationToken.unauthenticated` có `isAuthenticated()==false`. `AuthenticationManager` mới được quyền biến token thành authenticated result sau khi kiểm tra password và trạng thái account.

**Đặc biệt:** converter này không chấp nhận cookie/header/token nào làm credential thay thế. Nếu một hệ thống hỗ trợ nhiều authentication schemes, thiết kế tách converter/filter và request matcher rõ ràng; không tự “tìm credential ở đâu cũng được” để qua kiểm thử.

### 6.2. Những điểm production cần mở rộng

Hợp đồng lab dùng username ASCII để cô lập test; production cần policy email/Unicode/IDN thống nhất, không làm mất danh tính bằng `trim`/lowercase tùy tiện. Password là thông tin nhạy cảm: không log, không include trong metrics/exception, để `ProviderManager` hoặc custom auth provider quản lý clearing và kiểm tra hash. Đối với xác thực browser/session, cần CSRF, chống login CSRF, session fixation protections và cookie settings. Với API thật, nên có adaptive password hashing, MFA, rate limit/throttle và user enumeration mitigation.

**Không nên bỏ qua exception do đọc InputStream vì “JSON của client bị lỗi”.** Trong lab chúng ta map lỗi đọc stream sang 400 theo contract đơn giản; production có thể phân biệt lỗi kết nối/body truncation với lỗi client rõ ràng, đồng thời vẫn không lộ thông tin nhạy cảm.

## 7. Tích hợp AuthenticationFilter và AuthenticationManager

`AuthenticationFilter` có constructor nhận `AuthenticationManager` và `AuthenticationConverter`. Bộ lọc:
1. Match request.
2. Gọi `convert(request)`.
3. Nếu được token → gọi `AuthenticationManager.authenticate(token)`.
4. Khi thành công → gọi `AuthenticationSuccessHandler`.
5. Khi lỗi `AuthenticationException` → gọi `AuthenticationFailureHandler`.

Ví dụ chọn **một** cơ chế xác thực JSON, không tự tạo cookie/session. Điều này cho phép kiểm thử rõ việc input không hợp lệ không biến thành credential đã được xác thực.

`src/main/java/demo/jsonauth/SecurityConfig.java`:

~~~java
package demo.jsonauth;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFilter;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder encoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("lab-password-123"))
                        .roles("USER")
                        .build());
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider dao = new DaoAuthenticationProvider();
        dao.setUserDetailsService(users);
        dao.setPasswordEncoder(encoder);
        return new ProviderManager(dao);
    }

    @Bean
    JsonLoginAuthenticationConverter jsonConverter(ObjectMapper mapper) {
        return new JsonLoginAuthenticationConverter(mapper);
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http,
            JsonLoginAuthenticationConverter converter,
            AuthenticationManager manager) throws Exception {

        AuthenticationFilter loginFilter =
                new AuthenticationFilter(manager, converter);

        loginFilter.setRequestMatcher(
                new AntPathRequestMatcher("/auth/login", "POST"));

        loginFilter.setSuccessHandler((request, response, auth) -> {
            response.setHeader("Cache-Control", "no-store");
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setStatus(200);
            response.getWriter().write(
                    "{\"status\":\"AUTHENTICATED\"}");
        });

        loginFilter.setFailureHandler((request, response, error) -> {
            boolean badInput = error instanceof
                    JsonLoginAuthenticationConverter.InvalidLoginRequestException;
            response.setHeader("Cache-Control", "no-store");
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setStatus(badInput ? 400 : 401);
            response.getWriter().write(
                    badInput
                            ? "{\"error\":\"INVALID_REQUEST\"}"
                            : "{\"error\":\"BAD_CREDENTIALS\"}");
        });

        return http
                // Chỉ là login giao tiếp JSON stateless trong lab,
                // không dùng cookie/session trình duyệt làm credential.
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(s -> s
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .requestCache(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .authorizeHttpRequests(a -> a
                        .requestMatchers(HttpMethod.POST,
                                "/auth/login").permitAll()
                        .anyRequest().denyAll())
                .addFilterAt(loginFilter,
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
~~~

### 7.1. Những lưu ý về cấu hình

- `DaoAuthenticationProvider` đọc `UserDetailsService` và so password theo `PasswordEncoder`. Password demo chỉ dành cho local; lưu hash qua DelegatingPasswordEncoder.
- `AuthenticationFilter` được khởi tạo **trong SecurityFilterChain**, không gắn `@Component`. Tránh vô tình được Spring Boot đăng ký như Servlet Filter bên ngoài `FilterChainProxy`, dẫn đến chạy hai lần/sai thứ tự.
- `new AntPathRequestMatcher("/auth/login","POST")` buộc đúng HTTP method/path. Converter cũng kiểm tra lại để test direct.
- `addFilterAt(..., UsernamePasswordAuthenticationFilter.class)` đặt JSON authentication filter tại vị trí biết trước trong Spring Security filter order; form login đã tắt nên không có hai login filter cùng hoạt động.
- `STATELESS` là **chính sách lab**: response 200 ở đây có nghĩa credential đã được kiểm tra, **không** phát cookie/session/JWT để dùng cho request sau. Production cần thiết kế authentication/session/token issuance riêng, không coi status 200 là đăng nhập bền vững.
- `csrf.disable()` **chỉ được cân nhắc** vì demo không dùng browser cookie/session/HTTP Basic làm auto-sent credential. Nếu frontend thực tế sử dụng session cookie, login CSRF và các request thay đổi trạng thái vẫn phải được bảo vệ; không copy dòng đó sang flow browser.
- Failure handler phân loại **lỗi payload** (400) và **credential sai** (401), đều trả body cố định; không sử dụng `error.getMessage()`/`getCause()` để làm response.
- Không tạo authentication khi password rỗng hoặc không đạt schema. Không dùng user-provided `role`, `authenticated` hay `scope` để cấp quyền.

### 7.2. Phân biệt JSON parser exception với auth exception

Một converter có thể bắt `JsonProcessingException` từ Jackson, nhưng `AuthenticationFilter` xử lý lỗi bằng `AuthenticationException`. Vì vậy converter **chuyển lỗi JSON** sang một subclass cụ thể của `AuthenticationException`; không để exception do parser trôi ra rồi thành `500`.

Đừng map **mọi** `RuntimeException` sang invalid login. NullPointerException do bug, lỗi kết nối user store hay lỗi cấu hình có thể là **sự cố backend**, cần 5xx và alarm an toàn chứ không phải bị giấu thành 400. Bắt đúng kiểu lỗi ở đúng tầng.

## 8. Unit test converter với MockHttpServletRequest

Unit test có nhiều lợi thế: nhanh, không cần Spring context, không kích hoạt database/service và không cần lắng nghe TCP port. `MockHttpServletRequest` cho phép đặt HTTP method, path, Content-Type và request body.

`src/test/java/demo/jsonauth/JsonLoginAuthenticationConverterTest.java`:

~~~java
package demo.jsonauth;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;

import static org.assertj.core.api.Assertions.*;

class JsonLoginAuthenticationConverterTest {

    private final JsonLoginAuthenticationConverter converter =
            new JsonLoginAuthenticationConverter(new ObjectMapper());

    private static MockHttpServletRequest request(
            String method, String path, String contentType, String body) {

        MockHttpServletRequest req =
                new MockHttpServletRequest(method, path);
        req.setServletPath(path);
        if (contentType != null) {
            req.setContentType(contentType);
        }
        req.setContent(body.getBytes(StandardCharsets.UTF_8));
        return req;
    }

    private static MockHttpServletRequest json(String body) {
        return request("POST", "/auth/login",
                "application/json", body);
    }

    @Test
    void validJsonProducesUnauthenticatedToken() {
        Authentication auth = converter.convert(json("""
                {"username":"alice","password":"lab-password-123"}
                """));

        assertThat(auth).isInstanceOf(
                UsernamePasswordAuthenticationToken.class);
        assertThat(auth.isAuthenticated()).isFalse();
        assertThat(auth.getName()).isEqualTo("alice");
        assertThat(auth.getCredentials()).isEqualTo(
                "lab-password-123");
        assertThat(auth.getAuthorities()).isEmpty();
    }

    @Test
    void unrelatedPathOrMethodDoesNotAttemptAuthentication() {
        assertThat(converter.convert(request(
                "GET", "/auth/login", "text/plain", "not json")))
                .isNull();
        assertThat(converter.convert(request(
                "POST", "/unrelated", "text/plain", "not json")))
                .isNull();
    }

    @Test
    void malformedJsonFailsClosed() {
        assertThatThrownBy(() -> converter.convert(
                json("{\"username\":\"alice\",\"password\":")))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
    }

    @Test
    void missingUsernameOrPasswordIsRejected() {
        assertThatThrownBy(() -> converter.convert(
                json("{\"username\":\"alice\"}")))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
        assertThatThrownBy(() -> converter.convert(
                json("{\"password\":\"lab-password-123\"}")))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
    }

    @Test
    void emptyBodyAndNullAreRejected() {
        assertThatThrownBy(() -> converter.convert(json("")))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
        assertThatThrownBy(() -> converter.convert(
                json("{\"username\":\"alice\",\"password\":null}")))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
    }

    @Test
    void wrongTypesAndRootShapeAreRejected() {
        assertThatThrownBy(() -> converter.convert(
                json("{\"username\":42,\"password\":\"lab-password-123\"}")))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
        assertThatThrownBy(() -> converter.convert(
                json("[\"alice\",\"lab-password-123\"]")))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
    }

    @Test
    void duplicateKeysAndTrailingJsonAreRejected() {
        assertThatThrownBy(() -> converter.convert(json("""
                {"username":"alice","password":"abc-12345678",
                 "password":"lab-password-123"}
                """)))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);

        assertThatThrownBy(() -> converter.convert(json("""
                {"username":"alice","password":"lab-password-123"}
                {"second":"object"}
                """)))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
    }

    @Test
    void extraFieldsCannotControlRoles() {
        assertThatThrownBy(() -> converter.convert(json("""
                {"username":"alice","password":"lab-password-123",
                 "role":"ADMIN"}
                """)))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
    }

    @Test
    void incorrectContentTypeIsRejected() {
        assertThatThrownBy(() -> converter.convert(request(
                "POST", "/auth/login", "text/plain",
                "{\"username\":\"alice\",\"password\":\"lab-password-123\"}")))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
    }

    @Test
    void emptyOrShortCredentialsAreRejected() {
        assertThatThrownBy(() -> converter.convert(json("""
                {"username":"","password":"lab-password-123"}
                """)))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
        assertThatThrownBy(() -> converter.convert(json("""
                {"username":"alice","password":"  "}
                """)))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
    }

    @Test
    void oversizedBodyIsRejected() {
        String payload = "{\"username\":\"alice\",\"password\":\""
                + "x".repeat(5000) + "\"}";
        assertThatThrownBy(() -> converter.convert(json(payload)))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
    }
}
~~~

### 8.1. Điều gì được khẳng định?

11 bài test unit trên chỉ kiểm tra **converter**:
- Với JSON hợp lệ, tạo `Authentication` đúng principal/credentials, chưa được authenticated, **không cấp authorities**.
- JSON lỗi/thiếu trường/`null`/mảng/số/trường dư/trường trùng/trailing JSON/oversize đều là **exception xác thực kiểm soát được**.
- Sai path/method trả `null`, không parsing body.
- Password không bị converter tự mã hóa, so sánh hay gắn quyền; Provider xử lý bước đó.

Một test còn có thể dùng parameterized tests (JUnit 5 `@ParameterizedTest` + `@MethodSource`) để bao phủ hàng chục JSON input. Trong tài liệu này các case được viết tường minh để người học dễ thấy **mỗi rủi ro tương ứng một assert**.

### 8.2. Vì sao không chỉ test `assertNotNull(authentication)`?

Kiểm tra `notNull` không chứng minh:
- `authentication.isAuthenticated() == false`;
- Username lấy từ đúng field, không phải query parameter;
- Password chưa bị mất/trim/đổi encoding;
- Không có `ROLE_ADMIN` tự gắn;
- Input sai không tạo token và không gọi Manager;
- Body lớn không bị đọc vô hạn.

Unit test tốt có cả **trạng thái và tính âm tính**, không chỉ type check.

## 9. Filter-level unit test: JSON sai không chạm AuthenticationManager

Một converter sai vẫn có thể bị filter cấu hình không đúng. Ta có thể kiểm tra rằng `AuthenticationFilter` **không gọi `AuthenticationManager`** khi converter ném exception, và failure handler được chạy.

`src/test/java/demo/jsonauth/AuthenticationFilterTest.java`:

~~~java
package demo.jsonauth;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.web.authentication.AuthenticationFilter;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

class AuthenticationFilterTest {

    @Test
    void invalidPayloadDoesNotCallAuthenticationManager()
            throws Exception {

        AuthenticationManager manager = mock(AuthenticationManager.class);
        var converter =
                new JsonLoginAuthenticationConverter(new ObjectMapper());
        AuthenticationFilter filter =
                new AuthenticationFilter(manager, converter);

        filter.setRequestMatcher(
                new AntPathRequestMatcher("/auth/login", "POST"));
        filter.setFailureHandler((request, response, error) ->
                response.setStatus(400));

        MockHttpServletRequest request =
                new MockHttpServletRequest("POST", "/auth/login");
        request.setServletPath("/auth/login");
        request.setContentType("application/json");
        request.setContent(
                "{\"username\":\"alice\"}"
                        .getBytes(StandardCharsets.UTF_8));

        MockHttpServletResponse response =
                new MockHttpServletResponse();

        filter.doFilter(request, response, (req, res) -> {
            throw new AssertionError("Must not continue on bad JSON");
        });

        assertThat(response.getStatus()).isEqualTo(400);
        verifyNoInteractions(manager);
    }
}
~~~

**Giải thích:** nếu converter tạo một token dù thiếu `password`, `Manager.authenticate(...)` có thể được gọi, và test `verifyNoInteractions(manager)` sẽ thất bại. Kết quả 400 chỉ do **failure handler của test**, giúp cô lập converter/filter. Test này không xác minh password hoặc response JSON thật; mục 10 kiểm tra những phần đó qua Spring context/MockMvc.

Có thể bổ sung ca positive và xác nhận Manager nhận token chưa authenticated:

~~~java
// Trích đoạn mở rộng (chưa phải một @Test class độc lập):
// verify(manager).authenticate(argThat(auth ->
//     auth != null && !auth.isAuthenticated()
//     && "alice".equals(auth.getName())));
~~~

Test verification trên chỉ có ý nghĩa khi bạn thực sự thực thi request hợp lệ và setup mock AuthenticationManager trả authenticated result. Đừng chép comment này rồi tưởng đã có một bài test chạy.

## 10. MockMvc integration test: HTTP 400, 401, 200

`MockMvc` khởi chạy web application context và Spring Security filter chain mà không cần TCP port. Điều này phù hợp để test contract của `AuthenticationFilter`, error handler và provider với dữ liệu demo.

`src/test/java/demo/jsonauth/JsonLoginHttpTest.java`:

~~~java
package demo.jsonauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class JsonLoginHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validCredentialsReturn200() throws Exception {
        mvc.perform(post("/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"alice",
                                 "password":"lab-password-123"}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("AUTHENTICATED"))
                .andExpect(header().string("Cache-Control", "no-store"));
    }

    @Test
    void badPasswordReturns401WithoutUsernameLeak() throws Exception {
        mvc.perform(post("/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"alice",
                                 "password":"wrong-password-123"}
                                """))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error").value("BAD_CREDENTIALS"));
    }

    @Test
    void malformedJsonReturns400() throws Exception {
        mvc.perform(post("/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"alice\",\"password\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("INVALID_REQUEST"));
    }

    @Test
    void missingPasswordReturns400() throws Exception {
        mvc.perform(post("/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"alice\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("INVALID_REQUEST"));
    }

    @Test
    void wrongJsonTypeReturns400() throws Exception {
        mvc.perform(post("/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"alice",
                                 "password":12345}
                                """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void duplicatePasswordFieldReturns400() throws Exception {
        mvc.perform(post("/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"alice",
                                 "password":"lab-password-123",
                                 "password":"wrong-password-123"}
                                """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void contentTypeTextPlainReturns400() throws Exception {
        mvc.perform(post("/auth/login")
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("""
                                {"username":"alice",
                                 "password":"lab-password-123"}
                                """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void trailingJsonObjectReturns400() throws Exception {
        mvc.perform(post("/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"alice",
                                 "password":"lab-password-123"}
                                {"extra":true}
                                """))
                .andExpect(status().isBadRequest());
    }
}
~~~

**Kỳ vọng: 8 integration tests pass** với project/config được mô tả, khi chạy cùng dependency version phù hợp. Các test phân biệt:
- **400**: payload không đáp ứng JSON contract.
- **401**: payload hợp lệ nhưng credential không được provider chấp nhận.
- **200**: provider xác thực password đúng theo password hash trong `InMemoryUserDetailsManager`.

Những test này không assert “đã phát session”, vì **lab không phát session/token**. Với flow production thực sự, hãy kiểm thử cookie/session fixation/CSRF/token issuance, không coi một response 200 là bảo đảm user đã có session bền vững.

**Không tự động sửa test để chấp nhận 500 cho JSON sai.** Nếu một lỗi Jackson/Spring bị tuôn ra như 500, phải sửa converter/failure handler để xử lý một lỗi đầu vào dự kiến; nhưng những lỗi backend không lường trước vẫn cần alarm 5xx.

## 11. Chạy toàn bộ project và quan sát

Yêu cầu: JDK 17+ và Gradle tương thích với Spring Boot 3.3.x. Nếu project có Gradle Wrapper, dùng `./gradlew` hoặc `gradlew.bat` thay cho `gradle`.

~~~bash
# Tại thư mục project:
gradle test
gradle bootRun
~~~

Từ terminal khác, gửi một request JSON hợp lệ bằng curl tới **localhost**, chỉ dùng mật khẩu demo:

~~~bash
curl -i \
  -H 'Content-Type: application/json' \
  --data '{"username":"alice","password":"lab-password-123"}' \
  http://localhost:8080/auth/login
~~~

Phản hồi kỳ vọng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"status":"AUTHENTICATED"}
~~~

Thử JSON thiếu password:

~~~bash
curl -i \
  -H 'Content-Type: application/json' \
  --data '{"username":"alice"}' \
  http://localhost:8080/auth/login
~~~

Kỳ vọng:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{"error":"INVALID_REQUEST"}
~~~

Thử password sai:

~~~bash
curl -i \
  -H 'Content-Type: application/json' \
  --data '{"username":"alice","password":"wrong-password-123"}' \
  http://localhost:8080/auth/login
~~~

Kỳ vọng 401 với:

~~~json
{"error":"BAD_CREDENTIALS"}
~~~

**Lưu ý output:** Status/header/body ở trên thể hiện **contract dự định của lab**. Có thể có thêm headers do Spring Security và web container chèn; nội dung dòng status HTTP/1.1/HTTP/2 thay đổi theo client. Không coi các đoạn này là log thực tế đã chạy trong bài. Không in raw body/password vào log khi chạy production, không đưa password thật vào shell history bằng lệnh `curl --data`.

### 11.1. Expected test summary

Với project như trên:
- 11 test ở `JsonLoginAuthenticationConverterTest`.
- 1 test ở `AuthenticationFilterTest`.
- 8 test ở `JsonLoginHttpTest`.
- **Tổng dự kiến 20 tests.**

Đây là **kỳ vọng logic**, không phải chứng nhận test đã được thực thi trong môi trường hiện tại. Khi thực thi, nếu kết quả khác, hãy đọc error chi tiết của test runner, đối chiếu version dependency, `SecurityFilterChain` matcher và JSON parser settings; không “sửa nhanh” bằng cách bỏ test âm tính.

## 12. Kiểm thử ranh giới request và sự cố parser

Các ca cốt lõi còn nên bổ sung khi nâng cấp từ lab lên production:

| Case | Input | Kết quả an toàn |
| --- | --- | --- |
| Empty body | 0 byte | 400 |
| Whitespace-only body | `"   "` | 400 |
| JSON syntax wrong | Thiếu dấu } / dấu " | 400 |
| JSON `null` root | `null` | 400 |
| JSON array root | `[]` | 400 |
| JSON number root | `123` | 400 |
| JSON top-level string | `"hello"` | 400 |
| `username` missing | Chỉ `password` | 400 |
| `password` missing | Chỉ `username` | 400 |
| `username` null | `"username":null` | 400 |
| `password` null | `"password":null` | 400 |
| Wrong field type | Number/boolean/array/object | 400, không ép sang String |
| Duplicate JSON fields | Hai `password` | 400 |
| Trailing JSON | Hai JSON documents | 400 |
| Unexpected fields | `"isAdmin":true` | 400, không tạo authority |
| Username invalid format | Cấm theo contract lab | 400 |
| Password quá ngắn/rỗng | Chuỗi không đạt contract lab | 400 |
| Body lớn hơn 4096 byte | Quá giới hạn | 400 hoặc 413 theo contract production |
| Missing Content-Type | Không biết body encoding | 400 hoặc 415 theo contract production |
| `application/x-www-form-urlencoded` | Form body | Không tự fallback vào JSON login |
| `application/json;charset=UTF-8` | JSON hợp lệ | Được parse |
| `application/json;charset=ISO-8859-1` | Khác policy UTF-8 lab | 400 hoặc 415 |
| Query có `username/password` | Body không có | 400, không lấy query thay body |
| GET /auth/login | Sai method | Converter return null |
| POST /other | Sai path | Converter return null |
| Password sai | JSON hợp lệ | 401, không tiết lộ user tồn tại hay không |
| Account disabled | JSON hợp lệ | Provider chặn, response chung theo policy |
| Đúng password | JSON hợp lệ | Chỉ Manager mới xác thực |
| Body có UTF-8 không hợp lệ | Byte sequence sai | 400, không mù quáng thay ký tự |
| Request stream lỗi giữa chừng | InputStream throw IOException | Controlled failure theo contract; không lộ cause |
| Concurrent requests | Nhiều request độc lập | Không chia sẻ mutable parse state hoặc credential |

### 12.1. Multipart/form data không phải JSON credential

Một số ứng dụng hỗ trợ cả `POST /login` HTML form và `POST /auth/login` JSON. Nên thiết kế **hai request matchers/converters riêng**, không đoán bằng “nếu JSON parse lỗi thì thử `request.getParameter`”. Fallback kiểu đó khiến một request có thể được hiểu khác nhau giữa gateway, servlet container và ứng dụng. Bất kỳ vị trí nhận credential nào đều phải được tài liệu hóa rõ và kiểm thử.

### 12.2. Content-Length không phải giới hạn đủ

Một request dùng `Transfer-Encoding: chunked` có thể không có `Content-Length` biết trước. Nếu chỉ check `request.getContentLengthLong() > 4096` rồi parse toàn body, vẫn có thể đọc lượng dữ liệu rất lớn. Converter mẫu dùng `readNBytes(4097)` để phát hiện vượt ngưỡng, đồng thời cần cấu hình giới hạn request body ở gateway/container và timeout ở production.

### 12.3. Duplicate field và parser differences

JSON tiêu chuẩn cho phép cú pháp object nhưng kỳ vọng tên member duy nhất để interoperability. Parser A có thể lấy giá trị đầu, parser B lấy giá trị cuối, WAF có thể nhìn thấy một giá trị khác backend. Đối với trường **authentication**, khác biệt này nguy hiểm. Bật duplicate detection và test request đi qua gateway thực để đảm bảo các tầng không diễn giải khác nhau.

### 12.4. JSON số hoặc object không tự là username/password

Đoạn sau **không** hợp lệ theo contract:

~~~json
{"username":{"value":"alice"},"password":["one","two"]}
~~~

Nếu dùng Jackson databinding vào DTO có `String username`, một số cấu hình/coercion có thể biến số hoặc boolean thành text. Với JSON credential, kiểm tra `JsonNode.isTextual()` giúp xác định kiểu rõ ràng. Nếu dùng DTO, bật cơ chế validation và coercion phù hợp, không tin chỉ `@NotNull` là đủ để chặn mọi input sai kiểu.

## 13. Kiểm thử security properties ngoài JSON

Payload validation tốt vẫn không đủ nếu toàn bộ login flow thiếu bảo vệ:

### 13.1. Login CSRF và browser cookie

Lab ở trên **stateless** và không tạo cookie session. Nếu ứng dụng thực sử dụng session cookie hoặc browser tự gửi credential, **login CSRF** là một rủi ro riêng. Spring Security mặc định bảo vệ state-changing requests bằng CSRF token. Đừng tắt CSRF toàn hệ thống chỉ vì API có JSON body: JSON parse strict giúp giảm bề mặt tấn công nhưng không thay thế CSRF defense và CORS/Origin policy.

### 13.2. Rate limit, brute force, account enumeration

Client có thể gửi JSON hoàn toàn đúng nhưng thử vô hạn password:
- Rate limit theo IP, account ID/username, device và tenant, kết hợp policy abuse detection.
- Dùng response chung cho username không tồn tại và password sai.
- Kiểm soát khác biệt timing, message, metrics và side-channel.
- Không đưa password hoặc raw body vào access log, application exception, APM, test logs và analytics.
- Mật khẩu do người dùng chọn phải hash bằng adaptive `PasswordEncoder` và có chính sách reset/lockout phù hợp.

### 13.3. Mass assignment và credential leakage

Không bao giờ parse các trường do client gửi như `roles`, `authorities`, `enabled`, `authenticated` để đưa vào Authentication:
- Converter chỉ dùng `username`, `password`.
- Provider đọc roles và account status từ nguồn tin cậy.
- Failure handler không trả raw request body trong `error_description`.
- Không truyền password sang response JSON, cookie, URL, redirect hoặc log.
- Sau khi authentication thành công, nên xóa credentials trong manager/context theo policy; tránh lưu raw password quá thời gian cần thiết.

### 13.4. Không để một exception generic che lỗi ứng dụng

Một anti-pattern:

~~~java
// MINH HỌA CÁCH KHÔNG NÊN VIẾT:
try {
    return parser.parse(request);
} catch (Exception everything) {
    return null;
}
~~~

Lỗi parse sẽ bị biến thành “không có nỗ lực đăng nhập”, hoặc bug backend bị che khuất. Thay vào đó:
- Bắt `JsonProcessingException`/`IOException` ở parser như lỗi request theo policy.
- Chuyển sang `AuthenticationException` có loại cụ thể.
- Để hệ thống log/alert lỗi server khác theo chính sách; không trả stack trace cho client.
- Test riêng behavior `null` và exception của converter.

## 14. Khi nào dùng unit test, MockMvc và integration thật?

| Lớp kiểm thử | Bắt được lỗi nào? | Không chứng minh |
| --- | --- | --- |
| Pure unit với `MockHttpServletRequest` | JSON syntax/schema, phương thức/path, token chưa auth | Filter đã được cắm đúng vào chain |
| Filter unit với Mockito Manager | JSON sai không gọi auth manager, failure handler | Provider/DB/web configuration thật |
| `@SpringBootTest + @AutoConfigureMockMvc` | Spring Security chain, HTTP status/body, Provider demo | TLS/proxy/browser/CSRF đầy đủ |
| Controller/contract tests | Content-Type, error JSON, auth headers theo policy | Username/password lifecycle production |
| Browser E2E trên HTTPS staging | Cookie/CSRF/CORS/network behavior | Quy trình nhiều server/data race nếu thiếu setup |
| Test gateway/container | Content size, encoding, proxy normalization, rate limit | Business permission trên từng object nếu không test riêng |

Một bộ test tốt có **nghiệp vụ kiểm tra độc lập với kỹ thuật framework**: thiếu password không được authenticate; sai type không thể thành principal; sai password không được nhận response thành công; JSON trùng field không được một lớp bảo mật xem là giá trị khác tầng sau.

Để viết test lâu bền:
1. Kiểm tra output/side effects hơn là assert mọi internal method call.
2. Dùng test data giả, không ghi password/token thật vào logs.
3. Đặt test name theo kịch bản và kết quả bảo mật mong đợi.
4. Tách unit tests nhanh ra khỏi integration tests nặng.
5. Dùng `@ParameterizedTest` khi có hàng chục biến thể JSON.
6. Thêm boundary test: độ dài 4096/4097 byte, password 7/8/128/129 ký tự.
7. Kiểm tra filter order và requestMatcher sau khi đổi Spring Security version.
8. Đảm bảo result `null` của converter trên non-login **không** mở một endpoint protected ngoài ý muốn.

## 15. Các lỗi thực tế và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Sửa đúng |
| --- | --- | --- |
| JSON lỗi trả 500 | Json exception không được converter chuyển thành auth exception | Bắt lỗi parse cụ thể, map thành 400 |
| Thiếu password vẫn tạo token | Check null nhưng không check schema/type/empty | Validate required fields, type, length trước khi tạo token |
| JSON có 2 password mà vẫn login | Parser cho duplicate keys | Bật strict duplicate detection |
| JSON có trailing object nhưng thành công | Parser chỉ đọc document đầu | Gọi `nextToken()` kiểm tra EOF |
| `{"username":42}` được coi là `"42"` | Databinding/coercion | Parse `JsonNode` và kiểm tra `isTextual` |
| Form params vào được JSON login | Fallback từ body sang `getParameter` | Chỉ một nguồn canonical cho credential |
| Test converter pass nhưng HTTP 404 | Filter matcher/order/path không đúng | Kiểm tra chain và `RequestMatcher` |
| Error 403 khi POST login | CSRF vẫn bật cho flow browser | Bảo vệ/gửi token đúng; không tắt CSRF vô điều kiện |
| Error 401 cho malformed JSON | Failure handler gộp lỗi credential và payload | Phân loại `InvalidLoginRequestException` |
| Server trả 200 cho password sai | Manager stub trả success không xét input | Unit Manager test và MockMvc dùng provider thật |
| Unexpected `ROLE_ADMIN` xuất hiện | Client roles bị tin cậy | Server-side authority mapping |
| Request body lớn gây memory pressure | Parse không giới hạn | Bounded read + gateway/body limit + timeout |
| Credential lọt vào log | Log raw request, body, exception | Redaction, logging allowlist, retention |
| Test pass trên MockMvc nhưng gateway 413 | Gateway có giới hạn khác | Đồng bộ contract và test end-to-end |
| Một bug NullPointerException thành 400 | `catch(Exception)` quá rộng | Phân biệt client parsing và server bugs |
| Login 200 nhưng request sau vẫn chưa auth | Endpoint chỉ trả 200, không phát session/token | Thiết kế rõ session/token lifecycle |
| Duplicate converter/filter chạy hai lần | Gắn `@Component` và addFilter cùng lúc | Đăng ký filter đúng một lần |
| Cookie/JWT tự gửi nhưng CSRF bị tắt | Nhầm JSON format với threat model | Áp dụng CSRF theo auth transport |

## 16. Bài tập tự kiểm tra

**Câu 1.** `AuthenticationConverter.convert()` trả `null` khi nào?  
**Đáp án:** Khi converter **không thực hiện authentication attempt** cho request, chẳng hạn request ngoài phạm vi. Với login JSON sai, nên ném một `AuthenticationException` cụ thể, không trả null để bỏ qua lỗi.

**Câu 2.** JSON `{"username":"alice"}` đúng cú pháp nhưng có nên tạo `UsernamePasswordAuthenticationToken`?  
**Không.** Thiếu `password` so với contract, phải từ chối trước khi gọi Provider.

**Câu 3.** Parser đọc được JSON `{"password":"A","password":"B"}`. Có nên dùng giá trị cuối?  
**Không.** Từ chối duplicate keys vì cách hiểu mơ hồ giữa parser/proxy/validator có thể dẫn đến bypass.

**Câu 4.** Converter trả token `isAuthenticated=true` ngay sau khi đọc JSON có mật khẩu?  
**Sai nghiêm trọng.** Converter không xác minh password; chỉ Manager/Provider có đủ quyền xác thực và tạo authenticated result.

**Câu 5.** Sai mật khẩu và sai JSON có bắt buộc cùng HTTP status không?  
**Không.** Có thể phân loại payload invalid 400 và credentials invalid 401 theo API contract, đồng thời tránh lộ username tồn tại.

**Câu 6.** Kiểm tra `Content-Length < 4096` đã bảo đảm request không quá 4096 byte?  
**Chưa.** Request chunked có thể không biết length; phải giới hạn lượng byte thực sự đọc và cấu hình gateway/container.

**Câu 7.** Test `MockMvc` trả 200 chứng minh browser giữ session sau login?  
**Không.** Lab stateless không phát session. Muốn đăng nhập có hiệu lực ở request sau cần triển khai và kiểm thử session/token issuance cụ thể.

**Câu 8.** `@SpringBootTest` có thay thế unit test converter không?  
**Không hoàn toàn.** Unit test xác minh từng nhánh nhanh và chính xác; integration test kiểm tra wiring/filter/error responses. Hai tầng bổ sung nhau.

**Câu 9.** Một JSON object có `{"username":"alice","password":"correct","role":"ADMIN"}`. Có nên đọc `role` vào authorities?  
**Không.** Authorities phải từ user store/policy đáng tin cậy; lab từ chối fields ngoài schema.

**Câu 10.** Lỗi `JsonParseException` trôi ra khỏi converter rồi nhận 500. Ai nên chuyển nó thành lỗi 400?  
**Converter hoặc adapter parsing** nhận biết lỗi client và chuyển thành exception chuyên biệt; handler trả mã chung phù hợp. Không catch mọi runtime exception.

## 17. Checklist trước khi đưa JSON AuthenticationConverter vào production

- [ ] Chỉ xử lý đúng endpoint/method/content type; ngoài phạm vi trả null không đọc body.
- [ ] JSON parser dùng UTF-8, có body-size limit, depth/constraints phù hợp và strict duplicate-key policy.
- [ ] Không cho phép trailing JSON, root không phải object hoặc field type bị coercion âm thầm.
- [ ] Các trường bắt buộc, length/format và null/blank được kiểm tra rõ.
- [ ] Converter chỉ tạo unauthenticated token; không cấp quyền/role theo client.
- [ ] JSON errors không thành 500, không thành success và không gọi AuthenticationManager.
- [ ] Credential failures có status chung, không user enumeration, không rò raw password/exception.
- [ ] HTTP filter/request matcher/CSRF/session policy phù hợp browser hoặc machine-to-machine use case thực.
- [ ] PasswordEncoder, UserDetailsService, account lock/expiry/disabled, MFA và rate limit được kiểm soát.
- [ ] Unit tests cover missing/null/wrong type/duplicate/extra/trailing/oversize/bad Content-Type.
- [ ] Filter tests xác nhận Manager không bị gọi khi payload sai.
- [ ] MockMvc kiểm tra 200/400/401 cùng body/header/side effects đúng contract.
- [ ] Không log request credential; bảo vệ TLS, observability, gateway và retention.
- [ ] Test qua reverse proxy/container để phát hiện khác biệt parsing, kích thước và encoding.
- [ ] Không copy demo stateless làm login session production mà thiếu phát hành token/phiên.

## 18. Tài liệu chính thức

- [Spring Security 6.3 — AuthenticationConverter API](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/web/authentication/AuthenticationConverter.html): `convert(HttpServletRequest)`, `null` và `AuthenticationException`.
- [Spring Security 6.3 — AuthenticationFilter API](https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/web/authentication/AuthenticationFilter.html): converter, manager, request matcher, success/failure handlers.
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `AuthenticationManager`, `AuthenticationProvider`, context.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): `DelegatingPasswordEncoder` và password hashes.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html): MockMvc, SecurityFilterChain và request test helpers.
- [Jackson Core — JsonParser](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/2.17.2/com/fasterxml/jackson/core/JsonParser.html): parsing, duplicate detection.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259.html): syntax/semantics, UTF-8, uniqueness of object member names.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): authentication error handling, throttling, account enumeration, credential protection.
- [OWASP — Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html): allowlist, syntactic/semantic validation và server-side limits.

**Kết luận:** `AuthenticationConverter` là **ranh giới diễn giải HTTP request thành một nỗ lực xác thực**, không phải nơi quyết định mật khẩu đúng. Request ngoài phạm vi → `null`; JSON login hợp lệ → unauthenticated `Authentication`; JSON sai/thiếu đầu vào → `AuthenticationException` có kiểm soát. Test ba nhánh riêng, test filter không gọi Manager khi payload lỗi và test MockMvc rằng `400` khác `401`; như vậy mới tránh biến dữ liệu đầu vào lỗi thành authenticated principal hoặc lỗi server khó quan sát.