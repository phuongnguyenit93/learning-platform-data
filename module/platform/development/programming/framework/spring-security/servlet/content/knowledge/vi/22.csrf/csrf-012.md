# Giới hạn ngoại lệ CSRF bằng ignoringRequestMatchers và đánh giá trước khi disable

## 1. Vấn đề cần giải quyết

Trong Spring Security trên nền **Servlet** (Spring MVC, Spring Boot 3.x và Spring Security 6.x), CSRF (Cross-Site Request Forgery) là nguy cơ khi trình duyệt tự gửi thông tin xác thực như session cookie theo một yêu cầu do trang khác khởi tạo. Ví dụ, người dùng vẫn đăng nhập vào ứng dụng ngân hàng; một trang độc hại khiến trình duyệt của họ gửi POST chuyển tiền. Máy chủ có thể nhận cookie phiên hợp lệ dù người dùng không hề chủ ý chuyển tiền.

Spring Security mặc định bảo vệ các phương thức có khả năng thay đổi trạng thái (như POST, PUT, PATCH, DELETE) bằng CSRF token; các phương thức được xem là an toàn (GET, HEAD, TRACE, OPTIONS) thường không cần token. Nếu một yêu cầu phải được bảo vệ mà không có token hợp lệ, **CsrfFilter trả HTTP 403** trước khi xử lý nghiệp vụ. Nguyên tắc quan trọng: GET không được thực hiện thay đổi trạng thái.

Một số endpoint, điển hình là webhook từ hệ thống bên ngoài, không sử dụng trình duyệt/session cookie nên không có CSRF token để gửi. Khi có lý do rõ ràng, hãy **bỏ qua kiểm tra CSRF cho đúng request cần thiết** bằng **csrf.ignoringRequestMatchers(...)**, trong khi vẫn giữ cơ chế phòng vệ cho những request khác. Không nên tắt CSRF trên toàn bộ filter chain chỉ để chữa một lỗi 403 ở một endpoint.

Mục tiêu sau bài học:
- Phân biệt một endpoint thực sự không cần CSRF với endpoint chỉ đang thiếu cách gửi token.
- Viết ngoại lệ hẹp theo **đường dẫn và HTTP method**.
- Hiểu rằng miễn kiểm tra CSRF không đồng nghĩa bỏ xác thực, phân quyền hoặc xác minh chữ ký webhook.
- Kiểm chứng ngoại lệ và phần bảo vệ còn lại bằng bài kiểm thử HTTP.

## 2. Cơ chế và ranh giới bảo vệ

Với Servlet SecurityFilterChain, Spring Security xác định request nào cần kiểm tra CSRF. Khi dùng **ignoringRequestMatchers**, request khớp matcher sẽ được loại khỏi tập request phải kiểm tra token; những request còn lại vẫn tuân theo chính sách CSRF. Matcher là điều kiện chọn request chứ không phải một danh sách quyền truy cập.

Phân biệt ba cấu hình thường bị nhầm:

| Cấu hình | Mục đích | Kết quả |
| --- | --- | --- |
| **csrf.ignoringRequestMatchers(matcher)** | Miễn CSRF cho request khớp matcher | CSRF vẫn bật ở các request khác |
| **authorizeHttpRequests(...requestMatchers(...).permitAll())** | Cho phép truy cập endpoint mà không cần đăng nhập | **Không** tự miễn CSRF: POST vẫn có thể nhận 403 |
| **csrf.disable()** | Vô hiệu hóa CSRF cho toàn bộ SecurityFilterChain tương ứng | Mọi request trong chain mất lớp kiểm tra CSRF |

Do đó, chỉ thêm **permitAll()** không khắc phục POST thiếu token. Ngược lại, chỉ thêm **ignoringRequestMatchers** không khiến endpoint được truy cập nếu quy tắc xác thực/phân quyền vẫn từ chối.

### CSRF có còn cần cho REST API không?

Tên gọi “REST” không quyết định rủi ro; **cách phía client xác thực** mới quan trọng:

| Luồng sử dụng | Đánh giá CSRF |
| --- | --- |
| Web MVC có login/session cookie | Giữ CSRF; form/JavaScript phải gửi token |
| SPA gọi API bằng cookie đăng nhập | Thường vẫn cần CSRF, kể cả khi phản hồi là JSON |
| API dùng bearer token chỉ được client chủ động gắn trong header Authorization, không chấp nhận cookie làm thông tin xác thực | Có thể không cần CSRF cho luồng ấy sau khi xác minh toàn bộ cơ chế xác thực |
| JWT lưu trong cookie và được trình duyệt tự gửi | **Vẫn có nguy cơ CSRF**; việc dùng JWT không tự giải quyết vấn đề |
| Webhook server-to-server dùng chữ ký HMAC, không dựa vào session/cookie trình duyệt | Có thể miễn CSRF cho endpoint cụ thể, nhưng bắt buộc xác minh chữ ký/yêu cầu theo giao thức đối tác |

CORS không phải cơ chế thay thế CSRF: việc trình duyệt bị chặn đọc phản hồi cross-origin không bảo đảm máy chủ không nhận được request làm thay đổi dữ liệu. Cookie SameSite, kiểm tra Origin/Referer và giới hạn Content-Type có ích như các lớp phòng vệ bổ sung, nhưng không nên được dùng làm lý do tùy tiện vô hiệu hóa CSRF. HTTP Basic cũng cần cân nhắc vì trình duyệt có thể tự gửi lại thông tin xác thực đã ghi nhớ.

## 3. Cấu hình ngoại lệ có giới hạn

Giả sử ứng dụng có:
- **POST /account/notification**: thao tác của người dùng đã đăng nhập bằng session; phải có CSRF token.
- **POST /webhooks/provider**: callback từ đối tác, xác thực bằng HMAC trên raw body; không có CSRF token.

Ví dụ dưới đây hoạt động trong ứng dụng Spring Boot 3.x / Spring Security 6.x với Java 17+. Dùng một **RequestMatcher** xét cả method và đường dẫn chính xác để tránh miễn nhầm POST khác hoặc các phương thức khác trên cùng URL. Với ứng dụng có DispatcherServlet ở mapping mặc định, **getServletPath()** là đường dẫn request không bao gồm context path.

Thêm các dependency sau vào khối **dependencies** của dự án Gradle Spring Boot đã được cấu hình:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
implementation 'org.springframework.boot:spring-boot-starter-security'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.security:spring-security-test'
~~~

Tệp **src/main/java/com/example/csrf/CsrfExampleApplication.java**:

~~~java
package com.example.csrf;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RequestMatcher;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CsrfExampleApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfExampleApplication.class, args);
    }
}

@Configuration
class WebSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        RequestMatcher providerWebhookPost = request ->
                "POST".equals(request.getMethod())
                && "/webhooks/provider".equals(request.getServletPath())
                && request.getPathInfo() == null;

        return http
                .csrf(csrf -> csrf.ignoringRequestMatchers(providerWebhookPost))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.POST, "/webhooks/provider").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}

@RestController
class DemoController {
    private final byte[] webhookSecret;

    DemoController(@Value("${example.webhook-secret}") String secret) {
        this.webhookSecret = secret.getBytes(StandardCharsets.UTF_8);
    }

    @PostMapping("/account/notification")
    String updateNotification() {
        return "updated";
    }

    @PostMapping("/webhooks/provider")
    ResponseEntity<String> providerWebhook(
            @RequestBody byte[] rawBody,
            @RequestHeader(value = "X-Signature", required = false) String signature) {
        if (!validHmac(rawBody, signature)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body("bad signature");
        }
        return ResponseEntity.ok("accepted");
    }

    private boolean validHmac(byte[] rawBody, String signature) {
        if (signature == null || !signature.matches("[0-9a-fA-F]{64}")) {
            return false;
        }
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(webhookSecret, "HmacSHA256"));
            byte[] expected = mac.doFinal(rawBody);
            byte[] provided = HexFormat.of().parseHex(signature);
            return MessageDigest.isEqual(expected, provided);
        } catch (GeneralSecurityException ex) {
            return false;
        }
    }
}
~~~

Ở cấu hình này:
1. **providerWebhookPost** chỉ khớp một yêu cầu POST có servlet path chính xác **/webhooks/provider**. POST đến **/webhooks/provider/extra**, hoặc PUT đến **/webhooks/provider**, vẫn chịu CSRF.
2. **ignoringRequestMatchers(providerWebhookPost)** miễn kiểm tra CSRF đúng cho callback nói trên. Nó không tắt toàn bộ CsrfFilter.
3. **permitAll()** cho phép đối tác không có phiên đăng nhập tới controller, nhưng controller tự yêu cầu và kiểm tra chữ ký HMAC. Chữ ký được tính trên **raw bytes** của request body và so sánh bằng **MessageDigest.isEqual**.
4. **/account/notification** cần đăng nhập qua form login và phải gửi token CSRF khi POST.

**Giới hạn an toàn của demo:** Header **X-Signature** với HMAC-SHA256 là giao thức minh họa, không phải chuẩn chung cho mọi nhà cung cấp. Trong hệ thống thật phải tuân thủ đúng định dạng signature/timestamp của đối tác, dùng secret lấy từ kho secret hoặc biến môi trường, xác minh giới hạn thời gian, chống replay, idempotency và các quy tắc xác thực khác. Không dùng giá trị secret của bài kiểm thử cho production. Nếu ứng dụng có context path, servlet mapping đặc biệt hoặc nhiều SecurityFilterChain, kiểm thử lại matcher và thứ tự chain theo cấu hình thực tế.

## 4. Kiểm thử chính sách: chỉ một endpoint được miễn

Tệp **src/test/java/com/example/csrf/CsrfPolicyTest.java**:

~~~java
package com.example.csrf;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = "example.webhook-secret=test-secret")
@AutoConfigureMockMvc
class CsrfPolicyTest {
    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser
    void accountPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/account/notification"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser
    void accountPostWithCsrfSucceeds() throws Exception {
        mvc.perform(post("/account/notification").with(csrf()))
                .andExpect(status().isOk());
    }

    @Test
    void webhookWithoutValidSignatureIsUnauthorized() throws Exception {
        mvc.perform(post("/webhooks/provider")
                        .content("payload")
                        .header("X-Signature", "invalid"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void webhookWithValidSignatureDoesNotNeedCsrf() throws Exception {
        byte[] body = "payload".getBytes(StandardCharsets.UTF_8);
        mvc.perform(post("/webhooks/provider")
                        .content(body)
                        .header("X-Signature", signatureFor(body)))
                .andExpect(status().isOk());
    }

    @Test
    void differentPathIsStillProtected() throws Exception {
        mvc.perform(post("/webhooks/provider/extra"))
                .andExpect(status().isForbidden());
    }

    @Test
    void differentUnsafeMethodIsStillProtected() throws Exception {
        mvc.perform(put("/webhooks/provider"))
                .andExpect(status().isForbidden());
    }

    private static String signatureFor(byte[] body) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(
                "test-secret".getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        return HexFormat.of().formatHex(mac.doFinal(body));
    }
}
~~~

Chạy tại thư mục dự án có Gradle wrapper:

~~~bash
./gradlew test --tests com.example.csrf.CsrfPolicyTest
~~~

Trên Windows có thể dùng **gradlew.bat** thay cho **./gradlew**. Sáu trường hợp có kết quả HTTP mong đợi lần lượt là **403, 200, 401, 200, 403, 403**. Hai kiểm thử cuối xác nhận phạm vi ngoại lệ không lan sang URL gần giống hoặc method khác; chúng vẫn bị CsrfFilter từ chối trước bước tìm controller tương ứng. Bài test dùng **@WithMockUser** chỉ để mô phỏng người dùng đã xác thực, không thay thế CSRF token; **with(csrf())** tạo token hợp lệ cho MockMvc.

Nếu muốn quan sát request thật bằng curl hoặc Postman, cần cấu hình **example.webhook-secret** từ môi trường (ví dụ **EXAMPLE_WEBHOOK_SECRET**) và tạo signature đúng trên byte body. Lưu ý curl/Postman không tự tạo mối đe dọa CSRF: bài kiểm thử nhằm chứng minh chính sách phía server, còn rủi ro thực tế bắt nguồn từ trình duyệt tự gửi credential.

## 5. Đánh giá trước khi cân nhắc disable

Đừng sửa ngay thành **csrf.disable()** chỉ vì một POST trả 403. Hãy đi theo thứ tự sau:

1. **Xác định request và kết quả thực tế.** Ghi rõ method, path, filter chain được chọn, dạng credential, status, log và xem request có bị thiếu/không hợp lệ CSRF token hay không. 403 cũng có thể đến từ quy tắc authorization; đừng mặc định mọi 403 đều do CSRF.
2. **Phân loại client.** Request có thể đến từ browser đang mang session/cookie hoặc HTTP Basic tự gửi? Nếu có, ưu tiên giữ CSRF và gửi token đúng cách. HTML form cần hidden input token; với JavaScript SPA, thiết lập cách cấp/đọc/gửi token phù hợp Spring Security 6 và chính sách cookie của ứng dụng.
3. **Tìm lý do kỹ thuật để miễn.** Endpoint có thực sự chỉ nhận kết nối server-to-server, không dựa vào credential tự gửi của trình duyệt, và đã có xác thực độc lập (signature/mTLS/tiêu chuẩn tương đương)? Nếu chưa, không tạo ngoại lệ chỉ vì đối tác hoặc frontend đang thiếu token.
4. **Thu hẹp matcher.** Chọn path cụ thể, method, servlet mapping và chain thích hợp; tránh mẫu rộng kiểu **/api/** hoặc **/** khi chỉ một callback cần miễn. Nếu dùng nhiều SecurityFilterChain, xem xét **securityMatcher** và thứ tự **@Order** vì cấu hình CSRF chỉ tác động trong chain được chọn.
5. **Định nghĩa quyền truy cập độc lập.** Xác thực và phân quyền vẫn cần áp dụng; webhook public về mặt session phải có xác thực thông điệp. Cần thêm rate limit, audit, chống replay và idempotency tùy rủi ro, không coi việc bỏ CSRF là biện pháp xác minh nguồn gửi.
6. **Viết kiểm thử âm và dương.** Request miễn CSRF có thể đi đến bước xác thực nghiệp vụ mà không cần token; request tương tự nhưng khác path/method vẫn bị chặn; tác vụ browser vẫn bị 403 khi thiếu token và thành công khi có token. Kiểm tra lại khi mở route mới hoặc thay đổi chain.
7. **Chỉ cân nhắc disable ở cấp chain sau khi chứng minh toàn bộ chain không cần CSRF.** Ví dụ một chain API thực sự stateless chỉ chấp nhận bearer token trong Authorization header, không xác thực bằng cookie/session/Basic tự động từ browser, và đã được kiểm thử. Nếu cùng chain còn form login, logout, trang quản trị hoặc API dựa trên cookie, tắt global sẽ làm mất bảo vệ của chúng.

### Các lỗi thường gặp

- **“API trả JSON nên không cần CSRF.”** Sai khi trình duyệt xác thực bằng cookie.
- **“Đã permitAll nên POST sẽ không đòi token.”** Sai vì authorization và CSRF là hai quyết định riêng.
- **“Webhook không có token, vậy disable toàn bộ.”** Mở rộng ngoại lệ không cần thiết sang chức năng đăng nhập, cấu hình tài khoản và các POST khác.
- **“Đã dùng JWT nên miễn CSRF.”** Không đúng nếu JWT nằm trong cookie được tự gửi.
- **“ignoringRequestMatchers bảo vệ webhook.”** Sai: nó chỉ bỏ một kiểm tra; xác minh chữ ký và quyền truy cập vẫn phải triển khai.
- **“Dùng /** sẽ tiện cho mọi callback.”** Matcher quá rộng có thể vô hiệu hóa CSRF cho các route được thêm về sau.
- **“GET có thể sửa dữ liệu vì GET không yêu cầu token.”** Sai về thiết kế HTTP; phải chuyển thao tác thay đổi trạng thái sang phương thức phù hợp.

## 6. Tiêu chí hoàn thành

Một ngoại lệ CSRF tốt có thể được giải thích bằng một câu: **request nào được miễn, vì sao không cần token CSRF, cơ chế nào xác thực nó, và những request nào vẫn được bảo vệ**. Với ví dụ trên, chỉ **POST /webhooks/provider** được miễn CSRF và chữ ký HMAC vẫn là điều kiện nghiệp vụ; **POST /account/notification** tiếp tục yêu cầu đăng nhập và CSRF token. Khi không thể chứng minh ranh giới ấy, giữ CSRF và xử lý cách client lấy/gửi token là lựa chọn an toàn hơn.
