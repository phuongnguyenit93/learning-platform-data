# @ExampleObject và nhiều ví dụ cho một kiểu nội dung

Một schema mô tả cấu trúc dữ liệu mà API nhận hoặc trả về, nhưng người tích hợp thường cần xem những payload cụ thể để hiểu cách điền field, kết hợp giá trị và biểu diễn các trường hợp khác nhau. OpenAPI hỗ trợ khai báo một ví dụ hoặc nhiều ví dụ cho cùng một media type. Với springdoc-openapi, annotation @ExampleObject cho phép đặt các ví dụ có tên, phần tóm tắt và giá trị ngay trên request body, response hoặc parameter.

Ví dụ hữu ích giúp người đọc hiểu hợp đồng nhanh hơn, đồng thời giúp Swagger UI hiển thị các payload mẫu để thử API. Tuy nhiên, ví dụ chỉ minh họa cách sử dụng; nó không thay thế schema, không thực thi validation và không làm thay đổi dữ liệu mà controller xử lý.

## 1. Phân biệt schema và example

Schema trả lời câu hỏi dữ liệu có cấu trúc và giới hạn nào. Example trả lời câu hỏi một payload cụ thể trông như thế nào.

| Thành phần | Mục đích | Ví dụ |
| --- | --- | --- |
| Schema | Mô tả kiểu, field, required và constraint | quantity là integer lớn hơn 0 |
| Example | Minh họa một giá trị cụ thể | {"sku":"KB-01","quantity":2} |
| Description | Giải thích ý nghĩa và quy ước | sku là mã sản phẩm trong catalog |

Một schema có thể có nhiều ví dụ hợp lệ. Chẳng hạn cùng schema CreateOrderRequest, ta có thể minh họa đơn hàng có một sản phẩm, đơn hàng có nhiều sản phẩm hoặc đơn hàng có ghi chú giao hàng. Các ví dụ đều tuân theo cùng cấu trúc nhưng làm rõ các cách sử dụng khác nhau.

Ví dụ schema:

~~~yaml
CreateOrderRequest:
  type: object
  required: [customerId, items]
  properties:
    customerId:
      type: string
    items:
      type: array
      minItems: 1
      items:
        type: object
        required: [sku, quantity]
        properties:
          sku:
            type: string
          quantity:
            type: integer
            minimum: 1
    deliveryNote:
      type: string
~~~

Ví dụ hợp lệ theo schema:

~~~json
{
  "customerId": "C-100",
  "items": [
    {"sku": "KB-01", "quantity": 2}
  ],
  "deliveryNote": "Giao giờ hành chính"
}
~~~

Nếu example chứa quantity: 0 trong khi schema quy định minimum: 1, tài liệu trở nên mâu thuẫn. Vì vậy, hãy kiểm tra ví dụ cùng với schema và validation runtime.

## 2. Example Object trong OpenAPI

OpenAPI dùng Example Object để lưu thông tin của một ví dụ. Những trường thường dùng gồm:

| Trường | Ý nghĩa |
| --- | --- |
| summary | Tiêu đề ngắn của ví dụ |
| description | Giải thích chi tiết hơn; có thể dùng Markdown theo hỗ trợ của công cụ |
| value | Giá trị ví dụ được nhúng trực tiếp trong đặc tả |
| externalValue | URL trỏ tới nội dung ví dụ bên ngoài |
| $ref | Tham chiếu một Example Object được định nghĩa ở nơi khác |

Ở cấp Media Type Object, OpenAPI có hai cách:

- example: một ví dụ duy nhất.
- examples: một map gồm nhiều Example Object, mỗi ví dụ có một khóa riêng.

Không khai báo đồng thời example và examples trong cùng một Media Type Object. Khi cần nhiều payload cho cùng media type, dùng examples.

Ví dụ:

~~~yaml
content:
  application/json:
    schema:
      $ref: '#/components/schemas/CreateOrderRequest'
    examples:
      singleItem:
        summary: Đơn hàng có một sản phẩm
        value:
          customerId: C-100
          items:
            - sku: KB-01
              quantity: 2
      multipleItems:
        summary: Đơn hàng có nhiều sản phẩm
        value:
          customerId: C-200
          items:
            - sku: KB-01
              quantity: 1
            - sku: MS-02
              quantity: 3
~~~

Khóa singleItem và multipleItems là tên định danh trong map examples. Chúng giúp Swagger UI hoặc công cụ khác phân biệt các lựa chọn.

## 3. Khai báo nhiều ví dụ cho request body bằng @ExampleObject

Với springdoc-openapi, có thể dùng @Operation, @Content và @ExampleObject để mô tả nhiều payload cho cùng request media type.

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@Operation(
    summary = "Tạo đơn hàng",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Thông tin đơn hàng cần tạo",
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = CreateOrderRequest.class),
            examples = {
                @ExampleObject(
                    name = "singleItem",
                    summary = "Đơn hàng có một sản phẩm",
                    description = "Dùng khi khách chỉ mua một mặt hàng.",
                    value = "{\"customerId\":\"C-100\",\"items\":[{\"sku\":\"KB-01\",\"quantity\":2}]}"
                ),
                @ExampleObject(
                    name = "multipleItems",
                    summary = "Đơn hàng có nhiều sản phẩm",
                    description = "Minh họa danh sách items gồm nhiều phần tử.",
                    value = "{\"customerId\":\"C-200\",\"items\":[{\"sku\":\"KB-01\",\"quantity\":1},{\"sku\":\"MS-02\",\"quantity\":3}]}"
                )
            }
        )
    )
)
@PostMapping(
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
OrderResponse create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Trong đoạn mã trên có hai annotation cùng tên đơn giản là RequestBody:

- org.springframework.web.bind.annotation.RequestBody đặt trên tham số controller để Spring đọc HTTP body.
- io.swagger.v3.oas.annotations.parameters.RequestBody nằm trong @Operation để mô tả request body trong OpenAPI.

Ví dụ dùng tên đầy đủ cho annotation OpenAPI để tránh import nhầm. Nếu đặt import, hãy dùng đúng package tương ứng.

Thuộc tính name của @ExampleObject trở thành khóa trong map examples; nó không phải là tên property trong JSON. summary và description giúp người đọc chọn đúng ví dụ. value chứa payload mẫu dưới dạng chuỗi trong annotation, vì vậy JSON phải được escape dấu ngoặc kép và dấu gạch chéo đúng cú pháp Java.

Các ví dụ này chỉ áp dụng cho application/json. Chúng không tự làm cho endpoint nhận XML, form hoặc multipart. Mapping controller và message converter vẫn phải hỗ trợ media type được khai báo.

## 4. Nhiều ví dụ cho response

Có thể gắn nhiều ví dụ vào response của một status code. Điều này hữu ích khi response có cùng schema nhưng các giá trị khác nhau, ví dụ đơn hàng ở trạng thái mới tạo, đang xử lý hoặc đã giao.

~~~java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;

@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Đã tạo đơn hàng",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class),
            examples = {
                @ExampleObject(
                    name = "created",
                    summary = "Đơn hàng vừa được tạo",
                    value = "{\"id\":\"O-100\",\"status\":\"CREATED\",\"total\":398000}"
                ),
                @ExampleObject(
                    name = "accepted",
                    summary = "Đơn hàng đã được tiếp nhận",
                    value = "{\"id\":\"O-101\",\"status\":\"ACCEPTED\",\"total\":125000}"
                )
            }
        )
    )
})
~~~

Đoạn annotation có thể đặt trên method controller. Mỗi ví dụ cần tuân theo OrderResponse; nếu status là enum, các giá trị phải khớp với enum được công bố. Response example cũng không làm thay đổi object thực tế mà method trả về.

Có thể dùng ví dụ để minh họa lỗi:

~~~java
@ApiResponse(
    responseCode = "400",
    description = "Dữ liệu request không hợp lệ",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ApiError.class),
        examples = {
            @ExampleObject(
                name = "missingField",
                summary = "Thiếu trường bắt buộc",
                value = "{\"code\":\"INVALID_REQUEST\",\"message\":\"customerId là bắt buộc\"}"
            ),
            @ExampleObject(
                name = "invalidQuantity",
                summary = "Số lượng không hợp lệ",
                value = "{\"code\":\"INVALID_QUANTITY\",\"message\":\"quantity phải lớn hơn 0\"}"
            )
        }
    )
)
~~~

Ví dụ lỗi giúp client hiểu cấu trúc error response và các mã lỗi có thể xuất hiện. Hãy bảo đảm chúng khớp với exception handler và status code thực tế.

## 5. Nhiều ví dụ cho parameter

@ExampleObject cũng có thể mô tả các giá trị mẫu của query parameter hoặc header parameter. Dùng @Parameter(examples = ...) khi muốn đưa ra một số lựa chọn hoặc tình huống gọi API.

~~~java
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.ExampleObject;

@GetMapping
List<OrderResponse> search(
    @Parameter(
        name = "status",
        in = ParameterIn.QUERY,
        description = "Lọc theo trạng thái đơn hàng",
        examples = {
            @ExampleObject(name = "created", summary = "Đơn mới", value = "CREATED"),
            @ExampleObject(name = "shipping", summary = "Đang giao", value = "SHIPPING"),
            @ExampleObject(name = "completed", summary = "Đã hoàn tất", value = "COMPLETED")
        }
    )
    @RequestParam(name = "status", required = false) OrderStatus status
) {
    return orderService.search(status);
}
~~~

Ví dụ cho parameter là các giá trị của chính parameter, không phải JSON object. Nếu parameter là enum, các giá trị mẫu nên khớp enum hoặc converter mà server chấp nhận.

Với query parameter, cũng cần phân biệt example/examples của OpenAPI Parameter Object với ví dụ trong Schema Object. @Parameter mô tả parameter ở cấp operation; @Schema mô tả kiểu dữ liệu của giá trị.

## 6. Một media type có nhiều ví dụ; nhiều media type có bộ ví dụ riêng

Mỗi mục trong content có thể có schema và examples riêng. Ví dụ một endpoint chấp nhận cả JSON và XML:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateOrderRequest'
      examples:
        standard:
          summary: Payload JSON thông thường
          value:
            customerId: C-100
            items:
              - sku: KB-01
                quantity: 2
    application/xml:
      schema:
        $ref: '#/components/schemas/CreateOrderRequest'
      examples:
        standard:
          summary: Payload XML thông thường
          value: |
            <createOrderRequest>
              <customerId>C-100</customerId>
              <items>
                <item><sku>KB-01</sku><quantity>2</quantity></item>
              </items>
            </createOrderRequest>
~~~

Ví dụ JSON và XML phải là biểu diễn hợp lệ của media type tương ứng. Một JSON object không thể được dùng nguyên trạng làm ví dụ XML. Mỗi media type có map examples riêng, dù các schema cùng tham chiếu một component.

Trong annotation, có thể khai báo nhiều @Content bên trong mảng content của request body hoặc response. Mỗi @Content chứa media type, schema và các @ExampleObject tương ứng. consumes của controller phải khớp các định dạng request mà server thực sự hỗ trợ.

## 7. Phân biệt @ExampleObject với @Schema(example = ...)

@Schema(example = "...") và @ExampleObject có phạm vi khác nhau:

| Cách khai báo | Phạm vi | Dùng khi |
| --- | --- | --- |
| @Schema(example = "...") | Một giá trị mẫu gắn với schema/property | Muốn minh họa một field hoặc một schema |
| @Content(example = "...") | Một ví dụ cho media type | Chỉ cần một payload mẫu ở cấp content |
| @Content(examples = {...}) | Nhiều Example Object cho một media type | Muốn người đọc chọn giữa nhiều payload |
| @Parameter(examples = {...}) | Nhiều ví dụ cho parameter | Muốn minh họa các giá trị query/header khác nhau |

Ví dụ schema property:

~~~java
public record ProductRequest(
    @Schema(
        description = "Mã sản phẩm",
        example = "KB-01"
    )
    String sku
) {}
~~~

Ví dụ ở cấp property giúp người đọc hiểu một giá trị đơn lẻ. Nó không thể hiện nhiều kịch bản request hoàn chỉnh như singleItem và multipleItems.

Trong OpenAPI Media Type Object, example và examples loại trừ lẫn nhau. Khi đã dùng @Content(examples = {...}), không nên đồng thời đặt một ví dụ đơn lẻ cho cùng content. Với OpenAPI 3.1, Schema Object cũng có keyword examples theo JSON Schema; đây là vị trí khác với map examples của Media Type Object. Hãy xem đúng cấp trong JSON/YAML để tránh nhầm.

## 8. Tái sử dụng ví dụ qua components.examples

Khi cùng một payload mẫu được dùng ở nhiều operation, có thể định nghĩa ví dụ dùng chung trong components.examples, rồi tham chiếu bằng $ref.

~~~yaml
components:
  examples:
    StandardOrder:
      summary: Đơn hàng tiêu chuẩn
      description: Đơn hàng có một sản phẩm và số lượng bằng hai.
      value:
        customerId: C-100
        items:
          - sku: KB-01
            quantity: 2
    OrderWithoutNote:
      summary: Đơn hàng không có ghi chú giao hàng
      value:
        customerId: C-200
        items:
          - sku: MS-02
            quantity: 1

paths:
  /api/orders:
    post:
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
            examples:
              standard:
                $ref: '#/components/examples/StandardOrder'
              withoutNote:
                $ref: '#/components/examples/OrderWithoutNote'
~~~

Với annotation, có thể tham chiếu component example đã tồn tại:

~~~java
@Content(
    mediaType = "application/json",
    schema = @Schema(implementation = CreateOrderRequest.class),
    examples = {
        @ExampleObject(
            name = "standard",
            ref = "#/components/examples/StandardOrder"
        ),
        @ExampleObject(
            name = "withoutNote",
            ref = "#/components/examples/OrderWithoutNote"
        )
    }
)
~~~

Các component được tham chiếu phải thực sự tồn tại trong tài liệu OpenAPI. Có thể tạo chúng qua OpenAPI model bean hoặc customizer; chỉ ghi chuỗi $ref mà không định nghĩa component sẽ tạo liên kết hỏng.

Tái sử dụng ví dụ phù hợp khi cùng payload được dùng ở nhiều operation hoặc response. Tuy nhiên, nếu một operation cần bối cảnh khác, hãy tạo ví dụ riêng thay vì dùng chung một tên chung chung khiến người đọc không hiểu khác biệt.

## 9. Dùng externalValue cho ví dụ lớn hoặc file bên ngoài

externalValue trỏ tới nội dung ví dụ được lưu ở một URL. Cách này hữu ích khi payload lớn, có nhiều dòng hoặc được quản lý trong repository tài liệu riêng.

~~~java
@ExampleObject(
    name = "bulkImport",
    summary = "Tệp nhập dữ liệu số lượng lớn",
    description = "Ví dụ JSON đầy đủ được lưu ở kho tài liệu.",
    externalValue = "https://docs.example.com/openapi/examples/bulk-import.json"
)
~~~

Không khai báo đồng thời value và externalValue trong cùng một Example Object. Khi dùng externalValue:

- URL phải truy cập được từ môi trường của người xem tài liệu.
- Nội dung đích phải đúng định dạng và phù hợp media type đang mô tả.
- Không dùng URL chứa token, mật khẩu, session id hoặc thông tin nhạy cảm.
- Cân nhắc quyền truy cập, CORS và chứng chỉ TLS nếu Swagger UI tải trực tiếp tài nguyên.
- Nên dùng URL ổn định, có phiên bản hoặc chính sách tương thích.

External example là tham chiếu tới nội dung bên ngoài; OpenAPI không nhúng nội dung đó và không bảo đảm URL luôn hoạt động.

## 10. Chọn ví dụ có giá trị cho người tích hợp

Nhiều ví dụ chỉ hữu ích khi chúng làm rõ những cách sử dụng khác nhau. Nên đặt tên và mô tả theo kịch bản, không chỉ đánh số.

Ví dụ một endpoint tìm kiếm sản phẩm:

| Tên ví dụ | Nội dung minh họa |
| --- | --- |
| keywordOnly | Tìm theo từ khóa, không có bộ lọc khác |
| categoryAndPrice | Kết hợp category và khoảng giá |
| emptyResult | Request hợp lệ nhưng không có kết quả |
| specialCharacters | Từ khóa có dấu hoặc ký tự cần URL encode |

Khi thiết kế example:

- Dùng dữ liệu giả nhưng có ý nghĩa, dễ hiểu và nhất quán giữa các field.
- Bao gồm trường hợp tối thiểu và một trường hợp thực tế có nhiều field.
- Minh họa optional field khi có và khi vắng mặt.
- Với response, chọn ví dụ cho các trạng thái hoặc loại kết quả quan trọng.
- Với lỗi, dùng mã lỗi và status code đúng với exception handler.
- Không dùng dữ liệu khách hàng thật hoặc bí mật production.
- Bảo đảm ví dụ thỏa schema, enum, format và validation.

Không cần tạo hàng chục ví dụ gần như giống nhau. Mỗi ví dụ nên giúp người đọc hiểu thêm một trường hợp hoặc quy ước.

## 11. Ví dụ không phải là validation

Một lỗi phổ biến là cho rằng nếu Swagger UI hiển thị một ví dụ thì server sẽ chấp nhận payload đó. Thực tế:

- ExampleObject chỉ lưu payload mẫu trong tài liệu.
- Schema mô tả cấu trúc và constraint được công bố.
- Bean Validation và logic nghiệp vụ mới kiểm tra dữ liệu ở runtime.
- Message converter/Jackson quyết định cách đọc body và chuyển đổi kiểu.

Ví dụ, khai báo:

~~~java
@ExampleObject(
    name = "invalidQuantity",
    summary = "Ví dụ số lượng bằng 0",
    value = "{\"sku\":\"KB-01\",\"quantity\":0}"
)
~~~

Nếu schema quy định minimum: 1, ví dụ trên là ví dụ không hợp lệ. Có thể chủ ý đưa ví dụ lỗi vào tài liệu để minh họa response 400, nhưng không đặt nó làm payload thành công cho request body. Nên phân tách ví dụ hợp lệ và không hợp lệ bằng nội dung/response tương ứng, tên rõ ràng.

Swagger UI có thể cho phép chọn ví dụ và đưa nó vào vùng Try it out. Người dùng vẫn phải gửi request thực tế; server xử lý theo controller, converter, validation và nghiệp vụ đã cấu hình.

## 12. Kiểm tra examples trong OpenAPI được sinh

Sau khi khai báo annotation, lấy đặc tả JSON/YAML từ springdoc. Endpoint mặc định thường là /v3/api-docs và /v3/api-docs.yaml, trừ khi ứng dụng đã tùy chỉnh đường dẫn.

~~~bash
curl -sS http://localhost:8080/v3/api-docs
curl -sS http://localhost:8080/v3/api-docs.yaml
~~~

Với operation tạo đơn hàng, kiểm tra cấu trúc tương tự:

~~~yaml
paths:
  /api/orders:
    post:
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
            examples:
              singleItem:
                summary: Đơn hàng có một sản phẩm
                value:
                  customerId: C-100
                  items:
                    - sku: KB-01
                      quantity: 2
              multipleItems:
                summary: Đơn hàng có nhiều sản phẩm
                value:
                  customerId: C-200
                  items:
                    - sku: KB-01
                      quantity: 1
                    - sku: MS-02
                      quantity: 3
~~~

Checklist kiểm tra:

1. Các ví dụ có nằm dưới đúng operation và media type không?
2. Mỗi khóa examples có duy nhất trong cùng map không?
3. Summary và description có giải thích rõ sự khác nhau không?
4. Giá trị JSON/XML có parse được và đúng media type không?
5. Payload có tuân theo schema, required, enum và constraint không?
6. Các ví dụ response có đúng status code và schema response không?
7. $ref trong examples có trỏ tới component tồn tại không?
8. externalValue có thể truy cập và không yêu cầu bí mật nhúng trong URL không?
9. Swagger UI có hiển thị đúng danh sách lựa chọn và payload mẫu không?

Nếu @ExampleObject không xuất hiện trong tài liệu, kiểm tra annotation được đặt trong đúng @Content, đúng request/response/parameter và phiên bản swagger-core được springdoc sử dụng. Nếu chỉ thấy một ví dụ, kiểm tra code có đang đặt example đơn lẻ cùng examples hoặc metadata khác ghi đè content hay không.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Chỉ có một ví dụ trong Swagger UI | Dùng example thay vì examples, hoặc annotation đặt sai cấp | Khai báo mảng @ExampleObject trong @Content(examples = {...}) |
| JSON example không parse được | Chuỗi value chưa escape đúng trong Java | Escape dấu ngoặc kép hoặc dùng externalValue |
| Ví dụ không khớp schema | Dữ liệu mẫu thiếu field hoặc sai type/enum | Đối chiếu schema và kiểm thử payload |
| $ref example bị lỗi | Component example chưa được định nghĩa | Thêm components.examples và kiểm tra ref |
| externalValue không tải được | URL sai, cần đăng nhập, CORS hoặc TLS lỗi | Kiểm tra URL từ môi trường trình duyệt |
| Ví dụ query hiển thị như object JSON | Đặt example ở cấp schema/content thay vì parameter | Dùng @Parameter(examples = {...}) |
| Request body có ví dụ XML nhưng endpoint trả 415 | Controller hoặc converter không hỗ trợ XML | Đồng bộ consumes và message converter |
| Ví dụ lỗi được dùng làm payload thành công | Không phân biệt ví dụ request hợp lệ với ví dụ response lỗi | Đặt ví dụ lỗi trong response có status tương ứng |

## 14. Quy trình thiết kế nhiều ví dụ

Khi cần công bố nhiều ví dụ cho một operation:

1. Xác định media type và schema của request hoặc response.
2. Chọn các kịch bản khác nhau mà người tích hợp cần hiểu.
3. Đặt tên ngắn, có ý nghĩa cho từng ví dụ.
4. Dùng @ExampleObject với summary, description và value, hoặc externalValue nếu nội dung lớn.
5. Gắn mảng examples vào đúng @Content; với parameter thì dùng @Parameter(examples = ...).
6. Tái sử dụng components.examples khi cùng một payload xuất hiện ở nhiều operation.
7. Kiểm tra JSON/YAML sinh ra, Swagger UI và payload runtime.

Với một kiểu nội dung như application/json, nhiều ví dụ giúp thể hiện các kịch bản khác nhau mà không cần tạo thêm endpoint hoặc schema trùng lặp. Khi ví dụ nhất quán với schema và hành vi thực tế, tài liệu springdoc trở nên dễ đọc và hữu ích hơn cho người tích hợp.

## Tài liệu tham khảo

- [OpenAPI Specification – Example Object](https://spec.openapis.org/oas/latest.html#example-object)
- [OpenAPI Specification – Media Type Object](https://spec.openapis.org/oas/latest.html#media-type-object)
- [OpenAPI Specification – Parameter Object](https://spec.openapis.org/oas/latest.html#parameter-object)
- [Swagger Core – @ExampleObject Annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/media/ExampleObject.html)
- [springdoc-openapi – Documentation](https://springdoc.org/)
