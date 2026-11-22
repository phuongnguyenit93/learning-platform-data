# Thứ tự khai báo và quy tắc khớp đầu tiên trong phân quyền HTTP (Spring Security)

> **Phạm vi:** phân quyền request HTTP trong ứng dụng Spring Security Servlet / Spring MVC, sử dụng `SecurityFilterChain` và `authorizeHttpRequests`. Mục tiêu: hiểu **quy tắc nào được chọn khi nhiều matcher cùng khớp**, tại sao rule đặt sai chỗ có thể làm lộ endpoint, và cách kiểm chứng bằng Java 17+ cùng Spring Boot.

## 1. Quy tắc gốc: xét theo thứ tự, lấy **match đầu tiên**

Trong cấu hình Spring Security kiểu:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Spring Security xét các cặp **`RequestMatcher → AuthorizationManager`** trong **thứ tự đã khai báo**, từ trên xuống dưới. Khi gặp matcher đầu tiên nhận diện request, hệ thống áp dụng **quy tắc phân quyền của matcher đó** và **không tiếp tục đi tìm một rule phía dưới chỉ vì user bị từ chối ở rule đầu**.

Ví dụ request `GET /api/admin/users`:

1. `/public/**` không khớp.
2. `/api/admin/**` khớp → bắt buộc có authority `ROLE_ADMIN` theo quy ước role mặc định.
3. Rule `/api/**` cũng có thể khớp về mặt đường dẫn, nhưng **không được xét** vì đã có match đầu tiên.
4. Nếu user chỉ có `ROLE_USER` → kết quả **DENY**, chứ **không quay xuống** rule `authenticated()` để được phép.

**Câu cần ghi nhớ:** *Spring Security không tự động chọn “rule cụ thể nhất” trong một danh sách đã khai báo sai thứ tự; thứ tự là một phần của chính sách bảo mật*. Tài liệu chính thức mô tả `AuthorizationFilter` xử lý các cặp này theo thứ tự và áp dụng **chỉ match đầu tiên**.

### Cách đọc cấu hình bằng câu điều kiện

~~~text
if path khớp "/public/**":
    permitAll
else if path khớp "/api/admin/**":
    require ROLE_ADMIN
else if path khớp "/api/**":
    require authenticated
else:
    denyAll
~~~

Đây là cách diễn giải **thứ tự ưu tiên** trong ví dụ, không có nghĩa Spring Security thực thi code `if/else` này nguyên văn.

**Hệ quả:** nếu một rule tổng quát đứng trước rule nhạy cảm, rule nhạy cảm có thể trở thành **không thể tới được** (*shadowed/unreachable rule*).

## 2. Ví dụ sai thứ tự làm mở quá rộng quyền quản trị

Xét cấu hình **sai**:

~~~java
// SAI: quy tắc tổng quát che mất quy tắc admin.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

Với request `GET /api/admin/users` từ Bob đã đăng nhập nhưng **không phải admin**:

- `/api/**` khớp ngay từ dòng đầu → chỉ cần `authenticated()`.
- Bob đã đăng nhập → được **ALLOW ở HTTP authorization**.
- `/api/admin/**` phía dưới **không bao giờ được xét** cho URL này.

Điều này có thể tạo lỗ hổng truy cập trái phép nếu service/controller không có lớp kiểm tra riêng. Đừng tự an ủi rằng “rule admin cụ thể hơn nên Spring sẽ ưu tiên nó”; Spring Security không tự sắp lại thứ tự khai báo thành độ cụ thể.

Cấu hình **đúng**:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Giờ đây user thường truy cập `/api/admin/users` sẽ bị chặn ngay ở rule admin. `/api/profile` không khớp admin, nên rơi vào `/api/**` và được phép nếu đã đăng nhập.

### So sánh hai thứ tự

| Request | User | Rule đầu tiên (sai) | Kết quả HTTP sai | Rule đầu tiên (đúng) | Kết quả đúng |
| --- | --- | --- | --- | --- | --- |
| `GET /api/admin/users` | Bob đã đăng nhập, thiếu admin | `/api/** → authenticated` | ALLOW | `/api/admin/** → hasRole("ADMIN")` | DENY |
| `GET /api/admin/users` | Carol có `ROLE_ADMIN` | `/api/** → authenticated` | ALLOW | `/api/admin/** → hasRole("ADMIN")` | ALLOW |
| `GET /api/profile` | Bob đã đăng nhập | `/api/** → authenticated` | ALLOW | `/api/** → authenticated` | ALLOW |
| `GET /unknown` | Bob đã đăng nhập | `anyRequest() → denyAll` | DENY | `anyRequest() → denyAll` | DENY |

Bảng giả định request đã vào đúng `SecurityFilterChain` và không có rào cản khác như CSRF, method security hoặc điều kiện nghiệp vụ. Một quyết định ALLOW ở HTTP **không chứng minh toàn bộ ứng dụng sẽ cho truy cập** nếu phía sau còn bộ kiểm tra khác.

## 3. “Khớp đầu tiên” không phải “quy tắc cho phép đầu tiên”

Đây là nhầm lẫn đặc biệt nguy hiểm.

Giả sử:

~~~java
.requestMatchers("/finance/**").hasAuthority("finance:read")
.requestMatchers("/finance/**").hasRole("MANAGER")
~~~

User có `ROLE_MANAGER` nhưng **không** có `finance:read`:

1. Matcher đầu tiên `/finance/**` khớp.
2. Check `hasAuthority("finance:read")` là **DENY**.
3. Spring Security **không thử matcher thứ hai** để tìm một ALLOW khác.

Hai dòng trên **không** tạo logic “có permission hoặc là manager”, cũng **không** tạo logic “phải có cả permission và manager”. Nó chỉ chọn rule đầu tiên.

Nếu nghiệp vụ muốn **OR** (có một trong hai quyền), có thể dùng:

~~~java
.requestMatchers("/finance/**")
    .hasAnyAuthority("finance:read", "ROLE_MANAGER")
~~~

Nếu muốn **AND** (có đủ hai authority), trên các phiên bản hỗ trợ `hasAllAuthorities` có thể dùng:

~~~java
.requestMatchers("/finance/**")
    .hasAllAuthorities("finance:read", "ROLE_MANAGER")
~~~

Các đoạn trên là **fragment** đặt trong `authorizeHttpRequests`. Khi chính sách có các điều kiện theo tài nguyên như tenant/ownership, dùng `access(customAuthorizationManager)` hoặc method/domain policy thay vì cố biểu diễn bằng hai matcher trùng nhau.

**Chốt lại:**

- **Một matcher được chọn:** một quy tắc cho request ở tầng HTTP.
- **Một rule có thể yêu cầu nhiều điều kiện:** kết hợp chúng **bên trong cùng rule/manager**.
- **Nhiều matcher trùng nhau không tự tạo OR/AND.**

## 4. Thứ tự ưu tiên chuẩn khi có nhiều nhóm endpoint

Một ví dụ API quản lý tài liệu:

| Đường dẫn | Ý nghĩa | Chính sách mong muốn |
| --- | --- | --- |
| `/public/**` | Nội dung công khai | `permitAll()` |
| `/api/admin/**` | Quản trị hệ thống | `hasRole("ADMIN")` |
| `/api/reports/secret` | Báo cáo nhạy cảm | `hasAuthority("report:read")` |
| `/api/reports/**` | Báo cáo thông thường | `authenticated()` |
| `/api/**` | API chưa có quyền cụ thể | `denyAll()` |
| Mọi đường dẫn khác | Không được khai báo | `anyRequest().denyAll()` |

Thứ tự an toàn là:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/reports/secret").hasAuthority("report:read")
    .requestMatchers("/api/reports/**").authenticated()
    .requestMatchers("/api/**").denyAll()
    .anyRequest().denyAll()
);
~~~

Trong ví dụ này:

- `/api/admin/users` chạm rule admin trước khi tới `/api/**`.
- `/api/reports/secret` chạm rule cần permission đọc báo cáo trước khi tới `/api/reports/**`.
- `/api/reports/overview` chạm rule báo cáo chung.
- `/api/unknown-feature` bị rule `/api/** → denyAll()` chặn.
- `/outside` không khớp bất kỳ nhóm trước nào và bị `anyRequest().denyAll()` chặn.

**Vì sao có cả `/api/**.denyAll()` và `anyRequest().denyAll()`?** Trong ví dụ, chúng tương đương về kết quả cho endpoint không được liệt kê; rule `/api/**` giúp người đọc thấy rõ các API chưa phân loại đều bị chặn, còn `anyRequest` là chốt tổng quát. Nếu không cần phân biệt nhóm, có thể chỉ giữ fallback cuối.

### Quy tắc thiết kế thứ tự

1. **Ngoại lệ cụ thể trước quy tắc bao quát**: `/api/admin/**` trước `/api/**`.
2. **Quy tắc kiểm tra permission nhạy cảm trước điều kiện đăng nhập chung**: `/api/reports/secret` trước `/api/reports/**`.
3. **Đường công khai có danh sách rõ ràng**: chỉ dùng `permitAll()` với endpoint thực sự công khai.
4. **Fallback ở cuối**: `anyRequest().denyAll()` để không vô tình mở endpoint mới.
5. **Tránh matcher lặp vô nghĩa**: một matcher sau đã bị rule trước che mất thường là dấu hiệu sai thứ tự.
6. **Kiểm thử các vùng giao nhau**, không chỉ đường dẫn điển hình, vì lỗi xuất hiện khi hai hoặc nhiều mẫu cùng khớp.

Không có công thức “độ dài đường dẫn dài hơn thì luôn ưu tiên”. **Thứ tự thực tế của DSL** mới quyết định khi có chồng lấn.

## 5. Match theo HTTP method: thứ tự vẫn quan trọng

Trong API REST, cùng path pattern có thể cần quyền khác nhau cho từng phương thức:

- `GET /api/documents/42` → `document:read`.
- `POST /api/documents` → `document:create`.
- `PATCH /api/documents/42` → `document:write`.
- `DELETE /api/documents/42` → `document:delete`.

Có thể dùng matcher với `HttpMethod`:

~~~java
import org.springframework.http.HttpMethod;

// Fragment trong authorizeHttpRequests:
.requestMatchers(HttpMethod.GET, "/api/documents/**")
    .hasAuthority("document:read")
.requestMatchers(HttpMethod.POST, "/api/documents")
    .hasAuthority("document:create")
.requestMatchers(HttpMethod.PATCH, "/api/documents/**")
    .hasAuthority("document:write")
.requestMatchers(HttpMethod.DELETE, "/api/documents/**")
    .hasAuthority("document:delete")
.requestMatchers("/api/documents/**")
    .denyAll()
~~~

Rule cuối chặn những tổ hợp path/method chưa được cấp quyền. Nếu ứng dụng phải hỗ trợ cả URL collection `/api/documents` và đường dẫn con `/api/documents/**`, cần xác nhận matcher có bao phủ đúng ý định trong **phiên bản Spring Security/Spring MVC đang dùng**; không phỏng đoán về dấu gạch chéo, đường dẫn gốc hoặc path-pattern engine.

**Sai thứ tự:**

~~~java
// SAI: GET đã rơi vào rule chung trước.
.requestMatchers("/api/documents/**").authenticated()
.requestMatchers(HttpMethod.GET, "/api/documents/**")
    .hasAuthority("document:read")
~~~

Một user đăng nhập thiếu `document:read` vẫn có thể qua tầng HTTP nếu đường dẫn đã được rule rộng đầu tiên nhận diện.

**Lưu ý quan trọng về HTTP method:** matcher của Spring Security không tự quyết định business action; endpoint update cần check thêm owner/tenant/trạng thái. Với `POST`, `PUT`, `PATCH` và `DELETE`, **CSRF** có thể từ chối request độc lập với authorization nếu ứng dụng dùng cơ chế cookie/session. Do đó, test method-specific rule phải cung cấp token CSRF hợp lệ khi chính sách yêu cầu; đừng kết luận 403 do rule từ một request thiếu CSRF.

## 6. Java 17 thuần: mô phỏng first-match và quy tắc bị che khuất

Chương trình Java độc lập dưới đây chỉ mô phỏng **cách chọn rule theo thứ tự**; nó không thay thế Spring Security. Mỗi `Rule` có `matches` để nhận diện request và `allows` để kiểm quyền. Điều khác biệt then chốt: khi rule đầu tiên khớp, chương trình **trả kết quả ngay**, kể cả kết quả `false`.

Tạo tệp **`FirstMatchDemo.java`**:

~~~java
import java.util.List;
import java.util.function.Predicate;

public class FirstMatchDemo {

    record Request(String path, boolean authenticated, boolean admin) {}

    record Rule(
        String name,
        Predicate<Request> matches,
        Predicate<Request> allows
    ) {}

    static boolean authorize(List<Rule> rules, Request request) {
        for (Rule rule : rules) {
            if (rule.matches().test(request)) {
                return rule.allows().test(request);
            }
        }
        return false; // Không rule nào khớp -> default deny của ví dụ.
    }

    public static void main(String[] args) {
        Rule broad = new Rule(
            "/api/**",
            r -> r.path().startsWith("/api/"),
            Request::authenticated
        );

        Rule admin = new Rule(
            "/api/admin/**",
            r -> r.path().startsWith("/api/admin/"),
            Request::admin
        );

        Request bob = new Request("/api/admin/users", true, false);
        Request carol = new Request("/api/admin/users", true, true);
        Request stranger = new Request("/other", true, false);

        System.out.println("bad Bob: "
            + authorize(List.of(broad, admin), bob));
        System.out.println("good Bob: "
            + authorize(List.of(admin, broad), bob));
        System.out.println("good Carol: "
            + authorize(List.of(admin, broad), carol));
        System.out.println("unmatched: "
            + authorize(List.of(admin, broad), stranger));
    }
}
~~~

Biên dịch/chạy bằng **JDK 17+** trong thư mục chứa tệp:

~~~bash
javac FirstMatchDemo.java
java FirstMatchDemo
~~~

**Stdout chính xác:**

~~~text
bad Bob: true
good Bob: false
good Carol: true
unmatched: false
~~~

Giải thích:

- **Bad Bob = true**: rule `/api/**` đứng trước và chỉ hỏi Bob đã đăng nhập chưa.
- **Good Bob = false**: rule admin đứng trước, khớp và từ chối; không được thử tiếp rule rộng.
- **Good Carol = true**: Carol có quyền admin nên vượt qua rule đầu.
- **Unmatched = false**: ví dụ chủ động chọn default deny khi không match.

Đây là một mô phỏng `Predicate`, không dùng matcher thực của Spring, không có khái niệm authentication filter hay context path. Ví dụ có giá trị vì chứng minh **luồng kiểm tra**, còn matcher thực tế phải được thử bằng integration test.

## 7. Ví dụ Spring Boot Java 17+ chạy được

Tạo dự án **Spring Boot 3.x** (Java 17+, Maven), chọn **Spring Web** và **Spring Security**. Ví dụ dùng **một `SecurityFilterChain` duy nhất** để cô lập quy tắc khớp đầu tiên, tránh phụ thuộc thứ tự chain.

Tạo tệp:

`src/main/java/com/example/order/RuleOrderApplication.java`

~~~java
package com.example.order;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RuleOrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(RuleOrderApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .requestMatchers("/api/reports/secret")
                .hasAuthority("report:read")
            .requestMatchers("/api/reports/**").authenticated()
            .requestMatchers("/api/**").denyAll()
            .anyRequest().denyAll()
        ).httpBasic(Customizer.withDefaults());

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
            .authorities("report:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .roles("USER")
            .build();

        UserDetails carol = User.withUsername("carol")
            .password(encoder.encode("demo789"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, carol);
    }

    @RestController
    static class Api {

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/api/admin/users")
        String adminUsers() {
            return "admin users";
        }

        @GetMapping("/api/reports/secret")
        String secret() {
            return "secret report";
        }

        @GetMapping("/api/reports/overview")
        String overview() {
            return "report overview";
        }

        @GetMapping("/api/unknown")
        String unknown() {
            return "should not be reached";
        }

        @GetMapping("/outside")
        String outside() {
            return "should not be reached";
        }
    }
}
~~~

### Diễn giải authorities

- `alice` có authority chính xác `report:read`, không tự có `ROLE_ADMIN`.
- `bob` có `ROLE_USER` do `roles("USER")` tạo.
- `carol` có `ROLE_ADMIN` do `roles("ADMIN")` tạo. **`roles("ADMIN")` không tự tạo `report:read`**.
- Rule `hasRole("ADMIN")` theo quy ước mặc định yêu cầu `ROLE_ADMIN`.
- Rule `hasAuthority("report:read")` yêu cầu đúng chuỗi `report:read`.

Không cần trộn hai loại permission vào một rule nếu bài toán chỉ muốn minh họa đường chồng lấn. Ở dự án thật, cần thiết kế quyền trên từng tài nguyên, chứ không dùng một role để quyết định mọi hành động toàn hệ thống.

### Chạy ứng dụng

Tại thư mục dự án:

~~~bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
~~~

Khi server sẵn sàng ở cổng mặc định `8080`, thử:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/admin/users
curl -i -u bob:demo456 http://localhost:8080/api/admin/users
curl -i -u carol:demo789 http://localhost:8080/api/admin/users
curl -i -u bob:demo456 http://localhost:8080/api/reports/overview
curl -i -u bob:demo456 http://localhost:8080/api/reports/secret
curl -i -u alice:demo123 http://localhost:8080/api/reports/secret
curl -i -u carol:demo789 http://localhost:8080/api/reports/secret
curl -i -u bob:demo456 http://localhost:8080/api/unknown
curl -i -u bob:demo456 http://localhost:8080/outside
~~~

| Request | Trạng thái HTTP kỳ vọng | Rule được chọn trước tiên |
| --- | --- | --- |
| Public, anonymous | **200**, body `pong` | `/public/** → permitAll` |
| Admin, anonymous | **401** với HTTP Basic | `/api/admin/** → hasRole("ADMIN")`; chưa xác thực |
| Admin, Bob | **403** | `/api/admin/**`; thiếu `ROLE_ADMIN` |
| Admin, Carol | **200**, body `admin users` | `/api/admin/**`; có `ROLE_ADMIN` |
| Overview, Bob | **200**, body `report overview` | `/api/reports/** → authenticated` |
| Secret, Bob | **403** | `/api/reports/secret`; thiếu `report:read` |
| Secret, Alice | **200**, body `secret report` | `/api/reports/secret`; có `report:read` |
| Secret, Carol | **403** | Rule secret, thiếu `report:read` dù Carol là ADMIN |
| Unknown API, Bob | **403** | `/api/** → denyAll` |
| Outside, Bob | **403** | `anyRequest() → denyAll` |

Kết quả kỳ vọng cho **HTTP Basic của ví dụ**, giả định không thêm SecurityFilterChain hoặc bộ lọc bảo mật khác. Với form login, yêu cầu chưa đăng nhập thường được chuyển hướng tới trang đăng nhập thay vì 401. Những endpoint trên đều là GET, không thay đổi dữ liệu; nếu chuyển thành API ghi, phải thiết kế CSRF và authorization phù hợp.

**An toàn demo:** ba mật khẩu nằm trong mã ví dụ chỉ để học. Với môi trường thật, dùng kho định danh tin cậy, quản lý bí mật phù hợp và chỉ truyền HTTP Basic qua **HTTPS**.

## 8. Hai tầng “first matching”: chọn filter chain và chọn rule bên trong

Đây là phân biệt cần thiết khi hệ thống có **nhiều `SecurityFilterChain`**.

**Tầng A — `FilterChainProxy` chọn chain:** Spring Security có thể chứa nhiều chain, mỗi chain có một `RequestMatcher` tổng thể. Các chain được xét theo mức ưu tiên (ví dụ `@Order`). **Chain đầu tiên khớp request được chọn**; các chain tiếp theo không “bổ sung” filter hay policy cho cùng request đó.

**Tầng B — `AuthorizationFilter` trong chain đã chọn:** bên trong chain, các `requestMatchers(...)` của `authorizeHttpRequests` được xét **theo thứ tự khai báo**. **Rule đầu tiên khớp** được dùng.

~~~text
Request GET /api/admin/users
   |
   v
FilterChainProxy
   |
   +-- SecurityFilterChain @Order(1) securityMatcher("/api/**")
   |        MATCH -> chọn chain API
   |             |
   |             +-- authorizeHttpRequests:
   |                   "/api/admin/**" -> hasRole("ADMIN")  [MATCH]
   |                   "/api/**"       -> authenticated()  [KHÔNG XÉT]
   |
   +-- fallback SecurityFilterChain khác               [KHÔNG CHỌN]
~~~

**`http.securityMatcher(...)` khác `authorizeHttpRequests().requestMatchers(...)`:**

| API | Nơi áp dụng | Tác dụng |
| --- | --- | --- |
| `http.securityMatcher("/api/**")` | Chọn **cả SecurityFilterChain** | Nếu request không khớp, chain này không được dùng |
| `authorizeHttpRequests().requestMatchers("/api/admin/**")` | Chọn **một rule trong chain đã được chọn** | Chỉ xét sau khi đã vào chain |
| `anyRequest()` | Fallback **bên trong chain đó** | Không tự động bảo vệ các request không khớp `securityMatcher` của chain |

Nếu chỉ cấu hình duy nhất một chain với `securityMatcher("/api/**")`, các request không nằm dưới `/api/**` có thể **không được bảo vệ bởi Spring Security** nếu không có chain khác khớp. Vì vậy tài liệu chính thức khuyến nghị có **fallback chain không đặt `securityMatcher`**, để phủ toàn bộ ứng dụng.

### Ví dụ cấu hình nhiều chain (fragment)

~~~java
// Fragment trong lớp @Configuration, dùng Java 17+ và Spring Security.
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().denyAll()
    );
    return http.build();
}
~~~

Các import tương ứng gồm `org.springframework.context.annotation.Bean`, `org.springframework.core.annotation.Order`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.security.config.Customizer` và `org.springframework.security.web.SecurityFilterChain`. Đây là fragment cấu hình **thay thế ví dụ một chain**, không đặt thêm cạnh ví dụ Boot ở mục 7 mà không xem xét trùng bean.

Trong chain API, `anyRequest()` chỉ nói về **những request đã được chọn vào chain API**; nó không bao phủ `/outside`. Fallback chain xử lý request chưa vào API chain. Nếu đổi thứ tự ưu tiên để fallback tổng quát được xét trước, API chain có thể không được sử dụng và các rule chi tiết bị che khuất.

### Không nhầm với thứ tự security filters

Trong một chain, các filter như authentication filter và authorization filter chạy theo thứ tự được Spring Security xây dựng. **Filter order** là vấn đề khác với **thứ tự matcher/rule** đang học. Không sửa filter order để giải quyết một rule `requestMatchers("/api/**")` đặt trước `/api/admin/**`.

## 9. Matcher thực tế: đường dẫn, phương thức và servlet dispatch

### Path pattern không phải một chuỗi URL tùy ý

`requestMatchers("/api/**")` nhận các pattern path và chuyển cho cơ chế `RequestMatcher` phù hợp. Hành vi có thể phụ thuộc version, Spring MVC integration và kiểu matcher được chọn. Vì vậy:

- Test cả `/api/admin`, `/api/admin/` và `/api/admin/users` nếu chúng có ý nghĩa trong routing thật.
- Test trường hợp URL chứa ký tự đặc biệt, đường dẫn đã được chuẩn hóa, encoded path và nhiều servlet.
- Không giả định tên query parameter là một phần của pattern path. Nếu `/api/reports?private=true` mang ý nghĩa khác `/api/reports?private=false`, cần chính sách dành riêng cho ngữ cảnh request chứ không hy vọng chỉ path matcher phân biệt chúng.
- Khi dùng context path, reverse proxy hoặc URL rewrite, kiểm tra phần path thực tế mà Spring Security thấy.
- Trong ứng dụng nhiều servlet, xem lại `MvcRequestMatcher`, `PathPatternRequestMatcher` hoặc matcher chỉ rõ servlet path theo phiên bản đang dùng.

**Không có sự ưu tiên mặc định theo “matcher dài hơn”.** Một pattern ngắn nhưng đặt trước có thể che một pattern dài hơn.

### Method matcher và rule chung

~~~java
// Fragment:
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("orders:read")
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("orders:write")
.requestMatchers("/api/orders/**").denyAll()
~~~

Nếu đặt dòng `requestMatchers("/api/orders/**").authenticated()` lên đầu, mọi request thuộc nhóm đó có thể đi qua rule “chỉ cần đăng nhập” và bỏ qua GET/POST-specific permissions.

### FORWARD, ERROR và ASYNC dispatch

Servlet có thể có request dispatch ngoài `REQUEST` thông thường. Tài liệu Spring Security minh họa cách khai báo `dispatcherTypeMatchers(FORWARD, ERROR).permitAll()` **khi ứng dụng thật sự cần** cho rendering/error pages. Nhưng khai báo quá rộng có thể tạo ngoại lệ quyền không mong muốn. Hãy xác định mục tiêu, thứ tự và kiểm thử các dispatch type trong chính ứng dụng; không tự động sao chép `permitAll` lên mọi dispatch.

### Nhiều SecurityFilterChain và cache tình trạng đăng nhập

Nếu route vào chain khác, cơ chế xác thực có thể khác: HTTP Basic, form login, bearer token, session... Vì vậy, khi URL có 401/403 lạ, kiểm tra **chain nào khớp trước**, không chỉ đọc các rule trong chain mình tưởng đang được dùng. Với authority đã cấp, kiểm tra `Authentication#getAuthorities()` từ nguồn tin cậy; không dựa vào role do frontend gửi.

## 10. Kiểm thử để bắt lỗi thứ tự trước khi triển khai

Một tập test hữu ích nên có cả **cho phép đúng** và **từ chối đúng**. Kiểm thử tối thiểu theo ví dụ:

| Test | Người gọi | Endpoint | Mong đợi |
| --- | --- | --- | --- |
| Public route | Anonymous | `GET /public/ping` | 200 |
| Admin bị chặn | Bob `ROLE_USER` | `GET /api/admin/users` | 403 |
| Admin được phép | Carol `ROLE_ADMIN` | `GET /api/admin/users` | 200 |
| Report nhạy cảm bị chặn | Bob `ROLE_USER` | `GET /api/reports/secret` | 403 |
| Report nhạy cảm được phép | Alice `report:read` | `GET /api/reports/secret` | 200 |
| Rule bao quát có hiệu lực | Bob | `GET /api/reports/overview` | 200 |
| API chưa khai báo bị chặn | Bob | `GET /api/unknown` | 403 |
| URL ngoài phạm vi bị chặn | Bob | `GET /outside` | 403 |
| Admin không tự có report permission | Carol | `GET /api/reports/secret` | 403 |

Để chạy với `MockMvc`, thêm dependency **`spring-security-test`** vào test classpath, dùng `@SpringBootTest` + `@AutoConfigureMockMvc` và tạo test trong project có lớp Boot ở mục 7. Đây là **fragment test class** (cần imports và package tương ứng):

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class RuleOrderSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(roles = "USER")
    void nonAdminCannotCallAdmin() throws Exception {
        mvc.perform(get("/api/admin/users"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanCallAdmin() throws Exception {
        mvc.perform(get("/api/admin/users"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "USER")
    void nonReaderCannotCallSecret() throws Exception {
        mvc.perform(get("/api/reports/secret"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void readerCanCallSecret() throws Exception {
        mvc.perform(get("/api/reports/secret"))
            .andExpect(status().isOk());
    }
}
~~~

Các import đáng chú ý: `org.springframework.boot.test.context.SpringBootTest`, `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc`, `org.springframework.beans.factory.annotation.Autowired`, `org.springframework.test.web.servlet.MockMvc`, `org.springframework.security.test.context.support.WithMockUser`, `org.junit.jupiter.api.Test`, `org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get` và `org.springframework.test.web.servlet.result.MockMvcResultMatchers.status` (hai import cuối thường dùng `static`).

**Vì sao test âm tính là then chốt?** Nếu vô tình chuyển `/api/**.authenticated()` lên trên rule admin hoặc secret, test 200 của admin/Alice vẫn có thể **đỗ**, nhưng test 403 của Bob sẽ **thất bại**. Đây là lý do test “từ chối đúng” quan trọng không kém test “cho phép đúng”.

### Những test bổ sung đáng làm

- Request **không có authentication** đến admin/report.
- Request ở **giao điểm hai pattern**, ví dụ prefix admin và prefix API.
- Mỗi **HTTP method** trên cùng resource path.
- Một URL chưa có controller hoặc mới được thêm vào: không được mở do rule mặc định quá rộng.
- Nhiều chain: URL chỉ khớp API chain, chỉ khớp fallback, hoặc khớp cả hai.
- Resource instance khác tenant hoặc khác owner: test tại method/domain layer.
- Dispatch `FORWARD/ERROR` nếu ứng dụng thật dùng và đã thêm `dispatcherTypeMatchers`.

Đừng chỉ kiểm tra status 200; kiểm tra nội dung response và side effect phù hợp để chứng minh đúng endpoint chạy, đặc biệt khi hệ thống có router/gateway phức tạp.

## 11. Cách debug khi rule dường như “không hoạt động”

Một quy trình chẩn đoán hữu dụng:

1. **Xác định request thật:** HTTP method, path, context path, dispatcher type, URL được proxy rewrite.
2. **Xác định chain đầu tiên khớp:** rà `@Order` và `http.securityMatcher` ở tất cả `SecurityFilterChain`.
3. **Trong chain đó, liệt kê rule đúng thứ tự:** đánh số từ 1, mô tả matcher và policy đi kèm.
4. **Tính matcher đầu tiên khớp request:** không bỏ qua dòng rộng như `/api/**` hay `/**`.
5. **Đánh giá policy của dòng đầu đó:** user đã xác thực chưa, có role/authority thực tế nào, manager custom có điều kiện gì.
6. **Xác định điểm trả lỗi:** HTTP `AuthorizationFilter`, method security, CSRF filter, authentication entry point hay xử lý nghiệp vụ. 403 không phải lúc nào cũng do thiếu role.
7. **Bổ sung test phủ định** để khóa chính sách, rồi mới thay đổi thứ tự/chính sách.

Có thể bật log Spring Security ở môi trường phát triển để xem thêm quá trình chọn filter chain và authorization, chẳng hạn cấu hình logging cho package `org.springframework.security` ở mức `DEBUG` hoặc `TRACE`. Tuy nhiên, log có thể chứa dữ liệu bảo mật: chỉ bật có kiểm soát, không ghi credential/token vào log và tắt mức quá chi tiết khi không cần.

**Không nên “sửa” lỗi 403 bằng cách di chuyển `permitAll()` lên đầu hoặc chèn `.anyRequest().permitAll()`**. Những thay đổi như vậy có thể vô hiệu hóa nhiều rule quan trọng.

## 12. Bảng các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Đặt `/api/**.authenticated()` trước `/api/admin/**.hasRole(...)` | User thường có thể qua HTTP check cho admin | Đưa admin lên trước |
| Đặt `/reports/**` trước `/reports/secret` | Rule báo cáo nhạy cảm bị che | Đưa secret lên trước |
| Viết hai matcher cùng path để mong OR | Rule thứ hai không được xét | Dùng một rule có `hasAnyAuthority` hoặc manager tổng hợp |
| Viết hai matcher cùng path để mong AND | Không kết hợp điều kiện như ý | Dùng một rule kiểm đủ điều kiện |
| Cho rằng deny sẽ “thử rule sau” | Phát sinh giả định sai về policy | Nhớ **first matching**, không phải first granting |
| Đặt `/**.permitAll()` lên đầu | Che mọi quy tắc sau | Chỉ công khai endpoint có chủ đích |
| Đặt `anyRequest().authenticated()` cho mọi URL chưa rõ | API mới có thể được mở với bất kỳ tài khoản đăng nhập | Chọn fallback `denyAll()` khi phù hợp |
| Chỉ cấu hình chain có `securityMatcher("/api/**")` | URL khác có thể không được Spring Security bảo vệ | Thêm chain fallback không giới hạn |
| Cho rằng `anyRequest` của API chain bao phủ cả `/outside` | Hiểu sai phạm vi chain | Phân biệt hai tầng matcher |
| Chỉ test request admin được 200 | Không phát hiện user thường lọt qua | Test cả 200 lẫn 403 |
| Bỏ qua HTTP method và CSRF | Đánh giá sai nguyên nhân 403 hoặc mở quyền ghi | Test method-specific và CSRF |
| Chỉ bảo vệ HTTP, không xét owner/tenant | Người dùng có quyền tuyến URL nhưng đọc sai bản ghi | Bổ sung kiểm tra theo resource instance |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Với `requestMatchers("/api/**").authenticated()` trước `requestMatchers("/api/admin/**").hasRole("ADMIN")`, Bob đã đăng nhập nhưng không là admin gọi `/api/admin/users`. Rule nào được dùng?  
**Trả lời:** `/api/**.authenticated()`; đây là lỗ hổng thứ tự vì rule admin bị che.

**Câu 2.** Nếu rule đầu đã khớp nhưng trả DENY, Spring Security có tiếp tục tìm một rule thứ hai để cho phép không?  
**Trả lời:** **Không** trong cơ chế `authorizeHttpRequests` first matching rule.

**Câu 3.** Hai dòng cùng matcher `/finance/**`, một `hasAuthority("finance:read")` và một `hasRole("MANAGER")` tạo logic OR không?  
**Trả lời:** Không. Dùng `hasAnyAuthority("finance:read", "ROLE_MANAGER")` hoặc một manager kết hợp.

**Câu 4.** `/api/reports/secret` có hai matcher: riêng secret và chung `/api/reports/**`. Đặt dòng nào trước?  
**Trả lời:** Dòng riêng secret trước, vì cần permission nhạy cảm hơn.

**Câu 5.** `anyRequest().denyAll()` có bắt URL ngoài `securityMatcher("/api/**")` của chain đó không?  
**Trả lời:** **Không**. Nó chỉ áp dụng sau khi chain đã được chọn.

**Câu 6.** Vì sao cần test user không phải admin gọi endpoint admin?  
**Trả lời:** Để phát hiện trường hợp rule rộng đứng trước khiến request bị cho phép ngoài ý muốn, trong khi test admin được 200 vẫn có thể đỗ.

**Câu 7.** Đặt rule `/api/docs/**.authenticated()` trước matcher `HttpMethod.DELETE` cùng path có an toàn không?  
**Trả lời:** Không, nếu DELETE phải cần `document:delete`. Rule broad sẽ che rule chuyên biệt.

**Câu 8.** Nếu có nhiều `SecurityFilterChain`, thứ tự ưu tiên nằm ở đâu?  
**Trả lời:** `FilterChainProxy` chọn chain đầu tiên khớp theo ưu tiên; trong chain đã chọn, `AuthorizationFilter` chọn rule đầu tiên khớp theo thứ tự khai báo.

**Ghi nhớ:** **Thứ tự là chính sách**. Với các matcher có thể giao nhau, rule **cụ thể và nhạy cảm** phải được khai báo **trước** rule bao quát; một khi matcher đầu tiên khớp, việc ALLOW/DENY được quyết định theo rule đó. Luôn có fallback **default deny** phù hợp và kiểm thử cả người có quyền lẫn người thiếu quyền.

## Tài liệu chính thức

- Spring Security — Authorize HTTP Requests (thứ tự các cặp matcher/rule): https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Java Configuration (nhiều SecurityFilterChain, securityMatcher và requestMatchers): https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — Servlet Architecture (FilterChainProxy và security filters): https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security 6.5 — HttpSecurity API (lưu ý thứ tự matchers): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/builders/HttpSecurity.html
- Spring Security — Method Security (phân quyền ở service sau HTTP): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
