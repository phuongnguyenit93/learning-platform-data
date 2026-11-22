# Giới hạn của mock web environment với filter container và cấu hình mạng

## 1. Mục tiêu và phạm vi

Trong Spring Boot Testing, **mock web environment** cho phép nạp web application context và xử lý request bằng các mock Servlet API mà **không khởi động Servlet container đang lắng nghe cổng HTTP thật**. Cơ chế này rất hữu ích để kiểm tra Spring MVC, nhưng không đủ để kết luận rằng **mọi filter của Servlet container, mọi URL mapping, dispatcher type, cấu hình connector, cổng mạng, TLS, proxy và transport** đã được kiểm chứng.

Bài này đi sâu vào ranh giới thường bị bỏ sót khi viết integration tests:

- `@SpringBootTest(webEnvironment = MOCK)` nạp context web giả, nhưng không mở embedded server.
- `@AutoConfigureMockMvc(addFilters = true)` cho phép MockMvc thực thi các `Filter` được đưa vào **mock filter chain**; điều đó **không đồng nghĩa** đã kiểm chứng cách container thực đăng ký mọi filter.
- `FilterRegistrationBean`, `@WebFilter` và `@ServletComponentScan` liên quan đến **Servlet container registration**, bao gồm URL pattern, servlet name, dispatch types, thứ tự và async support.
- Cấu hình như `server.port`, `server.servlet.context-path`, `server.ssl.*`, `server.compression.*`, `server.forward-headers-strategy` và các giới hạn của connector cần được test tại **đúng ranh giới**.
- `@SpringBootTest(webEnvironment = RANDOM_PORT)` cùng HTTP client thật bổ sung embedded server và network path, nhưng vẫn chưa tự tái hiện production reverse proxy, DNS, ingress, load balancer hay internet.

**Mục tiêu thực hành:** tạo ứng dụng Java 17+/Spring Boot 3.x có **một filter Spring bean** và **một filter chỉ đăng ký qua `FilterRegistrationBean`**; dùng MockMvc chứng minh request handling/filter bean và khả năng giả lập request metadata; dùng HTTP thật kiểm chứng URL mapping của filter container và context path. Từ đó biết chính xác test nào chứng minh điều gì.

Bài chỉ nói đến **Servlet stack/Spring MVC**; WebFlux có mô hình web filter và Netty khác, được phân biệt rõ ở phần sau. Không có database, Docker hoặc security provider trong mã mẫu để dễ tái lập; những yếu tố đó được bàn ở phần giới hạn và tình huống production.

## 2. Hai tầng cần phân biệt: Spring MVC pipeline và Servlet container

### 2.1. MockMvc đi qua DispatcherServlet nhưng không qua connector mạng

Đường xử lý của `MockMvc.perform(...)`:

```text
JUnit test
  |
  +-- MockMvc.perform(...)
       |
       +-- MockHttpServletRequest / MockHttpServletResponse
       +-- MockFilterChain (các Filter được đăng ký với MockMvc)
       +-- DispatcherServlet
            +-- HandlerMapping / HandlerAdapter
            +-- converters / validators / exception resolvers
            +-- controller --> service --> repository (nếu được nạp)
       |
       +-- Mock response --> status/header/jsonPath assertions
```

Đây là sơ đồ khái niệm. Trong Spring Framework, MockMvc **gọi trực tiếp DispatcherServlet** với các triển khai mock của Servlet API từ `spring-test`, không cần running server.

Những phần MockMvc vẫn có thể kiểm tra tốt:

- request mapping theo method/path, path variable, query parameter;
- argument binding, type conversion, `@Valid` và validation;
- JSON/XML converters có trong test application context;
- controller advice, exception resolver, response status/body;
- logic service/repository thật nếu bạn dùng full test context;
- các `Filter` đã thực sự được đưa vào mock filter chain;
- nhiều trường hợp Spring Security authorization/CSRF với Spring Security Test.

Những phần **không được chứng minh chỉ vì MockMvc pass**:

- embedded Tomcat/Jetty/Undertow có khởi động và bind port được không;
- servlet container có áp dụng URL pattern/dispatcher mapping và startup lifecycle như production không;
- raw HTTP request bytes có được connector parse giống production không;
- giới hạn header/body, timeout, connection reuse, keep-alive, HTTP/2;
- TLS handshake, certificate, proxy trust, forwarding thực tế;
- container access log, compression ở network layer, multi-connector behavior;
- request/response đi qua socket, client và server ở các thread riêng.

### 2.2. HTTP thật với RANDOM_PORT

Đường xử lý của một live HTTP test:

```text
JUnit client thread
  |
  +-- HttpClient GET http://127.0.0.1:<random-port>/demo/api/...
       |
       +-- TCP loopback + HTTP bytes
       +-- embedded server connector
       +-- ServletContext / servlet/filter registrations
       +-- mapped Filter chain theo URL/dispatcher/order
       +-- DispatcherServlet
            +-- controller/service/repository
       +-- response encoding + socket
  |
  +-- HttpClient receives status, headers and body
```

Bây giờ có một real server/port trong test process, và request được xử lý qua container. Tuy nhiên, máy test vẫn chỉ đang gọi **loopback localhost**. Nếu proxy/TLS/ingress không tồn tại trong môi trường test, đường đó **chưa được kiểm chứng**.

### 2.3. Độ rộng context là trục riêng

| Cấu hình | Context được nạp | Đường request | Embedded server |
|---|---|---|---|
| `@WebMvcTest` + MockMvc | MVC slice | Mock Servlet | Không |
| `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` | Full test ApplicationContext theo config/profile | Mock Servlet | Không |
| `@SpringBootTest(RANDOM_PORT)` + HTTP client | Full test ApplicationContext theo config/profile | HTTP qua socket thật | Có |
| `@SpringBootTest(RANDOM_PORT)` + MockMvc | Có thể có full context và server, nếu MockMvc cũng được cấu hình | **`mockMvc.perform` vẫn là đường mock** | Server có thể đang chạy, nhưng lời gọi đó không đi qua socket |
| Staging qua proxy/gateway | Hệ thống triển khai theo staging | HTTP(S) qua nhiều hop | Có, cộng thêm hạ tầng thực tế |

**Ghi nhớ:** tên `@SpringBootTest` không tự bảo đảm real HTTP. Mặc định `webEnvironment` là `MOCK`. Ngược lại, có server đang chạy không làm `MockMvc.perform(...)` chuyển thành một network call.

## 3. Filter là ba thứ khác nhau trong cùng một hệ thống

Từ “filter” xuất hiện ở nhiều lớp, nhưng các lớp đó không có cùng nhiệm vụ.

### 3.1. Servlet Filter: đối tượng thực thi

Trong Servlet API, một `jakarta.servlet.Filter` có method chính:

```java
void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException;
```

Đây là **chữ ký minh họa** của interface Servlet, không phải source file có thể chạy độc lập.

Filter có thể đọc/chỉnh request, set response header, từ chối request hoặc gọi `chain.doFilter(...)` để chuyển bước tiếp theo. Trong ứng dụng thật, một filter xử lý authentication, correlation ID, encoding, CORS hoặc logging có thể cần chạy đúng trước/sau filter khác.

Một filter có mặt trong Spring `ApplicationContext` **chưa đủ** chứng minh nó đã được Servlet container đăng ký ở URL/dispatcher nào.

### 3.2. Filter registration: cấu hình cho container

Trong Spring Boot Servlet application, các cơ chế phổ biến:

1. Khai báo một `Filter` như Spring bean (ví dụ `@Component`): Boot thường tự động đăng ký filter với embedded servlet container, mapping mặc định thường là `/*`.
2. Khai báo `FilterRegistrationBean<T extends Filter>`: thiết lập **URL patterns**, **servlet names**, **order**, **dispatcherTypes**, **asyncSupported**, enabled/disabled và tùy chọn khác.
3. Dùng `@WebFilter` của Servlet API cùng `@ServletComponentScan` để container phát hiện thành phần Servlet theo cơ chế hỗ trợ.
4. Ở Spring Security, `DelegatingFilterProxy` và `springSecurityFilterChain` phối hợp bean trong Spring context với Servlet container registration.

Các cơ chế này **liên quan nhưng không đồng nhất**. Một filter đã được khai báo qua `FilterRegistrationBean` không nên vô tình được đăng ký lần thứ hai bằng cách vừa dùng stereotype bean vừa tự registration mà không hiểu Boot xử lý cách đăng ký. Nếu phải kết hợp, xác minh Boot/container và tránh double registration.

### 3.3. MockMvc filter chain: cơ chế đăng ký khác

Spring Test cung cấp `MockFilterChain`. Với standalone MockMvc, bạn có thể cấu hình:

```java
mockMvc = MockMvcBuilders.standaloneSetup(controller)
        .addFilters(new CharacterEncodingFilter())
        .build();
```

Đây là **đoạn minh họa**, cần controller và imports đầy đủ. Filter chỉ được đưa vào mock chain theo setup này; **không có hành động container `ServletContext.addFilter(...)` qua real connector**.

Với `@AutoConfigureMockMvc(addFilters = true)`, Boot tự đưa các filter thích hợp từ Spring context vào MockMvc. Tuy nhiên, đây không phải bằng chứng rằng mọi registration bean, URL pattern, servlet mapping, dispatcher type hay lifecycle của **Servlet container thật** đã được kiểm chứng đúng.

**Không khẳng định cực đoan “MockMvc không chạy bất kỳ filter nào”.** Điều đó sai khi filter đã được đăng ký trong mock chain. Nhận định đúng là: *MockMvc kiểm tra filter logic được đưa vào mock chain; real HTTP test mới kiểm tra container-specific registration qua live server*.

## 4. Các thuộc tính của container filter cần kiểm chứng đúng tầng

### 4.1. URL pattern

Một `FilterRegistrationBean` có thể đăng ký filter chỉ cho:

```java
registration.addUrlPatterns("/api/private/*");
```

Container thực dùng URL pattern kiểu Servlet để quyết định request nào đi qua filter. Kỳ vọng:

- Request vào `/api/private/inspect` sẽ được map.
- Request vào `/api/public/inspect` không đi qua **registration đó**, nếu không có mapping khác.
- Nếu application có `server.servlet.context-path=/demo`, phía ngoài client truy cập `/demo/api/private/inspect`, nhưng URL pattern filter vẫn đặt theo **đường dẫn trong application context**, ví dụ `/api/private/*`, không phải ghép cứng `/demo`.

Việc mock một request ở `/api/private/inspect` không tự chứng minh rằng container thật đã áp mapping. Hãy gửi HTTP thật tới port chạy server và so sánh header/effect cho hai URL nằm trong và ngoài pattern.

### 4.2. DispatcherType

Servlet có các dispatch types như:

- `REQUEST`: request ban đầu từ client;
- `FORWARD`: nội bộ forward qua RequestDispatcher;
- `INCLUDE`: include một resource;
- `ASYNC`: dispatch bất đồng bộ;
- `ERROR`: error dispatch.

Filter chỉ tham gia các dispatch types mà registration của nó được phép nhận. Với `FilterRegistrationBean`, `setDispatcherTypes(...)` có thể cấu hình điều này. Theo tài liệu Spring Boot Servlet, khi không chỉ định dispatch type, mặc định theo Servlet specification là **`REQUEST`**.

Ví dụ:

```java
registration.setDispatcherTypes(
        DispatcherType.REQUEST,
        DispatcherType.ASYNC,
        DispatcherType.ERROR);
```

Đây là đoạn minh họa dùng imports `jakarta.servlet.DispatcherType`. Nếu filter có trách nhiệm ở cả async/error dispatch, hãy cấu hình phù hợp và **viết bài test có dispatch thật**. Không suy ra một MockMvc test request đồng bộ đã kiểm tra được toàn bộ `ASYNC/ERROR`.

**Lưu ý với `OncePerRequestFilter`:** class còn có hook như `shouldNotFilterAsyncDispatch()` và `shouldNotFilterErrorDispatch()`. Việc registration cho phép `ASYNC/ERROR` là **một điều kiện**, nhưng implementation của filter có thể chủ động bỏ qua một số dispatch. Cần kiểm tra **cả mapping và chính logic filter**.

### 4.3. Thứ tự filter

Các lớp quan trọng như security, logging, encoding, forwarded-header handling và request wrapper có thể phụ thuộc thứ tự.

```java
registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
```

Đây là snippet cho `FilterRegistrationBean`. Boot có thứ tự cho nhiều filter/registration; nếu muốn đặt order cho một `Filter` đã có, có thể dùng annotation hoặc implementation `Ordered` ở chỗ phù hợp, nhưng với một registration bean hãy ưu tiên `setOrder(...)` theo API.

**Không nên kiểm tra order bằng cách chỉ assert hai header đều tồn tại.** Hai filter có thể chạy sai thứ tự mà vẫn set được hai header. Nếu order là hợp đồng, hãy tạo một test nơi filter A set request attribute/wrapper và filter B phụ thuộc attribute đó, rồi xác nhận chuỗi hành vi qua HTTP thật.

### 4.4. `asyncSupported` và error handling

Một filter hoặc servlet có thể được đăng ký với `asyncSupported = true/false`. Sai cấu hình có thể khiến yêu cầu khởi tạo async thất bại trên container, dù MockMvc test không đi qua cùng lifecycle.

Nếu application có `DeferredResult`, `Callable`, Servlet async hoặc error pages, test riêng trên live server cần kiểm tra dispatcher types, filter behavior và cleanup. Một test MockMvc với `asyncDispatch(...)` rất hữu ích cho **Spring MVC async contract**, nhưng vẫn không tái hiện toàn bộ container async timeout/connector/network behavior.

### 4.5. Init parameters, lifecycle và `ServletContextInitializer`

Một filter có thể được khởi tạo qua `init(FilterConfig)`, đọc init parameters hoặc phụ thuộc lifecycle/container. `FilterRegistrationBean` là một `ServletContextInitializer` có trách nhiệm đăng ký filter trong Servlet container.

Mock Servlet objects và MockFilterChain không phải bằng chứng rằng **chính cấu hình đăng ký trong embedded container** đã được chạy như production. Nếu filter phụ thuộc container init parameters, mapping, servlet name hoặc thứ tự khởi tạo, cần kiểm tra qua live server và, nếu cần, observability/inspection tại container.

## 5. Khác nhau giữa các cách “loại filter”

Rất dễ sửa sai chỗ khi một request bị filter chặn.

| Cách cấu hình | Tác động | Không chứng minh/không thay đổi điều gì |
|---|---|---|
| `@AutoConfigureMockMvc(addFilters = false)` | Không thêm filter beans từ application context vào MockMvc theo cơ chế tương ứng | Không xóa bean và không chứng minh filter không chạy trên real server |
| `@WebMvcTest(excludeFilters = ...)` | Tinh chỉnh candidate của component scan trong MVC slice | Không phải generic filter để xóa mọi auto-config hoặc bean từ `@Bean`/`@Import` |
| `FilterRegistrationBean.setEnabled(false)` | Tắt **registration** qua bean đó trong Servlet container | Không nhất thiết xóa instance/filter bean khỏi Spring context |
| `FilterRegistrationBean.addUrlPatterns(...)` | Giới hạn mapping tại Servlet container | Không tự quyết định mọi filter được thêm vào MockMvc |
| `Spring Security test user/CSRF postprocessor` | Cung cấp authentication/CSRF context cho test phù hợp | Không bỏ qua filter; không chứng minh real OIDC/TLS |
| `@SpringBootTest(RANDOM_PORT)` + HTTP client | Chạy qua filter/servlet container thực trong JVM test | Không đưa gateway/proxy của môi trường production vào đường request |

**Không dùng `addFilters = false` để “fix” một HTTP 401/403 và vẫn tuyên bố security rules đã được test.** Với MockMvc, hãy cấu hình principal và CSRF token bằng Spring Security Test khi cần. Với real HTTP, hãy gửi credentials/cookie/token test hợp lệ bằng HTTP client.

## 6. Ví dụ hoàn chỉnh Java 17+ và Spring Boot 3.x

Mã mẫu được thiết kế để phân tách **filter logic trong MockMvc** và **container URL mapping qua live HTTP**, đồng thời chứng minh rằng MockMvc có thể tạo request metadata “giống HTTPS” mà không có TLS.

**Phạm vi hỗ trợ:** Spring Boot 3.x, Servlet MVC, Java 17+, JUnit Jupiter, `spring-boot-starter-web` và `spring-boot-starter-test`. Không có Spring Security, R2DBC, JPA, database, external API hoặc proxy thực.

### 6.1. Dependencies

**Gradle Groovy DSL** — trong một project đã có Boot plugin, dependency management, Java toolchain và repositories:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Maven** — trong `pom.xml` đã có Spring Boot parent/BOM và test plugin thích hợp:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Đây là **đoạn dependency**, không phải toàn bộ build file; không thêm dependency trùng nếu project đã có. JDK 17 bao gồm `java.net.http.HttpClient`. Spring Boot 3 dùng package `jakarta.servlet.*`, không phải `javax.servlet.*` từ ứng dụng Boot 2.

### 6.2. Cấu trúc tệp

```text
src/
├── main/java/com/example/boundary/
│   ├── BoundaryApplication.java
│   ├── ProbeController.java
│   ├── GlobalStampFilter.java
│   └── ScopedFilterConfiguration.java
└── test/java/com/example/boundary/
    ├── MockBoundaryTest.java
    └── RealContainerBoundaryTest.java
```

Tất cả class production nằm trong `com.example.boundary`, cùng package với `@SpringBootApplication` để component scan mặc định tìm được controller, filter bean và configuration.

### 6.3. Ứng dụng Spring Boot

**File `src/main/java/com/example/boundary/BoundaryApplication.java`:**

```java
package com.example.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}
```

Không có cổng cố định. Test MOCK sẽ không mở server; test RANDOM_PORT sẽ để Boot chọn cổng đang rảnh.

### 6.4. Controller đọc request metadata

**File `src/main/java/com/example/boundary/ProbeController.java`:**

```java
package com.example.boundary;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ProbeController {

    public record Snapshot(
            String path,
            String scheme,
            boolean secure,
            int port,
            String remoteAddress
    ) {}

    @GetMapping({"/public/inspect", "/private/inspect"})
    public Snapshot inspect(HttpServletRequest request) {
        return new Snapshot(
                request.getRequestURI(),
                request.getScheme(),
                request.isSecure(),
                request.getServerPort(),
                request.getRemoteAddr());
    }
}
```

Controller chỉ phản ánh **giá trị do Servlet request cung cấp**. Trong MockMvc, các giá trị này có thể được test tự đặt trên mock request; trong live HTTP, chúng được container xây dựng dựa trên HTTP connection/headers và cấu hình đã được áp dụng.

Bài cố tình không đưa thông tin nhạy cảm hay token vào response. Trong ứng dụng production, **không nên tạo endpoint công khai hiển thị mọi request headers/remote address** chỉ để debug, vì có thể làm lộ dữ liệu hoặc tăng bề mặt tấn công. Endpoint ở đây chỉ là fixture học tập.

### 6.5. Filter bean chạy trên nhiều request

**File `src/main/java/com/example/boundary/GlobalStampFilter.java`:**

```java
package com.example.boundary;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class GlobalStampFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        response.setHeader("X-Global-Stamp", "active");
        chain.doFilter(request, response);
    }
}
```

Đây là một Spring `@Component` kiểu Servlet `Filter`. Trong MockMvc test với `@AutoConfigureMockMvc` và `addFilters = true` mặc định, filter phù hợp từ context được thêm vào mock chain. Trong real HTTP test, Boot sẽ tự đăng ký Filter bean đó với embedded container theo cơ chế Servlet.

Test sẽ **assert header `X-Global-Stamp: active` ở cả hai đường**. Vì vậy nó không tạo ngộ nhận MockMvc “bỏ qua mọi Filter”.

### 6.6. Filter riêng chỉ đăng ký bằng FilterRegistrationBean

**File `src/main/java/com/example/boundary/ScopedFilterConfiguration.java`:**

```java
package com.example.boundary;

import java.io.IOException;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration(proxyBeanMethods = false)
public class ScopedFilterConfiguration {

    @Bean
    FilterRegistrationBean<ScopedFilter> scopedFilterRegistration() {
        FilterRegistrationBean<ScopedFilter> registration =
                new FilterRegistrationBean<>();

        registration.setFilter(new ScopedFilter());
        registration.addUrlPatterns("/api/private/*");
        registration.setDispatcherTypes(DispatcherType.REQUEST);
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return registration;
    }

    static final class ScopedFilter implements Filter {
        @Override
        public void doFilter(
                ServletRequest request,
                ServletResponse response,
                FilterChain chain)
                throws IOException, ServletException {

            ((HttpServletResponse) response)
                    .setHeader("X-Scoped-Stamp", "private-only");
            chain.doFilter(request, response);
        }
    }
}
```

**Ba chi tiết chủ đích:**

1. `ScopedFilter` **không** có `@Component` và không được khai báo thành `@Bean Filter` riêng. Nó chỉ được cung cấp trong `FilterRegistrationBean` để tránh đường đăng ký không mong muốn.
2. URL pattern `/api/private/*` chỉ cho phép container registration áp dụng ở nhánh private trong application context.
3. `DispatcherType.REQUEST` và order được khai báo tường minh; test live sẽ chứng minh **nhánh URL** chứ không giả vờ rằng đã test tất cả dispatcher types hoặc ordering concurrency.

**Không áp dụng một kết luận cứng cho `MockMvc` về header scoped này.** Cách đưa `FilterRegistrationBean` vào mock chain và giữ URL mapping có thể khác cách container thực áp registration; đó chính là lý do test live dùng request qua socket để xác minh hợp đồng filter registration.

### 6.7. Test MOCK: filter trong context và request metadata tự tạo

**File `src/test/java/com/example/boundary/MockBoundaryTest.java`:**

```java
package com.example.boundary;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
    classes = BoundaryApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
class MockBoundaryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void springFilterBeanRunsInMockFilterChain()
            throws Exception {

        mvc.perform(get("/api/public/inspect")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string(
                        "X-Global-Stamp", "active"))
                .andExpect(jsonPath("$.path").value(
                        "/api/public/inspect"));
    }

    @Test
    void httpsAndRemoteAddressCanBeFakedWithoutTls()
            throws Exception {

        mvc.perform(get("/api/public/inspect")
                .with(request -> {
                    request.setScheme("https");
                    request.setSecure(true);
                    request.setServerPort(443);
                    request.setRemoteAddr("203.0.113.10");
                    return request;
                }))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Global-Stamp", "active"))
                .andExpect(jsonPath("$.scheme").value("https"))
                .andExpect(jsonPath("$.secure").value(true))
                .andExpect(jsonPath("$.port").value(443))
                .andExpect(jsonPath("$.remoteAddress")
                        .value("203.0.113.10"));
    }
}
```

**Kết quả kỳ vọng:** **2 phương thức `@Test` pass** trên một Spring Boot 3.x MVC project đúng cấu hình. Không có cổng HTTPS 443 hoặc kết nối từ địa chỉ `203.0.113.10` thật. Các giá trị được đặt trên `MockHttpServletRequest` bởi test.

Đây là điểm học tập quan trọng: controller trả `"https"` và `secure=true` trong MockMvc **không chứng minh certificate được tin cậy, TLS handshake hoàn tất hoặc request thực đã được mã hóa**. Test mới chỉ kiểm tra logic controller phản ứng với thuộc tính request giả.

Test cũng chứng minh một `Filter` Spring bean **có thể chạy trong mock chain**, nhưng **không kết luận** gì về URL mapping của `ScopedFilter` từ kết quả đó.

### 6.8. Test real container: port, context path và filter registration

**File `src/test/java/com/example/boundary/RealContainerBoundaryTest.java`:**

```java
package com.example.boundary;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = BoundaryApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "server.servlet.context-path=/demo"
)
class RealContainerBoundaryTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    private HttpResponse<String> get(String path)
            throws Exception {

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(
                        "http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    @Test
    void privateUrlIsMappedToContainerRegisteredFilter()
            throws Exception {

        assertThat(port).isGreaterThan(0);

        HttpResponse<String> response =
                get("/demo/api/private/inspect");

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.headers().firstValue(
                "X-Global-Stamp")).contains("active");
        assertThat(response.headers().firstValue(
                "X-Scoped-Stamp")).contains("private-only");

        JsonNode json = mapper.readTree(response.body());
        assertThat(json.path("path").asText()).isEqualTo(
                "/demo/api/private/inspect");
        assertThat(json.path("scheme").asText()).isEqualTo(
                "http");
        assertThat(json.path("secure").asBoolean()).isFalse();
    }

    @Test
    void publicUrlDoesNotMatchPrivateFilterRegistration()
            throws Exception {

        HttpResponse<String> response =
                get("/demo/api/public/inspect");

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.headers().firstValue(
                "X-Global-Stamp")).contains("active");
        assertThat(response.headers().firstValue(
                "X-Scoped-Stamp")).isEmpty();

        JsonNode json = mapper.readTree(response.body());
        assertThat(json.path("path").asText()).isEqualTo(
                "/demo/api/public/inspect");
    }

    @Test
    void realContextPathChangesReachableHttpUrl()
            throws Exception {

        HttpResponse<String> missingPrefix =
                get("/api/public/inspect");

        assertThat(missingPrefix.statusCode()).isEqualTo(404);

        HttpResponse<String> correctPrefix =
                get("/demo/api/public/inspect");

        assertThat(correctPrefix.statusCode()).isEqualTo(200);
    }
}
```

**Kết quả kỳ vọng:** **3 phương thức `@Test` pass** trên dự án Spring Boot 3.x có embedded Servlet MVC server từ web starter và không có security/proxy khác can thiệp. Client gửi request HTTP thật đến loopback port được Boot chọn; context path `/demo` là cấu hình server ở test class.

Bài test live này chứng minh:

- Embedded server mở được một TCP port thực.
- Client có thể GET qua socket vào application.
- Filter bean toàn cục được container áp dụng.
- Filter đăng ký theo URL pattern chỉ tác động nhánh `/api/private/*` (URL public không có header riêng).
- `server.servlet.context-path=/demo` ảnh hưởng route có thể truy cập từ client.

**Không tuyên bố** nó đã kiểm chứng HTTPS, mTLS, reverse proxy, tất cả `DispatcherType` hoặc container khác: URI là `http://127.0.0.1`; snippet chỉ dùng REQUEST và một embedded container cụ thể được chọn bởi dependencies.

### 6.9. Chạy test

Linux/macOS — chọn **một** build tool của dự án:

```bash
# Gradle Wrapper:
./gradlew test --tests "com.example.boundary.MockBoundaryTest"
./gradlew test --tests "com.example.boundary.RealContainerBoundaryTest"

# Hoặc Maven Wrapper:
./mvnw -Dtest=MockBoundaryTest test
./mvnw -Dtest=RealContainerBoundaryTest test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.boundary.MockBoundaryTest"
.\gradlew.bat test --tests "com.example.boundary.RealContainerBoundaryTest"

# Hoặc Maven Wrapper:
.\mvnw.cmd "-Dtest=MockBoundaryTest" test
.\mvnw.cmd "-Dtest=RealContainerBoundaryTest" test
```

Tổng ví dụ có **5 bài JUnit test**, gồm **2 bài MockMvc + 3 bài live HTTP**. Code không chủ động in `stdout`; Spring Boot, Maven/Gradle và IDE có thể ghi log startup/test summary theo cấu hình. Đọc test report để xác nhận test đã thực thi, không chỉ dựa vào exit code của build có cache.

## 7. Vì sao không nên so sánh cứng mọi kết quả MockMvc và live server?

### 7.1. Các cấu hình servlet khác nhau có thể được mô phỏng khác

MockMvc có thể dùng `MockServletContext` và thực thi `MockFilterChain`. Embedded server dùng một ServletContext do container khởi tạo, áp dụng các mappings và `ServletContextInitializer`. Một bài test MockMvc và một bài live HTTP có thể tạo context với profile/property khác nhau, vì vậy so sánh kết quả mà không ghi lại cấu hình dễ dẫn đến kết luận sai.

Ví dụ runnable cố ý **không khẳng định** filter `ScopedFilter` có hoặc không có header trong MockMvc; điều muốn kiểm chứng là **Servlet container URL mapping**, nên kiểm tra ở đường live. MockMvc chỉ được dùng cho assertion filter bean và khả năng giả lập request scheme.

### 7.2. `addFilters=true` không hứa mô phỏng mọi registration metadata

Có `@AutoConfigureMockMvc(addFilters = true)` không có nghĩa:

- container init lifecycle đã được thực hiện giống real startup;
- URL mapping của `FilterRegistrationBean` chắc chắn được áp nguyên vẹn;
- `DispatcherType.ERROR/ASYNC` và thứ tự container mappings đã được chứng minh;
- security proxy setup hoặc header trust đã hoạt động qua mạng.

Hãy dùng MockMvc để kiểm tra logic filter có thể gọi, nhưng dùng real HTTP để kiểm tra những hợp đồng thuộc container và connector.

### 7.3. Một filter có thể tự từ chối request

Nếu `Filter#doFilter` trả lỗi 403 trước khi gọi `chain.doFilter(...)`, controller sẽ không được gọi. Trong MockMvc, điều đó có thể được tái hiện **nếu đúng filter được đăng ký**. Nhưng nếu filter chỉ đăng ký cho URL/dispatcher cụ thể ở real container, việc ép đăng ký filter vào mọi request của MockMvc có thể tạo kết quả **khác production**.

Khi gặp 403 ở live test nhưng 200 ở MockMvc, hãy kiểm tra (a) filter chain nào chạy ở từng test, (b) security, (c) URL/dispatcher mapping và (d) cấu hình environment, thay vì đoán controller sai.

## 8. Cấu hình mạng nào mock web environment không chứng minh được?

### 8.1. Port, bind address và server startup

Spring Boot có các property như:

- `server.port`: cổng HTTP;
- `server.address`: địa chỉ interface bind;
- `server.servlet.context-path`: context path của Servlet application;
- `management.server.port`: cổng quản trị nếu khác cổng app.

Trong `webEnvironment = MOCK` không có socket listening, nên việc test inject một property `server.port=8080` hoặc nhìn thấy nó trong `Environment` chỉ chứng minh **giá trị config được resolve**, không chứng minh cổng 8080 bind thành công.

Trong live HTTP test, `RANDOM_PORT` thường chọn cổng rảnh nên ít tranh chấp trên CI. Khi cần test port cụ thể, `DEFINED_PORT` có thể hữu ích, nhưng cần cô lập parallel workers và bảo đảm port chưa được chiếm. Không dùng port production thật cho bài test thường ngày.

**Quy tắc:** Nếu câu hỏi là “app có nhận được config port không?”, unit/context test có thể đủ. Nếu câu hỏi là “client kết nối được vào port không?”, cần real server/HTTP client. Nếu câu hỏi là “người dùng ngoài mạng truy cập được không?”, cần test từ **mạng tương ứng**, không chỉ localhost.

### 8.2. Context path và Servlet mapping

Cấu hình:

```properties
server.servlet.context-path=/demo
```

ảnh hưởng URI mà một client ngoài JVM gọi. Một request từ client tới `/demo/api/public/inspect` sẽ đi vào app, còn `/api/public/inspect` có thể trả 404 vì thiếu context path.

MockMvc có thể tạo mock request với context path được thiết lập bằng builder/postprocessor. Tuy nhiên, việc thủ công đặt `contextPath("/demo")` hoặc `servletPath(...)` trên mock request **không chứng minh** connector và ServletContext trong live server đã triển khai đúng config.

### 8.3. Header limits, URI limits, request body size

Servlet containers có thể giới hạn:

- tổng kích thước header hoặc request line;
- số lượng headers/request params;
- kích thước form post hoặc multipart request;
- thời gian đọc body, connection timeout;
- số kết nối đồng thời, backlog và thread pool.

Trong MockMvc bạn có thể nạp trực tiếp mock request content và header với kích thước lớn; nó **không phải phép kiểm chứng** rằng real connector sẽ chấp nhận/cấm request bytes đó theo policy.

Để test 413/400/431 hoặc kết quả transport khác từ giới hạn, dùng HTTP client thật với payload được kiểm soát, chọn container thực tế, và đối chiếu các property của đúng version. **Không mặc định mọi container sẽ trả cùng status code** cho mọi loại vượt giới hạn.

### 8.4. HTTP/2, compression, keep-alive, streaming

Các property như `server.http2.enabled`, `server.compression.enabled` và các cấu hình connector khác chỉ có nghĩa khi server và protocol support tương ứng được thực thi. MockMvc có thể assert một response header do code app set, nhưng không đo được handshake HTTP/2, wire compression, chunked transfer, connection reuse hay client disconnect.

Một live HTTP test vẫn cần dùng **client/protocol đúng** để chứng minh tính năng. JDK HttpClient mặc định có thể tự negotiate protocol và tự xử lý một số behavior; khi test HTTP/2, phải kiểm tra thực tế `HttpResponse.version()` và TLS/ALPN nếu liên quan.

### 8.5. Request scheme và `isSecure()` có thể bị giả lập

Trong mã mẫu, MockMvc có thể đặt:

```java
request.setScheme("https");
request.setSecure(true);
request.setServerPort(443);
```

Đây là **ba thao tác giả lập trong RequestPostProcessor**, không phải cấu hình SSL. Nếu controller tạo absolute URL dựa vào `request.getScheme()`, test có thể xác minh kết quả theo giả lập HTTPS. Nhưng nó **không xác nhận** keystore, truststore, certificate, SNI hoặc handshake.

Một live test muốn chứng minh TLS phải dùng `https://` với server SSL thực và HTTP client được cấu hình trust chain hợp lệ. Không tạo shortcut bỏ certificate verification trong production test chỉ để test xanh.

## 9. Forwarded headers, reverse proxy và ranh giới tin cậy

### 9.1. Vì sao mock header không chứng minh proxy đang đúng?

Khi reverse proxy kết thúc HTTPS và gọi backend HTTP, proxy có thể thêm:

```text
Forwarded: proto=https;host=shop.example.org
X-Forwarded-Proto: https
X-Forwarded-Host: shop.example.org
X-Forwarded-For: 203.0.113.10
```

Đây là ví dụ minh họa, **không phải một yêu cầu phải tin mọi header**. Backend có thể dùng những header này để tạo redirect/absolute URL hoặc biết client address. Tuy nhiên, một client bất kỳ cũng có thể **tự gửi** header giả nếu edge proxy không loại bỏ/sửa chúng.

MockMvc test viết:

```java
mvc.perform(get("/api/public/inspect")
        .header("X-Forwarded-Proto", "https"))
        .andExpect(status().isOk());
```

chỉ chứng minh request với header được cấp có thể đi qua test pipeline. Nó **không chứng minh** trusted proxy thực sẽ thêm header đúng, client ngoài không giả mạo được, hay app đã trust đúng proxy hops.

### 9.2. `server.forward-headers-strategy`

Trong Spring Boot Servlet app, property:

```properties
server.forward-headers-strategy=framework
```

yêu cầu framework xử lý forwarded headers theo cơ chế Spring, ví dụ `ForwardedHeaderFilter` khi phù hợp. Những chiến lược có thể gặp:

- `none`: không xử lý forwarded headers theo chiến lược đó;
- `native`: dựa vào hỗ trợ của servlet container;
- `framework`: dùng hỗ trợ từ Spring Framework.

**Không xem đây là giải pháp tự động chống spoofing.** Dù dùng `native` hay `framework`, phải xác định **trust boundary** ở reverse proxy/ingress: edge phải loại bỏ hoặc chuẩn hóa các forwarded headers đến từ client không tin cậy, rồi mới gửi bản đã được xác thực logic tới backend.

### 9.3. ForwardedHeaderFilter và order

Theo Spring Framework, `ForwardedHeaderFilter` có thể wrap request để `getScheme()`, `getServerName()` hoặc các trường liên quan phản ánh thông tin đã được forwarded. Nó cần chạy **trước** những filter/handler khác phụ thuộc vào thông tin đã sửa. Ở error/async dispatch, mapping của filter cần được cấu hình phù hợp.

Vì vậy test chỉ dùng MockMvc với header giả không đủ kiểm chứng:

- filter được đăng ký trong real container với order đúng;
- forwarding từ ingress thật;
- thuật toán chọn trusted hop/container valve;
- security redirect/cookie Secure/SameSite trong đường network;
- behavior khi có nhiều giá trị `X-Forwarded-For` và các proxy trung gian.

Hãy tách kiểm thử:

1. **Unit/MockMvc:** logic xử lý forwarded headers trong MVC/filter khi bạn cấp input có kiểm soát.
2. **Live HTTP to embedded server:** chiến lược xử lý filter/container và request metadata qua connector.
3. **Staging/infrastructure:** proxy trust, ingress/TLS, redirect và client address thực sự đi qua các hops triển khai.

### 9.4. Không log dữ liệu nhạy cảm khi debug

Request headers có thể chứa `Authorization`, Cookie, session token và IP cá nhân. Tránh `andDo(print())` toàn bộ request trong CI khi dữ liệu nhạy cảm xuất hiện; nếu cần log, mask hoặc chỉ ghi tên header và metadata không nhạy cảm. Đừng dùng client IP trong test làm bằng chứng danh tính người dùng.

## 10. Spring Security: filter chain và real authentication là hai mục tiêu

### 10.1. MockMvc vẫn có thể kiểm tra authorization

Nếu ứng dụng có Spring Security và filter chain được cấu hình trong MockMvc, bạn có thể test:

- 401/403 khi thiếu authentication/quyền;
- request được chấp nhận khi principal có role phù hợp;
- CSRF với unsafe methods;
- SecurityContext truyền vào controller trong test;
- một số security headers do ứng dụng/filter tạo.

Chẳng hạn Spring Security Test có `@WithMockUser` hoặc request processors `user(...)` / `csrf()`. Chúng giúp test authorization nhanh và có giá trị.

### 10.2. Điều chưa được kiểm chứng bởi mock user

Một `@WithMockUser` test **không đi qua login/OIDC handshake production**, không xác nhận issuer/JWK retrieval thực, không có TLS session, cookie policy của browser hay proxy auth. Ngay cả HTTP localhost với một fake JWT còn không chứng minh IdP hoặc gateway production hoạt động.

Nên giữ cả hai nhóm test khi có yêu cầu bảo mật:

- **authorization tests** bằng MockMvc/Spring Security Test cho policy cụ thể;
- **protocol/integration tests** qua real HTTP và môi trường có authentication infrastructure tương ứng cho login, JWT decoding, session cookie, gateway, OAuth redirect.

### 10.3. Vì sao một test 403 có thể là filter problem chứ không phải controller bug?

Request có thể bị từ chối trước khi tới DispatcherServlet vì security filter hoặc container filter. Quy trình debug:

1. Xác định status, exception và vị trí filter chain.
2. Kiểm tra URL pattern/dispatcher của real container.
3. Kiểm tra auth/CSRF/roles và order của security filters.
4. So sánh mock chain với live chain.
5. Chỉ sau đó mới tìm lỗi mapping/controller.

**Không bật `addFilters=false` trên tất cả test** để tránh 403 rồi kết luận API đã đạt security contract.

## 11. Lỗi HTTP khác giữa MockMvc và container: các case điển hình

### 11.1. GET trên MockMvc thành công, live HTTP không kết nối

**Có thể do:** server chưa khởi động, sai webEnvironment, sai cổng, bind address, firewall hoặc client gửi tới host khác.

Kiểm tra `@SpringBootTest(webEnvironment = RANDOM_PORT)`, `@LocalServerPort`, server startup log và URI có port được inject. `@SpringBootTest(MOCK)` **không mở port**; đó không phải lỗi của MockMvc.

### 11.2. Live HTTP 404 còn MockMvc 200

Có thể do:

- thiếu `server.servlet.context-path` ở URI thật;
- servlet mapping, path prefix, case-sensitivity hoặc encoded path;
- proxy rewrite hoặc header handling;
- hai test dùng profile/configuration khác nhau;
- request được gửi sang sai server/port.

Ví dụ test live ở phần 6 đặt `/demo`, nên client gọi thiếu prefix nhận 404 có chủ đích. MockMvc test cùng app không đặt context path đó; kết quả không thể so sánh “cùng một URI” một cách máy móc khi test configurations khác nhau.

### 11.3. Filter hiện trên MockMvc nhưng không chạy ở live HTTP

Có thể do URL pattern không khớp, `DispatcherType` khác, registration bị disable, filter được tạo từ config chỉ có trong mock context, hoặc order với filter khác làm short-circuit.

Cần điều tra **chính registration bean và request thực**, không chỉ tìm xem bean tồn tại ở application context. Nếu filter cần chạy với async/error, đảm bảo mapping được khai báo và `OncePerRequestFilter` hook không bỏ qua dispatch đó.

### 11.4. Live HTTP có filter effect còn MockMvc không có

Có thể filter chỉ tồn tại dưới dạng container registration (không là filter bean được MockMvc tự thêm), hoặc có initialization/registration qua `ServletContextInitializer`, `@ServletComponentScan`, web.xml hoặc server container mechanism. Trong MockMvc standalone, bạn cũng có thể quên gọi `addFilters(...)`.

**Kết luận đúng:** mock chain và live chain chưa cùng cấu hình. Không lập tức “sửa” production filter để phù hợp MockMvc; trước hết xác định test cần chứng minh **logic filter** hay **container registration**.

### 11.5. Live HTTP 400/413/431 nhưng MockMvc tiếp nhận request

Nghi ngờ raw header size, request line, multipart/form size, encoding hoặc HTTP protocol parser. Spring MVC validation có thể vẫn trả 400 trong cả hai, nhưng container rejection diễn ra **trước controller** và không thể được xem là một `@Valid` error.

Dùng controlled HTTP request với kích thước phù hợp và container version cố định. Không dự đoán status chỉ từ giá trị property mà không kiểm tra thực nghiệm trên container đang dùng.

### 11.6. HTTP redirect sai scheme/host

Nghi ngờ forwarded-header strategy, proxy trust, filter order, context path hoặc host header. Test MockMvc với `request.setScheme("https")` chỉ chứng minh controller xây URL đúng **trên request metadata giả lập**. Cần live HTTP và, khi liên quan, môi trường proxy để chứng minh redirect người dùng thật.

## 12. Giao dịch và thread boundary khi chuyển sang HTTP thật

### 12.1. Test transaction với MockMvc đồng bộ

Spring TestContext có thể mở một **test-managed transaction** cho test method `@Transactional`. Trong request MockMvc xử lý đồng bộ cùng test thread, controller/service/repository có thể tham gia giao dịch ấy khi transaction manager và propagation phù hợp; Spring thường rollback test transaction sau method theo mặc định.

Nhưng không được đảm bảo mọi side effect rollback: async work, `REQUIRES_NEW`, external queue, file, remote HTTP call hoặc transaction manager khác có thể nằm ngoài phạm vi.

### 12.2. Real HTTP client và server có transaction khác

Với `RANDOM_PORT` hoặc `DEFINED_PORT`, client và server chạy trên **các thread khác nhau**, theo hướng dẫn Spring Boot. Giao dịch từ test thread **không tự áp dụng** cho server thread, nên những thao tác server commit không được rollback chỉ bằng `@Transactional` trên JUnit test.

**Hệ quả:** thay `mockMvc.perform(post(...))` bằng HTTP client thật và vẫn tin rằng mọi DB writes được rollback có thể làm suite phụ thuộc thứ tự test. Cần DB/schema riêng, seed và cleanup, Testcontainers hoặc fixture management phù hợp.

### 12.3. Parallel test và môi trường mạng

- `RANDOM_PORT` tránh tranh cổng cố định nhưng không xóa mọi race.
- Các test có HTTP server có thể chia sẻ static state, DB, broker, cache hoặc port management.
- Context cache có thể tái sử dụng các context có cấu hình tương thích; mutable singleton state phải được reset.
- Một test thay global JVM system property rồi không restore có thể ảnh hưởng test khác.
- Đừng dùng `@DirtiesContext` như cách thay thế cho cleanup dữ liệu đã commit ngoài context.

## 13. Test phương pháp nào cho từng hợp đồng?

| Điều cần chứng minh | Test nên ưu tiên | Vì sao |
|---|---|---|
| Controller trả đúng JSON/status | MockMvc slice/full-context | Nhanh, đủ Spring MVC pipeline |
| `Filter#doFilter` set header/chặn request đúng | MockMvc có đúng filter chain | Đo logic filter mà không cần server |
| `FilterRegistrationBean` chỉ map một URL pattern | **Real HTTP + embedded container** | Đo mapping được Servlet container áp dụng |
| Filter chạy trong `ERROR/ASYNC` dispatch | Live server với test dispatch tương ứng | Mock request đồng bộ chưa đủ |
| Port có thể bind và client kết nối được | `RANDOM_PORT`/`DEFINED_PORT` + HTTP client | Cần socket thực |
| Context path và servlet mapping thực | Real HTTP với URI bao gồm context path | Đo endpoint reachable từ client |
| Thay `X-Forwarded-Proto` đổi redirect logic | MockMvc + filter config đúng | Kiểm tra Spring logic với input giả |
| Proxy thực có loại header giả mạo không | Staging/e2e qua trusted proxy | Test ở trust boundary thực |
| TLS certificate/HTTPS | Real HTTPS + truststore, hoặc staging | Cần handshake/chứng chỉ |
| Header-size/connector limits | Real HTTP trên container đúng | MockMvc không có network parser |
| HTTP/2, gzip, streaming, keep-alive | Live protocol/client tests | Có transport và connector |
| Spring Security authorization | MockMvc + security filter chain | Kiểm thử rule nhanh |
| OAuth/SSO/browser cookies thật | Live HTTP/browser/infrastructure integration | Mock principal không mô phỏng login protocol |
| Test DB rollback qua request | Tùy thread/test model; real HTTP cần cleanup riêng | Không chia sẻ test transaction qua server thread |

**Tối ưu test suite:** đa số mapping/JSON/validation/security rules có thể nằm ở MVC tests. Chỉ những hợp đồng thuộc container/network mới cần tập HTTP tests được chọn lọc. Sau đó thêm test hạ tầng khi proxy/TLS/ingress là một phần yêu cầu.

## 14. Version: Spring Boot 2, 3 và 4

### 14.1. Spring Boot 3.x (mã runnable của bài)

Những imports chính:

```java
import jakarta.servlet.Filter;
import jakarta.servlet.DispatcherType;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
```

Dự án Boot 3.x thường dùng `spring-boot-starter-web` và `spring-boot-starter-test`. Boot 3 yêu cầu Java 17+, dùng Jakarta Servlet packages.

### 14.2. Spring Boot 2.x

Spring Boot 2.x phổ biến với `javax.servlet.*` thay vì `jakarta.servlet.*`, và có baseline Java/dependency khác. Nếu sao chép Java source Boot 3 sang Boot 2, imports Servlet có thể không biên dịch. Thay cho tương thích tùy phiên bản và không mặc định mọi annotation/test class có cùng package.

Nguyên lý **MOCK không mở server**, **MockMvc dùng mock Servlet pipeline**, **RANDOM_PORT dùng real embedded server** vẫn là cách hiểu chính, nhưng code/build cần đối chiếu với docs nhánh cũ.

### 14.3. Spring Boot 4.x

Boot 4 modular hóa testing và thay đổi một số package/starter. Ví dụ `@AutoConfigureMockMvc` được tổ chức trong package:

```java
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
```

Các starter phù hợp MVC gồm `spring-boot-starter-webmvc` và `spring-boot-starter-webmvc-test`, theo phiên bản release. Cần đối chiếu Servlet API, JSON/Jackson, testing module và JDK với BOM Boot 4 của project.

**Không chuyển Boot 3 sang 4 bằng cách đổi một import rồi giữ nguyên mọi dependency**. Mã runnable của bài được ghi rõ đích Spring Boot 3.x, tránh khẳng định source biên dịch y nguyên trên mọi nhánh Boot 4.x.

### 14.4. WebFlux khác Servlet MVC

Với WebFlux, bạn thường dùng `WebFilter`, `WebTestClient` và một server Reactive (ví dụ Reactor Netty); nó không sử dụng `jakarta.servlet.Filter`/`FilterRegistrationBean` theo cùng cơ chế nếu app không chạy trên Servlet stack.

`WebTestClient` cũng có **chế độ không dùng server** khi bind tới handler/context, và chế độ **HTTP thật** khi bind tới server. Không dựa vào tên client để kết luận đã qua mạng; hãy kiểm tra setup của test.

## 15. Bài tập thực hành

### Bài A. Giải thích hai kết quả không mâu thuẫn

Trong MockMvc, test:

```java
mvc.perform(get("/api/public/inspect")
        .with(request -> {
            request.setScheme("https");
            request.setSecure(true);
            return request;
        }))
        .andExpect(jsonPath("$.scheme").value("https"));
```

pass. Có thể kết luận server đã bật HTTPS chưa?

**Đáp án:** chưa. Test chỉ giả lập request metadata; không có TLS handshake, certificate, connector hoặc HTTPS port thật. Muốn kiểm thử HTTPS phải dựng SSL server và dùng client HTTPS xác minh trust.

### Bài B. Filter chỉ chạy trên private endpoint

Bạn đăng ký filter qua `FilterRegistrationBean` với `addUrlPatterns("/api/private/*")`. Khi app có context path `/demo`, client nên thử hai URI nào?

**Đáp án:** `/demo/api/private/inspect` và `/demo/api/public/inspect`. Bài live HTTP phải xác minh header/effect có ở private và không có ở public. Pattern của registration vẫn là `/api/private/*`, không thêm context path vào pattern.

### Bài C. Tại sao addFilters=false không xóa bean filter?

Cho:

```java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc(addFilters = false)
class ExampleTest {
}
```

Hỏi: một Spring bean `GlobalStampFilter` có bị xóa khỏi `ApplicationContext` không?

**Đáp án:** không mặc nhiên. Annotation thay đổi filter registration vào **MockMvc**, không phải component scanning hoặc bean definition của Spring context. Với real server, filter vẫn có thể được Boot đăng ký theo cấu hình của app.

### Bài D. ERROR dispatch bị bỏ sót

Filter chỉ đặt `setDispatcherTypes(DispatcherType.REQUEST)`, nhưng yêu cầu nghiệp vụ đòi ghi audit cả error dispatch. Có thể kết luận test GET đồng bộ pass là đủ không?

**Đáp án:** không. Cần cấu hình `ERROR` mapping phù hợp, kiểm tra logic `OncePerRequestFilter`/container và chạy test có error dispatch thật. Chú ý response có thể đã commit trước error page, nên đừng đặt assertion header theo suy đoán; thiết kế fixture rõ ràng.

### Bài E. Proxy tin X-Forwarded-For không đáng tin

Client Internet tự gửi `X-Forwarded-For: 127.0.0.1` rồi backend coi request từ localhost. Lỗi có thể nằm ở đâu?

**Đáp án:** trust boundary bị cấu hình sai. Proxy/ingress cần loại hoặc chuẩn hóa các forwarded headers từ client không tin cậy; backend chỉ trust thông tin do các proxy được cấu hình đúng tạo ra. Test MockMvc gửi header giả chỉ kiểm tra logic parsing, không phát hiện proxy thực không sanitize header.

### Bài F. Chọn phạm vi test cho HTTP 413

Một upload lớn pass trong MockMvc nhưng khi gọi live Tomcat nhận status lỗi. Có nên sửa controller validation theo kết quả mock?

**Đáp án:** chưa. Kiểm tra kích thước body, multipart/connector limits, proxy limits, request encoding và exception layer. Dùng live HTTP test với server/container đã xác định để kiểm chứng expected behavior. Status cụ thể phụ thuộc nơi từ chối request, không nên đoán toàn bộ từ một config flag.

### Bài G. Test database qua live HTTP không rollback

Một JUnit test có `@Transactional` POST qua `RANDOM_PORT`; bản ghi vẫn tồn tại sau test. Có phải `@Transactional` hỏng?

**Đáp án:** không nhất thiết. HTTP server xử lý ở thread/transaction khác, nên rollback ở test thread không tự rollback phần server. Cần data cleanup hoặc isolated test database phù hợp.

## 16. Checklist trước khi chốt bài test về filter/container/network

- [ ] Biết test đang dùng `@WebMvcTest`, `@SpringBootTest(MOCK)` hay `RANDOM_PORT`.
- [ ] Biết chính xác request đi qua MockMvc hay HTTP client/socket.
- [ ] Không coi filter bean có mặt trong context là đủ chứng minh container registration.
- [ ] Không coi MockMvc `addFilters=true` là bằng chứng URL pattern/dispatcher mapping thật.
- [ ] Phân biệt `FilterRegistrationBean`, `@WebFilter`/`@ServletComponentScan` và Spring `@Component`.
- [ ] Tránh double registration do khai báo cùng filter bằng nhiều cơ chế thiếu kiểm soát.
- [ ] Đã xét `DispatcherType.REQUEST/ASYNC/ERROR` và `OncePerRequestFilter` hooks khi cần.
- [ ] Đã kiểm tra order khi filter phụ thuộc nhau, không chỉ assert header tồn tại.
- [ ] Có HTTP test cho URL pattern hoặc network property thuộc hợp đồng.
- [ ] Với context path, client URI và registration pattern phân biệt rõ.
- [ ] `@LocalServerPort` chỉ dùng cho real embedded server test.
- [ ] Không gọi localhost qua HTTP rồi cho rằng đã test TLS/proxy/DNS.
- [ ] Forwarded headers chỉ được tin từ các proxy/hops đã được cấu hình an toàn.
- [ ] Security filter chain và CSRF không bị bỏ qua ngoài ý định.
- [ ] HTTP client timeout, headers, body encoding và port được xác định.
- [ ] Không dựa vào Spring test `@Transactional` để rollback server thread khi real HTTP.
- [ ] Đúng Servlet packages/test starters theo Boot major version.
- [ ] Không đụng production DB, production endpoints hoặc secret thật trong CI.
- [ ] Mock tests giữ vai trò phản hồi nhanh; real HTTP tests đo đúng container boundary.
- [ ] Có bài test e2e riêng nếu hợp đồng liên quan proxy, gateway, TLS hoặc hạ tầng triển khai.

## 17. Kết luận

**Mock web environment không có Servlet container đang chạy qua network.** Nó rất mạnh để kiểm tra Spring MVC request handling, và filter logic vẫn có thể chạy nếu được đưa vào MockFilterChain. Nhưng các hợp đồng thuộc **Servlet container registration** (URL patterns, dispatcher types, order, lifecycle) và thuộc **network** (port, context path từ client, connector, TLS, compression, forwarded headers qua proxy) cần phép kiểm chứng bổ sung tại đúng boundary.

Với Spring Boot, hãy dùng **MockMvc cho phần logic web** và **RANDOM_PORT + HTTP client cho hợp đồng container/transport**, sau đó thêm test đi qua gateway/proxy/staging khi đặc tính triển khai là yêu cầu. Đừng nâng mọi test lên live HTTP; cũng đừng dùng một test MockMvc pass để khẳng định toàn bộ môi trường mạng production đã được chứng minh.

## Tài liệu tham khảo chính thức

- [Spring Framework — MockMvc Overview](https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html): dùng mock Servlet API + DispatcherServlet mà không có running server.
- [Spring Framework — MockMvc Filter Registrations](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/filters.html): đăng ký filter vào MockFilterChain trong test.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `MOCK`, `RANDOM_PORT`, embedded server và transaction caveat.
- [Spring Boot 3.5 — FilterRegistrationBean Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/FilterRegistrationBean.html): đăng ký filter theo URL/servlet mapping và startup.
- [Spring Boot 3.5 — Embedded Web Servers How-to](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): Servlet/Filter/Listener registration, dispatch type mặc định và lifecycle.
- [Spring Boot 3.5 — AutoConfigureMockMvc Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/AutoConfigureMockMvc.html): `addFilters` và mock configuration.
- [Spring Framework — Servlet Filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): ForwardedHeaderFilter, trust boundary, async/error dispatcher mappings.
- [Spring Boot 3.5 — ForwardHeadersStrategy](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/ServerProperties.ForwardHeadersStrategy.html): `NATIVE/FRAMEWORK/NONE`.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): port, SSL, HTTP/2, compression và forwarded headers.
- [Java 17 — HttpClient Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP client dùng để kiểm tra embedded server qua socket.
