# CsrfFilter và các HTTP method cần kiểm tra CSRF token

## 1. Vấn đề cần giải quyết

Trong một ứng dụng Spring Security chạy trên **Servlet stack**, người dùng có thể đăng nhập bằng phiên (session); trình duyệt tự đính kèm cookie phiên vào các yêu cầu phù hợp. Kẻ tấn công có thể dụ người dùng đang đăng nhập truy cập trang khác và từ đó gửi yêu cầu thay đổi dữ liệu tới ứng dụng. Nếu máy chủ chỉ dựa vào cookie phiên, yêu cầu giả mạo có thể được xử lý bằng quyền của nạn nhân. Đây là **Cross-Site Request Forgery (CSRF)**.

Ví dụ: người dùng đang đăng nhập vào một trang quản lý tài khoản. Trang độc hại gửi biểu mẫu POST tới chức năng đổi địa chỉ giao hàng. Trình duyệt có thể gửi kèm cookie đăng nhập tùy chính sách cookie/SameSite; máy chủ thấy phiên hợp lệ nhưng không chứng minh được yêu cầu bắt nguồn từ giao diện đáng tin cậy. **CSRF token** bổ sung bằng chứng mà trang của kẻ tấn công thông thường không thể đọc được từ cùng phiên do giới hạn same-origin.

Ba câu hỏi trọng tâm của bài:

1. **CsrfFilter** thực hiện kiểm tra ở đâu trong luồng yêu cầu Servlet?
2. Những **HTTP method** nào mặc định phải mang token, và vì sao GET khác POST, PUT, PATCH, DELETE?
3. Cách lấy, gửi, kiểm thử token mà không tắt bảo vệ CSRF chỉ để một API hoạt động?

CSRF là cơ chế bảo vệ yêu cầu thay đổi trạng thái khi trình duyệt **tự động gửi thông tin xác thực** như cookie phiên. Nó không thay thế đăng nhập, phân quyền, kiểm tra dữ liệu hay biện pháp chống XSS.

## 2. CsrfFilter làm việc như thế nào?

**CsrfFilter** nằm trong chuỗi filter do Spring Security thiết lập cho ứng dụng Servlet. Nó xử lý yêu cầu **trước khi đến controller**, sử dụng những thành phần chính sau:

- **CsrfTokenRepository**: lưu, tải hoặc sinh token; cấu hình mặc định thông dụng là **HttpSessionCsrfTokenRepository**, lưu token phía máy chủ trong HTTP session.
- **CsrfTokenRequestHandler**: đưa token vào request để giao diện có thể sử dụng và xác định token do client gửi lên; các bản Spring Security 6 dùng cơ chế mặc định có xử lý che token (XOR) nhằm hạn chế lộ token qua cơ chế nén phản hồi/BREACH.
- **RequestMatcher** dành cho bảo vệ CSRF: quyết định một yêu cầu có phải **xác minh** token hay không. Mặc định lựa chọn này dựa trên HTTP method.
- **AccessDeniedHandler**: từ chối yêu cầu thuộc diện bảo vệ nếu token thiếu hoặc sai; thông thường nhận được **HTTP 403 Forbidden**.

Luồng rút gọn:

~~~text
HTTP request
    |
    v
SecurityFilterChain (Servlet)
    |
    v
CsrfFilter: nạp nguồn token, thiết lập request handler
    |
    +-- Method được miễn kiểm tra (GET/HEAD/OPTIONS/TRACE mặc định)
    |       |
    |       +--> Cho qua bước xác minh CSRF --> các filter/controller tiếp theo
    |
    +-- Method cần kiểm tra (ví dụ POST/PUT/PATCH/DELETE)
            |
            +--> Lấy token hợp lệ từ repository
            +--> Đọc token client gửi (header hoặc parameter)
            |
            +-- Trùng khớp? -- Có --> Tiếp tục chuỗi filter
                         |
                         +-- Không --> 403; controller không xử lý thao tác
~~~

**Điểm dễ nhầm:** CsrfFilter có thể được gọi cho GET; điều được miễn là **bước yêu cầu token để cho phép request đi tiếp**. GET vẫn có thể được dùng để **cấp/đưa token cho client**. Trạng thái HTTP cuối cùng còn phụ thuộc các filter khác, định tuyến và phân quyền; “được miễn CSRF” không đồng nghĩa với “luôn được trả 200”.

Token từ repository gắn với ngữ cảnh người dùng/phiên, còn token do client trình lên là bằng chứng phải đối chiếu. Trong cấu hình session, gửi lại cùng cookie phiên khi dùng token là điều thiết yếu: token của phiên A không hợp lệ cho phiên B.

## 3. Mặc định method nào cần token?

Spring Security Servlet dùng matcher mặc định của CsrfFilter: **không yêu cầu kiểm tra CSRF đối với GET, HEAD, TRACE, OPTIONS; mọi method khác đều thuộc diện kiểm tra** nếu request đang đi qua security chain có bật CSRF và không được cấu hình ngoại lệ.

| HTTP method | Kiểm tra CSRF theo mặc định? | Ý nghĩa |
| --- | --- | --- |
| **GET** | Không | Lấy biểu diễn dữ liệu, không được gây thay đổi trạng thái có ý nghĩa nghiệp vụ. |
| **HEAD** | Không | Tương tự GET nhưng không có response body. |
| **OPTIONS** | Không | Truy vấn tùy chọn máy chủ, thường dùng trong CORS preflight. |
| **TRACE** | Không | Nằm trong nhóm method được matcher mặc định loại trừ; nhiều máy chủ vô hiệu hóa TRACE vì lý do bảo mật khác. |
| **POST** | **Có** | Thường tạo dữ liệu, gửi form hoặc thực hiện hành động. |
| **PUT** | **Có** | Ghi hoặc thay thế tài nguyên; dù có tính idempotent theo HTTP vẫn không phải safe method. |
| **PATCH** | **Có** | Cập nhật một phần tài nguyên. |
| **DELETE** | **Có** | Xóa tài nguyên; idempotent không đồng nghĩa với miễn CSRF. |
| **Method khác**, ví dụ CONNECT hoặc method mở rộng | **Có** | Vì không thuộc bốn method được miễn mặc định. |

Hãy phân biệt hai tính chất HTTP:

- **Safe**: theo hợp đồng HTTP, request không nhằm thay đổi trạng thái do người dùng yêu cầu. GET/HEAD/OPTIONS/TRACE được xem là safe; hệ thống phải thiết kế GET đọc dữ liệu và không dùng GET cho xóa, thanh toán hoặc đổi mật khẩu.
- **Idempotent**: lặp lại cùng request có tác động dự kiến như một lần. PUT và DELETE có thể idempotent **nhưng vẫn là unsafe** và vẫn cần CSRF token trong cấu hình mặc định.

Không nên gắn kết luận “DELETE an toàn vì idempotent” hay “POST không cần token vì endpoint cho phép anonymous”. **CSRF và authorization là hai cơ chế độc lập**: một endpoint `permitAll()` vẫn có thể bị CsrfFilter trả 403 khi thiếu token.

Matcher có thể được tùy biến bằng `csrf().requireCsrfProtectionMatcher(...)` hoặc bổ sung ngoại lệ bằng `ignoringRequestMatchers(...)`; khi đó bảng trên mô tả **mặc định**, không phải luật bất biến của mọi ứng dụng.

## 4. Token đến từ đâu và được gửi bằng cách nào?

Với cấu hình mặc định phổ biến **HttpSessionCsrfTokenRepository**:

1. Server cấp/đọc CSRF token cho HTTP session. Spring Security 6 hỗ trợ **deferred token**: chỉ thực sự tải/sinh khi cần.
2. Ở request đọc hoặc trang biểu mẫu, ứng dụng đưa token hợp lệ vào HTML hoặc trả token từ endpoint cùng origin.
3. Khi gửi request thuộc diện bảo vệ, client gửi **cookie phiên** cùng **token** lấy từ phiên đó.
4. CsrfFilter so sánh token client gửi với token trong repository; thiếu, sai, hết hiệu lực hoặc thuộc phiên khác thì bị từ chối.

Tên mặc định trong repository session:

- **Form parameter**: `_csrf` (phù hợp biểu mẫu HTML).
- **Header**: `X-CSRF-TOKEN` (phù hợp fetch/AJAX).
- **Request attribute** do handler cung cấp: thường truy cập qua `CsrfToken.class.getName()` hoặc `_csrf`; handler mặc định của Spring Security 6 có thể trả **giá trị đã che (masked token)** để đưa ra trang.

**Đừng tự bóc/biến đổi giá trị token lấy từ request attribute trước khi gửi lại.** Với ví dụ dưới đây, client dùng trực tiếp giá trị do endpoint `/csrf` trả và Spring Security xử lý phía server.

Một cấu hình khác là **CookieCsrfTokenRepository**, thường có cookie tên `XSRF-TOKEN` và header `X-XSRF-TOKEN`. Với SPA, việc cho JavaScript đọc cookie (ví dụ `withHttpOnlyFalse()`) phải được đánh giá cẩn thận. Trên Spring Security 6, token gửi theo kiểu SPA từ cookie không nhất thiết giống token XOR được render vào response; tùy cấu hình cần **request handler hỗ trợ SPA** để giải mã/tiếp nhận đúng và tải token khi cần. Không nên đổi repository rồi mặc định cho rằng frontend cũ sẽ hoạt động.

Session cookie, CSRF token, access token và JWT là các khái niệm khác nhau. Nếu API xác thực **chỉ** qua header Authorization do client chủ động gắn và không dùng cookie hay thông tin tự gửi của trình duyệt, rủi ro CSRF có thể khác đáng kể. Nếu JWT lại được giữ trong cookie tự gửi, vấn đề CSRF vẫn hiện hữu.

## 5. Ví dụ chạy được: GET không cần token, POST phải có token

Mẫu này dùng **Java 17**, **Spring Boot 3.3.5**, Spring Security Servlet. Nó cố ý để mọi URL `permitAll()` nhằm quan sát riêng hành vi CSRF, không phải cấu hình phân quyền dành cho production. Cấu trúc:

~~~text
csrf-method-demo/
  pom.xml
  src/main/java/example/csrf/CsrfDemoApplication.java
  src/test/java/example/csrf/CsrfDemoApplicationTests.java
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
    <artifactId>csrf-method-demo</artifactId>
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

**src/main/java/example/csrf/CsrfDemoApplication.java**:

~~~java
package example.csrf;

import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CsrfDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CsrfDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
                .csrf(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class DemoController {

        @GetMapping("/csrf")
        Map<String, String> csrf(HttpServletRequest request) {
            CsrfToken token = (CsrfToken) request.getAttribute(CsrfToken.class.getName());
            return Map.of("token", token.getToken());
        }

        @GetMapping("/api/messages")
        Map<String, String> read() {
            return Map.of("message", "read permitted");
        }

        @PostMapping("/api/messages")
        Map<String, String> write(@RequestBody Map<String, String> body) {
            return Map.of("saved", body.getOrDefault("message", ""));
        }
    }
}
~~~

Dòng `.csrf(Customizer.withDefaults())` nêu rõ rằng bài đang giữ bảo vệ CSRF mặc định. Endpoint GET `/csrf` đọc token từ request attribute, gọi `getToken()` để sinh/tải token khi cần; với session repository, bước này cho client một token liên kết với cookie phiên. Trên Spring Security 6, giá trị nhận được có thể là token đã che và **có thể khác giữa các lần GET**; đó không nhất thiết là lỗi.

Chạy trong thư mục dự án có Maven và JDK 17+:

~~~bash
mvn spring-boot:run
~~~

Mở terminal thứ hai (các lệnh sau dùng Bash/Git Bash; cần `curl` và Python 3 để đọc JSON):

~~~bash
# 1) GET: không đòi CSRF token.
curl -i http://localhost:8080/api/messages

# 2) POST: không gửi token -> 403.
curl -i -H 'Content-Type: application/json' \
  -d '{"message":"hello"}' \
  http://localhost:8080/api/messages

# 3) GET token; lưu cookie phiên do server cấp.
TOKEN=$(curl -fsS -c csrf-cookies.txt http://localhost:8080/csrf \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

# 4) POST cùng cookie và token -> 200.
curl -i -b csrf-cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"message":"hello"}' \
  http://localhost:8080/api/messages
~~~

Kết quả dự kiến, với ứng dụng mẫu chạy đúng và không có filter/cấu hình khác: bước 1 là **200 OK** kèm JSON `{"message":"read permitted"}`; bước 2 là **403 Forbidden** (body lỗi tùy cấu hình); bước 4 là **200 OK** kèm `{"saved":"hello"}`. Token ở bước 3 được đọc từ JSON thực tế, không hard-code. Đổi cookie, dùng token sai hoặc bỏ header ở bước 4 sẽ làm xác minh thất bại.

Frontend cùng origin có thể thực hiện tương tự:

~~~javascript
const tokenResponse = await fetch("/csrf", { credentials: "same-origin" });
if (!tokenResponse.ok) throw new Error("Cannot obtain CSRF token");
const { token } = await tokenResponse.json();

const result = await fetch("/api/messages", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": token
  },
  body: JSON.stringify({ message: "hello" })
});
if (!result.ok) throw new Error("Request failed: " + result.status);
console.log(await result.json());
~~~

Bên trong trình duyệt, mã cần được chạy từ origin hợp lệ của ứng dụng; JavaScript của trang độc hại thông thường không thể tự do đọc phản hồi token từ origin khác. Tránh cấu hình CORS cho phép đọc token từ nguồn không tin cậy kèm credentials.

## 6. Kiểm thử hành vi CsrfFilter bằng MockMvc

Tệp **src/test/java/example/csrf/CsrfDemoApplicationTests.java**:

~~~java
package example.csrf;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void getWithoutTokenIsAllowed() throws Exception {
        mvc.perform(get("/api/messages"))
                .andExpect(status().isOk());
    }

    @Test
    void postWithoutTokenIsRejected() throws Exception {
        mvc.perform(post("/api/messages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"hello\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void postWithValidTokenIsAllowed() throws Exception {
        mvc.perform(post("/api/messages").with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"hello\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.saved").value("hello"));
    }
}
~~~

Chạy `mvn test`. `csrf()` là **test request post-processor** do `spring-security-test` cung cấp: nó thêm token hợp lệ để kiểm thử chức năng đi qua filter, không phải cách client production tự sinh token. Có thể dùng `with(csrf().useInvalidToken())` để xác minh đường đi 403 với token không hợp lệ.

Các test cho **POST** chứng minh cả hai nhánh của CsrfFilter; bảng method ở mục 3 giải thích matcher mặc định. Nếu viết endpoint thật cho PUT/PATCH/DELETE, nên có các test thiếu/có token tương ứng. Không kết luận việc miễn CSRF chỉ từ response 404/405 của method chưa có handler.

## 7. Khi nào chỉnh phạm vi bảo vệ?

Một vài hệ thống có nhiều loại endpoint trong cùng ứng dụng:

| Tình huống | Cách đánh giá |
| --- | --- |
| Web dùng session/form login, cookie phiên gửi tự động | **Giữ CSRF** cho method thay đổi dữ liệu. |
| SPA cùng origin dùng cookie phiên | Giữ CSRF; cấp token và chuyển trong header đúng theo request handler đang dùng. |
| REST API thật sự không dùng cookie/thông tin xác thực tự gửi, chỉ Bearer token qua Authorization header do ứng dụng gắn | Đánh giá threat model để quyết định bảo vệ, dựa trên cách client lưu và gửi credential thực tế. |
| Webhook máy-máy từ nhà cung cấp, không dựa vào browser session | Có thể loại trừ **đúng đường dẫn webhook**, đồng thời kiểm tra chữ ký/HMAC/secret theo giao thức nhà cung cấp. |
| Endpoint POST cho khách chưa đăng nhập | Vẫn có thể bị CSRF kiểm tra; anonymous/`permitAll()` không tự miễn CSRF. |

Ví dụ **đoạn cấu hình bên trong SecurityFilterChain đang xây dựng**, không phải chương trình Java độc lập:

~~~java
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/webhooks/provider/**")
);
~~~

Đoạn trên chỉ nhằm minh họa ngoại lệ có phạm vi. Nó không xác thực webhook và không nên được sao chép nếu chưa có cơ chế xác thực nguồn gọi. Tránh cấu hình `csrf.disable()` cho cả ứng dụng chỉ vì POST từ Postman/curl bị 403. Khi có nhiều `SecurityFilterChain`, hãy kiểm tra **chain nào thật sự match URL**, vì CsrfFilter và matcher trong từng chain có thể khác nhau.

**Chú ý với login và logout:** nếu bật CSRF, các POST đăng nhập và đăng xuất cũng có thể phải gửi token. Trong cấu hình Spring Security có bật CSRF, logout mặc định thường dùng POST. Khi xác thực thành công/đăng xuất, token cũ có thể bị xóa hoặc cần tải mới; SPA giữ token quá lâu có thể nhận 403 sau thay đổi phiên. Với template engine như Thymeleaf kết hợp Spring MVC/Spring Security, form có thể được tự chèn trường CSRF; với fetch thủ công, lập trình viên cần gửi header/parameter tương ứng.

## 8. Chẩn đoán khi gặp 403 và lỗi thiết kế thường thấy

1. **POST/PUT/PATCH/DELETE trả 403, GET trả 200:** trước tiên kiểm tra có CSRF filter và thiếu/sai token hay không; sau đó kiểm tra authorization. Một mã 403 không tự chứng minh chỉ có CSRF gây lỗi.
2. **Đã gửi token nhưng vẫn 403:** xem client có giữ **cùng session cookie** khi lấy và gửi token không; kiểm tra đúng tên header/parameter, token có bị HTML escaping, thay đổi phiên hoặc bị gửi từ repository/request handler khác.
3. **Dùng `X-XSRF-TOKEN` nhưng server chờ `X-CSRF-TOKEN`:** xác định repository, request handler và quy ước phía frontend. Tên thường gặp của CookieCsrfTokenRepository không tự áp dụng cho HttpSessionCsrfTokenRepository.
4. **GET làm thay đổi dữ liệu:** đây là lỗi thiết kế nghiêm trọng. Đổi thao tác ghi sang method phù hợp và yêu cầu token; không “chữa” bằng cách bắt mọi GET có CSRF token.
5. **Dựa vào CORS hoặc SameSite như biện pháp duy nhất:** CORS chủ yếu kiểm soát việc đọc phản hồi và một số request của JavaScript; biểu mẫu HTML vẫn có những đường gửi cross-site. SameSite hỗ trợ giảm rủi ro nhưng cần xét cross-site/same-site, subdomain, browser và luồng đăng nhập; nó là lớp bổ sung, không phải bằng chứng rằng CsrfFilter không cần thiết.
6. **API dùng JWT thì tắt CSRF ngay:** cần hỏi JWT nằm trong Authorization header được client chủ động gắn hay nằm trong cookie được browser tự gửi. Vị trí và cơ chế truyền mới quyết định threat model.
7. **Giải quyết 403 bằng `permitAll()`:** quy tắc authorization không bỏ qua CSRF. Nếu endpoint thực sự cần miễn, đánh giá cơ chế xác thực của nó và dùng matcher ngoại lệ hẹp.
8. **Không thấy token sau GET:** với deferred token, token chỉ tải/sinh khi được truy cập. Render token bằng form hoặc endpoint `/csrf` phù hợp; đừng giả định mọi GET luôn tạo session.
9. **Đã có header token nhưng không có cookie:** nếu token lưu trong session, thiếu cookie phiên tương ứng sẽ làm token không khớp. Khi thử với curl/Postman, nhớ mang cả cookie jar.
10. **TRACE được liệt kê là miễn CSRF nên mở TRACE:** sai. Bảo vệ CSRF và chính sách cho phép HTTP method là hai quyết định độc lập; TRACE thường bị chặn ở server/proxy.

Để debug, bật log phù hợp cho Spring Security ở môi trường phát triển, theo dõi **method, URL, chain được chọn, status, tên header/parameter, cookie/session có hiện diện**. Không ghi nguyên token, cookie phiên hoặc credential vào log production.

## 9. Ghi nhớ đúng bản chất

- **CsrfFilter** chặn trước controller khi request cần token nhưng thiếu/sai token; request an toàn vẫn đi qua filter và có thể lấy token.
- Theo matcher mặc định, **GET, HEAD, TRACE, OPTIONS không cần xác minh CSRF**; **POST, PUT, PATCH, DELETE và method còn lại cần xác minh** nếu CSRF đang áp dụng cho request đó.
- **Safe khác idempotent**: PUT/DELETE không được miễn vì có thể idempotent.
- **Token và cookie phải cùng ngữ cảnh phiên**; session repository thường nhận `_csrf` hoặc `X-CSRF-TOKEN`. Với SPA dùng cookie repository, xử lý token theo đúng cơ chế của Spring Security 6.
- Khi một request 403, xác định chain, matcher, repository, handler, token và cookie thực tế trước khi quyết định điều chỉnh cấu hình.
