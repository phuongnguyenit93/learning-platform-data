# Cache-Control: max-age, s-maxage, public và private

Một REST API trả danh sách sản phẩm cho hàng nghìn khách hàng. Mỗi lần tải trang đều truy vấn cùng dữ liệu catalog, khiến database và ứng dụng chịu tải không cần thiết. Nhóm phát triển thêm **Cache-Control: public, max-age=300** để browser và CDN tái sử dụng response. Hiệu năng cải thiện, nhưng ngay sau đó nhóm nhận thấy API thông tin tài khoản cũng trả dữ liệu qua shared cache vì đã sao chép cùng cấu hình. Một người đăng nhập có nguy cơ nhận nội dung của người khác.

Vấn đề không phải **có nên cache REST API hay không**, mà là **ai được phép lưu response, lưu bao lâu, dùng lại cho request nào và khi nào phải xác minh dữ liệu còn đúng**. Các directive **max-age**, **s-maxage**, **public** và **private** trong HTTP Cache-Control là công cụ cốt lõi để diễn đạt những quyết định đó.

Bài học thuộc chương **Bộ nhớ đệm** của module **INTEGRATION_API_REST**. Nội dung bám theo HTTP Semantics và HTTP Caching (đặc biệt **RFC 9110 và RFC 9111**), kết hợp thiết kế URI/resource, trạng thái HTTP, ETag, phân quyền, Spring Boot và kiểm thử đường đi qua browser, reverse proxy, CDN và origin.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **private cache** như browser cache với **shared cache** như proxy/CDN, cùng các điều kiện lưu và sử dụng lại HTTP response.
2. Giải thích độc lập **max-age**, **s-maxage**, **public**, **private** và cách chúng kết hợp.
3. Tính độ tươi từ các giá trị minh họa của **Date**, **Age** và freshness lifetime; không nhầm TTL với dữ liệu bảo đảm đúng mãi.
4. Thiết kế header cho catalog công khai, dữ liệu theo ngôn ngữ, tài nguyên riêng của người dùng, trạng thái đơn hàng và nội dung bất biến.
5. Phân biệt **no-cache**, **no-store**, **must-revalidate**, **ETag/If-None-Match** và phản hồi **304 Not Modified** với các directive chính.
6. Triển khai và kiểm thử Cache-Control bằng **Java/Spring** trong trường hợp có browser và CDN.
7. Nhận diện nguy cơ **rò dữ liệu xuyên người dùng/tenant**, cache key không đầy đủ, stale data và cấu hình cache khác nhau giữa các tầng.

## 2. Cache hoạt động ở những tầng nào?

HTTP cache là thành phần **lưu một response có thể lưu trữ** để dùng cho một request tương đương về sau khi điều kiện cho phép. Trong REST API, một request có thể đi qua nhiều cache với chính sách khác nhau.

~~~mermaid
flowchart LR
    U["Browser / mobile HTTP client"] --> B[("Private cache")]
    B --> C[("Shared CDN cache")]
    C --> P["Reverse proxy / API gateway"]
    P --> A["Spring REST API"]
    A --> D[("Database")]
    C -.->|"Cache hit hợp lệ"| U
    A -.->|"Response + Cache-Control"| C
~~~

Sơ đồ mang tính logic. Một cache hit ở browser có thể **không gửi request ra Internet**; một cache hit ở CDN có thể **không chạm tới origin**. Các ứng dụng mobile cũng có thể dùng thư viện HTTP cache riêng; không phải mọi client tự động cache giống browser.

### 2.1. Hai loại cache liên quan trực tiếp đến bài

| Loại cache | Ví dụ | Đặc điểm tin cậy |
|---|---|---|
| **Private cache** | Browser HTTP cache, cache riêng dành cho một người dùng | Phục vụ một người dùng hoặc ngữ cảnh riêng; có thể lưu nội dung không dành cho shared cache nếu chính sách cho phép |
| **Shared cache** | CDN, forward proxy chung, reverse proxy cache cho nhiều người dùng | Có thể phục vụ nhiều client; phải bảo vệ việc phân biệt dữ liệu và tuân thủ các hạn chế lưu trữ/reuse |

Một CDN có chức năng bảo vệ dữ liệu theo người dùng **không tự trở thành private cache chỉ vì có authentication**. Nó vẫn có thể là shared cache theo nghĩa HTTP nếu một kho cache được sử dụng cho nhiều client. Điều quan trọng là phạm vi lưu/trả response và các quy tắc RFC tương ứng.

### 2.2. Request nào có thể tái sử dụng response?

Khóa cache cơ bản liên quan đến **request method** và **target URI**. Các request header được nêu trong **Vary** có thể bổ sung chiều phân biệt biểu diễn.

Ví dụ:

~~~http
GET /v1/products?category=camera HTTP/1.1
Host: api.example.test
Accept: application/json
Accept-Language: vi
~~~

URI **/v1/products?category=camera** khác URI **/v1/products?category=laptop**. Nếu dữ liệu phụ thuộc ngôn ngữ, response có thể cần **Vary: Accept-Language**. Nếu dữ liệu phụ thuộc tài khoản hoặc tenant, chỉ thêm một tham số hay Vary tùy tiện **không đủ bảo đảm** cache phân tách đúng theo chính sách bảo mật.

**Lưu ý:** các implementation có thể dùng cache key/phân vùng tùy biến ở CDN. Cấu hình nhà cung cấp có thể bỏ qua query, chỉ chọn một số cookie hoặc thay hành vi của origin. Vì thế phải kiểm thử **cache key hiệu dụng** của sản phẩm đang triển khai, không suy đoán từ một header đơn lẻ.

## 3. Bốn directive quan trọng nhất

Cache-Control là một HTTP field chứa các **cache directives**. Ở response, chúng biểu đạt điều kiện lưu, thời gian tươi và phạm vi cache được dùng. Ở request cũng có các directive riêng; cần phân biệt cùng tên nhưng vai trò khác nhau.

| Response directive | Tác dụng chính | Đối tượng liên quan | Điều **không** được suy ra |
|---|---|---|---|
| **max-age=N** | Freshness lifetime tối đa **N giây** cho response theo quy tắc cache | Private và shared cache nếu không bị directive khác ghi đè | Không phải bảo đảm backend không đổi trong N giây |
| **s-maxage=N** | Freshness lifetime **N giây dành cho shared cache**, ghi đè max-age/Expires tại shared cache | Shared cache | Không áp dụng cho browser/private cache như một TTL riêng |
| **public** | Khẳng định response được phép lưu trong shared cache, kể cả một số trường hợp thông thường bị hạn chế | Đặc biệt shared cache | Không có nghĩa dữ liệu thực sự công khai hoặc không cần phân quyền |
| **private** | Response không được shared cache lưu nếu không có field qualifier; private cache vẫn có thể lưu khi điều kiện khác cho phép | Shared/private cache | Không có nghĩa mã hóa dữ liệu hoặc buộc browser không lưu |

Đọc bốn directive như **hai câu hỏi tách biệt**:

1. **Ai có thể lưu/tái sử dụng?** → public, private và những quy tắc HTTP khác.
2. **Một bản đã lưu còn fresh bao lâu?** → max-age, s-maxage, Age, validation và chính sách khác.

### 3.1. Các header mẫu

~~~http
Cache-Control: public, max-age=60, s-maxage=300
~~~

Ý định: response được phép dùng trong shared cache; browser nhận freshness lifetime 60 giây, shared cache nhận freshness lifetime 300 giây (nếu các điều kiện lưu/tái sử dụng khác cho phép).

~~~http
Cache-Control: private, max-age=30
~~~

Ý định: shared cache **không lưu** response; private cache có thể giữ response fresh tối đa 30 giây theo quy tắc HTTP caching.

~~~http
Cache-Control: no-store
~~~

Ý định: các cache tuân chuẩn **không được lưu** nội dung request/response thuộc phạm vi directive; phù hợp với nhiều response nhạy cảm.

### 3.2. Cú pháp và đơn vị

Giá trị của **max-age** và **s-maxage** là số giây không âm (delta-seconds). Ví dụ:

- **max-age=0**: freshness lifetime bằng 0; thường khiến cache phải xác minh trước khi tái sử dụng một response đã có tuổi.
- **max-age=60**: freshness lifetime 60 giây.
- **s-maxage=600**: shared cache có freshness lifetime 600 giây.

Không dùng **max-age=5m**, **s-maxage="1 hour"** hoặc một giá trị không đúng cú pháp để chỉ thời gian. Đừng tự chọn TTL từ cảm giác; hãy dựa vào mức chịu dữ liệu cũ của nghiệp vụ, tần suất đổi và phương án invalidation.

## 4. max-age: một response được xem là fresh trong bao lâu?

Ở response:

~~~http
HTTP/1.1 200 OK
Date: Wed, 18 Nov 2026 10:00:00 GMT
Cache-Control: max-age=120
Content-Type: application/json

{"id":"p-42","name":"Camera A","price":1200000}
~~~

**max-age=120** quy định freshness lifetime 120 giây. Một cache tuân chuẩn có thể tái sử dụng response khi nó còn **fresh** và đáp ứng các điều kiện khác (method, URI, Vary, authorization, v.v.).

### 4.1. Fresh không đồng nghĩa chắc chắn đúng theo dữ liệu mới nhất

Nếu giá sản phẩm đổi sau 30 giây nhưng cache đã lưu response **max-age=120**, cache có thể tiếp tục trả giá cũ trong phần thời gian còn fresh. Cấu hình đó phản ánh **mức chấp nhận dữ liệu cũ**, chứ không khiến database giữ nguyên giá.

Nếu giá cuối cùng phải đúng tuyệt đối tại checkout, không được tin giá đã cache ở trang catalog. Hãy **kiểm tra lại giá và điều kiện bán** tại bước giao dịch theo hợp đồng nghiệp vụ.

### 4.2. Freshness lifetime và current age

Một mô hình đơn giản:

\[
\text{fresh nếu } \text{current\_age} < \text{freshness\_lifetime}.
\]

**current_age** không chỉ tính từ lúc browser nhận response. HTTP cache có cách tính tuổi từ thời gian xử lý, chênh lệch Date, thời gian resident và đặc biệt header **Age** do cache trung gian đưa ra. Để làm bài tập, có thể dùng Age và thời gian trôi qua như một xấp xỉ khi mọi đồng hồ hợp lý.

Giả sử:

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=120
Age: 80
~~~

Response đã có tuổi xấp xỉ **80 giây** khi client nhận nó; ở thời điểm đó, thời gian fresh còn khoảng **40 giây**, không phải được bắt đầu lại 120 giây từ lúc nhận. Khi 40 giây trôi qua, response có thể trở thành stale và cần revalidation hoặc fetch mới theo chính sách.

**Age** biểu thị tuổi ước lượng của response theo cơ chế HTTP caching; không dùng Age làm đồng hồ tuyệt đối để chứng minh dữ liệu backend đã đổi hay chưa.

### 4.3. max-age của request khác max-age của response

Client có thể gửi:

~~~http
GET /v1/products/p-42 HTTP/1.1
Host: api.example.test
Cache-Control: max-age=0
~~~

Đây là **request directive**, nêu giới hạn freshness mà client chấp nhận từ cache. Nó không đặt TTL của response được tạo ở origin. Với một response đã có tuổi, **max-age=0** thường dẫn đến revalidation; nhưng muốn yêu cầu cache xác minh response trước khi sử dụng dù còn fresh thì **Cache-Control: no-cache** là chỉ dẫn trực tiếp hơn.

**Cache-Control: max-age=0** cũng **không đồng nghĩa** không lưu dữ liệu. Nó khác với response **no-store**.

### 4.4. max-age không ghi đè mọi điều kiện

Một response có:

~~~http
Cache-Control: private, max-age=3600
~~~

không được shared cache lưu chỉ vì max-age lớn. Một response có:

~~~http
Cache-Control: no-store, max-age=3600
~~~

không trở thành response được lưu vì có max-age; **no-store** hạn chế lưu trữ. Hãy tránh cấu hình directive mâu thuẫn, thừa hoặc khiến người vận hành hiểu sai chính sách.

## 5. s-maxage: điều chỉnh freshness riêng cho shared cache

**s-maxage** là response directive dành cho **shared cache**. Nó ghi đè **max-age** hoặc **Expires** khi shared cache xác định freshness lifetime. Private cache như browser không dùng s-maxage để ghi đè max-age.

Ví dụ:

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=60, s-maxage=300
Content-Type: application/json

{"items":[{"id":"p-42","name":"Camera A"}]}
~~~

Ý định:

- **Browser/private cache:** freshness lifetime **60 giây** do max-age.
- **CDN/shared cache:** freshness lifetime **300 giây** do s-maxage.
- **Origin:** có thể tránh nhiều request từ CDN trong 300 giây nếu cache hit, key đúng và không có chính sách khác yêu cầu revalidation.

### 5.1. Điều quan trọng: Age đi tiếp xuống browser

Giả sử CDN đã giữ response **250 giây** và trả nó cho browser mới:

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=60, s-maxage=300
Age: 250
~~~

Với shared cache, response còn fresh vì 250 < 300. Nhưng với browser/private cache, freshness lifetime do **max-age=60**; cùng response đó **đã stale** theo tuổi mà browser thấy. Browser có thể cần revalidation cho lần sử dụng sau. Vì vậy, **“CDN giữ fresh 5 phút, browser giữ 1 phút” không có nghĩa một browser luôn được thêm 1 phút fresh mới sau mọi CDN hit**.

Đây là một chi tiết quan trọng khi thiết kế nhiều lớp cache: cùng một response có thể fresh ở tầng này nhưng stale ở tầng khác do cách chọn freshness lifetime.

### 5.2. s-maxage còn ảnh hưởng cách xử lý response đã stale

Theo RFC 9111, **s-maxage** đối với shared cache cũng mang ý nghĩa ràng buộc về **revalidation khi stale**, tương tự tinh thần proxy-revalidate. Shared cache không tự do phục vụ response stale chỉ vì origin tạm thời không liên hệ được, trừ những điều kiện cụ thể được quy tắc HTTP và các extension hợp lệ cho phép.

Nếu muốn phục vụ dữ liệu cũ có kiểm soát trong lúc làm mới hoặc khi origin lỗi, phải thiết kế rõ các directive như **stale-while-revalidate** hoặc **stale-if-error** và xác minh hỗ trợ thực tế. **s-maxage tự nó không có nghĩa “được trả stale thêm N giây”.**

### 5.3. Khi nào dùng s-maxage?

- Catalog công khai mà CDN có thể giữ lâu hơn browser theo chính sách.
- Nội dung tin tức/danh mục có thể chấp nhận refresh khác nhau tại edge và browser.
- Dịch vụ có nhiều người đọc chung một representation và muốn giảm tải origin.
- Trường hợp có thể invalidation/purge CDN khi thay đổi dữ liệu quan trọng.

Không dùng s-maxage như cách vô hiệu hóa các yêu cầu phân quyền. **Shared cache chỉ an toàn khi nội dung thật sự có thể được chia sẻ cho các request tương đương**, và mọi chiều phân biệt nội dung đã được kiểm chứng.

## 6. public: cho phép lưu vào shared cache, không phải tuyên bố dữ liệu không nhạy cảm

**public** là response directive cho biết response **được phép lưu bởi shared cache**, ngay cả trong một số tình huống HTTP thông thường không cho phép shared cache lưu, ví dụ response cho request có **Authorization** khi không có directive cho phép đặc biệt.

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=120
Content-Type: application/json

{"category":"camera","items":[{"id":"p-42"}]}
~~~

Với một catalog giống nhau cho mọi người, **public** có thể hợp lý. Tuy nhiên, public **không mã hóa dữ liệu**, **không thay kiểm soát quyền**, **không buộc cache chắc chắn lưu** và **không tự đặt TTL cụ thể**. Cache vẫn cần điều kiện lưu/tái sử dụng phù hợp, và các directive khác có thể hạn chế lưu.

### 6.1. public khác với việc tài nguyên có URL công khai

Một URL như **/v1/products/p-42** có thể trả:

- Tên, ảnh và mô tả sản phẩm giống nhau cho mọi khách → ứng viên cho public cache.
- Giá riêng theo hợp đồng của doanh nghiệp → **không được** coi là public chỉ vì cùng URI.
- Số lượng tồn theo cửa hàng được phép xem → cần định nghĩa cache key/TTL theo cửa hàng và tính nhạy cảm.
- Mức giảm giá riêng sau đăng nhập → cần xem xét private hoặc no-store.

**Quyết định cache dựa trên tính chia sẻ của representation**, không dựa duy nhất vào phương thức GET hay việc endpoint không có chữ “private” trong đường dẫn.

### 6.2. Đặc biệt cẩn thận với Authorization

Theo các quy tắc HTTP caching, shared cache bị hạn chế sử dụng/lưu response cho request có **Authorization**, trừ những trường hợp response có directive cho phép một cách rõ ràng, ví dụ **public**, **s-maxage** hoặc **must-revalidate** theo các điều kiện tiêu chuẩn.

Vì vậy:

~~~http
GET /v1/me/profile HTTP/1.1
Authorization: Bearer <access-token>
~~~

không được trả:

~~~http
Cache-Control: public, max-age=300
~~~

chỉ để “cache cho nhanh”. Directive này có thể **mở đường cho shared cache lưu dữ liệu đã được xác thực**. Nếu representation là profile cá nhân, chọn **Cache-Control: no-store** hoặc một chính sách private có thể kiểm chứng, và làm rõ yêu cầu bảo mật. **Không giả định cứ có Authorization thì header public trở nên vô hại**.

Ngay cả response có cookie/Set-Cookie cũng cần phân tích riêng. **Set-Cookie tự nó không phải một bảo đảm phổ quát rằng shared cache sẽ không lưu response**. Một cấu hình public thiếu thận trọng có thể dẫn đến rò response hoặc metadata giữa người dùng nếu cache key và điều kiện tái sử dụng không đúng.

### 6.3. public có bắt buộc đi kèm max-age?

Không. public diễn đạt **khả năng lưu trong shared cache**, còn freshness có thể được xác định bằng các nguồn khác theo RFC. Ví dụ response có thể có Expires, s-maxage hoặc các cơ chế freshness khác.

Tuy nhiên, với REST API muốn hành vi nhất quán và đo được, thường nên đưa **freshness lifetime rõ ràng**, ví dụ:

~~~http
Cache-Control: public, max-age=60, s-maxage=300
~~~

Nếu bỏ TTL và dựa vào heuristic freshness, browser/CDN có thể xử lý khác mong muốn. Một số status response được phép cache theo mặc định, nhưng **public không có nghĩa mọi response đều fresh**.

### 6.4. public không ghi đè no-store

Đừng gửi:

~~~http
Cache-Control: public, no-store
~~~

với kỳ vọng public sẽ thắng hoặc no-store chỉ áp dụng ở browser. Đó là cấu hình mâu thuẫn về ý định. Các cache tuân chuẩn phải tôn trọng hạn chế **no-store**. Cần chọn một chính sách nhất quán cho resource và kiểm thử trên đường CDN thực tế.

## 7. private: cấm shared cache lưu, nhưng vẫn có thể cho browser lưu

Một response có:

~~~http
HTTP/1.1 200 OK
Cache-Control: private, max-age=30
Content-Type: application/json

{"theme":"dark","itemsPerPage":20}
~~~

phù hợp với dữ liệu tùy chọn giao diện dành cho **một người dùng** nếu tổ chức chấp nhận lưu ngắn hạn ở private cache. **Shared cache không được lưu response** khi private không có qualifier; browser/private cache có thể lưu và tái sử dụng theo những quy tắc khác.

### 7.1. private không đồng nghĩa no-store

| Chính sách | Shared cache | Private cache | Trường hợp nên cân nhắc |
|---|---|---|---|
| **private, max-age=30** | Không được lưu response | Có thể lưu fresh khoảng 30 giây | Preferences ít nhạy cảm, được chấp nhận lưu cục bộ |
| **private, no-cache** | Không được lưu response | Có thể lưu nhưng phải revalidate trước mỗi lần sử dụng | Dữ liệu riêng cần xác minh trạng thái liên tục và cho phép lưu |
| **no-store** | Không được lưu | Không được lưu | Token, dữ liệu nhạy cảm, thông tin giao dịch cần hạn chế lưu |

**Cache-Control: private** không có nghĩa “dữ liệu được mã hóa”, “không ai ngoài chủ tài khoản đọc được” hoặc “xóa sau khi đăng xuất”. Browser cache có thể vẫn chứa response nếu TTL còn hiệu lực và chính sách cho phép. Nếu threat model yêu cầu **không lưu ở HTTP cache**, dùng **no-store**.

### 7.2. Quyền và tuổi thọ dữ liệu

Giả sử một API trả danh sách địa chỉ giao hàng với:

~~~http
Cache-Control: private, max-age=3600
~~~

Sau khi user đăng xuất, browser có thể còn bản đã lưu trong phạm vi private cache. Các hệ thống cần chính sách về logout, thiết bị dùng chung, dữ liệu trên ổ đĩa và khả năng lưu từ các tầng khác. Đặt **private** đơn độc không giải quyết yêu cầu xóa dữ liệu nhạy cảm khỏi mọi loại storage.

Đối với số dư, token, thông tin thanh toán hoặc hồ sơ rất nhạy cảm, **no-store** thường là lựa chọn dễ bảo vệ hơn, dù có thể làm tăng số request tới origin.

### 7.3. Qualified private: một trường hợp nâng cao

HTTP hỗ trợ biến thể **private** với danh sách tên trường trong response, ví dụ về mặt cú pháp:

~~~http
Cache-Control: private="Set-Cookie", max-age=60
~~~

Ý nghĩa được chuẩn hóa là cho phép shared cache lưu phần response trong những điều kiện nhất định **sau khi loại trừ các header field được liệt kê**, thay vì cấm lưu toàn bộ representation. Nhưng dạng **qualified private** không được hỗ trợ nhất quán bởi mọi cache/proxy và rất dễ cấu hình sai.

Đối với REST API cho nhiều client/CDN, **ưu tiên private không qualifier hoặc no-store** khi cần bảo vệ dữ liệu riêng; đừng dựa vào qualified private để bảo vệ thông tin nhạy cảm nếu chưa chứng minh được hỗ trợ end-to-end.

### 7.4. Có nên kết hợp public và private?

Không nên. Ví dụ:

~~~http
Cache-Control: public, private, max-age=60
~~~

thể hiện hai ý định đối nghịch về shared storage. Tránh kiểu cấu hình này; thay bằng chính sách rõ ràng theo từng resource, sự kiện xác thực hoặc dạng representation.

## 8. Đặt bốn directive cạnh nhau trong những tình huống thực tế

| Response | Browser/private cache | CDN/shared cache | Nhận xét |
|---|---|---|---|
| **Cache-Control: max-age=60** | Có thể lưu/dùng trong 60s | Có thể lưu/dùng nếu các điều kiện khác cho phép | Không tự xử lý rủi ro theo người dùng |
| **Cache-Control: s-maxage=300** | Không lấy 300s làm TTL riêng; có thể cần freshness khác | 300s nếu lưu/tái sử dụng được | Shared cache có chính sách freshness rõ |
| **Cache-Control: public, max-age=60** | Có thể dùng 60s | Có thể dùng 60s | Phù hợp nội dung có thể chia sẻ |
| **Cache-Control: public, max-age=60, s-maxage=300** | 60s theo tuổi response | 300s theo tuổi response | Age có thể khiến browser thấy stale ngay sau CDN hit |
| **Cache-Control: private, max-age=60** | Có thể dùng 60s | Không được lưu toàn bộ response | Phù hợp một số dữ liệu riêng ít nhạy cảm |
| **Cache-Control: private, no-cache** | Lưu nhưng phải xác minh trước khi dùng lại | Không được lưu | Cần phân biệt với no-store |
| **Cache-Control: no-store** | Không được lưu | Không được lưu | Lựa chọn bảo vệ dữ liệu mạnh hơn |

Bảng mô tả **ý định theo chuẩn**, không khẳng định browser nào cũng bật cache, CDN nào cũng lưu, hay một response cụ thể chắc chắn đủ điều kiện reuse. Một response có thể không lưu được do phương thức, status, Authorization, Vary, policy khác hoặc do cache implementation không hỗ trợ.

### 8.1. Bốn cấu hình theo độ nhạy

**Nội dung công khai tương đối ổn định**

~~~http
GET /v1/categories HTTP/1.1

HTTP/1.1 200 OK
Cache-Control: public, max-age=300, s-maxage=900
Content-Type: application/json
~~~

**Thông tin catalog cần browser làm mới nhanh hơn CDN**

~~~http
GET /v1/products?category=camera HTTP/1.1

HTTP/1.1 200 OK
Cache-Control: public, max-age=30, s-maxage=180
Vary: Accept-Language
Content-Type: application/json
~~~

**Tùy chọn cá nhân không quá nhạy cảm**

~~~http
GET /v1/me/display-preferences HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Cache-Control: private, max-age=30
Content-Type: application/json
~~~

**Trạng thái giao dịch cá nhân**

~~~http
GET /v1/me/orders/o-918 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json
~~~

Các response đầu vào/output chỉ là **minh họa phần header**; không phải thông điệp HTTP hoàn chỉnh để gửi qua dây. TTL đề xuất cần được nghiệp vụ duyệt và đo trong môi trường thực tế. Không sao chép các mức 30/180/300/900 giây sang một hệ thống khác mà chưa đánh giá stale-data budget.

## 9. no-cache, no-store, Expires, must-revalidate và Age có liên quan thế nào?

Để hiểu bốn directive chính, cần phân biệt chúng với những cơ chế thường đi cùng.

### 9.1. no-cache không có nghĩa không lưu

~~~http
Cache-Control: no-cache
~~~

Theo ngữ nghĩa response, cache có thể **lưu** nhưng không được dùng bản đã lưu để đáp ứng request tiếp theo **nếu chưa xác minh thành công với origin**. Cách hiểu đúng là **revalidate before reuse**, không phải “bỏ hẳn cache”.

Điều này có ích cho nội dung có thể dùng ETag để tránh truyền lại body lớn khi không thay đổi.

### 9.2. no-store không đồng nghĩa xóa mọi dấu vết

~~~http
Cache-Control: no-store
~~~

Chỉ dẫn các HTTP cache tuân chuẩn không lưu dữ liệu thuộc phạm vi directive. Nhưng no-store **không phải một công nghệ xóa dữ liệu đã từng bị lưu trước đó**, không bảo đảm proxy sai chuẩn không giữ log, cũng không ngăn ứng dụng cố ý ghi dữ liệu ở database hoặc các storage khác.

Nếu response chứa dữ liệu nhạy cảm, cần kiểm soát thêm **logging, analytics, browser storage riêng của ứng dụng, proxy và quyền truy cập**.

### 9.3. must-revalidate và trường hợp stale

~~~http
Cache-Control: max-age=60, must-revalidate
~~~

Sau khi stale, cache không được sử dụng response cũ để đáp ứng request mà chưa revalidation thành công theo quy tắc áp dụng. Điều này có thể khiến request thất bại khi origin không liên lạc được, thay vì phục vụ dữ liệu cũ.

**must-revalidate** là ràng buộc quan trọng cho trường hợp không được trả stale tùy ý. Đối với **shared cache**, **s-maxage** có tác dụng liên quan tới proxy-revalidate khi response stale. Tuy nhiên, khả năng phục vụ stale còn chịu các directive mở rộng hợp lệ và các ngoại lệ cụ thể; không mặc định mọi cache đều giống nhau.

### 9.4. Expires và Date

~~~http
HTTP/1.1 200 OK
Date: Wed, 18 Nov 2026 10:00:00 GMT
Expires: Wed, 18 Nov 2026 10:05:00 GMT
~~~

**Expires** chỉ thời điểm hết fresh bằng HTTP-date. Khi response có **max-age** hợp lệ, max-age thường được ưu tiên hơn Expires khi tính freshness; shared cache ưu tiên **s-maxage** khi có. Dùng delta-seconds thường rõ ràng hơn khi các hệ thống có đồng hồ khác nhau.

### 9.5. Age và revalidation

**Age** do cache trung gian cung cấp để thể hiện tuổi ước lượng của response. Khi cache revalidate thành công hoặc nhận response mới, các header và tuổi được cập nhật theo quy tắc HTTP. Không nên đo TTL chỉ bằng “bao lâu rồi kể từ lần browser nhận body” nếu có CDN đứng giữa.

### 9.6. Header request và response đều có Cache-Control

| Ví dụ | Chiều | Ý nghĩa |
|---|---|---|
| **Cache-Control: max-age=60** | Response | Freshness lifetime tối đa 60 giây |
| **Cache-Control: max-age=0** | Request | Client chỉ chấp nhận response có độ tuổi phù hợp mức 0, thường cần xác minh |
| **Cache-Control: no-cache** | Request | Yêu cầu cache xác minh lại trước khi đáp ứng bằng bản lưu |
| **Cache-Control: no-store** | Request | Chỉ dẫn cache không lưu request và response tương ứng |
| **Cache-Control: private** | Response | Shared cache không lưu response nguyên vẹn |
| **Cache-Control: s-maxage=300** | Response | Shared cache có lifetime riêng 300 giây |

**Không dùng request Cache-Control để thay thế chính sách của origin**. Ví dụ một SPA gửi request no-store không có nghĩa API backend đã cấu hình response an toàn cho mọi client khác. Origin cần trả header response phù hợp với bản chất dữ liệu.

## 10. Revalidation: ETag, If-None-Match và 304 Not Modified

Một response hết thời gian fresh không nhất thiết phải tải lại toàn bộ JSON. HTTP cho phép cache **xác minh bản đang có còn phù hợp** với origin thông qua validator như **ETag** hoặc **Last-Modified**.

### 10.1. Vòng đời một GET có ETag

~~~mermaid
sequenceDiagram
    actor C as Browser
    participant E as CDN / Shared Cache
    participant O as Spring API / Origin
    C->>E: GET /v1/products/p-42
    E->>O: GET /v1/products/p-42
    O-->>E: 200 + ETag "product-v7" + max-age=60
    E-->>C: 200 + ETag + Cache-Control
    Note over C,E: Bản response trở thành stale theo freshness policy
    C->>E: GET /v1/products/p-42 (conditional)
    E->>O: If-None-Match: "product-v7"
    O-->>E: 304 Not Modified
    E-->>C: Reuse representation theo chính sách được cập nhật
~~~

Sơ đồ rút gọn: một browser và CDN có thể thực hiện revalidation ở các tầng khác nhau; không phải lúc nào cả hai cũng gửi conditional request đến origin. Khi server trả 304 cho một conditional request đúng, nó cho biết representation liên quan **không thay đổi theo validator**, để cache có thể cập nhật stored response theo các quy tắc của HTTP caching.

Một trao đổi HTTP điển hình:

~~~http
GET /v1/products/p-42 HTTP/1.1
Host: api.example.test
Accept: application/json
If-None-Match: "product-v7"
~~~

~~~http
HTTP/1.1 304 Not Modified
ETag: "product-v7"
Date: Wed, 18 Nov 2026 10:03:00 GMT
Cache-Control: public, max-age=60, s-maxage=300
Vary: Accept-Language

~~~

**304 không có response content**. Cache có thể kết hợp metadata mới với representation đã lưu để trả cho ứng dụng mà không tải lại toàn bộ body. Nếu chưa có bản lưu phù hợp, 304 tự nó không phải một bản JSON sản phẩm để client hiển thị.

### 10.2. Strong ETag và weak ETag

- **Strong ETag** như **"product-v7"** phù hợp với xác minh có yêu cầu mạnh về thay đổi byte representation.
- **Weak ETag** như **W/"product-v7"** cho phép so sánh yếu cho các biểu diễn được xem là tương đương về mặt ngữ nghĩa trong điều kiện áp dụng.
- **If-None-Match** trong conditional GET áp dụng phép so sánh yếu theo HTTP; **If-Match** trong điều kiện ghi thường dùng so sánh mạnh.

Nếu ứng dụng dùng ETag để điều kiện cập nhật resource, không nên tái sử dụng một weak validator như một cơ chế bảo vệ optimistic locking mạnh mà không hiểu đúng điều kiện HTTP. Cache validation và concurrency control là hai use case liên quan nhưng khác mục tiêu.

### 10.3. ETag phải tương ứng với variant

Giả sử JSON sản phẩm thay đổi theo **Accept-Language**:

~~~http
Vary: Accept-Language
~~~

Nếu tiếng Việt và tiếng Anh tạo ra các byte representation khác nhau, thiết kế ETag phải phù hợp với **biểu diễn được chọn** và quy tắc validator, tránh báo “không thay đổi” cho một variant thực tế khác.

Nếu origin cũng nén payload theo Accept-Encoding, cache có thể lưu nhiều phiên bản mã hóa nội dung. Tạo ETag và xử lý revalidation phải phù hợp với từng biểu diễn/encoding; không suy một version database duy nhất luôn đủ để làm strong ETag cho mọi dạng byte trên dây.

### 10.4. max-age không thay thế invalidation

Khi cập nhật sản phẩm, có một số chiến lược:

1. **TTL ngắn:** chấp nhận dữ liệu cũ trong một cửa sổ nhỏ rồi kiểm tra lại.
2. **Revalidation:** dùng ETag/Last-Modified để tránh tải lại body khi chưa thay đổi.
3. **Purge/invalidate CDN:** chủ động loại bỏ entry theo URL/surrogate key/tag khi nội dung đổi, tùy khả năng nhà cung cấp.
4. **Versioned URI:** nội dung bất biến như ảnh được phát hành dưới URI có hash/version để cache lâu mà không cần purge từng file.
5. **Không cache:** cho trạng thái giao dịch hoặc dữ liệu yêu cầu tính mới nghiêm ngặt.

Mỗi cách có đánh đổi giữa độ mới, chi phí origin, băng thông, độ phức tạp và tính sẵn sàng khi mất kết nối. Đừng tuyên bố ETag khiến dữ liệu luôn mới: cache còn fresh **có thể không hỏi origin**.

## 11. Vary, cache key và an toàn dữ liệu

Trong REST API, nhiều response là **biểu diễn theo ngữ cảnh**. Một URI có thể trả dữ liệu khác nhau do request header, quyền, locale hoặc điều kiện khác. Đây là nguồn lỗi nguy hiểm khi dùng shared cache.

### 11.1. Vary với nội dung theo ngôn ngữ

Hai request tới cùng URI:

~~~http
GET /v1/products/p-42 HTTP/1.1
Host: api.example.test
Accept-Language: vi
~~~

~~~http
GET /v1/products/p-42 HTTP/1.1
Host: api.example.test
Accept-Language: en
~~~

Nếu response khác nhau theo ngôn ngữ, có thể trả:

~~~http
Cache-Control: public, max-age=120, s-maxage=600
Vary: Accept-Language
~~~

**Vary** giúp cache tuân chuẩn phân biệt request chọn các representation khác nhau. Bỏ Vary có thể khiến client tiếng Anh nhận JSON tên sản phẩm tiếng Việt hoặc ngược lại.

Nếu client đổi **Accept: application/hal+json** sang **Accept: application/json** và server có hai biểu diễn khác nhau, cần xem xét **Vary: Accept**. Nếu response có encoding khác theo Accept-Encoding, cache/intermediary cũng cần quản lý variant đúng. Không thêm Vary cho mọi header tùy tiện, vì có thể làm **phân mảnh cache** và giảm hit ratio.

### 11.2. Phân biệt cache key với authorization

Một shared cache có thể bị cấu hình bỏ qua **Cookie, Authorization, tenant header hoặc query filter**. Khi đó:

~~~http
GET /v1/reports/current HTTP/1.1
Host: api.example.test
Authorization: Bearer token-for-tenant-A
~~~

và:

~~~http
GET /v1/reports/current HTTP/1.1
Host: api.example.test
Authorization: Bearer token-for-tenant-B
~~~

có **cùng URI** nhưng dữ liệu không được chia sẻ. Gửi **Cache-Control: public** ở response từ endpoint này có thể vô cùng nguy hiểm. Với dữ liệu tenant/user, ưu tiên **private** hoặc **no-store** theo mức nhạy cảm, và không tin rằng một Vary tùy chỉnh chắc chắn tạo ra cô lập an toàn trên mọi CDN.

**Nguyên tắc bảo mật:** nếu chưa chứng minh được shared cache không bao giờ phục vụ nội dung của tenant A cho tenant B, **không bật public caching** cho tài nguyên chứa dữ liệu tenant riêng.

### 11.3. Cookie và Set-Cookie

Một origin có thể trả:

~~~http
HTTP/1.1 200 OK
Set-Cookie: session=...; Secure; HttpOnly
Cache-Control: public, max-age=300
~~~

Cấu hình này cần được review kỹ. **Set-Cookie không tự cấm mọi cache lưu response** theo các quy tắc chung; không được dựa vào sự tồn tại của Set-Cookie như hàng rào bảo vệ dữ liệu cá nhân. Một số CDN có policy đặc biệt để không cache khi thấy Set-Cookie; đó là **hành vi sản phẩm/cấu hình**, cần kiểm tra, không phải thứ tự động được RFC đảm bảo trong mọi trường hợp.

Đối với API cookie-based authentication, thường an toàn hơn khi trả **no-store** cho dữ liệu riêng hoặc tách **API public thực sự** khỏi những endpoint phản hồi theo session.

### 11.4. Query string và dữ liệu nhạy cảm

Query là một phần của target URI và thường tham gia cache key, nhưng **URI có thể hiện trong log, history, analytics và monitoring**. Không đưa access token hoặc thông tin nhạy cảm lên query chỉ vì muốn CDN cache theo URI. Dùng **Authorization** và một chính sách lưu trữ phù hợp.

Nếu API lọc sản phẩm bằng query bình thường, cần cấu hình CDN giữ đúng tham số ảnh hưởng nội dung. Ví dụ bỏ **storeId** khỏi key nhưng giá/tồn khác theo store sẽ tạo sai lệch dù endpoint về lý thuyết là public.

### 11.5. Lỗi cache poisoning và cache deception

Một số pattern rủi ro:

- Origin sinh response dựa trên request header **X-Store-ID**, CDN không đưa header vào cache key.
- Client đưa một header không được kiểm soát khiến origin thay body, nhưng CDN cache phản hồi đó rồi phát cho người khác.
- API trả HTML/JSON riêng ở path trông như tài nguyên tĩnh, CDN bị cấu hình cache theo phần mở rộng file.
- Shared cache giữ response lỗi hoặc redirect theo policy không phù hợp.

Để phòng ngừa: xác định **nguồn tạo sự khác biệt của response**, kiểm soát key/Vary, hạn chế nội dung tùy biến dựa trên input không tin cậy và kiểm thử **hai người dùng, hai tenant, hai locale, hai store** liên tiếp qua cùng cache.

### 11.6. Response có Authorization: kiểm tra cả điều kiện lưu lẫn tái sử dụng

Một request có Authorization chịu hạn chế đặc biệt ở shared cache theo RFC. Các directive như **public/s-maxage/must-revalidate** có thể là những điều kiện cho phép storage/reuse trong phạm vi chuẩn; nhưng điều đó **không đảm bảo ứng dụng an toàn**. Hãy hỏi:

1. Nội dung có thật sự giống nhau với mọi người được phép đi tới URI đó không?
2. Những header/request attribute nào chọn representation?
3. CDN được cấu hình route/key/vary như thế nào?
4. Có bước kiểm soát quyền nào diễn ra **trước hoặc sau cache lookup**?
5. Khi user bị thu hồi quyền hoặc đổi tenant, bản cache cũ còn có thể được phục vụ không?

Nếu không trả lời được, dùng **private/no-store** thay vì tối ưu hit ratio bằng public.

## 12. Thiết kế caching theo tài nguyên và yêu cầu nghiệp vụ

Không nên đặt một header Cache-Control toàn cục giống nhau cho mọi controller. Hãy phân loại theo **tính chia sẻ, tốc độ thay đổi, hậu quả của dữ liệu cũ và quyền**.

| Resource | Yêu cầu điển hình | Chính sách bắt đầu để thảo luận | Lưu ý |
|---|---|---|---|
| **GET /v1/categories** | Công khai, thay đổi ít | public, max-age=300, s-maxage=900 | Có thể purge khi thay menu lớn |
| **GET /v1/products/{id}** | Công khai nhưng giá/tồn thay đổi | public, max-age=30, s-maxage=120 | Chỉ khi nội dung thật sự chia sẻ được; checkout kiểm tra lại |
| **GET /v1/products?category=...** | Danh sách công khai, filter theo URI | public, max-age=60, s-maxage=300 | CDN key bao gồm filter cần thiết; Vary khi có locale |
| **GET /v1/me/display-preferences** | Dữ liệu riêng, ít nhạy cảm | private, max-age=30 | Đánh giá thiết bị dùng chung và chính sách logout |
| **GET /v1/me/orders/{id}** | Trạng thái đơn của một khách | no-store | Tránh lưu thông tin cá nhân/giao dịch ngoài ý muốn |
| **GET /v1/payments/{id}** | Thông tin thanh toán nhạy cảm | no-store | Không đưa token/card data vào payload |
| **GET /assets/app.hash.js** | Tài nguyên đã version hóa theo nội dung | public, max-age=31536000, immutable | Đổi nội dung thì đổi URI/hash; kiểm tra quy trình deploy |
| **GET /v1/inventory/current** | Dữ liệu tồn có tính thời điểm | TTL rất ngắn hoặc no-store | Phải xác định sai lệch chấp nhận được |
| **POST /v1/orders** | Tạo giao dịch | Không dùng public caching cho response nghiệp vụ | Idempotency, location/status và tính đúng đơn quan trọng hơn hit ratio |

Mỗi hàng là **mẫu kiến trúc**, không phải cấu hình mặc định đúng mọi nơi. Ví dụ **GET /v1/products/{id}** sẽ không phù hợp public nếu giá phụ thuộc nhóm khách hàng hoặc có chiết khấu riêng. **immutable** là directive mở rộng được nhiều cache hỗ trợ cho tài nguyên versioned; nó không làm các byte trong một URI tự trở nên bất biến nếu nhóm triển khai vẫn ghi đè nội dung cũ.

### 12.1. Chia response công khai và response cá nhân

Nếu trang sản phẩm gồm tên/ảnh public và thông tin như **đã lưu yêu thích**, **giá cá nhân**, **khả năng mua theo tài khoản**, nên cân nhắc:

- Endpoint public catalog có thể được chia sẻ qua CDN.
- Endpoint user-specific như **/v1/me/favorites** trả private/no-store.
- Frontend kết hợp hai nguồn dữ liệu sau khi đã xác thực.

Thiết kế này có thể tăng số request, nhưng giúp **phân tách trust boundary** và tăng cache hit cho phần thực sự chia sẻ được. Nếu gộp tất cả vào một response phụ thuộc người dùng rồi đánh dấu public, nguy cơ rò dữ liệu tăng rất mạnh.

### 12.2. Cache không là nguồn dữ liệu chuẩn cho giao dịch

Catalog có thể phục vụ giá 30 giây trước; API checkout phải xác minh giá, khuyến mãi và tồn theo quy tắc nghiệp vụ. **Cache hit** là thành công của tối ưu hiệu năng, không là bằng chứng dữ liệu đủ mới để commit một giao dịch.

Với thao tác ghi, HTTP caching của response không thay thế transaction, idempotency, optimistic locking hoặc kiểm soát cạnh tranh. Cần phân biệt cache response GET với **application/data cache** như Redis cho các object nghiệp vụ: hai lớp có chính sách và rủi ro nhất quán khác nhau.

### 12.3. private cache không nhất thiết tách riêng từng tài khoản trong cùng browser

Một điểm tinh tế: **private cache theo HTTP** thường có nghĩa cache dành riêng cho một user agent/ngữ cảnh riêng, **không mặc định có namespace an toàn cho mỗi lần đăng nhập**. Nếu hai tài khoản dùng cùng một browser profile lần lượt, một URL cố định như **/v1/me/display-preferences** có nguy cơ gặp dữ liệu cũ nếu cache và xác thực không được phối hợp đúng.

Vì vậy, trong các luồng đăng nhập/đăng xuất hoặc chuyển tài khoản, cần đánh giá **đổi identity, cache partitioning, cache invalidation, Vary và no-store**. Với dữ liệu cá nhân quan trọng, **no-store** thường dễ bảo đảm tính riêng tư hơn **private, max-age=30**.

## 13. Java/Spring Boot: trả Cache-Control theo loại resource

Spring Web MVC cho phép đặt header Cache-Control bằng **ResponseEntity** và lớp hỗ trợ **CacheControl**. Ví dụ sử dụng Spring Framework 6/Spring Boot 3 và Java 17, tập trung vào response headers. Các lớp service là dependency minh họa và cần được hiện thực trong dự án thật.

### 13.1. Một endpoint catalog có thể được chia sẻ

~~~java
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

record ProductItem(String id, String name, long price) {}
record CatalogPage(
        java.util.List<ProductItem> items,
        String versionTag) {}

interface CatalogService {
    CatalogPage listPublicProducts(String category, Locale locale);
}

@RestController
@RequestMapping("/v1/products")
class CatalogController {
    private final CatalogService catalog;

    CatalogController(CatalogService catalog) {
        this.catalog = catalog;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<CatalogPage> list(
            @RequestParam(required = false) String category,
            Locale locale) {

        // BẮT BUỘC: kết quả này không chứa dữ liệu theo tài khoản.
        CatalogPage page = catalog.listPublicProducts(category, locale);

        CacheControl policy = CacheControl
                .maxAge(Duration.ofSeconds(60))
                .sMaxAge(5, TimeUnit.MINUTES)
                .cachePublic();

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .cacheControl(policy)
                .varyBy(HttpHeaders.ACCEPT_LANGUAGE)
                .eTag("W/\"catalog-" + page.versionTag()
                        + "-" + locale.toLanguageTag() + "\"")
                .body(page);
    }
}
~~~

Với response thành công, mục tiêu là tạo header tương đương:

~~~http
Cache-Control: max-age=60, s-maxage=300, public
Vary: Accept-Language
ETag: W/"catalog-v17-vi"
Content-Type: application/json
~~~

Thứ tự directive trong Cache-Control có thể khác mà không làm đổi ý nghĩa; **đừng viết test đòi đúng một thứ tự chuỗi cố định** nếu muốn kiểm tra semantics.

**Giải thích thiết kế:**

- **maxAge** chọn freshness cho các cache nói chung; **sMaxAge** thay freshness ở shared cache.
- **cachePublic()** chỉ phù hợp vì service trả danh sách **không phụ thuộc tài khoản/tenant**.
- **varyBy(Accept-Language)** cần vì tên sản phẩm ở ví dụ phụ thuộc locale.
- **ETag** ở ví dụ dùng **weak validator** cùng phiên bản dữ liệu và locale, tránh dùng một strong ETag chung cho các representation khác nhau. **versionTag** phải được quản lý để thay đổi khi nội dung tương ứng đổi.
- **category** là query parameter: CDN phải dùng những query filter ảnh hưởng response trong cache key hiệu dụng.

Trong thực tế, cần kiểm tra phiên bản Spring và cấu hình message converters để xác nhận xử lý conditional GET/304, encoding và ETag đúng. Không giả định chỉ gắn ETag sẽ tối ưu được mọi trường hợp request; hãy thêm integration tests.

Mã này minh họa **header response và hợp đồng cache**, chưa triển khai xác thực, quyền, validation, pagination, DB, exception mapping, metric và CDN. Nếu thêm các biến thể ngôn ngữ/encoding khác, cần thiết kế validator phù hợp với từng biểu diễn thực.

### 13.2. Một resource riêng có thể lưu ngắn hạn ở browser

~~~java
import java.time.Duration;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

record DisplayPreferences(String theme, int itemsPerPage) {}

interface PreferencesService {
    DisplayPreferences forCurrentUser();
}

@RestController
class PreferencesController {
    private final PreferencesService preferences;

    PreferencesController(PreferencesService preferences) {
        this.preferences = preferences;
    }

    @GetMapping("/v1/me/display-preferences")
    ResponseEntity<DisplayPreferences> get() {
        return ResponseEntity.ok()
                .cacheControl(
                        CacheControl.maxAge(Duration.ofSeconds(30))
                                .cachePrivate()
                )
                .body(preferences.forCurrentUser());
    }
}
~~~

Header mong muốn:

~~~http
Cache-Control: max-age=30, private
~~~

Đây chỉ phù hợp khi product/security **chấp nhận việc browser HTTP cache lưu preferences tạm thời** và đã xử lý an toàn tình huống đổi tài khoản trong cùng user agent. Không áp dụng cho token, số dư, hồ sơ y tế, thông tin nhạy cảm hoặc giao dịch cần tính mới chặt chẽ.

### 13.3. Resource nhạy cảm không được HTTP cache lưu

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

record OrderSummary(String id, String status, long total) {}

interface OrdersService {
    OrderSummary getOrderVisibleToCurrentUser(String id);
}

@RestController
@RequestMapping("/v1/me/orders")
class OrdersController {
    private final OrdersService orders;

    OrdersController(OrdersService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderSummary> get(@PathVariable String id) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(orders.getOrderVisibleToCurrentUser(id));
    }
}
~~~

Lớp **OrdersService** phải thực sự kiểm tra quyền trên đơn hàng. **no-store không phải cơ chế phân quyền**: một API trả nhầm đơn cho người gọi trái phép vẫn là lỗ hổng dù response không được cache.

### 13.4. Vì sao không nên cấu hình một header chung cho mọi endpoint?

Giả sử thêm filter toàn ứng dụng:

~~~text
Cache-Control: public, max-age=600
~~~

Nếu filter chạy cả với **/v1/me/orders** hoặc trang quản trị, nó có thể mở đường cho shared cache lưu dữ liệu cá nhân. Ngược lại, đặt **no-store** cho tất cả asset static, catalog và nội dung không nhạy cảm sẽ giảm cache hit và tăng tải origin.

Trong dự án thật, chọn **policy theo route/resource/data classification**, dùng default an toàn cho API nhạy cảm và danh sách cho phép cache công khai rõ ràng. Kết hợp kiểm thử response cuối cùng sau khi mọi filter, interceptor, proxy và CDN đã thêm hoặc sửa header.

### 13.5. ETag trong Spring và dữ liệu đã cá nhân hóa

Đừng tạo strong ETag chỉ từ **database version** khi response có dữ liệu khác theo locale, quyền, giá nhóm khách hoặc encoding. Validator phải phản ánh biểu diễn mà nó xác minh. Nếu không thể tính ETag đúng hoặc chi phí lớn, có thể **không dùng ETag** cho endpoint đó; một chiến lược cache đơn giản nhưng chính xác tốt hơn một validator sai.

Khi dùng ETag cho dữ liệu cá nhân, vẫn cần chính sách **private/no-store** phù hợp; ETag không biến dữ liệu có quyền truy cập thành tài nguyên công khai.

## 14. CDN, reverse proxy và API gateway có thể thay đổi kết quả

Ngay cả khi controller phát Cache-Control chính xác, đường đi production còn có nhiều cấu hình:

- CDN chỉ cache GET/HEAD, có thể giới hạn status hoặc content type được lưu.
- CDN có thể được cấu hình **ignore origin Cache-Control** hoặc đặt edge TTL riêng.
- API gateway có thể chèn/ghi đè Vary, Cache-Control hoặc loại header trong một policy.
- Reverse proxy có thể cache theo URL nhưng bỏ query, cookie hoặc header cần thiết.
- Một số CDN có lựa chọn cache responses có Authorization hoặc bỏ qua Set-Cookie; cần xem đúng chính sách.
- Browser có thể giữ response trong các cơ chế khác nhau; service worker/app cache không nhất thiết tuân HTTP cache mặc định nếu code của app chủ động lưu dữ liệu.

Do đó, khi bật cache, phải có **bản đồ đường request** từ client đến origin và xác định nơi nào lưu response thực sự.

### 14.1. Một checklist cấu hình CDN cho catalog

| Mục | Câu hỏi cần xác minh |
|---|---|
| **Cacheable routes** | Chỉ cho phép các route danh mục/asset được phê duyệt hay bật cả /v1/me? |
| **Cache key** | Có bao gồm path, query filter, host, locale/variant cần thiết? |
| **Authorization** | Request có Authorization có bypass cache hay được xử lý theo policy đặc biệt? |
| **Cookies** | Cookie nào khiến response khác; cache có chuyển tiếp/loại cookie đúng? |
| **Cache-Control** | CDN tôn trọng public/private/no-store và s-maxage không? |
| **Invalidation** | Ai purge khi đổi giá, xóa sản phẩm hoặc cập nhật chính sách? |
| **Age và hit/miss** | Có log/metric đủ để thấy HIT, MISS, REVALIDATED, BYPASS? |
| **Error responses** | 404/5xx có bị cache quá lâu hoặc tràn sang user khác không? |
| **Security** | Có test chéo user/tenant, locale, store, role và path nhạy cảm? |
| **Observability** | Có trace/correlation để phân biệt CDN hit với origin request không? |

Nếu CDN dùng **edge TTL cấu hình riêng** thay vì s-maxage của origin, phải ghi rõ ai là nguồn cấu hình chính, cách deploy đồng bộ và kiểm thử mâu thuẫn. Không kết luận rằng header đã phát từ Spring chắc chắn là header có hiệu lực ở lớp CDN.

### 14.2. Kiểm thử HEAD cùng GET

HEAD có ngữ nghĩa lấy metadata của GET tương ứng nhưng **không gửi response content**. Nếu origin trả Cache-Control/ETag khác nhau giữa GET và HEAD, cache validation hoặc các client có thể gặp hành vi không nhất quán.

Khi có HEAD, cần kiểm tra metadata cần thiết phù hợp với GET cùng variant. Nếu có **Content-Length** trong HEAD, giá trị phải phản ánh kích thước content của response GET tương ứng theo điều kiện HTTP, không phải số byte body được gửi trong HEAD.

### 14.3. Thao tác ghi và invalidation

HTTP caching có quy tắc vô hiệu hóa response đã lưu khi nhận response hợp lệ cho các phương thức **không safe** (như PUT, POST, DELETE) theo những URI liên quan. Tuy nhiên:

- CDN có thể không nhìn thấy request ghi nếu nó đi qua đường riêng.
- API có thể cập nhật nhiều URI liên quan mà cache không tự đoán được.
- Application/Redis cache không tự tuân đầy đủ quy tắc HTTP.
- Cache purge có thể cần thời gian lan truyền, nhất là nhiều region/edge.

Nếu sau khi thay giá sản phẩm phải phản ánh trong 5 giây, hãy thiết kế một cơ chế **purge/invalidation có SLA đo được**, hoặc TTL phù hợp; không chỉ dựa vào việc origin đã commit database.

### 14.4. Cảnh giác với cache của lỗi

Một số HTTP status như **404** có thể cache được theo quy tắc/heuristic khi không có chỉ dẫn ngăn cản; response lỗi cũng có thể được cache nếu có explicit policy phù hợp. Nếu API trả lỗi theo user hoặc dependency đang tạm lỗi, hãy định nghĩa cache behavior rõ ràng, thường là **no-store** cho phản hồi nhạy cảm hoặc biến động.

**Cache-Control trên response thành công không tự động áp dụng an toàn cho mọi response lỗi của gateway**. Một 502/503 do CDN tự sinh có thể không đi qua Spring, nên cần kiểm tra error caching ở chính CDN.

## 15. OpenAPI và hợp đồng cache

OpenAPI không thay thế quy tắc HTTP caching, nhưng có thể giúp tài liệu hóa **những header API trả**, ngữ nghĩa freshness và các giả định client cần biết. Ví dụ rút gọn:

~~~yaml
openapi: 3.0.3
info:
  title: Catalog API
  version: 1.0.0
paths:
  /v1/products:
    get:
      summary: List public catalog products
      parameters:
        - name: category
          in: query
          required: false
          schema:
            type: string
        - name: Accept-Language
          in: header
          required: false
          schema:
            type: string
            example: vi
      responses:
        '200':
          description: Public catalog data
          headers:
            Cache-Control:
              description: >
                Public response; browser max-age 60 seconds,
                shared cache s-maxage 300 seconds, subject to HTTP rules.
              schema:
                type: string
                example: public, max-age=60, s-maxage=300
            ETag:
              description: Validator for the selected representation
              schema:
                type: string
                example: W/"catalog-v17-vi"
            Vary:
              description: Representation can vary by language
              schema:
                type: string
                example: Accept-Language
          content:
            application/json:
              schema:
                type: object
        '304':
          description: Not modified for a valid conditional request
          headers:
            ETag:
              schema:
                type: string
        '400':
          description: Invalid request parameters
~~~

Điểm cần chú ý:

- **Cache-Control** và **ETag** ở đây là **response headers**, không phải query parameter.
- **304 Not Modified** không khai báo response content. Client hoặc cache phải có bản lưu phù hợp để tái sử dụng.
- Các con số TTL là **quyết định hợp đồng ứng dụng**; khi thay đổi có thể ảnh hưởng dữ liệu cũ mà client được phép thấy và SLA cập nhật.
- **Age** thường do cache trung gian thêm khi phục vụ bản lưu, không cần giả định origin luôn gửi Age.
- OpenAPI có thể mô tả header nhưng **không chứng minh CDN sẽ tuân theo**; cần kiểm thử triển khai.

Nếu cùng API có response riêng theo user, hãy tài liệu hóa chính sách riêng cho những operation đó, không dùng một security scheme chung để suy rằng mọi endpoint sau login đều không cache.

## 16. Quy trình kiểm thử cache end-to-end

Một chiến lược kiểm thử tốt phải quan sát **request nào tới origin, response nào đến client và cache nào thực sự lưu**. Test controller chỉ kiểm tra header, chưa chứng minh hệ thống an toàn qua nhiều cache.

### 16.1. Gọi endpoint để đọc header

Ví dụ CLI:

~~~bash
curl -i \
  -H 'Accept: application/json' \
  -H 'Accept-Language: vi' \
  'https://api.example.test/v1/products?category=camera'
~~~

Kiểm tra **Cache-Control, Vary, ETag, Date, Age** và header chẩn đoán cache nếu CDN có hỗ trợ. Tên **api.example.test** chỉ là placeholder, không phải một endpoint đang triển khai.

Để thử conditional GET:

~~~bash
curl -i \
  -H 'Accept: application/json' \
  -H 'Accept-Language: vi' \
  -H 'If-None-Match: W/"catalog-v17-vi"' \
  'https://api.example.test/v1/products?category=camera'
~~~

Nếu validator còn khớp với variant và cache/origin xử lý conditional request, có thể nhận **304**. Nhưng không được giả định ví dụ ETag trong tài liệu chắc chắn đang tồn tại trên máy chủ nào đó; phải lấy ETag thật từ response đầu tiên rồi gọi lại.

### 16.2. Ma trận các test cần thiết

| Kịch bản | Hành động | Kết quả cần quan sát |
|---|---|---|
| **Browser TTL** | Gọi catalog, sau đó gọi lại khi còn fresh | Có thể sử dụng cache mà không đến origin; kiểm tra tuổi response |
| **Shared cache TTL** | Gọi qua CDN từ hai client tới cùng URI public | CDN có cache hit khi response hợp lệ; không chứa dữ liệu cá nhân |
| **s-maxage override** | Response max-age=60, s-maxage=300; kiểm tra ở tuổi khoảng 120 | CDN có thể vẫn fresh, browser coi stale theo tuổi |
| **Age forwarding** | Nhận response CDN có Age lớn | Browser không được bắt đầu thêm nguyên max-age từ thời điểm nhận |
| **Vary theo locale** | Gọi vi rồi en rồi vi | Không trả nhầm bản dịch |
| **Query key** | Gọi category=camera rồi laptop | Không trả dữ liệu sai filter |
| **Hai tenant** | Gọi cùng URI riêng với token tenant A rồi B | Không rò dữ liệu/cache hit không hợp lệ |
| **Cookie/session** | Gọi /v1/me bằng hai account trong cùng browser | Không dùng dữ liệu riêng của account cũ khi đổi phiên |
| **private** | Gọi route preferences qua CDN | Shared cache không lưu response; browser policy theo contract |
| **no-store** | Gọi order/payment endpoint | HTTP cache tuân chuẩn không lưu response |
| **Conditional GET** | Dùng If-None-Match với ETag thật | 304 không có body khi chưa đổi; 200 với body mới khi đã đổi |
| **Cache invalidation** | Đổi giá, purge và kiểm tra nhiều CDN edge | Dữ liệu mới xuất hiện trong thời gian đã cam kết |
| **Lỗi 404/5xx** | Gây lỗi có kiểm soát trong staging | Không cache lỗi ngoài policy hoặc làm gián đoạn dài hơn |
| **Authorization** | Gọi private API qua CDN, kiểm tra policy bypass | Không lưu/trả sai theo người gọi |
| **Response overwrite** | Gọi qua Spring trực tiếp, qua gateway và CDN | Header cuối đúng; không có policy bất ngờ ghi đè |
| **Concurrent requests** | Nhiều request khi cache vừa hết hạn | Không tạo stampede quá tải origin hoặc sai dữ liệu |

Trong môi trường thật, mỗi phép thử phải có **route, người chịu trách nhiệm, dữ liệu test, thời điểm, build version, vị trí CDN edge và bằng chứng**. Một cache hit không có Age hoặc diagnostic header vẫn có thể xảy ra tùy sản phẩm; cần kết hợp access log và metric chứ không suy từ một header duy nhất.

### 16.3. Phân biệt HIT, MISS và REVALIDATED

Nhiều CDN có header debug hoặc metric:

- **HIT:** trả từ bản lưu mà không cần lấy lại toàn bộ response ở origin.
- **MISS:** không có bản lưu phù hợp, phải đi upstream/origin.
- **REVALIDATED:** có bản lưu nhưng đã xác minh với origin, có thể nhận 304.
- **BYPASS:** chính sách không sử dụng cache (ví dụ route nhạy cảm hoặc request phù hợp điều kiện bypass).

Các tên này **không thuộc tập giá trị bắt buộc của HTTP** và có thể khác nhau theo provider. Một số sản phẩm có thêm **STALE, UPDATING, EXPIRED**. Hãy dùng tài liệu/log thực tế để giải thích trước khi tính hit ratio.

### 16.4. Kiểm tra với Spring MockMvc

Ví dụ dưới đây kiểm tra response headers của **CatalogController** nếu đã có một bean CatalogService/stub trả dữ liệu công khai:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class CatalogCachingTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicCatalogHasExpectedCacheDirectives() throws Exception {
        mvc.perform(get("/v1/products")
                .param("category", "camera")
                .header("Accept-Language", "vi"))
           .andExpect(status().isOk())
           .andExpect(header().string(
                "Cache-Control",
                org.hamcrest.Matchers.allOf(
                    org.hamcrest.Matchers.containsString("max-age=60"),
                    org.hamcrest.Matchers.containsString("s-maxage=300"),
                    org.hamcrest.Matchers.containsString("public")
                )
           ))
           .andExpect(header().string(
                "Vary",
                org.hamcrest.Matchers.containsString("Accept-Language")
           ))
           .andExpect(header().exists("ETag"));
    }
}
~~~

Test trên **không độc lập chạy được** nếu chưa có CatalogService, dữ liệu fixture và cấu hình ứng dụng. Ngoài ra, matcher kiểm tra có directive trong chuỗi chứ không chứng minh browser/CDN tuân theo TTL. Nên bổ sung integration test với proxy/cache thật và test bảo mật chéo tenant.

### 16.5. Test theo cách thay đổi tài khoản

Đây là phép thử quan trọng cho cả **private** và **no-store**:

1. Đăng nhập bằng account A và gọi **GET /v1/me/display-preferences**.
2. Đăng xuất, đăng nhập bằng account B **trong cùng browser profile**.
3. Gọi lại cùng URI và kiểm tra dữ liệu thuộc B, không thuộc A.
4. Lặp lại với back/forward navigation, reload, đổi tab và những cơ chế cache của SPA.
5. Thử qua CDN và xem shared cache có lưu response không.

Nếu bị lẫn nội dung, giải pháp không đơn giản là giảm max-age. Cần xác định **cơ chế cache nào đã reuse response**, xem xét no-store, user-scoped URL/key, invalidation khi đổi phiên và phân tách dữ liệu công khai/riêng.

## 17. Bài tập: lựa chọn Cache-Control cho REST API bán hàng

Một nền tảng thương mại điện tử sử dụng Spring Boot sau CDN với các endpoint sau:

| Endpoint | Dữ liệu | Tốc độ thay đổi |
|---|---|---|
| **GET /v1/categories** | Nhóm sản phẩm giống nhau cho mọi khách | Vài lần/ngày |
| **GET /v1/products/{id}** | Tên, ảnh, giá niêm yết chung | Vài lần/giờ |
| **GET /v1/products/{id}/my-price** | Giá chiết khấu riêng theo tài khoản | Có thể đổi sau từng phiên đăng nhập |
| **GET /v1/me/display-preferences** | Theme và số mục/trang | Thỉnh thoảng |
| **GET /v1/me/orders/{id}** | Trạng thái, địa chỉ, tổng tiền cá nhân | Có thể đổi từng phút |
| **GET /assets/app.v42.js** | Tài nguyên có URI version | Không thay đổi ở URI đã phát hành |

Người quản lý mong muốn CDN giảm tải origin, nhưng tuyệt đối không được để người dùng B nhận dữ liệu của A. Hệ thống được phép chấp nhận catalog cũ tối đa vài phút; checkout vẫn phải kiểm tra giá/đơn hàng tại thời điểm xử lý.

### 17.1. Yêu cầu thực hành

1. Chọn Cache-Control cho từng endpoint, giải thích lý do **public/private/no-store**.
2. Chọn max-age và s-maxage cho categories và products, nêu mức chịu dữ liệu cũ và kế hoạch purge khi có thay đổi quan trọng.
3. Với **public, max-age=60, s-maxage=300**, CDN trả response có **Age: 240**. Nó còn fresh ở CDN không? Browser mới nhận có thể coi fresh không?
4. Với **private, max-age=30**, browser đổi từ account A sang B trong 10 giây. Có thể có rủi ro gì dù CDN không lưu?
5. Nếu catalog có hai bản vi/en, server phải thêm header gì? Điều gì xảy ra nếu bỏ header đó?
6. Nếu origin trả **304** khi If-None-Match khớp, client có cần tải lại toàn bộ JSON không?
7. Viết một test có khả năng phát hiện shared cache bỏ qua **storeId** trong query khi mỗi cửa hàng có giá khác nhau.
8. Đề xuất cách theo dõi hit/miss và đo lượng request tiết kiệm được mà không lấy các số 5xx hoặc dữ liệu cá nhân làm cache key.

### 17.2. Gợi ý đáp án

| Endpoint | Gợi ý policy | Giải thích |
|---|---|---|
| **Categories** | public, max-age=300, s-maxage=900 | Nội dung công khai, khá ổn định; có thể purge khi đổi phân loại |
| **Product public** | public, max-age=60, s-maxage=300 | Cho phép stale theo ngân sách đã duyệt; checkout kiểm tra lại |
| **My price** | no-store | Không chia sẻ và có rủi ro đổi tài khoản; cần tính mới |
| **Display preferences** | private, max-age=30 **nếu chấp nhận lưu cục bộ**; khác thì no-store | Đánh giá nguy cơ cùng browser có nhiều account |
| **My orders** | no-store | Dữ liệu cá nhân và trạng thái giao dịch |
| **Versioned JS** | public, max-age=31536000, immutable | Chỉ khi asset không bị ghi đè ở cùng URI |

Với **Age: 240**, shared cache còn fresh trong ví dụ vì **240 < 300**; browser/private cache lại xét **max-age=60**, nên response đó **đã stale** ngay tại thời điểm nhận. Nó không tự được thêm 60 giây mới. Nếu phải dùng lại, browser cần xử lý theo policy revalidation/fetch hiện hành.

Với **private, max-age=30**, CDN không lưu, nhưng private cache của browser có thể còn response của account A. Chính sách an toàn có thể là no-store hoặc cơ chế session-scoped caching đã được thiết kế, kiểm chứng. Đăng xuất và đổi account **không tự được giải quyết bằng chữ private**.

Với bản ngôn ngữ, dùng **Vary: Accept-Language** khi nội dung khác theo header; nếu không, cache có thể trả bản vi cho client en. Với ETag, client/cache có thể tận dụng **304 Not Modified** để không truyền lại body khi dữ liệu chưa đổi, nếu đang có bản lưu phù hợp.

Để phát hiện lỗi **storeId**, gọi cùng URI path với **?storeId=A** và **?storeId=B** qua CDN rồi đối chiếu nội dung/giá và log cache. Nếu CDN bỏ storeId khỏi cache key, giá của cửa hàng A có thể xuất hiện ở response B. Không dựa duy nhất vào câu “query mặc định là cache key”, mà đo cấu hình thực tế.

### 17.3. Bài tập nâng cao

Từ các yêu cầu trên, hãy lập **Cache Policy ADR** với nội dung:

- Những route được bật public cache và ai phê duyệt.
- Mỗi route có **TTL, stale-data budget và chiến lược invalidation**.
- Cách phân biệt URL/query/header biến thể và loại dữ liệu nhạy cảm.
- Cách theo dõi Age, hit ratio, origin request rate, cache pollution và error response caching.
- Điều kiện thay đổi policy khi xuất hiện giá cá nhân hoặc mở rộng sang nhiều tenant.
- Các bước rollback cấu hình CDN nếu phát hiện dữ liệu riêng bị phát ra từ shared cache.

Một ADR tốt nên cho thấy **đánh đổi giữa chi phí/băng thông/độ trễ và tính đúng/bảo mật**, không chỉ sao chép các giá trị TTL.

## 18. Các lỗi thiết kế và anti-pattern thường gặp

### 18.1. “Có max-age thì CDN phải cache”

**Sai ở đâu?** max-age chủ yếu định nghĩa thời gian fresh, không tự giải quyết mọi điều kiện lưu trữ. Một response private không thể dùng chung chỉ vì max-age lớn; một request có Authorization chịu ràng buộc đặc biệt; CDN có thể không cache route hoặc status đó.

**Cải thiện:** kiểm tra **cacheability + freshness + cache key** và chính sách sản phẩm. Test cả request từ browser và từ CDN đến origin.

### 18.2. “s-maxage nghĩa là browser được cache thêm N giây”

**Sai ở đâu?** s-maxage dành cho shared cache; browser dùng max-age hoặc cơ chế freshness áp dụng riêng. Response qua CDN còn có **Age**, không được reset TTL từ đầu.

**Cải thiện:** đo Age và đánh giá freshness **tại từng tầng**, không vẽ hai bộ đếm thời gian độc lập bắt đầu khi mỗi tầng nhận dữ liệu.

### 18.3. “public nghĩa là tài nguyên đã được bảo vệ”

**Sai ở đâu?** public có thể cho shared cache lưu response; nếu response cá nhân, đây là một rủi ro bảo mật. Dữ liệu có token/cookie không được tự động che bằng chữ public.

**Cải thiện:** chỉ bật public cho representation **thực sự có thể chia sẻ**. Tách public catalog khỏi dữ liệu riêng và kiểm tra xuyên tenant/user.

### 18.4. “private nghĩa là browser không lưu”

**Sai ở đâu?** private thường **cho phép private cache** lưu nếu không có điều kiện ngăn khác. Một thiết bị dùng chung có thể gặp rủi ro khi đổi tài khoản.

**Cải thiện:** khi yêu cầu không lưu hoặc cần bảo đảm dữ liệu cá nhân không tồn tại trong HTTP cache, dùng **no-store** và kiểm tra cả application storage/logging.

### 18.5. “no-cache và no-store giống nhau”

**Sai ở đâu?** no-cache cho phép lưu nhưng yêu cầu xác minh trước khi dùng; no-store hạn chế lưu. Hệ thống dùng ETag với no-cache vẫn có thể tiết kiệm băng thông qua 304.

**Cải thiện:** chọn theo nhu cầu **revalidate** hay **không lưu**, không chỉ theo tên directive.

### 18.6. “Set-Cookie tự khiến response không cache được”

**Sai ở đâu?** Set-Cookie không phải điều kiện phủ định chung của mọi HTTP cache. Một cấu hình public thiếu thận trọng có thể làm shared cache lưu response chứa thông tin chỉ dành cho một người.

**Cải thiện:** áp dụng Cache-Control, kiểm soát auth và cache key đúng; kiểm thử với CDN thật thay vì dựa vào hành vi mặc định đang quan sát.

### 18.7. “Vary: Authorization đảm bảo không rò tài khoản”

**Sai ở đâu?** Vary là cơ chế lựa chọn variant trong cache tuân chuẩn, không phải một hệ kiểm soát truy cập và không bảo đảm mọi CDN áp dụng đúng trong cấu hình đặc biệt.

**Cải thiện:** dữ liệu riêng dùng private/no-store, quyền vẫn kiểm tra ở backend, và kiểm thử nhiều tài khoản/tenant.

### 18.8. “Cache hit là dữ liệu luôn chính xác tại checkout”

**Sai ở đâu?** giá và tồn kho có thể đổi sau khi cache lưu. Cache hit chỉ cho thấy response được phép reuse theo policy, không chứng minh phiên bản hiện tại của database còn như cũ.

**Cải thiện:** kiểm tra lại điều kiện giao dịch và xử lý cạnh tranh ở bước checkout.

### 18.9. “Cứ tăng TTL để giảm chi phí”

**Sai ở đâu?** TTL quá dài có thể trả catalog cũ, đơn sai, thông báo bảo trì không đúng hoặc dữ liệu bị thu hồi quyền. Chi phí hỗ trợ khách, rủi ro giao dịch và thời gian purge cũng là chi phí.

**Cải thiện:** đo tỷ lệ cache hit, origin RPS, bytes saved, stale-response rate và rủi ro nghiệp vụ theo từng endpoint.

### 18.10. “Spring trả đúng header là hoàn thành”

**Sai ở đâu?** gateway/CDN có thể ghi đè Cache-Control, bỏ query khỏi key hoặc lưu lỗi do chính nó phát sinh.

**Cải thiện:** so sánh header trực tiếp từ Spring với response qua toàn bộ đường production-like; kiểm tra log của từng lớp và bản ghi thay đổi cấu hình.

### 18.11. “ETag luôn bảo đảm không trả dữ liệu cũ”

**Sai ở đâu?** cache còn fresh có thể không revalidate. Một ETag tính sai hoặc không thay đổi theo locale/encoding có thể dẫn tới 304 không phù hợp.

**Cải thiện:** quản lý ETag theo representation, phân biệt strong/weak validator và xác minh khi thay dữ liệu.

### 18.12. “Bật cache cho mọi response GET vì GET là safe”

**Sai ở đâu?** GET có thể trả dữ liệu riêng, trạng thái rất mới hoặc response bị giới hạn bởi authorization. Safe về HTTP method **không đồng nghĩa mọi response GET có thể shared cache**.

**Cải thiện:** phân loại dữ liệu và yêu cầu tính mới theo resource; để cacheable routes trong danh sách được phê duyệt.

## 19. Checklist review Cache-Control cho REST API

- [ ] Đã xác định từng cache trong request path: browser, proxy, CDN, API gateway, application cache.
- [ ] Có phân loại dữ liệu **public, cá nhân, theo tenant, nhạy cảm và trạng thái giao dịch**.
- [ ] Dùng **max-age** với đơn vị giây đúng và TTL dựa trên stale-data budget.
- [ ] Dùng **s-maxage** khi có nhu cầu freshness riêng cho shared cache; hiểu tác động của Age.
- [ ] Chỉ đặt **public** khi response thực sự có thể được shared cache dùng lại một cách an toàn.
- [ ] Dùng **private** khi muốn cấm shared storage nhưng chấp nhận private caching; nếu không được lưu, dùng **no-store**.
- [ ] Không trộn public/private hoặc cấu hình mâu thuẫn với no-store một cách tùy tiện.
- [ ] Phân biệt **no-cache, no-store, max-age=0 và must-revalidate** trong cả request và response.
- [ ] Đã xác định các request header/URI/query khiến representation thay đổi và cấu hình **Vary/cache key** phù hợp.
- [ ] Đã kiểm tra tác động của **Authorization, Cookie, Set-Cookie**, đăng nhập/đăng xuất và đổi account.
- [ ] Có chiến lược ETag/Last-Modified và xử lý conditional GET/304 nếu dữ liệu cần revalidate.
- [ ] Với response nhiều variant, validator và Vary được thiết kế nhất quán.
- [ ] Có purge/invalidation khi thay đổi dữ liệu cần cập nhật nhanh; TTL phù hợp với cam kết.
- [ ] API checkout vẫn xác minh giá/tồn/điều kiện nghiệp vụ, không coi catalog cache là nguồn chuẩn.
- [ ] CDN không ghi đè Cache-Control ngoài chủ đích; có policy rõ cho error responses và các route nhạy cảm.
- [ ] Có integration test với **hai user, hai tenant, hai locale, hai filter/cửa hàng** và ít nhất hai cache hop khi phù hợp.
- [ ] Đo Age, cache hit/miss, origin traffic, latency, invalidation delay và tỷ lệ stale response.
- [ ] Spring MVC/OpenAPI tài liệu hóa policy; thay đổi TTL hoặc cache key có review về bảo mật và dữ liệu.
- [ ] Có runbook rollback cấu hình cache và quy trình xử lý khi nghi ngờ rò dữ liệu hoặc cache poisoning.

## 20. Tài liệu chuẩn tham khảo

- **RFC 9111 — HTTP Caching**: cơ chế lưu và reuse, freshness, Age, Cache-Control response/request directives, Authorization, Vary và validation; https://www.rfc-editor.org/rfc/rfc9111.html
- **RFC 9110 — HTTP Semantics**: phương thức, trạng thái, biểu diễn, ETag, conditional request và header liên quan; https://www.rfc-editor.org/rfc/rfc9110.html
- **RFC 8246 — HTTP Immutable Responses**: directive immutable cho representation theo URI bất biến; https://www.rfc-editor.org/rfc/rfc8246.html
- **RFC 5861 — HTTP Cache-Control Extensions for Stale Content**: stale-while-revalidate và stale-if-error; https://www.rfc-editor.org/rfc/rfc5861.html
- **RFC 9457 — Problem Details for HTTP APIs**: định dạng lỗi HTTP để kiểm soát response riêng và chính sách cache của lỗi; https://www.rfc-editor.org/rfc/rfc9457.html
- **Spring Framework — CacheControl API**: các builder cho maxAge, sMaxAge, cachePublic, cachePrivate, noStore, noCache; https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/CacheControl.html
- **Spring Framework — ResponseEntity**: tạo response HTTP kèm header, status, ETag và Cache-Control; https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseEntity.html
- **OpenAPI Specification**: mô tả headers trong response contract; https://spec.openapis.org/oas/latest.html

**Kết luận:** **max-age** nói response được xem là fresh bao lâu; **s-maxage** điều chỉnh thời gian đó cho shared cache; **public** cho phép chia sẻ trong shared cache; **private** cấm shared cache lưu response nhưng không cấm private cache. Để tối ưu REST API đúng và an toàn, phải kết hợp **freshness + cacheability + cache key/Vary + authorization + invalidation + kiểm thử end-to-end**. Một cache hit tốt chỉ có giá trị khi response được trả cho **đúng người, đúng tài nguyên và trong mức độ dữ liệu cũ mà nghiệp vụ cho phép**.
