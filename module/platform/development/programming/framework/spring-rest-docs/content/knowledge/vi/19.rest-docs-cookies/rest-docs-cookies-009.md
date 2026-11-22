# Kiểm tra cookie trong MockMvc hoặc REST Assured

## Mục tiêu bài học

Cookie là một phần của hợp đồng HTTP: client có thể gửi cookie trong request và server có thể phát hành, cập nhật hoặc xóa cookie trong response. Tài liệu chỉ đáng tin cậy khi bài kiểm thử xác nhận đúng cookie thực tế, đúng giá trị và đúng thuộc tính mà API cam kết. **MockMvc** và **REST Assured** đều có thể kiểm tra hành vi cookie; Spring REST Docs bổ sung descriptor để sinh snippet mô tả cookie.

Bài học thuộc chương **Cookies** của module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn tài liệu Asciidoctor/Markdown và tích hợp vào build, CI.

Sau bài học, bạn có thể:

- Kiểm tra cookie gửi lên bằng MockMvc và REST Assured.
- Kiểm tra cookie response về tên, giá trị, Path, Domain, Max-Age, Secure và HttpOnly.
- Xác nhận header **Cookie** và **Set-Cookie** khi cần kiểm tra wire representation.
- Kết hợp assertion cookie với **requestCookies(...)** và **responseCookies(...)**.
- Cấu hình REST Docs cho MockMvc hoặc REST Assured.
- Chọn dữ liệu test an toàn và tránh đưa session/token thật vào snippet.
- Tổ chức test cho cookie thiếu, cookie sai và cookie hết hạn.
- Tạo snippet và ghép vào Asciidoctor/CI.

## 1. Chiến lược kiểm thử cookie

Một bài kiểm thử cookie tốt nên xác nhận cả **hành vi ứng dụng** và **hợp đồng HTTP**. Tùy tình huống, hãy kiểm tra:

| Thành phần | Câu hỏi cần xác nhận | Công cụ thường dùng |
| --- | --- | --- |
| Request cookie | Client có gửi đúng tên và giá trị không? | MockMvc **.cookie(...)**; REST Assured **.cookie(...)** |
| Response cookie | Server có phát hành cookie không? | MockMvc **cookie()** matcher; REST Assured response cookie API |
| Giá trị | Giá trị cookie trả về có đúng không? | **cookie().value(...)**; **response.getCookie(...).getValue()** |
| Thuộc tính | Path, Secure, HttpOnly, Max-Age có đúng không? | Cookie matcher hoặc kiểm tra **Set-Cookie** |
| Thiếu cookie | API dùng mặc định hay trả lỗi? | Request không gắn cookie, assert status/body |
| Nhiều cookie | Tất cả cookie cần thiết đều có mặt? | Kiểm tra từng cookie và descriptor tương ứng |
| Tài liệu | Snippet phản ánh đúng cookie thực tế? | **requestCookies(...)**, **responseCookies(...)** |

Không nên chỉ assert status 200 rồi kết luận cookie đã đúng. Một API có thể trả 200 nhưng phát hành cookie thiếu Secure, sai Path hoặc có giá trị không hợp lệ.

## 2. Chuẩn bị ví dụ API

Ví dụ dùng endpoint lấy tùy chọn giao diện. Client gửi cookie **locale**; server trả cookie **display-mode**.

~~~java
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PreferenceController {

    @GetMapping(
        path = "/api/preferences",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    PreferenceResponse getPreferences(
            @CookieValue(name = "locale", defaultValue = "vi") String locale,
            HttpServletResponse response) {

        Cookie displayMode = new Cookie("display-mode", "compact");
        displayMode.setPath("/");
        displayMode.setHttpOnly(true);
        displayMode.setSecure(true);
        displayMode.setMaxAge(3600);
        response.addCookie(displayMode);

        return new PreferenceResponse(locale, "loaded");
    }
}

record PreferenceResponse(String locale, String status) {}
~~~

Đây là ví dụ Spring MVC/Servlet. Giá trị cookie là dữ liệu kiểm thử giả lập. Với session hoặc token xác thực thật, ứng dụng phải dùng cơ chế quản lý phiên an toàn; không hard-code chuỗi cố định như trên.

## 3. Kiểm tra request cookie bằng MockMvc

MockMvc cho phép gắn cookie vào request bằng **.cookie(...)**:

~~~java
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PreferenceController.class)
class PreferenceCookieMockMvcTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void readsLocaleCookie() throws Exception {
        mockMvc.perform(get("/api/preferences")
                .cookie(new Cookie("locale", "en"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.locale").value("en"));
    }
}
~~~

Request phải gửi đúng **cookie name** mà controller đọc qua **@CookieValue**. Nếu gửi **language=en** thay cho **locale=en**, Spring không bind được cookie mong muốn và có thể dùng defaultValue hoặc trả lỗi tùy khai báo controller.

### 3.1. Kiểm tra nhiều cookie request

MockMvc nhận nhiều đối tượng Cookie trong một lần gọi:

~~~java
mockMvc.perform(get("/api/preferences")
        .cookie(
            new Cookie("locale", "en"),
            new Cookie("display-mode", "compact")
        ))
    .andExpect(status().isOk());
~~~

Nếu endpoint sử dụng cả hai cookie, thêm assertion cho hành vi tương ứng. Nếu chỉ **locale** thuộc contract endpoint còn **display-mode** là cookie do client khác gửi, đừng mô tả nó như input được API cam kết xử lý.

## 4. Kiểm tra response cookie bằng MockMvc

MockMvc cung cấp **MockMvcResultMatchers.cookie()** để xác minh cookie response.

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.cookie;

@Test
void returnsDisplayModeCookieWithExpectedAttributes() throws Exception {
    mockMvc.perform(get("/api/preferences")
            .cookie(new Cookie("locale", "vi"))
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(cookie().exists("display-mode"))
        .andExpect(cookie().value("display-mode", "compact"))
        .andExpect(cookie().path("display-mode", "/"))
        .andExpect(cookie().httpOnly("display-mode", true))
        .andExpect(cookie().secure("display-mode", true))
        .andExpect(cookie().maxAge("display-mode", 3600));
}
~~~

Những matcher thường dùng:

| Matcher | Mục đích |
| --- | --- |
| **exists(name)** | Cookie có xuất hiện trong response |
| **value(name, value)** | Giá trị cookie đúng |
| **path(name, path)** | Path đúng |
| **domain(name, domain)** | Domain đúng |
| **maxAge(name, seconds)** | Thời hạn đúng |
| **secure(name, true)** | Có flag Secure |
| **httpOnly(name, true)** | Có flag HttpOnly |

Tên matcher và overload có thể khác giữa các phiên bản Spring Test. Hãy dùng API của phiên bản dependency trong dự án và kiểm tra Javadoc tương ứng.

### 4.1. Kiểm tra SameSite qua Set-Cookie

MockMvc matcher không có matcher SameSite chuyên biệt trong mọi phiên bản. Có thể kiểm tra header do server phát hành:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

mockMvc.perform(get("/api/preferences"))
    .andExpect(header().string(
        "Set-Cookie",
        containsString("SameSite=Lax")
    ));
~~~

Nếu response có nhiều cookie, có thể có nhiều header **Set-Cookie**. Đừng giả định matcher header luôn kiểm tra đúng cookie; hãy lấy danh sách header và xác nhận header có tên cookie tương ứng:

~~~java
MvcResult result = mockMvc.perform(get("/api/preferences"))
    .andExpect(status().isOk())
    .andReturn();

List<String> setCookieHeaders =
    result.getResponse().getHeaders("Set-Cookie");

assertThat(setCookieHeaders)
    .anySatisfy(value -> {
        assertThat(value).contains("display-mode=compact");
        assertThat(value).contains("SameSite=Lax");
    });
~~~

Đoạn trên dùng AssertJ. Cần import **MvcResult**, **List** và assertion tương ứng khi ghép vào test class. Kiểm tra header xác nhận server phát hành thuộc tính, nhưng chưa chứng minh browser áp dụng chính sách cross-site như mong muốn.

## 5. Sinh cookie snippet bằng Spring REST Docs với MockMvc

Sau khi assertion đã xác nhận request/response, thêm descriptor để sinh snippet:

~~~java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;

mockMvc.perform(get("/api/preferences")
        .cookie(new Cookie("locale", "en"))
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.locale").value("en"))
    .andExpect(cookie().value("display-mode", "compact"))
    .andDo(document("preferences-get",
        requestCookies(
            cookieWithName("locale")
                .description("Mã ngôn ngữ client mong muốn; mặc định vi nếu vắng mặt")
        ),
        responseCookies(
            cookieWithName("display-mode")
                .description("Chế độ giao diện server ghi nhớ cho lần truy cập sau")
        )
    ));
~~~

Với cấu hình **@AutoConfigureRestDocs**, snippet thường được tạo ở:

~~~text
build/generated-snippets/
└── preferences-get/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-cookies.adoc
    └── response-cookies.adoc
~~~

**request-cookies.adoc** mô tả cookie **locale**; **response-cookies.adoc** mô tả **display-mode**. Snippet HTTP request/response ghi lại nội dung operation quan sát được, có thể chứa giá trị cookie và Set-Cookie. Hãy kiểm tra dữ liệu trước khi xuất bản.

### 5.1. Cấu hình test tài liệu hóa

~~~java
@WebMvcTest(PreferenceController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class PreferenceCookieDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentsRequestAndResponseCookies() throws Exception {
        mockMvc.perform(get("/api/preferences")
                .cookie(new Cookie("locale", "en"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.locale").value("en"))
            .andExpect(cookie().value("display-mode", "compact"))
            .andExpect(cookie().httpOnly("display-mode", true))
            .andExpect(cookie().secure("display-mode", true))
            .andDo(document("preferences-get",
                requestCookies(
                    cookieWithName("locale")
                        .description("Mã ngôn ngữ client mong muốn")
                ),
                responseCookies(
                    cookieWithName("display-mode")
                        .description("Chế độ giao diện server ghi nhớ")
                )
            ));
    }
}
~~~

Đây là phần thân của test class; các import và annotation cần có như ví dụ ở trên. Descriptor không thay thế assertion: **responseCookies(...)** không tự xác minh giá trị **compact**, Secure hoặc HttpOnly.

## 6. Kiểm thử cookie thiếu, sai và hết hạn

### 6.1. Cookie không được gửi

Nếu controller dùng **defaultValue**, kiểm tra request không có cookie:

~~~java
mockMvc.perform(get("/api/preferences")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.locale").value("vi"));
~~~

Nếu cookie là bắt buộc, test nên xác nhận lỗi theo contract:

~~~java
mockMvc.perform(get("/api/secure-profile"))
    .andExpect(status().isBadRequest());
~~~

Mã HTTP chính xác phụ thuộc exception handler. Nếu API chuyển lỗi thành response có cấu trúc, hãy thêm assertion payload và REST Docs snippet cho lỗi khi cần.

### 6.2. Cookie có giá trị không hợp lệ

Với cookie **locale**, API có thể chỉ chấp nhận **vi** hoặc **en**. Gửi giá trị không hợp lệ:

~~~java
mockMvc.perform(get("/api/preferences")
        .cookie(new Cookie("locale", "unknown")))
    .andExpect(status().isBadRequest());
~~~

Đảm bảo ứng dụng validation cookie; **@CookieValue** chỉ bind chuỗi, không tự xác thực tập giá trị nghiệp vụ. Nếu không validate, request có thể được xử lý với phản hồi khác hợp đồng mong muốn.

### 6.3. Cookie hết hạn hoặc bị xóa

Cookie được xóa thường bằng response **Set-Cookie** có cùng tên và phạm vi, cùng **Max-Age=0** hoặc Expires trong quá khứ:

~~~java
mockMvc.perform(delete("/api/preferences/display-mode"))
    .andExpect(status().isNoContent())
    .andExpect(cookie().maxAge("display-mode", 0));
~~~

Test nên xác nhận cả Path/Domain tương ứng nếu chúng là một phần hợp đồng; nếu không, browser có thể không xóa đúng cookie cũ.

## 7. Kiểm tra cookie bằng REST Assured

REST Assured cho phép gửi cookie và đọc cookie response qua fluent API. Để document với Spring REST Docs, cấu hình filter **RestAssuredRestDocumentation**.

### 7.1. Gửi cookie request

~~~java
given()
    .cookie("locale", "en")
    .when()
    .get("/api/preferences")
    .then()
    .statusCode(200)
    .body("locale", equalTo("en"));
~~~

Với nhiều cookie:

~~~java
given()
    .cookies(Map.of(
        "locale", "en",
        "display-mode", "compact"
    ))
    .when()
    .get("/api/preferences")
    .then()
    .statusCode(200);
~~~

Các import phổ biến:

~~~java
import static io.restassured.RestAssured.given;
import static org.hamcrest.Matchers.equalTo;
import java.util.Map;
~~~

### 7.2. Kiểm tra cookie response

REST Assured cho phép đọc cookie từ response:

~~~java
Response response =
    given()
        .when()
        .get("/api/preferences");

assertThat(response.getCookie("display-mode"))
    .isEqualTo("compact");
~~~

Đoạn này dùng AssertJ; cần import **io.restassured.response.Response** và assertion tương ứng. Có thể kiểm tra thêm chi tiết cookie bằng cookie API của REST Assured hoặc xác nhận header **Set-Cookie**:

~~~java
given()
    .when()
    .get("/api/preferences")
    .then()
    .statusCode(200)
    .header("Set-Cookie", containsString("display-mode=compact"))
    .header("Set-Cookie", containsString("HttpOnly"));
~~~

Khi có nhiều header Set-Cookie, nên kiểm tra tập header hoặc cookie cụ thể thay vì phụ thuộc thứ tự xuất hiện. Cách đọc giá trị cookie qua **getCookie(...)** thuận tiện cho assertion đơn giản; header phù hợp hơn khi cần xác nhận thuộc tính.

## 8. Sinh snippet với REST Assured

REST Docs tích hợp với REST Assured thông qua filter **RestAssuredRestDocumentation**. Ví dụ:

~~~java
import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;

given(spec)
    .filter(document("preferences-get-rest-assured",
        requestCookies(
            cookieWithName("locale")
                .description("Mã ngôn ngữ client mong muốn")
        ),
        responseCookies(
            cookieWithName("display-mode")
                .description("Chế độ giao diện server ghi nhớ")
        )
    ))
    .cookie("locale", "en")
    .when()
    .get("/api/preferences")
    .then()
    .statusCode(200)
    .body("locale", equalTo("en"));
~~~

**spec** là **RequestSpecification** đã cấu hình filter REST Docs theo hướng dẫn phiên bản đang dùng. Ví dụ rút gọn tập trung vào vị trí của **document(...)**; dự án cần cấu hình **RestAssuredRestDocumentation.documentationConfiguration(...)** và snippet output directory trước khi gọi test.

### 8.1. Cấu hình RestAssuredRestDocumentation

Một cấu hình thường gặp:

~~~java
@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    this.spec = new RequestSpecBuilder()
        .addFilter(documentationConfiguration(restDocumentation))
        .build();
}
~~~

Trong dự án thực tế, khai báo field **RequestSpecification spec**, thêm các import từ REST Assured và Spring REST Docs, rồi dùng extension/test lifecycle phù hợp. Tùy phiên bản REST Docs, có thể cấu hình output và snippet defaults tại documentation configuration.

## 9. Khi nào dùng MockMvc, khi nào dùng REST Assured?

| Tiêu chí | MockMvc | REST Assured |
| --- | --- | --- |
| Tích hợp Spring MVC trong test | Trực tiếp, thuận tiện với **@WebMvcTest** | Gọi endpoint qua HTTP/test server hoặc cấu hình phù hợp |
| Gửi cookie | **.cookie(new Cookie(...))** | **.cookie(...)**, **.cookies(...)** |
| Assertion response cookie | **cookie()** result matcher | **getCookie(...)**, cookie API hoặc header |
| Kiểm tra Set-Cookie | Header matcher và response result | **.header(...)**, response headers |
| REST Docs | **MockMvcRestDocumentation.document(...)** | **RestAssuredRestDocumentation.document(...)** filter |
| Phù hợp | Test controller slice và contract Spring MVC | API integration test, fluent client hoặc test HTTP độc lập |

Chọn công cụ theo tầng cần kiểm thử. MockMvc phù hợp khi muốn kiểm tra controller mà không cần server thật; REST Assured phù hợp với luồng gọi HTTP tích hợp hoặc test API qua endpoint đang chạy. Cả hai đều không thay thế browser test nếu contract phụ thuộc hành vi chính sách cookie cross-site.

## 10. Bảo vệ giá trị cookie trong test và snippet

Không dùng cookie phiên, token hoặc dữ liệu người dùng thật trong test. Ví dụ:

~~~java
new Cookie("SESSION", "test-session-placeholder")
~~~

Giá trị placeholder giúp snippet minh họa cách client gửi cookie mà không tiết lộ thông tin xác thực. Tuy nhiên, snippet **http-request.adoc** và **http-response.adoc** có thể in value, kể cả khi cookie descriptor chỉ mô tả tên. Vì vậy:

- Sử dụng session giả lập và token test vô hiệu.
- Kiểm tra toàn bộ request/response snippets trước khi xuất bản.
- Dùng operation preprocessor để thay thế/xóa giá trị nếu test cần value nhạy cảm.
- Không ghi cookie vào log khi test thất bại.
- Không nhúng cookie jar hoặc file chứa phiên người dùng vào repository.

Nếu cookie là một phần hợp đồng, giữ mô tả tên và mục đích bằng **requestCookies(...)**/**responseCookies(...)**; chỉ che giá trị bí mật. Không giả định **ignored()** trên descriptor sẽ xóa cookie khỏi tất cả snippet HTTP.

## 11. Tích hợp snippets vào Asciidoctor và CI

Sau khi chạy test, thư mục output có thể gồm:

~~~text
build/generated-snippets/
├── preferences-get/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── request-cookies.adoc
│   └── response-cookies.adoc
└── preferences-get-rest-assured/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-cookies.adoc
    └── response-cookies.adoc
~~~

Trong **src/docs/asciidoc/preferences.adoc**:

~~~asciidoc
= Preferences API
:toc: left

== Lấy tùy chọn

GET /api/preferences

=== Request cookies

include::{snippets}/preferences-get/request-cookies.adoc[]

=== Response cookies

include::{snippets}/preferences-get/response-cookies.adoc[]

=== HTTP response

include::{snippets}/preferences-get/http-response.adoc[]
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

Trong CI, chạy test trước khi dựng Asciidoctor. Test cookie sai, cookie response thiếu flag hoặc descriptor không khớp phải làm pipeline thất bại. Kiểm tra snippet output không chứa giá trị session/token thật trước khi publish.

Nếu đầu ra cuối là Markdown, cần converter hoặc cách include tương thích. **include::{snippets}/...[]** là cú pháp Asciidoctor, không phải Markdown tiêu chuẩn.

## 12. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Controller dùng default dù test đã gửi cookie | Tên cookie request sai | Đối chiếu **@CookieValue** và **.cookie(...)** |
| Response có cookie nhưng sai value | Logic phát hành hoặc test fixture sai | Assert **.value(...)**/**getCookie(...)** |
| Cookie thiếu Secure/HttpOnly | Code không cấu hình flag | Thêm matcher và kiểm tra Set-Cookie |
| SameSite assertion không ổn định | Có nhiều Set-Cookie hoặc matcher chọn header khác | Lọc đúng header theo tên cookie |
| REST Docs không sinh cookie snippet | Thiếu **requestCookies(...)**/**responseCookies(...)** | Thêm descriptor vào đúng document operation |
| Descriptor không khớp | Tên cookie hoặc hướng request/response sai | So sánh tên trong operation thực tế |
| Snippet lộ session/token | Dùng giá trị thật trong test | Dùng placeholder/preprocessor và kiểm tra output |
| MockMvc pass nhưng browser không gửi cookie | Test không mô phỏng chính sách browser cross-site | Bổ sung HTTPS browser test |
| Asciidoctor báo thiếu snippet | Sai ID hoặc test chưa chạy trước | Đồng bộ document ID, include và task dependency |

## 13. Bài thực hành

API:

~~~text
POST /api/session
GET /api/profile
DELETE /api/session
~~~

Hợp đồng:

- POST tạo session và phát hành cookie **SESSION** với HttpOnly, Secure, Path và Max-Age.
- GET yêu cầu cookie SESSION; nếu hợp lệ, trả profile.
- DELETE kết thúc session và phát hành cookie SESSION hết hạn.
- Giá trị cookie trong test chỉ là placeholder.

Yêu cầu:

1. Viết MockMvc test POST, assert cookie tồn tại, giá trị giả lập và các flag.
2. Document response cookie bằng **responseCookies(cookieWithName("SESSION")...)**.
3. Viết test GET có SESSION và test thiếu SESSION; assert đúng status/body.
4. Viết test DELETE, assert Max-Age=0 và Path khớp cookie ban đầu.
5. Viết một bài REST Assured gửi cookie SESSION và xác nhận response.
6. Tạo snippet request/response cookies cho những operation cần công bố.
7. Include snippets vào Asciidoctor và chạy test → Asciidoctor trong CI.
8. Rà soát generated snippets để bảo đảm không chứa session ID thật.

**Tiêu chí hoàn thành:** request cookie được gửi đúng; response cookie được kiểm tra về giá trị và thuộc tính; tình huống thiếu/xóa cookie được test; REST Docs sinh snippet đúng operation; tài liệu được dựng trong CI và không lộ bí mật.

## Ghi nhớ

MockMvc kiểm tra cookie thuận tiện qua **.cookie(...)** và **cookie()** matcher; REST Assured hỗ trợ **.cookie(...)**, **.cookies(...)**, **getCookie(...)** và kiểm tra header Set-Cookie. Khi tài liệu hóa, dùng **requestCookies(...)** và **responseCookies(...)** cùng assertion để bảo đảm snippet phản ánh đúng hành vi HTTP. Kiểm tra cả tình huống cookie thiếu, sai hoặc hết hạn, và xác nhận các thuộc tính bảo mật theo contract. Test mô phỏng không chứng minh đầy đủ hành vi browser cross-site; cần HTTPS browser test khi chính sách Secure/SameSite quan trọng. Dùng giá trị giả, rà soát snippet và nối test với Asciidoctor/CI để duy trì tài liệu đáng tin cậy.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs MockMvc API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/mockmvc/MockMvcRestDocumentation.html), [Spring REST Docs REST Assured API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/restassured/RestAssuredRestDocumentation.html), [Spring MockMvcResultMatchers API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/result/CookieResultMatchers.html) và [REST Assured Usage Guide](https://github.com/rest-assured/rest-assured/wiki/Usage).
