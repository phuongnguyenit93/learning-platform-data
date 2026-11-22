# Bộ nhớ đệm tại client, gateway, dịch vụ và tầng dữ liệu trong Microservices

## Mục tiêu học tập

Sau bài này, người học có thể phân biệt vai trò của bộ nhớ đệm (cache) ở client, API gateway/edge, từng microservice và tầng dữ liệu; chọn nơi đặt cache theo đặc điểm dữ liệu và mức độ nhất quán; thiết kế cache key, TTL, cơ chế cập nhật/vô hiệu hóa; nhận diện cache stampede, hot key, stale data và những sai lầm bảo mật; đồng thời dùng metric và load test để đánh giá liệu cache thực sự giảm tải, cải thiện độ trễ và chi phí hay không.

Trong kiến trúc microservices, cache là một **bản sao dữ liệu có vòng đời và tính nhất quán riêng**, không đơn giản là một bộ tăng tốc có thể thêm vào bất cứ đâu. Mỗi tầng cache phục vụ một nhóm truy cập và tạo ra một số rủi ro cần quản lý.

## 1. Nhìn tổng thể: cache có thể nằm ở đâu?

Một request xem chi tiết sản phẩm có thể đi qua nhiều tầng:

~~~text
                Browser / Mobile App
                [Client cache]
                       |
                       v
                CDN / API Gateway
                [Edge / Gateway cache]
                       |
                       v
               Catalog Service
                [L1 local cache]
                       |
                       v
              Redis / Shared Cache
               [L2 distributed]
                       |
                       v
            PostgreSQL / Search Store
         [DB buffer / read model / data cache]
~~~

Đường đi này là một mô hình tham khảo. Không bắt buộc phải triển khai đủ bốn tầng. Một ứng dụng nhỏ có thể chỉ cần HTTP caching và database tốt; hệ thống tải lớn có thể cần thêm CDN và Redis; một dịch vụ cần tính đúng đắn giao dịch cao có thể không cache kết quả trạng thái nhạy cảm.

**Cache hit** là khi dữ liệu được trả về từ cache mà không cần truy vấn tầng phía sau. **Cache miss** xảy ra khi chưa có bản ghi, bản ghi đã hết hạn hoặc cache key không khớp; hệ thống phải lấy dữ liệu từ nguồn tiếp theo và có thể lưu lại để dùng ở lần sau.

Khi có nhiều tầng, request thường trả lời từ tầng gần người dùng nhất còn đáp ứng yêu cầu về độ mới, quyền truy cập và ngữ nghĩa dữ liệu. Ví dụ browser có bản sao còn hạn thì không gọi gateway; browser miss nhưng CDN hit thì không gọi Catalog Service; Redis hit có thể tránh truy vấn PostgreSQL.

Điều cần nhớ: **tăng hit ratio không phải mục tiêu tự thân**. Một cache hit trả dữ liệu sai hoặc dữ liệu của người khác còn tệ hơn cache miss. Quyết định cuối cần dựa trên độ trễ p95/p99, thông lượng thành công, chi phí, mức tiêu thụ tài nguyên và tính đúng đắn của nghiệp vụ.

## 2. Tại sao mỗi microservice cần chiến lược cache khác nhau?

Microservices khác nhau về lưu lượng, quyền sở hữu dữ liệu và yêu cầu nhất quán:

| Dịch vụ | Dữ liệu | Tần suất thay đổi | Hướng cache có thể phù hợp |
| --- | --- | --- | --- |
| Catalog | Mô tả sản phẩm, ảnh, danh mục | Thấp đến trung bình | Browser, CDN, gateway, local/Redis |
| Search | Danh sách kết quả theo bộ lọc | Trung bình, key đa dạng | CDN có chọn lọc hoặc service cache với TTL ngắn |
| Pricing | Giá, chương trình khuyến mãi | Có thể thay đổi theo thời điểm/khách hàng | Cache theo phiên bản chính sách, tenant và thời hạn ngắn |
| Inventory | Tồn kho khả dụng | Cao, cạnh tranh ghi | Cache để hiển thị có ghi chú độ mới; kiểm tra chính xác tại bước đặt hàng |
| Identity | Quyền và trạng thái phiên | Nhạy cảm bảo mật | Cache có giới hạn rất chặt; hỗ trợ thu hồi/invalidation |
| Order | Trạng thái đơn theo người dùng | Cao, yêu cầu đúng quyền | Cache riêng theo phạm vi quyền và vòng đời trạng thái |
| Reporting | Bản tổng hợp lịch sử | Theo lô hoặc theo kỳ | Cache kết quả tính toán/read model, TTL dài theo phiên bản |

Dịch vụ sở hữu dữ liệu chịu trách nhiệm định nghĩa **dữ liệu nào được cache và ý nghĩa độ mới**. Dịch vụ gọi không nên tự quyết rằng trạng thái Inventory từ năm phút trước vẫn đủ để xác nhận một đơn hàng có hàng. Với dữ liệu cá nhân và tài khoản, phải thiết kế chống lộ cache giữa các người dùng.

### Phân biệt latency và freshness

Giả sử truy vấn gốc có p95 = 150 ms, cache hit thường trả trong 5 ms và hit ratio là 80%. Thời gian trung bình có thể giảm đáng kể; nhưng p95 của toàn luồng không chắc chỉ còn 5 ms, vì 20% request miss vẫn có thể nằm ở phần đuôi. Nếu miss đồng loạt, database còn có thể chậm hơn trước.

Độ mới (freshness) là khoảng trễ giữa trạng thái nguồn và bản sao cache. Một cache có thời hạn 60 giây có thể trả bản cũ trong khoảng đó, trừ khi có invalidation/refresh trước. Cần xác định dữ liệu chịu được sự trễ này hay không, thay vì dùng TTL theo cảm tính.

## 3. Client cache: gần người dùng nhất

Client cache là dữ liệu được giữ tại browser, mobile app hoặc ứng dụng desktop. Nó có thể là HTTP cache do trình duyệt quản lý, dữ liệu trong memory, service worker/Cache Storage, local database hoặc bộ nhớ ứng dụng.

Lợi ích:
- Không cần network round trip cho dữ liệu còn dùng được.
- Giảm số request đến gateway và backend.
- Cải thiện trải nghiệm khi mạng yếu, di chuyển hoặc offline.
- Giảm tiêu thụ băng thông cho ảnh, font, JavaScript và dữ liệu ít thay đổi.

Rủi ro:
- Dữ liệu cũ có thể tồn tại sau khi backend đổi.
- Dữ liệu cá nhân có thể bị lưu trên thiết bị dùng chung hoặc ngoài thời hạn mong muốn.
- Mỗi client có vòng đời khác nhau; server khó đảm bảo xóa tức thời mọi bản đã lưu.
- Khi người dùng đăng xuất hoặc đổi tài khoản, cache không được làm hiển thị dữ liệu của phiên trước.

### HTTP cache trong trình duyệt

Một phản hồi GET có thể đi kèm:

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=300
ETag: "product-42-v7"
Content-Type: application/json
~~~

Nếu tài nguyên được cache và còn fresh trong 300 giây, browser có thể dùng bản lưu theo chính sách HTTP. Khi cần xác nhận lại, client gửi:

~~~http
GET /api/products/42 HTTP/1.1
If-None-Match: "product-42-v7"
~~~

Nếu representation chưa thay đổi, server có thể trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "product-42-v7"
Cache-Control: public, max-age=300
~~~

**304 Not Modified** giúp không tải lại toàn bộ body, nhưng vẫn cần một lượt giao tiếp với server khi revalidation. ETag không đồng nghĩa với việc dữ liệu luôn chính xác; cách tạo ETag phải phản ánh representation thực tế, bao gồm phiên bản, ngôn ngữ và những yếu tố làm thay đổi nội dung.

Một số chỉ dẫn Cache-Control thường gặp:

| Chỉ dẫn | Ý nghĩa cơ bản |
| --- | --- |
| public | Cho phép shared cache lưu khi các điều kiện HTTP khác cho phép |
| private | Chỉ phù hợp cho cache riêng, không cho shared cache lưu |
| no-store | Không lưu phản hồi trong cache HTTP |
| no-cache | Có thể lưu nhưng phải revalidate trước khi sử dụng lại |
| max-age=N | Thời gian fresh theo giây đối với cache áp dụng |
| s-maxage=N | Freshness dành cho shared cache, thường ở CDN/proxy |
| must-revalidate | Khi stale, cache phải xác thực lại theo ngữ nghĩa HTTP |
| stale-while-revalidate=N | Có thể dùng tạm bản stale trong cửa sổ cho phép khi đang revalidate |

Ví dụ response chứa thông tin tài khoản hoặc số dư nhạy cảm thường nên có chính sách chặt như:

~~~http
Cache-Control: private, no-store
~~~

Không coi private là lớp bảo mật độc lập. Xác thực, ủy quyền, mã hóa transport và chính sách lưu dữ liệu của client vẫn cần thực hiện đầy đủ.

### Cache dữ liệu trong SPA hoặc mobile app

Bên cạnh HTTP cache, frontend thường dùng cache dữ liệu theo truy vấn để giảm request trùng, kết hợp stale time, refetch khi quay lại màn hình, mutation invalidation và optimistic update.

Ví dụ màn hình Product Detail dùng key phân biệt:

~~~text
product-detail / product-id=42 / locale=vi-VN / currency=VND
~~~

Nếu cùng dữ liệu được hiển thị trên nhiều màn hình, có thể tái sử dụng một bản lưu cục bộ. Khi người dùng sửa sản phẩm qua một mutation được phép, phải invalidate hoặc cập nhật những truy vấn liên quan. Với dữ liệu theo tài khoản, cache key và vòng đời cần gắn với identity/scope; lúc logout hoặc chuyển account phải dọn cache phù hợp.

Dữ liệu trong localStorage hoặc IndexedDB tồn tại qua phiên làm việc; chỉ nên lưu khi thật sự cần và đã đánh giá rủi ro. Không lưu access token hoặc dữ liệu bí mật trong cache một cách tùy tiện.

## 4. Gateway và edge cache: chia sẻ kết quả cho nhiều client

CDN, reverse proxy hoặc API gateway có thể cache response trước khi request đến microservice. Đây là nơi phù hợp cho các GET có cùng representation cho nhiều người dùng.

Ví dụ:

~~~text
                 100.000 client GET /products/42
                              |
                              v
                       CDN / Gateway
                        cache hit 95%
                              |
                         cache miss
                              v
                         Catalog API
                              |
                              v
                           Database
~~~

Nếu response có thể dùng chung an toàn, edge cache giảm lượng request xuyên mạng vào cụm và giúp bảo vệ hệ thống khi lưu lượng đột biến.

Những loại nội dung thường phù hợp:
- Ảnh sản phẩm, logo, CSS/JS/font với tên asset có fingerprint.
- Mô tả và danh mục sản phẩm công khai ít thay đổi.
- Thông tin cấu hình công khai hoặc dữ liệu tra cứu có cùng kết quả cho mọi client.
- API GET có payload, TTL, quyền truy cập và cache key rõ ràng.

### Cache key tại gateway

Không thể chỉ dùng path làm cache key nếu kết quả còn phụ thuộc query, ngôn ngữ, currency, tenant hoặc người dùng. Hai truy vấn sau có thể cần hai bản cache khác nhau:

~~~text
GET /products?category=books&sort=price&currency=VND
GET /products?category=books&sort=price&currency=USD
~~~

Một key hợp lệ cần bao gồm mọi phần đầu vào ảnh hưởng đến response: HTTP method/host/path, query parameters sau khi chuẩn hóa, header quan trọng, locale, phiên bản API, tenant và scope quyền nếu response được phép cache theo scope đó. Hệ thống CDN/gateway cụ thể có quy tắc cache key riêng, nên phải cấu hình và kiểm thử thực tế.

Header **Vary** thông báo cho cache HTTP những request header liên quan đến việc chọn representation:

~~~http
Vary: Accept-Language, Accept-Encoding
~~~

Tuy nhiên, chỉ thêm Vary không đảm bảo an toàn cho API có Authorization. Với dữ liệu đăng nhập, lựa chọn bảo thủ thường là **bỏ qua shared cache**. Nếu cần cache có xác thực, phải có thiết kế riêng về phân vùng theo identity, tenant, policy và invalidation; không dựa vào một đường URL chung.

### TTL và purge ở edge

CDN có thể dùng TTL dài hơn browser để giảm tải backend, kết hợp purge theo URL/tag hoặc thay đổi URL theo phiên bản nội dung. Ví dụ ảnh có tên chứa hash nội dung có thể dùng thời hạn cache dài, vì thay đổi ảnh sẽ tạo một URL mới. Với giá sản phẩm đổi liên tục, TTL cần ngắn hơn hoặc dùng invalidation sự kiện theo chính sách.

Một lệnh purge không nhất thiết xóa đồng thời mọi cache client, proxy trung gian và local cache. Phải biết hệ thống nào thực sự nhận và xác nhận purge. Khi có yêu cầu thu hồi dữ liệu khẩn cấp, thiết kế không được phụ thuộc hoàn toàn vào TTL dài ở những lớp không kiểm soát được.

## 5. Cache tại từng microservice: giảm truy vấn lặp

Trong backend, service có thể cache kết quả truy vấn, cấu hình, dữ liệu tham chiếu hoặc kết quả tính toán tốn CPU. Có hai dạng chính:

**Local cache (L1):** nằm trong RAM của từng instance, ví dụ Caffeine. Truy cập rất nhanh, không phát sinh network hop. Mỗi pod có bản sao riêng, nên dễ lệch dữ liệu sau cập nhật và tốn thêm RAM khi scale nhiều replica.

**Distributed cache (L2):** nằm ở dịch vụ dùng chung như Redis. Nhiều instance truy cập chung một cache key, hỗ trợ điều phối TTL và invalidation tập trung. Đổi lại có thêm network I/O, serialization, quota bộ nhớ, kết nối và failure mode của một dependency mới.

| Tiêu chí | Local cache | Distributed cache |
| --- | --- | --- |
| Độ trễ truy cập | Rất thấp, trong tiến trình | Có network hop và serialization |
| Chia sẻ giữa pod | Không tự động | Có, nếu cùng cluster/key namespace |
| Quản lý bộ nhớ | Tiêu thụ RAM từng pod | Tiêu thụ RAM trên cache cluster |
| Invalidation | Mỗi pod phải nhận hoặc tự hết TTL | Có thể xóa chung một entry |
| Ảnh hưởng khi cache lỗi | Thường mất dữ liệu cache cục bộ | Có thể tạo dependency outage và miss storm |
| Dữ liệu phù hợp | Tham chiếu nhỏ, TTL ngắn, immutable | Dữ liệu dùng chung, kết quả tra cứu lặp, TTL kiểm soát |

**Không phải cứ nhiều pod là bắt buộc dùng Redis.** Với dữ liệu tham chiếu ít thay đổi, local cache TTL ngắn có thể đủ. Ngược lại, một cache Redis tập trung chưa chắc nhanh hơn cách tối ưu truy vấn SQL hoặc dùng database buffer cache cho truy vấn đã có index tốt.

### Cache nhiều tầng L1 + L2

Một số hệ thống dùng:

~~~text
Service Pod A -> L1 local cache --+
                                  |
Service Pod B -> L1 local cache --+--> L2 Redis --> Database
                                  |
Service Pod C -> L1 local cache --+
~~~

L1 giúp giảm số lượt gọi Redis; L2 giúp giảm tải database và chia sẻ data giữa pod. Cái giá phải trả là **hai tầng có thể stale khác nhau**. Nếu xóa key ở Redis nhưng không xóa local cache của Pod B, Pod B vẫn có thể trả dữ liệu cũ.

Có thể dùng TTL L1 ngắn, thông báo invalidation theo sự kiện, versioned key hoặc đọc theo version. Không xem Redis Pub/Sub đơn thuần là kênh sự kiện bền vững: subscriber mất kết nối có thể bỏ lỡ thông báo; cần fallback TTL hoặc cơ chế đồng bộ đáng tin hơn cho dữ liệu nhạy cảm.

## 6. Cache ở tầng dữ liệu: phân biệt những khái niệm dễ nhầm

Cụm từ “database cache” có thể chỉ nhiều cơ chế khác nhau:

1. **Buffer pool/page cache của DB:** hệ quản trị giữ các trang dữ liệu/index trong RAM để giảm đọc disk. Ứng dụng thường không tự quyết cache key của tầng này.
2. **Prepared statement/plan cache:** tái sử dụng kế hoạch hoặc cấu trúc thực thi SQL, tùy DB/driver. Nó khác với cache kết quả truy vấn.
3. **Result cache hoặc materialized view:** lưu kết quả tính toán/truy vấn theo cơ chế hệ quản trị hoặc job cập nhật. Có thể cần refresh và có sự trễ dữ liệu.
4. **Read model chuyên dụng:** CQRS projection, search index hoặc bảng tổng hợp để phục vụ mẫu truy vấn cụ thể. Đây là một bản sao dữ liệu có pipeline đồng bộ, không đơn giản là một hashmap cache.
5. **Redis/Key-value cache đặt gần database:** tuy đứng ở tầng dữ liệu trong sơ đồ, nó vẫn là một hệ thống cache độc lập có TTL, eviction và chính sách điều hành riêng.

Ví dụ một truy vấn SELECT đã sử dụng index tốt và dữ liệu nằm trong DB buffer cache có thể đủ nhanh. Thêm Redis làm tăng chi phí duy trì phiên bản và lỗi phân tán mà không cải thiện đáng kể SLO. Ngược lại, một truy vấn tổng hợp nhiều bảng nặng có thể nên chuyển sang materialized view hoặc read model thay vì cache toàn bộ output với key có hàng triệu biến thể.

### Read replica không phải cache hoàn toàn tương đương

Read replica giúp phân phối tải đọc nhưng thường có replication lag. Sau khi ghi vào primary, đọc từ replica có thể trả dữ liệu chưa được đồng bộ. Phải định nghĩa rõ đường đọc yêu cầu read-after-write và mức trễ chấp nhận được. Replica là một thành phần storage có trạng thái, không chỉ là entry cache có thể tùy ý xóa.

## 7. Bốn kiểu phổ biến để đọc và ghi cache

### 7.1 Cache-aside (lazy loading)

Ứng dụng kiểm tra cache trước. Khi miss, truy vấn database rồi lưu kết quả:

~~~text
GET product(id)
    |
    v
cache.get(key) ------ hit -----> return
    |
   miss
    v
database.select(id)
    |
    v
cache.set(key, value, ttl)
    |
    v
return
~~~

Pseudocode:

~~~java
Product getProduct(String id) {
    String key = "catalog:product:v2:" + id;
    Product cached = cache.get(key);
    if (cached != null) return cached;

    Product product = repository.findById(id);
    if (product != null) cache.put(key, product, Duration.ofSeconds(60));
    return product;
}
~~~

Ưu điểm: đơn giản, chỉ cache những dữ liệu thực sự được truy cập. Nhược điểm: miss chậm; dữ liệu có thể stale sau khi cập nhật; nhiều miss đồng thời có thể cùng đánh vào DB. Thực tế cần cơ chế serialization, timeout và xử lý cache unavailable phù hợp.

### 7.2 Read-through

Ứng dụng yêu cầu dữ liệu từ cache abstraction; cache tự gọi loader khi miss. Cách này tập trung logic đọc, nhưng phải thiết kế loader, TTL, xử lý lỗi và hành vi khi backing store chậm. Đừng giả định mọi thư viện đều có read-through tương tự nhau.

### 7.3 Write-through

Khi ghi, tầng cache phối hợp cập nhật backing store và cache trước khi xác nhận. Có thể giảm khả năng đọc bản cũ từ cache nhưng khiến đường ghi phức tạp và thêm độ trễ. Cần xác định rõ thành phần nào giữ transaction, chuyện gì xảy ra nếu DB thành công nhưng cache thất bại, và thứ tự quan sát của các reader.

### 7.4 Write-behind / write-back

Cache nhận thay đổi trước, đồng bộ về database sau. Cách này có thể làm write latency thấp nhưng tiềm ẩn mất dữ liệu nếu cache/queue chưa durable hoặc crash. Với thanh toán, tồn kho hay sổ cái, không dùng write-behind như thể nó mặc nhiên có cùng độ bền với transaction database.

| Chiến lược | Đặc điểm | Rủi ro chính |
| --- | --- | --- |
| Cache-aside | App quản lý miss và invalidation | Stale và stampede |
| Read-through | Cache abstraction quản lý loader | Loader/timeout bị ẩn và miss đồng loạt |
| Write-through | Ghi theo đường phối hợp DB/cache | Dual-write và độ trễ ghi |
| Write-behind | Ghi cache trước, DB sau | Mất cập nhật khi lỗi và khó bảo toàn thứ tự |

Một hệ thống thường pha trộn chiến lược theo nhóm dữ liệu, không cần áp đặt cùng một kiểu cho mọi service.

## 8. Thiết kế cache key đúng ngữ nghĩa

**Cache key** phải xác định chính xác representation của dữ liệu. Nếu hai request đáng lẽ ra kết quả khác nhau mà dùng cùng key, đó là lỗi tính đúng đắn hoặc rò rỉ dữ liệu.

Ví dụ product detail:

~~~text
catalog:product:v3:tenant-7:product-42:locale-vi:currency-VND
~~~

Các thành phần có thể gồm:
- **Namespace:** catalog:product để không trùng với dữ liệu khác.
- **Schema/version:** v3 giúp phân biệt serialization hoặc semantics khi deploy.
- **Tenant/identity/scope:** nếu nội dung thay đổi theo quyền truy cập.
- **Entity ID:** khóa định danh dữ liệu chuẩn.
- **Locale/currency/device variant:** nếu ảnh hưởng đến response.
- **Query params:** được chuẩn hóa để tránh các key trùng nghĩa hoặc dùng nhầm kết quả.

Không bỏ sót tenant trong cache của hệ thống đa khách hàng. Không đưa nguyên token truy cập, mật khẩu, dữ liệu bí mật hoặc URL chứa thông tin nhạy cảm vào key/logs. Nếu scope người dùng có cardinality rất cao, cân nhắc có nên cache theo user hay chuyển sang dữ liệu dùng chung kết hợp bước kiểm tra quyền khi trả response.

### Vấn đề số lượng key

Một API search nhận hàng chục bộ lọc có thể tạo số tổ hợp gần như vô hạn. Nếu cache mỗi request với TTL dài, cache nhanh đầy dù hit ratio thấp. Cân nhắc giới hạn tập query được cache, chuẩn hóa tham số, chỉ cache các truy vấn phổ biến, đặt max entries, giới hạn kích thước value và xem xét chi phí bộ nhớ.

Ví dụ query string có thứ tự khác nhau nhưng ý nghĩa giống nhau phải được canonicalize trước khi tạo key, nếu tầng cache cho phép:

~~~text
?category=book&sort=price
?sort=price&category=book
~~~

Canonicalization phải hiểu ngữ nghĩa tham số, không tùy ý đổi thứ tự mảng có ý nghĩa như nhiều mức sắp xếp.

## 9. TTL, freshness và ba chiến lược invalidation

Không có TTL đúng cho mọi loại dữ liệu. TTL nên xuất phát từ **mức độ stale có thể chấp nhận** và **chi phí truy vấn nguồn**:

| Dữ liệu | TTL minh họa | Ghi chú |
| --- | --- | --- |
| Ảnh/static asset có content hash | Dài: giờ đến tháng | Đổi tên asset khi nội dung đổi |
| Mô tả sản phẩm công khai | Phút | Có thể purge khi cập nhật |
| Bảng mã quốc gia/ngôn ngữ | Giờ hoặc ngày | Cân nhắc versioned key |
| Giá theo khuyến mãi | Giây đến phút | Giá xác nhận đơn phải kiểm tra nguồn chuẩn |
| Tồn kho hiển thị | Rất ngắn hoặc theo event | Checkout không được tin một bản cache cũ |
| Số dư và quyền truy cập | Thường bỏ qua shared cache | Ưu tiên chính xác, thu hồi quyền và bảo mật |

Đây chỉ là phạm vi ví dụ để học cách lựa chọn; phải chốt TTL theo SLO, yêu cầu nghiệp vụ và dữ liệu đo thực tế.

**Time-based expiration:** entry hết hạn sau TTL. Đơn giản và tự phục hồi khỏi invalidation bị bỏ lỡ, nhưng luôn có một cửa sổ stale.

**Event-based invalidation:** sau khi nguồn chuẩn thay đổi, phát event hoặc xóa key. Cải thiện freshness nhưng event có thể trễ, bị gửi lặp hoặc bị bỏ lỡ, nhất là qua nhiều dịch vụ.

**Versioned cache key:** gắn phiên bản entity/schema/policy vào key. Khi dữ liệu đổi version, reader dùng key mới; bản cũ tự hết TTL hoặc bị dọn. Phải có cách xác định version hiện hành không gây truy vấn tốn kém hơn cache mang lại.

### TTL jitter và thời hạn hết hạn đồng loạt

Nếu một triệu entry được tạo cùng lúc với TTL 300 giây, chúng có thể hết hạn cùng thời điểm và đẩy tải lớn lên database. Jitter tạo độ lệch ngẫu nhiên có kiểm soát quanh TTL, ví dụ từ 240 đến 360 giây với dữ liệu cho phép. Không áp dụng jitter vượt mức stale tối đa được phép.

### Stale-while-revalidate

Cho phép tạm trả dữ liệu cũ trong một cửa sổ ngắn khi một tiến trình làm mới ở phía sau. Cách này hữu ích cho catalog công khai và dashboard không đòi chính xác tức thời. Với kiểm tra thanh toán, quyền truy cập hoặc cam kết tồn kho, stale-while-revalidate có thể không chấp nhận được.

## 10. Cache invalidation khi có thao tác ghi

Một pattern phổ biến của cache-aside:

~~~text
UPDATE product
   |
   v
COMMIT database
   |
   v
INVALIDATE product cache
   |
   v
Các lần đọc sau tải lại dữ liệu mới
~~~

Cần đặc biệt chú ý **thời điểm commit**. Nếu xóa cache trước khi transaction ghi dữ liệu commit, một request khác có thể miss, đọc lại giá trị cũ từ database, rồi nạp bản cũ vào cache sau đó. Vì vậy, có thể dùng callback/event sau commit của transaction hoặc một cơ chế outbox/consumer để phát invalidation đúng lúc.

### Race condition khi đọc và ghi

Một kịch bản vẫn có thể xảy ra ngay cả khi writer xóa cache sau commit:

~~~text
T1  Request A cache miss, bắt đầu SELECT old-value
T2  Request B cập nhật new-value và COMMIT
T3  Request B xóa cache key
T4  Request A hoàn thành SELECT old-value và SET cache
T5  Request C cache hit old-value
~~~

Đây là lý do “ghi DB xong thì DELETE key” vẫn chưa hoàn toàn loại bỏ stale trong môi trường concurrency. Biện pháp tùy tính chất dữ liệu: TTL ngắn; versioned key; conditional set với version/timestamp; per-key synchronization; cơ chế invalidate lại; hoặc đọc trực tiếp nguồn chuẩn cho quyết định quan trọng.

Với dữ liệu theo entity version, cache payload có thể chứa version. Một writer hoặc loader cần ngăn bản version thấp thay thế bản version cao ở cache, bằng compare-and-set hoặc định danh version trong key. Đừng chỉ dùng timestamp từ đồng hồ của nhiều máy nếu không có đồng bộ/ordering phù hợp.

### Invalidation xuyên nhiều instance và nhiều dịch vụ

Một update tại Catalog Pod A chỉ xóa local cache của Pod A. Pod B/C vẫn có thể giữ bản cũ. Có thể chọn:
- Local cache TTL ngắn nên chấp nhận trễ đến hết TTL.
- Publish invalidation event để mọi pod xóa entry liên quan.
- Lưu cache trên Redis dùng chung để xóa một key có hiệu lực với các pod đang đọc Redis.
- Thêm versioned key để reader không chọn bản cũ.
- Dùng outbox và durable event khi mất một thông báo có thể gây hậu quả lớn.

Không được giả định event delivery luôn đúng một lần hoặc theo thứ tự. Các consumer nên idempotent; cần định nghĩa hành vi khi event trễ, duplicate hoặc out of order. Nếu một service nhận bản sao dữ liệu từ service khác, phải nhớ rằng cache trong service nhận không trở thành nguồn chuẩn cho dữ liệu đó.

## 11. Cache stampede và miss đồng loạt

**Cache stampede** xảy ra khi nhiều request cùng miss một key phổ biến và đồng thời truy vấn nguồn. Nó thường xuất hiện khi:
- Cache cold sau deploy/restart.
- Hot key hết TTL cùng lúc.
- Redis mất dữ liệu hoặc eviction hàng loạt.
- Một chiến dịch marketing làm traffic đột ngột tập trung vào một sản phẩm.
- Tất cả pod khởi động với local cache trống.

~~~text
                  10.000 request cùng cache miss
                     /     |      \
                    v      v       v
               Service A  B ...   Service N
                     \     |      /
                        Database
                    (sudden surge)
~~~

Cơ chế giảm stampede:
1. **Request coalescing/singleflight:** trong một process, nhiều request cùng key chỉ có một loader, các request còn lại đợi kết quả.
2. **Distributed lock khi phù hợp:** một worker làm mới trên toàn cụm; cần timeout và fallback khi lock owner chết.
3. **Stale-while-revalidate:** dùng bản cũ trong khi làm mới nếu nghiệp vụ cho phép.
4. **TTL jitter:** tránh nhiều key hết hạn cùng lúc.
5. **Pre-warming có chọn lọc:** làm nóng một vài key nóng sau deploy trước khi traffic tăng.
6. **Rate limit và bounded concurrency:** giới hạn số miss được phép đẩy xuống DB.
7. **Circuit breaker/backpressure:** giữ hệ thống không sụp khi cache và nguồn cùng chịu lỗi.

Không làm warm-up bằng cách tải toàn bộ database vào RAM nếu đa số key không bao giờ được sử dụng. Cần đo hot-key distribution và lượng bộ nhớ có thể cấp.

## 12. Cache penetration và negative caching

**Cache penetration** là lưu lượng truy vấn key không tồn tại hoặc không hợp lệ, dẫn tới miss liên tục và truy vấn database. Ví dụ bot gửi hàng triệu product ID ngẫu nhiên.

Có thể giảm bằng:
- Kiểm tra format ID, quyền và giới hạn tốc độ trước khi truy vấn.
- Cache kết quả “không tìm thấy” với TTL rất ngắn cho những truy vấn đã xác thực hợp lệ.
- Cấu trúc hỗ trợ lọc nhanh khi thực sự cần, với chi phí và false positive được hiểu rõ.
- Observability riêng cho miss do ID không tồn tại.

**Negative caching** phải phân biệt “thực sự không tồn tại” với “dependency timeout” hoặc “chưa được phép truy cập”. Không cache một lỗi 403 của User A rồi trả cho User B theo một key dùng chung. Không cache lỗi 500 do hệ thống tạm thời mà biến nó thành kết luận “sản phẩm không tồn tại”.

Negative cache có thể gây stale khi một entity được tạo ngay sau lần miss; vì vậy TTL thường ngắn và cần invalidation khi tạo entity nếu độ mới là quan trọng.

## 13. Cache eviction và giới hạn tài nguyên

Cache có dung lượng hữu hạn. Các policy thường gặp gồm:
- **TTL/expire-after-write:** bản ghi hết hạn sau khoảng thời gian từ khi ghi.
- **Expire-after-access:** bản ghi ít được sử dụng sẽ rời cache sau khoảng thời gian không truy cập; dễ kéo dài tuổi bản cũ nếu không kết hợp policy freshness.
- **LRU/LFU hoặc các biến thể:** loại bỏ theo mức sử dụng gần đây hoặc tần suất.
- **Maximum size/weight:** giới hạn số entry hoặc trọng số bộ nhớ.
- **Memory pressure eviction:** Redis hoặc các cache server có chính sách evict theo bộ nhớ khi đạt ngưỡng.

Eviction và expiration khác nhau: entry bị evict vì thiếu chỗ không có nghĩa dữ liệu đã cũ; entry hết TTL có thể bị loại dù cache còn dư RAM. Cần theo dõi từng nguyên nhân.

Với local cache trên JVM, cache quá lớn có thể tạo áp lực heap, GC pause hoặc OOM; cần chọn maximumSize/maximumWeight theo kích thước dữ liệu thật. Với Redis, không chỉ tính tổng payload mà còn tính overhead key, metadata, serialization, replication và fragmentation.

Nếu cache key vô hạn theo query/tenant/user, một số key nóng có thể bị loại bởi lượng lớn key hiếm truy cập; cân nhắc phân chia namespace/quota và chính sách admission.

## 14. Ví dụ Spring Boot: cache tại service bằng Caffeine

Ví dụ Catalog Service dùng Spring Cache abstraction kết hợp Caffeine, phù hợp với dữ liệu sản phẩm được đọc nhiều và có thể chấp nhận stale trong thời hạn ngắn.

Các dependency cần có trong dự án gồm Spring Boot starter cache và thư viện Caffeine tương thích:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

Cấu hình một cache cục bộ giới hạn dung lượng và TTL:

~~~java
@Configuration
@EnableCaching
public class CacheConfiguration {

    @Bean
    public CaffeineCacheManager cacheManager() {
        CaffeineCacheManager manager =
            new CaffeineCacheManager("catalogProduct");

        manager.setCaffeine(Caffeine.newBuilder()
            .maximumSize(10_000)
            .expireAfterWrite(Duration.ofSeconds(60)));

        return manager;
    }
}
~~~

Service đọc:

~~~java
@Service
public class ProductQueryService {
    private final ProductRepository repository;

    public ProductQueryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(
        cacheNames = "catalogProduct",
        key = "#id",
        unless = "#result == null"
    )
    public ProductView findById(Long id) {
        return repository.findViewById(id)
            .orElse(null);
    }
}
~~~

Mã trên minh họa quy tắc đọc. Các class ProductView và ProductRepository phải do ứng dụng cung cấp. Cache key chỉ dùng ID nếu dữ liệu được trả về không phụ thuộc tenant, locale hoặc quyền; trong hệ đa tenant phải đưa context cần thiết vào key và kiểm tra ủy quyền trước khi trả dữ liệu.

Spring Cache thường dùng proxy để intercept method; lời gọi từ một method tới method @Cacheable khác **trên cùng instance** có thể không đi qua proxy và không kích hoạt caching. Nếu logic cập nhật cần xóa cache, không nên chỉ nghĩ đến đặt @CacheEvict trong một method bất kỳ: phải xét thời điểm commit, gọi qua proxy và việc xóa local cache trên các pod khác.

Ví dụ hướng tiếp cận cập nhật:

~~~text
@Transactional
ProductService.updateProduct(...)
    -> Update database
    -> Commit transaction
    -> After-commit handler invalidates cache key
    -> Broadcast invalidation / version update nếu nhiều pod
~~~

Cần đặt một lớp xử lý after-commit phù hợp với transaction manager hiện có. Với Redis, có thể dùng RedisCacheManager qua Spring Cache abstraction để thay cache local, nhưng serialization, TTL, key prefix, cluster failures và metrics vẫn cần được cấu hình theo môi trường thực.

## 15. Một thiết kế cache nhiều tầng cho Catalog API

Giả sử Product Catalog có API GET /products/{id} và thuộc tính: tên, mô tả, hình ảnh, nhóm hàng. Giá khuyến mãi và tồn kho được cung cấp bởi các dịch vụ khác hoặc có quy tắc cập nhật riêng.

Thiết kế minh họa:

~~~text
Browser:
  Cache ảnh/versioned asset dài hạn
  Product detail cache ngắn theo HTTP header

Gateway/CDN:
  GET public product detail: cache 30–120 giây
  Key gồm host, path, locale, currency, API version
  Không cache phản hồi chứa dữ liệu theo user

Catalog Service:
  L1 Caffeine: 15–30 giây cho metadata phổ biến
  L2 Redis: 2–5 phút cho dữ liệu ít thay đổi
  Lấy dữ liệu chuẩn từ Catalog DB khi miss

Catalog DB:
  Index truy vấn product ID
  Buffer pool giữ dữ liệu/index nóng
~~~

Đây là các khoảng TTL minh họa để trình bày cách phân tầng; TTL thật phải xác định qua độ mới cho phép và chi phí miss. Đặc biệt, một response gateway có TTL 120 giây không thể được làm mới ngay chỉ vì local cache 15 giây đã hết. **Thời hạn stale mà người dùng có thể thấy được quyết định bởi các tầng có khả năng giữ bản cũ, không chỉ TTL của tầng thấp nhất.**

Khi quản trị viên sửa mô tả sản phẩm:
1. Catalog Service validate và commit thay đổi trong nguồn chuẩn.
2. Sau commit, invalidation/version event được tạo theo cơ chế đáng tin cậy.
3. Local caches và Redis xóa/version bump các key liên quan.
4. Gateway/CDN purge hoặc đợi TTL theo chính sách đã cam kết.
5. Frontend revalidate/cache invalidation nếu vừa thực hiện thao tác sửa và cần hiển thị ngay.

Không có bảo đảm rằng mọi cache bị xóa nguyên tử cùng một lúc. Nếu yêu cầu pháp lý hoặc quyền truy cập đòi thu hồi dữ liệu tức thời, nên tránh các cache không hỗ trợ bảo đảm đó, hoặc thiết kế kiểm soát quyền ở bước trả dữ liệu thay vì dựa vào purge.

## 16. Price và Inventory: ví dụ vì sao cache không thay nguồn chuẩn

Ở màn hình sản phẩm, tồn kho trong Redis có thể ghi “còn 5 chiếc” nhưng trong vài mili giây đã có người đặt hết. UI có thể hiển thị một giá trị gần đúng; **xác nhận đặt hàng phải kiểm tra tồn kho với transaction/điều kiện cạnh tranh phù hợp tại nguồn chuẩn**.

Ví dụ giả định inventory trong PostgreSQL:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE product_id = :product_id
  AND available >= :quantity;
~~~

Kết quả số dòng được cập nhật phải được kiểm tra. Khi đồng thời nhiều request giảm cùng sản phẩm, điều kiện SQL này giúp không trừ quá mức trong ví dụ một row. Trong kiến trúc có nhiều kho, đặt trước hàng, event hoặc transaction khác, cần thiết kế nhất quán rộng hơn.

Tương tự, giá hiển thị có thể được cache nhưng giá cuối cùng tại checkout cần được tính hoặc xác nhận theo chính sách đã định: thời điểm khóa giá, phiên bản khuyến mãi, currency, thuế và quyền hưởng ưu đãi. Không dùng giá cache cũ làm căn cứ tính tiền nếu nghiệp vụ yêu cầu giá cập nhật.

Một cách thiết kế là trả cùng dữ liệu phiên bản:

~~~json
{
  "productId": 42,
  "displayPrice": 125000,
  "currency": "VND",
  "priceVersion": 18,
  "inventoryDisplay": "LOW_STOCK"
}
~~~

Client biết đây là thông tin hiển thị và phải xử lý việc checkout có thể trả kết quả giá/kho đã thay đổi.

## 17. Bảo mật cache giữa người dùng và tenant

Một lỗi cache key hoặc cấu hình shared cache có thể làm lộ dữ liệu nghiêm trọng.

**Không cache phản hồi người dùng theo URL chung** nếu nội dung khác nhau theo Authorization, cookie, tenant hoặc role. Ví dụ GET /me trả profile của người đang đăng nhập: nếu gateway key chỉ là path "/me", User B có thể nhận dữ liệu của User A.

Các biện pháp:
- Phân loại public, private, sensitive ngay tại API contract.
- Trả Cache-Control phù hợp. Với nội dung nhạy cảm, dùng no-store khi chính sách yêu cầu.
- Shared cache mặc định bypass với dữ liệu Authorization/cookie trừ khi có thiết kế được phê duyệt riêng.
- Xác định key với tenant, auth scope, locale, currency và các variant quyết định representation.
- Không lưu dữ liệu nhạy cảm hoặc token vào logs/metrics của cache key.
- Áp dụng TTL ngắn, xóa dữ liệu khi logout/revocation theo yêu cầu, và không dựa hoàn toàn vào TTL khi cần thu hồi quyền tức thời.
- Kiểm thử hai tài khoản/tenant song song với cùng URL, chuyển vai trò và thay đổi quyền.
- Bảo vệ Redis bằng network isolation, ACL, TLS và quota theo môi trường; không coi việc cache là không nhạy cảm chỉ vì nó không phải database chuẩn.

Cache thông tin phân quyền có thể làm quyền bị thu hồi vẫn còn hiệu lực trong thời gian stale. Nếu cần thu hồi ngay, dùng version của policy hoặc kiểm tra trạng thái mới tại điểm quyết định quyền thay vì dựa vào cache TTL dài.

## 18. Chịu lỗi: cache phải phục vụ hệ thống thay vì trở thành điểm sập mới

Không nên mặc định Redis luôn sẵn sàng và latency luôn nhỏ. Khi Redis lỗi:
- Một số cache-aside workloads có thể fallback sang DB, nhưng **không được làm DB sập vì toàn bộ request cùng miss**.
- Có thể cần giới hạn số request fallback, timeout ngắn cho cache, circuit breaker và bulkhead.
- Nếu cache là thành phần bắt buộc để bảo đảm latency ở tải đỉnh, cần có plan giảm tải, trả response thích hợp hoặc giảm chức năng không thiết yếu khi cache mất.
- Redis replication/cluster failover giúp cải thiện availability nhưng vẫn có latency spike, mất kết nối và hành vi dữ liệu cần đánh giá.
- Eviction do bộ nhớ thiếu có thể làm tăng miss mà không phát sinh lỗi kết nối; metrics phải phân biệt hai vấn đề.

### Tránh retry storm khi cache chậm

Nếu mỗi request truy vấn Redis timeout sau 2 giây rồi retry ba lần, toàn bộ request có thể giữ thread hàng giây trước khi tới DB. Timeout, retry và fallback cần được thiết kế theo ngân sách latency. Với cache thường là thành phần tối ưu, retry nhiều lần trên mỗi request có thể không đáng; quan sát và giảm tải đúng nơi quan trọng hơn.

### Cache warming sau triển khai

Khi deploy lại 20 pod cùng lúc, mọi local cache trống. Nếu mỗi pod warm toàn bộ sản phẩm, backend có thể bị quá tải trong lúc rollout. Dùng rollout dần, warm key nóng có giới hạn hoặc cho cache tự nạp theo yêu cầu, kết hợp singleflight và rate limiting.

## 19. Đo lường để biết cache có hiệu quả thật hay không

Những chỉ số cốt lõi:

| Chỉ số | Câu hỏi cần trả lời |
| --- | --- |
| Cache hit/miss ratio theo tầng | Có bao nhiêu request được phục vụ tại client, edge, L1, L2? |
| Request latency p50/p95/p99 | Cache có cải thiện trải nghiệm và SLO thực tế không? |
| Database QPS và query latency | Cache có giảm áp lực lên nguồn chuẩn không? |
| Cache operation latency/error rate | Cache có trở thành dependency chậm hoặc không ổn định không? |
| Eviction, memory usage, key count | Cache có bị giới hạn bởi dung lượng hoặc cardinality không? |
| Stale data incident/age | Có trả dữ liệu quá cũ so với cam kết không? |
| Redis network/connection saturation | Chi phí mạng và pool có tăng bất thường không? |
| Stampede/singleflight wait | Nhiều request có đập vào một key lúc miss không? |
| Cost per successful request | Chi phí hạ tầng có thực sự giảm không? |

Theo dõi metric theo service/cache name/operation; tránh label chứa product ID, user ID hoặc cache key tự do gây cardinality rất cao. Với lỗi dữ liệu cũ, structured log/tracing nên có key đã ẩn thông tin nhạy cảm, version, cache layer, age và request correlation ID khi phù hợp.

Một ví dụ:
- Trước cache: 1.000 request/giây, DB phải xử lý 800 query/giây, p95 API 250 ms.
- Sau cache: request vẫn 1.000/giây, DB còn 150 query/giây, p95 API 90 ms.
- Nhưng nếu p99 tăng lên 2 giây mỗi khi cache hết TTL đồng loạt, cần xử lý stampede; nhìn mỗi hit ratio sẽ bỏ sót vấn đề.

Không đánh giá một thay đổi cache chỉ bằng thời gian của happy-path hit. Phải đo miss, cold start, invalidation và trạng thái cache suy giảm.

## 20. Kiểm thử cache ở đúng tầng

**Unit/component tests:** xác nhận key đúng khi đổi locale/tenant/currency; hit không gọi loader; miss có gọi loader; TTL và negative caching tuân theo quy tắc.

**Integration tests:** chạy với Redis hoặc công nghệ cache thật trong môi trường thử nghiệm; xác nhận serialization, TTL, eviction, timeout và lỗi kết nối. Với @Cacheable của Spring, cần kiểm tra lời gọi đi qua proxy phù hợp.

**Concurrency tests:** nhiều request cùng key khi cache trống; một reader miss trong lúc writer commit; cùng lúc nhiều pod invalidation; event đến trễ và out-of-order.

**Security tests:** hai người dùng/tenant gọi cùng endpoint; sau đổi quyền hoặc logout không đọc nhầm bản cache khác; response private không được edge cache phục vụ cho người không có quyền.

**Load tests:** warm cache, cold cache, mất Redis, key nóng, tỷ lệ hit thấp, traffic spike, rolling deploy và scale out. Quan sát DB QPS, p95/p99, eviction, thread pool và số request fail.

**E2E chọn lọc:** khi admin đổi nội dung công khai, user thấy dữ liệu mới trong giới hạn stale cam kết; checkout luôn xác nhận giá và tồn kho đúng ở bước quyết định.

Một bài test cache có thể “PASS vì luôn hit” nhưng không phát hiện lỗi stale nếu không tạo dữ liệu mới và thực hiện invalidation thật. Nên kiểm tra hành vi trước, trong và sau hết TTL, không dùng Thread.sleep tùy tiện khi có thể kiểm soát clock/scheduler hoặc polling có deadline.

## 21. Bài toán chọn tầng cache theo tình huống

| Tình huống | Tầng ưu tiên | Lý do |
| --- | --- | --- |
| CSS/JS/ảnh có hash nội dung | Client + CDN | Tài nguyên bất biến theo URL, hiệu quả băng thông cao |
| Danh mục sản phẩm công khai | CDN/gateway + service | Nhiều người cùng đọc, cần TTL và purge |
| Cấu hình tham chiếu nội bộ nhỏ | Local cache | Truy cập nhanh, ít đổi, không cần network hop |
| Kết quả lookup chung giữa nhiều pod | Distributed cache | Giảm query trùng ở nhiều replica |
| Báo cáo tổng hợp tốn CPU/SQL | Materialized view/read model + optional cache | Cần tính trước và làm mới có quản lý |
| Tồn kho hiển thị | Cache thời hạn ngắn | UI chấp nhận độ trễ; checkout phải xác nhận lại |
| Thanh toán hoặc quyền truy cập | Nguồn chuẩn/kiểm tra bảo mật | Không để stale quyết định nghiệp vụ nhạy cảm |
| Search query có vô số filter hiếm lặp | Chọn lọc hoặc không cache | Cardinality lớn, hit ratio thấp |
| Dữ liệu theo người dùng | Client/private hoặc service cache theo scope | Tránh leak từ shared cache |

Đặt cache ở tầng sớm nhất có thể trả lời **an toàn** và đủ mới. Nhưng quá nhiều tầng có thể làm invalidation khó hơn lợi ích mang lại; nên thêm lớp mới khi đã có bằng chứng về điểm nghẽn và thiết kế vận hành phù hợp.

## 22. Tình huống thực tế: Catalog trong đợt flash sale

Giả sử Catalog Service có 8 replica, PostgreSQL và Redis. Trang chủ hiển thị 100 sản phẩm nổi bật, một phần lớn lưu lượng tập trung vào 10 sản phẩm hot. Trước flash sale, backend có p95 220 ms và database gần giới hạn read IOPS.

### Giai đoạn thiết kế

1. Ảnh và asset mang content hash được cache lâu ở browser/CDN.
2. Response danh mục công khai được cache ở CDN với TTL ngắn; key tách locale/currency.
3. Product metadata dùng local Caffeine TTL ngắn và Redis TTL dài hơn, cả hai có max size/eviction phù hợp.
4. Tác vụ cập nhật sản phẩm phát tín hiệu invalidation/version sau khi commit.
5. Giá và tồn kho động được tách khỏi phần metadata hoặc có freshness riêng; checkout kiểm tra nguồn chuẩn.
6. Khi miss đồng loạt, singleflight và concurrency limit giảm truy vấn dồn lên DB.
7. Dashboard theo dõi hit ratio từng tầng, read QPS và stale age.

### Một trường hợp cập nhật giữa lúc nhiều người đọc

~~~text
12:00:00  Product v7 đã được cache tại CDN và Redis
12:00:10  Admin cập nhật mô tả -> Product v8 trong DB
12:00:11  Catalog commit -> invalidation/version event
12:00:12  Redis và local cache được xóa hoặc đổi key
12:00:13  CDN bắt đầu purge hoặc đợi TTL theo policy
12:00:15  Client mới có thể nhận v8 tùy tầng vừa phục vụ
~~~

Không coi mốc thời gian này là bảo đảm các tầng đồng bộ tuyệt đối. Nếu nghiệp vụ cam kết mô tả thay đổi hiện ra trong tối đa 60 giây, phải đo từ lúc commit đến lúc người dùng nhận bản mới qua **mọi lớp có thể phục vụ**. Nếu cần thay đổi tức thì, phải chọn cơ chế phù hợp hơn hoặc loại bỏ tầng cache không kiểm soát được.

### Đánh giá sau khi triển khai

So sánh cùng dạng tải trước/sau: p95/p99, throughput, DB QPS, Redis p95, CDN offload, số lần miss dồn và tỉ lệ lỗi. Kiểm tra riêng tình huống Redis mất kết nối, CDN purge trễ, sản phẩm chưa tồn tại và thay đổi giá ngay trước checkout. Từ đó quyết định TTL/chi phí thích hợp thay vì chỉ tăng thời hạn cache để có hit ratio đẹp.

## 23. Những sai lầm cần tránh

1. **Cache toàn bộ response ở gateway chỉ theo path:** dễ trả dữ liệu sai locale/tenant/user hoặc sai quyền.
2. **Dùng TTL dài cho dữ liệu giao dịch:** giá, tồn kho, quyền có thể không đáp ứng tính đúng đắn khi ra quyết định.
3. **Quên invalidation giữa nhiều pod:** xóa local cache của một pod không xóa bản sao ở các pod khác.
4. **Xóa cache trước commit:** loader khác có thể nạp lại bản dữ liệu cũ vào khoảng race.
5. **Chỉ theo dõi hit ratio:** bỏ qua p99 miss, stale errors, chi phí và sức khỏe nguồn dữ liệu.
6. **Tăng Redis như giải pháp cho mọi query chậm:** có thể che index/SQL chưa tốt và tạo dependency mới.
7. **Cache vô hạn các tổ hợp query:** gây cardinality lớn, eviction liên tục, chi phí tăng.
8. **Không phòng cache stampede:** TTL đồng loạt hoặc cold start làm DB bị dội tải.
9. **Cache 404/403/500 giống nhau:** có thể che lỗi hệ thống và lộ dữ liệu giữa các quyền khác nhau.
10. **Nhầm no-cache và no-store:** no-cache vẫn có thể lưu nhưng cần revalidate; no-store mới là chỉ dẫn không lưu.
11. **Coi read replica là dữ liệu tức thời:** replication lag có thể làm read-after-write trả bản cũ.
12. **Coi cache là nguồn dữ liệu chuẩn:** eviction hoặc mất cache không được làm mất giao dịch đã xác nhận.
13. **Không tính memory/serialization/network overhead:** cache lớn có thể làm JVM GC chậm hoặc Redis bị quá tải.
14. **Không kiểm thử khi một tầng cache lỗi:** fallback hàng loạt có thể làm sập backend.
15. **Dùng cùng cache key cho nhiều phiên bản schema:** deploy có thể đọc payload không tương thích, gây lỗi deserialize.
16. **Cache response chứa token hoặc dữ liệu nhạy cảm trong shared cache:** tạo rủi ro bảo mật nghiêm trọng.

## 24. Checklist khi đưa cache vào sản xuất

- [ ] Biết điểm nghẽn và SLO cần cải thiện; đo baseline trước khi cache.
- [ ] Xác định dữ liệu chuẩn, mức stale tối đa và tính nhạy cảm của từng nhóm dữ liệu.
- [ ] Chọn tầng cache phù hợp: client, gateway, local service, Redis hoặc data/read model.
- [ ] Cache key đủ method/path/query/locale/currency/tenant/scope/version khi chúng ảnh hưởng representation.
- [ ] Có quy tắc Cache-Control, ETag/Vary hoặc chính sách tương đương cho HTTP.
- [ ] Shared cache không lưu dữ liệu riêng tư ngoài phạm vi cho phép.
- [ ] TTL và eviction có giới hạn rõ, tránh bộ nhớ tăng vô hạn.
- [ ] Có invalidation sau commit hoặc versioned key khi dữ liệu cập nhật.
- [ ] Xử lý việc nhiều pod có local cache và các event invalidation bị trễ.
- [ ] Đã xét race giữa cache miss loader và update writer.
- [ ] Có cơ chế giảm cache stampede, hot key và negative miss.
- [ ] Khi cache lỗi có timeout, fallback hoặc giảm tải không làm DB sập.
- [ ] Checkout/thanh toán/ủy quyền xác nhận đúng từ nguồn đáng tin thay vì tin cache stale.
- [ ] Có metric hit/miss, p95/p99, stale, eviction, errors, DB QPS và chi phí.
- [ ] Đã kiểm thử cold start, purge, concurrency, TTL expiry, multi-tenant và sự cố cache.
- [ ] Có người sở hữu cache policy, runbook invalidation và quy trình ứng phó lỗi.

## 25. Bài tập thực hành

Hãy thiết kế cache cho hệ thống gồm Product Service, Pricing Service, Inventory Service và Gateway. Mỗi giây có 3.000 request xem sản phẩm, 200 request xem giá khuyến mãi theo người dùng, và 80 request đặt hàng. Hình ảnh thay đổi hiếm, mô tả sản phẩm đổi vài lần mỗi ngày, giá có thể đổi mỗi phút, tồn kho cập nhật liên tục.

Trả lời các câu hỏi:

1. Dữ liệu nào có thể cache ở client và CDN với TTL dài hoặc content-hash URL?
2. Những endpoint nào phù hợp với shared gateway cache, endpoint nào phải bypass?
3. Catalog nên dùng local cache, Redis hay cả hai, trong điều kiện nhiều replica?
4. Cache key phải chứa những phần nào để không trộn tenant, locale, currency hoặc quyền?
5. Khi admin cập nhật mô tả, làm sao invalidation qua nhiều pod và CDN?
6. Nếu 10.000 request cùng miss một sản phẩm hot, bạn giới hạn truy vấn database như thế nào?
7. Nếu Redis mất kết nối đúng giờ cao điểm, hệ thống có ngưỡng fallback/rate limit nào?
8. Vì sao checkout không được dựa duy nhất vào tồn kho/giá vừa đọc từ cache?
9. Bạn dùng những metric nào để chứng minh cache cải thiện p95/p99 mà không tăng lỗi stale?
10. Nếu một người bị thu hồi quyền truy cập, dữ liệu cached có thể tiếp tục phục vụ bao lâu theo thiết kế?

Hãy mô tả một sơ đồ request path, cache keys, TTL và sự kiện invalidation cho ba nhóm dữ liệu: thông tin công khai, dữ liệu theo tài khoản và dữ liệu giao dịch. Sau đó kiểm thử tình huống rolling deployment khi một pod cũ vẫn giữ cache L1 không tương thích với phiên bản mới.

## Kết luận

Bộ nhớ đệm trong microservices có nhiều lớp với vai trò khác nhau: client cache giảm network và cải thiện trải nghiệm; gateway/CDN chia sẻ response công khai; local/distributed cache giảm công việc tại service; buffer pool, materialized view và read model giúp tầng dữ liệu phục vụ truy vấn hiệu quả hơn. Thiết kế tốt bắt đầu từ việc xác định nguồn dữ liệu chuẩn, độ mới cần thiết và quyền truy cập; sau đó chọn key, TTL, invalidation, giới hạn tài nguyên và cách ứng phó khi cache lỗi. Giá trị thực của caching được chứng minh bằng SLO, thông lượng đúng, tính nhất quán, an toàn dữ liệu và chi phí khi hệ thống chạy nhiều instance dưới tải thực tế.
