# Kiểm tra phụ thuộc, ánh xạ URL và phiên bản khi kết hợp nhiều nền tảng web trong Spring Boot

## 1. Mục tiêu và tình huống thực tế

Một ứng dụng Spring Boot có thể lớn dần từ REST API đơn giản thành hệ thống chứa nhiều công nghệ: Spring MVC, WebFlux client, Jersey/JAX-RS, servlet tùy chỉnh, security filters, static assets, WebSocket, template engines, Actuator và reverse proxy phía trước. Có thể tất cả đều chạy tốt riêng lẻ, nhưng **kết hợp** chúng có thể gây ba nhóm lỗi khó nhận diện:

1. **Phụ thuộc (dependencies/classpath):** hai starters chọn hai web stacks khác nhau; thư viện kéo theo phiên bản Spring/Jakarta/Jersey không tương thích; dependency transitively override library chuẩn của Boot; trùng JSON providers hoặc embedded servers.
2. **Ánh xạ URL (routing/mapping):** Jersey servlet mặc định phủ `/*` và chiếm request của DispatcherServlet; custom servlet hoặc filter match quá rộng; nhầm context path với servlet path; proxy sửa URI; đường dẫn của MVC, JAX-RS, static assets và Actuator xung đột.
3. **Phiên bản (versions/contracts):** Boot/Framework/server/Jakarta APIs không đồng bộ; namespace `javax.*` đời cũ trộn với `jakarta.*`; URL `/v1` và `/v2` mơ hồ; khác biệt routing khi nâng Spring Framework; test chạy được trong IDE nhưng executable JAR lại lỗi classpath hoặc scanning.

**Nguyên tắc triển khai:** xác định rõ **một web runtime chính**, chọn dependencies theo BOM của cùng bản Spring Boot, cấp **mỗi nền tảng một vùng URL** và kiểm thử HTTP thật ở đúng từng tầng. Không chỉ kiểm tra “mvn package thành công”.

Bài viết sử dụng **Java 17+ và Spring Boot 3.5.16** để trình bày; các mã nguồn đầy đủ mô phỏng ứng dụng chứa **Spring MVC + Jersey/JAX-RS + một Servlet tùy chỉnh** trên cùng embedded Tomcat, với các URL riêng biệt. Đồng thời có phần giải thích MVC + WebFlux, Jakarta APIs, security filters, version alignment, kiểm thử và các lỗi thường gặp.

### Sau bài này, cần trả lời được

- Vì sao thêm `spring-boot-starter-webflux` vào MVC **không tự chuyển** application thành WebFlux?
- Vì sao Jersey có thể khiến `@GetMapping` MVC trả 404 dù method đúng?
- Trong `/app/api/hello`, thành phần nào là **context path**, **servlet mapping** và **controller path**?
- Cách dùng Maven/Gradle xem **runtime dependency tree** và BOM-managed versions?
- Vì sao không nên tự ghim `spring-webmvc`, Jersey hoặc Jakarta Servlet versions thiếu kiểm soát?
- Làm thế nào thử route thuộc **đúng công nghệ**, thay vì chỉ nhìn status 200?
- Khi qua Nginx/Ingress, phải xác định URL public, URL upstream và handler thực nhận ra sao?

## 2. “Kết hợp nhiều nền tảng” có những trường hợp nào?

Không phải cứ có nhiều web libraries là nhiều HTTP servers đang tranh nhau nhận request. Cần phân loại:

| Tổ hợp | Có thể dùng? | Điểm cốt lõi |
| --- | --- | --- |
| Spring MVC + RestClient | Có, phổ biến | MVC xử lý inbound; RestClient gọi outbound HTTP đồng bộ |
| Spring MVC + WebClient | Có | Thêm WebFlux library cho **outbound client**, inbound thường vẫn MVC |
| Spring MVC + Jersey/JAX-RS | Có, nếu có thiết kế mapping | Cả hai là Servlet-based frameworks; phân chia `DispatcherServlet` và Jersey servlet |
| Spring MVC + servlet tùy chỉnh | Có | Dùng `ServletRegistrationBean` với path cụ thể, tránh chiếm `/*` |
| Spring MVC + Thymeleaf + static assets | Có | Template/view resolver và static handlers; kiểm tra path trùng controller |
| WebFlux + Reactor Netty | Có, mặc định reactive starter | Reactor Netty xử lý inbound, Reactor/WebFlux reactive stack |
| WebFlux + JPA/JDBC blocking | Có về kỹ thuật nhưng phải xử lý đúng | Không chạy blocking JDBC trên event loop |
| MVC + WebFlux server trong **một** Boot app | Không tự động chạy hai dispatcher cùng lúc | Boot 3.5 **ưu tiên MVC** khi cả hai starters cùng có |
| Jersey/JAX-RS + Spring Security Servlet | Có, nhưng cần policy/filter rõ | Security filter gắn vào Servlet request pipeline, không chỉ MVC controller |
| gRPC + HTTP REST + WebSocket | Có nếu thư viện/server tương thích | Có thể dùng **listener/port/protocol** khác; không mặc định chia cùng mapping |
| JSF/Vaadin + Spring MVC | Có với tích hợp tương thích | Có servlet/filter/view lifecycle riêng, cần version/mapping phù hợp |
| Actuator + REST API | Có | Endpoint management có thể ở cùng hoặc khác port/base path |

**Các từ giống nhau không tương đương:**

- WebFlux **server** khác WebClient **client**.
- Servlet container (Tomcat/Jetty/Undertow) khác Spring MVC DispatcherServlet.
- Jersey REST resource khác Spring MVC `@RestController` dù cả hai có thể cùng trả JSON.
- JAX-RS `jakarta.ws.rs.Path` không phải Spring MVC `@RequestMapping`.
- URL public qua ingress không nhất thiết là URI thấy ở backend.
- API version `/v2` của nghiệp vụ khác **library version** và khác version Spring Boot.

## 3. Bước 1: xác định web application type thực tế

### 3.1. Spring MVC (Servlet stack)

Với Spring Boot 3.5, `spring-boot-starter-web` thông thường mang Spring MVC và embedded Tomcat. Pipeline mặc định:

```text
HTTP connection -> Tomcat
     -> Servlet filters
     -> DispatcherServlet
     -> HandlerMapping
     -> @RestController / @Controller
     -> HTTP response
```

Spring MVC dùng Jakarta Servlet APIs và `DispatcherServlet`, thích hợp ứng dụng imperative sử dụng JDBC/JPA, synchronous service calls, view templates hoặc servlet integration.

### 3.2. Spring WebFlux (reactive stack)

`spring-boot-starter-webflux` thường dùng Reactor Netty làm embedded server trong project reactive thuần:

```text
HTTP connection -> Reactor Netty
     -> HttpHandler/WebFilter
     -> DispatcherHandler/RouterFunction
     -> Mono/Flux handler
     -> HTTP response
```

WebFlux không yêu cầu Servlet API để chạy, có model reactive streams/backpressure. Tuy vậy **WebFlux cũng có thể chạy trên một số Servlet containers với adapter**, tùy cấu hình; đừng đồng nhất “WebFlux” với “Netty” trong mọi kiến trúc.

### 3.3. Khi cả hai starters cùng có

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

Đây là **fragment Maven**, không phải POM hoàn chỉnh. Theo Spring Boot 3.5, khi có cả MVC và WebFlux trên classpath, **MVC được chọn làm web application type mặc định**. Đây là hành vi có chủ đích để ứng dụng MVC vẫn dùng được outbound `WebClient`.

Hệ quả:

- Controller `@GetMapping` thường được Spring MVC `RequestMappingHandlerMapping` quản lý.
- Có thể dùng `WebClient` để gọi dịch vụ khác; không phải đang có thêm một WebFlux `DispatcherHandler` độc lập chịu trách nhiệm inbound.
- Các cấu hình `WebFluxConfigurer` hoặc `spring.webflux.*` không tự trở thành cấu hình MVC.
- Nếu ứng dụng phải **thực sự** chạy reactive, chọn starter/runtime đúng hoặc đặt `spring.main.web-application-type=reactive` sau khi đánh giá cả classpath; điều đó **không** biến Servlet-specific Jersey integration thành reactive.

**Không thêm cả hai starters chỉ để “tăng hiệu năng”**. Chọn một runtime chính; thêm client libraries nếu có nhu cầu cụ thể.

### 3.4. Kiểm tra runtime qua code và log

Khi ứng dụng đã start, có thể dùng một component kiểm tra context type (snippet, không phải project demo):

```java
@Component
class RuntimeReporter implements ApplicationRunner {
    private final ApplicationContext context;

    RuntimeReporter(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Context=" +
                context.getClass().getSimpleName());
    }
}
```

Mã này cần imports Spring `ApplicationRunner`, `ApplicationArguments`, `ApplicationContext` và `@Component`. Trong ứng dụng MVC embedded server, thường thấy một Servlet web application context; reactive server sử dụng Reactive web context. Không dựa chỉ vào tên class in ra nếu có custom context; kết hợp với dependency tree, startup logs và HTTP test.

## 4. Bước 2: kiểm tra dependency graph và version alignment

### 4.1. Spring Boot BOM là nguồn phiên bản chính

Spring Boot phát hành `spring-boot-dependencies` **Bill of Materials (BOM)** quản lý phiên bản tương thích của Spring Framework, embedded server, Jackson, validation, logging và rất nhiều thư viện thứ ba.

Với Maven, cách đơn giản là dùng `spring-boot-starter-parent`:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>
```

Sau đó thường **không cần khai báo `<version>` riêng** cho `spring-boot-starter-web`, `spring-boot-starter-jersey` và các dependencies được BOM quản lý.

Với Gradle, dùng plugin và dependency management/platform BOM đúng phiên bản. Ví dụ khi dùng Spring Dependency Management plugin:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

java {
    toolchain { languageVersion = JavaLanguageVersion.of(17) }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-jersey'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đây là **fragment build.gradle minh họa dependency management**; phiên bản plugin Gradle và cấu trúc project cần phù hợp với Gradle wrapper thực. Không dùng đồng thời nhiều BOM khác nhau rồi giả định version selection không có xung đột.

### 4.2. Lệnh Maven kiểm tra dependencies

Chạy tại thư mục có `pom.xml`:

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework:*
mvn dependency:tree -Dincludes=org.glassfish.jersey:*
mvn dependency:tree -Dincludes=jakarta.servlet:*
mvn help:effective-pom -Doutput=effective-pom.xml
mvn dependency:analyze
```

Ý nghĩa:

- `dependency:tree`: nhìn các transitive dependencies, server và libraries thực được chọn.
- `-Dincludes`: thu hẹp group/artifact để thấy Spring/Jersey/Jakarta.
- `help:effective-pom`: xem parent/BOM/plugin/dependency management sau khi hợp nhất.
- `dependency:analyze`: hỗ trợ phát hiện used/unused/undeclared dependencies (có ngoại lệ với reflection/runtime providers).
- Bản **runtime classpath** mới là thứ thực sự được packaged/chạy. Có thể cần kiểm tra `mvn dependency:build-classpath` và nội dung executable JAR.

Trong PowerShell, nếu dấu `*` được shell xử lý không như mong đợi, hãy quote nguyên tham số `"-Dincludes=org.springframework:*"`. Không coi một lệnh báo “không có kết quả” là đã chứng minh không có dependency nếu filter sai.

### 4.3. Gradle kiểm tra transitive dependencies

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jersey-server --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jakarta.servlet-api --configuration runtimeClasspath
```

Gradle có cơ chế version conflict resolution khác Maven; `dependencyInsight` giúp giải thích vì sao một version được chọn. Kiểm tra cả build và IDE run configuration nếu chỉ IDE tái hiện lỗi.

### 4.4. Danh sách những nhóm version cần cùng thế hệ

| Thành phần | Điều cần xác nhận | Lỗi thường gặp nếu sai |
| --- | --- | --- |
| Spring Boot 3.5.x | Parent/BOM và starters nhất quán | Auto-configuration khác kỳ vọng |
| Spring Framework | Do Boot BOM quản lý, không ghim ngẫu nhiên | `NoSuchMethodError`, handler/config incompatibility |
| Tomcat 10.1.x | Servlet/Jakarta generation phù hợp | Classloading/Servlet API mismatch |
| Jersey 3.x | Jakarta JAX-RS và Jersey modules tương thích | `ClassNotFoundException`, provider/servlet init failure |
| Jackson | Jackson core/databind/module versions đồng bộ | Decode error, method linkage, duplicated providers |
| Spring Security | Đúng Boot generation và filter chain runtime | Filter/API incompatibility |
| Jakarta Servlet | `jakarta.servlet.*` trên Boot 3.x | `javax.servlet.*` incompatible |
| Jakarta REST | `jakarta.ws.rs.*` đối với Jersey 3.x | Provider hoặc resource không đăng ký |
| Reactor Netty | Dùng phiên bản BOM quản lý nếu thêm WebFlux | Codec/Netty runtime mismatch |
| JDK | **Java 17+** cho Boot 3.5 | `UnsupportedClassVersionError` hoặc build error |

Boot 3.x chuyển sang hệ sinh thái Jakarta EE. Nhiều thư viện cũ dùng `javax.servlet.*`, `javax.ws.rs.*` không thể thay bằng đổi import một cách máy móc; phải nâng **toàn bộ API/provider/adapter** tương thích.

### 4.5. Những anti-pattern về version

- Tự khai báo `org.springframework:spring-webmvc:5.x` trong Spring Boot 3.5 vì một ví dụ cũ.
- Thêm `javax.servlet:javax.servlet-api` rồi viết Filter theo `javax.servlet.Filter` cho Tomcat 10.x.
- Bắt Jersey 2.x (javax) chạy chung với Jersey 3.x (jakarta) thông qua transitive dependencies.
- Pin một module Jackson khác đời với phần còn lại mà không có tests.
- Thay một Spring Framework module độc lập để sửa CVE, bỏ qua BOM/Boot patch và dependency compatibility.
- Giữ cả embedded Tomcat lẫn Jetty starters không có chủ đích; gây khó đọc runtime selection/classpath.
- Thêm client library gọi HTTP nhưng vô tình kéo server auto-configuration thay đổi.

**Cách xử lý:** nâng **Spring Boot patch** và curated dependencies theo BOM khi có thể; các overrides phải được ghi lý do, kiểm tra security advisories và có tests regression. Không chỉ “mvn compile pass” — lỗi linkage thường xuất hiện lúc startup hoặc lúc endpoint được gọi.

## 5. Bước 3: mô hình ánh xạ URL gồm nhiều lớp

URL mà browser thấy không giống tuyệt đối với pattern trong `@GetMapping`. Với embedded Servlet application, hãy nghĩ theo thứ tự:

```text
Scheme + Host + Port
    |
    +-- Reverse proxy public prefix / rewrite (nếu có)
    |
    +-- Servlet context path
    |
    +-- Servlet mapping (DispatcherServlet / Jersey servlet / custom)
    |
    +-- Framework handler path (MVC @GetMapping / JAX-RS @Path)
    |
    +-- HTTP method + headers + params + consumes/produces
```

Ví dụ:

```text
http://localhost:8080/demo/mvc/hello
  host:port         /demo   /mvc/hello
                    context   MVC controller mapping
```

Khi `DispatcherServlet` mặc định được map ở `/`, Spring MVC handler mapping có thể sở hữu `/mvc/hello`. Một Jersey servlet được map `/jaxrs/*` thì path ngoài cùng `/demo/jaxrs/hello` được **Servlet container chuyển vào Jersey**, không phải Spring MVC.

### 5.1. Servlet context path

```properties
server.servlet.context-path=/demo
```

Property này đặt context root cho **Servlet web application**, ví dụ MVC, Jersey và servlet đăng ký trong cùng servlet context đều được truy cập sau `/demo`. Nó không phải là `@RequestMapping` của controller và không phải proxy public prefix.

### 5.2. DispatcherServlet mapping

Mặc định Spring Boot MVC dùng `DispatcherServlet` nhận routing từ root context; controller có thể:

```java
@RestController
@RequestMapping("/mvc")
class HelloController {
    @GetMapping("/hello")
    String hello() { return "mvc-ok"; }
}
```

Đây là snippet. Với context path `/demo`, URL là `/demo/mvc/hello`.

Có thể đổi Servlet mapping của MVC bằng `spring.mvc.servlet.path`. Tuy nhiên với **Spring Boot 3.5, PathPatternParser mặc định có hạn chế khi dùng một servlet path prefix**. Nếu thật sự cấu hình:

```properties
server.servlet.context-path=/demo
spring.mvc.servlet.path=/spring-api
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
```

thì MVC controller `@GetMapping("/hello")` có thể được truy cập theo URL `/demo/spring-api/hello`. **Không tự áp dụng `spring.mvc.servlet.path` lên Jersey servlet hoặc custom servlet**. Trước khi dùng, kiểm tra cụ thể Boot/Framework version và regression tests; chỉ để phân tách URL thường không cần đổi DispatcherServlet mapping, có thể dùng `@RequestMapping("/mvc")` đơn giản hơn.

### 5.3. Jersey `@ApplicationPath`

Spring Boot có starter và auto-configuration cho Jersey/JAX-RS. Khi không giới hạn mapping, **Jersey servlet mặc định có thể được map `/*`**, chiếm request mà bạn tưởng MVC sẽ xử lý.

Giải pháp rõ ràng:

```java
@Component
@ApplicationPath("/jaxrs")
class JerseyResources extends ResourceConfig {
    JerseyResources() {
        register(JerseyHelloResource.class);
    }
}
```

Đây là snippet. Với `@ApplicationPath("/jaxrs")`, Jersey được ánh xạ dưới prefix `/jaxrs` trong servlet context. Một resource `@Path("/hello")` tương ứng `/demo/jaxrs/hello` trong ví dụ có context `/demo`.

**Lưu ý khi đóng gói executable JAR:** tài liệu Boot 3.5 khuyến nghị **register từng resource class** qua `ResourceConfig.register(...)` thay vì dựa vào `packages(...)` scanning, vì Jersey scanning trên executable archives có hạn chế. Resources nên là `@Component` nếu cần Spring DI và có annotations JAX-RS như `@GET`, `@Path`.

### 5.4. Custom Servlet mapping

`ServletRegistrationBean` cho bạn kiểm soát servlet name và URL pattern:

```java
@Bean
ServletRegistrationBean<HealthServlet> healthServlet() {
    return new ServletRegistrationBean<>(
            new HealthServlet(), "/legacy/*");
}
```

Đây là snippet, `HealthServlet` là Servlet do ứng dụng định nghĩa. Nên map hẹp như `/legacy/*`, tránh `/*` hoặc `/` nếu không thực sự muốn thay đổi behavior của toàn servlet container. Trong project hoàn chỉnh bên dưới, custom servlet phục vụ `/legacy/health` và không intercept MVC/Jersey.

### 5.5. Servlet container chọn Servlet trước khi framework chọn controller

Quan trọng: với Spring MVC + Jersey + custom Servlet, routing có **hai cấp**:

1. Servlet container chọn servlet theo path mapping (exact, longest path-prefix, extension, default, theo Servlet spec).
2. **Chỉ sau khi** servlet đã nhận request, Spring MVC `HandlerMapping` hoặc Jersey resource matching mới chọn handler ở bên trong.

Vì vậy, hai endpoint có text `/hello` ở **hai servlet khác nhau** không nhất thiết là “ambiguous MVC mapping”; chúng có thể được phân biệt rõ bằng `/mvc/*` và `/jaxrs/*`. Ngược lại, nếu Jersey được map `/*` và MVC `/`, Jersey có thể nhận request trước khi Spring MVC kịp match.

**Không mong đợi Spring MVC báo “Ambiguous mapping” cho conflict xảy ra ở Servlet container trước đó.** Spring MVC chỉ thấy phần request đã vào DispatcherServlet.

## 6. Ma trận ownership URL nên lập trước khi code

Ví dụ với `server.servlet.context-path=/demo`:

| URL public local | Owner mong đợi | Định nghĩa | Kiểm thử đúng |
| --- | --- | --- | --- |
| `/demo/mvc/hello` | Spring MVC | `@RequestMapping("/mvc")` + `@GetMapping("/hello")` | Body `mvc-ok` |
| `/demo/jaxrs/hello` | Jersey/JAX-RS | `@ApplicationPath("/jaxrs")` + `@Path("/hello")` | Body `jersey-ok` |
| `/demo/legacy/health` | Custom Servlet | `ServletRegistrationBean("/legacy/*")` | Body `legacy-ok` |
| `/demo/mvc/missing` | MVC, không có endpoint | MVC mapping miss / static handler fallback | HTTP 404 |
| `/demo/jaxrs/missing` | Jersey, không có resource | Jersey resource miss | HTTP 404 |
| `/demo/hello` | Không được đăng ký | Tránh đoán owner | HTTP 404 |
| `/demo/assets/app.js` | Static resource **nếu có** | MVC resource handler hoặc servlet khác | 200 nếu file thực tồn tại |
| `/actuator/health` | Actuator **nếu được thêm** | Management base path/port config | Không suy diễn từ app endpoints |

**Không đánh giá thành công chỉ bằng status 200**. Ví dụ một fallback SPA trả HTML index với HTTP 200 cho `/api/missing` không có nghĩa endpoint đúng. Kiểm tra Content-Type, body, response header và route owner.

### Đường dẫn khác nhau theo loại endpoint

- Spring MVC `@RequestMapping` và `@GetMapping`: path tương đối **trong DispatcherServlet**.
- Jersey `@Path`: path tương đối **trong Jersey application mapping**.
- Servlet `/legacy/*`: xử lý `getServletPath()`/`getPathInfo()` tùy pattern.
- Static resources: `spring.mvc.static-path-pattern` áp dụng MVC resource handlers, không tự thay Jersey mapping.
- WebFlux: có hệ thống `HandlerMapping` và `spring.webflux.static-path-pattern` khác với MVC.
- Actuator management port/base-path: có thể là listener/context khác.
- Reverse proxy public prefix: có thể được strip/rewrite trước khi tới app.

## 7. Xung đột URL còn phát sinh từ đâu?

### 7.1. Hai MVC controllers đăng ký cùng một request mapping

Nếu hai phương thức MVC trùng **method + path + điều kiện mapping** (headers, params, consumes, produces...), Spring MVC có thể báo ambiguous mapping trong startup. Không “giải quyết” bằng tăng `@Order` ngẫu nhiên; hãy tạo đường dẫn riêng hoặc làm rõ điều kiện request mapping.

Nếu patterns chỉ chồng nhau một phần nhưng có độ đặc hiệu khác nhau, Spring MVC có thể chọn theo specificity. Vì vậy cần **test các URL thật** chứ không chỉ tìm chuỗi giống nhau trong source.

### 7.2. Jersey chiếm `/*`

Jersey servlet mapping `/*` có thể cạnh tranh với DispatcherServlet default `/`. Triệu chứng: MVC controller tồn tại nhưng `GET /api/users` trả 404; log Jersey nhận request hoặc resource not found. Sửa bằng `@ApplicationPath("/jaxrs")` hoặc cấu hình rõ ServletRegistrationBean/route ownership.

Đừng sửa bằng cách tắt `@RestController`, thêm `@ComponentScan` bừa bãi hoặc đổi random cổng trước khi xác định Servlet nào nhận URL.

### 7.3. Servlet hoặc Filter chiếm quá rộng

Servlet được đăng ký `/*` có thể nhận mọi URL, dẫn đến MVC/Jersey/Actuator không còn được dispatch như mong đợi. Filter map `/*` có thể tác động đến **mọi Servlet**, không chỉ MVC. Khi filter trả `401`/`403` trước khi gọi `chain.doFilter`, framework handlers không chạy.

Đăng ký filter dùng `FilterRegistrationBean` và đặt URL pattern rõ khi filter chỉ dành cho một subsystem. Phân biệt security filter chain của Spring Security với servlet filter tự định nghĩa.

### 7.4. Static resources, WebJars và SPA fallback

Spring MVC thường đăng ký static resource mapping `/**` để phục vụ classpath `/static`, `/public` và các vị trí khác. Một request thiếu controller route có thể đi tới resource handler rồi trả 404 dưới dạng `NoResourceFoundException`, không nhất thiết `NoHandlerFoundException`. Nếu SPA fallback cấu hình bắt `/**` và trả `index.html` cho mọi path, API 404 có thể bị che bằng HTML 200.

Nên phân chia rõ:

- `/api/**` cho backend APIs.
- `/assets/**` cho hashed static assets.
- `/webjars/**` cho WebJars nếu dùng.
- `/ui/**` hoặc `/` cho frontend.
- `/jaxrs/**` cho Jersey.
- `/legacy/**` cho custom servlet.

Đừng đặt tất cả handler/filter vào `/**` mà không có tests thứ tự/behavior.

### 7.5. Security, CORS và CSRF

Khi phối hợp MVC và Jersey cùng trên Servlet stack, Spring Security `FilterChainProxy` hoạt động ở **Servlet filter level**. Security policy chỉ viết theo `MvcRequestMatcher` cho một DispatcherServlet path có thể không bao phủ resource thuộc Jersey/custom servlet theo kỳ vọng.

Cần kiểm tra:

- `SecurityFilterChain` nào match `/jaxrs/**` và `/legacy/**`.
- Authentication/authorization áp dụng cả non-MVC endpoints.
- CSRF cho unsafe methods (POST/PUT/DELETE) nếu dùng cookie/session.
- CORS preflight `OPTIONS` được xử lý đúng filter order và path.
- Login/logout redirect và error pages không chiếm namespace khác.
- Không coi “bị 403” là bằng chứng controller/Jersey route bị sai; security filter có thể chặn trước.

**Không cấp `permitAll("/**")` trong production** chỉ để “để các nền tảng cùng chạy”. Mục tiêu là phân quyền rõ từng namespace và test negative access.

## 8. Versioned API paths khác library version

### 8.1. Hai khái niệm

- **Library version**: Spring Boot 3.5.x, Spring Framework 6.2.x, Jersey 3.x, Tomcat 10.1.x; quyết định classpath và APIs runtime.
- **API version**: `/api/v1/orders`, `/api/v2/orders`, Accept vendor media type hoặc version header; quyết định hợp đồng với client.

Nâng Spring Boot version **không tự biến** URL `/api/v1` thành `/api/v2`. Ngược lại, giữ URL `/api/v1` không bảo đảm library cũ vẫn tương thích với runtime Jakarta.

### 8.2. Thiết kế URL versioning nhất quán

Ví dụ dành vùng cho từng nền tảng:

```text
/app/mvc/v1/products           Spring MVC v1
/app/mvc/v2/products           Spring MVC v2
/app/jaxrs/v1/report           Jersey JAX-RS legacy v1
/app/jaxrs/v2/report           Jersey JAX-RS v2
/app/legacy/health             Custom Servlet không version hóa public API
```

Không để hai API versions có cùng path/method mà chỉ phân biệt bằng giả định “version mới được load trước”. Nếu dùng header/media type versioning, configure resolver/mapping chính xác theo Spring Framework version và **test requests có/không có version header**.

### 8.3. API version không phải Bean version

Một codebase có thể cung cấp v1 và v2 từ cùng Java service nhưng DTO khác. Không tạo hai beans `@RestController` trùng mapping rồi kỳ vọng component name quyết định phiên bản URL. Nếu thay đổi JSON contract, dùng DTO/version mapping rõ, kiểm thử backward compatibility.

### 8.4. Deprecation và rollback

Khi chuyển v1 sang v2:

1. Xác định client đang dùng v1 và mức độ tương thích.
2. Cấp endpoint mới có namespace/version rõ.
3. Thêm contract tests cho cả v1/v2.
4. Đảm bảo cache/CDN và route proxy phân biệt versions.
5. Lập migration deadline có monitoring.
6. Không xóa v1 trước khi client đã chuyển theo chính sách.
7. Ghi release notes và rollback plan nếu upgrade framework/server làm route behavior thay đổi.

## 9. Reverse proxy, context path và đường dẫn hiệu lực

Một ứng dụng có thể chạy nội bộ:

```text
http://backend:8080/app/mvc/hello
```

nhưng public URL là:

```text
https://example.com/service/mvc/hello
```

Nginx/Ingress có thể strip `/service` và thêm `/app`, hoặc giữ nguyên path. **Chỉ nhìn `@GetMapping("/mvc/hello")` không đủ** để tính public URL.

### 9.1. Hai trường hợp `proxy_pass` của Nginx

Giả sử backend có route `/app/mvc/hello`.

Cấu hình ví dụ **giữ nguyên URI**:

```nginx
location /app/ {
    proxy_pass http://127.0.0.1:8080;
}
```

Request `/app/mvc/hello` có thể được gửi upstream với nguyên path `/app/mvc/hello`.

Trường hợp **có URI slash cuối**:

```nginx
location /app/ {
    proxy_pass http://127.0.0.1:8080/;
}
```

Nginx có thể thay prefix `/app/` bằng `/`, nên request `/app/mvc/hello` đến upstream thành `/mvc/hello`; backend đòi context `/app` sẽ **404**. Sửa ở proxy route/rewrite, không phải thêm `@CrossOrigin("*")` hay đổi Java controller.

Đây là **fragment Nginx**, không phải cấu hình proxy sản xuất hoàn chỉnh. Trong container/Kubernetes, `127.0.0.1` của Nginx không tự trỏ sang process ở pod khác; dùng service DNS/network phù hợp.

### 9.2. Forwarded headers

`Forwarded` hoặc `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Prefix` có thể mô tả đường public khi TLS termination/rewrite xảy ra ở proxy. Spring Boot có `server.forward-headers-strategy`, nhưng bật nó **không tự sửa sai URI rewrite**.

Chỉ tin forwarded headers từ proxy được cấu hình kiểm soát; Internet client có thể giả mạo header nếu gateway không lọc/ghi đè. Kiểm thử redirect URL, absolute links, cookies và request origin sau proxy.

### 9.3. So sánh trực tiếp và qua proxy

```bash
curl -i http://localhost:8080/app/mvc/hello
curl -i https://example.com/service/mvc/hello
```

Lệnh thứ hai là **URL minh họa**, không phải endpoint truy cập được. Khi debug, dùng domain/host thật được cấp, và so request ID/status/Location/path qua proxy và backend; không dùng một ví dụ hostname giả để kết luận hệ thống.

## 10. Project hoàn chỉnh: MVC, Jersey và custom Servlet cùng một Boot app

Project này dùng Spring Boot **3.5.16**, Java **17+** và Maven. Mục đích chứng minh:

- Spring MVC giữ namespace `/mvc/**` trong DispatcherServlet mặc định.
- Jersey/JAX-RS dùng `@ApplicationPath("/jaxrs")`, không chiếm `/*`.
- Một servlet legacy được đăng ký rõ `/legacy/*`.
- Cả ba nằm dưới **context path `/app`**.
- Một integration test gọi HTTP thật và xác nhận đúng body cho từng owner.

Không cần database, Redis, Docker, frontend, token hay partner API. Không thêm WebFlux starter vì demo không cần outbound WebClient; phần MVC + WebFlux được kiểm thử về nguyên tắc ở mục 3.

### 10.1. Cấu trúc thư mục

```text
multi-web-platform-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/multiweb/
    │   │   ├── MultiWebApplication.java
    │   │   ├── MvcHelloController.java
    │   │   ├── JerseyConfiguration.java
    │   │   ├── JerseyHelloResource.java
    │   │   └── LegacyServletConfiguration.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/multiweb/
            └── MultiPlatformRoutingTest.java
```

Đặt tất cả classes trong package `com.example.multiweb` để `@SpringBootApplication` component scan tìm được. Các class public phải nằm trong file trùng tên. Class package-private có thể ở chung file.

### 10.2. `pom.xml` đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>multi-web-platform-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jersey</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

**Tại sao POM này đúng phạm vi?**

- `spring-boot-starter-web` cung cấp Spring MVC + embedded Tomcat.
- `spring-boot-starter-jersey` cung cấp Jersey runtime/JAX-RS integration được Boot quản lý.
- Không tự ghim `jersey-server`, `spring-webmvc`, `jakarta.ws.rs-api` hoặc `tomcat-embed-core` versions; dùng Boot BOM.
- `starter-test` cung cấp JUnit và HTTP integration test tools.
- `java.version=17` phù hợp baseline của Spring Boot 3.5.

Không thêm `spring-boot-starter-webflux` chỉ để có “nhiều platforms”. Sự tích hợp cần được thiết kế dựa vào yêu cầu, không dựa vào số dependencies.

### 10.3. Application main

Tệp `src/main/java/com/example/multiweb/MultiWebApplication.java`:

```java
package com.example.multiweb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiWebApplication {

    public static void main(String[] args) {
        SpringApplication.run(MultiWebApplication.class, args);
    }
}
```

Application khởi động một embedded Servlet container và đăng ký các components. Không cần tự tạo ServletContext hay DispatcherServlet bằng tay.

### 10.4. MVC controller

Tệp `src/main/java/com/example/multiweb/MvcHelloController.java`:

```java
package com.example.multiweb;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/mvc")
public class MvcHelloController {

    @GetMapping(value = "/hello",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return "mvc-ok\n";
    }
}
```

`@RestController` là Spring MVC component. Với context path `/app` và DispatcherServlet mặc định ở root context, URL đầy đủ là **`/app/mvc/hello`**, body là chuỗi `mvc-ok` kèm newline.

### 10.5. Jersey ResourceConfig và `@ApplicationPath`

Tệp `src/main/java/com/example/multiweb/JerseyConfiguration.java`:

```java
package com.example.multiweb;

import jakarta.ws.rs.ApplicationPath;

import org.glassfish.jersey.server.ResourceConfig;
import org.springframework.stereotype.Component;

@Component
@ApplicationPath("/jaxrs")
public class JerseyConfiguration extends ResourceConfig {

    public JerseyConfiguration() {
        register(JerseyHelloResource.class);
    }
}
```

**Tác dụng:** Jersey servlet được giới hạn ở vùng `/jaxrs/**`. Không để nó giữ mapping mặc định `/*` và lấn sang `/mvc/**`. Đăng ký resource class **tường minh** để chạy trong executable JAR thay vì dùng `packages(...)` scanning không đáng tin ở một số kiểu đóng gói.

### 10.6. Jersey resource

Tệp `src/main/java/com/example/multiweb/JerseyHelloResource.java`:

```java
package com.example.multiweb;

import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

import org.springframework.stereotype.Component;

@Component
@Path("/hello")
public class JerseyHelloResource {

    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String hello() {
        return "jersey-ok\n";
    }
}
```

`@Path` và `@GET` là **JAX-RS annotations**, không phải Spring MVC `@GetMapping`. Java resource có `@Component` để tham gia Spring lifecycle, đồng thời được Jersey `ResourceConfig.register(...)` đăng ký xử lý HTTP.

Với context path `/app` + Jersey mapping `/jaxrs/*` + resource path `/hello`, endpoint là **`/app/jaxrs/hello`**, body `jersey-ok` + newline.

### 10.7. Custom Servlet đăng ký hẹp

Tệp `src/main/java/com/example/multiweb/LegacyServletConfiguration.java`:

```java
package com.example.multiweb;

import java.io.IOException;

import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LegacyServletConfiguration {

    @Bean
    ServletRegistrationBean<LegacyHealthServlet>
    legacyHealthServletRegistration() {
        ServletRegistrationBean<LegacyHealthServlet> bean =
                new ServletRegistrationBean<>(
                        new LegacyHealthServlet(), "/legacy/*");
        bean.setName("legacyHealthServlet");
        return bean;
    }
}

class LegacyHealthServlet extends HttpServlet {

    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response) throws IOException {
        if (!"/health".equals(request.getPathInfo())) {
            response.sendError(HttpServletResponse.SC_NOT_FOUND);
            return;
        }
        response.setCharacterEncoding("UTF-8");
        response.setContentType("text/plain");
        response.getWriter().write("legacy-ok\n");
    }
}
```

Đây là **một Java file hợp lệ**: `LegacyServletConfiguration` public đúng tên file; `LegacyHealthServlet` package-private. Chỉ `ServletRegistrationBean` là Spring bean; **không** thêm `@Component` lên `LegacyHealthServlet` hoặc đăng ký một Servlet bean thứ hai làm lặp mapping.

`/legacy/*` nghĩa request `/app/legacy/health` vào custom servlet. Khi đó `request.getPathInfo()` là `/health`. Một URL `/app/legacy/unknown` đi vào servlet nhưng được handler tự trả 404.

### 10.8. Cấu hình ứng dụng

Tệp `src/main/resources/application.properties`:

```properties
server.port=8080
server.servlet.context-path=/app
spring.application.name=multi-web-platform-demo

# Không chỉnh spring.mvc.servlet.path trong demo này.
# Jersey mapping được định nghĩa bằng @ApplicationPath("/jaxrs").
```

**Điểm chủ ý:** `/app` là Servlet context path **chung**; namespace `/mvc`, `/jaxrs` và `/legacy` thuộc các framework/Servlet khác nhau. Không cần thay DispatcherServlet mapping nên tránh được vấn đề tương thích `spring.mvc.servlet.path` với `PathPatternParser`.

### 10.9. Build và chạy

Từ thư mục có `pom.xml`, cần JDK 17+ và Maven:

```bash
java -version
mvn -version
mvn clean package
java -jar target/multi-web-platform-demo-1.0.0.jar
```

Sau khi ứng dụng khởi động (port 8080 còn trống), dùng terminal thứ hai:

```bash
curl -i http://localhost:8080/app/mvc/hello
curl -i http://localhost:8080/app/jaxrs/hello
curl -i http://localhost:8080/app/legacy/health
```

Cả ba là HTTP 200 nếu mapping được đăng ký đúng. Các body tương ứng:

```text
mvc-ok
```

```text
jersey-ok
```

```text
legacy-ok
```

Mỗi body kết thúc bằng một newline. Trong `curl -i` còn có các HTTP headers, và format status line có thể khác theo môi trường; **giá trị body** là điều ổn định trong source demo.

Kiểm tra các URL âm tính:

```bash
curl -i http://localhost:8080/app/mvc/missing
curl -i http://localhost:8080/app/jaxrs/missing
curl -i http://localhost:8080/app/legacy/missing
curl -i http://localhost:8080/app/hello
```

Những request này nên trả HTTP 404 theo hạ tầng/handlers tương ứng; nội dung error body có thể khác giữa MVC, Jersey và custom Servlet. Không đồng nhất mọi 404 với “Spring MVC không tìm thấy controller” — hãy xác định **Servlet owner**.

Nếu gọi `http://localhost:8080/mvc/hello` **thiếu `/app`**, request không vào đúng context của demo, nên không cho kết quả MVC endpoint thành công.

### 10.10. Một phép thử gửi sai method

```bash
curl -i -X POST http://localhost:8080/app/mvc/hello
curl -i -X POST http://localhost:8080/app/jaxrs/hello
```

Cả hai endpoints chỉ khai báo GET. Kết quả thường là HTTP 405 Method Not Allowed khi request tới đúng handler; error body/header `Allow` có thể khác giữa MVC và Jersey. Nếu thêm Spring Security/CSRF, POST có thể bị chặn trước handler bằng 401/403; khi đó phải debug filter chain trước, không tuyên bố controller mapping sai.

## 11. Integration test HTTP thật cho từng nền tảng

Tệp `src/test/java/com/example/multiweb/MultiPlatformRoutingTest.java`:

```java
package com.example.multiweb;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MultiPlatformRoutingTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate http;

    private String url(String path) {
        return "http://localhost:" + port + "/app" + path;
    }

    @Test
    void mvcOwnsItsPath() {
        ResponseEntity<String> response =
                http.getForEntity(url("/mvc/hello"), String.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("mvc-ok\n", response.getBody());
    }

    @Test
    void jerseyOwnsItsPath() {
        ResponseEntity<String> response =
                http.getForEntity(url("/jaxrs/hello"), String.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("jersey-ok\n", response.getBody());
    }

    @Test
    void legacyServletOwnsItsPath() {
        ResponseEntity<String> response =
                http.getForEntity(url("/legacy/health"), String.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("legacy-ok\n", response.getBody());
    }

    @Test
    void wrongPrefixIsNotAnAlias() {
        ResponseEntity<String> response =
                http.getForEntity(url("/hello"), String.class);
        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    }
}
```

Chạy:

```bash
mvn test
```

**Vì sao nên có HTTP integration test, không chỉ MockMvc?**

- `MockMvc` tập trung vào Spring MVC DispatcherServlet pipeline; nó **không tương đương** HTTP container dispatch qua Jersey servlet và custom servlet.
- `@SpringBootTest(RANDOM_PORT)` chạy embedded server thật, kiểm tra Servlet registration, context path và Jersey auto-configuration.
- `TestRestTemplate` gửi request thật tới random port, tránh đụng cổng 8080.
- Test kiểm tra **body đặc trưng của owner** thay vì chỉ kiểm tra 200, giúp phát hiện fallback/route shadowing.
- Một lỗi do `Jersey servlet /*` chiếm MVC route thường được phát hiện bởi test `mvcOwnsItsPath`.

Các tests trên dựa vào cấu hình example và không thử proxy production. Để kiểm tra TLS, gateway, authentication và rewrites, cần thêm smoke test trên môi trường triển khai thực.

### 11.1. Nếu test từ IDE khác với executable JAR

Jersey có thể hạn chế package scanning trong executable archives. Demo dùng `register(JerseyHelloResource.class)` tường minh để tránh phụ thuộc classpath scanner. Khi thay code và một thử nghiệm chỉ pass trong IDE nhưng fail sau `java -jar`, hãy so sánh classpath, file packaging và resource registration, không tự kết luận lỗi do Java bytecode.

Kiểm tra packaged JAR:

```bash
jar tf target/multi-web-platform-demo-1.0.0.jar
```

Tìm các class của ứng dụng trong `BOOT-INF/classes/` và libraries trong `BOOT-INF/lib/`. Với Gradle/War packaging, layout sẽ khác; không gán các đường dẫn này cho mọi loại artifact.

### 11.2. Còn cần những tests nào?

| Test | Mục đích | Cấp độ |
| --- | --- | --- |
| `GET /app/mvc/hello` trả `mvc-ok` | MVC mapping đúng | HTTP integration |
| `GET /app/jaxrs/hello` trả `jersey-ok` | Jersey resource đăng ký đúng | HTTP integration |
| `GET /app/legacy/health` trả `legacy-ok` | ServletRegistrationBean đúng | HTTP integration |
| Sai URL `/app/hello` trả 404 | Không có alias ngẫu nhiên | Negative integration |
| Các POST không được phép | Kiểm tra method contracts | Negative integration |
| Không auth vào `/jaxrs/private` | Security coverage ngoài MVC | Security integration |
| Versioned paths v1/v2 | Đảm bảo không shadow routes | Contract regression |
| CORS preflight từng namespace | Filters/policy đúng | Browser + HTTP |
| Static assets/WebJars URLs | Không bị Jersey/SPA chiếm | Resource integration |
| Reverse proxy public prefix | URI rewrite/forwarded headers đúng | Deployment smoke tests |

## 12. Kiểm tra mappings khi ứng dụng có nhiều hệ thống

### 12.1. Spring MVC mappings không đại diện mọi Servlet

Có thể lấy danh sách mappings từ Spring MVC `RequestMappingHandlerMapping` hoặc Actuator `/actuator/mappings` khi dependency/exposure phù hợp. Nhưng:

- MVC mappings mô tả handler **trong DispatcherServlet**, không tự liệt kê đầy đủ JAX-RS resources như MVC annotations.
- Actuator mappings trong Servlet app có thể hiển thị servlet registrations/filter mappings và dispatcher mappings, tùy cấu hình/version.
- Jersey có registry/resource model riêng, nên cần kiểm tra `ResourceConfig`, annotations `@Path` và HTTP routes.
- Custom Servlet có `ServletRegistrationBean`, path pattern không phải `@GetMapping`.
- Proxy/Ingress routes nằm **ngoài Spring Boot**; không xuất hiện trong MVC HandlerMapping.

**Không chỉ grep `@GetMapping` để kết luận không có conflict.** Lập inventory theo layer.

### 12.2. Actuator mappings (khi được phép)

Nếu cần dùng Actuator cho môi trường dev, thêm starter vào POM rồi cấu hình exposure một cách có kiểm soát:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

```properties
management.endpoints.web.exposure.include=health,info,mappings
```

Đây là **các fragment tùy chọn**, **không thuộc POM/cấu hình demo đang chạy**. Không bật `mappings` public ở production nếu thông tin route/servlet/filter là nhạy cảm. Với management port riêng, URL có thể thay đổi, không giả định nó nằm dưới cùng `/app`.

### 12.3. Filter order ảnh hưởng kết quả

Nếu có Spring Security, CORS Filter, custom logging, tracing, request body wrappers hoặc URL rewrite filters, request có thể bị intercept **trước** MVC/Jersey/servlet. Khi startup, có thể bật log web group trong môi trường dev:

```properties
logging.level.web=debug
```

Tài liệu Boot 3.5 cho biết logging có thể hiển thị registered filter order và URL patterns. Đừng bật debug đầy đủ ở production rồi ghi secrets. Với filter cần order rõ, dùng `FilterRegistrationBean#setOrder(...)` hoặc implement `Ordered`/`@Order` theo đúng loại registration.

## 13. Lỗi thường gặp: triệu chứng, nguyên nhân và hướng sửa

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm chứng/sửa |
| --- | --- | --- |
| MVC `@GetMapping` trả 404 khi thêm Jersey | Jersey servlet `/*` chiếm request | `@ApplicationPath("/jaxrs")`, test body MVC |
| Jersey resource trả 404 trong executable JAR | Dùng `packages(...)` scanner không tìm class | `ResourceConfig.register(Resource.class)` tường minh |
| MVC và Jersey đều trả 200 nhưng nhầm handler | Path ownership không tách rõ/fallback | Kiểm tra exact body, filter/servlet mappings |
| Boot chọn MVC khi thêm WebFlux starter | MVC ưu tiên khi cả hai starters | Đây là mặc định; chọn runtime rõ, không đoán |
| WebFlux config không có tác dụng | Runtime đang Servlet MVC | Xem web application type/logs, dùng `WebMvcConfigurer` |
| Servlet/JAX-RS compilation error `javax.*` | Trộn Java EE cũ với Jakarta APIs | Nâng thư viện tương thích Boot 3.5, dùng `jakarta.*` |
| `NoSuchMethodError` sau nâng một library | Dependency version lệch BOM | Xem dependency tree/effective POM, bỏ override |
| `ClassNotFoundException` Jersey provider | Missing transitive dependency hoặc mismatch | Xem Jersey modules/package versions |
| Tomcat và Jetty cùng trong tree | Starter exclusions chưa đúng | Xác định one embedded server, sửa dependency |
| 404 chỉ khi thêm `server.servlet.context-path` | Quên context prefix ở URL/client | Dùng đúng `/app/...` |
| 404 khi đổi `spring.mvc.servlet.path` | URL/matching strategy chưa phù hợp | Kiểm tra PathPatternParser vs Ant matcher |
| 404 chỉ qua Nginx/Ingress | Proxy rewrite `/app` hoặc slash `proxy_pass` | So backend/public URI và proxy logs |
| POST 403 dù GET 200 | Spring Security/CSRF/filter | Kiểm tra security chain, token, Filter order |
| `OPTIONS` preflight fail | CORS không xử lý trước auth hoặc proxy chặn | Test Origin/Access-Control-Request-* |
| JSON response sai Content-Type | MVC converters vs Jersey providers khác | Kiểm tra `@Produces`/`produces` và media negotiation |
| Static assets 404 sau thêm Jersey | Jersey mapping/filter chiếm resource paths | Namespace riêng, test `/assets/**` |
| `/actuator/health` khác cổng | Management server riêng | Kiểm tra management port/base-path |
| Test MVC pass, app deployed fail | MockMvc không test container/Jersey/proxy | Thêm RANDOM_PORT/integration/deploy smoke |
| JAR chạy khác IDE | Classpath/resources/scanning khác | Test executable JAR, `jar tf`, explicit registration |
| Security bảo vệ MVC nhưng Jersey public | Security matchers chỉ xét MVC path | Tạo coverage theo Servlet URL namespaces |
| Endpoint trùng v1/v2 | Version mapping không rõ | Phân biệt path/header và tests |
| Handler `@GetMapping` khai báo nhưng chưa thấy | Component scan thiếu package | Kiểm tra `@SpringBootApplication` base package |
| 200 HTML thay vì API JSON | SPA fallback hoặc proxy fallback | Kiểm tra Content-Type/owner body |
| Thay Boot major làm mất Undertow/starter | Khác danh sách supported servers | Đọc docs **đúng major** trước nâng |
| API GET mới lỗi 415/406 | `consumes`/`produces`/Accept sai | Kiểm tra media types |
| Boot start fail vì ambiguous mappings | Hai MVC mappings có điều kiện giống | Sửa path/method/params/headers mapping |

## 14. Quy trình kiểm tra theo thứ tự, không đoán lỗi

Khi cần thêm một nền tảng web vào Boot app đang chạy, dùng chuỗi kiểm tra:

1. **Xác định Spring Boot version thật** từ parent/BOM hoặc Gradle plugin.
2. Chạy `java -version` và kiểm tra baseline Java; Boot 3.5 cần Java 17+.
3. Chạy `mvn dependency:tree` hoặc Gradle `runtimeClasspath`, xác nhận Spring MVC, WebFlux, Jersey và embedded server nào có mặt.
4. Tìm dependency overrides thủ công, `javax.*` cũ, duplicated Jackson/Jersey providers, server starter trùng.
5. Xác định **web application type** đang được Boot chọn: MVC hoặc reactive; đừng suy ra từ tên controller.
6. Lập bảng URL: public prefix → context path → Servlet mapping → framework handler path.
7. Chỉ định namespace riêng như `/mvc/**`, `/jaxrs/**`, `/legacy/**`, `/assets/**`.
8. Với Jersey, kiểm tra `@ApplicationPath` và explicit `ResourceConfig.register(...)`.
9. Với custom Servlet/Filter, xem `ServletRegistrationBean`, `FilterRegistrationBean` và URL patterns/order.
10. Bật app và thử **mỗi namespace** bằng `curl -i`; xác nhận body/status/Content-Type, không chỉ 200.
11. Chạy HTTP integration tests với random port, kiểm tra negative URLs và method.
12. So sánh direct backend và ingress/public proxy nếu có khác biệt.
13. Xác nhận security/CORS/CSRF trên các vùng Jersey/legacy, không chỉ MVC.
14. Test package bằng executable JAR, không chỉ trong IDE.
15. Nâng Spring Boot patch/BOM có kiểm soát, chạy lại tests và kiểm tra công cụ SCA/CVE.
16. Ghi ownership map và phụ thuộc version vào tài liệu release/architecture.

### Một ma trận kiểm chứng trước và sau nâng version

| Trường kiểm tra | Trước nâng | Sau nâng |
| --- | --- | --- |
| Boot/Framework/Jersey/Tomcat versions | Ghi runtime dependencies | Không có library lệch major |
| Chọn web application type | MVC/Reactive đã xác nhận | Không đổi ngoài chủ đích |
| Servlet mappings | `/`, `/jaxrs/*`, `/legacy/*` | Không shadow nhau |
| Context path | `/app` | Cùng contract public |
| MVC GET route | `/app/mvc/hello` → MVC | Vẫn MVC |
| Jersey GET route | `/app/jaxrs/hello` → Jersey | Vẫn Jersey |
| Custom servlet | `/app/legacy/health` → Servlet | Vẫn Servlet |
| Status 404/405/406/415 | Có tests | Không mất semantics |
| Security filters/CORS/CSRF | Có coverage | Không lộ namespace mới |
| Front proxy/rewrite | Public URL ổn định | Không mất prefix |
| Executable JAR packaging | Route hoạt động | Không mất Jersey resources |
| Response codec/content type | Theo hợp đồng | Không thay ngẫu nhiên |

## 15. Bài tập thực hành

### Bài 1: thêm WebClient nhưng giữ MVC

Một MVC app dùng `spring-boot-starter-web` cần gọi đối tác bằng `WebClient`. Thêm `spring-boot-starter-webflux` và thấy context vẫn Servlet MVC.

**Giải thích:** đây là hành vi mặc định của Boot 3.5. `WebClient` là HTTP client reactive, không đồng nghĩa inbound routing phải chuyển sang WebFlux. Nếu chỉ cần client, giữ MVC là hợp lý.

### Bài 2: Jersey chiếm route API

MVC có `GET /api/books`, sau khi thêm Jersey thì trả 404. Jersey `ResourceConfig` không có `@ApplicationPath`.

**Hướng giải:** kiểm tra Jersey servlet registration có `/*`; giới hạn mapping thành `/jaxrs/*` qua `@ApplicationPath("/jaxrs")`; chạy lại MVC/Jersey smoke tests. Không thêm random controllers chỉ để cứu 404.

### Bài 3: dùng context path nhưng quên URL

Cấu hình `server.servlet.context-path=/shop`. Controller `@GetMapping("/orders")` chỉ còn nhận URL `/shop/orders`.

**Giải thích:** context prefix nằm trước framework handler path; đây không phải lỗi Java annotation.

### Bài 4: lỗi thư viện khi chuyển Boot 2 sang Boot 3

Một Filter sử dụng `javax.servlet.Filter` và Jersey 2.x.

**Hướng giải:** chuyển toàn bộ integration sang Jakarta-compatible versions, dùng `jakarta.servlet.Filter` và Jersey 3.x tương thích, kiểm tra Maven dependency tree/BOM. Không sửa bằng cách thêm cả javax và jakarta APIs rồi hy vọng framework tự bridge.

### Bài 5: MVC path prefix làm mapping lỗi

Config `spring.mvc.servlet.path=/api` trong Boot 3.5, một số endpoints không match như trước.

**Hướng giải:** kiểm tra `PathPatternParser`/`spring.mvc.pathmatch.matching-strategy`. Nếu cần prefix servlet, cấu hình strategy được tài liệu Boot 3.5 hỗ trợ và thêm tests; nếu chỉ cần group routes, dùng `@RequestMapping("/api")` để tránh thay DispatcherServlet path.

### Bài 6: proxy làm mất prefix

Nginx có `location /app/` và `proxy_pass http://backend/;` trong khi Boot context path `/app`.

**Hướng giải:** `/app/` bị thay bằng `/` khi forward; backend nhận `/mvc/hello` và có thể 404. Sửa proxy rewrite hoặc backend context theo hợp đồng, không mở CORS wildcard.

### Bài 7: test controller không phát hiện Jersey mapping

Unit test MockMvc tất cả pass, nhưng sau deploy Jersey không đăng ký JAX-RS resource trong executable JAR.

**Hướng giải:** thêm `@SpringBootTest(RANDOM_PORT)` gọi Jersey endpoint và kiểm tra `ResourceConfig.register(Resource.class)` explicit. `MockMvc` không kiểm tra toàn bộ Servlet container.

### Bài 8: security filter chưa bảo vệ servlet legacy

Ứng dụng chặn `/mvc/admin` nhưng `/legacy/admin` vẫn có thể gọi không auth.

**Hướng giải:** xem Servlet security filter chain/request matchers cho toàn bộ namespace, thêm negative HTTP tests. `MvcRequestMatcher` không thay thế policy cho mọi Servlet.

### Bài 9: API versions đụng nhau

Hai MVC controllers cùng `@GetMapping("/products")` nhưng developer nghĩ tên class `ProductsV1Controller`/`ProductsV2Controller` tự phân biệt version.

**Hướng giải:** đặt `/v1/products`, `/v2/products` hoặc điều kiện version header được hỗ trợ; viết contract tests. Tên class không ảnh hưởng HTTP mapping.

### Bài 10: đổi server starter gây xung đột

Developer thêm Jetty starter mà không exclude Tomcat từ `spring-boot-starter-web`.

**Hướng giải:** dùng starter exclude/replace đúng cách, kiểm tra runtime dependency tree và embedded server thực chạy; không để selection phụ thuộc classpath order khó dự đoán.

## 16. Câu hỏi tự đánh giá

1. **MVC + WebFlux starters có mặc định tạo hai inbound HTTP dispatchers không?** Không. Boot 3.5 ưu tiên MVC, WebClient vẫn dùng được.
2. **Jersey JAX-RS dùng annotation nào cho URL resource?** `@Path` trong `jakarta.ws.rs`, không phải MVC `@RequestMapping`.
3. **Tại sao Jersey cần `@ApplicationPath` khi cùng MVC?** Để tránh Jersey servlet mapping rộng `/*` chiếm requests.
4. **ServletRegistrationBean dùng để làm gì?** Đăng ký custom Servlet với URL patterns/name/init params rõ.
5. **`server.servlet.context-path` và `spring.mvc.servlet.path` có giống nhau không?** Không. Context path áp cho Servlet application, MVC servlet path chỉ DispatcherServlet.
6. **Spring MVC `@GetMapping("/hello")` có biết đường dẫn public ingress không?** Không; proxy có thể rewrite prefix.
7. **Vì sao nên dùng Spring Boot BOM?** Nó quản lý bộ versions đã được kiểm thử nhất quán.
8. **Spring Boot 3.5 dùng namespace Servlet nào?** `jakarta.servlet.*`, không phải `javax.servlet.*` đời cũ.
9. **Jersey 3.x dùng REST namespace nào?** `jakarta.ws.rs.*`.
10. **Maven compile pass đã đủ chứng minh routing đúng không?** Chưa; cần HTTP integration tests và packaged JAR smoke test.
11. **Vì sao MockMvc không thay HTTP integration test Jersey?** MockMvc chủ yếu kiểm tra Spring MVC DispatcherServlet, không container servlet dispatch.
12. **Một `404` luôn do MVC controller thiếu?** Không; Jersey, proxy, static handler, filter và servlet đều có thể tạo 404.
13. **Khi thêm servlet custom mapping `/*` có rủi ro gì?** Nó có thể nhận requests định dành cho MVC/Jersey.
14. **`spring.mvc.static-path-pattern` có đổi Jersey mapping không?** Không, nó thuộc MVC static resource handler.
15. **Khi đổi `spring.mvc.servlet.path` Boot 3.5 cần xem gì?** Tương thích `PathPatternParser`/`AntPathMatcher` và tests.
16. **Nâng Spring Boot library version có tự nâng API URL v1 lên v2 không?** Không; đó là contract riêng.
17. **Actuator mappings có liệt kê toàn bộ ingress routes không?** Không; proxy ở ngoài Spring Boot.
18. **Tại sao cần test wrong URL negative?** Để tránh SPA/Servlet fallback 200 che một route sai.
19. **Spring Security filter có thể chặn trước MVC và Jersey không?** Có, nếu filter mapping/chain match đúng.
20. **Tiêu chí QA cuối cùng là gì?** Đúng dependency versions, đúng web runtime, đúng Servlet owner, đúng URL/proxy và đúng contract/security qua tests thực.

## 17. Checklist chuẩn bị production

- [ ] Ghi chính xác Boot/JDK/Framework/server/Jersey versions và dependency tree.
- [ ] Theo Boot BOM; không override transitive Spring/Jakarta dependencies vô cớ.
- [ ] Không trộn `javax.*` cũ với Jakarta-native Servlet/JAX-RS integration.
- [ ] Chọn một web runtime inbound chính, MVC hoặc WebFlux, có lý do.
- [ ] Xác định loại HTTP client vs server, không thêm server stack do nhầm WebClient.
- [ ] Cấp namespace URL riêng cho MVC/Jersey/custom Servlet/static/management.
- [ ] Giới hạn Jersey bằng `@ApplicationPath`; register resource classes tường minh.
- [ ] Đăng ký Servlet/Filter với pattern/order được review.
- [ ] Phân biệt context path, servlet path, framework mapping và proxy rewrite.
- [ ] Kiểm tra hạn chế `spring.mvc.servlet.path` và matching strategy đúng Boot version.
- [ ] Test 200 với **body owner cụ thể**, negative 404/405, Content-Type và phương thức.
- [ ] Có HTTP integration tests và smoke tests executable JAR.
- [ ] Có test về CORS, authentication, authorization và CSRF cho tất cả namespaces.
- [ ] Kiểm tra static assets/WebJars/SPA fallback không chiếm API path.
- [ ] Kiểm tra Actuator management path/port và không expose mappings nhạy cảm.
- [ ] Kiểm thử direct backend và reverse proxy/ingress để xác nhận path rewrite.
- [ ] Nâng Boot/Jersey/Servlet container patch đồng bộ, xem CVE và release notes.
- [ ] Có owner rõ cho dependencies, URL routing và API version contract.
- [ ] Có rollback plan và regression tests khi thêm một platform/plugin/starter.

## 18. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): Spring MVC, Jersey, `@ApplicationPath`, Servlet/filter registrations, static resources, routing.
- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): WebFlux và hành vi chọn MVC khi cả MVC + WebFlux hiện diện.
- [Spring Boot 3.5 — Spring MVC How-to](https://docs.spring.io/spring-boot/3.5/how-to/spring-mvc.html): `spring.mvc.servlet.path`, DispatcherServlet configuration.
- [Spring Boot 3.5 — Build Systems](https://docs.spring.io/spring-boot/3.5/reference/using/build-systems.html): starter parent, Maven/Gradle, curated dependency versions/BOM.
- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): Tomcat/Jetty/Undertow/Reactor Netty và version/platform requirements.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): test web application type, RANDOM_PORT, TestRestTemplate.
- [Spring Framework 6.2 — Spring Web MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc.html): DispatcherServlet và HandlerMappings.
- [Spring Framework — Request Mapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): URL/method/params/headers/consumes/produces mapping.
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/): servlet URL matching và filter pipeline.
- [Jakarta RESTful Web Services (JAX-RS)](https://jakarta.ee/specifications/restful-ws/): `@Path`, `@GET` và `@ApplicationPath`.
- [Apache Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): dependency tree.
- [Nginx ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html): `proxy_pass` URI replacement và upstream routing.

**Kết luận:** Khi mở rộng Spring Boot bằng nhiều nền tảng web, hãy tách **phụ thuộc đúng BOM/Jakarta generation**, **runtime inbound chủ đạo**, **Servlet/handler URL ownership** và **API version contract**. Một ứng dụng có thể chứa Spring MVC, Jersey và Servlet tùy chỉnh mà không va chạm nếu mỗi thành phần có namespace cụ thể, dependencies phù hợp và HTTP integration tests được chạy **trên server thật**. Không đánh đổi tính đúng đắn của routing/security bằng cách gắn wildcard `/*` hoặc bỏ qua version conflicts.