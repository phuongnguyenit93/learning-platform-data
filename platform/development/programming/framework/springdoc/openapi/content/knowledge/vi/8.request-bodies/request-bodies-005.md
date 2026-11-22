# Đối tượng, mảng, kiểu nguyên thủy và thân yêu cầu tùy chọn

Trong một HTTP API, request body là phần dữ liệu client gửi đến server để tạo mới, cập nhật hoặc thực hiện một thao tác. Khi mô tả bằng OpenAPI, body không nhất thiết luôn là một object JSON. Nó có thể là object, array, giá trị nguyên thủy như string, number hoặc boolean, dữ liệu nhị phân, biểu mẫu hoặc thậm chí không bắt buộc phải có. Việc chọn đúng cấu trúc giúp client biết chính xác nội dung cần gửi và giúp Spring Boot chuyển dữ liệu vào tham số controller đúng cách.

Với springdoc-openapi, thông tin body thường được suy ra từ tham số có annotation @RequestBody, kiểu Java và các annotation mô tả. Khi cần kiểm soát rõ hơn, ta có thể dùng annotation OpenAPI RequestBody, Content, Schema và ExampleObject. Bài học này tập trung vào hình dạng dữ liệu ở cấp cao nhất của body, sự khác nhau giữa body tùy chọn và field tùy chọn, cùng cách thể hiện các trường hợp đó trong OpenAPI và Spring MVC.

## 1. Request body trong OpenAPI nằm ở đâu?

Trong OpenAPI 3.x, request body được mô tả bằng trường requestBody bên trong một operation. Trường này chứa:

- description: giải thích mục đích hoặc quy tắc của dữ liệu gửi lên.
- required: cho biết toàn bộ request body có bắt buộc hay không.
- content: ánh xạ media type sang cách mô tả nội dung tương ứng.

Ví dụ một operation nhận object JSON:

```yaml
paths:
  /api/v1/products:
    post:
      summary: Tạo sản phẩm
      requestBody:
        required: true
        description: Thông tin sản phẩm cần tạo.
        content:
          application/json:
            schema:
              type: object
              required:
                - name
              properties:
                name:
                  type: string
                price:
                  type: number
      responses:
        '201':
          description: Sản phẩm đã được tạo.
```

content là một map, vì vậy một operation có thể nhận nhiều media type nếu server thực sự hỗ trợ. Ví dụ, cùng một body logic có thể được nhận dưới dạng application/json hoặc application/xml, nhưng mỗi media type cần có schema và cách xử lý phù hợp.

Không nhầm requestBody.required với required trong schema. Trường đầu tiên áp dụng cho toàn bộ body; required trong object schema liệt kê các thuộc tính bắt buộc bên trong object.

## 2. Object JSON: lựa chọn phổ biến cho request có nhiều trường

Object JSON biểu diễn một thực thể hoặc một tập dữ liệu có tên trường. Nó phù hợp khi request có nhiều thuộc tính, cần kiểm tra từng field hoặc có khả năng mở rộng trong tương lai.

Ví dụ:

```json
{
  "name": "Bàn phím cơ",
  "price": 1250000,
  "active": true
}
```

Schema tương ứng:

```yaml
type: object
required:
  - name
  - price
properties:
  name:
    type: string
    minLength: 1
    maxLength: 120
  price:
    type: number
    format: double
    minimum: 0
  active:
    type: boolean
    default: true
```

Trong ví dụ, name và price là field bắt buộc; active có thể được bỏ qua. Khi client không gửi active, server có thể áp dụng giá trị mặc định nếu ứng dụng triển khai hành vi đó. Giá trị default trong OpenAPI mang tính mô tả, không tự động gán giá trị cho DTO hoặc database.

### 2.1. Field bắt buộc và field tùy chọn

Với object schema, danh sách required xác định các field mà client phải cung cấp:

```yaml
type: object
required:
  - email
  - displayName
properties:
  email:
    type: string
    format: email
  displayName:
    type: string
  phone:
    type: string
```

Ở đây email và displayName là bắt buộc; phone là tùy chọn. Field không xuất hiện trong required không bắt buộc phải được gửi. Điều đó không đồng nghĩa server phải chấp nhận mọi giá trị hoặc tự tạo giá trị mặc định.

Trong Java, Bean Validation thường được dùng để kiểm tra dữ liệu:

```java
public record CreateCustomerRequest(
    @NotBlank
    @Email
    String email,

    @NotBlank
    @Size(max = 100)
    String displayName,

    @Size(max = 30)
    String phone
) {
}
```

Khi dùng springdoc, schema có thể được suy ra từ kiểu DTO và annotation validation nếu dependency và cấu hình hỗ trợ. Hãy kiểm tra tài liệu JSON/YAML được sinh ra để xác nhận field nào xuất hiện trong required, format, minLength hoặc maxLength.

### 2.2. Field bị bỏ qua, null và giá trị mặc định

Ba trạng thái này cần được phân biệt:

| Dữ liệu client gửi | Ý nghĩa có thể có |
|---|---|
| Không có field | Client không cung cấp thuộc tính |
| Field có giá trị null | Client cung cấp rõ ràng giá trị rỗng/null |
| Field có giá trị cụ thể | Client cung cấp giá trị đó |

Ý nghĩa nghiệp vụ của field bị bỏ qua và field bằng null phụ thuộc hợp đồng API. Ví dụ, với PATCH, bỏ qua phone có thể nghĩa là giữ nguyên số điện thoại; gửi phone: null có thể nghĩa là xóa số điện thoại. Nếu API không phân biệt được hai trường hợp do cách ánh xạ DTO, cần chọn một quy ước rõ ràng và mô tả trong tài liệu.

OpenAPI 3.0 dùng nullable: true để cho phép giá trị null trong schema:

```yaml
type: object
properties:
  phone:
    type: string
    nullable: true
```

Trong OpenAPI 3.1, null được mô tả theo JSON Schema, ví dụ dùng union type gồm string và null hoặc anyOf. Cú pháp phải khớp với phiên bản OpenAPI mà tài liệu công bố. Không trộn nullable của 3.0 vào schema 3.1 như thể hai cách viết có ý nghĩa giống hệt.

Giá trị default cũng không làm field trở thành bắt buộc. Nếu client bỏ qua field, server chỉ áp dụng giá trị mặc định khi code hoặc cơ chế binding thực sự quy định điều đó.

## 3. Array ở cấp cao nhất của request body

Request body có thể là một mảng JSON trực tiếp thay vì object bao quanh:

```json
[
  {
    "productId": 101,
    "quantity": 2
  },
  {
    "productId": 205,
    "quantity": 1
  }
]
```

Schema có dạng:

```yaml
type: array
minItems: 1
maxItems: 100
items:
  type: object
  required:
    - productId
    - quantity
  properties:
    productId:
      type: integer
      format: int64
    quantity:
      type: integer
      minimum: 1
```

type: array mô tả body là mảng; items mô tả kiểu của từng phần tử. Có thể dùng minItems, maxItems và uniqueItems để mô tả các giới hạn của mảng nếu chúng là quy tắc thực tế của API.

Một array ở cấp cao nhất phù hợp với thao tác nhận danh sách thuần túy, chẳng hạn nhập nhiều mã hoặc cập nhật hàng loạt theo một quy tắc cố định. Tuy nhiên, nếu request cần thêm metadata như nguồn dữ liệu, chế độ xử lý, khóa chống gửi trùng hoặc ghi chú, một object chứa array thường dễ mở rộng hơn.

Ví dụ object bọc danh sách:

```json
{
  "source": "web-checkout",
  "items": [
    {
      "productId": 101,
      "quantity": 2
    },
    {
      "productId": 205,
      "quantity": 1
    }
  ]
}
```

Object bọc danh sách cũng giúp bổ sung thuộc tính mới mà không thay đổi hình dạng cấp cao nhất của request. Dù chọn kiểu nào, hãy giữ hợp đồng đơn giản và phù hợp với thao tác.

## 4. Kiểu nguyên thủy ở cấp cao nhất

OpenAPI cho phép request body là một giá trị JSON nguyên thủy: string, number, integer hoặc boolean. Ví dụ, một API có thể nhận trực tiếp chuỗi tìm kiếm:

```json
"springdoc-openapi"
```

Schema:

```yaml
type: string
minLength: 2
maxLength: 100
```

Hoặc API có thể nhận trực tiếp một số nguyên:

```yaml
type: integer
minimum: 1
maximum: 10
```

Và một boolean:

```yaml
type: boolean
```

Kiểu nguyên thủy phù hợp khi body chỉ có đúng một giá trị và ngữ nghĩa rất rõ. Tuy nhiên, với API có khả năng cần thêm thuộc tính trong tương lai, object thường dễ mở rộng hơn. Ví dụ, thay vì gửi chuỗi "springdoc-openapi", client có thể gửi object {"query":"springdoc-openapi","language":"vi"} nếu thao tác cần thêm ngữ cảnh.

Trong Spring MVC, body số nguyên JSON có thể được ánh xạ vào kiểu Java tương ứng. Với văn bản thuần, khai báo rõ media type text/plain:

```java
@PostMapping(path = "/search", consumes = MediaType.TEXT_PLAIN_VALUE)
public SearchResult search(
    @RequestBody String query
) {
    return searchService.search(query);
}

@PutMapping("/settings/page-size")
public void updatePageSize(
    @RequestBody Integer pageSize
) {
    settingsService.updatePageSize(pageSize);
}
```

Kiểu Java và message converter quyết định cách nội dung được chuyển đổi. Một String body với text/plain khác với một JSON string có dấu ngoặc kép và Content-Type: application/json. Hãy khai báo đúng media type mà endpoint thực sự nhận.

Nếu hợp đồng yêu cầu một JSON string ở cấp cao nhất, không nên mặc định rằng mọi cấu hình Spring MVC sẽ ánh xạ nó giống text/plain vào tham số String. Lựa chọn kiểu Java và HttpMessageConverter cần được kiểm tra theo thứ tự converter của ứng dụng; có thể dùng JsonNode hoặc một DTO bao bọc nếu cần xử lý rõ ràng.

## 5. Thân request tùy chọn: required ở cấp requestBody

Một operation có thể cho phép client gọi mà không gửi body. Khi đó OpenAPI mô tả:

```yaml
requestBody:
  required: false
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/UpdatePreferencesRequest'
```

required: false nghĩa là toàn bộ request body có thể vắng mặt. Nó không có nghĩa mọi field bên trong object đều tùy chọn. Ngược lại, body bắt buộc vẫn có thể chứa nhiều field tùy chọn:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        type: object
        required:
          - displayName
        properties:
          displayName:
            type: string
          phone:
            type: string
```

Ở ví dụ thứ hai, client bắt buộc gửi một body JSON và phải có displayName; phone có thể bỏ qua. Đây là hai cấp bắt buộc khác nhau.

### 5.1. Ánh xạ body tùy chọn trong Spring MVC

Spring MVC cho phép khai báo required = false trên @RequestBody:

```java
@PatchMapping("/preferences")
public PreferencesResponse updatePreferences(
    @RequestBody(required = false) UpdatePreferencesRequest request
) {
    if (request == null) {
        return preferencesService.getCurrent();
    }
    return preferencesService.update(request);
}
```

Khi không có body, Spring có thể truyền null cho tham số không bắt buộc. Code cần xử lý trường hợp này an toàn. Nếu tham số vẫn là bắt buộc theo mặc định, request không có body thường dẫn đến lỗi đọc request trước khi vào logic controller.

Với springdoc, annotation @RequestBody của Spring được dùng để nhận diện request body. Tùy phiên bản springdoc và cách khai báo annotation, required có thể được suy ra từ tham số Spring. Sau khi thêm required = false, hãy mở /v3/api-docs và kiểm tra requestBody.required là false. Nếu tài liệu chưa phản ánh đúng, có thể khai báo mô tả OpenAPI tường minh.

### 5.2. Ghi đè metadata bằng annotation OpenAPI

Có thể dùng annotation OpenAPI để mô tả request body rõ hơn:

```java
import io.swagger.v3.oas.annotations.parameters.RequestBody;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.PatchMapping;

@PatchMapping("/preferences")
@Operation(
    summary = "Cập nhật tùy chọn",
    requestBody = @RequestBody(
        required = false,
        description = "Có thể bỏ qua body để đọc lại tùy chọn hiện tại.",
        content = @Content(
            schema = @Schema(implementation = UpdatePreferencesRequest.class)
        )
    )
)
public PreferencesResponse updatePreferences(
    @org.springframework.web.bind.annotation.RequestBody(required = false)
    UpdatePreferencesRequest request
) {
    if (request == null) {
        return preferencesService.getCurrent();
    }
    return preferencesService.update(request);
}
```

Ở đây có hai annotation cùng tên đơn giản RequestBody: một của Spring MVC dùng để binding request; một của OpenAPI dùng để mô tả tài liệu. Ví dụ viết đầy đủ tên annotation Spring ở tham số để tránh xung đột import. Nếu dùng annotation OpenAPI ở cấp operation, hãy kiểm tra tài liệu sinh ra để xác nhận schema và cờ required phù hợp.

## 6. Body không có, body rỗng và JSON null không phải một

Ba request dưới đây có ý nghĩa khác nhau:

| Request body | Ý nghĩa ở tầng HTTP/JSON |
|---|---|
| Không gửi byte body | Không có nội dung request body |
| Gửi {} | Có JSON object rỗng |
| Gửi null | Có nội dung JSON với giá trị null |

Với {}, server nhận một object nhưng không có thuộc tính. Với null, JSON parser đọc giá trị null, không phải object rỗng. Không gửi body thì message converter có thể không được gọi hoặc tham số không bắt buộc được nhận giá trị null, tùy kiểu tham số và cấu hình.

Nếu API chấp nhận body tùy chọn, cần nói rõ hành vi khi body vắng mặt. Nếu API nhận object rỗng để yêu cầu một hành động mặc định, hãy mô tả riêng trường hợp {}. Nếu JSON null được chấp nhận, phải bảo đảm kiểu Java, message converter và validation hỗ trợ đúng hành vi đó.

Không nên chỉ dựa vào required = false để ngụ ý rằng {} và null đều hợp lệ. Cờ này nói về việc body có thể vắng mặt; quy tắc cho nội dung body vẫn được quyết định bởi schema và ứng dụng.

## 7. Khai báo request body trong Springdoc: từ DTO đến schema

Với body là object, cách phổ biến nhất là tạo DTO riêng và đặt DTO vào tham số @RequestBody. Springdoc đọc kiểu DTO để sinh schema:

```java
public record CreateProductRequest(
    @NotBlank
    @Size(max = 120)
    String name,

    @NotNull
    @DecimalMin("0.0")
    BigDecimal price,

    Boolean active
) {
}

@RestController
@RequestMapping("/api/v1/products")
public class ProductController {

    @PostMapping
    public ResponseEntity<ProductResponse> create(
        @Valid @RequestBody CreateProductRequest request
    ) {
        ProductResponse created = productService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
```

Nếu body là array ở cấp cao nhất, kiểu tham số có thể là List của một DTO phần tử:

```java
@PostMapping("/products/batch")
public List<ProductResponse> createBatch(
    @Valid @RequestBody List<@Valid CreateProductRequest> requests
) {
    return productService.createBatch(requests);
}
```

Schema sinh ra cần có type array và items trỏ đến schema của CreateProductRequest. Nếu quy tắc yêu cầu danh sách không rỗng hoặc có giới hạn số phần tử, hãy bổ sung validation phù hợp cho collection và xác minh các ràng buộc đó xuất hiện trong tài liệu.

Các annotation Bean Validation diễn tả ràng buộc đầu vào. Để schema được sinh chính xác, dự án cần dependency hỗ trợ tích hợp validation và phiên bản phù hợp. Sau khi sinh tài liệu, kiểm tra field required, minLength, maxLength, minimum và format.

Nếu cần giải thích thêm quy tắc mà schema không diễn tả đủ, dùng @Schema:

```java
public record CreateProductRequest(
    @Schema(
        description = "Tên sản phẩm hiển thị cho khách hàng.",
        example = "Bàn phím cơ"
    )
    @NotBlank
    @Size(max = 120)
    String name,

    @Schema(
        description = "Giá bán theo đơn vị tiền tệ của cửa hàng.",
        example = "1250000",
        minimum = "0"
    )
    @NotNull
    @DecimalMin("0.0")
    BigDecimal price
) {
}
```

Không dùng DTO response làm request chỉ vì hai cấu trúc hiện tại giống nhau. Request và response có thể có quy tắc bắt buộc khác nhau, chẳng hạn client không được gửi id, createdAt hoặc trường trạng thái do server quản lý.

## 8. Mô tả ví dụ request với ExampleObject

Ví dụ giúp người tích hợp hiểu cấu trúc body nhanh hơn schema. Có thể khai báo example cho cả media type hoặc từng media type:

```java
@Operation(
    summary = "Tạo sản phẩm",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = CreateProductRequest.class),
            examples = @ExampleObject(
                name = "simple-product",
                summary = "Sản phẩm cơ bản",
                value = """
                    {
                      "name": "Bàn phím cơ",
                      "price": 1250000,
                      "active": true
                    }
                    """
            )
        )
    )
)
```

Example phải hợp lệ với schema và phản ánh dữ liệu mà server chấp nhận. Không dùng dữ liệu cá nhân thật hoặc token bí mật trong ví dụ. Nếu có nhiều biến thể request, đặt tên và mô tả riêng cho từng example, chẳng hạn sản phẩm vật lý, sản phẩm số hoặc request thiếu field tùy chọn.

## 9. Nhiều media type cho một request body

Trường content có thể mô tả nhiều loại nội dung:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateProductRequest'
    application/xml:
      schema:
        $ref: '#/components/schemas/CreateProductXml'
```

Client chọn một media type bằng header Content-Type. Server phải thực sự có khả năng đọc media type đó, ví dụ thông qua consumes, HttpMessageConverter hoặc cấu hình phù hợp. Chỉ khai báo thêm XML trong OpenAPI không làm Spring tự động hỗ trợ XML.

Một số media type thường gặp:

| Media type | Dạng dữ liệu |
|---|---|
| application/json | Object, array hoặc giá trị JSON |
| application/xml | Tài liệu XML |
| application/x-www-form-urlencoded | Các cặp key/value được mã hóa theo form URL |
| multipart/form-data | Nhiều phần, thường dùng cho upload file và field đi kèm |
| text/plain | Nội dung văn bản thuần |
| application/octet-stream | Dữ liệu nhị phân |

## 10. Form và multipart request body

Không phải mọi request body đều là JSON. Với application/x-www-form-urlencoded, các field được gửi như một form đã mã hóa. Với multipart/form-data, mỗi phần có thể có kiểu dữ liệu và header riêng; thường dùng khi upload file kèm metadata.

Ví dụ mô tả multipart:

```yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        required:
          - file
        properties:
          file:
            type: string
            format: binary
          description:
            type: string
```

Trong Spring MVC, endpoint có thể nhận file qua MultipartFile:

```java
@PostMapping(
    path = "/documents",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public DocumentResponse upload(
    @RequestPart("file") MultipartFile file,
    @RequestPart(value = "description", required = false) String description
) {
    return documentService.upload(file, description);
}
```

Với multipart, @RequestPart thường phù hợp khi từng phần cần được chuyển đổi bằng message converter. @RequestParam cũng có thể được dùng cho các field form tùy cấu trúc endpoint. Hãy kiểm tra schema sinh ra và bảo đảm tên part khớp với tên client phải gửi.

## 11. Những lưu ý khi chọn hình dạng body

| Hình dạng | Khi phù hợp | Điểm cần cân nhắc |
|---|---|---|
| Object | Request có nhiều thuộc tính hoặc cần mở rộng | Xác định rõ field bắt buộc, tùy chọn và null |
| Array | Gửi một danh sách đồng nhất, không cần metadata ngoài danh sách | Cần giới hạn số phần tử và mô tả lỗi theo từng phần tử nếu có |
| Primitive | Body chỉ chứa một giá trị đơn giản | Khó mở rộng khi cần thêm thông tin |
| Body tùy chọn | Thao tác cho phép client không gửi nội dung | Phải định nghĩa rõ hành vi khi body vắng mặt |
| Multipart | Upload file hoặc kết hợp file với metadata | Mô tả từng part, media type và giới hạn file |

Không có một hình dạng tốt cho mọi API. Hãy chọn hình dạng thể hiện đúng ý nghĩa nghiệp vụ và có thể được xử lý nhất quán ở server.

## 12. Các lỗi thường gặp khi mô tả request body

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Đặt requestBody.required: false vì một field tùy chọn | Client nghĩ toàn bộ body có thể bỏ qua | Giữ body required và bỏ field đó khỏi danh sách schema required |
| Dùng required của body để mô tả field | Không thể hiện được các field bắt buộc bên trong object | Khai báo required ở cả hai cấp đúng mục đích |
| Dùng nullable để diễn tả field tùy chọn | Client hiểu nhầm field phải gửi null | Bỏ field khỏi danh sách required; chỉ dùng nullable nếu null được chấp nhận |
| Dùng array ở cấp cao nhất dù cần metadata | Khó bổ sung chế độ xử lý hoặc thông tin nguồn | Cân nhắc object chứa array |
| Khai báo XML hoặc multipart nhưng server không nhận | Swagger UI gửi request bị từ chối | Đồng bộ content, consumes và message converter |
| Ví dụ không khớp schema | Client sao chép request lỗi | Kiểm tra example theo schema và validation |
| Cho rằng default tự áp dụng ở backend | Giá trị thực tế có thể là null | Triển khai default trong DTO, controller hoặc service |
| Cho rằng body vắng mặt, {} và null giống nhau | Hành vi API không rõ ràng | Định nghĩa và kiểm thử riêng từng trường hợp |
| Dùng DTO response làm request | Client có thể gửi field server quản lý | Tạo DTO request riêng với field được phép ghi |

## 13. Kiểm tra request body trong tài liệu được sinh ra

Sau khi khởi động ứng dụng Spring Boot, mở endpoint OpenAPI mặc định:

```bash
curl -s http://localhost:8080/v3/api-docs
```

Tìm operation tương ứng trong paths, sau đó kiểm tra:

1. requestBody có xuất hiện đúng operation không?
2. required ở cấp body có phản ánh đúng việc body có thể vắng mặt không?
3. content có đúng media type mà controller nhận không?
4. Schema cấp cao nhất có đúng là object, array, string, number, boolean hay loại nội dung khác không?
5. Các field bên trong object có danh sách required, kiểu, giới hạn và nullability đúng không?
6. Ví dụ có khớp schema và quy tắc validation không?

Có thể dùng Swagger UI để nhập body và gửi request thử nghiệm. Với body tùy chọn, kiểm tra cả trường hợp bỏ hẳn body. Với JSON object, kiểm tra object đầy đủ, object thiếu field bắt buộc, object có field tùy chọn bị bỏ qua và giá trị null nếu hợp đồng cho phép.

## 14. Ghi nhớ

- requestBody mô tả dữ liệu client gửi; content ánh xạ media type đến schema và ví dụ.
- Body cấp cao nhất có thể là object, array, string, number, integer, boolean hoặc nội dung nhị phân/form.
- requestBody.required nói về toàn bộ body; schema.required nói về các field bắt buộc bên trong object.
- Field tùy chọn, field nullable và field có giá trị mặc định là ba khái niệm khác nhau.
- Body vắng mặt, object rỗng {} và JSON null có ngữ nghĩa khác nhau.
- Trong Spring MVC, @RequestBody(required = false) cho phép tham số body vắng mặt; code phải xử lý trường hợp null.
- Springdoc có thể suy ra schema từ DTO và annotation, nhưng cần kiểm tra tài liệu sinh ra để bảo đảm đúng hợp đồng.
- Mỗi media type được công bố phải được server hỗ trợ thực tế.

Khi mô tả request body với springdoc-openapi, hãy bắt đầu từ dữ liệu client cần gửi và ý nghĩa của từng trường. Chọn hình dạng cấp cao nhất phù hợp, xác định rõ body có bắt buộc hay không, rồi đối chiếu schema, ví dụ và cách Spring MVC binding dữ liệu. Nhờ vậy, Swagger UI và các công cụ sinh client có thể tạo request đúng với hợp đồng API.
