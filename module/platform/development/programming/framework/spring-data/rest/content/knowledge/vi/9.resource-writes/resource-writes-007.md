# JSON Patch với application/json-patch+json và các thao tác cơ bản

JSON Patch là định dạng mô tả một loạt thay đổi cần áp dụng lên một JSON document. Thay vì gửi lại toàn bộ entity, client gửi một mảng operation chỉ rõ thao tác, đường dẫn và giá trị cần dùng. Với Spring Data REST, cách tiếp cận này hữu ích khi muốn cập nhật một vài thuộc tính của tài nguyên qua HTTP PATCH, miễn là endpoint và cấu hình server hỗ trợ media type JSON Patch.

## 1. JSON Patch là gì?

JSON Patch được chuẩn hóa trong RFC 6902. Một JSON Patch document là một JSON array; mỗi phần tử là một operation được thực hiện theo đúng thứ tự xuất hiện.

Một operation thường có các trường:

- `op`: tên thao tác, ví dụ `add`, `remove`, `replace`, `move`, `copy` hoặc `test`.
- `path`: JSON Pointer xác định vị trí trong document cần thao tác.
- `value`: giá trị cần thêm, thay thế hoặc so sánh; chỉ có ở những operation cần giá trị.
- `from`: đường dẫn nguồn, được dùng bởi `move` và `copy`.

Ví dụ một patch document:

```json
[
  {
    "op": "replace",
    "path": "/name",
    "value": "An Nguyen"
  },
  {
    "op": "add",
    "path": "/nickname",
    "value": "An"
  }
]
```

Hai operation được áp dụng tuần tự: trước tiên thay đổi `name`, sau đó thêm thuộc tính `nickname`. Kết quả cuối cùng phụ thuộc document ban đầu và việc mỗi operation có hợp lệ tại thời điểm nó chạy hay không.

JSON Patch khác JSON Merge Patch. JSON Patch biểu diễn từng thao tác tường minh bằng một mảng operation; JSON Merge Patch biểu diễn một object mô tả các giá trị cần gộp và có semantics riêng cho `null`. Hai định dạng có media type khác nhau và không thể hoán đổi tùy ý.

## 2. application/json-patch+json và HTTP PATCH

Media type chuẩn của JSON Patch là:

`application/json-patch+json`

Client gửi patch document trong request body và khai báo media type này bằng `Content-Type`. Header `Accept` cho biết representation mà client muốn nhận lại; với Spring Data REST, client thường yêu cầu HAL JSON nếu endpoint trả hypermedia representation.

Ví dụ:

```http
PATCH /people/42 HTTP/1.1
Host: api.example.test
Content-Type: application/json-patch+json
Accept: application/hal+json

[
  {
    "op": "replace",
    "path": "/name",
    "value": "An Nguyen"
  },
  {
    "op": "add",
    "path": "/nickname",
    "value": "An"
  }
]
```

Ở đây:

- `PATCH` biểu thị yêu cầu thay đổi một phần tài nguyên.
- `Content-Type` cho server biết body là JSON Patch document.
- `Accept` yêu cầu response theo HAL JSON.
- `/people/42` là URI của item resource trong ví dụ.

Không phải mọi endpoint chỉ vì hỗ trợ PATCH đều tự động hỗ trợ `application/json-patch+json`. Spring Data REST phụ thuộc phiên bản, HTTP message converters, thư viện hỗ trợ và cấu hình ứng dụng. Hãy xác nhận endpoint chấp nhận media type này; nếu không, server có thể trả `415 Unsupported Media Type`. Cũng cần phân biệt JSON Patch với định dạng PATCH khác mà ứng dụng có thể cấu hình, chẳng hạn JSON Merge Patch.

## 3. JSON Pointer: cách chỉ vị trí cần thay đổi

Trường `path` sử dụng JSON Pointer (RFC 6901). Một pointer thường bắt đầu bằng dấu gạch chéo `/`; mỗi đoạn sau dấu gạch chéo xác định một key trong object hoặc một vị trí trong array.

Với document:

```json
{
  "name": "An",
  "address": {
    "city": "Da Nang",
    "postalCode": "550000"
  },
  "tags": ["java", "spring", "rest"]
}
```

Một số pointer tương ứng:

| Pointer | Vị trí |
|---|---|
| `/name` | Thuộc tính name ở root |
| `/address/city` | city bên trong address |
| `/tags/0` | Phần tử đầu tiên của tags |
| `/tags/2` | Phần tử thứ ba của tags |

Nếu tên key chứa ký tự `/` hoặc `~`, JSON Pointer yêu cầu escape:

- `~1` biểu diễn dấu `/`.
- `~0` biểu diễn dấu `~`.

Ví dụ key `a/b` được viết thành pointer segment `a~1b`. Khi có cả hai ký tự, cần escape theo đúng quy tắc JSON Pointer; không tự URL-encode pointer thay cho quy tắc escape này.

Với array, index bắt đầu từ 0. Token `-` có ý nghĩa đặc biệt trong operation `add`: nó chỉ vị trí nối thêm phần tử vào cuối array. Token này không phải index hợp lệ cho mọi operation.

## 4. Sáu operation cơ bản

### add — thêm giá trị

`add` thêm một giá trị tại `path`.

- Nếu path trỏ đến thuộc tính object chưa tồn tại, thuộc tính được tạo.
- Nếu thuộc tính đã tồn tại, giá trị của nó được thay thế.
- Nếu path trỏ đến array index, phần tử mới được chèn tại vị trí đó và các phần tử sau dịch chuyển.
- Dùng `-` để nối phần tử vào cuối array.

Ví dụ thêm tag vào cuối:

```json
[
  {
    "op": "add",
    "path": "/tags/-",
    "value": "spring-data"
  }
]
```

### remove — xóa giá trị

`remove` xóa giá trị tại path. Path phải xác định một thuộc tính hoặc phần tử đang tồn tại.

```json
[
  {
    "op": "remove",
    "path": "/address/postalCode"
  }
]
```

Sau thao tác, thuộc tính `postalCode` không còn trong object `address`.

### replace — thay thế giá trị

`replace` thay giá trị tại path bằng `value`. Path phải tồn tại.

```json
[
  {
    "op": "replace",
    "path": "/address/city",
    "value": "Ho Chi Minh City"
  }
]
```

### move — chuyển giá trị

`move` lấy giá trị tại `from`, xóa vị trí nguồn rồi thêm giá trị đó tại `path`. Cả hai pointer phải hợp lệ theo document tại thời điểm operation chạy.

```json
[
  {
    "op": "move",
    "from": "/address/city",
    "path": "/previousCity"
  }
]
```

Không thể chuyển một node vào bên trong chính node con của nó. Khi làm việc với array, cần nhớ rằng xóa phần tử nguồn có thể làm thay đổi index của các phần tử phía sau trước khi đích được xử lý.

### copy — sao chép giá trị

`copy` đọc giá trị tại `from` rồi thêm một bản sao tại `path`. Giá trị nguồn vẫn giữ nguyên.

```json
[
  {
    "op": "copy",
    "from": "/address/city",
    "path": "/billingCity"
  }
]
```

### test — kiểm tra giá trị

`test` so sánh giá trị tại path với `value`. Nếu không bằng nhau theo semantics của JSON Patch, operation thất bại.

```json
[
  {
    "op": "test",
    "path": "/status",
    "value": "ACTIVE"
  },
  {
    "op": "replace",
    "path": "/name",
    "value": "An Nguyen"
  }
]
```

Trong ví dụ này, thao tác replace chỉ tiếp tục nếu status hiện tại là `ACTIVE`. `test` hữu ích để đặt điều kiện trên trạng thái hiện tại, nhưng không thay thế cơ chế kiểm soát đồng thời ở cấp HTTP hoặc database.

## 5. Kết hợp nhiều operation trong một patch

Một patch document có thể chứa nhiều operation và thứ tự rất quan trọng. Mỗi operation nhìn thấy kết quả của những operation chạy trước nó.

Ví dụ:

```json
[
  {
    "op": "test",
    "path": "/status",
    "value": "ACTIVE"
  },
  {
    "op": "replace",
    "path": "/name",
    "value": "An Nguyen"
  },
  {
    "op": "add",
    "path": "/tags/-",
    "value": "spring-data"
  },
  {
    "op": "remove",
    "path": "/temporaryNote"
  }
]
```

Nếu `test` thất bại hoặc một operation khác có path không hợp lệ, patch không thể được xem là đã áp dụng thành công. Theo semantics của HTTP PATCH, server phải áp dụng toàn bộ patch một cách nguyên tử: không để lại trạng thái chỉ được cập nhật một phần nếu patch thất bại. Chi tiết transaction và persistence thực tế vẫn cần được kiểm chứng trong implementation của server.

JSON Patch không tự động idempotent. Ví dụ `add` vào `/tags/-` có thể thêm một phần tử trùng nếu client gửi lại request. Vì vậy, không nên retry mù một PATCH sau timeout khi chưa biết server đã xử lý request hay chưa.

## 6. JSON Patch trong Spring Data REST

Spring Data REST công bố repository resources dưới dạng HTTP endpoints. Một item resource có thể hỗ trợ PATCH để cập nhật một phần dữ liệu. Tuy nhiên, khả năng nhận JSON Patch cụ thể phụ thuộc media type và converter/patch handler được cấu hình trong ứng dụng.

Khi tích hợp, cần xác định:

1. Item URI được export và client đang gọi đúng URI.
2. Endpoint hỗ trợ HTTP PATCH.
3. Server chấp nhận `application/json-patch+json` và có thể đọc JSON Patch document.
4. Các path trong patch khớp với thuộc tính mà endpoint cho phép cập nhật.
5. Representation trả về phù hợp với `Accept` mà client yêu cầu.

Không nên giả định mọi thuộc tính Java đều là một path có thể ghi. Một field có thể không xuất hiện trong representation, bị giới hạn bởi mapping, là read-only, hoặc không được phép thay đổi qua repository resource. Association cũng có thể có semantics và association resource riêng; thay đổi quan hệ thường cần theo link association mà Spring Data REST công bố thay vì giả định có thể thay mọi relation bằng một JSON object path.

Ví dụ dùng curl:

```bash
curl -i -X PATCH \
  -H "Content-Type: application/json-patch+json" \
  -H "Accept: application/hal+json" \
  --data-binary '[
    {"op":"replace","path":"/name","value":"An Nguyen"},
    {"op":"add","path":"/nickname","value":"An"}
  ]' \
  https://api.example.test/people/42
```

Đây là request mẫu. Tên field, URI, media type được hỗ trợ và response phụ thuộc cấu hình API thực tế. Nếu server đang dùng JSON Merge Patch hoặc một định dạng PATCH tùy chỉnh, cần gửi đúng media type mà endpoint công bố.

## 7. Đồng thời, ETag và If-Match

Một patch thường dựa trên trạng thái mà client đã đọc trước đó. Nếu một client khác cập nhật tài nguyên trước khi patch được gửi, patch có thể vô tình áp dụng lên phiên bản mới hơn và tạo kết quả ngoài ý muốn.

HTTP cung cấp conditional request để giảm rủi ro này. Nếu server trả ETag cho representation, client có thể gửi giá trị đó trong `If-Match`:

```http
PATCH /people/42 HTTP/1.1
Host: api.example.test
Content-Type: application/json-patch+json
Accept: application/hal+json
If-Match: "version-7"

[
  {
    "op": "replace",
    "path": "/name",
    "value": "An Nguyen"
  }
]
```

Server chỉ nên áp dụng thay đổi khi validator vẫn khớp với phiên bản hiện tại. Nếu representation đã thay đổi, server có thể trả `412 Precondition Failed`. ETag và conditional request phải được server hỗ trợ và cấu hình đúng; không tự tạo ETag ở client hoặc giả định mọi Spring Data REST endpoint đều bật cơ chế này.

## 8. Lỗi thường gặp khi gửi JSON Patch

| Status | Nguyên nhân có thể gặp | Cách xử lý |
|---|---|---|
| `400 Bad Request` | JSON không hợp lệ, thiếu trường operation, pointer sai hoặc operation không thể thực hiện | Kiểm tra cú pháp JSON, `op`, `path`, `from` và trạng thái document |
| `404 Not Found` | Item URI hoặc path target không tồn tại theo cách server xử lý | Kiểm tra item URI và pointer |
| `405 Method Not Allowed` | Endpoint không hỗ trợ PATCH | Kiểm tra method khả dụng và API contract |
| `409 Conflict` | Patch xung đột với trạng thái hoặc quy tắc xử lý của server | Đọc trạng thái mới và tạo patch phù hợp |
| `412 Precondition Failed` | Điều kiện `If-Match` không còn đúng | Đọc lại representation/ETag rồi quyết định patch mới |
| `415 Unsupported Media Type` | Server không hỗ trợ `application/json-patch+json` tại endpoint | Kiểm tra converter và media type mà endpoint chấp nhận |
| `422 Unprocessable Content` | Server hiểu cú pháp nhưng không thể xử lý nội dung patch theo quy tắc ứng dụng | Kiểm tra validation và quy tắc nghiệp vụ nếu server dùng status này |

Status thực tế tùy exception mapping và cấu hình của ứng dụng. Không nên suy ra nguyên nhân chỉ từ một status; hãy đọc response body, headers và log server khi cần.

## 9. Checklist cho client

1. Lấy item URI từ HAL `self` link hoặc API contract.
2. Xác nhận endpoint hỗ trợ PATCH và media type `application/json-patch+json`.
3. Tạo một JSON array gồm các operation hợp lệ, theo đúng thứ tự mong muốn.
4. Dùng JSON Pointer chính xác; nhớ escape `~` thành `~0` và `/` thành `~1` trong tên key.
5. Dùng `test` hoặc conditional request khi cần ràng buộc trạng thái trước khi thay đổi.
6. Gửi `Content-Type: application/json-patch+json` và `Accept` phù hợp với response mong muốn.
7. Xử lý status code và representation trả về; không retry mù một patch có thể không idempotent.

JSON Patch cung cấp một cách diễn đạt thay đổi nhỏ, có thứ tự và rõ ràng cho HTTP PATCH. Khi kết hợp đúng JSON Pointer, media type, semantics của từng operation và cơ chế kiểm soát đồng thời, client có thể cập nhật tài nguyên Spring Data REST một cách chính xác mà không cần gửi lại toàn bộ entity.
