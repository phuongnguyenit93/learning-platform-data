# Envelope phản hồi và đánh đổi khi bọc mọi kết quả

Trong chương **Biểu diễn dữ liệu** của module **INTEGRATION_API_REST**, bài này xem xét cách thiết kế phần thân phản hồi của REST API: trả trực tiếp biểu diễn tài nguyên hay đặt biểu diễn đó vào một đối tượng bao ngoài, thường gọi là **response envelope**.

Mục tiêu là xây dựng hợp đồng dữ liệu dễ dùng cho client, đồng thời giữ đúng ý nghĩa của resource, URI, phương thức và mã trạng thái HTTP. Những lựa chọn này ảnh hưởng trực tiếp đến phân trang, cache, xác thực, phân quyền, xử lý lỗi, tài liệu OpenAPI và kiểm thử API trong Java/Spring hoặc công nghệ tương đương.

Sau bài học, bạn có thể:

- Phân biệt envelope dữ liệu với thông điệp HTTP và biểu diễn tài nguyên.
- Chọn khi nào trả tài nguyên trực tiếp, khi nào dùng `data`, `meta`, `links`.
- Nhận ra các vấn đề của quy tắc “mọi phản hồi đều có cùng một wrapper”.
- Thiết kế riêng hợp đồng thành công, lỗi, danh sách và phản hồi không có nội dung.
- Triển khai và kiểm thử hợp đồng đã chọn mà không làm mất ngữ nghĩa HTTP.

## 1. Envelope phản hồi là gì?

Giả sử client yêu cầu một đơn hàng:

```http
GET /orders/184 HTTP/1.1
Accept: application/json
```

Một phản hồi trả trực tiếp biểu diễn tài nguyên có thể là:

```http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-184-v7"

{
  "id": 184,
  "status": "CONFIRMED",
  "totalAmount": 420000,
  "currency": "VND"
}
```

Nếu dùng envelope, dữ liệu đơn hàng được đặt vào trường `data`:

```http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-184-v7"

{
  "data": {
    "id": 184,
    "status": "CONFIRMED",
    "totalAmount": 420000,
    "currency": "VND"
  },
  "meta": {
    "schemaVersion": "1"
  }
}
```

Ở đây có ba lớp cần phân biệt:

| Lớp | Vai trò | Ví dụ |
| --- | --- | --- |
| Thông điệp HTTP | Diễn đạt kết quả giao tiếp và điều khiển truyền tải | `200`, `Content-Type`, `ETag`, `Location` |
| Envelope trong body | Tổ chức payload và thông tin bổ trợ theo hợp đồng API | `data`, `meta`, `links` |
| Biểu diễn tài nguyên | Các thuộc tính và liên kết của tài nguyên mà client cần | `id`, `status`, `totalAmount`, `currency` |

Envelope không thay thế HTTP. Một body có `success: false` không làm cho HTTP `200 OK` trở thành lỗi đối với proxy, công cụ giám sát hay client chỉ kiểm tra status.

Ngược lại, HTTP không bắt buộc mọi JSON phải có `data`. Trả trực tiếp tài nguyên không tự động làm API kém REST hơn; thêm envelope cũng không tự động làm API tuân thủ REST hơn.

## 2. Vì sao nhiều API muốn có một envelope chung?

### 2.1. Có chỗ cho metadata ngoài dữ liệu nghiệp vụ

Danh sách đơn hàng có thể cần con trỏ trang tiếp theo hoặc thông tin giới hạn truy vấn. Nếu root JSON là một mảng, việc bổ sung các trường này vào body sẽ phải đổi hình dạng phản hồi.

```json
{
  "data": [
    {
      "id": 184,
      "status": "CONFIRMED"
    },
    {
      "id": 185,
      "status": "SHIPPED"
    }
  ],
  "meta": {
    "pageSize": 2,
    "hasNext": true
  },
  "links": {
    "self": "/orders?limit=2",
    "next": "/orders?limit=2&after=185"
  }
}
```

`meta` mô tả kết quả truy vấn, không phải thuộc tính của từng đơn hàng. Client có thể đọc `data` để hiển thị và đọc `links.next` để chuyển trang.

Liên kết trong ví dụ là URI tương đối; client phân giải theo URI nền phù hợp với hợp đồng API. Trong triển khai thực tế, thứ tự sắp xếp và cấu trúc cursor phải được thiết kế ổn định; `after=185` ở đây chỉ minh họa hình dạng phản hồi.

### 2.2. Giúp quy ước giữa các endpoint dễ đoán hơn

Khi các endpoint đọc danh sách đều dùng `data`, `meta`, `links`, client và SDK có thể chia sẻ một phần xử lý phân trang. Điều này hữu ích khi nhiều nhóm phát triển cùng một API.

Tuy nhiên, quy ước chỉ mang lại giá trị nếu các trường có ý nghĩa ổn định. Nếu `meta` có lúc là thông tin phân trang, có lúc là chi tiết lỗi, có lúc chứa thuộc tính tài nguyên, client vẫn phải suy đoán theo từng endpoint.

### 2.3. Tạo vị trí mở rộng có chủ đích

Một envelope đã tồn tại cho phép thêm thông tin bổ trợ mà không chuyển root JSON từ mảng sang object. Dù vậy, thêm field chỉ tương thích khi client chấp nhận field chưa biết; client dùng bộ kiểm tra schema quá chặt có thể vẫn bị ảnh hưởng.

Envelope tạo ra khả năng mở rộng, không phải lời bảo đảm rằng mọi thay đổi đều tương thích.

## 3. Cái giá của việc bọc mọi kết quả

### 3.1. Thêm cấu trúc nhưng không luôn thêm ý nghĩa

Với một tài nguyên nhỏ, khác biệt giữa `order.id` và `response.data.id` không lớn. Nhưng nếu wrapper chỉ có `data`, không có metadata hay nhu cầu mở rộng cụ thể, lợi ích có thể thấp hơn chi phí duy trì.

Chi phí gồm payload lặp lại, kiểu dữ liệu bổ sung trong SDK, schema OpenAPI dài hơn và lớp chuyển đổi trong client. Với các phản hồi nhỏ được gọi thường xuyên, các trường lặp lại cũng góp phần tăng dữ liệu truyền tải; mức ảnh hưởng cần đo theo lưu lượng thực tế.

### 3.2. Dễ sinh ra hai nguồn sự thật về kết quả

Xem phản hồi sau:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "success": false,
  "code": 404,
  "message": "Không tìm thấy đơn hàng",
  "data": null
}
```

Client phải tự quyết định tin HTTP status hay `code` trong body. Các công cụ dựa vào HTTP có thể ghi nhận đây là request thành công dù ứng dụng đang báo không tìm thấy tài nguyên.

Cách diễn đạt rõ hơn là dùng HTTP `404` và một hợp đồng lỗi đã được tài liệu hóa. Nếu body cần mã lỗi nghiệp vụ, mã đó nên có vai trò riêng, chẳng hạn `ORDER_NOT_FOUND`, thay vì làm bản sao tùy ý của HTTP status.

Một API vẫn có thể đưa `success` vào hợp đồng, nhưng phải xác định tính nhất quán với HTTP và cân nhắc liệu client có thật sự cần thông tin trùng lặp đó không.

### 3.3. Generic wrapper có thể làm hợp đồng yếu đi

Một kiểu Java như sau trông rất tiện:

```java
public record ApiResponse(
    boolean success,
    Object data,
    Object error,
    String message
) {}
```

Nhưng nó cho phép nhiều trạng thái vô nghĩa:

- `success = true` nhưng `error` có giá trị.
- `success = false` nhưng không có chi tiết lỗi.
- `data` vừa là đơn hàng, vừa là chuỗi, vừa là object lỗi tùy endpoint.
- Cả `data` và `error` đều có giá trị nhưng không có quy tắc giải thích.

Dùng `ApiResponse<T>` cải thiện kiểu của `data`, nhưng vẫn cần xác định schema cụ thể cho từng endpoint và quy tắc cho từng loại phản hồi. Một generic trong Java không tự giải quyết hợp đồng JSON, tài liệu OpenAPI hay khả năng tương thích của client.

### 3.4. Wrapper có thể che giấu kiểu biểu diễn thật

Một lớp bọc toàn cục có thể vô tình biến tệp tải xuống, dữ liệu nhị phân, stream hoặc lỗi theo một media type chuyên biệt thành JSON khác cấu trúc. Client đã thương lượng một kiểu dữ liệu nhưng nhận về kiểu khác.

Vì vậy, câu hỏi hữu ích là “loại phản hồi này có cần envelope không?”, thay vì chỉ hỏi “có thể dùng interceptor để bọc tất cả không?”.

## 4. Những phản hồi cần tôn trọng ngữ nghĩa riêng

| Trường hợp | Hợp đồng nên thể hiện | Tác động với envelope |
| --- | --- | --- |
| `GET` tài nguyên thành công | `200` với biểu diễn theo media type đã chọn | Có thể trực tiếp hoặc có envelope |
| `POST` tạo tài nguyên | Thường dùng `201`, trả `Location` khi thích hợp và body đã định nghĩa | Envelope không thay thế `Location` |
| `DELETE` thành công, chọn không trả nội dung | `204 No Content` | Không gửi JSON, kể cả `{"data": null}` |
| `GET` có điều kiện, tài nguyên không đổi | `304 Not Modified`, không có nội dung | Không bọc body; client dùng lại biểu diễn đã cache |
| `HEAD` | Header tương ứng với yêu cầu `GET`, không có nội dung phản hồi | Không chèn envelope vào body |
| Tải tệp | Media type của tệp và header liên quan | Không tự đổi tệp thành JSON envelope |
| Luồng sự kiện hoặc dữ liệu | Định dạng luồng đúng hợp đồng | Envelope JSON thông thường có thể phá định dạng |
| Lỗi HTTP | Status lỗi và schema lỗi tương ứng | Không buộc lỗi phải có cùng schema với dữ liệu thành công |

`204` và `304` không có body nhưng vẫn có thể mang các header được phép và phù hợp với trường hợp cụ thể. “Không có body” không có nghĩa là mọi thông tin bổ trợ đều biến mất.

Ví dụ tạo đơn hàng với envelope:

```http
HTTP/1.1 201 Created
Location: /orders/186
Content-Type: application/json

{
  "data": {
    "id": 186,
    "status": "PENDING",
    "totalAmount": 280000,
    "currency": "VND"
  }
}
```

Ví dụ xóa theo hợp đồng không trả nội dung:

```http
HTTP/1.1 204 No Content
```

Nếu API cần trả thông tin sau thao tác xóa, có thể thiết kế phản hồi `200` với body phù hợp. Không chọn `204` rồi vẫn gửi wrapper để giữ “đồng nhất”.

## 5. Thiết kế ba hợp đồng rõ ràng

Một hướng thực dụng là phân biệt tài nguyên đơn, tập hợp tài nguyên và lỗi. Chúng có thể chia sẻ một số quy ước mà không cần dùng một object cho mọi trường hợp.

### 5.1. Tài nguyên đơn

Hai lựa chọn hợp lệ:

```json
{
  "id": 184,
  "status": "CONFIRMED"
}
```

Hoặc:

```json
{
  "data": {
    "id": 184,
    "status": "CONFIRMED"
  }
}
```

Nếu chọn cách thứ hai, phải nói rõ `data` có bắt buộc không, có thể là `null` không và trường hợp không tìm thấy được biểu diễn thế nào. Trong hợp đồng minh họa của bài này, phản hồi thành công của endpoint tài nguyên đơn có `data` là object khác `null`; không tìm thấy được trả bằng `404`.

Không dùng `200` với `data: null` như một quy tắc chung thay cho `404` cho mọi endpoint tài nguyên đơn. Nếu một truy vấn đặc thù có khái niệm “chưa có giá trị” và trả `null` là hợp lệ, hợp đồng phải mô tả rõ ý nghĩa đó.

### 5.2. Tập hợp tài nguyên

Một truy vấn thành công không có phần tử thường trả `200` với danh sách rỗng:

```json
{
  "data": [],
  "meta": {
    "pageSize": 20,
    "hasNext": false
  },
  "links": {
    "self": "/orders?limit=20",
    "next": null
  }
}
```

Trong hợp đồng này:

- `data` luôn là mảng, không đổi thành `null` hoặc object khi rỗng.
- `pageSize` là số phần tử tối đa được áp dụng cho trang, không phải tổng số kết quả.
- `hasNext` cho biết có trang kế tiếp theo cơ chế phân trang đã định nghĩa.
- `next` là URI hoặc `null` và luôn xuất hiện theo schema đã chọn.
- Không có `totalElements` nếu server không cam kết tính tổng chính xác.

Tính tổng có thể tốn truy vấn hoặc không phù hợp với dữ liệu thay đổi nhanh. Không thêm trường tổng chỉ vì một mẫu envelope luôn có trường đó. Nếu có tổng ước lượng, cần đặt tên và mô tả để client biết đó là ước lượng.

### 5.3. Lỗi

Có thể dùng Problem Details theo RFC 9457 với media type `application/problem+json`:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Không tìm thấy đơn hàng",
  "status": 404,
  "detail": "Không có đơn hàng phù hợp với yêu cầu.",
  "instance": "/orders/184",
  "code": "ORDER_NOT_FOUND",
  "traceId": "a73f8d20"
}
```

`type` định danh loại lỗi; `title` và `detail` cung cấp thông tin để con người hiểu. `status`, khi xuất hiện, phải nhất quán với HTTP status. `code` và `traceId` là các trường mở rộng do API định nghĩa; `traceId` không phải trường bắt buộc của Problem Details.

Client nên xử lý theo status, loại lỗi hoặc mã lỗi ổn định, không phân tích câu tiếng Việt trong `detail` để quyết định luồng nghiệp vụ. Không đưa stack trace, thông tin bí mật hoặc chi tiết nội bộ nhạy cảm vào body lỗi.

Không đặt object này vào `data` rồi tiếp tục gắn media type `application/problem+json`: khi đó các thành phần Problem Details không còn ở vị trí mà client mong đợi. Nếu hệ thống chọn schema lỗi riêng, hãy công bố đúng schema và media type của hợp đồng đó.

## 6. Envelope và các mối quan tâm xuyên suốt

### 6.1. Cache, ETag và metadata thay đổi theo request

Một wrapper tĩnh không tự làm mất khả năng cache. Vấn đề xuất hiện khi mọi lần gọi đều thêm `timestamp` hiện tại hoặc mã request duy nhất vào body.

```json
{
  "data": {
    "id": 184,
    "status": "CONFIRMED"
  },
  "meta": {
    "generatedAt": "2026-01-10T09:30:00Z",
    "requestId": "req-72a"
  }
}
```

Nếu cùng một đơn hàng nhưng body thay đổi ở mỗi request, chiến lược so sánh biểu diễn và tạo ETag phải xét các thay đổi đó. Đặc biệt, không được tuyên bố cùng một strong ETag cho các body khác byte chỉ vì phần `data` giống nhau.

Các hướng thiết kế cần cân nhắc:

- Chỉ đưa timestamp vào body khi đó là thông tin có ý nghĩa đối với biểu diễn.
- Đưa mã đối soát request vào response header nếu nó chỉ phục vụ việc theo dõi request.
- Xác định validator và chính sách cache cho toàn bộ biểu diễn đã chọn.
- Thiết kế cache riêng cho dữ liệu phụ thuộc người dùng, quyền truy cập hoặc nội dung thương lượng.

Chuyển `requestId` sang header có thể giúp body ổn định hơn, nhưng không tự giải quyết quyền riêng tư hay mọi vấn đề cache. `Cache-Control`, `Vary` khi thích hợp và các điều kiện xác thực vẫn cần được thiết kế đúng.

### 6.2. Idempotency và retry

Envelope không tạo ra tính idempotent. Thêm `success: true` hay `requestId` không ngăn một lệnh tạo đơn hàng bị thực hiện hai lần khi client retry.

Với endpoint hỗ trợ idempotency key, server phải quản lý khóa và kết quả nghiệp vụ theo hợp đồng: phạm vi khóa, thời gian lưu, cách xử lý cùng khóa với payload khác và phản hồi khi có request đồng thời. Body trả lại có thể được bọc hoặc không bọc; tính đúng đắn nằm ở cơ chế xử lý thao tác.

Ngoài ra, idempotency không có nghĩa mọi lần gọi đều phải trả body hoặc status giống hệt nhau. Cần phân biệt hiệu ứng lên tài nguyên với chiến lược phát lại phản hồi mà API đã cam kết.

### 6.3. Xác thực và phân quyền

Một envelope thành công không được che mất lỗi xác thực hoặc phân quyền. Ví dụ, dùng `200` với `success: false` cho lỗi xác thực có thể làm SDK và tầng giám sát bỏ qua cơ chế xử lý lỗi HTTP.

Với `401`, phản hồi cần có challenge `WWW-Authenticate` phù hợp. Với `403`, hợp đồng cần diễn đạt việc từ chối truy cập. Nếu hệ thống dùng `404` để hạn chế tiết lộ sự tồn tại của một tài nguyên, chính sách đó phải nhất quán và không bị phá bởi `detail`, `code`, `meta` hay liên kết trong envelope.

Ngoài ra, bọc DTO vào `data` không phải là bước kiểm soát quyền. DTO vẫn chỉ được chứa các field người gọi được phép đọc; liên kết và metadata cũng phải tuân thủ phạm vi truy cập.

## 7. Minh họa trong Java/Spring

Các đoạn mã dưới đây minh họa hợp đồng phản hồi, không phải một ứng dụng hoàn chỉnh. Giả sử tầng dịch vụ xử lý nghiệp vụ, kiểm tra quyền và trả DTO phù hợp; các kiểu `public` được đặt trong tệp Java riêng khi triển khai.

### 7.1. Định nghĩa kiểu dữ liệu có phạm vi rõ

Ví dụ dùng Java hỗ trợ `record`:

```java
public record OrderView(
    long id,
    String status,
    long totalAmount,
    String currency
) {}

public record DataResponse<T>(T data) {}

public record PageMeta(int pageSize, boolean hasNext) {}

public record PageLinks(String self, String next) {}

public record PageResponse<T>(
    java.util.List<T> data,
    PageMeta meta,
    PageLinks links
) {}
```

`totalAmount` ở đây là số tiền theo đơn vị đã công bố trong hợp đồng của ví dụ, tính bằng đồng với `VND`. Một API đa tiền tệ phải định nghĩa chính xác đơn vị và quy tắc làm tròn; envelope không giải quyết những quy tắc dữ liệu nghiệp vụ này.

Các record chỉ thể hiện hình dạng dữ liệu. Chúng không tự bảo đảm `data` khác `null`, danh sách không chứa phần tử `null` hay `pageSize` dương. Những bất biến đó cần được kiểm soát tại nơi tạo đối tượng và mô tả trong schema.

### 7.2. Đặt status và header ở lớp HTTP

Trích đoạn controller có sẵn `orderService`:

```java
import java.net.URI;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@GetMapping("/orders/{id}")
public ResponseEntity<DataResponse<OrderView>> getOrder(
        @PathVariable("id") long id) {
    OrderView order = orderService.getVisibleOrder(id);
    return ResponseEntity.ok(new DataResponse<>(order));
}

@PostMapping("/orders")
public ResponseEntity<DataResponse<OrderView>> createOrder(
        @RequestBody CreateOrderRequest request) {
    OrderView created = orderService.create(request);

    URI location = ServletUriComponentsBuilder.fromCurrentRequest()
        .path("/{id}")
        .buildAndExpand(created.id())
        .toUri();

    return ResponseEntity.created(location)
        .body(new DataResponse<>(created));
}

@DeleteMapping("/orders/{id}")
public ResponseEntity<Void> deleteOrder(
        @PathVariable("id") long id) {
    orderService.deleteVisibleOrder(id);
    return ResponseEntity.noContent().build();
}
```

`CreateOrderRequest`, cơ chế xác thực và phần cài đặt dịch vụ thuộc ứng dụng sử dụng ví dụ. Ở luồng đọc, nếu không có đơn hàng được phép trả về, dịch vụ phát sinh lỗi để lớp xử lý lỗi ánh xạ sang HTTP phù hợp. Không thay đường đi lỗi đó bằng `new DataResponse<>(null)`.

Ví dụ chủ động tạo envelope ở endpoint để người đọc thấy rõ kiểu trả về. Có thể dùng factory hoặc quy ước dùng chung để giảm mã lặp, miễn là schema thực tế vẫn dễ kiểm tra. Khi chạy sau reverse proxy, việc xây dựng URI công khai và cấu hình tin cậy forwarded header cũng cần được thiết kế đúng.

### 7.3. Thận trọng với bọc phản hồi toàn cục

Spring có cơ chế như `ResponseBodyAdvice` để can thiệp trước khi ghi response body. Dùng nó để bọc mọi phản hồi tạo ra các điểm cần xử lý rõ:

- Không bọc lần nữa một body đã là `DataResponse` hoặc `PageResponse`.
- Không thay đổi body lỗi theo Problem Details thành schema thành công.
- Không thêm body cho `204`, `304` hay phản hồi `HEAD`.
- Không áp quy tắc JSON cho tệp, dữ liệu nhị phân hoặc cơ chế streaming.
- Không giả định mọi converter đều xử lý được object envelope; chẳng hạn converter cho chuỗi có thể đã được chọn theo kiểu trả về ban đầu.
- Không để OpenAPI mô tả DTO trực tiếp trong khi runtime trả `{"data": ...}`.

Nếu dự án chọn cách tự động hóa, nên giới hạn phạm vi áp dụng bằng một quy tắc rõ và có kiểm thử cho các đường đi ngoài JSON thông thường. Mục tiêu là giảm mã lặp mà vẫn giữ hợp đồng dễ nhìn thấy và dễ kiểm chứng.

## 8. Mô tả đúng envelope trong OpenAPI

Client code generation cần nhìn thấy schema thực tế. Nếu body có `data`, schema phải có `data`; không chỉ khai báo `Order` vì đó là kiểu nghiệp vụ bên trong.

Ví dụ OpenAPI tối thiểu cho endpoint đọc đơn hàng:

```yaml
openapi: 3.0.3
info:
  title: Orders API
  version: 1.0.0
paths:
  /orders/{id}:
    get:
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
            format: int64
      responses:
        '200':
          description: Đơn hàng được phép truy cập
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '404':
          description: Không có đơn hàng phù hợp
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
components:
  schemas:
    Order:
      type: object
      required: [id, status, totalAmount, currency]
      properties:
        id:
          type: integer
          format: int64
        status:
          type: string
        totalAmount:
          type: integer
          format: int64
          description: Số tiền tính bằng đồng trong hợp đồng VND này
        currency:
          type: string
          enum: [VND]
    OrderResponse:
      type: object
      required: [data]
      properties:
        data:
          $ref: '#/components/schemas/Order'
    Problem:
      type: object
      required: [type, title, status, code]
      properties:
        type:
          type: string
          format: uri
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
        instance:
          type: string
          format: uri-reference
        code:
          type: string
        traceId:
          type: string
```

Schema `Problem` trên là hợp đồng cụ thể của API minh họa: API này yêu cầu `type`, `title`, `status`, `code`. Đây không phải khẳng định rằng RFC bắt buộc mọi phản hồi Problem Details đều có đủ các trường đó.

Tài liệu cho endpoint phân trang cần mô tả riêng `data` là mảng, các field metadata và quy tắc `null` của liên kết. Các phản hồi `204` và `304` không khai báo JSON body để cố tạo một schema chung.

## 9. Chọn envelope theo nhu cầu, không theo khẩu hiệu

| Điều kiện | Lựa chọn đáng cân nhắc | Điểm phải chốt |
| --- | --- | --- |
| Tài nguyên đơn, ít metadata bổ trợ | Trả trực tiếp DTO | Schema tài nguyên và hợp đồng lỗi |
| Nhiều client đã thống nhất đọc `data` | Envelope cho phản hồi JSON thành công | Kiểu cụ thể, quy tắc null và ngoại lệ theo HTTP |
| Danh sách cần phân trang hoặc liên kết | Object chứa `data`, `meta`, `links` | Ý nghĩa kích thước trang, cursor, tổng và liên kết |
| Lỗi cần cấu trúc nhất quán | Schema lỗi riêng, có thể dùng Problem Details | HTTP status, media type và mã lỗi ổn định |
| Tệp, stream hoặc phản hồi không có nội dung | Hợp đồng theo loại phản hồi | Không ép vào wrapper JSON |
| API đang có client hoạt động | Giữ hợp đồng hiện tại hoặc tổ chức migration | Version, lịch hỗ trợ và kiểm tra tương thích |

Một quy ước nhất quán có thể là: “JSON thành công trả tài nguyên đơn dùng `data`; JSON danh sách thêm `meta` và `links`; lỗi dùng Problem Details; phản hồi không có nội dung và tệp theo ngữ nghĩa riêng”. Quy ước này cụ thể hơn câu “mọi thứ đều được bọc”.

Cũng có thể chọn trả tài nguyên đơn trực tiếp và chỉ dùng envelope cho collection. Client xử lý theo schema của endpoint; sự khác nhau có lý do và được công bố không đồng nghĩa với hợp đồng thiếu nhất quán.

## 10. Thay đổi hình dạng phản hồi là thay đổi hợp đồng

Chuyển từ:

```json
{
  "id": 184
}
```

sang:

```json
{
  "data": {
    "id": 184
  }
}
```

làm đường dẫn đọc của client đổi từ `id` thành `data.id`. Đây là thay đổi phá vỡ tương thích dù dữ liệu nghiệp vụ không thay đổi.

Khi cần chuyển đổi:

1. Kiểm kê client và cách chúng giải mã phản hồi.
2. Chọn cơ chế công bố hợp đồng mới, chẳng hạn version mới theo quy ước của API.
3. Cập nhật OpenAPI, SDK và ví dụ cùng với runtime.
4. Duy trì hợp đồng cũ trong thời hạn đã cam kết nếu còn client sử dụng.
5. Kiểm tra tương thích trước khi ngừng hỗ trợ phiên bản cũ.

Không tùy tiện trả lúc có wrapper, lúc không có wrapper trên cùng một endpoint, cùng status và cùng media type chỉ để hỗ trợ hai nhóm client. Nếu hỗ trợ nhiều biểu diễn, cơ chế chọn biểu diễn phải tường minh và cache phải phân biệt đúng biến thể.

## 11. Kiểm thử hợp đồng cần kiểm tra những gì?

Đừng chỉ kiểm tra `response.data != null`. Kiểm thử cần bao gồm cả HTTP lẫn cấu trúc dữ liệu:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Đọc tài nguyên có tồn tại | `200`, đúng media type, `data` là object đúng schema |
| Đọc tài nguyên không có | `404`, đúng schema lỗi và không bị bọc vào schema thành công |
| Tạo tài nguyên | `201`, `Location` hợp lệ và body đúng hợp đồng |
| Xóa với hợp đồng không có nội dung | `204`, body rỗng |
| Danh sách không có kết quả | `200`, `data` là `[]`, metadata và liên kết đúng quy ước |
| Request có điều kiện khớp validator | `304`, không có JSON body |
| `HEAD` | Không có nội dung phản hồi |
| Lỗi xác thực hoặc phân quyền | Status, header cần thiết và dữ liệu lỗi đúng chính sách |
| Tệp hoặc streaming | Media type và định dạng vẫn đúng sau các lớp xử lý chung |
| Sinh SDK từ OpenAPI | Kiểu client khớp body mà server thực sự trả |

Ví dụ trích đoạn kiểm thử với Spring MockMvc, giả sử fixture có đơn hàng `184` và người gọi đã được cấp quyền phù hợp:

```java
mockMvc.perform(get("/orders/184")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.data.id").value(184));

mockMvc.perform(delete("/orders/184"))
    .andExpect(status().isNoContent())
    .andExpect(content().string(""));

mockMvc.perform(get("/orders/999999")
        .accept(MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(status().isNotFound())
    .andExpect(content()
        .contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(jsonPath("$.status").value(404))
    .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
    .andExpect(jsonPath("$.data").doesNotExist());
```

Đây là các đoạn kiểm thử hợp đồng; khi áp dụng cần thiết lập fixture, import và cấu hình bảo mật theo ứng dụng, bao gồm CSRF nếu có. Nếu có bộ bọc tự động, nên chạy các kiểm thử này qua cấu hình MVC thật để phát hiện tương tác với converter và lớp xử lý lỗi.

## 12. Những lỗi thiết kế thường gặp

- **Luôn trả `200` và để client đọc `success`:** làm mất tín hiệu lỗi HTTP đối với các thành phần không đọc body. Trả status phản ánh đúng kết quả.
- **Luôn trả `data: null` khi không có dữ liệu:** làm lẫn danh sách rỗng, tài nguyên không tồn tại và phản hồi không có nội dung. Định nghĩa riêng từng trường hợp.
- **Cho `message` quyết định luồng xử lý:** khiến thay đổi câu chữ hoặc ngôn ngữ làm client hỏng. Dùng mã hoặc loại lỗi ổn định.
- **Bọc lại phản hồi đã có envelope:** tạo `data.data` và làm schema khác tài liệu. Xác định nơi chịu trách nhiệm tạo envelope.
- **Đặt mọi thứ vào `meta`:** biến metadata thành vùng dữ liệu không có schema. Chỉ đưa các trường có tên, kiểu và ý nghĩa rõ ràng.
- **Đưa request ID và thời gian hiện tại vào mọi body:** có thể làm biểu diễn biến đổi liên tục và gây khó cho validator. Chọn vị trí theo nhu cầu sử dụng.
- **Tưởng wrapper là cơ chế bảo mật:** dữ liệu nhạy cảm vẫn có thể lộ trong `data`, `meta`, lỗi và liên kết. Quyền phải được kiểm tra ở đúng luồng xử lý.
- **Đổi wrapper mà không đổi tài liệu:** client sinh từ OpenAPI có thể giải mã sai dù HTTP request thành công. Đồng bộ schema và runtime.

Một envelope có giá trị khi nó tổ chức dữ liệu và metadata theo nhu cầu cụ thể của client. Quyết định tốt cần giữ nguyên ý nghĩa HTTP, mô tả rõ từng hình dạng phản hồi và có bằng chứng kiểm thử rằng hợp đồng thực tế khớp với tài liệu.