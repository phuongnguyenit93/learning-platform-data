# Origin gồm giao thức, hostname và cổng trong CORS

Frontend chạy ở `http://localhost:5173` gọi API Spring Boot tại `http://localhost:8080`. Hai ứng dụng ở cùng máy, cùng hostname `localhost`, cùng giao thức HTTP, nhưng trình duyệt vẫn xem chúng là **khác origin** vì số cổng khác. Tương tự, `https://shop.example.test` không cùng origin với `http://shop.example.test` vì giao thức khác, và `https://api.example.test` không cùng origin với `https://shop.example.test` vì hostname khác.

Đó là khái niệm nền tảng của **Cross-Origin Resource Sharing (CORS)**: đối với URL HTTP(S), origin được xác định bằng **giao thức (scheme), hostname và cổng hiệu lực (effective port)**. CORS giúp website đích công bố ngoại lệ cho những script từ origin khác được quyền đọc response theo chính sách của browser; CORS **không thay thế** việc xác thực người dùng, phân quyền hay bảo vệ CSRF.

Bài thuộc nhóm **CORS** của **Spring Security - fundamentals**, dùng Java 17+, Spring Boot 3.3.x và Spring Security 6.3.x với Servlet/Spring MVC. Chúng ta sẽ tính origin, so sánh URL và site, đọc header HTTP, hiểu preflight, cấu hình CORS chính xác và kiểm thử những thay đổi chỉ một thành phần scheme, hostname hoặc port.

## 1. Định nghĩa và ba thành phần origin

Với một URL HTTP(S) bình thường:

~~~text
https://app.example.test:8443/orders?page=2#summary
└─┬─┘ └─────────┬──────┘ └┬─┘ └───────────┬───────┘
scheme        hostname    port       path/query/fragment

Origin = (scheme, hostname, effective port)
       = https://app.example.test:8443
~~~

- **Scheme**: giao thức URL, điển hình là `http` hoặc `https`.
- **Hostname**: ví dụ `app.example.test`, `localhost`, `127.0.0.1`, `api.example.test`.
- **Effective port**: cổng được ghi rõ, hoặc cổng mặc định nếu URL không ghi.

**Không thuộc origin:** path (`/orders`), query (`?page=2`), fragment (`#summary`), tên Controller, tên method HTTP, trạng thái đăng nhập, quyền người dùng. Path có thể ảnh hưởng routing và phân quyền trên server, nhưng không đổi origin của URL.

Dùng bộ ba này để so sánh hai URL:

~~~text
same-origin = scheme giống nhau
          AND hostname giống nhau
          AND effective port giống nhau
~~~

Đây là ý tưởng sau khi trình duyệt **chuẩn hóa URL/origin theo tiêu chuẩn**, không phải phép so sánh trực tiếp chuỗi đầu vào chưa chuẩn hóa.

## 2. Bảng so sánh URL cùng origin

Lấy URL tham chiếu `https://shop.example.test/cart`.

| URL thứ hai | Giao thức | Hostname | Cổng hiệu lực | Cùng origin? |
| --- | --- | --- | --- | :---: |
| `https://shop.example.test/orders` | https | shop.example.test | 443 | ✅ |
| `https://shop.example.test/cart?item=1` | https | shop.example.test | 443 | ✅ |
| `https://shop.example.test:443/checkout` | https | shop.example.test | 443 | ✅ |
| `https://shop.example.test:8443/cart` | https | shop.example.test | 8443 | ❌ |
| `http://shop.example.test/cart` | http | shop.example.test | 80 | ❌ |
| `http://shop.example.test:443/cart` | http | shop.example.test | 443 | ❌ |
| `https://api.example.test/cart` | https | api.example.test | 443 | ❌ |
| `https://www.shop.example.test/cart` | https | www.shop.example.test | 443 | ❌ |
| `https://SHOP.example.test/cart` | https | shop.example.test sau chuẩn hóa | 443 | ✅ |

Từng lý do:

- URL chỉ khác **path/query** vẫn có thể cùng origin.
- `:443` trên HTTPS là cổng mặc định, nên `https://shop.example.test:443` tương đương origin `https://shop.example.test`.
- `:8443` khác 443, nên origin khác dù hostname giống.
- HTTP và HTTPS không cùng origin ngay cả khi hostname hoặc cổng số học trùng.
- Hai hostname như `shop.example.test` và `api.example.test` không tự cùng origin dù cùng đăng ký dưới `example.test`.
- DNS phân giải hai hostname tới cùng IP **không** khiến chúng cùng origin.

### Cổng mặc định cần nhớ

~~~text
http://example.test      = http://example.test:80
https://example.test     = https://example.test:443

http://example.test:443  != https://example.test:443
https://example.test:80  != https://example.test
~~~

Dấu `=` ở đây chỉ có nghĩa **cùng origin** đối với URL HTTP(S), không khẳng định hai URL có cùng chuỗi văn bản hoặc cùng cách server vận hành.

## 3. Localhost, 127.0.0.1 và frontend dev server

Một dự án có thể chạy Vite ở `http://localhost:5173` và Spring Boot ở `http://localhost:8080`. Vì port khác nhau nên script trong trang Vite gọi API Spring là request cross-origin.

| Frontend | API | Cùng origin? | Nguyên nhân |
| --- | --- | :---: | --- |
| `http://localhost:5173` | `http://localhost:8080` | ❌ | Port khác |
| `http://localhost:5173` | `http://localhost:5173/api` | ✅ | Chỉ path khác |
| `http://localhost` | `http://localhost:80` | ✅ | Port 80 mặc định |
| `http://localhost:8080` | `http://127.0.0.1:8080` | ❌ | Hostname khác |
| `http://localhost:8080` | `https://localhost:8080` | ❌ | Scheme khác |
| `https://app.example.test` | `https://api.example.test` | ❌ | Hostname khác |

**`localhost` và `127.0.0.1` không cùng hostname**, dù có thể tới cùng thiết bị. Quy tắc origin không tra DNS để xác minh hai host cuối cùng có dẫn tới cùng IP hay không.

Có thể dùng **dev proxy**: browser chỉ gọi `http://localhost:5173/api/orders`, còn dev server proxy request nội bộ tới `http://localhost:8080/api/orders`. Lúc này URL mà browser truy cập có cùng origin với trang frontend, nên browser không cần CORS cho kết nối đó. Dịch vụ backend vẫn ở port 8080; browser chỉ không giao tiếp trực tiếp với nó.

Đừng dùng `allowedOrigins("*")` chỉ để bỏ lỗi local development. Có thể cho phép riêng `http://localhost:5173` trong Spring hoặc thiết lập dev proxy rõ ràng.

## 4. Origin khác URL, site, cookie domain và server Host

| Thuật ngữ | Ví dụ | Dùng cho |
| --- | --- | --- |
| URL đầy đủ | `https://app.example.test:8443/orders?id=1` | Chỉ ra tài nguyên |
| Origin | `https://app.example.test:8443` | Same-Origin Policy, CORS |
| Hostname | `app.example.test` | Một thành phần của origin |
| Site (schemeful) | Thường là `https://example.test` | SameSite cookie, mô hình same-site |
| Cookie Domain | `example.test` nếu được khai báo như vậy | Phạm vi host nhận cookie |
| HTTP Host header | `api.example.test:443` | Host đích request HTTP/1.1 |
| HTTP Origin header | `https://app.example.test` | Origin nguồn tạo request |

**Same-site không đồng nghĩa same-origin:**

~~~text
https://app.example.test  → https://api.example.test

Khác origin (hostname khác)
Nhưng có thể cùng schemeful site (https + example.test)
~~~

Cookie `SameSite` nhìn theo site, còn CORS nhìn theo origin. Vì vậy frontend và API trên hai subdomain có thể **same-site**, nhưng script vẫn cần kiểm tra CORS khi đọc response của origin khác.

Với mô hình *schemeful same-site*, `http://app.example.test` và `https://app.example.test` được xem khác site vì scheme khác. Đây cũng là hai origin khác nhau. Cookie có `Domain=example.test` không tự cấp quyền cho JavaScript từ mọi subdomain đọc dữ liệu của origin khác.

## 5. Chuẩn hóa cổng, hostname và opaque origin

### Effective port

Trong HTTP, URL không ghi port có effective port 80. Trong HTTPS, URL không ghi port có effective port 443. Bởi vậy `https://app.example.test` và `https://app.example.test:443` cùng origin, dù chuỗi URL không giống hệt.

Browser thường **không tuần tự hóa port mặc định** vào string origin. Ví dụ `window.location.origin` có thể trả `https://app.example.test`, chứ không nhất thiết chứa `:443`.

### Chuẩn hóa hostname

Tên DNS có quy tắc không phân biệt chữ hoa/thường và xử lý tên miền quốc tế qua IDNA/Punycode. Vì vậy không nên tự so sánh hai raw URL bằng những thao tác chuỗi tùy tiện. CORS của Spring có thành phần cấu hình/so khớp chuẩn; hãy sử dụng nó.

### Opaque origin và Origin: null

Không phải mọi document đều có origin dạng bộ ba HTTP(S). Một số trường hợp có **opaque origin**, ví dụ `data:` URL, một số tài liệu `file:` hoặc `iframe sandbox` không có `allow-same-origin`.

Origin đặc biệt có thể được biểu diễn trong request:

~~~http
Origin: null
~~~

`null` ở đây không có nghĩa “không có Origin header”, cũng không phải một hostname an toàn. Đừng thêm `"null"` vào danh sách origin tin cậy chỉ để làm một file HTML local hoạt động, vì nhiều nguồn không tin cậy có thể mang cùng cách biểu diễn này.

Không phải mọi `blob:` hoặc `about:blank` đều có opaque origin: một tài liệu `about:blank` được tạo bởi script có thể kế thừa origin; một blob URL có thể liên kết với môi trường tạo nó. Bài này tập trung vào HTTP(S), nơi quy tắc bộ ba được dùng trực tiếp.

## 6. Chương trình Java 17+ tính origin HTTP(S)

Đoạn sau là **một chương trình Java độc lập, biên dịch được** dùng `java.net.URI` và record để minh họa default port. Nó không triển khai mọi quy tắc browser cho opaque origins hoặc tên miền quốc tế.

Tạo `OriginDemo.java`:

~~~java
import java.net.URI;
import java.util.Locale;

public class OriginDemo {

    record OriginKey(String scheme, String host, int port) {
    }

    static OriginKey of(String rawUrl) {
        URI url = URI.create(rawUrl);
        String scheme = url.getScheme();
        String host = url.getHost();

        if (scheme == null || host == null) {
            throw new IllegalArgumentException("HTTP(S) URL required");
        }

        scheme = scheme.toLowerCase(Locale.ROOT);
        host = host.toLowerCase(Locale.ROOT);

        if (!scheme.equals("http") && !scheme.equals("https")) {
            throw new IllegalArgumentException("Unsupported scheme");
        }

        int port = url.getPort();
        if (port == -1) {
            port = scheme.equals("https") ? 443 : 80;
        }

        return new OriginKey(scheme, host, port);
    }

    static boolean sameOrigin(String left, String right) {
        return of(left).equals(of(right));
    }

    public static void main(String[] args) {
        String base = "https://shop.example.test/orders";

        System.out.println(sameOrigin(
                base, "https://shop.example.test:443/cart"));
        System.out.println(sameOrigin(
                base, "http://shop.example.test/cart"));
        System.out.println(sameOrigin(
                base, "https://shop.example.test:8443/cart"));
        System.out.println(sameOrigin(
                base, "https://api.example.test/cart"));
        System.out.println(sameOrigin(
                base, "https://shop.example.test/orders?page=2"));
    }
}
~~~

Lệnh:

~~~bash
javac OriginDemo.java
java OriginDemo
~~~

Stdout theo đúng mã:

~~~text
true
false
false
false
true
~~~

Lần lượt: port HTTPS mặc định giống; scheme khác; port khác; hostname khác; chỉ query khác. **Không dùng hàm tự viết này làm hệ thống xác minh Origin production**; trong Spring Security, hãy dùng `CorsConfiguration` và CORS processing của framework.

## 7. HTTP Origin request header

Khi script tại `https://app.example.test` gọi API tại `https://api.example.test`, browser có thể gửi:

~~~http
GET /api/greeting HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
~~~

**`Host` chỉ server đích, `Origin` chỉ origin gây ra request.** Origin header không chứa path/query/fragment:

~~~http
Origin: https://app.example.test
Origin: http://localhost:5173
Origin: https://app.example.test:8443
Origin: null
~~~

Không viết `Origin: https://app.example.test/dashboard?x=1` cho một origin HTTP(S) đúng chuẩn.

`Origin` có thể không xuất hiện trên mọi GET/HEAD bình thường, và có thể mang giá trị `null` ở một số trường hợp. Browser có quy tắc tự đặt header này, nhưng **curl/Postman và HTTP client tự viết có thể giả mạo bất kỳ Origin header nào**. Vì thế Origin không chứng minh người dùng đăng nhập và không được dùng làm một credential.

`Referer` có thể chứa thêm path URL nguồn tùy Referrer-Policy, còn Origin được thiết kế để chỉ diễn tả origin với thông tin hạn chế hơn.

## 8. CORS cho phép chia sẻ response giữa các origin

Same-Origin Policy (SOP) hạn chế script một origin đọc/tương tác tùy ý với tài nguyên origin khác. CORS cho phép server công bố những origin được đọc response trong ngữ cảnh browser.

Script trong `https://app.example.test`:

~~~javascript
fetch("https://api.example.test/api/greeting");
~~~

Vì origin khác hostname, browser áp dụng CORS. Server có thể cho phép bằng header:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

Những điều **CORS không làm**:

- Không biến hai origin thành cùng origin.
- Không xác thực một người dùng hay cấp vai trò ADMIN.
- Không mặc định ngăn mọi cross-origin request **được gửi** tới server.
- Không thay CSRF protection trên ứng dụng dùng cookie/session.
- Không chặn curl hay các HTTP client không thực thi chính sách browser.

Một request có thể đã tới server và gây side effect, nhưng browser từ chối cho script đọc response. Điều này đặc biệt quan trọng với HTML form POST không cần preflight.

## 9. CORS preflight: method OPTIONS không phải method nghiệp vụ

Browser cần **preflight OPTIONS** trước một số yêu cầu cross-origin, chẳng hạn POST JSON có `Content-Type: application/json` hay có header không thuộc danh sách safelisted.

~~~http
OPTIONS /api/greeting HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
~~~

Phân biệt:

- Method của request preflight thật là **OPTIONS**.
- `Access-Control-Request-Method: POST` chỉ method của request sẽ được gửi sau nếu được phép.
- `Access-Control-Request-Headers` liệt kê những header dự kiến.

Server có thể trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: content-type
Access-Control-Max-Age: 3600
Vary: Origin
~~~

Response trên là ví dụ, status và header đầy đủ tùy cấu hình. Preflight thường **không mang cookie/credential đăng nhập**. Vì vậy Spring Security cần xử lý CORS trước những kiểm tra authentication có thể chặn OPTIONS chỉ vì thiếu session.

Không sửa lỗi preflight bằng cách cho `OPTIONS /**` qua mọi điều kiện mà không có cấu hình origin, method và header. CORS chỉ chấp nhận preflight **đúng policy**, sau đó request thật vẫn phải qua authentication, authorization và CSRF khi cần.

## 10. Credentialed CORS và wildcard

Nếu frontend ở `https://app.example.test` cần browser gửi cookie được phép tới API:

~~~javascript
fetch("https://api.example.test/api/greeting", {
  method: "GET",
  credentials: "include"
});
~~~

Browser chỉ gửi credential theo điều kiện cookie/SameSite/Secure/third-party cookie policy. Nếu request là credentialed, server còn cần phản hồi:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
~~~

Cấu hình sau **không phù hợp** để browser chia sẻ credentialed response:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Với credentialed CORS, không dùng wildcard `*` ở `Access-Control-Allow-Origin`; cần origin cụ thể. Khi server phản hồi giá trị phụ thuộc Origin của request, `Vary: Origin` giúp cache phân biệt những biến thể.

Đừng bật credentials chỉ vì frontend báo lỗi CORS. Với API dữ liệu cá nhân, đây là quyết định tin cậy: **code của origin được allow có thể đọc response** trong điều kiện browser và server chấp nhận. CORS cũng không có tác dụng thay cho CSRF token khi dùng cookie tự gửi.

## 11. Ví dụ Spring Boot 3.3 + Spring Security 6.3

Ta tạo một API mẫu:

- `GET /api/greeting` yêu cầu xác thực.
- `POST /api/greeting` yêu cầu xác thực và CSRF token; lưu một chuỗi demo vào bộ nhớ.
- Chỉ cho phép cross-origin từ `https://app.example.test` và `http://localhost:5173`.
- Method được CORS cho phép: GET, POST.
- Để minh họa credential, test dùng HTTP Basic và tài khoản demo.
- Giữ CSRF mặc định, không tắt toàn ứng dụng.
- Các request không được liệt kê bị `denyAll`.

### 11.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'origin-cors-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
~~~

Các file Java dưới đây đặt chung package `example.origincors`. Ví dụ cần Gradle hoặc wrapper tương thích.

### 11.2. OriginCorsApplication.java

~~~java
package example.origincors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OriginCorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(OriginCorsApplication.class, args);
    }
}
~~~

Lưu ở `src/main/java/example/origincors/OriginCorsApplication.java`.

### 11.3. SecurityConfig.java

~~~java
package example.origincors;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/greeting")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/greeting")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Không tắt CSRF: POST vẫn yêu cầu token hợp lệ.
        return http.build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();

        config.setAllowedOrigins(List.of(
                "https://app.example.test",
                "http://localhost:5173"
        ));
        config.setAllowedMethods(List.of("GET", "POST"));
        config.setAllowedHeaders(List.of(
                "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        config.setAllowCredentials(true);
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(lan);
    }
}
~~~

Ý nghĩa:

1. `http.cors(Customizer.withDefaults())` tích hợp CORS processing với Spring Security, để preflight được xử lý trước authentication.
2. `setAllowedOrigins(...)` dùng chính xác **origin**, không có path: `https://app.example.test` chứ không phải `https://app.example.test/dashboard`.
3. `https://app.example.test:8443` không được phép bởi allowlist này vì port khác.
4. `http://app.example.test` không được phép vì scheme khác.
5. `http://localhost:5174` không được phép vì khác port với dev server 5173.
6. `setAllowCredentials(true)` là lựa chọn demo; production chỉ bật nếu thật sự cần và tin cậy origin.
7. `allowedMethods` và `allowedHeaders` chỉ quy định CORS. Chúng **không** thay `authorizeHttpRequests`.
8. `anyRequest().denyAll()` chặn URL ngoài phạm vi.
9. `PasswordEncoder` BCrypt và tài khoản in-memory chỉ để học; không dùng user/password mẫu ngoài môi trường thử nghiệm.
10. CSRF vẫn bật mặc định với POST. HTTP Basic có thể là credential được browser nhớ/tự sử dụng; không mặc nhiên bỏ CSRF.

### 11.4. GreetingStore.java

~~~java
package example.origincors;

import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;

@Service
public class GreetingStore {

    private final ConcurrentHashMap<String, String> values =
            new ConcurrentHashMap<>();

    public void save(String user, String message) {
        values.put(user, message);
    }

    public String get(String user) {
        return values.getOrDefault(user, "(unset)");
    }

    public void clear() {
        values.clear();
    }
}
~~~

`ConcurrentHashMap` chỉ là kho giả để đo tác dụng phụ trong test, không phải database hay cơ chế lưu dữ liệu có độ bền.

### 11.5. GreetingController.java

~~~java
package example.origincors;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greeting")
public class GreetingController {

    private final GreetingStore store;

    public GreetingController(GreetingStore store) {
        this.store = store;
    }

    @GetMapping
    public String read(Authentication auth) {
        return "Hello, " + auth.getName();
    }

    @PostMapping
    public String save(@RequestParam String message,
                       Authentication auth) {
        store.save(auth.getName(), message);
        return "Saved for " + auth.getName() + ": " + message;
    }
}
~~~

CORS cho phép một nguồn browser đọc response theo chính sách, nhưng Controller vẫn chỉ được gọi khi security chain cho qua. `GET` chỉ đọc, `POST` thay đổi kho giả.

## 12. Kiểm thử method, origin và CSRF bằng MockMvc

Trong `src/test/java/example/origincors/OriginCorsTest.java`:

~~~java
package example.origincors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.options;
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
class OriginCorsTest {

    @Autowired MockMvc mvc;
    @Autowired GreetingStore store;

    @BeforeEach
    void reset() {
        store.clear();
    }

    @Test
    void allowedPreflightDoesNotRequireLogin() throws Exception {
        mvc.perform(options("/api/greeting")
                .header(HttpHeaders.ORIGIN, "https://app.example.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "https://app.example.test"))
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
    }

    @Test
    void differentHostnameFails() throws Exception {
        mvc.perform(options("/api/greeting")
                .header(HttpHeaders.ORIGIN, "https://evil.example.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
                .andExpect(status().isForbidden());
    }

    @Test
    void differentSchemeFails() throws Exception {
        mvc.perform(options("/api/greeting")
                .header(HttpHeaders.ORIGIN, "http://app.example.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
                .andExpect(status().isForbidden());
    }

    @Test
    void differentPortFails() throws Exception {
        mvc.perform(options("/api/greeting")
                .header(HttpHeaders.ORIGIN, "https://app.example.test:8443")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
                .andExpect(status().isForbidden());
    }

    @Test
    void localhostPortIsImportant() throws Exception {
        mvc.perform(options("/api/greeting")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
                .andExpect(status().isOk());

        mvc.perform(options("/api/greeting")
                .header(HttpHeaders.ORIGIN, "http://localhost:5174")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
                .andExpect(status().isForbidden());
    }

    @Test
    void notAllowedCorsMethodFailsPreflight() throws Exception {
        mvc.perform(options("/api/greeting")
                .header(HttpHeaders.ORIGIN, "https://app.example.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE"))
                .andExpect(status().isForbidden());
    }

    @Test
    void corsDoesNotReplaceAuthentication() throws Exception {
        mvc.perform(get("/api/greeting")
                .header(HttpHeaders.ORIGIN, "https://app.example.test"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void allowedOriginCanReadWithCredentials() throws Exception {
        mvc.perform(get("/api/greeting")
                .header(HttpHeaders.ORIGIN, "https://app.example.test")
                .with(httpBasic("lan", "demo123")))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "https://app.example.test"))
                .andExpect(content().string("Hello, lan"));
    }

    @Test
    void disallowedOriginIsRejectedBeforeController() throws Exception {
        mvc.perform(get("/api/greeting")
                .header(HttpHeaders.ORIGIN, "https://evil.example.test")
                .with(httpBasic("lan", "demo123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void noOriginHeaderDoesNotRequireCorsHeader() throws Exception {
        mvc.perform(get("/api/greeting")
                .with(httpBasic("lan", "demo123")))
                .andExpect(status().isOk())
                .andExpect(header().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void allowedOriginCannotPostWithoutCsrf() throws Exception {
        mvc.perform(post("/api/greeting")
                .header(HttpHeaders.ORIGIN, "https://app.example.test")
                .with(httpBasic("lan", "demo123"))
                .param("message", "unsafe"))
                .andExpect(status().isForbidden());

        assertEquals("(unset)", store.get("lan"));
    }

    @Test
    void allowedOriginCanPostWithCsrf() throws Exception {
        mvc.perform(post("/api/greeting")
                .header(HttpHeaders.ORIGIN, "https://app.example.test")
                .with(httpBasic("lan", "demo123"))
                .with(csrf())
                .param("message", "hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Saved for lan: hello"));

        assertEquals("hello", store.get("lan"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests '*OriginCorsTest'
~~~

Windows:

~~~powershell
.\gradlew.bat test --tests "*OriginCorsTest"
~~~

**Kết quả kỳ vọng:** **12 phép thử** thành công với đúng project/dependency của ví dụ. Đây là **kỳ vọng từ mã và hợp đồng Spring Security**, không phải kết quả thực tế đã chạy ở đây. Test kiểm tra CORS policy phía server, preflight, xác thực HTTP Basic và CSRF. `MockMvc` **không mô phỏng đầy đủ trình duyệt**: nó không chứng minh SameSite cookie có được gửi, preflight cache có hoạt động hay JS có đọc response thật được không.

Khi cần bảo đảm hành vi browser, chạy hai origin thử nghiệm thực tế và quan sát Network tab; không chia sẻ cookie/token hoặc password thật.

## 13. Chẩn đoán từ DevTools/Network

Trong trình duyệt, mở Developer Tools → Network, bật Preserve log rồi gọi API:

~~~javascript
console.log(window.location.origin);

fetch("http://localhost:8080/api/greeting", {
  method: "GET",
  credentials: "include"
});
~~~

Nếu trang frontend chạy `http://localhost:5173`, `window.location.origin` tương ứng giá trị đó. Browser gọi API origin `http://localhost:8080` nên đây là cross-origin. Kết quả có thể không thành công vì chưa có authentication, cookie policy hoặc CORS config; đoạn code chỉ minh họa cách quan sát.

Quy trình gỡ lỗi:

1. Kiểm tra **Request URL** để xác định origin của API.
2. So sánh với **window.location.origin** để xác định nguồn.
3. Xem có request `OPTIONS` trước request thật hay không.
4. Kiểm tra `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers` của preflight.
5. Kiểm tra `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Credentials` trong response.
6. Kiểm tra URL sau reverse proxy và chứng chỉ TLS, tránh nhầm lỗi mạng với CORS.
7. Nếu CORS cho phép nhưng nhận 401/403, kiểm tra authentication, authorization và CSRF riêng.
8. Khi có credentialed response, kiểm tra SameSite/Secure/third-party cookie policy; `credentials: include` không ép browser bỏ qua các quy định này.

**Một lỗi CORS trong console không bảo đảm request thật chưa đến server.** Một số request được gửi nhưng JS bị chặn đọc response; preflight thất bại thì request thật có thể không được gửi. Hãy kiểm tra cả Network và log server có chọn lọc.

## 14. Reverse proxy và URL công khai

Browser có thể truy cập:

~~~text
https://api.example.test
        |
        | Reverse proxy HTTPS :443
        v
http://api-service:8080   (mạng nội bộ)
~~~

Origin **phía browser** của API là `https://api.example.test`, không phải `http://api-service:8080`. CORS allowlist phải dựa trên origin của **frontend gọi API**, không dựa trên hostname/port nội bộ của backend. Nếu frontend ở `https://app.example.test`, server cần cho phép origin này khi có nhu cầu cross-origin chính đáng.

Khi tự xây URL redirect hoặc xử lý scheme/host trong ứng dụng, chỉ tin `Forwarded` hoặc `X-Forwarded-*` do reverse proxy đáng tin đã kiểm soát. Đừng cho client Internet tự khai forwarded headers để tác động các quyết định bảo mật. Với nhiều `SecurityFilterChain`, phải bảo đảm CORS được áp dụng đúng chain và các đường API không lọt qua một chain không bảo vệ.

## 15. Lỗi phổ biến

1. **“Cùng domain là cùng origin.”** Sai nếu scheme/hostname/port khác.
2. **“localhost:5173 và localhost:8080 cùng origin.”** Sai vì port khác.
3. **“localhost và 127.0.0.1 cùng origin.”** Sai vì hostname khác.
4. **“HTTP và HTTPS cùng origin nếu cùng hostname.”** Sai vì scheme khác.
5. **“Port 443 tường minh khác HTTPS mặc định.”** Sai về effective port.
6. **“Path và query là một phần origin.”** Sai; chúng ảnh hưởng URL, không ảnh hưởng origin.
7. **“Subdomain cùng site thì JS đọc response không cần CORS.”** Sai; same-site khác same-origin.
8. **“Origin header chứa đường dẫn trang nguồn.”** Sai với HTTP(S) origin tuple thông thường.
9. **“Origin: null là an toàn vì không có host.”** Sai; opaque origin có thể không tin cậy.
10. **“CORS cho phép origin là đã đăng nhập.”** Sai; vẫn cần authentication/authorization.
11. **“CORS thay CSRF.”** Sai; request có side effect có thể được gửi dù browser không cho script đọc response.
12. **“Allow-Origin: * cùng Allow-Credentials: true được browser chấp nhận.”** Sai đối với credentialed request.
13. **“OPTIONS preflight cần đăng nhập như POST thật.”** Preflight thường không mang credential; phải CORS xử lý trước.
14. **“Header Origin từ curl đáng tin như bằng chứng danh tính.”** Sai; non-browser client có thể tự đặt.
15. **“CORS lỗi nên tắt CSRF.”** Sai vì đây là hai cơ chế khác nhau.
16. **“Server nội bộ chạy :8080 nên browser thấy origin :8080.”** Sai khi đứng sau reverse proxy công khai.
17. **“Phản chiếu mọi Origin yêu cầu trong Allow-Origin là an toàn.”** Sai; tương đương cho origin không đáng tin.
18. **“CORS chặn mọi request từ domain khác.”** Sai; CORS chủ yếu kiểm soát chia sẻ response trong browser.

## 16. Bài tập tự kiểm tra và đáp án

**1.** `https://example.test` và `https://example.test:443` cùng origin không?

**Đáp án:** Có, vì effective port của HTTPS mặc định là 443.

**2.** `http://example.test:443` và `https://example.test:443` cùng origin không?

**Đáp án:** Không. Scheme HTTP khác HTTPS.

**3.** `http://localhost:5173` gọi `http://localhost:8080` có cần xét CORS không?

**Đáp án:** Có với script browser gọi trực tiếp. Port khác nên cross-origin.

**4.** `https://app.example.test` và `https://api.example.test` cùng site nhưng khác origin không?

**Đáp án:** Có thể cùng schemeful site, nhưng khác origin vì hostname khác.

**5.** `https://app.example.test/cart` và `https://app.example.test/orders?tab=1` cùng origin không?

**Đáp án:** Có. Path/query khác không đổi origin.

**6.** Preflight gửi `OPTIONS` với `Access-Control-Request-Method: POST`. Method request hiện tại là gì?

**Đáp án:** OPTIONS; POST là method của request dự kiến.

**7.** Server trả `Access-Control-Allow-Origin: *` và `Access-Control-Allow-Credentials: true`; JS credentialed fetch có thể đọc response không?

**Đáp án:** Không theo CORS. Credentialed response không dùng wildcard Allow-Origin.

**8.** API cho phép `https://app.example.test` nhưng frontend chạy ở `https://app.example.test:8443`. Được phép mặc định không?

**Đáp án:** Không. Cổng khác tạo origin khác.

**9.** `Origin: null` có nghĩa source là một website tin cậy không?

**Đáp án:** Không. Nó có thể đến từ opaque origin; không whitelist bừa.

**10.** CORS cho phép origin nhưng user không gửi credential tới endpoint cần login. Có được API trả dữ liệu không?

**Đáp án:** Không. CORS không cấp danh tính hay quyền.

**11.** Nếu frontend và backend phục vụ qua cùng URL công khai `https://shop.example.test/api`, nhưng backend nội bộ chạy port 8080, browser có cần CORS chỉ vì port nội bộ không?

**Đáp án:** Không. Origin mà browser nhìn thấy dựa trên URL công khai, không dựa trên cổng service nội bộ.

## 17. Checklist triển khai

- Đã xác định đầy đủ scheme, hostname, effective port từ browser origin chưa?
- Đã phân biệt rõ frontend URL với API URL và các port dev/prod chưa?
- Đã kiểm tra cổng mặc định HTTP 80, HTTPS 443 chưa?
- Đã tránh nhầm same-site cookie với same-origin CORS chưa?
- Allowed origins có đúng định dạng, không có path/query không?
- Khi bật allowCredentials, đã tránh wildcard `*` và giới hạn nguồn tin cậy chưa?
- Đã xử lý preflight trước authentication phụ thuộc session/cookie chưa?
- Đã khai báo allowedMethods và allowedHeaders theo những request thật chưa?
- Đã kiểm tra Origin null và subdomain không tin cậy chưa?
- Đã tách lỗi CORS với CSRF, authentication, authorization và TLS chưa?
- Đã kiểm thử scheme khác, hostname khác, port khác, dev localhost khác và same-origin không cần CORS chưa?
- Khi dùng reverse proxy, đã xác minh URL công khai và forwarded headers tin cậy chưa?
- Đã thử trên browser thật ngoài MockMvc chưa?

**Ghi nhớ:** Với HTTP(S), **origin gồm scheme + hostname + effective port**. Chỉ cần thay **một** thành phần là có thể thành cross-origin; thay path/query thì vẫn cùng origin. CORS cho phép chia sẻ response giữa các origin theo policy của browser, **không** thay cơ chế xác thực, phân quyền hoặc chống CSRF.

## Tài liệu tham khảo

- [MDN — Origin](https://developer.mozilla.org/en-US/docs/Glossary/Origin): bộ ba origin, default port, opaque origin.
- [MDN — Same-Origin Policy](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Same-origin_policy): giới hạn giữa các origin.
- [MDN — Origin HTTP header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Origin): cú pháp và ý nghĩa của Origin.
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): preflight và credentialed requests.
- [MDN — Access-Control-Allow-Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin): wildcard và origin cụ thể.
- [Spring Security — CORS (Servlet)](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): CORS trước authentication và cấu hình CorsConfigurationSource.
- [Spring Framework — Web MVC CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): cấu hình CORS, credentialed requests và preflight.
