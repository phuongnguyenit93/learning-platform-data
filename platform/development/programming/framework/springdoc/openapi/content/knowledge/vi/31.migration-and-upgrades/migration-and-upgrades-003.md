# Thay @Api, @ApiOperation và @ApiParam bằng annotation OpenAPI tương ứng

Các annotation Swagger 2 thường gặp trong dự án Spring Boot cũ gồm @Api, @ApiOperation, @ApiParam, @ApiModel và @ApiModelProperty. Khi chuyển sang springdoc-openapi, thay chúng bằng annotation Swagger Core 3 thuộc OpenAPI 3, nằm trong package io.swagger.v3.oas.annotations.

Các ánh xạ cốt lõi:

- @Api chuyển thành @Tag.
- @ApiOperation chuyển thành @Operation.
- @ApiParam chuyển thành @Parameter.
- @ApiModel và @ApiModelProperty chuyển thành @Schema.
- @ApiResponse của Swagger 2 chuyển thành @ApiResponse của OpenAPI 3, nhưng thuộc tính code/message đổi thành responseCode/description.

Thay tên annotation chưa đủ để bảo đảm tài liệu đúng. Một số thông tin trước đây được khai báo trong annotation giờ nên lấy từ Spring MVC mapping, kiểu Java hoặc OpenAPI model. Bài này hướng dẫn thay package import, ánh xạ thuộc tính, xử lý response/security/schema và xác minh document sau migration.

## 1. Nhận diện hai hệ annotation

Swagger 2 annotations thường dùng package:

~~~java
io.swagger.annotations.Api
io.swagger.annotations.ApiOperation
io.swagger.annotations.ApiParam
io.swagger.annotations.ApiModel
io.swagger.annotations.ApiModelProperty
~~~

OpenAPI 3 annotations dùng package:

~~~java
io.swagger.v3.oas.annotations.tags.Tag
io.swagger.v3.oas.annotations.Operation
io.swagger.v3.oas.annotations.Parameter
io.swagger.v3.oas.annotations.media.Schema
io.swagger.v3.oas.annotations.responses.ApiResponse
~~~

Tên một số annotation được giữ lại, chẳng hạn ApiResponse và ApiResponses, nhưng package và thuộc tính đã thay đổi. Vì vậy, khi IDE tự động thêm import, hãy kiểm tra package đầy đủ thay vì chỉ nhìn tên ngắn.

Không nên giữ đồng thời swagger-annotations 1.x và swagger-annotations 2.x trong code chỉ để migration từng phần mà không kiểm soát. Hai hệ có những class trùng tên đơn giản, dễ gây import nhầm và tạo tài liệu thiếu nhất quán.

## 2. Bảng ánh xạ annotation phổ biến

| Swagger 2 | OpenAPI 3 | Mục đích |
|---|---|---|
| @Api | @Tag | Nhóm controller hoặc operation |
| @ApiOperation | @Operation | Mô tả operation |
| @ApiParam | @Parameter | Mô tả path/query/header/cookie parameter |
| @ApiImplicitParam | @Parameter | Khai báo parameter không có Java argument tương ứng |
| @ApiImplicitParams | @Parameters | Nhóm nhiều parameter |
| @ApiModel | @Schema | Mô tả model/schema |
| @ApiModelProperty | @Schema | Mô tả property trong schema |
| @ApiResponse | @ApiResponse | Mô tả một response |
| @ApiResponses | @ApiResponses | Nhóm nhiều response |
| @ApiIgnore | @Hidden, @Operation(hidden=true) hoặc @Parameter(hidden=true) | Ẩn API hoặc parameter |
| @Authorization | @SecurityRequirement kết hợp @SecurityScheme | Mô tả bảo mật |
| @AuthorizationScope | OAuth flow scopes trong @SecurityScheme | Khai báo OAuth scope |

Đây là ánh xạ khởi đầu, không phải phép thay thế văn bản một-một. Cần xem từng thuộc tính và vị trí annotation được sử dụng.

## 3. Thay @Api bằng @Tag

Trong Swagger 2, @Api thường đặt ở cấp controller để nhóm các operation:

~~~java
import io.swagger.annotations.Api;

@Api(
    value = "Orders",
    description = "Các thao tác quản lý đơn hàng"
)
@RestController
@RequestMapping("/api/orders")
class OrderController {
}
~~~

Trong OpenAPI 3, dùng @Tag:

~~~java
import io.swagger.v3.oas.annotations.tags.Tag;

@Tag(
    name = "Orders",
    description = "Các thao tác quản lý đơn hàng"
)
@RestController
@RequestMapping("/api/orders")
class OrderController {
}
~~~

name là tên tag được dùng để nhóm operation. description mô tả nhóm đó trong tài liệu.

Nếu controller có nhiều nhóm operation hoặc một method thuộc tag khác controller, có thể chỉ định tags trực tiếp trên @Operation:

~~~java
@Operation(
    summary = "Tìm đơn hàng",
    tags = {"Orders", "Search"}
)
~~~

Không dùng @Tag để mô tả HTTP method hoặc URL. Spring MVC mapping như @GetMapping và @PostMapping vẫn xác định route.

## 4. Thay @ApiOperation bằng @Operation

Ví dụ Swagger 2:

~~~java
import io.swagger.annotations.ApiOperation;

@ApiOperation(
    value = "Tìm đơn hàng theo mã",
    notes = "Chỉ trả về đơn hàng mà người dùng có quyền truy cập",
    nickname = "findOrderById"
)
@GetMapping("/{id}")
OrderResponse findById(@PathVariable String id) {
    // ...
}
~~~

OpenAPI 3:

~~~java
import io.swagger.v3.oas.annotations.Operation;

@Operation(
    summary = "Tìm đơn hàng theo mã",
    description = "Chỉ trả về đơn hàng mà người dùng có quyền truy cập",
    operationId = "findOrderById"
)
@GetMapping("/{id}")
OrderResponse findById(@PathVariable String id) {
    // ...
}
~~~

Các thuộc tính thường được ánh xạ:

| @ApiOperation cũ | @Operation mới |
|---|---|
| value | summary |
| notes | description |
| nickname | operationId |
| hidden | hidden |
| authorizations | security |
| tags | tags |
| deprecated | deprecated |
| extensions | extensions |
| response/code | Thường chuyển sang @ApiResponse hoặc để springdoc suy ra từ method return type |

summary nên ngắn gọn và mô tả hành động. description có thể giải thích điều kiện, giới hạn hoặc hành vi nghiệp vụ.

operationId cần duy nhất trong document nếu client generator dựa vào nó để đặt tên method. Tránh tạo operationId trùng sau khi đổi tên controller hoặc method.

## 5. Những thuộc tính @ApiOperation không nên thay máy móc

Một số thuộc tính Swagger 2 cũ không có thuộc tính tương đương trực tiếp trên @Operation:

| Thuộc tính cũ | Cách xử lý |
|---|---|
| httpMethod | Đã được xác định bởi @GetMapping, @PostMapping hoặc mapping tương ứng |
| consumes | Khai báo consumes trên Spring mapping |
| produces | Khai báo produces trên Spring mapping |
| response | Để springdoc suy ra từ kiểu trả về; chỉ định schema trong @ApiResponse khi cần override |
| responseContainer | Dùng kiểu generic thực tế như List<T> hoặc @ArraySchema khi cần |
| code | Khai báo responseCode trong @ApiResponse |
| authorizations | Dùng @SecurityRequirement và @SecurityScheme |
| protocols | Cấu hình server URL/scheme theo OpenAPI và deployment |
| position | Không có ánh xạ trực tiếp; cân nhắc thứ tự tag hoặc cách hiển thị trong UI |

Ví dụ consumes/produces thuộc về HTTP contract của Spring:

~~~java
@PostMapping(
    value = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
~~~

Không chuyển chúng thành một trường tùy ý của @Operation. springdoc đọc mapping của Spring để tạo requestBody và response content phù hợp.

## 6. Thay @ApiParam bằng @Parameter

Swagger 2:

~~~java
import io.swagger.annotations.ApiParam;

@GetMapping("/{id}")
OrderResponse findById(
    @ApiParam(
        name = "id",
        value = "Mã đơn hàng",
        required = true,
        example = "ORD-1001"
    )
    @PathVariable String id
) {
    // ...
}
~~~

OpenAPI 3:

~~~java
import io.swagger.v3.oas.annotations.Parameter;

@GetMapping("/{id}")
OrderResponse findById(
    @Parameter(
        description = "Mã đơn hàng",
        example = "ORD-1001",
        required = true
    )
    @PathVariable String id
) {
    // ...
}
~~~

Parameter có thể mô tả path, query, header và cookie parameter.

Với Spring MVC, springdoc thường suy ra tên, vị trí và kiểu từ @PathVariable, @RequestParam, @RequestHeader hoặc @CookieValue. Chỉ thêm @Parameter cho phần mô tả hoặc điều chỉnh không thể suy ra từ code.

Nếu tên parameter quan trọng với client, có thể khai báo name tường minh để tránh phụ thuộc compiler giữ parameter names.

## 7. Mô tả query parameter và giá trị mặc định

Ví dụ:

~~~java
@GetMapping
List<OrderResponse> search(
    @Parameter(
        description = "Trạng thái đơn hàng",
        example = "PAID"
    )
    @RequestParam(required = false)
    OrderStatus status,

    @Parameter(
        description = "Số bản ghi tối đa",
        schema = @Schema(defaultValue = "20", minimum = "1", maximum = "100")
    )
    @RequestParam(defaultValue = "20")
    int limit
) {
    // ...
}
~~~

required và defaultValue của Spring binding cần thống nhất với metadata trong @Parameter. Nếu @RequestParam(defaultValue = "20") thì tham số thường không bắt buộc từ góc nhìn request; tài liệu phải thể hiện default đúng.

Không đánh dấu required=true chỉ để làm Swagger UI hiển thị dấu sao nếu server thực tế chấp nhận thiếu parameter.

Khi muốn khai báo allowable values, có thể dùng schema enum:

~~~java
@Parameter(
    description = "Trạng thái đơn hàng",
    schema = @Schema(
        allowableValues = {"PENDING", "PAID", "CANCELLED"}
    )
)
@RequestParam(required = false)
String status
~~~

Nếu Java type đã là enum, springdoc thường suy ra danh sách giá trị. Chỉ override khi tài liệu cần tập giá trị khác có chủ đích và runtime thực sự hỗ trợ điều đó.

## 8. Thay @ApiImplicitParam bằng @Parameter

@ApiImplicitParam thường được dùng khi parameter không xuất hiện như argument rõ ràng trong method, chẳng hạn header do filter hoặc gateway quản lý.

Swagger 2:

~~~java
@ApiImplicitParam(
    name = "X-Request-Id",
    value = "Mã tương quan request",
    required = false,
    dataType = "string",
    paramType = "header"
)
@GetMapping("/api/orders")
List<OrderResponse> list() {
    // ...
}
~~~

OpenAPI 3:

~~~java
@Operation(
    summary = "Liệt kê đơn hàng",
    parameters = {
        @Parameter(
            name = "X-Request-Id",
            description = "Mã tương quan request",
            in = ParameterIn.HEADER,
            schema = @Schema(type = "string")
        )
    }
)
@GetMapping("/api/orders")
List<OrderResponse> list() {
    // ...
}
~~~

ParameterIn xác định vị trí PATH, QUERY, HEADER hoặc COOKIE.

Với header authentication như Authorization, không nên khai báo thủ công một header parameter thông thường nếu ý nghĩa thực sự là security scheme. Hãy dùng @SecurityScheme và @SecurityRequirement để Swagger UI hiểu đúng cơ chế xác thực.

## 9. Thay @ApiImplicitParams bằng @Parameters

Swagger 2:

~~~java
@ApiImplicitParams({
    @ApiImplicitParam(
        name = "X-Tenant-Id",
        value = "Mã tenant",
        paramType = "header",
        dataType = "string"
    ),
    @ApiImplicitParam(
        name = "X-Request-Id",
        value = "Mã tương quan",
        paramType = "header",
        dataType = "string"
    )
})
~~~

OpenAPI 3:

~~~java
@Parameters({
    @Parameter(
        name = "X-Tenant-Id",
        description = "Mã tenant",
        in = ParameterIn.HEADER,
        schema = @Schema(type = "string")
    ),
    @Parameter(
        name = "X-Request-Id",
        description = "Mã tương quan",
        in = ParameterIn.HEADER,
        schema = @Schema(type = "string")
    )
})
~~~

Nếu parameter tương ứng đã có trong method signature, ưu tiên gắn @Parameter trực tiếp lên argument. Cách đó giúp tài liệu bám sát request binding và giảm nguy cơ khai báo trùng.

## 10. Dùng @ParameterObject cho object gom query parameter

Một số controller dùng object để gom nhiều query parameter:

~~~java
@GetMapping("/api/orders")
Page<OrderResponse> search(OrderSearchCriteria criteria) {
    // ...
}
~~~

Nếu muốn springdoc bung các field thành query parameters, dùng @ParameterObject:

~~~java
import org.springdoc.core.annotations.ParameterObject;

@GetMapping("/api/orders")
Page<OrderResponse> search(
    @ParameterObject OrderSearchCriteria criteria
) {
    // ...
}
~~~

Đây là annotation hỗ trợ của springdoc, không phải annotation Swagger 3 thay thế trực tiếp @ApiParam. Nó giúp mô tả object query theo từng thuộc tính.

Nếu object là request body JSON, không dùng @ParameterObject; hãy dùng @RequestBody và schema của DTO.

## 11. Thay @ApiModel bằng @Schema

Swagger 2:

~~~java
import io.swagger.annotations.ApiModel;

@ApiModel(
    value = "Order",
    description = "Thông tin đơn hàng"
)
public class OrderResponse {
}
~~~

OpenAPI 3:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "Order",
    description = "Thông tin đơn hàng"
)
public class OrderResponse {
}
~~~

@Schema có thể mô tả name, title, description, type, format, requiredMode, allowableValues, example, constraints, implementation, oneOf/anyOf/allOf, discriminator, accessMode, deprecated và hidden.

Thông thường springdoc suy ra schema từ kiểu Java và Jackson annotations. Chỉ dùng @Schema khi cần bổ sung hoặc điều chỉnh tài liệu.

## 12. Thay @ApiModelProperty bằng @Schema

Swagger 2:

~~~java
@ApiModelProperty(
    value = "Mã đơn hàng",
    required = true,
    example = "ORD-1001",
    position = 1
)
private String id;
~~~

OpenAPI 3:

~~~java
@Schema(
    description = "Mã đơn hàng",
    requiredMode = Schema.RequiredMode.REQUIRED,
    example = "ORD-1001"
)
private String id;
~~~

Một số mapping phổ biến:

| @ApiModelProperty | @Schema |
|---|---|
| value | description |
| name | name |
| dataType | type hoặc implementation khi thật sự cần |
| example | example |
| allowableValues | allowableValues |
| required | requiredMode |
| readOnly | accessMode = READ_ONLY |
| hidden | hidden |
| notes | description |
| deprecated | deprecated |
| accessMode | accessMode |

requiredMode làm rõ cách xác định required. Tùy phiên bản swagger-annotations, thuộc tính required cũ có thể được đánh dấu deprecated; hãy dùng API của version mà springdoc đang quản lý.

position không có ánh xạ trực tiếp tương đương trong @Schema. Nếu thứ tự property hiển thị là yêu cầu, xem xét Jackson @JsonPropertyOrder hoặc cấu hình UI, rồi kiểm tra output của toolchain.

## 13. Required, nullable và allowEmptyValue

Springdoc migration guide có chỉ dẫn ánh xạ @ApiModelProperty(allowEmptyValue = true) sang @Schema(nullable = true). Tuy nhiên, khi migration cần hiểu ý nghĩa dữ liệu thực tế.

Các khái niệm này khác nhau:

- Required: property có bắt buộc xuất hiện hay không.
- Nullable: property có được phép mang giá trị null hay không.
- Empty string: property có thể có giá trị chuỗi rỗng hay không.

Trong JSON, null và chuỗi rỗng là hai giá trị khác nhau:

~~~json
{
  "nickname": null,
  "comment": ""
}
~~~

Không đánh đồng nullable với allow empty string. Nếu API cần chấp nhận chuỗi rỗng, hãy kiểm tra Bean Validation như @NotBlank, @NotEmpty, @Size và mô tả schema tương ứng.

Ví dụ:

~~~java
@Schema(
    description = "Biệt danh, có thể là null",
    nullable = true
)
private String nickname;
~~~

OpenAPI 3.0 và 3.1 có cách biểu diễn null khác nhau. Hãy kiểm tra OpenAPI version đang được sinh và validator/client generator đang sử dụng.

## 14. Thay @ApiResponse Swagger 2 bằng @ApiResponse OpenAPI 3

Hai annotation cùng tên nhưng khác package và thuộc tính.

Swagger 2:

~~~java
import io.swagger.annotations.ApiResponse;

@ApiResponse(
    code = 404,
    message = "Không tìm thấy đơn hàng",
    response = ApiError.class
)
~~~

OpenAPI 3:

~~~java
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;

@ApiResponse(
    responseCode = "404",
    description = "Không tìm thấy đơn hàng",
    content = @Content(
        schema = @Schema(implementation = ApiError.class)
    )
)
~~~

Các thuộc tính chính:

| Swagger 2 | OpenAPI 3 |
|---|---|
| code | responseCode dạng String |
| message | description |
| response | content.schema.implementation |
| responseContainer | @ArraySchema hoặc schema phù hợp |
| responseHeaders | headers |
| examples | @ExampleObject bên trong @Content |

Nếu response type đã được suy ra chính xác từ method return type, không cần khai báo lại schema chỉ để lặp thông tin. Dùng @ApiResponse để bổ sung status, mô tả, header hoặc override response khi cần.

## 15. Khai báo nhiều response bằng @ApiResponses

Ví dụ:

~~~java
@Operation(summary = "Tìm đơn hàng theo mã")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Tìm thấy đơn hàng",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Không tìm thấy",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
@GetMapping("/{id}")
OrderResponse findById(@PathVariable String id) {
    // ...
}
~~~

@ApiResponses vẫn là annotation container trong OpenAPI 3, nhưng phải import từ io.swagger.v3.oas.annotations.responses.

Đừng khai báo response 200 với schema không khớp method return type. Nếu controller trả ResponseEntity<OrderResponse>, tài liệu cần mô tả đúng body thực tế và status code có thể được trả về.

## 16. Mô tả response dạng collection

Trong Swagger 2, responseContainer thường được dùng để nói kiểu trả về là List hoặc Set. Trong Spring, ưu tiên khai báo kiểu generic thực tế:

~~~java
@GetMapping
List<OrderResponse> list() {
    // ...
}
~~~

springdoc có thể suy ra array schema từ List<OrderResponse>.

Nếu cần khai báo response rõ ràng:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Danh sách đơn hàng",
    content = @Content(
        array = @ArraySchema(
            schema = @Schema(implementation = OrderResponse.class)
        )
    )
)
~~~

Không dùng @Schema(implementation=OrderResponse.class) đơn lẻ nếu body thực tế là array. Khi schema có cấu trúc lồng nhau hoặc generic phức tạp, hãy kiểm tra JSON OpenAPI đầu ra để chắc chắn items được mô tả đúng.

## 17. Mô tả request body thay vì dùng @ApiParam

@ApiParam dành cho parameter, không phải cách mô tả request body hiện đại.

Spring MVC:

~~~java
@PostMapping("/api/orders")
OrderResponse create(
    @RequestBody CreateOrderRequest request
) {
    // ...
}
~~~

springdoc suy ra requestBody và schema từ CreateOrderRequest.

Nếu cần mô tả thêm:

~~~java
@PostMapping("/api/orders")
OrderResponse create(
    @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Thông tin cần thiết để tạo đơn hàng",
        required = true
    )
    @RequestBody
    CreateOrderRequest request
) {
    // ...
}
~~~

Ở đây có hai annotation cùng tên đơn giản RequestBody: một của Spring và một của OpenAPI. Có thể dùng fully qualified name hoặc import OpenAPI annotation với tên rõ ràng để tránh nhầm.

Nếu chỉ cần mô tả DTO, @Schema trên request class hoặc field thường dễ bảo trì hơn.

## 18. Thay @ApiIgnore bằng @Hidden hoặc hidden flag

Swagger 2:

~~~java
@ApiIgnore
@GetMapping("/internal/diagnostics")
Map<String, Object> diagnostics() {
    // ...
}
~~~

OpenAPI 3 có thể dùng:

~~~java
@Hidden
@GetMapping("/internal/diagnostics")
Map<String, Object> diagnostics() {
    // ...
}
~~~

Các lựa chọn khác:

~~~java
@Operation(hidden = true)
@GetMapping("/internal/diagnostics")
Map<String, Object> diagnostics() {
    // ...
}
~~~

Ẩn parameter:

~~~java
@GetMapping("/api/orders")
List<OrderResponse> list(
    @Parameter(hidden = true)
    @RequestHeader("X-Internal-Trace") String trace
) {
    // ...
}
~~~

Chọn phạm vi phù hợp:

- @Hidden trên controller hoặc method khi muốn ẩn khỏi OpenAPI.
- @Operation(hidden = true) để ẩn một operation.
- @Parameter(hidden = true) để ẩn một parameter.

Ẩn khỏi tài liệu không đồng nghĩa bảo vệ endpoint. Authorization, network policy và Spring Security vẫn phải kiểm soát quyền truy cập.

## 19. Thay authorization annotation bằng security scheme

Swagger 2 thường dùng @Authorization hoặc thuộc tính authorizations của @Api/@ApiOperation. OpenAPI 3 tách hai khái niệm:

1. @SecurityScheme định nghĩa cách xác thực.
2. @SecurityRequirement yêu cầu operation sử dụng scheme đó.

Ví dụ bearer JWT:

~~~java
import org.springframework.context.annotation.Configuration;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class OpenApiSecurityConfiguration {
}
~~~

Áp dụng ở operation:

~~~java
@Operation(
    summary = "Lấy thông tin tài khoản",
    security = @SecurityRequirement(name = "bearerAuth")
)
@GetMapping("/api/me")
AccountResponse me() {
    // ...
}
~~~

Không khai báo Authorization như một query parameter hoặc header parameter thông thường nếu nó là cơ chế authentication. Security scheme giúp Swagger UI hiển thị nút Authorize và mô tả credential đúng theo OpenAPI.

## 20. Migrate OAuth scopes

Swagger 2 có @AuthorizationScope để mô tả scope. Trong OpenAPI 3, scope được khai báo bên trong OAuth flow của @SecurityScheme.

Ví dụ:

~~~java
import org.springframework.context.annotation.Configuration;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;

@Configuration
@SecurityScheme(
    name = "oauth2",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://auth.example.com/oauth/authorize",
            tokenUrl = "https://auth.example.com/oauth/token",
            scopes = {
                @OAuthScope(
                    name = "orders.read",
                    description = "Đọc đơn hàng"
                ),
                @OAuthScope(
                    name = "orders.write",
                    description = "Tạo và cập nhật đơn hàng"
                )
            }
        )
    )
)
class OpenApiOAuthConfiguration {
}
~~~

Yêu cầu scope trên operation:

~~~java
@Operation(
    security = @SecurityRequirement(
        name = "oauth2",
        scopes = {"orders.read"}
    )
)
~~~

Scope là một phần của security scheme và requirement. Không chuyển @AuthorizationScope thành @Parameter vì scope không phải HTTP parameter.

## 21. Chuyển @ApiOperation.authorizations sang @SecurityRequirement

Ví dụ cũ:

~~~java
@ApiOperation(
    value = "Cập nhật đơn hàng",
    authorizations = {
        @Authorization(value = "oauth2",
            scopes = {
                @AuthorizationScope(
                    scope = "orders.write",
                    description = "Cập nhật đơn hàng"
                )
            }
        )
    }
)
~~~

Mới:

~~~java
@Operation(
    summary = "Cập nhật đơn hàng",
    security = @SecurityRequirement(
        name = "oauth2",
        scopes = {"orders.write"}
    )
)
~~~

Tên trong SecurityRequirement phải khớp name của @SecurityScheme. Nếu không khớp, document có thể chứa requirement tham chiếu scheme không tồn tại.

Sau migration, kiểm tra cả components.securitySchemes và security ở root/operation trong OpenAPI JSON.

## 22. Thay response header annotation

Nếu Swagger 2 khai báo response header, OpenAPI 3 dùng @Header trong @ApiResponse:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Thành công",
    headers = {
        @Header(
            name = "ETag",
            description = "Mã phiên bản tài nguyên",
            schema = @Schema(type = "string")
        )
    }
)
~~~

Header response không giống request header parameter. Một cái nằm trong Response Object, cái còn lại nằm trong Parameter Object.

Với header chung như X-Request-Id mà client gửi, dùng @Parameter(in = ParameterIn.HEADER). Với header server trả về, dùng @Header bên trong @ApiResponse.

## 23. Thay ví dụ và allowable values

Swagger 2 có thể khai báo example trong @ApiParam hoặc @ApiModelProperty. OpenAPI 3 có thể dùng:

- @Parameter(example = "...") cho parameter.
- @Schema(example = "...") cho property hoặc schema.
- @ExampleObject bên trong @Content cho ví dụ request/response.

Ví dụ request body:

~~~java
@io.swagger.v3.oas.annotations.parameters.RequestBody(
    description = "Thông tin tạo đơn hàng",
    content = @Content(
        examples = @ExampleObject(
            name = "Đơn hàng tiêu chuẩn",
            value = """
                {
                  "customerId": "CUS-1001",
                  "items": [
                    {
                      "productId": "SKU-01",
                      "quantity": 2
                    }
                  ]
                }
                """
        )
    )
)
~~~

Đây là ví dụ annotation OpenAPI RequestBody; khi dùng cùng Spring @RequestBody, cần phân biệt hai package hoặc dùng fully qualified name.

Example phải là payload hợp lệ theo schema và không chứa dữ liệu thật nhạy cảm. Nếu example không khớp required field hoặc enum, Swagger UI có thể tạo request thất bại.

## 24. Thay mô tả polymorphism và discriminator

Swagger 2 @ApiModel có thể dùng subTypes và discriminator. OpenAPI 3 mô tả rõ hơn bằng oneOf/allOf và discriminator trong @Schema.

Ví dụ:

~~~java
@Schema(
    name = "Payment",
    oneOf = {
        CardPayment.class,
        BankTransferPayment.class
    },
    discriminatorProperty = "paymentType"
)
public interface Payment {
}
~~~

Các subtype:

~~~java
@Schema(name = "CardPayment")
public class CardPayment implements Payment {
    private String cardToken;
}
~~~

~~~java
@Schema(name = "BankTransferPayment")
public class BankTransferPayment implements Payment {
    private String bankAccount;
}
~~~

Cần kiểm tra mapping discriminator trong OpenAPI output. Chỉ khai báo Java inheritance không bảo đảm mọi client generator suy ra đúng union type.

Nếu subtype có discriminator value khác tên class, cấu hình mapping tường minh theo khả năng của swagger-annotations version đang dùng.

## 25. Không cần thay annotation khi Spring đã cung cấp metadata

Một phần Swagger 2 annotations có thể đang lặp lại thông tin đã được thể hiện trong Spring MVC:

- @ApiOperation.httpMethod lặp @GetMapping/@PostMapping.
- @ApiParam.name lặp @PathVariable("id") hoặc @RequestParam("status").
- consumes/produces lặp thuộc tính trên mapping.
- response type lặp method return type.
- required lặp @RequestParam(required=true) hoặc Bean Validation.

Khi migration, ưu tiên nguồn sự thật của runtime. Nếu Spring đã biết method, path, parameter type hoặc media type, hãy để springdoc suy ra.

Chỉ thêm annotation OpenAPI khi cần mô tả thông tin mà framework không thể suy ra hoặc cần override có chủ đích.

Điều này giúp tránh tài liệu mâu thuẫn với controller sau các lần refactor.

## 26. Ví dụ migration một controller hoàn chỉnh

Swagger 2:

~~~java
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import io.swagger.annotations.ApiParam;
import io.swagger.annotations.ApiResponse;
import io.swagger.annotations.ApiResponses;

@Api(
    value = "Orders",
    description = "Các thao tác quản lý đơn hàng"
)
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @ApiOperation(
        value = "Tìm đơn hàng",
        notes = "Tìm theo mã đơn hàng",
        nickname = "findOrderById"
    )
    @ApiResponses({
        @ApiResponse(
            code = 200,
            message = "Tìm thấy đơn hàng",
            response = OrderResponse.class
        ),
        @ApiResponse(
            code = 404,
            message = "Không tìm thấy"
        )
    })
    @GetMapping("/{id}")
    OrderResponse findById(
        @ApiParam(
            value = "Mã đơn hàng",
            required = true,
            example = "ORD-1001"
        )
        @PathVariable String id
    ) {
        // ...
    }
}
~~~

OpenAPI 3:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;

@Tag(
    name = "Orders",
    description = "Các thao tác quản lý đơn hàng"
)
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @Operation(
        summary = "Tìm đơn hàng",
        description = "Tìm theo mã đơn hàng",
        operationId = "findOrderById"
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Tìm thấy đơn hàng",
            content = @Content(
                schema = @Schema(
                    implementation = OrderResponse.class
                )
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Không tìm thấy"
        )
    })
    @GetMapping("/{id}")
    OrderResponse findById(
        @Parameter(
            description = "Mã đơn hàng",
            required = true,
            example = "ORD-1001"
        )
        @PathVariable String id
    ) {
        // ...
    }
}
~~~

Trong ví dụ, Spring mapping vẫn xác định GET /api/orders/{id}. @Operation chỉ mô tả operation. Return type OrderResponse đã cho springdoc biết response schema; phần schema tường minh trong @ApiResponse được giữ để minh họa cách override hoặc cố định schema.

Nếu không cần override response, có thể bỏ content để springdoc dùng return type inference, sau đó kiểm tra output.

## 27. Dependency và import cần thay đổi

Khi chuyển từ Springfox sang springdoc, loại bỏ các dependency Swagger 2/Springfox không còn cần thiết và thêm starter springdoc phù hợp với Spring MVC hoặc WebFlux.

Ví dụ Maven cho Spring MVC:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>3.x.y</version>
</dependency>
~~~

Với WebFlux, dùng starter webflux UI tương ứng. Chọn version theo Spring Boot major version và compatibility table của springdoc.

Không giữ các dependency sau chỉ để duy trì annotation cũ:

- springfox-swagger2.
- springfox-swagger-ui.
- springfox-boot-starter.
- swagger-annotations 1.x nếu code đã chuyển sang OpenAPI 3.

Starter springdoc thường đã mang swagger-annotations OpenAPI 3 phù hợp. Tránh tự thêm một version swagger-annotations khác nếu không có lý do tương thích rõ ràng.

## 28. Tìm annotation Swagger 2 còn sót lại

Có thể dùng ripgrep để rà source:

~~~bash
rg -n "io\.swagger\.annotations|@Api\b|@ApiOperation\b|@ApiParam\b|@ApiModel\b|@ApiModelProperty\b|@ApiIgnore\b|@ApiImplicitParam\b" src
~~~

Tìm dependency cũ trong Maven:

~~~bash
mvn dependency:tree | findstr /i "springfox swagger-annotations"
~~~

Hoặc Gradle:

~~~bash
./gradlew dependencies
~~~

Không chỉ tìm tên annotation. Một số import có thể được alias, dùng fully qualified name hoặc nằm trong module khác. Kiểm tra dependency tree của toàn bộ module liên quan.

Sau khi migration, code không còn import io.swagger.annotations.* và dependency Swagger 2 cũ không còn được resolve ngoài trường hợp thư viện khác có yêu cầu đã được đánh giá.

## 29. Tránh xung đột annotation trùng tên

Một số tên được dùng ở cả Swagger 2 và OpenAPI 3:

- ApiResponse.
- ApiResponses.
- Api.
- ApiOperation có thể vẫn còn trong dependency cũ.

IDE có thể tự import package cũ khi code có dependency cả hai hệ.

Khi gặp lỗi compile hoặc tài liệu không thay đổi sau migration:

1. Mở import ở đầu file.
2. Xác nhận package là io.swagger.v3.oas.annotations.
3. Kiểm tra dependency tree.
4. Xóa import cũ không còn sử dụng.
5. Clean/rebuild project.
6. Tải lại /v3/api-docs và kiểm tra output.

Không giải quyết import conflict bằng cách giữ cả hai annotation trên cùng method. springdoc đọc annotation OpenAPI 3; annotation cũ có thể bị bỏ qua.

## 30. Cập nhật test và endpoint tài liệu

Springfox thường cung cấp Swagger 2 document ở /v2/api-docs. springdoc mặc định cung cấp OpenAPI document ở /v3/api-docs.

Sau migration, cập nhật:

- Integration test tải spec.
- API gateway hoặc API portal đọc spec.
- OpenAPI Generator input URL.
- Script export JSON/YAML.
- Link tài liệu nội bộ.
- CI contract validation.
- Cấu hình Swagger UI nếu dùng spec ngoài.

Ví dụ:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o target/openapi.json
~~~

Nếu ứng dụng cấu hình springdoc.api-docs.path khác mặc định, dùng path đã cấu hình thay vì hard-code /v3/api-docs.

Không giữ test chỉ kiểm tra endpoint trả 200. Hãy xác nhận trường openapi, tags, operation summary, parameters, requestBody, responses và schemas.

## 31. Kiểm tra annotation sau migration bằng JSON

Một số lệnh jq hữu ích:

~~~bash
jq '.tags' target/openapi.json
~~~

~~~bash
jq '.paths["/api/orders/{id}"].get' target/openapi.json
~~~

~~~bash
jq '.components.schemas.OrderResponse' target/openapi.json
~~~

~~~bash
jq '.components.securitySchemes' target/openapi.json
~~~

Đối chiếu:

- Tag có đúng tên và description không?
- Operation có summary, description, operationId không?
- Path parameter có required=true không?
- Query/header parameter có đúng in và schema không?
- Response code có đúng chuỗi "200", "404" không?
- Response schema có đúng type hoặc array không?
- Security requirement có tham chiếu scheme tồn tại không?
- Hidden operation/parameter có thực sự bị ẩn không?

Kiểm tra document đầu ra quan trọng hơn việc chỉ xác nhận code compile.

## 32. Kiểm thử bằng WebTestClient

Có thể kiểm tra OpenAPI endpoint trong integration test:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class OpenApiAnnotationMigrationTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void publishesMigratedOperationMetadata() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.openapi").exists()
            .jsonPath("$.paths['/api/orders/{id}'].get.summary")
                .isEqualTo("Tìm đơn hàng")
            .jsonPath("$.paths['/api/orders/{id}'].get.operationId")
                .isEqualTo("findOrderById")
            .jsonPath("$.paths['/api/orders/{id}'].get.parameters[0].name")
                .isEqualTo("id");
    }
}
~~~

Thứ tự parameter có thể thay đổi theo cách framework thu thập metadata. Nếu test chỉ cần xác minh parameter tồn tại, dùng JSONPath filter hoặc parse document rồi tìm theo name thay vì phụ thuộc index cố định.

Test thêm các response code, schema và security requirement quan trọng để phát hiện annotation bị bỏ qua.

## 33. Các trường hợp cần review thủ công

Một script thay tên annotation có thể xử lý phần lớn import đơn giản, nhưng các trường hợp sau cần người review:

- @ApiOperation.responseContainer.
- @ApiOperation.response và generic return type.
- @ApiParam đặt trên request body.
- @ApiImplicitParam cho header authentication.
- @Authorization và OAuth scopes.
- @ApiModel.subTypes và discriminator.
- @ApiModelProperty.position.
- allowEmptyValue, nullable và empty string.
- Response headers và examples.
- Annotation đặt trên interface hoặc base controller.
- Annotation kết hợp với custom composed annotation.

Đặc biệt, responseContainer List/Set cần được chuyển sang schema array đúng cách. Nếu return type đã là List<OrderResponse>, không cần giữ annotation cũ chỉ để khai báo List lần nữa.

## 34. Quy trình migration theo từng bước

Một quy trình có thể áp dụng:

1. Liệt kê toàn bộ annotation Swagger 2 và dependency liên quan.
2. Xác định Spring Boot, Spring MVC/WebFlux và springdoc version mục tiêu.
3. Loại dependency Springfox và Swagger 2 sau khi xác nhận không còn module sử dụng.
4. Thêm springdoc starter phù hợp.
5. Đổi import sang io.swagger.v3.oas.annotations.
6. Chuyển @Api thành @Tag.
7. Chuyển @ApiOperation thành @Operation.
8. Chuyển @ApiParam và implicit params thành @Parameter/@Parameters.
9. Chuyển model annotation thành @Schema.
10. Chuyển response code/message/schema sang @ApiResponse.
11. Chuyển authorization thành security scheme và requirement.
12. Rà các thuộc tính không có ánh xạ trực tiếp.
13. Build và xử lý import conflict.
14. Tải /v3/api-docs và kiểm tra JSON.
15. Chạy integration/contract test.
16. So sánh spec trước và sau để tìm thay đổi ngoài dự kiến.

Thực hiện theo từng nhóm controller hoặc module giúp review diff dễ hơn, nhất là khi codebase có nhiều annotation lồng nhau.

## 35. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| @Api cũ không tạo tag | springdoc đọc @Tag trong package OpenAPI 3 |
| Summary bị mất | Dùng value thay vì summary |
| Description bị mất | Dùng notes thay vì description |
| operationId thay đổi | Chưa chuyển nickname sang operationId |
| Parameter không hiện | Import @Parameter sai package hoặc parameter bị ẩn |
| Header auth hiện như query/header thường | Dùng Parameter thay cho SecurityScheme |
| Response schema sai | Chuyển response trực tiếp nhưng không khai báo content/schema phù hợp |
| List response thành object | Chưa mô tả array schema hoặc return type không đủ rõ |
| 404 không xuất hiện | Chưa đổi code/message thành responseCode/description |
| Nullable sai | Nhầm null với chuỗi rỗng hoặc allowEmptyValue |
| Model property order thay đổi | position không có mapping trực tiếp |
| Swagger UI không hiển thị scheme | SecurityRequirement tham chiếu name không tồn tại |
| Annotation mới compile nhưng output không đổi | Controller có import Swagger 2 cũ |
| Test vẫn gọi /v2/api-docs | Chưa cập nhật endpoint sang /v3/api-docs |
| IDE tự thêm import cũ | Dependency Swagger 2 còn trên classpath |

## 36. Checklist hoàn tất migration

- [ ] Đã chọn đúng springdoc starter theo Spring MVC hoặc WebFlux.
- [ ] Đã loại dependency Springfox không còn dùng.
- [ ] Đã loại swagger-annotations 1.x khỏi code đã migrate.
- [ ] Import mới dùng io.swagger.v3.oas.annotations.
- [ ] @Api đã chuyển thành @Tag.
- [ ] @ApiOperation đã chuyển thành @Operation.
- [ ] @ApiParam đã chuyển thành @Parameter.
- [ ] @ApiImplicitParam và @ApiImplicitParams đã được chuyển đúng.
- [ ] @ApiModel và @ApiModelProperty đã chuyển thành @Schema.
- [ ] @ApiResponse code/message đã chuyển thành responseCode/description.
- [ ] Response schema và array schema khớp kiểu trả về.
- [ ] Security scheme và requirement đã được định nghĩa riêng.
- [ ] Hidden controller/operation/parameter dùng đúng phạm vi.
- [ ] Required, nullable và empty string đã được phân biệt.
- [ ] Các thuộc tính không có mapping trực tiếp đã được review.
- [ ] Đã cập nhật endpoint /v2/api-docs sang /v3/api-docs ở test và CI.
- [ ] Đã kiểm tra JSON OpenAPI thực tế.
- [ ] Đã chạy integration test và contract validation.
- [ ] Đã review diff trước/sau migration.

## 37. Nguồn tra cứu

- [springdoc-openapi – Migrating from SpringFox](https://springdoc.org/migrating-from-springfox.html)
- [springdoc-openapi v2 – Migrating from SpringFox](https://springdoc.org/v2/#migrating-from-springfox)
- [Swagger Core – Swagger 2.x Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations)
- [Swagger Core – OpenAPI 3 Annotations](https://github.com/swagger-api/swagger-core/wiki/Annotations)
- [Swagger Core – Operation annotation API](https://docs.swagger.io/swagger-core/v2.2.34/apidocs/io/swagger/v3/oas/annotations/Operation.html)
- [Swagger Core – ApiResponse annotation API](https://github.com/swagger-api/swagger-core/blob/master/modules/swagger-annotations/src/main/java/io/swagger/v3/oas/annotations/responses/ApiResponse.java)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)

Migration đúng là chuyển ý nghĩa annotation, không chỉ đổi tên class. @Tag tổ chức controller, @Operation mô tả operation, @Parameter mô tả tham số và @Schema mô tả dữ liệu; response và security cần được khai báo theo mô hình OpenAPI 3. Hãy tận dụng thông tin Spring MVC có thể tự suy ra, review những thuộc tính không có ánh xạ trực tiếp và xác minh tài liệu JSON cuối cùng trước khi hoàn tất migration.
