# GET, POST, PUT, PATCH và DELETE đúng ngữ nghĩa

HTTP method mô tả ý định của client đối với tài nguyên mà endpoint đại diện. Khi thiết kế REST API, chọn đúng `GET`, `POST`, `PUT`, `PATCH` hay `DELETE` giúp client hiểu cách sử dụng endpoint, proxy và cache xử lý request nhất quán, đồng thời giúp máy chủ áp dụng đúng quy tắc xác thực, phân quyền, kiểm tra dữ liệu và chống gửi lặp.

Trong API Security, ngữ nghĩa HTTP còn là một phần của ranh giới bảo mật. Một endpoint đọc dữ liệu không nên âm thầm thay đổi trạng thái nghiệp vụ; quyền cập nhật không nên được cấp chỉ vì người dùng có quyền xem; và dữ liệu client gửi trong một request không được tự động trở thành mọi thuộc tính của tài nguyên. Vì vậy, cần hiểu method theo hợp đồng HTTP và nghiệp vụ, không chỉ xem chúng là các tên khác nhau của thao tác CRUD.

Sau bài học, người đọc có thể:

- Giải thích mục đích và đặc tính của năm method thường dùng trong REST API.
- Chọn method phù hợp cho thao tác đọc, tạo mới, thay thế, cập nhật một phần và xóa tài nguyên.
- Phân biệt tính an toàn (safe), tính lặp lại không đổi kết quả nghiệp vụ (idempotent) và khả năng cache.
- Thiết kế request, response, status code và xử lý lỗi phù hợp với từng method.
- Áp dụng kiểm soát phân quyền, validation, chống gửi lặp và kiểm soát cập nhật đồng thời cho endpoint.

## 1. HTTP method là một phần của hợp đồng API

Một URI nên xác định tài nguyên hoặc tập tài nguyên, còn method mô tả client muốn thực hiện hành động gì với tài nguyên đó. Ví dụ, `/orders/42` đại diện cho đơn hàng có định danh `42`; method xác định request muốn đọc, thay thế, chỉnh sửa hay xóa đơn hàng.

| Request | Ý nghĩa dự kiến |
|---|---|
| `GET /orders/42` | Lấy biểu diễn của đơn hàng 42 |
| `POST /orders` | Gửi yêu cầu tạo đơn hàng mới trong collection orders |
| `PUT /orders/42` | Tạo hoặc thay thế biểu diễn tại URI đơn hàng 42, theo hợp đồng API |
| `PATCH /orders/42` | Áp dụng các thay đổi được mô tả trong patch document lên đơn hàng 42 |
| `DELETE /orders/42` | Yêu cầu xóa hoặc gỡ bỏ đơn hàng 42 khỏi phạm vi tài nguyên được quản lý |

REST không bắt buộc mọi hệ thống phải có đúng một endpoint cho mỗi method, nhưng endpoint nên giữ ngữ nghĩa nhất quán. Dùng danh từ cho tài nguyên như `/orders`, `/users/17` và `/products/sku-1`; dùng method để thể hiện thao tác. Những hành động nghiệp vụ đặc thù như duyệt đơn, hoàn tiền hoặc khóa tài khoản có thể được mô hình hóa thành tài nguyên/command riêng, miễn là hợp đồng rõ ràng và có kiểm tra quyền tương ứng.

Không nên chọn method chỉ dựa trên tên hàm trong code. Ví dụ, một endpoint tên `/orders/42/cancel` có thể được thiết kế như một command `POST` vì nó yêu cầu thực hiện một chuyển trạng thái nghiệp vụ; nếu hệ thống biểu diễn việc hủy như cập nhật thuộc tính trạng thái của tài nguyên thì có thể dùng `PATCH`. Điều quan trọng là hợp đồng phải mô tả rõ kết quả, điều kiện hợp lệ, khả năng gửi lại và quyền cần thiết.

## 2. Ba đặc tính cần hiểu: safe, idempotent và cacheable

Các method có những đặc tính giao thức giúp client và hạ tầng HTTP xử lý request đúng cách.

### 2.1. Safe — không yêu cầu thay đổi trạng thái tài nguyên

Method được xem là *safe* khi client chỉ yêu cầu đọc hoặc quan sát tài nguyên, không yêu cầu máy chủ thực hiện thay đổi trạng thái nghiệp vụ. `GET` là safe. `HEAD` cũng safe, dù không thuộc năm method chính của bài này.

Safe không có nghĩa máy chủ không thực hiện bất kỳ hoạt động nội bộ nào. Ghi access log, tăng bộ đếm giám sát hoặc cập nhật cache không phải là thay đổi nghiệp vụ mà client yêu cầu. Tuy nhiên, `GET` không được dùng để chuyển tiền, xóa dữ liệu, gửi email, tạo đơn hàng hoặc thay đổi trạng thái tài khoản. Các thao tác như vậy có thể bị kích hoạt bởi crawler, prefetch của trình duyệt, proxy hoặc hệ thống giám sát khi chúng tưởng rằng chỉ đang đọc dữ liệu.

### 2.2. Idempotent — gửi lặp có cùng hiệu ứng nghiệp vụ

Một method là *idempotent* nếu thực hiện cùng một request một lần hay nhiều lần có cùng hiệu ứng dự kiến trên trạng thái tài nguyên ở máy chủ. `GET`, `PUT` và `DELETE` có tính idempotent theo ngữ nghĩa HTTP. `POST` không được bảo đảm idempotent; `PATCH` cũng không mặc nhiên idempotent.

Idempotent không có nghĩa mọi response phải giống hệt nhau. Ví dụ, lần đầu `DELETE /orders/42` có thể trả `204 No Content`, lần tiếp theo có thể trả `404 Not Found`; trạng thái cuối cùng vẫn là tài nguyên đã không còn tồn tại. Tương tự, một `PUT` lặp lại có thể tạo response khác nhau về thời điểm hoặc metadata, nhưng biểu diễn đích vẫn được đặt về cùng giá trị mà request yêu cầu.

Tính idempotent rất quan trọng khi client không biết request đã tới máy chủ hay chưa. Nếu kết nối bị ngắt sau khi gửi, client có thể cần thử lại. Với thao tác không idempotent như tạo thanh toán hoặc gửi lệnh tạo đơn, cần cơ chế chống xử lý trùng, chẳng hạn idempotency key.

### 2.3. Cacheable — có thể lưu response để tái sử dụng

`GET` là method thường được cache. Khả năng cache thực tế còn phụ thuộc status code, header như `Cache-Control`, `ETag`, `Last-Modified`, `Vary`, cấu hình cache và tính riêng tư của dữ liệu. `POST` chỉ cache được trong những điều kiện cụ thể và ít phổ biến hơn. Không nên mặc định cache response chứa dữ liệu riêng tư.

| Method | Safe | Idempotent | Cache theo ngữ nghĩa HTTP |
|---|---|---|---|
| `GET` | Có | Có | Có thể cache |
| `POST` | Không | Không được bảo đảm | Chỉ trong điều kiện cụ thể |
| `PUT` | Không | Có | Không cache response PUT |
| `PATCH` | Không | Không được bảo đảm | Không cache response PATCH theo mặc định; có thể có điều kiện riêng |
| `DELETE` | Không | Có | Không cache response DELETE |

Các đặc tính này là đặc tính ngữ nghĩa của method, không phải lời khẳng định rằng mọi triển khai đều tự động an toàn. Ứng dụng vẫn phải xác thực, phân quyền và kiểm soát dữ liệu trên từng request.

## 3. GET — đọc biểu diễn của tài nguyên

`GET` yêu cầu máy chủ trả về biểu diễn hiện tại của tài nguyên hoặc tập tài nguyên. Ví dụ:

```http
GET /api/orders/42 HTTP/1.1
Host: shop.example.com
Accept: application/json
Authorization: Bearer <access-token>
```

Response thành công thường có dạng:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "id": "42",
  "status": "PROCESSING",
  "total": 1250000,
  "currency": "VND"
}
```

### 3.1. Dùng GET cho truy vấn, bộ lọc và phân trang

Các tham số lọc, sắp xếp và phân trang thường đặt trong query string:

```http
GET /api/orders?status=PROCESSING&page=0&size=20&sort=createdAt,desc
```

Query string nên thể hiện điều kiện đọc và có giới hạn hợp lý. Máy chủ cần giới hạn `size`, số điều kiện lọc, độ phức tạp truy vấn và thời gian thực thi để tránh một request đọc gây cạn tài nguyên. Với dữ liệu lớn hoặc thay đổi liên tục, cursor pagination có thể ổn định hơn offset pagination.

GET không nên dùng request body để truyền bộ lọc. Nội dung body của GET không có ngữ nghĩa chung được các hệ thống trung gian hỗ trợ nhất quán. Nếu truy vấn phức tạp đến mức cần body, cân nhắc thiết kế endpoint tìm kiếm bằng `POST` với hợp đồng chỉ đọc được mô tả rõ, hoặc đơn giản hóa tiêu chí truy vấn.

### 3.2. GET phải giữ tính safe

Không dùng GET cho hành động làm thay đổi trạng thái nghiệp vụ. Những thiết kế sau là nguy hiểm:

```http
GET /api/orders/42/cancel
GET /api/users/17/enable
GET /api/payments/99/refund
```

Các URL này có thể bị gọi ngoài ý muốn bởi crawler, link preview, browser prefetch hoặc công cụ quét. Hãy dùng method không safe phù hợp, chẳng hạn `POST` cho command hủy/hoàn tiền hoặc `PATCH` khi cập nhật biểu diễn trạng thái theo hợp đồng.

### 3.3. Bảo vệ dữ liệu GET

GET vẫn cần xác thực và phân quyền. Người gọi có quyền `order:read` vẫn chỉ được xem các đơn hàng thuộc phạm vi của họ. Kiểm tra quyền trên đối tượng phải được thực hiện cho từng ID, kể cả ID nằm trong query hoặc đường dẫn lồng nhau.

Không đưa access token, API key hoặc dữ liệu bí mật vào URL vì URL thường xuất hiện trong browser history, access log, proxy log và hệ thống phân tích. Query parameter có thể chứa dữ liệu cá nhân hoặc thông tin nhạy cảm; nếu không cần cho việc chia sẻ URL, hãy cân nhắc dùng request body của một endpoint tìm kiếm phù hợp hoặc cơ chế khác.

Với response riêng tư, cấu hình cache rõ ràng, ví dụ `Cache-Control: private, no-store` khi không muốn lưu bản sao ở cache. Có thể dùng `ETag` và `If-None-Match` để hỗ trợ cache/điều kiện đọc cho dữ liệu được phép cache. Khi representation chưa thay đổi, máy chủ có thể trả `304 Not Modified` mà không gửi lại body.

Status code thường gặp:

- `200 OK`: đọc thành công và có biểu diễn trong response.
- `206 Partial Content`: trả một phần nội dung theo cơ chế range, thường dùng với tải tệp.
- `304 Not Modified`: biểu diễn chưa thay đổi theo điều kiện cache; không có response body.
- `401 Unauthorized`: thiếu hoặc không hợp lệ thông tin xác thực.
- `403 Forbidden`: đã xác thực nhưng không được phép truy cập theo chính sách.
- `404 Not Found`: tài nguyên không tồn tại hoặc hệ thống chủ động che giấu sự tồn tại của tài nguyên mà người gọi không được truy cập.

## 4. POST — gửi dữ liệu để xử lý hoặc tạo tài nguyên

`POST` yêu cầu tài nguyên đích xử lý nội dung được gửi kèm theo ngữ nghĩa do tài nguyên đó định nghĩa. Một cách dùng phổ biến là gửi dữ liệu để tạo tài nguyên mới trong collection:

```http
POST /api/orders HTTP/1.1
Host: shop.example.com
Content-Type: application/json
Accept: application/json
Authorization: Bearer <access-token>

{
  "items": [
    { "productId": "P-100", "quantity": 2 }
  ],
  "deliveryAddressId": "ADDR-8"
}
```

Nếu tạo đơn hàng thành công, máy chủ thường trả `201 Created`, header `Location` trỏ tới tài nguyên mới và có thể trả representation:

```http
HTTP/1.1 201 Created
Location: /api/orders/42
Content-Type: application/json

{
  "id": "42",
  "status": "CREATED",
  "total": 1250000
}
```

### 4.1. POST không chỉ dành cho thao tác tạo

POST cũng phù hợp khi gửi một yêu cầu xử lý tới tài nguyên, chẳng hạn chạy tìm kiếm phức tạp, tạo báo cáo hoặc thực hiện command nghiệp vụ. Khi đó, cần mô tả rõ endpoint nhận dữ liệu gì, tạo ra tác động nào và kết quả được truy xuất ở đâu. Nếu công việc kéo dài, có thể trả `202 Accepted` cùng URL trạng thái của tác vụ; `202` chỉ cho biết request đã được chấp nhận để xử lý, không khẳng định công việc đã hoàn tất.

### 4.2. POST thường không idempotent: chống tạo trùng

Nếu client gửi `POST /orders` hai lần, máy chủ có thể tạo hai đơn hàng. Việc tự động retry khi timeout vì thế có thể tạo dữ liệu hoặc giao dịch trùng lặp.

Với thao tác quan trọng, API có thể hỗ trợ `Idempotency-Key`:

```http
POST /api/payments HTTP/1.1
Idempotency-Key: 8c7e0b7d-5e9f-4c1d-9a9a-5a12b9f43a01
Content-Type: application/json

{
  "orderId": "42",
  "amount": 1250000,
  "currency": "VND"
}
```

Máy chủ lưu kết quả xử lý gắn với key trong một khoảng thời gian và bảo đảm các request lặp cùng key không tạo tác động trùng. Thiết kế cần quy định phạm vi key theo người gọi/tenant, thời hạn lưu, xử lý request đồng thời và hành vi khi cùng key được gửi với payload khác. Idempotency key không thay thế xác thực, phân quyền hoặc kiểm tra tính hợp lệ của giao dịch.

### 4.3. Kiểm soát dữ liệu và quyền khi POST

Không bind trực tiếp toàn bộ JSON vào entity rồi lưu. Chỉ nhận các trường mà client được phép cung cấp. Ví dụ, client có thể gửi `productId`, `quantity` và `deliveryAddressId`; máy chủ tự xác định `customerId`, giá có thẩm quyền, trạng thái ban đầu và tenant từ ngữ cảnh đáng tin cậy.

Phân quyền phải kiểm tra cả chức năng tạo và các đối tượng được tham chiếu. Người dùng có thể có quyền `order:create` nhưng không được đặt hàng thay khách hàng khác hoặc dùng địa chỉ giao hàng thuộc tài khoản khác. Kiểm tra giá, tồn kho, giới hạn số lượng và trạng thái sản phẩm ở phía máy chủ.

Status code thường gặp:

- `201 Created`: tạo tài nguyên thành công.
- `202 Accepted`: đã nhận yêu cầu xử lý bất đồng bộ, kết quả chưa hoàn tất.
- `200 OK`: xử lý thành công và có representation kết quả.
- `204 No Content`: xử lý thành công nhưng không trả body.
- `400 Bad Request`: request sai cú pháp hoặc dữ liệu không hợp lệ theo hợp đồng.
- `401 Unauthorized` / `403 Forbidden`: xác thực hoặc phân quyền thất bại.
- `409 Conflict`: xung đột với trạng thái hiện tại hoặc ràng buộc nghiệp vụ.
- `422 Unprocessable Content`: cú pháp và kiểu nội dung được hiểu nhưng không thể xử lý theo quy tắc nội dung/nghiệp vụ của API.
- `429 Too Many Requests`: vượt giới hạn tần suất hoặc quota.

## 5. PUT — tạo hoặc thay thế biểu diễn tại URI đích

`PUT` yêu cầu máy chủ tạo hoặc thay thế trạng thái của tài nguyên được xác định bởi URI đích bằng biểu diễn mà request cung cấp, theo hợp đồng của API. Ví dụ:

```http
PUT /api/users/17/preferences HTTP/1.1
Content-Type: application/json
Authorization: Bearer <access-token>

{
  "language": "vi",
  "timeZone": "Asia/Ho_Chi_Minh",
  "marketingEmails": false
}
```

Trong ví dụ, request thể hiện toàn bộ representation của tài nguyên preferences. Nếu trường được quản lý bởi representation bị bỏ qua, API phải định nghĩa rõ đó là giá trị mặc định, giá trị rỗng hay lỗi validation; không để client phải đoán.

### 5.1. PUT thường là thay thế toàn bộ representation

Khác với PATCH, PUT thường biểu đạt việc đặt representation của tài nguyên về nội dung được gửi. Nếu client chỉ muốn thay đổi một trường, gửi PUT với một body thiếu các trường còn lại có thể làm các trường đó bị xóa hoặc đặt về mặc định. Đây là nguyên nhân phổ biến gây mất dữ liệu khi client hiểu PUT như cập nhật một phần.

Một số API dùng PUT để tạo tài nguyên tại URI do client chọn, nếu tài nguyên chưa tồn tại và chính sách cho phép. Khi URI do server cấp phát, POST lên collection thường tự nhiên hơn. Dù chọn cách nào, response và hành vi khi tài nguyên đã tồn tại/chưa tồn tại phải được tài liệu hóa.

### 5.2. PUT có tính idempotent

Gửi cùng một PUT nhiều lần phải đưa tài nguyên đích về cùng trạng thái mong muốn. Ví dụ, PUT cùng representation preferences hai lần không được tạo hai tài nguyên preferences hoặc lặp lại một tác động nghiệp vụ như gửi hai email.

PUT không phải safe vì nó yêu cầu thay đổi trạng thái. Một endpoint PUT vẫn cần quyền cập nhật tài nguyên và validation đầy đủ. Tính idempotent cũng không miễn trừ việc xử lý xung đột khi nhiều client cập nhật cùng một tài nguyên.

### 5.3. Kiểm soát cập nhật đồng thời bằng điều kiện

Giả sử hai client cùng đọc phiên bản preferences ETag `"v7"`. Client A cập nhật ngôn ngữ, client B cập nhật múi giờ. Nếu cả hai ghi toàn bộ representation mà không kiểm soát phiên bản, request sau có thể ghi đè thay đổi của request trước.

Client có thể gửi `If-Match` để chỉ cập nhật khi representation vẫn là phiên bản đã đọc:

```http
PUT /api/users/17/preferences HTTP/1.1
If-Match: "v7"
Content-Type: application/json

{
  "language": "vi",
  "timeZone": "Asia/Ho_Chi_Minh",
  "marketingEmails": false
}
```

Nếu ETag không còn khớp, máy chủ trả `412 Precondition Failed` để client tải phiên bản mới và xử lý xung đột. Có thể dùng `409 Conflict` cho các xung đột nghiệp vụ khác. Kiểm tra điều kiện và ghi dữ liệu cần được thực hiện an toàn trước race condition.

Status code thường gặp:

- `200 OK`: thay thế thành công và trả representation.
- `204 No Content`: thay thế thành công, không trả body.
- `201 Created`: tài nguyên mới được tạo tại URI đích.
- `400 Bad Request` / `422 Unprocessable Content`: representation không hợp lệ.
- `401 Unauthorized` / `403 Forbidden`: không đủ xác thực hoặc quyền cập nhật.
- `404 Not Found`: tài nguyên đích không tồn tại và API không hỗ trợ tạo bằng PUT.
- `409 Conflict`: xung đột với trạng thái hoặc quy tắc nghiệp vụ.
- `412 Precondition Failed`: điều kiện như `If-Match` không thỏa mãn.

## 6. PATCH — áp dụng thay đổi một phần

`PATCH` yêu cầu máy chủ áp dụng một tập thay đổi lên tài nguyên hiện tại. Khác với PUT, body PATCH thường mô tả những thay đổi cần thực hiện thay vì toàn bộ representation.

Ví dụ, client chỉ muốn đổi ghi chú giao hàng:

```http
PATCH /api/orders/42 HTTP/1.1
Content-Type: application/merge-patch+json
Authorization: Bearer <access-token>

{
  "deliveryNote": "Giao tại quầy lễ tân"
}
```

API cần công bố rõ định dạng patch được hỗ trợ. Hai định dạng thường gặp là:

- **JSON Merge Patch** (`application/merge-patch+json`, RFC 7396): object trong body được hợp nhất với target; thuộc tính có giá trị `null` thường mang nghĩa xóa thuộc tính. Mảng thường được thay thế toàn bộ, không tự động hợp nhất từng phần tử.
- **JSON Patch** (`application/json-patch+json`, RFC 6902): một danh sách thao tác có thứ tự như `add`, `remove`, `replace`, `move`, `copy`, `test`, mỗi thao tác chỉ rõ đường dẫn trong JSON document.

Ví dụ JSON Patch:

```http
PATCH /api/users/17/preferences HTTP/1.1
Content-Type: application/json-patch+json

[
  { "op": "replace", "path": "/language", "value": "vi" },
  { "op": "replace", "path": "/marketingEmails", "value": false }
]
```

Không nên nhận patch document tùy ý rồi áp dụng trực tiếp lên entity. Máy chủ phải allowlist đường dẫn/thuộc tính được phép thay đổi, kiểm tra kiểu và giá trị, xác minh quyền trên từng thuộc tính, đồng thời từ chối các trường như `ownerId`, `tenantId`, `role`, `price` hoặc `approvalStatus` nếu caller không có quyền đặc biệt.

### 6.1. PATCH không mặc nhiên idempotent

Một patch kiểu `replace /status = "CANCELLED"` có thể idempotent nếu thực hiện nhiều lần vẫn đưa tài nguyên về cùng trạng thái. Ngược lại, patch kiểu tăng số lượng thêm một đơn vị hoặc thêm phần tử vào cuối mảng có thể tạo hiệu ứng khác nhau mỗi lần gửi. Do đó, không thể giả định mọi PATCH đều an toàn để retry.

Với patch cần chống cập nhật lặp hoặc xung đột, có thể dùng idempotency key theo hợp đồng riêng và điều kiện `If-Match`/ETag. Máy chủ nên quy định patch được áp dụng nguyên tử: nếu một thao tác trong patch document thất bại thì không để lại trạng thái nửa chừng, trừ khi hợp đồng nêu rõ một cơ chế khác.

### 6.2. PATCH và kiểm tra quy tắc nghiệp vụ

Validation không chỉ kiểm tra từng trường riêng lẻ. Ví dụ, đổi `deliveryAddressId` phải kiểm tra địa chỉ thuộc người dùng; đổi `quantity` phải kiểm tra tồn kho; chuyển `status` phải tuân theo state machine của đơn hàng. Một trường có thể hợp lệ về kiểu nhưng không hợp lệ trong trạng thái hiện tại.

Status code thường gặp:

- `200 OK`: cập nhật thành công và trả representation mới.
- `204 No Content`: cập nhật thành công, không trả body.
- `400 Bad Request` / `422 Unprocessable Content`: patch document hoặc giá trị không hợp lệ.
- `404 Not Found`: tài nguyên đích không tồn tại hoặc bị che giấu theo chính sách.
- `409 Conflict`: patch xung đột với trạng thái hoặc quy tắc nghiệp vụ.
- `412 Precondition Failed`: điều kiện phiên bản như `If-Match` không thỏa mãn.
- `415 Unsupported Media Type`: định dạng patch không được hỗ trợ.

## 7. DELETE — yêu cầu xóa tài nguyên

`DELETE` yêu cầu máy chủ xóa liên kết giữa URI đích và chức năng hiện tại của nó, theo mô hình tài nguyên của hệ thống. Ví dụ:

```http
DELETE /api/orders/42 HTTP/1.1
Host: shop.example.com
Authorization: Bearer <access-token>
```

Xóa trong nghiệp vụ không nhất thiết là xóa vật lý ngay khỏi cơ sở dữ liệu. Hệ thống có thể dùng soft delete, đánh dấu hủy, ẩn khỏi collection hoặc đưa vào quy trình lưu trữ/retention. API cần diễn đạt chính xác kết quả và bảo đảm các endpoint khác không tiếp tục cho truy cập tài nguyên đã bị xóa theo chính sách.

### 7.1. DELETE có tính idempotent

Gửi cùng một DELETE nhiều lần phải có cùng hiệu ứng cuối: tài nguyên không còn khả dụng tại URI đó. Response có thể khác nhau giữa lần đầu và lần sau. Ví dụ, lần đầu trả `204 No Content`, lần sau trả `404 Not Found`; điều này không làm mất tính idempotent.

DELETE không safe vì nó yêu cầu thay đổi trạng thái. Không bao giờ thực hiện xóa qua GET. DELETE thường không cần request body; ý nghĩa của body trong DELETE không được các hệ thống trung gian hỗ trợ nhất quán. Nếu cần truyền nhiều điều kiện hoặc một tập ID phức tạp, cân nhắc thiết kế endpoint command/batch bằng POST với hợp đồng rõ ràng.

### 7.2. Phân quyền và quy tắc xóa

Quyền xóa thường có tác động lớn hơn quyền đọc. Kiểm tra quyền trên chức năng và từng đối tượng; xác minh caller thuộc đúng tenant/owner; kiểm tra quan hệ phụ thuộc, trạng thái, retention và yêu cầu audit. Với dữ liệu tài chính hoặc dữ liệu cần lưu trữ theo quy định, thao tác xóa có thể phải bị cấm hoặc chuyển thành quy trình ẩn danh hóa/lưu trữ có kiểm soát.

Để tránh xóa nhầm phiên bản mới, có thể yêu cầu `If-Match` với ETag. Nếu tài nguyên đã thay đổi kể từ lúc client đọc, trả `412 Precondition Failed`. Với xóa bất đồng bộ hoặc công việc chưa hoàn tất, `202 Accepted` có thể phù hợp; với xóa hoàn tất không có body, `204 No Content` thường được dùng; `200 OK` phù hợp khi trả representation hoặc kết quả xử lý.

Status code thường gặp:

- `204 No Content`: xóa thành công, không có body.
- `200 OK`: xóa thành công và trả kết quả/representation.
- `202 Accepted`: yêu cầu xóa đã được nhận nhưng xử lý chưa hoàn tất.
- `404 Not Found`: tài nguyên không tồn tại hoặc không được tiết lộ.
- `409 Conflict`: không thể xóa do trạng thái hoặc ràng buộc nghiệp vụ.
- `412 Precondition Failed`: điều kiện phiên bản không thỏa mãn.

## 8. Chọn method cho các tình huống thường gặp

Bảng dưới đây là gợi ý thiết kế phổ biến. Quyết định cuối cùng cần dựa trên tài nguyên và hợp đồng nghiệp vụ thực tế.

| Nhu cầu | Method thường phù hợp | Lý do |
|---|---|---|
| Đọc một đơn hàng | `GET /orders/{id}` | Chỉ truy xuất representation |
| Liệt kê đơn hàng theo bộ lọc | `GET /orders?...` | Truy vấn collection, hỗ trợ cache/phân trang |
| Tạo đơn hàng mới với ID do server cấp | `POST /orders` | Collection xử lý yêu cầu tạo và cấp URI mới |
| Tạo/đặt representation tại URI do client biết trước | `PUT /users/{id}/preferences` | Đích và representation được xác định rõ |
| Thay toàn bộ thông tin preferences | `PUT /users/{id}/preferences` | Đặt representation đích về nội dung gửi lên |
| Chỉ đổi ghi chú giao hàng | `PATCH /orders/{id}` | Áp dụng thay đổi một phần |
| Xóa địa chỉ đã lưu | `DELETE /addresses/{id}` | Yêu cầu xóa tài nguyên tại URI |
| Gửi lệnh hoàn tiền | `POST /orders/{id}/refunds` | Tạo yêu cầu/giao dịch nghiệp vụ mới, thường cần chống gửi trùng |
| Tìm kiếm phức tạp với body lớn | `POST /orders/search` | Dùng khi query string không phù hợp; hợp đồng cần nêu rõ đây là truy vấn không làm đổi nghiệp vụ |

Một lỗi thiết kế thường gặp là dùng `POST` cho mọi thao tác vì dễ viết controller, hoặc dùng `PUT` cho mọi cập nhật vì có sẵn một endpoint save. Cách làm đó làm mất thông tin về tính safe/idempotent, khiến client khó retry đúng và làm chính sách bảo mật khó diễn đạt. Hãy chọn method theo tác động mà client yêu cầu.

## 9. Status code, header và lỗi nhất quán

Method xác định loại thao tác; status code mô tả kết quả xử lý. Một API nên dùng status code nhất quán để client có thể quyết định hiển thị, thử lại hoặc yêu cầu người dùng xử lý xung đột.

| Status | Ý nghĩa điển hình |
|---|---|
| `200 OK` | Request thành công; thường có response body |
| `201 Created` | Tạo tài nguyên thành công; nên cung cấp `Location` khi phù hợp |
| `202 Accepted` | Đã nhận xử lý nhưng chưa hoàn tất |
| `204 No Content` | Thành công, không có response body |
| `304 Not Modified` | GET có điều kiện; representation chưa thay đổi |
| `400 Bad Request` | Cú pháp hoặc cấu trúc request không hợp lệ |
| `401 Unauthorized` | Thiếu hoặc thông tin xác thực không hợp lệ; có thể kèm `WWW-Authenticate` |
| `403 Forbidden` | Đã xác thực nhưng không có quyền thực hiện |
| `404 Not Found` | Không tìm thấy hoặc chủ động che giấu tài nguyên |
| `405 Method Not Allowed` | URI có tồn tại nhưng không hỗ trợ method đó; nên trả `Allow` |
| `409 Conflict` | Xung đột với trạng thái hoặc ràng buộc nghiệp vụ |
| `412 Precondition Failed` | Điều kiện request như `If-Match` không thỏa mãn |
| `415 Unsupported Media Type` | Content-Type hoặc patch format không được hỗ trợ |
| `422 Unprocessable Content` | Nội dung hiểu được nhưng không đáp ứng quy tắc xử lý |
| `429 Too Many Requests` | Vượt giới hạn; có thể kèm `Retry-After` |
| `500 Internal Server Error` | Lỗi không dự kiến ở phía máy chủ; không tiết lộ chi tiết nội bộ |

Một số header quan trọng:

- `Content-Type`: định dạng representation hoặc patch document trong request/response.
- `Accept`: định dạng response client có thể xử lý.
- `Location`: URI của tài nguyên mới hoặc tài nguyên/trạng thái tác vụ cần truy cập tiếp.
- `ETag`: mã phiên bản của representation, hỗ trợ cache và cập nhật có điều kiện.
- `If-Match`: yêu cầu chỉ xử lý khi phiên bản hiện tại khớp; hữu ích để chống ghi đè cập nhật đồng thời.
- `If-None-Match`: thường dùng với GET để kiểm tra representation có thay đổi hay không.
- `Cache-Control`: quy định cache response.
- `Allow`: liệt kê method được hỗ trợ khi trả `405 Method Not Allowed`.
- `Retry-After`: gợi ý thời điểm thử lại, thường dùng với `429` hoặc một số response tạm thời.

Không trả stack trace, câu SQL, secret, token hoặc dữ liệu của người dùng khác trong response lỗi. Có thể dùng một cấu trúc lỗi thống nhất như `type`, `title`, `status`, `detail` và `instance` theo Problem Details (RFC 9457), nhưng `detail` chỉ nên chứa thông tin an toàn cho client.

## 10. Kết hợp method với API Security

Chọn đúng method mới chỉ là bước đầu. Mỗi endpoint vẫn phải có chính sách bảo mật tương ứng với tác động của nó.

### 10.1. Phân quyền riêng cho từng method

Quyền đọc và quyền thay đổi phải tách biệt. Ví dụ, `order:read` không tự động cấp `order:update` hoặc `order:delete`. `POST /orders` cần quyền tạo đơn; `POST /orders/{id}/refunds` cần quyền hoàn tiền; `PATCH /orders/{id}` cần quyền sửa các trường được cho phép. Quyền nên được kiểm tra ở máy chủ trên từng request, không dựa vào việc client đã ẩn nút thao tác.

### 10.2. Phân quyền đối tượng và thuộc tính

Với mọi method nhận ID, kiểm tra caller có quyền trên đúng đối tượng và tenant. Không cho phép người dùng thay ID trên URL để truy cập dữ liệu người khác (BOLA/IDOR). Với PUT/PATCH/POST, dùng request DTO và allowlist field để ngăn mass assignment; với GET, dùng response DTO để không trả thuộc tính nội bộ. Với DELETE, kiểm tra trạng thái và quan hệ phụ thuộc trước khi xóa.

### 10.3. Không dùng GET để lách bảo vệ CSRF

Các thao tác thay đổi trạng thái phải dùng method không safe. Nếu xác thực dựa trên cookie, những method thay đổi như POST, PUT, PATCH và DELETE cần được bảo vệ CSRF phù hợp với kiến trúc. `SameSite` là một lớp hỗ trợ, không nên mặc định rằng mọi trường hợp đều không cần token hoặc kiểm tra origin. GET phải giữ tính safe để prefetch và crawler không gây thay đổi dữ liệu.

### 10.4. Chống retry và race condition

POST cho giao dịch quan trọng nên có idempotency key hoặc cơ chế định danh request duy nhất. PUT/DELETE có tính idempotent theo ngữ nghĩa nhưng vẫn cần kiểm soát quyền và điều kiện phiên bản. PATCH cần quy định thao tác nào có thể lặp và cách xử lý khi cùng lúc có nhiều bản cập nhật. Dùng ETag/`If-Match`, optimistic locking hoặc cơ chế đồng bộ phù hợp để tránh mất cập nhật và chuyển trạng thái sai.

### 10.5. Chỉ hỗ trợ method cần thiết

Endpoint nên công bố các method được hỗ trợ. Request dùng method không được phép cần trả `405 Method Not Allowed` và header `Allow` khi phù hợp. Không bật rộng rãi các method mà ứng dụng không sử dụng. Nếu có cơ chế method override qua header hoặc form field do proxy/framework hỗ trợ, cần hiểu rõ đường đi của request và bảo đảm lớp xác thực, WAF, router và ứng dụng diễn giải cùng một method.

## 11. Ví dụ thiết kế một nhóm endpoint đơn hàng

Giả sử hệ thống bán hàng có các nghiệp vụ đọc, tạo, sửa ghi chú và hủy đơn. Một hợp đồng có thể được thiết kế như sau:

| Endpoint | Request body | Kết quả chính | Quyền gợi ý |
|---|---|---|---|
| `GET /orders/{id}` | Không cần | `200` với representation đơn hàng | `order:read` + quyền trên đơn |
| `POST /orders` | Sản phẩm, số lượng, địa chỉ | `201` + `Location` | `order:create` + quyền trên địa chỉ/sản phẩm |
| `PUT /orders/{id}` | Toàn bộ representation được phép thay thế | `200` hoặc `204` | `order:replace` + quyền trên đơn |
| `PATCH /orders/{id}` | Patch document cho trường được phép | `200` hoặc `204` | `order:update` + quyền theo thuộc tính/trạng thái |
| `DELETE /orders/{id}` | Thường không cần | `204`, `202` hoặc kết quả được mô tả | `order:delete` + quyền trên đơn + điều kiện xóa |
| `POST /orders/{id}/cancellations` | Lý do hủy nếu cần | `201` hoặc `202` | `order:cancel` + điều kiện trạng thái |

Ví dụ controller rút gọn với Spring Boot minh họa việc tách method và request model:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('order:read')")
    OrderResponse get(@PathVariable UUID id) {
        return orderService.getVisibleOrder(id);
    }

    @PostMapping
    @PreAuthorize("hasAuthority('order:create')")
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderResponse created = orderService.create(request);
        URI location = URI.create("/api/orders/" + created.id());
        return ResponseEntity.created(location).body(created);
    }

    @PatchMapping(path = "/{id}",
            consumes = "application/merge-patch+json")
    @PreAuthorize("hasAuthority('order:update')")
    ResponseEntity<OrderResponse> patch(
            @PathVariable UUID id,
            @RequestBody UpdateOrderNoteRequest request) {
        return ResponseEntity.ok(orderService.updateAllowedFields(id, request));
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasAuthority('order:delete')")
    ResponseEntity<Void> delete(@PathVariable UUID id) {
        orderService.deleteIfAllowed(id);
        return ResponseEntity.noContent().build();
    }
}
```

Đây là ví dụ minh họa cấu trúc controller; các phương thức trong `orderService` vẫn phải kiểm tra quyền trên đối tượng, tenant, thuộc tính và trạng thái nghiệp vụ. Annotation `@PreAuthorize` chỉ kiểm tra quyền chức năng, không tự chứng minh caller có quyền trên đơn hàng cụ thể. Cấu hình xử lý PATCH cũng phải parse đúng media type và áp dụng patch theo hợp đồng đã công bố.

## 12. Checklist review endpoint

Khi review một endpoint, hãy kiểm tra các câu hỏi sau:

- [ ] URI đại diện cho tài nguyên hoặc collection rõ ràng.
- [ ] HTTP method thể hiện đúng ý định và tác động nghiệp vụ.
- [ ] GET chỉ đọc, không kích hoạt thay đổi trạng thái nghiệp vụ.
- [ ] PUT có hợp đồng thay thế representation rõ ràng; PATCH nêu rõ patch format và ý nghĩa của `null`/trường bị thiếu.
- [ ] POST có quy tắc xử lý retry và chống tạo trùng nếu tác động không được phép lặp.
- [ ] DELETE mô tả rõ xóa logic/vật lý, điều kiện xóa và response.
- [ ] Request DTO chỉ nhận trường client được phép gửi; response không lộ thuộc tính nội bộ.
- [ ] Có xác thực và quyền chức năng riêng cho từng method.
- [ ] Có kiểm tra quyền trên đối tượng, tenant, thuộc tính và trạng thái nghiệp vụ.
- [ ] Có validation kích thước, kiểu, miền giá trị và quan hệ dữ liệu.
- [ ] Có xử lý cập nhật đồng thời phù hợp, ví dụ ETag/`If-Match` hoặc optimistic locking.
- [ ] Status code và header nhất quán; `405` có `Allow` khi phù hợp.
- [ ] Cache được cấu hình phù hợp với độ nhạy cảm của response.
- [ ] Có rate limit, quota và giới hạn tài nguyên phù hợp với tác động của endpoint.
- [ ] Log/audit đủ để điều tra nhưng không ghi token hoặc dữ liệu nhạy cảm không cần thiết.

## Kết luận

`GET` dùng để đọc; `POST` gửi yêu cầu xử lý hoặc tạo tài nguyên; `PUT` đặt representation tại URI đích; `PATCH` áp dụng thay đổi một phần; `DELETE` yêu cầu xóa tài nguyên. Hiểu đúng safe, idempotent và cacheable giúp client retry, cache và xử lý lỗi chính xác. Khi kết hợp method với xác thực, phân quyền theo chức năng/đối tượng/thuộc tính, validation và kiểm soát đồng thời, API có một hợp đồng rõ ràng hơn và giảm được nhiều lỗi bảo mật phát sinh từ cách sử dụng endpoint không nhất quán.
