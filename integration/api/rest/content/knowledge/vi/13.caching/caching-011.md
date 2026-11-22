# Vô hiệu hóa cache sau thao tác ghi và giới hạn nhất quán

## 1. Bài toán: dữ liệu đã cập nhật nhưng API vẫn trả phiên bản cũ

Một REST API bán hàng cho phép khách xem sản phẩm, quản trị viên thay giá và ứng dụng kiểm tra tồn kho. Để giảm tải database, hệ thống đưa kết quả **GET /api/products/42** vào cache trong 5 phút. Sau đó quản trị viên gửi **PATCH /api/products/42** để đổi giá từ 120.000 đồng thành 99.000 đồng. Database xác nhận đã cập nhật, nhưng nhiều người dùng vẫn thấy giá cũ.

Trong tình huống này, HTTP API có thể trả đúng status **200 OK** cho PATCH nhưng **trạng thái đọc sau ghi** chưa đáp ứng kỳ vọng. Nguyên nhân có thể là:

- Cache của ứng dụng chưa bị vô hiệu hóa sau transaction.
- API đã xóa cache tại một instance nhưng instance khác vẫn giữ bản cũ.
- **CDN/reverse proxy** đang lưu GET cũ và không nhìn thấy yêu cầu PATCH.
- Cache bị vô hiệu hóa đúng lúc nhưng một request GET đồng thời lại **điền dữ liệu cũ vào cache**.
- Dữ liệu đọc từ **read replica** chưa bắt kịp primary, khiến lần tải lại cache lấy chính bản cũ.
- Client/browser vẫn dùng response còn **fresh** theo Cache-Control và chưa gửi request mới.

Vì vậy, “thêm Redis”, “đặt TTL ngắn” hoặc “gọi evict sau save” **chưa tự giải quyết toàn bộ bài toán**.

Bài **“Vô hiệu hóa cache sau thao tác ghi và giới hạn nhất quán”** thuộc chương **Bộ nhớ đệm** của module **INTEGRATION_API_REST**. Người học vận dụng kiến thức về **resource, URI, phương thức, status HTTP, hợp đồng response, ETag, điều kiện request, xác thực/phân quyền, OpenAPI và kiểm thử Java/Spring** để thiết kế cơ chế cache có ngữ nghĩa đúng.

Sau bài này, bạn có thể:

1. Phân biệt **cache invalidation** với **cache refresh**, TTL và HTTP conditional requests.
2. Giải thích khi nào HTTP cache phải vô hiệu hóa representation sau một phương thức không an toàn theo **RFC 9111**, và vì sao điều đó không đủ cho mọi layer.
3. Chọn thời điểm vô hiệu hóa theo **database commit**, phân tích race condition giữa GET và write, và các cơ chế khắc phục.
4. Thiết kế **read-your-writes, eventual consistency, bounded staleness** phù hợp nghiệp vụ.
5. Áp dụng **ETag/If-None-Match/If-Match**, Cache-Control và cache keys đúng với user/tenant.
6. Mô tả triển khai với Spring Cache, sự kiện sau commit, outbox cho nhiều node và kế hoạch kiểm thử lỗi.

> **Nguyên tắc:** Cache là **bản sao được phép sử dụng trong một giới hạn nhất quán đã xác định**. Muốn bảo đảm một dữ liệu mới được quan sát, phải chỉ rõ **cache nào**, **được vô hiệu hóa khi nào**, **ai thấy dữ liệu mới**, và **khi nào những bản sao khác được phép hết hạn**.

## 2. Vị trí của các cache và “nguồn sự thật”

Một request GET có thể đi qua nhiều cache, không phải chỉ một Redis:

~~~mermaid
flowchart LR
    B["Browser / mobile client cache"] --> C["CDN / edge cache"]
    C --> P["Reverse proxy / API gateway cache"]
    P --> A["REST API"]
    A --> L["Local in-memory cache"]
    L --> D["Distributed cache"]
    D --> DB[("Primary database / source of truth")]
    DB --> RR[("Read replica")]
    A -. "có thể đọc" .-> RR
~~~

Sơ đồ là **mô hình khái niệm**, không có nghĩa một ứng dụng cần triển khai toàn bộ các tầng. Trong một hệ thống thật, cache miss ở local/distributed có thể dẫn tới primary hoặc replica tùy kiến trúc; bản thân mỗi lớp có khóa, TTL, cơ chế invalidation và phạm vi chia sẻ riêng.

| Tầng | Ai quản lý? | Cách mất hiệu lực thường gặp | Rủi ro |
|---|---|---|---|
| **Browser / HTTP client** | Trình duyệt, SDK | HTTP cache semantics, revalidation, xóa dữ liệu cục bộ | Tiếp tục dùng bản fresh dù server đã đổi |
| **CDN / edge** | CDN hoặc tổ chức | TTL, purge URI/tag, đổi cache key, revalidation | Nhiều vùng edge chưa purge đồng thời |
| **Reverse proxy** | Gateway/proxy | HTTP invalidation, policy proxy, purge | Request ghi không đi qua cùng cache |
| **Local in-memory** | Từng instance API | Evict tại instance, broadcast, TTL | Một node đổi cache nhưng node khác còn dữ liệu cũ |
| **Distributed cache** | Redis/managed cache/ứng dụng | DEL, tag/version, TTL, event | Delete/set không đồng bộ với DB commit |
| **Read replica/materialized view** | Database/consumer | Replication hoặc cập nhật view | Có độ trễ dù cache đã miss |

**Nguồn sự thật (source of truth)** thường là cơ sở dữ liệu giao dịch hoặc kho dữ liệu có thẩm quyền theo miền nghiệp vụ. Nhưng **đọc trực tiếp DB cũng chưa đủ** nếu đọc từ một replica eventual-consistent hoặc một materialized view chưa cập nhật.

### “Ghi thành công” phải được định nghĩa

Đối với **PATCH /products/42**, có ít nhất ba thời điểm khác nhau:

1. **Write received**: server đã nhận request, chưa chắc transaction đã commit.
2. **Write committed**: thay đổi đã được commit bền vững theo bảo đảm của database.
3. **Write visible**: mọi con đường đọc liên quan đã thấy phiên bản mới theo cam kết nhất quán.

Một HTTP **200 OK/204 No Content** sau mutation thường cần nói rõ thời điểm nào đã đạt. Nếu API chỉ **nhận việc xử lý bất đồng bộ** thì **202 Accepted** với resource theo dõi trạng thái có thể phù hợp hơn, không được gọi đó là commit hoàn tất.

## 3. Cache invalidation, expiration, refresh và revalidation khác nhau

| Cơ chế | Diễn giải | Khi phù hợp | Điều không tự bảo đảm |
|---|---|---|---|
| **Expiration theo TTL** | Bản sao tự hết freshness sau thời gian đặt trước | Dữ liệu chấp nhận cũ trong khoảng | Không thấy update ngay khi ghi |
| **Explicit invalidation / eviction** | Đánh dấu bản sao không còn dùng được hoặc xóa entry | Muốn giảm cửa sổ trả dữ liệu cũ sau ghi | Không tự đồng bộ mọi tầng cache |
| **Refresh** | Lấy representation mới và thay entry | Dữ liệu nóng, dự báo cache miss cao | Refresh đọc từ replica cũ có thể tái điền stale |
| **Revalidation** | HTTP cache hỏi origin xem bản lưu còn hợp lệ không, thường qua validator | Giảm bandwidth khi entry stale | Không bắt origin kiểm tra nếu entry vẫn fresh và policy cho phép dùng |
| **Versioned cache key** | Khóa cache gồm phiên bản nội dung; version đổi thì dùng key mới | Chống ghi đè bản mới bằng bản cũ | Phải lấy version đủ mới và dọn khóa cũ |
| **Bypass cache** | Đọc một đường có bảo đảm nhất quán cao hơn | Read-after-write, quyết định tài chính/tồn kho | Có chi phí và tải cao hơn; replica có thể vẫn lag |

### Cache “stale” là gì?

Một biểu diễn **stale** theo HTTP caching là biểu diễn có thời gian freshness đã hết; tuy nhiên từ góc nhìn nghiệp vụ, một bản **vẫn fresh theo TTL nhưng khác database mới** cũng là dữ liệu **cũ về nội dung**.

Ví dụ `Cache-Control: max-age=300`: lúc t=0 cache lưu giá 120.000. Lúc t=20 giá được cập nhật thành 99.000. Tại t=30, nếu không có invalidation, HTTP cache vẫn có thể coi bản lưu **fresh** trong phần TTL còn lại, dù giá đã đổi. **Freshness theo HTTP và độ mới của nghiệp vụ không phải cùng khái niệm.**

### Invalidation không luôn là xóa vật lý

Cache có thể xóa entry, đánh dấu invalid, đổi version, hoặc giữ stale entry cho trường hợp được phép dùng theo policy. Điều cần kiểm chứng là **cache không còn phục vụ bản sai ngoài giới hạn**, không phải nhất thiết một lệnh `DEL` đã chạy.

## 4. Quy tắc HTTP: thao tác ghi có tự vô hiệu hóa cache không?

Theo **RFC 9111, mục 4.4 (Invalidating Stored Responses)**, khi một HTTP cache **nhận phản hồi không phải lỗi** cho request dùng phương thức **không an toàn** hoặc phương thức chưa biết có an toàn hay không, cache **phải vô hiệu hóa target URI** của request.

### Phương thức safe và unsafe

- **GET** và **HEAD** là safe theo ngữ nghĩa HTTP; chúng không được thiết kế để tạo thay đổi nghiệp vụ được client yêu cầu.
- **POST, PUT, PATCH, DELETE** được dùng cho các tương tác có thể thay đổi trạng thái, nên cần xét quy tắc invalidation khi cache quan sát chúng.
- **OPTIONS** cũng safe theo HTTP semantics, không dùng để thực hiện ghi.

Ví dụ cache trung gian lưu response của:

~~~http
GET /api/products/42 HTTP/1.1
Host: api.example.test

HTTP/1.1 200 OK
Cache-Control: public, max-age=300
ETag: "product-42-v5"

{"id":42,"price":120000}
~~~

Sau đó **cùng cache này** nhận phản hồi thành công cho:

~~~http
PATCH /api/products/42 HTTP/1.1
Host: api.example.test
Content-Type: application/merge-patch+json
If-Match: "product-42-v5"

{"price":99000}
~~~

~~~http
HTTP/1.1 204 No Content
ETag: "product-42-v6"

~~~

Với các điều kiện trên, HTTP cache đã quan sát phản hồi mutation phải **invalidate các response đã lưu của target URI /api/products/42**. Điều này không đồng nghĩa nó tự tìm được tất cả representation khác của sản phẩm hay mọi trang collection.

### Những giới hạn rất quan trọng của quy tắc tự động

1. **Chỉ cache nào nhìn thấy response của thao tác unsafe mới áp dụng quy tắc đó.** Nếu browser gửi PATCH trực tiếp qua đường khác nhưng một CDN phục vụ GET không quan sát PATCH, CDN không tự biết rằng phải purge.
2. **Target URI** là đích của request ghi. PATCH **/api/products/42** không tự đồng bộ mọi cache của **/api/products?category=BOOK**, **/api/search?q=...** hoặc **/api/categories/7/count**.
3. Một HTTP cache **có thể** invalidation thêm các URI liên quan, nhất là URI trong **Location** và **Content-Location** của phản hồi, nhưng điều đó **không phải cơ chế phổ quát được bảo đảm**.
4. Một HTTP cache **không được** dùng những URI có **origin khác** trong các trường liên quan để kích hoạt invalidation ngoài origin của target URI theo quy tắc chuẩn.
5. Phản hồi **lỗi** không kích hoạt yêu cầu invalidation này như một response ghi không lỗi. Không được giả định rằng PATCH nhận 409/412 đã cập nhật dữ liệu.
6. Cache ở **application/Redis** không tự động tuân thủ HTTP invalidation chỉ vì server đã dùng phương thức PATCH; đó là cơ chế do ứng dụng phải thiết kế.

### Tình huống POST vào collection

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"cartId":"cart-9"}
~~~

~~~http
HTTP/1.1 201 Created
Location: /api/orders/913
Content-Type: application/json

{"id":913,"status":"CREATED"}
~~~

Cache quan sát thành công POST phải invalidation **target /api/orders**. URI trong **Location** có thể là ứng viên cho invalidation bổ sung, nhưng không nên dựa vào việc mọi proxy đều làm như nhau. Việc tạo đơn còn có thể làm thay đổi **/api/orders?status=CREATED&sort=...**, các bộ đếm dashboard và cache tìm kiếm: API cần thiết kế invalidation theo **dependency của dữ liệu**, không chỉ theo request target.

### Cẩn thận với biến thể cache key

Nhiều HTTP cache phân biệt response theo **URI + các header trong Vary**. Invalidation target cần làm cho các response đã lưu ứng với target URI không còn được dùng trái quy tắc, kể cả các biến thể phù hợp. Không chỉ xóa một cache key JSON do ứng dụng tự đặt rồi tuyên bố mọi variant HTTP đã được invalidation.

## 5. Dependency graph: một mutation làm bẩn những representation nào?

Hãy coi các response cacheable là **các phép chiếu (projection)** của dữ liệu:

~~~mermaid
flowchart LR
    W["PATCH /api/products/42"] --> DB[("Products DB")]
    DB --> P["GET /api/products/42"]
    DB --> C["GET /api/products?category=BOOK"]
    DB --> S["GET /api/search?q=java"]
    DB --> T["GET /api/categories/BOOK/summary"]
    DB --> R["GET /api/recommendations?user=..."]
    P -. "invalidation rõ target" .-> I["Invalidation strategy"]
    C -. "dependency" .-> I
    S -. "dependency" .-> I
    T -. "dependency" .-> I
    R -. "có thể chấp nhận stale" .-> I
~~~

Một thay đổi **giá** có thể ảnh hưởng item, trang list có giá, kết quả tìm kiếm, tính tổng hoặc recommendation. Một thay đổi **tên** ảnh hưởng list/sort/search khác; một thay đổi **tồn kho** có thể ảnh hưởng badge “còn hàng” mà không cần invalidation mô tả sản phẩm tĩnh.

### Lập bảng phụ thuộc theo loại ghi

| Lệnh ghi | Target URI | Representation có thể ảnh hưởng | Giải pháp gợi ý |
|---|---|---|---|
| PATCH giá sản phẩm | **/products/{id}** | Item, list theo category, search, giá trên recommendation | Evict theo product ID + tag/category/chiến lược TTL cho search |
| POST sản phẩm mới | **/products** | Collection và các bộ lọc/đếm liên quan | Evict collection/tag, cập nhật index bất đồng bộ có SLO riêng |
| DELETE sản phẩm | **/products/{id}** | Item, collection, search, cart nếu lưu bản sao | Evict + loại bỏ/tombstone phù hợp; tránh phục hồi bản cũ |
| PATCH trạng thái đơn | **/orders/{id}** | Item, danh sách theo trạng thái, thống kê, timeline | Event theo order ID; invalidation page/tổng hoặc TTL |
| POST thanh toán | **/payments** | Payment, order balance, lịch sử, hạn mức | Không dùng cache cũ để quyết định trừ tiền; read-after-write theo bảo đảm dữ liệu |

**Điều quan trọng:** Không nhất thiết phải evict mọi query key khi ghi một record nếu chi phí quá cao. Có thể chọn:

- Tag/cache dependency để xóa nhóm representation.
- Version hóa **collection generation** để key cũ không còn được tra cứu.
- TTL ngắn cho view lớn và eventual consistency được công bố.
- Không cache những truy vấn nhạy cảm với cập nhật tức thời.
- Tách projection/chỉ mục đọc có SLO về độ trễ cập nhật.

## 6. Chọn chiến lược caching và invalidation

| Mô hình | Read | Write | Ưu điểm | Rủi ro/đánh đổi |
|---|---|---|---|---|
| **Cache-aside / lazy loading** | Cache miss → DB → cache | Commit DB rồi evict cache liên quan | Đơn giản, phổ biến | Race GET điền stale; double miss; evict sai thời điểm |
| **Read-through** | Cache layer tự tải từ DB | Phải gắn cơ chế invalidation/update | Đơn giản hóa caller | Cache layer cần hiểu nguồn dữ liệu, quyền và nhất quán |
| **Write-through** | Read từ cache/DB theo thiết kế | Ghi qua cache rồi ghi DB theo quy tắc đồng bộ | Có thể đồng bộ cache với lệnh ghi | Phải định nghĩa atomicity/lỗi giữa hai hệ; thứ tự và latency |
| **Write-around** | Đọc theo đường cache-aside | Ghi DB và invalidation/bỏ qua cập nhật cache | Giảm cache pollution do ghi nhiều | Read sau ghi có thể miss và cần bảo đảm dữ liệu nguồn |
| **Write-behind / write-back** | Cache có thể giữ trạng thái mới trước DB | Đồng bộ xuống nguồn sau | Giảm latency ghi | Rủi ro mất dữ liệu và xung đột; cần durable log, replay, thứ tự |
| **TTL-only** | Dùng bản lưu đến hết TTL | Không gửi thông điệp invalidation | Ít coupling, đơn giản | Staleness có thể tới thời hạn được phép, thậm chí lâu hơn nếu có stale policy |
| **Versioned key** | Dùng key theo version/generation | Đổi version sau commit | Chống bản cũ ghi đè key mới | Phải quản lý version, rác key và việc đồng bộ version |

**Write-through** không tự có giao dịch nguyên tử giữa cache và database nếu hai hệ thống độc lập. **Write-behind** không nên dùng cho giao dịch tiền hoặc kho hàng nếu chưa có bảo đảm bền vững và recovery đủ mạnh.

### Chọn theo rủi ro nghiệp vụ

| Loại dữ liệu | Mức nhất quán thường cần xem xét | Chiến lược khởi đầu |
|---|---|---|
| Catalog mô tả ít thay đổi | Chấp nhận stale ngắn | CDN/HTTP max-age + purge khi sửa hoặc TTL có giới hạn |
| Giá khuyến mãi | Cần minh bạch khoảng trễ, phụ thuộc pháp lý/nghiệp vụ | Evict theo giá + giới hạn TTL + kiểm tra giá chính thức lúc checkout |
| Ảnh, CSS, tệp tĩnh có hash | Immutable theo version | URL có content hash và `immutable` |
| Trạng thái đơn của chính người vừa sửa | Thường cần read-your-writes | Bypass/đọc primary hoặc version-aware cache |
| Số dư, quyết định thanh toán, giữ chỗ | Cần tính đúng và kiểm soát đồng thời | Giao dịch tại source of truth, không quyết định từ cache eventual-consistent |
| Báo cáo phân tích tổng hợp | Có thể eventual-consistent | Projection được cập nhật async, hiển thị mốc `asOf` và SLO độ trễ |

Không áp một TTL cố định cho mọi endpoint. Những dữ liệu có cùng schema JSON có thể có **yêu cầu nhất quán rất khác nhau**.

## 7. Thứ tự ghi và invalidation: vì sao phải xét commit?

Trong cache-aside, một thứ tự thường được chọn là:

1. Xác thực, phân quyền và kiểm tra điều kiện cập nhật.
2. Bắt đầu transaction, thay đổi dữ liệu ở nguồn sự thật.
3. **Commit thành công**.
4. Invalidate những entry liên quan, hoặc phát một cơ chế invalidation đáng tin.
5. Trả kết quả theo hợp đồng đã công bố.

### Xóa cache trước commit có thể tạo dữ liệu cũ được tái điền

~~~text
Thời gian  | Writer A                              | Reader B
-----------+---------------------------------------+--------------------------
t0         | DB đang có price=120000              |
t1         | BEGIN; UPDATE price=99000             |
t2         | DELETE cache key product:42          |
t3         |                                       | Cache MISS
t4         |                                       | DB chưa commit: đọc 120000
t5         |                                       | SET cache=120000
t6         | COMMIT price=99000                     |
t7         |                                       | GET khác đọc cache=120000
~~~

**Xóa trước commit** làm mở cửa sổ cache miss và lấy dữ liệu cũ chưa được commit. Nếu hệ thống không tiếp tục invalidate sau commit, bản cũ sống lại đến hết TTL hoặc đến lần evict tiếp theo.

### Commit trước rồi xóa cũng chưa tuyệt đối an toàn

Một chuỗi race khác:

~~~text
Thời gian  | Reader A                              | Writer B
-----------+---------------------------------------+--------------------------
t0         | Cache MISS                            |
t1         | SELECT DB -> price=120000             |
t2         |                                       | UPDATE + COMMIT 99000
t3         |                                       | DELETE cache product:42
t4         | SET cache=120000                      |
t5         | Request khác đọc cache=120000         |
~~~

Ở t4, Reader A ghi lại dữ liệu cũ **sau khi Writer B đã evict**. Đây là race **stale cache fill**, không phải lỗi cú pháp hay một lần gọi evict thất bại.

### Chiến lược giảm race

- **Versioned key:** dùng key `product:42:v6` sau khi commit thay đổi; một read cũ chỉ có thể điền `product:42:v5`, không làm bẩn key mới. Nhưng caller phải biết version mới từ một nguồn đủ tin cậy.
- **Conditional cache write/CAS:** chỉ ghi cache nếu version của dữ liệu được lấy không cũ hơn version hiện biết của entry/generation.
- **Invalidate có phối hợp** với các lệnh đọc đang chạy: serialization theo khóa, read/write lock hoặc cơ chế fencing token khi cần bảo đảm mạnh hơn.
- **Bypass cache cho đọc sau ghi** tới primary/nguồn có cam kết phù hợp, có thể dùng phiên bản tối thiểu của session.
- **TTL ngắn như lớp an toàn cuối**, không xem TTL là bằng chứng đáp ứng SLO mạnh.
- **Double deletion có độ trễ** đôi khi giảm xác suất race nhưng không phải bằng chứng loại bỏ hoàn toàn; cần cân nhắc nợ vận hành, độ trễ và sự cố mới.

Nếu cần **linearizable reads**, một cache-aside thông thường với eviction bất đồng bộ **không đủ chứng minh** bảo đảm đó. Cần giao thức phối hợp/nguồn nhất quán phù hợp, hoặc không dùng cache trên đường quyết định quan trọng.

## 8. Giới hạn nhất quán phải được mô tả thành hợp đồng

Từ “nhất quán” thường bị dùng quá mơ hồ. Khi đánh giá cache, hãy chọn **mô hình có thể kiểm thử**.

| Mô hình | Điều client được hứa | Ví dụ |
|---|---|---|
| **Eventual consistency** | Nếu không có cập nhật mới và hệ thống hoạt động, các bản sao cuối cùng hội tụ | Recommendation hoặc thống kê |
| **Bounded staleness** | Dữ liệu có thể cũ tối đa một khoảng/phiên bản trong điều kiện đã mô tả | “Giá hiển thị được cập nhật trong 30 giây ở điều kiện bình thường” |
| **Read-your-writes** | Người vừa ghi thành công có thể đọc lại và thấy ít nhất phiên bản mình đã ghi | Người sửa thông tin tài khoản thấy dữ liệu mới |
| **Monotonic reads** | Một phiên đọc không thấy phiên bản cũ hơn phiên đã thấy | Không trở lại trạng thái PENDING sau khi đã thấy PAID |
| **Strong/linearizable read** | Một lần đọc diễn ra sau ghi đã hoàn tất phản ánh thứ tự thời gian thực theo bảo đảm nguồn | Kiểm tra quota/tồn kho trong giao dịch nhạy cảm |

Đây là các **mức cam kết khác nhau**, không thể suy ra chỉ từ việc dùng Redis, CDN hoặc database managed.

### Bounded staleness cần điều kiện cụ thể

Một câu “cache cập nhật trong 30 giây” chỉ có giá trị nếu có:

- Mốc bắt đầu đo: **sau DB commit** hay sau khi user nhận 200?
- Phạm vi: toàn bộ tenant, region, edge POP, local cache hay chỉ một instance?
- Dữ liệu: item, list, search, recommendation, dashboard?
- Điều kiện: khi event bus/CDN hoạt động bình thường; xử lý khi purge thất bại ra sao?
- Thước đo: p95/p99 hay **đảm bảo tuyệt đối**; có giám sát vượt ngưỡng không?

TTL `max-age=30` trên một tầng **không tự bảo đảm độ trễ nhất quán tối đa 30 giây end-to-end**, vì còn read replica lag, invalidation queue, stale-while-revalidate và các tầng cache khác.

### Read-your-writes qua API

Sau PATCH, server có thể trả representation mới với version/ETag:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "product-42-v6"
Cache-Control: no-store

{"id":42,"price":99000,"version":6}
~~~

Client có thể **cập nhật UI trực tiếp từ response đã commit**; ở GET tiếp theo, nếu cần read-your-writes, client hoặc server dùng **version >= 6**, primary read hoặc đường cache được bảo đảm. Chỉ trả ETag không tự buộc các cache khác phục vụ version 6.

### Thông tin `asOf` cho dữ liệu eventual-consistent

~~~json
{
  "data": {"soldToday": 1042},
  "metadata": {
    "asOf": "2026-11-18T10:00:00Z",
    "consistency": "eventual"
  }
}
~~~

`asOf` trong ví dụ là thời điểm của một projection đã được cập nhật; nó **không phải bảo đảm thời gian trễ** nếu không có quan sát và hợp đồng kèm theo. Tính minh bạch thường tốt hơn tuyên bố sai rằng mọi số liệu đều tức thời.

## 9. TTL, Cache-Control và điều kiện cho phép dùng stale

Trong HTTP, **Cache-Control** điều khiển cách cache lưu, dùng và xác minh lại representation:

| Directive | Ý nghĩa thực dụng | Cảnh báo |
|---|---|---|
| **max-age=N** | Cho phép dùng response ở trạng thái fresh tối đa N giây theo tuổi response | Không nhận biết mutation mà cache không nhìn thấy |
| **s-maxage=N** | Freshness riêng cho shared cache khi áp dụng | Không tự purge trên các CDN khác |
| **private** | Response chỉ dành cho cache riêng của một user agent theo HTTP semantics | Không dùng như cơ chế authorization |
| **no-store** | Không lưu request/response theo phạm vi directive | Không phải lệnh xóa những bản sao đã lưu trước đó |
| **no-cache** | Có thể lưu nhưng phải validate trước khi dùng lại | Tên dễ gây nhầm: không phải “cấm cache” |
| **must-revalidate** | Khi stale, không được dùng lại nếu chưa validate thành công theo quy tắc | Không bảo đảm không thấy nội dung cũ lúc response còn fresh |
| **stale-while-revalidate=N** | Cho phép dùng stale trong cửa sổ mở rộng khi revalidate bất đồng bộ theo chính sách | Tăng độ trễ quan sát update |
| **stale-if-error=N** | Cho phép dùng stale trong một số tình huống lỗi khi phù hợp | Không dùng cho dữ liệu đòi tính đúng tức thời |

**stale-while-revalidate** và **stale-if-error** được mô tả trong **RFC 5861**, thường được CDN/proxy hỗ trợ theo cấu hình. Hãy kiểm tra hành vi thực tế của từng cache và không suy rằng mọi HTTP client đều thực hiện giống nhau.

### Ví dụ catalog có thể chịu stale ngắn

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=30, s-maxage=120, stale-while-revalidate=30
ETag: "catalog-v17"
Vary: Accept

{"items":[{"id":42,"name":"Sách Java"}]}
~~~

Ở đây browser và shared cache có thể áp dụng freshness khác nhau. Nếu cho phép stale-while-revalidate, **bản cũ có thể tiếp tục được dùng trong cửa sổ stale được phép**. Với catalog marketing điều đó có thể chấp nhận; với **giá thanh toán cuối cùng** thì không nên dùng thông số này một cách thiếu đánh giá.

### Dữ liệu riêng tư

Một response lịch sử đơn hàng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{"orders":[{"id":913,"status":"PAID"}]}
~~~

Không dùng `public` chỉ để tăng cache hit cho một resource phụ thuộc user/tenant. Response có Authorization còn có các quy tắc shared cache riêng; ngay cả khi có directive mở khả năng lưu trong shared cache, vẫn phải đánh giá **cache key, Vary, quyền truy cập, CORS và dữ liệu nhạy cảm**.

### Request `Cache-Control: no-cache` không phải cơ chế toàn năng

Client có thể gửi **Cache-Control: no-cache** để yêu cầu cache kiểm tra lại trước khi đáp ứng, nhưng cache phải thực thi đúng, và **nguồn revalidation có thể là một replica/projection cũ**. Với trạng thái nghiệp vụ bắt buộc mới, nên thiết kế server-side freshness/version guard thay vì trông chờ một request header của client.

## 10. ETag, conditional GET và conditional write

**ETag** là một **validator** cho representation. Nó giúp HTTP cache/clients xác minh một bản lưu, và khi dùng đúng, giúp tránh ghi đè cập nhật đồng thời.

### GET có điều kiện với If-None-Match

~~~http
GET /api/products/42 HTTP/1.1
Host: api.example.test
If-None-Match: "product-42-v5"

~~~

Nếu representation hiện tại **vẫn khớp validator**, server có thể trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "product-42-v5"
Cache-Control: private, max-age=30
Vary: Accept

~~~

Nếu đã đổi sang v6, server trả **200 OK** cùng body và ETag mới. **304 không có message content**, không được dùng như body dữ liệu mới. Một conditional GET đúng giảm bandwidth, nhưng chỉ có hiệu lực **khi revalidation thật sự diễn ra**; cache fresh có thể dùng bản lưu mà không hỏi origin.

### PATCH có điều kiện với If-Match

~~~http
PATCH /api/products/42 HTTP/1.1
Host: api.example.test
Content-Type: application/merge-patch+json
If-Match: "product-42-v5"

{"price":99000}
~~~

Nếu ETag của **target resource** không còn khớp, server có thể trả **412 Precondition Failed** và **không thực hiện cập nhật được điều kiện bảo vệ**:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/version-conflict",
  "title": "Precondition Failed",
  "status": 412,
  "detail": "Phiên bản sản phẩm đã thay đổi; hãy đọc lại trước khi cập nhật."
}
~~~

**Phân biệt hai vai trò:**

- **If-None-Match trên GET**: kiểm tra xem bản đọc đã lưu có còn hợp lệ hay không.
- **If-Match trên mutation**: ngăn một thay đổi dựa trên phiên bản cũ ghi đè phiên bản mới.

**ETag/If-Match không thay cho invalidation.** Một cache ở edge vẫn có thể giữ v5 theo TTL, trong khi database đã commit v6; điều kiện ghi bảo vệ DB nhưng không tự purge bản đọc ở edge.

### Strong và weak validators

ETag có thể ở dạng strong (`"v6"`) hoặc weak (`W/"v6"`). Với **If-Match**, HTTP dùng **strong comparison**; không nên dùng weak ETag để thực hiện một điều kiện cập nhật yêu cầu so khớp mạnh. Khi cung cấp nhiều representation variant (JSON/HTML, ngôn ngữ khác nhau), phải tạo validator phản ánh đúng semantics representation; tránh dùng một **strong ETag** cho các octet representations khác nhau.

### Không dùng ETag là khóa quyền

ETag là metadata về representation, **không phải credential**. Dù client cung cấp If-Match chính xác, server vẫn phải xác thực, phân quyền và kiểm tra quy tắc nghiệp vụ ở thời điểm request.

## 11. Cache keys: scope, query parameters và dữ liệu nhạy cảm

Tính đúng của invalidation phụ thuộc vào việc **biết dữ liệu nào đang được cache dưới khóa nào**.

### Một khóa cache ứng dụng an toàn hơn

Ví dụ cho sản phẩm theo tenant:

~~~text
product-view:v1:tenant-27:product-42:locale-vi
~~~

Nếu response phụ thuộc vào các yếu tố sau, key (hoặc partition/cache policy) phải phản ánh chúng:

- **tenant/user/role/scope** khi dữ liệu nhìn thấy khác nhau theo quyền;
- **URI, query filter, sort, pagination/cursor**;
- **language, representation media type, currency, feature flag** khi thay đổi nội dung;
- **version dữ liệu hoặc generation** nếu dùng versioned keys.

### Không dùng token làm cache key

Không ghi raw bearer token/API key vào tên khóa Redis, log hoặc metric label. Sử dụng **identity đã xác thực, định danh nội bộ không nhạy cảm**, và phân vùng phù hợp. Nếu nội dung thay đổi theo quyền của từng người ngay cả trong cùng tenant, **tenant ID đơn độc chưa đủ**.

### Vary và HTTP cache key

HTTP caches sử dụng thông tin URI và **Vary** để chọn representation phù hợp. Ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Vary: Accept, Accept-Language
Cache-Control: private, max-age=60

{"name":"Sản phẩm ví dụ"}
~~~

`Vary` giúp cache phân biệt biến thể theo request headers, nhưng không thay thế việc đánh giá **authorization và cache partition**. Không giả định một shared proxy tùy ý sẽ tạo khóa theo user chỉ vì ứng dụng có header Authorization.

### Invalidation collection và filter query

Một PATCH có thể khiến sản phẩm 42 chuyển từ category A sang B. Nếu cache key của list là:

~~~text
products:tenant-27:category-A:page-1
products:tenant-27:category-B:page-1
~~~

thì không chỉ cache item cần cập nhật: **cả hai collection query** có thể bị ảnh hưởng. Nếu có nhiều tổ hợp filter/sort/cursor, không thể liệt kê thủ công tất cả. Cần tag dependency, generation hoặc TTL được công bố.

## 12. Distributed invalidation, sự kiện và transactional outbox

Khi có **nhiều instance, nhiều region hoặc nhiều cache độc lập**, một lệnh evict trong bộ nhớ của một node không có tác dụng trên các node còn lại. Có thể phát sự kiện invalidation:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Orders API
    participant DB as Database + Outbox
    participant P as Outbox Relay
    participant B as Broker
    participant W as Cache Invalidator
    participant K as Redis / CDN
    C->>A: PATCH /api/orders/913
    A->>DB: Transaction: update order + insert outbox event
    DB-->>A: Commit
    A-->>C: 200/204 theo hợp đồng nhất quán
    P->>DB: Đọc outbox chưa publish
    P->>B: Publish OrderChanged(id=913,version=8)
    B-->>P: ACK
    P->>DB: Mark outbox delivered
    B->>W: Deliver event (có thể trùng)
    W->>K: Evict keys / bump generation / purge tags
    W-->>B: ACK sau thao tác an toàn
~~~

**Transactional outbox** đặt bản ghi event cùng transaction dữ liệu nghiệp vụ, giảm khoảng trống “DB commit thành công nhưng process crash trước khi publish”. Tuy nhiên:

- Relay có thể phát **trùng** khi broker nhận nhưng chưa ghi trạng thái delivered.
- Invalidation nên **idempotent**: xóa key lặp thường an toàn, còn **ghi lại giá trị cũ** thì không.
- Sự kiện có thể **đến không đúng thứ tự**, cần version/generation để tránh event cũ hạ phiên bản hiện tại.
- Các cache/CDN purge có thể thất bại hoặc trễ; cần retry, DLQ, alert và **TTL như lớp dự phòng** theo SLO.
- Sau khi API trả 200, quá trình publish/purge có thể **chưa hoàn tất**. Vì thế đây là **eventual invalidation**, không được quảng bá là strong consistency nếu không có biện pháp bổ sung.

### Versioning chống sự kiện đến muộn

Giả sử event:

~~~json
{
  "eventId": "order-913-updated-v8",
  "eventType": "OrderChanged",
  "orderId": "913",
  "tenantId": "tenant-27",
  "version": 8,
  "occurredAt": "2026-11-18T10:30:00Z"
}
~~~

Nếu invalidator đã biết phiên bản v9, một event v8 đến muộn **không được ghi giá trị v8 vào cache**. Với cơ chế **evict-only**, phải xét race của các read đang điền cache, nhưng không cần viết lại dữ liệu cũ. Khi tăng generation theo event, thực hiện cập nhật **monotonic** (ví dụ `max(current, event.version)` có atomicity), không gán generation bằng giá trị thấp hơn.

### CDN purge và edge consistency

Một CDN có thể hỗ trợ purge theo **URL**, **cache tag/surrogate key**, hoặc **prefix** tùy nhà cung cấp. Không mặc định mọi CDN hỗ trợ cùng tên header và cùng thời gian purge. Đánh giá:

1. Phạm vi các điểm biên (POP) cần purge.
2. Thời gian purge p95/p99 và failure rate thực tế.
3. Cách nhận ACK và kiểm chứng sau purge.
4. Ảnh hưởng tới cache hit ratio và tải origin khi purge hàng loạt.
5. Trường hợp edge mất kết nối hoặc phục vụ stale theo policy.

Một bản cache CDN có thể đang fresh theo `s-maxage` dù Redis đã được evict; giải pháp phải bao phủ **đúng layer**.

## 13. Spring Boot 3: ví dụ cache-aside và evict sau commit

Ví dụ dưới đây minh họa **application-level cache** với **Spring Framework 6 / Spring Boot 3**. Nó không tự điều khiển browser/CDN cache. Cần cấu hình `@EnableCaching`, CacheManager và cache provider (in-memory/Redis...) trong ứng dụng thực.

### 13.1. Đọc qua cache

~~~java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

record ProductView(long id, String name, long price, long version) {}

@Service
class ProductQueryService {
    private final ProductRepository repository;

    ProductQueryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "productViews",
            key = "#tenantId + ':' + #id")
    public ProductView getById(String tenantId, long id) {
        Product product = repository.findByTenantIdAndId(tenantId, id)
                .orElseThrow(() -> new ProductNotFoundException(id));
        return new ProductView(product.id(), product.name(),
                product.price(), product.version());
    }
}
~~~

`ProductRepository`, `Product`, `ProductNotFoundException` là các loại miền **được ứng dụng tự cung cấp**; ví dụ không phải project độc lập có thể biên dịch ngay.

**Lưu ý an ninh:** Với `@Cacheable`, khi cache hit thì **body của method không chạy**. Nếu bạn đặt kiểm tra quyền **bên trong method được cache**, cache hit có thể bỏ qua kiểm tra đó. Phải đảm bảo xác thực và phân quyền đã xảy ra **trước khi truy cập cache**, và key bao gồm các yếu tố scope cần thiết. Không chỉ tin `tenantId` client tự truyền.

### 13.2. Mutation phát sự kiện trong cùng luồng giao dịch

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

record ProductChanged(String tenantId, long productId, long version) {}

@Service
class ProductMutationService {
    private final ProductRepository repository;
    private final ApplicationEventPublisher publisher;

    ProductMutationService(ProductRepository repository,
                           ApplicationEventPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Transactional
    public ProductView changePrice(
            String tenantId, long id, long newPrice) {
        Product product = repository.findByTenantIdAndId(tenantId, id)
                .orElseThrow(() -> new ProductNotFoundException(id));

        // Kiểm tra quyền, expected version và giá hợp lệ ở tầng phù hợp.
        product.setPrice(newPrice);
        Product saved = repository.save(product);
        // Giả định version của entity đã được cập nhật đúng tại đây.
        publisher.publishEvent(
                new ProductChanged(tenantId, id, saved.version()));

        return new ProductView(saved.id(), saved.name(),
                saved.price(), saved.version());
    }
}
~~~

Lớp service chỉ phát **application event nội bộ trong transaction**. `saved.version()` trong một ORM có thể chưa phản ánh version DB cuối cùng nếu flush/commit chưa diễn ra; ứng dụng thực cần bảo đảm version chính xác (flush, lock, hoặc lấy version sau commit theo chiến lược đã chọn). Không dựa vào giả định này để cài đặt CAS/version key nếu chưa kiểm chứng.

### 13.3. Invalidation sau commit

~~~java
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class ProductCacheInvalidator {
    private final CacheManager cacheManager;

    ProductCacheInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(ProductChanged event) {
        Cache cache = cacheManager.getCache("productViews");
        if (cache != null) {
            cache.evict(event.tenantId() + ":" + event.productId());
        }
        // Collection/search cache cũng cần chiến lược invalidation riêng.
    }
}
~~~

`@TransactionalEventListener(AFTER_COMMIT)` giúp tránh chạy eviction khi transaction **rollback**. Tuy nhiên:

- Event nội bộ **không bền vững qua process crash** sau commit; giữa DB commit và listener vẫn có cửa sổ lỗi.
- Việc evict chỉ ảnh hưởng **cache provider mà CacheManager điều khiển**, không tự purge CDN/browser.
- Eviction sau commit **không loại bỏ race stale fill** của GET đã đọc DB cũ.
- Với cache local trên từng node, chỉ node xử lý listener được evict. Cần distributed cache hoặc broadcast.
- Nếu listener/purge lỗi, phải có chiến lược retry/quan sát và giới hạn stale phù hợp.

Với hệ thống yêu cầu invalidation liên node đáng tin cậy, dùng **transactional outbox + consumer** hoặc cơ chế durable tương đương. Không coi một annotation riêng lẻ là bảo đảm exactly-once hay strong consistency.

### 13.4. Vì sao @CacheEvict đặt trên method ghi cần thận trọng?

~~~java
@CacheEvict(cacheNames = "productViews",
            key = "#tenantId + ':' + #id")
@Transactional
public void updateProduct(String tenantId, long id, UpdateCommand command) {
    // mutate repository...
}
~~~

Đây là **minh họa ý tưởng**, không phải bản triển khai được khuyến nghị vô điều kiện. Theo mặc định, eviction của `@CacheEvict` gắn với việc invocation kết thúc thành công; thứ tự giữa **cache advice và transaction advice** phụ thuộc cấu hình. Một phương thức return thành công **không tự chứng minh DB đã commit trước eviction** nếu advice order/transaction boundaries khác nhau. Ngoài ra, lệnh cập nhật collection/search cache vẫn còn thiếu. Cần xác minh lifecycle thực tế hoặc dùng event after-commit/transaction-aware cache phù hợp, cộng cơ chế durable khi cần.

### 13.5. HTTP response độc lập với Spring Cache

Một controller có thể gửi:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "product-42-v6"
Cache-Control: private, max-age=30

{"id":42,"price":99000,"version":6}
~~~

Đó là **chính sách HTTP caching** cho browser/proxy. Việc có `@Cacheable` trong service không tự sinh `ETag`, `Cache-Control` và cũng không purge CDN. Hai tầng phải được thiết kế và kiểm thử **tách biệt nhưng nhất quán**.

## 14. Trường hợp write thất bại, retry và xung đột phiên bản

### Không invalidation theo một write đã rollback

Giả sử PATCH sửa sản phẩm nhưng transaction rollback do vi phạm constraint:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/product-conflict",
  "title": "Product Conflict",
  "status": 409,
  "detail": "Cập nhật không thành công vì trạng thái dữ liệu đã thay đổi."
}
~~~

Nếu không có commit dữ liệu, không cần thông báo đã có phiên bản mới. Tuy vậy, **evict thừa** thường chỉ tăng cache miss, còn **không evict sau commit** có thể gây stale. Cần chọn chính sách dựa trên ngữ nghĩa transaction thật.

### Mất response sau commit

Một client gửi PATCH, server đã commit v6 nhưng kết nối bị ngắt trước khi client nhận 200. Client không nên lập tức gửi lại một mutation không idempotent. Cần:

- Dùng **If-Match** để kiểm soát phiên bản target phù hợp.
- Nếu dùng POST cho thao tác có side effect, có thể cần **Idempotency-Key** được lưu bền vững.
- Cho client **GET trạng thái mới** với đường đọc đủ mới hoặc endpoint tra cứu kết quả.
- Thiết kế response/retry rõ ràng khi trạng thái của request chưa biết.

### Bị từ chối 412 không phải lý do phá cache toàn bộ

Một PATCH với **If-Match: "v5"** nhận **412** vì resource đã sang v6. Hành vi đúng của client là đọc lại representation, hiểu xung đột và quyết định có ghi tiếp hay không. Không nên giải quyết mọi 412 bằng cách tự động retry PATCH vô hạn.

## 15. Tình huống thực hành: cập nhật giá nhưng trang tìm kiếm vẫn cũ

### Bối cảnh giả định

Một API thương mại điện tử có:

- **GET /api/products/{id}**: cache ứng dụng TTL 5 phút và CDN TTL 2 phút.
- **GET /api/products?category=BOOK**: cache danh sách theo filter/sort/limit.
- **GET /api/search?q=java**: kết quả từ search index cập nhật bất đồng bộ.
- **PATCH /api/products/{id}**: quản trị viên thay giá.
- Trang checkout có bước kiểm tra **giá cuối cùng từ nguồn có thẩm quyền**.

Giả định đã đo hệ thống cho thấy **p95 2 giây**, **p99 8 giây** để search index nhận cập nhật trong điều kiện bình thường; đây chỉ là dữ liệu minh họa của bài tập, không phải mức mặc định của công nghệ.

### Đề xuất kiến trúc

~~~mermaid
flowchart TD
    A["PATCH product price"] --> DB[("Primary DB: product v6")]
    DB --> OUT["Transactional outbox: ProductPriceChanged(v6)"]
    OUT --> BUS["Durable events"]
    BUS --> I["Invalidate product/item/list cache"]
    BUS --> S["Update search index"]
    I --> R["Distributed cache eviction/version bump"]
    I --> C["CDN purge item + related tags"]
    S --> IDX[("Search index")]
    B["GET product / search"] --> R
    B --> C
    B --> IDX
    CHECKOUT["Checkout"] --> DB
~~~

**Chú ý:** Sơ đồ diễn đạt các dependency, không có nghĩa một request GET phải đi đồng thời qua Redis, CDN và search index. Thực tế từng endpoint có đường đọc khác nhau. Checkout vẫn phải dùng **giá được kiểm chứng theo quy tắc nghiệp vụ**, không tin tuyệt đối giá trong card search.

### Hợp đồng nhất quán theo endpoint

| Endpoint | Cam kết đề xuất trong tình huống | Cơ chế |
|---|---|---|
| PATCH sản phẩm | 200/204 chỉ sau commit của primary | Transaction, If-Match, response version mới |
| GET item ngay sau PATCH từ người sửa | Read-your-writes nếu API công bố | Đọc primary/bypass cache hoặc cache version-aware |
| GET item cho người dùng khác | Bounded staleness nếu đã kiểm chứng | Evict + purge + TTL dự phòng; đo p99 |
| GET category list | Eventual/bounded staleness theo SLO riêng | Tag/generation/TTL, invalidation theo category |
| GET search | Eventual consistency, hiển thị `asOf`/lag khi cần | Update index async, metric lag, reconciliation |
| Checkout | Tính đúng về giá cuối cùng | Đọc nguồn có thẩm quyền trong transaction/quy trình đặt hàng |

**Không tuyên bố** “giá mọi nơi cập nhật tức thời” chỉ vì ProductPriceChanged đã được publish. Sự kiện có thể trễ, CDN có thể purge chưa xong và search index có thể lag. Phải ghi cụ thể **phạm vi và ngưỡng thời gian**.

### Phân tích một sự cố

Sau cập nhật giá thành công, metric cho thấy:

- Redis item đã được evict.
- CDN purge response lỗi tạm thời.
- Search index xử lý event trễ 25 giây.
- Trang checkout vẫn tính giá mới đúng.

Hệ thống **đúng về giao dịch** nhưng **vi phạm kỳ vọng hiển thị** nếu SLO trang search là 10 giây. Hướng xử lý gồm retry purge có idempotency, cảnh báo purge lag, xử lý DLQ/outbox age, cập nhật SLO và xác minh bản sao tại edge. Không sửa bằng cách để mọi endpoint GET đọc DB primary không giới hạn nếu chưa đánh giá tải và chi phí.

## 16. Kế hoạch kiểm thử tính nhất quán và failure injection

### Ma trận kiểm thử

| Kịch bản | Thao tác | Điều cần chứng minh |
|---|---|---|
| **Update thành công** | Warm cache v5, PATCH commit v6, GET | Không trả v5 ngoài hợp đồng; đúng version |
| **Transaction rollback** | Warm v5, PATCH lỗi, đọc lại | DB vẫn v5; không quảng bá v6 giả |
| **Evict trước commit** | Tạm dừng writer trước commit, GET cache miss | Nhận ra nguy cơ tái điền v5; thiết kế loại bỏ hoặc chấp nhận |
| **Stale fill race** | Reader đọc v5, writer commit/evict, reader SET v5 | Cơ chế version/CAS hoặc hợp đồng giới hạn staleness hoạt động |
| **Nhiều API nodes** | Warm cache ở 2 nodes, ghi qua node A | Node B không trả stale quá giới hạn |
| **Redis/distributed cache lỗi** | Chặn cache trong vài giây | Fallback an toàn, không bypass authorization |
| **CDN purge lỗi** | Giả lập purge trả lỗi | Retry/alert/TTL fallback; đo edge staleness |
| **Outbox relay crash** | Commit DB + outbox, dừng relay trước publish | Event còn tồn, publish lại sau phục hồi |
| **Duplicate event** | Giao ProductChanged v6 hai lần | Eviction/generation xử lý idempotent |
| **Out-of-order event** | Giao v7 trước v6 | Không phục hồi dữ liệu/version cũ |
| **Read replica lag** | Đọc replica chưa có v6 sau cache miss | Read-your-writes không bị vi phạm nếu đã hứa |
| **Conditional GET** | If-None-Match v5 sau ghi v6 | Trả representation v6, không 304 sai |
| **Conditional write** | If-Match v5 khi DB đang v6 | Trả 412, không ghi đè |
| **Private response** | Hai tenant cùng URI nhưng khác quyền | Cache không trộn dữ liệu |
| **Vary/representation variant** | Accept JSON và HAL | Validator, cache key và invalidation đúng từng variant |
| **Search projection lag** | Tắt consumer cập nhật search | Metric/SLO độ trễ cập nhật phản ánh sự cố |

### Test luồng bằng curl

Ví dụ minh họa trên **môi trường thử nghiệm**:

~~~bash
# 1. Đọc representation và validator hiện tại.
curl -i \
  -H 'Authorization: Bearer <test-token>' \
  'https://api.example.test/api/products/42'

# 2. Ghi có điều kiện theo ETag đã nhận.
curl -i -X PATCH \
  -H 'Authorization: Bearer <test-token>' \
  -H 'If-Match: "product-42-v5"' \
  -H 'Content-Type: application/merge-patch+json' \
  --data '{"price":99000}' \
  'https://api.example.test/api/products/42'

# 3. Revalidate bản lưu v5.
curl -i \
  -H 'Authorization: Bearer <test-token>' \
  -H 'If-None-Match: "product-42-v5"' \
  'https://api.example.test/api/products/42'
~~~

Không dùng **production data** để thử thay giá. Lệnh curl không mô phỏng đầy đủ HTTP cache của trình duyệt/CDN; cần test riêng qua đường thật của từng layer, so sánh **ETag, Age, Cache-Control, server/cache hit headers** và giá trị nghiệp vụ.

### Kiểm thử tự động Spring

Với unit/integration test, có thể:

1. Seed product v5 và đọc để warm cache.
2. Thực hiện mutation trong transaction, khẳng định event after-commit chỉ xử lý khi commit.
3. Cố ý tạo rollback và xác minh không publish invalidation như một update thành công.
4. Đọc qua service sau commit và đối chiếu version.
5. Chạy **hai luồng** theo barrier để tái tạo race stale fill.
6. Thử node/cache mô phỏng lỗi và kiểm tra fallback.

**MockMvc chỉ kiểm tra HTTP contract/controller**; nó không tự mô phỏng CDN toàn cầu, read replica lag hay event relay crash. Cần kết hợp integration test, test qua gateway và failure injection.

## 17. Giám sát, SLO và runbook khi phát hiện stale data

### Những metric hữu ích

| Metric | Diễn giải |
|---|---|
| **Cache hit/miss ratio theo endpoint/tầng** | Cơ chế cache có đang giảm tải? |
| **Cache entry age/TTL** | Bản phục vụ có được tính fresh hợp lệ? |
| **Business version mismatch** | Đã đọc v5 sau khi nguồn có v6 hay chưa? |
| **Eviction/purge success và latency** | Mất bao lâu để vô hiệu hóa cache sau commit? |
| **Outbox oldest event age** | Có update bị kẹt chưa gửi? |
| **Invalidation consumer lag/DLQ** | Event nào chưa tới các cache? |
| **Read replica lag** | Dữ liệu nguồn read path đã theo kịp primary chưa? |
| **CDN edge staleness theo POP** | Có vùng edge nào chưa purge? |
| **ETag 304/200 rate** | Revalidation có đúng và tiết kiệm băng thông? |
| **Origin QPS/DB latency sau purge** | Có cache stampede làm quá tải database? |
| **SLO violation của read-after-write** | Người ghi có thấy lại version vừa commit không? |

**Cache hit ratio cao không đồng nghĩa API đúng**. Một cache luôn trả dữ liệu cũ có thể hit 100% nhưng thất bại về tính đúng. Cần có metric **freshness/version** hoặc phép kiểm chứng đối chiếu với nguồn thẩm quyền trên một tập mẫu an toàn.

### Runbook: người dùng phản ánh giá cũ

1. **Xác định phạm vi:** product ID, tenant, người dùng, region/POP, thời gian update, version DB và giá client thấy.
2. **Truy vết mutation:** PATCH đã commit chưa? Response status/version là gì? Có rollback, 409/412 hoặc yêu cầu khác ghi sau?
3. **Kiểm tra đường đọc:** response tới từ browser, CDN, gateway, local cache, Redis hay read replica; đọc `Age`, `ETag`, cache headers và trace.
4. **Đối chiếu version:** DB primary v6, cache nào vẫn v5; search index/materialized view có lag không?
5. **Kiểm tra invalidation:** outbox, broker, consumer, CDN purge logs và retry/DLQ.
6. **Giảm tác động:** bypass/purge đúng keys/tags, phục vụ primary cho endpoint cần đọc mới, tạm giảm TTL theo kế hoạch; không flush toàn Redis/CDN nếu không đánh giá hậu quả.
7. **Xác minh phục hồi:** đọc từ nhiều nodes/regions, tenant/scope và client loại khác nhau; giá/ETag đúng, stale window trong SLO.
8. **Ngăn tái diễn:** bổ sung contract test stale race, alert invalidation lag, ownership cho từng cache và quyết định điều chỉnh kiến trúc.

### Tránh cache stampede sau invalidation

Nếu một sản phẩm rất phổ biến bị purge, hàng nghìn request có thể cùng **cache miss** và đọc DB. Biện pháp thường dùng:

- **Single-flight/request coalescing**: nhiều request cùng key chia sẻ một lần tải.
- **Jitter TTL**: giảm việc hàng loạt key hết hạn đồng thời.
- **Prewarm** cho một số key nóng khi có cơ sở đo lường.
- **Bounded concurrency** tới database/downstream.
- **Serve stale có điều kiện** chỉ với dữ liệu mà nghiệp vụ cho phép, không áp dụng cho giá/quyền/tài chính bắt buộc mới.

Purge càng “nhanh” nhưng thiếu biện pháp bảo vệ origin thì nguy cơ tăng latency và 503 sau purge càng cao.

## 18. Bài tập thực hành và gợi ý lời giải

### Bối cảnh

Một REST API quản lý khóa học có các endpoint:

- **GET /api/courses/{id}**: chi tiết khóa học, cache tại CDN 120 giây và local cache 60 giây.
- **GET /api/courses?category=JAVA&sort=popular**: danh sách, cache 90 giây.
- **GET /api/instructors/{id}/summary**: tổng số khóa học của giảng viên, cache 5 phút.
- **PATCH /api/courses/{id}**: sửa tiêu đề, danh mục hoặc trạng thái công khai.
- **POST /api/courses**: tạo khóa học mới.

API chạy trên **ba instance** phía sau gateway. Dữ liệu nằm ở primary DB và một read replica có thể trễ **3 giây** khi tải cao. Có event bus cho việc đồng bộ search index nhưng hiện chưa có invalidation bền vững.

### Câu hỏi

1. Với PATCH thay **category=JAVA thành category=CLOUD**, hãy liệt kê các cache item, list, summary và search có thể cần invalidation.
2. Giải thích vì sao **HTTP cache invalidation của target URI** chưa đủ để cập nhật các collection và instructor summary.
3. Vẽ **timeline hai luồng** chứng minh race stale fill dù writer evict sau commit.
4. Đề xuất **cache key** cho GET item theo tenant, locale, version; giải thích dữ liệu nào không nên đưa vào key.
5. Đặt hợp đồng **read-your-writes** cho người vừa sửa khóa học; con đường đọc nào phải dùng nếu replica lag?
6. Thiết kế cơ chế event/outbox để ba instance và CDN được invalidation; chỉ rõ rủi ro duplicate/out-of-order.
7. Viết ví dụ **GET có If-None-Match** và **PATCH có If-Match** cùng status 304/412 tương ứng.
8. Đề xuất ít nhất **tám contract/failure tests**, **sáu metrics** và một runbook ngắn khi trang danh sách vẫn hiển thị category cũ.

### Gợi ý lời giải

**Câu 1–2:** Phải xét **GET item**, **list category JAVA**, **list category CLOUD**, summary của giảng viên nếu số liệu liên quan thay đổi, các search result hoặc projection chứa dữ liệu cũ. HTTP cache nhìn thấy PATCH thường chỉ có nghĩa vụ invalidate **target item URI**; nó không biết dependency của mọi trang list/summary khác.

**Câu 3:** Reader lấy giá trị cũ từ DB ở t1, writer commit giá trị mới và evict ở t2, reader điền giá trị cũ vào cache ở t3. Cần versioned key/CAS, điều phối fill hoặc chấp nhận staleness có giới hạn đo được.

**Câu 4:** Ví dụ `course-view:tenant-27:course-42:locale-vi:v8`. Không dùng raw bearer token hoặc secret trong key; phải xét quyền khác nhau trong cùng tenant khi scope có thể khác.

**Câu 5:** Sau PATCH commit v8, GET của chính người sửa phải nhận phiên bản **không cũ hơn v8** nếu API đã hứa read-your-writes. Có thể dùng **primary read** hoặc đường version-aware; replica lag 3 giây không được dùng để phá cam kết đó.

**Câu 6:** Transaction ghi course cùng outbox event có `courseId, tenantId, version, changedFields`; relay publish, consumer idempotent evict Redis/local/generation và purge URL/tag CDN. Có thể retry, DLQ và TTL fallback. Event cũ không được ghi dữ liệu cũ lên key mới.

**Câu 7:** GET gửi `If-None-Match: "course-42-v8"` → 304 nếu representation hiện tại thực sự tương ứng v8, ngược lại 200 với body/ETag mới. PATCH gửi `If-Match: "course-42-v7"` khi source đã ở v8 → 412, không cập nhật.

**Câu 8:** Test commit/rollback, stale fill race, multi-node, CDN purge failure, replica lag, duplicate/out-of-order event, tenant data isolation, list dependency, ETag/304/412, stampede. Metric gồm purge latency, stale version mismatch, outbox lag, cache hit/miss, CDN edge age, replica lag, DB QPS và SLO read-after-write.

### Rubric tự đánh giá

| Năng lực | Điểm | Dấu hiệu đạt |
|---|---:|---|
| HTTP invalidation và Cache-Control | 25 | Hiểu target URI, các tầng cache và freshness |
| Transaction và race condition | 25 | Nêu đúng hai timeline và biện pháp theo mức nhất quán |
| Consistency contract và ETag | 20 | Phân biệt read-your-writes, replica lag, If-Match/If-None-Match |
| Hệ thống phân tán và bảo mật | 15 | Outbox, multi-node, scope/tenant, CDN purge |
| Kiểm thử, SLO và vận hành | 15 | Có test failure, metrics, runbook và cost/risk tradeoffs |

## 19. Checklist đưa chiến lược cache vào production

- [ ] Từng endpoint đã xác định **có cache hay không**, lớp cache, key, TTL và chủ sở hữu.
- [ ] Có **source of truth** và phạm vi nhất quán rõ cho dữ liệu: eventual, bounded stale, read-your-writes hay mạnh hơn.
- [ ] Không hiểu lầm rằng **Cache-Control max-age** bảo đảm dữ liệu còn đúng sau một write.
- [ ] Biết quy tắc RFC 9111 về **HTTP cache invalidation với unsafe methods** và giới hạn của quy tắc theo target URI/cache observer.
- [ ] Có bảng **mutation → affected representations**, gồm item, collection, search, summary và variant.
- [ ] Invalidation không chạy trước commit theo cách làm tăng rủi ro stale; rollback không được quảng bá như thành công.
- [ ] Đã đánh giá race GET điền bản cũ **sau khi evict**, có version/CAS hoặc SLO chấp nhận được.
- [ ] Hệ thống nhiều node có **shared cache hoặc invalidation broadcast đáng tin**, không chỉ xóa local cache một node.
- [ ] Nếu dùng outbox/events, có xử lý duplicate, out-of-order, consumer lag, retry/DLQ và TTL fallback.
- [ ] CDN purge/tag/version phù hợp với năng lực provider, đo thời gian lan truyền và xác minh từ edge.
- [ ] Dữ liệu theo tenant/user/role được phân vùng; không dùng credentials làm cache key; tránh shared-cache leakage.
- [ ] ETag được dùng đúng với representation variants; **If-None-Match** đọc và **If-Match** ghi không bị nhầm.
- [ ] Cache-Control `no-store`, `no-cache`, `private`, `s-maxage`, `stale-while-revalidate` được hiểu đúng ngữ nghĩa.
- [ ] Có test commit/rollback, stale-fill race, multi-node, replica lag, CDN purge error, 304/412 và side effect không rõ kết quả.
- [ ] Có metric về **staleness thực tế** bên cạnh hit ratio, alerts, runbook và giới hạn origin sau purge.
- [ ] Không dùng bản cache eventual-consistent để ra quyết định tài chính, quyền hoặc tồn kho khi nghiệp vụ yêu cầu kết quả mạnh.

**Điểm cần nhớ:** **Vô hiệu hóa cache sau ghi** không phải một lệnh `DEL` đơn lẻ. Đó là một **hợp đồng nhất quán xuyên nhiều tầng**: biết dữ liệu nào phụ thuộc mutation, phối hợp với commit, chống race, truyền invalidation đáng tin, chọn TTL/ETag và kiểm thử giới hạn stale. Một API tốt không chỉ nhanh khi cache hit, mà còn **không đánh lừa client về tính mới và tính đúng của dữ liệu**.

### Tài liệu nền để tra cứu

- **RFC 9110 — HTTP Semantics:** safe/unsafe methods, validators, ETag, If-Match, If-None-Match, 304 và 412.
- **RFC 9111 — HTTP Caching:** freshness, Cache-Control, Vary và invalidation stored responses sau unsafe requests.
- **RFC 5861 — HTTP Cache-Control Extensions for Stale Content:** stale-while-revalidate và stale-if-error.
- **Spring Framework Reference — Caching Abstraction:** CacheManager, @Cacheable, @CacheEvict và giới hạn của cache advice.
- **Spring Framework Reference — Transaction-bound Events:** @TransactionalEventListener và TransactionPhase.AFTER_COMMIT.
- **OpenAPI Specification 3.1:** mô tả headers/response schemas và hợp đồng GET/PATCH.
