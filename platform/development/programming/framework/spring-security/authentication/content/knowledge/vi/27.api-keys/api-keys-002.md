# Lựa chọn vị trí truyền API key và tránh đưa bí mật vào URL

## 1. Mục tiêu và bối cảnh

Một ứng dụng Spring Boot cung cấp `GET /api/report` cho dịch vụ đối tác. Để nhận diện bên gọi, API yêu cầu một **API key**: giá trị bí mật được cấp riêng cho client/integration và được kiểm tra ở mỗi request. Người nắm được key thường có khả năng sử dụng API với phạm vi quyền của key, nên vị trí truyền key có ảnh hưởng trực tiếp đến rủi ro lộ credential.

Hai request có ý nghĩa nghiệp vụ giống nhau nhưng cách mang bí mật khác nhau:

~~~http
GET /api/report?api_key=lab-demo-secret HTTP/1.1
Host: api.example.org
~~~

~~~http
GET /api/report HTTP/1.1
Host: api.example.org
X-API-Key: lab-demo-secret
~~~

**Quy tắc thiết kế:** với API key riêng cho giao tiếp máy–máy, ưu tiên **HTTP header trên HTTPS**. Không nhận bí mật trong URL query, URL path, fragment hoặc URL userinfo. Tránh chấp nhận đồng thời nhiều vị trí truyền credential khiến các thành phần hạ tầng hiểu request khác nhau.

Sau bài này bạn có thể:
- Giải thích rủi ro rò rỉ API key qua URL, log, history, proxy và analytics, kể cả khi HTTPS được sử dụng.
- Chọn giữa header `Authorization`, header `X-API-Key`, request body, cookie và query string theo đúng contract.
- Cấu hình Spring Security Servlet chỉ xác thực API key từ header và không duy trì session xác thực giữa request.
- Kiểm thử đủ các ca đúng key, sai key, thiếu key, key trong URL, header trùng và endpoint public.
- Vận hành key có định danh, quyền tối thiểu, logging redaction, hạn sử dụng, rotation và khả năng thu hồi.

**Phạm vi:** Spring Security 6.x, Spring Boot 3.x, Java 17+, ứng dụng Servlet/Spring MVC. WebFlux dùng `SecurityWebFilterChain` và reactive context, không áp dụng nguyên filter Servlet bên dưới.

## 2. API key xác thực client, không tự thay thế mọi cơ chế quyền

API key thường gắn với một ứng dụng hoặc dịch vụ tích hợp:

~~~text
Client ID: billing-exporter
Key ID: key_prod_7c12         # ID có thể dùng để tra cứu, audit
Secret: [giá trị ngẫu nhiên dài, chỉ hiển thị khi cấp]
Environment: production
Scopes: invoices:read
Status: active
Expires: theo chính sách
~~~

**Phân biệt:** key ID là định danh; secret là credential cần giữ kín. Một key đúng có thể giúp server xác định **client** đã được cấp khóa, nhưng không tự xác thực người dùng cuối hay cấp quyền xem bất kỳ hóa đơn nào. API vẫn cần kiểm tra scope, tenant, ownership, rate limit và quyền ở từng endpoint.

Với endpoint rất nhạy cảm, API key đơn lẻ có thể chưa đủ. Có thể cần OAuth 2.0 client credentials, access token ngắn hạn, mTLS, IP/network control và chính sách phân quyền riêng. Không coi giới hạn lưu lượng là cơ chế authorization thay thế.

## 3. So sánh nơi mang khóa trong HTTP

| Vị trí | Ví dụ | Đánh giá | Điểm cần chú ý |
| --- | --- | --- | --- |
| Header riêng | `X-API-Key: <secret>` | **Ưu tiên** cho API key do hệ thống tự cấp với contract rõ | Cần redaction riêng vì hệ thống log có thể không che header custom |
| Header `Authorization` | `Authorization: Bearer <token>` | **Ưu tiên cho OAuth2 bearer access token** | Scheme Bearer không có nghĩa mọi API key đều là OAuth access token |
| Header `Authorization` riêng | `Authorization: ApiKey <secret>` | Có thể dùng khi API tự định nghĩa scheme | Cần thống nhất với SDK/proxy; không mặc định được Spring xác thực |
| Request body | `{"apiKey":"..."}` trong POST | Có thể trong protocol đặc biệt, **không mặc định** | GET không có request body chuẩn để truyền key; body vẫn có thể bị log |
| Cookie | `Cookie: session=...` | Dùng cho thiết kế browser session khác | Browser gửi cookie tự động; cần `Secure`, `HttpOnly`, `SameSite`, CSRF |
| Query string | `?api_key=<secret>` | **Không dùng** | URL có thể vào logs, history, analytics, cache, bản copy liên kết |
| Path | `/api/keys/<secret>/report` | **Không dùng** | Bí mật vẫn nằm trong URL, lộ ở log và route telemetry |
| URL userinfo | `https://key:secret@host/path` | **Không dùng** | URL dễ bị chia sẻ, ghi log, parse sai |
| Fragment | `https://host/path#secret` | **Không dùng** | Fragment thường không gửi lên server trong HTTP request; không phù hợp xác thực API |

`X-API-Key` là tên header theo quy ước, **không phải một chuẩn có duy nhất tên này**. Hệ thống có thể định nghĩa một tên khác, nhưng phải thống nhất ở client, gateway, backend và OpenAPI. Header name không phân biệt hoa thường; **giá trị secret phải so khớp chính xác**.

### 3.1. Khi nào dùng `Authorization: Bearer`?

RFC 6750 mô tả gửi **OAuth 2.0 bearer access token** trong header `Authorization`. Token có thể là JWT hoặc opaque; resource server phải xác thực theo đúng issuer, expiry, audience, scope và trust contract. Không lấy một chuỗi API key riêng rồi đưa vào JWT Resource Server của Spring Security và giả định nó sẽ tự được nhận.

Nếu một sản phẩm tài liệu `Authorization: ApiKey <secret>`, đó là contract riêng của sản phẩm. Cần triển khai parser/authentication và redaction tương ứng.

### 3.2. Ví dụ OpenAPI khai báo key trong header

~~~yaml
openapi: 3.0.3
info:
  title: Reporting API
  version: 1.0.0
components:
  securitySchemes:
    ReportingKey:
      type: apiKey
      in: header
      name: X-API-Key
security:
  - ReportingKey: []
paths: {}
~~~

Cấu hình OpenAPI nói cho client cách truyền credential. **Nó không tự tạo filter xác thực** và không lưu key cho server. Với bearer token đúng chuẩn, định nghĩa security scheme phù hợp với `type: http`, `scheme: bearer` hoặc OAuth flows, không lẫn lộn hai kiểu.

## 4. Vì sao HTTPS không cứu được bí mật nằm trong URL?

HTTPS bảo vệ request **trên đường truyền tới điểm kết thúc TLS**; proxy/gateway/server nhận request vẫn cần đọc request URI. Khi client dùng:

~~~text
https://api.example.org/api/report?api_key=lab-demo-secret&month=11
~~~

giá trị query có thể đi vào:

1. **Web server access log:** Nginx/Apache thường ghi request URI; một số định dạng log có query string.
2. **CDN/API gateway/load balancer:** access log, WAF event và debug trace có thể lưu URL.
3. **Ứng dụng/APM:** framework request logging, exception log, trace attribute như `url.full` hoặc request URL.
4. **Trình duyệt:** history, bookmark, link chia sẻ, screenshot, devtools hoặc công cụ tự động chụp lỗi.
5. **Cache và phân tích:** URL có thể là cache key hoặc được gửi cho analytics/monitoring.
6. **Referer:** tùy `Referrer-Policy` và kiểu điều hướng, một phần URL có thể xuất hiện ở bên nhận khác. Không đặt bí mật vào URL rồi trông chờ chính sách referrer bảo vệ.

Ngay cả khi ứng dụng không chủ động log, **một điểm trung gian vẫn có thể lưu URL**. Không chữa lỗi bằng cách URL-encode, Base64-encode, thay tên query param hoặc xóa key sau redirect: credential vẫn nằm trong URL trước khi đến nơi.

Các mẫu đều không phù hợp:

~~~text
/api/report?api_key=secret
/api/report?token=secret
/api/report?access_token=secret
/api/credentials/secret/report
https://secret@api.example.org/api/report
~~~

RFC 6750 mô tả cách gửi OAuth bearer token bằng query parameter vì tương thích lịch sử, nhưng cảnh báo mức độ dễ bị ghi log và **không khuyến nghị sử dụng**. API key không mặc nhiên là OAuth token, song rủi ro rò rỉ URL là tương tự.

### 4.1. URL có những gì được phép?

URL nên chứa định tuyến và tham số nghiệp vụ:

~~~text
GET https://api.example.org/api/report?month=11&format=csv
GET https://api.example.org/api/customers/42
~~~

Không đưa password, API key, bearer access token, refresh token, secret HMAC hoặc dữ liệu xác thực có khả năng dùng lại vào query/path. Nếu URL có dữ liệu cá nhân nhạy cảm, đánh giá riêng theo chính sách privacy/logging.

## 5. Header tốt hơn URL nhưng vẫn cần phòng rò rỉ

Request đề xuất:

~~~http
GET /api/report?month=11 HTTP/1.1
Host: api.example.org
Accept: text/plain
X-API-Key: <demo-key-value>
~~~

Khóa được gửi trong header và kết nối phải dùng HTTPS ở môi trường thật. Nhưng hệ thống vẫn có thể lộ header nếu log toàn bộ request, bật curl verbose, bật debug HTTP client hoặc forward header đến host khác.

Thực hiện đồng thời:
- **TLS đúng từng chặng tin cậy**: client → gateway, gateway → backend nếu kết nối đi qua mạng cần bảo vệ; xác minh certificate và hostname.
- **Che header nhạy cảm**: `X-API-Key`, `Authorization`, `Cookie` ở proxy, application logging, collector, tracing, error reporting và support tooling.
- **Không forward ngoài ý muốn**: tránh gửi key tới upstream khác qua HTTP redirect hoặc proxy được cấu hình sai.
- **Không để key trong client công khai**: key nằm trong SPA JavaScript bundle hoặc app mobile có thể bị trích xuất; header không bảo mật được secret đã phát cho mọi người dùng.
- **Không dùng key làm quyền tuyệt đối**: kiểm tra client/tenant/scope và object-level authorization ở API.

Một frontend web có end user nên dùng BFF giữ secret server-side, hoặc OAuth2/OIDC cho user-delegated access; không đóng gói một API key chung vào public SPA.

## 6. Ví dụ hoàn chỉnh Spring Boot 3.3.x + Spring Security Servlet

Ví dụ sử dụng **Java 17+**, Spring Boot 3.3.12, một API key demo truyền qua `X-API-Key` và hai endpoint:
- `GET /health`: public.
- `GET /api/report`: yêu cầu authority `API_READ`, chỉ cấp sau khi kiểm tra đúng API key **trong header**.

Mục tiêu là kiểm tra *nơi lấy credential*, không xây một hệ thống phát hành key production. Code dưới đây hỗ trợ một key giả cho một service account; production cần key ID/hash store, expiry, revocation, tenant và rotation.

### 6.1. Cấu trúc project

~~~text
api-key-header-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/apikey/
    │   │   ├── ApiKeyApplication.java
    │   │   ├── ApiKeyFilter.java
    │   │   └── SecurityConfig.java
    │   └── resources/application.yml
    └── test/java/demo/apikey/ApiKeySecurityTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'api-key-header-demo'
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

`src/main/resources/application.yml`:

~~~yaml
app:
  api-key: ${LAB_API_KEY}
~~~

`LAB_API_KEY` được cung cấp từ môi trường. Không commit secret thật vào repository, YAML hoặc container image.

### 6.2. Ứng dụng và endpoints

`src/main/java/demo/apikey/ApiKeyApplication.java`:

~~~java
package demo.apikey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ApiKeyApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiKeyApplication.class, args);
    }

    @GetMapping(value = "/health", produces = MediaType.TEXT_PLAIN_VALUE)
    public String health() {
        return "OK";
    }

    @GetMapping(value = "/api/report", produces = MediaType.TEXT_PLAIN_VALUE)
    public String report() {
        return "report: READY";
    }
}
~~~

### 6.3. Filter chỉ nhận credential từ header

`src/main/java/demo/apikey/ApiKeyFilter.java`:

~~~java
package demo.apikey;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Collections;
import java.util.List;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class ApiKeyFilter extends OncePerRequestFilter {
    private static final String HEADER = "X-API-Key";
    private final byte[] expectedDigest;

    public ApiKeyFilter(String configuredKey) {
        if (configuredKey == null || configuredKey.isBlank()) {
            throw new IllegalArgumentException("API key must be configured");
        }
        this.expectedDigest = sha256(configuredKey);
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        if (!request.getServletPath().startsWith("/api/")) {
            chain.doFilter(request, response);
            return;
        }

        var keys = Collections.list(request.getHeaders(HEADER));

        if (keys.isEmpty()) {
            // Không lấy key từ request.getParameter("api_key").
            chain.doFilter(request, response);
            return;
        }

        if (keys.size() != 1 || keys.get(0).isBlank()
                || keys.get(0).length() > 512) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        if (!MessageDigest.isEqual(
                expectedDigest, sha256(keys.get(0)))) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        var auth = new UsernamePasswordAuthenticationToken(
                "reporting-client",
                null,
                List.of(new SimpleGrantedAuthority("API_READ")));

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(auth);
        SecurityContextHolder.setContext(context);

        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private static byte[] sha256(String value) {
        try {
            return MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException impossibleOnJava17) {
            throw new IllegalStateException(impossibleOnJava17);
        }
    }
}
~~~

**Giải thích:**
1. Filter chỉ dùng `getHeaders("X-API-Key")`, không gọi `getParameter("api_key")`, không parse query/path/body để tìm key.
2. Thiếu header → request vẫn chưa có Authentication; endpoint `/api/report` sẽ bị phần authorization từ chối.
3. Sai/trùng header → từ chối 401, tránh proxy và backend diễn giải nhiều header khác nhau.
4. Với key khớp, filter tạo một `Authentication` cho service account giả lập `reporting-client` với authority `API_READ`. Không dùng thông tin key để tạo danh tính người dùng cuối.
5. Demo băm key rồi so byte bằng `MessageDigest.isEqual` nhằm hạn chế kiểu so sánh prefix không an toàn. Đây không phải giải pháp đầy đủ cho storage, timing hoặc brute-force; key phải được sinh ngẫu nhiên và quản lý vòng đời.
6. Context được xóa sau request. Đây là code Servlet sử dụng `SecurityContextHolder`, không phải Reactor Context của WebFlux.
7. Filter **không có `@Component`** vì cấu hình bên dưới sẽ thêm nó một lần vào Spring Security chain; tránh vô tình được Spring Boot đăng ký như servlet filter thứ hai.

### 6.4. SecurityFilterChain

`src/main/java/demo/apikey/SecurityConfig.java`:

~~~java
package demo.apikey;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.LogoutFilter;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain security(
            HttpSecurity http,
            @Value("${app.api-key}") String configuredKey) throws Exception {
        return http
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .requestCache(cache -> cache.disable())
                .formLogin(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint((request, response, error) ->
                                response.sendError(
                                        HttpServletResponse.SC_UNAUTHORIZED)))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/health").permitAll()
                        .requestMatchers("/api/**").hasAuthority("API_READ")
                        .anyRequest().denyAll())
                .addFilterAfter(new ApiKeyFilter(configuredKey),
                        LogoutFilter.class)
                .build();
    }
}
~~~

Custom authentication filter được đặt sau `LogoutFilter` và trước authorization. `STATELESS` tránh sử dụng session cho SecurityContext; mỗi request phải gửi key. `formLogin` và `httpBasic` bị tắt để demo chỉ có một cơ chế đăng nhập.

**CSRF chỉ tắt trong mô hình máy–máy không dùng cookie phiên trình duyệt làm credential**. Nếu tích hợp browser cookie hay session, phải phân tích CSRF và cấu hình tương ứng; không sao chép phần này vào mọi ứng dụng. Hệ thống thực thường bổ sung lookup key ID, kiểm tra trạng thái và scope, và ràng buộc tenant; một key đúng chưa chắc đủ quyền.

Spring Security không tự hiểu `X-API-Key` chỉ nhờ thêm starter. Code filter/AuthenticationProvider hoặc gateway phải thực thi xác thực theo contract.

## 7. Chạy thử và quan sát

Đặt key **giả** cho local demo:

~~~bash
# Linux/macOS
export LAB_API_KEY='lab-demo-only-1234567890'
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
$env:LAB_API_KEY = 'lab-demo-only-1234567890'
.\gradlew.bat bootRun
~~~

Dùng Gradle Wrapper của project đã tạo; nếu chưa có wrapper, cài Gradle phù hợp và chạy `gradle bootRun`. Trong production không đưa secret thật vào shell history, process arguments, transcript, ảnh chụp màn hình hoặc file cấu hình không kiểm soát; hãy dùng secret manager/secret injection.

Từ terminal khác, gọi:

~~~bash
# Public, không cần header:
curl -i http://localhost:8080/health

# Đúng API key, trong header:
curl -i -H 'X-API-Key: lab-demo-only-1234567890' \
  http://localhost:8080/api/report

# Thiếu header:
curl -i http://localhost:8080/api/report

# Header sai:
curl -i -H 'X-API-Key: wrong-demo-key' \
  http://localhost:8080/api/report

# Để chứng minh API không đọc URL key. Chỉ dùng giá trị giả ở localhost:
curl -i 'http://localhost:8080/api/report?api_key=lab-demo-only-1234567890'
~~~

Kết quả dự kiến:

| Request | HTTP status | Body/ý nghĩa |
| --- | --- | --- |
| `GET /health` | 200 | `OK` |
| `GET /api/report` với header đúng | 200 | `report: READY` |
| `GET /api/report` thiếu header | 401 | Không được xác thực |
| `GET /api/report` với header sai | 401 | Không được xác thực |
| `GET /api/report?api_key=...`, không header | 401 | **URL không có tác dụng xác thực** |

Ở production **phải dùng HTTPS**. URL `http://localhost:8080` chỉ phục vụ kiểm thử local với key demo. Không dùng `curl -v` hoặc dump request có key thật vì terminal/log có thể hiển thị header nhạy cảm.

## 8. Test tự động bằng MockMvc

`src/test/java/demo/apikey/ApiKeySecurityTest.java`:

~~~java
package demo.apikey;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = "app.api-key=lab-demo-only-1234567890")
@AutoConfigureMockMvc
class ApiKeySecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void acceptsHeaderCredential() throws Exception {
        mvc.perform(get("/api/report")
                        .header("X-API-Key", "lab-demo-only-1234567890"))
                .andExpect(status().isOk())
                .andExpect(content().string("report: READY"));
    }

    @Test
    void rejectsMissingHeader() throws Exception {
        mvc.perform(get("/api/report"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void rejectsWrongKey() throws Exception {
        mvc.perform(get("/api/report")
                        .header("X-API-Key", "wrong-demo"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void urlParameterIsNotAuthentication() throws Exception {
        mvc.perform(get("/api/report")
                        .queryParam("api_key", "lab-demo-only-1234567890"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void rejectsDuplicateHeader() throws Exception {
        mvc.perform(get("/api/report")
                        .header("X-API-Key",
                                "lab-demo-only-1234567890",
                                "lab-demo-only-1234567890"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void healthIsPublic() throws Exception {
        mvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(content().string("OK"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
# Windows: gradlew.bat test
~~~

Kỳ vọng **6 test pass**. Không khẳng định nguyên văn stdout của Gradle vì log thay đổi theo version/console/cache. Các test dùng key giả và `MockMvc` để chạy Servlet security filter chain; không cần API mạng thật. Những kết luận về **proxy/TLS/redaction** vẫn phải kiểm tra tại môi trường integration có gateway tương ứng.

**Mở rộng:** test key có quyền `READ` nhưng không có quyền `WRITE`, sai tenant, key bị thu hồi, nhiều key đồng thời, expiry, rate limit và redirect/header forwarding. Đừng chỉ kiểm tra “key đúng trả HTTP 200” rồi suy ra cả hệ thống an toàn.

## 9. Client Java 17+ gửi header, giữ URL sạch

File `ApiKeyClient.java` chạy độc lập với JDK 17 khi backend demo đang chạy:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class ApiKeyClient {
    public static void main(String[] args) throws Exception {
        String key = System.getenv("LAB_API_KEY");
        if (key == null || key.isBlank()) {
            throw new IllegalStateException("LAB_API_KEY is required");
        }

        HttpClient http = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:8080/api/report?month=11"))
                .header("X-API-Key", key)
                .GET()
                .build();

        HttpResponse<String> response = http.send(
                request, HttpResponse.BodyHandlers.ofString());

        System.out.println("HTTP " + response.statusCode());
        System.out.println(response.body());
    }
}
~~~

Chạy:

~~~bash
javac ApiKeyClient.java
java ApiKeyClient
~~~

Khi key demo hợp lệ và backend đang chạy, stdout:

~~~text
HTTP 200
report: READY
~~~

Trong Java 17, `HttpClient` không dùng `try-with-resources` như một `AutoCloseable`; ví dụ trên cố ý tạo client bình thường để biên dịch đúng. Với production, thay `http://localhost` bằng HTTPS, bổ sung timeout, xử lý redirect có kiểm soát và không forward key đến host ngoài ý muốn.

## 10. Log, proxy và observability: bảo vệ qua nhiều chặng

Luồng điển hình:

~~~text
Client service
    |
    | HTTPS, X-API-Key
    v
CDN / WAF / API Gateway / TLS Terminator
    |
    | Forward header có kiểm soát
    | TLS nội bộ nếu có ranh giới tin cậy
    v
Spring Security Filter
    |
    | API_READ + business authorization
    v
Report API
~~~

Một vài kiểm soát thực tế:
1. **Edge access log:** không log toàn bộ `X-API-Key` hoặc `Authorization`; dùng allowlist field và redaction trước khi xuất log.
2. **App logging:** không in `request.getHeader("X-API-Key")`, toàn bộ request dumps, stack trace chứa secret hoặc error response tiết lộ giá trị key.
3. **Distributed tracing:** kiểm tra trường request URL, query, headers ở SDK/collector/exporter; không lưu raw credential trong trace/span.
4. **CI và test report:** dùng key giả; không in secret qua `curl -v`, test snapshots, debug, chat, screenshots hoặc support tickets.
5. **Gateway → backend:** xác định nơi thực hiện xác thực. Nếu gateway thêm header “client đã xác thực”, backend chỉ được tin nó khi chặn truy cập trực tiếp và loại header do client bên ngoài tự đặt.
6. **Redirect:** không tự động gửi key sang host khác và không đưa key vào `Location` response.
7. **Thống nhất phương thức:** gateway và app phải đồng ý chấp nhận **chỉ header**, không để gateway chấp nhận query trong khi backend đã bỏ.
8. **Cache:** tránh cache response riêng tư sai phân quyền hoặc dùng URL có credential làm cache key. Với API nhạy cảm, cấu hình `Cache-Control` phù hợp.

**HTTPS là bắt buộc nhưng chưa đủ:** ngay cả header cũng có thể xuất hiện trong APM hay request dump nếu cấu hình sai. Do đó, “đưa key khỏi URL” và “ngăn log header” là hai yêu cầu bổ sung cho nhau.

## 11. Vòng đời API key: sinh, lưu, hạn chế quyền, thu hồi

Một khóa nên có:
- **Key ID** riêng để tra cứu/audit, không phải secret.
- **Secret ngẫu nhiên mạnh** tạo bằng CSPRNG; ví dụ giá trị ngẫu nhiên khoảng 256 bit, truyền qua kênh cấp phát an toàn.
- **Bản lưu để xác minh**: không ghi plaintext key ở log/database. Với secret ngẫu nhiên đủ mạnh, lưu digest (ví dụ SHA-256) kèm key ID và so sánh an toàn; mật khẩu do con người chọn cần KDF cho password thay vì coi là API key ngẫu nhiên.
- **Owner/tenant/environments**: biết key của ứng dụng nào và có hiệu lực ở đâu; không dùng key test ở production.
- **Permissions/scope**: quyền tối thiểu, ví dụ `reports:read`, cùng quota/rate limit riêng.
- **Expiry/disable/revoke**: thu hồi ngay khi lộ hoặc client ngừng hoạt động; theo dõi thời gian dùng cuối mà không log secret.
- **Rotation**: cho phép chồng lấn thời gian hiệu lực của key cũ và key mới trong cửa sổ ngắn, cập nhật client rồi thu hồi key cũ.
- **Storage phía client**: secret manager/biến môi trường được kiểm soát; tránh Git, frontend bundle, mobile APK, shell history và plaintext config công khai.

Khi dùng nhiều key, đừng hardcode một key chung như demo. Xây KeyRepository/AuthenticationProvider tra key ID, đối chiếu digest, kiểm tra status, expiry, scope, tenant và tạo principal chứa **client ID**, không chứa raw credential. Database cần uniqueness và khả năng revoke an toàn. Response 401 cho key sai/thiếu; 403 cho client đã được xác thực nhưng không được quyền truy cập theo policy.

## 12. Di chuyển API cũ đang chấp nhận `?api_key=...`

Không cần tự động hỗ trợ query mãi mãi vì rủi ro tiếp tục hiện hữu. Một lộ trình có kiểm soát:

1. **Inventory** client/SDK/API docs đang truyền key qua query/path; xác định owner và môi trường.
2. **Bổ sung header canonical** ở client/gateway theo đúng contract; test xác thực, logging và permission.
3. **Thông báo migration** và cutoff rõ ràng. Không log nguyên văn URL chứa key trong quá trình đo sử dụng legacy.
4. **Ngừng xác thực từ URL**: chỉ nhận header. Nếu client cũ còn gửi query, phản hồi lỗi chung và hướng dẫn sửa cấu hình ở kênh tài liệu.
5. **Kiểm tra secret có thể đã bị lộ** trong access logs/analytics/cache theo quy trình bảo mật và retention; rotate/revoke key cần thiết.
6. **Xác minh sau cutover** ở ingress, backend và test. Không “fallback tạm” sang query khi header sai, vì như vậy phá chính sách.

Ví dụ bộ lọc ở trên thể hiện đúng nguyên tắc: request có `?api_key=...` **nhưng không có `X-API-Key`** không được xác thực. Chỉ với key giả mới mô phỏng URL chứa secret; không cố tình đưa key thật vào URL để thử.

## 13. Lỗi phổ biến

| Nhầm lẫn | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| “Có HTTPS nên key trong URL an toàn” | URL vẫn hiện tại TLS terminator và có thể vào logs | Chuyển credential sang header, che log |
| “Thay `api_key` thành `token` là xong” | Query vẫn là URL | Ngừng dùng query credential |
| “Header luôn bí mật” | Header có thể bị proxy/APM/debug log | Redact `X-API-Key`/`Authorization` ở mọi lớp |
| “`X-API-Key` là chuẩn bắt buộc” | Đây là tên header do API tự chọn | Chuẩn hóa trong tài liệu/SDK/OpenAPI |
| “Mọi API key là OAuth bearer access token” | Issuer, grant, token validation và contract có thể khác | Dùng validator phù hợp từng cơ chế |
| “Key đúng thì client được mọi quyền” | Authentication và authorization khác nhau | Kiểm tra scope, tenant, record ownership |
| “Dùng CORS để chặn client không có key” | CORS chỉ tác động đến một số hành vi browser | Xác thực và phân quyền ở server |
| “SPA có thể giấu key vì đã minify JavaScript” | Bundle và request có thể bị đọc | BFF hoặc OAuth2/OIDC theo người dùng |
| “Gửi key trong path an toàn hơn query” | Cả hai đều thuộc URL | Không gửi key trong path/query |
| “Key vào POST body không bao giờ lộ” | Body có thể bị capture/trace, không dùng nhất quán cho GET | Header theo contract, bảo vệ logging |
| “API máy–máy phải tắt CSRF trong mọi trường hợp” | Nếu cookie/session browser được dùng vẫn có CSRF risk | Đánh giá transport và threat model |
| “Một key chung cho tất cả khách hàng tiện hơn” | Không phân quyền, audit và revoke riêng | Key độc lập theo client/tenant |
| “Chỉ cần test key đúng là đủ” | Bỏ sót URL fallback, duplicate và 403 | Test dương, âm, proxy và quyền |

## 14. Câu hỏi tự luyện

**1.** Một request có `https://api.example.org/report?api_key=K`. HTTPS có ngăn server access log lưu K không?  
**Không.** Server/gateway vẫn nhìn thấy URL đã giải mã tại điểm kết thúc TLS, và logging có thể ghi nó.

**2.** Key gửi trong `X-API-Key`. Có thể bật “log all request headers” trên production không?  
**Không.** Header cũng cần redaction. Không đưa credential nguyên văn vào log hoặc trace.

**3.** Một SPA chạy trong trình duyệt có key cố định trong JavaScript nhưng gửi qua HTTPS header. Đã bảo vệ key chưa?  
**Chưa.** Người dùng có thể xem network request/code. Cần thay cách phân phối credential.

**4.** Request `/api/report?api_key=K` không có header. Trong ví dụ Spring Security trả gì?  
**401**, vì filter không đọc query và endpoint đòi authority `API_READ`.

**5.** Dùng `Authorization: Bearer <token>` có nghĩa đang dùng API key tự định nghĩa phải không?  
**Không nhất thiết.** Bearer thường là OAuth access token, có bộ quy tắc xác minh riêng; phải theo contract.

**6.** Key xác thực client A, request truy cập tài nguyên tenant B. Được cho qua nếu key đúng không?  
**Chỉ khi policy thực sự cho phép.** Xác thực key không loại bỏ kiểm tra tenant và quyền trên đối tượng.

### Checklist triển khai

- [ ] Chỉ chấp nhận API key ở header canonical theo contract.
- [ ] Dùng HTTPS và xác minh chứng chỉ đúng mọi chặng cần bảo vệ.
- [ ] Không đặt secret trong path/query/fragment/userinfo, kể cả trong link test thật.
- [ ] Che `X-API-Key`, `Authorization`, URL/query nhạy cảm ở proxy, app, APM và client logging.
- [ ] Không nhúng key bí mật cố định trong SPA/mobile hoặc commit vào repo.
- [ ] API key có ID, owner, tenant, scope, expiry, revoke, rotation và rate limit.
- [ ] API kiểm tra authorization đối với từng endpoint/tài nguyên.
- [ ] Test thiếu/sai/đúng/trùng header, key trong query và các đường truy cập qua gateway.
- [ ] Không vô hiệu CSRF nếu còn dùng browser cookie làm credential mà chưa phân tích rủi ro.
- [ ] Không lưu key thật trong support ticket, stdout, CI artifact hay screenshot.

## 15. Nguồn tham khảo

- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): HTTPS, API Keys, tránh thông tin nhạy cảm trong URL và kiểm soát API.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): truyền Bearer access token bằng `Authorization`, cảnh báo cách dùng query parameter.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): thứ tự SecurityFilterChain, custom authentication filter.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session policy và stateless authentication.
- [OpenAPI 3.0.3 — Security Scheme Object](https://spec.openapis.org/oas/v3.0.3#security-scheme-object): mô tả API key trong header.
- [Spring Boot 3.3 Reference](https://docs.spring.io/spring-boot/3.3/reference/): cấu hình ứng dụng và kiểm thử.

**Điểm nhớ:** tách bí mật khỏi URL, đưa API key vào HTTP header được chuẩn hóa trên HTTPS, không fallback sang query và bảo vệ header khỏi log. Việc nhận đúng API key chỉ là bước xác thực client; phân quyền và quản lý vòng đời key vẫn bắt buộc.