# Tái sử dụng preprocessor chung

## Mục tiêu bài học

Trong dự án có nhiều endpoint, các bài test REST Docs thường lặp lại thao tác chuẩn bị request/response trước khi ghi snippet: format JSON, loại bỏ header nhạy cảm, thay token giả lập hoặc chuẩn hóa dữ liệu động. Nếu mỗi test tự khai báo các thao tác này, cấu hình dễ lệch nhau và khó bảo trì.

**Preprocessor** của Spring REST Docs biến đổi bản request hoặc response dùng để tạo tài liệu. Có thể cấu hình các bước dùng chung ở cấp MockMvc/WebTestClient/REST Assured hoặc đóng gói thành helper để nhiều test sử dụng cùng chính sách.

Bài học thuộc chương **Tái sử dụng** của module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng bằng test HTTP với **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn Asciidoctor/Markdown và tích hợp vào build, CI.

Sau bài học, bạn có thể:

- Giải thích vai trò của operation preprocessor và thời điểm áp dụng.
- Tái sử dụng cấu hình request/response preprocessing trên nhiều operation.
- Thiết lập default preprocessors ở cấp documentation configurer.
- Tạo helper dùng chung để chuẩn hóa request và response.
- Loại bỏ hoặc thay thế dữ liệu nhạy cảm trước khi ghi snippet.
- Phân biệt dữ liệu được biến đổi trong tài liệu với HTTP exchange thực tế.
- Kiểm tra chính sách preprocessing bằng test và áp dụng nhất quán trong CI.

## 1. Preprocessor giải quyết vấn đề gì?

REST Docs ghi lại operation được thực hiện trong test. Request và response có thể chứa dữ liệu không phù hợp để đưa thẳng vào tài liệu:

- JSON body được serialize trên một dòng, khó đọc.
- Header Authorization, cookie phiên hoặc correlation ID không nên công bố.
- Token, email, số điện thoại hoặc ID sinh ngẫu nhiên làm snippet không ổn định.
- Các test cùng một API có cách trình bày khác nhau.

Thay vì chỉnh sửa snippet sau khi sinh, hãy tiền xử lý operation data trước khi REST Docs tạo snippet.

~~~mermaid
flowchart LR
    A["HTTP test executes"] --> B["Request / response"]
    B --> C["Shared preprocessors"]
    C --> D["REST Docs snippets"]
    D --> E["Asciidoctor / Markdown"]
~~~

Preprocessor tác động lên bản dữ liệu REST Docs sử dụng để tạo tài liệu. Nó không phải middleware thay đổi request mà ứng dụng nhận hoặc response mà client thực tế nhận. Ví dụ, loại bỏ Authorization trong snippet không có nghĩa header đó bị xóa khỏi HTTP request gửi tới controller.

## 2. Tách preprocessing cho request và response

Spring REST Docs cung cấp các hàm tạo preprocessor trong package org.springframework.restdocs.operation.preprocess.Preprocessors. Hai nhóm thường dùng:

- **Request preprocessing:** chuẩn hóa request trước khi tạo http-request, request body và snippet liên quan.
- **Response preprocessing:** chuẩn hóa response trước khi tạo http-response, response body và snippet liên quan.

Ví dụ format JSON dễ đọc:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

mockMvc.perform(get("/api/orders/42")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("orders-get",
        preprocessRequest(prettyPrint()),
        preprocessResponse(prettyPrint())
    ));
~~~

prettyPrint() làm JSON trong snippet dễ đọc hơn khi body là định dạng được hỗ trợ. Nó chỉ thay đổi cách biểu diễn nội dung ghi vào tài liệu; không thay đổi dữ liệu ứng dụng xử lý.

Nếu mọi operation đều cần format, khai báo defaults một lần thay vì lặp hai dòng trên trong từng test.

## 3. Khai báo default preprocessors dùng chung

Với MockMvc, MockMvcRestDocumentationConfigurer có thể đặt request/response preprocessors mặc định:

~~~java
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.mockmvc.MockMvcRestDocumentationConfigurer;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;

MockMvcRestDocumentationConfigurer configurer =
    documentationConfiguration(restDocumentation)
        .operationPreprocessors()
        .withRequestDefaults(prettyPrint())
        .withResponseDefaults(prettyPrint());
~~~

Đây là cấu hình minh họa cho project dùng Spring Test/MockMvc. Đưa configurer vào MockMvcBuilders hoặc test setup theo cấu trúc test hiện có. Có thể đặt cấu hình trong lớp base test hoặc factory dùng chung để mọi test sử dụng cùng configurer.

Khi đã khai báo default preprocessors, operation chỉ cần mô tả phần riêng:

~~~java
mockMvc.perform(get("/api/orders/42"))
    .andExpect(status().isOk())
    .andDo(document("orders-get",
        responseFields(
            fieldWithPath("id").description("Mã đơn hàng"),
            fieldWithPath("status").description("Trạng thái đơn hàng")
        )
    ));
~~~

Không cần gọi preprocessRequest(prettyPrint()) và preprocessResponse(prettyPrint()) ở từng operation nếu defaults đã áp dụng. Tránh format hai lần hoặc cấu hình mâu thuẫn ở cấp test.

## 4. Đóng gói helper để tái sử dụng

Khi không muốn đặt mọi chính sách vào configurer, có thể tạo helper trả về cấu hình preprocessor cho các operation cần dùng.

Ví dụ gom các preprocessor theo mục đích:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;
import org.springframework.restdocs.operation.preprocess.OperationPreprocessor;

final class ApiDocumentationPreprocessors {

    private ApiDocumentationPreprocessors() {
    }

    static OperationPreprocessor[] safeRequestDefaults() {
        return new OperationPreprocessor[] {
            prettyPrint(),
            removeHeaders("Authorization")
        };
    }

    static OperationPreprocessor[] readableResponseDefaults() {
        return new OperationPreprocessor[] {
            prettyPrint()
        };
    }
}
~~~

Helper tập trung chính sách và tên gọi có ý nghĩa. Kiểu preprocessor và overload được chấp nhận có thể khác theo phiên bản REST Docs. Kiểm tra Javadoc dependency đang dùng; nếu API yêu cầu OperationRequestPreprocessor hoặc OperationResponsePreprocessor, tạo helper trả đúng kiểu chuyên biệt thay vì ép kiểu.

Với API nhận từng preprocessor, truyền lần lượt từng phần tử vào preprocessRequest(...) hoặc preprocessResponse(...). Với configurer hỗ trợ varargs, có thể truyền danh sách tương ứng vào withRequestDefaults(...) và withResponseDefaults(...). Không giả định mọi overload có cùng chữ ký.

## 5. Chọn phạm vi áp dụng: global, nhóm API hay từng operation

Không phải mọi preprocessor đều nên áp dụng cho toàn bộ tài liệu:

| Phạm vi | Khi phù hợp | Ví dụ |
| --- | --- | --- |
| Toàn bộ MockMvc configurer | Quy tắc luôn đúng với mọi endpoint | Pretty-print JSON |
| Nhóm API | Một nhóm endpoint có chính sách chung | Ẩn header nội bộ của API quản trị |
| Một operation | Chỉ endpoint đó có dữ liệu cần xử lý | Thay token giả lập trong callback response |
| Một loại snippet | Chỉ một fragment cần trình bày khác | Tùy chỉnh payload snippet |

Nên đặt quy tắc trình bày chung ở cấp configurer. Quy tắc bảo vệ dữ liệu nhạy cảm cần được cân nhắc kỹ hơn: nếu header nhạy cảm có thể xuất hiện ở bất kỳ operation nào, chính sách che/loại bỏ nên được áp dụng tập trung để không bỏ sót endpoint.

Không thêm preprocessing toàn cục làm mất thông tin hợp đồng. Ví dụ, xóa toàn bộ Content-Type sẽ khiến snippet không còn cho biết định dạng request/response.

## 6. Loại bỏ header nhạy cảm

Header như Authorization không nên xuất hiện trong tài liệu công khai. Có thể dùng preprocessor loại bỏ header khỏi bản request được ghi:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

mockMvc.perform(get("/api/profile")
        .header("Authorization", "Bearer test-token"))
    .andExpect(status().isOk())
    .andDo(document("profile-get",
        preprocessRequest(removeHeaders("Authorization"))
    ));
~~~

Header vẫn được gửi tới ứng dụng để xác thực trong test; preprocessor chỉ loại nó khỏi operation REST Docs ghi lại.

Nếu cần giữ tên header để người đọc biết API yêu cầu xác thực, nhưng không muốn lộ giá trị, hãy dùng preprocessor thay thế giá trị bằng placeholder theo API hỗ trợ của phiên bản, hoặc dùng operation preprocessor tùy chỉnh. Snippet khi đó có thể thể hiện:

~~~http
GET /api/profile HTTP/1.1
Authorization: Bearer [redacted]
Accept: application/json
~~~

Giữ lại header name và cấu trúc xác thực thường hữu ích hơn xóa toàn bộ header, nhưng cần bảo đảm placeholder không bị hiểu nhầm là token thật.

## 7. Chuẩn hóa dữ liệu động trong request/response

Một số response chứa timestamp, UUID hoặc host động. Nếu các giá trị đó không phải trọng tâm của API contract, có thể thay thế chúng trong tài liệu để snippet ổn định:

~~~java
import java.util.regex.Pattern;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content(requestJson))
    .andExpect(status().isCreated())
    .andDo(document("orders-create",
        preprocessResponse(
            replacePattern(
                Pattern.compile("\"createdAt\":\"[^\"]+\""),
                "\"createdAt\":\"2026-01-01T00:00:00Z\""
            )
        )
    ));
~~~

Ví dụ thay chuỗi JSON khớp regular expression trong bản response được ghi tài liệu. Chỉ dùng khi pattern đủ hẹp và không làm biến đổi cấu trúc ngoài ý muốn. Nếu cần thay JSON field có cấu trúc, hãy dùng custom preprocessor parse JSON rồi cập nhật đúng field, thay vì regex tổng quát.

Không thay giá trị có ý nghĩa contract. Ví dụ orderId, trạng thái, số tiền hoặc field mà client cần hiểu phải giữ nguyên hoặc dùng fixture xác định ngay từ test.

## 8. Tái sử dụng với nhiều test và nhiều client

REST Docs hỗ trợ các tích hợp test khác nhau. Ý tưởng tái sử dụng giống nhau: chuẩn hóa operation request/response trước khi tạo snippet. Cách gắn configurer/filter phụ thuộc integration:

| Tích hợp | Điểm cấu hình | Cách tái sử dụng |
| --- | --- | --- |
| MockMvc | MockMvcRestDocumentationConfigurer | Dùng chung configurer hoặc base test |
| WebTestClient | WebTestClientRestDocumentationConfigurer | Dùng chung WebTestClient builder/configuration |
| REST Assured | RestAssuredRestDocumentation filter/configuration | Dùng chung RequestSpecification và filter |

Với REST Assured, có thể tạo specification chung chứa filter REST Docs và dùng cho nhiều test. Với WebTestClient, cấu hình documentation trên builder dùng chung. Không sao chép nguyên cấu hình MockMvc sang hai integration kia vì mỗi integration có API cấu hình riêng.

Giữ chính sách preprocessing tương đương giữa các client test: cùng header nhạy cảm phải được che, cùng JSON phải được format và cùng dữ liệu động phải được chuẩn hóa. Nếu ba test harness tạo tài liệu khác nhau, cần xác định đó là khác biệt có chủ đích hay cấu hình bị lệch.

## 9. Thứ tự preprocessor và tính idempotent

Khi kết hợp nhiều bước, thứ tự có thể ảnh hưởng kết quả. Ví dụ:

1. Thay giá trị token.
2. Xóa header không cần xuất hiện.
3. Format JSON.

Nếu xóa header trước, bước thay thế giá trị header sau đó không còn tác dụng. Nếu format JSON trước rồi regex dựa trên chuỗi một dòng, pattern có thể không còn khớp.

Hãy thiết kế helper sao cho:

- Thứ tự được khai báo rõ và có comment khi cần.
- Mỗi bước chỉ thay đổi phần dữ liệu được dự định.
- Chạy lặp không tiếp tục làm biến dạng output (idempotent nếu phù hợp).
- Không xóa thông tin cần để hiểu contract.
- Có test xác nhận snippet đã được che/format đúng.

Ví dụ thứ tự:

~~~java
preprocessResponse(
    replacePattern(Pattern.compile("internal-node-[0-9]+"), "service-node"),
    prettyPrint()
)
~~~

Đây là minh họa thứ tự biến đổi. Nếu JSON có thể thay đổi whitespace hoặc escaping, pattern cần được kiểm tra trên đúng representation trước/sau từng bước.

## 10. Test chính sách preprocessing

Không chỉ kiểm tra endpoint trả đúng status. Cần kiểm tra snippet được tạo có đúng chính sách:

- JSON được format khi cần.
- Header Authorization không bị lộ hoặc được thay bằng placeholder.
- Cookie session không bị ghi ra dưới dạng giá trị thật.
- Timestamp/UUID động được chuẩn hóa nếu contract cho phép.
- Header quan trọng như Content-Type và Location vẫn còn.

Ví dụ kiểm tra file snippet sau khi test:

~~~java
String requestSnippet = Files.readString(
    Path.of("build/generated-snippets/profile-get/http-request.adoc"),
    StandardCharsets.UTF_8
);

assertThat(requestSnippet).doesNotContain("test-token");
assertThat(requestSnippet).contains("Accept");
~~~

Đường dẫn và phần mở rộng phụ thuộc output directory/template format. Có thể đặt kiểm tra snippet trong test hoặc một bước validation riêng sau khi tất cả test chạy xong. Đảm bảo test không phụ thuộc thứ tự chạy hoặc file snippet cũ còn sót lại.

### 10.1. Kiểm tra preprocessor không thay đổi HTTP behavior

Vì preprocessor hoạt động trên operation data dùng cho tài liệu, test cần chứng minh ứng dụng vẫn nhận request đúng:

~~~java
mockMvc.perform(get("/api/profile")
        .header("Authorization", "Bearer test-token"))
    .andExpect(status().isOk());
~~~

Sau đó kiểm tra snippet không chứa test-token. Hai assertion chứng minh hai mục tiêu riêng:

- Request test thực tế vẫn mang thông tin xác thực cần thiết để endpoint xử lý.
- Tài liệu đã loại bỏ hoặc che giá trị nhạy cảm.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Header Authorization vẫn xuất hiện trong snippet | Preprocessor chưa được gắn vào operation/configurer | Kiểm tra đúng request preprocessing và scope |
| Endpoint không còn nhận Authorization | Nhầm preprocessor tài liệu với filter HTTP thật hoặc đặt logic sai tầng | Xác nhận header vẫn được gửi trong request test |
| JSON snippet vẫn trên một dòng | prettyPrint() chưa áp dụng hoặc content type không được nhận diện | Kiểm tra request/response content type và configurer |
| Một số test có format, một số không | Cấu hình bị lặp hoặc test dùng builder khác | Đưa default vào factory/base configuration |
| Token bị thay ở body nhưng vẫn lộ trong header | Chỉ preprocessing body, chưa xử lý header | Thêm chính sách header riêng |
| Timestamp bị thay quá rộng | Regex khớp cả field khác | Dùng pattern hẹp hoặc parse JSON có cấu trúc |
| Header Content-Type biến mất | Dùng removeHeaders quá rộng | Chỉ loại header nhạy cảm cụ thể |
| Snippet thiếu thông tin hợp đồng | Preprocessor xóa dữ liệu quan trọng | Rà soát danh sách header/field giữ lại |
| API MockMvc có cấu hình nhưng REST Assured không có | Mỗi integration có configurer/filter riêng | Tạo cấu hình tương đương cho từng test harness |
| Helper không biên dịch | Kiểu preprocessor hoặc overload khác giữa các REST Docs version | Kiểm tra Javadoc và dùng đúng kiểu request/response |
| CI pass nhờ snippet cũ | Output directory còn artifact từ lần chạy trước | Làm mới output có kiểm soát và validate content |

## 12. Bài thực hành

Tạo endpoint:

~~~text
GET /api/profile
~~~

Request test có header Authorization với giá trị Bearer test-token và header Accept: application/json.

Response JSON:

~~~json
{
  "id": 42,
  "name": "Lan",
  "generatedAt": "2026-11-17T08:30:15Z"
}
~~~

Yêu cầu:

1. Tạo helper/preprocessor dùng chung để pretty-print request và response JSON.
2. Loại bỏ hoặc thay giá trị Authorization trong request snippet.
3. Chuẩn hóa generatedAt thành timestamp fixture nếu thời gian không phải nội dung contract.
4. Dùng cùng cấu hình cho ít nhất hai operation test.
5. Assert endpoint vẫn nhận request có Authorization và trả response thành công.
6. Đọc snippet được sinh để xác nhận test-token không xuất hiện, nhưng header Accept và Content-Type cần thiết vẫn được giữ.
7. Nối test sinh snippet và bước kiểm tra output vào CI.

**Tiêu chí hoàn thành:** helper được tái sử dụng; request/response snippet có format thống nhất; dữ liệu nhạy cảm được che; HTTP behavior vẫn đúng; CI thất bại nếu snippet để lộ token hoặc thiếu header quan trọng.

## Ghi nhớ

Preprocessor biến đổi bản request/response mà Spring REST Docs dùng để tạo snippet, không thay đổi HTTP exchange của ứng dụng. Đặt quy tắc chung như pretty-print ở cấp configurer; đóng gói quy tắc theo nhóm hoặc operation bằng helper khi cần. Dùng preprocessing để loại bỏ/thay dữ liệu nhạy cảm và chuẩn hóa giá trị động, nhưng giữ lại thông tin cần thiết để hiểu contract. Kiểm tra cả request thực tế lẫn snippet sau preprocessing, và áp dụng chính sách tương đương cho MockMvc, WebTestClient và REST Assured. Tập trung cấu hình dùng chung giúp tài liệu nhất quán và dễ duy trì trong CI.

**Tài liệu tham khảo:** [Spring REST Docs Reference – Preprocessing](https://docs.spring.io/spring-restdocs/reference/documentation-operations/preprocessing.html), [Spring REST Docs Preprocessors API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/operation/preprocess/Preprocessors.html), [Spring REST Docs MockMvc API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/mockmvc/MockMvcRestDocumentationConfigurer.html).
