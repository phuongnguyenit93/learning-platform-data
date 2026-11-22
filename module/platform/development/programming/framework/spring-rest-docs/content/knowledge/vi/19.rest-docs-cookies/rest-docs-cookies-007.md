# Cookie nhiều giá trị và encoding

## Mục tiêu bài học

Một HTTP request có thể gửi nhiều cookie, mỗi cookie mang một cặp tên/giá trị. Ngoài ra, một cookie đơn đôi khi chứa dữ liệu có cấu trúc như danh sách quyền, tùy chọn hoặc mã định danh. Hai trường hợp này cần được thiết kế và tài liệu hóa rõ ràng. Nếu tự nối nhiều giá trị bằng dấu phân cách mà không có quy ước encoding, client và server có thể phân tích dữ liệu khác nhau.

Bài học thuộc chương **Cookies** của module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn tài liệu Asciidoctor/Markdown rồi tích hợp vào build và CI.

Sau bài học này, bạn có thể:

- Phân biệt nhiều cookie trong một request với nhiều phần giá trị trong một cookie.
- Hiểu cấu trúc header **Cookie** và nhiều header **Set-Cookie**.
- Chọn quy ước biểu diễn danh sách hoặc dữ liệu có cấu trúc trong cookie.
- Encoding/decoding giá trị cookie nhất quán, tránh lỗi delimiter và double encoding.
- Dùng **requestCookies(...)**, **responseCookies(...)** và **cookieWithName(...)** để tài liệu hóa từng cookie.
- Viết test MockMvc kiểm tra cookie nhiều tên, giá trị encoded và kết quả decode.
- Dùng REST Docs để mô tả tên/mục đích cookie, đồng thời kiểm tra giá trị thực tế bằng assertion.
- Giữ cookie ngắn gọn, an toàn và tránh đưa dữ liệu nhạy cảm vào snippet.

## 1. Hai ý nghĩa khác nhau của “cookie nhiều giá trị”

Trước khi thiết kế, cần phân biệt:

**Nhiều cookie trong một request:** request chứa nhiều cặp cookie độc lập, thường được phân cách bằng dấu chấm phẩy trong header **Cookie**.

~~~http
GET /api/profile
Cookie: locale=vi; display-mode=compact; region=apac
~~~

**Một cookie chứa nhiều phần dữ liệu:** chỉ có một tên cookie, nhưng value biểu diễn nhiều mục theo quy ước của ứng dụng.

~~~http
Cookie: feature-flags=beta~search~compact
~~~

Ở ví dụ thứ hai, **feature-flags** là một cookie; **beta**, **search** và **compact** là các phần dữ liệu bên trong value sau khi ứng dụng giải mã và phân tích.

| Mô hình | Ví dụ | Tài liệu hóa |
| --- | --- | --- |
| Nhiều cookie độc lập | **locale=vi** và **display-mode=compact** | Một descriptor cho mỗi tên trong **requestCookies(...)** |
| Một cookie chứa danh sách | **feature-flags=beta%2Csearch** | Một descriptor cho **feature-flags**, mô tả rõ định dạng value |
| Một cookie chứa cấu trúc | **preferences=...** | Một descriptor cho **preferences**, mô tả encoding/schema của value |

Không gọi **locale**, **display-mode**, **region** là ba giá trị của cùng một cookie. Chúng là ba cookie khác nhau.

## 2. Cấu trúc cookie trong HTTP

Client gửi cookie trong header **Cookie**. Mỗi cặp có tên và value; nhiều cặp thường được phân cách bằng dấu chấm phẩy:

~~~http
Cookie: locale=vi; display-mode=compact
~~~

Server phát hành cookie trong response bằng header **Set-Cookie**. Mỗi cookie được gửi bằng một header Set-Cookie riêng:

~~~http
HTTP/1.1 200 OK
Set-Cookie: locale=vi; Path=/; Secure; SameSite=Lax
Set-Cookie: display-mode=compact; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

Không gộp nhiều **Set-Cookie** thành một header bằng dấu phẩy. Thuộc tính **Expires** có thể chứa dấu phẩy trong ngày tháng, nên việc gộp có thể làm parser hiểu sai ranh giới cookie.

Trong Spring REST Docs, từng cookie được mô tả bằng **cookieWithName(...)**:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Mã ngôn ngữ client mong muốn"),
    cookieWithName("display-mode")
        .description("Chế độ giao diện client đã lưu")
)
~~~

Nếu server trả hai cookie:

~~~java
responseCookies(
    cookieWithName("locale")
        .description("Mã ngôn ngữ được lưu cho lần truy cập sau"),
    cookieWithName("display-mode")
        .description("Chế độ giao diện được lưu cho lần truy cập sau")
)
~~~

**responseCookies(...)** mô tả cookie theo tên; **http-response.adoc** thể hiện các header Set-Cookie được ghi nhận. Hai phần này bổ sung cho nhau.

## 3. Quy tắc ký tự và lý do cần encoding

Cookie value không phải một vùng dữ liệu tùy ý như JSON body. Cú pháp cookie giới hạn một số ký tự, chẳng hạn dấu cách, dấu chấm phẩy, dấu phẩy, dấu ngoặc kép, dấu gạch chéo ngược và ký tự điều khiển. Ký tự Unicode cũng không nên được đưa trực tiếp vào cookie value mà không có quy ước encoding.

Một số ký tự dễ gây lỗi:

| Dữ liệu gốc | Vấn đề nếu đưa thẳng vào cookie value | Ví dụ biểu diễn encoded |
| --- | --- | --- |
| **hello world** | Dấu cách không thuộc tập cookie-octet chuẩn | **hello%20world** |
| **a;b** | Dấu **;** có thể bị hiểu là dấu phân cách cookie | **a%3Bb** |
| **a,b** | Dấu phẩy không thuộc tập cookie-octet chuẩn | **a%2Cb** |
| **a"b** | Dấu ngoặc kép không thuộc tập cookie-octet chuẩn | **a%22b** |
| **đăng nhập** | Chứa Unicode và dấu cách | **%C4%91%C4%83ng%20nh%E1%BA%ADp** |
| **50%** | Dấu phần trăm có thể bị nhầm là escape sequence | **50%25** |

Các chuỗi ở cột cuối minh họa **percent-encoding UTF-8**. Đây là quy ước phổ biến ở tầng ứng dụng, không có nghĩa mọi HTTP client hoặc servlet container tự động percent-decode cookie value. Client và server phải thống nhất cùng một cách encode/decode.

**Cookie header không phải query string và cũng không phải form body.** Không giả định rằng dấu cộng sẽ được giải mã thành khoảng trắng như một số bộ giải mã application/x-www-form-urlencoded.

## 4. Chọn cách biểu diễn cookie nhiều phần

Khi một cookie chứa danh sách hoặc dữ liệu có cấu trúc, hãy chọn định dạng rõ ràng thay vì tự nối chuỗi tùy ý.

### 4.1. Danh sách với delimiter

Ví dụ quy ước danh sách mã tính năng, phân tách bằng dấu ngã (**~**), một ký tự được phép trong cookie value:

~~~text
feature-flags=beta~search~compact
~~~

Nếu delimiter có thể xuất hiện trong một phần tử, phải escape/encode phần tử trước khi nối, hoặc chọn định dạng có parser chuẩn. Nếu không, value như **sales,west** sẽ không phân biệt được là một phần tử hay hai phần tử.

Một quy ước chặt chẽ:

1. Mã hóa từng phần tử theo UTF-8 percent-encoding.
2. Nối các phần tử đã mã hóa bằng dấu phân cách được quy ước, ở ví dụ này là dấu ngã (**~**).
3. Khi đọc, tách theo delimiter trước, rồi decode từng phần tử đúng một lần.
4. Kiểm tra các giá trị rỗng, trùng lặp, độ dài và tập giá trị được phép.

~~~text
Giá trị gốc:       ["beta", "sales,west", "tìm kiếm"]
Từng phần tử:      ["beta", "sales%2Cwest", "t%C3%ACm%20ki%E1%BA%BFm"]
Cookie value:      beta~sales%2Cwest~t%C3%ACm%20ki%E1%BA%BFm
Sau khi tách/decode:
                   ["beta", "sales,west", "tìm kiếm"]
~~~

Đây là một **quy ước do ứng dụng định nghĩa**. Cần ghi nó trong contract và triển khai cùng một parser ở tất cả client/server.

### 4.2. JSON được encode

Nếu dữ liệu cookie thực sự có cấu trúc, JSON có thể là một lựa chọn:

~~~json
{"theme":"dark","locale":"vi","flags":["beta","search"]}
~~~

Không gửi nguyên JSON tùy ý vào cookie value. Hãy serialize thành UTF-8, sau đó encode theo quy ước đã chọn (percent-encoding hoặc Base64URL). Ví dụ minh họa dùng Base64URL không padding:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

String json = """
    {"theme":"dark","locale":"vi","flags":["beta","search"]}
    """.trim();

String encoded = Base64.getUrlEncoder()
    .withoutPadding()
    .encodeToString(json.getBytes(StandardCharsets.UTF_8));
~~~

Base64URL tạo ký tự phù hợp hơn cho value trong nhiều trường hợp, nhưng nó **không mã hóa bí mật**. Người có cookie vẫn có thể decode Base64. Không đưa dữ liệu bí mật vào cookie chỉ vì đã encode.

Nếu cookie value phình to do JSON, danh sách hoặc dữ liệu lặp lại ở nhiều request, hãy cân nhắc lưu dữ liệu phía server và chỉ gửi một mã định danh ngắn trong cookie. Cookie thường được gửi kèm nhiều request nên kích thước lớn gây chi phí băng thông và có thể chạm giới hạn client/server.

### 4.3. Nhiều cookie độc lập thay cho một cookie phức tạp

Nếu các giá trị có vòng đời hoặc mục đích khác nhau, tách thành cookie riêng có thể dễ quản lý hơn:

~~~http
Cookie: locale=vi; display-mode=compact
~~~

Tách cookie hợp lý khi client có thể cập nhật từng lựa chọn riêng, mỗi giá trị có Path/Domain/Max-Age hoặc chính sách bảo mật khác nhau, hay API cần mô tả từng giá trị thành contract riêng.

Giữ một cookie tổng hợp hợp lý khi các phần dữ liệu luôn thay đổi cùng nhau và có schema ổn định. Đừng tạo quá nhiều cookie nhỏ nếu chúng chỉ có ý nghĩa khi được sử dụng cùng nhau.

## 5. Percent-encoding và Base64URL: lựa chọn đúng

| Cách | Phù hợp với | Ưu điểm | Lưu ý |
| --- | --- | --- | --- |
| Percent-encoding UTF-8 | Chuỗi văn bản, delimiter và ký tự đặc biệt | Có thể đọc một phần, biểu diễn byte rõ | Client/server phải thống nhất decode; **%** phải được encode khi là dữ liệu |
| Base64URL | Blob hoặc JSON đã serialize | Tránh nhiều ký tự delimiter trong cookie value | Tăng kích thước; không phải mã hóa bảo mật |
| Danh sách delimiter | Tập giá trị đơn giản, giới hạn ký tự | Dễ đọc | Chọn delimiter hợp lệ trong cookie value và escape khi nó xuất hiện trong phần tử |
| Cookie riêng cho từng giá trị | Các tùy chọn độc lập | Dễ mô tả và cập nhật riêng | Tăng số lượng cookie gửi theo request |

Tránh dùng **URLEncoder** như một bộ mã hóa cookie chung. URLEncoder tạo định dạng application/x-www-form-urlencoded, trong đó khoảng trắng thường thành dấu cộng. Cookie value không tự áp dụng quy tắc đó. Hãy dùng một hàm encode phù hợp với quy ước cookie mà ứng dụng công bố, hoặc dùng Base64URL nếu cần biểu diễn dữ liệu byte.

Không encode một giá trị hai lần. Nếu giá trị gốc là **a;b**, percent-encoding một lần tạo **a%3Bb**; encode tiếp dấu phần trăm có thể tạo **a%253Bb**. Sau một lần decode, server vẫn nhận **a%3Bb** thay vì **a;b**.

## 6. Triển khai encode/decode ở tầng ứng dụng

Ví dụ dưới đây dùng một quy ước đơn giản: cookie **feature-flags** là danh sách các phần tử UTF-8 percent-encoded, phân tách bằng dấu ngã (**~**). Dấu này nằm trong tập ký tự cookie-octet. Mã minh họa logic ứng dụng; trong sản phẩm, nên dùng thư viện encoding đã được kiểm chứng hoặc parser dùng chung thay vì tự xây dựng bộ percent-encoder tổng quát.

### 6.1. Ví dụ tạo cookie value

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;
import org.springframework.web.util.UriUtils;

class FeatureCookieCodec {

    String encode(List<String> flags) {
        return flags.stream()
            .map(value -> UriUtils.encode(value, StandardCharsets.UTF_8))
            .collect(java.util.stream.Collectors.joining("~"));
    }
}
~~~

**UriUtils.encode(...)** mã hóa dữ liệu theo quy tắc URI của Spring; cần xác nhận bộ ký tự được giữ lại phù hợp với contract cookie của ứng dụng. Nếu cần giới hạn chặt theo cookie-octet, hãy kiểm tra output và thêm validation trước khi đặt value vào Cookie.

### 6.2. Ví dụ decode có kiểm tra

Thêm method sau vào **FeatureCookieCodec** ở phần trên:

~~~java
List<String> decode(String cookieValue) {
    if (cookieValue == null || cookieValue.isBlank()) {
        return List.of();
    }

    return Arrays.stream(cookieValue.split("~", -1))
        .map(value -> UriUtils.decode(value, StandardCharsets.UTF_8))
        .toList();
}
~~~

Với input không hợp lệ, bộ decode có thể ném exception; API nên bắt lỗi và trả response theo hợp đồng thay vì âm thầm bỏ qua dữ liệu.

Ở hệ thống thực tế, hãy bổ sung giới hạn số lượng phần tử, độ dài tổng thể, độ dài mỗi phần tử, tập ký tự được phép, chính sách xử lý phần tử trùng lặp/rỗng và cách trả lỗi khi escape không hợp lệ.

## 7. Tài liệu hóa cookie nhiều giá trị bằng Spring REST Docs

Spring REST Docs mô tả **tên cookie**, không tự hiểu schema bên trong value. Ví dụ với cookie chứa danh sách:

~~~java
requestCookies(
    cookieWithName("feature-flags")
        .description("Danh sách mã tính năng, phân tách bằng dấu ~; từng phần tử được UTF-8 percent-encode")
)
~~~

Nếu request gửi nhiều cookie độc lập:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Mã ngôn ngữ ưu tiên, ví dụ vi"),
    cookieWithName("display-mode")
        .description("Chế độ giao diện, ví dụ compact"),
    cookieWithName("feature-flags")
        .description("Danh sách mã tính năng phân tách bằng dấu ~; phần tử UTF-8 percent-encoded")
)
~~~

Nếu response trả nhiều cookie:

~~~java
responseCookies(
    cookieWithName("locale")
        .description("Ngôn ngữ được lưu cho lần truy cập tiếp theo"),
    cookieWithName("display-mode")
        .description("Chế độ giao diện được lưu"),
    cookieWithName("feature-flags")
        .description("Danh sách mã tính năng phân tách bằng dấu ~ theo quy ước API")
)
~~~

Không đưa từng phần tử của **feature-flags** thành nhiều descriptor cùng tên. Descriptor là cho cookie **feature-flags**; schema danh sách cần được giải thích bằng description hoặc phần văn bản riêng.

### 7.1. Kết hợp cookie với response fields

Nếu API cũng trả danh sách trong JSON body, mô tả body bằng **responseFields(...)**:

~~~java
document("profile-preferences",
    requestCookies(
        cookieWithName("feature-flags")
            .description("Danh sách mã tính năng, UTF-8 percent-encoded")
    ),
    responseFields(
        fieldWithPath("enabledFeatures")
            .description("Các mã tính năng sau khi server decode cookie")
    )
)
~~~

Cookie descriptor và payload descriptor mô tả hai vị trí dữ liệu khác nhau. Không dùng **requestFields(...)** cho cookie vì cookie không nằm trong JSON request body.

## 8. Ví dụ kiểm thử MockMvc với cookie nhiều tên và encoded value

Ví dụ dùng **Java 17+**, **Spring Boot 3.x**, **JUnit 5** và **spring-restdocs-mockmvc**.

### 8.1. Controller đọc cookie

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriUtils;

@RestController
class PreferenceController {

    @GetMapping("/api/preferences")
    PreferenceView getPreferences(
            @CookieValue(name = "locale", defaultValue = "vi") String locale,
            @CookieValue(name = "feature-flags", required = false) String featureFlags) {

        List<String> flags = featureFlags == null || featureFlags.isBlank()
            ? List.of()
            : Arrays.stream(featureFlags.split("~", -1))
                .map(value -> UriUtils.decode(value, StandardCharsets.UTF_8))
                .toList();

        return new PreferenceView(locale, flags);
    }
}

record PreferenceView(String locale, List<String> enabledFeatures) {}
~~~

Đây là parser minh họa cho contract delimiter đã nêu. Ứng dụng thực tế nên kiểm tra đầu vào, giới hạn số lượng/độ dài và xử lý exception khi encoding không hợp lệ.

### 8.2. Test sinh request-cookies snippet

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

@WebMvcTest(PreferenceController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class PreferenceCookieEncodingTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentsMultipleCookiesAndEncodedListValue() throws Exception {
        mockMvc.perform(get("/api/preferences")
                .cookie(
                    new Cookie("locale", "vi"),
                    new Cookie("feature-flags",
                        "beta~sales%2Cwest~t%C3%ACm%20ki%E1%BA%BFm")
                )
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.locale").value("vi"))
            .andExpect(jsonPath("$.enabledFeatures[0]").value("beta"))
            .andExpect(jsonPath("$.enabledFeatures[1]").value("sales,west"))
            .andExpect(jsonPath("$.enabledFeatures[2]").value("tìm kiếm"))
            .andDo(document("preferences-cookie-list",
                requestCookies(
                    cookieWithName("locale")
                        .description("Mã ngôn ngữ ưu tiên"),
                    cookieWithName("feature-flags")
                        .description("Danh sách mã tính năng; các phần tử UTF-8 percent-encoded và phân tách bằng dấu ~")
                )
            ));
    }
}
~~~

MockMvc test gửi hai cookie độc lập. Cookie **feature-flags** có một value chứa ba phần tử, phân tách bằng dấu ~. Phần tử có dấu phẩy nội bộ được encode thành **%2C**, còn tiếng Việt được encode theo UTF-8. Dấu ~ được chọn vì thuộc tập cookie-octet; không dùng dấu phẩy thô làm delimiter cookie.

Servlet API và MockMvc quản lý cookie như những đối tượng riêng. Khi test bằng client HTTP thật, header Cookie trên wire có dạng nhiều cặp name=value ngăn cách bằng dấu chấm phẩy; hãy kiểm tra request thực tế nếu cần xác nhận encoding ở tầng network.

### 8.3. Kiểm tra response cookie nhiều giá trị

Nếu server trả cookie chứa danh sách, controller có thể tạo một cookie:

~~~java
Cookie features = new Cookie(
    "feature-flags",
    "beta~sales%2Cwest~t%C3%ACm%20ki%E1%BA%BFm");
features.setPath("/");
features.setHttpOnly(true);
features.setSecure(true);
response.addCookie(features);
~~~

Tài liệu hóa:

~~~java
responseCookies(
    cookieWithName("feature-flags")
        .description("Danh sách mã tính năng; phần tử được UTF-8 percent-encode và phân tách bằng dấu ~")
)
~~~

Test cần assert cookie value thực tế và có thể dùng **responseCookies(...)** để sinh **response-cookies.adoc**. Nếu value chứa dữ liệu nhạy cảm, dùng giá trị test giả hoặc preprocessing phù hợp trước khi ghi snippet.

## 9. Kết hợp encoding với bảo mật và giới hạn kích thước

Encoding không phải mã hóa bảo mật:

- Percent-encoding chỉ chuyển byte thành biểu diễn **%HH**; ai đọc cookie vẫn có thể decode.
- Base64URL chỉ thay đổi cách biểu diễn; không bảo vệ tính bí mật hoặc toàn vẹn.
- Cookie có thể bị sửa ở phía client, trừ khi server dùng cơ chế chữ ký/xác thực phù hợp.

Không lưu dữ liệu nhạy cảm hoặc danh sách quyền quyết định phân quyền vào cookie client có thể sửa nếu không có chữ ký và xác minh ở server. Với session/authentication, ưu tiên cookie mang session identifier khó đoán và dữ liệu quyền được kiểm soát phía server.

Cookie cũng có giới hạn kích thước và số lượng phụ thuộc browser, server và hạ tầng. RFC 6265 đưa ra các mức tối thiểu mà user agent nên hỗ trợ, nhưng không nên thiết kế API để dựa vào một giới hạn cụ thể của mọi trình duyệt. Giữ cookie nhỏ, tránh lặp payload JSON lớn qua mọi request và kiểm tra giới hạn của môi trường triển khai.

Khi nhiều cookie được đặt trong cùng response, mỗi cookie cần một **Set-Cookie** riêng với Path/Domain/Secure/SameSite phù hợp. Cookie cùng tên nhưng khác Path hoặc Domain có thể cùng tồn tại ở client; server cần tránh thiết kế mơ hồ khi đọc.

## 10. Tích hợp snippet vào Asciidoctor và CI

Sau khi test sinh **preferences-cookie-list**, cấu trúc snippet dự kiến:

~~~text
build/generated-snippets/
└── preferences-cookie-list/
    ├── http-request.adoc
    ├── http-response.adoc
    └── request-cookies.adoc
~~~

Trong **src/docs/asciidoc/preferences.adoc**:

~~~asciidoc
= Preferences API
:toc: left

== Lấy tùy chọn người dùng

GET /api/preferences

=== Request cookies

include::{snippets}/preferences-cookie-list/request-cookies.adoc[]

=== HTTP request

include::{snippets}/preferences-cookie-list/http-request.adoc[]

=== HTTP response

include::{snippets}/preferences-cookie-list/http-response.adoc[]

Cookie feature-flags chứa danh sách mã tính năng. Các phần tử được UTF-8 percent-encode riêng và phân tách bằng dấu ~; server tách trước rồi decode từng phần tử một lần.
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

Trong CI, chạy test trước Asciidoctor. Test nên xác nhận giá trị sau decode khớp dữ liệu mong đợi; tài liệu cần nêu rõ delimiter, charset và thứ tự encode/decode. Kiểm tra cả request snippet để chắc chắn không có giá trị bí mật hoặc cookie vượt giới hạn được công bố.

Nếu đầu ra cuối là Markdown, dùng converter hoặc cơ chế nhúng tương thích; **include::{snippets}/...[]** là cú pháp Asciidoctor, không phải Markdown chuẩn.

## 11. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Request có nhiều cookie nhưng bảng chỉ có một dòng | Chỉ khai báo một descriptor | Khai báo từng tên trong **requestCookies(...)** |
| Một cookie danh sách bị hiểu thành nhiều cookie | Nhầm delimiter trong value với dấu phân cách cookie | Phân biệt dấu chấm phẩy giữa cookie và delimiter do ứng dụng định nghĩa trong value |
| Phần tử chứa dấu phẩy bị tách sai | Không encode delimiter bên trong phần tử | Encode delimiter trong phần tử trước khi nối |
| Giá trị Unicode bị lỗi | Client/server không dùng cùng charset | Chuẩn hóa UTF-8 và kiểm tra byte/encoded value |
| Dấu cộng trở thành khoảng trắng không mong muốn | Dùng form decoding cho cookie | Quy định rõ percent-decoding hoặc Base64URL, không suy diễn quy tắc dấu cộng |
| Giá trị vẫn có **%20** sau khi đọc | Chưa decode hoặc decode sai tầng | Chỉ decode một lần tại điểm đã quy định |
| Giá trị **%2520** xuất hiện | Double encoding | Giữ dữ liệu gốc tới lúc encode; không encode lại giá trị đã encode |
| Cookie bị server từ chối | Có dấu cách, dấu chấm phẩy, dấu phẩy hoặc ký tự ngoài tập cookie-octet | Encode/validate value trước khi phát hành |
| REST Docs báo descriptor không khớp | Sai tên cookie hoặc nhầm request/response | Đối chiếu tên thực và nhóm descriptor |
| Cookie quá lớn hoặc request header quá dài | Nhét quá nhiều dữ liệu vào cookie | Rút gọn, chia dữ liệu hợp lý hoặc lưu phía server |

## 12. Bài thực hành

Thiết kế endpoint:

~~~text
GET /api/catalog
~~~

Hợp đồng cookie:

- **locale** là cookie riêng, có giá trị **vi** hoặc **en**.
- **feature-flags** là một cookie chứa danh sách mã tính năng.
- Các phần tử **feature-flags** được UTF-8 percent-encode riêng rồi nối bằng dấu ~.
- Server tách danh sách trước và decode từng phần tử đúng một lần.

Giá trị thử:

~~~text
Các phần tử: ["beta", "sales,west", "tìm kiếm"]
Cookie value: beta~sales%2Cwest~t%C3%ACm%20ki%E1%BA%BFm
~~~

Yêu cầu:

1. Viết parser cho **feature-flags** và kiểm tra đầu vào rỗng, delimiter, escape không hợp lệ, phần tử trùng lặp.
2. Viết MockMvc test gửi đồng thời **locale** và **feature-flags**.
3. Assert JSON response chứa đúng ba phần tử sau decode.
4. Dùng **requestCookies(...)** với hai descriptor riêng cho **locale** và **feature-flags**.
5. Thêm một test response phát hành **feature-flags** và dùng **responseCookies(...)**.
6. Tài liệu hóa rõ charset UTF-8, delimiter, thứ tự tách/decode và giới hạn độ dài.
7. Include cookie snippets vào Asciidoctor và chạy test → Asciidoctor trong CI.

**Tiêu chí hoàn thành:** phân biệt đúng nhiều cookie với một cookie có danh sách; giá trị encoded được decode chính xác một lần; descriptor khớp từng tên; snippet và tài liệu mô tả được schema cookie mà client cần tuân theo.

## Ghi nhớ

Một request có thể mang nhiều cookie độc lập, còn một cookie đơn có thể chứa danh sách hoặc dữ liệu cấu trúc theo quy ước riêng của ứng dụng. **requestCookies(...)** và **responseCookies(...)** mô tả từng cookie theo tên; chúng không tự hiểu schema bên trong value. Cookie value có giới hạn ký tự, vì vậy cần chọn delimiter hợp lệ trong cookie-octet, quy định encoding như UTF-8 percent-encoding hoặc Base64URL, thứ tự decode và giới hạn kích thước. Encoding không phải mã hóa bảo mật và không thay thế chữ ký/xác minh phía server. Hãy kiểm thử giá trị encoded qua MockMvc, sinh snippet bằng Spring REST Docs và mô tả rõ quy ước trong Asciidoctor/CI.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs CookieDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/cookies/CookieDocumentation.html), [RFC 6265: HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265) và [RFC 4648: Base-N Encodings](https://www.rfc-editor.org/rfc/rfc4648).
