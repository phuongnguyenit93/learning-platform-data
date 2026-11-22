# Cache-aside, read-through, write-through và write-behind

Cache giúp ứng dụng đọc dữ liệu nhanh hơn bằng cách giữ một bản sao gần nơi sử dụng. Trong kiến trúc cloud, cache có thể giảm số lần truy vấn database, giảm latency và hấp thụ một phần tải đột biến. Nhưng cache cũng tạo ra một bản dữ liệu thứ hai, có vòng đời và quy tắc cập nhật riêng. Nếu không xác định rõ ai nạp dữ liệu, ai ghi dữ liệu chuẩn và khi nào cache bị làm mới, hệ thống có thể trả dữ liệu cũ, mất cập nhật hoặc làm database quá tải khi cache gặp sự cố.

Bốn mẫu phổ biến để phối hợp cache với kho dữ liệu là **cache-aside**, **read-through**, **write-through** và **write-behind** (còn gọi là write-back). Chúng khác nhau ở việc ứng dụng hay cache chịu trách nhiệm nạp dữ liệu khi đọc, và ghi dữ liệu vào kho chính ở thời điểm nào. Không có một mẫu luôn tốt nhất: lựa chọn phụ thuộc vào tần suất đọc/ghi, mức nhất quán, khả năng chấp nhận mất dữ liệu, latency và cách vận hành.

Bài học thuộc phần **Bộ nhớ đệm** của học phần kiến trúc cloud. Mục tiêu là hiểu cách thiết kế cache như một thành phần trong đường đi dữ liệu, biết đánh đổi giữa hiệu năng và tính đúng đắn, và đưa ra quyết định có thể kiểm chứng theo các mục tiêu độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành.

Sau bài học, bạn có thể:

- Giải thích cache-aside, read-through, write-through và write-behind qua luồng đọc/ghi.
- Chọn pattern phù hợp với workload và yêu cầu nhất quán.
- Thiết kế TTL, invalidation, cache key, negative caching và xử lý dữ liệu stale.
- Kiểm soát cache stampede, thundering herd, hot key và cạnh tranh cập nhật.
- Xây dựng fallback khi cache lỗi, timeout hoặc mất kết nối.
- Bảo vệ dữ liệu cache, quan sát hit/miss/latency và kiểm soát chi phí.
- Kiểm thử hành vi cache trong tải cao, lỗi và tình huống cập nhật đồng thời.

## 1. Cache nằm ở đâu trong đường đi dữ liệu?

Ứng dụng thường dùng database hoặc dịch vụ nguồn làm nơi lưu dữ liệu chuẩn. Cache giữ bản sao có thể tái tạo của một phần dữ liệu để phục vụ truy cập thường xuyên nhanh hơn.

~~~mermaid
flowchart LR
    CLIENT["Client"] --> APP["Application service"]
    APP --> CACHE[("Cache")]
    CACHE -->|Miss| DB[("Primary database")]
    DB -->|Load data| CACHE
    CACHE -->|Hit / loaded value| APP
    APP --> CLIENT
~~~

Sơ đồ khái quát một đường đọc. Luồng ghi cần được thiết kế riêng: ghi vào cache trước, ghi database trước hay ghi database bất đồng bộ sau khi cập nhật cache tạo ra khác biệt lớn về độ bền và tính nhất quán.

### Vì sao cần cache?

- **Giảm latency:** đọc từ memory/network gần ứng dụng thường nhanh hơn truy vấn nguồn dữ liệu từ xa.
- **Giảm tải database:** các lần đọc cùng dữ liệu không cần lặp lại query đắt tiền.
- **Hấp thụ burst:** cache có thể phục vụ nhiều lượt đọc khi nguồn dữ liệu không thay đổi thường xuyên.
- **Tăng khả năng phục vụ trong một số lỗi:** dữ liệu đã cache có thể giúp phục vụ tạm thời nếu ứng dụng được thiết kế cho stale read.
- **Giảm chi phí nguồn:** ít query, I/O hoặc compute hơn khi hit ratio đủ cao.

Cache cũng có chi phí: hạ tầng, network hop, serialization, invalidation, memory fragmentation, eviction và vận hành. Một cache phân tán không tự động nhanh hơn một truy vấn database có index tốt, đặc biệt khi dữ liệu ít được đọc lại hoặc cache nằm xa ứng dụng.

### Cache không phải nguồn dữ liệu chuẩn

Thông thường, database hoặc domain service sở hữu dữ liệu là **source of truth**. Cache là bản sao phục vụ hiệu năng. Khi cache bị xóa hoặc mất node, ứng dụng phải có cách tái tạo dữ liệu.

Có ngoại lệ như write-behind, nơi cache hoặc một hàng đợi ghi tạm thời tham gia đường ghi. Khi đó hệ thống phải coi cache/store đệm là một thành phần có trách nhiệm độ bền riêng, có replication, persistence, replay và quy trình khôi phục. Không thể gọi nó là cache có thể bỏ đi mà không làm rõ rủi ro mất dữ liệu.

## 2. Bốn pattern khác nhau ở điểm nào?

| Pattern | Khi đọc cache miss | Khi ghi | Chủ thể điều phối chính |
| --- | --- | --- | --- |
| **Cache-aside** | Ứng dụng đọc nguồn, sau đó tự nạp kết quả vào cache | Ứng dụng ghi nguồn rồi xóa/cập nhật cache theo policy | Ứng dụng |
| **Read-through** | Cache tự gọi loader/data source và lưu kết quả trước khi trả | Không quy định riêng cách ghi; thường kết hợp write-through hoặc invalidation | Cache layer/provider |
| **Write-through** | Thường đọc từ cache; miss được nạp theo cache-aside hoặc read-through | Ghi cache và nguồn đồng bộ theo một hợp đồng | Cache layer hoặc adapter |
| **Write-behind** | Đọc từ cache hoặc lớp đọc phù hợp | Ghi cache trước, xếp ghi xuống nguồn bất đồng bộ | Cache/write buffer và worker |

Điểm quan trọng: **read-through mô tả đường đọc; write-through và write-behind mô tả đường ghi**. Cache-aside thường để ứng dụng quản lý cả việc nạp khi miss và invalidation khi ghi. Một kiến trúc thực tế có thể ghép các mẫu, ví dụ cache-aside cho đọc và write-through hoặc cache invalidation cho ghi.

~~~mermaid
flowchart TD
    A["Chọn chiến lược cache"] --> R{"Đọc"}
    R --> CA["Cache-aside<br/>Application load on miss"]
    R --> RT["Read-through<br/>Cache invokes loader"]
    A --> W{"Ghi"}
    W --> WT["Write-through<br/>Cache + source synchronously"]
    W --> WB["Write-behind<br/>Cache first, source later"]
~~~

## 3. Cache-aside: ứng dụng chủ động nạp và làm mất hiệu lực cache

Cache-aside còn gọi là lazy loading. Ứng dụng kiểm tra cache trước. Nếu có dữ liệu, trả về ngay. Nếu miss, ứng dụng đọc source of truth, ghi kết quả vào cache rồi trả về caller.

### 3.1. Luồng đọc

~~~mermaid
sequenceDiagram
    participant A as Application
    participant C as Cache
    participant D as Database
    A->>C: GET key
    alt Cache hit
        C-->>A: Cached value
    else Cache miss
        C-->>A: Miss
        A->>D: SELECT data
        D-->>A: Current data
        A->>C: SET key with TTL
        C-->>A: Stored
    end
    A-->>A: Return result
~~~

Ví dụ, ứng dụng đặt lịch đọc hồ sơ bác sĩ theo doctor ID. Khi cache chưa có, service lấy hồ sơ từ database, serialize và lưu cache với TTL 5 phút. Những request tiếp theo có thể trả dữ liệu từ cache.

### 3.2. Luồng ghi: update source rồi invalidate

Một lựa chọn phổ biến là ghi database thành công rồi xóa cache:

~~~mermaid
sequenceDiagram
    participant A as Application
    participant D as Database
    participant C as Cache
    A->>D: UPDATE profile
    D-->>A: Commit success
    A->>C: DEL profile key
    C-->>A: Deleted
    A-->>A: Return success
~~~

Request đọc tiếp theo sẽ miss và nạp bản mới từ database. Cách này giảm rủi ro ghi cache một giá trị không được database commit.

Tuy nhiên, giữa thời điểm database commit và lệnh delete cache, một reader có thể đọc bản cũ. Nếu ứng dụng chết sau commit nhưng trước invalidation, cache cũ có thể còn cho tới khi TTL hết. Vì vậy:

- TTL là hàng rào cuối cùng để cache cũ tự hết hạn.
- Có thể phát sự kiện invalidation qua outbox để tăng độ tin cậy.
- Nếu yêu cầu đọc sau ghi rất chặt, có thể trả dữ liệu vừa commit từ writer hoặc dùng version/fencing thay vì chỉ dựa vào cache.
- Invalidation handler cần idempotent và có retry.

### 3.3. Ưu điểm và đánh đổi

**Ưu điểm**

- Dễ triển khai và kiểm soát trong ứng dụng.
- Chỉ cache dữ liệu thực sự được đọc.
- Cache lỗi có thể fallback về nguồn dữ liệu nếu database còn khả năng phục vụ.
- Không bắt buộc mọi đường ghi phải đi qua cache.

**Đánh đổi**

- Ứng dụng phải quản lý logic cache miss, TTL, key và invalidation.
- Cache miss tạo thêm query, có thể gây spike khi key hết hạn đồng thời.
- Invalidation sau commit có khoảng trống lỗi.
- Nhiều service cùng đọc một dữ liệu cần thống nhất format key và policy.

Cache-aside thường phù hợp với dữ liệu được đọc nhiều, chấp nhận một khoảng stale ngắn và có nguồn dữ liệu chuẩn đáng tin cậy.

## 4. Read-through: cache layer tự nạp dữ liệu

Với read-through, ứng dụng gửi yêu cầu đọc tới cache abstraction. Nếu key không tồn tại, cache layer gọi loader hoặc data source đã cấu hình, lấy dữ liệu, lưu cache và trả về ứng dụng.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant C as Read-through cache
    participant D as Data source
    A->>C: GET key
    alt Hit
        C-->>A: Cached value
    else Miss
        C->>D: Load(key)
        D-->>C: Value
        C->>C: Store with TTL
        C-->>A: Value
    end
~~~

### Cache loader và abstraction

Loader là thành phần biết cách lấy giá trị nếu cache miss. Nó có thể truy vấn database, gọi một service nội bộ hoặc ghép dữ liệu từ nguồn phù hợp. Ứng dụng chỉ dùng interface đọc; chi tiết load được đóng gói ở cache provider hoặc adapter.

Ví dụ pseudocode:

~~~java
Profile profile = profileCache.get(
    doctorId,
    id -> profileRepository.findById(id)
);
~~~

Đoạn code thể hiện ý tưởng loader; API thật phụ thuộc cache library. Cần xác định behavior khi loader trả null, exception, timeout hoặc nhiều request cùng miss.

### Ưu điểm

- Logic tải dữ liệu tập trung, giảm mã lặp ở nhiều caller.
- Có thể chuẩn hóa serialization, TTL và error handling.
- Nhiều ứng dụng dùng chung một cache abstraction.

### Đánh đổi

- Cache layer trở thành dependency quan trọng và có thể che giấu chi phí của loader.
- Debug miss và query source có thể khó hơn nếu observability kém.
- Loader cần kiểm soát concurrency, timeout, retry và lỗi nguồn.
- Không phải cache server hoặc managed cache nào cũng có read-through loader; một số cần library/sidecar/gateway trong ứng dụng.

Read-through phù hợp khi tổ chức muốn chuẩn hóa cách nạp dữ liệu hoặc có một lớp cache provider hỗ trợ loader rõ ràng. Nó không tự giải quyết invalidation khi dữ liệu được sửa từ một hệ thống khác.

## 5. Write-through: ghi cache và nguồn đồng bộ

Write-through yêu cầu thao tác ghi được chuyển qua cache layer. Cache ghi giá trị mới vào nguồn dữ liệu trước hoặc theo cơ chế đồng bộ đã định nghĩa, sau đó cập nhật cache và trả kết quả thành công.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant C as Write-through cache
    participant D as Database
    A->>C: PUT key, new value
    C->>D: Persist value
    D-->>C: Commit success
    C->>C: Update cache entry
    C-->>A: Success
~~~

Ưu điểm của write-through là sau khi thao tác thành công theo hợp đồng, cache thường chứa giá trị vừa ghi. Reader không phải chờ một lần cache miss để thấy giá trị mới.

### Các câu hỏi phải định nghĩa

- Source commit trước cache update hay ngược lại?
- Nếu source commit thành công nhưng cache update thất bại thì response là gì?
- Nếu cache cập nhật thành công nhưng source thất bại, có rollback cache được không?
- Thứ tự ghi có được bảo vệ khi hai writer cập nhật cùng key?
- Có transaction nguyên tử giữa cache và database không, hay chỉ là hai thao tác tuần tự?

Thông thường không có transaction ACID chung giữa cache và database độc lập. Vì vậy write-through vẫn phải xác định trạng thái partial failure. Một lựa chọn an toàn hơn là **source commit trước, sau đó update cache; nếu update cache lỗi thì invalidate cache và để lần đọc kế tiếp nạp lại**. Hợp đồng response phải phản ánh rõ source đã commit hay chưa.

### Ưu điểm và đánh đổi

**Ưu điểm**

- Dữ liệu cache được làm mới ngay sau một ghi thành công theo flow chuẩn.
- Giảm khoảng thời gian stale so với chỉ chờ TTL.
- Có thể đơn giản hóa read path.

**Đánh đổi**

- Write latency tăng vì thao tác ghi phải chạm cả cache và source.
- Mọi writer phải đi qua cùng policy; ghi trực tiếp vào database sẽ phá giả định.
- Partial failure vẫn có thể xảy ra giữa hai hệ thống.
- Dữ liệu ít được đọc vẫn tiêu tốn cache memory.

Write-through phù hợp khi nhiều lần đọc cần thấy giá trị mới sớm và lưu lượng ghi không quá nhạy với chi phí đồng bộ. Cần đánh giá kỹ nếu database có nhiều writer độc lập hoặc cache được chia sẻ bởi nhiều ứng dụng.

## 6. Write-behind: cache nhận ghi trước, source cập nhật sau

Write-behind (write-back) phản hồi cho caller sau khi thay đổi được ghi vào cache hoặc write buffer, còn việc ghi vào database diễn ra bất đồng bộ. Hệ thống có thể gom nhiều thay đổi, ghi theo lô hoặc giảm số lần truy cập nguồn.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant C as Cache / write buffer
    participant Q as Durable queue or log
    participant W as Writer worker
    participant D as Database
    A->>C: Write value
    C->>Q: Persist pending write
    Q-->>C: Durable acknowledgement
    C-->>A: Accepted
    Q->>W: Deliver pending write
    W->>D: Apply write
    D-->>W: Commit
    W->>Q: Mark processed
~~~

Điểm quan trọng trong sơ đồ là cần một **durable queue/log hoặc cơ chế persistence tương đương** nếu hệ thống muốn tuyên bố ghi đã được chấp nhận an toàn trước khi database commit. Nếu chỉ đặt dữ liệu trong RAM của cache node rồi trả success, node mất điện có thể làm mất các ghi chưa flush.

### Khi nào write-behind hữu ích?

- Tải ghi rất cao, có thể batch nhiều cập nhật.
- Chấp nhận độ trễ trước khi dữ liệu xuất hiện trong nguồn chính.
- Ghi vào cache/buffer nhanh hơn ghi đồng bộ vào database.
- Có thể xử lý eventual consistency và có quy trình replay/reconciliation.

Ví dụ bộ đếm lượt xem có thể ghi tăng vào buffer, rồi worker tổng hợp theo lô. Ngược lại, giao dịch chuyển tiền hoặc giữ khung giờ đặt lịch không nên dùng write-behind tùy tiện nếu caller cần xác nhận nguồn dữ liệu đã commit.

### Rủi ro chính

- **Mất dữ liệu:** buffer không bền vững hoặc queue chưa replicate.
- **Backlog:** writer không theo kịp tốc độ ghi, độ trễ đồng bộ tăng.
- **Thứ tự sai:** nhiều worker xử lý update cùng key không đúng trình tự.
- **Ghi lặp:** worker commit database rồi chết trước khi ack, dẫn tới redelivery.
- **Mất đồng bộ:** cache đã phản ánh giá trị mới nhưng database vẫn cũ hoặc ghi thất bại.
- **Xung đột:** một writer trực tiếp cập nhật database trong khi write-behind còn pending.

### Điều kiện cần có trước production

- Write buffer được lưu bền vững và có replication phù hợp.
- Mỗi mutation có operation/event ID và được xử lý idempotent.
- Có ordering theo key/aggregate nếu nghiệp vụ cần.
- Có giới hạn backlog, cảnh báo oldest age và backpressure.
- Có dead-letter/quarantine và khả năng replay có kiểm soát.
- Có reconciliation để so sánh cache/buffer với database.
- Có policy khi writer không phục hồi trong thời hạn cho phép.

## 7. So sánh theo tình huống đọc và ghi

| Tiêu chí | Cache-aside | Read-through | Write-through | Write-behind |
| --- | --- | --- | --- | --- |
| Cache miss | Application load | Cache layer gọi loader | Cần kết hợp một read pattern | Thường đọc từ cache/buffer hoặc source |
| Nơi ghi chuẩn | Thường source trước | Không quyết định riêng đường ghi | Source được cập nhật đồng bộ qua cache layer | Source cập nhật bất đồng bộ |
| Write latency | Thường thấp hơn do app ghi source rồi invalidate; có thêm invalidation | Tùy pattern ghi kết hợp | Cao hơn do đồng bộ với source | Thấp ở front path nếu buffer ack nhanh |
| Độ trễ stale | Có thể tồn tại tới invalidation/TTL | Phụ thuộc refresh/invalidation | Thường thấp sau ghi thành công theo hợp đồng | Có chủ đích cho tới khi flush |
| Độ phức tạp | Vừa phải, ở application | Loader/provider | Điều phối partial failure hai nơi | Cao: queue, replay, ordering, recovery |
| Rủi ro nổi bật | Cache stale, stampede | Loader bottleneck | Partial write failure | Data loss/backlog/duplicate |
| Use case điển hình | Hồ sơ, catalog, cấu hình ít đổi | Cache abstraction dùng chung | Dữ liệu đọc lại ngay sau ghi | Counter, telemetry hoặc batchable update có thể eventual |

Không nên coi bốn mẫu là bốn công nghệ cache tách biệt. Đây là **pattern phối hợp đường đọc và đường ghi**. Một hệ thống có thể dùng cache-aside cho profile, read-through cho catalog, write-through cho cấu hình và write-behind cho counter không quan trọng.

## 8. TTL, invalidation và dữ liệu stale

Cache cần chính sách vòng đời. **TTL (time to live)** xác định một entry có thể tồn tại bao lâu trước khi hết hạn. TTL dài tăng hit ratio nhưng tăng rủi ro stale; TTL ngắn giảm thời gian stale tối đa theo lý thuyết nhưng tăng miss và tải nguồn.

### Chọn TTL theo semantics dữ liệu

| Dữ liệu | TTL gợi ý để bắt đầu thử nghiệm | Lưu ý |
| --- | --- | --- |
| Danh mục công khai ít đổi | Vài phút đến hàng giờ | Có thể invalidation khi publish |
| Hồ sơ người dùng | Vài chục giây đến vài phút | Cập nhật quyền/thông tin cần policy chặt |
| Feature/config | Theo vòng đời release hoặc vài phút | Cần versioning và khả năng refresh |
| Kết quả query đắt | Tùy access pattern và độ nhạy freshness | Key phải chứa mọi filter liên quan |
| Dữ liệu tồn kho/slot | TTL ngắn hoặc không cache quyết định cuối | Revalidate trên source khi đặt thật |
| Negative cache (không tìm thấy) | Rất ngắn | Resource có thể vừa được tạo |

Các khoảng trên chỉ là điểm bắt đầu để benchmark, không phải tiêu chuẩn chung. TTL nên xuất phát từ yêu cầu freshness của nghiệp vụ.

### Invalidation theo sự kiện

Khi dữ liệu thay đổi, service sở hữu có thể phát event để xóa hoặc cập nhật cache. Nên dùng transactional outbox khi cần bảo đảm event không bị mất giữa database commit và publish.

Ví dụ event ProfileUpdated chứa profile ID và version. Cache consumer chỉ cập nhật hoặc invalidate nếu version mới hơn version đang có; event cũ đến trễ không được ghi đè dữ liệu mới.

### Versioned key

Một cách giảm race condition là đưa version vào cache key:

~~~text
profile:{profileId}:v{version}
~~~

Ứng dụng tra cứu version hiện hành từ một nguồn điều phối đáng tin cậy hoặc metadata phù hợp, rồi đọc key tương ứng. Cách này giảm ghi đè vào key cũ nhưng vẫn cần cơ chế xác định version hiện tại và cleanup key cũ.

### Cache stale có chủ đích

Một số nghiệp vụ chấp nhận **stale-while-revalidate**: trả dữ liệu còn dùng được trong khi nạp bản mới ở nền. Có thể cải thiện latency và tăng khả năng phục vụ, nhưng cần:

- Định nghĩa tuổi dữ liệu tối đa.
- Không áp dụng cho trạng thái cần kiểm tra ngay trước side effect.
- Đánh dấu thời điểm/version dữ liệu cho client nếu cần.
- Giới hạn số lần refresh đồng thời.
- Có fallback nếu refresh thất bại và stale data đã quá hạn.

## 9. Cache key, serialization và phạm vi dữ liệu

Cache key là địa chỉ logic của entry. Thiết kế key sai có thể trả dữ liệu nhầm tenant hoặc nhầm biến thể query.

Một cache key cần bao gồm mọi yếu tố làm thay đổi kết quả:

- Resource identifier.
- Tenant/organization nếu dữ liệu phân tách theo tenant.
- Locale, currency hoặc role/permission scope khi ảnh hưởng kết quả.
- Query filters, sort, page/cursor nếu cache response danh sách.
- Schema/data version khi định dạng thay đổi.
- Feature flags hoặc tham số nghiệp vụ cần thiết.

Ví dụ:

~~~text
booking:tenant-21:doctor-42:date-2026-11-18
catalog:tenant-21:locale-vi-VN:category-8:page-1
profile:user-991:v17
~~~

Không đặt raw access token, email hoặc dữ liệu cá nhân không cần thiết vào key. Key nên có giới hạn độ dài, naming convention và namespace để tránh collision.

### Serialization

Cache thường lưu byte/string, nên ứng dụng cần chọn format serialization. JSON dễ debug và tương thích nhưng có overhead; binary format có thể nhỏ/nhanh hơn nhưng cần quản lý schema/version. Cache entry nên có:

- Schema version.
- Data version hoặc updated timestamp nếu cần.
- TTL phù hợp.
- Kích thước có kiểm soát.
- Quy tắc xử lý payload không parse được.

Khi deploy version mới không đọc được format cũ, cần chiến lược namespace/versioned key hoặc invalidate có kiểm soát. Không để serialization failure khiến mọi request liên tục truy vấn nguồn và tạo stampede.

## 10. Cache stampede, thundering herd và hot key

Khi một key phổ biến hết hạn, rất nhiều request có thể cùng miss và truy vấn database cùng lúc. Đây là **cache stampede** hoặc thundering herd. Một key cực kỳ phổ biến cũng có thể thành hot key, gây bão hòa một shard/node.

### Các biện pháp

1. **Request coalescing/single-flight:** chỉ một request nạp key, các request khác chờ kết quả.
2. **TTL jitter:** thêm độ lệch ngẫu nhiên vào TTL để nhiều entry không hết hạn cùng thời điểm.
3. **Refresh ahead:** làm mới trước khi entry hết hạn theo policy.
4. **Stale-while-revalidate:** phục vụ bản cũ trong giới hạn cho phép.
5. **Negative caching:** cache kết quả không tìm thấy trong thời gian ngắn để tránh query lặp.
6. **Rate limit/load shedding:** giới hạn tải xuống source khi cache mất hiệu lực.
7. **Sharding/replication:** phân phối tải hot key nếu kiến trúc và semantics cho phép.

### Ví dụ single-flight ở một instance

Một service có thể giữ một future/promise cho mỗi key đang được nạp. Các request trong cùng process đợi chung future. Nhưng cơ chế local chỉ coalesce trong một instance; nhiều instance vẫn có thể đồng thời miss. Nếu cần coordination toàn cụm, phải dùng cơ chế phân tán có timeout và fencing an toàn, hoặc chấp nhận số loader song song có giới hạn.

Không dùng distributed lock thiếu lease/fencing rồi giả định nó bảo đảm tuyệt đối. Lock hết hạn khi loader cũ vẫn chạy có thể cho phép hai loader cùng ghi. Version check hoặc compare-and-set giúp tránh dữ liệu cũ ghi đè dữ liệu mới.

### Cache hit ratio không phải mục tiêu duy nhất

Hit ratio cao nhưng trả dữ liệu stale có thể làm hỏng nghiệp vụ. Hit ratio thấp có thể là chấp nhận được nếu nguồn query rẻ và latency đạt mục tiêu. Theo dõi cả:

- Hit/miss theo key class hoặc endpoint.
- Loader calls và database load.
- Latency p50/p95/p99 của hit và miss.
- Stale age và invalidation lag.
- Eviction, memory pressure, hot key và payload size.

## 11. Concurrency và cập nhật cạnh tranh

Hai writer có thể cập nhật cùng một key gần như đồng thời. Nếu không có version hoặc thứ tự, writer cũ đến sau có thể ghi đè giá trị mới.

Ví dụ:

1. Request A đọc version 10.
2. Request B đọc version 10.
3. B cập nhật source thành version 12 và cache.
4. A hoàn thành chậm, ghi version 11 vào cache.

Cache trở về dữ liệu cũ dù source đang ở version 12. Cần áp dụng một trong các cách:

- Compare-and-set: chỉ ghi cache nếu version mới hơn version hiện tại.
- Optimistic concurrency: update source với điều kiện version vẫn như lúc đọc.
- Invalidation theo version và bỏ qua event đến trễ.
- Serialize update theo aggregate/key nếu yêu cầu ordering chặt.
- Đọc version từ source of truth khi xử lý thao tác quan trọng.

Cache là bản sao, nên không nên dùng lock cache để thay transaction/constraint nghiệp vụ trong database. Ví dụ giữ một slot đặt lịch phải được bảo vệ bằng transaction/unique constraint tại datastore, không chỉ bằng cache lock.

## 12. Failure mode và fallback

Cache có thể timeout, mất node, failover, đầy memory, eviction, partition mạng hoặc trả dữ liệu không deserialize được. Ứng dụng cần xác định cache là dependency bắt buộc hay tối ưu có thể bỏ qua.

### Khi cache không khả dụng

Với cache-aside, ứng dụng có thể fallback về database. Nhưng nếu mọi request đồng thời fallback, database có thể bị quá tải. Fallback cần:

- Timeout ngắn và circuit breaker.
- Giới hạn concurrency tới database.
- Rate limit hoặc load shedding khi database gần bão hòa.
- Bulkhead để lỗi cache không chiếm toàn bộ thread pool.
- Retry có giới hạn, tránh retry storm.
- Cảnh báo cache unavailable và database saturation.

Nếu cache được dùng làm durable write buffer trong write-behind, không được bỏ qua cache khi lỗi. Cần dừng hoặc buffer tại một hệ thống bền vững khác; trả lỗi/accepted status đúng với mức dữ liệu đã được lưu an toàn.

### Cache failover

Một dịch vụ cache managed có thể cung cấp replication và failover, nhưng client vẫn có thể gặp connection reset, DNS change hoặc dữ liệu mất theo cấu hình. Cần kiểm tra:

- Replication mode và khả năng mất write gần nhất.
- Client reconnect/backoff.
- Read endpoint sau failover.
- Eviction/persistence behavior.
- Ảnh hưởng tới hit ratio khi toàn bộ cache warm-up lại.

### Cache poisoning và dữ liệu không hợp lệ

Nếu attacker có thể ghi cache key hoặc nội dung tùy ý, dữ liệu độc hại có thể được phục vụ cho nhiều người dùng. Phải phân quyền write path, validate payload, namespace theo tenant, kiểm tra serialization và không tin input làm cache key trực tiếp.

## 13. Bảo mật và quyền riêng tư

Cache thường chứa bản sao dữ liệu ứng dụng; vì vậy yêu cầu bảo mật không thấp hơn nguồn dữ liệu chỉ vì đây là dữ liệu tạm.

- Dùng private networking và firewall/security group để giới hạn client.
- Bật TLS trên đường truyền nếu dịch vụ và môi trường yêu cầu.
- Dùng authentication/ACL/identity phù hợp; không để cache endpoint công khai.
- Phân tách namespace và quyền theo service/tenant.
- Mã hóa dữ liệu at rest nếu nền tảng hỗ trợ và dữ liệu cần bảo vệ.
- Không cache token, secret hoặc dữ liệu nhạy cảm nếu không có nhu cầu rõ.
- Với dữ liệu cá nhân, có policy TTL, deletion và invalidation sau khi người dùng yêu cầu xóa.
- Tránh ghi cache value/key vào log; mask thông tin khi trace.
- Kiểm soát snapshot/export và quyền truy cập console.

### Authorization trước hay sau cache?

Nếu cache một response đã lọc theo người dùng, key phải phản ánh đúng quyền/tenant hoặc dữ liệu phải được phân quyền lại ở mỗi request. Không dùng chung cache key cho response đã chứa dữ liệu cá nhân nếu caller khác có thể nhận kết quả đó.

Một lựa chọn an toàn là cache dữ liệu domain đã phân quyền phù hợp ở tầng service rồi áp dụng authorization trên mỗi request. Không coi việc key khó đoán là biện pháp authorization.

## 14. Quan sát, vận hành và chi phí

Cache cần dashboard và alert riêng, nhưng metric phải liên kết với trải nghiệm người dùng và nguồn dữ liệu.

| Metric | Dùng để trả lời |
| --- | --- |
| Hit/miss ratio | Cache có phục vụ phần lớn access pattern dự kiến không? |
| Hit/miss latency | Cache có thực sự giảm latency so với loader không? |
| Evictions/expired entries | Memory có thiếu hoặc TTL quá ngắn không? |
| Memory used/fragmentation | Có nguy cơ hết memory hoặc payload tăng không? |
| Connections/commands per second | Client có tạo quá nhiều connection/command không? |
| Hot key / top key cardinality | Một key hoặc shard có lệch tải không? |
| Loader/database QPS | Cache miss có làm nguồn dữ liệu quá tải không? |
| Invalidation lag | Dữ liệu mới mất bao lâu để phản ánh trong cache? |
| Stale age | Caller có thể nhận dữ liệu cũ bao lâu? |
| Write-behind backlog/oldest age | Source đang chậm hơn tốc độ nhận ghi bao nhiêu? |
| DLQ/retry count | Có mutation/event không thể áp dụng không? |
| Cache spend / cost per request | Tiền cache tiết kiệm được có lớn hơn chi phí không? |

### Ước lượng hiệu quả chi phí

Giả sử endpoint có 1.000 request/giây, hit ratio 90%, mỗi lần query database có chi phí tài nguyên tương đương một đơn vị. Khi cache hoạt động, số query nguồn lý thuyết còn khoảng 100/giây, chưa tính refresh, invalidation, retry và query khác.

Đây là phép tính đơn giản để hình dung. TCO cần cộng cache node, replication, network, serialization CPU, observability và vận hành. Nếu cache tăng thêm latency nhưng chỉ đạt hit ratio thấp, giải pháp có thể không đáng.

### Chọn capacity

Ước tính memory dựa trên số entry hoạt động, payload thực tế, metadata, key, overhead của engine, replication và headroom. Không lấy tổng kích thước JSON thô rồi coi đó là dung lượng cần provision. Phải đo trên engine/instance type mục tiêu và tải đại diện.

## 15. Chọn pattern theo yêu cầu

Một quyết định tốt bắt đầu từ câu hỏi: **nếu cache stale, mất hoặc chậm thì điều gì xảy ra với nghiệp vụ?**

| Câu hỏi | Hướng lựa chọn có thể phù hợp |
| --- | --- |
| Dữ liệu đọc nhiều, ghi ít, có thể chấp nhận stale ngắn? | Cache-aside hoặc read-through |
| Muốn tập trung logic nạp dữ liệu vào cache abstraction? | Read-through |
| Sau khi ghi, phần lớn caller cần đọc lại ngay và write latency chấp nhận tăng? | Write-through |
| Có thể chấp nhận source cập nhật trễ, cần gom/batch lượng ghi rất lớn? | Write-behind, chỉ khi có durable buffer và recovery |
| Dữ liệu cần quyết định giao dịch ngay, ví dụ slot hoặc số dư? | Source of truth/transaction; cache chỉ hỗ trợ đọc, không quyết định cuối |
| Nhiều writer độc lập? | Ưu tiên invalidation/version strategy và transaction ở source; cẩn trọng write-through |
| Cache không khả dụng mà hệ thống vẫn phải ghi bền vững? | Không phụ thuộc cache làm buffer duy nhất nếu durability chưa được chứng minh |

### Cây quyết định tham khảo

~~~mermaid
flowchart TD
    A["Xác định access pattern"] --> B{"Chủ yếu cần tối ưu đọc?"}
    B -- "Có" --> C{"Ứng dụng tự quản lý loader được?"}
    C -- "Có" --> D["Cache-aside"]
    C -- "Muốn loader tập trung" --> E["Read-through"]
    B -- "Cần chọn chiến lược ghi" --> F{"Source phải commit trước response?"}
    F -- "Có" --> G["Write-through hoặc source write + invalidate"]
    F -- "Không, chấp nhận eventual" --> H{"Có durable buffer, replay và idempotency?"}
    H -- "Có" --> I["Đánh giá write-behind"]
    H -- "Không" --> J["Không ack trước khi dữ liệu bền vững"]
~~~

Cây chỉ là hướng dẫn khởi đầu. Kiến trúc có thể cần kết hợp nhiều pattern theo từng loại dữ liệu.

## 16. Ví dụ thiết kế cache cho ứng dụng đặt lịch

**Bối cảnh giả định:** Một ứng dụng có ba loại dữ liệu:

- Hồ sơ bác sĩ và mô tả dịch vụ: đọc nhiều, cập nhật không thường xuyên.
- Danh sách slot có thể đặt: đọc nhiều, thay đổi liên tục khi người dùng đặt/hủy.
- Số lượt xem trang bác sĩ: cập nhật liên tục, có thể chấp nhận tổng hợp trễ vài giây.

### Hồ sơ bác sĩ

Dùng cache-aside hoặc read-through với TTL vài phút. Khi admin cập nhật hồ sơ, database commit rồi phát event invalidation. Nếu event bị trễ, TTL giới hạn thời gian stale. Cache key có tenant/locale nếu nội dung khác nhau.

### Slot có thể đặt

Cache có thể phục vụ danh sách slot để hiển thị nhanh, nhưng **không quyết định việc đặt thành công**. Khi khách hàng chọn slot, Booking Service revalidate và ghi qua transaction/constraint tại database hoặc dịch vụ giữ chỗ có consistency phù hợp. Sau khi commit, invalidate/version slot cache. Có thể hiển thị timestamp dữ liệu để khách hiểu danh sách vừa được cập nhật.

### Số lượt xem

Có thể dùng write-behind hoặc counter aggregation nếu chấp nhận số liệu trễ và có durable event buffer. Mỗi event cần ID để consumer idempotent; worker batch update source. Có dashboard backlog, oldest event age và reconciliation.

### Sơ đồ tổng thể

~~~mermaid
flowchart TD
    USER["Browser / Mobile"] --> API["Application API"]
    API --> PROFILE["Profile cache-aside<br/>TTL + invalidation"]
    PROFILE --> PDB[("Profile database")]
    API --> SLOT["Slot cache<br/>Read optimization only"]
    SLOT --> SDB[("Booking database<br/>Source of truth")]
    API --> BOOK["Reserve/confirm transaction"]
    BOOK --> SDB
    BOOK --> INV["Invalidate slot cache"]
    API --> COUNTER["View counter buffer"]
    COUNTER --> Q[("Durable event log / queue")]
    Q --> WORKER["Batch consumer"]
    WORKER --> ANALYTICS[("Analytics store")]
~~~

### Điều cần kiểm chứng

- Cập nhật profile commit nhưng invalidation event bị mất: TTL/replay có khôi phục không?
- Hai người dùng cùng đặt slot đang cache là còn trống: database constraint có ngăn double booking không?
- Cache mất toàn bộ node: database có chịu được cold cache load không?
- View counter event được giao lặp: số đếm có bị tăng hai lần không?
- Tenant A không nhận cache entry của tenant B: key và authorization có đúng không?

## 17. Bài thực hành: thiết kế và kiểm thử bốn cache pattern

**Bối cảnh:** Một nền tảng thương mại điện tử có catalog, tồn kho, hồ sơ khách hàng và lượt xem sản phẩm. Catalog được đọc nhiều, thay đổi theo đợt; tồn kho thay đổi liên tục; hồ sơ có dữ liệu theo tenant; lượt xem có thể tổng hợp trễ. Ở tải cao điểm, catalog nhận 5.000 read request/giây; database không được vượt 1.000 query/giây. Đây là số liệu giả định cho bài tập.

### Nhiệm vụ 1 — Chọn pattern theo từng dữ liệu

Đề xuất cache-aside/read-through cho catalog và profile, chiến lược cho inventory và write-behind cho view counter nếu phù hợp. Giải thích dữ liệu nào được phép stale, tối đa bao lâu, và thao tác nào bắt buộc đi qua source of truth.

### Nhiệm vụ 2 — Thiết kế key và TTL

Viết cache key cho catalog theo locale/category/page, profile theo tenant/user, inventory theo SKU/warehouse và counter theo product ID. Chọn TTL ban đầu và cách invalidation/versioning.

### Nhiệm vụ 3 — Xử lý concurrency

Mô phỏng nhiều request đồng thời miss cùng một catalog key. Thiết kế single-flight, jitter hoặc stale-while-revalidate. Với inventory, chứng minh cache không quyết định giao dịch cuối.

### Nhiệm vụ 4 — Thiết kế write failure

Phân tích source commit thành công nhưng cache update thất bại; cache update thành công nhưng source thất bại; write-behind buffer nhận ghi nhưng worker không chạy; worker commit rồi chết trước ack. Định nghĩa trạng thái và phục hồi.

### Nhiệm vụ 5 — Capacity và observability

Tính QPS nguồn theo hit ratio mục tiêu, ước lượng memory theo payload, đề xuất replication/headroom. Tạo dashboard hit/miss, latency, eviction, loader QPS, stale age, invalidation lag và backlog.

### Nhiệm vụ 6 — Kiểm thử lỗi và bảo mật

Thử cache unavailable, node failover, key collision, cross-tenant access, malformed entry, hot key và event duplicate. Thu bằng chứng về latency, database saturation, dữ liệu stale và side effect trùng.

### Ma trận phép thử

| Phép thử | Tác động | Kết quả cần kiểm tra |
| --- | --- | --- |
| Cold cache | Xóa/đổi namespace cache trong môi trường thử | Database không bị stampede vượt quota |
| Stampede | Cho key phổ biến hết TTL đồng thời | Loader bị giới hạn; latency và source QPS trong ngưỡng |
| Invalidation gap | Commit DB rồi cố ý làm lỗi publish invalidation | Outbox/retry hoặc TTL phục hồi trong freshness bound |
| Concurrent inventory update | Nhiều user đặt cùng SKU/slot | Source constraint bảo vệ tồn kho, không dựa vào cache |
| Write-through partial failure | Cache/database một bên lỗi | Trạng thái được phản ánh rõ, có invalidate/reconcile |
| Write-behind crash | Worker chết sau DB commit trước ack | Redelivery không ghi side effect trùng |
| Cache outage | Chặn kết nối tới cache | Fallback có giới hạn, không làm nguồn quá tải |
| Tenant isolation | Dùng cùng resource ID ở hai tenant | Không trả nhầm cache entry |
| Stale event | Event version cũ đến sau event mới | Giá trị mới không bị ghi đè |
| Capacity peak | Tăng QPS và hot key | Không vượt memory/connection/quota; SLO đạt |

## 18. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi cho cache pattern |
| --- | --- |
| **Operational Excellence** | Có runbook warm-up, invalidation, failover, cache flush và xử lý backlog không? Key/TTL/policy có được quản lý bằng code và review? |
| **Security** | Cache có private access, identity, TLS, encryption, tenant isolation và data retention phù hợp không? |
| **Reliability** | Cache mất thì ứng dụng fallback thế nào? Stampede, hot key, write-behind recovery và stale bound đã được thử? |
| **Performance Efficiency** | Hit ratio, latency, memory, serialization, loader QPS và query cost có được đo? |
| **Cost Optimization** | Cache capacity, replication, network, eviction và vận hành có tiết kiệm hơn nguồn dữ liệu không? |
| **Sustainability** | Có tránh giữ cache ít dùng, refresh/polling dư thừa và payload lớn không cần thiết không? |

## 19. Những sai lầm thường gặp

**Dùng cache làm source of truth mà không thiết kế durability.** Cache có thể evict, failover hoặc mất dữ liệu theo cấu hình; dữ liệu quan trọng phải có nơi lưu bền vững.

**Chọn TTL giống nhau cho mọi key.** Catalog, profile, tồn kho và counter có yêu cầu freshness khác nhau.

**Chỉ invalidate sau ghi mà không xử lý lỗi giữa commit và delete.** Outbox/retry hoặc versioning cần đảm bảo khoảng trống không kéo dài vô hạn.

**Cho phép hai writer ghi cache không có version.** Writer cũ hoàn tất sau có thể ghi đè dữ liệu mới.

**Dùng cache lock thay transaction nghiệp vụ.** Lock cache không thay uniqueness/transaction ở database.

**Ghi thành công vào RAM rồi ack write-behind.** Node mất có thể làm mất mutation chưa flush; cần durable buffer và replay.

**Không giới hạn fallback.** Cache outage có thể đẩy toàn bộ tải về database và gây cascading failure.

**Chỉ theo dõi hit ratio.** Hit ratio cao không chứng minh dữ liệu mới hoặc latency tốt.

**Bỏ tenant/locale/filter khỏi cache key.** Dữ liệu có thể rò giữa tenant hoặc trả sai biến thể.

**Coi read-through tự giải quyết invalidation.** Loader chỉ xử lý miss; dữ liệu được sửa ngoài cache vẫn cần refresh hoặc invalidate.

**Bỏ qua cache stampede và hot key.** Một key hết hạn có thể làm nguồn dữ liệu quá tải.

**Không có quy trình xóa dữ liệu cá nhân khỏi cache.** Data lifecycle phải bao gồm cả bản sao và snapshot.

## 20. Checklist trước khi đưa cache vào production

- [ ] Source of truth và loại dữ liệu được phép cache đã xác định.
- [ ] Pattern đọc/ghi được chọn theo yêu cầu freshness, durability và latency.
- [ ] Cache key chứa tenant, locale, filter, version và mọi yếu tố ảnh hưởng kết quả.
- [ ] TTL, invalidation, negative caching và stale-while-revalidate có policy theo từng data class.
- [ ] Writer cạnh tranh được bảo vệ bằng version/transaction ở nơi sở hữu dữ liệu.
- [ ] Cache-aside/read-through loader có timeout, retry và request coalescing.
- [ ] Write-through có xử lý partial failure giữa cache và source.
- [ ] Write-behind có durable buffer, idempotency, ordering, DLQ, replay và reconciliation.
- [ ] Cache stampede, hot key, memory pressure và cold-cache load đã được thử.
- [ ] Fallback khi cache lỗi có concurrency/rate limit để không làm sập database.
- [ ] Client, network, secret, TLS, tenant isolation và data retention được kiểm soát.
- [ ] Dashboard có hit/miss, latency, eviction, loader QPS, stale age và invalidation lag.
- [ ] Chi phí cache, replication, network, log và nguồn dữ liệu được so sánh.
- [ ] Có runbook failover, flush, warm-up, invalidation, replay và xử lý dữ liệu sai.
- [ ] Các test concurrent, failure, security và load có bằng chứng đạt mục tiêu.

Cache-aside, read-through, write-through và write-behind là những cách tổ chức trách nhiệm giữa ứng dụng, cache và kho dữ liệu. Cache-aside để ứng dụng chủ động nạp và invalidate; read-through đưa loader vào cache layer; write-through đồng bộ ghi với source; write-behind nhận ghi trước rồi cập nhật source bất đồng bộ. Lựa chọn đúng phụ thuộc dữ liệu nào được phép stale, nguồn nào là chuẩn, và hệ thống có thể phục hồi ra sao khi một bước thành công còn bước kia thất bại. Cache chỉ đem lại lợi ích bền vững khi TTL, invalidation, concurrency, fallback, bảo mật và quan sát được thiết kế cùng với pattern.
