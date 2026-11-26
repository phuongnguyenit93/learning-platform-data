# Preflight với OPTIONS, Access-Control-Request-Method và header yêu cầu

> **Chương:** CORS và header bảo vệ  
> **Module:** SPRING_SECURITY_TESTING — thực hành kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive.

## 1. Mục tiêu và tình huống thực tế

Một frontend triển khai tại `https://app.example.vn` gửi yêu cầu `POST https://api.example.vn/api/orders`, body JSON và header `Authorization: Bearer ...`. Trước khi gửi yêu cầu thật, trình duyệt thường hỏi API bằng một yêu cầu **preflight**: *Origin này có được gửi POST kèm các header dự định sử dụng hay không?*

Với Spring Security, câu hỏi này có hai mặt:

- **CORS** xác định JavaScript chạy từ một origin có được thực hiện lời gọi và đọc phản hồi xuyên origin hay không.
- **Security filter chain** xác thực danh tính, kiểm tra quyền, session/JWT và CSRF cho yêu cầu thật.

Một API có thể xử lý đăng nhập chính xác nhưng preflight bị chặn `401`; lúc đó trình duyệt không tiếp tục gửi request thật. Ngược lại, preflight được phép không bảo đảm `POST` kế tiếp có quyền hoặc token CSRF hợp lệ.

Bài này tập trung vào **preflight với phương thức OPTIONS**, đặc biệt ba header `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`. Sau bài học, bạn có thể nhận diện đúng preflight, xây dựng chính sách CORS, kiểm thử với **MockMvc** và **WebTestClient**, và phân tích các ca cho phép hoặc từ chối mà không nhầm với lỗi xác thực.

## 2. Khi nào trình duyệt gửi preflight?

Trình duyệt áp dụng CORS khi trang web gọi tài nguyên thuộc origin khác; origin là bộ ba **scheme + host + port**. Không phải mọi request CORS đều có preflight.

Một request được miễn preflight do các tiêu chí *CORS-safelisted* thường chỉ dùng `GET`, `HEAD` hoặc `POST`, cùng một tập header/giá trị giới hạn. Chẳng hạn, `POST` sử dụng `Content-Type: text/plain` có thể thuộc diện không cần preflight nếu thỏa các điều kiện khác.

Các thay đổi sau thường khiến trình duyệt **phải preflight**:

| Yêu cầu JavaScript định gửi | Có preflight? | Lý do |
| --- | --- | --- |
| `GET` với các header mặc định phù hợp điều kiện safelist | Thường không | Phương thức/header thuộc diện safelist |
| `POST` với `Content-Type: application/json` | Có | Giá trị Content-Type không thuộc nhóm safelisted |
| `GET` kèm `Authorization: Bearer ...` | Có | `Authorization` không phải header safelisted |
| `DELETE`, kể cả không có body | Có | Phương thức không thuộc nhóm safelisted |
| `PUT` kèm `X-Request-ID` | Có | Phương thức và header đều không safelisted |
| `POST` kèm `Content-Type: application/x-www-form-urlencoded` | Có thể không | Còn phụ thuộc các header và điều kiện safelist khác |

**Không dựa duy nhất vào tên phương thức** để dự đoán preflight. Kiểu nội dung, các header mà mã JavaScript đặt và những điều kiện khác của trình duyệt cũng tham gia quyết định. Chẳng hạn, `GET` có `Authorization` vẫn thường phải preflight.

Phải phân biệt:

- **HTTP OPTIONS:** một phương thức HTTP hợp lệ. Gọi `OPTIONS /api/orders` đơn thuần chưa đủ để tạo preflight.
- **CORS preflight:** yêu cầu `OPTIONS` có `Origin` **và** `Access-Control-Request-Method`; `Access-Control-Request-Headers` được thêm khi cần khai báo header yêu cầu thật.

## 3. Đọc một yêu cầu preflight

Giả sử mã frontend:

~~~javascript
await fetch("https://api.example.vn/api/orders", {
  method: "POST",
  headers: {
    "Authorization": "Bearer <access-token>",
    "Content-Type": "application/json"
  },
  body: JSON.stringify({ sku: "BOOK-1", quantity: 1 })
});
~~~

Do có `Authorization` và `application/json`, trình duyệt gửi trước một yêu cầu tương tự:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.vn
Origin: https://app.example.vn
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Ý nghĩa của từng thành phần:

| Thành phần preflight | Nội dung | Dùng để quyết định |
| --- | --- | --- |
| `OPTIONS` | Phương thức của **preflight** | Máy chủ cần xử lý truy vấn khả năng CORS |
| `Origin` | `https://app.example.vn` | Có cho phép trang này gọi API không? |
| `Access-Control-Request-Method` | `POST` | Yêu cầu thật dự kiến dùng phương thức nào? |
| `Access-Control-Request-Headers` | `authorization,content-type` | Yêu cầu thật dự kiến gửi những **tên header** nào? |

Điểm rất dễ nhầm: **phương thức của preflight luôn là OPTIONS, nhưng phương thức phải đưa vào kiểm tra chính sách là giá trị của `Access-Control-Request-Method`**. Nếu test gửi `OPTIONS` mà không có header này thì không đang kiểm thử việc cho phép `POST`.

Header `Access-Control-Request-Headers` chỉ chứa **tên** header, không chứa giá trị. Ví dụ `authorization,content-type` là đúng; gửi bearer token nguyên văn trong header này là sai. Tên HTTP header không phân biệt chữ hoa/thường nên `Authorization` và `authorization` cần được xử lý như một tên.

### 3.1. Phản hồi chấp thuận

Nếu máy chủ cho phép đúng origin, phương thức và các header yêu cầu:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.vn
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: authorization,content-type
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Các header phản hồi chủ yếu:

- `Access-Control-Allow-Origin`: origin mà API đồng ý. Với credential, giá trị phải là origin cụ thể phù hợp, không phải `*`.
- `Access-Control-Allow-Methods`: các phương thức được phép dùng cho yêu cầu thật; phải bao gồm `POST` của ví dụ.
- `Access-Control-Allow-Headers`: các tên header yêu cầu thật được phép; phải đáp ứng cả `authorization` và `content-type`.
- `Access-Control-Allow-Credentials`: áp dụng khi truy cập kèm credential như cookie trong chế độ `credentials: "include"`; không thay thế xác thực hay CSRF.
- `Access-Control-Max-Age`: khoảng thời gian trình duyệt *có thể* cache kết quả preflight (trình duyệt có thể áp giới hạn riêng).
- `Vary`: giúp các cache HTTP phân biệt phản hồi theo những header có ảnh hưởng đến quyết định CORS.

Một preflight thành công có thể trả `200` hoặc `204` tùy server/filter. Tiêu chí kỹ thuật không chỉ là status: **cần kiểm tra đúng bộ header cho phép**. Trong các ví dụ dùng trình xử lý CORS mặc định của Spring, phản hồi preflight hợp lệ thường có `200 OK`.

### 3.2. Phản hồi bị từ chối

Ví dụ origin hợp lệ nhưng phương thức dự định là `DELETE` trong khi policy chỉ cho `GET` và `POST`:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.vn
Access-Control-Request-Method: DELETE
~~~

Bộ xử lý CORS mặc định của Spring thường trả `403 Forbidden` khi origin, method hoặc requested headers không được phép; phản hồi này không cấp `Access-Control-Allow-Origin` tương ứng để cho phép trình duyệt.

Không phải mọi máy chủ đều trả cùng status khi từ chối CORS. Khi kiểm thử hệ thống có gateway hoặc custom filter, xác nhận **origin/method/header không được cấp quyền** và đặc tả lỗi của chính hệ thống, thay vì cố định `403` bất kể kiến trúc.

## 4. Preflight đi qua bảo mật như thế nào?

~~~mermaid
flowchart TD
    A["JavaScript định gửi POST + Authorization + JSON"] --> B["Trình duyệt gửi OPTIONS preflight"]
    B --> C["CORS kiểm tra Origin"]
    C -->|Từ chối| X["Preflight thất bại"]
    C -->|Cho phép| D["Kiểm tra Request-Method: POST"]
    D -->|Từ chối| X
    D -->|Cho phép| E["Kiểm tra Request-Headers"]
    E -->|Từ chối| X
    E -->|Cho phép| F["Trả Access-Control-Allow-*"]
    F --> G["Trình duyệt gửi POST thật"]
    G --> H["Spring Security: authn, authz, CSRF"]
    H -->|Từ chối| I["401/403 hoặc phản hồi theo cấu hình"]
    H -->|Cho phép| J["Controller xử lý request"]
~~~

**Preflight thường không mang session cookie hoặc bearer token của yêu cầu thật.** Do đó nếu filter xác thực chạy trước bộ xử lý CORS và yêu cầu phải có đăng nhập cho `OPTIONS`, trình duyệt có thể nhận `401` trước khi kiểm tra policy. Cấu hình Spring Security nên xử lý CORS đúng thứ tự.

Cần nhớ ba sự thật độc lập:

1. `Access-Control-Allow-Methods: POST` chỉ nói **POST được phép xét theo CORS**. Nó không chứng minh người dùng có quyền tạo đơn hàng.
2. Preflight `200` không đảm bảo `POST` thật thành công. HTTP request thật vẫn có thể trả `401` (chưa đăng nhập), `403` (thiếu quyền/CSRF) hoặc lỗi nghiệp vụ.
3. CORS được trình duyệt thực thi; `curl` và các HTTP client tùy ý có thể gửi header `Origin` giả. **Không dùng CORS thay cho xác thực hay phân quyền**.

## 5. Cấu hình mẫu: Servlet với Spring MVC và Spring Security

Giả sử API `/api/orders` cho phép frontend `https://app.example.vn` gọi `GET` và `POST`; khi POST, frontend được khai báo `Authorization` và `Content-Type`. Ví dụ cấu hình:

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
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.vn"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

`http.cors(Customizer.withDefaults())` kích hoạt xử lý CORS trong chuỗi bảo mật để preflight được xét trước các bộ lọc yêu cầu xác thực. Phần `CorsConfigurationSource` khai báo chính sách; cả hai cần được ghép đúng khi cấu hình thủ công.

Ví dụ controller đủ để kiểm tra cả preflight lẫn POST thật:

~~~java
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrdersController {

    @GetMapping
    Map<String, String> list(Authentication user) {
        return Map.of("viewer", user.getName());
    }

    @PostMapping
    ResponseEntity<Void> create(@RequestBody Map<String, Object> input) {
        return ResponseEntity.noContent().build();
    }
}
~~~

CSRF trong cấu hình trên vẫn bật theo mặc định cho các phương thức cần bảo vệ như POST. Điều này hữu ích cho bài kiểm thử: **preflight không cần CSRF token; POST thật có thể cần**. Nếu ứng dụng là resource server JWT không dùng cookie, chính sách CSRF cần được quyết định từ kiến trúc xác thực thực tế, không tắt CSRF chỉ để làm cho bài test xanh.

## 6. Kiểm thử preflight bằng MockMvc

Với Spring Boot Test và dependency `spring-security-test` ở scope `test`, dùng `@SpringBootTest` + `@AutoConfigureMockMvc` để chạy qua filter chain của ứng dụng Servlet. Đây là kiểm thử tích hợp bộ lọc, không phải gọi trực tiếp phương thức controller.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.allOf;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.containsStringIgnoringCase;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletPreflightTests {

    private static final String ORIGIN = "https://app.example.vn";
    @Autowired MockMvc mvc;

    @Test
    void choPhepPostVoiAuthorizationVaContentType() throws Exception {
        mvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization,content-type"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                containsString("POST")))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS,
                allOf(containsStringIgnoringCase("authorization"),
                      containsStringIgnoringCase("content-type"))))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
    }

    @Test
    void tuChoiDeleteDuOriginDuocPhep() throws Exception {
        mvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void tuChoiHeaderChuaDuocKhaiBao() throws Exception {
        mvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization,x-superuser"))
            .andExpect(status().isForbidden());
    }

    @Test
    void tuChoiOriginKhac() throws Exception {
        mvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN, "https://evil.example.vn")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void optionsKhongCoOriginKhongPhaiPreflight() throws Exception {
        mvc.perform(options("/api/orders")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    @WithMockUser(username = "learner")
    void postThatCanCsrfVaCoCorsHeader() throws Exception {
        mvc.perform(post("/api/orders")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"BOOK-1\",\"quantity\":1}")
                .with(csrf()))
            .andExpect(status().isNoContent())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN));
    }

    @Test
    @WithMockUser(username = "learner")
    void postThatKhongCsrfBiTuChoiDuPreflightHopLe() throws Exception {
        mvc.perform(post("/api/orders")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"BOOK-1\",\"quantity\":1}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void getThatKhongCoDanhTinhBiChanBoiSecurity() throws Exception {
        mvc.perform(get("/api/orders")
                .header(HttpHeaders.ORIGIN, ORIGIN))
            .andExpect(status().isUnauthorized());
    }
}
~~~

### 6.1. Giải thích các phép thử quan trọng

**`choPhepPostVoiAuthorizationVaContentType`** có `OPTIONS`, origin hợp lệ, `Request-Method: POST` và *hai tên header* yêu cầu thật. Test xác nhận preflight được phép mà **không cần `@WithMockUser` hoặc bearer token**. Điều này kiểm tra thứ tự xử lý CORS trước authentication.

**`tuChoiDeleteDuOriginDuocPhep`** chứng minh origin hợp lệ *không đồng nghĩa mọi phương thức đều được phép*. Thay đổi `Access-Control-Request-Method` độc lập với phương thức HTTP OPTIONS.

**`tuChoiHeaderChuaDuocKhaiBao`** chỉ thêm một header lạ vào danh sách; chính sách không được cho phép toàn bộ chỉ vì `Authorization` hợp lệ. Khi nhiều tên được liệt kê, mọi header nằm ngoài safelist có liên quan phải được chính sách đáp ứng.

**`optionsKhongCoOriginKhongPhaiPreflight`** không khẳng định mã trạng thái vì phương thức OPTIONS thông thường có thể được xử lý khác nhau theo routing/security. Nó chỉ kiểm tra không phát header `Allow-Origin` khi không có yêu cầu CORS.

Hai phép thử POST dùng `@WithMockUser` để tạo danh tính giả lập trong `SecurityContext`, và `csrf()` cho POST hợp lệ. Chúng chứng minh rằng **qua preflight không bỏ qua được CSRF**. Nếu ứng dụng dùng JWT/OAuth2/OIDC, bạn có thể thay nguồn danh tính bằng `jwt()`, `oauth2Login()` hoặc `oidcLogin()` từ spring-security-test tùy kiến trúc; test đó kiểm tra bảo vệ endpoint với danh tính giả lập, **không tự kiểm tra chữ ký token hoặc luồng đăng nhập thật**.

Lưu ý: ví dụ dùng HTTP Basic để thống nhất kỳ vọng `401` cho request chưa xác thực. Khi dùng form login hoặc entry point tùy biến, phản hồi có thể là redirect hay status khác.

## 7. Kiểm thử preflight trên ứng dụng Reactive với WebTestClient

Với Spring WebFlux, cấu hình CORS cần dùng kiểu reactive của `CorsConfigurationSource`. Ví dụ đặt chính sách trực tiếp vào Spring Security WebFlux:

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
        cors.setAllowedOrigins(List.of("https://app.example.vn"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

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

Cấu hình này dùng cơ chế CORS do `SecurityWebFilterChain` quản lý. Nếu dự án chọn `CorsWebFilter` độc lập, cần bảo đảm filter chạy trước bộ lọc security và tránh hai cơ chế có policy mâu thuẫn.

Kiểm thử tương ứng bằng `WebTestClient`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactivePreflightTests {

    private static final String ORIGIN = "https://app.example.vn";
    @Autowired WebTestClient client;

    @Test
    void preflightHopLe() {
        client.options().uri("/api/orders")
            .header(HttpHeaders.ORIGIN, ORIGIN)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization,content-type")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN)
            .expectHeader().exists(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS);
    }

    @Test
    void preflightSaiMethod() {
        client.options().uri("/api/orders")
            .header(HttpHeaders.ORIGIN, ORIGIN)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE")
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void preflightSaiHeader() {
        client.options().uri("/api/orders")
            .header(HttpHeaders.ORIGIN, ORIGIN)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "x-superuser")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void preflightSaiOrigin() {
        client.options().uri("/api/orders")
            .header(HttpHeaders.ORIGIN, "https://evil.example.vn")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

`WebTestClient` không thực thi hạn chế CORS như trình duyệt. Nó gửi HTTP request và cho phép xác nhận phản hồi; vì vậy vẫn cần kiểm tra **các header `Access-Control-Allow-*`**, không chỉ status.

Lớp test reactive này được thiết kế cho ứng dụng Spring Boot WebFlux thực sự được nạp trong ngữ cảnh test. Nếu muốn kiểm tra request thật có danh tính, dùng bộ test security của WebFlux, ví dụ `SecurityMockServerConfigurers.mockJwt()` khi security test client đã được liên kết với Spring Security. Phân biệt bộ giả lập danh tính với kiểm thử OAuth2/OIDC end-to-end.

## 8. Ma trận kiểm thử và cách giải thích kết quả

| Tình huống | Header preflight chính | Kỳ vọng với chính sách ví dụ |
| --- | --- | --- |
| POST JSON có Authorization | `Origin: https://app.example.vn`; `Request-Method: POST`; `Request-Headers: authorization,content-type` | Chấp thuận; phản hồi cho phép origin, POST và hai header |
| GET có Authorization | `Request-Method: GET`; `Request-Headers: authorization` | Chấp thuận |
| DELETE | `Request-Method: DELETE` | Từ chối dù origin hợp lệ |
| POST kèm header chưa khai báo | `Request-Headers: x-superuser` | Từ chối |
| Nhiều header, trong đó một cái bị cấm | `Request-Headers: authorization,x-superuser` | Từ chối, không chấp nhận một phần |
| Origin ngoài danh sách | `Origin: https://evil.example.vn` | Từ chối |
| Origin khác scheme | `Origin: http://app.example.vn` | Từ chối |
| Không có `Origin` | Chỉ có `Request-Method` | Không phải preflight CORS đúng nghĩa |
| Không có `Access-Control-Request-Method` | `OPTIONS` + `Origin` | Không phải preflight hợp lệ theo cấu trúc CORS |
| Preflight hợp lệ nhưng POST thiếu CSRF | Preflight vẫn chấp thuận | POST thật có thể `403` |
| Preflight hợp lệ nhưng GET không đăng nhập | Preflight vẫn chấp thuận | GET thật có thể `401` |

**Đừng kiểm tra rằng preflight đã chạy controller.** Spring thường trả lời preflight tại CORS filter, không gọi logic nghiệp vụ. Khi cần chứng minh một POST thật thành công, phải viết riêng bài test POST và các điều kiện bảo mật của nó.

### Các lỗi giả định dễ khiến test “xanh” sai

- Chỉ kiểm tra `status().isOk()` mà không kiểm tra `Access-Control-Allow-Origin`, `Allow-Methods` hoặc `Allow-Headers`.
- Gửi `OPTIONS` nhưng quên `Access-Control-Request-Method`, rồi kết luận API cho phép POST.
- Gửi `Authorization: Bearer ...` trên chính preflight thay vì khai báo **tên** `authorization` trong `Access-Control-Request-Headers`.
- Gán `@WithMockUser` vào mọi preflight, khiến test không phát hiện thứ tự filter xử lý sai và preflight thực tế đòi đăng nhập.
- Dùng wildcard `allowedHeaders("*")` trong test và tưởng rằng đã chứng minh header lạ bị cấm.
- Không kiểm tra trường hợp có **nhiều** requested headers, trong đó chỉ một header được phép.
- Giả định `Vary` và `Access-Control-Max-Age` luôn xuất hiện giống nhau khi qua reverse proxy/cache, thay vì kiểm tra đáp ứng yêu cầu ở môi trường cụ thể.

## 9. Dùng curl đối chiếu trong môi trường chạy thật

Tạo một preflight gửi tới API; ví dụ bên dưới giả sử ứng dụng chạy ở `localhost:8080`:

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/orders' \
  -H 'Origin: https://app.example.vn' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type'
~~~

Kiểm tra có `Access-Control-Allow-Origin` đúng origin, `Allow-Methods` chứa POST, `Allow-Headers` đáp ứng hai tên header và phản hồi không yêu cầu đăng nhập. Thử đổi riêng một header để cô lập nguyên nhân:

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/orders' \
  -H 'Origin: https://app.example.vn' \
  -H 'Access-Control-Request-Method: DELETE'

curl -i -X OPTIONS 'http://localhost:8080/api/orders' \
  -H 'Origin: https://app.example.vn' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,x-superuser'
~~~

`curl` chỉ giúp xem phản hồi của server; nó không tự chặn request hay dữ liệu theo CORS như trình duyệt. Hãy dùng tab Network/Console trên trình duyệt để kiểm tra liệu request thật có được gửi sau preflight và lỗi xuất hiện ở bước nào.

Nếu gặp lỗi:

1. **Preflight `401`:** kiểm tra CORS filter có chạy trước cơ chế authentication không. Không dùng việc tắt xác thực toàn API làm cách sửa.
2. **Preflight `403`:** kiểm tra từng yếu tố origin, method, header và path, đồng thời xem có gateway/filter phía trước ứng dụng từ chối không.
3. **Preflight `200` nhưng trình duyệt báo CORS:** kiểm tra thiếu hoặc sai `Allow-Origin`, `Allow-Methods`, `Allow-Headers`, `Allow-Credentials`; đừng chỉ nhìn status.
4. **Preflight `200`, POST thật `403`:** kiểm tra CSRF hoặc phân quyền của yêu cầu thật; preflight chỉ quyết định khả năng gửi yêu cầu.
5. **Lúc được lúc không khi đi qua CDN:** kiểm tra chính sách cache và `Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers` ở phản hồi có phụ thuộc vào chúng. Preflight cache ở trình duyệt cũng có thể khiến thay đổi policy chưa được thấy ngay.

## 10. Bài thực hành tự kiểm chứng

Một nhóm triển khai API Spring Security có chính sách: chỉ `https://app.example.vn` được dùng `GET`, `POST` tại `/api/**`; các header không safelisted được chủ động cho phép là `Authorization` và `Content-Type`. Frontend gửi POST JSON có Bearer token.

Hãy hoàn thành các bước theo đúng thứ tự logic:

1. Viết test preflight `OPTIONS /api/orders` có `Origin`, `Access-Control-Request-Method: POST`, `Access-Control-Request-Headers: authorization,content-type`; xác nhận HTTP thành công và các header CORS.
2. Đổi riêng `Access-Control-Request-Method` thành `DELETE`; khẳng định chính sách từ chối.
3. Trả về `POST` nhưng thêm `x-superuser` vào danh sách requested headers; khẳng định chính sách từ chối.
4. Gỡ hết danh tính test trên preflight; chứng minh preflight hợp lệ vẫn được xử lý khi chưa đăng nhập.
5. Gửi `POST` thật đã xác thực nhưng thiếu CSRF trong cấu hình có CSRF; kiểm tra rằng endpoint vẫn bảo vệ tài nguyên.
6. Chạy bộ ca này qua **MockMvc** nếu dùng Servlet, hoặc **WebTestClient** nếu dùng WebFlux; đối chiếu kết quả với HTTP thực tế.

**Kết quả học tập cần đạt:** đọc được toàn bộ quá trình preflight; biết rõ `OPTIONS` là phương thức của câu hỏi, `Access-Control-Request-Method` là phương thức thật sắp dùng, `Access-Control-Request-Headers` là danh sách **tên** header cần cấp quyền; kiểm chứng độc lập quyết định **CORS** và quyết định **xác thực/phân quyền/CSRF**. Đây là cơ sở để mở rộng bài test Spring Security với `SecurityContext`, `@WithMockUser`, JWT/OAuth2/OIDC giả lập cùng các header bảo vệ HTTP khác.
