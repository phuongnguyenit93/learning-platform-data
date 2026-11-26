# Access-Control-Allow-Origin và các header phản hồi cần đối chiếu

> **Chương:** CORS và header bảo vệ  
> **Module:** SPRING_SECURITY_TESTING — kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên ứng dụng Servlet và Reactive.

## 1. Vì sao phải kiểm tra header phản hồi?

Frontend chạy tại `https://portal.example.vn` cần gọi API tại `https://api.example.vn`. Hai địa chỉ khác **origin** vì khác host. Trong công cụ kiểm thử HTTP, bạn có thể thấy `200 OK` và một JSON hoàn chỉnh; nhưng trình duyệt vẫn có thể chặn JavaScript đọc phản hồi nếu API không phát các header CORS phù hợp.

Ngược lại, phản hồi CORS hợp lệ không chứng minh yêu cầu đã **được xác thực** hoặc **được phân quyền**. Kiểm thử Spring Security phải đánh giá riêng:

- **CORS:** origin, phương thức và các tên header yêu cầu có được chính sách cho phép không? Phản hồi có header để trình duyệt chấp thuận không?
- **HTTP security:** yêu cầu thật có danh tính hợp lệ, authority/role phù hợp và token CSRF (nếu cần) không?
- **Header bảo vệ khác:** response có các header như `X-Content-Type-Options`, `Content-Security-Policy`, `Strict-Transport-Security` theo yêu cầu riêng không?

Bài này tập trung vào **`Access-Control-Allow-Origin` và các header phản hồi liên quan**. Người học sẽ cấu hình Spring Security, dùng **MockMvc** hoặc **WebTestClient** để kiểm tra header được cấp, giá trị được cấp, thời điểm cấp và trường hợp phải từ chối; sau đó kết hợp `@WithMockUser` hoặc ngữ cảnh JWT/OAuth2/OIDC giả lập để kiểm tra API thật.

### Kết quả cần đạt

Sau bài, bạn có thể:

1. Đối chiếu đúng `Access-Control-Allow-Origin` với `Origin` của request.
2. Phân biệt header cần kiểm tra trên **preflight OPTIONS** và trên **actual request**.
3. Kiểm chứng chính sách credential, danh sách phương thức/header, cache preflight, header response được lộ cho JavaScript và `Vary`.
4. Viết test vừa có ca **được phép**, vừa có ca **bị từ chối** và tránh nhầm lỗi CORS với lỗi xác thực, phân quyền hoặc CSRF.

## 2. Xác định bối cảnh từ request

Một origin gồm bộ ba **scheme + host + port**. Path và query không thuộc origin.

Ví dụ frontend và API:

~~~text
Frontend: https://portal.example.vn/dashboard
Origin:   https://portal.example.vn

API:      https://api.example.vn/api/reports
Origin:   https://api.example.vn
~~~

Khi frontend gọi API, trình duyệt thường thêm:

~~~http
Origin: https://portal.example.vn
~~~

Nếu request không thỏa điều kiện *CORS-safelisted* (chẳng hạn có `Authorization` hoặc `Content-Type: application/json`), trình duyệt có thể gửi **preflight** trước:

~~~http
OPTIONS /api/reports HTTP/1.1
Host: api.example.vn
Origin: https://portal.example.vn
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Một preflight như vậy hỏi: “Trang ở origin này có được gửi **POST** kèm hai tên header đó không?”. Giá trị của `Access-Control-Request-Headers` là **tên header**, không phải bearer token hay nội dung JSON.

Trong khi đó, actual request là request thật đến endpoint:

~~~http
GET /api/reports HTTP/1.1
Host: api.example.vn
Origin: https://portal.example.vn
Authorization: Bearer <access-token>
~~~

**Một actual request có thể không được gửi sau preflight thất bại.** Với request không cần preflight, trình duyệt có thể đã gửi request thật rồi mới quyết định không cho JavaScript đọc phản hồi. Vì vậy, CORS không thay thế xác thực, phân quyền và CSRF.

## 3. Bảng đối chiếu các header phản hồi CORS

Đây là bảng trọng tâm khi kiểm thử Spring Security:

| Header phản hồi | Có ý nghĩa ở đâu? | Cách đối chiếu |
| --- | --- | --- |
| `Access-Control-Allow-Origin` | Preflight và actual response | Bằng origin được cấp phép, hoặc `*` trong trường hợp wildcard hợp lệ; phải không cấp cho origin bị cấm |
| `Access-Control-Allow-Credentials` | Preflight và actual response | Khi client dùng credential với chế độ phù hợp, cần giá trị `true` và origin cụ thể |
| `Access-Control-Allow-Methods` | Đặc biệt là preflight | Phải chứa phương thức trong `Access-Control-Request-Method` của request |
| `Access-Control-Allow-Headers` | Đặc biệt là preflight | Phải đáp ứng các tên header trong `Access-Control-Request-Headers` |
| `Access-Control-Max-Age` | Preflight | Số giây trình duyệt có thể cache kết quả preflight; không phải TTL của JSON API |
| `Access-Control-Expose-Headers` | Actual response | Danh sách header response ngoài safelist mà JavaScript có thể đọc |
| `Vary` | Cơ chế cache HTTP | Phải phản ánh các request header làm biến đổi phản hồi CORS, thường `Origin`, và với preflight còn có `Access-Control-Request-Method`/`Access-Control-Request-Headers` |

Một vài header có tên gần giống nhưng **khác chiều**:

| Header trong request | Header trong response | Mục đích |
| --- | --- | --- |
| `Origin` | `Access-Control-Allow-Origin` | Trình duyệt nêu nguồn; server quyết định nguồn nào được phép |
| `Access-Control-Request-Method` | `Access-Control-Allow-Methods` | Client hỏi phương thức thật; server công bố phương thức được phép |
| `Access-Control-Request-Headers` | `Access-Control-Allow-Headers` | Client hỏi tên header gửi đi; server công bố header được phép |
| Không có header yêu cầu tương ứng bắt buộc | `Access-Control-Expose-Headers` | Server công bố header **phản hồi** nào JavaScript được đọc |

**Quy tắc kiểm thử:** một response `200` mà thiếu `Access-Control-Allow-Origin` có thể vẫn không sử dụng được từ JavaScript khác origin. Vì thế, chỉ so sánh status là không đủ.

## 4. Access-Control-Allow-Origin: giá trị nào mới đúng?

Giả sử API chỉ cho phép `https://portal.example.vn`.

### 4.1. Origin hợp lệ: phải khớp chính xác

Request:

~~~http
GET /api/reports HTTP/1.1
Origin: https://portal.example.vn
~~~

Response mong đợi khi endpoint thành công:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://portal.example.vn
Vary: Origin
Content-Type: application/json
~~~

Khi cấu hình danh sách origin cụ thể, test nên kiểm tra **chính xác chuỗi origin**, không chỉ kiểm tra header tồn tại. `https://portal.example.vn` khác `http://portal.example.vn` và `https://portal.example.vn:8443`.

### 4.2. Origin không hợp lệ: không được cấp quyền

Với request từ `https://unknown.example.vn`, server không được trả `Access-Control-Allow-Origin: https://unknown.example.vn` nếu policy cấm origin này.

Trong cấu hình CORS mặc định của Spring, preflight hoặc actual CORS request có origin không hợp lệ thường bị từ chối với `403 Forbidden` và **không có `Access-Control-Allow-Origin`**. Nếu API có gateway/filter tùy biến, mã trạng thái có thể khác; điều cốt lõi là không phát header chấp thuận nguồn bị cấm.

Đừng nhầm **vắng `Origin`** với origin bị cấm. Một request không có `Origin` thường không được xử lý như CORS request; nó có thể đi qua xác thực và tới controller mà không cần `Access-Control-Allow-Origin`.

### 4.3. Wildcard và credential

Nếu API cho phép công khai nội dung từ **mọi** origin và request không dùng chế độ credential đòi hỏi cấp phép tương ứng, server có thể trả:

~~~http
Access-Control-Allow-Origin: *
~~~

Khi frontend dùng cookie hoặc chế độ `fetch(..., { credentials: "include" })`, trình duyệt **không chấp nhận `Access-Control-Allow-Origin: *`** để chia sẻ phản hồi. Server cần trả origin cụ thể được phép và, nếu cần, `Access-Control-Allow-Credentials: true`. Với Spring, không kết hợp `allowedOrigins("*")` và `allowCredentials(true)`.

`Access-Control-Allow-Origin` cũng không phải một danh sách nhiều origin phân cách dấu phẩy. Server phải chọn một origin được phép (hoặc wildcard hợp lệ); với nhiều origin trong allowlist, phản hồi thường thay đổi theo `Origin` của request.

Ví dụ sai khi client gửi credential:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Ví dụ hợp lệ trong chính sách minh họa:

~~~http
Access-Control-Allow-Origin: https://portal.example.vn
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Dù có header CORS này, việc gửi cookie còn chịu chính sách `SameSite`/`Secure` của cookie và thiết lập frontend. Credential được phép qua CORS **không đồng nghĩa người dùng đã xác thực**.

## 5. Đối chiếu riêng phản hồi preflight và actual request

### 5.1. Preflight: cần đủ method và requested headers

Chính sách ví dụ của API:

- Origin được phép: `https://portal.example.vn`.
- Method được phép: `GET`, `POST`.
- Request header được phép: `Authorization`, `Content-Type`.
- Credential qua CORS: được phép.
- Thời gian cache preflight: 1.800 giây.

Một preflight hợp lệ:

~~~http
OPTIONS /api/reports HTTP/1.1
Origin: https://portal.example.vn
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Phản hồi điển hình từ bộ xử lý CORS mặc định của Spring:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://portal.example.vn
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: authorization,content-type
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Đối chiếu:

1. `Allow-Origin` bằng chính `Origin` hợp lệ đã gửi.
2. `Allow-Methods` bao gồm `POST`, **không chỉ OPTIONS**.
3. `Allow-Headers` đáp ứng **cả** `authorization` và `content-type`.
4. `Allow-Credentials` bằng `true` nếu policy yêu cầu.
5. `Max-Age` đúng giá trị cấu hình trong phép thử tích hợp.
6. `Vary` phản ánh các đầu vào dùng để quyết định preflight.

Tên HTTP header không phân biệt chữ hoa/thường. Khi kiểm tra danh sách `Access-Control-Allow-Headers`, hãy so khớp tên header theo cách không phân biệt hoa/thường và đừng phụ thuộc vào một cách viết hoa duy nhất.

Preflight có thể trả `200` hoặc `204` tùy implementation. Trong những đoạn mã dùng Spring CORS mặc định bên dưới, kỳ vọng `200` là dành cho cấu hình cụ thể của ví dụ.

### 5.2. Actual request: quan tâm Origin, Credential và Expose

Actual GET hợp lệ:

~~~http
GET /api/reports HTTP/1.1
Origin: https://portal.example.vn
~~~

Phản hồi có thể như sau:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://portal.example.vn
Access-Control-Allow-Credentials: true
Access-Control-Expose-Headers: X-Request-ID,X-Total-Count
X-Request-ID: req-demo-42
X-Total-Count: 1
Content-Type: application/json
~~~

Trên actual response, kiểm tra `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials` và `Access-Control-Expose-Headers` nếu frontend cần đọc các header ngoài danh sách safelisted.

**Không bắt buộc `Access-Control-Allow-Methods`/`Access-Control-Allow-Headers` có mặt trên actual response.** Những header này chủ yếu trả lời preflight. Tương tự, `Access-Control-Max-Age` là cache của **preflight**, không phải thời gian cache tài nguyên GET/POST.

### 5.3. Khi nào cần Access-Control-Expose-Headers?

Trình duyệt cho JavaScript đọc một nhóm response header safelisted, ví dụ `Content-Type` và `Cache-Control`. Nếu giao diện muốn đọc `X-Request-ID` để hiển thị mã hỗ trợ, hoặc `X-Total-Count` cho phân trang, API nên xuất:

~~~http
Access-Control-Expose-Headers: X-Request-ID,X-Total-Count
~~~

JavaScript có thể sử dụng:

~~~javascript
const response = await fetch("https://api.example.vn/api/reports", {
  credentials: "include"
});

console.log(response.headers.get("X-Request-ID"));
console.log(response.headers.get("X-Total-Count"));
~~~

Hai điều kiện **khác nhau**:

- `Access-Control-Allow-Headers` trả lời **client được gửi những request header nào**; dùng trong kiểm tra preflight.
- `Access-Control-Expose-Headers` trả lời **client được đọc thêm những response header nào**; cần trên phản hồi thực tế.

`Access-Control-Expose-Headers` không làm cho `Set-Cookie` trở thành header có thể đọc bằng JavaScript; `Set-Cookie` là *forbidden response-header name*. Với request dùng credential, không dựa vào wildcard `*` cho expose headers; liệt kê rõ các tên cần lộ.

## 6. Vai trò của Vary và Max-Age trong kiểm thử

### 6.1. Vary tránh cache phục vụ nhầm phản hồi

Khi CORS phản hồi khác nhau theo origin, một cache HTTP phải biết response phụ thuộc vào header `Origin`. Với preflight, phương thức và requested headers cũng có thể làm phản hồi thay đổi.

~~~http
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Một server có thể ghi nhiều dòng `Vary` hoặc gộp chúng thành một dòng phân cách dấu phẩy. Khi test, nên đọc **tất cả giá trị** rồi đối chiếu danh sách tên, thay vì bắt buộc server trình bày theo một cách xuống dòng cụ thể.

Lưu ý quan trọng: `Vary` thuộc cơ chế cache HTTP nói chung. Nếu có CDN/reverse proxy hoặc một lớp phát header CORS riêng, cần kiểm tra phản hồi HTTP cuối cùng của hệ thống, ngoài kết quả test trong ứng dụng.

### 6.2. Max-Age khác Cache-Control

`Access-Control-Max-Age: 1800` cho trình duyệt biết kết quả preflight có thể được giữ lại một khoảng thời gian; trình duyệt có thể giới hạn thời gian thực tế và chủ động gửi preflight lại. Nó không thay thế `Cache-Control` của nội dung API, không mang quyền truy cập và không bảo đảm request thật trong tương lai luôn thành công.

Vì vậy, một test có thể kiểm tra giá trị `Max-Age` trong phản hồi preflight; nhưng test HTTP thông thường không chứng minh được chính xác hành vi cache preflight của từng trình duyệt.

## 7. Cấu hình Spring Security Servlet để làm bài kiểm thử

Ví dụ Spring MVC + Spring Security khai báo một nguồn cấu hình CORS cho `/api/**`. Các class ở mục Servlet và mục Reactive là **hai biến thể ứng dụng riêng**, không khai báo đồng thời trong cùng một ứng dụng.

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(List.of("https://portal.example.vn"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setExposedHeaders(List.of("X-Request-ID", "X-Total-Count"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

`http.cors(Customizer.withDefaults())` cho phép Spring Security xử lý CORS **trước** các kiểm tra xác thực cần credential. Preflight bình thường không mang session hay bearer token của request thật, vì vậy nó không nên bị yêu cầu đăng nhập chỉ để hỏi policy.

Controller tối thiểu để tạo response header cần so sánh:

~~~java
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/reports")
class ReportsController {

    @GetMapping
    ResponseEntity<Map<String, String>> list(Authentication auth) {
        return ResponseEntity.ok()
            .header("X-Request-ID", "req-demo-42")
            .header("X-Total-Count", "1")
            .body(Map.of("viewer", auth.getName()));
    }

    @PostMapping
    ResponseEntity<Void> create() {
        return ResponseEntity.noContent().build();
    }
}
~~~

CSRF vẫn bật theo mặc định trong cấu hình này. Khi test POST thật với session-style security, vẫn phải đáp ứng CSRF, bất kể preflight có được chấp thuận.

## 8. MockMvc: kiểm chứng header cho phép, từ chối và phản hồi lỗi bảo mật

Sử dụng `spring-security-test` ở scope test, `@SpringBootTest` và `@AutoConfigureMockMvc` để test qua security filter chain của ứng dụng Servlet.

~~~java
import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.allOf;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.containsStringIgnoringCase;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletCorsHeaderTests {

    private static final String ALLOWED = "https://portal.example.vn";
    private static final String DENIED = "https://other.example.vn";

    @Autowired MockMvc mvc;

    @Test
    void preflightCoDuCacHeaderDuocPhep() throws Exception {
        mvc.perform(options("/api/reports")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization,content-type"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                containsString("POST")))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS,
                allOf(
                    containsStringIgnoringCase("authorization"),
                    containsStringIgnoringCase("content-type"))))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_MAX_AGE, "1800"))
            .andExpect(result -> {
                String vary = String.join(",",
                    result.getResponse().getHeaders(HttpHeaders.VARY))
                    .toLowerCase(Locale.ROOT);
                assertThat(vary).contains(
                    "origin",
                    "access-control-request-method",
                    "access-control-request-headers");
            });
    }

    @Test
    @WithMockUser(username = "learner")
    void actualGetCoAllowOriginVaExposeHeaders() throws Exception {
        mvc.perform(get("/api/reports")
                .header(HttpHeaders.ORIGIN, ALLOWED))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS,
                allOf(
                    containsStringIgnoringCase("x-request-id"),
                    containsStringIgnoringCase("x-total-count"))))
            .andExpect(header().string("X-Request-ID", "req-demo-42"))
            .andExpect(header().string("X-Total-Count", "1"));
    }

    @Test
    void preflightOriginBiCamKhongDuocCapAllowOrigin()
            throws Exception {
        mvc.perform(options("/api/reports")
                .header(HttpHeaders.ORIGIN, DENIED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void preflightMethodKhongDuocPhep() throws Exception {
        mvc.perform(options("/api/reports")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void preflightHeaderKhongDuocPhep() throws Exception {
        mvc.perform(options("/api/reports")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization,x-admin-override"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void originHopLeVanCanXacThuc() throws Exception {
        mvc.perform(get("/api/reports")
                .header(HttpHeaders.ORIGIN, ALLOWED))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED));
    }

    @Test
    @WithMockUser
    void khongCoOriginKhongBatBuocAllowOrigin() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }
}
~~~

### Vì sao mỗi assertion đều có ý nghĩa?

- `preflightCoDuCacHeaderDuocPhep` kiểm tra cả **origin**, **method**, **requested headers**, **credential**, **max-age** và những thành phần **Vary** liên quan. Nếu chỉ `status().isOk()`, bạn chưa chứng minh trình duyệt sẽ chấp thuận.
- `actualGetCoAllowOriginVaExposeHeaders` xác nhận server có **trả thực tế** `X-Request-ID` và **cho phép JavaScript đọc** header đó qua `Access-Control-Expose-Headers`. Một header tồn tại trong HTTP response chưa chắc đọc được từ JavaScript khác origin.
- Các test từ chối dùng bộ xử lý CORS mặc định của Spring, vì vậy kỳ vọng `403` và thiếu `Allow-Origin`. Không cần giả lập danh tính cho preflight.
- `originHopLeVanCanXacThuc` chứng minh phản hồi `401` có thể mang CORS header hợp lệ. Đây là **lỗi xác thực của request thật**, không phải bằng chứng CORS từ chối.
- `khongCoOriginKhongBatBuocAllowOrigin` xác nhận request ngoài ngữ cảnh CORS không cần phát `Allow-Origin`.

`@WithMockUser` tạo danh tính giả trong `SecurityContext` của bài test; nó không gửi token thật trên mạng. Trong ứng dụng JWT/OAuth2/OIDC, có thể dùng `jwt()`, `oauth2Login()` hoặc `oidcLogin()` trên request thật tùy cơ chế xác thực. Các helper này kiểm thử hành vi sau khi có ngữ cảnh xác thực giả lập, không xác minh chữ ký JWT hay luồng đăng nhập thật.

## 9. Reactive: cấu hình CORS và kiểm thử với WebTestClient

Với ứng dụng **Spring WebFlux**, dùng nguồn cấu hình CORS reactive và `SecurityWebFilterChain`. Ví dụ dưới đây thay thế cấu hình Servlet ở mục 7.

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://portal.example.vn"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setExposedHeaders(List.of("X-Request-ID", "X-Total-Count"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http,
                                    CorsConfigurationSource cors) {
        return http
            .cors(spec -> spec.configurationSource(cors))
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/**").authenticated()
                .anyExchange().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Controller WebFlux minh họa cùng header phản hồi:

~~~java
import java.security.Principal;
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class ReactiveReportsController {

    @GetMapping("/api/reports")
    Mono<ResponseEntity<Map<String, String>>> reports(
            Principal principal) {
        return Mono.just(ResponseEntity.ok()
            .header("X-Request-ID", "req-demo-42")
            .header("X-Total-Count", "1")
            .body(Map.of("viewer", principal.getName())));
    }
}
~~~

Đây là class cho ứng dụng WebFlux riêng; trong ứng dụng thực tế, dùng endpoint hiện có thay vì trùng lặp controller với Servlet.

Các test sau dùng `WebTestClient` gắn vào application context và tích hợp Spring Security Test để có thể mô phỏng người dùng cho actual request:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveCorsHeaderTests {

    private static final String ALLOWED = "https://portal.example.vn";

    @Autowired ApplicationContext context;

    WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void preflightCoAllowOriginVaAllowMethods() {
        client().options().uri("/api/reports")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED)
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true")
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_MAX_AGE, "1800")
            .expectHeader().exists(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS)
            .expectHeader().exists(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS);
    }

    @Test
    void actualResponseCoExposeHeaders() {
        client().mutateWith(mockUser("learner"))
            .get().uri("/api/reports")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED)
            .expectHeader().valueMatches(
                HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS,
                "(?i).*x-request-id.*x-total-count.*")
            .expectHeader().valueEquals(
                "X-Request-ID", "req-demo-42");
    }

    @Test
    void originBiCamKhongDuocCapAllowOrigin() {
        client().options().uri("/api/reports")
            .header(HttpHeaders.ORIGIN, "https://other.example.vn")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void headerLaKhongDuocCapQuyen() {
        client().options().uri("/api/reports")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization,x-admin-override")
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void chuaDangNhapVanCoCorsHeaderChoOriginHopLe() {
        client().get().uri("/api/reports")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED);
    }
}
~~~

`WebTestClient` chỉ so khớp phản hồi HTTP; nó không tự đóng vai cơ chế kiểm tra CORS trong trình duyệt. Dù test `200` thành công, vẫn phải xác nhận header phản hồi như ở trên.

## 10. Kiểm tra các trường hợp dễ hiểu sai

| Trường hợp | Quan sát | Cách kết luận |
| --- | --- | --- |
| `200` nhưng không có `Allow-Origin` | HTTP server có thể xử lý request; JavaScript khác origin có thể bị chặn đọc | Test phải có assertion header |
| `Allow-Origin: *` kèm `Allow-Credentials: true` | Phản hồi có header nhưng không hợp lệ cho credentialed CORS | Không coi là chấp thuận |
| `Allow-Origin` là origin khác origin đã gửi | Sai quyết định cấp quyền | So khớp giá trị chính xác |
| Preflight `200` nhưng thiếu `Allow-Headers: authorization` | Browser có thể không gửi actual request cần Authorization | Đối chiếu requested headers |
| Actual GET có `X-Request-ID` nhưng không có expose header | DevTools thấy header, JavaScript khác origin có thể không đọc được | Kiểm tra `Access-Control-Expose-Headers` |
| Preflight trả `Max-Age` nhưng actual GET không có | Bình thường | `Max-Age` phục vụ preflight |
| Response `401` có `Allow-Origin` đúng | CORS cho phép origin; yêu cầu chưa xác thực | Kiểm tra authentication riêng |
| Response `403` có `Allow-Origin` đúng | Có thể do quyền hoặc CSRF | Không kết luận CORS bị từ chối nếu chỉ nhìn status |
| Origin không được phép nhưng response có `Allow-Origin` phản chiếu lại | CORS có nguy cơ quá rộng | Kiểm tra allowlist, origin patterns, gateway |
| API hỗ trợ nhiều frontend nhưng `Vary: Origin` không đúng | Cache trung gian có thể phát header không phù hợp | Xem phản hồi HTTP qua CDN/proxy |

### 10.1. Sự khác biệt giữa request headers và response headers

- `Access-Control-Allow-Headers` **không có nghĩa** ứng dụng đã gửi các response header đó.
- `Access-Control-Expose-Headers` **không có nghĩa** frontend được gửi các request header đó.
- `Access-Control-Allow-Origin` **không có nghĩa** frontend đã đăng nhập.
- `Access-Control-Max-Age` **không có nghĩa** phản hồi business được cache.
- `Vary` **không có nghĩa** kết quả CORS tự động hợp lệ: nó là tín hiệu cho bộ nhớ đệm.

### 10.2. Phản hồi HTTP bị từ chối: phải phân loại đúng nguyên nhân

Ví dụ một API có `POST /api/reports`:

~~~text
Preflight hợp lệ + POST thật thiếu CSRF:
  OPTIONS /api/reports -> 200 + CORS headers
  POST /api/reports    -> 403 + có thể vẫn có CORS headers hợp lệ

Preflight có Origin bị cấm:
  OPTIONS /api/reports -> thường 403 + không cấp Allow-Origin
  Trình duyệt không gửi POST thật sau preflight thất bại
~~~

Khi dùng `@WithMockUser` hoặc `mockJwt()`, chỉ áp dụng danh tính giả để kiểm chứng authorization cho actual request. Không cần gửi JWT giả trên preflight; preflight thông thường được xử lý trước lớp xác thực.

## 11. Chẩn đoán bằng HTTP và DevTools

Dùng `curl` để yêu cầu preflight như trình duyệt:

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/reports' \
  -H 'Origin: https://portal.example.vn' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type'
~~~

Kiểm tra các header phản hồi: `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Credentials`, `Access-Control-Max-Age` và `Vary`.

Để xem actual GET của tài khoản hợp lệ trong môi trường có HTTP Basic, sử dụng credential thử nghiệm riêng của môi trường:

~~~bash
curl -i 'http://localhost:8080/api/reports' \
  -H 'Origin: https://portal.example.vn' \
  -u 'demo-user:demo-password'
~~~

Lưu ý ví dụ trên chỉ minh họa cú pháp; tài khoản thật cần được tạo trong môi trường dev. Không đưa credential production vào lệnh shell, log hay tài liệu.

Sau đó dùng Network tab của trình duyệt để xác nhận:

1. Trình duyệt có gửi preflight không; nếu có, `Access-Control-Request-Method` và `Access-Control-Request-Headers` mang giá trị gì?
2. Header `Access-Control-Allow-Origin` có khớp Origin không; với cookie, `Allow-Credentials` có đúng không?
3. Sau preflight hợp lệ, actual request có xuất hiện không; status thực sự của nó là gì?
4. Có header response mà JavaScript cần đọc nhưng thiếu `Access-Control-Expose-Headers` không?
5. Có CDN/reverse proxy sửa hoặc phát CORS header khác Spring không; `Vary` của phản hồi cuối cùng có phù hợp không?

**`curl` và các HTTP test client không thực thi chính sách CORS như trình duyệt.** Chúng giúp kiểm chứng phản hồi server; DevTools và thử nghiệm trên trình duyệt bổ sung bằng chứng về hành vi JavaScript thực tế.

## 12. Ma trận thực hành và tiêu chí hoàn thành

Chính sách bài thực hành: chỉ `https://portal.example.vn` được gọi `GET`/`POST` ở `/api/**` với `Authorization` và `Content-Type`; cho phép credential; frontend cần đọc `X-Request-ID` và `X-Total-Count`; `Max-Age` bằng 1.800 giây.

| Mã ca | HTTP đầu vào | Assertion trọng tâm |
| --- | --- | --- |
| P-OK | Preflight hợp lệ cho POST JSON + Authorization | Origin đúng; Methods chứa POST; Headers chứa hai tên; Credentials true; Max-Age 1800 |
| P-ORIGIN | Preflight từ `https://other.example.vn` | Không cấp `Allow-Origin` cho origin lạ; từ chối theo policy |
| P-METHOD | Preflight `Request-Method: DELETE` | Không cấp quyền cho method bị cấm |
| P-HEADER | Preflight `Request-Headers: x-admin-override` | Không cấp quyền cho header bị cấm |
| A-OK | Actual GET đã xác thực, Origin hợp lệ | `Allow-Origin` chính xác; response có `X-Request-ID`; `Expose-Headers` chứa tên header này |
| A-NO-ORIGIN | Actual GET đã xác thực, thiếu `Origin` | Không bắt buộc có `Allow-Origin` |
| A-UNAUTH | Actual GET chưa xác thực, Origin hợp lệ | Lỗi xác thực riêng; có thể vẫn có header CORS hợp lệ |
| A-CSRF | Actual POST đã xác thực nhưng thiếu CSRF trong cấu hình cần CSRF | Request thật bị từ chối dù preflight tương ứng có thể thành công |
| VARY | Preflight từ origin được phép | Các giá trị `Vary` phản ánh request header ảnh hưởng đến policy |
| EXPOSE | Actual GET trả header tùy biến | `Access-Control-Expose-Headers` cho phép JavaScript đọc những header cần thiết |

Hãy thử **cố ý xóa** `cors.setExposedHeaders(...)` trong cấu hình rồi chạy lại test actual GET. Test kiểm tra status và `Allow-Origin` vẫn có thể qua, nhưng test kiểm tra `Expose-Headers` phải thất bại. Đây là cách minh họa vì sao không thể chỉ dựa vào status.

Tiếp theo, thử thay `allowedOrigins` bằng origin khác và chạy test P-OK/P-ORIGIN. Bộ test tốt sẽ phát hiện cả trường hợp *cho phép sai* lẫn *từ chối sai*.

**Tiêu chí hoàn thành:** bạn chứng minh được `Access-Control-Allow-Origin` khớp chính xác origin được cho phép, các header preflight khớp phương thức/header yêu cầu, credential/expose/max-age/vary được đối chiếu đúng vai trò và các ca xác thực/phân quyền/CSRF được kiểm tra độc lập. Đây là nền tảng để mở rộng bộ kiểm thử HTTP security trên cả Servlet và Reactive với `SecurityContext`, `@WithMockUser` và JWT/OAuth2/OIDC giả lập.
