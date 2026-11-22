# Kiểm thử đường dẫn bất thường qua proxy, Servlet container và bộ khớp bảo mật

> **Phạm vi:** Spring Security **Servlet** (Spring Boot 3.x, Spring Security 6.x, Java 17+). Bài tập trung vào kiểm thử `HttpFirewall` và sự nhất quán khi reverse proxy, Servlet container, Spring Security `RequestMatcher` và Spring MVC diễn giải đường dẫn HTTP. Mục tiêu là phát hiện **đường dẫn không rõ nghĩa hoặc bị chuẩn hóa khác nhau** trước khi chúng tạo ra lỗ hổng phân quyền.

## 1. Vì sao phải kiểm thử đường dẫn qua nhiều tầng?

Với một API có tài nguyên quản trị `GET /api/admin/report` chỉ dành cho `ROLE_ADMIN`, request có thể đi qua nhiều hệ thống:

```text
Client
  |
  | HTTP request-target (đường dẫn trong yêu cầu thực tế)
  v
CDN / WAF / API gateway / reverse proxy
  |  Có thể decode, normalize, rewrite, chuyển prefix
  v
Servlet container (Tomcat / Jetty / Undertow)
  |  Phân tách contextPath / servletPath / pathInfo;
  |  có chính sách riêng về ký tự và URL encoding
  v
FilterChainProxy của Spring Security
  |  HttpFirewall kiểm tra và bao request trước khi khớp filter chain
  |  SecurityFilterChain + RequestMatcher xác định quyền
  v
DispatcherServlet / Spring MVC HandlerMapping
  |  Khớp URL với controller
  v
HTTP response
```

Rủi ro xuất hiện khi **mỗi tầng hiểu một đường dẫn theo cách khác nhau**. Ví dụ proxy có thể biến một dạng đường dẫn thành `/api/admin/report`, trong khi quy tắc bảo mật ở tầng sau lại được viết theo một dạng khác; hoặc cơ chế bảo mật thấy một đường dẫn “công khai” trong khi router thực thi lại chọn endpoint “quản trị”.

Tình huống nguy hiểm về mặt logic:

```text
Dạng đường dẫn đến request matcher: /api/public/../admin/report
                               |
                     matcher cho rằng không phải /api/admin/**
                               |
Dạng đường dẫn controller thực thi: /api/admin/report
                               |
                  Đường dẫn thực tế là tài nguyên cần quyền ADMIN
```

Đây chỉ là **mô hình minh họa sai lệch**, không khẳng định cấu hình Spring Security mặc định cho phép bypass như vậy. Mục tiêu kiểm thử là chứng minh việc từ chối từ sớm hoặc kiểm tra quyền đúng **sau mọi phép biến đổi**.

Cần phân biệt bốn kết quả:

- **Bị từ chối tại proxy/container**: ứng dụng có thể không bao giờ nhìn thấy request.
- **Bị từ chối bởi `HttpFirewall`**: request được vào Servlet filter chain nhưng không tới bộ khớp tài nguyên.
- **Được chấp nhận và chuyển tới Spring Security**: phải được phân quyền theo đường dẫn thực tế được thực thi.
- **Không khớp route**: trả lỗi an toàn (ví dụ 404 hoặc 403 theo policy). Việc “không khớp” không được rơi vào nhánh `permitAll` rồi thực thi endpoint nhạy cảm.

Không được suy ra “Spring Security đã chặn” chỉ vì client nhận HTTP 400/403: cần chứng cứ chỉ rõ tầng trả lỗi.

## 2. Những biểu diễn đường dẫn cần phân biệt

### 2.1. Raw request-target, URL đã decode và đường dẫn servlet

Ví dụ client gửi:

```http
GET /api/%2e%2e/admin/report HTTP/1.1
Host: app.example.test
```

`%2e` là biểu diễn percent-encoded của dấu chấm, nhưng **không thể giả định** mọi tầng đều xử lý giống nhau hoặc decode cùng số lần. Proxy có thể giữ nguyên, từ chối, decode hoặc chuẩn hóa dot segment; container có thể chặn trước ứng dụng; ứng dụng và framework có thể chỉ quan sát giá trị đã qua biến đổi.

Các khái niệm quan sát thường gặp:

| Đối tượng | Ý nghĩa | Điểm cần thận trọng |
|---|---|---|
| HTTP request-target | Phần path/query client thực sự gửi trên kết nối HTTP | Proxy có thể thay đổi nó trước upstream; `curl` thường chuẩn hóa một số URL nếu không có `--path-as-is` |
| URI trong access log proxy | Giá trị do proxy ghi nhận, tùy biến log và cấu hình | Có thể là raw request hoặc path đã rewrite; phải biết trường log nào được dùng |
| `HttpServletRequest.getRequestURI()` | URI yêu cầu theo cách container biểu diễn, không có query string | Không nhất thiết là bản byte-for-byte của request-target ngoài Internet |
| `getContextPath()` | Prefix của web application trên container | Không nhất thiết khớp external path sau rewrite qua gateway |
| `getServletPath()` / `getPathInfo()` | Phần đường dẫn được container ánh xạ tới servlet | Cách phân tách và xử lý ký tự phụ thuộc container/mapping |
| `HttpFirewall.getFirewalledRequest(...)` | Request được kiểm tra/bao lại cho Spring Security | Firewall có thể ném `RequestRejectedException` trước khi matcher chạy |
| `SecurityFilterChain` / `RequestMatcher` | Xác định chain và rule xử lý request | Matcher phải diễn giải nhất quán với URL mà ứng dụng thực sự phục vụ |
| Spring MVC HandlerMapping | Quyết định handler/controller thực thi | Cấu hình mapping, path variables, context path và servlet mapping đều ảnh hưởng |

`query string` như `?next=/api/admin/report` là **tham số**, không phải đoạn path của route hiện hành. Đừng áp dụng quy tắc phân quyền theo cách nối/chuẩn hóa tùy tiện query vào đường dẫn.

### 2.2. Các dạng bất thường thường gặp

| Nhóm | Ví dụ kiểm thử trên đường dẫn giả lập | Điều cần xác minh |
|---|---|---|
| Dấu gạch chéo lặp | `/api//admin/report` | Proxy/container/firewall có gộp `//` hay từ chối? |
| Dot segment | `/api/./admin/report` | Có loại `./` trước matcher và controller không? |
| Parent segment | `/api/x/../admin/report` | Có dẫn đến route admin hay bị chặn? |
| Chấm encode | `/api/%2e/admin/report`; `/api/%2e%2e/admin/report` | Decode/normalize bao nhiêu lần, ở tầng nào? |
| Slash encode | `/api/%2fadmin/report` | Encoded slash bị từ chối hay coi là separator? |
| Backslash | `/api/%5cadmin/report` hoặc dấu `\` thực | Container, proxy hoặc hệ điều hành diễn giải ký tự thế nào? |
| Semicolon/path parameter | `/api/admin;v=1/report` | Có bị chặn hoặc bị bỏ phần `;v=1` khi route/matcher so sánh? |
| Double encoding | `/api/%252e%252e/admin/report` | Có tầng nào decode thêm lần nữa sau khi bảo mật đã kiểm tra? |
| Trailing slash | `/api/admin/report/` | MVC và matcher có cùng chính sách đường dẫn kết thúc bằng `/`? |
| Case | `/API/admin/report` | Có bộ khớp không phân biệt hoa/thường hoặc proxy biến đổi? |
| Prefix bị rewrite | External `/service/api/admin/report` → upstream `/api/admin/report` | Filter chain và controller kiểm tra quyền trên path nào? |
| Path thông thường nhưng query giống path | `/api/public?next=/api/admin/report` | Query không bị nhầm thành route admin |

Ví dụ ở đây là **đầu vào kiểm thử trong môi trường được phép**, không có cam kết về một status cố định trên mọi phiên bản và mọi proxy. Kết quả của một case có thể là 400, 403, 404 hoặc được rewrite hợp lệ; điều quan trọng là **không cấp quyền sai và không vô tình chạy thao tác nhạy cảm**.

## 3. HttpFirewall của Spring Security chặn ở đâu?

Trong Servlet stack, `FilterChainProxy` dùng `HttpFirewall` để kiểm tra và bao `HttpServletRequest` trước khi quyết định `SecurityFilterChain` nào áp dụng. Một implementation phổ biến và mặc định là `StrictHttpFirewall`. Nó chủ động từ chối nhiều cách biểu diễn URL khó phân tích an toàn, chẳng hạn một số dấu phân tách bất thường, percent encoding nhạy cảm và semicolon, theo tập quy tắc của phiên bản hiện hành.

Sơ đồ logic:

```text
Request từ container
        |
        v
StrictHttpFirewall.getFirewalledRequest(request)
        |
        +---- phát hiện biểu diễn bị cấm ---> RequestRejectedException
        |                                    --> xử lý lỗi (thường HTTP 400,
        |                                        tùy phiên bản/cấu hình handler)
        |
        v
Request đã được firewall chấp nhận
        |
        v
Chọn SecurityFilterChain -> RequestMatcher -> AuthorizationFilter
        |
        v
MVC HandlerMapping -> Controller
```

**Đừng đánh đồng ba kết quả**:

1. `RequestRejectedException` là quyết định của firewall về request không được phép đi sâu.
2. `401 Unauthorized` là lỗi thiếu/không hợp lệ xác thực, không phải dấu hiệu firewall đang chặn URL.
3. `403 Forbidden` từ authorization có thể là người dùng không đủ quyền; HTTP 403 từ proxy, CSRF hoặc một cơ chế khác cần được phân biệt bằng log và trace.

Spring Security cũng có `DefaultHttpFirewall` và nhiều tùy chọn nới lỏng `StrictHttpFirewall` (chẳng hạn chấp nhận semicolon hoặc encoded slash trong một số use case). **Không nới lỏng toàn cục để “sửa lỗi request”** trước khi xác nhận chính sách ở tất cả proxy, container, matcher và controller, bởi nó có thể tạo sự không nhất quán hoặc làm mất lớp phát hiện đầu vào nguy hiểm.

`HttpFirewall` là tuyến kiểm tra **bên trong ứng dụng Servlet**. Nó không thể khôi phục chuỗi raw nếu upstream proxy đã rewrite/chuẩn hóa hoặc chặn request. Chính vì thế một unit test trực tiếp trên `StrictHttpFirewall` **chưa đủ** chứng minh toàn tuyến Internet → proxy → container → Spring Security là an toàn.

## 4. Bất biến bảo mật cần viết ra trước khi test

Để test có ý nghĩa, định nghĩa ba route ví dụ:

- `GET /api/public`: được phép không cần đăng nhập.
- `GET /api/admin/report`: phải có `ROLE_ADMIN`.
- Các route khác: **deny by default**, trừ khi được khai báo rõ trong ứng dụng thực.

Các bất biến cần bảo toàn:

**A — Không vượt quyền.** Request từ anonymous hoặc người dùng chỉ có `ROLE_USER` **không bao giờ** trả dữ liệu `/api/admin/report`, dù đường dẫn có thêm slash, dot segment, semicolon, encoding, rewrite prefix hay trailing slash.

**B — Không sai lệch giữa matcher và handler.** Nếu container/MVC cuối cùng thực thi một endpoint cần quyền admin, Spring Security phải áp dụng policy phù hợp với **endpoint đó**. Không để một request được nhận như “public” ở matcher nhưng được thực thi như “admin” ở controller.

**C — Đầu vào không rõ nghĩa có xử lý rõ ràng.** Có thể từ chối tại proxy, container hoặc `HttpFirewall`. Nếu được cho đi tiếp, mọi tầng phải thống nhất cách xác định route và giữ nguyên phân quyền.

**D — Hành vi bình thường không bị hỏng.** `/api/public` vẫn 200; admin hợp lệ vẫn truy cập được tài nguyên của mình; endpoint không tồn tại không vô tình xuất dữ liệu của route khác.

**E — Có thể truy vết tầng từ chối.** Mỗi test có request ID, kết quả client, record tại edge/upstream (khi có), trạng thái Servlet/filter và handler đã chạy hay chưa. Không ghi mật khẩu, `Authorization`, cookie hoặc token thô vào log.

Không nên chỉ nhìn status: một API có thể vô tình trả 200 với dữ liệu nhạy cảm, hoặc trả 404 do middleware nhưng vẫn kích hoạt tác dụng phụ. Dùng **marker nghiệp vụ được instrument** ở staging (ví dụ bộ đếm handler, test fixture không có dữ liệu thật) để biết controller nào thực sự được thực thi.

## 5. Ví dụ Spring Boot 3 / Security 6 có thể chạy

Phần này tạo một ứng dụng Servlet nhỏ với rule rõ ràng và `StrictHttpFirewall`. Có thể copy vào một dự án Gradle Spring Boot mới có wrapper. Ví dụ dùng Spring Boot 3.3.5 và Java 17; không cần cấu hình proxy để chạy baseline.

### 5.1. Khai báo Gradle

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

### 5.2. Controller và đường dẫn thật

Tệp `src/main/java/demo/path/PathAuditApplication.java`:

```java
package demo.path;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class PathAuditApplication {
    public static void main(String[] args) {
        SpringApplication.run(PathAuditApplication.class, args);
    }

    @GetMapping("/api/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("resource", "public");
    }

    @GetMapping("/api/admin/report")
    public Map<String, String> adminEndpoint() {
        // Dữ liệu giả lập để minh họa, không lấy dữ liệu production.
        return Map.of("resource", "admin-report");
    }
}
```

Tệp `src/main/java/demo/path/PathSecurityConfig.java`:

```java
package demo.path;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.firewall.HttpFirewall;
import org.springframework.security.web.firewall.StrictHttpFirewall;

@Configuration
public class PathSecurityConfig {
    @Bean
    HttpFirewall httpFirewall() {
        // Chủ động giữ nguyên các mặc định nghiêm ngặt.
        return new StrictHttpFirewall();
    }

    @Bean
    WebSecurityCustomizer webSecurityCustomizer(HttpFirewall firewall) {
        // Gắn firewall được khai báo vào FilterChainProxy.
        return web -> web.httpFirewall(firewall);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin/report")
                    .hasRole("ADMIN")
                // Không tạo lỗ hổng ở route chưa được khớp.
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

**Tại sao cấu hình này có giá trị học tập?** Rule cụ thể cho route admin nằm trước fallback. `denyAll()` khiến đường dẫn không thuộc danh sách không được tự động truy cập. `StrictHttpFirewall` kiểm tra đầu vào bất thường trước các matcher. Không sử dụng `web.ignoring()` cho `/api/**`, vì việc bỏ qua toàn bộ security filter chain cũng bỏ qua firewall của chain đó.

Ví dụ **không nới lỏng** `allowUrlEncodedSlash`, `allowSemicolon` hoặc các lựa chọn tương tự. Khi ứng dụng thật cần matrix variables hoặc đường dẫn đặc biệt, hãy phân tích riêng request mapping, proxy, container và chính sách bảo mật rồi mới quyết định.

### 5.3. Kiểm thử trực tiếp cấu hình và firewall bằng JUnit

Tệp `src/test/java/demo/path/PathSecurityTest.java`:

```java
package demo.path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.web.firewall.HttpFirewall;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PathSecurityTest {
    @Autowired MockMvc mvc;
    @Autowired HttpFirewall firewall;

    @Test
    void publicPathStillWorks() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.resource").value("public"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void ordinaryUserCannotReadAdminReport() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void authorizedAdminCanReadReport() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.resource").value("admin-report"));
    }

    @ParameterizedTest
    @ValueSource(strings = {
        "/api//admin/report",
        "/api/admin;v=1/report",
        "/api/%2fadmin/report",
        "/api/%5cadmin/report"
    })
    void firewallRejectsSelectedAmbiguousPaths(String requestUri) {
        // Test trực tiếp firewall với URI và servlet path mô phỏng.
        // Không thay cho test real container/reverse proxy.
        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", requestUri);
        request.setServletPath(requestUri);

        assertThrows(RequestRejectedException.class,
                () -> firewall.getFirewalledRequest(request));
    }
}
```

Chạy trong dự án có Gradle Wrapper:

```bash
./gradlew test
./gradlew bootRun
```

Các assertion trên kiểm tra **baseline auth** và hành vi firewall ở một số chuỗi đầu vào trực tiếp. Với test trực tiếp, `MockHttpServletRequest` giữ chính URI mô phỏng; nó **không** tái hiện đầy đủ Tomcat, reverse proxy, URL parser của browser hay hạ tầng TLS. Bộ test tích hợp thực tế ở mục 6–8 mới xác định toàn tuyến có an toàn hay không.

Ứng dụng demo không cung cấp người dùng `ROLE_ADMIN` qua HTTP Basic; phần test tạo principal giả lập bằng `@WithMockUser`. Khi chạy `bootRun`, `GET /api/admin/report` của anonymous sẽ bị thách thức xác thực (thường 401), còn `/api/public` được phép trả JSON. Không lấy mật khẩu generated trong console của Boot làm chính sách xác thực cho production.

## 6. Kiểm thử HTTP thật tại upstream và reverse proxy

### 6.1. Lấy baseline trên đường dẫn chuẩn

Trước khi biến đổi URL, xác nhận những request bình thường:

| Đường dẫn | Người gọi | Kết quả mục tiêu |
|---|---|---|
| `GET /api/public` | Anonymous | HTTP 200, JSON `{"resource":"public"}` |
| `GET /api/admin/report` | Anonymous | Bị từ chối do chưa xác thực (HTTP Basic thường là 401) |
| `GET /api/admin/report` | `ROLE_USER` | 403 |
| `GET /api/admin/report` | `ROLE_ADMIN` | 200, JSON `{"resource":"admin-report"}` |
| `GET /api/unknown` | Bất kỳ | Bị từ chối theo fallback; không trả `admin-report` |

Các trường hợp có role cụ thể được kiểm tra bằng `MockMvc` trong ví dụ; khi thử HTTP thật cần tài khoản thử nghiệm hoặc một cơ chế đăng nhập staging **được cấp quyền**, không dùng tài khoản/hồ sơ của người thật.

### 6.2. Gửi path chính xác bằng curl

Một số HTTP client tự loại dot segments (`/./`, `/../`) ngay trước khi gửi. Khi kiểm thử phải phân biệt **chuỗi bạn gõ** và **request-target thật đi trên dây**. `curl --path-as-is` giúp giữ các đoạn path khi gửi; `--globoff` tránh xử lý globbing URL ở phía curl.

Script Bash dùng trên máy thử nghiệm với một **base URL được chỉ định** (ví dụ `http://127.0.0.1:8080` hoặc domain staging của proxy):

```bash
#!/usr/bin/env bash
set -euo pipefail

BASE_URL="$1"

paths=(
  "/api/public"
  "/api/admin/report"
  "/api//admin/report"
  "/api/./admin/report"
  "/api/x/../admin/report"
  "/api/%2e/admin/report"
  "/api/%2e%2e/admin/report"
  "/api/%2fadmin/report"
  "/api/%5cadmin/report"
  "/api/admin;v=1/report"
  "/api/%252e%252e/admin/report"
  "/api/admin/report/"
  "/API/admin/report"
  "/api/public?next=/api/admin/report"
)

for path in "${paths[@]}"; do
  printf '%-43s ' "$path"
  curl --path-as-is --globoff --silent --show-error \
    --output /dev/null --write-out '%{http_code}\n' \
    "$BASE_URL$path"
done
```

Dùng script trên **chỉ với môi trường staging/local được phép**. Để kiểm tra trực tiếp Spring Boot, có thể lưu thành `probe-paths.sh` rồi chạy:

```bash
bash probe-paths.sh http://127.0.0.1:8080
```

Với upstream đặt sau gateway, chạy lại bằng URL **public staging** theo cùng tập test. Không bao giờ công bố một bảng “mọi path bất thường luôn 400”: proxy, Servlet container và firewall có thể chặn ở các tầng khác nhau; đường dẫn không tồn tại có thể 404/403 theo route; HTTP client có thể không gửi được một số chuỗi malformed.

**Lưu ý khi quan sát:** script chỉ ghi status để sàng lọc. Nếu một đường dẫn bất thường trả **200**, phải kiểm tra body, endpoint được thực thi và principal để xác định có thật là vượt quyền hay chỉ là `/api/public`. Nếu nhận 400/403, cần trace tầng từ chối, không kết luận ngay rằng chính firewall đã hoạt động.

### 6.3. Quan sát request-target và response headers

Để biết curl gửi gì, dùng `--verbose` cùng `--path-as-is` trên một case:

```bash
curl --path-as-is --globoff --verbose \
  --output /dev/null \
  "http://127.0.0.1:8080/api/x/../admin/report"
```

Trong HTTP/1.1, `curl -v` thường hiển thị request line có path; khi kết nối dùng HTTP/2, thông tin có thể hiện dưới dạng pseudo-header `:path`. Việc client thực sự gửi gì còn phụ thuộc phiên bản curl, URL parser và giao thức. Xác minh bằng log ingress hoặc network trace có kiểm soát nếu cần.

Muốn xem header body trên đường dẫn cụ thể:

```bash
curl --path-as-is --globoff -i \
  "http://127.0.0.1:8080/api//admin/report"
```

Đừng dùng mỗi `curl -I` như thay thế GET: `-I` gửi HEAD, có thể đi qua route/matcher khác. Dùng đúng method mà bạn cần bảo vệ.

### 6.4. So sánh hai đường đi trong cùng môi trường

Lập cùng một bảng kết quả:

| Case | Client gửi | Kết quả trực tiếp container | Kết quả qua proxy | Tầng chặn / route thực thi |
|---|---|---|---|---|
| Baseline public | `/api/public` | Ghi kết quả quan sát | Ghi kết quả quan sát | Controller public |
| Baseline admin | `/api/admin/report` | Ghi kết quả quan sát | Ghi kết quả quan sát | Authorization |
| Double slash | `/api//admin/report` | Ghi kết quả quan sát | Ghi kết quả quan sát | Proxy/container/firewall |
| Encoded slash | `/api/%2fadmin/report` | Ghi kết quả quan sát | Ghi kết quả quan sát | Proxy/container/firewall |
| Dot segment | `/api/x/../admin/report` | Ghi kết quả quan sát | Ghi kết quả quan sát | Proxy/container/firewall/route |
| Semicolon | `/api/admin;v=1/report` | Ghi kết quả quan sát | Ghi kết quả quan sát | Proxy/container/firewall/route |
| Double encoded | `/api/%252e%252e/admin/report` | Ghi kết quả quan sát | Ghi kết quả quan sát | Các lần decode qua từng tầng |
| Trailing slash | `/api/admin/report/` | Ghi kết quả quan sát | Ghi kết quả quan sát | Security matcher và MVC mapping |

Đây là **mẫu biểu ghi nhận**, không phải kết quả đo sẵn. Để so sánh có ý nghĩa, dùng cùng version ứng dụng và cùng dữ liệu thử nghiệm. Đường dẫn direct/container đôi khi đi qua `Host` hoặc context path khác: ghi rõ khác biệt đó và điều chỉnh fixture/routing cho tương đương. Nếu proxy chuyển HTTPS sang HTTP upstream, scheme ngoài và scheme trong cũng khác; không trộn khác biệt môi trường với hành vi URL.

## 7. Xác định chính xác tầng nào đã từ chối hoặc biến đổi path

Một lỗi `400 Bad Request` có thể đến từ reverse proxy, Servlet container hoặc `RequestRejectedHandler` của Spring Security. Để phân biệt, cần một chuỗi dấu vết tối thiểu:

1. **Client** ghi URL yêu cầu, method, protocol và thời điểm. Với request nhạy cảm, không log `Authorization`/cookie/token.
2. **Edge/proxy** ghi một mã correlation ID đáng tin, giá trị request path trước và sau rewrite nếu có, status gửi client và status upstream (nếu có). Không giả định trường log “URI” luôn là raw path: đọc đúng tài liệu/cấu hình của proxy.
3. **Upstream access log** ghi URI mà Servlet container quan sát cùng status. Nếu không có record upstream, request có thể đã bị chặn trước ứng dụng.
4. **Security** ghi sự kiện bị firewall từ chối hoặc authorization denied theo logger/metrics đã cấu hình, tránh in toàn bộ exception/path hoặc thông tin xác thực chưa được lọc.
5. **Controller** dùng marker/counter chỉ có trong môi trường thử nghiệm để chứng minh handler nào đã chạy. Không thêm cơ chế ghi dữ liệu nhạy cảm vào production chỉ để debug.

Ví dụ bảng suy luận:

| Bằng chứng | Kết luận khả dĩ | Cần kiểm tra thêm |
|---|---|---|
| Edge có log 400, upstream không có request | Bị chặn trước container | WAF rule, URI parser, proxy rewrite |
| Upstream có 400, security không có dấu vết | Container có thể đã chặn | Container access log, parser, filter order |
| Security ghi `RequestRejectedException` | `HttpFirewall` đã từ chối | Request representation đến firewall, handler trả status |
| 401/403 từ security | Xác thực/phân quyền ngăn request | Matcher/chain đã chọn, principal/test fixture |
| HTTP 404 nhưng có controller marker không mong đợi | Routing hoặc logging bất nhất, cần điều tra | Controller mapping, error dispatch |
| HTTP 200 cùng body `admin-report` cho user thiếu quyền | **Fail nghiêm trọng** | Kiểm tra chain/matcher/rewrites và dừng rollout |

**Đừng tiết lộ path chứa token trong log** khi test. Có thể dùng path fixture không nhạy cảm và một mã `X-Test-Case-Id` được kiểm soát. Với `X-Forwarded-*` và correlation ID từ client, chỉ tin header khi đã được ingress/proxy đáng tin lọc và thiết lập lại; header giả do client gửi không được quyết định danh tính hoặc quyền.

## 8. Những sai lệch điển hình giữa proxy, container và matcher

### 8.1. Reverse proxy rewrite/normalize

Cấu hình proxy có thể ảnh hưởng đến: dấu `//`, dot segments, percent encoding, phần prefix, dấu slash cuối, URI được chuyển tiếp khi `proxy_pass` có hoặc không có URI, và các rule rewrite. Ví dụ nhiều hệ thống có đường dẫn ngoài `/service/api/admin/report` nhưng upstream nhận `/api/admin/report`.

Cần lưu bản cấu hình của **đúng môi trường đang kiểm thử** và kiểm tra cả đường direct/upstream lẫn đường edge. Với NGINX, cách `proxy_pass` dùng phần URI và các biến log có thể làm kết quả khác nhau; với API gateway/CDN khác cũng có các cơ chế chuẩn hóa riêng. Không giả định “reverse proxy chỉ chuyển tiếp nguyên xi”.

Nếu proxy chuẩn hóa một path rồi upstream thấy đường dẫn hợp lệ, firewall có thể không biết request ban đầu khác thường. Vì vậy **policy ở edge và ở ứng dụng phải tương thích**: hoặc reject từ edge, hoặc chuyển tiếp một dạng đã chuẩn hóa mà Spring Security và MVC xử lý nhất quán, không có đường bypass.

### 8.2. Servlet container và URL encoding

Tomcat, Jetty, Undertow có parser, mapping và lựa chọn xử lý encoded slash/backslash/path parameters khác nhau; có thể từ chối request trước Servlet filter. Một số lựa chọn như hỗ trợ encoded solidus hoặc ký tự URI nới lỏng có thể làm thay đổi khả năng lọt qua các tầng.

Khi test, ghi **tên container, version, context path, servlet mapping** và mọi cấu hình URL decoding/normalization đặc biệt. Không thay đổi chúng chỉ vì một test mong status 400 nhưng thực tế trả 404: cần đối chiếu bất biến phân quyền và nguyên nhân.

### 8.3. SecurityMatcher và RequestMatcher khác MVC mapping

Spring Security có thể dùng nhiều `SecurityFilterChain`, mỗi chain chọn bằng `securityMatcher(...)`; trong từng chain, các `requestMatchers(...)` áp dụng rule. MVC HandlerMapping lại quyết định controller thực thi. Đừng mặc định mẫu chuỗi của security matcher và MVC route sẽ luôn hiểu mọi cách biểu diễn bất thường giống nhau nếu proxy/container đã biến đổi chúng.

Ví dụ cấu hình rủi ro là: một chain `/api/admin/**` rất chặt, nhưng chain fallback `/**` lại `permitAll` cho mọi thứ không khớp. Nếu biểu diễn bất thường khiến matcher admin không nhận ra trong khi MVC vẫn điều hướng tới admin, có thể tạo lỗ hổng. **Giữ fallback nghiêm ngặt** và kiểm thử trên chính request qua HTTP thật.

Khi dùng context path hoặc prefix qua proxy, đừng cố khắc phục bằng cách match raw `X-Forwarded-Prefix` do client tự đưa. Forwarded headers cần được xử lý nhất quán và chỉ tin từ proxy đáng tin; điều đó là câu chuyện trust boundary riêng, không phải lý do bỏ `HttpFirewall`.

### 8.4. Semicolon và matrix variables

Một số ứng dụng dùng path parameters/matrix variables với dạng `/items;color=red/123`. `StrictHttpFirewall` theo cấu hình nghiêm ngặt mặc định có thể từ chối semicolon để tránh sự mập mờ khi so khớp URL. Nếu nghiệp vụ thực sự cần, giải pháp không đơn giản là bật `setAllowSemicolon(true)` trên toàn bộ app: phải kiểm tra URL sau khi container xử lý, chính sách route, MVC, cache và security matcher trong đầy đủ ma trận.

Nếu không có yêu cầu nghiệp vụ rõ ràng, cách an toàn hơn là giữ policy mặc định và dùng query parameters khi phù hợp. Không dùng đường dẫn chứa ký tự đặc biệt như cách né rule của container hoặc Spring Security.

## 9. Phương pháp test theo tầng: unit, integration, end-to-end

| Mức | Chạy ở đâu | Bảo đảm điều gì | Không thể tự chứng minh |
|---|---|---|---|
| Unit `HttpFirewall` | `MockHttpServletRequest` → `StrictHttpFirewall` | Các chuỗi thực sự tới firewall bị reject/accept theo cấu hình | Proxy, HTTP parser của container, URL sau rewrite |
| MVC/Security integration | `MockMvc` + Spring Security | Endpoint thông thường được xác thực/phân quyền đúng và rule fallback hoạt động | Chuỗi raw trên mạng, hành vi parser/reverse proxy |
| Embedded container | `@SpringBootTest(webEnvironment = RANDOM_PORT)` hoặc server chạy thật | Container xử lý đường dẫn thật trước filter, phản hồi HTTP | Proxy/CDN/gateway ở môi trường triển khai |
| End-to-end qua proxy | Domain staging thật + test client giữ request-target | Cả pipeline, status, header, rewrite và khả năng bypass quyền | Mọi biến thể production nếu cấu hình staging khác |
| Browser | Trình duyệt thật khi frontend phát request | Một số URL có thể bị browser tự chuẩn hóa trước khi gửi | Các malformed request mà browser không gửi được |

**Hai nhóm assertion phải kiểm tra song song**:

- **Chính sách**: anonymous/`ROLE_USER` không nhận dữ liệu `admin-report`; `ROLE_ADMIN` có thể truy cập bằng path chuẩn; route public hoạt động đúng.
- **Tính nhất quán**: với path bất thường, nếu được xử lý thì security và controller phải cùng hiểu route; nếu bị reject thì xác định tầng đã reject, không diễn giải 400/403/404 như bằng chứng duy nhất.

Có thể đặt test CI cho `MockMvc` và firewall unit; chạy kiểm thử integration với embedded container trên mọi lần nâng phiên bản Spring Security/container; chạy một tập probe E2E trên staging mỗi khi thay đổi proxy rewrite, WAF, context path hoặc API gateway. Không cần chạy payload gây thay đổi dữ liệu; dùng GET vào fixture không nhạy cảm và trace marker.

## 10. Ma trận mở rộng cho regression và nâng cấp

Tạo test cases từ nhiều trục, nhưng giới hạn tổ hợp có ý nghĩa:

| Trục | Nhánh nên thử | Lý do |
|---|---|---|
| Đầu vào path | Chuẩn, `//`, `./`, `../`, `%2e`, `%2f`, `%5c`, `;`, `%25`, trailing `/` | Bao phủ các điểm normalization/decoding dễ mập mờ |
| Người gọi | Anonymous, `ROLE_USER`, `ROLE_ADMIN` | Phát hiện bypass hoặc chặn nhầm quyền |
| Đường kết nối | Direct container, qua reverse proxy | Phát hiện proxy rewrite trước firewall |
| Method | `GET` và method nghiệp vụ liên quan (nếu có) | Tránh matcher chỉ phân quyền theo path nhưng sai method |
| Quy tắc security | Route public, route protected, fallback deny | Phát hiện nhảy nhầm chain/rule |
| Cấu hình | Trước/sau nâng Spring Security, container, proxy | Bắt regression khi behavior thay đổi |

Khi một test thất bại, ghi lại **request-target chính xác**, method, HTTP protocol, edge/upstream URL, status từng tầng, chain/matcher được chọn, controller marker, phiên bản thư viện và cấu hình liên quan. Đặc biệt với phần path encode, chữ hoa/thường của percent sequence cũng nên có ca đại diện nếu proxy/parser có sự khác biệt.

Không nên tự động “sửa test” bằng cách cho chấp nhận mọi encoded slash hay semicolon: việc thay đổi policy phải có threat model rõ, bằng chứng routing/matcher nhất quán và kiểm chứng toàn tuyến.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Một request `/api//admin/report` trả 400 khi gọi qua gateway, nhưng nếu gửi trực tiếp tới container thì bị `RequestRejectedException`. Có thể kết luận gì?

**Trả lời:** Hai đường đều chặn, nhưng tại **hai tầng khác nhau**. Cần xác minh gateway thực sự là nơi trả 400 và request không vào upstream; trực tiếp thì firewall chặn. Không lấy cùng status làm bằng chứng cùng một nguyên nhân.

**Câu 2.** Spring Security đang có chain admin rất chặt và chain fallback `permitAll`. Vì sao đây là điểm cần test đường dẫn bất thường?

**Trả lời:** Nếu chain admin không khớp một biểu diễn URL nhưng MVC thực thi tài nguyên admin sau biến đổi, request có thể rơi vào fallback quá rộng. Giải pháp nền tảng là thiết kế matcher/route nhất quán, firewall phù hợp và fallback có bảo vệ.

**Câu 3.** Vì sao unit test `StrictHttpFirewall` PASS chưa chứng minh API public sau proxy an toàn?

**Trả lời:** Unit test truyền trực tiếp một request giả vào firewall, bỏ qua các phép decode/rewrite của proxy và Servlet container. E2E phải chứng minh **request-target thực tế** qua hạ tầng vẫn bị reject hoặc được phân quyền đúng.

**Câu 4.** Nếu `curl --path-as-is` nhận 404 với encoded path, 404 có đủ kết luận là an toàn không?

**Trả lời:** Chưa. Phải kiểm tra controller không thực thi bất ngờ, body không chứa dữ liệu nhạy cảm và cùng test với người dùng có các role khác nhau. 404 cũng cần được gắn với đúng tầng trả lỗi.

**Câu 5.** Có nên bật `setAllowUrlEncodedSlash(true)` để làm mọi test encoded slash chuyển sang 200 không?

**Trả lời:** Không. Nới lỏng phải xuất phát từ yêu cầu nghiệp vụ, rà soát proxy/container/matcher/MVC, kiểm tra chính sách truy cập và ca regression. Mục tiêu là **route đúng và an toàn**, không phải tất cả input đều được nhận.

## 12. Checklist nghiệm thu

- [ ] Đã xác định exact URL và security rule cho route public, route nhạy cảm và fallback.
- [ ] Đã ghi lại version/config của proxy, container, Spring Security, servlet mapping và các rule rewrite.
- [ ] Đã xác minh request-target thực sự bằng client không tự loại path segments (khi cần).
- [ ] Đã kiểm thử slash lặp, dot/parent segments, percent encoding, encoded slash/backslash, semicolon, double encoding, trailing slash và prefix rewrite.
- [ ] Đã chạy cùng ma trận trực tiếp tại container và qua proxy, với anonymous, role thường và admin trên dữ liệu fixture.
- [ ] Đã phân biệt lỗi ở proxy, container, HttpFirewall, authorization và Spring MVC bằng correlation ID/trace có kiểm soát.
- [ ] Không có path bất thường nào giúp anonymous hoặc user thiếu quyền nhận dữ liệu/thi hành thao tác quản trị.
- [ ] Route bình thường vẫn hoạt động đúng; fallback không mở route lạ.
- [ ] Không lưu token, cookie, credential hoặc dữ liệu cá nhân vào log kiểm thử.
- [ ] Những khác biệt được ghi vào regression suite trước khi thay đổi cấu hình hoặc nâng phiên bản.

**Điểm cốt lõi:** `HttpFirewall` là lớp từ chối đầu vào mập mờ ở Spring Security Servlet, nhưng độ an toàn của route phải được chứng minh trên **toàn chuỗi client → proxy → container → firewall → RequestMatcher → MVC handler**. Kết quả đúng là đường dẫn bị từ chối có thể giải thích được hoặc được xử lý với **cùng quyền truy cập như tài nguyên thực tế**; không chỉ là một mã HTTP “có vẻ an toàn”.