# Request target, phương thức và tài nguyên đích

## Mục tiêu bài học

Hai yêu cầu `GET /orders/842` và `DELETE /orders/842` có cùng đường dẫn nhưng yêu cầu server thực hiện những việc khác nhau. Ngược lại, hai yêu cầu có cùng đường dẫn trên hai máy chủ khác nhau chưa chắc hướng đến cùng tài nguyên.

Muốn thiết kế REST API đúng, cần đọc một yêu cầu HTTP thành các phần có ý nghĩa: thao tác được yêu cầu, đích của thao tác, máy chủ có thẩm quyền phục vụ và dữ liệu đi kèm.

Trong chương **Nền tảng HTTP** của module **INTEGRATION_API_REST**, bài học này giải thích request target và mối quan hệ của nó với phương thức, URI cùng tài nguyên đích. Những kiến thức này làm nền cho thiết kế resource, phân trang, cache, idempotency, OpenAPI, xác thực, phân quyền, xử lý lỗi và kiểm thử API bằng Java/Spring hoặc công nghệ tương đương.

Sau bài học, bạn có thể:

- Đọc request-line của HTTP/1.1 và tách đúng phương thức, request target, phiên bản.
- Nhận diện bốn dạng request target trong HTTP/1.1.
- Phân biệt path, query, fragment và authority.
- Giải thích vì sao một đường dẫn chưa đủ xác định thao tác hoặc toàn bộ URI đích.
- Liên hệ phương thức với ngữ nghĩa safe, idempotent và các response cơ bản.
- Ánh xạ URI vào path variable, query parameter và controller Spring.
- Nhận diện các lỗi định tuyến, mã hóa và kiểm tra quyền thường gặp.

## 1. Đọc một yêu cầu HTTP/1.1

Xét một yêu cầu minh họa:

```http
GET /orders/842?view=summary HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Accept: application/json

```

Dòng đầu tiên là **request-line**:

```text
method SP request-target SP HTTP-version
```

Trong đó `SP` là ký tự khoảng trắng phân tách các thành phần. Trên đường truyền HTTP/1.1, dòng được kết thúc theo quy tắc CRLF; các ví dụ trong bài trình bày dạng văn bản để dễ đọc.

| Thành phần | Giá trị trong ví dụ | Vai trò |
| --- | --- | --- |
| Method | `GET` | Nêu ngữ nghĩa thao tác mà client yêu cầu |
| Request target | `/orders/842?view=summary` | Chỉ đích của yêu cầu theo một dạng mà HTTP cho phép |
| HTTP version | `HTTP/1.1` | Phiên bản giao thức của thông điệp |

Những dòng tiếp theo là các header field. Dòng trống đánh dấu kết thúc phần header; nội dung yêu cầu có thể theo sau nếu thao tác và hợp đồng có sử dụng.

Các ví dụ trong bài lược bỏ một số chi tiết truyền tải. Khi có body, việc xác định độ dài và đóng khung thông điệp vẫn phải được client, server hoặc thư viện HTTP thực hiện đúng.

### 1.1. Ba câu hỏi cần tách riêng

Khi đọc request, hãy hỏi:

1. **Muốn làm gì?** Xem phương thức và ngữ nghĩa đã công bố.
2. **Làm với đích nào?** Xem request target cùng thông tin để xác định URI đích.
3. **Với tư cách và dữ liệu nào?** Xem thông tin xác thực, header điều kiện, kiểu nội dung và body.

Không nên tìm câu trả lời cho cả ba câu hỏi chỉ trong URL hoặc chỉ trong JSON.

Ví dụ:

- `Authorization` cung cấp thông tin xác thực, không thay thế định danh đơn hàng.
- `Accept` có thể ảnh hưởng representation được chọn, không biến GET thành thao tác ghi.
- Body tạo đơn chứa dữ liệu nghiệp vụ, không làm request target tự đổi từ tập hợp đơn sang một đơn đã có ID.

## 2. Request target không phải lúc nào cũng là một path

Trong các API thường ngày, bạn hay gặp `/orders/842`. Tuy nhiên, HTTP/1.1 định nghĩa bốn dạng request target cho những tình huống khác nhau.

| Dạng | Ví dụ | Tình huống tiêu biểu |
| --- | --- | --- |
| Origin-form | `/orders/842?view=summary` | Yêu cầu thông thường gửi tới origin server hoặc reverse proxy |
| Absolute-form | `http://api.example.com/orders/842` | Yêu cầu thông thường qua một forward proxy |
| Authority-form | `api.example.com:443` | CONNECT thông thường để thiết lập đường hầm |
| Asterisk-form | `*` | OPTIONS hỏi về server nói chung |

Đây là các dạng của HTTP/1.1. Không nên lấy request-line của HTTP/1.1 làm cấu trúc truyền tải nguyên xi cho HTTP/2 hoặc HTTP/3.

### 2.1. Origin-form: path và query

Ví dụ:

```http
GET /orders/842?view=summary HTTP/1.1
Host: api.example.com
```

Request target gồm:

```text
/orders/842?view=summary
```

Trong dạng này:

- Path là `/orders/842`.
- Query là `view=summary`.
- Scheme và authority không xuất hiện trực tiếp trong request target.

Nếu URI không có path, client dùng `/` trong origin-form. Chẳng hạn, khi truy cập gốc của máy chủ:

```http
GET / HTTP/1.1
Host: api.example.com
```

Nếu có query tại gốc, request target có thể là `/?q=java`.

Origin-form là dạng thường thấy khi trình duyệt hoặc HTTP client gọi REST API. Việc phía trước backend có reverse proxy không bắt client phải dùng absolute-form.

### 2.2. Absolute-form: một URI tuyệt đối

Ví dụ client gửi yêu cầu HTTP qua forward proxy:

```http
GET http://api.example.com/orders/842?view=summary HTTP/1.1
Host: api.example.com
```

Request target chứa URI tuyệt đối, cho phép proxy biết origin cần chuyển đến.

Một **forward proxy** đại diện cho client khi truy cập server khác. Một **reverse proxy** đứng trước các server để tiếp nhận và chuyển tiếp yêu cầu tới backend. Hai vai trò này không nên bị gộp thành một.

Không phải cứ “có proxy” thì request target luôn là URI tuyệt đối. Với HTTPS qua forward proxy theo cơ chế đường hầm thông thường, client thường thiết lập CONNECT trước, rồi trao đổi HTTP được bảo vệ bởi TLS bên trong đường hầm.

Trong absolute-form, authority đã nằm trong target. Không xây hợp đồng dựa vào việc target và Host mâu thuẫn nhau; các thành phần HTTP phải xử lý authority theo quy tắc giao thức, thay vì mỗi tầng tự chọn một nguồn khác nhau.

### 2.3. Authority-form: CONNECT tới host và port

Ví dụ:

```http
CONNECT api.example.com:443 HTTP/1.1
Host: api.example.com:443
```

Ở đây request target là:

```text
api.example.com:443
```

Đó là authority gồm host và port đích của đường hầm, không phải đường dẫn resource trong REST API. Không có `https://` hay `/orders` trong authority-form của CONNECT thông thường.

Một phản hồi thành công có thể bắt đầu như sau:

```http
HTTP/1.1 200 Connection Established

```

Sau khi thiết lập đường hầm thành công, luồng dữ liệu chuyển sang mục đích đường hầm. Không nên hiểu phản hồi này là server vừa trả JSON của một resource.

CONNECT và những cơ chế mở rộng liên quan có các quy tắc riêng; trong bài này, authority-form được giới thiệu cho trường hợp HTTP/1.1 thông thường.

### 2.4. Asterisk-form: OPTIONS cho server nói chung

Ví dụ:

```http
OPTIONS * HTTP/1.1
Host: api.example.com
```

Dấu `*` không có nghĩa “đọc mọi resource” hoặc “khớp mọi đường dẫn”. Nó được dùng với OPTIONS để hỏi về server nói chung.

Cần phân biệt với:

```http
OPTIONS /orders/842 HTTP/1.1
Host: api.example.com
```

Yêu cầu thứ hai hướng tới một resource cụ thể.

Cũng không phải mọi OPTIONS đều là CORS preflight. Preflight là một trường hợp sử dụng OPTIONS với các header đặc thù, chẳng hạn `Origin` và `Access-Control-Request-Method`.

## 3. Từ request target đến URI của tài nguyên đích

Xét URI mà người dùng hoặc client sử dụng:

```text
https://api.example.com:8443/orders/842?view=summary#payment
```

Các thành phần có ý nghĩa khác nhau:

| Thành phần | Giá trị | Vai trò |
| --- | --- | --- |
| Scheme | `https` | Cơ chế truy cập |
| Authority | `api.example.com:8443` | Host và port |
| Path | `/orders/842` | Thành phần đường dẫn |
| Query | `view=summary` | Thành phần truy vấn |
| Fragment | `payment` | Tham chiếu được xử lý phía client đối với tài liệu hoặc representation |

Trong một yêu cầu origin-form thông thường, phần gửi tới server có dạng:

```http
GET /orders/842?view=summary HTTP/1.1
Host: api.example.com:8443
```

Fragment `#payment` không được gửi như một phần request target HTTP. Nếu backend cần một tham số để xử lý, không đặt nó trong fragment rồi chờ controller đọc được.

### 3.1. Path giống nhau chưa có nghĩa cùng tài nguyên

Hai URI:

```text
https://shop-a.example/orders/842
https://shop-b.example/orders/842
```

có cùng path nhưng khác authority. Không thể mặc định chúng định danh cùng một đơn hàng.

Tương tự, scheme và port có thể làm khác ngữ cảnh truy cập. Khi định tuyến, tạo liên kết, kiểm tra cache hoặc phân quyền theo host, không nên chỉ giữ path rồi bỏ qua những thành phần cần thiết khác.

Một đường dẫn tương đối chỉ có nghĩa đầy đủ khi được đặt trong ngữ cảnh URI phù hợp.

### 3.2. Host không phải một URL đầy đủ

Với HTTP/1.1, Host là thành phần bắt buộc theo quy tắc giao thức. Ví dụ hợp lệ về hình thức sử dụng là:

```http
Host: api.example.com
```

hoặc:

```http
Host: api.example.com:8443
```

Không viết:

```http
Host: https://api.example.com/orders
```

vì scheme và path không thuộc giá trị Host.

Server có thể dùng authority để chọn virtual host hoặc ứng dụng. Tuy vậy, giá trị do client gửi vẫn phải được kiểm tra và xử lý theo cấu hình tin cậy; nó không tự chứng minh người gọi có quyền trên dữ liệu.

### 3.3. HTTPS sau reverse proxy cần ngữ cảnh triển khai rõ ràng

Một client có thể truy cập:

```text
https://api.example.com/api/orders/842
```

trong khi reverse proxy chuyển tiếp tới:

```text
http://orders-service:8080/orders/842
```

Scheme, authority và path mà backend trực tiếp nhìn thấy có thể khác URI công khai.

Hệ thống cần cấu hình rõ:

- Phần prefix nào được giữ hoặc loại bỏ.
- URI công khai dùng để tạo Location và các liên kết.
- Proxy nào được phép cung cấp thông tin chuyển tiếp.
- Cách ghi log để đối chiếu request bên ngoài và request nội bộ.

Không tin vô điều kiện các header chuyển tiếp do client tự gửi. Nếu một ứng dụng dùng Host hoặc thông tin forwarded để sinh URL nhạy cảm, cần có chính sách host và proxy tin cậy phù hợp.

Đây là trách nhiệm phối hợp giữa tầng giao thức, hạ tầng và ứng dụng, không chỉ là việc đổi annotation của controller.

## 4. HTTP/2 và HTTP/3 biểu diễn thông tin này ra sao?

HTTP/2 và HTTP/3 không truyền request-line dạng văn bản như HTTP/1.1. Với một yêu cầu thông thường, các thông tin tương ứng được biểu diễn bằng pseudo-header:

```text
:method: GET
:scheme: https
:authority: api.example.com
:path: /orders/842?view=summary
accept: application/json
```

Đây là cách trình bày để đọc, không phải một request HTTP/1.1 có thêm các header bắt đầu bằng dấu hai chấm.

Các ý nghĩa vẫn còn:

- Phương thức nêu thao tác.
- Scheme và authority góp phần xác định URI đích.
- `:path` của yêu cầu thông thường chứa path và query.
- Các header khác bổ sung ngữ cảnh xử lý.

CONNECT thông thường có cách sử dụng pseudo-header riêng; không lấy ví dụ GET trên để suy ra CONNECT cũng phải có đủ các trường giống hệt.

Khi lập trình bằng thư viện HTTP hoặc framework, phần lớn chi tiết mã hóa thông điệp do thư viện xử lý. Người thiết kế API vẫn cần hiểu các thành phần để đọc log và chẩn đoán lỗi đúng.

## 5. Tài nguyên đích và kết quả tạo ra không phải lúc nào cũng trùng nhau

Xét:

```http
POST /orders HTTP/1.1
Host: api.example.com
Content-Type: application/json
Authorization: Bearer <access-token>

{
  "items": [
    {
      "productId": "book-1",
      "quantity": 2
    }
  ]
}
```

Tài nguyên đích của request là tập hợp `/orders`. Server xử lý dữ liệu gửi tới tập hợp theo hợp đồng và có thể tạo đơn mới.

```http
HTTP/1.1 201 Created
Location: /orders/842
Content-Type: application/json
Cache-Control: no-store

{
  "id": "842",
  "status": "PENDING_PAYMENT"
}
```

`Location` chỉ ra URI của resource mới được tạo trong ví dụ. Nó không làm request target ban đầu trở thành `/orders/842`.

Các ID xuất hiện trong body cũng có vai trò riêng:

- `productId` tham chiếu sản phẩm liên quan.
- Credentials xác định người gọi.
- URI `/orders` xác định resource nhận yêu cầu tạo.

Phân biệt các vai trò giúp tránh thiết kế mà một `id` bất kỳ trong JSON âm thầm thay thế resource đã được chỉ ra trong URI.

### 5.1. Cùng target, phương thức khác nhau

Ví dụ:

```text
GET    /orders/842
PUT    /orders/842
PATCH  /orders/842
DELETE /orders/842
```

Cùng một resource có thể hỗ trợ nhiều thao tác. Server không chỉ định tuyến bằng chuỗi path mà còn phải xét phương thức và các điều kiện liên quan.

Một framework có thể ánh xạ các tổ hợp này tới các hàm khác nhau, nhưng hợp đồng bên ngoài vẫn là HTTP tương tác với resource.

### 5.2. Resource không bắt buộc là một bảng dữ liệu

Resource `/orders/842` có thể được tổng hợp từ nhiều bảng hoặc dịch vụ. Path không bắt buộc chứa tên entity, tên schema hoặc tên phương thức Java.

Query như `?view=summary` có thể chọn một biến thể theo hợp đồng; header Accept có thể chọn định dạng. Resource, representation và cách lưu trữ là những khái niệm liên quan nhưng khác nhau.

## 6. Phương thức cung cấp ngữ nghĩa, không chỉ chọn hàm xử lý

Các phương thức tiêu biểu trong REST API:

| Phương thức | Ý nghĩa chính trong tương tác | Safe | Idempotent theo ngữ nghĩa phương thức |
| --- | --- | --- | --- |
| GET | Yêu cầu representation hiện tại của resource đích | Có | Có |
| HEAD | Tương tự GET nhưng response không gửi nội dung | Có | Có |
| POST | Yêu cầu resource đích xử lý dữ liệu theo ngữ nghĩa đã công bố | Không | Không được bảo đảm |
| PUT | Tạo hoặc thay thế trạng thái resource đích theo representation gửi lên | Không | Có |
| PATCH | Áp dụng thay đổi theo một tài liệu bản vá | Không | Không được bảo đảm |
| DELETE | Yêu cầu bỏ liên hệ giữa URI đích và chức năng hiện tại của resource | Không | Có |
| OPTIONS | Hỏi về các lựa chọn giao tiếp của resource hoặc server | Có | Có |

CONNECT đã được giới thiệu với authority-form và có mục đích đường hầm riêng. Bảng trên không phải danh sách mọi phương thức mà giao thức có thể hỗ trợ.

### 6.1. Safe nói về điều client yêu cầu

GET không được dùng để yêu cầu chuyển đơn thành đã thanh toán hoặc xóa đơn.

```text
GET /orders/842/delete
GET /orders/842/confirm-payment
```

Dù path có thể được router nhận diện, thiết kế này dùng sai ngữ nghĩa GET. Cơ chế tải trước, kiểm tra liên kết hoặc công cụ tự động có thể thực hiện GET mà không có ý định thay đổi nghiệp vụ.

Server vẫn có thể ghi access log hoặc số liệu đo lường khi xử lý GET. Những hiệu ứng nội bộ đó không có nghĩa GET được phép trở thành một lệnh ghi nghiệp vụ do client yêu cầu.

### 6.2. Idempotent nói về tác động dự định

Nhiều yêu cầu giống nhau có tính idempotent phải có tác động dự định tương đương với một yêu cầu như vậy. Không yêu cầu mọi response giống nhau.

Ví dụ, xóa một resource có thể trả 204 lần đầu và 404 ở lần sau. Nếu trạng thái cuối vẫn là resource không còn được cung cấp tại URI đó, sự khác nhau về response chưa đủ kết luận vi phạm idempotency.

Ngược lại, hai lần POST tới `/orders` với cùng JSON có thể tạo hai đơn nếu hợp đồng không có cơ chế chống trùng. Cùng method và cùng target không có nghĩa server phải tự nhận đó là cùng một ý định.

Tính idempotent giúp thiết kế retry, nhưng vẫn cần xét điều kiện cập nhật, thời gian chờ, lỗi và hợp đồng nghiệp vụ. Stateless cũng không tự bảo đảm thao tác chỉ thực hiện một lần.

### 6.3. Method phân biệt chữ hoa và chữ thường

Tên phương thức HTTP là token phân biệt chữ hoa và chữ thường. Các phương thức chuẩn thường được viết như `GET`, `POST`, `PUT`.

Không tự đổi `get` thành `GET` rồi mặc định giao thức coi chúng giống nhau. Hành vi với một method không được nhận diện còn phụ thuộc vào khả năng và chính sách xử lý của server.

Điều này khác với quy tắc tên header field không phân biệt hoa thường. Không nên dùng một quy tắc chuẩn hóa cho mọi thành phần HTTP.

### 6.4. HEAD không có nội dung response

Ví dụ:

```http
HEAD /orders/842 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
```

Server xử lý theo ngữ nghĩa tương ứng với GET nhưng không gửi nội dung phản hồi. HEAD vẫn có thể cung cấp metadata hữu ích như Content-Type hoặc validator.

Nếu phản hồi HEAD có Content-Length phù hợp với độ dài nội dung mà GET sẽ trả, không được suy ra ngay rằng server phải gửi từng ấy byte body cho HEAD. Quy tắc về nội dung của HEAD vẫn áp dụng.

HEAD không phải cách bỏ qua xác thực hay phân quyền của GET.

### 6.5. Body không tự thay thế request target

Một body trong GET không có ngữ nghĩa chung được HTTP định nghĩa để thay đổi ý nghĩa hoặc đích của yêu cầu. Không nên thiết kế một GET mà bộ lọc bắt buộc chỉ nằm trong body rồi kỳ vọng mọi client, proxy và cache đều hiểu giống ứng dụng.

Với truy vấn đơn giản, query parameter thường là lựa chọn rõ hơn. Nếu cần xử lý một truy vấn phức tạp bằng POST, hãy công bố resource đích, schema, kết quả và hành vi cache hoặc gọi lại của thao tác đó.

Tương tự, một trường `method` trong JSON không tự đổi phương thức HTTP trên đường truyền. Nếu hệ thống dùng cơ chế ghi đè phương thức ở tầng ứng dụng, đó là một quy ước bổ sung cần được nhận diện và kiểm soát.

## 7. Path, query và header nên mang dữ liệu gì?

Một cách tổ chức thường dễ hiểu:

| Vị trí | Vai trò thường gặp | Ví dụ |
| --- | --- | --- |
| Path | Định danh resource và quan hệ cần thiết | `/orders/842/items/item-2` |
| Query | Lọc, sắp xếp, phân trang hoặc lựa chọn theo hợp đồng | `?status=CONFIRMED&limit=20` |
| Header | Metadata và điều kiện xử lý giao thức | `Accept`, `Authorization`, `If-Match` |
| Body | Representation hoặc dữ liệu thao tác | Các dòng hàng khi tạo đơn |

Đây là hướng dẫn thiết kế, không phải quy tắc bắt buộc rằng mọi ID phải nằm trong path và mọi giá trị khác phải nằm trong query.

### 7.1. Query vẫn thuộc URI

Hai request target:

```text
/orders?status=CONFIRMED
/orders?status=CANCELLED
```

là hai URI truy cập tập hợp với những điều kiện khác nhau theo hợp đồng.

Vì query thuộc URI, nó liên quan đến định tuyến, log, cache và liên kết. Đừng bỏ query khi tạo cache key cho các response mà bộ lọc làm thay đổi nội dung.

Một cache HTTP còn cần xét method, URI đích và các yếu tố lựa chọn response như Vary theo quy tắc cache. Chỉ dùng path làm khóa cho mọi host, mọi query và mọi người dùng có thể trả sai dữ liệu.

### 7.2. Query parameter là quy ước cần được định nghĩa

Cách viết `name=value&name2=value2` rất phổ biến, nhưng HTTP không tự định nghĩa ý nghĩa nghiệp vụ cho từng cặp.

Cần công bố:

- Các tên tham số được hỗ trợ.
- Kiểu dữ liệu và giới hạn.
- Giá trị mặc định.
- Khác biệt giữa tham số thiếu và giá trị rỗng.
- Có cho phép tham số lặp không.
- Hành vi với tham số không được hỗ trợ.

Ví dụ:

```text
/orders?limit=20&limit=1000
```

Nếu gateway lấy giá trị đầu còn ứng dụng lấy giá trị cuối, hai tầng có thể hiểu cùng request khác nhau. Với tham số đơn trị, một chính sách rõ có thể là từ chối đầu vào lặp; với tham số đa trị, cần mô tả cách kết hợp.

Không tự mặc định mọi thứ tự query parameter hoặc mọi dạng lặp đều tương đương.

### 7.3. Ngữ cảnh giao thức không phải quyền truy cập

```http
GET /tenants/tenant-a/orders/842 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
```

Path nói người gọi muốn truy cập resource trong tenant nào. Nó không chứng minh người gọi thuộc tenant đó.

Server vẫn cần xác minh danh tính và kiểm tra quyền trên tenant cùng đơn hàng. Tương tự, ID khó đoán chỉ làm giảm khả năng đoán, không thay thế phân quyền.

Nếu một ID ở path và một ID trong body cùng mô tả một đối tượng, hợp đồng cần xác định có cho phép cả hai hay không và xử lý mâu thuẫn ra sao. Không để từng tầng tự chọn một nguồn khác nhau.

## 8. Mã hóa URI: dấu phân cách khác với dữ liệu

Request target được phân tích theo cú pháp URI. Các ký tự như `/`, `?`, `&` hoặc `#` có vai trò khác nhau tùy vị trí và quy ước.

### 8.1. Mã hóa giá trị, không ghép chuỗi tùy ý

Giả sử muốn tìm sách có cụm:

```text
Java & Spring
```

Một request target phù hợp có thể là:

```text
/books?q=Java%20%26%20Spring
```

Ở đây:

- `%20` biểu diễn khoảng trắng trong dữ liệu.
- `%26` biểu diễn ký tự `&` thuộc giá trị tìm kiếm.
- Dấu `?` phân tách path và query.

Nếu ghép trực tiếp dữ liệu thành `q=Java & Spring`, khoảng trắng và dấu phân cách có thể làm target không hợp lệ hoặc bị diễn giải sai.

Nên dùng API xây dựng URI hoặc chức năng mã hóa tham số của HTTP client. Không mã hóa toàn bộ URI như một giá trị duy nhất rồi làm mất ý nghĩa các dấu phân cách cấu trúc.

Ví dụ lệnh minh họa trên Windows:

```powershell
curl.exe --get "https://api.example.com/books" --data-urlencode "q=Java & Spring" --data-urlencode "limit=20"
```

Lệnh để công cụ mã hóa giá trị query, thay vì yêu cầu người dùng tự ghép từng ký tự phần trăm. Domain trong ví dụ chỉ dùng minh họa hợp đồng, không giả định có dịch vụ thực đang phục vụ.

### 8.2. Dấu cộng không có một ý nghĩa duy nhất trong mọi URI

Trong cách mã hóa form thường dùng, bộ giải mã có thể coi `+` là khoảng trắng. Tuy nhiên, không nên áp dụng quy tắc “mọi dấu cộng trong mọi URI đều là khoảng trắng”.

Một query value cần dấu cộng thật phải được mã hóa và giải mã theo đúng quy ước giữa client với server. Thư viện xử lý URI và thư viện xử lý form có thể có mục đích khác nhau.

### 8.3. Mã hóa dấu slash có thể làm lộ sự khác nhau giữa các tầng

So sánh:

```text
/files/a/b
/files/a%2Fb
```

Dấu slash thật phân tách các path segment. Với slash đã mã hóa, gateway, server và framework có thể có chính sách chấp nhận, từ chối hoặc giải mã khác nhau.

Không nên mặc định chúng luôn định danh cùng resource hoặc luôn khác nhau theo một cách thống nhất ở mọi triển khai. Cần xác định tập ký tự ID được phép dùng và giữ quy trình phân tích nhất quán.

Một chuỗi như `%252F` còn có thể trở thành `%2F` sau một lượt giải mã rồi thành slash sau lượt tiếp theo. Giải mã lặp không có kiểm soát có thể làm thay đổi cách xác định resource.

Bài học ở đây là không tự viết nhiều lớp giải mã tùy ý, không dựa vào chuỗi chưa thống nhất để kiểm tra quyền, và cần kiểm tra hành vi từ proxy tới ứng dụng theo hợp đồng.

### 8.4. Không chuẩn hóa mọi thành phần theo cùng một quy tắc

Scheme và host có quy tắc so sánh khác với path hoặc query. Không tự chuyển toàn bộ URL sang chữ thường, xóa dấu slash cuối hoặc sắp xếp mọi query parameter rồi cho rằng ý nghĩa luôn được giữ nguyên.

Ví dụ, API có thể xử lý `/orders` và `/orders/` bằng cùng route, bằng redirect hoặc bằng hai hành vi khác nhau. Điều đó cần rõ trong hợp đồng và cấu hình.

Thông tin nhạy cảm như access token không nên đặt trong query string. HTTPS bảo vệ đường truyền nhưng không tự xóa URL khỏi log, lịch sử hoặc những nơi hệ thống đã lưu lại.

## 9. Các response giúp phân biệt lỗi đích và lỗi phương thức

Một request không thành công có thể lỗi ở những lớp khác nhau.

| Tình huống | Response có thể dùng | Điều cần hiểu |
| --- | --- | --- |
| Cú pháp request hoặc tham số không hợp lệ | 400 Bad Request | Không xử lý được đầu vào theo yêu cầu của giao thức hoặc hợp đồng |
| Resource không tồn tại hoặc không được công bố | 404 Not Found | Không nhất thiết là method sai |
| Method được server biết nhưng không được phép với resource đích | 405 Method Not Allowed | Response cần có Allow |
| Server không hỗ trợ chức năng cần để thực hiện, điển hình là không nhận diện hoặc không triển khai method | 501 Not Implemented | Khác với một method đã biết nhưng bị cấm riêng trên resource |
| Người gọi không được phép thực hiện | 403 Forbidden, hoặc 404 theo chính sách công bố | Method tồn tại không đồng nghĩa người gọi có quyền |
| Kiểu nội dung request không được hỗ trợ | 415 Unsupported Media Type | Liên quan representation gửi lên |
| Không cung cấp được representation chấp nhận được theo thương lượng | 406 Not Acceptable | Liên quan lựa chọn response |

Ví dụ resource chỉ hỗ trợ đọc:

```http
POST /orders/842 HTTP/1.1
Host: api.example.com
Content-Type: application/json

{}
```

Một phản hồi có thể là:

```http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD, OPTIONS
Content-Type: application/json

{
  "code": "METHOD_NOT_ALLOWED"
}
```

Header Allow mô tả các phương thức được hỗ trợ cho resource theo response này. Nó không cấp quyền cho người gọi và không thay thế kiểm tra bảo mật.

Trong hệ thống thực, gateway hoặc lớp bảo mật có thể xử lý request trước controller. Vì vậy, không chỉ nhìn một mã rồi kết luận chính xác tầng nào tạo ra nó; cần đối chiếu log và cấu hình.

### 9.1. Route tồn tại chưa chắc resource tồn tại

Framework có thể khớp `/orders/{orderId}` với mọi ID có dạng phù hợp. Điều đó chỉ chọn được hàm xử lý.

Nếu service không tìm thấy đơn hàng tương ứng, response vẫn có thể là 404. Cần tách:

- Không có route phù hợp.
- Có route nhưng không có resource.
- Có resource nhưng người gọi không được xem.
- Có resource nhưng method không được hỗ trợ.

### 9.2. OPTIONS không thay thế kiểm tra nghiệp vụ

Một CORS preflight minh họa:

```http
OPTIONS /orders/842 HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: DELETE
```

Trình duyệt hỏi về việc gửi một yêu cầu cross-origin. Phản hồi cho phép về CORS không có nghĩa thao tác DELETE sau đó được bỏ qua xác thực, phân quyền hoặc kiểm tra trạng thái đơn hàng.

CORS là cơ chế liên quan cách trình duyệt cho phép truy cập cross-origin; nó không phải hệ thống phân quyền resource cho mọi HTTP client.

## 10. Java/Spring ánh xạ các thành phần như thế nào?

Web server và framework xử lý cú pháp HTTP trước khi gọi controller. Ở tầng ứng dụng, các annotation giúp lấy ra những thành phần đã được phân tích.

Ví dụ controller:

```java
import java.security.Principal;
import java.util.List;
import java.util.Optional;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderQuery query;

    public OrderController(OrderQuery query) {
        this.query = query;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<List<OrderView>> list(
            @RequestParam(value = "status", required = false) String status,
            @RequestParam(value = "limit", defaultValue = "20") int limit,
            Principal principal) {

        if (limit < 1 || limit > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "limit must be between 1 and 100");
        }

        List<OrderView> orders = query.listVisibleTo(
                principal.getName(), status, limit);

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(orders);
    }

    @GetMapping(value = "/{orderId}", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<OrderView> get(
            @PathVariable("orderId") String orderId,
            Principal principal) {

        OrderView order = query
                .findVisibleTo(principal.getName(), orderId)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Order not found"));

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(order);
    }

    public record OrderView(String id, String status) {
    }

    public interface OrderQuery {
        List<OrderView> listVisibleTo(String subject, String status, int limit);

        Optional<OrderView> findVisibleTo(String subject, String orderId);
    }
}
```

Đây là đoạn minh họa trong ứng dụng Spring đã có cấu hình JSON và bảo mật yêu cầu người gọi được xác thực. Cần cung cấp bean hiện thực OrderQuery, kiểm tra quyền và xử lý lỗi theo hợp đồng.

Với request:

```text
GET /orders?status=CONFIRMED&limit=20
```

phương thức `list` nhận status và limit từ query.

Với:

```text
GET /orders/842
```

phương thức `get` nhận orderId từ path.

Những điểm cần lưu ý:

- Query parameter không tự trở thành path variable.
- Principal phải đến từ cơ chế xác thực, không lấy tùy ý từ query.
- Route khớp không có nghĩa người gọi được xem đơn hàng.
- Service phải giới hạn dữ liệu theo quyền và kiểm tra các giá trị status hợp lệ.
- Đoạn mã chỉ minh họa giới hạn số lượng, chưa công bố một hợp đồng phân trang đầy đủ hoặc xử lý mọi trường hợp tham số lặp.
- `produces` góp phần xác định kiểu response, không thay đổi resource ID.

Một controller đúng annotation vẫn có thể nằm sau một proxy viết lại path sai hoặc một cấu hình authority không đúng. Cần kiểm tra cả đường đi của request.

## 11. Đọc và kiểm tra request theo một trình tự rõ ràng

Khi gặp một request lỗi, có thể lần lượt kiểm tra:

1. **Xác định phiên bản và dạng thông điệp.** Đang xem request-line HTTP/1.1 hay bản hiển thị pseudo-header?
2. **Tách method và target.** Target có đúng dạng cho trường hợp đang dùng không?
3. **Xác định URI đích.** Scheme, authority, path và query được lấy từ đâu?
4. **Theo dõi qua proxy.** Có thay prefix, host, port hoặc scheme không?
5. **Kiểm tra mã hóa.** Đang xem chuỗi thô hay đã giải mã? Có giải mã nhiều lần không?
6. **Đối chiếu route.** Tổ hợp method và path có được hỗ trợ không?
7. **Kiểm tra resource và quyền.** Dữ liệu có tồn tại và thuộc phạm vi người gọi không?
8. **Đối chiếu representation.** Content-Type, Accept, body và điều kiện có đúng hợp đồng không?
9. **Đọc response.** Mã trạng thái, Allow, Location hoặc cấu trúc lỗi đang nói điều gì?

Các câu hỏi này giúp phân biệt lỗi đường dẫn với lỗi dữ liệu, lỗi method với lỗi quyền. Không cần đổi method hoặc sửa URL ngẫu nhiên để thử đến khi nhận 200.

Khi ghi log, nên có thông tin đủ để đối chiếu request bên ngoài với request backend, method, route và mã phản hồi. Cần tránh đưa credentials hoặc dữ liệu nhạy cảm vào log; trace ID chỉ phục vụ liên kết các bước, không phải danh tính bảo mật.

## 12. Bài tập tự kiểm tra

### Câu hỏi

1. Với URI `https://api.example.com/orders/842?view=summary#payment`, origin-form request target là gì?
2. Request target `api.example.com:443` thường thuộc method và mục đích nào?
3. `OPTIONS *` có nghĩa lấy mọi đơn hàng hay không?
4. `GET /orders/842` trên hai Host khác nhau có mặc nhiên đọc cùng resource không?
5. Client gửi POST tới `/orders` và nhận Location `/orders/842`. Target của request ban đầu là tập hợp hay đơn 842?
6. Vì sao đặt thao tác hủy vào `GET /orders/842/cancel` có vấn đề dù route chạy đúng?
7. Một resource chỉ hỗ trợ GET nhưng nhận POST. Mã 405 cần kèm header nào?
8. Route `/orders/{orderId}` khớp nhưng cơ sở dữ liệu không có ID đó. Có thể trả 404 không?
9. Muốn tìm chuỗi `Java & Spring`, vì sao không nên ghép trực tiếp thành query chưa mã hóa?
10. API trả JSON dựa trên bộ lọc trong GET body. Vì sao không nên kỳ vọng mọi cache hiểu bộ lọc đó?
11. Backend thấy HTTP và path không có prefix trong khi client gọi HTTPS có prefix. Có đủ kết luận client gửi sai không?
12. Một token hợp lệ cùng ID đơn hàng có đủ bảo đảm người gọi được đọc đơn đó không?

### Gợi ý đối chiếu

1. `/orders/842?view=summary`. Fragment không thuộc request target gửi tới server.
2. Authority-form của CONNECT thông thường để thiết lập đường hầm tới host và port.
3. Không. Đó là OPTIONS cho server nói chung, không phải wildcard đọc toàn bộ resource.
4. Không. Authority là một phần cần xét khi xác định URI đích.
5. Target ban đầu là `/orders`; Location chỉ resource mới trong phản hồi.
6. GET có ngữ nghĩa safe; công cụ tự động có thể gọi nó mà không có ý định gây thay đổi nghiệp vụ.
7. Allow, liệt kê các method mà resource hỗ trợ theo quy tắc phản hồi.
8. Có. Khớp route và tồn tại resource là hai việc khác nhau.
9. Khoảng trắng và dấu phân cách có thể làm target không hợp lệ hoặc đổi cách phân tích. Cần mã hóa giá trị theo đúng thành phần URI.
10. GET body không có ngữ nghĩa chung để thay đổi target; cache không mặc nhiên dùng body đó làm một phần phân biệt truy vấn.
11. Không. Reverse proxy có thể kết thúc TLS và viết lại path. Cần đối chiếu cấu hình cùng thông tin chuyển tiếp tin cậy.
12. Không. Server còn phải kiểm tra quyền trên resource đích.

Khi đọc một lời gọi API, hãy gọi tên phương thức, dạng target và URI đích trước khi nhìn vào hàm Java được thực thi. Cách đọc đó giúp hợp đồng và việc chẩn đoán bám vào những gì HTTP thực sự truyền tải.
