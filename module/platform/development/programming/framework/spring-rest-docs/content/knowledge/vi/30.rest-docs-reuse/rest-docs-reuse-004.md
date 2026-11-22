# Tái sử dụng header và cookie descriptors

## 1. Vì sao cần tái sử dụng header và cookie descriptors?

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Test gửi request, xác nhận response, rồi dùng descriptor để mô tả headers, cookies, payload, parameters và hypermedia links. Những snippet được sinh ra sẽ được biên soạn thành Asciidoctor/Markdown và đưa vào build, CI.

Nhiều endpoint dùng chung một số headers và cookies. Ví dụ:

- Request thường gửi Accept để khai báo media type mong muốn.
- Request có body JSON gửi Content-Type.
- API bảo vệ bằng bearer token có header Authorization.
- API đa ngôn ngữ có thể dùng Accept-Language.
- Session-based application có thể nhận cookie JSESSIONID.
- Response có thể trả Cache-Control, ETag, Set-Cookie hoặc correlation header.

Nếu khai báo lại cùng một descriptor ở hàng chục test, mô tả dễ lệch nhau. Tập trung các descriptor dùng chung vào helper giúp tài liệu nhất quán và giảm lặp.

## 2. HeaderDescriptor và CookieDescriptor

Spring REST Docs cung cấp descriptor chuyên biệt cho mỗi loại metadata HTTP:

| Descriptor | Mục đích | API tạo descriptor |
| --- | --- | --- |
| HeaderDescriptor | Mô tả một HTTP header | headerWithName("...") |
| CookieDescriptor | Mô tả một cookie | cookieWithName("...") |

Descriptor có thể khai báo description, trạng thái optional/ignored và attributes bổ sung. Chúng được truyền cho snippet tương ứng:

| Snippet API | Phạm vi |
| --- | --- |
| requestHeaders(...) | Header client gửi |
| responseHeaders(...) | Header server trả |
| requestCookies(...) | Cookie client gửi |
| responseCookies(...) | Cookie server trả |

Header và cookie là hai cấu trúc khác nhau. Cookie được truyền trong request bằng header Cookie, còn server gửi cookie qua Set-Cookie. Spring REST Docs có cookie descriptors để tài liệu hóa cookie theo tên và thuộc tính; dùng header descriptor cho toàn bộ Cookie header không thay thế cho cookie descriptors khi mục tiêu là mô tả từng cookie.

## 3. Khai báo descriptor dùng chung cho request headers

Ví dụ một API thường nhận các headers:

- Accept: media type client muốn nhận.
- Content-Type: media type của request body.
- Authorization: bearer token dùng xác thực.
- X-Correlation-ID: mã tương quan để theo dõi request.

Tạo helper trả về các descriptor chuẩn:

~~~java
import org.springframework.restdocs.headers.HeaderDescriptor;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;

final class ApiHeaderDescriptors {

    private ApiHeaderDescriptors() {
    }

    static HeaderDescriptor[] commonRequestHeaders() {
        return new HeaderDescriptor[] {
                headerWithName("Accept")
                        .description("Media type mà client chấp nhận"),
                headerWithName("Content-Type")
                        .optional()
                        .description("Media type của request body"),
                headerWithName("Authorization")
                        .description("Bearer token dùng để xác thực"),
                headerWithName("X-Correlation-ID")
                        .description("Mã tương quan của request")
        };
    }
}
~~~

Mỗi lần gọi commonRequestHeaders(), helper tạo một mảng descriptor mới. Có thể dùng helper ở nhiều operation:

~~~java
document("orders-create",
        requestHeaders(ApiHeaderDescriptors.commonRequestHeaders()),
        requestFields(orderRequestFields()));

document("customers-update",
        requestHeaders(ApiHeaderDescriptors.commonRequestHeaders()),
        requestFields(customerRequestFields()));
~~~

Hai operation dùng chung cách diễn đạt cho headers mà API yêu cầu. Khi thuật ngữ hoặc chính sách header thay đổi, cập nhật helper rồi chạy lại documentation tests để sinh snippet thống nhất.

Chỉ đưa vào snippet những headers thực sự có mặt trong request. Nếu endpoint không gửi Content-Type vì không có body, đừng đưa descriptor bắt buộc cho header đó vào operation.

## 4. Tái sử dụng response header descriptors

Request headers và response headers có ngữ nghĩa khác nhau, vì vậy nên định nghĩa helper riêng. Ví dụ response có Content-Type, Cache-Control, ETag và X-Correlation-ID:

~~~java
import org.springframework.restdocs.headers.HeaderDescriptor;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;

final class ApiResponseHeaderDescriptors {

    private ApiResponseHeaderDescriptors() {
    }

    static HeaderDescriptor[] commonResponseHeaders() {
        return new HeaderDescriptor[] {
                headerWithName("Content-Type")
                        .description("Media type của response"),
                headerWithName("Cache-Control")
                        .description("Chính sách cache của response"),
                headerWithName("ETag")
                        .description("Validator đại diện cho phiên bản representation"),
                headerWithName("X-Correlation-ID")
                        .description("Mã tương quan để theo dõi request")
        };
    }
}
~~~

Sử dụng trong operation:

~~~java
document("orders-get",
        responseHeaders(
                ApiResponseHeaderDescriptors.commonResponseHeaders()));
~~~

Không dùng một mảng descriptor response cho request chỉ vì tên header giống nhau. Content-Type ở request mô tả định dạng body client gửi; ở response mô tả định dạng body server trả.

## 5. Cookie descriptors dùng chung

Với session-based application, nhiều request có thể gửi cookie JSESSIONID. Một số ứng dụng còn dùng cookie locale, remember-me hoặc cookie CSRF. Tạo helper cho request cookies:

~~~java
import org.springframework.restdocs.cookies.CookieDescriptor;

import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;

final class ApiCookieDescriptors {

    private ApiCookieDescriptors() {
    }

    static CookieDescriptor[] commonRequestCookies() {
        return new CookieDescriptor[] {
                cookieWithName("JSESSIONID")
                        .description("Mã phiên đăng nhập của client"),
                cookieWithName("locale")
                        .optional()
                        .description("Ngôn ngữ hiển thị được client lựa chọn")
        };
    }
}
~~~

Khi document một request:

~~~java
document("account-get",
        requestCookies(ApiCookieDescriptors.commonRequestCookies()));
~~~

Cookie JSESSIONID được mô tả như cookie bắt buộc trong operation này; locale là tùy chọn. Trạng thái required/optional phải theo hợp đồng của endpoint, không nhất thiết giống nhau ở mọi API.

### Response cookies

Nếu server tạo session hoặc cập nhật cookie, có thể định nghĩa bộ response cookie riêng:

~~~java
static CookieDescriptor[] commonResponseCookies() {
    return new CookieDescriptor[] {
            cookieWithName("JSESSIONID")
                    .description("Cookie phiên do server cấp"),
            cookieWithName("locale")
                    .optional()
                    .description("Cookie lưu lựa chọn ngôn ngữ")
    };
}
~~~

Và sử dụng:

~~~java
document("login",
        responseCookies(ApiCookieDescriptors.commonResponseCookies()));
~~~

Chỉ mô tả response cookie nếu response thực tế có cookie tương ứng, thường được gửi qua Set-Cookie. Không giả định mọi response đều phát hành lại session cookie.

## 6. Kết hợp descriptor chung và descriptor riêng của operation

Một endpoint có thể dùng bộ header chung và thêm header riêng, chẳng hạn If-Match khi cập nhật tài nguyên có optimistic locking.

Có thể tạo helper ghép descriptor:

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

static HeaderDescriptor[] withAdditionalHeaders(
        HeaderDescriptor[] common,
        HeaderDescriptor... specific) {
    return Stream.concat(Arrays.stream(common), Arrays.stream(specific))
            .toArray(HeaderDescriptor[]::new);
}
~~~

Sử dụng:

~~~java
requestHeaders(withAdditionalHeaders(
        ApiHeaderDescriptors.commonRequestHeaders(),
        headerWithName("If-Match")
                .description("ETag phiên bản mà client đã đọc")));
~~~

Nếu cần ghép cookie chung với cookie riêng, có thể áp dụng cùng cách với CookieDescriptor[]. Chỉ nên tạo abstraction ghép mảng nếu dự án có nhiều operation thật sự cần; với một hoặc hai endpoint, khai báo trực tiếp thường dễ đọc hơn.

## 7. Ví dụ MockMvc hoàn chỉnh

Ví dụ sau minh họa request gửi headers/cookies và response trả headers/cookies. Giả định ứng dụng có endpoint session-based /api/account và các headers/cookies nêu trong descriptor thực sự được gửi/trả.

~~~java
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs
class AccountDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void getAccountDocumentsReusableHeadersAndCookies() throws Exception {
        mockMvc.perform(get("/api/account")
                        .accept(MediaType.APPLICATION_JSON)
                        .header("Authorization", "Bearer test-token")
                        .header("X-Correlation-ID", "test-correlation-001")
                        .cookie(new Cookie("JSESSIONID", "session-fixture"),
                                new Cookie("locale", "vi")))
                .andExpect(status().isOk())
                .andDo(document("account-get",
                        requestHeaders(ApiHeaderDescriptors.commonRequestHeaders()),
                        requestCookies(ApiCookieDescriptors.commonRequestCookies()),
                        responseHeaders(ApiResponseHeaderDescriptors.commonResponseHeaders()),
                        responseCookies(ApiCookieDescriptors.commonResponseCookies())));
    }
}
~~~

Ví dụ phải điều chỉnh theo response thật và cấu hình session của ứng dụng. Nếu ứng dụng không dùng cookie session hoặc không trả ETag, Cache-Control hay response cookie trong operation này, hãy thay helper/descriptor cho phù hợp hoặc không đưa snippet đó vào operation.

Giá trị cookie/header trong tài liệu nên là fixture giả. Không ghi session ID hoặc bearer token còn hiệu lực từ môi trường chạy thật.

## 8. Required, optional và ignored khi tái sử dụng

Descriptor có thể mang trạng thái optional() hoặc ignored(). Cân nhắc các trạng thái này khi tái sử dụng:

- Dùng descriptor bắt buộc khi header/cookie phải có theo hợp đồng operation.
- Dùng optional() khi hợp lệ để header/cookie vắng mặt.
- Dùng ignored() khi chủ ý không đưa header/cookie vào snippet và kiểm tra descriptor.

Không nên tạo một descriptor dùng chung đã gọi optional() chỉ vì một endpoint cho phép vắng mặt, rồi dùng nguyên descriptor đó cho endpoint khác yêu cầu header bắt buộc.

Một cách an toàn là dùng factory tạo descriptor mới:

~~~java
static HeaderDescriptor correlationIdHeader() {
    return headerWithName("X-Correlation-ID")
            .description("Mã tương quan của request");
}

static HeaderDescriptor optionalTraceHeader() {
    return headerWithName("X-Trace-Parent")
            .optional()
            .description("Thông tin trace nếu client gửi");
}
~~~

Operation bắt buộc dùng correlationIdHeader(); operation cho phép thiếu trace dùng optionalTraceHeader(). Nhờ đó trạng thái descriptor gắn với ý định rõ ràng.

## 9. Chia sẻ descriptor qua helper hoặc lớp tiện ích

| Cách tổ chức | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| Static factory methods | Nhiều test trong cùng module | Đơn giản, dễ đọc |
| Utility class theo nhóm API | Nhiều bộ endpoint dùng chung header/cookie | Tách request và response rõ ràng |
| Test fixture module | Nhiều module cần cùng mô tả | Cần đưa fixture vào test runtime classpath |
| Descriptor builder theo profile | API có nhóm public, internal, admin | Tránh ghép bộ descriptor quá rộng |

Ví dụ cấu trúc source:

~~~text
src/test/java/
└── com/example/docs/
    ├── descriptors/
    │   ├── ApiHeaderDescriptors.java
    │   ├── ApiResponseHeaderDescriptors.java
    │   └── ApiCookieDescriptors.java
    └── tests/
        ├── AccountDocumentationTest.java
        └── OrderDocumentationTest.java
~~~

Không đưa helper test-only vào package production nếu ứng dụng không cần nó ở runtime. Nếu nhiều module cần dùng chung, đóng gói helper vào test fixtures phù hợp thay vì phụ thuộc chéo vào source test của module khác.

## 10. Cookie và header không phải nơi lưu bí mật trong tài liệu

Headers như Authorization, Cookie và Set-Cookie có thể chứa token hoặc session identifier. Khi document request/response, cần kiểm tra dữ liệu được ghi vào snippet:

- Dùng token giả hoặc giá trị đã làm sạch.
- Xóa hoặc thay thế header nhạy cảm bằng operation preprocessors nếu cần.
- Không dùng cookie session thật lấy từ trình duyệt hoặc môi trường staging/production.
- Kiểm tra http-request, http-response, request-headers và các snippet cookie trước khi commit.

Mục tiêu của descriptor là mô tả tên và ý nghĩa header/cookie. Không cần công bố giá trị bí mật để giải thích hợp đồng API.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Header descriptor không khớp request | Header không thực sự được gửi hoặc sai tên | Kiểm tra request fixture và tên header |
| Response header không được tìm thấy | Endpoint không trả header đó trong operation | Xác nhận response thực tế trước khi dùng descriptor bắt buộc |
| Cookie descriptor không tìm thấy cookie | Cookie không có trong request/response hoặc test setup sai | Kiểm tra Cookie/Set-Cookie và dùng đúng requestCookies/responseCookies |
| Một endpoint vô tình coi header là optional | Tái sử dụng descriptor đã gọi optional() | Tạo factory riêng cho trạng thái required và optional |
| Mô tả request/response header bị lẫn | Dùng chung nội dung mô tả không đúng chiều truyền | Tách helper request headers và response headers |
| Test lặp lại nhiều mô tả khác nhau | Descriptor bị khai báo lại ở mỗi operation | Chuyển phần thực sự dùng chung vào helper |
| Snippet chứa session/token thật | Fixture dùng dữ liệu môi trường | Dùng fixture giả hoặc preprocess trước khi ghi tài liệu |
| Build không tìm thấy helper ở module khác | Test fixture không có trên test runtime classpath | Thêm dependency test-fixtures hoặc khai báo helper cục bộ |

Khi test thất bại, xem HTTP operation thực tế trước. Descriptor phải phản ánh headers/cookies đang được gửi hoặc trả bởi request; helper tái sử dụng không làm một header tự xuất hiện trong HTTP message.

## 12. Bài thực hành

1. Tạo helper ApiHeaderDescriptors với các request headers chung của API.
2. Tạo helper riêng cho response headers và xác định những header endpoint nào thật sự trả.
3. Tạo ApiCookieDescriptors cho request cookie và response cookie.
4. Dùng lại helper trong hai documentation tests khác nhau; kiểm tra mô tả được giữ thống nhất.
5. Thêm header riêng If-Match cho endpoint cập nhật và ghép với bộ descriptor chung.
6. Tạo hai biến thể descriptor required và optional; xác nhận endpoint có hợp đồng khác nhau không dùng nhầm trạng thái.
7. Kiểm tra snippet được sinh không chứa bearer token hoặc session ID thật.

**Tiêu chí hoàn thành:** phân biệt HeaderDescriptor và CookieDescriptor; tái sử dụng bằng helper/factory; tách request và response descriptors; ghép descriptor chung với descriptor riêng; xử lý required/optional đúng hợp đồng; bảo vệ giá trị nhạy cảm trong snippet.

## 13. Checklist trước khi commit

- [ ] Header/cookie descriptors được phân loại đúng request hoặc response.
- [ ] Mô tả dùng chung được đặt trong helper có tên rõ nghĩa.
- [ ] Descriptor factory trả về trạng thái phù hợp với operation.
- [ ] Không tái sử dụng một descriptor optional cho operation yêu cầu bắt buộc.
- [ ] Cookie được mô tả bằng cookie descriptors khi cần tài liệu hóa từng cookie.
- [ ] Chỉ đưa descriptor vào operation nếu header/cookie thực sự có trong message.
- [ ] Giá trị Authorization/Cookie/Set-Cookie dùng fixture giả hoặc đã được làm sạch.
- [ ] Test được chạy để sinh lại request/response header và cookie snippets.
- [ ] Asciidoctor/Markdown build thành công với snippet mới.

**Ghi nhớ:** HeaderDescriptor và CookieDescriptor giúp mô tả headers/cookies theo cách thống nhất. Tạo helper hoặc factory cho nhóm metadata dùng chung, tách request khỏi response và tạo descriptor mới theo trạng thái required/optional của từng operation sẽ giúp tài liệu Spring REST Docs dễ bảo trì mà vẫn phản ánh đúng HTTP message thực tế.
