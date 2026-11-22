# Safe, idempotent và cacheable là ba thuộc tính khác nhau

Trong thiết kế REST API, chọn phương thức HTTP là chọn một hợp đồng hành vi để client, server, proxy và cache cùng hiểu. Ba thuộc tính **safe**, **idempotent** và **cacheable** trả lời ba câu hỏi khác nhau:

| Thuộc tính | Câu hỏi cần trả lời | Ý nghĩa thực tế |
| --- | --- | --- |
| Safe — an toàn về ngữ nghĩa | Client có yêu cầu làm thay đổi trạng thái hay gây tác động nghiệp vụ không? | Cho phép truy xuất, thăm dò và tải trước mà không chủ đích thực hiện một thao tác ghi. |
| Idempotent — lũy đẳng | Nếu gửi lại cùng yêu cầu, hiệu ứng được yêu cầu trên server có khác so với gửi một lần không? | Là cơ sở để cân nhắc retry khi mất kết nối hoặc không nhận được phản hồi. |
| Cacheable — có thể lưu cache | Một cache HTTP có được lưu phản hồi để dùng cho yêu cầu sau, và khi nào được dùng lại? | Giảm độ trễ, băng thông và tải xử lý trong phạm vi hợp đồng cache. |

Một yêu cầu có thể không safe nhưng vẫn idempotent. Một phương thức có thể safe mà phản hồi cụ thể lại không được lưu cache. Một thao tác POST có thể được thiết kế để chống tạo trùng mà vẫn không trở thành safe.

Bài học thuộc chương **Phương thức HTTP** của module **INTEGRATION_API_REST**. Các ví dụ sử dụng resource đơn hàng, hồ sơ và thanh toán để nối ngữ nghĩa HTTP với thiết kế URI, hợp đồng dữ liệu, mã trạng thái, kiểm thử và cách triển khai bằng Java/Spring hoặc công nghệ tương đương.

## 1. Phân biệt ba lớp khi đọc hợp đồng API

Trước khi phân tích từng thuộc tính, cần tách ba lớp:

1. **Ngữ nghĩa chuẩn của phương thức:** GET được dùng để truy xuất; PUT đặt trạng thái của resource đích; DELETE yêu cầu loại bỏ liên kết của resource với URI hiện tại.
2. **Hành vi endpoint thực tế:** code có thực hiện đúng ngữ nghĩa đó không, hay một GET lại xóa dữ liệu?
3. **Điều kiện của lần trao đổi cụ thể:** xác thực, header cache, precondition và tình trạng mạng có cho phép lưu cache, dùng lại hoặc retry không?

Client và hạ tầng thường chỉ nhìn thấy phương thức, URI, header và phản hồi. Nếu server đặt tên một endpoint là GET nhưng thực hiện chuyển tiền, server đã phá vỡ hợp đồng mà các thành phần này dựa vào. Không thể sửa sự lệch nghĩa đó chỉ bằng một dòng tài liệu “đừng gọi nhiều lần”.

## 2. Safe: client không yêu cầu tác động làm thay đổi trạng thái

### 2.1. Safe nói về ý định của yêu cầu

Một phương thức là safe khi ngữ nghĩa của nó về bản chất là đọc: client không yêu cầu và không kỳ vọng server làm thay đổi trạng thái như một phần của hành động được yêu cầu.

Ví dụ:

```http
GET /orders/ord-42 HTTP/1.1
Host: api.example.test
Accept: application/json
```

Client muốn lấy biểu diễn của đơn hàng `ord-42`. Client không yêu cầu xác nhận đơn, trừ hàng trong kho hay gửi hóa đơn.

Các phương thức được định nghĩa là safe gồm **GET, HEAD, OPTIONS và TRACE**. Đây là phân loại ngữ nghĩa, không có nghĩa một ứng dụng phải bật hoặc cung cấp tất cả các phương thức đó.

### 2.2. Safe không có nghĩa là server tuyệt đối không ghi gì

Một GET vẫn có thể khiến server:

- Ghi access log hoặc số liệu theo dõi vận hành.
- Cập nhật bộ nhớ đệm nội bộ.
- Thu thập thống kê phục vụ quan sát hệ thống.

Những hoạt động phụ do server quản lý không tự biến GET thành phương thức ghi. Điểm phân biệt là **tác động nào thuộc hành vi mà client yêu cầu**. Nếu hành vi được yêu cầu là tăng lượt bình chọn, đánh dấu đã đọc có ảnh hưởng nghiệp vụ, tiêu tiền hoặc cập nhật đơn hàng, hãy mô hình hóa nó bằng phương thức thích hợp cho thao tác ghi.

“Safe” cũng không đồng nghĩa với “bảo mật”. GET vẫn cần xác thực và phân quyền khi truy xuất dữ liệu riêng tư; vẫn có thể làm lộ thông tin nếu thiết kế URI hoặc cache sai.

### 2.3. Vì sao không được dùng GET để thực hiện hành động ghi?

Thiết kế sau vi phạm ngữ nghĩa safe:

```http
GET /orders/ord-42?operation=cancel HTTP/1.1
```

Query parameter không biến GET thành một phương thức có ngữ nghĩa khác. Trình duyệt, crawler, công cụ kiểm tra liên kết hoặc cơ chế tải trước có thể truy cập URL mà không có ý định hủy đơn.

Nếu việc hủy đơn là một chuyển trạng thái nghiệp vụ có kiểm tra điều kiện và tạo dấu vết riêng, một cách mô hình hóa là:

```http
POST /orders/ord-42/cancellations HTTP/1.1
Content-Type: application/json

{"reason":"customer_request"}
```

Việc dùng POST ở đây chưa quyết định khả năng retry hay chống hủy trùng. Các hành vi đó vẫn cần được định nghĩa trong hợp đồng endpoint. Nếu chọn một mô hình resource khác, có thể chọn phương thức khác phù hợp; điều bắt buộc là không giao tác động ghi cho GET.

## 3. Idempotent: lặp lại không nhân thêm hiệu ứng được yêu cầu

### 3.1. Định nghĩa qua hiệu ứng trên trạng thái

Một phương thức là idempotent nếu hiệu ứng dự định trên server của nhiều yêu cầu giống nhau tương đương với hiệu ứng của một yêu cầu như vậy.

Có thể hình dung một phép đặt giá trị:

```text
đặt email = "new@example.test"
đặt email = "new@example.test"
đặt email = "new@example.test"

Hiệu ứng được yêu cầu: email có giá trị "new@example.test".
```

Ngược lại, phép cộng dồn thường không idempotent:

```text
tăng số dư thêm 100
tăng số dư thêm 100
tăng số dư thêm 100

Hiệu ứng: số dư tăng tổng cộng 300, thay vì 100.
```

So sánh này xét hiệu ứng của chính thao tác được lặp lại. Nó không khẳng định resource không thể bị những client khác sửa trong khoảng thời gian đó.

Theo ngữ nghĩa HTTP, **các phương thức safe, PUT và DELETE là idempotent**. POST và PATCH không có bảo đảm idempotent chung cho mọi endpoint.

### 3.2. PUT: đặt trạng thái của resource tại URI đã biết

Giả sử hợp đồng định nghĩa PUT là thay thế tập thuộc tính do client quản lý của hồ sơ:

```http
PUT /profiles/u-17 HTTP/1.1
Content-Type: application/json

{"displayName":"An","email":"an@example.test"}
```

Gửi cùng yêu cầu hai lần vẫn yêu cầu hồ sơ có cùng các giá trị đó. Server có thể quản lý riêng ID, thời điểm cập nhật hoặc thông tin kiểm toán; hợp đồng cần nói rõ field nào do client kiểm soát và field nào chỉ đọc.

Nếu mỗi lần gọi endpoint này lại tạo một hồ sơ mới tại URI khác hoặc cộng thêm điểm thưởng như một hiệu ứng nghiệp vụ của việc “đặt hồ sơ”, triển khai đó không đáp ứng ngữ nghĩa idempotent mong đợi của PUT.

PUT cũng không mặc nhiên có nghĩa “chỉ sửa các field xuất hiện”. Một hợp đồng cập nhật một phần thường phù hợp với PATCH hơn. Cần mô tả rõ cách xử lý field thiếu để client không mất dữ liệu do hiểu sai phép thay thế.

### 3.3. DELETE: mã trạng thái khác nhau vẫn có thể idempotent

Xét chuỗi yêu cầu không có client nào tạo lại resource ở giữa:

```text
DELETE /drafts/d-8  → 204 No Content
DELETE /drafts/d-8  → 404 Not Found
DELETE /drafts/d-8  → 404 Not Found
```

Hiệu ứng được yêu cầu vẫn là resource không còn được cung cấp tại URI đó. Lần hai có thể báo không tìm thấy vì lần đầu đã xử lý thành công.

Một API cũng có thể quy định DELETE lên resource đã vắng mặt tiếp tục trả `204`. Cả hai chính sách đều có thể phù hợp; điều quan trọng là hợp đồng rõ ràng và client không đồng nhất “cùng hiệu ứng” với “cùng phản hồi”.

DELETE không bắt buộc phải xóa vật lý ngay mọi bản ghi và bản sao lưu. Nếu hệ thống giữ bản ghi kiểm toán hoặc dùng soft delete, vẫn phải bảo đảm hành vi quan sát được của resource phù hợp với hợp đồng đã công bố.

### 3.4. Idempotent không yêu cầu response giống hệt

Các yếu tố sau có thể khác giữa những lần gọi mà không tự làm mất tính idempotent:

- Mã trạng thái, chẳng hạn PUT lần đầu tạo resource trả `201`, lần sau cập nhật trả `200` hoặc `204`.
- Header thời gian, mã theo dõi và thông tin quan sát.
- Nội dung biểu diễn phụ thuộc vào trạng thái server tại thời điểm phản hồi.

Server cũng có thể ghi log cho từng lần nhận yêu cầu. Tuy nhiên, không nên dùng lý do “log được phép lặp” để nhân thêm một tác động nghiệp vụ như thu tiền hoặc gửi một yêu cầu xuất hàng mới sau mỗi lần retry.

### 3.5. PATCH phụ thuộc vào phép biến đổi cụ thể

Hai dạng cập nhật một phần có thể có hành vi khác nhau:

| Phép cập nhật | Khi áp dụng lại cùng thao tác | Nhận xét |
| --- | --- | --- |
| Đặt `displayName` thành `"An"` | Vẫn đặt cùng một giá trị | Có thể thiết kế idempotent. |
| Tăng `quantity` thêm `1` | Tiếp tục tăng | Không idempotent. |
| Thêm một phần tử vào cuối danh sách | Có thể tiếp tục thêm phần tử trùng | Thường không idempotent nếu không có cơ chế chống trùng. |

Chỉ nhìn chữ PATCH không đủ để kết luận rằng retry là an toàn. Cần đọc media type của tài liệu patch, các phép biến đổi và hợp đồng endpoint. Tương tự, một POST có thể được ứng dụng thiết kế idempotent, nhưng đó là bảo đảm cụ thể của ứng dụng, không phải mặc định của POST.

## 4. Cacheable: phản hồi có thể được lưu và tái sử dụng theo điều kiện

### 4.1. Phải tách “lưu được” và “dùng lại được ngay”

Cache HTTP có thể lưu một phản hồi rồi dùng nó để đáp ứng yêu cầu sau. Quyết định này phụ thuộc vào phương thức, mã trạng thái, header, loại cache và yêu cầu tiếp theo.

Hai câu hỏi cần hỏi riêng là:

1. Cache có được lưu phản hồi này không?
2. Nếu đã lưu, cache có được dùng lại ngay không, hay phải xác thực lại với server?

GET và HEAD có hỗ trợ cache theo ngữ nghĩa HTTP, nhưng không có nghĩa mọi phản hồi GET đều được lưu hoặc luôn có thể dùng lại. HEAD không có nội dung phản hồi như GET; cache có thể sử dụng metadata từ HEAD theo các quy tắc tương ứng.

Ví dụ một biểu diễn công khai có thể cho phép cache dùng lại trong khoảng thời gian ngắn:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=60
ETag: "catalog-v12"

{"items":[{"id":"p-1","name":"Notebook"}]}
```

`max-age=60` xác định thời gian freshness tính theo tuổi của phản hồi, không đơn giản là 60 giây kể từ mỗi lần cache nhận được một bản sao. Khi đáp ứng đúng điều kiện, cache có thể phục vụ biểu diễn còn fresh mà không gọi lại origin server.

### 4.2. Ba chỉ thị hay bị nhầm

| Header phản hồi | Ý nghĩa chính | Ví dụ sử dụng |
| --- | --- | --- |
| `Cache-Control: no-store` | Cache không được lưu phản hồi này. | Phản hồi chứa thông tin mà ứng dụng không muốn lưu trong cache HTTP. |
| `Cache-Control: no-cache` | Có thể lưu, nhưng phải xác thực lại thành công trước khi dùng để đáp ứng yêu cầu sau. | Muốn tận dụng validator để tiết kiệm nội dung truyền nhưng cần kiểm tra với server. |
| `Cache-Control: private, max-age=60` | Cho phép cache riêng lưu và dùng theo freshness; shared cache không được lưu phản hồi. | Dữ liệu cá nhân khi chính sách sản phẩm cho phép cache tại phía người dùng. |

`no-cache` không đồng nghĩa với `no-store`. `private` không phải cơ chế mã hóa hay phân quyền. Với dữ liệu nhạy cảm, phải chọn chính sách phù hợp cho từng endpoint và vẫn thực thi xác thực, phân quyền tại server.

### 4.3. ETag và conditional GET

Client đã có biểu diễn với ETag `"catalog-v12"` có thể kiểm tra lại:

```http
GET /products HTTP/1.1
Host: api.example.test
If-None-Match: "catalog-v12"
```

Nếu biểu diễn vẫn phù hợp với validator, server có thể trả:

```http
HTTP/1.1 304 Not Modified
ETag: "catalog-v12"
Cache-Control: public, max-age=60
```

Phản hồi `304` không gửi lại nội dung biểu diễn. Client/cache dùng bản đã lưu và cập nhật metadata theo quy tắc HTTP. Đây là tiết kiệm băng thông khi xác thực lại, khác với trường hợp cache còn fresh và tự phục vụ mà không liên hệ server.

### 4.4. Cache key và biến thể biểu diễn

Cache cần phân biệt đúng đối tượng được lưu. Phương thức và URI đích là cơ sở của cache key; URI bao gồm query string. Khi biểu diễn thay đổi theo một request header, server cần mô tả sự phân biệt thích hợp bằng `Vary`.

Ví dụ:

```http
GET /products?page=1&size=20 HTTP/1.1
Accept-Language: vi
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=60
Vary: Accept-Language
```

Hai trang khác nhau cần được phân biệt theo URI; hai ngôn ngữ khác nhau tại cùng URI cần được phân biệt theo `Accept-Language` như đã khai báo. Không được gom mọi trang hoặc mọi ngôn ngữ vào cùng một bản cache.

Dữ liệu phụ thuộc người dùng còn có các ràng buộc về xác thực và shared cache. Không dùng `public` cho phản hồi cá nhân chỉ vì endpoint là GET. Dùng `Vary` cũng không thay thế kiểm tra quyền truy cập hoặc tự giải quyết mọi vấn đề cách ly dữ liệu giữa người dùng.

### 4.5. POST và PATCH có thể có phản hồi cacheable trong điều kiện cụ thể

Nói “HTTP chỉ cho phép cache GET” là quá tuyệt đối:

- **POST:** ngữ nghĩa HTTP cho phép cache phản hồi khi có thông tin freshness tường minh và `Content-Location` bằng URI đích của POST. Phản hồi đó có thể dùng cho GET hoặc HEAD thích hợp về sau; nó không cho phép cache bỏ qua một POST mới chỉ vì đã thấy POST giống trước đó.
- **PATCH:** định nghĩa PATCH cũng cho phép cache phản hồi trong điều kiện có freshness tường minh và `Content-Location` khớp URI đích, với nội dung là biểu diễn của resource đó. Bản lưu có thể phục vụ GET/HEAD phù hợp, không phục vụ thay cho một PATCH mới.

Khả năng hỗ trợ thực tế của thư viện, proxy và CDN cho các trường hợp này không đồng đều. Khi muốn cache kết quả một truy vấn phức tạp được gửi qua POST, một lựa chọn thiết kế là tạo resource kết quả có URI riêng để client truy xuất bằng GET. Cần xác định rõ thời hạn, quyền truy cập và hợp đồng dữ liệu của resource đó.

Phản hồi PUT và DELETE không cacheable theo định nghĩa của các phương thức này. Việc một thao tác ghi làm cache cũ cần bị vô hiệu hóa là một vấn đề khác với việc lưu chính phản hồi của thao tác ghi.

## 5. Bảng đối chiếu các phương thức

| Phương thức | Safe theo định nghĩa | Idempotent theo định nghĩa | Khả năng cache phản hồi theo ngữ nghĩa HTTP |
| --- | --- | --- | --- |
| GET | Có | Có | Có; vẫn phụ thuộc mã trạng thái, header và quy tắc cache. |
| HEAD | Có | Có | Có; phản hồi không có nội dung, metadata có vai trò trong cache. |
| OPTIONS | Có | Có | Phản hồi không cacheable. |
| TRACE | Có | Có | Phản hồi không cacheable. |
| PUT | Không | Có | Phản hồi không cacheable. |
| DELETE | Không | Có | Phản hồi không cacheable. |
| POST | Không | Không được bảo đảm chung | Có điều kiện như đã mô tả; hỗ trợ thực tế hạn chế. |
| PATCH | Không | Không được bảo đảm chung | Có điều kiện theo định nghĩa PATCH; hỗ trợ thực tế hạn chế. |

Bảng mô tả hợp đồng chuẩn, không bảo đảm rằng code của mọi server đều đúng. Một endpoint GET xóa dữ liệu là lỗi thiết kế; không nên coi đó là một ngoại lệ hợp lệ cho safe GET.

Quan hệ cần nhớ:

- **Safe suy ra idempotent theo phân loại phương thức HTTP.**
- **Idempotent không suy ra safe:** PUT và DELETE yêu cầu thay đổi trạng thái.
- **Safe hoặc idempotent không quyết định khả năng cache của phản hồi.**
- **Cacheable không có nghĩa là yêu cầu không được gửi đến server nữa trong mọi hoàn cảnh.** Cache vẫn phải xét freshness, validator, phạm vi sử dụng và yêu cầu tiếp theo.

## 6. Retry: idempotent xử lý sự không chắc chắn của mạng

### 6.1. Timeout không cho biết thao tác đã thất bại

Xét một lần cập nhật bị mất phản hồi:

```text
Client                  Server
  | PUT /profiles/u-17     |
  |----------------------->|
  |                        | lưu dữ liệu thành công
  |       mất kết nối      |
  |<----------- X ---------|
  | timeout                |
```

Client không biết server chưa nhận được yêu cầu, đang xử lý hay đã hoàn tất. Với thao tác idempotent, gửi lại cùng yêu cầu có cùng hiệu ứng dự định như đã gửi một lần. Đây là lý do idempotence hữu ích khi kết nối đứt trước khi client nhận được phản hồi.

Tuy vậy, **idempotent không có nghĩa là retry mọi lỗi một cách vô hạn**. Chính sách retry vẫn phải xét loại lỗi, deadline, số lần thử, khoảng chờ và chỉ dẫn từ server. Lỗi dữ liệu đầu vào hoặc thiếu quyền thường cần sửa nguyên nhân thay vì gửi lại y nguyên. Nhiều client retry đồng loạt cũng có thể làm server quá tải dù thao tác hoàn toàn idempotent.

### 6.2. Idempotence không giải quyết lost update

Hai client cùng đọc một hồ sơ rồi lần lượt PUT hai phiên bản khác nhau có thể ghi đè thay đổi của nhau. Mỗi PUT vẫn idempotent, nhưng hệ thống thiếu kiểm soát đồng thời.

Một hợp đồng có thể sử dụng ETag và `If-Match`:

```http
PUT /profiles/u-17 HTTP/1.1
Content-Type: application/json
If-Match: "profile-v7"

{"displayName":"An Nguyen","email":"an@example.test"}
```

Nếu phiên bản hiện tại không còn khớp, server trả `412 Precondition Failed` thay vì ghi đè mù quáng.

Cần phân biệt validator ở hai mục đích:

| Cơ chế | Mục đích chính trong ví dụ |
| --- | --- |
| `If-None-Match` trong GET | Kiểm tra bản đã lưu còn dùng được không; có thể nhận `304`. |
| `If-Match` trong PUT | Chỉ ghi nếu resource vẫn đúng phiên bản đã đọc; nếu không thì `412`. |

Nếu lần PUT đầu đã thành công nhưng phản hồi bị mất, gửi lại cùng `If-Match` cũ có thể nhận `412` vì phiên bản đã đổi. Điều đó không làm PUT mất tính idempotent: lần retry không tạo thêm hiệu ứng ghi. Client cần đọc lại và đối chiếu trạng thái, hoặc dùng cơ chế theo dõi thao tác nếu cần biết chính xác kết quả của lần yêu cầu trước.

### 6.3. POST tạo thanh toán cần hợp đồng chống tạo trùng riêng

Một yêu cầu tạo thanh toán có thể không idempotent:

```http
POST /payments HTTP/1.1
Content-Type: application/json

{"orderId":"ord-42","amount":250000,"currency":"VND"}
```

Nếu server tạo một payment mới mỗi lần nhận, retry sau timeout có thể tạo nhiều payment. Một lựa chọn của ứng dụng là bổ sung khóa chống trùng:

```http
POST /payments HTTP/1.1
Content-Type: application/json
Idempotency-Key: checkout-ord-42-attempt-1

{"orderId":"ord-42","amount":250000,"currency":"VND"}
```

Trong ví dụ này, `Idempotency-Key` là một phần của hợp đồng API cần được tài liệu hóa. Chỉ gửi header không tự tạo ra tính idempotent; server phải triển khai cơ chế tương ứng:

1. Xác thực và phân quyền trước khi truy xuất kết quả được lưu cho một khóa.
2. Phân vùng khóa theo chủ thể/tenant và loại thao tác để tránh va chạm giữa các ngữ cảnh.
3. Ghi nhận khóa, dấu vân tay của yêu cầu và trạng thái xử lý một cách nguyên tử hoặc bằng cơ chế điều phối tương đương.
4. Với cùng khóa và cùng dữ liệu, trả kết quả đã có hoặc trạng thái đang xử lý theo hợp đồng; không tạo thêm payment.
5. Với cùng khóa nhưng dữ liệu khác, từ chối theo mã lỗi đã công bố, chẳng hạn `409 Conflict`.
6. Công bố thời hạn giữ khóa và hành vi sau khi khóa hết hạn. Client giữ nguyên khóa khi retry cùng thao tác; thao tác nghiệp vụ mới dùng khóa mới.

Hai yêu cầu cùng khóa có thể đến đồng thời. Cách làm “kiểm tra chưa có rồi insert” không có ràng buộc nguyên tử có thể cho cả hai chạy. Đồng thời, nếu gọi cổng thanh toán bên ngoài, việc chống trùng trong cơ sở dữ liệu cục bộ chưa đủ để chống thu tiền trùng sau một sự cố giữa chừng; cần phối hợp khóa phía nhà cung cấp hoặc quy trình phục hồi phù hợp.

Đây là chống lặp tác động nghiệp vụ, không phải cache HTTP. Việc ghi nhớ một kết quả theo khóa không làm POST trở thành safe, và cũng không bảo đảm mọi tác động phân tán chỉ xảy ra đúng một lần.

## 7. Cache sau thao tác ghi: ba thuộc tính vẫn độc lập

Giả sử các phản hồi sau đang được cache:

```text
GET /products/p-1
GET /products?page=1&size=20
GET /categories/c-2/products
```

Sau khi cập nhật giá bằng `PUT /products/p-1`, những biểu diễn liên quan có thể đã cũ. Cache HTTP có quy tắc vô hiệu hóa URI đích sau một phản hồi thành công cho phương thức unsafe mà nó quan sát được. Nhưng cache không tự suy ra toàn bộ quan hệ nghiệp vụ giữa sản phẩm, trang danh sách và danh mục; các cache khác cũng có thể không nhìn thấy thao tác ghi.

Do đó, thiết kế cần quyết định độ cũ chấp nhận được, TTL, validator và cách vô hiệu hóa các biểu diễn liên quan. Một PUT idempotent vẫn có thể đi cùng một GET danh sách trả dữ liệu cũ trong thời gian cache còn hiệu lực.

Không dùng một kết quả cache cũ để kết luận thao tác ghi chưa xảy ra. Cũng không vô hiệu hóa cache bằng một GET có tác động nghiệp vụ chỉ để giữ giao diện đồng bộ; hãy giữ đúng ngữ nghĩa phương thức và chọn cơ chế cập nhật cache riêng.

## 8. Đưa các thuộc tính vào hợp đồng và kiểm thử

Khi triển khai bằng Java/Spring, việc ánh xạ một handler vào GET hay PUT chỉ công bố phương thức HTTP. Tính đúng đắn còn phụ thuộc vào service, giao dịch dữ liệu, tác động ra hệ thống ngoài và cấu hình cache. Có thể mô tả các cam kết này trong tài liệu endpoint hoặc OpenAPI cùng ví dụ header và mã lỗi.

Một hợp đồng nên trả lời được:

- Yêu cầu đọc hay thay đổi resource nào? Field nào được thay thế, giữ nguyên hoặc do server quản lý?
- Gửi lại cùng yêu cầu có tạo thêm resource hoặc tác động nghiệp vụ không?
- Có cần khóa chống trùng, validator hoặc precondition không? Khóa có phạm vi và thời hạn gì?
- Phản hồi có được cache riêng/shared cache lưu không? Freshness và biến thể được xác định thế nào?
- Những phản hồi nào có thể khác nhau giữa lần đầu và lần lặp lại?

Các tình huống kiểm thử hành vi hữu ích:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Gọi GET đơn hàng nhiều lần | Không chuyển trạng thái đơn, không tạo thanh toán hoặc tác động ghi mà client không yêu cầu. |
| Gửi PUT cùng URI và cùng dữ liệu hai lần | Trạng thái nghiệp vụ cuối tương đương gửi một lần; không phát sinh bản ghi nghiệp vụ trùng. |
| Gửi DELETE hai lần | Resource vẫn vắng mặt; mã trạng thái lần hai theo đúng hợp đồng. |
| Gửi lại PATCH tăng số lượng | Số lượng có thể tăng tiếp; client không giả định retry được nếu thiếu bảo đảm bổ sung. |
| Gửi đồng thời hai POST thanh toán cùng khóa | Chỉ một thao tác thanh toán logic được tạo; yêu cầu còn lại được xử lý theo hợp đồng. |
| Dùng lại khóa với payload khác | Bị từ chối theo chính sách, không trả nhầm kết quả của dữ liệu cũ. |
| GET với `If-None-Match` khớp | Nhận `304` không có nội dung biểu diễn và có thể tái sử dụng bản đã lưu. |
| PUT với `If-Match` cũ | Không ghi đè dữ liệu mới; nhận `412` theo hợp đồng. |
| Truy xuất hồ sơ riêng qua shared cache | Phản hồi và cấu hình không cho phép lộ dữ liệu sang người dùng khác. |
| Lấy hai trang hoặc hai ngôn ngữ | Cache phân biệt đúng URI và biến thể, không phục vụ nhầm biểu diễn. |

Với bài kiểm thử idempotence, hãy so sánh **hiệu ứng nghiệp vụ** bên cạnh response: số payment, trạng thái resource, lượng tồn kho hoặc số yêu cầu gửi sang dịch vụ ngoài. Chỉ so sánh JSON trả về có thể bỏ sót tác động bị lặp.

## 9. Những kết luận sai cần tránh

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Safe là không cần xác thực.” | Safe nói về tác động được yêu cầu; quyền đọc vẫn phải được kiểm tra. |
| “Idempotent là gọi bao nhiêu lần cũng trả cùng JSON.” | Thuộc tính này xét hiệu ứng dự định trên server, không đòi response giống hệt. |
| “DELETE lần hai trả 404 nên không idempotent.” | Resource tiếp tục vắng mặt; hiệu ứng không bị nhân thêm. |
| “PUT luôn chống mất cập nhật.” | Cần precondition hoặc cơ chế kiểm soát đồng thời để xử lý các client ghi đè nhau. |
| “PATCH luôn không idempotent.” | PATCH không được bảo đảm chung; phép đặt giá trị có thể được thiết kế idempotent. |
| “GET luôn được cache.” | Phản hồi còn phải thỏa quy tắc cache; `no-store` có thể cấm lưu. |
| “`no-cache` cấm lưu phản hồi.” | Nó buộc xác thực lại trước khi dùng cho yêu cầu sau. |
| “Có idempotency key là có HTTP cache.” | Đây là hợp đồng chống trùng của ứng dụng; cache HTTP có ngữ nghĩa riêng. |
| “POST được cache nghĩa là có thể bỏ qua POST tiếp theo.” | Các điều kiện cache POST không cho phép dùng bản lưu để tự thay thế một POST mới. |

## 10. Bài tập tự kiểm tra

### Tình huống A: link hủy đăng ký

API cung cấp `GET /subscriptions/s-3?cancel=true` và ngay lập tức hủy đăng ký. Yêu cầu này có safe không?

**Gợi ý trả lời:** Triển khai đã vi phạm ngữ nghĩa safe của GET. Cần mô hình hóa hành động ghi bằng endpoint/phương thức phù hợp. Một trang xác nhận có thể được mở bằng GET, còn thao tác hủy phải được gửi riêng theo hợp đồng có kiểm tra quyền.

### Tình huống B: đặt giá sản phẩm

Client gửi hai lần cùng `PUT /products/p-1` với cùng biểu diễn giá. Lần đầu trả `200`, lần sau trả `204`. Có thể kết luận endpoint không idempotent không?

**Gợi ý trả lời:** Không. Cần kiểm tra hiệu ứng dự định trên resource và các tác động nghiệp vụ liên quan. Mã trạng thái khác nhau không đủ để kết luận.

### Tình huống C: hồ sơ cá nhân có `no-store`

`GET /me` trả `Cache-Control: no-store`. Ba thuộc tính nên được hiểu thế nào?

**Gợi ý trả lời:** GET có ngữ nghĩa safe và idempotent. Phản hồi cụ thể bị cấm lưu trong cache HTTP bởi `no-store`; không thể suy từ phương thức GET rằng phản hồi được cache.

### Tình huống D: timeout khi tạo payment

Client chưa nhận phản hồi từ POST thanh toán và tự sinh khóa mới để retry. Thiết kế đó đã chống trùng chưa?

**Gợi ý trả lời:** Chưa. Khóa mới có thể được server hiểu là thao tác mới. Retry cùng thao tác phải giữ khóa và dữ liệu tương ứng trong phạm vi thời hạn đã cam kết, đồng thời server phải thực hiện chống trùng đúng cách.

Khi đánh giá một endpoint REST, hãy luôn đặt riêng ba câu hỏi: **client yêu cầu tác động gì, lặp lại tác động đó có nhân thêm hiệu ứng không, và phản hồi được phép tái sử dụng theo những điều kiện nào?** Trả lời từng câu bằng hợp đồng cụ thể sẽ giúp chọn đúng phương thức, viết chính sách retry và cấu hình cache nhất quán.
