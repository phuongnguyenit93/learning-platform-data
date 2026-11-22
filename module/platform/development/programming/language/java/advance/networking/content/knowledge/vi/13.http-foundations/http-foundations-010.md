# Cache-Control, ETag, Last-Modified và yêu cầu HTTP có điều kiện

## 1. Vấn đề và mục tiêu

Giả sử một trình duyệt tải tài liệu qua HTTP:

~~~http
GET /articles/42 HTTP/1.1
Host: example.test
~~~

Server trả `200 OK` kèm nội dung 50 KiB. Người dùng mở lại URL sau vài giây. Có nhất thiết phải tải toàn bộ 50 KiB lần nữa? Không. Một **HTTP cache** có thể lưu phản hồi trước đó, quyết định **nó còn mới (fresh)** hay **đã cũ (stale)**, và nếu stale thì **xác minh lại** với origin bằng một yêu cầu **có điều kiện**. Nếu nội dung không đổi, origin có thể trả **`304 Not Modified` không mang representation body**, để client sử dụng lại bản đã lưu.

Ba nhóm header đóng vai trò khác nhau:

- **`Cache-Control`:** mô tả **chính sách cache** — phản hồi có thể lưu ở đâu, được tái sử dụng trong bao lâu và khi nào cần revalidate.
- **`ETag`:** **validator** dạng opaque token do server cấp để nhận diện một phiên bản của **selected representation**; client gửi lại qua `If-None-Match` hoặc `If-Match`.
- **`Last-Modified`:** thời điểm server cho rằng representation được sửa lần gần nhất; client có thể gửi lại qua `If-Modified-Since` hoặc dùng cho một số điều kiện khác.

**Yêu cầu có điều kiện** không chỉ dùng cho tiết kiệm băng thông: `If-Match` và `If-Unmodified-Since` có thể bảo vệ thao tác cập nhật khỏi **lost update**. Nhưng cache freshness, validation và write preconditions là **ba vấn đề liên quan mà không đồng nhất**.

Sau bài này, bạn cần giải thích được luồng `200 → cache → 304`, phân biệt `no-cache` với `no-store`, mạnh/yếu của ETag, độ chính xác của `Last-Modified`, thứ tự ưu tiên các conditional headers, cách dùng `Vary`, các mã `200/304/412`, và viết thử một HTTP server/client Java 17+ tái hiện các trường hợp đó.

## 2. Các thuật ngữ: cache, representation, freshness và validation

### 2.1. Resource không đồng nghĩa đúng một dãy byte

**Resource** là khái niệm được định danh qua URI, ví dụ `/articles/42`. **Representation** là nội dung đã được chọn để trả ở thời điểm cụ thể, gồm metadata và representation data. Cùng một resource có thể có nhiều representation:

- `Accept-Encoding: gzip` so với `identity`.
- `Accept-Language: vi` so với `en`.
- Nội dung cho thiết bị/định dạng khác nhau, nếu server thực sự thực hiện content negotiation.

Vì vậy ETag thường gắn với **selected representation**, không phải là một ID nghiệp vụ bất biến cho mọi biến thể. Nếu byte content-coding thay đổi, **strong ETag** của hai representation không nên được dùng như thể chúng cùng một dãy byte.

### 2.2. Ba nơi xử lý cache điển hình

~~~text
Client / browser
       |
       | (1) local/browser/private cache?
       v
Shared cache / reverse proxy / CDN
       |
       | (2) có bản fresh? có cần revalidation?
       v
Origin server
       |
       v
Selected representation + caching metadata
~~~

- **Private cache:** thường gắn với một người dùng, ví dụ cache trình duyệt.
- **Shared cache:** có thể phục vụ nhiều người dùng, ví dụ CDN/reverse proxy. Vì chia sẻ, nó có hạn chế nghiêm ngặt hơn đối với dữ liệu cá nhân và phản hồi có `Authorization`.
- **Origin:** nguồn cung cấp representation hoặc quyết định validator cho tài nguyên.

Một cache có thể lưu **metadata** và representation body. “Cache hit” có thể là **fresh hit** (không gọi origin) hoặc **revalidated hit** (gửi request có điều kiện, nhận 304 rồi dùng lại body cũ). Chúng không giống nhau về latency/băng thông.

### 2.3. Fresh khác Valid

- **Freshness:** cache có quyền **tái sử dụng phản hồi mà không cần liên hệ origin** hay không, theo metadata và thời gian hiện tại.
- **Validation:** cache/client hỏi origin xem **phiên bản đã lưu còn phù hợp** không, bằng validator.
- **Invalidation:** khiến cache không được tùy tiện tiếp tục phục vụ entry cũ, ví dụ do thao tác unsafe method hoặc purge; không có nghĩa origin đã đổi nội dung ngay tức thì.

Một response có `ETag` nhưng **không có `Cache-Control`** vẫn có validator; nhưng `ETag` **không tự đặt TTL**. Ngược lại một response `Cache-Control: max-age=600` có thể fresh trong 10 phút mà **không có ETag**, nhưng khi stale sẽ khó xác minh rẻ nếu không có validator.

## 3. Vòng đời của một bản cache

Ví dụ origin trả:

~~~http
HTTP/1.1 200 OK
Date: Wed, 10 Jan 2024 00:00:00 GMT
Cache-Control: public, max-age=600
ETag: "article-42-v7"
Last-Modified: Wed, 10 Jan 2024 00:00:00 GMT
Content-Type: text/plain; charset=utf-8
Content-Length: 12

Hello world!
~~~

`Content-Length` và body chỉ là ví dụ độc lập. Cache được phép lưu nếu các điều kiện khác của HTTP caching phù hợp. Khi còn trong **freshness lifetime** 600 giây, cache có thể phục vụ body đã lưu mà không gọi origin. Khi stale, cache có thể gửi:

~~~http
GET /articles/42 HTTP/1.1
Host: example.test
If-None-Match: "article-42-v7"
~~~

Nếu selected representation vẫn phù hợp:

~~~http
HTTP/1.1 304 Not Modified
Date: Wed, 10 Jan 2024 00:10:02 GMT
Cache-Control: public, max-age=600
ETag: "article-42-v7"
Last-Modified: Wed, 10 Jan 2024 00:00:00 GMT
~~~

Server **không gửi lại representation body**. Cache nhận 304 và **cập nhật metadata của stored response phù hợp**, sau đó có thể trả bản cached 200/body cho client sử dụng. Không được lấy `304` làm “một bài viết rỗng”.

Nếu origin đã đổi representation, nó trả `200 OK` kèm **body mới**, ETag mới và metadata mới. Chỉ server/ứng dụng biết nội dung đã đổi; client không được tự xem `304` như một bản 200 mới đủ dữ liệu.

### 3.1. Thời điểm hết freshness không phải lúc dữ liệu chắc chắn đã đổi

`max-age=600` nói về **thời gian có thể phục vụ mà không xác minh**, không phải “server cứ 600 giây thay đổi nội dung”. Một bản đã stale có thể vẫn đúng từng byte; cache revalidate và nhận 304 là trường hợp bình thường. Ngược lại bản **fresh** có thể đã lỗi thời so với cập nhật tức thời ở origin: freshness là chính sách chấp nhận mức chậm, không phải đồng bộ tức thì.

## 4. Cache-Control: một header nhưng nhiều chính sách khác nhau

`Cache-Control` có thể xuất hiện trong **response** và **request**, với ý nghĩa liên quan nhưng khác nhau. Các directive phân tách bằng dấu phẩy, ví dụ `Cache-Control: private, max-age=0, must-revalidate`.

### 4.1. Response directives thường gặp

| Directive | Ý nghĩa chính | Lưu ý |
| --- | --- | --- |
| `max-age=600` | Response có thể fresh tối đa 600 giây theo cách tính tuổi cache | Không phải thời hạn chắc chắn resource chưa đổi |
| `s-maxage=60` | Đặt freshness lifetime cho **shared caches** | Có thể ghi đè `max-age` đối với shared cache |
| `public` | Đánh dấu response đủ điều kiện lưu ở **shared cache** trong những điều kiện tương ứng | Không tự giải quyết chuyện lộ dữ liệu; phải kiểm soát nội dung |
| `private` | **Shared cache không được lưu** response được đánh dấu private | Private/browser cache có thể lưu nếu không có cấm khác |
| `no-cache` | Cache có thể lưu nhưng **phải validate** trước khi tái sử dụng (trừ ngoại lệ field-name semantics) | **Không đồng nghĩa cấm lưu** |
| `no-store` | Cache không được cố ý lưu request/response theo chính sách này | Không bảo đảm xóa bản đã lưu trước đó hay xóa mọi log/hệ điều hành |
| `must-revalidate` | Khi stale, cache **không được phục vụ** mà chưa revalidate thành công, theo quy tắc HTTP | Kết hợp TTL hữu ích cho dữ liệu cần freshness nghiêm ngặt |
| `proxy-revalidate` | Yêu cầu tương tự `must-revalidate` dành cho shared caches | Ít phổ biến hơn `must-revalidate` |
| `immutable` | Trong thời gian fresh, representation được tuyên bố sẽ không đổi; client phù hợp có thể bỏ revalidation thông thường | Dùng tốt cho asset URL versioned/hash |
| `stale-while-revalidate=30` | Có thể cho phép phục vụ stale trong thời gian giới hạn khi đang revalidate nền, nếu cache hỗ trợ | Phụ thuộc cache và chính sách khác |
| `stale-if-error=120` | Cho phép phục vụ stale trong khoảng giới hạn khi gặp lỗi, nếu chính sách cho phép | Không thay thế phương án phục hồi lỗi |
| `no-transform` | Yêu cầu intermediary không sửa đổi representation data trái phép theo quy tắc tương ứng | Không phải chính sách freshness |

`Expires` là header HTTP-date đặt thời điểm freshness tuyệt đối trong một số trường hợp. Khi `Cache-Control: max-age` thích hợp có mặt, nó có ưu tiên so với `Expires` theo HTTP caching. Với shared cache, `s-maxage` có thể ưu tiên hơn `max-age`.

Một số cache có thể suy ra **heuristic freshness** khi response có thể cache nhưng không có explicit freshness lifetime. Vì vậy **không được coi thiếu Cache-Control là chắc chắn không cache**. Nếu cần ngăn cache dữ liệu nhạy cảm, khai báo chính sách rõ ràng.

### 4.2. `no-cache` KHÁC `no-store`

Hai response:

~~~http
Cache-Control: no-cache
ETag: "v12"
~~~

và:

~~~http
Cache-Control: no-store
~~~

khác đáng kể:

- Với **`no-cache`**, cache **có thể giữ body**. Trước khi dùng lại, nó phải xác minh với origin; nếu nhận `304` thì vẫn có thể phục vụ body cũ theo metadata đã cập nhật.
- Với **`no-store`**, cache **không được cố ý lưu** response theo policy. Vì không có bản đã lưu để sử dụng lại, thường không có lợi ích “304 + dùng cached body” từ lần này.

“`Cache-Control: no-cache`” nghe như “không cache” nhưng theo giao thức là **không tái sử dụng khi chưa validate**. Sai lầm này dễ gây phí băng thông và hiểu lầm khi debug browser.

### 4.3. `max-age=0` khác `no-cache` một cách kỹ thuật

`Cache-Control: max-age=0` định nghĩa **freshness lifetime bằng 0**, khiến response thông thường trở nên stale ngay theo cách tính tuổi. Nó **không cấm lưu**. Khi cần dùng lại, cache có thể phải validate hoặc dùng quy tắc reuse stale nếu được phép. `no-cache` đặt yêu cầu validate trước reuse một cách tường minh, không phụ thuộc chỉ riêng thời gian freshness.

Khi muốn “lưu nhưng mỗi lần dùng đều xác minh”, chính sách như:

~~~http
Cache-Control: private, no-cache
ETag: "profile-42-v8"
~~~

là ví dụ hợp lý với nội dung chỉ dành cho private cache. Đối với một tài liệu cần stale behavior nghiêm ngặt, cũng có thể:

~~~http
Cache-Control: private, max-age=0, must-revalidate
ETag: "doc-v7"
~~~

Hai chính sách có thể cho hành vi tương tự trên cache thông thường, nhưng **không có nghĩa mọi edge case của directives giống hệt nhau**.

### 4.4. `public`, `private` và dữ liệu cá nhân

Ví dụ:

~~~http
Cache-Control: public, max-age=86400
~~~

phù hợp với tài nguyên công khai **chỉ khi** server thật sự muốn shared cache lưu và phục vụ cho nhiều người. Với một JSON chứa dữ liệu riêng của user, có thể dùng:

~~~http
Cache-Control: private, no-store
~~~

để giảm nguy cơ cache lưu/phát lại; cần đánh giá chính sách và rủi ro của hệ thống. **Không dùng `Vary: Cookie` hoặc ETag theo user như lớp bảo mật chính** cho dữ liệu private. Kiểm soát authz, cache key, headers và dữ liệu trả về vẫn cần đúng; `Set-Cookie`/`Authorization` không phải một cơ chế bảo đảm “an toàn khỏi mọi shared cache” trong mọi cấu hình.

### 4.5. `immutable` phù hợp URL có hash nội dung

Ví dụ asset JS được đặt tên theo hash:

~~~http
GET /assets/app.4a81d1.js HTTP/1.1
Host: example.test

HTTP/1.1 200 OK
Cache-Control: public, max-age=31536000, immutable
ETag: "hash-4a81d1"
~~~

Khi nội dung đổi, phát hành **URL mới** (hash mới), không ghi đè byte vào URL cũ đã phát hành như immutable. Nếu tái sử dụng URL cũ cho nội dung mới, client có thể tiếp tục xem bản cũ trong suốt freshness lifetime, dù server đã cập nhật.

## 5. Request Cache-Control: client có thể yêu cầu cách phục vụ khác

Request directives là tín hiệu **từ client tới cache/intermediary**, không phải tất cả đều là lệnh origin “bỏ qua mọi cache”. Ví dụ:

~~~http
GET /articles/42 HTTP/1.1
Host: example.test
Cache-Control: no-cache
~~~

đề nghị cache **không sử dụng** một stored response để thỏa mãn request khi chưa xác minh với origin. Client/caches có thể gửi `If-None-Match` tương ứng nếu có bản đã lưu và validator.

Một số request directives:

| Request directive | Ý nghĩa |
| --- | --- |
| `no-cache` | Yêu cầu cache không dùng stored response để thỏa mãn request khi chưa validate thành công |
| `no-store` | Yêu cầu cache không cố ý lưu request/response liên quan; không tự xóa mọi bản cũ |
| `max-age=0` | Client chấp nhận tối đa 0 giây độ tuổi theo request freshness constraint |
| `max-stale[=N]` | Client có thể chấp nhận bản stale trong giới hạn tương ứng khi chính sách cho phép |
| `min-fresh=N` | Client muốn response còn fresh ít nhất N giây |
| `only-if-cached` | Yêu cầu cache không gọi origin để thỏa mãn request; có thể dẫn tới `504 Gateway Timeout` nếu không có stored response phù hợp |

Không dựa vào việc browser có một header “refresh” để tuyên bố chính xác toàn bộ luồng cache; các trình duyệt và CDN có chính sách khác nhau. Để debug, quan sát **actual request/response headers**, status codes, `Age` và thông tin hit/miss của cache cụ thể.

## 6. Tuổi cache: Date, Age và freshness lifetime

Cache freshness không chỉ là “ngày tải + max-age”. Một cache tính **current age** của response dựa trên metadata/đường đi, bao gồm `Date`, `Age`, thời gian response transit và thời gian lưu tại cache theo quy tắc HTTP.

Ví dụ:

~~~http
HTTP/1.1 200 OK
Date: Wed, 10 Jan 2024 00:00:00 GMT
Cache-Control: public, max-age=600
Age: 90
~~~

Nếu nhận response đã có `Age: 90`, shared cache/client không nên coi **toàn bộ 600 giây** như vừa bắt đầu tại thời điểm nhận. Response đã có tuổi. Sau thời gian lưu thêm, age tăng; khi current age vượt freshness lifetime thì stale, cần revalidate hoặc áp dụng chính sách reuse stale phù hợp.

`Date` thường là thời điểm origin tạo response, **không phải `Last-Modified`**. Một tài liệu không đổi trong một tuần có thể được gửi lúc hiện tại với `Date` hiện tại, nhưng `Last-Modified` vẫn là tuần trước. Lẫn hai header sẽ khiến logic conditional GET sai.

`Last-Modified` **không phải TTL**. `ETag` **không phải TTL**. `Cache-Control` xác định phần lớn freshness policy; `Age/Date` tham gia tính tuổi khi cache xử lý.

## 7. ETag: validator opaque, strong và weak

### 7.1. ETag là gì?

`ETag` là **entity tag** do server tạo cho selected representation. Ví dụ:

~~~http
ETag: "v7"
ETag: "sha256-1b2c3d..."
ETag: W/"v7"
~~~

Cú pháp có **dấu nháy kép** quanh opaque-tag. `W/` là **tiền tố weak validator**, **không** nằm bên trong dấu nháy. Server có thể tạo tag từ phiên bản dữ liệu, hash, build ID hay cơ chế đáng tin khác; **ETag không bắt buộc là hash** và client không nên phân tích ý nghĩa bên trong như một API ổn định.

Server phải tạo ETag có **ngữ nghĩa phù hợp với sự thay đổi của representation**. Nếu bytes thay đổi nhưng vẫn phát cùng **strong ETag**, các yêu cầu có điều kiện có thể nhận kết quả sai hoặc cập nhật bị mất.

### 7.2. Strong ETag và Weak ETag

| Đặc điểm | Strong ETag | Weak ETag |
| --- | --- | --- |
| Ví dụ | `"abc"` | `W/"abc"` |
| Ngụ ý | Nhận diện representation theo so sánh mạnh cho cùng nội dung dữ liệu biểu diễn | Các representations có thể được xem là tương đương về mặt ngữ nghĩa, dù byte khác |
| So sánh trong `If-None-Match` | Dùng **weak comparison** | Dùng **weak comparison** |
| So sánh trong `If-Match` | Dùng **strong comparison** | Không thể thỏa điều kiện strong chỉ bằng weak tag |
| Kiểm soát lost update | Có thể dùng với `If-Match` | Không phù hợp thay strong validator cho `If-Match` |
| Range / If-Range | Có thể dùng strong validator phù hợp | Weak entity-tag không dùng cho `If-Range` |

Ví dụ cho If-None-Match (weak comparison):

~~~text
Current ETag:       "v7"
If-None-Match:      W/"v7"
Weak comparison:    MATCH
GET kết quả:        304 nếu các precondition khác phù hợp

Current ETag:       W/"v7"
If-Match:           "v7"
Strong comparison:  NO MATCH
Khi cập nhật:       412 Precondition Failed
~~~

**Điểm tinh tế:** “weak” không có nghĩa “kém bảo mật của hash”; nó mô tả **loại tương đương được phép giữa representations**. Auth/trust và ETag là hai vấn đề khác nhau. Một ETag dễ đoán vẫn có thể hợp lệ về mặt validator; đừng sử dụng ETag làm secret token để chứng minh quyền truy cập.

### 7.3. Điều kiện If-None-Match có thể gồm nhiều tag hoặc *

~~~http
If-None-Match: "v5", "v6", W/"v7"
~~~

Client có thể gửi **danh sách** validators. Cũng có cú pháp:

~~~http
If-None-Match: *
~~~

Dấu `*` biểu diễn điều kiện tài nguyên hiện **có representation** theo semantics HTTP, không phải chuỗi opaque tag bình thường. Với GET/HEAD, nếu điều kiện `If-None-Match` **không thỏa** (selected representation khớp validator), origin thường trả **`304`**. Với phương thức khác, khi điều kiện không thỏa có thể trả **`412 Precondition Failed`**, chẳng hạn dùng `If-None-Match: *` để **tạo tài nguyên chỉ khi chưa tồn tại**.

**Cẩn thận khi viết parser:** ETag opaque có thể chứa một số ký tự được phép trong dấu nháy. Không tự tách `If-None-Match` bằng `String.split(",")` rồi khẳng định đã parse RFC chính xác. Trong ứng dụng production, dùng parser HTTP chuẩn hoặc mã xử lý đầy đủ các dạng entity tag, weak comparison, wildcard và list syntax. Ví dụ Java ở phần 12 cố ý chỉ hỗ trợ **một strong tag chính xác** để dạy luồng căn bản.

### 7.4. ETag và content encoding

Nếu server trả nội dung tương tự với hai encoding:

~~~text
GET /data, Accept-Encoding: identity -> bytes A
GET /data, Accept-Encoding: gzip     -> bytes B
~~~

thì nếu bytes khác nhau, không dùng **cùng strong ETag** như thể là cùng một representation byte sequence. Một cách làm phổ biến là tạo strong ETag riêng cho từng variant hoặc weak tags nếu semantics và chính sách cho phép. Cần gửi `Vary: Accept-Encoding` để cache không chọn nhầm bản đã lưu (xem phần 10).

## 8. Last-Modified: validator theo thời gian

`Last-Modified` thường chứa thời điểm resource/representation được sửa lần cuối, theo **HTTP-date**:

~~~http
Last-Modified: Wed, 10 Jan 2024 00:00:00 GMT
~~~

Client có thể gửi:

~~~http
GET /articles/42 HTTP/1.1
Host: example.test
If-Modified-Since: Wed, 10 Jan 2024 00:00:00 GMT
~~~

Nếu selected representation **không mới hơn** mốc client đưa ra và request phù hợp, server có thể trả `304 Not Modified`. Nếu đã đổi sau mốc đó, trả `200 OK` với body mới.

### 8.1. Tại sao Last-Modified kém chính xác hơn ETag?

HTTP-date thường có **độ phân giải giây**. Một tài nguyên được cập nhật **hai lần trong cùng một giây** có thể vẫn mang cùng `Last-Modified` nếu server làm tròn thời gian, khiến validator dựa ngày không phân biệt rõ hai phiên bản. Clock skew/clock correction giữa nhiều node cũng làm kết quả phức tạp.

Ví dụ:

~~~text
10:00:00.100 -> content A
10:00:00.700 -> content B

Last-Modified của cả hai có thể là:
Wed, 10 Jan 2024 10:00:00 GMT

=> If-Modified-Since có thể thiếu độ chính xác để phát hiện B.
=> ETag "v1" -> "v2" sẽ rõ hơn nếu server cập nhật tag đúng.
~~~

Do đó dùng **ETag** khi có thể. `Last-Modified` vẫn hữu ích làm validator dự phòng hoặc cho tài nguyên có metadata sửa đổi ổn định, nhưng không dùng nó thay mọi chiến lược concurrency control.

### 8.2. Last-Modified có thể không có hoặc không chính xác

Một asset được tạo động mà không có thời điểm sửa đáng tin cậy có thể **không nên phát Last-Modified giả**. Nếu server tự gán `Last-Modified = current time` cho mỗi response, client sẽ liên tục thấy một thời điểm mới và khó revalidate hiệu quả. Ngược lại, nếu nguồn thay đổi mà timestamp không được cập nhật, `304` có thể sai.

Đối với nhiều bản cache theo encoding/language, timestamp có thể cùng nhau thay đổi, còn ETag cần xem xét selected representation riêng. Không tự dùng `Date` của response làm `Last-Modified`.

### 8.3. Xử lý If-Modified-Since đúng ý nghĩa

Với GET/HEAD, origin nên xét `If-Modified-Since` **khi không có If-None-Match** thích hợp. Một request có ngày lỗi hoặc không hợp lệ cần xử lý theo HTTP semantics, thường **bỏ qua điều kiện không hợp lệ**, không crash parser. Date từ tương lai, độ chính xác thời gian và proxy caches là những edge cases cần tuân theo RFC và kiểm thử thực tế.

Một server có thể vẫn trả `200` trong những tình huống điều kiện không áp dụng; client phải xử lý cả `200` và `304`, không được coi `If-Modified-Since` như lệnh chắc chắn sẽ nhận 304.

## 9. Yêu cầu có điều kiện: If-None-Match, If-Modified-Since, If-Match

### 9.1. Revalidation cho GET / HEAD

Khi cache có ETag:

~~~http
GET /articles/42 HTTP/1.1
If-None-Match: "article-42-v7"
~~~

Origin xét selected representation hiện tại. Nếu match theo **weak comparison**, response phù hợp cho GET/HEAD là **`304 Not Modified`**; nếu không match, response thông thường là **`200 OK`** kèm body mới.

Khi cache chỉ có Last-Modified:

~~~http
GET /articles/42 HTTP/1.1
If-Modified-Since: Wed, 10 Jan 2024 00:00:00 GMT
~~~

Nếu representation chưa đổi so với mốc được chấp nhận, origin có thể trả 304; nếu đã đổi, 200.

### 9.2. Cùng có ETag và Last-Modified: ưu tiên If-None-Match

Client/caches có thể gửi cả hai:

~~~http
GET /articles/42 HTTP/1.1
If-None-Match: "old-etag"
If-Modified-Since: Wed, 10 Jan 2024 00:00:00 GMT
~~~

**Theo thứ tự xử lý preconditions của HTTP, If-None-Match được ưu tiên so với If-Modified-Since.** Origin không được chỉ thấy ngày “chưa đổi” rồi trả 304 khi ETag mới **không khớp** ETag client gửi. Nếu `If-None-Match` không match, server xử lý request và trả bản mới theo điều kiện khác liên quan; `If-Modified-Since` không được dùng để phủ nhận kết quả của ETag.

Ví dụ:

~~~text
Origin ETag:              "v2"
Client If-None-Match:     "v1"       -> không match
Client If-Modified-Since: thời điểm không đổi/trùng do độ phân giải
GET kết quả:              200 + representation mới
                         không phải 304 chỉ vì timestamp giống nhau.
~~~

Đây là lý do dùng hai validator **không gây mâu thuẫn**: ETag có độ chính xác phiên bản tốt hơn, còn ngày là validator bổ trợ khi client không có ETag.

### 9.3. Preconditions cho thay đổi dữ liệu: If-Match

Một client đọc tài nguyên có ETag `"v7"`, sau đó muốn cập nhật nhưng sợ client khác đã sửa. Nó gửi:

~~~http
PUT /articles/42 HTTP/1.1
Content-Type: application/json
If-Match: "v7"

{"title":"Updated"}
~~~

Server chỉ cho phép cập nhật khi **strong comparison** của current representation ETag phù hợp với `If-Match`. Nếu resource đã đổi thành `"v8"` thì trả **`412 Precondition Failed`**, tránh ghi đè phiên bản của người khác.

Đó là **optimistic concurrency control**. Cần thực thi kiểm tra validator và thay đổi state **một cách atomic** tại tầng lưu trữ; nếu kiểm tra ETag rồi cập nhật tách rời mà có race, bạn vẫn có thể gặp lost update.

### 9.4. If-Unmodified-Since và If-None-Match: *

Khi không có ETag, một số hệ thống hỗ trợ:

~~~http
PUT /articles/42 HTTP/1.1
If-Unmodified-Since: Wed, 10 Jan 2024 00:00:00 GMT
~~~

Nếu representation đã được sửa sau mốc ngày, điều kiện fail và có thể trả `412`. Nhưng validator bằng ngày có giới hạn **độ chính xác giây**, nên đối với cập nhật cạnh tranh mạnh, **If-Match + strong ETag** thường thích hợp hơn.

Một lối thiết kế **create-if-absent**:

~~~http
PUT /objects/new-key HTTP/1.1
If-None-Match: *
~~~

Nghĩa là tạo nội dung **chỉ khi chưa có current representation** theo semantics điều kiện. Nếu tài nguyên đã tồn tại, với phương thức ghi có thể trả `412` thay vì ghi đè; backend phải thực thi điều kiện này atomically.

### 9.5. Nếu có nhiều precondition cùng lúc?

HTTP định nghĩa **thứ tự đánh giá** các precondition (ví dụ `If-Match`, `If-Unmodified-Since`, `If-None-Match`, `If-Modified-Since` và `If-Range` theo trường hợp). Không được so sánh tất cả bằng một phép OR/AND tự chế vì sẽ sinh kết quả 200/304/412 sai. Trong production, hãy áp dụng đầy đủ RFC 9110 **Section 13: Conditional Requests**, hoặc dùng framework HTTP đã thực thi đúng semantics.

Đối với server chỉ xử lý GET đơn giản, ít nhất cần tuân thủ **If-None-Match ưu tiên hơn If-Modified-Since** và phân biệt `304` với `200`.

## 10. Ba mã kết quả quan trọng: 200, 304 và 412

| Status | Khi nào dùng | Có representation body không? |
| --- | --- | --- |
| `200 OK` | GET không có điều kiện, điều kiện không match validator, hoặc cần gửi bản mới | **Có**, trừ tình huống đặc thù như HEAD tương đương |
| `304 Not Modified` | Conditional GET/HEAD đã chọn representation và điều kiện cho phép không gửi lại nội dung | **Không có message content** |
| `412 Precondition Failed` | Điều kiện yêu cầu (ví dụ `If-Match` của PUT) không thỏa | Có thể có error representation, nhưng **không áp dụng cập nhật** |

`304` **không phải** `204 No Content`. `204` mô tả một phản hồi thành công không mang body trong một kiểu tương tác khác. `304` nói rằng **client/caches có thể tham chiếu representation đã lưu** theo validator và metadata; một client chưa có body lưu trước đó không thể tái dựng tài liệu chỉ từ 304.

### 10.1. Các header của 304

Một `304` nên mang các metadata cần để cập nhật cached response, đặc biệt những field mà origin sẽ gửi trong `200` tương ứng, chẳng hạn:

~~~http
HTTP/1.1 304 Not Modified
Date: Wed, 10 Jan 2024 00:10:00 GMT
ETag: "v7"
Cache-Control: public, max-age=300
Vary: Accept-Encoding
Last-Modified: Wed, 10 Jan 2024 00:00:00 GMT
~~~

**Không gửi representation body cho 304**, kể cả JSON `{}` hay text “Not Modified”. Trình duyệt hoặc cache kết hợp metadata 304 với bản đã lưu, rồi quyết định cấp representation nào cho ứng dụng. Code Java demo ở phần 12 dùng `sendResponseHeaders(304, -1)` để không tạo response body.

Không coi mọi header của bản `200` cũ còn mãi không đổi: phản hồi `304` có thể cập nhật `Cache-Control` hoặc metadata tương ứng. Việc cache cập nhật stored response phải tuân theo quy tắc RFC 9111; không chỉ tự cộng TTL mà bỏ qua những header mới.

### 10.2. Nếu client không có bản cache?

Một client tự gửi `If-None-Match` nhưng đã làm mất phần body trước đó có thể vẫn nhận 304. Khi ấy nó **không có representation để tái sử dụng**. Cần tải mới bằng GET không điều kiện hoặc xây dựng lại cache state; không diễn giải 304 như một payload rỗng hợp lệ.

## 11. Vary và cache key: cùng URL nhưng không cùng representation

Một server có thể gửi:

~~~http
Vary: Accept-Encoding, Accept-Language
~~~

Header này báo rằng việc chọn representation phụ thuộc vào các request headers được liệt kê. Shared/private cache phải chọn đúng stored response cho request có matching request header dimensions theo rules, không dùng bản tiếng Việt cho người yêu cầu tiếng Anh hoặc nhầm gzip với identity.

Ví dụ:

| Request | Representation | Lưu ý ETag |
| --- | --- | --- |
| `Accept-Language: vi`, `Accept-Encoding: gzip` | JSON tiếng Việt đã gzip | Strong ETag gắn bytes của variant này |
| `Accept-Language: en`, `Accept-Encoding: gzip` | JSON tiếng Anh đã gzip | Nên có strong ETag khác nếu bytes khác |
| `Accept-Language: vi`, `Accept-Encoding: identity` | JSON tiếng Việt chưa gzip | Strong ETag khác nếu bytes khác vì content-coding |

**Vary không thay authz.** Một cache key “bao gồm User-ID” không tự ngăn lộ dữ liệu nếu shared cache cấu hình sai. Với response cá nhân hóa, cân nhắc `private`/`no-store` và kiểm soát CDN policy.

`Vary: *` có nghĩa selection phụ thuộc các yếu tố không thể được cache reuse theo matching thông thường. Không dùng nó thay cho một chính sách cache được suy nghĩ kỹ.

## 12. Ví dụ Java 17+ hoàn chỉnh: HTTP server + HttpClient có ETag và Last-Modified

Ví dụ tự chạy trên **loopback IPv4 127.0.0.1**, không cần Internet. Server sử dụng module `jdk.httpserver` (`com.sun.net.httpserver.HttpServer`) trong JDK, và client dùng `java.net.http.HttpClient`. Bản demo có **một resource** với state bất biến chứa body, ETag và Last-Modified. Client gửi request không điều kiện và ba request có điều kiện, sau đó server đổi resource.

**Quy tắc demo:**

- Chỉ hỗ trợ **GET**, trả `405` cho phương thức khác.
- Khi có `If-None-Match`, demo **chỉ nhận một strong ETag chính xác**, so khớp string; không hỗ trợ danh sách, `W/` hay wildcard. Đây là **giản lược có chủ đích**, không phải implementation đầy đủ theo RFC 9110.
- Nếu không có `If-None-Match`, xét `If-Modified-Since` theo IMF-fixdate và thời điểm sửa của resource.
- Nếu validator cho biết resource chưa đổi, trả `304` **không có body**.
- Nếu đã đổi/không match, trả `200` kèm body, `Cache-Control`, `ETag` và `Last-Modified`.
- `Cache-Control: private, max-age=0, must-revalidate` dùng để nói cache có thể lưu riêng nhưng thường cần xác minh khi tái sử dụng; client demo **tự tạo conditional requests**.

Lưu mã sau vào file **HttpCacheDemo.java**:

~~~java
import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.concurrent.atomic.AtomicReference;

public class HttpCacheDemo {
    record Version(String body, String etag, Instant lastModified) {}

    static void serve(HttpExchange exchange,
                      AtomicReference<Version> state) throws IOException {
        try (exchange) {
            Version version = state.get();

            Headers headers = exchange.getResponseHeaders();
            String modified = DateTimeFormatter.RFC_1123_DATE_TIME.format(
                    version.lastModified().atZone(ZoneOffset.UTC));

            headers.set("Cache-Control",
                    "private, max-age=0, must-revalidate");
            headers.set("ETag", version.etag());
            headers.set("Last-Modified", modified);

            if (!"GET".equals(exchange.getRequestMethod())) {
                headers.set("Allow", "GET");
                exchange.sendResponseHeaders(405, -1);
                return;
            }

            String ifNoneMatch = exchange.getRequestHeaders()
                    .getFirst("If-None-Match");
            boolean notModified = false;

            if (ifNoneMatch != null) {
                // CHỈ demo: một strong tag giống hệt.
                // Production cần parse danh sách, W/ và *.
                notModified = ifNoneMatch.equals(version.etag());
            } else {
                String ifModifiedSince = exchange.getRequestHeaders()
                        .getFirst("If-Modified-Since");

                if (ifModifiedSince != null) {
                    try {
                        Instant since = ZonedDateTime.parse(
                                ifModifiedSince,
                                DateTimeFormatter.RFC_1123_DATE_TIME)
                                .toInstant();
                        notModified =
                                !version.lastModified().isAfter(since);
                    } catch (DateTimeParseException ignored) {
                        // Demo bỏ qua HTTP-date sai.
                    }
                }
            }

            if (notModified) {
                // 304 không có representation body.
                exchange.sendResponseHeaders(304, -1);
                return;
            }

            byte[] bytes =
                    version.body().getBytes(StandardCharsets.UTF_8);
            headers.set("Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, bytes.length);

            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    static HttpResponse<String> get(
            HttpClient client, URI uri,
            String etag, String modified)
            throws IOException, InterruptedException {

        HttpRequest.Builder req = HttpRequest.newBuilder(uri).GET();
        if (etag != null) {
            req.header("If-None-Match", etag);
        }
        if (modified != null) {
            req.header("If-Modified-Since", modified);
        }
        return client.send(req.build(),
                HttpResponse.BodyHandlers.ofString());
    }

    public static void main(String[] args) throws Exception {
        AtomicReference<Version> state = new AtomicReference<>(
                new Version("version one", "\"v1\"",
                        Instant.parse("2024-01-10T00:00:00Z")));

        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/resource",
                exchange -> serve(exchange, state));
        server.start();

        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/resource");
            HttpClient client = HttpClient.newHttpClient();

            HttpResponse<String> first =
                    get(client, uri, null, null);
            String etag = first.headers()
                    .firstValue("ETag").orElseThrow();
            String lastModified = first.headers()
                    .firstValue("Last-Modified").orElseThrow();

            System.out.println(
                    "First: " + first.statusCode()
                    + " " + first.body());

            System.out.println(
                    "If-None-Match: "
                    + get(client, uri, etag, null).statusCode());

            System.out.println(
                    "If-Modified-Since: "
                    + get(client, uri, null, lastModified)
                            .statusCode());

            // ETag không match => KHÔNG lấy timestamp để trả 304.
            System.out.println(
                    "Stale ETag overrides date: "
                    + get(client, uri, "\"stale\"", lastModified)
                            .statusCode());

            state.set(new Version("version two", "\"v2\"",
                    Instant.parse("2024-01-10T00:00:10Z")));

            HttpResponse<String> changed =
                    get(client, uri, etag, null);

            System.out.println(
                    "Changed: " + changed.statusCode()
                    + " " + changed.body());

            System.out.println(
                    "New ETag: " + get(client, uri,
                            changed.headers().firstValue("ETag")
                                    .orElseThrow(), null)
                            .statusCode());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 HttpCacheDemo.java
java HttpCacheDemo
~~~

Đầu ra kỳ vọng đã kiểm tra trên JDK có `jdk.httpserver`:

~~~text
First: 200 version one
If-None-Match: 304
If-Modified-Since: 304
Stale ETag overrides date: 200
Changed: 200 version two
New ETag: 304
~~~

### 12.1. Giải thích vì sao các kết quả đúng

1. Request đầu **không có validator**, origin trả `200` với body `version one`, ETag `"v1"` và Last-Modified là HTTP-date. Java client lưu chúng trong biến cục bộ để thử điều kiện.
2. Request thứ hai gửi `If-None-Match: "v1"`; tag khớp, origin trả **304**, không phát lại body.
3. Request thứ ba chỉ gửi `If-Modified-Since` bằng đúng thời điểm Last-Modified, origin trả **304**.
4. Request thứ tư gửi cả `If-None-Match: "stale"` và ngày vẫn phù hợp; do **If-None-Match có ưu tiên**, origin trả **200**, không trả 304 chỉ vì timestamp.
5. Server cập nhật representation thành `version two`, ETag `"v2"` và timestamp mới. Request mang ETag cũ `"v1"` nhận **200** và body mới.
6. Request cuối gửi ETag `"v2"` nên nhận **304**.

### 12.2. Các giới hạn chủ đích của demo

- Demo không triển khai **full HTTP cache**. `HttpClient` ở đây chỉ gửi request; nó **không tự quản lý stored response body, Age, TTL, Vary hoặc cache metadata**. Các conditional headers được lập trình viên gắn thủ công.
- Chỉ có một strong ETag đơn lẻ. Production cần **weak comparison cho If-None-Match**, danh sách entity tags, `*`, các status tương ứng, kiểm soát `If-Match`/`If-Range` nếu hỗ trợ và thứ tự preconditions của RFC 9110.
- Demo chỉ xử lý GET; production nên triển khai **HEAD**, range requests nếu có, và các phương thức write theo mô hình giao thức đầy đủ.
- Date parser đơn giản dùng `DateTimeFormatter.RFC_1123_DATE_TIME` và bỏ qua malformed date. HTTP thực có thêm các yêu cầu xử lý legacy date formats/clock behavior, do framework HTTP chuẩn nên đảm nhiệm.
- Dữ liệu state cố định/`AtomicReference` chỉ minh họa đổi phiên bản. Backend production cần version/ETag nhất quán với transaction, cập nhật atomic và phân tách variant theo `Vary`/encoding.
- Demo không xử lý `If-Modified-Since` từ tương lai, độ chính xác nhỏ hơn giây, caching qua CDN hay structured error responses.
- Đây là HTTP server **không TLS** trên loopback chỉ để học semantics. Với deployment thật dùng HTTPS, xác thực, kiểm tra input, giới hạn tài nguyên và framework phù hợp.

**Điểm quan trọng:** một ví dụ ngắn có thể dạy chính xác **cách dùng headers và status**, nhưng không thể thay thế đầy đủ HTTP conditional request implementation đã qua kiểm thử RFC.

## 13. Kiểm thử bằng curl và đọc response headers

Với một endpoint server thực tế có ETag:

~~~bash
curl -i https://example.test/articles/42
~~~

Giả sử nhận:

~~~http
HTTP/1.1 200 OK
Cache-Control: private, max-age=0, must-revalidate
ETag: "v7"
Last-Modified: Wed, 10 Jan 2024 00:00:00 GMT
Content-Type: application/json

{"id":42}
~~~

Kiểm tra If-None-Match:

~~~bash
curl -i -H 'If-None-Match: "v7"' https://example.test/articles/42
~~~

Nếu không đổi, kỳ vọng **304 không có body**. Kiểm tra khi ETag cũ:

~~~bash
curl -i -H 'If-None-Match: "old"' https://example.test/articles/42
~~~

Kỳ vọng thông thường **200** với bản mới (trừ các điều kiện/trạng thái khác).

Kiểm tra Last-Modified:

~~~bash
curl -i -H 'If-Modified-Since: Wed, 10 Jan 2024 00:00:00 GMT' \
  https://example.test/articles/42
~~~

Ví dụ `example.test` và các response là **minh họa**, không phải server đang chạy. Cú pháp single quotes áp dụng tốt với shell kiểu POSIX; trong Windows PowerShell, quy tắc quoting khác nhau theo phiên bản, cần điều chỉnh theo shell dùng thực tế.

### 13.1. Cách đọc log network trong browser

Với DevTools Network, quan sát:

- Status `200` hay `304`; một số browser có thể hiển thị response `from disk cache`/`from memory cache`, nghĩa là có thể **không gọi origin** trong lượt đó.
- **Request headers**: có `If-None-Match` hoặc `If-Modified-Since` không?
- **Response headers**: có `Cache-Control`, `ETag`, `Last-Modified`, `Vary`, `Age`?
- Cache nào trả response: browser, service worker, reverse proxy hay CDN?
- DevTools “Disable cache” và reload có thể thay đổi thử nghiệm; đừng dùng một kết quả để khẳng định tất cả client như nhau.

Dùng `curl -i` để thấy response headers; cần kiểm tra chuỗi CDN có thể dùng verbose/tracing và log tại origin để phân biệt **fresh hit, revalidation hit, full miss**. Không suy ra 304 “từ origin” nếu chính intermediary là thành phần trả response trong điều kiện được cho phép.

## 14. Thiết kế policy cho những loại tài nguyên khác nhau

| Loại tài nguyên | Chính sách thường đáng cân nhắc | Lý do |
| --- | --- | --- |
| JS/CSS có filename chứa content hash | `public, max-age=31536000, immutable` | URL mới khi bytes mới; tránh revalidation thường xuyên |
| HTML entry point cập nhật thường xuyên | `no-cache` + ETag | Có thể giữ body nhưng xác minh trước khi reuse |
| JSON public ít đổi | `public, max-age=60` + ETag | Fresh ngắn và 304 rẻ khi stale |
| Hồ sơ cá nhân được phép cache cục bộ | `private, no-cache` + ETag | Tránh shared-cache, private cache revalidate |
| Dữ liệu cực nhạy cảm | `private, no-store` (cùng kiểm soát bảo mật khác) | Giảm lưu response ở caches |
| Dashboard có SLA freshness chặt | TTL nhỏ, `must-revalidate`/điều kiện phù hợp | Tránh phục vụ stale vượt chính sách |
| Resource dùng cho concurrent PUT | Strong ETag + `If-Match` | Tránh lost update |
| File lớn có Range downloads | Strong validators và `If-Range` theo RFC | Không trộn byte từ các phiên bản khác nhau |

Đây là **định hướng**, không phải cấu hình an toàn mặc định cho mọi ứng dụng. Cần cân nhắc: dữ liệu có được chia sẻ không, tốc độ thay đổi, bảo mật, CDN behavior, thay đổi deployment, khả năng purge và mức stale được phép.

## 15. Những lỗi thực tế thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `no-cache` như nghĩa “không được lưu” | Hiểu nhầm browser vẫn giữ body | Dùng `no-store` khi thực sự cấm lưu |
| `max-age=0` rồi nghĩ “không có cache” | Body vẫn có thể lưu/revalidate | Phân biệt freshness và storage |
| Chỉ đặt `ETag` nhưng không có policy | TTL có thể dựa heuristic/metadata khác | Đặt Cache-Control tường minh |
| Trả `304` có JSON/body | Sai semantics 304 | Không gửi representation body |
| Trả `304` dù ETag đã đổi nhưng ngày chưa đổi | Client dùng bản cũ sai | Ưu tiên If-None-Match, validator chính xác |
| So sánh If-None-Match bằng strong comparison | Weak ETag revalidation bị xử lý sai | Dùng weak comparison theo RFC |
| Dùng weak ETag cho If-Match | Điều kiện strong không thể thỏa như mong muốn | Dùng strong ETag cho lost update |
| Gán ETag từ timestamp giây duy nhất | Hai bản đổi trong cùng giây trùng validator | Dùng version/hash/transaction ID ổn định |
| Content-Encoding thay đổi nhưng giữ cùng strong ETag | Range và variant có thể sai | Dùng ETag mạnh phân biệt bytes/variant |
| Không có `Vary: Accept-Encoding` | Cache có thể trả sai encoding | Khai báo đúng request selection headers |
| Coi `Vary: Cookie` đủ bảo vệ dữ liệu private | Có thể lộ thông tin từ shared cache | Chính sách private/no-store + authz |
| Trả `Last-Modified=Date` mỗi lần GET | Validator thời gian luôn đổi | Dùng thời gian sửa thực tế hoặc bỏ |
| Thiếu giới hạn thời gian cache nội dung công khai | Stale lâu không mong muốn hoặc revalidation nhiều | Đặt TTL theo mục tiêu |
| `immutable` nhưng vẫn ghi đè cùng URL | Client giữ nội dung cũ rất lâu | Dùng URL versioned/hash mới |
| Gửi If-None-Match mà chưa giữ cached body | 304 không chứa nội dung để hiển thị | Giữ body hoặc GET vô điều kiện |
| Nghĩ Java `HttpClient` tự cache như browser | Code có thể tải lại mỗi lần | Tự quản lý cache hoặc dùng thư viện caching phù hợp |
| Không áp dụng `If-Match` atomically | Race gây lost update | Kiểm tra version và update trong transaction |
| Không kiểm thử qua CDN/proxy | Header và Age bị biến đổi trên đường đi | Đo tại từng layer, cấu hình cache keys đúng |

## 16. Kịch bản vận hành: sai 304 và lỗi người dùng thấy trang cũ

Một hệ thống có nhiều origin nodes A và B sau load balancer. Node A phát `ETag: "v10"`, Node B có bản content mới nhưng vẫn phát `"v10"` vì tag được hard-code theo deployment hoặc cache state riêng.

Client có stored content A, sau đó request đến B với `If-None-Match: "v10"`. Nếu B trả `304` dù bytes đã đổi, client tiếp tục dùng body A. **Lỗi ở cách sinh validator**, không phải “HTTP cache không cập nhật”.

Cách sửa:

1. ETag phải phản ánh **selected representation version** một cách nhất quán trên tất cả nodes (ví dụ từ content revision hoặc hash đúng phạm vi).
2. Dữ liệu và validator cần được xuất bản/đổi theo quy tắc atomic; không thay body trước rồi vài giây sau mới đổi ETag.
3. Nếu có nhiều variants/encodings, gắn đúng Vary và ETag cho từng variant.
4. Kiểm tra 200/304 tại origin và qua CDN, quan sát `Date`, `Age`, `ETag`, `Cache-Control` và `Vary`.
5. Có quy trình purge/versioned URL khi cần loại bỏ object stale trước TTL, nhưng purge không thay thế validator đúng trong tương lai.

### 16.1. Khi nào revalidation không giúp?

Nếu server không cung cấp validator, cache có thể phải tải lại body khi stale. Nếu cache bị `no-store`, không có bản đã lưu phù hợp để dùng cùng 304. Nếu validator không đổi dù representation thay đổi, `304` còn nguy hiểm hơn re-download vì che giấu nội dung mới.

Đừng tối ưu băng thông bằng ETag nếu cách tính tag không đáng tin. **Correctness của validator quan trọng hơn số byte tiết kiệm được.**

## 17. Bài tập tự kiểm tra

### Bài A — no-cache và no-store

Resource A trả `Cache-Control: no-cache`, resource B trả `Cache-Control: no-store`. Sau khi tải, browser có thể giữ body của A không?

**Đáp án:** có thể giữ A theo policy, nhưng phải validate trước khi reuse. Với B, cache không được cố ý lưu theo chỉ thị no-store. Cả hai **không đồng nghĩa**.

### Bài B — Freshness 600 giây, Age 500 giây

Cache nhận response `max-age=600` đã có `Age=500`. Nó có ngay 600 giây mới hay không?

**Đáp án:** không. Age là thời gian response đã “già” trước đó; cache phải tính current age theo RFC. Tối đa khoảng 100 giây freshness còn lại trong ví dụ đơn giản, trừ các thành phần thời gian/network và metadata khác.

### Bài C — If-None-Match và If-Modified-Since mâu thuẫn

Client gửi `If-None-Match: "v1"` và `If-Modified-Since` là một ngày bằng thời điểm current representation. Origin đang phát `ETag: "v2"`. Trả 304 hay 200?

**Đáp án:** với GET thông thường, **200** vì If-None-Match được ưu tiên, không khớp validator hiện tại. Server không được chỉ nhìn ngày để trả 304.

### Bài D — Strong vs weak

Current ETag là `"v2"`, client gửi `If-None-Match: W/"v2"`. Nó có match không? Nếu gửi `If-Match: W/"v2"` để PUT?

**Đáp án:** `If-None-Match` dùng weak comparison nên match theo opaque value; GET có thể nhận **304**. `If-Match` đòi strong comparison, weak tag không đủ để cho phép cập nhật, nên có thể trả **412**.

### Bài E — Dữ liệu thay hai lần trong cùng giây

`Last-Modified` bị làm tròn về cùng một giây sau hai lần cập nhật; một client gửi If-Modified-Since cũ. Vấn đề gì xảy ra?

**Đáp án:** timestamp có thể không phân biệt hai phiên bản, dẫn tới validation sai. Dùng ETag được thay đổi đúng hoặc version transaction cho các tài nguyên cần chính xác.

### Bài F — Trang cá nhân trên CDN

Một endpoint hồ sơ người dùng được trả `Cache-Control: public, max-age=3600`. Có an toàn nếu người dùng khác truy cập cùng URL qua CDN?

**Đáp án:** không thể coi là an toàn. Nếu representation cá nhân hóa, shared caching có thể rò rỉ thông tin nếu cache key/policy/authz sai. Xem xét `private`/`no-store`, tách public/private content và kiểm tra authz.

### Bài G — 304 không có body

Ứng dụng Java tự gửi `If-None-Match: "v7"` nhưng không lưu response body trước đó. Server trả 304. App nên hiển thị dữ liệu gì?

**Đáp án:** không có body mới. App cần **cached representation hợp lệ** hoặc gửi GET vô điều kiện để tải lại. `304` là cơ chế revalidation chứ không phải response content rỗng.

### Bài H — PUT cạnh tranh

Hai client đều đọc ETag `"v1"`. Client A cập nhật thành `"v2"` bằng `If-Match: "v1"`; sau đó B gửi PUT cũng với `If-Match: "v1"`. Server xử lý?

**Đáp án:** A có thể thành công nếu compare-and-update atomic. B phải nhận **`412 Precondition Failed`** khi bản hiện tại không còn `"v1"`, tránh ghi đè A.

### Bài I — Asset có content hash nhưng đổi byte tại cùng URL

Server gửi `Cache-Control: public, max-age=31536000, immutable` cho `/assets/app.4a81d1.js`, nhưng deploy ghi đè bytes mới dưới **cùng URL**. Vì sao client vẫn nhận bản cũ?

**Đáp án:** client có thể tin asset còn fresh và không revalidate. Cách đúng là publish **URL mới theo hash** và cập nhật HTML tham chiếu, không ghi đè nội dung URL immutable.

### Bài J — Last-Modified và Date

Server trả `Date: Wed, 10 Jan 2024 12:00:00 GMT` và `Last-Modified: Tue, 09 Jan 2024 08:00:00 GMT`. Có lỗi không?

**Đáp án:** không. `Date` biểu thị thời điểm tạo response, `Last-Modified` biểu thị thời điểm nội dung được sửa. Chúng không cần giống nhau. Không dùng Date để thay thế tự động Last-Modified.

## 18. Checklist thiết kế và kiểm thử HTTP caching

- [ ] Đã xác định representation có công khai hay cá nhân hóa, có được shared cache không?
- [ ] `Cache-Control` phản ánh TTL, private/public, no-cache/no-store và yêu cầu revalidation đúng mục tiêu?
- [ ] Có hiểu `no-cache` vẫn **cho phép lưu**, còn `no-store` ngăn lưu?
- [ ] `max-age`/`s-maxage` được đặt hợp lý; xem xét `Date` và `Age` khi đánh giá freshness?
- [ ] ETag được tạo nhất quán với representation, đổi khi bytes/version đổi và phân biệt strong/weak?
- [ ] Có `Vary` đúng với content negotiation, đặc biệt `Accept-Encoding`?
- [ ] `Last-Modified` là thời điểm sửa thực tế, không lấy `Date` hiện tại làm thời điểm sửa?
- [ ] GET/HEAD conditional xử lý `If-None-Match` và `If-Modified-Since` với **ưu tiên đúng**?
- [ ] `304` không có body, trả metadata cần cho cache update?
- [ ] Nếu triển khai write preconditions, `If-Match` dùng strong comparison và compare-and-write **atomic**?
- [ ] Có handling đúng `If-None-Match: *`, entity-tag lists, W/ tags, date parsing nếu triển khai đầy đủ?
- [ ] Client khi nhận 304 có stored body phù hợp, không hiểu thành dữ liệu rỗng?
- [ ] Các lớp CDN/reverse proxy/browser không dùng cache key sai hoặc public policy cho dữ liệu private?
- [ ] Test lại sau cập nhật thực tế, hai lần sửa cùng giây, nhiều origin nodes, gzip/identity variants, clock skew, malformed validators?
- [ ] Dùng metrics quan sát hit/miss/revalidate, status 200/304/412, Age, network bytes, latency và stale incidents?

**Kết luận:** `Cache-Control` quyết định **khi nào/ở đâu một phản hồi có thể được lưu và tái sử dụng**; `ETag` và `Last-Modified` cung cấp **validators** để xác minh bản đã lưu; `If-None-Match`/`If-Modified-Since` làm xuất hiện **304 Not Modified** khi phù hợp, tiết kiệm truyền body; `If-Match`/`If-Unmodified-Since` giúp ngăn thao tác ghi đè phiên bản cũ. Muốn cache đúng, phải kết hợp **freshness, selected representation, Vary, validators, status codes và quyền truy cập**, không chỉ thêm một header rồi tin trình duyệt tự làm đúng mọi trường hợp.

## 19. Tài liệu chuẩn để đối chiếu

- **RFC 9110 — HTTP Semantics:** đặc biệt Section 8 về representation metadata, Section 13 về conditional requests, Section 15 về status codes. https://www.rfc-editor.org/rfc/rfc9110
- **RFC 9111 — HTTP Caching:** cacheability, freshness, Age, Cache-Control và validation. https://www.rfc-editor.org/rfc/rfc9111
- **RFC 5861 — HTTP Cache-Control Extensions for Stale Content:** `stale-while-revalidate`, `stale-if-error`. https://www.rfc-editor.org/rfc/rfc5861
- **Java 17 HttpClient:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **Java 17 HttpServer:** https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html

HTTP caching là giao thức có nhiều điều kiện; các ví dụ trên dạy nền tảng và những quy tắc quan trọng. Khi triển khai public CDN, proxy hoặc máy chủ HTTP hoàn chỉnh, hãy dùng framework phù hợp và kiểm tra trực tiếp các RFC/hành vi của cache trước khi tin vào các tối ưu hoặc thay đổi bảo mật.