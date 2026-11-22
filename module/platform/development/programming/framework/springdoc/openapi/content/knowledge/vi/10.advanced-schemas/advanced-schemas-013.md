# Kiểm tra schema đầu ra trước khi dùng bộ sinh mã phía gọi

springdoc-openapi có thể tạo đặc tả OpenAPI từ controller và DTO của Spring Boot. Đặc tả này thường được dùng làm đầu vào cho công cụ sinh client SDK, vì vậy chất lượng schema ảnh hưởng trực tiếp đến kiểu dữ liệu, chữ ký method và cách client gọi API được tạo ra.

Một trang Swagger UI hiển thị đẹp chưa chứng minh tài liệu đủ tốt cho code generation. Trước khi phát hành spec cho đội frontend, mobile hoặc đối tác, cần kiểm tra cấu trúc OpenAPI, tính nhất quán của schema, khả năng tương thích với generator đã chọn và khả năng biên dịch của mã client được sinh.

Bài này trình bày quy trình kiểm tra đầu ra tại /v3/api-docs, từ việc lưu spec, xác thực, rà soát các thành phần dễ gây lỗi, thử sinh client đến tích hợp kiểm tra vào CI.

## 1. Vì sao phải kiểm tra spec trước code generation?

Bộ sinh mã đọc OpenAPI và chuyển mô hình API thành các thành phần của ngôn ngữ đích: class, enum, method, parameter, request model, response model và cấu hình xác thực. Nếu spec thiếu hoặc mô tả sai, lỗi có thể xuất hiện trong mã client dù ứng dụng Spring Boot vẫn chạy bình thường.

Ví dụ:

- Một field thực tế có thể bị thiếu nhưng schema lại đánh dấu required, khiến client buộc phải truyền dữ liệu không cần thiết.
- Một field có thể nhận null nhưng schema mô tả như field luôn có giá trị, khiến client sinh kiểu không phù hợp.
- Một response dùng generic wrapper nhưng schema làm mất kiểu dữ liệu cụ thể, khiến client chỉ nhận được object chung.
- Hai operation có operationId giống nhau có thể tạo method trùng tên.
- Một oneOf thiếu discriminator hoặc có các nhánh khó phân biệt có thể khiến generator tạo model không dùng được.
- Một $ref sai hoặc trỏ tới schema không tồn tại có thể làm validator và generator dừng ngay.

Vì vậy, cần xem spec như một artifact được kiểm soát phiên bản. Chỉ chuyển cho consumer sau khi đã xác thực cấu trúc và thử với generator thực tế mà nhóm dự định sử dụng.

## 2. Xuất đặc tả từ springdoc-openapi

Trong cấu hình mặc định, springdoc cung cấp OpenAPI JSON tại:

~~~text
GET /v3/api-docs
~~~

Nếu ứng dụng chạy local tại cổng 8080, có thể tải tài liệu bằng curl:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Tải bản YAML:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs.yaml -o openapi.yaml
~~~

Nếu ứng dụng có context path hoặc đã tùy chỉnh springdoc.api-docs.path, hãy dùng URL thực tế. Khi chạy sau API gateway hoặc reverse proxy, cần xác minh request đang đi đến đúng ứng dụng và đúng môi trường.

Nên xuất spec từ một cấu hình môi trường xác định. Nếu server URL, group API, feature flag hoặc cấu hình bảo mật thay đổi theo profile, cùng một source code có thể tạo ra các tài liệu khác nhau. Hãy ghi nhận profile và phiên bản ứng dụng đã dùng để tạo artifact.

Với API chia nhóm bằng GroupedOpenApi, cần tải và kiểm tra từng tài liệu nhóm mà client sẽ tiêu thụ. Không giả định kiểm tra tài liệu mặc định tại /v3/api-docs cũng bao phủ tất cả group.

## 3. Kiểm tra cấu trúc và phiên bản OpenAPI

Mở đầu file JSON để xem trường openapi. Ví dụ:

~~~json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Shop API",
    "version": "v1"
  }
}
~~~

Trường openapi cho biết phiên bản đặc tả OpenAPI. Nó khác với phiên bản Spring Boot, springdoc-openapi hoặc phiên bản nghiệp vụ của API.

Cần kiểm tra:

- Tài liệu có trường openapi và info hợp lệ không?
- info.title và info.version có giá trị rõ ràng không?
- paths có phải object và có các operation dự kiến không?
- components có cấu trúc hợp lệ không?
- servers có URL đúng với môi trường consumer không?
- securitySchemes và security có mô tả cơ chế xác thực thực tế không?
- Các media type có đúng với request và response không?

Không nên chỉ nhìn vào con số phiên bản OpenAPI để kết luận generator hỗ trợ. Một generator có thể hỗ trợ OpenAPI 3.0 tốt hơn một số tính năng của 3.1, hoặc hỗ trợ 3.1 không đồng đều giữa các ngôn ngữ. Hãy kiểm tra tài liệu và thử nghiệm với đúng phiên bản generator sẽ dùng.

## 4. Xác thực spec trước khi sinh mã

Bước đầu tiên là chạy validator để phát hiện lỗi cú pháp, cấu trúc và tham chiếu không hợp lệ. Với OpenAPI Generator CLI, có thể dùng:

~~~bash
openapi-generator-cli validate -i openapi.json
~~~

Nếu dùng YAML:

~~~bash
openapi-generator-cli validate -i openapi.yaml
~~~

Validator giúp phát hiện những vấn đề như cấu trúc sai, trường không hợp lệ hoặc tham chiếu không giải quyết được. Nếu validator báo lỗi, cần sửa nguồn tạo spec hoặc cấu hình springdoc trước khi chạy code generation.

Có thể bổ sung công cụ lint để kiểm tra quy ước của tổ chức:

~~~bash
npx @stoplight/spectral-cli lint openapi.yaml --ruleset .spectral.yaml
~~~

Một ruleset có thể kiểm tra các quy tắc như:

- Mọi operation phải có summary và operationId.
- operationId phải duy nhất.
- Path phải tuân theo quy ước đặt tên.
- Response phải mô tả mã HTTP quan trọng.
- Schema public phải có description ở các field cần giải thích.
- Không dùng server URL trỏ tới localhost trong spec production.
- Security phải được khai báo đúng với chính sách API.

Validator kiểm tra tính hợp lệ của tài liệu; linter kiểm tra quy ước và chất lượng theo tiêu chuẩn nhóm. Hai công việc này bổ trợ cho nhau.

## 5. Kiểm tra operationId và tên method sinh ra

operationId là định danh của một operation trong OpenAPI. Nhiều generator dùng giá trị này để đặt tên method trong client SDK. Nếu operationId bị thiếu, trùng hoặc thay đổi không chủ ý, tên method sinh ra có thể không ổn định.

Có thể khai báo tường minh bằng @Operation:

~~~java
@GetMapping("/{orderId}")
@Operation(
    operationId = "getOrderById",
    summary = "Lấy đơn hàng theo mã"
)
public OrderResponse getOrder(
    @PathVariable String orderId
) {
    return orderService.getById(orderId);
}
~~~

Với operation khác:

~~~java
@PostMapping
@Operation(
    operationId = "createOrder",
    summary = "Tạo đơn hàng mới"
)
public OrderResponse createOrder(
    @RequestBody CreateOrderRequest request
) {
    return orderService.create(request);
}
~~~

Tên operationId nên:

- Duy nhất trong toàn tài liệu.
- Dễ đọc và biểu thị hành động cùng đối tượng.
- Ổn định giữa các lần phát hành nếu client đã sử dụng method đó.
- Không phụ thuộc vào tên class controller hoặc tên method nội bộ có thể đổi thường xuyên.

Một thay đổi operationId có thể khiến method trong SDK đổi tên dù URL và HTTP method không đổi. Vì vậy, coi operationId là một phần của hợp đồng public và kiểm tra diff trước khi phát hành.

## 6. Kiểm tra schema object và kiểu dữ liệu

Mỗi schema cần mô tả đúng kiểu dữ liệu mà API thực sự nhận hoặc trả về. Các kiểu phổ biến gồm:

| Java | Schema OpenAPI thường gặp | Điều cần kiểm tra |
|---|---|---|
| String | type: string | Độ dài, pattern, enum |
| Integer / int | type: integer | format int32 hoặc giới hạn số |
| Long | type: integer | format int64 |
| BigDecimal | type: number | Precision, scale và giới hạn |
| Boolean | type: boolean | Khả năng phân biệt thiếu và false |
| LocalDate | type: string, format: date | Định dạng ngày |
| Instant / OffsetDateTime | type: string, format: date-time | Offset và quy ước thời gian |
| UUID | type: string, format: uuid | Generator có hỗ trợ format |
| List<T> | type: array, items | Kiểu item cụ thể |
| Map<String, T> | object với additionalProperties | Kiểu value của map |

Không chỉ kiểm tra type. Một schema có type đúng nhưng thiếu format, enum hoặc giới hạn có thể tạo client không an toàn hoặc khó sử dụng.

Ví dụ:

~~~yaml
quantity:
  type: integer
  format: int32
  minimum: 1
  maximum: 100
~~~

Schema này mô tả quantity là số nguyên trong khoảng 1 đến 100. Nếu DTO Java dùng Integer nhưng runtime không có @Min và @Max, tài liệu có thể hứa nhiều hơn hành vi thực tế. Ngược lại, nếu backend thực thi giới hạn nhưng spec không công bố, client không thể biết trước giới hạn đó.

## 7. Kiểm tra required, nullable và default

Đây là nhóm lỗi thường gây ra khác biệt giữa kiểu dữ liệu Java và mã client.

- **required** cho biết property có bắt buộc xuất hiện trong object hay không.
- **nullable** hoặc kiểu null trong schema cho biết property có thể nhận null hay không, theo phiên bản OpenAPI.
- **default** mô tả giá trị mặc định trong schema; nó không tự động bảo đảm backend gán giá trị đó khi request thiếu field.

Ví dụ schema có field tùy chọn:

~~~yaml
type: object
required:
  - name
properties:
  name:
    type: string
  description:
    type: string
~~~

Trong ví dụ này, name bắt buộc có mặt; description không nằm trong danh sách required. Điều đó không tự khẳng định description có nhận null hay không.

OpenAPI 3.0 thường dùng nullable: true. OpenAPI 3.1 dựa trên JSON Schema và biểu diễn null qua type hoặc schema composition phù hợp. Hãy kiểm tra phiên bản đặc tả và cách generator diễn giải.

Trong Java, primitive như int và boolean không biểu diễn null. Nếu API cần phân biệt field không được gửi với giá trị 0 hoặc false, DTO request nên cân nhắc Integer hoặc Boolean kết hợp validation phù hợp.

Đặc biệt, hãy kiểm tra DTO dùng chung cho create và update. Hai operation có thể có yêu cầu required khác nhau. Nếu generator tạo một model chung nhưng hợp đồng của hai operation khác nhau, cân nhắc DTO riêng hoặc schema riêng cho từng operation.

## 8. Kiểm tra enum và khả năng mở rộng

Enum trong OpenAPI thường được chuyển thành enum trong client. Điều này giúp code an toàn kiểu nhưng có một rủi ro: server có thể bổ sung giá trị mới trong tương lai, trong khi client cũ chưa biết giá trị đó.

Ví dụ:

~~~yaml
status:
  type: string
  enum:
    - PENDING
    - CONFIRMED
    - PAID
    - CANCELLED
~~~

Cần xác định:

- Giá trị enum có ổn định và đúng chữ hoa/chữ thường không?
- Có giá trị nào bị thiếu so với backend không?
- Client cũ xử lý thế nào khi server trả giá trị mới?
- Generator có tùy chọn fallback cho enum chưa biết hay không?
- Có cần biểu diễn giá trị mở bằng string thay vì enum đóng trong client không?

Đối với request, enum đóng thường hữu ích vì server có thể từ chối giá trị không hợp lệ. Với response, cần cân nhắc khả năng mở rộng để client cũ không lỗi khi server thêm trạng thái mới.

Không thay đổi enum chỉ vì muốn đổi tên hiển thị. Giá trị enum là dữ liệu hợp đồng; nếu đổi từ PAID sang COMPLETED, cần đánh giá ảnh hưởng tới client và dữ liệu đã lưu.

## 9. Kiểm tra $ref, schema dùng chung và vòng tham chiếu

Mọi $ref nội bộ cần trỏ tới component tồn tại. Ví dụ:

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

Khi rà soát:

- Tên component có duy nhất không?
- $ref có đúng JSON Pointer không?
- Component được tham chiếu có tồn tại không?
- Generic wrapper có giữ kiểu dữ liệu cụ thể không?
- Có schema trùng tên do @Schema(name = ...) không?
- Có tham chiếu đệ quy không cần thiết không?

Tham chiếu đệ quy có thể hợp lệ trong OpenAPI, nhưng không phải generator nào cũng xử lý giống nhau. Một số generator có thể tạo model tham chiếu hai chiều hoặc gặp khó khăn khi serialize. Hãy thử đúng generator và ngôn ngữ đích, đặc biệt với các DTO có quan hệ hai chiều.

Không đưa entity persistence trực tiếp vào public API chỉ để tận dụng schema tự sinh. Entity thường có quan hệ lazy, vòng tham chiếu, field nội bộ hoặc cấu trúc không ổn định. DTO riêng giúp kiểm soát schema và client tốt hơn.

## 10. Kiểm tra allOf, oneOf, anyOf và discriminator

Schema composition là nguồn gây khác biệt giữa các generator.

- **allOf:** dữ liệu phải thỏa tất cả schema thành phần.
- **oneOf:** dữ liệu phải phù hợp đúng một schema trong danh sách.
- **anyOf:** dữ liệu phù hợp ít nhất một schema.
- **discriminator:** giúp xác định schema con dựa trên một property, thường dùng với mô hình đa hình.

Ví dụ:

~~~yaml
PaymentMethod:
  oneOf:
    - $ref: '#/components/schemas/CardPayment'
    - $ref: '#/components/schemas/BankTransfer'
  discriminator:
    propertyName: type
    mapping:
      CARD: '#/components/schemas/CardPayment'
      BANK_TRANSFER: '#/components/schemas/BankTransfer'
~~~

Nếu dùng oneOf, các nhánh nên có cách phân biệt rõ. Discriminator giúp client chọn kiểu cụ thể dựa trên property type. Cần bảo đảm property này tồn tại và giá trị mapping phù hợp với payload thực tế.

Không giả định tất cả generator đều tạo cùng một cấu trúc class cho allOf hoặc oneOf. Một generator có thể tạo interface và model con; generator khác có thể tạo wrapper hoặc cấu trúc khác. Hãy mở tài liệu cấu hình của generator và chạy thử một mẫu nhỏ trước khi quyết định thiết kế schema public.

## 11. Kiểm tra parameter và cách serialize

Parameter không chỉ có tên và kiểu. Với array hoặc object trong query string, cách serialize cũng ảnh hưởng client.

Ví dụ array parameter:

~~~yaml
parameters:
  - name: status
    in: query
    required: false
    schema:
      type: array
      items:
        type: string
        enum: [PENDING, PAID]
    style: form
    explode: true
~~~

Với explode: true, client có thể gửi nhiều key cùng tên:

~~~text
?status=PENDING&status=PAID
~~~

Nếu API mong đợi một dạng khác như status=PENDING,PAID, cần khai báo style/explode phù hợp và xác minh Spring MVC binding thực tế.

Kiểm tra các nhóm parameter:

- Path parameter phải có required: true.
- Query parameter có đúng tên và required không?
- Array/object parameter có style và explode đúng không?
- Header parameter có tên chính xác và có bị trùng với header do gateway quản lý không?
- Date, date-time, UUID và enum có được mô tả đúng không?
- Pageable có page, size và sort theo định dạng mà backend nhận không?

Nếu generator tạo client gửi query string khác cách Spring bind, hợp đồng có thể hợp lệ về cú pháp nhưng không tương thích về hành vi.

## 12. Kiểm tra request body, response và media type

Một endpoint cần mô tả rõ nội dung request và các phản hồi.

Với request body, kiểm tra:

- requestBody.required có đúng không?
- Media type có đúng như controller nhận không?
- Schema có đúng field, required, nullable và constraints không?
- Multipart/form-data có mô tả đúng từng phần không?
- File upload có schema và encoding phù hợp với phiên bản OpenAPI không?

Với response, kiểm tra:

- Có mô tả response thành công không?
- Các mã lỗi quan trọng như 400, 401, 403, 404, 409 hoặc 500 có cần công bố không?
- Schema response có đúng DTO public không?
- Response 204 có tránh khai báo content body không?
- Các media type và header có khớp runtime không?

Nếu generator chỉ nhìn thấy response 200 trong khi backend còn trả lỗi có cấu trúc, client SDK có thể không cung cấp kiểu lỗi hữu ích. Hãy mô tả response lỗi bằng @ApiResponse hoặc cơ chế tùy biến OpenAPI phù hợp.

## 13. Kiểm tra security và servers

Client SDK cần biết endpoint ở đâu và cách xác thực ra sao.

Kiểm tra servers:

~~~yaml
servers:
  - url: https://api.example.com/v1
    description: Production API
~~~

Không để localhost hoặc URL staging trong spec được phát hành cho đối tác production. Nếu có nhiều server, xác định generator và client có chọn đúng server mặc định hay không.

Kiểm tra securitySchemes và security requirement. Ví dụ bearer token:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

security:
  - bearerAuth: []
~~~

Nếu chỉ một số operation cần xác thực, có thể khai báo security ở cấp operation thay vì root. Hãy kiểm tra tài liệu được sinh có đúng với Spring Security và gateway thực tế hay không. OpenAPI security mô tả cơ chế gửi thông tin xác thực; nó không tự cấu hình authorization trên server.

## 14. Chạy thử generator đã chọn

Sau khi spec vượt qua validator, thử sinh client bằng đúng generator và phiên bản mà nhóm sẽ sử dụng.

Liệt kê generator được hỗ trợ:

~~~bash
openapi-generator-cli list
~~~

Xem các tùy chọn của generator:

~~~bash
openapi-generator-cli config-help -g java
~~~

Sinh client Java từ spec:

~~~bash
openapi-generator-cli generate \
  -i openapi.json \
  -g java \
  -o ./build/generated-client
~~~

Có thể thử generator cho TypeScript, Kotlin, Swift hoặc ngôn ngữ khác tùy nhóm client. Cấu hình phải được chốt theo generator cụ thể, chẳng hạn thư viện HTTP, cách biểu diễn date, enum, nullable, package name và kiểu dữ liệu bất đồng bộ.

Không dùng cờ bỏ qua validation để che lỗi spec. Nếu generator không hỗ trợ một tính năng OpenAPI, cần quyết định điều chỉnh schema, chọn generator khác hoặc ghi nhận giới hạn tương thích. Sau khi sinh mã, hãy biên dịch project được tạo và kiểm tra các operation, model và cấu hình auth quan trọng.

## 15. Pin phiên bản generator và cấu hình

Cùng một spec có thể tạo mã khác nhau khi đổi phiên bản generator hoặc config option. Để kết quả lặp lại được:

- Pin phiên bản OpenAPI Generator CLI hoặc Maven/Gradle plugin.
- Lưu config file và template tùy chỉnh trong repository.
- Ghi rõ generatorName và ngôn ngữ đích.
- Ghi lại các config option ảnh hưởng kiểu dữ liệu và thư viện HTTP.
- Không dùng nhãn latest hoặc version động trong pipeline.
- Cập nhật generator có chủ đích và xem diff mã được sinh.

Ví dụ cấu hình lệnh:

~~~bash
openapi-generator-cli generate \
  -i openapi.json \
  -g java \
  -o ./build/generated-client \
  --additional-properties=dateLibrary=java8
~~~

Các option cụ thể thay đổi theo generator và phiên bản. Trước khi dùng, kiểm tra:

~~~bash
openapi-generator-cli config-help -g java
~~~

Nếu nhóm dùng Maven plugin, hãy khai báo một version cố định trong pom.xml và lưu các configOptions cùng inputSpec. Không dựa vào version ngầm định của máy developer vì kết quả local và CI có thể khác nhau.

## 16. Biên dịch và kiểm thử client được sinh

Sinh mã thành công chỉ chứng minh generator đã tạo file. Nó chưa chứng minh client compile hoặc gọi đúng API.

Nên kiểm tra:

1. Build client project thành công.
2. Các model quan trọng được tạo với kiểu dữ liệu mong đợi.
3. Enum và nullable được biểu diễn phù hợp.
4. Method operation có tên ổn định và không bị trùng.
5. Client gửi đúng path, query, header và request body.
6. Authentication được gắn đúng vào request.
7. Response body được deserialize đúng DTO.
8. Lỗi HTTP có thể được đọc và xử lý theo contract.
9. Test tích hợp gọi được server test hoặc mock server theo spec.

Có thể viết smoke test cho một luồng quan trọng như tạo đơn hàng, truy vấn đơn hàng và xử lý response lỗi 400. Với API có nhiều operation, ưu tiên các luồng đại diện và các schema phức tạp như oneOf, generic wrapper, date-time và file upload.

Nếu client generator tạo mã biên dịch được nhưng serialize request sai, cần so sánh request thực tế trên wire với OpenAPI parameter serialization và media type. Đây là bước kiểm tra hành vi, không chỉ kiểm tra kiểu Java.

## 17. So sánh spec giữa các lần phát hành

Trước khi phát hành API mới, nên so sánh spec mới với bản đã công bố. Diff giúp phát hiện thay đổi có thể phá vỡ client:

- Xóa path hoặc HTTP method.
- Đổi operationId.
- Xóa hoặc đổi tên property.
- Chuyển field tùy chọn thành bắt buộc.
- Thu hẹp enum hoặc giới hạn dữ liệu.
- Đổi kiểu dữ liệu hoặc format.
- Thay đổi request body media type.
- Xóa response code hoặc thay đổi response schema.
- Thay đổi security requirement.
- Đổi server URL hoặc path prefix.

Không phải mọi thay đổi schema đều là breaking change. Thêm một field optional vào response thường ít rủi ro hơn việc thêm field required vào request. Tuy nhiên, client generator và ngôn ngữ đích có thể có hành vi riêng, vì vậy cần kiểm tra theo chính sách tương thích của nhóm.

Lưu bản spec đã phát hành hoặc commit snapshot vào repository. Khi thay đổi controller hoặc DTO, tạo spec mới và chạy công cụ diff/compatibility check. Nếu có breaking change, cần nâng phiên bản API hoặc có kế hoạch migration rõ ràng.

## 18. Tích hợp quy trình vào CI

Một pipeline cơ bản có thể thực hiện theo thứ tự:

~~~mermaid
flowchart TD
    A["Khởi động ứng dụng test"] --> B["Tải /v3/api-docs"]
    B --> C["Validate OpenAPI"]
    C --> D["Lint theo quy ước nhóm"]
    D --> E["So sánh với spec đã phát hành"]
    E --> F["Sinh client bằng generator đã pin version"]
    F --> G["Build client"]
    G --> H["Smoke test contract"]
    H --> I["Lưu spec và báo cáo"]
~~~

Ví dụ lệnh trong pipeline:

~~~bash
curl -fsS "$API_BASE_URL/v3/api-docs" -o openapi.json
openapi-generator-cli validate -i openapi.json
npx @stoplight/spectral-cli lint openapi.json --ruleset .spectral.yaml
openapi-generator-cli generate -i openapi.json -g java -o build/generated-client
~~~

Sau bước generate, pipeline cần chạy build của client. Tùy dự án, có thể lưu generated client như artifact hoặc chỉ dùng nó để kiểm tra tính tương thích.

Nếu spec được lấy từ ứng dụng đang chạy, bảo đảm ứng dụng test đã sẵn sàng trước khi curl. Không nên tạo spec từ một server có dữ liệu hoặc cấu hình ngẫu nhiên khiến kết quả thay đổi giữa các lần build. Hãy dùng profile và fixture ổn định.

## 19. Các lỗi thường gặp khi sinh client

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Validator từ chối spec | Cấu trúc sai, $ref không hợp lệ hoặc cú pháp OpenAPI không đúng |
| Generator không hiểu schema 3.1 | Generator hoặc phiên bản đang dùng chưa hỗ trợ đầy đủ tính năng được xuất |
| Method client bị trùng | operationId thiếu hoặc trùng |
| Nullable bị sinh thành kiểu non-null | required/nullable trong spec hoặc mapping của generator chưa đúng |
| Enum response làm client cũ lỗi | Server bổ sung giá trị enum mới nhưng client dùng enum đóng |
| allOf tạo model khó dùng | Generator diễn giải composition khác mong đợi |
| oneOf không deserialize đúng | Thiếu discriminator hoặc các nhánh không phân biệt được |
| Date/time sai múi giờ | Format hoặc quy ước timezone không rõ |
| Query array gửi sai định dạng | style/explode không khớp cách backend bind |
| Client gọi sai host | servers có URL hoặc server mặc định sai |
| Client không gửi bearer token | securitySchemes/security requirement thiếu hoặc sai |
| Build client thất bại sau khi cập nhật spec | Thay đổi schema, operationId hoặc generator config làm đổi mã được sinh |

Khi gặp lỗi, xác định lỗi thuộc lớp nào: spec không hợp lệ, generator không hỗ trợ, cấu hình generator sai, mã sinh ra không compile hay request runtime không tương thích. Phân loại đúng giúp sửa nguồn gây lỗi thay vì chỉnh tay file generated.

## 20. Checklist trước khi phát hành spec cho client

- [ ] Đã xuất spec từ đúng profile và đúng group API.
- [ ] openapi, info, paths, servers và components hợp lệ.
- [ ] Validator OpenAPI chạy thành công.
- [ ] Linter không còn lỗi theo quy ước bắt buộc.
- [ ] operationId đầy đủ, duy nhất và ổn định.
- [ ] Schema có type, format, required, nullable và enum chính xác.
- [ ] Các $ref đều trỏ đến component hợp lệ.
- [ ] allOf/oneOf/anyOf và discriminator được generator hỗ trợ.
- [ ] Parameter serialization khớp cách Spring MVC nhận request.
- [ ] Request body, response, media type và mã lỗi được mô tả đúng.
- [ ] Security scheme và servers đúng với môi trường consumer.
- [ ] Generator và config đã được pin version.
- [ ] Client được sinh và biên dịch thành công.
- [ ] Có smoke test cho các luồng và schema quan trọng.
- [ ] Spec mới đã được so sánh với bản phát hành trước.
- [ ] Artifact spec và báo cáo kiểm tra được lưu để truy vết.

## 21. Nguồn tra cứu

- [springdoc-openapi – tài liệu chính thức](https://springdoc.org/)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [OpenAPI Generator – Usage](https://openapi-generator.tech/docs/usage/)
- [OpenAPI Generator – Validators](https://openapi-generator.tech/docs/usage/#validate)
- [OpenAPI Generator – Configuration](https://openapi-generator.tech/docs/configuration/)
- [Spectral – OpenAPI linting](https://docs.stoplight.io/docs/spectral/)
- [Swagger – OpenAPI Specification overview](https://swagger.io/specification/)

Spec do springdoc-openapi sinh ra là đầu vào của các công cụ tiêu thụ API. Trước khi giao cho client generator, hãy xác thực cấu trúc, rà soát schema và operationId, thử sinh mã bằng đúng phiên bản generator, rồi biên dịch và kiểm tra request thực tế. Quy trình này giúp phát hiện sớm khác biệt giữa tài liệu và API đang chạy.
