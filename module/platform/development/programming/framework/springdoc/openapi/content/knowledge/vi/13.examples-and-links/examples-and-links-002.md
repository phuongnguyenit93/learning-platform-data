# Ví dụ ở cấp tham số, schema và request hoặc response

Ví dụ giúp người dùng API hiểu dữ liệu cần gửi hoặc sẽ nhận. Một schema có thể mô tả chính xác kiểu, field và ràng buộc nhưng vẫn khó hiểu nếu thiếu giá trị minh họa. Với `springdoc-openapi`, có thể bổ sung ví dụ ở nhiều cấp: tham số, thuộc tính model, request body và response body.

Điều quan trọng là đặt ví dụ đúng vị trí. Ví dụ của query parameter mô tả một giá trị client gửi trong URL; ví dụ của schema minh họa một field hoặc model; ví dụ của request/response content mô tả cả payload gắn với media type. Những ví dụ này được xuất vào OpenAPI để Swagger UI và các công cụ khác trình bày, nhưng không tự thay đổi validation hoặc hành vi của controller.

## 1. Phân biệt schema, example và default

Ba khái niệm thường bị nhầm lẫn:

| Thành phần | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Schema | Dữ liệu có hình dạng và ràng buộc nào? | `email` là chuỗi có format `email`; `quantity` là số nguyên tối thiểu bằng 1. |
| Example | Một giá trị mẫu hợp lệ trông như thế nào? | `"support@example.com"`, `3`. |
| Default | Giá trị nào được dùng khi client không cung cấp, theo hợp đồng hoặc cơ chế của ứng dụng? | Query parameter `page` mặc định bằng `0`. |

Ví dụ không phải là quy tắc validation. Nếu schema cho phép `quantity` từ 1 đến 100 nhưng ví dụ minh họa là `0`, tài liệu trở nên mâu thuẫn. Tương tự, đặt `example = "PENDING"` không làm server tự động từ chối giá trị enum khác; tập giá trị phải được mô tả bằng schema `enum` và thực thi bằng kiểu Java hoặc validation phù hợp.

## 2. Ví dụ ở cấp tham số

Với một tham số đơn giản, có thể dùng `example` trong `@Parameter`:

```java
@GetMapping("/api/orders")
List<OrderResponse> search(
    @Parameter(
        description = "Mã trạng thái cần lọc",
        example = "PENDING"
    )
    @RequestParam(required = false) OrderStatus status,

    @Parameter(
        description = "Số trang, bắt đầu từ 0",
        example = "0"
    )
    @RequestParam(defaultValue = "0") @Min(0) int page
) {
    return orderService.search(status, page);
}
```

`example` là một giá trị minh họa cho parameter. Springdoc kết hợp nó với thông tin suy ra từ `@RequestParam`, kiểu Java và các annotation khác để tạo Parameter Object trong OpenAPI.

Khi cần nhiều lựa chọn, dùng `examples` với các `@ExampleObject` có tên:

```java
@GetMapping("/api/orders")
List<OrderResponse> search(
    @Parameter(
        name = "status",
        in = ParameterIn.QUERY,
        description = "Trạng thái đơn hàng",
        examples = {
            @ExampleObject(name = "pending", summary = "Đang chờ xử lý", value = "PENDING"),
            @ExampleObject(name = "shipped", summary = "Đã giao cho đơn vị vận chuyển", value = "SHIPPED"),
            @ExampleObject(name = "cancelled", summary = "Đã hủy", value = "CANCELLED")
        }
    )
    @RequestParam(required = false) OrderStatus status
) {
    return orderService.searchByStatus(status);
}
```

Mỗi `ExampleObject` có thể có `name`, `summary`, `description` và `value`. `name` định danh ví dụ; `summary` giúp người đọc chọn đúng trường hợp; `value` chứa giá trị thực tế. Các ví dụ được đặt tên hữu ích khi client có nhiều trường hợp để thử trong Swagger UI.

Với parameter dạng số hoặc ngày giờ, giá trị ví dụ vẫn cần đúng kiểu wire format:

```java
@Parameter(
    description = "Ngày bắt đầu lọc, định dạng yyyy-MM-dd",
    example = "2026-11-01"
)
@RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate from
```

Query parameter được truyền qua URL dưới dạng chuỗi, sau đó Spring chuyển đổi sang kiểu Java. Vì vậy ví dụ ngày giờ cần khớp định dạng mà converter của ứng dụng chấp nhận.

## 3. Ví dụ ở cấp thuộc tính schema

Khi muốn minh họa riêng một field của DTO, dùng `@Schema(example = "...")`:

```java
public record CreateCustomerRequest(
    @Schema(
        description = "Tên hiển thị của khách hàng",
        example = "Nguyen An",
        minLength = 1,
        maxLength = 100
    )
    @NotBlank @Size(max = 100)
    String displayName,

    @Schema(
        description = "Địa chỉ email liên hệ",
        example = "an.nguyen@example.com",
        format = "email"
    )
    @NotBlank @Email
    String email,

    @Schema(
        description = "Số lượng đơn hàng dự kiến",
        example = "3",
        minimum = "1",
        maximum = "100"
    )
    @Min(1) @Max(100)
    Integer expectedOrders
) {}
```

Schema của từng thuộc tính sẽ có kiểu và ràng buộc được suy ra từ Java hoặc annotation. `example` cung cấp một giá trị minh họa nằm trong schema đó. `@NotBlank`, `@Email`, `@Min` và `@Max` mới là constraint validation được thực thi khi ứng dụng kích hoạt Bean Validation.

Ví dụ ở cấp field phù hợp khi một thuộc tính có định dạng dễ nhầm hoặc cần gợi ý ngắn. Nó không thay thế ví dụ hoàn chỉnh của request body: người đọc vẫn có thể cần thấy các field kết hợp với nhau trong một payload.

## 4. Ví dụ cho toàn bộ request body

Khi muốn cung cấp nhiều payload mẫu cho cùng một operation, khai báo `examples` trong `@Content`. Có thể đặt request body OpenAPI ngay trong `@Operation`:

```java
@PostMapping("/api/customers")
@Operation(
    summary = "Tạo khách hàng",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        description = "Thông tin khách hàng cần tạo",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = CreateCustomerRequest.class),
            examples = {
                @ExampleObject(
                    name = "individual",
                    summary = "Khách hàng cá nhân",
                    description = "Tạo khách hàng có tên hiển thị và email liên hệ",
                    value = """
                        {
                          "displayName": "Nguyen An",
                          "email": "an.nguyen@example.com",
                          "expectedOrders": 3
                        }
                        """
                ),
                @ExampleObject(
                    name = "support-contact",
                    summary = "Tài khoản liên hệ hỗ trợ",
                    value = """
                        {
                          "displayName": "Support Team",
                          "email": "support@example.com",
                          "expectedOrders": 10
                        }
                        """
                )
            }
        )
    )
)
ResponseEntity<CustomerResponse> create(
    @Valid @RequestBody CreateCustomerRequest request
) {
    CustomerResponse created = customerService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
```

Ở đây:

- `mediaType` xác định ví dụ áp dụng cho nội dung JSON.
- `schema` chỉ định hình dạng request body là `CreateCustomerRequest`.
- `examples` chứa nhiều trường hợp có tên để người dùng chọn.
- `summary` và `description` giải thích ý nghĩa của từng payload.
- `value` là JSON mẫu; các field và giá trị phải khớp schema.

Tên annotation `RequestBody` được viết đầy đủ để phân biệt với `org.springframework.web.bind.annotation.RequestBody` dùng ở tham số controller. Annotation OpenAPI chỉ mô tả request body; tham số Spring mới nhận và deserialize payload.

Nếu chỉ cần một ví dụ đơn giản, có thể dùng `example` ở `@Content` hoặc `@Schema` tùy vị trí. Khi có nhiều tình huống, nên dùng `examples` để đặt tên và mô tả từng trường hợp. Không khai báo đồng thời `example` và `examples` cho cùng một media type nếu chúng diễn đạt các nội dung khác nhau, vì công cụ hiển thị có thể gây nhầm lẫn.

## 5. Ví dụ cho response body

Response cũng có thể có nhiều ví dụ, chẳng hạn một khách hàng mới tạo và một khách hàng được tạo từ nguồn import:

```java
@PostMapping("/api/customers")
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Khách hàng đã được tạo",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = CustomerResponse.class),
            examples = {
                @ExampleObject(
                    name = "created",
                    summary = "Khách hàng mới",
                    value = """
                        {
                          "id": "4f1b8a22-0c6a-4c8e-9b47-cc3d40f32e10",
                          "displayName": "Nguyen An",
                          "email": "an.nguyen@example.com",
                          "status": "ACTIVE"
                        }
                        """
                ),
                @ExampleObject(
                    name = "imported",
                    summary = "Khách hàng được nhập từ hệ thống khác",
                    value = """
                        {
                          "id": "aa08b2b6-18d0-4d73-b2e4-6c8d1a8e1f50",
                          "displayName": "Support Team",
                          "email": "support@example.com",
                          "status": "PENDING_REVIEW"
                        }
                        """
                )
            }
        )
    )
})
ResponseEntity<CustomerResponse> create(
    @Valid @RequestBody CreateCustomerRequest request
) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(customerService.create(request));
}
```

Response example nằm trong `content` của response code `201`. Nếu endpoint có nhiều response code, mỗi code có thể có schema và ví dụ riêng. Ví dụ lỗi `400` nên mô tả error response thay vì dùng lại payload thành công.

Ví dụ lỗi:

```java
@ApiResponse(
    responseCode = "400",
    description = "Dữ liệu đầu vào không hợp lệ",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ApiError.class),
        examples = @ExampleObject(
            name = "invalid-email",
            summary = "Email không đúng định dạng",
            value = """
                {
                  "code": "VALIDATION_FAILED",
                  "message": "Request validation failed",
                  "fieldErrors": [
                    {"field": "email", "message": "must be a well-formed email address"}
                  ]
                }
                """
        )
    )
)
```

Không nên ghi thông tin nhạy cảm hoặc dữ liệu cá nhân thật vào response example. Dùng dữ liệu giả có hình dạng thực tế nhưng không thể nhận diện người dùng thật.

## 6. Ví dụ bên ngoài bằng `externalValue`

Với payload lớn hoặc ví dụ được dùng chung ở nhiều tài liệu, có thể tham chiếu file ví dụ bên ngoài bằng `externalValue`:

```java
@Content(
    mediaType = MediaType.APPLICATION_JSON_VALUE,
    schema = @Schema(implementation = BulkImportRequest.class),
    examples = @ExampleObject(
        name = "large-import",
        summary = "Ví dụ nhập dữ liệu số lượng lớn",
        externalValue = "https://docs.example.com/openapi/examples/bulk-import.json"
    )
)
```

`externalValue` là URI đến nội dung ví dụ. Theo OpenAPI Example Object, một ví dụ dùng `value` hoặc `externalValue`; không dùng cả hai để mô tả hai payload khác nhau trong cùng một object. Đường dẫn bên ngoài cần được duy trì ổn định và công cụ xem tài liệu phải có khả năng truy cập. Một số giao diện chỉ hiển thị liên kết hoặc không tải ví dụ ngoài, tùy cách triển khai.

Với file nhỏ, dữ liệu ngắn và ví dụ cần luôn đi cùng đặc tả, dùng `value` thường thuận tiện hơn. Với payload rất dài, dữ liệu nhị phân hoặc ví dụ dùng chung giữa nhiều API, tham chiếu ngoài có thể giúp tài liệu gọn hơn.

## 7. Ví dụ cho media type khác nhau

Một operation có thể nhận nhiều định dạng nội dung. Ví dụ API nhập dữ liệu hỗ trợ JSON và XML. Mỗi media type có schema và ví dụ riêng:

```java
@PostMapping(
    path = "/api/imports",
    consumes = {MediaType.APPLICATION_JSON_VALUE, MediaType.APPLICATION_XML_VALUE}
)
@Operation(
    summary = "Nhập dữ liệu",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = {
            @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = ImportRequest.class),
                examples = @ExampleObject(
                    name = "json-import",
                    value = "{\"source\":\"warehouse\",\"count\":12}"
                )
            ),
            @Content(
                mediaType = MediaType.APPLICATION_XML_VALUE,
                schema = @Schema(implementation = ImportRequest.class),
                examples = @ExampleObject(
                    name = "xml-import",
                    value = "<importRequest><source>warehouse</source><count>12</count></importRequest>"
                )
            )
        }
    )
)
ResponseEntity<ImportResponse> importData(@RequestBody ImportRequest request) {
    return ResponseEntity.accepted().body(importService.importData(request));
}
```

Ví dụ JSON và XML biểu diễn cùng dữ liệu nhưng có cú pháp khác nhau. Ứng dụng chỉ thực sự nhận cả hai định dạng nếu có message converter tương ứng và cấu hình `consumes` đúng. Việc khai báo hai `@Content` trong OpenAPI không tự thêm XML converter hoặc làm controller hỗ trợ XML.

## 8. Ví dụ cho header hoặc parameter object

`@ExampleObject` cũng có thể được dùng trong `@Parameter` cho header, cookie hoặc path parameter. Ví dụ header `X-Client-Version`:

```java
@GetMapping("/api/profile")
ProfileResponse getProfile(
    @Parameter(
        name = "X-Client-Version",
        in = ParameterIn.HEADER,
        description = "Phiên bản ứng dụng client",
        examples = {
            @ExampleObject(name = "android", value = "5.4.0"),
            @ExampleObject(name = "ios", value = "5.3.2")
        }
    )
    @RequestHeader("X-Client-Version") String clientVersion
) {
    return profileService.getProfile(clientVersion);
}
```

Ví dụ ở parameter object giúp Swagger UI gợi ý giá trị khi thử request. Với header response, dùng `@Header` trong `@ApiResponse` để mô tả header mà server trả về; không dùng `@Parameter(in = HEADER)` cho response header.

## 9. Chọn vị trí khai báo ví dụ

| Nhu cầu | Annotation hoặc vị trí phù hợp | Phạm vi ví dụ |
| --- | --- | --- |
| Một giá trị cho query/path/header parameter | `@Parameter(example = "...")` | Một parameter. |
| Nhiều lựa chọn cho parameter | `@Parameter(examples = @ExampleObject(...))` | Các giá trị của parameter. |
| Một field trong DTO | `@Schema(example = "...")` | Một thuộc tính schema. |
| Một payload request | `@Content(examples = @ExampleObject(...))` trong OpenAPI RequestBody | Một media type của request. |
| Một payload response | `@Content(examples = @ExampleObject(...))` trong `@ApiResponse` | Một response code và media type. |
| Ví dụ được lưu ở file ngoài | `@ExampleObject(externalValue = "...")` | Một ví dụ tham chiếu URI bên ngoài. |

Không đặt một payload hoàn chỉnh vào `@Parameter.example` nếu endpoint thực sự nhận JSON body. Ngược lại, không dùng `@Schema(example)` của một field để thay cho ví dụ toàn bộ object khi client cần thấy quan hệ giữa nhiều field.

## 10. Kiểm tra ví dụ trong OpenAPI và Swagger UI

Sau khi thêm ví dụ, cần kiểm tra tài liệu được sinh ra thay vì chỉ dựa vào annotation trong source:

1. Khởi động ứng dụng và mở `/v3/api-docs` hoặc endpoint tài liệu đã cấu hình.
2. Tìm operation trong `paths`; kiểm tra `parameters`, `requestBody.content` và `responses`.
3. Với parameter, xác nhận `example` hoặc các phần tử `examples` nằm đúng parameter.
4. Với model, mở `components.schemas` và kiểm tra ví dụ của thuộc tính cùng schema type/format.
5. Với request/response, xác nhận ví dụ nằm dưới đúng media type và tên ví dụ không trùng nhau trong cùng phạm vi.
6. Mở Swagger UI, chọn từng ví dụ và xác nhận payload hiển thị đúng.
7. Dùng **Try it out** để gửi request; kiểm tra server thực sự chấp nhận payload theo validation và converter hiện có.
8. Nếu dùng `externalValue`, thử mở URI từ môi trường người đọc tài liệu và xác minh nội dung vẫn tồn tại.

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Swagger UI chỉ hiển thị một ví dụ | Dùng `example` đơn thay vì `examples`, hoặc phiên bản UI không trình bày danh sách | Kiểm tra `/v3/api-docs` và dùng `@ExampleObject` có tên. |
| Ví dụ không xuất hiện ở parameter | Đặt `@ExampleObject` trong `@Content` thay vì `@Parameter`, hoặc ngược lại | Đặt ví dụ theo đúng loại Parameter Object hay Media Type Object. |
| Request body example không được chọn trong Try it out | Ví dụ chỉ được ghi trong `@Schema` của field hoặc description | Khai báo `examples` trong `@Content` của request body. |
| Ví dụ không khớp payload server nhận | Schema, converter, enum hoặc validation khác ví dụ | Đồng bộ DTO, schema, converter và constraint runtime. |
| Ví dụ JSON không hợp lệ | Chuỗi `value` có lỗi cú pháp hoặc thiếu escape | Kiểm tra JSON sau khi giải mã từ `/v3/api-docs`. |
| `externalValue` không tải được | URI sai, file bị xóa hoặc công cụ không hỗ trợ tải ngoài | Dùng URI ổn định, kiểm tra quyền truy cập hoặc nhúng `value`. |
| Ví dụ cho XML nhưng endpoint trả 415 | Ứng dụng thiếu XML message converter hoặc `consumes` không khớp | Cấu hình converter và kiểm thử HTTP thực tế. |

## 11. Nguyên tắc áp dụng

- Dùng `@Parameter(example = ...)` cho một giá trị tham số và `@Parameter(examples = ...)` cho nhiều trường hợp.
- Dùng `@Schema(example = ...)` để minh họa field hoặc model.
- Dùng `@Content(examples = ...)` để cung cấp payload request/response theo media type.
- Đặt tên và mô tả các `@ExampleObject` để người đọc hiểu khi nào nên chọn từng ví dụ.
- Bảo đảm mọi ví dụ tuân thủ schema, enum, định dạng và ràng buộc runtime.
- Dùng `externalValue` cho payload lớn hoặc dùng chung; duy trì URI ổn định.
- Kiểm tra `/v3/api-docs`, Swagger UI và request thật sau khi cập nhật ví dụ.

Ví dụ tốt làm rõ cách sử dụng API bằng dữ liệu cụ thể. Đặt ví dụ ở đúng cấp giúp client biết giá trị của từng parameter, ý nghĩa từng field và cấu trúc payload hoàn chỉnh. Springdoc chuyển các annotation này thành OpenAPI Example Object; ứng dụng vẫn phải bảo đảm schema, converter và validation chấp nhận đúng dữ liệu đã công bố.

## Tài liệu tham khảo

- [OpenAPI Specification – Example Object và Media Type Object](https://spec.openapis.org/oas/latest.html)
- [Swagger Annotations – `@ExampleObject`, `@Content`, `@Parameter` và `@Schema`](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations)
- [Springdoc OpenAPI – tài liệu chính thức](https://springdoc.org/)
- [Swagger UI – sử dụng và hiển thị examples](https://swagger.io/docs/open-source-tools/swagger-ui/usage/)
