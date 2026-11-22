# CDN, bộ nhớ đệm tại biên và phân phối tài nguyên tĩnh

> **Chương:** Điểm vào hệ thống  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây (CLOUD_ARCHITECTURE), từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Trọng tâm là đánh đổi về độ trễ, khả năng mở rộng, tính sẵn sàng, bảo mật, chi phí và vận hành theo các nguyên tắc Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của **Content Delivery Network (CDN)**, **Point of Presence (PoP)**, **edge cache**, **origin**, **origin shield** và các lớp bộ nhớ đệm trong đường đi một HTTP request.
2. Thiết kế chính sách cache dựa trên tính chất dữ liệu, thời gian chấp nhận dữ liệu cũ, quyền truy cập và các chỉ thị **Cache-Control**, **ETag**, **Last-Modified**, **Vary**.
3. Phân phối an toàn HTML, CSS, JavaScript, hình ảnh, font, video và tệp tải xuống; chọn chiến lược **tên tệp chứa mã băm**, **TTL**, **revalidation**, **invalidation** và **deployment**.
4. Giảm nguy cơ lộ dữ liệu giữa người dùng/tenant, cache poisoning, truy cập trái phép origin và lỗi phân phối nội dung.
5. Đo lường hiệu quả bằng cache hit ratio, byte hit ratio, origin offload, p95/p99 TTFB, Core Web Vitals, tỷ lệ lỗi và tổng chi phí.
6. Đánh giá phương án CDN, cache tại biên, cache trình duyệt và lưu trữ nguồn theo yêu cầu nghiệp vụ, độ tin cậy, bảo mật, chi phí và khả năng vận hành.

## 1. Tại sao CDN là một phần của điểm vào hệ thống?

Giả sử một ứng dụng đặt chỗ trên cloud được triển khai tại một khu vực (region), còn khách hàng truy cập từ nhiều quốc gia. Nếu mọi trình duyệt đều yêu cầu ảnh, CSS, JavaScript và tài liệu trực tiếp từ application server trong region đó, hệ thống sẽ chịu:

- **Độ trễ đường truyền:** kết nối xa có round-trip time lớn, ảnh hưởng thời gian nhận byte đầu tiên (TTFB) và tốc độ hiển thị trang.
- **Tải lặp lại:** cùng một tệp CSS hoặc ảnh logo được truyền từ origin hàng nghìn lần dù nội dung không đổi.
- **Chi phí và điểm nghẽn:** origin phải phục vụ nhiều request, truyền dữ liệu và xử lý TLS/HTTP, cạnh tranh tài nguyên với các luồng nghiệp vụ quan trọng.
- **Phạm vi tác động sự cố:** origin hoặc đường mạng tới origin chậm có thể làm trải nghiệm của mọi người dùng suy giảm.

**CDN** là hệ thống các điểm phục vụ phân tán trên nhiều vị trí mạng, có thể đặt **bản sao nội dung được phép cache** gần người dùng và điều phối request đến lớp ứng dụng/origin khi cần. CDN còn có thể cung cấp TLS termination, tối ưu truyền nội dung, chính sách bảo mật và lọc lưu lượng, nhưng tính năng cụ thể phụ thuộc nhà cung cấp và cấu hình.

Lợi ích chính là **giảm quãng đường dữ liệu thường truy cập phải di chuyển, giảm tải lặp lại tại origin và giảm độ trễ cho nội dung thích hợp**. CDN không thể mặc nhiên làm mọi API nhanh hơn: với request cần chạy tính toán và đọc dữ liệu mới nhất, edge vẫn có thể phải chờ origin.

### Các thuật ngữ

| Thuật ngữ | Ý nghĩa | Vai trò trong kiến trúc |
| --- | --- | --- |
| **PoP (Point of Presence)** | Điểm hiện diện mạng gồm hạ tầng xử lý request, có thể có cache | Tiếp nhận lưu lượng từ người dùng theo cơ chế định tuyến CDN |
| **Edge cache** | Bộ nhớ đệm tại hoặc gần PoP | Trả nội dung có thể cache mà không phải luôn gọi origin |
| **Origin** | Nguồn nội dung gốc: object storage, web server, application service hoặc một dịch vụ khác | Xử lý cache miss, revalidation và nội dung không cache |
| **Cache key** | Bộ thuộc tính định danh một bản sao cache | Quyết định request nào được dùng chung bản sao |
| **TTL (Time to Live)** | Khoảng thời gian bản sao được coi là còn mới theo chính sách | Cân bằng độ mới nội dung với khả năng giảm tải origin |
| **Cache hit/miss** | Hit: có bản sao phù hợp để phục vụ; miss: không có bản sao phù hợp | Chỉ báo hiệu quả cache, không phải chỉ số hiệu năng duy nhất |
| **Revalidation** | Kiểm tra với origin xem bản sao còn hợp lệ hay đã thay đổi | Cho phép tái sử dụng nội dung khi nhận 304 Not Modified |
| **Invalidation/purge** | Xóa hoặc đánh dấu không hợp lệ bản sao đã lưu ở edge | Dùng khi cần làm mới nội dung trước khi TTL hết |
| **Origin shield / tiered cache** | Lớp cache trung gian giữa nhiều PoP và origin | Giảm số lần các PoP đồng thời truy vấn origin |
| **Edge function/worker** | Logic được chạy tại điểm biên nếu nền tảng hỗ trợ | Chuyển hướng, chuẩn hóa request, kiểm soát truy cập, tạo biến thể có giới hạn |

**CDN khác load balancer:** CDN tập trung phân phối/caching tại hệ thống biên; load balancer tập trung phân phối lưu lượng tới các backend đích. Cả hai có thể có trong cùng đường đi. **CDN cũng khác DNS:** DNS giúp phân giải tên miền và có thể tham gia hướng tới điểm CDN; DNS không lưu hoặc phục vụ nội dung HTTP.

## 2. Đường đi từ người dùng đến origin

### 2.1. Kiến trúc tham khảo

~~~mermaid
flowchart LR
    U["Trình duyệt / mobile app"] --> DNS["DNS cho tên miền"]
    DNS -. "Phân giải / điều hướng" .-> EDGE["CDN PoP gần vị trí mạng"]
    U -->|"HTTPS request"| EDGE
    EDGE -->|"Cache HIT"| U
    EDGE -->|"MISS / revalidate"| SHIELD["Regional cache / origin shield (tùy chọn)"]
    SHIELD -->|"MISS / cần dữ liệu mới"| ORIGIN["Origin endpoint"]
    ORIGIN --> OBJ[("Object storage: CSS / JS / ảnh")]
    ORIGIN --> APP["Application / API"]
    APP --> DB[("Database")]
~~~

Đây là sơ đồ logic. Cơ chế lựa chọn PoP có thể liên quan đến DNS, anycast hoặc kỹ thuật định tuyến khác tùy nhà cung cấp; **PoP gần nhất về địa lý không luôn là điểm có độ trễ mạng tốt nhất**.

Một request được cache tại edge thường diễn ra như sau:

1. Trình duyệt phân giải tên miền và kết nối HTTPS đến hệ thống CDN.
2. CDN xác định host, đường dẫn, các thành phần cache key, chính sách bảo mật và chính sách cache.
3. Nếu có **bản sao còn mới** và hợp lệ với request, CDN trả về trực tiếp.
4. Nếu không có bản sao, bản sao đã hết hạn hoặc cần xác minh, CDN liên hệ origin hoặc lớp cache trung gian.
5. Origin trả nội dung và các header. CDN quyết định có lưu, lưu bao lâu và dùng cache key nào.
6. Trình duyệt nhận kết quả, có thể lưu thêm trong **browser cache** theo chính sách riêng.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant C as CDN Edge
    participant O as Origin
    B->>C: GET /assets/app.a71c.css
    alt Có bản sao hợp lệ (HIT)
      C-->>B: 200 + nội dung đã cache
    else Chưa có hoặc không hợp lệ (MISS)
      C->>O: GET /assets/app.a71c.css
      O-->>C: 200 + Cache-Control + nội dung
      C->>C: Lưu theo chính sách
      C-->>B: 200 + nội dung
    end
    Note over B,C: Sau đó browser có thể tự dùng browser cache
~~~

### 2.2. Các lớp cache dễ bị nhầm

| Lớp | Vị trí | Phạm vi chia sẻ | Điểm cần thiết kế |
| --- | --- | --- | --- |
| **Browser cache** | Thiết bị người dùng | Thông thường theo profile và phân vùng cache của trình duyệt | Độ mới, reload, phiên bản ứng dụng, dữ liệu nhạy cảm |
| **CDN shared cache** | PoP hoặc hệ thống cache CDN | Nhiều request/người dùng theo cache key và chính sách | Không cache nhầm nội dung riêng tư, tối ưu TTL và invalidation |
| **Reverse-proxy cache** | Gần ứng dụng/origin | Nhiều client kết nối tới một cụm backend | Cache key, bộ nhớ, TTL, hành vi khi backend lỗi |
| **Application cache** | Trong process, distributed cache hoặc DB cache | Theo phạm vi ứng dụng/tenant và khóa dữ liệu | Invalidation, nhất quán, tải lên DB |
| **Origin shield** | Giữa edge và origin | Nhiều PoP trong một vùng/cache tier | Tránh cache miss đồng loạt và quá tải origin |

Một tệp có thể được lưu ở browser, edge và lớp reverse proxy đồng thời. Xóa CDN cache **không nhất thiết** xóa bản sao browser đã được cho phép lưu lâu. Vì vậy với tài nguyên cần cập nhật chắc chắn, **đổi URL theo phiên bản nội dung** thường tin cậy hơn việc chỉ dựa vào purge.

## 3. Phân loại nội dung trước khi chọn chính sách cache

Không nên áp dụng một TTL cho toàn bộ website. Mỗi loại nội dung có độ nhạy và yêu cầu về độ mới khác nhau.

| Loại tài nguyên | Mức chia sẻ/độ mới | Chiến lược tham khảo | Lưu ý |
| --- | --- | --- | --- |
| CSS/JS có tên chứa hash nội dung | Công khai, bất biến theo URL | TTL dài; cache tại browser và CDN | Không ghi đè cùng URL bằng nội dung mới |
| Font, icon, ảnh phiên bản hóa | Thường công khai và ít thay đổi | TTL dài khi URL thay đổi theo nội dung | Cấu hình CORS phù hợp nơi dùng font |
| HTML public marketing | Có thể cập nhật thường xuyên | TTL ngắn hoặc revalidation | Cẩn thận HTML tham chiếu phiên bản asset |
| HTML sau đăng nhập | Chứa thông tin phiên/người dùng | Mặc định không lưu ở shared cache | Không dùng TTL chung cho response có dữ liệu riêng |
| Public API đọc danh mục | Có thể chấp nhận dữ liệu chậm vài giây/phút | TTL ngắn, cache key đủ tham số | Chỉ cache khi không bị cá nhân hóa và đúng tính nhất quán |
| API trạng thái thanh toán/đặt chỗ | Phụ thuộc dữ liệu tức thời và quyền | Bypass CDN shared cache | Kiểm tra authorization, trạng thái giao dịch |
| Tài liệu tải xuống riêng khách hàng | Nhạy cảm, cần kiểm tra quyền | Signed URL/cookie có thời hạn hoặc origin kiểm quyền, chính sách cache kiểm soát | Không để cùng key dùng chung nội dung hai tenant |
| Ảnh biến thể theo kích thước/định dạng | Công khai, nhiều biến thể | Cache theo kích thước và định dạng được cho phép | Kiểm soát số biến thể để tránh bùng cache |

Điểm xuất phát an toàn: **chỉ bật shared caching cho nội dung đã xác định rõ là có thể dùng chung**. Với nội dung cá nhân, dữ liệu tenant, trạng thái tài chính hoặc thông tin có quyền truy cập, cần thiết kế kiểm soát chuyên biệt; mặc định bỏ qua cache tại CDN.

**Cacheability** (được phép lưu) và **correctness** (phục vụ đúng nội dung) là hai vấn đề khác nhau: một API public có thể lưu được nhưng vẫn không nên dùng TTL 10 phút nếu dữ liệu tồn kho phải mới trong vài giây.

## 4. Hiểu chính xác HTTP Cache-Control

Cache-Control gồm các chỉ thị điều khiển việc lưu và tái sử dụng HTTP response. Các shared cache có thể sử dụng chỉ thị khác với browser cache; hành vi thực tế cũng phụ thuộc cấu hình CDN, request method, header và chính sách override.

| Chỉ thị | Ý nghĩa thực hành | Trường hợp thường gặp |
| --- | --- | --- |
| **public** | Cho phép shared cache lưu response trong các trường hợp quy tắc HTTP phù hợp | Nội dung công khai được phép chia sẻ |
| **private** | Không cho shared cache lưu; browser vẫn có thể lưu theo quy tắc | Nội dung không được chia sẻ giữa người dùng |
| **no-store** | Cache tuân thủ chỉ thị không lưu response | Trang/response nhạy cảm, cần tránh lưu nội dung |
| **no-cache** | Có thể lưu, nhưng phải **xác minh với origin trước khi tái sử dụng** | HTML cần cập nhật khi nội dung thay đổi |
| **max-age=N** | Thời gian tính bằng giây response còn mới theo cache HTTP | Browser và cache có liên quan |
| **s-maxage=N** | TTL ưu tiên cho **shared cache**, nếu được hỗ trợ/tuân thủ | CDN giữ bản công khai lâu hơn browser |
| **must-revalidate** | Khi response đã stale, không dùng lại nếu chưa xác minh hợp lệ | Nội dung phải kiểm tra lại sau hết hạn |
| **immutable** | Gợi ý nội dung không đổi trong khoảng thời gian còn mới | Asset có hash trong tên |
| **stale-while-revalidate=N** | Cho phép một số cache phục vụ bản stale trong cửa sổ N giây khi revalidate nền | Public content chấp nhận trễ cập nhật |
| **stale-if-error=N** | Có thể dùng bản stale có giới hạn khi gặp lỗi phù hợp | Nội dung công khai ưu tiên tính sẵn sàng |

**Hai nhầm lẫn phổ biến:**

- **no-cache không có nghĩa là “không lưu”.** Nó yêu cầu xác minh trước khi tái sử dụng bản đã lưu. Muốn tránh lưu, dùng **no-store** và áp dụng chính sách phù hợp với dữ liệu.
- **TTL hết không có nghĩa cache đã xóa bản sao.** Cache có thể giữ bản stale để revalidate hoặc áp dụng chỉ thị cho phép sử dụng stale. Cần phân biệt “không còn fresh” với “đã purge”.

### 4.1. Ví dụ 1: tài nguyên tĩnh có hash

~~~http
HTTP/1.1 200 OK
Content-Type: text/javascript; charset=utf-8
Cache-Control: public, max-age=31536000, immutable
ETag: "js-bundle-a71c"
~~~

Giả sử đường dẫn là **/assets/app.a71c.js** và hậu tố **a71c** được tạo từ nội dung build. TTL một năm chỉ phù hợp nếu **URL này không bao giờ bị dùng cho nội dung khác**. Khi đổi code, tạo tên mới như **app.9fe2.js** thay vì ghi đè app.a71c.js.

### 4.2. Ví dụ 2: HTML public cần cập nhật sớm

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Cache-Control: public, max-age=0, s-maxage=60, stale-while-revalidate=30
ETag: "home-v42"
~~~

Cấu hình minh họa: browser cần revalidate theo max-age=0, còn shared cache có thể giữ response fresh trong 60 giây, sau đó một số cache có thể dùng stale thêm tối đa 30 giây khi revalidate. Chỉ dùng khi HTML thực sự **không cá nhân hóa** và hệ thống chấp nhận độ trễ cập nhật. Cần xác minh hỗ trợ của nhà cung cấp và cấu hình edge.

### 4.3. Ví dụ 3: nội dung nhạy cảm sau đăng nhập

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store
~~~

Đây là cấu hình minh họa cho API có thông tin riêng người dùng. Để an toàn hơn, chính sách CDN còn phải **bypass caching** với các đường dẫn xác thực, không dựa riêng vào header ứng dụng nếu CDN có cấu hình ghi đè.

### 4.4. Ví dụ 4: public API có dữ liệu chấp nhận trễ ngắn

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=15, s-maxage=90, stale-while-revalidate=30
Vary: Accept-Encoding
~~~

Chỉ phù hợp nếu mọi caller có cùng URL/cache key thực sự được phép xem **cùng một kết quả**, dữ liệu được phép cũ tối đa trong khoảng đã xác định và origin không phụ thuộc session/cookie/token. Nếu tồn kho thay đổi liên tục, TTL 90 giây có thể không đáp ứng tính đúng đắn nghiệp vụ.

### 4.5. CDN có thể có chính sách riêng

Một số CDN cung cấp **cache rule, origin TTL override, minimum/maximum TTL, cache status và error caching** riêng. Vì thế:

1. Đừng suy đoán chỉ từ Cache-Control của origin.
2. Kiểm tra precedence thực tế giữa header từ origin và chính sách edge.
3. Cấu hình phương án thử **HIT/MISS/REVALIDATED** và kiểm tra header phản hồi.
4. Bảo đảm rule mới không vô tình cache response có Authorization, Cookie hoặc Set-Cookie.

## 5. ETag, Last-Modified và revalidation

Khi cache có bản đã stale, nó có thể gửi **conditional request** tới origin thay vì tải toàn bộ nội dung.

- **ETag** là định danh validator cho một phiên bản biểu diễn. Cache gửi **If-None-Match** để hỏi xem nội dung còn khớp không.
- **Last-Modified** là thời điểm chỉnh sửa do origin công bố. Cache gửi **If-Modified-Since**; tính chính xác và ý nghĩa phụ thuộc ứng dụng.
- Nếu nội dung chưa thay đổi, origin có thể trả **304 Not Modified** và cache tái sử dụng bản body đang có, cập nhật metadata phù hợp.
- Nếu đã thay đổi, origin trả body mới (thường **200 OK**) cùng header thích hợp.

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant E as CDN Edge
    participant O as Origin
    U->>E: GET /public/menu.json
    Note over E: Bản sao đã hết thời gian fresh
    E->>O: GET + If-None-Match: "menu-v7"
    alt Nội dung chưa thay đổi
      O-->>E: 304 Not Modified + header cần thiết
      E-->>U: 200 từ body đang cache
    else Nội dung đã đổi
      O-->>E: 200 + ETag: "menu-v8" + body mới
      E-->>U: 200 + body mới
    end
~~~

**304 không phải là cache hit không cần origin:** revalidation vẫn dùng đường mạng đến origin, dù tiết kiệm dung lượng body. Khi phân tích hiệu quả, cần tách lượt trả trực tiếp từ cache với lượt revalidate.

Với nội dung đã được gắn hash vào tên, revalidation thường ít cần thiết trong khoảng còn fresh. Với HTML hay danh mục công khai thay đổi thường xuyên, validator giúp tránh truyền lại body nếu không đổi.

## 6. Cache key: điều kiện để đúng nội dung và không rò rỉ

Cache key là tập thuộc tính khiến CDN xác định một phiên bản response. Trong nhiều triển khai, nó có thể gồm **scheme, host, path, query parameters** và một số header/cookie được cho phép. Cấu hình mặc định không giống nhau giữa các nhà cung cấp.

Ví dụ:

- **/images/item.jpg?w=200** và **/images/item.jpg?w=800** phải được phân biệt nếu body khác kích thước.
- **/catalog?lang=vi** và **/catalog?lang=en** phải khác bản nếu ngôn ngữ tạo khác nội dung.
- Một tham số tracking không ảnh hưởng body, như **utm_source**, có thể được loại khỏi cache key **sau khi xác minh origin không dùng nó để thay đổi nội dung**.
- Response phụ thuộc Cookie, Authorization hoặc tenant không được dùng chung cache key với người không có quyền.

### 6.1. Vary và negotiated content

Header **Vary** cho biết những request header nào ảnh hưởng lựa chọn response, ví dụ:

~~~http
Vary: Accept-Encoding
~~~

Có thể dùng Vary với Accept-Language hoặc một header định dạng ảnh đã chuẩn hóa, nhưng **không nên thêm tùy tiện mọi header**. Quá nhiều biến thể làm giảm hit ratio, tăng chi phí và có thể tạo rủi ro cache fragmentation. Ngoài ra, cần kiểm tra CDN có thực sự tôn trọng Vary và tạo cache key tương ứng hay không.

### 6.2. Một cache key thiếu thuộc tính có thể gây lộ dữ liệu

Giả sử API có URL **/api/profile** và trả hồ sơ người đăng nhập dựa trên cookie. Nếu CDN cache response rồi phục vụ cho request khác chỉ vì URL giống nhau, có thể lộ dữ liệu cá nhân.

Không dùng giải pháp “thêm toàn bộ cookie vào cache key” như một cách sửa chung: nó phức tạp, dễ sai và còn có vấn đề quản lý quyền. Với hồ sơ và giao dịch riêng tư, **bypass shared cache** thường an toàn và đơn giản hơn.

Nếu yêu cầu sản phẩm thật sự cần cache nội dung riêng theo tenant hoặc người dùng, phải thiết kế có đánh giá bảo mật: identity đã xác thực, quyền sử dụng, phân vùng khóa, thời gian sống, cơ chế thu hồi và phép thử truy cập chéo. Một cache key chứa tenant_id tự khai từ client **không phải** bằng chứng ủy quyền.

### 6.3. Chuẩn hóa URL và cache poisoning

Những điểm cần rà soát:

- URL khác nhau chỉ ở dấu gạch, mã hóa ký tự, chữ hoa/thường, query order hoặc tham số trùng có được hiểu giống nhau không?
- Origin có dùng Host, forwarded headers hoặc query không nằm trong cache key để tạo URL chuyển hướng/HTML không?
- Response phụ thuộc Authorization, Cookie, Origin hoặc ngôn ngữ có được đánh dấu và key đúng cách không?
- Request path lạ có thể vượt qua bypass rule cho **/api/private** hoặc tài nguyên quản trị không?
- CDN có cache **redirect, lỗi 404/500 hoặc Set-Cookie** theo các rule vô tình cho phép không?

**Cache poisoning** xảy ra khi kẻ tấn công ảnh hưởng một response có thể cache, khiến người dùng khác nhận nội dung không mong muốn. Kiểm soát gồm chuẩn hóa request nhất quán, chỉ cho phép host/header cần thiết, phân tách nội dung cá nhân, kiểm thử các biến thể đường dẫn và cache key với origin thực tế.

## 7. Triển khai tài nguyên tĩnh: kết hợp URL bất biến và HTML cập nhật nhanh

Một pipeline frontend điển hình tạo các tệp:

~~~text
index.html
assets/
  app.8fe21a4.js
  style.b713e1c.css
  logo.4d92c30.svg
  font.6a8bf10.woff2
~~~

Các chuỗi trong tên file là **ví dụ hash nội dung**. Cùng nội dung tạo cùng tên theo cách build xác định; thay đổi nội dung làm thay đổi tên.

### 7.1. Vì sao cache lâu asset nhưng cache ngắn HTML?

**HTML** tham chiếu tên CSS/JS mới nhất. Nếu HTML được cache quá lâu sau khi phát hành, người dùng có thể tiếp tục nhận phiên bản cũ. Ngược lại, các tệp có hash cũ nên vẫn tồn tại trong một thời gian vì có thể còn HTML cũ đang được phục vụ từ browser/CDN hoặc trang đã mở trước đó.

| Tài nguyên | Mẫu chính sách | Lý do |
| --- | --- | --- |
| **/index.html** public | no-cache, hoặc shared TTL ngắn được phê duyệt | Cho phép thấy manifest/version mới sớm |
| **/assets/app.hash.js** | public, max-age dài, immutable | Không bao giờ dùng cùng URL cho body khác |
| **/assets/style.hash.css** | public, max-age dài, immutable | Tránh tải lặp và giảm origin |
| **/api/me** | private, no-store; bypass edge cache | Dữ liệu người dùng |
| **/downloads/private/report.csv** | Truy cập có kiểm tra quyền; không chia sẻ tùy tiện | Tài liệu riêng và có thể bị thu hồi |

### 7.2. Trình tự phát hành an toàn

~~~mermaid
flowchart TD
    A["Build asset chứa hash"] --> B["Upload asset mới lên object storage"]
    B --> C["Kiểm tra tồn tại / MIME / integrity"]
    C --> D["Phát hành HTML/manifest mới"]
    D --> E["Revalidate / purge HTML nếu chính sách cần"]
    E --> F["Theo dõi 404, lỗi JS, hit ratio và LCP"]
    F --> G["Giữ asset cũ trong thời gian chuyển tiếp đã chốt"]
~~~

**Tại sao upload asset trước HTML?** Nếu HTML mới được phát hành trước và tham chiếu một file JS chưa có ở origin, cache miss sẽ trả 404, làm người dùng nhận trang hỏng. Nếu asset cũ bị xóa ngay sau deploy, người dùng đang giữ HTML cũ cũng có thể gặp lỗi tải chunk.

Ngoài ra:

- Dùng upload/đồng bộ có kiểm tra thay đổi để không ghi đè nội dung của URL đã đánh dấu immutable.
- Thiết lập **Content-Type chính xác** cho JS, CSS, ảnh, font và các tệp khác; kiểm tra hành vi nén nếu đối tượng đã được nén trước.
- Dùng pipeline và hạ tầng khai báo để ghi lại phiên bản đang phục vụ, có khả năng rollback HTML/manifest.
- Có chính sách lưu giữ asset cũ, giới hạn dung lượng và truy vết phiên bản; thời hạn lưu cần phù hợp TTL và trải nghiệm người dùng.
- Nếu ứng dụng có **Service Worker**, cần thêm chiến lược cập nhật service worker vì nó tạo một lớp cache khác, có vòng đời riêng.
- Nếu có build frontend dùng chunk tải động, thử điều hướng từ tab cũ sau khi deploy mới để phát hiện lỗi missing chunk.

### 7.3. Single Page Application (SPA) và fallback

SPA thường cần trả **index.html** cho route điều hướng không trỏ tới tệp cụ thể, ví dụ **/dashboard/orders**. Nhưng quy tắc fallback không được biến **/assets/missing.js** thành HTTP 200 với HTML, vì trình duyệt sẽ báo lỗi phân tích JavaScript khó chẩn đoán.

Nên giới hạn fallback cho request điều hướng phù hợp, còn tài nguyên mất phải trả **404/410** theo ý nghĩa chính xác. Chú ý policy cache cho response lỗi: một 404 được cache lâu ngay trước khi asset upload xong có thể khiến lỗi tồn tại dù file đã có.

## 8. Tối ưu nội dung và kết nối tại biên

CDN không thay thế tối ưu tài nguyên. Một trang tải 10 MB JavaScript và ảnh không cần thiết vẫn có thể chậm dù cache hit 100%.

### 8.1. Ảnh và phương tiện

- Phục vụ ảnh theo kích thước hiển thị, độ phân giải và khả năng thiết bị; tránh gửi ảnh lớn rồi thu nhỏ bằng CSS.
- Cân nhắc định dạng hiện đại phù hợp nội dung và client (WebP/AVIF khi hỗ trợ), có fallback cần thiết.
- Kiểm soát biến thể cache: nếu cho phép tham số kích thước bất kỳ, kẻ xấu có thể tạo vô số biến thể và tăng chi phí xử lý/lưu trữ.
- Dùng lazy loading cho ảnh ngoài vùng nhìn; ưu tiên preload/priority hợp lý cho hình ảnh ảnh hưởng **Largest Contentful Paint (LCP)**.
- Video lớn thường dùng cơ chế streaming và phân đoạn riêng; CDN nên được cấu hình theo yêu cầu Range/segment, quyền phát và phương thức caching thích hợp.

### 8.2. Nén và truyền tải

- Văn bản như HTML/CSS/JS/JSON có thể hưởng lợi từ Brotli hoặc gzip nếu client hỗ trợ.
- Không nên cố nén thêm những định dạng đã nén hiệu quả như nhiều ảnh/video; lợi ích có thể rất nhỏ.
- Kiểm tra nội dung gzip/Brotli có cùng URL nhưng khác content encoding được cache và phục vụ đúng theo **Accept-Encoding**.
- HTTP/2 và HTTP/3, TLS resumption, keep-alive và kết nối biên có thể cải thiện truyền tải tùy hạ tầng, trình duyệt và tuyến mạng.
- Giảm số lượng và kích thước resource quan trọng, tránh blocking CSS/JS không cần; đặt kỳ vọng dựa trên dữ liệu Real User Monitoring (RUM).

### 8.3. Khi nào edge compute có ích?

Edge function/worker có thể thực hiện rewrite URL, chuyển hướng khu vực, xác thực chữ ký, thêm header bảo mật hoặc cá nhân hóa **rất nhẹ**. Nhưng đưa logic nghiệp vụ và dữ liệu nhạy cảm lên edge làm tăng số nơi xử lý thông tin, cấu hình và bề mặt tấn công; cần xem ràng buộc vùng dữ liệu, secret, độ trễ gọi backend và chi phí request.

Nên bắt đầu từ các **quy tắc cache và static origin đơn giản**. Chỉ thêm edge code khi có bài toán đo được và năng lực vận hành phù hợp.

## 9. Bảo mật CDN, origin và dữ liệu người dùng

Một CDN nằm trên đường vào hệ thống nên các chính sách bảo mật phải nhất quán giữa client, edge và origin.

### 9.1. Kiểm soát quan trọng

1. **TLS từ client đến edge và edge đến origin:** cấu hình chứng chỉ, phiên bản giao thức và chính sách mã hóa theo yêu cầu; tránh để đường từ edge tới origin là HTTP không được bảo vệ cho dữ liệu cần bảo mật.
2. **Không để origin công khai ngoài ý muốn:** object storage chứa asset có thể sử dụng quyền chỉ cho CDN truy cập; application origin có firewall/network policy hoặc cơ chế xác thực nguồn yêu cầu phù hợp. Khả năng “origin chỉ cho edge” phụ thuộc tính năng nhà cung cấp, cần kiểm chứng.
3. **WAF, bot protection, DDoS và rate limiting:** bảo vệ sớm tại edge theo lưu lượng và chính sách rủi ro; không thay thế authorization tại ứng dụng.
4. **Hạn chế caching dữ liệu nhạy cảm:** bypass trang đăng nhập, token, giao dịch thanh toán, hồ sơ và dữ liệu theo quyền người dùng nếu chưa có thiết kế đặc biệt.
5. **Signed URL/signed cookie:** hạn chế truy cập tài nguyên được cấp quyền trong thời gian hữu hạn. Phải quản lý nơi ký, rotation, phạm vi đường dẫn, hạn dùng và hành vi sau thu hồi.
6. **Không tin header do client tự gửi:** đặc biệt host, forwarded host, tenant ID, IP origin và các header được dùng để tạo redirect/cache key.
7. **Header bảo mật ứng dụng:** cân nhắc Content-Security-Policy (CSP), HSTS, X-Content-Type-Options và chính sách CORS theo nhu cầu; CDN có thể giúp áp dụng nhưng phải kiểm tra tương thích.
8. **Log và dữ liệu cá nhân:** lọc token, cookie, query có bí mật và thông tin nhạy cảm trước khi lưu vào edge logs/analytics; kiểm soát thời gian lưu, truy cập và vùng lưu trú.

### 9.2. Signed URL không đồng nghĩa không có cache

Một URL có chữ ký có thể cho phép edge xác minh quyền truy cập trước khi trả body từ cache; cách thực thi phụ thuộc thiết kế và hỗ trợ CDN. Điều tối quan trọng là **không được phục vụ bản cache trước khi xác thực/ủy quyền cần thiết**.

Nếu dùng chung một object URL cho nhiều tenant nhưng quyền truy cập khác nhau, cần bảo đảm người không có quyền không lấy được tài nguyên chỉ vì bản sao đã được cache. Cũng phải tính đến việc URL đã phát có thể bị sao chép trong thời gian hiệu lực và khả năng thu hồi trước hạn.

### 9.3. Mối đe dọa minh họa

| Tấn công/sai sót | Tác động | Phòng vệ và phép thử |
| --- | --- | --- |
| Cache response hồ sơ dùng chung | Rò rỉ thông tin người dùng/tenant | Bypass authenticated content, kiểm tra key, test hai tài khoản |
| Cache poisoning qua header/path | Nhiều người nhận nội dung sai | Chuẩn hóa request, trusted header, thử biến thể URL |
| Truy cập trực tiếp object storage gốc | Bỏ qua kiểm soát tại CDN | Private origin, origin access policy, thử truy cập không qua CDN |
| Signed URL quá dài hạn | Link bị chia sẻ trái phép lâu | TTL hợp lý, phạm vi URL hẹp, cơ chế thu hồi khi cần |
| CDN rule bỏ qua Authorization | Lộ dữ liệu hoặc trả sai phiên | Bypass/auth checks, integration security tests |
| Tải file chứa mã độc qua CDN | CDN giúp phân phối nội dung nguy hiểm | Kiểm soát upload, quét nội dung phù hợp, MIME và content disposition |
| Edge logs chứa token/session | Rò rỉ qua hệ thống quan sát | Redact data, RBAC, retention, audit |
| Cấu hình wildcard/host sai | Phục vụ nội dung không đúng domain | Xác minh domain/cert/origin mapping, test Host header |

**Tư duy zero trust:** CDN và mạng nội bộ là lớp kiểm soát, nhưng ứng dụng vẫn phải tự xác minh quyền truy cập vào dữ liệu và nghiệp vụ quan trọng.

## 10. Độ tin cậy, failover và dữ liệu stale

CDN có thể giúp ứng dụng tiếp tục phục vụ tài nguyên tĩnh khi origin tạm chậm, nhưng **khả năng sống sót phụ thuộc việc bản sao đã được cache, chính sách stale, loại lỗi và thiết kế origin**.

### 10.1. Các kịch bản

- **Một PoP bị lỗi:** CDN có thể định tuyến tới vị trí khác tùy hệ thống và mạng; độ trễ và hit ratio có thể thay đổi.
- **Origin chậm hoặc quá tải:** cache HIT tiếp tục phục vụ nội dung đủ điều kiện; MISS có thể thất bại, phát sinh cache stampede.
- **Origin trả lỗi 5xx:** với nội dung công khai, stale-if-error hoặc stale serving có điều kiện có thể giúp người dùng nhận bản cũ. Không áp dụng bừa cho trạng thái thanh toán, giá cần nhất quán hoặc dữ liệu riêng.
- **Lỗi phân phối asset khi deploy:** HTML mới tham chiếu tệp chưa được upload, hoặc lỗi negative cache của 404. Cần quy trình publish và rollback.
- **Lỗi cấu hình CDN toàn cục:** một rule sai có thể ảnh hưởng mọi PoP đồng thời; cần kiểm thử/canary và kiểm soát thay đổi.
- **Origin mất cả region:** CDN không tự có dữ liệu chưa từng cache hoặc chưa đồng bộ ở origin dự phòng; thiết kế multi-region, failover và RTO/RPO phải được kiểm chứng độc lập.

### 10.2. Cache stampede, origin shield và request collapsing

Giả sử một asset phổ biến hết TTL cùng thời điểm ở nhiều PoP. Nếu tất cả đồng loạt truy vấn origin, tải có thể tăng đột ngột (**cache stampede/thundering herd**).

Giải pháp tùy nền tảng:

- **Origin shield/tiered caching:** giảm số request lên origin và hợp nhất nhu cầu từ nhiều PoP.
- **Request collapsing/coalescing:** gom các request đồng thời cho cùng cache key nếu CDN hỗ trợ.
- **TTL jitter hoặc làm mới chủ động:** tránh nhiều đối tượng cùng hết hạn, khi khả thi.
- **stale-while-revalidate:** với nội dung cho phép, trả bản cũ khi làm mới nền.
- **Autoscaling/rate limit tại origin:** giúp chịu MISS, nhưng không thay thế cache design.

### 10.3. Cache lỗi phải có giới hạn

Nhiều CDN cho phép cache riêng các status như 301, 302, 404, 500 hoặc 503. Điều này hữu ích trong một số trường hợp, nhưng có thể làm kéo dài lỗi sau khi backend hồi phục. Cần xem **negative caching TTL**, bảo đảm 404 tạm thời của asset mới không bị giữ lâu và không cache nhầm lỗi có thông tin riêng tư.

### 10.4. Failover phải giữ tính đúng đắn

Một origin dự phòng có thể ở AZ/region khác, dùng object storage replica hoặc môi trường ứng dụng dự phòng. Trước khi bật failover:

- Xác minh nội dung static đã đồng bộ, có phiên bản tương thích với HTML.
- Kiểm tra chính sách lưu trú dữ liệu tại vùng dự phòng.
- Xem đường DNS, TLS, origin failover và cache key có tạo vòng redirect không.
- Kiểm thử tình huống origin chính lỗi, CDN MISS tại PoP chưa có nội dung và người dùng quay lại.
- Đo RTO (thời gian khôi phục) và RPO (mức mất dữ liệu được chấp nhận) cho **các thành phần thực sự có dữ liệu cần bảo vệ**.

Với asset tĩnh versioned có thể tái tạo từ artifact build, RPO thường có cách đánh giá khác cơ sở dữ liệu giao dịch. Không đánh đồng khả dụng của ảnh/logo với khả dụng của quy trình đặt chỗ.

## 11. Đo hiệu quả CDN bằng chỉ số đúng mục tiêu

### 11.1. Phân biệt tỷ lệ HIT theo request và theo byte

**Request hit ratio** (mô hình đơn giản):

\[
H_{\text{request}}=\frac{\text{số request được CDN phục vụ từ cache}}{\text{tổng request có liên quan}} \times 100\%
\]

**Byte hit ratio**:

\[
H_{\text{byte}}=\frac{\text{số byte CDN phục vụ từ nội dung cache}}{\text{tổng byte CDN phục vụ trong phạm vi đo}} \times 100\%
\]

Một trang có 90% request HIT nhưng các file video lớn toàn MISS có thể vẫn tạo tải truyền dữ liệu lớn tại origin. Ngược lại, những request API động cố tình bypass CDN làm giảm hit ratio tổng thể nhưng **không phải lỗi**.

Cần thống nhất mẫu số: tính toàn bộ request, chỉ request cacheable, có tính revalidation, partial content/range, error hoặc edge function hay không? Các nhà cung cấp có định nghĩa metric khác nhau.

### 11.2. Các thước đo vận hành

| Nhóm | Chỉ số | Câu hỏi đặt ra |
| --- | --- | --- |
| **Cache** | Hit/miss ratio, byte hit ratio, revalidation count, bypass count | Nội dung phù hợp có đang được lưu và phục vụ đúng? |
| **Origin** | Origin requests/s, origin bandwidth, p95 origin latency, 5xx | CDN có thực sự giảm tải nguồn? |
| **Trải nghiệm** | p50/p95/p99 TTFB theo khu vực, LCP, INP, tải resource | Người dùng có nhận nội dung nhanh hơn không? |
| **Chất lượng** | 4xx/5xx, lỗi tải JS/CSS, cache stale, MIME errors, 404 asset | Có phục vụ đúng phiên bản và đường dẫn không? |
| **Bảo mật** | Request bị WAF/rate limit, lỗi chữ ký, truy cập origin bị từ chối | Kiểm soát có chặn đúng và không chặn nhầm? |
| **Chi phí** | CDN egress, requests, origin fetch, invalidation, edge compute, logging | Tổng chi phí có phù hợp ngân sách không? |
| **Vận hành** | Thời gian purge/publish, rollback, thay đổi rule, số incident | Có thể sửa sự cố nhanh và an toàn không? |

**TTFB** phụ thuộc DNS, kết nối TLS, đường mạng, thời gian edge xử lý, thời gian origin xử lý và cách đo của client. Một TTFB thấp không chắc cải thiện LCP nếu ảnh hero quá lớn hoặc JavaScript blocking.

### 11.3. Kiểm chứng bằng HTTP request

Có thể dùng một lệnh kiểm tra header:

~~~bash
curl -I https://static.example.com/assets/app.a71c.js
~~~

Khi thử thực tế, xem:

- Cache-Control, ETag, Last-Modified, Content-Type và Vary.
- Header cache status nếu CDN cung cấp, ví dụ HIT/MISS/BYPASS/REVALIDATED theo tên của nhà cung cấp.
- Age của response, khi xuất hiện, giúp suy luận thời gian bản sao ở shared cache; không phải mọi phản hồi đều có.
- Cùng URL ở lần đầu/lần sau, ở nhiều vị trí mạng, lúc chưa/đã hết TTL và sau deploy.
- API private với hai tài khoản khác nhau **không được trả chung nội dung**.

Tránh coi một lần curl từ máy local là đủ: điểm PoP, cookie, accept headers, cache warm-up, trạng thái origin và rule có thể khác theo địa lý hoặc môi trường.

## 12. Phân tích chi phí: CDN tiết kiệm ở đâu và tốn thêm ở đâu?

CDN có thể giảm traffic và tài nguyên origin, nhưng vẫn phát sinh chi phí riêng:

- Phí truyền dữ liệu từ CDN tới người dùng cuối, phụ thuộc khu vực và giá nhà cung cấp.
- Phí request và một số loại xử lý/biến đổi nội dung.
- Phí fetch từ origin, egress/cross-region nếu được tính.
- Phí WAF, bot protection, edge function, logging/analytics, purge nếu thuộc gói tính phí.
- Chi phí object storage, replica, hạ tầng dự phòng, vận hành và xử lý sự cố.
- Khác biệt về hợp đồng, bậc giá, vùng phục vụ và mô hình dự báo tải.

### Ví dụ tính nhẩm có nêu giả định

Giả sử trong một kỳ:

- Có **10 triệu lượt tải** tài nguyên công khai có thể cache.
- Kích thước trung bình **100 KB/lượt**; dùng đơn vị thập phân 1 KB = 1.000 byte.
- CDN đạt **90% byte hit ratio** trong phạm vi lưu lượng đang xét.
- Bỏ qua request revalidation, range request, overhead giao thức, nội dung động, purge và các lớp cache khác để dễ minh họa.

Khi đó:

\[
B_{\text{client}} = 10{,}000{,}000 \times 100{,}000
 = 1{,}000{,}000{,}000{,}000\text{ bytes} \approx 1 \text{ TB}
\]

\[
B_{\text{origin}} \approx (1-0{,}90)\times1\text{ TB}=0{,}1\text{ TB}=100\text{ GB}
\]

**Kết luận có điều kiện:** thay vì origin truyền gần 1 TB nội dung trực tiếp, lượng body fetch tại origin trong ví dụ còn khoảng 100 GB. Nhưng CDN **vẫn phải truyền khoảng 1 TB tới client**, và chi phí CDN egress vẫn cần tính. Không được suy từ 90% hit thành “tiết kiệm 90% hóa đơn cloud”.

**Ảnh hưởng của geography và cache fragmentation:** nếu mỗi PoP, query variant và phiên bản cần tự warm cache, origin fetch có thể cao hơn ước tính. Ngược lại, shield/tiered cache có thể giảm đáng kể lượng request lên origin.

### Bảng so sánh TCO cần lập

| Khoản mục | Không CDN | Có CDN | Cách thu thập |
| --- | --- | --- | --- |
| Origin compute | Có thể cao do phục vụ static trực tiếp | Có thể giảm khi phần tĩnh được offload | CPU/network/requests thực tế |
| Origin egress | Phục vụ trực tiếp client | Fetch từ edge và các luồng khác | Số byte origin và điều kiện tính phí |
| CDN egress | Không có | Có, thường là khoản mục lớn | Dự toán theo vùng và lưu lượng |
| CDN requests/processing | Không có | Có | Số request và loại tính năng |
| Storage, backup, replica | Có | Vẫn có | Dung lượng, chính sách lưu giữ |
| Bảo mật và quan sát | Ứng dụng tự gánh một phần | Có thể chuyển một số kiểm soát lên edge, thêm phí | WAF, logs, metrics, audit |
| Vận hành | Thay đổi origin/server | Thêm quản lý cache key, TTL, invalidation, cert, rules | Công vận hành, incident, pipeline |

Lập ít nhất ba kịch bản: **lưu lượng bình thường, chiến dịch cao điểm và sự cố cache MISS/origin failover**. Kịch bản tệ nhất có thể xảy ra khi purge toàn bộ cache ngay trước thời gian cao điểm.

## 13. Thiết kế một kiến trúc CDN cho ứng dụng đặt chỗ

### 13.1. Bài toán nghiệp vụ

Một nền tảng đặt chỗ có:

- Website giới thiệu, danh sách dịch vụ và hàng nghìn ảnh công khai.
- Frontend SPA có tệp CSS/JS thay đổi vài lần mỗi tuần.
- API danh mục public, dữ liệu có thể chậm khoảng một phút nếu Product chấp nhận.
- API tìm chỗ, tạo booking, tài khoản, thanh toán và xác nhận giao dịch yêu cầu dữ liệu đúng quyền.
- Người dùng phân bố ở nhiều thành phố, có đợt lưu lượng đỉnh khi chạy chiến dịch.

Mục tiêu giả định: giảm p95 tải tài nguyên tĩnh ở các thị trường xa origin, giảm tải origin, không lộ dữ liệu tenant và giữ quy trình cập nhật/rollback an toàn. Các ngưỡng định lượng cụ thể cần được Product/SRE phê duyệt trước khi coi là yêu cầu nghiệm thu.

### 13.2. Sơ đồ đề xuất

~~~mermaid
flowchart TB
    U["Web / Mobile clients"] --> CDN["CDN: TLS, WAF, cache rules"]
    CDN -->|"Static HIT/MISS"| STO[("Object storage riêng tư\nHTML, CSS/JS hash, ảnh")]
    CDN -->|"Public catalog có TTL"| API["API Gateway / Load Balancer"]
    CDN -->|"Private API: BYPASS"| API
    API --> APP["Ứng dụng đặt chỗ đa AZ"]
    APP --> DB[("Database giao dịch")]
    APP --> CACHE[("Application cache theo nghiệp vụ")]
    CDN -. "Cache metrics / logs" .-> OBS["Monitoring, tracing, cost"]
    APP -. "SLI / traces" .-> OBS
~~~

Các đường có nhãn phân biệt chính sách cache; cùng một CDN endpoint có thể định tuyến theo host/path tới nhiều origin, nhưng quy tắc phải được triển khai và kiểm thử cụ thể.

### 13.3. Bảng chính sách đề xuất

| Đường dẫn minh họa | Origin | Edge cache | Browser cache | Lý do |
| --- | --- | --- | --- | --- |
| **/assets/*.hash.js, *.hash.css** | Object storage | Cache dài khi URL bất biến | Cache dài, immutable | Tối ưu tải lặp và triển khai theo phiên bản |
| **/images/catalog/*.hash.webp** | Object storage | Cache dài theo URL/biến thể | Cache dài | Nội dung public, ít thay đổi |
| **/**, **/landing** | Object storage/static site renderer | TTL ngắn hoặc revalidate | Revalidate | HTML tham chiếu asset build mới |
| **/api/public/catalog** | App/API | TTL ngắn theo tiêu chí độ mới | Ngắn hơn hoặc revalidate | Danh mục public, có giới hạn dữ liệu trễ |
| **/api/search/availability** | App/API | Bypass nếu cần tồn kho mới | Theo yêu cầu nghiệp vụ, thường không lưu tùy tiện | Tránh trả khả dụng cũ gây hiểu nhầm |
| **/api/bookings** | App/API | Bypass | no-store nếu chứa dữ liệu nhạy cảm | Tính đúng đắn và phân quyền |
| **/api/payment/status** | App/API | Bypass | no-store | Trạng thái giao dịch nhạy cảm |
| **/api/account/profile** | App/API | Bypass | no-store | Dữ liệu cá nhân |
| **/download/private/** | Object storage hoặc service cấp quyền | Có kiểm tra chữ ký/quyền nếu cache được phép; không cache chung tùy tiện | Theo chính sách dữ liệu | Dữ liệu riêng khách hàng |

Đây là **đề xuất minh họa**, không phải cấu hình có thể áp dụng nguyên xi. Cần xác định public/private bằng phân loại dữ liệu thực tế và kiểm tra mọi rule, kể cả lỗi, redirect, query, cookies, phương thức HTTP khác GET/HEAD.

### 13.4. Kịch bản deploy/frontend

1. Build frontend, tạo asset chứa hash và manifest.
2. Upload tất cả asset mới, xác minh quyền object origin, MIME, checksum và URL.
3. Phát hành HTML mới sau khi asset đã sẵn sàng.
4. Revalidate/purge những HTML cần cập nhật; tránh purge toàn bộ asset dài hạn.
5. Chạy synthetic test từ vài vị trí mạng với route SPA, asset và API private.
6. Theo dõi 404 asset, lỗi JavaScript, p95 TTFB, LCP, cache HIT và origin requests.
7. Nếu rollback, đổi HTML/manifest về phiên bản cũ còn được lưu giữ; kiểm tra phiên bản cũ có còn đủ chunk/asset.

### 13.5. Các thử nghiệm cần qua trước go-live

| Kiểm thử | Điều kiện đạt |
| --- | --- |
| Tệp JS/CSS theo hash | Hai version giữ URL riêng, cache header đúng, không có 404 sau rollout/rollback |
| HTML public | Nội dung mới xuất hiện trong thời gian cập nhật đã cam kết, không giữ HTML cũ quá giới hạn |
| API riêng của hai người dùng | Không thể trả dữ liệu chéo tài khoản/tenant do shared caching |
| Public catalog cache | Độ mới nằm trong giới hạn được phê duyệt, query variant cho kết quả đúng |
| Origin chậm/mất tạm thời | HIT vẫn đáp ứng theo chính sách; MISS và thông báo lỗi theo runbook |
| DDoS/rate limit/WAF | Có khả năng giới hạn lưu lượng, tỷ lệ chặn nhầm được kiểm tra |
| Chi phí chiến dịch | Dự báo CDN egress, origin traffic và cache cold-start trong ngân sách |
| Region lưu dữ liệu/log | Vị trí cache, logs, origin/replica và quyền truy cập được Security/Legal xác nhận khi có ràng buộc |

## 14. Quy trình quyết định và đánh đổi kiến trúc

### 14.1. Câu hỏi cần trả lời trước khi mua/cấu hình CDN

1. **Loại nội dung nào có thể chia sẻ?** Có dữ liệu đăng nhập, tenant hoặc thông tin cá nhân không?
2. **Người dùng ở đâu?** Đo p95 TTFB/LCP theo mạng, địa lý, thiết bị, thay vì chỉ suy từ bản đồ.
3. **Nội dung cần mới đến mức nào?** 1 giây, 1 phút hay 1 ngày; tính đúng đắn nghiệp vụ bị ảnh hưởng ra sao nếu stale?
4. **Nguồn dữ liệu ở đâu?** Object storage, application server, nhiều origin hoặc region dự phòng; có truy cập riêng tư không?
5. **Lưu lượng và đối tượng phân phối là gì?** Kích thước tệp, phân phối theo địa lý, tần suất thay đổi, cache key variations.
6. **Hệ thống phải chịu lỗi nào?** PoP, origin, CDN control plane, region và CDN rule thay đổi?
7. **Ngân sách nào?** CDN egress, requests, origin, log, WAF, edge compute, vận hành và DR.
8. **Ai vận hành?** Quyền đổi rule, cấp chứng chỉ, purge khẩn, rollback, xử lý cache poisoning và theo dõi chỉ số.

### 14.2. So sánh ba phương án

| Phương án | Ưu điểm | Hạn chế | Thường hợp lý khi |
| --- | --- | --- | --- |
| **A. Origin trực tiếp** | Ít thành phần, quy tắc cache đơn giản hơn | Tải static dồn về origin, latency cao ở xa, tốn tài nguyên | Hệ thống nội bộ, ít người dùng gần origin, tệp nhỏ |
| **B. CDN trước static origin** | Offload tệp công khai, triển khai asset hiệu quả, giảm độ trễ nhiều khu vực | Cần policy cache, invalidation, logging và cấu hình quyền origin | Website/SPA/ảnh public phục vụ nhiều nơi |
| **C. CDN trước static và public API phù hợp** | Có thêm khả năng giảm tải API đọc công khai | Cache key và freshness phức tạp hơn; nguy cơ dữ liệu sai/chia sẻ nhầm | Public API có dữ liệu và TTL được phê duyệt rõ |

Không nên đưa toàn bộ API qua shared caching chỉ vì CDN ở phía trước hệ thống. Với private API, vẫn có thể dùng CDN làm **reverse proxy/security ingress** nhưng caching cần bị bypass.

### 14.3. Mẫu ADR

~~~markdown
# ADR-024: Phân phối tài nguyên tĩnh qua CDN

Trạng thái: Đề xuất / chấp thuận có điều kiện
Owner: Kiến trúc sư, SRE và Product
Ngày: YYYY-MM-DD

Bối cảnh:
- Người dùng ở nhiều vùng mạng; trang có CSS/JS và ảnh công khai.
- Origin hiện phục vụ tài nguyên tĩnh cùng với API giao dịch.
- API tài khoản và thanh toán chứa dữ liệu theo quyền người dùng.

Lựa chọn:
A. Origin trực tiếp.
B. CDN + object storage riêng tư cho nội dung công khai.
C. CDN + static + một số public API có TTL ngắn.

Quyết định:
- Chọn B trước, xem C sau khi có bằng chứng freshness và security.
- Asset có tên chứa hash được cache dài; HTML revalidate.
- API private BYPASS shared cache; bảo vệ đường vào origin.

Đánh đổi/rủi ro:
- Cache miss lạnh vẫn phụ thuộc origin.
- Cấu hình nhầm cache key có thể lộ dữ liệu.
- CDN egress và logging phát sinh chi phí.

Tiêu chí nghiệm thu:
- Đo p95 TTFB/LCP theo vùng; cache/offload đúng.
- Thử hai tài khoản không lộ dữ liệu.
- Deploy/rollback asset không lỗi 404.
- Dự báo TCO tại lưu lượng thường và cao điểm.

Điều kiện xem lại:
- Lưu lượng/chi phí thay đổi lớn, có nhu cầu public API caching,
  hoặc SLO, chính sách dữ liệu và mức stale cho phép thay đổi.
~~~

## 15. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi rà soát CDN/edge |
| --- | --- |
| **Operational Excellence** | Cache rules có version, review, canary/rollback, runbook purge và dashboard không? |
| **Security** | TLS, WAF, quyền origin, signed URL, dữ liệu riêng, cache key và log có được kiểm tra không? |
| **Reliability** | Origin miss khi mất region ra sao? Có kiểm thử 404, stale, cold cache, failover, CDN misconfiguration không? |
| **Performance Efficiency** | CDN thực sự giảm p95 TTFB/LCP và origin saturation ở các địa điểm người dùng không? |
| **Cost Optimization** | Có dự báo cả CDN egress, origin fetch, logs, invalidation và edge compute theo tải không? |
| **Sustainability** | Có giảm truyền lặp, kích thước asset, lưu trữ không cần thiết và tài nguyên origin nhàn rỗi không? |

Sáu trụ cột là **khung đặt câu hỏi và tìm bằng chứng**. Chúng không bảo đảm dùng CDN sẽ luôn tốt hơn; một hệ thống nội bộ với người dùng cạnh origin và nội dung động có thể không hưởng lợi tương xứng với độ phức tạp mới.

## 16. Lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cache mọi response theo URL | Rò rỉ dữ liệu khi URL giống nhau nhưng session/tenant khác | Phân loại public/private, bypass theo path/auth, test hai tài khoản |
| Cache HTML như asset immutable | Người dùng giữ giao diện cũ, tham chiếu bundle không còn tồn tại | HTML TTL ngắn/revalidate; bundle URL chứa hash |
| Ghi đè URL của bundle có TTL một năm | Người dùng nhận code cũ và mới không nhất quán | Build asset bất biến theo hash, giữ phiên bản cũ |
| Deploy HTML trước asset | 404 JavaScript/CSS ở lần đầu truy cập | Upload và kiểm tra asset trước khi phát HTML |
| Xóa asset cũ ngay sau deploy | Tab cũ không tải được chunk động | Chính sách retention bao phủ thời gian chuyển tiếp |
| Bỏ qua query khi query thay đổi nội dung | Trả sai ảnh/ngôn ngữ/kết quả | Cache key theo tham số có tác động |
| Đưa tất cả cookie/header vào key | Cache phân mảnh, tốn bộ nhớ và khó audit | Chỉ whitelisting biến thể cần thiết; private bypass |
| Tin TTL từ origin dù edge override | Không đạt yêu cầu freshness | Đọc cấu hình CDN và test header thực |
| Cache 404 quá lâu | Lỗi asset còn sau khi object đã có | Negative caching ngắn và kiểm thử deployment |
| Chỉ theo hit ratio | Không thấy origin egress lớn hoặc chất lượng người dùng kém | Đo byte hit, TTFB/LCP, miss cost, lỗi và trải nghiệm |
| Coi CDN là cơ chế bảo vệ origin đủ dùng | Có thể truy cập trực tiếp origin và bỏ qua WAF | Private origin/allowlist và identity phù hợp |
| Coi CDN là giải pháp DR đầy đủ | Cache miss vẫn fail nếu origin mất | Backup, replica, failover và kiểm thử theo RTO/RPO |
| Chỉ nhìn phí origin giảm | Bỏ phí CDN egress, WAF, logs, edge function | Dự báo TCO end-to-end |
| Purge toàn bộ trước chiến dịch | Lượng MISS lớn tạo cache stampede | Invalidation có phạm vi, prewarm/shield khi cần |

## 17. Bài tập thực hành

Một nền tảng thương mại điện tử chạy tại một cloud region phục vụ khách hàng ở ba quốc gia. Website có 15 MB tài nguyên tĩnh khi tải lần đầu (bao gồm ảnh), tệp JS/CSS phát hành hai lần mỗi tuần, danh mục public được cập nhật mỗi phút, giỏ hàng và thanh toán bắt buộc theo phiên đăng nhập. Công ty chuẩn bị một chiến dịch gấp năm lần tải bình thường. SRE nhận thấy lưu lượng tại origin tăng mạnh và người dùng ở xa có p95 TTFB cao.

Hãy thực hiện:

1. **Vẽ kiến trúc as-is và to-be:** client, DNS, CDN PoP, optional shield, object storage, API gateway, application, database, monitoring.
2. **Phân loại tài nguyên:** HTML, JS/CSS, ảnh, public catalog API, giỏ hàng, thanh toán và file tải riêng; chọn cache/bypass, TTL và cách xác minh độ mới.
3. **Thiết kế cache key:** cho một API danh mục có tham số language và category, và một dịch vụ ảnh có width và format. Nêu biến nào được phép bỏ qua và vì sao.
4. **Viết header:** Cache-Control cho bundle hash, HTML public, public API và API hồ sơ; giải thích khác nhau giữa no-cache và no-store.
5. **Thiết kế phát hành:** nêu thứ tự upload asset, publish HTML, kiểm thử và rollback; xử lý tab cũ tải chunk cũ.
6. **Threat model ngắn:** ít nhất ba đường dẫn có nguy cơ cache poisoning hoặc lộ dữ liệu; đề xuất phép thử để chứng minh ranh giới quyền.
7. **Chịu sự cố:** mô tả cách ứng xử khi origin trả 503, cache MISS tăng vọt và CDN cấu hình nhầm; xác định nội dung nào có thể phục vụ stale.
8. **Tính chi phí sơ bộ:** ước lượng client egress, origin fetch với ít nhất hai kịch bản byte hit ratio, thêm chi phí CDN request/WAF/log và kế hoạch theo dõi thực tế.
9. **Đặt tiêu chí nghiệm thu:** p95 TTFB theo quốc gia, LCP, lỗi 404 asset, hit ratio, origin load, bảo mật hai tài khoản và chi phí chiến dịch.
10. **Viết ADR:** lựa chọn phương án CDN, lợi ích, điều kiện bắt buộc, rủi ro còn lại và trigger xem xét lại.

**Gợi ý tự đánh giá:** bài làm tốt không chỉ đạt hit ratio cao; nó chứng minh nội dung **đúng người, đúng phiên bản, đúng độ mới**, vẫn hoạt động khi cache lạnh, có kế hoạch rollback và đo được lợi ích trên trải nghiệm người dùng cùng tổng chi phí.

## 18. Checklist trước khi đưa CDN vào production

- [ ] Xác định rõ những nội dung được phép cache và nội dung cần bypass do quyền truy cập, dữ liệu riêng hoặc tính đúng đắn.
- [ ] Vẽ đường đi client → edge → shield (nếu có) → origin → ứng dụng/data, gồm trust boundary và dependency.
- [ ] Kiểm tra Cache-Control, s-maxage/max-age, ETag, Last-Modified, Vary và các rule override tại CDN.
- [ ] Thiết kế cache key đúng theo host/path/query/header/biến thể được phép, chuẩn hóa URL an toàn.
- [ ] Có quy tắc không cache nhầm Authorization, Cookie, Set-Cookie, private HTML/API và nội dung tenant.
- [ ] Tài nguyên có hash là immutable; HTML/manifest có chính sách cập nhật nhanh và rollback rõ.
- [ ] Upload asset trước HTML và giữ asset cũ đủ lâu cho tab/browser cache cũ.
- [ ] Kiểm thử SPA fallback, MIME, nén, font/CORS, ảnh biến thể và negative caching.
- [ ] Bảo vệ truy cập trực tiếp origin; kiểm tra TLS, WAF, rate limit, signed resource và logging.
- [ ] Kiểm thử cross-user/cross-tenant cache leaks, cache poisoning và lỗi signed URL.
- [ ] Kiểm thử cold cache, cache stampede, origin 5xx, purge sai, mất vùng và quy trình failover.
- [ ] Đo request/byte hit ratio, origin offload, p95 TTFB, LCP, error rate và cost/request.
- [ ] Có dashboard, cảnh báo, owner, quyền thay rule, kế hoạch canary và runbook incident.
- [ ] Đối chiếu phí CDN, origin, egress, logs, WAF, DR với ngân sách ở tải bình thường và đỉnh.
- [ ] Có ADR ghi đánh đổi, bằng chứng kiểm thử, rủi ro còn lại và điều kiện xem xét lại.

## Ghi nhớ

**CDN** đặt điểm phân phối nội dung trên đường vào hệ thống, phục vụ bản sao có thể cache gần người dùng và giảm tải lặp lại ở origin. **Edge cache** chỉ hiệu quả và an toàn khi biết chính xác nội dung nào được phép dùng chung, cache key có đủ biến thể và TTL phù hợp yêu cầu độ mới. Với **tài nguyên tĩnh**, chiến lược thường hiệu quả là **URL có hash nội dung + cache dài**, kết hợp **HTML/manifest revalidate hoặc cache ngắn** và pipeline phát hành có rollback.

Một thiết kế cloud đáng tin cậy phải chứng minh đồng thời **hiệu năng, tính đúng đắn, bảo mật, khả năng khôi phục, khả năng mở rộng, chi phí và vận hành** qua chỉ số thực và thử nghiệm có chủ đích. CDN là một công cụ trong kiến trúc điểm vào hệ thống, không thay thế các quyết định về dữ liệu, ứng dụng và DR phía sau.
