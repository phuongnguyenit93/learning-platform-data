# request-cookies và response-cookies

## Mục tiêu học tập

Trong module **SPRING_REST_DOCS**, cookie thường được dùng để duy trì phiên đăng nhập, lưu dấu trạng thái hoặc truyền một mã định danh giữa client và server. Một API có thể đọc cookie từ request hoặc tạo/cập nhật cookie trong response. Tài liệu API cần giải thích cookie nào client phải gửi, cookie nào server trả về và ý nghĩa của từng cookie.

Spring REST Docs cung cấp hai snippet mặc định:

- **request-cookies**: mô tả cookie xuất hiện trong HTTP request.
- **response-cookies**: mô tả cookie xuất hiện trong HTTP response.

Các snippet được tạo từ cookie descriptor trong bài test. REST Docs đối chiếu descriptor với cookie quan sát được, giúp phát hiện cookie mới, cookie bị bỏ sót hoặc tên cookie thay đổi.

Sau bài này, bạn có thể:

- Phân biệt cookie phía request và cookie phía response.
- Dùng requestCookies, responseCookies và cookieWithName.
- Sinh và include request-cookies.adoc, response-cookies.adoc.
- Dùng optional, ignored và relaxedRequestCookies/relaxedResponseCookies.
- Kiểm thử cookie bằng MockMvc và WebTestClient.
- Hiểu mối quan hệ giữa Cookie header, Set-Cookie và các thuộc tính bảo mật.
- Tránh nhầm việc ghi tài liệu cookie với việc kiểm thử toàn bộ chính sách bảo mật cookie.

## 1. Cookie trong HTTP request và response

Cookie có hai chiều trao đổi:

**Request:** client gửi cookie tới server qua header Cookie. Ví dụ:

```http
GET /profile HTTP/1.1
Host: api.example.test
Cookie: JSESSIONID=abc123; theme=dark
```

**Response:** server gửi cookie về client qua header Set-Cookie. Ví dụ:

```http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=xyz789; Path=/; HttpOnly; Secure; SameSite=Lax
Set-Cookie: logged_in=true; Path=/; Secure; SameSite=Lax
```

| Phía | HTTP header | Ý nghĩa |
| --- | --- | --- |
| Request | Cookie | Các cặp tên/giá trị cookie mà client gửi |
| Response | Set-Cookie | Chỉ thị server gửi để tạo, cập nhật hoặc xóa cookie ở client |

Một cookie server tạo trong response thường chỉ xuất hiện ở request kế tiếp khi client lưu và gửi lại theo quy tắc domain, path, expiry, Secure, SameSite và chính sách cookie của client. Vì vậy, cookie request và response phải được mô tả theo từng HTTP exchange.

## 2. API tài liệu hóa cookie của Spring REST Docs

Các API nằm trong package:

```java
org.springframework.restdocs.cookies.CookieDocumentation
```

Các phương thức chính:

| API | Chức năng |
| --- | --- |
| cookieWithName("...") | Tạo descriptor cho cookie có tên đã chọn |
| requestCookies(...) | Tạo snippet mô tả cookie của request |
| responseCookies(...) | Tạo snippet mô tả cookie của response |
| relaxedRequestCookies(...) | Mô tả một phần cookie request, bỏ qua cookie khác chưa khai báo |
| relaxedResponseCookies(...) | Mô tả một phần cookie response, bỏ qua cookie khác chưa khai báo |

Hai snippet mặc định:

```text
build/generated-snippets/
└── profile/
    ├── request-cookies.adoc
    └── response-cookies.adoc
```

Tên file không chứa tên cookie. Mỗi snippet chứa một bảng tổng hợp cookie được mô tả cho operation đó.

## 3. requestCookies — mô tả cookie client gửi

### 3.1. Ví dụ với MockMvc

Giả sử endpoint GET /profile yêu cầu session cookie:

```java
import jakarta.servlet.http.Cookie;

import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;

this.mockMvc.perform(get("/profile")
        .cookie(new Cookie("JSESSIONID", "abc123")))
    .andExpect(status().isOk())
    .andDo(document("profile",
        requestCookies(
            cookieWithName("JSESSIONID")
                .description("Cookie định danh phiên đăng nhập.")
        )));
```

requestCookies tạo snippet request-cookies.adoc. Descriptor cookieWithName xác định tên cookie và description giải thích vai trò của nó.

Trong ví dụ Spring Boot 3/4, servlet API dùng namespace jakarta.servlet. Với dự án Spring cũ dùng javax.servlet, import Cookie phải theo namespace mà ứng dụng đang sử dụng.

### 3.2. Nhiều cookie trong request

```java
this.mockMvc.perform(get("/profile")
        .cookie(
            new Cookie("JSESSIONID", "abc123"),
            new Cookie("locale", "vi-VN")
        ))
    .andExpect(status().isOk())
    .andDo(document("profile",
        requestCookies(
            cookieWithName("JSESSIONID")
                .description("Cookie định danh phiên đăng nhập."),
            cookieWithName("locale")
                .description("Ngôn ngữ ưu tiên của người dùng.")
        )));
```

Tên trong cookieWithName phải khớp với tên thực tế trong request. REST Docs không suy diễn rằng sessionId, JSESSIONID và SESSION là cùng một cookie.

### 3.3. Dùng relaxedRequestCookies

Nếu request có một số cookie không thuộc phạm vi tài liệu của operation:

```java
relaxedRequestCookies(
    cookieWithName("JSESSIONID")
        .description("Cookie định danh phiên.")
)
```

Chế độ relaxed cho phép cookie khác chưa khai báo xuất hiện trong request mà không làm test thất bại. Cookie đã khai báo vẫn phải có mặt, trừ khi được đánh dấu optional.

## 4. responseCookies — mô tả cookie server trả về

### 4.1. Ví dụ với MockMvc

Giả sử endpoint xác thực tạo session cookie:

```java
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;

this.mockMvc.perform(post("/login")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "username": "an",
                  "password": "test-password"
                }
                """))
    .andExpect(status().isOk())
    .andDo(document("login",
        responseCookies(
            cookieWithName("JSESSIONID")
                .description("Cookie định danh phiên do server cấp."),
            cookieWithName("logged_in")
                .description("Cho biết client đã đăng nhập.")
        )));
```

Snippet response-cookies.adoc mô tả cookie trong response. Cookie JSESSIONID có thể được server cập nhật khi session được tạo hoặc thay đổi.

### 4.2. Tạo cookie trong response của test

Với MockMvc, cookie response có thể được tạo từ controller:

```java
ResponseCookie sessionCookie = ResponseCookie.from("SESSION", "session-value")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .build();

return ResponseEntity.ok()
        .header(HttpHeaders.SET_COOKIE, sessionCookie.toString())
        .body(profile);
```

REST Docs đọc cookie được gửi trong response của exchange. Trong test, nên kiểm tra thêm header Set-Cookie hoặc cookie tương ứng để xác minh endpoint thực sự tạo cookie theo hợp đồng.

### 4.3. Xóa cookie

Server thường xóa cookie bằng cách gửi Set-Cookie cùng tên, giá trị rỗng và thời hạn hết hạn trong quá khứ hoặc Max-Age=0:

```http
Set-Cookie: SESSION=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax
```

Về giao thức, đây vẫn là một Set-Cookie trong response. Tài liệu nên giải thích hành vi xóa cookie, thay vì chỉ gọi nó là cookie mới được tạo.

## 5. Hành vi strict, optional và ignored

### 5.1. Strict mode mặc định

requestCookies và responseCookies kiểm tra sự tương ứng giữa cookie thực tế và descriptor:

- Cookie xuất hiện trong exchange nhưng chưa được mô tả có thể làm test thất bại.
- Cookie đã được mô tả nhưng không xuất hiện trong exchange cũng làm test thất bại nếu chưa đánh dấu optional.

Điều này khiến bài test tài liệu phát hiện khi API bắt đầu gửi cookie mới hoặc ngừng gửi cookie đã công bố.

### 5.2. Cookie optional

Một cookie có thể xuất hiện ở một số response nhưng không xuất hiện ở response khác:

```java
responseCookies(
    cookieWithName("SESSION")
        .description("Cookie phiên đăng nhập."),
    cookieWithName("remember_me")
        .optional()
        .description("Cookie duy trì đăng nhập; chỉ có khi người dùng chọn ghi nhớ.")
)
```

optional cho phép cookie được mô tả nhưng vắng mặt trong exchange hiện tại. Nó hữu ích cho cookie phụ thuộc trạng thái đăng nhập, tùy chọn người dùng hoặc nhánh xử lý.

### 5.3. Cookie ignored

Nếu cookie có trong exchange nhưng không cần xuất hiện trong bảng snippet:

```java
requestCookies(
    cookieWithName("SESSION")
        .description("Cookie phiên."),
    cookieWithName("tracking_id")
        .ignored()
)
```

ignored xử lý cookie để kiểm tra không thất bại vì cookie chưa được mô tả, đồng thời không đưa nó vào bảng snippet. Không dùng ignored để che giấu cookie bảo mật quan trọng mà client cần hiểu.

### 5.4. relaxedResponseCookies

Nếu chỉ muốn mô tả một phần response cookies:

```java
relaxedResponseCookies(
    cookieWithName("SESSION")
        .description("Cookie phiên đăng nhập.")
)
```

Cookie khác chưa khai báo được bỏ qua. Cookie đã khai báo mà không xuất hiện vẫn cần optional nếu nó có thể vắng mặt.

| Cách khai báo | Cookie chưa mô tả | Cookie đã mô tả nhưng vắng mặt |
| --- | --- | --- |
| requestCookies/responseCookies | Làm test thất bại | Làm test thất bại, trừ optional |
| relaxedRequestCookies/relaxedResponseCookies | Bỏ qua | Làm test thất bại, trừ optional |
| ignored() | Xử lý cookie được chỉ định nhưng không hiển thị | Không biến cookie thành optional |
| optional() | Không tác động cookie khác | Cho phép cookie được mô tả vắng mặt |

## 6. Ví dụ WebTestClient

WebTestClient có thể gửi cookie trong request bằng phương thức cookie:

```java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

this.webTestClient.get()
    .uri("/people")
    .cookie("JSESSIONID", "abc123")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("people",
        requestCookies(
            cookieWithName("JSESSIONID")
                .description("Cookie định danh phiên.")
        ),
        responseCookies(
            cookieWithName("logged_in")
                .description("Cho biết người dùng đã đăng nhập.")
        )));
```

Trong response, ứng dụng có thể trả Set-Cookie qua response headers. REST Docs ghi nhận cookie response để tạo response-cookies.adoc. Hãy kiểm tra request/response của test có đúng cookie trước khi dựa vào snippet.

## 7. Cookie name, value và các thuộc tính bảo mật

Snippet cookie của REST Docs tập trung vào **tên cookie và mô tả**. Nó không thay thế tài liệu chính sách cookie và không tự bảo đảm các cờ bảo mật được bật.

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa | Điều cần giải thích trong tài liệu |
| --- | --- | --- |
| Secure | Trình duyệt chỉ gửi cookie qua kênh bảo mật theo quy tắc cookie | Cookie chỉ dùng qua HTTPS trong môi trường production phù hợp |
| HttpOnly | JavaScript phía client không thể đọc cookie qua API cookie thông thường | Giảm khả năng đọc cookie bằng script; không thay thế các biện pháp chống XSS |
| SameSite | Kiểm soát việc gửi cookie trong ngữ cảnh site khác | Lựa chọn Strict, Lax hoặc None theo luồng điều hướng và xác thực |
| Domain | Phạm vi host được phép nhận cookie | Cookie áp dụng cho host/domain nào |
| Path | Phạm vi đường dẫn request mà cookie được gửi tới | Cookie áp dụng cho path nào |
| Max-Age/Expires | Thời hạn lưu cookie | Session cookie hay persistent cookie; khi nào hết hạn |

Ví dụ Set-Cookie:

```http
Set-Cookie: SESSION=opaque-value; Path=/; Max-Age=1800; Secure; HttpOnly; SameSite=Lax
```

REST Docs response-cookies giúp liệt kê SESSION và mô tả công dụng. Nếu người đọc cần biết Secure, HttpOnly, SameSite, Path hoặc Max-Age, hãy mô tả các chính sách đó bằng prose hoặc tài liệu hóa header Set-Cookie riêng. Không nên giả định bảng cookie mặc định sẽ có cột cho tất cả thuộc tính này.

### 7.1. Không ghi giá trị bí mật vào tài liệu

Cookie session, refresh token hoặc mã xác thực thường là dữ liệu nhạy cảm. Test nên dùng giá trị giả, không lấy cookie thật từ tài khoản hoặc môi trường production. Trong phần mô tả, ghi mục đích và cách client sử dụng cookie thay vì công bố giá trị.

## 8. Cookie và bảo mật phiên đăng nhập

Cookie có thể mang session ID hoặc token; vì vậy nội dung tài liệu phải chính xác:

- Cookie session thường do server cấp và client tự gửi ở các request tiếp theo.
- Không mô tả cookie phiên như access token trong Authorization header nếu cơ chế xác thực không dùng bearer token.
- Secure, HttpOnly và SameSite có vai trò khác nhau; không gộp tất cả thành một tuyên bố “cookie an toàn”.
- Cookie có thể bị xóa hoặc thay đổi sau logout, hết hạn phiên hoặc đổi trạng thái đăng nhập.
- Cookie scope chịu ảnh hưởng của domain/path và chính sách trình duyệt.

Test REST Docs có thể chứng minh một exchange đã gửi/trả cookie có tên cụ thể. Để chứng minh thuộc tính bảo mật, cần assertion riêng trên Set-Cookie hoặc cấu hình ứng dụng và test tương ứng.

Ví dụ kiểm tra header:

```java
MvcResult result = this.mockMvc.perform(post("/login")
        .contentType(MediaType.APPLICATION_JSON)
        .content(loginJson))
    .andExpect(status().isOk())
    .andReturn();

String setCookie = result.getResponse().getHeader(HttpHeaders.SET_COOKIE);

assertThat(setCookie)
        .contains("HttpOnly")
        .contains("Secure")
        .contains("SameSite=Lax");
```

Đây là assertion minh họa. Trong dự án thật, kiểm tra cookie bằng API servlet hoặc parser phù hợp cũng có thể bền vững hơn so với so khớp chuỗi header nguyên văn.

## 9. Include cookie snippets vào AsciiDoc

Sau khi chạy test, có thể include hai snippet:

```asciidoc
== Request cookies
include::{snippets}/profile/request-cookies.adoc[]

== Response cookies
include::{snippets}/profile/response-cookies.adoc[]
```

Nếu một operation chỉ có cookie request hoặc chỉ có cookie response, chỉ include snippet tương ứng. Không include file chưa được test tạo ra.

Một cấu trúc thư mục ví dụ:

```text
build/generated-snippets/
└── profile/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-cookies.adoc
    └── response-cookies.adoc
```

request-cookies và response-cookies là snippet bổ sung cho HTTP request/response tổng quát; chúng không thay thế http-request hoặc http-response.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Test báo cookie request chưa được mô tả | Request có cookie mới chưa có descriptor | Thêm cookieWithName hoặc dùng relaxedRequestCookies có chủ ý |
| Test báo descriptor không tìm thấy cookie | Sai tên hoặc request không gửi cookie | Đối chiếu Cookie header, test setup và tên descriptor |
| response-cookies.adoc không được tạo | Chưa khai báo responseCookies hoặc response không có cookie tương ứng | Thêm snippet và xác minh Set-Cookie |
| Cookie được mô tả nhưng không xuất hiện ở một nhánh | Cookie chỉ có trong một số trạng thái | Đánh dấu optional nếu hợp đồng cho phép vắng mặt |
| Cookie nội bộ làm test thất bại | Strict mode phát hiện cookie chưa khai báo | Mô tả, ignored hoặc relaxed với lý do rõ |
| Bảng cookie không hiện Secure/HttpOnly | Cookie snippet mặc định tập trung vào tên/mô tả | Assertion Set-Cookie và giải thích thuộc tính riêng |
| Test dùng javax.servlet.Cookie không biên dịch | Dự án dùng Jakarta Servlet | Đổi sang jakarta.servlet.http.Cookie theo thế hệ Spring |
| Cookie được trả nhưng browser không gửi lại | Domain, Path, Secure, SameSite, expiry hoặc client policy | Kiểm tra Set-Cookie và điều kiện gửi cookie của client |
| Tài liệu chứa session value thật | Dữ liệu test lấy từ môi trường thật | Dùng giá trị giả, thay token và kiểm tra artifact |

## 11. Bài thực hành

1. Tạo endpoint GET /profile nhận cookie JSESSIONID.
2. Viết MockMvc test gửi cookie và dùng requestCookies để mô tả cookie phiên.
3. Tạo endpoint POST /login trả cookie SESSION hoặc JSESSIONID.
4. Dùng responseCookies để mô tả cookie server cấp.
5. Kiểm tra Secure, HttpOnly, SameSite, Path và Max-Age bằng assertion riêng trên Set-Cookie.
6. Đánh dấu remember_me là optional khi cookie chỉ được tạo nếu client chọn ghi nhớ.
7. Thêm cookie phụ chưa mô tả; quan sát strict mode thất bại và thử relaxedRequestCookies.
8. Include request-cookies.adoc và response-cookies.adoc vào tài liệu AsciiDoc.

**Câu hỏi tự đánh giá**

1. requestCookies và responseCookies mô tả hai phía nào của HTTP exchange?
2. Cookie header khác Set-Cookie ra sao?
3. cookieWithName dùng để làm gì?
4. requestCookies mặc định xử lý cookie chưa được mô tả như thế nào?
5. optional khác ignored ở điểm nào?
6. relaxedResponseCookies thay đổi quy tắc kiểm tra nào?
7. Vì sao bảng cookie snippet không thay thế mô tả Secure/HttpOnly/SameSite?
8. Làm sao kiểm thử thuộc tính cookie bảo mật mà không đưa giá trị bí mật vào tài liệu?

## Tài liệu tham khảo chính thức

- [Spring REST Docs — HTTP Cookies](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-cookies.html): requestCookies, responseCookies, cookieWithName và chế độ relaxed.
- [CookieDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/cookies/CookieDocumentation.html): các phương thức tạo cookie snippets.
- [CookieDescriptor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/cookies/CookieDescriptor.html): mô tả, optional và ignored cho cookie descriptor.
- [MDN — Set-Cookie HTTP Header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie): thuộc tính cookie và cách trình duyệt xử lý.
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265): cơ chế cookie HTTP.

**Kết luận thực hành:** Dùng requestCookies để mô tả cookie client gửi và responseCookies để mô tả cookie server cấp hoặc cập nhật. Dùng cookieWithName cho từng cookie, optional cho cookie có thể vắng mặt, ignored hoặc relaxed khi có lý do rõ ràng. Tài liệu hóa thêm Secure, HttpOnly, SameSite và thời hạn bằng phần giải thích hoặc assertion Set-Cookie riêng, đồng thời chỉ sử dụng giá trị cookie giả trong test và artifact.
