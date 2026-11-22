# addFilterBefore, addFilterAfter và addFilterAt: chọn điểm mở rộng trong Spring Security Servlet

## 1. Vấn đề: chèn filter vào đúng chỗ trong chuỗi bảo mật

Trong ứng dụng Spring Boot sử dụng **Servlet stack** (ví dụ Spring MVC), HTTP request đi qua chuỗi Servlet Filter trước khi đến controller. Spring Security triển khai bảo mật HTTP bằng **SecurityFilterChain**, nơi các filter thực hiện công việc như nạp SecurityContext, xử lý CSRF, xác thực và phân quyền.

Khi cần thêm xử lý riêng, Spring Security cho phép gắn một filter vào chuỗi bằng ba phương thức trên **HttpSecurity**:

- **addFilterBefore(customFilter, AnchorFilter.class)**: xếp filter mới **trước** vị trí của filter mốc.
- **addFilterAfter(customFilter, AnchorFilter.class)**: xếp filter mới **sau** vị trí của filter mốc.
- **addFilterAt(customFilter, AnchorFilter.class)**: xếp filter mới **cùng vị trí thứ tự** với filter mốc. Cách này **không tự thay thế** filter mốc; nếu cả hai có mặt, thứ tự giữa chúng không được bảo đảm.

Bài học hướng dẫn chọn điểm mở rộng, hiểu chính xác ý nghĩa của “trước/sau/cùng vị trí”, tự tạo hai filter mẫu chạy được, quan sát hiệu ứng qua HTTP và tránh các lỗi thường gặp khi đăng ký filter.

**Mục tiêu sau bài:** bạn biết khi nào cần filter, chọn được anchor phù hợp, phân biệt ba phương thức, không vô tình chạy filter hai lần và biết cách kiểm tra thứ tự thực tế bằng log hoặc bài thử HTTP.

## 2. Bản đồ kiến trúc: filter của Servlet và filter của Spring Security

Các lớp tham gia cơ bản:

~~~text
HTTP client
    |
    v
Servlet container filter chain
    |
    +-- (Các Servlet Filter khác của ứng dụng, nếu có)
    |
    +-- DelegatingFilterProxy: springSecurityFilterChain
            |
            v
        FilterChainProxy
            |
            +-- Chọn SecurityFilterChain đầu tiên khớp request
                    |
                    +-- Spring Security filters theo thứ tự đã cấu hình
                    |
                    v
                DispatcherServlet -> Controller -> Service
~~~

- **DelegatingFilterProxy** kết nối Servlet container với bean Spring tên **springSecurityFilterChain**.
- **FilterChainProxy** quản lý một hoặc nhiều **SecurityFilterChain**, chọn chain đầu tiên có matcher phù hợp.
- **SecurityFilterChain** là tập hợp có thứ tự của những filter sẽ xử lý request tương ứng.
- **HttpSecurity** là builder dùng để định nghĩa chain. Các phương thức addFilterBefore/addFilterAfter/addFilterAt chèn filter vào **chain đang cấu hình**, không mặc nhiên chèn vào mọi chain khác.
- **OncePerRequestFilter** là lớp cơ sở tiện dụng khi viết filter của Spring Web. Nó hỗ trợ tránh lặp lại quá trình lọc trong một lần dispatch theo cơ chế đánh dấu của framework; cần hiểu riêng hành vi với ASYNC/ERROR dispatch.

Đừng nhầm **Servlet Filter toàn cục** với **filter thuộc SecurityFilterChain**. Một filter đăng ký trực tiếp với Servlet container có thể chạy ở phạm vi khác và thứ tự khác với các filter được chèn qua HttpSecurity.

### Ví dụ thứ tự khái niệm

Khi ứng dụng bật HTTP Basic, có thể hình dung một phần của chuỗi như sau:

~~~text
... SecurityContextHolderFilter ...
    |
    +-- BeforeBasicFilter              (tự thêm bằng addFilterBefore)
    |
    +-- BasicAuthenticationFilter      (xác thực HTTP Basic)
    |
    +-- AfterBasicFilter               (tự thêm bằng addFilterAfter)
    |
    ... các filter khác ...
    |
    +-- AuthorizationFilter            (quyết định quyền URL)
    |
    v
Controller
~~~

Đây là **đoạn minh họa** phục vụ việc so sánh trước/sau, không phải danh sách đầy đủ mọi filter hoặc thứ tự bất biến cho tất cả phiên bản/cấu hình. Muốn xác nhận chain thật, xem log/debug hoặc kiểm tra SecurityFilterChain của ứng dụng đang chạy.

## 3. Ý nghĩa chính xác của ba API

| API | Vị trí được yêu cầu | Dùng khi | Điều cần nhớ |
| --- | --- | --- | --- |
| **addFilterBefore(f, A.class)** | Filter f nằm trước **vị trí thứ tự** của A | Phải đọc/chỉnh thông tin request trước một cơ chế bảo mật cụ thể | Nếu không cần biết kết quả xác thực thì có thể đặt trước filter xác thực |
| **addFilterAfter(f, A.class)** | Filter f nằm sau **vị trí thứ tự** của A | Cần quan sát trạng thái đã được filter A xử lý, ví dụ kết quả HTTP Basic thành công | Nếu A kết thúc request sớm vì lỗi, f có thể không được gọi |
| **addFilterAt(f, A.class)** | f nhận **cùng thứ tự** đã đăng ký của A | Chủ động thiết kế một cơ chế cùng vị trí, thường là filter xác thực tùy biến | **Không phải lệnh replace**; nếu A vẫn tồn tại thì hai filter có thể cùng ở một vị trí, không có thứ tự xác định giữa chúng |

Cách gọi có dạng:

~~~java
http.addFilterBefore(myFilter, BasicAuthenticationFilter.class);
http.addFilterAfter(myFilter, BasicAuthenticationFilter.class);
http.addFilterAt(myFilter, BasicAuthenticationFilter.class);
~~~

Ba dòng trên **chỉ là ba cách thay thế để minh họa API**, không phải hướng dẫn gọi cả ba cho cùng một instance myFilter. Khi chèn, cần quyết định một mục tiêu rõ ràng và dùng một vị trí có ý nghĩa.

### “Anchor” có nghĩa gì?

**AnchorFilter.class** là **lớp filter dùng làm mốc vị trí** trong bảng thứ tự mà Spring Security biết. Spring Security xác định thứ tự thông qua đăng ký lớp filter và các quy tắc nội bộ, thay vì đơn thuần tìm một object trong danh sách rồi luôn chèn sát object đó.

Điểm dễ nhầm:

1. **Anchor phải có thứ tự mà Spring Security nhận biết.** Chọn một lớp filter tùy tiện chưa được đăng ký thứ tự có thể khiến ứng dụng lỗi khi build SecurityFilterChain; không phải cứ là lớp implements Filter thì dùng làm anchor được.
2. **Một anchor có vị trí đã biết không đồng nghĩa instance anchor chắc chắn hiện diện trong chain.** Việc dùng AnchorFilter.class không tự bật tính năng tương ứng. Ví dụ, chỉ dùng UsernamePasswordAuthenticationFilter.class làm mốc không tự bật form login.
3. **addFilterBefore/After bảo đảm quan hệ thứ tự theo anchor,** nhưng không bảo đảm những filter khác sẽ luôn nằm cách đúng một vị trí ngay bên cạnh.
4. **Không nên phụ thuộc vào cách Spring Security sắp xếp các filter có cùng order.** Nếu cần thứ tự nghiêm ngặt giữa hai filter riêng, dùng quan hệ before/after rõ ràng.

Trong dự án có nhiều SecurityFilterChain, filter được thêm vào chain nào thì phục vụ chain đó. Một đường dẫn không khớp chain sẽ không thấy filter riêng của chain ấy.

## 4. Chọn Before, After hay At theo nhu cầu

**Chọn addFilterBefore khi cần tiền xử lý trước một bước cụ thể.**

Ví dụ: trước **BasicAuthenticationFilter** muốn đặt correlation ID vào request attribute, đánh dấu request phục vụ truy vết, hoặc chuẩn hóa một phần metadata không nhạy cảm. Hãy chọn before khi tác vụ của bạn **không cần** Authentication do BasicAuthenticationFilter tạo ra.

Lưu ý: nếu trước Basic có cơ chế khác đã xác thực (session, filter khác...), SecurityContext có thể đã có thông tin. Vì vậy “before Basic” **không tuyệt đối** đồng nghĩa “request luôn chưa xác thực”.

**Chọn addFilterAfter khi cần dữ liệu đã được bước mốc xử lý.**

Ví dụ: ngay sau **BasicAuthenticationFilter**, bạn muốn ghi nhận mức thông tin tối thiểu rằng request đã có Authentication hợp lệ, rồi truyền tiếp. Filter sau Basic có thể quan sát SecurityContext sau khi Basic xác thực thành công. Nếu Basic từ chối vì credentials sai và kết thúc response, filter đặt sau nó có thể không chạy.

Đừng suy diễn “after Basic” nghĩa là “mọi quyết định phân quyền đã xong”: **AuthorizationFilter** còn xử lý ở giai đoạn sau; request thiếu role vẫn có thể nhận 403 sau khi filter của bạn đã chạy.

**Chọn addFilterAt khi cần chủ động thiết kế filter ở cùng vị trí đã định nghĩa.**

Trường hợp phù hợp thường liên quan triển khai filter xác thực tùy biến, khi bạn hiểu rõ vị trí của cơ chế cũ và cách loại bỏ nó khỏi chain nếu muốn thay thế luồng cũ. **addFilterAt không tự loại bỏ filter sẵn có.** Đặt một filter khác vào cùng vị trí của UsernamePasswordAuthenticationFilter trong lúc formLogin vẫn bật có thể khiến hai filter cùng hoạt động, với thứ tự không rõ ràng.

Cách dễ nhớ: **Before = trước mốc; After = sau mốc; At = cùng bậc thứ tự với mốc, không phải thay mốc.**

### Quy tắc chọn điểm mở rộng

- Muốn gắn **tracing/correlation ID, thông tin hạ tầng nhẹ**: chọn filter có vị trí trước bước cần quan sát; không ghi credentials hay token vào log.
- Muốn biết **Authentication đã được Basic tạo chưa**: chọn after Basic, nhưng xử lý cả trường hợp thiếu Authentication và request bị chặn sớm.
- Muốn thực hiện **xác thực bằng một giao thức chuẩn**: trước tiên xem Spring Security có cơ chế sẵn như httpBasic, formLogin, oauth2ResourceServer, AuthenticationProvider hay AuthenticationConverter hay không. Chỉ thêm filter custom khi thực sự cần.
- Muốn kiểm tra **người dùng có quyền truy cập dữ liệu nào**: dùng authorizeHttpRequests, method security hoặc kiểm tra ở service; đây không phải lý do đủ để tự tạo một filter authorization phức tạp.
- Muốn **thay cơ chế xác thực hiện có**: cấu hình rõ cơ chế nào được bật/tắt, cách xử lý AuthenticationManager và failure/success, sau đó mới cân nhắc addFilterAt.

## 5. Ví dụ hoàn chỉnh: chèn filter trước và sau HTTP Basic

Ta sẽ tạo ứng dụng Spring Boot có hai filter để chứng minh vị trí hoạt động:

1. **BeforeBasicFilter** thêm header phản hồi **X-Demo-Before-Basic: visited** trước khi HTTP Basic được xử lý.
2. **AfterBasicFilter** đọc SecurityContext ngay sau vị trí HTTP Basic và đặt header **X-Demo-After-Basic: authenticated** hoặc **missing**. Không đưa tên user hay token lên header.
3. **SecurityFilterChain** bật HTTP Basic, khai báo quyền cho ba endpoint và thêm hai filter bằng addFilterBefore/addFilterAfter.
4. **UserDetailsService** trong bộ nhớ cung cấp hai tài khoản để thử các nhánh 200/401/403.

Ví dụ chạy với **Java 17+**, **Spring Boot 3.3.13**, **Spring Security 6** và Maven. Đây là môi trường học tập cục bộ với tài khoản mẫu, không dùng credential hardcoded khi triển khai thật.

### 5.1. Cấu trúc tệp

~~~text
filter-extension-demo/
├── pom.xml
└── src/main/java/com/example/filterdemo/
    ├── FilterDemoApplication.java
    ├── SecurityConfig.java
    ├── BeforeBasicFilter.java
    ├── AfterBasicFilter.java
    └── DemoController.java
~~~

### 5.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>filter-extension-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
~~~

Spring Boot parent quản lý các phiên bản Spring Framework và Spring Security tương thích, nên không cần tự khai version cho starter-security.

### 5.3. FilterDemoApplication.java

~~~java
package com.example.filterdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterDemoApplication.class, args);
    }
}
~~~

Tất cả lớp nằm trong package com.example.filterdemo để Spring Boot tự phát hiện SecurityConfig và DemoController.

### 5.4. BeforeBasicFilter.java

~~~java
package com.example.filterdemo;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

public final class BeforeBasicFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        // Đánh dấu rằng request đã đi qua filter này trước vị trí HTTP Basic.
        response.setHeader("X-Demo-Before-Basic", "visited");

        // Cho request tiếp tục tới các filter kế tiếp.
        chain.doFilter(request, response);
    }
}
~~~

**Giải thích:**

- **OncePerRequestFilter** cung cấp doFilterInternal để viết logic ở một vị trí tập trung.
- **setHeader** chỉ được dùng làm dấu quan sát trong ví dụ. Nó không xác thực user và không thay đổi quyền.
- **chain.doFilter(...)** chuyển điều khiển sang filter tiếp theo. Nếu thiếu dòng này, request có thể dừng trước khi đến controller và các bộ lọc bảo mật phía sau.
- Không khai báo @Component hoặc @Bean cho class filter trong ví dụ. Filter sẽ được tạo trực tiếp trong SecurityConfig để tránh bị Spring Boot đăng ký thêm vào Servlet container.

### 5.5. AfterBasicFilter.java

~~~java
package com.example.filterdemo;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class AfterBasicFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        boolean authenticated =
                authentication != null && authentication.isAuthenticated();

        response.setHeader(
                "X-Demo-After-Basic",
                authenticated ? "authenticated" : "missing");

        chain.doFilter(request, response);
    }
}
~~~

**Giải thích:**

- Với HTTP Basic hợp lệ và cấu hình ở phần sau, **Authentication** đã được tạo tại vị trí này. Header phản hồi sẽ mang giá trị **authenticated**.
- Với request không gửi credentials và chưa có Authentication, header sẽ là **missing**. Điều này vẫn cho phép /public vì rule permitAll cho phép anonymous request.
- Sau filter này, còn các bước phân quyền. Một request có header authenticated **vẫn có thể nhận 403** vì thiếu role ADMIN.
- Nếu HTTP Basic từ chối credentials sai và kết thúc xử lý ngay, AfterBasicFilter **có thể không được gọi**. Không dựa vào header này để xác định toàn bộ kết quả xác thực.
- Header chỉ có giá trị minh họa, không chứng minh quyền hoặc mức bảo mật của request. Trong ứng dụng thực, có thể thay bằng ghi nhận metric/audit đã được thiết kế an toàn.

**Chú ý về AnonymousAuthenticationToken:** Với vị trí sau Basic nhưng trước AnonymousAuthenticationFilter, request chưa đăng nhập thường chưa có Authentication. Ở vị trí **sau** anonymous filter, Authentication có thể là anonymous với isAuthenticated() là true. Khi cần phân biệt người dùng thật, phải kiểm tra loại token hoặc dùng cách kiểm tra danh tính phù hợp, không chỉ dựa vào isAuthenticated().

### 5.6. SecurityConfig.java

~~~java
package com.example.filterdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        // Chỉ thêm qua HttpSecurity: hai filter không đăng ký Servlet Filter riêng.
        http.addFilterBefore(new BeforeBasicFilter(),
                             BasicAuthenticationFilter.class);

        http.addFilterAfter(new AfterBasicFilter(),
                            BasicAuthenticationFilter.class);

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }
}
~~~

**Vì sao cấu hình này phù hợp để quan sát thứ tự?**

- **httpBasic(...)** thêm cơ chế HTTP Basic, trong đó có **BasicAuthenticationFilter** mà ta dùng làm anchor.
- **addFilterBefore** đặt BeforeBasicFilter trước vị trí BasicAuthenticationFilter.
- **addFilterAfter** đặt AfterBasicFilter sau vị trí BasicAuthenticationFilter.
- **SessionCreationPolicy.STATELESS** tránh việc dựa vào session để nhớ Authentication giữa các request; mỗi lệnh curl Basic có hoặc không có credentials đều dễ kiểm chứng độc lập.
- **formLogin(disable)** tắt login form để /me chưa đăng nhập được thử qua HTTP Basic và phản hồi 401, thay vì redirect sang trang login.
- **authorizeHttpRequests** yêu cầu đăng nhập với /me, ROLE_ADMIN với /admin, công khai /public; request khác bị từ chối.
- **BCryptPasswordEncoder** mã hóa mật khẩu mẫu bằng hash để cơ chế xác thực kiểm tra. Trong production cần lưu hash bền vững, không hardcode mật khẩu.
- **CSRF** không bị tắt. Ví dụ chỉ dùng GET nên không cần CSRF token; khi thêm POST/PUT/DELETE phải kiểm tra chính sách CSRF theo mô hình client.

**Không đặt @Component trên BeforeBasicFilter hoặc AfterBasicFilter.** Nếu một filter là Spring bean kiểu Filter, Spring Boot có thể tự đăng ký nó vào Servlet container. Đồng thời thêm chính bean ấy vào SecurityFilterChain có thể khiến nó chạy hai lần hoặc chạy ở vị trí ngoài mong muốn.

### 5.7. DemoController.java

~~~java
package com.example.filterdemo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public-ok";
    }

    @GetMapping("/me")
    public String profile(Authentication authentication) {
        return "user=" + authentication.getName();
    }

    @GetMapping("/admin")
    public String adminEndpoint() {
        return "admin-ok";
    }
}
~~~

Ba endpoint phân biệt rõ **request công khai**, **request cần danh tính hợp lệ**, và **request cần role ADMIN**. Các header thêm bởi hai filter vẫn có thể xuất hiện kể cả khi controller không chạy, vì filter xử lý trước giai đoạn controller.

## 6. Chạy và tự kiểm chứng bằng HTTP

Tại thư mục **filter-extension-demo** có pom.xml:

~~~bash
mvn spring-boot:run
~~~

Dùng terminal khác để gọi curl. Nếu Windows PowerShell có alias curl, sử dụng **curl.exe** thay cho curl; các đối số giữ nguyên.

### Trường hợp A — GET công khai, chưa có credentials

~~~bash
curl -i http://localhost:8080/public
~~~

Kết quả trọng tâm dự kiến:

~~~http
HTTP/1.1 200
X-Demo-Before-Basic: visited
X-Demo-After-Basic: missing

public-ok
~~~

Điều này chứng minh hai filter đã được gọi, nhưng chưa có Authentication tại vị trí AfterBasicFilter. Request vẫn được phép vì GET /public được cấu hình permitAll.

### Trường hợp B — GET /me với credentials hợp lệ

~~~bash
curl -i -u alice:alice-pass http://localhost:8080/me
~~~

Kết quả trọng tâm dự kiến:

~~~http
HTTP/1.1 200
X-Demo-Before-Basic: visited
X-Demo-After-Basic: authenticated

user=alice
~~~

BasicAuthenticationFilter xác thực alice thành công; AfterBasicFilter quan sát được Authentication; rule authenticated() chấp nhận request rồi controller nhận danh tính alice.

### Trường hợp C — GET /me thiếu credentials

~~~bash
curl -i http://localhost:8080/me
~~~

Kết quả trọng tâm dự kiến:

~~~http
HTTP/1.1 401
X-Demo-Before-Basic: visited
X-Demo-After-Basic: missing
WWW-Authenticate: Basic realm="Realm"
~~~

Các header khác và chi tiết của WWW-Authenticate phụ thuộc cấu hình. Điều cần quan sát: before filter đã chạy, after filter thấy thiếu Authentication, và quy tắc authenticated() khiến hệ thống yêu cầu xác thực.

### Trường hợp D — GET /me với mật khẩu sai

~~~bash
curl -i -u alice:wrong-pass http://localhost:8080/me
~~~

Kết quả chính: **401**. Trước khi request đi tiếp, HTTP Basic có thể trực tiếp xử lý lỗi xác thực và kết thúc response; do đó **X-Demo-After-Basic không nhất thiết xuất hiện**. Đây là bằng chứng quan trọng: addFilterAfter không đảm bảo filter sau mốc được gọi cho mọi request, đặc biệt khi mốc từ chối sớm.

### Trường hợp E — Đăng nhập đúng nhưng thiếu quyền

~~~bash
curl -i -u alice:alice-pass http://localhost:8080/admin
~~~

Kết quả trọng tâm:

~~~http
HTTP/1.1 403
X-Demo-Before-Basic: visited
X-Demo-After-Basic: authenticated
~~~

AfterBasicFilter thấy Authentication thành công, song **AuthorizationFilter** từ chối vì alice chỉ có ROLE_USER. Filter đặt sau Basic **không phải** là filter có vị trí sau toàn bộ authorization.

### Trường hợp F — Admin hợp lệ

~~~bash
curl -i -u admin:admin-pass http://localhost:8080/admin
~~~

Kết quả trọng tâm dự kiến:

~~~http
HTTP/1.1 200
X-Demo-Before-Basic: visited
X-Demo-After-Basic: authenticated

admin-ok
~~~

Bảng đối chiếu:

| Request | Status dự kiến | X-Demo-Before-Basic | X-Demo-After-Basic | Ý nghĩa |
| --- | --- | --- | --- | --- |
| GET /public, không credentials | 200 | visited | missing | Hai filter chạy; URL public |
| GET /me, alice đúng mật khẩu | 200 | visited | authenticated | HTTP Basic tạo Authentication |
| GET /me, không credentials | 401 | visited | missing | Xác thực bắt buộc |
| GET /me, alice sai mật khẩu | 401 | visited | Có thể không có | Basic có thể dừng chain do lỗi |
| GET /admin, alice đúng mật khẩu | 403 | visited | authenticated | Xác thực thành công, thiếu role |
| GET /admin, admin đúng mật khẩu | 200 | visited | authenticated | Đủ quyền |

Bảng chỉ biểu diễn các header/status quan trọng của ví dụ. HTTP server có thể tự thêm Date, Cache-Control, X-Content-Type-Options, WWW-Authenticate hoặc các security header khác. Không so toàn bộ raw response từng byte.

**Điều rút ra từ thử nghiệm:** before/after mô tả vị trí trong chain; **không phải** lời hứa rằng cả hai đều chạy nếu một filter trước đó dừng request, cũng không thay thế các bước xác thực/phân quyền chuẩn.

## 7. addFilterAt: hiểu “cùng vị trí” và giới hạn thay thế

Giả sử hệ thống cần một filter xác thực đăng nhập do ứng dụng tự viết tên **CustomLoginAuthenticationFilter** và muốn đặt nó tại vị trí thường dành cho **UsernamePasswordAuthenticationFilter**.

Hình thức gọi về mặt API là:

~~~java
// Minh họa cách chọn vị trí; không phải chương trình độc lập.
// customLoginAuthenticationFilter phải được hiện thực và cấu hình đầy đủ.
http.addFilterAt(
    customLoginAuthenticationFilter,
    UsernamePasswordAuthenticationFilter.class);
~~~

**Đây là đoạn mã minh họa cấu hình khi đã có instance customLoginAuthenticationFilter**; nó không tự chạy nếu chưa tạo filter, AuthenticationManager và các handler liên quan.

Những điều bắt buộc phải hiểu:

1. **addFilterAt gán vị trí thứ tự** của UsernamePasswordAuthenticationFilter cho filter mới. Nó **không xóa** UsernamePasswordAuthenticationFilter đang có trong chain.
2. Nếu formLogin đang bật và cả filter mặc định lẫn filter tùy biến cùng tồn tại ở một order, **không thể dựa vào thứ tự thực thi giữa hai filter đó**. Sự kiện login có thể bị xử lý bởi cơ chế không như mong muốn.
3. Muốn thay một cơ chế, phải **chủ động tắt/không tạo cơ chế cũ** theo cách cấu hình hỗ trợ, rồi đảm bảo filter mới có luồng success/failure, lưu SecurityContext, chiến lược session và CSRF phù hợp.
4. Filter custom cần có lý do rõ ràng. Nếu mục tiêu chỉ là xác minh mật khẩu, chuyển đổi credentials hay cấp authorities, đôi khi **AuthenticationProvider**, **AuthenticationConverter** hoặc cấu hình Spring Security có sẵn là điểm mở rộng phù hợp hơn.
5. Nếu mục tiêu là JWT/OAuth2 bearer token thông thường, ưu tiên **oauth2ResourceServer** với các extension point chính thức trước khi viết filter đọc Authorization header từ đầu.
6. Không lấy addFilterAt làm “mẹo” sửa sai thứ tự filter. Khi chỉ cần thêm tracing, đo thời gian hoặc đọc context, **addFilterBefore/addFilterAfter** diễn đạt ý định rõ hơn và dễ kiểm thử hơn.

### Một hiểu nhầm nguy hiểm

Giả định sai: “Gọi addFilterAt(CustomFilter, BasicAuthenticationFilter.class) thì BasicAuthenticationFilter bị thay thế”.

**Thực tế:** cả hai có thể cùng tồn tại ở thứ tự tương đương. Thứ tự giữa chúng không được đảm bảo. Nếu CustomFilter ngắt chain, Basic có thể không chạy; nếu Basic đi trước, CustomFilter có thể không nhận đúng tình huống cần xử lý. Không dùng cách này để ép cơ chế cũ biến mất.

Nếu ứng dụng chỉ cần tùy biến cách xác thực Basic, nên xem xét cấu hình **AuthenticationProvider/UserDetailsService/PasswordEncoder** và handler được hỗ trợ trước.

## 8. Tránh đăng ký filter hai lần

Với Spring Boot, mã sau có nguy cơ chạy filter **ngoài** SecurityFilterChain nếu bạn đồng thời chèn nó bằng HttpSecurity:

~~~java
@Component
public class MyFilter extends OncePerRequestFilter {
    // ...
}
~~~

Nguyên nhân: **@Component** khiến MyFilter trở thành bean kiểu Filter. Spring Boot có thể tự đăng ký nó với Servlet container, trong khi **http.addFilterBefore(myFilter, ...)** lại đăng ký instance vào security chain. Kết quả có thể là hai đường thực thi hoặc tác dụng ngoài phạm vi matcher; OncePerRequestFilter không phải giải pháp bảo đảm bạn luôn đúng vị trí khi đăng ký trùng.

### Cách an toàn nhất cho ví dụ nhỏ

Tạo filter trực tiếp trong SecurityFilterChain:

~~~java
http.addFilterBefore(
    new BeforeBasicFilter(),
    BasicAuthenticationFilter.class);
~~~

Không gắn @Component hay @Bean lên class filter đó. Đây là cách ví dụ chạy được ở phần 5 đang làm.

### Khi thật sự cần dependency injection

Nếu custom filter phải được quản lý như một Spring bean vì cần service khác, có thể đăng ký một **FilterRegistrationBean** và tắt đăng ký Servlet tự động, rồi vẫn gắn filter trong SecurityFilterChain:

~~~java
@Bean
FilterRegistrationBean<MyFilter> disableServletRegistration(MyFilter filter) {
    FilterRegistrationBean<MyFilter> registration =
        new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}
~~~

Đoạn mã trên **chỉ minh họa thủ thuật đăng ký**, chưa độc lập biên dịch nếu chưa có lớp MyFilter và các import thích hợp. Khi áp dụng cần import org.springframework.boot.web.servlet.FilterRegistrationBean, định nghĩa bean MyFilter và thêm đúng instance ấy bằng HttpSecurity vào chain. Không tạo thêm một instance khác không cần thiết.

Một lựa chọn đơn giản khác là truyền service vào **@Bean SecurityFilterChain** và tự tạo filter bằng new CustomFilter(service), không xuất filter thành bean riêng. Mục tiêu là có một nơi kiểm soát rõ ràng vị trí chạy của filter.

## 9. Tương tác với nhiều SecurityFilterChain

Một ứng dụng có thể có hai chính sách:

- Các endpoint /api/** dùng HTTP Basic hoặc bearer token và stateless.
- Các trang web còn lại dùng session/form login.

Khi đó, mỗi **SecurityFilterChain** có matcher và thứ tự riêng. **addFilterBefore/After/At** chỉ ảnh hưởng chain được gọi. Nếu cần chung filter cho cả hai chain, bạn phải thiết kế việc gắn vào từng chain phù hợp; không cho rằng một lần gắn tự bao phủ tất cả URL.

Với nhiều chain, Spring Security chọn **chain đầu tiên khớp** request. Nếu một request không khớp chain nào và không có fallback, nó có thể không được các filter Security chain ấy bảo vệ. Thiết kế matcher rõ ràng và kiểm chứng các URL nhạy cảm.

Không nên dùng filter global từ Servlet container để “vá” một chain security bị sai matcher, vì phạm vi, thứ tự và cơ chế exception/security context có thể khác.

## 10. Những sai lầm về thứ tự và ngữ nghĩa bảo mật

### Sai lầm 1 — Đọc Authentication quá sớm

Đặt filter trước Basic rồi mong getAuthentication() luôn trả user của HTTP Basic hiện tại là không đúng. Credentials chưa được Basic xử lý tại vị trí đó.

**Sửa:** đặt sau filter xác thực tương ứng, hoặc sử dụng listener/handler chính thức nếu cần tín hiệu thành công/thất bại của xác thực.

### Sai lầm 2 — Đặt filter quá muộn để sửa request

Nếu mục đích là thêm thông tin cần cho bước xác thực, đặt filter sau bước đó không giúp nó xử lý lại request đã qua. Ngược lại, đặt filter quá sớm và tin vào Authentication chưa có cũng sai.

**Sửa:** xác định chính xác dữ liệu mà filter cần đọc và filter nào tạo dữ liệu ấy, rồi chọn trước/sau mốc tương ứng.

### Sai lầm 3 — Tin addFilterAt sẽ ghi đè

addFilterAt không thay instance sẵn có. Nếu hai filter chung vị trí, thứ tự không bảo đảm.

**Sửa:** cấu hình cơ chế cũ chủ động và cân nhắc khả năng mở rộng chính thức; chỉ dùng cùng vị trí khi nắm chắc toàn bộ chain.

### Sai lầm 4 — Chọn filter class không có order đăng ký

Tự chọn một lớp Filter làm anchor mà Spring Security không nhận biết có thể khiến HttpSecurity không thể xác định thứ tự.

**Sửa:** dùng lớp anchor trong danh sách filter chuẩn có order hoặc tự thiết lập thứ tự qua cơ chế hỗ trợ; xác minh chain lúc startup.

### Sai lầm 5 — Quên chain.doFilter hoặc gọi hai lần

Khi filter chỉ quan sát request, **chain.doFilter(...) thường phải được gọi chính xác một lần**. Bỏ gọi sẽ dừng cả chuỗi; gọi hai lần có thể gây tác dụng không mong muốn.

**Sửa:** xác định rõ filter này là quan sát hay chủ động từ chối request. Nếu từ chối, thiết kế status/body và cơ chế xử lý exception nhất quán. Đừng chặn tùy tiện ngay giữa các bước bảo mật.

### Sai lầm 6 — Lẫn filter bảo mật với Servlet filter toàn cục

Thêm @Component vào filter rồi thêm bằng HttpSecurity có thể tạo nhiều đường đăng ký. Filter global còn có thể chạy trên path không khớp security chain.

**Sửa:** quản lý vòng đời và vị trí filter rõ ràng; với filter chỉ phục vụ Spring Security, giữ nó trong chain.

### Sai lầm 7 — Log bí mật khi “debug”

Filter được đặt gần xác thực rất dễ nhìn thấy password, Authorization header, cookie và token nhạy cảm.

**Sửa:** chỉ log thông tin tối thiểu như request ID, method, path đã kiểm soát và outcome phù hợp; che hoặc không log các credential. Không phản chiếu principal/token ra response header trong production.

### Sai lầm 8 — Cho rằng OncePerRequestFilter luôn chạy đúng một lần theo toàn bộ vòng đời HTTP

Một request có thể trải qua dispatch kiểu REQUEST, ASYNC hoặc ERROR. Hành vi của OncePerRequestFilter phụ thuộc dispatch và các phương thức shouldNotFilterAsyncDispatch/shouldNotFilterErrorDispatch. Không dùng lời hứa “chính xác một lần trên mọi đường thực thi” làm nền tảng an toàn.

**Sửa:** xác định dispatch type cần hỗ trợ, kiểm thử trường hợp async/error nếu ứng dụng sử dụng.

## 11. Chẩn đoán khi custom filter không chạy hoặc chạy sai lúc

Thực hiện các bước sau theo thứ tự:

1. **SecurityConfig có được Spring quét không?** Kiểm tra package, @Configuration, @Bean SecurityFilterChain và việc ứng dụng khởi động.
2. **Request có khớp SecurityFilterChain chứa filter không?** Xem securityMatcher, thứ tự các chain và path thực tế.
3. **Anchor được chọn là lớp nào?** Kiểm tra lớp mốc có order được Spring Security nhận biết, và filter mốc có thật sự đang bật trong chain không.
4. **Filter đã được đăng ký qua đâu?** Kiểm tra có @Component/@Bean, FilterRegistrationBean hoặc đăng ký Servlet container trùng không.
5. **Một filter trước đó có từ chối request không?** Nếu HTTP Basic xử lý sai credentials và trả 401, filter sau nó không nhất thiết chạy.
6. **Có logic shouldNotFilter không?** Nếu có, điều kiện bỏ qua có đúng URL/method/dispatch không?
7. **Bạn đang quan sát đúng giai đoạn không?** “Sau Basic” có thể chưa phải “sau authorization”; 200/401/403 cần được hiểu theo các filter phía sau.
8. **Phản hồi đã commit chưa?** Nếu code chèn filter tự ghi body/flush quá sớm, các filter/handler phía sau có thể không thể sửa HTTP status/header được nữa.

Trong môi trường phát triển, có thể tạm bật DEBUG của org.springframework.security để xem chain và quyết định authorization. Không ghi Authorization header, mật khẩu hoặc session token vào log.

## 12. Bài tập tự thực hành

### Bài tập A — Đổi vị trí, quan sát khác biệt

Chuyển vị trí của AfterBasicFilter từ:

~~~java
http.addFilterAfter(new AfterBasicFilter(),
                    BasicAuthenticationFilter.class);
~~~

sang:

~~~java
http.addFilterBefore(new AfterBasicFilter(),
                     BasicAuthenticationFilter.class);
~~~

Chạy lại GET /me có Basic credentials. Quan sát X-Demo-After-Basic và giải thích vì sao nó có thể chuyển từ authenticated thành missing trong cấu hình stateless một request mới.

**Giải thích:** đặt trước Basic khiến filter đọc SecurityContext khi HTTP Basic chưa xác thực credentials của request. Với stateless và không có Authentication từ filter trước đó, kết quả ở vị trí ấy là missing. Tên class AfterBasicFilter chỉ còn là tên minh họa, không quyết định vị trí.

### Bài tập B — Tại sao 403 vẫn có header authenticated?

Gọi GET /admin với alice. Tại sao HTTP status là 403 nhưng X-Demo-After-Basic lại là authenticated?

**Giải thích:** Basic xác thực danh tính thành công; AuthorizationFilter phía sau từ chối vì thiếu ROLE_ADMIN. Authentication và authorization là hai quyết định khác nhau.

### Bài tập C — Đọc log khi password sai

Gọi GET /me với alice và mật khẩu sai. Giải thích tại sao BeforeBasicFilter có thể chạy mà AfterBasicFilter không chạy.

**Giải thích:** BasicAuthenticationFilter có thể xử lý AuthenticationException và gọi AuthenticationEntryPoint trực tiếp để trả 401, không chuyển điều khiển qua chain ở vị trí sau.

### Bài tập D — Đánh giá một đề xuất addFilterAt

Một đồng nghiệp thêm CustomLoginAuthenticationFilter bằng addFilterAt(..., UsernamePasswordAuthenticationFilter.class) nhưng vẫn bật formLogin. Hãy nêu ít nhất ba câu hỏi cần trả lời trước khi áp dụng.

**Gợi ý đáp án:** Có hai filter tại cùng order không? Cơ chế nào xử lý login request và success/failure? Có đang xử lý/trả kết quả không xác định vì chung vị trí? Có nên dùng AuthenticationProvider/AuthenticationConverter? Đã thiết kế lưu SecurityContext và CSRF/session chưa?

### Bài tập E — Thử thêm POST

Thêm một endpoint POST thay đổi dữ liệu, dùng HTTP Basic đúng credentials nhưng không gửi CSRF token. Có thể nhận 403 dù trước đó GET /me đã thành công. Hãy giải thích lớp bảo vệ nào chịu trách nhiệm và tại sao không nên tắt CSRF theo phản xạ.

**Gợi ý đáp án:** CSRF là lớp bảo vệ độc lập với xác thực/role; rủi ro phụ thuộc cách client tự gửi credentials, nhất là cookie/session trong browser. Cần cấu hình CSRF phù hợp với threat model.

## 13. Checklist trước khi đưa custom filter vào ứng dụng thực

- Đã xác định rõ filter giải quyết công việc gì và có thật sự cần filter mới hay không.
- Đã chọn before/after/at vì có **phụ thuộc kỹ thuật cụ thể** vào filter mốc.
- Anchor có order hợp lệ; đã xác minh filter chain thực sự được build và request khớp chain ấy.
- Không hiểu addFilterAt như thao tác replace; không vô ý giữ hai cơ chế xác thực chung một vị trí.
- Không đăng ký filter hai lần giữa Servlet container và SecurityFilterChain.
- Với filter quan sát, đã gọi chain.doFilter đúng một lần; với filter chặn request, đã thiết kế rõ outcome và exception handling.
- Không tin rằng Authentication luôn tồn tại trước filter xác thực hoặc mọi request sẽ qua filter phía sau một bước có thể chặn sớm.
- Kiểm tra 200/401/403, path được phép/từ chối, mật khẩu sai, và phạm vi nhiều security chain nếu có.
- Không log credentials, token, cookie nhạy cảm; không đưa thông tin user nhạy cảm lên response headers.
- Đã xét dispatcher type, async/error, CSRF, CORS và vòng đời SecurityContext trong hoàn cảnh ứng dụng thực tế.

**Ghi nhớ:** **addFilterBefore** phù hợp khi xử lý cần diễn ra *trước* một mốc, **addFilterAfter** khi cần chạy *sau* mốc, và **addFilterAt** khi cố ý dùng *cùng order* với mốc. Vị trí filter quyết định lúc dữ liệu bảo mật trở nên sẵn có, nhưng không thay đổi nguyên tắc xác thực, phân quyền và bảo vệ HTTP phải được cấu hình bằng những cơ chế thích hợp của Spring Security.
