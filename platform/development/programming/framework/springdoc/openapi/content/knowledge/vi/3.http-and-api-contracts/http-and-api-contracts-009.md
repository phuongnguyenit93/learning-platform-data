# Tính tương thích của hợp đồng đối với bên gọi API

Hợp đồng API mô tả cách một bên gọi gửi request và cách hệ thống cung cấp API phản hồi. Khi hợp đồng thay đổi, điều cần quan tâm là những client đang hoạt động có tiếp tục gọi được API hay không, và client mới có thể làm việc với các phiên bản server đang được hỗ trợ hay không. Một thay đổi nhìn qua có vẻ nhỏ, chẳng hạn thêm một giá trị enum hoặc đổi mã trạng thái, vẫn có thể làm hỏng ứng dụng đang sử dụng API.

Với `springdoc-openapi`, hợp đồng được biểu diễn bằng đặc tả OpenAPI sinh từ controller, DTO, annotation và cấu hình Spring. Vì vậy, quản lý tính tương thích cần kết hợp ba việc: thiết kế hợp đồng rõ ràng, kiểm soát thay đổi trong đặc tả và kiểm thử hành vi thực tế giữa provider với consumer.

## 1. Bên cung cấp và bên gọi API

Trong một tương tác API:

- **Provider** là hệ thống cung cấp endpoint và xử lý request.
- **Consumer** là ứng dụng, dịch vụ hoặc người dùng gọi endpoint đó.
- **Hợp đồng API** quy định path, HTTP method, parameter, request body, response, schema, mã trạng thái, media type và yêu cầu bảo mật.

Ví dụ, một ứng dụng bán hàng gọi `GET /api/products/42` để lấy thông tin sản phẩm. Provider cam kết trả về một response theo schema đã công bố. Consumer có thể là frontend, ứng dụng di động, dịch vụ kho hàng hoặc một SDK được sinh từ tài liệu OpenAPI.

Tính tương thích phải được đánh giá từ góc nhìn của consumer. Một thay đổi có thể an toàn với client cũ nhưng gây lỗi cho client mới khi client mới kết nối đến server cũ. Vì vậy cần phân biệt hai hướng:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Backward compatibility (tương thích ngược) | Server mới có tiếp tục phục vụ client cũ không? | Server thêm một field request tùy chọn nhưng vẫn chấp nhận request cũ không có field đó |
| Forward compatibility (tương thích xuôi) | Client mới có làm việc được với server cũ không? | Client mới vẫn gửi request theo dạng cũ khi kết nối tới server chưa hỗ trợ field mới |

Một thay đổi chỉ có thể được gọi là tương thích khi xét rõ hướng giao tiếp, quy tắc xử lý dữ liệu và cách client được triển khai. Không có quy tắc chung bảo đảm mọi client đều bỏ qua field hoặc giá trị mà chúng chưa biết.

## 2. Những phần tạo nên hợp đồng cần ổn định

Đặc tả OpenAPI chứa nhiều thành phần ảnh hưởng trực tiếp đến consumer:

| Thành phần | Thông tin consumer dựa vào | Thay đổi có thể gây lỗi |
|---|---|---|
| `paths` và HTTP method | Địa chỉ và cách gọi operation | Đổi path, đổi method hoặc xóa endpoint |
| `parameters` | Tên, vị trí, kiểu và tính bắt buộc của tham số | Đổi tên query parameter hoặc chuyển optional thành required |
| `requestBody` | Cấu trúc payload, media type và schema | Xóa field được chấp nhận hoặc thêm field bắt buộc |
| `responses` | Mã trạng thái, header, media type và payload trả về | Xóa field, đổi kiểu hoặc đổi mã trạng thái |
| `components.schemas` | Cấu trúc dữ liệu dùng chung | Thay đổi required, enum, format hoặc giới hạn giá trị |
| `security` | Cách xác thực và quyền cần có | Thêm yêu cầu xác thực khiến client cũ không có credential bị từ chối |
| `operationId` | Tên operation mà công cụ sinh SDK có thể dùng | Đổi tên có thể làm đổi tên method trong client được sinh |

Hợp đồng còn bao gồm ý nghĩa nghiệp vụ. Ví dụ, trường `price` vẫn là số nguyên nhưng đổi đơn vị từ đồng sang nghìn đồng; schema có thể không thay đổi nhưng kết quả consumer tính toán sẽ sai. Tương tự, thay đổi múi giờ, quy tắc làm tròn, thứ tự mặc định, ý nghĩa của trạng thái hoặc cách phân trang đều có thể phá vỡ tương thích.

## 3. Đánh giá thay đổi ở request

Request do consumer gửi đến provider. Cần kiểm tra provider mới có tiếp tục chấp nhận mọi request hợp lệ mà client cũ đang gửi hay không.

| Thay đổi ở request | Ảnh hưởng đến client cũ gọi server mới | Đánh giá thường gặp |
|---|---|---|
| Thêm field tùy chọn và server chấp nhận khi field vắng mặt | Client cũ không gửi field mới vẫn hoạt động | Thường tương thích ngược |
| Thêm field bắt buộc | Client cũ không gửi field mới nên request bị từ chối hoặc xử lý sai | Breaking change |
| Chuyển field tùy chọn thành bắt buộc | Request cũ có thể thiếu field | Breaking change |
| Xóa field request mà server trước đây chấp nhận | Client cũ vẫn gửi field đã bị loại bỏ | Có thể breaking, đặc biệt khi server từ chối field không biết |
| Đổi tên field hoặc parameter | Client cũ tiếp tục gửi tên cũ | Breaking change nếu tên cũ không còn được hỗ trợ |
| Thu hẹp miền giá trị, pattern hoặc giới hạn số | Giá trị trước đây hợp lệ có thể bị từ chối | Breaking change |
| Bổ sung một giá trị được chấp nhận cho enum request | Client cũ vẫn gửi các giá trị cũ | Thường tương thích ngược; client mới gửi giá trị mới đến server cũ có thể thất bại |
| Đổi media type hoặc cấu trúc payload | Client cũ có thể gửi định dạng không còn được chấp nhận | Thường breaking |

Ví dụ, phiên bản đầu của API tạo sản phẩm nhận request:

```json
{
  "name": "Keyboard",
  "price": 1290000
}
```

Server có thể bổ sung field `description` dưới dạng tùy chọn:

```json
{
  "name": "Keyboard",
  "price": 1290000,
  "description": "Bàn phím cơ"
}
```

Client cũ vẫn gửi payload chỉ có `name` và `price`. Để thay đổi này tương thích ngược, server mới phải tiếp tục chấp nhận request thiếu `description` và có quy tắc xử lý hợp lý khi field đó không xuất hiện.

Trong OpenAPI, cần phân biệt field được phép xuất hiện với field bắt buộc phải có. Ví dụ schema sau chỉ yêu cầu `name` và `price`; `description` là tùy chọn:

```yaml
type: object
required:
  - name
  - price
properties:
  name:
    type: string
  price:
    type: integer
    format: int64
  description:
    type: string
```

Khi cập nhật DTO, annotation và validation phải phản ánh đúng quy tắc này. Nếu thêm `@NotNull` hoặc đưa `description` vào danh sách `required`, đó là thay đổi hợp đồng có thể làm client cũ không còn gửi được request hợp lệ.

## 4. Đánh giá thay đổi ở response

Response do provider gửi đến consumer. Với response, cần xem client cũ có xử lý được dữ liệu mới và client mới có thể hoạt động khi gặp server cũ hay không.

| Thay đổi ở response | Ảnh hưởng đến client cũ | Đánh giá thường gặp |
|---|---|---|
| Thêm property tùy chọn | Client bỏ qua property chưa biết có thể tiếp tục hoạt động | Thường tương thích ngược với client tolerant |
| Xóa property hoặc đổi tên | Client đang đọc property cũ có thể lỗi hoặc thiếu dữ liệu | Breaking change |
| Chuyển property luôn có thành có thể vắng mặt hoặc null | Client có thể không xử lý trường hợp thiếu dữ liệu | Breaking change |
| Đổi kiểu dữ liệu hoặc format | Bộ giải mã hoặc logic client có thể không còn tương thích | Breaking change |
| Thêm giá trị enum trong response | Client dùng switch exhaustive có thể không xử lý giá trị mới | Có rủi ro breaking |
| Xóa giá trị enum trong response | SDK hoặc consumer dựa vào tập giá trị đã công bố có thể cần cập nhật; cần kiểm tra logic phụ thuộc giá trị cũ | Có thể breaking tùy cách sinh mã và xử lý enum |
| Thay mã trạng thái hoặc response body | Logic xử lý thành công/lỗi của client có thể sai | Thường breaking |
| Thêm response status mới | Client có thể coi đó là lỗi không xác định | Cần kiểm tra cách client xử lý status chưa biết |

Thêm property vào response thường được coi là thay đổi cộng thêm, nhưng chỉ an toàn nếu consumer được thiết kế để bỏ qua property không biết. Một số bộ giải mã, cấu hình schema hoặc client sinh mã có thể từ chối dữ liệu chứa field lạ. Vì thế, cần kiểm tra các client thực tế và quy ước tolerant-reader của hệ thống.

Ví dụ response cũ:

```json
{
  "id": 42,
  "name": "Keyboard"
}
```

Response mới bổ sung `description`:

```json
{
  "id": 42,
  "name": "Keyboard",
  "description": "Bàn phím cơ"
}
```

Client chỉ đọc `id` và `name` thường vẫn hoạt động. Tuy nhiên, client mới dựa vào `description` sẽ không thể nhận được dữ liệu đó khi gọi server cũ. Nếu cần triển khai client và server độc lập, consumer nên xử lý trường mới như dữ liệu có thể vắng mặt trong giai đoạn chuyển đổi.

## 5. Phân biệt field vắng mặt, null và giá trị mặc định

Một nguồn lỗi phổ biến là coi ba trạng thái sau như nhau:

1. Field không xuất hiện trong JSON.
2. Field xuất hiện với giá trị `null`.
3. Field xuất hiện với giá trị mặc định như `0`, `false` hoặc chuỗi rỗng.

Ví dụ:

```json
{}
```

```json
{"description": null}
```

```json
{"description": ""}
```

Ba payload có thể mang ý nghĩa khác nhau. Với API cập nhật dữ liệu, field vắng mặt có thể có nghĩa là giữ nguyên giá trị; `null` có thể có nghĩa là xóa giá trị; chuỗi rỗng có thể là một giá trị được gửi có chủ đích. Cần định nghĩa rõ hành vi này trong hợp đồng và kiểm thử ở cả provider lẫn consumer.

Trong OpenAPI, `required` điều khiển việc property có bắt buộc xuất hiện hay không. Khả năng nhận `null` là một khía cạnh riêng và được biểu diễn theo phiên bản OpenAPI/JSON Schema đang dùng. Không được suy luận rằng field không nằm trong `required` thì tự động cho phép giá trị `null`. DTO, Jackson configuration và validation ở server phải nhất quán với schema đã công bố.

## 6. Enum, kiểu dữ liệu và ràng buộc schema

Enum trong request và response có mức độ rủi ro khác nhau. Khi server bổ sung giá trị enum được chấp nhận cho request, client cũ vẫn có thể tiếp tục gửi các giá trị trước đó. Nhưng client mới gửi giá trị vừa bổ sung tới server cũ có thể bị từ chối. Với enum trong response, server mới có thể trả về một giá trị mà client cũ chưa biết; code sinh từ enum hoặc switch expression có thể không xử lý được.

Ví dụ:

```yaml
type: string
enum:
  - NEW
  - PROCESSING
  - COMPLETED
```

Nếu provider bổ sung `CANCELLED`, cần kiểm tra consumer có nhánh xử lý mặc định hay có thể gặp lỗi khi deserialize enum không biết. Với API công khai hoặc nhiều client được phát hành độc lập, có thể dùng string và quy ước xử lý giá trị chưa biết, hoặc thiết kế cơ chế mở rộng enum phù hợp với ngôn ngữ SDK.

Các thay đổi schema khác cũng cần đánh giá cẩn thận:

- Đổi `integer` thành `string` làm thay đổi kiểu dữ liệu mà client nhận hoặc gửi.
- Đổi `int32` thành `int64` có thể gây vấn đề với client có giới hạn số nguyên hoặc generator ánh xạ kiểu khác nhau.
- Thêm `minimum`, `maximum`, `minLength`, `maxLength` hoặc `pattern` có thể loại bỏ dữ liệu từng hợp lệ.
- Đổi `format` của ngày giờ hoặc số có thể thay đổi cách parse và serialize.
- Thay đổi `oneOf`, `anyOf`, `allOf` hoặc discriminator có thể ảnh hưởng mạnh đến client sinh mã và bộ giải mã đa hình.
- Thay đổi đơn vị, độ chính xác, timezone hoặc ý nghĩa của property là thay đổi ngữ nghĩa, kể cả khi kiểu OpenAPI không đổi.

Khi dùng `@Schema`, mô tả chính xác kiểu và giới hạn thực tế. Không thêm ràng buộc chỉ để tài liệu trông chặt chẽ hơn nếu server chưa thực thi cùng quy tắc đó.

## 7. HTTP method, parameter, status và bảo mật

Tính tương thích không chỉ nằm trong JSON body. Các phần của giao thức HTTP cũng là một phần hợp đồng:

- Đổi path hoặc HTTP method làm client đang gọi URL cũ không còn truy cập được operation.
- Đổi tên query parameter, path parameter hoặc header khiến request cũ không còn khớp hợp đồng.
- Chuyển query parameter từ optional sang required có thể làm client cũ nhận `400 Bad Request` hoặc lỗi validation.
- Đổi `Content-Type` hoặc `Accept` có thể khiến client và server không thương lượng được media type.
- Đổi từ `200 OK` có body sang `204 No Content` làm client đang đọc body gặp lỗi.
- Trả `200` cho trường hợp trước đây là `404`, hoặc thay đổi cấu trúc error response, có thể làm logic xử lý lỗi của consumer sai lệch.
- Thêm xác thực hoặc quyền truy cập bắt buộc có thể khiến client cũ nhận `401 Unauthorized` hoặc `403 Forbidden`.

Ví dụ, một client đang gọi:

```http
GET /api/products?page=0&size=20
Accept: application/json
```

Nếu server đổi `size` thành `pageSize` mà không hỗ trợ tên cũ, client phải được cập nhật. Có thể triển khai chuyển tiếp bằng cách tạm thời chấp nhận cả hai parameter, xác định rõ ưu tiên khi cả hai cùng xuất hiện và đánh dấu tên cũ là deprecated trước khi loại bỏ.

## 8. Thay đổi tương thích và breaking change

Một cách thực tế để đánh giá là hỏi liệu consumer hiện tại có phải sửa mã, cấu hình hoặc phát hành lại ứng dụng chỉ để tiếp tục hoạt động hay không.

| Thay đổi | Thường có thể giữ tương thích? | Điều kiện cần kiểm tra |
|---|---|---|
| Thêm endpoint mới | Có | Không làm thay đổi route hoặc hành vi cũ |
| Thêm request field tùy chọn | Có với client cũ | Server chấp nhận payload không có field mới |
| Thêm response field | Có với client tolerant | Client cũ bỏ qua field lạ; schema decoder không strict |
| Thêm giá trị enum response | Có rủi ro | Consumer có xử lý giá trị chưa biết |
| Thêm request field bắt buộc | Không | Client cũ không thể tự gửi field mới |
| Xóa hoặc đổi tên field response | Không | Client cũ có thể đang đọc field đó |
| Đổi path, method hoặc parameter | Không nếu bỏ giao diện cũ | Client phải đổi request |
| Thu hẹp giá trị hợp lệ | Không nếu dữ liệu cũ bị từ chối | Request trước đây hợp lệ phải tiếp tục được chấp nhận |
| Tăng yêu cầu bảo mật | Có thể breaking | Credential và quyền của client cũ có đáp ứng được không |
| Đổi ý nghĩa nghiệp vụ | Thường là breaking | Consumer có thể diễn giải cùng dữ liệu theo quy tắc cũ |

Đây là đánh giá phổ biến, không phải định luật tuyệt đối. Kết quả phụ thuộc vào schema thực tế, cách serialize/deserialize, cấu hình validator, code được sinh và cách consumer xử lý trường hợp không biết.

## 9. Dùng springdoc để thể hiện hợp đồng ổn định

Springdoc tạo tài liệu từ controller, DTO, Spring annotations và Swagger annotations. Hãy xem đặc tả sinh ra như hợp đồng công khai giữa provider và consumer. Ví dụ:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
@Tag(name = "Products")
class ProductController {

    @GetMapping("/{id}")
    @Operation(
        operationId = "getProductById",
        summary = "Lấy sản phẩm theo mã"
    )
    ProductResponse getById(@PathVariable Long id) {
        return productService.getById(id);
    }
}

@Schema(description = "Thông tin sản phẩm")
record ProductResponse(
    @Schema(description = "Mã sản phẩm", example = "42")
    Long id,
    @Schema(description = "Tên sản phẩm", example = "Keyboard")
    String name,
    @Schema(description = "Mô tả sản phẩm", example = "Bàn phím cơ")
    String description
) {
}
```

Một số nguyên tắc nên áp dụng:

- Giữ `operationId` ổn định vì công cụ sinh client có thể dùng nó để tạo tên method.
- Chỉ đánh dấu property là required khi server thực sự yêu cầu hoặc luôn bảo đảm trả về property đó.
- Mô tả rõ kiểu dữ liệu, format, enum, giới hạn và ví dụ.
- Công bố response thành công và lỗi quan trọng, gồm mã trạng thái cùng schema body.
- Giữ path, method, parameter và media type ổn định trong cùng một phiên bản hợp đồng.
- Không dùng annotation để mô tả một hành vi mà controller hoặc cấu hình runtime không thực thi.

### Đánh dấu operation đã deprecated

Khi chuẩn bị thay thế endpoint, có thể đánh dấu operation cũ là deprecated để consumer biết cần chuyển đổi:

```java
@GetMapping("/legacy/{id}")
@Operation(
    operationId = "getLegacyProductById",
    summary = "Lấy sản phẩm theo endpoint cũ",
    deprecated = true
)
ProductResponse getLegacyById(@PathVariable Long id) {
    return productService.getById(id);
}
```

Trạng thái deprecated trong OpenAPI là tín hiệu cho công cụ và người đọc tài liệu. Nó không tự chặn request và cũng không thông báo đầy đủ thời điểm endpoint sẽ bị gỡ. Provider cần công bố hướng thay thế, thời hạn hỗ trợ, kế hoạch chuyển đổi và theo dõi việc sử dụng endpoint cũ trước khi xóa.

## 10. Quản lý phiên bản hợp đồng

Khi thay đổi không thể duy trì tương thích, cần có chiến lược phiên bản để consumer chuyển đổi có kiểm soát. Một số cách phổ biến:

| Cách versioning | Ví dụ | Đặc điểm |
|---|---|---|
| Version trong path | `/api/v1/products`, `/api/v2/products` | Dễ quan sát, định tuyến và vận hành song song |
| Version qua header | `X-API-Version: 2` | Giữ path ổn định nhưng cần quản lý header và tài liệu rõ ràng |
| Version qua media type | `Accept: application/vnd.example.product-v2+json` | Gắn version với biểu diễn nội dung, phức tạp hơn khi debug |

Không nhất thiết tăng version cho mọi thay đổi cộng thêm. Có thể giữ cùng phiên bản khi thêm operation mới hoặc field tùy chọn mà vẫn đáp ứng chính sách tương thích của hệ thống. Khi thay đổi bắt buộc khiến client cũ không thể hoạt động, nên công bố phiên bản hợp đồng mới hoặc có cơ chế chuyển tiếp tương đương.

Một kế hoạch chuyển phiên bản nên có các bước:

1. Xác định thay đổi nào không thể giữ tương thích và consumer nào bị ảnh hưởng.
2. Công bố hợp đồng mới cùng ví dụ request/response và hướng dẫn di chuyển.
3. Vận hành phiên bản cũ và mới song song trong thời gian đã thông báo.
4. Đánh dấu operation hoặc schema cũ là deprecated trong tài liệu.
5. Theo dõi traffic, lỗi và consumer còn sử dụng phiên bản cũ.
6. Chỉ ngừng hỗ trợ khi đã hết thời hạn và đáp ứng chính sách thông báo đã công bố.

Giữ bản OpenAPI của từng phiên bản đã phát hành để có thể so sánh chính xác. Tài liệu hiện tại không thay thế được hợp đồng lịch sử mà client đã dùng để phát triển.

## 11. Kiểm thử tính tương thích của hợp đồng

Kiểm tra cú pháp OpenAPI hợp lệ là cần thiết nhưng chưa đủ. Một tài liệu có thể hợp lệ về cấu trúc mà vẫn chứa breaking change hoặc mô tả sai hành vi server. Nên kiểm tra ở nhiều lớp:

1. **Validate đặc tả:** kiểm tra JSON/YAML có đúng cấu trúc OpenAPI, schema và reference hợp lệ.
2. **So sánh đặc tả:** so sánh tài liệu hiện tại với bản đã phát hành để tìm endpoint, field, parameter, enum, status hoặc security requirement đã thay đổi.
3. **Phân loại thay đổi:** xác định tác động với request và response, theo cả hướng client cũ gọi server mới và client mới gọi server cũ.
4. **Kiểm thử provider:** gửi request theo hợp đồng và xác nhận server trả status, header và body đúng như tài liệu.
5. **Kiểm thử consumer:** xác nhận client xử lý được response thực tế, field thiếu, field mới và giá trị enum chưa biết theo chính sách đã chọn.
6. **Kiểm thử tích hợp:** chạy các consumer quan trọng với phiên bản provider mới trước khi phát hành.

Ví dụ một pipeline có thể lấy tài liệu OpenAPI từ ứng dụng chạy trong môi trường kiểm thử:

```bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  -o build/openapi.json
```

Sau đó lưu hoặc tải bản hợp đồng chuẩn của phiên bản đang phát hành và chạy công cụ validate/diff trong CI. Khi diff phát hiện thay đổi, nhóm phát triển cần review ý nghĩa của thay đổi thay vì tự động kết luận mọi khác biệt đều breaking hoặc đều an toàn.

### Những tình huống nên có trong bộ kiểm thử

- Request cũ không có field vừa được bổ sung vẫn được server mới chấp nhận.
- Response mới có thêm property không làm client cũ lỗi deserialize.
- Client xử lý được enum hoặc status chưa biết theo quy tắc dự phòng đã thiết kế.
- Parameter tùy chọn, giá trị mặc định và giới hạn được thực thi đúng như tài liệu.
- Error response giữ cấu trúc ổn định cho các mã trạng thái đã công bố.
- Credential, scope và quyền truy cập của consumer được duy trì hoặc có kế hoạch chuyển đổi.
- Client mới có hành vi phù hợp khi kết nối đến server cũ trong giai đoạn rollout song song.

## 12. Quy trình review một thay đổi hợp đồng

Trước khi merge thay đổi controller hoặc DTO, reviewer có thể thực hiện quy trình sau:

1. Sinh lại OpenAPI từ ứng dụng và kiểm tra diff so với hợp đồng đã phát hành.
2. Xác định thay đổi nằm ở request, response, HTTP operation, security hay ngữ nghĩa dữ liệu.
3. Với từng thay đổi, mô phỏng client cũ gọi server mới và client mới gọi server cũ.
4. Kiểm tra các SDK được sinh, frontend và dịch vụ tích hợp có phụ thuộc vào field, enum, `operationId` hoặc status bị thay đổi hay không.
5. Bổ sung kiểm thử provider/consumer cho trường hợp có rủi ro.
6. Nếu thay đổi không tương thích, cập nhật versioning, tài liệu di chuyển và thời hạn hỗ trợ.
7. Phát hành tài liệu cùng phiên bản ứng dụng để consumer có thể truy xuất đúng hợp đồng.

Một thay đổi được coi là an toàn khi đã có bằng chứng rằng các consumer trong phạm vi hỗ trợ tiếp tục hoạt động theo chính sách tương thích của sản phẩm. Đối với API được nhiều nhóm hoặc khách hàng sử dụng, cần tính đến client cũ vẫn tồn tại sau khi server đã được nâng cấp.

## 13. Checklist duy trì tính tương thích

- [ ] Đã xác định provider, consumer và hướng tương thích đang đánh giá.
- [ ] Request cũ vẫn được chấp nhận sau thay đổi server.
- [ ] Response mới không làm client hiện tại lỗi khi parse hoặc xử lý.
- [ ] Field required, optional, nullable và giá trị mặc định được định nghĩa rõ.
- [ ] Enum, kiểu dữ liệu, format và giới hạn schema được đánh giá khi thay đổi.
- [ ] Path, method, parameter, status code, header và media type được giữ ổn định hoặc có kế hoạch chuyển đổi.
- [ ] Thay đổi ý nghĩa nghiệp vụ được xem xét như thay đổi hợp đồng.
- [ ] `operationId` ổn định nếu được dùng để sinh SDK.
- [ ] OpenAPI đã được validate và so sánh với phiên bản đã phát hành.
- [ ] Có kiểm thử provider/consumer cho các trường hợp rủi ro.
- [ ] Breaking change có version mới, hướng dẫn di chuyển và thời hạn hỗ trợ phù hợp.
- [ ] Tài liệu OpenAPI của từng phiên bản phát hành được lưu để đối chiếu.

Tính tương thích của hợp đồng quyết định khả năng các ứng dụng độc lập cùng phát triển mà không làm gián đoạn tích hợp. Springdoc giúp biểu diễn hợp đồng từ mã nguồn Spring Boot; quy trình review, so sánh đặc tả và kiểm thử provider/consumer giúp phát hiện thay đổi nguy hiểm trước khi phát hành. Khi đánh giá từ cả hai hướng client cũ và client mới, nhóm phát triển có thể mở rộng API có kiểm soát và duy trì dịch vụ cho những consumer đang sử dụng.
