# Document request và response cookies

## Mục tiêu bài học

HTTP cookie là dữ liệu nhỏ mà server gửi cho client qua header **Set-Cookie**; ở những request tiếp theo, client có thể gửi lại cookie qua header **Cookie**. API có thể dùng cookie để duy trì phiên đăng nhập, ghi nhớ lựa chọn giao diện hoặc xác định ngôn ngữ. Khi tài liệu hóa API bằng **Spring REST Docs**, cần mô tả rõ cookie nào client phải gửi và cookie nào server có thể trả về.

Bài học thuộc module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn tài liệu Asciidoctor/Markdown rồi tích hợp vào build và CI.

Sau bài học này, bạn có thể:

- Phân biệt cookie trong request với cookie trong response.
- Dùng **requestCookies(...)**, **responseCookies(...)** và **cookieWithName(...)** của Spring REST Docs.
- Gửi cookie bằng MockMvc và xác nhận cookie server tạo ra.
- Sinh snippet **request-cookies.adoc** và **response-cookies.adoc**.
- Phân biệt mô tả cookie với mô tả header **Cookie/Set-Cookie**.
- Tài liệu hóa cookie tùy chọn và xử lý trường hợp thiếu cookie.
- Bảo vệ session ID, token và dữ liệu nhạy cảm trong test fixture và tài liệu.
- Nhúng snippet cookies vào Asciidoctor và chạy quy trình sinh tài liệu trong CI.

## 1. Cookie đi qua HTTP như thế nào?

Cookie có hai chiều trao đổi:

1. Server gửi cookie cho client bằng header **Set-Cookie** trong response.
2. Client lưu cookie theo quy tắc của trình duyệt hoặc HTTP client. Ở request phù hợp sau đó, client gửi tên và giá trị cookie trong header **Cookie**.

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: display-mode=compact; Path=/; HttpOnly; Secure; SameSite=Lax
Content-Type: application/json

{"message":"Preferences saved"}
~~~

Request tiếp theo:

~~~http
GET /api/profile
Cookie: display-mode=compact; locale=vi
Accept: application/json
~~~

| Thành phần | Hướng truyền | Vai trò |
| --- | --- | --- |
| **Set-Cookie** | Server → client | Yêu cầu client lưu hoặc cập nhật cookie |
| **Cookie** | Client → server | Gửi các cặp tên/giá trị cookie phù hợp với request |
| **Path** | Thuộc tính Set-Cookie | Giới hạn phạm vi đường dẫn mà client gửi cookie |
| **Domain** | Thuộc tính Set-Cookie | Xác định phạm vi host áp dụng theo quy tắc cookie |
| **Max-Age/Expires** | Thuộc tính Set-Cookie | Hạn sử dụng của cookie |
| **Secure** | Thuộc tính Set-Cookie | Hạn chế gửi cookie qua kết nối không an toàn |
| **HttpOnly** | Thuộc tính Set-Cookie | Ngăn JavaScript phía trình duyệt truy cập cookie qua API như document.cookie |
| **SameSite** | Thuộc tính Set-Cookie | Điều khiển việc gửi cookie trong ngữ cảnh cross-site |

**Cookie không phải path parameter hay query parameter.** Nó được truyền trong header HTTP. Vì vậy, trong Spring REST Docs ta dùng nhóm descriptor dành riêng cho cookie, không đặt cookie vào **pathParameters(...)**, **queryParameters(...)** hoặc **requestFields(...)**.

## 2. Spring REST Docs mô tả cookie bằng API nào?

Spring REST Docs cung cấp các descriptor cho cookie:

~~~java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
~~~

- **cookieWithName("locale")** tạo descriptor cho cookie có tên locale.
- **requestCookies(...)** mô tả cookie client gửi trong request.
- **responseCookies(...)** mô tả cookie server gửi trong response.
- **description(...)** giải thích mục đích cookie để người dùng API hiểu khi nào cần gửi hoặc nhận nó.

Ví dụ:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Ngôn ngữ người dùng mong muốn, ví dụ vi")
);

responseCookies(
    cookieWithName("display-mode")
        .description("Chế độ hiển thị được server ghi nhớ")
);
~~~

Một request/response có thể có nhiều cookie. Mỗi cookie cần một descriptor riêng, có tên khớp với cookie thực tế trong operation được kiểm thử.

### 2.1. Cookie descriptor và header descriptor khác nhau

Cookie được truyền qua header, nhưng Spring REST Docs cung cấp snippet riêng để trình bày cookie theo tên:

| API tài liệu hóa | Mục đích |
| --- | --- |
| **requestHeaders(...)** | Mô tả header như Accept, Authorization hoặc X-Request-Id |
| **responseHeaders(...)** | Mô tả header như Content-Type, Location hoặc Cache-Control |
| **requestCookies(...)** | Mô tả từng cookie client gửi |
| **responseCookies(...)** | Mô tả từng cookie server thiết lập |

Nếu mục tiêu là hướng dẫn cookie **locale**, hãy dùng **requestCookies(cookieWithName("locale")...)**. Nếu muốn giải thích header tổng thể **Cookie**, có thể mô tả header đó ở phần header riêng khi phù hợp, nhưng không nên dùng nó thay cho bảng cookie.

## 3. Tạo controller ví dụ

Ví dụ sử dụng **Java 17+**, **Spring Boot 3.x**, Spring MVC và **JUnit 5**. Endpoint đọc cookie **locale**, dùng mặc định khi cookie vắng mặt, đồng thời gửi cookie **display-mode** về client.

~~~java
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/api/profile")
    ProfileResponse getProfile(
            @CookieValue(name = "locale", defaultValue = "vi")
            String locale,
            HttpServletResponse response) {

        Cookie displayMode = new Cookie("display-mode", "compact");
        displayMode.setPath("/");
        displayMode.setHttpOnly(true);
        displayMode.setSecure(true);
        displayMode.setMaxAge(3600);
        response.addCookie(displayMode);

        return new ProfileResponse("Lan", locale);
    }
}

record ProfileResponse(String name, String locale) {}
~~~

Giải thích:

- **@CookieValue("locale")** liên kết cookie request với tham số Java.
- **defaultValue = "vi"** cho phép endpoint dùng ngôn ngữ mặc định nếu cookie locale không được gửi.
- **response.addCookie(...)** yêu cầu servlet response gửi cookie display-mode.
- **HttpOnly**, **Secure**, **Path** và **Max-Age** là thuộc tính cookie được thiết lập cho response.

Đây là ví dụ minh họa. Trong hệ thống thực tế, cookie xác thực/session phải được quản lý bởi cơ chế bảo mật của ứng dụng hoặc Spring Security; không nên tự tạo session token bằng một chuỗi cố định như ví dụ cho cookie tùy chọn giao diện.

## 4. Test MockMvc và sinh snippet cho request/response cookies

Thêm dependency nếu dự án chưa có:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Ví dụ giả định BOM/dependency management của Spring Boot quản lý phiên bản tương thích. Tạo test cùng package với controller:

~~~java
import jakarta.servlet.http.Cookie;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.cookie;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProfileController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProfileCookieDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentProfileRequestAndResponseCookies() throws Exception {
        mockMvc.perform(get("/api/profile")
                .cookie(new Cookie("locale", "vi"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.locale").value("vi"))
            .andExpect(cookie().value("display-mode", "compact"))
            .andDo(document("profile-get",
                requestCookies(
                    cookieWithName("locale")
                        .description("Ngôn ngữ người dùng mong muốn")
                ),
                responseCookies(
                    cookieWithName("display-mode")
                        .description("Chế độ hiển thị được server ghi nhớ")
                )
            ));
    }
}
~~~

Trong test này:

1. **.cookie(new Cookie("locale", "vi"))** gửi cookie từ client vào MockMvc.
2. **requestCookies(...)** mô tả cookie locale trong request snippet.
3. Controller gọi **response.addCookie(...)** để tạo cookie display-mode.
4. **cookie().value(...)** xác nhận giá trị cookie mà response trả về.
5. **responseCookies(...)** mô tả cookie response trong snippet riêng.

Các assertion xác nhận cả hành vi HTTP và nội dung cookie. Descriptor chỉ mô tả hợp đồng tài liệu; nó không tự tạo cookie hoặc làm cho cookie xuất hiện trong response.

### 4.1. Kết quả snippet

Với identifier **profile-get**, thư mục snippet dự kiến có:

~~~text
build/generated-snippets/
└── profile-get/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-cookies.adoc
    └── response-cookies.adoc
~~~

REST Docs tạo các snippet cookie khi operation có descriptor **requestCookies(...)** và **responseCookies(...)**. Những snippet request/response mặc định khác được sinh theo cấu hình tích hợp.

Bảng tài liệu thể hiện tên cookie và mô tả đã khai báo. Giá trị thực tế của cookie được gửi/nhận vẫn có thể xuất hiện trong request/response snippet mặc định; hãy xem kỹ đầu ra trước khi xuất bản nếu giá trị có tính bí mật.

## 5. Cookie tùy chọn và trường hợp không gửi cookie

Một cookie có thể tùy chọn theo hợp đồng. Ví dụ **locale** không được gửi thì ứng dụng dùng mặc định **vi**. Bài kiểm thử trường hợp đó:

~~~java
@Test
void profileUsesDefaultLocaleWhenCookieIsMissing() throws Exception {
    mockMvc.perform(get("/api/profile")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.locale").value("vi"));
}
~~~

Nếu muốn tài liệu hóa cookie không bắt buộc, có thể đánh dấu descriptor:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Ngôn ngữ người dùng; mặc định vi nếu không gửi")
        .optional()
)
~~~

**optional()** trên cookie descriptor cho biết cookie có thể vắng mặt trong request được tài liệu hóa. Nó không thiết lập giá trị mặc định cho controller; giá trị mặc định đến từ **@CookieValue(defaultValue = "vi")** hoặc logic ứng dụng. Cần có test xác nhận hành vi khi thiếu cookie.

Với cookie bắt buộc, không đánh dấu optional:

~~~java
@CookieValue(name = "session-id") String sessionId
~~~

Nếu request không gửi cookie bắt buộc, Spring MVC có thể trả lỗi binding theo cơ chế xử lý ngoại lệ của ứng dụng. Hãy xác định status và cấu trúc lỗi trong test thay vì giả định mọi trường hợp thiếu cookie đều có cùng response.

## 6. Cookie response: hết hạn, xóa và thuộc tính bảo mật

Server có thể gửi cookie mới, cập nhật cookie hiện tại hoặc xóa cookie. Client nhận một header **Set-Cookie** mới và xử lý theo thuộc tính của nó.

### 6.1. Thiết lập cookie

~~~java
Cookie preference = new Cookie("display-mode", "compact");
preference.setPath("/");
preference.setHttpOnly(true);
preference.setSecure(true);
preference.setMaxAge(3600);
response.addCookie(preference);
~~~

Thuộc tính thường cần cân nhắc:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| **HttpOnly** | Cookie không truy cập được bằng JavaScript thông thường trong trình duyệt |
| **Secure** | Cookie chỉ được gửi qua kênh bảo mật theo quy tắc client |
| **SameSite** | Kiểm soát việc gửi cookie trong ngữ cảnh cross-site |
| **Path** | Phạm vi đường dẫn mà cookie áp dụng |
| **Domain** | Phạm vi host mà cookie áp dụng |
| **Max-Age** | Thời lượng tồn tại tính bằng giây |
| **Expires** | Thời điểm cookie hết hạn |

API Servlet và phiên bản Spring có thể khác nhau trong cách hỗ trợ thuộc tính mới như **SameSite**. Hãy kiểm tra header **Set-Cookie** thực tế được tạo và dùng cách cấu hình phù hợp phiên bản framework/container.

### 6.2. Xóa cookie

Để yêu cầu client xóa cookie, server thường gửi lại cùng tên và phạm vi cookie với giá trị rỗng và thời hạn hết hạn trong quá khứ hoặc **Max-Age=0**. Ví dụ servlet:

~~~java
Cookie expired = new Cookie("display-mode", "");
expired.setPath("/");
expired.setMaxAge(0);
response.addCookie(expired);
~~~

Phạm vi **Path** và **Domain** cần tương thích với cookie đã tạo để client xóa đúng cookie. Nếu chỉ xóa cùng tên nhưng khác phạm vi, client có thể vẫn giữ cookie cũ.

Có thể tài liệu hóa response cookie bị xóa bằng **responseCookies(...)** nếu hợp đồng yêu cầu client nhận biết việc xóa. Đồng thời kiểm tra **Set-Cookie** trong response để xác nhận thuộc tính hết hạn. Không chỉ dựa trên tên cookie trong snippet mà bỏ qua hành vi thực tế.

### 6.3. Cookie session và cookie preference

| Loại | Ví dụ | Lưu ý |
| --- | --- | --- |
| Session/authentication | **JSESSIONID**, cookie session của ứng dụng | Giá trị bí mật; không ghi giá trị thật vào tài liệu |
| CSRF | Cookie token CSRF | Mô tả mối quan hệ với header/token gửi lại nếu ứng dụng yêu cầu |
| Preference | **locale**, **display-mode** | Thường không nhạy cảm, nhưng vẫn dùng dữ liệu test giả |
| Tracking/analytics | Cookie phân tích hành vi | Chỉ tài liệu hóa khi thuộc contract API và đáp ứng yêu cầu quyền riêng tư |

Với session cookie, có thể ghi descriptor:

~~~java
responseCookies(
    cookieWithName("JSESSIONID")
        .description("Cookie phiên do server quản lý; client gửi lại tự động")
)
~~~

Nhưng **không đưa giá trị session thật** vào ví dụ hoặc snippet. Dùng phiên test giả, preprocessor thay thế hoặc loại giá trị khỏi bản ghi nếu không cần thiết.

## 7. Kết hợp cookie snippet với header và body snippet

Một operation có thể cần mô tả cả cookie, header và payload. Ví dụ:

~~~java
document("profile-get",
    requestHeaders(
        headerWithName("Accept")
            .description("Kiểu nội dung response client chấp nhận")
    ),
    requestCookies(
        cookieWithName("locale")
            .description("Ngôn ngữ người dùng mong muốn")
    ),
    responseCookies(
        cookieWithName("display-mode")
            .description("Chế độ hiển thị được server ghi nhớ")
    ),
    responseFields(
        fieldWithPath("name").description("Tên người dùng"),
        fieldWithPath("locale").description("Ngôn ngữ áp dụng")
    )
)
~~~

Các API descriptor cần import:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
~~~

Đặt descriptor vào đúng nhóm:

- **requestHeaders(...)** cho header Accept.
- **requestCookies(...)** cho cookie locale.
- **responseCookies(...)** cho cookie display-mode.
- **responseFields(...)** cho dữ liệu JSON response.

Không lặp cùng một thông tin ở nhiều snippet nếu điều đó khiến tài liệu khó hiểu. Khi cần giải thích toàn bộ cơ chế session, có thể có một mục riêng về authentication/session thay vì biến mọi cookie thành nội dung của từng operation.

## 8. Bảo vệ cookie và dữ liệu nhạy cảm trong tài liệu

Cookie thường chứa định danh phiên hoặc token. Do đó, tài liệu hóa cookie cần kiểm soát dữ liệu test:

1. Dùng giá trị giả lập, không dùng session ID, token hoặc cookie của tài khoản thật.
2. Không commit file cookie jar hoặc thông tin đăng nhập vào repository.
3. Kiểm tra **http-request.adoc**, **http-response.adoc**, **request-cookies.adoc** và **response-cookies.adoc** trước khi xuất bản.
4. Nếu giá trị xuất hiện trong snippet mặc định, cân nhắc preprocessor để thay thế/xóa giá trị nhạy cảm.
5. Giữ mô tả hợp đồng về tên cookie, vai trò, thuộc tính và cách client sử dụng; che giá trị không đồng nghĩa xóa toàn bộ tài liệu cookie.

Ví dụ dùng preprocessor xóa header Cookie hoặc Set-Cookie khỏi snippet mặc định:

~~~java
document("session-check",
    preprocessRequest(removeHeaders("Cookie")),
    preprocessResponse(removeHeaders("Set-Cookie")),
    requestCookies(
        cookieWithName("JSESSIONID")
            .description("Cookie phiên do server quản lý")
    )
)
~~~

Đây là cách kiểm soát snippet header thô; hãy xác nhận cách tương tác giữa preprocessor và cookie snippets ở phiên bản Spring REST Docs đang dùng. Nếu cookie snippet cũng chứa giá trị cần ẩn, kiểm tra output và chọn chiến lược thay thế phù hợp. Đừng giả định việc xóa một header tự động bảo đảm mọi snippet khác đều không chứa cùng dữ liệu.

## 9. Tài liệu hóa cookies trong Asciidoctor

Sau khi test tạo snippet **profile-get**, tài liệu có thể include:

~~~asciidoc
= Profile API
:toc: left

== Lấy hồ sơ người dùng

GET /api/profile

=== Request cookies

include::{snippets}/profile-get/request-cookies.adoc[]

=== Response cookies

include::{snippets}/profile-get/response-cookies.adoc[]

=== HTTP request

include::{snippets}/profile-get/http-request.adoc[]

=== HTTP response

include::{snippets}/profile-get/http-response.adoc[]
~~~

Với Gradle và plugin **org.asciidoctor.jvm.convert** đã được cấu hình:

~~~groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir
}
~~~

Tác vụ Asciidoctor phụ thuộc vào test nên snippet được sinh trước khi include. Trong CI, chỉ xuất bản tài liệu khi test REST Docs và bước dựng tài liệu thành công. Nếu descriptor khai báo cookie không có trong operation hoặc thiếu một cookie cần mô tả, cơ chế kiểm chứng của REST Docs có thể làm test thất bại theo cấu hình descriptor.

Nếu tài liệu cuối xuất bản bằng Markdown, cần công cụ chuyển đổi hoặc cách nhúng snippet tương ứng. Chỉ thị **include::{snippets}/...[]** là cú pháp của Asciidoctor, không phải Markdown tiêu chuẩn.

## 10. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Không sinh **request-cookies.adoc** | Chưa khai báo **requestCookies(...)** hoặc request không chứa cookie tương ứng | Gửi cookie trong MockMvc và thêm descriptor đúng tên |
| Không sinh **response-cookies.adoc** | Controller/response không thiết lập cookie hoặc thiếu **responseCookies(...)** | Gọi **response.addCookie(...)**, assert Set-Cookie và khai báo descriptor |
| Descriptor báo cookie không tồn tại | Sai tên, khác chữ hoa/thường hoặc cookie không có trong operation | Đối chiếu tên thực tế trong request/response |
| Cookie tùy chọn gây lỗi khi vắng mặt | Descriptor chưa đánh dấu optional hoặc controller không có giá trị mặc định | Đồng bộ hợp đồng, optional() và logic xử lý |
| Tài liệu lộ session ID/token | Snippet request/response ghi giá trị thật | Dùng fixture giả, che hoặc loại giá trị khỏi snippets |
| Cookie bị xóa nhưng client vẫn gửi lại | Sai Path/Domain hoặc chưa có Max-Age=0/Expires phù hợp | Gửi Set-Cookie cùng phạm vi và kiểm tra response header |
| Cookie không được gửi trên trình duyệt | Secure, SameSite, Domain, Path hoặc chính sách cross-site không phù hợp | Kiểm thử trong môi trường client/browser tương ứng |
| Chỉ thấy header Set-Cookie mà thiếu bảng cookie | Mới tài liệu hóa responseHeaders | Dùng **responseCookies(...)** cho cookie |
| Asciidoctor báo thiếu cookie snippet | Test chưa sinh snippet hoặc sai identifier trong include | Kiểm tra document ID, output directory và thứ tự test → asciidoctor |

## 11. Bài thực hành

API quản lý tùy chọn giao diện:

~~~text
GET /api/settings
POST /api/settings
~~~

Hợp đồng:

- Request GET có thể gửi cookie **locale**; nếu vắng mặt, server sử dụng **vi**.
- Response GET thiết lập cookie **display-mode** với giá trị giả lập **compact**.
- POST nhận JSON body chứa **displayMode**, rồi cập nhật cookie **display-mode**.
- Cookie preference không chứa thông tin xác thực.

Yêu cầu:

1. Viết controller với **@CookieValue** để đọc **locale** và **HttpServletResponse.addCookie(...)** để trả **display-mode**.
2. Viết MockMvc test có cookie locale; assert response JSON và cookie response.
3. Dùng **requestCookies(cookieWithName("locale")...)** và **responseCookies(cookieWithName("display-mode")...)** để sinh hai snippet.
4. Viết test không gửi locale và xác nhận mặc định **vi**; đánh dấu descriptor optional trong bài tài liệu phù hợp.
5. Viết test POST có JSON body và response cookie, kết hợp **requestFields(...)** nếu cần mô tả payload.
6. Nhúng cookie snippets và HTTP snippets vào Asciidoctor; kiểm tra CI tạo đủ file.
7. Thử thay cookie preference bằng một cookie session giả lập; đảm bảo giá trị bí mật không xuất hiện trong tài liệu.

Mẫu descriptor:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Ngôn ngữ người dùng; mặc định vi nếu không gửi")
        .optional()
),
responseCookies(
    cookieWithName("display-mode")
        .description("Chế độ hiển thị được lưu cho lần truy cập sau")
)
~~~

**Tiêu chí hoàn thành:** test xác nhận request cookie và response cookie; snippet ghi đúng tên và mô tả; trường hợp thiếu cookie xử lý theo hợp đồng; tài liệu không để lộ dữ liệu nhạy cảm và được dựng thành công từ snippets.

## Ghi nhớ

**requestCookies(...)** mô tả cookie client gửi, còn **responseCookies(...)** mô tả cookie server thiết lập. Dùng **cookieWithName(...)** để tạo descriptor và **description(...)** để giải thích mục đích; kết hợp assertion MockMvc để xác nhận cookie thật sự được gửi/nhận. Cookie tùy chọn cần được mô tả bằng **optional()** khi phù hợp và phải có test cho trường hợp vắng mặt. Với session ID hoặc token, luôn dùng dữ liệu giả và kiểm tra mọi snippet trước khi xuất bản. Sau đó include **request-cookies.adoc** và **response-cookies.adoc** trong Asciidoctor và nối tác vụ test vào build/CI để tài liệu phản ánh đúng contract cookie của API.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs CookieDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/cookies/CookieDocumentation.html), [Spring MVC @CookieValue](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/cookievalue.html) và [RFC 6265: HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265).
