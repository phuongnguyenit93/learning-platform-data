# Đối chiếu ví dụ với schema mà ví dụ thuộc về

Ví dụ request và response chỉ hữu ích khi dữ liệu trong ví dụ phù hợp với schema của đúng operation và media type. Một ví dụ có thể là JSON hợp lệ nhưng vẫn sai contract: thiếu property bắt buộc, dùng enum không tồn tại, sai format ngày giờ, vượt giới hạn số hoặc đặt một field chỉ dành cho response vào request body.

Với Spring Boot và springdoc-openapi, cần kiểm tra hai việc riêng:

1. Ví dụ được đặt đúng vị trí trong OpenAPI document và gắn với đúng schema, parameter, response và media type.
2. Giá trị ví dụ thực sự thỏa mãn schema mà nó tham chiếu hoặc mô tả.

Swagger UI hiển thị ví dụ không có nghĩa ví dụ đã được xác thực. Springdoc có thể đưa annotation và metadata vào OpenAPI document, nhưng việc bảo đảm mọi Example Object tương thích với schema cần validator hoặc contract test riêng.

## 1. Ví dụ thuộc về schema nào?

Một OpenAPI document có thể có ví dụ ở nhiều cấp. Trước khi kiểm tra dữ liệu, xác định ví dụ đang mô tả loại giá trị nào:

| Vị trí | Ví dụ mô tả | Schema cần đối chiếu |
|---|---|---|
| Schema Object | Giá trị minh họa cho model hoặc property | Schema tại chính vị trí đó |
| Parameter Object | Giá trị của path, query, header hoặc cookie parameter | Schema của parameter và quy tắc serialization |
| Request Body / Media Type Object | Body client gửi lên | Schema dưới đúng media type |
| Response / Media Type Object | Body server trả về theo status | Schema của response và media type |
| Header Object | Giá trị header được gửi hoặc trả về | Schema của header |
| Components / Examples | Ví dụ dùng lại ở nhiều operation | Schema của từng vị trí tham chiếu |

Ví dụ Product có thể xuất hiện ở cả request và response, nhưng không phải mọi trường hợp đều dùng cùng một shape. Request có thể yêu cầu name và price, trong khi response có id, createdAt và trạng thái do server tạo. Đối chiếu ví dụ response với request schema sẽ tạo kết quả sai dù cả hai đều nói về Product.

Một ví dụ cần được xác định bằng đủ ngữ cảnh: operation, hướng dữ liệu (request/response), status code, media type và schema. Không chỉ tìm một schema có tên gần giống rồi dùng nó cho mọi ví dụ.

## 2. Phân biệt example trong Schema Object và examples của Media Type Object

OpenAPI có hai nơi thường được dùng để khai báo ví dụ:

- Schema Object có thể chứa ví dụ cho giá trị dữ liệu của schema.
- Media Type Object có thể chứa example đơn hoặc examples dạng map các Example Object.

Ví dụ schema:

~~~yaml
components:
  schemas:
    CreateProductRequest:
      type: object
      required:
        - name
        - price
      properties:
        name:
          type: string
          minLength: 1
          maxLength: 80
          example: Bút bi
        price:
          type: number
          exclusiveMinimum: 0
          example: 12500
~~~

Ví dụ gắn với media type:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateProductRequest'
      examples:
        standard:
          summary: Sản phẩm thông thường
          value:
            name: Bút bi
            price: 12500
        premium:
          summary: Sản phẩm có giá cao hơn
          value:
            name: Bút máy
            price: 250000
~~~

Schema example thường minh họa một giá trị hoặc property. Media type examples thể hiện toàn bộ representation được gửi hoặc nhận, có tên, summary và description riêng. Khi có nhiều tình huống thực tế, dùng examples ở Media Type Object để phân biệt từng case.

Trong cùng một Media Type Object, example và examples là hai cách khai báo loại trừ lẫn nhau. Không khai báo cả hai ở cùng vị trí. Nếu media type có example hoặc examples, ví dụ tại media type sẽ ghi đè ví dụ được đặt trong schema cho mục đích hiển thị representation.

## 3. Khác biệt giữa OpenAPI 3.0 và 3.1

Khi kiểm tra ví dụ, cần biết document đang dùng phiên bản OpenAPI nào:

| Nội dung | OpenAPI 3.0 | OpenAPI 3.1 |
|---|---|---|
| Schema Object | Dựa trên subset JSON Schema được OpenAPI định nghĩa | Dựa trên JSON Schema Draft 2020-12 và OpenAPI vocabulary |
| Ví dụ ở schema | Dùng keyword example đơn | Hỗ trợ examples theo JSON Schema; example đơn còn vì tương thích |
| Nullable | Có keyword nullable | Dùng JSON Schema type union, ví dụ type: [string, "null"] |
| Boolean schema | Hạn chế hơn | Có thể dùng theo JSON Schema |
| Validator | Cần hỗ trợ OpenAPI 3.0 schema dialect | Cần hỗ trợ JSON Schema 2020-12 và OpenAPI dialect/keywords |

Không dùng validator JSON Schema Draft 2020-12 mặc định cho mọi schema OpenAPI 3.0. Ngược lại, không bỏ qua semantics của JSON Schema 2020-12 khi document là OpenAPI 3.1.

Property examples trong Schema Object của OpenAPI 3.1 là mảng JSON Schema. Trường examples trong Media Type Object lại là map Example Object có key định danh từng ví dụ. Hai cấu trúc cùng tên nhưng nằm ở hai cấp và có ý nghĩa khác nhau.

## 4. Example Object có value hoặc externalValue

Example Object hỗ trợ metadata và nguồn dữ liệu:

| Field | Ý nghĩa |
|---|---|
| summary | Tiêu đề ngắn cho ví dụ |
| description | Giải thích ngữ cảnh và cách dùng |
| value | Giá trị ví dụ nhúng trong OpenAPI document |
| externalValue | URI trỏ tới nội dung ví dụ nằm bên ngoài |

value và externalValue loại trừ lẫn nhau. Dùng value cho JSON nhỏ, dễ đọc và có thể review cùng code. Dùng externalValue khi payload lớn, là file nhị phân, hoặc khó biểu diễn trực tiếp trong YAML/JSON.

Ví dụ nhúng:

~~~yaml
examples:
  validProduct:
    summary: Sản phẩm hợp lệ
    description: Body tối thiểu để tạo sản phẩm.
    value:
      name: Bút bi
      price: 12500
      category: STATIONERY
~~~

Ví dụ ngoài:

~~~yaml
examples:
  productImportCsv:
    summary: File CSV nhập sản phẩm
    externalValue: https://docs.example.com/examples/products-import.csv
~~~

Khi dùng externalValue, kiểm tra URL có thể truy cập trong môi trường người dùng tài liệu, nội dung được version hóa và file thực tế khớp media type/schema. OpenAPI document chỉ lưu liên kết; validator không nhất thiết tải và kiểm tra file bên ngoài.

## 5. Đặt ví dụ request bằng springdoc annotations

Springdoc đọc Swagger annotations để tạo OpenAPI document. Với request body, dùng @Content và @ExampleObject:

~~~java
@Operation(
    operationId = "createProduct",
    summary = "Tạo sản phẩm mới",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        description = "Thông tin cần thiết để tạo sản phẩm.",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = CreateProductRequest.class),
            examples = {
                @ExampleObject(
                    name = "stationery",
                    summary = "Sản phẩm văn phòng phẩm",
                    value = """
                        {
                          "name": "Bút bi",
                          "price": 12500,
                          "category": "STATIONERY"
                        }
                        """
                ),
                @ExampleObject(
                    name = "notebook",
                    summary = "Sổ tay",
                    value = """
                        {
                          "name": "Sổ tay A5",
                          "price": 32000,
                          "category": "NOTEBOOK"
                        }
                        """
                )
            }
        )
    )
)
@PostMapping("/api/products")
ResponseEntity<ProductResponse> create(
    @Valid @RequestBody CreateProductRequest request
) {
    ProductResponse created = productService.create(request);
    return ResponseEntity.created(
        URI.create("/api/products/" + created.id())
    ).body(created);
}
~~~

Lưu ý có hai annotation cùng tên RequestBody:

- org.springframework.web.bind.annotation.RequestBody gắn vào tham số controller để Spring MVC đọc body.
- io.swagger.v3.oas.annotations.parameters.RequestBody mô tả request body trong OpenAPI.

Trong ví dụ, annotation Swagger được ghi đầy đủ package để tránh nhầm import. Nếu dùng @Operation.requestBody, annotation này có thể định nghĩa content và examples cho tài liệu mà không thay đổi cách controller nhận request.

Mỗi ExampleObject có name duy nhất trong phạm vi map examples, summary rõ nghĩa và value phải là JSON hợp lệ. Không đưa chuỗi JSON bị escape sai hoặc bọc toàn bộ object thành một string nếu media type là application/json và mục tiêu là ví dụ object.

Các đoạn Java dùng text block để dễ đọc, yêu cầu Java 15 trở lên. Với dự án dùng Java cũ hơn, thay text block bằng chuỗi JSON đã escape đúng hoặc nạp ví dụ từ file fixture.

## 6. Đặt ví dụ response theo status code

Response example phải khớp schema của response tương ứng, không dùng ví dụ thành công cho response lỗi:

~~~java
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Sản phẩm được tạo",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ProductResponse.class),
            examples = @ExampleObject(
                name = "createdProduct",
                summary = "Sản phẩm vừa tạo",
                value = """
                    {
                      "id": "7c1e2b3a-4d5f-6789-8abc-def012345678",
                      "name": "Bút bi",
                      "price": 12500,
                      "category": "STATIONERY",
                      "createdAt": "2026-11-20T09:30:00Z"
                    }
                    """
            )
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Request không hợp lệ",
        content = @Content(
            mediaType = MediaType.APPLICATION_PROBLEM_JSON_VALUE,
            schema = @Schema(implementation = ValidationProblem.class),
            examples = @ExampleObject(
                name = "invalidPrice",
                summary = "Giá sản phẩm không hợp lệ",
                value = """
                    {
                      "type": "https://api.example.com/problems/validation-error",
                      "title": "Request validation failed",
                      "status": 400,
                      "detail": "Price must be greater than zero.",
                      "errors": [
                        {
                          "field": "price",
                          "code": "Positive",
                          "message": "Price must be greater than zero."
                        }
                      ]
                    }
                    """
            )
        )
    )
})
~~~

Ví dụ 201 cần thỏa ProductResponse; ví dụ 400 cần thỏa ValidationProblem. Không kiểm tra ví dụ 400 với ProductResponse chỉ vì hai ví dụ xuất hiện trên cùng operation.

Nếu response 204 không có body, không gắn JSON example cho response đó. Nếu response có header Location, ETag hoặc Retry-After, mô tả và đưa ví dụ header ở Header Object tương ứng.

## 7. Ví dụ cho path, query và header parameter

Ví dụ parameter phải phù hợp schema và cách giá trị được serialize lên HTTP request. Ví dụ query parameter:

~~~java
@GetMapping("/api/products")
List<ProductResponse> search(
    @Parameter(
        name = "status",
        description = "Trạng thái sản phẩm cần lọc.",
        examples = {
            @ExampleObject(name = "active", value = "ACTIVE"),
            @ExampleObject(name = "archived", value = "ARCHIVED")
        }
    )
    @RequestParam(required = false) ProductStatus status
) {
    return productService.search(status);
}
~~~

Ví dụ request URL tương ứng:

~~~http
GET /api/products?status=ACTIVE
Accept: application/json
~~~

Với parameter object, example thể hiện giá trị parameter theo cách nó xuất hiện trên wire. Nếu parameter là array và dùng form, pipeDelimited hoặc spaceDelimited, kiểm tra ví dụ đã được serialize đúng theo style/explode. Một mảng JSON như ["ACTIVE","ARCHIVED"] không nhất thiết là ví dụ wire đúng cho query parameter.

Với header parameter, giá trị ví dụ phải phù hợp cú pháp header. Với path parameter, kiểm tra encoding của ký tự đặc biệt và format được công bố.

## 8. Ví dụ multipart và form data

Ví dụ cho multipart cần đối chiếu cả schema tổng thể lẫn encoding của từng part. Không dùng JSON object làm ví dụ multipart nếu client thực tế phải gửi từng part riêng.

~~~yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        required:
          - metadata
          - file
        properties:
          metadata:
            $ref: '#/components/schemas/ProductImportMetadata'
          file:
            type: string
            format: binary
      encoding:
        metadata:
          contentType: application/json
        file:
          contentType: text/csv
      examples:
        importProducts:
          summary: Metadata cho một file CSV
          value:
            metadata:
              category: STATIONERY
              replaceExisting: false
            file: products.csv
~~~

Trong ví dụ multipart, giá trị file trong Example Object chỉ mang tính minh họa tên file; payload thực tế là binary/text part được gửi qua multipart boundary. Nếu cần chỉ rõ nội dung CSV, cung cấp file externalValue hoặc tài liệu ví dụ riêng và mô tả encoding/content type của part.

Với application/x-www-form-urlencoded, mỗi property được serialize thành field form. Kiểm tra kiểu chuỗi cuối cùng, array serialization, ký tự Unicode và percent-encoding. Một object JSON lồng nhau không tự động trở thành một form field theo cùng cách trên mọi client.

## 9. Đối chiếu ví dụ với các constraint của schema

Khi review một ví dụ, kiểm tra các nhóm constraint:

| Schema constraint | Điều cần kiểm tra trong ví dụ |
|---|---|
| type | JSON value đúng kiểu string, number, integer, boolean, object hoặc array |
| required | Có đủ property bắt buộc |
| enum / const | Giá trị nằm trong tập cho phép hoặc bằng hằng số |
| format | Ngày giờ, UUID, email, URI đúng định dạng |
| minLength / maxLength | Chuỗi nằm trong giới hạn |
| pattern | Chuỗi khớp biểu thức chính quy |
| minimum / maximum | Số nằm trong giới hạn |
| exclusiveMinimum / exclusiveMaximum | Không chạm ngưỡng bị loại trừ |
| multipleOf | Số là bội số theo quy tắc |
| minItems / maxItems | Mảng có số phần tử hợp lệ |
| uniqueItems | Mảng không có phần tử trùng nếu yêu cầu |
| items | Từng phần tử thỏa schema item |
| properties | Mỗi property có kiểu và constraint phù hợp |
| additionalProperties | Field ngoài danh sách có được phép hay không |
| oneOf / anyOf / allOf | Giá trị thỏa đúng tổ hợp schema |
| discriminator | Giá trị phân loại khớp schema con |

Không chỉ kiểm tra JSON parse được. Ví dụ sau parse thành công nhưng sai schema nếu price phải lớn hơn 0 và category chỉ nhận các giá trị enum đã công bố:

~~~json
{
  "name": "Bút bi",
  "price": -10,
  "category": "UNKNOWN"
}
~~~

Ví dụ cũng có thể sai vì thiếu field required, sai định dạng date-time, có thêm property bị cấm hoặc dùng sai kiểu number/integer. Các trường hợp này cần được phát hiện trước khi đưa ví dụ vào tài liệu.

## 10. Đối chiếu schema có $ref và schema dùng lại

OpenAPI thường đặt schema trong components rồi tham chiếu bằng $ref. Ví dụ phải được kiểm tra theo schema sau khi giải quyết reference, không chỉ theo object chứa $ref.

~~~yaml
components:
  schemas:
    ProductCode:
      type: string
      pattern: '^[A-Z]{3}-[0-9]{4}$'
      example: PEN-1024
    CreateProductRequest:
      type: object
      required:
        - productCode
        - name
      properties:
        productCode:
          $ref: '#/components/schemas/ProductCode'
        name:
          type: string
          minLength: 1
          maxLength: 80

paths:
  /api/products:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateProductRequest'
            examples:
              valid:
                value:
                  productCode: PEN-1024
                  name: Bút bi
~~~

Ví dụ valid thỏa ProductCode vì chuỗi khớp pattern. Giá trị PEN-1 hoặc pen-1024 sẽ không hợp lệ dù vẫn là string. Nếu validator không giải quyết local reference, nó có thể bỏ qua constraint của ProductCode hoặc báo lỗi unresolved reference; đó là lỗi cấu hình kiểm thử, không phải bằng chứng ví dụ hợp lệ.

Khi dùng external reference, cần cố định nguồn và version của schema để test có thể lặp lại. Không để CI tải schema tùy ý từ một URL có nội dung thay đổi theo thời gian.

## 11. Đối chiếu oneOf, anyOf, allOf và discriminator

Schema hợp thành thường xuất hiện khi API có nhiều loại resource hoặc payload. Ví dụ phải khớp đúng nhánh:

- allOf: giá trị phải thỏa tất cả schema được kết hợp.
- anyOf: giá trị phải thỏa ít nhất một schema.
- oneOf: giá trị phải thỏa chính xác một schema trong tập.
- discriminator: giúp chọn schema con theo property phân loại; nó không thay thế các constraint của schema con.

Ví dụ:

~~~yaml
components:
  schemas:
    Payment:
      oneOf:
        - $ref: '#/components/schemas/CardPayment'
        - $ref: '#/components/schemas/BankTransfer'
      discriminator:
        propertyName: method
        mapping:
          CARD: '#/components/schemas/CardPayment'
          BANK_TRANSFER: '#/components/schemas/BankTransfer'

    CardPayment:
      type: object
      required: [method, last4]
      properties:
        method:
          type: string
          enum: [CARD]
        last4:
          type: string
          pattern: '^[0-9]{4}$'

    BankTransfer:
      type: object
      required: [method, bankCode, accountNumber]
      properties:
        method:
          type: string
          enum: [BANK_TRANSFER]
        bankCode:
          type: string
        accountNumber:
          type: string
~~~

Ví dụ card hợp lệ:

~~~yaml
value:
  method: CARD
  last4: '1234'
~~~

Ví dụ bank transfer hợp lệ:

~~~yaml
value:
  method: BANK_TRANSFER
  bankCode: VCB
  accountNumber: '0123456789'
~~~

Ví dụ method CARD nhưng có bankCode và thiếu last4 không thỏa CardPayment. Nếu schema con cho phép additional properties, việc có thêm bankCode có thể không làm nhánh card thất bại; nếu cần cấm field lạ, đặt additionalProperties: false hoặc unevaluatedProperties theo dialect phù hợp.

Với oneOf, một ví dụ vô tình thỏa hai nhánh sẽ không hợp lệ vì oneOf yêu cầu đúng một nhánh. Với anyOf, ví dụ thỏa nhiều nhánh vẫn có thể hợp lệ. Đây là khác biệt quan trọng khi kiểm tra ví dụ cho polymorphic DTO.

## 12. Ví dụ request và response khi có readOnly/writeOnly

OpenAPI hỗ trợ readOnly và writeOnly để biểu diễn property chỉ đọc hoặc chỉ ghi:

- readOnly: property thuộc response; client không gửi property này trong request.
- writeOnly: property thuộc request; server không trả property này trong response.

Ví dụ schema Product bên dưới dùng cú pháp exclusiveMinimum dạng số của OpenAPI 3.1. Nếu document là OpenAPI 3.0, biểu diễn cùng giới hạn bằng minimum: 0 và exclusiveMinimum: true.

Ví dụ:

~~~yaml
components:
  schemas:
    Product:
      type: object
      required: [name, price]
      properties:
        id:
          type: string
          format: uuid
          readOnly: true
        name:
          type: string
          minLength: 1
        price:
          type: number
          exclusiveMinimum: 0
        internalNote:
          type: string
          writeOnly: true
~~~

Ví dụ request:

~~~yaml
name: Bút bi
price: 12500
internalNote: Hàng cần kiểm tra tem
~~~

Ví dụ response:

~~~yaml
id: 7c1e2b3a-4d5f-6789-8abc-def012345678
name: Bút bi
price: 12500
~~~

Không đưa id vào ví dụ request nếu contract đánh dấu id là readOnly. Không đưa internalNote vào response nếu contract đánh dấu writeOnly. Nếu dùng chung một schema cho cả request và response, kiểm tra tool validator có hiểu ngữ cảnh direction hay không; nhiều JSON Schema validator thuần không tự áp dụng semantics request/response của OpenAPI.

Với API quan trọng, DTO request và response riêng thường giúp ví dụ và schema dễ hiểu hơn, đồng thời tránh vô tình công bố field nội bộ.

## 13. Dùng reusable examples trong components

Khi nhiều operation dùng cùng ví dụ, đặt Example Object trong components/examples rồi tham chiếu bằng $ref:

~~~yaml
components:
  examples:
    standardProduct:
      summary: Sản phẩm văn phòng phẩm tiêu chuẩn
      description: Ví dụ dùng trong create và update product.
      value:
        name: Bút bi
        price: 12500
        category: STATIONERY

paths:
  /api/products:
    post:
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateProductRequest'
            examples:
              standard:
                $ref: '#/components/examples/standardProduct'
~~~

Tái sử dụng ví dụ giảm việc copy/paste nhưng tạo ra một trách nhiệm mới: nếu schema của một operation thay đổi, ví dụ dùng chung có thể không còn hợp lệ với operation đó. Một Example Object được tham chiếu từ nhiều vị trí phải tương thích với tất cả schema đích hoặc được tách thành các ví dụ chuyên biệt.

Đặt tên example theo tình huống hoặc intent, ví dụ standardProduct, invalidPrice hoặc archivedProduct. Tránh đặt tên quá chung như example1 hoặc data2 vì khó xác định ví dụ thuộc case nào khi review.

## 14. Ví dụ cho error response cũng phải khớp error schema

Không chỉ ví dụ thành công mới cần kiểm tra. Error example cần khớp schema lỗi và phản ánh đúng status/media type:

~~~yaml
components:
  schemas:
    ValidationProblem:
      type: object
      required: [type, title, status, errors]
      properties:
        type:
          type: string
          format: uri
        title:
          type: string
        status:
          type: integer
          enum: [400]
        detail:
          type: string
        errors:
          type: array
          items:
            $ref: '#/components/schemas/FieldViolation'
    FieldViolation:
      type: object
      required: [field, code, message]
      properties:
        field:
          type: string
        code:
          type: string
        message:
          type: string

paths:
  /api/products:
    post:
      responses:
        '400':
          description: Request validation failed
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ValidationProblem'
              examples:
                invalidPrice:
                  value:
                    type: https://api.example.com/problems/validation-error
                    title: Request validation failed
                    status: 400
                    detail: Price must be greater than zero.
                    errors:
                      - field: price
                        code: Positive
                        message: Price must be greater than zero.
~~~

Trong ví dụ trên, status trong body là integer 400 và response status là '400'. Đây là hai giá trị ở hai lớp khác nhau nhưng cần nhất quán. Nếu schema error không có field errors hoặc status là string, ví dụ sẽ không khớp.

Với RFC 9457, các member chuẩn gồm type, title, status, detail và instance; extension member như errors cần được định nghĩa bởi API. Nếu API dùng application/problem+json, ví dụ phải là Problem Details JSON và không được nhầm với một object lỗi tùy ý mà không mô tả media type.

## 15. Ví dụ trong annotation không thay thế kiểm tra runtime

@ExampleObject là metadata cho OpenAPI document. Nó không gửi request, không chạy Bean Validation và không chứng minh controller có thể xử lý payload.

Để kiểm tra ví dụ với Java DTO, có thể deserialize và chạy Jakarta Bean Validation:

~~~java
class ProductExampleTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final Validator validator =
        Validation.buildDefaultValidatorFactory().getValidator();

    @Test
    void productRequestExamplePassesBeanValidation() throws Exception {
        String example = """
            {
              "name": "Bút bi",
              "price": 12500,
              "category": "STATIONERY"
            }
            """;

        CreateProductRequest request =
            objectMapper.readValue(example, CreateProductRequest.class);

        Set<ConstraintViolation<CreateProductRequest>> violations =
            validator.validate(request);

        assertThat(violations).isEmpty();
    }
}
~~~

Test này kiểm tra ví dụ với Jackson và Bean Validation trên DTO Java. Nó hữu ích để phát hiện lỗi annotation hoặc ví dụ không deserialize được, nhưng chưa chứng minh ví dụ khớp toàn bộ OpenAPI Schema Object. Schema có thể chứa constraint bổ sung như oneOf, discriminator, additionalProperties hoặc format assertion mà Bean Validation không đại diện đầy đủ.

Nếu DTO có custom Jackson module, naming strategy hoặc deserializer, hãy dùng cùng ObjectMapper configuration với ứng dụng. Một ObjectMapper mới mặc định có thể deserialize khác runtime, nhất là với Java Time, enum, polymorphism và custom serializers.

## 16. Tự động xác thực example value với JSON Schema

Để xác minh dữ liệu theo schema, dùng JSON Schema validator có hỗ trợ dialect tương ứng với OpenAPI document. Một lựa chọn Java là NetworkNT JSON Schema Validator, hỗ trợ JSON Schema Draft 2020-12 và có hỗ trợ dialect OpenAPI 3.0/3.1.

Quy trình kiểm tra:

1. Parse OpenAPI document.
2. Tìm từng operation và media type.
3. Lấy schema của request body hoặc response.
4. Giải quyết local/external $ref theo nguồn đã được kiểm soát.
5. Lấy từng example.value hoặc dữ liệu từ externalValue.
6. Chọn validator/dialect tương ứng với openapi version và schema dialect.
7. Validate example instance.
8. Báo lỗi kèm operation, direction, status code, media type, example name và JSON path.

Ví dụ, validator nhận schema CreateProductRequest và example standard. Nếu thiếu required name hoặc price âm, test phải báo example không hợp lệ.

Với một JSON Schema Draft 2020-12 độc lập, không chứa reference bên ngoài, đoạn kiểm tra tối giản có thể như sau:

~~~java
SchemaRegistry registry = SchemaRegistry.withDefaultDialect(
    SpecificationVersion.DRAFT_2020_12
);
Schema schema = registry.getSchema(schemaJson);

List<Error> errors = schema.validate(
    exampleJson,
    InputFormat.JSON,
    executionContext -> executionContext.executionConfig(
        config -> config.formatAssertionsEnabled(true)
    )
);

assertThat(errors).isEmpty();
~~~

Đây là ví dụ cho schema JSON độc lập. Khi schema được trích từ OpenAPI, cấu hình SchemaRegistry theo OpenAPI dialect phù hợp, resolve references trước khi validate và áp dụng quy tắc readOnly/writeOnly theo hướng message. Không thay thế OAS 3.0 hoặc OAS 3.1 dialect bằng Draft 2020-12 thuần.

### Lưu ý khi dùng JSON Schema validator

- Không đưa nguyên OpenAPI document vào validator như thể toàn bộ document là JSON Schema. Chỉ validate schema tại đúng vị trí.
- Phải resolve $ref và giữ base URI để relative reference hoạt động.
- Với OpenAPI 3.0, dùng dialect/adapter hiểu nullable và các khác biệt của OAS 3.0.
- Với OpenAPI 3.1, dùng JSON Schema 2020-12 cùng OpenAPI dialect/vocabulary thích hợp.
- Kiểm tra format assertion có được bật hay không; một số validator mặc định chỉ ghi nhận format thay vì từ chối giá trị sai.
- Xử lý readOnly/writeOnly theo hướng request/response. Validator JSON Schema thuần có thể không biết hướng của HTTP message.
- ExternalValue cần được tải từ nguồn được kiểm soát và xác thực theo media type; không tải URL tùy ý từ tài liệu không tin cậy.

Không coi kết quả validator là chân lý tuyệt đối nếu validator không hỗ trợ một keyword hoặc dialect. Ghi rõ giới hạn và kiểm tra bằng công cụ hiểu đúng phiên bản OpenAPI của dự án.

## 17. Kiểm tra ví dụ đã được springdoc đưa vào document

Sau khi khai báo annotations, gọi endpoint /v3/api-docs và xác minh examples xuất hiện đúng vị trí. Ví dụ MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ProductOpenApiExamplesTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesRequestExamplesForJsonMediaType() throws Exception {
        mockMvc.perform(get("/v3/api-docs")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.paths['/api/products'].post.requestBody.content['application/json'].schema.$ref"
            ).value("#/components/schemas/CreateProductRequest"))
            .andExpect(jsonPath(
                "$.paths['/api/products'].post.requestBody.content['application/json'].examples.stationery.summary"
            ).value("Sản phẩm văn phòng phẩm"))
            .andExpect(jsonPath(
                "$.paths['/api/products'].post.requestBody.content['application/json'].examples.stationery.value.name"
            ).value("Bút bi"));
    }
}
~~~

Ví dụ response:

~~~java
@Test
void publishesErrorExampleUnderItsOwnStatusAndMediaType() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.paths['/api/products'].post.responses['400'].content['application/problem+json'].examples.invalidPrice.value.status"
        ).value(400))
        .andExpect(jsonPath(
            "$.paths['/api/products'].post.responses['201'].content['application/json'].examples.createdProduct.value.id"
        ).exists());
}
~~~

Các JSONPath trên giả định tên example stationery, invalidPrice và createdProduct như trong annotations. Nếu springdoc hoặc swagger-core version thay đổi cách chuyển annotation value thành JSON node, kiểm tra raw /v3/api-docs và điều chỉnh assertion theo document được sinh ra. Không bỏ qua test chỉ vì Swagger UI vẫn hiển thị một ví dụ nào đó; cần xác minh schema và ví dụ nằm cùng media type/status mong muốn.

## 18. Kiểm tra ví dụ trong response runtime

Một example trong OpenAPI là tài liệu minh họa, không nhất thiết là response cố định của server. Tuy nhiên, nếu example mô tả một response cụ thể mà API cam kết có thể trả, nên có test runtime tương ứng:

~~~java
@Test
void createProductResponseHasTheDocumentedShape() throws Exception {
    mockMvc.perform(post("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Bút bi",
                  "price": 12500,
                  "category": "STATIONERY"
                }
                """))
        .andExpect(status().isCreated())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").isNotEmpty())
        .andExpect(jsonPath("$.name").value("Bút bi"))
        .andExpect(jsonPath("$.price").value(12500))
        .andExpect(jsonPath("$.category").value("STATIONERY"))
        .andExpect(jsonPath("$.createdAt").isNotEmpty());
}
~~~

Giá trị id và createdAt được sinh tại runtime nên không cần bằng chuỗi cố định trong example. Test xác minh kiểu và sự hiện diện của field. Nếu example minh họa một response cố định từ fixture hoặc sandbox, có thể so sánh giá trị cụ thể.

Với response lỗi, gửi request tạo lỗi có kiểm soát và kiểm tra error body. Không giả định error example được trả nguyên văn bởi exception handler; nó có thể chỉ là một ví dụ minh họa. Điều cần bảo đảm là response thực tế thỏa cùng schema và semantics.

## 19. Đối chiếu example với schema bằng validator độc lập

Một quy trình tự động nên duyệt toàn bộ examples trong document:

~~~text
OpenAPI document
       |
       v
Find operations and parameters
       |
       v
Find request/response media types
       |
       v
Resolve schema references
       |
       v
Read inline examples or controlled external examples
       |
       v
Validate each example against its schema
       |
       +---- invalid ----> report operation, media type, example, JSON path
       |
       +---- valid ------> continue
       |
       v
Run runtime contract tests
~~~

Thông tin cần có trong báo cáo lỗi:

- HTTP method và path.
- Request hay response; nếu là response thì kèm status code.
- Media type.
- Tên example.
- Schema đã được resolve.
- JSON path của vị trí không hợp lệ.
- Constraint bị vi phạm và giá trị liên quan nếu an toàn để hiển thị.

Ví dụ lỗi hữu ích: POST /api/products, request, application/json, example premium, path $.price, vi phạm exclusiveMinimum. Cách báo này giúp người viết tài liệu tìm đúng ví dụ thay vì phải đọc toàn bộ validator stack trace.

Không validate tất cả ví dụ bằng một schema chung. Mỗi example phải được lấy từ đúng vị trí OpenAPI và kiểm tra với schema thuộc về vị trí đó. Ví dụ của response 409 không được so với schema response 201.

## 20. Kiểm tra ví dụ bên ngoài và ví dụ nhạy cảm

Ví dụ ngoài document có một số rủi ro:

- URL externalValue có thể hỏng hoặc trả nội dung khác theo thời gian.
- File có thể không còn khớp media type được khai báo.
- Dữ liệu mẫu có thể chứa thông tin cá nhân hoặc bí mật thật.
- Một URL không tin cậy có thể khiến CI tải dữ liệu không mong muốn.

Đối với externalValue:

1. Lưu file ví dụ trong repository hoặc artifact có version.
2. Ghim URL hoặc checksum nếu file được phân phối ngoài repository.
3. Chỉ tải từ host được cho phép trong pipeline.
4. Kiểm tra HTTP status, content type và kích thước trước khi parse.
5. Validate nội dung với schema tương ứng.
6. Không đưa credential, token, cookie, email/điện thoại thật hoặc dữ liệu khách hàng vào ví dụ.

Nếu example có API key hoặc bearer token, dùng giá trị giả được đánh dấu rõ ràng. Không dùng token đã hết hạn của môi trường thật làm ví dụ.

## 21. Các lỗi thường gặp khi đối chiếu examples

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Swagger UI hiển thị example nhưng example sai kiểu | ExampleObject.value không khớp schema | Validate value với schema của media type |
| Ví dụ request có id do server sinh | Dùng response example cho request schema | Tạo request example riêng |
| Ví dụ response thiếu required field | Copy request payload làm response | Đối chiếu với schema response đúng status |
| Example hợp lệ JSON nhưng sai enum | Chỉ parse JSON, không validate schema | Kiểm tra enum/const và discriminator |
| Example ngày giờ bị từ chối | Format sai hoặc validator chưa bật format assertion | Dùng RFC 3339 phù hợp và cấu hình format validator |
| Ví dụ trong parameter hiển thị như object JSON | Không xét style/explode hoặc serialization | Kiểm tra giá trị cuối cùng trên wire |
| example và examples cùng khai báo | Dùng đồng thời hai field loại trừ nhau | Chọn một cách khai báo ở Media Type Object |
| Schema example bị media type example ghi đè | Đặt ví dụ ở cả hai cấp | Xác định cấp sở hữu ví dụ cần hiển thị |
| $ref không được validator resolve | Thiếu base URI hoặc reference loader | Cấu hình resolver và cố định nguồn schema |
| oneOf báo nhiều nhánh khớp | Các schema con chồng lấn | Làm discriminator/constraint phân biệt rõ hoặc dùng anyOf nếu đúng semantics |
| Ví dụ multipart không chạy được trong client | Dùng JSON object thay cho từng part | Mô tả encoding và content type của từng part |
| Runtime nhận request nhưng example test thất bại | OpenAPI schema chặt hơn Bean Validation | Xác định nguồn contract chuẩn và đồng bộ validation |
| ExampleObject value bị hiển thị thành chuỗi | Media type hoặc annotation value không được parse như mong muốn | Kiểm tra /v3/api-docs và khai báo value đúng format |
| External example không tải được | URL riêng tư, sai path hoặc file đã đổi | Đưa file vào nguồn version hóa và kiểm tra link |

## 22. Quy trình review một ví dụ trước khi merge

Với từng ví dụ được thêm hoặc sửa, thực hiện:

1. Xác định ví dụ thuộc request, response, parameter hay header.
2. Xác định đúng operation, status code và media type.
3. Tìm schema trực tiếp hoặc resolve toàn bộ $ref.
4. Kiểm tra required, type, format, enum, bounds, pattern và composition.
5. Kiểm tra readOnly/writeOnly theo hướng request/response.
6. Kiểm tra serialization đối với path/query/header và encoding đối với multipart/form.
7. Parse JSON/YAML hoặc tải externalValue từ nguồn được kiểm soát.
8. Chạy JSON Schema validator đúng dialect.
9. Kiểm tra springdoc đã sinh ví dụ tại đúng vị trí trong /v3/api-docs.
10. Chạy runtime test nếu ví dụ mô tả response/request có hành vi thực thi.
11. Kiểm tra ví dụ không chứa dữ liệu nhạy cảm hoặc credential thật.
12. Review OpenAPI diff để bảo đảm không vô tình đổi schema hoặc xóa example khác.

Nếu một ví dụ không thể được xác thực tự động do external format hoặc custom media type, ghi rõ cách kiểm tra thủ công và giữ fixture có thể tái hiện. Không âm thầm bỏ qua lỗi validator.

## 23. Tài liệu tham khảo

- [OpenAPI Specification 3.1.2 – Media Type Object](https://spec.openapis.org/oas/v3.1.html#media-type-object): schema, example/examples, media type và quy tắc ghi đè.
- [OpenAPI Specification 3.1.2 – Example Object](https://spec.openapis.org/oas/v3.1.html#example-object): summary, description, value và externalValue.
- [OpenAPI Specification 3.1.2 – Working with Examples](https://spec.openapis.org/oas/v3.1.html#working-with-examples): vị trí và semantics của examples.
- [Swagger Core – ExampleObject annotation](https://docs.swagger.io/swagger-core/v2.2.25/apidocs/io/swagger/v3/oas/annotations/media/ExampleObject.html): khai báo ví dụ cho request/response content.
- [Swagger Core – Parameter annotation](https://docs.swagger.io/swagger-core/v2.2.34/apidocs/io/swagger/v3/oas/annotations/Parameter.html): examples cho path, query, header và cookie parameter.
- [NetworkNT JSON Schema Validator](https://github.com/networknt/json-schema-validator): hỗ trợ JSON Schema và OpenAPI 3.0/3.1 dialect.
- [NetworkNT JSON Schema Validator – Quick Start](https://github.com/networknt/json-schema-validator/blob/master/doc/quickstart.md): tải schema, giải quyết reference và validate instance.
- [Springdoc OpenAPI](https://springdoc.org/): sinh OpenAPI document từ Spring Boot và Swagger annotations.

## 24. Tổng kết áp dụng

Đối chiếu ví dụ với schema là một phần của contract testing. Mỗi ví dụ cần gắn đúng schema, đúng hướng request/response, đúng status và đúng media type. Ví dụ phải thỏa constraint của schema sau khi resolve reference, đồng thời phản ánh representation thật trên HTTP wire.

Trong dự án Spring Boot, annotations giúp công bố examples trong OpenAPI; MockMvc hoặc WebTestClient kiểm tra document và hành vi runtime; Bean Validation kiểm tra DTO theo Java constraints; JSON Schema validator kiểm tra giá trị ví dụ theo schema OpenAPI. Kết hợp các lớp kiểm tra này giúp phát hiện ví dụ sai trước khi consumer sao chép chúng vào tích hợp thật.
