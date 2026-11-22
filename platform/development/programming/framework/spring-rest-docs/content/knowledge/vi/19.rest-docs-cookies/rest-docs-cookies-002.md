# Document response cookies bằng responseCookies

## Mục tiêu bài học

Server có thể gửi cookie về client để lưu tùy chọn, duy trì phiên hoặc hỗ trợ một quy trình bảo mật. Trong HTTP, server phát hành cookie bằng header **Set-Cookie**. Khi tài liệu hóa response bằng **Spring REST Docs**, ta cần mô tả cookie nào được tạo, mục đích của nó và cách client xử lý những thuộc tính đi kèm.

Bài học thuộc chương **Cookies** của module **SPRING_REST_DOCS**: xây dựng tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn tài liệu Asciidoctor/Markdown và đưa vào build, CI.

Sau bài này, bạn có thể:

- Dùng **responseCookies(...)** và **cookieWithName(...)** để mô tả cookie server trả về.
- Phân biệt bảng cookie snippet với header **Set-Cookie** trong HTTP response.
- Kiểm tra cookie, giá trị và các thuộc tính như **Path**, **HttpOnly**, **Secure**, **Max-Age**.
- Tài liệu hóa cookie mới, cookie cập nhật và cookie bị xóa.
- Dùng MockMvc để xác nhận response cookie và sinh snippet **response-cookies.adoc**.
- Giữ session ID, token và dữ liệu nhạy cảm khỏi tài liệu công khai.
- Nhúng cookie snippet vào Asciidoctor và đảm bảo CI tái tạo tài liệu từ bài kiểm thử.

## 1. Response cookie được server gửi như thế nào?

Khi muốn tạo hoặc cập nhật cookie, server gửi một hoặc nhiều header **Set-Cookie** trong response. Ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: display-mode=compact; Path=/; Max-Age=3600; Secure; HttpOnly; SameSite=Lax

{"message":"Preferences saved"}
~~~

Header **Set-Cookie** có một cặp tên/giá trị và các thuộc tính điều khiển cách client lưu, gửi và hết hạn cookie. Với ví dụ trên:

| Thành phần | Ý nghĩa |
| --- | --- |
| **display-mode=compact** | Tên cookie và giá trị server phát hành |
| **Path=/** | Cookie áp dụng cho các request trong phạm vi path tương ứng |
| **Max-Age=3600** | Thời hạn tối đa 3.600 giây kể từ lúc nhận |
| **Secure** | Client chỉ gửi cookie qua kết nối bảo mật theo quy tắc cookie |
| **HttpOnly** | JavaScript phía trình duyệt không đọc cookie qua API như document.cookie |
| **SameSite=Lax** | Chính sách gửi cookie trong một số ngữ cảnh cross-site |

Cookie ở response khác cookie ở request:

| Hướng truyền | HTTP header | Spring REST Docs |
| --- | --- | --- |
| Client → server | **Cookie** | **requestCookies(...)** |
| Server → client | **Set-Cookie** | **responseCookies(...)** |

Cookie được truyền qua header, nhưng khi cần mô tả từng cookie theo tên, hãy dùng API **CookieDocumentation**. **responseHeaders(...)** vẫn hữu ích khi muốn mô tả các header khác như **Cache-Control**, **Location** hoặc **Content-Type**.

## 2. responseCookies(...) và cookieWithName(...)

Spring REST Docs cung cấp API để khai báo cookie server trả về:

~~~java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
~~~

Ví dụ:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Chế độ hiển thị được lưu cho lần truy cập sau")
)
~~~

Vai trò:

- **cookieWithName("display-mode")** tạo descriptor cho cookie có tên **display-mode**.
- **description(...)** giải thích ý nghĩa của cookie trong hợp đồng API.
- **responseCookies(...)** yêu cầu REST Docs tạo snippet mô tả các cookie của response.

Một response có nhiều cookie thì truyền nhiều descriptor:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Chế độ hiển thị đã lưu"),
    cookieWithName("locale")
        .description("Ngôn ngữ được dùng cho các lần truy cập tiếp theo")
)
~~~

Tên trong descriptor phải khớp với tên cookie thực tế được gửi trong response. **responseCookies(...)** không tự tạo cookie; controller/filter phải thêm cookie vào response và bài kiểm thử phải thực sự nhận được nó.

### 2.1. Snippet response-cookies.adoc

Khi test gọi:

~~~java
document("profile-save",
    responseCookies(
        cookieWithName("display-mode")
            .description("Chế độ hiển thị đã lưu")
    )
)
~~~

REST Docs sinh snippet **response-cookies.adoc** trong thư mục:

~~~text
build/generated-snippets/
└── profile-save/
    └── response-cookies.adoc
~~~

Đây là bảng tên cookie và mô tả theo descriptor. **http-response.adoc** là snippet khác, thể hiện HTTP status, header và response body. Hai snippet bổ sung cho nhau: một cái trình bày hợp đồng cookie, cái còn lại cho thấy response HTTP được quan sát.

Giá trị cookie và thuộc tính **Set-Cookie** có thể xuất hiện trong snippet HTTP response mặc định. Vì vậy, trước khi xuất bản, hãy kiểm tra cả **response-cookies.adoc** lẫn **http-response.adoc**, đặc biệt với session cookie.

## 3. Tạo cookie trong Spring MVC

Ví dụ sử dụng **Java 17+**, **Spring Boot 3.x**, Spring MVC và servlet API. Endpoint lưu tùy chọn hiển thị rồi gửi cookie về client:

~~~java
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PreferenceController {

    @PostMapping(
        path = "/api/preferences",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    PreferenceResponse save(
            @RequestBody PreferenceRequest request,
            HttpServletResponse response) {

        Cookie displayMode =
            new Cookie("display-mode", request.displayMode());
        displayMode.setPath("/");
        displayMode.setHttpOnly(true);
        displayMode.setSecure(true);
        displayMode.setMaxAge(3600);
        response.addCookie(displayMode);

        return new PreferenceResponse("saved");
    }
}

record PreferenceRequest(String displayMode) {}
record PreferenceResponse(String status) {}
~~~

Response thành công có JSON body và header **Set-Cookie**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: display-mode=compact; Path=/; Max-Age=3600; Secure; HttpOnly

{"status":"saved"}
~~~

Ví dụ dùng **jakarta.servlet.http.Cookie** để minh họa các thuộc tính servlet thường dùng. Thuộc tính **SameSite** không có setter chuẩn trong API Cookie Servlet cơ bản; nếu ứng dụng cần thuộc tính này, hãy dùng cơ chế cấu hình cookie/header phù hợp với phiên bản Spring và servlet container, sau đó kiểm tra header Set-Cookie thực tế.

Trong sản phẩm, hãy validation giá trị **displayMode** theo danh sách được phép như **compact** hoặc **comfortable**. Không đưa dữ liệu bất kỳ từ client vào cookie mà không kiểm tra kích thước và định dạng.

## 4. Kiểm thử response cookie với MockMvc

Thêm dependency nếu dự án chưa có:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Giả định Spring Boot BOM/dependency management quản lý các phiên bản tương thích. Test dưới đây đặt cùng package với **PreferenceController**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.cookie;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PreferenceController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class PreferenceCookieDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentDisplayModeResponseCookie() throws Exception {
        mockMvc.perform(post("/api/preferences")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"displayMode":"compact"}
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("saved"))
            .andExpect(cookie().value("display-mode", "compact"))
            .andExpect(cookie().httpOnly("display-mode", true))
            .andExpect(cookie().secure("display-mode", true))
            .andExpect(cookie().path("display-mode", "/"))
            .andDo(document("preference-save",
                responseCookies(
                    cookieWithName("display-mode")
                        .description("Chế độ hiển thị đã lưu cho lần truy cập sau")
                )
            ));
    }
}
~~~

Trong test:

1. **POST /api/preferences** gửi JSON yêu cầu lưu tùy chọn.
2. Controller gọi **response.addCookie(...)** để đưa cookie vào response.
3. Các matcher **cookie()** xác nhận giá trị và một số thuộc tính quan trọng.
4. **responseCookies(...)** mô tả cookie bằng snippet riêng.
5. **document("preference-save", ...)** ghi operation và tạo các snippet liên quan.

Các matcher cookie của MockMvc hữu ích để xác minh giá trị, path, domain, max-age, secure, httpOnly và version khi API hỗ trợ. Với thuộc tính không có matcher tương ứng hoặc khác biệt container, kiểm tra header **Set-Cookie** thực tế bằng **header().string(...)** hoặc lấy response rồi xác nhận thuộc tính phù hợp.

### 4.1. Kết quả snippet

Thư mục output dự kiến:

~~~text
build/generated-snippets/
└── preference-save/
    ├── http-request.adoc
    ├── http-response.adoc
    └── response-cookies.adoc
~~~

Các snippet mặc định và snippet payload bổ sung phụ thuộc cấu hình document. **response-cookies.adoc** chứa bảng mô tả tên cookie; **http-response.adoc** cho thấy header **Set-Cookie** và body đã quan sát. Không chỉnh sửa trực tiếp snippet đã sinh vì lần chạy test sau sẽ tạo lại chúng.

## 5. Tài liệu hóa nhiều response cookie

Nếu response thiết lập **display-mode** và **locale**, hãy khai báo đủ hai descriptor:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Chế độ hiển thị được lưu"),
    cookieWithName("locale")
        .description("Ngôn ngữ dùng cho các request tiếp theo")
)
~~~

Test phải tạo cả hai cookie. Ví dụ:

~~~java
Cookie displayMode = new Cookie("display-mode", "compact");
displayMode.setPath("/");
response.addCookie(displayMode);

Cookie locale = new Cookie("locale", "vi");
locale.setPath("/");
response.addCookie(locale);
~~~

Mỗi cookie có thể có thuộc tính khác nhau. Hãy kiểm thử những thuộc tính thuộc hợp đồng, không giả định rằng mô tả trong **description(...)** tự xác nhận **Path**, **Secure** hoặc **HttpOnly**.

### 5.1. Cookie có thể tùy chọn theo response

Một endpoint có thể chỉ phát hành cookie khi người dùng chọn ghi nhớ tùy chọn. Khi đó response của một số kịch bản không có cookie. Descriptor có thể dùng **optional()** nếu cookie không xuất hiện trong mọi request/response được tài liệu hóa:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Chế độ hiển thị; chỉ được tạo khi người dùng lưu tùy chọn")
        .optional()
)
~~~

**optional()** chỉ mô tả rằng cookie có thể vắng mặt trong operation được REST Docs kiểm tra. Nó không khiến controller tự tạo cookie hoặc quyết định khi nào cookie được phát hành. Hãy có test riêng cho trường hợp có và không có cookie, đồng thời mô tả rõ điều kiện phát hành trong tài liệu.

## 6. Cập nhật và xóa cookie

### 6.1. Cập nhật cookie

Để cập nhật cookie, server gửi **Set-Cookie** mới với cùng tên và phạm vi áp dụng, nhưng giá trị hoặc thuộc tính mới. Ví dụ đổi chế độ hiển thị:

~~~java
Cookie preference = new Cookie("display-mode", "comfortable");
preference.setPath("/");
preference.setHttpOnly(true);
preference.setSecure(true);
preference.setMaxAge(3600);
response.addCookie(preference);
~~~

Có thể tài liệu hóa response mới với cùng descriptor:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Chế độ hiển thị hiện tại được server lưu")
)
~~~

Nếu cùng endpoint có thể trả các giá trị cookie khác nhau theo request, hãy có test cho mỗi hành vi cần công bố. Bảng descriptor mô tả cookie; test và response snippet cho thấy giá trị/thuộc tính cụ thể trong từng tình huống.

### 6.2. Xóa cookie

Server thường yêu cầu client xóa cookie bằng cách gửi lại tên và phạm vi tương ứng, đặt giá trị rỗng và **Max-Age=0** hoặc thời điểm **Expires** đã qua:

~~~java
Cookie expired = new Cookie("display-mode", "");
expired.setPath("/");
expired.setMaxAge(0);
response.addCookie(expired);
~~~

Cookie được nhận diện theo phạm vi, vì vậy **Path** và **Domain** cần tương thích với cookie ban đầu. Nếu cookie cũ được đặt cho **Path=/** nhưng response xóa lại gửi phạm vi khác, client có thể giữ cookie cũ.

Test có thể xác nhận response phát hành cookie hết hạn:

~~~java
mockMvc.perform(delete("/api/preferences/display-mode"))
    .andExpect(status().isNoContent())
    .andExpect(cookie().maxAge("display-mode", 0))
    .andDo(document("preference-delete-cookie",
        responseCookies(
            cookieWithName("display-mode")
                .description("Cookie chế độ hiển thị được xóa bằng Max-Age=0")
        )
    ));
~~~

Đây là phần trích cho endpoint DELETE giả định. Cần import **MockMvcRequestBuilders.delete** và xây dựng controller tương ứng. Nếu response xóa cookie không có body, vẫn có thể tài liệu hóa response cookie và status HTTP.

## 7. Thuộc tính cookie và cách tài liệu hóa

Cookie snippet chủ yếu mô tả tên và ý nghĩa của cookie. Các thuộc tính thường được thể hiện qua header **Set-Cookie** trong **http-response.adoc**. Khi cần hướng dẫn chi tiết, bổ sung mô tả bằng văn bản và test xác nhận giá trị thực tế.

| Thuộc tính | Ý nghĩa | Điều nên kiểm tra |
| --- | --- | --- |
| **Path** | Phạm vi đường dẫn áp dụng | Client có gửi cookie ở endpoint cần dùng không? |
| **Domain** | Phạm vi host áp dụng | Host/subdomain được cấu hình đúng không? |
| **Max-Age** | Thời gian tồn tại tính bằng giây | Cookie có hết hạn đúng thời điểm mong muốn không? |
| **Expires** | Thời điểm hết hạn | Có cùng ý nghĩa với chính sách vòng đời cookie không? |
| **Secure** | Chỉ gửi qua kết nối bảo mật | Môi trường production dùng HTTPS chưa? |
| **HttpOnly** | Không cho JavaScript đọc qua API thông thường | Có cần hạn chế truy cập từ script không? |
| **SameSite** | Chính sách gửi trong ngữ cảnh cross-site | Luồng đăng nhập/redirect có hoạt động theo thiết kế không? |

**SameSite** thường có các giá trị **Strict**, **Lax** hoặc **None**. Nếu dùng **SameSite=None**, cookie cần đáp ứng yêu cầu **Secure** của các trình duyệt hiện đại. Hành vi trình duyệt có thể phụ thuộc phiên bản và ngữ cảnh; đừng chỉ dựa vào MockMvc để kết luận luồng cross-site hoạt động thực tế.

### 7.1. Cookie Servlet và ResponseCookie

**jakarta.servlet.http.Cookie** thuận tiện cho ứng dụng Spring MVC chạy trên Servlet. API này không cung cấp setter tiêu chuẩn cho mọi thuộc tính cookie hiện đại như SameSite.

Spring cũng có **org.springframework.http.ResponseCookie** để xây dựng cookie dưới dạng header:

~~~java
import org.springframework.http.ResponseCookie;

ResponseCookie cookie = ResponseCookie.from("display-mode", "compact")
    .path("/")
    .httpOnly(true)
    .secure(true)
    .sameSite("Lax")
    .maxAge(3600)
    .build();

response.addHeader("Set-Cookie", cookie.toString());
~~~

Đoạn này minh họa khả năng khai báo thuộc tính bằng **ResponseCookie**; kiểm tra method và phiên bản Spring Framework thực tế của dự án. Không thêm đồng thời một servlet Cookie cùng tên nếu không muốn response phát ra hai header Set-Cookie khác nhau.

## 8. Bảo mật giá trị cookie trong tài liệu

Response cookie có thể chứa **session ID**, refresh token hoặc giá trị xác thực. Các giá trị đó không được đưa vào tài liệu hoặc commit như fixture thật.

Nguyên tắc:

1. Dùng cookie giả lập trong test, ví dụ **test-session-placeholder**, không dùng session production.
2. Kiểm tra cả **response-cookies.adoc** và **http-response.adoc** vì giá trị cookie có thể xuất hiện ở cả bảng và header thô.
3. Nếu cần che giá trị, sử dụng preprocessing phù hợp hoặc thiết kế fixture không chứa bí mật.
4. Không bỏ toàn bộ mô tả cookie xác thực nếu client cần biết cơ chế gửi cookie; thay vào đó mô tả tên, mục đích và thuộc tính mà không công bố giá trị.
5. Không ghi token, session ID, thông tin cá nhân vào log test hoặc output CI.

Ví dụ chỉ mô tả cookie session:

~~~java
responseCookies(
    cookieWithName("SESSION")
        .description("Cookie phiên do server quản lý; client gửi lại tự động")
)
~~~

Giá trị thật do server sinh có thể cần được thay thế trong bản ghi operation trước khi sinh snippet. Sau preprocessing, vẫn phải kiểm tra các snippet cuối để bảo đảm không còn dữ liệu nhạy cảm.

## 9. Kết hợp responseCookies với header và response fields

Một operation có thể mô tả cookie, header và JSON body cùng lúc:

~~~java
document("preference-save",
    responseCookies(
        cookieWithName("display-mode")
            .description("Chế độ hiển thị được lưu")
    ),
    responseHeaders(
        headerWithName("Cache-Control")
            .description("Chính sách cache của response")
    ),
    responseFields(
        fieldWithPath("status")
            .description("Kết quả lưu tùy chọn")
    )
)
~~~

Các static import:

~~~java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
~~~

Không mô tả **Set-Cookie** bằng **responseCookies(...)** và **responseHeaders(...)** như thể chúng là hai cookie khác nhau. Cookie descriptor mô tả tên cookie; response header snippet là nơi thể hiện header HTTP đã quan sát.

## 10. Nhúng snippet response cookie vào Asciidoctor và CI

Sau khi test sinh snippet **preference-save**, có thể nhúng vào **src/docs/asciidoc/index.adoc**:

~~~asciidoc
= Preference API
:toc: left

== Lưu chế độ hiển thị

POST /api/preferences

=== Response cookies

include::{snippets}/preference-save/response-cookies.adoc[]

=== HTTP response

include::{snippets}/preference-save/http-response.adoc[]
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

Tác vụ Asciidoctor phụ thuộc vào test nên snippet được tạo trước khi include. Trong CI, chỉ xuất bản tài liệu sau khi test REST Docs và dựng tài liệu thành công. Nếu cookie bị xóa khỏi response, descriptor bị khai báo sai tên hoặc include trỏ nhầm snippet ID, pipeline cần phát hiện lỗi thay vì phát hành tài liệu thiếu.

Nếu tài liệu cuối là Markdown, dùng công cụ chuyển đổi hoặc cơ chế nhúng snippet phù hợp. **include::{snippets}/...[]** là cú pháp Asciidoctor, không phải Markdown tiêu chuẩn.

## 11. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Không có **response-cookies.adoc** | Chưa khai báo **responseCookies(...)** hoặc operation không sinh descriptor | Thêm descriptor vào đúng **document(...)** và chạy lại test |
| Descriptor báo cookie không tồn tại | Tên cookie sai hoặc response không gửi cookie | Đối chiếu **Set-Cookie** thực tế và tên trong **cookieWithName(...)** |
| Cookie snippet có nhưng HTTP response không như mong đợi | Chỉ khai báo descriptor, chưa tạo cookie trong controller | Dùng **response.addCookie(...)** hoặc thêm Set-Cookie |
| Cookie giá trị đúng nhưng thiếu thuộc tính | Chưa cấu hình Path, Secure, HttpOnly, Max-Age | Thiết lập thuộc tính và assert trong test |
| Cookie xóa nhưng browser vẫn lưu | Path/Domain không khớp cookie cũ | Gửi cookie hết hạn với cùng phạm vi |
| Session ID xuất hiện trong tài liệu | Giá trị response thật bị ghi vào snippet HTTP | Dùng fixture giả hoặc preprocessing và kiểm tra mọi output |
| Cross-site request không gửi cookie | SameSite/Secure hoặc chính sách trình duyệt không phù hợp | Kiểm thử trên browser và HTTPS theo contract |
| Có hai cookie cùng tên ngoài ý muốn | Vừa add Servlet Cookie vừa thêm ResponseCookie cùng tên | Chọn một cơ chế tạo Set-Cookie cho mỗi cookie |
| Asciidoctor không tìm thấy response cookie snippet | Test chưa chạy hoặc sai snippet ID | Kiểm tra document identifier, output dir và task dependency |

## 12. Bài thực hành

Xây dựng endpoint ghi nhớ lựa chọn giao diện:

~~~text
POST /api/preferences
DELETE /api/preferences/display-mode
~~~

Hợp đồng:

- POST nhận JSON **{"displayMode":"compact"}**.
- Response POST trả HTTP 200 và thiết lập cookie **display-mode**.
- Cookie có **Path=/**, **HttpOnly**, **Secure**, **Max-Age=3600**.
- DELETE trả HTTP 204 và phát hành lại cookie **display-mode** với **Max-Age=0**.

Yêu cầu:

1. Viết controller dùng **HttpServletResponse.addCookie(...)** hoặc **ResponseCookie**.
2. Viết MockMvc test cho POST; assert status, response body, cookie value và thuộc tính.
3. Dùng **responseCookies(cookieWithName("display-mode")...)** để sinh snippet **preference-save/response-cookies.adoc**.
4. Viết test DELETE; assert HTTP 204 và Max-Age=0; sinh snippet **preference-delete-cookie/response-cookies.adoc**.
5. Tạo tài liệu Asciidoctor có hai section mô tả cookie được tạo và cookie bị xóa.
6. Kiểm tra **http-response.adoc** không chứa token/session ID thật.
7. Nối test và Asciidoctor trong Gradle/CI, xác nhận thay đổi thuộc tính cookie làm test thất bại khi không còn đúng hợp đồng.

Mẫu descriptor:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Chế độ hiển thị được lưu ở client; hết hạn sau một giờ")
)
~~~

**Tiêu chí hoàn thành:** response cookie được tạo đúng; test xác nhận tên, giá trị và thuộc tính; cookie hết hạn được kiểm tra; snippet được sinh và nhúng đúng operation; tài liệu không làm lộ giá trị bí mật.

## Ghi nhớ

**responseCookies(...)** dùng để tài liệu hóa cookie server trả về, còn **cookieWithName(...)** xác định từng tên cookie và **description(...)** giải thích mục đích. Hãy tạo cookie trong response, kiểm tra giá trị và thuộc tính bằng MockMvc, rồi dùng descriptor để sinh **response-cookies.adoc**. Với cookie cập nhật hoặc xóa, kiểm tra cả phạm vi và thời hạn. Giá trị session/token phải được giả lập hoặc che trước khi xuất bản. Cuối cùng include cookie snippet và HTTP response vào Asciidoctor, để build/CI luôn tạo tài liệu từ response đã được kiểm thử.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs CookieDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/cookies/CookieDocumentation.html), [Spring MVC @CookieValue](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/cookievalue.html), [Spring ResponseCookie API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseCookie.html) và [RFC 6265](https://www.rfc-editor.org/rfc/rfc6265).
