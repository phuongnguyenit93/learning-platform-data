# CSRF với multipart, tải tệp và thứ tự xử lý MultipartFilter (Spring Security Servlet)

## 1. Bài toán và kết quả cần hiểu

Trong ứng dụng Spring MVC dùng session/cookie, một yêu cầu tải tệp lên thường là **POST multipart/form-data**. Trình duyệt gửi cả dữ liệu tệp lẫn các trường biểu mẫu trong nhiều phần (part), phân cách bởi boundary. Vì POST có thể thay đổi trạng thái máy chủ, Spring Security mặc định yêu cầu CSRF token hợp lệ.

Điểm khó nằm ở **thời điểm đọc các part**. Bộ lọc bảo mật kiểm tra CSRF *trước* khi request đi tới DispatcherServlet, trong khi Spring MVC thường phân tích multipart ở giai đoạn xử lý MVC. Nếu token chỉ nằm trong trường ẩn của multipart body, CsrfFilter có thể chưa lấy được token khi nó cần kiểm tra.

Sau bài này, bạn cần phân biệt được:

- **CSRF token** dùng để chứng minh yêu cầu thay đổi trạng thái đến từ giao diện hợp lệ gắn với phiên người dùng; nó không thay thế xác thực, phân quyền hoặc kiểm tra tệp.
- **MultipartResolver** phân tích multipart body và cung cấp MultipartFile, các tham số biểu mẫu.
- **MultipartFilter** có thể đặt *trước toàn bộ Spring Security filter chain* để phân tích multipart trước khi CsrfFilter đọc trường token.
- Gửi token qua **HTTP header** là lựa chọn khác cho fetch/AJAX: CsrfFilter kiểm tra header mà không cần parse body trước.
- Thứ tự lọc quyết định **rủi ro tài nguyên**: parse multipart trước bảo mật có thể tạo tệp tạm ngay cả đối với yêu cầu chưa được xác thực hoặc bị chặn CSRF.

Phạm vi: **Spring Security trên Servlet stack (Spring MVC, Spring Boot 3.x, Spring Security 6.x, Java 17+)**. WebFlux có pipeline và cơ chế multipart khác; không lấy cách đăng ký Servlet MultipartFilter trong bài này áp dụng trực tiếp cho WebFlux.

## 2. Vì sao multipart có thể dẫn đến 403 CSRF?

Với biểu mẫu thông thường dùng application/x-www-form-urlencoded, container thường cung cấp được các tham số qua HttpServletRequest.getParameter(). Với multipart/form-data, các trường và tệp nằm trong một body có cấu trúc multipart; việc đọc chúng phụ thuộc vào multipart parsing.

Một luồng Servlet điển hình:

~~~text
Trình duyệt
  |
  v
Servlet filter chain
  |
  +--> DelegatingFilterProxy("springSecurityFilterChain")
  |       |
  |       +--> FilterChainProxy
  |               |
  |               +--> SecurityContext, xác thực, ...
  |               +--> CsrfFilter   <--- cần token tại đây
  |
  v
DispatcherServlet
  |
  +--> MultipartResolver / HandlerMapping / Controller
  |
  v
@RequestParam("file") MultipartFile
~~~

Các bộ lọc nội bộ Spring Security chạy **bên trong** servlet filter tên springSecurityFilterChain. Trong cấu hình CSRF mặc định, CsrfFilter bảo vệ các phương thức không an toàn (ví dụ POST, PUT, PATCH, DELETE; GET, HEAD, TRACE và OPTIONS thường không bị CSRF check). Nó lấy token kỳ vọng qua CsrfTokenRepository, rồi lấy token mà client gửi qua CsrfTokenRequestHandler, thường từ header hoặc tham số request.

Nếu request chưa được phân tích multipart, trường ẩn có tên _csrf trong body có thể không xuất hiện như một request parameter tại thời điểm CsrfFilter đọc nó. Kết quả thường là **403 Forbidden**, dù biểu mẫu đã gửi trường ẩn. Không nên giả định mọi servlet container đều tự parse multipart tại thời điểm đó: hành vi phụ thuộc vào đăng ký multipart, resolver và cách ứng dụng được khởi tạo.

Lưu ý: Spring Security 6 có cơ chế deferred CSRF token và mặc định bảo vệ token xuất vào HTML khỏi BREACH bằng giá trị token đã che (masked). Giao diện nên dùng giá trị _csrf mà framework đưa cho view; đừng tự trộn token đã che với token thô từ cookie hoặc tự giải mã token.

## 3. Hai cách bố trí đúng và điểm đánh đổi

| Cách làm | Token được gửi ở đâu? | Multipart được parse khi nào? | Đánh đổi chính |
| --- | --- | --- | --- |
| **A. MultipartFilter trước Spring Security** | Trường ẩn trong multipart body | Trước CsrfFilter và thường trước cả xác thực | Hỗ trợ biểu mẫu HTML thuần; request chưa được duyệt có thể tạo tệp tạm |
| **B. Giữ xử lý multipart sau bảo mật** | Header X-CSRF-TOKEN (hoặc tên từ CsrfToken.headerName) | Sau khi CsrfFilter đã kiểm tra header, thường tại MVC | Giảm nhu cầu parse trước kiểm tra CSRF; cần JavaScript/HTTP client có thể đặt header |
| **Token trong URL** | Query parameter trên POST URL | Không cần parse body để tìm token | Có nguy cơ lộ token trong log, lịch sử, công cụ quan sát, liên kết; nên tránh |

Không có lựa chọn nào biến xác thực, authorization, kiểm tra kích thước, virus scanning hay giới hạn tốc độ thành không cần thiết.

## 4. Cách A: biểu mẫu có token trong multipart body

### 4.1. Đặt MultipartFilter trước springSecurityFilterChain

Thứ tự mong muốn:

~~~text
Client -> MultipartFilter -> springSecurityFilterChain
                              -> CsrfFilter
       -> DispatcherServlet -> Controller
~~~

MultipartFilter bọc request bằng MultipartHttpServletRequest thông qua MultipartResolver. Vì vậy CsrfFilter có thể nhìn thấy tham số _csrf trong multipart body trước khi quyết định cho đi tiếp. Trong ứng dụng Spring Boot, nên đăng ký thứ tự ở **cấp Servlet filter** bằng FilterRegistrationBean.

Ví dụ SecurityConfig.java, trong dự án có spring-boot-starter-web và spring-boot-starter-security:

~~~java
package demo.upload;

import org.springframework.boot.autoconfigure.security.SecurityProperties;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.multipart.support.MultipartFilter;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .formLogin(login -> login.permitAll())
            // Giữ CSRF mặc định đang bật.
            .build();
    }

    @Bean
    FilterRegistrationBean<MultipartFilter> multipartFilterBeforeSecurity() {
        var registration =
            new FilterRegistrationBean<>(new MultipartFilter());
        registration.setName("multipartFilterBeforeSecurity");
        registration.setOrder(SecurityProperties.DEFAULT_FILTER_ORDER - 1);
        return registration;
    }
}
~~~

Trong ví dụ, thứ tự đăng ký MultipartFilter nhỏ hơn (chạy trước) thứ tự đăng ký filter Spring Security mà Spring Boot dùng mặc định. **Luôn kiểm tra thứ tự thực tế** nếu dự án đã thay đổi security filter registration order, dùng nhiều SecurityFilterChain, cấu hình servlet initializer riêng hoặc tự thêm bộ lọc khác. Annotation @Order trên SecurityFilterChain chỉ chọn thứ tự *bên trong* FilterChainProxy; nó không thay cho thứ tự đăng ký servlet filter.

MultipartFilter tìm multipart resolver phù hợp trong root context và có đường fallback tới StandardServletMultipartResolver trong môi trường Servlet hỗ trợ. Để ví dụ chạy, ứng dụng phải có multipart support của Spring MVC/Servlet đã được cấu hình; Spring Boot MVC thường tự cấu hình hỗ trợ này qua spring.servlet.multipart.*. Nếu dự án dùng resolver tùy biến, hãy kiểm tra resolver mà MultipartFilter thực tế sử dụng, thay vì ngầm cho rằng resolver của DispatcherServlet và filter giống nhau.

**Không** coi http.addFilterBefore(..., CsrfFilter.class) là tương đương với đăng ký servlet MultipartFilter trước springSecurityFilterChain. addFilterBefore chỉ sắp xếp filter *bên trong* chuỗi Spring Security và không diễn tả cùng ranh giới xử lý.

### 4.2. Ví dụ endpoint upload

Một controller hoàn chỉnh ở mức minh họa:

~~~java
package demo.upload;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
public class UploadController {

    @GetMapping("/upload")
    public String form() {
        return "upload";
    }

    @PostMapping("/upload")
    public String receive(@RequestParam("file") MultipartFile file,
                          RedirectAttributes flash) {
        if (file.isEmpty()) {
            flash.addFlashAttribute("message", "Bạn chưa chọn tệp.");
        } else {
            flash.addFlashAttribute(
                "message", "Đã nhận " + file.getSize() + " byte.");
        }
        return "redirect:/upload";
    }
}
~~~

Controller chỉ đọc kích thước để minh họa luồng xác thực/CSRF, **không lưu tệp lâu dài**. Khi triển khai lưu thật, cần kiểm tra loại nội dung, giới hạn kích thước, sinh tên lưu trữ an toàn, cô lập thư mục, kiểm soát quyền và quét nội dung theo yêu cầu hệ thống; không tin tên tệp hoặc Content-Type do client gửi.

File src/main/resources/templates/upload.html nếu dự án có spring-boot-starter-thymeleaf:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Tải tệp</title>
</head>
<body>
  <h1>Tải tệp</h1>
  <form action="/upload" method="post" enctype="multipart/form-data">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <input type="file" name="file" required>
    <button type="submit">Gửi</button>
  </form>
  <p th:if="${message}" th:text="${message}"></p>
</body>
</html>
~~~

Giá trị _csrf do Spring Security đưa vào request khi view truy cập CSRF token; Thymeleaf render tên trường và giá trị thực tế phù hợp với request handler. Ví dụ dùng action="/upload" với context path gốc. Nếu dùng th:action của Thymeleaf, Spring MVC có thể tự chèn trường CSRF qua RequestDataValueProcessor; hãy kiểm tra HTML render ra và **không chủ động chèn trùng trường _csrf**. Với ứng dụng đặt dưới context path khác, URL action phải được tạo đúng context path.

Cấu hình giới hạn ví dụ, file application.properties:

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
~~~

Trong dự án Boot 3.x, dùng Java 17+ và các starter Web, Security, Thymeleaf; class @SpringBootApplication nằm trong package demo.upload hoặc package cha để quét SecurityConfig và UploadController. Khi chạy ứng dụng, đăng nhập theo cơ chế form login đã cấu hình rồi truy cập GET /upload. Trang trả về phải có một hidden input mang tên _csrf (hoặc parameterName do framework cung cấp), sau đó POST multipart hợp lệ sẽ được controller xử lý.

### 4.3. Điều thực sự xảy ra khi POST

1. Trình duyệt gửi session cookie, multipart part "file" và hidden field _csrf.
2. MultipartFilter đọc/phân tích body, tạo request wrapper với các part và tham số.
3. CsrfFilter kiểm tra giá trị token gửi vào so với token gắn với phiên/request theo repository và request handler.
4. Nếu token sai hoặc thiếu, trả 403; controller không chạy. Nếu hợp lệ, request tiếp tục qua xác thực/phân quyền và MVC.
5. Controller chỉ được phép xử lý tệp khi vượt qua các kiểm tra trên.

**Đánh đổi rất quan trọng:** bước 2 diễn ra trước khi Spring Security chặn một request không hợp lệ. Tùy implementation/resolver và ngưỡng lưu bộ nhớ, việc parse có thể tạo tệp tạm trên đĩa trước khi CSRF/xác thực hoàn tất. Một người chưa đăng nhập vẫn có thể gửi body để tiêu tốn băng thông, RAM, CPU hoặc dung lượng tạm, dù không thể làm controller lưu tệp thành công. Cần giới hạn request size ở reverse proxy/container, quota và rate limit, quản lý thư mục tạm và theo dõi tài nguyên. Các giới hạn multipart tại ứng dụng chỉ là một lớp bảo vệ.

## 5. Cách B: gửi CSRF token bằng header, giữ multipart sau bảo mật

Nếu giao diện sử dụng fetch/AJAX, client có thể gửi token bằng header thay vì phụ thuộc vào việc CsrfFilter đọc tham số trong multipart body. Khi đó **không cần thêm MultipartFilter trước Spring Security chỉ để đọc CSRF token**. Để Spring MVC/DispatcherServlet xử lý multipart sau kiểm tra bảo mật theo cấu hình thông thường.

Luồng:

~~~text
Client (multipart body + X-CSRF-TOKEN header)
  -> springSecurityFilterChain
       -> CsrfFilter đọc header, đối chiếu token
  -> DispatcherServlet / MultipartResolver
  -> Controller nhận MultipartFile
~~~

Ví dụ view Thymeleaf đặt token trong meta tag, và gửi FormData từ JavaScript:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="_csrf" th:content="${_csrf.token}">
  <meta name="_csrf_header" th:content="${_csrf.headerName}">
</head>
<body>
  <form id="uploadForm" action="/upload"
        method="post" enctype="multipart/form-data">
    <input type="file" name="file" required>
    <button type="submit">Tải lên</button>
  </form>
  <p id="result"></p>
  <script>
    const form = document.getElementById("uploadForm");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const token = document.querySelector('meta[name="_csrf"]').content;
      const header = document.querySelector('meta[name="_csrf_header"]').content;

      const response = await fetch(form.action, {
        method: "POST",
        credentials: "same-origin",
        headers: { [header]: token },
        body: new FormData(form)
      });

      document.getElementById("result").textContent =
        response.ok ? "Yêu cầu đã được chấp nhận." :
                      "Yêu cầu thất bại: HTTP " + response.status;
    });
  </script>
</body>
</html>
~~~

Giữ cấu hình SecurityFilterChain và controller tương tự ở trên, nhưng **bỏ bean đăng ký MultipartFilter chạy trước Security** nếu chọn cách B. Có thể dùng headerName do CsrfToken cung cấp, không nhất thiết hard-code X-CSRF-TOKEN. Không tự đặt Content-Type: multipart/form-data khi dùng FormData; trình duyệt phải tự bổ sung boundary chính xác. Header này thường phải được gửi cùng cookie phiên cho yêu cầu cùng origin.

Lưu ý với SPA hoặc cơ chế token lưu cookie: Spring Security 6 có khác biệt giữa token được che để render HTML và token đọc trực tiếp từ cookie. Không mặc định lấy một giá trị cookie rồi áp dụng handler mặc định như thể mọi kiểu token đều giống nhau; phải cấu hình CsrfTokenRepository và CsrfTokenRequestHandler theo hướng dẫn của đúng phiên bản, nhất là khi dùng CookieCsrfTokenRepository.

Với **form HTML thuần gửi trực tiếp** (không có JavaScript đặt header), cách B không đáp ứng được vì HTML form không tự tạo custom header; chọn cách A hoặc thiết kế lại luồng request. Truyền _csrf trên query string của URL POST là một giải pháp kỹ thuật có thể được xử lý sớm nhưng thường không nên dùng vì URL dễ xuất hiện trong log và hệ thống theo dõi.

## 6. Phân biệt các tầng trách nhiệm

| Thành phần | Vai trò | Điều không nên suy luận |
| --- | --- | --- |
| Servlet MultipartConfig / container | Cho phép Servlet xử lý các part của request | Không quyết định CSRF token có hợp lệ |
| MultipartResolver | Biến multipart request thành part/MultipartFile | Không thay xác thực hoặc authorization |
| MultipartFilter | Kích hoạt multipart parsing sớm tại cấp Servlet filter | Không có nghĩa body được bảo vệ trước khi parse |
| DelegatingFilterProxy / FilterChainProxy | Cầu nối tới chuỗi Spring Security | Thứ tự servlet filter khác thứ tự security filter nội bộ |
| CsrfFilter | Xác nhận token cho các request cần bảo vệ | Không quét virus hoặc kiểm tra nội dung tệp |
| AuthorizationFilter | Kiểm tra quyền truy cập endpoint | Không thay CSRF đối với xác thực dùng cookie |
| DispatcherServlet / Controller | Map multipart và chạy logic upload | Không nên xử lý tệp nếu request đã bị từ chối ở lớp trước |

Một POST upload có thể trả **401/redirect tới login** nếu chưa xác thực, **403** nếu CSRF sai hoặc thiếu, **403** do phân quyền, **413**/lỗi multipart khi vượt kích thước, hoặc **400** vì thiếu part "file". Các trạng thái phụ thuộc cấu hình và thứ tự filter; chỉ nhìn 403 không đủ để kết luận nguyên nhân.

## 7. Kiểm thử CSRF và thứ tự filter

Ví dụ kiểm thử logic bảo vệ endpoint bằng MockMvc với spring-security-test và spring-boot-starter-test:

~~~java
package demo.upload;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UploadCsrfTest {

    @Autowired
    MockMvc mvc;

    private MockMultipartFile sampleFile() {
        return new MockMultipartFile(
            "file", "demo.txt", "text/plain",
            "hello".getBytes(StandardCharsets.UTF_8));
    }

    @Test
    void missingCsrfIsRejected() throws Exception {
        mvc.perform(multipart("/upload")
                .file(sampleFile())
                .with(user("alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfCanReachController() throws Exception {
        mvc.perform(multipart("/upload")
                .file(sampleFile())
                .with(user("alice"))
                .with(csrf()))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

Test thứ nhất xác nhận yêu cầu authenticated nhưng thiếu token bị chặn. Test thứ hai xác nhận token hợp lệ đi tới controller và nhận response redirect. **Giới hạn của MockMvc:** MockMvc đã tạo request multipart giả lập và đưa dữ liệu part vào test request; nó **không chứng minh thứ tự filter thực tế của servlet container**. Cần kiểm tra bổ sung bằng cách chạy ứng dụng trên embedded Tomcat/Jetty, xem filter registration order và thử upload qua HTTP thật.

Checklist thử trên môi trường tích hợp:

1. GET /upload sau đăng nhập trả trang có token hợp lệ; xem HTML đã render để kiểm tra field _csrf hoặc meta CSRF, không chỉ nhìn source template.
2. POST multipart cùng session với token đúng tới controller và có kết quả dự kiến.
3. POST multipart cùng session nhưng bỏ/sửa token bị từ chối; controller không được chạy.
4. Với cách A, xác minh MultipartFilter đứng **trước** springSecurityFilterChain trong servlet filter registrations; quan sát việc parse body xảy ra trước bảo mật.
5. Với cách B, xác minh CSRF header xuất hiện trước khi request tới controller; không có đăng ký MultipartFilter sớm không cần thiết.
6. Thử tệp vượt max-file-size và max-request-size; ghi nhận loại lỗi thực tế, không gộp nhầm vào chẩn đoán CSRF.
7. Quan sát vùng lưu tạm/băng thông khi gửi request không xác thực hoặc token sai; đảm bảo giới hạn tài nguyên hoạt động.

Trong khi chẩn đoán, có thể bật log DEBUG của org.springframework.security ở môi trường phát triển để biết request bị chặn ở đâu, nhưng **không ghi hoặc chia sẻ nguyên giá trị session cookie và CSRF token** trong log hay ảnh chụp.

## 8. Các lỗi phổ biến và cách sửa

**Lỗi 1: Có hidden _csrf trong HTML nhưng POST luôn 403.** Xác minh trường thực sự xuất hiện trong request gửi đi, token thuộc đúng phiên, request có cookie phù hợp và nó đã được parse/đọc tại thời điểm CsrfFilter chạy. Nếu là token trong multipart body, kiểm tra filter order; nếu là header, kiểm tra đúng tên header và giá trị token đã render.

**Lỗi 2: Đăng ký MultipartFilter sau Spring Security.** Lúc CsrfFilter kiểm tra, multipart wrapper chưa tồn tại. Đặt thứ tự ở servlet registration, trước springSecurityFilterChain; không nhầm thứ tự của SecurityFilterChain hoặc một HttpSecurity.addFilterBefore với thứ tự servlet filter.

**Lỗi 3: Thêm MultipartFilter trước bảo mật để sửa 403 nhưng bỏ qua nguy cơ tệp tạm.** Request bị từ chối vẫn có thể bị parse và tiêu tốn tài nguyên. Giới hạn kích thước tại proxy/container, quota, thư mục tạm, tốc độ và số request đồng thời; cân nhắc chuyển sang header token khi client có JavaScript.

**Lỗi 4: Tắt CSRF cho /upload để request chạy.** csrf.disable() hoặc csrf.ignoringRequestMatchers("/upload") có thể khiến endpoint dùng session cookie trở thành mục tiêu CSRF. Không dùng cách này chỉ để che đi lỗi thứ tự parse. Chỉ thay đổi chính sách CSRF khi đã đánh giá đúng mô hình xác thực và rủi ro request.

**Lỗi 5: Gửi FormData nhưng tự đặt Content-Type.** Nếu JavaScript chỉ gán multipart/form-data mà thiếu boundary tương ứng, server có thể không parse được các part. Để fetch tự đặt Content-Type khi body là FormData.

**Lỗi 6: Nhầm tên trường hoặc cấu hình kích thước.** name="file" trên biểu mẫu phải tương ứng với @RequestParam("file"); lỗi part missing hoặc vượt kích thước không phải bằng chứng CsrfFilter sai. Token và part cũng là hai dữ liệu khác nhau.

**Lỗi 7: Tin vào file.getOriginalFilename().** Giá trị này do client điều khiển. Không dùng làm đường dẫn lưu, không suy ra file an toàn từ extension/MIME type, không cho phép path traversal; kiểm tra thực tế và dùng tên server sinh.

**Lỗi 8: Trộn CSRF với CORS hoặc chỉ kiểm tra Origin.** CORS kiểm soát quyền đọc/gửi một số request từ browser qua origin khác; nó không tự thay thế cơ chế CSRF cho các thao tác nhạy cảm dùng cookie. Các cơ chế SameSite, Origin/Referer validation và CSRF token có thể bổ trợ nhau.

## 9. Quy tắc lựa chọn và ghi nhớ

- Với **form HTML POST multipart gửi trực tiếp** và token trong body: cần đảm bảo tham số token sẵn sàng trước CsrfFilter, điển hình là đăng ký MultipartFilter trước Spring Security; đánh giá chặt rủi ro parse/upload tạm trước xác thực.
- Với **fetch hoặc client có thể đặt header**: ưu tiên gửi token qua header, để CSRF được xác minh trước khi Spring MVC cần parse multipart; tránh multipart filter sớm chỉ vì yêu cầu đọc token.
- Với upload thật: sau khi qua CSRF và authentication/authorization, controller vẫn phải giới hạn và xác thực nội dung, lưu tệp an toàn, dọn tài nguyên và giám sát lạm dụng.
- Một request **403** cần truy ngược đầy đủ: CSRF token, session, vị trí multipart parsing, xác thực và phân quyền. Chỉ sửa đúng tầng gây lỗi.

Điểm cốt lõi: **đặt MultipartFilter trước springSecurityFilterChain làm token trong multipart body sẵn sàng sớm, nhưng cũng cho phép body được parse trước kiểm tra bảo mật**. Gửi token bằng header tránh sự phụ thuộc đó khi client có khả năng đặt header; mỗi thiết kế phải đi kèm kiểm soát tải lên và tài nguyên phù hợp.
