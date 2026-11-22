# Cache stampede, hot key và biện pháp giảm tải

## 1. Cache giúp tăng tốc, nhưng cache cũng có thể tạo ra sự cố tải

Cache giữ bản sao dữ liệu gần nơi sử dụng để giảm độ trễ và số lần truy cập storage hoặc service nguồn (origin). Khi cache hit cao, database nhận ít truy vấn hơn, response nhanh hơn và hệ thống có thể phục vụ nhiều request hơn với cùng năng lực compute. Tuy nhiên, cache không tự bảo đảm tải luôn được phân tán đều.

Hai tình huống đặc biệt nguy hiểm:

- **Cache stampede:** nhiều request cùng lúc gặp cache miss hoặc một key hết hạn, rồi đồng loạt truy vấn origin để tái tạo cùng một dữ liệu.
- **Hot key:** một key nhận lượng truy cập vượt xa các key khác, khiến một cache node, partition, shard hoặc backend phục vụ key đó bị quá tải dù tổng cluster vẫn còn năng lực.

Trong module **CLOUD_ARCHITECTURE**, thiết kế cache phải cân bằng độ trễ, khả năng mở rộng, độ tin cậy, chi phí và khả năng vận hành. Một cache hiệu quả không chỉ có hit ratio cao; nó còn cần kiểm soát đồng thời lúc miss, xử lý dữ liệu cũ hợp lý, phân phối key, bảo vệ origin và phục hồi khi cache hoặc backend gặp sự cố.

Sau bài này, bạn có thể:

- Phân biệt cache stampede, cache penetration, cache avalanche và hot key.
- Giải thích vì sao TTL đồng loạt hoặc một key phổ biến có thể tạo ra tải đột biến.
- Áp dụng TTL jitter, request coalescing/singleflight, stale-while-revalidate, refresh-ahead và probabilistic early refresh.
- Thiết kế khóa phân tán, lease, fencing token và giới hạn thời gian giữ lock.
- Xử lý hot key bằng replication, local cache, sharding có chủ đích, admission control và tải bất đồng bộ.
- Bảo vệ origin bằng rate limit, concurrency limit, circuit breaker, backpressure và fallback.
- Đo hit/miss, refresh, waiters, origin load, key skew và độ trễ để chứng minh hiệu quả.

## 2. Nhận diện bốn kiểu vấn đề cache

Các vấn đề này có thể xuất hiện riêng lẻ hoặc cùng lúc:

| Vấn đề | Điều xảy ra | Hệ quả điển hình |
|---|---|---|
| **Cache stampede** | Nhiều request cùng refresh một key đang miss/expired | Origin nhận hàng trăm truy vấn trùng cho một dữ liệu |
| **Hot key** | Một vài key có tỷ lệ request rất lớn | Một shard/node hoặc backend của key đó quá tải |
| **Cache penetration** | Request liên tục hỏi key không tồn tại hoặc không được cache | Miss đi xuyên xuống origin; có thể bị khai thác bằng key ngẫu nhiên |
| **Cache avalanche** | Nhiều key hết hạn hoặc cache layer hỏng gần cùng lúc | Nhiều miss đồng thời, tải origin tăng trên diện rộng |

### 2.1. Ví dụ BookingCloud

BookingCloud hiển thị trang thiết bị phổ biến. Cache có key `device:dev-017`, TTL 10 phút. Một chiến dịch marketing khiến key này nhận 20.000 request/giây. Khi key hết hạn, rất nhiều request cùng đọc database để tái tạo object.

Nếu database chỉ xử lý ổn định 2.000 truy vấn/giây, phần request vượt năng lực có thể tạo queue, tăng connection, timeout và retry. Thời gian xử lý chậm khiến request tồn tại lâu hơn; số request đồng thời tăng thêm, tạo vòng phản hồi quá tải.

Vấn đề không chỉ là “cache bị miss”. Đó là **cache miss đã làm mất lớp giảm tải đúng lúc hệ thống cần nó nhất**.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Many clients
    participant C as Cache
    participant D as Database
    Note over C: Key expires
    par Request 1
        U->>C: GET device:dev-017
        C-->>U: MISS
        U->>D: SELECT device
    and Request 2
        U->>C: GET device:dev-017
        C-->>U: MISS
        U->>D: SELECT device
    and Request N
        U->>C: GET device:dev-017
        C-->>U: MISS
        U->>D: SELECT device
    end
    D-->>U: Repeated result computation
~~~

Đây là cache stampede: nhiều request thực hiện cùng công việc tái tạo trong cùng khoảng thời gian.

## 3. Vì sao stampede xảy ra?

### 3.1. TTL đồng loạt

Nếu hệ thống nạp hàng loạt key lúc 09:00 và gán TTL đúng 3.600 giây, rất nhiều key hết hạn gần 10:00. Một chiến dịch, batch job hoặc deploy có thể tạo ra “làn sóng” cache miss.

TTL cố định còn dễ làm các replica cùng cache một tập dữ liệu hết hạn cùng lúc. Nếu cả application instances đều refresh origin đồng thời, tải tăng theo số replica.

### 3.2. Popular key hết hạn

Một key có traffic cao có thể chịu stampede ngay cả khi chỉ một key hết hạn. Ví dụ trang chủ thường đọc cùng một object cấu hình hoặc danh sách nổi bật. Khi key miss, số request đồng thời tạo ra nhiều bản tính toán giống nhau.

### 3.3. Cache node restart hoặc cache flush

Deploy, failover, eviction, memory pressure, flush hoặc mất kết nối cache có thể tạo nhiều miss. Nếu ứng dụng fallback trực tiếp xuống database mà không giới hạn concurrency, cache failure biến thành origin failure.

### 3.4. Refresh chậm hơn tốc độ request

Ngay cả khi một key TTL dài, giá trị đó có thể cần vài giây để tính lại. Nếu hàng nghìn request đến trong thời gian tính toán, hệ thống vẫn có stampede nếu không gộp request.

## 4. TTL jitter: phân tán thời điểm hết hạn

**TTL jitter** thêm một độ lệch ngẫu nhiên vào TTL để các key không hết hạn đồng loạt.

Thay vì TTL cố định 3600 giây, có thể chọn:

~~~text
ttl = base_ttl + random(0, jitter_window)
~~~

hoặc:

~~~text
ttl = base_ttl * random(0.8, 1.2)
~~~

Ví dụ TTL cơ sở 10 phút với jitter ±20% tạo khoảng TTL từ 8 đến 12 phút. Các key được ghi ở cùng thời điểm sẽ phân tán expiry hơn.

### 4.1. Chọn jitter phù hợp

- Jitter additive phù hợp khi muốn phân tán trong một khoảng thời gian cố định.
- Jitter proportional phù hợp khi TTL của các nhóm dữ liệu khác nhau nhiều bậc.
- Với dữ liệu có deadline freshness cứng, không cho jitter làm TTL vượt quá giới hạn cho phép.
- Có thể dùng jitter khác nhau theo data class hoặc key category.

TTL jitter **giảm khả năng nhiều key hết hạn cùng lúc**, nhưng không giải quyết triệt để một hot key có hàng nghìn request cùng miss. Với một key phổ biến, cần thêm request coalescing, stale serving hoặc refresh coordination.

## 5. Request coalescing: một lần nạp, nhiều request cùng chờ

**Request coalescing** (còn gọi singleflight trong một số thư viện) gộp nhiều request cùng cần một key thành một lần tải origin. Request đầu tiên thực hiện load; các request còn lại đợi kết quả đó thay vì truy vấn origin riêng.

~~~mermaid
flowchart TD
    R["Concurrent requests for one key"] --> G["Cache lookup"]
    G -->|"Hit"| H["Return cached value"]
    G -->|"Miss"| S["Singleflight / in-flight registry"]
    S -->|"Leader"| L["One origin fetch"]
    S -->|"Followers"| W["Wait for shared result"]
    L --> O["Origin"]
    O --> P["Populate cache"]
    P --> RET["Return result to leader"]
    P --> W
~~~

### 5.1. Coalescing trong một process

Nếu application chỉ có một process, có thể giữ map từ cache key sang promise/future đang chạy:

~~~text
get(key):
    value = cache.get(key)
    if value exists:
        return value

    return singleflight.do(key, function:
        value = cache.get(key)       # double-check
        if value exists:
            return value

        value = origin.fetch(key)
        cache.set(key, value, ttl_with_jitter)
        return value
    )
~~~

Đây là pseudocode. Thư viện thực tế cần xử lý exception, cancellation, timeout, memory cleanup và race khi entry hoàn thành/xóa. Double-check sau khi trở thành leader tránh một request khác đã nạp cache trong lúc request hiện tại chờ lock.

### 5.2. Giới hạn của singleflight cục bộ

Nếu có 30 application replicas, mỗi process có singleflight riêng. Khi key miss, vẫn có thể có tối đa khoảng 30 leader cùng truy vấn origin. Điều này thường tốt hơn hàng nghìn request nhưng chưa phải một lần nạp duy nhất trên toàn cluster.

Có ba lựa chọn:

- Chấp nhận một leader trên mỗi process nếu origin đủ năng lực.
- Dùng distributed coordination để một worker/instance làm leader toàn cluster.
- Kết hợp local coalescing với distributed cache/refresh service để hạn chế số origin fetch.

Distributed lock có thêm độ trễ, phụ thuộc mạng và cần thiết kế correctness; không nên thêm vào mọi cache key khi singleflight cục bộ đã đáp ứng SLO.

## 6. Distributed lock, lease và fencing token

Khi nhiều application replicas chia sẻ cache, chúng có thể cần phối hợp để chỉ một replica refresh key tại một thời điểm. Distributed lock không đơn giản là “SET key = locked”.

### 6.1. Lock có lease và token riêng

Một lock nên có key định danh công việc, owner token ngẫu nhiên, lease/TTL hữu hạn, timeout chờ lock và cơ chế double-check cache sau khi acquire. Chỉ owner hợp lệ mới được release lock.

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Replica A
    participant B as Replica B
    participant L as Lock service
    participant C as Shared cache
    participant O as Origin
    A->>C: GET key
    C-->>A: MISS
    B->>C: GET key
    C-->>B: MISS
    A->>L: Acquire lease with owner token
    L-->>A: Granted
    B->>L: Acquire lease
    L-->>B: Busy
    A->>C: Double-check key
    C-->>A: MISS
    A->>O: Fetch value
    O-->>A: Result
    A->>C: SET value + TTL
    A->>L: Release only if owner token matches
    B->>C: Retry/read
    C-->>B: HIT
~~~

### 6.2. Vì sao TTL lock chưa đủ?

Giả sử Replica A có lease 5 giây nhưng origin query mất 8 giây. Lock hết hạn khi A vẫn chạy. Replica B acquire lease mới và bắt đầu refresh. A sau đó hoàn thành và ghi kết quả cũ đè kết quả mới.

Một lock có lease giảm khả năng deadlock khi owner chết nhưng không tự ngăn owner cũ tiếp tục ghi sau khi lease hết hạn.

### 6.3. Fencing token

**Fencing token** là số thứ tự tăng dần do lock/coordination service cấp mỗi lần acquire. Storage/write path kiểm tra token; token cũ hơn token đã chấp nhận bị từ chối. Điều này ngăn owner cũ ghi sau khi một owner mới được cấp quyền.

~~~text
Replica A acquires lease -> token 41
Lease A expires
Replica B acquires lease -> token 42
Storage accepts write with token 42
Replica A later sends write with token 41 -> reject
~~~

Fencing chỉ hữu ích khi nơi ghi kết quả thực sự enforce token. Một Redis lock đơn giản không thể ngăn process cũ tự ghi vào database nếu database không kiểm tra fencing/version. Nếu cache chỉ lưu bản sao có thể tái tạo, stale overwrite có thể được xử lý bằng version check hoặc compare-and-set; nếu dữ liệu mang tính nghiệp vụ, cần consistency mechanism mạnh hơn.

## 7. Stale-while-revalidate và stale-if-error

Một trong những cách giảm stampede hiệu quả là không buộc mọi request chờ dữ liệu mới ngay khi TTL vừa hết.

**Stale-while-revalidate (SWR):** sau fresh TTL, cache có thể tiếp tục trả bản cũ trong một khoảng stale window trong khi một worker refresh ở nền.

**Stale-if-error:** nếu refresh thất bại, cache có thể tiếp tục trả bản cũ trong một khoảng thời gian cho phép để giữ availability.

~~~mermaid
flowchart LR
    F["Fresh period"] --> S["Stale-while-revalidate window"]
    S -->|"Refresh succeeds"| N["New fresh value"]
    S -->|"Refresh fails, within policy"| E["Serve stale-if-error"]
    E --> R["Retry with backoff"]
    R -->|"Success"| N
    S -->|"Stale limit exceeded"| H["Fail / fallback by business policy"]
~~~

Ví dụ chính sách:

| Mốc | Hành vi |
|---|---|
| 0–300 giây | Trả giá trị fresh |
| 300–360 giây | Trả stale ngay; một request kích hoạt refresh nền |
| Refresh thành công | Thay bằng giá trị mới và bắt đầu TTL mới |
| Refresh lỗi trong stale-if-error 10 phút | Tiếp tục phục vụ giá trị cũ và retry có giới hạn |
| Stale window hết | Fail/fallback theo yêu cầu nghiệp vụ |

Các mốc này chỉ là ví dụ, không phải mặc định dùng cho mọi dữ liệu.

### 7.1. Dữ liệu nào có thể phục vụ stale?

Phù hợp hơn: danh mục thiết bị, ảnh, mô tả marketing; cấu hình ít thay đổi có last-known-good value; báo cáo tổng hợp có độ trễ chấp nhận được; recommendation nếu policy cho phép.

Cần thận trọng hoặc không phục vụ stale: số dư tiền, quyền truy cập, trạng thái payment; slot đặt lịch hoặc inventory mà stale value có thể gây đặt trùng; revocation, credential, policy bảo mật và trạng thái khóa tài khoản; dữ liệu có deadline freshness bắt buộc.

Không dùng SWR cho dữ liệu cần strong consistency nếu stale response có thể phá invariant hoặc tạo hành động không thể đảo ngược.

## 8. Refresh-ahead và probabilistic early refresh

Ngoài chờ tới khi TTL hết, hệ thống có thể chủ động refresh trước khi hết hạn.

### 8.1. Refresh-ahead

Khi còn một khoảng thời gian trước expiry, background worker tải lại giá trị. Nếu thành công, thay cache entry; nếu thất bại, giữ bản hiện có trong stale policy.

Ưu điểm là giảm cache miss ở giờ cao điểm và có thể chọn thời điểm origin ít bận. Đánh đổi là refresh cả key ít được dùng tạo tải lãng phí; cần scheduler/worker và kiểm soát đồng thời; phải tính freshness, version và failure.

Có thể kết hợp refresh-ahead với admission policy: chỉ refresh key có recent access hoặc popularity vượt ngưỡng.

### 8.2. Probabilistic early expiration

Với tập key lớn và traffic biến động, có thể chọn ngẫu nhiên một request refresh sớm hơn TTL. Xác suất tăng dần khi key tiến gần expiry hoặc khi thời gian tính toán origin dài.

~~~text
refresh_probability = f(time_to_expiry, observed_load_time, traffic_rate)
~~~

Không có một công thức phù hợp cho mọi ứng dụng. Một số thuật toán probabilistic early expiration dùng thời gian tải gần nhất và biến ngẫu nhiên exponential để phân tán refresh mà không cần lock toàn cục. Cần thử tải, đo số refresh thừa và kiểm tra freshness.

## 9. Hot key: khi một key chi phối toàn bộ tải

Hot key khác stampede: cache có thể hit rất tốt nhưng một key vẫn nhận traffic quá lớn. Nếu cache cluster phân shard theo hash của key, mọi request cho cùng key có thể đi tới cùng shard. Shard đó quá tải trong khi các shard khác rảnh.

Ví dụ key `homepage:featured-devices` nhận 40% tổng request. Tăng số shard không nhất thiết giúp vì hash của một key vẫn ánh xạ tới cùng một shard.

### 9.1. Nhân bản giá trị phổ biến

Với dữ liệu read-only hoặc cập nhật có thể phân phối, có thể tạo nhiều bản cache replica và phân tán read:

~~~mermaid
flowchart TB
    U["High-volume clients"] --> LB["Read routing"]
    LB --> R1["Cache replica A"]
    LB --> R2["Cache replica B"]
    LB --> R3["Cache replica C"]
    R1 --> ORIGIN["Origin / refresh result"]
    R2 --> ORIGIN
    R3 --> ORIGIN
    REF["Refresh publisher"] --> R1
    REF --> R2
    REF --> R3
~~~

Các biến thể:

- Replica ở nhiều cache node/zone để tăng read capacity.
- Local in-process cache ở application replica cho key public, với invalidation/TTL ngắn.
- CDN edge cache cho nội dung có thể cache ở gần user.
- Read replica database nếu query và consistency semantics phù hợp.

Replication tăng năng lực đọc nhưng cần đồng bộ invalidation/update. Nhiều bản sao có thể tiếp tục phục vụ giá trị cũ nếu refresh chưa đến nơi; cần quy định freshness và propagation.

### 9.2. Key salting và sharding

Có thể chia một hot key thành nhiều sub-key, ví dụ:

~~~text
homepage:featured-devices:bucket-00
homepage:featured-devices:bucket-01
homepage:featured-devices:bucket-02
...
~~~

Cách này chỉ có ích nếu request có thể được phân phối thực sự giữa các bucket và nội dung có thể nhân bản/partition. Nếu mọi request vẫn phải đọc một counter hoặc object duy nhất rồi mới chọn bucket, bottleneck chưa biến mất.

Không thêm random suffix để chia shard khi mỗi suffix dẫn tới dữ liệu độc lập hoặc không được populate nhất quán. Với một giá trị chung, fan-out write/update có thể tốn chi phí; có thể dùng một nguồn canonical và phân phối snapshot tới các replica.

### 9.3. Local cache và CDN

Local cache có độ trễ thấp và có thể giảm traffic tới shared cache, nhưng mỗi process giữ một bản riêng. Cần TTL ngắn hoặc invalidation có version; giới hạn memory và eviction policy; không cache dữ liệu theo user/tenant mà key thiếu identity scope; chấp nhận eventual update nếu business cho phép.

CDN phù hợp nội dung public/cacheable; thiết lập Cache-Control, surrogate key/purge, vary dimensions và authorization cẩn thận. Không để CDN cache response riêng tư chỉ vì URL giống nhau.

## 10. Cache penetration và negative caching

Attacker hoặc client lỗi có thể gửi nhiều key ngẫu nhiên không tồn tại. Vì cache không lưu miss, mỗi request đi xuống database.

Biện pháp:

- **Negative caching:** cache kết quả “không tồn tại” trong TTL ngắn.
- **Bloom filter:** cấu trúc xác suất kiểm tra key có thể tồn tại; false positive có thể xảy ra, false negative cần được kiểm soát theo cách khởi tạo/cập nhật.
- Validate ID/format trước khi gọi origin.
- Rate limit theo identity/IP/API key và giới hạn concurrency.
- Theo dõi tỷ lệ miss của nonexistent keys và nguồn request bất thường.

Negative caching cần cẩn thận khi resource mới được tạo: nếu cache NOT_FOUND quá lâu, user có thể không thấy resource mới. Invalidate negative entry khi create event commit hoặc chọn TTL ngắn.

## 11. Bảo vệ origin: không để cache failure thành database outage

Cache chỉ là một lớp tối ưu. Origin cần giới hạn tải độc lập với cache.

### 11.1. Concurrency limit và semaphore

Giới hạn số truy vấn origin đang chạy đồng thời cho một nhóm resource hoặc một service. Khi đạt ngưỡng, cho request chờ trong queue hữu hạn; trả stale nếu policy cho phép; trả lỗi overload có kiểm soát; hoặc hạ ưu tiên background refresh.

Queue không giới hạn chỉ biến overload thành latency và memory exhaustion. Cần giới hạn queue length, queue wait time và deadline.

### 11.2. Rate limit và token bucket

Rate limit giới hạn tốc độ gọi origin theo tenant, client, route hoặc key group. Token bucket cho phép burst ngắn trong khi giữ tốc độ trung bình có giới hạn. Cần chia budget giữa foreground request và background refresh để refresh không chiếm hết capacity.

### 11.3. Circuit breaker

Khi origin liên tục lỗi hoặc timeout, circuit breaker mở để tạm ngừng gửi request mới, tránh khuếch đại sự cố. Sau cooldown, cho một số request thử lại (half-open). Trong thời gian breaker mở:

- Trả stale nếu dữ liệu được phép.
- Trả fallback có ý nghĩa nghiệp vụ.
- Báo lỗi có cấu trúc nếu không thể phục vụ an toàn.
- Không retry ngay lập tức trên mọi application replica.

### 11.4. Backpressure và graceful degradation

Nếu hệ thống quá tải, cần giảm mức công việc thay vì nhận vô hạn: tạm bỏ recommendation hoặc view count; cache response tổng hợp; hạn chế batch/refresh không cấp thiết; giữ capacity cho thao tác quan trọng như đặt/hủy booking; trả 429/503 và Retry-After khi phù hợp để client retry có backoff.

~~~mermaid
flowchart TD
    REQ["Request"] --> CACHE["Cache lookup"]
    CACHE -->|"Hit"| OK["Return cached"]
    CACHE -->|"Miss"| GUARD["Origin load guard"]
    GUARD --> CB{"Circuit breaker"}
    CB -->|"Closed + capacity"| SEM["Concurrency / rate limit"]
    CB -->|"Open"| STALE["Serve stale if allowed"]
    STALE -->|"Not allowed"| ERR["Controlled fallback/error"]
    SEM -->|"Admitted"| ORIGIN["Origin service"]
    SEM -->|"Rejected / queue full"| STALE
    ORIGIN -->|"Success"| SET["Populate cache"]
    ORIGIN -->|"Timeout / error"| STALE
    SET --> OK
~~~

### 11.5. Không dùng fallback làm sai nghiệp vụ

Giá trị mặc định 0, danh sách rỗng hoặc trạng thái cũ có thể làm UI chạy nhưng sai nghiệp vụ. Trang sản phẩm có thể hiển thị mô tả cũ; recommendation có thể bỏ qua tạm thời; booking slot availability cần nguồn có thẩm quyền hoặc báo chưa thể xác nhận; authorization không được fallback thành allow; payment outcome unknown không được coi là failed để charge lại hoặc success để xác nhận đơn.

## 12. Chọn chiến lược theo workload

| Workload | Rủi ro chính | Biện pháp gợi ý |
|---|---|---|
| Product/catalog public | Hot key, cache avalanche | CDN/local cache, TTL jitter, refresh-ahead, replica |
| Booking detail cá nhân | Key scope sai, stampede, stale privacy | Cache key có tenant/user scope, singleflight, short TTL |
| Slot availability | Stale gây double-booking | Dùng DB/strong source cho write decision; cache chỉ gợi ý |
| Dashboard/report | Stampede do query nặng | SWR, background refresh, coalescing, materialized view |
| Session/token | Invalidation và security | TTL/expiry chính xác, revoke semantics, không stale tùy tiện |
| Configuration/feature flags | Nhiều key hết hạn cùng lúc | Jitter, local cache, version/invalidation |
| Recommendation | Hot aggregate key, origin query đắt | Precompute, replication, stale-serving |
| Negative lookup | Penetration từ key ngẫu nhiên | Negative cache TTL ngắn, validation, Bloom filter, rate limit |

## 13. Quan sát cache và phát hiện bất thường

Hit ratio cao chưa đủ để chứng minh cache khỏe. Có thể cache hit 99% nhưng 1% miss tập trung vào một hot key làm origin quá tải; hoặc hit trả dữ liệu quá cũ.

### 13.1. Metric nên theo dõi

| Metric | Ý nghĩa | Dấu hiệu bất thường |
|---|---|---|
| Hit/miss ratio | Phần request được phục vụ từ cache | Miss tăng đột ngột sau deploy/expiry |
| Origin QPS | Số truy vấn xuống nguồn | Tăng nhanh khi cache miss hoặc flush |
| Refresh count/duration | Số lần và thời gian tái tạo key | Một key refresh song song nhiều lần |
| Coalesced waiter count | Số request chờ một refresh | Tăng cao có thể báo refresh quá chậm |
| Lock contention/lease expiry | Cạnh tranh refresh | Lease hết trước khi owner hoàn tất |
| Stale response rate/age | Tần suất và tuổi dữ liệu cũ được trả | Tăng kéo dài hoặc vượt freshness budget |
| Hot-key skew | Tỷ lệ traffic của top keys/shards | Một shard lệch xa các shard khác |
| Eviction/memory usage | Áp lực memory và key churn | Cache thrashing |
| Origin latency/error | Sức khỏe dependency | Timeout, connection pool exhaustion |
| Negative-cache hit | Miss được chặn tại cache | Bot/key random tăng mạnh |

### 13.2. Tránh cardinality bùng nổ

Không tạo metric label cho mọi cache key; một triệu key có thể tạo một triệu time series. Thay vào đó, ghi top-N hot key bằng log/sample hoặc diagnostic view có giới hạn; nhóm theo key namespace, tenant tier, shard, endpoint và data class; dùng histogram cho latency; hash/mask key khi chứa ID nhạy cảm; dùng trace exemplar hoặc sampled event.

### 13.3. Dashboard theo luồng request

Một dashboard sự cố cache nên hiển thị cùng nhau: incoming QPS, hit/miss, origin QPS/latency, refresh concurrency, top hot namespace, cache memory/eviction, DB connections, error rate và stale age. Nếu chỉ có cache hit ratio, khó biết miss đang gây áp lực lên đâu.

## 14. Kiểm thử và diễn tập stampede/hot key

Trước production, mô phỏng các tình huống:

1. Hàng nghìn request đồng thời cho một key cold.
2. Một key cực phổ biến hết hạn trong peak traffic.
3. Nhiều key được populate cùng lúc rồi cùng hết hạn.
4. Cache cluster restart hoặc network partition.
5. Origin chậm hơn lease/refresh timeout.
6. Lock holder bị kill trước khi ghi cache.
7. Lock lease hết hạn khi leader cũ vẫn đang chạy.
8. Refresh trả lỗi liên tục hoặc trả dữ liệu không hợp lệ.
9. Một tenant/client gửi key ngẫu nhiên để gây penetration.
10. Cache replica bị stale sau purge/invalidation.

### 14.1. Chỉ số chấp nhận

Định nghĩa trước max origin QPS và concurrent queries; số lần load origin cho một key trong một refresh window; p95/p99 latency và error rate; thời gian phục hồi sau cache flush/node loss; freshness/stale age tối đa theo data class; tỷ lệ request bị shed/rate-limited; và bảo đảm không có booking, payment hoặc authorization sai do fallback stale.

Một thử nghiệm tốt cố tình gây lỗi, đồng thời xác nhận hệ thống giữ được giới hạn origin và trả kết quả đúng theo policy.

## 15. Thiết kế tham chiếu cho BookingCloud

Giả sử product catalog public có traffic lớn, còn slot availability và booking detail mang tính nghiệp vụ.

| Luồng | Cache strategy | Origin protection | Consistency policy |
|---|---|---|---|
| Public product page | CDN + shared cache + local cache ngắn | TTL jitter, SWR, refresh-ahead | Chấp nhận stale vài phút |
| Popular device detail | Replicated hot entry + singleflight | Per-key refresh limit, origin semaphore | Versioned refresh, stale window |
| Booking detail | Key gồm tenant/user scope, coalescing | Rate/concurrency limit | TTL ngắn; invalidate sau mutation |
| Slot availability | Cache chỉ cho display hint | Write path luôn kiểm tra source có thẩm quyền | Không quyết định booking từ stale cache |
| Recommendations | Precompute + CDN/local cache | Background refresh, stale-if-error | Chấp nhận dữ liệu cũ có giới hạn |
| User-not-found lookup | Negative cache ngắn + input validation | Rate limit và origin budget | Invalidate khi user được tạo |

~~~mermaid
flowchart TB
    CLIENT["Web / mobile clients"] --> CDN["CDN / edge cache"]
    CDN --> API["API gateway / application"]
    API --> LOCAL["Local cache + request coalescing"]
    LOCAL --> SHARED["Shared cache / hot-key replicas"]
    SHARED --> GUARD["Refresh coordinator + origin guard"]
    GUARD --> ORIGIN["Catalog / reporting origin"]
    ORIGIN --> DB[("Database / materialized view")]
    ORIGIN --> SHARED
    API --> BOOK["Booking write service"]
    BOOK --> DB
~~~

Sơ đồ cho thấy cache phục vụ đọc và giảm tải cho origin; booking write vẫn kiểm tra invariant ở nguồn dữ liệu có thẩm quyền. Không nên biến cache thành nơi quyết định cuối cùng cho giao dịch đặt chỗ.

## 16. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi review | Bằng chứng cần có |
|---|---|---|
| **Operational Excellence** | Ai theo dõi hot key, refresh queue và cache recovery? | Dashboard, alert, runbook, load/chaos drill và owner |
| **Security** | Cache key có tách tenant/user? Stale data hoặc CDN có thể lộ dữ liệu riêng tư? | Key scoping, authorization test, TLS, private access và log redaction |
| **Reliability** | Cache flush, node loss hoặc origin outage có làm database sập theo không? | Coalescing, stale policy, origin concurrency budget, circuit breaker và failover test |
| **Performance Efficiency** | Hot key có được phân phối read? Refresh có cạnh tranh với foreground traffic? | Key skew, p95/p99, origin QPS, waiter count và refresh latency |
| **Cost Optimization** | Replication, local cache, CDN và refresh-ahead có đáng với chi phí không? | Cost per request, origin query avoided, memory/egress và refresh overhead |
| **Sustainability** | Có refresh key ít dùng, cache dữ liệu dư hoặc giữ cache quá lâu? | Admission metrics, eviction, TTL/retention policy và resource utilization |

Một giải pháp giảm tải cần chứng minh cả hai phía: cache có thể phục vụ lượng đọc mục tiêu và origin vẫn được bảo vệ khi cache miss hoặc cache layer lỗi. Tăng replica hay thời gian stale mà không đo freshness, memory, egress và tính đúng đắn có thể chỉ chuyển chi phí hoặc rủi ro sang chỗ khác.

## 17. Bài thực hành: xử lý cache stampede và hot key

BookingCloud có endpoint GET /devices/dev-017. Trong giờ cao điểm:

- Endpoint nhận 15.000 request/giây.
- Cache TTL là 5 phút.
- Origin query mất p95 250 ms và chỉ chịu được khoảng 2.500 query/giây cho workload này.
- Có 20 application replicas.
- Shared cache hiện shard theo hash key.
- Khi key hết hạn, origin QPS tăng vọt và database connection pool bão hòa.

Nhóm đề xuất tăng số cache shard gấp đôi.

Hãy thực hiện:

**Bài 1 — Chẩn đoán:** giải thích vì sao tăng shard không chắc giải quyết hot key; phân biệt vấn đề stampede với key skew.

**Bài 2 — Coalescing:** chọn local singleflight, distributed refresh lock hoặc kết hợp. Ước lượng số leader origin fetch tối đa nếu chỉ dùng local singleflight với 20 replicas.

**Bài 3 — Freshness:** đề xuất TTL jitter, stale-while-revalidate và stale-if-error window cho product detail. Nêu điều kiện dừng trả stale.

**Bài 4 — Lock safety:** mô tả lease, owner token, timeout và fencing token; phân tích trường hợp leader cũ hoàn thành sau khi lease hết hạn.

**Bài 5 — Hot key:** đề xuất replica/local cache/CDN hoặc precompute; nêu cách cập nhật và invalidation để các bản sao không quá cũ.

**Bài 6 — Origin protection:** thiết kế rate limit, concurrency limit, circuit breaker và backpressure; xác định khi nào trả 429/503.

**Bài 7 — Kiểm chứng:** lập load test cho cold key, cache flush, origin chậm, leader crash và một tenant gửi key ngẫu nhiên. Chọn metric và go/no-go threshold.

### Khung phân tích tự kiểm tra

| Quyết định | Hướng suy nghĩ |
|---|---|
| Tăng shard | Chỉ giúp nếu nhiều key/partition phân bố lệch; một key vẫn hash về một shard |
| Local singleflight | Tối đa khoảng một leader cho mỗi key trên mỗi process; 20 replicas có thể tạo 20 origin fetch |
| Distributed coordination | Giảm leader toàn cụm nhưng thêm latency và failure mode; cần lease/fencing hoặc cơ chế version |
| SWR | Trả stale ngay trong window và refresh ở nền; không dùng cho dữ liệu quyết định booking/payment |
| Replica | Tăng read capacity; phải có refresh/invalidation và freshness policy |
| Origin guard | Giới hạn concurrency/rate; không để queue vô hạn |
| Fallback | Bảo vệ availability nhưng phải giữ semantics nghiệp vụ và không mở quyền truy cập |

Các con số chỉ dùng cho bài tập. Thiết kế production cần benchmark, xác nhận traffic shape và data freshness.

## 18. Checklist trước khi đưa cache vào production

- [ ] Đã phân loại cache stampede, hot key, penetration và avalanche cho workload.
- [ ] TTL có jitter phù hợp; freshness deadline được định nghĩa theo data class.
- [ ] Cache miss có request coalescing hoặc refresh coordination khi cần.
- [ ] Leader refresh double-check cache trước khi gọi origin.
- [ ] Distributed lock có owner token, lease, timeout và release an toàn.
- [ ] Nếu correctness yêu cầu, write path có fencing/version check để chặn stale owner.
- [ ] Có SWR/stale-if-error chỉ cho dữ liệu được phép phục vụ stale.
- [ ] Refresh-ahead/probabilistic refresh được giới hạn để tránh refresh thừa.
- [ ] Hot key được nhận diện; replication/local cache/CDN/sharding được chọn dựa trên access pattern.
- [ ] Cache key có tenant/user scope đúng để tránh rò dữ liệu.
- [ ] Negative caching có TTL phù hợp và invalidate khi resource mới được tạo.
- [ ] Origin có rate limit, concurrency budget, bounded queue, circuit breaker và backpressure.
- [ ] Fallback không cho phép quyết định sai với booking, payment hoặc authorization.
- [ ] Metrics bao gồm origin QPS, refresh concurrency, waiter count, hot-key skew và stale age.
- [ ] Đã diễn tập cache flush, node failure, slow origin, duplicate refresh và lock expiry.

Cache stampede xảy ra khi nhiều request cùng tái tạo một giá trị; hot key xảy ra khi một vài key tập trung phần lớn traffic. TTL jitter làm expiry bớt đồng loạt, request coalescing gộp các lần nạp trùng, stale-while-revalidate giảm yêu cầu chờ, còn replication và local/edge cache tăng năng lực đọc cho key phổ biến. Các biện pháp này cần đi cùng origin guard, freshness policy và quan sát đầy đủ để cache failure không lan thành database outage hoặc làm sai trạng thái nghiệp vụ.
