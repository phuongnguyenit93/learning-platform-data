# Masking host hoặc thay thế pattern URI

## 1. Mục tiêu bài học

Trong module SPRING_REST_DOCS, ta tạo tài liệu REST API có thể kiểm chứng bằng các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Test gửi request, xác nhận response và Spring REST Docs sinh snippet cho request, response, payload, tham số và header. Các snippet được biên soạn bằng Asciidoctor/Markdown rồi đưa vào build và CI.

Request/response thực tế đôi khi chứa hostname nội bộ, domain của môi trường test, URL có token hoặc hypermedia link dài. Tài liệu cần minh họa cấu trúc API nhưng không nhất thiết phải công bố mọi giá trị môi trường hoặc URI riêng tư. Spring REST Docs cung cấp các operation preprocessor để thay đổi bản request/response trước khi sinh snippet.

Bài này tập trung vào ba công cụ:

- modifyUris(): thay scheme, host và port của URI trong operation.
- maskLinks(): che href của hypermedia links trong request/response.
- replacePattern(Pattern, String): thay các phần nội dung khớp biểu thức chính quy.

Sau bài học, bạn có thể chọn đúng công cụ để chuẩn hóa host, ẩn link hypermedia hoặc thay một pattern URI trong payload; kết hợp chúng với preprocessRequest(...)/preprocessResponse(...); và kiểm tra snippet để bảo đảm tài liệu vẫn có ý nghĩa.

## 2. Vì sao cần masking hoặc thay thế URI?

Giả sử test chạy tại hostname nội bộ:

~~~http
GET http://orders-service.test.svc.cluster.local:8080/api/orders/42 HTTP/1.1
~~~

Response trả về hypermedia link:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {
      "href": "http://orders-service.test.svc.cluster.local:8080/api/orders/42"
    },
    "payment": {
      "href": "http://payments.internal.local/private/txn/93821"
    }
  }
}
~~~

Khi công bố tài liệu, có thể cần thay hostname test bằng hostname sandbox/public, che một hypermedia link nếu client nên khám phá API qua quan hệ link, hoặc thay ID giao dịch và đoạn URI riêng tư bằng placeholder.

Không cần sửa request hoặc response mà ứng dụng thực sự xử lý. Preprocessor tác động lên bản operation mà Spring REST Docs chuẩn bị ghi thành snippet.

## 3. Chọn đúng preprocessor

Ba công cụ giải quyết ba vấn đề khác nhau:

| Công cụ | Phạm vi thay đổi | Trường hợp phù hợp |
| --- | --- | --- |
| modifyUris() | URI trong request/response, bao gồm request URI, header và content có URI | Thay host/scheme/port từ môi trường test sang địa chỉ tài liệu. |
| maskLinks() | Giá trị href của hypermedia links | Ẩn URI link để người đọc tập trung vào quan hệ link và dùng link do server trả về. |
| replacePattern(...) | Nội dung request hoặc response khớp regex | Thay một URI pattern/đoạn path/identifier có cấu trúc cụ thể bằng placeholder. |

~~~mermaid
flowchart TD
    A["Cần biến đổi URI trong snippet?"] --> B{"Phần nào cần thay?"}
    B -->|"Scheme / host / port"| C["modifyUris()"]
    B -->|"href hypermedia"| D["maskLinks()"]
    B -->|"Một chuỗi/pattern trong body"| E["replacePattern()"]
    C --> F["Kiểm tra request/response snippet"]
    D --> F
    E --> F
~~~

Nếu chỉ muốn đổi host, không dùng regex rộng để thay mọi chuỗi trông giống URL. Nếu muốn ẩn hyperlink, đừng xóa toàn bộ response body. Chọn preprocessor theo cấu trúc cần bảo toàn.

## 4. Thay hostname bằng modifyUris()

modifyUris() trả về UriModifyingOperationPreprocessor. Nó có thể thay scheme, host hoặc port của URI trong operation request/response.

Import tĩnh:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
~~~

Ví dụ thay hostname nội bộ bằng hostname sandbox:

~~~java
preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("sandbox-api.example.com")
        .removePort()
)
~~~

Khi dùng trong MockMvc:

~~~java
mockMvc.perform(get("/api/orders/42"))
    .andExpect(status().isOk())
    .andDo(document("orders/get",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("sandbox-api.example.com")
                .removePort()
        )
    ));
~~~

Request snippet được ghi theo địa chỉ sandbox. Đích request thực tế trong MockMvc không thay đổi.

### 4.1. Thay host nhưng giữ scheme và port

Nếu chỉ gọi modifyUris().host("sandbox-api.example.com"), preprocessor thay host và để scheme/port theo URI nguồn. Điều này hữu ích nếu scheme và port đã đúng, nhưng cần kiểm tra kết quả URL trong snippet vì port của môi trường test có thể vẫn còn.

### 4.2. Thay scheme, host và port

~~~java
modifyUris()
    .scheme("https")
    .host("api.example.com")
    .port(8443)
~~~

URI được ghi có dạng:

~~~text
https://api.example.com:8443/api/orders/42
~~~

Nếu API dùng port mặc định và không muốn hiển thị port, dùng removePort(). Hãy chọn địa chỉ mà client thực sự cần gọi; đừng thay bằng hostname production nếu bộ tài liệu dành cho sandbox.

### 4.3. Chuẩn hóa cả URI trong response

Một số response có Location hoặc hypermedia link chứa hostname nội bộ. Có thể áp dụng URI modifier cho response:

~~~java
preprocessResponse(
    modifyUris()
        .scheme("https")
        .host("sandbox-api.example.com")
        .removePort()
)
~~~

modifyUris() được thiết kế để thay URI trong operation, không chỉ request line. Nó có thể tác động đến URI trong request/response headers và content. Hãy kiểm tra kỹ những URI được thay trong snippet, nhất là khi response chứa liên kết tới nhiều dịch vụ khác nhau.

## 5. Che hypermedia link bằng maskLinks()

Nếu API dùng HAL hoặc định dạng hypermedia tương tự, response có thể cung cấp các link như self, next, payment. maskLinks() thay href của các link bằng ký hiệu che mặc định là dấu ba chấm đơn typographic.

Import:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.maskLinks;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
~~~

Ví dụ:

~~~java
mockMvc.perform(get("/api/orders/42"))
    .andExpect(status().isOk())
    .andDo(document("orders/get",
        preprocessResponse(maskLinks())
    ));
~~~

Response snippet vẫn mô tả cấu trúc representation và quan hệ link, nhưng href được che.

Trước khi mask:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    },
    "payment": {
      "href": "https://payments.example.com/api/payments/93821"
    }
  }
}
~~~

Sau khi mask:

~~~json
{
  "_links": {
    "self": {
      "href": "…"
    },
    "payment": {
      "href": "…"
    }
  }
}
~~~

Điều này hữu ích khi muốn người đọc sử dụng quan hệ link thay vì hard-code URI. Không dùng maskLinks() nếu tài liệu cần hướng dẫn cụ thể URL mà client phải gọi; khi đó nên chuẩn hóa URI bằng modifyUris() hoặc giữ nguyên link mẫu có chủ đích.

### 5.1. Tùy chỉnh ký hiệu thay thế

Có thể truyền chuỗi thay thế:

~~~java
preprocessResponse(
    maskLinks("[link omitted]")
)
~~~

Snippet sẽ dùng [link omitted] thay cho giá trị href. Chọn placeholder dễ hiểu với người đọc và nhất quán giữa các operation.

## 6. Thay URI pattern bằng replacePattern()

replacePattern(Pattern, String) cung cấp cơ chế tổng quát để thay mọi đoạn nội dung khớp regex trong request hoặc response.

Import:

~~~java
import java.util.regex.Pattern;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
~~~

Ví dụ response có URI nội bộ chứa mã giao dịch:

~~~json
{
  "id": 42,
  "receiptUrl": "https://payments.internal.local/private/transactions/93821"
}
~~~

Có thể thay phần hostname và transaction ID theo pattern cụ thể:

~~~java
preprocessResponse(
    replacePattern(
        Pattern.compile("https://payments\\.internal\\.local/private/transactions/[0-9]+"),
        "https://payments.example.com/transactions/{transactionId}"
    )
)
~~~

Snippet sẽ thể hiện URI mẫu:

~~~json
{
  "id": 42,
  "receiptUrl": "https://payments.example.com/transactions/{transactionId}"
}
~~~

Regex được áp dụng trên content của request/response đã ghi nhận. Nó không parse JSON và không phải công cụ chuyên biệt để thay request-line URI hoặc header URI. Nếu mục tiêu là thay URI ở các vị trí URI mà REST Docs nhận diện, ưu tiên modifyUris(). Nếu URI nằm trong một field body tùy biến, replacePattern(...) có thể xử lý nội dung đó. Pattern phải đủ đặc hiệu vì mọi đoạn content khớp regex đều có thể bị thay, kể cả đoạn không phải URI.

### 6.1. Thay một path segment

Nếu host đã đúng và chỉ cần thay mã định danh:

~~~java
replacePattern(
    Pattern.compile("/transactions/[0-9]+"),
    "/transactions/{transactionId}"
)
~~~

Kết quả giữ nguyên domain và các phần path không liên quan:

~~~text
https://payments.example.com/transactions/{transactionId}
~~~

### 6.2. Dùng nhóm bắt trong regex

Pattern có thể giữ lại một phần URI:

~~~java
replacePattern(
    Pattern.compile("https://([^/]+)/private/transactions/[0-9]+"),
    "https://$1/transactions/{transactionId}"
)
~~~

Nhóm bắt $1 giữ hostname đã khớp. Cách này phù hợp khi có nhiều hostname hợp lệ nhưng muốn loại phần path riêng tư. Khi viết replacement trong Java string, dùng $1 cho nhóm bắt; escape dấu gạch chéo ngược trong regex Java bằng hai dấu gạch chéo ngược.

## 7. Kết hợp modifyUris() và replacePattern()

Một response có thể vừa chứa host môi trường test vừa chứa một URI path cần ẩn. Có thể xâu chuỗi hai preprocessor trong preprocessResponse(...):

~~~java
mockMvc.perform(get("/api/orders/42"))
    .andExpect(status().isOk())
    .andDo(document("orders/get",
        preprocessResponse(
            modifyUris()
                .scheme("https")
                .host("sandbox-api.example.com")
                .removePort(),
            replacePattern(
                Pattern.compile("/private/transactions/[0-9]+"),
                "/transactions/{transactionId}"
            )
        )
    ));
~~~

Preprocessor được áp dụng theo thứ tự truyền vào. modifyUris() chuẩn hóa URI trước; replacePattern(...) tiếp tục thay path pattern trong nội dung operation đã được xử lý. Xác minh kết quả cuối để chắc rằng pattern vẫn khớp sau bước chuẩn hóa đầu tiên.

Nếu muốn xử lý cả request lẫn response, khai báo preprocessor tương ứng cho từng phía:

~~~java
document("orders/get",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("sandbox-api.example.com")
            .removePort()
    ),
    preprocessResponse(
        maskLinks("[link omitted]")
    )
)
~~~

Không đặt response preprocessor ở vị trí request hoặc ngược lại. document(...) nhận request preprocessor trước và response preprocessor sau.

## 8. Ví dụ MockMvc hoàn chỉnh

Ví dụ dưới đây minh họa response có self link và receipt URL. Test kiểm tra HTTP response thực tế, còn REST Docs tạo snippet đã chuẩn hóa và ẩn mã giao dịch.

~~~java
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class UriMaskingDocumentationTest {

    private final MockMvc mockMvc;

    UriMaskingDocumentationTest(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @Test
    void documentsOrderWithSanitizedUris() throws Exception {
        this.mockMvc.perform(get("/api/orders/42"))
            .andExpect(status().isOk())
            .andDo(document("orders/get",
                preprocessResponse(
                    modifyUris()
                        .scheme("https")
                        .host("sandbox-api.example.com")
                        .removePort(),
                    replacePattern(
                        Pattern.compile("/private/transactions/[0-9]+"),
                        "/transactions/{transactionId}"
                    )
                )
            ));
    }
}
~~~

Ví dụ giả định MockMvc đã được cấu hình REST Docs filter và endpoint trả response JSON có URI trong link/body. modifyUris() thay scheme/host/port của URI; replacePattern(...) thay đoạn path riêng tư. Response mà endpoint trả về cho assertion vẫn là response thật.

Nếu mục tiêu là che toàn bộ href hypermedia thay vì thay một URI pattern cụ thể, dùng preprocessResponse(maskLinks()). Không cần tự viết regex để parse JSON links.

## 9. Phân biệt thay URI và che link

| Nhu cầu | Chọn | Kết quả |
| --- | --- | --- |
| Đổi host orders.test.local thành api.example.com nhưng giữ path | modifyUris().host("api.example.com") | href vẫn là URI có thể đọc và truy cập theo domain mới. |
| Không muốn công bố URL đích của hypermedia link | maskLinks() | href được thay bằng placeholder. |
| Muốn ẩn riêng ID giao dịch trong một URI | replacePattern(...) | Giữ cấu trúc URL, thay phần ID bằng token mẫu. |
| Muốn thay cả scheme, host và port | modifyUris() với nhiều setter | Các URI được xử lý dùng authority đã chọn. |
| Muốn sửa một chuỗi URI trong JSON không được nhận diện như link | replacePattern(...) | Thay nội dung khớp regex ở bất kỳ vị trí nào trong content. |

maskLinks() dành cho hypermedia link có trường href; replacePattern(...) là thay thế chuỗi tổng quát. Nếu response là JSON tùy biến và URI nằm trong receiptUrl, downloadUrl hoặc field khác, replacePattern(...) có thể phù hợp hơn nếu pattern đủ chính xác.

## 10. Cẩn trọng khi dùng regex

replacePattern(...) không parse JSON, XML hay URI theo ngữ nghĩa. Nó thay chuỗi dựa trên regex trên nội dung operation. Các lỗi dễ gặp:

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Pattern quá rộng như https://.* | Thay cả nhiều URL không liên quan hoặc nuốt quá nhiều ký tự. | Giới hạn hostname, path segment và ký tự kết thúc. |
| Quên escape dấu chấm trong hostname | Regex match nhiều ký tự thay vì dấu chấm literal. | Dùng \\. trong Java regex string. |
| Thay ID bằng pattern chỉ dựa vào số | Có thể thay các số nghiệp vụ khác trong body. | Neo pattern theo path cụ thể như /transactions/[0-9]+. |
| Replacement có $ không đúng | Java regex hiểu $1 là group reference; replacement có thể lỗi nếu group không tồn tại. | Kiểm tra số nhóm bắt hoặc dùng chuỗi thay thế không chứa ký hiệu nhóm. |
| Giả định regex chỉ thay trong một JSON field | Pattern có thể thay ở mọi vị trí trong content. | Viết pattern đặc hiệu và xem toàn bộ snippet sau xử lý. |
| Dùng regex để ẩn tất cả hypermedia href | Có thể làm hỏng cấu trúc JSON hoặc thay các URL không liên quan. | Dùng maskLinks() cho link hypermedia. |

Không dùng preprocessor để che dữ liệu nhạy cảm rồi cho rằng dữ liệu test an toàn. Request/response vẫn tồn tại trong quá trình test, log và các hệ thống khác. Dùng fixture giả cho test và kiểm tra nơi dữ liệu được lưu trước khi chia sẻ artifact.

## 11. Kiểm tra snippet sau khi preprocessing

Sau khi test chạy, mở operation snippet tương ứng, ví dụ:

~~~text
build/generated-snippets/orders/get/http-response.adoc
~~~

Kiểm tra:

1. Host đã đổi đúng domain sandbox/public chưa.
2. Scheme và port có đúng chính sách URI tài liệu không.
3. Hypermedia href có được che bằng placeholder mong đợi không.
4. Pattern URI chỉ thay phần cần thay, không ảnh hưởng ID hoặc path khác.
5. JSON/XML vẫn hợp lệ và phần payload quan trọng còn đọc được.
6. Response assertion trong test vẫn kiểm tra giá trị thực tế, không phải giá trị sau preprocessing.

Một preprocessor có thể làm snippet đẹp hơn nhưng không thay thế assertion. Test phải xác nhận ứng dụng trả response đúng trước khi REST Docs biến đổi bản ghi phục vụ tài liệu.

## 12. Tích hợp Asciidoctor và CI

Asciidoctor có thể include request/response snippet đã preprocessing:

~~~asciidoc
= Orders API
:snippets: build/generated-snippets

== Lấy đơn hàng

=== HTTP response
include::{snippets}/orders/get/http-response.adoc[]
~~~

Giả sử plugin Asciidoctor đã được cấu hình, nối task dựng tài liệu với test:

~~~groovy
def snippetsDir = layout.buildDirectory.dir("generated-snippets")

tasks.named("test") {
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(snippetsDir)
    attributes "snippets": snippetsDir.get().asFile
}
~~~

CI có thể chạy:

~~~bash
./gradlew clean test asciidoctor
~~~

Test xác nhận hành vi API; preprocessors tạo bản request/response phù hợp cho tài liệu; Asciidoctor ghép snippet mới. Khi hostname hoặc URI format đổi, review các snippet đã preprocessing cùng thay đổi API.

Với Markdown thuần, cú pháp include:: của Asciidoctor không tự được xử lý. Cần bước build riêng để nhúng snippet hoặc liên kết tới tệp đã sinh.

## 13. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân và cách xử lý |
| --- | --- |
| Host nội bộ vẫn xuất hiện | Chưa áp dụng modifyUris() đúng phía request/response hoặc URI nằm trong dạng content mà preprocessor không nhận diện. |
| URI response không đổi nhưng request đã đổi | Preprocessor chỉ được đặt trong preprocessRequest(...); thêm preprocessResponse(...) nếu response cũng cần chuẩn hóa. |
| Hypermedia href vẫn dài | Dùng maskLinks() trong response preprocessor và kiểm tra link có được biểu diễn theo hypermedia format hỗ trợ. |
| Các URL không liên quan cũng bị thay | Regex replacePattern(...) quá rộng; thu hẹp pattern theo hostname và path. |
| JSON snippet không còn hợp lệ | Pattern đã thay cả dấu ngoặc kép hoặc ký tự cấu trúc; điều chỉnh regex/replacement rồi đọc lại payload. |
| ID khác bị che ngoài ý muốn | Pattern đang match mọi dãy số; gắn pattern với path segment cụ thể. |
| Test pass dù snippet bị che sai | Assertion đang kiểm tra response gốc; thêm kiểm tra/review snippet cho quy tắc tài liệu quan trọng. |
| Snippet vẫn chứa dữ liệu nhạy cảm | Chưa nhận diện tất cả vị trí chứa dữ liệu hoặc chỉ xử lý response mà quên request; rà soát cả hai phía. |

## 14. Bài thực hành

1. Tạo response HAL có _links.self.href chứa hostname nội bộ.
2. Dùng modifyUris() để thay scheme/host/port và kiểm tra snippet.
3. Dùng maskLinks() để thay toàn bộ href; so sánh cấu trúc JSON trước và sau.
4. Đặt maskLinks("[link omitted]") và xem placeholder hiển thị trong snippet.
5. Tạo receiptUrl có transaction ID; dùng replacePattern(Pattern, String) để thay ID bằng {transactionId}.
6. Cố ý dùng regex rộng, quan sát các chuỗi ngoài ý muốn bị thay, rồi thu hẹp pattern.
7. Kết hợp modifyUris() và replacePattern(...) trong một response preprocessor; xác nhận thứ tự và kết quả.
8. Chạy ./gradlew clean test asciidoctor và review response snippet trước khi đưa tài liệu vào CI artifact.

## 15. Ghi nhớ

- modifyUris() thay scheme, host và port của URI trong operation request/response; dùng để chuẩn hóa hostname môi trường.
- maskLinks() thay href của hypermedia links bằng placeholder; phù hợp khi muốn client khám phá API qua quan hệ link.
- replacePattern(Pattern, String) thay nội dung khớp regex trong request hoặc response; phù hợp với URI pattern/identifier cụ thể.
- Dùng preprocessRequest(...) cho bản request và preprocessResponse(...) cho bản response.
- Regex phải đặc hiệu; preprocessor chuỗi không parse cấu trúc JSON/XML.
- Preprocessor chỉ thay bản ghi để sinh snippet, không thay đổi request/response thực tế của endpoint và không thay thế assertion.
- Luôn đọc lại snippet sau khi xử lý để chắc host đã chuẩn hóa, link được che đúng và payload vẫn có ý nghĩa.

## 16. Tài liệu tham khảo

- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html): tài liệu về maskLinks, modifyUris, replacePattern và preprocessors.
- [Spring REST Docs — Preprocessors API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html): factory methods và phạm vi xử lý của các preprocessor.
