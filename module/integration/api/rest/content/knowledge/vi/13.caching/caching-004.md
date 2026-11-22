# Phân biệt no-cache với no-store

## 1. Cùng có chữ “no”, nhưng khác hoàn toàn về ngữ nghĩa

Trong một REST API, server thường trả header **Cache-Control** để hướng dẫn browser, proxy, CDN và các HTTP cache khác về việc **có được lưu phản hồi không** và **khi nào được dùng lại phản hồi đã lưu**. Hai chỉ thị hay bị hiểu nhầm nhất là:

- **no-cache:** cache **có thể lưu** phản hồi, nhưng **không được sử dụng phản hồi đã lưu để đáp ứng một yêu cầu tiếp theo nếu chưa xác thực lại thành công với origin server**.
- **no-store:** cache **không được lưu bất kỳ phần nào của phản hồi hoặc yêu cầu đã tạo ra phản hồi đó**, theo quy tắc của HTTP caching.

Vì thế, **no-cache không đồng nghĩa với “không lưu cache”**. Trong nhiều ứng dụng, no-cache kết hợp **ETag** là cách tiết kiệm băng thông trong khi vẫn xác minh được tài nguyên có thay đổi không. Còn no-store phù hợp hơn khi muốn tránh lưu dữ liệu nhạy cảm tại HTTP cache.

Xét hai endpoint:

~~~http
GET /products/SKU-42 HTTP/1.1
Host: api.example.com
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-cache
ETag: "product-42-v7"

{"id":"SKU-42","name":"Bàn phím","priceMinor":799000}
~~~

Sản phẩm có thể được lưu trong cache. Nhưng lần sử dụng tiếp theo, cache cần hỏi lại origin xem phiên bản có còn hợp lệ hay không; nếu còn, origin có thể trả **304 Not Modified** và cache dùng body cũ.

Với dữ liệu tài khoản:

~~~http
GET /me/profile HTTP/1.1
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{"displayName":"Người dùng A","email":"a@example.com"}
~~~

Ở đây API không muốn một HTTP cache tuân thủ chuẩn lưu bản sao response. **private** còn nhấn mạnh dữ liệu không dành cho shared cache, nhưng **no-store mới là chỉ thị ngăn lưu**, kể cả ở cache riêng của client.

Bài thuộc chương **Bộ nhớ đệm** của module **INTEGRATION_API_REST**, nơi người học thiết kế REST API theo resource, URI, phương thức và mã trạng thái HTTP cùng hợp đồng dữ liệu rõ ràng. Hiểu đúng no-cache/no-store còn giúp kết hợp phân trang, ETag, OpenAPI, xác thực, phân quyền, idempotency, xử lý lỗi và kiểm thử API với Java/Spring.

Sau bài này, bạn có thể giải thích hai chỉ thị theo RFC 9111, phân biệt chỉ thị ở request/response, mô tả luồng revalidation với ETag và 304, lựa chọn chính sách an toàn cho từng resource, viết mã Spring và thiết kế kiểm thử cả qua CDN/proxy.

## 2. Mô hình HTTP cache: lưu khác với dùng lại

Một HTTP cache có thể nằm tại nhiều vị trí:

| Tầng | Ví dụ | Điểm cần nhớ |
| --- | --- | --- |
| **Private cache** | Cache HTTP của trình duyệt hoặc client dành riêng cho một người dùng. | Có thể lưu dữ liệu cá nhân nếu response cho phép; **private** không cấm loại cache này. |
| **Shared cache** | CDN, reverse proxy cache, proxy chung cho nhiều người dùng. | Cần chính sách chia sẻ chính xác để tránh đưa dữ liệu user A cho user B. |
| **Origin server** | API Java/Spring hoặc service phía sau gateway. | Cung cấp resource, validator và chính sách cache. |
| **Application cache** | Redis trong service, cache của ORM, biến state frontend. | Không nhất thiết là HTTP cache; không tự động bị điều khiển bởi Cache-Control. |

Một response được lưu và một response được dùng lại là **hai quyết định riêng**:

1. **Store:** có thể giữ response vào cache không?
2. **Reuse:** ở request sau, cache có được dùng response đang giữ để đáp ứng không? Cần kiểm tra freshness, validator, request directives, method, status, URL, Vary và chính sách bảo mật.

~~~mermaid
flowchart TD
    A[GET tới server / cache] --> B{Có response phù hợp trong HTTP cache?}
    B -->|Không| C[Gọi origin]
    B -->|Có| D{Được phép dùng ngay?}
    D -->|Có, còn fresh và không bị cấm| E[Trả bản lưu]
    D -->|Phải xác thực lại| F[Gửi conditional request tới origin]
    F --> G{Origin trả 304?}
    G -->|Có| H[Cập nhật metadata và dùng body đã lưu]
    G -->|Không, trả 200 mới| I[Dùng response mới và xử lý cache policy]
    C --> I
~~~

Trong luồng **no-cache**, nhánh “được dùng ngay” **không được phép** đối với response đã lưu nếu chưa có xác thực lại thành công, ngay cả khi cache còn coi bản đó là fresh. Trong luồng **no-store**, cache tuân thủ chuẩn **không lưu response để đi vào nhánh dùng lại về sau**.

Các thuật ngữ:

- **Freshness:** khoảng thời gian một response được coi là còn mới theo quy tắc cache, chẳng hạn **max-age=120**.
- **Stale:** response đã quá freshness lifetime hoặc bị các điều kiện khác khiến không thể dùng như bản fresh.
- **Validation/revalidation:** hỏi origin xem bản đã lưu còn hợp lệ không, thường sử dụng **ETag/If-None-Match** hoặc **Last-Modified/If-Modified-Since**.
- **Validator:** thông tin origin phát để client/cache kiểm tra một representation có thay đổi hay không.

Đừng dùng “đã lưu” và “đã phục vụ từ cache mà không gọi origin” như hai cách nói thay thế cho nhau.

## 3. Định nghĩa theo RFC 9111 và bảng so sánh trực diện

**RFC 9111 – HTTP Caching** quy định ngữ nghĩa của những chỉ thị Cache-Control phổ biến, kết hợp với các khái niệm ngữ nghĩa HTTP trong RFC 9110.

| Câu hỏi | **Cache-Control: no-cache** | **Cache-Control: no-store** |
| --- | --- | --- |
| Có thể **lưu** response vào HTTP cache? | **Có**, nếu các điều kiện lưu trữ khác cho phép. | **Không**, cache tuân chuẩn không được lưu. |
| Có thể lấy bản lưu ra dùng lại **không hỏi origin**? | **Không**; cần xác thực thành công trước khi tái sử dụng. | Không có bản được lưu theo chỉ thị này để dùng lại. |
| Có thể dùng **ETag → 304** để tiết kiệm response body? | **Có**, đây là ứng dụng rất điển hình. | Không dựa vào việc lưu body trong HTTP cache sau response no-store. |
| Phù hợp cho dữ liệu thay đổi thường xuyên nhưng không quá nhạy cảm? | Thường **có**, nếu chi phí revalidation chấp nhận được. | Có thể dùng, nhưng mất lợi ích tái sử dụng body của HTTP cache. |
| Phù hợp khi muốn **tránh lưu dữ liệu nhạy cảm**? | **Không đủ**, vì vẫn cho phép lưu. | **Phù hợp hơn** để yêu cầu cache không lưu. |
| Có bắt buộc server luôn trả body mới? | **Không**; có thể trả 304 và không có body. | Trong một luồng tải lại bình thường không có bản HTTP cache được phép dùng lại; response mới thường cần mang representation nếu thành công và có body. |
| Có tự xóa các bản sao đã tồn tại trước đó? | **Không**. | **Không bảo đảm xóa hồi tố** mọi bản đã được lưu trước khi chính sách đổi. |
| Có chặn log, screenshot, file người dùng chủ động tải, frontend state hay cache trong DB? | **Không**. | **Không**; tác động chính là HTTP cache tuân thủ quy tắc. |

**Một câu ghi nhớ:** **no-cache = lưu được, dùng lại phải hỏi**; **no-store = đừng lưu**.

### 3.1. “Không được dùng lại” là yêu cầu xác thực thực sự

Với **Cache-Control: no-cache** ở response, cache không được tự quyết định dùng body cũ chỉ vì:

- **max-age** nào đó cho biết bản đang fresh;
- khách hàng vừa gọi cùng URL vài giây trước;
- cache đang có đủ body để render;
- hệ thống muốn giảm một chuyến gọi mạng.

Cache cần một bước validation thành công với origin trước khi dùng bản đã lưu để trả một request tiếp theo. Nếu không có validator phù hợp, nó vẫn có thể liên hệ origin và nhận **200** cùng body mới; không thể tự biến thiếu validator thành quyền tái sử dụng bản cũ.

### 3.2. no-store có phạm vi và giới hạn

**no-store** nói về nghĩa vụ của HTTP cache tuân thủ chuẩn. Nó **không phải** cơ chế xóa dữ liệu đầu cuối, không bảo đảm browser không giữ trạng thái trong giao diện, không xóa file mà người dùng lưu, không ngăn ứng dụng ghi log hoặc downstream tự lưu dữ liệu ngoài mô hình HTTP cache.

Ngay cả khi đáp ứng đúng no-store, API vẫn phải kiểm soát truy cập, mã hóa kết nối, tránh gửi bí mật không cần thiết, hạn chế log và có chính sách lưu trữ dữ liệu ở tầng ứng dụng. Đây là biện pháp giảm khả năng lưu response trong cache, không phải thay thế toàn bộ thiết kế bảo mật.

## 4. Phải phân biệt chỉ thị ở response và ở request

Cache-Control xuất hiện trong **HTTP response** hoặc **HTTP request**, nhưng chủ thể đưa ra chỉ thị và kết quả thực tế khác nhau.

### 4.1. Chỉ thị từ response của server

~~~http
HTTP/1.1 200 OK
Cache-Control: no-cache
ETag: "v7"
Content-Type: application/json

{"id":"p-42","priceMinor":799000}
~~~

Server cho phép cache giữ response, nhưng muốn cache xác thực lại trước khi dùng ở lần sau.

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json

{"accessToken":"<sensitive-value>"}
~~~

Server yêu cầu cache **không lưu** phần nào của request/response liên quan theo ngữ nghĩa response no-store. Ví dụ cố ý minh họa loại dữ liệu rất nhạy cảm; trong hệ thống thực, nên hạn chế tối đa việc đưa token qua response hoặc log và sử dụng các bảo vệ khác phù hợp.

### 4.2. Chỉ thị từ request của client

Client có thể chủ động yêu cầu kiểm tra lại:

~~~http
GET /products/p-42 HTTP/1.1
Cache-Control: no-cache
~~~

**Request no-cache** yêu cầu cache không dùng một bản response đã lưu để đáp ứng request này nếu chưa có xác thực thành công với origin. Đó là một tín hiệu “hãy kiểm tra lại”, không phải lệnh xóa toàn bộ cache.

Client cũng có thể gửi:

~~~http
GET /reports/financial-summary HTTP/1.1
Cache-Control: no-store
~~~

**Request no-store** yêu cầu cache không lưu phần nào của request này hoặc response tới request đó. Nó **không có nghĩa** server đã tự công bố response no-store cho tất cả client; và không phải lệnh xóa mọi bản cache đã tồn tại. Để chính sách tài nguyên được thực thi nhất quán đối với nhiều client, **server nên phát response Cache-Control phù hợp**.

### 4.3. Ma trận trách nhiệm

| Nơi phát | Header | Diễn giải |
| --- | --- | --- |
| Origin trả response | **Cache-Control: no-cache** | Response có thể lưu, nhưng lần dùng lại cần validation. |
| Origin trả response | **Cache-Control: no-store** | Cache không được lưu request/response tương ứng. |
| Client gửi request | **Cache-Control: no-cache** | Đối với request này, cache phải xác thực lại bản lưu trước khi dùng. |
| Client gửi request | **Cache-Control: no-store** | Cache không được lưu request và response của lần trao đổi này. |

**Không dùng request header như một biện pháp bảo mật duy nhất.** Client khác hoặc crawler có thể không gửi nó, trong khi server là bên hiểu mức độ nhạy cảm của tài nguyên.

### 4.4. Nút Reload trong browser nói lên điều gì?

Trình duyệt có thể dùng các chỉ thị request đặc thù khi người dùng bấm Reload hoặc Hard Reload; hành vi cụ thể tùy browser, service worker và trạng thái cache. Không nên kết luận “bấm Reload thì response đã được no-store” hoặc “DevTools Disable cache có nghĩa server đang phát no-store”.

Khi đánh giá chính sách API, hãy **đọc chính xác response Cache-Control ở network trace**, quan sát request tiếp theo và xác minh behavior qua cache thực tế.

## 5. Luồng no-cache với ETag và 304 Not Modified

Đây là ví dụ điển hình thể hiện vì sao **no-cache vẫn có ý nghĩa lưu cache**.

### 5.1. Lần đầu: lấy và lưu representation

~~~http
GET /products/p-42 HTTP/1.1
Host: api.example.com

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-cache
ETag: "product-p42-v7"

{"id":"p-42","name":"Bàn phím","priceMinor":799000}
~~~

Một HTTP cache có đủ điều kiện lưu có thể giữ cả body JSON và ETag **"product-p42-v7"**.

### 5.2. Lần hai: revalidation bắt buộc trước khi dùng body cũ

Khi client yêu cầu lại cùng representation, cache phát một **conditional GET** tới origin:

~~~http
GET /products/p-42 HTTP/1.1
If-None-Match: "product-p42-v7"
~~~

Nếu representation hiện tại vẫn khớp:

~~~http
HTTP/1.1 304 Not Modified
ETag: "product-p42-v7"
Cache-Control: no-cache
~~~

**304 không có response body.** Cache xử lý các metadata liên quan theo quy tắc HTTP và dùng representation đã lưu để hoàn tất request cho client. Một cache có thể trả body 200 cho client sau khi nhận 304 từ origin; những gì client thấy tùy vị trí tầng cache và API, nhưng bản 304 là tín hiệu xác thực lại chứ không phải payload JSON mới.

Nếu sản phẩm đã đổi giá, origin có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-cache
ETag: "product-p42-v8"

{"id":"p-42","name":"Bàn phím","priceMinor":749000}
~~~

Cache có thể cập nhật bản lưu theo chính sách và dùng body mới.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant K as HTTP Cache
    participant O as Origin API
    C->>K: GET /products/p-42
    K->>O: GET lần đầu
    O-->>K: 200 + body + ETag + no-cache
    K-->>C: 200 + body
    Note over K: Có thể lưu body/ETag
    C->>K: GET lần hai
    K->>O: GET + If-None-Match: "v7"
    O-->>K: 304 Not Modified
    Note over K: Xác thực thành công; dùng bản đã lưu
    K-->>C: Representation từ cache
~~~

**Điểm đánh đổi:** request vẫn cần một vòng kiểm tra origin, nên **no-cache không loại bỏ hoàn toàn round-trip latency hay tải xác thực ở server**. Nó có thể giảm lượng body truyền qua mạng khi không đổi, nhất là JSON/file lớn. Nếu origin không hỗ trợ validator và không có cách validation hữu ích, lợi ích băng thông giảm đáng kể.

### 5.3. Với no-store thì chuỗi trên thay đổi thế nào?

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"id":"p-42","priceMinor":799000}
~~~

Cache tuân thủ chuẩn không lưu body của response này, nên ở lần GET kế tiếp không thể dựa trên bản đã lưu đó để dựng lại nội dung sau một response 304. Dù server có phát ETag, **ETag không tự cho phép lưu response bất chấp no-store**.

Đừng nói “no-store cấm hoàn toàn 304”: nếu client hoặc một thành phần khác gửi một conditional request với validator hợp lệ thì origin vẫn có thể trả 304 theo ngữ nghĩa điều kiện HTTP. Điều được no-store quy định là **không lưu response trong HTTP cache**, không phải cấm client sử dụng header điều kiện trong mọi hoàn cảnh. Nếu client không có body hợp lệ tương ứng, 304 đơn lẻ không giúp nó hiển thị representation.

## 6. Validator: ETag, Last-Modified và điều kiện kiểm tra

### 6.1. ETag và If-None-Match

**ETag** là nhãn đại diện cho một representation mà origin phát ra. Cache hoặc client gửi **If-None-Match** để hỏi origin liệu representation đã thay đổi hay chưa:

~~~http
GET /products/p-42 HTTP/1.1
If-None-Match: "product-p42-v7"
~~~

Nếu không đổi, GET có thể nhận **304**; nếu đổi, nhận body mới (thường **200**). Một ETag tốt phải thay đổi khi nội dung có liên quan của representation thay đổi. Nếu API trả giá được tính theo người dùng nhưng ETag chỉ dựa trên **productId** hoặc version chung, nó có thể gây hiểu sai và rò dữ liệu khi cùng một cache dùng cho nhiều representation khác nhau.

### 6.2. Last-Modified và If-Modified-Since

Một lựa chọn khác:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-cache
Last-Modified: Wed, 18 Nov 2026 10:00:00 GMT
Content-Type: application/json

{"id":"p-42","priceMinor":799000}
~~~

Lần sau cache gửi:

~~~http
GET /products/p-42 HTTP/1.1
If-Modified-Since: Wed, 18 Nov 2026 10:00:00 GMT
~~~

Last-Modified thường có độ chính xác theo giây ở HTTP-date, nên cần cẩn thận khi tài nguyên có thể cập nhật nhiều lần trong một giây. ETag phù hợp hơn khi cần phản ánh version chính xác. Khi request chứa cả **If-None-Match** và **If-Modified-Since**, quy tắc ưu tiên điều kiện HTTP cần được áp dụng đúng; đừng viết hai nhánh tự chế độc lập dễ mâu thuẫn.

### 6.3. ETag mạnh, yếu và kiểm soát đồng thời

~~~http
ETag: "p42-v7"
ETag: W/"p42-v7"
~~~

Hai dòng trên là **hai ví dụ riêng**, không phải một response nên gửi hai giá trị ETag. Prefix **W/** biểu thị validator yếu, thích hợp cho một số trường hợp tương đương về mặt ngữ nghĩa nhưng chưa chắc tương đương byte-for-byte.

Với conditional **GET/If-None-Match**, HTTP dùng so sánh ETag yếu theo ngữ nghĩa tương ứng. Với cập nhật có điều kiện bằng **If-Match** để tránh ghi đè, so sánh mạnh mới là điều quan trọng; đừng áp dụng quy tắc revalidation GET một cách máy móc cho **PUT/PATCH**.

**Caching** và **optimistic concurrency control** đều dùng ETag nhưng mục tiêu khác nhau:

- GET + If-None-Match → kiểm tra có thể dùng representation cũ hay không; có thể trả 304.
- PATCH + If-Match → chỉ cập nhật nếu version phù hợp; có thể trả **412 Precondition Failed** khi không còn khớp.

### 6.4. Cache variants và Vary

Giả sử cùng URL có thể trả nội dung tiếng Việt hoặc tiếng Anh:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-cache
Vary: Accept-Language
ETag: "product-p42-vi-v7"
Content-Language: vi
~~~

**Vary** giúp cache phân biệt những representation khác nhau theo các request header được liệt kê. Nếu server trả nội dung theo ngôn ngữ nhưng không công bố Vary phù hợp, cache có thể lấy bản tiếng Việt khi client muốn tiếng Anh. Vấn đề tương tự có thể xảy ra với Content-Encoding hoặc các lựa chọn representation khác.

**Vary không thay thế authorization.** Không nên coi **Vary: Authorization** là đủ để thiết kế phân quyền và chia sẻ cache cho dữ liệu tenant. Nếu response chứa thông tin cá nhân, chọn chính sách cache phù hợp và kiểm tra quyền ở origin, tránh phụ thuộc riêng vào một header biến thể.

## 7. Phân biệt với private, public, max-age và must-revalidate

Để hiểu đúng no-cache/no-store, phải đặt chúng cạnh các chỉ thị Cache-Control khác:

| Chỉ thị | Ý nghĩa chính | Không nên nhầm với |
| --- | --- | --- |
| **no-cache** | Có thể lưu nhưng phải validation thành công trước mỗi lần reuse. | **no-store** |
| **no-store** | Không được lưu request/response theo quy tắc cache. | **no-cache** |
| **private** | Không cho shared cache lưu response; private cache có thể lưu. | Ngăn mọi cache lưu. |
| **public** | Cho phép lưu trong shared cache theo điều kiện áp dụng. | Bảo đảm an toàn để công bố mọi dữ liệu. |
| **max-age=120** | Freshness lifetime theo giây là tối đa 120, có xét tuổi response và các quy tắc khác. | Bắt buộc dùng cache trong 120 giây hoặc luôn bỏ qua origin. |
| **s-maxage=300** | Chính sách freshness cho shared cache, có ảnh hưởng theo ngữ nghĩa chuẩn. | Quy tắc cho private browser cache. |
| **max-age=0** | Freshness lifetime bằng 0; thường dẫn đến revalidation khi reuse. | Tương đương hoàn toàn **no-cache** trong mọi tình huống. |
| **must-revalidate** | Khi response stale, không được reuse nếu chưa validation thành công theo quy tắc. | Bắt buộc validation ngay cả khi response vẫn fresh. |
| **immutable** | Gợi ý response không thay đổi trong freshness lifetime được chỉ định. | Cho phép dùng với URL có nội dung thay đổi bất kỳ. |

### 7.1. Vì sao private không đủ bảo vệ bí mật?

~~~http
Cache-Control: private
~~~

Header trên chặn **shared cache** lưu response, nhưng vẫn cho phép **private cache** lưu nếu điều kiện khác thỏa. Đó có thể là lựa chọn hợp lý với một dashboard cá nhân ít nhạy cảm, nhưng chưa đáp ứng mục tiêu “không để cache giữ dữ liệu tài khoản”.

Nếu muốn ngăn lưu:

~~~http
Cache-Control: private, no-store
~~~

**no-store** đã có nghĩa ngăn lưu ở HTTP cache; **private** có thể được thêm để làm rõ ý định và giúp người đọc nhận biết response gắn với người dùng. Không nên tuyên bố **private** là một bản thay thế của no-store.

### 7.2. Vì sao max-age=0 không hoàn toàn là no-cache?

~~~http
Cache-Control: max-age=0
~~~

Header này khiến freshness lifetime bằng 0 theo ngữ nghĩa liên quan. Trong nhiều luồng tải lại thông thường, nó dẫn đến việc cache phải kiểm tra origin để dùng tiếp. Nhưng **no-cache** nói trực tiếp rằng **không được tái sử dụng response đã lưu nếu chưa validation thành công**, ngay cả khi một quy tắc khác có thể khiến response được coi là fresh.

Không nên thay thế no-cache bằng max-age=0 chỉ vì “nhìn giống nhau” khi chính sách nghiệp vụ yêu cầu **revalidate trước mọi reuse**.

### 7.3. must-revalidate chỉ có tác dụng khi stale

~~~http
Cache-Control: max-age=60, must-revalidate
~~~

Response có thể được dùng khi vẫn fresh trong thời gian phù hợp. Khi stale, cache không được tùy tiện dùng lại mà không validation, kể cả trong nhiều tình huống không liên lạc được origin. **must-revalidate không bắt cache kiểm tra origin cho mọi lần GET khi response còn fresh**, nên cũng không giống no-cache.

### 7.4. public và s-maxage không làm dữ liệu bí mật thành an toàn

Một endpoint công khai, không mang thông tin user và có dữ liệu ổn định có thể dùng:

~~~http
Cache-Control: public, max-age=60, s-maxage=300
~~~

Nhưng không được lấy cấu hình đó áp cho **GET /me/profile**, danh sách đơn hàng cá nhân hay response chứa token. Cần đánh giá bản chất dữ liệu, Authorization, cookie, Vary và khả năng dùng chung một URL trước khi cho phép shared cache lưu.

## 8. Chọn chính sách theo tài nguyên REST API

Không nên có một annotation “cache tất cả” cho toàn bộ controller. Cùng API có thể có nhiều loại dữ liệu với thời gian sống và độ nhạy cảm khác nhau:

| Resource / tình huống | Mục tiêu | Header gợi ý | Giải thích |
| --- | --- | --- | --- |
| **GET /products/{id}**, giá hoặc tồn kho thay đổi thường xuyên, dữ liệu công khai | Muốn kiểm tra phiên bản trước reuse nhưng tiết kiệm body. | **Cache-Control: no-cache** + **ETag** | Có thể lưu, 304 khi không đổi. |
| **GET /me/profile**, chứa thông tin cá nhân | Hạn chế lưu response trong HTTP cache. | **Cache-Control: private, no-store** | Không chỉ dùng private/no-cache. |
| **GET /orders/{id}** theo tenant, có địa chỉ người nhận | Tránh cache giữ thông tin nhạy cảm. | **Cache-Control: no-store** | Luôn xác thực/phân quyền và không cache dữ liệu cá nhân. |
| **GET /dashboard/preferences** có thể lưu riêng, dữ liệu không quá nhạy cảm | Cho browser cache giữ bản nhưng luôn kiểm tra version. | **Cache-Control: private, no-cache** + **ETag** | Shared cache không lưu; private cache có thể lưu và revalidate. |
| **GET /assets/app.abc123.js**, file có content hash trong URL | Tối ưu hiệu năng khi nội dung không đổi. | **Cache-Control: public, max-age=31536000, immutable** | Chỉ phù hợp khi URL đổi lúc nội dung đổi. |
| **GET /catalog/categories**, công khai, thay đổi ít | Cho phép cache trong thời gian ngắn. | **Cache-Control: public, max-age=120** | Giảm round-trip tới origin; chấp nhận mức stale ngắn theo hợp đồng. |
| **GET /reports/payroll.csv** theo quyền, chứa dữ liệu nhạy cảm | Không lưu body ở HTTP cache. | **Cache-Control: private, no-store** | Không ngăn người dùng chủ động lưu file sau tải xuống. |
| **POST /auth/token**, response chứa token | Tránh lưu bí mật trong HTTP cache. | **Cache-Control: no-store** | Không đồng nghĩa ngăn log hoặc lưu token sai cách ở client. |
| **404** cho một resource có thể sớm xuất hiện | Tránh giữ lỗi không tìm thấy lâu. | Quy định cache tường minh, ví dụ **no-cache** hoặc **no-store** theo độ nhạy cảm. | Một số phản hồi lỗi có thể cache theo HTTP; cần cân nhắc. |

**Đây là phương án tham khảo, không phải bảng bắt buộc cho mọi hệ thống.** Dữ liệu, SLO, yêu cầu bảo mật, hành vi browser/CDN và năng lực origin quyết định lựa chọn cuối.

### 8.1. Dữ liệu thường thay đổi nhưng cần nhanh: cân nhắc giữa hai mục tiêu

Đặt **no-cache** cho mọi sản phẩm cho phép tiết kiệm body khi không đổi nhưng vẫn phải liên hệ origin để validation. Nếu hàng triệu client gọi một endpoint công khai với tần suất cao, request revalidation vẫn tạo tải. Khi sản phẩm chấp nhận độ trễ cập nhật 30–120 giây, **max-age** hoặc chính sách CDN riêng có thể phù hợp hơn.

Ngược lại, nếu giá có thể thay đổi tại thời điểm thanh toán, việc client nhìn thấy một representation được revalidate cũng **không thay thế** bước kiểm tra giá ở thao tác đặt hàng. Quy tắc tính tiền phải được kiểm tra tại server với dữ liệu và transaction phù hợp.

### 8.2. Dữ liệu nhạy cảm không chỉ là access token

Thông tin đơn hàng, lịch sử y tế, phiếu lương, số tài khoản, địa chỉ vận chuyển hoặc thông tin định danh có thể cần no-store tùy chính sách. Một response mang dữ liệu cá nhân không tự động an toàn chỉ vì:

- API bắt buộc bearer token;
- URL chứa UUID khó đoán;
- body được mã hóa trên đường truyền bằng HTTPS;
- có **Vary: Authorization**;
- đã gắn **Cache-Control: private**.

Các yếu tố này giải quyết những rủi ro khác nhau; **no-store giúp kiểm soát lưu trữ ở tầng HTTP cache**.

## 9. Authorization, cookie, CDN và các trường hợp rò rỉ

### 9.1. Cẩn thận với response đến từ yêu cầu có Authorization

HTTP có quy tắc hạn chế shared cache sử dụng response của request có header **Authorization**, trừ khi có chỉ thị hoặc điều kiện cho phép phù hợp. Tuy nhiên, không nên lấy điều này làm lý do bỏ qua việc đặt **Cache-Control** cho response chứa dữ liệu nhạy cảm.

Ví dụ:

~~~http
GET /orders/ord-123 HTTP/1.1
Authorization: Bearer <access-token>
~~~

Nếu server vô tình phát:

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=3600
Content-Type: application/json

{"id":"ord-123","recipientAddress":"..."}
~~~

thì đây là dấu hiệu cần xem xét nghiêm túc: **public** có thể thay đổi điều kiện cho phép shared cache lưu response, trong khi body có dữ liệu cá nhân. Hãy thiết kế theo nguyên tắc dữ liệu nào được phép chia sẻ, không chỉ theo sự có mặt của Authorization.

### 9.2. Set-Cookie không phải một chỉ thị cấm cache

Một response có **Set-Cookie** không được xem là mặc nhiên tương đương **no-store** ở mọi tình huống. Nếu nội dung phụ thuộc session hoặc cá nhân, cần chính sách Cache-Control phù hợp, cấu hình cookie an toàn và thử qua cache thực tế.

Tương tự, **Vary: Cookie** có thể phân biệt biến thể nhưng không phải một ranh giới bảo mật đủ thay thế quyền truy cập và no-store cho dữ liệu cần bảo vệ.

### 9.3. Phải kiểm tra cả gateway và CDN

~~~mermaid
flowchart LR
    B[Browser private cache] --> C[CDN shared cache]
    C --> G[API Gateway]
    G --> O[Spring Origin API]
    O -.->|Cache-Control, ETag, Vary| C
    C -.->|Chính sách cache và response| B
~~~

Một cấu hình CDN có thể bỏ qua header origin, áp rule cache theo URL, strip header hoặc cache cả lỗi 404 theo thời hạn riêng. Việc controller trả đúng header trong unit test **chưa chứng minh** request từ ngoài internet nhận đúng chính sách hoặc có hành vi đúng.

Thử các tầng:

1. Gọi trực tiếp origin ở môi trường kiểm soát, kiểm tra header.
2. Gọi qua gateway/CDN và xác minh header đến client không bị thay đổi trái ý định.
3. Gửi hai request cho cùng URL; quan sát Cache-Status hoặc các header chẩn đoán do hạ tầng cung cấp nếu có.
4. Thử với **hai người dùng/tenant khác nhau** và bảo đảm không có representation bị chia sẻ sai.
5. Thử sau khi thay đổi nội dung, đổi token hoặc thu hồi quyền.

Các header như **Age**, **Cache-Status**, **Via** hoặc header riêng của CDN có thể hỗ trợ chẩn đoán, nhưng phải hiểu chính xác ngữ nghĩa của nhà cung cấp; không suy luận “không thấy Age” nghĩa là chắc chắn response không được cache.

## 10. no-store không phải cơ chế invalidation

**Cache invalidation** là bài toán đảm bảo những bản lưu cũ không còn được dùng sai khi resource thay đổi. **no-store** không phải lệnh “xóa cache toàn bộ” và **no-cache** không phải lệnh “làm sạch cache”.

Ví dụ sản phẩm từng được phát:

~~~http
Cache-Control: public, max-age=3600
~~~

Sau đó team đổi chính sách thành:

~~~http
Cache-Control: no-store
~~~

Các cache **có thể vẫn có bản lưu cũ** từ trước khi đổi chính sách; một thay đổi header trên origin không tự bảo đảm mọi cache đang giữ bản cũ lập tức truy cập origin để học chính sách mới. Có thể cần purge/invalidation theo cơ chế CDN, thay URI chứa version hoặc chờ bản cũ hết freshness theo chính sách đã phát.

### 10.1. Cập nhật resource và invalidation

Khi thực hiện **PUT/PATCH/DELETE** thành công, các cache xử lý một số quan hệ URI theo ngữ nghĩa vô hiệu hóa phản hồi của phương thức không an toàn; nhưng phạm vi và thời điểm không nên bị xem là cơ chế đồng bộ dữ liệu tức thì cho mọi tầng. Nếu hệ thống có cache ứng dụng trong Redis, search index hay CDN được cấu hình đặc biệt, còn phải thiết kế invalidation riêng.

Một API sản phẩm có thể:

- gắn **ETag** dựa trên version representation;
- đổi version khi giá, mô tả hoặc trường được trả thay đổi;
- cho **GET no-cache** tái xác thực qua conditional request;
- chủ động purge những entry CDN được cache theo TTL khi cần thay đổi hiển thị sớm;
- tránh dùng **no-store** như một cách chữa sai lầm version/invalidation ở tầng ứng dụng.

### 10.2. no-store không thay thế idempotency

POST tạo đơn hoặc thanh toán có thể bị gửi lặp do mất mạng, timeout gateway hoặc retry. Gắn:

~~~http
Cache-Control: no-store
~~~

vào response POST **không hề** đảm bảo thao tác chỉ được xử lý một lần. Cần **Idempotency-Key**, ràng buộc nghiệp vụ hoặc cơ chế deduplication phù hợp. Caching là về **lưu và dùng lại HTTP representation**; idempotency là về **hiệu ứng của việc xử lý lệnh**.

## 11. Triển khai với Java/Spring

Ví dụ dưới dùng Spring MVC/Spring Boot hiện đại. **ProductService**, **ProfileService** và các DTO là thành phần giả định; mục đích là minh họa việc phát Cache-Control và xử lý conditional GET. Trong hệ thống thật phải bổ sung security, transaction, mapping lỗi và kiểm thử qua gateway.

### 11.1. no-cache với ETag cho sản phẩm công khai

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.WebRequest;

record ProductView(
        String id,
        String name,
        long priceMinor,
        long version
) {}

interface ProductService {
    ProductView getPublishedProduct(String id);
}

@RestController
@RequestMapping("/products")
class ProductController {
    private final ProductService service;

    ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    ResponseEntity<ProductView> get(
            @PathVariable String id, WebRequest webRequest) {

        ProductView product = service.getPublishedProduct(id);

        // Version phải thay đổi khi representation công khai thay đổi.
        String etag = "\"product-" + product.id()
                + "-v" + product.version() + "\"";

        // Spring đánh giá điều kiện HTTP, thay vì so chuỗi ETag thủ công.
        if (webRequest.checkNotModified(etag)) {
            return ResponseEntity
                    .status(HttpStatus.NOT_MODIFIED)
                    .cacheControl(CacheControl.noCache())
                    .eTag(etag)
                    .build();
        }

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noCache())
                .eTag(etag)
                .body(product);
    }
}
~~~

Điều quan trọng:

- **CacheControl.noCache()** phát chính sách no-cache, **không cấm lưu**.
- **WebRequest.checkNotModified(etag)** hỗ trợ xử lý conditional GET theo cơ chế của framework, tránh so sánh ETag đơn giản có thể sai với danh sách tag hoặc weak validators.
- Phản hồi **304 Not Modified** không có body; body 200 chỉ gửi khi phù hợp.
- **Version** phải đại diện đầy đủ cho representation. Nếu giá theo tenant, ngôn ngữ hoặc danh tính khác nhau, phải tính đến representation variant và chính sách cache phù hợp. Đừng dùng ETag chung rồi lộ dữ liệu khác người.
- Nếu response của endpoint yêu cầu Authorization và chứa dữ liệu cá nhân, **không copy no-cache của ví dụ sản phẩm** mà không đánh giá rủi ro lưu body.

### 11.2. no-store cho hồ sơ cá nhân

~~~java
import java.security.Principal;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record ProfileView(String displayName, String email) {}

interface ProfileService {
    ProfileView findForAuthenticatedUser(String userId);
}

@RestController
@RequestMapping("/me")
class ProfileController {
    private final ProfileService service;

    ProfileController(ProfileService service) {
        this.service = service;
    }

    @GetMapping("/profile")
    ResponseEntity<ProfileView> profile(Principal principal) {
        // Security filter phải bảo đảm chỉ principal đã xác thực
        // mới có thể đi đến endpoint này.
        ProfileView value = service.findForAuthenticatedUser(
                principal.getName());
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(value);
    }
}
~~~

**CacheControl.noStore()** yêu cầu cache không lưu response. Nếu hệ thống muốn ghi rõ thêm tính riêng tư, có thể cấu hình **private, no-store** theo API policy và khả năng builder. Không nên lấy **principal** từ query parameter do client tự gửi; phải dựa trên danh tính đã xác thực và kiểm tra quyền ở service.

### 11.3. Lỗi API cũng cần cache policy

Ví dụ endpoint báo lỗi xác thực hoặc phân quyền có thể trả **401/403** với Problem Details theo **RFC 9457**. Khi response chứa thông tin nhạy cảm hay bối cảnh tài khoản, nên áp chính sách **no-store** phù hợp:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders"
Cache-Control: no-store
Content-Type: application/problem+json

{"title":"Authentication required","status":401}
~~~

Không phải mọi lỗi đều cần cùng chính sách. Ví dụ **404** của resource công khai có thể được phép cache trong thời gian ngắn; **404** có thể chứa tín hiệu về quyền hoặc tài nguyên cá nhân thì cần thận trọng hơn. Việc chọn 401/403/404 là quyết định về xác thực và phân quyền, không được sửa tùy tiện chỉ để cache dễ hơn.

### 11.4. Đặt header ở đúng tầng

Trong Spring, header có thể được phát từ **ResponseEntity**, filter hoặc cấu hình cache/security. Nếu dùng nhiều lớp cùng ghi Cache-Control, có nguy cơ bị ghi đè hoặc ghép mâu thuẫn:

~~~http
Cache-Control: public, max-age=3600
Cache-Control: no-store
~~~

Đừng thiết kế theo giả định các client sẽ tự “chọn cái đúng”. Nên có một chính sách thống nhất theo endpoint và kiểm thử response cuối **sau khi qua gateway**. Các chỉ thị không tương thích có thể khiến hành vi phức tạp, khó đoán hoặc cache bỏ lưu; tốt nhất tránh phát tổ hợp mâu thuẫn ngay từ đầu.

## 12. Mô tả chính sách cache trong OpenAPI 3.1

OpenAPI không làm cache tự hoạt động; nó giúp công bố header và các phản hồi có thể phát sinh.

~~~yaml
openapi: 3.1.0
info:
  title: Catalog and Profile API
  version: 1.0.0
paths:
  /products/{id}:
    get:
      summary: Lấy thông tin sản phẩm công khai
      parameters:
        - in: path
          name: id
          required: true
          schema:
            type: string
        - in: header
          name: If-None-Match
          required: false
          description: Validator dùng để kiểm tra representation đã lưu
          schema:
            type: string
      responses:
        '200':
          description: Representation hiện hành
          headers:
            Cache-Control:
              description: no-cache; có thể lưu nhưng phải revalidate
              schema:
                type: string
              example: no-cache
            ETag:
              description: Validator của representation
              schema:
                type: string
              example: '"product-p42-v7"'
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
        '304':
          description: Representation không thay đổi theo điều kiện GET
          headers:
            Cache-Control:
              schema: {type: string}
              example: no-cache
            ETag:
              schema: {type: string}
          # 304 không có response content.
        '404':
          description: Không tìm thấy sản phẩm
  /me/profile:
    get:
      summary: Lấy hồ sơ người dùng đã xác thực
      responses:
        '200':
          description: Hồ sơ cá nhân, không lưu tại HTTP cache
          headers:
            Cache-Control:
              schema: {type: string}
              example: no-store
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Profile'
        '401':
          description: Chưa xác thực hợp lệ
components:
  schemas:
    Product:
      type: object
      properties:
        id: {type: string}
        name: {type: string}
        priceMinor: {type: integer, format: int64}
    Profile:
      type: object
      properties:
        displayName: {type: string}
        email: {type: string}
~~~

Đây là trích đoạn minh họa; một API production còn cần mô tả bảo mật (**securitySchemes**), schema body đầy đủ, response lỗi có cấu trúc và yêu cầu quyền truy cập. OpenAPI mô tả ý định, còn **HTTP response thực tế mới quyết định cache behavior**.

## 13. Kiểm thử Cache-Control và revalidation

### 13.1. Ma trận kiểm thử chức năng

| ID | Kịch bản | Kỳ vọng cần xác minh |
| --- | --- | --- |
| C01 | GET sản phẩm lần đầu | **200**, **Cache-Control: no-cache**, ETag và JSON hợp lệ. |
| C02 | GET cùng sản phẩm với If-None-Match khớp | **304**, không có response body. |
| C03 | Cập nhật giá rồi GET với ETag cũ | **200** với body mới và ETag khác. |
| C04 | GET profile đã xác thực | **200**, **Cache-Control: no-store**, không bị cache chung. |
| C05 | GET profile bằng danh tính khác | Không nhận profile của user trước, dù gọi cùng URI. |
| C06 | Không có hoặc token không hợp lệ | **401**, WWW-Authenticate hợp lệ, body/cache policy an toàn. |
| C07 | Product có bản tiếng Việt/Anh | Vary/validator đúng theo representation nếu được thương lượng theo ngôn ngữ. |
| C08 | Cache nhận response no-cache, gọi lại khi đang fresh | Vẫn revalidate với origin trước reuse. |
| C09 | Cache nhận response no-store | Không lưu response theo quy tắc HTTP cache. |
| C10 | Trước đây max-age=3600, nay đổi thành no-store | Có kế hoạch invalidate/purge các entry cũ; không giả định chúng tự biến mất. |
| C11 | Có CDN hoặc gateway | Response header tới client và hành vi cache phù hợp cấu hình đã công bố. |
| C12 | 404 cho resource công khai có thể xuất hiện sau đó | Không tiếp tục trả 404 cũ sai thời gian nghiệp vụ cho phép. |
| C13 | Gọi với request Cache-Control: no-cache | Cache phải validation trước khi reuse response đang lưu. |
| C14 | Gọi với request Cache-Control: no-store | Cache không lưu request/response lần đó. |
| C15 | HEAD/304 | Không trả body, vẫn bảo toàn metadata và semantics phù hợp. |

Đặc biệt, **C08–C09 không thể được chứng minh chỉ bằng unit test của controller**. Cần có một HTTP cache thật hoặc hệ thống kiểm thử có behavior chuẩn ở giữa client và origin, đo xem response có được lưu và đã gọi origin để xác thực lại hay chưa.

### 13.2. Ví dụ curl

~~~bash
# Đọc status và response headers do origin/gateway thực sự trả.
curl -i 'https://api.example.com/products/p-42'

# Thử conditional GET với ETag đã nhận.
curl -i \
  -H 'If-None-Match: "product-p42-v7"' \
  'https://api.example.com/products/p-42'

# Yêu cầu kiểm tra lại cache cho request hiện tại.
curl -i \
  -H 'Cache-Control: no-cache' \
  'https://api.example.com/products/p-42'

# Kiểm tra response của endpoint cá nhân (token chỉ minh họa).
curl -i \
  -H 'Authorization: Bearer <access-token>' \
  'https://api.example.com/me/profile'
~~~

Lưu ý: lệnh **curl** từ terminal bình thường không tự chứng minh một browser/CDN có lưu response hay không. Nó giúp kiểm tra status/header, và có thể tự gửi conditional request. Muốn chứng minh cơ chế cache, hãy đặt một HTTP cache thật trong đường truyền và quan sát các request tới origin hoặc log/cache metrics phù hợp.

### 13.3. Ví dụ Spring MockMvc

Giả sử ProductService trả product **p-42** ở version 7 và ProfileController yêu cầu authentication đúng cấu hình:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import org.springframework.http.HttpHeaders;

mockMvc.perform(get("/products/p-42"))
    .andExpect(status().isOk())
    .andExpect(header().string(
            HttpHeaders.CACHE_CONTROL, "no-cache"))
    .andExpect(header().string(
            HttpHeaders.ETAG, "\"product-p-42-v7\""));

mockMvc.perform(get("/products/p-42")
        .header(HttpHeaders.IF_NONE_MATCH, "\"product-p-42-v7\""))
    .andExpect(status().isNotModified())
    .andExpect(content().string(""));

// Phải thêm principal/token hợp lệ theo cấu hình security của test.
mockMvc.perform(get("/me/profile"))
    .andExpect(status().isOk())
    .andExpect(header().string(
            HttpHeaders.CACHE_CONTROL, "no-store"));
~~~

Test cuối **chỉ PASS** khi test request đã được xác thực hoặc security được thiết lập để cung cấp principal theo đúng môi trường thử. Nếu API bắt buộc token và không có thông tin đăng nhập, phải mong đợi 401 thay vì 200. Không tắt security trong integration test bảo mật chỉ để kiểm tra header; hãy thử cả luồng 401 và dữ liệu user khác.

### 13.4. Kiểm thử hành vi cache bằng hai lớp

Một kịch bản tích hợp nên:

1. Cho client đi qua cache tới origin và gọi **GET /products/p-42** lần đầu. Origin trả 200, no-cache, ETag v7.
2. Gọi lần hai. Bắt log tại origin: cache phải gửi revalidation (ví dụ If-None-Match v7), không được tự trả body cũ mà bỏ qua origin.
3. Origin trả 304. Xác minh response client nhận là representation đúng và body không bị nhân đôi/trộn metadata.
4. Đổi version lên v8. Lần gọi sau phải hiển thị nội dung mới, không dùng v7 khi chưa xác thực thành công.
5. Lặp lại với **GET /me/profile** phát no-store; xác minh cache không lưu/không phục vụ từ bản của user A cho user B.
6. Thử khi origin tạm mất kết nối. Response no-cache đã lưu không được phát lại như thể đã revalidate thành công.
7. Nếu có CDN, kiểm tra cả rule tại CDN vì nó có thể chặn hoặc ghi đè Cache-Control từ origin.

Muốn đánh giá độ tin cậy, nên kết hợp **trace ID**, log origin request, metric cache hit/revalidation và test theo từng URI/tenant. Chỉ dựa vào một dòng header không đủ để chứng minh hạ tầng đã tuân thủ.

## 14. Đánh đổi hiệu năng và các con số minh họa

Giả sử endpoint sản phẩm trả body JSON trung bình khoảng **40 KB**, có **1.000 GET mỗi giây** và trong một khoảng quan sát **80%** các lần kiểm tra không phát hiện thay đổi.

- Nếu mọi request đều lấy lại body đầy đủ, riêng payload khoảng **40 MB/giây** theo phép tính đơn giản chưa tính header/giao thức.
- Nếu dùng **no-cache + ETag** và các lần không đổi nhận 304, lượng payload JSON gửi từ origin có thể giảm đáng kể; với giả định 80% không đổi, còn khoảng **8 MB/giây** body của những request thực sự đổi, chưa tính các byte HTTP/304 và biến động thực tế.
- Nhưng **origin vẫn phải xử lý xác thực lại cho các request**; no-cache không chuyển bài toán sang “không có request tới server”.
- Nếu chọn một **max-age** cho phép dùng bản fresh không cần revalidation, origin có thể nhận ít request hơn, đổi lại client có thể thấy nội dung chưa cập nhật trong thời gian chấp nhận.
- Nếu dùng **no-store**, các HTTP cache không được lưu body để phục vụ request tương lai; có thể tăng lượng truyền dữ liệu nhưng đáp ứng tốt hơn mục tiêu tránh lưu ở cache.

Đây là **mô hình giả định**, không phải benchmark hay SLA. Phải đo theo payload thực, tỷ lệ thay đổi, kích thước header, nén, CDN tier, latency, connection reuse, chi phí origin và chính sách bảo mật. Đừng tối ưu băng thông bằng cách cho shared cache lưu dữ liệu nhạy cảm.

## 15. Các phản mẫu cần tránh

| Phản mẫu | Vì sao sai hoặc nguy hiểm? | Cách sửa |
| --- | --- | --- |
| “no-cache nghĩa là không lưu gì.” | Cache vẫn có thể lưu body. | Dùng **no-store** khi mục tiêu thực sự là cấm lưu response. |
| “no-store chỉ là luôn revalidate.” | no-store ngăn lưu, không phải mô hình ETag/304 từ bản đã giữ. | Chọn no-cache nếu muốn lưu và xác thực lại. |
| Dùng **private** thay **no-store** cho token/hồ sơ nhạy cảm | Private cache vẫn được phép lưu. | Dùng **no-store** theo yêu cầu bảo vệ dữ liệu. |
| Dùng **max-age=0** như định nghĩa tương đương no-cache | Semantics khác; no-cache cấm reuse thiếu validation kể cả khi fresh. | Công bố no-cache nếu cần điều kiện bắt buộc đó. |
| Nghĩ **must-revalidate** luôn hỏi origin | Fresh response vẫn có thể được dùng trong freshness lifetime. | Xác định có yêu cầu revalidation cho mọi reuse không. |
| Nghĩ **ETag** tự bật caching bất chấp no-store | Validator không ghi đè lệnh cấm lưu. | Thiết kế validator và cache policy đồng bộ. |
| Chỉ kiểm tra controller, không kiểm CDN | Hạ tầng có thể ghi đè/strip header, cache sai policy. | Integration test qua toàn bộ đường truyền. |
| Dùng **public** trên response theo tenant | Có thể cho shared cache giữ dữ liệu riêng. | Phân loại dữ liệu và cấu hình no-store/private phù hợp. |
| Cho rằng **Set-Cookie** ngăn cache mặc định | Không phải một cache directive thay no-store. | Khai báo Cache-Control và thử hành vi. |
| Đổi policy sang no-store và nghĩ mọi cache cũ đã bị xóa | no-store không tự invalidate entry cũ đã fresh. | Purge/invalidation/versioned URI khi cần. |
| Trả cùng ETag cho representation khác người | Validation có thể làm client nhận bản không đúng. | ETag theo representation/variant và Vary/cache scope phù hợp. |
| Dùng no-store để giải quyết POST bị retry trùng | Cache policy không quyết định idempotency nghiệp vụ. | Idempotency key/transaction/deduplication. |
| Đưa PII vào log vì response đã no-store | Cache policy không kiểm soát hệ thống log. | Redact dữ liệu, giới hạn quyền và retention. |
| Bỏ qua 404/401/403 trong cache policy | Lỗi cũng có thể bị lưu/tái sử dụng theo quy tắc HTTP. | Công bố và thử policy ở các response lỗi phù hợp. |

## 16. Bài tập thực hành: chọn chính sách cho API thương mại điện tử

### 16.1. Tình huống

Một nền tảng thương mại điện tử có những endpoint:

1. **GET /catalog/products/{id}** trả tên và mô tả công khai; giá có thể đổi trong ngày.
2. **GET /me/account** trả tên, email, số điện thoại và địa chỉ người dùng.
3. **GET /orders/{id}** trả đơn hàng kèm địa chỉ giao hàng và trạng thái thanh toán.
4. **GET /assets/app.4f19b2.js** là file JavaScript đặt tên theo hash nội dung.
5. **POST /payments** tạo giao dịch thanh toán, có nguy cơ client retry khi gateway trả 504.

Một thành viên đề xuất gắn **Cache-Control: no-cache** cho **tất cả** endpoint vì “không muốn cache dữ liệu cũ”. Một thành viên khác đề xuất **no-store** cho tất cả để “đảm bảo luôn mới”. Hệ thống sử dụng Spring Boot sau CDN và có frontend chạy ở browser.

### 16.2. Yêu cầu

1. Chọn cache policy cho từng endpoint và giải thích đánh đổi giữa freshness, băng thông và bảo mật.
2. Mô tả hai request GET sản phẩm liên tiếp với ETag: lần đầu 200, lần sau nội dung không đổi.
3. Chỉ ra vì sao no-cache **không đủ** cho response hồ sơ chứa dữ liệu nhạy cảm.
4. Giải thích tại sao no-store **không thay thế** cơ chế chống thanh toán trùng.
5. Đề xuất một kiểm thử chứng minh CDN không làm lộ đơn hàng giữa tenant A và tenant B.
6. Nếu sản phẩm trước đây có **max-age=3600**, việc đổi sang no-store có ngay lập tức xóa mọi cache cũ không?

### 16.3. Phương án tham khảo

| Endpoint | Chính sách gợi ý | Lý do |
| --- | --- | --- |
| GET sản phẩm | **no-cache** + **ETag** nếu yêu cầu revalidation trước reuse; cân nhắc **max-age** ngắn nếu chấp nhận độ trễ cập nhật. | Dữ liệu công khai, có ích khi tránh tải lại body. |
| GET hồ sơ | **private, no-store** | Tránh HTTP cache lưu dữ liệu cá nhân. |
| GET đơn hàng cá nhân | **no-store** | Quyền và dữ liệu nhạy cảm, không chỉ dựa vào UUID. |
| GET asset fingerprinted | **public, max-age=31536000, immutable** | Hash URL đổi khi nội dung đổi; tiết kiệm request. |
| POST thanh toán | **no-store** cho response có thông tin nhạy cảm; **Idempotency-Key** cho request và kiểm soát giao dịch. | no-store không ngăn backend xử lý lặp. |

Với GET sản phẩm, origin lần đầu trả **200 + body + Cache-Control: no-cache + ETag: "v7"**. Khi cache có bản v7, lần GET sau phải validation với **If-None-Match: "v7"**. Nếu không đổi, origin trả **304** không body và cache dùng representation đã lưu theo quy tắc.

Với hồ sơ, **no-cache** vẫn cho phép lưu body ở cache phù hợp, do đó chưa đáp ứng mục tiêu tránh lưu thông tin cá nhân. **no-store** không ngăn lưu ở app state hoặc log, nhưng giúp quy định rõ không lưu trong HTTP cache.

Với POST thanh toán, dù client nhận 504, lệnh có thể đã commit. Thiết kế retry phải dựa vào idempotency key, trạng thái giao dịch hoặc biện pháp chống trùng có kiểm soát, không dựa vào Cache-Control.

Để kiểm tra CDN, dùng **hai danh tính/tenant**, gửi cùng route dạng template và xác minh mỗi request luôn qua kiểm tra quyền; không có body/header chứa dữ liệu người khác, đồng thời quan sát cache status/rule ở CDN. Khi đổi policy từ **max-age=3600** sang **no-store**, cần xem xét **purge/invalidation** đối với entry cũ; header mới không bảo đảm mọi cache đã lưu trước đó bị xóa ngay.

### 16.4. Câu hỏi nâng cao

- Nếu server trả **Cache-Control: no-cache, max-age=600**, cache có thể dùng body đã lưu trong 600 giây mà không validation không?
- Nếu response **no-store** vẫn kèm ETag, client có thể kỳ vọng browser lưu body để hưởng 304 không?
- Nếu frontend JavaScript giữ thông tin profile trong state sau GET, no-store có tự xóa state khi người dùng đăng xuất không?
- Nếu GET sản phẩm có **Vary: Accept-Language**, một ETag chung cho hai ngôn ngữ có luôn chính xác không?

**Gợi ý:** (1) không, no-cache yêu cầu validation trước reuse; (2) không, no-store không cho HTTP cache giữ body đó; (3) không, phải xử lý state ở ứng dụng; (4) cần ETag và định danh representation đúng theo từng variant, không dùng chung một cách tùy tiện.

## 17. Checklist thiết kế và đánh giá HTTP caching

- [ ] Phân biệt rõ **lưu response** và **dùng lại response đã lưu**.
- [ ] Hiểu **no-cache** cho phép lưu nhưng **bắt buộc revalidation thành công** trước reuse.
- [ ] Hiểu **no-store** yêu cầu HTTP cache **không lưu** request/response tương ứng.
- [ ] Phân biệt Cache-Control do **client gửi request** với header **server phát response**.
- [ ] Không xem no-store là công cụ xóa hồi tố mọi cache cũ, log hay frontend state.
- [ ] Chọn cache policy theo **độ nhạy cảm và độ mới cần thiết** của từng resource.
- [ ] Response chứa token hoặc PII có no-store phù hợp; không chỉ dựa vào private/HTTPS/UUID.
- [ ] Với no-cache, có validator như ETag/Last-Modified khi hữu ích, cùng code xử lý 304 không body.
- [ ] ETag phản ánh đúng version của representation, có xem xét Vary và bản dịch.
- [ ] 304 không có JSON body; client/cache hiểu cách dùng bản lưu sau validation.
- [ ] Không nhầm **private**, **max-age=0**, **must-revalidate** với no-cache/no-store.
- [ ] Cẩn trọng với Authorization, Set-Cookie, shared cache và các response lỗi.
- [ ] Mọi chính sách được thử sau **gateway/CDN**, không chỉ ở controller.
- [ ] Kiểm thử người dùng/tenant khác nhau để không có cross-user cache leak.
- [ ] Có kế hoạch purge/invalidation khi đổi policy hoặc cập nhật resource quan trọng.
- [ ] Không dùng caching để giải quyết idempotency hay optimistic locking nghiệp vụ.
- [ ] Spring controller/filter phát header thống nhất; OpenAPI ghi rõ policy liên quan.
- [ ] Test status, Cache-Control, ETag, If-None-Match, 304, 401/403 và hành vi cache thật.
- [ ] Đo cả round-trip revalidation, tỉ lệ 304, bytes tiết kiệm và tải origin.

**Kết luận:** **no-cache** và **no-store** không phải hai cách viết của cùng một chính sách. **no-cache cho phép lưu nhưng buộc cache phải xác thực lại trước khi sử dụng**, giúp tận dụng ETag và 304 cho tài nguyên thường thay đổi. **no-store ngăn HTTP cache lưu response**, phù hợp khi cần hạn chế lưu dữ liệu nhạy cảm. Muốn REST API vừa nhanh vừa an toàn, cần phối hợp Cache-Control với validator, Vary, Authorization, quyền truy cập, chính sách CDN, OpenAPI và kiểm thử end-to-end; không dựa vào tên chỉ thị hay một response header đơn lẻ để suy ra toàn bộ hệ thống đã an toàn.
