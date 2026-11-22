# Negative caching và lỗi biến dữ liệu chưa có thành kết quả tồn tại lâu

## 1. Một bản ghi vừa được tạo nhưng hệ thống vẫn nói “không tồn tại”

Một ứng dụng Java lưu thông tin sản phẩm trong NoSQL và dùng Redis để giảm lượng truy vấn:

~~~text
t=00:00  GET /products/P101
         Redis miss -> database trả NOT_FOUND.

t=00:01  Service đặt key cache "P101 does not exist",
         TTL = 24 giờ.

t=00:02  Admin tạo sản phẩm P101 thành công trong database.

t=00:03  GET /products/P101
         Redis hit negative entry -> API trả 404.

t=12:00  Sản phẩm P101 vẫn có thật trong database,
         nhưng API tiếp tục trả 404 từ cache.
~~~

Ở đây, dữ liệu **chưa tồn tại tại một thời điểm** bị biến thành kết luận **không tồn tại lâu dài**. Database không hề mất bản ghi; chính cache đã lưu một sự thật tạm thời quá lâu và thiếu cơ chế thu hồi khi sự thật thay đổi.

Người phát triển thường bật negative caching để tránh truy vấn lặp lại các key không tồn tại. Kỹ thuật này hợp lý khi được áp dụng có điều kiện, nhưng rất dễ tạo lỗi khó chẩn đoán:

- User đăng ký tài khoản nhưng API vẫn nói username chưa có hoặc profile chưa được tạo.
- Một đơn hàng đã commit nhưng endpoint trạng thái tiếp tục trả NOT_FOUND.
- Sản phẩm vừa được import chưa hiện trên trang chi tiết.
- Trạng thái từ một replica chậm bị cache thành kết quả “không có”.
- Một timeout ở downstream vô tình được chuyển thành null rồi bị cache như bản ghi không tồn tại.
- Xóa một item nhưng stale cache khiến dữ liệu đã xóa xuất hiện trở lại, hoặc một negative entry cũ khiến item mới không xuất hiện.

Bài này thuộc module **Database No SQL**, chương **Bộ nhớ đệm dữ liệu**. Trọng tâm không phải chỉ là cú pháp Redis, mà là **ý nghĩa của sự vắng mặt, phạm vi thẩm quyền của dữ liệu và giới hạn thời gian một kết luận NOT_FOUND được phép tồn tại**.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **cache miss**, **cached negative result**, **source NOT_FOUND**, **transient error**, **stale read** và **business deletion**.
2. Hiểu cơ chế negative caching, lợi ích ngăn *cache penetration* và rủi ro biến kết quả tạm thời thành sai lệch kéo dài.
3. Thiết kế positive/negative TTL, invalidation, key namespace và giới hạn stale.
4. Nhận diện các cuộc đua giữa đọc NOT_FOUND, tạo dữ liệu, retry, invalidate và cache fill.
5. Dùng version/generation/conditional write để tránh negative entry cũ ghi đè trạng thái mới.
6. Lập sơ đồ cache-aside, read-after-write, multi-level cache và failover.
7. Viết ví dụ Java với Redis, tự phân loại kết quả từ repository, và thảo luận Caffeine/Spring Cache.
8. Liên hệ MongoDB, DynamoDB, Cassandra/ScyllaDB và Elasticsearch/OpenSearch trong hệ NoSQL có eventual consistency.
9. Chọn metrics và test cases để chứng minh negative caching không phá đúng đắn nghiệp vụ.

## 2. Negative caching là gì?

**Negative caching** là lưu một kết quả có nghĩa **không tìm thấy đối tượng**, **không có kết quả phù hợp** hoặc **điều kiện nào đó không thỏa**, nhằm tránh lặp lại một truy vấn tốn kém trong một khoảng thời gian.

Ví dụ:

~~~text
GET product P999
   |
   v
Cache miss
   |
   v
Database: NOT_FOUND
   |
   v
Cache NEGATIVE(P999) for 10 seconds
   |
   v
Repeated GET P999 -> return NOT_FOUND from cache
~~~

### 2.1. Vì sao cache cả kết quả “không có”?

Nếu một API nhận 100.000 requests tới ID không tồn tại, chỉ cache bản ghi tìm được sẽ không giúp gì; mọi request đều tới database.

Negative caching có thể:

- Giảm query vô ích đến NoSQL.
- Giảm latency khi có nhiều truy vấn tới cùng key không tồn tại.
- Hạn chế traffic từ bots/crawlers hoặc các clients gõ sai ID liên tục.
- Giảm áp lực lên index và read replicas.
- Tránh stampede lặp lại trên một số key không tồn tại.

### 2.2. Điều kiện để negative caching đúng

Kết luận NOT_FOUND phải được tạo ra từ **đường đọc có độ tin cậy đủ cho nghiệp vụ**, và thời gian sống của kết luận phải phù hợp khả năng dữ liệu được tạo/cập nhật sau đó.

Nếu service chỉ nhận thông tin “không thấy ở một bản sao”, nó chưa chắc có đủ bằng chứng nói “nguồn có thẩm quyền xác nhận không tồn tại”.

### 2.3. Negative không phải exception

Một NOT_FOUND hợp lệ có thể là một kết quả nghiệp vụ bình thường. Timeout, server error, quyền bị từ chối, parse error hoặc circuit breaker mở là **trạng thái khác**; không được gộp tất cả vào một null chung.

### 2.4. Negative entry không phải tombstone của database

Một cache entry NEGATIVE(P101) nói **đường đọc này không tìm được P101 trong một thời điểm và phạm vi**.

Một tombstone của storage có thể là metadata của thao tác xóa phục vụ replication/compaction và bảo vệ dữ liệu đã xóa. Hai khái niệm khác chức năng, thời hạn và protocol. Không coi cached NOT_FOUND là một lệnh DELETE hoặc bằng chứng xóa vật lý.

## 3. Bốn tình huống không được đặt cùng một giá trị null

Một cache cho profile thường có các trạng thái:

| Trạng thái | Ý nghĩa | Nguồn kết luận | Cách xử lý |
|---|---|---|---|
| CACHE_MISS | Cache không biết gì về key | Cache lookup | Hỏi nguồn có thẩm quyền |
| POSITIVE | Có giá trị đã cache | Cache lookup | Trả nếu hợp freshness/authorization |
| NEGATIVE | Đã cache một kết luận không tìm thấy | Lần đọc nguồn trước | Chỉ trả NOT_FOUND trong thời hạn/policy |
| ERROR/UNKNOWN | Không xác định sự tồn tại | Timeout, 5xx, throttle, lỗi driver | Trả lỗi/retry có kiểm soát; không cache như NOT_FOUND |

### 3.1. Sai lầm với Optional.empty()

Một repository có thể trả:

~~~java
Optional<Product> findById(String id);
~~~

Khi Optional.empty() biểu diễn **source xác nhận không có** thì hợp lý. Nhưng nếu service bắt mọi exception và trả Optional.empty(), cache không còn phân biệt được outage với absent.

### 3.2. Không nên có code như sau

~~~java
public Optional<Product> findProduct(String id) {
    try {
        return repository.findById(id);
    } catch (Exception error) {
        return Optional.empty(); // Nguy hiểm: biến lỗi thành NOT_FOUND.
    }
}
~~~

Một outage kéo dài 30 giây có thể làm hệ cache hàng nghìn kết quả NEGATIVE sai, rồi tiếp tục trả 404 hàng giờ ngay cả khi database phục hồi.

### 3.3. Trả 503 khác trả 404

Nếu không kết nối được database:

~~~text
503 Service Unavailable
~~~

có thể đúng hơn:

~~~text
404 Not Found
~~~

Miễn là API contract xác định lỗi này là unavailable. Không tự biến tính sẵn sàng kém thành tuyên bố dữ liệu vắng mặt.

### 3.4. Một cached negative entry phải là object có ý nghĩa

Thay vì đặt value bằng null mơ hồ, có thể lưu:

~~~json
{
  "kind": "NOT_FOUND",
  "observedAtEpochMs": 1794645000000,
  "source": "authoritative-products",
  "schemaVersion": 1
}
~~~

Timestamp chỉ là metadata. Nó không tự bảo đảm kết luận còn đúng; TTL, nguồn đọc và invalidation vẫn quyết định.

## 4. Cache miss và negative cache hit là hai trạng thái khác nhau

### 4.1. Cache miss

~~~text
Redis GET product:P101
-> nil
~~~

Không có cache entry, nghĩa là **cache chưa biết** sản phẩm có tồn tại hay không.

### 4.2. Negative cache hit

~~~text
Redis GET product:P101
-> "N"
~~~

Hệ đã từng lưu một kết luận NOT_FOUND. Nếu key còn hợp lệ, có thể trả 404 mà không query database.

### 4.3. Vì sao dùng null làm sentinel dễ sai?

Một số caches không cho lưu null; một số framework coi null là giá trị hợp lệ; Redis GET nil có nghĩa key không tồn tại. Nếu code dùng một null cho cả miss và negative, hệ có thể:

- Không có tác dụng giảm cache penetration.
- Cache sai timeout thành absent.
- Không biết lúc nào cần query source.
- Không biết negative entry đã hết hạn hay chưa.

### 4.4. Cách mô hình hóa

~~~text
CacheLookup =
  MISS
  HIT_VALUE(value, metadata)
  HIT_NOT_FOUND(metadata)
~~~

Còn source lookup:

~~~text
SourceLookup =
  FOUND(value, version)
  AUTHORITATIVE_NOT_FOUND(observation)
  UNAVAILABLE(error)
  FORBIDDEN
  INDETERMINATE
~~~

Không phải mọi hệ cần nhiều class như trên, nhưng **ngữ nghĩa các đường đi phải giữ riêng**.

## 5. “Không tìm thấy” còn phụ thuộc vào phạm vi truy vấn

### 5.1. Không có record với ID chính xác

~~~text
GET product P101 by canonical primary key -> not found.
~~~

Đây có thể là một ứng viên negative caching nếu source/consistency đủ mạnh.

### 5.2. Không có kết quả tìm kiếm

~~~text
SEARCH title contains "ban phim"
-> empty results.
~~~

Không có kết quả trong search index **không chứng minh** không có product trong nguồn chuẩn, vì index có thể chưa bắt kịp.

### 5.3. Không tồn tại trong một tenant

~~~text
GET tenant=T17 product=P101 -> NOT_FOUND
~~~

không đồng nghĩa product=P101 không tồn tại ở tenant T18.

### 5.4. Không có quyền xem

Service có thể cố ý trả 404 thay vì 403 để tránh làm lộ sự tồn tại của resource. Đây là chính sách security/API, không đồng nghĩa **thực thể thực sự không có**.

Không cache kết quả che giấu quyền truy cập dưới một global key dùng chung tất cả users.

### 5.5. Không còn tồn tại vì xóa

Một resource bị xóa có thể dẫn tới 404 hoặc 410 theo API contract. Đối với ID không được phép tái sử dụng, một negative kết luận có thể ổn định hơn. Nếu business cho phép tạo lại cùng ID, cached negative vẫn phải có expiration/invalidation.

### 5.6. Không thấy dữ liệu ở thời điểm chưa commit

Một workflow tạo order có thể có trạng thái PENDING trước khi tạo xong record nguồn. Không thấy record trong một read replica chưa phải bằng chứng order sẽ không tồn tại; trạng thái pending/unknown của operation thường hữu ích hơn 404 dài hạn.

## 6. Dòng thời gian của lỗi “không có” trở thành sự thật kéo dài

~~~mermaid
sequenceDiagram
    participant C as Client
    participant Cache as Redis
    participant API as Product Service
    participant DB as NoSQL Source
    C->>API: GET P101
    API->>Cache: GET product:P101
    Cache-->>API: MISS
    API->>DB: Read P101
    DB-->>API: NOT_FOUND
    API->>Cache: SET NEGATIVE TTL=24h
    API-->>C: 404
    Note over DB: P101 được tạo thành công
    C->>API: GET P101
    API->>Cache: GET product:P101
    Cache-->>API: NEGATIVE
    API-->>C: 404 dù source đã có dữ liệu
~~~

### 6.1. Sai ở đâu?

Không nhất thiết sai ở thao tác đầu: tại thời điểm ban đầu P101 thật sự chưa tồn tại. Sai nằm ở **quy tắc cho kết luận âm tồn tại 24 giờ không có invalidation khi tạo**.

### 6.2. Tác động nghiệp vụ

Một sản phẩm mới có thể “vô hình” trên API dù create trả 201. User thấy trải nghiệm mâu thuẫn; monitoring chỉ thấy database khỏe và cache hit rate cao, nên lỗi dễ bị bỏ qua.

### 6.3. Nếu TTL là 15 giây?

Hệ có thể còn trả 404 trong tối đa khoảng TTL còn lại, giả sử key không được refresh lại hoặc có tầng cache khác. Nếu ứng dụng chấp nhận eventual visibility trong 15 giây, đây có thể là lựa chọn có chủ đích. Nếu API hứa read-your-writes ngay, vẫn chưa đủ.

### 6.4. Nếu invalidation được phát sau tạo?

Khi Product Service commit P101, nó cần xóa/ghi đè negative entry hoặc phát event cho cache invalidator. Nhưng **xóa cache đơn giản cũng có race**, sẽ được phân tích ở phần sau.

## 7. Vì sao NoSQL làm bài toán negative caching dễ phức tạp hơn?

Không phải NoSQL luôn eventual, nhưng nhiều triển khai có:

- Replicas với các mức read consistency khác nhau.
- Global secondary indexes cập nhật bất đồng bộ.
- Search projections theo CDC.
- Cross-Region replication.
- Cache nhiều tầng.
- Workflow command/transaction đa bước.
- TTL và tombstones được xử lý bất đồng bộ.

Một GET có thể trả không thấy từ một bản sao/index dù ghi ở nguồn đã thành công.

### 7.1. “Không thấy ở replica” là một quan sát, không phải kết luận tuyệt đối

~~~text
Source primary: item P101 exists, version 8.
Read replica:   item P101 not yet replicated.
~~~

Nếu API cache NOT_FOUND từ replica trong một giờ, lag vài giây đã trở thành lỗi một giờ.

### 7.2. Không được dùng consistency level theo tên mà bỏ qua contract

Ví dụ, đọc quorum, strongly consistent read hoặc read-index có ý nghĩa riêng theo từng engine/phạm vi. Không suy một query vào GSI hay external search có cùng tính nhất quán với primary-key read trên canonical table.

### 7.3. Negative cache và read-after-write

Nếu client vừa create và GET ngay, đường đọc sau create có thể cần:

- Bypass negative cache theo session/operation.
- Lấy trực tiếp kết quả create trả về.
- Dùng owner authoritative read.
- Yêu cầu minimum version/revision để coi cache entry là hợp lệ.

### 7.4. Nguyên tắc thực hành

**Cache chỉ được “khẳng định không tồn tại” mạnh tới mức nguồn dữ liệu mà nó đã dựa vào, và chỉ trong thời gian mà business cho phép khẳng định đó.**

## 8. Khi nào negative caching đem lại lợi ích rõ ràng?

### 8.1. Key không tồn tại bị hỏi nhiều lần

~~~text
10,000 repeated GETs for product P999.
Source lookup takes 10 ms.
Negative TTL = 5 seconds.
~~~

Nếu cùng key được hỏi liên tục, chỉ một vài lần cần truy vấn source trong mỗi khoảng TTL, giảm tải đáng kể.

### 8.2. Bot quét không gian ID

Nếu bot tạo mỗi request một ID khác nhau, cache negative theo từng ID có thể **không giúp** vì hit rate gần zero; thậm chí làm Redis đầy keys vô ích. Cần rate limiting, validation, bounded cache size và các cơ chế chống abuse khác.

### 8.3. Metadata có xác suất thay đổi thấp

Một code không hợp lệ trong danh mục ít thay đổi có thể dùng negative TTL lâu hơn một order vừa tạo, nhưng vẫn cần chính sách invalidation nếu danh mục được mở rộng.

### 8.4. External lookup tốn phí

Một lookup định danh ở hệ ngoài có thể rất đắt. Negative caching giảm phí nhưng cần phân biệt nguồn trả NOT_FOUND chính thức với 429/5xx và thời gian tài nguyên có thể được tạo mới.

### 8.5. Không dùng với mọi truy vấn “empty”

Kết quả của query time-window, search theo keyword, permission filter hay dynamic inventory có thể thay đổi nhanh. Cache empty-result phải phụ thuộc **full query key**, freshness, filter scope và invalidation.

## 9. Chọn TTL cho kết quả âm

Không có một TTL âm tối ưu cho mọi resource. Hãy xem tốc độ tạo dữ liệu, tính nhất quán của source, yêu cầu read-after-write và chi phí truy vấn.

| Kiểu dữ liệu | Khả năng xuất hiện sau NOT_FOUND | Hướng TTL âm |
|---|---|---|
| Product ID chưa có nhưng admin có thể tạo | Có | Ngắn + invalidate lúc create |
| Order ID đang trong workflow create | Cao ngay sau create | Tránh negative hoặc cực ngắn; ưu tiên operation status |
| Username đang được đăng ký | Có race và unique claim | Không dùng negative cache để quyết định availability |
| Feature flag mới phát hành | Có | Ngắn, event invalidation |
| Search query rỗng trên index eventual | Cao khi indexing | Ngắn, không suy source absence |
| Mã định danh vĩnh viễn invalid theo schema | Không nếu validation xác định | Reject ở validation, không cần cache source NOT_FOUND |
| Historical ID bị xóa vĩnh viễn | Tùy chính sách tái sử dụng | Có thể lâu hơn khi có tombstone/never-reuse contract |
| Permission-filtered resource | Thay đổi theo user/role | Key theo principal/scope; TTL có policy security |

### 9.1. Negative TTL thường ngắn hơn positive TTL

Đây là một quy tắc **thực dụng, không tuyệt đối**:

~~~text
Positive TTL: 5 minutes
Negative TTL: 5–15 seconds
~~~

Những con số chỉ để minh họa. Business có yêu cầu tạo hiển thị ngay phải invalidate/bypass, chứ không đơn thuần “TTL âm 5 giây là đủ”.

### 9.2. TTL là giới hạn sai lệch có điều kiện

Nếu negative entry được tạo lúc t0, item được tạo ở t1 ngay sau đó, và không có invalidation, thời gian sai lệch tối đa gần bằng **TTL còn lại**.

Nếu nhiều tầng cache hoặc code gia hạn TTL mỗi lần đọc, sai lệch có thể dài hơn dự tính.

### 9.3. Fixed TTL khác sliding TTL

Fixed TTL: entry tự hết hạn sau khoảng thời gian từ lần tạo.

Sliding TTL: mỗi lần hit lại gia hạn expiration. Với negative cache, sliding TTL có thể biến một resource mới được tạo thành **NOT_FOUND gần như vô hạn** nếu liên tục có traffic và không có invalidation.

### 9.4. Tránh negative entry không có TTL

~~~text
SET product:P101 "NOT_FOUND"
~~~

Nếu không có EX/PX/TTL policy, entry có thể tồn tại rất lâu tùy eviction/persistence. Đây là một anti-pattern nguy hiểm cho resource có thể được tạo sau đó.

### 9.5. Đừng cache “not found” 24 giờ vì positive TTL cũng 24 giờ

Lý do cache positive data lâu không tự áp dụng cho negative data. Positive data tồn tại thường có đường update/invalidate, còn negative data **có thể trở nên sai ngay khi một create xảy ra**.

## 10. TTL và chi phí: một phép tính trực giác

Giả sử cùng key không tồn tại bị hỏi đều với tốc độ 100 requests/giây.

Không negative cache:

~~~text
100 requests/giây tới database
~~~

Nếu TTL âm là 10 giây và mỗi khoảng chỉ một request phải truy vấn database:

~~~text
~0.1 source lookup/giây cho key đó
~~~

Đây là lý tưởng hóa, bỏ qua concurrent misses, refresh, outage và race. Nó minh họa vì sao negative caching hiệu quả với **hot missing keys**.

Nhưng nếu 100 requests/giây đều tới **100 ID khác nhau**, mỗi key chỉ một lần:

~~~text
100 source lookups/giây
100 negative cache entries/giây
~0 future negative hits
~~~

Lúc này negative caching gần như chỉ tốn thêm cache memory. Cần policy admission, max size, validation hoặc rate limit.

## 11. Thiết kế cache-aside có negative entry

Một luồng đọc phổ biến:

~~~mermaid
flowchart TD
    A["GET resource K"] --> B["Lookup cache K"]
    B --> C{"Cache state?"}
    C -->|"POSITIVE"| D["Return cached value"]
    C -->|"NEGATIVE"| E["Return NOT_FOUND under policy"]
    C -->|"MISS"| F["Read authoritative source"]
    F --> G{"Source result?"}
    G -->|"FOUND"| H["Cache positive with TTL"]
    G -->|"NOT_FOUND"| I["Cache negative with short TTL"]
    G -->|"ERROR or UNKNOWN"| J["Propagate failure; do not cache negative"]
    H --> K["Return value"]
    I --> E
~~~

### 11.1. Chỉ negative-cache kết quả đã được phân loại

Một mapper nên có kết quả rõ ràng:

~~~text
Found(resource, revision)
NotFound(observedSourceRevision)
Unavailable(error)
Forbidden
Indeterminate
~~~

Trong đó observedSourceRevision là thông tin tùy khả năng của storage; nếu không có, thiết kế phải dựa vào TTL, consistency và invalidation thay vì bịa một revision.

### 11.2. Cache key chứa đủ phạm vi

~~~text
product:{tenant=T17}:id=P101
~~~

Nếu P101 tồn tại ở tenant A nhưng không ở tenant B, negative cache của B không được khiến A trả 404.

### 11.3. Positive và negative dùng cùng logic version

Không có nghĩa negative và positive phải có cùng TTL. Có thể cần phân biệt stored observation version/epoch và source revision để không cho cache entry cũ overwrite entry mới.

### 11.4. Cache write là tối ưu hóa

Nếu source trả FOUND nhưng Redis unavailable, application có thể trả dữ liệu nguồn cho GET nếu policy cho phép. Không biến lỗi set cache thành lỗi đọc business dữ liệu một cách vô lý.

### 11.5. Không đọc nguồn không đủ thẩm quyền

Một negative entry chỉ nên được tạo từ read path có consistency phù hợp. Nếu đọc từ search index eventual, nó phải được gắn nghĩa **search result empty**, không phải **canonical item absent**.

## 12. Invalidation khi CREATE: cần thiết nhưng chưa đủ

Một quy tắc đơn giản:

~~~text
CREATE P101 commits in source
  -> DEL cache key product:P101
~~~

hoặc:

~~~text
CREATE P101 commits in source
  -> write-through/cache positive P101
~~~

### 12.1. Invalidate trước source commit là nguy hiểm

~~~text
t1 DEL cache negative P101
t2 Reader cache MISS, source vẫn NOT_FOUND
t3 Reader đặt lại negative P101
t4 CREATE commit P101
~~~

Nếu không có invalidation **sau commit**, cache giữ lại kết luận sai.

### 12.2. Invalidation sau commit là thứ tự hợp lý

Về nguyên tắc:

~~~text
1. Commit source.
2. Publish invalidation/update after commit.
~~~

Không nên phát business event “đã tạo” trước khi nguồn thực sự commit.

### 12.3. Nhưng source commit và Redis DEL có thể bị lỗi giữa chừng

~~~text
Source commits P101.
Process crashes before cache DEL.
~~~

Negative key vẫn tồn tại tới TTL. Nếu cần bảo đảm mạnh hơn, dùng transactional outbox/CDC + consumer invalidation, kèm TTL làm fallback. Thậm chí outbox cũng có delivery lag; API yêu cầu read-your-writes có thể phải bypass cache.

### 12.4. Invalidate theo mọi đường tạo/cập nhật

Không chỉ API POST thông thường. Hệ còn có:

- Bulk import.
- Admin maintenance.
- Batch migration.
- CDC replication từ hệ nguồn.
- Restore/undelete.
- Scheduled publish.

Nếu một đường create không phát invalidation, cache vẫn có thể sai.

## 13. Cuộc đua nguy hiểm: negative entry được ghi sau invalidation

Đây là lỗi tinh vi hơn việc quên DEL:

~~~text
t1 Reader R: cache MISS P101.
t2 Reader R: query nguồn; tại thời điểm đọc, P101 chưa có.
t3 Writer W: CREATE P101 commits.
t4 Writer W: DEL cache P101.
t5 Reader R: nhận NOT_FOUND cũ, SET NEGATIVE(P101) TTL=10min.
t6 Các GET mới đều trả 404 trong 10 phút.
~~~

Writer **đã invalidate đúng sau commit**, nhưng một request đọc cũ ghi negative vào cache sau đó.

### 13.1. Nguyên nhân

Cache fill và cache invalidation không được phối hợp theo **thế hệ dữ liệu**. DEL chỉ tác động key ở thời điểm gọi; nó không ngăn một request cũ ghi vào key sau DEL.

### 13.2. Chỉ rút TTL không giải quyết hoàn toàn

TTL 5 giây rút ngắn hậu quả, nhưng API hứa read-your-writes tức thời vẫn có thể vi phạm. Với resource critical, cần cơ chế chống stale fill hoặc bypass có chủ đích.

### 13.3. Dùng generation token

Một chiến lược:

~~~text
R: đọc cache generation G=12 trước khi query source.
W: commit source P101.
W: tăng generation lên G=13 và xóa cache.
R: nhận NOT_FOUND cũ.
R: trước khi SET NEGATIVE, kiểm tra generation vẫn 12?
    Không -> bỏ kết quả âm; retry/source read mới nếu cần.
~~~

Điều kiện so sánh generation và SET negative phải được thực thi **nguyên tử ở cache**, nếu không vẫn có race giữa check và set.

### 13.4. Phạm vi bảo đảm

Generation cache chặn stale fill **sau khi invalidation đã làm tăng generation**. Nó không biến hai hệ độc lập (database và Redis) thành một distributed transaction, nên vẫn có khoảng thời gian giữa source commit và invalidation. API mạnh hơn cần owner/source read và protocol riêng.

### 13.5. Cache positive cũng có race tương tự

Reader lấy dữ liệu version 7; writer commit version 8 và DEL; reader cũ SET version 7 sau DEL. Vấn đề cache fill stale không chỉ có negative entries, nhưng với NOT_FOUND hậu quả là làm record mới **biến mất khỏi đường đọc**.

## 14. Redis generation và Lua: ví dụ chặn stale negative fill

Giả sử hai Redis keys cho một logical resource:

~~~text
resource:{T17:P101}:data
resource:{T17:P101}:generation
~~~

Dùng cùng hash tag để keys nằm cùng slot nếu triển khai Redis Cluster và chạy multi-key Lua.

### 14.1. Bắt đầu đọc

~~~text
GET resource:{T17:P101}:data
GET resource:{T17:P101}:generation
~~~

Nếu data MISS, reader ghi nhớ generation hiện tại, giả sử 12; nếu generation không tồn tại thì dùng giá trị mặc định 0 theo contract.

### 14.2. Writer sau commit

Một Lua script chạy nguyên tử trên Redis:

~~~lua
-- KEYS[1] = generation key
-- KEYS[2] = data key
redis.call("INCR", KEYS[1])
redis.call("DEL", KEYS[2])
return redis.call("GET", KEYS[1])
~~~

Script này chỉ chạy **sau source commit thành công**. Không làm một cache invalidation thất bại biến source write thành chưa commit; phải có retry/outbox/reconciliation cho invalidation.

### 14.3. Reader ghi negative có điều kiện

~~~lua
-- KEYS[1] = generation key
-- KEYS[2] = data key
-- ARGV[1] = generation observed before source lookup
-- ARGV[2] = negative TTL in milliseconds

local generation = redis.call("GET", KEYS[1]) or "0"
if generation ~= ARGV[1] then
    return 0  -- stale observation; do not cache
end

-- Do not overwrite a concurrently populated positive/negative entry.
local ok = redis.call("SET", KEYS[2], "N", "NX", "PX", ARGV[2])
if ok then return 1 else return 0 end
~~~

### 14.4. Vì sao dùng NX?

Hai readers có thể cùng query source. Nếu một reader khác đã set positive mới, stale negative không được overwrite dữ liệu đó. Tuy vậy **NX riêng không đủ** nếu stale negative set trước positive và writer không invalidated; generation/ordering vẫn cần thiết.

### 14.5. Generation key cần sống đủ lâu

Nếu generation key bị hết TTL hoặc eviction và reset về 0 trong khi old in-flight readers giữ expected=0, có nguy cơ ABA (giá trị cũ lặp lại). Cần policy generation persistence/epoch uniqueness, retention đủ cho request lifetime và cache failure handling.

Một giải pháp khác dùng unique epoch/token không tái sử dụng hoặc source-version validation, tùy công nghệ.

### 14.6. Giới hạn minh họa

- Lua không thể atomic cùng transaction NoSQL ở bên ngoài Redis.
- Redis failover và durability có thể ảnh hưởng generation state.
- Multi-Region caches cần invalidation/generation theo từng vùng hoặc một authority phù hợp.
- Positive cache fill cũng phải dùng guard tương ứng.
- Nếu Redis đang lỗi, có thể bypass cache theo API contract; không nên dùng generation không tin cậy để xác nhận resource vắng mặt.

## 15. Negative caching với version của nguồn

Nếu source cung cấp revision rõ:

~~~text
Source revision 41: P101 absent.
Source revision 42: P101 created.
~~~

Một negative observation có thể ghi revision 41 và chỉ được dùng khi request không đòi dữ liệu mới hơn revision 41.

### 15.1. Minimum revision

Sau CREATE trả sourceRevision=42, client gửi:

~~~text
GET P101, minimumRevision=42
~~~

Cache negative ghi từ revision 41 phải bị bypass/rejected. Đường đọc phải bảo đảm thấy ít nhất revision 42 theo semantics của nguồn; không được giả vờ “đã có version” nếu source không hỗ trợ guarantee đó.

### 15.2. Global revision và entity revision khác nhau

Một bản ghi **chưa có** thì khó có entity version riêng. Revision của collection/partition/log có thể mô tả quan sát absent. Nếu hệ chỉ có version trên record đã tồn tại, không được bịa entityVersion=0 rồi xem nó đủ chống mọi create race.

### 15.3. Delete rồi recreate cùng ID

~~~text
P101 v5 exists.
P101 deleted, generation 6.
P101 recreated, generation 7.
~~~

Một negative từ generation 6 không được che P101 generation 7. Tùy business, có thể cấm tái sử dụng ID để đơn giản hóa invariant và giảm rủi ro stale writes.

### 15.4. Cache TTL và revision là hai lớp

TTL giới hạn thời gian stale trong trường hợp thiếu invalidation; version/generation giúp ngăn overwrite và phục vụ minimum-revision reads. Một hệ nhạy cảm thường cần cả hai.

## 16. Negative cache và khả năng hiển thị ngay sau CREATE

### 16.1. Định nghĩa read-your-writes

Nếu user gửi:

~~~text
POST /products -> 201 Created, productId=P101
GET /products/P101 -> 404
~~~

ngay sau thành công, hành vi này có thể vi phạm kỳ vọng read-your-writes của ứng dụng, dù search/index consistency là eventual.

### 16.2. Các lựa chọn

**Cách A — Trả kết quả vừa tạo:** POST trả đầy đủ ProductDto. UI dùng ngay DTO đó cho lần render tiếp theo, không GET qua cache cũ.

**Cách B — Invalidate/write-through sau commit:** Cập nhật cached positive với revision/generation đúng.

**Cách C — Bypass negative cache trong session:** Nếu session/operation có create result hoặc minimum revision, đọc trực tiếp nguồn đủ mạnh.

**Cách D — Pending state:** Nếu create còn bất đồng bộ, trả operationId và PENDING thay vì khẳng định resource đã tồn tại ngay khi chưa commit.

### 16.3. Không biến GET canonical thành search lookup

GET /products/P101 theo primary key nên có đường đọc authoritative/consistency rõ. Search index dùng để tìm theo text không nên là nguồn duy nhất xác nhận item tồn tại.

### 16.4. Khi nào eventual visibility được chấp nhận?

Một API search có thể nói sản phẩm mới xuất hiện sau tối đa vài giây. Nhưng API trả 201 cho create và hứa GET by ID ngay có thể cần bảo đảm cao hơn. **Phân biệt hợp đồng endpoint**, không bắt mọi query có cùng consistency.

## 17. Phân biệt 404, 403, 410, 429 và 5xx trước khi cache

| Kết quả | Ý nghĩa có thể có | Negative-cache như “resource absent”? |
|---|---|---|
| 200 FOUND | Có resource | Không; positive cache theo policy |
| 404 authoritative | Không có item trong scope | Có thể, TTL/invalidation phù hợp |
| 404 che giấu quyền | Không lộ sự tồn tại | Không global-cache; scope theo principal/policy |
| 410 Gone | Resource đã bị xóa theo contract | Có thể theo policy lifecycle/ID reuse |
| 403 Forbidden | Có thể tồn tại nhưng không được phép | Không cache thành global absence |
| 401 Unauthorized | Không xác thực | Không cache thành absence |
| 429 Too Many Requests | Bị rate limit | Không; backoff/Retry-After theo API |
| 500/502/503/504 | Lỗi dịch vụ/downstream | Không; không đổi thành NOT_FOUND |
| Timeout/connection reset | Outcome chưa rõ | Không; trả lỗi/retry có kiểm soát |
| Empty search result | Không match index/query tại thời điểm đó | Chỉ cache theo query scope/freshness |

### 17.1. Mã HTTP không đủ để xác định cache policy

Một HTTP 404 có thể được cố ý dùng che giấu resource thiếu quyền. Cần biết **nguồn/loại lỗi và user scope**, không chỉ lấy statusCode == 404 rồi đặt Redis negative.

### 17.2. CDN và HTTP negative caching

Proxy/CDN/browser có thể cache 404 theo HTTP caching directives hoặc cấu hình riêng. Nếu API gửi Cache-Control cho 404 quá dài, ngay cả Redis đã DEL vẫn có thể tiếp tục trả 404 ở CDN.

Kiểm tra Cache-Control, Vary, Authorization, surrogate keys và negative caching policy ở các tầng, không chỉ Redis.

### 17.3. Không cache nhầm 404 HTML từ gateway

Một gateway route sai có thể trả 404 “endpoint not found” trong khi product có thật. Nếu application coi mọi 404 downstream là item absent, cache sẽ giữ lỗi routing thành dữ liệu nghiệp vụ.

### 17.4. Negative cache có thể bị lạm dụng để dò tài khoản

Khác biệt latency giữa FOUND và NEGATIVE có thể làm lộ sự tồn tại của user/email. Authentication endpoints cần thiết kế anti-enumeration, rate limiting và response policy phù hợp, không dựa vào negative cache như cơ chế bảo mật.

## 18. Java: phân loại kết quả từ nguồn trước khi cache

Một cách viết rõ ý là dùng một sealed interface cho kết quả đọc. Ví dụ dùng cú pháp Java 17:

~~~java
public sealed interface ProductLookup
        permits ProductLookup.Found,
                ProductLookup.NotFound,
                ProductLookup.Unavailable {

    record Found(Product product, long sourceRevision)
            implements ProductLookup {}

    record NotFound(long observedRevision)
            implements ProductLookup {}

    record Unavailable(String reason)
            implements ProductLookup {}
}

public record Product(
        String tenantId,
        String productId,
        String name
) {}
~~~

### 18.1. Source repository phải giữ đúng lỗi

~~~java
public interface ProductRepository {
    // NotFound only for validated authoritative absence.
    // Timeouts and errors must never silently become NotFound.
    ProductLookup lookup(String tenantId, String productId);
}
~~~

Không phải NoSQL nào cũng cung cấp revision cho negative observation. Trong triển khai không có revision tương ứng, thay record bằng metadata khả dụng hoặc dùng loại kết quả khác; **không giả định observedRevision=0 có ý nghĩa mạnh**.

### 18.2. Converter không gộp kết quả

~~~java
public ProductLookup lookupSource(String tenantId, String productId) {
    try {
        return repository.lookup(tenantId, productId);
    } catch (DatabaseTimeoutException ex) {
        return new ProductLookup.Unavailable("SOURCE_TIMEOUT");
    }
}
~~~

DatabaseTimeoutException là tên exception minh họa của ứng dụng, không phải class Java chuẩn. Với driver thật, dùng đúng exception hierarchy và phân biệt retryable/non-retryable errors.

### 18.3. Không tự trả NOT_FOUND cho deserialize failure

Nếu dữ liệu tồn tại nhưng converter không hiểu schema cũ, đó có thể là data-contract error hoặc service error. Trả 404 và cache negative sẽ che mất lỗi đọc document đang tồn tại.

## 19. Java: phân biệt cache hit, miss và negative một cách tường minh

Một interface cache đơn giản:

~~~java
public sealed interface CachedProduct
        permits CachedProduct.Miss,
                CachedProduct.Present,
                CachedProduct.Absent {

    record Miss() implements CachedProduct {}

    record Present(Product product) implements CachedProduct {}

    record Absent() implements CachedProduct {}
}

public interface ProductCache {
    CachedProduct get(String tenantId, String productId);

    void putPresent(
            String tenantId, String productId, Product product);

    void putAbsent(
            String tenantId, String productId);
}
~~~

### 19.1. Cache-aside implementation

~~~java
public final class ProductReadService {
    private final ProductRepository repository;
    private final ProductCache cache;

    public ProductReadService(
            ProductRepository repository,
            ProductCache cache
    ) {
        this.repository = repository;
        this.cache = cache;
    }

    public ProductLookup get(String tenantId, String productId) {
        CachedProduct hit = cache.get(tenantId, productId);

        if (hit instanceof CachedProduct.Present p) {
            return new ProductLookup.Found(p.product(), -1);
        }

        if (hit instanceof CachedProduct.Absent) {
            return new ProductLookup.NotFound(-1);
        }

        ProductLookup source = repository.lookup(tenantId, productId);

        if (source instanceof ProductLookup.Found p) {
            cache.putPresent(tenantId, productId, p.product());
        } else if (source instanceof ProductLookup.NotFound) {
            cache.putAbsent(tenantId, productId);
        }

        return source;
    }
}
~~~

### 19.2. Đây chỉ là baseline, chưa phải bản chống race hoàn chỉnh

Đoạn trên minh họa **phân biệt kết quả**. Nó vẫn cần:

- Positive/negative TTL và namespace.
- Source consistency contract.
- Invalidation khi create/delete/update.
- Guard stale fill bằng generation/version hoặc chính sách phù hợp.
- Bypass khi client đòi minimum revision.
- Cache error handling và circuit breaker.
- Authorization trên mỗi request.

Các giá trị revision=-1 ở cached result chỉ là sentinel để code ví dụ biên dịch, **không được dùng làm proof về consistency**. Trong implementation thật, định nghĩa CachedProduct giữ revision/metadata hoặc không dùng revision cho pathway đó.

### 19.3. Tránh handler chung “catch Exception -> cache absent”

~~~java
try {
    return repository.lookup(tenantId, productId);
} catch (Exception e) {
    cache.putAbsent(tenantId, productId);  // Sai.
    return new ProductLookup.NotFound(-1);
}
~~~

Lỗi mạng, JSON parser, quyền truy cập hoặc schema không phải bằng chứng record không có.

## 20. Redis sentinel: cách mã hóa đơn giản

### 20.1. Dùng prefix để phân biệt

Ví dụ:

~~~text
P:<serialized-product>    positive
N                         negative
nil                       cache miss
~~~

Cách này cần encoder/decoder chặt và version schema; nếu serialized product tình cờ trùng sentinel, thiết kế prefix giúp phân biệt.

### 20.2. Redis commands minh họa

~~~redis
SET product:{T17:P101}:data "N" EX 10
GET product:{T17:P101}:data
TTL product:{T17:P101}:data
~~~

Đây là Redis command syntax minh họa; phần EX 10 đặt TTL 10 giây. Kết quả GET "N" là negative hit, còn nil là miss.

### 20.3. Không dùng GET nil để kết luận source absent

~~~text
GET key -> nil
~~~

chỉ nói Redis không có entry, không nói database có hay không. Phải hỏi source.

### 20.4. Đặt TTL ngay khi SET

Không tách:

~~~text
SET key "N"
EXPIRE key 10
~~~

nếu ứng dụng có thể crash giữa hai calls; cache entry sẽ thiếu TTL cho đến khi được sửa/evict. Dùng SET với EX/PX trong cùng command.

### 20.5. EXPIRE không có nghĩa event-driven invalidation

TTL chỉ tự xóa khi đến thời hạn; nó không biết admin vừa tạo Product P101 ở MongoDB. CREATE commit vẫn cần invalidation hoặc contract cho phép stale.

### 20.6. Sentinel có thể kèm metadata

~~~json
{
  "kind": "NOT_FOUND",
  "observedAt": "2026-11-14T08:30:00Z",
  "source": "product-owner",
  "generation": 12,
  "schema": 2
}
~~~

Không bắt buộc mọi negative entry giữ JSON dài. Nếu API nhẹ và consistency requirements đơn giản, sentinel "N" với TTL là đủ cho caching layer cơ bản. Metadata quan trọng hơn khi cần debug/version-aware reads.

## 21. Java và Redis: policy TTL có chủ đích

~~~java
import java.time.Duration;

public record ProductCachePolicy(
        Duration positiveTtl,
        Duration negativeTtl
) {
    public ProductCachePolicy {
        if (positiveTtl.isZero() || positiveTtl.isNegative()) {
            throw new IllegalArgumentException("positive TTL must be > 0");
        }
        if (negativeTtl.isZero() || negativeTtl.isNegative()) {
            throw new IllegalArgumentException("negative TTL must be > 0");
        }
    }
}

var policy = new ProductCachePolicy(
        Duration.ofMinutes(5),
        Duration.ofSeconds(10)
);
~~~

Đây là policy ví dụ. TTL nên được chọn theo loại resource/tenant và có khả năng thay đổi hoặc disable khi sự cố.

### 21.1. Vì sao positive và negative khác TTL?

Negative entry nhạy với **create mới**. Positive entry nhạy với **update/delete**. Hai loại có xác suất và hậu quả stale khác nhau.

### 21.2. Khi nào tắt negative cache?

Có thể cần tắt hoặc giảm TTL trong đợt:

- Bulk import catalog.
- Migration/backfill.
- Triển khai dữ liệu mới rất nhanh.
- Source/replica bị lag lớn.
- Sự cố invalidation pipeline.

### 21.3. Cấu hình không làm thay consistency

TTL âm 10 giây không thay cho một source read đủ mạnh. Nếu cache negative sinh từ eventual GSI, nó có thể sai ngay tại thời điểm tạo; TTL chỉ giới hạn thời gian lỗi.

## 22. Jitter cho TTL âm

Nếu 10.000 negative entries được tạo cùng lúc và đều hết hạn chính xác sau 10 giây, database có thể nhận một đợt reload lớn.

Thêm jitter nhỏ:

~~~text
base negative TTL = 10 seconds
actual TTL = 8..12 seconds (example)
~~~

### 22.1. Jitter phân tán expiration

Thời gian hết hạn không còn hội tụ vào một mốc tuyệt đối, có thể giảm đồng bộ cache misses.

### 22.2. Jitter không làm NOT_FOUND đúng hơn

Nếu actual TTL có thể 12 giây nhưng SLO stale tối đa 10 giây, policy đã vi phạm. Khi đặt giới hạn cứng:

~~~text
base TTL = 8 seconds
random addition = 0..2 seconds
maximum = 10 seconds
~~~

hoặc chỉ giảm TTL từ baseline, không kéo dài hơn stale budget.

### 22.3. Jitter không thay single-flight

1000 requests cùng hỏi **một** key vừa hết hạn vẫn có thể 1000 source lookups, dù expiration của các keys khác được phân tán. Cần coalescing/single-flight cho hot key.

## 23. Cache penetration: requests cho key không có thật

**Cache penetration** là tình huống queries liên tục đi qua cache xuống source vì key không có positive cached value.

### 23.1. Hot missing key

~~~text
GET P999, GET P999, GET P999 ...
~~~

Negative caching giúp vì nhiều requests cùng key.

### 23.2. Random missing keys

~~~text
GET P000001
GET P000002
GET P000003
...
~~~

Nếu mỗi key chỉ xuất hiện một lần, negative cache hầu như không có hit, nhưng tăng cache cardinality/memory.

### 23.3. Chặn đầu vào không hợp lệ

Nếu ID format chỉ cho:

~~~text
P-<12 digit decimal>
~~~

thì malformed IDs có thể bị trả 400/404 theo API contract ngay ở validation boundary mà không query database hay cache từng biến thể.

Validation phải đúng domain; không loại bỏ những ID hợp lệ do schema mới.

### 23.4. Rate limiting và abuse detection

Đặt per-client/per-tenant rate limit, circuit breaker và giới hạn cache key admission. Negative caching không phải giải pháp thay thế anti-abuse.

### 23.5. Bounded cache

Redis có memory/eviction policy; in-process caches như Caffeine có maximumSize/weight. Không dùng negative cache unbounded cho không gian key không giới hạn.

## 24. Cache stampede trên một key không tồn tại

Một negative entry hết hạn:

~~~text
t0  product:P999 NEGATIVE expires.
t1  1000 clients cùng cache MISS.
t2  1000 queries tới database.
t3  All source results are NOT_FOUND.
t4  1000 clients cùng SET negative.
~~~

Hệ không tạo sai business data, nhưng phá lợi ích caching và có thể quá tải database.

### 24.1. Single-flight

Một node ứng dụng có thể gộp các yêu cầu cùng key thành **một in-flight lookup**:

~~~text
Client A ---\
Client B ----> one source read for P999 -> shared result
Client C ---/
~~~

### 24.2. Đừng nhầm single-flight với distributed lock

Single-flight trong JVM chỉ gộp requests ở một instance. Nếu 20 instances cùng miss, vẫn có thể có 20 source queries.

### 24.3. Distributed coalescing

Redis short lease/lock có thể giảm concurrent source reads trên nhiều instances. Nhưng phải xử lý:

- Lock owner crash.
- Lease timeout.
- Reader khác không được chờ vô hạn.
- Source lookup lỗi.
- Fencing khi late cache fill.

Không xem SET NX lock là nguyên tử với truy vấn NoSQL bên ngoài. Generation/version guard vẫn cần nếu correctness yêu cầu.

### 24.4. Bảo vệ khi quá tải

Có thể sử dụng request queue bounded, deadline, rate limit và stale-positive policy được xác định rõ. Không biến mọi lỗi DB thành negative để “giữ uptime”.

## 25. Negative cache với local cache Caffeine

Caffeine là thư viện in-process cache trong Java. Một mô hình:

~~~java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Duration;

public record NegativeObservation(String sourceName) {}

Cache<String, NegativeObservation> missingProducts =
        Caffeine.newBuilder()
                .maximumSize(20_000)
                .expireAfterWrite(Duration.ofSeconds(8))
                .build();
~~~

### 25.1. Đọc cache

~~~java
String key = tenantId + ":" + productId;
NegativeObservation negative = missingProducts.getIfPresent(key);

if (negative != null) {
    // May return NOT_FOUND only under the endpoint's freshness policy.
}
~~~

### 25.2. Khi source xác nhận absent

~~~java
missingProducts.put(key, new NegativeObservation("product-owner"));
~~~

Không put khi source timeout hoặc read path không đủ consistency.

### 25.3. Khi product được tạo

~~~java
missingProducts.invalidate(key);
~~~

Nhưng invalidation ở một JVM không tự xóa negative entries trong các instances khác.

### 25.4. Multi-instance consequence

~~~text
App A local cache: NEGATIVE(P101).
App B local cache: NEGATIVE(P101).
Product created via App C.
Only App C invalidates its local cache.
~~~

A và B tiếp tục trả 404 đến TTL hết, trừ khi có event broadcast/invalidation cho mọi instances hoặc read bypass.

### 25.5. expireAfterWrite khác expireAfterAccess

Đối với negative cache, expireAfterWrite thường dễ lý giải stale upper bound hơn. Nếu expireAfterAccess liên tục gia hạn khi key được hỏi, một kết luận sai có thể được giữ rất lâu.

### 25.6. Caffeine cache loader và exception

Một loader cần phân loại NOT_FOUND thành value sentinel nếu muốn lưu negative. Không catch mọi exception rồi trả một sentinel absent, vì sẽ che lỗi source. Khi dùng cache async/loading API, cũng cần xét behavior khi concurrent callers cùng load và timeout.

## 26. Spring Cache: lưu null có thể tạo negative cache ngoài ý muốn

Một service có:

~~~java
@Cacheable(cacheNames = "products", key = "#productId")
public Product findProduct(String productId) {
    return repository.findById(productId).orElse(null);
}
~~~

Tùy **CacheManager** và cấu hình cache, null có thể được lưu dưới dạng sentinel hoặc bị từ chối, thay vì chỉ coi là cache miss.

### 26.1. Vì sao phải kiểm tra framework?

Một số cache implementations hỗ trợ cache null, một số không. Nếu method trả null cho NOT_FOUND và cấu hình cache null với TTL dài, đó là negative caching ngay cả khi team không gọi tên như vậy.

### 26.2. Annotation không tự phân loại lỗi

Nếu repository chuyển timeout thành null, framework có thể lưu null đó. Sửa đúng ở boundary: không đồng nhất **source unavailable** và **not found**.

### 26.3. Hai TTL trong một cache name?

Nếu CacheManager gán một TTL cho mọi entries trong cache, positive và negative dùng chung TTL khi cùng cache. Muốn khác TTL, có thể:

- Tách positive và negative caches.
- Dùng custom cache abstraction/policy.
- Dùng Redis commands hoặc CacheManager hỗ trợ per-entry expiry.

### 26.4. Ví dụ tránh lưu null

~~~java
@Cacheable(
    cacheNames = "existingProducts",
    key = "#tenantId + ':' + #productId",
    unless = "#result == null"
)
public Product getExisting(String tenantId, String productId) {
    return repository.findExisting(tenantId, productId);
}
~~~

Đoạn này minh họa policy **không cache null**, chứ chưa phải negative caching tối ưu. Khi cần negative TTL riêng, thiết kế một đường sentinel/negative cache có chủ đích.

### 26.5. Key phải bao gồm tenant/security scope

Nếu dữ liệu có thể khác giữa tenants/users, chỉ dùng productId có thể rò thông tin hoặc trả 404 sai. Cache key và authorization cần có contract phù hợp.

### 26.6. Spring Cache có thể có nhiều tầng

Một ứng dụng vừa dùng local Caffeine vừa Redis, còn phía trước có CDN. Xóa Redis nhưng không xóa local/CDN negative sẽ làm kết luận 404 tiếp tục tồn tại.

## 27. Bloom filter và negative caching

Một **Bloom filter** có thể trả lời:

~~~text
Definitely not in set
Possibly in set
~~~

Với bộ lọc được xây đúng và tập dữ liệu được cập nhật phù hợp, nó có thể tránh truy vấn DB cho các key chắc chắn không nằm trong tập.

### 27.1. False positive

Bloom filter có thể nói *possibly present* dù key không tồn tại; khi đó vẫn truy vấn source.

### 27.2. False negative không nên có trong mô hình chuẩn

Bloom filter truyền thống không có false negative **cho những key đã được thêm đầy đủ vào filter**, nếu dữ liệu filter không bị hỏng hay cập nhật thiếu.

Nhưng nếu filter được dựng trước khi sản phẩm mới được tạo và chưa được cập nhật, nó có thể trả “definitely not” cho một key **mới tồn tại trong source**. Đó là lỗi freshness/synchronization của filter, không phải xác suất lý thuyết false negative trong tập mà filter đã biết.

### 27.3. Filter rebuild/incremental updates

Muốn dùng Bloom filter trong hệ cho phép create:

- Update filter khi item mới được tạo.
- Hoặc định kỳ rebuild với cutoff/watermark.
- Hoặc bypass filter cho newly-created keys/session.

### 27.4. Không dùng filter làm authority

Bloom filter không thay primary-key read khi trả lời business operation quan trọng như unique username hoặc reservation.

### 27.5. Filter giúp chống random-key penetration

Với rất nhiều request tới random IDs không tồn tại, Bloom filter ở gateway có thể giảm DB lookups, nhưng cần quản trị memory, false-positive rate, rebuild và update consistency.

## 28. MongoDB: đọc từ secondary rồi cache NOT_FOUND

Một replica set có primary và secondaries:

~~~text
Primary:   Product P101 vừa được insert.
Secondary: Chưa nhận/apply write P101.
~~~

### 28.1. Negative caching qua secondary

~~~text
POST /products/P101 -> write acknowledged theo contract.
GET /products/P101 -> read preference = secondary.
Secondary -> NOT_FOUND vì replication lag.
Redis -> NEGATIVE(P101) TTL=30 minutes.
~~~

Một độ trễ replication ngắn bị biến thành dữ liệu “không có” trong 30 phút.

### 28.2. Read preference và read concern

MongoDB hỗ trợ nhiều đường đọc và read concern/session semantics. Tùy yêu cầu, GET sau CREATE có thể cần đọc từ primary với cấu hình/session phù hợp hoặc chờ cơ chế đảm bảo độ mới của dữ liệu.

Không tự suy “write majority đã ACK” nghĩa mọi secondary lập tức nhìn thấy write.

### 28.3. Change streams và invalidation

Một index/cache consumer có thể dùng change stream để nhận insert/update/delete và invalidate Redis. Nhưng:

- Consumer có thể lag.
- Resume token/change history có retention hữu hạn.
- Source write không atomic với Redis DEL.
- Một read cũ vẫn có thể fill negative sau invalidate.

Do đó event invalidation phối hợp với TTL và stale-fill protection khi freshness quan trọng.

### 28.4. Đọc từ source canonical thay vì external search

GET by _id nên ưu tiên một đường có consistency contract đúng với resource, không dùng search index chỉ vì API search đã có sẵn. Search không thấy document có thể chỉ vì indexing lag.

### 28.5. Transaction chưa commit

Một read không thấy record đang được tạo trong transaction chưa commit là bình thường. Không cache NOT_FOUND qua một giao thức có thể trả success CREATE ngay sau đó mà không có invalidation/bypass.

## 29. DynamoDB: GSI eventual và negative cache

Giả sử DynamoDB là nguồn chuẩn:

~~~text
Table Users:
  PK = USER#U101
  emailCanonical = alice@example.test

GSI byEmail:
  PK = alice@example.test
~~~

### 29.1. GSI có thể trễ

Sau PutItem trên base table, GSI có thể chưa có entry ngay. Query GSI theo email trả rỗng không chứng minh user không tồn tại ở table.

### 29.2. Negative cache qua GSI khuếch đại lag

~~~text
t0 PutItem succeeds.
t1 Query byEmail GSI -> empty.
t2 Cache "email absent" for 1 hour.
t3 GSI catches up in seconds.
t4 API still returns absent from Redis for 1 hour.
~~~

### 29.3. Strongly consistent GetItem ở base table

DynamoDB hỗ trợ strongly consistent reads cho những API/nguồn trong phạm vi được hỗ trợ, nhưng **GSI không hỗ trợ strongly consistent read**. Nếu có canonical key, một GetItem phù hợp có thể trả lời chính xác hơn về sự tồn tại.

### 29.4. Username uniqueness không được dựa vào query GSI

Hai requests:

~~~text
Query GSI email=alice -> none.
Put user U101.

Query GSI email=alice -> none.
Put user U102.
~~~

có thể tạo hai users nếu uniqueness không được enforce ở một conditional key/transaction authority.

Thiết kế tốt hơn:

~~~text
PK = UNIQUE_EMAIL#T17#alice@example.test
Conditional PutItem if absent
~~~

Sau đó liên kết claim với user creation theo transaction/workflow phù hợp.

### 29.5. Global Tables và multi-Region

Ở chế độ Global Tables eventual, Region A và B có thể nhìn các trạng thái khác nhau trong lúc replication. Không dùng negative cache ở Region B để quyết định một identifier chắc chắn chưa được claim toàn cầu nếu consistency mode không bảo đảm.

### 29.6. DynamoDB TTL

Một item hết hạn TTL không nhất thiết biến mất ngay lập tức; TTL deletion là asynchronous. Query trả absent, present hoặc stale theo đường đọc và trạng thái TTL đều cần được hiểu theo API/business contract, không coi expiresAt đơn thuần là bằng chứng physical deletion hoàn tất.

## 30. Cassandra/ScyllaDB: consistency level và negative caching

Trong một cụm nhiều replicas, việc đọc có thể sử dụng các mức consistency khác nhau.

### 30.1. Read ở mức thấp

Một read với consistency level cho phép ít replicas có thể nhìn dữ liệu cũ khi một mutation mới chưa hội tụ. Nếu trả NOT_FOUND, cache âm kéo dài có thể che bản ghi.

### 30.2. Read QUORUM không phải phép màu mọi tình huống

Quorum read/write có giao nhau trong một số cấu hình, nhưng bảo đảm quan sát và xử lý concurrent writes còn phụ thuộc topology, timestamps, replication semantics, repair và protocol.

Không lấy công thức quorum đơn giản để khẳng định mọi truy vấn Cassandra đều linearizable.

### 30.3. LWT cho unique claim

Cassandra/ScyllaDB có lightweight transactions/conditional statements ở phạm vi được hỗ trợ. Nếu cần quyết định “username chưa được ai sở hữu”, dùng conditional command tương ứng chứ không dựa vào negative cache của một SELECT.

### 30.4. Tombstones và xóa

Storage tombstones có vai trò ngăn dữ liệu đã xóa bị hồi sinh khi các replicas/compaction/repair phối hợp. Cache NOT_FOUND không thay storage tombstone, và negative TTL không quyết định thời điểm tombstone được purge.

### 30.5. Query tables khác nhau

Một user có thể xuất hiện trong users_by_id nhưng chưa có ở users_by_email do denormalization pipeline hoặc application dual-write lỗi. Negative cache từ users_by_email cần được hiểu là **query-view absent**, không tự chứng minh user không tồn tại ở source of record.

## 31. Elasticsearch/OpenSearch: “no hits” không phải “document chưa từng tồn tại”

Search engine có index refresh và pipeline bất đồng bộ.

### 31.1. Refresh latency

~~~text
Source product v8 committed.
Indexer receives event.
Search has not refreshed.
Search query -> 0 hits.
~~~

Nếu ứng dụng cache “product missing” 20 phút dựa vào search query, vài trăm milliseconds indexing lag biến thành lỗi kéo dài.

### 31.2. Search no hits có nhiều nguyên nhân

- Document chưa được index.
- Search refresh chưa xảy ra.
- Query analyzer không match.
- Filter tenant/status loại document.
- Alias trỏ vào index khác.
- Lỗi schema mapping.
- Consumer CDC đang lag.

Không đồng nhất “không match query” với “canonical item absent”.

### 31.3. Search result có thể negative-cache theo query

Nếu API search chấp nhận eventual freshness, có thể cache empty result ngắn hạn theo **đầy đủ query + filters + tenant + index generation**.

Không dùng một negative entry cho key productId để che endpoint GET authoritative by ID chỉ vì query search vừa empty.

### 31.4. Reindex/cutover

Khi đổi index alias từ products-v1 sang products-v2, một cache empty-result của v1 có thể không còn phù hợp. Cache key nên gắn index generation hoặc invalidate khi cutover.

### 31.5. Xóa rồi recreate

Nếu index cũ có delete nhưng index mới được rebuild từ snapshot trước khi xóa, document có thể hồi sinh. Delete/tombstones và replay watermark cần được bảo vệ; cache negative không thể giải quyết thiếu dữ liệu trong index.

## 32. Negative caching trong multi-level cache

Một đường đọc có thể qua:

~~~text
Browser cache
    |
CDN / API gateway
    |
Application local Caffeine
    |
Redis cluster
    |
NoSQL source
~~~

### 32.1. Tầng nào đang giữ 404?

Nếu Redis đã xóa negative nhưng Caffeine còn key, API vẫn có thể trả 404. Nếu cả hai đã xóa mà CDN cache 404 10 phút, user vẫn không thấy resource.

### 32.2. TTL tổng không đơn giản là TTL lớn nhất

Nếu các tầng nối tiếp giữ entries và **có thể tái nạp từ một tầng stale**, 404 có thể bị kéo dài qua nhiều chu kỳ. Ví dụ local cache hết hạn nhưng lại nạp negative từ CDN/proxy/Redis stale rồi tự gia hạn TTL mới.

Để đặt bound, phải xem:

- Tầng nào có quyền tạo negative mới?
- TTL áp dụng từ source observation hay từ cache refill?
- Có stale-while-revalidate/stale-if-error không?
- Có invalidation fan-out?
- Khi nạp từ tầng cũ có giữ original observedAt không?

### 32.3. Giữ original observation age

Nếu một negative entry được quan sát lúc t0, downstream không nên tùy ý xem t1 là một source observation mới. Có thể lưu observedAt và maxStaleUntil để không reset TTL logic khi chuyển tầng.

### 32.4. HTTP caching

Với public resources, CDN có thể cache 404 nếu cấu hình cho phép. Với authenticated/tenant data, cần cẩn trọng Cache-Control: private/no-store và Vary/authorization behavior theo API contract.

### 32.5. Invalidate nhiều tầng

Một resource CREATE có thể cần:

~~~text
Invalidate Redis key
Publish invalidation event to app instances
Purge CDN/surrogate key where applicable
Return source commit version for session reads
~~~

Không nhất thiết có mọi tầng; quan trọng là biết tầng nào tồn tại và cách giải thích stale.

## 33. Cache key: chính xác về tenant, query, quyền và version

### 33.1. Key theo primary resource

~~~text
product:{tenant=T17}:id=P101
~~~

### 33.2. Key theo query

~~~text
search:{tenant=T17}:qHash=H:filtersHash=F:indexGen=7
~~~

Query empty cache phải tính cả:

- Query text canonical.
- Filters, locale và language.
- Tenant/authorization scope.
- Paging/sort (khi ảnh hưởng response).
- Index/schema generation.

### 33.3. Key theo user và policy

Nếu một user không có quyền xem P101 nhưng user khác có quyền, một cached 404 global theo productId có thể làm user có quyền bị từ chối sai.

Không chỉ “thêm userId vào key” rồi bỏ authorization. Quyền thay đổi theo role, membership, session, policy version; cần design cache policy có khả năng invalidation khi quyền thay đổi.

### 33.4. Canonicalization

~~~text
P101
p101
P101<space>
~~~

có thể được xem là cùng ID hoặc khác ID theo domain. Chuẩn hóa trước cache lookup và trước source lookup theo **cùng một rule**, tránh cache fragmentation hoặc key collisions.

### 33.5. Không dùng raw PII trong key nếu không cần

Email/phone trong Redis key có thể xuất hiện trong logs, monitoring và memory dumps. Dùng HMAC/opaque identifier hoặc hashing phù hợp và bảo vệ salts/keys theo security policy.

### 33.6. Key-space cardinality

Một attacker tạo hàng triệu random keys có thể làm negative cache chiếm RAM. Cần per-scope quotas, max entries, admission và monitoring cardinality.

## 34. Xóa, tombstone, recreate và negative cache

### 34.1. Delete có thẩm quyền

~~~text
DELETE P101 commit -> resource no longer active.
~~~

API có thể trả NOT_FOUND/410 sau đó theo contract. Nếu ID có thể được tái sử dụng hoặc undo delete, negative phải có invalidation khi recreate/restore.

### 34.2. Soft delete

Một document:

~~~json
{
  "productId": "P101",
  "deletedAt": "2026-11-14T08:30:00Z",
  "state": "DELETED"
}
~~~

Resource có thể còn trong source nhưng bị ẩn đối với người dùng. Cache negative phải hiểu đây là **not visible under policy**, không phải physical absence.

### 34.3. Tombstone khác NOT_FOUND

Storage tombstone bảo vệ propagation xóa. Business tombstone có thể ghi ID không được tái sử dụng, generation và thời điểm xóa. Cache negative là kết quả dẫn xuất, có thể bị evict và rebuild.

### 34.4. Bảo vệ event cũ

~~~text
v5: Product active
v6: Product deleted
v7: Product recreated
~~~

Một cache projector không được apply event v6 đến muộn để xóa v7. Dùng version/generation và kiểm tra thứ tự nguồn.

### 34.5. Quyền riêng tư

Không cache dữ liệu nhạy cảm đã xóa với positive TTL dài mà không có purge. Negative caching không cứu được positive stale còn chứa PII; deletion workflow cần fan-out tới các tầng.

### 34.6. Không tái sử dụng ID là một lựa chọn hữu ích

Nếu domain quy định ID đã xóa không bao giờ được cấp lại, negative về “ID không có resource active” có thể ổn định hơn. Tuy vậy permissions, restore và eventual read vẫn cần xem xét theo contract.

## 35. Negative caching khi create command trả UNKNOWN

Một client:

~~~text
POST /orders (operationId=CREATE-O101)
   -> timeout
GET /orders/O101
   -> NOT_FOUND từ một read replica
~~~

Có thể POST đã commit nhưng response mất. Đọc từ replica chậm rồi cache negative 30 phút sẽ khiến client tưởng create thất bại và retry với ID mới.

### 35.1. Không suy timeout là create thất bại

Trạng thái đúng có thể là **UNKNOWN**. Cần lookup operationId hoặc đọc nguồn có thẩm quyền/consistency phù hợp.

### 35.2. Idempotency

Retry CREATE với **cùng operationId** giúp service trả kết quả cũ nếu đã commit; không tự sinh một business operation mới.

### 35.3. Pending lookup

Nếu source chưa có Order nhưng workflow đang chạy:

~~~text
GET /operations/CREATE-O101 -> PENDING
~~~

có thể đúng hơn việc negative-cache Order NOT_FOUND và giả vờ không còn khả năng xuất hiện.

### 35.4. Không cho negative ảnh hưởng quyết định thanh toán

Nếu Payment/Order projection thiếu item, đừng tự kích hoạt capture lần nữa. Domain business invariants nằm ở authoritative service/idempotency ledger, không ở negative cache.

## 36. Metrics: làm sao biết negative cache đang giúp hay đang hại?

Một dashboard chỉ có **cache hit rate** là không đủ. Negative hit rate cao có thể là tốt (giảm DB reads) hoặc xấu (user liên tục bị trả 404 sai).

| Nhóm | Metric ví dụ | Câu hỏi |
|---|---|---|
| Cache lookup | positive_hit_total | Bao nhiêu kết quả có value từ cache? |
| Cache lookup | negative_hit_total | Bao nhiêu requests dùng kết luận absent đã cache? |
| Cache lookup | miss_total | Bao nhiêu requests vẫn phải đọc nguồn? |
| Source result | authoritative_not_found_total | Source thực xác nhận absent bao nhiêu lần? |
| Source errors | source_timeout_total / source_error_total | Lỗi nguồn có bị biến thành 404 không? |
| Cache write | negative_fill_total | Đã ghi negative entries bao nhiêu lần? |
| Cache write | stale_fill_rejected_total | Generation/version đã chặn bao nhiêu stale fills? |
| Invalidation | cache_invalidation_total | Có phát invalidation khi create/update/delete không? |
| Invalidation | invalidation_failure_total | Có entries chưa được thu hồi? |
| Freshness | negative_false_hit_total | Cache trả absent nhưng source có resource? |
| Freshness | negative_stale_duration_seconds | Resource bị che sau khi create bao lâu? |
| Load | extra_source_reads_total | Stampede/negative misses tạo bao nhiêu reads? |
| Capacity | cache_keys_by_kind / memory | Negative entries có chiếm cache quá mức? |
| Business | create_then_get_404_total | POST thành công nhưng GET by ID trả 404? |
| Security | resource_enumeration_attempts | Có traffic đoán IDs/permissions bất thường? |

Các tên metric là đề xuất, không phải tên chuẩn của Redis, Caffeine hay NoSQL engine.

### 36.1. False-negative cache hit đo thế nào?

Không nên query database cho **mọi** negative hit, vì mất lợi ích caching. Có thể:

- Lấy mẫu một tỷ lệ nhỏ.
- Đối soát background với authoritative source.
- Kiểm tra create-to-first-visible SLO.
- Theo dõi các trường hợp phát sinh business error.

Việc shadow read để so sánh phải tôn trọng authorization và dữ liệu nhạy cảm.

### 36.2. Đo nguyên nhân 404

Tách:

~~~text
404_cache_negative
404_authoritative_source
404_filtered_by_policy
404_search_no_hits
~~~

Không gộp tất cả vào một HTTP 404 counter rồi khó biết nguồn sai ở đâu.

### 36.3. Đo lag trước khi cache âm

Nếu source lookup đi qua eventual replica, theo dõi replication lag, GSI propagation lag hay CDC/index lag. Một giai đoạn lag tăng đột biến là lý do giảm/tắt negative caching ở đường đó.

### 36.4. Đo cache entry tuổi đời

TTL remaining hữu ích, nhưng observedAt/source revision còn cho biết entry thực chất phản ánh nguồn từ khi nào. Đặc biệt trong multi-level cache, observedAt không nên tự reset khi copy giữa các tầng.

### 36.5. Negative hit rate không phải success rate

Nếu positive hits giảm và negative hits tăng sau deployment, có thể là sản phẩm bị mất khỏi search/cache key namespace, chứ không phải hiệu năng cải thiện.

## 37. SLO cho khả năng thấy dữ liệu mới

### 37.1. Create-to-visible latency

Định nghĩa:

\[
\text{VisibilityLag}
=\text{first successful authoritative GET time}
-\text{source commit time}.
\]

Với API có cache, điều cần đo cho người dùng thường là **first successful user-visible GET time** qua cache path chứ không chỉ source GET.

### 37.2. Ví dụ SLO

~~~text
GET /products/{id} after successful create:
  read-your-writes for creating session

Public catalog search:
  99% new products visible within 15 seconds

Negative cache:
  maximum fixed TTL 5 seconds,
  plus invalidation on create
~~~

Đây là các mục tiêu minh họa. Không tự tuyên bố chúng được bảo đảm bởi Redis; cần đo deployment thực tế.

### 37.3. Bảo đảm mạnh hơn TTL

Nếu read-your-writes phải tức thời, một TTL âm tối đa 5 giây vẫn cho phép sai trong 5 giây. Dùng session bypass, version-aware read, write-through và đường đọc nguồn phù hợp.

### 37.4. SLO khi invalidation event lag

Nếu invalidation pipeline chậm 30 giây nhưng TTL âm 5 giây, nhiều negative entries hết hạn trước event. Nếu TTL âm 30 phút, invalidation lag sẽ ảnh hưởng lớn hơn khi sự kiện bị mất.

### 37.5. SLO và giờ cao điểm

Không chỉ đo median visibility. Các ca lag cao hoặc source error dưới tải mới gây sự cố người dùng. Theo dõi p95/p99 và maximum observed stale duration theo nghiệp vụ quan trọng.

## 38. Công thức tính tải và tỷ lệ cache âm

Giả sử một endpoint nhận:

~~~text
Total requests:             100,000/minute
Positive cache hits:        60,000
Negative cache hits:        25,000
Misses requiring source:    15,000
~~~

Nếu không có bypass khác, cache hit rate:

\[
\frac{60{,}000 + 25{,}000}{100{,}000} = 85\%.
\]

Tỷ lệ negative hits trong tổng requests:

\[
\frac{25{,}000}{100{,}000} = 25\%.
\]

### 38.1. Chưa đủ chứng minh đúng đắn

Một negative hit rate 25% có thể là do clients nhập sai ID nhiều, hoặc do source lag khiến hàng nghìn records mới bị cache 404.

### 38.2. Chi phí false negatives

Giả sử 0,1% negative hits là sai:

\[
25{,}000\times 0.001 = 25
\]

requests/phút có thể bị trả NOT_FOUND sai trong ví dụ. Tùy use case, 25 lỗi/phút có thể không chấp nhận được.

### 38.3. Chọn số liệu theo logical user journey

Nếu user tạo product rồi refresh 10 lần và đều thấy 404, đó là **một product bị che** nhưng mười requests sai. Theo dõi cả số unique resources bị ảnh hưởng và số requests/user journeys bị ảnh hưởng.

### 38.4. Cache misses không đồng nghĩa database misses

Ứng dụng có nhiều tầng cache, single-flight hoặc batch read. Một local cache miss có thể được đáp ứng bởi Redis positive, không cần truy vấn database.

## 39. Runbook khi “resource đã tạo nhưng GET vẫn 404”

### Bước 1 — Xác minh source có thẩm quyền

Tra bằng primary/business key đã canonicalized, tenant scope và đường đọc có consistency phù hợp. Không chỉ dùng search query hay stale replica để khẳng định nguồn có record.

### Bước 2 — Thu thập operation metadata

~~~text
tenantId
resourceId
operationId
source commit timestamp/revision
cache key or redacted key hash
request trace IDs
cache layer and node identity
~~~

Không log PII/raw credentials; dùng IDs và sampling phù hợp.

### Bước 3 — Xác định tầng trả 404

~~~text
Browser/CDN?
Gateway?
Local Caffeine?
Redis?
Search index?
Authoritative read path?
~~~

### Bước 4 — Xem TTL và generation

Kiểm tra:

- Cache entry là NEGATIVE hay MISS?
- TTL còn bao lâu?
- observedAt trước hay sau create?
- Có invalidation event?
- Generation/version có thay sau commit?
- Có reader cũ ghi stale negative sau invalidate không?

### Bước 5 — Khôi phục đúng phạm vi

Có thể:

- Invalidate đúng key và các tầng.
- Bypass negative cache cho resource/tenant đang ảnh hưởng.
- Tạm tắt negative fill nếu pipeline lỗi.
- Replay invalidation từ outbox/CDC.
- Dùng source read trong đường API critical.

Không FLUSHALL Redis tùy tiện nếu cache chứa dữ liệu/locks của nhiều dịch vụ không liên quan.

### Bước 6 — Kiểm tra sau khắc phục

Đọc resource qua cùng đường HTTP của user (đúng quyền), xác nhận version và invalidation. Đồng thời kiểm tra các resources mới khác không bị ảnh hưởng.

### Bước 7 — Điều tra nguyên nhân gốc

Các khả năng:

- Negative TTL quá dài.
- Không invalidate khi create.
- Reader stale fill sau invalidate.
- Cache local/CDN còn negative.
- GSI/secondary/search lag.
- Source timeout bị chuyển thành null.
- Wrong tenant/cache key normalization.
- Event publisher/consumer thất bại.
- Một soft-deleted flag/filter chưa đúng.

### Bước 8 — Chặn tái diễn

Thêm fault-injection tests, negative/positive separate TTL, conditional fill, source errors classification, create-to-GET SLO và cảnh báo business-level.

## 40. Test matrix cho negative caching

| Kịch bản | Thiết lập | Kết quả kỳ vọng |
|---|---|---|
| Missing key lặp | GET P999 nhiều lần | Một số source reads giảm, cache negative hết TTL |
| Create after NOT_FOUND | Cache negative rồi CREATE | Read-your-writes theo contract; không giữ 404 dài |
| Delete then recreate | DELETE, cache negative, CREATE lại | Không để tombstone/negative cũ che generation mới |
| Stale fill race | Reader nhận NOT_FOUND trước commit, SET sau invalidation | Generation/version guard chặn |
| Source timeout | Database không phản hồi | Không cache như NOT_FOUND |
| Source 503 | Driver lỗi tạm thời | Trả lỗi/retry policy, không negative |
| Unauthorized | User B không có quyền | Không làm user A có quyền bị global cached 404 |
| Wrong tenant | Cùng productId ở T17/T18 | Cache keys không va chạm |
| Secondary lag | Read secondary chưa thấy create | Không cache canonical absence trái policy |
| DynamoDB GSI lag | Query GSI empty sau PutItem | Không dùng GSI empty để enforce uniqueness |
| Search refresh lag | Index chưa refresh | Empty search cache không che GET by ID |
| Concurrent miss | 1000 GET một key | Coalescing/backpressure giảm DB burst |
| Random missing keys | 1 triệu random IDs | Cache không nở vô hạn |
| Cache outage | Redis unavailable | Không đổi outage thành NOT_FOUND |
| Local cache stale | App B chưa nhận invalidation | Bypass/TTL/event fan-out đúng |
| CDN negative | CDN cache HTTP 404 | Purge/Cache-Control đúng |
| TTL sliding | Hits liên tục | Negative không sống mãi ngoài stale policy |
| Bulk import | Hàng nghìn IDs mới | Invalidation hoặc tắt negative theo kế hoạch |
| Reindex | Đổi search generation | Cache empty-results cũ không ảnh hưởng index mới |
| Outbox lag | CREATE commit, event chậm | Đường đọc critical vẫn đúng; lag được quan sát |

### 40.1. Test lỗi sau source commit

~~~text
1. CREATE succeeds in database.
2. Simulate process crash before Redis invalidation.
3. Retry/outbox eventually invalidates.
4. GET creating session must satisfy its contract.
~~~

Đây là case quan trọng; chỉ thử lỗi trước commit không đủ.

### 40.2. Test race bằng synchronization barrier

Có thể dùng test-controlled barriers để giữ reader giữa source NOT_FOUND và cache SET, cho writer commit và invalidate, rồi thả reader. Điều kiện này giúp tái hiện deterministic một bug khó gặp trong test thông thường.

### 40.3. Test multi-instance

Chạy hai hoặc nhiều service instances cùng local cache, không chỉ unit test một process. Verify invalidation fan-out và TTL policy.

### 40.4. Đối soát kết quả bằng source

Không chỉ assert API trả HTTP 200 sau CREATE; so business resource ID/version với source để bảo đảm không đọc nhầm một document cũ hoặc tenant khác.

## 41. Các anti-pattern phổ biến

| Anti-pattern | Hậu quả | Thay bằng |
|---|---|---|
| Cache null với positive TTL 24 giờ | Resource mới bị ẩn lâu | Negative TTL riêng ngắn và invalidate |
| Catch exception rồi trả Optional.empty | Outage thành 404 dai dẳng | Phân loại NOT_FOUND vs ERROR |
| GET nil từ Redis nghĩa DB không có | Nhầm cache miss với source absence | Query source |
| Query eventual GSI rồi cache absent như authoritative | Create có thật bị che | Đọc source đúng consistency |
| Search no hits nghĩa record không tồn tại | Indexing lag kéo dài qua cache | Phân biệt search vs canonical GET |
| Redis DEL trước CREATE commit | Reader tái nạp negative | Invalidate sau commit |
| Chỉ Redis DEL sau CREATE | Stale reader có thể SET sau DEL | Generation/version guard khi cần |
| SET negative không có EX/PX | Không có freshness bound | Atomic SET với TTL |
| Sliding TTL cho negative hot key | “Không tồn tại” sống vô hạn | Fixed expiry, observation-age limit |
| Cache key chỉ productId dù multi-tenant | Cache poisoning/rò scope | Tenant-scoped key |
| Cache 403/401 như global NOT_FOUND | User hợp lệ bị chặn | Permission-aware policy |
| Cache 429/503/timeout thành 404 | Che lỗi hệ thống | Retry/backoff/error |
| Duplicate layer TTL không được theo dõi | 404 còn sau khi Redis đã xóa | Cache inventory và purge propagation |
| Cho negative entries lấp đầy RAM | Eviction positive và tăng tải | Bounded admission/rate limiting |
| Cache username availability để quyết định uniqueness | Hai users cùng đăng ký được | Conditional claim/transaction |
| Không nhận delete/tombstone events | Dữ liệu đã xóa bị giữ/hồi sinh | Delete propagation và version |
| Reindex nhưng giữ empty search cache thế hệ cũ | Search mới vẫn trả rỗng | Generation key/invalidate |
| Dựa vào cache hit rate duy nhất | Không thấy false-negative impact | Source sampling và create-to-GET SLO |
| Negative cache không có on-call owner | Sự cố kéo dài khó truy vết | Metric, alerts, runbook |
| Dùng Redis FLUSHALL để chữa một key | Phá nhiều workloads khác | Targeted invalidate/bypass |

## 42. Checklist quyết định có nên negative-cache một endpoint

### 42.1. Về dữ liệu

- Resource có thể được tạo lại sau khi NOT_FOUND không?
- ID có thể tái sử dụng sau DELETE không?
- Có soft delete, restore hoặc delayed publish không?
- Result là canonical key lookup hay query vào index eventual?

### 42.2. Về nguồn

- Source read có đủ consistency cho kết luận absent không?
- Timeout/5xx/403 có đường đi riêng không?
- Có version/revision/generation hoặc operationId hỗ trợ không?
- Các writers có phát invalidation sau commit không?

### 42.3. Về cache

- Positive/negative có TTL riêng không?
- Có fixed maximum age, tránh sliding indefinite không?
- Cache keys đã bao gồm tenant/query/permission scope chưa?
- Có nhiều tầng cache/CDN hoặc regional cache không?
- Stale negative fill sau invalidation được chặn như thế nào?

### 42.4. Về vận hành

- Đo negative false hits và create-to-visible latency ra sao?
- Có runbook bypass/disable negative cache khi source lag tăng không?
- Có admission/rate limiting cho random IDs không?
- Có test delayed events, source crash, race và multi-instance không?

### 42.5. Về nghiệp vụ

- Nếu trả sai 404 trong 5 giây, hậu quả có chấp nhận được không?
- Nếu POST commit rồi response mất, GET có trả UNKNOWN/PENDING đúng không?
- Có hành động nhạy cảm đang dựa vào negative như một phép kiểm tra uniqueness/inventory/payment không?
- Có policy xóa dữ liệu nhạy cảm và invalidation xuyên các tầng không?

## 43. Bài tập 1 — phân biệt ba kết quả đọc

Một service dùng MongoDB và Redis. Hãy phân loại các tình huống:

~~~text
A. Redis GET key -> nil
B. Redis GET key -> "N"
C. MongoDB find by _id -> no document, authoritative read
D. MongoDB request -> timeout
E. JSON decoder cannot parse stored document
F. Secondary reports no document during replication lag
~~~

Yêu cầu:

1. Tình huống nào là cache miss?
2. Tình huống nào là negative cache hit?
3. Tình huống nào có thể là authoritative NOT_FOUND?
4. Trường hợp nào không được ghi negative?
5. Với F, cần thay đổi read path hoặc cache policy thế nào?
6. Vì sao chỉ dùng Optional.empty() cho cả C, D, E làm hệ khó gỡ lỗi?

## 44. Bài tập 2 — bug 404 kéo dài sau CREATE

Một API có:

~~~text
Positive TTL = 10 minutes
Negative TTL = 24 hours
Cache invalidation on create = none
~~~

Ngày 14/11 lúc 09:00, user GET P501 chưa có. Lúc 09:01, admin tạo P501 thành công. Lúc 09:02 user GET lại.

1. Kết quả nào có thể được trả ở 09:02?
2. Nếu cache entry không bị eviction/refresh, nó có thể kéo dài tới khi nào?
3. Negative TTL nên được lựa chọn theo điều kiện nào?
4. Nếu API hứa read-your-writes ngay, TTL âm 5 giây có đủ không?
5. Đề xuất thay đổi ở CREATE path, GET path và metrics.

## 45. Bài tập 3 — timeout bị biến thành NOT_FOUND

Một developer viết:

~~~java
public Optional<Product> fetch(String id) {
    try {
        return repository.find(id);
    } catch (Exception ignored) {
        return Optional.empty();
    }
}
~~~

Sau đó Spring Cache lưu null/empty rất lâu.

1. Mô tả điều gì xảy ra nếu database outage 30 giây.
2. Nếu database đã phục hồi, vì sao GET vẫn 404?
3. Thiết kế SourceLookup với Found, NotFound, Unavailable.
4. Trạng thái nào nên cache negative?
5. Những exceptions nào cần phân loại riêng theo driver?
6. Đề xuất alert phát hiện source errors và đột biến negative cache fills.

## 46. Bài tập 4 — race invalidate rồi stale fill

Timeline:

~~~text
t1 R cache miss
t2 R reads source -> NOT_FOUND
t3 W CREATE P501 commits
t4 W invalidates Redis P501
t5 R SET negative P501 TTL=600s
~~~

1. Vì sao invalidation sau commit vẫn chưa đủ?
2. Nếu chỉ dùng Redis SET NX, có chặn được mọi race không?
3. Thiết kế generation G ban đầu bằng 10.
4. Writer phải làm gì với G khi commit?
5. Reader so sánh generation trước khi SET ra sao?
6. Vì sao check generation và SET cần atomic?
7. Phân tích khoảng thời gian giữa source commit và Redis invalidation còn sót lại.

## 47. Bài tập 5 — viết Lua negative fill có điều kiện

Redis có:

~~~text
resource:{T17:P501}:generation = 21
resource:{T17:P501}:data = nil
~~~

Reader trước source lookup đã ghi nhớ expectedGeneration=20. Sau khi source trả NOT_FOUND, nó muốn set N.

1. Viết Lua lấy generation hiện tại.
2. Nếu actual khác expected, return 0 và không SET.
3. Nếu bằng nhau, dùng SET ... NX PX.
4. Giải thích Redis Cluster hash tags cho hai keys.
5. Nếu generation key bị evict/reset về 0, nguy cơ ABA là gì?
6. Negative TTL và generation token giải quyết hai vấn đề khác nhau thế nào?

## 48. Bài tập 6 — positive và negative TTL

Một service có:

~~~text
GET products frequently.
Product names change rarely.
New product IDs appear every minute.
Business accepts catalog search lag 15 seconds.
GET by ID after create should be immediate for creator.
~~~

1. Đề xuất positive TTL và negative TTL có giải thích.
2. Tại sao positive TTL dài không suy ra negative TTL dài?
3. Thiết kế read-your-writes cho creator.
4. Đề xuất invalidation sau CREATE.
5. Nếu invalidation delayed 30 giây, cơ chế nào bảo vệ source GET?
6. Với negative TTL jitter, làm sao không vượt freshness budget?

## 49. Bài tập 7 — cache penetration

Hai patterns:

~~~text
Pattern A:
  10.000 requests cùng hỏi P999.

Pattern B:
  10.000 requests hỏi 10.000 random IDs khác nhau.
~~~

1. Negative caching hiệu quả hơn ở pattern nào?
2. Vì sao pattern B có thể làm đầy Redis?
3. Đề xuất input validation, key admission, quota, rate limiting.
4. Bloom filter giúp gì ở pattern B?
5. Vì sao Bloom filter cần cập nhật khi item mới được tạo?
6. Làm sao tránh dùng Bloom filter làm quyết định unique username?

## 50. Bài tập 8 — stampede khi negative TTL hết hạn

Trong một giây, 2.000 clients hỏi cùng P999 khi negative entry vừa hết hạn.

1. Nếu không có coalescing, có thể có tối đa bao nhiêu source lookups?
2. Single-flight trong một JVM có thể giảm bao nhiêu nếu mọi clients đến cùng instance?
3. Nếu requests phân tán qua 20 instances, single-flight local có giới hạn gì?
4. Nếu dùng distributed lease với Redis, cần xử lý owner crash và TTL ra sao?
5. Vì sao distributed lease không thay generation guard?
6. Đề xuất giới hạn QPS và backpressure khi source overload.

## 51. Bài tập 9 — MongoDB secondary lag

Ứng dụng:

~~~text
POST P501 -> majority write acknowledged
GET P501 -> read secondary
Secondary has not applied P501
Cache NEGATIVE(P501) for 20 minutes
~~~

1. Secondary NOT_FOUND có phải definitive absence không?
2. Majority write ACK có đồng nghĩa mọi secondary đã apply không?
3. Chọn một đường đọc phù hợp để đáp ứng read-your-writes.
4. Change stream invalidation có thể gặp những rủi ro nào?
5. Nếu reader cũ set negative sau invalidation, làm sao xử lý?
6. So sánh source path GET by ID với search index query.

## 52. Bài tập 10 — DynamoDB GSI và username availability

Một người vừa đăng ký email alice@example.test. Table đã ghi, nhưng GSI byEmail chưa bắt kịp.

1. Query GSI empty có nghĩa email chắc chắn còn trống không?
2. Negative cache từ GSI có thể kéo dài lỗi như thế nào?
3. Strongly consistent read nào có thể được dùng ở base table khi đã biết key?
4. Thiết kế conditional unique claim keyed theo tenant+email canonical.
5. Nếu hai Regions với eventual Global Tables cùng nhận claim, có thể dựa vào conditional local để tuyên bố global uniqueness không?
6. Vì sao read cache không bao giờ là nơi enforce unique claim?

## 53. Bài tập 11 — search no hits sau reindex

Một ứng dụng có products-v1 và products-v2. Khi alias chuyển sang v2, cache vẫn giữ:

~~~text
search:{tenant=T17}:q="ban phim":indexGen=1 -> EMPTY
~~~

1. Nếu key không có index generation, user có thể gặp gì?
2. Cần đưa những query filters và locale nào vào cache key?
3. Nếu source có P501 nhưng v2 chưa refresh, nên diễn giải empty result ra sao?
4. Thiết kế ngưỡng freshness cho query empty cache.
5. Có được lấy empty search result làm bằng chứng P501 không tồn tại ở Product Service không?
6. Cache invalidation và search index watermark liên quan thế nào?

## 54. Bài tập 12 — cache nhiều tầng và CDN 404

Đường đọc:

~~~text
Browser -> CDN -> App Caffeine -> Redis -> MongoDB
~~~

Redis negative đã bị DEL sau khi product P501 được tạo, nhưng CDN và App B vẫn trả 404.

1. Liệt kê tầng nào có thể đang cache 404.
2. Vì sao xóa Redis không đủ?
3. Các Cache-Control/Vary decisions nào cần xem?
4. Nếu negative entry được copy giữa tầng với TTL mới mỗi lần, lỗi gì xảy ra?
5. Đề xuất original observedAt/maxStaleUntil.
6. Thiết kế kế hoạch invalidate và kiểm tra end-to-end.

## 55. Bài tập 13 — security: 403 được chuyển thành 404

Một hệ cố ý trả 404 khi user B không được xem document D101, trong khi user A được xem.

1. Vì sao cache 404 với global key D101 là sai?
2. Nếu cache theo userId, quyền thay đổi sau đó gây vấn đề gì?
3. Cache key cần policy/security scope nào?
4. Vì sao authorization vẫn phải được thực thi trước khi trả cached positive?
5. Negative cache latency có thể góp phần resource enumeration như thế nào?
6. Rate limiting/response policy có vai trò gì?

## 56. Bài tập 14 — xóa rồi tái tạo cùng ID

~~~text
P501 version 4 active.
P501 version 5 deleted.
P501 version 6 recreated.
DELETE event v5 arrives at cache after CREATE event v6.
~~~

1. Nếu apply theo arrival order, cache có thể kết luận gì sai?
2. Dùng sourceVersion/generation như thế nào?
3. So sánh storage tombstone, business tombstone và negative cache.
4. Nếu ID không thể tái sử dụng theo business policy, thiết kế thay đổi ra sao?
5. Nếu dữ liệu chứa PII, cần purge những positive caches nào?
6. Vì sao một cache negative không chứng minh việc xóa đã lan truyền hoàn toàn?

## 57. Bài tập 15 — Spring Cache và null result

Một method:

~~~java
@Cacheable(cacheNames = "products", key = "#id")
public Product get(String id) {
    return repo.find(id).orElse(null);
}
~~~

1. Cấu hình CacheManager ảnh hưởng cách null được cache như thế nào?
2. Nếu TTL của products là một giờ, rủi ro với product mới là gì?
3. Dùng unless expression để không cache null.
4. Nếu muốn negative TTL ngắn hơn positive, thiết kế hai caches như thế nào?
5. Với nhiều tenants cùng ID, key hiện tại có vấn đề gì?
6. Nếu repo lỗi và trả null, cần sửa boundary nào?

## 58. Bài tập 16 — Caffeine local negative caching

Ứng dụng có ba JVM instances A/B/C, mỗi instance dùng Caffeine:

~~~text
expireAfterWrite = 10 minutes
maximumSize = 100,000
~~~

1. Nếu CREATE chạy qua C còn A/B có negative, điều gì xảy ra?
2. Có cách nào broadcast invalidation tới các instances?
3. Nếu chỉ hạ TTL xuống 5 giây, có đáp ứng immediate RYW không?
4. expireAfterAccess có thể làm negative sống lâu hơn ra sao?
5. Đề xuất metrics negative entries per instance và cache eviction.
6. Nêu một test multi-instance phát hiện stale negative.

## 59. Bài tập 17 — failover và UNKNOWN outcome

Client gửi POST tạo Order O101. Database đã commit nhưng response mất. Client GET trạng thái qua một replica stale rồi cache 404.

1. Phân biệt FAILED, NOT_FOUND và UNKNOWN trong timeline này.
2. Tại sao retry POST với operationId mới nguy hiểm?
3. Thiết kế endpoint status theo stable operationId.
4. Nếu GET by ID cần minimum revision, client lấy mốc đó từ đâu?
5. Nếu source không cung cấp revision, có thể dùng các cơ chế nào?
6. Tại sao negative cache không được quyết định có charge lại payment hay không?

## 60. Bài tập 18 — thiết kế dashboard

Một hệ báo:

~~~text
100,000 requests/minute.
60,000 positive cache hits.
25,000 negative cache hits.
15,000 cache misses.
0.1% of negative hits sampled are false.
~~~

1. Tính cache hit rate.
2. Tính negative hit rate trên tổng requests.
3. Ước lượng số false-negative responses nếu sample phản ánh quần thể.
4. Vì sao cần theo dõi distinct resources bị che?
5. Thiết kế alert create_then_get_404_total và stale duration p99.
6. Metric nào giúp phân biệt lỗi mapper với replication lag?
7. Nếu hit rate tăng nhưng create-to-visible SLO xấu đi, có nên coi deployment thành công không?

## 61. Bài tập 19 — thiết kế thí nghiệm race deterministic

Hãy xây integration test với một barrier điều khiển hai threads:

~~~text
Reader:
  cache MISS -> source NOT_FOUND -> pause at barrier

Writer:
  CREATE P501 commit -> invalidate cache -> signal barrier

Reader:
  resume -> attempt to cache NEGATIVE
~~~

1. Viết trình tự test trước khi thêm generation guard.
2. Xác định assertion nào cho thấy bug.
3. Thêm generation compare-and-set.
4. Kiểm tra Redis key không trở lại NEGATIVE sau khi writer invalidated.
5. Test thêm positive stale fill tương tự.
6. Nếu Redis failover mất generation state, còn cần cơ chế gì?

## 62. Bài tập 20 — thiết kế negative caching policy cho ba endpoints

Một sản phẩm SaaS có:

~~~text
GET /catalog/search?q=...
GET /orders/{orderId}
GET /users/{userId}/permissions
~~~

Với mỗi endpoint, hãy lập bảng:

1. Authoritative source là hệ nào?
2. Read path có eventual hay strong semantics?
3. Có thể negative-cache ở tầng nào?
4. Cache key gồm tenant/user/query/generation gì?
5. TTL âm tối đa là bao nhiêu theo SLO đề xuất?
6. Khi create/update permission, invalidation hoạt động thế nào?
7. Timeout/403/404 được phân loại thế nào?
8. Có cần bypass nếu client vừa thực hiện command?
9. Những metrics và fault tests nào chứng minh đúng đắn?

## 63. Bài tập 21 — sự cố production giả lập

Sau một bản phát hành, 3% khách hàng thấy “sản phẩm không tồn tại” dù admin xác nhận vừa tạo. Telemetry cho thấy:

~~~text
Redis negative hit ratio:   tăng từ 5% lên 38%.
NoSQL source errors:        tăng trong 2 phút sau deploy.
Invalidation consumer lag:  tăng từ 1s lên 90s.
CDN negative TTL:           10 minutes.
Product API negative TTL:   30 minutes.
~~~

Hãy xây runbook:

1. Khoanh vùng các tenants/resources bị ảnh hưởng.
2. Xác định khả năng timeout bị đổi thành NOT_FOUND.
3. Kiểm tra CDN/local/Redis negative entries.
4. Kiểm tra CREATE commit và outbox/CDC lag.
5. Đề xuất cách giảm ảnh hưởng tức thời mà không dùng Redis FLUSHALL.
6. Đề xuất thay đổi TTL, error classification và generation guard lâu dài.
7. Tạo test regression với network timeout sau source commit.
8. Nêu tiêu chí khẳng định sự cố đã được khắc phục với người dùng.

## 64. Tổng kết: cache kết luận “chưa có” phải có thời hạn và thẩm quyền

**Negative caching là tối ưu hóa hợp lệ khi nhiều requests cùng hỏi một key không tồn tại**, nhưng nó không được biến một quan sát tạm thời hoặc lỗi hệ thống thành một sự thật vĩnh viễn.

Những nguyên tắc cốt lõi:

1. **Cache miss khác cached NOT_FOUND.** Nil từ Redis chỉ cho biết cache chưa có entry; negative entry mới là một kết luận đã lưu trước đó.
2. **NOT_FOUND khác ERROR/UNKNOWN/FORBIDDEN.** Không biến timeout, 503, 403, lỗi deserialize hoặc stale replica thành 404 được cache.
3. **Chỉ cache kết luận có nguồn đủ tin cậy.** Primary-key authoritative read khác GSI eventual hoặc search index vừa chưa refresh.
4. **Negative TTL phải gắn với khả năng xuất hiện của dữ liệu.** Một ID chưa được tạo có thể tồn tại ngay sau đó; TTL dài tạo 404 giả kéo dài.
5. **Không gia hạn negative vô hạn trên mỗi hit.** Fixed expiry/maximum observation age giúp có giới hạn stale rõ ràng.
6. **Invalidate sau khi nguồn commit.** Tất cả đường create/recreate/import/restore cần biết cách thu hồi negative.
7. **DEL không tự chặn stale fill.** Một reader cũ có thể SET NOT_FOUND sau khi writer đã invalidate; generation/version/conditional SET giúp chống race.
8. **Read-your-writes cần đường đọc phù hợp.** Session bypass, source read hoặc minimum revision mới giải quyết yêu cầu đọc thấy dữ liệu vừa tạo.
9. **Multi-level caches có thể giữ 404 ở nhiều nơi.** Redis, Caffeine, CDN và browser có TTL/invalidation riêng.
10. **Cache penetration và stampede là vấn đề tải.** Short negative TTL, bounded admission, single-flight, Bloom filter được đồng bộ và rate limiting có thể giúp, nhưng không đổi business correctness.
11. **Cache key phải giữ tenant, query và permission scope.** Một 404 của user A không được làm user B bị chặn hoặc rò thông tin.
12. **Delete/tombstone không đồng nghĩa negative entry.** Xóa, restore, version và chính sách privacy cần quản trị xuyên storage/cache.
13. **Đo false-negative ảnh hưởng người dùng.** Hit rate cao không có nghĩa tốt nếu resource vừa tạo bị che; hãy đo create-to-visible SLO và stale negative incidents.
14. **Khi lỗi, ưu tiên tìm nguồn có thẩm quyền.** Xác nhận version/commit, xác định tầng giữ 404, targeted invalidate và đối soát events, tránh sửa hoặc xóa cache bừa bãi.

Câu hỏi thiết kế quan trọng nhất là:

> **“Hệ thống đang cache một sự vắng mặt được xác nhận trong phạm vi nào, từ nguồn nào, trong bao lâu; nếu bản ghi xuất hiện ngay sau đó, cơ chế nào bảo đảm kết luận cũ không tiếp tục che dữ liệu thật?”**






