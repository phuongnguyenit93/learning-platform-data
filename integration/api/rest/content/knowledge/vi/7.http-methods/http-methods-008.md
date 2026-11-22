# JSON Patch: add, remove, replace, move, copy và test

## 1. JSON Patch trong thiết kế REST API

Một màn hình quản trị khóa học cho phép sửa học phí, chèn một nhãn, bỏ phần tóm tắt và đổi tên một thuộc tính metadata. Nếu client chỉ gửi một object JSON thông thường, server vẫn cần quy ước riêng để hiểu việc xóa thuộc tính, chèn phần tử hay đổi thứ tự mảng.

JSON Patch mô tả thay đổi bằng một danh sách thao tác có thứ tự. Khi dùng qua HTTP, client gửi danh sách đó đến URI của resource bằng phương thức `PATCH`, với media type `application/json-patch+json`. JSON Patch là một định dạng nội dung cho PATCH; phương thức PATCH không bắt buộc mọi API phải dùng định dạng này. Xem [RFC 6902, phần 1–3](https://www.rfc-editor.org/rfc/rfc6902.html#section-3).

Trong module `INTEGRATION_API_REST`, bài học kết nối thao tác trên JSON với hợp đồng REST: URI xác định resource, phương thức HTTP xác định cách tương tác, còn patch document mô tả cách biến đổi biểu diễn JSON. Server vẫn chịu trách nhiệm xác thực, phân quyền, kiểm soát cập nhật đồng thời, kiểm tra nghiệp vụ và lưu dữ liệu.

Sau bài học, người học có thể:

- Sử dụng sáu thao tác `add`, `remove`, `replace`, `move`, `copy`, `test`.
- Định vị dữ liệu bằng JSON Pointer, kể cả tên thuộc tính chứa `/` hoặc `~`.
- Dự đoán kết quả của chuỗi thao tác trên object và array.
- Thiết kế endpoint PATCH có tính nguyên tử, điều kiện phiên bản và lỗi rõ ràng.
- Phân chia trách nhiệm khi triển khai bằng Java/Spring hoặc công nghệ tương đương.

## 2. Cấu trúc của patch document

Patch document là **một mảng JSON**. Mỗi phần tử là một object mô tả một thao tác:

```json
[
  { "op": "test", "path": "/status", "value": "DRAFT" },
  { "op": "replace", "path": "/fee", "value": 950000 }
]
```

Đọc thành: “Nếu trạng thái hiện tại là `DRAFT`, thay học phí bằng `950000`”. Đây chưa phải resource sau cập nhật.

| Field | Vai trò | Thao tác sử dụng |
| --- | --- | --- |
| `op` | Tên thao tác, phân biệt chữ hoa và chữ thường | Cả sáu thao tác |
| `path` | JSON Pointer đến vị trí đích | Cả sáu thao tác |
| `value` | Giá trị JSON được thêm, thay hoặc so sánh | `add`, `replace`, `test` |
| `from` | JSON Pointer đến vị trí nguồn | `move`, `copy` |

`value` có thể là string, number, boolean, object, array hoặc `null`. Có `"value": null` khác với thiếu field `value`. Các tên như `Replace`, `delete` hay `increment` không phải thao tác JSON Patch chuẩn.

Thứ tự các phần tử trong mảng quyết định thứ tự thực hiện. Thứ tự các field bên trong một operation object không quyết định ý nghĩa. Field không được định nghĩa cho thao tác được bộ xử lý JSON Patch bỏ qua; không dùng field như `"mustBeOwner": true` để thay cho kiểm tra quyền trên server. Quy tắc cấu trúc nằm trong [RFC 6902, phần 3–4](https://www.rfc-editor.org/rfc/rfc6902.html#section-4).

Payload dưới đây chỉ là một object JSON, không phải JSON Patch:

```json
{
  "title": "REST API thực hành"
}
```

API cần một hợp đồng khác để diễn giải object này. Không gửi nó với `Content-Type: application/json-patch+json`.

## 3. Định vị dữ liệu bằng JSON Pointer

### 3.1. Đường dẫn trỏ vào biểu diễn JSON

Giả sử resource đang có biểu diễn:

```json
{
  "id": "rest-101",
  "title": "REST API căn bản",
  "fee": 1200000,
  "status": "DRAFT",
  "tags": ["java", "http"],
  "summary": null,
  "contact": {
    "email": "teacher@example.test"
  },
  "metadata": {
    "legacyCode": "REST-101",
    "a/b": "slash",
    "m~n": "tilde"
  }
}
```

| Pointer | Vị trí được tham chiếu |
| --- | --- |
| `""` | Toàn bộ tài liệu, tức root |
| `/title` | Thuộc tính `title` |
| `/contact/email` | Thuộc tính `email` trong `contact` |
| `/tags/0` | Phần tử đầu tiên của `tags` |
| `/metadata/a~1b` | Thuộc tính có tên thực là `a/b` |
| `/metadata/m~0n` | Thuộc tính có tên thực là `m~n` |

Mỗi token được ngăn bằng `/`. Trong tên thuộc tính, mã hóa `~` thành `~0`, rồi `/` thành `~1`. Khi giải mã, xử lý `~1` trước `~0`. Ví dụ tên thực `x~1y` được biểu diễn bằng token `x~01y`. Quy tắc này được định nghĩa trong [RFC 6901, phần 3–5](https://www.rfc-editor.org/rfc/rfc6901.html#section-3).

Pointer không phải đường dẫn filesystem, JSONPath hay tên property Java. `/contact/email` hợp lệ; `$.contact.email` không phải JSON Pointer. Trong patch document, dùng dạng chuỗi pointer, không dùng URI fragment `#/contact/email`.

### 3.2. Những ranh giới cần phân biệt

- Chuỗi rỗng `""` chọn root. Chuỗi `"/"` chọn thuộc tính có tên rỗng trong một object.
- Chỉ số mảng bắt đầu từ `0`. Token `01` không phải chỉ số mảng hợp lệ.
- Token số trong object vẫn là tên thuộc tính. `/metadata/0` có thể chọn key `"0"` nếu `metadata` là object.
- Token cuối `-` trong đích thêm vào mảng biểu diễn vị trí sau phần tử cuối. `/tags/-` dùng được với `add`; không có phần tử hiện hữu tại đó cho `remove`, `replace` hoặc `test`.
- Pointer không tự tìm phần tử theo ID. `/items/42` chọn index `42` nếu `items` là array, không tìm object có `id` bằng `42`.

Với collection thường xuyên thay đổi thứ tự, một API con như `/courses/rest-101/lessons/lesson-42` có thể phù hợp hơn việc buộc mọi client nhớ index trong mảng. Đây là lựa chọn thiết kế resource của ứng dụng.

## 4. Sáu thao tác và kết quả cụ thể

Các ví dụ nhỏ dưới đây độc lập với nhau, trừ khi có nói rõ là một chuỗi liên tiếp.

### 4.1. `add`: thêm thuộc tính hoặc chèn phần tử

Bắt đầu từ:

```json
{
  "title": "REST API căn bản",
  "tags": ["java", "http"]
}
```

Áp dụng:

```json
[
  { "op": "add", "path": "/subtitle", "value": "Thiết kế hợp đồng HTTP" },
  { "op": "add", "path": "/tags/1", "value": "rest" }
]
```

Kết quả:

```json
{
  "title": "REST API căn bản",
  "subtitle": "Thiết kế hợp đồng HTTP",
  "tags": ["java", "rest", "http"]
}
```

Ở object, `add` tạo thuộc tính nếu chưa có, nhưng thay giá trị nếu thuộc tính đã có. Vì vậy `add /title` có thể đổi title hiện tại; nó không bảo đảm “chỉ tạo mới”.

Ở array, `add /tags/1` chèn trước phần tử đang có index `1`, làm các phần tử phía sau dịch sang phải. Với mảng có độ dài `n`, index thêm hợp lệ thuộc `0..n`; `n` có nghĩa nối cuối. Cách viết `/tags/-` cũng nối cuối.

Object hoặc array cha phải tồn tại. Nếu tài liệu là `{}`, thao tác `add /contact/email` thất bại vì chưa có `contact`. Có thể thêm cả object cha trước:

```json
[
  {
    "op": "add",
    "path": "/contact",
    "value": { "email": "teacher@example.test" }
  }
]
```

Nếu `contact` đã tồn tại, ví dụ trên thay cả giá trị `contact`; nó không tự hợp nhất các thuộc tính con. Hợp đồng client cần phân biệt tạo object với cập nhật một field của object đang có.

### 4.2. `remove`: xóa vị trí đang tồn tại

Bắt đầu từ:

```json
{
  "summary": null,
  "tags": ["java", "rest", "http"]
}
```

Áp dụng:

```json
[
  { "op": "remove", "path": "/summary" },
  { "op": "remove", "path": "/tags/1" }
]
```

Kết quả:

```json
{
  "tags": ["java", "http"]
}
```

`summary` đã bị xóa khỏi object, không còn tồn tại với giá trị `null`. Phần tử `http` dịch từ index `2` sang index `1`.

Xóa một thuộc tính chưa có là lỗi. Không tự biến `remove` thành thao tác “xóa nếu có” rồi vẫn coi đó là ngữ nghĩa JSON Patch chuẩn. Client cần dựa vào snapshot đã đọc hoặc sử dụng một hợp đồng khác phù hợp với ý định cập nhật.

### 4.3. `replace`: thay giá trị đang tồn tại

Bắt đầu từ:

```json
{
  "fee": 1200000,
  "tags": ["java", "http"]
}
```

Áp dụng:

```json
[
  { "op": "replace", "path": "/fee", "value": 950000 },
  { "op": "replace", "path": "/tags/0", "value": "spring" }
]
```

Kết quả:

```json
{
  "fee": 950000,
  "tags": ["spring", "http"]
}
```

Đích của `replace` phải có sẵn. Thao tác này không tạo thuộc tính còn thiếu. Trên array, nó thay phần tử tại index thay vì chèn thêm, nên độ dài mảng không đổi.

Thay cả object có nghĩa thay toàn bộ giá trị tại vị trí đó:

```json
[
  {
    "op": "replace",
    "path": "/contact",
    "value": { "email": "support@example.test" }
  }
]
```

Nếu `contact` cũ còn có `phone`, field `phone` không tự được giữ lại. Muốn chỉ đổi email, dùng `/contact/email` khi field đó đang tồn tại.

### 4.4. `move`: lấy giá trị nguồn, xóa nguồn, rồi thêm vào đích

Bắt đầu từ:

```json
{
  "metadata": {
    "legacyCode": "REST-101"
  }
}
```

Áp dụng:

```json
[
  {
    "op": "move",
    "from": "/metadata/legacyCode",
    "path": "/metadata/externalCode"
  }
]
```

Kết quả:

```json
{
  "metadata": {
    "externalCode": "REST-101"
  }
}
```

`from` phải tồn tại. Đích dùng quy tắc thêm của `add`, nên có thể tạo key mới hoặc ghi đè key object đã có. Không dùng `value` để chỉ định nội dung chuyển; giá trị được lấy từ nguồn.

Điểm dễ sai nhất là chuyển trong cùng một mảng. Giả sử có:

```json
{
  "steps": ["A", "B", "C", "D"]
}
```

Áp dụng:

```json
[
  { "op": "move", "from": "/steps/1", "path": "/steps/3" }
]
```

Sau khi lấy `B` và xóa nguồn, mảng tạm là `["A", "C", "D"]`. Chèn `B` vào index `3` của mảng tạm, kết quả là `["A", "C", "D", "B"]`. Không tính đích như thể nguồn vẫn còn trong mảng.

Không được chuyển một node vào node con của chính nó. Chuyển `/contact` đến `/contact/backup` là lỗi. Khi kiểm tra quy tắc này, so sánh các token pointer; `/a` và `/ab` là hai key khác nhau.

### 4.5. `copy`: thêm một bản sao giá trị nguồn vào đích

Bắt đầu từ:

```json
{
  "contact": {
    "email": "teacher@example.test"
  }
}
```

Áp dụng:

```json
[
  { "op": "copy", "from": "/contact", "path": "/supportContact" },
  {
    "op": "replace",
    "path": "/supportContact/email",
    "value": "support@example.test"
  }
]
```

Kết quả:

```json
{
  "contact": {
    "email": "teacher@example.test"
  },
  "supportContact": {
    "email": "support@example.test"
  }
}
```

Nguồn vẫn tồn tại. Sửa bản sao không làm thay đổi nguồn như hai biến Java cùng tham chiếu một mutable object. Nếu tự triển khai trên cây JSON có thể thay đổi, phải tránh dùng chung node khiến thao tác sau vô tình sửa cả hai nơi.

Nguồn phải tồn tại và đích dùng quy tắc thêm của `add`. Vì vậy `copy` vào array chèn thêm phần tử; `copy` vào key object đã có thay giá trị tại key đó. Đường dẫn nguồn cũng cần được phân quyền đọc.

### 4.6. `test`: kiểm tra giá trị tại thời điểm thao tác được thực hiện

Bắt đầu từ:

```json
{
  "status": "DRAFT",
  "fee": 1200000
}
```

Áp dụng:

```json
[
  { "op": "test", "path": "/status", "value": "DRAFT" },
  { "op": "replace", "path": "/fee", "value": 950000 }
]
```

`test` không thay đổi dữ liệu. Nó thành công thì thao tác sau mới tiếp tục. Nếu trạng thái là `PUBLISHED`, patch thất bại. Đích không tồn tại cũng không được coi là khớp giá trị `null`.

So sánh là so sánh giá trị JSON, không phải so sánh chuỗi JSON đã serialize:

| Hai giá trị đem so sánh | Kết quả |
| --- | --- |
| `950000` và `"950000"` | Khác kiểu, không bằng nhau |
| `1` và `1.0` | Bằng nhau về giá trị số |
| `null` và `null` | Bằng nhau |
| `false` và `0` | Khác kiểu, không bằng nhau |
| `["java", "rest"]` và `["rest", "java"]` | Không bằng nhau vì thứ tự array khác |
| `{"a":1,"b":2}` và `{"b":2,"a":1}` | Bằng nhau dù thứ tự key object khác |

Với chuỗi, không tự đổi chữ hoa/thường hay chuẩn hóa Unicode để coi là bằng nhau. Với số tiền, ứng dụng vẫn phải quy định đơn vị, miền giá trị và cách biểu diễn số; `test` không thay thế quy tắc tài chính của miền nghiệp vụ.

## 5. Thứ tự thực hiện quyết định ý nghĩa

Mỗi thao tác nhận tài liệu kết quả của thao tác trước. Server không được gom các thao tác cùng tên rồi đổi thứ tự để tối ưu.

Ví dụ ban đầu:

```json
{
  "tags": ["java", "rest", "spring", "http"]
}
```

Patch sau xóa `java`, rồi xóa `spring`:

```json
[
  { "op": "remove", "path": "/tags/0" },
  { "op": "remove", "path": "/tags/1" }
]
```

Sau lần xóa đầu, mảng là `["rest", "spring", "http"]`. Lần xóa sau tác động vào `spring` tại index `1`. Kết quả cuối là `["rest", "http"]`.

Nếu ý định là xóa các phần tử có index ban đầu `0` và `1`, có thể xóa theo thứ tự giảm dần: index `1`, rồi index `0`. Cách này chỉ đúng khi các thao tác được sinh từ cùng một snapshot và không có thao tác khác làm thay đổi index xen giữa.

`test` cũng quan sát trạng thái tại vị trí của nó trong chuỗi:

```json
[
  { "op": "replace", "path": "/fee", "value": 950000 },
  { "op": "test", "path": "/fee", "value": 950000 }
]
```

Đoạn trên xác nhận kết quả vừa thay, không xác nhận học phí ban đầu là bao nhiêu. Muốn bảo vệ giả định về học phí cũ, đặt `test` tương ứng trước `replace`.

## 6. Ví dụ hoàn chỉnh trên resource khóa học

Dùng resource ban đầu ở phần 3. Client thực hiện sáu thao tác trong một lần tương tác:

```http
PATCH /courses/rest-101 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: application/json-patch+json
Accept: application/json
If-Match: "course-rest-101-r7"

[
  { "op": "test", "path": "/status", "value": "DRAFT" },
  { "op": "add", "path": "/tags/1", "value": "rest" },
  { "op": "remove", "path": "/summary" },
  { "op": "replace", "path": "/fee", "value": 950000 },
  { "op": "copy", "from": "/contact", "path": "/supportContact" },
  {
    "op": "move",
    "from": "/metadata/legacyCode",
    "path": "/metadata/externalCode"
  }
]
```

Giả sử người gọi đủ quyền, phiên bản khớp và dữ liệu hợp lệ, biểu diễn sau cập nhật là:

```json
{
  "id": "rest-101",
  "title": "REST API căn bản",
  "fee": 950000,
  "status": "DRAFT",
  "tags": ["java", "rest", "http"],
  "contact": {
    "email": "teacher@example.test"
  },
  "metadata": {
    "externalCode": "REST-101",
    "a/b": "slash",
    "m~n": "tilde"
  },
  "supportContact": {
    "email": "teacher@example.test"
  }
}
```

Có thể trả `200 OK` kèm biểu diễn mới và ETag mới. Nếu hợp đồng không trả body, có thể dùng:

```http
HTTP/1.1 204 No Content
ETag: "course-rest-101-r8"
```

Response `204` không chứa body JSON. ETag trong ví dụ do server phát hành; client giữ nguyên dấu ngoặc kép khi gửi lại trong `If-Match`.

## 7. Tính nguyên tử, cập nhật đồng thời và retry

### 7.1. Không lưu thành công một phần

Giả sử tài liệu có `fee = 1200000`. Patch sau thất bại ở thao tác thứ hai:

```json
[
  { "op": "replace", "path": "/fee", "value": 950000 },
  { "op": "remove", "path": "/missingField" }
]
```

Dữ liệu lưu trữ phải vẫn giữ học phí `1200000`. Trả lỗi nhưng để học phí thành `950000` là vi phạm tính nguyên tử của HTTP PATCH. Yêu cầu áp dụng toàn bộ hoặc không áp dụng thay đổi nào được nêu trong [RFC 5789, phần 2](https://www.rfc-editor.org/rfc/rfc5789.html#section-2).

Một cách triển khai là áp dụng patch lên bản sao cây JSON trong bộ nhớ, kiểm tra kết quả rồi mới ghi trong transaction. Nếu phải thay nhiều bảng liên quan, transaction phải bao trùm toàn bộ thay đổi đó. Không phát email hay gọi hệ thống ngoài sau từng operation; với tác động ngoài database, có thể ghi sự kiện outbox cùng transaction để xử lý sau commit.

Thư viện JSON Patch giúp biến đổi JSON. Nó không tự bảo đảm transaction cho database của ứng dụng.

### 7.2. `test` và `If-Match` bảo vệ hai loại điều kiện

`test /status = DRAFT` diễn đạt điều kiện về một giá trị trong tài liệu. Nếu người khác chỉ sửa `title`, điều kiện này vẫn có thể đúng dù phiên bản resource đã thay đổi.

`If-Match` kiểm tra validator của biểu diễn. Khi điều kiện không khớp, server thông thường trả `412 Precondition Failed` và không thực hiện thay đổi. `If-Match` dùng phép so sánh mạnh; một weak ETag dạng `W/"..."` không khớp theo phép so sánh này. Xem [RFC 9110, phần 13.1.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1).

Luồng thường dùng:

1. Client GET resource và nhận ETag, ví dụ `"course-rest-101-r7"`.
2. Client tạo patch từ dữ liệu đã đọc và gửi cùng `If-Match` tương ứng.
3. Server xác thực quyền, kiểm tra điều kiện và áp dụng patch trên đúng snapshot.
4. Server lưu với khóa hoặc điều kiện phiên bản để ngăn request khác chen giữa bước đọc và ghi.
5. Server trả kết quả cùng ETag mới.

Kiểm tra ETag ở controller rồi ghi đè database vô điều kiện vẫn có race condition. Cần cơ chế ở tầng lưu trữ, ví dụ optimistic locking bằng version hoặc câu lệnh `UPDATE ... WHERE revision = :expectedRevision`. Khi không cập nhật được dòng nào do xung đột phiên bản, toàn bộ lần cập nhật phải thất bại.

Không chỉ dựa vào annotation transaction để suy ra rằng mọi request đồng thời được tuần tự hóa. Cần hiểu isolation level, khóa và cơ chế kiểm tra phiên bản thực tế.

### 7.3. PATCH không mặc nhiên idempotent

Xét cùng một request được gửi hai lần:

| Thao tác | Rủi ro khi thực hiện lại trên trạng thái đã thay đổi |
| --- | --- |
| `add /tags/- = "rest"` | Nhãn được nối thêm lần nữa |
| `add /tags/0 = "rest"` | Thêm phần tử và tiếp tục dịch index |
| `remove /tags/0` | Lần sau có thể xóa một phần tử khác |
| `move /steps/0` đến `/steps/2` | Thứ tự tiếp tục bị thay đổi |
| `replace /fee = 950000` | Riêng phép gán này giữ cùng giá trị nếu đích vẫn tồn tại |

Không kết luận toàn endpoint idempotent chỉ vì patch hiện tại có một phép `replace`. Còn phải xét chuỗi thao tác, cập nhật đồng thời và tác động nghiệp vụ.

Khi request dùng ETag cũ đã thành công một lần, lần gửi lại thường thất bại điều kiện phiên bản. Điều này ngăn áp dụng lặp trên phiên bản mới nhưng không tự cho client biết request trước đã commit hay chưa. Nếu bị timeout, client nên đọc lại và đối chiếu trạng thái. Cơ chế idempotency key chỉ có ý nghĩa khi API thật sự định nghĩa cách lưu và phát lại kết quả.

## 8. Hợp đồng HTTP và lỗi có thể xử lý được

### 8.1. Công bố định dạng và phạm vi hỗ trợ

Server có thể công bố:

```http
HTTP/1.1 204 No Content
Allow: GET, PATCH, OPTIONS
Accept-Patch: application/json-patch+json
```

`Allow` nói về phương thức; `Accept-Patch` nói về các định dạng patch được hỗ trợ. Cơ chế `Accept-Patch` được mô tả trong [RFC 5789, phần 3.1](https://www.rfc-editor.org/rfc/rfc5789.html#section-3.1).

Hợp đồng endpoint cũng cần nói rõ:

- Resource phải tồn tại hay có hỗ trợ tạo mới. Ví dụ trong bài chỉ cập nhật khóa học đã tồn tại.
- Những đường dẫn và thao tác nào người gọi được phép sử dụng.
- Có yêu cầu `If-Match` hay không; giới hạn kích thước body và số operation.
- Thuộc tính nào có thể vắng mặt, nhận `null`, hoặc bắt buộc giữ lại.
- Trả `200` kèm resource hay `204` không body khi thành công.

### 8.2. Một bảng ánh xạ lỗi cho API minh họa

Bảng sau là hợp đồng thiết kế cho ví dụ; các thư viện và API khác có thể chọn cách ánh xạ khác cho lỗi áp dụng patch:

| Tình huống | HTTP status của API ví dụ |
| --- | --- |
| JSON hỏng, body không phải mảng, thiếu field bắt buộc, `op` không hợp lệ hoặc pointer sai cú pháp | `400 Bad Request` |
| Chưa có thông tin xác thực hợp lệ | `401 Unauthorized` |
| Đã xác thực nhưng không được sửa resource hoặc đường dẫn | `403 Forbidden` |
| Không tìm thấy resource khóa học theo URI | `404 Not Found` |
| `test` không khớp, nguồn không có hoặc đích bắt buộc tồn tại nhưng không có | `409 Conflict` |
| `If-Match` được đánh giá không khớp | `412 Precondition Failed` |
| Body vượt giới hạn đã công bố | `413 Content Too Large` |
| Định dạng patch không được endpoint hỗ trợ | `415 Unsupported Media Type` |
| Kết quả patch vi phạm schema hoặc nghiệp vụ, ví dụ học phí âm | `422 Unprocessable Content` |
| Endpoint yêu cầu điều kiện nhưng request thiếu `If-Match` | `428 Precondition Required` |

`428` thể hiện server yêu cầu request có điều kiện, theo [RFC 6585, phần 3](https://www.rfc-editor.org/rfc/rfc6585.html#section-3). Chính sách bắt buộc `If-Match` là lựa chọn của endpoint trong bài.

`test` thất bại trong body không tự động đồng nghĩa với `412`. Mã `412` gắn với điều kiện trong header HTTP; lỗi điều kiện trong patch có thể được API quy định là `409` như ở đây. Việc chọn `409` hay `422` cho các lỗi áp dụng patch cần được mô tả nhất quán.

Ví dụ body lỗi do ứng dụng định nghĩa:

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "code": "JSON_PATCH_TEST_FAILED",
  "message": "Điều kiện cập nhật không còn đúng.",
  "operationIndex": 0,
  "path": "/status"
}
```

`operationIndex` trong hợp đồng này bắt đầu từ `0`. Chỉ trả thông tin mà người gọi được quyền biết; không đính kèm giá trị hiện tại của trường nhạy cảm. Body lỗi trên là schema riêng của API, không phải một phần bắt buộc của JSON Patch.

## 9. Phân chia triển khai trong Java/Spring

### 9.1. Controller nhận đúng media type

Đây là minh họa kiến trúc Spring MVC dùng Jackson 2. Các kiểu `CoursePatchService` và `PatchResult` thuộc ứng dụng; đoạn code không phải ứng dụng độc lập chạy ngay. Dự án dùng thế hệ Jackson khác cần adapter và kiểu JSON tree tương ứng.

```java
import com.fasterxml.jackson.databind.JsonNode;
import java.security.Principal;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/courses")
public class CoursePatchController {
    private final CoursePatchService service;

    public CoursePatchController(CoursePatchService service) {
        this.service = service;
    }

    @PatchMapping(
        path = "/{id}",
        consumes = "application/json-patch+json",
        produces = "application/json"
    )
    public ResponseEntity<JsonNode> patch(
            @PathVariable("id") String id,
            @RequestHeader(name = "If-Match", required = false) String ifMatch,
            @RequestBody JsonNode patchDocument,
            Principal principal) {

        PatchResult result = service.apply(
            id, ifMatch, patchDocument, principal.getName()
        );

        return ResponseEntity.ok()
            .header("ETag", result.etagHeaderValue())
            .body(result.representation());
    }
}
```

Ví dụ giả định Spring Security đã buộc xác thực trước khi gọi controller. Service xử lý thiếu `If-Match` thành lỗi `428` theo hợp đồng; `required = false` tránh để lỗi thiếu header mặc định quyết định thay chính sách ứng dụng. `etagHeaderValue()` trả giá trị header hoàn chỉnh, gồm dấu ngoặc kép.

`@PatchMapping` chọn HTTP PATCH; `consumes` chọn media type đầu vào. Annotation này không tự áp dụng sáu thao tác lên entity. Tham khảo [tài liệu Spring về PatchMapping](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/PatchMapping.html).

### 9.2. Service quản lý snapshot, patch và commit

Mã giả dưới đây thể hiện trách nhiệm, không phải API có sẵn của Spring hay một thư viện cụ thể:

```text
apply(courseId, ifMatch, patchDocument, actor):
    xác minh quyền truy cập khóa học của actor
    yêu cầu và phân tích If-Match theo cú pháp HTTP
    kiểm tra body là patch document hợp lệ và trong giới hạn

    bắt đầu transaction
        đọc khóa học và revision hiện tại
        xác minh If-Match trên biểu diễn tương ứng
        dựng JSON projection dành cho hợp đồng PATCH
        tạo bản sao làm việc

        với từng operation theo thứ tự:
            kiểm tra quyền trên các pointer liên quan
            áp dụng operation bằng bộ xử lý JSON Patch
            nếu thất bại: dừng và hủy toàn bộ cập nhật

        kiểm tra schema và nghiệp vụ của kết quả cuối
        kiểm tra thay đổi thực tế nằm trong phạm vi được phép
        ánh xạ rõ từng field được sửa vào mô hình nghiệp vụ
        ghi có điều kiện revision vẫn bằng revision đã đọc
        nếu xung đột phiên bản: hủy transaction
        dựng representation và ETag của revision mới
    commit transaction

    trả kết quả sau khi commit thành công
```

Nếu lỗi chỉ xuất hiện khi flush hoặc commit, response không được coi là thành công trước khi xử lý lỗi đó. Cần giữ đúng ranh giới transaction giữa service và controller.

JSON projection phải ổn định và được mô tả trong hợp đồng. Không serialize toàn bộ JPA entity có quan hệ lazy, field nội bộ hoặc dữ liệu nhạy cảm rồi cho client patch tùy ý. Nếu representation dùng cho PATCH khác representation GET, API phải giải thích client lấy cấu trúc và validator tương ứng từ đâu.

### 9.3. Tích hợp bộ xử lý JSON Patch

Có thể dùng thư viện triển khai RFC 6902 thay vì tự viết toàn bộ engine. Adapter của ứng dụng cần làm rõ:

- Engine trả cây JSON mới hay sửa trực tiếp cây đầu vào.
- Cách phân biệt lỗi cấu trúc, pointer không tồn tại và `test` thất bại.
- So sánh số của `test` có đúng ngữ nghĩa JSON Patch hay phụ thuộc kiểu số trong JSON tree.
- Cách xử lý `copy` object/array, escape pointer và `move` trong cùng mảng.
- Giới hạn tài nguyên và mức tương thích với Java/Jackson của dự án.

Không bind patch thẳng vào entity để thay cho bộ xử lý JSON Patch. `@Valid` trên danh sách operation cũng không tự kiểm tra rằng resource cuối cùng vẫn hợp lệ.

## 10. Phân quyền theo tác động thực tế

Quyền cập nhật khóa học không đồng nghĩa quyền thay mọi field trong JSON. Giảng viên có thể sửa `title`, `fee`, `tags`, `summary`, `contact` và một số metadata, nhưng không được sửa `id`, chủ sở hữu hoặc doanh thu đã đối soát.

| Thao tác | Quyền cần xét |
| --- | --- |
| `add`, `replace`, `remove` | Tác động ghi/xóa tại đích và các field con bị thay thế |
| `copy` | Quyền đọc nguồn và quyền ghi đích |
| `move` | Quyền đọc/xóa nguồn và quyền ghi đích |
| `test` | Quyền quan sát giá trị tại đích, tránh dò dữ liệu qua kết quả đúng/sai |

Những trường hợp cần xử lý rõ:

1. **Thay object cha:** chặn `/metadata/protectedFlag` nhưng cho thay toàn bộ `/metadata` có thể tạo đường vòng. Phải kiểm tra các field con bị ảnh hưởng.
2. **Thay root:** `add` hoặc `replace` tại `path: ""` có thể thay cả tài liệu. Endpoint có thể cấm vì chính sách quyền; pointer rỗng vẫn hợp lệ về cú pháp.
3. **Đọc nguồn nhạy cảm:** `copy /internalSecret` đến `/publicNote` có thể làm lộ dữ liệu nếu chỉ kiểm tra đích.
4. **So sánh chuỗi thô:** `startsWith("/contact")` có thể nhầm `/contactSecret` với con của `/contact`. Cần phân tích pointer thành token.
5. **Thay index:** chuỗi thao tác trên mảng thay đổi đối tượng tại một index. Nếu quyền gắn với từng phần tử, kiểm tra trên trạng thái làm việc tại thời điểm thực hiện thao tác.

Ngoài giới hạn request body, nên giới hạn số operation, độ sâu cây JSON và kích thước kết quả. Nhiều thao tác `copy` có thể tạo dữ liệu lớn hơn đáng kể so với body đầu vào. Giới hạn cụ thể phải dựa vào nhu cầu và được công bố cho client.

Với `remove`, dữ liệu vắng mặt sau patch phải được chuyển thành thay đổi có ý nghĩa khi lưu. DTO coi “thiếu field” và “field bằng null” là cùng một trạng thái có thể làm mất ý định của client. Hợp đồng cần xác định trường nào được xóa, trường nào chỉ cho gán `null`; mapper phải bảo toàn khác biệt cần thiết đó.

## 11. Các tình huống cần kiểm thử khi triển khai endpoint

Đây là các tình huống dành cho người xây dựng API; kết quả thực tế cần được kiểm tra trên engine và tầng lưu trữ mà dự án lựa chọn.

| Nhóm | Dữ liệu hoặc thao tác | Điều cần chứng minh |
| --- | --- | --- |
| Object | `add` vào key mới và key đã có | Tạo mới hoặc thay giá trị đúng hợp đồng |
| Array | `add` tại `0`, `n`, `-`, `n+1` | Chèn đúng; vượt giới hạn bị từ chối |
| Điều kiện tồn tại | `replace` hoặc `remove` field thiếu | Không âm thầm tạo mới hoặc bỏ qua |
| Null | `test` field bằng `null`; `test` field vắng mặt | Hai tình huống được phân biệt |
| Escape | Key `a/b`, `m~n`, `x~1y` | Định vị đúng field thực |
| Move | Chuyển trong cùng array; chuyển cha vào con | Index đúng; thao tác không hợp lệ bị chặn |
| Copy | Copy object rồi sửa bản sao | Nguồn không bị sửa theo |
| Test | Số với string, object đổi thứ tự key, array đổi thứ tự | So sánh theo giá trị và kiểu JSON |
| Thứ tự | Hai lần xóa liên tiếp cùng mảng | Mỗi thao tác thấy kết quả trước đó |
| Nguyên tử | Thao tác đầu thành công, thao tác sau thất bại | Database giữ nguyên trạng thái ban đầu |
| Đồng thời | Hai request cùng đọc một revision rồi cùng PATCH | Không ghi đè mất cập nhật; xung đột được trả rõ |
| Phân quyền | Đường dẫn cấm, thay object cha, nguồn copy bị cấm | Không vượt quyền qua cấu trúc patch |
| HTTP | Media type sai, thiếu `If-Match`, ETag cũ, thành công `204` | Status và body đúng hợp đồng |

Kiểm tra tính nguyên tử cần đọc lại dữ liệu đã lưu, không chỉ assert HTTP status. Kiểm tra đồng thời cần tạo tình huống cả hai request cùng nhìn thấy một phiên bản; chạy hai request tuần tự không chứng minh việc ngăn race condition.

Trong OpenAPI, mô tả request body là `application/json-patch+json` với schema array các operation, có các nhánh tương ứng yêu cầu `value` hoặc `from`. Đưa vào ví dụ, header `If-Match`, giới hạn thao tác, đường dẫn được sửa và schema lỗi. Không dùng schema toàn bộ resource làm schema request cho JSON Patch.

## 12. Chọn JSON Patch và tránh ngộ nhận

JSON Patch phù hợp khi client cần diễn đạt thao tác trên vị trí cụ thể: chèn/xóa phần tử mảng, chuyển dữ liệu, sao chép giá trị và đặt điều kiện `test` trong chuỗi thay đổi. Với form đơn giản, DTO cập nhật có hợp đồng rõ ràng có thể dễ sử dụng hơn. Với hành động như xuất bản khóa học, ứng dụng có thể cần hợp đồng thể hiện việc xuất bản cùng các điều kiện nghiệp vụ liên quan.

Một patch nhỏ vẫn có thể gây thay đổi lớn: một operation thay root có thể thay mọi thứ; một operation `remove` có thể xóa cả collection. Luôn xét tác động, quyền và kết quả cuối.

Những cách hiểu cần sửa:

- `add` không luôn chỉ tạo mới: trên key object đã tồn tại, nó thay giá trị.
- `replace` không phải upsert: vị trí đích phải có sẵn.
- `remove` không phải gán `null`: nó xóa vị trí.
- `move` trong array tính đích sau khi nguồn đã bị xóa.
- `copy` không tạo liên kết sống giữa nguồn và đích.
- `test` không khóa database và không tự bảo vệ toàn bộ phiên bản resource.
- Nhận JSON bằng `@RequestBody` không có nghĩa Spring đã xử lý JSON Patch.
- HTTP PATCH yêu cầu lưu nguyên tử, không chấp nhận thành công một phần.

Khi thiết kế endpoint, đi từ ý định cập nhật đến pointer và thao tác, rồi đến quyền, điều kiện phiên bản, kiểm tra kết quả và commit nguyên tử. Chuỗi trách nhiệm này giúp JSON Patch trở thành hợp đồng REST có thể sử dụng ổn định.
