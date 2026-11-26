# Nguồn, phương thức hoặc header không được phép

> **Chương:** CORS và header bảo vệ  
> **Module:** SPRING_SECURITY_TESTING — kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive.

## 1. Bài toán: chứng minh chính sách thật sự từ chối

Nhóm phát triển có frontend tại `https://app.example.vn` và API tại `https://api.example.vn`. API cần cho frontend đọc tài liệu và tạo tài liệu mới, nhưng không muốn JavaScript từ các website ngoài danh sách được phép truy cập phản hồi. Khi cấu hình CORS, việc kiểm tra **nguồn được phép** là chưa đủ: phải kiểm tra cả những trường hợp bị từ chối.

Ba nhóm đầu vào cần kiểm thử riêng:

1. **Nguồn không được phép:** giá trị `Origin` không nằm trong danh sách của API.
2. **Phương thức không được phép:** preflight mang `Access-Control-Request-Method` ngoài danh sách phương thức đã cấu hình.
3. **Header không được phép:** preflight mang `Access-Control-Request-Headers` chứa một hoặc nhiều tên header không được chính sách chấp thuận.

Ví dụ, `https://app.example.vn` được gọi `GET` và `POST` kèm `Authorization`/`Content-Type`; nhưng `https://evil.example.vn`, `DELETE` và `X-Admin-Override` đều phải bị từ chối.

Trong module **SPRING_SECURITY_TESTING**, một ca kiểm thử CORS tốt cần chứng minh **cấu hình từ chối đúng** và vẫn phân biệt được lớp CORS với xác thực, phân quyền, CSRF, JWT/OAuth2/OIDC giả lập. Bài này hướng dẫn viết các ca kiểm thử âm (*negative tests*) bằng **MockMvc** cho Servlet và **WebTestClient** cho Reactive.

Sau khi hoàn thành, bạn có thể:

- Xác định chính xác đầu vào nào làm một yêu cầu CORS bị từ chối.
- Kiểm tra cả status và header của phản hồi, tránh suy luận từ riêng `401` hay `403`.
- Tách lỗi cấu hình CORS khỏi lỗi xác thực, thiếu quyền hay CSRF.
- Thiết kế bảng ca kiểm thử có một trường hợp hợp lệ làm đối chứng và các trường hợp không hợp lệ độc lập.
- Nhận ra giới hạn của CORS: cơ chế này chủ yếu được **trình duyệt** thực thi và không thay thế bảo vệ endpoint ở phía server.

## 2. Chính sách giả định để làm chuẩn đối chiếu

Mọi ví dụ dùng một chính sách xác định rõ ràng:

| Thành phần | Quy tắc |
| --- | --- |
| Đường dẫn áp dụng | `/api/**` |
| Origin được phép | `https://app.example.vn` |
| Phương thức được phép | `GET`, `POST` |
| Header yêu cầu được phép | `Authorization`, `Content-Type` |
| Cho phép credential trong CORS | `true` |
| Max age của preflight | 600 giây |
| Endpoint ví dụ | `GET /api/documents` và `POST /api/documents` |

**Mục tiêu phép thử:** khi dữ liệu đầu vào nằm ngoài chính sách trên, server không được gửi những header CORS khiến trình duyệt coi yêu cầu là được cấp quyền.

Phân biệt chính xác **origin** với một URL đầy đủ. Origin là `scheme://host[:port]`; path/query không thuộc origin. Với allowlist chỉ chứa `https://app.example.vn`:

| Origin trong yêu cầu | Kết luận | Lý do |
| --- | --- | --- |
| `https://app.example.vn` | Được phép theo Origin | Khớp chính xác origin khai báo |
| `http://app.example.vn` | Bị từ chối | Khác giao thức HTTP/HTTPS |
| `https://app.example.vn:8443` | Bị từ chối | Khác cổng |
| `https://other.example.vn` | Bị từ chối | Khác host |
| `https://app.example.vn.evil.test` | Bị từ chối | Tên miền được thêm hậu tố, không phải host được phép |
| `null` | Bị từ chối theo chính sách ví dụ | Origin dạng opaque không được cấp quyền |
| Không có header `Origin` | Không phải CORS request | Không thể kết luận đây là một origin bị cấm |

Một origin hợp lệ mới vượt qua được **bước kiểm tra nguồn**. Máy chủ còn phải xét phương thức và header theo loại request. Các giá trị `Host`, `Referer` hoặc đường dẫn của request không thay thế `Origin`.

## 3. Phân biệt hai nơi chính sách có thể từ chối

### 3.1. Preflight: từ chối trước yêu cầu thật

Preflight là request `OPTIONS` mang cả `Origin` lẫn `Access-Control-Request-Method`; có thể mang thêm `Access-Control-Request-Headers`:

~~~http
OPTIONS /api/documents HTTP/1.1
Host: api.example.vn
Origin: https://app.example.vn
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Đây là một preflight **hợp lệ** theo policy của bài. Với cấu hình mặc định phù hợp ở Spring, phản hồi điển hình:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.vn
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: authorization,content-type
Access-Control-Allow-Credentials: true
~~~

Nếu thay riêng `Access-Control-Request-Method: POST` bằng `DELETE`, bộ xử lý CORS mặc định của Spring thường trả:

~~~http
HTTP/1.1 403 Forbidden

Invalid CORS request
~~~

Phản hồi từ chối không cấp `Access-Control-Allow-Origin` cho origin đang yêu cầu. Trình duyệt vì thế không tiếp tục gửi request thật sau preflight thất bại. **Không cần bearer token hoặc session cookie trên preflight** để thử xem policy cho phép hay không.

Lưu ý `OPTIONS` một mình không đủ: nếu thiếu `Origin` hoặc `Access-Control-Request-Method`, bạn chưa tạo đúng preflight CORS. Test có thể đi vào nhánh xử lý hoàn toàn khác.

### 3.2. Yêu cầu thật: từ chối khi không có preflight hoặc client tự gửi

Không phải mọi yêu cầu CORS đều có preflight. Ví dụ một GET đơn giản từ origin khác có thể được trình duyệt gửi ngay:

~~~http
GET /api/documents HTTP/1.1
Origin: https://evil.example.vn
~~~

Với bộ lọc CORS mặc định của Spring, actual request CORS có origin không được phép thường nhận `403` mà chưa chạy logic nghiệp vụ. Tuy nhiên, **không được mặc định mọi CORS request bị cấm đều chưa tới server**: trình duyệt có thể đã gửi một *simple request* trước khi quyết định có cho JavaScript đọc phản hồi hay không. Những tác động của request thật ở hệ thống có thể đã xảy ra trong các cấu hình khác.

Điều này đặc biệt quan trọng với request dùng cookie:

- CORS kiểm soát khả năng truy cập xuyên origin ở phía trình duyệt, không bảo vệ endpoint trước client tùy ý.
- Kiểm tra **CSRF** với các thao tác làm thay đổi trạng thái vẫn cần khi kiến trúc dùng cookie/session và có nguy cơ CSRF.
- Xác thực và phân quyền phải chạy cho request thật theo yêu cầu nghiệp vụ; cấp quyền CORS không đồng nghĩa người dùng có quyền với dữ liệu.

### 3.3. Luồng ra quyết định

~~~mermaid
flowchart TD
    A["Request tới API"] --> B{"Có Origin?"}
    B -- "Không" --> K["Không áp dụng kiểm tra CORS"]
    B -- "Có" --> C{"Origin được phép?"}
    C -- "Không" --> X["Từ chối CORS"]
    C -- "Có" --> D{"Preflight?"}
    D -- "Có" --> E{"Request-Method được phép?"}
    E -- "Không" --> X
    E -- "Có" --> F{"Requested headers được phép?"}
    F -- "Không" --> X
    F -- "Có" --> G["Trả header CORS cho preflight"]
    D -- "Không" --> H{"Method của request thật được phép?"}
    H -- "Không" --> X
    H -- "Có" --> I["CORS chấp thuận; xét authn/authz/CSRF"]
    K --> I
    I --> J["Phản hồi HTTP của ứng dụng"]
~~~

Sơ đồ trình bày luồng kiểm tra điển hình trong ứng dụng Spring đã tích hợp CORS với security filter. Với reverse proxy, gateway hoặc custom filter, thứ tự và mã trạng thái cụ thể có thể thay đổi.

## 4. Ba nhóm ca kiểm thử âm

### 4.1. Nguồn không được phép

Một test tốt thay **một yếu tố**: giữ `POST` và các header thuộc policy, chỉ đổi origin.

~~~http
OPTIONS /api/documents HTTP/1.1
Origin: https://evil.example.vn
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

**Kỳ vọng khi dùng Spring CORS mặc định:** thường `403 Forbidden`; không có `Access-Control-Allow-Origin` cấp quyền. Nếu origin lạ mà phản hồi vẫn mang `Access-Control-Allow-Origin: https://evil.example.vn` thì cần kiểm tra cấu hình quá rộng, chẳng hạn danh sách mẫu khớp ngoài ý muốn.

Các biến thể cần cân nhắc: HTTP thay vì HTTPS, cổng lạ, host có hậu tố đánh lừa và `Origin: null`. Thử cả origin được phép để bảo đảm test không báo sai rằng *mọi* origin đều bị chặn.

**Lưu ý về wildcard:** `allowedOrigins("*")` không được dùng với `allowCredentials(true)` theo cơ chế Spring CORS; nếu cần khớp có điều kiện, Spring hỗ trợ `allowedOriginPatterns`. Tuy nhiên, mẫu `https://*.example.vn` có thể cho phép các subdomain không mong muốn; hãy ưu tiên danh sách origin cụ thể khi có thể.

### 4.2. Phương thức không được phép

Khi preflight, **HTTP method là OPTIONS**, còn phương thức thật nằm trong `Access-Control-Request-Method`:

~~~http
OPTIONS /api/documents HTTP/1.1
Origin: https://app.example.vn
Access-Control-Request-Method: DELETE
~~~

Với `allowedMethods(GET, POST)`, `DELETE` bị từ chối. Đừng nhầm một test `OPTIONS /api/documents` có status `200` với bằng chứng `DELETE` được phép: phải gửi đúng `Access-Control-Request-Method`.

Cần thêm ca đối chứng `Request-Method: POST` để chứng minh cấu hình thực sự cho phép method dự kiến. Nếu policy thay đổi theo đường dẫn, kiểm tra đúng đường dẫn: `/api/public/**` và `/api/admin/**` có thể có phương thức được phép khác nhau.

### 4.3. Header không được phép

Giả sử policy chỉ cho tên header `Authorization` và `Content-Type`:

~~~http
OPTIONS /api/documents HTTP/1.1
Origin: https://app.example.vn
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,x-admin-override
~~~

`Authorization` hợp lệ nhưng `X-Admin-Override` không hợp lệ. **Không được chấp nhận một phần danh sách**: bộ xử lý phải xác định tất cả header được yêu cầu có được cấp quyền hay không.

Hai lỗi phổ biến khi viết test:

1. Gửi `X-Admin-Override: true` trực tiếp trên OPTIONS rồi quên `Access-Control-Request-Headers`. Bạn chưa mô phỏng đúng việc trình duyệt hỏi quyền gửi header này ở request thật.
2. Kiểm tra tên header có đúng chữ hoa/thường. Tên HTTP header không phân biệt chữ hoa/thường, vì vậy hãy đối chiếu không phân biệt chữ hoa khi test nội dung `Access-Control-Allow-Headers`.

Header mà trình duyệt đưa vào `Access-Control-Request-Headers` là **tên**, không phải giá trị. Không đặt bearer token nguyên văn vào đây.

## 5. Điều gì được phép khẳng định từ kết quả?

| Quan sát trong test | Kết luận phù hợp | Điều chưa được chứng minh |
| --- | --- | --- |
| Preflight `403`, không có `Allow-Origin` | Spring CORS đã từ chối request đang thử | Nguyên nhân chính xác nếu thay đổi nhiều yếu tố cùng lúc |
| Preflight `200` nhưng thiếu `Allow-Headers` cần thiết | Chưa đáp ứng điều kiện cấp quyền của trình duyệt | Không thể coi request thật đã được phép |
| Origin sai nhưng response có `Allow-Origin` đúng origin sai | Chính sách có khả năng quá rộng | Không suy ra endpoint không có xác thực |
| GET thật từ origin đúng trả `401` | Có thể do không xác thực | Không thể kết luận CORS bị cấu hình sai |
| POST thật từ origin đúng trả `403` | Có thể do quyền, CSRF hoặc CORS | Cần test riêng từng nguyên nhân |
| Preflight `200`, POST thật `403` | Preflight được chấp thuận, request thật bị từ chối | Không mâu thuẫn: hai bước có vai trò khác |
| `curl` đọc được body dù Origin sai | Client HTTP có thể đọc phản hồi theo cách riêng | Trình duyệt JavaScript chưa chắc đọc được body |

Khi dùng **bộ xử lý CORS mặc định của Spring**, có thể kiểm tra chính xác `403` cho các negative test. Nếu ứng dụng dùng bộ lọc tùy biến, reverse proxy hoặc gateway khác, hãy định nghĩa lại status theo hợp đồng của hệ thống; tiêu chí quyết định vẫn là **không cấp quyền CORS ngoài policy**.

Không nên chỉ kiểm tra status: ở một số triển khai, HTTP `200` có thể vẫn là preflight **không hợp lệ đối với trình duyệt** nếu thiếu header CORS bắt buộc. Ngược lại, chỉ kiểm tra header vắng mặt chưa chứng minh lý do bị từ chối nằm ở policy thay vì cấu hình test không nạp filter.

## 6. Cấu hình Servlet mẫu để kiểm chứng

Đây là cấu hình Spring Security dành cho ứng dụng Servlet, với một nguồn gốc cấu hình CORS tường minh. Nó bảo vệ `/api/**` và xử lý preflight trước bước yêu cầu đăng nhập.

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
        cors.setAllowedOrigins(List.of("https://app.example.vn"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(
            List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Với `http.cors(...)`, preflight đi qua xử lý CORS thích hợp trước filter xác thực; nó không phải mang session hoặc JWT chỉ để hỏi policy. **`permitAll` cho OPTIONS không tự tạo header `Access-Control-Allow-*`** và không thay thế cấu hình CORS.

Controller thử nghiệm tối giản:

~~~java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
class DocumentsController {

    @GetMapping
    Map<String, String> list(Authentication authentication) {
        return Map.of("viewer", authentication.getName());
    }

    @PostMapping
    ResponseEntity<Void> create() {
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
~~~

Cấu hình giữ CSRF mặc định của Spring Security. Nhờ đó, bạn có thể xác minh POST thật vẫn cần token CSRF trong mô hình session/CSRF này, dù preflight hợp lệ.

## 7. MockMvc: kiểm chứng các trường hợp bị từ chối

Thêm dependency `spring-security-test` vào scope `test`. Với `@SpringBootTest` và `@AutoConfigureMockMvc`, phép thử chạy qua **security filter chain**. Ví dụ giả định các bean ở mục 6 thuộc ứng dụng được tải trong test.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

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
class ServletCorsDeniedTests {

    private static final String ALLOWED = "https://app.example.vn";
    private static final String DENIED = "https://evil.example.vn";

    @Autowired
    MockMvc mvc;

    @Test
    void baselinePreflightHopLe() throws Exception {
        mvc.perform(options("/api/documents")
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
                containsStringIgnoringCase("authorization")));
    }

    @Test
    void tuChoiOriginKhongNamTrongDanhSach() throws Exception {
        mvc.perform(options("/api/documents")
                .header(HttpHeaders.ORIGIN, DENIED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization,content-type"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void tuChoiSaiScheme() throws Exception {
        mvc.perform(options("/api/documents")
                .header(HttpHeaders.ORIGIN, "http://app.example.vn")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void tuChoiHostCoHauToDanhLua() throws Exception {
        mvc.perform(options("/api/documents")
                .header(HttpHeaders.ORIGIN, "https://app.example.vn.evil.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
            .andExpect(status().isForbidden());
    }

    @Test
    void tuChoiOriginNull() throws Exception {
        mvc.perform(options("/api/documents")
                .header(HttpHeaders.ORIGIN, "null")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
            .andExpect(status().isForbidden());
    }

    @Test
    void tuChoiPhuongThucDelete() throws Exception {
        mvc.perform(options("/api/documents")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void tuChoiHeaderLa() throws Exception {
        mvc.perform(options("/api/documents")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "x-admin-override"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void tuChoiNeuDanhSachCoMotHeaderBiCam() throws Exception {
        mvc.perform(options("/api/documents")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization,x-admin-override"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "learner")
    void requestThatTuOriginBiCamCungBiTuChoi() throws Exception {
        mvc.perform(get("/api/documents")
                .header(HttpHeaders.ORIGIN, DENIED))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    @WithMockUser(username = "learner")
    void requestThatOriginHopLeDuocXuLy() throws Exception {
        mvc.perform(get("/api/documents")
                .header(HttpHeaders.ORIGIN, ALLOWED))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED));
    }

    @Test
    void originHopLeNhungChuaDangNhap() throws Exception {
        mvc.perform(get("/api/documents")
                .header(HttpHeaders.ORIGIN, ALLOWED))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED));
    }

    @Test
    @WithMockUser
    void postThatThieuCsrf() throws Exception {
        mvc.perform(post("/api/documents")
                .header(HttpHeaders.ORIGIN, ALLOWED))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser
    void postThatCoCsrf() throws Exception {
        mvc.perform(post("/api/documents")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED));
    }
}
~~~

### 7.1. Vì sao test đối chứng là bắt buộc?

Nếu cả `baselinePreflightHopLe` và test bị cấm đều trả `403`, có thể CORS chưa được bật hoặc policy không được nạp. Một tập kiểm thử chỉ có negative tests sẽ dễ **thành công giả**: hệ thống chặn tất cả chứ không thực sự phân biệt theo allowlist.

Vì vậy, phải có ít nhất một preflight hợp lệ kiểm tra đầy đủ:

- Status thành công.
- `Access-Control-Allow-Origin` khớp chính xác.
- `Access-Control-Allow-Methods` bao gồm phương thức dự kiến.
- `Access-Control-Allow-Headers` bao gồm các tên header yêu cầu.

Trong test `requestThatTuOriginBiCamCungBiTuChoi`, `@WithMockUser` cố ý xác thực trước cho request thật. Bằng cách này, `403` khó bị nhầm với việc người dùng chưa đăng nhập. Test `originHopLeNhungChuaDangNhap` làm đối chứng ngược: origin được phép **không thay thế xác thực**.

### 7.2. Không đưa danh tính giả lên preflight

Để bắt lỗi thứ tự bộ lọc, các test preflight ở trên **không dùng `@WithMockUser` và không gửi bearer token**. Preflight hợp lệ vẫn phải được chấp thuận.

`@WithMockUser` tạo `SecurityContext` phục vụ test, nhưng không kiểm chứng việc nhận token từ mạng. Nếu ứng dụng xác thực bằng JWT/OAuth2/OIDC, có thể dùng các tiện ích `jwt()`, `oauth2Login()`, `oidcLogin()` của `spring-security-test` cho **request thật**, và vẫn cần test CORS riêng. Những tiện ích này giả lập ngữ cảnh bảo mật, không thay thế kiểm chứng chữ ký JWT hoặc luồng đăng nhập thật.

## 8. WebFlux: cấu hình Reactive và kiểm thử WebTestClient

Với WebFlux, sử dụng nguồn cấu hình CORS reactive và tích hợp qua `ServerHttpSecurity`:

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
    SecurityWebFilterChain webFilterChain(
            ServerHttpSecurity http, CorsConfigurationSource cors) {
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

Nếu hệ thống sử dụng `CorsWebFilter` riêng, đặt filter trước security filter và tránh đăng ký hai policy khác nhau trên cùng request. Đối với test này, ví dụ dùng tích hợp của Spring Security WebFlux như ở trên.

Với ứng dụng WebFlux đã tải cấu hình trong ngữ cảnh Spring Boot:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveCorsDeniedTests {

    private static final String ALLOWED = "https://app.example.vn";

    @Autowired
    WebTestClient client;

    @Test
    void preflightDuocPhep() {
        client.options().uri("/api/documents")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization,content-type")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED)
            .expectHeader().exists(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS);
    }

    @Test
    void originLaBiTuChoi() {
        client.options().uri("/api/documents")
            .header(HttpHeaders.ORIGIN, "https://evil.example.vn")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void methodDeleteBiTuChoi() {
        client.options().uri("/api/documents")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE")
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void headerLaBiTuChoi() {
        client.options().uri("/api/documents")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization,x-admin-override")
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void originNullBiTuChoi() {
        client.options().uri("/api/documents")
            .header(HttpHeaders.ORIGIN, "null")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

`WebTestClient` kiểm tra phản hồi server; nó **không đóng vai trình duyệt để tự chặn JavaScript**. Hãy xác nhận rõ `Access-Control-Allow-Origin` bị loại bỏ khi từ chối và xuất hiện khi được phép.

Nếu tiếp tục test request thật với `mockJwt()` hoặc mock security context của WebFlux, phải liên kết test client với Spring Security theo cách phù hợp với loại test. Điều đó phục vụ kiểm thử phân quyền, không thay đổi nguyên tắc từ chối Origin/method/header.

## 9. Ma trận kiểm thử đủ mạnh

Một bảng kiểm thử ngắn có thể dùng để rà soát phạm vi bảo vệ của chính sách:

| Mã ca | Origin | Request-Method | Request-Headers | Kỳ vọng |
| --- | --- | --- | --- | --- |
| OK-01 | `https://app.example.vn` | `POST` | `authorization,content-type` | Preflight được phép |
| OK-02 | `https://app.example.vn` | `GET` | `authorization` | Preflight được phép |
| DENY-O1 | `https://evil.example.vn` | `POST` | `authorization` | Từ chối Origin |
| DENY-O2 | `http://app.example.vn` | `GET` | Không có | Từ chối do scheme |
| DENY-O3 | `https://app.example.vn:8443` | `GET` | Không có | Từ chối do port |
| DENY-O4 | `null` | `GET` | Không có | Từ chối opaque origin |
| DENY-M1 | `https://app.example.vn` | `DELETE` | Không có | Từ chối phương thức |
| DENY-M2 | `https://app.example.vn` | `PATCH` | `content-type` | Từ chối phương thức |
| DENY-H1 | `https://app.example.vn` | `POST` | `x-admin-override` | Từ chối header |
| DENY-H2 | `https://app.example.vn` | `POST` | `authorization,x-admin-override` | Từ chối khi có một header ngoài allowlist |
| ACT-01 | `https://evil.example.vn` | GET thật | Không áp dụng | Actual request CORS bị từ chối theo Spring mặc định |
| AUTH-01 | `https://app.example.vn` | GET thật | Không áp dụng | Không xác thực thì bị security chặn |
| CSRF-01 | `https://app.example.vn` | POST thật | Không áp dụng | Có danh tính, thiếu CSRF → có thể `403` |

Những ca mà policy từ chối cần sử dụng **cùng đường dẫn** và chỉ đổi yếu tố đang xét, tránh nhận một phản hồi `404` hay `405` từ routing rồi tưởng đó là kiểm soát CORS. Với preflight, không kiểm tra liệu controller có được gọi: Spring thường trả lời ngay ở tầng CORS filter.

### 9.1. Những điều không nên gộp vào cùng phép thử

- **Sai origin + sai method + header lạ**: chỉ biết bị từ chối, khó xác định điều kiện nào có tác dụng.
- **Thiếu đăng nhập + origin bị cấm**: status `403` có thể làm bạn gán nhầm nguyên nhân.
- **Không có `Origin`**: request này không đánh giá danh sách origin, nên không thể dùng làm ca negative về CORS.
- **Header `Access-Control-Allow-Origin` vắng mặt**: phải đối chiếu với ca thành công để chứng minh filter CORS thực sự hoạt động.
- **HTTP OPTIONS không có `Access-Control-Request-Method`**: không phải preflight đúng nghĩa; không chứng minh policy chặn POST/DELETE.

## 10. Đối chiếu thực tế với curl và DevTools

Trên môi trường dev, có thể dùng `curl` để tạo các request CORS:

~~~bash
# Đối chứng hợp lệ
curl -i -X OPTIONS 'http://localhost:8080/api/documents' \
  -H 'Origin: https://app.example.vn' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type'

# Nguồn bị cấm
curl -i -X OPTIONS 'http://localhost:8080/api/documents' \
  -H 'Origin: https://evil.example.vn' \
  -H 'Access-Control-Request-Method: POST'

# Phương thức bị cấm
curl -i -X OPTIONS 'http://localhost:8080/api/documents' \
  -H 'Origin: https://app.example.vn' \
  -H 'Access-Control-Request-Method: DELETE'

# Header bị cấm
curl -i -X OPTIONS 'http://localhost:8080/api/documents' \
  -H 'Origin: https://app.example.vn' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,x-admin-override'
~~~

So sánh status và các header `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`. Với đường dẫn này chưa triển khai ở dev, đổi URL cho đúng API nhưng giữ ý tưởng test nguyên vẹn.

**`curl` không thực thi CORS**. Ngay cả khi API trả body cho một HTTP client không thuộc trình duyệt, việc đó không chứng minh trang web khác origin có thể đọc body bằng JavaScript. Để xem hành vi trình duyệt, dùng Network tab: quan sát preflight `OPTIONS`, header yêu cầu và phản hồi, sau đó kiểm tra xem request thật có được gửi hay bị chặn.

| Triệu chứng | Chỗ cần kiểm tra |
| --- | --- |
| Preflight `401` | Security filter có yêu cầu đăng nhập trước khi xử lý CORS không? |
| Preflight `403` dù origin đúng | Method, header, path hoặc policy của gateway có cho phép không? |
| Preflight `200` nhưng trình duyệt vẫn báo lỗi | Có thiếu `Allow-Origin`, `Allow-Methods`, `Allow-Headers` hoặc credential phù hợp không? |
| GET thật `401` dù CORS đúng | Kiểm tra xác thực; không nới chính sách origin để sửa lỗi đăng nhập |
| POST thật `403` dù preflight đúng | Kiểm tra CSRF, authority/role và các rule khác |
| Có origin lạ được chấp thuận | Kiểm tra `allowedOrigins`, `allowedOriginPatterns`, wildcard và policy ở proxy |
| Phản hồi CORS lúc đúng lúc sai qua cache | Kiểm tra `Vary: Origin` và các thành phần `Vary` liên quan đến preflight |

Khi kiểm tra cấu hình qua reverse proxy/CDN, nhớ rằng chính sách CORS ở gateway có thể khác với Spring. Trong test tích hợp tại application context, bạn xác minh quyết định của Spring; muốn khẳng định hành vi production, cần đối chiếu trên đường đi HTTP thật.

## 11. Bài tập áp dụng và tiêu chí hoàn thành

**Tình huống:** Nhóm muốn chỉ frontend `https://app.example.vn` được gọi `GET`/`POST` trên `/api/documents`; chỉ `Authorization` và `Content-Type` là header do chính sách cho phép. Hệ thống dùng Spring Security để bảo vệ tài liệu.

Hãy viết hoặc điều chỉnh bộ test của bạn để đáp ứng tất cả tiêu chí sau:

1. Có **ca đối chứng chấp thuận** preflight đúng origin, method và headers; kiểm tra cả status và những `Access-Control-Allow-*` có liên quan.
2. Có ba test từ chối **độc lập**: origin lạ, phương thức `DELETE`, header `X-Admin-Override`. Mỗi test chỉ thay một điều kiện so với ca hợp lệ.
3. Có test dùng **danh sách hai requested headers**, trong đó chỉ một header được cho phép; kết quả phải từ chối toàn bộ preflight.
4. Có test request thật từ origin sai với danh tính hợp lệ giả lập và test request thật từ origin đúng mà chưa xác thực; giải thích được vì sao các kết quả có thể khác nhau.
5. Có test xác nhận POST thật vẫn cần kiểm soát CSRF/quyền theo cấu hình ứng dụng, bất kể preflight được cho phép.
6. Bộ test dùng **MockMvc** khi chạy Servlet hoặc **WebTestClient** khi chạy Reactive, và đi qua CORS/security filter chain thay vì chỉ gọi trực tiếp controller.

**Điều cần ghi nhớ:** CORS kiểm tra **nguồn gọi, phương thức và tên header** theo chính sách dành cho trình duyệt. Khi bị từ chối, preflight không được cấp quyền; nhưng server vẫn phải bảo vệ request thật bằng xác thực, phân quyền, CSRF hoặc các biện pháp cần thiết của kiến trúc. Kiểm thử Spring Security đáng tin cậy luôn phân biệt kết luận **“nguồn bị CORS từ chối”** với **“người dùng không có quyền”**.
