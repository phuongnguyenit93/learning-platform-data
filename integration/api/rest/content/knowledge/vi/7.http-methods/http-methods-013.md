# Nội dung trong GET, HEAD, DELETE và giới hạn liên thông

Khi thiết kế REST API, một câu hỏi thường gây tranh luận là: **GET, HEAD hoặc DELETE có được mang request body không?** Người học có thể thấy một HTTP client gửi JSON kèm GET, một controller Spring đọc được dữ liệu, nhưng trình duyệt hoặc API gateway lại từ chối. Một số nhóm từ đó kết luận “HTTP cấm body trong GET”; nhóm khác lại kết luận “chạy trên máy tôi thì cứ dùng”. Cả hai cách hiểu đều thiếu phần quan trọng nhất: **khả năng truyền nội dung trên dây khác với ngữ nghĩa mà HTTP chuẩn hóa và các thành phần trung gian có thể hiểu thống nhất**.

Bài học thuộc phần **Phương thức HTTP** của module INTEGRATION_API_REST, tập trung vào hợp đồng REST dựa trên resource, URI, method và status code. Qua các ví dụ Java/Spring và HTTP thuần, bạn sẽ biết khi nào nên sử dụng query parameter, header điều kiện, POST tạo tài nguyên tác vụ, và cách kiểm thử đường đi thực tế qua client, proxy, WAF, cache và origin server.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **request content** là gì và phân biệt nó với **response content**.
2. Mô tả chính xác vị trí ngữ nghĩa request body của **GET, HEAD, DELETE** theo HTTP Semantics (RFC 9110), không đánh đồng “có thể gửi byte” với “có ý nghĩa chuẩn”.
3. Thiết kế API tra cứu, kiểm tra metadata, xóa resource và xóa hàng loạt với URI, phương thức, điều kiện và mã phản hồi phù hợp.
4. Nhận diện rủi ro liên thông tại browser Fetch API, proxy, cache/CDN, gateway, WAF, client generator và controller Java/Spring.
5. Viết hợp đồng OpenAPI, triển khai và kiểm thử để tránh phụ thuộc vào request body không có ngữ nghĩa chung.

## 2. Phân biệt message framing, request content và response content

Một HTTP request được mô tả bằng **method, target URI, header fields và phần content tùy chọn**. Cách truyền content phụ thuộc phiên bản giao thức: HTTP/1.1 có cơ chế đóng khung message; HTTP/2 và HTTP/3 truyền dữ liệu qua frame. Việc có hoặc không có byte trong phần content **không tự làm thay đổi ý nghĩa chuẩn** của method.

Xem hai thông điệp minh họa:

~~~http
GET /v1/products?category=camera HTTP/1.1
Host: api.example.test
Accept: application/json

~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=60

{"items":[{"id":"p-1","name":"Camera A"}]}
~~~

Thông điệp thứ nhất là **request GET không có content**; JSON ở thông điệp thứ hai là **response content**. Điều GET thường nhận JSON **không có nghĩa** GET cần JSON trong request.

HTTP/1.1 vẫn có thể đóng khung một request GET chứa bytes:

~~~http
GET /v1/products HTTP/1.1
Host: api.example.test
Content-Type: application/json
Content-Length: 21

{"category":"camera"}
~~~

Thông điệp trên được đưa ra **để phân tích vấn đề liên thông**, không phải đề xuất API. Một số server có thể đọc được 21 byte đó. Tuy nhiên, **GET request content không có ngữ nghĩa chung được HTTP định nghĩa**, và không thể dựa vào nó để thay đổi ý nghĩa hay đối tượng của request theo một hợp đồng HTTP phổ quát.

### 2.1. “Có thể truyền” khác “nên thiết kế”

Ba tầng cần tách bạch:

| Tầng | Câu hỏi | Điều có thể xảy ra |
|---|---|---|
| **Định dạng truyền (wire framing)** | Có byte content trong message không? | Có thể có, tùy client và giao thức |
| **HTTP semantics** | Method quy định content đó có ý nghĩa chuẩn nào? | GET, HEAD, DELETE không định nghĩa ý nghĩa chung cho request content |
| **Ứng dụng và trung gian** | Client, proxy, cache, framework có chuyển tiếp và hiểu nội dung thống nhất không? | Có thể hỗ trợ, bỏ qua, chặn, từ chối hoặc xử lý khác nhau |

**Header Content-Type** chỉ mô tả kiểu dữ liệu content nếu có; nó không tự biến JSON trong GET thành bộ lọc được HTTP chuẩn hóa. **Content-Length** mô tả framing, không quy định request đó nên mang ý nghĩa nào. Ngược lại, không có body cũng không làm GET/HEAD/DELETE “thiếu dữ liệu bắt buộc” chỉ vì ứng dụng có thể nhận tham số.

## 3. Quy tắc của GET, HEAD và DELETE

### 3.1. GET: lấy biểu diễn của tài nguyên

GET yêu cầu chuyển biểu diễn hiện hành của **target resource**. GET là phương thức **safe** (khách không yêu cầu thay đổi trạng thái ứng dụng) và **idempotent** theo ý nghĩa chuẩn. Nó cũng là phương thức chủ chốt của HTTP caching.

Theo HTTP Semantics, **request content trong GET không có ngữ nghĩa chung được định nghĩa**. Việc gửi content có thể khiến một số implementation từ chối request hoặc đóng kết nối vì lo ngại request smuggling. Client **SHOULD NOT** tạo content trong GET trừ trường hợp giao tiếp trực tiếp với origin server đã chủ động cho biết mục đích và khả năng hỗ trợ; origin server cũng **SHOULD NOT** dựa vào thỏa thuận riêng như vậy, vì các trung gian trên đường truyền có thể không biết.

Chữ **SHOULD NOT** là khuyến nghị chuẩn mạnh nhưng khác với **MUST NOT** (cấm theo yêu cầu chuẩn). Vì vậy, phát biểu đúng là:

> HTTP không cấm tuyệt đối mọi GET request có content, nhưng không định nghĩa ý nghĩa chung cho content đó và không bảo đảm nó liên thông qua các thành phần HTTP.

API lọc sản phẩm nên biểu diễn điều kiện tra cứu qua **query parameter**:

~~~http
GET /v1/products?category=camera&brand=acme&page=0&size=20 HTTP/1.1
Host: api.example.test
Accept: application/json
~~~

Ưu điểm: URI có thể bookmark, kiểm tra trong log/tracing đã che dữ liệu nhạy cảm, tương thích client và có khả năng cache phù hợp. Nhưng **query parameter không nên chứa secret, access token hay dữ liệu nhạy cảm** vì URI có thể xuất hiện trong history, log, referrer hoặc hệ thống giám sát.

### 3.2. HEAD: lấy metadata của biểu diễn GET

HEAD giống GET về ngữ nghĩa chọn tài nguyên, **ngoại trừ server không gửi response content**. HEAD hữu ích khi cần biết resource có tồn tại không, ETag, Last-Modified hoặc các metadata liên quan đến biểu diễn mà không nhận toàn bộ dữ liệu.

~~~http
HEAD /v1/products/p-1 HTTP/1.1
Host: api.example.test

HTTP/1.1 200 OK
ETag: "product-42"
Last-Modified: Wed, 18 Nov 2026 08:00:00 GMT
Cache-Control: public, max-age=60
Content-Type: application/json

~~~

Phần phản hồi được minh họa **không có body**. Server nên gửi các header giống GET tương ứng, ngoại trừ một số header có thể chỉ xác định khi tạo nội dung; nếu gửi **Content-Length** trên HEAD, giá trị phải phản ánh kích thước nội dung của phản hồi GET tương ứng (không phải số byte response HEAD thực sự gửi).

**HEAD request content** cũng không có ngữ nghĩa chung, tương tự GET. Dù một số client cho truyền body, không nên xây dựng API “HEAD kèm JSON để tìm metadata của bộ lọc”. Trên nền tảng Spring MVC, mapping GET thông thường đã hỗ trợ HEAD theo cơ chế của framework; khi phản hồi GET đòi hỏi tạo dữ liệu lớn, cần đo và cân nhắc tối ưu metadata cho HEAD thay vì mặc định rằng HEAD luôn rẻ.

### 3.3. DELETE: yêu cầu loại bỏ liên kết của target resource

DELETE yêu cầu server xóa liên kết giữa target resource với chức năng hiện tại của nó. Việc thực thi có thể là xóa vật lý, xóa mềm, đánh dấu ngừng hoạt động hoặc đưa vào tác vụ bất đồng bộ, tùy hợp đồng hệ thống. **DELETE là idempotent nhưng không safe**: nó yêu cầu thay đổi trạng thái.

~~~http
DELETE /v1/carts/cart-42/items/item-7 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>

~~~

Các response thông dụng:

| Status | Khi nào phù hợp | Response content |
|---|---|---|
| **204 No Content** | Thao tác xóa hoàn tất, không cần trả nội dung | Không được gửi response content |
| **200 OK** | Xóa hoàn tất và muốn trả mô tả trạng thái/kết quả | Có thể có nội dung JSON phù hợp |
| **202 Accepted** | Yêu cầu đã được chấp nhận, thao tác sẽ xử lý sau | Có thể trả thông tin theo dõi tác vụ |
| **404 Not Found** | Resource không tồn tại/không được tiết lộ là tồn tại | Tùy hợp đồng lỗi |
| **410 Gone** | Server biết resource đã bị loại bỏ và muốn công khai điều đó | Tùy hợp đồng lỗi |
| **409 Conflict** | Trạng thái hiện tại khiến không thể xóa theo quy tắc nghiệp vụ | Nêu xung đột nếu được phép |
| **412 Precondition Failed** | Điều kiện If-Match không còn đúng | Nêu trạng thái lỗi nếu phù hợp |

Tương tự GET và HEAD, **request content trong DELETE không có ngữ nghĩa chung được HTTP định nghĩa**; client không nên dựa vào body theo một hợp đồng riêng mà qua nhiều trung gian có thể bị từ chối hoặc diễn giải khác nhau. Tránh thiết kế kiểu **DELETE /v1/items** với JSON danh sách ID trong body làm nguồn duy nhất xác định tài nguyên cần xóa.

### 3.4. Bảng so sánh cần nhớ

| Thuộc tính | GET | HEAD | DELETE |
|---|---|---|---|
| Ý nghĩa chuẩn | Lấy biểu diễn resource | Lấy metadata của GET tương ứng, không có response content | Yêu cầu loại bỏ liên kết resource tại target URI |
| Safe | Có | Có | Không |
| Idempotent | Có | Có | Có |
| Response content | Thường có nhưng không bắt buộc với mọi status | **Không có** | 200 có thể có; 204 không có; 202 có thể có |
| Request content | Không có ngữ nghĩa chung | Không có ngữ nghĩa chung | Không có ngữ nghĩa chung |
| Caching | GET là phương thức cache phổ biến | Có thể cập nhật metadata phản hồi GET lưu trong cache | Response DELETE không cacheable; xử lý vô hiệu hóa cache theo quy tắc |
| Cách truyền tiêu chí thông thường | URI/query, header điều kiện | URI và header | URI resource, header điều kiện |

**Idempotent** là tính chất của **hiệu ứng dự kiến** khi lặp cùng một request, không có nghĩa mọi lần gửi phải có cùng status code. Ví dụ DELETE đầu tiên trả 204 và lần tiếp theo trả 404 vẫn có thể idempotent: trạng thái resource sau cả hai lần đều là “không còn tồn tại”.

## 4. Tại sao request body ở GET/HEAD/DELETE gây rủi ro liên thông?

Sự cố thường xuất hiện khi ứng dụng chỉ kiểm thử “controller đọc được JSON” mà chưa thử hết **end-to-end request path**:

~~~mermaid
flowchart LR
    A["Browser / mobile / CLI"] --> B["CDN / reverse proxy"]
    B --> C["WAF / API gateway"]
    C --> D["Load balancer"]
    D --> E["REST controller"]
    E --> F["Service + DB"]
    B -.->|"Cache key thường dựa method, URI, Vary"| G[("HTTP cache")]
~~~

### 4.1. Browser và HTTP client

**Fetch API trong trình duyệt không cho khởi tạo GET hoặc HEAD có request body**; thường nhận lỗi trước khi gửi qua mạng. Công cụ dòng lệnh có thể cho phép gửi body với GET, nhưng đó là khả năng của một công cụ, không chứng minh browser hay SDK tạo từ OpenAPI sẽ hỗ trợ.

**DELETE** thường có thể mang body ở nhiều client, kể cả Fetch, nhưng khả năng gửi **không đồng nghĩa** mọi WAF/proxy/SDK/origin đều xử lý body đó giống nhau. Vì vậy, “DELETE có body chạy với curl” không đủ cơ sở để coi là hợp đồng API liên thông.

### 4.2. Proxy, WAF và API gateway

Các thành phần trung gian có thể:

- Từ chối content ở phương thức không mong đợi theo chính sách phòng chống request smuggling.
- Giới hạn size hoặc loại content, không chuyển tiếp body hoặc xử lý buffering khác với origin.
- Áp dụng xác thực, chữ ký và chuẩn hóa request chỉ dựa trên method, URI và một tập header.
- Retry hoặc định tuyến theo method mà không hiểu bộ lọc được giấu trong body.
- Phát sinh sai khác về framing khi các hop xử lý Content-Length/Transfer-Encoding hoặc stream không nhất quán.

Vì đây là rủi ro **nhiều tầng**, việc trực tiếp gửi vào cổng ứng dụng rồi thấy thành công chỉ xác minh được một đoạn nhỏ của hệ thống.

### 4.3. Cache/CDN và cache key

HTTP cache chủ yếu phân biệt phản hồi theo **method + target URI** và các trường header được chọn thông qua **Vary**; request body không phải một phần của khóa chọn biểu diễn phổ quát.

Xét một API không nên thiết kế:

~~~http
GET /v1/reports HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"year":2025}
~~~

Và một request khác, **cùng URI**, body khác:

~~~http
GET /v1/reports HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"year":2026}
~~~

Nếu origin coi body là bộ lọc nhưng cache không phân biệt hai body, cache có thể trả báo cáo năm 2025 cho người hỏi năm 2026. Đây có thể là **lỗi tính đúng và rò dữ liệu**. Dùng GET với URI phân biệt:

~~~http
GET /v1/reports?year=2025 HTTP/1.1
Host: api.example.test
~~~

Nếu kết quả cá nhân hóa, cache còn cần các điều kiện an toàn như **Cache-Control: private/no-store** tùy nhu cầu; không dựa vào body để giấu nội dung nhạy cảm khỏi cache.

### 4.4. Chữ ký, log, tracing và OpenAPI code generation

Một client ký request dựa trên method, path và query có thể tạo chữ ký khác với gateway kỳ vọng khi có body. Middleware có thể không ghi lại request body ở GET để giảm chi phí; điều tra sự cố sẽ thiếu bộ lọc thực sự. SDK được sinh từ OpenAPI, thư viện HTTP hoặc bộ kiểm thử contract có thể bỏ qua hoặc không cho tạo requestBody ở GET/HEAD/DELETE tùy phiên bản và cách triển khai.

**Khuyến nghị kỹ thuật:** dù một hệ thống tự quản cả client và server, trước khi chấp nhận ngoại lệ phải kiểm tra từng hop, chính sách bảo mật và khả năng thay client trong tương lai. Với API dùng rộng rãi, giải pháp phù hợp thường là **thiết kế lại hợp đồng** để không phụ thuộc vào request content của ba method này.

## 5. Chọn URI, query và header thay cho body

### 5.1. Lọc, phân trang, sắp xếp bằng query

~~~http
GET /v1/orders?status=PAID&createdFrom=2026-11-01&sort=-createdAt&limit=20&cursor=eyJpZCI6... HTTP/1.1
Host: api.example.test
Accept: application/json
~~~

Một hợp đồng tốt định nghĩa rõ:

- Tên filter được phép, kiểu dữ liệu, giá trị mặc định và hành vi khi filter không hợp lệ.
- Phân trang **offset/limit** hay **cursor**; thứ tự ổn định để giảm trùng/bỏ sót khi dữ liệu thay đổi.
- Cách mã hóa URI/percent-encoding, giới hạn số filter và kích thước yêu cầu.
- Thông tin dữ liệu nhạy cảm không xuất hiện trong query, cache hoặc log.
- Chính sách cache, ETag hoặc Last-Modified khi kết quả phù hợp để tái sử dụng.

**URI không có giới hạn chiều dài cố định chung áp dụng cho mọi triển khai HTTP**; browser, proxy, gateway và server có ngưỡng thực tế khác nhau. Nếu truy vấn quá phức tạp/dài, có thể nhận **414 URI Too Long** hoặc lỗi giới hạn khác. Không giải quyết bằng cách nhét cùng truy vấn đó vào body của GET.

### 5.2. Metadata và điều kiện bằng header

HEAD dùng để lấy metadata của resource:

~~~http
HEAD /v1/documents/doc-42 HTTP/1.1
Host: api.example.test

HTTP/1.1 200 OK
ETag: "v7"
Last-Modified: Wed, 18 Nov 2026 08:00:00 GMT
Content-Type: application/pdf

~~~

Với xóa có điều kiện, dùng **If-Match** và ETag đã nhận từ lần GET/HEAD trước:

~~~http
DELETE /v1/documents/doc-42 HTTP/1.1
Host: api.example.test
If-Match: "v7"

HTTP/1.1 204 No Content

~~~

Nếu tài liệu đã được sửa thành phiên bản khác, server có thể trả **412 Precondition Failed** thay vì xóa phiên bản mới ngoài ý muốn. Nếu API bắt buộc mọi lần xóa phải có điều kiện, server có thể trả **428 Precondition Required** khi thiếu If-Match. Như vậy, điều kiện tranh chấp được biểu diễn bằng cơ chế HTTP chuẩn thay vì JSON mơ hồ trong DELETE body.

### 5.3. Đặt tiêu chí xóa trong URI của tài nguyên đích

**Xóa một resource cụ thể**:

~~~http
DELETE /v1/carts/cart-42/items/p-17 HTTP/1.1
Host: api.example.test

HTTP/1.1 204 No Content

~~~

Ở đây target resource đã được xác định bằng path. Server vẫn phải kiểm tra xác thực, quyền sở hữu cart và quy tắc nghiệp vụ; biết ID không đồng nghĩa được quyền xóa.

Không dùng một DELETE body kiểu:

~~~http
DELETE /v1/carts/cart-42/items HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"itemIds":["p-17","p-18"]}
~~~

làm hợp đồng chung nếu danh sách item là thông tin quyết định **xóa những gì**. Điều này dựa vào ngữ nghĩa body mà các trung gian không có nghĩa vụ hiểu. Với xóa số lượng lớn hoặc có kiểm tra nghiệp vụ phức tạp, hãy cân nhắc một **resource tác vụ** ở mục tiếp theo.

## 6. Khi query phức tạp hoặc xóa hàng loạt: thiết kế resource tác vụ

Không phải mọi truy vấn đều biểu diễn thuận tiện bằng URI ngắn; cũng không phải mọi lần xóa đều hoàn tất ngay. HTTP có cách diễn đạt điều này mà không dựa vào GET/DELETE request body.

### 6.1. Truy vấn nhiều điều kiện: POST tạo search request

Ví dụ yêu cầu tìm sản phẩm có hàng chục filter hoặc một cây biểu thức động:

~~~http
POST /v1/search-requests HTTP/1.1
Host: api.example.test
Content-Type: application/json
Idempotency-Key: search-req-92

{
  "resource": "orders",
  "filters": {
    "status": ["PAID", "FULFILLING"],
    "period": {"from": "2026-11-01", "to": "2026-11-18"},
    "storeIds": ["store-1", "store-2"]
  },
  "sort": [{"field": "createdAt", "direction": "desc"}]
}
~~~

Server có thể tạo một resource biểu diễn yêu cầu tìm kiếm, rồi trả:

~~~http
HTTP/1.1 201 Created
Location: /v1/search-requests/sr-92
Content-Type: application/json

{"id":"sr-92","status":"PENDING"}
~~~

Client theo dõi trạng thái và đọc kết quả bằng GET:

~~~http
GET /v1/search-requests/sr-92/results?limit=100 HTTP/1.1
Host: api.example.test
Accept: application/json
~~~

Thiết kế này phù hợp với truy vấn cần nhiều thời gian hoặc có nhu cầu theo dõi/retry. Nó có **chi phí quản lý state, thời hạn resource, quyền truy cập, quota** và không nên được dùng một cách máy móc cho mọi bộ lọc đơn giản. Với tìm kiếm phức tạp nhưng cần phản hồi đồng bộ, API có thể định nghĩa một **POST /v1/products/search** nhận JSON và trả kết quả, ghi rõ đó là giao diện tìm kiếm dùng POST; không mặc định hưởng tính safe, idempotent và cache behavior của GET.

**Idempotency-Key** trong các ví dụ là **hợp đồng cấp ứng dụng**: server phải định nghĩa phạm vi duy nhất, thời gian giữ khóa, cách phát hiện cùng khóa nhưng payload khác và response khi retry. Việc gửi header này không tự khiến POST có ngữ nghĩa idempotent của HTTP.

### 6.2. Xóa hàng loạt: tạo deletion job có thể theo dõi

Một yêu cầu quản trị muốn xóa 2.000 bản ghi theo danh sách và cần kiểm tra quyền, log, đối soát:

~~~http
POST /v1/deletion-jobs HTTP/1.1
Host: api.example.test
Content-Type: application/json
Idempotency-Key: delete-batch-73

{
  "resourceType": "expired-carts",
  "resourceIds": ["cart-10", "cart-11", "cart-12"],
  "dryRun": false
}
~~~

~~~http
HTTP/1.1 202 Accepted
Location: /v1/deletion-jobs/dj-73
Content-Type: application/json

{"jobId":"dj-73","status":"QUEUED"}
~~~

Sau đó client dùng **GET /v1/deletion-jobs/dj-73** để xem trạng thái, số thành công/thất bại và nguyên nhân; nếu hệ thống hỗ trợ hủy tác vụ, cần mô tả riêng cách hủy và giới hạn khi một phần kết quả đã được áp dụng.

Đây không phải “cấm xóa hàng loạt bằng DELETE”. Một API có thể cho DELETE đối với **một tập resource được URI định danh rõ ràng**, miễn hợp đồng nhất quán với các hiệu ứng HTTP. Điểm quan trọng là **danh sách xóa không chỉ tồn tại trong request body mà hệ thống trung gian có thể không hiểu**. Với tác vụ lâu, POST tạo job còn hỗ trợ tracking và audit tốt hơn.

### 6.3. Bảng chọn mẫu API

| Nhu cầu | Thiết kế ưu tiên | Tránh phụ thuộc vào |
|---|---|---|
| Lấy sản phẩm theo ID | GET /v1/products/{id} | GET body chứa ID |
| Lọc/phân trang đơn hàng | GET /v1/orders?status=PAID&limit=20 | JSON filter trong GET body |
| Xem metadata của một tài liệu | HEAD /v1/documents/{id} | HEAD body chứa câu lệnh |
| Xóa một item giỏ hàng | DELETE /v1/carts/{cartId}/items/{itemId} | DELETE body làm selector |
| Xóa chỉ khi chưa bị cập nhật | DELETE theo URI + If-Match | JSON expectedVersion trong DELETE body |
| Tìm kiếm với bộ lọc phức tạp | POST search request hoặc POST search endpoint có hợp đồng rõ | GET body không có cache key phổ quát |
| Xóa số lượng lớn, chạy nền | POST deletion-job rồi GET trạng thái | DELETE body chứa danh sách dài |

## 7. Ví dụ triển khai với Java/Spring MVC

Ví dụ sau minh họa **hợp đồng HTTP**; các lớp service, DTO, kiểm tra quyền và xử lý lỗi được lược bớt để tập trung vào request/response. Không nên coi đoạn code là ứng dụng hoàn chỉnh hoặc sao chép chạy production nếu chưa bổ sung validation, authorization, persistence, transaction và test.

### 7.1. GET dùng query parameter; HEAD theo mapping GET

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;
import java.util.List;

@RestController
@RequestMapping("/v1/products")
class ProductController {
    private final ProductService service;

    ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping
    ProductPage list(
            @RequestParam(required = false) String category,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {

        if (page < 0 || size < 1 || size > 100) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid pagination"
            );
        }
        return service.find(category, page, size);
    }

    @GetMapping("/{id}")
    ResponseEntity<ProductView> get(@PathVariable String id) {
        ProductView product = service.get(id);
        return ResponseEntity.ok()
                .eTag(product.versionTag())
                .body(product);
    }
}

record ProductView(String id, String name, String versionTag) {}
record ProductPage(List<ProductView> items, int page, int size) {}
~~~

Trong Spring MVC, **GET mapping thường xử lý cả HEAD** và framework sẽ không gửi response content của HEAD. Nên kiểm thử đúng phiên bản Spring và các filter/serializer được dùng, nhất là khi controller xử lý stream hoặc có middleware tùy biến. Đo hiệu năng vì việc không trả body **không tự bảo đảm** server không thực hiện công việc tính nội dung đắt đỏ.

Giả định **ProductService** có hai phương thức như trong ví dụ và tự bảo đảm trả lỗi phù hợp khi resource không tồn tại. Đoạn code không nhận **@RequestBody** cho GET vì điều kiện tìm kiếm đã được định nghĩa trên URI.

### 7.2. DELETE với URI và If-Match

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/v1/documents")
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @DeleteMapping("/{id}")
    ResponseEntity<Void> delete(
            @PathVariable String id,
            @RequestHeader(value = "If-Match", required = false)
            String ifMatch) {

        if (ifMatch == null || ifMatch.isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.PRECONDITION_REQUIRED, "If-Match required"
            );
        }

        service.deleteIfCurrentVersionMatches(id, ifMatch);
        return ResponseEntity.noContent().build();
    }
}
~~~

**DocumentService.deleteIfCurrentVersionMatches** phải:

1. Xác thực danh tính và **kiểm tra quyền xóa** trên đúng document.
2. Kiểm tra If-Match bằng **strong comparison** theo ngữ nghĩa ETag; trả 412 khi điều kiện sai.
3. Thực hiện kiểm tra phiên bản và xóa **nguyên tử** trong ranh giới giao dịch/cơ chế cạnh tranh phù hợp; tránh race giữa kiểm tra và ghi.
4. Xác định rõ xóa mềm, audit, giữ dữ liệu và trạng thái khi retry; không tiết lộ tài liệu mà người gọi không có quyền.

Đoạn code là API minh họa, **không cung cấp một triển khai service đúng và đầy đủ**; các điều kiện quan trọng nhất phải được kiểm chứng ở tầng dữ liệu.

### 7.3. Đọc body trong GET/DELETE tại controller có nghĩa là được HTTP bảo đảm?

Không. Một method Java có thể khai báo **@RequestBody** trong **@GetMapping** hoặc **@DeleteMapping**, tùy cấu hình có thể được framework bind dữ liệu. Điều đó chỉ chứng minh **framework tại điểm cuối hiểu content đã tới nơi**. Nó không chứng minh browser gửi được body GET, proxy chuyển tiếp đúng, CDN phân biệt cache theo body hay code generator giữ requestBody.

Với API mới, hãy biểu diễn selector bằng **@PathVariable / @RequestParam**, điều kiện bằng **@RequestHeader**, và JSON phức tạp bằng **@PostMapping** hoặc phương thức khác có ngữ nghĩa phù hợp. Nếu phải tương thích API cũ dùng body cho DELETE, ghi rõ giới hạn, triển khai adapter chuyển tiếp và lộ trình thay contract thay vì mở rộng cách dùng này.

### 7.4. Không nhầm 204 No Content với JSON rỗng

Sau khi DELETE thành công, có thể trả:

~~~http
HTTP/1.1 204 No Content
ETag: "v9"

~~~

**204 không có response content**. Không gửi chuỗi JSON **null**, object trống hoặc thông báo thành công trong body của 204. Nếu cần trả một tài liệu JSON kết quả xóa, dùng 200 với nội dung hợp lệ; nếu tác vụ chưa hoàn tất, dùng 202 và một cách truy vấn trạng thái.

## 8. OpenAPI: diễn đạt contract phù hợp với tooling

Khi viết OpenAPI cho API công khai, nên tránh **requestBody** ở GET, HEAD và DELETE. Một số phiên bản đặc tả và công cụ có cách xử lý khác nhau với requestBody ở phương thức mà HTTP chưa định nghĩa ngữ nghĩa chung; có công cụ không hỗ trợ hoặc bỏ qua. Cách an toàn nhất cho liên thông là biểu diễn dữ liệu bằng path/query/header theo đúng vai trò.

Ví dụ rút gọn OpenAPI 3.0.3:

~~~yaml
openapi: 3.0.3
info:
  title: Product and Document API
  version: 1.0.0
paths:
  /v1/products:
    get:
      summary: List products
      parameters:
        - in: query
          name: category
          required: false
          schema:
            type: string
        - in: query
          name: size
          required: false
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
      responses:
        '200':
          description: Product page
          content:
            application/json:
              schema:
                type: object
  /v1/documents/{id}:
    parameters:
      - in: path
        name: id
        required: true
        schema:
          type: string
    head:
      summary: Get document metadata
      responses:
        '200':
          description: Metadata, no response body
          headers:
            ETag:
              schema:
                type: string
        '404':
          description: Document not found
    delete:
      summary: Delete a specific version
      parameters:
        - in: header
          name: If-Match
          required: true
          schema:
            type: string
      responses:
        '204':
          description: Deleted, no response body
        '412':
          description: Resource version changed
        '428':
          description: If-Match required
~~~

Ví dụ **không có requestBody** ở ba method. Response 204 cũng **không khai báo content**. Trong API production, nên bổ sung schemas thực tế, security schemes, mô hình lỗi nhất quán, ví dụ response và giới hạn phân trang. Dù ở OpenAPI không khai báo body, cũng cần kiểm thử SDK sinh ra từ contract để chắc chắn request target và các header được tạo đúng.

### 8.1. Có nên dùng GET với Content-Type: application/json?

Nếu GET không có request content thì **Content-Type** không có vai trò mô tả JSON gửi lên. Khách thường cần **Accept: application/json** để nói muốn nhận JSON từ server. Ngược lại, **Content-Type: application/json** có ý nghĩa khi gửi JSON trong POST/PUT/PATCH. Việc gắn Content-Type vào GET trống có thể vô hại về framing nhưng không giúp định nghĩa bộ lọc hay cải thiện tương thích.

### 8.2. Tài liệu lỗi nên rõ ràng

Nên phân biệt:

- **400 Bad Request:** cú pháp/giá trị request không hợp lệ theo hợp đồng, bao gồm một lựa chọn policy từ chối body không hỗ trợ.
- **405 Method Not Allowed:** method không được hỗ trợ trên resource; response 405 cần header **Allow** phù hợp.
- **412 Precondition Failed:** If-Match không phù hợp với trạng thái hiện tại.
- **414 URI Too Long:** request target dài vượt khả năng/giới hạn được áp dụng.
- **415 Unsupported Media Type:** định dạng content được gửi không được chấp nhận khi endpoint có xử lý content.
- **422 Unprocessable Content:** content đúng cú pháp nhưng không thể xử lý theo quy tắc ngữ nghĩa của ứng dụng, khi phù hợp.
- **428 Precondition Required:** server yêu cầu điều kiện cập nhật/xóa nhưng client thiếu.

Không có một mã trạng thái duy nhất mà mọi server **bắt buộc** phải trả chỉ vì GET hoặc DELETE kèm body. Cần định nghĩa policy hợp lý và viết test với hệ thống thực tế, thay vì dựa vào một quan sát duy nhất.

## 9. Kiểm thử liên thông: đừng chỉ gọi trực tiếp vào controller

Đường kiểm thử thực tế phải đi qua các thành phần tương đương production:

~~~text
Client/Browser
  -> TLS termination / CDN
  -> WAF / API Gateway
  -> Reverse proxy / Load balancer
  -> Spring MVC app
  -> Cache / Database
~~~

Với ứng dụng mobile hoặc một SDK do OpenAPI sinh ra, cần thêm chính client đó vào ma trận. Một bài kiểm thử thành công với curl chỉ nói được về cặp **curl và đường đi mà lệnh thực sự sử dụng**.

### 9.1. Các lệnh kiểm thử cơ bản

Lấy dữ liệu với query được mã hóa đúng:

~~~bash
curl -i -G "https://api.example.test/v1/products" \
  --data-urlencode "category=camera" \
  --data-urlencode "size=20"
~~~

Lấy metadata bằng HEAD:

~~~bash
curl --head "https://api.example.test/v1/documents/doc-42"
~~~

Xóa có điều kiện:

~~~bash
curl -i -X DELETE \
  -H 'If-Match: "v7"' \
  "https://api.example.test/v1/documents/doc-42"
~~~

Ở đây **-G** yêu cầu curl chuyển các cặp tham số thành **query string** cho GET; **--head** yêu cầu HEAD và chỉ nhận header phản hồi. Lệnh curl không chứng minh server đã kiểm tra quyền hay xử lý ETag đúng: các yêu cầu đó cần test riêng. Lệnh cũng chỉ là ví dụ; URL **api.example.test** không phải dịch vụ chạy thật.

Muốn quan sát một server có tiếp nhận GET body không trong môi trường thử nghiệm có kiểm soát, có thể cấu hình một HTTP client cho request GET kèm JSON rồi so sánh đường trực tiếp với đường qua proxy. **Không đưa kiểu request đó vào contract production** chỉ vì một lần thử thấy được phản hồi mong muốn.

### 9.2. Ma trận kiểm thử đề xuất

| Kiểm thử | Hành động | Bằng chứng/kết quả mong muốn |
|---|---|---|
| **GET query** | Gọi hai URI khác filter, có CDN và không có CDN | Mỗi URI trả đúng tập dữ liệu; cache key theo URI và policy |
| **GET không body** | Gọi bằng browser Fetch, mobile SDK và curl | Không cần request content, hành vi thống nhất |
| **GET body chẩn đoán** | Thử ở môi trường lab qua từng hop | Ghi nhận hop nào từ chối/bỏ qua; không lấy làm hợp đồng |
| **HEAD metadata** | So GET và HEAD cùng URI | HEAD không có response content; ETag/metadata nhất quán theo contract |
| **HEAD khi resource thiếu** | Gọi HEAD tới ID không tồn tại | Nhận status phù hợp, không có body |
| **DELETE một resource** | Xóa item tồn tại rồi gửi lại yêu cầu | Trạng thái cuối ổn định; lần 2 theo contract (204/404/410) |
| **DELETE điều kiện đúng** | Lấy ETag rồi xóa với If-Match hợp lệ | Xóa đúng phiên bản và trả status đã định nghĩa |
| **DELETE điều kiện sai** | Thay đổi resource rồi gửi If-Match cũ | Không xóa phiên bản mới; nhận 412 khi thích hợp |
| **DELETE không điều kiện** | Bỏ If-Match khi API yêu cầu | Không xóa; 428 theo contract |
| **DELETE sau cache GET** | GET resource qua cache, DELETE rồi GET lại | Không phát lại biểu diễn đã bị xóa trái với chính sách |
| **POST deletion job** | Retry cùng Idempotency-Key khi client timeout | Không tạo tác vụ xóa trùng ngoài chính sách |
| **Độ dài URI** | Gửi query vượt ngưỡng gateway thử nghiệm | Nhận lỗi được tài liệu hóa và có cách thay thế |
| **Kiểm thử bảo mật** | Dùng ID resource của tài khoản khác | Server từ chối truy cập/xóa; audit đầy đủ |

**Lưu ý cache invalidation:** một phản hồi thành công cho phương thức không safe có thể làm vô hiệu hóa các entry liên quan theo quy tắc HTTP caching, nhưng không nên giả định mọi cache hoặc CDN của hệ thống sẽ tự được cập nhật nếu luồng DELETE đi qua đường khác, cache đặt chính sách riêng hoặc có lớp application cache. Khi dữ liệu cần xóa ngay, cần thử **invalidation/purge end-to-end**.

### 9.3. Kiểm tra response HEAD không vô tình truyền content

Đối với mỗi HEAD test, xác minh:

- Mã trạng thái phù hợp (200/304/404/... theo tình huống) và **không có response content**.
- ETag, Last-Modified, Content-Type, Cache-Control, Vary phản ánh metadata cần thiết của GET tương ứng.
- Nếu Content-Length có mặt, giá trị phản ánh nội dung GET tương ứng, **không bắt buộc bằng 0**.
- Không vô tình chạy thao tác thay đổi dữ liệu trong controller/service (HEAD và GET đều safe).
- Không mặc định HEAD nhanh hơn GET chỉ do ít byte truyền; đo CPU, query và serialization nếu cần.

Nếu API không hỗ trợ HEAD như mong đợi, kiểm tra router, gateway và cách framework mapping GET/HEAD. Khi cố viết một HEAD handler riêng, cần đảm bảo nó không trả metadata khác hoặc sai phiên bản so với GET.

### 9.4. Kiểm tra DELETE có idempotency ở cấp nghiệp vụ

HTTP định nghĩa DELETE là idempotent về **hiệu ứng dự kiến trên target resource**. Nếu một DELETE gọi hệ thống bên ngoài, phát email, trừ tiền hoặc tạo job mới mỗi lần retry, thiết kế vẫn cần xử lý **side effect** để tránh hậu quả không mong muốn.

Ví dụ:

- Xóa một file lần đầu thành công, lần hai báo không thấy: có thể hợp lệ và idempotent.
- Gửi cùng DELETE hai lần khiến mỗi lần tạo một yêu cầu hoàn tiền khác nhau: **nguy hiểm**, dù mapping endpoint là DELETE.
- Xóa mềm đặt deletedAt mới mỗi lần có thể tạo thêm audit log; log/audit vẫn có thể phát sinh, nhưng không nên làm đổi kết quả nghiệp vụ cần ổn định do retry.

Với tác vụ xóa bất đồng bộ, **idempotency key ứng dụng, job ID ổn định và deduplication** có thể cần thiết bên cạnh ngữ nghĩa HTTP.

## 10. Những trường hợp ngoại lệ và giới hạn thực tế

Có hệ thống nội bộ sử dụng **GET có JSON body** cho ngôn ngữ tìm kiếm phức tạp hoặc **DELETE có body** để truyền thêm thông tin. Không thể suy ra mọi triển khai như vậy đều bất hợp lệ về định dạng message, nhưng cần đánh giá chúng theo tính liên thông:

1. **Phạm vi client:** có browser hoặc SDK đa ngôn ngữ không? Fetch có cho GET/HEAD body không?
2. **Đường truyền:** client có đi qua CDN, WAF, forward/reverse proxy, API gateway, service mesh không? Bản nâng cấp có thể thay hành vi?
3. **Cache:** request content có đang quyết định dữ liệu trả về nhưng không nằm trong cache key không?
4. **Hợp đồng và tooling:** OpenAPI generator, logging, tracing, signature và kiểm thử có cùng hiểu selector/điều kiện?
5. **Rủi ro bảo mật:** framing hoặc cách hiểu khác nhau giữa các hop có bị lợi dụng làm request smuggling, bỏ qua xác thực hoặc sai phân quyền không?
6. **Kế hoạch thay thế:** có thể dùng query/header hoặc POST tạo resource/query job để loại bỏ phụ thuộc riêng không?

Trong phạm vi ứng dụng kín, tổ chức có thể chấp nhận một thỏa thuận riêng sau khi xác minh đầy đủ, nhưng **RFC 9110 khuyến nghị origin server không dựa vào thỏa thuận riêng** với request content của các method này. Với REST API cho nhiều client hoặc đối tác, hãy ưu tiên contract thông thường; lựa chọn đặc biệt cần được ghi thành ADR với bằng chứng tương thích và kế hoạch migration.

### 10.1. Ba nhầm lẫn phổ biến

**Nhầm lẫn 1: “GET mà có body là không phải HTTP”.** Không chính xác: message có thể chứa content, nhưng GET request content không có ngữ nghĩa chung và nhiều implementation không hỗ trợ.

**Nhầm lẫn 2: “DELETE luôn không có body và response cũng không có body”.** Không chính xác: request content có thể được truyền nhưng không có ý nghĩa chung; response DELETE có thể dùng **200** với nội dung, **202** cho tác vụ chưa hoàn tất, hoặc **204** không có nội dung.

**Nhầm lẫn 3: “HEAD trả 200 thì phải gửi JSON rỗng để client nhận”.** Không chính xác: **HEAD không có response content**, ngay cả khi GET tương ứng sẽ trả JSON. HEAD dùng status và header.

### 10.2. Vì sao cùng một API chạy với Postman nhưng hỏng trên trình duyệt?

Một số client cho phép tạo request GET với body; **Fetch trong browser không hỗ trợ**. Thêm vào đó, frontend thường đi qua CDN/WAF/gateway khác đường thử trong mạng nội bộ. Nếu bộ lọc chỉ nằm trong GET body, frontend có thể không tạo request được hoặc cache trả dữ liệu từ bộ lọc khác. Giải pháp là định nghĩa filter trong query khi phù hợp, hoặc chuyển truy vấn phức tạp thành POST với hợp đồng rõ ràng và test end-to-end.

## 11. Bài tập thực hành

Một nhóm phát triển API cho hệ thống quản lý tệp có bốn endpoint đang được đề xuất:

~~~text
A. GET    /v1/files         body: {"ownerId":"u-10","type":"pdf"}
B. HEAD   /v1/files/f-9     body: {"includePreview":true}
C. DELETE /v1/files         body: {"ids":["f-9","f-10"]}
D. DELETE /v1/files/f-9     header: If-Match: "v4"
~~~

Hãy trả lời:

1. Endpoint nào có thể gặp vấn đề với browser Fetch, cache và API gateway? Giải thích cơ chế, tránh trả lời đơn giản “HTTP cấm”.
2. Viết lại A, B và C theo thiết kế dựa trên resource. Cần POST không? Khi nào?
3. Với D, server trả gì khi ETag không khớp hoặc resource đã bị xóa? Phân biệt lựa chọn theo hợp đồng.
4. Một client gửi hai lần DELETE D; lần đầu 204, lần sau 404. Có vi phạm idempotency không?
5. HEAD của một tài liệu có Content-Length lớn nhưng không có response body là đúng hay sai?
6. Đề xuất ba kiểm thử có khả năng phát hiện vấn đề mà unit test controller không thấy.

### 11.1. Lời giải tham khảo

**A — GET body:** dù origin có thể đọc JSON, bộ lọc nằm trong body không có ngữ nghĩa chung. Browser Fetch có thể từ chối, cache có thể dựa vào cùng URI **/v1/files** và trả sai dữ liệu. Nếu điều kiện ngắn và không nhạy cảm, đổi thành **GET /v1/files?ownerId=u-10&type=pdf**; server vẫn phải kiểm tra ownerId có thuộc phạm vi người gọi được phép hay không. Nếu điều kiện phức tạp/dài, dùng POST search request hoặc POST search endpoint với hợp đồng riêng.

**B — HEAD body:** HEAD phải dùng target URI và header để lấy metadata của tài liệu **f-9**, không phải điều khiển preview bằng JSON request body. Dùng **HEAD /v1/files/f-9** để lấy metadata; muốn preview thì định nghĩa resource ví dụ **GET /v1/files/f-9/preview** hoặc một liên kết preview đã được công bố, tùy model tài nguyên.

**C — DELETE body:** nếu muốn xóa nhóm tệp cần kiểm tra quyền, quota và xử lý nền, dùng **POST /v1/deletion-jobs** với danh sách ID trong JSON và theo dõi **GET /v1/deletion-jobs/{id}**. Nếu chỉ xóa một tệp, dùng **DELETE /v1/files/{id}**. Với resource collection được mô hình hóa rõ, có thể có lựa chọn DELETE theo URI phù hợp, nhưng không ngầm dùng request body làm selector bắt buộc.

**D — If-Match:** nếu phiên bản đã khác, **412 Precondition Failed** là cách phản hồi thông thường; nếu API bắt buộc If-Match nhưng request thiếu, **428 Precondition Required** phù hợp. Khi resource đã bị xóa, có thể trả 404/410 hoặc một status đã quy định; cần xem xét thứ tự kiểm tra quyền và điều kiện. Không được biến If-Match sai thành xóa thành công trên phiên bản mới.

**Lặp DELETE:** lần đầu 204, lần hai 404 **không vi phạm idempotency** nếu hiệu ứng dự kiến của việc xóa vẫn ổn định.

**Content-Length của HEAD:** nếu header có mặt, nó có thể cho biết kích thước nội dung GET tương ứng dù response HEAD **không gửi content**. Giá trị không nhất thiết bằng 0; phải đảm bảo phù hợp với GET tương ứng và các điều kiện tạo biểu diễn.

**Kiểm thử liên thông:** gọi từ browser Fetch thật; gọi qua CDN/WAF/API gateway ở môi trường giống production; kiểm tra cache key/invalidation và replay; bổ sung kiểm thử ETag, retry và phân quyền.

## 12. Checklist cho reviewer REST API

- [ ] GET, HEAD và DELETE được chọn theo ý nghĩa của resource, không dựa vào khả năng framework bind JSON tùy ý.
- [ ] Không dùng GET/HEAD/DELETE request content làm điều kiện bắt buộc chọn resource cho API liên thông.
- [ ] GET dùng URI/query thích hợp, không đưa secret hoặc dữ liệu nhạy cảm lên query/log.
- [ ] HEAD không có response content và metadata phù hợp với GET của cùng resource.
- [ ] DELETE URI xác định rõ resource; policy xóa mềm/vật lý, idempotency và retry được tài liệu hóa.
- [ ] DELETE 204 không trả JSON; 200 hoặc 202 chỉ dùng khi có ý nghĩa và hợp đồng rõ.
- [ ] If-Match và ETag được xử lý chính xác nếu cần chống xóa nhầm phiên bản.
- [ ] Tác vụ tìm kiếm/xóa hàng loạt phức tạp có API POST và resource trạng thái rõ ràng khi phù hợp.
- [ ] OpenAPI không dựa vào requestBody ở GET/HEAD/DELETE và SDK được kiểm thử thực tế.
- [ ] Cache key, Cache-Control, Vary và invalidation được kiểm chứng trên đường đi production.
- [ ] Client browser, gateway, WAF, proxy và origin đều được kiểm thử end-to-end.
- [ ] Lỗi phương thức, giới hạn URI, thiếu điều kiện, quyền truy cập và dữ liệu không hợp lệ có response nhất quán.
- [ ] Retry, idempotency và các tác động ngoài hệ thống (payment, email, job) được kiểm soát.

## Tài liệu chuẩn để tra cứu thêm

- **RFC 9110 — HTTP Semantics**: định nghĩa phương thức GET (9.3.1), HEAD (9.3.2), DELETE (9.3.5), safe và idempotent; https://www.rfc-editor.org/rfc/rfc9110.html
- **RFC 9111 — HTTP Caching**: cache key, validation và cache invalidation; https://www.rfc-editor.org/rfc/rfc9111.html
- **Fetch Standard**: giới hạn tạo request có body với GET/HEAD ở môi trường dùng Fetch API; https://fetch.spec.whatwg.org/
- **OpenAPI Specification**: mô tả parameters, requestBody, response và các yêu cầu liên thông khi sinh client; https://spec.openapis.org/oas/latest.html

**Nguyên tắc cần nhớ:** HTTP có thể truyền content ở một request GET, HEAD hoặc DELETE trong một số hoàn cảnh, nhưng **không có ngữ nghĩa chung của request content** cho các method đó. REST API ổn định nên để **URI định danh resource, query mô tả cách truy vấn, header biểu diễn điều kiện và body ở phương thức phù hợp khi cần gửi dữ liệu phức tạp**. Đánh giá thành công dựa trên toàn bộ hành trình client → trung gian → server, không chỉ dựa trên một controller đọc được JSON.
