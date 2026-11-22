# Cookie bắt buộc, tùy chọn và giá trị mặc định

## Mục tiêu bài học

Một API có thể yêu cầu client gửi cookie, chấp nhận cookie nếu có, hoặc dùng giá trị mặc định khi cookie vắng mặt. Ba trường hợp này cần được thể hiện nhất quán ở controller, bài kiểm thử và tài liệu **Spring REST Docs**. Nếu controller yêu cầu cookie nhưng descriptor lại đánh dấu tùy chọn, tài liệu sẽ mô tả sai hợp đồng. Ngược lại, nếu cookie thực sự tùy chọn nhưng test không kiểm tra trường hợp vắng mặt, client có thể gặp lỗi ngoài dự kiến.

Bài học thuộc chương **Cookies** của module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn tài liệu Asciidoctor/Markdown và đưa vào build, CI.

Sau bài học, bạn có thể:

- Phân biệt cookie bắt buộc, cookie tùy chọn và cookie có giá trị mặc định.
- Cấu hình **@CookieValue** bằng **required** và **defaultValue**.
- Mô tả tính tùy chọn bằng **optional()** trên cookie descriptor.
- Viết MockMvc test cho request có cookie và không có cookie.
- Tránh nhầm optional() của REST Docs với hành vi binding của Spring MVC.
- Tài liệu hóa giá trị mặc định, phản hồi lỗi và nhiều tình huống cookie.
- Kết hợp request/response cookie snippets với Asciidoctor và CI.

## 1. Ba hợp đồng cookie thường gặp

Giả sử endpoint **GET /api/profile** nhận cookie **locale** để chọn ngôn ngữ:

| Hợp đồng | Khi client gửi cookie | Khi client không gửi | Ví dụ khai báo Spring |
| --- | --- | --- | --- |
| Bắt buộc | Dùng giá trị cookie | Request không bind được; thường trả lỗi 400 theo xử lý mặc định | **@CookieValue("locale")** |
| Tùy chọn, không có mặc định | Dùng giá trị cookie | Java nhận **null** nếu kiểu/khai báo cho phép | **@CookieValue(name="locale", required=false)** |
| Có giá trị mặc định | Dùng giá trị cookie | Dùng giá trị thay thế | **@CookieValue(name="locale", defaultValue="vi")** |

Đây là ba hành vi ở **tầng binding/controller**. Spring REST Docs có cơ chế riêng để mô tả cookie có thể vắng mặt trong request được tài liệu hóa. Hai tầng phải nhất quán.

### 1.1. Luồng xử lý

~~~mermaid
flowchart TD
    A["HTTP request"] --> B{"Có cookie locale?"}
    B -->|Có| C["Bind giá trị cookie"]
    B -->|Không| D{"Controller khai báo thế nào?"}
    D -->|required=true| E["Binding error, thường 400"]
    D -->|required=false| F["Bind null"]
    D -->|defaultValue=vi| G["Bind giá trị vi"]
    C --> H["Controller xử lý"]
    F --> H
    G --> H
~~~

Không xem mọi cookie là tùy chọn chỉ vì client có thể bỏ header. **Hợp đồng API** quyết định cookie nào bắt buộc, và code/test cần thực thi đúng hợp đồng đó.

## 2. Cookie bắt buộc

### 2.1. Khai báo bằng @CookieValue

Khi cookie bắt buộc, có thể dùng:

~~~java
@GetMapping("/api/profile")
ProfileResponse getProfile(
        @CookieValue("locale") String locale) {
    return new ProfileResponse("Lan", locale);
}
~~~

Thuộc tính **required** mặc định là **true**. Nếu request không có cookie **locale**, Spring MVC không thể bind tham số bắt buộc; với cấu hình xử lý ngoại lệ thông thường, response thường là **400 Bad Request**.

Nếu muốn viết rõ hợp đồng:

~~~java
@CookieValue(name = "locale", required = true) String locale
~~~

Hai cách khai báo có cùng ý nghĩa. Chỉ dùng **required = true** khi nó giúp code dễ hiểu hơn.

### 2.2. Descriptor bắt buộc trong Spring REST Docs

Với cookie bắt buộc, khai báo descriptor không có **optional()**:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Mã ngôn ngữ bắt buộc của client, ví dụ vi hoặc en")
)
~~~

Imports:

~~~java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
~~~

Bài test thành công phải gửi cookie:

~~~java
mockMvc.perform(get("/api/profile")
        .cookie(new Cookie("locale", "vi")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.locale").value("vi"))
    .andDo(document("profile-get",
        requestCookies(
            cookieWithName("locale")
                .description("Mã ngôn ngữ bắt buộc của client")
        )
    ));
~~~

Trong ví dụ trên, **requestCookies(...)** mô tả cookie được gửi thật trong request. REST Docs kiểm tra descriptor với operation; nó không tự biến cookie thiếu thành có sẵn.

### 2.3. Kiểm thử trường hợp thiếu cookie

Nên có test riêng cho request không có cookie:

~~~java
@Test
void rejectsRequestWithoutRequiredLocaleCookie() throws Exception {
    mockMvc.perform(get("/api/profile"))
        .andExpect(status().isBadRequest());
}
~~~

Mã 400 ở ví dụ phụ thuộc controller và exception handling của ứng dụng. Nếu có **@ControllerAdvice** tùy chỉnh, hãy assert mã HTTP và payload đúng theo hợp đồng thực tế. Test này kiểm tra hành vi thiếu cookie; không nhất thiết phải sinh snippet thành công của operation.

## 3. Cookie tùy chọn không có giá trị mặc định

Nếu API chấp nhận request dù cookie không tồn tại và ứng dụng xử lý trường hợp đó riêng, khai báo:

~~~java
@GetMapping("/api/profile")
ProfileResponse getProfile(
        @CookieValue(name = "locale", required = false) String locale) {
    String effectiveLocale = locale == null ? "vi" : locale;
    return new ProfileResponse("Lan", effectiveLocale);
}
~~~

Ở đây:

- Khi có **locale=en**, controller dùng **en**.
- Khi không có cookie, tham số Java là **null**.
- Ứng dụng tự quyết định giá trị thay thế trong logic controller/service.

Nếu xử lý null ở service, nên đặt quy tắc mặc định tại một nơi rõ ràng thay vì lặp lại trong nhiều endpoint.

Trong Spring REST Docs, cookie descriptor được đánh dấu tùy chọn:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Mã ngôn ngữ client mong muốn; nếu thiếu, API dùng vi")
        .optional()
)
~~~

**optional()** nói với REST Docs rằng cookie có thể không xuất hiện trong request được tài liệu hóa. Nó **không** thay đổi **@CookieValue(required = ...)**, không tự gán **null** hoặc giá trị **vi**, và không thay đổi hành vi controller.

### 3.1. Test có cookie và không có cookie

~~~java
@Test
void usesProvidedLocaleCookie() throws Exception {
    mockMvc.perform(get("/api/profile")
            .cookie(new Cookie("locale", "en")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.locale").value("en"));
}

@Test
void usesFallbackWhenOptionalLocaleCookieIsMissing() throws Exception {
    mockMvc.perform(get("/api/profile"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.locale").value("vi"));
}
~~~

Khi sinh snippet cho request **có** cookie, descriptor tùy chọn vẫn có thể được dùng để mô tả hợp đồng tổng quát. Nếu cần tạo snippet phản ánh rõ trường hợp không có cookie, hãy ghi một operation/test riêng và dùng descriptor **optional()** để REST Docs biết việc vắng mặt là hợp lệ.

## 4. Cookie có giá trị mặc định

### 4.1. Dùng defaultValue

Nếu API có giá trị mặc định cố định, khai báo trực tiếp:

~~~java
@GetMapping("/api/profile")
ProfileResponse getProfile(
        @CookieValue(name = "locale", defaultValue = "vi") String locale) {
    return new ProfileResponse("Lan", locale);
}
~~~

Khi không có cookie **locale**, Spring sử dụng **vi**. Khi cookie có giá trị, giá trị đó được bind. Trong **@CookieValue**, đặt **defaultValue** cũng khiến tham số không còn bắt buộc theo nghĩa **required**; không cần đồng thời viết **required = false**.

Một cách dùng khác là:

~~~java
@CookieValue(name = "locale", required = false) String locale
// rồi tự xử lý null trong code
~~~

Hai cách có thể cho kết quả tương tự, nhưng thể hiện ý định khác nhau. **defaultValue** phù hợp khi có giá trị thay thế rõ ràng; **required=false** phù hợp khi code muốn phân biệt trạng thái vắng mặt và tự xử lý.

### 4.2. Tài liệu hóa giá trị mặc định

Descriptor:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Mã ngôn ngữ; mặc định vi nếu client không gửi cookie")
        .optional()
)
~~~

Descriptor không có thuộc tính riêng để đặt giá trị mặc định cho **@CookieValue**. Ghi giá trị mặc định trong **description(...)**, sau đó chứng minh bằng test:

~~~java
@Test
void documentsDefaultLocaleWhenCookieIsAbsent() throws Exception {
    mockMvc.perform(get("/api/profile")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.locale").value("vi"))
        .andDo(document("profile-default-locale",
            requestCookies(
                cookieWithName("locale")
                    .description("Mã ngôn ngữ; mặc định vi nếu không gửi")
                    .optional()
            )
        ));
}
~~~

Test này ghi lại request không có cookie và response dùng ngôn ngữ mặc định. Nếu phiên bản REST Docs đang dùng không chấp nhận descriptor cookie tùy chọn vắng mặt như dự kiến, kiểm tra hành vi của phiên bản đó và xác minh snippet sinh ra; không khai báo cookie như thể nó đã được gửi.

## 5. Phân biệt required, defaultValue và optional()

Ba thuộc tính thường bị nhầm vì cùng liên quan đến việc cookie có thể vắng mặt:

| Cơ chế | Nơi khai báo | Tác động |
| --- | --- | --- |
| **required=true** | **@CookieValue** | Spring yêu cầu cookie để bind tham số |
| **required=false** | **@CookieValue** | Cho phép thiếu cookie; giá trị bind thường là null |
| **defaultValue="vi"** | **@CookieValue** | Dùng vi khi cookie thiếu hoặc rỗng theo cơ chế binding |
| **.optional()** | Cookie descriptor REST Docs | Cho phép cookie không xuất hiện khi kiểm tra/tạo tài liệu |
| **.ignored()** | Cookie descriptor REST Docs | Biết cookie tồn tại nhưng không hiển thị nó trong bảng snippet |

Hãy ghi nhớ hai tầng độc lập:

- **Spring MVC** quyết định request thiếu cookie có được xử lý hay không và giá trị Java nhận được là gì.
- **Spring REST Docs** kiểm tra và mô tả operation đã được test; **optional()** không sửa binding của ứng dụng.

Không dùng **.optional()** để che việc controller khai báo cookie bắt buộc. Điều đó tạo ra tài liệu nói rằng client có thể bỏ cookie trong khi ứng dụng thực tế trả lỗi.

## 6. Cookie response có mặc định hay có điều kiện phát hành

Tính bắt buộc/tùy chọn cũng có thể áp dụng cho cookie **response** theo cách diễn đạt hợp đồng: server luôn trả cookie hay chỉ trả trong một số trường hợp?

Ví dụ server luôn phát hành **display-mode**:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Chế độ giao diện server luôn trả về sau khi lưu tùy chọn")
)
~~~

Nếu cookie chỉ được phát hành khi client yêu cầu ghi nhớ tùy chọn:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Chế độ giao diện; chỉ phát hành khi client chọn lưu")
        .optional()
)
~~~

Test cần xác minh từng trường hợp có và không có **Set-Cookie**. **optional()** chỉ mô tả sự hiện diện không bắt buộc của cookie trong operation; điều kiện phát hành vẫn thuộc logic ứng dụng và phải được nêu trong tài liệu.

## 7. Ví dụ hoàn chỉnh với MockMvc

Ví dụ dùng **Java 17+**, **Spring Boot 3.x**, **JUnit 5** và **spring-restdocs-mockmvc**.

### 7.1. Controller

~~~java
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/api/profile")
    ProfileResponse getProfile(
            @CookieValue(name = "locale", defaultValue = "vi") String locale) {
        return new ProfileResponse("Lan", locale);
    }
}

record ProfileResponse(String name, String locale) {}
~~~

### 7.2. Test tài liệu hóa request có cookie và request dùng mặc định

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
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProfileController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProfileLocaleDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentProfileWithLocaleCookie() throws Exception {
        mockMvc.perform(get("/api/profile")
                .cookie(new Cookie("locale", "en"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.locale").value("en"))
            .andDo(document("profile-with-locale",
                requestCookies(
                    cookieWithName("locale")
                        .description("Mã ngôn ngữ; mặc định vi nếu không gửi")
                        .optional()
                )
            ));
    }

    @Test
    void documentProfileWithDefaultLocale() throws Exception {
        mockMvc.perform(get("/api/profile")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.locale").value("vi"))
            .andDo(document("profile-default-locale",
                requestCookies(
                    cookieWithName("locale")
                        .description("Mã ngôn ngữ; mặc định vi nếu không gửi")
                        .optional()
                )
            ));
    }
}
~~~

Hai test chứng minh hai tình huống của cùng một contract:

- Khi gửi **locale=en**, response sử dụng **en**.
- Khi bỏ cookie, response sử dụng **vi**.

**requestCookies(...)** mô tả cookie tùy chọn; test mặc định không thêm **.cookie(...)**, do đó request thực sự không chứa cookie. Khi dùng phiên bản REST Docs có kiểm tra descriptor cookie nghiêm ngặt, xác nhận hành vi **optional()** bằng cách chạy test và xem snippet được tạo.

### 7.3. Trường hợp cookie bắt buộc

Nếu đổi controller sang:

~~~java
@CookieValue(name = "locale") String locale
~~~

thì test có cookie vẫn thành công, nhưng test không có cookie cần assert lỗi binding. Trong tài liệu thành công, bỏ **.optional()** khỏi descriptor:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Mã ngôn ngữ bắt buộc của client")
)
~~~

Không dùng descriptor tùy chọn cho endpoint này, vì nó sẽ mô tả sai khả năng gọi API.

## 8. Kết hợp cookies với headers và response body

Một operation có thể tài liệu hóa cookie, header và JSON response cùng lúc:

~~~java
document("profile-get",
    requestHeaders(
        headerWithName("Accept")
            .description("Kiểu nội dung response client chấp nhận")
    ),
    requestCookies(
        cookieWithName("locale")
            .description("Mã ngôn ngữ; mặc định vi nếu không gửi")
            .optional()
    ),
    responseCookies(
        cookieWithName("display-mode")
            .description("Chế độ hiển thị server trả về nếu người dùng đã lưu")
            .optional()
    ),
    responseFields(
        fieldWithPath("name").description("Tên người dùng"),
        fieldWithPath("locale").description("Ngôn ngữ áp dụng cho response")
    )
)
~~~

Imports cần thiết:

~~~java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
~~~

Chỉ đánh dấu **.optional()** khi endpoint thực sự cho phép cookie vắng mặt hoặc không phát hành cookie ở một số response. Nếu cookie không thể thiếu, hãy giữ descriptor bắt buộc.

## 9. Tích hợp snippet vào Asciidoctor và CI

Với hai test ở mục 7, thư mục snippets dự kiến:

~~~text
build/generated-snippets/
├── profile-with-locale/
│   ├── request-cookies.adoc
│   └── http-response.adoc
└── profile-default-locale/
    ├── request-cookies.adoc
    └── http-response.adoc
~~~

Trong **src/docs/asciidoc/profile.adoc**:

~~~asciidoc
= Profile API
:toc: left

== Gửi cookie locale

GET /api/profile

include::{snippets}/profile-with-locale/request-cookies.adoc[]
include::{snippets}/profile-with-locale/http-response.adoc[]

== Không gửi locale: sử dụng mặc định

GET /api/profile

include::{snippets}/profile-default-locale/request-cookies.adoc[]
include::{snippets}/profile-default-locale/http-response.adoc[]
~~~

Ví dụ Gradle Groovy DSL, giả định plugin **org.asciidoctor.jvm.convert** đã được cấu hình:

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

Trong CI, chạy test trước khi dựng Asciidoctor. Nếu controller đổi từ cookie tùy chọn sang bắt buộc mà test vắng cookie vẫn mong đợi 200, assertion sẽ phát hiện hợp đồng đã thay đổi. Nếu descriptor vẫn đánh dấu optional khi code đã yêu cầu cookie, review và test cần cập nhật đồng bộ.

Nếu xuất bản Markdown, cần bộ chuyển đổi hoặc phương pháp include tương thích. **include::{snippets}/...[]** là cú pháp Asciidoctor, không phải cú pháp Markdown tiêu chuẩn.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Thiếu cookie trả 400 ngoài dự kiến | **@CookieValue** mặc định **required=true** | Dùng **required=false** hoặc **defaultValue** nếu contract cho phép |
| Controller nhận **null** | Cookie khai báo **required=false** nhưng code chưa xử lý null | Xử lý rõ trong controller/service và test cả hai trường hợp |
| Cookie mặc định vẫn bị coi là bắt buộc | Descriptor chưa đánh dấu **.optional()** | Ghi rõ cookie có thể vắng mặt trong descriptor |
| REST Docs nói cookie tùy chọn nhưng API trả 400 | Descriptor optional không đồng bộ với **@CookieValue** bắt buộc | Sửa code hoặc descriptor theo contract đúng |
| Tài liệu ghi mặc định vi nhưng response là giá trị khác | Không có assertion xác nhận default | Test request không cookie và assert response |
| Đánh dấu optional nhưng cookie luôn được gửi trong mọi test | Chưa kiểm thử kịch bản vắng mặt | Thêm test request không có cookie |
| Cookie response không xuất hiện | Code không phát hành cookie trong response | Kiểm tra **addCookie/Set-Cookie** và matcher |
| Cookie bị thiếu trong bảng | Sai tên descriptor hoặc đặt ở sai nhóm | Đối chiếu cookie thật và dùng requestCookies/responseCookies phù hợp |

## 11. Bài thực hành

Thiết kế endpoint:

~~~text
GET /api/catalog
~~~

Hợp đồng:

- Cookie **locale** là tùy chọn.
- Nếu có **locale=vi** hoặc **locale=en**, response dùng đúng ngôn ngữ đó.
- Nếu không có cookie, ứng dụng dùng mặc định **vi**.
- Cookie sai giá trị ngoài tập cho phép trả lỗi theo contract do bạn chọn và mô tả rõ.

Yêu cầu:

1. Viết controller dùng **@CookieValue(name = "locale", defaultValue = "vi")**.
2. Viết MockMvc test có cookie **en**, xác nhận response dùng **en**.
3. Viết test không có cookie, xác nhận response dùng **vi**.
4. Dùng **requestCookies(cookieWithName("locale").description(...).optional())** để mô tả cookie tùy chọn.
5. Viết test cho cookie sai giá trị và assert status/payload lỗi.
6. Sinh snippet cho hai tình huống có cookie và dùng mặc định.
7. Include snippet trong Asciidoctor và chạy test → Asciidoctor trong CI.

Mẫu descriptor:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Mã ngôn ngữ; chấp nhận vi hoặc en, mặc định vi khi vắng mặt")
        .optional()
)
~~~

**Tiêu chí hoàn thành:** controller xử lý đúng cookie có/không có; test chứng minh giá trị mặc định; descriptor phản ánh tính tùy chọn; lỗi cookie không hợp lệ được kiểm thử; snippet và tài liệu được dựng thành công.

## Ghi nhớ

Cookie bắt buộc thường dùng **@CookieValue** với **required=true** (mặc định) và descriptor không có **.optional()**. Cookie tùy chọn có thể dùng **required=false**, còn cookie có giá trị mặc định dùng **defaultValue**; cả hai trường hợp có thể dùng **.optional()** trong descriptor vì cookie có thể vắng mặt. **.optional() chỉ điều khiển việc kiểm tra/tài liệu hóa của Spring REST Docs, không thay đổi binding trong Spring MVC.** Hãy viết test cả trường hợp có cookie và vắng cookie, assert giá trị mặc định hoặc lỗi tương ứng, rồi include snippet vào Asciidoctor và build/CI.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs CookieDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/cookies/CookieDocumentation.html), [Spring MVC @CookieValue](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/cookievalue.html) và [RFC 6265: HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265).
