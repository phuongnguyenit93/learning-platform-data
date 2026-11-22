# Thông điệp tự mô tả và vai trò của media type

## 1. Mục tiêu bài học

Trong chương **Ràng buộc REST** của module **INTEGRATION_API_REST**, bài học này giải thích cách một thông điệp HTTP cung cấp thông tin để bên nhận hiểu và xử lý yêu cầu hoặc phản hồi. Trọng tâm là đặc tính **tự mô tả** của thông điệp và vai trò của **media type** trong hợp đồng API.

Sau bài học, bạn có thể:

- Đọc phương thức, URI, mã trạng thái, header và body như những phần phối hợp của một thông điệp.
- Phân biệt kiểu nội dung đang gửi với kiểu phản hồi mà bên gọi mong muốn nhận.
- Giải thích giới hạn của `application/json` và ý nghĩa của các media type chuyên biệt.
- Phân biệt lỗi kiểu nội dung, lỗi thương lượng phản hồi và lỗi dữ liệu nghiệp vụ.
- Áp dụng những nguyên tắc này khi thiết kế hợp đồng và tổ chức HTTP adapter trong Java/Spring hoặc công nghệ tương đương.

## 2. Vì sao chỉ nhìn JSON chưa đủ?

Giả sử client nhận một body:

```json
{
  "id": "ord_8421",
  "status": "PENDING"
}
```

Chỉ từ hai trường này, bên nhận chưa biết đầy đủ:

- Đây là kết quả đọc một đơn đã có hay phản hồi sau khi tạo đơn mới?
- Yêu cầu đã thành công hay đây là dữ liệu đính kèm một lỗi?
- `PENDING` là trạng thái đơn hàng hay trạng thái một lần thanh toán?
- Có tài nguyên mới nào vừa được tạo và có thể truy cập ở URI nào?
- Body phải được diễn giải theo hợp đồng nào?

Hãy đặt body vào thông điệp đầy đủ hơn:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /orders/ord_8421

{
  "id": "ord_8421",
  "status": "PENDING"
}
```

Bây giờ client có thêm căn cứ để xử lý:

- `201 Created` cho biết yêu cầu đã dẫn tới việc tạo tài nguyên.
- `Location` xác định URI của tài nguyên chính được tạo trong phản hồi này.
- `Content-Type` cho biết nội dung được gửi là JSON.
- Hợp đồng biểu diễn đơn hàng giải thích ý nghĩa nghiệp vụ của `id` và `status`.

Thông điệp HTTP cần được đọc như một tổng thể. Một body JSON hợp lệ không tự thay thế ngữ nghĩa của phương thức, mã trạng thái hoặc metadata.

Các ví dụ HTTP trong bài lược bỏ một số chi tiết truyền tải và thông tin xác thực để tập trung vào nội dung bài học. Triển khai thực tế vẫn phải tuân thủ hợp đồng xác thực, phân quyền và truyền tải đã chọn.

## 3. Thông điệp tự mô tả trong REST

### 3.1. Tự mô tả là khả năng diễn giải thông điệp

Thông điệp tự mô tả cung cấp thông tin cần thiết để bên nhận hiểu cách xử lý nó, dựa trên ngữ nghĩa của giao thức, metadata và kiểu biểu diễn được thống nhất.

Trong REST, đây là một phần của ràng buộc **uniform interface**, tức giao diện thống nhất. Các bên dùng những quy tắc chung để tương tác với tài nguyên, thay vì mỗi endpoint tự phát minh cách đọc thông điệp hoàn toàn khác nhau.

Ví dụ, client có thể hiểu vai trò của `Content-Type`, `Location` hoặc `Cache-Control` nhờ ngữ nghĩa HTTP chung, dù chưa từng dùng API đặt hàng cụ thể này.

### 3.2. Tự mô tả không có nghĩa là không cần biết hợp đồng

Một client vẫn phải hiểu giao thức, media type và ngữ nghĩa mà ứng dụng sử dụng. `application/json` không tự dạy client rằng `totalAmount` là số tiền hay `PENDING` có những chuyển tiếp nào.

Tự mô tả cũng không yêu cầu nhét toàn bộ tài liệu API, lược đồ dữ liệu và lịch sử tương tác vào mỗi response. Những quy tắc đã được media type hoặc hợp đồng xác định có thể được dùng lại.

Điểm cần tránh là buộc bên nhận đoán cách xử lý từ các dấu hiệu không có hợp đồng, chẳng hạn “nếu body có trường `result` thì coi là thành công” dù mã HTTP lại báo lỗi.

### 3.3. Phân biệt với stateless

Hai đặc tính có liên quan nhưng không đồng nghĩa:

- **Stateless** xét việc server có cần giữ ngữ cảnh hội thoại của các yêu cầu trước để hiểu yêu cầu hiện tại hay không.
- **Thông điệp tự mô tả** xét việc các thành phần của thông điệp có cung cấp ngữ nghĩa đủ rõ để bên nhận xử lý hay không.

Một request có thể xác định đầy đủ tài nguyên mà vẫn gửi sai `Content-Type`. Ngược lại, khai báo `Content-Type` chính xác không giải quyết việc server đang dựa vào “đơn được chọn trong phiên trước”.

## 4. Các thành phần cùng tạo nên ý nghĩa

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Phương thức HTTP | Cho biết ngữ nghĩa thao tác đối với tài nguyên đích | `GET`, `POST`, `PATCH` |
| URI đích | Xác định tài nguyên mà request đang tác động tới | `/products/P-100` |
| Mã trạng thái | Cho biết kết quả xử lý yêu cầu theo ngữ nghĩa HTTP | `200`, `201`, `400`, `415` |
| `Content-Type` | Mô tả media type của nội dung đang được gửi | `application/json` |
| `Accept` | Nêu các media type phản hồi mà bên gọi chấp nhận | `application/json, application/problem+json` |
| Header khác | Cung cấp metadata hoặc điều khiển xử lý | `Location`, `ETag`, `Cache-Control` |
| Body | Mang biểu diễn hoặc dữ liệu thao tác theo media type | JSON đơn hàng, tài liệu lỗi, tài liệu patch |

Không phải thông điệp nào cũng có tất cả các thành phần. Ví dụ, một phản hồi `204 No Content` không có body; không nên cố gắn JSON rỗng vào để làm cho các response trông giống nhau.

Một `GET` trả `200 OK` có thể có body là biểu diễn sản phẩm. Một `POST` trả `201 Created` có thể có body là biểu diễn tài nguyên vừa tạo. Hình dạng body có thể giống nhau, nhưng ngữ nghĩa của tương tác vẫn khác.

## 5. Media type mô tả điều gì?

### 5.1. Cấu trúc cơ bản

Media type thường có dạng:

```text
type/subtype
type/subtype; parameter=value
```

Một số ví dụ:

| Media type | Ý nghĩa chính |
|---|---|
| `application/json` | Nội dung dùng cú pháp JSON |
| `application/xml` | Nội dung dùng cú pháp XML |
| `text/html` | Nội dung là tài liệu HTML |
| `application/problem+json` | Chi tiết lỗi theo mô hình Problem Details, biểu diễn bằng JSON |
| `application/json-patch+json` | Tài liệu thao tác theo JSON Patch |
| `application/merge-patch+json` | Tài liệu cập nhật theo JSON Merge Patch |

Parameter có ý nghĩa theo định nghĩa của media type tương ứng. Không nên tự thêm một parameter rồi giả định mọi client hoặc framework đều hiểu nó.

### 5.2. Tài nguyên và kiểu biểu diễn là hai khái niệm khác nhau

`/products/P-100` xác định tài nguyên sản phẩm. `application/json` mô tả kiểu nội dung của một biểu diễn được truyền.

Cùng một tài nguyên có thể được cung cấp dưới nhiều kiểu biểu diễn nếu API hỗ trợ. Ví dụ, client nhận JSON hoặc XML nhưng đều đang truy cập cùng sản phẩm.

Điều đó không buộc API phải hỗ trợ nhiều định dạng. Một API chỉ cung cấp JSON vẫn cần mô tả chính xác kiểu nội dung và hợp đồng dữ liệu của nó.

### 5.3. `application/json` có giới hạn về ngữ nghĩa

JSON định nghĩa cách biểu diễn object, array, string, number, boolean và null. Nó không tự quy định:

- `price` đang dùng đồng, nghìn đồng hay một đơn vị khác.
- `createdAt` là thời gian theo định dạng nào và múi giờ nào.
- Trường nào bắt buộc hoặc có thể vắng mặt.
- Giá trị `CANCELLED` có còn cho phép cập nhật hay không.
- Một body gửi bằng `PATCH` phải được áp dụng theo thuật toán nào.

Các ý nghĩa đó cần đến hợp đồng ứng dụng, lược đồ, tài liệu hoặc media type chuyên biệt phù hợp. Có cú pháp JSON đúng mới là một phần của việc hiểu thông điệp.

## 6. Phân biệt `Content-Type` và `Accept`

### 6.1. `Content-Type`: nội dung tôi đang gửi là gì?

Trong request tạo đơn:

```http
POST /orders HTTP/1.1
Content-Type: application/json
Accept: application/json, application/problem+json

{
  "items": [
    {
      "productId": "P-100",
      "quantity": 2
    }
  ]
}
```

`Content-Type: application/json` mô tả body của request. Nó giúp server chọn cách đọc nội dung được gửi đến.

Trong response, `Content-Type` lại mô tả body của response đó. Hai phía có thể gửi các media type khác nhau trong cùng một tương tác.

Ví dụ, request dùng JSON thông thường, nhưng nếu dữ liệu không hợp lệ thì server trả chi tiết lỗi bằng `application/problem+json`.

### 6.2. `Accept`: tôi chấp nhận nhận lại kiểu nào?

`Accept` thể hiện các media type phản hồi mà client chấp nhận. Nó không mô tả body request và không đổi JSON thành XML.

```http
GET /products/P-100 HTTP/1.1
Accept: application/json
```

Request này không cần có body. `Accept` vẫn có ý nghĩa vì client muốn nhận biểu diễn JSON trong response.

Nếu thiếu `Accept`, không có ràng buộc ưu tiên media type từ header đó; server có thể dùng kiểu biểu diễn mặc định theo hợp đồng. Không nên suy rằng thiếu `Accept` luôn có nghĩa là yêu cầu JSON.

### 6.3. Hai chiều có thể khác nhau

| Trường hợp | `Content-Type` request | `Accept` request | `Content-Type` response có thể nhận |
|---|---|---|---|
| Đọc sản phẩm | Không có body để mô tả | `application/json` | `application/json` |
| Tạo đơn thành công | `application/json` | `application/json, application/problem+json` | `application/json` |
| Tạo đơn bị lỗi đầu vào | `application/json` | `application/json, application/problem+json` | `application/problem+json` |
| Cập nhật bằng JSON Patch | `application/json-patch+json` | `application/json, application/problem+json` | JSON tài nguyên hoặc chi tiết lỗi theo kết quả |

Mỗi trường hợp còn phụ thuộc các định dạng mà endpoint thực sự hỗ trợ. Đặt một giá trị trong `Accept` không làm server tự có thêm bộ chuyển đổi định dạng.

### 6.4. Ưu tiên qua hệ số `q`

Client có thể nêu mức ưu tiên:

```http
Accept: application/json, application/xml;q=0.5
```

Trong ví dụ, JSON có mức ưu tiên mặc định là `1`, cao hơn mức `0.5` của XML. Giá trị `q=0` thể hiện kiểu tương ứng không được chấp nhận.

Server lựa chọn dựa trên các kiểu được hỗ trợ và quy tắc thương lượng áp dụng. Client vẫn phải đọc `Content-Type` của phản hồi thực tế, thay vì mặc định luôn nhận kiểu mình thích nhất.

## 7. Đọc một tương tác tự mô tả

### 7.1. Yêu cầu đọc sản phẩm

```http
GET /products/P-100 HTTP/1.1
Host: api.example.test
Accept: application/json, application/xml;q=0.5
```

Server hỗ trợ cả JSON và XML, và chọn JSON cho tương tác này:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=60
Vary: Accept
ETag: "P-100-json-v3"

{
  "id": "P-100",
  "name": "Sổ tay",
  "price": 125000,
  "currency": "VND"
}
```

Hợp đồng quy định `price` là số nguyên đồng Việt Nam. Thông điệp còn mang metadata phục vụ những bên hiểu HTTP:

- `Content-Type` chỉ ra cách đọc body là JSON.
- `Cache-Control` cho phép cache dùng lại phản hồi công khai này trong thời gian phù hợp với chỉ thị đã gửi.
- `Vary: Accept` cho biết lựa chọn biểu diễn có phụ thuộc header `Accept`, để cache phân biệt các biến thể khi áp dụng.
- `ETag` cung cấp một validator cho biểu diễn theo quy tắc của API và HTTP.

Ví dụ dùng dữ liệu sản phẩm công khai. Không nên sao chép chính sách cache công khai này sang dữ liệu riêng của từng người dùng mà không thiết kế chính sách tương ứng.

Một cache không cần hiểu “sổ tay” là gì vẫn có thể xử lý các chỉ thị cache. Đây là một lợi ích của metadata có ngữ nghĩa chung.

### 7.2. Nội dung phù hợp nhưng metadata sai vẫn gây vấn đề

Nếu server gửi cùng JSON đó với:

```http
Content-Type: text/plain
```

thì thông điệp tuy có thể nhìn giống JSON nhưng đang khai báo nội dung văn bản thuần. Một client có xử lý nghiêm theo media type có thể không chọn bộ đọc JSON.

Client không nên phải thử đoán mọi body bằng cách nhìn ký tự đầu tiên hoặc thử nhiều parser cho đến khi một parser chấp nhận. Hợp đồng cần cung cấp kiểu nội dung chính xác; nếu hỗ trợ thêm định dạng, hãy khai báo và xử lý định dạng đó rõ ràng.

## 8. Cùng là JSON nhưng ngữ nghĩa có thể khác

### 8.1. JSON Patch là danh sách thao tác

Giả sử sản phẩm đã có trường `name`. Một yêu cầu JSON Patch có thể là:

```http
PATCH /products/P-100 HTTP/1.1
Content-Type: application/json-patch+json
Accept: application/json, application/problem+json

[
  {
    "op": "replace",
    "path": "/name",
    "value": "Sổ tay bìa cứng"
  }
]
```

Ở đây, body là danh sách thao tác. `op`, `path` và `value` có ngữ nghĩa do JSON Patch quy định. Server còn phải kiểm tra endpoint hỗ trợ cách cập nhật này, đường dẫn được phép sửa và dữ liệu mới hợp lệ.

### 8.2. JSON Merge Patch mô tả các thay đổi theo cấu trúc

Một cách khác là:

```http
PATCH /products/P-100 HTTP/1.1
Content-Type: application/merge-patch+json
Accept: application/json, application/problem+json

{
  "name": "Sổ tay bìa cứng"
}
```

Body này được diễn giải theo JSON Merge Patch. Với object trong ví dụ, trường được gửi sẽ được áp dụng theo quy tắc merge patch; các trường không có trong patch không bị thay đổi bởi bước merge đó.

Giá trị `null` có ý nghĩa xóa thành viên trong quy tắc merge patch đối với object, nên không thể tùy ý xem nó là “không cập nhật”. Các array cũng không được cập nhật từng phần tử theo cách mà người đọc có thể tự suy đoán. API cần quy định trường được phép sửa và kiểm tra tài nguyên kết quả theo nghiệp vụ.

### 8.3. Không đổi nhãn media type tùy tiện

Hai body trên đều là JSON hợp lệ nhưng không thể tráo cách diễn giải:

- Bộ xử lý JSON Patch chờ một tài liệu gồm các thao tác phù hợp.
- Bộ xử lý JSON Merge Patch áp dụng thuật toán merge theo tài liệu patch.
- `application/json` tự nó không xác định một thuật toán cập nhật chung cho `PATCH`.

Nếu API chọn nhận `application/json` cho một thao tác cập nhật riêng, nó phải mô tả rõ quy tắc riêng đó. Không nên mặc định các client sẽ tự hiểu cùng một cách.

### 8.4. Hậu tố `+json` có ích nhưng không đủ

Hậu tố cấu trúc `+json` cho biết kiểu biểu diễn dùng cú pháp JSON, giúp một số công cụ nhận diện khả năng xử lý cấu trúc chung. Nó không làm các media type trở thành tương đương về nghiệp vụ hoặc thao tác.

Đọc được JSON của một problem detail không có nghĩa client được phép áp dụng nó như một tài liệu patch. Tương tự, không nên mặc định mọi framework sẽ thương lượng hoặc chấp nhận mọi subtype có hậu tố `+json` mà không cấu hình phù hợp.

## 9. Media type cho lỗi và mã trạng thái HTTP

### 9.1. Một lỗi đầu vào có cấu trúc

Giả sử request tạo đơn có số lượng bằng `0`. API có thể trả Problem Details:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/invalid-order",
  "title": "Dữ liệu đơn hàng không hợp lệ",
  "status": 400,
  "detail": "Có trường chưa đáp ứng yêu cầu tạo đơn.",
  "instance": "/problem-occurrences/err_100",
  "errors": [
    {
      "field": "items[0].quantity",
      "code": "MUST_BE_POSITIVE"
    }
  ]
}
```

Trong mô hình này:

- `type` xác định loại vấn đề bằng URI.
- `title` mô tả ngắn loại vấn đề cho người đọc.
- `status`, khi được cung cấp, thể hiện mã HTTP cho lần phát sinh đó và cần nhất quán với mã HTTP thực tế.
- `detail` cung cấp diễn giải cho trường hợp cụ thể.
- `instance` xác định lần phát sinh cụ thể bằng URI.
- `errors` là phần mở rộng do hợp đồng API này định nghĩa; nó không phải trường bắt buộc chung của Problem Details.

Không phải mọi trường trong ví dụ đều bắt buộc trong mọi problem detail. Client cần hiểu mô hình cùng các quy ước mà API hỗ trợ, thay vì suy rằng mọi lỗi đều có đúng một hình dạng như trên.

Một client tổng quát có thể hiểu các thành phần chung của lỗi. Một client biết thêm quy ước `errors` có thể gắn lỗi vào ô nhập cụ thể. Nó không cần phân tích câu tiếng Việt trong `detail` để xác định trường số lượng.

### 9.2. Phân biệt các nhóm lỗi

| Tình huống | Kết quả thường được hợp đồng lựa chọn | Điểm cần phân biệt |
|---|---|---|
| Endpoint chỉ nhận JSON nhưng request gửi XML | `415 Unsupported Media Type` | Kiểu nội dung gửi đến không được hỗ trợ |
| Client chỉ chấp nhận XML nhưng server chỉ cung cấp JSON | Có thể là `406 Not Acceptable` | Không có biểu diễn phản hồi phù hợp với thương lượng |
| Request khai báo JSON nhưng body sai cú pháp JSON | `400 Bad Request` | Không phân tích được nội dung theo kiểu đã khai báo |
| JSON đúng cú pháp nhưng số lượng không hợp lệ | Ví dụ này chọn `400 Bad Request` | Kiểu nội dung đúng, dữ liệu không đáp ứng hợp đồng |

`406` phụ thuộc chính sách thương lượng của server: server có thể chọn tôn trọng chặt yêu cầu `Accept`, hoặc áp dụng cách xử lý khác được cho phép và được mô tả trong hợp đồng. Không nên khẳng định mọi giá trị `Accept` không khớp đều chắc chắn dẫn tới `406` trong mọi triển khai.

Những khác biệt này giúp client phản ứng đúng. Gửi lại body XML với số lượng khác không giải quyết lỗi endpoint chỉ nhận JSON; đổi `Accept` cũng không sửa một body JSON sai cú pháp.

### 9.3. Media type lỗi không thay mã trạng thái

Một lỗi được mô tả bằng `application/problem+json` vẫn cần mã HTTP thích hợp. Dùng `200 OK` cho mọi kết quả rồi bắt client đọc một trường `success` làm giảm khả năng xử lý chung của các thành phần hiểu HTTP.

Ngược lại, chỉ gửi `400` mà không có dữ liệu lỗi hữu ích có thể khiến client khó hướng dẫn người dùng sửa đầu vào. Mã HTTP và biểu diễn lỗi bổ sung cho nhau.

## 10. Đừng nhầm media type với các lớp mô tả khác

### 10.1. Media type và schema

Media type cho biết loại biểu diễn cùng các quy tắc gắn với loại đó. Schema mô tả cấu trúc dữ liệu cụ thể hơn: kiểu của trường, trường bắt buộc, giới hạn và các ràng buộc có thể biểu diễn.

Ví dụ:

```text
Media type:
  application/json

Hợp đồng biểu diễn sản phẩm:
  id: string, bắt buộc
  name: string, bắt buộc
  price: số nguyên không âm, đơn vị VND
  currency: chuỗi "VND" trong phạm vi ví dụ
```

Schema cũng không thay thế toàn bộ quy tắc nghiệp vụ. Việc một người dùng được quyền đổi giá hay không còn phụ thuộc ngữ cảnh xác thực và chính sách của server.

OpenAPI có thể mô tả các media type được nhận hoặc trả, cùng schema cho từng loại phản hồi. Cần giữ mô tả đó nhất quán với hành vi thực tế.

### 10.2. Media type và mã hóa nội dung

Hai header sau mô tả hai việc khác nhau:

```http
Content-Type: application/json
Content-Encoding: gzip
```

`Content-Encoding: gzip` cho biết nội dung đã được mã hóa theo gzip. Sau khi xử lý lớp gzip, bên nhận đọc biểu diễn theo `application/json`.

Không nên đổi `Content-Type` thành một kiểu không phù hợp chỉ vì đang nén body. Media type, nén nội dung và lựa chọn bộ ký tự là những vấn đề khác nhau. JSON trao đổi giữa các hệ thống nên dùng UTF-8 theo quy tắc của JSON; các ví dụ trong bài dùng `application/json` mà không tự thêm một parameter bộ ký tự riêng.

### 10.3. Media type và phiên bản hợp đồng

Một API có thể thiết kế subtype riêng, chẳng hạn:

```text
application/vnd.example.order+json
```

Tên này chỉ minh họa một kiểu biểu diễn riêng cho đơn hàng. Đặt tên subtype riêng không tự tạo ra ngữ nghĩa, khả năng tương thích hoặc hỗ trợ trong công cụ. Cần định nghĩa cách hiểu dữ liệu và điều kiện thay đổi hợp đồng.

Nếu API dùng parameter phiên bản hoặc cơ chế phiên bản khác, các bên phải thống nhất rõ quy tắc lựa chọn. Không có một parameter tự đặt nào khiến mọi client tự hiểu phiên bản mới.

Không cần tạo media type riêng cho mọi endpoint. Hãy chọn dựa trên ngữ nghĩa cần công bố, mức tái sử dụng và khả năng của các bên tích hợp.

### 10.4. Media type và hypermedia

Một media type hoặc hợp đồng biểu diễn có thể mô tả cách nhận biết liên kết và điều khiển tương tác tiếp theo. Khi đó client biết cách tìm và sử dụng các khả năng mà server cung cấp.

Nhưng chỉ thêm trường `links` vào một object JSON chưa đủ tạo ra một quy tắc chung. Cần định nghĩa quan hệ liên kết, cách hiểu URI và dữ liệu cần thiết cho hành động. `application/json` tự nó không quy định tất cả những điều đó.

## 11. Áp dụng trong Java/Spring

### 11.1. Hình dạng DTO và media type là hai việc riêng

DTO Java có thể mô tả dữ liệu sản phẩm:

```java
import java.math.BigDecimal;

record ProductResponse(
        String id,
        String name,
        BigDecimal price,
        String currency
) {}
```

Đối tượng này không tự quyết định response sẽ là JSON, XML hay một kiểu khác. Việc chọn bộ chuyển đổi nội dung và đặt header thuộc xử lý HTTP cùng cấu hình tương ứng.

Tương tự, một object Java chứa các trường `type`, `title` và `detail` không tự bảo đảm toàn bộ response tuân thủ hợp đồng Problem Details nếu status hoặc `Content-Type` được gửi sai.

### 11.2. Các quyết định cần thể hiện ở HTTP adapter

Ví dụ hợp đồng triển khai có thể được mô tả như sau:

```text
POST /orders
  Nội dung nhận:
    application/json
  Thành công:
    201 Created
    Content-Type: application/json
    Location: URI đơn hàng vừa tạo
  Lỗi đầu vào:
    400 Bad Request
    Content-Type: application/problem+json

PATCH /products/{productId}
  Nội dung nhận:
    application/merge-patch+json
  Thành công có body:
    200 OK
    Content-Type: application/json
```

Trong ứng dụng Java/Spring hoặc công nghệ tương đương, cần phân công rõ:

| Phần xử lý | Trách nhiệm |
|---|---|
| Bộ định tuyến và xử lý HTTP | Xác định endpoint, phương thức và kiểu nội dung được hỗ trợ |
| Bộ đọc hoặc ghi nội dung | Chuyển đổi giữa nội dung truyền và dữ liệu ứng dụng theo kiểu phù hợp |
| Kiểm tra dữ liệu | Kiểm tra cấu trúc cùng các yêu cầu đầu vào |
| Logic nghiệp vụ | Quyết định thao tác có hợp lệ theo tài nguyên, quyền và trạng thái hiện tại không |
| Xử lý phản hồi và lỗi | Chọn status, header, media type và biểu diễn nhất quán |

Đừng giả định cấu hình phản hồi thành công tự áp dụng đúng cho mọi lỗi. Lỗi phân tích body, lỗi kiểu nội dung và lỗi nghiệp vụ có thể đi qua những nhánh xử lý khác nhau. Hợp đồng cần bao quát hành vi mà client thực sự nhận được.

### 11.3. Những điểm cần xác minh khi tích hợp

- Request khai báo đúng media type của body đã gửi.
- Response công bố đúng media type của body thực tế.
- Client chấp nhận được kiểu phản hồi cần dùng, bao gồm kiểu lỗi đã thống nhất.
- Status và header phù hợp với kết quả thao tác.
- Các quy tắc cập nhật, đơn vị dữ liệu và phần mở rộng lỗi được mô tả rõ.
- Công cụ hoặc framework thực sự hỗ trợ các kiểu đã công bố, thay vì chỉ có tên trong tài liệu.

Những điểm này là tiêu chí kiểm tra hợp đồng khi triển khai. Việc có một DTO hoặc một schema hợp lệ chưa đủ chứng minh toàn bộ tương tác HTTP đã đúng.

## 12. Bài tập vận dụng

### 12.1. Chẩn đoán một hợp đồng có vấn đề

Một client gửi:

```http
PATCH /products/P-100 HTTP/1.1
Content-Type: application/json
Accept: application/xml

{
  "name": "Sổ tay mới"
}
```

Server trả:

```http
HTTP/1.1 200 OK
Content-Type: text/plain

{
  "success": false,
  "message": "Không hỗ trợ định dạng cập nhật"
}
```

Hãy phân tích ba nhóm vấn đề:

1. Client và server đã thống nhất quy tắc áp dụng body `PATCH` chưa?
2. `Accept` của client có khớp kiểu phản hồi mà endpoint hỗ trợ không?
3. Status, `Content-Type` và nội dung lỗi có phối hợp nhất quán không?

### 12.2. Một cách sửa

Giả sử hợp đồng chọn JSON Merge Patch để cập nhật sản phẩm, JSON cho phản hồi thành công và Problem Details dạng JSON cho lỗi. Client có thể gửi:

```http
PATCH /products/P-100 HTTP/1.1
Content-Type: application/merge-patch+json
Accept: application/json, application/problem+json

{
  "name": "Sổ tay mới"
}
```

Nếu thành công và trả biểu diễn mới:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "P-100",
  "name": "Sổ tay mới",
  "price": 125000,
  "currency": "VND"
}
```

Nếu request dùng kiểu nội dung mà endpoint không hỗ trợ, server có thể trả `415 Unsupported Media Type` theo hợp đồng thay vì `200 OK` với cờ thất bại. Nếu có body lỗi, media type phải mô tả chính xác định dạng lỗi được gửi và cách thương lượng lỗi phải được thống nhất.

Khi thiết kế và đọc một REST API, hãy xác định tài nguyên, ngữ nghĩa HTTP và kiểu biểu diễn cùng nhau. Media type giúp chọn cách hiểu nội dung; hợp đồng dữ liệu và nghiệp vụ làm rõ những ý nghĩa mà định dạng truyền tải chưa thể tự cung cấp.
