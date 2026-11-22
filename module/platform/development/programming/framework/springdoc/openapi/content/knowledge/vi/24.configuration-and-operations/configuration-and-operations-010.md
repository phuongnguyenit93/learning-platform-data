# Tránh phụ thuộc dữ liệu biến động khi xây hợp đồng

OpenAPI là hợp đồng mô tả API mà client có thể dựa vào để tích hợp, sinh mã và kiểm thử. Hợp đồng cần ổn định trong suốt một phiên bản phát hành: cùng một phiên bản ứng dụng và cùng cấu hình triển khai phải tạo ra cùng cấu trúc operation, schema, parameter, response và ví dụ. Nếu quá trình sinh tài liệu phụ thuộc vào dữ liệu đang có trong database, thời điểm hiện tại, người dùng đang đăng nhập hoặc kết quả gọi một dịch vụ bên ngoài, hợp đồng có thể thay đổi ngoài ý muốn.

springdoc-openapi sinh tài liệu từ controller, DTO, annotation và các customizer. Vì vậy, cần giữ phần mô tả hợp đồng tách khỏi dữ liệu nghiệp vụ tại runtime. Hãy mô tả kiểu dữ liệu, quy tắc và các trường hợp đại diện bằng metadata có chủ đích; dùng ví dụ tĩnh đã được làm sạch; để endpoint nghiệp vụ trả dữ liệu thật khi client gọi API.

## 1. Hợp đồng API và dữ liệu runtime có mục đích khác nhau

Hợp đồng mô tả hình dạng và quy tắc của request/response. Dữ liệu runtime là giá trị cụ thể của một lần gọi API.

| Thành phần | Thuộc về hợp đồng | Thuộc về runtime |
| --- | --- | --- |
| Kiểu orderId | string, pattern hoặc format nếu có | ORD-10482 của một đơn hàng cụ thể |
| Trạng thái đơn hàng | Tập giá trị ổn định nếu nghiệp vụ thực sự giới hạn | Trạng thái hiện tại của từng đơn |
| createdAt | string với format date-time | Thời điểm tạo đơn thực tế |
| Tổng số kết quả | Kiểu integer, mô tả ý nghĩa | Số bản ghi tìm thấy ở thời điểm gọi |
| Trang hiện tại | Parameter page kiểu integer | Giá trị page=3 của request cụ thể |
| URL API | Server URL theo môi trường triển khai | Host nội bộ của request đi qua một proxy cụ thể |
| Ví dụ response | Dữ liệu giả đại diện cho hợp đồng | Bản ghi khách hàng hoặc đơn hàng trong database |

Ví dụ, OpenAPI nên mô tả createdAt là ngày giờ ISO 8601. Nó không nên lấy Instant.now() khi tạo tài liệu rồi biến thời điểm khởi động ứng dụng thành giá trị mặc định của field.

## 2. Những nguồn dữ liệu dễ làm hợp đồng biến động

Các nguồn sau thường không nên được truy vấn trong lúc xây OpenAPI:

- Database: danh sách category, trạng thái, sản phẩm, tenant hoặc bản ghi mới nhất.
- Dịch vụ ngoài: giá hiện tại, tỷ giá, trạng thái nhà cung cấp hoặc cấu hình từ remote API.
- Đồng hồ hệ thống: thời gian hiện tại, ngày triển khai hoặc thời gian khởi động.
- Bộ sinh ngẫu nhiên: UUID, số thứ tự, mã giao dịch hoặc dữ liệu faker tạo mới mỗi lần.
- Request hiện tại: user, tenant, header, host, locale hoặc query parameter của người đang xem tài liệu.
- Feature flag thay đổi theo user hoặc thời điểm.
- Environment variable không được quản lý theo release hoặc bị thay đổi giữa các replica.

Nếu một customizer gọi repository, WebClient hoặc Instant.now() để điền schema/example, tài liệu có thể khác giữa lần khởi động, giữa các instance hoặc giữa các request. Điều đó làm contract diff nhiễu và có thể đưa dữ liệu thật vào tài liệu công khai.

## 3. Mô tả DTO ổn định thay vì lấy một entity làm hợp đồng

Không nên để schema công khai phụ thuộc trực tiếp vào cấu trúc bảng hoặc entity persistence. Entity thường có quan hệ lazy, field nội bộ, audit field và thuộc tính thay đổi theo cách lưu trữ.

Tạo DTO dành riêng cho API:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;

@Schema(name = "OrderResponse", description = "Thông tin đơn hàng trả về cho client.")
public record OrderResponse(
    @Schema(
        description = "Mã đơn hàng do hệ thống cấp.",
        example = "ORD-10482",
        pattern = "^ORD-[0-9]{5}$"
    )
    String orderId,

    @Schema(
        description = "Trạng thái hiện tại của đơn hàng.",
        example = "PROCESSING",
        allowableValues = {"PENDING", "PROCESSING", "SHIPPED", "CANCELLED"}
    )
    String status,

    @Schema(
        description = "Thời điểm đơn hàng được tạo, theo ISO 8601 UTC.",
        type = "string",
        format = "date-time",
        example = "2030-04-15T09:30:00Z"
    )
    Instant createdAt
) {
}
~~~

DTO làm rõ hợp đồng bên ngoài. Database có thể thêm cột, đổi quan hệ hoặc đổi cách lưu trữ mà không buộc schema OpenAPI thay đổi nếu API contract vẫn giữ nguyên.

Chỉ đưa field mà client cần vào response DTO. Không để springdoc vô tình công bố password hash, internal note, database key, thông tin audit nội bộ hoặc dữ liệu nhạy cảm chỉ vì entity có các field đó.

## 4. Chỉ dùng enum khi tập giá trị thực sự ổn định

Enum phù hợp khi tập giá trị là một phần của hợp đồng và được quản lý cùng vòng đời API, ví dụ trạng thái đơn hàng có tập giá trị cố định.

Không nên truy vấn database để tạo allowableValues từ những dòng dữ liệu hiện có. Danh mục có thể thay đổi, phân trang, phụ thuộc tenant hoặc được cập nhật bởi quản trị viên. Một tài liệu được sinh sáng nay có thể liệt kê một tập giá trị khác vào chiều nay.

| Dữ liệu | Cách mô tả phù hợp |
| --- | --- |
| Trạng thái đơn hàng với tập giá trị được kiểm soát trong code | Enum hoặc allowableValues |
| Mã quốc gia theo danh mục chuẩn được version hóa | Enum nếu API thực sự giới hạn theo phiên bản danh mục |
| Danh mục sản phẩm do quản trị viên thêm/xóa | String hoặc schema tham chiếu một mã; mô tả endpoint tra cứu danh mục |
| Tenant ID hoặc user ID | String với format/pattern nếu có quy tắc ổn định |
| Tên nhà cung cấp được cấu hình ngoài | String; không biến danh sách runtime thành enum |

Nếu client cần biết các giá trị động được phép, cung cấp endpoint discovery như /api/categories hoặc /api/configuration/options. Hợp đồng của endpoint discovery vẫn ổn định, còn danh sách trả về có thể thay đổi theo dữ liệu nghiệp vụ.

## 5. Phân biệt example và default

Hai khái niệm này không thể dùng thay thế cho nhau:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| example / examples | Giá trị minh họa để người đọc hiểu cách dùng |
| default | Giá trị mặc định theo ngữ nghĩa schema khi không cung cấp giá trị, nếu định nghĩa API có quy định |

Không đặt giá trị hiện tại của database hoặc thời điểm hiện tại vào default chỉ để Swagger UI hiển thị một giá trị đẹp. default có thể được client generator hoặc công cụ khác hiểu như một mặc định có ý nghĩa.

Ví dụ đúng: parameter page có default là 0 nếu API thực sự dùng trang đầu tiên khi client bỏ qua parameter:

~~~java
import io.swagger.v3.oas.annotations.Parameter;

@Parameter(
    name = "page",
    description = "Chỉ số trang, bắt đầu từ 0.",
    schema = @Schema(type = "integer", defaultValue = "0", minimum = "0"),
    example = "2"
)
~~~

Ở đây defaultValue = "0" là hành vi mặc định của API; example = "2" chỉ minh họa một request có chỉ số trang khác.

Nếu server luôn yêu cầu client truyền page, không khai báo default chỉ vì backend hiện đang tự chọn một giá trị trong code. Hãy mô tả đúng hành vi thực tế.

## 6. Dùng ví dụ tĩnh, đại diện và không chứa dữ liệu thật

Ví dụ trong OpenAPI nên:

- Có giá trị cố định để lần sinh tài liệu sau không đổi.
- Đại diện cho trường hợp thông thường và các trường hợp biên quan trọng.
- Không lấy nguyên bản ghi production hoặc dữ liệu cá nhân.
- Không chứa access token, API key, email thật, địa chỉ thật hoặc bí mật.
- Phù hợp với schema và quy tắc validation.
- Có summary/description giải thích tình huống mà ví dụ thể hiện.

Ví dụ response:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;

@Operation(
    operationId = "getOrderById",
    summary = "Lấy thông tin đơn hàng",
    responses = @ApiResponse(
        responseCode = "200",
        description = "Đơn hàng được tìm thấy.",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class),
            examples = @ExampleObject(
                name = "processingOrder",
                summary = "Đơn hàng đang được xử lý",
                value = """
                    {
                      "orderId": "ORD-10482",
                      "status": "PROCESSING",
                      "createdAt": "2030-04-15T09:30:00Z"
                    }
                    """
            )
        )
    )
)
~~~

Ví dụ trên không phụ thuộc vào một đơn hàng đang tồn tại trong database. Nó minh họa hình dạng response và có thể được giữ nguyên qua nhiều lần build.

## 7. Không tạo example bằng dữ liệu runtime

Tránh các cách làm sau trong OpenApiCustomizer, OperationCustomizer hoặc code cấu hình:

~~~java
// Không nên: ví dụ thay đổi theo thời gian và database.
openApi.getComponents()
    .getSchemas()
    .get("OrderResponse")
    .setExample(orderRepository.findTopByOrderByCreatedAtDesc());

// Không nên: cùng một build có thể sinh tài liệu khác nhau.
schema.setExample(UUID.randomUUID().toString());
schema.setDefault(Instant.now().toString());
~~~

Thay vào đó, đặt example cố định trong annotation hoặc fixture được quản lý cùng source code:

~~~java
schema.setExample("ORD-10482");
~~~

Nếu có nhiều ví dụ, đặt tên theo tình huống như processingOrder, shippedOrder, cancelledOrder. Khi nghiệp vụ thay đổi và ví dụ cần cập nhật, thay đổi đó sẽ xuất hiện trong code review và contract diff.

Không gọi repository hoặc remote service từ customizer để lấy dữ liệu mẫu. Customizer nên biến đổi OpenAPI model dựa trên cấu hình và metadata ổn định, không thực hiện nghiệp vụ.

## 8. Không dùng dữ liệu động để quyết định schema

Một hợp đồng không nên đổi hình dạng dựa trên những dòng dữ liệu đang có:

- Không thêm/bớt property theo cột nào đang có giá trị trong database.
- Không đổi kiểu field từ string sang number dựa trên dữ liệu hiện tại.
- Không suy ra enum từ các trạng thái đã xuất hiện trong bảng.
- Không tạo response schema từ bản ghi đầu tiên của một collection.
- Không bỏ field khỏi OpenAPI vì tenant hiện tại chưa có dữ liệu cho field đó.
- Không thay đổi required list theo giá trị null quan sát được ở một vài bản ghi.

Schema phải phản ánh khả năng và quy tắc của API, không phải ảnh chụp dữ liệu tại một thời điểm.

Ví dụ, nếu discountCode có thể vắng mặt hoặc null tùy đơn hàng, mô tả tính optional/nullable theo contract. Không xóa property khỏi schema chỉ vì các đơn hàng đang có trong database đều chưa dùng mã giảm giá.

## 9. Pagination và số liệu biến động

Pagination là ví dụ điển hình của dữ liệu runtime. Tổng số bản ghi, số trang và phần tử đầu tiên có thể thay đổi sau mỗi lần gọi.

Schema response nên mô tả kiểu và ý nghĩa:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "PageMetadata")
public record PageMetadata(
    @Schema(description = "Chỉ số trang bắt đầu từ 0.", example = "0")
    int page,

    @Schema(description = "Kích thước trang.", example = "20")
    int size,

    @Schema(description = "Tổng số phần tử khớp truy vấn.", example = "135")
    long totalElements,

    @Schema(description = "Tổng số trang tại thời điểm truy vấn.", example = "7")
    int totalPages
) {
}
~~~

135 và 7 chỉ là ví dụ tĩnh để giải thích response. Không lấy tổng số bản ghi thực tế từ database lúc khởi động để điền vào OpenAPI.

Nếu collection rỗng, API vẫn trả cùng schema với items là mảng rỗng và các số liệu tương ứng. Không tạo một schema riêng chỉ vì database hiện không có bản ghi.

## 10. Thời gian, ID và giá trị sinh tự động

Các field thường có giá trị thay đổi theo từng request:

| Field | Cách mô tả |
| --- | --- |
| UUID | type string, format uuid; ví dụ cố định nếu cần |
| Timestamp | type string, format date-time; example cố định theo UTC |
| Ngày | type string, format date |
| Mã giao dịch | String và pattern nếu có quy tắc ổn định |
| Giá trị ngẫu nhiên | Mô tả kiểu/range và nguồn sinh; không lấy một giá trị ngẫu nhiên làm default |
| Số dư hoặc giá hiện tại | Number với precision/range phù hợp; example chỉ minh họa |

Ví dụ:

~~~java
@Schema(
    description = "Mã định danh duy nhất của giao dịch.",
    type = "string",
    format = "uuid",
    example = "8f14e45f-ea2d-4a3f-9b12-1a2b3c4d5e6f"
)
private UUID transactionId;

@Schema(
    description = "Thời điểm giao dịch được ghi nhận.",
    type = "string",
    format = "date-time",
    example = "2030-04-15T09:30:00Z"
)
private Instant recordedAt;
~~~

Không dùng UUID.randomUUID() hoặc Instant.now() trong lúc sinh schema/example. Giá trị thật được tạo khi nghiệp vụ chạy; hợp đồng chỉ mô tả định dạng và ý nghĩa.

## 11. Giữ operationId và tên schema ổn định

OpenAPI tooling có thể dùng operationId để sinh tên method trong client SDK. Nếu operationId thay đổi giữa các build, mã client được sinh ra có thể đổi tên method dù endpoint không đổi.

Khai báo operationId rõ ràng:

~~~java
@Operation(
    operationId = "getOrderById",
    summary = "Lấy đơn hàng theo mã"
)
@GetMapping("/api/orders/{orderId}")
OrderResponse getOrderById(@PathVariable String orderId) {
    return orderService.findById(orderId);
}
~~~

Tương tự, đặt tên schema ổn định khi cần bằng @Schema(name = "OrderResponse") trên DTO. Tránh tạo operationId từ timestamp, random value, tên class proxy hoặc dữ liệu runtime. Không đổi tên schema chỉ vì đổi package nội bộ nếu contract bên ngoài không cần thay đổi.

OpenAPI yêu cầu operationId phải duy nhất giữa các operation trong document. Hãy kiểm tra uniqueness trong contract test.

## 12. Metadata và server URL nên đến từ cấu hình triển khai

Thông tin Info.version, contact, license và server URL cần ổn định trong phạm vi một release/môi trường. Không dùng thời gian hiện tại hoặc request bất kỳ làm version.

Trường openapi ở đầu document cho biết phiên bản OpenAPI Specification, còn Info.version cho biết phiên bản hợp đồng API của ứng dụng. Hai giá trị độc lập; không dùng thời gian build hoặc timestamp hiện tại làm Info.version nếu không phải quy ước release đã chọn.

Nếu các môi trường có public URL khác nhau, dùng cấu hình triển khai:

~~~yaml
app:
  public-api-url: https://api.example.test
~~~

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

import java.util.List;

@Configuration
class ApiDocumentationConfig {

    @Bean
    OpenAPI apiDocumentation(Environment environment) {
        String publicApiUrl =
            environment.getRequiredProperty("app.public-api-url");

        return new OpenAPI()
            .servers(List.of(
                new Server()
                    .url(publicApiUrl)
                    .description("Public API")
            ));
    }
}
~~~

URL có thể khác giữa dev và production, nhưng mỗi deployment có một giá trị được cấu hình rõ ràng. Không lấy host từ header tùy ý của request để tạo servers nếu chưa có forwarded-header trust boundary phù hợp.

## 13. Không tạo tài liệu khác nhau theo user hoặc tenant ngoài chủ đích

Nếu customizer lọc paths, schema hoặc examples theo user đang đăng nhập, cùng một URL /v3/api-docs có thể trả về hợp đồng khác nhau cho từng người. Điều này gây khó cho cache, gateway, contract test và client generator; trong một số cấu hình còn có nguy cơ một người nhận tài liệu đã được tạo cho người khác.

Nếu có nhiều audience:

- Dùng GroupedOpenApi với group có tên và phạm vi cố định.
- Bảo vệ endpoint tài liệu của từng group bằng quyền truy cập phù hợp.
- Không dựa vào dữ liệu tenant hiện tại để thay đổi schema dùng chung.
- Nếu thật sự cần tài liệu theo tenant, xác định rõ cache key, quyền truy cập, isolation và vòng đời; không dùng cache OpenAPI mặc định như cache riêng cho từng tenant.

Thông thường, tenant khác nhau về dữ liệu và quyền truy cập, không khác về cấu trúc contract. Hãy thể hiện khác biệt quyền bằng security scheme, scope và response code; dữ liệu của tenant được trả khi gọi API.

## 14. Hiểu đúng cache OpenAPI của springdoc

Theo FAQ springdoc, OpenAPI description mặc định được tính một lần rồi cache. Cache này giúp tránh việc quét controller và tạo lại document cho mọi request.

Thuộc tính:

~~~yaml
springdoc:
  cache:
    disabled: false
~~~

false là giá trị mặc định trong các dòng springdoc được tài liệu hóa. Khi cần tắt cache:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

FAQ nêu một trường hợp đặc biệt: cùng Swagger UI được phục vụ qua proxy nội bộ và bên ngoài, và server URL cần được tính lại theo từng HTTP request. Đây là tình huống có thể cân nhắc tắt cache sau khi cấu hình forwarded headers và trust boundary đúng.

Không tắt cache chỉ để làm ví dụ, enum hoặc schema lấy từ database cập nhật liên tục. Cách đó biến hợp đồng thành đầu ra phụ thuộc runtime, tăng chi phí sinh tài liệu và khiến kết quả khó tái lập. Nếu giá trị là dữ liệu nghiệp vụ, hãy đưa nó về response của endpoint nghiệp vụ thay vì OpenAPI document.

## 15. Sắp xếp output ổn định để review

Có thể bật sắp xếp key khi serialize tài liệu:

~~~yaml
springdoc:
  writer-with-order-by-keys: true
~~~

Thuộc tính này giúp thứ tự key trong output dễ dự đoán hơn, thuận tiện cho diff và review. Nó không làm cho dữ liệu động trở nên ổn định: một timestamp mới, example lấy từ DB hoặc server URL thay đổi vẫn tạo ra diff.

Khi so sánh OpenAPI trong CI, có thể chuẩn hóa JSON trước:

~~~bash
curl -sS http://localhost:8080/v3/api-docs | jq -S . > openapi.json
~~~

Sau đó so sánh với artifact của release trước. Hãy xem diff theo ngữ nghĩa:

- Operation hoặc HTTP method bị thêm/xóa.
- Required field hoặc kiểu dữ liệu thay đổi.
- Enum/format/range thay đổi.
- Response status hoặc schema thay đổi.
- Security requirement hoặc server URL thay đổi.
- Example thay đổi ngoài chủ đích.

Không tự động chấp nhận mọi snapshot diff. Ví dụ và description cũng là một phần trải nghiệm tích hợp; thay đổi của chúng cần được review dù không phải lúc nào cũng phá vỡ tương thích.

## 16. Kiểm thử tính xác định của OpenAPI document

Có thể viết integration test gọi endpoint tài liệu hai lần trong cùng test context và so sánh nội dung:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiStabilityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentDoesNotChangeBetweenRequests() throws Exception {
        MvcResult first = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn();

        MvcResult second = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn();

        assertThat(first.getResponse().getContentAsString())
            .isEqualTo(second.getResponse().getContentAsString());
    }
}
~~~

Test này phát hiện một số nguồn không ổn định như timestamp/random value được tạo trong customizer. Nếu tài liệu có server URL được suy ra từ forwarded headers, hai request test phải dùng cùng forwarded headers; nếu không, khác biệt URL có thể là hành vi được cấu hình có chủ đích.

Ngoài so sánh toàn bộ JSON, nên có assertion riêng cho các phần quan trọng:

1. operationId không trùng.
2. Schema name và property không đổi ngoài chủ đích.
3. Ví dụ khớp schema.
4. default chỉ được khai báo khi có ý nghĩa thật.
5. Không có credential hoặc dữ liệu cá nhân trong example, description hay extension.
6. Không có giá trị được lấy từ database/runtime trong metadata.

## 17. Kiểm tra ví dụ không chứa dữ liệu nhạy cảm

Một bộ test hoặc bước kiểm tra CI có thể rà soát các trường dễ chứa bí mật:

- example, examples và default.
- description, summary và externalDocs.
- servers.url.
- components.securitySchemes.
- Extension bắt đầu bằng x-.

Không chỉ tìm chuỗi Bearer; API key, cookie, client secret, email thật và URL nội bộ cũng có thể xuất hiện trong tài liệu. Dùng dữ liệu tổng hợp có quy ước rõ như user@example.test, api.example.test và mã đơn giả.

Nếu cần chia sẻ tài liệu được sinh từ production để debug, hãy rà soát và làm sạch dữ liệu trước khi lưu artifact hoặc gửi cho bên ngoài. Không giả định OpenAPI document luôn vô hại chỉ vì nó là JSON/YAML.

## 18. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| OpenAPI thay đổi mỗi lần gọi | Customizer tạo timestamp/UUID hoặc truy vấn dữ liệu runtime | Dùng metadata và example cố định |
| Enum trong tài liệu thiếu giá trị mới | Enum được sinh từ dữ liệu đang có trong DB | Dùng kiểu tổng quát hoặc version hóa danh mục |
| Swagger UI hiển thị dữ liệu khách hàng thật | Example lấy từ bản ghi production | Thay bằng fixture tổng hợp, làm sạch artifact |
| Client generator đổi tên method | operationId được sinh từ tên method/class không ổn định | Khai báo operationId rõ ràng và giữ ổn định |
| default thay đổi theo thời gian | Dùng thời gian hiện tại hoặc dữ liệu mới nhất làm default | Chỉ khai báo default theo hành vi API |
| Tài liệu khác nhau giữa user/tenant | Customizer phụ thuộc security context hoặc tenant | Dùng group cố định; tách quyền xem tài liệu |
| Tài liệu không cập nhật sau thay đổi cấu hình | Cache giữ document đã tạo | Kiểm tra cache và vòng đời restart/config refresh |
| Tắt cache làm ứng dụng chậm | Tính lại OpenAPI trên mỗi request | Chỉ tắt cache khi có lý do như server URL qua proxy |
| Snapshot luôn khác dù contract không đổi | Key order hoặc dữ liệu biến động | Bật order-by-keys, chuẩn hóa và loại nguồn dynamic |
| servers chứa host nội bộ | URL suy ra từ request/proxy chưa được cấu hình đúng | Dùng public URL cấu hình hoặc forwarded headers đáng tin cậy |

## 19. Quy trình xây dựng hợp đồng ổn định

1. Xác định DTO và schema công khai độc lập với entity persistence.
2. Định nghĩa kiểu, format, required, nullable, range và pattern theo quy tắc API.
3. Chỉ dùng enum cho tập giá trị ổn định; dữ liệu danh mục động được tra cứu qua endpoint riêng.
4. Dùng example cố định, tổng hợp và khớp schema.
5. Dùng default chỉ khi API thực sự có giá trị mặc định.
6. Không gọi database, remote API, clock hoặc random generator trong customizer để xây schema/example.
7. Giữ operationId, schema name, tag và Info.version ổn định.
8. Đưa server URL theo cấu hình triển khai; chỉ tính theo request khi có yêu cầu proxy cụ thể và cache/trust được thiết kế phù hợp.
9. Giữ cache mặc định trừ khi có lý do kỹ thuật rõ ràng để tắt.
10. Xuất JSON/YAML trong CI, chuẩn hóa output và review contract diff.
11. Rà soát example, server URL, description và extension để không rò rỉ dữ liệu thật.

Một hợp đồng tốt mô tả điều API cam kết, không mô tả tình cờ database đang chứa gì ở thời điểm tài liệu được sinh. Khi schema, metadata và ví dụ được quản lý như mã nguồn ổn định, client có thể dựa vào tài liệu qua nhiều lần triển khai mà không bị bất ngờ bởi dữ liệu runtime.

## Tài liệu tham khảo

- [springdoc-openapi – FAQ: OpenAPI cache và server URL](https://springdoc.org/faq.html)
- [springdoc-openapi – Configuration Properties: cache và writer ordering](https://springdoc.org/properties.html)
- [OpenAPI Specification – Schema Object và examples](https://spec.openapis.org/oas/latest.html#schema-object)
- [OpenAPI Specification – Example Object](https://spec.openapis.org/oas/latest.html#example-object)
- [OpenAPI Specification – Operation Object và operationId](https://spec.openapis.org/oas/latest.html#operation-object)
- [Swagger Annotations – @Schema](https://docs.swagger.io/swagger-core/v2.2.53/apidocs/io/swagger/v3/oas/annotations/media/Schema.html)
- [Swagger Annotations – @ExampleObject](https://docs.swagger.io/swagger-core/v2.2.53/apidocs/io/swagger/v3/oas/annotations/media/ExampleObject.html)
