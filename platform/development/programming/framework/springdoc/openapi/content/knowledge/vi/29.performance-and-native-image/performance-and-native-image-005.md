# Giới hạn kích thước ví dụ và mô tả để giữ tài liệu dễ tải

OpenAPI Description có thể trở nên rất lớn khi một API có nhiều operation, schema lồng nhau, ví dụ request/response dài và mô tả chứa nhiều đoạn Markdown. Tài liệu lớn làm tăng thời gian sinh và tải file, chi phí truyền qua mạng, bộ nhớ cần để parse JSON/YAML và thời gian Swagger UI dựng giao diện. Người tích hợp cũng khó tìm thông tin quan trọng khi mỗi operation mang theo nhiều nội dung lặp lại.

Giữ tài liệu gọn không có nghĩa là xóa thông tin hợp đồng. Cần nhận diện phần nào mô tả cấu trúc API, phần nào chỉ là dữ liệu minh họa hoặc hướng dẫn dài; sau đó đặt giới hạn có chủ đích cho example, description, schema và phạm vi tài liệu. Các chi tiết cần thiết để hiểu request, response, validation và security vẫn phải được giữ lại.

Bài này hướng dẫn đo dung lượng OpenAPI document, rút gọn ví dụ và mô tả, tái sử dụng schema/example, chia tài liệu theo API group, tối ưu cách phục vụ và đặt ngân sách dung lượng trong CI.

## 1. Vì sao kích thước tài liệu ảnh hưởng hiệu năng?

Một lần mở Swagger UI thường gồm nhiều công đoạn:

~~~mermaid
flowchart TD
    A["Browser opens API docs"] --> B["Download Swagger UI assets"]
    B --> C["Download OpenAPI JSON/YAML"]
    C --> D["Parse document"]
    D --> E["Resolve schemas and references"]
    E --> F["Render tags, operations, models and examples"]
    F --> G["User expands an operation"]
~~~

Document lớn có thể làm tăng chi phí ở nhiều nơi:

| Công đoạn | Tác động của document lớn |
|---|---|
| Sinh tài liệu | Springdoc phải phân tích metadata và serialize nhiều object |
| Truyền tải | Nhiều byte hơn đi qua ứng dụng, proxy và trình duyệt |
| Parse | Browser hoặc tool tiêu thụ cần thêm CPU và bộ nhớ |
| Render | Nhiều operation, schema và example làm giao diện dựng chậm hơn |
| CI | Artifact lớn hơn, validator và diff có thể chạy lâu hơn |
| Consumer tooling | Code generator hoặc API portal phải xử lý nhiều nội dung hơn |

Không phải mọi document lớn đều chậm như nhau. Một file có nhiều schema tái sử dụng bằng reference có thể dễ xử lý hơn file có nhiều schema inline trùng lặp. Một example JSON lớn vài megabyte có thể ảnh hưởng tải và render nhiều hơn hàng trăm dòng description ngắn.

## 2. OpenAPI không đặt một giới hạn byte chung cho mọi document

OpenAPI Specification định nghĩa cấu trúc và ý nghĩa của document, nhưng không đưa ra một giới hạn byte tối đa chung áp dụng cho mọi server, proxy, browser, API portal hoặc generator.

Giới hạn thực tế phụ thuộc vào:

- Kích thước response mà ứng dụng và reverse proxy cho phép.
- Timeout và giới hạn bộ nhớ của browser hoặc API documentation portal.
- Giới hạn upload/import của registry hoặc gateway.
- Khả năng parse và render của phiên bản Swagger UI.
- Thời gian CI chấp nhận cho generation, validation và diff.
- Mạng của nhóm phát triển hoặc consumer.

Vì vậy, không nên áp một con số tùy ý như 1 MB hay 5 MB cho mọi dự án. Hãy đo document hiện tại, xác định ngưỡng phù hợp với môi trường tiêu thụ, theo dõi xu hướng tăng và đặt budget có lý do.

Nên theo dõi ít nhất ba số liệu:

1. **Raw size:** số byte của JSON/YAML được lưu.
2. **Compressed size:** số byte sau gzip hoặc Brotli khi truyền qua HTTP.
3. **Structural size:** số path, operation, schema, parameter và example trong document.

Compressed size phản ánh chi phí truyền tải tốt hơn khi server bật compression. Raw size vẫn quan trọng vì browser phải parse nội dung sau giải nén. Structural size giúp giải thích tại sao document tăng.

## 3. Xác định thành phần làm document phình to

Những nguồn thường làm tài liệu lớn:

- Example request hoặc response chứa mảng dữ liệu rất dài.
- Example chứa base64, ảnh, PDF hoặc chuỗi nhị phân được encode.
- Description sao chép cả hướng dẫn sử dụng, bảng mã lỗi hoặc tài liệu nghiệp vụ dài.
- Nhiều operation lặp lại cùng một schema inline.
- DTO có nhiều field nội bộ hoặc field không thuộc hợp đồng công khai.
- Nhiều API group bị gộp vào một document duy nhất.
- Example được khai báo lặp ở cả schema, media type và từng operation.
- Tên, mô tả hoặc example được sinh động theo môi trường.

Không nên chỉ nhìn tổng byte rồi cắt bớt nội dung. Trước tiên hãy xác định phần đóng góp lớn nhất. Nếu example chiếm phần lớn, rút gọn example có thể giảm mạnh kích thước mà không thay đổi schema. Nếu schema bị lặp, tái sử dụng component có thể hiệu quả hơn. Nếu document chứa nhiều bounded context độc lập, chia group có thể giảm lượng dữ liệu người dùng phải tải cho mỗi nhóm.

## 4. Đo dung lượng file OpenAPI

Nếu Gradle plugin sinh file mặc định tại build/openapi.json, có thể đo raw size bằng PowerShell:

~~~powershell
(Get-Item "build/openapi.json").Length
~~~

Hoặc trên Linux/macOS:

~~~bash
wc -c < build/openapi.json
~~~

Đo kích thước gzip để ước lượng payload truyền qua HTTP khi compression được bật:

~~~bash
gzip -c build/openapi.json | wc -c
~~~

Để so sánh xu hướng, ghi lại số liệu cùng commit, API group, profile và phiên bản springdoc. Không so sánh raw size của public API với compressed size của admin API.

### Đếm operation và schema

Có thể dùng jq để đếm số operation trong JSON:

~~~bash
jq '[.paths[] | keys[] | select(
  . == "get" or . == "post" or . == "put" or
  . == "patch" or . == "delete" or . == "options" or
  . == "head" or . == "trace"
)] | length' build/openapi.json
~~~

Đếm schema component:

~~~bash
jq '(.components.schemas // {}) | length' build/openapi.json
~~~

Các con số này không thay thế việc phân tích nội dung. Một operation có example rất lớn vẫn có thể làm document nặng dù tổng operation thấp.

## 5. Giới hạn kích thước example

Example giúp người đọc hiểu cách gửi request và đọc response. Một example tốt thể hiện hình dạng dữ liệu và một tình huống điển hình. Nó không cần chứa toàn bộ dữ liệu có thể xuất hiện trong production.

Nên ưu tiên:

- Dùng một bản ghi đại diện thay vì mảng hàng trăm bản ghi.
- Chọn giá trị ngắn nhưng hợp lệ với schema.
- Chỉ giữ field cần để minh họa operation.
- Dùng một ví dụ cho luồng thành công phổ biến và thêm ví dụ lỗi khi chúng giải thích một hợp đồng khác biệt quan trọng.
- Tránh lặp lại cùng payload ở nhiều nơi nếu có thể tham chiếu example dùng chung.
- Không nhúng base64, file nhị phân hoặc log dài vào example.
- Không dùng token, cookie, dữ liệu cá nhân hoặc thông tin production thật.

Ví dụ response danh sách không cần chứa cả trang dữ liệu:

~~~json
{
  "items": [
    {
      "id": "prd-1001",
      "name": "Keyboard",
      "price": 1250000
    },
    {
      "id": "prd-1002",
      "name": "Mouse",
      "price": 450000
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 2
}
~~~

Ví dụ này minh họa một trang có hai item. Nếu API có thể trả hàng nghìn item, hãy mô tả pagination trong schema và description; không cần nhúng hàng nghìn phần tử vào document.

### Example không phải giới hạn dữ liệu runtime

Rút ngắn example chỉ thay đổi nội dung minh họa. Nó không đặt giới hạn số phần tử mà API có thể trả, không bật pagination và không giới hạn request body. Những giới hạn runtime phải được thực hiện trong controller, validation, service hoặc cấu hình server tương ứng.

Ngược lại, schema có minItems, maxItems, maxLength hoặc maximum là ràng buộc hợp đồng. Chỉ khai báo các constraint đó khi API thực sự áp dụng chúng; không thêm maxItems chỉ để làm example ngắn.

## 6. Khai báo example ngắn gọn bằng annotation

Có thể dùng @Schema để mô tả một giá trị mẫu cho field:

~~~java
import java.math.BigDecimal;
import io.swagger.v3.oas.annotations.media.Schema;

public record CreateProductRequest(
    @Schema(
        description = "Tên hiển thị của sản phẩm.",
        example = "Keyboard"
    )
    String name,

    @Schema(
        description = "Giá bán theo đơn vị tiền tệ của cửa hàng.",
        example = "1250000"
    )
    BigDecimal price
) {}
~~~

Example ở cấp field giúp người đọc hiểu kiểu và hình dạng giá trị. Description nên giải thích ý nghĩa hoặc quy tắc quan trọng, không lặp lại toàn bộ ví dụ.

Với request body, dùng @ExampleObject để mô tả một payload:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;

@PostMapping("/products")
@Operation(
    summary = "Tạo sản phẩm",
    description = "Tạo một sản phẩm mới trong danh mục.",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            examples = @ExampleObject(
                name = "basic-product",
                summary = "Sản phẩm cơ bản",
                value = """
                    {
                      "name": "Keyboard",
                      "price": 1250000
                    }
                    """
            )
        )
    )
)
public ResponseEntity<ProductResponse> create(
        @org.springframework.web.bind.annotation.RequestBody
        CreateProductRequest request) {
    // ...
}
~~~

Trong code thực tế, RequestBody annotation được đặt trong metadata của operation hoặc trên tham số tương ứng theo cách khai báo của controller. Không thêm một example lớn chỉ để lặp lại schema mà người đọc đã nhìn thấy ngay bên dưới.

## 7. Tái sử dụng example thay vì sao chép

OpenAPI hỗ trợ khai báo example dùng chung trong components rồi tham chiếu từ nhiều operation:

~~~yaml
components:
  examples:
    BasicProduct:
      summary: Sản phẩm cơ bản
      value:
        name: Keyboard
        price: 1250000
paths:
  /products:
    post:
      requestBody:
        content:
          application/json:
            examples:
              basic:
                $ref: '#/components/examples/BasicProduct'
~~~

Tái sử dụng example tránh sao chép cùng một payload vào nhiều operation và giúp sửa ví dụ tại một nơi. Với annotation, có thể dùng tham chiếu Example Object nếu phiên bản swagger-annotations đang dùng hỗ trợ thuộc tính ref.

Không nên tạo component cho mọi example nhỏ chỉ để giảm vài byte. Reference làm cấu trúc phức tạp hơn và tool tiêu thụ phải resolve nó. Chỉ tái sử dụng khi payload có ý nghĩa chung và được nhiều operation dùng.

## 8. Đưa example rất lớn ra ngoài document

OpenAPI Example Object có thuộc tính externalValue để trỏ tới nội dung ví dụ ở một URL bên ngoài. Cách này có thể giữ OpenAPI document nhẹ hơn khi cần cung cấp file mẫu lớn:

~~~yaml
paths:
  /reports/export:
    get:
      responses:
        "200":
          description: File báo cáo được tạo.
          content:
            application/json:
              examples:
                sample:
                  summary: Một báo cáo mẫu
                  externalValue: https://docs.example.com/examples/report-sample.json
~~~

External example phù hợp với:

- Payload lớn cần tải riêng khi người dùng thật sự muốn xem.
- File mẫu CSV hoặc JSON nhiều dòng.
- Bộ fixture dùng trong hướng dẫn tích hợp.
- Ví dụ nhị phân hoặc file tải xuống không phù hợp nhúng vào JSON OpenAPI.

Có một số giới hạn cần cân nhắc:

- External URL phải ổn định, có version hoặc được quản lý cùng release.
- Consumer có thể không tự tải externalValue.
- Swagger UI và API portal có thể hỗ trợ external example khác nhau.
- URL riêng tư có thể yêu cầu authentication mà browser hoặc generator không có.
- Tài liệu có thể mất tính tự chứa nếu example bị xóa hoặc URL đổi.

Nếu example quan trọng cho contract test, lưu fixture trong repository hoặc artifact có version và kiểm tra nó trong CI. Không phụ thuộc vào một URL công khai không được quản lý.

## 9. Giới hạn độ dài description

Description nên trả lời câu hỏi mà người tích hợp cần biết tại vị trí đó. Một mô tả ngắn, cụ thể thường hữu ích hơn đoạn văn dài lặp lại schema.

| Vị trí | Nên mô tả điều gì? |
|---|---|
| OpenAPI info.description | Phạm vi API, audience và quy tắc chung |
| Tag description | Nhóm nghiệp vụ hoặc miền tài nguyên |
| Operation summary | Hành động ngắn gọn của endpoint |
| Operation description | Điều kiện, luồng xử lý hoặc hành vi đặc biệt |
| Parameter description | Ý nghĩa, định dạng, đơn vị và cách truyền |
| Schema/property description | Ý nghĩa field, constraint nghiệp vụ và đơn vị |
| Response description | Điều kiện trả status code |

Tránh:

- Chép lại tên field ngay trong description mà không bổ sung ý nghĩa.
- Dán nguyên trang hướng dẫn vào từng operation.
- Lặp cùng nội dung authentication ở mọi operation khi đã mô tả bằng security scheme và policy chung.
- Nhúng stack trace, log hoặc payload production dài.
- Dùng Markdown table rất lớn cho danh sách giá trị có thể được mô tả bằng enum hoặc link tài liệu.
- Dùng description để thay thế schema, required, format hoặc constraint có thể biểu diễn bằng OpenAPI.

Không có giới hạn ký tự description chung trong OAS. Nhóm dự án nên đặt style guide, ví dụ giới hạn độ dài summary, description cấp operation và description cấp property, rồi áp dụng bằng review hoặc lint rule. Ngưỡng cụ thể nên dựa trên khả năng đọc và dữ liệu thực tế của module.

## 10. Đưa hướng dẫn dài sang tài liệu riêng

Nếu một operation cần hướng dẫn nhiều bước, ví dụ nghiệp vụ dài hoặc giải thích quy trình, hãy giữ một đoạn tóm tắt trong OpenAPI và đặt phần hướng dẫn chi tiết ở tài liệu riêng.

OpenAPI hỗ trợ External Documentation Object ở cấp tài liệu, tag hoặc operation. Ví dụ annotation:

~~~java
import io.swagger.v3.oas.annotations.ExternalDocumentation;
import io.swagger.v3.oas.annotations.Operation;

@Operation(
    summary = "Tạo đơn hàng",
    description = "Tạo đơn hàng từ các sản phẩm đã chọn.",
    externalDocs = @ExternalDocumentation(
        description = "Hướng dẫn vòng đời đơn hàng",
        url = "https://docs.example.com/orders/lifecycle"
    )
)
~~~

Ví dụ YAML:

~~~yaml
paths:
  /orders:
    post:
      summary: Tạo đơn hàng
      description: Tạo đơn hàng từ các sản phẩm đã chọn.
      externalDocs:
        description: Hướng dẫn vòng đời đơn hàng
        url: https://docs.example.com/orders/lifecycle
~~~

OpenAPI vẫn giữ phần cần thiết để hiểu operation: request, response, parameter, security và các điều kiện quan trọng. Link ngoài chỉ bổ sung hướng dẫn dài, không thay thế nội dung hợp đồng.

## 11. Tái sử dụng schema bằng components và $ref

Nếu nhiều operation dùng cùng một cấu trúc, hãy dùng schema component chung thay vì lặp lại một object inline ở từng nơi.

~~~yaml
components:
  schemas:
    ProductSummary:
      type: object
      required:
        - id
        - name
      properties:
        id:
          type: string
        name:
          type: string
        price:
          type: number
          format: double
paths:
  /products:
    get:
      responses:
        "200":
          description: Danh sách sản phẩm
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/ProductSummary'
  /products/{id}:
    get:
      responses:
        "200":
          description: Chi tiết sản phẩm
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductSummary'
~~~

Springdoc thường nhận diện model Java được tái sử dụng và tạo component schema để tham chiếu. Dùng DTO riêng, có tên rõ ràng và tái sử dụng khi hai operation thực sự có cùng hợp đồng. Không ép mọi endpoint dùng chung một DTO khổng lồ chỉ để giảm số dòng OpenAPI.

Schema dùng chung có thể làm thay đổi một lúc nhiều operation khi DTO thay đổi. Vì vậy, cần kiểm tra semantic diff và cân nhắc tách request model, response model hoặc view model khi ý nghĩa của chúng khác nhau.

## 12. Không đưa field nội bộ vào public schema

Một DTO nội bộ có thể chứa field phục vụ persistence, tracing, audit hoặc xử lý nội bộ. Nếu tất cả field đều xuất hiện trong OpenAPI, document vừa lớn hơn vừa có thể tiết lộ cấu trúc không dành cho consumer.

Nên thiết kế request/response DTO dành riêng cho hợp đồng công khai. Chỉ dùng annotation ẩn field khi field đó thực sự không thuộc hợp đồng:

~~~java
public record ProductResponse(
    String id,
    String name,

    @Schema(hidden = true)
    String internalWarehouseKey
) {}
~~~

Trong ví dụ, internalWarehouseKey không được công bố trong schema. Việc ẩn field khỏi OpenAPI không tự loại field khỏi JSON runtime. Nếu serializer vẫn trả field đó, tài liệu và response thực tế sẽ không khớp. Hãy cấu hình Jackson hoặc DTO để response thật cũng không phát ra dữ liệu nội bộ.

Không dùng hidden=true chỉ để làm tài liệu nhỏ hơn nếu field đó là một phần của API mà client cần biết. Mục tiêu là công bố đúng hợp đồng, không che giấu contract.

## 13. Chia tài liệu theo API group

Nếu một ứng dụng phục vụ nhiều miền độc lập như catalog, orders và billing, một document duy nhất có thể chứa quá nhiều operation. springdoc hỗ trợ GroupedOpenApi để tạo tài liệu riêng theo path hoặc package.

~~~java
import org.springframework.context.annotation.Bean;
import org.springdoc.core.models.GroupedOpenApi;

@Bean
GroupedOpenApi catalogApi() {
    return GroupedOpenApi.builder()
        .group("catalog")
        .pathsToMatch("/api/catalog/**")
        .build();
}

@Bean
GroupedOpenApi ordersApi() {
    return GroupedOpenApi.builder()
        .group("orders")
        .pathsToMatch("/api/orders/**")
        .build();
}
~~~

Các tài liệu group thường được phục vụ ở:

~~~text
/v3/api-docs/catalog
/v3/api-docs/orders
~~~

Tách group giúp người dùng chỉ tải phần tài liệu liên quan. Có thể dùng nhiều tài liệu trong Swagger UI hoặc cung cấp từng URL riêng cho portal và consumer.

Không chia quá nhỏ đến mức người dùng phải mở nhiều document để hiểu một workflow đơn giản. Chọn ranh giới theo bounded context, nhóm consumer hoặc quyền truy cập thực tế. Mỗi group cần có server URL, security và metadata nhất quán.

## 14. Tối ưu Swagger UI mà không thay đổi hợp đồng

Document nhỏ hơn thường giúp Swagger UI tải và parse nhanh hơn. Ngoài ra, có thể giảm lượng nội dung được mở rộng ngay khi giao diện hiển thị.

Ví dụ cấu hình UI:

~~~yaml
springdoc:
  swagger-ui:
    doc-expansion: none
    default-models-expand-depth: -1
    display-request-duration: true
~~~

Ý nghĩa:

- doc-expansion none thu gọn operation theo mặc định.
- default-models-expand-depth -1 ẩn phần model expansion mặc định.
- display-request-duration hiển thị thời gian của request Try it out.

Các tùy chọn này ảnh hưởng cách Swagger UI trình bày tài liệu. Chúng không làm giảm số byte của OpenAPI JSON/YAML và không xóa schema hay operation khỏi hợp đồng.

Tên property và khả năng hỗ trợ có thể phụ thuộc phiên bản springdoc/Swagger UI được đóng gói. Hãy xác minh trong tài liệu của đúng phiên bản đang dùng.

## 15. Bật HTTP compression cho endpoint tài liệu

Nếu OpenAPI document lớn nhưng vẫn cần cung cấp đầy đủ, HTTP compression có thể giảm số byte truyền qua mạng. Với Spring Boot, cấu hình server compression có thể bật như sau:

~~~yaml
server:
  compression:
    enabled: true
    mime-types:
      - application/json
      - application/yaml
      - text/yaml
    min-response-size: 2KB
~~~

Danh sách MIME type cần khớp Content-Type mà endpoint thực tế trả về. Kiểm tra response header và dùng curl để xác nhận server/proxy thực sự trả Content-Encoding: gzip khi client gửi Accept-Encoding: gzip.

Compression giảm payload truyền tải, nhưng browser vẫn phải giải nén và parse document. Nó không giải quyết schema trùng lặp, example quá lớn hoặc giao diện phải dựng quá nhiều operation.

Nếu reverse proxy hoặc ingress đã nén response, tránh cấu hình nhiều lớp gây nén hai lần. Chọn một tầng chịu trách nhiệm và đo kích thước thực tế.

## 16. Cân nhắc cache và tài liệu tĩnh

Nếu OpenAPI document không thay đổi theo từng request, có thể cân nhắc cache ở reverse proxy hoặc phục vụ file tĩnh được tạo trong release. Điều này giúp giảm chi phí sinh tài liệu và response lặp lại.

Trước khi cache, xác định:

- Document có thay đổi theo Spring profile, tenant hoặc user không?
- Endpoint docs có yêu cầu authentication không?
- Có group hoặc server URL được tạo từ forwarded headers không?
- Cache key có bao gồm host, path và query cần thiết không?
- Khi phát hành phiên bản mới, cache có được invalidated không?

Không cache công khai một document có chứa metadata riêng tư hoặc khác nhau theo quyền truy cập. Nếu dùng tài liệu tĩnh, gắn file với commit/release và công bố URL có version để consumer biết họ đang đọc hợp đồng nào.

## 17. Đặt ngân sách dung lượng trong CI

Đặt một ngưỡng dung lượng giúp phát hiện document tăng bất thường. Ngưỡng phải dựa trên baseline của dự án, mức tải thực tế và giới hạn của công cụ tiêu thụ.

Ví dụ Bash:

~~~bash
./gradlew generateOpenApiDocs

bytes=$(wc -c < build/openapi.json)
echo "OpenAPI raw size: $bytes bytes"

if [ "$bytes" -gt "$MAX_OPENAPI_BYTES" ]; then
  echo "OpenAPI document exceeds the configured size budget"
  exit 1
fi

gzip -c build/openapi.json > build/openapi.json.gz
gzip_bytes=$(wc -c < build/openapi.json.gz)
echo "OpenAPI gzip size: $gzip_bytes bytes"
~~~

MAX_OPENAPI_BYTES là biến CI được cấu hình theo budget của dự án. Không đặt một giá trị ví dụ rồi coi đó là giới hạn chuẩn của OpenAPI.

Có thể theo dõi thêm số operation và schema:

~~~bash
operations=$(jq '[.paths[] | keys[] | select(
  . == "get" or . == "post" or . == "put" or
  . == "patch" or . == "delete" or . == "options" or
  . == "head" or . == "trace"
)] | length' build/openapi.json)

schemas=$(jq '(.components.schemas // {}) | length' build/openapi.json)

echo "Operations: $operations"
echo "Schemas: $schemas"
~~~

CI có thể cảnh báo khi raw size hoặc gzip size tăng vượt mức cho phép. Nếu chỉ số tăng, tạo report hoặc yêu cầu reviewer xác định phần đóng góp trước khi chặn merge. Không tự động xóa example hay description để ép pipeline xanh.

## 18. Lint description và example theo style guide

Ngoài byte budget, có thể dùng lint rule hoặc script để kiểm tra:

- Summary quá dài hoặc không phải một câu hành động ngắn.
- Description lặp lại cùng nội dung ở nhiều operation.
- Example chứa base64, token hoặc dữ liệu nhạy cảm.
- Example không parse được JSON hoặc không khớp schema.
- Description có đoạn log, stack trace hoặc nội dung không liên quan.
- Schema không được tái sử dụng dù có cùng ý nghĩa.
- Operation thiếu summary hoặc response description quan trọng.

Các công cụ lint OpenAPI có thể hỗ trợ rule tùy chỉnh. Chọn rule dựa trên style guide của nhóm và tránh giới hạn quá chặt khiến tài liệu thiếu thông tin. Một description ngắn nhưng mơ hồ có thể làm tăng thời gian tích hợp dù document nhẹ hơn.

## 19. Các lỗi thường gặp khi tối ưu

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| File JSON lớn dù số operation ít | Example hoặc schema inline quá lớn | Đo phần đóng góp, rút gọn example và tái sử dụng component |
| Swagger UI mở chậm dù gzip nhỏ | Parse/render tốn CPU hoặc quá nhiều operation/schema | Chia group và thu gọn UI expansion |
| Description chiếm nhiều dung lượng | Copy hướng dẫn dài vào từng operation | Giữ tóm tắt, dùng External Documentation |
| Nhiều example gần giống nhau | Lặp payload ở nhiều operation | Tái sử dụng component example hoặc chỉ giữ ví dụ khác biệt |
| Tài liệu thiếu field sau tối ưu | Dùng hidden=true hoặc bỏ schema quá rộng | Đối chiếu hợp đồng công khai và response runtime |
| External example không mở được | URL không ổn định hoặc consumer không resolve | Version hóa fixture và kiểm tra khả năng hỗ trợ của UI/tool |
| Compression không giảm kích thước | MIME type không khớp hoặc proxy không bật compression | Kiểm tra Content-Type, Accept-Encoding và Content-Encoding |
| Group document bị thiếu operation | Filter path/package sai | Kiểm tra GroupedOpenApi và URL group |
| File tăng mạnh sau nâng springdoc | Serializer hoặc schema resolution thay đổi | Review semantic diff, component count và release notes |
| CI báo vượt budget nhưng không rõ lý do | Chỉ đo tổng byte | Lưu metric operation/schema và report thay đổi |

## 20. Quy trình tối ưu tài liệu theo từng bước

Khi OpenAPI document vượt budget hoặc Swagger UI tải chậm:

1. Sinh lại document từ profile và group xác định.
2. Đo raw size và compressed size.
3. Đếm operation, schema và xem diff với baseline.
4. Xác định example, description hoặc schema nào đóng góp lớn nhất.
5. Rút gọn example về một payload đại diện hợp lệ.
6. Chuyển fixture rất lớn sang externalValue hoặc tài liệu riêng nếu phù hợp.
7. Tái sử dụng schema/example có cùng ý nghĩa.
8. Rút gọn description và chuyển hướng dẫn dài sang externalDocs.
9. Chia document theo bounded context nếu người dùng không cần tải toàn bộ API.
10. Cấu hình UI expansion và HTTP compression nếu cần.
11. Chạy validator, semantic diff và contract test để bảo đảm hợp đồng không bị mất.
12. Cập nhật budget sau khi review, không tự động nới ngưỡng theo mọi lần tăng.

Sau tối ưu, kiểm tra lại file OpenAPI và response runtime. Dung lượng nhỏ hơn không phải tiêu chí duy nhất; tài liệu vẫn phải đủ để consumer xây request hợp lệ và hiểu response.

## 21. Checklist giữ OpenAPI document dễ tải

- [ ] Đã đo raw size và compressed size.
- [ ] Đã xác định profile, group và commit tạo snapshot.
- [ ] Example chỉ minh họa payload điển hình, không chứa dữ liệu production.
- [ ] Không nhúng base64 hoặc file lớn vào example nếu không cần.
- [ ] Example phù hợp schema và có thể parse.
- [ ] Example dùng chung được tái sử dụng khi có lợi.
- [ ] Description ngắn gọn, không lặp schema hoặc tài liệu dài.
- [ ] Hướng dẫn dài được chuyển sang External Documentation.
- [ ] Schema component được tái sử dụng khi hợp đồng thực sự giống nhau.
- [ ] Không ẩn field công khai chỉ để giảm dung lượng.
- [ ] API group được chia theo ranh giới người dùng có ý nghĩa.
- [ ] Swagger UI expansion được cấu hình phù hợp với quy mô document.
- [ ] Compression được kiểm tra bằng response header thực tế.
- [ ] Cache không làm lộ tài liệu riêng tư hoặc phục vụ phiên bản cũ.
- [ ] CI có budget và report giải thích khi dung lượng tăng.
- [ ] Validator, semantic diff và runtime contract test vẫn PASS.

## 22. Kết luận

Giữ OpenAPI document dễ tải bắt đầu bằng việc đo raw size, compressed size và cấu trúc của tài liệu. Hãy dùng example nhỏ nhưng hợp lệ, description ngắn và đúng vị trí, schema/example dùng chung khi có ý nghĩa, externalValue cho fixture lớn và External Documentation cho hướng dẫn dài. Khi ứng dụng có nhiều miền API, chia GroupedOpenApi theo nhu cầu consumer; compression và UI expansion chỉ tối ưu truyền tải hoặc hiển thị, không thay đổi hợp đồng. Đặt budget trong CI để phát hiện tăng trưởng bất thường, đồng thời chạy validator, semantic diff và contract test để bảo đảm việc tối ưu không làm mất thông tin mà client cần.
