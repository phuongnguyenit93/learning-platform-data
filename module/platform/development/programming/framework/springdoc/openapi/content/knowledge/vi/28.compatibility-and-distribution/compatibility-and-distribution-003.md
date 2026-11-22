# Thu hẹp enum, đổi kiểu, format hoặc mã trạng thái

## 1. Vì sao những thay đổi nhỏ có thể phá vỡ client?

Một thay đổi trong DTO Java có thể làm OpenAPI document thay đổi dù path và HTTP method không đổi. Ví dụ, nhóm phát triển xóa một giá trị enum, đổi một property từ integer sang string, đổi format từ date sang date-time hoặc thay response 200 bằng 204.

Những thay đổi này có thể khiến client đã sinh code từ OpenAPI cũ không còn tương thích. Client có thể không parse được JSON, không deserialize được kiểu dữ liệu, từ chối một enum value mới hoặc đi vào nhánh xử lý lỗi khi server trả status khác.

Khi đánh giá compatibility, cần xem dữ liệu đi theo chiều nào:

- **Request**: client gửi dữ liệu; server phải tiếp tục chấp nhận những request mà client cũ đang gửi.
- **Response**: server gửi dữ liệu; client cũ phải tiếp tục đọc và xử lý được response mà server mới có thể trả về.

Cùng một thay đổi có thể an toàn ở request nhưng rủi ro ở response. Ví dụ, thêm một giá trị enum vào tập giá trị server chấp nhận thường mở rộng khả năng của API. Nhưng thêm giá trị enum mà server có thể trả về có thể làm client cũ lỗi nếu client dùng enum đóng và không có nhánh fallback.

Springdoc OpenAPI phản ánh kiểu Java, validation và annotation thành schema, parameter, request body và response. Vì vậy, thay đổi model hoặc annotation cần được kiểm tra trong OpenAPI document và so sánh với hợp đồng đã phát hành.

## 2. Phân biệt request compatibility và response compatibility

Có thể dùng nguyên tắc sau để định hướng:

| Vị trí schema | Server mới cần bảo đảm | Thay đổi thường có rủi ro |
|---|---|---|
| Request body | Tiếp tục chấp nhận request hợp lệ từ client cũ | Thêm field bắt buộc, bỏ enum value được chấp nhận, thu hẹp range hoặc format |
| Query/path/header parameter | Tiếp tục chấp nhận cách gọi cũ | Đổi tên, đổi kiểu, đổi vị trí hoặc chuyển optional thành required |
| Response body | Client cũ tiếp tục đọc được mọi response mới | Đổi type, thêm enum output chưa biết, xóa field client cần |
| Response status | Client cũ xử lý được các status server mới trả về | Thay status, bỏ status cũ hoặc thay body semantics |
| Response headers | Client cũ không bị mất metadata cần thiết | Xóa hoặc đổi header mà client phụ thuộc |

Một thay đổi chỉ tương thích nếu xét cả schema lẫn hành vi thực tế. Ví dụ, OpenAPI cho phép một property nullable nhưng server lại luôn bỏ field đó hoặc serialize thành chuỗi rỗng thì client vẫn có thể gặp lỗi.

Không đánh giá compatibility chỉ bằng việc document mới validate thành công. Cần so sánh với document cũ và hiểu cách client sử dụng API.

## 3. Enum trong OpenAPI được tạo từ Java như thế nào?

Một enum Java thường được Springdoc chuyển thành schema string với danh sách giá trị được phép:

~~~java
public enum OrderStatus {
    NEW,
    CONFIRMED,
    SHIPPED,
    DELIVERED,
    CANCELLED
}
~~~

DTO:

~~~java
public record OrderResponse(
    String orderId,
    OrderStatus status
) {
}
~~~

OpenAPI schema tương ứng có thể giống:

~~~yaml
OrderResponse:
  type: object
  properties:
    orderId:
      type: string
    status:
      type: string
      enum:
        - NEW
        - CONFIRMED
        - SHIPPED
        - DELIVERED
        - CANCELLED
~~~

Danh sách enum là một phần hợp đồng. Client generator có thể tạo enum type tương ứng trong Java, Kotlin, TypeScript, C# hoặc ngôn ngữ khác.

Nếu đổi tên constant, xóa constant hoặc thêm constant, schema thay đổi. Dù JSON vẫn chứa chuỗi, client đã sinh enum đóng có thể không chấp nhận giá trị ngoài danh sách.

Hãy xem enum là tập giá trị công khai của API, không chỉ là chi tiết nội bộ của Java.

## 4. Thu hẹp enum trong request là breaking change

Giả sử API cũ chấp nhận:

~~~yaml
status:
  type: string
  enum:
    - NEW
    - CONFIRMED
    - SHIPPED
    - CANCELLED
~~~

Client cũ có thể gửi CANCELLED. Nếu server mới bỏ giá trị đó:

~~~yaml
status:
  type: string
  enum:
    - NEW
    - CONFIRMED
    - SHIPPED
~~~

server đã thu hẹp tập request được chấp nhận. Client cũ gửi một request hợp lệ theo contract trước đây nhưng bị từ chối theo contract mới.

Đây là breaking change ở chiều request. Tương tự, nếu server ngừng chấp nhận một enum value được công bố, cần có migration hoặc version API mới.

Một cách chuyển đổi an toàn hơn là:

1. Giữ enum value cũ trong giai đoạn chuyển tiếp.
2. Đánh dấu giá trị cũ là deprecated trong tài liệu nếu tooling hỗ trợ.
3. Thông báo replacement value và thời hạn loại bỏ.
4. Theo dõi request thực tế còn dùng giá trị cũ.
5. Chỉ loại bỏ khi đã hết thời gian hỗ trợ hoặc phát hành API version mới.

Không xóa enum value chỉ vì ứng dụng nội bộ không còn dùng nó; client bên ngoài có thể vẫn gửi.

## 5. Thêm enum value trong request và response khác nhau

Thêm một giá trị vào enum request thường mở rộng tập dữ liệu server chấp nhận:

~~~yaml
status:
  type: string
  enum:
    - NEW
    - CONFIRMED
    - SHIPPED
    - RETURNED
~~~

Client cũ vẫn có thể gửi các giá trị cũ. Nếu server mới chấp nhận thêm RETURNED, đây thường là thay đổi tương thích ở chiều request.

Tuy nhiên, thêm giá trị vào enum response lại có thể phá vỡ client:

~~~yaml
status:
  type: string
  enum:
    - NEW
    - CONFIRMED
    - SHIPPED
    - RETURNED
~~~

Server mới có thể trả RETURNED cho một order. Client cũ được sinh từ enum cũ có thể:

- Ném exception khi deserialize.
- Map thành null hoặc UNKNOWN.
- Từ chối response.
- Không xử lý nhánh nghiệp vụ mới.
- Ghi đè dữ liệu khi serialize lại.

Vì vậy, thêm enum response value là thay đổi có rủi ro và nhiều công cụ compatibility sẽ cảnh báo. Mức độ phá vỡ phụ thuộc client có xử lý unknown enum value hay không.

Để mở rộng enum response an toàn hơn, có thể thiết kế client có fallback UNKNOWN, dùng string khi phù hợp hoặc thêm field mới thay vì thay đổi enum hiện có. Với API public đã phát hành, hãy coi việc thêm enum response là thay đổi cần đánh giá kỹ.

## 6. Xóa enum value trong response

Nếu server mới không còn trả một giá trị cũ, tập response có thể được thu hẹp:

~~~yaml
status:
  type: string
  enum:
    - NEW
    - CONFIRMED
    - SHIPPED
~~~

Với client đã xử lý tất cả giá trị cũ, việc server không còn trả một số giá trị thường không làm client lỗi khi đọc response. Tuy nhiên, client có thể dựa vào giá trị đó để thực hiện luồng nghiệp vụ, hoặc hợp đồng có cam kết rằng trạng thái đó vẫn có thể xuất hiện.

Do đó, xóa enum response value thường ít nguy hiểm hơn thêm giá trị mới về mặt deserialize, nhưng vẫn có thể là thay đổi nghiệp vụ không tương thích.

Hãy phân biệt:

- **Schema compatibility**: client có parse được giá trị hay không.
- **Behavioral compatibility**: client có còn hoạt động đúng khi giá trị không bao giờ hoặc không còn xuất hiện hay không.

Một contract diff tool có thể phân loại thay đổi enum theo quy tắc tổng quát. Kết quả cần được review cùng business semantics.

## 7. Biểu diễn enum bằng @Schema trong Springdoc

Springdoc thường suy luận enum từ Java enum. Nếu cần mô tả rõ hơn, có thể dùng @Schema:

~~~java
@Schema(description = "Trạng thái đơn hàng")
public enum OrderStatus {
    NEW,
    CONFIRMED,
    SHIPPED,
    DELIVERED,
    CANCELLED
}
~~~

Có thể mô tả allowable values trên property:

~~~java
public record OrderFilter(
    @Schema(
        description = "Lọc theo trạng thái",
        allowableValues = {"NEW", "CONFIRMED", "SHIPPED"}
    )
    String status
) {
}
~~~

Cần cẩn thận khi dùng allowableValues để thu hẹp một Java enum hoặc string property. Annotation làm thay đổi contract được công bố; nó không tự bảo đảm tầng service hoặc validation thực sự từ chối các giá trị ngoài danh sách.

Nếu API dùng enum Java làm kiểu request, validation và binding runtime cần đồng bộ với schema. Nếu schema nói chỉ có ba giá trị nhưng controller vẫn chấp nhận giá trị khác, document sẽ không phản ánh hành vi thật.

Không dùng @Schema để che một thay đổi breaking. Hãy cập nhật code, validation, OpenAPI và test theo cùng một quy tắc.

## 8. Enum có giá trị wire khác tên constant

Một số hệ thống cần giữ tên constant Java khác với chuỗi JSON công khai. Ví dụ:

~~~java
public enum PaymentState {
    @JsonProperty("awaiting-payment")
    PENDING,

    @JsonProperty("paid")
    COMPLETED,

    @JsonProperty("payment-failed")
    FAILED
}
~~~

Giá trị wire được Jackson serialize/deserialize có thể khác tên constant. OpenAPI document cần phản ánh giá trị JSON thực tế mà client gửi và nhận.

Hãy kiểm tra /v3/api-docs sau khi thêm @JsonProperty. Nếu schema vẫn hiển thị PENDING, COMPLETED, FAILED trong khi JSON runtime dùng awaiting-payment, paid, payment-failed, hợp đồng và serialization đang không đồng nhất.

Không đổi giá trị wire chỉ để tên Java đẹp hơn. Với enum đã công bố, giá trị JSON là một phần hợp đồng và cần được quản lý như API change.

## 9. Đổi kiểu dữ liệu là thay đổi hợp đồng

OpenAPI schema xác định type của property và parameter. Ví dụ:

~~~yaml
quantity:
  type: integer
  format: int32
~~~

Nếu server đổi sang:

~~~yaml
quantity:
  type: string
~~~

client cũ có thể không parse được response hoặc không serialize request đúng kiểu. Đây thường là breaking change.

Một số thay đổi kiểu thường gặp:

| Kiểu cũ | Kiểu mới | Rủi ro |
|---|---|---|
| integer | string | Breaking: kiểu JSON thay đổi |
| string | integer | Breaking: client gửi/đọc sai kiểu |
| integer/int32 | integer/int64 | Có thể breaking do range và kiểu sinh code thay đổi |
| number/double | string | Breaking: numeric value thành text |
| object | array | Breaking: cấu trúc JSON thay đổi |
| array | object | Breaking: cấu trúc JSON thay đổi |
| string | object | Breaking: scalar thành object |
| boolean | string | Breaking: boolean thành text |

Không nên dựa vào việc một parser có thể ép kiểu tự động. Client generator, validation và ngôn ngữ đích có thể xử lý khác nhau.

Nếu cần chuyển đổi type, thường nên tạo property mới, duy trì property cũ trong thời gian chuyển tiếp và phát hành API version mới nếu client phải thay đổi đồng loạt.

## 10. Thay đổi integer range và numeric precision

JSON có một loại number chung, nhưng OpenAPI dùng type và format để mô tả integer, int32, int64, float hoặc double.

Ví dụ:

~~~yaml
quantity:
  type: integer
  format: int32
price:
  type: number
  format: double
~~~

Nếu đổi int32 sang int64, dữ liệu có thể vẫn là JSON number nhưng client generator có thể đổi từ Integer sang Long hoặc từ number sang bigint tùy ngôn ngữ. Giá trị vượt range cũ có thể không biểu diễn được trong client cũ.

Đổi double sang decimal hoặc string có thể ảnh hưởng precision, serialization và phép tính. Với tiền tệ, hãy chọn representation rõ ràng, ví dụ integer minor units hoặc decimal string theo contract, rồi giữ ổn định.

Nếu chỉ tăng maximum trong schema request, server có thể chấp nhận thêm giá trị. Đây thường là mở rộng ở chiều request. Nhưng nếu server bắt đầu trả giá trị vượt range mà client cũ hỗ trợ, đó có thể là breaking change ở chiều response.

Hãy kiểm tra cả type, format, minimum, maximum, multipleOf và runtime serialization.

## 11. Thay đổi format của string

OpenAPI thường dùng type string cùng format để mô tả dữ liệu có cấu trúc:

~~~yaml
createdAt:
  type: string
  format: date-time
birthDate:
  type: string
  format: date
email:
  type: string
  format: email
uuid:
  type: string
  format: uuid
~~~

Đổi format có thể ảnh hưởng code generation và validation:

| Format cũ | Format mới | Ảnh hưởng |
|---|---|---|
| date | date-time | Thêm thời gian và timezone; kiểu client có thể đổi |
| date-time | date | Mất thông tin thời gian |
| uuid | string không format | Có thể mất kiểu UUID trong client |
| int64 | decimal hoặc string | Thay đổi cách parse và range |
| binary | byte/base64 | Có thể đổi encoding hoặc media handling |

Format là một gợi ý có ý nghĩa cho tooling. Không phải validator nào cũng thực thi mọi format giống nhau, nhưng client generator có thể ánh xạ format sang kiểu native.

Ví dụ Java DTO:

~~~java
public record OrderResponse(
    LocalDate deliveryDate,
    OffsetDateTime createdAt
) {
}
~~~

Springdoc và Jackson có thể mô tả LocalDate thành date và OffsetDateTime thành date-time tùy cấu hình converter. Hãy kiểm tra JSON thực tế, timezone và định dạng serialize sau khi thay đổi Java type.

## 12. Thay đổi nullable và required

Required và nullable là hai khái niệm khác nhau:

- Required xác định property có bắt buộc xuất hiện trong object hay không.
- Nullable xác định giá trị null có được chấp nhận hay không theo schema/version.

Ví dụ property optional nhưng không nullable:

~~~yaml
nickname:
  type: string
~~~

Property required nhưng cho phép null trong OpenAPI 3.1:

~~~yaml
required:
  - middleName
properties:
  middleName:
    type:
      - string
      - "null"
~~~

Nếu server mới bắt buộc một field mà client cũ không gửi, request có thể bị từ chối. Đây là breaking change ở chiều request.

Nếu response mới bỏ một field mà client cũ kỳ vọng luôn có, client có thể lỗi hoặc hiển thị sai. Nếu response field chuyển từ non-null sang nullable, client cũ có thể gặp null unexpectedly.

Khi thay đổi required/nullable, kiểm tra cả JSON Schema, Jackson serialization, Bean Validation và client generator. Đừng coi optional và nullable là đồng nghĩa.

## 13. Thay đổi validation constraint

Schema có thể chứa các constraint như:

~~~yaml
quantity:
  type: integer
  minimum: 1
  maximum: 100
name:
  type: string
  minLength: 1
  maxLength: 80
~~~

Thu hẹp constraint request có thể làm server từ chối dữ liệu mà client cũ từng gửi:

- Giảm maximum.
- Tăng minimum.
- Giảm maxLength.
- Tăng minLength.
- Thu hẹp pattern.
- Giảm số phần tử tối đa của array.
- Thêm required property.

Đây thường là breaking change ở chiều request.

Mở rộng constraint request, ví dụ tăng maximum hoặc maxLength, thường cho phép thêm dữ liệu và ít phá vỡ client cũ. Tuy nhiên, giới hạn backend và database phải hỗ trợ range mới.

Với response, thu hẹp tập giá trị server có thể trả thường không gây lỗi parse nhưng có thể thay đổi business behavior. Mở rộng response constraint có thể khiến client cũ gặp giá trị chưa biết hoặc dữ liệu lớn hơn khả năng xử lý.

Các annotation validation của Jakarta như @Min, @Max, @Size, @Pattern và @NotNull có thể được Springdoc dùng để tạo schema constraints. Hãy kiểm tra document sau khi thay annotation.

## 14. Đổi mã trạng thái HTTP là thay đổi hành vi

HTTP status code là một phần quan trọng của contract. Client có thể dựa vào status để quyết định retry, hiển thị lỗi, điều hướng hoặc cập nhật trạng thái.

Một số thay đổi có rủi ro:

| Thay đổi | Tác động có thể có |
|---|---|
| 200 thành 201 | Client có thể không mong đợi Created hoặc header Location |
| 200 thành 204 | Response body biến mất |
| 404 thành 200 với body rỗng | Client không còn nhận diện resource không tồn tại |
| 400 thành 422 | Logic phân loại lỗi của client thay đổi |
| 401 thành 403 | Luồng đăng nhập/ủy quyền của client có thể sai |
| 409 thành 200 | Conflict không còn được biểu diễn như trước |
| Bỏ 429 | Client không còn nhận được tín hiệu rate limit |
| Thêm status mới | Client dùng switch đóng có thể không xử lý |

Không coi các status trong cùng nhóm 2xx hoặc 4xx là thay thế được cho nhau. 200 OK, 201 Created và 204 No Content có semantics khác nhau.

Nếu muốn bổ sung status mới cho một tình huống mới, hãy mô tả nó trong OpenAPI và bảo đảm client có default branch xử lý response chưa biết. Nếu thay status cũ, cần đánh giá migration và versioning.

## 15. Mô tả response status bằng Springdoc

Springdoc có thể suy luận response từ return type và các annotation, nhưng response quan trọng nên được mô tả tường minh.

Ví dụ:

~~~java
@PostMapping
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
        description = "Request không hợp lệ"
    ),
    @ApiResponse(
        responseCode = "409",
        description = "Đơn hàng bị xung đột"
    )
})
public ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest request) {
    OrderResponse response = orderService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(response);
}
~~~

Annotation mô tả document; ResponseEntity và exception handler quyết định status runtime. Cần giữ hai phần nhất quán.

Nếu annotation nói 201 nhưng controller thực tế trả 200, client nhận hợp đồng sai. Hãy test HTTP status thực tế và OpenAPI response cùng nhau.

Với response mặc định hoặc error response được tạo bởi @ControllerAdvice, có thể dùng @ApiResponse hoặc OpenApiCustomizer để mô tả schema lỗi chuẩn trên các operation.

## 16. Không đổi 200 thành 204 nếu body vẫn cần thiết

204 No Content có nghĩa response không chứa content body. Nếu API cũ trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 42,
  "status": "DELETED"
}
~~~

và API mới trả 204, client cũ không còn nhận được JSON body để đọc id hoặc trạng thái.

Nếu mục tiêu chỉ là báo thao tác thành công, 204 có thể là thiết kế phù hợp cho API mới. Nhưng với endpoint đã phát hành, đây là thay đổi contract. Có thể giữ response 200 cũ trong version hiện tại và dùng 204 cho endpoint/version mới.

Tương tự, không đổi 204 thành 200 với body mà không kiểm tra client generator và client code. Một số client có method return void; thay đổi response body có thể không được xử lý như mong đợi.

## 17. Error response và schema lỗi chuẩn

Nên giữ error response nhất quán giữa các operation. Ví dụ schema:

~~~java
public record ApiError(
    String code,
    String message,
    String traceId
) {
}
~~~

OpenAPI:

~~~yaml
responses:
  '400':
    description: Request không hợp lệ
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ApiError'
  '404':
    description: Không tìm thấy tài nguyên
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ApiError'
  '409':
    description: Xung đột nghiệp vụ
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ApiError'
~~~

Nếu thay error body từ object thành string hoặc đổi tên property, client đang parse ApiError có thể lỗi. Nếu thay error status mà giữ body, client vẫn có thể xử lý sai nhánh.

Nên định nghĩa một error contract ổn định và dùng lại component schema. Nếu cần bổ sung error code, cân nhắc giữ property cũ và thêm field optional để client cũ tiếp tục hoạt động.

## 18. Deprecation trước khi loại bỏ enum, field hoặc status

Khi cần loại bỏ một enum value, property hoặc operation, hãy thông báo trước:

- Đánh dấu operation/property deprecated nếu OpenAPI element hỗ trợ.
- Với enum value, dùng description hoặc extension theo convention của tổ chức nếu tooling không hỗ trợ deprecation riêng cho từng value.
- Công bố replacement value hoặc endpoint.
- Đưa thời hạn ngừng hỗ trợ.
- Theo dõi traffic để biết client nào còn sử dụng.
- Cung cấp migration guide.
- Chỉ xóa sau khi hết thời hạn và có versioning policy phù hợp.

Ví dụ property deprecated:

~~~java
public record PaymentRequest(
    @Schema(
        description = "Mã trạng thái cũ, sẽ ngừng hỗ trợ sau ngày công bố.",
        deprecated = true
    )
    String legacyStatus
) {
}
~~~

Không phải mọi phiên bản Swagger annotation đều có cách đánh dấu từng enum constant là deprecated một cách portable. Có thể mô tả rõ trong schema description hoặc vendor extension, nhưng cần thống nhất convention với tooling.

Deprecation là tín hiệu cho client lên kế hoạch migration; nó không tự ngăn server nhận giá trị cũ.

## 19. Dùng versioned endpoint khi không thể giữ tương thích

Nếu một thay đổi bắt buộc phải phá vỡ contract, có thể phát hành API version mới:

~~~text
/api/v1/orders
/api/v2/orders
~~~

Ví dụ v1 dùng status enum cũ và v2 dùng enum mới. Hai version có thể có DTO, controller và OpenAPI document group riêng.

Springdoc có thể tách document theo group:

~~~java
@Bean
GroupedOpenApi v1Api() {
    return GroupedOpenApi.builder()
        .group("v1")
        .pathsToMatch("/api/v1/**")
        .build();
}

@Bean
GroupedOpenApi v2Api() {
    return GroupedOpenApi.builder()
        .group("v2")
        .pathsToMatch("/api/v2/**")
        .build();
}
~~~

Các endpoint tài liệu group thường có dạng /v3/api-docs/v1 và /v3/api-docs/v2. Kiểm tra đúng URL theo cấu hình Springdoc đang dùng.

Không tạo version mới chỉ vì application build version tăng. API version mới nên phản ánh thay đổi contract có chủ đích và có kế hoạch hỗ trợ client.

## 20. Kiểm tra compatibility bằng OpenAPI diff

Contract diff so sánh document cũ và mới để tìm thay đổi ở path, parameter, schema, enum, response và security.

Có thể dùng oasdiff:

~~~bash
oasdiff breaking previous/openapi.yaml candidate/openapi.yaml
~~~

Cần pin phiên bản tool trong CI và lưu baseline của release đã phát hành. Không so candidate với một document mới nhất không rõ nguồn.

Khi review kết quả, chú ý:

- Enum values được thêm hay xóa ở request hay response.
- Type và format của property có thay đổi không.
- Required, nullable và validation constraints có thay đổi không.
- Status code cũ có bị bỏ hoặc thay đổi không.
- Response content/media type có thay đổi không.
- Security requirement có làm client cần credential mới không.

Tool diff không biết hết semantics nghiệp vụ và cách client deserialize. Một cảnh báo cần được đánh giá cùng contract tests và client behavior.

## 21. Kiểm thử schema và status bằng MockMvc

Có thể kiểm tra OpenAPI document được Springdoc tạo:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.components.schemas.OrderStatus.enum"
    ).isArray())
    .andExpect(jsonPath(
        "$.paths['/api/orders'].post.responses['201']"
    ).exists());
~~~

Đường dẫn schema và operation cần điều chỉnh theo document thực tế. Nếu enum nằm trong schema khác hoặc được inline, JSONPath phải trỏ tới đúng vị trí.

Kiểm tra response runtime:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "status": "NEW"
            }
            """))
    .andExpect(status().isCreated())
    .andExpect(jsonPath("$.status").value("NEW"));
~~~

Cần có test cho:

- Mọi enum request value còn được hỗ trợ.
- Giá trị enum không hợp lệ bị từ chối theo contract.
- Enum response có giá trị mà client cần biết.
- Kiểu JSON serialize đúng.
- Format ngày giờ và timezone đúng.
- Các status code quan trọng được trả đúng.
- Response body có mặt hoặc vắng mặt đúng với status.

Contract test kiểm tra document; integration test kiểm tra runtime. Cả hai cần chạy trong pipeline.

## 22. Ma trận đánh giá thay đổi phổ biến

| Thay đổi | Request | Response |
|---|---|---|
| Xóa enum value | Breaking: server từ chối input cũ | Thường không lỗi parse nhưng có thể đổi semantics |
| Thêm enum value | Thường mở rộng input được chấp nhận | Có thể breaking với client enum đóng |
| Đổi type | Thường breaking | Thường breaking |
| Tăng numeric maximum | Mở rộng input, thường tương thích | Có thể khiến client nhận số ngoài range cũ |
| Giảm numeric maximum | Thu hẹp input, breaking | Thu hẹp output có thể đổi semantics |
| Đổi date thành date-time | Thay đổi định dạng input, thường breaking | Client có thể không parse được |
| Chuyển optional thành required | Breaking | Không áp dụng cùng cách; field response mất đi cũng có rủi ro |
| Chuyển non-null thành nullable | Server có thể nhận null mới nếu request | Client có thể gặp null mới |
| 200 thành 204 | Không áp dụng cho request body | Breaking nếu client cần response body |
| Thêm status response mới | Không áp dụng | Có thể breaking với client xử lý status đóng |
| Xóa status response cũ | Không áp dụng | Có thể phá nhánh xử lý của client |

Ma trận là định hướng ban đầu. Compatibility cuối cùng còn phụ thuộc client, serializer, generator, validation và business semantics.

## 23. Quy trình thay đổi contract an toàn

Khi cần thu hẹp enum, đổi type/format hoặc thay status:

1. Lấy OpenAPI document của release đang được hỗ trợ.
2. Xác định thay đổi nằm ở request hay response.
3. Kiểm tra client generator và client đang dùng kiểu dữ liệu nào.
4. Đánh giá tác động schema và semantics.
5. Ưu tiên mở rộng tương thích hoặc thêm field/endpoint mới.
6. Đánh dấu deprecated và công bố migration nếu cần loại bỏ.
7. Viết test cho request/response và status runtime.
8. Sinh OpenAPI document từ Springdoc.
9. Chạy validator, linter và breaking-change diff.
10. Review mọi cảnh báo enum, type, format và response status.
11. Tăng API contract version hoặc tạo document group/version mới khi cần.
12. Phát hành migration guide và duy trì thời gian chuyển tiếp.

Không dựa vào việc server mới vẫn compile hoặc unit test nội bộ pass. Client cũ có thể được generate từ contract trước đó và cần được kiểm tra riêng.

## 24. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Client deserialize lỗi sau khi thêm enum | Client dùng enum đóng và không có unknown fallback |
| Request cũ bị 400 sau release | Server đã loại enum value hoặc thu hẹp constraint |
| OpenAPI báo enum khác JSON runtime | Jackson @JsonProperty hoặc custom serializer không đồng bộ |
| Client nhận null bất ngờ | Property response chuyển sang nullable hoặc bị bỏ khỏi JSON |
| Numeric overflow | Server trả giá trị vượt range type client cũ |
| Date parse lỗi | Format hoặc timezone representation thay đổi |
| Client không xử lý được 204 | Server bỏ response body mà client đang cần |
| Client báo lỗi với status mới | Switch/case không có default handling |
| Swagger UI hiển thị response sai | @ApiResponse không khớp ResponseEntity hoặc exception handler |
| Contract diff không phát hiện thay đổi | Baseline sai, tool version cũ hoặc schema bị inline/resolve khác |
| Version API tăng nhưng contract không đổi | Nhầm application version với API contract version |

Khi điều tra, so sánh JSON runtime, OpenAPI document và code client đã generate. Chỉ kiểm tra Java enum hoặc annotation là chưa đủ.

## 25. Nguyên tắc giữ tương thích khi thay đổi schema và status

Khi quản lý thay đổi enum, type, format và HTTP status:

1. Đánh giá riêng request compatibility và response compatibility.
2. Không xóa enum request value đang được client dùng nếu chưa có migration.
3. Coi enum response value mới là thay đổi cần kiểm tra với client enum đóng.
4. Không đổi type hoặc format của property công khai mà không có kế hoạch.
5. Giữ numeric range và precision phù hợp với client đã phát hành.
6. Phân biệt required với nullable.
7. Đồng bộ Bean Validation, Jackson serialization và OpenAPI schema.
8. Không thay 200, 201, 204 hoặc error status như thể chúng tương đương.
9. Mô tả response bằng @ApiResponse và kiểm tra status runtime.
10. Dùng deprecation, migration window và versioned API khi cần.
11. Chạy OpenAPI diff và contract tests trước khi phát hành.
12. Lưu baseline theo đúng API version và audience.

Enum, type, format và status code đều là thành phần của hợp đồng API. Khi đánh giá thay đổi theo chiều dữ liệu, giữ đồng bộ Java DTO, Jackson, validation và OpenAPI, đồng thời kiểm tra client compatibility trước release, nhóm phát triển có thể tiến hóa API mà giảm nguy cơ làm hỏng tích hợp đang hoạt động.

