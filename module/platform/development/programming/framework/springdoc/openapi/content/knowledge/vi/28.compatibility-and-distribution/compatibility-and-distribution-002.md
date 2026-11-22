# Đổi tên, bỏ hoặc thêm thuộc tính bắt buộc

Thay đổi một thuộc tính trong OpenAPI có thể ảnh hưởng trực tiếp tới client đang gửi request hoặc đọc response. Ba thao tác thường gặp là đổi tên property, loại bỏ property và thay đổi danh sách property bắt buộc. Chúng có vẻ nhỏ trong DTO Java, nhưng có thể làm hỏng quá trình deserialize, validation, sinh client SDK hoặc kiểm thử hợp đồng.

Để đánh giá đúng mức độ tương thích, cần xác định property nằm ở phía request hay response, ai là bên thay đổi và client/server cũ sẽ tương tác với phiên bản mới theo chiều nào. Thêm một trường tùy chọn vào response thường dễ tương thích với client cũ, nhưng thêm trường bắt buộc vào request có thể khiến mọi client chưa gửi trường đó bị từ chối. Đổi tên về bản chất là bỏ tên cũ và thêm tên mới, nên thường cần một giai đoạn chuyển tiếp.

Bài học sử dụng OpenAPI Schema Object và ví dụ Spring Boot để xây dựng cách đánh giá thay đổi. Mục tiêu là giúp nhóm phát hành API có kế hoạch migration rõ ràng, kiểm tra được bằng contract test và tránh làm hỏng client đang hoạt động.

## 1. Thuộc tính trong hợp đồng API là gì?

Trong một JSON object, property là một cặp tên và giá trị. Ví dụ:

~~~json
{
  "id": "ORD-1001",
  "customerName": "An",
  "note": "Giao giờ hành chính"
}
~~~

Object này có ba property: id, customerName và note. OpenAPI mô tả chúng trong Schema Object:

~~~yaml
type: object
properties:
  id:
    type: string
  customerName:
    type: string
  note:
    type: string
~~~

Schema mô tả những property được phép hoặc được kỳ vọng trong payload. Danh sách required ở cấp object xác định property nào phải xuất hiện. Nếu một property không nằm trong required, JSON Schema mặc định xem nó là tùy chọn.

Thay đổi property có thể tác động tới:

- Request body mà client gửi tới server.
- Response body mà server trả về client.
- Parameter dạng object, ví dụ query parameter được gom bằng Parameter Object.
- Schema dùng chung được tham chiếu từ nhiều operation.
- Model được sinh tự động trong Java, TypeScript, Kotlin hoặc ngôn ngữ khác.
- Consumer contract và các quy tắc validation ở runtime.

Vì vậy, trước khi sửa DTO hoặc annotation, cần xác định tất cả operation sử dụng schema đó.

## 2. Phân biệt property bị thiếu, null và có giá trị

Ba trạng thái này không giống nhau:

~~~json
{}
~~~

Property không xuất hiện trong object.

~~~json
{
  "middleName": null
}
~~~

Property xuất hiện nhưng giá trị là null.

~~~json
{
  "middleName": "Minh"
}
~~~

Property xuất hiện với một giá trị cụ thể.

Trong JSON Schema, required kiểm tra sự hiện diện của tên property. Nó không tự cấm giá trị null. Muốn cấm null, schema của property phải không chấp nhận kiểu null.

Ví dụ OpenAPI 3.1, property bắt buộc nhưng không được null:

~~~yaml
type: object
properties:
  customerId:
    type: string
required:
  - customerId
~~~

Ví dụ property bắt buộc và cho phép null:

~~~yaml
type: object
properties:
  middleName:
    type:
      - string
      - "null"
required:
  - middleName
~~~

Ví dụ property tùy chọn nhưng nếu xuất hiện thì không được null:

~~~yaml
type: object
properties:
  note:
    type: string
~~~

Trong OpenAPI 3.0, nullable thường được biểu diễn bằng nullable: true kết hợp với type. Trong OpenAPI 3.1, dùng mô hình JSON Schema, chẳng hạn type gồm string và null.

Không suy ra rằng property tùy chọn đồng nghĩa với nullable. Cũng không suy ra rằng property required luôn phải có giá trị khác null.

## 3. required được khai báo ở cấp object

Ví dụ:

~~~yaml
CreateOrder:
  type: object
  properties:
    customerId:
      type: string
    note:
      type: string
    priority:
      type: integer
  required:
    - customerId
~~~

Trong schema này:

- customerId phải xuất hiện.
- note có thể không xuất hiện.
- priority có thể không xuất hiện.

Để thay đổi note thành bắt buộc, thêm tên note vào danh sách required:

~~~yaml
required:
  - customerId
  - note
~~~

Không đặt required: true bên trong schema của từng property. required là một mảng tên property thuộc schema object cha.

Một property có default cũng không tự trở thành required. default mô tả giá trị mặc định, không thay đổi quy tắc hiện diện của property và không bảo đảm server hoặc client tự điền giá trị đó.

## 4. Đánh giá tương thích theo hướng request và response

Request và response có hướng dữ liệu ngược nhau:

~~~text
Client  ---- request ---->  API server
Client  <--- response ---  API server
~~~

Khi thay đổi request schema, cần hỏi client cũ gửi payload như thế nào tới server mới. Khi thay đổi response schema, cần hỏi client cũ xử lý response mới ra sao.

| Thay đổi | Request: client gửi tới server | Response: server gửi tới client |
|---|---|---|
| Thêm property tùy chọn | Client cũ không gửi trường mới thường vẫn hoạt động | Client cũ thường có thể bỏ qua trường mới |
| Thêm property bắt buộc | Có thể làm server mới từ chối payload của client cũ | Server mới cam kết luôn gửi trường; client cũ có thể bỏ qua nhưng validator nghiêm ngặt có thể cần cập nhật |
| Bỏ property | Client cũ còn gửi trường đã bỏ có thể bị từ chối hoặc mất tác dụng | Client cũ đọc trường đã bị bỏ có thể lỗi hoặc mất dữ liệu |
| Tùy chọn thành bắt buộc | Breaking change với client chưa gửi trường | Server cam kết mạnh hơn; thường là thay đổi nới lỏng với consumer, nhưng cần kiểm tra validator/codegen |
| Bắt buộc thành tùy chọn | Server chấp nhận thêm payload thiếu trường, thường tương thích với client | Breaking change vì client không còn được bảo đảm luôn nhận trường |
| Đổi tên | Client cũ gửi tên cũ; server mới phải hỗ trợ chuyển tiếp | Client cũ đọc tên cũ; server mới cần tiếp tục phát tên cũ trong giai đoạn migration |

Đây là đánh giá ở mức hợp đồng. Tương thích thực tế còn phụ thuộc cách serializer, deserializer, validator, gateway và client SDK xử lý property không biết hoặc bị thiếu.

## 5. Phân biệt backward compatibility và forward compatibility

Hai khái niệm thường bị nhầm:

- **Backward compatibility:** client đã tồn tại tiếp tục hoạt động với server mới.
- **Forward compatibility:** client mới có thể hoạt động với server cũ.

Ví dụ thêm property optional vào request schema:

- Client cũ không gửi property mới. Server mới vẫn chấp nhận payload cũ nếu property thật sự optional.
- Client mới gửi property mới tới server cũ. Server cũ có thể bỏ qua hoặc từ chối property không biết, tùy cấu hình Jackson và validation.

Do đó, một thay đổi có thể backward-compatible nhưng không forward-compatible.

Với response:

- Server mới thêm một property response. Client cũ thường tiếp tục hoạt động nếu bỏ qua field lạ.
- Client mới mong đợi property mới nhưng gọi server cũ. Server cũ không gửi property đó, khiến client mới có thể nhận null, lỗi validation hoặc lỗi xử lý.

Khi tuyên bố một thay đổi tương thích, cần nói rõ chiều tương thích và phạm vi consumer được hỗ trợ.

## 6. Thêm một property tùy chọn vào request

Giả sử API hiện nhận:

~~~yaml
CreateOrder:
  type: object
  properties:
    customerId:
      type: string
  required:
    - customerId
~~~

Phiên bản mới bổ sung note nhưng không đưa note vào required:

~~~yaml
CreateOrder:
  type: object
  properties:
    customerId:
      type: string
    note:
      type: string
      maxLength: 500
  required:
    - customerId
~~~

Client cũ vẫn gửi:

~~~json
{
  "customerId": "CUS-100"
}
~~~

Payload này vẫn hợp lệ theo schema mới. Client mới có thể gửi thêm note:

~~~json
{
  "customerId": "CUS-100",
  "note": "Gọi trước khi giao"
}
~~~

Đây thường là thay đổi backward-compatible ở phía provider. Tuy nhiên, cần kiểm tra server cũ có chấp nhận trường mới nếu client mới phải gọi ngược về server cũ hay không.

Nếu DTO dùng Jackson với cấu hình từ chối unknown properties, client mới gửi note tới server cũ có thể nhận lỗi deserialize. Vì vậy, không nên khẳng định thêm optional request property tương thích hai chiều nếu chưa kiểm tra hành vi runtime.

## 7. Thêm một property bắt buộc vào request

Giả sử request cũ chỉ yêu cầu customerId. Phiên bản mới thêm channel và bắt buộc:

~~~yaml
CreateOrder:
  type: object
  properties:
    customerId:
      type: string
    channel:
      type: string
      enum:
        - web
        - mobile
        - partner
  required:
    - customerId
    - channel
~~~

Client cũ vẫn gửi:

~~~json
{
  "customerId": "CUS-100"
}
~~~

Payload này không còn hợp lệ vì thiếu channel. Server có thể trả 400 sau khi validation thất bại.

Đây là breaking change đối với client cũ. Chỉ thêm trường vào DTO và đánh dấu required trong OpenAPI có thể làm hợp đồng thay đổi ngay cả khi code Java vẫn biên dịch thành công.

Nếu server có thể tự xác định channel từ thông tin xác thực hoặc nguồn khác, cân nhắc giữ property tùy chọn và áp dụng default ở tầng nghiệp vụ. Nếu channel thực sự bắt buộc từ phía client, cần có giai đoạn migration hoặc version API mới.

## 8. Bỏ một property khỏi request

Giả sử request trước đây nhận legacyCode:

~~~yaml
CreateOrder:
  type: object
  properties:
    customerId:
      type: string
    legacyCode:
      type: string
~~~

Khi xóa legacyCode khỏi schema, client cũ vẫn có thể gửi:

~~~json
{
  "customerId": "CUS-100",
  "legacyCode": "OLD-77"
}
~~~

Hành vi phụ thuộc cấu hình:

- Nếu Jackson bỏ qua unknown property, request có thể vẫn được xử lý nhưng legacyCode mất tác dụng.
- Nếu Jackson từ chối unknown property, request có thể bị lỗi deserialize.
- Nếu server còn dùng legacyCode để quyết định nghiệp vụ, bỏ trường khỏi DTO có thể làm thay đổi hành vi.

Do đó, bỏ property khỏi request không luôn luôn an toàn chỉ vì client cũ có thể gửi thêm dữ liệu. Phải kiểm tra unknown-property policy và ý nghĩa nghiệp vụ của trường.

Nếu property đã lỗi thời, đánh dấu deprecated trong schema, ghi hướng dẫn thay thế và tiếp tục chấp nhận nó trong một khoảng thời gian trước khi loại bỏ.

## 9. Bỏ một property khỏi response

Giả sử response cũ:

~~~yaml
Order:
  type: object
  properties:
    id:
      type: string
    total:
      type: number
    customerName:
      type: string
~~~

Client có thể đọc customerName để hiển thị đơn hàng. Nếu server bỏ property này, client cũ có thể:

- Hiển thị thông tin trống.
- Gặp null khi truy cập model được deserialize.
- Lỗi khi code giả định giá trị luôn tồn tại.
- Không còn thực hiện được chức năng phụ thuộc customerName.

Đây thường là breaking change đối với consumer, kể cả khi customerName không nằm trong required của response schema. Optional có nghĩa server có thể không gửi trường, nhưng không có nghĩa client chắc chắn không sử dụng trường đó.

Với response đã công bố, hãy kiểm tra usage thực tế, consumer contract và chính sách hỗ trợ trước khi xóa. Nếu trường không còn cần thiết, đánh dấu deprecated trước rồi loại bỏ ở phiên bản có kế hoạch.

## 10. Thêm property tùy chọn vào response

Response mới có thể bổ sung:

~~~yaml
Order:
  type: object
  properties:
    id:
      type: string
    total:
      type: number
    estimatedDelivery:
      type:
        - string
        - "null"
      format: date
~~~

Client cũ nhận thêm estimatedDelivery nhưng không cần dùng nó. Với consumer bỏ qua field chưa biết, đây thường là thay đổi additive và backward-compatible.

Tuy nhiên, có những client được sinh từ schema đóng, validator bật additionalProperties: false hoặc deserializer cấu hình fail khi gặp property lạ. Các client này có thể từ chối response mới.

Khi API có nhiều consumer khác nhau, kiểm tra SDK được phát hành và contract test đại diện. Nếu cần hỗ trợ client strict, cân nhắc versioning hoặc cơ chế tương thích rõ ràng.

## 11. Thêm property bắt buộc vào response

Khi server bổ sung một property và bảo đảm luôn gửi nó:

~~~yaml
Order:
  type: object
  properties:
    id:
      type: string
    total:
      type: number
    currency:
      type: string
  required:
    - id
    - total
    - currency
~~~

Đối với client cũ, server mới gửi thêm currency. Consumer thường có thể bỏ qua field này, vì vậy thay đổi thường backward-compatible nếu client chấp nhận property chưa biết.

Ở chiều ngược lại, client mới được sinh từ schema mới có thể kỳ vọng currency luôn có mặt. Nếu client đó gọi server cũ chưa gửi currency, giả định này không còn đúng.

Ngoài ra, validator phía consumer có thể kiểm tra response cũ theo schema mới và báo thiếu currency. Cần phân biệt server mới thực hiện cam kết mạnh hơn với việc client mới có thể làm việc với server cũ.

## 12. Tùy chọn thành bắt buộc trong response

Đây là thay đổi tăng mức bảo đảm của server:

~~~yaml
type: object
properties:
  id:
    type: string
  trackingUrl:
    type: string
required:
  - id
  - trackingUrl
~~~

Nếu server mới thực sự luôn trả trackingUrl, client cũ vốn chấp nhận trường này có thể tiếp tục hoạt động. Tuy nhiên:

- Consumer contract cũ có thể cho phép field vắng mặt, nên không cần thay đổi.
- Consumer mới có thể dựa vào cam kết mới và không xử lý trường hợp thiếu.
- Server cũ vẫn có thể không gửi trackingUrl.
- Tool diff có thể phân loại đây là thay đổi schema đáng chú ý dù runtime server mới chỉ tăng guarantee.

Trong phát hành đa phiên bản, hãy xác định rõ liệu client mới có cần gọi các server cũ hay không. Nếu có, client vẫn cần fallback cho trường hợp thiếu cho đến khi mọi server cũ hết vòng đời hỗ trợ.

## 13. Bắt buộc thành tùy chọn trong response

Giả sử trước đây id luôn có:

~~~yaml
type: object
properties:
  id:
    type: string
required:
  - id
~~~

Phiên bản mới bỏ id khỏi required. Từ thời điểm đó, hợp đồng cho phép response không có id.

Client đã dựa vào cam kết id luôn xuất hiện có thể gặp lỗi khi server trả payload thiếu trường. Đây là breaking change về guarantee của response.

Nếu server vẫn luôn gửi id trên mọi response hiện tại, thay đổi có thể chưa gây lỗi ngay. Nhưng schema mới đã cho phép hành vi yếu hơn và consumer không còn được bảo đảm. Contract diff nên cảnh báo việc nới lỏng response guarantee.

Đừng chỉ kiểm tra payload mẫu hiện tại. Hợp đồng phải mô tả mọi response mà server được phép trả về trong tương lai.

## 14. Đổi tên property là bỏ tên cũ và thêm tên mới

Giả sử customerName được đổi thành customerDisplayName:

~~~yaml
properties:
  customerDisplayName:
    type: string
~~~

Đối với client cũ, customerName đã biến mất. Đối với client mới, customerDisplayName có thể không có trên server cũ. Đây là thay đổi không tương thích nếu thay thế trực tiếp.

Không nên xem đổi tên chỉ là refactor nội bộ. Tên JSON property là một phần của hợp đồng công khai. Dù Java field đổi tên nhưng Jackson vẫn serialize bằng tên cũ thì hợp đồng wire format chưa đổi; ngược lại, đổi @JsonProperty có thể thay đổi hợp đồng dù Java field không đổi.

Trước khi đổi tên, xác định:

- Tên JSON thực tế trước và sau thay đổi.
- Property xuất hiện trong request, response hay cả hai.
- Consumer nào đang gửi hoặc đọc tên cũ.
- Có thể hỗ trợ song song hai tên trong thời gian chuyển tiếp không.
- Có cần API version mới hay không.

## 15. Migration đổi tên property trong request

Một chiến lược chuyển tiếp có thể chia thành các giai đoạn:

**Giai đoạn 1: Chấp nhận cả tên cũ và tên mới.**

~~~json
{
  "customerName": "An",
  "customerDisplayName": "An"
}
~~~

Server nhận một trong hai tên. Nếu cả hai cùng xuất hiện, cần quy tắc rõ ràng: từ chối khi giá trị xung đột, hoặc xác định tên ưu tiên. Không để thứ tự deserialize ngẫu nhiên quyết định dữ liệu.

**Giai đoạn 2: Công bố tên mới và đánh dấu tên cũ deprecated.**

~~~yaml
properties:
  customerName:
    type: string
    deprecated: true
    description: Dùng customerDisplayName thay thế. Tên cũ dự kiến ngừng hỗ trợ ở API v2.
  customerDisplayName:
    type: string
~~~

Trong giai đoạn này, client mới chuyển sang gửi tên mới; server vẫn chấp nhận tên cũ.

**Giai đoạn 3: Theo dõi việc sử dụng tên cũ.**

Ghi nhận metric hoặc log an toàn để biết client nào còn gửi customerName. Tránh ghi dữ liệu cá nhân vào log chỉ để theo dõi tên property.

**Giai đoạn 4: Loại bỏ theo chính sách versioning.**

Sau thời gian thông báo và khi consumer đã chuyển đổi, loại bỏ tên cũ trong một phiên bản có kế hoạch. Nếu không thể xác định mọi consumer đã nâng cấp, giữ hỗ trợ cũ lâu hơn hoặc phát hành API version mới.

## 16. Migration đổi tên property trong response

Với response, server kiểm soát tên được serialize. Có thể phát đồng thời hai property trong giai đoạn chuyển tiếp:

~~~json
{
  "id": "ORD-1001",
  "customerName": "An",
  "customerDisplayName": "An"
}
~~~

OpenAPI có thể mô tả:

~~~yaml
properties:
  customerName:
    type: string
    deprecated: true
    description: Dùng customerDisplayName.
  customerDisplayName:
    type: string
required:
  - customerName
  - customerDisplayName
~~~

Không nhất thiết phải đánh dấu cả hai required. Nếu muốn duy trì bảo đảm cho client cũ, giữ customerName luôn xuất hiện trong response cho đến khi kết thúc thời gian migration. Tên mới có thể được thêm và đưa vào required sau khi server bảo đảm giá trị luôn có.

Khi xóa tên cũ, kiểm tra client telemetry, SDK downloads, consumer-driven contracts và chính sách hỗ trợ. Việc hai trường cùng chứa một giá trị cũng cần được duy trì nhất quán trong suốt giai đoạn chuyển tiếp.

## 17. Dùng oneOf hoặc anyOf khi chấp nhận một trong hai tên

Trong một số hợp đồng, có thể mô tả payload yêu cầu một trong hai property cũ hoặc mới:

~~~yaml
type: object
properties:
  customerName:
    type: string
  customerDisplayName:
    type: string
anyOf:
  - required:
      - customerName
  - required:
      - customerDisplayName
~~~

anyOf cho phép ít nhất một trong hai property xuất hiện. Nếu muốn chính xác một tên, có thể dùng oneOf, nhưng cần cân nhắc payload có cả hai trường: nó sẽ khớp cả hai nhánh đơn giản và bị từ chối.

Ví dụ trên chỉ mô tả sự hiện diện. Nếu cần cấm hai trường cùng lúc hoặc yêu cầu giá trị đồng nhất khi cả hai cùng xuất hiện, có thể cần schema điều kiện phức tạp hơn hoặc validation nghiệp vụ ở server.

OpenAPI Schema Object hỗ trợ composition, nhưng không phải mọi client generator đều biểu diễn các điều kiện này đẹp trong model code. Hãy kiểm tra codegen và runtime validation trước khi dùng làm chiến lược migration chính.

## 18. Đánh dấu property deprecated trong OpenAPI

Có thể đánh dấu property đã lỗi thời:

~~~yaml
properties:
  legacyStatus:
    type: string
    deprecated: true
    description: Trường này sẽ được thay thế bằng status ở API v2.
  status:
    type: string
~~~

deprecated là metadata giúp tài liệu và công cụ nhận biết property không nên dùng cho tích hợp mới. Nó không tự:

- Từ chối request chứa property.
- Ngừng serialize property trong response.
- Ghi cảnh báo runtime.
- Xóa property khỏi DTO.
- Chuyển dữ liệu sang property mới.

Server phải thực hiện hành vi migration trong code. OpenAPI chỉ công bố trạng thái và hướng dẫn cho consumer.

Nên ghi rõ tên thay thế, thời điểm dự kiến ngừng hỗ trợ, phiên bản bị ảnh hưởng và cách client chuyển đổi. Nếu chưa có ngày cụ thể, mô tả điều kiện loại bỏ thay vì hứa một mốc không chắc chắn.

## 19. Ánh xạ thay đổi vào DTO Spring Boot

Ví dụ DTO request:

~~~java
public class CreateOrderRequest {

    @NotBlank
    private String customerId;

    private String note;

    // getters and setters
}
~~~

Controller:

~~~java
@PostMapping("/orders")
public ResponseEntity<OrderResponse> createOrder(
        @Valid @RequestBody CreateOrderRequest request) {
    // xử lý nghiệp vụ
    return ResponseEntity.status(HttpStatus.CREATED).body(result);
}
~~~

@NotBlank mô tả constraint chuỗi không null, không rỗng và không chỉ chứa khoảng trắng khi Bean Validation được kích hoạt. @Valid trên request body yêu cầu Spring kích hoạt validation cho DTO trong luồng phù hợp.

Để bổ sung metadata OpenAPI tường minh, có thể dùng:

~~~java
@Schema(description = "Mã khách hàng", requiredMode = Schema.RequiredMode.REQUIRED)
@NotBlank
private String customerId;
~~~

Và với trường tùy chọn:

~~~java
@Schema(description = "Ghi chú giao hàng", requiredMode = Schema.RequiredMode.NOT_REQUIRED)
private String note;
~~~

Tên enum và API annotation cần khớp phiên bản swagger-annotations đang dùng. Hãy kiểm tra OpenAPI JSON được sinh ra thay vì giả định một annotation luôn tạo đúng required, nullable hoặc deprecated trong mọi cấu hình.

## 20. Bean Validation, Jackson và OpenAPI không phải một lớp

Ba cơ chế có vai trò khác nhau:

| Cơ chế | Vai trò |
|---|---|
| OpenAPI Schema | Mô tả hợp đồng cho client và công cụ |
| Bean Validation | Kiểm tra dữ liệu sau khi request được bind vào object |
| Jackson | Chuyển đổi JSON thành Java object và ngược lại |

Ví dụ:

- required trong OpenAPI mô tả property phải có mặt.
- @NotNull hoặc @NotBlank có thể kiểm tra giá trị sau khi deserialize.
- Jackson quyết định property JSON nào được bind, bỏ qua hoặc từ chối.

Với field Java kiểu primitive như int hoặc boolean, JSON thiếu property có thể tạo giá trị mặc định 0 hoặc false. @NotNull không thể phát hiện trường hợp đó vì primitive không nhận null. Nếu cần phân biệt thiếu với giá trị 0/false, dùng wrapper type, constructor binding hoặc cơ chế kiểm tra presence phù hợp.

Ngược lại, field kiểu String có thể thành null khi JSON không có property. @NotBlank sẽ phát hiện nếu validation được gọi. Nhưng nếu controller không dùng @Valid hoặc validation dependency không được cấu hình, constraint có thể không được thực thi.

Vì vậy, thay đổi OpenAPI và thay đổi runtime phải được kiểm tra riêng.

## 21. Unknown properties và khả năng tương thích Jackson

Khi client gửi một property mà DTO server không khai báo, Jackson có thể:

- Bỏ qua property không biết theo cấu hình mặc định thường gặp.
- Từ chối deserialize nếu bật chế độ fail on unknown properties.
- Xử lý khác khi dùng custom deserializer hoặc cấu hình ObjectMapper riêng.

Điều này đặc biệt quan trọng khi thêm property vào request schema. Client mới gửi property đó tới server cũ có thể thành công nếu server cũ bỏ qua, nhưng thất bại nếu server cũ từ chối.

Có thể cấu hình ở mức class:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public class CreateOrderRequest {
    private String customerId;
}
~~~

Annotation này cho phép bỏ qua property không được DTO ánh xạ. Đây là quyết định về hành vi runtime, không phải bằng chứng rằng mọi unknown property đều an toàn để bỏ qua. Nếu trường mới có ý nghĩa nghiệp vụ, server cũ bỏ qua nó có thể tạo kết quả khác với mong đợi của client.

Không bật chế độ bỏ qua unknown property một cách máy móc nếu API cần phát hiện lỗi đánh máy hoặc dữ liệu không hợp lệ. Hãy chọn chính sách có chủ đích và kiểm thử.

## 22. Required trong response và dữ liệu thực tế

Nếu OpenAPI đánh dấu response property là required, server phải bảo đảm property xuất hiện trong mọi response phù hợp với schema đó.

Ví dụ:

~~~yaml
OrderResponse:
  type: object
  properties:
    id:
      type: string
    total:
      type: number
  required:
    - id
    - total
~~~

Nếu Java DTO có total bằng null và Jackson cấu hình bỏ qua null property, response có thể không chứa total dù OpenAPI đánh dấu required. Khi đó hợp đồng và runtime không nhất quán.

Kiểm tra các yếu tố:

- Giá trị field có luôn được gán trước khi serialize không?
- Jackson có cấu hình NON_NULL hoặc NON_EMPTY làm bỏ property không?
- Custom serializer có đổi tên hoặc loại bỏ property không?
- Mapping entity sang DTO có bỏ sót field trong một số nhánh không?
- Error response có dùng schema khác không?

Đối với response, nên có integration test kiểm tra JSON thực tế, không chỉ kiểm tra annotation hoặc schema được sinh ra.

## 23. Thay đổi required trong schema dùng chung

Một schema trong components.schemas có thể được nhiều operation tham chiếu:

~~~yaml
components:
  schemas:
    Customer:
      type: object
      properties:
        id:
          type: string
        displayName:
          type: string
~~~

Nếu thêm displayName vào required, mọi operation dùng Customer đều nhận thay đổi đó. Điều này có thể ảnh hưởng cả request và response tùy vị trí tham chiếu.

Ví dụ Customer dùng trong:

- Request tạo đơn hàng.
- Response chi tiết đơn hàng.
- Response danh sách khách hàng.
- Nested schema của Order.

Một thay đổi required chung có thể tạo breaking change ở nhiều operation cùng lúc. Nếu request và response có nhu cầu khác nhau, cân nhắc tách schema:

~~~yaml
components:
  schemas:
    CustomerInput:
      type: object
      properties:
        displayName:
          type: string
      required:
        - displayName
    CustomerView:
      type: object
      properties:
        id:
          type: string
        displayName:
          type: string
      required:
        - id
        - displayName
~~~

Tách schema giúp hợp đồng thể hiện rõ dữ liệu client được gửi và dữ liệu server cam kết trả. Không nên tái sử dụng một schema chỉ để giảm số lượng class nếu ngữ nghĩa request/response khác nhau.

## 24. Contract test cho thay đổi property

Nên kiểm tra cả schema và payload thực tế:

| Trường hợp | Điều cần xác minh |
|---|---|
| Request cũ không có property mới | Server mới vẫn xử lý nếu trường mới optional |
| Request thiếu property vừa thành required | Server từ chối theo status/validation contract |
| Request gửi tên cũ trong giai đoạn migration | Server vẫn chấp nhận và ánh xạ đúng |
| Request gửi tên mới | Server xử lý đúng |
| Request gửi cả tên cũ và mới | Quy tắc xung đột được thực thi |
| Response mới có property mới | Giá trị và kiểu dữ liệu đúng |
| Response không có property đã cam kết required | Test thất bại |
| Response vẫn phát property deprecated | Tên cũ và mới nhất quán trong giai đoạn chuyển tiếp |

Với Spring MVC, có thể dùng MockMvc hoặc test qua HTTP thực. Với WebFlux, dùng WebTestClient. Test phải xác minh status, JSON path và nội dung response.

Ví dụ kiểm tra request cũ vẫn hợp lệ sau khi thêm property optional:

~~~java
mockMvc.perform(post("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "customerId": "CUS-100"
            }
            """))
    .andExpect(status().isCreated());
~~~

Ví dụ kiểm tra trường mới bắt buộc:

~~~java
mockMvc.perform(post("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "customerId": "CUS-100"
            }
            """))
    .andExpect(status().isBadRequest());
~~~

Các ví dụ cần được điều chỉnh theo response status và exception handler thực tế của ứng dụng.

## 25. Consumer-driven contract và kiểm tra client cũ

OpenAPI diff cho biết schema thay đổi, nhưng không phải lúc nào cũng biết client thực tế có phụ thuộc vào property hay không.

Consumer-driven contract test có thể ghi nhận kỳ vọng của từng consumer:

- Consumer A cần customerName trong response.
- Consumer B chỉ dùng id và total.
- Consumer C gửi legacyCode trong request.
- Consumer D đã chuyển sang customerDisplayName.

Khi đổi hoặc bỏ property, chạy provider verification với các contract đã đăng ký. Điều này giúp nhận diện consumer nào còn phụ thuộc tên cũ hoặc giả định required.

Nếu tổ chức có nhiều client SDK, cần kiểm thử ít nhất các phiên bản SDK còn được hỗ trợ. Một schema change có thể tương thích với client viết tay nhưng không tương thích với model được sinh từ OpenAPI Generator.

## 26. Kiểm tra breaking change trong CI

Pipeline có thể so sánh OpenAPI hiện tại với baseline đã phát hành:

~~~text
Generate OpenAPI from Spring Boot
          |
          v
Parse and validate current document
          |
          v
Compare with released baseline
          |
          v
Classify property changes
          |
          v
Run provider/consumer contract tests
          |
          v
Approve compatible change or require versioning
~~~

Các thay đổi cần được gắn nhãn:

- Property bị xóa.
- Property được thêm vào required.
- Property bị bỏ khỏi required.
- Property đổi type, format hoặc enum.
- Property đổi tên.
- Property nullable thành non-null hoặc ngược lại.
- Response field bị bỏ hoặc có thể vắng mặt.
- Request field mới được yêu cầu.

Diff tool có thể phân loại một thay đổi là breaking theo quy tắc chung. Nhóm vẫn cần đánh giá ngữ cảnh request/response và chiều tương thích. Không bỏ qua cảnh báo chỉ vì ứng dụng hiện tại vẫn trả payload mẫu thành công.

Baseline phải là tài liệu của release đã được công bố hoặc chấp nhận. Nếu dùng một file từ nhánh phát triển khác làm baseline, kết quả diff có thể không phản ánh hợp đồng mà consumer đang dùng.

## 27. Chiến lược versioning khi không thể duy trì tương thích

Nếu bắt buộc đổi tên, xóa property hoặc thêm request property required mà không thể hỗ trợ chuyển tiếp, cần có kế hoạch versioning.

Các lựa chọn:

- Tạo endpoint version mới, ví dụ /api/v2/orders.
- Dùng media type hoặc version header nếu tổ chức đã có quy ước rõ ràng.
- Duy trì v1 trong thời gian hỗ trợ và chuyển consumer sang v2.
- Công bố ngày kết thúc hỗ trợ v1 và cách migration.

Không nên thay đổi ngữ nghĩa của một property nhưng giữ nguyên API version mà không thông báo. Ví dụ trước đây amount là tổng tiền trước thuế, sau đó đổi thành tổng tiền sau thuế dù tên và type không đổi. Đây là thay đổi hợp đồng ngữ nghĩa dù schema diff có thể không phát hiện.

Versioning giúp phân tách hợp đồng, nhưng tăng chi phí vận hành vì phải duy trì nhiều phiên bản. Chỉ tạo version mới khi thay đổi thực sự không thể tương thích hoặc chính sách sản phẩm yêu cầu.

## 28. Quy trình migration an toàn

Khi cần thay đổi property trong API đã phát hành:

1. Xác định property nằm ở request, response hay cả hai.
2. Liệt kê operation và schema dùng property.
3. Xác định client/provider cần giữ tương thích theo chiều nào.
4. Kiểm tra usage telemetry và consumer contracts.
5. Thêm tên mới dưới dạng optional nếu có thể.
6. Tiếp tục chấp nhận hoặc phát tên cũ trong thời gian chuyển tiếp.
7. Đánh dấu property cũ deprecated và mô tả tên thay thế.
8. Triển khai runtime mapping, quy tắc xung đột và validation.
9. Cập nhật SDK, tài liệu và ví dụ cho consumer.
10. Chạy contract test với payload cũ và mới.
11. Theo dõi việc sử dụng tên cũ và trường hợp thiếu field.
12. Chỉ loại bỏ tên cũ hoặc thay đổi required sau khi đáp ứng chính sách hỗ trợ.
13. Nếu không thể đáp ứng, phát hành API version mới và duy trì version cũ theo thời hạn.

Trong mỗi giai đoạn, OpenAPI document phải mô tả đúng hành vi runtime hiện tại. Không công bố property đã required trước khi server thực sự kiểm tra nó; cũng không đánh dấu property deprecated nếu server đã ngừng hỗ trợ nhưng tài liệu vẫn hứa chấp nhận.

## 29. Các lỗi thường gặp

| Thay đổi | Hiểu nhầm | Hậu quả |
|---|---|---|
| Thêm property request | Cho rằng server cũ luôn bỏ qua field lạ | Client mới có thể bị server cũ từ chối |
| Thêm property required vào request | Xem như thay đổi additive | Client cũ thiếu trường bị 400 |
| Xóa property request | Cho rằng client gửi field lạ không ảnh hưởng | Server strict có thể từ chối; logic cũ có thể mất |
| Xóa property response | Cho rằng property optional nên không ai dùng | Client cũ mất dữ liệu hoặc lỗi |
| Đổi tên property | Chỉ đổi tên Java field | JSON contract có thể đổi ngoài ý muốn qua Jackson |
| required thành optional trong response | Cho rằng schema nới lỏng là an toàn | Client mất bảo đảm field luôn xuất hiện |
| optional thành required trong response | Cho rằng mọi client mới gọi server cũ sẽ ổn | Server cũ có thể không gửi field mới |
| required và nullable | Coi hai khái niệm giống nhau | Payload thiếu field và field null bị xử lý sai |
| Dùng default | Nghĩ server tự điền giá trị | Request thiếu field vẫn có thể không hợp lệ |
| Đánh dấu deprecated | Nghĩ server tự ngừng nhận hoặc trả field | Runtime tiếp tục hành xử như trước nếu code không đổi |
| Sửa schema dùng chung | Không rà soát mọi operation | Một thay đổi lan sang nhiều request/response |
| Chỉ chạy schema diff | Không test payload thực tế | Bỏ sót khác biệt Jackson, validation và consumer |

## 30. Ghi nhớ

- Đánh giá thay đổi property phải phân biệt request và response.
- required kiểm tra sự hiện diện; nullable kiểm tra giá trị null có được phép hay không.
- Property không nằm trong required mặc định là tùy chọn.
- Thêm optional request field thường giữ client cũ hoạt động với server mới, nhưng client mới gọi server cũ còn phụ thuộc unknown-property policy.
- Thêm optional response field thường tương thích với consumer bỏ qua field lạ.
- Thêm required request field là breaking change với client cũ chưa gửi trường.
- Bỏ response property có thể phá client đang đọc nó, kể cả khi property từng optional.
- Đổi tên tương đương bỏ tên cũ và thêm tên mới; nên có giai đoạn dual-read/dual-write hoặc version mới.
- deprecated chỉ là metadata tài liệu, không tự đổi hành vi runtime.
- OpenAPI, Bean Validation và Jackson phải được kiểm tra riêng và giữ nhất quán.
- Schema dùng chung có thể lan thay đổi tới nhiều operation; tách request/response schema khi ngữ nghĩa khác nhau.
- Dùng OpenAPI diff, integration test và consumer-driven contracts trước khi release.
- Khi không thể giữ tương thích, version API và cung cấp kế hoạch migration rõ ràng.

Để đổi tên, bỏ hoặc thêm thuộc tính bắt buộc an toàn, hãy xác định hướng dữ liệu và chiều tương thích trước. Giữ tên cũ trong giai đoạn chuyển tiếp, đánh dấu deprecated, kiểm tra hành vi Jackson/Bean Validation và xác minh bằng contract test với payload cũ lẫn mới. Nếu thay đổi làm client hiện tại không còn đáp ứng hợp đồng, hãy phát hành phiên bản API mới theo chính sách hỗ trợ đã công bố.
