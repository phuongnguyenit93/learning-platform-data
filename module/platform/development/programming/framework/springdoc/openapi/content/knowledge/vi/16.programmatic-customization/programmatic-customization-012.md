# Đăng ký components đồng bộ với mọi $ref được bổ sung

Khi tùy biến OpenAPI bằng Java, có thể cần thêm schema dùng chung, response lỗi, parameter, request body hoặc security scheme để nhiều operation cùng tham chiếu. Trong OpenAPI, các định nghĩa tái sử dụng được đặt trong **components**; những vị trí sử dụng chúng trỏ tới bằng **$ref** hoặc tên scheme tương ứng.

Một tham chiếu chỉ có ý nghĩa khi đích của nó tồn tại và đúng loại. Ví dụ, $ref trỏ tới `#/components/responses/NotFound` phải trỏ tới một Response Object; không thể đăng ký tên đó dưới `components.schemas` rồi kỳ vọng operation hiểu được. Bài này hướng dẫn đăng ký component bằng mô hình OpenAPI và customizer của springdoc, tạo tham chiếu chính xác, tránh ghi đè component hiện có và xác minh toàn bộ tài liệu sau khi tùy biến.

## 1. Components và $ref giải quyết vấn đề gì?

Nếu nhiều operation dùng cùng một cấu trúc lỗi, việc lặp lại schema và mô tả ở từng operation khiến tài liệu dài và dễ không đồng nhất. OpenAPI cung cấp vùng `components` để định nghĩa các thành phần có thể tái sử dụng.

Ví dụ:

~~~yaml
components:
  schemas:
    ApiError:
      type: object
      required:
        - code
        - message
      properties:
        code:
          type: string
        message:
          type: string

paths:
  /api/orders/{id}:
    get:
      responses:
        '404':
          description: Không tìm thấy đơn hàng
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiError'
~~~

Schema ApiError chỉ được định nghĩa một lần trong components.schemas. Operation tham chiếu lại schema đó bằng JSON Pointer.

Lợi ích của cách tổ chức này:

- Giữ mô tả dùng chung ở một nơi.
- Tránh lặp schema trong nhiều operation.
- Giúp client generator tái sử dụng model.
- Dễ cập nhật cấu trúc chung và rà soát ảnh hưởng.
- Làm cho tài liệu lớn dễ đọc và dễ bảo trì hơn.

Components là vùng định nghĩa, không phải endpoint HTTP. Việc thêm một schema vào components không tự tạo API mới và không làm thay đổi hành vi controller.

## 2. Những nhóm component có thể đăng ký

OpenAPI hỗ trợ nhiều loại component. Mỗi loại có vị trí và kiểu tham chiếu riêng:

| Nhóm | Vị trí | Dùng để tái sử dụng |
|---|---|---|
| Schemas | `components.schemas` | Object, enum, primitive schema, cấu trúc request/response |
| Responses | `components.responses` | Response description, headers, content và schema |
| Parameters | `components.parameters` | Path, query, header hoặc cookie parameter |
| Request Bodies | `components.requestBodies` | Request body cùng media type và schema |
| Headers | `components.headers` | Định nghĩa header response |
| Examples | `components.examples` | Ví dụ request hoặc response |
| Links | `components.links` | Liên kết từ response tới operation khác |
| Callbacks | `components.callbacks` | Mô tả callback do API gọi tới client |
| Security Schemes | `components.securitySchemes` | Cơ chế xác thực như bearer, API key hoặc OAuth2 |

Không phải mọi component đều được tham chiếu bằng cùng một cú pháp annotation. Schema, response, parameter và request body thường có thể dùng $ref tại vị trí tương ứng. Security scheme thường được gắn với operation thông qua tên scheme trong security requirement hoặc annotation `@SecurityRequirement`.

## 3. Đọc đúng đường dẫn $ref

Với component nội bộ trong cùng tài liệu, tham chiếu thường có dạng:

~~~text
#/components/<nhóm>/<tên-component>
~~~

Ví dụ:

~~~yaml
$ref: '#/components/schemas/ApiError'
$ref: '#/components/responses/NotFound'
$ref: '#/components/parameters/TraceId'
$ref: '#/components/requestBodies/CreateOrderBody'
$ref: '#/components/headers/RateLimitRemaining'
$ref: '#/components/securitySchemes/bearerAuth'
~~~

Cách đọc `#/components/schemas/ApiError`:

1. `#` chỉ tài liệu OpenAPI hiện tại.
2. `components` đi tới vùng component.
3. `schemas` chọn nhóm schema.
4. `ApiError` chọn component có đúng tên đó.

Tên component phân biệt chữ hoa và chữ thường. `ApiError`, `apiError` và `APIError` là ba khóa khác nhau. Tên chứa ký tự đặc biệt trong JSON Pointer cần được escape theo quy tắc JSON Pointer; để tránh nhầm lẫn, nên dùng tên component đơn giản gồm chữ, số và dấu gạch dưới khi cần.

Không tạo $ref bằng cách đoán tên class Java. Tên component có thể được thay đổi bởi `@Schema(name = "...")`, generic type, model converter hoặc cấu hình swagger-core. Hãy kiểm tra khóa thực tế trong JSON được sinh ra.

## 4. Đăng ký schema bằng OpenAPI model

Có thể tạo component trực tiếp bằng các lớp trong swagger-models. Ví dụ đăng ký schema ApiError:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.media.ObjectSchema;
import io.swagger.v3.oas.models.media.StringSchema;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI openAPI() {
        Components components = new Components()
            .addSchemas(
                "ApiError",
                new ObjectSchema()
                    .addProperties("code",
                        new StringSchema().example("ORDER_NOT_FOUND"))
                    .addProperties("message",
                        new StringSchema().example("Không tìm thấy đơn hàng"))
            );

        return new OpenAPI()
            .components(components);
    }
}
~~~

Trong ví dụ, `addSchemas("ApiError", ...)` đăng ký một schema dưới khóa ApiError. Sau đó operation có thể tham chiếu:

~~~yaml
schema:
  $ref: '#/components/schemas/ApiError'
~~~

OpenAPI model là mô hình đối tượng của đặc tả, không phải DTO runtime của controller. Khi tự tạo schema, cần khai báo đủ type, properties, required, format, enum và constraint mà client cần biết. Việc tạo schema bằng Java không tự tạo class DTO hay validation trong ứng dụng.

Nếu ứng dụng đã dùng DTO ApiError và springdoc tự sinh schema, hãy cân nhắc để thư viện phân tích DTO thay vì tạo thêm một schema thủ công trùng tên. Chọn một nguồn định nghĩa rõ ràng cho mỗi component.

## 5. Thêm component bằng OpenApiCustomizer

Khi muốn bổ sung component vào tài liệu được springdoc tạo từ controller, có thể dùng `OpenApiCustomizer`. Customizer nhận mô hình OpenAPI đã được tạo để bổ sung hoặc điều chỉnh metadata.

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.media.ObjectSchema;
import io.swagger.v3.oas.models.media.Schema;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.responses.ApiResponse;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class SharedOpenApiComponentsConfiguration {

    @Bean
    OpenApiCustomizer sharedComponentsCustomizer() {
        return openApi -> {
            Components components = openApi.getComponents();

            if (components == null) {
                components = new Components();
                openApi.setComponents(components);
            }

            components.addSchemas("ApiError", apiErrorSchema());
            components.addResponses("BadRequest", badRequestResponse());
        };
    }

    private Schema<?> apiErrorSchema() {
        return new ObjectSchema()
            .addProperties("code", new StringSchema()
                .example("VALIDATION_FAILED"))
            .addProperties("message", new StringSchema()
                .example("Dữ liệu yêu cầu không hợp lệ"));
    }

    private ApiResponse badRequestResponse() {
        return new ApiResponse()
            .description("Request không hợp lệ")
            .content(new Content().addMediaType(
                "application/json",
                new MediaType().schema(
                    new Schema<>().$ref("#/components/schemas/ApiError")
                )
            ));
    }
}
~~~

Customizer trên bổ sung hai component:

- `components.schemas.ApiError`: schema của body lỗi.
- `components.responses.BadRequest`: response dùng schema ApiError.

Trong Response Object, schema được tham chiếu bằng `#/components/schemas/ApiError`. Việc đăng ký response và schema là hai thao tác riêng; cần bảo đảm cả hai đều tồn tại.

Ví dụ dùng API model của swagger-core. Các import và extension point phải khớp phiên bản springdoc/swagger-models mà dự án đang sử dụng. Nếu nâng major, hãy kiểm tra package và chữ ký API tương ứng.

## 6. Không thay toàn bộ Components khi chỉ muốn bổ sung

Một lỗi dễ gặp là tạo Components mới rồi gán lại vào OpenAPI sau khi springdoc đã sinh các schema khác:

~~~java
// Không nên làm nếu mục đích chỉ là bổ sung một component.
openApi.setComponents(
    new Components().addSchemas("ApiError", apiErrorSchema())
);
~~~

Cách này có thể làm mất các schema, response hoặc security scheme đã được sinh từ controller và annotation. Hãy lấy Components hiện có; chỉ tạo mới khi nó đang null; sau đó thêm đúng thành phần cần thiết.

Mẫu an toàn hơn:

~~~java
Components components = openApi.getComponents();

if (components == null) {
    components = new Components();
    openApi.setComponents(components);
}

components.addSchemas("ApiError", apiErrorSchema());
~~~

Nếu cần thay đổi component hiện có, hãy xác định rõ component đó do ai sở hữu và vì sao cần thay. Không dùng thao tác thay toàn bộ map chỉ để cập nhật một khóa.

## 7. Kiểm soát trùng tên và chính sách ghi đè

Các component được lưu theo khóa. Khi đăng ký component cùng tên với một khóa đã tồn tại, thao tác thêm có thể thay thế định nghĩa trước đó tùy cách API model quản lý map. Việc ghi đè vô tình có thể làm thay đổi schema mà nhiều operation đang tham chiếu.

Có thể kiểm tra xung đột trước khi thêm:

~~~java
Map<String, Schema> schemas = components.getSchemas();

if (schemas != null && schemas.containsKey("ApiError")) {
    throw new IllegalStateException(
        "Component ApiError đã tồn tại; cần xác định nguồn định nghĩa trước khi thay thế"
    );
}

components.addSchemas("ApiError", apiErrorSchema());
~~~

Đây là chính sách fail-fast minh họa. Tùy dự án, có thể chọn một trong các cách:

- Dùng component hiện có nếu nó đã đúng hợp đồng.
- Đổi tên component mới nếu ngữ nghĩa khác.
- Thực hiện merge có chủ đích và kiểm tra tương thích.
- Thay thế component cũ khi đã đánh giá ảnh hưởng tới tất cả $ref.

Không nên âm thầm ghi đè. Nếu component cũ được dùng bởi nhiều operation, thay đổi một field required, type hoặc enum có thể ảnh hưởng toàn bộ client.

## 8. Đăng ký Response dùng chung và tham chiếu từ operation

Sau khi đăng ký `components.responses.BadRequest`, operation có thể tham chiếu response này:

~~~java
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;

@PostMapping("/api/orders")
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Đã tạo đơn hàng"
    ),
    @ApiResponse(
        responseCode = "400",
        ref = "#/components/responses/BadRequest"
    )
})
public OrderResponse createOrder(
    @RequestBody CreateOrderRequest request
) {
    return orderService.create(request);
}
~~~

Trong OpenAPI đầu ra, response 400 sẽ tham chiếu component response BadRequest. Component response đó lại chứa content schema trỏ tới ApiError.

Chuỗi tham chiếu cần nhất quán:

~~~text
operation.responses["400"]
    -> #/components/responses/BadRequest
        -> content.application/json.schema
            -> #/components/schemas/ApiError
~~~

Mỗi mắt xích phải tồn tại đúng loại. Nếu response component tồn tại nhưng schema ApiError không có, tài liệu vẫn bị lỗi tham chiếu.

Lưu ý: @ApiResponse chỉ mô tả tài liệu. Controller hoặc exception handler vẫn phải trả status 400 và body đúng cấu trúc ApiError nếu đó là hợp đồng đã công bố.

## 9. Đăng ký Parameter dùng chung

Một header như X-Request-Id có thể được dùng trong nhiều operation. Có thể đăng ký Parameter Object:

~~~java
import io.swagger.v3.oas.models.parameters.Parameter;
import io.swagger.v3.oas.models.media.StringSchema;

components.addParameters(
    "TraceId",
    new Parameter()
        .name("X-Request-Id")
        .in("header")
        .required(false)
        .description("Mã truy vết do client gửi nếu có")
        .schema(new StringSchema())
);
~~~

Tham chiếu từ annotation:

~~~java
@GetMapping("/api/orders")
public List<OrderResponse> listOrders(
    @io.swagger.v3.oas.annotations.Parameter(
        ref = "#/components/parameters/TraceId"
    )
    @RequestHeader(name = "X-Request-Id", required = false)
    String traceId
) {
    return orderService.findAll();
}
~~~

Trong ví dụ, annotation OpenAPI `@Parameter` được viết đầy đủ package để phân biệt với model class `io.swagger.v3.oas.models.parameters.Parameter`. Annotation của Spring `@RequestHeader` vẫn quyết định binding header ở runtime.

Tên header trong component phải khớp với header mà controller và client sử dụng. Nếu component mô tả X-Request-Id nhưng controller nhận X-Correlation-Id, tài liệu và runtime đã không còn đồng bộ.

## 10. Đăng ký Request Body dùng chung

Khi nhiều operation nhận cùng một cấu trúc request body, có thể đăng ký Request Body Object trong components.requestBodies:

~~~yaml
components:
  requestBodies:
    CreateOrderBody:
      required: true
      description: Dữ liệu tạo đơn hàng
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/CreateOrderRequest'
~~~

Tham chiếu tại operation:

~~~yaml
paths:
  /api/orders:
    post:
      requestBody:
        $ref: '#/components/requestBodies/CreateOrderBody'
      responses:
        '201':
          description: Đã tạo đơn hàng
~~~

Trong controller, annotation OpenAPI request body có thể tham chiếu component, đồng thời annotation Spring vẫn thực hiện binding:

~~~java
public OrderResponse createOrder(
    @org.springframework.web.bind.annotation.RequestBody
    @io.swagger.v3.oas.annotations.parameters.RequestBody(
        ref = "#/components/requestBodies/CreateOrderBody"
    )
    CreateOrderRequest request
) {
    return orderService.create(request);
}
~~~

Chỉ dùng request body chung khi các operation thật sự có cùng cấu trúc, media type, required và ý nghĩa dữ liệu. Nếu hai request chỉ giống một phần nhưng có quy tắc required khác nhau, nên tạo schema hoặc request body riêng để tránh mô tả sai.

## 11. Đăng ký Security Scheme và đồng bộ tên requirement

Security scheme được khai báo trong `components.securitySchemes`. Ví dụ bearer JWT:

~~~java
import io.swagger.v3.oas.models.security.SecurityScheme;

components.addSecuritySchemes(
    "bearerAuth",
    new SecurityScheme()
        .type(SecurityScheme.Type.HTTP)
        .scheme("bearer")
        .bearerFormat("JWT")
);
~~~

Operation có thể yêu cầu scheme theo tên:

~~~java
@Operation(
    summary = "Lấy hồ sơ hiện tại",
    security = @SecurityRequirement(name = "bearerAuth")
)
@GetMapping("/api/me")
public ProfileResponse getProfile() {
    return profileService.current();
}
~~~

Tên `bearerAuth` trong @SecurityRequirement phải khớp chính xác khóa đã đăng ký trong components.securitySchemes. Đây là liên kết theo tên scheme, không phải một $ref thông thường.

Nếu khai báo scheme dưới tên `jwtAuth` nhưng operation yêu cầu `bearerAuth`, tài liệu có thể không gắn đúng cơ chế xác thực. Hãy kiểm tra cả component và security requirement trong JSON.

Khai báo security scheme chỉ mô tả cách client gửi credential. Nó không tự cấu hình Spring Security, cấp token hoặc bảo vệ endpoint. Cấu hình runtime phải được triển khai riêng.

## 12. Tổ chức component bằng một nguồn định nghĩa rõ ràng

Trong dự án lớn, component có thể đến từ nhiều nguồn:

- springdoc tự suy ra từ DTO và kiểu trả về.
- Annotation swagger như @Schema, @ApiResponse và @SecurityScheme.
- OpenAPI bean.
- OpenApiCustomizer hoặc customizer theo group.
- Tệp OpenAPI được nạp hoặc hợp nhất từ nguồn ngoài.

Nếu nhiều nguồn cùng tạo component, cần quy ước quyền sở hữu. Ví dụ:

| Component | Nguồn định nghĩa đề xuất |
|---|---|
| DTO request/response | Java DTO và @Schema |
| Response lỗi dùng chung | DTO lỗi hoặc customizer chung |
| Parameter header dùng chung | Customizer hoặc OpenAPI bean |
| Security scheme | OpenAPI bean hoặc @SecurityScheme |
| Component đặc thù một group | Customizer gắn với group đó |

Không cần định nghĩa thủ công một schema nếu springdoc đã tự tạo chính xác từ DTO và annotation. Định nghĩa trùng lặp làm tăng nguy cơ khác biệt về required, nullable, format và property.

Nếu dùng OpenAPI bean và customizer cùng lúc, hãy xác định phần nào tạo metadata nền và phần nào bổ sung. Tránh nhiều customizer cùng ghi một khóa component với nội dung khác nhau.

## 13. Phân biệt customizer toàn cục và theo group

Một ứng dụng có thể công bố nhiều tài liệu qua GroupedOpenApi. Mỗi group có thể có tập path, operation và component khác nhau.

Khi thêm component bằng customizer, cần xác định phạm vi:

- Component cần dùng cho mọi tài liệu thì cấu hình ở extension point áp dụng toàn cục phù hợp với phiên bản springdoc.
- Component chỉ phục vụ một nhóm API thì gắn customizer vào group tương ứng.
- Component được tham chiếu trong một group phải có mặt trong tài liệu group đó, không chỉ trong tài liệu mặc định.

Các extension point như OpenApiCustomizer và GlobalOpenApiCustomizer có phạm vi áp dụng khác nhau giữa cấu hình mặc định và grouped API. Hãy kiểm tra tài liệu đúng phiên bản springdoc và xác minh từng endpoint tài liệu, ví dụ `/v3/api-docs` cùng `/v3/api-docs/{group}`.

Một $ref nội bộ luôn được giải quyết trong tài liệu đang chứa nó. Không giả định component ở tài liệu mặc định tự động có mặt trong tài liệu group.

## 14. Tránh component mồ côi và tham chiếu bị thiếu

Hai tình huống thường gặp:

- **Component mồ côi:** component được đăng ký nhưng không operation nào tham chiếu. Điều này không nhất thiết làm tài liệu không hợp lệ, nhưng có thể gây nhiễu và làm client generator tạo model không cần thiết tùy công cụ.
- **Tham chiếu bị thiếu:** operation có $ref nhưng component tương ứng không tồn tại. Đây là lỗi cấu trúc cần sửa trước khi phát hành.

Ví dụ sai:

~~~yaml
responses:
  '404':
    $ref: '#/components/responses/NotFound'

components:
  responses:
    NotFoundOrder:
      description: Không tìm thấy đơn hàng
~~~

Operation trỏ tới NotFound nhưng component được đăng ký là NotFoundOrder. Tên khóa không khớp nên tham chiếu không được giải quyết.

Cách sửa:

~~~yaml
responses:
  '404':
    $ref: '#/components/responses/NotFoundOrder'
~~~

Hãy kiểm tra cả loại component. Nếu response trỏ nhầm sang `#/components/schemas/NotFoundOrder`, việc tên cuối giống nhau không làm tham chiếu đúng loại.

## 15. Kiểm tra $ref trong OpenAPI JSON

Sau khi ứng dụng chạy, tải tài liệu:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Liệt kê tất cả tham chiếu trong tài liệu:

~~~bash
jq -r '
  .. | objects
  | .["$ref"]? // empty
' openapi.json
~~~

Kiểm tra các component schema đã đăng ký:

~~~bash
jq '.components.schemas | keys' openapi.json
~~~

Kiểm tra response dùng chung:

~~~bash
jq '.components.responses.BadRequest' openapi.json
~~~

Kiểm tra response của operation:

~~~bash
jq '.paths["/api/orders"].post.responses["400"]' openapi.json
~~~

Kiểm tra security scheme và requirement:

~~~bash
jq '.components.securitySchemes, .paths["/api/me"].get.security' openapi.json
~~~

Đối chiếu từng tham chiếu:

- Đúng nhóm component chưa?
- Tên khóa có khớp chính xác không?
- Component có thực sự tồn tại trong cùng tài liệu không?
- Kiểu component có đúng vị trí sử dụng không?
- Component có đủ schema, description, media type hoặc header cần thiết không?
- Các group API có đăng ký component riêng cần thiết không?

Có thể dùng validator OpenAPI để kiểm tra tự động các tham chiếu không hợp lệ:

~~~bash
openapi-generator-cli validate -i openapi.json
~~~

Validator không thay thế review ngữ nghĩa. Một $ref có thể hợp lệ về cấu trúc nhưng trỏ tới schema không phản ánh đúng payload runtime.

## 16. Kiểm tra bằng test

Có thể viết test gọi endpoint OpenAPI và xác minh component cùng tham chiếu:

~~~java
@Test
void documentsSharedBadRequestResponse() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.components.schemas.ApiError"
        ).exists())
        .andExpect(jsonPath(
            "$.components.responses.BadRequest"
        ).exists())
        .andExpect(jsonPath(
            "$.paths['/api/orders'].post.responses['400'].$ref"
        ).value("#/components/responses/BadRequest"));
}
~~~

Test trên kiểm tra các thành phần quan trọng được công bố. Có thể bổ sung assertion rằng response component tham chiếu schema ApiError:

~~~java
.andExpect(jsonPath(
    "$.components.responses.BadRequest.content['application/json'].schema.$ref"
).value("#/components/schemas/ApiError"));
~~~

Nếu có grouped API, gọi endpoint của từng group và xác minh component cần thiết tồn tại trong từng tài liệu. Một test chỉ kiểm tra default document không bảo đảm các group đều đúng.

Ngoài test JSON, hãy chạy validator trong CI và kiểm tra request/response runtime. Component response được tham chiếu đúng vẫn có thể mô tả sai body mà exception handler trả về.

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| $ref trỏ tới component không tồn tại | Tên khóa sai, component chưa được đăng ký hoặc customizer không chạy trong tài liệu đó |
| Đã đăng ký ApiError nhưng operation vẫn inline schema | Operation chưa tham chiếu component hoặc annotation dùng implementation thay vì ref |
| Component tự sinh bị mất sau customizer | Customizer thay toàn bộ Components thay vì bổ sung vào object hiện có |
| Schema bị thay đổi bất ngờ | Hai nguồn cùng ghi một component key |
| Response $ref trỏ nhầm sang schemas | Dùng sai nhóm component trong JSON Pointer |
| Security requirement không nhận scheme | Tên trong @SecurityRequirement khác khóa securitySchemes |
| Default document đúng nhưng group bị lỗi | Customizer không áp dụng cho grouped OpenAPI hoặc group không có component cần thiết |
| Validator báo lỗi sau khi thêm response ref | Response component thiếu description hoặc tham chiếu schema bên trong không hợp lệ |
| Component mồ côi xuất hiện nhiều | Đăng ký thủ công không cần thiết hoặc không có quy ước dọn dẹp |
| Ref ngoài không truy cập được | URL tài liệu ngoài sai hoặc consumer không thể truy cập tài nguyên |

Khi điều tra, hãy lần theo chuỗi từ vị trí sử dụng tới component và các tham chiếu lồng bên trong. Không chỉ tìm tên component rồi kết luận mọi liên kết đã đúng.

## 18. Quy trình đăng ký component an toàn

Khi bổ sung một component mới, có thể thực hiện theo thứ tự:

1. Xác định component thuộc loại nào: schema, response, parameter, request body, header hay security scheme.
2. Chọn tên component ổn định và không trùng khóa hiện có.
3. Đăng ký component trong đúng nhóm Components.
4. Bổ sung $ref hoặc security requirement tại vị trí sử dụng.
5. Kiểm tra các tham chiếu lồng nhau bên trong component.
6. Xác minh customizer áp dụng cho default document và các group cần thiết.
7. Tải JSON OpenAPI và kiểm tra component cùng tất cả $ref.
8. Chạy validator và test tự động.
9. Đối chiếu schema với request/response runtime.
10. Review ảnh hưởng của thay đổi component dùng chung tới các operation và client hiện có.

Giữ phần đăng ký và tham chiếu gần nhau về mặt tổ chức code, hoặc tập trung trong một cấu hình chung. Cách này giúp người bảo trì nhìn thấy component được tạo ở đâu và được sử dụng ở đâu.

## 19. Checklist đăng ký Components và $ref

- [ ] Đã xác định đúng loại component cần tái sử dụng.
- [ ] Tên component rõ nghĩa, ổn định và không trùng.
- [ ] Component được thêm vào đúng nhóm trong Components.
- [ ] Customizer giữ lại các component đã được springdoc tạo.
- [ ] Mọi $ref trỏ tới đúng nhóm và đúng tên component.
- [ ] Các $ref lồng bên trong component cũng hợp lệ.
- [ ] Security requirement dùng đúng tên security scheme.
- [ ] Không có ghi đè component ngoài ý muốn.
- [ ] Component chỉ được đăng ký ở những tài liệu/group cần dùng.
- [ ] Không có component mồ côi không cần thiết.
- [ ] Validator OpenAPI chạy thành công.
- [ ] Test xác minh component và reference trong JSON.
- [ ] Schema và response component khớp dữ liệu runtime.

## 20. Nguồn tra cứu

- [OpenAPI Specification – Components Object](https://spec.openapis.org/oas/latest.html#components-object)
- [OpenAPI Specification – Reference Object](https://spec.openapis.org/oas/latest.html#reference-object)
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object)
- [Swagger – Using $ref](https://swagger.io/docs/specification/v3_0/using-ref/)
- [springdoc-openapi – tài liệu chính thức](https://springdoc.org/)
- [Swagger Core – Models and annotations](https://github.com/swagger-api/swagger-core)

Components lưu các định nghĩa dùng chung; $ref và security requirement kết nối operation với những định nghĩa đó. Khi tùy biến bằng springdoc, hãy bổ sung vào Components hiện có, tránh xung đột khóa và kiểm tra mọi tham chiếu trong từng tài liệu OpenAPI được phát hành. Một spec chỉ nên được dùng cho client generator sau khi các component, tham chiếu và hành vi runtime đã được xác minh.
