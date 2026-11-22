# 301, 302, 303, 307, 308 và bảo toàn phương thức khi chuyển hướng

## 1. Vì sao chuyển hướng HTTP quan trọng với REST API?

Trong một REST API, tài nguyên được định danh bằng URI, thao tác được diễn đạt qua phương thức HTTP và kết quả được thể hiện bằng mã trạng thái. Nhóm mã **3xx (redirection)** cho phép máy chủ hướng client tới URI khác hoặc tới tài nguyên thể hiện kết quả của một thao tác. Tuy nhiên, **không phải mọi mã 3xx đều giữ nguyên phương thức HTTP**.

Giả sử ứng dụng đặt hàng có endpoint cũ:

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Idempotency-Key: req-demo-001

{"sku":"BOOK-01","quantity":2}
~~~

Khi API chuyển sang đường dẫn mới /v2/orders, câu hỏi không chỉ là trả về URL nào. Client phải biết **gửi tiếp POST hay chuyển thành GET**, có cần gửi lại body, có thể truyền lại thông tin xác thực và có nên lưu cache địa chỉ chuyển hướng hay không.

- Nếu client đổi POST thành GET, yêu cầu tạo đơn có thể không được thực hiện ở endpoint mới.
- Nếu client giữ POST nhưng gửi lại ngoài ý muốn, nghiệp vụ không được tạo trùng đơn.
- Nếu URI mới nằm ở host khác, header xác thực và cookie có thể không được tự chuyển theo vì lý do bảo mật.
- Nếu chuyển hướng được ghi nhớ lâu, việc quay lại endpoint cũ có thể không có hiệu lực ngay với mọi client.

**Mục tiêu bài học:** chọn đúng giữa **301, 302, 303, 307 và 308** dựa trên ý nghĩa chuyển hướng, thời hạn chuyển hướng và khả năng bảo toàn phương thức/body; thiết kế hợp đồng REST rõ ràng; viết và kiểm thử phản hồi chuyển hướng trong Java/Spring hoặc công nghệ tương đương.

> **Quy tắc ghi nhớ:** 301/302 có ngoại lệ lịch sử cho POST; 303 dẫn tới request truy xuất (thường là GET); 307/308 được thiết kế để không đổi phương thức. Cặp 301/308 mang ý nghĩa chuyển địa chỉ lâu dài, cặp 302/307 mang ý nghĩa tạm thời.

## 2. Một phản hồi redirect có gì?

Phản hồi chuyển hướng thông thường gồm:

~~~http
HTTP/1.1 307 Temporary Redirect
Location: /v2/orders
Cache-Control: no-store
Content-Length: 0
~~~

Các thành phần:

| Thành phần | Vai trò | Lưu ý khi thiết kế API |
|---|---|---|
| **Status 3xx** | Cho biết loại chuyển hướng và ngữ nghĩa tiếp theo | Phải chọn theo method, ý định và thời hạn |
| **Location** | URI tham chiếu mà client có thể dùng để thực hiện request tiếp theo | Có thể là URI tuyệt đối hoặc tham chiếu tương đối; client giải quyết theo URI của request trước |
| **Cache-Control** | Chỉ dẫn về khả năng lưu và thời gian sử dụng đáp ứng | Đặc biệt quan trọng với 301/308 dễ được ghi nhớ |
| **Response body** | Có thể mô tả việc chuyển hướng cho người đọc hoặc client không tự theo | Không phải nơi chuyển tiếp request body cũ |
| **Headers bảo mật** | Chính sách cache, cookie, CORS, v.v. | Không giả định credential luôn được truyền sang host mới |

Máy chủ **gửi phản hồi 3xx về client**, rồi client quyết định có tạo request mới tới URI trong Location không. Chuyển hướng không phải thao tác proxy nội bộ: nếu client không hỗ trợ, không cho phép hoặc không tự theo redirect, hành trình dừng tại phản hồi 3xx.

### 2.1. Phân biệt method, request body và redirect

- **Method:** GET, HEAD, POST, PUT, PATCH, DELETE... xác định ý nghĩa thao tác.
- **Body:** dữ liệu của request, chẳng hạn JSON tạo đơn. Giữ nguyên method không tự đảm bảo client có thể phát lại body nếu body được gửi qua stream một lần.
- **Target URI:** URI của request tiếp theo, có thể khác host, path hoặc query.
- **Follow redirect:** hành vi client thực hiện thêm request, không phải hành vi bắt buộc máy chủ thực hiện thay client.

Những nội dung này cần được mô tả trong hợp đồng API; không nên chỉ ghi “trả redirect khi endpoint thay đổi”.

## 3. Bảng so sánh năm mã trạng thái

| Mã | Tên thông dụng | Ý nghĩa URI đích | Sau POST, client có thể/chủ yếu làm gì? | Giữ nguyên method? | Use case điển hình |
|---|---|---|---|---|---|
| **301** | Moved Permanently | Địa chỉ tài nguyên được chuyển lâu dài | Vì lịch sử, client **có thể** đổi POST thành GET khi theo redirect | **Không bảo đảm** với POST | URI GET cũ được đổi sang URI chuẩn lâu dài |
| **302** | Found | Tài nguyên tạm thời truy cập qua URI khác | Vì lịch sử, client **có thể** đổi POST thành GET khi theo redirect | **Không bảo đảm** với POST | Chuyển tạm request GET khi bảo trì hoặc điều phối |
| **303** | See Other | Kết quả hoặc tài nguyên liên quan cần được **truy xuất** | Thực hiện request truy xuất, **thường GET** (có thể HEAD) | **Không** giữ phương thức ghi | Sau POST, chuyển sang trang/tài nguyên kết quả |
| **307** | Temporary Redirect | URI thay thế tạm thời | Giữ POST khi tự theo redirect | **Có: client không được đổi method** | Tạm chuyển endpoint POST/PUT/PATCH mà vẫn giữ ý nghĩa thao tác |
| **308** | Permanent Redirect | URI thay thế lâu dài | Giữ POST khi tự theo redirect | **Có: client không được đổi method** | Chuyển vĩnh viễn endpoint ghi sang đường dẫn mới |

**Lưu ý chuẩn HTTP:** ngoại lệ 301/302 được quy định cụ thể cho việc client **có thể** chuyển POST thành GET vì tương thích lịch sử. Không có nghĩa là server “ép” mọi client chuyển POST thành GET, hoặc tùy tiện đổi mọi method thành GET. Trong khi đó, 307/308 có quy tắc rõ: client **MUST NOT change the request method** khi tự động chuyển hướng. Đây là lý do chúng thường phù hợp hơn cho các thao tác ghi cần chuyển sang endpoint khác.

**303 không phải một kiểu “tạm chuyển địa chỉ” tương đương 302.** Nó nói với client rằng phản hồi của thao tác hiện tại có thể được tìm thấy qua một request truy xuất tới URI khác, thường là trang/tài nguyên kết quả. Nó đặc biệt hữu ích cho mẫu POST/Redirect/GET.

### 3.1. Bốn câu hỏi để chọn mã nhanh

1. **Có phải muốn client tới tài nguyên kết quả bằng GET/HEAD sau một thao tác ghi?** Chọn **303** khi hợp đồng muốn hành vi này.
2. **Có phải cần giữ nguyên phương thức, bao gồm POST/PUT/PATCH/DELETE?** Chọn **307** nếu tạm thời hoặc **308** nếu lâu dài.
3. **Có phải chuyển URI lâu dài của tài nguyên chỉ được truy vấn bằng GET/HEAD?** **301** thường phù hợp; **308** cũng có thể dùng nếu muốn ý nghĩa bảo toàn method rõ ràng.
4. **Có phải tạm chuyển một thao tác đọc GET/HEAD?** **302** có thể đủ; nếu quy tắc giữ method quan trọng, chọn **307**.

Chọn mã đúng chỉ giải quyết phần HTTP semantics. API vẫn phải xét client thực tế, authentication, redirect support, cache và các giao dịch có side effect.

## 4. Điều gì xảy ra khi một POST gặp redirect?

### 4.1. POST + 301 hoặc 302: có sự không chắc chắn lịch sử

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"sku":"BOOK-01","quantity":2}

HTTP/1.1 302 Found
Location: /v2/orders
~~~

Một số client khi theo redirect **có thể** gửi request mới như sau:

~~~http
GET /v2/orders HTTP/1.1
Host: api.example.test
~~~

Khi đó body tạo đơn không đi cùng GET. Client khác có thể giữ POST theo lựa chọn và cấu hình của nó. Bởi vậy không thể thiết kế hợp đồng POST dựa trên giả định rằng 301 hoặc 302 sẽ luôn bảo toàn request ban đầu.

**Tình huống sai:** API cũ trả 302 từ POST /v1/orders sang /v2/orders, nhưng /v2/orders chỉ chấp nhận POST; client đổi sang GET và nhận 405 Method Not Allowed hoặc dữ liệu ngoài dự kiến. Việc sửa ở đây là đổi sang mã có ngữ nghĩa đúng với mục tiêu, chẳng hạn 307/308, cùng kiểm thử client.

### 4.2. POST + 303: nhận kết quả qua GET

~~~http
POST /checkout HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"cartId":"cart-42"}

HTTP/1.1 303 See Other
Location: /orders/ord-42
~~~

Request tiếp theo thường là:

~~~http
GET /orders/ord-42 HTTP/1.1
Host: api.example.test

HTTP/1.1 200 OK
Content-Type: application/json

{"id":"ord-42","status":"PENDING_PAYMENT"}
~~~

Điểm chính là **không phát lại POST /checkout** ở URI mới. Client truy xuất tài nguyên đại diện cho kết quả của thao tác đã thực hiện. Với request HEAD, HTTP cho phép dùng HEAD làm request truy xuất khi xử lý 303; không nên viết rằng mọi 303 bắt buộc chuyển thành GET trong tất cả tình huống.

### 4.3. POST + 307 hoặc 308: giữ nguyên phương thức

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Idempotency-Key: req-demo-001

{"sku":"BOOK-01","quantity":2}

HTTP/1.1 308 Permanent Redirect
Location: /v2/orders
~~~

Khi client hỗ trợ và quyết định theo redirect, request ở đích vẫn có method POST:

~~~http
POST /v2/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Idempotency-Key: req-demo-001

{"sku":"BOOK-01","quantity":2}
~~~

**307 và 308 không cho phép client tự đổi POST thành GET** khi tự động theo chuyển hướng. Body và các header liên quan thường được client gửi lại để giữ ý nghĩa thao tác, nhưng một số client không thể phát lại streaming body, chặn redirect hoặc không chuyển header nhạy cảm sang origin khác. Do đó, phải kiểm thử **khả năng replay body** và hành vi xác thực của các client được hỗ trợ.

### 4.4. So sánh trực quan hai hành vi

~~~mermaid
flowchart TB
    A[Client gửi POST /old] --> B{Phản hồi từ server}
    B -->|303 See Other| C[Client truy xuất /result bằng GET hoặc HEAD]
    B -->|307 Temporary Redirect| D[Client gửi lại POST tới /new]
    B -->|308 Permanent Redirect| E[Client gửi lại POST tới /new lâu dài]
    B -->|301/302| F[POST có thể bị đổi sang GET bởi client]
    C --> G[Đọc representation của kết quả]
    D --> H[Endpoint mới xử lý thao tác POST]
    E --> H
    F --> I[Cần kiểm tra hành vi từng client]
~~~

## 5. Chọn mã theo tình huống REST thực tế

| Tình huống | Mã gợi ý | Lý do và điều kiện |
|---|---|---|
| GET /articles/old-slug chuyển sang canonical /articles/new-slug vĩnh viễn | **301** | Thông báo vị trí chuẩn lâu dài; phù hợp tài nguyên đọc |
| GET /catalog tạm thời chuyển đến /catalog-preview | **302** | Điều phối tạm cho GET; cần cấu hình cache phù hợp |
| POST /checkout thành công, muốn người dùng xem /orders/42 bằng GET | **303** | POST/Redirect/GET, tránh trình duyệt phát lại POST khi refresh trang kết quả |
| POST /v1/orders tạm chuyển sang /v2/orders nhưng vẫn tạo đơn bằng POST | **307** | Giữ method cho yêu cầu ghi; target phải thực hiện cùng ý nghĩa |
| PUT /v1/users/42 lâu dài được thay thế bằng /v2/users/42 | **308** | Giữ PUT và body khi client theo redirect |
| PATCH /v1/orders/42 tạm chuyển đến endpoint tương đương | **307** | Không tự chuyển PATCH thành GET |
| DELETE /v1/items/42 chuyển lâu dài đến /v2/items/42 | **308**, nếu chính sách cho phép | Phải giữ DELETE và xác minh quyền/sự kiện xóa tại đích |
| POST tạo tài nguyên và trả kết quả ngay cho API client | **201 Created** thường phù hợp hơn redirect | 201 có thể kèm Location của tài nguyên mới nhưng **không phải** 3xx |
| Công việc bất đồng bộ mới được tiếp nhận, chưa hoàn thành | **202 Accepted**, cùng hợp đồng theo dõi tiến trình | 202 không tự chứng minh thành công; có thể dùng URI trạng thái |

Các mã trong bảng là hướng dẫn lựa chọn theo ý định. Một hợp đồng API cho phép client tự xử lý Location cũng có thể phù hợp hơn yêu cầu redirect tự động. Cần thống nhất rõ **client nào sẽ dùng API, khả năng theo redirect, trải nghiệm mong muốn và hậu quả nếu không theo**.

### 5.1. GET và HEAD khi chuyển địa chỉ

Đối với GET, 301/302/307/308 thường đều dẫn tới **GET ở đích**; khác biệt lớn là tính lâu dài và khả năng cache. Với HEAD, client tiếp tục truy vấn metadata mà không yêu cầu response body. 303 cũng cho phép một request truy xuất bằng GET hoặc HEAD; không dùng 303 để diễn đạt việc phải gửi lại một request ghi.

Nếu URI cũ chỉ là bí danh lâu dài của một tài nguyên đọc, 301 là lựa chọn quen thuộc và có khả năng tương thích rộng. Chọn 308 khi cần truyền tải rõ quy tắc giữ method hoặc route cũng xử lý các thao tác không an toàn.

### 5.2. PUT, PATCH và DELETE

PUT được định nghĩa là idempotent ở cấp ngữ nghĩa HTTP: thực hiện lại cùng một PUT hợp lệ nhằm tạo ra cùng trạng thái tài nguyên mục tiêu (dù việc ghi log/side effect phụ trợ có thể xảy ra). DELETE cũng có ngữ nghĩa idempotent. **PATCH không mặc nhiên idempotent**; một PATCH kiểu “tăng số lượng thêm 1” có thể nhân tác động khi bị gửi lại. POST cũng không mặc nhiên idempotent.

Vì thế, 307/308 bảo toàn method nhưng **không làm một thao tác trở thành idempotent**. Khi client hoặc proxy retry request, vẫn cần idempotency key, unique constraint, version/ETag, điều kiện If-Match hoặc kiểm soát nghiệp vụ thích hợp. Không nên đổi phương thức của một thao tác ghi chỉ để “đi qua redirect cho dễ”.

## 6. Khi nào dùng 303: mẫu POST/Redirect/GET

Mẫu **Post/Redirect/Get (PRG)** phổ biến với form hoặc ứng dụng web có điều hướng:

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant API as REST API
    participant DB as Database
    U->>API: POST /checkout
    API->>DB: Ghi đơn một lần
    DB-->>API: orderId=42
    API-->>U: 303 See Other, Location: /orders/42
    U->>API: GET /orders/42
    API-->>U: 200 OK, representation đơn
    Note over U,API: Refresh trang kết quả làm lại GET, không lặp POST ban đầu
~~~

Lợi ích:

- Tách thao tác thay đổi trạng thái khỏi request chỉ đọc trang kết quả.
- Cho phép URL trang kết quả có thể bookmark hoặc chia sẻ theo quyền truy cập.
- Giảm nguy cơ refresh trình duyệt tái gửi form POST ngay sau khi đã nhận 303.
- Giúp xác định tài nguyên đại diện cho kết quả của lệnh.

**Giới hạn:** PRG không phải cơ chế chống tạo trùng nghiệp vụ đầy đủ. Người dùng có thể nhấn gửi hai lần trước khi nhận 303; mạng có thể timeout trước khi client nhận phản hồi. Server vẫn phải xử lý idempotency và chống ghi trùng khi phù hợp.

Với REST API dùng bởi ứng dụng di động hoặc service-to-service, **201 Created + Location** đôi khi trực tiếp và dễ tiêu thụ hơn 303. Chọn 303 khi muốn client chủ động thực hiện request truy xuất tới URI kết quả theo hợp đồng đã tài liệu hóa.

### 6.1. 201 Created có Location nhưng không phải redirect

~~~http
HTTP/1.1 201 Created
Location: /orders/42
Content-Type: application/json

{"id":"42","status":"CREATED"}
~~~

Phản hồi trên **không yêu cầu client tự theo Location**, vì status là 201. Location chỉ định danh tài nguyên mới được tạo (theo ngữ nghĩa tương ứng). Nếu muốn client truy xuất URI kết quả tự động bằng GET hoặc HEAD, hãy thiết kế 303 cho trường hợp phù hợp.

### 6.2. 202 Accepted và kết quả xử lý bất đồng bộ

Nếu việc tạo đơn được xử lý trong queue, phản hồi ban đầu có thể là 202 với URI tiến trình:

~~~http
HTTP/1.1 202 Accepted
Location: /operations/op-42
Retry-After: 3
Content-Type: application/json

{"operationId":"op-42","status":"PENDING"}
~~~

Client cần có hợp đồng truy vấn/truy nhận trạng thái. Khi hoạt động hoàn tất, endpoint trạng thái có thể trả 303 tới tài nguyên kết quả nếu API chọn cách đó. Điều kiện tiên quyết là trạng thái hoàn tất được xác nhận đáng tin cậy, không dùng 303 như phép thay thế cho theo dõi queue hoặc giao dịch.

## 7. Chuyển endpoint tạm thời và lâu dài

### 7.1. Chuyển tạm bằng 302 hay 307?

Đặt câu hỏi: **Request ở đích có phải mang nguyên method?**

- GET tài nguyên danh mục tạm hiển thị ở endpoint dự phòng: 302 thường dễ dùng.
- POST hoặc PATCH cần tạm đến endpoint khác với cùng ý nghĩa: 307 phù hợp hơn vì không được đổi method.
- Nếu chỉ muốn client xem trang thông báo sau một lệnh đã được xử lý, 303 diễn đạt đúng hơn 307.

Tránh dùng 307 như giải pháp failover chung khi chưa chắc endpoint đích có quyền, data owner, rate limit và xử lý side effect giống nguồn. Redirect có thể đổi origin và làm mất thông tin xác thực hoặc vi phạm chính sách network.

### 7.2. Chuyển lâu dài bằng 301 hay 308?

- **301:** rất phổ biến với GET/HEAD khi đổi slug, đổi cấu trúc URI hoặc xác lập URI chuẩn.
- **308:** nêu rõ ý định chuyển lâu dài mà **không thay đổi method**. Có lợi khi route cũ từng nhận POST/PUT/PATCH/DELETE và API đích có cùng hợp đồng.

**Không vội dùng redirect vĩnh viễn** trong quá trình thử nghiệm: client, proxy hoặc cache có thể ghi nhớ URI mới, khiến việc đảo lại lộ trình khó hơn. Khi migration chưa ổn định, có thể dùng 307 có giới hạn cache, rồi chuyển sang 308 sau khi kiểm chứng tương thích.

### 7.3. Một kế hoạch chuyển v1 sang v2

1. **Xác định thay đổi hợp đồng:** endpoint v2 có giữ cùng method, schema, authorization, kết quả nghiệp vụ và điều kiện lỗi không?
2. **Kiểm tra khách hàng thực:** browser, CLI, SDK, mobile app, server-to-server, proxy/API gateway có tự theo 307/308 và phát lại body được không?
3. **Tạo đích trước:** endpoint mới hoạt động, đủ năng lực, có telemetry, kiểm thử tính đúng đắn và idempotency.
4. **Điều phối có kiểm soát:** cân nhắc 307 cho giai đoạn chuyển tiếp khi cần giữ method; dùng 308 sau khi đường mới ổn định và quyết định là lâu dài.
5. **Theo dõi luồng cũ:** tỷ lệ 3xx, số client không theo, lỗi 401/403/405 ở đích, redirect loop và latency tăng thêm.
6. **Cập nhật hợp đồng:** OpenAPI, SDK, tài liệu, ví dụ và thông báo deprecation; khuyến khích client gọi trực tiếp URI mới.
7. **Đóng đường cũ có kế hoạch:** khi hết thời hạn tương thích, trả kết quả đã thiết kế (chẳng hạn 410 Gone cho tài nguyên không còn) nếu phù hợp hợp đồng, thay vì giữ redirect vô hạn mà không có owner.

**Một lần redirect tạo thêm ít nhất một round trip HTTP** trong hành trình client theo redirect. Với API có độ trễ thấp hoặc lượng request lớn, migrate client sang URI mới trực tiếp thường tốt hơn việc coi redirect là đường truyền chính lâu dài.

## 8. Cache và thời hạn của redirect

Ngữ nghĩa “permanent” và khả năng lưu cache có liên quan, nhưng **không đồng nghĩa** hoàn toàn:

| Mã | Khả năng cache thường gặp | Hành động thiết kế |
|---|---|---|
| **301** | Thuộc nhóm response có thể được cấp freshness theo heuristic nếu phù hợp quy tắc cache | Thận trọng khi di chuyển URI lâu dài, đặt cache policy có chủ đích |
| **308** | Tương tự 301 ở ngữ nghĩa vĩnh viễn và có thể được cache theo heuristic | Cân nhắc rollback, đặc biệt khi client ghi nhớ vị trí mới |
| **302** | Không nên mặc định cache tự giữ lâu nếu không có freshness rõ | Đặt Cache-Control theo nhu cầu tạm thời |
| **303** | Chỉ cache khi đáp ứng các điều kiện phù hợp, thường cần freshness tường minh | Không coi PRG redirect là tài nguyên ổn định để cache tùy tiện |
| **307** | Không nên mặc định cache tự giữ lâu nếu không có freshness rõ | Đặt chính sách cache phù hợp thời gian chuyển hướng |

Khả năng cache **còn phụ thuộc method của request, Cache-Control, quy tắc HTTP cache và hành vi client**. Không suy luận rằng một 308 sau POST chắc chắn được mọi proxy/browser cache giống 308 sau GET.

Ví dụ muốn client kiểm tra lại đường chuyển hướng tạm trong mỗi lần truy cập:

~~~http
HTTP/1.1 307 Temporary Redirect
Location: /v2/orders
Cache-Control: no-store
~~~

Ví dụ chuyển URI GET lâu dài, có chính sách freshness tường minh:

~~~http
HTTP/1.1 301 Moved Permanently
Location: /articles/new-slug
Cache-Control: public, max-age=3600
~~~

Thông số max-age trong ví dụ chỉ để minh họa, không phải thời gian tối ưu chung. Với endpoint có quyền truy cập hoặc response riêng tư, không tùy tiện dùng public; chính sách cache phải được thiết kế theo dữ liệu và security model.

## 9. Location và tính đúng đắn của URI đích

### 9.1. URI tương đối và tuyệt đối

Cả hai cách đều có thể hợp lệ khi target được giải quyết đúng:

~~~http
Location: /v2/orders
~~~

~~~http
Location: https://api.example.test/v2/orders
~~~

URI tương đối thuận lợi khi cùng origin, tránh hard-code host trong các môi trường. URI tuyệt đối diễn đạt rõ host đích, cần thiết khi chuyển sang origin khác, nhưng phải kiểm tra proxy headers, scheme HTTPS, port và URL do người dùng cung cấp.

**Cảnh báo:** Nếu backend sau reverse proxy tự dựng redirect từ Host hoặc X-Forwarded-* không được kiểm soát, có thể phát sinh URI sai scheme/host hoặc open redirect. Chỉ tin forwarded headers từ proxy đáng tin và dùng danh sách host/đích được cho phép khi tạo Location.

### 9.2. Path, query và ý nghĩa tài nguyên

Một redirect không nên làm mất tham số ảnh hưởng nghiệp vụ hoặc làm lộ thông tin nhạy cảm:

- GET /search?q=java&page=2 chuyển sang endpoint mới cần giữ ý nghĩa query nếu hợp đồng vẫn hỗ trợ.
- POST /v1/orders chuyển sang /v2/orders phải xác định schema và header ở đích có tương thích hay không.
- Không đặt access token, khóa API hoặc thông tin nhạy cảm vào Location/query string.
- Nếu dữ liệu body được ký theo đường dẫn, thay path có thể khiến signature không còn hợp lệ; cần thiết kế lại hợp đồng ký.
- Không chuyển một DELETE sang endpoint khác nếu nó có nghĩa xóa loại tài nguyên khác; redirect phải giữ đúng ý nghĩa thao tác được công bố.

Tài liệu API nên cung cấp **response 3xx mẫu, Location, hành vi client và thời điểm bỏ URI cũ**. Nếu client được yêu cầu không tự theo redirect, phải nêu cách ứng dụng đọc Location và tạo request tiếp theo.

## 10. Bảo mật khi redirect trong REST API

### 10.1. Redirect qua origin khác

Nếu chuyển từ api.example.test sang api-new.example.test, client có thể không tự chuyển Authorization hoặc Cookie. Đây là hành vi bảo vệ thông tin nhạy cảm, không phải lỗi phải sửa bằng cách chuyển mọi credential một cách vô điều kiện.

- Với **Bearer token**, xác nhận audience, issuer, scope và chính sách cho phép token được dùng ở đích.
- Với **Cookie**, domain, SameSite, Secure và browser policy quyết định việc cookie có được gửi không.
- Với **browser CORS**, redirect, preflight và cross-origin request có các giới hạn riêng; cần thử trên browser và chính sách production.
- Với **mTLS hoặc request signature**, việc đổi host/path có thể làm thay đổi cơ chế xác thực, certificate và phần dữ liệu được ký.

**Không khuyến nghị sao chép Authorization header sang một origin chưa được tin cậy** chỉ để 307/308 tiếp tục thành công.

### 10.2. HTTPS và chuyển hướng kém an toàn

Nếu API nhận dữ liệu nhạy cảm, nên cho client gọi thẳng HTTPS. Redirect từ HTTP sang HTTPS không thay thế biện pháp bảo mật khi request ban đầu đã có body nhạy cảm gửi qua HTTP. Khi chuyển HTTPS sang HTTP, có nguy cơ hạ cấp bảo mật và nhiều client sẽ từ chối theo redirect.

Đối với website có browser, HSTS giúp browser tuân theo HTTPS cho host đã áp dụng chính sách, nhưng không thể coi nó là bảo đảm cho tất cả REST client. Quản lý certificate, URL gốc và cấu hình proxy là một phần của thiết kế.

### 10.3. Open redirect và SSRF

Không cho phép client tự chọn bất kỳ URI đích qua tham số như nextUrl rồi trả:

~~~http
HTTP/1.1 302 Found
Location: https://untrusted.example/collect
~~~

Nếu tham số redirect không được kiểm soát, kẻ tấn công có thể dẫn người dùng hoặc một client tự động tới host giả mạo, làm lộ dữ liệu qua URL hoặc tạo nguy cơ SSRF khi client/backend theo redirect. Áp dụng allowlist của host/scheme, kiểm tra URL sau chuẩn hóa, và ưu tiên tham chiếu path nội bộ khi thích hợp.

### 10.4. Retry, body replay và hành vi có side effect

307/308 có thể khiến client phát lại request body ở endpoint mới. Nếu endpoint cũ **đã xử lý nghiệp vụ trước khi trả redirect**, thao tác có thể thực hiện hai lần. Với POST tạo đơn hoặc lệnh thanh toán:

1. Quyết định redirect trước khi thực hiện side effect nếu mục tiêu chỉ là đổi URI.
2. Bảo đảm endpoint đích kiểm tra quyền, idempotency key và invariant nghiệp vụ.
3. Dùng unique constraint/transaction và cơ chế chống trùng phù hợp; không coi client hoàn hảo.
4. Kiểm thử client timeout, reconnect, retry qua proxy và callback lặp.
5. Ghi correlation ID để đối soát request trước và sau redirect.

Kể cả khi redirect giữ đúng method, **khả năng thực hiện đúng một lần về nghiệp vụ là trách nhiệm của thiết kế ứng dụng**, không phải tính chất tự động của HTTP redirect.

## 11. Triển khai ví dụ bằng Java/Spring

### 11.1. Trả 308 khi di chuyển endpoint POST

Đoạn mã minh họa Spring Web; URI đích phải thực sự hỗ trợ POST với hợp đồng tương đương:

~~~java
import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class LegacyOrderRedirectController {

    @PostMapping("/v1/orders")
    public ResponseEntity<Void> movedPermanently() {
        return ResponseEntity
                .status(HttpStatus.PERMANENT_REDIRECT) // 308
                .location(URI.create("/v2/orders"))
                .build();
    }
}
~~~

Server không sao chép body từ request cũ sang request mới. Nó trả 308 và Location; **client** chịu trách nhiệm tạo request POST mới khi chọn theo redirect. Vì vậy, backend tại /v1/orders không nên ghi một đơn trước khi chuyển hướng.

Nếu di chuyển chỉ mang tính tạm thời, đổi status thành HttpStatus.TEMPORARY_REDIRECT (307), đồng thời đặt chính sách cache thích hợp:

~~~java
return ResponseEntity
        .status(HttpStatus.TEMPORARY_REDIRECT)
        .location(URI.create("/v2/orders"))
        .header("Cache-Control", "no-store")
        .build();
~~~

Đây là một response fragment đặt trong controller method, không phải đoạn mã đứng riêng có thể biên dịch ngoài phương thức.

### 11.2. Dùng 303 cho POST/Redirect/GET

Ở ví dụ sau, OrderService được giả định đã có hàm tạo đơn với cơ chế idempotency. Đây là phần hợp đồng nghiệp vụ cần triển khai và kiểm thử riêng:

~~~java
import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
class CheckoutController {
    private final OrderService orderService;

    CheckoutController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping("/checkout")
    public ResponseEntity<Void> checkout(
            @RequestBody CheckoutRequest request,
            @RequestHeader("Idempotency-Key") String key) {

        String orderId = orderService.createOnce(request, key);

        return ResponseEntity
                .status(HttpStatus.SEE_OTHER) // 303
                .location(URI.create("/orders/" + orderId))
                .build();
    }

    @GetMapping("/orders/{id}")
    public ResponseEntity<OrderView> findOrder(
            @PathVariable String id) {
        return ResponseEntity.ok(orderService.getView(id));
    }
}
~~~

Các kiểu OrderService, CheckoutRequest và OrderView là mô hình minh họa của ứng dụng. **createOnce** phải bảo vệ idempotency ở phía server và kiểm tra dữ liệu đầu vào; tên hàm không tự tạo bảo đảm. Endpoint GET /orders/{id} còn phải kiểm tra người gọi có quyền xem đơn tương ứng.

### 11.3. 301/302 cho GET

~~~java
import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CatalogRedirectController {

    @GetMapping("/old-catalog")
    public ResponseEntity<Void> permanentGetRedirect() {
        return ResponseEntity
                .status(HttpStatus.MOVED_PERMANENTLY) // 301
                .location(URI.create("/catalog"))
                .build();
    }

    @GetMapping("/preview")
    public ResponseEntity<Void> temporaryGetRedirect() {
        return ResponseEntity
                .status(HttpStatus.FOUND) // 302
                .location(URI.create("/catalog-preview"))
                .header("Cache-Control", "no-store")
                .build();
    }
}
~~~

Đặt route tránh vòng lặp: /catalog không được lại trả redirect tới /old-catalog. Nếu path có ID hoặc query phức tạp, xây URI bằng công cụ encode URI phù hợp thay vì nối chuỗi nhận trực tiếp từ người dùng.

## 12. Kiểm thử redirect ở hai cấp

### 12.1. Kiểm tra response hợp đồng với MockMvc

MockMvc kiểm tra controller trả đúng status và Location, nhưng **không mặc nhiên chứng minh client thực sẽ theo redirect và giữ method/body**.

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(LegacyOrderRedirectController.class)
class LegacyOrderRedirectControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void redirectsPostPermanentlyToNewEndpoint() throws Exception {
        mvc.perform(post("/v1/orders")
                .contentType("application/json")
                .content("{\"sku\":\"BOOK-01\",\"quantity\":2}"))
            .andExpect(status().is(308))
            .andExpect(header().string("Location", "/v2/orders"));
    }
}
~~~

Để kết luận method được bảo toàn khi **theo** redirect, cần có bài **integration/end-to-end test** chạy qua HTTP client thật và một endpoint đích ghi nhận method, body, content type, idempotency key và kết quả nghiệp vụ.

### 12.2. Kiểm tra thủ công bằng curl

Gửi request để quan sát phản hồi 3xx mà chưa tự theo:

~~~bash
curl -i \
  -H 'Content-Type: application/json' \
  --data '{"sku":"BOOK-01","quantity":2}' \
  http://localhost:8080/v1/orders
~~~

Thêm --location (-L) để curl thử theo redirect:

~~~bash
curl --location --verbose \
  -H 'Content-Type: application/json' \
  --data '{"sku":"BOOK-01","quantity":2}' \
  http://localhost:8080/v1/orders
~~~

Trong ví dụ, **--data tự chọn POST** nên không cần thêm --request POST hoặc -X POST. Ép method bằng -X khi thử redirect có thể gây hiểu nhầm vì curl vẫn giữ lựa chọn method tùy tình huống. Với 307/308, cần xác nhận endpoint đích nhận POST và payload; với 303, phải thấy request theo redirect là GET (hoặc HEAD theo trường hợp).

**Lưu ý bảo mật:** --verbose có thể hiển thị URL, header và dữ liệu nhạy cảm. Chỉ thử với môi trường và dữ liệu giả được phép; không chia sẻ log chứa Authorization, Cookie hoặc dữ liệu cá nhân.

### 12.3. Ma trận thử nghiệm cần có

| Test | Request đầu | Mã trả về | Kết quả mong đợi cần xác minh |
|---|---|---|---|
| Canonical URI | GET /old | 301 | Client tới GET /new; cache phù hợp |
| Đổi đường GET tạm | GET /old | 302 | GET /new; cache không lưu quá lâu |
| PRG | POST /checkout | 303 | GET /orders/{id}; không lặp POST khi refresh trang kết quả |
| Chuyển POST tạm | POST /v1/orders | 307 | POST /v2/orders; body và dữ liệu nghiệp vụ đúng |
| Chuyển PUT lâu dài | PUT /v1/item/1 | 308 | PUT /v2/item/1; nội dung và precondition phù hợp |
| PATCH/DELETE | PATCH hoặc DELETE /v1/... | 307/308 | Method không bị đổi; kết quả không bị lặp tác động ngoài ý muốn |
| HEAD | HEAD /old | 301/302/307/308 | Kiểm tra method và hành vi không lấy body |
| Cross-origin | POST sang host khác | 307/308 | Chính sách credential, TLS, CORS, chữ ký và redirect được kiểm soát |
| Vòng lặp | GET A → B → A | Bất kỳ 3xx | Client không treo vô hạn, có cảnh báo và sửa route |
| Client không theo redirect | Bất kỳ | Bất kỳ 3xx | SDK/ứng dụng có xử lý Location hoặc thông báo rõ |
| Streaming/non-replayable body | POST stream | 307/308 | Client xử lý được hoặc báo lỗi có kiểm soát; không mất dữ liệu |

### 12.4. Kiểm thử cả kết quả nghiệp vụ

Đối với endpoint tạo đơn, kiểm tra thêm:

- Tổng số đơn được tạo tương ứng với **idempotency key** và yêu cầu hợp lệ.
- Cả endpoint cũ và mới cùng áp dụng xác thực, phân quyền, chống replay và validation.
- Một request timeout rồi retry không tạo thêm đơn hoặc thu thêm tiền ngoài quy tắc nghiệp vụ.
- Trạng thái callback/payment được đối soát sau retry, bao gồm failure và timeout từ đối tác.
- CORS, gateway, WAF, rate limit, trace ID và metric vẫn hoạt động với URI mới.
- Không có 3xx loop, location sai origin hoặc rò rỉ token trong URL/log.

Đây mới là bằng chứng chuyển hướng an toàn đối với thao tác ghi, thay vì chỉ thấy status code đúng.

## 13. OpenAPI và tài liệu hợp đồng chuyển hướng

Đối với REST API dùng OpenAPI, mô tả rõ các response có Location, ý nghĩa và cách client phải xử lý. Ví dụ minh họa một endpoint chuyển vĩnh viễn:

~~~yaml
paths:
  /v1/orders:
    post:
      summary: Old endpoint for creating orders
      description: >
        Use /v2/orders. A client following 308 must preserve
        the POST method and applicable request content.
      responses:
        '308':
          description: Permanent redirect to the new order endpoint
          headers:
            Location:
              description: New endpoint URI
              schema:
                type: string
                format: uri-reference
        '401':
          description: Authentication required or invalid
        '403':
          description: Not authorized
~~~

Đây chỉ là **một phần** định nghĩa OpenAPI; khi triển khai phải mô tả requestBody, security scheme, response thành công, validation và ví dụ hợp đồng của endpoint /v2/orders. Tùy phiên bản OpenAPI và công cụ, một số code generator hoặc HTTP client **không tự theo 308**. Đừng mặc định chỉ cần khai báo response 308 thì SDK đã xử lý đúng.

Tài liệu migration nên ghi:

1. URI cũ và URI mới; có thay host hay không.
2. Method, body, Content-Type, Accept, auth scope, idempotency key và precondition cần giữ.
3. Status 3xx cụ thể, Location và chính sách cache.
4. Ngày bắt đầu chuyển hướng, thời gian tồn tại của API cũ và cách xử lý client không follow.
5. Kịch bản lỗi đặc trưng: 401, 403, 405, redirect loop, invalid Location, body không replay.
6. Khi nào client nên sửa base URL để **gọi thẳng endpoint mới**, tránh thêm hop.

## 14. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Dùng 302 cho POST khi cần giữ body/method | Client có thể đổi thành GET | Dùng 307/308 và thử với client thật |
| Dùng 307 để chuyển tới trang kết quả sau POST | Client phát lại POST tới URI chỉ nhận GET | Dùng 303 cho PRG hoặc 201 cho tạo resource |
| Coi 301 luôn giữ POST | Sai do ngoại lệ lịch sử | Không dùng 301 khi cần bảo toàn POST |
| Coi 303 luôn cùng nghĩa với 302 | Lẫn “xem kết quả” với “tạm chuyển tài nguyên” | Dựa vào ý định của request tiếp theo |
| Không đặt Location hoặc tạo sai URI | Client không xác định được điểm đến | Kiểm tra scheme, host, path, encoding |
| Chuyển endpoint cũ nhưng đã thực hiện side effect | Có thể tạo trùng khi client theo redirect | Redirect trước xử lý, có idempotency |
| Dùng 308 quá sớm rồi rollback path | Cache/client vẫn nhớ URI mới | Giai đoạn thử dùng 307/cache có kiểm soát |
| Tự chuyển Authorization sang host lạ | Rò rỉ thông tin xác thực | Chính sách trust và auth riêng ở target |
| Redirect HTTPS sang HTTP | Rủi ro lộ dữ liệu hoặc client từ chối | Dùng HTTPS end-to-end, kiểm tra proxy |
| Giả định mọi SDK follow 3xx | Client fail hoặc mất body | Contract test theo tập client được hỗ trợ |
| Dùng redirect làm cơ chế retry giao dịch | Trùng đơn/thanh toán | Idempotency, state machine, reconciliation |
| Chỉ kiểm tra response MockMvc | Không biết thực tế client gửi method nào ở đích | Thử tích hợp theo redirect end-to-end |

## 15. Bài tập thực hành

### Bài 1: chọn mã phù hợp

Chọn mã và giải thích:

1. API GET /products/old-id có URI chuẩn mới /products/new-id lâu dài.
2. API POST /orders tạm chuyển sang service mới nhưng vẫn yêu cầu tạo đơn bằng POST.
3. Sau POST /checkout đã tạo đơn, trình duyệt cần mở trang /orders/42 bằng GET.
4. API PUT /v1/profiles/42 được chuyển lâu dài sang /v2/profiles/42 và phải giữ body.
5. GET /news tạm chuyển đến /news-preview trong một đợt bảo trì.

**Gợi ý đáp án:** (1) 301, có thể cân nhắc 308; (2) 307; (3) 303; (4) 308; (5) 302 hoặc 307 nếu muốn nhấn mạnh giữ method. Các câu trả lời phải kèm giả định về cache, client và hợp đồng URI đích.

### Bài 2: phát hiện lỗi trong hợp đồng

API cũ trả:

~~~http
HTTP/1.1 302 Found
Location: /v2/orders
~~~

Client gọi POST /v1/orders với JSON; sau khi tự theo 302, endpoint v2 trả 405 Method Not Allowed.

**Câu hỏi:** Điều gì có thể đã xảy ra? Chỉnh status sang 307 giải quyết toàn bộ bài toán chưa?

**Gợi ý:** Client có thể đã đổi POST thành GET. 307 giữ method khi client follow, nhưng còn phải kiểm tra body replay, authentication, idempotency, schema và đường đích. Thử nghiệm thực tế để xác nhận.

### Bài 3: tạm chuyển API thanh toán

Một API POST /payments chạy phía sau gateway, cần chuyển tạm tới host khác. Host mới không chấp nhận token của host cũ và client mobile không replay được streaming body.

**Câu hỏi:** Có nên trả 307 ngay cho mọi client không?

**Gợi ý:** Chưa. Về ngữ nghĩa 307 phù hợp để giữ POST, nhưng kiến trúc chưa đáp ứng auth và body replay. Cần thiết kế lại hợp đồng, cập nhật client, giữ gateway/proxy ở origin tin cậy khi phù hợp hoặc cung cấp migration tương thích. Tránh chuyển token sang host khác một cách mù quáng.

### Bài 4: viết bài kiểm thử

Viết một test chứng minh POST /v1/orders trả 308 và Location /v2/orders, sau đó một bài thử tích hợp xác nhận endpoint /v2/orders nhận đúng POST, JSON và idempotency key. Mô phỏng client từ chối theo redirect và client theo redirect quá nhiều lần để kiểm tra khả năng quan sát lỗi.

**Gợi ý:** MockMvc chỉ chứng minh response 308 và Location. Phần giữ method/body đòi hỏi HTTP client thật; dùng endpoint đích giả ghi nhận request. Không dùng giao dịch thanh toán thực trong thử nghiệm.

## 16. Checklist trước khi phát hành chuyển hướng

- [ ] Đã xác định rõ là **chuyển URI**, **chuyển tạm**, hay **truy xuất kết quả sau thao tác ghi**?
- [ ] Đã chọn 301/302/303/307/308 đúng với thời hạn và phương thức mong muốn?
- [ ] Nếu cần giữ POST/PUT/PATCH/DELETE, đã dùng 307/308 và kiểm thử method/body?
- [ ] Nếu dùng PRG, client có theo 303 bằng GET/HEAD và kết quả không tạo side effect mới?
- [ ] Đã phân biệt 201 Created + Location, 202 Accepted với phản hồi redirect 3xx?
- [ ] Location hợp lệ, encode chính xác, không có host giả mạo hoặc vòng lặp?
- [ ] Đã chọn Cache-Control phù hợp, nhất là với chuyển hướng vĩnh viễn?
- [ ] Target giữ đúng hợp đồng nghiệp vụ, validation, content type, auth và phân quyền?
- [ ] Không đưa token/dữ liệu nhạy cảm vào URI; không tự chuyển credential qua origin không tin cậy?
- [ ] Đã thử client hỗ trợ thực tế, bao gồm SDK, browser, CLI và trường hợp body không replay được?
- [ ] Endpoint cũ không thực hiện side effect trước redirect; phía đích có chống trùng/retry an toàn?
- [ ] Đã cập nhật OpenAPI, tài liệu deprecation, SDK, monitoring và kế hoạch bỏ URI cũ?

## 17. Kết luận

**301 và 302** lần lượt diễn đạt chuyển URI lâu dài và tạm thời, nhưng vì tương thích lịch sử, client **có thể đổi POST thành GET**. **303** yêu cầu client đi tới URI khác để truy xuất representation của kết quả, thường dùng cho **POST/Redirect/GET**. **307 và 308** lần lượt là chuyển tạm và chuyển lâu dài với quy tắc **không được thay đổi phương thức** khi client tự theo redirect.

Trong REST API, chọn đúng status chỉ là bước đầu. Một thiết kế chuyển hướng đáng tin cậy phải bảo toàn **ý nghĩa nghiệp vụ, dữ liệu request khi cần, quyền truy cập, chính sách cache, tính idempotent và khả năng tương thích client**. Hãy kiểm thử cả response 3xx lẫn request thực tế tại đích để việc đổi URI không làm đổi sai ngữ nghĩa HTTP hoặc tạo lỗi khó phát hiện trong hệ thống tích hợp.
