# DTO lồng nhau và các tham chiếu schema dùng chung

Một request hoặc response API thường chứa nhiều lớp dữ liệu. Đơn hàng có địa chỉ giao hàng và danh sách mặt hàng; hồ sơ khách hàng có địa chỉ liên hệ; mỗi mặt hàng lại tham chiếu thông tin sản phẩm. Nếu mô tả tất cả field trong một object lớn hoặc lặp lại cùng một cấu trúc ở nhiều endpoint, tài liệu OpenAPI sẽ khó bảo trì và dễ lệch nhau.

Với springdoc-openapi, DTO Java giúp mô tả cấu trúc dữ liệu theo cách gần với code ứng dụng. Thư viện phân tích các kiểu thuộc tính, collection và quan hệ giữa các DTO để tạo Schema Object trong OpenAPI. Những kiểu được dùng lại có thể được đặt trong components.schemas và được liên kết bằng $ref. Bài này hướng dẫn thiết kế DTO lồng nhau, tái sử dụng schema và kiểm tra tài liệu sinh ra.

## 1. Từ DTO Java đến Schema Object

DTO (Data Transfer Object) là kiểu dữ liệu dùng để trao đổi thông tin qua API. DTO có thể xuất hiện ở request body hoặc response body. Mỗi thuộc tính của DTO trở thành một property trong schema tương ứng.

Ví dụ một response đơn giản:

~~~java
public class ProductResponse {
    private String id;
    private String name;
    private BigDecimal price;

    // Constructor, getters và setters.
}
~~~

Với controller trả về ProductResponse:

~~~java
@GetMapping("/api/products/{id}")
public ProductResponse getProduct(@PathVariable String id) {
    return productService.findById(id);
}
~~~

springdoc phân tích kiểu trả về và có thể sinh schema trong components.schemas, sau đó tham chiếu schema đó từ response content của operation.

Mô hình OpenAPI rút gọn:

~~~yaml
paths:
  /api/products/{id}:
    get:
      responses:
        '200':
          description: Thông tin sản phẩm
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductResponse'

components:
  schemas:
    ProductResponse:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
        price:
          type: number
~~~

Tên schema thực tế được sinh ra phụ thuộc kiểu Java, generic type và metadata annotation. Có thể dùng @Schema(name = "...") để đặt tên rõ ràng, ổn định hơn cho component khi cần.

## 2. Biểu diễn object lồng nhau

Một property có kiểu DTO khác sẽ trở thành object lồng nhau trong schema. Ví dụ đơn hàng chứa địa chỉ giao hàng:

~~~java
public class ShippingAddress {
    private String recipient;
    private String street;
    private String city;
    private String postalCode;

    // Constructor, getters và setters.
}

public class OrderResponse {
    private String id;
    private String status;
    private ShippingAddress shippingAddress;

    // Constructor, getters và setters.
}
~~~

Định nghĩa OpenAPI tương ứng có thể được biểu diễn bằng một schema tham chiếu:

~~~yaml
components:
  schemas:
    OrderResponse:
      type: object
      properties:
        id:
          type: string
        status:
          type: string
        shippingAddress:
          $ref: '#/components/schemas/ShippingAddress'

    ShippingAddress:
      type: object
      properties:
        recipient:
          type: string
        street:
          type: string
        city:
          type: string
        postalCode:
          type: string
~~~

Ở đây, shippingAddress vẫn là property của OrderResponse, nhưng định nghĩa cấu trúc của nó được đặt ở schema ShippingAddress. Client đọc $ref để lấy cấu trúc được tham chiếu.

Việc tách DTO con giúp:

- Dễ dùng lại cùng một cấu trúc ở nhiều request hoặc response.
- Tập trung mô tả field và constraint tại một nơi.
- Tránh lặp schema dài trong nhiều operation.
- Giúp tài liệu dễ đọc khi object có nhiều cấp.
- Hỗ trợ sinh client và validator dựa trên cấu trúc nhất quán.

Không phải cứ tách một class là bắt buộc phải có component dùng chung. Với object nhỏ, chỉ dùng ở một vị trí, schema inline cũng có thể đủ rõ. Mục tiêu là giữ cấu trúc dễ hiểu và dễ bảo trì.

## 3. Collection chứa DTO

DTO thường chứa danh sách các object con. Ví dụ một đơn hàng có nhiều dòng hàng:

~~~java
public class OrderItemResponse {
    private String productId;
    private String productName;
    private Integer quantity;
    private BigDecimal unitPrice;

    // Constructor, getters và setters.
}

public class OrderResponse {
    private String id;
    private List<OrderItemResponse> items;

    // Constructor, getters và setters.
}
~~~

Trong OpenAPI, property items được mô tả bằng type array và items schema:

~~~yaml
OrderResponse:
  type: object
  properties:
    id:
      type: string
    items:
      type: array
      items:
        $ref: '#/components/schemas/OrderItemResponse'
~~~

Mỗi phần tử của mảng tuân theo schema OrderItemResponse. Có thể thêm constraint cho collection bằng Bean Validation và metadata OpenAPI:

~~~java
public class CreateOrderRequest {

    @NotEmpty
    @Size(max = 50)
    @Valid
    private List<OrderItemRequest> items;

    // Getters và setters.
}
~~~

~~~java
@Schema(name = "OrderItemRequest")
public class OrderItemRequest {

    @NotBlank
    @Schema(description = "Mã sản phẩm", example = "SKU-1001")
    private String productId;

    @Min(1)
    @Schema(description = "Số lượng đặt", example = "2", minimum = "1")
    private Integer quantity;

    // Getters và setters.
}
~~~

Trong ví dụ, @NotEmpty yêu cầu danh sách có ít nhất một phần tử khi validation chạy; @Size(max = 50) giới hạn số phần tử. @Valid yêu cầu kiểm tra các object con. Schema có thể phản ánh minItems và maxItems nếu phiên bản tích hợp ánh xạ constraint tương ứng. Hãy kiểm tra JSON thực tế thay vì giả định mọi constraint đều được chuyển đổi.

## 4. Nhiều cấp DTO lồng nhau

Có thể lồng nhiều cấp nếu cấu trúc nghiệp vụ cần thiết. Ví dụ:

~~~java
public class CreateOrderRequest {
    private CustomerSummary customer;
    private ShippingAddress shippingAddress;
    private List<OrderItemRequest> items;

    // Getters và setters.
}

public class CustomerSummary {
    private String customerId;
    private String displayName;

    // Getters và setters.
}

public class ShippingAddress {
    private String recipient;
    private String street;
    private String city;
    private String postalCode;

    // Getters và setters.
}

public class OrderItemRequest {
    private String productId;
    private Integer quantity;

    // Getters và setters.
}
~~~

Sơ đồ quan hệ:

~~~mermaid
classDiagram
    class CreateOrderRequest {
      CustomerSummary customer
      ShippingAddress shippingAddress
      List~OrderItemRequest~ items
    }
    class CustomerSummary {
      String customerId
      String displayName
    }
    class ShippingAddress {
      String recipient
      String street
      String city
      String postalCode
    }
    class OrderItemRequest {
      String productId
      Integer quantity
    }
    CreateOrderRequest --> CustomerSummary
    CreateOrderRequest --> ShippingAddress
    CreateOrderRequest --> OrderItemRequest
~~~

Trong OpenAPI, mỗi kiểu có thể trở thành một schema component riêng và được tham chiếu từ CreateOrderRequest. Khi đọc tài liệu, bắt đầu từ requestBody của operation, theo $ref tới schema gốc, sau đó tiếp tục mở các $ref của property con và item trong array.

Lồng nhiều cấp là hợp lệ nhưng không nên tạo độ sâu quá mức. Một cấu trúc quá sâu làm client khó dựng payload và khó hiểu quan hệ dữ liệu. Nếu nhiều lớp chỉ chuyển tiếp một field duy nhất, hãy cân nhắc gộp chúng khi điều đó không làm mất ý nghĩa miền nghiệp vụ.

## 5. Tái sử dụng cùng DTO ở nhiều operation

Một trong những lợi ích của component schema là có thể dùng cùng kiểu dữ liệu trong nhiều operation. Ví dụ AddressDto được dùng trong hồ sơ khách hàng và đơn hàng:

~~~java
@Schema(
    name = "Address",
    description = "Địa chỉ liên hệ hoặc giao nhận"
)
public class AddressDto {

    @Schema(example = "12 Nguyen Hue")
    private String street;

    @Schema(example = "Ben Nghe")
    private String ward;

    @Schema(example = "Ho Chi Minh City")
    private String city;

    @Schema(example = "700000")
    private String postalCode;

    // Getters và setters.
}
~~~

Hai DTO khác có thể sử dụng AddressDto:

~~~java
public class CustomerResponse {
    private String id;
    private String fullName;
    private AddressDto address;

    // Getters và setters.
}

public class DeliveryRequest {
    private String orderId;
    private AddressDto destination;

    // Getters và setters.
}
~~~

OpenAPI có thể chứa một component Address được tham chiếu ở cả hai nơi:

~~~yaml
components:
  schemas:
    CustomerResponse:
      type: object
      properties:
        id:
          type: string
        fullName:
          type: string
        address:
          $ref: '#/components/schemas/Address'

    DeliveryRequest:
      type: object
      properties:
        orderId:
          type: string
        destination:
          $ref: '#/components/schemas/Address'

    Address:
      type: object
      properties:
        street:
          type: string
        ward:
          type: string
        city:
          type: string
        postalCode:
          type: string
~~~

Cùng một component được dùng ở nhiều vị trí. Khi cấu trúc Address thay đổi, các tham chiếu đều trỏ đến định nghĩa mới được sinh ra. Điều này giúp giảm trùng lặp, nhưng cũng có nghĩa thay đổi DTO dùng chung có thể ảnh hưởng nhiều endpoint cùng lúc.

Chỉ tái sử dụng DTO khi ngữ nghĩa dữ liệu giống nhau. Hai object có cùng các field nhưng khác ý nghĩa hoặc quy tắc quyền riêng tư có thể cần DTO riêng.

## 6. Đặt tên component bằng @Schema

Tên component được sinh từ class name có thể không đủ rõ, nhất là khi có nhiều lớp cùng tên ở package khác nhau hoặc có nhiều phiên bản DTO. Có thể đặt tên schema bằng @Schema:

~~~java
@Schema(
    name = "PublicCustomer",
    description = "Thông tin khách hàng được phép công bố cho client"
)
public class CustomerPublicResponse {
    private String id;
    private String displayName;

    // Getters và setters.
}
~~~

Một ví dụ khác:

~~~java
@Schema(
    name = "AdminCustomer",
    description = "Thông tin khách hàng dành cho chức năng quản trị"
)
public class CustomerAdminResponse {
    private String id;
    private String displayName;
    private String email;
    private String internalNote;

    // Getters và setters.
}
~~~

Dù hai DTO có một số field giống nhau, chúng có ngữ nghĩa và phạm vi công bố khác nhau. Tên schema rõ ràng giúp người đọc phân biệt và giảm nguy cơ hiểu nhầm dữ liệu nào được trả cho client công khai.

Khi đặt tên component, nên:

- Dùng tên mô tả vai trò và hướng trao đổi, ví dụ CreateOrderRequest hoặc OrderResponse.
- Tránh dùng tên quá chung như Data, Object hoặc Model.
- Giữ tên ổn định giữa các lần phát hành nếu schema được client tham chiếu.
- Tránh hai DTO không liên quan cùng khai báo một tên schema.
- Không đổi tên component tùy tiện nếu tài liệu được dùng làm hợp đồng cho code generation hoặc contract testing.

Tên component là một phần của tài liệu OpenAPI. Thay đổi tên có thể ảnh hưởng đến client sinh mã, file spec đã lưu và các công cụ tham chiếu đến JSON Pointer.

## 7. Hiểu đường dẫn $ref

$ref là một Reference Object hoặc schema reference dùng để trỏ đến định nghĩa khác. Với component schema trong cùng tài liệu, dạng phổ biến là JSON Pointer:

~~~yaml
$ref: '#/components/schemas/Address'
~~~

Đọc đường dẫn:

- Dấu # chỉ tài liệu hiện tại.
- /components đi tới object components.
- /schemas đi tới tập schema.
- /Address chọn schema có tên Address.

Ví dụ:

~~~yaml
components:
  schemas:
    OrderResponse:
      type: object
      properties:
        shippingAddress:
          $ref: '#/components/schemas/Address'
    Address:
      type: object
      properties:
        city:
          type: string
~~~

Khi client đọc OrderResponse, nó phải theo $ref để biết shippingAddress có cấu trúc gì.

Có thể có tham chiếu ngoài tài liệu, ví dụ URL tới một file OpenAPI khác. Tuy nhiên, với tài liệu được springdoc sinh động từ ứng dụng, tham chiếu nội bộ trong components.schemas thường dễ triển khai và phân phối hơn. Tham chiếu ngoài cần bảo đảm tài nguyên được lưu trữ ổn định và công cụ client có thể truy cập.

Không tự ghép tên class vào đường dẫn $ref bằng suy đoán. Hãy đọc JSON thực tế vì tên component có thể được điều chỉnh bởi annotation, generic type, converter hoặc cấu hình thư viện.

## 8. Mô tả field con bằng @Schema

Có thể bổ sung description, example, format, allowableValues và các ràng buộc cho từng property:

~~~java
public class ShippingAddress {

    @Schema(
        description = "Tên người nhận",
        example = "Nguyen Van An",
        minLength = 1,
        maxLength = 100
    )
    private String recipient;

    @Schema(
        description = "Địa chỉ đường và số nhà",
        example = "12 Nguyen Hue",
        maxLength = 255
    )
    private String street;

    @Schema(
        description = "Mã bưu chính",
        example = "700000",
        pattern = "^[0-9]{5,10}$"
    )
    private String postalCode;

    // Getters và setters.
}
~~~

Metadata trên field giúp schema dùng chung có mô tả đầy đủ ở mọi nơi tham chiếu. Nếu field có validation runtime, có thể kết hợp Bean Validation:

~~~java
@NotBlank
@Size(max = 100)
@Schema(
    description = "Tên người nhận",
    example = "Nguyen Van An",
    minLength = 1,
    maxLength = 100
)
private String recipient;
~~~

Cần giữ constraint giữa @Schema và Bean Validation nhất quán. Nếu tài liệu cho phép chuỗi tối đa 100 ký tự nhưng backend chỉ cho 80, client có thể gửi dữ liệu tưởng là hợp lệ nhưng bị từ chối. Nếu backend cho phép nhiều hơn schema, client sinh từ spec có thể tự chặn dữ liệu hợp lệ.

## 9. Tái sử dụng schema với generic wrapper

Nhiều API dùng wrapper chung để đóng gói dữ liệu và metadata phân trang:

~~~java
public class ApiResponse<T> {
    private String code;
    private String message;
    private T data;

    // Getters và setters.
}
~~~

Controller có thể trả về ApiResponse<ProductResponse>:

~~~java
@GetMapping("/api/products/{id}")
public ApiResponse<ProductResponse> getProduct(@PathVariable String id) {
    return productService.getProduct(id);
}
~~~

Hoặc ApiResponse<OrderResponse>:

~~~java
@GetMapping("/api/orders/{id}")
public ApiResponse<OrderResponse> getOrder(@PathVariable String id) {
    return orderService.getOrder(id);
}
~~~

Generic type giúp tái sử dụng wrapper trong Java. springdoc/swagger-core có thể phân giải kiểu tham số hóa để mô tả kiểu của data trong schema. Tên component cụ thể có thể được sinh theo generic signature hoặc cấu hình của thư viện; không nên giả định luôn có một component tên ApiResponse chung.

Nếu cần điều chỉnh schema cho generic wrapper, có thể dùng @Schema(implementation = ...) trên response hoặc tùy biến OpenAPI model. Tuy nhiên, cần bảo đảm schema cuối cùng vẫn phản ánh kiểu data cụ thể của từng operation. Nếu mọi endpoint đều bị mô tả data thành object chung, thông tin kiểu generic đã bị mất và client khó sinh mã chính xác.

Với response phân trang, cân nhắc dùng kiểu Page hoặc DTO phân trang riêng. Nếu public contract cần ổn định, DTO riêng thường kiểm soát được tên field, cấu trúc metadata và định dạng mà client nhìn thấy tốt hơn việc phụ thuộc trực tiếp vào kiểu nội bộ của framework.

## 10. Dùng allOf để biểu diễn schema composition

OpenAPI hỗ trợ composition để kết hợp nhiều schema. allOf yêu cầu instance đáp ứng tất cả schema thành phần. Cơ chế này thường được dùng khi mô tả kiểu dữ liệu có phần chung và phần mở rộng.

Ví dụ:

~~~yaml
components:
  schemas:
    AuditFields:
      type: object
      properties:
        createdAt:
          type: string
          format: date-time
        updatedAt:
          type: string
          format: date-time

    ProductResponse:
      allOf:
        - $ref: '#/components/schemas/AuditFields'
        - type: object
          properties:
            id:
              type: string
            name:
              type: string
~~~

ProductResponse kết hợp các field audit với field riêng của sản phẩm. allOf là cách kết hợp schema trong OpenAPI; nó không phải cơ chế kế thừa Java tự động trong mọi trường hợp.

Nếu dùng Java inheritance, springdoc có thể mô tả quan hệ kế thừa theo metadata và cách swagger-core xử lý model. Để có kết quả ổn định, hãy xem JSON được sinh ra và xác nhận công cụ client hiểu đúng allOf. Không nên dùng allOf chỉ để tránh vài dòng lặp nếu cấu trúc kết quả làm client khó sử dụng.

Cũng cần phân biệt:

- **$ref:** tham chiếu đến một schema đã được định nghĩa.
- **allOf:** kết hợp nhiều schema, tất cả điều kiện thành phần đều phải thỏa.
- **oneOf:** instance phải phù hợp với đúng một trong các schema được liệt kê theo ngữ nghĩa oneOf.
- **anyOf:** instance phù hợp với ít nhất một schema trong danh sách.

Các composition này hữu ích cho mô hình đa hình hoặc dữ liệu có nhiều dạng. Chỉ dùng khi có yêu cầu rõ ràng và kiểm tra bằng validator hoặc client generator tương thích.

## 11. DTO riêng cho request và response

Không nên dùng một DTO duy nhất cho mọi hướng dữ liệu chỉ vì các field trông giống nhau. Request và response thường có khác biệt:

- Request có thể nhận password, secret hoặc dữ liệu ghi.
- Response có thể trả id, createdAt, trạng thái xử lý hoặc computed fields.
- Một field có thể chỉ đọc, chỉ ghi hoặc bị ẩn theo quyền.
- Quy tắc required khi tạo mới có thể khác khi cập nhật.
- Dữ liệu nội bộ không nên xuất hiện trong response công khai.

Ví dụ:

~~~java
public class CreateCustomerRequest {
    @NotBlank
    private String fullName;

    @NotBlank
    @Email
    private String email;

    @NotBlank
    private String password;

    // Getters và setters.
}

@Schema(name = "CustomerResponse")
public class CustomerResponse {
    private String id;
    private String fullName;
    private String email;
    private Instant createdAt;

    // Getters và setters.
}
~~~

CreateCustomerRequest và CustomerResponse có thể dùng chung các kiểu con như AddressDto nếu ngữ nghĩa và phạm vi dữ liệu giống nhau, nhưng không nên đưa password vào schema response.

Việc tách DTO giúp schema phản ánh đúng hợp đồng của từng operation và tránh lộ field không dành cho client. Không nên dựa duy nhất vào @Schema(accessMode = READ_ONLY hoặc WRITE_ONLY) để thay thế việc thiết kế DTO an toàn nếu request và response khác nhau đáng kể.

## 12. Tránh vòng tham chiếu trong DTO

Một số mô hình domain có quan hệ hai chiều: Department chứa danh sách Employee, trong khi Employee lại chứa Department. Nếu đưa trực tiếp entity hoặc DTO tham chiếu hai chiều vào API, tài liệu có thể tạo chuỗi schema đệ quy; serializer JSON cũng có thể gặp vòng lặp tùy cấu hình.

Ví dụ quan hệ dễ gây vòng lặp:

~~~java
public class DepartmentDto {
    private String id;
    private List<EmployeeDto> employees;
}

public class EmployeeDto {
    private String id;
    private DepartmentDto department;
}
~~~

Về mặt schema, tham chiếu đệ quy có thể hợp lệ trong một số mô hình, nhưng cần bảo đảm JSON runtime không tạo vòng lặp vô hạn. Với API đọc danh sách, thường nên giới hạn chiều tham chiếu:

~~~java
public class DepartmentResponse {
    private String id;
    private List<EmployeeSummaryResponse> employees;
}

public class EmployeeSummaryResponse {
    private String id;
    private String displayName;
}
~~~

Nếu cần chi tiết phòng ban từ một nhân viên, cung cấp endpoint hoặc DTO riêng cho phần thông tin đó. Cách thiết kế này giúp kiểm soát kích thước response, tránh lặp dữ liệu và giữ schema dễ đọc.

## 13. Tùy chỉnh component bằng OpenAPI model hoặc customizer

Annotation phù hợp với metadata gắn trực tiếp vào DTO. Khi cần điều chỉnh schema ở cấp tài liệu, có thể dùng bean OpenAPI hoặc customizer do springdoc cung cấp. Ví dụ, bổ sung mô tả hoặc thay đổi metadata của một component sau khi mô hình được tạo.

Cấu hình OpenAPI bean cơ bản:

~~~java
@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI shopOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("Shop API")
                .version("v1")
                .description("API của hệ thống bán hàng"));
    }
}
~~~

Với thay đổi schema chuyên biệt, springdoc cung cấp các extension point như OpenApiCustomizer hoặc OperationCustomizer tùy phạm vi. Dùng customizer khi metadata phụ thuộc toàn tài liệu, group hoặc quy tắc chung; dùng @Schema khi mô tả gắn với một DTO cụ thể.

Không nên tùy biến cùng một field bằng nhiều cơ chế nếu không có quy tắc ưu tiên rõ ràng. Annotation, model bean, customizer và cấu hình global có thể cùng tác động lên tài liệu. Sau khi thêm customizer, hãy kiểm tra kết quả JSON và xác nhận mọi group OpenAPI cần hỗ trợ đều nhận đúng thay đổi.

## 14. Kiểm tra component và $ref trong OpenAPI JSON

Sau khi ứng dụng chạy, lưu tài liệu:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Xem schema gốc của OrderResponse:

~~~bash
jq '.components.schemas.OrderResponse' openapi.json
~~~

Xem response schema của operation:

~~~bash
jq '.paths["/api/orders/{id}"].get.responses["200"].content["application/json"].schema' openapi.json
~~~

Liệt kê component schema:

~~~bash
jq -r '.components.schemas | keys[]' openapi.json
~~~

Tìm các tham chiếu schema:

~~~bash
jq -r '
  .. | objects
  | select(has("$ref"))
  | ."$ref"
' openapi.json
~~~

Đối chiếu các điểm:

- DTO lồng nhau có xuất hiện đúng dưới properties không?
- Collection có type=array và items đúng schema không?
- $ref có trỏ tới component tồn tại không?
- Component được dùng chung có bị sinh nhiều bản trùng tên không?
- Tên schema có rõ nghĩa và ổn định không?
- Generic wrapper có giữ đúng kiểu data cụ thể không?
- Schema request và response có tách đúng field không?
- Có vòng tham chiếu ngoài dự kiến không?

Nếu có validator OpenAPI trong pipeline, chạy validator sau khi tải spec để phát hiện $ref không hợp lệ hoặc schema composition sai cấu trúc. Sau đó thử sinh client hoặc mở Swagger UI để xác nhận công cụ tiêu thụ tài liệu có thể đọc được các component.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| DTO con không xuất hiện trong schema | Kiểu property không được introspect, getter/setter thiếu hoặc field bị ẩn |
| Object lồng nhau xuất hiện inline thay vì $ref | Cách model resolver xử lý kiểu, cấu hình hoặc phiên bản thư viện; kiểm tra JSON trước khi kết luận lỗi |
| Cùng một DTO sinh ra nhiều component gần giống nhau | Tên schema khác nhau do generic, package hoặc annotation |
| Hai DTO khác nhau bị trùng component name | @Schema(name = ...) dùng cùng tên; đổi tên theo ngữ nghĩa |
| Collection không có items schema rõ ràng | Kiểu generic bị mất do raw List hoặc kiểu khai báo quá chung |
| Generic response có data là object không xác định | Kiểu tham số hóa không được giữ trong chữ ký method hoặc schema bị tùy biến quá rộng |
| $ref trỏ tới schema không tồn tại | Tên component bị đổi hoặc tài liệu bị chỉnh sửa thủ công không đồng bộ |
| Client generator xử lý allOf không đúng | Kiểm tra khả năng hỗ trợ composition của generator và cấu trúc OpenAPI |
| Tài liệu có schema đệ quy quá sâu | DTO tham chiếu hai chiều hoặc entity graph được đưa trực tiếp vào API |
| Field nội bộ xuất hiện trong response | Dùng chung DTO request/response hoặc thiếu DTO công khai riêng |

## 16. Quy ước thiết kế DTO và schema dùng chung

Một số quy ước giúp tài liệu OpenAPI ổn định:

- Dùng DTO theo mục đích: CreateRequest, UpdateRequest, DetailResponse và SummaryResponse.
- Tách object con khi có ý nghĩa nghiệp vụ độc lập hoặc được tái sử dụng.
- Dùng tên component rõ ràng bằng @Schema(name = ...) khi cần ổn định hợp đồng.
- Dùng collection có generic type cụ thể như List<OrderItemResponse>, tránh raw List.
- Không đưa entity persistence trực tiếp vào hợp đồng API.
- Giữ mô tả, example và constraint của schema dùng chung nhất quán.
- Tránh vòng tham chiếu hai chiều nếu client không cần cấu trúc đó.
- Kiểm tra ảnh hưởng trên mọi operation dùng component trước khi thay đổi DTO dùng chung.
- Dùng allOf/oneOf/anyOf khi cần composition thực sự, không chỉ để làm ngắn YAML.
- Xác minh OpenAPI JSON và client generator sau các thay đổi cấu trúc.

## 17. Checklist kiểm tra DTO lồng nhau và $ref

- [ ] DTO gốc có schema và properties rõ ràng.
- [ ] Các object con được biểu diễn đúng kiểu.
- [ ] Collection có items schema và generic type cụ thể.
- [ ] DTO được tái sử dụng có component schema phù hợp.
- [ ] Các $ref đều trỏ đến schema tồn tại.
- [ ] Tên component rõ nghĩa và không bị trùng.
- [ ] Request DTO và response DTO không vô tình làm lộ field.
- [ ] Generic wrapper giữ đúng kiểu dữ liệu của từng operation.
- [ ] allOf/oneOf/anyOf được dùng đúng ngữ nghĩa.
- [ ] Không có vòng tham chiếu ngoài dự kiến.
- [ ] Đã kiểm tra /v3/api-docs bằng jq hoặc validator.
- [ ] Swagger UI hoặc client generator đọc được cấu trúc đã sinh.

## 18. Nguồn tra cứu

- [springdoc-openapi – tài liệu chính thức](https://springdoc.org/)
- [Swagger – Using $ref](https://swagger.io/docs/specification/v3_0/using-ref/)
- [OpenAPI Specification – Reference Object](https://spec.openapis.org/oas/latest.html#reference-object)
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object)
- [OpenAPI Specification – Composition and Inheritance](https://spec.openapis.org/oas/latest.html#composition-and-inheritance)
- [Swagger Core – Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations)

springdoc-openapi chuyển kiểu Java và metadata annotation thành các schema trong tài liệu OpenAPI. DTO lồng nhau mô tả cấu trúc phân cấp; component schema và $ref giúp tái sử dụng định nghĩa ở nhiều vị trí. Sau mỗi thay đổi DTO, hãy kiểm tra JSON sinh ra và các operation sử dụng component để bảo đảm hợp đồng vẫn rõ ràng, nhất quán.
