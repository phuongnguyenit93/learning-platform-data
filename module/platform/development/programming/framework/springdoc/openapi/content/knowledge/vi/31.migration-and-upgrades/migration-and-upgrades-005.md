# Đổi annotation response hoặc hidden đúng package và ngữ cảnh

Khi chuyển API từ SpringFox/Swagger 2 sang springdoc-openapi/OpenAPI 3, hai nhóm annotation thường gây lỗi import hoặc mô tả sai là **response** và **hidden**. Tên annotation có thể gần giống nhau, nhưng package, thuộc tính và phạm vi áp dụng không hoàn toàn giống nhau.

Với OpenAPI 3, annotation mô tả response là **io.swagger.v3.oas.annotations.responses.ApiResponse**; annotation ẩn tài nguyên là **io.swagger.v3.oas.annotations.Hidden**. Chọn annotation theo đúng đối tượng cần mô tả: response của operation, toàn bộ controller, một operation, một parameter hay một schema property.

Một điểm cần phân biệt xuyên suốt bài: annotation Swagger mô tả hợp đồng trong OpenAPI document. Các annotation Spring như **@ResponseStatus** và **ResponseEntity** mới điều khiển HTTP response thực tế của controller.

## 1. Nhận diện đúng package annotation

Các annotation OpenAPI 3 thường dùng trong controller Spring:

| Annotation | Package đúng | Mục đích |
| --- | --- | --- |
| @ApiResponse | io.swagger.v3.oas.annotations.responses.ApiResponse | Mô tả một mã và nội dung response |
| @ApiResponses | io.swagger.v3.oas.annotations.responses.ApiResponses | Gom nhiều response cho operation |
| @Operation | io.swagger.v3.oas.annotations.Operation | Mô tả operation và metadata của nó |
| @Hidden | io.swagger.v3.oas.annotations.Hidden | Ẩn controller, method hoặc bean khỏi tài liệu |
| @Parameter | io.swagger.v3.oas.annotations.Parameter | Mô tả parameter; có thể ẩn một parameter |
| @Content | io.swagger.v3.oas.annotations.media.Content | Mô tả media type và schema của nội dung |
| @Schema | io.swagger.v3.oas.annotations.media.Schema | Mô tả hoặc ẩn schema/model/property |

Không nhầm @Parameter với @RequestBody: @Parameter nằm ở package gốc io.swagger.v3.oas.annotations, còn annotation OpenAPI @RequestBody nằm trong io.swagger.v3.oas.annotations.parameters. Spring cũng có org.springframework.web.bind.annotation.RequestBody để bind HTTP body vào tham số Java.

Hai package cần nhớ nhất cho đề bài:

~~~java
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.Hidden;
~~~

@ApiResponse không nằm trong io.swagger.v3.oas.annotations trực tiếp. @Hidden không nằm trong package responses, media hoặc package nội bộ org.springdoc.

## 2. Phân biệt Swagger 2 ApiResponse và OpenAPI 3 ApiResponse

Trong Swagger 2/SpringFox, annotation thường được import từ:

~~~java
import io.swagger.annotations.ApiResponse;
import io.swagger.annotations.ApiResponses;
~~~

Ví dụ cũ:

~~~java
@ApiResponses({
    @ApiResponse(code = 201, message = "Created"),
    @ApiResponse(code = 400, message = "Invalid request")
})
~~~

Khi chuyển sang OpenAPI 3, dùng package và thuộc tính mới:

~~~java
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;

@ApiResponses({
    @ApiResponse(responseCode = "201", description = "Created"),
    @ApiResponse(responseCode = "400", description = "Invalid request")
})
~~~

Các khác biệt cần chú ý:

| Swagger 2 | OpenAPI 3 |
| --- | --- |
| io.swagger.annotations.ApiResponse | io.swagger.v3.oas.annotations.responses.ApiResponse |
| code = 201 là số nguyên | responseCode = "201" là chuỗi |
| message = "Created" | description = "Created" |
| response = Order.class | content = @Content(schema = @Schema(implementation = Order.class)) |
| responseContainer | Mô tả cấu trúc bằng schema/array schema phù hợp |

Không chỉ sửa tên package rồi giữ nguyên thuộc tính cũ. OpenAPI 3 dùng responseCode, description và content để mô tả response. Thuộc tính response của Swagger 2 không còn là cách khai báo schema trong annotation OpenAPI 3.

## 3. Khai báo một response bằng @ApiResponse

@ApiResponse mô tả một response có thể xuất hiện khi operation được gọi. Các thông tin thường cần khai báo gồm:

- responseCode: mã HTTP dạng chuỗi, ví dụ "200", "201", "400", "404" hoặc "default".
- description: ý nghĩa của response.
- content: media type và schema của response body.
- headers: các response header nếu cần mô tả.
- ref: tham chiếu response component dùng chung khi phù hợp.

Ví dụ response JSON thành công:

~~~java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;

@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Lấy đơn hàng thành công",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Không tìm thấy đơn hàng"
    )
})
~~~

@Schema(implementation = OrderResponse.class) cho biết response body có cấu trúc theo model OrderResponse. Nếu controller trả nhiều kiểu nội dung, khai báo từng media type tương ứng trong content.

Khi method trả về DTO mà springdoc đã suy luận đúng schema, không cần lặp lại metadata cho response thành công chỉ để khai báo lại kiểu trả về. Hãy bổ sung @ApiResponse khi cần mô tả rõ mã trạng thái, mô tả nghiệp vụ, response lỗi, header hoặc nội dung đặc biệt.

## 4. Khai báo nhiều response bằng @ApiResponses

@ApiResponses là container để gom nhiều @ApiResponse trên một operation. Annotation @ApiResponse của swagger-annotations OpenAPI 3 cũng là repeatable, nhưng wrapper giúp nhóm các mã response dễ đọc và dễ rà soát.

Ví dụ endpoint tạo đơn hàng:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;

@PostMapping("/api/orders")
@ResponseStatus(HttpStatus.CREATED)
@Operation(summary = "Tạo đơn hàng")
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Đơn hàng được tạo",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Dữ liệu yêu cầu không hợp lệ",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiErrorResponse.class)
        )
    )
})
public OrderResponse createOrder(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Trong ví dụ này:

- @Operation mô tả operation.
- @ApiResponses liệt kê các response có thể xảy ra.
- @ResponseStatus(HttpStatus.CREATED) đặt HTTP status thực tế cho đường chạy thành công của method.
- @RequestBody ở đây là annotation Spring MVC để bind JSON request body, không phải annotation OpenAPI parameters.RequestBody.

Các kiểu OrderResponse, ApiErrorResponse, CreateOrderRequest và orderService là model/service của ứng dụng.

Có thể đặt @ApiResponse trực tiếp trong @Operation.responses:

~~~java
@Operation(
    summary = "Lấy đơn hàng theo mã",
    responses = {
        @ApiResponse(
            responseCode = "200",
            description = "Thành công",
            content = @Content(
                schema = @Schema(implementation = OrderResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Không tìm thấy"
        )
    }
)
~~~

Chọn một cách khai báo nhất quán cho từng operation. Tránh khai báo cùng một mã response nhiều lần ở cả @Operation.responses và @ApiResponses nếu không có chủ đích, vì tài liệu có thể khó đọc hoặc bị ghi đè khi tổng hợp.

## 5. Mô tả response không đồng nghĩa điều khiển HTTP status

Đây là nhầm lẫn phổ biến khi đổi annotation response. @ApiResponse chỉ mô tả OpenAPI document. Nó không tự đặt HTTP status khi controller chạy.

Ngược lại, @ResponseStatus thuộc Spring MVC:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.CREATED)
~~~

Annotation này yêu cầu Spring đặt status cho response khi handler được gọi. Một lựa chọn khác là trả ResponseEntity:

~~~java
return ResponseEntity
    .status(HttpStatus.CREATED)
    .body(orderResponse);
~~~

So sánh:

| Thành phần | Vai trò | Có trực tiếp điều khiển response runtime? |
| --- | --- | --- |
| @ApiResponse(responseCode = "201") | Ghi tài liệu response 201 trong OpenAPI | Không |
| @ResponseStatus(HttpStatus.CREATED) | Đặt status cho response của handler | Có |
| ResponseEntity.status(...).body(...) | Đặt status, header và body khi trả response | Có |
| @Operation | Mô tả operation | Không |

Nếu tài liệu ghi 201 nhưng controller thực tế trả 200, OpenAPI đang mô tả sai hành vi. Nếu controller trả 201 nhưng tài liệu chỉ ghi 200, client generator và người đọc tài liệu cũng nhận hợp đồng sai. Cần đồng bộ cả hai lớp.

Không thay @ResponseStatus bằng @ApiResponse, và cũng không thêm @ResponseStatus chỉ vì đã khai báo responseCode. Chọn cách điều khiển HTTP phù hợp với implementation, rồi mô tả kết quả đó bằng OpenAPI.

## 6. Response không có body

Với endpoint trả 204 No Content, mô tả response không có nội dung:

~~~java
@ApiResponse(
    responseCode = "204",
    description = "Đã xóa đơn hàng",
    content = @Content
)
~~~

Không khai báo schema body cho response 204 nếu server thực sự không gửi body. Nếu endpoint trả body JSON, hãy khai báo media type và schema tương ứng thay vì mô tả như response rỗng.

Tương tự, response 404 có thể chỉ có mô tả nếu API thực sự không gửi body. Nếu ứng dụng trả ProblemDetail hoặc ApiErrorResponse, hãy khai báo schema lỗi để client biết cấu trúc dữ liệu.

## 7. Chọn đúng package khi đổi @Hidden

Trong SpringFox, annotation thường dùng để bỏ qua tài nguyên là:

~~~java
import springfox.documentation.annotations.ApiIgnore;
~~~

Với springdoc/OpenAPI 3, annotation @Hidden nằm tại:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
~~~

Không có package io.swagger.v3.oas.annotations.responses.Hidden. @Hidden không phải annotation response; nó đánh dấu resource, class, method hoặc bean type không đưa vào quá trình đọc/tạo tài liệu.

Có thể dùng fully qualified name để tránh import nhầm:

~~~java
@io.swagger.v3.oas.annotations.Hidden
~~~

FAQ của springdoc xác nhận có thể dùng @Hidden ở @RestController, @RestControllerAdvice và method level. Với operation cụ thể, @Operation(hidden = true) cũng là lựa chọn phù hợp.

## 8. Chọn hidden theo đúng phạm vi

Không nên thay mọi @ApiIgnore bằng một @Hidden duy nhất. Trước hết xác định đối tượng cũ cần ẩn:

| Đối tượng cần ẩn | Annotation OpenAPI 3 phù hợp |
| --- | --- |
| Toàn bộ controller/resource | @Hidden trên class |
| Toàn bộ @RestControllerAdvice khỏi tài liệu | @Hidden trên class advice |
| Một method/operation | @Hidden trên method hoặc @Operation(hidden = true) |
| Một parameter | @Parameter(hidden = true) |
| Một field/property trong model | @Schema(hidden = true) |
| Schema của một response cụ thể | @Schema(hidden = true) trong @Content của response đó, nếu chủ đích là không công bố schema body |

Các annotation có phạm vi khác nhau. Ẩn một parameter không ẩn operation. Ẩn một schema property không ẩn endpoint. Ẩn controller sẽ loại tất cả operation thuộc controller đó khỏi tài liệu.

## 9. Ẩn toàn bộ controller

Khi một controller là nội bộ và không nên xuất hiện trong OpenAPI document, đặt @Hidden ở cấp class:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Hidden
@RestController
@RequestMapping("/internal/maintenance")
class MaintenanceController {

    // Các endpoint nội bộ không được đưa vào OpenAPI document.
}
~~~

Đặt annotation trên class để áp dụng cho toàn bộ controller. Không cần lặp lại trên từng method nếu tất cả endpoint trong class đều cần ẩn.

Lưu ý: @Hidden chỉ ẩn tài liệu. Endpoint vẫn có thể được Spring đăng ký và truy cập qua HTTP. Nếu route nội bộ cần bảo vệ, phải cấu hình Spring Security, network policy hoặc cơ chế authorization tương ứng.

## 10. Ẩn một operation nhưng giữ các operation khác

Nếu controller có cả API công khai và endpoint chẩn đoán nội bộ, chỉ ẩn method cần thiết:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/api/orders")
    public List<OrderResponse> listOrders() {
        return orderService.findAll();
    }

    @GetMapping("/internal/order-cache")
    @Operation(hidden = true)
    public Map<String, Integer> inspectCache() {
        return orderService.cacheStatistics();
    }
}
~~~

Trong trường hợp này, operation /api/orders vẫn xuất hiện trong OpenAPI; operation /internal/order-cache bị ẩn. Có thể dùng @Hidden trực tiếp trên method:

~~~java
@Hidden
@GetMapping("/internal/order-cache")
public Map<String, Integer> inspectCache() {
    return orderService.cacheStatistics();
}
~~~

@Operation(hidden = true) làm rõ ý định ở cấp Operation Object. @Hidden phù hợp khi muốn đánh dấu method/resource không tham gia quá trình đọc tài liệu. Hãy chọn một cách và giữ nhất quán trong module.

## 11. Ẩn parameter khỏi tài liệu

Một method có thể nhận parameter phục vụ Spring Security hoặc infrastructure nhưng không phải tham số mà client gửi qua HTTP. Ví dụ @AuthenticationPrincipal được Spring inject từ security context.

~~~java
import io.swagger.v3.oas.annotations.Parameter;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/me")
public UserResponse getCurrentUser(
    @Parameter(hidden = true)
    @AuthenticationPrincipal CurrentUser currentUser
) {
    return userService.toResponse(currentUser);
}
~~~

Ở đây chỉ parameter currentUser bị ẩn. Operation /api/me vẫn xuất hiện và các query/path parameter khác vẫn được mô tả.

Không dùng @Hidden trên method nếu chỉ muốn ẩn một parameter. Nếu đặt @Hidden lên method, toàn bộ operation có thể bị loại khỏi tài liệu.

## 12. Ẩn field hoặc property của schema

Nếu model chứa field nội bộ mà không nên xuất hiện trong OpenAPI schema, dùng @Schema(hidden = true):

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

public record UserResponse(
    String id,
    String displayName,
    @Schema(hidden = true)
    String internalRiskScore
) {}
~~~

Annotation này áp dụng vào property của schema. Nó không ẩn toàn bộ endpoint và không tự loại field khỏi JSON serialization của Jackson.

Nếu field cũng không được gửi ra JSON runtime, cần cấu hình model/serializer phù hợp, ví dụ @JsonIgnore hoặc DTO response riêng. @Schema(hidden = true) chỉ tác động tài liệu OpenAPI; @JsonIgnore tác động quá trình Jackson serialize/deserialize.

## 13. Ẩn schema của một response cụ thể

Springdoc FAQ có ví dụ dùng @Schema(hidden = true) bên trong @Content khi muốn ẩn response schema:

~~~java
@Operation(
    responses = @ApiResponse(
        responseCode = "200",
        description = "Thành công",
        content = @Content(
            schema = @Schema(hidden = true)
        )
    )
)
~~~

Đây là trường hợp ẩn schema body của response. Nó khác với:

- @Operation(hidden = true): ẩn toàn bộ operation.
- @Hidden trên controller: ẩn toàn bộ controller.
- @Parameter(hidden = true): ẩn parameter.

Chỉ dùng cách này khi chủ đích không công bố cấu trúc response body. Nếu client cần biết JSON response để tích hợp, hãy mô tả schema thay vì ẩn nó.

## 14. Ẩn ControllerAdvice và exception handler

Springdoc có thể đọc @ControllerAdvice để tổng hợp response lỗi vào tài liệu. Nếu một advice chỉ phục vụ xử lý nội bộ hoặc không nên đóng góp response vào OpenAPI, có thể đặt @Hidden trên class:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.ControllerAdvice;

@Hidden
@ControllerAdvice
class InternalExceptionAdvice {
    // Exception handlers nội bộ.
}
~~~

Nếu chỉ một exception handler không nên được tính vào generic error responses, đặt @Hidden ở method handler tương ứng. FAQ springdoc ghi rõ annotation trên exception handler được xem xét khi xây dựng generic responses từ @ControllerAdvice.

Không ẩn toàn bộ advice nếu những response lỗi mà API công khai cần mô tả đang được sinh từ cùng advice đó. Kiểm tra OpenAPI document sau khi thay đổi để bảo đảm các response lỗi công khai vẫn có mặt.

## 15. Ánh xạ @ApiIgnore sang annotation OpenAPI 3

@ApiIgnore trong code cũ có thể đã được dùng ở nhiều vị trí. Khi chuyển đổi, hãy đọc vị trí và mục đích trước:

| Vị trí @ApiIgnore cũ | Thay thế đề xuất |
| --- | --- |
| Trên controller | @Hidden trên class |
| Trên method/operation | @Hidden trên method hoặc @Operation(hidden = true) |
| Trên parameter | @Parameter(hidden = true) |

Ví dụ cũ:

~~~java
@ApiIgnore
@RestController
class InternalController {
}
~~~

Sau chuyển đổi:

~~~java
@Hidden
@RestController
class InternalController {
}
~~~

Ví dụ cũ ẩn parameter:

~~~java
public UserResponse currentUser(@ApiIgnore CurrentUser user) {
    // ...
}
~~~

Sau chuyển đổi:

~~~java
public UserResponse currentUser(
    @Parameter(hidden = true) CurrentUser user
) {
    // ...
}
~~~

Không chuyển máy móc tất cả vị trí thành @Hidden. Làm như vậy có thể vô tình ẩn cả endpoint trong khi chỉ cần ẩn một parameter.

Lưu ý: SpringFox @ApiIgnore chỉ nhắm đến method, type và parameter. Nếu code cũ dùng @ApiModelProperty(hidden = true) để ẩn một model property, chuyển riêng trường hợp đó thành @Schema(hidden = true); đây là phép chuyển từ annotation mô tả model property, không phải từ @ApiIgnore.

## 16. Phân biệt migration SpringFox sang springdoc và springdoc v1 sang v2

Hai quá trình nâng cấp này thường bị gộp nhầm:

**SpringFox/Swagger 2 sang springdoc/OpenAPI 3:** đổi hệ annotation từ Swagger 2 sang Swagger 3. Ví dụ @ApiResponse chuyển sang package io.swagger.v3.oas.annotations.responses, @ApiIgnore được thay bằng annotation hidden theo phạm vi, @ApiOperation chuyển thành @Operation.

**springdoc v1 sang springdoc v2:** springdoc thay đổi tên starter/module và một số class/annotation nội bộ. Các annotation Swagger 3 như @ApiResponse và @Hidden vẫn thuộc package io.swagger.v3.oas.annotations...; không đổi sang package org.springdoc.

Một số package springdoc nội bộ đã thay đổi giữa v1 và v2:

| springdoc v1 | springdoc v2 |
| --- | --- |
| org.springdoc.api.annotations.ParameterObject | org.springdoc.core.annotations.ParameterObject |
| org.springdoc.core.GroupedOpenApi | org.springdoc.core.models.GroupedOpenApi |
| org.springdoc.core.customizers.OpenApiCustomiser | org.springdoc.core.customizers.OpenApiCustomizer |
| org.springdoc.core.SpringDocUtils | org.springdoc.core.utils.SpringDocUtils |
| org.springdoc.core.Constants | org.springdoc.core.utils.Constants |
| org.springdoc.core.SwaggerUiConfigParameters | org.springdoc.core.properties.SwaggerUiConfigParameters |

Đừng áp dụng các thay đổi package nội bộ này cho @ApiResponse, @ApiResponses, @Hidden, @Operation, @Parameter hoặc @Schema. Chúng là annotation swagger-core, không phải class nội bộ springdoc.

## 17. Cập nhật starter khi nâng springdoc v1 lên v2

Springdoc v2 được thiết kế cho Spring Boot 3.x. Các starter/module cũng được đổi tên:

| springdoc v1 | springdoc v2 |
| --- | --- |
| springdoc-openapi-ui | springdoc-openapi-starter-webmvc-ui |
| springdoc-openapi-webflux-ui | springdoc-openapi-starter-webflux-ui |
| springdoc-openapi-webmvc-core | springdoc-openapi-starter-webmvc-api |
| springdoc-openapi-webflux-core | springdoc-openapi-starter-webflux-api |
| springdoc-openapi-common | springdoc-openapi-starter-common |

Ví dụ Maven cho ứng dụng Spring MVC cần Swagger UI:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

Nếu chỉ cần endpoint OpenAPI mà không cần Swagger UI, dùng starter API phù hợp với stack. Với WebFlux, chọn starter WebFlux tương ứng. Không thêm starter MVC và WebFlux cùng lúc nếu ứng dụng chỉ chạy một stack web.

Khi nâng từ Spring Boot 2 lên Spring Boot 3, còn cần xử lý các thay đổi Spring Framework 6/Jakarta như package javax.* sang jakarta.* đối với API Java EE tương ứng. Việc đổi package Jakarta không làm thay đổi package annotation swagger-core.

## 18. Tránh import nhầm ApiResponse model và annotation

Ngoài annotation, swagger-core còn có model class cùng tên:

~~~java
io.swagger.v3.oas.annotations.responses.ApiResponse
io.swagger.v3.oas.models.responses.ApiResponse
~~~

Hai kiểu này có mục đích khác nhau:

| Kiểu | Là gì? | Dùng ở đâu? |
| --- | --- | --- |
| io.swagger.v3.oas.annotations.responses.ApiResponse | Java annotation | Gắn lên controller method/type hoặc bên trong @Operation |
| io.swagger.v3.oas.models.responses.ApiResponse | OpenAPI model object | Tạo/chỉnh sửa response bằng Java code trong customizer/bean |

Nếu file Java cần dùng cả hai kiểu, Java không cho import hai class cùng simple name. Hãy import kiểu được dùng thường xuyên và viết fully qualified name cho kiểu còn lại:

~~~java
import io.swagger.v3.oas.annotations.responses.ApiResponse;

io.swagger.v3.oas.models.responses.ApiResponse responseModel =
    new io.swagger.v3.oas.models.responses.ApiResponse()
        .description("Thành công");
~~~

Tương tự, đừng nhầm @ApiResponse với Spring @ResponseStatus. Hai annotation có tên gần nhau nhưng package và trách nhiệm hoàn toàn khác nhau.

## 19. Kiểm tra dependency và import cũ

Nếu code không biên dịch hoặc annotation không được springdoc nhận diện:

1. Kiểm tra import ở đầu file controller và DTO.
2. Tìm các import io.swagger.annotations.* còn sót từ Swagger 2.
3. Kiểm tra dependency tree để phát hiện springfox hoặc swagger-annotations phiên bản cũ còn trong classpath.
4. Đảm bảo starter springdoc phù hợp với Spring MVC/WebFlux và Spring Boot đang dùng.
5. Dùng annotation Swagger 3 được starter cung cấp; tránh trộn annotation Swagger 2 và OpenAPI 3 trên cùng controller.

Một số dấu hiệu nhận biết:

| Lỗi | Nguyên nhân thường gặp |
| --- | --- |
| responseCode không tồn tại | Đang import Swagger 2 io.swagger.annotations.ApiResponse |
| code hoặc message không tồn tại | Đang import OpenAPI 3 ApiResponse nhưng còn dùng thuộc tính Swagger 2 |
| Không tìm thấy @Hidden | Import sai package hoặc thiếu swagger-annotations tương thích |
| @Hidden không ẩn parameter như mong đợi | Dùng annotation ở sai scope; dùng @Parameter(hidden = true) |
| Endpoint biến mất hoàn toàn | Đặt @Hidden ở cấp controller thay vì parameter/operation |
| Tài liệu ghi 201 nhưng request trả 200 | Chỉ khai báo @ApiResponse, chưa cấu hình runtime status |
| Schema response biến mất | Dùng @Schema(hidden = true) ở response content hoặc DTO ngoài ý muốn |

## 20. Kiểm thử response và hidden trong OpenAPI document

Sau khi đổi annotation, kiểm tra JSON mà springdoc sinh ra. Mặc định endpoint thường là /v3/api-docs.

Ví dụ kiểm tra response 201:

~~~bash
curl --fail --silent --show-error http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/orders"].post.responses'
~~~

Kiểm tra operation bị ẩn không còn trong document:

~~~bash
curl --fail --silent --show-error http://localhost:8080/v3/api-docs \
  | jq '.paths | keys'
~~~

Có thể viết integration test bằng MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiAnnotationMigrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentsCreatedResponseAndHidesInternalOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.paths['/api/orders'].post.responses['201'].description"
            ).value("Đơn hàng được tạo"))
            .andExpect(jsonPath(
                "$.paths['/internal/maintenance']"
            ).doesNotExist());
    }
}
~~~

Nếu chỉ ẩn parameter, kiểm tra operation vẫn tồn tại và parameter đó không xuất hiện trong parameters. Nếu chỉ ẩn schema property, kiểm tra endpoint và các property công khai khác vẫn được sinh.

Đồng thời kiểm tra HTTP runtime riêng:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"customerId":"c-100"}
            """))
    .andExpect(status().isCreated());
~~~

Test tài liệu xác minh @ApiResponse; test runtime xác minh Spring trả đúng status và body. Không gộp hai mục tiêu thành một assertion.

## 21. Những lỗi thường gặp khi migrate

**Giữ import io.swagger.annotations.ApiResponse.** Đây là Swagger 2. Thay bằng io.swagger.v3.oas.annotations.responses.ApiResponse.

**Đặt @Hidden trong package responses.** @Hidden nằm ở package gốc io.swagger.v3.oas.annotations.

**Dùng @Hidden để ẩn một parameter.** Chọn @Parameter(hidden = true) để giữ operation hiển thị.

**Dùng @Operation(hidden = true) trên controller class.** Annotation này dành cho operation method. Để ẩn cả controller, dùng @Hidden trên class.

**Thay mọi @ApiIgnore bằng @Hidden.** Hãy xác định annotation cũ được đặt trên class, method, parameter hay property; chọn annotation tương ứng.

**Dùng @ApiResponse(code = 201, message = "...") trong OpenAPI 3.** Đổi thành responseCode = "201" và description = "...".

**Dùng @ApiResponse để ép HTTP status thành 201.** Cấu hình @ResponseStatus hoặc ResponseEntity ở runtime.

**Đổi response annotation nhưng quên content schema.** Nếu body có JSON/XML model cần công bố, mô tả content và schema.

**Ẩn schema bằng @Schema(hidden = true) dù client cần đọc response.** Chỉ ẩn khi chủ đích không công bố cấu trúc body; nếu không, giữ schema công khai.

**Nâng springdoc v1 lên v2 nhưng chuyển mọi annotation sang package org.springdoc.** Chỉ các class nội bộ springdoc trong migration guide mới đổi package; annotation swagger-core vẫn dùng io.swagger.v3.oas.annotations.

**Endpoint bị ẩn nhưng vẫn truy cập được và cho rằng @Hidden không hoạt động.** @Hidden chỉ tác động tài liệu, không phải cơ chế bảo mật route.

## 22. Checklist trước khi hoàn tất migration

- [ ] Dùng io.swagger.v3.oas.annotations.responses.ApiResponse.
- [ ] Dùng io.swagger.v3.oas.annotations.responses.ApiResponses.
- [ ] Dùng responseCode dạng chuỗi và description, không dùng code/message của Swagger 2.
- [ ] Mô tả response body bằng content và @Schema(implementation = ...) khi cần.
- [ ] Dùng io.swagger.v3.oas.annotations.Hidden đúng package.
- [ ] Chọn @Hidden, @Operation(hidden = true), @Parameter(hidden = true) hoặc @Schema(hidden = true) theo đúng phạm vi.
- [ ] Phân biệt annotation OpenAPI với @ResponseStatus và ResponseEntity.
- [ ] Không nhầm annotation ApiResponse với model io.swagger.v3.oas.models.responses.ApiResponse.
- [ ] Loại bỏ import Swagger 2 cũ còn sót.
- [ ] Khi nâng springdoc v1 lên v2, cập nhật starter và chỉ đổi các package nội bộ được liệt kê trong migration guide.
- [ ] Kiểm tra OpenAPI JSON sau khi build.
- [ ] Kiểm tra HTTP status/body thực tế bằng integration test riêng.
- [ ] Xác minh endpoint bị ẩn vẫn được bảo vệ bằng security nếu đó là endpoint nội bộ.

## 23. Kết luận

Khi migrate annotation response, dùng io.swagger.v3.oas.annotations.responses.ApiResponse và khai báo responseCode, description, content theo OpenAPI 3. Khi migrate annotation ignore, chọn @Hidden cho resource/controller hoặc method, @Operation(hidden = true) cho operation, @Parameter(hidden = true) cho parameter và @Schema(hidden = true) cho property/schema. Đừng nhầm annotation mô tả response với @ResponseStatus điều khiển HTTP thật. Cuối cùng, kiểm tra import, starter, OpenAPI JSON và runtime response để bảo đảm tài liệu phản ánh đúng ứng dụng.

## 24. Nguồn tham khảo

- [springdoc-openapi — Migrating from v1 to v2](https://springdoc.org/v2/migrating-from-springdoc-v1.html): các module, class và package nội bộ thay đổi giữa springdoc v1 và v2.
- [springdoc-openapi — Migrating from SpringFox](https://springdoc.org/v1/migrating-from-springfox.html): ánh xạ annotation Swagger 2 sang OpenAPI 3, gồm @ApiResponse và @ApiIgnore.
- [springdoc-openapi v2 — Migrating from SpringFox](https://springdoc.org/v2/migrating-from-springfox.html): ánh xạ annotation Swagger 2 sang OpenAPI 3 cho Spring Boot 3.
- [SpringFox — ApiIgnore Javadoc](https://springfox.github.io/springfox/javadoc/current/springfox/documentation/annotations/ApiIgnore.html): package và các target method, type, parameter của @ApiIgnore.
- [springdoc-openapi v2 FAQ — Hide operation/controller](https://springdoc.org/v2/faq.html): phạm vi dùng @Hidden, @Operation(hidden = true) và @Parameter(hidden = true).
- [springdoc-openapi v2 FAQ — Hide response schema](https://springdoc.org/v2/faq.html): ví dụ @Schema(hidden = true) trong response content.
- [swagger-core — ApiResponse annotation](https://docs.swagger.io/swagger-core/v2.2.27/apidocs/io/swagger/v3/oas/annotations/responses/ApiResponse.html): package, thuộc tính responseCode/description/content và phạm vi annotation.
- [swagger-core — Hidden annotation](https://docs.swagger.io/swagger-core/v2.2.27/apidocs/io/swagger/v3/oas/annotations/Hidden.html): package và phạm vi áp dụng của @Hidden.
- [Spring Framework — ResponseStatus](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/ResponseStatus.html): tác động runtime của @ResponseStatus.
