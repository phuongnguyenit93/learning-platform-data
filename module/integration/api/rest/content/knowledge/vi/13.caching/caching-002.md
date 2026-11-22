# Khả năng cache theo phương thức, status và header

## 1. Mục tiêu bài học và bối cảnh

Trong module **INTEGRATION_API_REST**, thiết kế REST API phải kết hợp resource, URI, phương thức HTTP, mã trạng thái và hợp đồng dữ liệu rõ ràng. **Caching** là phần quan trọng của hợp đồng đó: một phản hồi có được lưu và dùng lại hay không phụ thuộc **đồng thời** vào phương thức request, trạng thái response, các header, ngữ cảnh xác thực và hành vi của thành phần cache.

Giả sử một dịch vụ bán hàng có ba endpoint:

- **GET /api/v1/products/p-101** trả thông tin sản phẩm công khai, ít thay đổi;
- **GET /api/v1/me/orders** trả đơn hàng riêng của người dùng đang đăng nhập;
- **POST /api/v1/orders** tạo đơn hàng mới và thay đổi trạng thái hệ thống.

Nếu chỉ nhìn thấy **HTTP 200** rồi cache mọi phản hồi, hệ thống có thể trả đơn hàng của người A cho người B. Nếu cache quá ít, mỗi lượt xem catalog lại truy vấn CSDL. Nếu cache quá lâu, người dùng có thể thấy giá hoặc tình trạng tồn kho đã cũ.

**Mục tiêu:** chọn được chính sách cache vừa đúng ngữ nghĩa HTTP vừa đáp ứng độ mới, bảo mật và chi phí hệ thống.

Sau bài học, bạn có thể:

1. Giải thích **cacheable**, **storable**, **fresh**, **stale**, **revalidation** và **invalidation**.
2. Phân tích khả năng cache theo **GET, HEAD, POST, PUT, PATCH, DELETE** và các phương thức khác.
3. Phân biệt những HTTP status có thể được **heuristically cached** với các status cần chỉ dẫn rõ.
4. Dùng đúng **Cache-Control**, **Expires**, **ETag**, **Last-Modified**, **If-None-Match**, **Vary**, **Age** và **Date**.
5. Thiết kế chính sách cho public cache, private browser cache, CDN, dữ liệu cá nhân và request có **Authorization**.
6. Hiểu vai trò của **304 Not Modified** và cách cache phản ứng với thao tác ghi.
7. Cấu hình response bằng Java/Spring Boot, mô tả OpenAPI và kiểm thử qua proxy/CDN.

**Phạm vi:** tập trung vào **HTTP caching** ở client, browser, proxy và CDN. Cache trong ứng dụng (ví dụ Redis hay Spring Cache) có thể tuân theo các quy tắc khác do lập trình viên tự định nghĩa; không được mặc định rằng header HTTP tự cấu hình mọi tầng cache nội bộ.

## 2. Ba câu hỏi cần trả lời trước khi dùng cache

Một HTTP cache thường cần quyết định:

**1. Có được lưu phản hồi này không?** Điều này phụ thuộc vào tính chất phương thức, mã trạng thái, chỉ thị Cache-Control, Authorization và quy tắc của cache.

**2. Phản hồi đã lưu có thể dùng lại cho request mới không?** Cần xem cache key (URI, phương thức, các chiều được khai báo qua Vary), freshness và các điều kiện dùng lại.

**3. Nếu đã stale thì xử lý ra sao?** Có thể gửi conditional request tới origin để **revalidate**, nhận **304 Not Modified**, hoặc tải một biểu diễn mới. Một số cơ chế stale có điều kiện cho phép dùng lại tạm thời, nhưng không phải lúc nào cũng được phép.

~~~mermaid
flowchart TD
    A[Client gửi HTTP request] --> B{Cache có response phù hợp?}
    B -- Không --> C[Forward tới origin]
    B -- Có --> D{Được phép dùng lại và vẫn fresh?}
    D -- Có --> E[Trả cached response]
    D -- Không --> F{Có thể revalidate?}
    F -- Không --> C
    F -- Có --> G[Conditional request tới origin]
    G --> H{304 Not Modified?}
    H -- Có --> I[Cập nhật metadata cache]
    I --> E
    H -- Không --> J[Nhận response mới theo quy tắc HTTP]
    J --> K[Đánh giá có thể lưu lại?]
    C --> K
    K --> L[Trả response tới client]
~~~

Sơ đồ biểu diễn **luồng phổ biến**, không bao quát mọi ngoại lệ của HTTP caching (ví dụ stale-while-revalidate, stale-if-error, range responses, cache directives của client).

### 2.1. Phân biệt năm khái niệm

| Thuật ngữ | Ý nghĩa | Điều dễ nhầm |
| --- | --- | --- |
| **Storable** | Cache được phép lưu response | Có thể lưu **không đồng nghĩa** được phép dùng lại ngay |
| **Fresh** | Response còn nằm trong thời hạn tươi theo quy tắc caching | Không bảo đảm dữ liệu origin chưa hề thay đổi |
| **Stale** | Freshness lifetime đã hết | Không có nghĩa tuyệt đối bị cấm dùng lại; tùy directive và hoàn cảnh |
| **Revalidation** | Hỏi origin xem biểu diễn đã lưu còn hợp lệ không | Có thể trả **304** thay vì tải lại toàn bộ body |
| **Invalidation** | Đánh dấu hoặc loại bỏ response lưu trữ khi có sự kiện làm nó không còn đáng tin | Không đồng nghĩa đã xóa dữ liệu khỏi DB |

Khi xem một header **Cache-Control: max-age=60**, hãy đọc đúng: cache có thể coi biểu diễn là fresh theo thời hạn **60 giây**, tùy các điều kiện còn lại; không phải origin cam kết dữ liệu tuyệt đối bất biến trong 60 giây.

## 3. Khả năng cache theo HTTP method

Phương thức là lớp điều kiện đầu tiên. Bảng này nói về **ngữ nghĩa tiêu chuẩn**, không phải bảo đảm rằng mọi cache thương mại sẽ triển khai đầy đủ.

| Phương thức | Ý nghĩa | Khả năng cache | Điểm cần lưu ý |
| --- | --- | --- | --- |
| **GET** | Lấy biểu diễn resource | **Có thể cache** theo quy tắc HTTP | Trường hợp phổ biến nhất; còn phụ thuộc status, header, auth và cache key |
| **HEAD** | Lấy metadata như GET, không có response content | **Có thể cache**; metadata HEAD có thể cập nhật hoặc vô hiệu hóa GET đã lưu | Không dùng HEAD như một bản sao JSON của GET |
| **POST** | Yêu cầu target resource xử lý content | **Có thể trong điều kiện đặc biệt**, không mặc định | RFC 9110 nêu explicit freshness và **Content-Location** bằng target URI; hỗ trợ thực tế hạn chế |
| **PUT** | Tạo/thay thế trạng thái target resource | Response PUT **không cacheable** | Thành công có thể invalidation những biểu diễn đã lưu liên quan |
| **DELETE** | Gỡ liên kết hiện tại của target resource | Response DELETE **không cacheable** | Thành công có thể invalidation target URI |
| **PATCH** | Áp dụng thay đổi một phần | Theo RFC 5789, response PATCH có thể cache với điều kiện đặc biệt; **không phải hành vi thông dụng** | PATCH cũng yêu cầu quản lý invalidation |
| **OPTIONS** | Hỏi tùy chọn giao tiếp | Response OPTIONS **không cacheable** theo ngữ nghĩa HTTP | Preflight CORS có cơ chế cache riêng của browser, không đồng nhất HTTP response cache |
| **TRACE** | Chẩn đoán vòng lặp HTTP | Response TRACE không cacheable | Thường tắt ở API công khai vì lý do bảo mật |

### 3.1. GET không có nghĩa mọi kết quả đều được cache

Hai GET dưới đây có cùng phương thức nhưng chính sách khác hẳn:

~~~http
GET /api/v1/products/p-101 HTTP/1.1
Host: api.example.test
~~~

~~~http
GET /api/v1/me/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

GET catalog công khai có thể dùng **public, max-age** và CDN. GET đơn hàng riêng cần **private/no-store**, hoặc chính sách riêng chặt chẽ bảo đảm dữ liệu cá nhân không bị lưu ở shared cache.

HTTP method **không tự thể hiện quyền truy cập**. “GET là safe” và “GET là cacheable” không đồng nghĩa “GET là public”.

### 3.2. POST có thể cache nhưng không phải đường mặc định

Theo RFC 9110, response POST có thể phù hợp để cache khi có **explicit freshness information** và **Content-Location** có giá trị bằng URI đích của POST. Khi đó response đã lưu có thể được tái sử dụng cho các request **GET/HEAD** tiếp theo tới URI đích trong những điều kiện được định nghĩa.

~~~http
POST /api/v1/reports/preview HTTP/1.1
Content-Type: application/json

{"period":"2026-10"}
~~~

~~~http
HTTP/1.1 200 OK
Content-Location: /api/v1/reports/preview
Cache-Control: max-age=60
Content-Type: application/json

{"summary":"..."}
~~~

**Không suy ra** rằng chỉ thêm max-age làm mọi POST được cache, hay một CDN sẽ tự biết cache key của request body. Hỗ trợ POST caching còn rất hạn chế trong triển khai thực tế; nếu muốn response preview được chia sẻ rộng rãi, thường nên tạo một **resource có URI ổn định** và cho GET tới resource đó khi nghiệp vụ phù hợp.

**Không biến POST tạo đơn thành cacheable chỉ để giảm tải**. Tính idempotent và chống tạo đơn trùng cần giải quyết bằng hợp đồng nghiệp vụ/Idempotency-Key, không dựa vào HTTP cache.

### 3.3. PATCH là ngoại lệ có điều kiện

RFC 5789 mô tả khả năng cache response PATCH khi response có freshness rõ ràng và **Content-Location khớp URI request**. Dù vậy, hệ sinh thái cache chủ yếu tối ưu GET/HEAD. Đối với API thường ngày, hãy thiết kế PATCH như một thao tác thay đổi trạng thái cần **invalidation/revalidation**, không giả định response PATCH được cache hay thay thế GET cũ tự động.

## 4. Khả năng cache theo HTTP status

Sau phương thức, mã trạng thái và chỉ dẫn cache tiếp tục quyết định. **Một số status được tiêu chuẩn cho phép heuristic caching**, tức cache có thể ước lượng thời gian fresh khi không có explicit freshness, nếu các điều kiện lưu trữ khác thỏa. Điều này **không có nghĩa** mọi response cùng status luôn được cache.

### 4.1. Các status có khả năng heuristic caching

Theo ngữ nghĩa HTTP hiện hành, những status thường được liệt kê là **heuristically cacheable**, trừ khi phương thức hoặc quy tắc khác cấm, gồm:

| Status | Ý nghĩa | Hệ quả với thiết kế |
| --- | --- | --- |
| **200 OK** | Thành công, thường có biểu diễn | GET 200 là ứng viên phổ biến cho cache |
| **203 Non-Authoritative Information** | Biểu diễn đã được biến đổi bởi intermediary | Có thể cache theo quy tắc, cần hiểu nguồn dữ liệu |
| **204 No Content** | Thành công không có response content | Có thể heuristic-cache trong ngữ cảnh hợp lệ, nhưng không có body |
| **206 Partial Content** | Một phần biểu diễn do Range | Cache cần hỗ trợ range và điều kiện hợp lệ |
| **300 Multiple Choices** | Có nhiều lựa chọn biểu diễn | Có thể cache khi thỏa các điều kiện |
| **301 Moved Permanently** | Redirect lâu dài | Cần thận trọng khi thay đổi URI |
| **308 Permanent Redirect** | Redirect lâu dài, giữ phương thức | Cần thận trọng khi thay đổi URL |
| **404 Not Found** | Không tìm thấy resource | **Negative caching** có thể giữ 404 một thời gian |
| **405 Method Not Allowed** | Phương thức không được hỗ trợ | Có thể heuristic-cache khi đáp ứng điều kiện |
| **410 Gone** | Resource được coi là đã không còn | Có thể cache thông tin gone |
| **414 URI Too Long** | URI quá dài | Có thể heuristic-cache trong điều kiện áp dụng |
| **501 Not Implemented** | Server không hỗ trợ chức năng/phương thức | Có thể heuristic-cache |

Đây là danh sách **khả năng heuristic theo status**, không phải danh sách “response 404 luôn được lưu 10 phút” hay “DELETE 204 được cache”: **DELETE response không cacheable theo ngữ nghĩa phương thức**, dù status 204 nằm trong danh sách trên.

### 4.2. Những status không nên mặc định cache

| Status | Hướng xử lý |
| --- | --- |
| **201 Created** | Không phải status heuristic mặc định; cần xét ngữ nghĩa phương thức và explicit policy, không coi là GET cacheable |
| **302 Found / 307 Temporary Redirect** | Chỉ cache khi có cơ sở freshness hợp lệ hoặc quy tắc cụ thể; không mặc định redirect tạm tồn tại lâu |
| **304 Not Modified** | Dùng để **revalidate/cập nhật metadata** của response có sẵn, không phải JSON resource độc lập |
| **401 Unauthorized** | Thường là lỗi liên quan xác thực; tránh chia sẻ, giữ header WWW-Authenticate |
| **403 Forbidden** | Có thể tiết lộ thông tin về quyền; nên dùng chính sách cache bảo thủ |
| **409 Conflict / 412 Precondition Failed** | Gắn trạng thái/phiên bản hiện tại, thường không muốn lưu lâu |
| **429 Too Many Requests** | Không heuristic-cache mặc định; có thể có Retry-After cho client |
| **500 Internal Server Error** | Không heuristic-cache mặc định; không làm CDN giữ lỗi thay vì trả dữ liệu mới |
| **502 / 503 / 504** | Lỗi proxy/service, không heuristic-cache mặc định; xem stale-if-error có điều kiện |

**Cảnh báo:** một status không nằm trong danh sách heuristic không tự động chứng minh response “không bao giờ storable”. Các chính sách explicit, phương thức và ngữ nghĩa có thể tạo tình huống đặc biệt. Khi thiết kế API, hãy công bố **chính sách cụ thể** thay vì dựa vào suy đoán mặc định của cache.

### 4.3. 404 và negative caching

Ví dụ client gọi:

~~~http
GET /api/v1/products/p-new HTTP/1.1
~~~

Server trả 404 vì sản phẩm chưa được đăng. Một thời gian sau sản phẩm được tạo, nhưng browser/CDN có thể tiếp tục trả **404 cũ** nếu đã lưu phản hồi đó theo chính sách hoặc heuristic freshness.

Với URI có khả năng được tạo mới trong thời gian ngắn, nên quyết định rõ:

~~~http
HTTP/1.1 404 Not Found
Cache-Control: no-store
Content-Type: application/problem+json

{"type":"about:blank","title":"Not Found","status":404}
~~~

Hoặc dùng một TTL âm rất ngắn nếu nghiệp vụ chấp nhận và bảo đảm không có dữ liệu cá nhân. Không để negative caching ngầm kéo dài làm onboarding, tạo mới hoặc khôi phục resource trông như thất bại.

## 5. Cache-Control: công cụ điều khiển quan trọng nhất

**Cache-Control** có thể xuất hiện ở **response** lẫn **request**. Các directive có ý nghĩa khác nhau; không được coi mọi từ như “no-cache”, “no-store”, “private” là từ đồng nghĩa.

### 5.1. Response directives chính

| Directive | Ý nghĩa | Use case |
| --- | --- | --- |
| **max-age=N** | Freshness lifetime tối đa N giây từ gốc tính tuổi theo HTTP | Catalog ít thay đổi |
| **s-maxage=N** | Freshness cho **shared cache**, ưu tiên hơn max-age tại shared cache | CDN có TTL khác browser |
| **public** | Cho phép shared cache lưu response trong những trường hợp được chỉ thị cho phép, nếu các điều kiện khác thỏa | Tài nguyên công khai |
| **private** | Shared cache không được lưu response; private cache có thể lưu nếu không có hạn chế khác | Dashboard riêng nếu chấp nhận browser cache |
| **no-cache** | Có thể lưu, nhưng **không được dùng lại nếu chưa revalidate thành công** | Nội dung cần xác nhận lại trước mỗi reuse |
| **no-store** | Cache không được lưu request/response tương ứng theo directive | Token, dữ liệu tài chính, profile nhạy cảm |
| **must-revalidate** | Khi stale, không được dùng lại nếu chưa revalidate thành công | Dữ liệu cần tránh phục vụ bản cũ khi offline |
| **proxy-revalidate** | Tương tự must-revalidate nhưng áp dụng shared cache | Quy tắc shared cache |
| **immutable** | Khi response còn fresh, client không cần revalidate chỉ vì thao tác reload thông thường | File asset có hash trong tên |
| **stale-while-revalidate=N** | Cho phép một khoảng dùng bản stale trong lúc revalidate bất đồng bộ | Catalog có thể chịu cũ tạm thời |
| **stale-if-error=N** | Cho phép dùng bản stale trong giới hạn khi gặp lỗi phù hợp | Dữ liệu công khai, ưu tiên khả dụng |

**Đặc biệt quan trọng:**

- **no-cache ≠ no-store**. no-cache **cho phép lưu**, nhưng phải validate trước khi dùng lại.
- **private ≠ no-store**. private cho phép private cache lưu, nhưng chặn shared cache.
- **max-age=0** thường làm response ngay lập tức stale, nhưng không tương đương yêu cầu không lưu.
- **public** không có nghĩa bypass quyền truy cập của API; việc mở shared cache phải được thiết kế chủ đích.
- **must-revalidate** không tự “xóa cache”; nó hạn chế reuse khi stale.

### 5.2. Ví dụ chính sách rõ ràng

**Public catalog:**

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=60, s-maxage=300
ETag: "product-p101-v9"
Content-Type: application/json

{"id":"p-101","name":"Bình giữ nhiệt"}
~~~

Browser có thể dùng freshness 60 giây; shared cache có thể dùng freshness 300 giây, nếu thỏa các điều kiện còn lại. Cần chấp nhận rằng có thời gian dữ liệu có thể cũ hoặc chủ động purge khi giá thay đổi.

**Profile riêng nhạy cảm:**

~~~http
HTTP/1.1 200 OK
Cache-Control: private, no-store
Content-Type: application/json

{"userId":"u-17","email":"user@example.test"}
~~~

Shared cache không được lưu; no-store cũng ngăn private HTTP cache lưu phản hồi. Điều này không tự ngăn ứng dụng hoặc hệ logging lưu dữ liệu; những tầng đó phải có chính sách riêng.

**Muốn lưu nhưng validate mỗi lần:**

~~~http
HTTP/1.1 200 OK
Cache-Control: private, no-cache
ETag: "settings-v12"
Content-Type: application/json

{"theme":"dark"}
~~~

Private cache có thể giữ biểu diễn rồi gửi conditional request trước khi dùng lại.

**Asset phiên bản bằng hash:**

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=31536000, immutable
Content-Type: application/javascript

// Nội dung asset đã có hash trong tên tệp
~~~

Nên dùng URI dạng **/assets/app.8f13c0.js**; khi nội dung đổi, tạo URL mới. Không áp dụng TTL rất dài cho URL không đổi mà nội dung thường xuyên thay đổi.

### 5.3. Header khác liên quan

| Header | Vai trò |
| --- | --- |
| **Expires** | Thời điểm hết fresh theo lịch; Cache-Control max-age/s-maxage thường ưu tiên khi cùng tồn tại |
| **Date** | Thời điểm origin tạo response; góp phần tính tuổi |
| **Age** | Tuổi ước lượng của response theo giây khi đi qua cache |
| **ETag** | Validator cho biểu diễn |
| **Last-Modified** | Validator theo thời điểm chỉnh sửa |
| **Vary** | Các trường request header ảnh hưởng lựa chọn biểu diễn |
| **Content-Location** | Cho biết URI liên quan tới biểu diễn; quan trọng ở những tình huống như POST caching |
| **Location** | Vị trí resource mới/redirect; không đồng nghĩa Content-Location |
| **Warning** | Một số cảnh báo lịch sử, không nên lấy làm cơ chế cache mới mặc định |
| **Pragma: no-cache** | Tương thích HTTP/1.0 ở request; không thay cho Cache-Control hiện đại |

Việc response có **Set-Cookie** không tự động là một lệnh “cấm cache” tuyệt đối theo mọi quy tắc HTTP. Dữ liệu cá nhân phải được bảo vệ bằng **Cache-Control và thiết kế quyền/cache key**, không chỉ dựa vào Set-Cookie.

## 6. Tính freshness và vai trò của Age

Một response có:

~~~http
HTTP/1.1 200 OK
Date: Wed, 18 Nov 2026 10:00:00 GMT
Cache-Control: public, max-age=60
Age: 40
~~~

Khi được nhận từ intermediary với **Age: 40**, response đã có tuổi ước lượng khoảng 40 giây. Nếu các yếu tố khác không thay đổi, nó chỉ còn khoảng **20 giây** fresh trong cửa sổ 60 giây, không được tính mới lại 60 giây từ lúc client nhận.

HTTP có thuật toán tính **current_age** phức tạp hơn phép trừ đơn giản (bao gồm Date, Age, thời gian mạng và thời gian resident). Ý chính: **Age không bị đặt lại thành 0 chỉ vì response vừa được chuyển qua một cache mới**.

Khi hết freshness, cache có thể:

- **Revalidate** bằng ETag/Last-Modified;
- lấy một 200 mới từ origin;
- trong những tình huống được cho phép, phục vụ stale trong giới hạn;
- không được phục vụ stale nếu có ràng buộc như must-revalidate mà chưa đáp ứng điều kiện.

### 6.1. Heuristic freshness có rủi ro gì?

Không phải mọi response có status cacheable đều có max-age/Expires. Một cache có thể dùng heuristic freshness theo các quy tắc được phép, đôi khi dựa vào Last-Modified.

Đối với API nghiệp vụ, nên **công bố freshness rõ** cho những resource được phép cache. Không đặt hy vọng rằng browser, CDN và proxy tình cờ chọn cùng heuristic.

## 7. Conditional GET và 304 Not Modified

Cache giữ một biểu diễn GET với ETag:

~~~http
GET /api/v1/products/p-101 HTTP/1.1
~~~

~~~http
HTTP/1.1 200 OK
ETag: "product-p101-v9"
Cache-Control: public, max-age=60
Content-Type: application/json

{"id":"p-101","name":"Bình giữ nhiệt","price":199000}
~~~

Khi cache muốn revalidate, nó có thể gửi:

~~~http
GET /api/v1/products/p-101 HTTP/1.1
If-None-Match: "product-p101-v9"
~~~

Nếu biểu diễn vẫn phù hợp, origin trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "product-p101-v9"
Cache-Control: public, max-age=60
Date: Wed, 18 Nov 2026 10:01:00 GMT
~~~

**304 không có response content của tài nguyên**. Cache dùng metadata phản hồi để cập nhật bản 200 đã lưu và có thể phục vụ lại body đó theo quy tắc. Nếu dữ liệu đổi, origin trả **200** với biểu diễn mới và ETag mới.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant K as HTTP cache
    participant O as Origin
    C->>K: GET /products/p-101
    K->>O: GET /products/p-101
    O-->>K: 200 + body + ETag "v9"
    K-->>C: 200 + body
    Note over K: Bản lưu hết freshness
    C->>K: GET /products/p-101
    K->>O: GET + If-None-Match "v9"
    O-->>K: 304 Not Modified
    K-->>C: 200 + body từ cache (đã revalidate)
~~~

Khi client tự gửi conditional GET và không có cached body để dùng, **client có thể nhận trực tiếp 304**. Khi cache có body và revalidate thay mặt client, client thường nhận biểu diễn được phục vụ từ cache. Cần phân biệt vai trò.

### 7.1. ETag mạnh, ETag yếu và Last-Modified

- **Strong ETag** dạng **"v9"** dùng khi cần phân biệt chặt biểu diễn.
- **Weak ETag** dạng **W/"v9"** có thể phù hợp cho cache validation khi hai biểu diễn tương đương về mặt ngữ nghĩa.
- **If-None-Match** dùng so sánh yếu cho GET/HEAD validation theo HTTP, nên weak validator có thể được sử dụng.
- **If-Match** dùng strong comparison cho điều kiện ghi, ví dụ chống lost update khi PUT/DELETE.
- **Last-Modified / If-Modified-Since** dùng mốc thời gian; độ chính xác có thể không đủ nếu cập nhật nhiều lần trong một giây hoặc timestamp không phản ánh đúng nguồn.

Khi có cả **If-None-Match** và **If-Modified-Since**, server cần áp dụng thứ tự ưu tiên theo HTTP; **If-None-Match** có ưu tiên hơn. Không tự phát minh phép so sánh “chỉ cần một trong hai khớp” nếu làm sai semantics.

**ETag phải gắn với representation**; nếu endpoint có biến thể theo ngôn ngữ, encoding hoặc quyền, validator và **Vary** phải nhất quán với các biến thể đó. Không nên dùng cùng ETag cho hai body khác nhau mà client có thể nhầm là một biểu diễn hợp lệ.

### 7.2. Phải kiểm tra quyền trước khi trả 304

Một GET có **If-None-Match** không phải đường tắt bỏ qua authentication/authorization. Với resource riêng, server phải kiểm tra người gọi **có quyền truy cập biểu diễn hiện tại** trước khi quyết định phản hồi 304.

Nếu user bị thu hồi quyền, phản hồi chỉ dựa trên ETag cũ có thể tiếp tục giúp cache/client giữ dữ liệu trái chính sách. Cần phối hợp **Cache-Control, revalidation, revoke policy và cơ chế cache invalidation**.

## 8. Vary và cache key: cùng URI chưa chắc cùng biểu diễn

Một cache thông thường cần phân biệt response theo phương thức, URI và các trường header được nêu trong **Vary**.

Ví dụ endpoint tài liệu hỗ trợ tiếng Việt và tiếng Anh:

~~~http
GET /api/v1/articles/a-1 HTTP/1.1
Accept-Language: vi
~~~

~~~http
HTTP/1.1 200 OK
Vary: Accept-Language
Cache-Control: public, max-age=120
Content-Language: vi
Content-Type: application/json

{"title":"Tổng quan API"}
~~~

Nếu client khác gửi **Accept-Language: en**, cache không được dùng một variant tiếng Việt khi không phù hợp lựa chọn biểu diễn.

Các giá trị Vary phổ biến:

| Vary | Vì sao cần |
| --- | --- |
| **Accept-Encoding** | Biểu diễn gzip, br hoặc không nén có thể khác |
| **Accept-Language** | Biểu diễn theo ngôn ngữ |
| **Accept** | JSON, XML hoặc media type khác |
| **Origin** | Có thể cần nếu server phản hồi chính sách CORS khác theo Origin; phải cấu hình đúng |

**Vary: \*** báo hiệu không thể dùng response đã lưu để thỏa request tiếp theo theo quy tắc matching thông thường.

### 8.1. Vary không phải cơ chế phân quyền

Chỉ đặt:

~~~http
Vary: Authorization
Cache-Control: public, max-age=300
~~~

không nên được coi là đủ để bảo vệ response chứa đơn hàng riêng. Shared cache có quy tắc đặc biệt với Authorization, nhưng cấu hình CDN hoặc cache ứng dụng có thể khác, và token thay đổi/thu hồi là bài toán riêng.

Với dữ liệu nhạy cảm, sử dụng chính sách **private/no-store** hoặc cơ chế shared caching đã được threat-model và kiểm thử rất chặt. Authorization và Vary không thay thế kiểm tra quyền tại origin.

### 8.2. Query string có tạo cache key khác không?

Về HTTP, target URI bao gồm query string, vì vậy:

~~~text
GET /products?category=books&page=1
GET /products?category=books&page=2
~~~

là hai target URI khác nhau. Tuy nhiên, một số CDN cho phép cấu hình bỏ qua, chuẩn hóa hoặc allowlist query parameters khi tạo cache key. Nếu cấu hình bỏ qua **page**, hai trang có thể bị trộn.

Cần kiểm thử thực tế:

- URI, query filter, page, sort và locale có được đưa đúng vào cache key?
- Có tham số tracking không ảnh hưởng biểu diễn nên được canonicalize hay bỏ qua?
- Có filter/tenant identifier nhạy cảm nào tuyệt đối không được dùng từ client để quyết định quyền?
- Có nguy cơ **cache poisoning** khi một header hoặc query ảnh hưởng nội dung nhưng bị loại khỏi key?

## 9. Request có Authorization: lưu cache thế nào?

**RFC 9111** có quy tắc riêng cho **shared cache** đối với response của request mang **Authorization**: shared cache không được dùng lại response như bình thường trừ khi có directive response cho phép một cách rõ ràng theo tiêu chuẩn (chẳng hạn **public, s-maxage, must-revalidate**, tùy điều kiện). Đây là lý do **không thể chỉ nhìn GET + 200 + max-age rồi kết luận CDN được lưu và chia sẻ**.

Ví dụ cần bảo vệ:

~~~http
GET /api/v1/me/orders HTTP/1.1
Authorization: Bearer <secret-token>
~~~

~~~http
HTTP/1.1 200 OK
Cache-Control: private, no-store
Content-Type: application/json

{"items":[{"id":"o-17","total":420000}]}
~~~

Quy tắc hợp đồng:

1. **Public content:** có thể chia sẻ qua CDN nếu resource thực sự công khai và không phụ thuộc người dùng.
2. **Personalized content:** tránh lưu shared cache; private cache chỉ được lưu nếu hợp đồng cho phép.
3. **Sensitive content:** thường dùng no-store để hạn chế lưu response trong HTTP cache.
4. **Có thay đổi quyền/tenant:** invalidation/revalidation phải xét membership và quyền hiện tại.
5. **Không biến credential thành cache key công khai:** không log Authorization header, không để secret xuất hiện trong URL hoặc metric label.

**Mấu chốt:** nếu public GET vẫn cho phép header Authorization nhưng response không phụ thuộc token, cần thiết kế rõ policy. Không thêm **public** chỉ để “bật CDN” cho một endpoint có body cá nhân hóa.

## 10. Cache invalidation sau PUT, POST, PATCH và DELETE

Cache không tự hiểu mọi thay đổi dữ liệu trong CSDL. Theo các quy tắc HTTP, khi một cache nhận **non-error response** cho một phương thức không an toàn, cache có trách nhiệm invalidation các response đã lưu đối với **target URI**, và có quy tắc bổ sung cho Location/Content-Location trong những điều kiện áp dụng.

Ví dụ:

~~~text
GET    /api/v1/products/p-101  -> 200, response được cache
PUT    /api/v1/products/p-101  -> 200, đổi dữ liệu
GET    /api/v1/products/p-101  -> cần phản ánh bản mới theo policy
~~~

Một cache nhìn thấy PUT thành công phải invalidation dữ liệu liên quan đến target URI theo quy tắc. Tuy nhiên, đó **không tự động giải quyết** mọi cache của:

- danh sách **GET /products?page=1**;
- kết quả tìm kiếm **GET /products?category=...**;
- thống kê **GET /catalog/summary**;
- dữ liệu lưu ở Redis, search index hoặc cache của ứng dụng khác.

### 10.1. Invalidation theo dữ liệu phụ thuộc

Với API thương mại điện tử:

~~~mermaid
flowchart LR
    W[PUT /products/p-101] --> DB[(DB)]
    DB --> EV[Outbox/event cập nhật]
    EV --> C1[Invalidate product detail]
    EV --> C2[Invalidate product lists]
    EV --> C3[Update search index]
    EV --> C4[Invalidate catalog summaries]
~~~

Một chiến lược đáng tin cần:

- xác định tài nguyên và biểu diễn nào phụ thuộc bản ghi vừa thay đổi;
- bảo đảm sự kiện cập nhật/invalidation không bị mất; có thể dùng transactional outbox trong hệ phân tán;
- giới hạn thời gian dữ liệu có thể stale;
- có cơ chế retry và quan sát lag;
- không coi response PUT/DELETE là một cache entry của GET;
- kiểm soát thứ tự/generation để một sự kiện cũ không ghi đè cache mới.

**Không hứa “PUT tự xóa tất cả cache”**. Invalidation theo HTTP nhìn thấy request/response và URI; cache phân tán khác có thể không nhận biết giao dịch đó.

### 10.2. DELETE và negative caching

Sau DELETE thành công, một GET có thể trả 404 và chính 404 này lại được cache nếu không có chỉ dẫn cấm. Nếu sau đó resource được restore/tạo lại cùng URI, cache có thể tiếp tục trả 404 cũ. Cần thiết kế TTL cho response not-found hoặc chủ động purge khi tái tạo resource.

### 10.3. POST tạo resource mới

Sau **POST /orders** tạo đơn và trả **201 Created**, có thể có:

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders/o-17
Content-Type: application/json

{"id":"o-17","status":"CREATED"}
~~~

Phản hồi POST này không tự động khiến mọi cache lập tức có **GET /orders/o-17** hay cập nhật **GET /orders**. Client có thể dùng Location để GET resource mới; hệ thống cần invalidation các danh sách liên quan nếu được cache. Phân biệt **Location** của resource mới với **Content-Location** dùng mô tả biểu diễn.

## 11. Những tình huống status + header dễ nhầm

### Tình huống A: 200 nhưng không được lưu

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json

{"balance":1500000}
~~~

HTTP 200 không thắng được **no-store**. Đây là response thành công nhưng không được HTTP cache lưu.

### Tình huống B: 404 có thể được cache

~~~http
HTTP/1.1 404 Not Found
Cache-Control: public, max-age=30
Content-Type: application/problem+json

{"type":"about:blank","title":"Not Found","status":404}
~~~

Response 404 cho tài nguyên công khai có thể cache 30 giây nếu thỏa các điều kiện khác. Với resource có thể được tạo mới, TTL 30 giây nghĩa là client có thể vẫn thấy 404 trong khoảng thời gian đó. Không dùng public caching cho 404 tiết lộ thông tin người dùng.

### Tình huống C: 301/308 còn hiệu lực lâu

~~~http
HTTP/1.1 308 Permanent Redirect
Location: /api/v2/products/p-101
Cache-Control: public, max-age=86400
~~~

Redirect lâu dài có thể được cache. Nếu vừa chuyển nhầm URI, client/CDN có thể tiếp tục dùng redirect cũ. Nên lập kế hoạch migration/rollback URI trước khi phát hành.

### Tình huống D: 304 không phải JSON rỗng của resource

~~~http
HTTP/1.1 304 Not Modified
ETag: "v9"
Cache-Control: public, max-age=60
~~~

304 dùng trong **conditional request**. Nó không mang bản sao JSON body mới và không nên được ứng dụng hiểu là “tài nguyên trả về null”.

### Tình huống E: 206 Range và cache một phần

~~~http
GET /videos/demo.mp4 HTTP/1.1
Range: bytes=0-999
~~~

~~~http
HTTP/1.1 206 Partial Content
Content-Range: bytes 0-999/10000
ETag: "video-v3"
Cache-Control: public, max-age=600
Content-Type: video/mp4

[1000 bytes dữ liệu]
~~~

Cache chỉ có thể xử lý các phần range theo quy tắc HTTP và khi hỗ trợ. Không coi 206 là status dành cho “một phần batch API thành công”.

### Tình huống F: 429 và Retry-After

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 10
Cache-Control: no-store
Content-Type: application/problem+json

{"type":"about:blank","title":"Too Many Requests","status":429}
~~~

**Retry-After** là gợi ý thời điểm thử lại, không tự cấp phép cache và không thay cho rate-limiting policy.

## 12. Ma trận quyết định cache cho một REST API

| Endpoint/phản hồi | Ví dụ policy | Lý do |
| --- | --- | --- |
| GET public product 200 | public, max-age=60, s-maxage=300, ETag | CDN giảm tải, chấp nhận dữ liệu có thể cũ |
| GET public category list 200 | public, max-age=30, Vary nếu có variant | Danh sách thay đổi, cần TTL ngắn và invalidation |
| GET personal orders 200 | private, no-store | Tránh lưu dữ liệu cá nhân ở HTTP cache |
| GET settings cá nhân 200 | private, no-cache, ETag | Có thể dùng private cache nhưng revalidate trước khi sử dụng |
| GET một resource chưa xuất bản 404 | no-store hoặc TTL rất ngắn theo chính sách | Tránh negative cache gây lỗi khi resource xuất hiện |
| POST create order 201 | no-store hoặc policy riêng | Không dùng HTTP cache làm idempotency |
| PUT update product 200/204 | Response thao tác không cacheable | Invalidate những biểu diễn liên quan |
| DELETE document 204 | Response thao tác không cacheable | Không dùng 204 này làm body của GET |
| GET public asset 200 | public, max-age dài, immutable khi URL có hash | Asset versioned ít thay đổi |
| Gateway 503/504 | no-store; có thể thiết kế stale-if-error riêng cho public GET | Tránh lưu lỗi và trả lâu |
| OPTIONS / preflight | Không cache như GET response thông thường | CORS preflight cache ở browser tuân cơ chế riêng |

**Không sao chép một policy cho tất cả endpoints.** Phân loại resource theo tính công khai, tần suất thay đổi, mức chấp nhận stale và tác động khi lộ dữ liệu.

## 13. Cấu hình cache cho Java/Spring Boot

Ví dụ dùng **Spring Boot 3/Spring Web**, Java 17+. Mã tập trung vào response headers; repository, service, security và mapping DTO cần được xây dựng thêm theo dự án.

### 13.1. GET catalog công khai với Cache-Control và ETag

~~~java
@RestController
@RequestMapping("/api/v1/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public ResponseEntity<ProductDto> getPublicProduct(@PathVariable UUID id) {
        ProductDto dto = service.findPublishedProduct(id);

        // Version phải thay đổi khi biểu diễn công khai thay đổi.
        String etag = "\"product-" + dto.id() + "-v" + dto.version() + "\"";

        return ResponseEntity.ok()
                .cacheControl(CacheControl.maxAge(Duration.ofSeconds(60))
                        .cachePublic())
                .eTag(etag)
                .body(dto);
    }
}
~~~

Đoạn mã trên có **max-age=60** và **public**. Nếu muốn **s-maxage=300**, có thể cấu hình header **Cache-Control** theo policy rõ ràng, thay vì giả định cachePublic() tự sinh s-maxage:

~~~java
return ResponseEntity.ok()
        .header(HttpHeaders.CACHE_CONTROL,
                "public, max-age=60, s-maxage=300")
        .eTag(etag)
        .body(dto);
~~~

**Lưu ý:**

- Hai đoạn mã đều là mẫu ở **cùng ngữ cảnh ví dụ**, không dùng cả hai return trong cùng một phương thức.
- ETag cần tương ứng với **biểu diễn**. Nếu version không đổi khi giá, tên hoặc trường body đổi, validator sai và client có thể nhận 304 không đúng.
- Ví dụ dùng UUID; các ID ngắn trong HTTP example chỉ mang tính minh họa.
- **@GetMapping** không tự kiểm tra quyền của tài nguyên riêng. Chỉ dùng public nếu endpoint thực sự trả dữ liệu công khai.
- Spring MVC có hỗ trợ conditional requests; triển khai ETag/revalidation nên dựa vào cơ chế đúng chuẩn của framework hoặc kiểm tra điều kiện đầy đủ, không tự so chuỗi If-None-Match một cách giản lược rồi trả 304.

### 13.2. GET dữ liệu cá nhân: tránh lưu HTTP cache

~~~java
@RestController
@RequestMapping("/api/v1/me")
public class MyOrdersController {

    private final OrderService service;

    public MyOrdersController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/orders")
    public ResponseEntity<List<OrderSummaryDto>> myOrders(
            Authentication authentication) {

        // Service phải xác định principal và kiểm tra quyền đọc.
        List<OrderSummaryDto> orders = service.forPrincipal(authentication);

        return ResponseEntity.ok()
                .header(HttpHeaders.CACHE_CONTROL, "private, no-store")
                .body(orders);
    }
}
~~~

**Không** lấy userId từ query string để xác định chủ dữ liệu khi API mang ngữ nghĩa **/me**. Nếu có cache trong service/repository, nó vẫn cần tenant/user scope, retention và invalidation riêng; header HTTP không tự cấu hình Redis hay JPA cache.

### 13.3. Conditional GET có kiểm soát

Một luồng kiểm tra hợp lệ:

1. Xác thực và phân quyền (đối với private resource).
2. Xác định biểu diễn và ETag đúng theo variant.
3. Kiểm tra precondition **If-None-Match** theo semantics HTTP.
4. Nếu khớp và điều kiện phù hợp, trả 304 **không có response content** với header cần thiết.
5. Nếu không khớp, trả 200 cùng body/ETag và policy cache tương ứng.

Với Spring MVC, có thể dùng **ServletWebRequest.checkNotModified(...)** hoặc cơ chế conditional response của framework. Khi tự cài đặt, phải xử lý đúng weak comparison, nhiều entity tag, If-None-Match: *, precedence với If-Modified-Since và trạng thái resource. Không để phần xử lý 304 vượt qua authorization.

### 13.4. Thao tác cập nhật và invalidation

~~~java
@PutMapping("/{id}")
public ResponseEntity<Void> update(
        @PathVariable UUID id,
        @Valid @RequestBody UpdateProductRequest request) {

    service.updateProduct(id, request); // Kiểm tra quyền và version trong service

    // Thao tác PUT không dùng response này để cache một GET representation.
    return ResponseEntity.noContent().build();
}
~~~

Sau commit, hệ thống có thể cần invalidation CDN cho **/products/{id}**, danh sách liên quan và search index. Controller trả 204 không có nghĩa mọi cache độc lập đã được purge. Thiết kế đúng độ trễ nhất quán theo yêu cầu nghiệp vụ và quan sát lỗi invalidation.

## 14. CDN, reverse proxy và cache nội bộ: tránh nhầm phạm vi

Một kiến trúc REST phổ biến:

~~~mermaid
flowchart LR
    C[Browser / Mobile] --> P[CDN / Reverse proxy]
    P --> G[API Gateway]
    G --> A[Spring REST API]
    A --> R[(Redis/application cache)]
    A --> DB[(Database)]
~~~

Mỗi thành phần có cơ chế riêng:

| Tầng | Cần cấu hình/kiểm chứng |
| --- | --- |
| Browser HTTP cache | Response Cache-Control, ETag, Vary, ngữ cảnh private |
| CDN / reverse proxy | Path/method/status policy, query handling, Authorization/cookies, cache key, TTL, purge |
| API gateway | Có thể cache response theo plugin/filter; cần test bảo mật và invalidation |
| Redis/application cache | Key tenant/user/filter, TTL, quyền, locking, cache stampede |
| Database query cache/materialized view | Tính đúng của dữ liệu, refresh, scope truy cập |

**Không giả định một header Cache-Control gửi từ Spring luôn được mọi tầng tuân theo.** Một số CDN có rule ghi đè TTL, bỏ query, bypass Origin Cache-Control hoặc cache lỗi theo chính sách riêng. Cần xem cấu hình thực và test end-to-end.

### 14.1. Cache stampede và thundering herd

Khi hàng nghìn client đồng thời làm ETag revalidation hoặc miss cùng URI sau TTL, origin có thể bị dội tải. Cân nhắc:

- request coalescing/single-flight ở cache;
- TTL có jitter khi thích hợp;
- stale-while-revalidate cho dữ liệu **công khai** chịu được độ trễ;
- giới hạn truy vấn và timeout ở origin;
- prewarming cho resource nóng, kèm chỉ số hit/miss.

Không áp dụng stale-while-revalidate cho dữ liệu nhạy cảm hoặc thông tin đòi hỏi nhất quán chặt nếu chưa được phép theo hợp đồng.

## 15. OpenAPI 3.1: ghi rõ caching trong hợp đồng API

Caching thường được diễn đạt bằng **response headers** và description trong OpenAPI, thay vì chỉ đặt một flag mơ hồ tên cacheable.

~~~yaml
openapi: 3.1.0
info:
  title: Product API
  version: 1.0.0
paths:
  /api/v1/products/{id}:
    get:
      operationId: getProduct
      summary: Xem sản phẩm công khai
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            format: uuid
        - name: If-None-Match
          in: header
          required: false
          schema:
            type: string
          description: Conditional GET theo ETag của biểu diễn trước
      responses:
        '200':
          description: Biểu diễn sản phẩm hiện tại
          headers:
            Cache-Control:
              schema:
                type: string
              description: 'Ví dụ: public, max-age=60, s-maxage=300'
            ETag:
              schema:
                type: string
              description: Validator cho biểu diễn công khai
            Vary:
              schema:
                type: string
              description: Chỉ khai báo khi response có variant theo header
          content:
            application/json:
              schema:
                type: object
                required: [id, name, price]
                properties:
                  id:
                    type: string
                    format: uuid
                  name:
                    type: string
                  price:
                    type: number
        '304':
          description: Biểu diễn chưa thay đổi theo conditional GET
          headers:
            ETag:
              schema:
                type: string
            Cache-Control:
              schema:
                type: string
        '404':
          description: Không tìm thấy sản phẩm
  /api/v1/me/orders:
    get:
      operationId: listMyOrders
      summary: Đơn hàng của principal hiện tại
      security:
        - bearerAuth: []
      responses:
        '200':
          description: Danh sách đơn của người gọi
          headers:
            Cache-Control:
              schema:
                type: string
              description: 'private, no-store'
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: string
                    total:
                      type: number
        '401':
          description: Chưa xác thực hợp lệ
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
~~~

OpenAPI chỉ **mô tả** expected headers/status. Nó không tự bật caching, không bảo đảm CDN giữ đúng TTL, và không xử lý invalidation. Khi production, bổ sung schema lỗi theo Problem Details và ví dụ 404/401 phù hợp với policy.

## 16. Kiểm thử caching theo method, status và header

Bộ kiểm thử cần có **HTTP client, proxy/CDN cấu hình gần thực tế và origin có trạng thái có thể thay đổi**. Chỉ test annotation Spring trong unit test không chứng minh cấu hình cache ở edge hoạt động đúng.

### 16.1. Ma trận kiểm thử

| ID | Kịch bản | Kết quả cần xác minh |
| --- | --- | --- |
| C01 | GET public 200 max-age=60 | Response có thể dùng lại trong freshness, đúng cache key |
| C02 | GET public với ETag | Hết TTL → conditional GET → 304 → dùng lại body hợp lệ |
| C03 | GET public đổi version | Revalidate trả 200 mới, không dùng body cũ sau khi hết điều kiện |
| C04 | GET private no-store | Không có cache hit shared/browser theo chính sách |
| C05 | GET có Authorization | Shared cache không lưu/dùng lại sai quyền |
| C06 | User A và B cùng gọi /me/orders | Không bao giờ trả dữ liệu A cho B |
| C07 | Vary: Accept-Language | Header vi/en nhận đúng biến thể |
| C08 | Vary: Accept-Encoding | Cache không trộn gzip/br/identity sai |
| C09 | Query page=1 và page=2 | CDN cache key không trộn trang |
| C10 | DELETE thành công sau GET đã cache | Target URI được invalidation phù hợp |
| C11 | PUT cập nhật sản phẩm | Detail và list/search cache phản ánh policy invalidation |
| C12 | POST tạo resource | Không lấy response POST làm bằng chứng GET cùng URL đã được cập nhật |
| C13 | GET 404 rồi tạo mới resource | Negative caching không kéo dài ngoài hợp đồng |
| C14 | 301/308 redirect | TTL và Location đúng, kế hoạch thay URI được tính đến |
| C15 | 206 Range | Cache đáp đúng byte range và Content-Range |
| C16 | 304 | Không có response content; client/cache xử lý validator đúng |
| C17 | 429 có Retry-After | Không mặc định cache như 200; client áp backoff |
| C18 | 503/504 | CDN không lưu lỗi quá chính sách; stale-if-error chỉ áp dụng khi được phép |
| C19 | Token/role bị thu hồi | Không còn đọc dữ liệu trái quyền qua cache/304 |
| C20 | Header do client gửi bị sửa | Không thể cache poisoning qua Origin/Vary/Host/query |
| C21 | HEAD cùng URI GET | Metadata phù hợp, không trả body; quy tắc cập nhật cache đúng |
| C22 | Concurrent cache miss | Không gây stampede vượt giới hạn origin |
| C23 | Cache-Control no-cache | Cache có thể lưu nhưng phải revalidate trước reuse |
| C24 | Cache-Control no-store | Không có lưu response theo chính sách |
| C25 | max-age=60 kèm Age=40 | Thời gian fresh còn lại phản ánh Age, không tính mới toàn bộ |

### 16.2. Kiểm thử 304 end-to-end

~~~bash
# 1. Lấy biểu diễn và ETag từ môi trường thử.
curl -i https://api.example.test/api/v1/products/11111111-1111-4111-8111-111111111111

# 2. Yêu cầu có điều kiện với ETag vừa nhận.
curl -i \
  -H 'If-None-Match: "product-11111111-1111-4111-8111-111111111111-v9"' \
  https://api.example.test/api/v1/products/11111111-1111-4111-8111-111111111111

# 3. Thay dữ liệu thử, dùng lại ETag cũ:
# origin cần trả 200 với representation/validator mới nếu đã thay đổi.
~~~

Giá trị ETag trong lệnh hai là **ví dụ**, không được đoán trong test thực tế; phải lấy đúng từ response trước. URL **api.example.test** chỉ là hostname minh họa.

Khi kiểm thử qua cache, có thể thêm quan sát response headers do cache phát ra (chẳng hạn **Age**, **Via** hoặc header vendor-specific). Tuy nhiên, không có header debug chung nào đảm bảo mọi CDN đều bộc lộ hit/miss, nên cần cả metrics/log của cache và origin.

### 16.3. Test bảo mật bắt buộc

Tạo user A, user B và các resource riêng. Gửi GET của A, rồi GET của B cùng URI mà response phụ thuộc principal. Kiểm tra:

- B không nhận body hoặc ETag của A nếu không có quyền;
- response không được shared-cache tái sử dụng sai;
- Vary/cache key không bỏ sót điều kiện cần;
- 304 không trả cho principal đã bị thu hồi quyền;
- log và metric không lưu token;
- cache invalidation có hiệu lực khi membership/policy đổi.

Một chỉ số cache hit ratio cao **không có giá trị** nếu cache đang phục vụ dữ liệu sai người dùng.

## 17. Bài thực hành: chính sách cache cho API thương mại điện tử

**Bối cảnh:** một nền tảng có các API:

1. **GET /products/{id}** – sản phẩm công khai; giá cập nhật vài lần một ngày.
2. **GET /products?category=...&page=...** – danh sách công khai, thay đổi khi thêm/xóa sản phẩm.
3. **GET /me/orders** – đơn hàng của người đăng nhập.
4. **GET /me/preferences** – cấu hình giao diện riêng; thay đổi không thường xuyên.
5. **POST /orders** – tạo đơn hàng.
6. **PUT /products/{id}** – thay đổi thông tin sản phẩm, chỉ admin được làm.
7. **DELETE /products/{id}** – gỡ sản phẩm khỏi catalog.
8. **GET /products/{id}** có thể trả 404 khi sản phẩm chưa phát hành.

Doanh nghiệp muốn giảm truy vấn CSDL nhưng không chấp nhận lộ đơn hàng và muốn sản phẩm mới xuất hiện trong danh sách nhanh sau phát hành.

### Nhiệm vụ A – Ma trận chính sách

Với mỗi endpoint, ghi: method, status điển hình, khả năng cache, Cache-Control, ETag/Vary nếu cần, TTL chấp nhận và lý do. Giải thích rõ vì sao **POST/PUT/DELETE** không thể được cache như GET thông thường.

### Nhiệm vụ B – Invalidation

Vẽ sơ đồ khi admin sửa sản phẩm:

~~~text
PUT product -> DB commit -> event/outbox -> invalidation
                                  -> detail cache
                                  -> category list cache
                                  -> search index
~~~

Nêu cách xử lý event lỗi, thứ tự cập nhật và trường hợp CDN không nhìn thấy request PUT vì có một service nội bộ thực hiện thay đổi.

### Nhiệm vụ C – Bảo mật

Thiết kế chính sách cho /me/orders và /me/preferences. Giải thích sự khác nhau giữa **private**, **no-cache** và **no-store**, đồng thời mô tả cách ngăn user A nhận dữ liệu B qua shared cache.

### Nhiệm vụ D – Kiểm thử

Thiết kế ít nhất tám ca test, bắt buộc có ETag/304, Age, Vary, Authorization, 404 negative caching, invalidation sau PUT và dữ liệu cá nhân.

### 17.1. Hướng giải tham khảo

| Resource | Policy đề xuất | Ghi chú |
| --- | --- | --- |
| GET product 200 | public, max-age=60, s-maxage=300, ETag | Cache công khai có TTL hữu hạn |
| GET product list 200 | public, max-age=30; key gồm filter/page/sort | Cần invalidation khi danh mục thay đổi |
| GET /me/orders 200 | private, no-store | Tránh lưu nội dung cá nhân |
| GET /me/preferences 200 | private, no-cache, ETag | Private cache lưu nhưng validate trước reuse |
| POST /orders 201 | no-store | Idempotency cho tạo đơn là bài toán riêng |
| PUT product 204 | Response PUT không cacheable | Invalidate detail/list |
| DELETE product 204 | Response DELETE không cacheable | Invalidate detail/list/search |
| GET product 404 | no-store hoặc TTL ngắn có chủ đích | Tránh giữ lỗi khi sản phẩm vừa được đăng |

Đây là **một phương án mẫu**, chưa phải số TTL chuẩn cho mọi hệ thống. Khi dùng CDN, phải xác minh **s-maxage**, key theo query, tác động của cookie/auth, chính sách cached errors và cơ chế purge.

Một câu trả lời đạt yêu cầu sẽ chỉ ra **rủi ro stale chấp nhận được**, cách bảo vệ dữ liệu cá nhân và cách test end-to-end, thay vì chỉ liệt kê các header.

## 18. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Cho rằng GET luôn cacheable | Lộ nội dung cá nhân | Xét auth, header, status và quyền |
| Cho rằng chỉ 200 cacheable | Bỏ qua 404/301/308 và negative caching | Xem cả status heuristic và policy |
| Cho rằng 204 từ DELETE cacheable vì 204 heuristic | Nhầm status với phương thức | Xét method + status cùng lúc |
| Dùng no-cache để cấm lưu | Cache vẫn có thể lưu | Dùng no-store khi thực sự cần cấm lưu |
| Dùng private để cấm mọi cache | Browser/private cache vẫn có thể lưu | Dùng no-store nếu cần |
| Dùng max-age=0 thay cho no-store | Response vẫn được lưu, có thể revalidate | Chọn directive đúng mục tiêu |
| Cache POST tạo đơn mà không xét ngữ nghĩa | Gây hành vi sai, không giải quyết tạo trùng | Dùng idempotency contract đúng |
| Trả 304 trước khi auth | Tái sử dụng dữ liệu sau khi quyền bị thu hồi | Kiểm tra quyền trước validation |
| Dùng ETag không đổi dù JSON đổi | Client nhận dữ liệu cũ | Validator gắn với representation |
| Quên Vary khi có nhiều variant | Trộn ngôn ngữ/encoding | Vary đúng chiều thay đổi body |
| Chỉ đặt Vary: Authorization để bảo vệ dữ liệu riêng | Shared cache vẫn có thể cấu hình sai | Private/no-store và threat model |
| CDN bỏ qua query trong cache key | Trộn trang/filter | Kiểm tra cấu hình query cache key |
| Chỉ invalidate detail, quên list/search | Danh sách vẫn cũ | Dependency invalidation và outbox |
| Cache 404 quá lâu | Resource mới tạo vẫn “không tồn tại” | Short TTL/no-store hoặc purge |
| Dùng 206 cho batch partial success | Sai nghĩa Range | 206 chỉ dành cho partial representation |
| Coi 429 và Retry-After là cache TTL | Client/cache xử lý sai | Tách retry policy và cache policy |
| Đánh giá cache chỉ bằng hit ratio | Có thể nhanh nhưng sai quyền | Kiểm thử bảo mật và freshness |

## 19. Checklist tổng kết

- [ ] Tôi phân biệt **storable**, **fresh**, **stale**, **revalidation**, **invalidation**.
- [ ] Tôi xét **phương thức, status, header, auth và cache key** cùng nhau.
- [ ] Tôi biết GET/HEAD thường cacheable, còn PUT/DELETE responses không cacheable.
- [ ] Tôi không coi response POST là cacheable mặc định.
- [ ] Tôi nêu được những status heuristic như 200, 301, 308, 404 và 410.
- [ ] Tôi biết 304 dùng để revalidate và không có response content.
- [ ] Tôi phân biệt **no-cache**, **no-store**, **private**, **public**, **max-age**, **s-maxage**.
- [ ] Tôi hiểu Age/Date và không đặt lại TTL chỉ vì response vừa tới cache mới.
- [ ] Tôi biết dùng ETag/If-None-Match và Last-Modified đúng ngữ nghĩa.
- [ ] Tôi biết Vary theo variant và tránh cache key trộn user, tenant hoặc query.
- [ ] Tôi kiểm tra quyền trước khi trả 304 cho private resources.
- [ ] Tôi xử lý Authorization và không để CDN cache sai dữ liệu cá nhân.
- [ ] Tôi có chiến lược invalidation detail, list, search sau ghi/xóa.
- [ ] Tôi kiểm soát negative caching của 404 và redirect caching.
- [ ] Tôi có OpenAPI, kiểm thử HTTP/CDN và quan sát hit/miss, age, stale, revalidation.
- [ ] Tôi đã nêu giới hạn HTTP caching khác với cache trong ứng dụng.

**Ghi nhớ:** **Khả năng cache không được quyết định bởi một dấu hiệu đơn lẻ.** GET + 200 chưa đủ, 404 không mặc nhiên “không cache”, còn no-cache không có nghĩa no-store. Thiết kế API REST đúng phải phối hợp **ngữ nghĩa phương thức, status, header, phạm vi quyền, freshness, revalidation và invalidation** để cân bằng hiệu năng với tính đúng đắn và bảo mật.

### Tài liệu chuẩn để tra cứu

- **RFC 9110 – HTTP Semantics:** thuộc tính phương thức, khả năng cache theo method/status, Content-Location, ETag và conditional requests.
- **RFC 9111 – HTTP Caching:** lưu cache, cache keys, freshness, validation, invalidation, Authorization và Cache-Control directives.
- **RFC 5789 – PATCH Method for HTTP:** ngữ nghĩa PATCH và điều kiện cache đặc thù.
- **RFC 5861 – HTTP Cache-Control Extensions:** stale-while-revalidate và stale-if-error.
- **RFC 8246 – HTTP Immutable Responses:** immutable directive.
- **OpenAPI Specification 3.1:** mô tả HTTP headers, responses và security.
- **Spring Framework / Spring Boot:** ResponseEntity, CacheControl, hỗ trợ conditional requests với ETag.
