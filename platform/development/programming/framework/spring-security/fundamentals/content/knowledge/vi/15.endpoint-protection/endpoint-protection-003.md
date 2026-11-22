# Yêu cầu đăng nhập và yêu cầu quyền cụ thể cho từng nhóm endpoint trong Spring Security

## 1. Mục tiêu

Một ứng dụng thường có nhiều nhóm endpoint: thông tin công khai, hồ sơ người dùng đã đăng nhập, API đọc báo cáo, API cập nhật dữ liệu và khu vực quản trị. Đặt toàn bộ hệ thống dưới một quy tắc **authenticated()** chưa đủ: nhân viên chỉ được đọc báo cáo có thể không được cập nhật báo cáo, còn người dùng bình thường không được vào chức năng quản trị.

Bài học này hướng dẫn thiết kế và cấu hình **authorization theo URL + HTTP method + quyền**, tập trung vào các câu hỏi:

- Endpoint nào không cần đăng nhập?
- Endpoint nào chỉ yêu cầu một danh tính đã xác thực?
- Endpoint nào đòi **role** hoặc **authority** cụ thể?
- Làm sao dùng các quy tắc theo **nhóm URL** mà không vô tình mở quyền cho endpoint khác?
- Vì sao thứ tự matcher, phương thức HTTP, CSRF và quy tắc cuối cùng quyết định tính an toàn?

Ví dụ chính dùng **Spring Boot 3.x + Spring Security 6.x + Spring MVC/Servlet**, Java 17+. Phần cuối chỉ ra cách chuyển ý tưởng sang WebFlux. Đây là bài về **bảo vệ endpoint**, không đi sâu vào giao thức đăng nhập hay thiết kế identity provider.

## 2. Xác thực khác phân quyền như thế nào?

**Authentication (xác thực)** trả lời: “Request này thuộc về ai; danh tính đó đã được xác minh chưa?”. Spring Security đại diện kết quả bằng **Authentication**, bao gồm principal, trạng thái authenticated và danh sách **GrantedAuthority**.

**Authorization (phân quyền)** trả lời: “Danh tính đó có được thực hiện thao tác này không?”. Các quy tắc kiểm tra authentication và authorities để quyết định có cho request đi tiếp tới endpoint hay không.

~~~text
HTTP request
   |
   v
Spring Security filter chain
   |
   +--> Authentication (đọc/kiểm tra credentials nếu cần)
   |         |
   |         +--> Authentication với principal, authorities
   |
   +--> Authorization (xét path, HTTP method, quy tắc yêu cầu)
             |
             +--> Được phép  --> Controller/endpoint
             |
             +--> Bị từ chối --> Exception handling (ví dụ 401/403)
~~~

Một người **đã đăng nhập** vẫn có thể **không đủ quyền**. Bởi vậy:

| Quy tắc | Ý nghĩa |
| --- | --- |
| **permitAll()** | Cho phép request không cần xác thực; các security filter khác vẫn có thể áp dụng. |
| **authenticated()** | Cần Authentication được coi là đã xác thực; không tự yêu cầu role nghiệp vụ cụ thể. |
| **hasRole("ADMIN")** | Mặc định cần GrantedAuthority **ROLE_ADMIN**. |
| **hasAuthority("report:read")** | Cần GrantedAuthority có chuỗi đúng bằng **report:read**. |
| **hasAnyRole("ADMIN", "SUPPORT")** | Cần ít nhất một trong các role tương ứng. |
| **hasAnyAuthority("report:read", "report:write")** | Cần ít nhất một trong các authority đã liệt kê. |
| **denyAll()** | Không cho phép request tương ứng; hữu ích làm quy tắc cuối cùng. |

**hasRole("ADMIN") không chỉ kiểm tra có đăng nhập**: nó còn yêu cầu quyền ROLE_ADMIN. **hasAuthority("report:read")** không tự thêm tiền tố ROLE_. Không cấp quyền bằng cách viết quy tắc; authority phải đến từ quá trình xác thực/ánh xạ quyền.

## 3. Bắt đầu từ ma trận truy cập trước khi viết mã

Ví dụ hệ thống báo cáo nội bộ có chính sách:

| Nhóm endpoint | HTTP method | Người được phép | Quy tắc dự kiến |
| --- | --- | --- | --- |
| /public/info | GET | Tất cả | permitAll() |
| /account/profile | GET | Bất kỳ người dùng đã đăng nhập | authenticated() |
| /reports/summary | GET | Người có quyền đọc báo cáo | hasAuthority("report:read") |
| /reports/summary | POST | Người có quyền ghi báo cáo | hasAuthority("report:write") |
| /admin/status | GET | Quản trị viên | hasRole("ADMIN") |
| Endpoint khác chưa khai báo | Mọi method | Không ai | denyAll() |

**Ma trận là đặc tả hành vi**, không chỉ là cách trình bày. Khi phát triển, có thể dùng nó để viết test cho cả trường hợp truy cập được và bị từ chối.

Ví dụ về bốn tài khoản:

| Tài khoản | Authorities thực tế | Ý nghĩa |
| --- | --- | --- |
| member | ROLE_USER | Đăng nhập được, không có quyền báo cáo/quản trị |
| reader | report:read | Đọc được báo cáo, không cập nhật |
| editor | report:read, report:write | Đọc và cập nhật báo cáo |
| admin | ROLE_ADMIN | Truy cập nhóm /admin/** |

**Không giả định admin tự có report:read.** Nếu nghiệp vụ muốn admin đọc báo cáo thì phải cấp thêm authority hoặc định nghĩa cơ chế kế thừa/authorization phù hợp. Trong ví dụ, chúng là những quyền độc lập.

### Vì sao phải xét cả HTTP method?

Cùng path **/reports/summary**, hai thao tác có mức rủi ro khác nhau:

- **GET** chỉ đọc kết quả.
- **POST** khởi động thao tác cập nhật hoặc tính toán lại báo cáo.

Nếu chỉ viết **requestMatchers("/reports/**").hasAuthority("report:read")**, cùng quyền đọc có thể được dùng cho POST. Để phân biệt, cần matcher kết hợp **HttpMethod.GET/POST** với path, đồng thời tính đến các method không được khai báo như PUT, PATCH hoặc DELETE. Những method không được phê duyệt phải rơi vào quy tắc từ chối.

## 4. Cách Spring Security chọn quy tắc cho request

Với Spring Security 6.x trên Servlet, API phổ biến là:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/public/info").permitAll()
        .requestMatchers(HttpMethod.GET, "/account/profile").authenticated()
        .requestMatchers(HttpMethod.GET, "/reports/**").hasAuthority("report:read")
        .requestMatchers(HttpMethod.POST, "/reports/**").hasAuthority("report:write")
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll());
~~~

Đây là **fragment cấu hình** trong một bean SecurityFilterChain, không phải chương trình độc lập.

Đối với một **SecurityFilterChain đã được chọn**, Spring Security xét các cặp **RequestMatcher → AuthorizationManager** theo **thứ tự khai báo**. Quy tắc khớp đầu tiên quyết định kiểm tra quyền. Khi một rule đã khớp nhưng quyền thiếu, Spring Security **không tiếp tục thử các rule phía sau để tìm quyền dễ hơn**.

Ví dụ:

~~~text
GET /reports/summary
   |
   +--> GET /public/info     ? không
   +--> GET /account/profile ? không
   +--> GET /reports/**      ? CÓ
             |
             +--> cần report:read
                     |
                     +--> reader có --> được phép
                     +--> member thiếu --> bị từ chối
~~~

**Đặt quy tắc cụ thể trước quy tắc bao phủ chung.** Hai cấu hình sau khác nhau rõ rệt:

~~~java
// Sai cho mục tiêu "admin cần role ADMIN":
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/**").authenticated()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll());
~~~

Quy tắc đầu đã khớp /admin/status nên rule hasRole phía sau không được áp dụng.

~~~java
// Đúng: ưu tiên vùng admin trước vùng chung:
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
~~~

Ví dụ đúng thứ hai chỉ minh họa **thứ tự**; trong API có yêu cầu deny-by-default, hãy khai báo mọi nhóm cần thiết và kết thúc bằng **anyRequest().denyAll()**.

### requestMatchers và securityMatcher khác nhau

- **http.securityMatcher(...)** quyết định request có thuộc **SecurityFilterChain này** hay không, đặc biệt khi ứng dụng có nhiều SecurityFilterChain.
- **authorizeHttpRequests(...requestMatchers(...))** chọn **quy tắc authorization bên trong SecurityFilterChain đã được áp dụng**.

Một ứng dụng cơ bản có thể dùng **một SecurityFilterChain** bảo vệ toàn bộ request; đây cũng là lựa chọn của ví dụ bên dưới. Với nhiều chain, phải sắp xếp @Order phù hợp và bảo đảm không có URL vô tình rơi ngoài tất cả chain. **anyRequest().denyAll() trong một chain không bảo vệ URL mà chain đó hoàn toàn không khớp**.

## 5. Ví dụ Spring Boot 3.x đầy đủ, có thể chạy

### 5.1. Tạo dự án

Dùng Spring Initializr tạo dự án **Gradle**, Java **17+**, Spring Boot **3.x**, group **com.example**, package **com.example.demo**, với hai dependency:

- **Spring Web** = spring-boot-starter-web
- **Spring Security** = spring-boot-starter-security

Ví dụ dùng **HTTP Basic** để dễ gửi yêu cầu bằng curl, **in-memory users** để thấy authority trực tiếp, và **REST endpoints** trả về chuỗi đơn giản.

Tạo file **src/main/java/com/example/demo/EndpointAuthorizationApplication.java** với **toàn bộ nội dung** sau:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class EndpointAuthorizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(EndpointAuthorizationApplication.class, args);
    }
}

@Configuration
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                // Chỉ dành cho demo curl cục bộ. Xem cảnh báo CSRF bên dưới.
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(session ->
                        session.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        // Nhóm công khai
                        .requestMatchers(HttpMethod.GET, "/public/info")
                            .permitAll()

                        // Nhóm chỉ cần đăng nhập
                        .requestMatchers(HttpMethod.GET, "/account/profile")
                            .authenticated()

                        // Nhóm báo cáo: đọc và ghi có quyền riêng
                        .requestMatchers(HttpMethod.GET, "/reports/**")
                            .hasAuthority("report:read")
                        .requestMatchers(HttpMethod.POST, "/reports/**")
                            .hasAuthority("report:write")

                        // Nhóm quản trị: yêu cầu ROLE_ADMIN
                        .requestMatchers("/admin/**")
                            .hasRole("ADMIN")

                        // Không mở mặc định các URL/method khác
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails member = User.withUsername("member")
                .password("{noop}demo123")
                .roles("USER")
                .build();

        UserDetails reader = User.withUsername("reader")
                .password("{noop}demo123")
                .authorities("report:read")
                .build();

        UserDetails editor = User.withUsername("editor")
                .password("{noop}demo123")
                .authorities("report:read", "report:write")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}demo123")
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(
                member, reader, editor, admin);
    }
}

@RestController
class DemoEndpoints {

    @GetMapping("/public/info")
    String info() {
        return "public-info";
    }

    @GetMapping("/account/profile")
    String profile(Authentication authentication) {
        return "hello-" + authentication.getName();
    }

    @GetMapping("/reports/summary")
    String readReport() {
        return "report-summary";
    }

    @PostMapping("/reports/summary")
    String updateReport() {
        return "report-updated";
    }

    @GetMapping("/admin/status")
    String adminStatus() {
        return "admin-ok";
    }

    @GetMapping("/unlisted")
    String unlisted() {
        return "should-not-be-visible";
    }
}
~~~

**Tại sao file này chạy được?** Java chỉ cho phép một public top-level class trùng tên file. Các class còn lại không public và nằm cùng package; Spring Boot quét các @Configuration/@RestController cùng package. Các endpoint cố ý đơn giản để tách việc **match request + kiểm tra authority** khỏi logic database/nghiệp vụ.

**Lưu ý khi chạy thử:**

- Mật khẩu **{noop}demo123** chỉ phục vụ bài học; không dùng kiểu lưu mật khẩu này trong môi trường thật.
- **csrf(AbstractHttpConfigurer::disable)** chỉ được dùng để tập lệnh curl bên dưới có thể gửi POST mà không cần cung cấp CSRF token. **Không sao chép cấu hình này một cách máy móc vào sản phẩm thật.** Ngay cả HTTP Basic cũng có thể bị trình duyệt tự gửi lại credentials; cần đánh giá CSRF theo kiểu client, cách trình duyệt gửi credentials và mô hình đe dọa. Ứng dụng trình duyệt dùng cookie/session thường phải duy trì bảo vệ CSRF phù hợp.
- **SessionCreationPolicy.STATELESS** tránh phụ thuộc phiên đăng nhập HTTP cho demo API Basic; nó **không thay thế** việc đánh giá CSRF.
- Mã ví dụ không triển khai authentication từ JWT, database hay identity provider; thực tế cần chuyển role/permission của hệ thống đó sang GrantedAuthority chính xác.

### 5.2. Khởi động và gửi request

Ở thư mục gốc dự án Gradle đã tạo:

~~~bash
./gradlew bootRun
~~~

Trên Windows, dùng **gradlew.bat bootRun**. Đợi ứng dụng chạy tại **http://localhost:8080**, sau đó dùng terminal khác:

~~~bash
# Endpoint công khai: không cần credentials
curl -i http://localhost:8080/public/info

# Endpoint chỉ cần danh tính đã xác thực
curl -i http://localhost:8080/account/profile
curl -i -u member:demo123 http://localhost:8080/account/profile

# Báo cáo: GET cần report:read
curl -i -u member:demo123 http://localhost:8080/reports/summary
curl -i -u reader:demo123 http://localhost:8080/reports/summary

# Báo cáo: POST cần report:write
curl -i -X POST -u reader:demo123 http://localhost:8080/reports/summary
curl -i -X POST -u editor:demo123 http://localhost:8080/reports/summary

# Nhóm admin
curl -i -u member:demo123 http://localhost:8080/admin/status
curl -i -u admin:demo123 http://localhost:8080/admin/status

# Endpoint tồn tại nhưng không được allowlist
curl -i -u admin:demo123 http://localhost:8080/unlisted
~~~

Trong PowerShell, **curl** có thể là alias của lệnh khác; dùng **curl.exe** thay **curl** nếu cần.

### 5.3. Kết quả HTTP dự kiến

| Request | Rule áp dụng | Kết quả dự kiến | Body khi 200 |
| --- | --- | --- | --- |
| GET /public/info, anonymous | permitAll | **200** | public-info |
| GET /account/profile, anonymous | authenticated | **401** | — |
| GET /account/profile, member | authenticated | **200** | hello-member |
| GET /reports/summary, member | hasAuthority(report:read) | **403** | — |
| GET /reports/summary, reader | hasAuthority(report:read) | **200** | report-summary |
| POST /reports/summary, reader | hasAuthority(report:write) | **403** | — |
| POST /reports/summary, editor | hasAuthority(report:write) | **200** | report-updated |
| GET /admin/status, member | hasRole(ADMIN) | **403** | — |
| GET /admin/status, admin | hasRole(ADMIN) | **200** | admin-ok |
| GET /unlisted, admin | anyRequest().denyAll() | **403** | — |

Đây là **kết quả dự kiến từ mã nguồn cấu hình**, không phải bản ghi của một lần chạy thực tế. Header, nội dung response lỗi và thông tin cổng có thể thay đổi theo môi trường. Ví dụ không có login form, nên HTTP Basic thường trả **401 Unauthorized** cho request chưa xác thực hợp lệ thay vì redirect sang trang đăng nhập.

**Vì sao admin bị 403 ở /unlisted?** Chính sách cuối cùng là denyAll, không có ngoại lệ “admin được phép tất cả”. Ngay cả khi đã xác thực thành công và có ROLE_ADMIN, endpoint ngoài danh sách được phép vẫn bị từ chối.

**Vì sao reader không POST được?** Request POST /reports/summary khớp quy tắc POST, yêu cầu report:write; quyền report:read không đủ. Việc dùng cùng path không làm hai quyền tự thay thế nhau.

## 6. Theo dõi một request qua các bước

### Trường hợp A: người chưa đăng nhập gọi /account/profile

~~~text
GET /account/profile, không Authorization header
        |
        +--> GET /public/info? không
        +--> GET /account/profile? có
                      |
                      v
                authenticated()
                      |
                      +--> không có Authentication hợp lệ
                      |
                      v
                HTTP Basic entry point -> 401
~~~

Controller profile() không được gọi.

### Trường hợp B: reader GET /reports/summary

~~~text
GET /reports/summary
Authorization: Basic credentials của reader
        |
        +--> xác thực user reader thành công
        +--> GrantedAuthority = ["report:read"]
        +--> GET /reports/** khớp
        +--> hasAuthority("report:read") đúng
        |
        v
Controller readReport() -> HTTP 200, "report-summary"
~~~

### Trường hợp C: reader POST /reports/summary

~~~text
POST /reports/summary
Authorization: Basic credentials của reader
        |
        +--> xác thực user reader thành công
        +--> GrantedAuthority = ["report:read"]
        +--> GET /reports/**? không, HTTP method khác
        +--> POST /reports/**? có
        +--> cần "report:write" nhưng thiếu
        |
        v
HTTP 403; updateReport() không được gọi
~~~

Dòng POST trong ví dụ không bị CSRF chặn trước vì bài demo **chủ động vô hiệu hóa CSRF**. Trong ứng dụng có CSRF bật, request POST có thể nhận **403 do thiếu/không hợp lệ CSRF token ngay cả khi đã có report:write**. Phải phân biệt lỗi CSRF với lỗi quyền.

### Trường hợp D: người có vai trò admin

~~~text
GET /admin/status, credentials admin
        |
        +--> UserDetails được tạo bởi roles("ADMIN")
        +--> authorities chứa "ROLE_ADMIN"
        +--> /admin/** khớp, yêu cầu hasRole("ADMIN")
        +--> mặc định hasRole("ADMIN") đòi "ROLE_ADMIN"
        |
        v
HTTP 200, "admin-ok"
~~~

Nếu hệ thống cấp authority **ADMIN** không có prefix thì hasRole("ADMIN") mặc định **không** coi là thỏa. Cần thống nhất tên quyền ở tầng chuyển đổi dữ liệu sang Authentication.

## 7. Thiết kế nhóm endpoint mà không mở quyền ngoài ý muốn

### 7.1. Đặt một chính sách rõ ràng cho mỗi nhóm

Ví dụ hệ thống có thêm URL:

~~~text
/public/**
/account/**
/reports/**
/admin/**
~~~

Không nên dùng quy tắc **/reports/** → authenticated()** nếu cả đọc và ghi báo cáo cần quyền riêng. Đặt quy tắc GET và POST rõ ràng, sau đó sử dụng denyAll cho các thao tác chưa thiết kế.

Đừng để thứ tự như sau:

~~~java
// Nguy hiểm: rule rộng che mất rule bảo vệ chi tiết:
.requestMatchers("/reports/**").authenticated()
.requestMatchers(HttpMethod.POST, "/reports/**")
    .hasAuthority("report:write")
~~~

Rule đầu đã khớp mọi request /reports/**, kể cả POST.

Sửa thành các rule theo method đứng trước:

~~~java
.requestMatchers(HttpMethod.GET, "/reports/**")
    .hasAuthority("report:read")
.requestMatchers(HttpMethod.POST, "/reports/**")
    .hasAuthority("report:write")
.anyRequest().denyAll()
~~~

Nếu có quy tắc bổ sung cho PUT/PATCH/DELETE, khai báo rõ trước denyAll sau khi xác định yêu cầu nghiệp vụ.

### 7.2. Không trộn nhóm công khai và nhóm nội bộ

Không viết **requestMatchers("/**").permitAll()** để “sửa tạm lỗi 403”; nó làm các quy tắc phía dưới không có hiệu lực. Cũng không nên đặt **anyRequest().permitAll()** làm mặc định khi dự án có yêu cầu bảo vệ endpoint. Chính sách an toàn là cho phép chính xác những gì có trong ma trận và từ chối phần còn lại, trừ khi nghiệp vụ chủ ý yêu cầu khác.

### 7.3. URL không đủ để quyết định mọi quyền

Ví dụ:

- User có report:read nhưng chỉ được xem báo cáo thuộc **tenant của mình**.
- Người có report:write chỉ được cập nhật một báo cáo khi báo cáo đó ở trạng thái **DRAFT**.
- Quản trị viên bộ phận A không được duyệt giao dịch của bộ phận B.

Các điều kiện như tenant, ownership, trạng thái tài nguyên cần được kiểm tra trong service/authorization layer hoặc AuthorizationManager có đủ thông tin nghiệp vụ. **hasRole/hasAuthority cho nhóm URL chỉ là tuyến phòng vệ ban đầu**, không chứng minh user được phép thao tác lên *mọi bản ghi* nằm sau endpoint đó.

### 7.4. Chú ý URL nội bộ và dispatcher

Spring Security thường xét đường dẫn của request; **không dựa vào việc frontend ẩn nút** hoặc tên controller để quyết định quyền. Nếu ứng dụng sử dụng forward, error dispatch, static assets, CORS preflight hoặc actuator endpoints, phải quyết định chúng thuộc chính sách nào. Ví dụ ứng dụng có ERROR/FORWARD dispatcher đặc thù có thể cần cấu hình dispatcherTypeMatchers phù hợp để trang lỗi hoạt động; không mở vô điều kiện mọi dispatcher trong hệ thống có rủi ro.

## 8. Những vấn đề bảo mật đi kèm

### CSRF khi bảo vệ HTTP method thay đổi trạng thái

**Authorization** và **CSRF** là hai kiểm tra khác nhau. Quyền **report:write** không có nghĩa browser request POST luôn hợp lệ; nếu authentication tự động được gửi qua browser (cookie, session và trong một số trường hợp Basic), website khác có thể lợi dụng môi trường trình duyệt để tạo request không mong muốn.

Trong ví dụ curl, CSRF được tắt để minh họa kết quả phân quyền của POST. Trong hệ thống thật:

1. Xác định browser có tự gửi credentials theo request chéo nguồn hay không.
2. Nếu cần CSRF, cấu hình CSRF token và yêu cầu frontend gửi đúng token với request thay đổi trạng thái.
3. Nếu thiết kế API không phụ thuộc browser credential tự động, đánh giá và ghi nhận lý do nếu muốn tắt CSRF cho phạm vi API phù hợp.
4. Không dùng **permitAll** hoặc **hasAuthority** để thay thế kiểm tra CSRF.

### CORS không phải authorization

CORS quyết định trang web ở origin khác có được browser cho phép đọc/gửi một số kiểu request không; nó **không cấp quyền nghiệp vụ**. API không thể coi việc đặt Access-Control-Allow-Origin là tương đương hasAuthority. Một attacker/client ngoài browser vẫn có thể gọi API, nên server luôn phải kiểm tra Authentication và Authorization.

### Quyền nên được cấp tối thiểu

Không mặc định gán **ROLE_ADMIN** hoặc quyền write cho mọi tài khoản mới. Khi dùng JWT hoặc identity provider, hãy xác minh conversion sang GrantedAuthority (ví dụ scope có thể mang tên **SCOPE_...** chứ không phải report:read). Tên authority ở policy phải khớp với tên đã ánh xạ.

### Method security bổ sung cho URL policy

Nếu một thao tác nhạy cảm có thể được gọi từ nhiều đường đi, có thể dùng **@EnableMethodSecurity** và **@PreAuthorize** ở service method để thực thi quyền gần nghiệp vụ. Đây là cơ chế bổ sung, không làm việc rà soát URL rule trở nên thừa. Đối với kiểm tra quyền trên từng bản ghi, service phải nhận thông tin tài nguyên/người dùng để thực hiện kiểm tra chính xác.

## 9. Phân biệt 401, 403 và 404 khi kiểm thử

| HTTP status | Ý nghĩa thường gặp trong demo | Điều nên kiểm tra |
| --- | --- | --- |
| **200** | Xác thực/phân quyền đã cho phép, handler trả thành công | Đúng rule và đúng body nghiệp vụ chưa? |
| **401** | Thiếu hoặc sai credentials, Basic entry point yêu cầu xác thực | Authorization header, thông tin user, cơ chế Basic/token |
| **403** | Đã xác thực nhưng thiếu quyền, bị denyAll, hoặc bị một lớp bảo vệ khác từ chối (như CSRF) | Authorities thực tế, matcher đầu tiên, CSRF, quy tắc dự phòng |
| **404** | Không có handler khớp sau khi request đã đi qua các lớp bảo mật cần thiết | URL mapping, HTTP method, context path; không vội kết luận là vấn đề quyền |
| **405** | Có path nhưng HTTP method không được controller hỗ trợ, với điều kiện request đã vượt qua các kiểm tra bảo mật | Annotation @GetMapping/@PostMapping, router, rule cho method |

Không nên khẳng định mọi request không tồn tại đều trả 404: nếu **anyRequest().denyAll()** từ chối từ trước, ứng dụng có thể trả 401/403 mà chưa tới giai đoạn xác định handler. Tương tự, một trang sử dụng form login có thể redirect **302** cho người chưa đăng nhập thay vì trả 401.

### Bật log khi chẩn đoán

Chỉ dùng ở môi trường phát triển khi cần:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Kiểm tra theo thứ tự: (1) request method/path, (2) SecurityFilterChain áp dụng, (3) Authentication/principal, (4) GrantedAuthority thực tế, (5) RequestMatcher đầu tiên khớp, (6) rule, (7) lỗi CSRF/entry point/handler. Tránh ghi password, session identifier, token hoặc dữ liệu nhạy cảm ra log.

## 10. Chiến lược kiểm thử có giá trị

Từ ma trận ở mục 3, mỗi nhóm nên có:

- **Ít nhất một ca được phép**: ví dụ reader GET /reports/summary nhận 200.
- **Một ca thiếu xác thực**: anonymous GET /account/profile nhận 401 với Basic.
- **Một ca đã xác thực nhưng thiếu quyền**: reader POST /reports/summary nhận 403.
- **Một ca phủ định các thao tác khác**: editor PUT /reports/summary không được tự động truy cập chỉ vì có report:write.
- **Một ca phủ định đường dẫn chưa khai báo**: admin GET /unlisted bị denyAll.

Có thể viết integration test với **spring-boot-starter-test**, **spring-security-test**, **MockMvc** để tránh việc kiểm tra thủ công mỗi lần đổi cấu hình. Đoạn sau là **fragment minh họa** bên trong class test có cấu hình MockMvc phù hợp, không phải chương trình Java độc lập:

~~~java
mvc.perform(get("/reports/summary")
        .with(httpBasic("reader", "demo123")))
    .andExpect(status().isOk());

mvc.perform(post("/reports/summary")
        .with(httpBasic("reader", "demo123")))
    .andExpect(status().isForbidden());

mvc.perform(post("/reports/summary")
        .with(httpBasic("editor", "demo123")))
    .andExpect(status().isOk());
~~~

Các static imports thường dùng: **org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic**, **org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get/post**, **org.springframework.test.web.servlet.result.MockMvcResultMatchers.status**. Nếu ứng dụng bật CSRF cho POST, test phải cung cấp token hợp lệ khi muốn kiểm tra đúng authorization thay vì thất bại ở CSRF.

Khi URL thay đổi hoặc thêm nhóm endpoint, cập nhật **ma trận quyền trước**, sau đó cập nhật rule và test. Không dùng duy nhất một tài khoản admin để kiểm thử, vì cách đó bỏ sót nhiều lỗi phân quyền.

## 11. Áp dụng ý tưởng với Spring WebFlux

Với WebFlux, tên API cấu hình khác Servlet:

| Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- |
| SecurityFilterChain | SecurityWebFilterChain |
| HttpSecurity | ServerHttpSecurity |
| authorizeHttpRequests | authorizeExchange |
| requestMatchers | pathMatchers |
| HttpServletRequest | ServerWebExchange |

Fragment reactive tương đương về chính sách (đặt trong cấu hình **ServerHttpSecurity**, không phải mã Java độc lập):

~~~java
http.authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/public/info").permitAll()
        .pathMatchers(HttpMethod.GET, "/account/profile").authenticated()
        .pathMatchers(HttpMethod.GET, "/reports/**")
            .hasAuthority("report:read")
        .pathMatchers(HttpMethod.POST, "/reports/**")
            .hasAuthority("report:write")
        .pathMatchers("/admin/**").hasRole("ADMIN")
        .anyExchange().denyAll());
~~~

Nguyên tắc vẫn là kiểm tra đường dẫn, method, Authentication, authority và thứ tự rule. **Không dùng HttpSecurity trong dự án WebFlux thuần**. Reactive có cơ chế authentication/security context bất đồng bộ riêng; khi chuyển stack, cần kiểm tra cả security filters, CSRF, test client và converter tương ứng. Fragment này chỉ chuyển **chính sách authorization**, chưa phải bean SecurityWebFilterChain đầy đủ.

## 12. Lỗi cấu hình thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đặt /**.authenticated() trước /admin/**.hasRole("ADMIN") | User thường có thể lọt vào nhóm admin vì rule đầu đã khớp | Đưa rule cụ thể lên trước; cân nhắc denyAll cuối cùng. |
| Dùng /reports/**.authenticated() cho cả GET/POST | Người chỉ đăng nhập cũng cập nhật được dữ liệu | Phân biệt HTTP method và yêu cầu authority read/write. |
| Chỉ kiểm tra frontend có hiện nút hay không | Client có thể gọi API trực tiếp | Bảo vệ request ở backend bằng Spring Security. |
| Cho phép toàn bộ request chưa match bằng permitAll() | Endpoint mới có thể trở thành công khai ngoài ý muốn | Dùng anyRequest().denyAll() trong chính sách allowlist. |
| Bỏ fallback SecurityFilterChain khi dùng nhiều chain | URL có thể không khớp chain nào và không được Spring Security bảo vệ | Thiết kế matcher/ưu tiên đúng; có chain dự phòng thích hợp. |
| Có ADMIN nhưng hasRole("ADMIN") trả 403 | Authentication thực tế chỉ có ADMIN, không có ROLE_ADMIN | Chuẩn hóa mapping hoặc dùng hasAuthority tương ứng. |
| Có report:read nhưng GET bị 403 | User authority khác tên, converter không cấp đúng quyền, hoặc matcher khác chiếm trước | Kiểm tra Authentication.getAuthorities() và rule đầu tiên khớp. |
| POST bị 403 dù có report:write | Có thể thiếu CSRF token hoặc rule khác khớp trước | Xem log, token, CSRF configuration và matcher order. |
| Mở rộng quyền write để sửa lỗi tạm | Vi phạm nguyên tắc quyền tối thiểu | Sửa matcher/mapping đúng nguyên nhân, test trường hợp bị từ chối. |
| Dùng hasRole cho quyền kiểu invoice:approve | Dễ lẫn tiền tố ROLE_ và role nghiệp vụ | Dùng hasAuthority("invoice:approve") cho permission cụ thể. |
| Chỉ kiểm tra quyền chung, không kiểm tra dữ liệu sở hữu | User có quyền nhóm nhưng xem/sửa bản ghi của người khác | Thêm kiểm tra ownership/tenant/resource ở service/authorization layer. |
| Cho tất cả OPTIONS đi qua bằng permitAll vô điều kiện | Có thể nới phạm vi quá rộng so với chính sách | Cấu hình CORS/preflight đúng ngữ cảnh; test hành vi thực tế. |

## 13. Câu hỏi và bài tập

1. Nếu **GET /reports/summary** yêu cầu report:read, tại sao việc người dùng đăng nhập thành công vẫn chưa đủ?
2. Vì sao **requestMatchers("/admin/**").hasRole("ADMIN")** phải đặt trước rule rộng như **requestMatchers("/**").authenticated()**?
3. Nếu editor có report:read và report:write, editor có mặc định truy cập được **/admin/status** không? Giải thích bằng GrantedAuthority.
4. Với endpoint **DELETE /reports/summary**, cấu hình demo sẽ làm gì? Điều gì ngăn quyền report:write tự động cho phép DELETE?
5. Tại sao POST có thể bị 403 dù Authentication chứa authority chính xác? Nêu vai trò của CSRF.
6. Khi tạo API nhóm **/orders/**, bạn sẽ phân quyền GET (đọc), POST (tạo), DELETE (xóa) và yêu cầu quyền trên *từng đơn hàng* ra sao?
7. Nếu ứng dụng dùng hai SecurityFilterChain, **securityMatcher** và **requestMatchers** kiểm soát hai quyết định khác nhau như thế nào?
8. Đọc trace: **reader** gọi **POST /reports/summary** với credentials hợp lệ. Xác thực thành công, rule nào khớp, và tại sao controller không được gọi?

**Điểm cần ghi nhớ:** Thiết kế bảo vệ endpoint bắt đầu từ **ma trận method + URL + danh tính/quyền**. Trong một SecurityFilterChain, **rule khớp đầu tiên** quyết định kiểm tra. Dùng **permitAll** cho endpoint công khai, **authenticated** cho vùng chỉ yêu cầu đăng nhập, **hasRole/hasAuthority** cho vùng có quyền cụ thể, và **denyAll** cho phần chưa được cho phép. Luôn kiểm tra thêm CSRF và điều kiện quyền trên dữ liệu khi nghiệp vụ yêu cầu.

## Tài liệu Spring Security chính thức

- Spring Security 6.5 — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Java Configuration, securityMatcher vs requestMatchers: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security — CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security 6.5 — Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — Authorize ServerHttpRequest (Reactive): https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
