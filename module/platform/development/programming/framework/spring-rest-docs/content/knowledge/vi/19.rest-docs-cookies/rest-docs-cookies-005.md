# HttpOnly, Secure, SameSite và ý nghĩa tài liệu

## Mục tiêu bài học

Cookie có thể mang session identifier, token, lựa chọn giao diện hoặc dữ liệu cần gửi lại giữa các request. Những thuộc tính **HttpOnly**, **Secure** và **SameSite** quyết định cách trình duyệt truy cập và gửi cookie. Khi tài liệu hóa API bằng **Spring REST Docs**, chỉ ghi tên cookie là chưa đủ nếu client hoặc đội vận hành cần hiểu các đặc tính bảo mật này.

Bài học thuộc chương **Cookies** của module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn tài liệu Asciidoctor/Markdown rồi tích hợp vào build và CI.

Sau bài học, bạn có thể:

- Giải thích vai trò của **HttpOnly**, **Secure** và **SameSite**.
- Chọn cấu hình cookie phù hợp với session, xác thực hoặc tùy chọn giao diện.
- Tạo cookie bằng Servlet **Cookie** hoặc Spring **ResponseCookie**.
- Kiểm tra giá trị và thuộc tính cookie trong MockMvc test.
- Dùng **responseCookies(...)** để mô tả cookie và dùng response/header snippet để thể hiện **Set-Cookie**.
- Phân biệt bảng cookie descriptor với các thuộc tính bảo mật thực tế.
- Kiểm thử các kịch bản HTTPS, cross-site và CSRF phù hợp với hợp đồng.
- Tránh đưa giá trị session/token thật vào snippet và tích hợp tài liệu vào CI.

## 1. Ba thuộc tính bảo mật quan trọng

Khi server gửi cookie, các thuộc tính nằm trong header **Set-Cookie**. Ví dụ:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=sample-session; Path=/; HttpOnly; Secure; SameSite=Lax
Content-Type: application/json

{"status":"authenticated"}
~~~

Ba thuộc tính có vai trò khác nhau:

| Thuộc tính | Tác dụng chính | Câu hỏi cần đặt ra |
| --- | --- | --- |
| **HttpOnly** | Hạn chế JavaScript truy cập cookie qua API trình duyệt như document.cookie | Có cần ngăn script phía client đọc session cookie không? |
| **Secure** | Hướng dẫn client chỉ gửi cookie qua kết nối bảo mật | Cookie có phải chỉ được gửi qua HTTPS không? |
| **SameSite** | Kiểm soát việc gửi cookie trong các ngữ cảnh request cross-site | Cookie cần được gửi khi điều hướng hoặc request bắt nguồn từ site khác không? |

Các thuộc tính này được client/browser thực thi theo quy tắc cookie. Chúng không mã hóa giá trị cookie và cũng không thay thế xác thực, phân quyền, bảo vệ CSRF hoặc kiểm soát XSS.

## 2. HttpOnly: hạn chế truy cập cookie từ JavaScript

### 2.1. Ý nghĩa

Cookie có **HttpOnly** không được truy cập qua các API JavaScript phía trình duyệt như **document.cookie**. Trình duyệt vẫn có thể tự gửi cookie trong những request phù hợp theo Domain, Path, Secure và SameSite.

Đặc tính này hữu ích cho cookie session hoặc cookie xác thực do server quản lý:

~~~http
Set-Cookie: SESSION=sample-session; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

Nếu trang web bị một lỗ hổng XSS, HttpOnly có thể ngăn script lấy trực tiếp giá trị session cookie qua document.cookie. Tuy nhiên, nó **không ngăn script độc hại thực hiện request bằng phiên hiện tại** trong trình duyệt của nạn nhân. Vì vậy vẫn cần phòng chống XSS, kiểm soát đầu vào/đầu ra và chính sách bảo mật nội dung phù hợp.

### 2.2. Khi nào nên dùng?

| Loại cookie | HttpOnly thường phù hợp? | Lý do |
| --- | --- | --- |
| Session cookie do server quản lý | Có | JavaScript không cần đọc session identifier |
| Cookie xác thực do server quản lý | Thường có | Hạn chế việc lấy trực tiếp token qua script |
| Cookie preference như locale | Tùy kiến trúc | Nếu JavaScript cần đọc để thay đổi giao diện thì HttpOnly không phù hợp |
| CSRF cookie theo mô hình JavaScript đọc token rồi gửi lại header | Có thể không | Client script cần đọc token theo thiết kế đó; phải cân nhắc mô hình CSRF |

Không bật HttpOnly chỉ vì đó là một thuộc tính “an toàn” trong mọi tình huống. Hãy xem client cần đọc cookie hay không và thiết kế xác thực/CSRF đang dùng.

## 3. Secure: chỉ gửi cookie qua kênh bảo mật

### 3.1. Ý nghĩa

Thuộc tính **Secure** yêu cầu user agent chỉ gửi cookie qua kết nối được xem là an toàn theo quy tắc cookie, thường là HTTPS:

~~~http
Set-Cookie: SESSION=sample-session; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Secure giúp hạn chế gửi session cookie qua HTTP không mã hóa. Nó không tự mã hóa cookie trong database, không ngăn lộ giá trị trong log và không thay thế việc dùng TLS cho toàn bộ ứng dụng.

Trong production, cookie xác thực thường cần **Secure** cùng HTTPS. Nếu ứng dụng được đặt sau reverse proxy hoặc load balancer, cần cấu hình nhận diện scheme bên ngoài một cách an toàn để không phát hành cookie với chính sách sai.

### 3.2. Secure và môi trường local

MockMvc test thường không tạo kết nối HTTPS thật; nó gọi ứng dụng trong môi trường mô phỏng. Vì vậy một cookie có Secure vẫn có thể được kiểm tra trong response bằng MockMvc, nhưng test đó **không chứng minh** trình duyệt sẽ gửi cookie qua một luồng HTTPS/HTTP triển khai thực tế.

Không hạ cấu hình production để làm test local dễ chạy. Dùng test fixture độc lập và kiểm tra header Set-Cookie; nếu cần xác nhận hành vi gửi cookie của trình duyệt, bổ sung integration test qua HTTPS trong môi trường phù hợp.

## 4. SameSite: kiểm soát cookie trong ngữ cảnh cross-site

SameSite ảnh hưởng việc trình duyệt gửi cookie khi request phát sinh trong ngữ cảnh site khác. Ba giá trị phổ biến:

| Giá trị | Mô tả tổng quát | Trường hợp sử dụng thường gặp |
| --- | --- | --- |
| **Strict** | Giới hạn chặt việc gửi cookie trong request cross-site | Phiên hoặc khu vực nhạy cảm không cần cookie trong luồng điều hướng từ site khác |
| **Lax** | Cho phép một số điều hướng top-level an toàn, nhưng hạn chế nhiều request cross-site khác | Lựa chọn thường dùng cho cookie phiên trong nhiều ứng dụng web |
| **None** | Cho phép cookie được gửi trong ngữ cảnh cross-site theo các điều kiện khác | Luồng đăng nhập hoặc tích hợp thực sự cần cookie cross-site |

Với cookie **SameSite=None**, trình duyệt hiện đại yêu cầu cookie có **Secure**. Hãy dùng HTTPS và xác minh hành vi trong browser mà ứng dụng hỗ trợ.

### 4.1. SameSite và CSRF

Cookie tự động được trình duyệt gửi kèm request là một yếu tố trong các mô hình CSRF. SameSite có thể giảm một số request cross-site mang cookie, nhưng không thay thế toàn bộ biện pháp bảo vệ CSRF:

- Với ứng dụng session-based, xác định rõ cơ chế CSRF token và cách client gửi lại token.
- Kiểm tra các luồng cross-site hợp lệ như OAuth/OIDC redirect hoặc thanh toán bên thứ ba.
- Không giả định GET an toàn nếu endpoint thực tế thay đổi trạng thái.
- Kết hợp kiểm tra Origin/Referer, CSRF token và các biện pháp phù hợp với kiến trúc.

Việc chọn Strict, Lax hoặc None phải dựa vào luồng trình duyệt thật, không chỉ dựa trên test MockMvc.

## 5. Cấu hình cookie trong Spring

### 5.1. Dùng Servlet Cookie

Trong Spring MVC chạy trên Servlet, có thể tạo cookie bằng **jakarta.servlet.http.Cookie**:

~~~java
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletResponse;

Cookie session = new Cookie("SESSION", "sample-session");
session.setPath("/");
session.setHttpOnly(true);
session.setSecure(true);
session.setMaxAge(1800);
response.addCookie(session);
~~~

API Servlet Cookie truyền thống có các setter cho HttpOnly, Secure, Path, Domain và Max-Age; cách cấu hình SameSite tùy phiên bản servlet/container hoặc cần thêm qua header/cơ chế hỗ trợ tương ứng. Không nối chuỗi Set-Cookie tùy tiện nếu framework có API hỗ trợ.

### 5.2. Dùng Spring ResponseCookie

Spring cung cấp **org.springframework.http.ResponseCookie** để xây dựng cookie với API fluent:

~~~java
import org.springframework.http.ResponseCookie;

ResponseCookie session = ResponseCookie.from("SESSION", "sample-session")
    .path("/")
    .httpOnly(true)
    .secure(true)
    .sameSite("Lax")
    .maxAge(1800)
    .build();

response.addHeader("Set-Cookie", session.toString());
~~~

Kiểm tra API của phiên bản Spring Framework đang dùng để xác nhận các method và kiểu dữ liệu hỗ trợ. Tránh phát hành đồng thời hai cookie cùng tên do vừa gọi addCookie vừa thêm một Set-Cookie thủ công.

### 5.3. Ví dụ controller phát hành cookie phiên

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SessionController {

    @PostMapping("/api/session")
    ResponseEntity<SessionResponse> createSession() {
        // Chỉ là giá trị minh họa trong ví dụ; ứng dụng thật phải
        // dùng session identifier ngẫu nhiên do cơ chế bảo mật quản lý.
        ResponseCookie cookie = ResponseCookie.from(
                "SESSION", "test-session-placeholder")
            .path("/")
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax")
            .maxAge(1800)
            .build();

        return ResponseEntity.ok()
            .header(HttpHeaders.SET_COOKIE, cookie.toString())
            .body(new SessionResponse("created"));
    }
}

record SessionResponse(String status) {}
~~~

Không dùng chuỗi cố định ở trên làm session identifier thực tế. Hệ thống thật phải tạo, lưu trữ, xoay vòng và thu hồi session bằng cơ chế an toàn; ví dụ chỉ tập trung vào việc cấu hình cookie.

## 6. Tài liệu hóa thuộc tính bảo mật với Spring REST Docs

### 6.1. responseCookies mô tả tên và ý nghĩa cookie

Spring REST Docs dùng **responseCookies(...)** và **cookieWithName(...)** để mô tả cookie response:

~~~java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;

responseCookies(
    cookieWithName("SESSION")
        .description("Cookie phiên do server quản lý; trình duyệt gửi lại trong các request phù hợp")
)
~~~

Descriptor cookie mô tả **tên và ý nghĩa**. Bảng **response-cookies.adoc** không phải bảng đầy đủ mọi thuộc tính Set-Cookie. Các flag **HttpOnly**, **Secure**, **SameSite**, **Path** và **Max-Age** được thể hiện trong header **Set-Cookie** của response snippet hoặc được giải thích thêm bằng văn bản.

### 6.2. Ghi lại header Set-Cookie

Trong cùng operation, có thể dùng **responseHeaders(...)** để chỉ rõ header Set-Cookie:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;

responseHeaders(
    headerWithName("Set-Cookie")
        .description("Cookie phiên cùng các thuộc tính bảo mật do server thiết lập")
)
~~~

Header **Set-Cookie** có thể xuất hiện nhiều lần trong một response, mỗi cookie thường có một header riêng. Nếu tài liệu hóa nhiều cookie, kiểm tra hành vi snippet header của phiên bản REST Docs và vẫn dùng **responseCookies(...)** để mô tả từng cookie theo tên.

Khi cần làm nổi bật thuộc tính, bổ sung đoạn văn có ý nghĩa:

~~~asciidoc
Cookie SESSION được phát hành với HttpOnly và Secure. SameSite=Lax giới hạn việc trình duyệt gửi cookie trong các ngữ cảnh cross-site; ứng dụng yêu cầu HTTPS.
~~~

Đoạn mô tả này phải phản ánh đúng cấu hình response được test, không ghi chính sách dự kiến khi code đang phát hành giá trị khác.

## 7. Kiểm thử HttpOnly và Secure với MockMvc

MockMvc có cookie matcher để kiểm tra các thuộc tính được Servlet API biểu diễn:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.cookie;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(SessionController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class SessionCookieDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentSecureHttpOnlySessionCookie() throws Exception {
        mockMvc.perform(post("/api/session")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(cookie().exists("SESSION"))
            .andExpect(cookie().httpOnly("SESSION", true))
            .andExpect(cookie().secure("SESSION", true))
            .andExpect(cookie().path("SESSION", "/"))
            .andExpect(cookie().maxAge("SESSION", 1800))
            .andExpect(header().string("Set-Cookie",
                org.hamcrest.Matchers.allOf(
                    org.hamcrest.Matchers.containsString("HttpOnly"),
                    org.hamcrest.Matchers.containsString("Secure"),
                    org.hamcrest.Matchers.containsString("SameSite=Lax")
                )))
            .andDo(document("session-create",
                responseCookies(
                    cookieWithName("SESSION")
                        .description("Cookie phiên do server quản lý")
                ),
                responseHeaders(
                    headerWithName("Set-Cookie")
                        .description("Cookie phiên với thuộc tính HttpOnly, Secure và SameSite")
                )
            ));
    }
}
~~~

Trong test:

- **cookie().httpOnly(...)** xác nhận flag HttpOnly.
- **cookie().secure(...)** xác nhận flag Secure.
- **cookie().path(...)** và **cookie().maxAge(...)** kiểm tra thêm thuộc tính vòng đời/phạm vi.
- Assertion trên **Set-Cookie** xác nhận SameSite trong ví dụ ResponseCookie.
- **responseCookies(...)** tạo bảng tên cookie; **responseHeaders(...)** mô tả header được phát hành.

Với nhiều header Set-Cookie, không nên giả định **header().string("Set-Cookie", ...)** luôn chọn đúng header nếu response có nhiều cookie. Có thể lấy danh sách header và kiểm tra từng giá trị bằng assertion phù hợp.

### 7.1. Kiểm thử SameSite

SameSite không phải thuộc tính có matcher chuyên biệt trong mọi phiên bản MockMvc. Có thể kiểm tra header Set-Cookie:

~~~java
mockMvc.perform(post("/api/session"))
    .andExpect(header().string("Set-Cookie",
        org.hamcrest.Matchers.containsString("SameSite=Lax")));
~~~

Đây là assertion trên biểu diễn header được server phát hành, không phải kiểm thử trình duyệt có gửi cookie trong luồng cross-site hay không. Đối với hành vi browser, cần integration/end-to-end test trên HTTPS và các origin thực tế.

## 8. Những gì snippet chứng minh và không chứng minh

| Kiểm tra/tài liệu | Có thể xác nhận | Không thể tự xác nhận |
| --- | --- | --- |
| **responseCookies(...)** | Tên cookie và mô tả đã khai báo có khớp operation | Trình duyệt lưu cookie đúng trong mọi ngữ cảnh |
| **http-response.adoc** | Response thực tế của test, gồm Set-Cookie được ghi lại | Trình duyệt thực thi Secure/HttpOnly/SameSite như dự kiến |
| MockMvc cookie matcher | Giá trị, HttpOnly, Secure, Path, Max-Age trong response mô phỏng | Trình duyệt từ chối cookie trên HTTP hay gửi trong cross-site |
| Assertion **SameSite=Lax** trên Set-Cookie | Server phát hành thuộc tính đó | Luồng OAuth, redirect hoặc CSRF hoạt động đúng trên browser |
| Browser integration test | Hành vi cookie trong browser/HTTPS theo kịch bản test | Tất cả browser/phiên bản đều giống nhau nếu không được kiểm thử |

Do đó, tài liệu REST Docs và test MockMvc nên đi cùng browser test khi contract phụ thuộc vào chính sách cookie của trình duyệt.

## 9. Chọn chính sách theo loại cookie

| Cookie | HttpOnly | Secure | SameSite gợi ý để đánh giá |
| --- | --- | --- | --- |
| Session của ứng dụng web | Thường bật | Bật trên production HTTPS | Lax hoặc Strict tùy luồng đăng nhập/điều hướng |
| Refresh token trong cookie | Thường bật | Bật | Lax/Strict nếu kiến trúc cho phép; cần đánh giá luồng cross-site |
| CSRF token cookie được JavaScript đọc | Có thể cần tắt | Bật trên HTTPS | Theo thiết kế CSRF và luồng client |
| Preference mà JavaScript cần đọc | Thường tắt | Tùy dữ liệu và môi trường | Chọn theo nhu cầu cross-site |
| Cookie nhúng trong iframe hoặc cross-site flow | Thường bật nếu không cần JS đọc | Thường cần bật | None có thể cần thiết, kèm Secure |

Đây là điểm xuất phát để đánh giá, không phải cấu hình bắt buộc cho mọi ứng dụng. Cần xem cách client hoạt động, nguy cơ XSS/CSRF, domain, HTTPS, redirect, iframe và chính sách trình duyệt.

## 10. Nhúng snippet và tài liệu Asciidoctor

Sau khi test sinh operation **session-create**, thư mục snippets có thể gồm:

~~~text
build/generated-snippets/session-create/
├── http-request.adoc
├── http-response.adoc
├── response-cookies.adoc
└── response-headers.adoc
~~~

Trong **src/docs/asciidoc/session.adoc**:

~~~asciidoc
= Session API
:toc: left

== Tạo phiên

POST /api/session

=== Response cookie

include::{snippets}/session-create/response-cookies.adoc[]

=== Response headers

include::{snippets}/session-create/response-headers.adoc[]

=== HTTP response

include::{snippets}/session-create/http-response.adoc[]

Cookie SESSION được phát hành với HttpOnly, Secure và SameSite=Lax. API sử dụng HTTPS; client không cần đọc giá trị session từ JavaScript.
~~~

Đoạn văn cuối chỉ đúng khi test và code thực sự tạo cookie như mô tả. Nếu SameSite hoặc thuộc tính thay đổi, hãy cập nhật test và tài liệu cùng lúc.

### 10.1. Tích hợp Gradle/CI

Ví dụ Gradle Groovy DSL, giả định dự án đã áp dụng plugin **org.asciidoctor.jvm.convert**:

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

Trong CI:

1. Chạy test MockMvc tạo cookie.
2. Assert các flag HttpOnly, Secure, SameSite và những thuộc tính liên quan.
3. Sinh response-cookies, response-headers và http-response snippets.
4. Dựng Asciidoctor sau khi test thành công.
5. Kiểm tra output không chứa giá trị session thật trước khi xuất bản.

Nếu tài liệu cuối là Markdown, cần cơ chế chuyển đổi hoặc nhúng tương ứng; **include::{snippets}/...[]** là cú pháp của Asciidoctor.

## 11. Bảo mật và những lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Session cookie không có HttpOnly | Quên cấu hình hoặc dùng cơ chế phát hành cookie khác | Assert HttpOnly và kiểm tra Set-Cookie thực tế |
| Cookie production không có Secure | Ứng dụng nhận diện sai scheme phía sau proxy hoặc cấu hình thiếu | Cấu hình HTTPS/forwarded headers an toàn và test header |
| SameSite=None nhưng thiếu Secure | Cấu hình cookie không tương thích yêu cầu browser hiện đại | Thêm Secure và chạy browser test qua HTTPS |
| MockMvc test pass nhưng browser không gửi cookie | MockMvc không mô phỏng chính sách browser cross-site | Thêm end-to-end test trên browser/origin thực |
| JavaScript không đọc được cookie preference | Bật HttpOnly trong khi client cần đọc cookie | Xem lại yêu cầu; có thể chuyển dữ liệu sang API/JSON |
| Tài liệu nói cookie bảo vệ CSRF hoàn toàn | Nhầm SameSite với giải pháp CSRF đầy đủ | Tài liệu hóa cơ chế CSRF thực tế và test luồng |
| Snippet lộ session identifier | Dùng giá trị thật hoặc fixture nhạy cảm | Dùng placeholder, preprocessing và kiểm tra tất cả snippets |
| response-cookies chỉ ghi tên, thiếu thuộc tính | Chỉ dùng cookie descriptor | Include http-response/response-headers và giải thích flags |

Không log giá trị session/token, kể cả trong test failure hoặc pipeline. Nếu cần kiểm thử token, dùng fixture giả định và chỉ công bố tên cookie cùng thuộc tính cần thiết.

## 12. Bài thực hành

Xây dựng endpoint:

~~~text
POST /api/session
~~~

Hợp đồng:

- Server phát hành cookie **SESSION**.
- Cookie có **Path=/**, **HttpOnly**, **Secure**, **SameSite=Lax** và **Max-Age=1800**.
- Response có JSON body báo trạng thái tạo phiên.
- Tài liệu không được lộ giá trị session.

Yêu cầu:

1. Dùng **ResponseCookie** để tạo cookie với đủ các thuộc tính.
2. Viết test MockMvc xác nhận cookie tồn tại, HttpOnly, Secure, Path và Max-Age.
3. Assert header Set-Cookie chứa **SameSite=Lax**.
4. Dùng **responseCookies(cookieWithName("SESSION")...)** để mô tả cookie.
5. Dùng **responseHeaders(headerWithName("Set-Cookie")...)** và include **http-response.adoc** để thể hiện response header.
6. Dùng session placeholder trong test; kiểm tra snippet không chứa session value thật.
7. Tạo browser integration test trên HTTPS nếu ứng dụng cần chứng minh hành vi Secure/SameSite trong trình duyệt.
8. Dựng Asciidoctor sau test và chạy toàn bộ luồng trong CI.

**Tiêu chí hoàn thành:** server phát hành đúng ba flag; test kiểm tra các thuộc tính; cookie descriptor và response/header snippet được sinh; tài liệu giải thích đúng giới hạn của MockMvc; không có session secret trong output.

## Ghi nhớ

**HttpOnly** hạn chế JavaScript đọc cookie; **Secure** giới hạn gửi cookie qua kết nối không bảo mật; **SameSite** điều khiển việc gửi cookie trong ngữ cảnh cross-site. Ba thuộc tính giải quyết các khía cạnh khác nhau và không thay thế TLS, phòng chống XSS, CSRF hay phân quyền. Trong Spring REST Docs, **responseCookies(...)** mô tả tên và ý nghĩa cookie; **http-response.adoc** hoặc **response-headers.adoc** thể hiện header **Set-Cookie** chứa flags. MockMvc có thể kiểm tra cấu hình response, còn hành vi browser cần test trên HTTPS/origin thực tế. Kết hợp hai loại kiểm thử và snippet trong CI để tài liệu phản ánh chính xác chính sách cookie.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs CookieDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/cookies/CookieDocumentation.html), [Spring ResponseCookie API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseCookie.html), [RFC 6265](https://www.rfc-editor.org/rfc/rfc6265) và [RFC 6265bis: Cookies](https://datatracker.ietf.org/doc/draft-ietf-httpbis-rfc6265bis/).
