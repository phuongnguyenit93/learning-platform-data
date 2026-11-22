# POST để xử lý biểu diễn hoặc tạo tài nguyên trong tập hợp

## Mục tiêu bài học

Trong chương **Phương thức HTTP** của module **INTEGRATION_API_REST**, bài học này giải thích cách dùng POST để yêu cầu một tài nguyên xử lý dữ liệu đầu vào và cách áp dụng ngữ nghĩa đó khi tạo tài nguyên mới trong một tập hợp. Đây là nền tảng để thiết kế REST API dựa trên resource, URI, phương thức HTTP và hợp đồng dữ liệu rõ ràng.

Sau bài học, bạn có thể:

- Phân biệt POST dùng để tạo tài nguyên với POST dùng để thực hiện một xử lý nghiệp vụ.
- Chọn tài nguyên đích, cấu trúc request và mã trạng thái phù hợp.
- Thiết kế phản hồi có `Location`, biểu diễn kết quả hoặc thông tin theo dõi tác vụ.
- Giải thích vì sao retry POST có thể tạo hiệu ứng lặp và cách xây dựng hợp đồng chống trùng.
- Áp dụng các quyết định trên vào một endpoint Java/Spring và các tình huống kiểm thử API.

## 1. Ngữ nghĩa cốt lõi: tài nguyên đích quyết định cách xử lý

POST yêu cầu tài nguyên đích xử lý biểu diễn gửi trong request theo ngữ nghĩa riêng của tài nguyên đó. Biểu diễn thường là JSON, nhưng cũng có thể là dữ liệu biểu mẫu, nội dung văn bản hoặc dữ liệu khác mà endpoint hỗ trợ.

Ví dụ:

```http
POST /orders HTTP/1.1
Host: api.example.com
Content-Type: application/json
Accept: application/json

{
  "items": [
    { "productId": "prd-101", "quantity": 2 }
  ],
  "shippingAddress": "12 Nguyen Trai, TP. Ho Chi Minh"
}
```

Tài nguyên đích của request là tập hợp `/orders`. Hợp đồng của API quy định rằng xử lý biểu diễn này sẽ tạo một đơn hàng mới và thêm đơn hàng đó vào tập hợp.

Điều cần phân biệt là **phương thức POST tự nó không có nghĩa rằng mọi request đều tạo một tài nguyên mới**. Ý nghĩa cụ thể còn phụ thuộc vào tài nguyên đích và hợp đồng của endpoint.

| Request | Tài nguyên đích | Xử lý được hợp đồng quy định |
| --- | --- | --- |
| `POST /orders` | Tập hợp đơn hàng | Tạo một đơn hàng mới |
| `POST /orders/ord-501/cancellations` | Tập hợp yêu cầu hủy của một đơn hàng | Ghi nhận yêu cầu hủy và thực hiện chuyển trạng thái nếu hợp lệ |
| `POST /price-quotes` | Tài nguyên xử lý báo giá | Tính và trả báo giá, có thể không lưu một tài nguyên lâu dài |
| `POST /report-jobs` | Tập hợp tác vụ tạo báo cáo | Tiếp nhận yêu cầu và khởi động xử lý nền |

API cần mô tả rõ dữ liệu nào được nhận, điều kiện nào phải thỏa mãn, trạng thái nào bị thay đổi và kết quả nào được trả về. Tên phương thức không thay thế cho hợp đồng nghiệp vụ.

## 2. POST vào tập hợp để tạo tài nguyên

### 2.1. Tập hợp nhận yêu cầu, tài nguyên thành viên có URI riêng

Một cách thiết kế phổ biến là:

```text
/orders             Tập hợp đơn hàng
/orders/ord-501     Một đơn hàng cụ thể
```

Client gửi thông tin cần thiết để tạo đơn hàng đến `/orders`. Server quyết định mã định danh và URI của đơn hàng mới.

```http
HTTP/1.1 201 Created
Location: https://api.example.com/orders/ord-501
Content-Type: application/json
Cache-Control: no-store

{
  "id": "ord-501",
  "status": "PENDING",
  "items": [
    { "productId": "prd-101", "quantity": 2 }
  ],
  "total": 250000,
  "currency": "VND"
}
```

Ở đây:

- `201 Created` thông báo request đã được thực hiện và tạo tài nguyên mới.
- `Location` chỉ đến đơn hàng mới, giúp client tìm được tài nguyên vừa tạo.
- Body trả về biểu diễn đơn hàng theo hợp đồng của API.
- `Cache-Control: no-store` là lựa chọn của ví dụ vì phản hồi chứa dữ liệu đơn hàng cá nhân.

Client có thể dùng URI từ `Location` cho request tiếp theo:

```http
GET /orders/ord-501 HTTP/1.1
Host: api.example.com
Accept: application/json
```

Với kiểu endpoint tạo tài nguyên này, nên quy định `Location` trong hợp đồng và kiểm thử giá trị của nó. `Location` có thể là URI tuyệt đối hoặc tham chiếu URI tương đối hợp lệ; API nên chọn một quy ước thống nhất. Ví dụ dùng URI tuyệt đối để minh họa rõ đích đến.

### 2.2. Request là dữ liệu tạo mới, không nhất thiết là bản sao resource

Biểu diễn đầu vào có thể khác biểu diễn đầu ra:

| Trường | Request tạo đơn | Response đơn hàng | Ai quyết định? |
| --- | --- | --- | --- |
| `items` | Có | Có | Client chọn sản phẩm và số lượng; server kiểm tra |
| `shippingAddress` | Có | Theo hợp đồng đọc | Client cung cấp, server xác thực |
| `id` | Không | Có | Server sinh |
| `status` | Không | Có | Server áp dụng quy tắc nghiệp vụ |
| `total` | Không | Có | Server tính theo giá và chính sách có hiệu lực |
| `currency` | Theo hợp đồng | Có | Server xác định hoặc kiểm tra theo thị trường |

Không nhận thẳng toàn bộ entity từ request rồi lưu vào cơ sở dữ liệu. Cách đó có thể cho phép client tự đặt trạng thái `PAID`, thay đổi chủ sở hữu hoặc sửa tổng tiền.

Nên tách DTO đầu vào khỏi entity và DTO phản hồi. Nếu cần biết người đặt hàng, server lấy danh tính từ ngữ cảnh xác thực thay vì tin vào một `customerId` bất kỳ trong body.

### 2.3. ID do client cung cấp không tự quyết định phương thức

POST vẫn có thể nhận một mã tham chiếu nghiệp vụ do client cung cấp, chẳng hạn `externalOrderId`. Việc có mã này không tự động làm request trở thành PUT.

Hãy nhìn vào hợp đồng:

- Nếu client gửi yêu cầu đến một tập hợp và server xử lý để tạo thành viên mới, POST thường phù hợp.
- Nếu client chọn chính URI tài nguyên và yêu cầu tạo hoặc thay thế trạng thái tại URI đó theo ngữ nghĩa PUT, hãy cân nhắc PUT.

Ví dụ `POST /orders` có `externalOrderId` vẫn có thể trả về `/orders/ord-501`. API phải nói rõ mã tham chiếu có duy nhất trong phạm vi nào và gửi lại cùng mã sẽ được xử lý ra sao.

## 3. POST để xử lý nghiệp vụ

### 3.1. Không phải mọi xử lý đều cần tạo tài nguyên lâu dài

Một endpoint tính báo giá có thể xử lý dữ liệu và trả kết quả ngay:

```http
POST /price-quotes HTTP/1.1
Host: api.example.com
Content-Type: application/json
Accept: application/json

{
  "items": [
    { "productId": "prd-101", "quantity": 2 }
  ],
  "destinationCity": "Ho Chi Minh"
}
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "subtotal": 250000,
  "shippingFee": 30000,
  "total": 280000,
  "currency": "VND"
}
```

Trong hợp đồng ví dụ này, báo giá chỉ là kết quả xử lý và không có URI để đọc lại. Vì vậy, `200 OK` cùng biểu diễn kết quả phù hợp hơn `201 Created`.

Nếu sản phẩm cần lưu báo giá để người dùng chấp nhận sau đó, API có thể thiết kế báo giá thành tài nguyên có vòng đời riêng. Khi tạo thành công, `201 Created` cùng `Location: /price-quotes/quote-701` trở nên phù hợp.

### 3.2. Biểu diễn một chuyển trạng thái nghiệp vụ

Với việc hủy đơn, có thể mô hình hóa yêu cầu hủy thành tài nguyên:

```http
POST /orders/ord-501/cancellations HTTP/1.1
Host: api.example.com
Content-Type: application/json
Accept: application/json

{
  "reason": "CUSTOMER_REQUEST"
}
```

Nếu server thực sự tạo bản ghi hủy có thể truy xuất, API có thể trả:

```http
HTTP/1.1 201 Created
Location: https://api.example.com/orders/ord-501/cancellations/can-801
Content-Type: application/json

{
  "id": "can-801",
  "orderId": "ord-501",
  "status": "COMPLETED",
  "reason": "CUSTOMER_REQUEST"
}
```

Cần quy định thêm:

- Đơn đang ở trạng thái nào thì được hủy?
- Người gọi có quyền hủy đơn đó không?
- Nếu đã hủy thì trả lại kết quả, từ chối, hay tạo thêm một yêu cầu khác?
- Hoàn tiền đã hoàn tất cùng việc hủy hay còn là bước xử lý riêng?

Một số API chọn URI hành động như `POST /orders/ord-501/cancel`. Khi đó vẫn phải mô tả đầy đủ ngữ nghĩa và kết quả. Mô hình tài nguyên hủy có ích khi cần lịch sử, lý do, người thực hiện và URI theo dõi riêng; tránh tạo một resource giả chỉ để thay cách viết URI.

### 3.3. Xử lý nền và ý nghĩa của 202

Giả sử tạo báo cáo mất vài phút:

```http
POST /report-jobs HTTP/1.1
Host: api.example.com
Content-Type: application/json
Accept: application/json

{
  "reportType": "MONTHLY_SALES",
  "month": "2026-10"
}
```

```http
HTTP/1.1 202 Accepted
Location: https://api.example.com/report-jobs/job-901
Content-Type: application/json

{
  "id": "job-901",
  "status": "QUEUED",
  "statusUrl": "/report-jobs/job-901"
}
```

`202 Accepted` chỉ cho biết yêu cầu đã được chấp nhận để xử lý. Nó không bảo đảm tác vụ nghiệp vụ đã hoàn tất hoặc sau này chắc chắn thành công. Trong ví dụ này, hợp đồng dùng `Location` và `statusUrl` để cung cấp nơi theo dõi; không nên giả định mọi phản hồi 202 của mọi API đều có cơ chế đó.

Endpoint theo dõi cần mô tả các trạng thái như `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, kết quả khi thành công và lỗi khi thất bại. Nếu mục tiêu của request chỉ là tạo bản ghi job và bản ghi đó đã được tạo xong, `201 Created` cũng có thể phù hợp; hãy chọn dựa trên điều API tuyên bố đã hoàn thành và ghi rõ trong hợp đồng.

## 4. Chọn mã trạng thái dựa trên kết quả

| Mã | Khi dùng với POST | Nội dung phản hồi cần cân nhắc |
| --- | --- | --- |
| `201 Created` | Đã tạo tài nguyên mới | URI tài nguyên mới và biểu diễn phù hợp |
| `200 OK` | Đã xử lý thành công và có kết quả để trả | Body mô tả kết quả xử lý |
| `204 No Content` | Đã xử lý thành công và không có nội dung phản hồi | Không gửi body |
| `202 Accepted` | Đã chấp nhận, xử lý nghiệp vụ chưa hoàn tất | Thông tin trạng thái và cơ chế theo dõi theo hợp đồng |
| `303 See Other` | Hướng client tới tài nguyên khác để lấy kết quả qua GET | `Location` của tài nguyên kết quả |

Ví dụ biểu mẫu web thường áp dụng POST rồi chuyển hướng để trình duyệt tải trang kết quả bằng GET. Điều này giảm nguy cơ gửi lại biểu mẫu khi refresh trang. Nó không thay thế cơ chế chống trùng tại server nếu việc gửi POST ban đầu vẫn có thể lặp.

Một số lỗi thường gặp:

| Mã | Tình huống ví dụ |
| --- | --- |
| `400 Bad Request` | JSON hỏng hoặc dữ liệu đầu vào không thỏa hợp đồng được API ánh xạ thành 400 |
| `401 Unauthorized` | Chưa có thông tin xác thực hợp lệ; phản hồi dùng cơ chế challenge phù hợp qua `WWW-Authenticate` |
| `403 Forbidden` | Người gọi đã được nhận diện nhưng không được phép thực hiện thao tác |
| `404 Not Found` | Không tìm thấy tài nguyên đích hoặc tài nguyên liên quan theo chính sách của API |
| `409 Conflict` | Yêu cầu xung đột với trạng thái hiện tại, như hủy đơn đã giao |
| `415 Unsupported Media Type` | Kiểu nội dung request không được endpoint hỗ trợ |
| `422 Unprocessable Content` | Nội dung đã được hiểu nhưng không thể xử lý theo quy tắc mà API chọn ánh xạ thành 422 |
| `429 Too Many Requests` | Vượt giới hạn tần suất được API áp dụng |

Việc chọn 400 hay 422 cho từng loại lỗi cần nhất quán trong toàn API. Không mặc định framework sẽ tự sinh đúng mọi phản hồi nghiệp vụ trong bảng. Endpoint hỗ trợ thương lượng nội dung cũng cần có chính sách rõ khi `Accept` của client không có kiểu phản hồi phù hợp, thường là `406 Not Acceptable`.

Không trả `200 OK` kèm `{ "success": false }` cho mọi lỗi. Client, công cụ quan sát và kiểm thử cần đọc được kết quả ở cả mã HTTP và cấu trúc body.

## 5. POST không safe và không mặc nhiên idempotent

### 5.1. Safe: client có yêu cầu thay đổi trạng thái hay không?

Một phương thức safe có ngữ nghĩa đọc, không yêu cầu thay đổi trạng thái nghiệp vụ. POST không được định nghĩa là safe, vì nó có thể yêu cầu tạo đơn, gửi thông báo hoặc thực hiện thanh toán.

Một endpoint POST cụ thể có thể chỉ tính toán mà không ghi dữ liệu, như báo giá tạm thời. Điều đó không biến POST thành phương thức safe ở cấp giao thức. Nếu chỉ cần đọc dữ liệu và có thể biểu diễn truy vấn phù hợp qua URI, nên xem xét GET để giữ được ngữ nghĩa đọc và các khả năng hỗ trợ tương ứng của HTTP.

### 5.2. Idempotent: gửi lại cùng request có cùng hiệu ứng dự kiến không?

POST không được bảo đảm idempotent theo ngữ nghĩa chung của phương thức. Hai lần gửi cùng body đến `/orders` có thể tạo hai đơn hàng:

```text
POST /orders, body A  -> ord-501
POST /orders, body A  -> ord-502
```

Body giống nhau không đủ để server kết luận hai request là cùng một ý định. Một người dùng hoàn toàn có thể muốn mua cùng các sản phẩm hai lần.

Idempotency liên quan tới **hiệu ứng dự kiến lên trạng thái**, không yêu cầu mọi byte của response đều giống nhau. Một endpoint POST có thể bổ sung hợp đồng chống lặp, nhưng client chỉ được dựa vào bảo đảm mà endpoint công bố.

### 5.3. Timeout tạo ra kết quả chưa biết

```text
Client                         Server
  | POST /orders                  |
  |------------------------------>|
  |                      Tạo ord-501, commit
  |                               |
  |<---- Response bị mất ---------|
  |                               |
  | Timeout: chưa biết kết quả    |
```

Timeout không có nghĩa là server chưa làm gì. Retry ngay có thể tạo thêm đơn, trong khi không retry có thể khiến client bỏ sót đơn đã tồn tại.

Không tự động retry mọi POST chỉ vì gặp timeout, lỗi kết nối hoặc mã 5xx. Client cần hợp đồng chống trùng hoặc một cách tra cứu chắc chắn kết quả của ý định ban đầu.

## 6. Hợp đồng chống trùng với Idempotency-Key

Một lựa chọn phổ biến cho thao tác nhạy cảm là API quy định header `Idempotency-Key`. Các chi tiết như phạm vi key, thời hạn lưu và cách phát lại kết quả phải do hợp đồng của API nêu rõ; không coi header này là một bảo đảm tự có của HTTP hay của Spring.

```http
POST /orders HTTP/1.1
Host: api.example.com
Content-Type: application/json
Accept: application/json
Idempotency-Key: order-submit-7d7c2a

{
  "items": [
    { "productId": "prd-101", "quantity": 2 }
  ],
  "shippingAddress": "12 Nguyen Trai, TP. Ho Chi Minh"
}
```

Ví dụ một hợp đồng cụ thể:

| Tình huống | Cách xử lý đã quy định |
| --- | --- |
| Key chưa xuất hiện trong phạm vi người gọi và endpoint | Tiếp nhận và xử lý một ý định mới |
| Cùng key, cùng dữ liệu, lần đầu đã hoàn tất | Trả lại kết quả đã lưu, không tạo thêm đơn |
| Cùng key, dữ liệu khác | Từ chối với `409 Conflict` và mã lỗi `IDEMPOTENCY_KEY_REUSED` |
| Cùng key, lần đầu đang xử lý | Trả `409 Conflict` với mã `REQUEST_IN_PROGRESS`; hướng dẫn thời điểm thử lại |
| Key đã hết thời gian lưu | Không còn bảo đảm phát lại kết quả cũ; client cần cách đối soát được tài liệu hóa |

Các mã lỗi ở bảng là lựa chọn của API ví dụ. API khác có thể chọn hợp đồng khác, nhưng phải đủ rõ để client không đoán.

### 6.1. Những phần server cần thực hiện

Một thiết kế đáng tin cậy cần:

1. Xác thực và phân quyền người gọi, xác định phạm vi key, chẳng hạn theo tenant, người gọi và loại thao tác.
2. Gắn key với dấu nhận diện dữ liệu có ý nghĩa nghiệp vụ, bao gồm tài nguyên đích khi cần. Phải quy định cách xác định hai payload tương đương; băm chuỗi JSON nguyên trạng sẽ coi khác thứ tự thuộc tính là dữ liệu khác.
3. Giữ chỗ key bằng thao tác nguyên tử hoặc ràng buộc duy nhất, để hai request đồng thời không cùng đi qua bước kiểm tra.
4. Liên kết kết quả tạo đơn với trạng thái xử lý key bằng cơ chế nhất quán. Tránh tình huống đã tạo đơn nhưng mất thông tin nhận diện lần xử lý đó khi tiến trình bị dừng.
5. Lưu đủ thông tin để phát lại response theo hợp đồng, ví dụ status code, `Location` và body.
6. Quy định thời hạn lưu, xử lý trạng thái đang chạy và cách phục hồi khi tiến trình lỗi.

Nếu cùng một cơ sở dữ liệu quản lý đơn hàng và bản ghi key, transaction và ràng buộc duy nhất có thể là phần quan trọng của giải pháp. Nếu thao tác gọi thêm cổng thanh toán hoặc gửi sự kiện, transaction cục bộ không tự bao phủ dịch vụ bên ngoài; cần cơ chế phối hợp và chống trùng tương ứng ở bước đó.

Một `Map` trong bộ nhớ của một instance không đủ để bảo đảm trong hệ thống nhiều instance hoặc sau khi khởi động lại. Cũng không nên tuyên bố thực thi nghiệp vụ “đúng một lần” chỉ vì đã thêm header vào controller.

### 6.2. Trách nhiệm của client

Client tạo key khi bắt đầu một ý định nghiệp vụ và giữ nguyên key cho các lần gửi lại của chính ý định đó. Một đơn hàng mới thực sự phải dùng key mới.

Nếu mỗi lần retry đều sinh key khác thì server nhìn thấy các ý định mới. Nếu tái sử dụng mãi một key cho nhiều lần mua hàng thì server không thể phân biệt đúng yêu cầu của người dùng.

Chống trùng không thay thế phân quyền. Khi phát lại kết quả, server vẫn phải bảo đảm người gọi được xem dữ liệu đó, đặc biệt trong hệ thống nhiều tenant.

## 7. Hợp đồng request và response rõ ràng

### 7.1. Media type và dữ liệu

Với endpoint JSON:

- `Content-Type: application/json` mô tả kiểu nội dung client đang gửi.
- `Accept: application/json` cho biết client mong nhận biểu diễn JSON.
- Schema đầu vào cần có trường bắt buộc, giới hạn số lượng, độ dài và quy tắc xử lý trường không được hỗ trợ.
- Schema đầu ra cần phân biệt các trạng thái nghiệp vụ và giá trị do server tính.

Không dùng GET với body để thay cho mọi thao tác xử lý phức tạp. Nếu chọn POST cho một truy vấn vì dữ liệu đầu vào lớn hoặc có cấu trúc phức tạp, phải mô tả rõ đây là xử lý truy vấn, các tác động nếu có và hạn chế đối với cache hoặc retry.

### 7.2. Lỗi có cấu trúc

Ví dụ API lựa chọn biểu diễn lỗi theo Problem Details, dùng `application/problem+json`:

```http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Không thể hủy đơn hàng",
  "status": 409,
  "detail": "Đơn hàng đã được giao nên không thể hủy theo quy trình này.",
  "instance": "/orders/ord-501/cancellations",
  "code": "ORDER_ALREADY_DELIVERED"
}
```

`code` là trường mở rộng của API ví dụ, giúp client xử lý lỗi ổn định mà không phải phân tích câu chữ trong `detail`. Không trả stack trace, thông tin kết nối cơ sở dữ liệu hoặc dữ liệu nhạy cảm trong thông báo lỗi.

### 7.3. Cache phải được thiết kế có chủ ý

Không giả định response POST sẽ được cache và tái sử dụng như GET. Việc cache phản hồi POST có những điều kiện và giới hạn riêng, đồng thời mức hỗ trợ của các cache có thể khác nhau.

Trong ví dụ đơn hàng có dữ liệu cá nhân, `Cache-Control: no-store` nêu rõ không lưu phản hồi. Nếu muốn client đọc lại tài nguyên và áp dụng chính sách cache có kiểm soát, hãy thiết kế endpoint GET trên URI tài nguyên cùng các header thích hợp. Cache không phải cơ chế chống tạo đơn trùng.

### 7.4. Những thông tin cần ghi trong OpenAPI

Hợp đồng OpenAPI của `POST /orders` nên mô tả ít nhất:

- `requestBody` bắt buộc, media type và schema dữ liệu tạo đơn.
- Cơ chế xác thực, quyền gọi endpoint và cách xác định chủ sở hữu.
- Response thành công: mã trạng thái, schema body, header `Location`.
- Các lỗi có cấu trúc, đặc biệt lỗi dữ liệu, lỗi quyền và xung đột.
- Header chống trùng nếu có, phạm vi key, thời hạn và các trường hợp phát lại hoặc từ chối.
- Giới hạn nghiệp vụ như số dòng hàng tối đa, số lượng mỗi dòng và cách tính giá.

Ví dụ request/response phải khớp với schema. Tài liệu hóa 201 nhưng code luôn trả 200 sẽ làm client sinh tự động và kiểm thử hợp đồng hiểu sai hành vi.

## 8. Minh họa ranh giới HTTP bằng Java/Spring

Đoạn code dưới đây minh họa controller và hợp đồng giữa controller với service. Đây là một phần của ứng dụng Spring MVC có Bean Validation; cần triển khai `OrderService`, persistence, cấu hình bảo mật và ánh xạ lỗi trong ứng dụng thực tế.

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.net.URI;
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderResponse created = orderService.create(request);

        URI location = ServletUriComponentsBuilder
            .fromCurrentRequestUri()
            .pathSegment(created.id())
            .build()
            .toUri();

        return ResponseEntity.created(location).body(created);
    }

    public record CreateOrderRequest(
        @NotEmpty
        @Size(max = 100)
        List<@NotNull @Valid OrderLineRequest> items,

        @NotBlank
        @Size(max = 500)
        String shippingAddress
    ) {}

    public record OrderLineRequest(
        @NotBlank String productId,
        @NotNull @Min(1) @Max(100) Integer quantity
    ) {}

    public record OrderResponse(
        String id,
        String status,
        BigDecimal total,
        String currency
    ) {}

    public interface OrderService {
        OrderResponse create(CreateOrderRequest request);
    }
}
```

Các quyết định quan trọng trong ví dụ:

- Controller nhận DTO tạo mới, không nhận entity để client sửa mọi trường.
- `@Valid` kích hoạt kiểm tra đầu vào khi ứng dụng có thành phần Bean Validation phù hợp.
- `Integer` kết hợp `@NotNull` giúp phân biệt thiếu số lượng với giá trị số được gửi; `@Min` và `@Max` giới hạn số lượng.
- `@NotNull` trên phần tử danh sách ngăn dòng hàng `null`; `@Valid` tiếp tục kiểm tra từng dòng hàng.
- `ResponseEntity.created(location)` trả 201 cùng header `Location`.
- Service phải hoàn tất phần tạo tài nguyên mà hợp đồng cam kết trước khi controller trả 201. Chỉ đưa yêu cầu vào hàng đợi chưa đủ để tuyên bố đơn hàng đã được tạo thành công nếu đơn còn có thể bị từ chối sau đó.

Các validation về cấu trúc không kiểm tra được mọi điều kiện nghiệp vụ. Service vẫn phải kiểm tra sản phẩm tồn tại, quyền đặt hàng, trạng thái khả dụng, giá và tồn kho theo quy tắc của hệ thống. Ràng buộc dữ liệu và transaction giúp xử lý cạnh tranh mà kiểm tra ở controller không giải quyết được.

Ví dụ này chưa triển khai `Idempotency-Key`. Nếu bổ sung, cần đưa thông tin key và danh tính người gọi vào luồng xử lý nghiệp vụ, giữ chỗ nguyên tử và lưu kết quả như phần trước; chỉ thêm một tham số `@RequestHeader` không đủ.

Trong triển khai có reverse proxy, URI tuyệt đối được dựng từ request cần phản ánh đúng địa chỉ công khai của API. Chỉ sử dụng thông tin forwarded từ hạ tầng được tin cậy và cấu hình theo môi trường triển khai, tránh để client tùy ý quyết định host của `Location`.

## 9. Kiểm thử hành vi của endpoint POST

Kiểm thử API cần kiểm tra hiệu ứng nghiệp vụ và hợp đồng HTTP, không chỉ kiểm tra controller trả một con số.

| Nhóm | Kịch bản | Điều cần xác minh |
| --- | --- | --- |
| Tạo mới | Request hợp lệ | Trả 201; đúng một đơn được tạo; ID và dữ liệu phản hồi hợp lệ |
| URI | Theo `Location` sau khi tạo | GET bằng cùng ngữ cảnh có quyền trả đúng đơn vừa tạo |
| Dữ liệu | JSON hỏng, thiếu `items`, số lượng bằng 0, dòng hàng `null` | Trả lỗi theo hợp đồng; không tạo đơn |
| Media type | Gửi loại nội dung không được hỗ trợ | Trả 415 theo hợp đồng |
| Xác thực | Gọi khi chưa xác thực | Trả 401 với challenge phù hợp của cơ chế xác thực |
| Phân quyền | Người gọi không có quyền thực hiện hoặc truy cập tài nguyên | Trả lỗi theo chính sách, thường là 403 hoặc 404 khi cần che giấu sự tồn tại |
| Dữ liệu do server quản lý | Client gửi thêm `status` hoặc tổng tiền | Không cho phép client điều khiển trường ngoài hợp đồng; từ chối hoặc bỏ qua theo chính sách đã công bố |
| Xung đột | Hủy đơn không còn đủ điều kiện | Trả 409 và mã lỗi ổn định; trạng thái đơn không bị chuyển sai |
| Chống trùng | Gửi lại cùng key và dữ liệu sau khi thành công | Không tạo thêm đơn; phát lại kết quả theo hợp đồng |
| Cạnh tranh | Hai request cùng key đến đồng thời | Chỉ một lần thực hiện hiệu ứng tạo đơn; request còn lại được xử lý theo hợp đồng |
| Dùng sai key | Cùng key nhưng body khác | Trả lỗi tái sử dụng key; không tạo đơn thứ hai |
| Xử lý nền | Nhận 202 rồi theo dõi job | Trạng thái cuối phản ánh thành công hoặc thất bại thực tế |

Với luồng chống trùng, nên có kiểm thử tích hợp sử dụng cơ chế lưu trữ thực tế của ứng dụng. Mock một service luôn trả cùng ID không chứng minh rằng ràng buộc đồng thời hoặc phục hồi sau lỗi hoạt động đúng.

## 10. Các lỗi thiết kế thường gặp

### “POST lúc nào cũng trả 201”

POST có thể trả kết quả xử lý, không có nội dung, chấp nhận xử lý nền hoặc chuyển hướng tới kết quả. Chọn mã trạng thái theo điều đã thực sự xảy ra và theo hợp đồng đã công bố.

### “Cùng JSON thì server phải biết là retry”

Hai đơn hàng hợp lệ có thể có nội dung giống hệt nhau. Cần mã nhận diện ý định hoặc ràng buộc nghiệp vụ rõ ràng để phân biệt retry với yêu cầu mới.

### “Đã nhận request thì coi là đặt hàng thành công”

Việc request được tiếp nhận, đơn hàng được tạo và thanh toán thành công là những mốc khác nhau. Response và trạng thái tài nguyên phải phản ánh đúng mốc mà hệ thống đã đạt được.

### “Có @PostMapping là đủ hợp đồng REST”

Annotation chỉ ánh xạ phương thức và đường dẫn. Hợp đồng còn gồm schema, trạng thái, URI tài nguyên, lỗi, quyền, giới hạn và cách retry.

### “POST giấu dữ liệu nên an toàn hơn”

Đưa dữ liệu vào body không tự tạo ra tính bảo mật. API vẫn cần HTTPS, xác thực, phân quyền, giới hạn kích thước request và chính sách ghi log tránh lộ thông tin nhạy cảm.

## 11. Bài thực hành

Thiết kế `POST /orders` cho hệ thống bán hàng với yêu cầu:

1. Nhận danh sách sản phẩm, số lượng và địa chỉ giao hàng; không cho client quyết định giá hoặc trạng thái thanh toán.
2. Tạo đơn ở trạng thái `PENDING`, trả 201, `Location` và biểu diễn tối thiểu của đơn.
3. Mô tả ít nhất một lỗi dữ liệu, một lỗi quyền và một lỗi xung đột bằng mã HTTP cùng body lỗi cụ thể.
4. Bổ sung hợp đồng chống trùng, nêu cách xử lý khi hai request cùng key đến đồng thời và khi key hết thời hạn lưu.
5. Viết các ca kiểm thử để chứng minh retry cùng ý định không sinh thêm đơn và người dùng khác không đọc được kết quả của key đó.

Sau đó, thiết kế thêm `POST /report-jobs` trả 202. Chỉ ra điều gì đã hoàn thành tại thời điểm phản hồi và cách client phân biệt tác vụ thành công với thất bại về sau.

Một thiết kế đạt yêu cầu phải giải thích được ba điểm: tài nguyên đích đang được yêu cầu làm gì, response xác nhận điều gì đã xảy ra, và client được phép làm gì khi chưa biết kết quả của lần gửi trước.
