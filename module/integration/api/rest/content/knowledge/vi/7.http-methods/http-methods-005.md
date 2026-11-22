# PUT và ngữ nghĩa thay thế trạng thái tại URI do client biết

## 1. Mục tiêu bài học

Trong một REST API, URI xác định resource, còn phương thức HTTP mô tả ý định của client đối với resource đó. `PUT` thể hiện ý định tạo hoặc thay thế trạng thái của resource đích bằng trạng thái được mô tả trong nội dung request.

Sau bài này, bạn có thể:

- Chọn `PUT` khi client biết URI đích và muốn gửi trạng thái thay thế đầy đủ.
- Xác định rõ phần trạng thái nào client được quản lý, cách xử lý field thiếu và giá trị `null`.
- Phân biệt thay thế bằng `PUT`, cập nhật một phần bằng `PATCH` và xử lý bằng `POST`.
- Giải thích tính idempotent mà không nhầm với phản hồi luôn giống nhau.
- Chọn mã trạng thái và điều kiện HTTP phù hợp khi tạo, thay thế hoặc gặp xung đột cập nhật.
- Áp dụng hợp đồng trên vào Java/Spring và xác định các tình huống cần kiểm thử.

Ví dụ xuyên suốt là resource cấu hình thông báo của một người dùng:

```text
/users/u-42/notification-preferences
```

Client biết `u-42` và biết quy tắc URI từ hợp đồng API, nên có thể xác định URI cấu hình ngay cả khi cấu hình chưa được tạo. Việc client biết URI không đồng nghĩa client có quyền sửa resource; xác thực và phân quyền vẫn là yêu cầu độc lập.

## 2. Ngữ nghĩa cốt lõi: trạng thái mong muốn tại một URI xác định

Giả sử cấu hình hiện tại là:

```json
{
  "emailEnabled": true,
  "smsEnabled": false,
  "digestFrequency": "DAILY"
}
```

Client muốn thay toàn bộ cấu hình bằng trạng thái mới:

```http
PUT /users/u-42/notification-preferences HTTP/1.1
Host: api.example.test
Content-Type: application/json

{
  "emailEnabled": false,
  "smsEnabled": true,
  "digestFrequency": "OFF"
}
```

Nếu server chấp nhận và thực hiện thành công, trạng thái cấu hình mới tương ứng với nội dung client gửi. Server không lấy những field vắng mặt rồi mặc nhiên giữ giá trị cũ như một phép cập nhật từng phần.

Một cách diễn đạt hữu ích là:

> Client nói: “Hãy làm cho resource tại URI này có trạng thái được mô tả trong representation tôi gửi.”

Representation là cách biểu diễn resource trên đường truyền, chẳng hạn JSON. Representation không phải bản sao bắt buộc của một hàng cơ sở dữ liệu. Server có thể lưu dữ liệu thành nhiều bảng, áp dụng ràng buộc nghiệp vụ hoặc cung cấp những representation khác nhau.

Vì vậy, không nên diễn giải `PUT` thành “xóa hàng cũ rồi insert hàng mới”. Đó là lựa chọn cài đặt, có thể gây lỗi khóa ngoại, mất lịch sử hoặc thay đổi định danh ngoài ý muốn. Thường có thể cập nhật trạng thái trong một transaction mà vẫn giữ nguyên định danh resource.

### 2.1. “URI do client biết” nghĩa là gì?

Client biết chính xác resource đích trước khi gửi request. Có thể là:

- URI được server trả về từ lần đọc trước.
- URI được tài liệu API quy định, như cấu hình gắn với một user đã biết.
- URI chứa khóa do client được phép lựa chọn, như mã tài liệu trong một namespace thuộc quyền quản lý của client.

Không nhất thiết client tự đặt mọi định danh. Điều quan trọng là request đã chỉ ra URI của resource sẽ nhận trạng thái mới.

So sánh hai thiết kế:

```http
POST /documents
Content-Type: application/json

{"title":"Hướng dẫn vận hành"}
```

Server chọn URI tài liệu mới, ví dụ `/documents/d-901`, rồi trả URI đó cho client.

```http
PUT /documents/client-guide
Content-Type: application/json

{"title":"Hướng dẫn vận hành","body":"..."}
```

Client đã xác định URI `/documents/client-guide`. API phải cho phép client quản lý tên này; không phải API nào cũng cần hỗ trợ cách tạo đó.

### 2.2. PUT không tự động có nghĩa là upsert

HTTP cho phép dùng `PUT` để tạo resource tại URI chưa có representation hiện tại. Tuy nhiên, API có thể chỉ hỗ trợ thay thế resource đã tồn tại.

Ví dụ, với `/users/u-42/notification-preferences`:

- Nếu user tồn tại và API cho phép tạo cấu hình khi chưa có: `PUT` có thể tạo cấu hình.
- Nếu API yêu cầu cấu hình phải được khởi tạo bằng một luồng khác: `PUT` không được tự ý tạo.
- Nếu user `u-42` không tồn tại: request không có nghĩa là tự tạo cả user và mọi resource cha còn thiếu.

Hợp đồng phải nói rõ chính sách này. Không suy ra chính sách tạo mới chỉ từ tên phương thức.

## 3. “Thay thế đầy đủ” phải có ranh giới rõ ràng

Một hợp đồng `PUT` tốt xác định đầy đủ phần trạng thái client được phép ghi. Nó không yêu cầu client gửi mọi thuộc tính nội bộ của server.

Với resource cấu hình thông báo, giả sử hợp đồng ghi gồm đúng ba field:

| Field | Kiểu | Bắt buộc | Quy tắc |
| --- | --- | --- | --- |
| `emailEnabled` | boolean | Có | Chỉ nhận `true` hoặc `false` |
| `smsEnabled` | boolean | Có | Chỉ nhận `true` hoặc `false` |
| `digestFrequency` | string | Có | Một trong `OFF`, `DAILY`, `WEEKLY` |

Định danh user lấy từ URI. Các thông tin như phiên bản lưu trữ, thời điểm tạo và người thực hiện được server quản lý. API không cho client tùy ý ghi những thông tin đó.

Việc phân biệt mô hình ghi và mô hình đọc giúp tránh yêu cầu client gửi lại dữ liệu chỉ đọc. Ví dụ response có thể có `updatedAt`, nhưng request thay thế không nhất thiết chứa field đó. Nếu sử dụng OpenAPI, nên biểu diễn ranh giới này bằng schema request/response riêng hoặc khai báo field chỉ đọc phù hợp.

### 3.1. Field bị bỏ qua không được âm thầm mang nghĩa “giữ nguyên”

Request dưới đây không thỏa hợp đồng của ví dụ:

```http
PUT /users/u-42/notification-preferences HTTP/1.1
Content-Type: application/json

{
  "emailEnabled": false
}
```

Server phải từ chối vì thiếu `smsEnabled` và `digestFrequency`. Trong bài này, API dùng `400 Bad Request` cho lỗi validation. Một API khác có thể chọn `422 Unprocessable Content` cho nội dung có cú pháp đúng nhưng không thỏa schema hoặc nghiệp vụ, miễn hợp đồng và cách xử lý nhất quán.

Nếu server giữ hai giá trị cũ rồi chỉ thay `emailEnabled`, endpoint đang áp dụng phép gộp một phần dưới tên `PUT`. Hành vi này làm người đọc hợp đồng khó dự đoán kết quả, nhất là khi có retry hoặc nhiều client cùng sửa.

Đối với field tùy chọn, hợp đồng vẫn phải định nghĩa ý nghĩa của việc bỏ qua: bỏ giá trị, trở về mặc định hay bị từ chối khi thay thế. Không có quy tắc JSON chung rằng mọi field thiếu trong `PUT` đều tự chuyển thành `null`.

### 3.2. Phân biệt thiếu field, null và giá trị rỗng

Ba request sau có ý nghĩa khác nhau về mặt dữ liệu:

```json
{}
```

```json
{"digestFrequency": null}
```

```json
{"digestFrequency": ""}
```

Trong hợp đồng ví dụ, cả ba đều không hợp lệ: field bắt buộc, không nhận `null`, và chuỗi rỗng không thuộc tập giá trị cho phép. Với một resource khác, `null` có thể biểu thị chủ đích xóa giá trị nếu API định nghĩa như vậy.

Trong Java, dùng `Boolean` kết hợp validation cho field bắt buộc giúp phát hiện trường hợp thiếu hoặc `null`. Nếu dùng primitive `boolean`, field vắng mặt có thể trở thành `false` sau deserialize, làm mất khả năng nhận biết request thiếu dữ liệu.

### 3.3. Field không được phép ghi

Ví dụ, client gửi thêm:

```json
{
  "emailEnabled": false,
  "smsEnabled": true,
  "digestFrequency": "OFF",
  "userId": "u-99",
  "role": "ADMIN"
}
```

Server phải bảo đảm `userId` và `role` không thể tác động đến trạng thái được ghi. Chính sách từ chối field lạ hay bỏ qua field lạ cần được tài liệu hóa; ví dụ trong bài chọn từ chối để client phát hiện lỗi sớm.

Không deserialize trực tiếp request vào entity rồi lưu toàn bộ entity. Hãy dùng DTO có danh sách field được phép ghi, xác định user từ URI và kiểm tra quyền của principal đối với user đó.

## 4. Idempotent: lặp lại cùng ý định không nhân đôi tác động mong muốn

`PUT` là phương thức idempotent. Với cùng request hợp lệ, tác động mong muốn lên server khi thực hiện nhiều lần phải tương đương với thực hiện một lần.

Gọi `P(S, R)` là kết quả áp dụng representation `R` lên trạng thái `S`. Với phép thay thế hợp lệ, không có cập nhật xen kẽ và bỏ qua các tác động phụ nội bộ:

```text
P(P(S, R), R) = P(S, R)
```

Nếu gửi hai lần cấu hình `emailEnabled = false`, kết quả vẫn là tắt email. Không có ý nghĩa “đảo trạng thái email thêm một lần”.

### 4.1. Idempotent không yêu cầu response giống hệt nhau

Nếu API cho phép tạo bằng `PUT`:

```text
Lần đầu: PUT /users/u-42/notification-preferences → 201 Created
Lần sau: PUT /users/u-42/notification-preferences → 204 No Content
```

Cả hai đều có thể đưa resource về cùng trạng thái mong muốn. Sự khác nhau giữa mã phản hồi tạo mới và thay thế không làm mất tính idempotent.

Server vẫn có thể ghi log mỗi request hoặc lưu lịch sử xử lý. Tuy nhiên, không nên lợi dụng điều này để thực hiện nghiệp vụ lặp ngoài hợp đồng. Một endpoint `PUT /accounts/a-1/balance` mà mỗi request lại cộng thêm tiền có tác động khác hẳn việc đặt số dư thành một giá trị cụ thể.

### 4.2. Retry khi không nhận được response

Giả sử server đã lưu cấu hình nhưng kết nối bị ngắt trước khi client nhận response. Client chưa biết request đã thành công hay chưa.

Với `PUT`, gửi lại cùng representation tiếp tục diễn đạt cùng trạng thái mong muốn. Đây là lý do tính idempotent hữu ích khi lỗi mạng xảy ra.

Tuy nhiên, retry không đồng nghĩa có thể bỏ qua mọi điều kiện:

- Không retry vô hạn lỗi validation hoặc lỗi quyền truy cập.
- Nếu request có `If-Match`, sau lần ghi đầu tiên phiên bản có thể đã đổi; lần retry có thể nhận `412 Precondition Failed`.
- Nếu có client khác sửa xen kẽ, một `PUT` không điều kiện có thể ghi đè cập nhật của họ.
- Nếu cấu hình kích hoạt gửi thông báo, tạo hóa đơn hoặc phát sự kiện, cần thiết kế riêng để không nhân đôi tác động nghiệp vụ ngoài ý muốn khi retry.

Tính idempotent của phương thức không thay thế kiểm soát đồng thời hay bảo đảm exactly-once cho toàn bộ hệ thống phân tán.

## 5. PUT khác PATCH và POST ở ý định của request

| Tình huống | Phương thức phù hợp thường gặp | Ý nghĩa |
| --- | --- | --- |
| Client có toàn bộ cấu hình mới tại URI đã biết | `PUT` | Tạo hoặc thay thế trạng thái theo hợp đồng |
| Client chỉ muốn sửa một phần cấu hình | `PATCH` | Áp dụng tài liệu thay đổi theo media type quy định |
| Client gửi dữ liệu để server tạo resource và chọn URI | `POST` | Server xử lý nội dung tại resource đích, thường là collection |
| Client yêu cầu thực hiện một hành động nghiệp vụ | Thường dùng `POST` tại resource phù hợp | Ví dụ yêu cầu gửi lại thông báo hoặc khởi động một lần xử lý |

Ví dụ thay thế đầy đủ:

```http
PUT /users/u-42/notification-preferences HTTP/1.1
Content-Type: application/json

{"emailEnabled":false,"smsEnabled":true,"digestFrequency":"OFF"}
```

Ví dụ thay đổi một phần bằng JSON Merge Patch, nếu API hỗ trợ định dạng đó:

```http
PATCH /users/u-42/notification-preferences HTTP/1.1
Content-Type: application/merge-patch+json

{"emailEnabled":false}
```

Trong JSON Merge Patch, field không xuất hiện không bị thay đổi; `null` có ngữ nghĩa loại bỏ thành viên tương ứng của đối tượng. Quy tắc này thuộc định dạng patch, không được áp dụng tùy tiện cho body JSON của `PUT`.

Không phải mọi `PATCH` đều idempotent. Một phép đặt giá trị cố định có thể idempotent, còn một tài liệu thay đổi làm tăng bộ đếm có thể không idempotent. Cũng không nên chọn phương thức chỉ dựa trên tên hàm repository như `save`, `update` hoặc `upsert`.

## 6. Mã trạng thái và hợp đồng phản hồi

### 6.1. Thành công đồng bộ

| Trạng thái trước request | Kết quả | Response phù hợp |
| --- | --- | --- |
| Chưa có resource và API cho phép tạo bằng `PUT` | Đã tạo thành công | `201 Created` |
| Đã có resource | Đã thay thế, trả representation trong body | `200 OK` |
| Đã có resource | Đã thay thế, không trả body | `204 No Content` |

Response tạo mới có thể trả `Location` để xác nhận URI của resource:

```http
HTTP/1.1 201 Created
Location: /users/u-42/notification-preferences
Content-Length: 0
```

Vì request đã hướng tới URI đích, đừng thiết kế `PUT /users/u-42/notification-preferences` như một yêu cầu âm thầm tạo resource chính ở một URI ngẫu nhiên khác. Nếu server cần chọn URI, hãy xem lại thiết kế `POST`.

Response thay thế không có body:

```http
HTTP/1.1 204 No Content
```

Không kèm `{}` hay một thông báo JSON vào response `204`. Nếu cần body, sử dụng `200` và mô tả schema phản hồi.

Nếu chỉ tiếp nhận công việc bất đồng bộ, `202 Accepted` có thể phù hợp. Khi đó, server chưa khẳng định trạng thái resource đã được thay thế xong; hợp đồng cần cho client cách theo dõi kết quả.

### 6.2. Những lỗi cần phân biệt

| Mã | Trường hợp minh họa |
| --- | --- |
| `400 Bad Request` | JSON sai cú pháp hoặc thiếu field bắt buộc theo chính sách của bài |
| `401 Unauthorized` | Chưa có thông tin xác thực hợp lệ |
| `403 Forbidden` | Đã xác thực nhưng không có quyền sửa cấu hình |
| `404 Not Found` | User không tồn tại hoặc API không cho tạo resource cấu hình còn thiếu |
| `405 Method Not Allowed` | URI có resource nhưng không hỗ trợ `PUT`; response phải có `Allow` phù hợp |
| `409 Conflict` | Trạng thái nghiệp vụ hiện tại không cho phép thay thế, ví dụ cấu hình đã bị khóa bởi chính sách tổ chức |
| `412 Precondition Failed` | Điều kiện `If-Match` hoặc `If-None-Match` không thỏa |
| `415 Unsupported Media Type` | Content-Type không được endpoint hỗ trợ |
| `428 Precondition Required` | API yêu cầu điều kiện chống ghi đè nhưng client không gửi |

Một API có thể dùng `404` để không tiết lộ sự tồn tại của resource cho người không có quyền. Lựa chọn này phải nhất quán với chính sách truy cập của hệ thống.

Đừng dùng `409` cho mọi trường hợp lỗi. Nếu client đã cung cấp điều kiện HTTP và điều kiện đó thất bại, `412` diễn đạt chính xác hơn.

## 7. Tránh lost update bằng ETag và If-Match

Thay thế đầy đủ đặc biệt dễ ghi đè dữ liệu khi hai client cùng làm việc.

Ví dụ:

1. A và B cùng đọc cấu hình phiên bản 7.
2. A bật SMS và gửi cấu hình mới thành công.
3. B chỉ định đổi email nhưng gửi lại toàn bộ bản đã đọc từ phiên bản 7.
4. Nếu server chấp nhận vô điều kiện, cấu hình của B có thể tắt SMS trở lại, làm mất thay đổi của A.

Đây là lost update. Một cách xử lý là cho client đọc validator bằng `GET` rồi gửi `If-Match` khi ghi.

### 7.1. Đọc representation cùng validator

```http
GET /users/u-42/notification-preferences HTTP/1.1
Host: api.example.test
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "preferences-7"
Cache-Control: private, no-cache

{"emailEnabled":true,"smsEnabled":false,"digestFrequency":"DAILY"}
```

`ETag` là giá trị opaque do server cấp; client lưu và gửi lại nguyên giá trị, gồm dấu ngoặc kép. Không nên tự suy ra ETag từ ID hoặc tự tăng số phiên bản trong header.

Để dùng cho `If-Match`, cần strong validator. Một weak ETag như `W/"preferences-7"` không thỏa phép so sánh strong của `If-Match`. Nếu server tạo ETag từ version trong database, version đó phải thay đổi khi representation tương ứng thay đổi và phải được thiết kế phù hợp với các biến thể representation được cung cấp.

### 7.2. Thay thế có điều kiện

```http
PUT /users/u-42/notification-preferences HTTP/1.1
Host: api.example.test
Content-Type: application/json
If-Match: "preferences-7"

{"emailEnabled":false,"smsEnabled":true,"digestFrequency":"OFF"}
```

Server chỉ thực hiện thay thế nếu representation hiện tại còn khớp validator đã gửi. Kiểm tra và ghi phải nguyên tử trong tầng lưu trữ; kiểm tra ở controller rồi ghi sau mà không có khóa hoặc điều kiện phiên bản vẫn có race condition.

Nếu A đã cập nhật trước, request của B với validator cũ nhận:

```http
HTTP/1.1 412 Precondition Failed
```

Client nên đọc trạng thái mới và cho người dùng hoặc logic nghiệp vụ quyết định cách kết hợp. Không tự động xóa `If-Match` rồi gửi lại, vì việc đó bỏ chính cơ chế chống mất cập nhật.

### 7.3. Điều kiện “chỉ tạo nếu chưa có”

Khi API cho phép tạo bằng `PUT`, client có thể dùng:

```http
PUT /users/u-42/notification-preferences HTTP/1.1
Content-Type: application/json
If-None-Match: *

{"emailEnabled":true,"smsEnabled":false,"digestFrequency":"DAILY"}
```

Nếu resource chưa có representation hiện tại và các điều kiện khác hợp lệ, server có thể tạo rồi trả `201`. Nếu đã có, điều kiện thất bại và server trả `412`, không thay thế dữ liệu đang tồn tại.

`If-Match: *` lại có ý nghĩa yêu cầu resource đang tồn tại; nó không ràng buộc vào một phiên bản cụ thể nên không bảo vệ khỏi mọi lost update như một ETag cụ thể.

### 7.4. Retry request có điều kiện

Sau một request thành công nhưng mất response, retry cùng `If-Match` cũ có thể nhận `412`. Điều đó không chứng minh lần đầu thất bại.

Client có thể đọc lại resource để xác định trạng thái hiện tại và tiếp tục theo nhu cầu nghiệp vụ. Việc dữ liệu đang giống trạng thái mong muốn chỉ xác nhận trạng thái hiện tại; nó không tự chứng minh chính request trước đó là tác nhân đã ghi. Nếu cần truy vết một lần xử lý cụ thể, phải có cơ chế định danh và lưu kết quả xử lý riêng.

## 8. Phác thảo triển khai bằng Java/Spring

Phần này minh họa ranh giới controller, DTO và thao tác lưu có điều kiện. Đây là các mảnh thiết kế, chưa phải ứng dụng Spring hoàn chỉnh có cấu hình security, persistence và exception handler.

### 8.1. DTO cho trạng thái thay thế

```java
import jakarta.validation.constraints.NotNull;

public record ReplaceNotificationPreferencesRequest(
        @NotNull Boolean emailEnabled,
        @NotNull Boolean smsEnabled,
        @NotNull DigestFrequency digestFrequency
) {
    public enum DigestFrequency {
        OFF, DAILY, WEEKLY
    }
}
```

Khi request được validate, ba field đều phải có giá trị hợp lệ. Giá trị enum không được hỗ trợ phải được xử lý thành lỗi request theo hợp đồng.

DTO này không tự bảo đảm tất cả quy tắc của API. Cần cấu hình bộ đọc JSON để từ chối field không biết nếu hợp đồng chọn chính sách đó; giới hạn kiểu dữ liệu cũng phải được cấu hình phù hợp để không vô tình nhận chuỗi hoặc số thay boolean qua cơ chế ép kiểu. Quyền truy cập, điều kiện HTTP và ràng buộc nghiệp vụ thuộc các bước xử lý khác.

### 8.2. Controller cho nhánh chỉ thay thế resource đã tồn tại

Ví dụ dưới đây chọn chính sách cụ thể: chỉ thay thế cấu hình đã tồn tại và bắt buộc gửi `If-Match`. Nhánh tạo mới đã mô tả ở trên là một lựa chọn hợp đồng khác, không được controller này tự động hỗ trợ.

```java
import jakarta.validation.Valid;
import java.security.Principal;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class NotificationPreferencesController {
    private final NotificationPreferencesService service;

    public NotificationPreferencesController(
            NotificationPreferencesService service) {
        this.service = service;
    }

    @PutMapping(
            path = "/users/{userId}/notification-preferences",
            consumes = "application/json"
    )
    public ResponseEntity<Void> replace(
            @PathVariable("userId") String userId,
            @RequestHeader(value = "If-Match", required = false)
            String ifMatch,
            @Valid @RequestBody
            ReplaceNotificationPreferencesRequest request,
            Principal principal) {

        service.replaceExisting(
                principal, userId, ifMatch, request);

        return ResponseEntity.noContent().build();
    }
}
```

`NotificationPreferencesService` là ranh giới nghiệp vụ cần triển khai. Controller cố ý chuyển cả principal và URI đích xuống service; không tin một `userId` do body cung cấp. Cấu hình security phải yêu cầu xác thực trước khi endpoint được xử lý.

Hợp đồng của `replaceExisting` cần bảo đảm:

1. Principal được quyền sửa cấu hình của `userId`.
2. Resource đích phải tồn tại theo chính sách endpoint.
3. Thiếu `If-Match` được trả thành `428`.
4. Header sai cú pháp được từ chối theo hợp đồng; header hợp lệ được đánh giá đúng ngữ nghĩa HTTP.
5. Representation được thay thế đầy đủ, và kiểm tra điều kiện cùng phép ghi diễn ra nguyên tử.
6. Điều kiện hợp lệ nhưng không còn khớp được trả thành `412`, không ghi dữ liệu.
7. Exception handler chuyển lỗi thành mã HTTP và body lỗi thống nhất, không trả lỗi nghiệp vụ thành `500` một cách mặc định.

Parser `If-Match` phải xét cú pháp thực tế như danh sách entity-tag và dấu `*`. Không nên cài đặt bằng `replace("\"", "")` rồi parse phần còn lại thành số. Các giá trị ETag ở ví dụ chỉ minh họa giao thức, không quy định client hoặc server được bỏ qua cú pháp header.

### 8.3. Ghi đầy đủ bằng điều kiện phiên bản

Sau khi đã phân quyền và ánh xạ validator hợp lệ tới phiên bản hiện tại, một thao tác lưu có thể dùng ý tưởng sau:

```sql
UPDATE notification_preferences
SET email_enabled = :emailEnabled,
    sms_enabled = :smsEnabled,
    digest_frequency = :digestFrequency,
    version = version + 1
WHERE user_id = :userId
  AND version = :expectedVersion;
```

Cả ba field của trạng thái ghi đều nhận giá trị từ request. Không dùng cách gộp “field nào có thì sửa field đó” cho hợp đồng này.

Nếu không cập nhật được hàng nào, lớp persistence/service phải phân loại theo chính sách và thời điểm kiểm tra: resource không có, điều kiện không còn khớp hay xung đột khác. Không tự biến kết quả bằng không thành một lệnh insert, vì endpoint ví dụ chỉ cho phép thay thế resource đã tồn tại.

SQL trên chỉ minh họa nhánh đối chiếu một phiên bản cụ thể. Nhánh `If-Match: *`, nhiều entity-tag hoặc tạo mới bằng `If-None-Match: *` cần được xử lý đúng trước hoặc trong thao tác lưu phù hợp. Với nhánh tạo mới, ràng buộc duy nhất của `user_id` và transaction giúp tránh hai request đồng thời tạo hai cấu hình.

Nếu ghi cấu hình và phát sự kiện là một nghiệp vụ liên kết, cân nhắc lưu sự kiện cùng transaction bằng cơ chế outbox, đồng thời định nghĩa quy tắc khử trùng lặp ở consumer. Chỉ chọn phương thức `PUT` không làm các tác động qua message broker tự trở thành exactly-once.

### 8.4. Cẩn thận khi trả ETag ngay sau PUT

Không nên tự động gắn ETag của trạng thái lưu vào mọi response thành công của `PUT`. HTTP chỉ cho phép trả validator như `ETag` hoặc `Last-Modified` trong response thành công của `PUT` khi dữ liệu representation nhận được được lưu không biến đổi và validator phản ánh representation mới đó.

Nếu server chuẩn hóa JSON, bổ sung field, thay đổi representation hoặc biến đổi nội dung trước khi lưu, phải xem xét điều kiện này. Controller ví dụ trả `204` không có validator; client có thể dùng `GET` tiếp theo để lấy representation chuẩn cùng ETag. Việc response `PUT` không có ETag không làm giảm hiệu lực của điều kiện `If-Match` đã được kiểm tra cho request.

## 9. Cache và các bản sao dữ liệu sau thay thế

Response của `PUT` không được cache theo ngữ nghĩa phương thức. Khi một cache nhận response không lỗi cho một phương thức không an toàn như `PUT`, nó phải vô hiệu hóa các response đã lưu cho URI đích theo quy tắc HTTP caching.

Điều này không có nghĩa mọi dữ liệu liên quan trên hệ thống đều tự làm mới. Ví dụ:

- Danh sách tổng hợp `/users?hasSms=true` có thể chứa thông tin suy ra từ cấu hình vừa đổi.
- Cache trong ứng dụng, Redis hoặc bộ nhớ của frontend có thể không phải HTTP cache.
- Một CDN hoặc cache khác không đi qua đường request ghi có thể không quan sát thấy response `PUT`.

Do đó, thiết kế cần xác định cách invalidation hoặc revalidation cho các bản sao liên quan. Với dữ liệu cấu hình gắn với từng người dùng, chính sách cache còn phải phù hợp với phạm vi truy cập. `Cache-Control: private, no-cache` trong ví dụ `GET` cho phép cache riêng lưu dữ liệu nhưng yêu cầu xác thực lại trước khi tái sử dụng; `no-cache` không có nghĩa là cấm lưu.

## 10. Những tình huống cần kiểm thử

Kiểm thử phải xác nhận hành vi quan sát được từ hợp đồng, không chỉ kiểm tra controller gọi đúng một hàm service.

| Tình huống | Kết quả cần quan sát |
| --- | --- |
| Thay thế cấu hình bằng body đầy đủ và điều kiện còn đúng | Các field ghi có đúng giá trị mới; phản hồi `200` hoặc `204` theo hợp đồng |
| Bỏ một field bắt buộc | Lỗi validation; dữ liệu cũ không bị thay đổi |
| Gửi `null`, enum lạ hoặc kiểu dữ liệu sai | Bị từ chối nhất quán; không ghi một phần |
| Gửi field không được phép như `role` | Bị từ chối theo chính sách ví dụ; không ghi field ngoài hợp đồng |
| Gửi lại cùng body không điều kiện tại endpoint cho phép | Trạng thái mong muốn không bị biến thành phép cộng, đảo giá trị hoặc tạo bản ghi mới |
| Hai client dùng cùng ETag cũ | Chỉ request còn thỏa điều kiện được ghi; request còn lại nhận `412` |
| Thiếu `If-Match` tại endpoint bắt buộc điều kiện | Nhận `428`, không ghi |
| `If-Match` có weak tag, danh sách tag hoặc `*` | Đánh giá đúng cú pháp và phép so sánh tương ứng |
| Client sửa cấu hình của user không thuộc quyền quản lý | Không được ghi dù URI và body hợp lệ |
| Resource không có tại endpoint chỉ cho thay thế | Không tự tạo; trả lỗi đã tài liệu hóa |
| Tạo bằng `PUT` tại endpoint cho phép tạo | URI đúng đích và response `201` |
| Tạo với `If-None-Match: *` khi resource đã có | Nhận `412`, giữ nguyên trạng thái đã tồn tại |
| Response `204` | Không có body |
| Transaction thất bại khi lưu | Không để lại cấu hình chỉ thay được một phần |

Hai nhóm kiểm thử về resource chưa tồn tại phải chạy theo hợp đồng endpoint tương ứng. Không yêu cầu cùng một endpoint vừa cấm tạo vừa phải trả `201` cho cùng điều kiện đầu vào.

Một kiểm thử tích hợp đặc biệt hữu ích là đọc ETag, thực hiện hai request ghi cùng điều kiện và đọc lại resource. Nó xác nhận việc chống lost update thực sự được bảo đảm ở tầng persistence, thay vì chỉ được mô phỏng trong unit test.

## 11. Lỗi thiết kế thường gặp

### Gọi PUT nhưng xử lý như PATCH

Server chỉ cập nhật field có trong JSON và giữ nguyên field còn lại, trong khi tài liệu mô tả thay thế đầy đủ. Cần chọn lại hợp đồng: yêu cầu body đầy đủ cho `PUT`, hoặc cung cấp `PATCH` với định dạng và ngữ nghĩa rõ ràng.

### Ép client gửi lại toàn bộ entity

Client phải gửi cả `createdAt`, cờ nội bộ và khóa cơ sở dữ liệu chỉ để thay cấu hình. Cách này làm lộ mô hình lưu trữ và tăng nguy cơ ghi field ngoài quyền. Hãy xác định resource cùng DTO ghi có ranh giới rõ ràng.

### Dùng tên phương thức để thay thế phân quyền

Biết URI `/users/u-99/notification-preferences` không trao quyền sửa cấu hình của `u-99`. Phải kiểm tra quyền trên resource đích ở mỗi request.

### Cho rằng idempotent thì không có lost update

Hai request riêng biệt đều có thể idempotent nhưng vẫn ghi đè lẫn nhau. Dùng điều kiện phiên bản hoặc cơ chế đồng thời phù hợp nếu cần bảo vệ chỉnh sửa của người khác.

### Chuyển mọi PUT thành upsert trong repository

API nói “chỉ thay thế” nhưng repository tự insert khi không tìm thấy, khiến hợp đồng tạo mới bị thay đổi ngoài ý muốn. Chính sách tồn tại phải được quyết định ở tầng nghiệp vụ và được bảo đảm trong thao tác lưu.

### Dùng PUT cho hành động lặp

Một request có ý nghĩa “gửi thêm một SMS” hay “tăng hạn mức thêm 10” không diễn đạt trạng thái thay thế như ví dụ cấu hình. Hãy mô hình hóa hành động hoặc resource kết quả phù hợp, đồng thời xác định cơ chế retry riêng.

## 12. Tự kiểm tra bằng một quyết định thiết kế

Giả sử màn hình chỉ có một công tắc bật SMS, trong khi resource cấu hình có ba field. Frontend đang giữ dữ liệu được đọc từ vài phút trước.

Nếu frontend gửi `PUT` với cả ba field lấy từ bản cũ, request có thể ghi đè thay đổi email của thiết bị khác. Hai cách thiết kế cần cân nhắc là:

1. Tiếp tục dùng `PUT`, yêu cầu ETag và xử lý `412` khi trạng thái đã đổi. Client phải lấy đủ trạng thái để gửi bản thay thế hợp lệ.
2. Cung cấp `PATCH` cho thay đổi một phần, với media type và điều kiện đồng thời phù hợp. Nếu các field có ràng buộc chéo, patch vẫn phải được validate trên trạng thái kết quả.

Việc giao diện chỉ sửa một field không làm `PUT` tự mang ngữ nghĩa gộp. Lựa chọn phương thức phải nhất quán với ý định request và hợp đồng resource.

Khi thiết kế một endpoint `PUT`, hãy chốt bốn điểm: URI đích đã xác định; phạm vi trạng thái thay thế đã rõ; chính sách tạo mới hoặc chỉ thay thế đã được công bố; và việc ghi đồng thời có cơ chế bảo vệ phù hợp. Từ đó, mã phản hồi, validation và kiểm thử mới có một nền tảng nhất quán.
