# Lỗi theo trường, theo phần tử và đường dẫn dữ liệu

## 1. Vì sao một thông báo "Dữ liệu không hợp lệ" là chưa đủ?

Khi client gửi dữ liệu đến REST API, lỗi không chỉ xảy ra ở toàn bộ request. Một thuộc tính đơn lẻ có thể sai định dạng, một phần tử trong danh sách có thể thiếu dữ liệu, hoặc hai trường vốn hợp lệ riêng lẻ lại mâu thuẫn với nhau. Nếu server chỉ trả "Validation failed", client rất khó chỉ đúng ô nhập liệu cần sửa, đặc biệt với form lồng nhau, danh sách dòng hàng hoặc thao tác nhập hàng loạt.

Ví dụ một yêu cầu tạo đơn:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <test-token>
Content-Type: application/json
Accept: application/problem+json

{
  "customer": {
    "email": "not-an-email"
  },
  "items": [
    {"sku": "BOOK-01", "quantity": 0},
    {"sku": "PEN-02", "quantity": 2}
  ],
  "currency": "VND"
}
~~~

Ở đây có hai lỗi cụ thể:

- Giá trị email không hợp lệ tại đường dẫn **/customer/email**.
- Số lượng bằng 0 tại đường dẫn **/items/0/quantity**, tức phần tử đầu tiên của mảng items.

Một phản hồi hữu ích cần giúp client trả lời **điều gì sai, sai ở vị trí nào, cần sửa theo quy tắc nào**, đồng thời không tiết lộ dữ liệu nhạy cảm hoặc chi tiết triển khai nội bộ.

Trong module thiết kế REST API, việc mô tả lỗi theo trường, phần tử và đường dẫn phải gắn với **HTTP status**, **hợp đồng JSON**, **schema/OpenAPI**, **validation**, **phân quyền** và **kiểm thử client–server**. Một error format tốt là một phần của hợp đồng công khai, không phải chỉ là nội dung log.

> **Nguyên tắc:** Status HTTP mô tả kết quả ở cấp request; chi tiết có cấu trúc chỉ ra các vị trí sai bên trong request. Hai lớp thông tin bổ sung cho nhau, không thay thế nhau.

## 2. Phân biệt ba mức lỗi

| Mức lỗi | Câu hỏi trả lời | Ví dụ | Vị trí minh họa |
|---|---|---|---|
| **Theo trường (field-level)** | Thuộc tính nào không đúng quy tắc? | email sai định dạng, quantity nhỏ hơn 1 | /customer/email, /items/0/quantity |
| **Theo phần tử (element-level)** | Phần tử nào trong array/list/map có vấn đề? | Dòng hàng thứ ba có SKU trùng, phần tử thứ hai không hợp lệ | /items/2, /items/1 |
| **Theo đường dẫn dữ liệu (path-level)** | Vị trí trong cây JSON hoặc vị trí đầu vào ở đâu? | nested object, array nhiều cấp, query param | /addresses/1/postalCode; query.page |

Ba mức này không đối lập. Một lỗi theo trường có thể nằm **bên trong một phần tử của mảng**, vì vậy đường dẫn kết hợp cả tên trường lẫn chỉ số phần tử.

Cũng cần phân biệt vị trí lỗi với loại quy tắc:

- **Syntactic error:** JSON không phân tích cú pháp được, sai content type hoặc sai kiểu tại một vị trí.
- **Constraint violation:** JSON hợp lệ nhưng vi phạm quy tắc trường, ví dụ số lượng phải lớn hơn 0.
- **Cross-field invariant:** hai hay nhiều trường cần được kiểm tra cùng nhau, ví dụ endAt phải sau startAt.
- **Cross-element invariant:** hai phần tử cùng danh sách bị trùng SKU hoặc tổng tỷ lệ phân bổ vượt 100%.
- **Resource/business conflict:** trạng thái hiện có trong hệ thống xung đột với yêu cầu, ví dụ mã đơn đã được sử dụng.

**Không gán mọi lỗi vào một trường tùy ý** nếu bản chất là ràng buộc toàn request. Client cần biết lỗi thuộc một ô nhập, một dòng dữ liệu hay toàn bộ biểu mẫu.

## 3. Hợp đồng lỗi nên gồm những gì?

Một API có thể sử dụng định dạng **Problem Details for HTTP APIs** theo RFC 9457 với media type **application/problem+json**. Chuẩn định nghĩa các trường như type, title, status, detail và instance; các trường mở rộng giúp biểu diễn chi tiết validation.

**Quan trọng:** RFC 9457 **không chuẩn hóa sẵn** một mảng tên invalid-params với cấu trúc cố định. Nếu API dùng invalid-params, đó là một **extension do API định nghĩa và tài liệu hóa**; client không nên mặc định mọi API Problem Details đều có trường này.

Ví dụ phản hồi theo hợp đồng được chọn cho bài học:

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: req-7c91

{
  "type": "https://api.example.test/problems/validation-failed",
  "title": "Validation failed",
  "status": 422,
  "detail": "Yêu cầu có 2 lỗi cần sửa",
  "instance": "/api/orders",
  "requestId": "req-7c91",
  "invalid-params": [
    {
      "code": "EMAIL_INVALID",
      "message": "Email không đúng định dạng",
      "source": {
        "in": "body",
        "path": "/customer/email"
      }
    },
    {
      "code": "QUANTITY_MIN",
      "message": "Số lượng phải lớn hơn hoặc bằng 1",
      "source": {
        "in": "body",
        "path": "/items/0/quantity"
      },
      "constraint": {
        "min": 1
      }
    }
  ]
}
~~~

Ví dụ chọn 422 vì server đọc được JSON, hiểu kiểu nội dung nhưng không thể xử lý các yêu cầu ngữ nghĩa đã nhận. Một số API sử dụng 400 cho validation; điều quan trọng là **định nghĩa chính sách nhất quán**, không phải mặc định 422 là bắt buộc cho mọi lỗi trường.

### 3.1. Các trường ở mức Problem Details

| Trường | Ngữ nghĩa | Khuyến nghị |
|---|---|---|
| **type** | URI định danh loại vấn đề | Dùng URI ổn định, có thể dẫn đến tài liệu của loại lỗi |
| **title** | Tiêu đề ngắn của loại vấn đề | Ổn định theo type, không chứa dữ liệu bí mật |
| **status** | Mã HTTP của lỗi | Phải khớp status line của phản hồi |
| **detail** | Mô tả lỗi của lần xử lý cụ thể | Hữu ích nhưng không làm hợp đồng máy phụ thuộc vào câu văn |
| **instance** | Tham chiếu lần xảy ra vấn đề | Có thể là URI; không đưa dữ liệu nhạy cảm vào path/query |
| **requestId** | Extension phục vụ đối chiếu log/trace | ID không được xem là bằng chứng quyền truy cập |
| **invalid-params** | Extension danh sách lỗi chi tiết | Phải có schema, quy tắc định vị và giới hạn kích thước rõ |

Trong ứng dụng thực tế, requestId còn có thể được đưa vào header hoặc correlation context. Nếu ID xuất hiện ở nhiều nơi, các giá trị cần nhất quán.

### 3.2. Các trường của từng lỗi chi tiết

| Trường | Ví dụ | Vai trò |
|---|---|---|
| **code** | QUANTITY_MIN | Mã ổn định để client xử lý theo quy tắc |
| **message** | Số lượng phải lớn hơn hoặc bằng 1 | Thông điệp dễ hiểu, có thể bản địa hóa |
| **source.in** | body, query, path, header | Nơi lấy dữ liệu đầu vào |
| **source.path** | /items/0/quantity | Vị trí trong cây body theo quy ước của API |
| **source.name** | page, X-Correlation-Id | Tên tham số khi nguồn không phải JSON body |
| **constraint** | {"min":1} | Metadata an toàn giúp client hướng dẫn sửa |
| **relatedPaths** | ["/startAt", "/endAt"] | Những trường liên quan trong lỗi ràng buộc chéo |
| **itemId** | item-client-42 | Định danh phần tử ổn định nếu client đã cung cấp và được phép trả |

Không bắt buộc phải có tất cả trường cho mỗi lỗi. Ví dụ request body sai cú pháp có thể không xác định được một trường hợp lệ; lỗi liên quan quy tắc toàn bộ order có thể **không có source.path**.

**Mã code là hợp đồng máy; message là thông điệp dành cho người đọc.** Client nên ưu tiên code và source để xử lý, thay vì so khớp chính xác chuỗi thông báo vốn có thể thay đổi theo ngôn ngữ.

## 4. Đường dẫn dữ liệu: JSON Pointer và quy ước path

Một cách mô tả vị trí trong JSON là **JSON Pointer** theo RFC 6901. Cú pháp của nó dùng các đoạn bắt đầu bằng dấu gạch chéo và ngăn nhau bằng ký tự /.

Với JSON:

~~~json
{
  "customer": {
    "email": "bad-email"
  },
  "items": [
    {"sku": "A", "quantity": 1},
    {"sku": "B", "quantity": 0}
  ]
}
~~~

Các JSON Pointer hợp lệ tới giá trị đang tồn tại:

| Pointer | Vị trí | Giá trị |
|---|---|---|
| /customer | Object customer | Object chứa email |
| /customer/email | Trường email | "bad-email" |
| /items | Cả mảng items | Array |
| /items/0 | Phần tử đầu tiên | Object SKU A |
| /items/1/quantity | Trường quantity của phần tử thứ hai | 0 |
| Chuỗi rỗng | Toàn bộ tài liệu JSON | Root object |

**Chỉ số mảng bắt đầu từ 0**: /items/0 là phần tử thứ nhất, /items/1 là phần tử thứ hai. Không dùng /items/1 để chỉ dòng đầu tiên theo cách đánh số trên UI.

### 4.1. Quy tắc escape ký tự

Trong **tên thành phần** của JSON Pointer:

- Ký tự dấu ngã **~** được escape thành **~0**.
- Ký tự dấu gạch chéo **/** được escape thành **~1**.

Ví dụ:

~~~json
{
  "tax/rate": 10,
  "display~name": "Sổ tay",
  "items": [
    {
      "a/b~c": "x"
    }
  ]
}
~~~

| Tên hoặc vị trí thực | JSON Pointer |
|---|---|
| Thuộc tính tax/rate | /tax~1rate |
| Thuộc tính display~name | /display~0name |
| Thuộc tính a/b~c ở phần tử đầu | /items/0/a~1b~0c |

Khi giải mã, thứ tự đúng là **~1 → /** rồi **~0 → ~**, để tránh diễn giải sai chuỗi như ~01. Khi mã hóa, thay **~ → ~0** trước rồi **/ → ~1**.

### 4.2. Pointer và các dạng đường dẫn khác không giống nhau

| Dạng | Ví dụ | Lưu ý |
|---|---|---|
| JSON Pointer | /items/1/quantity | RFC 6901; dùng dấu / và escape ~0, ~1 |
| Bean Validation / Spring field path | items[1].quantity | Thường xuất hiện trong lỗi binding của Java |
| JSONPath | $.items[1].quantity | Ngôn ngữ truy vấn khác; cú pháp/khả năng biểu đạt khác |
| Đường dẫn tham số HTTP | query.page hoặc header.X-Request-Id | Không phải node trong JSON body |

Không đưa field path của framework vào hợp đồng công khai mà không quy định cú pháp. Client JavaScript, iOS hoặc hệ thống đối tác có thể không hiểu biểu thức kiểu items[1].quantity.

### 4.3. Trường thiếu không tạo ra JSON Pointer tới giá trị tồn tại

Giả sử body là:

~~~json
{
  "customer": {
    "name": "Lan"
  }
}
~~~

Trường customer.email **không có**. Chuỗi /customer/email trông giống JSON Pointer nhưng **không resolve được tới giá trị đang tồn tại**. Đây là khác biệt quan trọng:

- **Con trỏ tới dữ liệu thực tế:** /customer/name hoặc /customer.
- **Đường dẫn của trường mà schema mong đợi:** /customer/email, kể cả khi chưa có.

Nếu API tuyên bố source.pointer là **JSON Pointer chuẩn trỏ đến giá trị trong body**, không được đưa /customer/email rồi giả định nó hợp lệ. Cách diễn đạt an toàn:

~~~json
{
  "code": "REQUIRED",
  "message": "Thiếu trường email",
  "source": {
    "in": "body",
    "pointer": "/customer"
  },
  "missingProperty": "email"
}
~~~

Một thiết kế khác là **định nghĩa source.path như đường dẫn đến vị trí mong đợi**, cho phép path chưa tồn tại, và ghi rõ đây là **quy ước ứng dụng dùng cú pháp JSON Pointer**, không bảo đảm một JSON Pointer có thể resolve được. Ví dụ của bài học dùng source.path theo quy ước này, còn source.pointer chỉ dùng khi muốn khẳng định con trỏ trỏ đến giá trị tồn tại.

Với lỗi phần tử mảng thiếu trường, có thể dùng pointer tới parent /items/1 và missingProperty = "quantity". Cách này đặc biệt cần lưu ý nếu tích hợp với chuẩn **JSON:API**, vì đối tượng source.pointer của JSON:API được kỳ vọng chỉ đến một giá trị **tồn tại** trong request.

### 4.4. Trường không có giá trị và trường có null

Đây là hai tình huống khác nhau:

~~~json
{"quantity": null}
~~~

~~~json
{}
~~~

Đối với null, /quantity có thể trỏ đến một giá trị tồn tại là null. Đối với trường bị thiếu, /quantity không trỏ được tới giá trị. Hợp đồng có thể quy định cả hai đều vi phạm REQUIRED, nhưng thông điệp, mã lỗi và vị trí cần được thiết kế rõ.

### 4.5. Định danh phần tử: index hay ID?

Trong array, index là cách định vị phù hợp với **request đã được gửi**. Nhưng nếu client tự sắp xếp lại các dòng hàng trước khi hiển thị lỗi, /items/2 sẽ không còn chỉ đúng dòng cũ.

Có thể hỗ trợ định danh client cung cấp:

~~~json
{
  "items": [
    {"clientLineId": "line-a", "sku": "A", "quantity": 2},
    {"clientLineId": "line-b", "sku": "B", "quantity": 0}
  ]
}
~~~

Phản hồi lỗi có thể thêm itemId = "line-b", cùng source.path = "/items/1/quantity". Client nên map lại lỗi **theo phiên bản form đã gửi**, không sử dụng một index cũ để đánh dấu nhầm dữ liệu đã reorder. Chỉ trả itemId nếu nó xuất phát từ nguồn đáng tin trong phạm vi request hoặc được phép tiết lộ.

## 5. Chọn mã HTTP cho loại lỗi phù hợp

| Tình huống | Mã thường phù hợp | Vì sao |
|---|---|---|
| JSON sai cú pháp, không parse được | **400 Bad Request** | Server không đọc được cấu trúc request đúng yêu cầu |
| Query param page không parse được thành số | **400 Bad Request** | Tham số đầu vào không hợp lệ |
| JSON parse được nhưng email/quantity không đạt ràng buộc | **400 hoặc 422 Unprocessable Content** theo hợp đồng | Cả hai lựa chọn xuất hiện trong API thực; cần chính sách nhất quán |
| Đơn tạo mới mâu thuẫn trạng thái tài nguyên hiện hữu, như key đã chiếm dụng | **409 Conflict** nếu phản ánh xung đột trạng thái | Lỗi gắn với trạng thái hệ thống, không chỉ cú pháp |
| Precondition If-Match không đạt | **412 Precondition Failed** | Đừng thay bằng lỗi field chung |
| Không có thông tin xác thực hợp lệ | **401 Unauthorized** | Cần challenge WWW-Authenticate phù hợp |
| Đã xác thực nhưng không đủ quyền | **403 Forbidden**, hoặc 404 nếu chủ đích che giấu | Không trả tên trường hoặc trạng thái tài nguyên nhạy cảm |
| Đường dẫn tài nguyên không tồn tại | **404 Not Found** | Không có tài nguyên được phục vụ/được phép thấy |
| Body quá lớn so với giới hạn server | **413 Content Too Large** | Không diễn đạt như sai trường quantity |
| Content-Type request không được hỗ trợ | **415 Unsupported Media Type** | Khác với JSON hợp lệ nhưng nội dung sai |
| Rate limit vượt ngưỡng | **429 Too Many Requests** | Có thể dùng Retry-After theo chính sách |
| DB timeout hay lỗi lập trình | **5xx thích hợp** | Không biến lỗi server thành validation error của client |

Theo RFC 9110, **422 Unprocessable Content** áp dụng khi server hiểu loại nội dung, cú pháp request đúng nhưng không thể xử lý các chỉ dẫn chứa trong nội dung đó. API có thể chọn 422 cho lỗi validation ngữ nghĩa; không bắt buộc tách từng kiểu lỗi ra mã khác nhau.

**Quy ước dùng xuyên suốt ví dụ của bài:** 400 cho JSON/parameter không hợp lệ ở tầng cú pháp; 422 cho constraint của body đã parse; 409 cho xung đột trạng thái tài nguyên. Đây là **quy ước minh họa của một API**, không phải yêu cầu bắt buộc của HTTP hoặc Spring.

### 5.1. Vì sao không trả HTTP 200 kèm success=false?

Ví dụ không nên dùng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"success":false,"message":"Invalid email"}
~~~

Nếu không có lý do hợp đồng đặc biệt, 200 làm sai tín hiệu cho gateway, monitoring, retry policy, SDK và client. Với yêu cầu không thể xử lý do lỗi đầu vào, cần dùng **4xx phù hợp** và body lỗi chuẩn hóa. HTTP status phải nhất quán với Problem Details status.

### 5.2. Không gắn validation detail vào lỗi xác thực

Không nên trả danh sách trường thiếu cho một request **chưa có quyền truy cập** nếu làm như vậy tiết lộ schema, định danh hoặc trạng thái dữ liệu ngoài phạm vi được phép. Tùy thiết kế, authentication và authorization cần được đánh giá trước khi đưa ra thông tin chi tiết.

Ngoài ra, một số lỗi có thể được phát hiện sớm ở gateway trước khi request đến ứng dụng, như 413 hoặc 415. Hợp đồng lỗi nên xác định mức nhất quán kỳ vọng giữa gateway và ứng dụng, nhưng không hứa mọi 4xx đều có cùng danh sách field errors.

## 6. Lỗi theo trường: validation đơn giản nhưng phải đủ ngữ nghĩa

### 6.1. Trường bắt buộc, định dạng và miền giá trị

~~~json
{
  "customer": {"email": "bad-email"},
  "items": [{"sku": "A", "quantity": 0}],
  "currency": "VND"
}
~~~

Các loại lỗi:

| Code ví dụ | Vị trí | Ý nghĩa |
|---|---|---|
| REQUIRED | /customer/email nếu thiếu | Trường bắt buộc không được cung cấp |
| EMAIL_INVALID | /customer/email nếu hiện có nhưng sai định dạng | Không tuân thủ định dạng email |
| QUANTITY_MIN | /items/0/quantity | Giá trị nhỏ hơn giới hạn |
| ENUM_UNSUPPORTED | /currency | Mã tiền tệ không được hỗ trợ trong hợp đồng |
| TYPE_MISMATCH | /items/0/quantity | Kiểu dữ liệu không phù hợp schema |
| STRING_LENGTH_MAX | /customer/name | Chuỗi vượt độ dài giới hạn |

**Không nên dùng một code duy nhất INVALID cho mọi loại lỗi** nếu client cần xử lý khác nhau. Tuy nhiên, tránh thiết kế hàng trăm code phụ thuộc sát vào implementation của Bean Validation. Mỗi mã công khai cần rõ ý nghĩa, ổn định và được tài liệu hóa.

### 6.2. Một trường có thể có nhiều ràng buộc

Ví dụ tên người dùng phải không rỗng, có độ dài tối thiểu và không chứa ký tự bị cấm. Có hai chính sách hợp lệ:

- Trả **tất cả lỗi có thể xác định** cho một trường trong một lần validation.
- Trả **một lỗi ưu tiên** cho mỗi trường, giúp UI ít bị ngập thông báo.

Nếu API có thứ tự ưu tiên, cần công bố/kiểm thử tính ổn định, chẳng hạn REQUIRED trước FORMAT rồi RANGE. Không phụ thuộc vào thứ tự phát hiện của framework hoặc thứ tự iteration của tập kết quả vốn có thể thay đổi.

### 6.3. Không trả rejectedValue tùy tiện

Giá trị bị từ chối đôi khi là token, số thẻ, mật khẩu, dữ liệu sức khỏe hoặc thông tin cá nhân. Phản hồi và log validation **không nên echo nguyên giá trị** trừ khi có lý do đã đánh giá bảo mật. Một message như "Giá trị không được chấp nhận" thường an toàn hơn "Số thẻ 4111... không hợp lệ".

## 7. Lỗi theo phần tử trong collection

Lỗi phần tử xuất hiện ở mảng đơn giản, danh sách object hoặc dữ liệu nhập hàng loạt.

### 7.1. Mảng giá trị đơn giản

~~~json
{
  "tags": ["java", "", "api"]
}
~~~

Nếu tag không được rỗng, vị trí của lỗi là **/tags/1**. Đây là lỗi theo **phần tử**, không có trường con.

~~~json
{
  "code": "TAG_BLANK",
  "message": "Tag không được rỗng",
  "source": {"in": "body", "path": "/tags/1"}
}
~~~

### 7.2. Mảng object lồng nhau

~~~json
{
  "items": [
    {"sku": "A", "quantity": 2},
    {"sku": "B", "quantity": -1}
  ]
}
~~~

Đường dẫn lỗi là **/items/1/quantity**. Nó xác định cả **phần tử thứ hai** lẫn **thuộc tính quantity**. Trả mỗi lỗi chung tại /items sẽ khiến client không biết dòng nào cần sửa.

### 7.3. Ràng buộc giữa các phần tử

~~~json
{
  "items": [
    {"sku": "A", "quantity": 2},
    {"sku": "B", "quantity": 1},
    {"sku": "A", "quantity": 3}
  ]
}
~~~

Nếu API không chấp nhận cùng SKU xuất hiện hai lần, có thể trả:

~~~json
{
  "code": "SKU_DUPLICATED",
  "message": "SKU trùng với một dòng hàng khác",
  "source": {"in": "body", "path": "/items/2/sku"},
  "relatedPaths": ["/items/0/sku"]
}
~~~

Tùy UX, có thể đánh dấu cả hai dòng. Nhưng **relatedPaths phải dẫn tới những chỗ có liên quan thực tế**, không tạo cặp lỗi ngẫu nhiên. Nếu kiểm tra trùng dựa trên dữ liệu DB thay vì chỉ trong request, chỉ tiết lộ chi tiết mà caller có quyền biết.

### 7.4. Phần tử không tồn tại và phần tử sai kiểu

~~~json
{
  "items": [
    {"sku": "A", "quantity": 2},
    null
  ]
}
~~~

Nếu phần tử thứ hai phải là object, lỗi trỏ tới **/items/1**, vì vị trí có giá trị null thực tế. Ngược lại nếu một item object có sku nhưng **thiếu quantity**, pointer tới /items/1/quantity sẽ không resolve được; có thể trỏ tới parent /items/1 và thêm missingProperty = "quantity" như đã phân tích.

### 7.5. Danh sách nhiều tầng

~~~json
{
  "shipments": [
    {
      "packages": [
        {"dimensions": {"width": 0, "height": 20}}
      ]
    }
  ]
}
~~~

Lỗi width tại **/shipments/0/packages/0/dimensions/width**. Với dữ liệu nhiều tầng, một định dạng path thống nhất quan trọng hơn diễn đạt bằng câu như "Chiều rộng kiện hàng đầu tiên không hợp lệ".

## 8. Lỗi ràng buộc chéo và lỗi toàn request

Không phải lỗi nào cũng có một trường làm nguồn duy nhất.

### 8.1. So sánh ngày bắt đầu và ngày kết thúc

~~~json
{
  "startAt": "2026-11-20T10:00:00Z",
  "endAt": "2026-11-19T10:00:00Z"
}
~~~

Ràng buộc **endAt phải sau startAt** liên quan hai trường:

~~~json
{
  "code": "DATE_RANGE_INVALID",
  "message": "Thời điểm kết thúc phải sau thời điểm bắt đầu",
  "source": {"in": "body", "path": "/endAt"},
  "relatedPaths": ["/startAt"]
}
~~~

Việc gắn lỗi chính vào /endAt là **quy ước UI**; API có thể trả lỗi ở root và liệt kê cả hai relatedPaths nếu không có trường chính hợp lý.

### 8.2. Tổng tỉ lệ phân bổ

Nếu tổng các phần tử allocations phải bằng 100%, một lỗi có thể thuộc **toàn danh sách** thay vì phần tử cụ thể:

~~~json
{
  "code": "ALLOCATION_SUM_INVALID",
  "message": "Tổng tỉ lệ phân bổ phải bằng 100%",
  "source": {"in": "body", "path": "/allocations"},
  "constraint": {"expectedTotal": 100}
}
~~~

Chỉ gắn lỗi vào một phần tử khi có căn cứ xác định phần tử đó sai. Nếu tất cả giá trị đều hợp lệ riêng lẻ nhưng tổng sai, client thường nên hiện thông báo ở cấp collection.

### 8.3. Lỗi toàn request không có đường dẫn trường

Ví dụ một request vi phạm quy tắc nghiệp vụ "giỏ hàng phải thuộc cùng địa chỉ giao" mà không thể quy về một trường duy nhất. Có thể bỏ source.path:

~~~json
{
  "code": "CART_RULE_VIOLATION",
  "message": "Các mục trong giỏ không thể được đặt cùng một đơn",
  "source": {"in": "body"}
}
~~~

Không sử dụng chuỗi "/" để biểu diễn root nếu đang dùng JSON Pointer chuẩn: **chuỗi rỗng** mới chỉ toàn bộ document, còn "/" chỉ thuộc tính có tên rỗng của object. Trong API dùng source.path như quy ước riêng, có thể quy định cách đánh dấu lỗi global rõ ràng, chẳng hạn không có path hoặc dùng scope = "request".

## 9. Lỗi trong path parameter, query parameter và header

Không phải mọi tham số REST nằm trong JSON body. Một URI có thể chứa tham số định danh tài nguyên, query phân trang hoặc header điều kiện.

### 9.1. Lỗi query parameter

Request:

~~~http
GET /api/orders?page=-1&size=5000 HTTP/1.1
Host: api.example.test
~~~

Phản hồi minh họa:

~~~json
{
  "type": "https://api.example.test/problems/invalid-parameters",
  "title": "Invalid parameters",
  "status": 400,
  "invalid-params": [
    {
      "code": "PAGE_MIN",
      "message": "page phải từ 0 trở lên",
      "source": {"in": "query", "name": "page"}
    },
    {
      "code": "PAGE_SIZE_MAX",
      "message": "size không vượt 100",
      "source": {"in": "query", "name": "size"},
      "constraint": {"max": 100}
    }
  ]
}
~~~

Không ép source.path thành /page vì "/page" có thể bị hiểu nhầm là trường trong JSON body. Thuộc tính source.in giúp client biết phải sửa **query** chứ không phải payload.

### 9.2. Lỗi path parameter

URI /api/orders/not-a-uuid có thể vi phạm định dạng UUID mà endpoint công bố. Nếu route vẫn match và converter/validator xác định tham số sai, API có thể trả **400** với:

~~~json
{
  "code": "ORDER_ID_FORMAT",
  "message": "id phải là UUID hợp lệ",
  "source": {"in": "path", "name": "id"}
}
~~~

Lưu ý framework có thể trả 404 khi không match route hoặc 400 khi conversion thất bại; cần định nghĩa và thử nghiệm **hành vi thực**. Không đưa giá trị định danh của tài nguyên thuộc người khác vào detail khi không có quyền.

### 9.3. Lỗi header

Nếu endpoint yêu cầu Idempotency-Key theo hợp đồng:

~~~json
{
  "code": "IDEMPOTENCY_KEY_REQUIRED",
  "message": "Thiếu Idempotency-Key",
  "source": {"in": "header", "name": "Idempotency-Key"}
}
~~~

Không echo giá trị header Authorization hoặc API key trong body lỗi. Với lỗi liên quan HTTP conditional request như If-Match, cần dùng **412 Precondition Failed** khi precondition không đạt, thay vì biến thành lỗi field vô nghĩa.

### 9.4. Field name trùng ở nhiều nguồn

Body có trường page và query cũng có tham số page. Nếu chỉ trả name = "page", client khó biết phải sửa nơi nào. Mỗi lỗi cần định vị nguồn **body/query/path/header** riêng. Với multipart form-data, file upload hoặc body dạng khác JSON, hợp đồng phải quy định locator tương ứng; JSON Pointer không thể mô tả mọi dạng body.

## 10. Lỗi trong yêu cầu batch: toàn bộ thất bại hay từng phần tử thất bại?

Trong REST API, endpoint nhận một mảng không mặc nhiên có cùng ngữ nghĩa với nhiều request đơn lẻ. Hãy phân biệt **validation của cả batch** với **kết quả xử lý từng phần tử**.

### 10.1. Batch nguyên tử: tất cả thành công hoặc tất cả bị từ chối

Ví dụ POST /api/orders/batch nhận 50 dòng, server kiểm tra toàn bộ trước khi ghi. Nếu ba dòng vi phạm schema, hợp đồng quy định **không tạo bất kỳ đơn nào** và trả lỗi 422 với các path:

~~~json
{
  "type": "https://api.example.test/problems/batch-validation-failed",
  "title": "Batch validation failed",
  "status": 422,
  "detail": "Không có phần tử nào được ghi",
  "invalid-params": [
    {
      "code": "QUANTITY_MIN",
      "message": "Số lượng tối thiểu là 1",
      "source": {"in": "body", "path": "/items/3/quantity"}
    },
    {
      "code": "SKU_REQUIRED",
      "message": "SKU là bắt buộc",
      "source": {"in": "body", "path": "/items/11/sku"}
    },
    {
      "code": "PRICE_INVALID",
      "message": "Giá không hợp lệ",
      "source": {"in": "body", "path": "/items/42/price"}
    }
  ]
}
~~~

Đối với batch nguyên tử, số lượng phần tử lỗi chỉ ảnh hưởng chi tiết trả về. **Một lần POST thất bại không được âm thầm ghi 47 dòng còn lại** nếu hợp đồng đã hứa all-or-nothing. Cần kiểm soát transaction boundary, lỗi ngoài validation và tình huống mạng timeout khiến client không nhận được kết quả cuối.

### 10.2. Batch chấp nhận thành công một phần

Một API nhập dữ liệu có thể cho phép xử lý độc lập từng phần tử. Khi đó việc dùng một Problem Details 422 cấp request có thể gây hiểu nhầm rằng **không phần tử nào được xử lý**.

Một hợp đồng khác có thể trả **200** với tài liệu kết quả batch:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "batchId": "batch-42",
  "results": [
    {
      "clientItemId": "line-a",
      "status": 201,
      "resourceId": "order-a"
    },
    {
      "clientItemId": "line-b",
      "status": 422,
      "errors": [
        {
          "code": "QUANTITY_MIN",
          "message": "Số lượng tối thiểu là 1",
          "source": {"in": "body", "path": "/items/1/quantity"}
        }
      ]
    }
  ]
}
~~~

Trong ví dụ này, **200 mô tả việc yêu cầu xử lý batch đã được trả kết quả**, không có nghĩa mọi item thành công. Mã status bên trong results là phần **hợp đồng ứng dụng**. Một số API có thể dùng 207 Multi-Status (xuất phát từ WebDAV), nhưng không nên mặc định 207 là chuẩn chung cho mọi REST batch.

Nếu batch chạy bất đồng bộ, có thể trả **202 Accepted** cùng URI kiểm tra trạng thái; kết quả của từng phần tử được lấy khi job hoàn tất. Phải phân biệt rõ *request được chấp nhận* với *dữ liệu đã ghi thành công*.

### 10.3. Tránh lẫn lộn index và định danh nghiệp vụ

Đối với batch:

- **source.path** phản ánh vị trí phần tử trong **body gốc**.
- **clientItemId** có thể giúp client cập nhật một dòng sau khi người dùng sắp xếp lại danh sách.
- **resourceId** chỉ xuất hiện nếu một resource đã được tạo hoặc được phép tiết lộ.
- Khi server sắp xếp dữ liệu để tối ưu xử lý, **không dùng vị trí trong danh sách đã sắp xếp** làm path của request gốc.

### 10.4. Giới hạn số lỗi trả về

Với request hàng nghìn item, trả mọi lỗi có thể tạo response rất lớn, chậm và gây rủi ro từ input ác ý. API nên công bố:

1. Kích thước body, số item và độ sâu JSON tối đa.
2. Số invalid-params tối đa được trả, ví dụ 100 lỗi đầu tiên theo thứ tự ổn định.
3. Cách báo rằng danh sách lỗi đã bị cắt ngắn, chẳng hạn **errorsTruncated: true**.
4. Cách tiếp tục sửa: client gửi lại toàn bộ batch hoặc lấy báo cáo đầy đủ theo một job hợp lệ nếu có hỗ trợ.

Không bắt buộc tính tổng lỗi khi phải scan toàn bộ dữ liệu rất đắt đỏ. Có thể công bố giới hạn và dừng validation sớm một cách nhất quán.

## 11. Java/Spring: validation dữ liệu lồng nhau

Spring Boot hiện đại thường dùng **Jakarta Bean Validation** kết hợp Spring MVC và Jackson để đọc JSON, chuyển thành DTO rồi kiểm tra các constraint.

### 11.1. Khai báo request DTO theo contract

Ví dụ một endpoint tạo đơn bằng Java:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;

public record CreateOrderRequest(
        @NotBlank String currency,
        @NotNull @Valid CustomerInput customer,
        @NotEmpty List<@NotNull @Valid OrderItemInput> items
) {}

public record CustomerInput(
        @NotBlank @Email String email
) {}

public record OrderItemInput(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity
) {}
~~~

Các record minh họa nên đặt ở file Java phù hợp hoặc trong một lớp chứa chúng vì Java thông thường chỉ cho phép một top-level public type trên mỗi source file. Chú ý:

- **@Valid** ở customer cho phép kiểm tra nested object.
- **List<@NotNull @Valid OrderItemInput>** kiểm tra từng phần tử và từ chối phần tử null khi validator hỗ trợ container element validation theo Jakarta Validation.
- **@NotEmpty** kiểm tra danh sách không null và không rỗng, nhưng không thay thế validation từng item.
- **@NotBlank @Email** ngăn email rỗng và sai định dạng; **@NotNull @Min(1)** chặn quantity null và giá trị nhỏ hơn 1.

Với sản phẩm thực, có thể cần kiểm tra currency thuộc danh mục cho phép, độ dài SKU, số lượng item tối đa và các quy tắc nghiệp vụ không thể mô tả bằng annotation đơn giản.

Controller sử dụng @Valid:

~~~java
import jakarta.validation.Valid;
import java.net.URI;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderCommandController {
    private final OrderService service;

    OrderCommandController(OrderService service) {
        this.service = service;
    }

    @PostMapping("/api/orders")
    ResponseEntity<OrderView> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderView created = service.create(request);
        return ResponseEntity
                .created(URI.create("/api/orders/" + created.id()))
                .body(created);
    }
}
~~~

OrderService và OrderView là kiểu của ứng dụng minh họa. Controller không tự thay thế xác thực, phân quyền, idempotency và transaction trong use case tạo đơn.

### 11.2. Chuyển field path của Spring thành path công khai

Với lỗi quantity trong phần tử thứ hai, Spring BindingResult có thể cung cấp field dạng:

~~~text
items[1].quantity
~~~

Hợp đồng REST của bài dùng đường dẫn theo **cú pháp JSON Pointer**:

~~~text
/items/1/quantity
~~~

Một hàm chuyển đổi đơn giản cho **các field name thông dụng và index số**:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class FieldPaths {
    private static final Pattern SEGMENT =
            Pattern.compile("([^.\\[\\]]+)|\\[(\\d+)\\]");

    private FieldPaths() {}

    static String toBodyPath(String springField) {
        Matcher matcher = SEGMENT.matcher(springField);
        StringBuilder path = new StringBuilder();
        while (matcher.find()) {
            String segment = matcher.group(1) != null
                    ? matcher.group(1)
                    : matcher.group(2);
            path.append('/')
                    .append(segment.replace("~", "~0")
                                   .replace("/", "~1"));
        }
        return path.toString();
    }
}
~~~

Ví dụ:

| Input | Kết quả |
|---|---|
| customer.email | /customer/email |
| items[0].quantity | /items/0/quantity |
| shipments[2].packages[1].weight | /shipments/2/packages/1/weight |

**Giới hạn quan trọng của helper:** đây không phải parser hoàn chỉnh của mọi Spring property path. Nó không xử lý chính xác map keys chứa chấm, dấu ngoặc vuông, trường dùng tên JSON khác tên Java qua @JsonProperty, và mọi trường hợp deserialization phức tạp. Trong production cần map theo **wire contract của Jackson/OpenAPI** và/hoặc duyệt metadata path có cấu trúc, thay vì áp dụng regex đơn giản cho mọi dữ liệu đầu vào.

Hơn nữa, source.path ở đây là **đường dẫn mong đợi theo quy ước API**, có thể không resolve được nếu field bắt buộc bị thiếu; do đó không gọi nó là source.pointer chuẩn với bảo đảm trỏ tới giá trị tồn tại.

### 11.3. Tạo Problem Details từ MethodArgumentNotValidException

Spring có thể phát sinh **MethodArgumentNotValidException** khi @Valid @RequestBody phát hiện lỗi binding/validation đối với DTO. Ta có thể chuyển FieldError sang extension invalid-params và trả status 422 theo chính sách API.

~~~java
import java.net.URI;
import java.util.Comparator;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiValidationAdvice {

    public record Source(String in, String path) {}
    public record InvalidParam(
            String code, String message, Source source) {}

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> invalidBody(
            MethodArgumentNotValidException exception) {

        List<InvalidParam> invalidParams =
                exception.getBindingResult()
                        .getFieldErrors()
                        .stream()
                        .map(error -> new InvalidParam(
                                publicCode(error),
                                publicMessage(error),
                                new Source(
                                        "body",
                                        FieldPaths.toBodyPath(
                                                error.getField()))))
                        .sorted(Comparator
                                .comparing((InvalidParam item) ->
                                        item.source().path())
                                .thenComparing(InvalidParam::code))
                        .toList();

        ProblemDetail problem = ProblemDetail.forStatus(
                HttpStatus.UNPROCESSABLE_ENTITY);
        problem.setType(URI.create(
                "https://api.example.test/problems/validation-failed"));
        problem.setTitle("Validation failed");
        problem.setDetail("Dữ liệu trong yêu cầu chưa hợp lệ");
        problem.setProperty("invalid-params", invalidParams);

        return ResponseEntity
                .status(HttpStatus.UNPROCESSABLE_ENTITY)
                .contentType(MediaType.valueOf(
                        "application/problem+json"))
                .body(problem);
    }

    private String publicCode(FieldError error) {
        String constraint = error.getCode();
        if ("NotBlank".equals(constraint)
                || "NotNull".equals(constraint)
                || "NotEmpty".equals(constraint)) {
            return "REQUIRED";
        }
        if ("Min".equals(constraint)) {
            return "VALUE_TOO_SMALL";
        }
        if ("Email".equals(constraint)) {
            return "EMAIL_INVALID";
        }
        return "INVALID_FIELD";
    }

    private String publicMessage(FieldError error) {
        return switch (publicCode(error)) {
            case "REQUIRED" -> "Trường bắt buộc";
            case "VALUE_TOO_SMALL" -> "Giá trị nhỏ hơn giới hạn";
            case "EMAIL_INVALID" -> "Email không đúng định dạng";
            default -> "Giá trị không hợp lệ";
        };
    }
}
~~~

Điểm cần hiểu:

- **422 không phải phản hồi mặc định bắt buộc của Spring**. Handler trên chủ động đổi từ validation error thành 422 theo hợp đồng ứng dụng.
- **getFieldErrors() chỉ bao phủ lỗi gắn field**. Nếu có global/object-level error hoặc ràng buộc chéo, phải xử lý thêm getGlobalErrors() và biểu diễn không có path hoặc relatedPaths.
- **publicCode()** là phép ánh xạ minh họa. Trong production hãy thiết kế bảng ánh xạ đầy đủ theo quy tắc nghiệp vụ, không để client phụ thuộc tên constraint như NotBlank/Min của Java.
- **publicMessage()** cố ý không echo rejectedValue hoặc exception message từ parser. Có thể bản địa hóa qua message catalog nhưng giữ code ổn định.
- Danh sách được sắp theo path và code để giảm kết quả dao động. Cần thêm **giới hạn số lỗi** trước khi trả cho client khi dữ liệu lớn.
- Ở nhiều ứng dụng, các ngoại lệ validation khác xảy ra ở query/path/header hoặc method-level validation. Chúng cần handler riêng để trả đúng source.in và không bị nhầm là body.
- Mã ví dụ chỉ minh họa đường xử lý @RequestBody DTO thông thường; khi áp dụng cần kiểm tra phiên bản Spring, cấu hình Jackson, exception mapping và test thực tế.

### 11.4. JSON sai cú pháp và sai kiểu không luôn tạo FieldError

Request:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"items":[{"sku":"A","quantity":1}
~~~

Body thiếu dấu đóng mảng/object nên **không parse được**. Trong Spring MVC, lỗi có thể phát sinh dưới dạng HttpMessageNotReadableException, trước khi Bean Validation chạy. Trả **400 Bad Request** với thông điệp tổng quát thay vì khẳng định có FieldError chính xác.

Tương tự:

~~~json
{"items":[{"sku":"A","quantity":"abc"}]}
~~~

Jackson có thể cung cấp path từ exception tới thuộc tính sai kiểu, nhưng cần **lọc, chuẩn hóa và đánh giá bảo mật** trước khi công bố. Không trả stack trace, tên class Java hoặc nội dung raw JSON từ exception ra ngoài.

Đặc biệt, không dựa vào thứ tự do framework phát sinh nhiều lỗi để cam kết một form luôn nhận lỗi theo thứ tự mong muốn; định nghĩa quy tắc sort và kiểm thử.

### 11.5. Validation cho query và path trong Spring

Một controller có thể kiểm tra page và size:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
class OrderSearchController {
    private final OrderSearchService searchService;

    OrderSearchController(OrderSearchService searchService) {
        this.searchService = searchService;
    }

    @GetMapping("/api/orders")
    OrderPage find(
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20")
            @Min(1) @Max(100) int size) {
        return searchService.find(page, size);
    }
}
~~~

Các kiểu OrderSearchService và OrderPage là kiểu của ứng dụng. Cơ chế method validation và ngoại lệ có thể thay đổi theo cấu hình/phiên bản Spring; ví dụ Spring Framework 6.1 có **HandlerMethodValidationException** trong một số trường hợp, còn conversion có thể tạo ngoại lệ khác. Handler cần map tham số nguồn query thay vì biến nó thành /page của JSON body.

Ngoài mã trạng thái, hãy kiểm tra Spring Security và permission cho collection. Nếu người gọi chưa được phép biết dữ liệu, không ưu tiên trả hàng loạt chi tiết validation làm lộ cấu trúc/giá trị nhạy cảm.

## 12. Thiết kế schema OpenAPI cho lỗi chi tiết

Để SDK và client không phải đoán tên field, error extension cần được định nghĩa trong **OpenAPI** giống các response thành công.

Ví dụ OpenAPI 3.x rút gọn:

~~~yaml
paths:
  /api/orders:
    post:
      summary: Create order
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Order created
        '400':
          description: Malformed JSON or invalid request parameter
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
        '422':
          description: Request validation failed
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
components:
  schemas:
    CreateOrderRequest:
      type: object
      required: [currency, customer, items]
      properties:
        currency:
          type: string
        customer:
          type: object
        items:
          type: array
          minItems: 1
          items:
            type: object
    ApiProblem:
      type: object
      required: [type, title, status]
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
        requestId:
          type: string
        invalid-params:
          type: array
          items:
            $ref: '#/components/schemas/InvalidParam'
    InvalidParam:
      type: object
      required: [code, message]
      properties:
        code:
          type: string
        message:
          type: string
        source:
          $ref: '#/components/schemas/InvalidParamSource'
        relatedPaths:
          type: array
          items:
            type: string
        missingProperty:
          type: string
    InvalidParamSource:
      type: object
      properties:
        in:
          type: string
          enum: [body, query, path, header]
        path:
          type: string
          description: >
            API-specific expected body path using JSON Pointer syntax.
            May refer to a missing member; not guaranteed to resolve.
        pointer:
          type: string
          description: >
            RFC 6901 JSON Pointer to an existing request JSON value.
        name:
          type: string
          description: Query, path or header parameter name.
~~~

Đây là **đoạn schema minh họa**, chưa thay thế một tài liệu OpenAPI hoàn chỉnh. Trong production cần hoàn thiện CreateOrderRequest, securitySchemes, các status như 401/403/409/415, ví dụ và quy tắc tương thích. Chú ý tên **invalid-params** có dấu gạch nối, nên các client có thể cần truy cập theo key chứ không dùng property notation trực tiếp ở một số ngôn ngữ.

### 12.1. Hợp đồng cần ghi thêm các quy ước

Một schema đơn thuần không đủ. Tài liệu phải nói:

1. Mã HTTP nào dành cho lỗi cú pháp, lỗi validation và xung đột trạng thái?
2. Mã code nào ổn định và được version như thế nào?
3. source.path theo cú pháp nào? Có cho phép chỉ vị trí **chưa tồn tại** không?
4. Index mảng bắt đầu từ 0 hay 1? Có sử dụng clientItemId không?
5. Phân biệt source.in cho body/query/path/header ra sao?
6. Có trả nhiều lỗi cho cùng một trường? Thứ tự lỗi có ổn định không?
7. Có giới hạn số lượng lỗi? Client biết kết quả bị cắt bằng trường nào?
8. Lỗi nghiệp vụ liên quan nhiều trường hoặc nhiều phần tử được biểu diễn thế nào?
9. Thông điệp có dịch theo Accept-Language không? Code có giữ nguyên không?
10. Có những trường nào bị cấm xuất ra vì bảo mật và riêng tư?

### 12.2. Tính tương thích khi thay đổi API

Đổi tên source.path thành field hoặc thay index 0-based bằng 1-based là **thay đổi hợp đồng có khả năng phá client**, dù status HTTP không thay. Cần versioning hoặc thay đổi có tương thích; cập nhật OpenAPI, SDK, UI và consumer contract tests.

Client nên chịu được các **extension field** mới không ảnh hưởng ý nghĩa cũ, nhưng không nên bị buộc phụ thuộc vào detail hoặc message có thể bản địa hóa. Đối với error code mới, UI cần hành vi fallback an toàn.

## 13. Bảo mật, riêng tư và chống lạm dụng

Thông báo validation càng chi tiết càng hữu ích cho client, nhưng cũng có thể tiết lộ nội bộ hoặc giúp người không có quyền dò dữ liệu.

### 13.1. Không công bố dữ liệu bị từ chối

Tránh:

~~~json
{
  "code": "CARD_NUMBER_INVALID",
  "message": "Số thẻ 4111111111111111 không hợp lệ",
  "rejectedValue": "4111111111111111"
}
~~~

Thay vào đó:

~~~json
{
  "code": "PAYMENT_INPUT_INVALID",
  "message": "Thông tin thanh toán không hợp lệ",
  "source": {"in": "body", "path": "/payment"}
}
~~~

Nếu cần chi tiết hơn, hãy trả chỉ những metadata đã được đánh giá an toàn, không ghi secret trong URL, log, trace hoặc exception message. Ngay cả tên field cũng có thể tiết lộ một tính năng nội bộ mà người gọi không được phép biết; authorization policy quyết định mức chi tiết có thể công bố.

### 13.2. Không để lỗi validation tiết lộ tài nguyên của người khác

Ví dụ API đặt hàng thuộc tenant A nhưng client gửi productId của tenant B. Thay vì trả:

~~~text
Product 987 tồn tại nhưng thuộc tenant B.
~~~

hãy dùng thông điệp theo chính sách:

~~~json
{
  "code": "PRODUCT_NOT_AVAILABLE",
  "message": "Mặt hàng không khả dụng",
  "source": {"in": "body", "path": "/items/0/productId"}
}
~~~

Mã HTTP có thể là 404, 422 hoặc 403 theo contract/resource model và yêu cầu che giấu, không áp đặt 422 nếu nghiệp vụ cần tránh lộ sự tồn tại. Áp dụng kiểm tra quyền ở truy vấn hoặc tầng domain, không chỉ sửa câu chữ.

### 13.3. Ngăn validation trở thành điểm tiêu thụ tài nguyên vô hạn

Các rủi ro:

- Body cực lớn, mảng hàng triệu phần tử hoặc JSON lồng quá sâu.
- Regex validation gây xử lý lâu trên chuỗi bất thường.
- Trả hàng nghìn lỗi chi tiết, chiếm CPU/băng thông.
- Log toàn bộ payload lỗi và tạo chi phí observability quá lớn.
- Nhiều request thử từng giá trị để dò tài nguyên hoặc quy tắc bảo mật.

Giảm rủi ro bằng body size limit, giới hạn collection/depth, validation có thời gian phù hợp, cap số lỗi, rate limiting, metrics và logging có phân loại. Với API public, cân nhắc chống enumeration và không tiết lộ constraint nhạy cảm khi chưa xác thực.

### 13.4. Request ID phục vụ điều tra, không phải credential

RequestId/correlationId giúp liên hệ phản hồi với trace nội bộ:

~~~http
X-Request-Id: req-7c91
~~~

Giá trị này **không thay thế authentication hay authorization**. Không để người dùng dùng requestId để truy vấn log của người khác nếu không có quyền. Trên log nội bộ, có thể ghi field path, code, status, route và latency; tránh ghi nguyên rejectedValue hoặc body nhạy cảm.

## 14. Client sử dụng lỗi chi tiết như thế nào?

Giả sử một form có các trường email và mảng items; client nhận response 422.

Quy trình hiển thị gợi ý:

1. Kiểm tra **HTTP status**, Content-Type và loại Problem Details.
2. Đọc extension invalid-params nếu có, không mặc định mọi lỗi đều chứa mảng.
3. Dựa vào **code** và source.in/path để phân loại lỗi cho form, dòng dữ liệu hoặc thông báo toàn trang.
4. Ánh xạ path vào **snapshot dữ liệu của request đã gửi**, không map mù vào trạng thái form vừa bị thay đổi hoặc reorder.
5. Bản địa hóa message nếu client có bảng dịch theo code; dùng message của server làm fallback an toàn.
6. Với lỗi không có path hoặc không nhận diện được code, hiển thị thông báo tổng quát thay vì bỏ qua.
7. Nếu lỗi xảy ra do timeout hoặc 5xx, không hiển thị như lỗi người dùng nhập sai; áp dụng retry/backoff theo hợp đồng.

### 14.1. Pseudocode ánh xạ lỗi vào UI

~~~text
handleResponse(response, submittedFormSnapshot):
    if response.status == 401:
        requestAuthentication()
        return

    if response.status == 403:
        showPermissionMessage()
        return

    if response.status not in [400, 422] or
       response.contentType != "application/problem+json":
        showGeneralFailure()
        return

    problem = parseProblem(response.body)
    errors = problem["invalid-params"] or []

    for error in errors:
        location = error.source
        if location.in == "body" and
           isRecognizedPath(location.path, submittedFormSnapshot):
            showFieldOrItemError(location.path, error.code, error.message)
        else if location.in in ["query", "path", "header"]:
            showParameterError(location.in, location.name, error)
        else:
            showFormError(error)

    if errors is empty:
        showGeneralFailure(problem.title, problem.detail)
~~~

Đây là pseudocode, không phải thư viện chạy trực tiếp. Client không nên tự parse một đường dẫn không tin cậy thành code có thể thực thi, không truy cập prototype/dynamic property theo cách thiếu kiểm soát và không để message server trở thành HTML chưa escape.

### 14.2. Trường hợp nhiều request kiểm tra đồng thời

Trong ứng dụng web, người dùng có thể gửi bản form A rồi sửa thành B trước khi phản hồi A tới. Nếu gắn lỗi từ A trực tiếp lên B, UI có thể hiển thị sai trường hoặc sai nội dung. Nên gắn phản hồi với **submission ID** hoặc snapshot của request, bỏ qua phản hồi cũ không còn liên quan hoặc hiển thị rõ lỗi của phiên gửi trước.

## 15. Kiểm thử lỗi theo trường và đường dẫn

### 15.1. Ma trận test tối thiểu

| Test | Dữ liệu gửi | Status kỳ vọng trong ví dụ | Điều cần xác minh |
|---|---|---|---|
| JSON thiếu dấu đóng | JSON malformed | 400 | Không trả stack trace, không gán path bịa |
| email sai định dạng | customer.email = invalid | 422 | EMAIL_INVALID và /customer/email |
| quantity = 0 | items[0].quantity = 0 | 422 | VALUE_TOO_SMALL và /items/0/quantity |
| quantity = null | items[0].quantity = null | 422 | REQUIRED; path chỉ đúng vị trí |
| quantity bị bỏ qua | items[0] không có quantity | 422 | Không gọi path thiếu là pointer resolve được |
| Item null | items[1] = null | 422 | Lỗi phần tử /items/1 |
| Hai SKU trùng | items[2].sku trùng items[0].sku | 422 | primary path và relatedPaths hợp lệ |
| endAt trước startAt | Hai trường hợp lệ riêng | 422 | Lỗi cross-field |
| page âm | GET ?page=-1 | 400 | source.in=query, name=page |
| Token thiếu | Không có Authorization | 401 | Không lộ dữ liệu hoặc cấu trúc nhạy cảm |
| Scope không đủ | Token hợp lệ nhưng bị cấm | 403 hoặc 404 theo policy | Không để lộ field/rejectedValue |
| Body cực lớn | Vượt cấu hình giới hạn | 413 | Không xử lý tiếp batch |
| Batch atomic lỗi một item | Một phần tử sai | 422 | Không có record nào được ghi |
| Batch partial | Một item hợp lệ, một item sai | 200/202 theo contract | Kết quả từng item, không nói tất cả thành công |

### 15.2. Ví dụ test hợp đồng với MockMvc

Test fragment dưới đây giả định đã khởi tạo MockMvc, controller và validator phù hợp; cần cấu hình authentication hợp lệ hoặc môi trường test đúng với endpoint thực.

~~~java
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;

import org.junit.jupiter.api.Test;

// Đặt trong class test có trường mockMvc:
@Test
void invalidNestedFieldsReturnLocations() throws Exception {
    mockMvc.perform(post("/api/orders")
            .contentType("application/json")
            .content("""
                {
                  "currency": "VND",
                  "customer": {"email": "not-an-email"},
                  "items": [
                    {"sku": "A", "quantity": 0}
                  ]
                }
                """))
        .andExpect(status().isUnprocessableEntity())
        .andExpect(content().contentTypeCompatibleWith(
                "application/problem+json"))
        .andExpect(jsonPath("$.status").value(422))
        .andExpect(jsonPath(
                "$['invalid-params'][0].source.path")
                .value("/customer/email"))
        .andExpect(jsonPath(
                "$['invalid-params'][1].source.path")
                .value("/items/0/quantity"));
}
~~~

Thứ tự hai lỗi trong test dựa trên **quy tắc sort theo path** của handler minh họa. Nếu API không cam kết thứ tự, test nên tìm theo code/path thay vì yêu cầu index cố định. Text block Java yêu cầu phiên bản Java hỗ trợ cú pháp đó; có thể dùng String thông thường trong dự án cũ.

Ngoài response, cần kiểm tra **không có side effect** khi validation thất bại: không tạo order, không phát event thanh toán, không ghi dữ liệu nhạy cảm vào log.

### 15.3. Kiểm thử với curl

~~~bash
curl -i \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/problem+json' \
  -H 'Authorization: Bearer <test-token>' \
  --data '{"currency":"VND","customer":{"email":"bad-email"},"items":[{"sku":"A","quantity":0}]}' \
  https://api.example.test/api/orders
~~~

Chỉ sử dụng môi trường, token và dữ liệu thử nghiệm được phép. Nếu dùng flag verbose hoặc ghi lại response/log, cần bảo vệ credential và thông tin nhạy cảm.

### 15.4. Contract testing và compatibility

Consumer contract tests nên xác minh:

- Status và media type đúng.
- Field type/title/status của Problem Details nhất quán.
- invalid-params có schema và source đúng.
- Mã code không bị đổi tùy tiện.
- JSON Pointer escape chính xác với tên có "/" và "~".
- Index array theo request gốc, kể cả khi server xử lý/sort lại.
- Missing field được diễn đạt theo đúng quy ước, không gán pointer sai.
- Client xử lý được lỗi global, lỗi không có path và code chưa biết.
- Không lộ rejectedValue, class name, stack trace hay dữ liệu khác tenant.
- Bounded response khi một request chứa nhiều lỗi.

## 16. Bài tập thực hành

### Bài 1 — Xác định đường dẫn JSON

Cho payload:

~~~json
{
  "groups": [
    {
      "members": [
        {"email": "ok@example.test"},
        {"email": "bad"}
      ]
    },
    {
      "members": [
        {"email": ""}
      ]
    }
  ]
}
~~~

**Câu hỏi:** Viết đường dẫn cho email của phần tử thứ hai trong nhóm đầu và email của phần tử đầu tiên trong nhóm thứ hai.

**Đáp án:** /groups/0/members/1/email và /groups/1/members/0/email. Chỉ số mảng bắt đầu từ 0.

### Bài 2 — Escape JSON Pointer

Cho object:

~~~json
{
  "rate/standard": {
    "label~en": "VAT"
  }
}
~~~

**Câu hỏi:** Pointer tới giá trị VAT là gì? Nếu client gửi field thiếu label~vi thì có thể gọi pointer đó là pointer tới giá trị đang tồn tại không?

**Đáp án:** /rate~1standard/label~0en. Với label~vi chưa tồn tại, /rate~1standard/label~0vi là **đường dẫn mong đợi**, không resolve được tới một giá trị hiện hữu; nếu hợp đồng yêu cầu pointer hiện hữu, dùng parent /rate~1standard kèm missingProperty = "label~vi".

### Bài 3 — Chọn status và locator

Phân loại những yêu cầu:

1. POST body không parse được vì dấu ngoặc JSON không khớp.
2. POST body parse được nhưng items[2].quantity = -3.
3. GET /api/orders?page=abc.
4. PUT /api/orders/42 với If-Match sai.
5. POST tạo đơn có externalId đã tồn tại và bất biến uniqueness không cho ghi đè.

**Gợi ý:** (1) 400, không nhất thiết có field path; (2) 422 theo hợp đồng minh họa, /items/2/quantity; (3) 400, source.in=query, name=page; (4) 412; (5) 409 nếu là xung đột trạng thái resource. Các mã cần khớp hợp đồng thực tế.

### Bài 4 — Phân biệt lỗi từng trường và toàn request

Một booking có startAt và endAt đều là timestamp hợp lệ, nhưng endAt trước startAt. Một danh sách allocations có ba phần tử 60%, 30%, 30%, tổng 120%.

**Câu hỏi:** Nên đặt lỗi ở đâu?

**Gợi ý:** Booking có thể dùng /endAt và relatedPaths /startAt; tổng allocation nên thuộc /allocations hoặc lỗi cấp request vì không thể kết luận một phần tử cụ thể sai. Không buộc một lỗi global vào phần tử cuối chỉ vì dễ hiển thị.

### Bài 5 — Chỉ ra lỗi trong handler

~~~java
problem.setProperty("invalid-params",
    errors.stream().map(e -> Map.of(
        "field", e.getField(),
        "rejectedValue", e.getRejectedValue(),
        "message", e.getDefaultMessage()
    )).toList());
~~~

**Câu hỏi:** Vì sao đoạn này chưa đủ an toàn/ổn định cho hợp đồng API?

**Gợi ý:** dùng field path nội bộ của Spring; có thể lộ rejectedValue nhạy cảm; message phụ thuộc ngôn ngữ và framework; thiếu code, source.in, quy tắc sort, giới hạn số lỗi; chưa xử lý global errors. Cần ánh xạ sang contract đã định nghĩa, đặc biệt việc bảo mật rejectedValue.

### Bài 6 — Batch partial success

Một batch có 100 dòng; 95 dòng đã ghi và 5 dòng sai. Server trả:

~~~json
{"status":"FAILED","errors":[{"message":"Invalid data"}]}
~~~

**Câu hỏi:** Client có biết dòng nào đã ghi và nên retry toàn bộ không?

**Gợi ý:** Không. Cần công bố atomic hay partial; nếu partial, trả kết quả từng item, mapping với clientItemId hoặc index, trạng thái đã ghi và lỗi cụ thể. Retry toàn bộ có thể tạo duplicate nếu không có idempotency. Với batch all-or-nothing phải đảm bảo thực sự rollback tất cả.

## 17. Checklist thiết kế lỗi theo trường, phần tử và đường dẫn

- [ ] Status HTTP và body Problem Details mô tả nhất quán kết quả yêu cầu?
- [ ] Đã định nghĩa khi nào dùng 400, 422, 409 và các mã như 401/403/412/413/415?
- [ ] Có extension invalid-params được tài liệu hóa đầy đủ, không ngầm coi là trường chuẩn của RFC 9457?
- [ ] Mỗi lỗi có code ổn định, message an toàn và source đủ chính xác?
- [ ] Đã phân biệt field, element, ràng buộc chéo và lỗi toàn request?
- [ ] Body/query/path/header có locator khác nhau; không dùng body path cho query parameter?
- [ ] Đường dẫn JSON dùng chỉ số 0-based và escape ~, / chính xác?
- [ ] Với trường bị thiếu, đã phân biệt **đường dẫn mong đợi** và **JSON Pointer tới giá trị tồn tại**?
- [ ] Đã xử lý mảng nhiều tầng, map keys đặc biệt, field mapping @JsonProperty và phần tử bị sắp xếp lại?
- [ ] Có thể trả lỗi ở collection/root và relatedPaths khi quy tắc không thuộc một field duy nhất?
- [ ] Hợp đồng batch nói rõ all-or-nothing, partial success hay bất đồng bộ?
- [ ] Có giới hạn kích thước payload, độ sâu JSON, số phần tử và số lỗi công bố?
- [ ] Đã không echo rejectedValue, secret, stack trace, tên class, dữ liệu tenant khác?
- [ ] Code lỗi ổn định khi ngôn ngữ message thay đổi, có fallback cho client không nhận diện code?
- [ ] Spring validation handler xử lý đúng lỗi @RequestBody, query/path và global errors theo use case?
- [ ] OpenAPI mô tả 4xx, application/problem+json, invalid-params và các quy ước định vị?
- [ ] Có unit/MockMvc/integration/consumer contract tests cho nested field, array, escape, missing, batch và bảo mật?
- [ ] Client ánh xạ lỗi vào đúng snapshot của request, không nhầm index sau reorder hoặc phản hồi đến trễ?

## 18. Kết luận

**Lỗi theo trường** giúp người dùng biết thuộc tính nào cần sửa; **lỗi theo phần tử** chỉ rõ dòng hay phần tử nào sai; **đường dẫn dữ liệu** là cách kết nối hai mức đó trong một cây JSON hoặc một nguồn tham số HTTP cụ thể. Một API tốt phải thể hiện được cả lỗi cục bộ và ràng buộc toàn request mà không đánh mất ngữ nghĩa.

Để xây dựng hợp đồng lỗi REST đáng tin cậy, hãy kết hợp **HTTP status phù hợp**, **Problem Details RFC 9457 với extension có schema rõ**, **quy ước đường dẫn chính xác**, **mã lỗi ổn định**, **validation Java/Spring**, **OpenAPI** và **kiểm thử cả server lẫn client**. Đặc biệt, phân biệt JSON Pointer tới giá trị tồn tại với đường dẫn của trường bị thiếu, kiểm soát việc tiết lộ dữ liệu và xác định rõ cách xử lý batch. Những lựa chọn này giúp API dễ tích hợp, sửa lỗi nhanh và an toàn hơn khi dữ liệu phức tạp hoặc nhiều đội phát triển cùng sử dụng.
