# Các handler dùng chung path nhưng khác consumes hoặc produces

Spring MVC cho phép nhiều handler cùng xử lý một đường dẫn và HTTP method nếu các điều kiện mapping phân biệt được request, chẳng hạn `consumes` hoặc `produces`. Cách tổ chức này hữu ích khi một endpoint nhận nhiều định dạng payload hoặc trả nhiều kiểu representation. Khi tạo tài liệu bằng springdoc-openapi, cần hiểu thêm một giới hạn của OpenAPI: mỗi cặp path và HTTP method chỉ có một operation. Các handler ở runtime vì vậy phải được phản ánh thành một hợp đồng operation thống nhất, với nhiều media type trong request body hoặc response khi phù hợp.

## 1. Vì sao nhiều handler có thể dùng chung path và HTTP method?

Spring không chỉ chọn handler dựa trên URL và HTTP method. Một request mapping còn có thể chứa các điều kiện như:

- `params`: điều kiện về query parameter.
- `headers`: điều kiện về request header.
- `consumes`: media type được chấp nhận trong request body.
- `produces`: media type mà handler có thể tạo cho response.
- Các điều kiện routing khác do Spring hỗ trợ.

Do đó, hai phương thức có thể cùng ánh xạ `POST /api/imports` nhưng nhận payload khác nhau:

```java
@RestController
@RequestMapping("/api/imports")
class ImportController {

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ImportResult importJson(@RequestBody ImportJsonRequest request) {
        return importService.importJson(request);
    }

    @PostMapping(consumes = "text/csv")
    ImportResult importCsv(@RequestBody String csv) {
        return importService.importCsv(csv);
    }
}
```

Hai handler có cùng path và method, nhưng điều kiện `consumes` khác nhau. Spring dùng `Content-Type` của request để chọn handler phù hợp:

| Request | Handler được chọn |
|---|---|
| `POST /api/imports` với `Content-Type: application/json` | `importJson` |
| `POST /api/imports` với `Content-Type: text/csv` | `importCsv` |

Khi mapping được phân biệt rõ, Spring có thể đăng ký cả hai handler. Nếu hai mapping giống nhau về tất cả điều kiện, ứng dụng có thể gặp lỗi mapping trùng khi khởi động. Nếu điều kiện giao nhau và một request khớp nhiều handler với mức ưu tiên tương đương, Spring có thể không xác định được handler duy nhất.

## 2. consumes phân biệt định dạng request body

`consumes` khai báo media type mà handler chấp nhận. Spring so sánh điều kiện này với header `Content-Type` của request. Đây là cách thường dùng để tách handler nhận JSON, XML, CSV hoặc multipart trên cùng một URL.

Ví dụ hai dạng dữ liệu cùng được gửi tới một endpoint:

```http
POST /api/imports HTTP/1.1
Content-Type: application/json
Accept: application/json

{"source":"warehouse-a","items":[{"sku":"P-01","quantity":4}]}
```

```http
POST /api/imports HTTP/1.1
Content-Type: text/csv
Accept: application/json

sku,quantity
P-01,4
P-02,2
```

Ví dụ mapping tương ứng:

```java
@PostMapping(
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
ImportResult importJson(@Valid @RequestBody ImportJsonRequest request) {
    return importService.importJson(request);
}

@PostMapping(
    consumes = "text/csv",
    produces = MediaType.APPLICATION_JSON_VALUE
)
ImportResult importCsv(@RequestBody String csv) {
    return importService.importCsv(csv);
}
```

Ở đây cả hai handler đều trả `ImportResult` dưới dạng JSON, nhưng request body có schema khác nhau. `ImportJsonRequest` là object JSON; CSV là văn bản có cấu trúc theo quy ước cột. Với CSV, ứng dụng cần parser phù hợp để kiểm tra tiêu đề, kiểu dữ liệu và từng dòng. `consumes` chỉ chọn handler theo media type; nó không tự phân tích hoặc xác thực nội dung CSV.

Nếu client gửi `Content-Type` không khớp với bất kỳ mapping nào, Spring thường trả `415 Unsupported Media Type`. Lỗi này khác với lỗi JSON sai cú pháp: JSON có media type được chấp nhận nhưng body không deserialize được thường dẫn đến lỗi đọc request, thường là `400 Bad Request`.

### Một handler nhận nhiều media type

Nếu các định dạng có thể được xử lý trong cùng một luồng và cùng mô hình tham số Java, có thể khai báo nhiều media type trong một mapping:

```java
@PostMapping(
    path = "/api/imports",
    consumes = {
        MediaType.APPLICATION_JSON_VALUE,
        "text/csv"
    },
    produces = MediaType.APPLICATION_JSON_VALUE
)
ImportResult importData(@RequestBody String payload) {
    // Xác định định dạng theo Content-Type và phân tích payload phù hợp.
    return importService.importPayload(payload);
}
```

Để ví dụ này hoạt động, ứng dụng phải có converter đọc kiểu `String` cho các media type đó và phần xử lý phải biết cách diễn giải từng định dạng. Với DTO JSON và chuỗi CSV có cấu trúc khác nhau, hai handler riêng thường rõ ràng hơn. Không nên thêm media type vào `consumes` nếu converter hoặc logic xử lý chưa hỗ trợ nó.

## 3. produces phân biệt representation của response

`produces` khai báo media type mà handler có thể tạo. Spring xét header `Accept` của request cùng điều kiện mapping để chọn handler phù hợp. Điều này cho phép cùng một tài nguyên được trả dưới dạng JSON hoặc CSV.

Ví dụ:

```java
@RestController
@RequestMapping("/api/products")
class ProductExportController {

    @GetMapping(value = "/export", produces = MediaType.APPLICATION_JSON_VALUE)
    List<ProductResponse> exportJson() {
        return productService.findAll();
    }

    @GetMapping(value = "/export", produces = "text/csv")
    ResponseEntity<String> exportCsv() {
        String csv = productExportService.toCsv(productService.findAll());
        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType("text/csv"))
            .body(csv);
    }
}
```

Client có thể yêu cầu từng representation:

```http
GET /api/products/export HTTP/1.1
Accept: application/json
```

```http
GET /api/products/export HTTP/1.1
Accept: text/csv
```

Spring chọn handler tương ứng theo `produces`. Sau khi handler được chọn, một `HttpMessageConverter` phù hợp vẫn phải có khả năng ghi giá trị trả về thành media type đó. Việc ghi `produces = "text/csv"` không tự cài parser hoặc writer CSV. Có thể dùng thư viện CSV, custom converter hoặc tự tạo chuỗi CSV rồi trả về với `Content-Type` chính xác.

Nếu client yêu cầu `Accept: application/xml` trong khi endpoint chỉ hỗ trợ JSON và CSV, server thường trả `406 Not Acceptable`. Trường hợp client gửi `Accept: */*` hoặc không gửi `Accept` cần được kiểm thử riêng: nhiều representation có thể cùng phù hợp, và lựa chọn cuối cùng phụ thuộc độ cụ thể của mapping cùng cấu hình content negotiation. Không nên dựa vào thứ tự khai báo phương thức Java để chọn định dạng mặc định.

## 4. Có thể kết hợp consumes và produces

Một mapping có thể đồng thời ràng buộc định dạng request và response. Khi nhiều handler dùng chung path/method, chúng có thể được phân biệt bằng một trong hai điều kiện hoặc cả hai:

```java
@PostMapping(
    path = "/api/conversions",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
ConversionResult convertJson(@RequestBody JsonConversionRequest request) {
    return conversionService.convertJson(request);
}

@PostMapping(
    path = "/api/conversions",
    consumes = "text/csv",
    produces = "text/csv"
)
ResponseEntity<String> convertCsv(@RequestBody String csv) {
    String converted = conversionService.convertCsv(csv);
    return ResponseEntity.ok()
        .contentType(MediaType.parseMediaType("text/csv"))
        .body(converted);
}
```

Các điều kiện tương ứng:

| Handler | `Content-Type` được nhận | `Accept`/response được công bố |
|---|---|---|
| `convertJson` | `application/json` | `application/json` |
| `convertCsv` | `text/csv` | `text/csv` |

Spring có thể chọn handler theo cả hai phía. Tuy nhiên, cần lưu ý rằng `consumes` xét định dạng request body còn `produces` xét định dạng response. Chúng không thay thế cho nhau: một request gửi JSON có thể yêu cầu response CSV nếu endpoint và handler được thiết kế để hỗ trợ tổ hợp đó.

## 5. Điều kiện mapping phải không mơ hồ

Nhiều handler cùng path/method chỉ an toàn khi điều kiện chọn handler đủ rõ. Những trường hợp sau cần được xem xét:

| Cấu hình | Rủi ro | Cách xử lý |
|---|---|---|
| Hai handler cùng path/method và cùng `consumes`/`produces` | Mapping trùng hoặc không phân biệt được handler | Hợp nhất logic hoặc thêm điều kiện phân biệt có ý nghĩa |
| Một handler nhận `application/json`, handler khác nhận `application/*` | Điều kiện có thể giao nhau với request JSON | Tránh wildcard rộng hoặc thiết kế điều kiện cụ thể hơn |
| Hai handler có `produces` khác nhau nhưng client gửi `Accept: */*` | Cả hai representation có thể phù hợp | Quy định representation mặc định rõ ràng và kiểm thử wildcard |
| `consumes` có nhiều media type nhưng chỉ có một converter | Request có thể chọn được mapping nhưng body không đọc được | Cấu hình converter hoặc giới hạn media type được công bố |
| `produces` có media type nhưng không có converter ghi response | Handler được chọn nhưng response không serialize được | Bổ sung converter hoặc dùng kiểu trả về phù hợp |
| Mapping khác nhau theo header tùy chỉnh nhưng tài liệu không mô tả header | Client không biết điều kiện chọn handler | Khai báo parameter header và giải thích điều kiện |

Điều kiện media type có thể dùng wildcard hoặc suffix, ví dụ `application/*` hay `application/*+json`. Những điều kiện rộng giúp hỗ trợ nhiều định dạng nhưng làm tăng khả năng giao nhau. Chỉ dùng wildcard khi handler thực sự xử lý được toàn bộ nhóm media type tương ứng.

Khi Spring không tìm được mapping phù hợp do `Content-Type`, kết quả thường là `415`. Khi không có representation phù hợp với `Accept`, kết quả thường là `406`. Nếu nhiều mapping cùng phù hợp và không có mapping nào cụ thể hơn, có thể xảy ra lỗi ambiguous handler. Hãy kiểm tra log và thử request với các tổ hợp header thực tế.

## 6. Giới hạn mô hình Path Item của OpenAPI

OpenAPI mô tả tài nguyên trong `paths`. Mỗi path có một Path Item Object, và mỗi Path Item chỉ có một operation cho mỗi HTTP method như `get`, `post`, `put` hoặc `delete`.

Vì vậy, tài liệu không thể khai báo hai khóa `post` độc lập cho cùng `/api/imports` chỉ vì Spring có hai phương thức Java. Thay vào đó, các định dạng request được mô tả chung trong `requestBody.content`, còn các định dạng response được mô tả trong `responses.<status>.content`.

Ví dụ một operation nhận JSON hoặc CSV và trả JSON:

```yaml
paths:
  /api/imports:
    post:
      summary: Nhập dữ liệu sản phẩm
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ImportJsonRequest'
          text/csv:
            schema:
              type: string
              description: Nội dung CSV gồm các cột sku và quantity
      responses:
        '200':
          description: Kết quả nhập dữ liệu
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ImportResult'
        '415':
          description: Media type request không được hỗ trợ
```

Ví dụ này thể hiện đúng ý nghĩa của hai handler khác `consumes`: chúng là hai cách gửi request body cho cùng một operation. Mỗi media type có thể dùng schema riêng.

Với hai handler khác `produces`, response có thể liệt kê nhiều representation:

```yaml
paths:
  /api/products/export:
    get:
      summary: Xuất danh sách sản phẩm
      responses:
        '200':
          description: Danh sách sản phẩm ở định dạng được yêu cầu
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Product'
            text/csv:
              schema:
                type: string
                description: Nội dung CSV
        '406':
          description: Không có representation phù hợp với Accept
```

Trong ví dụ này, `Accept` cho biết client muốn JSON hay CSV; `Content-Type` trong response cho biết server đã trả định dạng nào.

## 7. OpenAPI không thể hiện mọi quan hệ giữa request và response

`requestBody.content` và `responses.content` mô tả các tập media type độc lập. Chúng không biểu diễn trực tiếp quy tắc kiểu: “nếu request là JSON thì bắt buộc response là JSON, còn nếu request là CSV thì bắt buộc response là CSV”.

Ví dụ, hai handler sau tạo ra hai cặp định dạng:

| Request | Response |
|---|---|
| `application/json` | `application/json` |
| `text/csv` | `text/csv` |

Nếu OpenAPI liệt kê cả JSON và CSV ở `requestBody.content`, đồng thời cả JSON và CSV ở response `content`, người đọc có thể hiểu rằng operation hỗ trợ các tổ hợp khác. OpenAPI chuẩn không có cấu trúc tổng quát để ràng buộc từng media type request với đúng một media type response.

Khi mối quan hệ này quan trọng với client, có thể chọn một trong các cách sau:

1. **Dùng URL riêng cho từng biểu diễn nghiệp vụ.** Ví dụ `/api/imports/json` và `/api/imports/csv`, nếu đây thực sự là hai contract khác nhau cần client lựa chọn rõ.
2. **Dùng một operation với response thống nhất.** Chẳng hạn cả JSON và CSV request đều trả `ImportResult` dạng JSON.
3. **Mô tả rõ quy tắc trong description hoặc example.** Cách này phù hợp khi vẫn muốn giữ cùng URL nhưng cần giải thích tổ hợp được hỗ trợ.
4. **Dùng extension riêng của tổ chức.** Chỉ dùng khi các công cụ nội bộ hiểu extension đó; client OpenAPI thông thường có thể bỏ qua nó.

Nếu hai handler chỉ khác cách serialize cùng một tài nguyên, một operation với nhiều media type thường là hợp đồng tự nhiên. Nếu chúng có semantics, quyền truy cập, status hoặc quy trình nghiệp vụ khác nhau, hãy cân nhắc thiết kế endpoint riêng để hợp đồng không gây hiểu nhầm.

## 8. Springdoc tạo operation cho các mapping trùng path/method như thế nào?

Springdoc đọc các mapping Spring để tạo OpenAPI, nhưng cấu trúc OpenAPI vẫn chỉ có một operation cho mỗi cặp path/method. Vì vậy, không nên giả định mỗi phương thức controller sẽ trở thành một operation độc lập nếu chúng cùng `POST /api/imports` hoặc cùng `GET /api/products/export`.

Khi có nhiều handler, kết quả tài liệu cần được kiểm tra trên đúng phiên bản springdoc của dự án. Tùy cách thư viện thu thập mapping và metadata, media type có thể được tổng hợp hoặc tài liệu có thể thiếu một phần schema, response hay mô tả của handler còn lại. Các annotation `@Operation` trùng nhau nhưng có nội dung khác nhau cũng có thể tạo ra metadata khó dự đoán.

Quy trình nên làm:

1. Khởi động ứng dụng với đầy đủ handler.
2. Tải `/v3/api-docs` và tìm đúng path cùng HTTP method.
3. Kiểm tra tất cả media type cần thiết có xuất hiện trong `requestBody.content` và response `content` không.
4. Kiểm tra schema của từng media type, status code, description và security requirement.
5. Nếu thông tin chưa đầy đủ, bổ sung metadata OpenAPI tập trung hoặc dùng `OpenApiCustomizer` để chuẩn hóa operation cuối cùng.

Không nên dùng annotation trên từng handler như thể OpenAPI cho phép nhiều operation cùng method. Hãy xem các handler là các nhánh xử lý runtime của một operation và bảo đảm operation được công bố mô tả đầy đủ tất cả nhánh đó.

## 9. Mô tả nhiều media type bằng annotation OpenAPI

Nếu một operation có thể được mô tả trực tiếp trên một handler hoặc một phương thức đại diện, annotation Swagger cho phép liệt kê nhiều media type trong request body:

```java
@Operation(
    summary = "Nhập dữ liệu sản phẩm",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = {
            @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = ImportJsonRequest.class)
            ),
            @Content(
                mediaType = "text/csv",
                schema = @Schema(type = "string",
                    description = "Nội dung CSV gồm sku và quantity")
            )
        }
    )
)
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Nhập dữ liệu thành công",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ImportResult.class)
        )
    ),
    @ApiResponse(responseCode = "415", description = "Media type không được hỗ trợ")
})
```

Với response hỗ trợ nhiều định dạng, khai báo nhiều `@Content` trong cùng response:

```java
@ApiResponse(
    responseCode = "200",
    description = "Dữ liệu xuất",
    content = {
        @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ProductListResponse.class)
        ),
        @Content(
            mediaType = "text/csv",
            schema = @Schema(type = "string", description = "Nội dung CSV")
        )
    }
)
```

Annotation OpenAPI chỉ mô tả tài liệu. Các handler Spring vẫn phải có `consumes` và `produces` phù hợp, converter phải đọc/ghi được nội dung, và controller phải thực sự trả representation đã công bố. Nếu metadata được đặt trên một handler đại diện, hãy xác nhận springdoc giữ được metadata đó trong operation cuối cùng.

## 10. Chuẩn hóa operation bằng OpenApiCustomizer

Khi phải giữ nhiều handler Java riêng nhưng springdoc chưa tổng hợp đầy đủ nội dung của chúng, có thể dùng `OpenApiCustomizer` để chỉnh operation cuối cùng. Cách này phù hợp khi cần bảo đảm `requestBody.content` hoặc response `content` có đủ media type và schema.

Ví dụ dưới đây bổ sung hai định dạng request cho operation `POST /api/imports`:

```java
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.PathItem;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.media.Schema;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.parameters.RequestBody;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ImportOpenApiConfiguration {

    @Bean
    OpenApiCustomizer importRequestContent() {
        return openApi -> {
            PathItem pathItem = openApi.getPaths().get("/api/imports");
            if (pathItem == null || pathItem.getPost() == null) {
                return;
            }

            Operation operation = pathItem.getPost();
            RequestBody requestBody = operation.getRequestBody();
            if (requestBody == null) {
                requestBody = new RequestBody().required(true);
            }

            Content content = requestBody.getContent();
            if (content == null) {
                content = new Content();
            }

            content.addMediaType(
                "application/json",
                new MediaType().schema(
                    new Schema<>().$ref("#/components/schemas/ImportJsonRequest")
                )
            );
            content.addMediaType("text/csv", new MediaType().schema(new StringSchema()));

            requestBody.setContent(content);
            operation.setRequestBody(requestBody);
        };
    }
}
```

Đoạn mã dùng model của Swagger Core để sửa tài liệu sau khi springdoc đã tạo operation. Nếu ứng dụng dùng nhiều `GroupedOpenApi`, hãy gắn customizer vào đúng nhóm tài liệu hoặc cấu hình để tránh sửa nhầm tài liệu khác. Tên path trong customizer phải khớp path đã xuất hiện trong OpenAPI, bao gồm context mapping mà springdoc đưa vào tài liệu.

Có thể bổ sung response `content` theo cùng nguyên tắc bằng cách lấy response từ `operation.getResponses()`, tạo hoặc lấy `Content`, thêm media type và schema, rồi gán lại. Khi sửa, cần giữ các status, description, header và schema đã có. Customizer chỉ thay đổi hợp đồng được công bố; nó không thay đổi request mapping hoặc hành vi của controller.

## 11. Kiểm thử các nhánh mapping bằng MockMvc

Với handler khác `consumes`, cần gửi từng `Content-Type` để xác nhận Spring chọn đúng phương thức và trả đúng kết quả:

```java
@WebMvcTest(ImportController.class)
class ImportControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void acceptsJsonImport() throws Exception {
        mockMvc.perform(post("/api/imports")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"source":"warehouse-a","items":[]}
                    """))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON));
    }

    @Test
    void acceptsCsvImport() throws Exception {
        mockMvc.perform(post("/api/imports")
                .contentType("text/csv")
                .accept(MediaType.APPLICATION_JSON)
                .content("sku,quantity\nP-01,4"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON));
    }

    @Test
    void rejectsUnsupportedContentType() throws Exception {
        mockMvc.perform(post("/api/imports")
                .contentType(MediaType.TEXT_PLAIN)
                .content("unsupported"))
            .andExpect(status().isUnsupportedMediaType());
    }
}
```

Với handler khác `produces`, kiểm tra cả `Accept` và response `Content-Type`:

```java
@Test
void exportsJsonWhenJsonIsAccepted() throws Exception {
    mockMvc.perform(get("/api/products/export")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON));
}

@Test
void exportsCsvWhenCsvIsAccepted() throws Exception {
    mockMvc.perform(get("/api/products/export")
            .accept("text/csv"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.parseMediaType("text/csv")));
}
```

Các ví dụ là mẫu kiểm thử; cần cấu hình mock/service, DTO và status code khớp controller thực tế. Bổ sung test cho `Accept: */*`, không gửi `Accept`, các media type có tham số charset, wildcard, và trường hợp không có representation phù hợp. Những trường hợp này giúp phát hiện điều kiện mapping giao nhau hoặc lựa chọn mặc định không rõ ràng.

## 12. Kiểm tra tài liệu OpenAPI và Swagger UI

Sau khi chạy ứng dụng, tải `/v3/api-docs` hoặc `/v3/api-docs.yaml`. Với một path dùng chung method, kiểm tra các điểm sau:

1. Path chỉ có một operation cho HTTP method tương ứng.
2. `requestBody.content` liệt kê đủ media type mà các handler `consumes` nhận.
3. Mỗi media type của request trỏ tới schema đúng, chẳng hạn object JSON và chuỗi CSV.
4. `responses.<status>.content` liệt kê đủ representation mà các handler `produces` có thể trả.
5. Status code và schema lỗi như `406` hoặc `415` được mô tả nếu API công bố chúng.
6. Summary, description, operationId, tags và security requirement không bị mất hoặc mâu thuẫn giữa các handler.

Trong Swagger UI, chọn từng media type của request body và thử gọi endpoint. Với operation trả nhiều định dạng, chọn giá trị `Accept` tương ứng nếu giao diện hỗ trợ. Kiểm tra request trong tab Network và xác nhận response có `Content-Type` đúng. Swagger UI chỉ dựa trên OpenAPI; giao diện không chứng minh controller đã thực sự hỗ trợ media type.

Có thể kiểm tra tài liệu sinh ra bằng một bài test tích hợp riêng. Ví dụ với MockMvc có thể truy cập `/v3/api-docs` và kiểm tra JSONPath cho các key `content`:

```java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.paths['/api/imports'].post.requestBody.content['application/json']"
    ).exists())
    .andExpect(jsonPath(
        "$.paths['/api/imports'].post.requestBody.content['text/csv']"
    ).exists());
```

Test tài liệu nên chạy với cấu hình springdoc thực tế của ứng dụng, vì `@WebMvcTest` có thể không nạp đầy đủ cấu hình OpenAPI, bean customizer hoặc các controller khác.

## 13. Khi nào nên tách endpoint?

Dùng chung path và method có lợi khi các handler thực hiện cùng một thao tác nghiệp vụ và chỉ khác định dạng biểu diễn. Ví dụ, cùng một thao tác nhập dữ liệu chấp nhận JSON hoặc CSV, hoặc cùng một thao tác xuất danh sách hỗ trợ JSON và CSV.

Nên cân nhắc path riêng khi:

- Mỗi định dạng có quy tắc nghiệp vụ, quyền truy cập hoặc vòng đời khác nhau.
- Request và response có quan hệ phụ thuộc định dạng mà OpenAPI không thể mô tả rõ.
- Client thường xuyên gặp lỗi do `Accept` mặc định hoặc không thể chọn representation ổn định.
- Hai handler có status code, payload lỗi hoặc side effect khác nhau đáng kể.
- Cấu hình mapping ngày càng nhiều wildcard hoặc điều kiện chồng lấn.

Ví dụ `/api/imports/json` và `/api/imports/csv` làm cho lựa chọn định dạng hiện rõ trên URL. Đây là quyết định thiết kế API, không phải yêu cầu kỹ thuật bắt buộc. Nếu dùng cùng path, hãy giữ semantics thống nhất và mô tả các media type đầy đủ trong một operation.

## 14. Quy trình thiết kế và rà soát

Khi tạo nhiều handler dùng chung path và method, thực hiện lần lượt:

1. Xác định operation nghiệp vụ chung và các representation mà client cần gửi hoặc nhận.
2. Chọn điều kiện `consumes` cho request body và `produces` cho response.
3. Bảo đảm các mapping không trùng hoàn toàn và không giao nhau theo cách gây ambiguous handler.
4. Xác nhận `HttpMessageConverter` có thể đọc/ghi từng media type và kiểu Java tương ứng.
5. Kiểm tra lỗi `415`, `406`, request không có header và wildcard `Accept`.
6. Tải OpenAPI, hợp nhất các nhánh runtime thành một operation có đủ request/response `content`.
7. Bổ sung annotation hoặc `OpenApiCustomizer` nếu springdoc chưa công bố đủ schema và media type.
8. Kiểm thử cả hành vi HTTP và tài liệu JSON/YAML trước khi phát hành.

Spring MVC quyết định handler theo điều kiện request mapping; springdoc chuyển các handler đó thành hợp đồng OpenAPI. Thiết kế tốt cần bảo đảm hai mô hình này thống nhất: mỗi media type được công bố phải được xử lý thật ở runtime, và mỗi nhánh handler cần được thể hiện trong operation duy nhất mà client sử dụng.

## 15. Tài liệu tham khảo

- [Spring Framework: Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): điều kiện `consumes`, `produces`, `headers`, `params` và lựa chọn handler.
- [Spring Framework: HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): converter đọc request body và ghi response body.
- [Springdoc OpenAPI](https://springdoc.org/): cách tạo tài liệu OpenAPI từ Spring Boot và tùy chỉnh tài liệu.
- [OpenAPI Specification – Paths Object](https://spec.openapis.org/oas/latest.html#paths-object): cấu trúc path và các operation được phép.
- [OpenAPI Specification – Request Body Object](https://spec.openapis.org/oas/latest.html#request-body-object): mô tả request body theo media type.
- [OpenAPI Specification – Responses Object](https://spec.openapis.org/oas/latest.html#responses-object): mô tả response và content theo status code.
- [Swagger Core Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations): annotation để mô tả operation, request body và response.
