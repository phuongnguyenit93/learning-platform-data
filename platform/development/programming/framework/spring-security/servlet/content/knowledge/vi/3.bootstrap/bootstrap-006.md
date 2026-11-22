# Đăng ký bộ lọc bảo mật trong ứng dụng Servlet không dùng Spring Boot

> **Phạm vi:** Ứng dụng Java Servlet truyền thống chạy trên Servlet container (ví dụ Tomcat) và tự khởi tạo Spring Framework/Spring Security, **không dùng Spring Boot, không dùng Spring Boot auto-configuration**. Nội dung sử dụng Jakarta Servlet API, Spring Framework 6 và Spring Security 6, yêu cầu Java 17+. Trọng tâm là cách đăng ký bộ lọc bảo mật vào Servlet container, nơi tạo bean cần thiết, cách đặt thứ tự và cách xác minh đường đi request.

## 1. Vì sao không có Spring Boot thì phải đăng ký filter?

Trong một ứng dụng Servlet, **Servlet container** là nơi nhận HTTP request, chọn các servlet và gọi những `Filter` có mapping phù hợp. Spring Security cung cấp chuỗi filter để thực hiện các công việc như đọc security context, xác thực, xử lý ngoại lệ và phân quyền trước khi request đến servlet/controller.

Khi dùng Spring Boot Web, cơ chế tích hợp của Boot thường tự đăng ký filter của Spring Security với Servlet container. Trong ứng dụng **không dùng Spring Boot**, bạn phải bảo đảm việc nối **Servlet container → filter proxy → Spring Security** được khai báo rõ ràng bằng một trong các cách: mã khởi tạo dựa trên Servlet 3+ (Java configuration), `AbstractSecurityWebApplicationInitializer`, hoặc `web.xml`.

Ba lớp thường bị nhầm lẫn:

| Thành phần | Ai quản lý? | Nhiệm vụ |
| --- | --- | --- |
| `DelegatingFilterProxy` | Đăng ký như một Servlet `Filter` ở container; delegate thuộc Spring context | Cầu nối giữa filter chain của container và bean filter trong Spring |
| Bean `springSecurityFilterChain` (thường là `FilterChainProxy`) | Spring `ApplicationContext` | Chọn `SecurityFilterChain` khớp request và thực thi các security filter bên trong |
| Bean `SecurityFilterChain` | Spring `ApplicationContext`, được khai báo bằng `@Bean` | Mô tả nhóm filter và các quy tắc bảo vệ HTTP được tạo từ `HttpSecurity` |

**Tên `springSecurityFilterChain` rất quan trọng**: mặc định `DelegatingFilterProxy` tìm bean Spring có đúng tên đó. `@EnableWebSecurity` cùng cấu hình Spring Security tạo hạ tầng bao gồm `FilterChainProxy` mang tên này. Bean `SecurityFilterChain` do bạn khai báo là một thành phần bên trong hạ tầng ấy; tên method `securityFilterChain` không phải tên proxy phải tra cứu.

```text
HTTP request
    |
    v
Servlet container (filter mapping trên /*)
    |
    v
DelegatingFilterProxy [Servlet Filter]
    | tìm bean "springSecurityFilterChain" trong Spring WebApplicationContext
    v
FilterChainProxy [Spring bean]
    | chọn SecurityFilterChain khớp request
    v
Security filters: SecurityContext -> Authentication -> Authorization -> ...
    |
    v
Servlet / Spring MVC DispatcherServlet
    |
    v
HTTP response (hoặc 401/403 nếu security filter từ chối)
```

Nếu chỉ tạo `@Bean SecurityFilterChain` mà **không đăng ký cổng vào từ Servlet container**, request của ứng dụng không được bảo vệ như mong đợi. Ngược lại, nếu đăng ký `DelegatingFilterProxy` nhưng không khởi tạo đúng Spring context/bean `springSecurityFilterChain`, ứng dụng có thể lỗi khi container khởi tạo filter hoặc khi nhận request.

## 2. Chọn một trong ba đường đăng ký

| Cách | Đăng ký tại đâu? | Thích hợp khi |
| --- | --- | --- |
| **A. Tự đăng ký `DelegatingFilterProxy` qua `WebApplicationInitializer`** | `ServletContext#addFilter` | Muốn thấy rõ toàn bộ quá trình và chủ động điều khiển mapping/dispatcher |
| **B. Kế thừa `AbstractSecurityWebApplicationInitializer`** | Spring Security tự đăng ký proxy thông qua Servlet initializer | Dự án dùng Spring Security Java config và muốn ít mã khởi tạo |
| **C. Khai báo `DelegatingFilterProxy` trong `web.xml`** | File `WEB-INF/web.xml` | Ứng dụng WAR truyền thống đang có cấu hình XML |

**Không kích hoạt A, B và C cùng lúc cho cùng filter.** Mỗi cách ở trên là một phương án thay thế để gắn một proxy với container, không phải ba bước cần thực hiện liên tiếp. Tất cả đều cần một Spring `WebApplicationContext` chứa bean tên `springSecurityFilterChain`.

Phần kế tiếp triển khai **A** thành ví dụ chạy được; sau đó trình bày cách đổi sang **B** hoặc **C** mà không tạo trùng filter.

## 3. Ví dụ hoàn chỉnh: WAR Servlet thuần + Spring Security, không dùng Boot

Ví dụ tạo hai endpoint `GET /hello` và `GET /admin`:

- `/hello` cần người dùng đăng nhập hợp lệ.
- `/admin` chỉ cho người có role `ADMIN`.
- Hai tài khoản thử nghiệm: `alice` có role `USER`, `admin` có role `ADMIN`.

Môi trường mẫu: **JDK 17+**, **Maven 3.9+**, **Tomcat 10.1.x** (Jakarta Servlet 6), các bản ví dụ của **Spring Framework 6.1.x** và **Spring Security 6.3.x**. Đây là cặp phiên bản minh họa đã được phát hành; không phải khẳng định bản mới nhất. Có thể dùng phiên bản được quản lý thống nhất ở dự án thực tế nếu tương thích Servlet/JDK.

Cấu trúc dự án:

```text
plain-servlet-security/
├── pom.xml
└── src/main/java/example/security/
    ├── AppInitializer.java
    ├── SecurityConfig.java
    └── GreetingServlet.java
```

### 3.1. `pom.xml`: đóng gói WAR và dùng đúng Jakarta Servlet API

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>plain-servlet-security</artifactId>
    <version>1.0</version>
    <packaging>war</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>6.1.14</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
            <dependency>
                <groupId>org.springframework.security</groupId>
                <artifactId>spring-security-bom</artifactId>
                <version>6.3.4</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-config</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-web</artifactId>
        </dependency>
        <dependency>
            <groupId>jakarta.servlet</groupId>
            <artifactId>jakarta.servlet-api</artifactId>
            <version>6.0.0</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>

    <build>
        <finalName>secure-demo</finalName>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-war-plugin</artifactId>
                <version>3.4.0</version>
                <configuration>
                    <failOnMissingWebXml>false</failOnMissingWebXml>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-web` cung cấp `WebApplicationInitializer`, `ContextLoaderListener` và `DelegatingFilterProxy`; `spring-security-config` cung cấp cấu hình HTTP; `spring-security-web` chứa các security filter. Servlet API có `scope=provided` vì **Tomcat cung cấp Servlet API khi chạy**. Spring Framework 6 dùng namespace `jakarta.servlet.*`, không dùng `javax.servlet.*` của các ứng dụng đời trước.

Khi sử dụng Spring Framework BOM và Spring Security BOM, phiên bản Spring của các dependency được quản lý đồng bộ; tránh trộn ngẫu nhiên major version Spring 5 / Security 6 hoặc Tomcat 9 / Jakarta Servlet 6.

### 3.2. `SecurityConfig.java`: tạo chuỗi bảo mật và tài khoản minh họa

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin").hasRole("ADMIN")
                .requestMatchers("/hello").authenticated()
                .anyRequest().denyAll()
        );
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("demo123"))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }
}
```

Giải thích:

- `@EnableWebSecurity` kích hoạt cấu hình web security và các bean hạ tầng của Spring Security; trong đó hệ thống tạo bean filter có tên **`springSecurityFilterChain`**.
- `@Bean SecurityFilterChain` cung cấp quy tắc HTTP được dùng bên trong bean đó. Tên method `securityFilterChain` không thay cho tên `springSecurityFilterChain` của `DelegatingFilterProxy`.
- `hasRole("ADMIN")` theo mặc định tìm authority `ROLE_ADMIN`; builder `.roles("ADMIN")` cấp authority tương ứng.
- `httpBasic()` cho phép kiểm chứng credential gửi qua header `Authorization: Basic ...`. Chỉ dùng với HTTPS ở môi trường có dữ liệu thật.
- `anyRequest().denyAll()` khóa các URL không khai báo, để ví dụ có ranh giới phân quyền rõ ràng.
- `BCryptPasswordEncoder` lưu mật khẩu trong bộ nhớ dưới dạng hash; mật khẩu `demo123` và hai tài khoản test chỉ dùng cho bài thực hành.

Ví dụ chỉ thực hiện GET; CSRF vẫn được Spring Security bật theo cấu hình mặc định. Khi bổ sung POST/PUT/DELETE, phải xử lý CSRF token và chính sách sử dụng session/API phù hợp, không tùy tiện tắt CSRF chỉ để thử demo.

### 3.3. `GreetingServlet.java`: servlet nghiệp vụ không cần Spring MVC

```java
package example.security;

import java.io.IOException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

public class GreetingServlet extends HttpServlet {
    @Override
    protected void doGet(HttpServletRequest request,
                         HttpServletResponse response) throws IOException {
        String user = request.getUserPrincipal().getName();
        boolean adminEndpoint = "/admin".equals(request.getServletPath());

        response.setContentType("text/plain;charset=UTF-8");
        response.getWriter().write((adminEndpoint ? "admin:" : "hello:") + user);
    }
}
```

Servlet lấy `getUserPrincipal()` từ request đã đi qua Spring Security filter chain. Trong hai URL được bảo vệ, request chỉ đến servlet sau khi đã qua điều kiện `authenticated()` hoặc role tương ứng, nên ví dụ có principal hợp lệ. Với endpoint công khai, cần xử lý trường hợp `getUserPrincipal() == null`; đừng tái sử dụng nguyên method này cho anonymous endpoint mà không kiểm tra.

### 3.4. `AppInitializer.java`: đăng ký context, proxy filter và servlet

```java
package example.security;

import java.util.EnumSet;
import jakarta.servlet.DispatcherType;
import jakarta.servlet.FilterRegistration;
import jakarta.servlet.ServletContext;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRegistration;
import org.springframework.web.WebApplicationInitializer;
import org.springframework.web.context.ContextLoaderListener;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;
import org.springframework.web.filter.DelegatingFilterProxy;

public class AppInitializer implements WebApplicationInitializer {
    @Override
    public void onStartup(ServletContext servletContext) throws ServletException {
        // 1. Tạo Spring root WebApplicationContext.
        AnnotationConfigWebApplicationContext root =
                new AnnotationConfigWebApplicationContext();
        root.register(SecurityConfig.class);
        servletContext.addListener(new ContextLoaderListener(root));

        // 2. Gắn proxy filter vào Servlet container.
        FilterRegistration.Dynamic security = servletContext.addFilter(
                "springSecurityFilterChain",
                new DelegatingFilterProxy("springSecurityFilterChain")
        );
        if (security == null) {
            throw new ServletException(
                    "Filter springSecurityFilterChain already registered");
        }
        security.addMappingForUrlPatterns(
                EnumSet.of(DispatcherType.REQUEST),
                false,
                "/*"
        );

        // 3. Đăng ký servlet nghiệp vụ và URL của nó.
        ServletRegistration.Dynamic greeting = servletContext.addServlet(
                "greetingServlet", new GreetingServlet()
        );
        if (greeting == null) {
            throw new ServletException("Servlet greetingServlet already registered");
        }
        greeting.addMapping("/hello", "/admin");
    }
}
```

Đây là điểm mấu chốt của bài:

1. `AnnotationConfigWebApplicationContext` là **Spring root context** có `SecurityConfig` và các bean Spring Security.
2. `ContextLoaderListener` gắn lifecycle của root context với vòng đời ứng dụng web; container khởi tạo listener trước khi phục vụ request.
3. `servletContext.addFilter(...)` đăng ký một `DelegatingFilterProxy` **với Servlet container**. Proxy tìm Spring bean `springSecurityFilterChain` để ủy quyền khi chạy.
4. `addMappingForUrlPatterns(..., "/*")` bảo đảm các HTTP request vào ứng dụng được đi qua proxy; mapping `/hello` hoặc `/admin` riêng rẽ sẽ dễ bỏ sót những URL mới.
5. `EnumSet.of(DispatcherType.REQUEST)` là lựa chọn tối giản, đủ cho request HTTP đồng bộ của ví dụ. Trong ứng dụng có async/error dispatch, cần chủ động cấu hình thêm các dispatcher type phù hợp và xử lý ngữ cảnh bảo mật đúng cách.
6. Tham số `false` của `addMappingForUrlPatterns` là `isMatchAfter`: dùng `false` để chèn mapping trước các filter mapping đã khai báo, tùy thứ tự các initializer/filter khác. Hãy kiểm tra thực tế khi ứng dụng có encoding, logging, CORS hoặc custom filter.

Trong WAR có `spring-web`, cơ chế Servlet `ServletContainerInitializer` của Spring phát hiện các implementation `WebApplicationInitializer` khi container hỗ trợ Servlet 3+ và thực thi `onStartup`. Vì vậy cấu hình này **không cần `web.xml`**. Hãy xác nhận WAR được triển khai lên Tomcat 10.1+; không thể chạy WAR này trực tiếp bằng `java -jar` như ứng dụng Spring Boot.

### 3.5. Build, triển khai và kiểm chứng bằng HTTP

Trong thư mục có `pom.xml`:

```bash
mvn -q clean package

# Tệp kết quả:
# target/secure-demo.war
```

Chép `target/secure-demo.war` vào thư mục `webapps/` của Tomcat 10.1 và khởi động Tomcat. Trong cấu hình deploy mặc định, WAR tên `secure-demo.war` có context path `/secure-demo`. Nếu đổi context path qua cấu hình Tomcat, hãy thay phần đó trong các URL dưới đây.

```bash
# Khách chưa xác thực:
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/secure-demo/hello
# 401

# User thường truy cập URL cần đăng nhập:
curl -s -u alice:demo123 \
  http://localhost:8080/secure-demo/hello
# hello:alice

# User thường không có ROLE_ADMIN:
curl -s -o /dev/null -w '%{http_code}\n' -u alice:demo123 \
  http://localhost:8080/secure-demo/admin
# 403

# Admin có ROLE_ADMIN:
curl -s -u admin:demo123 \
  http://localhost:8080/secure-demo/admin
# admin:admin
```

Các kết quả là **kỳ vọng của cấu hình mẫu** khi Tomcat chạy đúng và không có filter/policy khác. Lệnh `curl` dùng cách viết shell kiểu POSIX. Với endpoint HTTP Basic, client thiếu credential hợp lệ thường nhận HTTP 401 kèm challenge; người đã xác thực nhưng thiếu role nhận HTTP 403.

Nếu hai endpoint đều trả 200 kể cả khi không có header Authorization, cần nghi ngờ **proxy chưa được gắn đúng vào Servlet container**, filter mapping chưa khớp hoặc WAR đang chạy bản cũ. Nếu khởi tạo lỗi `NoSuchBeanDefinitionException` liên quan `springSecurityFilterChain`, hãy kiểm tra root context, `@EnableWebSecurity` và sự tương ứng tên bean.

## 4. Phương án B: `AbstractSecurityWebApplicationInitializer` tự đăng ký proxy

Thay cho **bước 2** trong `AppInitializer` ở trên, có thể dùng initializer do Spring Security cung cấp:

```java
package example.security;

import org.springframework.security.web.context.AbstractSecurityWebApplicationInitializer;

public class SecurityInitializer
        extends AbstractSecurityWebApplicationInitializer {
}
```

Khi dùng cách B:

- **Giữ lại** cách tạo root `WebApplicationContext` và khai báo `SecurityConfig` của `AppInitializer`, cũng như phần đăng ký `GreetingServlet`.
- **Xóa hẳn phần `servletContext.addFilter(...)` ở bước 2 của `AppInitializer`** để không đăng ký hai proxy cùng tên.
- Thêm `SecurityInitializer` riêng. Lớp cơ sở `AbstractSecurityWebApplicationInitializer` tích hợp `DelegatingFilterProxy` với tên `springSecurityFilterChain` vào container.
- Constructor không tham số của lớp kế thừa phù hợp khi **Spring root context đã được tạo ở nơi khác**. Nếu dùng constructor nhận các class cấu hình, cần xem xét ai đang tạo root context để tránh khởi tạo context hai lần.

Cách này thường đơn giản hơn trong dự án Spring Security Java config. Nó không thay thế `@EnableWebSecurity`, `SecurityFilterChain` hay việc tải Spring context.

**Ứng dụng dùng Spring MVC cần lưu ý:** root context và child context của `DispatcherServlet` là hai phạm vi bean khác nhau. Nếu sử dụng `MvcRequestMatcher` hoặc matcher tích hợp `HandlerMappingIntrospector`, cấu hình Spring Security phải nhìn thấy cấu hình MVC phù hợp; nhiều thiết kế đặt cả security và MVC config trong servlet application context. Khi làm vậy, kiểm tra cách `DelegatingFilterProxy` truy cập context chứa bean đích, hoặc cấu hình target context rõ ràng; không giả định bean ở child context luôn được proxy tìm thấy qua root context. Ví dụ ở mục 3 dùng Servlet thuần, nên không gặp bài toán tích hợp matcher MVC.

## 5. Phương án C: đăng ký `DelegatingFilterProxy` bằng `web.xml`

Trong ứng dụng WAR truyền thống, bạn có thể dùng `src/main/webapp/WEB-INF/web.xml` thay cho **toàn bộ `AppInitializer`** ở mục 3. Ví dụ dưới đây tạo root annotation context từ `SecurityConfig`, đăng ký proxy và servlet:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="https://jakarta.ee/xml/ns/jakartaee
                             https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">

    <context-param>
        <param-name>contextClass</param-name>
        <param-value>org.springframework.web.context.support.AnnotationConfigWebApplicationContext</param-value>
    </context-param>
    <context-param>
        <param-name>contextConfigLocation</param-name>
        <param-value>example.security.SecurityConfig</param-value>
    </context-param>

    <listener>
        <listener-class>org.springframework.web.context.ContextLoaderListener</listener-class>
    </listener>

    <filter>
        <filter-name>springSecurityFilterChain</filter-name>
        <filter-class>org.springframework.web.filter.DelegatingFilterProxy</filter-class>
    </filter>
    <filter-mapping>
        <filter-name>springSecurityFilterChain</filter-name>
        <url-pattern>/*</url-pattern>
    </filter-mapping>

    <servlet>
        <servlet-name>greetingServlet</servlet-name>
        <servlet-class>example.security.GreetingServlet</servlet-class>
    </servlet>
    <servlet-mapping>
        <servlet-name>greetingServlet</servlet-name>
        <url-pattern>/hello</url-pattern>
        <url-pattern>/admin</url-pattern>
    </servlet-mapping>
</web-app>
```

Với cách C, **không đóng gói `AppInitializer` hoặc `SecurityInitializer` của hai phương án trước** trong WAR, vì Servlet container vẫn có thể tự phát hiện và gọi các initializer đó. Hai class `SecurityConfig` và `GreetingServlet` giữ nguyên; `web.xml` chịu trách nhiệm tạo root context, đăng ký filter và mapping servlet. Phải giữ **`filter-name` đúng `springSecurityFilterChain`**, vì đó là tên bean mà proxy mặc định tìm trong Spring context.

Trong `web.xml` này, `<filter-mapping>` không khai báo `<dispatcher>`, nên Servlet spec áp dụng mapping cho `REQUEST` theo mặc định. Nếu cần xử lý `ASYNC`, `ERROR` hoặc `FORWARD`, phải khai báo dispatcher mapping thích hợp và kiểm tra async support/filter ordering.

Không dùng XML schema `javax.servlet` hoặc WAR chạy trên Tomcat 9 cho ví dụ Spring 6 này: Tomcat 10.1+ dùng Jakarta Servlet namespace.

## 6. Nếu ứng dụng thực tế có nhiều filter, nhiều security chain

### 6.1. Filter của Servlet container khác filter nằm trong Spring Security

Có hai vị trí đăng ký dễ bị lẫn:

1. **Container filter**: đăng ký qua `ServletContext.addFilter`, `web.xml`, `@WebFilter` hoặc cơ chế container. `DelegatingFilterProxy` thuộc nhóm này.
2. **Security filter nội bộ**: thêm vào một `SecurityFilterChain` bằng `HttpSecurity.addFilterBefore`, `addFilterAfter`, `addFilterAt` và các cơ chế cấu hình security. Nhóm này do `FilterChainProxy` gọi theo cấu hình.

Chẳng hạn filter đọc JWT custom cần chạy ở vị trí thích hợp trong Spring Security chain thì thường được đăng ký **bên trong `HttpSecurity`**; đừng vô tình đăng ký cùng instance đó thêm lần nữa với Servlet container, vì nó có thể chạy hai lần hoặc chạy sai thứ tự. Nếu filter là Spring bean và dùng các cơ chế tự động đăng ký Servlet filter của hạ tầng khác, phải kiểm soát việc đăng ký trùng.

`DelegatingFilterProxy` thường đăng ký **một lần** ở container, trong khi `FilterChainProxy` có thể chứa nhiều `SecurityFilterChain`:

```java
// Minh họa bên trong một class @Configuration có @EnableWebSecurity.
// Hai bean được chọn bằng securityMatcher theo thứ tự cấu hình.
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    http.httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    http.formLogin(Customizer.withDefaults());
    return http.build();
}
```

Đây là **fragment minh họa riêng** (không ghép hai method vào `SecurityConfig` của mục 3). Cần import thêm `org.springframework.core.annotation.Order`. `FilterChainProxy` chọn **security chain đầu tiên phù hợp**; nếu không chain nào khớp, request có thể không được bảo vệ bởi Spring Security. `securityMatcher(...)` chọn phạm vi **của cả chain**; `requestMatchers(...)` bên trong `authorizeHttpRequests` chọn quy tắc **phân quyền** của chain đã được chọn.

### 6.2. Dispatcher types và thứ tự thực thi

- Đăng ký `/*` cho proxy giúp giảm nguy cơ bỏ sót URL; `requestMatchers` vẫn có thể quyết định quyền chi tiết bên trong.
- `REQUEST` đáp ứng luồng đồng bộ cơ bản. Các dispatch phụ như `FORWARD`, `ASYNC`, `ERROR` cần cân nhắc cả mapping ở Servlet container lẫn behavior của Spring Security trong phiên bản đang dùng; đừng giả định toàn bộ dispatch sẽ tự đi qua security nếu filter chỉ map `REQUEST`.
- Cần tránh đăng ký security filter **sau** một filter khác vốn đã trả response hoặc thay đổi security-relevant state; kiểm tra thực tế thứ tự container filters và security chain filters bằng logging có kiểm soát.
- Trên Servlet async, ngoài dispatcher mapping, cần bảo đảm các servlet/filter liên quan hỗ trợ async và security context được truyền đúng khi xử lý ở thread khác.

## 7. Những lỗi triển khai thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Endpoint truy cập được không cần auth | Proxy chưa được đăng ký, mapping không khớp, cấu hình permitAll quá rộng hoặc đang chạy WAR cũ | Kiểm tra mapping `/*`, `onStartup`, URL và filter chain được chọn |
| Lỗi `No bean named 'springSecurityFilterChain'` | Chưa load `SecurityConfig`, thiếu `@EnableWebSecurity`, sai context hoặc sai filter target name | Kiểm tra root/child context và bean hạ tầng |
| Filter đã có tên khi `addFilter` trả `null` | Đăng ký trùng bởi Java initializer và `web.xml` hoặc hai initializer | Chọn một cách đăng ký; bỏ đường trùng |
| Ứng dụng không gọi `onStartup` | Container/Servlet API không phù hợp hoặc WAR không phát hiện Spring `ServletContainerInitializer` | Kiểm tra phiên bản Tomcat, `spring-web` trong WAR và startup logs |
| `ClassNotFoundException: javax.servlet...` hoặc `jakarta.servlet...` | Trộn các major version Java EE/Jakarta EE | Dùng Spring 6 + Tomcat 10.1+ + `jakarta.servlet` đồng bộ |
| Có 401 khi không có credentials | Endpoint yêu cầu auth; Basic challenge hoạt động | Đăng nhập/test credential đúng, không mặc định xem là lỗi filter |
| Có 403 với tài khoản đã đăng nhập | Thiếu `ROLE_ADMIN` hoặc không thỏa quy tắc; đôi khi CSRF hay policy khác | Xem authorities và rule/method security/CSRF |
| Dùng Spring MVC nhưng matcher không nhận cấu hình MVC | Security config không nhìn thấy `HandlerMappingIntrospector` đúng context | Đặt cấu hình matcher phù hợp vào context và kiểm tra wiring của proxy |
| Filter custom chạy hai lần | Đăng ký vừa ở container vừa trong `SecurityFilterChain` | Chọn vị trí quản lý thích hợp, tránh auto-registration trùng |
| Security context bị mất trong async thread | Context gắn với thread/request, không tự truyền theo mọi cơ chế async | Dùng cơ chế context propagation do Spring Security hỗ trợ |

Khi debug, trước tiên xác minh **container có gọi proxy không**; kế đến **proxy có tìm thấy `springSecurityFilterChain` không**; sau đó **`FilterChainProxy` chọn chain nào**; cuối cùng xem **authentication và authorization**. Đó là bốn tầng khác nhau và giúp tránh thay đổi rule quyền khi lỗi thật sự nằm ở đăng ký filter.

Không dùng cơ chế debug hoặc trace có khả năng ghi mật khẩu/Bearer token vào logs ở môi trường thực. Có thể bật logging bảo mật phù hợp ở môi trường phát triển để quan sát các filter/chain, đồng thời che thông tin nhạy cảm.

## 8. Bài tập xác minh hiểu đúng

1. **Đã có `SecurityFilterChain` bean, sao còn phải đăng ký `DelegatingFilterProxy`?** Vì Servlet container chỉ chạy những filter nó biết; proxy là cầu nối từ Servlet filter chain sang bean Spring Security.
2. **Tên `springSecurityFilterChain` và tên method `securityFilterChain` có giống chức năng?** Không. `springSecurityFilterChain` là bean filter được proxy tìm; bean `SecurityFilterChain` mô tả cấu hình rule/filter nội bộ.
3. **Tự dùng `AppInitializer` có cần thêm `web.xml` để đăng ký cùng filter không?** Không. Chọn một cách đăng ký, tránh trùng.
4. **Vì sao URL `/secure-demo/hello` vẫn khớp matcher `/hello`?** Matcher làm việc trên đường dẫn ứng dụng theo cơ chế matcher của Spring Security, không lấy nguyên context path `/secure-demo` làm tiền tố trong rule minh họa.
5. **Vì sao `alice` nhận 200 ở `/hello` nhưng 403 ở `/admin`?** Alice đã xác thực với `ROLE_USER`, nhưng thiếu `ROLE_ADMIN` mà `hasRole("ADMIN")` yêu cầu.
6. **Khi thêm một security filter custom vào `HttpSecurity`, có nên đăng ký thêm cùng filter bằng `ServletContext.addFilter`?** Thông thường không; như vậy có thể chạy trùng hoặc sai vị trí trong chain.
7. **Nếu Spring MVC sử dụng matcher phụ thuộc `HandlerMappingIntrospector`, cần kiểm tra gì?** Cấu hình Spring Security nhìn thấy đúng MVC application context và proxy trỏ tới context có bean đích.

**Nguyên tắc kết thúc:** Trong ứng dụng Servlet không dùng Boot, bạn cần đồng thời có **Spring context chứa `springSecurityFilterChain`**, **một `DelegatingFilterProxy` được container đăng ký đúng một lần**, và **filter mapping phủ các request cần bảo vệ**. Sau khi nối đúng ba thành phần đó, mới đánh giá luật `SecurityFilterChain`, quyền `hasRole/hasAuthority` và kết quả 401/403.