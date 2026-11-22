# Bộ nhớ đệm riêng, dùng chung và nơi có thể lưu phản hồi

## 1. Một phản hồi REST API có thể được lưu ở đâu?

Giả sử REST API của một cửa hàng có hai endpoint:

- **GET /catalog/products/P-100**: mô tả sản phẩm công khai, giống nhau đối với mọi khách hàng.
- **GET /me/orders**: danh sách đơn hàng riêng của người đã đăng nhập.

Để giảm độ trễ và tải máy chủ, đội phát triển bật cache trên CDN. Một ngày, khách hàng A mở lịch sử đơn hàng; ngay sau đó khách hàng B cũng gọi **GET /me/orders** và nhận nhầm dữ liệu của A. Nguyên nhân có thể là CDN đã lưu phản hồi cá nhân hóa và dùng chung bản sao cho những request có cùng URI.

**Cache không chỉ là tối ưu hiệu năng. Cache là quyết định nơi giữ bản sao dữ liệu, ai có thể tái sử dụng bản sao và điều kiện nào khiến bản sao còn hợp lệ.** Với API chứa dữ liệu riêng, đó còn là một quyết định bảo mật.

Trong module **INTEGRATION_API_REST**, chủ đề này nối tiếp cách thiết kế resource, URI, phương thức HTTP, mã trạng thái, hợp đồng phản hồi, xác thực/phân quyền, phân trang và kiểm thử bằng Java/Spring. Người thiết kế API cần hiểu **HTTP cache** ở client, proxy, CDN và các lớp ứng dụng; chọn chính sách theo mức độ riêng tư, độ mới và tính nhất quán của dữ liệu.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **private cache** và **shared cache** theo ngữ nghĩa HTTP.
2. Vẽ được tuyến request/response và chỉ ra những nơi có thể lưu một representation.
3. Giải thích đúng **Cache-Control: private, public, no-store, no-cache, max-age, s-maxage, must-revalidate** cùng các validator **ETag/Last-Modified**.
4. Phân biệt **quyền lưu (store)**, **quyền tái sử dụng (reuse)**, **độ tươi (freshness)** và **tái xác nhận (revalidation)**.
5. Thiết kế cache cho nội dung công khai, dữ liệu cá nhân, endpoint có Authorization và ứng dụng đa tenant.
6. Hiểu vai trò của **Vary**, khóa cache, invalidation và điều kiện khi dữ liệu thay đổi.
7. Cấu hình ví dụ trong Spring MVC, mô tả OpenAPI và kiểm thử qua browser/gateway/CDN.

## 2. Private cache, shared cache và origin server

### 2.1. Private cache là gì?

Theo ngữ nghĩa HTTP, **private cache** là cache dành riêng cho một người dùng hoặc user agent nhất định, thường là **bộ nhớ đệm của trình duyệt**. Nó có thể lưu và tái sử dụng representation theo các chỉ thị cache của response. Private cache **không mặc định là dữ liệu riêng tư được mã hóa**: người có quyền sử dụng cùng browser profile, thiết bị hoặc hồ sơ trình duyệt có thể có khả năng truy cập những dữ liệu đã được lưu.

Một số nơi có thể đóng vai trò private cache:

- HTTP disk/memory cache của browser trong một browser profile.
- Cache của HTTP client dành riêng cho một người dùng, khi thư viện hỗ trợ lưu response theo HTTP semantics.
- Một cache được thiết kế cô lập theo danh tính người dùng và tuân thủ đúng chính sách HTTP.

Khái niệm **private** ở đây nói về **phạm vi sử dụng của cache**, không hứa rằng mọi bản sao nằm trên đĩa đã được bảo vệ tuyệt đối khỏi hệ điều hành, extension, backup thiết bị hoặc người dùng cùng tài khoản máy.

### 2.2. Shared cache là gì?

**Shared cache** là cache có thể dùng chung để phục vụ yêu cầu từ **nhiều người dùng hoặc user agents**. Ví dụ:

- Forward proxy cache của một tổ chức.
- Reverse proxy/HTTP accelerator phía trước ứng dụng.
- CDN edge cache trước origin.
- Gateway có cơ chế **HTTP response caching** chia sẻ giữa nhiều người gọi.

Điểm khác biệt là **một bản sao có khả năng được phục vụ cho nhiều client**. Vì vậy, shared cache phải tuân thủ ràng buộc chặt chẽ về dữ liệu riêng, header Authorization, Vary, điều kiện cacheability và chính sách của hệ thống.

**Origin server** là máy chủ chịu trách nhiệm tạo representation của tài nguyên. Origin có thể được đặt phía sau nhiều lớp cache, nhưng không phải mọi request đều đi đến origin nếu bản sao ở cache đủ điều kiện tái sử dụng.

### 2.3. Sơ đồ tuyến đường phản hồi

~~~mermaid
flowchart LR
    B["Trình duyệt / HTTP Client"] <-->|"HTTP"| P["Forward Proxy (nếu có)"]
    P <-->|"HTTP"| CDN["CDN / Reverse Proxy"]
    CDN <-->|"HTTP"| GW["API Gateway"]
    GW <-->|"HTTP"| APP["REST API / Origin"]
    APP --> DB[("Database")]
    APP --> REDIS[("Application Data Cache")]
    B -. "Private HTTP cache" .-> BC[("Browser cache")]
    P -. "Shared HTTP cache" .-> PC[("Proxy cache")]
    CDN -. "Shared HTTP cache" .-> CC[("Edge cache")]
~~~

Trong thực tế, tuyến đường có thể **không có forward proxy**, hoặc gateway đồng thời là reverse proxy/CDN. Mục đích sơ đồ là nhận diện **ranh giới lưu/tái sử dụng response**; không ngụ ý request buộc phải đi qua mọi hộp.

### 2.4. Phân biệt HTTP response cache với cache dữ liệu ứng dụng

| Loại cache | Đối tượng thường lưu | Có tự tuân thủ Cache-Control HTTP không? | Ví dụ |
|---|---|---|---|
| Browser HTTP cache | Response đã được nhận | Khi hoạt động như cache HTTP, có | Bộ nhớ đệm GET /products |
| Forward/reverse HTTP proxy | Response HTTP | Phải tuân thủ HTTP semantics, trừ cơ chế cấu hình đặc thù cần được hiểu rõ | Proxy, CDN, gateway response cache |
| Application memory cache | DTO, entity, kết quả tính toán | **Không tự động** | Caffeine, ConcurrentHashMap |
| Distributed application cache | Key-value nghiệp vụ | **Không tự động** | Redis lưu product summary |
| Database buffer/page cache | Trang dữ liệu và kết quả nội bộ DB | **Không** | Bộ nhớ đệm của DB |
| Service Worker/Cache API | Request/Response do script kiểm soát | Có **mô hình và chính sách ứng dụng riêng**, không được suy rằng mọi lưu trữ đều do HTTP cache quyết định | Offline-first PWA |

**Cache-Control: no-store** là chỉ thị cho **caches tuân thủ HTTP**; nó không phải lệnh có thể tự động xóa mọi bản sao trong Redis, log, analytics hoặc storage. Nếu ứng dụng cố tình sao chép payload nhạy cảm sang một cache nghiệp vụ riêng, ứng dụng vẫn phải tự áp dụng quyền, TTL, xóa và chính sách dữ liệu phù hợp.

## 3. Bốn quyết định khác nhau: lưu, dùng lại, kiểm tra, vô hiệu hóa

Một response đi qua cache có thể trải qua bốn bước:

1. **Store:** cache có được phép ghi bản sao response này hay không?
2. **Reuse:** bản sao đã lưu có được phép dùng cho request hiện tại hay không?
3. **Revalidate:** khi bản sao cũ hoặc có chỉ thị kiểm tra lại, cache có cần hỏi origin để xác nhận không?
4. **Invalidate:** sau khi tài nguyên thay đổi, các bản sao cũ được đánh dấu không còn hợp lệ hoặc loại bỏ bằng cơ chế nào?

Sự phân biệt này rất quan trọng:

- **no-store** hạn chế **lưu** bản sao trong cache HTTP.
- **no-cache** không có nghĩa “không được lưu”; nó yêu cầu **kiểm tra lại với origin trước khi tái sử dụng** theo điều kiện của chỉ thị.
- **max-age=60** cho biết thời hạn freshness; không phải lời hứa sau 60 giây bản sao bị xóa khỏi đĩa.
- **ETag/If-None-Match** cho phép kiểm tra bản sao mà không phải tải lại toàn bộ nội dung nếu chưa thay đổi.
- **Invalidation** giải quyết bản sao bị lỗi thời khi origin đổi trạng thái, có thể thông qua expiration, revalidation hoặc cơ chế purge chủ động.

~~~mermaid
flowchart TD
    REQ["GET request"] --> FOUND{"Có response phù hợp trong cache?"}
    FOUND -->|Không| ORIGIN["Chuyển request tới origin"]
    FOUND -->|Có| STORE{"Có quyền tái sử dụng?"}
    STORE -->|"Có và còn fresh"| HIT["Phục vụ từ cache"]
    STORE -->|"Cần xác nhận lại"| COND["Conditional request tới origin"]
    STORE -->|"Không"| ORIGIN
    COND --> RES{"Origin trả gì?"}
    RES -->|"304 Not Modified"| REFRESH["Cập nhật metadata, dùng body đã lưu"]
    RES -->|"200 với representation mới"| REPLACE["Dùng representation mới; lưu nếu đủ điều kiện"]
    ORIGIN --> RESP["Nhận response"]
    RESP --> MAYSTORE{"Response có được phép lưu?"}
    MAYSTORE -->|Có| SAVE["Lưu theo chính sách"]
    MAYSTORE -->|Không| RETURN["Chuyển response, không lưu"]
    SAVE --> RETURN
    HIT --> RETURN
    REFRESH --> RETURN
    REPLACE --> RETURN
~~~

Sơ đồ giản lược: HTTP còn có quy tắc về phương thức, status, header Authorization, Vary, Age, validator, các quy tắc freshness theo RFC và cache implementation cụ thể. **Cache hit** không chỉ dựa vào URI: phải khớp phương thức, khóa cache và các trường biến thiên theo Vary cùng điều kiện bảo mật.

## 4. Header Cache-Control quyết định điều gì?

**Cache-Control** là header HTTP mang các chỉ thị cache. Cùng một tên header có thể xuất hiện ở **request** hoặc **response**, nhưng ý nghĩa từng chỉ thị phụ thuộc vị trí.

### 4.1. Những response directives cần nhớ

| Response directive | Tác dụng chính | Những lưu ý quan trọng |
|---|---|---|
| **private** | Chỉ cho phép cache riêng lưu response; shared cache **không được lưu** response chứa chỉ thị private không có trường định danh | Không tự yêu cầu browser xóa cache, không tự mã hóa dữ liệu |
| **public** | Cho phép shared cache lưu một response nếu các điều kiện HTTP còn lại cho phép | Nguy hiểm nếu payload cá nhân hóa; còn có tác động đến quy tắc khi request có Authorization |
| **no-store** | Cache tuân thủ HTTP **không được lưu** request/response theo phạm vi áp dụng | Nên dùng khi nội dung rất nhạy cảm hoặc không muốn giữ bản sao HTTP |
| **no-cache** | Cho phép lưu, nhưng phải **xác nhận với origin trước mỗi lần tái sử dụng** theo quy tắc chỉ thị | **Không đồng nghĩa no-store** |
| **max-age=N** | Response được xem là fresh tối đa N giây từ thời điểm được tính theo HTTP | Áp dụng cho cả private và shared cache nếu không có quy tắc ưu tiên khác |
| **s-maxage=N** | Chỉ cho **shared cache**; ưu tiên hơn max-age và Expires đối với shared cache | Không dùng bừa cho response riêng tư |
| **must-revalidate** | Khi response stale, cache không được dùng lại khi chưa revalidate thành công | Không phải chỉ thị “cấm lưu”; có tác động đặc biệt tới shared cache khi Authorization hiện diện |
| **proxy-revalidate** | Tương tự must-revalidate nhưng chủ yếu áp dụng cho shared cache | Không thay thế private/no-store |
| **immutable** | Gợi ý response khó thay đổi trong thời gian fresh | Hữu ích với tài nguyên bất biến có version trong URL |

Ngoài ra còn có **Expires**, **Date**, **Age**, **ETag**, **Last-Modified**, **Vary** và các header khác ảnh hưởng đến quyết định cache. Tùy trường hợp, server có thể dùng nhiều chỉ thị phối hợp nhưng cần tránh mâu thuẫn.

### 4.2. no-store và no-cache: khác nhau ở đâu?

Hai phản hồi:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json

{"accountBalance": 1000000}
~~~

~~~http
HTTP/1.1 200 OK
Cache-Control: no-cache
ETag: "balance-v17"
Content-Type: application/json

{"accountBalance": 1000000}
~~~

**no-store**: cache HTTP tuân thủ không lưu bản sao. **no-cache**: bản sao có thể được lưu, nhưng trước khi phục vụ lại cần kiểm tra tại origin; nếu origin trả **304 Not Modified**, cache có thể tái sử dụng body đã lưu theo quy tắc.

Đối với số dư tài khoản nhạy cảm, **no-store** thường là lựa chọn bảo thủ. Với một biểu diễn có thể lưu nhưng phải luôn kiểm tra trước khi dùng, **no-cache** kèm ETag có thể phù hợp. Không dùng no-cache với kỳ vọng mọi dữ liệu đã không tồn tại trên thiết bị.

### 4.3. private không có nghĩa luôn fresh

~~~http
HTTP/1.1 200 OK
Cache-Control: private, max-age=60
Content-Type: application/json

{"displayName": "Lan"}
~~~

Response này cho phép **private cache** lưu và, nếu thỏa các điều kiện HTTP khác, dùng lại khi còn fresh trong khoảng thời gian được tính từ freshness lifetime. Shared cache **không được lưu** nó do chỉ thị **private**. Sau khi stale, browser có thể tái xác nhận hoặc tải lại.

Nếu dữ liệu như lịch sử thanh toán hoặc hồ sơ y tế đòi hỏi hạn chế lưu trữ, private **chưa đủ**: cân nhắc **no-store** và chính sách cache ứng dụng riêng.

### 4.4. public và s-maxage cho tài nguyên thật sự dùng chung

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=60, s-maxage=600
ETag: "catalog-v5"
Content-Type: application/json

{"id":"P-100","name":"Bút bi","price":12000}
~~~

Một lựa chọn thiết kế được phép cho nội dung công khai: browser coi thời hạn fresh tối đa 60 giây; shared cache như CDN có thể coi là fresh tối đa 600 giây theo **s-maxage**, tùy Age và các điều kiện còn lại. **Giá/sản phẩm phải thực sự giống nhau cho mọi client có cùng cache key**; nếu giá phụ thuộc người dùng hoặc hợp đồng, không được công khai cache key chung chỉ vì URI giống nhau.

Lưu ý rằng chỉ thị **public**, **s-maxage** và trong một số trường hợp **must-revalidate** có thể cho phép shared cache lưu/tái sử dụng response của request chứa **Authorization** theo các quy tắc RFC 9111. Vì vậy, **“endpoint cần token” không tự đảm bảo response sẽ không bị cache dùng chung**. Hãy chọn chính sách rõ ràng dựa trên nội dung, không dựa vào cảm giác an toàn do có header Authorization.

### 4.5. max-age=0 không đồng nghĩa xóa bản sao

~~~http
Cache-Control: max-age=0, must-revalidate
~~~

Response có thể được lưu, nhưng thường trở thành stale ngay và cần revalidate trước khi dùng lại khi các quy tắc áp dụng yêu cầu như vậy. Nó khác với **no-store**. Tương tự, response **no-cache** có thể được lưu và dùng sau khi xác nhận thành công.

### 4.6. Request directives và response directives

Client có thể gửi:

~~~http
GET /catalog/products/P-100 HTTP/1.1
Cache-Control: no-cache
~~~

Đây là **request directive** yêu cầu các cache trên đường đi kiểm tra lại trước khi dùng response đã lưu. Nó **không tự sửa chính sách Cache-Control mà origin trả cho các lần sau**, cũng không khiến server xóa mọi bản sao.

Việc client gửi **Cache-Control: no-store** trong request và origin gửi no-store trong response là hai chỉ thị ở hai phía, có phạm vi tác động theo HTTP. Trong API, **server phải tự chịu trách nhiệm phát response directives đúng** cho dữ liệu riêng tư; không thể yêu cầu mọi client nhớ tự gửi no-cache/no-store để bảo vệ dữ liệu.

## 5. Cache key, Vary và điều kiện phục vụ đúng representation

### 5.1. Cùng URI không nhất thiết cùng response

Một HTTP cache thường tìm bản sao theo **request method và target URI**, rồi áp dụng các điều kiện khớp bổ sung, bao gồm các header liệt kê ở **Vary**. Khi ứng dụng chủ động cấu hình CDN key theo nhiều thuộc tính, chính sách đó cũng phải bảo vệ đúng các biến thể.

Ví dụ:

~~~http
GET /articles/intro HTTP/1.1
Accept-Language: vi
~~~

và:

~~~http
GET /articles/intro HTTP/1.1
Accept-Language: en
~~~

Nếu nội dung khác nhau theo ngôn ngữ, origin có thể trả:

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=300
Vary: Accept-Language
Content-Type: application/json

{"title": "Giới thiệu"}
~~~

**Vary: Accept-Language** cho biết cache cần xét giá trị trường request tương ứng khi chọn representation được lưu. Nếu bỏ Vary, cache có thể trả tiếng Việt cho client yêu cầu tiếng Anh hoặc ngược lại.

Những chiều biến thiên thường gặp:

| Khác biệt response | Điều cần xét |
|---|---|
| Ngôn ngữ | Vary: Accept-Language nếu thực sự được thương lượng qua header |
| Định dạng | Vary: Accept nếu media type khác nhau theo Accept |
| Content-Encoding | Vary: Accept-Encoding khi cần phân biệt representation nén |
| Phiên bản/feature flag | Thiết kế versioning hoặc khóa cache phù hợp, kiểm soát rollout |
| Tenant hoặc nhóm người dùng | Mặc định tránh shared cache nếu payload riêng; chỉ cache chung khi thiết kế isolation có chứng cứ |
| Query filter/page/sort | URI/query là thành phần nhận diện request; CDN custom normalization không được làm mất tham số có ảnh hưởng |
| Quyền truy cập | Cần authorization ở mọi đường đi; không xem Vary là thay thế chính sách quyền |

**Vary** mô tả những request header có ảnh hưởng đến representation, nhưng **không phải cơ chế xác thực hay phân quyền**. Đừng cố làm endpoint cá nhân trở nên an toàn chỉ bằng **Vary: Authorization** rồi bỏ **private/no-store**. Một sai sót trong cache key, gateway rule hoặc sự thay đổi quyền vẫn có thể khiến dữ liệu bị phục vụ sai.

### 5.2. Query parameter cũng là một phần của yêu cầu

Ví dụ:

~~~text
GET /products?category=books&page=0
GET /products?category=books&page=1
GET /products?category=toys&page=0
~~~

Đây là những URI query khác nhau và thường cần những entry cache khác nhau. Các CDN có thể cho phép cấu hình **bỏ qua, chọn lọc hoặc sắp xếp query parameter** khi tạo khóa cache. Cấu hình này chỉ an toàn nếu các tham số bị bỏ qua **không ảnh hưởng** tới response và không tham gia kiểm tra quyền.

Một cấu hình nguy hiểm:

~~~text
Origin:
  GET /invoices?tenantId=A  -> hóa đơn của A
  GET /invoices?tenantId=B  -> hóa đơn của B

CDN cache key sai:
  chỉ dùng path /invoices, bỏ qua tenantId
~~~

Khi đó dù origin có authorization đúng, CDN có thể phục vụ entry của A cho B nếu response bị cache ở shared layer. Cách khắc phục ưu tiên **không cache dùng chung dữ liệu hóa đơn**, xác thực quyền tại origin, và rà soát khóa cache ở mọi lớp.

### 5.3. Cookie và Set-Cookie không tự bảo vệ bản sao

Không được tin rằng:

- Request có **Cookie** thì shared cache sẽ tự động không lưu.
- Response có **Set-Cookie** thì mọi cache tự động hiểu đó là thông tin riêng và không lưu.
- Endpoint dùng HTTPS thì không thể cache.
- URL chỉ có thể bị gọi bởi người đã đăng nhập thì payload mặc nhiên không bị cache ở CDN.

Các giả định trên **không phải cơ chế bảo vệ đủ theo HTTP**. Nếu response chứa dữ liệu định danh hoặc quyền lợi của user, cần **Cache-Control phù hợp**, cấu hình CDN/gateway đúng và kiểm thử thực tế trên tuyến có xác thực. Đừng đưa secret hoặc session token vào body công khai để dựa vào cache chống rò.

### 5.4. Cache poisoning, cache deception và nguồn dữ liệu không đáng tin

Hai lớp rủi ro thường gặp:

1. **Cache poisoning:** request được kẻ tấn công tạo ra làm origin sinh response khác thường nhưng cache lưu dưới khóa dùng chung với request hợp lệ, khiến người dùng khác nhận dữ liệu/redirect/header không mong muốn.
2. **Cache deception:** một đường dẫn trông như tài nguyên tĩnh hoặc khớp rule CDN nhưng thực tế được ứng dụng trả nội dung riêng tư; cache có thể lưu/cho phép truy cập không đúng.

Để giảm rủi ro:

- Chuẩn hóa và tài liệu hóa những header/query/path thực sự ảnh hưởng response.
- Không cấu hình CDN “cache mọi GET” nếu ứng dụng có endpoint người dùng, session hoặc tenant.
- Không để hostname/path extension đơn thuần quyết định rằng nội dung luôn công khai.
- Kiểm tra phản hồi với cookie/Authorization khác nhau và các tham số bị CDN bỏ qua.
- Không phản chiếu những giá trị client kiểm soát vào response có thể lưu chung mà không kiểm tra.

## 6. Authorization, session và nội dung cá nhân hóa

### 6.1. Request có Authorization được cache thế nào?

HTTP áp dụng quy tắc đặc biệt đối với **shared cache** khi request có trường **Authorization**. Theo RFC 9111, shared cache không được dùng cached response cho request có Authorization **trừ khi response có chỉ thị cụ thể cho phép điều đó**, chẳng hạn **public**, **s-maxage**, hoặc **must-revalidate** với các điều kiện liên quan.

Vì vậy:

- Đừng mặc định request có bearer token là “không bao giờ cache được”.
- Đừng gắn **public** hoặc **s-maxage** vào dữ liệu riêng chỉ vì muốn tăng cache hit.
- Đừng dùng **must-revalidate** như một ranh giới cách ly: nó xử lý tái xác nhận khi stale, **không thay thế private/no-store**.
- Dữ liệu cá nhân thường nên có **private** nếu cho phép browser cache, hoặc **no-store** nếu không muốn HTTP cache lưu.
- Với tài nguyên công khai mà endpoint vẫn chấp nhận token, cần bảo đảm representation thực sự **không bị cá nhân hóa** trước khi cho phép shared cache.

### 6.2. Ví dụ chính sách cho từng loại endpoint

| Endpoint | Tính chất dữ liệu | Chính sách khởi đầu tham khảo | Lý do |
|---|---|---|---|
| **GET /catalog/products/P-100** | Công khai, giống nhau cho mọi người | **public, max-age=60, s-maxage=300** | Cho phép browser/CDN lưu theo thời hạn khác nhau |
| **GET /me/profile** | Cá nhân hóa, không quá nhạy cảm theo giả định | **private, max-age=30** hoặc **no-store** theo chính sách | Không cho shared cache lưu, cân bằng hiệu năng và quyền riêng tư |
| **GET /me/payment-methods** | Dữ liệu tài chính/cá nhân nhạy cảm | **no-store** | Tránh lưu bản sao trong HTTP caches tuân thủ |
| **GET /accounts/{id}/balance** | Số dư theo quyền truy cập | **no-store** hoặc chính sách hạn chế nghiêm | Dữ liệu nhạy cảm, yêu cầu độ mới cao |
| **GET /reports/public-monthly** | Báo cáo công khai, có version | **public, max-age=300** và ETag | Giảm tải origin khi nhiều client đọc |
| **GET /tenants/{tenantId}/invoices** | Dữ liệu tenant riêng | **private** hoặc **no-store** | Tránh cross-tenant leak |
| **POST /orders** | Thao tác tạo đơn, response theo phiên làm việc | Thường **no-store** | Tránh lưu response nhạy cảm; không đồng nhất với idempotency |
| **GET /assets/app.7f3a9.js** | Asset bất biến có hash trong tên | **public, max-age=31536000, immutable** khi quy trình version đúng | Có thể lưu lâu vì URL đổi khi nội dung đổi |

Đây là **gợi ý khởi đầu**, không phải tiêu chuẩn bắt buộc cho mọi hệ thống. Độ nhạy cảm, hợp đồng, dữ liệu thay đổi, quy trình logout, thiết bị chia sẻ, điều kiện tuân thủ và khả năng purge đều có thể khiến chính sách thay đổi.

### 6.3. Logout, đổi quyền và cache riêng

Giả sử người dùng A đăng nhập trên một máy chung, mở **GET /me/profile** có **private, max-age=300**, sau đó logout. Chỉ thị **private** ngăn shared caches lưu, nhưng browser profile vẫn có thể giữ response trong private HTTP cache cho tới khi chính sách reuse/invalidation được áp dụng.

Biện pháp:

- Với thông tin rất nhạy cảm, chọn **no-store** ngay từ đầu.
- Tránh dùng chung browser profile hoặc session không được tách trên thiết bị nhiều người.
- Ứng dụng có thể thực hiện quy trình xóa dữ liệu phía client, cache ứng dụng, IndexedDB/Service Worker khi logout; đừng coi chỉ thị HTTP là cơ chế tự xóa mọi nơi.
- Đổi quyền/tenant cần ảnh hưởng ngay tới authorization và khả năng truy cập dữ liệu. Không dựa vào bản sao cũ chưa được xác thực lại để cho phép hành động mới.

Các hệ thống có thể dùng cơ chế **Clear-Site-Data** ở những browser hỗ trợ, nhưng cần hiểu phạm vi, tác động và hỗ trợ thực tế; không xem đó là thay thế cho thiết kế no-store và chính sách lưu trữ cục bộ.

### 6.4. Shared response phải thực sự tương đương với mọi người sử dụng nó

Ví dụ **GET /catalog/products/P-100** có thể tưởng là công khai, nhưng nội dung sau lại phụ thuộc:

- Giá theo khách hàng doanh nghiệp đã đăng nhập.
- Khuyến mãi theo region, currency hoặc group.
- Tồn kho theo kho giao hàng.
- Trường “favorite: true” chỉ người dùng A mới có.

Khi đó không thể cache toàn bộ response bằng một khóa URI dùng chung. Các hướng thiết kế gồm:

1. **Tách dữ liệu công khai và cá nhân hóa**: GET /catalog/products/P-100 cho thuộc tính chung, GET /me/favorites/P-100 cho trạng thái của user.
2. Dùng **Cache-Control: private/no-store** cho response tổng hợp cá nhân hóa.
3. Nếu cần chia sẻ theo phân khúc, thiết kế khóa cache và ranh giới quyền rõ ràng, có đo kiểm rò dữ liệu và quy trình đổi quyền/segment; tránh mở rộng phân đoạn tùy tiện theo mọi user.

Tách tài nguyên theo **mức chia sẻ dữ liệu** thường giúp cache hiệu quả mà dễ kiểm chứng hơn việc tạo cache key khổng lồ chứa mọi thuộc tính cá nhân.

## 7. Freshness, Age, Expires và các giá trị thời gian

### 7.1. Freshness là gì?

Một bản sao **fresh** có thể được tái sử dụng mà không cần truy vấn lại origin trong những điều kiện HTTP cho phép. Bản sao **stale** thường cần revalidation hoặc không được dùng lại, trừ các trường hợp giao thức/chỉ thị cho phép dùng stale.

Ví dụ:

~~~http
HTTP/1.1 200 OK
Date: Wed, 18 Nov 2026 10:00:00 GMT
Cache-Control: public, max-age=120
ETag: "catalog-v12"
Content-Type: application/json

{"id":"P-100","price":12000}
~~~

Nếu cache nhận response và đã qua 30 giây của tuổi hiệu lực, nó có thể tái sử dụng bản sao khi còn fresh và không gặp điều kiện khác yêu cầu kiểm tra lại. Khi hết thời hạn, nó có thể gửi conditional request để lấy nội dung mới hoặc xác nhận bản cũ.

**Đừng lấy thời gian hiện tại trừ thời điểm response đến rồi coi luôn là tuổi response chính xác.** HTTP có cơ chế tính **current_age** từ Date, Age, thời gian truyền và thời gian lưu. Một response chuyển qua nhiều cache đã có tuổi trước khi tới browser.

### 7.2. Age và Date trong shared cache

Response qua CDN có thể chứa:

~~~http
HTTP/1.1 200 OK
Date: Wed, 18 Nov 2026 10:00:00 GMT
Age: 75
Cache-Control: public, max-age=120
Content-Type: application/json
~~~

**Age: 75** biểu thị ước lượng số giây từ khi response được origin tạo/tái xác nhận theo quy tắc HTTP. Cache downstream cần tính tuổi đó khi quyết định còn fresh bao lâu; không được coi như vừa mới nhận bản sao.

### 7.3. Expires và các chỉ thị ưu tiên

Origin có thể dùng **Expires** để đưa thời điểm hết freshness bằng ngày HTTP. Khi có **Cache-Control: max-age**, chỉ thị tương ứng được ưu tiên hơn Expires; với **shared cache**, **s-maxage** có thể ưu tiên hơn các chỉ thị thời hạn chung. Sử dụng Cache-Control với thời hạn rõ thường dễ quản lý hơn phụ thuộc đồng hồ của nhiều thành phần.

### 7.4. Nếu không có Cache-Control thì sao?

**Không có Cache-Control không đồng nghĩa “không cache được”.** Với những phương thức/status được phép, HTTP cache có thể áp dụng **heuristic freshness** theo quy tắc RFC 9111, thường dựa vào Last-Modified hoặc thông tin khác. Một số status như **200**, **301**, **404** có thể được cache theo quy tắc phù hợp.

Điểm dễ bất ngờ: **404 của một tài nguyên chưa tồn tại** có thể bị cache; khi resource mới được tạo, người dùng vẫn thấy 404 trong một khoảng thời gian nếu cache chưa tái xác nhận. Cần thiết kế caching của 404 và invalidation theo yêu cầu nghiệp vụ thay vì chỉ cấu hình cho response 200.

## 8. Revalidation: ETag, Last-Modified và 304

### 8.1. Tại sao cần validator?

Cache thường có body cũ. Khi freshness hết, thay vì tải lại toàn bộ JSON hoặc file, cache có thể gửi một **conditional request** đến origin bằng validator.

Ví dụ:

~~~http
GET /catalog/products/P-100 HTTP/1.1
If-None-Match: "product-v7"
~~~

Nếu representation đã chọn **chưa thay đổi**, origin có thể trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "product-v7"
Cache-Control: public, max-age=60, s-maxage=300
~~~

**304 không chứa response content của representation.** Cache cập nhật metadata phù hợp, sau đó tái sử dụng body đã lưu nếu đủ điều kiện. Nếu representation thay đổi, origin trả **200 OK** với body và ETag mới.

### 8.2. ETag và Last-Modified

| Validator | Ý nghĩa | Điểm lưu ý |
|---|---|---|
| **ETag** | Opaque entity tag do server phát cho một representation | Có strong/weak; không yêu cầu client hiểu cách tính |
| **Last-Modified** | Thời điểm sửa gần nhất của representation | Độ phân giải thời gian có thể không phát hiện mọi thay đổi nhanh |
| **If-None-Match** | Kiểm tra validator theo ETag | Thường được ưu tiên khi client có cả If-None-Match và If-Modified-Since |
| **If-Modified-Since** | Kiểm tra thay đổi theo thời gian | Thích hợp khi có Last-Modified tin cậy |

Ví dụ response:

~~~http
HTTP/1.1 200 OK
ETag: W/"catalog-list-v7"
Last-Modified: Wed, 18 Nov 2026 09:30:00 GMT
Cache-Control: public, max-age=0, must-revalidate
~~~

**Weak ETag** với tiền tố **W/** có thể phục vụ revalidation GET khi biểu diễn được xem là tương đương về ngữ nghĩa dù byte không đồng nhất. Với các thao tác cập nhật đồng thời cần so khớp mạnh (**If-Match**), không thể coi weak ETag là thay thế cho strong validator.

### 8.3. ETag phải gắn với đúng representation

Một response có thể thay đổi theo:

- Sản phẩm hoặc phiên bản dữ liệu.
- Query filter, sort, page và size.
- Ngôn ngữ hoặc Content-Encoding.
- Phạm vi quyền, tenant hoặc người dùng.

Nếu origin trả chung ETag cho **hai body khác nhau**, cache có thể revalidate sai. Khi thiết kế ETag cho collection query, phải tính đến những yếu tố làm **body đã chọn** thay đổi. Cách tính validator phải chính xác và không vô tình tạo áp lực truy vấn DB lớn hơn lợi ích caching.

### 8.4. 304 không nói rằng tài nguyên rỗng

Một **304 Not Modified** nghĩa là cache có thể tiếp tục dùng representation đã lưu khi các điều kiện giao thức được đáp ứng. Nó **không phải** cách biểu diễn một collection rỗng. Nếu collection rỗng, origin có thể trả **200** với **[]** và validator; lần GET có điều kiện tiếp theo mới có khả năng trả 304 nếu representation chưa đổi.

### 8.5. Cache và cập nhật bằng POST/PUT/PATCH/DELETE

Khi origin chấp nhận request thay đổi trạng thái như PUT/PATCH/DELETE, những HTTP caches trên đường đi có quy tắc invalidation cho URI liên quan trong những điều kiện xác định; tuy nhiên **không thể dựa vào điều đó để bảo đảm mọi CDN, browser, Redis và client app cùng được xóa entry**. Các lớp dữ liệu ứng dụng cần invalidation riêng khi có thay đổi nghiệp vụ.

Đối với cache collection **GET /products** và member **GET /products/P-100**, việc cập nhật một product có thể làm thay đổi cả **member và nhiều danh sách lọc**, nhưng cache không tự hiểu mối liên hệ nghiệp vụ giữa tất cả các URI. Cần TTL hợp lý, versioning, sự kiện invalidation hoặc CDN purge theo cơ chế được hỗ trợ.

## 9. Nơi cache thực sự hoạt động trên một đường API

### 9.1. Browser HTTP cache

Browser có thể lưu GET response theo cache semantics và tái sử dụng nếu điều kiện cho phép. Nó thường hỗ trợ các chỉ thị và conditional requests, nhưng hành vi cụ thể có thể bị ảnh hưởng bởi profile, chế độ duyệt, DevTools, service worker và chính sách browser.

Với ứng dụng SPA:

~~~text
Web UI
  -> fetch("/catalog/products/P-100")
  -> Browser HTTP cache (nếu có entry hợp lệ)
  -> Network / CDN / Origin khi cần
~~~

**State cache của thư viện frontend** như TanStack Query hoặc SWR là một lớp khác. Response có **Cache-Control: no-store** không tự động ngăn ứng dụng tự giữ dữ liệu đã giải mã trong JavaScript memory. Đội frontend phải quản lý vòng đời dữ liệu khi logout, đổi tenant, đổi tài khoản, hoặc thay đổi authorization.

### 9.2. CDN edge cache

CDN thường được dùng để lưu nội dung công khai gần người dùng:

- **Ưu điểm:** giảm round-trip đến origin, băng thông, CPU và tải DB.
- **Trách nhiệm:** tuân thủ chính sách cacheability, Authorization, khóa cache, Vary, purge và TTL.
- **Rủi ro:** cấu hình “cache everything” hoặc override origin Cache-Control không tương thích với dữ liệu cá nhân; key thiếu query/cookie/đặc tính representation; cache của nhiều địa điểm có thời điểm cập nhật khác nhau.

Một CDN có thể có **nhiều edge POP và nhiều cấp cache**. Purge/invalidation có thể không đồng thời tuyệt đối; cần biết cam kết thực tế của nhà cung cấp, quan sát và yêu cầu độ mới của ứng dụng.

### 9.3. Reverse proxy hoặc API gateway

Một gateway có thể:

- **Không cache response** và chỉ xử lý auth, rate limit, routing.
- Có module **response caching** lưu theo route/query/key.
- Chỉ cache khi upstream trả đúng directive.
- Bị cấu hình **ghi đè** Cache-Control từ origin.

Do đó không thể suy rằng “đã có API gateway nghĩa là response được cache”. Cũng không thể suy rằng origin trả **private** sẽ luôn được tôn trọng nếu gateway đang được cấu hình làm **application-specific cache** không tuân thủ chính sách HTTP. Cần rà soát sản phẩm, phiên bản, rule và test end-to-end.

### 9.4. Forward proxy doanh nghiệp

Một số mạng có proxy chia sẻ giữa nhiều người dùng. Proxy hợp chuẩn HTTP phải tôn trọng **private/no-store**, Authorization restrictions và các điều kiện liên quan. Tuy nhiên, mạng doanh nghiệp còn có các thiết bị kiểm soát/capture ngoài vai trò HTTP cache; điều này càng nhấn mạnh rằng **Cache-Control là chính sách cache của HTTP**, không thay thế mã hóa và quy định dữ liệu của tổ chức.

### 9.5. Backend Redis / Caffeine / database caching

Ví dụ:

~~~java
@Cacheable(cacheNames = "productSummary", key = "#productId")
public ProductSummary loadProduct(String productId) {
    return repository.getSummary(productId);
}
~~~

Spring Cache **@Cacheable** ở đây là **cache kết quả phương thức ứng dụng**, không phải header Cache-Control của HTTP. Muốn dùng Redis/Caffeine cho product summary, cần định nghĩa TTL, invalidation, tránh stale data và tên khóa phù hợp.

Nếu dữ liệu phụ thuộc tenant, ví dụ một cùng productId tồn tại trong các tenant khác nhau, khóa như **#productId** là thiếu an toàn; cần gắn **tenant ID đã được xác thực** hoặc cô lập cache theo tenant. Đừng coi việc HTTP response trả **Cache-Control: private** có khả năng tự sửa khóa cache của Redis.

Một repository cache có thể phục vụ origin để tạo response **no-store**; hai quyết định khác nhau không nhất thiết mâu thuẫn nếu dữ liệu nội bộ được quản lý đúng quyền và vòng đời.

## 10. Các phương thức HTTP và khả năng lưu response

### 10.1. GET/HEAD là trường hợp phổ biến

HTTP caching chủ yếu áp dụng cho các representation được truy xuất bằng **GET** và đôi khi **HEAD**. Tuy nhiên, **không phải mọi response GET đều được phép lưu**, và **không phải chỉ GET mới có quy tắc caching**.

Một response được lưu phải đáp ứng **tập hợp điều kiện của RFC 9111**, chẳng hạn: phương thức/status phù hợp, không có no-store/giới hạn ngăn lưu, tuân thủ Authorization, có cơ chế xác định cacheability/freshness và các điều kiện cache tương ứng.

Đối với **POST**, HTTP có các điều kiện riêng để một số response có thể được tái sử dụng (trong những trường hợp được mô tả bằng thông tin freshness và Content-Location phù hợp), nhưng nhiều cache thực tế **không triển khai POST caching phổ biến**. Không nên giả định POST luôn cache được chỉ vì trả 200 hay có max-age; cũng không nên đồng nhất **idempotency key** với response caching.

### 10.2. Những status có thể được lưu theo HTTP

Một số response có status như **200 OK**, **301 Moved Permanently** và **404 Not Found** có thể được lưu và có khả năng được áp dụng heuristic freshness theo các điều kiện của HTTP. Các status khác cũng có quy tắc cacheability riêng; không dùng danh sách ví dụ như một danh sách đầy đủ.

Đặc biệt:

- **404** có thể được cache: nếu client vừa hỏi một sản phẩm chưa tồn tại, sau đó sản phẩm được tạo, cache 404 có thể vẫn xuất hiện nếu chưa hết hạn/tái xác nhận.
- **304** là kết quả của revalidation, không mang representation body mới.
- **204 No Content** là response thành công không có content; không xem nó là cách biểu diễn một array rỗng mặc định.
- **206 Partial Content** phục vụ cơ chế byte ranges; cache hỗ trợ phải xử lý các điều kiện về range, validator và kết hợp đoạn, không tự ghép byte tùy ý.
- **401/403** và lỗi có dữ liệu nhạy cảm cần chính sách rõ; không dựa vào việc lỗi là 4xx để nghĩ nó không thể bị lưu ở bất kỳ đâu.

### 10.3. Không biến GET thành lệnh ghi

Nếu endpoint **GET /orders/123/approve** làm thay đổi đơn hàng, cache, crawler hoặc prefetch có thể gửi GET ngoài dự tính và gây side effect. Thiết kế REST đúng phương thức là điều kiện nền tảng để caching an toàn. Hãy dùng POST/PATCH/PUT/DELETE theo ngữ nghĩa nghiệp vụ, kết hợp idempotency khi cần retry, thay vì dùng GET cho thao tác làm thay đổi trạng thái.

## 11. Thiết kế cache policy theo loại tài nguyên

Đội API có thể lập một **cache policy matrix** trước khi đưa endpoint lên CDN:

| Câu hỏi | Nếu câu trả lời là “có” | Hướng thiết kế |
|---|---|---|
| Representation giống hệt cho mọi người được phục vụ cùng cache key? | Có | Có thể đánh giá shared cache |
| Response chứa dữ liệu user/tenant/role hoặc giá theo hợp đồng? | Có | Ưu tiên **private/no-store**, hoặc tách tài nguyên công khai/riêng |
| Dữ liệu thay đổi nhanh, yêu cầu độ mới nghiêm ngặt? | Có | TTL thấp, revalidation, hoặc no-store |
| Có validator chính xác? | Có | Cân nhắc ETag/If-None-Match |
| URL chứa query ảnh hưởng representation? | Có | Phải đưa tham số đó vào khóa cache hoặc không cache chung |
| Có cookie/session/Authorization? | Có | Phân tích ảnh hưởng của identity lên body và các quy tắc shared cache |
| Ứng dụng phải dùng offline? | Có | Thiết kế cache client/Service Worker riêng, bảo mật và đồng bộ |
| Có thể purge hết những biến thể liên quan khi cập nhật? | Có | Có thể dùng TTL dài hơn nếu cơ chế purge được kiểm chứng |

**Ví dụ quyết định cho /catalog:**

~~~http
GET /catalog/categories HTTP/1.1

HTTP/1.1 200 OK
Cache-Control: public, max-age=120, s-maxage=600
ETag: "categories-v9"
Vary: Accept-Language
Content-Type: application/json

{"items":[{"id":"stationery","name":"Văn phòng phẩm"}]}
~~~

Nếu representation được dịch theo ngôn ngữ thì Vary phù hợp. Khi danh mục được cập nhật, backend cần chiến lược đổi validator, hết TTL hoặc purge edge.

**Ví dụ quyết định cho /me:**

~~~http
GET /me/orders HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json

{"items":[{"id":"O-1001","total":250000}]}
~~~

Trong hệ thống thật, thay chuỗi token minh họa bằng giá trị hợp lệ nhưng không đưa token vào log hoặc tài liệu. **no-store** không giải quyết thay cho authorization tại origin: server vẫn phải kiểm tra principal/tenant và quyền trên dữ liệu.

### 11.1. Những trường hợp nên tách endpoint

Nếu GET /products/{id} trả cả dữ liệu chung và các trường cá nhân, có thể tách:

~~~text
GET /products/P-100               -> công khai, dùng CDN
GET /me/products/P-100/preferences -> riêng, không shared-cache
~~~

Frontend ghép hai response ở UI. Khi dùng cách này cần cân nhắc số round-trip, xử lý lỗi từng nhánh, tính nhất quán giữa phần chung/riêng và quyền truy cập; không cần tách mọi field bằng mọi giá. Đây là công cụ thiết kế khi lợi ích shared caching đủ lớn và ranh giới dữ liệu rõ.

## 12. Cấu hình cache headers trong Java/Spring

### 12.1. Endpoint công khai với cache browser và CDN

Ví dụ Spring MVC:

~~~java
import java.time.Duration;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/catalog/products")
class PublicCatalogController {
    private final CatalogService catalogService;

    PublicCatalogController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @GetMapping(path = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<ProductView> getProduct(@PathVariable String id) {
        ProductView product = catalogService.findPublicProductOrThrow(id);

        // Version phải đổi khi representation công khai thay đổi.
        String etag = "\"product-v" + product.version() + "\"";

        return ResponseEntity.ok()
            .cacheControl(CacheControl
                .maxAge(Duration.ofSeconds(60))
                .sMaxAge(Duration.ofMinutes(5))
                .cachePublic())
            .eTag(etag)
            .body(product);
    }
}

// CatalogService và ProductView là các kiểu giả định của ứng dụng.
// ProductView phải loại bỏ mọi trường cá nhân hóa/nhạy cảm.
~~~

Kết quả mong muốn là response chứa các chỉ thị tương đương **public, max-age=60, s-maxage=300** và ETag strong đúng phiên bản.

**Quan trọng:** ví dụ mới phát ETag, **chưa thể hiện toàn bộ xử lý If-None-Match để trả 304**. Muốn hỗ trợ conditional GET, cần kết hợp logic kiểm tra validator (chẳng hạn API hỗ trợ trong Spring WebRequest/Servlet response) hoặc filter/middleware thích hợp, đồng thời bảo đảm representation và thời điểm version chính xác.

### 12.2. Endpoint dữ liệu riêng nhưng cho phép private cache

~~~java
@GetMapping("/me/preferences")
ResponseEntity<PreferenceView> preferences(Authentication principal) {
    PreferenceView view = preferenceService.loadFor(principal);
    return ResponseEntity.ok()
        .cacheControl(CacheControl
            .maxAge(Duration.ofSeconds(30))
            .cachePrivate())
        .body(view);
}
~~~

Những thành phần giả định gồm **Authentication, PreferenceService, PreferenceView** và các import liên quan. Chỉ dùng khi policy cho phép browser giữ dữ liệu riêng; không dùng cho những dữ liệu phải tránh lưu dưới mọi HTTP cache.

### 12.3. Endpoint nhạy cảm không muốn cache HTTP

~~~java
@GetMapping("/me/payment-methods")
ResponseEntity<PaymentMethodCollection> paymentMethods(
        Authentication principal) {

    PaymentMethodCollection view =
        paymentService.listAuthorizedMethods(principal);

    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(view);
}
~~~

Trong các ví dụ:

- **Principal và quyền** vẫn được xử lý ở security/service; Cache-Control không tự xác thực người dùng.
- Nếu gateway sinh response lỗi trước controller, header cache từ controller không áp dụng cho lỗi đó.
- Nên có chính sách **mặc định rõ** cho các route có dữ liệu riêng, xử lý cả lỗi và redirect.
- Không để filter hoặc reverse proxy ghi đè private/no-store bằng policy public ngoài chủ ý.

### 12.4. Cache HTTP khác hoàn toàn @Cacheable của Spring

Đặt **@Cacheable** trên service không tự sinh Cache-Control ở response. Ngược lại, **ResponseEntity.cacheControl(...)** không tự xóa entry Redis hoặc Caffeine khi dữ liệu DB thay đổi.

Khi cùng dùng cả hai loại cache, hãy mô tả:

1. Khóa dữ liệu ứng dụng (có tenant/user khi cần).
2. TTL và invalidation của Redis/Caffeine.
3. HTTP headers và cache key ở browser/CDN.
4. Điều kiện cấp quyền và thay đổi trạng thái nghiệp vụ.
5. SLO về độ mới và quy trình hỗ trợ sự cố stale data.

### 12.5. Xử lý response lỗi an toàn

Một lỗi nghiệp vụ có body chứa thông tin riêng có thể trả **application/problem+json** với **Cache-Control: no-store** nếu chính sách yêu cầu:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Cache-Control: no-store

{"type":"about:blank","title":"Forbidden","status":403}
~~~

Đừng dựa vào quy tắc cache của status 403 để bảo vệ toàn bộ thông tin lỗi. Tránh đưa token, stack trace, session data hoặc địa chỉ hệ thống nội bộ vào response. Nếu muốn cache 404 công khai để giảm tải với tài nguyên không tồn tại, hãy đặt TTL phù hợp và giải quyết việc resource có thể được tạo sau đó.

## 13. OpenAPI và hợp đồng dữ liệu có cache

Mã nguồn server, cấu hình CDN và tài liệu công khai phải cùng mô tả được:

- Response nào là **công khai** và response nào **riêng tư**.
- Response trả header nào: **Cache-Control, ETag, Vary** khi tương ứng.
- Các query/header nào làm representation khác đi.
- Tài nguyên có thể stale bao lâu và xử lý khi stale như thế nào.
- Các mã **200, 304, 404** hoặc lỗi liên quan khi tài nguyên chưa tồn tại.

OpenAPI mô tả header nhưng **không tự cấu hình CDN/gateway hoặc browser**. Cần thêm kiểm thử chạy trên mạng thật.

### 13.1. Ví dụ hợp đồng OpenAPI 3.x

~~~yaml
openapi: 3.0.3
info:
  title: Catalog API
  version: 1.0.0
paths:
  /catalog/products/{id}:
    get:
      summary: Lấy thông tin sản phẩm công khai
      description: >
        Cùng một URI, ngôn ngữ và representation đã chọn
        trả dữ liệu giống nhau cho mọi client.
        CDN được phép cache theo Cache-Control.
      parameters:
        - in: path
          name: id
          required: true
          schema:
            type: string
        - in: header
          name: If-None-Match
          required: false
          schema:
            type: string
      responses:
        "200":
          description: Representation của sản phẩm
          headers:
            Cache-Control:
              schema:
                type: string
              description: "Ví dụ: public, max-age=60, s-maxage=300"
            ETag:
              schema:
                type: string
              description: Validator của representation hiện tại
            Vary:
              schema:
                type: string
              description: Các request headers dùng chọn biến thể nội dung
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Product"
        "304":
          description: Representation không thay đổi theo điều kiện GET
          headers:
            ETag:
              schema:
                type: string
            Cache-Control:
              schema:
                type: string
        "404":
          description: Không tìm thấy sản phẩm công khai

  /me/profile:
    get:
      summary: Hồ sơ của người dùng hiện tại
      description: >
        Response được cá nhân hóa. Không được lưu ở shared cache.
        Khi cần giảm mức lưu trữ cục bộ, API có thể dùng no-store.
      responses:
        "200":
          description: Hồ sơ cá nhân
          headers:
            Cache-Control:
              schema:
                type: string
              description: "Ví dụ: private, max-age=30"
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Profile"
        "401":
          description: Chưa có xác thực hợp lệ
components:
  schemas:
    Product:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
        price:
          type: integer
      required: [id, name, price]
    Profile:
      type: object
      properties:
        displayName:
          type: string
      required: [displayName]
~~~

Ví dụ chỉ minh họa chính sách cache, chưa có security schemes đầy đủ hay toàn bộ lỗi 4xx/5xx. Với endpoint /me/profile, cần bổ sung cơ chế **bearer authentication** trong bản OpenAPI production và nhất quán với chính sách ở gateway.

### 13.2. Không coi tài liệu là thực thi

Một dòng trong OpenAPI viết “response private” nhưng server trả **Cache-Control: public** sẽ không bảo vệ dữ liệu. Ngược lại, server trả private nhưng CDN được cấu hình **force cache** có thể tạo rủi ro. Hợp đồng phải được bảo vệ bằng **integration tests**, review cấu hình và quan sát trên tuyến thực tế.

## 14. Kiểm thử cache từ unit đến browser và CDN

### 14.1. Ma trận kiểm thử các header

| Tình huống | Phép thử | Kết quả mong đợi |
|---|---|---|
| GET product công khai | Gọi qua Spring/controller | Có public và max-age/s-maxage đúng |
| GET profile riêng | Gọi với principal A | Có private hoặc no-store theo chính sách |
| GET tài chính nhạy cảm | Gọi với principal A | Có no-store; không bật public/s-maxage |
| Revalidation | Gửi If-None-Match khớp | 304 không có body, metadata hợp lệ |
| Representation đổi | Sửa dữ liệu rồi conditional GET | Validator khác; 200 với body mới hoặc hành vi chuẩn tương đương |
| Khác ngôn ngữ | Gửi Accept-Language khác nhau | Vary phù hợp, không trả nhầm representation |
| Khác query | Gửi page/filter khác nhau | CDN không dùng chung bản sao sai |
| User A/B cùng /me/orders | Gọi với hai credential khác nhau qua shared layer | B không nhận dữ liệu A |
| Tenant A/B cùng route | Thay tenant context đã xác thực | Không lộ dữ liệu/metadata tenant khác |
| Cookie hoặc Set-Cookie | Thử response cá nhân có cookie | Cache policy vẫn an toàn, không dựa vào cookie tự chặn cache |
| Lỗi 404 sau đó tạo resource | Cache 404 rồi tạo sản phẩm | Độ trễ cập nhật phù hợp chính sách TTL/purge |
| CDN override | Bật rule cache theo đường dẫn | Không ghi đè private/no-store trái hợp đồng |
| Logout/đổi user | Dùng cùng browser profile theo kịch bản có kiểm soát | Không hiển thị thông tin cũ trái chính sách |
| App cache song song | Dữ liệu có trong Redis/Caffeine | Khóa ứng dụng vẫn cô lập tenant, không bị chi phối sai bởi HTTP headers |
| Sự cố origin | Origin không sẵn sàng | Cache tuân thủ chính sách stale/revalidation, không phát dữ liệu riêng trái yêu cầu |

### 14.2. MockMvc kiểm tra Cache-Control

Ví dụ kiểm tra endpoint đã cấu hình như phần 12:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Public product được phép lưu ở shared cache.
mockMvc.perform(get("/catalog/products/{id}", "P-100"))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Cache-Control", containsString("public")))
    .andExpect(header().string(
        "Cache-Control", containsString("s-maxage=300")))
    .andExpect(header().exists("ETag"));

// Hồ sơ riêng không cho shared cache lưu.
mockMvc.perform(get("/me/preferences"))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Cache-Control", containsString("private")));

// Thông tin thanh toán không muốn HTTP cache lưu.
mockMvc.perform(get("/me/payment-methods"))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Cache-Control", containsString("no-store")));
~~~

Những test này giả định **fixture P-100 tồn tại**, các route đã đăng ký và có principal với quyền hợp lệ cho endpoint /me. Trong dự án có Spring Security, phải thêm **mock user/token hoặc test authentication** thích hợp. Kiểm tra header ở controller chưa đủ; nên kiểm tra **response cuối cùng sau gateway** để phát hiện thay đổi/ghi đè.

### 14.3. Kiểm thử CDN/gateway thật

Một bài test an toàn cho môi trường staging:

1. Tạo hai user **A** và **B**, mỗi người có một đơn hàng giả khác nhau, xác thực bằng credential thử nghiệm.
2. Gọi cùng **GET /me/orders** qua tuyến CDN/gateway bằng credential A; ghi status, Cache-Control, Age và tín hiệu cache nếu có.
3. Gọi bằng credential B, xác minh **không có nội dung hoặc metadata của A**.
4. Thử request khác query/header, sau đó thử logout/đổi user theo chính sách.
5. Đổi một sản phẩm công khai, quan sát thời gian edge cache phản ánh thay đổi và hành vi ETag.
6. Kiểm tra log/hit ratio ở từng lớp, đặc biệt những rule override theo route.

Không dùng dữ liệu thật hoặc access token thật trong file test chia sẻ. Đừng dùng header do CDN tự phát như **X-Cache: HIT** làm bằng chứng duy nhất: tên và ý nghĩa có thể không chuẩn hóa. Một số hệ thống hỗ trợ **Cache-Status** hoặc **Age**, nhưng khả năng tra cứu còn phụ thuộc cấu hình; **quan sát dữ liệu trả về và việc cách ly người dùng mới là điều quyết định**.

### 14.4. Kiểm thử trình duyệt

Browser DevTools có thể cho biết response đến từ memory cache, disk cache hay network, nhưng chế độ “Disable cache” khi mở DevTools có thể làm kết quả khác hành vi người dùng thực. Hãy thử:

- Phiên bình thường và phiên riêng nếu phù hợp.
- Người dùng A logout và người dùng B login trong cùng profile theo chính sách test.
- Client dùng service worker hoặc client query cache.
- Điều kiện mất mạng rồi hoạt động lại.
- Thay đổi quyền/tenant và kiểm tra dữ liệu không còn hiển thị sai.

Mục tiêu không phải “không có bất kỳ cache nào”, mà là **đúng dữ liệu, đúng người, đúng thời điểm và đúng quy định lưu trữ**.

## 15. Quan sát, hiệu năng và chi phí của caching

Cache có thể giảm tải đáng kể, nhưng tối ưu tỷ lệ hit bằng mọi giá không đúng với dữ liệu riêng tư hoặc dữ liệu phải chính xác tức thời.

| Chỉ số | Dùng để làm gì? | Lưu ý |
|---|---|---|
| **Cache hit ratio** | Tỷ lệ yêu cầu được phục vụ từ cache | Phải tách public/private và route, không gộp mọi endpoint |
| **Origin request rate** | Lưu lượng thực tới origin | Giảm đúng khi cache hoạt động và không gặp stale nguy hiểm |
| **p50/p95/p99 latency** | Độ trễ người dùng trải nghiệm | Có thể đo từ client và gateway |
| **Age distribution** | Mức tuổi của bản sao được dùng | Đánh giá freshness và TTL thực tế |
| **Revalidation rate** | Mức request có điều kiện và 304 | Giúp biết cache tránh body transfer được bao nhiêu |
| **Stale content incident** | Lần khách hàng nhận dữ liệu lỗi thời quá mức chấp nhận | Đòi hỏi điều tra riêng từng loại dữ liệu |
| **Cross-user/tenant leak tests** | Kiểm soát an toàn khi shared caching | Không thể đánh đổi bằng hit ratio |
| **CDN egress và cache storage cost** | Chi phí truyền/lưu response | Cần cân đối số biến thể và thời hạn |
| **Origin CPU/DB load** | Hiệu quả giảm công việc ở backend | Cache entry riêng theo từng user có thể không đem lại nhiều hit |

**Cache key cardinality** cũng cần được kiểm soát. Nếu mỗi request có query parameter ngẫu nhiên, timestamp hoặc header theo user được đưa vào khóa, số entry tăng rất nhanh và hit ratio giảm. Nhưng **bỏ một thuộc tính chỉ để tăng hit ratio** có thể làm lẫn dữ liệu hoặc sai representation. Cần tối ưu khóa cache dựa trên semantics, không chỉ dựa trên số liệu hit.

### 15.1. SLO về độ mới dữ liệu

Với những tài nguyên có thay đổi, nên định nghĩa **staleness budget** theo nghiệp vụ:

- Catalog công khai: giá hiển thị có thể trễ 30–60 giây theo chính sách?
- Trạng thái giao hàng: người dùng chấp nhận chậm bao nhiêu?
- Số dư hoặc quyền truy cập: có cho phép dùng bản sao cũ không?
- Chính sách pháp lý/đăng ký: có bắt buộc phản hồi trạng thái mới nhất không?

**max-age=60** là một cấu hình freshness HTTP, không tự chứng minh rằng dữ liệu end-to-end chỉ trễ tối đa 60 giây nếu phía origin đã dùng Redis stale, pipeline sự kiện trễ hoặc CDN áp dụng chính sách riêng. Đánh giá độ mới phải tính **mọi lớp**.

### 15.2. Khi nào dùng stale-while-revalidate hoặc stale-if-error?

Một số hệ thống hỗ trợ các mở rộng như **stale-while-revalidate** hoặc **stale-if-error** theo chính sách HTTP/CDN phù hợp. Chúng có thể giảm độ trễ hoặc tăng khả năng phục vụ khi origin gặp vấn đề, nhưng đồng nghĩa một số client có thể nhận bản sao stale.

Không áp dụng các cơ chế này tùy tiện cho **dữ liệu cá nhân có yêu cầu xóa gấp, thay đổi quyền, số dư, giao dịch hoặc trạng thái tuân thủ**. Đầu tiên phải quyết định liệu **tính sẵn sàng của bản sao cũ** có phù hợp hơn **độ mới và quyền truy cập chính xác** trong từng luồng nghiệp vụ hay không.

## 16. Case study: rò dữ liệu đơn hàng do cấu hình CDN

### 16.1. Bối cảnh

Một nền tảng bán hàng giả định tên **StoreHub** có:

~~~text
GET /products/P-100 -> dữ liệu sản phẩm công khai
GET /me/orders      -> lịch sử đơn hàng của user hiện tại
GET /me/profile     -> hồ sơ user
~~~

Đội triển khai một rule CDN: “Cache mọi GET có status 200 trong 10 phút để giảm tải”. Origin có authorization đúng, nhưng CDN không đưa user identity vào cache key và không tôn trọng policy private của route. Một số response /me/orders chưa có Cache-Control rõ.

### 16.2. Diễn biến sự cố

~~~mermaid
sequenceDiagram
    participant A as Người dùng A
    participant CDN as CDN shared cache
    participant API as REST API
    participant B as Người dùng B
    A->>CDN: GET /me/orders (token A)
    CDN->>API: Cache miss, forward request
    API-->>CDN: 200, đơn hàng của A
    Note over CDN: Cấu hình lỗi: lưu dưới key /me/orders
    CDN-->>A: 200, dữ liệu của A
    B->>CDN: GET /me/orders (token B)
    Note over CDN: Cache hit sai, không phân biệt user
    CDN-->>B: 200, dữ liệu của A
~~~

**Vấn đề không phải là origin thiếu kiểm tra quyền cho B**: request của B thậm chí không tới origin. Sai sót là **shared cache lưu và phục vụ response cá nhân hóa**.

### 16.3. Cách xử lý sự cố

1. **Ngăn rò tiếp tục:** tắt shared caching tại các route riêng tư, bổ sung no-store/private phù hợp và xác minh rule CDN thực sự tôn trọng policy.
2. **Xử lý bản sao đã lưu:** purge/expire những entry rủi ro theo khả năng của nhà cung cấp, kiểm tra các tầng edge liên quan; không giả định đổi origin header tự xóa mọi entry cũ.
3. **Đánh giá phạm vi:** tra cứu log truy cập, cấu hình cache key, response headers, tenant/user bị ảnh hưởng theo quy trình bảo mật.
4. **Khắc phục thiết kế:** tách nội dung công khai/riêng tư, cấu hình mặc định không cache shared cho /me, review các route có Cookie/Authorization.
5. **Ngăn tái diễn:** thêm test hai principal có dữ liệu khác nhau đi qua CDN thực tế và cảnh báo policy drift.

Lưu ý vụ rò dữ liệu có thể cần quy trình bảo mật, thông báo và xử lý theo nghĩa vụ hợp đồng/pháp lý áp dụng; tài liệu kỹ thuật này không thay thế đánh giá của nhóm chịu trách nhiệm.

### 16.4. Kiến trúc sau khắc phục

| Endpoint | Cache HTTP | Quyết định |
|---|---|---|
| /products/P-100 | Browser và CDN khi đủ điều kiện | public, max-age ngắn, s-maxage lớn hơn, ETag |
| /me/orders | Không lưu ở HTTP caches theo policy mới | no-store |
| /me/profile | Private cache hoặc no-store theo mức nhạy cảm | Không dùng shared cache |
| /assets/* có hash version | Browser và CDN dài hạn | public, long max-age, immutable |

Sau khi sửa, CDN vẫn giúp giảm tải mạnh cho catalog và assets, mà không cố cache chung dữ liệu riêng. **Thiết kế tốt không phải bật hoặc tắt cache toàn hệ thống, mà là chọn đúng phạm vi cho từng loại representation.**

## 17. Bài thực hành: chọn nơi lưu và header cache

### 17.1. Bối cảnh

Bạn đang thiết kế REST API cho một nền tảng đặt vé có các tài nguyên:

~~~text
GET  /events/{eventId}            -> thông tin sự kiện công khai
GET  /events/{eventId}/seats      -> số ghế còn lại, thay đổi liên tục
GET  /me/tickets                  -> danh sách vé của người đăng nhập
GET  /me/profile                  -> hồ sơ người dùng
GET  /assets/poster.abc123.webp   -> ảnh đã có hash phiên bản
POST /bookings                    -> tạo đặt vé
GET  /reports/public-summary      -> báo cáo công khai cập nhật mỗi giờ
~~~

Client có browser và mobile app; ứng dụng đặt sau CDN và API gateway. Có nhiều tenant tổ chức sự kiện, nhưng **/events/{id}** chỉ trả thuộc tính công khai, còn dữ liệu booking/ticket phụ thuộc quyền.

**Yêu cầu giả định** (để luyện thiết kế, không phải cấu hình mặc định bắt buộc):

- Poster là asset bất biến khi URL giữ nguyên.
- Thông tin sự kiện công khai cho phép trễ tối đa 60 giây khi xuất hiện thay đổi.
- Số ghế còn lại cần phản ánh trạng thái mới trước khi xác nhận đặt vé; UI có thể hiển thị giá trị tham khảo và server vẫn phải kiểm tra tồn kho trong transaction.
- Vé và profile cần chính sách quyền riêng tư; dữ liệu vé không được lưu ở shared cache.
- Báo cáo công khai thay đổi nhiều nhất một lần mỗi giờ nhưng có thể được cập nhật thủ công.

### 17.2. Nhiệm vụ

1. Với mỗi endpoint, chọn **private cache, shared cache, không lưu trong HTTP cache**, hoặc kết hợp phù hợp.
2. Đề xuất **Cache-Control**, ETag/Vary nếu cần. Giải thích trade-off độ trễ, độ mới và riêng tư.
3. Giả sử thông tin sự kiện thay đổi theo **Accept-Language**: cần thêm điều kiện gì để cache không trả sai ngôn ngữ?
4. Giả sử ứng dụng bổ sung **isFavorite** vào response **GET /events/{id}**, thay đổi theo user: chính sách shared cache cũ còn an toàn không? Nêu hai phương án sửa.
5. Một khách hàng logout rồi người khác login trên cùng trình duyệt. Dữ liệu **/me/tickets** có thể còn ở đâu và làm sao giảm nguy cơ đọc nhầm?
6. Khi poster URL có hash phiên bản nhưng file bị thay thế tại cùng URL, điều gì sẽ xảy ra với **immutable, max-age dài**?
7. Thiết kế ba phép thử bảo mật và ba phép thử độ mới dữ liệu trên tuyến CDN thực.
8. Phân biệt cách **Spring @Cacheable** ở service với **Cache-Control** ở controller, nhất là khi cùng eventId có dữ liệu khác nhau theo tenant.

### 17.3. Hướng giải tham khảo

| Tài nguyên | Hướng chính sách tham khảo | Lý do |
|---|---|---|
| GET /events/{id} | **public, max-age=30, s-maxage=60** + ETag + Vary khi có ngôn ngữ | Công khai và có staleness budget rõ |
| GET /events/{id}/seats | **no-store**, hoặc private/revalidation chặt nếu chỉ hiển thị gợi ý | Tránh bản sao stale tác động quyết định mua; origin phải kiểm tra tồn kho khi POST |
| GET /me/tickets | **no-store** | Vé là dữ liệu riêng và nhạy cảm |
| GET /me/profile | **private, max-age ngắn** hoặc **no-store** tùy mức nhạy cảm | Shared cache không được lưu; cân nhắc thiết bị dùng chung |
| GET /assets/poster.abc123.webp | **public, max-age dài, immutable** | URL đổi khi nội dung đổi; cache dài hạn hiệu quả |
| POST /bookings | Thường **no-store** | Tạo giao dịch, cần logic idempotency riêng |
| GET /reports/public-summary | **public**, TTL theo chính sách, ETag và quy trình purge | Dữ liệu công khai, có thể thay đổi thủ công |

**Giải thích các câu còn lại:**

- Với ngôn ngữ thương lượng theo Accept-Language, cân nhắc **Vary: Accept-Language** để các cache phân biệt đúng representation.
- Trường **isFavorite** làm response cá nhân hóa. Có thể tách thành endpoint riêng cho user, hoặc đổi response tổng hợp sang **private/no-store**; không giữ shared cache key chung.
- Khi logout, cần nghĩ tới browser HTTP cache, app query cache, Service Worker/Cache API, storage phía client. Chọn no-store cho dữ liệu vé và xóa state ứng dụng đúng vòng đời.
- **immutable** chỉ an toàn khi phiên bản trong URL thực sự bất biến. Nếu thay byte tại cùng URL, khách hàng có thể giữ nội dung cũ rất lâu; cách đúng là phát hành URL/hash mới.
- Test bảo mật gồm A/B cùng URI nhưng credential khác nhau, đổi tenant/quyền và kiểm tra Set-Cookie/Authorization qua CDN. Test độ mới gồm cập nhật event, thay representation theo ngôn ngữ và tái xác nhận ETag sau TTL.
- Redis/Caffeine cache nội bộ cần key đã xác thực và invalidation. HTTP Cache-Control không tự tạo key Redis an toàn hoặc bảo đảm transaction đặt vé.

Không có một đáp án duy nhất cho seats và profile: yêu cầu nghiệp vụ, thiết bị dùng chung, quyền riêng tư và độ mới dữ liệu quyết định chính sách. Điểm cần chứng minh là **không vượt staleness budget và không lộ dữ liệu**.

## 18. Những nhầm lẫn và phản mẫu thường gặp

| Nhầm lẫn / phản mẫu | Hậu quả | Cách sửa |
|---|---|---|
| “private nghĩa là response không được lưu ở đâu” | Browser vẫn có thể giữ bản sao theo policy | Dùng **no-store** nếu không muốn HTTP caches lưu |
| “no-cache cấm lưu” | Vẫn có bản sao ở cache, chỉ yêu cầu revalidate | Phân biệt store và reuse |
| “max-age=0 giống no-store” | Cache vẫn có thể giữ body và validator | Dùng đúng directive theo mục tiêu |
| “Có Authorization nên CDN không thể cache” | Một số response directives cho phép shared caching theo RFC | Chọn **private/no-store** cho dữ liệu riêng và kiểm tra CDN |
| “Set-Cookie tự động chặn cache” | Response cá nhân hóa có thể được lưu sai | Cấu hình Cache-Control và cache key |
| “HTTPS tự động tắt caching” | Browser/CDN vẫn có thể cache nội dung HTTPS theo chính sách | Dựa trên cache directives và quyền |
| “Vary: Authorization thay thế authorization” | Không bảo vệ dữ liệu nếu cấu hình hoặc quyền sai | Kiểm tra quyền tại origin, tránh shared cache cho payload riêng |
| “CDN chỉ dùng URL path làm key là đủ” | Filter/tenant/language có thể nhận sai body | Xét URI đầy đủ, Vary và các biến thể trong hợp đồng |
| “Bật cache mọi GET 200” | Lộ /me/orders, /accounts và dữ liệu đa tenant | Policy theo loại tài nguyên, deny-by-default cho route riêng |
| “Cache rỗng không cần vô hiệu hóa” | Resource mới tạo vẫn có thể bị che bởi response 404 hoặc items [] stale | TTL/revalidation/invalidation cho kết quả rỗng |
| “ETag hiện diện thì server tự trả 304” | Client vẫn nhận full 200 nếu logic conditional request chưa có | Triển khai và test If-None-Match đúng |
| “CDN purge xong là browser hết cache” | Browser và lớp ứng dụng có vòng đời riêng | Hiểu từng lớp, version URL và chính sách cập nhật |
| “@Cacheable tuân theo Cache-Control” | Redis/Caffeine bị giữ stale hoặc dùng khóa sai tenant | Thiết kế caching ứng dụng độc lập với caching HTTP |
| “Tỷ lệ hit càng cao càng tốt” | Tăng cache hit nhờ chia sẻ sai dữ liệu hoặc stale quá mức | Đặt an toàn và staleness budget lên trước |
| “304 là response rỗng của collection” | Nhầm conditional GET với dữ liệu rỗng | 304 liên quan validator, không phải số phần tử |
| “Có no-store là mọi bản sao không bao giờ tồn tại” | Các hệ thống log, app state hoặc storage vẫn có thể giữ dữ liệu | Kiểm soát toàn vòng đời dữ liệu, không chỉ HTTP cache |

## 19. Checklist trước khi đưa REST API có cache lên production

- [ ] Đã phân loại endpoint: công khai, cá nhân hóa, đa tenant, nhạy cảm, immutable.
- [ ] Biết tuyến request đi qua browser, gateway, forward proxy/reverse proxy/CDN nào và lớp nào thực sự cache HTTP.
- [ ] Đã chọn **private, public, no-cache, no-store, max-age, s-maxage** theo nội dung và yêu cầu độ mới; không dùng mặc định cho mọi route.
- [ ] Dữ liệu cá nhân/tenant không được lưu ở **shared cache** nếu không có thiết kế bảo vệ được kiểm chứng.
- [ ] Đã hiểu quy tắc shared cache đối với request có **Authorization**; không trông cậy vào token hoặc cookie để tự chặn lưu.
- [ ] Cache key và Vary phản ánh đúng query, ngôn ngữ, representation; không bỏ tham số ảnh hưởng dữ liệu/quyền.
- [ ] Các response 200/304/404 có chính sách phù hợp, kể cả tài nguyên mới được tạo sau khi cache 404.
- [ ] ETag/Last-Modified thay đổi đúng khi representation thay đổi; conditional GET và 304 được kiểm thử.
- [ ] Có TTL, invalidation/purge/versioning cho member và collection liên quan khi dữ liệu thay đổi.
- [ ] Đã xác minh header cuối cùng **sau gateway/CDN** không bị override trái hợp đồng.
- [ ] App cache/Redis/Caffeine có key tenant/user đúng và TTL/invalidation độc lập với header HTTP.
- [ ] Có bài test hai user/tenant khác nhau dùng chung URI và kiểm tra không rò dữ liệu.
- [ ] Có bài test logout/đổi user, CORS/client cache, nếu sản phẩm có offline/Service Worker.
- [ ] Kiểm tra staleness budget và hành vi khi origin lỗi hoặc revalidation không thành công.
- [ ] OpenAPI mô tả Cache-Control, ETag, Vary và các status 200/304/404 khi liên quan.
- [ ] Theo dõi hit ratio, Age, latency, origin load, chi phí và sự cố stale/cross-tenant, không để metric cardinality quá lớn.
- [ ] Runbook ghi cách purge, kiểm tra cache key, xác định lớp phục vụ response và rollback cấu hình lỗi.

## 20. Ghi nhớ và tài liệu tham khảo

**Private cache** dành cho phạm vi một user agent/người dùng; **shared cache** phục vụ nhiều người dùng nên cần ranh giới nghiêm ngặt để không tái sử dụng nhầm response riêng tư. Một phản hồi REST có thể được lưu ở **browser, proxy, CDN hoặc các lớp cache ứng dụng**, nhưng **chỉ các HTTP caches tuân thủ giao thức mới tự áp dụng các quy tắc Cache-Control**; Redis, state frontend và log có cơ chế riêng.

Nhớ ba sự khác biệt:

1. **private cho phép cache riêng lưu, ngăn shared cache lưu; no-store không cho HTTP cache lưu; no-cache có thể lưu nhưng phải revalidate trước khi tái sử dụng.**
2. **max-age/s-maxage** điều chỉnh freshness, **ETag/304** hỗ trợ revalidation, **Vary/cache key** hỗ trợ lựa chọn đúng representation; chúng không thay thế authorization.
3. Cache an toàn là **đúng người được xem, đúng dữ liệu được chọn và độ mới chấp nhận được**, không chỉ là hit ratio cao hay số request origin giảm.

Tài liệu chuẩn để đối chiếu:

- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): định nghĩa shared/private cache, store/reuse, freshness, Cache-Control, Authorization, Vary và cache validation.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): phương thức, status, conditional requests, ETag, Last-Modified và representation.
- [RFC 5861 — HTTP Cache-Control Extensions for Stale Content](https://www.rfc-editor.org/rfc/rfc5861): stale-while-revalidate và stale-if-error.
- [RFC 9211 — The Cache-Status HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9211): thông tin chẩn đoán cache trên đường truyền.
- [Spring Framework — CacheControl](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/CacheControl.html): API xây dựng header Cache-Control trong Spring.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): mô tả hợp đồng HTTP headers, response và schema.

**Quyết định đặt cache ở đâu là một phần của thiết kế REST API.** Hãy bắt đầu từ phân loại dữ liệu và phạm vi người được xem, sau đó mới chọn mức lưu trữ, thời hạn, validator và cơ chế kiểm thử trên toàn tuyến.
