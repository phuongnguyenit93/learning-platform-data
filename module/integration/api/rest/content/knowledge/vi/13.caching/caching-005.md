# Freshness, Age, Date, Expires và thời điểm cần xác thực lại

## 1. Bài toán: một phản hồi đã lưu còn dùng được đến bao giờ?

Một REST API có thể trả cùng một representation nhiều lần: thông tin sản phẩm, danh mục, cấu hình công khai, một bài viết hoặc danh sách được lọc. Nếu mọi request đều đi tới ứng dụng và database, hệ thống tốn tài nguyên không cần thiết. **HTTP caching** cho phép cache tại trình duyệt, proxy hoặc CDN lưu response và tái sử dụng khi phù hợp.

Nhưng câu hỏi khó không phải “lưu bao lâu?” mà là:

- Response này có **được phép lưu** không?
- Bản đã lưu còn **fresh** (đủ mới) tại thời điểm nhận request tiếp theo không?
- Thời gian đã trôi qua được đo bằng đồng hồ nào, có tính thời gian ở cache trung gian không?
- Khi bản lưu **stale** (hết độ mới), cache phải hỏi lại origin hay có ngoại lệ cho phép dùng bản cũ?
- Nếu origin trả **304 Not Modified**, cache làm gì với body và metadata đã lưu?
- Có nguy cơ dùng lại dữ liệu của người dùng hoặc tenant khác không?

Bài này thuộc chương **Bộ nhớ đệm** của module **INTEGRATION_API_REST**. Người học kết nối HTTP method/status, URI của resource, hợp đồng phản hồi, cache, ETag/Last-Modified, xác thực/phân quyền, OpenAPI và kiểm thử Java/Spring để thiết kế REST API có hiệu năng nhưng vẫn đúng dữ liệu.

**Mục tiêu học tập:** Sau bài, bạn có thể đọc và thiết kế các header **Cache-Control**, **Date**, **Age**, **Expires**; tính **freshness lifetime**, **current age** và thời điểm phải xác thực lại; phân biệt cache riêng/chung; xây dựng conditional GET bằng **If-None-Match** và **304**; kiểm thử hành vi ở client và CDN.

> Cơ sở ngữ nghĩa chính: **RFC 9110 – HTTP Semantics** và **RFC 9111 – HTTP Caching**. Các ví dụ dùng thời điểm cụ thể để minh họa cách tính, không khẳng định mọi CDN/framework có cấu hình giống nhau.

## 2. Ba vai trò và luồng sử dụng bản lưu

Một bản response có thể đi qua nhiều nơi:

~~~mermaid
sequenceDiagram
    participant C as Client / browser
    participant D as Shared cache / CDN
    participant O as Origin REST API
    C->>D: GET /api/v1/articles/42
    D->>O: Cache miss: GET
    O-->>D: 200 + Date + Cache-Control + ETag + body
    D-->>C: 200 + body (có thể kèm Age)
    Note over D: Lưu response nếu được phép
    C->>D: GET cùng URI
    Note over D: Kiểm tra freshness
    alt Fresh
        D-->>C: 200 từ cache, Age tăng
    else Stale, cần revalidation
        D->>O: GET + If-None-Match
        O-->>D: 304 Not Modified
        D-->>C: 200 với body đã lưu và metadata đã cập nhật
    end
~~~

**Origin** là server có thẩm quyền đối với tài nguyên. **Private cache** gắn với một người dùng hoặc client (thường là cache trình duyệt). **Shared cache** phục vụ nhiều người dùng (thường là CDN hoặc proxy).

Các thuật ngữ:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Cacheable** | Phản hồi có thể được lưu theo các quy tắc caching hiện hành. |
| **Fresh** | Bản lưu đủ mới để có thể được dùng mà không cần hỏi origin trong điều kiện thông thường. |
| **Stale** | Độ tuổi bản lưu đã đạt hoặc vượt giới hạn freshness; thông thường phải xác thực lại trước khi sử dụng, trừ các ngoại lệ được phép. |
| **Freshness lifetime** | Khoảng thời gian mà response được coi là đủ mới, tính theo ngữ nghĩa caching. |
| **Current age** | Độ tuổi hiện tại của response, có xét thời gian upstream và thời gian nằm trong cache. |
| **Revalidation** | Cache hỏi origin xem representation đã thay đổi chưa, thường qua request có điều kiện với ETag/Last-Modified. |
| **Cache hit / miss** | Hit: trả được từ bản lưu; miss: phải tìm hoặc lấy response từ tầng tiếp theo. Một cache hit cũng có thể phải xác thực lại với origin. |

**Fresh không đồng nghĩa chính xác tuyệt đối với dữ liệu hiện tại của database.** Nó có nghĩa cache được phép sử dụng theo chính sách mà origin đã công bố. Dữ liệu có thể thay đổi ở origin trong khi một bản cũ vẫn được phép dùng tới lúc hết freshness lifetime.

## 3. Các header quan trọng: Date, Age, Expires và Cache-Control

Ví dụ một phản hồi của resource công khai:

~~~http
HTTP/1.1 200 OK
Date: Wed, 18 Nov 2026 10:00:00 GMT
Cache-Control: public, max-age=120
Expires: Wed, 18 Nov 2026 10:05:00 GMT
ETag: "article-42-v7"
Content-Type: application/json

{
  "id": "42",
  "title": "Giới thiệu HTTP caching",
  "version": 7
}
~~~

| Header | Vai trò | Điều dễ nhầm |
| --- | --- | --- |
| **Date** | Thời điểm thông điệp được origin tạo theo đồng hồ của bên phát, biểu diễn bằng HTTP-date. | Không có nghĩa bản lưu còn fresh đến chính thời điểm Date. |
| **Age** | Ước lượng độ tuổi của response tính bằng **giây**, do cache dùng khi chuyển tiếp response; cần xét cả thời gian ở các cache trước đó. | Không phải TTL còn lại. |
| **Expires** | Thời điểm tuyệt đối mà sau đó response được coi là stale nếu quy tắc ưu tiên không có freshness directive phù hợp. | Không có quyền ưu tiên hơn **max-age** hoặc **s-maxage** khi các directive đó áp dụng. |
| **Cache-Control: max-age=N** | Thời gian freshness tối đa tính bằng giây đối với cache được áp dụng directive. | Không phải “lưu N giây tính từ lúc client nhận”. |
| **Cache-Control: s-maxage=N** | Freshness dành cho **shared cache**; ghi đè max-age/Expires đối với shared cache. | Không áp dụng cho private cache. |
| **ETag** | Validator nhận diện phiên bản representation cho kiểm tra điều kiện. | Không quy định TTL; chỉ hỗ trợ phát hiện thay đổi khi xác thực lại. |
| **Last-Modified** | Validator theo thời điểm chỉnh sửa, có thể dùng với If-Modified-Since. | Độ chính xác và độ tin cậy có thể thấp hơn ETag trong một số tình huống. |

Trong response ví dụ, **max-age=120** được ưu tiên hơn **Expires=10:05 GMT**. Vì vậy freshness lifetime theo cache-control là **120 giây**, không phải 300 giây, dù hai header cùng xuất hiện.

**HTTP-date** được biểu diễn theo GMT, như **Wed, 18 Nov 2026 10:00:00 GMT**. Trong hệ thống phân tán, đồng hồ origin và cache có thể lệch; không nên chỉ lấy đồng hồ client trừ trực tiếp Date rồi coi đó là phép đo đầy đủ.

## 4. Freshness lifetime: quy tắc ưu tiên

**Freshness lifetime** trả lời: “Độ tuổi tối đa cho phép của response trước khi nó trở thành stale là bao nhiêu?”

Theo cách chọn giá trị trong HTTP caching:

1. Với **shared cache**, nếu response có **s-maxage**, dùng giá trị đó.
2. Nếu không áp dụng s-maxage nhưng có **max-age**, dùng **max-age**.
3. Nếu không có các directive trên và có **Expires** hợp lệ, dùng hiệu số **Expires − Date** khi tính freshness lifetime.
4. Nếu không có freshness rõ ràng và đủ điều kiện theo HTTP, cache **có thể dùng heuristic freshness**; đây là lựa chọn chính sách của cache, không phải lời cam kết TTL của API.

~~~text
Shared cache:
    s-maxage  >  max-age  >  Expires  >  heuristic (nếu được phép)

Private cache:
                 max-age  >  Expires  >  heuristic (nếu được phép)
~~~

Dấu “>” thể hiện **độ ưu tiên chọn nguồn thông tin**, không phải giá trị số lớn hơn.

| Response directives | Private cache | Shared cache |
| --- | --- | --- |
| **max-age=120** | 120 giây | 120 giây |
| **public, max-age=120, s-maxage=60** | 120 giây | 60 giây |
| **max-age=120**, Expires cách Date 5 phút | 120 giây | 120 giây |
| Chỉ có Expires cách Date 5 phút | 300 giây, nếu các điều kiện caching khác thỏa | 300 giây, nếu các điều kiện caching khác thỏa |
| Không có explicit freshness | Có thể dùng heuristic nếu hợp lệ | Có thể dùng heuristic nếu hợp lệ |
| **no-store** | Không được lưu response theo directive | Không được lưu response theo directive |

**Cần phân biệt quyền lưu và độ mới:** Các bước trên xác định freshness lifetime **khi response được phép cache**. Một response có max-age dài nhưng bị chính sách no-store, private ở shared cache hoặc các quy tắc bảo mật khác ngăn lưu thì không thể dùng bảng ưu tiên để hợp thức hóa việc cache.

### Trường hợp chỉ dùng Expires

~~~http
Date: Wed, 18 Nov 2026 10:00:00 GMT
Expires: Wed, 18 Nov 2026 10:02:00 GMT
~~~

Nếu không có max-age/s-maxage áp dụng, freshness lifetime là **120 giây**. Nếu Expires bằng hoặc sớm hơn Date, lifetime không dương và bản phản hồi trở thành stale ngay trong điều kiện thông thường.

**Expires không phải bộ đếm khởi động lại ở mỗi proxy.** Response đi qua cache trung gian vẫn mang độ tuổi tích lũy; một cache phía sau không được tự cho 120 giây mới nếu response thực tế đã cũ 100 giây.

### Heuristic freshness không phải TTL mặc định tùy tiện của API

Một cache có thể suy đoán thời gian freshness trong một số trường hợp thiếu explicit freshness, chẳng hạn dựa trên Last-Modified và thời gian từ lúc sửa đến Date. Tuy nhiên, **không có công thức tỷ lệ phần trăm bắt buộc cho mọi cache**, và nhiều loại response không đủ điều kiện heuristic. Với REST API cần hành vi ổn định, **hãy đặt Cache-Control rõ ràng** thay vì dựa vào “trình duyệt/CDN chắc sẽ tự biết”.

## 5. Age: độ tuổi đã tích lũy của response

**Age** là một trường response, thường do một cache trung gian thêm hoặc cập nhật khi chuyển tiếp. Giá trị là **số nguyên không âm, tính bằng giây**, biểu diễn tuổi ước lượng của response.

Ví dụ:

~~~http
HTTP/1.1 200 OK
Date: Wed, 18 Nov 2026 09:59:30 GMT
Age: 30
Cache-Control: public, max-age=120
~~~

Nếu response tới một cache tại **10:00:00 GMT** với Age khoảng 30 giây, nó **không còn đủ 120 giây** từ thời điểm đó. Bỏ qua sai số truyền mạng, cache chỉ còn khoảng **90 giây freshness**, tức đến xấp xỉ **10:01:30 GMT**.

**Age không phải giá trị phải giảm dần.** Khi một cache phục vụ lại cùng response sau đó, Age được kỳ vọng tăng phản ánh tuổi lớn hơn. Nếu thấy **Age: 100**, điều đó thường nói rằng bản response đã có tuổi khoảng 100 giây, chứ không phải “còn 100 giây mới hết hạn”.

### Hai cấp cache

~~~text
Origin tạo response
   ↓ Sau 20 giây
CDN cấp 1 phục vụ với Age khoảng 20
   ↓ Sau thêm 35 giây
CDN cấp 2 phục vụ với Age khoảng 55
   ↓
Browser đánh giá độ mới dựa trên tuổi đã tích lũy
~~~

Cache ở phía sau phải cộng/hiệu chỉnh độ tuổi, không coi Age do upstream gửi là TTL mới bắt đầu. Khi nhiều tầng cache cùng hoạt động, **Date và Age** giúp tránh tình huống mỗi tầng tự cho phép thêm một chu kỳ freshness đầy đủ.

## 6. Cách tính current age theo HTTP Caching

RFC 9111 đưa ra một thuật toán để cache tính **current_age**, có xét Date, Age và thời gian truyền/ở lại cache. Dưới đây là mô hình diễn giải công thức.

Các biến:

- **request_time:** lúc cache gửi request lên tầng trên.
- **response_time:** lúc cache nhận response từ tầng trên.
- **date_value:** giá trị Date trong response, theo đồng hồ có thể quy đổi.
- **age_value:** số giây từ header Age, nếu không có thì dùng giá trị ban đầu theo thuật toán.
- **now:** thời điểm hiện tại khi cache chuẩn bị sử dụng bản lưu.

~~~text
apparent_age =
    max(0, response_time - date_value)

response_delay =
    response_time - request_time

corrected_age_value =
    age_value + response_delay

corrected_initial_age =
    max(apparent_age, corrected_age_value)

resident_time =
    now - response_time

current_age =
    corrected_initial_age + resident_time
~~~

Các phép trừ thời gian cùng đơn vị giây; hệ thống thực tế cần xử lý đồng hồ và giới hạn số theo quy tắc HTTP.

**Vì sao có cả apparent_age lẫn Age?** Cache không thể tin tuyệt đối đồng hồ Date của upstream, cũng không được bỏ qua độ tuổi do proxy khác báo. Thuật toán dùng giá trị phù hợp để tránh đánh giá response mới hơn tuổi thực tế trong những tình huống phổ biến.

**Vì sao cộng response_delay?** Request có thể mất thời gian đi về. Response đã già đi trong quãng chờ đó.

**Vì sao cộng resident_time?** Sau khi cache nhận và lưu bản phản hồi, thời gian nằm trong cache vẫn tiếp tục tăng tuổi của nó.

### Ví dụ tính số

Giả sử:

~~~text
request_time          = 10:00:00
response_time         = 10:00:02
date_value            = 09:59:52
Age header            = 8 giây
now                   = 10:00:32
Cache-Control         = max-age=120
~~~

Tính:

~~~text
apparent_age         = max(0, 10:00:02 - 09:59:52)
                     = 10 giây

response_delay       = 10:00:02 - 10:00:00
                     = 2 giây

corrected_age_value  = 8 + 2
                     = 10 giây

corrected_initial_age = max(10, 10)
                      = 10 giây

resident_time        = 10:00:32 - 10:00:02
                     = 30 giây

current_age          = 10 + 30
                     = 40 giây

freshness_lifetime   = 120 giây
remaining freshness  = khoảng 80 giây
~~~

Bản response **fresh** tại 10:00:32 trong ví dụ. Nếu các điều kiện khác cho phép cache dùng lại, không cần đến origin chỉ để kiểm tra độ mới.

**Quan trọng:** Trong bài toán thực tế, đừng tự viết một bộ HTTP cache parser chỉ để tính giá trị này cho mọi request nếu framework/proxy đáng tin đã tuân thủ RFC. Mục đích của công thức là giúp bạn **thiết kế, giải thích và kiểm thử** hiệu ứng của Date/Age/TTL.

## 7. Khi nào response chuyển từ fresh sang stale?

Quy tắc cốt lõi:

~~~text
response_is_fresh = (freshness_lifetime > current_age)
~~~

Khi **current_age đạt hoặc vượt freshness_lifetime**, response không còn fresh theo cách tính thông thường.

Giả sử một CDN nhận response lúc **10:00:00**:

~~~http
Date: Wed, 18 Nov 2026 09:59:30 GMT
Age: 30
Cache-Control: public, max-age=120
ETag: "article-42-v7"
~~~

Bỏ qua độ trễ truyền mạng bổ sung, bảng thời gian:

| Thời điểm kiểm tra | Current age xấp xỉ | Freshness còn lại | Phân loại |
| --- | ---: | ---: | --- |
| **10:00:00** | 30 giây | 90 giây | Fresh |
| **10:00:30** | 60 giây | 60 giây | Fresh |
| **10:01:00** | 90 giây | 30 giây | Fresh |
| **10:01:29** | 119 giây | 1 giây | Fresh |
| **10:01:30** | 120 giây | 0 giây | Stale |
| **10:02:00** | 150 giây | 0 giây | Stale |

Thời điểm **10:01:30** không nhất thiết là lúc có một request được gửi đi. Nó là mốc mà cache phải **đánh giá lại khả năng sử dụng bản lưu** khi có request mới. Cache không nhất thiết chủ động gọi origin ngay đúng phút/giây hết hạn.

### Freshness có thể thay đổi vì request của client

Một client có thể gửi request với Cache-Control để hạn chế độ tuổi được chấp nhận, ví dụ:

~~~http
GET /api/v1/articles/42 HTTP/1.1
Cache-Control: max-age=30
~~~

Client yêu cầu không dùng response có tuổi lớn hơn ngưỡng này theo ngữ nghĩa request. Dù origin từng công bố max-age=120, cache phải tính thêm yêu cầu của client. Ngoài ra có **min-fresh**, **max-stale** và **no-cache** trong request với những tác động khác nhau; khi triển khai nên dựa trên parser/cache tuân RFC, không chỉ kiểm tra một chuỗi header.

## 8. Phân biệt fresh, stale, validate và tải lại

Một flow thông thường của shared cache khi nhận GET:

~~~mermaid
flowchart TD
    A[GET tài nguyên] --> B{Cache có bản lưu hợp lệ và được phép dùng?}
    B -->|Không| M[Chuyển request tới origin]
    B -->|Có| C[Tính freshness lifetime và current age]
    C --> D{Fresh và không có directive buộc validate?}
    D -->|Có| H[Trả bản lưu ngay]
    D -->|Không| E{Có ngoại lệ hợp lệ cho phép dùng stale?}
    E -->|Có| S[Trả stale theo đúng giới hạn/chính sách]
    E -->|Không| V[Conditional GET / revalidation]
    V --> F{Origin trả gì?}
    F -->|304| U[Cập nhật metadata/cache entry, dùng body đã lưu]
    F -->|200| R[Thay bản lưu bằng representation mới nếu cacheable]
    F -->|Lỗi| X[Theo chính sách lỗi; không tự ý trả stale]
~~~

Không phải mọi response stale đều được phép dùng. Nếu có **must-revalidate** hay các ràng buộc khác, cache phải tôn trọng khi stale. Một số cơ chế như **stale-while-revalidate** và **stale-if-error** chỉ cho phép dùng stale trong phạm vi và điều kiện đã công bố; không phải giấy phép bỏ qua quyền riêng tư hoặc trả bản cũ vô hạn.

### Phân biệt các directive dễ nhầm

| Directive | Ý nghĩa thiết kế | Điều không nên suy ra |
| --- | --- | --- |
| **no-store** | Cache không được lưu request/response theo directive áp dụng. | Không phải chỉ “TTL bằng 0 nhưng vẫn lưu”. |
| **no-cache** | Cache có thể lưu, nhưng **không được dùng lại để đáp ứng request kế tiếp nếu chưa xác thực thành công với origin**. | Không đồng nghĩa không lưu trên đĩa. |
| **max-age=0** | Response trở nên stale ngay theo freshness lifetime 0. | Không tự xóa bản lưu; có thể xác thực lại. |
| **must-revalidate** | Khi đã stale, cache không được dùng lại trước khi xác thực lại thành công, theo quy tắc áp dụng. | Không buộc revalidation trong mọi request **khi response còn fresh**. |
| **proxy-revalidate** | Ràng buộc revalidation khi stale dành cho shared cache. | Không có tác dụng tương tự cho private cache. |
| **immutable** | Tín hiệu rằng representation sẽ không thay đổi trong thời gian fresh; hỗ trợ hạn chế revalidation không cần thiết khi được hỗ trợ. | Không thay thế versioning đúng hoặc cho phép stale vô hạn. |
| **stale-while-revalidate=N** | Cho phép dùng stale một khoảng giới hạn trong lúc revalidation chạy, khi đủ điều kiện. | Không bảo đảm mọi cache đều hỗ trợ; không dùng trái các ràng buộc áp dụng. |
| **stale-if-error=N** | Cho phép dùng stale có giới hạn khi gặp một số lỗi theo ngữ nghĩa extension, nếu đủ điều kiện. | Không nên biến mọi lỗi ứng dụng, dữ liệu sai hay 403 thành trả cache cũ. |

Ví dụ response riêng tư cần luôn kiểm tra phiên bản trước khi dùng:

~~~http
Cache-Control: private, no-cache
ETag: "account-42-v9"
~~~

Một private cache có thể lưu representation, nhưng phải revalidate trước khi dùng lại. Nếu dữ liệu rất nhạy cảm và không được lưu, dùng **Cache-Control: no-store** thay vì chỉ no-cache.

## 9. Xác thực lại bằng ETag và If-None-Match

Khi cached response đã stale và có ETag, cache có thể gửi GET có điều kiện:

~~~http
GET /api/v1/articles/42 HTTP/1.1
Host: api.example.com
If-None-Match: "article-42-v7"
~~~

Nếu representation hiện tại vẫn khớp validator, origin có thể trả:

~~~http
HTTP/1.1 304 Not Modified
Date: Wed, 18 Nov 2026 10:02:00 GMT
Cache-Control: public, max-age=120
ETag: "article-42-v7"
~~~

**304 không mang representation body**. Cache kết hợp metadata cập nhật từ 304 với representation đã lưu theo quy tắc HTTP caching, rồi có thể phục vụ body cũ cho client dưới dạng response phù hợp.

Nếu tài nguyên đã đổi, origin gửi representation mới:

~~~http
HTTP/1.1 200 OK
Date: Wed, 18 Nov 2026 10:02:00 GMT
Cache-Control: public, max-age=120
ETag: "article-42-v8"
Content-Type: application/json

{
  "id": "42",
  "title": "Giới thiệu HTTP caching – bản mới",
  "version": 8
}
~~~

Cache có thể thay bản lưu cũ nếu response mới được phép lưu và khóa cache/variant phù hợp.

### 304 làm gì với freshness?

Không nên hiểu “304 thì cộng thêm đúng 120 giây vào TTL cũ” như quy tắc tổng quát. Cache cập nhật metadata theo **RFC 9111**, sau đó tính lại freshness lifetime và current age từ các header đã cập nhật. Thời điểm Date, Age, Cache-Control, Expires và validator trên 304 đều ảnh hưởng đến trạng thái mới tùy các trường hiện diện.

Ví dụ 304 trả Date mới và max-age=120 giúp cache cập nhật độ mới từ thông tin origin vừa xác nhận; song thời gian truyền và Age vẫn phải được xét. Việc “reset Age về 0” không phải cách tính đúng trong mọi tình huống.

### Điều kiện không còn khớp

Nếu có **If-None-Match** và server đánh giá điều kiện không cho phép 304 (representation đã đổi), kết quả thường là **200 OK** có body mới. Nếu resource đã bị xóa, server có thể trả **404 Not Found** hoặc **410 Gone** theo hợp đồng và trạng thái. Không trả 304 chỉ vì client có gửi If-None-Match; điều kiện phải được kiểm tra với representation hiện tại.

## 10. Last-Modified và If-Modified-Since

Nếu API không dùng ETag nhưng biết thời điểm sửa đáng tin cậy, có thể dùng validator thời gian:

~~~http
HTTP/1.1 200 OK
Last-Modified: Wed, 18 Nov 2026 09:30:00 GMT
Cache-Control: public, max-age=60
~~~

Khi cần xác thực:

~~~http
GET /api/v1/articles/42 HTTP/1.1
If-Modified-Since: Wed, 18 Nov 2026 09:30:00 GMT
~~~

Nếu representation không thay đổi theo điều kiện hợp lệ, server có thể trả **304 Not Modified**. Tuy nhiên:

- Last-Modified thường ở độ phân giải giây, có thể không phân biệt nhiều lần cập nhật trong cùng giây.
- Thời điểm database và thời điểm biến đổi representation cần khớp; nếu body thay đổi do nội dung phụ nhưng timestamp không đổi, validator có thể báo sai.
- Khi client gửi **If-None-Match** hợp lệ cùng **If-Modified-Since**, server tuân thứ tự ưu tiên điều kiện HTTP; **If-None-Match được ưu tiên**, không để Last-Modified ghi đè kết quả đối chiếu ETag.
- **Last-Modified không phải Expires.** Một header cho biết khi representation đổi, header kia mô tả thời điểm hết freshness theo cache policy.

Khi representation phức tạp hoặc thay đổi thường xuyên, ETag được xây đúng theo phiên bản nội dung thường là validator thuận tiện. ETag không tự làm response fresh; nó chỉ giúp revalidation tiết kiệm truyền body.

## 11. Response công khai, private và bảo vệ dữ liệu cá nhân

Cache đúng tốc độ nhưng sai phạm vi người dùng có thể gây **rò rỉ dữ liệu**. Ví dụ /api/v1/orders trả danh sách riêng cho từng tenant; nếu CDN dùng chung key chỉ gồm URI, người dùng T2 có thể nhận response từng được tạo cho T1.

Một số hướng thiết kế:

| Dữ liệu | Header ví dụ | Ý nghĩa |
| --- | --- | --- |
| Danh mục công khai, ít thay đổi | **public, max-age=120, s-maxage=60** | Browser có thể dùng 120 giây; shared cache 60 giây nếu được phép và phù hợp |
| Hồ sơ cá nhân có thể lưu riêng nhưng phải validate | **private, no-cache** | Private cache được lưu nhưng phải revalidate khi dùng lại |
| Thông tin tài chính/token nhạy cảm | **no-store** | Không lưu response theo cơ chế caching |
| Tài nguyên bất biến theo hash/version trong URL | **public, max-age=31536000, immutable** | Chỉ phù hợp nếu URL mới được dùng khi nội dung thay đổi |
| API động chứa thông tin tenant | **private, no-store** | Tránh lưu và dùng lại tại shared cache/trình duyệt nếu chính sách yêu cầu |

**Authorization:** Shared cache có ràng buộc đặc biệt đối với response của request mang header Authorization; một số directive có thể cho phép shared cache sử dụng trong những trường hợp hợp lệ. Với API riêng tư, đừng dựa vào giả định “có Bearer token thì CDN chắc chắn không cache”; hãy đặt **private/no-store**, cấu hình shared cache phù hợp và kiểm thử thực tế.

**Vary** cho biết những trường request ảnh hưởng đến lựa chọn representation, ví dụ **Vary: Accept-Language**. Nhưng **Vary không phải cơ chế phân quyền**. Không nên coi **Vary: Authorization** là giải pháp duy nhất để ngăn rò dữ liệu cross-user. Thực hiện authz ở origin và đặt chính sách cache/key an toàn.

**no-store không xóa mọi bản sao ngoài phạm vi HTTP cache** (ví dụ log ứng dụng hoặc bản tải xuống do người dùng chủ động lưu). Bảo vệ dữ liệu cần kết hợp chính sách logging, quyền, lưu giữ, mã hóa và kiểm toán.

## 12. Vary và khóa cache: freshness đúng nhưng biến thể sai vẫn là lỗi

Hai request cùng URI có thể có representation khác nhau theo ngôn ngữ hoặc encoding:

~~~http
GET /api/v1/articles/42 HTTP/1.1
Accept-Language: vi
~~~

~~~http
GET /api/v1/articles/42 HTTP/1.1
Accept-Language: en
~~~

Nếu origin sinh nội dung theo ngôn ngữ, có thể trả:

~~~http
Vary: Accept-Language
Cache-Control: public, max-age=120
~~~

Cache phải tuân thủ Vary khi chọn stored response phù hợp. Việc **Age còn dưới 120** không cho phép trả bản tiếng Việt cho request tiếng Anh nếu biến thể không khớp.

Với query parameter:

~~~text
/products?category=BOOK&page=0
/products?category=BOOK&page=1
/products?category=TOY&page=0
~~~

Đây là những URI khác nhau về bộ lọc và trang. Cache key thường phải phân biệt chúng; nếu dùng cơ chế normalize/canonicalize query trong CDN, không được loại bỏ nhầm tham số ảnh hưởng đến representation.

**Kiểm chứng thực tế:** dùng hai người dùng/tenant, hai ngôn ngữ, hai page và hai giá trị filter; quan sát phản hồi khi cache hit. Phát hiện rò quyền và trả nhầm biến thể quan trọng hơn việc đạt tỉ lệ hit cao.

## 13. Ví dụ Java/Spring: cấu hình cache policy và conditional GET

Ví dụ dùng **Java 17+**, **Spring MVC** và một service trả article DTO có ID, version và thời điểm thay đổi. Code minh họa phần giao thức HTTP; project thực tế phải cấu hình authentication/authorization, dependency, exception handler và repository tương ứng.

### 13.1. Response có max-age và ETag

~~~java
public record ArticleView(
        UUID id,
        String title,
        String content,
        long version,
        Instant updatedAt
) {}

@RestController
@RequestMapping("/api/v1/articles")
public class ArticleController {
    private final ArticleService service;

    public ArticleController(ArticleService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public ResponseEntity<ArticleView> get(
            @PathVariable UUID id, WebRequest request) {

        ArticleView article = service.findPublicArticle(id)
                .orElseThrow(() ->
                    new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Article not found"));

        String etag = "\"article-" + article.id()
                + "-v" + article.version() + "\"";

        CacheControl policy =
                CacheControl.maxAge(Duration.ofSeconds(120))
                            .mustRevalidate();

        long lastModified = article.updatedAt().toEpochMilli();

        if (request.checkNotModified(etag, lastModified)) {
            return ResponseEntity.status(HttpStatus.NOT_MODIFIED)
                    .eTag(etag)
                    .lastModified(lastModified)
                    .cacheControl(policy)
                    .build();
        }

        return ResponseEntity.ok()
                .eTag(etag)
                .lastModified(lastModified)
                .cacheControl(policy)
                .body(article);
    }
}
~~~

Các lớp cần import gồm **ResponseEntity**, **CacheControl**, **HttpStatus**, **WebRequest**, **ResponseStatusException**, **Duration**, **Instant**, **UUID** và các annotation MVC; interface **ArticleService** do ứng dụng định nghĩa.

Điểm quan trọng:

1. **Cache-Control** được đặt tại origin. Với max-age=120, cache có thể dùng bản fresh trong giới hạn đã công bố.
2. **ETag** dựa trên **version của representation**. Nếu title/content thay đổi, version phải đổi; nếu logic sinh body thay đổi mà version không đổi, validator này không đáng tin.
3. **Last-Modified** cung cấp validator thời gian bổ sung. Khi sinh từ DB, phải bảo đảm updatedAt phản ánh thay đổi của representation.
4. **WebRequest.checkNotModified** hỗ trợ đánh giá điều kiện HTTP; không nên tự so chuỗi If-None-Match đơn lẻ mà bỏ qua danh sách giá trị, weak comparison hoặc thứ tự ưu tiên.
5. Khi điều kiện hợp lệ, **304 không có body**. Khi representation đã thay đổi, trả **200 với body**.
6. **Date và Age** thường liên quan đến hạ tầng HTTP server/cache trung gian; origin không nên tự đặt **Age: 0** như một thủ thuật “reset TTL” khi trả từng response.

**Hạn chế của ví dụ:** để quyết định 304, service vẫn phải lấy đủ dữ liệu/metadata để xác minh phiên bản. 304 tiết kiệm băng thông và công xử lý body ở client, nhưng không mặc nhiên loại bỏ toàn bộ truy vấn database tại origin. Một thiết kế tối ưu có thể kiểm tra version trước rồi chỉ tải payload đầy đủ khi cần.

### 13.2. Chính sách cho dữ liệu người dùng

Với endpoint tài chính hoặc đơn hàng riêng tư:

~~~java
@GetMapping("/me/orders")
public ResponseEntity<List<OrderView>> myOrders(
        Authentication authentication) {

    List<OrderView> result = service.findOrdersFor(authentication);

    return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(result);
}
~~~

**CacheControl.noStore()** làm rõ yêu cầu không lưu; phân quyền trong **findOrdersFor** vẫn là bắt buộc. Không thay kiểm tra tenant hoặc ownership bằng cách chỉ thêm no-store.

### 13.3. Quy tắc chính sách theo loại tài nguyên

Đừng áp **max-age=120** cho mọi GET chỉ vì Spring hỗ trợ dễ dàng. Có thể định nghĩa policy khác nhau:

~~~text
GET /catalog/categories         -> public, s-maxage phù hợp nếu công khai
GET /articles/{id}              -> public/max-age nếu dữ liệu công khai
GET /me/profile                 -> private, no-cache hoặc no-store
GET /payments/{id}              -> no-store
GET /product-images/{hash}.png  -> public, max-age dài + immutable
~~~

Các giá trị phải đến từ yêu cầu nghiệp vụ về chấp nhận dữ liệu trễ, bảo mật và chiến lược invalidation.

## 14. Kiểm thử HTTP với MockMvc

Kiểm thử nên xác nhận cả **Cache-Control/ETag** lẫn **200/304** và việc không phát body khi 304.

Ví dụ minh họa, với dữ liệu article có version 7:

~~~java
@Test
void articleSupportsConditionalGet() throws Exception {
    MvcResult first = mockMvc.perform(
            get("/api/v1/articles/{id}", articleId))
        .andExpect(status().isOk())
        .andExpect(header().exists("Cache-Control"))
        .andExpect(header().exists("ETag"))
        .andExpect(jsonPath("$.version").value(7))
        .andReturn();

    String etag = first.getResponse().getHeader("ETag");

    mockMvc.perform(
            get("/api/v1/articles/{id}", articleId)
                .header("If-None-Match", etag))
        .andExpect(status().isNotModified())
        .andExpect(content().string(""));
}
~~~

Đây là skeleton cần imports/fixture và cấu hình dự án. Khi endpoint có security, test phải cung cấp principal hợp lệ; không vô hiệu hóa bảo vệ chỉ để kiểm thử cache.

### Ma trận kiểm thử cần có

| Trường hợp | Kỳ vọng |
| --- | --- |
| GET tài nguyên công khai lần đầu | 200, Cache-Control, ETag, representation đúng |
| GET có If-None-Match trùng phiên bản | 304, không có body |
| GET có If-None-Match cũ sau thay đổi | 200, ETag mới, body mới |
| GET có If-Modified-Since phù hợp | 304 nếu điều kiện được đánh giá đúng |
| Cùng request có ETag và If-Modified-Since | Ưu tiên điều kiện theo ngữ nghĩa HTTP |
| Response **no-store** | Cache được kiểm thử không lưu/dùng lại |
| Response **private** tại CDN | Shared cache không lưu dùng chung |
| max-age=120 với Age=30 | Lifetime còn khoảng 90 giây ở thời điểm nhận nếu bỏ qua delay |
| max-age=120, current age 119 | Fresh trong điều kiện không có ràng buộc khác |
| max-age=120, current age 120 | Stale, phải xử lý revalidation/ngoại lệ hợp lệ |
| Expires > Date và không có max-age | Freshness bằng hiệu thời gian thích hợp |
| Expires khác max-age | Ưu tiên max-age |
| Có s-maxage và max-age | Shared cache dùng s-maxage, private dùng max-age |
| no-cache với ETag | Revalidate trước mỗi lần dùng lại |
| Hai ngôn ngữ có Vary | Không trả nhầm representation |
| Hai tenant hoặc user | Không trả dữ liệu của nhau qua cache |
| Lỗi origin lúc stale | Chỉ dùng stale khi policy cho phép, không dùng ngầm |

**MockMvc không phải một CDN thật.** Nó kiểm thử response header và conditional GET ở ứng dụng; việc cache có tuân **Age, Expires, Vary, s-maxage, stale** hay không phải kiểm thử tích hợp với proxy/cache thực tế hoặc cache giả lập tuân RFC.

## 15. OpenAPI ghi hợp đồng cache như thế nào?

OpenAPI mô tả API contract, nhưng không thay thế cấu hình CDN. Có thể mô tả các header cache và response 304:

~~~yaml
openapi: 3.1.0
info:
  title: Articles API
  version: 1.0.0
paths:
  /api/v1/articles/{id}:
    get:
      summary: Lấy bài viết công khai
      description: >
        Response có ETag và chính sách freshness.
        Client có thể gửi If-None-Match để xác thực lại khi cần.
        Khi ETag phù hợp, server trả 304 không có body.
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string, format: uuid }
        - in: header
          name: If-None-Match
          required: false
          schema: { type: string }
      responses:
        '200':
          description: Representation bài viết
          headers:
            Cache-Control:
              schema: { type: string }
              description: Ví dụ public, max-age=120
            ETag:
              schema: { type: string }
              description: Validator của representation
            Last-Modified:
              schema: { type: string }
              description: HTTP-date của thay đổi gần nhất nếu có
          content:
            application/json:
              schema:
                type: object
                required: [id, title, version]
                properties:
                  id: { type: string, format: uuid }
                  title: { type: string }
                  version: { type: integer }
        '304':
          description: Representation không thay đổi theo điều kiện; không có body
          headers:
            ETag:
              schema: { type: string }
            Cache-Control:
              schema: { type: string }
        '404':
          description: Không tìm thấy bài viết
~~~

Trong ví dụ, **Date** là metadata HTTP thông thường của hệ thống phát response; **Age** thường do cache trung gian tính và chèn/cập nhật. Vì vậy không nên bắt origin luôn trả một **Age** cố định trong OpenAPI chỉ để client “dễ tính TTL”.

Với dữ liệu yêu cầu xác thực, thêm security scheme và mô tả chính sách **private/no-store**; không dùng ví dụ public của article cho /me hoặc payment.

## 16. CDN, reverse proxy và kiểm tra hành vi thực tế

Triển khai production thường có một chuỗi:

~~~text
Browser / mobile client
       ↓
CDN hoặc shared reverse proxy
       ↓
API gateway / ingress
       ↓
Spring Boot origin
       ↓
Database / downstream services
~~~

Cách kiểm tra:

1. Gọi GET từ client ngoài CDN và ghi **Date, Cache-Control, Age, ETag, Vary** cùng thời gian phản hồi.
2. Gọi lại cùng URI/headers sau vài giây, quan sát header cache do CDN cung cấp (ví dụ chỉ báo hit/miss đặc thù nếu có), thời gian phản hồi và Age.
3. Đổi một filter, page, Accept-Language hoặc user/tenant; xác nhận cache **không trả nhầm biến thể**.
4. Cho response hết freshness (hoặc dùng môi trường thử có TTL ngắn), quan sát cache revalidate với origin.
5. Thay đổi representation/version, xác nhận origin trả **200 mới** thay vì 304 sai.
6. Giả lập lỗi origin trong staging và kiểm tra liệu stale có được phục vụ đúng chính sách hay không.
7. Đo số request thật sự đến origin: cache hit cao chưa đủ nếu revalidation bị kích hoạt quá thường xuyên.

Một CDN có thể có cấu hình **override TTL, cache-key policy hoặc bypass** khác với header origin. Nếu kết quả thực tế không giống mô hình, kiểm tra cấu hình cache trung gian và header response **trên đường đi**, không chỉ controller. Hợp đồng của API và cấu hình CDN phải được thiết kế thống nhất.

## 17. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nhầm Age là TTL còn lại | Dùng response lâu hơn mức được cho phép | Tính current age và so với freshness lifetime |
| Bắt đầu max-age lại từ lúc mỗi cache nhận | TTL kéo dài qua nhiều tầng | Tôn trọng Date/Age và thuật toán RFC 9111 |
| Coi Expires luôn có ưu tiên | Bỏ qua max-age/s-maxage | Dùng đúng thứ tự ưu tiên |
| Coi fresh là dữ liệu tuyệt đối mới | Hiển thị dữ liệu đã thay đổi ở origin | Thống nhất độ trễ chấp nhận được; chọn TTL/revalidation |
| Coi no-cache nghĩa là cấm lưu | Sai chính sách riêng tư và hành vi | Phân biệt no-cache với no-store |
| Coi max-age=0 nghĩa là xóa cache | Không dùng được conditional GET | Hiểu stale và revalidation |
| Coi 304 như 200 JSON rỗng | Client xóa nhầm dữ liệu đã lưu | 304 không có body; dùng representation đã cache |
| Reset Age=0 sau mọi 304 | Kéo dài freshness sai | Cập nhật metadata và tính lại theo RFC |
| Dùng Last-Modified như Expires | Không biết khi nào xác thực lại | Tách validator khỏi freshness policy |
| Cache /me hoặc /orders ở shared CDN | Rò dữ liệu giữa người dùng | Dùng private/no-store, authz, test tenant isolation |
| Bỏ qua Vary hoặc filter/page trong cache key | Trả sai ngôn ngữ/trang/kết quả | Dùng đúng biến thể và normalized cache key |
| Dựa vào ETag nhưng không đổi khi body đổi | Trả 304 sai | Bảo đảm validator gắn đúng representation |
| Không test stale ở nhiều tầng cache | Chạy đúng ở local nhưng sai production | Test CDN/proxy thật và quan sát Age |
| Dùng stale-if-error cho mọi lỗi | Có thể che lỗi quyền hoặc trạng thái không hợp lệ | Chỉ áp dụng ngoại lệ theo policy và HTTP semantics |

## 18. Bài thực hành: danh mục sản phẩm và thông tin đơn hàng

Một API thương mại điện tử có ba endpoint:

- **GET /api/v1/catalog/categories**: danh mục công khai, thay đổi vài lần mỗi ngày.
- **GET /api/v1/products/{id}**: chi tiết sản phẩm công khai, giá có thể cập nhật trong ngày.
- **GET /api/v1/me/orders**: danh sách đơn hàng riêng tư, chứa dữ liệu cá nhân.

Hạ tầng có CDN trước API Spring. Nghiệp vụ chấp nhận danh mục trễ tối đa **5 phút**, thông tin giá sản phẩm trễ tối đa **30 giây** ở shared cache; đơn hàng cá nhân không được lưu tại shared cache. Các mục tiêu này là **đề bài minh họa**.

### Nhiệm vụ A — Thiết kế header

Chọn Cache-Control, ETag, Last-Modified/Expires nếu phù hợp cho từng endpoint. Giải thích:

1. Vì sao danh mục có thể dùng shared cache.
2. Vì sao **s-maxage** có thể khác **max-age** để điều khiển CDN và browser.
3. Vì sao /me/orders cần private/no-store và phân quyền thay vì chỉ dùng Vary.
4. Nếu response có Date và Expires cùng max-age, header nào quyết định freshness và vì sao.
5. Cách thay đổi ETag khi server cập nhật representation.

### Nhiệm vụ B — Tính tuổi và thời điểm revalidate

Cho một cache nhận response ở **12:00:03** sau khi gửi request lúc **12:00:01**:

~~~http
Date: Wed, 18 Nov 2026 11:59:55 GMT
Age: 5
Cache-Control: public, max-age=90
ETag: "catalog-v12"
~~~

Tại **12:00:33**, hãy tính:

- apparent_age, response_delay, corrected_age_value;
- corrected_initial_age, resident_time, current_age;
- freshness lifetime còn lại;
- thời điểm xấp xỉ chuyển stale nếu không có tác động khác.

**Gợi ý kiểm tra kết quả:** apparent_age=8 giây; response_delay=2 giây; corrected_age_value=7 giây; corrected_initial_age=8 giây; resident_time=30 giây; current_age=38 giây; còn khoảng 52 giây freshness. Mốc stale xấp xỉ **12:01:25**, nếu không có biến động thời gian/metadata khác.

### Nhiệm vụ C — Mô phỏng 304

Cho client hoặc CDN có ETag **"catalog-v12"** và response đã stale. Hãy viết request có **If-None-Match**, hai response có thể xảy ra khi origin giữ nguyên hoặc đã chuyển sang version 13, và mô tả cache xử lý body/metadata theo từng trường hợp.

### Nhiệm vụ D — Cài đặt và kiểm thử

1. Tạo controller Spring cho catalog và product, có ETag theo version và Cache-Control theo yêu cầu.
2. Viết test GET đầu tiên 200, conditional GET 304, body rỗng cho 304, phiên bản mới trả 200.
3. Dựng một proxy/cache môi trường thử hoặc tích hợp CDN staging, xác minh **Age tăng** và **revalidation khi stale**.
4. Đổi Accept-Language hoặc query filter, xác nhận các biến thể không bị trộn nếu representation phụ thuộc vào chúng.
5. Dùng hai người dùng khác tenant để thử /me/orders; kiểm tra không có cache dùng chung trả dữ liệu sai.
6. Ghi nhận hit rate, origin request rate, p95 latency, số lần 304, lượng dữ liệu truyền và sự cố stale không đúng chính sách.

**Sản phẩm cần nộp:** Bảng policy từng endpoint; lời giải phép tính Age; hai HTTP transcript 304/200; controller Spring; OpenAPI; ma trận test; nhận xét bảo mật và hiệu năng.

## 19. Checklist trước khi công bố chính sách HTTP cache

| Câu hỏi | Chỉ coi là đạt khi |
| --- | --- |
| Resource có được phép lưu trong cache không? | Xét dữ liệu, quyền và loại private/shared |
| max-age/s-maxage/Expires có mâu thuẫn không? | Quy tắc ưu tiên rõ và test được |
| Có hiểu Age là tuổi response không? | Không reset TTL ở mỗi proxy |
| Có dùng đúng công thức current age không? | Tính được cả upstream Age, Date và resident time |
| Thời điểm stale có được dự báo không? | Current age được so với freshness lifetime |
| no-cache/no-store/must-revalidate dùng đúng? | Không nhầm lưu và buộc xác thực lại |
| Có validator đáng tin khi cần? | ETag/Last-Modified phản ánh representation thực |
| 304 có được xử lý đúng? | Không body; cập nhật cache metadata theo RFC |
| Cache key có đủ URI/query/Vary không? | Không trả nhầm language, filter hoặc page |
| Dữ liệu riêng tư có được bảo vệ? | Không chia sẻ qua CDN; authz vẫn được thực hiện |
| CDN có override TTL/policy không? | Cấu hình origin và edge thống nhất |
| Có test lúc fresh và stale? | Không chỉ test response lần đầu |
| Có test clock skew và nhiều cache? | Age/Date được hiểu đúng trên chuỗi proxy |
| Có theo dõi hiệu quả và rủi ro? | Cache hit, 304, p95, data freshness và security findings |

## 20. Kết luận

**Freshness** xác định một response có còn đủ mới để cache sử dụng hay không. **Cache-Control: max-age/s-maxage** và **Expires** định nghĩa giới hạn độ mới; **Date** và **Age** giúp xác định **độ tuổi hiện tại**, kể cả khi response đã qua các tầng cache. Khi **current age không còn nhỏ hơn freshness lifetime**, response trở thành **stale**; cache thường cần **revalidation** bằng ETag/Last-Modified và xử lý **304 Not Modified** hoặc **200 OK** theo kết quả từ origin.

Thiết kế caching tốt không chỉ tăng cache hit. Nó còn phải giữ đúng **hợp đồng dữ liệu, quyền riêng tư, tính nhất quán giữa các biến thể và quy tắc xử lý response hết hạn**. Khi viết hoặc kiểm thử REST API, hãy luôn trả lời được: **“Bản này được lưu ở đâu, hiện đã bao nhiêu tuổi, còn fresh bao lâu, và tại thời điểm nào phải hỏi lại nguồn có thẩm quyền?”**
