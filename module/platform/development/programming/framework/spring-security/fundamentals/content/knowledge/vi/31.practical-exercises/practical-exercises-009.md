# Đánh giá một cấu hình mẫu để phát hiện cấp quyền quá rộng hoặc tắt bảo vệ

## 1. Mục tiêu của bài thực hành tổng hợp

Nhiệm vụ của người học là **đọc một cấu hình Spring Security như một người review bảo mật**, tìm các chỗ cấp quyền quá rộng, kiểm tra các lớp bảo vệ bị tắt, giải thích hậu quả có thể khai thác, đề xuất cấu hình an toàn hơn và viết kiểm thử tự động chứng minh rằng bản sửa thực thi đúng chính sách.

Trọng tâm là **Spring Security cho Servlet/Spring MVC**, Java 17, Spring Boot 3.5.x và Spring Security 6.5.x. Cách khởi tạo/filter chain có thể thay đổi khi chuyển sang Spring Boot 4/Spring Security 7; khi dùng phiên bản khác, đối chiếu API và migration guide. Mã cấu hình cố ý sai ở phần đầu **chỉ để phân tích**, tuyệt đối không triển khai. Phần thực hành cuối cung cấp một ứng dụng an toàn tối giản có thể xây dựng với Maven và kiểm tra bằng MockMvc.

Sau bài này, bạn có thể:

- Phân biệt **phạm vi áp dụng của `SecurityFilterChain`** với **quy tắc cấp quyền bên trong chain**.
- Phát hiện `permitAll` hoặc matcher quá rộng, thứ tự quy tắc sai, thiếu deny-by-default và endpoint mới vô tình mở.
- Đánh giá đúng ngữ cảnh khi thấy `csrf.disable()`, `headers.disable()`, `sessionFixation().none()`, `web.ignoring()` hoặc `securityMatcher` chỉ bao một phần ứng dụng.
- Không nhầm CORS, CSRF, xác thực (authentication), phân quyền (authorization), method security và kiểm tra chủ sở hữu dữ liệu.
- Viết kiểm thử âm tính: anonymous, sai role, method không được cho phép, thiếu CSRF, tài nguyên không có trong whitelist, chuỗi filter không được chọn.
- Báo cáo phát hiện dựa trên **bằng chứng → rủi ro → điều kiện → sửa đổi → phép thử**, tránh phán đoán tuyệt đối từ một dòng config tách khỏi ngữ cảnh.

### Chính sách ứng dụng giả định

Một hệ thống nội bộ tên **Report Desk** có các URL:

| URL / thao tác | Ai được phép? | Ghi chú |
|---|---|---|
| `GET /` | Mọi người | Trang giới thiệu |
| `GET /login` và `POST /login` | Mọi người | Trình duyệt đăng nhập form, POST được CSRF bảo vệ |
| `GET /api/public/info` | Mọi người | Thông tin công khai, không có dữ liệu nhạy cảm |
| `GET /api/reports/summary` | `VIEWER` hoặc `ADMIN` | Xem báo cáo |
| `POST /api/reports/export` | `ADMIN` | Yêu cầu xuất báo cáo, có CSRF token nếu dùng cookie/session |
| `GET /api/admin/users` | `ADMIN` | Quản trị tài khoản |
| `GET /api/account/me` | Mọi người **đã xác thực** | Xem thông tin chính mình |
| Bất kỳ route khác, kể cả route mới chưa kiểm duyệt | Từ chối | Mặc định deny-all; thêm rule có chủ đích mới mở |

Đây là **hợp đồng cấp quyền** của bài thực hành. Nếu thiếu hợp đồng tương tự trong một dự án thật, hãy hỏi product/security owner trước khi quyết định `permitAll` hay `hasRole`. Một audit tốt không thể suy ra ý định nghiệp vụ chỉ từ tên endpoint.

## 2. Đọc đúng Spring Security trước khi tìm lỗi

Trong Spring Security Servlet, `FilterChainProxy` chọn **`SecurityFilterChain` đầu tiên phù hợp** với request. Mỗi chain có một **chain-level matcher**; theo mặc định chain được tạo bởi `HttpSecurity` có thể áp dụng cho mọi request, nhưng gọi `securityMatcher(...)` sẽ giới hạn phạm vi đó. **Nếu không có chain nào khớp, request không được Spring Security bảo vệ.** Nếu có nhiều chain, phải xét `@Order` và fallback, không thể nhìn một bean riêng lẻ rồi kết luận.

**Bên trong chain đã được chọn**, `authorizeHttpRequests` kiểm tra các `requestMatchers` theo thứ tự khai báo; **rule đầu tiên khớp quyết định quyền**. `anyRequest()` chỉ áp dụng cho các request đã vào chain đó, không làm fallback cho toàn ứng dụng khi chain bị giới hạn bởi `securityMatcher`.

```text
Request HTTP
   |
   v
FilterChainProxy
   |
   +-- SecurityFilterChain @Order(1), securityMatcher("/api/**") ?
   |      | yes
   |      v
   |    CSRF/Auth filters -> authorizeHttpRequests (rule đầu tiên khớp)
   |
   +-- SecurityFilterChain @Order(2), catch-all ?
   |      | yes
   |      v
   |    CSRF/Auth filters -> authorizeHttpRequests
   |
   +-- Không chain nào khớp
          |
          v
      KHÔNG qua lớp bảo vệ Spring Security
```

Phân biệt những từ khóa rất dễ bị hiểu sai:

| Cấu hình | Ý nghĩa thực | Câu hỏi khi review |
|---|---|---|
| `requestMatchers("/x/**").permitAll()` | Cho phép request phù hợp không cần authorization | Đây có phải tài nguyên công khai thật sự? Mẫu có bắt cả route nhạy cảm không? |
| `requestMatchers("/x/**").authenticated()` | Cần danh tính đã xác thực | Có cần role, permission hoặc kiểm tra tenant/owner không? |
| `requestMatchers("/x/**").hasRole("ADMIN")` | Cần authority `ROLE_ADMIN` (mặc định) | Rule có bị rule trước đó che khuất không? Dữ liệu authority có đáng tin? |
| `anyRequest().permitAll()` | Mở mọi route còn lại **trong chain** | Có đường dẫn nội bộ hoặc route tương lai bị mở không? |
| `anyRequest().authenticated()` | Cho mọi user đã đăng nhập đi qua | Có đủ cho hành động quản trị hay phải deny-by-default? |
| `anyRequest().denyAll()` | Từ chối mọi request chưa khớp rule trước | Có giúp phát hiện endpoint mới chưa khai báo không? |
| `securityMatcher("/api/**")` | Chọn phạm vi **toàn bộ chain** | Các route ngoài `/api/**` có catch-all chain khác không? |
| `web.ignoring().requestMatchers(...)` | Bỏ qua Spring Security filters cho các path đó | Có mất headers, SecurityContext/CSRF/filter logging ngoài chủ đích không? |
| `csrf.disable()` | Tắt CSRF trong chain | Chain có nhận request mà browser tự gửi cookie/Basic credential không? |
| `headers.disable()` | Tắt writer mặc định của Spring Security response headers | Edge/proxy có thay thế đầy đủ không? Có kiểm chứng HTTP response không? |

**Không áp dụng quy tắc “mọi `permitAll` đều là lỗi”.** Health endpoint tối thiểu và static resource có thể công khai hợp lệ. Vấn đề là **độ rộng matcher, thứ tự và hợp đồng quyền của dữ liệu thực tế**.

## 3. Mẫu cố ý thiếu an toàn: tìm vấn đề trước khi đọc lời giải

Giả định đây là **SecurityFilterChain duy nhất** trong ứng dụng. Code minh họa có thể biên dịch khi đặt trong dự án có Spring Security 6.5; nó được viết để làm bài audit và **không được chạy ở môi trường có dữ liệu thật**.

```java
package com.example.audit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class VulnerableSecurityConfiguration {

    @Bean
    SecurityFilterChain unsafeChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")                  // A
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").permitAll() // B
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")                   // C
                .anyRequest().authenticated()          // D
            )
            .csrf(AbstractHttpConfigurer::disable)     // E
            .headers(AbstractHttpConfigurer::disable)  // F
            .sessionManagement(sessions -> sessions
                .sessionFixation(fixation -> fixation.none()) // G
            )
            .formLogin(withDefaults())                 // H
            .httpBasic(withDefaults())
            .build();
    }
}
```

**Bài tập trước khi xem đáp án:**

1. Request `GET /api/admin/users` của người ẩn danh sẽ đi vào chain nào? Rule B hay rule C quyết định quyền?
2. `GET /dashboard` hoặc `GET /admin` nằm ngoài `/api/**` có đi qua bất cứ `SecurityFilterChain` nào không?
3. `anyRequest().authenticated()` ở D có “cứu” được rule B không? Có bảo vệ các đường dẫn ngoài `/api/**` không?
4. Tắt CSRF ở E có chắc chắn là lỗ hổng trong mọi API không? Phải biết thêm điều gì về credential và cách browser gọi API?
5. Tắt headers ở F gây mất những header bảo vệ nào? Có phải Spring Security tự thêm CSP mặc định không?
6. G làm gì nếu application dùng session? H có thực sự cung cấp endpoint `POST /login` trong một chain chỉ khớp `/api/**`?
7. Một bản vá chỉ đảo B/C, nhưng vẫn giữ A và E/F/G, đã đạt chính sách ở phần 1 chưa?
8. Bạn sẽ viết những **negative tests** nào để chứng minh đã chặn được đúng đường tấn công?

## 4. Lời giải review: bằng chứng, tác động, bản sửa

### R1. `requestMatchers("/api/**").permitAll()` cấp quyền quá rộng

Trong chain đã chọn, rule B khớp với **mọi URL thuộc `/api/**`**, bao gồm `/api/admin/users`, `/api/reports/export` và `/api/account/me`. Khi rule B đã trả quyết định permit, rule C và D không được xét. `hasRole("ADMIN")` ở dòng sau nhìn có vẻ nghiêm ngặt nhưng hoàn toàn bị shadow bởi rule B.

**Tác động:** request ẩn danh có thể đi qua lớp authorization HTTP đến handler nhạy cảm. Một endpoint có thêm bảo vệ ở tầng service vẫn có thể chặn, nên phải kiểm tra cả controller, service và các chain khác trước khi khẳng định dữ liệu đã bị lộ; tuy nhiên lớp HTTP policy rõ ràng không đáp ứng hợp đồng.

**Sửa:** cho phép chính xác `GET /api/public/info`, đặt quyền admin và quyền report trước fallback, tránh `/api/**.permitAll()`. **Test:** anonymous đọc `/api/admin/users` phải bị chặn; user VIEWER GET admin phải 403; chỉ ADMIN mới đọc được.

### R2. Matcher sai thứ tự che khuất rule chặt

Trong Spring Security, các authorization matcher có thứ tự; một đường dẫn phù hợp cả `/api/**` và `/api/admin/**` sẽ chịu rule đầu tiên. Đặt rule cụ thể trước rule bao quát có thể giải quyết một phần, nhưng một `permitAll` quá rộng ở phía dưới vẫn cho phép nhiều endpoint khác.

**Sửa:** viết matrix theo method + path + role; chỉ permit danh sách endpoint công khai đã duyệt; cuối cùng dùng `anyRequest().denyAll()` khi mô hình sản phẩm yêu cầu whitelist chặt. **Test:** một route được thêm mới nhưng chưa có rule phải bị từ chối, ngay cả với user ADMIN.

### R3. `securityMatcher("/api/**")` bỏ trống các đường dẫn khác

Đây là **chain duy nhất** của ví dụ. Vì thế `GET /dashboard`, `GET /internal/maintenance`, `GET /admin` không khớp matcher của chain và **không đi qua Spring Security**. Nếu một ứng dụng thật có thêm catch-all chain xếp sau thì kết luận khác; phải kiểm tra tổng thể tất cả `SecurityFilterChain` và thứ tự `@Order`.

**Sửa:** với ứng dụng nhỏ, dùng một chain catch-all **không đặt `securityMatcher`**. Với nhiều chuỗi API/web độc lập, đặt chain đặc thù trước và catch-all ở cuối; viết test request cho từng nhóm và đường dẫn ngoài phạm vi. **Test:** gọi một route bất ngờ như `/internal/maintenance` phải bị chặn theo hợp đồng.

### R4. `csrf.disable()` bỏ một lớp bảo vệ cần theo ngữ cảnh

Với ứng dụng web dùng **cookie phiên** hoặc credential browser tự đính kèm, tắt CSRF trên POST/PUT/PATCH/DELETE có thể cho phép request thay đổi trạng thái ngoài ý muốn. Trong ví dụ, `formLogin` được bật (dù ngoài phạm vi chain), và các endpoint báo cáo có thao tác POST; đây là dấu hiệu phải review CSRF nghiêm túc.

**Không suy ra** mọi API stateless bearer-token đều nhất thiết cần CSRF token: với API chỉ chấp nhận `Authorization: Bearer ...` do client chủ động đặt, không dùng cookie để xác thực, threat model CSRF khác. Nếu API hỗn hợp, có thể tách filter chain hoặc dùng matcher CSRF rất hẹp, nhưng phải kiểm tra thực tế. **Sửa trong ứng dụng lab cookie/form-login:** giữ CSRF bật. **Test:** ADMIN POST `/api/reports/export` thiếu token phải 403; có token hợp lệ phải 200.

### R5. `headers.disable()` tắt các response header phòng vệ

Spring Security Servlet mặc định viết nhiều header có ích, ví dụ `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` và các header chống cache; `Strict-Transport-Security` thường chỉ thêm cho phản hồi HTTPS. Tắt `headers` làm mất writer mặc định của Spring Security. Ngay cả khi chỉ public static files, `web.ignoring()` cũng bỏ qua security filters nên thường kém an toàn hơn `permitAll`.

**Không khẳng định** CSP hay Referrer-Policy luôn có sẵn: CSP **không phải header mặc định** của Spring Security, cần thiết kế riêng theo ứng dụng. Có thể proxy/CDN thêm một số header, vì vậy kết luận dựa trên **response cuối cùng**. **Sửa:** giữ headers mặc định và bổ sung chính sách như CSP khi đã có đánh giá UX/browser. **Test:** response kiểm tra `nosniff`, frame options, cache-control; kiểm tra HSTS qua HTTPS, không đòi nó ở localhost HTTP.

### R6. `sessionFixation().none()` tắt thay đổi session ID lúc login

Với **đăng nhập dựa trên HTTP session**, việc đổi session ID khi authentication thành công chống session fixation. Spring Security trên Servlet hiện đại có chiến lược phù hợp mặc định; đặt `none()` là dấu hiệu đáng ngại. Nếu chain hoàn toàn stateless và không login session, mục này không tương đương một lỗ hổng thực tế.

**Sửa:** bỏ cấu hình yếu, hoặc `sessionFixation(f -> f.changeSessionId())` khi có login với session. **Test:** tạo anonymous session ID A, đăng nhập, quan sát ID B khác A; sau logout, A/B cũ không còn truy cập được dữ liệu. Đừng dùng tình huống này để suy diễn rằng đổi ID có thể chống XSS hay cookie theft sau login.

### R7. `formLogin` không cung cấp endpoint login vì chain scope

Trong mẫu, chain chỉ chọn URL `/api/**`, nhưng `formLogin(withDefaults())` có mặc định login page và login processing dưới `/login`. Vì `/login` **không vào chain**, filter tạo form login và xử lý `POST /login` không chạy cho các request đó; cấu hình trông có đăng nhập nhưng endpoint cần thiết lại không nằm trong chain. Đây thường gây lỗi chức năng; kết hợp với việc các route khác không được bảo vệ làm tình hình nguy hiểm hơn.

**Sửa:** đặt form login vào catch-all web chain, hoặc mở rộng matcher đến đúng các endpoint auth và thêm fallback chain. **Test:** `GET /login` hiển thị form và `POST /login` thành công với CSRF token, nhưng user chưa login không đọc được dữ liệu.

### R8. `anyRequest().authenticated()` chỉ yêu cầu đã đăng nhập

Ngay cả khi bỏ rule B, `authenticated()` không đủ cho hành động admin, xuất dữ liệu, duyệt đơn hàng, chỉnh quyền hoặc truy cập tài nguyên tenant khác. Một user hợp lệ nhưng thiếu quyền vẫn có thể vào nếu path đó chưa có rule chi tiết.

**Sửa:** `hasRole`/`hasAuthority` cho nhóm route nhạy cảm và **method-level/ownership checks** tại service. Đối với `/api/reports/{id}`, việc có quyền xem report nói chung **không chứng minh** được report ID đó thuộc tenant của user. **Test:** user của tenant A đọc `id` thuộc tenant B phải bị từ chối dù role giống nhau.

### R9. Không thấy `@EnableMethodSecurity` và quy tắc service

`@PreAuthorize` trên method chỉ hoạt động nếu bật method security thích hợp và lời gọi đi qua Spring proxy. Việc không có `@EnableMethodSecurity` trong một file không tự chứng minh toàn ứng dụng đã tắt method security (có thể được khai báo ở config khác). Tuy vậy, khi policy đòi kiểm tra cả use case ở service, phải xác nhận annotation được thực thi trong runtime.

**Sửa:** bật `@EnableMethodSecurity` nếu dùng `@PreAuthorize`, gọi service qua bean Spring, test từ controller **và** service. **Test:** user VIEWER không thể gọi service xuất báo cáo cho ADMIN bằng một đường vào khác.

### Tổng hợp ưu tiên xử lý

| ID | Bằng chứng trong mẫu | Mức độ ưu tiên giả định | Điều kiện xác minh |
|---|---|---|---|
| R1/R2 | B trước C: `/api/**` công khai | Rất cao | Endpoint nhạy cảm có handler và không có chặn bổ sung |
| R3 | Chỉ có chain `/api/**` | Rất cao | Không có catch-all chain khác |
| R4 | `csrf.disable()` | Cao trong web session | Browser tự gửi cookie/credential, endpoint thay đổi dữ liệu |
| R5 | `headers.disable()` | Cao/trung bình | Headers không được bổ sung đầy đủ ở proxy |
| R6 | `sessionFixation().none()` | Cao nếu session login | Login dùng HTTP session và cố giữ ID |
| R7 | Login filter ngoài chain | Trung bình/cao | Không có chain khác phục vụ `/login` |
| R8 | Fallback chỉ `authenticated()` | Cao | Có route nhạy cảm chưa được liệt kê |
| R9 | Method security chưa xác minh | Theo nghiệp vụ | Service cần kiểm tra quyền nhưng annotation chưa hoạt động |

Mức độ trong bảng là **ưu tiên review theo kịch bản**; severity thực tế phụ thuộc loại dữ liệu, lỗ hổng khai thác được, các biện pháp khác và bề mặt public internet/intranet. Tránh xếp mọi `csrf.disable` là critical khi chưa biết kiểu xác thực.

## 5. Phiên bản sửa đúng: ứng dụng Java 17 kiểm thử được

Để tập trung vào **kiểm tra chính sách**, lab này dùng Spring MVC với form login mặc định **và HTTP Basic cho kiểm thử API**. Production thường chọn mô hình xác thực phù hợp từng nhóm client; ví dụ bật song song chỉ nhằm quan sát và kiểm thử rõ ràng. Khi ứng dụng vẫn dùng login theo session/cookie, giữ CSRF trên POST.

Cấu trúc:

```text
security-audit-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/audit/
    │   ├── SecurityAuditApplication.java
    │   ├── SecurityConfiguration.java
    │   ├── DemoController.java
    │   └── ReportService.java
    └── test/java/com/example/audit/
        └── SecurityPolicyTest.java
```

### 5.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>security-audit-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
```

### 5.2. `SecurityAuditApplication.java`

```java
package com.example.audit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityAuditApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityAuditApplication.class, args);
    }
}
```

### 5.3. `SecurityConfiguration.java`: explicit rules và deny-by-default

```java
package com.example.audit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain applicationChain(HttpSecurity http) throws Exception {
        return http
            // Không đặt securityMatcher: chain mặc định bao toàn ứng dụng.
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/public/info")
                    .permitAll()
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAnyRole("VIEWER", "ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/reports/**")
                    .hasRole("ADMIN")
                .requestMatchers("/api/account/**")
                    .authenticated()
                // Đường dẫn mới/method lạ phải được duyệt trước khi mở.
                .anyRequest().denyAll()
            )
            .formLogin(withDefaults())
            .httpBasic(withDefaults())
            .csrf(withDefaults())
            .headers(withDefaults())
            .sessionManagement(sessions -> sessions
                .sessionFixation(fixation -> fixation.changeSessionId())
            )
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var viewer = User.withUsername("viewer")
            .password(encoder.encode("viewer-demo-123"))
            .roles("VIEWER")
            .build();
        var admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-123"))
            .roles("ADMIN")
            .build();
        return new InMemoryUserDetailsManager(viewer, admin);
    }
}
```

**Tại sao đây là cải thiện:**

1. Một `SecurityFilterChain` mặc định bắt mọi request; không còn khoảng trống do `securityMatcher("/api/**")`.
2. `GET /api/public/info` là public **theo đúng method và path**; một `POST` cùng path không tự được cho phép.
3. `/api/admin/**` được chặn bằng `ROLE_ADMIN` ngay từ request authorization; các report chỉ cho role tương ứng.
4. Fallback `denyAll` cố ý nghiêm ngặt: cập nhật business route phải cập nhật policy và test; giảm lỗi “endpoint mới vô tình mở”.
5. CSRF và security headers được giữ; form login trên `/login` nằm trong chain. Session fixation protection được đặt rõ cho web session.
6. `@EnableMethodSecurity` cho phép policy ở service hoạt động khi gọi qua Spring-managed bean.

**Vì sao có `/login` trước denyAll?** Form login mặc định cần endpoint login cho người chưa xác thực; nếu để fallback denyAll chặn chúng, chính luồng login sẽ không sử dụng được. Cách cho phép endpoint login vẫn không làm lỏng CSRF: POST thiếu token sẽ bị `CsrfFilter` từ chối. Nếu dùng login page tùy biến, phải đảm bảo static assets và endpoint phục vụ nó được cấp quyền chính xác.

**Cảnh báo cho production:** Các chuỗi password demo được ghi trong mã chỉ dùng cho môi trường học tập. Ở hệ thống thật, dùng nguồn account đáng tin (DB/LDAP/OIDC), password hash thích ứng, kiểm soát reset/MFA/rate limit, secret management và chính sách tài khoản/tenant riêng. Không copy user demo sang production.

### 5.4. `DemoController.java`: các handler có kết quả có thể kiểm thử

```java
package com.example.audit;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    private final ReportService reports;

    public DemoController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/")
    public String index() {
        return "REPORT_DESK_PUBLIC";
    }

    @GetMapping("/api/public/info")
    public String publicInfo() {
        return "PUBLIC_INFO";
    }

    @GetMapping("/api/reports/summary")
    public String reportSummary() {
        return "REPORT_SUMMARY";
    }

    @PostMapping("/api/reports/export")
    public String exportReport() {
        return reports.export();
    }

    @GetMapping("/api/admin/users")
    public String listUsers() {
        return "ADMIN_USERS";
    }

    @GetMapping("/api/account/me")
    public String profile(Authentication authentication) {
        return "HELLO_" + authentication.getName();
    }

    @GetMapping("/api/unlisted")
    public String unlisted() {
        return "SHOULD_NOT_BE_VISIBLE";
    }
}
```

`/api/unlisted` **cố ý có controller nhưng không có allow rule**. Đây là “canary route”: nếu một ai đó đổi `anyRequest().denyAll()` thành `permitAll()`, bài test sẽ báo rằng policy đã bị mở. Trong ứng dụng thật, dùng tập route và authorization test thích hợp thay vì một canary duy nhất.

### 5.5. `ReportService.java`: thêm bảo vệ ở use case

```java
package com.example.audit;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public String export() {
        // Trả chuỗi demo; chưa có thao tác xuất dữ liệu thật.
        return "EXPORT_REQUESTED";
    }
}
```

`@PreAuthorize` kiểm tra trước khi vào method, **khi method được gọi qua proxy do Spring quản lý**. Phần HTTP rule và method rule bổ sung cho nhau: một endpoint có thể được gọi qua message handler, scheduler, một controller khác hoặc service orchestration; chỉ bảo vệ URL chưa chắc đủ. Đừng phụ thuộc duy nhất vào annotation trong lời gọi `this.export()` nội bộ cùng object vì self-invocation có thể bỏ qua proxy. Với kiểm tra **ownership/tenant**, bổ sung điều kiện từ dữ liệu thật, không tự cho phép chỉ vì role bằng nhau.

### 5.6. `SecurityPolicyTest.java`: chứng minh chính sách bằng request thật qua filter

```java
package com.example.audit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityPolicyTest {

    @Autowired MockMvc mvc;
    @Autowired ReportService reports;

    @Test
    void publicRouteIsReadableAndSecurityHeadersRemain() throws Exception {
        mvc.perform(get("/api/public/info"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_INFO"))
            .andExpect(header().string("X-Content-Type-Options", "nosniff"))
            .andExpect(header().string("X-Frame-Options", "DENY"));
    }

    @Test
    void aViewerCannotUseAdminRoute() throws Exception {
        mvc.perform(get("/api/admin/users")
                .with(httpBasic("viewer", "viewer-demo-123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void anAdminCanUseAdminRoute() throws Exception {
        mvc.perform(get("/api/admin/users")
                .with(httpBasic("admin", "admin-demo-123")))
            .andExpect(status().isOk())
            .andExpect(content().string("ADMIN_USERS"));
    }

    @Test
    void aViewerCanReadReport() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(httpBasic("viewer", "viewer-demo-123")))
            .andExpect(status().isOk());
    }

    @Test
    void postExportRequiresCsrfAndAdminRole() throws Exception {
        mvc.perform(post("/api/reports/export")
                .with(httpBasic("admin", "admin-demo-123")))
            .andExpect(status().isForbidden()); // thiếu CSRF token

        mvc.perform(post("/api/reports/export")
                .with(httpBasic("viewer", "viewer-demo-123"))
                .with(csrf()))
            .andExpect(status().isForbidden()); // đủ CSRF, thiếu quyền

        mvc.perform(post("/api/reports/export")
                .with(httpBasic("admin", "admin-demo-123"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("EXPORT_REQUESTED"));
    }

    @Test
    void anUnlistedEndpointStaysForbiddenEvenForAdmin() throws Exception {
        mvc.perform(get("/api/unlisted")
                .with(httpBasic("admin", "admin-demo-123")))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void serviceGuardAlsoRejectsViewer() {
        assertThrows(AccessDeniedException.class, () -> reports.export());
    }
}
```

Mỗi test ở trên kiểm tra **hành vi quan sát được**, không chỉ grep code tìm chuỗi `hasRole`. `httpBasic` cung cấp credential cho filter thực; `csrf()` là helper tạo CSRF token hợp lệ để qua `CsrfFilter`; `@WithMockUser` được dùng riêng cho bài test **method security** và **không thay thế** test xác thực bằng password thực.

Khi ứng dụng dùng form login mặc định kèm HTTP Basic, response của **request ẩn danh** có thể là redirect login (302) hoặc 401 theo entry point/Accept header. Vì vậy các test bắt buộc phía trên chủ yếu kiểm **403 của user đã xác thực nhưng thiếu role**, **403 thiếu CSRF**, và **200 cho quyền hợp lệ**. Nếu muốn assert mã 401 cho anonymous API, hãy cấu hình và test `AuthenticationEntryPoint` cụ thể; đừng khẳng định mọi ứng dụng trả cùng một status.

**Chạy thử** khi đã tạo đầy đủ 5 file Java ở đúng package và `pom.xml`:

```bash
java -version
mvn -version
mvn clean test
mvn spring-boot:run
```

Sau khi server chạy tại `http://localhost:8080`, ví dụ kiểm tra nhanh:

```bash
curl -i http://localhost:8080/api/public/info
curl -i -u viewer:viewer-demo-123 http://localhost:8080/api/admin/users
curl -i -u admin:admin-demo-123 http://localhost:8080/api/admin/users
curl -i -u viewer:viewer-demo-123 http://localhost:8080/api/reports/summary
```

Dự kiến lần lượt nhận: **200 PUBLIC_INFO**; **403** vì VIEWER thiếu quyền admin; **200 ADMIN_USERS**; **200 REPORT_SUMMARY**. Không dùng những lệnh curl này để chứng minh CSRF: một POST hợp lệ cần token CSRF kèm trạng thái tương ứng, vì vậy dùng MockMvc test `.with(csrf())` hoặc lấy token từ form/browser đúng phiên.

**Giới hạn của minh chứng:** đoạn mã là một fixture học tập. Người học có thể copy vào Maven project và chạy test; bài viết không tuyên bố đã thực thi Maven hay chứng minh mọi version ngoài phạm vi có cùng API.

## 6. Thực hiện audit một cấu hình bất kỳ theo trình tự

### Bước 1 — Ghi hợp đồng quyền từ góc độ sản phẩm

Đừng bắt đầu bằng thao tác đổi `permitAll` thành `authenticated`. Với mỗi endpoint, ghi ít nhất:

- Method, path, auth mechanism (session, Basic, bearer token, OIDC), public/private.
- Principal type, authority/role, điều kiện owner/tenant, trạng thái account.
- Có thay đổi dữ liệu/đăng xuất/đổi quyền/nhập dữ liệu nhạy cảm không?
- Có bị gọi trực tiếp từ browser cookie hay chỉ từ machine-to-machine client?
- Có endpoint tương đương dưới actuator, management port, servlet khác hay proxy route không?
- Có tài nguyên tĩnh, trang login, error dispatch, CORS preflight hoặc webhook cần xử lý đặc biệt không?

Kết quả là bảng **method × path × persona × expected decision**, dùng làm oracle cho test. Phân biệt rõ `permitAll` cho public resource với `authenticated` cho trang cá nhân, và `hasRole`/`hasAuthority`/custom authorization cho dữ liệu nhạy cảm.

### Bước 2 — Liệt kê toàn bộ chuỗi bảo vệ và phạm vi

Kiểm tra **tất cả** `@Bean SecurityFilterChain`, thứ tự `@Order`, `securityMatcher`, `WebSecurityCustomizer`, servlet path, context path, management/actuator configuration, reverse proxy. Một matcher `/api/**` có thể an toàn khi có catch-all phía sau; thiếu catch-all có thể để lọt route mà nhà phát triển tưởng “mặc định Spring chặn”.

Lưu ý: `anyRequest().denyAll()` nằm trong một chain hẹp **không bù được** các path ngoài chain. Khi có nhiều DispatcherServlet, servlet path hoặc URL rewrite, kiểm tra matcher áp dụng lên **request path sau normalizing** và chính xác theo stack/framework version. Đừng tự đoán rằng wildcard sẽ khớp cùng cách trong mọi servlet context.

### Bước 3 — Tìm các phép cho phép rộng và rule bị che

Duyệt thứ tự từ trên xuống:

- `"/**".permitAll()`, `"/api/**".permitAll()`, `anyRequest().permitAll()`.
- `authenticated()` cho route admin/write/approve/finance có cần authority cụ thể không?
- Rule `"/admin/**".hasRole("ADMIN")` có đặt **sau** rule match rộng hơn không?
- Có giới hạn bằng `HttpMethod` không, hay permit GET vô tình cho phép POST/DELETE?
- Matcher có đúng endpoint thật, đúng servlet path và kể cả trailing slash/URL encoded paths không?
- Có fallback policy rõ ràng cho URL mới chưa từng review không?

Không xem việc xuất hiện text `permitAll` là bằng chứng đủ. Phải tính **matcher nào thật sự thắng** và thử request cụ thể.

### Bước 4 — Tìm các biện pháp bị tắt hoặc cấu hình lại

| Dấu hiệu | Cần điều tra | Định hướng |
|---|---|---|
| `csrf(AbstractHttpConfigurer::disable)` | Browser cookie/session? Basic credential? request thay đổi trạng thái? | Bật CSRF cho session web; chỉ ngoại lệ hẹp, có bằng chứng |
| `headers(AbstractHttpConfigurer::disable)` | Header cuối cùng ở response do app/proxy phát? | Giữ default headers; bổ sung CSP/Referrer-Policy theo ứng dụng |
| `sessionFixation(...none())` | Có form login sử dụng session? | Giữ changeSessionId/migrateSession phù hợp |
| `securityMatcher(...)` thiếu fallback | Route khác có chain bảo vệ không? | Thêm catch-all chain hoặc bỏ matcher nếu chỉ một chain |
| `web.ignoring().requestMatchers(...)` | Request có bypass header writer/filters? | Ưu tiên `permitAll` trong filter chain |
| `httpBasic(withDefaults())` | Có đang mở Basic cho endpoint internet mà sản phẩm không cần? | Chỉ bật scheme được phép, bắt buộc TLS |
| `cors(...)` mở origin | Có cookie credentials + origin không tin cậy? | Giới hạn origin/method/header, kiểm tra response CORS thật |
| `sessionCreationPolicy(STATELESS)` | Có mong đợi form login/session? | Giữ mô hình session phù hợp hoặc chuyển rõ sang stateless bearer |
| `@EnableMethodSecurity` bị thiếu | Có trông đợi `@PreAuthorize` được enforce không? | Bật và test service qua bean Spring |
| `/actuator/**` `permitAll` | Endpoint management nào được công khai? | Chỉ public liveness cần thiết, tách management/security config |

**CSRF và CORS là hai bài toán khác nhau**. CORS giới hạn trình duyệt đọc response cross-origin theo policy server; CORS không tự cung cấp authorization và không thay thế CSRF token. Đồng thời, tắt CSRF cho API bearer stateless có thể là quyết định hợp lý khi đã kiểm chứng không dùng credential browser tự đính kèm.

### Bước 5 — Kiểm tra bảo vệ nhiều lớp, không dừng ở URL

HTTP rules không thay thế:

- **Object-level authorization:** user của tenant A truy cập `/api/reports/42` thuộc tenant B. Cần kiểm tra bản ghi được truy cập, owner/tenant/ACL, không chỉ vai trò xem báo cáo.
- **Field-level authorization:** user được xem report nhưng không được xem trường mức lương/PII; serializer/query không được lộ dữ liệu.
- **Method security:** `@PreAuthorize`/`@PostAuthorize` hoặc service authorization component cần chạy trên đường gọi thật.
- **Authentication trust:** role/scope phải tới từ nguồn đáng tin, không tin field `role`/`tenantId` do client gửi mà không xác minh.
- **Token validation:** với JWT resource server, kiểm tra signature, issuer, expiry và audience thích hợp; đừng đồng nhất “decode được JWT” với “xác thực hợp lệ”.
- **Operational controls:** TLS, bảo vệ cookie, lockout/rate limit, session expiry/revocation, audit logging an toàn.

Một API trả 403 ở một route có thể vẫn lộ dữ liệu qua route khác, GraphQL endpoint hoặc export pathway. Review phải theo **đường đi dữ liệu**, không chỉ theo một regex.

### Bước 6 — Viết test dương tính và âm tính tương ứng

Dùng một bộ persona tối thiểu:

| Persona | Mục tiêu kiểm tra |
|---|---|
| Anonymous | Public GET được phép; private/admin bị chặn |
| VIEWER | Xem summary, không export hoặc quản trị |
| ADMIN | Được phép quản trị và export đúng phương thức |
| Authenticated không có role thích hợp | Không tự được quyền thông qua fallback |
| User khác tenant | Dữ liệu chéo tenant bị từ chối |
| Request thiếu CSRF | POST có cookie/session bị chặn |
| Request đến URL không liệt kê | Fail closed, kể cả khi người dùng có quyền admin |

Kiểm tra cả **status** lẫn **nội dung response**. Nếu denied vì method chưa khớp controller thay vì security policy, một `404`/`405` không phải bằng chứng rằng authorization hoạt động đúng; cần tạo handler có thật rồi chứng minh filter chặn trước khi vào handler. Tương tự, `403` do thiếu CSRF không chứng minh rule role admin đúng — luôn thử thêm **request có CSRF token hợp lệ nhưng thiếu role**.

### Bước 7 — Tài liệu hóa phát hiện và đánh giá lại

Một báo cáo review ngắn có thể có cấu trúc:

```text
ID: SEC-01
Path/method: GET /api/admin/users
Hợp đồng: chỉ ROLE_ADMIN
Bằng chứng: /api/**.permitAll() đứng trước /api/admin/**.hasRole("ADMIN")
Rủi ro: HTTP authorization cho anonymous qua; tác động thực tế
        còn phụ thuộc service policy và dữ liệu handler trả về
Mức độ: Cao trong giả định không có bảo vệ bổ sung
Bản sửa: rule cụ thể và deny-by-default; không dùng wildcard permit
Kiểm thử:
  - anonymous bị chặn
  - VIEWER nhận 403
  - ADMIN nhận 200
  - /api/unlisted vẫn bị chặn
Kết quả sau sửa: có evidence MockMvc và HTTP trace
```

Không ghi password, cookie, access token, session ID hay hồ sơ người dùng thật vào issue/log. Đối với production, cần kế hoạch rollout và kiểm tra tác động: một deny-all mới có thể chặn endpoint cần thiết nếu hợp đồng còn thiếu. Đây là lý do lập matrix và chạy integration tests **trước** khi triển khai.

## 7. Phân biệt false positive và lỗi thật

### Trường hợp A — `permitAll` có thể đúng

`GET /actuator/health/liveness` phục vụ load balancer có thể được công khai theo chính sách hạ tầng, trong khi `/actuator/env`, `/actuator/heapdump` hoặc endpoint quản trị không được mở. Lỗi là `"/actuator/**".permitAll()` khi không đánh giá từng endpoint; không phải việc có một public liveness endpoint.

### Trường hợp B — Tắt CSRF có thể đúng với một chain bearer API

Một chain chỉ nhận token trong `Authorization` do non-browser client chủ động gắn, hoàn toàn stateless và không hỗ trợ cookie/Basic authentication có threat model khác web session. Có thể tắt CSRF **chỉ tại chain API đó** khi đã kiểm chứng. Nếu một trang SPA dùng cookie để truy cập chính API đó, phải đánh giá lại. **Hãy dựa vào cách truyền credential thực tế**, không dựa vào tên đường dẫn chứa `api`.

### Trường hợp C — `authenticated()` không phải lúc nào quá rộng

`GET /api/account/me` trả dữ liệu của **chính principal hiện tại** và không nhận ID tùy ý có thể hợp lý với `authenticated()`. Nhưng `GET /api/account/{id}` cho client chọn ID thì cần ownership/role policy bổ sung; kết luận phụ thuộc use case.

### Trường hợp D — `headers.disable()` có thể được bù ở gateway, nhưng phải chứng minh

Nếu ingress/gateway cưỡng chế header tương đương và test response cuối cùng xác nhận, mức độ rủi ro từ app-only config khác với app public không có proxy. Tuy vậy việc tắt tùy tiện ở app làm bảo vệ phụ thuộc môi trường triển khai; cần ownership và test không bị drift. Spring Security **không tự thêm CSP** khi để default headers bật.

### Trường hợp E — Nhiều filter chain không tự là lỗ hổng

Một chain `@Order(1)` cho `/api/**` và một chain catch-all xếp sau là kiến trúc hợp lệ. Sai lầm là chỉ nhìn chain API hoặc chỉ nhìn fallback mà không tính chain selection; thêm `anyRequest().denyAll()` vào một chain sai phạm vi không bảo vệ phần còn lại.

## 8. Checklist nghiệm thu khi review xong

- [ ] Đã đọc toàn bộ SecurityFilterChain và thứ tự, xác minh không có path lọt ngoài chain.
- [ ] Đã xác nhận chính sách method + path + role + owner/tenant cho mọi endpoint nhạy cảm.
- [ ] `permitAll` chỉ dành cho endpoint công khai được duyệt; không bị matcher bao quát che rule chặt.
- [ ] Rule còn lại dùng `denyAll` nếu chính sách vận hành yêu cầu whitelist; route mới thất bại an toàn.
- [ ] CSRF được giữ cho web cookie/session, ngoại lệ nếu có được chứng minh bằng mô hình client/credential.
- [ ] Security headers có bằng chứng trên response thực, không giả định CSP luôn có sẵn.
- [ ] Form login/logout/session fixation/timeout phù hợp với browser-based authentication nếu có.
- [ ] Method security và authorization ở tầng dữ liệu được kiểm thử qua lời gọi thực.
- [ ] Có test anonymous, sai role, có/thiếu CSRF, method không cho phép, route lạ, tenant/owner.
- [ ] Đã phân biệt 302/401/403 theo entry point; không xem 404/405 hoặc CSRF 403 thay thế test role.
- [ ] Không để lại credential demo, endpoint debug/actuator hoặc policy bypass trong môi trường thật.
- [ ] Có bằng chứng chạy test và kế hoạch rollout, rollback, audit logs được che dữ liệu nhạy cảm.

**Câu hỏi kiểm tra cuối bài:**

1. Vì sao `anyRequest().denyAll()` **bên trong** một `securityMatcher("/api/**")` không đủ để bảo vệ `/internal`?
2. Nếu `"/api/**".permitAll()` đứng trước `"/api/admin/**".hasRole("ADMIN")`, rule nào thắng và tại sao?
3. Một test POST trả 403 có chứng minh được role authorization không? Phải thêm test nào?
4. Nếu mọi request dùng bearer token từ header, `csrf.disable()` có nhất thiết nguy hiểm? Điều kiện nào khiến câu trả lời thay đổi?
5. Vì sao `@PreAuthorize` có thể không có tác dụng dù annotation xuất hiện trên method?
6. Vì sao phải kiểm tra những response header thật sự được browser nhận, thay vì chỉ kiểm source config?
7. Thêm một endpoint mới mà quên policy: `denyAll` và `authenticated` cho kết quả khác nhau ra sao?
8. Khi có nhiều chain, cách nào bảo đảm login endpoint và mọi route nằm trong một chain phù hợp?

## 9. Tài liệu để đối chiếu khi làm bài

- [Spring Security 6.5 — Authorize HTTP Requests (matcher order, permitAll, denyAll)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Java Configuration, securityMatcher vs requestMatchers](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html)
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — MockMvc integration & testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html)

Kết quả của một lần review tốt là **policy rõ ràng, rule thực sự được áp dụng, các lớp bảo vệ được giữ theo đúng mô hình xác thực, và bộ test có thể phát hiện khi một cấu hình mới vô tình mở quyền**.
