# DelegatingFilterProxy: cầu nối giữa Servlet Container và Spring bean

> **Phạm vi:** Spring Security trên Servlet stack (`jakarta.servlet`, Spring MVC, Spring Framework 6 / Spring Security 6 / Spring Boot 3.x). Trọng tâm là cơ chế **DelegatingFilterProxy** kết nối Servlet container với một đối tượng `Filter` do Spring quản lý, đặc biệt là bean `springSecurityFilterChain`. Đây là kiến thức về **kiến trúc bộ lọc**, không phải cơ chế `WebFilter` của Spring WebFlux.

## 1. Vì sao cần một lớp cầu nối?

Trong ứng dụng Servlet, Tomcat/Jetty/Undertow gọi các `jakarta.servlet.Filter` đã **đăng ký với Servlet container**. Container biết URL mapping, dispatcher types, thứ tự filter và vòng đời filter theo Servlet API.

Ngược lại, Spring ApplicationContext quản lý **Spring bean**: tạo đối tượng, tiêm dependency, cấu hình bằng `@Bean` và quản lý vòng đời. Spring Security cần các filter sử dụng bean và cấu hình Spring như `AuthenticationManager`, `SecurityContextRepository` hoặc các luật authorization.

Nếu đăng ký trực tiếp từng security filter cho container, ta phải để container quyết định thứ tự, mapping và lifecycle của nhiều filter; điều này không phản ánh được cơ chế lựa chọn các `SecurityFilterChain` của Spring Security. `DelegatingFilterProxy` giải quyết điểm giao nhau:

- Với container, nó **chính là một `jakarta.servlet.Filter`** được đăng ký dưới một tên và URL/dispatcher mapping cụ thể.
- Với Spring, nó tìm một **bean cũng triển khai `Filter`** theo tên rồi chuyển tiếp lời gọi `doFilter(request, response, chain)` tới bean đó.
- Với Spring Security, bean đích thông thường có tên **`springSecurityFilterChain`** và kiểu là `FilterChainProxy`. Đối tượng này mới chọn `SecurityFilterChain` và thực thi các filter bảo mật thực sự.

**Từ khóa phân biệt:** `DelegatingFilterProxy` là **cầu nối/delegate**, còn `FilterChainProxy` là **bộ điều phối các security filter chains**. Hai tên đều có “Proxy” nhưng vai trò khác nhau.

## 2. Sơ đồ request: container filter và Spring Security filter chain

```text
HTTP request
    |
    v
Servlet container
    |
    +--> [Container Filter trước security, nếu có]
    |
    +--> DelegatingFilterProxy  (được đăng ký với container)
    |       targetBeanName = "springSecurityFilterChain"
    |             |
    |             v   tra cứu Spring WebApplicationContext
    |       Spring bean: FilterChainProxy
    |             |
    |             +--> chọn SecurityFilterChain đầu tiên match request
    |             |       |
    |             |       +--> Security Filter 1
    |             |       +--> Security Filter 2
    |             |       +--> ... authorization / exception handling
    |             |
    |             +--> gọi tiếp original FilterChain nếu được phép
    |
    +--> [Container Filter sau security, nếu có]
    |
    +--> DispatcherServlet (Spring MVC) / Servlet đích
                 |
                 +--> HandlerMapping -> HandlerInterceptor -> Controller
    |
    v
HTTP response (các filter hoàn tất theo đường quay về)
```

Sơ đồ cho thấy **quan hệ lồng nhau**, không khẳng định mọi container filter có cùng vị trí. Một container filter sau proxy chỉ được gọi nếu proxy và các security filter cho request đi tiếp; một security filter có thể kết thúc sớm bằng 401/403 hoặc redirect. Spring MVC interceptor chỉ nằm bên trong luồng `DispatcherServlet`, không chạy trước security chain.

### Bốn đối tượng thường bị nhầm

| Tên | Ở đâu? | Chịu trách nhiệm gì? |
| --- | --- | --- |
| Servlet container `FilterChain` | Container | Nối các servlet filter đã đăng ký và servlet đích |
| `DelegatingFilterProxy` | Một servlet filter trong container | Chuyển `doFilter` sang Spring bean có tên chỉ định |
| `FilterChainProxy` | Spring bean, target của proxy trong Security | Chọn chain phù hợp, thực thi ordered security filters |
| `SecurityFilterChain` | Spring Security | Chứa request matcher và danh sách các security filter cho một nhóm request |

`SecurityFilterChain` **không** phải đối tượng được container trực tiếp gọi cho mỗi request. Nó là cấu trúc được `FilterChainProxy` dùng sau khi `DelegatingFilterProxy` đã chuyển quyền điều khiển.

## 3. DelegatingFilterProxy hoạt động thế nào?

### 3.1. Đăng ký filter ở container, tìm bean theo tên

Khi được container gọi, `DelegatingFilterProxy` có tên bean đích được cấu hình, chẳng hạn:

```text
Servlet filter registration:
    name       = "springSecurityFilterChain"
    filter     = DelegatingFilterProxy
    URL mapping = /*
            |
            v
Spring WebApplicationContext:
    bean name  = "springSecurityFilterChain"
    bean type  = FilterChainProxy implements jakarta.servlet.Filter
```

Trong phương thức `doFilter`, proxy lấy target filter từ Spring context (nếu chưa resolve/cached), rồi gọi `target.doFilter(request, response, chain)`. Việc resolve có thể xảy ra khi khởi tạo proxy nếu context sẵn sàng hoặc muộn hơn khi request tới; không nên giả định luôn phải tra cứu bean mới trên từng request.

Minh họa **ý tưởng**, không phải mã nguồn nội bộ của Spring:

```java
// Pseudocode minh họa; không phải lớp độc lập để biên dịch.
Filter delegate = springContext.getBean("springSecurityFilterChain", Filter.class);
delegate.doFilter(request, response, servletContainerFilterChain);
```

Lời gọi nhận nguyên `ServletRequest`, `ServletResponse` và **`FilterChain` của container**. Nhờ vậy, khi target cuối cùng gọi `chain.doFilter`, luồng quay về các container filter tiếp theo rồi tới servlet đích.

### 3.2. Điều gì xảy ra nếu target bean không tồn tại?

Tên target là **hợp đồng cấu hình**. Nếu proxy đăng ký target `springSecurityFilterChain` nhưng ứng dụng không tạo bean đó hoặc proxy không tìm được đúng Spring `WebApplicationContext`, request không thể được ủy quyền bình thường và ứng dụng có thể báo lỗi khi khởi tạo filter hoặc lúc xử lý request. Không được âm thầm coi proxy là filter “pass through” cho tình huống này.

Cần kiểm tra tên bean, loại bean có triển khai `Filter`, context chứa bean, thời điểm khởi tạo và cấu hình đăng ký servlet filter. `DelegatingFilterProxy` có thể được tạo bằng constructor cung cấp target bean name và `WebApplicationContext` rõ ràng khi viết cấu hình thủ công.

### 3.3. Hai hệ thống lifecycle

- **Servlet container** gọi `init(FilterConfig)` và `destroy()` trên `DelegatingFilterProxy` được đăng ký.
- **Spring ApplicationContext** thường quản lý lifecycle của **target bean** (tạo/khởi tạo/hủy bean). Đây là hành vi mặc định khi không bật `targetFilterLifecycle`.
- `setTargetFilterLifecycle(true)` yêu cầu proxy ủy quyền `init`/`destroy` của Servlet Filter tới target theo vòng đời container. Chỉ nên dùng khi thật sự hiểu nhu cầu lifecycle; đối với filter bean quản lý bởi Spring, mặc định phù hợp hơn.

Không tự gọi `init`/`destroy` trên bean bảo mật; không tự đăng ký `FilterChainProxy` lần nữa ở container chỉ vì nó triển khai `Filter`.

## 4. Từ DelegatingFilterProxy đến springSecurityFilterChain

Trong một ứng dụng Spring Boot Servlet dùng `spring-boot-starter-security`:

1. Spring Security tạo bean filter đích tên **`springSecurityFilterChain`** (thường là một `FilterChainProxy`).
2. Spring Boot cấu hình đăng ký **`DelegatingFilterProxy`** với Servlet container (qua `DelegatingFilterProxyRegistrationBean` trong cơ chế auto-configuration thích hợp) để trỏ tới tên bean đó.
3. Container gọi proxy khi request phù hợp URL/dispatcher mapping.
4. `FilterChainProxy` chọn **`SecurityFilterChain` đầu tiên khớp request** theo thứ tự các chain, rồi chạy các security filter đã cấu hình.
5. Khi request hợp lệ và các filter gọi tiếp chain, xử lý đi tới servlet/MVC; khi bị chặn, controller có thể không chạy.

**Spring Boot tự động đăng ký proxy** trong cấu hình Servlet Security thông thường. Không cần viết thêm một `DelegatingFilterProxy` riêng cho `springSecurityFilterChain` chỉ để “bật security”; đăng ký trùng có thể dẫn tới hành vi không mong muốn.

Trong ứng dụng không dùng Boot, proxy có thể được đăng ký bằng `web.xml`, `ServletContext#addFilter` hoặc cơ chế khởi tạo Servlet tương ứng; ứng dụng vẫn phải cung cấp đúng Spring context và target bean.

### Nhiều SecurityFilterChain khác với nhiều container filter

Ví dụ cấu hình hai khu vực API và web, minh họa bằng một đoạn Java **độc lập về cú pháp nhưng cần đặt trong lớp `@Configuration` của ứng dụng có Spring Security**:

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

Cần import `@Bean`, `@Order`, `HttpSecurity`, `SecurityFilterChain`, `Customizer` và có beans xác thực phù hợp. Đây là đoạn giải thích về **chain selection**, không phải một chương trình Java tự chạy độc lập.

Request `/api/items` match chain API trước; `/public` đi qua chain web. Cả hai vẫn có thể đi qua **cùng một container `DelegatingFilterProxy`**. `securityMatcher` chọn *chain*, trong khi `requestMatchers` bên trong `authorizeHttpRequests` đặt *luật authorization trong chain đã chọn*. Nếu không chain nào match, `FilterChainProxy` không áp dụng filter bảo mật của chain cho request đó; vì vậy phải thiết kế fallback matcher an toàn cho ứng dụng thực tế.

## 5. Ví dụ Spring Boot chạy được: nhìn thấy ranh giới ủy quyền

Ví dụ dùng Java 17+, Spring Boot 3.3.x và Spring Security 6.x. Ta quan sát ba lớp: (1) một container filter thực sự; (2) một filter ở **bên trong** Spring Security chain; (3) controller. Sau đó ta đăng ký thêm **một DelegatingFilterProxy riêng cho một Spring bean bình thường** để thấy rõ cơ chế bridge, không phụ thuộc vào chi tiết nội bộ của Spring Security.

### 5.1. Tạo dự án

```text
delegating-filter-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    ContainerTraceFilter.java
    SecurityTraceFilter.java
    SecurityConfig.java
    BridgeConfig.java
    DemoController.java
```

`settings.gradle`:

```groovy
rootProject.name = 'delegating-filter-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0'

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
}
```

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

### 5.2. Filter thứ nhất: container filter

`src/main/java/demo/ContainerTraceFilter.java`:

```java
package demo;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ContainerTraceFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws IOException, ServletException {
        System.out.println("CONTAINER before " + request.getRequestURI());
        try {
            chain.doFilter(request, response);
        } finally {
            System.out.println("CONTAINER after status=" + response.getStatus());
        }
    }
}
```

`@Component` giúp Boot tự đăng ký filter này với container. `@Order` đặt nó ở đầu container filter chain trong ví dụ. Nó **không** được gắn vào danh sách security filters của `HttpSecurity`.

### 5.3. Filter thứ hai: nằm bên trong Spring Security

`src/main/java/demo/SecurityTraceFilter.java`:

```java
package demo;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

public class SecurityTraceFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws IOException, ServletException {
        System.out.println("SECURITY in-chain "
                + request.getMethod() + " " + request.getRequestURI());
        chain.doFilter(request, response);
    }
}
```

Lớp này **không có `@Component` và không có `@Bean` filter riêng**: ta khởi tạo nó duy nhất khi cấu hình `HttpSecurity`. Đây là cách đơn giản để tránh Boot tự động đăng ký cùng filter ở container thêm một lần.

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/bridge/ping").permitAll()
                .anyRequest().authenticated());
        http.httpBasic(Customizer.withDefaults());
        http.addFilterBefore(new SecurityTraceFilter(), AuthorizationFilter.class);
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails user = User.withUsername("learner")
                .password("{noop}study123")
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(user);
    }
}
```

`http.addFilterBefore` chỉ định vị trí **trong chain Spring Security**, không tạo container filter. `{noop}` là cú pháp password encoder không mã hóa để thử nghiệm cục bộ; hệ thống thực tế phải dùng password hashing phù hợp, ví dụ BCrypt, và quản lý bí mật an toàn.

### 5.4. Thêm một DelegatingFilterProxy tự khai báo để quan sát bridge

Ngoài proxy mặc định của Spring Security, ví dụ tạo một Spring bean `Filter` tên `bridgeTarget` và đăng ký **một proxy có URL mapping riêng** `/bridge/*`. Đây là proxy độc lập, phục vụ học cơ chế ủy quyền, không phải proxy thay thế `springSecurityFilterChain`.

`src/main/java/demo/BridgeConfig.java`:

```java
package demo;

import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.Ordered;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.web.filter.DelegatingFilterProxy;

@Configuration
public class BridgeConfig {
    @Bean("bridgeTarget")
    Filter bridgeTarget() {
        return (request, response, chain) -> {
            String uri = ((HttpServletRequest) request).getRequestURI();
            System.out.println("BRIDGE TARGET before " + uri);
            try {
                chain.doFilter(request, response);
            } finally {
                System.out.println("BRIDGE TARGET after " + uri);
            }
        };
    }

    @Bean
    FilterRegistrationBean<Filter> disableDirectRegistration(
            @Qualifier("bridgeTarget") Filter target) {
        FilterRegistrationBean<Filter> registration =
                new FilterRegistrationBean<>(target);
        registration.setEnabled(false);
        return registration;
    }

    @Bean
    FilterRegistrationBean<DelegatingFilterProxy> bridgeProxyRegistration(
            WebApplicationContext context) {
        DelegatingFilterProxy proxy =
                new DelegatingFilterProxy("bridgeTarget", context);
        FilterRegistrationBean<DelegatingFilterProxy> registration =
                new FilterRegistrationBean<>(proxy);
        registration.addUrlPatterns("/bridge/*");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return registration;
    }
}
```

Có **hai điểm không được lược bỏ** khi sử dụng mẫu này:

1. `bridgeTarget` là Spring bean kiểu `Filter`. Spring Boot thường sẽ **tự đăng ký bean Filter như servlet filter** nếu không có cấu hình khác. Bean `disableDirectRegistration` dùng `setEnabled(false)` để ngăn việc target chạy trực tiếp bên cạnh proxy.
2. `bridgeProxyRegistration` đăng ký **`DelegatingFilterProxy`**, chỉ match `/bridge/*` và tìm target tên `bridgeTarget` trong `WebApplicationContext`. Nếu đổi tên bean mà không đổi chuỗi target, bridge sẽ lỗi. Đặt order ở container khác với `addFilterBefore` của Spring Security.

Trong chương trình này, container filter logging chạy trước, manual bridge cho `/bridge/*` chạy kế tiếp, và Spring Security proxy chạy sau đó theo registration order của Boot.

### 5.5. Controller và lệnh thử

`src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/public")
    public String open() {
        System.out.println("CONTROLLER /public");
        return "PUBLIC";
    }

    @GetMapping("/private")
    public String privatePage() {
        System.out.println("CONTROLLER /private");
        return "PRIVATE";
    }

    @GetMapping("/bridge/ping")
    public String bridgePing() {
        System.out.println("CONTROLLER /bridge/ping");
        return "PONG";
    }
}
```

Cài JDK 17+ và Gradle tương thích Spring Boot 3.3 (ví dụ Gradle 8.5), sau đó từ thư mục `delegating-filter-demo` chạy:

```bash
gradle bootRun
```

Nếu dự án được tạo thêm Gradle wrapper, có thể chạy `./gradlew bootRun` trên macOS/Linux hoặc `.\gradlew.bat bootRun` trên Windows.

Mở terminal khác gửi lần lượt từng request (để log dễ đọc):

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u learner:study123 http://localhost:8080/private
curl -i http://localhost:8080/bridge/ping
```

**Quan sát 1 — `GET /public`:** HTTP 200, body `PUBLIC`. Các dòng do `System.out.println` của ứng dụng tạo ra theo thứ tự:

```text
CONTAINER before /public
SECURITY in-chain GET /public
CONTROLLER /public
CONTAINER after status=200
```

**Quan sát 2 — `GET /private` không credentials:** HTTP 401 với cấu hình HTTP Basic. Controller không chạy:

```text
CONTAINER before /private
SECURITY in-chain GET /private
CONTAINER after status=401
```

**Quan sát 3 — `GET /private` với HTTP Basic hợp lệ:** HTTP 200, body `PRIVATE`:

```text
CONTAINER before /private
SECURITY in-chain GET /private
CONTROLLER /private
CONTAINER after status=200
```

**Quan sát 4 — `GET /bridge/ping`:** HTTP 200, body `PONG`. Request đi vào manual proxy, target bean, rồi security và controller:

```text
CONTAINER before /bridge/ping
BRIDGE TARGET before /bridge/ping
SECURITY in-chain GET /bridge/ping
CONTROLLER /bridge/ping
BRIDGE TARGET after /bridge/ping
CONTAINER after status=200
```

Các ví dụ log trên thể hiện thứ tự dòng `System.out.println` của **một request đồng bộ riêng lẻ** với cấu hình vừa nêu; startup log, log của framework và request đồng thời có thể xen kẽ. Trường hợp Basic credentials **không hợp lệ** có thể bị từ chối bởi filter xác thực nằm **trước** vị trí `SecurityTraceFilter`, vì vậy không nên suy ra custom trace sẽ thấy mọi cách thất bại authentication.

Đọc lại luồng `/bridge/ping`: container gọi `DelegatingFilterProxy("bridgeTarget")` → proxy gọi Spring bean `bridgeTarget` → bean gọi `chain.doFilter` → request đi qua container registration của security proxy → `FilterChainProxy` và security filter nội bộ → `DispatcherServlet`/controller → quay trở lại qua các lớp đã gọi. Đây là bằng chứng trực tiếp về sự khác biệt giữa **đăng ký filter** và **triển khai logic bên trong Spring bean**.

## 6. Đăng ký, thứ tự và lifecycle cần đặt đúng tầng

| Muốn thay đổi | API/cấu hình phù hợp | Lưu ý |
| --- | --- | --- |
| URL pattern và dispatcher types của một container filter/proxy | Servlet registration hoặc `FilterRegistrationBean` | Container quyết định request nào đi qua proxy |
| Thứ tự của proxy so với các container filters | `FilterRegistrationBean#setOrder`/registration order | Không đồng nghĩa thứ tự security filter nội bộ |
| Bean mà proxy ủy quyền | Target bean name, `WebApplicationContext` | Bean phải triển khai `jakarta.servlet.Filter` |
| Các chain bảo mật cho nhóm URL | Nhiều `SecurityFilterChain` + `securityMatcher`/`@Order` | `FilterChainProxy` chọn chain đầu tiên match |
| Thứ tự **security filters** trong một chain | `HttpSecurity.addFilterBefore/addFilterAfter` | Dùng anchor filter đã biết của Spring Security |
| Authorization trong chain | `authorizeHttpRequests` | `permitAll` vẫn qua security filter chain |
| Vòng đời target bean | Spring bean lifecycle | Mặc định không bật `targetFilterLifecycle` |

**Ba kiểu “order” độc lập:** (1) order container registrations; (2) order chọn `SecurityFilterChain`; (3) order filters bên trong một chain. Chỉnh một kiểu không tự động chỉnh hai kiểu còn lại.

**Ba phạm vi “match” độc lập:** (1) URL/dispatcher mapping của container proxy; (2) request matcher chọn security chain; (3) authorization matcher trong chain đã được chọn. Ví dụ, proxy có URL pattern chỉ `/api/*` thì cấu hình authorization trong Spring không thể bảo vệ một request ngoài mapping đó thông qua proxy ấy.

Với Spring Boot cấu hình mặc định, hạn chế thao tác thủ công lên `springSecurityFilterChain` proxy nếu không có nhu cầu rõ ràng. `HttpSecurity` và `SecurityFilterChain` là nơi cấu hình chính sách bảo mật; Servlet registration chỉ dùng khi muốn thay đổi cách tích hợp ở ranh giới container.

## 7. Lỗi thường gặp và cách chẩn đoán

### 7.1. “Có `SecurityFilterChain` bean rồi, vì sao endpoint vẫn không bị bảo vệ?”

Kiểm tra có đăng ký `DelegatingFilterProxy` để request đi vào `springSecurityFilterChain` hay không; đúng Servlet stack chưa; tên target bean có khớp; URL/dispatcher mapping proxy có bao phủ endpoint; request matcher của security chain có khớp; chain đầu tiên match có luật phù hợp. Chỉ tồn tại `SecurityFilterChain` bean chưa chứng minh container đã chuyển request qua Spring Security.

### 7.2. “Tôi đã thêm filter bằng `http.addFilterBefore`, sao nó chạy hai lần?”

Một nguyên nhân phổ biến là class filter vừa là Spring bean kiểu `Filter` được Boot tự đăng ký vào **container**, vừa được thêm vào **security chain**. Đọc hai danh sách đăng ký và tránh đăng ký trùng. Cách đơn giản trong ví dụ là khởi tạo `new SecurityTraceFilter()` chỉ bên trong `HttpSecurity`. Nếu phải dùng bean `Filter`, cấu hình `FilterRegistrationBean` disabled cho đường container khi cần.

Ngoài ra, request `REQUEST`/`ERROR`/`ASYNC` có thể tạo nhiều lần dispatch; đừng kết luận hai bản đăng ký khi chưa xét dispatcher type.

### 7.3. “Đổi tên filter trong container có tự đổi target bean không?”

Không nên coi hai tên là tự động đồng bộ trong mọi kiểu đăng ký. Khi khởi tạo `new DelegatingFilterProxy("bridgeTarget", context)`, tên target đã chỉ định là `bridgeTarget`; tên bean khác sẽ không được proxy dùng trừ khi cấu hình lại. Một số kiểu constructor/registration có thể dùng filter-name làm tên target mặc định, nên luôn xác minh cách proxy được tạo trong ứng dụng.

### 7.4. “`@Order` trên custom filter có thay đổi thứ tự các security filter không?”

`@Order` thường tác động cách Boot đăng ký **container filter bean**. Filter trong `SecurityFilterChain` được sắp theo cấu hình Spring Security, ví dụ `addFilterBefore`. Muốn đặt filter sau bước authentication thì xác định filter mốc phù hợp trong security chain; không dùng `@Order` như một phép thay thế.

### 7.5. “Dùng `permitAll()` có bỏ qua DelegatingFilterProxy không?”

Không. `permitAll()` là quyết định authorization của một request đi qua chain, **không** phải bỏ qua proxy, không tự bỏ qua authentication/CORS/CSRF hay những security filters khác. Khác biệt với loại bỏ URL khỏi security bằng `web.ignoring()`: khi bị loại khỏi security, request không nhận các xử lý security filter chain theo cách thông thường. Cần ưu tiên `permitAll()` cho tài nguyên public trừ khi có lý do kỹ thuật rõ ràng.

### 7.6. “Có thể dựa vào MVC HandlerInterceptor để bảo vệ thay security proxy?”

Không nên. Interceptor chỉ chạy sau khi `DispatcherServlet` chọn handler MVC; các request bị chặn sớm trong filter, hoặc đi vào servlet khác, không qua cùng luồng interceptor. Bảo vệ HTTP endpoints nên cấu hình bằng Spring Security tại security chain (và method security nếu cần).

### 7.7. “Có cần tự gọi `FilterChainProxy.doFilter`?”

Không. Container gọi `DelegatingFilterProxy`; proxy ủy quyền; `FilterChainProxy` xử lý logic an toàn theo cấu hình và gọi tiếp original chain khi phù hợp. Gọi thủ công có thể bỏ qua ranh giới lifecycle/mapping hoặc chạy security logic trùng.

### 7.8. “Tại sao proxy không resolve được bean?”

Xem chính xác:
- Bean có được đăng ký dưới **đúng targetBeanName** và triển khai `Filter`?
- Proxy đang tìm trong **WebApplicationContext** nào? Ứng dụng có nhiều context cha/con hoặc custom Servlet context?
- Proxy có bị tạo quá sớm so với Spring context hoặc cấu hình target có dependency lỗi?
- Auto configuration Spring Security Servlet có bị loại trừ hay ứng dụng thực ra chạy WebFlux?
- Proxy có URL mapping/dispatcher types phù hợp request cần kiểm tra?

Không “sửa” bằng cách âm thầm bypass security khi target missing.

## 8. Checklist khi thiết kế filter cho ứng dụng thật

1. **Xác định tầng cần đặt logic:** container `Filter` cho xử lý toàn Servlet boundary; security filter cho authentication/authorization-related behavior; MVC `HandlerInterceptor` cho logic gắn với handler.
2. **Xác nhận nguồn đăng ký:** Boot auto-register? `FilterRegistrationBean`? `http.addFilterBefore`? Proxy tự thêm? Tránh một filter có hai owner bất ngờ.
3. **Xác minh ba mức thứ tự và ba mức matcher:** container registration, `SecurityFilterChain` selection, internal filter order/authorization rules.
4. **Gắn request ID vào log** để phân biệt nhiều HTTP requests và các lần dispatch `REQUEST`, `ERROR`, `ASYNC`; tránh suy diễn từ log xen kẽ.
5. **Kiểm tra nhánh bị từ chối:** 401, 403, CSRF denial, preflight CORS, exception, async dispatch; đừng chỉ test `200 OK`.
6. **Giữ an toàn vòng đời:** Spring quản lý target filter bean theo mặc định; chỉ bật `targetFilterLifecycle` khi có nhu cầu được xác minh.

## 9. Câu hỏi tự kiểm tra

1. **Container gọi `DelegatingFilterProxy` hay `SecurityFilterChain` trực tiếp?** Container gọi filter đã đăng ký là `DelegatingFilterProxy`; target bean thường là `FilterChainProxy`, chính nó chọn `SecurityFilterChain`.
2. **Proxy có tự xác thực người dùng không?** Không; nó chỉ chuyển tiếp lời gọi tới target. Các security filter và cấu hình ứng dụng mới thực hiện chính sách bảo mật.
3. **Một ứng dụng có ba `SecurityFilterChain` có bắt buộc ba `DelegatingFilterProxy` không?** Không; một proxy trỏ tới `FilterChainProxy` có thể phục vụ nhiều chain.
4. **Vì sao không tự đăng ký `springSecurityFilterChain` proxy lần nữa trong Spring Boot?** Boot thường đã làm việc này cho Servlet Security; đăng ký trùng có thể khiến xử lý lặp hoặc khó chẩn đoán.
5. **Tại sao cần `setEnabled(false)` cho bean `bridgeTarget` trong ví dụ?** Để Boot không đăng ký target `Filter` trực tiếp với container; request `/bridge/*` phải đi qua proxy mới gọi bean này.
6. **`http.addFilterBefore` và `FilterRegistrationBean#setOrder` có cùng tầng không?** Không; cái đầu sắp filter bên trong Spring Security chain, cái sau sắp servlet filter registrations của container.

**Ghi nhớ:** `DelegatingFilterProxy` là filter **đăng ký ở container** nhưng **ủy quyền cho Spring bean**. Trong Spring Security Servlet, target quan trọng là `springSecurityFilterChain` (một `FilterChainProxy`). Từ đó `FilterChainProxy` chọn `SecurityFilterChain` phù hợp và chạy các security filter; nếu request được đi tiếp, luồng mới tới servlet/MVC. Phân biệt rạch ròi container registration, Spring bean lookup, security chain selection và authorization là chìa khóa để cấu hình và gỡ lỗi chính xác.
