# cookieWithName và mô tả cookie

## Mục tiêu bài học

Khi tài liệu hóa cookie bằng **Spring REST Docs**, tên cookie giúp client nhận diện dữ liệu cần gửi hoặc nhận, còn mô tả giải thích mục đích và cách sử dụng. Descriptor **cookieWithName(...)** là điểm bắt đầu để khai báo từng cookie; nó được đặt bên trong **requestCookies(...)** hoặc **responseCookies(...)** tùy hướng truyền.

Bài học thuộc chương **Cookies** của module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ test HTTP bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn tài liệu Asciidoctor/Markdown rồi tích hợp vào build và CI.

Sau bài này, bạn có thể:

- Khai báo descriptor bằng **cookieWithName("...")**.
- Viết **description(...)** rõ ý nghĩa, thời điểm và mục đích sử dụng cookie.
- Đặt descriptor vào đúng nhóm **requestCookies(...)** hoặc **responseCookies(...)**.
- Mô tả nhiều cookie, cookie tùy chọn và cookie được chủ động bỏ khỏi bảng.
- Phân biệt descriptor với giá trị cookie, thuộc tính **Set-Cookie** và header **Cookie**.
- Kết hợp cookie descriptor với header/payload descriptor trong một operation.
- Kiểm tra snippet, tránh công bố giá trị nhạy cảm và nhúng tài liệu vào Asciidoctor/CI.

## 1. cookieWithName(...) là gì?

**cookieWithName(name)** tạo một descriptor cho cookie có tên **name**. Descriptor này được đưa vào hàm nhóm:

- **requestCookies(...)**: mô tả cookie mà client gửi trong HTTP request.
- **responseCookies(...)**: mô tả cookie mà server thiết lập trong HTTP response.

Ví dụ:

~~~java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;

requestCookies(
    cookieWithName("locale")
        .description("Ngôn ngữ người dùng mong muốn")
);

responseCookies(
    cookieWithName("display-mode")
        .description("Chế độ hiển thị được lưu cho lần truy cập sau")
);
~~~

Trong ví dụ này:

| Thành phần | Vai trò |
| --- | --- |
| **cookieWithName("locale")** | Chọn cookie tên **locale** |
| **description(...)** | Giải thích mục đích cookie cho người đọc tài liệu |
| **requestCookies(...)** | Khai báo cookie thuộc request |
| **cookieWithName("display-mode")** | Chọn cookie tên **display-mode** |
| **responseCookies(...)** | Khai báo cookie thuộc response |

Descriptor không tạo cookie và không thay đổi ứng dụng. Cookie phải thật sự xuất hiện trong request hoặc response của bài test thì REST Docs mới có thể đối chiếu và sinh snippet tương ứng.

## 2. Phân biệt tên cookie, giá trị và thuộc tính

Xét một response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: display-mode=compact; Path=/; Max-Age=3600; HttpOnly; Secure; SameSite=Lax
Content-Type: application/json

{"status":"saved"}
~~~

Ở đây:

- **display-mode** là tên cookie.
- **compact** là giá trị cookie.
- **Path**, **Max-Age**, **HttpOnly**, **Secure** và **SameSite** là thuộc tính của cookie trong **Set-Cookie**.
- **status** là field trong JSON response, không phải cookie.

Vì vậy descriptor thường là:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Chế độ hiển thị mà server đã lưu")
)
~~~

Không truyền giá trị vào **cookieWithName(...)**:

| Cách viết | Đúng/sai | Lý do |
| --- | --- | --- |
| **cookieWithName("display-mode")** | Đúng | Đây là tên cookie |
| **cookieWithName("compact")** | Sai trong ví dụ | Đây là giá trị, không phải tên |
| **cookieWithName("Path")** | Sai trong ví dụ | Đây là thuộc tính Set-Cookie |
| **cookieWithName("status")** | Sai trong ví dụ | Đây là field JSON |

Cookie trong request có dạng **Cookie: locale=vi**; cookie trong response có dạng **Set-Cookie: display-mode=compact; ...**. Descriptor chỉ chọn tên cookie, không chứa toàn bộ header thô.

## 3. Viết description có ích cho người gọi API

Một mô tả tốt trả lời được những câu hỏi người tích hợp API thường cần:

1. Cookie dùng để làm gì?
2. Client gửi cookie ở request nào hoặc server tạo cookie trong trường hợp nào?
3. Giá trị có định dạng hoặc tập giá trị được phép nào?
4. Cookie có tùy chọn hay có thể vắng mặt không?
5. Có thuộc tính hoặc lưu ý bảo mật quan trọng nào cần biết?

Ví dụ:

| Mô tả chung chung | Mô tả có ích hơn |
| --- | --- |
| “Ngôn ngữ” | “Mã ngôn ngữ ưu tiên của người dùng, ví dụ vi hoặc en” |
| “Theme” | “Chế độ giao diện đã lưu; nhận light hoặc dark” |
| “Session” | “Cookie phiên do server quản lý; client gửi lại trong các request thuộc phạm vi cookie” |
| “Cookie preference” | “Chế độ hiển thị compact hoặc comfortable do người dùng chọn” |

Nên viết mô tả ngắn nhưng rõ nghĩa. Nếu có nhiều quy tắc như thời hạn, chính sách SameSite hoặc luồng xác thực, trình bày ở phần văn bản riêng hoặc bảng header/cookie attributes; tránh biến description thành một đoạn dài khó đọc.

### 3.1. Mô tả theo góc nhìn client

Với cookie request:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Mã ngôn ngữ client muốn dùng cho nội dung trả về; ví dụ vi hoặc en")
)
~~~

Mô tả cho biết client cần gửi gì và gửi để làm gì.

Với cookie response:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Chế độ giao diện server lưu lại sau khi client cập nhật tùy chọn")
)
~~~

Mô tả cho biết server trả cookie trong tình huống nào và client có thể dùng nó ra sao.

Không viết mô tả theo góc nhìn implementation nội bộ như “được set ở method updatePreference()”. Tài liệu API nên ưu tiên hành vi quan sát được và hợp đồng mà client cần hiểu.

## 4. Khai báo nhiều cookie trong cùng một operation

Một request có thể gửi nhiều cookie:

~~~http
GET /api/profile
Cookie: locale=vi; display-mode=compact
Accept: application/json
~~~

Mô tả chúng bằng nhiều descriptor trong cùng **requestCookies(...)**:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Mã ngôn ngữ client mong muốn, ví dụ vi"),
    cookieWithName("display-mode")
        .description("Chế độ giao diện client đã lưu, ví dụ compact")
)
~~~

Một response có thể phát hành nhiều cookie:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Chế độ hiển thị được lưu"),
    cookieWithName("locale")
        .description("Ngôn ngữ ưu tiên được ghi nhớ")
)
~~~

Mỗi descriptor phải dùng đúng tên cookie mà operation thực sự gửi hoặc nhận. Tên cookie phân biệt chữ hoa/chữ thường theo cách triển khai và quy tắc cookie; giữ thống nhất cách viết trong controller, test và tài liệu.

Không tạo nhiều descriptor cùng tên để biểu diễn nhiều giá trị của một cookie. Nếu một cookie có giá trị thay đổi giữa các tình huống, mô tả một descriptor cho tên đó và viết test riêng cho từng trường hợp có ý nghĩa.

## 5. Cookie request và cookie response là hai nhóm độc lập

Một operation có thể vừa nhận cookie, vừa trả cookie. Ví dụ server đọc **locale** và phát hành **display-mode**:

~~~java
document("profile-get",
    requestCookies(
        cookieWithName("locale")
            .description("Mã ngôn ngữ client mong muốn")
    ),
    responseCookies(
        cookieWithName("display-mode")
            .description("Chế độ giao diện server ghi nhớ")
    )
)
~~~

Kết quả có hai snippet:

~~~text
build/generated-snippets/profile-get/
├── request-cookies.adoc
└── response-cookies.adoc
~~~

Hai bảng biểu diễn hai hướng truyền riêng. Không dùng **responseCookies(...)** cho cookie client gửi, hoặc **requestCookies(...)** cho cookie server vừa thiết lập.

### 5.1. Kết hợp với HTTP headers và payload

Một operation có thể tài liệu hóa cookie, header và JSON response cùng lúc:

~~~java
document("profile-get",
    requestHeaders(
        headerWithName("Accept")
            .description("Kiểu nội dung client chấp nhận")
    ),
    requestCookies(
        cookieWithName("locale")
            .description("Mã ngôn ngữ client mong muốn")
    ),
    responseCookies(
        cookieWithName("display-mode")
            .description("Chế độ giao diện server ghi nhớ")
    ),
    responseFields(
        fieldWithPath("name").description("Tên người dùng"),
        fieldWithPath("locale").description("Ngôn ngữ áp dụng")
    )
)
~~~

Các import:

~~~java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
~~~

Đặt mỗi thông tin vào đúng loại descriptor:

| Dữ liệu | Descriptor |
| --- | --- |
| Header **Accept** | **requestHeaders(...)** |
| Cookie **locale** gửi lên | **requestCookies(...)** |
| Cookie **display-mode** trả về | **responseCookies(...)** |
| Field JSON **name**, **locale** | **responseFields(...)** |

## 6. Cookie tùy chọn: optional()

Nếu cookie có thể vắng mặt theo hợp đồng API, descriptor có thể đánh dấu **optional()**:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Mã ngôn ngữ client mong muốn; mặc định vi nếu không gửi")
        .optional()
)
~~~

Hoặc với cookie response chỉ xuất hiện trong một số trường hợp:

~~~java
responseCookies(
    cookieWithName("promotion")
        .description("Cookie mã chương trình ưu đãi; chỉ phát hành khi đủ điều kiện")
        .optional()
)
~~~

**optional()** mô tả việc cookie có thể không xuất hiện trong operation được kiểm tra. Nó không tự:

- Tạo giá trị mặc định cho **@CookieValue**.
- Thay đổi controller hoặc filter.
- Làm cookie xuất hiện trong response.
- Xác nhận điều kiện nghiệp vụ phát hành cookie.

Ví dụ controller cần có hành vi riêng:

~~~java
@GetMapping("/api/profile")
ProfileResponse profile(
        @CookieValue(name = "locale", defaultValue = "vi") String locale) {
    return new ProfileResponse(locale);
}
~~~

Test nên có cả trường hợp gửi **locale=vi** và không gửi cookie để xác nhận ứng dụng thực sự dùng giá trị mặc định.

## 7. Bỏ cookie khỏi bảng bằng ignored()

Đôi khi cookie kỹ thuật tồn tại trong operation nhưng không cần lặp lại trong bảng tài liệu cụ thể. Có thể đánh dấu descriptor **ignored()**:

~~~java
requestCookies(
    cookieWithName("tracking-id").ignored(),
    cookieWithName("locale")
        .description("Mã ngôn ngữ client mong muốn")
)
~~~

Cookie **tracking-id** vẫn có trong request, nhưng không được trình bày thành dòng trong snippet. Chỉ nên dùng khi cookie đã được giải thích ở một phần chung hoặc nó không thuộc nội dung người gọi cần quan tâm ở operation đó.

**ignored()** khác với không khai báo descriptor:

- **ignored()** thể hiện rõ rằng cookie đã được nhận biết nhưng cố ý không đưa vào bảng.
- Không khai báo có thể khiến chế độ kiểm tra nghiêm ngặt báo cookie chưa được tài liệu hóa.
- **optional()** nói rằng cookie có thể vắng mặt; **ignored()** nói rằng cookie không cần hiển thị trong bảng.

Không dùng **ignored()** để che một cookie chứa bí mật rồi cho rằng dữ liệu đã biến mất khỏi mọi snippet. Giá trị có thể vẫn xuất hiện trong **http-request.adoc** hoặc **http-response.adoc**. Cần kiểm tra và preprocessing nếu cần ẩn giá trị.

## 8. Mô tả cookie session và cookie bảo mật

Cookie session thường nhạy cảm. Tài liệu nên giải thích vai trò và cách client sử dụng mà không đưa giá trị thật vào snippet.

~~~java
responseCookies(
    cookieWithName("SESSION")
        .description("Cookie phiên do server quản lý; client lưu và gửi lại trên các request thuộc phạm vi cookie")
)
~~~

Với cookie CSRF:

~~~java
responseCookies(
    cookieWithName("XSRF-TOKEN")
        .description("Token CSRF do server cấp; client sử dụng theo cơ chế bảo vệ CSRF của API")
)
~~~

Các mô tả trên là ví dụ, không khẳng định mọi ứng dụng dùng cùng cơ chế. Nếu client phải đọc cookie CSRF rồi gửi lại giá trị ở header **X-XSRF-TOKEN**, cần mô tả cả cookie response và header request ở phần xác thực/CSRF tương ứng.

Các thuộc tính **Secure**, **HttpOnly**, **SameSite**, **Path**, **Domain**, **Max-Age** và **Expires** thường hiển thị trong header **Set-Cookie** của response snippet. Cookie descriptor mô tả tên và ý nghĩa; nếu thuộc tính là phần quan trọng của contract, hãy có assertion riêng và diễn giải trong tài liệu.

Không ghi session ID thật, refresh token hoặc cookie xác thực production vào source test. Dùng giá trị giả định có thể công khai; kiểm tra cả snippet cookie và HTTP response trước khi publish.

## 9. Ví dụ hoàn chỉnh với MockMvc

Ví dụ dùng **Java 17+**, **Spring Boot 3.x**, **JUnit 5** và **spring-restdocs-mockmvc**.

### 9.1. Controller

~~~java
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/api/profile")
    ProfileView getProfile(
            @CookieValue(name = "locale", defaultValue = "vi")
            String locale,
            HttpServletResponse response) {

        Cookie displayMode = new Cookie("display-mode", "compact");
        displayMode.setPath("/");
        displayMode.setHttpOnly(true);
        displayMode.setSecure(true);
        displayMode.setMaxAge(3600);
        response.addCookie(displayMode);

        return new ProfileView("Lan", locale);
    }
}

record ProfileView(String name, String locale) {}
~~~

### 9.2. Test và descriptor

~~~java
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
class ProfileCookieTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentCookieNamesAndDescriptions() throws Exception {
        mockMvc.perform(get("/api/profile")
                .cookie(new jakarta.servlet.http.Cookie("locale", "vi"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.locale").value("vi"))
            .andExpect(cookie().value("display-mode", "compact"))
            .andExpect(cookie().httpOnly("display-mode", true))
            .andDo(document("profile-get",
                requestCookies(
                    cookieWithName("locale")
                        .description("Mã ngôn ngữ client mong muốn")
                ),
                responseCookies(
                    cookieWithName("display-mode")
                        .description("Chế độ giao diện server đã lưu")
                )
            ));
    }
}
~~~

Trong test:

- Cookie **locale** được gửi vào request bằng **.cookie(...)**.
- Descriptor request dùng **cookieWithName("locale")**.
- Controller phát hành **display-mode** trong response.
- Descriptor response dùng **cookieWithName("display-mode")**.
- Assertion xác nhận giá trị và thuộc tính của cookie thực sự trả về.

### 9.3. Kết quả tài liệu

Thư mục snippet:

~~~text
build/generated-snippets/
└── profile-get/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-cookies.adoc
    └── response-cookies.adoc
~~~

**request-cookies.adoc** và **response-cookies.adoc** trình bày tên cùng mô tả theo descriptor. **http-request.adoc** và **http-response.adoc** thể hiện request/response quan sát được; các giá trị cookie có thể xuất hiện ở đây. Không chỉnh sửa file trong **generated-snippets** bằng tay; hãy sửa test hoặc descriptor rồi chạy lại để sinh nội dung mới.

## 10. Tích hợp vào Asciidoctor và CI

Trong **src/docs/asciidoc/profile.adoc**:

~~~asciidoc
= Profile API
:toc: left

== Lấy hồ sơ

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

Ví dụ Gradle Groovy DSL khi plugin **org.asciidoctor.jvm.convert** đã được cấu hình:

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

Tác vụ Asciidoctor phụ thuộc vào test nên các snippet được tạo trước khi include. Trong CI, kiểm tra các thư mục **profile-get** và những file **request-cookies.adoc**, **response-cookies.adoc** đã được sinh. Nếu đổi tên cookie trong code nhưng quên cập nhật descriptor, test tài liệu phải phát hiện sự lệch đó.

Nếu đầu ra cuối là Markdown, dùng bộ chuyển đổi hoặc cơ chế nhúng snippet phù hợp. **include::{snippets}/...[]** là cú pháp Asciidoctor, không phải cú pháp Markdown chuẩn.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Descriptor không tìm thấy cookie | Tên trong **cookieWithName(...)** sai hoặc cookie không có trong operation | Đối chiếu tên cookie request/response thực tế |
| Chọn nhầm giá trị làm tên cookie | Dùng **cookieWithName("compact")** thay vì **cookieWithName("display-mode")** | Dùng tên ở bên trái dấu **=** |
| Mô tả cookie request trong response snippet | Đặt descriptor vào sai nhóm | Dùng **requestCookies(...)** hoặc **responseCookies(...)** đúng hướng |
| Bảng cookie thiếu một dòng | Quên descriptor cho cookie còn lại | Khai báo từng cookie riêng biệt |
| Cookie không xuất hiện nhưng test vẫn cần tài liệu | Cookie có thể tùy chọn nhưng descriptor chưa phản ánh | Dùng **optional()** khi phù hợp và test trường hợp vắng mặt |
| Cookie kỹ thuật xuất hiện trong bảng | Chưa có quyết định tài liệu hóa | Dùng **ignored()** khi đã giải thích ở nơi khác |
| Session ID vẫn lộ trong HTTP response snippet | Chỉ bỏ cookie khỏi bảng descriptor | Dùng fixture giả hoặc preprocessing và kiểm tra mọi snippet |
| Mô tả cookie không nói client cần làm gì | Description quá chung chung | Viết theo mục đích và hành vi quan sát được |
| Asciidoctor thiếu cookie snippet | Test chưa chạy hoặc include sai identifier | Kiểm tra document ID, output directory và task dependency |

## 12. Bài thực hành

Một API lưu tùy chọn người dùng:

~~~text
POST /api/preferences
~~~

Response phát hành hai cookie:

- **display-mode**: giá trị compact hoặc comfortable.
- **locale**: mã ngôn ngữ vi hoặc en.

Yêu cầu:

1. Viết controller hoặc filter phát hành hai cookie với **Set-Cookie**.
2. Viết MockMvc test xác nhận cả hai cookie có trong response và giá trị đúng.
3. Dùng **responseCookies(...)** với hai descriptor **cookieWithName(...)**.
4. Viết description nêu mục đích và tập giá trị được chấp nhận của từng cookie.
5. Thêm assertion cho **Path**, **Secure**, **HttpOnly** và **Max-Age** theo contract.
6. Nhúng **response-cookies.adoc** và **http-response.adoc** vào Asciidoctor.
7. Thử đổi tên cookie trong controller nhưng không sửa descriptor; xác nhận test tài liệu phát hiện mismatch.

Mẫu descriptor:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Chế độ giao diện đã lưu; compact hoặc comfortable"),
    cookieWithName("locale")
        .description("Mã ngôn ngữ được lưu để dùng cho lần truy cập sau; vi hoặc en")
)
~~~

**Tiêu chí hoàn thành:** cả hai tên cookie khớp response; mô tả có ý nghĩa cho client; test xác nhận giá trị và thuộc tính; snippet phản ánh đúng response; tài liệu Asciidoctor được sinh thành công trong build/CI.

## Ghi nhớ

**cookieWithName("name")** khai báo descriptor theo tên cookie; **description(...)** giải thích mục đích và cách client sử dụng. Đặt descriptor trong **requestCookies(...)** khi client gửi cookie và **responseCookies(...)** khi server phát hành cookie. Có thể dùng **optional()** cho cookie có thể vắng mặt hoặc **ignored()** khi chủ động không hiển thị cookie đã được nhận biết, nhưng cả hai đều không che giá trị khỏi mọi snippet. Hãy kiểm tra request/response thực tế, bảo vệ session/token và include cookie snippets vào Asciidoctor để hợp đồng cookie được kiểm chứng bởi test và CI.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs CookieDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/cookies/CookieDocumentation.html), [Spring MVC @CookieValue](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/cookievalue.html) và [RFC 6265](https://www.rfc-editor.org/rfc/rfc6265).
