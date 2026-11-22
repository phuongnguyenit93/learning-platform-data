# So sánh payload HTTP thực với schema thay vì chỉ kiểm tra annotation

Một endpoint có thể có đầy đủ `@Operation`, `@ApiResponse`, `@Schema` và vẫn trả về payload không khớp hợp đồng OpenAPI. Annotation mô tả ý định của API; nó không chứng minh HTTP response thực tế có đúng status, header, content type, field bắt buộc, kiểu dữ liệu hay cấu trúc JSON.

Với Spring Boot và springdoc-openapi, cần kiểm tra hai sản phẩm riêng:

1. **Đặc tả được sinh**: tài liệu OpenAPI JSON/YAML mô tả operation và schema.
2. **Trao đổi HTTP thực tế**: request đi vào ứng dụng và response được serialize, xử lý bởi filter, exception handler và security rồi gửi ra ngoài.

Contract test đặt hai sản phẩm cạnh nhau: gửi request như client thật, nhận response từ Spring MVC/WebFlux, sau đó validate toàn bộ HTTP interaction với OpenAPI. Nhờ vậy, test có thể phát hiện trường hợp tài liệu nói `price` là number nhưng Jackson lại serialize thành string, response thiếu field bắt buộc, endpoint trả status chưa được mô tả hoặc request query parameter sai kiểu.

## 1. Vì sao chỉ kiểm tra annotation chưa đủ?

Ví dụ controller có khai báo:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @Operation(summary = "Lấy thông tin sản phẩm")
    @ApiResponse(
            responseCode = "200",
            description = "Tìm thấy sản phẩm",
            content = @Content(
                    schema = @Schema(implementation = ProductResponse.class)
            )
    )
    @GetMapping("/{id}")
    ProductResponse getProduct(@PathVariable UUID id) {
        return productService.get(id);
    }
}
~~~

Test kiểm tra annotation hoặc test gọi trực tiếp method controller chưa xác nhận response trên wire. Payload thực tế còn chịu ảnh hưởng bởi:

- Jackson `ObjectMapper`, naming strategy và module cho Java Time.
- `@JsonProperty`, `@JsonIgnore`, `@JsonInclude` và custom serializer.
- Bean Validation và cách Spring chuyển validation error thành HTTP response.
- `ResponseEntity`, status code, response headers và content negotiation.
- `@ControllerAdvice`, exception handler và error response DTO.
- Servlet filter, Spring Security, gateway hoặc interceptor.
- Cấu hình profile, feature flag và phiên bản DTO đang chạy.

Ví dụ schema mô tả `createdAt` là chuỗi `date-time`, nhưng serializer có thể xuất epoch number nếu ObjectMapper cấu hình khác. Annotation vẫn tồn tại, Swagger UI vẫn render, còn client parse payload sẽ lỗi.

### 1.1. Ba cấp độ kiểm tra

| Cấp độ | Kiểm tra | Phát hiện được |
|---|---|---|
| Unit test/controller test | Logic method, service call, một số nhánh xử lý | Sai nghiệp vụ trong method, nhưng chưa chắc phản ánh serialization HTTP. |
| HTTP contract test | Request/response thực qua MockMvc hoặc HTTP server được validate với OpenAPI | Sai path, method, parameter, content type, status, header và body schema. |
| End-to-end test qua proxy/gateway | Request thực đi qua network boundary và các thành phần triển khai | Sai rewrite path, authentication, header gateway, TLS và cấu hình deployment. |

Các cấp độ bổ sung cho nhau. Contract test ở tầng MVC nhanh hơn end-to-end, nhưng không thay thế kiểm thử qua gateway khi gateway có thể sửa request/response.

## 2. Contract test xác minh những gì?

Một validator hiểu OpenAPI có thể đối chiếu nhiều phần của một HTTP interaction:

| Thành phần | Ví dụ cần kiểm tra |
|---|---|
| HTTP method và path | `GET /api/products/{id}` phải khớp operation được khai báo. |
| Path parameter | `id` phải có mặt và đúng định dạng UUID. |
| Query parameter | `page` là integer, `size` nằm trong giới hạn đã mô tả. |
| Header và cookie | Header bắt buộc, kiểu và giá trị theo schema. |
| Request body | JSON có field bắt buộc, enum và kiểu dữ liệu đúng. |
| Content-Type | Request/response dùng media type được khai báo. |
| Status code | Response `200`, `201`, `400`, `404` hoặc `default` phải được mô tả. |
| Response headers | Ví dụ `Location`, `ETag`, `Cache-Control`. |
| Response body | Field, kiểu, format, required, enum, array và object constraints. |
| Security requirement | Sự hiện diện của API key hoặc bearer/basic credential theo khả năng validator. |

Đây là điểm khác biệt so với test chỉ gọi `jsonPath("$.id").exists()`: test theo JSONPath xác minh một vài field được chọn; contract validator kiểm tra interaction theo operation và schema được công bố.

## 3. Dùng OpenAPI artifact làm chuẩn đối chiếu

Springdoc thường xuất tài liệu ở:

- JSON: `/v3/api-docs`
- YAML: `/v3/api-docs.yaml`

Có thể tải tài liệu để kiểm tra hoặc lưu thành artifact:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs.yaml \
  -o build/openapi/catalog.yaml
~~~

Trong test, nên chọn nguồn contract có chủ đích:

| Nguồn đặc tả | Khi phù hợp | Điểm cần lưu ý |
|---|---|---|
| OpenAPI file được review và lưu trong test resources | Muốn kiểm tra implementation hiện tại vẫn tuân theo hợp đồng đã duyệt. | Cần cập nhật file qua review khi contract thay đổi. |
| OpenAPI artifact được sinh từ springdoc trong build | Muốn kiểm tra payload HTTP có khớp tài liệu mà chính build hiện tại phát ra. | Nên so sánh artifact mới với baseline đã phát hành để phát hiện thay đổi ngoài ý muốn. |
| Endpoint `/v3/api-docs` của ứng dụng đang chạy | Kiểm thử toàn bộ luồng tạo tài liệu và HTTP runtime trong một test deployment. | Nếu tài liệu được tạo từ cùng source code, test này không tự phát hiện việc annotation đã thay đổi ngoài ý muốn so với hợp đồng cũ. |

Không nên chỉ lấy OpenAPI mới nhất từ chính ứng dụng rồi coi đó là bằng chứng duy nhất về tính tương thích. Cách đó xác nhận payload khớp schema hiện tại, nhưng không cho biết schema có vừa thay đổi theo cách phá vỡ client cũ hay không. Hãy giữ artifact baseline hoặc chạy contract diff giữa release hiện tại và release trước.

Ví dụ contract rút gọn cho endpoint lấy sản phẩm:

~~~yaml
openapi: 3.0.4
info:
  title: Catalog API
  version: 1.4.0
paths:
  /api/products/{id}:
    get:
      operationId: getProduct
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        "200":
          description: Tìm thấy sản phẩm
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ProductResponse"
        "404":
          description: Không tìm thấy sản phẩm
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"
components:
  schemas:
    ProductResponse:
      type: object
      additionalProperties: false
      required:
        - id
        - name
        - price
      properties:
        id:
          type: string
          format: uuid
        name:
          type: string
          minLength: 1
        price:
          type: number
          minimum: 0
        createdAt:
          type: string
          format: date-time
    ApiProblem:
      type: object
      required:
        - title
        - status
      properties:
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
~~~

Trong schema trên:

- `id`, `name` và `price` phải có mặt trong response thành công.
- `price` phải là JSON number và không âm.
- `createdAt`, nếu xuất hiện, phải là chuỗi date-time.
- `additionalProperties: false` cấm các field không được khai báo trong response object.
- Response `404` có schema lỗi riêng, không được trả tùy tiện một object khác.

## 4. Chọn validator theo Spring Boot và ranh giới test

Một lựa chọn Java là OpenAPI Request Validator do Atlassian duy trì. Thư viện có core validator và adapter cho REST Assured, Spring MockMvc, WireMock, Pact cùng một số client/framework khác.

| Adapter | Cách dùng | Ranh giới |
|---|---|---|
| `openapi-request-validator-mockmvc` | Thêm `ResultMatcher` vào MockMvc interaction. | Kiểm tra request/response trong Spring MVC test mà không cần mở cổng HTTP. |
| `openapi-request-validator-restassured` | Thêm `OpenApiValidationFilter` vào REST Assured. | Kiểm tra request/response qua HTTP server đang chạy. |
| `openapi-request-validator-wiremock-junit5` | Validate các interaction được WireMock trả về. | Đảm bảo mock/stub mà consumer dùng khớp contract. |
| `openapi-request-validator-pact` | Kết hợp validation với Pact consumer test. | Bổ sung kiểm tra OpenAPI cho expectation của consumer. |

### 4.1. Chú ý phiên bản thư viện

Các artifact và adapter đã đổi tên ở major version 3:

| Nền tảng | Nhánh validator | Artifact MockMvc |
|---|---|---|
| Spring Boot 3 / Spring Framework 6 | Nhánh 2.x của validator | `swagger-request-validator-mockmvc` |
| Spring Boot 4 / Spring Framework 7 | Nhánh 3.x của validator | `openapi-request-validator-mockmvc` |

Nhánh 3.x dùng Java 21 trở lên cho core và các adapter; adapter Spring mới dựa trên Spring Framework 7 và namespace `jakarta.*`. Ứng dụng Boot 3 không thể chỉ đổi tên dependency sang artifact v3 để tiếp tục dùng Spring 6. Hãy chọn đúng major line và đọc release notes trước khi nâng cấp.

Ví dụ dependency Maven cho nhánh 3.x:

~~~xml
<dependency>
    <groupId>com.atlassian.oai</groupId>
    <artifactId>openapi-request-validator-mockmvc</artifactId>
    <version>${openapi-request-validator.version}</version>
    <scope>test</scope>
</dependency>
~~~

Khai báo property `openapi-request-validator.version` bằng một bản phát hành đã pin, tương thích với Java và Spring của dự án. Với Boot 3, dùng dependency/artifact của nhánh 2.x theo tài liệu migration; không sao chép tọa độ v3 vào dự án Spring 6.

## 5. Validate request và response bằng MockMvc

MockMvc chạy request qua Spring MVC `DispatcherServlet`, message converter, controller, validation, exception handler và các filter được đưa vào test context. Đây là ranh giới hữu ích để kiểm tra payload sau serialization mà không phải khởi động network server.

Giả sử file contract được lưu tại `src/test/resources/openapi/catalog.yaml`. Với adapter MockMvc của nhánh 3.x, có thể thêm `openApi().isValid(...)` vào chính interaction:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import java.util.UUID;

import static com.atlassian.oai.validator.mockmvc.OpenApiValidationMatchers.openApi;
import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProductContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void getProductResponseMatchesOpenApiContract() throws Exception {
        UUID productId = UUID.fromString(
                "d9a5c6e8-10b4-4a2a-8d15-4b3d9e7f2a11"
        );

        mockMvc.perform(get("/api/products/{id}", productId)
                        .accept(APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(APPLICATION_JSON))
                .andExpect(openApi().isValid("openapi/catalog.yaml"));
    }
}
~~~

Matcher kiểm tra cả request gửi vào và response nhận được theo operation trong đặc tả. Nếu path parameter sai format, response status không được mô tả, response header/content type không khớp hoặc body vi phạm schema, interaction sẽ thất bại.

### 5.1. Kiểm tra request body và response cùng lúc

Với endpoint tạo sản phẩm, test nên gửi payload qua HTTP request builder:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@Test
void createProductRequestAndResponseMatchContract() throws Exception {
    mockMvc.perform(post("/api/products")
                    .contentType(APPLICATION_JSON)
                    .accept(APPLICATION_JSON)
                    .content("""
                            {
                              "name": "Mechanical Keyboard",
                              "price": 79.90
                            }
                            """))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(APPLICATION_JSON))
            .andExpect(openApi().isValid("openapi/catalog.yaml"));
}
~~~

Test này kiểm tra request body thực tế được gửi, response do Spring serialize và status code trả về. Nếu contract yêu cầu `price` là number nhưng ứng dụng trả `"79.90"` dạng string, validator sẽ phát hiện sai kiểu.

### 5.2. Kiểm tra response lỗi

Không chỉ test nhánh thành công. API cần mô tả và kiểm tra các response lỗi có ý nghĩa:

- `400 Bad Request`: payload hoặc parameter không hợp lệ.
- `401 Unauthorized`: chưa xác thực.
- `403 Forbidden`: đã xác thực nhưng không đủ quyền.
- `404 Not Found`: không có tài nguyên.
- `409 Conflict`: xung đột nghiệp vụ.
- `422 Unprocessable Content`: dữ liệu đúng cú pháp nhưng không thỏa điều kiện nghiệp vụ, nếu API dùng status này.

Ví dụ kiểm tra `404`:

~~~java
@Test
void missingProductReturnsDocumentedProblemResponse() throws Exception {
    UUID missingId = UUID.fromString(
            "00000000-0000-0000-0000-000000000099"
    );

    mockMvc.perform(get("/api/products/{id}", missingId)
                    .accept("application/problem+json"))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith("application/problem+json"))
            .andExpect(openApi().isValid("openapi/catalog.yaml"));
}
~~~

Nếu controller trả `404` nhưng OpenAPI chỉ mô tả `200`, contract test sẽ báo mismatch. Nếu error handler trả một object khác schema `ApiProblem`, test cũng thất bại.

### 5.3. Tách test request không hợp lệ khỏi test response contract

Một test cố ý gửi request vi phạm schema có hai mục tiêu khác nhau:

1. Xác nhận server từ chối request bằng status và error payload đúng.
2. Xác nhận response lỗi khớp schema được mô tả.

Một interaction validator mặc định kiểm tra cả request lẫn response, vì vậy request sai schema có thể làm test thất bại ngay cả khi response `400` hoàn toàn đúng. Với negative test, hãy cấu hình validator để chỉ xét response hoặc tách riêng assertion cho error payload theo khả năng của adapter. Giữ một positive contract test để chứng minh request hợp lệ được chấp nhận.

Không tắt request validation trên toàn bộ test suite chỉ để làm các negative test dễ pass; việc đó sẽ bỏ sót lỗi client request không đúng contract.

## 6. Validate HTTP server thật bằng REST Assured

MockMvc không mở cổng HTTP thật. Nếu muốn kiểm tra embedded Tomcat/Jetty/Undertow, servlet container, filter chain và network request, chạy ứng dụng với cổng ngẫu nhiên rồi dùng REST Assured.

Adapter `openapi-request-validator-restassured` cung cấp `OpenApiValidationFilter`. Ví dụ:

~~~java
import com.atlassian.oai.validator.restassured.OpenApiValidationFilter;
import io.restassured.filter.Filter;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static io.restassured.RestAssured.given;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ProductHttpContractTest {

    @LocalServerPort
    int port;

    @Test
    void realHttpResponseMatchesOpenApiContract() {
        String specificationUrl =
                "http://localhost:" + port + "/v3/api-docs";

        Filter validation = new OpenApiValidationFilter(specificationUrl);

        given()
                .port(port)
                .filter(validation)
                .accept("application/json")
        .when()
                .get("/api/products/{id}",
                        "d9a5c6e8-10b4-4a2a-8d15-4b3d9e7f2a11")
        .then()
                .statusCode(200);
    }
}
~~~

Ví dụ trên tải OpenAPI JSON từ chính ứng dụng đang chạy. Nó hữu ích để xác nhận tài liệu được publish và HTTP interaction khớp với tài liệu hiện tại. Trong pipeline kiểm tra tương thích với release trước, có thể cấu hình filter dùng artifact OpenAPI đã được review thay cho URL runtime; khi đó implementation mới phải tiếp tục đáp ứng hợp đồng baseline.

Nếu tài liệu OpenAPI được bảo vệ bởi Spring Security, cấu hình test authentication hoặc dùng artifact contract cục bộ. Không làm yếu security production chỉ để test có thể tải `/v3/api-docs`.

## 7. Không chỉ kiểm tra JSON body

Một contract test có giá trị phải kiểm tra cả phần HTTP envelope.

### 7.1. Status code và response headers

OpenAPI response có thể khai báo header:

~~~yaml
responses:
  "201":
    description: Đã tạo sản phẩm
    headers:
      Location:
        required: true
        schema:
          type: string
          format: uri-reference
    content:
      application/json:
        schema:
          $ref: "#/components/schemas/ProductResponse"
~~~

Khi server trả `201`, test cần xác minh `Location` thực sự có mặt và body đúng schema. Chỉ kiểm tra JSON body không phát hiện được response thiếu header cần thiết cho client.

### 7.2. Content negotiation

Nếu operation hỗ trợ `application/json` và `application/problem+json`, test cần gửi `Accept` phù hợp và kiểm tra `Content-Type` trả về. Một endpoint có thể trả body JSON hợp lệ nhưng media type sai, khiến client không chọn đúng decoder.

Với `204 No Content`, không được trả JSON body ngoài hợp đồng. Với `HEAD`, response không có body theo semantics của HTTP. Hãy mô tả các trường hợp này đúng trong OpenAPI và kiểm tra response thật.

### 7.3. Parameter serialization

Kiểm tra các dạng parameter mà client thực sự gửi:

- Path parameter có URL-encoding đúng.
- Query parameter số, boolean, enum và ngày giờ có format đúng.
- Array query parameter dùng đúng `style`/`explode`.
- Header parameter không bị mất do proxy hoặc filter.
- Cookie parameter có đúng tên và cách truyền.

Test một request với `?page=1&size=20` không chứng minh array parameter dạng `?tag=a&tag=b` hoặc `deepObject` đã được parse đúng. Mỗi cách serialization quan trọng cần có interaction test riêng.

## 8. Những sai lệch thường chỉ xuất hiện ở payload runtime

| Sai lệch | Nguyên nhân thường gặp | Contract test phát hiện |
|---|---|---|
| Thiếu field bắt buộc | `@JsonInclude(NON_NULL)`, mapper hoặc DTO mapping bỏ field | Required property không có trong response. |
| Sai tên field | `@JsonProperty`, naming strategy hoặc serializer | Schema có `productId`, payload lại có `product_id`. |
| Sai kiểu số | Decimal bị serialize thành string | Schema number nhưng payload string. |
| Sai ngày giờ | Epoch number, format hoặc timezone khác | Schema `date-time` nhưng payload không đúng format. |
| Field dư | DTO trả thêm internal field | Schema đóng bằng `additionalProperties: false` sẽ báo lỗi. |
| Enum mới | Code thêm enum value nhưng contract chưa cập nhật | Response có giá trị không nằm trong enum. |
| Sai status | Exception handler trả `200` hoặc `500` thay vì status đã công bố | Status code không được mô tả cho operation. |
| Sai media type | Converter trả `text/plain` hoặc media type khác | Content-Type không khớp `content`. |
| Sai error shape | `@ControllerAdvice` trả object khác error schema | Response lỗi vi phạm schema. |
| Thiếu header | Quên `Location`, `ETag` hoặc header pagination | Response header bắt buộc không có. |

### 8.1. `required`, nullable và field bị bỏ qua

Trong OpenAPI, một property không bắt buộc có thể bị bỏ qua; một property nullable có thể xuất hiện với giá trị `null`. Hai hành vi này khác nhau.

Ví dụ response:

~~~json
{
  "id": "d9a5c6e8-10b4-4a2a-8d15-4b3d9e7f2a11",
  "name": "Mechanical Keyboard",
  "price": 79.9
}
~~~

Nếu `createdAt` không nằm trong `required`, việc không có field này có thể hợp lệ. Nhưng nếu schema khai báo `createdAt` required và runtime dùng `@JsonInclude(NON_NULL)` để bỏ field, contract test phải thất bại.

### 8.2. Strict schema và `additionalProperties`

Khi schema dùng `additionalProperties: false`, payload có field chưa khai báo sẽ bị xem là không hợp lệ. Điều này hữu ích với response public cần kiểm soát chính xác, nhưng cần quyết định có chủ đích.

Nếu API chủ động hỗ trợ metadata mở rộng, dùng `additionalProperties` với schema phù hợp hoặc cho phép field mở rộng. Không bật `false` chỉ để test chặt hơn nếu server có hợp đồng extension hợp lệ.

## 9. Kiểm tra request và response của nhiều nhóm operation

Một bộ contract test nên bao phủ các dạng operation có rủi ro serialization khác nhau:

| Nhóm operation | Trường hợp cần có |
|---|---|
| GET collection | Danh sách rỗng, có dữ liệu, pagination, sort và filter. |
| GET item | Tồn tại, không tồn tại, ID sai format. |
| POST | Payload hợp lệ, field required thiếu, enum sai, body sai media type. |
| PUT/PATCH | Cập nhật đầy đủ và cập nhật một phần, nullability. |
| DELETE | Thành công, không tồn tại, response 204 không body. |
| Upload | Multipart, file metadata, giới hạn kích thước và media type. |
| Download | Content-Type, Content-Disposition, binary body. |
| Error handler | 400, 401, 403, 404, 409 và lỗi hệ thống đã công bố. |
| Security | Request có/không có credential và response status tương ứng. |

Không cần tạo hàng trăm test lặp lại cùng một schema. Chọn các trường hợp đại diện cho mỗi operation, mỗi response code quan trọng và các nhánh serialization đặc biệt.

## 10. Giới hạn của validator và OpenAPI version

Không phải validator nào cũng hỗ trợ mọi feature của OpenAPI ở cùng mức độ. Với OpenAPI Request Validator của Atlassian, tài liệu feature hiện tại nêu:

- OpenAPI 3.0: hỗ trợ request/response validation đầy đủ theo feature matrix.
- OpenAPI 3.1: hỗ trợ một phần; một số keyword JSON Schema 2020-12 chưa được thực thi đầy đủ.
- JSON Schema draft-07: hỗ trợ nhiều keyword và composition như `$ref`, `allOf`, `oneOf`, `anyOf`, discriminator.

Ví dụ trong feature matrix hiện tại, `contentMediaType` và `contentEncoding` có thể được parse nhưng giá trị không được enforce; `examples` dạng plural được parse nhưng không validate; `unevaluatedItems` chỉ hỗ trợ một phần. Kiểm tra feature matrix trước khi dựa vào các keyword này trong test bắt buộc.

### 10.1. Security validation không thay thế security test

Validator có thể kiểm tra sự hiện diện của một số security credential theo scheme được hỗ trợ. Tuy nhiên, điều đó không chứng minh:

- Token có chữ ký hợp lệ.
- Token chưa hết hạn.
- OAuth2 scope được authorize đúng.
- User có quyền truy cập tài nguyên.
- Tenant isolation được thực thi.

Hãy dùng Spring Security integration test hoặc end-to-end security test để kiểm tra xác thực và phân quyền. OpenAPI contract test xác minh request/response khớp tài liệu; nó không thay thế authorization test.

### 10.2. REST Assured JSON Schema module không giống OpenAPI validator

REST Assured có module `json-schema-validator` để xác minh response JSON với JSON Schema. Nó hữu ích khi chỉ cần kiểm tra body schema.

Tuy nhiên, JSON Schema validator riêng không tự xác minh:

- HTTP method và path khớp operation.
- Status code có được mô tả.
- Response headers và media type.
- Path/query/header/cookie parameters.
- OpenAPI security requirements.

Nếu mục tiêu là xác minh toàn bộ HTTP interaction theo OpenAPI, dùng adapter OpenAPI validator. Dùng JSON Schema validator khi chỉ cần assertion ở cấp body hoặc khi schema được quản lý độc lập.

## 11. Phân biệt OpenAPI conformance với consumer-driven contract

Hai loại kiểm thử thường bị gọi chung là contract testing:

| Loại | Câu hỏi chính | Công cụ thường dùng |
|---|---|---|
| OpenAPI conformance test | HTTP request/response thực có khớp đặc tả OpenAPI không? | OpenAPI Request Validator, REST Assured, MockMvc. |
| Consumer-driven contract test | Provider có đáp ứng những expectation mà consumer thực sự cần không? | Pact hoặc Spring Cloud Contract. |

OpenAPI là contract mô tả API ở mức công khai và thường do provider phát hành. Pact/Spring Cloud Contract giúp xác minh expectation giữa các service, quản lý stub và phát hiện thay đổi làm consumer bị ảnh hưởng.

Có thể kết hợp: OpenAPI validator kiểm tra mọi interaction theo API specification; Pact/Spring Cloud Contract kiểm tra những tương tác mà consumer cụ thể phụ thuộc. Không dùng một loại để thay thế hoàn toàn loại còn lại.

## 12. Tích hợp contract test vào CI

Một pipeline cơ bản:

~~~mermaid
flowchart TD
    A[Build Spring Boot application] --> B[Generate or load reviewed OpenAPI artifact]
    B --> C[Validate OpenAPI document]
    C --> D[Run MockMvc / REST Assured tests]
    D --> E[Validate real requests and responses]
    E --> F[Compare contract with released baseline]
    F --> G[Publish artifact and test report]
~~~

Các bước nên thực hiện:

1. Build ứng dụng và tạo test context theo profile xác định.
2. Tạo hoặc lấy OpenAPI JSON/YAML đã được review.
3. Validate cấu trúc OpenAPI và resolve `$ref`.
4. Chạy MockMvc contract tests cho các operation quan trọng.
5. Chạy REST Assured qua cổng HTTP thật cho các luồng cần container/filter/network.
6. Kiểm tra response thành công và error response.
7. So sánh OpenAPI artifact với baseline để phát hiện breaking change.
8. Lưu artifact, validator version và test report cùng build.

Không chỉ chạy test khi controller được sửa. Thay đổi ObjectMapper, DTO, `@ControllerAdvice`, security filter, dependency Spring hoặc cấu hình serialization cũng có thể làm payload thay đổi.

### 12.1. Làm test ổn định

- Dùng fixture dữ liệu xác định; tránh phụ thuộc thời gian hiện tại hoặc dữ liệu bên ngoài.
- Kiểm tra schema thay vì so sánh nguyên chuỗi JSON nếu thứ tự field không có ý nghĩa.
- Chỉ dùng `additionalProperties: false` khi API thực sự cam kết không có field mở rộng.
- Chuẩn hóa format thời gian và timezone trong test data.
- Không lấy tài liệu từ môi trường production có auth hoặc dữ liệu biến động.
- Pin validator version và OpenAPI artifact.
- Không bỏ qua mọi lỗi validator bằng whitelist rộng; mỗi ngoại lệ phải có lý do và phạm vi cụ thể.
- Lưu validation report để biết path, method, status và vị trí schema bị vi phạm.

## 13. Những lỗi thường gặp

- **Chỉ kiểm tra `@Schema` hoặc `@ApiResponse`**: annotation không chứng minh payload runtime khớp schema.
- **Chỉ kiểm tra một field bằng JSONPath**: có thể bỏ sót field dư, sai kiểu, sai header hoặc sai status.
- **Dùng tài liệu vừa sinh làm baseline duy nhất**: không phát hiện thay đổi contract ngoài ý muốn so với release cũ.
- **Không kiểm tra error response**: `@ControllerAdvice` có thể trả body khác schema.
- **Không kiểm tra Content-Type**: body JSON hợp lệ vẫn có thể được gửi với media type sai.
- **Không kiểm tra request body**: server có thể chấp nhận hoặc xử lý request trái schema.
- **Dùng matcher toàn interaction cho request cố ý sai schema**: validator sẽ báo request không hợp lệ; cần tách negative test hoặc chỉ validate response.
- **Dùng validator 3.x với Spring Boot 3**: nhánh 3.x yêu cầu Spring 7/Boot 4 cho adapter MockMvc; Boot 3 cần nhánh 2.x tương ứng.
- **Giả định OpenAPI 3.1 được hỗ trợ đầy đủ**: feature matrix của validator có thể chỉ hỗ trợ một phần.
- **Xem security scheme validation là kiểm thử authorization**: cần test token, scope và quyền truy cập riêng.
- **Chỉ test MockMvc nhưng bỏ qua gateway**: MockMvc không mô phỏng proxy, TLS, rewrite path hoặc network policy.
- **Tắt validator khi gặp mismatch**: xác định mismatch nằm ở code, schema hay test setup rồi sửa đúng nguồn.
- **Dùng whitelist quá rộng**: có thể che lỗi contract mới xuất hiện.

## 14. Quy trình review contract test

1. **Chọn contract baseline**: xác định test dùng file đã duyệt, artifact build hay tài liệu runtime.
2. **Xác minh OpenAPI**: document parse được, operation và `$ref` đầy đủ.
3. **Chọn test boundary**: MockMvc cho MVC interaction nhanh; REST Assured cho HTTP server thật.
4. **Gửi request thật**: dùng path, parameter, header, media type và body như client.
5. **Validate response thật**: status, headers, content type và body schema.
6. **Kiểm tra success/error**: có test cho các response code được công bố.
7. **Rà soát schema edge cases**: required, nullability, enum, format và additional properties.
8. **Kiểm tra compatibility**: validator version hỗ trợ OpenAPI dialect và framework của ứng dụng.
9. **Chạy CI**: lưu report và so sánh contract với baseline.
10. **Review mismatch**: sửa implementation hoặc contract dựa trên hành vi API đã được thống nhất.

## 15. Checklist review

- [ ] Test gửi HTTP request qua MockMvc hoặc HTTP server thật.
- [ ] Test validate request parameters và body.
- [ ] Test validate status code và response headers.
- [ ] Test validate Content-Type và response body schema.
- [ ] Có kiểm tra success response và error response.
- [ ] DTO serialization và `@ControllerAdvice` nằm trong đường chạy test.
- [ ] OpenAPI artifact là baseline đã duyệt hoặc được so sánh với baseline.
- [ ] Validator version tương thích với Spring Boot và OpenAPI version.
- [ ] Các keyword OpenAPI 3.1 đang dùng nằm trong feature set được hỗ trợ.
- [ ] Negative request tests không vô tình bị đánh giá như request hợp lệ.
- [ ] Security/authorization có test riêng.
- [ ] Gateway/proxy có end-to-end test nếu chúng thay đổi HTTP interaction.
- [ ] Validation report được lưu trong CI.
- [ ] Whitelist validation errors có phạm vi hẹp và lý do rõ ràng.

## 16. Tài liệu tham khảo

- [springdoc-openapi – Getting Started](https://springdoc.org/getting-started.html)
- [Atlassian OpenAPI Request Validator – README](https://github.com/atlassian/openapi-request-validator)
- [Atlassian OpenAPI Request Validator – MockMvc adapter](https://github.com/atlassian/openapi-request-validator/tree/master/openapi-request-validator-mockmvc)
- [Atlassian OpenAPI Request Validator – REST Assured adapter](https://github.com/atlassian/openapi-request-validator/tree/master/openapi-request-validator-restassured)
- [Atlassian OpenAPI Request Validator – Feature support matrix](https://github.com/atlassian/openapi-request-validator/blob/master/docs/FEATURES.md)
- [Atlassian OpenAPI Request Validator – OpenAPI 3 support](https://github.com/atlassian/openapi-request-validator/blob/master/docs/OPENAPIv3.md)
- [Atlassian OpenAPI Request Validator – Release notes and v2 to v3 migration](https://github.com/atlassian/openapi-request-validator/blob/master/RELEASE-NOTES.md)
- [REST Assured – Writing tests](https://rest-assured.io/docs/usage/)
- [REST Assured – JSON Schema validation](https://rest-assured.io/docs/usage/json-schema/)
- [Spring Cloud Contract – Getting Started](https://docs.spring.io/spring-cloud-contract/docs/current/reference/html/getting-started.html)
- [Pact – Documentation](https://docs.pact.io/)

Contract test có ý nghĩa khi nó kiểm tra đúng dữ liệu HTTP mà client nhận và gửi. Hãy dùng springdoc để tạo hoặc duy trì OpenAPI artifact, gửi request qua MockMvc/REST Assured, rồi validate status, headers, media type và payload với schema đã được duyệt. Kết hợp kiểm tra runtime với contract diff để phát hiện cả lỗi serialization hiện tại lẫn thay đổi hợp đồng có thể ảnh hưởng client.
