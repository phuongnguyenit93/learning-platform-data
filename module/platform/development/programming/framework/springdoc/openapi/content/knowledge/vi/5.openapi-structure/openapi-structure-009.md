# Tham chiếu `$ref` và cách phân giải tham chiếu

Trong OpenAPI, `$ref` cho phép một phần của đặc tả dùng lại schema, parameter, response hoặc thành phần đã được định nghĩa ở nơi khác. Tham chiếu giúp tài liệu gọn hơn, tránh khai báo lặp và giữ các mô hình dữ liệu nhất quán. Springdoc cũng thường tạo các schema dùng chung trong `components` rồi liên kết tới chúng bằng `$ref` khi mô tả các kiểu Java phức tạp.

Để đọc hoặc tổ chức một đặc tả có nhiều `$ref`, cần hiểu ba phần: URI xác định tài liệu đích, JSON Pointer xác định vị trí bên trong tài liệu, và công cụ phân giải tải/đọc đích rồi kiểm tra kiểu đối tượng. Một tham chiếu hợp lệ về cú pháp vẫn có thể không phân giải được nếu file không tồn tại, fragment sai hoặc công cụ không truy cập được tài nguyên bên ngoài.

## 1. `$ref` dùng để làm gì?

`$ref` là một giá trị URI trỏ tới một đối tượng khác. Đối tượng đích có thể nằm trong chính file OpenAPI hiện tại, trong một file JSON/YAML khác hoặc tại một URI bên ngoài.

Các lợi ích thường gặp:

- **Tái sử dụng**: nhiều operation cùng tham chiếu một schema `Address` hoặc response `NotFound`.
- **Nhất quán**: sửa định nghĩa dùng chung một lần sẽ cập nhật cách mô tả ở mọi nơi tham chiếu.
- **Tổ chức tài liệu**: tách schema, path, response và parameter thành các file riêng khi đặc tả lớn.
- **Giảm trùng lặp**: không phải sao chép một cấu trúc request/response vào nhiều endpoint.
- **Hỗ trợ mô hình đệ quy**: schema có thể tham chiếu lại chính nó, ví dụ cây danh mục có danh sách danh mục con.

Ví dụ ngắn nhất là một response dùng schema đã định nghĩa trong `components`:

```yaml
openapi: 3.1.0
info:
  title: Shop API
  version: 1.0.0
paths:
  /products/{id}:
    get:
      responses:
        '200':
          description: Tìm thấy sản phẩm
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
components:
  schemas:
    Product:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
```

Trong ví dụ này, `Product` chỉ được định nghĩa một lần ở `components.schemas`. Response `200` trỏ đến định nghĩa đó bằng `#/components/schemas/Product`.

## 2. Cấu trúc một tham chiếu

Một tham chiếu thông thường có hai phần:

```text
<URI của tài liệu>#<fragment xác định vị trí>
```

- Phần trước dấu `#` xác định tài liệu. Phần này có thể rỗng khi tham chiếu ngay trong tài liệu hiện tại.
- Phần sau dấu `#` xác định vị trí bên trong tài liệu, thường dùng JSON Pointer.

| Dạng | Ví dụ | Ý nghĩa |
|---|---|---|
| Tham chiếu trong cùng tài liệu | `#/components/schemas/Product` | Tìm schema `Product` trong `components` của file hiện tại. |
| Tham chiếu file tương đối | `./schemas/product.yaml` | Lấy đối tượng gốc từ file `product.yaml` cùng thư mục con `schemas`. |
| File tương đối kèm fragment | `./common.yaml#/components/schemas/Address` | Mở `common.yaml`, sau đó tìm schema `Address`. |
| Tham chiếu file ở thư mục cha | `../shared/errors.yaml#/components/responses/NotFound` | Đi lên một thư mục rồi tìm response `NotFound`. |
| Tham chiếu bằng URI tuyệt đối | `https://api.example.com/openapi/common.yaml#/components/schemas/Address` | Lấy schema từ tài liệu ở URI đã nêu. |

Giá trị `$ref` phải là URI hợp lệ. Với tham chiếu tương đối, công cụ phân giải dựa trên URI cơ sở của tài liệu chứa tham chiếu. Do đó, khi di chuyển một file OpenAPI sang thư mục khác, các đường dẫn tương đối có thể cần được cập nhật.

Trong YAML, nên đặt URI có fragment trong dấu nháy đơn hoặc nháy kép:

```yaml
$ref: '#/components/schemas/Product'
```

Điều này giúp tránh việc dấu `#` bị YAML hiểu là ký hiệu bắt đầu comment khi xuất hiện ở vị trí có thể gây nhập nhằng.

## 3. JSON Pointer: xác định đúng vị trí trong tài liệu

JSON Pointer là cú pháp xác định một giá trị cụ thể trong cây JSON. Trong OpenAPI, fragment phổ biến như `#/components/schemas/Product` được hiểu là đi từ gốc tài liệu, qua thuộc tính `components`, tiếp đến `schemas`, rồi lấy phần tử có tên `Product`.

Các token trong JSON Pointer được phân cách bằng dấu `/`:

```text
#/components/schemas/Product
  └ components
      └ schemas
          └ Product
```

Nếu tên key chứa ký tự đặc biệt, JSON Pointer yêu cầu escape:

| Ký tự trong tên key | Cách viết trong JSON Pointer |
|---|---|
| `~` | `~0` |
| `/` | `~1` |

Ví dụ, nếu component được đặt tên `Order/Item`, tham chiếu phải viết:

```yaml
$ref: '#/components/schemas/Order~1Item'
```

Nếu tên component là `Legacy~Product`, dùng:

```yaml
$ref: '#/components/schemas/Legacy~0Product'
```

Khi một key chứa cả hai ký tự, hãy escape từng ký tự theo quy tắc JSON Pointer. Không tự thay dấu `/` bằng dấu gạch ngang hoặc bỏ qua dấu `~`; làm vậy sẽ trỏ tới một key khác và khiến tham chiếu không phân giải được.

JSON Pointer cũng có thể trỏ vào phần tử mảng bằng chỉ số, ví dụ `#/paths/~1products/get/parameters/0`. Tuy nhiên, tham chiếu tới thành phần có tên trong `components` thường dễ bảo trì hơn vì không phụ thuộc vào vị trí phần tử trong mảng.

## 4. Các loại thành phần thường được tham chiếu

OpenAPI có vùng `components` để lưu các định nghĩa có thể dùng lại. Các nhóm phổ biến gồm:

| Vị trí | Nội dung | Ví dụ nơi sử dụng |
|---|---|---|
| `components/schemas` | Cấu trúc dữ liệu request/response | `schema` trong `content` |
| `components/parameters` | Tham số path, query, header hoặc cookie | Mảng `parameters` của Path Item/Operation |
| `components/responses` | Mô tả phản hồi HTTP dùng chung | Giá trị trong `responses` |
| `components/requestBodies` | Request body dùng chung | `requestBody` của operation |
| `components/headers` | Header response dùng chung | `headers` trong Response Object |
| `components/examples` | Ví dụ request/response dùng chung | `examples` trong Media Type Object |
| `components/securitySchemes` | Cách xác thực như Bearer, API key hoặc OAuth2 | `security` ở cấp tài liệu hoặc operation |
| `components/links` | Liên kết tới operation tiếp theo | `links` trong Response Object |
| `components/callbacks` | Mô tả callback dùng chung | `callbacks` của operation |

Ví dụ tái sử dụng parameter và response:

```yaml
paths:
  /orders:
    get:
      parameters:
        - $ref: '#/components/parameters/PageSize'
      responses:
        '404':
          $ref: '#/components/responses/NotFound'

components:
  parameters:
    PageSize:
      name: size
      in: query
      description: Số phần tử tối đa trong một trang
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20
  responses:
    NotFound:
      description: Không tìm thấy tài nguyên
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
  schemas:
    ApiError:
      type: object
      properties:
        code:
          type: string
        message:
          type: string
```

Một định nghĩa nằm trong `components` không tự tạo endpoint và cũng không tự xuất hiện trong API contract của người dùng. Nó chỉ có ý nghĩa khi được tham chiếu từ một vị trí được OpenAPI sử dụng.

## 5. Phân biệt Reference Object và Schema Object có `$ref`

Đây là điểm dễ gây nhầm lẫn. `$ref` có thể xuất hiện trong một Reference Object, chẳng hạn khi một response dùng lại response khác, hoặc xuất hiện như keyword của Schema Object để tái sử dụng một schema. Quy tắc xử lý các thuộc tính đứng cạnh `$ref` khác nhau theo phiên bản OpenAPI.

### 5.1. Reference Object trong OpenAPI 3.0

Trong OpenAPI 3.0, Reference Object chỉ có trường `$ref`. Các trường khác đặt cạnh nó bị bỏ qua theo đặc tả. Ví dụ sau không thể dùng `description` để ghi đè mô tả của response được tham chiếu:

```yaml
responses:
  '404':
    $ref: '#/components/responses/NotFound'
    description: Không tìm thấy đơn hàng
```

Với OpenAPI 3.0, hãy đặt mô tả cần dùng ngay trong component đích hoặc tạo một response riêng nếu ngữ nghĩa khác nhau.

### 5.2. Reference Object trong OpenAPI 3.1

Trong OpenAPI 3.1, Reference Object cho phép thêm `summary` và `description`; các trường này có thể ghi đè giá trị tương ứng của đối tượng được tham chiếu. Những trường tùy ý khác vẫn không được xem là phần mở rộng hợp lệ của Reference Object.

```yaml
responses:
  '404':
    $ref: '#/components/responses/NotFound'
    description: Không tìm thấy đơn hàng có mã đã cung cấp
```

Ví dụ này dùng quy tắc Reference Object của OpenAPI 3.1. Nếu tài liệu cần tương thích với OpenAPI 3.0, hãy dùng cách đặt mô tả trong component hoặc định nghĩa response riêng.

### 5.3. `$ref` bên trong Schema Object

Schema Object trong OpenAPI 3.1 dựa trên JSON Schema. Vì vậy, các keyword khác có thể được áp dụng cùng `$ref` theo quy tắc JSON Schema. Ví dụ:

```yaml
components:
  schemas:
    DetailedAddress:
      $ref: '#/components/schemas/Address'
      description: Địa chỉ nhận hàng của đơn đặt hàng
```

OpenAPI 3.0 dùng một tập con JSON Schema cũ hơn và có cách xử lý `$ref` khác. Để bổ sung metadata hoặc ràng buộc quanh schema được tham chiếu mà vẫn tương thích với 3.0, dùng `allOf`:

```yaml
components:
  schemas:
    DetailedAddress:
      description: Địa chỉ nhận hàng của đơn đặt hàng
      allOf:
        - $ref: '#/components/schemas/Address'
```

`allOf` kết hợp các schema con thành một schema phải thỏa tất cả các thành phần. Không dùng `allOf` chỉ để che một tham chiếu sai; schema đích vẫn phải tồn tại và hợp lệ.

Trước khi dựa vào các keyword đứng cạnh `$ref`, hãy kiểm tra trường `openapi` trong tài liệu được xuất ra. Springdoc có thuộc tính `springdoc.api-docs.version` để chọn phiên bản OpenAPI 3.0 hoặc 3.1; giá trị cấu hình và hỗ trợ cụ thể cần theo đúng nhánh springdoc của ứng dụng.

## 6. Springdoc tạo và sử dụng `$ref` như thế nào?

Khi controller nhận hoặc trả về các kiểu Java phức tạp, springdoc thường tạo schema trong `components.schemas` và dùng local `$ref` để liên kết các schema. Điều này giúp những DTO có cùng kiểu lồng nhau dùng chung một định nghĩa.

Ví dụ DTO:

```java
public record OrderResponse(
        String id,
        AddressResponse shippingAddress,
        AddressResponse billingAddress
) {}

public record AddressResponse(
        String street,
        String city,
        String postalCode
) {}
```

Đặc tả sinh ra có thể có cấu trúc tương tự:

```yaml
components:
  schemas:
    OrderResponse:
      type: object
      properties:
        id:
          type: string
        shippingAddress:
          $ref: '#/components/schemas/AddressResponse'
        billingAddress:
          $ref: '#/components/schemas/AddressResponse'
    AddressResponse:
      type: object
      properties:
        street:
          type: string
        city:
          type: string
        postalCode:
          type: string
```

Đây là hình minh họa cho cấu trúc đầu ra; tên schema và các thuộc tính chi tiết phụ thuộc vào kiểu Java, annotation, cấu hình Jackson, model converter và phiên bản springdoc. Có thể dùng `@Schema` để bổ sung tên, mô tả, ví dụ hoặc metadata cho model. Nếu cần định nghĩa component thủ công, có thể thêm schema vào `OpenAPI.components` qua bean cấu hình hoặc customizer.

Springdoc có `SpringDocAnnotationsUtils.extractSchema` để tạo schema từ kiểu Java theo cùng cơ chế xử lý annotation và converter mà springdoc dùng cho controller. Hàm này cũng đăng ký các schema lồng nhau vào `Components` và trả về schema tham chiếu tương ứng. Cách này hữu ích khi tự thêm operation không được khai báo bằng controller, ví dụ endpoint được phục vụ bởi filter.

Springdoc chủ yếu sinh local references trong tài liệu OpenAPI của ứng dụng. Nếu tự tách tài liệu thành nhiều file hoặc đưa `$ref` trỏ tới tài nguyên từ xa, cần dùng công cụ phân tích/phân giải OpenAPI hỗ trợ các tham chiếu bên ngoài. Không nên mặc định rằng Swagger UI hoặc mọi consumer đều tải được mọi URI bên ngoài.

## 7. Tham chiếu tới file bên ngoài

Khi đặc tả lớn, có thể tách schema hoặc path thành file riêng. Ví dụ cấu trúc thư mục:

```text
openapi/
├── openapi.yaml
├── paths/
│   └── orders.yaml
└── schemas/
    ├── order.yaml
    └── address.yaml
```

File gốc có thể tham chiếu tới path item:

```yaml
paths:
  /orders:
    $ref: './paths/orders.yaml'
```

Trong `paths/orders.yaml`, schema có thể được tham chiếu từ file schema riêng:

```yaml
get:
  responses:
    '200':
      description: Danh sách đơn hàng
      content:
        application/json:
          schema:
            type: array
            items:
              $ref: '../schemas/order.yaml'
```

Nếu `order.yaml` là một schema hoàn chỉnh, URI file có thể trỏ thẳng đến đối tượng gốc của file. Nếu file chứa nhiều component, thêm fragment JSON Pointer:

```yaml
$ref: '../common.yaml#/components/schemas/Address'
```

Một số quy tắc khi chia file:

- Tính đường dẫn tương đối từ file đang chứa `$ref`, không luôn luôn từ file gốc.
- Giữ cấu trúc thư mục và tên file ổn định để CI, IDE và công cụ tài liệu cùng phân giải được.
- Dùng URI/JSON Pointer đúng cú pháp và kiểm tra phân biệt chữ hoa, chữ thường trên môi trường build.
- Tránh tham chiếu HTTP tới tài nguyên thay đổi nội dung hoặc không sẵn sàng trong môi trường build.
- Với tài liệu cần phân phối độc lập, cân nhắc đóng gói các tham chiếu bên ngoài thành một tài liệu tự chứa.

## 8. Phân giải tham chiếu và đóng gói tài liệu

Một công cụ phân giải `$ref` thường thực hiện các công việc sau:

1. Đọc tài liệu OpenAPI gốc.
2. Tìm từng trường `$ref` trong những vị trí OpenAPI cho phép.
3. Phân tích URI để xác định tài liệu và fragment.
4. Tải hoặc đọc tài liệu đích, rồi áp dụng JSON Pointer để lấy đối tượng cần tham chiếu.
5. Kiểm tra đối tượng đích có đúng loại trong ngữ cảnh sử dụng hay không, ví dụ Schema Object được dùng ở vị trí schema.
6. Tiếp tục xử lý các tham chiếu lồng nhau và báo lỗi nếu không thể phân giải.

Phân biệt ba thao tác thường gặp:

| Thao tác | Kết quả |
|---|---|
| **Resolve** | Tìm và nạp các đối tượng được tham chiếu để công cụ có thể hiểu tài liệu. Tùy công cụ, tham chiếu bên ngoài có thể được chuyển thành tham chiếu nội bộ. |
| **Bundle** | Gộp nhiều file thành một tài liệu phân phối, thường chuyển các tham chiếu bên ngoài thành local references trong cùng tài liệu. |
| **Dereference** | Thay tham chiếu bằng nội dung đối tượng đích tại vị trí sử dụng. Kết quả có thể lặp lại cùng schema nhiều lần và khó xử lý khi có tham chiếu đệ quy. |

Tên gọi và kết quả cụ thể có thể khác giữa các công cụ. Khi chọn công cụ, hãy kiểm tra rõ nó giữ `$ref`, chuyển `$ref` bên ngoài thành local reference hay thay toàn bộ bằng nội dung inline.

### 8.1. Ví dụ phân giải bằng Swagger Parser

Swagger Parser có thể đọc OpenAPI JSON/YAML và bật chế độ resolve để xử lý tham chiếu tương đối hoặc từ xa. Ví dụ Java:

```java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.parser.OpenAPIV3Parser;
import io.swagger.v3.parser.core.models.ParseOptions;
import io.swagger.v3.parser.core.models.SwaggerParseResult;

ParseOptions options = new ParseOptions();
options.setResolve(true);

SwaggerParseResult result = new OpenAPIV3Parser().readLocation(
        "openapi/openapi.yaml",
        null,
        options
);

if (result.getMessages() != null && !result.getMessages().isEmpty()) {
    result.getMessages().forEach(System.err::println);
}

OpenAPI openAPI = result.getOpenAPI();
if (openAPI == null) {
    throw new IllegalStateException("Không thể đọc hoặc phân giải OpenAPI");
}
```

Với `resolve=true`, parser cố gắng đọc các tham chiếu tương đối hoặc từ xa, thêm đối tượng đã phân giải vào `components` và thay tham chiếu bên ngoài bằng local reference. Cần đọc các message parser trả về; không nên coi việc nhận được một đối tượng `OpenAPI` là bằng chứng rằng mọi cảnh báo đều không quan trọng.

Phân giải tham chiếu và kiểm tra hợp lệ là hai việc liên quan nhưng khác nhau. Sau khi resolve, vẫn cần chạy validator tương thích với phiên bản OpenAPI mục tiêu và kiểm tra các quy tắc nghiệp vụ của API.

### 8.2. Khi nào nên bundle?

Bundle hữu ích khi cần gửi một file OpenAPI cho đối tác, tải lên API portal hoặc làm đầu vào cho code generator không hỗ trợ nhiều file. Tài liệu sau bundle vẫn có thể giữ local `$ref` để tái sử dụng schema trong một file.

Không nhất thiết phải dereference toàn bộ. Giữ local references thường làm tài liệu dễ đọc hơn, tránh sao chép cùng một schema vào nhiều nơi và bảo toàn cấu trúc tái sử dụng.

## 9. Tham chiếu đệ quy và vòng lặp

Một schema có thể tham chiếu lại chính nó hoặc tham chiếu qua nhiều schema khác. Đây là mô hình hợp lệ khi dữ liệu thực tế có cấu trúc đệ quy.

Ví dụ một danh mục có danh sách danh mục con:

```yaml
components:
  schemas:
    Category:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
        children:
          type: array
          items:
            $ref: '#/components/schemas/Category'
```

`Category` tham chiếu lại `Category` thông qua `children.items`. Điều này mô tả một cây có độ sâu tùy ý. Công cụ cần hiểu rằng đây là tham chiếu đệ quy, không phải lý do để lặp vô hạn khi mở rộng schema.

Một chuỗi tham chiếu cũng có thể tạo vòng gián tiếp: `A` tham chiếu `B`, `B` tham chiếu `C`, và `C` tham chiếu lại `A`. Hãy kiểm tra xem mô hình dữ liệu có thực sự cho phép quan hệ đó hay chỉ do định nghĩa nhầm.

Các lỗi thường xuất hiện khi một công cụ cố dereference đệ quy thành cấu trúc inline không giới hạn. Trong trường hợp này, giữ `$ref` và dùng validator/generator hỗ trợ recursive schemas. Không xóa tham chiếu chỉ để làm cho công cụ cũ hết báo lỗi nếu việc đó làm sai mô hình dữ liệu.

## 10. Các lỗi phân giải `$ref` thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `Could not resolve reference` | File đích không tồn tại, URI sai hoặc tài nguyên không truy cập được | Kiểm tra đường dẫn tương đối, URI cơ sở và quyền truy cập. |
| Fragment không tìm thấy | JSON Pointer sai key, sai cấp hoặc escape `~`/`/` không đúng | So sánh với cấu trúc JSON/YAML thực tế và sửa pointer. |
| Schema không được nhận diện ở vị trí tham chiếu | `$ref` trỏ tới Response Object hoặc Parameter Object thay vì Schema Object | Trỏ tới đúng loại component theo ngữ cảnh. |
| Chạy local được nhưng CI lỗi | File tham chiếu không được commit, khác chữ hoa/thường hoặc CI chạy từ thư mục khác | Kiểm tra file trong repository và đường dẫn từ tài liệu chứa `$ref`. |
| Swagger UI không tải được tài liệu | UI hoặc browser không truy cập được URI bên ngoài, CORS hoặc tài liệu gốc sai đường dẫn | Kiểm tra request mạng, quyền truy cập và thử resolve bằng parser trong build. |
| Bundle tạo tên component có hậu tố | Nhiều file có component cùng tên | Đổi tên component để duy nhất hoặc review mapping do công cụ tạo. |
| Dereference bị lặp vô hạn hoặc tạo file quá lớn | Schema có tham chiếu đệ quy hoặc schema dùng chung ở nhiều nơi | Giữ local `$ref`, dùng công cụ hỗ trợ vòng lặp và tránh inline toàn bộ. |

Một số nguyên tắc giúp tránh lỗi:

- Tên component nên đơn giản, ổn định và duy nhất trong phạm vi tương ứng.
- Không dùng đường dẫn máy cá nhân trong `$ref`; dùng đường dẫn tương đối nằm trong repository hoặc URI có thể truy cập trong mọi môi trường.
- Không tham chiếu tới một component chỉ vì tên trùng; kiểm tra đúng file, đúng fragment và đúng loại đối tượng.
- Khi một file được đổi tên hoặc di chuyển, tìm tất cả `$ref` phụ thuộc và chạy lại resolver.
- Đưa bước kiểm tra OpenAPI vào CI để lỗi tham chiếu được phát hiện trước khi phát hành.

## 11. Quy trình làm việc với `$ref` trong dự án Spring Boot

Khi dùng springdoc để sinh tài liệu và cần tái sử dụng hoặc chia file, có thể áp dụng quy trình sau:

1. **Sinh tài liệu gốc**: chạy ứng dụng và lấy `/v3/api-docs` hoặc `/v3/api-docs.yaml` theo cấu hình.
2. **Kiểm tra phiên bản OpenAPI**: đọc trường `openapi` ở đầu tài liệu; bảo đảm consumer hỗ trợ phiên bản này.
3. **Kiểm tra components**: tìm `components.schemas`, `responses`, `parameters` và các vùng dùng chung mà springdoc đã tạo.
4. **Đối chiếu local references**: xác nhận mỗi `#/components/...` trỏ tới component có thật và đúng loại.
5. **Tách file khi có nhu cầu**: di chuyển các định nghĩa sang file riêng, cập nhật relative URI và fragment theo vị trí file mới.
6. **Resolve và validate**: dùng parser/validator để đọc toàn bộ tài liệu, phát hiện tham chiếu hỏng, sai cấu trúc hoặc không tương thích.
7. **Bundle nếu cần phân phối một file**: kiểm tra local references sau bundle và bảo đảm file đầu ra không phụ thuộc đường dẫn máy phát triển.
8. **Kiểm thử consumer**: thử Swagger UI, SDK generator, API portal hoặc công cụ tích hợp thực tế với file sẽ phát hành.

Trong pipeline CI, nên lưu bản OpenAPI đã resolve hoặc bundle làm artifact có phiên bản, đồng thời so sánh thay đổi hợp đồng với bản phát hành trước. Nếu tài liệu chứa URI từ xa, cần bảo đảm tài nguyên đó được quản lý và có thể truy cập ổn định trong CI.

## 12. Checklist review tham chiếu

- [ ] Mỗi `$ref` là URI hợp lệ.
- [ ] Relative URI được tính từ đúng tài liệu đang chứa tham chiếu.
- [ ] Fragment JSON Pointer trỏ đúng vị trí trong JSON/YAML.
- [ ] Key chứa `~` hoặc `/` đã được escape thành `~0` hoặc `~1`.
- [ ] Component đích tồn tại và đúng loại đối tượng theo ngữ cảnh.
- [ ] Tài liệu dùng đúng quy tắc `$ref` của OpenAPI 3.0 hoặc 3.1.
- [ ] Các component trong `components` được tham chiếu từ nơi sử dụng.
- [ ] Tham chiếu đệ quy là chủ ý và công cụ kiểm tra hỗ trợ chúng.
- [ ] Tất cả file bên ngoài được đưa vào repository hoặc URI có thể truy cập ổn định.
- [ ] Resolver và validator chạy thành công trong CI.
- [ ] File bundle phát hành không còn phụ thuộc đường dẫn máy cá nhân.

## 13. Tài liệu tham khảo

- [OpenAPI Specification 3.1.2 – Reference Object](https://spec.openapis.org/oas/v3.1.2.html#reference-object)
- [OpenAPI Specification 3.0.4 – Reference Object](https://spec.openapis.org/oas/v3.0.4.html#reference-object)
- [RFC 6901 – JSON Pointer](https://www.rfc-editor.org/rfc/rfc6901)
- [OpenAPI Initiative – Referencing overview](https://learn.openapis.org/referencing/overview.html)
- [Swagger Parser – Resolve external and relative references](https://github.com/swagger-api/swagger-parser)
- [springdoc-openapi FAQ – Reusable component schemas](https://springdoc.org/faq.html)
- [springdoc-openapi configuration properties](https://springdoc.org/properties.html)

`$ref` là cơ chế kết nối các phần của hợp đồng OpenAPI. Khi xác định đúng URI, dùng JSON Pointer chính xác và phân biệt quy tắc của OpenAPI 3.0 với 3.1, bạn có thể tái sử dụng schema an toàn, chia tài liệu thành nhiều file và đóng gói đặc tả đáng tin cậy cho các công cụ downstream.
