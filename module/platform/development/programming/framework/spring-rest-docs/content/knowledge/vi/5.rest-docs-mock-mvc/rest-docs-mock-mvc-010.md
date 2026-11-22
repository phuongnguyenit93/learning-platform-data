# Tiền xử lý request và response của MockMvc

## Mục tiêu bài học

Khi dùng **MockMvc** cùng **Spring REST Docs**, request và response được ghi lại từ bài kiểm thử có thể chứa dữ liệu không phù hợp để đưa thẳng vào tài liệu: JSON khó đọc, host nội bộ, cổng ngẫu nhiên, header phục vụ kiểm thử, token hoặc giá trị cần che. **Operation preprocessors** cho phép chuẩn hóa request/response trước khi REST Docs tạo snippet.

Trong module **SPRING_REST_DOCS**, ta xây dựng tài liệu REST API có thể kiểm chứng từ HTTP test bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn Asciidoctor/Markdown và đưa vào quy trình build, CI.

Sau bài học này, bạn có thể:

- Giải thích vị trí của preprocessing trong luồng MockMvc và Spring REST Docs.
- Dùng **preprocessRequest(...)** và **preprocessResponse(...)** để áp dụng các bộ xử lý vào operation được document.
- Làm đẹp JSON/XML, chuẩn hóa URI và xóa header không cần công bố.
- Che hoặc thay thế dữ liệu nhạy cảm trước khi sinh snippet.
- Chọn phạm vi áp dụng ở từng **document(...)** hoặc cấu hình dùng chung.
- Phân biệt dữ liệu được tiền xử lý cho tài liệu với dữ liệu ứng dụng thực sự nhận/trả.
- Kiểm tra snippet sau preprocessing và tích hợp tác vụ sinh tài liệu vào build/CI.

## 1. Preprocessing nằm ở đâu trong luồng tài liệu?

Một test MockMvc thông thường gửi request tới controller, kiểm tra status và response, sau đó gọi **document(...)** để sinh snippet:

~~~java
mockMvc.perform(get("/api/orders/{orderId}", 42L))
    .andExpect(status().isOk())
    .andDo(document("order-get"));
~~~

Khi thêm preprocessing, ta yêu cầu REST Docs biến đổi bản ghi operation trước khi tạo các snippet:

~~~java
mockMvc.perform(get("/api/orders/{orderId}", 42L))
    .andExpect(status().isOk())
    .andDo(document("order-get",
        preprocessRequest(prettyPrint()),
        preprocessResponse(prettyPrint())
    ));
~~~

Luồng khái quát:

~~~mermaid
flowchart TD
    A["MockMvc request"] --> B["Spring MVC xử lý request"]
    B --> C["HTTP response"]
    C --> D["Các assertion trong test"]
    D --> E["document(...) nhận operation"]
    E --> F["Preprocess request / response"]
    F --> G["Sinh request, response và payload snippets"]
    G --> H["Asciidoctor / tài liệu API"]
~~~

Preprocessor tác động lên **operation được REST Docs ghi lại để tạo tài liệu**. Nó không thay thế controller, không thay đổi logic service và không phải middleware dùng để sửa request trước khi ứng dụng xử lý. Ví dụ **prettyPrint()** không làm JSON mà controller trả về thay đổi; nó định dạng bản JSON trong snippet.

### 1.1. Hai nhóm hàm chính

| Hàm | Áp dụng lên | Mục đích |
| --- | --- | --- |
| **preprocessRequest(...)** | Bản ghi HTTP request | Chuẩn hóa URI, format body, loại header hoặc che dữ liệu request |
| **preprocessResponse(...)** | Bản ghi HTTP response | Format body, loại header, che dữ liệu response |

Các hàm này thường được import từ:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
~~~

Một operation có thể dùng cả hai nhóm hoặc chỉ một nhóm. Không cần tiền xử lý request nếu chỉ cần chuẩn hóa response, và ngược lại.

## 2. Làm đẹp body bằng prettyPrint()

JSON hoặc XML trong snippet mặc định có thể khó đọc nếu nội dung được ghi dưới dạng một dòng. **prettyPrint()** định dạng body để tài liệu dễ xem.

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

mockMvc.perform(get("/api/orders/{orderId}", 42L)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("order-get",
        preprocessRequest(prettyPrint()),
        preprocessResponse(prettyPrint())
    ));
~~~

Ví dụ JSON trước khi định dạng:

~~~json
{"id":42,"status":"OPEN","customer":{"name":"Lan","active":true}}
~~~

Sau khi định dạng:

~~~json
{
  "id": 42,
  "status": "OPEN",
  "customer": {
    "name": "Lan",
    "active": true
  }
}
~~~

**prettyPrint()** hữu ích khi body là JSON/XML mà bộ tiền xử lý nhận diện và xử lý được. Nó không thay thế **requestFields(...)** hoặc **responseFields(...)**: snippet body trình bày payload, còn field snippets mô tả ý nghĩa và cấu trúc của từng trường.

Nếu test không gửi hoặc không nhận body, pretty print không tạo ra nội dung body mới. Hãy giữ đúng **Content-Type** và kiểm tra snippet được sinh ra để bảo đảm định dạng cuối phù hợp.

## 3. Chuẩn hóa URI trong request snippet

Trong CI, MockMvc có thể ghi nhận host, scheme hoặc port khác với URL công khai. Ví dụ tài liệu mong muốn hiển thị:

~~~http
https://api.example.com/api/orders/42
~~~

nhưng test lại ghi:

~~~http
http://localhost:51827/api/orders/42
~~~

Dùng **modifyUris()** để chuẩn hóa URI trong tài liệu:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

mockMvc.perform(get("/api/orders/{orderId}", 42L))
    .andExpect(status().isOk())
    .andDo(document("order-get",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("api.example.com")
                .removePort()
        )
    ));
~~~

Nếu tài liệu cần cổng công khai cụ thể, có thể dùng **port(...)** thay cho **removePort()**:

~~~java
modifyUris()
    .scheme("https")
    .host("api.example.com")
    .port(443)
~~~

Việc chuẩn hóa này chỉ thay đổi URI được ghi trong snippet. Nó không chuyển request thực sang host **api.example.com**, không thay đổi môi trường chạy test và không kiểm tra DNS/TLS. Hãy sử dụng host công khai theo hợp đồng API, tránh ghi hostname nội bộ của CI hoặc cổng ngẫu nhiên vào tài liệu được xuất bản.

## 4. Xóa header không cần xuất hiện trong tài liệu

Một request có thể có header phục vụ nội bộ, tracing hoặc kiểm thử. Nếu header không phải một phần hợp đồng API, có thể xóa khỏi bản ghi request:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

mockMvc.perform(get("/api/orders/{orderId}", 42L)
        .header("X-Test-Run", "local-123")
        .header("X-Internal-Trace", "trace-456"))
    .andExpect(status().isOk())
    .andDo(document("order-get",
        preprocessRequest(
            removeHeaders("X-Test-Run", "X-Internal-Trace")
        )
    ));
~~~

Với response, áp dụng **removeHeaders(...)** trong **preprocessResponse(...)**:

~~~java
preprocessResponse(
    removeHeaders("X-Internal-Server", "X-Debug-Id")
)
~~~

Chỉ xóa header khỏi snippet khi header đó không cần thiết cho người dùng API. Không tự ý xóa **Authorization**, **Content-Type**, **Accept**, **ETag**, **Location**, **Cache-Control** hoặc các header có ý nghĩa đối với cách gọi API nếu tài liệu cần hướng dẫn client sử dụng chúng.

Nếu header chứa bí mật như bearer token, cookie hoặc API key, cần che hoặc loại khỏi bản ghi tài liệu. Đồng thời, không đưa bí mật thật vào fixture/test nếu có thể dùng giá trị giả lập.

## 5. Che hoặc thay thế dữ liệu nhạy cảm

Một số request/response có dữ liệu cần ẩn trước khi sinh snippet:

- **Authorization** có token truy cập.
- Cookie chứa session identifier.
- JSON body có email, số điện thoại hoặc dữ liệu cá nhân dùng trong fixture.
- Response có thông tin nội bộ không nên công bố.

Có hai cách thường dùng: xóa toàn bộ header không cần thiết hoặc **thay thế một phần giá trị** bằng dữ liệu giả.

### 5.1. Loại bỏ header nhạy cảm

~~~java
preprocessRequest(
    removeHeaders("Authorization", "Cookie")
)
~~~

Ví dụ:

~~~http
GET /api/orders/42
Accept: application/json
~~~

Snippet không còn thể hiện token. Tuy nhiên, nếu người đọc cần biết endpoint có yêu cầu xác thực, hãy tài liệu hóa **header Authorization ở dạng placeholder an toàn** bằng một cách thay thế có chủ đích, thay vì xóa mọi dấu hiệu về cơ chế bảo mật.

### 5.2. Thay thế pattern trong body

Spring REST Docs cung cấp **replacePattern(...)** để thay thế một pattern trong body của operation:

~~~java
import java.util.regex.Pattern;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;

preprocessResponse(
    replacePattern(
        Pattern.compile("lan@example\\.com"),
        "user@example.com"
    )
)
~~~

Trong Java string, dấu gạch chéo ngược của biểu thức chính quy cần escape. Nếu pattern có thể khớp nhiều dữ liệu, hãy viết biểu thức đủ cụ thể và kiểm tra body sau thay thế để tránh biến đổi nhầm nội dung nghiệp vụ.

Có thể áp dụng cho request body tương tự:

~~~java
preprocessRequest(
    replacePattern(
        Pattern.compile("0901234567"),
        "0900000000"
    )
)
~~~

**replacePattern(...)** thao tác trên nội dung operation được tiền xử lý; nó không sửa object đang được controller xử lý hoặc dữ liệu lưu trong database. Hãy xác minh snippet output để chắc chắn không còn giá trị cần che.

### 5.3. Che liên kết khi response có URL

Nếu response chứa các link HAL hoặc link dạng JSON có URL môi trường test, có thể xem xét preprocessor **maskLinks()** để thay thế URI của các link bằng placeholder trong tài liệu:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.maskLinks;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

preprocessResponse(maskLinks())
~~~

Chỉ dùng khi cấu trúc response thực sự là nội dung link mà preprocessor hỗ trợ. Nếu API muốn công bố URL chính xác hoặc cấu trúc link cụ thể, hãy cân nhắc **modifyUris()** hay replacement có chủ đích thay vì che toàn bộ.

## 6. Kết hợp nhiều preprocessor trong một operation

Các preprocessor có thể ghép trong cùng **preprocessRequest(...)** hoặc **preprocessResponse(...)**. Ví dụ:

~~~java
mockMvc.perform(get("/api/orders/{orderId}", 42L)
        .header("X-Test-Run", "ci-987")
        .header("Authorization", "Bearer test-token")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("order-get",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("api.example.com")
                .removePort(),
            removeHeaders("X-Test-Run", "Authorization")
        ),
        preprocessResponse(
            prettyPrint(),
            replacePattern(
                Pattern.compile("lan@example\\.com"),
                "user@example.com"
            )
        )
    ));
~~~

Thứ tự preprocessor trong cùng một chuỗi có ý nghĩa: mỗi bước nhận kết quả đã qua bước trước. Nên thực hiện chuẩn hóa và loại bỏ dữ liệu cần thiết với thứ tự dễ hiểu, tránh một bước replacement phụ thuộc vào giá trị đã bị bước trước thay đổi.

Không che thông tin theo cách khiến tài liệu mô tả sai hợp đồng. Ví dụ thay **Authorization** bằng cách xóa header có thể làm người dùng tưởng endpoint không cần xác thực. Nếu muốn hướng dẫn cách truyền token, tốt hơn là dùng giá trị giả nhưng có hình dạng rõ ràng, hoặc mô tả header bằng snippet riêng.

## 7. Áp dụng preprocessing dùng chung

Nếu hầu hết operation cần pretty print hoặc chuẩn hóa host, có thể cấu hình preprocessor dùng chung trong MockMvc REST Docs.

Ví dụ dùng **MockMvcRestDocumentationConfigurer**:

~~~java
mockMvc = MockMvcBuilders
    .webAppContextSetup(context)
    .apply(documentationConfiguration(restDocumentation)
        .operationPreprocessors()
            .withRequestDefaults(
                modifyUris()
                    .scheme("https")
                    .host("api.example.com")
                    .removePort(),
                prettyPrint()
            )
            .withResponseDefaults(prettyPrint()))
    .build();
~~~

Đoạn cấu hình minh họa cách đặt default preprocessor ở mức **documentationConfiguration**. Cần có **WebApplicationContext context** và **RestDocumentationContextProvider restDocumentation** được thiết lập trong test fixture theo hướng dẫn MockMvc REST Docs của phiên bản đang dùng.

Khi cấu hình mặc định đã bao gồm pretty print, không cần lặp lại **preprocessRequest(prettyPrint())** và **preprocessResponse(prettyPrint())** trong từng operation. Với một operation cần xử lý riêng, có thể bổ sung preprocessor trong **document(...)**.

### 7.1. Khi nào dùng default và khi nào dùng riêng?

| Tình huống | Cách đặt |
| --- | --- |
| Tất cả request dùng host công khai | Request defaults |
| Tất cả response JSON cần format | Response defaults |
| Chỉ một endpoint cần che email | Preprocessor riêng trong document của endpoint |
| Một endpoint có header debug riêng | Remove header ở operation đó |
| API có nhiều kiểu response hoặc nhiều media type | Chọn preprocessor phù hợp theo từng operation |

Không nên đặt quy tắc che dữ liệu đặc thù của một endpoint thành default toàn hệ thống nếu có thể làm biến dạng tài liệu của endpoint khác.

## 8. Preprocessing không thay thế descriptor

Preprocessor chỉnh sửa biểu diễn request/response của operation; descriptor mô tả ý nghĩa dữ liệu. Ví dụ:

~~~java
document("order-create",
    preprocessRequest(prettyPrint()),
    preprocessResponse(prettyPrint()),
    requestFields(
        fieldWithPath("description")
            .description("Mô tả đơn hàng")
    ),
    responseFields(
        fieldWithPath("id")
            .description("Mã đơn hàng được tạo"),
        fieldWithPath("status")
            .description("Trạng thái đơn hàng")
    )
)
~~~

Ở đây:

- **prettyPrint()** giúp body dễ đọc.
- **requestFields(...)** mô tả payload request.
- **responseFields(...)** mô tả payload response.
- **preprocessRequest(...)** và **preprocessResponse(...)** không thay thế việc xác nhận các field đã được tài liệu hóa.

Nếu body bị replacement làm thay đổi giá trị nhưng giữ nguyên cấu trúc, descriptor vẫn cần mô tả đúng field. Nếu preprocessor làm thay đổi cấu trúc JSON, hãy cẩn thận vì các descriptor payload cũng phải áp dụng trên operation đã được tiền xử lý và có thể không còn khớp.

## 9. Kiểm thử kết quả tiền xử lý

Không nên chỉ nhìn test thành công mà cho rằng snippet đã sạch. Hãy mở các snippet được sinh và kiểm tra:

1. Host, scheme và port trong **http-request.adoc** đúng với URL công khai.
2. Header debug/token/cookie không bị lộ ngoài ý muốn.
3. Request/response body được format đúng và không còn dữ liệu thật cần che.
4. Những header cần thiết cho client vẫn được giữ.
5. Các snippet **request-fields.adoc** và **response-fields.adoc** mô tả đúng payload thực tế.

Một test response được tiền xử lý:

~~~java
mockMvc.perform(get("/api/customers/{customerId}", 12L)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("customer-get",
        preprocessResponse(
            prettyPrint(),
            replacePattern(
                Pattern.compile("lan@example\\.com"),
                "user@example.com"
            )
        )
    ));
~~~

Response ứng dụng có thể chứa email test; snippet sau khi preprocessing phải hiển thị giá trị placeholder. Nếu cần xác nhận nội dung thay thế một cách tự động, có thể kiểm tra file snippet trong một bước QA tài liệu riêng hoặc dùng test cho preprocessor tùy chỉnh. Không dùng assertion trên response gốc để kết luận rằng bản ghi snippet đã được thay đổi.

## 10. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| JSON trong snippet vẫn là một dòng | Chưa áp dụng **prettyPrint()** hoặc body không được nhận diện | Thêm đúng preprocessRequest/preprocessResponse và kiểm tra Content-Type |
| URL hiển thị localhost/cổng ngẫu nhiên | Chưa chuẩn hóa URI request | Dùng **modifyUris()** trong request preprocessor |
| Token vẫn xuất hiện trong request snippet | Chỉ xóa token ở response hoặc không áp dụng preprocessor | Xóa/thay thế header trong **preprocessRequest(...)** |
| Email thật còn xuất hiện trong response snippet | Replacement không khớp pattern hoặc chỉ xử lý request | Kiểm tra pattern và dùng **preprocessResponse(...)** |
| Header cần thiết biến mất | Xóa header quá rộng | Chỉ remove header nội bộ; giữ header hợp đồng |
| Tài liệu mô tả khác với API thực | Preprocessor làm thay đổi dữ liệu nghiệp vụ | Chỉ chuẩn hóa phần trình bày/ẩn dữ liệu; mô tả rõ placeholder |
| URI bị encode hoặc chuẩn hóa hai lần | Nhiều lớp cùng biến đổi URI | Chọn một điểm chuẩn hóa và kiểm tra output |
| Default processor và processor riêng xung đột | Cùng một biến đổi được áp dụng nhiều lần | Quy định rõ defaults và override cho từng operation |

## 11. Bài thực hành

API quản lý hồ sơ khách hàng:

~~~text
GET /api/customers/{customerId}
~~~

Response test chứa:

~~~json
{
  "id": 12,
  "name": "Lan",
  "email": "lan@example.com"
}
~~~

Yêu cầu:

1. Viết test MockMvc với request template **/api/customers/{customerId}** và xác nhận HTTP 200.
2. Dùng **preprocessRequest(...)** để chuẩn hóa URI thành **https://api.example.com** và loại header **X-Test-Run**.
3. Dùng **preprocessResponse(...)** để format JSON và thay **lan@example.com** thành **user@example.com** trong snippet.
4. Thêm descriptor **pathParameters(...)** cho **customerId**.
5. Thêm **responseFields(...)** cho **id**, **name**, **email**.
6. Kiểm tra các snippet **http-request.adoc**, **http-response.adoc** và **response-fields.adoc** để xác nhận dữ liệu đã được chuẩn hóa/che đúng.
7. Đưa test vào tác vụ Gradle trước Asciidoctor và bảo đảm CI không xuất bản snippet chứa dữ liệu thật.

Mẫu thiết lập:

~~~java
document("customer-get",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.com")
            .removePort(),
        removeHeaders("X-Test-Run")
    ),
    preprocessResponse(
        prettyPrint(),
        replacePattern(
            Pattern.compile("lan@example\\.com"),
            "user@example.com"
        )
    ),
    pathParameters(
        parameterWithName("customerId")
            .description("Mã định danh khách hàng")
    ),
    responseFields(
        fieldWithPath("id").description("Mã khách hàng"),
        fieldWithPath("name").description("Tên khách hàng"),
        fieldWithPath("email").description("Email đã được ẩn trong snippet")
    )
)
~~~

**Tiêu chí hoàn thành:** request/response snippet được format đúng; host được chuẩn hóa; header test không xuất hiện; email thật không còn trong tài liệu; path parameter và response fields vẫn đầy đủ.

## Ghi nhớ

**preprocessRequest(...)** và **preprocessResponse(...)** giúp chuẩn hóa bản ghi HTTP mà Spring REST Docs dùng để sinh snippet. Dùng **prettyPrint()** cho body, **modifyUris()** cho URL, **removeHeaders(...)** để loại header nội bộ và **replacePattern(...)** để thay dữ liệu cần che. Có thể đặt bộ xử lý ở từng **document(...)** hoặc cấu hình mặc định cho MockMvc, nhưng phải kiểm tra snippet cuối để chắc chắn thông tin công khai vẫn chính xác và không chứa bí mật. Preprocessing kết hợp với descriptor và test HTTP giúp tài liệu API dễ đọc, ổn định và phù hợp quy trình build/CI.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [OperationPreprocessors API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/operation/preprocess/Preprocessors.html) và [MockMvcRestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/mockmvc/MockMvcRestDocumentation.html).
