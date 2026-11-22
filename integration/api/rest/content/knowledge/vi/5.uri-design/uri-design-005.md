# URI chuẩn và nhiều đường dẫn cùng tham chiếu tài nguyên

Trong một REST API, một đơn hàng có thể xuất hiện ở nhiều nơi: danh sách đơn hàng toàn hệ thống, danh sách đơn hàng của khách hàng, kết quả tìm kiếm theo mã nghiệp vụ hoặc liên kết từ một hóa đơn. Những cách tìm đến đó không nhất thiết tạo ra nhiều đơn hàng khác nhau. Chúng có thể cùng dẫn đến một tài nguyên có cùng định danh.

Vấn đề thiết kế là làm cho client nhận biết được sự đồng nhất ấy, đồng thời giữ đúng ý nghĩa của từng đường dẫn. Nếu không có quy ước rõ ràng, client dễ lưu trùng dữ liệu, cache bị phân mảnh, liên kết thay đổi theo màn hình và quyền truy cập khác nhau giữa các endpoint.

Trong chương **Thiết kế URI** của module `INTEGRATION_API_REST`, bài này tập trung vào cách chọn URI chuẩn, công bố các đường dẫn thay thế và giữ nhất quán hợp đồng HTTP. Các ví dụ dùng một API quản lý đơn hàng và có phần triển khai minh họa bằng Java/Spring.

## 1. Phân biệt tài nguyên, URI và biểu diễn

Ba khái niệm cần được tách rõ:

- **Tài nguyên** là đối tượng hoặc khái niệm mà API quản lý, chẳng hạn đơn hàng có định danh `ord_42`.
- **URI** là địa chỉ mà client dùng để tham chiếu hoặc tương tác với tài nguyên.
- **Biểu diễn** là dữ liệu được gửi qua HTTP, chẳng hạn JSON chứa mã đơn hàng, trạng thái và các liên kết.

Một tài nguyên có thể có nhiều URI. Ngược lại, không thể chỉ nhìn hai chuỗi URI gần giống nhau để kết luận chúng có cùng ngữ nghĩa.

Ví dụ:

```text
/api/orders/ord_42
/api/customers/cus_7/orders/ord_42
/api/orders/by-number/SO-2026-0042
```

API có thể định nghĩa cả ba đường dẫn cùng dẫn đến đơn hàng `ord_42`:

1. Đường dẫn thứ nhất tra cứu trực tiếp theo định danh kỹ thuật.
2. Đường dẫn thứ hai tra cứu trong phạm vi khách hàng `cus_7`.
3. Đường dẫn thứ ba phân giải từ mã nghiệp vụ.

Điều đó phải là một phần của hợp đồng API. Hai endpoint đọc cùng một dòng trong cơ sở dữ liệu vẫn có thể đại diện cho các tài nguyên khác nhau nếu chúng có vòng đời, quyền hoặc ý nghĩa nghiệp vụ khác nhau. Chẳng hạn `/orders/ord_42` và `/invoices/inv_19` có thể dùng chung dữ liệu tiền hàng nhưng vẫn là đơn hàng và hóa đơn riêng biệt.

**URI chuẩn**, hay canonical URI trong bài này, là URI mà API chọn làm địa chỉ tham chiếu ưu tiên cho một tài nguyên trong một phạm vi hợp đồng xác định. Đây là một quyết định thiết kế; HTTP không tự chọn URI chuẩn thay cho ứng dụng và cũng không bắt buộc mỗi tài nguyên chỉ được có đúng một URI.

## 2. Chọn URI chuẩn dựa trên định danh ổn định

Giả sử API chọn:

```text
/api/orders/ord_42
```

làm URI chuẩn của đơn hàng. Client có thể dùng URI này để lưu liên kết, mở lại đơn hàng hoặc ghép các kết quả thu được từ nhiều truy vấn.

Một URI chuẩn tốt thường đáp ứng các tiêu chí sau:

| Tiêu chí | Ý nghĩa thực tế |
| --- | --- |
| Định danh ổn định | Đổi tên hiển thị hoặc trạng thái đơn hàng không làm thay địa chỉ. |
| Phạm vi rõ ràng | Định danh được diễn giải trong đúng tenant hoặc không gian tài nguyên. |
| Ít phụ thuộc cấu trúc nội bộ | Đổi bảng dữ liệu, service hoặc phân vùng lưu trữ không buộc client đổi liên kết. |
| Được công bố nhất quán | Các response, liên kết và tài liệu dùng chung quy tắc tạo URI. |
| Có chính sách tương thích | Khi phải đổi địa chỉ, API quy định cách hỗ trợ URI cũ. |

Một mã như `ord_42` chỉ minh họa định danh kỹ thuật. Định danh chuẩn có thể là UUID hoặc một mã nghiệp vụ nếu mã đó thực sự duy nhất và ổn định trong phạm vi đã cam kết. Không cần thay mọi định danh nghiệp vụ bằng UUID; cần đánh giá khả năng đổi tên, tái sử dụng và va chạm của mã.

### Đưa tài nguyên cha vào URI khi nó thuộc phạm vi định danh

Nếu số đơn hàng chỉ duy nhất trong từng tenant, URI chuẩn có thể là:

```text
/api/tenants/ten_a/orders/42
```

Khi đó `ten_a` là một phần của phạm vi định danh. Bỏ nó đi thành `/api/orders/42` có thể làm địa chỉ mơ hồ.

Ngược lại, nếu `ord_42` duy nhất toàn hệ thống và khách hàng chỉ là một quan hệ có thể thay đổi, việc chọn `/api/customers/cus_7/orders/ord_42` làm URI chuẩn sẽ gắn địa chỉ đơn hàng với quan hệ đó. Khi quan hệ thay đổi, API phải xử lý các liên kết cũ.

Độ ngắn của URI không quyết định tính đúng. Hãy chọn cấu trúc thể hiện phạm vi định danh và vòng đời tài nguyên.

## 3. Không phải mọi đường dẫn liên quan đều là alias

**Alias** là một địa chỉ thay thế được API chủ động định nghĩa để tham chiếu cùng tài nguyên. Cần phân biệt alias với tập hợp, truy vấn, tài nguyên con và địa chỉ phụ thuộc ngữ cảnh.

| URI | Cách hiểu hợp lý | Có tự động là alias của đơn hàng không? |
| --- | --- | --- |
| `/api/orders/ord_42` | Đơn hàng theo định danh | Đây là URI chuẩn trong ví dụ. |
| `/api/customers/cus_7/orders/ord_42` | Đơn hàng trong phạm vi một khách hàng | Chỉ khi API định nghĩa như vậy và kiểm tra đúng quan hệ. |
| `/api/orders/by-number/SO-2026-0042` | Phân giải mã nghiệp vụ sang đơn hàng | Có thể là alias hoặc endpoint tra cứu, tùy hợp đồng. |
| `/api/customers/cus_7/orders` | Tập hợp đơn hàng của khách hàng | Không; đây là tập hợp. |
| `/api/orders?customerId=cus_7` | Kết quả truy vấn đơn hàng | Không; đây là kết quả truy vấn. |
| `/api/orders/ord_42/items` | Tập hợp dòng hàng của đơn hàng | Không; có ngữ nghĩa riêng. |
| `/api/orders/ord_42?fields=id,status` | Một phép chiếu dữ liệu đơn hàng | Không được mặc định thay thế bằng biểu diễn đầy đủ. |
| `/api/me` | Hồ sơ của người đang xác thực | Đích phụ thuộc danh tính người gọi. |
| `/api/reports/latest` | Báo cáo được coi là mới nhất tại thời điểm truy cập | Đích có thể thay đổi theo thời gian. |

### Đường dẫn lồng nhau mang theo một điều kiện

Với:

```text
/api/customers/cus_7/orders/ord_42
```

API phải xác định `ord_42` có thuộc `cus_7` hay không. Nếu bỏ qua `cus_7` và chỉ tìm theo `ord_42`, một đường dẫn sai vẫn trả dữ liệu thành công. Client có thể hiểu nhầm rằng quan hệ giữa khách hàng và đơn hàng đã được xác nhận.

Một hợp đồng rõ ràng có thể quy định:

- Đơn hàng tồn tại, người gọi có quyền và quan hệ đúng: trả dữ liệu hoặc redirect theo chính sách.
- Đơn hàng không thuộc khách hàng được nêu trong đường dẫn: trả `404 Not Found` cho địa chỉ trong phạm vi đó.
- Người gọi không có quyền: áp dụng chính sách `403` hoặc che giấu sự tồn tại bằng `404` một cách nhất quán.

Không tự động bỏ phần tài nguyên cha chỉ vì định danh tài nguyên con đủ để truy vấn cơ sở dữ liệu.

## 4. Hai lớp chuẩn hóa khác nhau

### 4.1. Chuẩn hóa cách viết URI

Đây là việc giải quyết các khác biệt về cú pháp hoặc quy ước tuyến đường, chẳng hạn API chỉ công bố một dạng dấu gạch chéo cuối:

```text
/api/orders/ord_42
/api/orders/ord_42/
```

API có thể hỗ trợ cả hai nhưng chọn một dạng chuẩn, hoặc chỉ chấp nhận một dạng. Cần thống nhất giữa gateway, router và phần tạo liên kết.

Một số giới hạn cần nhớ:

- Tên host không phân biệt chữ hoa và chữ thường, nhưng không thể suy ra rằng mọi thành phần URI đều như vậy.
- Không mặc định `/Orders/ord_42` tương đương `/orders/ord_42`; cách xử lý path phụ thuộc hợp đồng và hạ tầng.
- Không tùy tiện giải mã ký tự dành riêng rồi dùng kết quả như một path mới. Ví dụ `%2F` có thể làm thay đổi ranh giới giữa các đoạn đường dẫn nếu bị xử lý sai.
- Không tự ý bỏ query parameter hoặc sắp xếp lại mọi query parameter. Tham số lặp, bộ lọc và chữ ký có thể phụ thuộc cách biểu diễn đã quy định.
- Không coi `42` và `042` là cùng một định danh nếu API chưa định nghĩa điều đó.

Chuẩn hóa phải là quy tắc có chủ đích và được dùng nhất quán ở các lớp xử lý request, cache và kiểm tra chữ ký.

### 4.2. Chuẩn hóa tham chiếu theo ngữ nghĩa nghiệp vụ

Đây là việc nhận biết những URI khác hình thức nhưng cùng tham chiếu một tài nguyên:

```text
/api/orders/ord_42
/api/orders/by-number/SO-2026-0042
```

Không có thao tác chỉnh chuỗi tổng quát nào chứng minh được sự tương đương này. Ứng dụng cần phân giải mã nghiệp vụ, kiểm tra phạm vi và xác định tài nguyên đích.

Vì vậy, một bộ lọc tự xóa dấu gạch chéo hoặc đổi chữ thường không thay thế được chính sách URI chuẩn ở tầng nghiệp vụ.

## 5. Chọn cách xử lý địa chỉ thay thế

Không phải alias nào cũng cần redirect. Có ba lựa chọn phổ biến:

### 5.1. Trả `200 OK` cùng liên kết về URI chuẩn

Ví dụ:

```http
GET /api/customers/cus_7/orders/ord_42 HTTP/1.1
Host: api.example.com
Accept: application/json
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-cache

{
  "id": "ord_42",
  "customerId": "cus_7",
  "status": "CONFIRMED",
  "links": {
    "self": "/api/orders/ord_42"
  }
}
```

Ưu điểm là client nhận dữ liệu trong một lượt request. Đổi lại, API cần duy trì nhất quán serializer, phân quyền và cache ở mọi đường dẫn trả dữ liệu.

Trong hợp đồng JSON minh họa này, `links.self` được quy định là liên kết chuẩn của tài nguyên. Cấu trúc này là lựa chọn của API, không phải trường bắt buộc của mọi JSON REST API. Nếu dùng một định dạng hypermedia có quy tắc riêng, hãy tuân theo quy tắc của định dạng đó thay vì tự gán lại ý nghĩa của `self`.

Nếu query tạo một biểu diễn thu gọn hoặc một view riêng, cần mô tả liên kết đến view hiện tại và liên kết đến tài nguyên theo cách không gây hiểu nhầm. Không gắn nhãn mọi view là cùng một biểu diễn chỉ vì chúng có cùng `id`.

### 5.2. Redirect đến URI chuẩn

Ví dụ một đường dẫn cũ có quan hệ ổn định lâu dài với đường dẫn mới:

```http
GET /api/order/ord_42 HTTP/1.1
Host: api.example.com
```

```http
HTTP/1.1 308 Permanent Redirect
Location: /api/orders/ord_42
```

Client theo redirect rồi lấy dữ liệu ở URI chuẩn. Cách này tập trung endpoint trả biểu diễn nhưng thêm một lượt trao đổi và đòi hỏi client hỗ trợ redirect phù hợp.

Không trả `308` chỉ vì đã tìm ra đích ở thời điểm hiện tại. Với alias mà đích có thể thay đổi, như mã có thể cấp lại hoặc đường dẫn `/latest`, redirect vĩnh viễn dễ khiến client tiếp tục sử dụng đích cũ.

### 5.3. Chỉ hỗ trợ một URI

API mới có thể chỉ công bố URI chuẩn, các đường dẫn khác trả `404`. Lựa chọn này giảm số tuyến đường phải duy trì, nhưng cần phù hợp nhu cầu điều hướng của client.

Một endpoint tìm kiếm vẫn có thể trả liên kết đến tài nguyên mà không cần trở thành alias của tài nguyên đó:

```http
GET /api/orders?number=SO-2026-0042 HTTP/1.1
Host: api.example.com
```

```json
{
  "items": [
    {
      "id": "ord_42",
      "number": "SO-2026-0042",
      "links": {
        "self": "/api/orders/ord_42"
      }
    }
  ]
}
```

Response trên là kết quả truy vấn có danh sách `items`, kể cả khi chỉ khớp một đơn hàng. Client không nên biến URI truy vấn thành địa chỉ chuẩn của phần tử.

## 6. Chọn mã redirect theo tính ổn định và phương thức

| Mã | Ý nghĩa cần nhớ khi thiết kế alias |
| --- | --- |
| `301 Moved Permanently` | Chuyển vĩnh viễn; với POST, một số hành vi chuyển sang GET được HTTP cho phép vì tương thích lịch sử. |
| `302 Found` | Chuyển tạm thời; cũng có vấn đề thay đổi POST thành GET ở client. |
| `303 See Other` | Hướng client đến tài nguyên khác để truy xuất bằng GET hoặc HEAD; thường dùng sau một thao tác. |
| `307 Temporary Redirect` | Chuyển tạm thời và yêu cầu giữ nguyên phương thức khi client tự động chuyển tiếp. |
| `308 Permanent Redirect` | Chuyển vĩnh viễn và yêu cầu giữ nguyên phương thức khi client tự động chuyển tiếp. |

Với alias đọc dữ liệu, `307` hoặc `308` giúp thể hiện rõ chính sách bảo toàn phương thức. Với request ghi, sự khác biệt quan trọng hơn:

```text
PATCH /api/legacy-orders/ord_42
          |
          | 308 + Location
          v
PATCH /api/orders/ord_42
```

Client tuân thủ `308` phải bảo toàn phương thức khi tự động redirect, nhưng điều đó không có nghĩa mọi SDK đều sẽ tự theo redirect hoặc đều có thể gửi lại body. Một số client giới hạn redirect cho thao tác ghi, body dạng stream có thể không phát lại được và thông tin xác thực có thể không được chuyển sang origin khác.

Do đó, chỉ công bố redirect cho thao tác ghi sau khi đã xác định hành vi client và chính sách retry. Một API có thể chọn chỉ hỗ trợ alias cho `GET`/`HEAD`, còn thao tác ghi chỉ được thực hiện ở URI chuẩn. Nếu một phương thức đã biết nhưng không được phép tại địa chỉ đó, response `405 Method Not Allowed` cần có `Allow` phù hợp.

`303` không phải cách thay thế chung cho alias cần giữ nguyên thao tác. Ví dụ, trả `303` sau khi tạo một báo cáo có thể hướng client đến trang kết quả; nó không yêu cầu client lặp lại POST ở URI mới.

## 7. Công bố URI chuẩn bằng đúng cơ chế

### 7.1. Liên kết trong biểu diễn

Một API có thể công bố URI chuẩn theo cấu trúc đã tài liệu hóa:

```json
{
  "id": "ord_42",
  "status": "CONFIRMED",
  "links": {
    "self": "/api/orders/ord_42",
    "customer": "/api/customers/cus_7",
    "items": "/api/orders/ord_42/items"
  }
}
```

Định danh và liên kết phục vụ những mục đích khác nhau. `id` giúp đối chiếu định danh trong phạm vi ứng dụng; liên kết giúp client biết địa chỉ tương tác mà không tự ghép chuỗi theo cấu trúc router.

Nếu mỗi tenant có thể dùng cùng một `id`, client cần khóa nhận diện có chứa phạm vi tenant, hoặc một định danh ổn định khác đã được API cam kết. Chỉ dùng chuỗi `id` cục bộ để gộp dữ liệu giữa các tenant có thể gây trộn tài nguyên.

### 7.2. `Location` khi tạo mới

Giả sử client tạo đơn hàng qua tập hợp của khách hàng:

```http
POST /api/customers/cus_7/orders HTTP/1.1
Host: api.example.com
Content-Type: application/json

{
  "items": [
    { "productId": "prd_9", "quantity": 2 }
  ]
}
```

API có thể trả:

```http
HTTP/1.1 201 Created
Location: /api/orders/ord_42
Content-Type: application/json

{
  "id": "ord_42",
  "customerId": "cus_7",
  "status": "DRAFT",
  "links": {
    "self": "/api/orders/ord_42"
  }
}
```

Địa chỉ nhận POST là tập hợp nơi thực hiện tạo mới; `Location` chỉ đến tài nguyên chính vừa được tạo. Hai địa chỉ không cần có cùng cấu trúc tiền tố. Chọn `Location` theo quy ước URI chuẩn giúp các client lưu cùng một địa chỉ tham chiếu.

Không dùng `201` nếu request chỉ phân giải một alias hoặc đọc tài nguyên đã tồn tại mà không tạo gì mới.

### 7.3. Phân biệt `Location` và `Content-Location`

| Cơ chế | Vai trò |
| --- | --- |
| `Location` trong response 3xx | Xác định địa chỉ đích của redirect. |
| `Location` trong response 201 | Xác định tài nguyên chính được tạo bởi request. |
| `Content-Location` | Xác định URI tương ứng với biểu diễn được gửi trong nội dung response. |
| Liên kết trong body theo hợp đồng API | Giúp client điều hướng và nhận biết các tài nguyên liên quan. |

`Content-Location` không làm phát sinh redirect. Header này cũng không tự buộc mọi HTTP cache phải hợp nhất các khóa của những URI khác nhau.

Ví dụ, nếu một response `200` ở alias thực sự gửi biểu diễn của tài nguyên tại URI chuẩn, API có thể dùng:

```http
Content-Location: /api/orders/ord_42
```

Tuy nhiên, nếu body là kết quả tìm kiếm, bản tổng hợp hoặc biểu diễn riêng của một view, không nên gán URI của một đơn hàng làm `Content-Location` một cách máy móc. URI được công bố phải phù hợp với biểu diễn thực tế.

## 8. Nhiều URI ảnh hưởng đến cache như thế nào?

HTTP cache thường phân biệt các request dựa trên phương thức và URI đích, đồng thời xét những chiều biểu diễn liên quan như các header được nêu trong `Vary`. Vì vậy:

```text
GET /api/orders/ord_42
GET /api/customers/cus_7/orders/ord_42
```

có thể tạo ra hai mục cache riêng, ngay cả khi body JSON giống nhau.

Khi cập nhật đơn hàng qua URI chuẩn, không thể giả định các cache ở mọi alias, mọi danh sách và mọi trang tìm kiếm đều được vô hiệu hóa. Chúng có khóa khác nhau và có thể nằm ở các lớp hạ tầng khác nhau.

### Các lựa chọn kiểm soát

- Redirect các alias phù hợp để client lấy biểu diễn ở URI chuẩn.
- Quy định thời gian sống và cơ chế xác thực lại cho biểu diễn tại từng URI.
- Nếu cache nhiều view, thiết kế cơ chế vô hiệu hóa theo định danh tài nguyên hoặc nhóm phụ thuộc ở tầng ứng dụng/hạ tầng.
- Với dữ liệu cá nhân hóa, chọn chính sách cache theo quyền và ngữ cảnh; không dùng chung cache công khai chỉ vì đường dẫn giống nhau.

Trong ví dụ trước, `Cache-Control: private, no-cache` cho phép cache riêng lưu response nhưng yêu cầu xác thực lại trước khi tái sử dụng. `no-cache` không có nghĩa là cấm lưu. Nếu muốn yêu cầu cache không lưu response, dùng `no-store` theo chính sách phù hợp.

### `ETag` không phải mã định danh toàn cục

Có thể dùng `ETag` để xác thực lại biểu diễn, nhưng không được coi nó là khóa nhận diện tài nguyên trên toàn API. Hai URI có cùng chuỗi `ETag` không tự động được HTTP coi là cùng tài nguyên.

Nếu hai endpoint trả cùng biểu diễn và API dùng chung cách sinh validator, chúng có thể dùng cùng giá trị `ETag`. Khi biểu diễn khác nhau, đặc biệt với strong ETag, không được dùng một giá trị chung chỉ vì chúng đọc cùng bản ghi. Biểu diễn thu gọn, dữ liệu theo ngôn ngữ hoặc dữ liệu đã lọc theo quyền cần chính sách validator tương ứng.

Client cũng không nên tự mang `ETag` lấy ở một alias sang URI khác để ghi có điều kiện nếu API chưa cam kết rõ ngữ nghĩa đó.

## 9. Alias phải đi qua cùng quy tắc bảo mật

Một lỗi thường gặp là endpoint chuẩn kiểm tra quyền đầy đủ, còn endpoint lồng nhau chỉ kiểm tra quyền xem tài nguyên cha. Quyền xem khách hàng không nhất thiết đồng nghĩa với quyền xem toàn bộ thông tin của từng đơn hàng.

Luồng xử lý alias nên bao gồm:

1. Xác thực người gọi theo chính sách của API.
2. Xác định tenant hoặc phạm vi truy cập.
3. Tìm tài nguyên trong phạm vi được phép.
4. Kiểm tra quan hệ được nêu trên đường dẫn, nếu có.
5. Kiểm tra quyền thực hiện phương thức và quyền xem dữ liệu.
6. Sau đó mới trả biểu diễn hoặc phát redirect có chứa địa chỉ đích.

Nếu redirect trước khi kiểm tra quyền, header `Location` có thể tiết lộ định danh tài nguyên mà người gọi không được biết. Response `404` để che giấu sự tồn tại phải nhất quán giữa URI chuẩn và alias theo chính sách đã chọn.

Với `/api/me`, đích phụ thuộc người gọi. Không dùng redirect vĩnh viễn công khai có thể được tái sử dụng cho tài khoản khác. Có thể trả trực tiếp hồ sơ kèm liên kết chuẩn, hoặc dùng redirect tạm thời với chính sách cache phù hợp dữ liệu xác thực; `no-store` là một lựa chọn khi API muốn tránh lưu response phân giải này.

Nếu tạo URI tuyệt đối ở sau reverse proxy, hãy lấy public base URL từ cấu hình đáng tin cậy hoặc cơ chế forwarded header đã giới hạn proxy tin cậy. Không phản chiếu tùy ý `Host` hay một header do client kiểm soát vào `Location`. Một URI chuẩn do client khác cung cấp cũng không tự động là địa chỉ đáng tin để redirect.

## 10. Thao tác ghi và idempotency qua nhiều đường dẫn

Nếu API cho phép sửa cùng một đơn hàng qua hai URI, tất cả các đường dẫn đó phải áp dụng cùng:

- Quy tắc phân quyền và tenant.
- Kiểm tra dữ liệu đầu vào.
- Quy tắc chuyển trạng thái nghiệp vụ.
- Kiểm soát phiên bản hoặc ghi có điều kiện.
- Cơ chế chống xử lý lặp nếu thao tác cần cơ chế này.

Ví dụ một ứng dụng gửi lệnh xác nhận đơn hàng qua alias, bị mất response, rồi thử lại qua URI chuẩn. Nếu kho chống lặp chỉ dùng raw path làm phạm vi khóa, hai request có thể bị xử lý như hai thao tác độc lập.

Một thiết kế khóa chống lặp cho lệnh tác động đến tài nguyên đã tồn tại có thể gồm:

```text
(tenant, caller-scope, operation, canonical-resource-id, idempotency-key)
```

Đây là gợi ý thiết kế ứng dụng, không phải cấu trúc khóa bắt buộc của HTTP. API vẫn cần quy định thời hạn lưu khóa, cách xử lý request đang chạy, cách so sánh payload và response khi cùng khóa được dùng với nội dung khác.

Với request tạo mới, chưa có định danh tài nguyên mới để đưa vào khóa. Có thể dùng phạm vi tập hợp hoặc đối tượng cha đã chuẩn hóa cùng loại thao tác và danh tính người gọi. Không áp dụng công thức cho tài nguyên đã tồn tại một cách máy móc.

Điều đặc biệt cần tránh là thực hiện thao tác ghi tại alias rồi trả `307`/`308` để client thực hiện lại cùng thao tác ở URI chuẩn. Redirect để chuyển tiếp thao tác phải xảy ra trước khi thực thi tác động nghiệp vụ; nếu thao tác đã hoàn tất, hãy trả response thể hiện kết quả theo hợp đồng của thao tác đó.

## 11. Minh họa Java/Spring: đọc chuẩn và phân giải đường dẫn lồng nhau

Ví dụ dưới đây chọn hai hành vi:

- URI chuẩn trả biểu diễn đơn hàng.
- URI trong phạm vi khách hàng kiểm tra quyền và quan hệ rồi trả `307` kèm `no-store`.

Lựa chọn tạm thời ở đây phù hợp khi API không cam kết quan hệ khách hàng–đơn hàng là bất biến suốt vòng đời. Nếu quan hệ thực sự bất biến và API cam kết alias tồn tại lâu dài, có thể cân nhắc `308` với chính sách cache tương ứng.

Đoạn mã minh họa lớp HTTP; `OrderService` là service nghiệp vụ của ứng dụng, không phải lớp có sẵn trong Spring.

```java
import java.net.URI;
import java.security.Principal;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

@RestController
@RequestMapping("/api")
public class OrderController {
    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/orders/{orderId}")
    public ResponseEntity<OrderView> getOrder(
            @PathVariable("orderId") String orderId,
            Principal principal) {

        VisibleOrder order = orders.requireVisible(orderId, principal);
        URI canonicalUri = canonicalOrderUri(order.id());

        OrderView body = new OrderView(
                order.id(),
                order.customerId(),
                order.status(),
                new Links(canonicalUri.toString()));

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(body);
    }

    @GetMapping("/customers/{customerId}/orders/{orderId}")
    public ResponseEntity<Void> resolveCustomerOrder(
            @PathVariable("customerId") String customerId,
            @PathVariable("orderId") String orderId,
            Principal principal) {

        VisibleOrder order = orders.requireVisibleUnderCustomer(
                customerId, orderId, principal);

        return ResponseEntity.status(HttpStatus.TEMPORARY_REDIRECT)
                .location(canonicalOrderUri(order.id()))
                .cacheControl(CacheControl.noStore())
                .build();
    }

    private static URI canonicalOrderUri(String orderId) {
        return UriComponentsBuilder
                .fromPath("/api/orders/{orderId}")
                .encode()
                .buildAndExpand(orderId)
                .toUri();
    }

    public record Links(String self) {}

    public record OrderView(
            String id,
            String customerId,
            String status,
            Links links) {}

    public record VisibleOrder(
            String id,
            String customerId,
            String status) {}

    public interface OrderService {
        VisibleOrder requireVisible(String orderId, Principal principal);

        VisibleOrder requireVisibleUnderCustomer(
                String customerId,
                String orderId,
                Principal principal);
    }
}
```

Các điểm cần xác định khi tích hợp vào ứng dụng:

1. Cấu hình xác thực phải bảo đảm request được bảo vệ trước khi controller xử lý. `Principal` ở chữ ký phương thức không tự cấu hình bảo mật.
2. `requireVisible` kiểm tra tenant và quyền xem đơn hàng; `requireVisibleUnderCustomer` cần thêm kiểm tra quan hệ với `customerId`.
3. Lỗi từ service phải được ánh xạ sang `404`/`403` và cấu trúc lỗi thống nhất của API. Đoạn minh họa không định nghĩa hệ thống ánh xạ lỗi đó.
4. Cách tạo URI dùng builder và biến path, đồng thời ứng dụng vẫn cần xác thực định dạng định danh. Không nối trực tiếp dữ liệu đầu vào vào một URL tùy ý.
5. Ví dụ dùng đường dẫn bắt đầu từ gốc. Nếu public API có tiền tố do gateway thêm vào, phần tạo liên kết phải dùng đúng public base path đã cấu hình; không mặc định `/api` đúng ở mọi môi trường.
6. `no-store` được chọn để làm rõ chính sách của ví dụ. Khi đưa cache vào sản phẩm, cần quyết định lại dựa trên độ nhạy cảm và yêu cầu hiệu năng.

Có thể quan sát riêng response redirect bằng công cụ HTTP không tự theo redirect:

```bash
curl -i \
  -H "Authorization: Bearer <token>" \
  https://api.example.com/api/customers/cus_7/orders/ord_42
```

Với người gọi có quyền và quan hệ hợp lệ, response mong đợi của ví dụ là `307` với `Location: /api/orders/ord_42`. Khi gọi URI đích, client vẫn phải gửi thông tin xác thực phù hợp; redirect không thay thế bước phân quyền ở đích.

## 12. Giữ hợp đồng nhất quán trong OpenAPI và client

Nếu công bố một alias, hãy mô tả nó như một phần hợp đồng, gồm:

- Phương thức được hỗ trợ.
- Điều kiện alias hợp lệ và cách kiểm tra tài nguyên cha.
- Response `200` hay redirect, tính tạm thời hoặc vĩnh viễn.
- Header `Location` nếu trả redirect.
- Cơ chế xác thực, quyền truy cập và response lỗi.
- Chính sách cache và thời gian hỗ trợ nếu alias đang được ngừng dùng.

Một phần mô tả OpenAPI minh họa cho alias đọc dữ liệu:

```yaml
paths:
  /api/customers/{customerId}/orders/{orderId}:
    get:
      summary: Phân giải đơn hàng trong phạm vi khách hàng
      description: >-
        Kiểm tra quyền và quan hệ khách hàng trước khi chuyển tạm thời
        đến URI chuẩn của đơn hàng.
      parameters:
        - name: customerId
          in: path
          required: true
          schema:
            type: string
        - name: orderId
          in: path
          required: true
          schema:
            type: string
      responses:
        '307':
          description: URI chuẩn để truy cập đơn hàng
          headers:
            Location:
              description: Đường dẫn đến đơn hàng theo định danh chuẩn
              schema:
                type: string
        '401':
          description: Chưa xác thực hoặc thông tin xác thực không hợp lệ
        '404':
          description: Không tìm thấy trong phạm vi được phép
```

Đây chỉ là phần mô tả đường dẫn. Tài liệu hoàn chỉnh còn cần khai báo bảo mật và schema lỗi theo hợp đồng chung; riêng bảng response không tự bảo vệ endpoint.

Không giả định SDK sinh từ OpenAPI tự động cung cấp mọi hành vi redirect mong muốn. Cần xác định client có trả response 3xx cho ứng dụng xử lý, tự theo redirect hay từ chối trong một số tình huống. Những khác biệt đó ảnh hưởng trực tiếp đến việc chọn trả `200` hay redirect ở alias.

## 13. Đổi URI chuẩn mà vẫn hỗ trợ client cũ

Ví dụ một API cũ dùng:

```text
/api/order/ord_42
```

và muốn chuyển sang:

```text
/api/orders/ord_42
```

Có thể triển khai theo trình tự:

1. Bổ sung URI mới và xác nhận ngữ nghĩa, quyền truy cập, biểu diễn tương đương trong phạm vi cần chuyển đổi.
2. Cho các response mới công bố liên kết chuẩn mới; các response tạo mới dùng `Location` mới.
3. Duy trì URI cũ theo hợp đồng tương thích: trả cùng dữ liệu hoặc redirect phù hợp với phương thức và client.
4. Theo dõi lượng sử dụng URI cũ để biết client nào còn phụ thuộc.
5. Công bố thời điểm và điều kiện ngừng hỗ trợ; chỉ loại bỏ alias theo chính sách phiên bản đã cam kết.

Tránh chuỗi redirect:

```text
địa chỉ cũ -> địa chỉ trung gian -> địa chỉ chuẩn hiện tại
```

Khi có thể, các alias nên dẫn trực tiếp đến URI chuẩn hiện tại. Chuỗi dài làm tăng độ trễ, khó chẩn đoán và dễ vượt giới hạn redirect của client. Quy tắc chuyển hướng phải tránh vòng lặp giữa gateway và ứng dụng, đặc biệt khi chúng không thống nhất scheme, host hoặc dấu gạch chéo cuối.

Không coi `/v1/orders/ord_42` và `/v2/orders/ord_42` là alias chỉ vì cùng chứa một định danh đơn hàng. Hai phiên bản có thể khác schema, quyền, enum hoặc ngữ nghĩa thao tác. Redirect giữa phiên bản chỉ phù hợp khi đã bảo đảm tương thích cho hành vi được chuyển và công bố rõ hợp đồng đó.

## 14. Các sai sót thường gặp và tiêu chí hoàn tất thiết kế

| Sai sót | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Mỗi endpoint tự ghép một dạng liên kết | Cùng đơn hàng có nhiều địa chỉ được xem là chuẩn | Dùng một quy tắc tạo URI chuẩn cho response và `Location`. |
| Bỏ qua tài nguyên cha trên path | Trả thành công cho quan hệ không tồn tại | Kiểm tra quan hệ cùng với tenant và quyền. |
| Redirect vĩnh viễn cho đích thay đổi | Client tiếp tục truy cập đích cũ | Chọn response trực tiếp hoặc redirect tạm thời và cache phù hợp. |
| Cho rằng `Content-Location` gộp cache | Alias vẫn trả dữ liệu cũ sau cập nhật | Thiết kế cache/invalidation cho từng URI hoặc chuyển về URI chuẩn. |
| Dùng `301`/`302` cho mọi thao tác ghi | Có thể thay đổi POST thành GET tại client | Chọn chính sách theo phương thức; đánh giá `307`/`308` và khả năng gửi lại body. |
| Thực hiện lệnh rồi redirect để gửi lại lệnh | Tác động nghiệp vụ có thể bị lặp | Redirect trước khi thực thi, hoặc trả kết quả của thao tác đã hoàn tất. |
| Phân giải alias trước khi phân quyền | Tiết lộ định danh hoặc địa chỉ tài nguyên | Chỉ công bố đích sau các kiểm tra cần thiết. |
| Đồng nhất collection, view và tài nguyên | Client hiểu sai loại response | Mô tả riêng từng hợp đồng và liên kết đến tài nguyên thích hợp. |

Trước khi chốt thiết kế cho một nhóm URI, cần trả lời được các điểm sau:

- Tài nguyên được nhận diện bằng gì, trong phạm vi tenant nào?
- URI nào được API công bố làm tham chiếu chuẩn, và vì sao nó ổn định?
- Mỗi đường dẫn khác là alias, tập hợp, truy vấn hay tài nguyên có ngữ nghĩa riêng?
- Quan hệ trên đường dẫn lồng nhau được kiểm tra ở đâu?
- Alias hỗ trợ phương thức nào, trả trực tiếp hay redirect, và đích ổn định đến mức nào?
- `Location`, liên kết trong body và `Content-Location` có được dùng đúng vai trò?
- Cache, validator và quyền truy cập có nhất quán ở các đường dẫn liên quan?
- Nếu cho phép ghi qua nhiều URI, cơ chế kiểm soát xung đột và chống lặp có cùng nhận diện thao tác?
- Client có biết cách xử lý response và có đường chuyển đổi khi URI cũ ngừng được hỗ trợ?
