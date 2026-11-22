# Nguyên tắc chỉ chọn chuỗi đầu tiên khớp một yêu cầu trong Spring Security Servlet

Bài học thuộc chủ đề **Kiến trúc bộ lọc** của Spring Security trên Servlet. Mục tiêu là hiểu cách <code>FilterChainProxy</code> quyết định <code>SecurityFilterChain</code> nào xử lý một HTTP request, vì sao thứ tự các chuỗi quan trọng và cách kiểm thử để tránh bỏ sót bảo vệ endpoint. Ví dụ dùng Java 17+, Spring Boot 3.3.x và Spring Security 6.x.

## 1. Một request đi qua FilterChainProxy như thế nào?

Ứng dụng Servlet thường có một chuỗi các Servlet Filter do container quản lý. Spring Security đăng ký một <code>DelegatingFilterProxy</code>, trỏ tới bean tên <code>springSecurityFilterChain</code>. Bean này thường là <code>FilterChainProxy</code> và nắm giữ danh sách các <code>SecurityFilterChain</code> do cấu hình bảo mật tạo ra.

~~~text
Client gửi HTTP request
        |
Servlet container filter chain
        |
DelegatingFilterProxy -> bean "springSecurityFilterChain"
        |
   FilterChainProxy
        |
        +-- Chain A: matcher /api/admin/**  (@Order(1))
        +-- Chain B: matcher /api/**        (@Order(2))
        +-- Chain C: matcher mọi request   (@Order(3))
        |
        v
 Chỉ security filters của CHAIN ĐẦU TIÊN KHỚP
        |
 DispatcherServlet / Controller
~~~

Mỗi <code>SecurityFilterChain</code> gồm **một RequestMatcher** quyết định request thuộc chuỗi này hay không và **danh sách Security Filter** sẽ chạy khi chuỗi đó được chọn. Ví dụ chuỗi API có HTTP Basic, còn chuỗi trang web dùng form login. Chúng có thể có các tập filter và chính sách xử lý khác nhau.

Ba khái niệm dễ nhầm:
- **Servlet container filter chain** là tuyến filter cấp Servlet; trong đó có thể có filter không thuộc Spring Security.
- **FilterChainProxy** chọn một SecurityFilterChain theo matcher và thứ tự cấu hình.
- **SecurityFilterChain** được chọn cung cấp các security filter cho request đó.

Thứ tự **giữa nhiều SecurityFilterChain** không phải thứ tự **filter bên trong một SecurityFilterChain**. <code>@Order</code> của bean chain giải quyết vấn đề thứ nhất; cách Spring Security sắp xếp các filter và các API như <code>addFilterBefore</code> giải quyết vấn đề thứ hai.

## 2. Thuật toán first match: chỉ chọn chuỗi đầu tiên khớp

Giả sử <code>FilterChainProxy</code> đang có các SecurityFilterChain theo thứ tự ưu tiên.

1. Kiểm tra <code>matches(request)</code> của chain thứ nhất.
2. Nếu <code>false</code>, chuyển sang chain tiếp theo.
3. Nếu <code>true</code>, chọn **ngay chain hiện tại** và dừng tìm kiếm.
4. Chỉ chạy security filter của chain đã chọn; không cộng dồn filter của những chain khác.

Mã giả dưới đây mô tả nguyên tắc, không phải API ứng dụng hay bản sao mã nguồn Spring Security:

~~~java
for (SecurityFilterChain chain : orderedChains) {
    if (chain.matches(request)) {
        runSecurityFiltersFromSelectedChain(chain, request);
        return; // Không thử chain tiếp theo.
    }
}
continueServletChainWithoutMatchingSpringSecurityChain(request);
~~~

**Ba kết luận quan trọng:**

- Một request có thể **khớp nhiều matcher**, nhưng chỉ **chain khớp sớm nhất** được chọn. Spring Security không tìm matcher dài nhất/cụ thể nhất một cách tự động.
- Nếu chain đã chọn trả 401 (chưa xác thực) hoặc 403 (không đủ quyền), <code>FilterChainProxy</code> **không thử lại bằng chain phía sau**. Authentication và authorization xảy ra sau bước chọn chain.
- Nếu **không có SecurityFilterChain nào khớp**, request sẽ không đi qua các security filter của danh sách đó. Phần còn lại của Servlet container chain vẫn có thể chạy. Đừng mặc định các URL nằm ngoài matcher sẽ tự bị Spring Security chặn.

Ví dụ danh sách:

| Độ ưu tiên | Matcher | Mục đích |
| --- | --- | --- |
| 1 | <code>/api/admin/**</code> | API quản trị có cơ chế bảo mật chuyên biệt |
| 2 | <code>/api/**</code> | Các API khác |
| 3 | Bất kỳ request nào | Trang web và các URL còn lại |

<code>/api/admin/reports</code> khớp cả ba nhưng chọn chain 1. <code>/api/orders</code> không khớp chain 1, chọn chain 2. <code>/account</code> chọn chain 3. Nếu chain 3 được đặt lên đầu và dùng matcher mọi request, chain 1 và 2 hầu như sẽ không bao giờ được chọn.

## 3. Phân biệt securityMatcher và requestMatchers trong authorizeHttpRequests

Đây là nguồn nhầm lẫn phổ biến nhất khi cấu hình nhiều chain.

| Cấu hình | Phạm vi hoạt động | Ý nghĩa |
| --- | --- | --- |
| <code>http.securityMatcher("/api/**")</code> | **Cấp chọn SecurityFilterChain** | Chỉ request khớp <code>/api/**</code> mới có thể chọn chain này. |
| <code>http.securityMatchers(...)</code> | **Cấp chọn SecurityFilterChain** | Cấu hình thêm các matcher thuộc phạm vi toàn chain. |
| <code>authorizeHttpRequests(a -> a.requestMatchers(...))</code> | **Bên trong chain đã được chọn** | Định nghĩa quyền cho URL/điều kiện request thuộc chain. |
| <code>authorizeHttpRequests(a -> a.anyRequest()...)</code> | **Bên trong chain đã được chọn** | Luật phân quyền còn lại, không mở rộng matcher của chain ra toàn ứng dụng. |

Hai tầng áp dụng first match ở hai thời điểm khác nhau:

~~~text
Tầng 1: chọn SecurityFilterChain
    @Order(1) matcher /api/** ?       YES -> chọn API chain
    @Order(2) matcher mọi request ?   KHÔNG XÉT TIẾP

Tầng 2: bên trong API chain đã chọn
    requestMatchers("/api/public") ?      NO
    requestMatchers("/api/admin/**") ?    YES -> yêu cầu role ADMIN
    anyRequest().authenticated()          KHÔNG XÉT TIẾP
~~~

Ở tầng 2, thứ tự các rule trong <code>authorizeHttpRequests</code> cũng quan trọng: rule khớp đầu tiên quyết định yêu cầu phân quyền. Ví dụ <code>requestMatchers("/api/admin/**").hasRole("ADMIN")</code> nên đứng trước <code>anyRequest().authenticated()</code> trong cùng chain. Đây vẫn là **một** SecurityFilterChain, không phải hai.

Xét đoạn sau:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public").permitAll()
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

<code>/api/public</code> vẫn đi qua các security filter của chain API, dù luật phân quyền cho phép truy cập công khai. Ngược lại, <code>/orders</code> không thuộc phạm vi <code>/api/**</code>, nên luật <code>anyRequest().authenticated()</code> ở API chain không hề bảo vệ nó.

## 4. @Order quyết định trình tự xét chain

<code>@Order(1)</code> ưu tiên trước <code>@Order(2)</code>; số nhỏ hơn được xét trước. Spring Security dùng danh sách chain đã được sắp xếp và kết quả matcher, chứ không đo độ đặc hiệu của URL để tự chọn chain tốt nhất.

Khi các vùng bảo vệ chồng lấn, đặt **chain hẹp trước chain rộng**. Chỉ tạo nhiều chain khi cần cơ chế khác nhau như API dùng HTTP Basic/token và trang web dùng form login; nếu chỉ cần quyền khác nhau cho URL, một chain với nhiều rule <code>authorizeHttpRequests</code> thường dễ quản lý hơn.

Nếu <code>HttpSecurity</code> không khai báo <code>securityMatcher</code> riêng, matcher mặc định bao phủ mọi request. Vì vậy, một chain dạng này nên nằm cuối trong thiết kế nhiều chain để giữ vai trò dự phòng. Không nên dựa vào thứ tự ngẫu nhiên của nhiều bean không ghi rõ ưu tiên khi chúng có matcher chồng lấn.

## 5. Ví dụ Java 17+ chạy được: API HTTP Basic và trang web form login

Dự án demo dùng **Spring Boot 3.3.5**, Maven và Jakarta Servlet. Chúng ta tạo hai SecurityFilterChain: API chain hẹp đứng đầu, web chain mặc định bao phủ phần còn lại. Các tài khoản chỉ phục vụ học tập, không áp dụng nguyên trạng cho production.

Cấu trúc:

~~~text
first-match-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/firstmatch/
    │   ├── FirstMatchApplication.java
    │   └── SecurityConfiguration.java
    └── test/java/com/example/firstmatch/
        └── SecurityChainTest.java
~~~

**<code>pom.xml</code>:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>first-match-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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
~~~

**<code>src/main/java/com/example/firstmatch/FirstMatchApplication.java</code>:**

~~~java
package com.example.firstmatch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class FirstMatchApplication {
    public static void main(String[] args) {
        SpringApplication.run(FirstMatchApplication.class, args);
    }

    @GetMapping("/api/public")
    public String apiPublic() { return "api-public"; }

    @GetMapping("/api/data")
    public String apiData() { return "api-data"; }

    @GetMapping("/api/admin/report")
    public String apiAdmin() { return "api-admin-report"; }

    @GetMapping("/public")
    public String publicPage() { return "web-public"; }

    @GetMapping("/account")
    public String account() { return "web-account"; }

    @GetMapping("/admin/report")
    public String webAdmin() { return "web-admin-report"; }
}
~~~

**<code>src/main/java/com/example/firstmatch/SecurityConfiguration.java</code>:**

~~~java
package com.example.firstmatch;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**") // Matcher của toàn API chain.
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
            // Matcher mặc định khớp mọi request còn lại.
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("viewer")
                .password(encoder.encode("viewer-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

Giải thích dòng quan trọng:

- <code>apiChain</code> có <code>@Order(1)</code> và <code>securityMatcher("/api/**")</code>: mọi URL API phù hợp đi vào chain này trước khi web chain có cơ hội xét.
- <code>webChain</code> có <code>@Order(2)</code>, không cấu hình matcher riêng: đây là chain bao phủ các request còn lại. Trang login mặc định <code>/login</code> cũng thuộc web chain.
- API chain dùng HTTP Basic; với <code>SessionCreationPolicy.STATELESS</code>, Spring Security không dùng HttpSession để lưu/lấy SecurityContext của API request. Điều này không tự chứng minh rằng **mọi** thành phần Servlet trong ứng dụng không bao giờ tạo HttpSession.
- Web chain dùng form login; các URL admin của web yêu cầu role <code>ADMIN</code>.
- Cấu hình không tắt CSRF toàn cục. Ví dụ chỉ khảo sát các request GET. Các thao tác thay đổi trạng thái cần chính sách CSRF thích hợp với cơ chế xác thực của từng chain.

## 6. Dự đoán kết quả và thử bằng curl

Bảng sau cho thấy chain được chọn trước, sau đó mới đến rule phân quyền:

| Request | Chain được chọn | Authorization | Kết quả dự kiến |
| --- | --- | --- | --- |
| <code>GET /api/public</code> | API | <code>permitAll</code> | 200, <code>api-public</code> |
| <code>GET /api/data</code> không có credentials | API | Cần xác thực | 401, thử HTTP Basic |
| <code>GET /api/data</code> với viewer | API | <code>authenticated</code> | 200, <code>api-data</code> |
| <code>GET /api/admin/report</code> với viewer | API | Cần ADMIN | 403 |
| <code>GET /api/admin/report</code> với admin | API | Cần ADMIN | 200, <code>api-admin-report</code> |
| <code>GET /public</code> | Web | <code>permitAll</code> | 200, <code>web-public</code> |
| <code>GET /account</code> chưa login | Web | Cần xác thực | 302 tới trang login |
| <code>GET /login</code> | Web | Trang login mặc định | 200, form login |

Chạy trong thư mục chứa <code>pom.xml</code>:

~~~bash
mvn test
mvn spring-boot:run
~~~

Trong terminal thứ hai, thử:

~~~bash
# API public.
curl -i http://localhost:8080/api/public

# API cần đăng nhập: thiếu Basic credentials -> 401.
curl -i http://localhost:8080/api/data

# Viewer hợp lệ -> 200.
curl -i -u viewer:viewer-pass http://localhost:8080/api/data

# Viewer chưa có role ADMIN -> 403.
curl -i -u viewer:viewer-pass http://localhost:8080/api/admin/report

# Admin -> 200.
curl -i -u admin:admin-pass http://localhost:8080/api/admin/report

# Web công khai -> 200.
curl -i http://localhost:8080/public

# Web riêng tư -> redirect sang /login.
curl -i http://localhost:8080/account
~~~

<code>curl -i</code> hiển thị HTTP status và response headers. Mặc định curl không tự theo redirect nếu không có <code>-L</code>, vì vậy thấy phản hồi 302 từ web chain là bình thường. API trả 401 với HTTP Basic khi thiếu credentials; web chain sử dụng đường dẫn login của form login. Sự khác biệt này xuất phát từ **chain đầu tiên khớp**, không phải từ việc chạy cả hai chain.

Đáng chú ý: request <code>/api/admin/report</code> cũng khớp matcher tổng quát của web chain, nhưng khi viewer bị 403 ở API chain, Spring Security **không chuyển request sang web chain** để thử lại với form login.

## 7. Test tự động để tránh lỗi thứ tự

Tạo <code>src/test/java/com/example/firstmatch/SecurityChainTest.java</code>:

~~~java
package com.example.firstmatch;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityChainTest {

    @Autowired
    MockMvc mvc;

    @Test
    void apiChainIsSelectedBeforeWebChain() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("api-public"));

        mvc.perform(get("/api/data"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/data").with(httpBasic("viewer", "viewer-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("api-data"));

        mvc.perform(get("/api/admin/report")
                .with(httpBasic("viewer", "viewer-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin/report")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("api-admin-report"));
    }

    @Test
    void nonApiRequestsUseWebChain() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("web-public"));

        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

Chạy <code>mvn test</code> để kiểm tra trạng thái HTTP và body. Các test cho cả API và web chứng minh hành vi của từng chuỗi đã được cấu hình; khi ứng dụng lớn hơn, bổ sung test âm cho các URL nằm sát ranh giới matcher và các route phân quyền quan trọng. Phần mã trên được soạn để chạy độc lập với bộ dependency đã nêu; status thực tế cũng phụ thuộc cấu hình bổ sung nếu bạn tích hợp vào ứng dụng có sẵn.

## 8. Lỗi số một: catch-all ở trước chain chuyên biệt

Xét cấu hình sai (chỉ dùng để phân tích, không triển khai):

~~~java
@Bean
@Order(1)
SecurityFilterChain overlyBroad(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a.anyRequest().permitAll())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain intendedApi(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Với <code>GET /api/secret</code>, chuỗi đầu tiên có matcher mặc định khớp mọi request, nên được chọn lập tức. Rule <code>permitAll()</code> của chuỗi này cho phép đi tiếp. Chuỗi API đứng sau sẽ **không được xét**, dù có matcher <code>/api/**</code> và yêu cầu xác thực. Đây là lỗi có thể khiến endpoint được bảo vệ yếu hơn dự định.

**Cách sửa:** đặt API chain (matcher hẹp) trước, chain tổng quát cuối. Nếu không cần hai tập filter khác nhau, thay thế bằng một chain duy nhất có rule phân quyền chính xác.

## 9. Lỗi số hai: các matcher chồng lấn nhưng rule bảo mật khác nhau

Giả sử thứ tự:

~~~text
@Order(1): matcher /api/**       -> user đăng nhập đều được phép
@Order(2): matcher /api/admin/** -> chỉ role ADMIN
~~~

Request <code>/api/admin/report</code> được chain 1 nhận trước. Chain 2 không thể bổ sung điều kiện ADMIN; nếu chain 1 cho phép USER thì USER được qua. Đổi lại, nếu chain 1 từ chối request bằng 403, chain 2 cũng không được thử.

Có hai cách thiết kế:

**Cách A: Một chain cho toàn bộ API** nếu chỉ phân biệt quyền.

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(a -> a
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
~~~

**Cách B: Hai chain thực sự cần cơ chế filter khác nhau**, với matcher hẹp trước:

~~~text
@Order(1) /api/admin/**   -> admin SecurityFilterChain
@Order(2) /api/**         -> API SecurityFilterChain
@Order(3) mọi request     -> web SecurityFilterChain
~~~

Trong cách B, phải kiểm thử cả các URL admin và API thường. Spring Security không tự nâng chain <code>/api/admin/**</code> lên trước chỉ vì matcher cụ thể hơn.

## 10. Không có chain nào khớp: khoảng trống nguy hiểm

Giả sử toàn ứng dụng chỉ khai báo:

~~~java
@Bean
SecurityFilterChain onlyApi(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

<code>/api/orders</code> có chain bảo vệ. Nhưng <code>/billing</code> không khớp <code>/api/**</code>, vì vậy không đi qua các security filter của chain duy nhất này. <code>anyRequest().authenticated()</code> nằm **bên trong API chain**, nên không thể bảo vệ <code>/billing</code> bằng cách “vươn ra ngoài” matcher.

Khi bạn định nghĩa bean <code>SecurityFilterChain</code> riêng, không nên mặc định Spring Boot sẽ tự động chèn thêm một chain catch-all để bọc mọi URL còn lại. Nếu tất cả endpoint phải được Spring Security xử lý, thêm một chain phù hợp cuối cùng và xác định luật truy cập cho nó.

Điều này khác với một route **có chain khớp nhưng được <code>permitAll()</code>**. Route đó vẫn đi qua các security filter của chain đã chọn.

## 11. PermitAll, web.ignoring và first match

Các cấu hình này khác nhau về tác động:

| Trường hợp | Spring Security filter của chain có chạy? | Ý nghĩa |
| --- | --- | --- |
| <code>requestMatchers("/public").permitAll()</code> trong chain đã chọn | Có | Cho phép request qua bước phân quyền, nhưng các filter khác như security headers vẫn có thể áp dụng. |
| Cấu hình bỏ qua qua <code>web.ignoring()</code> | Không cho URL được bỏ qua | Chủ ý bỏ qua các security filter trong <code>FilterChainProxy</code> cho URL đó. |
| Request không khớp bất kỳ chain nào | Không | Không có chain được chọn để thực thi các security filter của danh sách. |

Thông thường với một trang công khai, <code>permitAll()</code> trong chain thích hợp là lựa chọn rõ ràng hơn nếu vẫn cần các cơ chế bảo mật áp dụng trên toàn ứng dụng. Không dùng chain <code>/**</code> với <code>permitAll()</code> ở đầu rồi kỳ vọng API chain phía dưới vẫn chạy.

## 12. Đường dẫn login và bộ lọc xác thực cũng phải nằm trong chain thích hợp

Một điểm cần kiểm tra khi chain có <code>securityMatcher("/api/**")</code>: matcher đó cũng giới hạn **các endpoint do security filter xử lý**. Ví dụ nếu bạn cấu hình <code>formLogin()</code> nhưng URL login mặc định là <code>/login</code>, đường dẫn <code>/login</code> không thuộc <code>/api/**</code>. Do đó chain API không tự xử lý được trang và điểm gửi login tại URL nằm ngoài phạm vi của nó.

Trong ví dụ của bài, web chain bao phủ <code>/login</code>, vì thế <code>formLogin</code> hoạt động cho phần web. Nếu bạn cần một cơ chế login riêng trong API chain, hãy thiết kế URL và matcher của toàn chain sao cho mọi request cần đến filter xử lý đều nằm trong phạm vi phù hợp.

Phân biệt thêm: <code>securityMatcher</code> ảnh hưởng việc **chọn chuỗi**, còn thiết lập <code>addFilterBefore</code>/<code>addFilterAfter</code> chỉ thay đổi thứ tự filter **trong chính chuỗi ấy**; nó không khiến một chain đang bị che khuất được ưu tiên.

## 13. Chẩn đoán chain được chọn trong ứng dụng

Khi một API trả 302 thay vì 401, hay một endpoint bất ngờ thành public, kiểm tra theo thứ tự:

1. Liệt kê **tất cả bean SecurityFilterChain và thứ tự** của chúng; xem có chain mặc định/catch-all nào đứng quá sớm hay không.
2. Ghi ra matcher cấp chain: <code>securityMatcher</code>, <code>securityMatchers</code>, hoặc matcher mặc định. Phân biệt chúng với <code>requestMatchers</code> ở tầng authorization.
3. Với từng request nghi vấn, duyệt matcher từ ưu tiên cao xuống và **dừng ở matcher đầu tiên trả true**.
4. Sau khi xác định chain, mới xem danh sách filter và các luật xác thực/phân quyền bên trong chain được chọn.
5. Viết MockMvc/integration test để khóa hành vi đã dự kiến, đặc biệt tại các URL chồng lấn và URL không khớp chain nào.

Trong môi trường phát triển có thể tạm bật log:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Xem log khi gọi các URL thuộc từng chain. Nội dung log chi tiết thay đổi theo phiên bản và cấu hình; không dựa vào một chuỗi log cố định. Tránh bật TRACE trong production lâu dài, đặc biệt khi log có thể chứa thông tin xác thực/phiên.

Nếu cần đánh giá chính xác matcher, nhớ rằng việc so khớp có thể xét HTTP method và quy tắc xử lý đường dẫn của loại <code>RequestMatcher</code> thực tế; context path, servlet path và cách dùng MVC matcher có thể ảnh hưởng phạm vi. Không chỉ nhìn tên endpoint và đoán matcher theo chuỗi ký tự.

## 14. Các lỗi phổ biến

| Lỗi cấu hình/tư duy | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Đặt matcher <code>/**</code> trước <code>/api/**</code> | API chain bị che khuất | Đưa chain hẹp lên trước, catch-all cuối |
| Đặt <code>/api/**</code> trước <code>/api/admin/**</code> khi cần hai tập filter khác nhau | Admin chain có thể không chạy | Đảo thứ tự hoặc dùng một chain với rule admin |
| Nghĩ <code>requestMatchers</code> chọn SecurityFilterChain | Hiểu sai phạm vi bảo vệ | Dùng <code>securityMatcher</code> ở tầng chain |
| Tưởng 403 sẽ fallback sang chain sau | Đánh giá sai chính sách quyền | Chỉ xử lý trong chain đầu tiên khớp |
| Không có chain cuối cho URL khác | Có endpoint không nhận security filter Spring Security | Thêm chain bao phủ phần còn lại khi cần |
| Để login URL ngoài phạm vi matcher chain phụ trách login | Endpoint login không được filter đó xử lý | Thiết kế lại URL/matcher và xác minh bằng test |
| Tạo nhiều chain chỉ để khác role | Dễ chồng lấn và khó duy trì | Dùng các rule authorize trong cùng chain |
| Không test các đường dẫn có thể khớp nhiều matcher | Thay đổi nhỏ có thể tạo lỗ hổng | Kiểm thử cả đường dẫn hẹp, rộng và ngoài phạm vi |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Có <code>@Order(1) /api/**</code> và <code>@Order(2) /**</code>. Request <code>/api/orders</code> chạy qua mấy SecurityFilterChain?  
**Trả lời:** Một: chain <code>/api/**</code>, vì khớp trước. Không ghép các filter của chain tổng quát vào sau.

**Câu 2.** Request đã khớp chain 1 nhưng nhận 403. Framework có thử lại chain 2 không?  
**Trả lời:** Không. 403 là kết quả xử lý của chain đã chọn, không kích hoạt chọn lại.

**Câu 3.** <code>anyRequest().authenticated()</code> trong chain giới hạn <code>/api/**</code> có bảo vệ <code>/account</code> không?  
**Trả lời:** Không. <code>/account</code> nằm ngoài matcher của chain; cần chain khác phù hợp.

**Câu 4.** Vì sao <code>@Order</code> quan trọng ngay cả khi matcher hẹp hơn?  
**Trả lời:** Spring Security ưu tiên thứ tự khai báo/sắp xếp các chain; nó không tự chọn matcher “cụ thể nhất”.

**Câu 5.** Một URL <code>permitAll()</code> trong chain đã chọn có hoàn toàn bỏ qua Spring Security không?  
**Trả lời:** Không. Các security filter của chain vẫn chạy; <code>permitAll</code> chỉ là quyết định tại tầng phân quyền.

**Ghi nhớ:** <code>FilterChainProxy</code> **chọn SecurityFilterChain đầu tiên có RequestMatcher khớp request**. Sau đó chỉ các security filter của chain ấy xử lý request và các rule <code>authorizeHttpRequests</code> của chain ấy quyết định quyền. Thiết kế thứ tự matcher đúng và kiểm thử các vùng chồng lấn là cách tránh lỗ hổng khi cấu hình nhiều chuỗi.
