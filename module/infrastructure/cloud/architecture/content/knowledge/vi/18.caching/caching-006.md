# Cache penetration, dữ liệu không tồn tại và negative caching

Cache giúp giảm tải database và rút ngắn thời gian phản hồi bằng cách lưu tạm những kết quả thường được truy cập. Tuy nhiên, một hệ thống cache-aside đơn giản có một điểm yếu: khi khóa được hỏi không có trong cache và cũng không tồn tại ở nguồn dữ liệu, ứng dụng vẫn phải truy vấn database. Nếu cùng một khóa không tồn tại bị gọi liên tục, cache không giúp giảm tải. Kẻ tấn công có thể cố ý tạo ra hàng triệu khóa ngẫu nhiên, hoặc một client lỗi có thể liên tục hỏi cùng một ID sai, làm database quá tải dù cache hit ratio tổng thể có vẻ tốt.

Hiện tượng này thường được gọi là **cache penetration**: request đi xuyên qua cache tới nguồn dữ liệu vì cache không có kết quả có thể sử dụng. Một trường hợp điển hình là **truy vấn dữ liệu không tồn tại**. Kỹ thuật **negative caching** lưu một kết quả âm có thời hạn, chẳng hạn ghi nhận “không tìm thấy bản ghi”, để những request lặp lại không cần hỏi database trong khoảng thời gian đó.

Negative caching là một biện pháp hữu ích, nhưng cần thiết kế cẩn thận. Cache nhầm dữ liệu không tồn tại có thể khiến một bản ghi mới tạo không được nhìn thấy trong một khoảng thời gian; TTL quá dài gây stale negative, TTL quá ngắn không giảm được tải; cache negative không kiểm tra quyền có thể tiết lộ thông tin hoặc gây sai lệch giữa tenant. Bài học này trình bày cách nhận diện, phòng vệ và vận hành các tình huống đó trong kiến trúc cloud.

Bài học thuộc chương **Bộ nhớ đệm** của module **CLOUD_ARCHITECTURE**. Trọng tâm là lựa chọn chiến lược cache phù hợp với hành vi truy cập, bảo vệ nguồn dữ liệu, cân bằng độ trễ, độ tin cậy, bảo mật, khả năng mở rộng và chi phí theo tư duy Well-Architected.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích cache penetration và phân biệt nó với cache miss thông thường, cache breakdown và cache stampede.
2. Phân tích cách truy vấn ID ngẫu nhiên hoặc dữ liệu không tồn tại làm tăng tải nguồn dữ liệu.
3. Thiết kế negative caching với TTL, sentinel value và namespace an toàn.
4. Chọn TTL theo khả năng tạo mới dữ liệu, yêu cầu freshness và chi phí truy vấn.
5. Kết hợp negative caching với validation, rate limiting, Bloom filter và giới hạn tài nguyên.
6. Tránh rủi ro cache poisoning, key collision, tenant leakage và stale negative.
7. Quan sát cache negative hit, nguồn query avoided, memory usage, hit ratio và hiệu quả bảo vệ.
8. Kiểm thử các kịch bản tạo mới/xóa bản ghi, invalidation, concurrency, lỗi cache và lưu lượng bất thường.

## 2. Ôn lại cache-aside và cache miss

### 2.1. Luồng cache-aside cơ bản

Trong mô hình cache-aside, ứng dụng chủ động đọc cache trước. Nếu cache không có dữ liệu, ứng dụng truy vấn nguồn dữ liệu, sau đó ghi kết quả vào cache:

~~~mermaid
flowchart TD
    R[Request] --> C{Cache has key?}
    C -->|Yes| H[Return cached value]
    C -->|No| DB[Query database]
    DB --> FOUND{Record found?}
    FOUND -->|Yes| SET[Write result to cache]
    SET --> RESP[Return result]
    FOUND -->|No| MISS[Return not found]
~~~

Luồng cơ bản thường chỉ cache kết quả dương (positive result). Khi không tìm thấy bản ghi, ứng dụng trả về NOT_FOUND nhưng không lưu dấu kết quả đó. Request tiếp theo với cùng khóa lại truy vấn database.

### 2.2. Cache miss là bình thường

Cache miss xảy ra khi khóa chưa từng được cache, entry đã hết TTL hoặc bị eviction, cache vừa restart/chưa warm, khóa mới xuất hiện hoặc entry bị invalidation sau khi dữ liệu thay đổi. Miss không phải lúc nào cũng là vấn đề. Cache chỉ là lớp tối ưu; nguồn dữ liệu vẫn phải trả lời đúng. Vấn đề xuất hiện khi tỷ lệ miss cao, miss tập trung vào nguồn có chi phí lớn hoặc request miss không được kiểm soát.

### 2.3. Cache penetration

Cache penetration xảy ra khi request đi qua cache và tiếp tục truy vấn nguồn dữ liệu vì cache không có một kết quả hợp lệ cho khóa. Một dạng phổ biến là khóa tương ứng với bản ghi không tồn tại:

~~~text
Request key: user:999999999
Cache lookup: MISS
Database lookup: NOT FOUND
Application: return 404

Request tiếp theo cùng key:
Cache lookup: MISS
Database lookup: NOT FOUND
Application: return 404
...
~~~

Nếu cùng một khóa được hỏi hàng chục nghìn lần, database nhận số lượng truy vấn không cần thiết. Nếu khóa thay đổi ngẫu nhiên mỗi request, cache dương gần như không có cơ hội tái sử dụng kết quả.

### 2.4. Hậu quả

- Database CPU, connection, IOPS và query throughput tăng.
- Latency p95/p99 tăng do hàng đợi connection và query.
- Request hợp lệ bị chậm hoặc lỗi theo hiệu ứng dây chuyền.
- Autoscaling database hoặc compute làm chi phí tăng đột ngột.
- Cache hit ratio có thể vẫn cao nếu phần lớn traffic bình thường hit, khiến dashboard tổng thể che khuất một luồng truy vấn xấu.
- Khi quá tải, retry ở client/gateway có thể khuếch đại traffic và kéo dài sự cố.

## 3. Phân biệt penetration, breakdown và stampede

Ba hiện tượng có thể cùng gây tải lớn lên nguồn dữ liệu nhưng nguyên nhân khác nhau:

| Hiện tượng | Nguyên nhân chính | Mẫu lưu lượng | Biện pháp tiêu biểu |
|---|---|---|---|
| **Cache penetration** | Cache không có entry cho khóa; thường do dữ liệu không tồn tại hoặc khóa tùy ý | Nhiều key không tồn tại, hoặc key miss lặp lại | Negative caching, validation, Bloom filter, rate limit |
| **Cache breakdown** | Một entry nóng hết hạn hoặc bị mất trong khi rất nhiều request cùng cần nó | Một key phổ biến đột ngột miss | Single-flight/lock, refresh-ahead, TTL jitter |
| **Cache stampede** | Nhiều key hết hạn hoặc cache mất dữ liệu cùng lúc khiến nhiều request truy vấn nguồn đồng thời | Một đợt miss đồng loạt | Jitter, warming, request coalescing, stale-while-revalidate |

Ví dụ: người dùng đoán một triệu customer ID ngẫu nhiên không có trong hệ thống là penetration; trang chủ có một key rất nóng vừa hết TTL là breakdown; cache cluster restart khiến hàng triệu key bị mất là stampede/cold-cache surge.

Giải pháp có thể giao nhau nhưng cần xác định nguyên nhân trước. Negative caching không giải quyết việc một key dương cực nóng hết TTL; distributed lock không ngăn kẻ tấn công tạo vô hạn key âm.

## 4. Nguồn gốc của request tới dữ liệu không tồn tại

### 4.1. ID ngẫu nhiên hoặc đoán được

Endpoint như GET /users/{id}, /orders/{id} hoặc /products/{slug} có thể bị gọi với ID tuần tự được đoán, UUID ngẫu nhiên, chuỗi dài hoặc ký tự không hợp lệ, mã thuộc tenant khác, identifier đã bị xóa hoặc hết hiệu lực. Nếu ứng dụng chỉ xác thực cú pháp sơ bộ rồi truy vấn DB cho mọi đầu vào, nguồn dữ liệu trở thành bộ lọc cuối cùng. Điều này vừa tốn tài nguyên, vừa có thể mở ra bề mặt DoS.

### 4.2. Client lỗi hoặc tích hợp ngoài

Một client có thể lặp request sai do cache phía client lỗi, bug retry, bookmark cũ hoặc dữ liệu mapping sai. Một đối tác có thể gửi mã tham chiếu không tồn tại do đồng bộ chậm. Không phải penetration nào cũng là tấn công; quan sát cần phân biệt client hợp lệ, lỗi tích hợp và traffic độc hại.

### 4.3. Dữ liệu bị xóa hoặc vòng đời thay đổi

Một khóa trước đây trả về bản ghi dương có thể trở thành NOT_FOUND sau khi xóa. Nếu cache dương đã invalidated nhưng không tạo negative entry, request lặp lại có thể dồn xuống DB. Ngược lại, negative entry cũ có thể còn tồn tại sau khi bản ghi được tạo lại.

### 4.4. Tenant và authorization

Một ID không tồn tại trong tenant A có thể tồn tại trong tenant B. Một request không có quyền truy cập không nhất thiết tương đương với “không tồn tại” ở góc nhìn nghiệp vụ. Nếu cache negative chỉ dùng ID mà không gắn tenant hoặc authorization scope, nó có thể trả kết quả sai giữa các tenant.

Thiết kế cần phân biệt không có bản ghi trong system of record, bản ghi tồn tại nhưng caller không được phép xem, bản ghi thuộc tenant khác, và bản ghi bị xóa mềm hoặc đang ở trạng thái không hiển thị. Không đưa kết quả authorization nhạy cảm vào cache dùng chung nếu cache key và policy không bảo toàn đúng ranh giới bảo mật.

## 5. Negative caching là gì?

### 5.1. Lưu kết quả âm

Negative caching lưu lại việc một lookup đã được thực hiện và kết quả là không tìm thấy hoặc một kết quả âm đã được xác định. Khi request tương tự xuất hiện trong thời gian hiệu lực, ứng dụng trả kết quả âm từ cache mà không truy vấn lại nguồn.

~~~mermaid
flowchart TD
    R[Request] --> C{Cache lookup}
    C -->|Positive entry| P[Return data]
    C -->|Negative entry| N[Return NOT_FOUND]
    C -->|No entry| DB[Query source]
    DB --> FOUND{Exists?}
    FOUND -->|Yes| POS[Cache positive result]
    POS --> DATA[Return data]
    FOUND -->|No| NEG[Cache negative sentinel with TTL]
    NEG --> MISS[Return NOT_FOUND]
~~~

### 5.2. Sentinel value

Cache cần phân biệt ba tình huống: key chưa tồn tại (miss), key chứa dữ liệu dương, và key xác nhận lookup không có bản ghi (negative hit). Không nên dùng một giá trị null mơ hồ nếu client library hoặc cache backend không phân biệt được null với key miss. Có thể dùng sentinel riêng:

~~~json
{
  "_cacheState": "NOT_FOUND",
  "version": 1
}
~~~

Hoặc một encoded value riêng như __NEGATIVE__. Sentinel phải nằm trong namespace và encoding không thể nhầm với dữ liệu hợp lệ. Nếu dữ liệu thật có thể chứa chính chuỗi sentinel đó, cần một envelope có type rõ ràng.

### 5.3. Pseudocode cache-aside có negative caching

~~~text
function getUser(tenantId, userId):
    key = "user:" + tenantId + ":" + userId
    cached = cache.get(key)

    if cached == POSITIVE:
        return cached.value

    if cached == NEGATIVE_SENTINEL:
        return NOT_FOUND

    user = database.findUser(tenantId, userId)

    if user exists:
        cache.set(key, POSITIVE(user), positiveTTL)
        return user

    cache.set(key, NEGATIVE_SENTINEL, negativeTTL)
    return NOT_FOUND
~~~

Đây là pseudocode. Trong triển khai thực tế cần xử lý timeout, lỗi kết nối cache, lỗi DB, serialization, tenant authorization, TTL và concurrency. Nếu cache gặp lỗi, chính sách fallback phải giới hạn tải nguồn; không nên mặc định mọi request đồng loạt bỏ qua cache và truy vấn database.

## 6. Chọn TTL cho negative entry

### 6.1. TTL ngắn hay dài?

| TTL | Lợi ích | Rủi ro |
|---|---|---|
| Quá ngắn | Dữ liệu mới được nhìn thấy nhanh | Request lặp lại vẫn xuống DB thường xuyên |
| Vừa phải | Giảm truy vấn lặp, giới hạn stale negative | Cần chọn theo vòng đời nghiệp vụ |
| Quá dài | Giảm tải nguồn rất mạnh với key xấu lặp lại | Bản ghi mới tạo có thể bị che khuất lâu |

Không có TTL mặc định phù hợp mọi hệ thống. Một API tra cứu mã đơn hàng có thể dùng TTL âm ngắn vì đơn hàng mới được tạo liên tục. Một lookup mã quốc gia/loại cấu hình gần như tĩnh có thể dùng TTL dài hơn.

### 6.2. Chọn theo khả năng tạo mới dữ liệu

Hãy hỏi: một ID chưa tồn tại có thể được tạo trong vài giây/phút tới không; request NOT_FOUND có được client retry tự động không; có luồng tạo bản ghi nào biết trước ID và có thể invalidation ngay không; có yêu cầu read-after-create không; dữ liệu có thể được import hoặc đồng bộ bất đồng bộ không?

TTL càng dài càng cần invalidation chủ động khi bản ghi được tạo hoặc khôi phục. Nếu không có cơ chế invalidation đáng tin cậy, dùng TTL ngắn để giới hạn thời gian stale negative.

### 6.3. TTL theo loại dữ liệu

| Loại lookup | Đặc tính | Chính sách có thể xem xét |
|---|---|---|
| Customer/booking ID được tạo thường xuyên | Có thể chuyển từ absent sang present sớm | TTL âm ngắn, invalidation khi tạo |
| Slug sản phẩm hiếm thay đổi | Tạo/xóa ít thường xuyên | TTL âm trung bình, purge khi publish |
| Mã cấu hình cố định | Tập giá trị nhỏ, gần tĩnh | TTL dài hơn nếu có version/invalidation |
| Tra cứu ID từ đối tác ngoài | Kết quả có thể thay đổi theo sync | TTL theo SLA đồng bộ, retry có backoff |
| ID ngẫu nhiên không đúng format | Có thể xác định invalid trước DB | Từ chối ở validation, không cần negative cache DB |

### 6.4. Jitter để tránh expiry đồng loạt

Nếu nhiều negative entries được tạo cùng thời điểm với TTL bằng nhau, chúng có thể hết hạn đồng loạt. Có thể thêm jitter:

~~~text
effectiveTTL = baseTTL * random(0.8, 1.2)
~~~

Jitter phân tán thời điểm hết hạn nhưng không thay thế TTL policy. Phải giới hạn khoảng jitter để không vượt freshness requirement hoặc chính sách dữ liệu.

## 7. Invalidation khi dữ liệu được tạo, cập nhật hoặc xóa

### 7.1. Stale negative sau khi tạo mới

Ví dụ: request lookup user 10042, database trả NOT_FOUND; ứng dụng cache sentinel với TTL 5 phút; một tiến trình tạo user 10042 thành công; request đọc user vẫn hit negative cache và trả NOT_FOUND. Đây là **stale negative**. Nó làm giảm tính nhất quán và có thể khiến client gửi lại thao tác tạo hoặc nghĩ tài khoản chưa tồn tại.

### 7.2. Xóa negative key khi tạo record

Sau khi transaction tạo record commit, service có thể xóa negative entry tương ứng:

~~~text
BEGIN DATABASE TRANSACTION
    INSERT user(...)
COMMIT

cache.delete("user:{tenantId}:{userId}")
~~~

Xóa sau commit tránh cache được cập nhật dương cho một transaction có thể rollback. Tuy nhiên, vẫn có race:

- Request A đọc DB chưa thấy user.
- Request B tạo user và xóa cache.
- Request A ghi negative cache sau khi B đã xóa.

Kết quả là stale negative xuất hiện lại. Có thể giảm rủi ro bằng version/fencing token, write-through positive sau commit, cache generation, kiểm tra lại version trước khi ghi negative hoặc cơ chế đồng bộ/invalidation có thứ tự. Cần chọn mức phức tạp tương ứng với yêu cầu read-after-create.

### 7.3. Version-aware cache

Nếu hệ thống có version tăng đơn điệu cho entity hoặc namespace, cache có thể lưu version và chỉ chấp nhận ghi entry nếu nó không cũ hơn generation hiện tại. Cách triển khai phụ thuộc backend và tính nguyên tử của thao tác.

~~~text
cache key: user:{tenantId}:{userId}
cache value: {state: NOT_FOUND, generation: 12}

Sau khi create:
generation(user) = 13
negative entry generation 12 không còn hợp lệ
~~~

Không nên tự giả định cache get-then-set là atomic. Nếu cần compare-and-set, script hoặc transaction của cache, phải kiểm tra khả năng cụ thể của backend.

### 7.4. Xóa record và cache positive

Khi xóa một record, cần invalidate positive entry; có thể thêm negative entry ngay sau khi xác nhận xóa nếu luồng đọc yêu cầu giảm query lặp. Nếu xóa mềm, negative semantics phải thống nhất: NOT_FOUND, GONE, DELETED hay ẩn theo quyền. Một số client cần phân biệt 404 và 410; cache phải giữ đúng kết quả nghiệp vụ.

## 8. Phòng vệ theo nhiều lớp

Negative caching chỉ giảm lặp lại cho những key đã được tra cứu. Một cuộc tấn công thay key liên tục vẫn có thể tạo vô hạn negative entries và vẫn buộc ứng dụng query nguồn một lần cho mỗi key. Kết hợp nhiều biện pháp:

### 8.1. Validate trước khi truy vấn

- Kiểm tra format, chiều dài và charset của ID.
- Từ chối giá trị rỗng, quá dài hoặc không hợp lệ.
- Kiểm tra giới hạn page size, filter và độ phức tạp query.
- Chuẩn hóa identifier nhất quán trước khi tạo cache key.

Validation không xác định một ID có tồn tại hay không, nhưng loại bỏ đầu vào chắc chắn không hợp lệ mà không cần truy vấn nguồn.

### 8.2. Rate limiting

Giới hạn request theo IP, user, API key, tenant hoặc endpoint. Có thể dùng token bucket/leaky bucket để kiểm soát burst và sustained rate. Cần tránh chỉ rate limit theo IP vì client hợp lệ có thể đi qua NAT; ngược lại, giới hạn theo user cần xử lý request chưa xác thực.

Rate limiting giảm tổng lưu lượng nhưng không thay thế authorization hoặc validation. Cần phản hồi phù hợp (ví dụ 429), backoff và metric để client không retry liên tục.

### 8.3. Bloom filter

Bloom filter là cấu trúc xác suất dùng để kiểm tra một phần tử có thể thuộc tập dữ liệu hay chắc chắn không thuộc tập dữ liệu:

- Nếu Bloom filter trả **definitely not present**, ứng dụng có thể bỏ qua database lookup.
- Nếu trả **possibly present**, ứng dụng tiếp tục truy vấn nguồn hoặc cache.

Bloom filter có thể có false positive (nói có thể tồn tại dù thực tế không có), nhưng thiết kế chuẩn không có false negative nếu được xây dựng/cập nhật đúng và không bị hỏng. Vì false positive chỉ làm tăng lookup không cần thiết, nó thường an toàn hơn false negative làm ứng dụng bỏ qua một bản ghi thật.

~~~mermaid
flowchart TD
    R[Lookup request] --> BF{Bloom filter}
    BF -->|Definitely absent| NF[Return NOT_FOUND]
    BF -->|Possibly present| CACHE[Check cache]
    CACHE -->|Hit| RET[Return cached result]
    CACHE -->|Miss| DB[Query database]
    DB --> RESULT[Return actual result]
~~~

Bloom filter phù hợp khi tập ID có thể nạp/duy trì hiệu quả và lượng truy vấn key không tồn tại rất lớn. Cần kiểm soát cập nhật filter khi record được tạo; snapshot/rebuild sau restart; false-positive rate và memory; delete semantics (có thể cần counting Bloom filter hoặc rebuild); và nguồn filter có nhất quán với database không.

Nếu Bloom filter stale và bỏ qua một ID vừa được tạo, nó sẽ tạo false negative ở cấp hệ thống dù thuật toán Bloom filter bản thân không có false negative trong tập dữ liệu đầu vào đã xây dựng. Vì vậy, cần cập nhật đồng bộ, dual-write an toàn, generation hoặc fallback cho read-after-create.

### 8.4. Allowlist hoặc namespace hợp lệ

Với tập khóa nhỏ, hữu hạn (ví dụ mã loại cấu hình), có thể validate theo allowlist hoặc lưu catalog hợp lệ. Điều này tốt hơn việc query database cho mọi chuỗi tùy ý.

### 8.5. Query budget và circuit breaker

Đặt giới hạn concurrency, query timeout và ngân sách request tới nguồn. Khi database chậm hoặc quá tải, circuit breaker có thể tạm dừng request không thiết yếu, trả fallback hoặc lỗi có kiểm soát. Không biến một lỗi cache thành hàng loạt query DB không giới hạn.

## 9. Negative caching và HTTP/API semantics

### 9.1. Không cache mọi lỗi thành NOT_FOUND

| Kết quả | Ý nghĩa | Có thể negative-cache? |
|---|---|---|
| 404 / NOT_FOUND | Không có tài nguyên theo phạm vi lookup | Có, nếu semantics ổn định và TTL phù hợp |
| 410 / GONE | Tài nguyên đã bị loại bỏ vĩnh viễn hoặc theo policy | Có thể, nếu được xác định rõ |
| 401 / UNAUTHENTICATED | Caller chưa xác thực | Thường không cache như absence của resource |
| 403 / FORBIDDEN | Caller không được phép | Chỉ cache trong scope identity/policy an toàn nếu có chủ đích |
| 429 / RATE_LIMITED | Request vượt giới hạn | Không coi là dữ liệu không tồn tại |
| 500/502/503 | Lỗi hệ thống hoặc dependency | Không negative-cache như NOT_FOUND |
| Timeout | Không biết nguồn có dữ liệu hay không | Không được biến thành NOT_FOUND |

Nếu database timeout nhưng ứng dụng ghi sentinel NOT_FOUND, dữ liệu hiện có có thể bị che khuất. Chỉ cache negative khi đã có kết quả absence xác định.

### 9.2. Cache key phải chứa scope bảo mật

Nếu kết quả phụ thuộc tenant hoặc user permissions, cache key cần thể hiện đúng scope:

~~~text
resource:{tenantId}:{resourceId}
~~~

Nếu kết quả còn phụ thuộc role/authorization policy, có thể phải thêm permission version hoặc tách cache data khỏi bước authorization. Không dùng một negative cache key toàn cục cho resource có semantics khác nhau giữa tenant.

### 9.3. HTTP cache và Cache-Control

HTTP response 404/410 đôi khi có thể được cache theo semantics của HTTP và header/cấu hình. Nhưng negative caching phía CDN/reverse proxy cần cân nhắc:

- CDN có thể dùng cache key gồm URL, query string và header được chọn.
- Authorization/cookie không được bỏ qua nếu response phụ thuộc danh tính.
- TTL CDN có thể khác TTL application cache.
- Purge/invalidation phải chạy khi resource được tạo mới.
- Không để cache response 404 của một tenant/user phục vụ nhầm caller khác.

Không giả định mọi CDN mặc định cache 404 giống nhau; kiểm tra policy và cấu hình thực tế.

## 10. Cache key, namespace và chống cache poisoning

### 10.1. Chuẩn hóa key

Key phải được tạo từ identifier đã validate và normalize. Nếu một tầng coi chữ hoa/chữ thường giống nhau nhưng tầng khác phân biệt, cache có thể chứa nhiều biến thể hoặc trả sai dữ liệu.

Các yếu tố có thể cần đưa vào key gồm tenant hoặc data partition, loại resource, identifier đã chuẩn hóa, locale/version nếu kết quả phụ thuộc, permission scope/version nếu cache kết quả đã authorization.

### 10.2. Không cho client tự ghi sentinel

Client không được quyền gửi một payload để ghi trực tiếp negative sentinel vào cache. Chỉ server-side code có thẩm quyền mới tạo negative entry sau khi truy vấn nguồn và xác định absence.

Nếu cache key có thể bị người dùng kiểm soát hoàn toàn, kẻ tấn công có thể tạo lượng lớn key riêng, gây memory exhaustion. Giải pháp gồm validation, giới hạn cardinality theo tenant, quota, eviction policy và rate limit.

### 10.3. Namespace riêng cho positive/negative

~~~text
cache:v1:positive:user:{tenantId}:{userId}
cache:v1:negative:user:{tenantId}:{userId}
~~~

Key tách riêng giúp chính sách TTL/metric khác nhau nhưng làm invalidation phải xóa cả hai. Một key duy nhất chứa envelope state đơn giản hơn nhưng cần parser nhận diện đúng trạng thái.

### 10.4. Không làm lộ sự tồn tại của dữ liệu

Một endpoint có thể cố ý trả cùng một thông báo cho “không tồn tại” và “không có quyền” để chống enumeration. Negative cache phải bảo toàn semantics đó; metric/log nội bộ có thể phân loại chi tiết hơn nhưng phải kiểm soát truy cập và tránh log PII.

## 11. Stampede trên negative entries

Negative caching giảm truy vấn lặp trong TTL, nhưng khi một negative key hết hạn, nhiều request đồng thời vẫn có thể query database. Đây là một dạng cache breakdown/stampede trên key âm.

### 11.1. Request coalescing / single-flight

Có thể gộp nhiều lookup đồng thời cho cùng một key thành một truy vấn nguồn. Một request thực hiện lookup; các request còn lại chờ kết quả dùng chung. Single-flight có thể thực hiện trong một process hoặc bằng coordination phân tán tùy yêu cầu.

### 11.2. TTL jitter

Phân tán thời điểm hết hạn để tránh nhiều key âm cùng miss đồng loạt sau một đợt scan hoặc batch.

### 11.3. Refresh hoặc recheck có giới hạn

Với dữ liệu có thể được tạo mới, một số hệ thống có thể recheck nền hoặc dùng stale-while-revalidate. Tuy nhiên không được trả stale negative vô hạn khi client cần read-after-create. Recheck phải được rate-limit và có deadline.

### 11.4. Lock không phải giải pháp duy nhất

Distributed lock có thể giảm duplicate lookup, nhưng thêm độ phức tạp về lease, fencing token, lock timeout và failure. Với một key không tồn tại và TTL ngắn, request coalescing trong process cộng với negative cache có thể đủ; với workload phân tán lớn cần đánh giá kỹ chi phí coordination.

## 12. Kích thước cache và eviction

### 12.1. Negative entries có thể chiếm nhiều bộ nhớ

Nếu mỗi request tạo một khóa không tồn tại khác nhau, cache có thể bị lấp đầy bởi negative entries ít khi được đọc lại. Khi đó entry hữu ích bị eviction, memory tăng và chi phí cache tăng, serialization/index overhead lớn hơn payload, cache hit ratio tổng thể giảm, và kẻ tấn công có thể biến cache thành nơi lưu rác.

### 12.2. Giới hạn negative cache

- Dùng TTL âm ngắn hơn positive TTL.
- Giới hạn dung lượng/namespace hoặc tỷ trọng negative entries.
- Eviction theo LRU/LFU hoặc policy phù hợp backend.
- Chỉ cache các lookup có khả năng lặp lại.
- Không cache ID không hợp lệ đã bị validation loại bỏ.
- Rate limit số key mới theo caller/tenant.
- Theo dõi số lượng negative key và tỷ lệ reuse trước khi tăng TTL.

### 12.3. Admission policy

Thay vì cache mọi negative result, có thể chỉ cache sau khi một key bị hỏi lặp, hoặc dùng TinyLFU/admission policy tùy cache engine. Đây là cách tránh đưa các key một lần vào cache rồi đẩy entry có giá trị ra ngoài.

Một policy đơn giản có thể: với lần đầu gặp key không tồn tại, trả NOT_FOUND và tăng bộ đếm nhẹ; nếu key lặp trong cửa sổ ngắn, tạo negative entry; áp TTL và quota theo namespace. Cần đảm bảo counter/admission store không trở thành bottleneck mới. Có thể dùng sampling hoặc local frequency sketch nếu độ chính xác tuyệt đối không cần thiết.

## 13. Quan sát và đo hiệu quả

### 13.1. Metric nên có

| Metric | Ý nghĩa | Câu hỏi vận hành |
|---|---|---|
| Positive cache hit | Request nhận dữ liệu dương từ cache | Cache đang giúp đọc thường xuyên đến đâu? |
| Negative cache hit | Request nhận NOT_FOUND từ cache | Bao nhiêu truy vấn nguồn được tránh? |
| Cache miss | Không có entry | Miss tăng do key mới, eviction hay TTL? |
| Negative write rate | Tốc độ tạo entry âm | Có scan/traffic bất thường không? |
| Negative entry count/memory | Số lượng và dung lượng key âm | Có nguy cơ cache pollution không? |
| Negative reuse ratio | Tỷ lệ entry âm được hit lại | Negative caching có đáng giữ không? |
| DB not-found query rate | Số query nguồn trả không tồn tại | Penetration còn đi xuyên cache bao nhiêu? |
| Invalid key reject rate | Đầu vào bị loại trước lookup | Client lỗi hoặc enumeration có tăng không? |
| TTL expiry/recreation | Entry âm hết hạn và bị tạo lại | TTL có quá ngắn hoặc traffic lặp bất thường? |
| Freshness/read-after-create error | Trường hợp bản ghi mới bị che bởi negative | Invalidation có race hoặc TTL quá dài không? |

### 13.2. Tách metric theo phạm vi

Phân tích theo endpoint, tenant, caller type, region và result class. Không gắn userId/resourceId vào metric label nếu tạo cardinality quá cao; dùng structured log hoặc trace có kiểm soát để điều tra.

### 13.3. Đo hiệu quả thực tế

~~~text
Before:
Not-found requests = 10.000 requests/min
DB not-found queries = 10.000 queries/min

After:
Not-found requests = 10.000 requests/min
Negative cache hits = 8.500 requests/min
DB not-found queries = 1.500 queries/min

Estimated DB queries avoided = 8.500/min
~~~

Đây là số liệu minh họa. Cần đo cùng khoảng tải và phân biệt request hợp lệ, key ngẫu nhiên, validation fail và caller. Nếu database query giảm nhưng cache memory/eviction tăng quá mạnh, policy có thể chưa tối ưu.

### 13.4. Alert

Có thể cảnh báo khi DB not-found queries tăng đột biến; negative write rate vượt baseline; negative entries chiếm tỷ trọng bộ nhớ quá lớn; một tenant/caller tạo quá nhiều key mới; cache error khiến fallback DB tăng mạnh; read-after-create miss/false-not-found vượt ngưỡng; hoặc negative hit ratio quá thấp so với memory đang tiêu thụ.

Ngưỡng dựa trên baseline và SLO; không áp một con số cố định cho mọi workload.

## 14. Ví dụ triển khai cho API tra cứu booking

Giả sử ứng dụng có endpoint tra cứu booking theo tenant và booking ID. ID phải đúng định dạng; booking có thể được tạo ngay sau khi client gửi yêu cầu.

### 14.1. Luồng đề xuất

~~~mermaid
flowchart TD
    REQ[GET booking] --> AUTH[Authenticate caller]
    AUTH --> VALID{Validate ID and tenant}
    VALID -->|Invalid| REJECT[Reject without DB lookup]
    VALID -->|Valid| CACHE{Check scoped cache}
    CACHE -->|Positive| RETURN[Return booking]
    CACHE -->|Negative| NF[Return not found]
    CACHE -->|Miss| DB[Query Booking DB]
    DB --> FOUND{Found and authorized?}
    FOUND -->|Yes| POS[Write positive entry]
    POS --> RETURN
    FOUND -->|No record| NEG[Write negative sentinel with short TTL]
    NEG --> NF
    FOUND -->|DB error/timeout| ERR[Return controlled error; do not cache NOT_FOUND]
~~~

### 14.2. Chính sách mẫu

| Thành phần | Chính sách minh họa | Lý do |
|---|---|---|
| ID validation | UUID/format đã quy định | Loại input chắc chắn không hợp lệ |
| Cache key | Version + tenantId + bookingId | Tách phạm vi tenant và hỗ trợ đổi schema |
| Positive TTL | 60–180 giây tùy trường dữ liệu | Tối ưu đọc thường xuyên |
| Negative TTL | 5–15 giây | Hạn chế DB query lặp nhưng giảm stale negative |
| Cache miss | Query DB có timeout | Nguồn chuẩn quyết định tồn tại |
| DB NOT_FOUND | Ghi negative sentinel | Tái sử dụng kết quả âm |
| DB timeout/5xx | Không ghi negative | Không biến lỗi nguồn thành absence |
| Create booking | Commit rồi write-through/invalidate cache | Giảm cửa sổ stale negative |
| Caller rate limit | Theo identity/tenant/endpoint | Hạn chế enumeration và burst |
| Observability | Negative hit, DB not-found, key cardinality | Đo hiệu quả và phát hiện abuse |

Thời lượng chỉ là ví dụ để thảo luận; phải kiểm chứng với yêu cầu nghiệp vụ. Nếu client cần thấy booking ngay sau khi tạo, endpoint vừa tạo có thể trả kết quả từ transaction hoặc đọc trực tiếp system of record thay vì phụ thuộc cache.

### 14.3. Race condition khi create và lookup

~~~mermaid
sequenceDiagram
    participant R as Reader
    participant DB as Booking DB
    participant C as Cache
    participant W as Writer
    R->>C: GET key
    C-->>R: MISS
    R->>DB: SELECT booking
    DB-->>R: NOT FOUND
    W->>DB: INSERT booking
    DB-->>W: COMMIT
    W->>C: DELETE negative key
    R->>C: SET negative key
    Note over R,C: Stale negative created after invalidation
~~~

Các hướng xử lý tùy yêu cầu: ghi positive cache sau create và dùng generation/version để ngăn ghi negative cũ; đưa cache update/invalidation qua pipeline có thứ tự; không negative-cache với resource vừa được tạo hoặc đang trong cửa sổ chuyển trạng thái; với đường đọc yêu cầu read-your-writes, đọc trực tiếp nguồn chuẩn; giữ negative TTL ngắn để giới hạn cửa sổ lỗi còn lại.

Không có một thao tác delete cache đơn lẻ nào giải quyết mọi race giữa reader và writer. Cần xác định consistency contract cho endpoint.

## 15. Kiểm thử

### 15.1. Functional test

- Key có record: trả dữ liệu dương và ghi positive cache.
- Key không có record: trả NOT_FOUND và ghi negative sentinel.
- Request lặp cùng key: negative hit, không query DB lại.
- DB timeout: không ghi negative.
- ID sai format: bị từ chối trước DB.
- Hai tenant dùng cùng ID: cache scope không chéo nhau.
- Tạo record sau negative: invalidation/write-through cho phép đọc bản ghi theo SLO.
- Xóa record: positive entry bị invalidation và negative semantics đúng.

### 15.2. Concurrency/race test

- Nhiều reader cùng query một missing key.
- Create xảy ra giữa DB lookup và negative cache write.
- Negative TTL hết hạn khi có burst request.
- Cache restart/flush làm toàn bộ negative entry biến mất.
- Hai writer tạo cùng ID hoặc retry sau timeout.

### 15.3. Load và security test

- Nhiều key ngẫu nhiên không tồn tại.
- Một key âm nóng được lặp lại ở tốc độ cao.
- Một tenant tạo key mới với tốc độ bất thường.
- Key rất dài hoặc malformed.
- Thử truy cập chéo tenant và khác permission scope.
- Cache lỗi hoặc chậm trong khi traffic tăng.

Đánh giá DB QPS, connection, p95/p99, negative memory, eviction, cache CPU và false-not-found sau create. Không chỉ kiểm tra ứng dụng trả 404 đúng.

## 16. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Không cache NOT_FOUND | Cùng key âm liên tục truy vấn DB | Negative cache có TTL |
| Cache mọi lỗi thành NOT_FOUND | DB timeout hoặc 500 bị biến thành dữ liệu không tồn tại | Chỉ cache absence xác định |
| TTL âm quá dài | Bản ghi mới bị che khuất | TTL theo vòng đời và invalidation |
| TTL âm quá ngắn | Query lặp vẫn dồn xuống DB | Đo reuse và chọn TTL phù hợp |
| Dùng null mơ hồ | Không phân biệt miss với negative hit | Sentinel/envelope có type rõ |
| Cache key thiếu tenant | Rò rỉ hoặc sai kết quả giữa tenant | Include tenant/scope trong key |
| Tin delete cache giải quyết mọi race | Reader cũ có thể ghi negative sau invalidation | Version/fencing/read-your-writes |
| Cache mọi random key | Cache pollution và memory exhaustion | Validation, admission policy, quota |
| Dựa riêng vào negative caching chống DoS | Key mới liên tục vẫn query DB một lần | Rate limiting, Bloom filter, query budget |
| Bloom filter không được cập nhật | False negative ở cấp hệ thống sau create | Đồng bộ generation/rebuild/fallback |
| Không quan sát negative entry | Không biết cache có hiệu quả hay bị scan | Metric hit/reuse/cardinality/DB not-found |
| Không kiểm thử cache failure | Cache down làm database bị flood | Circuit breaker, concurrency cap, fallback control |

## 17. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi | Biện pháp và đánh đổi |
|---|---|---|
| **Operational Excellence** | Làm sao biết negative cache có giảm tải và key nào bất thường? | Metric, dashboard, alert, runbook và review TTL; tăng số policy cần quản lý |
| **Security** | Ai có thể tạo key, đọc kết quả âm và truy cập khác tenant? | Validation, scoped key, IAM, rate limit và chống enumeration |
| **Reliability** | DB timeout, cache down, create race và invalidation lỗi được xử lý thế nào? | Không cache lỗi không xác định, TTL giới hạn, versioning, fallback có kiểm soát |
| **Performance Efficiency** | Negative cache giảm bao nhiêu DB query và tốn bao nhiêu memory? | TTL/admission tuning, Bloom filter cho tập phù hợp, đo p95/p99 |
| **Cost Optimization** | Có đang lưu vô số negative key chỉ được dùng một lần? | Admission policy, quota, short TTL và eviction |
| **Sustainability** | Có truy vấn lặp, payload lớn hoặc cache entry không tái sử dụng? | Validation sớm, key ngắn, giảm request không hữu ích và retention hợp lý |

Negative caching giảm công việc lặp nhưng không loại bỏ nhu cầu bảo vệ nguồn dữ liệu. Một lớp cache khỏe mạnh cần làm đúng cả khi cache hit, miss, timeout và mất kết nối.

## 18. Bài tập áp dụng

### Bài tập A — Tính mức giảm query

Một endpoint nhận 12.000 request/phút cho ID không tồn tại. Trong đó 75% request lặp lại những key đã được hỏi trong TTL âm.

**Câu hỏi:** Ước tính database query còn lại nếu negative cache hoạt động và hit đúng 75% request lặp?

**Gợi ý:** Nếu 75% được hiểu là tỷ lệ request được phục vụ từ negative hit, DB nhận khoảng 25% = 3.000 query/phút. Cần đo phân bố key và reuse thực tế; tỷ lệ lặp theo key không tự động bằng hit ratio.

### Bài tập B — Chọn TTL

Một hệ thống tra booking ID có thể tạo booking mới ngay sau request đầu tiên. Nhóm dự định cache NOT_FOUND trong 30 phút.

**Câu hỏi:** Rủi ro gì xuất hiện và nên xem xét phương án nào?

**Gợi ý:** Stale negative có thể che booking mới tới 30 phút. Giảm TTL, invalidate/write-through sau create, dùng version/generation và đọc nguồn chuẩn cho read-your-writes.

### Bài tập C — Phân loại lỗi

Database trả timeout. Code hiện tại cache NOT_FOUND trong 10 phút để giảm retry.

**Câu hỏi:** Vì sao đây là lỗi thiết kế?

**Gợi ý:** Timeout không chứng minh record không tồn tại. Chỉ cache negative khi query trả kết quả absence rõ ràng; timeout phải có retry/backoff hoặc controlled error.

### Bài tập D — Tấn công key ngẫu nhiên

Kẻ tấn công gửi mỗi request một UUID khác nhau. Negative TTL là 10 phút nhưng hầu như không có key nào được hỏi lại.

**Câu hỏi:** Vì sao negative caching không đủ? Cần lớp nào khác?

**Gợi ý:** Mỗi key vẫn tạo một DB lookup và một cache entry; dùng format validation, rate limit, Bloom filter nếu có tập ID, admission policy, per-tenant quota và query budget.

### Bài tập E — Tenant leakage

Tenant A yêu cầu resource ID 42 không tồn tại nên cache NOT_FOUND tại key resource:42. Tenant B có resource ID 42 nhưng request nhận NOT_FOUND.

**Câu hỏi:** Nguyên nhân và sửa thế nào?

**Gợi ý:** Cache key thiếu tenant scope. Dùng resource:{tenantId}:{resourceId} và xác thực tenant từ identity server-side; kiểm thử authorization riêng.

### Bài tập F — Race invalidation

Reader query DB nhận NOT_FOUND, writer insert record rồi xóa cache, sau đó reader ghi negative sentinel.

**Câu hỏi:** Vì sao xóa cache sau create vẫn chưa đủ?

**Gợi ý:** Reader có kết quả cũ và ghi sau invalidation. Cần version/fencing, write-through positive, cơ chế atomic, read-your-writes hoặc TTL âm ngắn để giới hạn rủi ro.

## 19. Checklist trước khi đưa negative caching vào production

- [ ] Đã xác định endpoint và workload có truy vấn lặp dữ liệu không tồn tại.
- [ ] Validation loại input malformed trước database.
- [ ] Chỉ cache NOT_FOUND/absence đã xác định; timeout và lỗi hệ thống không thành negative.
- [ ] Sentinel phân biệt rõ cache miss, positive hit và negative hit.
- [ ] Cache key bao gồm tenant/resource/permission scope cần thiết.
- [ ] Positive TTL và negative TTL được chọn theo freshness, khả năng tạo mới và reuse.
- [ ] Luồng create/delete có invalidation hoặc write-through phù hợp.
- [ ] Race giữa lookup và create đã được phân tích; có version/fencing/read-your-writes nếu cần.
- [ ] Negative entries có giới hạn memory, TTL, quota và admission/eviction policy.
- [ ] Rate limit, query budget và circuit breaker bảo vệ database khi traffic bất thường.
- [ ] Bloom filter chỉ dùng khi có quy trình đồng bộ, rebuild và xử lý delete rõ ràng.
- [ ] Cache failure không làm request đồng loạt bỏ qua cache và flood database.
- [ ] Có metric negative hit/reuse, DB not-found QPS, key cardinality, eviction và stale-negative.
- [ ] Có alert theo tenant/caller và runbook khi penetration tăng.
- [ ] Functional, concurrency, race, load và security test đã được thực hiện.
- [ ] SLO freshness, tenant isolation, retention và chi phí cache đã được review.

**Điểm cốt lõi:** cache penetration xảy ra khi request liên tục đi xuyên qua cache tới nguồn dữ liệu, thường vì khóa không tồn tại hoặc không được cache. Negative caching ghi nhớ kết quả âm trong một khoảng thời gian để tránh truy vấn lặp, nhưng phải giới hạn TTL, phân biệt NOT_FOUND với lỗi, bảo toàn tenant scope và xử lý race khi dữ liệu được tạo. Kết hợp validation, rate limiting, Bloom filter/admission policy và observability sẽ bảo vệ database tốt hơn mà không biến cache thành nơi lưu trữ rác hoặc nguồn gây stale data.
