# Vary, bộ nhớ đệm preflight và phản hồi qua CDN

## 1. Bài toán: CORS hoạt động ở máy phát triển nhưng lỗi sau CDN

Một ứng dụng Spring Security phục vụ API tại `https://api.example.com`, với hai giao diện được tin cậy:

- `https://app.example.com`: ứng dụng người dùng.
- `https://admin.example.com`: ứng dụng quản trị.

API dùng CORS allowlist, có thể nhận session cookie khi frontend sử dụng `credentials: "include"`. Ở môi trường local, hai frontend gọi API thành công. Sau khi đưa CDN vào trước API, nhóm phát triển thấy các triệu chứng khó hiểu:

- Frontend A gọi thành công, frontend B cùng gọi endpoint nhưng browser báo `Access-Control-Allow-Origin` không khớp.
- Preflight `OPTIONS` lúc được chấp nhận, lúc bị từ chối dù ứng dụng đã sửa `allowedMethods` hoặc `allowedHeaders`.
- Sau lần triển khai chính sách mới, một số browser tiếp tục dùng quyền preflight cũ trong một khoảng thời gian.
- Response cá nhân hóa hoặc dữ liệu quản trị có nguy cơ được CDN cache theo URL nhưng không phân biệt phiên/người dùng.
- Phản hồi từ gateway/CDN không còn giữ `Vary` hoặc bị chèn một header CORS khác với backend.

Để giải quyết, cần hiểu **ba lớp quyết định riêng**:

1. **CORS policy:** browser có được đọc response khác origin và gửi actual request sau preflight hay không?
2. **Bộ nhớ đệm preflight riêng của browser:** kết quả cấp quyền OPTIONS được lưu bao lâu?
3. **HTTP cache của browser, proxy và CDN:** response HTTP nào có thể được tái sử dụng cho những request tiếp theo?

Bài thuộc chương **CORS** của `SPRING_SECURITY_HTTP_PROTECTION`. Thiết kế cache không chỉ ảnh hưởng đến CORS mà còn liên quan authentication, authorization, CSRF, session cookie, security headers, CSP, HSTS và HTTP firewall. Ví dụ bao quát **Servlet/Spring MVC** và **Reactive/WebFlux**.

### Mục tiêu

Sau bài học, người học có thể:

1. Giải thích ý nghĩa của `Vary: Origin` và `Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers`.
2. Phân biệt `Access-Control-Max-Age` với `Cache-Control`, `Age`, `ETag` và cache chính của CDN.
3. Hiểu vì sao CDN phải tách các biến thể CORS theo origin, đồng thời không trộn dữ liệu riêng tư của nhiều người dùng.
4. Thiết kế chính sách cache cho API public và API dùng cookie/`Authorization`.
5. Cấu hình CORS trong Spring Security Servlet và Reactive, kiểm thử preflight và actual response qua gateway.
6. Chẩn đoán lỗi cache theo origin, stale preflight, duplicate headers, CDN caching OPTIONS và response 401/403.

Tên miền `example.com` hoặc `example.org` dưới đây chỉ là ví dụ minh họa.

## 2. Ba loại cache không được đánh đồng

| Cơ chế | Lưu nội dung gì? | Tín hiệu điều khiển chính | Hệ quả |
| --- | --- | --- | --- |
| **CORS-preflight cache của browser** | Kết quả cho phép một tổ hợp request CORS có preflight | `Access-Control-Max-Age`; giới hạn nội bộ của browser | Browser có thể bỏ qua OPTIONS khi tiếp tục gửi request phù hợp |
| **HTTP cache của browser** | HTTP response hoặc các thành phần cacheable của nó | `Cache-Control`, `ETag`, `Last-Modified`, `Vary` | Browser có thể tái sử dụng hoặc revalidate response GET |
| **HTTP cache của CDN/reverse proxy** | Response do máy chủ nguồn phát ra, theo cache key và policy ở edge | HTTP cache directives và quy tắc CDN | Edge có thể phản hồi trước khi request đến Spring |

**Preflight cache là một bộ nhớ đệm riêng, không phải cùng bộ nhớ đệm HTTP tổng quát của browser.** Đừng xem `Cache-Control: no-store` trên response nghiệp vụ là lệnh chắc chắn xóa những quyền preflight mà trình duyệt đã lưu.

Đặc biệt, `Access-Control-Max-Age` **không phải** lệnh yêu cầu CDN cache OPTIONS trong 600 giây. CDN có quy tắc cache HTTP/edge riêng và nhiều hệ thống không cache OPTIONS mặc định.

### 2.1. Luồng có hai tầng cache

~~~mermaid
sequenceDiagram
    participant JS as JavaScript tại app.example.com
    participant BR as Browser
    participant CDN as CDN / Reverse proxy
    participant API as Spring Security API
    JS->>BR: fetch PUT JSON + X-CSRF-TOKEN
    BR->>BR: Kiểm tra CORS-preflight cache
    alt Không có kết quả preflight có hiệu lực
        BR->>CDN: OPTIONS + Origin + Request-Method + Request-Headers
        CDN->>API: Chuyển tiếp OPTIONS nếu gateway không tự xử lý
        API-->>CDN: CORS preflight response + Max-Age
        CDN-->>BR: Trả response
        BR->>BR: Kiểm tra CORS, lưu kết quả preflight phù hợp
    else Preflight cache còn hiệu lực
        BR->>BR: Không phải gửi OPTIONS mới
    end
    BR->>CDN: Actual PUT với Origin và credentials nếu được phép
    CDN->>API: Chuyển tiếp thao tác được bảo vệ
    API-->>CDN: Actual response
    CDN-->>BR: Phản hồi có CORS headers thích hợp
    BR-->>JS: Cho đọc response khi actual CORS hợp lệ
~~~

Sơ đồ giả định CDN **không cache hoặc không xử lý độc lập** OPTIONS và không cache các thao tác PUT nhạy cảm. Nếu edge chủ động xử lý preflight, nó phải thực thi một chính sách CORS nhất quán với backend, không đơn thuần trả 200.

## 3. `Vary` có tác dụng gì trong HTTP caching?

Header `Vary` nói với HTTP cache rằng việc lựa chọn một representation có thể phụ thuộc vào **giá trị của những request headers được liệt kê**.

Ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
Cache-Control: public, max-age=60

{"items":[{"id":1,"name":"Book"}]}
~~~

Ở đây response mang `Access-Control-Allow-Origin` dành cho `https://app.example.com`. Nếu CDN lưu response này, `Vary: Origin` yêu cầu cache phân biệt request có:

~~~http
Origin: https://app.example.com
~~~

với:

~~~http
Origin: https://admin.example.com
~~~

**Tác dụng cốt lõi:** tránh lấy representation của một origin để trả lại cho request có Origin khác nếu cache tuân thủ semantics `Vary`.

### 3.1. `Vary: Origin` không phải là CORS allowlist

So sánh:

| Header | Trách nhiệm |
| --- | --- |
| `Access-Control-Allow-Origin` | Cấp quyền browser đọc response cho origin cụ thể hoặc `*` trong trường hợp hợp lệ |
| `Access-Control-Allow-Credentials` | Cho phép chia sẻ response trong credentials mode khi áp dụng |
| `Vary: Origin` | Báo cache phân biệt response theo request header `Origin` |
| `Cache-Control` | Hướng dẫn cache HTTP có được lưu và tái sử dụng response không |

`Vary` **không** làm một origin không được phép trở thành được phép. Ngược lại, nếu server không trả `Access-Control-Allow-Origin` hợp lệ, `Vary: Origin` tự nó không làm browser đọc được dữ liệu.

Một client không phải browser có thể tự gửi `Origin`. Header này không chứng minh identity; authentication và authorization vẫn bắt buộc.

### 3.2. Khi nào `Vary: Origin` đặc biệt quan trọng?

Khi backend quyết định `Access-Control-Allow-Origin` dựa trên request `Origin` từ một **allowlist**:

~~~http
GET /api/catalog HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
~~~

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
Cache-Control: public, max-age=120
~~~

Sau đó request từ một origin khác được phép:

~~~http
GET /api/catalog HTTP/1.1
Host: api.example.com
Origin: https://admin.example.com
~~~

Response đúng về CORS cho request thứ hai phải có `Access-Control-Allow-Origin: https://admin.example.com`; cache không được phát lại response đã dành cho `app.example.com` như thể nó phù hợp với `admin.example.com`.

Nếu một API hoàn toàn công khai cố định trả `Access-Control-Allow-Origin: *` cho mọi request, **không tùy biến theo Origin**, việc tách variant theo Origin có thể không cần thiết cho CORS. Nhưng wildcard **không được dùng** để browser đọc response trong `credentials: "include"`, và việc dữ liệu là “public” phải được đánh giá độc lập.

### 3.3. `Vary` cũng có thể chứa nhiều trường

Một response có thể mang:

~~~http
Vary: Origin, Accept-Encoding
~~~

Nếu middleware nén response đã thêm `Vary: Accept-Encoding`, CORS layer cần **giữ lại** giá trị này. Không được ghi đè thành chỉ còn `Vary: Origin`, vì có thể làm cache phục vụ nhầm representation nén.

Nhiều giá trị `Vary` có thể xuất hiện ở những dòng header riêng rồi được HTTP client/cache diễn giải như danh sách; điều quan trọng là **response cuối cùng sau gateway** giữ đủ các trường liên quan.

Tránh ép `Vary: *` để “khỏi phải phân tích”: giá trị này có semantics cache rất khác, thường loại trừ khả năng sử dụng response từ cache cho request sau. Đây không phải biện pháp thay thế việc phân định API public và private đúng cách.

### 3.4. Một phản hồi không có `Origin` thì sao?

Browser không phải lúc nào cũng gửi `Origin` cho mọi request. HTTP cache còn phải phân biệt trường hợp `Origin` vắng mặt với trường hợp có Origin khi response khác nhau theo trường này.

Với API có CORS được tính động, hãy kiểm tra cả request **có** và **không có** `Origin`. Đừng giả định response không có Origin luôn mang cùng chính sách hoặc cùng tập header.

## 4. Vì sao preflight có thể cần Vary trên ba request headers?

Preflight là request OPTIONS chứa thông tin về **actual request sắp tới**:

~~~http
OPTIONS /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Response mẫu:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,PUT
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Ba header xuất hiện trong `Vary` là các input có thể ảnh hưởng đến **quyết định CORS trên preflight**:

1. `Origin`: trang nào đang gọi?
2. `Access-Control-Request-Method`: actual request muốn dùng method nào?
3. `Access-Control-Request-Headers`: actual request muốn gửi những tên header nào?

Nếu một HTTP intermediary cố lưu OPTIONS theo URL nhưng không phân biệt các input này, nó có thể tái sử dụng response của request hỏi `GET` cho request hỏi `DELETE`, hoặc response của origin A cho origin B.

Đây là lý do Spring CORS processor thường đặt `Vary` cho các header CORS liên quan. **Tuy nhiên không nên dựa vào `Vary` như giấy phép mặc định cache OPTIONS tại CDN**: tốt hơn là kiểm soát rõ edge có cache preflight hay không.

### 4.1. Vary không cứu được cấu hình policy quá rộng

Ví dụ sai:

~~~http
Access-Control-Allow-Origin: https://untrusted.example.org
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Nếu API đã cấp quyền CORS cho origin không tin cậy, `Vary: Origin` chỉ giúp cache phân biệt variant; nó **không thu hồi quyền đọc** vừa cấp.

Tương tự, server không nên phản chiếu mọi giá trị `Origin` từ client:

~~~java
// Anti-pattern: đừng làm vậy cho API có dữ liệu cá nhân.
String origin = request.getHeader("Origin");
response.setHeader("Access-Control-Allow-Origin", origin);
response.setHeader("Access-Control-Allow-Credentials", "true");
~~~

Một site do kẻ tấn công kiểm soát có thể trở thành origin được cho phép đọc response sử dụng cookie. Hãy dùng allowlist cụ thể, đồng thời hạn chế scope pattern subdomain.

## 5. Bộ nhớ đệm preflight của browser: Access-Control-Max-Age

Sau khi một preflight thành công, response có thể bao gồm:

~~~http
Access-Control-Max-Age: 600
~~~

Đơn vị là **giây**. Trong ví dụ, server cho phép browser cache kết quả preflight tới 600 giây, **nhưng browser có thể áp giới hạn thấp hơn** hoặc điều chỉnh theo chính sách của nó. Không nên hứa rằng mọi browser sẽ giữ chính xác 600 giây.

Trong Spring:

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setMaxAge(600L);
~~~

Hoặc với cấu hình MVC/WebFlux global:

~~~java
registry.addMapping("/api/**")
    .allowedOrigins("https://app.example.com")
    .allowedMethods("GET", "POST", "PUT")
    .maxAge(600);
~~~

`maxAge` ảnh hưởng đến preflight cache, không đặt TTL cho JSON response `GET /api/me`. Header `Cache-Control: max-age=600` của actual response là cơ chế khác.

### 5.1. Khi nào browser có thể bỏ qua OPTIONS?

Sau một preflight thành công, browser có thể dùng kết quả đã lưu cho các request phù hợp về các yếu tố như origin, URL, method, tập request headers và ngữ cảnh credentials/network partition theo quy tắc triển khai.

Về mặt thực hành, không nên dựa vào một cache key đơn giản `URL-only`. Browser phải đảm bảo quyền đã cache **áp dụng được** cho actual request đang chuẩn bị gửi. Chỉ việc cùng URL chưa đủ để cho mọi method/header khác nhau đi qua.

Ví dụ:

~~~text
Lần 1: Origin A -> PUT /api/profile, headers Content-Type + X-CSRF-TOKEN
        Browser gửi OPTIONS rồi lưu kết quả nếu cho phép.

Lần 2: Origin A -> PUT /api/profile, cùng điều kiện
        Browser có thể không gửi lại OPTIONS trong thời gian cache.

Lần 3: Origin A -> DELETE /api/profile
        Phải có quyền cho DELETE; không thể suy ra từ việc PUT từng được phép.

Lần 4: Origin B -> PUT /api/profile
        Quyền CORS của Origin A không tự cấp cho Origin B.
~~~

### 5.2. Thay đổi policy không xóa tức thì cache ở mọi browser

Giả sử trước đây API cho `PUT`, nhưng giờ đã loại `PUT` khỏi `allowedMethods`. Một browser còn kết quả preflight hợp lệ trước đó có thể **không phát OPTIONS mới ngay lập tức**.

Điều này **không có nghĩa** server phải chấp nhận PUT. Authorization, method mapping, CSRF và rule nghiệp vụ trên **actual request** vẫn phải áp dụng chính sách mới. CORS preflight là kiểm tra quyền browser, không được dùng làm lớp duy nhất để thu hồi quyền thao tác.

Khi cần thu hồi khẩn cấp, thay đổi authentication/authorization tại server và bảo vệ endpoint là điều quyết định. Giảm `maxAge` trong tương lai không bảo đảm xóa các kết quả đã cache trước đó.

### 5.3. Dùng maxAge bao nhiêu?

Không có một giá trị duy nhất đúng cho mọi hệ thống. Có thể cân nhắc:

| Bối cảnh | Cách nghĩ về preflight TTL |
| --- | --- |
| Chính sách CORS thường xuyên thay đổi trong lúc phát triển | Dùng TTL ngắn để dễ quan sát cấu hình mới |
| Production ổn định, số lượng preflight lớn | Có thể dùng TTL vừa phải để giảm OPTIONS, sau khi kiểm thử |
| API nhạy cảm hoặc chính sách tenant thay đổi nhanh | Cân bằng giảm lưu lượng với độ trễ khi chính sách CORS đổi |
| Cần thu hồi quyền endpoint ngay | Thay đổi auth/authorization tại server; không dựa vào việc hết TTL |

**Không tắt authentication, CSRF hoặc mở wildcard để giảm số lượng OPTIONS.** Hãy tối ưu preflight TTL mà không thay đổi ý nghĩa kiểm tra CORS.

### 5.4. `Cache-Control: no-store` có xóa preflight cache không?

Không nên coi hai cơ chế là một. HTTP response cache và CORS-preflight cache có semantics riêng. Muốn điều khiển thời gian kết quả preflight còn hữu dụng, hãy dùng `Access-Control-Max-Age` và đánh giá hành vi browser.

Ở chiều ngược lại, `Access-Control-Max-Age: 600` **không cho phép** một shared HTTP cache lấy dữ liệu người dùng và tái sử dụng trong 600 giây. Việc cache dữ liệu thực phải được điều khiển bởi `Cache-Control` và policy CDN.

## 6. CDN cache response theo những thông tin nào?

Một CDN có thể dùng **cache key** gồm URL, query, một số request headers và những biến thể do cấu hình cụ thể quyết định. Những điểm cần kiểm tra:

- CDN có tuân thủ `Vary: Origin` không, hay chỉ cache theo URL/path?
- Có forward header `Origin` từ browser về Spring không?
- Có forward `Access-Control-Request-Method` và `Access-Control-Request-Headers` trên OPTIONS không?
- CDN có cache status 200, 204, 301, 401, 403 hoặc cả response lỗi theo rule tùy biến?
- Có phân biệt request mang `Cookie`/`Authorization` với request anonymous không?
- Có lỡ cache `Set-Cookie` hoặc nội dung phản hồi cá nhân hóa?
- CDN có thêm/sửa/xóa `Access-Control-Allow-Origin` hoặc `Vary` trên đường về browser không?
- Có dùng cache-key normalization (bỏ query, đổi scheme/host, rewrite path) gây biến thể bị gộp?

**Không phải CDN nào cũng thực thi `Vary` giống nhau trong mọi cấu hình.** Một số nền tảng cần khai báo cache key hoặc Origin forwarding tường minh. Phải kiểm tra tài liệu của nhà cung cấp và thực nghiệm bằng các request có Origin khác nhau.

### 6.1. Một kịch bản lỗi phổ biến

Giả sử CDN cache theo URL `/api/catalog` nhưng bỏ qua request `Origin`. Lần đầu:

~~~http
GET /api/catalog HTTP/1.1
Origin: https://app.example.com
~~~

Edge lưu:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
Cache-Control: public, max-age=300
~~~

Lần sau trang admin gọi cùng URL:

~~~http
GET /api/catalog HTTP/1.1
Origin: https://admin.example.com
~~~

Nếu edge vẫn trả bản đã cache cho app:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
~~~

Browser ở `https://admin.example.com` thấy ACAO không khớp và chặn JavaScript đọc response. **Đây thường là lỗi tính sẵn sàng/chức năng CORS**, không phải tự động là rò rỉ dữ liệu từ app sang admin: khi origin không khớp, browser không cho đọc body.

Rò rỉ dữ liệu xảy ra khi hệ thống **cache nội dung nhạy cảm sai phạm vi**, hoặc khi chính sách CORS thật sự cấp quyền đọc cho origin không tin cậy. Hai nguy cơ này khác nhau và phải được xử lý riêng.

### 6.2. Response public có origin biến thiên

Nếu API trả nội dung giống nhau cho mọi user nhưng chỉ cho một tập frontend được phép đọc, edge cần hai việc khác nhau:

1. Tái sử dụng body public một cách hiệu quả.
2. Trả **CORS response headers phù hợp với origin của request hiện tại**.

Có thể thực hiện qua cache key gồm Origin, hoặc qua cơ chế edge chuẩn hóa/đính CORS header **sau khi xác thực Origin theo allowlist an toàn**. Không được đơn giản phản chiếu mọi Origin để giữ cache hit ratio.

Mỗi phương án đều phải test với Origin hợp lệ A, hợp lệ B, origin không tin cậy và request không có Origin.

### 6.3. OPTIONS và CDN

`Access-Control-Max-Age` điều khiển preflight cache của browser; nó không tự biến OPTIONS thành response có thể cache tại CDN. Trong nhiều triển khai, **forward/bypass OPTIONS** đến nơi xử lý CORS đáng tin cậy là cách ít rủi ro hơn.

Nếu thật sự muốn edge tự trả hoặc cache preflight:

- Có chính sách CORS rõ ràng tại edge hoặc cơ chế cache được kiểm thử.
- Phân biệt `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers` theo semantics yêu cầu.
- Không dùng bản cấp quyền của origin A cho origin B.
- Có cơ chế triển khai/thu hồi policy đồng bộ với backend.
- Không để authentication tại edge đòi credentials của actual request trên preflight.
- Không nhầm cache TTL của CDN với `Access-Control-Max-Age` trong browser.

Cache OPTIONS ở edge là một quyết định kiến trúc riêng; **không phải tối ưu bắt buộc** của Spring Security.

## 7. Vấn đề nghiêm trọng hơn: cache chéo người dùng

Xét endpoint:

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Cookie: SESSION=<user-A-session>
~~~

Server trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin

{"userId":"A","email":"a@example.com"}
~~~

Nếu CDN được cấu hình cache `/api/me` theo URL mà không tách response cá nhân hóa, request của user B có thể bị trả body của user A.

**`Vary: Origin` không ngăn lỗi này**, vì user A và B đều có thể đến từ **cùng origin** `https://app.example.com`. CORS vẫn hợp lệ và JavaScript của user B có nguy cơ đọc dữ liệu user A.

### 7.1. Cách đặt cache policy cho dữ liệu riêng tư

Đối với tài nguyên chứa hồ sơ, thông tin tài khoản hoặc dữ liệu nhạy cảm:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json
~~~

`Cache-Control: no-store` hướng dẫn HTTP caches không lưu response để tái sử dụng. `Cache-Control: private` là lựa chọn khác trong một số tình huống khi muốn cho phép cache riêng của browser nhưng **không cho shared caches** lưu response; tính phù hợp phụ thuộc loại dữ liệu.

Với API nhạy cảm, `no-store` thường là một chính sách rõ ràng và dễ kiểm chứng. Phải xác minh CDN **không có rule override** cưỡng ép cache bất chấp directives của origin server.

Không cho rằng `Vary: Cookie` là giải pháp luôn đủ: cookie có thể có nhiều giá trị, cache key rất phức tạp và rủi ro nếu CDN không tôn trọng hoặc bỏ qua. Với response được xác thực, **bypass shared cache** thường đơn giản và an toàn hơn trừ khi có kiến trúc caching được thiết kế kỹ.

### 7.2. Authorization header và shared caches

Request chứa `Authorization` có quy tắc cache HTTP riêng; shared cache không được tự ý tái sử dụng response cho request khác nếu không có các điều kiện/directives cho phép theo HTTP caching semantics. Nhưng một rule CDN tùy chỉnh vẫn có thể phá giả định an toàn.

Đừng dựa đơn độc vào “CDN mặc định sẽ biết đây là endpoint private”. Hãy kiểm tra policy edge và response cuối cùng:

- Có bất kỳ rule nào cache mọi `GET /api/**` không?
- `Authorization` và `Cookie` có được forward về backend khi cần không?
- CDN có bỏ qua `Cache-Control: private/no-store` không?
- Có cache response chứa `Set-Cookie`, token hoặc thông tin cá nhân không?
- Các response lỗi xác thực có vô tình được cache dùng chung không?

### 7.3. Nguy cơ với Set-Cookie

`Set-Cookie` là response header mà JavaScript Fetch không được đọc trực tiếp, kể cả khi `Access-Control-Expose-Headers` liệt kê nó. Tuy vậy trình duyệt có thể xử lý cookie nếu request và chính sách cookie cho phép.

Một CDN lưu và tái sử dụng response chứa session cookie hoặc `Set-Cookie` không đúng cách có thể gây lỗi phiên đăng nhập nghiêm trọng. Đối với response đăng nhập/phát session, thường nên tắt shared caching và kiểm tra các cơ chế CDN không tự cache hoặc phát lại `Set-Cookie` cho người dùng khác.

## 8. Cấu hình CORS và cache cho Spring Security Servlet

Ví dụ Spring MVC + Spring Security dùng allowlist hai frontend và `maxAge` cho preflight. API private được đặt cache policy riêng ở controller.

### 8.1. CorsConfigurationSource + SecurityFilterChain

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletCorsSecurityConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of(
            "https://app.example.com",
            "https://admin.example.com"
        ));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        cors.setExposedHeaders(List.of("X-Request-Id"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L); // Cache preflight trên browser (giây).

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        CorsConfigurationSource corsConfigurationSource
    ) throws Exception {
        return http
            .cors(cors -> cors.configurationSource(corsConfigurationSource))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .build();
    }
}
~~~

**Cách đọc:**

- `CorsConfigurationSource` xác định policy CORS cho request `/api/**`.
- `allowedOrigins` gồm hai origin tin cậy; không phải wildcard.
- `setAllowCredentials(true)` hỗ trợ browser đọc response khi `credentials: "include"` và các điều kiện CORS khác đạt.
- `setMaxAge(600L)` đặt **preflight TTL** được đề xuất; không yêu cầu CDN cache body.
- `http.cors(...)` xử lý preflight đủ sớm, trước authentication yêu cầu cookie/token.
- Rule `authenticated()` bảo vệ actual API. Ví dụ chưa định nghĩa login/session/CSRF token hoàn chỉnh; chúng phải được bổ sung theo ứng dụng.

Spring CORS processor thường quản lý các response headers `Vary` phù hợp. **Không tự chèn một `Vary: Origin` duy nhất bằng cách ghi đè mọi Vary khác**. Hãy đo response cuối sau Security, MVC, gateway và CDN.

### 8.2. Endpoint private với Cache-Control no-store

~~~java
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
class AccountController {

    @GetMapping("/me")
    ResponseEntity<Map<String, String>> me() {
        // Giả định tài khoản đã được xác thực qua Security.
        // Trong dự án thật, body cần lấy từ principal đã xác thực.
        Map<String, String> body = Map.of(
            "displayName", "Lan"
        );

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(body);
    }
}
~~~

`CacheControl.noStore()` tạo cache directive cho **actual response** của endpoint, không phải thay đổi CORS policy hay preflight max age. Giá trị demo “Lan” chỉ để minh họa cấu trúc response; không được hardcode dữ liệu user thật.

Ngoài controller, Spring Security cũng có các default cache-related response headers trong nhiều cấu hình. Tuy vậy không nên mặc định rằng mọi endpoint/gateway/CDN đều giữ chính xác các header đó, nhất là khi ứng dụng đã tự đặt header hoặc dùng custom middleware. Kiểm tra HTTP response cuối là bắt buộc.

### 8.3. Endpoint public có thể cache khác

Một endpoint public, anonymous, không có thông tin theo user, ví dụ `GET /api/public/catalog`, có thể dùng:

~~~http
Cache-Control: public, max-age=60, s-maxage=300
Vary: Origin, Accept-Encoding
~~~

Trong đó `max-age` là freshness chung cho HTTP cache và `s-maxage` hướng tới shared caches. Ví dụ này **chỉ phù hợp nếu body thật sự công khai**, không dựa trên session hay user.

Nếu server chọn `Access-Control-Allow-Origin` khác nhau tùy `Origin`, CDN phải giữ biến thể CORS đúng, bất kể response body public giống nhau.

## 9. Cấu hình Reactive / WebFlux

Trong WebFlux, ý tưởng không thay đổi, nhưng `CorsConfigurationSource` và `UrlBasedCorsConfigurationSource` thuộc package reactive, và Security sử dụng `ServerHttpSecurity`.

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveCorsSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of(
            "https://app.example.com",
            "https://admin.example.com"
        ));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        cors.setExposedHeaders(List.of("X-Request-Id"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);

        return http
            .cors(spec -> spec.configurationSource(source))
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll())
            .build();
    }
}
~~~

Một handler reactive có thể chọn cache policy riêng:

~~~java
import java.util.Map;
import reactor.core.publisher.Mono;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
class ReactiveAccountController {

    @GetMapping("/me")
    Mono<ResponseEntity<Map<String, String>>> me() {
        // Chỉ minh họa response; lấy principal thực ở ứng dụng thật.
        return Mono.just(ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of("displayName", "Lan")));
    }
}
~~~

`CacheControl.noStore()` áp dụng cho HTTP caching của response. CORS preflight vẫn được điều khiển bằng `CorsConfiguration`/`Access-Control-Max-Age` và các quy tắc browser.

Nếu dùng `CorsWebFilter` độc lập, cần đảm bảo nó chạy đủ sớm so với Spring Security WebFilters và không tạo CORS headers chồng chéo với `ServerHttpSecurity.cors(...)`. Không dùng Servlet `CorsFilter` cho WebFlux.

## 10. Thiết kế CDN: tránh dùng một cache policy cho mọi API

Một chính sách CDN nên phân nhóm rõ ràng, thay vì cho rằng toàn bộ `/api/**` đều có thể cache.

| Loại tài nguyên | Cache policy gợi ý | CORS liên quan | Kiểm soát quan trọng |
| --- | --- | --- | --- |
| Tài nguyên tĩnh public, phiên bản hóa | Có thể cache dài theo asset version | Có thể dùng `*` nếu thực sự public, không cần credentials mode include | Không chứa dữ liệu user |
| Danh mục public GET | Có thể dùng `public`/TTL có kiểm soát | `Vary: Origin` nếu ACAO phụ thuộc origin | CDN phân biệt hoặc tạo header CORS theo allowlist |
| `GET /api/me` | `no-store`/bypass shared cache | Origin cụ thể + credentials nếu cần | Không phát dữ liệu user A cho user B |
| `GET /api/admin/reports` cá nhân hóa | Bypass shared cache | Allowlist origin admin cụ thể | Authentication, authorization, quyền dữ liệu |
| Login, refresh token, session response | Không cache dùng chung | CORS policy theo frontend được tin cậy | Không lưu/phát lại `Set-Cookie` hoặc token |
| POST/PUT/PATCH/DELETE thay đổi trạng thái | Không cache response cho user khác trừ thiết kế đặc biệt | Preflight có thể dùng Max-Age | Authentication, authorization, CSRF |
| OPTIONS preflight | Thường forward/bypass edge cache hoặc xử lý chuyên biệt | Origin + Request-Method + Request-Headers | Đồng bộ policy và TTL browser |
| Response lỗi 401/403 của API private | Thường không cache dùng chung | CORS headers đúng để frontend đọc status | Tránh phát sai thông tin lỗi/session giữa users |

**Quy tắc vận hành:** nếu không chắc response có phụ thuộc người dùng hay không, không đặt `Cache-Control: public` chỉ để tăng cache hit rate.

### 10.1. Pseudocode cấu hình edge theo chính sách

Đây là **mô tả logic, không phải cú pháp cấu hình của CDN cụ thể**:

~~~text
if path starts with "/api/me"
   or path starts with "/api/admin/"
   or request has session cookie
   or request has Authorization:
    bypass shared cache
    forward request to origin
    preserve Cache-Control / CORS response headers
else if method == OPTIONS:
    forward to the trusted CORS policy handler
    do not synthesize a generic 200
else if method == GET and path starts with "/api/public/":
    cache only when response is explicitly public
    respect Vary: Origin and other Vary fields
    do not cache Set-Cookie or personalized body
else:
    follow a documented safe cache policy
~~~

Các điều kiện phải được chuyển thành rule chính xác của CDN thực tế. Thứ tự rule và cách CDN diễn giải `Vary`, `Cookie`, `Authorization` có thể khác nhau; đây không phải cấu hình có thể copy-paste vào production.

### 10.2. CDN tự gắn ACAO tại edge: điều kiện an toàn

Một số hệ thống muốn cache body public duy nhất rồi chọn CORS headers ở edge theo request Origin. Phương án này chỉ hợp lý khi edge có một **allowlist kiểm soát được**, xác thực scheme/host/port đúng, không phản chiếu mọi origin và gắn policy nhất quán cho response lỗi.

Không dùng:

~~~text
Access-Control-Allow-Origin = incoming Origin   # Không kiểm tra allowlist
Access-Control-Allow-Credentials = true
~~~

cho API có session. Nếu cần credentials, browser không cho dùng `ACAO: *`; nhưng trả origin cụ thể không đủ để an toàn nếu origin đó không được tin cậy.

### 10.3. Những header khác không được vô tình đánh mất

Khi gateway chỉnh CORS headers, còn phải giữ:

- `Vary: Accept-Encoding` hoặc những request headers khác ảnh hưởng representation.
- `Cache-Control` phù hợp với loại dữ liệu.
- `ETag`/`Last-Modified` nếu ứng dụng sử dụng HTTP revalidation cho tài nguyên public.
- `Content-Security-Policy`, `Strict-Transport-Security` và các security headers liên quan khi được phát ở tầng phù hợp.
- Các headers CORS trên **response 401/403/500** nếu frontend được phép đọc lỗi.

Chèn thêm `Vary: Origin` không được vô tình loại `Vary` đã có do compression, localization hoặc content negotiation.

## 11. Kiểm thử thủ công: hai origins, hai tình huống cache

### 11.1. Thử actual GET từ hai origins

Thay hostname minh họa bằng endpoint kiểm thử có tồn tại.

~~~bash
curl -i "https://api.example.com/api/public/catalog" \
  -H "Origin: https://app.example.com"
~~~

~~~bash
curl -i "https://api.example.com/api/public/catalog" \
  -H "Origin: https://admin.example.com"
~~~

Kỳ vọng nếu cả hai origin được cho phép:

- Mỗi response chứa `Access-Control-Allow-Origin` tương ứng với **Origin đã gửi**.
- `Vary` có `Origin` nếu ACAO được chọn động theo request.
- CDN không phát lại ACAO của app cho admin.
- Khi có `Cache-Control: public`, nội dung body thật sự là public, không chứa dữ liệu session.

Thử origin ngoài allowlist:

~~~bash
curl -i "https://api.example.com/api/public/catalog" \
  -H "Origin: https://evil.example.org"
~~~

Không nên cấp ACAO cho origin không tin cậy. Cần kiểm tra response cuối từ CDN, **không chỉ response ở backend**.

### 11.2. Thử preflight với method và headers khác nhau

Preflight PUT có `X-CSRF-TOKEN`:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Preflight DELETE không được phép:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: DELETE"
~~~

Preflight đến từ origin không được phép:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://evil.example.org" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: content-type"
~~~

Kỳ vọng: PUT hợp lệ nhận CORS response đầy đủ; DELETE và origin lạ không được cấp quyền preflight. **Không** được để CDN cache một response 200 OPTIONS theo URL rồi tái sử dụng vô điều kiện cho DELETE/origin lạ.

### 11.3. Xem Age và các dấu hiệu cache của CDN

Một số CDN trả header như:

~~~http
Age: 42
X-Cache: HIT
~~~

`Age` có semantics HTTP về thời gian response đã nằm trong cache; `X-Cache` là header không thống nhất giữa các nhà cung cấp. Nhiều CDN dùng các tên header khác nhau hoặc không tiết lộ cache hit.

Hãy đánh giá cùng lúc: status, `Origin` gửi đi, `Access-Control-Allow-Origin`, `Vary`, `Cache-Control`, `Age`, các header cache vendor-specific và nội dung response. **Một mình `Age` không chứng minh response đã được cache đúng theo user/origin.**

### 11.4. Không dùng curl để thay thế browser

`curl` có thể tự đặt `Origin` và không thực thi SOP/CORS như trình duyệt. Thêm nữa, nó không vận hành CORS-preflight cache như Fetch, nên việc gửi OPTIONS bằng curl liên tiếp không thể mô phỏng đầy đủ browser cache.

Dùng curl để kiểm tra HTTP, rồi xác nhận bằng DevTools trên những frontend thực tại đúng origins, bao gồm chính sách cookie và `credentials` mode.

## 12. Test Spring Security Servlet: Vary và preflight

Với Spring Boot + Spring Security + cấu hình `CorsConfigurationSource` ở mục 8, có thể kiểm tra preflight hợp lệ không cần cookie và `Vary` chứa các key cần thiết.

~~~java
import java.util.List;
import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsVaryAndPreflightTest {

    @Autowired
    MockMvc mvc;

    @Test
    void allowedPreflightHasVaryAndMaxAge() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "https://app.example.com")
                .header("Access-Control-Request-Method", "PUT")
                .header("Access-Control-Request-Headers",
                    "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", "https://app.example.com"))
            .andExpect(header().string(
                "Access-Control-Max-Age", "600"))
            .andExpect(result -> {
                List<String> varyHeaders =
                    result.getResponse().getHeaders("Vary");
                String vary = String.join(",", varyHeaders)
                    .toLowerCase(Locale.ROOT);

                assertTrue(vary.contains("origin"));
                assertTrue(vary.contains("access-control-request-method"));
                assertTrue(vary.contains("access-control-request-headers"));
            });
    }

    @Test
    void secondAllowedOriginGetsItsOwnAcao() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "https://admin.example.com")
                .header("Access-Control-Request-Method", "PUT"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", "https://admin.example.com"));
    }

    @Test
    void unknownOriginIsNotGrantedPreflight() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "https://evil.example.org")
                .header("Access-Control-Request-Method", "PUT"))
            .andExpect(status().isForbidden());
    }
}
~~~

Đây là mã kiểm thử minh họa **chưa chạy trên dự án cụ thể**; nó giả định CORS processor mặc định của Spring và cấu hình tương ứng. Test theo framework có thể xác minh output `Vary` của ứng dụng, nhưng **không chứng minh CDN đã tuân thủ Vary hoặc không cache nhầm dữ liệu user**.

Để kiểm tra response private, bổ sung test `GET /api/me` với principal phù hợp, xác nhận `Cache-Control: no-store` và kiểm tra body không bao gồm dữ liệu người khác. Nếu Spring Security hoặc ứng dụng có response cache-header defaults, kết quả cuối cần được kiểm tra trong test thay vì suy từ controller đơn lẻ.

## 13. Test Reactive: WebTestClient

Ví dụ với `SecurityWebFilterChain` ở mục 9:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.http.HttpHeaders.*;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveCorsVaryTest {

    @Autowired
    WebTestClient client;

    @Test
    void preflightHasExpectedCORSHeaders() {
        client.options()
            .uri("/api/profile")
            .header(ORIGIN, "https://app.example.com")
            .header(ACCESS_CONTROL_REQUEST_METHOD, "PUT")
            .header(ACCESS_CONTROL_REQUEST_HEADERS,
                "content-type,x-csrf-token")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                ACCESS_CONTROL_ALLOW_ORIGIN, "https://app.example.com")
            .expectHeader().valueEquals(
                ACCESS_CONTROL_MAX_AGE, "600")
            .expectHeader().exists(VARY);
    }

    @Test
    void foreignOriginCannotPassPreflight() {
        client.options()
            .uri("/api/profile")
            .header(ORIGIN, "https://evil.example.org")
            .header(ACCESS_CONTROL_REQUEST_METHOD, "PUT")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Mục đích là kiểm tra preflight và `Vary` có hiện diện. Để xác thực **đầy đủ từng trường trong Vary**, có thể đọc values của response header trong test tùy framework version, chuẩn hóa chữ hoa/thường rồi kiểm tra cả `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`.

Như `MockMvc`, `WebTestClient` không mô phỏng preflight cache của browser, cache key CDN hoặc cookie tracking restrictions. Cần test qua HTTP gateway và browser.

## 14. Chẩn đoán lỗi Vary, Max-Age và CDN

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| App A dùng được, App B bị ACAO mismatch | CDN cache một variant ACAO theo Origin A rồi trả cho B | Kiểm tra `Vary: Origin`, cache key và Origin forwarding |
| Response có `Vary: Origin` nhưng edge vẫn trả nhầm | CDN không tôn trọng hoặc bị override cấu hình Vary | Test trực tiếp vs qua edge; xem rule cache key vendor-specific |
| Đổi `allowedMethods` nhưng browser vẫn không gửi OPTIONS mới | Browser còn preflight cache | Xem `Access-Control-Max-Age`, thử profile/test context mới, chờ TTL; giữ server authorization |
| `Access-Control-Max-Age: 600` nhưng mỗi lần vẫn thấy OPTIONS | Browser giới hạn/cache miss, origin/method/headers khác, network partition hoặc policy khác | So request details; không coi 600 là bảo đảm |
| OPTIONS GET được nhưng OPTIONS DELETE cũng nhận policy cũ | Edge cache preflight sai theo URL-only | Forward OPTIONS hoặc cache key đúng tất cả preflight inputs |
| `GET /api/me` trả dữ liệu user khác | Shared cache đang lưu response cá nhân hóa | Dừng shared caching, dùng `no-store` và rà soát CDN |
| GET public bị cache riêng theo quá nhiều origins | Vary Origin làm tăng variants | Cân nhắc edge CORS header an toàn theo allowlist, nhưng không phản chiếu tùy ý |
| Response bị mất `Vary: Accept-Encoding` | Middleware/gateway ghi đè Vary | Hợp nhất thay vì thay toàn bộ header |
| Browser báo CORS nhưng backend log 401 | Actual error response thiếu CORS headers, hoặc edge cache sai status | Xem actual response và chính sách CORS trên lỗi |
| Request dùng cookie nhưng nhận response public cache | CDN bỏ qua auth/cookie trong cache logic | Phân vùng API; bypass cache khi có session/Authorization |
| CDN cache hoặc phát lại Set-Cookie | Rule edge quá rộng hoặc forward không đúng | Không shared-cache phản hồi login/session, kiểm tra Set-Cookie |
| Một số origins không nhận CORS header | Edge bỏ Origin trước khi gửi backend | Kiểm tra header forwarding và origin-facing request |
| Browser thấy hai ACAO headers | Spring và CDN cùng chèn CORS | Chọn một chính sách CORS cuối cùng, loại header trùng |
| Chỉ lỗi sau khi deploy chính sách CORS mới | Cache variants/preflight hoặc nhiều backend chưa đồng bộ | Kiểm tra TTL, purge CDN khi cần, rollout và instance consistency |
| OPTIONS bị 401/403 ở gateway | Authentication/routing chạy trước CORS | Điều chỉnh gateway xử lý hoặc forward preflight đúng |
| Cache hit nhưng dữ liệu stale | HTTP cache TTL, `Age`, revalidation và invalidation | Tách việc điều chỉnh TTL HTTP khỏi preflight Max-Age |

### 14.1. Quy trình DevTools

1. Mở đúng frontend origin, xác định request đang lỗi và xem có OPTIONS không.
2. Nếu có OPTIONS, xem `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers` của preflight.
3. Kiểm tra `Access-Control-Allow-*`, `Access-Control-Max-Age` và `Vary` ở response preflight.
4. Nếu không thấy OPTIONS, xác định actual request có thuộc safelist hoặc preflight đã được cache không.
5. Nếu actual response bị chặn, kiểm tra ACAO trên **response cuối**, không chỉ response trực tiếp từ Spring.
6. So sánh hai origins được phép gọi cùng URL; kiểm tra response/caching trước và sau CDN.
7. Kiểm tra `Cache-Control`, `Age`, cache status của CDN và khả năng response thay đổi theo Cookie/Authorization.
8. Với endpoint có session, kiểm tra browser Cookies và xác minh CDN không lưu body cá nhân hóa.
9. Khi nghi ngờ policy cũ, phân biệt cache **browser preflight** với cache **CDN HTTP** trước khi purge hoặc thay cấu hình.

Không “sửa” bằng `mode: "no-cors"`: response opaque sẽ không cho JavaScript đọc JSON. Không dùng wildcard origin cùng `Access-Control-Allow-Credentials: true` cho request `credentials: "include"`.

## 15. Checklist trước khi triển khai production

- [ ] Nhóm API đã được phân loại public/cacheable và private/session-dependent.
- [ ] CORS cho phép **đúng tập origins**; không phản chiếu mọi Origin hoặc dùng wildcard pattern rộng với credentials.
- [ ] `Vary: Origin` có trong response nếu ACAO được tính dựa trên Origin và response có thể được HTTP cache.
- [ ] Preflight responses thay đổi theo method/header có `Vary` phù hợp cho `Access-Control-Request-Method`, `Access-Control-Request-Headers` khi cần.
- [ ] CDN được kiểm tra thực tế về hỗ trợ Vary, Origin forwarding và cache key.
- [ ] `Access-Control-Max-Age` được chọn có chủ đích, hiểu rằng browser có thể giới hạn và giữ cache đến khi hết hạn.
- [ ] Không dùng `Access-Control-Max-Age` để điều khiển HTTP cache TTL của response nghiệp vụ.
- [ ] OPTIONS tại CDN được forward/bypass hoặc xử lý chuyên biệt bằng policy đúng; không cache URL-only vô điều kiện.
- [ ] `/api/me`, admin, login/session và response cá nhân hóa không bị shared cache tái sử dụng giữa người dùng.
- [ ] Những response dùng cookie/token có cache directives đúng, và CDN không override thành public.
- [ ] `Vary: Accept-Encoding` và các Vary fields khác không bị thay mất khi thêm CORS.
- [ ] Security CORS integration cho Servlet/Reactive chạy trước authentication trên preflight; actual request vẫn qua authorization, CSRF và session.
- [ ] Response lỗi 401/403/500 có CORS headers đúng nếu frontend được phép đọc.
- [ ] Có test origins A/B/untrusted, preflight method/header khác nhau, direct backend và qua CDN.
- [ ] Có kế hoạch invalidation/purge CDN cho public content và quy trình xử lý thay đổi policy khẩn cấp **không dựa hoàn toàn vào preflight TTL**.

## 16. Câu hỏi vận dụng có đáp án

**Tình huống A.** API trả `Access-Control-Allow-Origin: https://app.example.com` khi Origin là app và ACAO bằng admin khi Origin là admin. CDN có thể lưu response GET. Tại sao cần `Vary: Origin`?

**Đáp án:** Vì response headers khác nhau theo request Origin. Cache phải phân biệt variants; nếu trả ACAO của app cho admin, browser admin có thể từ chối đọc response dù origin admin hợp lệ.

**Tình huống B.** Server trả `Access-Control-Max-Age: 600`. Điều đó có nghĩa CDN được phép cache `GET /api/me` trong 600 giây không?

**Đáp án:** Không. Max-Age CORS là TTL cho **preflight cache của browser**, không phải TTL HTTP cache của actual response. API private cần `Cache-Control` và policy CDN riêng.

**Tình huống C.** CDN lưu phản hồi `GET /api/me` của user A, rồi trả cho user B cùng frontend origin. `Vary: Origin` có ngăn rò rỉ không?

**Đáp án:** Không. Hai user có cùng Origin, nên Vary Origin không phân biệt phiên. Cần tránh shared caching của response cá nhân hóa, dùng `Cache-Control: no-store` và kiểm tra cấu hình CDN.

**Tình huống D.** Đã giảm `Access-Control-Max-Age` từ 600 xuống 0 nhưng browser trước đó vừa cache preflight. Có đảm bảo cache cũ biến mất ngay không?

**Đáp án:** Không. Policy mới không tự xóa kết quả preflight đã lưu của mọi browser. Server phải bảo vệ actual request bằng auth/authorization/CSRF nếu cần thu hồi quyền thao tác tức thì.

**Tình huống E.** CDN cache OPTIONS chỉ theo URL. Request hỏi `PUT` từ Origin A thành công, sau đó request hỏi `DELETE` từ Origin B cũng nhận cùng response. Sai ở đâu?

**Đáp án:** Cache key/preflight policy bỏ qua những input quyết định quyền: Origin, requested method và requested headers. Nên forward OPTIONS hoặc triển khai cache/edge CORS chuyên biệt với phân tách và kiểm thử đầy đủ.

**Tình huống F.** Spring trả `Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers` nhưng gateway ghi đè thành `Vary: Accept-Encoding`. Hệ quả?

**Đáp án:** Cache có thể mất thông tin cần thiết để phân biệt variants theo Origin/preflight inputs. Gateway phải giữ và hợp nhất các trường Vary liên quan, không xóa giá trị hiện có.

**Tình huống G.** API public trả `Access-Control-Allow-Origin: *` cho mọi Origin, không dùng credentials mode include và nội dung thật sự công khai. Có luôn cần `Vary: Origin` không?

**Đáp án:** Không nhất thiết vì ACAO không thay đổi theo Origin. Tuy vậy các yếu tố caching khác vẫn có thể cần Vary; phải xác nhận body thật sự công khai và không phụ thuộc user/cookie.

**Tình huống H.** CORS hoạt động khi gọi backend trực tiếp, nhưng khi qua CDN response 401 của API không có ACAO, frontend chỉ thấy CORS error. Nên kiểm tra gì?

**Đáp án:** Xem gateway/CDN có trả 401 trước Spring, cache response lỗi hoặc xóa CORS headers không; kiểm tra CORS trên actual error response và thống nhất nơi xử lý CORS.

---

**Ghi nhớ:** `Vary` giúp **HTTP caches** phân biệt response theo những request headers như `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`. `Access-Control-Max-Age` điều khiển **CORS-preflight cache riêng của browser**, không điều khiển việc CDN cache JSON hay dữ liệu phiên. Một CDN có thể gây lỗi ACAO giữa các origins hoặc, nghiêm trọng hơn, rò rỉ dữ liệu nếu cache sai response cá nhân hóa. Hãy kiểm soát cache key, `Cache-Control`, credentials, allowlist, filter ordering trên **Servlet và Reactive**, và kiểm thử response cuối qua CDN thay vì chỉ kiểm tra trong Spring.
