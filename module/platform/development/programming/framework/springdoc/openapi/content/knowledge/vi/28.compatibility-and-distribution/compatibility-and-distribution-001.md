# Nhận diện thay đổi phá vỡ hợp đồng đối với bên sử dụng

Một thay đổi trong OpenAPI có thể làm provider vẫn chạy bình thường nhưng consumer cũ không còn gọi API hoặc đọc response đúng cách. Ví dụ, thêm một query parameter bắt buộc, xóa một response field, đổi kiểu dữ liệu hoặc yêu cầu scope mới đều có thể phá vỡ tích hợp đang hoạt động.

Để đánh giá đúng, cần nhìn thay đổi từ góc độ consumer: client gửi request theo hợp đồng cũ có còn được chấp nhận không, và client đọc response theo hợp đồng cũ có còn xử lý được không? Request schema và response schema có hướng tương thích khác nhau. Provider nên tiếp tục chấp nhận các request hợp lệ cũ; response mới nên tiếp tục nằm trong phạm vi mà consumer cũ có thể hiểu.

Bài này trình bày cách nhận diện breaking change trong path, method, parameter, request body, response, schema, security và metadata dùng để sinh SDK. Bài cũng hướng dẫn so sánh OpenAPI document với baseline đã phát hành, tích hợp kiểm tra vào CI và quản lý ngoại lệ khi cần thay đổi không tương thích.

## 1. Contract compatibility là gì?

OpenAPI mô tả hợp đồng giữa provider và consumer. Provider triển khai endpoint; consumer dùng hợp đồng để tạo request, parse response, sinh SDK hoặc kiểm thử tích hợp.

Một thay đổi tương thích ngược thường giữ cho consumer đã được xây dựng theo hợp đồng trước tiếp tục hoạt động mà không phải sửa code hoặc cấu hình. Một breaking change làm ít nhất một hành vi hợp lệ theo hợp đồng cũ không còn được hỗ trợ, hoặc làm consumer cũ không thể xử lý response mới.

Cần phân biệt ba khái niệm:

| Khái niệm | Câu hỏi |
|---|---|
| Backward compatibility | Consumer cũ có tiếp tục hoạt động với provider mới không? |
| Forward compatibility | Consumer mới có thể làm việc với provider cũ trong phạm vi nào? |
| Contract compatibility | Request/response thực tế có còn phù hợp với hợp đồng mà consumer dựa vào không? |

Trong phát triển API, đánh giá thường tập trung vào backward compatibility của provider: nâng cấp server nhưng không buộc tất cả consumer đang hoạt động phải nâng cấp đồng thời.

Không có một quy tắc duy nhất đúng cho mọi client. Client sinh từ OpenAPI, client viết thủ công, client strict schema validation và client bỏ qua field lạ có thể phản ứng khác nhau. Vì vậy, cần phân biệt thay đổi wire contract với thay đổi ảnh hưởng đến generated SDK hoặc quy ước sử dụng.

## 2. Đánh giá riêng request contract và response contract

Provider nhận request từ consumer và trả response cho consumer. Vì hướng dữ liệu khác nhau, cùng một loại thay đổi có thể có kết quả tương thích khác nhau.

| Vùng hợp đồng | Provider cần bảo đảm để giữ consumer cũ |
|---|---|
| Request | Tiếp tục chấp nhận các request hợp lệ theo schema cũ |
| Response | Tiếp tục trả dữ liệu mà consumer cũ có thể đọc và xử lý |
| Authentication | Credential và quyền cũ tiếp tục đủ dùng theo chính sách đã cam kết |
| Routing | Path, method và server URL cũ tiếp tục truy cập được |
| Serialization | Tên field, kiểu dữ liệu và media type cũ không thay đổi ngoài dự kiến |

Ví dụ:
- Thêm một giá trị được chấp nhận vào enum của request thường mở rộng những gì provider có thể nhận.
- Thêm một giá trị enum mới vào response làm mở rộng những gì provider có thể trả; consumer cũ có thể không biết giá trị đó.
- Thêm một request field optional thường không bắt buộc client cũ phải gửi.
- Xóa một response field mà client cũ đang đọc có thể làm client lỗi hoặc mất dữ liệu.

Không nên đánh giá compatibility chỉ bằng việc OpenAPI document vẫn hợp lệ hoặc server vẫn trả HTTP 200. Cần xem xét tập request và response có thể xảy ra trước và sau thay đổi.

## 3. Thay đổi path, HTTP method và operation

Các thay đổi này thường có tác động trực tiếp đến mọi consumer gọi endpoint:

| Thay đổi | Đánh giá thông thường | Lý do |
|---|---|---|
| Xóa path đang được công bố | Breaking | Consumer không còn endpoint cũ |
| Đổi path | Breaking | URL client gọi không còn khớp |
| Xóa HTTP method trên path | Breaking | Request method cũ không còn được hỗ trợ |
| Đổi method GET thành POST | Breaking | Client cũ gửi method khác với route mới |
| Thêm path/method mới | Thường không breaking | Consumer cũ không bắt buộc dùng operation mới |
| Đổi trailing slash hoặc path casing | Có thể breaking | Routing và proxy có thể phân biệt URL |
| Đổi server URL | Có thể breaking | Client có thể tiếp tục gọi host/base path cũ |

Ví dụ baseline:

~~~yaml
paths:
  /api/orders/{id}:
    get:
      operationId: getOrderById
      responses:
        "200":
          description: Order found
~~~

Phiên bản mới chuyển endpoint sang `/api/order/{id}`:

~~~yaml
paths:
  /api/order/{id}:
    get:
      operationId: getOrderById
      responses:
        "200":
          description: Order found
~~~

Dù response không đổi, client cũ vẫn gọi `/api/orders/{id}`. Đây là breaking change ở routing.

Cách chuyển đổi an toàn hơn là duy trì path cũ trong một khoảng thời gian, công bố path mới, đo mức sử dụng path cũ và chỉ gỡ bỏ sau thời hạn migration đã thông báo. Nếu cần version URL, giữ version cũ song song trong giai đoạn chuyển tiếp.

## 4. Thay đổi parameter

Parameter được xác định bởi tên, vị trí, kiểu dữ liệu, required, serialization và constraint. Đổi bất kỳ thuộc tính nào cũng có thể ảnh hưởng đến request mà consumer tạo.

### 4.1. Thêm parameter bắt buộc

Baseline:

~~~yaml
parameters:
  - name: id
    in: path
    required: true
    schema:
      type: string
~~~

Phiên bản mới thêm tenant header bắt buộc:

~~~yaml
parameters:
  - name: id
    in: path
    required: true
    schema:
      type: string
  - name: X-Tenant-Id
    in: header
    required: true
    schema:
      type: string
~~~

Client cũ không gửi `X-Tenant-Id`, nên request có thể bị từ chối. Đây là breaking change nếu provider trước đó chấp nhận request không có header này.

Nếu cần bổ sung tenant context, có thể triển khai cơ chế suy ra tenant từ credential hiện tại hoặc cho phép header optional trong giai đoạn chuyển tiếp. Chỉ chuyển thành required khi consumer đã gửi property và kế hoạch rollout cho phép.

### 4.2. Thay đổi tên, vị trí hoặc kiểu parameter

Các thay đổi sau thường phá vỡ request cũ:
- Đổi query parameter `page` thành `pageNumber`.
- Đổi header `X-Client-Id` thành `X-Partner-Id`.
- Chuyển parameter từ query sang header.
- Đổi kiểu `string` thành `integer`.
- Đổi tên placeholder từ `/orders/{id}` sang `/orders/{orderId}` thường không đổi URL wire thực tế, nhưng có thể đổi tên tham số trong generated SDK hoặc code consumer.
- Thay `style`, `explode` hoặc cách encode array/object khiến request được serialize khác.

Để chuyển tên parameter, có thể tạm chấp nhận cả tên cũ và tên mới. Tuy nhiên, nếu hai giá trị cùng được gửi, provider cần quy định rõ precedence hoặc trả lỗi để tránh hành vi mơ hồ.

### 4.3. Thêm parameter optional

Thêm query parameter optional thường tương thích với consumer cũ vì request cũ có thể bỏ qua parameter:

~~~yaml
- name: includeArchived
  in: query
  required: false
  schema:
    type: boolean
    default: false
~~~

Điều này chỉ an toàn nếu provider thực sự có hành vi mặc định phù hợp khi parameter bị bỏ qua và không thay đổi ý nghĩa request cũ. Một parameter optional nhưng làm thay đổi default behavior của endpoint vẫn có thể là behavioral breaking change dù schema diff không báo lỗi.

## 5. Thay đổi request body và request schema

Request schema mô tả dữ liệu provider chấp nhận. Khi nâng cấp provider, giữ tương thích thường có nghĩa là không loại bỏ các payload hợp lệ theo schema cũ.

### 5.1. Thêm required property

Baseline:

~~~yaml
CreateOrderRequest:
  type: object
  required: [customerId]
  properties:
    customerId:
      type: string
~~~

Phiên bản mới:

~~~yaml
CreateOrderRequest:
  type: object
  required: [customerId, source]
  properties:
    customerId:
      type: string
    note:
      type: string
    source:
      type: string
~~~

Consumer cũ chỉ gửi `customerId`; payload trước đây hợp lệ nay bị từ chối. Đây là breaking change.

Nếu property mới có thể có giá trị mặc định, nên để optional và xử lý giá trị thiếu ở server trong giai đoạn chuyển tiếp. Sau khi consumer đã gửi property, có thể cân nhắc nâng mức required trong một major version.

### 5.2. Thu hẹp constraint của request

Giả sử trước đây server chấp nhận chuỗi tên dài tối đa 120 ký tự:

~~~yaml
name:
  type: string
  maxLength: 120
~~~

Phiên bản mới giảm còn 40:

~~~yaml
name:
  type: string
  maxLength: 40
~~~

Consumer cũ có thể gửi tên dài 80 ký tự và trước đây request hợp lệ. Nay provider từ chối. Đây là breaking change ở request contract.

Các thay đổi thu hẹp tập request hợp lệ thường cần đánh dấu:
- Thêm `required`.
- Tăng `minLength`, `minimum`, `minItems`.
- Giảm `maxLength`, `maximum`, `maxItems`.
- Thêm `pattern` hoặc constraint mới.
- Bỏ một giá trị khỏi enum được phép gửi.
- Đổi schema từ nullable sang non-nullable.
- Đặt `additionalProperties: false` khiến field cũ không còn được chấp nhận.

Ngược lại, nới constraint thường mở rộng tập request mà provider chấp nhận. Ví dụ tăng `maxLength`, bỏ một giới hạn hoặc cho phép thêm enum value trong request thường không buộc client cũ thay đổi.

### 5.3. Xóa hoặc đổi request property

Xóa property mà consumer vẫn gửi có thể làm request thất bại nếu provider từ chối field lạ, hoặc làm dữ liệu bị bỏ qua và thay đổi hành vi nghiệp vụ.

Đổi tên property cũng tương tự:
- Client cũ gửi `customerId`.
- Server mới chỉ đọc `clientId`.
- Giá trị cũ không được bind hoặc validation thất bại.

Để chuyển đổi, có thể tạm chấp nhận cả hai field, quy định rõ field ưu tiên và phát cảnh báo khi client dùng tên cũ. Không giữ hai field alias vô thời hạn nếu chúng có thể mang giá trị mâu thuẫn.

## 6. Thay đổi response schema

Response schema mô tả dữ liệu provider có thể trả. Consumer cũ thường phụ thuộc vào field, kiểu dữ liệu, enum và status code đã công bố.

### 6.1. Xóa response property

Baseline:

~~~yaml
OrderResponse:
  type: object
  properties:
    id:
      type: string
    status:
      type: string
    total:
      type: number
~~~

Phiên bản mới xóa `total`. Client cũ đang đọc `total` có thể nhận null, lỗi mapping hoặc mất dữ liệu nghiệp vụ. Đây là breaking change.

Nếu cần thay `total` bằng cấu trúc mới, có thể bổ sung field mới song song, giữ field cũ được đánh dấu deprecated và lên kế hoạch gỡ bỏ ở major version sau.

### 6.2. Đổi kiểu response property

Các thay đổi như:
- `integer` thành `string`.
- `number` thành object Money.
- `string` thành array.
- `date` thành `date-time`.
- Object thành nullable hoặc có thể thiếu.

đều có thể làm client parse response sai hoặc thay đổi kiểu generated SDK. Cần xem là breaking change trừ khi có bằng chứng consumer contract cho phép chuyển đổi.

### 6.3. Bỏ required khỏi response property

Nếu response trước đây bảo đảm `id` luôn có mặt:

~~~yaml
required: [id, status]
~~~

và phiên bản mới bỏ `id` khỏi required, provider được phép không trả `id`. Consumer cũ dựa vào guarantee này có thể lỗi khi field vắng mặt. Đây thường là breaking change vì provider đã nới lỏng cam kết response.

Ngược lại, thêm một property vào required của response làm provider cam kết trả property đó thường là thay đổi tăng guarantee. Tuy nhiên, hãy kiểm tra serializer/runtime thực tế và generated client trước khi kết luận an toàn.

### 6.4. Thêm response property

Thêm một field optional vào JSON response thường được coi là additive change:

~~~yaml
properties:
  id:
    type: string
  status:
    type: string
  trackingUrl:
    type: string
~~~

Nhưng một số consumer dùng deserializer strict và từ chối unknown property. Vì vậy, đây là thay đổi thường tương thích với client tolerant, không phải bảo đảm tuyệt đối cho mọi consumer. Nếu hệ sinh thái có strict deserialization, hãy kiểm tra cấu hình Jackson hoặc SDK generator đang dùng.

## 7. Thay đổi enum: request và response có chiều tác động khác nhau

Enum là nguồn breaking change thường bị bỏ qua.

### Request enum

Nếu provider nhận `statusFilter` với các giá trị `NEW`, `PAID`, `CANCELLED`, việc bỏ `CANCELLED` khiến request cũ dùng giá trị đó bị từ chối. Đây là breaking change.

Thêm một giá trị enum request thường mở rộng tập giá trị provider chấp nhận. Consumer cũ không cần dùng giá trị mới nên thường không bị ảnh hưởng.

### Response enum

Nếu provider có thể trả `status: NEW | PAID`, rồi bổ sung `REFUNDED`, tập giá trị response mở rộng. Client cũ dùng switch exhaustive hoặc enum generated có thể không xử lý được giá trị mới. Đây có thể là breaking change đối với consumer strict.

Bỏ một response enum value làm tập output hẹp hơn, thường ít rủi ro hơn vì consumer sẽ không còn gặp giá trị đó. Tuy nhiên, nếu consumer dựa vào việc một trạng thái nhất định xuất hiện để hoàn tất workflow, thay đổi này vẫn có thể ảnh hưởng hành vi.

| Vị trí enum | Thêm value | Xóa value |
|---|---|---|
| Request | Thường additive: provider chấp nhận thêm input | Thường breaking: provider từ chối input cũ |
| Response | Có thể breaking với client strict/exhaustive | Thường thu hẹp output, nhưng cần kiểm tra workflow |

Với response enum, khuyến khích consumer có nhánh xử lý giá trị không nhận diện được. Với request enum, provider nên duy trì các giá trị cũ trong thời gian migration đã cam kết.

## 8. Thay đổi response code, media type và header

Consumer thường xử lý theo status code và content type. Thay đổi chúng có thể phá vỡ client ngay cả khi JSON body không đổi.

| Thay đổi | Tác động |
|---|---|
| Xóa response code đã công bố | Client không còn nhận hành vi cũ |
| Đổi 200 thành 204 | Client có thể vẫn chờ response body |
| Đổi 201 thành 200 | Client xử lý create/Location có thể sai |
| Xóa media type `application/json` | Client không còn nhận representation cũ |
| Đổi response body media type | Parser/client negotiation có thể thất bại |
| Xóa response header được consumer dùng | Client mất metadata như Location hoặc ETag |
| Thêm response code mới | Thường additive, nhưng client strict có thể cần xử lý nhánh mới |

Thêm một response code mới thường không phá client tolerant, nhưng một số SDK sinh kiểu union hoặc code yêu cầu xử lý toàn bộ status có thể bị ảnh hưởng khi regenerate.

Nếu thay đổi hành vi lỗi, giữ status và error schema cũ trong giai đoạn chuyển tiếp hoặc công bố migration rõ ràng. Đừng thay 404 thành 200 với body rỗng chỉ để tránh báo lỗi; điều đó thay đổi semantics mà consumer có thể dựa vào.

## 9. Thay đổi security requirement và quyền truy cập

Thêm hoặc siết xác thực có thể làm client cũ không còn gọi được API:

- Endpoint trước public nay yêu cầu Bearer token.
- Scope cũ `orders:read` bị thay bằng scope mới `orders:read:all`.
- API key chuyển từ header cũ sang header mới.
- OAuth2 flow hoặc issuer thay đổi.
- Token audience hoặc client registration thay đổi khiến token hiện tại không được chấp nhận.

Đây thường là breaking change ở runtime contract, dù path và schema không đổi.

Ngược lại, xóa security requirement có thể không phá khả năng gọi của consumer cũ nhưng có thể tạo lỗ hổng bảo mật. Compatibility không phải tiêu chí duy nhất để quyết định một thay đổi security.

Khi đổi scope hoặc scheme:
1. Công bố scope mới và thời hạn chuyển tiếp.
2. Cho phép credential cũ và mới cùng hoạt động nếu chính sách bảo mật cho phép.
3. Cập nhật client và kiểm thử 401/403.
4. Theo dõi usage của scope cũ.
5. Thu hồi scope cũ theo lịch đã thông báo.

## 10. operationId, schema name và tác động đến generated SDK

Không phải mọi thay đổi breaking đều làm HTTP request thất bại. Một số thay đổi ảnh hưởng đến mã nguồn SDK được sinh từ OpenAPI.

Ví dụ:
- Đổi `operationId: getOrderById` thành `readOrder`.
- Đổi component schema `OrderResponse` thành `OrderView`.
- Đổi tag làm thay đổi package/class grouping trong một số generator.
- Đổi tên property hoặc enum constant.
- Đổi discriminator mapping.

Nếu client regenerate SDK, các method/class name có thể thay đổi khiến code không compile dù wire contract vẫn tương thích. Vì vậy, với dự án phân phối SDK, nên xem operationId, schema component name và tag là một phần của compatibility policy.

Một số thay đổi chỉ mang tính mô tả như sửa summary/description, thêm example hoặc sửa typo thường không phá wire contract. Nhưng nếu generator dùng metadata để đặt tên symbol, ngay cả thay đổi operationId/tag cũng có thể tác động source compatibility.

Khi đánh giá diff, tách hai lớp:
- **Wire compatibility:** request và response HTTP còn hoạt động không?
- **SDK/source compatibility:** consumer regenerate client có phải sửa code không?

## 11. Ví dụ tổng hợp: thay đổi nào nên chặn?

Giả sử baseline có operation tạo đơn:

~~~yaml
paths:
  /api/orders:
    post:
      operationId: createOrder
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        "201":
          description: Created
components:
  schemas:
    CreateOrderRequest:
      type: object
      required: [customerId]
      properties:
        customerId:
          type: string
        note:
          type: string
~~~

Phiên bản mới thêm `channel` vào required:

~~~yaml
CreateOrderRequest:
  type: object
  required: [customerId, channel]
  properties:
    customerId:
      type: string
    note:
      type: string
    channel:
      type: string
      enum: [WEB, MOBILE]
~~~

Consumer cũ chỉ gửi `customerId`, vì vậy payload cũ không còn hợp lệ. Đây là breaking change.

Nếu `channel` được thêm nhưng không nằm trong `required`, server có thể gán mặc định khi client cũ không gửi. Đây thường là thay đổi additive:

~~~yaml
CreateOrderRequest:
  type: object
  required: [customerId]
  properties:
    customerId:
      type: string
    note:
      type: string
    channel:
      type: string
      enum: [WEB, MOBILE]
      default: WEB
~~~

Dù vậy, default phải được thực thi trong code runtime; giá trị `default` trong OpenAPI chủ yếu là metadata và không tự làm Spring gán giá trị cho request DTO.

## 12. Phân biệt breaking, non-breaking và behavioral change

Một diff công cụ đánh dấu non-breaking không có nghĩa thay đổi không thể ảnh hưởng consumer. Cần phân biệt:

| Loại thay đổi | Ví dụ | Cách xử lý |
|---|---|---|
| Breaking wire change | Xóa path, thêm required request field, đổi response type | Major version hoặc migration có thời gian |
| Additive contract change | Thêm operation, thêm optional request parameter | Thường minor version, vẫn kiểm tra client strict |
| Documentation-only | Sửa description, example hoặc typo | Thường patch/documentation update |
| Behavioral change | Cùng schema nhưng đổi default, thứ tự xử lý, semantics status | Contract test và release note |
| Security change | Yêu cầu scope mới hoặc thay issuer | Đánh giá riêng, thường cần migration |
| SDK source change | Đổi operationId, schema name, tag | Kiểm tra generated SDK compile |

OpenAPI diff chủ yếu so sánh cấu trúc tài liệu. Nó không biết toàn bộ semantics nghiệp vụ, side effect, rate limit, latency hoặc dữ liệu thực tế mà provider trả về. Vì vậy, cần kết hợp diff với contract test, integration test và đánh giá consumer impact.

## 13. So sánh với baseline bằng công cụ OpenAPI diff

Không nên chỉ so sánh file hiện tại với file từ commit trước bất kỳ. Baseline nên là hợp đồng đã phát hành hoặc được consumer sử dụng làm chuẩn, chẳng hạn OpenAPI artifact của production release gần nhất.

Một công cụ phổ biến là oasdiff. Lệnh cơ bản:

~~~bash
oasdiff breaking openapi-released.yaml openapi-current.yaml
~~~

Công cụ so sánh baseline và tài liệu hiện tại, sau đó báo các thay đổi được phân loại là breaking theo rule set của phiên bản tool.

Có thể xem diff tổng quát:

~~~bash
oasdiff diff openapi-released.yaml openapi-current.yaml
~~~

Đặt baseline và current theo đúng thứ tự:
- Baseline: tài liệu đã phát hành.
- Current: tài liệu được sinh từ nhánh đang kiểm tra.

Đọc output thay vì chỉ dựa vào exit code. Một số thay đổi có thể được công cụ phân loại breaking nhưng được dự án chấp nhận có điều kiện; ngược lại, behavioral change hoặc SDK naming change có thể cần review thủ công dù công cụ không đánh dấu.

Pin version của oasdiff trong CI để rule set không tự thay đổi giữa các lần build. Khi nâng version tool, chạy lại trên một số cặp baseline/current đã biết để hiểu khác biệt phân loại.

## 14. Đưa kiểm tra breaking change vào CI

Một pipeline cơ bản có thể gồm:

~~~mermaid
flowchart TD
    A[Build Spring Boot application] --> B[Export OpenAPI document]
    B --> C[Validate OpenAPI syntax]
    C --> D[Compare with released baseline]
    D --> E{Breaking change?}
    E -- No --> F[Run contract tests]
    E -- Yes --> G[Require version/migration review]
    G --> H{Approved exception?}
    H -- No --> I[Fail pipeline]
    H -- Yes --> F
    F --> J[Publish artifact and report]
~~~

Ví dụ shell trong CI:

~~~bash
# Tạo OpenAPI document từ ứng dụng test đã khởi động
curl -fsS http://localhost:8080/v3/api-docs -o openapi-current.json

# So sánh với artifact của release gần nhất
oasdiff breaking openapi-released.json openapi-current.json
~~~

Nếu công cụ trả exit code khác 0 khi phát hiện breaking change, CI có thể fail job. Hãy kiểm tra hành vi exit code của version tool được pin và cấu hình pipeline theo đúng tài liệu phiên bản đó.

Pipeline nên lưu:
- Baseline artifact và version release tương ứng.
- OpenAPI document mới.
- Diff report.
- Phiên bản validator/diff tool.
- Kết quả contract test.
- Quyết định chấp nhận hoặc ngoại lệ nếu có.

Không tạo baseline mới từ chính nhánh đang kiểm tra rồi so sánh với nó; cách đó làm mất khả năng phát hiện thay đổi so với hợp đồng đã phát hành.

## 15. Quản lý version và migration khi có breaking change

Nếu breaking change là cần thiết, cần quản lý quá trình chuyển đổi:

1. Xác định consumer nào dùng operation hoặc schema bị thay đổi.
2. Công bố lý do, thời điểm và migration guide.
3. Tạo version API mới hoặc một giai đoạn tương thích song song theo policy.
4. Duy trì endpoint/schema cũ trong thời hạn đã công bố.
5. Cung cấp ví dụ request/response mới và mapping từ field cũ sang field mới.
6. Theo dõi usage của version cũ.
7. Chỉ gỡ bỏ sau khi consumer đã chuyển đổi hoặc hết thời hạn hỗ trợ.

SemVer thường được áp dụng ở version API hoặc SDK theo chính sách sản phẩm:
- Major: thay đổi không tương thích.
- Minor: bổ sung chức năng tương thích.
- Patch: sửa lỗi hoặc cập nhật không làm thay đổi contract theo chính sách.

Trường `info.version` trong OpenAPI là version API do dự án quản lý. Trường `openapi` là version của định dạng đặc tả. Đổi `openapi: 3.0.3` thành `3.1.0` không tự động là phát hành API major; ngược lại, đổi `info.version` không tự làm endpoint runtime có version mới.

Nếu dùng version trong URL như `/v1` và `/v2`, cần duy trì route và tài liệu cho từng version. Nếu version qua header hoặc media type, cần thể hiện rõ cách chọn representation và kiểm thử đúng negotiation.

## 16. Khi nào cần ngoại lệ?

Không phải breaking change nào cũng có thể tránh. Ví dụ lỗ hổng bảo mật, dữ liệu sai hoặc endpoint không còn hợp lệ có thể buộc provider thay đổi nhanh.

Một ngoại lệ nên ghi rõ:
- Rule diff nào được miễn.
- Path/operation/schema bị ảnh hưởng.
- Consumer bị tác động và người phụ trách.
- Lý do không thể duy trì tương thích.
- Version hoặc thời điểm áp dụng.
- Migration path và deadline.
- Người phê duyệt và ticket theo dõi.

Không nên tắt toàn bộ breaking-change check chỉ vì một operation cần thay đổi. Tạo allowlist hẹp theo rule/path/version và có thời hạn; nếu công cụ hỗ trợ, lưu file cấu hình ngoại lệ cùng review của code owner.

## 17. Checklist review một OpenAPI diff

- [ ] So sánh với baseline đã phát hành, không chỉ với tài liệu bất kỳ ở nhánh trước.
- [ ] Path và HTTP method cũ vẫn tồn tại.
- [ ] Parameter cũ giữ nguyên tên, vị trí, kiểu và serialization.
- [ ] Không thêm required request parameter ngoài kế hoạch.
- [ ] Request body cũ vẫn được chấp nhận.
- [ ] Không thu hẹp request enum hoặc constraint mà consumer đang dùng.
- [ ] Response code và media type quan trọng vẫn được hỗ trợ.
- [ ] Response property cũ không bị xóa hoặc đổi kiểu ngoài kế hoạch.
- [ ] Response enum mới đã được đánh giá với client strict.
- [ ] Security scheme và scope không thay đổi bất ngờ.
- [ ] operationId, schema name và tag được xem xét nếu có generated SDK.
- [ ] Server URL và versioning strategy vẫn đúng.
- [ ] Diff tool và validator được pin version.
- [ ] Contract test bao phủ happy path và các response quan trọng.
- [ ] Breaking change có migration guide, version plan và phê duyệt.

## Tài liệu tham khảo

- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): cấu trúc path, operation, parameter, request body, response và schema.
- [oasdiff](https://github.com/Tufin/oasdiff): công cụ so sánh OpenAPI và phát hiện breaking changes.
- [Google Cloud – API Design Guide](https://cloud.google.com/apis/design): hướng dẫn thiết kế API ổn định và tương thích.
- [Microsoft REST API Guidelines](https://github.com/microsoft/api-guidelines): quy ước thiết kế và tiến hóa API.
- [Semantic Versioning](https://semver.org/): quy tắc major, minor và patch version.
- [Pact – Consumer Driven Contracts](https://docs.pact.io/): kiểm thử hợp đồng giữa consumer và provider.
