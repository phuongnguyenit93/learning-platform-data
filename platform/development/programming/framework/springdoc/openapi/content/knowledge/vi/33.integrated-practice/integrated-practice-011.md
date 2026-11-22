# Chẩn đoán một lỗi schema hoặc mapping từ dữ liệu quan sát

Khi một API chạy được nhưng tài liệu OpenAPI mô tả sai request hoặc response, việc sửa annotation ngay lập tức thường làm vấn đề khó tìm hơn. Hãy bắt đầu từ dữ liệu quan sát được: request mà client gửi, response mà server thực sự trả về, cấu hình được Swagger UI tải và schema mà springdoc-openapi sinh ra. Đối chiếu bốn nguồn này sẽ giúp xác định lỗi nằm ở HTTP mapping, Jackson serialization, validation, khai báo DTO hay lớp chuyển đổi phía sau ứng dụng.

Bài thực hành này dùng một endpoint đọc đơn hàng để chẩn đoán sai tên thuộc tính trong response, sau đó mở rộng phương pháp sang query parameter, request body, generic response và trường nullable. Mục tiêu là sửa đúng lớp chịu trách nhiệm và chứng minh hợp đồng đã khớp bằng kiểm tra runtime lẫn kiểm tra tài liệu.

## 1. Phân biệt dữ liệu runtime với hợp đồng OpenAPI

Một request đi qua nhiều lớp trước khi trở thành dữ liệu mà client nhìn thấy:

1. Spring MVC hoặc WebFlux ánh xạ URL, HTTP method, path variable, query parameter, header và body vào tham số của controller.
2. Jackson hoặc converter tương ứng đọc JSON thành DTO, sau đó ghi DTO thành JSON response.
3. Bean Validation và logic ứng dụng kiểm tra dữ liệu theo các quy tắc của endpoint.
4. springdoc-openapi phân tích controller, kiểu dữ liệu, annotation, cấu hình Jackson và các thành phần liên quan để sinh mô tả OpenAPI.
5. Gateway hoặc reverse proxy có thể tiếp tục thay đổi đường dẫn, header hoặc nội dung trước khi client nhận được response.

OpenAPI mô tả hợp đồng HTTP mà client cần sử dụng. Vì vậy, dữ liệu cuối cùng qua URL công khai là bằng chứng quan trọng nhất khi ứng dụng chạy sau gateway. Schema được sinh từ DTO có thể đúng với model Java nhưng vẫn không mô tả đúng response nếu serializer tùy chỉnh, controller trả về kiểu khác hoặc proxy biến đổi JSON.

Hãy phân biệt các khái niệm sau:

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Request mapping | Client phải gọi method và URL nào? |
| Parameter mapping | Giá trị nằm trong path, query, header, cookie hay request body? |
| Serialization | Tên field, kiểu dữ liệu, định dạng ngày giờ và cấu trúc JSON thực tế là gì? |
| Validation | Giá trị nào được chấp nhận hoặc bị từ chối? |
| OpenAPI schema | Tài liệu mô tả property, required, nullable, format và response nào? |
| Gateway transformation | Client có nhận đúng payload mà ứng dụng Spring trả về hay payload đã bị thay đổi? |

Không dùng riêng một nguồn làm kết luận. Ví dụ, DTO có trường **createdAt** chưa chứng minh JSON bên ngoài cũng có tên **createdAt**; Jackson có thể đổi tên thuộc tính khi serialize.

## 2. Thu thập bằng chứng trước khi sửa

Chọn một request có thể tái hiện lỗi và lưu lại đầy đủ:

- HTTP method, URL công khai và query string.
- Request headers quan trọng như **Content-Type**, **Accept** và thông tin xác thực đã được phép sử dụng.
- Request body nguyên bản nếu endpoint có body.
- HTTP status, response headers và response body.
- URL của OpenAPI JSON mà Swagger UI đang sử dụng.
- Schema của operation tương ứng trong OpenAPI JSON.
- Log phía ứng dụng tại cùng thời điểm nếu có lỗi binding, conversion hoặc validation.

Ví dụ lấy response thực tế:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/orders/42
~~~

Lấy tài liệu OpenAPI:

~~~bash
curl -s http://localhost:8080/v3/api-docs -o openapi.json
~~~

Nếu môi trường yêu cầu xác thực, thực hiện request với tài khoản hoặc token được cấp quyền. Nếu ứng dụng chạy dưới context path, có API docs path tùy chỉnh hoặc nằm sau proxy, hãy thay URL bằng địa chỉ thực tế. Không kết luận từ URL mặc định khi cấu hình triển khai đã thay đổi.

Có thể dùng jq để xem nhanh schema response của operation:

~~~bash
jq '.paths["/api/orders/{id}"].get.responses["200"].content["application/json"].schema' openapi.json
jq '.components.schemas.OrderView' openapi.json
~~~

Tên schema và response code trong lệnh phải khớp với tài liệu thực tế. Nếu operation trả về 201, 204 hoặc response dùng media type khác, hãy truy vấn đúng nhánh tương ứng.

Ghi kết quả vào một bảng so sánh trước khi chỉnh sửa:

| Hạng mục | Quan sát từ HTTP | Quan sát từ OpenAPI | Kết luận cần xác minh |
| --- | --- | --- | --- |
| URL và method | Request client thực sự gọi | Path và operation trong tài liệu | Controller mapping có khớp không? |
| Tên property | Key trong JSON response | Property trong schema | Jackson hoặc lớp biến đổi có đổi tên không? |
| Kiểu dữ liệu | Giá trị JSON và kiểu token | type, format trong schema | Runtime đang trả string, number, object hay array? |
| Required | Field có luôn xuất hiện không | Danh sách required | Field bị bỏ qua hay thực sự bắt buộc? |
| Nullable | Field có thể nhận JSON null không | nullable hoặc schema cho phép null | Hợp đồng có diễn tả đúng null không? |
| Parameter | Vị trí client truyền giá trị | in: path, query, header, cookie | Annotation mapping có đúng vị trí không? |

## 3. Tình huống thực hành: JSON response dùng tên snake_case

Giả sử endpoint **GET /api/orders/42** trả về:

~~~json
{
  "order_id": 42,
  "created_at": "2026-11-20T08:15:00Z",
  "status": "PAID",
  "customer": {
    "full_name": "Nguyen An"
  },
  "total": 125000.00
}
~~~

Trong khi schema OpenAPI lại hiển thị:

~~~yaml
OrderView:
  type: object
  properties:
    id:
      type: integer
      format: int64
    createdAt:
      type: string
      format: date-time
    status:
      type: string
    customer:
      $ref: '#/components/schemas/CustomerView'
    total:
      type: number
CustomerView:
  type: object
  properties:
    fullName:
      type: string
~~~

Client sinh code từ schema sẽ đọc **id**, **createdAt** và **customer.fullName**, nhưng server gửi **order_id**, **created_at** và **customer.full_name**. Đây là lỗi hợp đồng property name. Việc chỉ đổi tên field trong tài liệu mà không hiểu serializer đang hoạt động thế nào có thể làm request hoặc response ở một môi trường khác tiếp tục sai.

Trước tiên, kiểm tra payload ở hai điểm nếu có gateway:

1. Gọi trực tiếp ứng dụng Spring Boot và lưu response.
2. Gọi URL công khai qua gateway và lưu response.

Nếu hai payload khác nhau, lớp gateway hoặc adapter bên ngoài đang biến đổi dữ liệu. Schema công khai cần mô tả payload mà client thực sự nhận; đồng thời phải quyết định rõ lớp nào sở hữu việc chuyển đổi đó. Nếu hai payload giống nhau, kiểm tra cấu hình Jackson, serializer, mixin, annotation và kiểu response mà controller trả về.

Các nguyên nhân thường gặp gồm:

- ObjectMapper đang dùng naming strategy như **SNAKE_CASE**.
- DTO hoặc getter có **@JsonProperty** chỉ định tên JSON khác tên Java.
- **@JsonAlias** được dùng để chấp nhận tên đầu vào khác nhưng bị hiểu nhầm là tên field khi serialize.
- Custom serializer, mixin hoặc module Jackson thay đổi cấu trúc JSON.
- Controller trả về **Map**, **JsonNode**, projection hoặc DTO khác với kiểu mà người viết tài liệu nghĩ đến.
- Gateway đổi tên field hoặc đóng gói response sau khi Spring Boot đã hoàn thành serialization.

Hãy kiểm tra ObjectMapper thực sự được MVC/WebFlux sử dụng và mọi cấu hình serializer đang áp dụng cho endpoint. Nếu chỉ có một endpoint dùng response mapping riêng, đừng suy rộng rằng toàn bộ module đang dùng cùng một naming strategy.

## 4. Sửa tên property tại đúng lớp

Nếu tên JSON là một phần ổn định của hợp đồng API, có thể khai báo tường minh trên DTO bằng Jackson annotation. Ví dụ dùng Java record:

~~~java
public record CustomerView(
    @JsonProperty("full_name")
    String fullName
) {}

public record OrderView(
    @JsonProperty("order_id")
    Long id,

    @JsonProperty("created_at")
    Instant createdAt,

    OrderStatus status,
    CustomerView customer,
    BigDecimal total
) {}
~~~

Controller cần trả đúng kiểu response đã khai báo:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    public OrderView getOrder(@PathVariable Long id) {
        return orderService.getView(id);
    }
}
~~~

Tên import và phần khai báo service được lược bỏ để tập trung vào mapping. Trong dự án thực tế, bổ sung constructor injection và triển khai service theo cấu trúc sẵn có.

**@JsonProperty** điều khiển tên thuộc tính JSON mà Jackson sử dụng. springdoc-openapi thường đọc các metadata Jackson để mô tả tên property tương ứng. Sau khi sửa, phải kiểm tra lại cả response runtime và **/v3/api-docs**; không giả định annotation đã được nhận diện nếu ứng dụng dùng serializer hoặc converter riêng.

Phân biệt các annotation quan trọng:

| Annotation | Tác dụng chính | Điều cần tránh |
| --- | --- | --- |
| @JsonProperty | Xác định tên hoặc quyền truy cập property JSON | Chỉ đổi tên field Java mà quên kiểm tra JSON thực tế |
| @JsonAlias | Chấp nhận thêm tên khi deserialize input | Nghĩ rằng alias sẽ trở thành tên field khi serialize output |
| @JsonNaming | Áp dụng naming strategy cho các property của kiểu dữ liệu | Cho rằng mọi ObjectMapper hoặc gateway đều dùng cùng strategy |
| @Schema | Bổ sung metadata cho schema OpenAPI | Dùng nó như cách thay đổi JSON runtime |
| @JsonFormat | Quy định định dạng JSON cho một số kiểu dữ liệu | Dùng thay cho mapping ngày tháng của query parameter |

Nếu response được tạo bởi custom serializer hoặc được gateway biến đổi mà springdoc không thể suy ra từ DTO, cần mô tả schema công khai rõ ràng. Có thể dùng **@ApiResponse**, **@Content**, **@Schema** hoặc **OpenApiCustomizer** để sửa phần tài liệu tương ứng. Các cấu hình này chỉ sửa mô tả OpenAPI; chúng không làm thay đổi payload runtime.

Ví dụ mô tả rõ schema response:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Thông tin đơn hàng",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = OrderView.class)
    )
)
@GetMapping("/{id}")
public OrderView getOrder(@PathVariable Long id) {
    return orderService.getView(id);
}
~~~

Đoạn annotation này hữu ích khi cần chỉ định schema cho operation. Nếu runtime trả về một cấu trúc khác **OrderView**, hãy tạo kiểu view phản ánh đúng payload hoặc mô tả một schema riêng. Không dùng **implementation** để che giấu khác biệt runtime mà client vẫn gặp phải.

## 5. Chẩn đoán sai vị trí parameter

Một lỗi mapping khác xuất hiện khi giá trị được truyền ở query string nhưng tài liệu mô tả nó như request body, hoặc ngược lại. Xem lại chữ ký controller trước khi thêm **@Parameter**.

Ví dụ endpoint lọc đơn hàng:

~~~java
@GetMapping
public List<OrderView> search(
    @RequestParam(required = false) OrderStatus status,
    @RequestParam(required = false) LocalDate from,
    @RequestParam(required = false) Integer page
) {
    return orderService.search(status, from, page);
}
~~~

Client phải gọi query string, ví dụ:

~~~http
GET /api/orders?status=PAID&from=2026-11-01&page=0
~~~

Trong OpenAPI, các tham số này nằm trong **parameters** với **in: query**. **LocalDate** thường được mô tả là **type: string**, **format: date**. Nếu tài liệu lại thể hiện một object request body, hãy kiểm tra annotation và chữ ký controller có bị thay đổi hay không.

Các vị trí mapping phổ biến:

| Spring annotation | Vị trí dữ liệu HTTP | OpenAPI tương ứng |
| --- | --- | --- |
| @PathVariable | Một đoạn trong URL path | parameters với in: path |
| @RequestParam | Query string | parameters với in: query |
| @RequestHeader | HTTP header | parameters với in: header |
| @CookieValue | Cookie | Parameter cookie hoặc mô tả bảo mật phù hợp |
| @RequestBody | JSON hoặc body theo media type | requestBody |
| @RequestPart | Một phần multipart | requestBody với multipart/form-data |
| @ModelAttribute | Dữ liệu form hoặc các request parameter được bind | Các parameter tương ứng, tùy kiểu và cách binding |

Với DTO query phẳng, **@ParameterObject** có thể giúp springdoc tách các property thành query parameter:

~~~java
public record OrderFilter(
    OrderStatus status,
    LocalDate from,
    Integer page
) {}

@GetMapping
public List<OrderView> search(@ParameterObject OrderFilter filter) {
    return orderService.search(filter);
}
~~~

Kiểm tra schema sinh ra để chắc chắn từng field nằm ở query parameter đúng tên và đúng kiểu. Không dùng **@ParameterObject** để biến một cấu trúc JSON lồng nhau thành request body; với object lồng nhau hoặc quy tắc query phức tạp, hãy thiết kế parameter rõ ràng và mô tả serialization của query theo nhu cầu client.

Với path parameter, OpenAPI yêu cầu **required: true**. Nếu **@PathVariable** không khớp tên placeholder trong **@GetMapping**, request có thể không được ánh xạ như dự định. So sánh trực tiếp path template, tên biến và operation trong tài liệu.

## 6. Kiểm tra request body, media type và kiểu lồng nhau

Nếu request JSON bị từ chối nhưng Swagger UI cho phép gửi một payload khác cấu trúc, hãy kiểm tra lần lượt:

1. Controller có **@RequestBody** trên đúng tham số không?
2. **Content-Type** của client có khớp media type mà endpoint hỗ trợ không?
3. Tên JSON property có được Jackson nhận diện không?
4. Kiểu token có đúng không, ví dụ số thay cho chuỗi, object thay cho array?
5. Bean Validation có từ chối giá trị sau khi deserialize không?
6. Schema request body có tham chiếu đúng DTO và đúng phiên bản schema không?

Ví dụ body:

~~~json
{
  "customer_id": 42,
  "items": [
    {
      "product_id": 9,
      "quantity": 2
    }
  ]
}
~~~

Schema tương ứng cần thể hiện **customer_id** là số nguyên, **items** là array và phần tử array là object có **product_id** cùng **quantity**. Nếu schema thể hiện **items** là string, kiểm tra generic type của collection, khai báo DTO và custom converter.

Với upload file, **@RequestPart** và **multipart/form-data** thường phù hợp hơn một DTO JSON thông thường. Mô tả từng part với media type và schema riêng. Nếu endpoint nhận JSON metadata cùng file, kiểm tra request thực tế có đúng boundary, tên part và Content-Type của từng part.

Không nhầm **@DateTimeFormat** với **@JsonFormat**. **@DateTimeFormat** thường áp dụng cho dữ liệu được Spring bind từ path hoặc query parameter; **@JsonFormat** áp dụng cho quá trình Jackson đọc hoặc ghi JSON. Nếu ngày tháng bị parse sai, xác định dữ liệu nằm ở query hay body trước khi chọn annotation.

## 7. Phân biệt required, nullable và validation

Ba khái niệm này có liên quan nhưng không đồng nghĩa:

- **required** trong schema object cho biết property phải xuất hiện trong object.
- **nullable** hoặc cấu trúc schema cho phép null cho biết property có thể xuất hiện với giá trị null.
- Bean Validation như **@NotNull**, **@NotBlank**, **@Positive** quy định giá trị hợp lệ tại runtime khi validation được kích hoạt.

Ví dụ, property có thể bắt buộc xuất hiện nhưng giá trị được phép null. Ngược lại, property không bắt buộc xuất hiện nhưng nếu xuất hiện thì phải có giá trị hợp lệ. Hãy mô tả hai khía cạnh này riêng biệt.

Ví dụ DTO:

~~~java
public record CreateOrderRequest(
    @NotNull
    @Positive
    Long customerId,

    @NotBlank
    String reference,

    String note
) {}
~~~

Với DTO này, **customerId** và **reference** có ràng buộc validation. **note** không có ràng buộc tương tự. Tuy nhiên, schema được sinh còn phụ thuộc cấu hình Bean Validation, annotation trên property, kiểu dữ liệu và phiên bản OpenAPI. Hãy đọc **/v3/api-docs** để xác nhận kết quả thay vì suy ra hoàn toàn từ source code.

OpenAPI 3.0 và 3.1 biểu diễn null khác nhau. OpenAPI 3.0 thường dùng **nullable: true**; OpenAPI 3.1 dựa trên JSON Schema và có thể biểu diễn null trong type hoặc composition schema. Không sao chép cú pháp của một phiên bản vào tài liệu đang dùng phiên bản khác.

Các annotation **@Schema(requiredMode = Schema.RequiredMode.REQUIRED)**, **@Schema(nullable = true)**, **@NotNull** và **@NotBlank** phục vụ các khía cạnh khác nhau. Dùng annotation schema để làm rõ hợp đồng khi cần, nhưng vẫn kiểm tra validation runtime. Nếu API thực sự cho phép bỏ field, đừng đánh dấu required chỉ để Swagger UI hiển thị dấu sao.

Đối với enum, so sánh giá trị thực tế trong JSON với danh sách enum của schema. Nếu serializer dùng **toString()**, **@JsonValue** hoặc custom serializer để phát ra mã khác tên enum Java, cần mô tả chính xác tập giá trị client nhận được. Không giả định enum luôn được serialize bằng tên hằng Java.

## 8. Kiểm tra generic response, wrapper và schema tham chiếu

Một lỗi thường gặp là controller trả response wrapper nhưng OpenAPI chỉ mô tả kiểu raw hoặc không xác định được kiểu dữ liệu bên trong.

Ví dụ kiểu response rõ ràng:

~~~java
public record ApiEnvelope<T>(
    String code,
    String message,
    T data
) {}

@GetMapping("/{id}")
public ApiEnvelope<OrderView> getOrder(@PathVariable Long id) {
    return new ApiEnvelope<>("OK", "Success", orderService.getView(id));
}
~~~

Giữ generic type cụ thể tại chữ ký controller giúp công cụ phân tích kiểu có đủ thông tin để suy ra schema. Nếu dùng raw type như **ApiEnvelope**, trường **data** có thể không mang schema cụ thể. Cũng cần kiểm tra kiểu trả về thực tế khi dùng **ResponseEntity**, interface, base class, projection hoặc nhiều nhánh response.

Nếu response phụ thuộc vào subtype, kiểm tra **oneOf**, **anyOf**, **allOf** và discriminator. Một schema có **oneOf** cần chỉ ra các lựa chọn hợp lệ; nếu client không thể phân biệt subtype, xem xét discriminator property và giá trị mapping. Đừng dùng **allOf** chỉ để ghép các ví dụ JSON mà không có quan hệ kế thừa hoặc cấu trúc phù hợp.

Khi schema tham chiếu qua **$ref**, lần theo ref đến **components.schemas**. Kiểm tra schema gốc, schema lồng nhau và mọi composition. Nếu một property không xuất hiện như mong đợi, nó có thể đang nằm trong schema được tham chiếu hoặc bị loại bởi cấu hình access mode.

**readOnly** và **writeOnly** cũng ảnh hưởng cách hiểu schema. Một field chỉ đọc trong response có thể không xuất hiện trong request; một field chỉ ghi có thể không xuất hiện trong response. Nếu cùng DTO được dùng cho cả hai chiều, cân nhắc tạo request DTO và response DTO riêng để hợp đồng rõ ràng hơn.

## 9. Xác định lỗi ở springdoc hay ở ứng dụng

Sau khi có dữ liệu runtime và OpenAPI JSON, phân loại lỗi theo bằng chứng:

| Bằng chứng | Vị trí cần kiểm tra trước |
| --- | --- |
| Request trả 404 hoặc 405 | @RequestMapping, path, HTTP method, context path, gateway route |
| Request trả 400 khi parse body | Jackson deserialization, Content-Type, DTO và converter |
| Request trả 400 với lỗi validation | Bean Validation, nhóm validation và thông báo lỗi |
| Runtime JSON đúng nhưng schema property sai | Jackson metadata, kiểu controller, custom serializer, model converter |
| Schema đúng nhưng UI hiển thị khác | URL OpenAPI UI đang tải, cache trình duyệt, config URL hoặc nhiều group |
| Ứng dụng trả đúng nhưng URL công khai sai | Gateway, proxy, response transformation hoặc cache |
| Schema thiếu operation hoặc parameter | Controller scan, annotation mapping, group/package/path filter |
| Schema response dùng kiểu raw | Generic type bị mất, raw wrapper hoặc kiểu trả về không cụ thể |

Để biết Swagger UI đang đọc tài liệu nào, mở Network và tìm request swagger-config. Đọc URL hoặc danh sách URL trong response, sau đó mở đúng URL OpenAPI JSON. Ứng dụng có thể xuất nhiều document group; việc kiểm tra nhầm group sẽ dẫn đến kết luận rằng operation bị thiếu hoặc schema cũ.

Nếu **/v3/api-docs** thay đổi sau khi restart nhưng trình duyệt vẫn hiển thị schema cũ, kiểm tra cache của browser, reverse proxy và CDN. Nếu nhiều instance chạy phiên bản khác nhau, gửi request nhiều lần qua load balancer để xem các instance có trả cùng một hợp đồng không.

## 10. Sửa tài liệu bằng annotation hay customizer?

Chọn cách sửa theo nguồn gây ra khác biệt:

| Nguyên nhân | Cách sửa ưu tiên |
| --- | --- |
| JSON runtime có tên field sai | Sửa DTO hoặc Jackson mapping |
| Controller ánh xạ sai vị trí parameter | Sửa @PathVariable, @RequestParam, @RequestBody hoặc @RequestPart |
| Schema không biết generic type | Khai báo kiểu trả về cụ thể |
| Required/format/description thiếu | Bổ sung Bean Validation hoặc @Schema phù hợp |
| Serializer tùy chỉnh không thể suy ra schema | Dùng schema chuyên biệt hoặc ModelConverter |
| Gateway biến đổi payload công khai | Mô tả hợp đồng công khai bằng schema phù hợp và kiểm tra transformation |
| Cần sửa metadata ở một group hoặc operation | Dùng OpenApiCustomizer hoặc GroupedOpenApi phù hợp |

Không dùng **OpenApiCustomizer** để sửa mọi schema nếu nguyên nhân là DTO hoặc runtime serializer. Một customizer chỉ thay đổi tài liệu sinh ra. Nếu client vẫn nhận payload cũ, tài liệu và ứng dụng sẽ tiếp tục bất nhất.

Khi dùng customizer, giới hạn phạm vi thay đổi theo path, method hoặc group cụ thể. Tránh thay toàn bộ **components.schemas** nếu nhiều operation đang tham chiếu cùng schema. Sau khi sửa, kiểm tra các operation khác dùng chung component để tránh làm sai hợp đồng ở nơi khác.

## 11. Xác minh bằng kiểm thử runtime và hợp đồng

Một lần sửa cần có hai nhóm kiểm tra độc lập.

**Kiểm tra runtime**

- Gửi request hợp lệ và kiểm tra status code, Content-Type, tên property, kiểu dữ liệu và cấu trúc lồng nhau.
- Gửi request thiếu field bắt buộc, field sai kiểu hoặc enum không hợp lệ; xác nhận lỗi validation/parse theo thiết kế API.
- Kiểm tra query parameter, path variable và header bằng URL thực tế.
- Nếu có proxy, kiểm tra response qua cả địa chỉ nội bộ và địa chỉ công khai.

**Kiểm tra OpenAPI**

- Gọi đúng endpoint docs hoặc group URL mà Swagger UI sử dụng.
- Xác nhận path, method, parameter location, requestBody và response code.
- Theo $ref để xác nhận property, type, format, required, nullable và enum.
- Xác nhận schema không bị trùng hoặc bị thay đổi ngoài operation dự định.
- Kiểm tra document có thể được parse như JSON và được validator OpenAPI phù hợp chấp nhận.

Ví dụ kiểm thử với MockMvc có thể xác nhận response runtime:

~~~java
mockMvc.perform(get("/api/orders/42")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.order_id").value(42))
    .andExpect(jsonPath("$.created_at").exists())
    .andExpect(jsonPath("$.customer.full_name").value("Nguyen An"));
~~~

Kiểm tra OpenAPI bằng request riêng:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.paths['/api/orders/{id}'].get").exists())
    .andExpect(jsonPath("$.components.schemas.OrderView").exists());
~~~

Các assertion trên là ví dụ định hướng. Điều chỉnh URL, tên schema và JSONPath theo cấu trúc tài liệu thực tế. Nếu component được đặt tên khác hoặc schema được inline, kiểm tra nội dung OpenAPI JSON trước khi cố định assertion.

Khi dự án có contract test, có thể lưu một snapshot hoặc so sánh semantic OpenAPI giữa hai phiên bản. Review diff để nhận diện thay đổi breaking như đổi tên property, thay type, xóa response code, đổi required hoặc thu hẹp enum. Không xem mọi thay đổi snapshot là lỗi; cần phân biệt thay đổi có chủ đích với regression.

## 12. Bài tập chẩn đoán tổng hợp

Thực hiện bài tập theo trình tự sau trên một ứng dụng Spring Boot có springdoc-openapi:

1. Chọn một operation GET có path variable và response DTO lồng nhau.
2. Gọi endpoint bằng HTTP client và lưu JSON response thực tế.
3. Gọi swagger-config để xác định OpenAPI document đang được Swagger UI sử dụng.
4. Tìm path và method trong OpenAPI JSON; lần theo $ref đến schema response.
5. Ghi ra mọi khác biệt về property name, type, format, required, nullable và cấu trúc lồng nhau.
6. Kiểm tra chữ ký controller, DTO, Jackson annotations, ObjectMapper, validation và gateway transformation.
7. Chọn đúng lớp sửa: mapping runtime, kiểu dữ liệu, validation hoặc metadata OpenAPI.
8. Gửi lại cùng request, đọc lại OpenAPI JSON và so sánh hai kết quả.
9. Thử một request không hợp lệ để xác nhận validation và response lỗi vẫn được mô tả đúng.
10. Kiểm tra operation hoặc group khác có dùng chung schema để bảo đảm thay đổi không gây tác dụng phụ.

Hoàn thành bài tập khi có thể giải thích bằng bằng chứng: request nào được gửi, controller nào nhận request, Jackson tạo JSON ra sao, schema nào được springdoc sinh ra, điểm nào không khớp và thay đổi nào đã sửa nguyên nhân. Lưu lại request mẫu, response thực tế, phần schema liên quan và kết quả kiểm thử để lần nâng cấp sau có thể phát hiện hợp đồng bị lệch.
