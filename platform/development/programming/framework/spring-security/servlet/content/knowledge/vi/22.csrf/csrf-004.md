# HttpSessionCsrfTokenRepository và CSRF token gắn với phiên (Spring Security Servlet)

## 1. CSRF cần bảo vệ điều gì?

CSRF (Cross-Site Request Forgery) xảy ra khi kẻ tấn công dụ trình duyệt của người đã đăng nhập gửi một yêu cầu thay đổi trạng thái đến ứng dụng. Ví dụ, nạn nhân đang có phiên đăng nhập với website ngân hàng; trang độc hại cố gửi POST chuyển tiền. Tùy quy tắc cookie của trình duyệt (đặc biệt SameSite), cookie phiên có thể tự đi kèm yêu cầu. Nếu máy chủ chỉ kiểm tra cookie xác thực, nó có thể tưởng đây là ý định thật của nạn nhân.

Một **CSRF token** bí mật, khó đoán, được máy chủ phát cho trang hợp lệ và yêu cầu gửi lại khi thực hiện thao tác nguy hiểm. Kẻ tấn công ở origin khác có thể kích hoạt một số yêu cầu trình duyệt, nhưng thông thường không đọc được token trong nội dung trang/JSON cùng origin vì Same-Origin Policy và CORS đúng. Token vì thế là bằng chứng bổ sung rằng thao tác xuất phát từ giao diện hợp lệ.

Trong mô hình có HTTP session:

- **Session cookie** (thường là JSESSIONID) mang định danh để máy chủ tìm phiên; trình duyệt có thể tự đính kèm nó.
- **CSRF token** là một giá trị riêng lưu phía máy chủ **trong HttpSession**, đồng thời được cung cấp cho giao diện cùng origin.
- Khi gửi POST/PUT/PATCH/DELETE, giao diện phải gửi cả cookie phiên và token (tham số form hoặc header). Giá trị gửi lên phải khớp với token phía máy chủ của **đúng phiên đó**.
- CSRF token **không phải session ID**, không mã hóa session ID, không thay thế xác thực hoặc phân quyền. Một người có thể chưa đăng nhập nhưng vẫn có session và CSRF token (ví dụ biểu mẫu đăng nhập).

## 2. HttpSessionCsrfTokenRepository làm gì?

**org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository** là triển khai **CsrfTokenRepository** dành cho ứng dụng Spring Security **Servlet**. Ba phương thức nền tảng là:

| Phương thức | Ý nghĩa |
| --- | --- |
| **generateToken(HttpServletRequest)** | Tạo token ngẫu nhiên khó dự đoán, trả về đối tượng CsrfToken. |
| **saveToken(CsrfToken, request, response)** | Lưu token vào thuộc tính của HttpSession; truyền null để xóa token đã lưu. |
| **loadToken(HttpServletRequest)** | Đọc token từ HttpSession hiện có; trả null nếu không có session/token. |

Tên tham số form mặc định là **_csrf**, tên header mặc định là **X-CSRF-TOKEN**; các tên này có thể đổi qua **setParameterName** và **setHeaderName**. Giá trị token tồn tại ở server-side session; trình duyệt chỉ nhận token khi server chủ động đưa nó vào HTML hoặc một phản hồi cho phép.

**Điểm quan trọng về tạo session:** ở Spring Security 6, việc nạp CSRF token thường được trì hoãn (deferred). Một GET không thực sự dùng token có thể không sinh/lưu token và không tạo session chỉ vì CSRF được bật. Khi trang gọi **getToken()** để hiển thị token chưa có, token mới được tạo, lưu vào HttpSession và có thể khiến một session mới được tạo. Sau đó các yêu cầu dùng lại session đó sẽ đọc lại token đã lưu.

Spring Security Servlet thông thường đã bật CSRF và dùng repository gắn với HttpSession theo mặc định; khai báo repository tường minh sẽ làm cơ chế dễ thấy khi học. Không nhầm repository này với **CookieCsrfTokenRepository** (lưu token trong cookie) hoặc giải pháp CSRF của WebFlux.

## 3. Luồng xử lý của CsrfFilter

~~~text
Trình duyệt GET /csrf hoặc GET trang biểu mẫu
    └─ CsrfFilter chuẩn bị token deferred từ HttpSessionCsrfTokenRepository
       └─ Khi trang đọc token: tạo/lưu nếu chưa có, rồi trả token ra response
          └─ Trình duyệt giữ session cookie và token hiển thị cho ứng dụng

Trình duyệt POST /payments + session cookie + _csrf hoặc X-CSRF-TOKEN
    └─ CsrfFilter lấy token kỳ vọng theo session từ repository
       └─ CsrfTokenRequestHandler lấy giá trị token client gửi
          ├─ Khớp: tiếp tục chuỗi filter đến controller
          └─ Thiếu/sai/khác session: từ chối, thường HTTP 403
~~~

Mặc định CSRF được áp dụng cho các HTTP method có khả năng thay đổi dữ liệu, ví dụ **POST, PUT, PATCH, DELETE**; các phương thức **GET, HEAD, TRACE, OPTIONS** được xem là an toàn và không bắt buộc token. Vì vậy ứng dụng tuyệt đối không dùng GET để ghi/xóa/chuyển tiền. Một endpoint được **permitAll()** vẫn phải qua kiểm tra CSRF nếu nó nhận một method được bảo vệ: phân quyền và CSRF là hai kiểm tra khác nhau.

Thứ tự ở mức ý tưởng: **repository** giữ token kỳ vọng; **request handler** trình bày/đọc token trong request; **CsrfFilter** so sánh và quyết định tiếp tục hay chặn. Repository tự nó không phải nơi thực thi 403.

## 4. Ví dụ chạy được với Java 17, Spring Boot 3.4.5 và Spring Security Servlet

Tạo cấu trúc Maven:

~~~text
session-csrf-demo/
├── pom.xml
└── src/
    ├── main/java/demo/csrf/SessionCsrfApplication.java
    └── test/java/demo/csrf/SessionCsrfApplicationTests.java
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
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>session-csrf-demo</artifactId>
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

**src/main/java/demo/csrf/SessionCsrfApplication.java**:

~~~java
package demo.csrf;

import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SessionCsrfApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionCsrfApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
                .csrf(csrf -> csrf.csrfTokenRepository(
                        new HttpSessionCsrfTokenRepository()))
                .build();
    }

    @GetMapping("/csrf")
    ResponseEntity<Map<String, String>> csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken)
                request.getAttribute(CsrfToken.class.getName());
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                        "headerName", token.getHeaderName(),
                        "parameterName", token.getParameterName(),
                        "token", token.getToken()));
    }

    @PostMapping("/payments")
    Map<String, String> payments(@RequestParam String reference) {
        return Map.of("status", "accepted", "reference", reference);
    }
}
~~~

Ở demo này, **permitAll()** giúp thử CSRF mà không cần đăng nhập; ứng dụng thực tế vẫn phải áp dụng xác thực, phân quyền và kiểm tra nghiệp vụ. **GET /csrf** đọc thuộc tính token do Spring Security gắn vào request. Lệnh **token.getToken()** khiến token deferred được materialize khi cần, và **Cache-Control: no-store** hạn chế cache lưu phản hồi nhạy cảm. Endpoint POST chỉ giả lập chấp nhận một mã tham chiếu, không thực hiện thanh toán thật.

### Chạy thử với PowerShell

Khởi động trong thư mục dự án bằng **mvn spring-boot:run**. Trong một cửa sổ PowerShell khác:

~~~powershell
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$csrf = Invoke-RestMethod -Uri 'http://localhost:8080/csrf' -WebSession $session

# Thiếu token: POST bị từ chối
try {
    Invoke-RestMethod -Uri 'http://localhost:8080/payments' -Method Post -WebSession $session -Body @{ reference = 'INV-001' } | Out-Null
} catch {
    [int]$_.Exception.Response.StatusCode
}

# Cùng cookie phiên, kèm token đã nhận: POST được chấp nhận
$headers = @{}
$headers[$csrf.headerName] = $csrf.token
$ok = Invoke-RestMethod -Uri 'http://localhost:8080/payments' -Method Post -WebSession $session -Headers $headers -Body @{ reference = 'INV-001' }
$ok.status
$ok.reference
~~~

Kết quả quan sát mong đợi:

~~~text
403
accepted
INV-001
~~~

**WebRequestSession** giữ cookie giữa các lệnh; biến **$csrf** giữ token do cùng phiên nhận được. Nếu tạo **WebRequestSession** khác rồi gửi token của phiên trước, POST phải bị từ chối (thường 403). Thử bỏ cookie dù vẫn có token cũng không tạo ra quyền truy cập vào phiên gốc.

### Kiểm thử tự động bằng MockMvc

**src/test/java/demo/csrf/SessionCsrfApplicationTests.java**:

~~~java
package demo.csrf;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class SessionCsrfApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void postWithoutTokenIsForbidden() throws Exception {
        mvc.perform(post("/payments").param("reference", "INV-001"))
                .andExpect(status().isForbidden());
    }

    @Test
    void postWithValidTokenSucceeds() throws Exception {
        mvc.perform(post("/payments")
                        .with(csrf())
                        .param("reference", "INV-001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("accepted"))
                .andExpect(jsonPath("$.reference").value("INV-001"));
    }
}
~~~

Chạy **mvn test**. Hàm **with(csrf())** của spring-security-test dựng token hợp lệ cho request kiểm thử; nó giúp xác nhận nhánh chấp nhận/từ chối của filter, nhưng **không thay thế** bài kiểm tra tích hợp cookie thật, session timeout, login/logout hay nhiều instance máy chủ.

## 5. Gắn token vào form HTML và yêu cầu AJAX

Với Spring MVC và Thymeleaf (cần bổ sung **spring-boot-starter-thymeleaf**), một form có xử lý qua Thymeleaf có thể viết:

~~~html
<form th:action="@{/payments}" method="post">
    <label>Mã tham chiếu <input name="reference" required></label>
    <button type="submit">Gửi</button>
</form>
~~~

Khi Spring Security và Spring MVC tích hợp **RequestDataValueProcessor**, Thymeleaf có thể tự thêm hidden input mang tên **_csrf** cho form POST. Kiểm tra HTML sau render: hidden field phải có giá trị token thực từ **request/session**, không phải chuỗi cố định viết tay. Với form HTML thuần hoặc framework tự render, lập trình viên phải đưa token ra form đúng cách.

Với JavaScript gửi yêu cầu thay đổi dữ liệu, gửi token nhận được từ backend cùng session cookie, ví dụ **X-CSRF-TOKEN** trong header. Trình duyệt phải giữ đúng session cookie khi fetch/XHR gửi đến backend; với yêu cầu cross-origin hợp lệ, chính sách **credentials**, CORS và SameSite phải được thiết kế nhất quán. **Không** mở CORS quá rộng trên endpoint phát token và không gắn token vào query string, URL hay log ứng dụng.

### Raw token, masked token và BREACH trong Spring Security 6

Đây là điểm dễ nhầm: **HttpSessionCsrfTokenRepository** lưu **raw token** trong session, còn **CsrfTokenRequestHandler** quyết định token được đưa ra request và được đọc lại như thế nào. Với cấu hình Servlet hiện đại, handler mặc định thường là **XorCsrfTokenRequestAttributeHandler**: nó xuất token đã che bằng XOR với yếu tố ngẫu nhiên để giảm nguy cơ BREACH khi token được phản ánh trong response có nén. Hai lần lấy token trên HTML/response có thể thấy **chuỗi token khác nhau dù cùng một raw token trong session**; đó không nhất thiết là session đã thay đổi.

Trong demo, dùng đúng **token.getToken()** được Spring Security cung cấp từ request; đây là giá trị trình bày phù hợp với handler mặc định. Đừng tự đọc raw token từ HttpSession rồi giả định mọi request handler đều nhận raw token ở mọi vị trí. Nếu xây dựng SPA theo cơ chế cookie/token đọc được bằng JavaScript, cần thiết kế **CsrfTokenRequestHandler** phù hợp cho header raw, đồng thời bảo đảm bước tải lại token sau xác thực/đăng xuất. Không nên đổi sang **CookieCsrfTokenRepository.withHttpOnlyFalse()** chỉ để né sự khác biệt raw/masked mà chưa đánh giá mô hình bảo mật.

## 6. Vòng đời token và phiên

| Tình huống | Hệ quả cần hiểu |
| --- | --- |
| Chưa có session, request chưa đọc token | Có thể chưa phát sinh token/session do deferred loading. |
| Trang/form đọc token lần đầu | Token được tạo và lưu vào HttpSession; có thể tạo session mới. |
| Nhiều request trong cùng session | Repository dùng lại raw token đã lưu; token trình bày có thể khác vì cơ chế mask. |
| Token phiên A gửi cùng cookie phiên B | Không khớp token dự kiến của B; thao tác bị từ chối. |
| Session hết hạn/bị hủy | Token gắn session cũ không còn; client phải lấy token mới từ phiên hợp lệ. |
| Đăng nhập hoặc đăng xuất | Các chiến lược CSRF tiêu chuẩn như CsrfAuthenticationStrategy và CsrfLogoutHandler xóa token cũ; giao diện phải nhận token mới sau chuyển trạng thái. |
| Đổi session ID để chống session fixation | Đổi ID session và xoay CSRF token là hai cơ chế độc lập; không suy đoán chỉ từ giá trị JSESSIONID. |

**Token gắn với phiên**, tức giá trị kỳ vọng được lưu theo phiên. Điều đó **không** đồng nghĩa token được gắn mật mã vào địa chỉ IP, User-Agent, một account hay từng HTTP request. Repository mặc định cũng không tự đặt thời hạn token riêng: thời gian hiệu lực thực tế chịu ảnh hưởng bởi vòng đời session và các hành động xóa/đổi token.

Trong hệ thống nhiều replica, các yêu cầu phải thấy **cùng dữ liệu HttpSession** (ví dụ session affinity hoặc Spring Session với kho chung). Nếu request GET lấy token ở node A nhưng POST tới node B không đọc được cùng session, người dùng có thể nhận 403 dù header đúng.

## 7. Khi nào dùng repository này và khi nào không?

**Phù hợp:** ứng dụng web Servlet có đăng nhập bằng session/cookie, form MVC hoặc giao diện web gửi request với session cookie. Mô hình bảo vệ tự nhiên: token là dữ liệu server-side, không cần cookie CSRF riêng.

**Cần xem xét khác:** API thực sự stateless, client xác thực bằng Authorization header tự thêm cho từng request và không dựa vào thông tin xác thực tự động từ trình duyệt. Khi đó phân tích nguy cơ CSRF từ cơ chế xác thực cụ thể trước khi quyết định. Nếu backend vẫn dùng cookie để xác thực thì vẫn phải xem xét CSRF, kể cả khi UI là SPA hoặc API trả JSON. Đặt **SessionCreationPolicy.STATELESS** trong khi kỳ vọng token lưu qua **HttpSessionCsrfTokenRepository** thường làm mô hình không nhất quán; chọn chiến lược session/token tương thích.

**CookieCsrfTokenRepository** lưu token trong cookie thay vì server-side session. Điều này thay đổi cách front-end đọc token và yêu cầu xử lý raw/masked; không nên xem hai repository là tương đương chỉ vì cả hai đều hỗ trợ tên header CSRF.

## 8. Chẩn đoán lỗi 403 và lỗi thiết kế thường gặp

1. **POST thiếu token**: xác nhận form có hidden **_csrf** hoặc AJAX có header **X-CSRF-TOKEN**.
2. **Token đúng nhưng sai phiên**: kiểm tra cookie phiên có đi cùng cả request lấy token và request POST; session mới hoặc timeout làm token cũ hết giá trị.
3. **POST ngay sau login/logout bị 403**: token có thể đã được xóa theo chiến lược xác thực/đăng xuất; lấy token mới trước thao tác tiếp theo.
4. **Header có token nhưng vẫn sai**: kiểm tra tên header/tham số, repository cấu hình thực tế và cách request handler xử lý raw/masked token.
5. **Thỉnh thoảng 403 khi chạy nhiều node**: kiểm tra lưu trữ/định tuyến HttpSession và độ nhất quán của session store.
6. **Tắt CSRF để sửa 403**: trước hết xác định nguyên nhân. Với ứng dụng dựa vào session cookie, vô hiệu hóa CSRF thường xóa bỏ một lớp phòng vệ cần thiết.
7. **Để GET thay đổi dữ liệu hoặc chỉ dựa vào SameSite**: GET phải giữ ngữ nghĩa an toàn; SameSite, Origin/Referer check có thể tăng phòng vệ nhưng không mặc nhiên thay thế token.
8. **Lộ token qua XSS, URL, log, CDN cache hoặc CORS sai**: CSRF token không chống được JavaScript độc hại chạy cùng origin. Dùng HTTPS, phòng XSS, cấu hình cookie Secure/HttpOnly/SameSite thích hợp, và không cache nội dung gắn với phiên ở shared cache.

## 9. Tự kiểm tra hiểu bài

- Vì sao kẻ tấn công có thể khiến trình duyệt gửi cookie phiên nhưng khó gửi đúng CSRF token? Hãy liên hệ Same-Origin Policy và việc token nằm trong response của origin hợp lệ.
- Nếu hai response GET xuất token khác nhau, có đủ bằng chứng rằng HttpSession đã đổi không? **Không**: kiểm tra sự khác biệt raw token và token được XOR-mask.
- Vì sao một POST đến endpoint **permitAll()** vẫn có thể nhận 403? Vì CSRF được kiểm tra độc lập với quy tắc phân quyền.
- Vì sao sau khi session hết hạn không thể tiếp tục dùng token trước đó? Vì token kỳ vọng nằm trong HttpSession cũ, không còn được repository tải ra cho phiên mới.
- Khi nào một triển khai không cần session có thể xem xét chiến lược CSRF khác? Khi mô hình xác thực và cách trình duyệt tự gửi thông tin đăng nhập đã được xác định rõ, không chỉ dựa vào nhãn “REST API”.

**Ghi nhớ:** HttpSessionCsrfTokenRepository chịu trách nhiệm **tạo, lưu và nạp raw CSRF token theo HttpSession**. CsrfFilter cùng CsrfTokenRequestHandler chịu trách nhiệm **lấy token client gửi, đối chiếu và chặn request không hợp lệ**. Hiểu rõ session cookie, deferred token, masking và vòng đời login/logout giúp cấu hình đúng và chẩn đoán 403 mà không phải tắt CSRF.
