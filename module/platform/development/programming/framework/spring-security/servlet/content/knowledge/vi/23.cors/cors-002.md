# CORS Preflight OPTIONS: Vì sao phải xử lý trước quyết định xác thực trong Spring Security Servlet?

## 1. Bài toán: request thật chưa gửi nhưng trình duyệt đã bị chặn

Giả sử giao diện chạy tại `http://localhost:5173` và Spring Boot API chạy tại `http://localhost:8080`. Hai URL có **origin khác nhau** vì khác cổng. Frontend gọi API bằng `fetch`, trong đó có header `Authorization`. Trình duyệt có thể gửi **OPTIONS preflight** trước khi gửi GET/POST thật:

~~~http
OPTIONS /api/notes HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Nếu Security yêu cầu người dùng đã xác thực ngay ở OPTIONS, server có thể trả `401 Unauthorized` hoặc `403 Forbidden`. Preflight không có thông tin đăng nhập như request thật, nên trình duyệt **không gửi tiếp GET/POST**; người dùng thấy lỗi CORS dù tài khoản, mật khẩu hoặc access token dùng cho request thật có thể hoàn toàn hợp lệ.

Đây là điểm quan trọng nhất:

> **CORS preflight là câu hỏi của trình duyệt về chính sách truy cập cross-origin, không phải thao tác nghiệp vụ của người dùng. Server phải xử lý câu hỏi này trước khi bắt request đi qua quyết định xác thực/phân quyền của ứng dụng.**

Trong ứng dụng **Spring Security Servlet**, cách tích hợp thông thường là bật `http.cors(...)` và cung cấp cấu hình CORS đúng; Spring Security đặt xử lý CORS ở vị trí phù hợp trước các filter xác thực và phân quyền.

Mục tiêu của bài: giải thích chính xác khi nào có OPTIONS preflight, cách các header được trao đổi, vị trí của `CorsFilter`, cấu hình Spring Security 6 và kiểm thử độc lập giữa CORS, authentication, authorization và CSRF.

## 2. Phân biệt origin, same-origin, same-site và CORS

Một **origin** được xác định bởi bộ ba **scheme + hostname + port**. Với giao diện tại `http://localhost:5173`, các URL sau có quan hệ:

| URL API | Cùng origin với frontend? | Lý do |
| --- | --- | --- |
| `http://localhost:5173/api` | Có | Cùng scheme, hostname và port. |
| `http://localhost:8080/api` | Không | Khác port. |
| `https://localhost:5173/api` | Không | Khác scheme. |
| `http://127.0.0.1:5173/api` | Không | Hostname khác. |

**Cross-Origin Resource Sharing (CORS)** cho phép server công bố nguồn nào có thể truy cập tài nguyên từ JavaScript chạy trong browser. Browser áp dụng quy tắc này cho các yêu cầu cross-origin chịu sự kiểm soát của CORS. `curl`, Postman hoặc code server-to-server thông thường **không bị browser chặn bởi CORS**; chúng vẫn có thể gửi cùng HTTP request. Vì vậy, “Postman chạy, frontend lỗi” không chứng minh backend đã cho phép origin đó.

**Same-origin** khác **same-site**: chính sách cookie `SameSite` xét quan hệ site, còn CORS xét origin. Hai ứng dụng trên các subdomain cùng site vẫn có thể **khác origin** và cần xử lý CORS; cookie và CSRF vẫn là các quyết định riêng.

CORS là cơ chế browser kiểm soát việc mã nguồn ở origin khác được đọc phản hồi hoặc thực hiện một số yêu cầu cross-origin. Nó **không cấp quyền nghiệp vụ**, không bảo vệ API khỏi client tùy ý và không thay thế authentication/authorization.

## 3. Preflight là gì? Khi nào browser gửi OPTIONS?

Đối với một số cross-origin request, browser cần hỏi server trước liệu **method** và **header** dự định dùng có được cho phép hay không. Nó tự phát sinh một OPTIONS request đến **chính URL của request dự định gửi**, có ba header tiêu biểu:

- `Origin`: origin của trang đã khởi tạo yêu cầu.
- `Access-Control-Request-Method`: HTTP method của **request thật**; ví dụ GET, POST, PUT, DELETE.
- `Access-Control-Request-Headers`: tên các request header không thuộc danh sách được miễn hỏi trước mà browser định gửi; ví dụ `authorization,content-type`.

Một request CORS đơn giản thường **không** cần preflight nếu dùng GET/HEAD/POST và chỉ sử dụng các header/value thuộc nhóm CORS-safelisted theo đặc tả. Những trường hợp thường khiến browser cần preflight:

| Yêu cầu JavaScript cross-origin | Thường có preflight? | Vì sao |
| --- | --- | --- |
| `fetch(url)` với GET và không có header tùy chỉnh | Không | Thường là CORS request đủ điều kiện gửi trực tiếp. |
| GET kèm `Authorization: Bearer ...` | **Có** | `Authorization` không phải CORS-safelisted request header. |
| POST với `Content-Type: application/json` | **Có** | `application/json` không thuộc các giá trị MIME safelisted cho Content-Type. |
| POST form `application/x-www-form-urlencoded` và không có header đặc biệt | Thường không | Method và Content-Type đáp ứng điều kiện safelisted. |
| PUT, PATCH, DELETE | **Có** | Đây không phải CORS-safelisted methods. |
| POST có `X-CSRF-TOKEN` | **Có** | Header tùy chỉnh phải được xét trong preflight. |

Điều kiện đầy đủ do thuật toán Fetch/CORS của browser quyết định, bao gồm giới hạn về header và một số trường hợp đặc biệt; bảng trên là những tình huống thực tế thường gặp.

**OPTIONS là method của preflight; `Access-Control-Request-Method` mới cho biết method của request thật.** Chẳng hạn preflight `OPTIONS /api/items/7` với `Access-Control-Request-Method: DELETE` không có nghĩa trình duyệt đã xóa tài nguyên; nó mới đang hỏi server liệu DELETE có được chấp nhận từ origin này hay không.

Không phải mọi OPTIONS đều là CORS preflight. OPTIONS được gọi thủ công mà **thiếu `Origin` hoặc `Access-Control-Request-Method`** không phải preflight theo cách nhận diện thông thường của `CorsFilter`; request đó có thể đi tiếp tới xác thực, định tuyến hoặc handler OPTIONS khác.

## 4. Luồng hai bước: hỏi trước, sau đó mới thực hiện

Ví dụ frontend gọi:

~~~javascript
const response = await fetch("http://localhost:8080/api/notes", {
  method: "GET",
  headers: {
    "Authorization": "Bearer " + accessToken
  }
});
~~~

Do có header Authorization, browser trước hết có thể phát sinh:

~~~http
OPTIONS /api/notes HTTP/1.1
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Nếu origin, method và header được phép, phản hồi CORS điển hình có dạng:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: authorization
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Mã trạng thái preflight thành công thường là 200 hoặc 204 tùy server; cách viết, thứ tự hoặc số lượng header có thể khác. Điều quan trọng là server cung cấp chính sách cho **origin, method, headers đã yêu cầu**; trình duyệt kiểm tra phản hồi. Sau khi preflight hợp lệ, browser mới gửi request thật:

~~~http
GET /api/notes HTTP/1.1
Origin: http://localhost:5173
Authorization: Bearer <access-token>
~~~

Lúc này backend mới đánh giá token, quyền truy cập và nghiệp vụ. Dù preflight thành công, request thật vẫn có thể nhận **401** (chưa xác thực), **403** (không đủ quyền hoặc kiểm tra CSRF thất bại), **404**, **500**... Trong phản hồi thực tế, các header CORS phù hợp vẫn cần xuất hiện để browser cho phép frontend đọc response; “preflight thành công” không tự động khiến request thật được cấp quyền.

Sơ đồ thứ tự:

~~~text
Trang web origin A                           Spring Boot API origin B
         |                                             |
         | OPTIONS /api/notes                          |
         | Origin: A                                   |
         | Access-Control-Request-Method: GET          |
         | Access-Control-Request-Headers: auth...     |
         |-------------------------------------------->|
         |                                             | CorsFilter
         |                                             | - kiểm origin/method/header
         |                                             | - trả CORS response
         |<--------------------------------------------|
         |                                             |
         | Browser kiểm tra CORS response              |
         |           +-----------------------------+   |
         |           | Nếu KHÔNG hợp lệ: DỪNG    |   |
         |           +-----------------------------+   |
         |                                             |
         | GET /api/notes + Authorization              |
         |-------------------------------------------->|
         |                                             | CorsFilter (request thật)
         |                                             | Authentication/Authorization
         |                                             | Controller nếu được phép
         |<--------------------------------------------|
         | Browser kiểm tra CORS của response thật      |
~~~

Trình duyệt có thể cache kết quả preflight theo `Access-Control-Max-Age` trong giới hạn riêng của browser; bởi vậy không nhất thiết thấy OPTIONS trước **mọi lần** gọi giống nhau. Cache preflight không thay thế phiên đăng nhập hay kết quả phân quyền.

## 5. Vì sao CORS phải chạy trước authentication và authorization?

Câu trả lời nằm ở **ngữ nghĩa của preflight** và **thông tin mà browser gửi**:

1. Preflight được browser gửi để thỏa thuận chính sách CORS **trước** request thật. Nó không phải request nghiệp vụ.
2. Preflight chuẩn không đính kèm credentials như session cookie hoặc thông tin đăng nhập của request thật. Header `Authorization` dự định dùng chỉ được nêu **bằng tên** trong `Access-Control-Request-Headers`, chứ không mang access token ở preflight.
3. Nếu filter xác thực nhìn thấy OPTIONS trước filter CORS, quy tắc `anyRequest().authenticated()` có thể gây 401; nếu rule phân quyền từ chối, có thể gây 403.
4. Browser diễn giải preflight bị từ chối hoặc thiếu `Access-Control-Allow-*` phù hợp là **không đạt chính sách CORS**. Nó không gửi tiếp request thật, vì thế backend thậm chí chưa có cơ hội kiểm tra credentials thật.
5. Cho CORS xử lý trước cho phép browser biết chính sách truy cập; khi request thật xuất hiện, **authentication và authorization vẫn chạy đầy đủ**.

~~~text
SAI VỊ TRÍ:
OPTIONS -> Authentication/Authorization -> 401/403 -> Browser chặn -> KHÔNG có request thật

ĐÚNG VỊ TRÍ:
OPTIONS -> CorsFilter -> response CORS hợp lệ
GET/POST/... thật -> CorsFilter -> Authentication -> Authorization -> Controller
~~~

Theo mô hình Servlet, bộ lọc ngoài cùng đi qua `DelegatingFilterProxy` rồi vào `FilterChainProxy` của Spring Security. Khi cấu hình `http.cors(Customizer.withDefaults())`, Spring Security tích hợp `CorsFilter` ở vị trí sớm trong security filter chain, **trước các bước xác thực thông thường**. Khi gặp preflight hợp lệ, `CorsFilter` trả lời ngay, không tiếp tục vào phần còn lại của chain. Với request thật, nó kiểm tra và gắn CORS response header rồi cho request đi tiếp.

Cần phân biệt **xác thực** và **phân quyền**: authentication xác định client/người dùng là ai; authorization quyết định họ có được truy cập chức năng hay không. Cả hai vẫn cần cho request thật. Bật CORS **không** tự biến `/api/**` thành `permitAll()`.

Trong hệ thống có reverse proxy, gateway, load balancer, WAF hoặc nhiều security chain, preflight cũng phải được chuyển đến thành phần CORS phù hợp. Một gateway trả 401 cho OPTIONS trước Spring Security có thể phá luồng dù cấu hình Java đã đúng.

## 6. Cấu hình Spring Security 6 Servlet đúng cách

Ví dụ hoàn chỉnh sau dùng **Java 17**, **Spring Boot 3.3.5**, Spring Web MVC và Spring Security 6. Chúng ta sẽ:

- Cho phép frontend duy nhất `http://localhost:5173` gọi các đường `/api/**`.
- Cho phép CORS method thật **GET, POST**, và header **Authorization, Content-Type**.
- Giữ `anyRequest().authenticated()` và HTTP Basic để chứng minh preflight **không** yêu cầu đăng nhập nhưng request thật **vẫn** phải đăng nhập.
- Giữ CSRF mặc định để chỉ ra CORS và CSRF là hai lớp kiểm tra khác nhau.

Cấu trúc dự án Maven:

~~~text
cors-preflight-demo/
  pom.xml
  src/main/java/example/cors/CorsPreflightDemoApplication.java
  src/test/java/example/cors/CorsPreflightDemoApplicationTests.java
~~~

**pom.xml**:

~~~xml
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
    <groupId>example</groupId>
    <artifactId>cors-preflight-demo</artifactId>
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

**src/main/java/example/cors/CorsPreflightDemoApplication.java**:

~~~java
package example.cors;

import java.util.List;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CorsPreflightDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CorsPreflightDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("http://localhost:5173"));
        config.setAllowedMethods(List.of("GET", "POST"));
        config.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        config.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails user = User.withUsername("learner")
                .password("{noop}demo1234")
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(user);
    }

    @RestController
    @RequestMapping("/api/notes")
    static class NotesController {

        @GetMapping
        Map<String, String> getNotes() {
            return Map.of("message", "read permitted");
        }

        @PostMapping
        Map<String, String> saveNote(@RequestBody Map<String, String> request) {
            return Map.of("saved", request.getOrDefault("message", ""));
        }
    }
}
~~~

Giải thích từng thành phần quan trọng:

- `.cors(Customizer.withDefaults())` bật tích hợp CORS của **Spring Security filter chain**. Đây là phần đảm bảo xử lý preflight xảy ra sớm hơn xác thực.
- Bean `corsConfigurationSource` cấp chính sách CORS theo đường dẫn. `/api/**` chỉ bao phủ API, không tự mở CORS cho mọi tài nguyên của ứng dụng.
- `setAllowedOrigins(...)` liệt kê **origin được tin cậy**; hostname, scheme và port phải khớp chính xác với `Origin` browser gửi.
- `setAllowedMethods(...)` liệt kê **method của request thật** được chấp nhận. Preflight dùng OPTIONS nhưng **không cần thêm OPTIONS vào allowedMethods chỉ để preflight GET/POST hoạt động**.
- `setAllowedHeaders(...)` cho phép browser gửi `Authorization` và `Content-Type` trong request thật sau khi preflight đạt yêu cầu; giá trị header được so khớp không phân biệt chữ hoa/thường theo quy tắc HTTP.
- `setMaxAge(1800L)` gợi ý browser cache quyết định preflight trong 1.800 giây; browser có thể áp dụng giới hạn thấp hơn.
- `anyRequest().authenticated()` **vẫn bảo vệ request thật**. HTTP Basic cung cấp ví dụ xác thực dễ kiểm thử. Tài khoản và `{noop}` chỉ dùng cho máy phát triển, **không** phải thiết kế lưu mật khẩu production.
- `.csrf(Customizer.withDefaults())` giữ kiểm tra CSRF mặc định; ví dụ này không dùng mẹo tắt CSRF để làm POST chạy.

Để ứng dụng chạy, cần JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

**Tùy chọn khi đã có Spring MVC CORS mapping:** thay vì cung cấp bean `CorsConfigurationSource`, bạn có thể khai báo chính sách trong `WebMvcConfigurer#addCorsMappings` rồi bật `http.cors(...)`; Spring Security có thể sử dụng cấu hình MVC khi không có nguồn CORS chuyên biệt. Với nhiều `CorsConfigurationSource` hoặc nhiều `SecurityFilterChain`, hãy khai báo nguồn cho từng chain một cách tường minh nếu cơ chế tự phát hiện không xác định được. Tránh cấu hình trùng lặp giữa proxy, filter riêng và MVC khi chưa hiểu thứ tự xử lý.

## 7. Thử trực tiếp preflight và request thật bằng curl

`curl` **không thực thi chính sách CORS của browser**, nhưng rất hữu ích để quan sát HTTP status và header mà server trả về. Các ví dụ sau sử dụng ứng dụng từ mục 6.

**Bước 1 — mô phỏng preflight GET với header Authorization, KHÔNG gửi username/password:**

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/notes \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
~~~

Kết quả dự kiến: **200 OK**; response có `Access-Control-Allow-Origin: http://localhost:5173`, có method GET trong `Access-Control-Allow-Methods` và cho phép `authorization` trong `Access-Control-Allow-Headers`. Preflight không cần header `Authorization` hay cookie đăng nhập.

**Bước 2 — request GET thật, chưa có Basic credential:**

~~~bash
curl -i http://localhost:8080/api/notes \
  -H 'Origin: http://localhost:5173'
~~~

Kết quả dự kiến: **401 Unauthorized**; dù origin hợp lệ, request thật phải xác thực. CORS header có thể vẫn xuất hiện trên phản hồi 401 để browser có thể xử lý phản hồi đúng theo CORS.

**Bước 3 — request GET thật, có credential hợp lệ:**

~~~bash
curl -i -u learner:demo1234 \
  http://localhost:8080/api/notes \
  -H 'Origin: http://localhost:5173'
~~~

Kết quả dự kiến: **200 OK** với body `{"message":"read permitted"}`. Đây là bước xác thực HTTP Basic, xảy ra **sau** bước CORS cho request thật.

**Bước 4 — một origin khác thử preflight:**

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/notes \
  -H 'Origin: http://untrusted.example' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
~~~

Kết quả với `CorsFilter` mặc định và cấu hình trên: **403 Forbidden / Invalid CORS request**. Browser không chấp nhận origin này; nó không gửi tiếp request thật.

**Bước 5 — preflight cho POST JSON từ origin được phép:**

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/notes \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
~~~

Kết quả dự kiến: **200 OK**. Tuy nhiên, nếu sau đó gửi POST JSON thật cùng Basic credential mà **không có CSRF token**, cấu hình giữ CSRF mặc định có thể trả **403 Forbidden**:

~~~bash
curl -i -u learner:demo1234 \
  -H 'Origin: http://localhost:5173' \
  -H 'Content-Type: application/json' \
  -d '{"message":"hello"}' \
  http://localhost:8080/api/notes
~~~

Điều này **không mâu thuẫn**: preflight chỉ xác nhận phương thức và header được phép về mặt CORS; CSRF là bước độc lập trên request thật. Để POST thành công trong ứng dụng dùng CSRF, client phải lấy và gửi CSRF token hợp lệ theo repository/handler đang được dùng.

Lưu ý: response header `Vary`, kiểu trình bày `Access-Control-Allow-Headers` hoặc body lỗi có thể khác theo phiên bản/cấu hình. Kết quả cần kiểm tra là status và giá trị chính sách phù hợp, không phải so sánh từng byte với bản minh họa.

## 8. Kiểm thử bằng MockMvc: chứng minh preflight đi trước xác thực

Thêm tệp **src/test/java/example/cors/CorsPreflightDemoApplicationTests.java**:

~~~java
package example.cors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsPreflightDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void preflightSucceedsWithoutAuthentication() throws Exception {
        mvc.perform(options("/api/notes")
                        .header("Origin", "http://localhost:5173")
                        .header("Access-Control-Request-Method", "GET")
                        .header("Access-Control-Request-Headers", "authorization"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "Access-Control-Allow-Origin", "http://localhost:5173"))
                .andExpect(header().exists("Access-Control-Allow-Methods"))
                .andExpect(header().exists("Access-Control-Allow-Headers"));
    }

    @Test
    void actualGetStillNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/notes")
                        .header("Origin", "http://localhost:5173"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "Access-Control-Allow-Origin", "http://localhost:5173"));
    }

    @Test
    void actualGetWithBasicAuthenticationSucceeds() throws Exception {
        mvc.perform(get("/api/notes")
                        .header("Origin", "http://localhost:5173")
                        .with(httpBasic("learner", "demo1234")))
                .andExpect(status().isOk());
    }

    @Test
    void preflightFromUntrustedOriginIsRejected() throws Exception {
        mvc.perform(options("/api/notes")
                        .header("Origin", "http://untrusted.example")
                        .header("Access-Control-Request-Method", "GET")
                        .header("Access-Control-Request-Headers", "authorization"))
                .andExpect(status().isForbidden());
    }

    @Test
    void preflightPostIsAllowedButActualPostStillNeedsCsrf()
            throws Exception {
        mvc.perform(options("/api/notes")
                        .header("Origin", "http://localhost:5173")
                        .header("Access-Control-Request-Method", "POST")
                        .header("Access-Control-Request-Headers", "content-type"))
                .andExpect(status().isOk());

        mvc.perform(post("/api/notes")
                        .header("Origin", "http://localhost:5173")
                        .with(httpBasic("learner", "demo1234"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"hello\"}"))
                .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Bộ test kiểm tra riêng hai lớp hành vi:

- **Preflight hợp lệ, không có credential vẫn được CORS xử lý**, không bị `anyRequest().authenticated()` chặn.
- **Request thật vẫn phải xác thực**; POST thật còn chịu kiểm tra CSRF nếu bật. Origin lạ bị CORS từ chối trước khi vào xử lý nghiệp vụ.

`MockMvc` không phải browser và không tự phát sinh preflight. Test phải **tạo request OPTIONS với đầy đủ `Origin` và `Access-Control-Request-Method`** như trên. Ngược lại, chỉ test `options("/api/notes")` trống header không chứng minh cấu hình CORS preflight.

## 9. CORS, 401/403, CSRF và credentials: những lớp nào quyết định gì?

| Tầng | Câu hỏi được giải quyết | Ví dụ kết quả |
| --- | --- | --- |
| **CORS (preflight)** | Origin A có thể gửi method/header đó tới API origin B không? | Preflight hợp lệ trả 2xx + CORS headers; sai chính sách có thể 403. |
| **Authentication** | Request thật có chứng minh được danh tính không? | Thiếu/sai Basic/JWT/session → 401 hoặc chuyển hướng đăng nhập tùy cơ chế. |
| **Authorization** | Danh tính đó có quyền gọi endpoint không? | Đã đăng nhập nhưng thiếu quyền → thường 403. |
| **CSRF** | Request thay đổi dữ liệu trong mô hình có credential tự gửi có mang token phù hợp không? | POST/PUT/PATCH/DELETE thiếu/sai token → thường 403. |
| **Controller/business logic** | Thao tác có hợp lệ về mặt dữ liệu và nghiệp vụ không? | 200/201/400/404/... tùy logic. |

**Preflight không phải lời hứa rằng request thật sẽ thành công.** Nó chỉ là quyết định về chính sách cross-origin. Tương tự, đăng nhập thành công không có nghĩa mọi origin đều được CORS cho phép.

Nếu ứng dụng dùng **session cookie** và frontend thật sự cần gửi cookie cross-origin, còn có những điều kiện khác:

- Frontend dùng `fetch(url, { credentials: "include" })` khi cần gửi credential qua origin khác.
- CORS policy phải cho phép origin **cụ thể** và bật `config.setAllowCredentials(true)`; response liên quan cần có `Access-Control-Allow-Credentials: true`.
- Không thể dùng `Access-Control-Allow-Origin: *` để cho phép browser đọc response có credential. Tránh phản chiếu bừa mọi origin rồi bật credentials.
- Cookie còn phải đáp ứng `Secure`, `SameSite`, domain/path và chính sách third-party cookie của browser. CORS thành công không tự khiến cookie được gửi.
- **Preflight vẫn không mang cookie phiên**, kể cả khi request thật dự kiến gửi cookie. Vì vậy xử lý CORS trước authentication càng quan trọng.

Phần demo mục 6 dùng HTTP Basic nên **không bật `allowCredentials`** và không phụ thuộc cookie. Chỉ thêm `setAllowCredentials(true)` nếu ứng dụng thật cần và đã giới hạn chặt allowed origins. Với một `Authorization` header do frontend chủ động gắn, browser sẽ preflight vì tên header, bất kể endpoint cuối có chấp nhận token đó hay không.

Lỗi bảo mật thường gặp là `allowedOrigins("*")` hoặc một tập allowedOriginPatterns quá rộng, đặc biệt khi kết hợp `allowCredentials(true)`. Xác định chính xác những origin hợp lệ trong môi trường triển khai, đừng mặc định tin mọi origin để chữa lỗi frontend.

## 10. Vì sao `permitAll() OPTIONS` thường không giải quyết gốc vấn đề?

Một cấu hình thường được sao chép khi thấy 401 trên preflight:

~~~java
// Chỉ là minh họa ý tưởng; không thay thế cấu hình CORS.
auth.requestMatchers(org.springframework.http.HttpMethod.OPTIONS, "/**")
    .permitAll();
~~~

Cách này chỉ nói với **AuthorizationFilter** rằng nó không yêu cầu quyền cho các request OPTIONS khớp matcher. Nó **không** tự tạo `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, không kiểm tra allowed origins và không giải quyết trường hợp proxy hoặc authentication filter khác đã chặn trước. Browser vẫn có thể từ chối response vì thiếu hoặc sai CORS headers.

Với tích hợp `http.cors(...)` đúng, preflight hợp lệ được **`CorsFilter` xử lý sớm**; thông thường không cần một rule cho phép mọi OPTIONS chỉ để sửa CORS. Rule cho phép toàn bộ OPTIONS còn có thể mở phạm vi rộng hơn mục tiêu thực tế. Khi có endpoint OPTIONS nghiệp vụ, hãy phân quyền theo nhu cầu thật của endpoint đó.

Một sai lầm liên quan: thêm `@CrossOrigin` lên controller nhưng Security đã trả 401 trước khi request tới Spring MVC. Cần tích hợp cấu hình CORS vào security filter chain; nếu dùng cách Spring MVC quản lý mapping, bảo đảm `http.cors(...)` lấy được cấu hình đó.

## 11. Chẩn đoán lỗi thực tế theo thứ tự

Khi frontend báo “blocked by CORS policy”, mở **DevTools → Network** (trong browser) và phân biệt **OPTIONS preflight** với **request thật**. Một quy trình có ích:

1. **Có OPTIONS trước request thật không?** Nếu không, request có thể đủ điều kiện gửi trực tiếp, preflight đang được cache hoặc lỗi ở pha khác. Đừng khẳng định “CORS không chạy” chỉ vì không thấy OPTIONS.
2. **OPTIONS gửi đúng `Origin` và `Access-Control-Request-Method` chưa?** So khớp đúng scheme, host và port với cấu hình; không nhầm request method của OPTIONS với method được hỏi.
3. **OPTIONS nhận 401/302 sang login?** CORS có thể đang chạy sau cơ chế auth, hoặc proxy/gateway chặn OPTIONS. Kiểm tra thứ tự filter, security chain khớp URL và tầng đứng trước ứng dụng.
4. **OPTIONS 200 nhưng browser vẫn từ chối?** Kiểm tra `Access-Control-Allow-Origin`, `-Methods`, `-Headers` và `-Credentials` nếu cần. Chỉ status 200 là **không đủ** để preflight hợp lệ.
5. **OPTIONS 403?** Có thể chính `CorsFilter` từ chối origin, method hoặc header; cũng có thể một security/proxy rule từ chối. Dùng header và log để xác định nguồn lỗi; **không mặc định coi mọi 403 là authorization**.
6. **OPTIONS thành công nhưng request thật 401?** CORS đã qua; kiểm tra credential/token, HTTP Basic/JWT/session và cookie của request thật.
7. **OPTIONS thành công nhưng request thật 403?** Xem authorization, CSRF token và các policy khác. POST JSON dùng session cookie thường cần CSRF token dù CORS đã được cho phép.
8. **GET hoạt động, POST JSON thất bại ngay ở OPTIONS?** GET không header đặc biệt có thể không preflight; POST JSON yêu cầu xét `Content-Type`. Xem `allowedHeaders` và `allowedMethods`.
9. **CORS hoạt động local nhưng lỗi sau deploy?** Kiểm tra origin của frontend thực tế, HTTPS, port, routing của reverse proxy, HTTP OPTIONS ở gateway, header `Vary`, rule cache/CDN và thứ tự filter.
10. **Có nhiều `SecurityFilterChain`?** Xác định chain nào khớp **OPTIONS**; security matcher giới hạn theo method đôi khi khiến OPTIONS rơi vào chain khác không có CORS. Nguồn CORS cũng cần áp dụng cho đường dẫn request.
11. **Đã bật credentials nhưng cookie không gửi?** Kiểm tra `fetch.credentials`, cookie `SameSite`/`Secure`, chính sách browser. Không kết luận lỗi thuộc `CorsFilter` chỉ vì thiếu cookie.
12. **Chỉ thấy lỗi CORS trong frontend nhưng backend log có 500?** Browser có thể che nội dung response do thiếu CORS headers trên đường lỗi. Sửa lỗi backend và bảo đảm CORS response policy được áp dụng nhất quán.

Khi debug, log **method, URL, Origin, Access-Control-Request-Method/Headers, status, security chain và lý do bị từ chối** tại môi trường phát triển. Không log mật khẩu, bearer token, session cookie hoặc các giá trị bí mật trong production.

## 12. Bài tập kiểm tra hiểu đúng

**Tình huống A:** Frontend gọi GET cross-origin có `Authorization`. Browser gửi OPTIONS không có access token, server trả 401. Có nên vô hiệu hóa authentication cho GET? **Không.** Cần xử lý preflight đúng thứ tự; GET thật vẫn yêu cầu xác thực.

**Tình huống B:** Preflight trả 200 nhưng không có `Access-Control-Allow-Headers: authorization` trong khi browser hỏi header đó. Browser có gửi GET thật không? **Thông thường không**, vì phản hồi preflight không cho phép header yêu cầu. Một response status 200 không đủ.

**Tình huống C:** Preflight của POST JSON thành công, sau đó POST thật trả 403 vì thiếu CSRF token. Có phải CORS cấu hình sai? **Không nhất thiết.** CORS và CSRF kiểm tra khác nhau; cần xác định nguồn 403 trên request thật.

**Tình huống D:** Backend định nghĩa `allowedMethods = ["GET", "POST"]` nhưng không có `"OPTIONS"`. Preflight POST có nhất định bị từ chối không? **Không.** `allowedMethods` biểu diễn method **thật** mà browser muốn gửi; preflight OPTIONS là cơ chế hỏi policy.

**Tình huống E:** Gọi OPTIONS bằng curl với `-X OPTIONS` nhưng không có `Origin` và `Access-Control-Request-Method`; server trả 401. Điều đó có chứng minh CORS tích hợp lỗi không? **Không.** Đây chưa phải CORS preflight đầy đủ.

**Tình huống F:** Dùng `permitAll()` với mọi OPTIONS nhưng browser vẫn báo thiếu `Access-Control-Allow-Origin`. Cần làm gì? **Cấu hình và tích hợp CORS thật sự** để server trả chính sách origin/method/header đúng, kiểm tra thêm proxy và chain.

## 13. Ghi nhớ

- **Preflight là OPTIONS do browser gửi trước request thật** khi method/header yêu cầu phải được hỏi policy; header `Access-Control-Request-Method` cho biết method của request thật.
- Browser thường **không gửi credential của request thật trong preflight**. Vì thế không thể yêu cầu preflight đi qua đăng nhập giống request thật.
- Trong **Spring Security Servlet**, bật `http.cors(Customizer.withDefaults())` cùng nguồn cấu hình CORS để `CorsFilter` xử lý preflight sớm; khi hợp lệ, nó trả CORS response mà không chạy phần còn lại của security chain.
- **Request thật vẫn cần authentication, authorization và có thể cần CSRF token**. Preflight 2xx chỉ cho phép browser tiến hành bước tiếp theo về mặt CORS.
- **`permitAll(OPTIONS)` không tự tạo CORS response headers**; phải xác nhận policy và thứ tự filter.
- Khi lỗi, tách hai request trong Network, xem status và toàn bộ header CORS, sau đó xác định lỗi thuộc CORS, auth, authorization, CSRF hay proxy.
