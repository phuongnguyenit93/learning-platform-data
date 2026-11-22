# Schema trùng tên hoặc tham chiếu $ref bị hỏng

## 1. Vì sao lỗi schema và $ref làm hỏng hợp đồng API?

Springdoc OpenAPI tạo schema từ DTO, Java type, Jackson metadata, Bean Validation và Swagger annotations. Các schema thường được đưa vào mục components.schemas rồi được tái sử dụng từ request body, response, parameter hoặc schema lồng nhau bằng tham chiếu $ref.

Cơ chế này giúp document gọn và tránh lặp định nghĩa. Tuy nhiên, nếu hai kiểu Java khác nhau cùng được ánh xạ vào một tên component, hoặc một tham chiếu trỏ tới key không tồn tại, OpenAPI document có thể sai hoặc không còn mô tả đúng payload runtime.

Các biểu hiện thường gặp:

- Hai DTO khác package nhưng cùng tên đơn giản tạo ra component name va chạm.
- Một @Schema(name = "...") được khai báo trùng với schema khác.
- Customizer thêm component có key đã được Springdoc sử dụng.
- Request hoặc response tham chiếu tới tên schema sai chữ hoa/thường.
- $ref dùng sai đường dẫn hoặc JSON Pointer escaping.
- Component bị đổi tên nhưng những nơi tham chiếu vẫn dùng tên cũ.
- Một document group không chứa component mà customizer đang tham chiếu.
- External reference dùng đường dẫn tương đối không còn đúng sau khi phân phối file.

Một document có thể parse được như JSON/YAML nhưng vẫn chứa $ref không resolve. Ngược lại, một reference có thể resolve nhưng trỏ nhầm schema có cấu trúc khác, khiến client generator tạo model sai.

Bài này trình bày cách Springdoc đặt tên và đăng ký schema, cách đọc $ref, cách sửa collision, và cách kiểm tra contract trước khi publish.

## 2. components.schemas là kho định nghĩa dùng chung

OpenAPI đặt các schema có thể tái sử dụng trong components.schemas. Ví dụ:

~~~yaml
openapi: 3.1.0
info:
  title: Order API
  version: "1.0.0"

paths:
  /api/orders/{id}:
    get:
      responses:
        "200":
          description: Order được tìm thấy
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/OrderResponse"

components:
  schemas:
    OrderResponse:
      type: object
      required:
        - id
        - status
      properties:
        id:
          type: string
        status:
          type: string
          enum:
            - NEW
            - SHIPPED
~~~

Trong ví dụ, response không lặp lại toàn bộ cấu trúc OrderResponse. Nó tham chiếu đến component có key OrderResponse.

Các điểm cần nhớ:

- components.schemas là một map.
- Mỗi key trong map là tên schema công khai trong document.
- $ref phải trỏ chính xác tới key đó.
- Tên key phân biệt chữ hoa và chữ thường.
- Việc đổi key là thay đổi contract, vì client generator có thể dùng key đó làm tên model.

Một DTO có thể được dùng ở nhiều operation. Springdoc thường tạo một component schema rồi tham chiếu từ các vị trí sử dụng. Nếu cùng một kiểu xuất hiện trong nhiều response, tái sử dụng component giúp giữ một định nghĩa nhất quán.

## 3. Vì sao hai lớp Java có thể trùng tên schema?

Tên lớp Java đơn giản không nhất thiết duy nhất trong toàn bộ ứng dụng. Ví dụ:

~~~text
com.acme.identity.dto.UserDto
com.acme.billing.dto.UserDto
~~~

Hai lớp này có cùng simple name là UserDto nhưng có ý nghĩa khác nhau:

- Identity UserDto có id, displayName và roles.
- Billing UserDto có customerNumber, taxCode và billingAddress.

Nếu cả hai được ánh xạ vào cùng một component key UserDto, một định nghĩa có thể va chạm với định nghĩa còn lại. Tùy cách resolver và phiên bản thư viện, document có thể tạo tên khác, ghi đè, hoặc không biểu diễn đúng model mà operation cần.

Các nguồn collision thường gặp:

- Hai class cùng simple name ở package khác nhau.
- DTO nested có tên giống top-level DTO.
- Hai module độc lập khai báo schema cùng tên.
- Nhiều annotation @Schema đặt cùng name.
- Customizer hoặc ModelConverter tự đăng ký schema trùng key.
- Một component thủ công trùng tên với component Springdoc đã sinh.
- Refactor đổi package nhưng không kiểm tra tên component đã phát hành.

Không nên dựa vào thứ tự scan class hoặc thứ tự khởi tạo bean để giải quyết collision. Kết quả cần ổn định giữa local, CI và production.

## 4. Dùng tên schema rõ nghĩa với @Schema(name)

Với schema public, cách dễ kiểm soát là đặt tên component rõ nghĩa bằng @Schema(name = "...").

Ví dụ hai DTO cùng tên Java nhưng khác miền nghiệp vụ:

~~~java
package com.acme.identity.dto;

@Schema(name = "IdentityUser")
public record UserDto(
    String id,
    String displayName,
    List<String> roles
) {
}
~~~

~~~java
package com.acme.billing.dto;

@Schema(name = "BillingCustomer")
public record UserDto(
    String customerNumber,
    String taxCode,
    BillingAddress billingAddress
) {
}
~~~

Trong OpenAPI document, hai component có tên IdentityUser và BillingCustomer. Tên Java vẫn có thể là UserDto trong package riêng, nhưng tên contract đã rõ nghĩa.

Quy tắc đặt tên nên:

- Duy nhất trong toàn document.
- Phản ánh khái niệm nghiệp vụ, không chỉ tên package.
- Ổn định qua refactor package.
- Dễ đọc trong generated SDK.
- Không thay đổi tùy môi trường hoặc thứ tự khởi động.
- Được dùng nhất quán trong tài liệu và test.

Đối với API đã phát hành, không đổi schema name tùy tiện. Việc đổi tên component có thể làm client SDK thay đổi tên class dù JSON wire format không đổi. Hãy coi schema name là một phần của trải nghiệm contract và review diff trước khi đổi.

## 5. Khi nào cân nhắc dùng fully qualified class name?

Springdoc có cấu hình dùng fully qualified name cho schema, thường được điều khiển bằng thuộc tính springdoc.use-fqn ở các phiên bản hỗ trợ:

~~~yaml
springdoc:
  use-fqn: true
~~~

Cách này giúp phân biệt các class cùng simple name bằng tên đầy đủ có package. Ví dụ component name có thể phản ánh package thay vì chỉ UserDto.

Đây là lựa chọn có thể hữu ích với codebase lớn có nhiều module và nhiều DTO trùng simple name. Tuy nhiên, cần cân nhắc:

- Tên component dài và gắn với cấu trúc package nội bộ.
- Refactor package có thể làm thay đổi schema name.
- Generated SDK có thể sinh tên model dài hoặc khác trước.
- Bật thuộc tính trên API đã phát hành có thể tạo một diff lớn dù JSON payload không đổi.
- Cần kiểm tra property có được hỗ trợ ở đúng phiên bản Springdoc đang dùng.

Với public API cần tên contract ổn định, explicit @Schema(name = "...") thường giúp kiểm soát tốt hơn. use-fqn có thể phù hợp khi muốn tự động phân biệt model và chấp nhận tên schema gắn với package.

Không bật use-fqn chỉ để che một collision mà chưa xác định nguyên nhân. Trước tiên hãy tìm các class hoặc customizer đang đăng ký cùng component name.

## 6. Đặt tên schema theo miền nghiệp vụ

Một convention có thể dùng:

| Miền | Tên component gợi ý |
|---|---|
| Identity | IdentityUser, IdentityRole |
| Billing | BillingCustomer, InvoiceSummary |
| Order | OrderResponse, OrderLine |
| Payment | PaymentRequest, PaymentResult |
| Shared primitives | Money, Address, PageMetadata |

Tên schema không nhất thiết phải chứa hậu tố Dto. Component là tên model trong API contract; nó có thể được sinh từ DTO Java nhưng không cần phơi bày tên lớp nội bộ.

Tránh các tên chung chung như Data, Result, Response, Item nếu nhiều module cùng dùng. Nếu schema thực sự khác nhau, hãy đặt tên thể hiện phạm vi hoặc ý nghĩa.

Không tạo nhiều component khác nhau chỉ để đổi tên nếu chúng có cùng ý nghĩa và cần đồng bộ. Với kiểu dùng chung thật sự, tái sử dụng một schema chung. Với hai khái niệm nghiệp vụ khác nhau, dùng hai schema riêng dù field hiện tại giống nhau.

## 7. Dùng @Schema(implementation = ...) để chỉ rõ kiểu

Khi Springdoc không suy ra đúng schema từ wrapper hoặc generic return type, có thể chỉ rõ implementation trong annotation.

Ví dụ response:

~~~java
@GetMapping("/{id}")
@ApiResponse(
    responseCode = "200",
    description = "Tìm thấy đơn hàng",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = OrderResponse.class)
    )
)
public ResponseEntity<?> findById(@PathVariable String id) {
    return ResponseEntity.ok(orderService.findById(id));
}
~~~

implementation chỉ rõ class được dùng để mô tả schema response. Nó không thay đổi object thực tế mà controller trả về.

Nếu controller trả ApiEnvelope<OrderResponse>, nhưng annotation lại khai báo OrderResponse trực tiếp, document sẽ mô tả sai cấu trúc wrapper. Hãy chọn implementation phản ánh đúng JSON wire format.

Ví dụ:

~~~java
public record ApiEnvelope<T>(
    String requestId,
    T data
) {
}
~~~

Nếu runtime JSON là envelope có data, OpenAPI cần mô tả wrapper tương ứng. Với generic schema phức tạp, kiểm tra document do đúng phiên bản Springdoc tạo ra thay vì giả định annotation đã giải quyết mọi type parameter.

## 8. Không đăng ký component thủ công trùng tên

Một customizer có thể thêm schema vào components:

~~~java
@Bean
OpenApiCustomizer customSchemaCustomizer() {
    return openApi -> {
        if (openApi.getComponents() == null) {
            openApi.setComponents(new Components());
        }

        Schema<?> externalEvent = new ObjectSchema()
            .addProperty("eventId", new StringSchema())
            .addProperty("eventType", new StringSchema());

        openApi.getComponents()
            .addSchemas("ExternalEvent", externalEvent);
    };
}
~~~

Đoạn code minh họa việc thêm component ExternalEvent. Trước khi đăng ký, cần xác minh key chưa tồn tại.

Nếu key đã tồn tại, không ghi đè một cách im lặng. Có thể kiểm tra:

~~~java
Map<String, Schema> schemas =
    openApi.getComponents().getSchemas();

if (schemas == null || !schemas.containsKey("ExternalEvent")) {
    openApi.getComponents()
        .addSchemas("ExternalEvent", externalEvent);
}
~~~

Nếu component đã tồn tại, cần quyết định rõ dùng schema hiện có hay dừng với lỗi cấu hình. Không nên chỉ kiểm tra key rồi bỏ qua mà không biết schema hiện tại có đúng nội dung cần thiết không.

Trong ứng dụng thực tế, nên tạo helper kiểm tra tên component và báo lỗi khi một key được đăng ký bởi hai nguồn khác nhau. Điều này giúp phát hiện collision ngay trong lúc tạo document.

## 9. Cấu trúc $ref nội bộ

Một local reference thường bắt đầu từ root document:

~~~yaml
$ref: "#/components/schemas/OrderResponse"
~~~

Các phần trong reference:

- # chỉ root của document hiện tại.
- /components đi tới object components.
- /schemas đi tới map schemas.
- /OrderResponse chọn component có key OrderResponse.

Reference phải trỏ tới đúng node. Ví dụ sau là sai nếu component nằm trong components.schemas:

~~~yaml
$ref: "#/schemas/OrderResponse"
~~~

Ví dụ này cũng sai nếu key thực tế là OrderResponse:

~~~yaml
$ref: "#/components/schemas/orderResponse"
~~~

JSON Pointer phân biệt chữ hoa/thường. Hãy sao chép chính xác key được định nghĩa trong components.schemas.

## 10. JSON Pointer escaping trong tên component

$ref dùng URI fragment và JSON Pointer. Nếu key có ký tự đặc biệt, cần escape theo quy tắc JSON Pointer:

- Dấu ~ được thay bằng ~0.
- Dấu / được thay bằng ~1.

Ví dụ key có tên:

~~~text
Legacy/Order~V1
~~~

Reference tương ứng phải encode token:

~~~yaml
$ref: "#/components/schemas/Legacy~1Order~0V1"
~~~

Để giảm lỗi, nên tránh slash và tilde trong component key. Dùng tên chữ-số và PascalCase thường dễ đọc, dễ test và tương thích với nhiều generator hơn.

Không dùng URL encoding thay cho JSON Pointer escaping. Hai cơ chế này khác nhau. Khi có key đặc biệt, dùng OpenAPI-aware parser để resolve reference thay vì tự tách chuỗi bằng script.

## 11. Các dạng $ref thường gặp

Schema có thể được tham chiếu ở nhiều vị trí:

**Response body**

~~~yaml
responses:
  "200":
    description: Thành công
    content:
      application/json:
        schema:
          $ref: "#/components/schemas/OrderResponse"
~~~

**Request body**

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: "#/components/schemas/CreateOrderRequest"
~~~

**Array item**

~~~yaml
type: array
items:
  $ref: "#/components/schemas/OrderLine"
~~~

**Property lồng nhau**

~~~yaml
properties:
  customer:
    $ref: "#/components/schemas/BillingCustomer"
~~~

**Composition**

~~~yaml
allOf:
  - $ref: "#/components/schemas/BaseEvent"
  - type: object
    properties:
      orderId:
        type: string
~~~

Không phải mọi $ref đều trỏ tới components.schemas. OpenAPI còn có thể tham chiếu parameters, responses, requestBodies, headers, examples và securitySchemes. Khi debug, cần kiểm tra đúng loại object và đúng đường dẫn components.

## 12. Những lỗi tham chiếu thường gặp

| Reference | Vấn đề |
|---|---|
| #/components/schemas/Order | Đúng nếu key Order tồn tại |
| #/components/schema/Order | Sai tên nhánh: schemas có chữ s |
| #/components/schemas/order | Sai nếu key là Order |
| #/schemas/Order | Thiếu components |
| #/components/schemas/OrderResponse | Sai nếu component đã đổi tên |
| #/components/responses/OrderResponse | Sai loại component nếu key nằm trong schemas |
| #/components/schemas/Legacy~Order | Sai escaping nếu key chứa dấu ~ |
| #/components/schemas/Legacy/Order | Sai nếu slash trong key chưa được escape |

Một lỗi phổ biến là đổi @Schema(name = "OrderView") nhưng customizer hoặc file OpenAPI thủ công vẫn tham chiếu OrderResponse. Hãy tìm tất cả nơi sử dụng schema name cũ và cập nhật cùng một thay đổi.

## 13. Tránh hard-code $ref khi có thể để Springdoc suy luận

Nếu controller dùng DTO trực tiếp, Springdoc thường tự tạo component và reference phù hợp:

~~~java
@GetMapping("/{id}")
public OrderResponse getOrder(@PathVariable String id) {
    return orderService.getOrder(id);
}
~~~

Khi cần khai báo response rõ hơn, dùng implementation:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Order được tìm thấy",
    content = @Content(
        schema = @Schema(implementation = OrderResponse.class)
    )
)
~~~

Cách này liên kết schema với Java type, giảm nguy cơ gõ sai tên component trong một chuỗi $ref thủ công.

Hard-code $ref có thể cần thiết khi bổ sung cấu trúc OpenAPI bằng customizer hoặc khi tham chiếu external document. Khi đó, tên component và nơi đăng ký phải được quản lý cùng nhau.

Không tạo một component key giả định trước khi biết Springdoc thực sự đặt tên schema ra sao. Hãy xem output /v3/api-docs hoặc đặt explicit schema name.

## 14. $ref trong OpenAPI 3.0 và 3.1

Cách xử lý sibling fields quanh $ref có khác biệt theo phiên bản và ngữ cảnh.

Trong OpenAPI 3.0, Reference Object có giới hạn chặt; các sibling ngoài $ref không được xử lý như thuộc tính tùy ý. Ví dụ:

~~~yaml
$ref: "#/components/schemas/Order"
description: Order response
~~~

không nên được dùng với giả định description luôn được áp dụng như một Schema Object thông thường trong mọi ngữ cảnh 3.0.

OpenAPI 3.1 cập nhật Reference Object để hỗ trợ summary và description theo quy tắc chuẩn. Trong Schema Object, $ref tuân theo ngữ nghĩa JSON Schema 2020-12, nên sibling schema keywords được xử lý theo quy tắc JSON Schema.

Khi cần mô tả thêm, hãy chọn cấu trúc đúng theo vị trí và phiên bản OpenAPI document. Không áp dụng một quy tắc duy nhất cho mọi loại $ref.

Nếu API hỗ trợ cả 3.0 và 3.1, hãy validate từng document bằng validator tương ứng. Một document hợp lệ ở 3.1 không có nghĩa parser cũ hiểu cùng cách.

## 15. Phân biệt reference bị hỏng và schema đệ quy hợp lệ

Một số model có quan hệ đệ quy:

~~~java
public record Category(
    String id,
    String name,
    Category parent
) {
}
~~~

Schema có thể tham chiếu chính nó:

~~~yaml
Category:
  type: object
  properties:
    id:
      type: string
    name:
      type: string
    parent:
      $ref: "#/components/schemas/Category"
~~~

Đây là recursive schema hợp lệ nếu cấu trúc và use case phù hợp. Không phải cứ $ref tạo vòng là broken reference.

Một broken reference là tham chiếu không resolve được hoặc trỏ sai node. Một recursive reference resolve về chính component hoặc chuỗi component hợp lệ.

Không inline đệ quy vô hạn khi bundle document. Hãy giữ $ref để biểu diễn quan hệ và dùng tool hiểu OpenAPI để kiểm tra.

Nếu recursive schema có thể tạo payload quá sâu, hãy cân nhắc giới hạn độ sâu ở API contract hoặc application validation. OpenAPI schema không tự giới hạn kích thước dữ liệu runtime nếu không có constraint phù hợp.

## 16. External $ref và đường dẫn khi phân phối

OpenAPI có thể tham chiếu file hoặc URL bên ngoài:

~~~yaml
$ref: "./schemas/common.yaml#/components/schemas/Address"
~~~

Hoặc:

~~~yaml
$ref: "https://contracts.example.com/common/1.2.0.yaml#/components/schemas/Address"
~~~

External reference tạo thêm phụ thuộc vào vị trí và khả năng truy cập của file đích.

Các lỗi thường gặp:

- File common.yaml không được đóng gói cùng artifact.
- Relative path được tính từ base URI khác dự kiến.
- URL yêu cầu authentication mà generator không có.
- URL trỏ tới nội dung thay đổi theo thời gian.
- Môi trường CI không có network access.
- Khi upload document lên portal, cấu trúc thư mục bị thay đổi làm hỏng relative ref.

Với tài liệu cần phân phối độc lập, có thể bundle các external references thành một document đã resolve nếu toolchain và policy cho phép. Nếu giữ external reference, phải publish đầy đủ dependency và giữ nguyên cấu trúc URI.

Không dùng đường dẫn file local như C:/work/contracts/common.yaml hoặc /home/runner/... trong document public. Đường dẫn local không có ý nghĩa với client và làm lộ thông tin môi trường build.

## 17. Kiểm tra component trong document group

Springdoc có thể tạo nhiều document qua GroupedOpenApi. Mỗi group chỉ bao gồm các operation theo filter đã cấu hình.

Ví dụ:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/public/**")
        .build();
}
~~~

Nếu customizer thêm một operation vào group public và operation đó tham chiếu component mà group không chứa, document có thể có $ref bị hỏng.

Tương tự, một schema được thêm thủ công vào default OpenAPI document không nhất thiết xuất hiện trong mọi group document. Hãy kiểm tra customizer áp dụng ở phạm vi global hay group-specific theo phiên bản Springdoc.

Với mỗi group được publish:

- Tải đúng endpoint group.
- Kiểm tra component được tham chiếu có trong cùng document.
- Resolve toàn bộ local $ref trong group.
- Kiểm tra không có schema internal bị lộ sang public.
- Chạy validator riêng cho từng group.

Không lấy kết quả validate của default document để kết luận tất cả group đều hợp lệ.

## 18. Cẩn thận khi customizer thay thế component map

Một customizer có thể thêm schema nhưng vô tình thay cả map components:

~~~java
openApi.setComponents(new Components()
    .addSchemas("ExternalEvent", externalEvent));
~~~

Nếu Springdoc đã tạo OrderResponse, Customer và các schema khác, đoạn code này có thể loại bỏ chúng khỏi document.

Thay vì thay toàn bộ Components, hãy lấy object hiện tại và thêm schema cần thiết:

~~~java
Components components = openApi.getComponents();

if (components == null) {
    components = new Components();
    openApi.setComponents(components);
}

Map<String, Schema> schemas = components.getSchemas();

if (schemas == null || !schemas.containsKey("ExternalEvent")) {
    components.addSchemas("ExternalEvent", externalEvent);
}
~~~

Nếu tên đã tồn tại, hãy so sánh schema và báo lỗi khi hai nguồn định nghĩa khác nhau. Không ghi đè lặng lẽ vì nó có thể thay đổi response schema của operation khác.

Customizer nên deterministic: cùng source và configuration phải tạo cùng components, cùng key và cùng references. Tránh phụ thuộc thứ tự khởi tạo bean hoặc dữ liệu request.

## 19. Tìm nguyên nhân collision trong Springdoc

Khi phát hiện component trùng tên:

1. Xác định component key đang bị trùng trong OpenAPI output.
2. Tìm các DTO có simple name tương ứng.
3. Kiểm tra package và nested class.
4. Tìm annotation @Schema(name = "...") có cùng giá trị.
5. Kiểm tra ModelConverter và OpenApiCustomizer tự đăng ký schema.
6. Kiểm tra dependency/module có mang DTO cùng tên.
7. So sánh document trước và sau khi thêm module hoặc dependency.
8. Đặt explicit schema name cho các model khác nhau.
9. Nếu dùng use-fqn, đánh giá tác động tới tên contract và generated client.
10. Tải lại document và xác nhận mỗi operation tham chiếu đúng component.

Đừng chỉ sửa tên component trong output YAML sau khi generate. Lần sinh tiếp theo sẽ tạo lại collision nếu nguyên nhân trong Java annotation hoặc customizer chưa được sửa.

## 20. Kiểm thử $ref bằng MockMvc

Có thể kiểm tra endpoint OpenAPI được Springdoc tạo bằng MockMvc.

Ví dụ xác nhận component tồn tại:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.components.schemas.IdentityUser"
    ).exists())
    .andExpect(jsonPath(
        "$.components.schemas.BillingCustomer"
    ).exists());
~~~

Kiểm tra operation tham chiếu schema đúng:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.paths['/api/identity/users/{id}'].get.responses['200']"
        + ".content['application/json'].schema['$ref']"
    ).value("#/components/schemas/IdentityUser"));
~~~

JSONPath cần điều chỉnh theo path và operation thực tế của ứng dụng. Test nên xác minh cả component và reference, không chỉ kiểm tra document trả HTTP 200.

Với document group, gọi endpoint group và chạy cùng các assertion cho group đó. Với external reference, cần test bundle hoặc resolver theo đúng cách artifact sẽ được phân phối.

## 21. Validate toàn bộ references bằng công cụ OpenAPI

MockMvc assertions hữu ích cho các schema quan trọng nhưng không thay thế việc resolve tất cả references.

Có thể dùng OpenAPI Generator CLI:

~~~bash
openapi-generator-cli validate -i target/openapi/openapi.yaml
~~~

Hoặc Redocly CLI:

~~~bash
npx redocly lint target/openapi/openapi.yaml
~~~

Pin version tool trong CI. Chọn version hiểu OpenAPI 3.0 hoặc 3.1 tương ứng với document.

Với external reference, cấu hình resolver và network policy rõ ràng. Nếu pipeline không thể truy cập external URL, lỗi resolve phải làm job fail thay vì bị bỏ qua.

Validator có thể phát hiện reference không tồn tại, object sai vị trí hoặc schema không hợp lệ. Linter có thể bổ sung rule về naming, description và cấu trúc. Cần phân biệt lỗi chuẩn OpenAPI với warning theo quy ước nội bộ.

## 22. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Hai DTO khác package dùng chung component | Cùng simple name | Đặt @Schema(name) duy nhất hoặc đánh giá use-fqn |
| Component bị mất sau customizer | Thay toàn bộ Components | Thêm vào object hiện có, không thay map |
| $ref trả lỗi unresolved | Sai key hoặc sai path | So khớp chính xác components và key |
| $ref sai chữ hoa/thường | Key phân biệt case | Dùng đúng tên component |
| Ref có slash hoặc tilde bị lỗi | JSON Pointer chưa escape | Dùng ~1 và ~0 đúng quy tắc |
| Đổi @Schema(name) làm document lỗi | Ref thủ công vẫn dùng tên cũ | Cập nhật mọi reference và test |
| Schema response sai cấu trúc | implementation trỏ nhầm DTO/wrapper | Mô tả đúng wire type |
| Group document thiếu schema | Component không được thêm vào group | Dùng customizer phù hợp và validate từng group |
| External ref không resolve trong CI | URL/path hoặc quyền truy cập sai | Bundle hoặc publish dependency cùng cấu trúc |
| Recursive model bị báo vòng | Tool không xử lý recursion đúng | Dùng OpenAPI-aware validator và giữ ref |
| YAML có duplicate key | Hai schema cùng key trong file thủ công | Dùng key duy nhất và parser strict |
| Generated SDK đổi tên model hàng loạt | Bật use-fqn hoặc đổi naming convention | Review compatibility và giữ tên contract ổn định |

Khi điều tra, hãy lưu OpenAPI JSON/YAML đầu ra và xác định chính xác component key nào bị thiếu hoặc trùng. Đừng chỉ nhìn annotation rồi suy ra document đã được tạo đúng.

## 23. Quy trình sửa lỗi an toàn

Khi gặp schema collision hoặc broken $ref:

1. Lấy OpenAPI document thực tế từ đúng endpoint và đúng group.
2. Xác định reference bị lỗi và component key được mong đợi.
3. Kiểm tra component có tồn tại trong cùng document hay không.
4. Tìm DTO, annotation và customizer tạo component key đó.
5. Đặt tên duy nhất cho các model khác nhau.
6. Giữ schema name hiện tại nếu nó đã là contract public ổn định.
7. Sửa customizer để không ghi đè Components hoặc schema hiện hữu.
8. Kiểm tra JSON Pointer escaping nếu key có ký tự đặc biệt.
9. Kiểm tra external ref và relative base URI.
10. Xác minh group-specific document.
11. Chạy MockMvc test cho component và operation quan trọng.
12. Chạy OpenAPI validator/linter để resolve toàn bộ references.
13. So sánh contract diff trước khi phát hành.

Nếu thay schema name của API đã được client sử dụng, hãy xem đó là thay đổi contract. Có thể cần giữ alias hoặc component cũ trong thời gian chuyển tiếp, hoặc phát hành API version mới theo chính sách của tổ chức.

## 24. Nguyên tắc giữ schema và reference ổn định

Để tránh schema trùng tên và $ref bị hỏng:

1. Đặt tên component duy nhất và có ý nghĩa nghiệp vụ.
2. Dùng @Schema(name) khi nhiều class có cùng simple name.
3. Chỉ bật springdoc.use-fqn sau khi đánh giá ảnh hưởng contract.
4. Dùng @Schema(implementation) đúng với JSON runtime.
5. Không đăng ký component trùng key bằng customizer.
6. Không thay toàn bộ Components khi chỉ muốn thêm một schema.
7. Kiểm tra $ref đúng path, đúng case và đúng JSON Pointer escaping.
8. Phân biệt local reference, external reference và recursive reference.
9. Validate từng document group độc lập.
10. Dùng MockMvc để kiểm tra component và operation quan trọng.
11. Chạy OpenAPI-aware validator/linter trong CI.
12. Review schema rename như một thay đổi API contract.

Schema là mô hình dữ liệu mà client dùng để sinh code và xử lý request/response. Một tên component trùng hoặc một $ref sai có thể làm hỏng cả quá trình tích hợp dù controller vẫn chạy bình thường. Kiểm soát tên schema, giữ references đồng bộ và validate document được Springdoc sinh ra sẽ giúp hợp đồng API ổn định qua các lần mở rộng module và refactor code.

## 25. Tài liệu tham khảo

- Springdoc OpenAPI: https://springdoc.org/
- Springdoc Configuration Properties: https://springdoc.org/properties.html
- OpenAPI Specification: https://spec.openapis.org/oas/latest.html
- Swagger Core Annotations: https://github.com/swagger-api/swagger-core
- OpenAPI Generator CLI: https://openapi-generator.tech/docs/usage/

