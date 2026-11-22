# Xác định dữ liệu phù hợp và mục tiêu của bộ nhớ đệm

Bộ nhớ đệm (cache) thường được thêm vào khi hệ thống chậm hoặc database chịu tải cao. Tuy nhiên, cache không tự động làm mọi ứng dụng nhanh hơn. Nó tạo thêm một bản sao dữ liệu, có thể cũ hơn nguồn chính, cần dung lượng và quy trình hết hạn/làm mới. Nếu cache nhầm dữ liệu, đặt TTL thiếu cơ sở hoặc không có cách xử lý cache miss, hệ thống có thể trả kết quả sai, tăng tải đột biến hoặc khó khôi phục khi cache ngừng hoạt động.

Trước khi chọn Redis, Memcached, CDN hay cache trong tiến trình, kiến trúc sư cần trả lời câu hỏi căn bản: **dữ liệu nào đáng được cache, để đạt mục tiêu gì và chấp nhận dữ liệu cũ tới mức nào?**

Bài học này thuộc chương **Bộ nhớ đệm** của module **CLOUD_ARCHITECTURE**. Mục tiêu là phân tích access pattern, giá trị của việc tái sử dụng dữ liệu, độ mới và tính nhất quán; xác định mục tiêu latency, throughput và cost; chọn dữ liệu phù hợp và nhận diện trường hợp không nên cache. Những quyết định này cần cân bằng độ tin cậy, bảo mật, hiệu năng, chi phí và vận hành theo tư duy Well-Architected.

## 1. Cache giải quyết vấn đề gì?

Cache giữ một bản sao dữ liệu hoặc kết quả tính toán ở nơi có thể truy cập nhanh hơn nguồn chính. Khi có yêu cầu:

- **Cache hit:** dữ liệu cần thiết có sẵn trong cache và được trả về theo chính sách.
- **Cache miss:** cache không có bản sao phù hợp; hệ thống lấy từ nguồn chính hoặc tính toán lại rồi có thể lưu vào cache.
- **Stale entry:** dữ liệu còn trong cache nhưng không còn phản ánh trạng thái mới nhất của nguồn.
- **Eviction:** cache loại bỏ một entry để giải phóng dung lượng hoặc theo chính sách thay thế.
- **Invalidation:** entry được đánh dấu không còn hợp lệ hoặc bị xóa khi nguồn thay đổi.

Ví dụ, Booking API hiển thị trang chi tiết phòng. Thông tin mô tả, ảnh, tiện ích và chính sách hủy thường được đọc nhiều lần nhưng ít thay đổi. Giá và tình trạng còn chỗ lại có thể thay đổi liên tục. Nếu cache mọi trường với TTL dài giống nhau, giao diện có thể hiển thị giá hoặc availability sai.

~~~mermaid
flowchart LR
    U["Client request"] --> APP["Application"]
    APP --> C{"Cache hit?"}
    C -->|"Yes"| R["Return cached data"]
    C -->|"No"| DB[("Source of truth")]
    DB --> APP
    APP -->|"Optional: populate/update"| C
    APP --> R
~~~

Cache thường được dùng để giảm latency đọc dữ liệu, giảm tải database/API bên ngoài, hấp thụ burst, phục vụ nội dung gần người dùng qua CDN, giảm chi phí gọi dịch vụ hoặc tính toán và cải thiện khả năng phục vụ một số chức năng khi nguồn chậm nếu có chính sách stale/fallback rõ.

Cache không phải nguồn dữ liệu chuẩn cho giao dịch quan trọng trừ khi kiến trúc xác định rõ vai trò và cơ chế bền vững. Mất cache thường phải làm hệ thống có thể lấy lại dữ liệu từ source of truth hoặc tái tạo bản sao.

## 2. Bắt đầu từ access pattern, không bắt đầu từ công nghệ

Cùng một loại dữ liệu có thể phù hợp hoặc không phù hợp để cache tùy cách ứng dụng truy cập. Trước khi chọn cache, thu thập các đặc điểm sau:

| Đặc điểm | Câu hỏi cần trả lời | Ý nghĩa với cache |
|---|---|---|
| Read frequency | Dữ liệu được đọc bao nhiêu lần? | Đọc nhiều có thể tăng giá trị tái sử dụng |
| Write/update frequency | Dữ liệu thay đổi thường xuyên không? | Ghi nhiều làm cache dễ stale và tốn invalidation |
| Read/write ratio | Tỷ lệ đọc so với ghi? | Read-heavy thường dễ hưởng lợi hơn |
| Reuse/popularity | Nhiều request có hỏi cùng key không? | Reuse cao tạo hit tốt hơn |
| Working set | Có bao nhiêu key thường được truy cập? | Quyết định dung lượng cần giữ nóng |
| Entry size | Mỗi entry lớn bao nhiêu? | Ảnh hưởng memory, network và eviction |
| Access locality | Request tập trung theo key, tenant hay region? | Có thể quyết định cache phân tầng/phân vùng |
| Computation cost | Tạo dữ liệu tốn bao nhiêu thời gian/CPU/API call? | Kết quả tính toán đắt có thể đáng cache |
| Freshness requirement | Dữ liệu được phép cũ tối đa bao lâu? | Định hình TTL và invalidation |
| Consistency requirement | Có cần đọc ngay giá trị vừa ghi? | Có thể loại trừ cache hoặc cần thiết kế đặc biệt |
| Lifetime | Dữ liệu có thể tái sử dụng trong bao lâu? | Entry sống quá ngắn có thể không đáng cache |

Một cache key chỉ được tái sử dụng nếu các request thực sự tương đương. Ví dụ nội dung trang phòng có thể phụ thuộc locale, currency, tenant, nhóm quyền hoặc feature flag. Nếu key chỉ là roomId, cache có thể trả bản dịch, giá hoặc dữ liệu không thuộc người dùng đó.

### 2.1. Read-heavy và write-heavy

- **Read-heavy:** cùng dữ liệu được đọc nhiều lần giữa các lần cập nhật; cache có cơ hội giảm số lần gọi nguồn.
- **Write-heavy:** dữ liệu liên tục thay đổi; cache dễ bị invalidation liên tục hoặc trả bản cũ. Lợi ích cần đo kỹ.
- **Mixed workload:** một số trường/endpoint read-heavy, một số khác write-heavy. Có thể cache projection hoặc phần ít thay đổi thay vì toàn record.

Ví dụ:
- Danh mục loại phòng: đọc cao, thay đổi vài lần mỗi ngày — ứng viên tốt.
- Cấu hình hiển thị: đọc nhiều, thay đổi khi admin cập nhật — có thể cache với invalidation.
- Availability theo phút: thay đổi liên tục — TTL ngắn hoặc cache kết quả tổng hợp có timestamp.
- Số dư ví/trạng thái giao dịch: yêu cầu chính xác cao — cân nhắc tránh cache làm nguồn quyết định giao dịch.

## 3. Định lượng giá trị của cache

Không nên cache chỉ vì endpoint có nhiều request. Cần ước lượng lợi ích ở ba mặt: latency, tải nguồn và chi phí.

### 3.1. Cache hit ratio

Tỷ lệ hit đơn giản:

\[
Hit\ Ratio = \frac{Cache\ Hits}{Cache\ Hits + Cache\ Misses}
\]

Nếu có 900 hit và 100 miss trong 1.000 request thì hit ratio là 90%. Tuy nhiên, hit ratio cao không tự chứng minh cache hữu ích:
- Entry có thể rất nhỏ và nguồn vốn đã nhanh.
- Một số hit có thể chứa dữ liệu rẻ để tính lại.
- Cache hit có thể trả dữ liệu stale và gây lỗi nghiệp vụ.
- Hit ratio toàn hệ thống có thể che endpoint quan trọng có tỷ lệ miss cao.

Cần theo dõi hit ratio theo dataset, key namespace, endpoint và thời gian; đồng thời đo latency, tải nguồn và chất lượng dữ liệu.

### 3.2. Ước lượng độ trễ

Giả sử một lần đọc nguồn mất trung bình 80 ms, cache hit mất 4 ms, hit ratio là 90%, bỏ qua overhead khác:

\[
E[T] = 0.9 \times 4 + 0.1 \times 80 = 11.6\ ms
\]

Đây chỉ là ước lượng đơn giản. Trong thực tế cần tính network hop tới distributed cache, serialization/deserialization, kích thước payload, cache contention, queueing, p95/p99 và cold start. Miss path có thể chậm hơn vì ứng dụng phải kiểm tra cache rồi mới đọc nguồn. Nếu nguồn đã trả trong 3 ms còn remote cache mất 5 ms, thêm cache có thể làm chậm đường đọc.

### 3.3. Giảm tải nguồn

Nếu endpoint nhận 10.000 request/giây và hit ratio ổn định 90%, số lần đọc nguồn theo mô hình đơn giản giảm từ 10.000 xuống khoảng 1.000 request/giây. Điều này chỉ đúng nếu mỗi miss tạo một lần đọc nguồn, không có stampede, retry hoặc background refresh tạo tải bổ sung, và key distribution giữ ổn định. Cần đo QPS thực ở nguồn, không chỉ suy ra từ cache metrics.

### 3.4. Chi phí tổng thể

Cache có thể giảm database instance size, compute hoặc API call bên ngoài nhưng phát sinh memory/storage, node/replica, network và cross-zone traffic, request operations, backup/replication, công vận hành và dữ liệu duplicate. So sánh tổng chi phí của request trước/sau: source read, cache read/write, network, compute và vận hành. Cache không phải lúc nào cũng tiết kiệm hơn khi dữ liệu hiếm được đọc hoặc nguồn rất rẻ.

## 4. Dữ liệu nào phù hợp để cache?

Ứng viên tốt thường có một hoặc nhiều đặc điểm:
1. Được đọc lặp lại bởi nhiều request.
2. Chi phí truy vấn, tính toán hoặc gọi API nguồn tương đối cao.
3. Có freshness requirement diễn đạt được thành TTL hoặc invalidation.
4. Có thể tái tạo từ nguồn chuẩn.
5. Bản sao tạm thời không làm sai quyết định nghiệp vụ.
6. Có thể giới hạn key space và dung lượng.

| Loại dữ liệu | Mức phù hợp tham khảo | Vì sao | Điều kiện/rủi ro |
|---|---|---|---|
| Danh mục, loại phòng, tiện ích | Cao | Ít thay đổi, đọc nhiều | Invalidate khi admin cập nhật |
| Nội dung CMS, ảnh, tài nguyên tĩnh | Cao | Có thể version/immutable | CDN và cache-control phù hợp |
| Cấu hình công khai | Cao | Nhiều client đọc cùng giá trị | Version và propagation |
| Kết quả tổng hợp dashboard | Trung bình–cao | Query/aggregation có thể đắt | Timestamp, freshness và quyền |
| Hồ sơ người dùng | Tùy use case | Có thể đọc lặp lại | Tenant/user isolation, expiry |
| Session/token | Cần thiết kế riêng | Truy cập thường xuyên | Thu hồi, expiry và bảo mật |
| Giá/availability | Tùy mức chính xác | Đọc nhiều nhưng thay đổi | TTL ngắn, xác minh trước giao dịch |
| Số dư/trạng thái giao dịch | Thấp cho quyết định ghi | Cần độ chính xác cao | Không dùng stale cache để xác nhận |
| Dữ liệu cá nhân nhạy cảm | Cẩn trọng | Cache giảm tải nhưng tăng bản sao | Encryption, isolation, purge |
| Query ad hoc hiếm gặp | Thường thấp | Ít reuse | Cache churn và memory waste |

Đây không phải phân loại tuyệt đối. Báo cáo tài chính có thể cache để hiển thị dashboard với nhãn “cập nhật lúc 10:05”, nhưng không dùng bản cache đó để quyết định thanh toán hoặc hạch toán.

### 4.1. Cache dữ liệu hay cache kết quả?

- **Cache entity/data:** giữ một record/object theo ID, ví dụ thông tin loại phòng. Dễ tái sử dụng giữa nhiều query nhưng có thể cần ghép dữ liệu.
- **Cache query/result:** giữ kết quả truy vấn hoặc phép tính, ví dụ top 20 phòng được xem nhiều trong tuần. Giảm computation nhưng key phức tạp, cardinality cao và invalidation khó khi nhiều record ảnh hưởng kết quả.

Chọn theo access pattern và phạm vi thay đổi. Không cache tập query tùy ý nếu mỗi key chỉ được dùng một lần.

## 5. Dữ liệu không nên cache hoặc cần giới hạn nghiêm ngặt

Một số trường hợp cache thường không có lợi hoặc rủi ro cao:
- Dữ liệu thay đổi sau gần như mọi request và phải luôn phản ánh trạng thái mới nhất.
- Kết quả có key gần như duy nhất nên hit thấp.
- Payload quá lớn so với dung lượng và giá trị reuse.
- Truy vấn đã rất nhanh, cache thêm network hop gây tốn latency.
- Dữ liệu bí mật nhưng chưa có thiết kế isolation, encryption và purge.
- Kết quả phụ thuộc identity, quyền, tenant hoặc locale nhưng key không mô tả đủ context.
- Cache bị dùng như nguồn dữ liệu duy nhất mà không có durability/recovery.
- Kết quả có thể gây side effect hoặc quyết định giao dịch sai nếu stale.

“Không cache” cũng là một quyết định kiến trúc hợp lệ. Có thể tối ưu query/index, connection pool, pagination, read replica hoặc thuật toán trước khi thêm cache.

## 6. Freshness, TTL và consistency

Cache luôn đặt câu hỏi: **bản sao có thể cũ tới mức nào mà nghiệp vụ vẫn chấp nhận?**

### 6.1. TTL

Time to live (TTL) là thời gian entry được coi là hợp lệ kể từ khi được lưu hoặc làm mới theo semantics hệ thống.

TTL dài có thể tăng hit ratio và giảm tải nguồn nhưng dữ liệu stale lâu hơn. TTL ngắn thường cho dữ liệu mới hơn nhưng tăng miss, tải nguồn và khả năng nhiều entry hết hạn cùng lúc. TTL phải xuất phát từ freshness requirement. Danh mục thay đổi vài giờ một lần có thể chấp nhận TTL vài phút; trạng thái giao dịch có thể cần đọc nguồn hoặc cập nhật/invalidate ngay. Không chọn TTL chỉ vì “5 phút là phổ biến”.

### 6.2. Freshness budget

| Dữ liệu | Freshness budget minh họa | Cách xử lý |
|---|---|---|
| Ảnh/nội dung versioned | Hàng ngày hoặc tới version mới | Cache lâu với key versioned |
| Danh mục tiện ích | Vài phút | TTL + invalidate khi publish |
| Nội dung landing page | 1–5 phút | CDN cache, purge khi publish |
| Kết quả tìm kiếm | Vài giây tới một phút | TTL ngắn hoặc refresh |
| Availability | 0–vài giây tùy nghiệp vụ | Cache rất ngắn; kiểm tra trước booking |
| Payment status | Theo yêu cầu giao dịch | Đọc nguồn authoritative |

Các khoảng thời gian chỉ minh họa. Product owner và hệ thống nghiệp vụ phải xác định mức chấp nhận thực tế.

### 6.3. Cache consistency model

- **Eventual consistency:** cache hội tụ về giá trị mới sau một khoảng thời gian hoặc khi refresh/invalidation thành công.
- **Read-after-write:** sau khi user cập nhật, request đọc tiếp theo cần thấy giá trị vừa ghi.
- **Authoritative read:** cần đọc giá trị có thẩm quyền tại thời điểm quyết định.
- **Stale-while-revalidate:** trả bản cũ trong giới hạn cho phép, đồng thời làm mới ở nền.
- **Stale-if-error:** khi nguồn lỗi, có thể trả bản cũ trong thời hạn dự phòng đã định.

Không có một consistency model đúng cho mọi trường. Trang chi tiết có thể hiển thị nội dung stale vài giây, nhưng khi user xác nhận booking phải kiểm tra availability ở nguồn authoritative.

## 7. Các chiến lược cập nhật cache

### 7.1. Cache-aside (lazy loading)

Ứng dụng kiểm tra cache trước; nếu miss thì đọc nguồn, đưa kết quả vào cache rồi trả về.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant C as Cache
    participant DB as Database
    A->>C: GET key
    alt Cache hit
        C-->>A: Value
    else Cache miss
        C-->>A: Miss
        A->>DB: Read source
        DB-->>A: Value
        A->>C: SET key with TTL
        A-->>A: Return value
    end
~~~

Ưu điểm: chỉ cache dữ liệu thực sự được yêu cầu; đơn giản và dễ triển khai. Đánh đổi: request miss đầu tiên chậm; cần xử lý stampede, stale entries và lỗi ghi cache.

### 7.2. Read-through

Ứng dụng yêu cầu cache đọc key; cache layer tự lấy dữ liệu từ source nếu miss thông qua loader được cấu hình. Cách này tập trung logic loading nhưng phụ thuộc cache client/library và vẫn cần xử lý lỗi, TTL, invalidation.

### 7.3. Write-through

Khi ứng dụng ghi dữ liệu, cache layer cập nhật source và cache theo cùng luồng. Điều này giúp cache có dữ liệu mới sau write nếu thao tác hoàn tất đúng, nhưng có thể tăng write latency và cần xử lý lỗi một phần giữa hai nơi.

### 7.4. Write-behind / write-back

Ứng dụng ghi vào cache trước, cache ghi xuống source bất đồng bộ sau. Có thể tăng tốc ghi nhưng rủi ro lớn hơn: cache mất trước khi flush có thể làm mất dữ liệu; phải bảo đảm durability, retry và ordering; khó đối soát khi write source thất bại. Không phù hợp mặc định cho giao dịch quan trọng nếu chưa có cơ chế bền vững.

| Pattern | Khi nào phù hợp | Rủi ro cần quản lý |
|---|---|---|
| Cache-aside | Read-heavy, muốn kiểm soát trong app | Miss, invalidation, stampede |
| Read-through | Muốn gom loading vào cache layer | Coupling với library/provider |
| Write-through | Cần cập nhật cache ngay sau write | Latency và partial failure |
| Write-behind | Chấp nhận write bất đồng bộ và có durability | Data loss, ordering, reconciliation |

## 8. Chọn vị trí cache theo dữ liệu và mục tiêu

~~~mermaid
flowchart TB
    U["Browser / Mobile"] --> EDGE["Browser cache / CDN / Edge"]
    EDGE --> GW["API gateway / reverse proxy"]
    GW --> APP["Application / in-process cache"]
    APP --> DIST["Distributed cache"]
    DIST --> DB[("Database / source of truth")]
~~~

| Tầng | Ví dụ | Dữ liệu phù hợp | Lưu ý |
|---|---|---|---|
| Browser/client | HTTP cache, local cache | Ảnh, JS/CSS, nội dung public | Cần cache headers và privacy |
| CDN/edge | Static asset, public API response | Nội dung phân phối rộng, ít thay đổi | Invalidation, cache key, geo và authorization |
| Gateway/reverse proxy | GET response, metadata | Endpoint có reuse cao | Vary, auth, cookies, status/error caching |
| In-process | Map/LRU trong JVM | Config nhỏ, immutable, lookup thường xuyên | Mỗi instance có bản sao riêng |
| Distributed cache | Redis/Memcached managed | Session, hot data, query result | Network hop, HA, scaling, eviction |
| Database cache/buffer | Buffer pool, query/page cache | Data pages/index | Do DB engine quản lý; không thay app cache |

### Local cache và distributed cache

**Local/in-process cache** nhanh vì không cần network, phù hợp giá trị nhỏ, đọc nhiều và có thể chấp nhận mỗi instance cập nhật khác thời điểm. Nhưng 10 instance có thể có 10 bản sao; invalidation cần broadcast/version hoặc TTL ngắn.

**Distributed cache** chia sẻ bản cache giữa nhiều instance, giảm dữ liệu trùng trên mỗi process. Đổi lại, mỗi lần đọc qua network; cache cluster có thể trở thành dependency và cần HA, scaling, failover và monitoring.

Hệ thống có thể dùng cả hai: local cache TTL rất ngắn trước distributed cache, nhưng cần quy tắc version/invalidation để không tạo nhiều lớp stale.

## 9. HTTP cache, CDN và Cache-Control

Đối với HTTP, response headers hướng dẫn browser và intermediary cache cách lưu và tái sử dụng response.

Các chỉ thị thường gặp:
- public: response có thể được shared cache lưu theo policy.
- private: chỉ private cache (ví dụ browser của user) được lưu.
- no-store: không lưu response theo chỉ thị này.
- no-cache: có thể lưu nhưng phải revalidate trước khi sử dụng lại.
- max-age: tuổi tối đa theo giây đối với cache phù hợp.
- s-maxage: max age dành cho shared cache.
- must-revalidate: cache phải revalidate khi stale theo semantics HTTP.
- stale-while-revalidate: cho phép trả stale trong khoảng quy định nếu cache hỗ trợ.

Ví dụ asset immutable có thể dùng:

~~~http
Cache-Control: public, max-age=31536000, immutable
~~~

Phù hợp khi URL chứa content hash/version và nội dung không thay đổi tại cùng URL. Khi phát hành nội dung mới, tạo URL mới.

Response user-specific cần thận trọng:

~~~http
Cache-Control: private, max-age=60
Vary: Accept-Language
~~~

Nếu response phụ thuộc cookie, Authorization, tenant hoặc role, phải xem shared cache có được phép lưu không và cache key có phân biệt đủ không. Không dùng public cho dữ liệu nhạy cảm chỉ để tăng hit ratio.

### Cache key và Vary

Cache phải phân biệt request có thể tạo ra response khác nhau. Các chiều thường gặp: path/query, Accept/Accept-Language, cookie/session, tenant, authorization role/scope, feature flag, locale và currency.

Nếu thiếu một chiều, cache có thể trả response của user/tenant này cho user/tenant khác. Nếu đưa quá nhiều chiều vào key, cardinality tăng và hit ratio giảm. Thiết kế key ảnh hưởng cả correctness lẫn security.

## 10. Cache dữ liệu trong hệ thống Booking

Không phải mọi trường của một màn hình nên có cùng policy.

| Thành phần trang phòng | Access pattern | Mục tiêu | Quyết định cache minh họa |
|---|---|---|---|
| Ảnh phòng | Nhiều lượt đọc, ít thay đổi | Giảm latency/origin traffic | CDN/browser cache dài, URL versioned |
| Mô tả/tiện ích | Đọc nhiều, admin cập nhật ít | Giảm query | Cache-aside vài phút, invalidate khi publish |
| Chính sách hủy | Đọc nhiều, thay đổi theo version | Nhất quán nội dung đã công bố | Cache theo policy version |
| Giá niêm yết | Đọc nhiều, thay đổi theo lịch/khuyến mại | Giảm query | Cache ngắn, key theo currency/tenant/segment |
| Availability | Thay đổi theo booking/cancel | Tránh overbooking | Cache rất ngắn; xác minh atomic trước booking |
| Payment status | Phụ thuộc giao dịch | Trạng thái authoritative | Đọc nguồn chuẩn hoặc cơ chế nhất quán |
| Báo cáo tìm kiếm | Query aggregation đắt | Giảm compute/database | Cache theo query key, TTL và timestamp |
| Hồ sơ cá nhân | User-specific, thay đổi theo profile | Giảm truy vấn lặp | Key theo user/tenant; invalidation sau update |

Có thể cache mô tả phòng 5 phút, nhưng khi người dùng bấm xác nhận booking, backend phải kiểm tra availability và giá có thẩm quyền trong transaction hoặc cơ chế reservation. Một màn hình có thể phối hợp nhiều nguồn có freshness khác nhau; UI nên thể hiện khi dữ liệu chỉ mang tính tham khảo.

## 11. Cache stampede, hot key và eviction

### 11.1. Cache stampede

Khi một key phổ biến hết hạn, nhiều request cùng miss và đồng thời gọi database. Điều này có thể gây tải đột biến.

Giải pháp:
- **Single-flight/request coalescing:** một request làm mới key; request khác chờ kết quả.
- **TTL jitter:** phân tán thời điểm hết hạn.
- **Refresh-ahead:** làm mới trước khi entry hết hạn.
- **Stale-while-revalidate:** trả stale trong ngân sách cho phép và làm mới nền.
- **Lock có giới hạn:** một worker refresh; phải xử lý lock timeout và worker bị chết.

Không dùng stale cho dữ liệu mà stale có thể gây tác động nghiệp vụ nghiêm trọng.

### 11.2. Hot key

Một key rất phổ biến có thể làm một node/partition cache chịu tải vượt trội. Cần quan sát request rate theo key/shard, cân nhắc local cache, replication/read scaling, key sharding hoặc precompute. Chia key máy móc có thể làm phức tạp invalidation.

### 11.3. Eviction policy

Khi hết memory, cache chọn entry để loại bỏ:
- **LRU:** loại entry ít được truy cập gần đây.
- **LFU:** ưu tiên giữ entry được truy cập thường xuyên.
- **TTL-based expiration:** xóa entry hết hạn.
- **Random/segmented policies:** theo cách triển khai và mục tiêu sản phẩm.

Không có policy chung tối ưu. LRU phù hợp khi locality thời gian tốt; LFU giữ dữ liệu phổ biến dài hạn nhưng có thể phản ứng chậm với xu hướng. Theo dõi eviction rate, memory fragmentation và hit ratio.

## 12. Bảo mật và quyền riêng tư khi cache

Cache tạo thêm bản sao dữ liệu. Cần trả lời: data classification nào được phép vào cache? Cache key có chứa token/email không? Dữ liệu được tách theo user/tenant? Cache cluster và network có encryption/authentication? Ai đọc keyspace hoặc export snapshot? TTL và purge có đáp ứng retention/deletion policy? Backup/replica có giữ dữ liệu sau khi xóa ở nguồn?

Nguyên tắc:
- Không cache credential dài hạn hoặc secret tùy tiện; dùng secret manager cho vòng đời secret.
- Tránh cache response nhạy cảm trong shared cache nếu chưa thiết kế authorization và key isolation.
- Mã hóa in transit/at rest theo yêu cầu; quản lý access control và network boundary.
- Hạn chế lưu payload đầy đủ; có thể cache projection tối thiểu.
- Có cơ chế purge theo user/tenant khi cần xóa dữ liệu.
- Không ghi cache value vào log; chỉ ghi key namespace đã chuẩn hóa, TTL, hit/miss và latency.
- Quản lý memory dump, snapshot, backup và replication như các bản sao dữ liệu.

Một cache private vẫn cần authorization. Chỉ nằm trong subnet nội bộ không có nghĩa mọi workload trong subnet đều nên đọc mọi key.

## 13. Cache failure và khả năng phục hồi

Cache nên được thiết kế như một thành phần có thể lỗi. Cần quyết định cách xử lý từng loại request:

- **Fail open:** bỏ qua cache và đọc nguồn.
- **Fail closed:** từ chối hoặc degrade chức năng khi không thể bảo đảm policy/dữ liệu.
- **Serve stale:** trả bản cache cuối cùng trong giới hạn.
- **Fallback:** dùng nguồn thay thế hoặc giá trị default an toàn.

Nếu cache danh mục loại phòng ngừng hoạt động, ứng dụng có thể đọc database và chậm hơn. Nếu cache session/authentication chứa trạng thái thu hồi quyền, bỏ qua cache có thể khiến quyết định bảo mật sai; cần lựa chọn consistency và fail mode riêng.

Không phải lúc nào cũng nên fail open. Nếu mọi request miss đồng loạt đổ về database, cache outage có thể gây database outage tiếp theo. Cần giới hạn concurrency/connection tới source, circuit breaker, load shedding, serve stale trong phạm vi cho phép, warm-up dần và thử failover.

## 14. Những chỉ số cần theo dõi

| Metric | Ý nghĩa | Cách diễn giải |
|---|---|---|
| Hit ratio | Tỷ lệ request được phục vụ từ cache | Theo dataset/endpoint, không chỉ tổng |
| Miss rate | Request phải đi nguồn | Miss spike có thể do flush, TTL hoặc traffic mới |
| Hit/miss latency | Thời gian phục vụ mỗi loại | So sánh p50/p95/p99, gồm network overhead |
| Eviction rate | Entry bị loại do memory/policy | Cao có thể báo working set quá lớn |
| Memory utilization | Mức dùng memory | Theo dõi headroom và fragmentation |
| Key cardinality | Số key khác nhau | Tăng đột biến làm hit thấp và memory cao |
| Hot key distribution | Tải tập trung theo key | Tìm hotspot/shard overload |
| Backend fallback QPS | Request đọc nguồn sau miss/failure | Đánh giá giảm tải thực tế |
| Stale response rate | Response dùng dữ liệu cũ theo policy | So với freshness budget |
| Refresh/invalidation failure | Làm mới hoặc xóa cache thất bại | Nguy cơ stale lâu |
| Cache availability | Health/error/timeout | Đánh giá tác động dependency |
| Cost per hit/saved read | Chi phí cache so với nguồn tránh được | Hỗ trợ quyết định tiếp tục hay bỏ |

Hit ratio cao không phải mục tiêu độc lập. Nếu cache hit 99% nhưng 1% miss làm database quá tải, hoặc cache trả dữ liệu stale gây overbooking, thiết kế vẫn thất bại. Mục tiêu kinh doanh là latency, availability, throughput, correctness và cost ở mức yêu cầu.

## 15. Quy trình xác định dữ liệu có nên cache

Một quy trình quyết định có thể dùng trong design review:

1. **Xác định source of truth:** Dữ liệu chuẩn nằm ở database, service hay object storage nào?
2. **Đo access pattern:** Read/write ratio, QPS, popularity, working set, key cardinality và payload size.
3. **Đo baseline:** Latency p50/p95/p99, source QPS, CPU, IO, API cost và lỗi.
4. **Xác định freshness/consistency:** Dữ liệu cũ tối đa bao lâu? Sau write có cần read-after-write? Có được serve stale khi lỗi?
5. **Ước lượng lợi ích:** Hit ratio tiềm năng, nguồn giảm tải, latency tiết kiệm và cost tránh được.
6. **Chọn tầng và pattern:** Browser/CDN, gateway, in-process, distributed cache; cache-aside, read-through hoặc write-through.
7. **Thiết kế key và isolation:** Bao gồm mọi chiều làm response thay đổi; tránh cross-user/tenant leak.
8. **Thiết kế TTL/invalidation:** Nguồn nào phát sự kiện update? Nếu invalidation lỗi thì giới hạn stale thế nào?
9. **Thiết kế cache miss/failure:** Load control, fallback, stampede protection, warm-up và recovery.
10. **Thử nghiệm có đo lường:** So sánh có/không cache bằng A/B hoặc load test có kiểm soát.
11. **Quyết định tiếp tục hay loại bỏ:** Cache chỉ tồn tại nếu lợi ích đo được lớn hơn chi phí và rủi ro.

### Checklist quyết định nhanh

| Câu hỏi | Nếu câu trả lời là “không” |
|---|---|
| Có reuse đủ nhiều cùng dữ liệu/key? | Không cache hoặc tìm tập dữ liệu nóng hơn |
| Nguồn đủ chậm/đắt để cần cache? | Tối ưu nguồn trước |
| Có freshness budget cụ thể? | Không cache luồng cần authoritative read |
| Có key và phân quyền an toàn? | Thiết kế lại identity/key isolation |
| Có cách cập nhật, hết hạn hoặc invalidation? | Chưa đưa cache vào production |
| Cache mất thì source/fallback chịu được? | Thêm load shedding, stale policy hoặc capacity |
| Lợi ích đo được vượt cost vận hành? | Không cache |

## 16. Đánh giá theo Well-Architected

| Khía cạnh | Câu hỏi review | Bằng chứng |
|---|---|---|
| **Vận hành xuất sắc** | Ai sở hữu TTL, key schema, invalidation và cleanup? | Runbook, config version, cache dashboard |
| **Bảo mật** | User/tenant có thể đọc nhầm dữ liệu? Cache có lưu secret/PII? | Threat model, IAM review, negative tests |
| **Độ tin cậy** | Cache outage/stampede có làm sập source? Stale được phép bao lâu? | Failure injection, circuit breaker, fallback test |
| **Hiệu quả hiệu năng** | Hit latency có tốt hơn miss path? Có hot key hoặc eviction? | p95/p99, hit ratio theo dataset, load test |
| **Tối ưu chi phí** | Cache tiết kiệm nguồn nhiều hơn chi phí cluster/network/ops? | Cost model, saved source QPS, memory |
| **Bền vững** | Có giữ bản sao quá lớn hoặc cache dữ liệu hiếm dùng? | Working-set analysis, TTL/eviction review |

### ADR minh họa — Cache danh mục phòng

> **Bối cảnh:** Endpoint danh mục phòng nhận lượng đọc cao. Truy vấn database mất trung bình 70 ms; nội dung chỉ thay đổi khi admin publish.
>
> **Phương án A:** Giữ đọc database. Ít thành phần và lấy trạng thái từ nguồn, nhưng query lặp gây tải và latency.
>
> **Phương án B:** Cache-aside tại distributed cache với TTL ngắn và invalidation khi publish.
>
> **Quyết định minh họa:** Chọn B nếu load test chứng minh giảm latency/source QPS và có owner cho invalidation.
>
> **Key:** tenant + locale + catalogVersion.
>
> **Freshness:** Chấp nhận một khoảng stale đã được product owner duyệt; publish event invalidate key liên quan.
>
> **Failure behavior:** Cache lỗi thì fallback database có concurrency limit; nếu DB tải cao thì dùng stale catalog trong giới hạn.
>
> **Kiểm chứng:** So sánh p95, hit ratio, database QPS, stale age, invalidation delay, tenant isolation và cache outage.
>
> **Điều kiện xem xét lại:** Catalog ít được đọc, query được tối ưu đáng kể hoặc chi phí cache vượt lợi ích.

## 17. Bài tập thực hành: chọn dữ liệu để cache cho Booking API

Booking API có các endpoint:
- GET /rooms: danh mục phòng và tiện ích.
- GET /rooms/{id}: mô tả, ảnh, giá tham khảo và availability.
- POST /bookings: tạo booking sau khi kiểm tra chỗ trống và giá.
- GET /bookings/{id}/status: trạng thái booking/payment.
- GET /reports/popular-rooms: truy vấn tổng hợp 30 ngày.

Nhóm cân nhắc thêm distributed cache dùng chung và dự kiến đặt TTL 30 phút cho mọi key để đạt hit ratio cao.

**Yêu cầu:**
1. Phân loại dữ liệu theo read/write ratio, reuse, cost và freshness.
2. Xác định trường nào nên cache dài, ngắn hoặc không cache.
3. Đề xuất cache key cho danh mục theo tenant/locale và dữ liệu cá nhân.
4. Nêu cách xử lý khi admin cập nhật danh mục.
5. Giải thích vì sao availability phải được xác minh lại khi tạo booking.
6. Thiết kế cache failure behavior để không làm database quá tải.
7. Chọn metric và mục tiêu đo trước/sau triển khai.
8. Đưa ra tiêu chí quyết định loại cache nếu lợi ích không đủ.

### Hướng giải quyết

- Danh mục và mô tả/ảnh có read reuse cao, ít thay đổi nên phù hợp cache; ảnh/tài nguyên tĩnh có thể dùng CDN với URL versioned.
- Giá tham khảo có thể cache ngắn và phải phân biệt currency, tenant, thời điểm/segment nếu các yếu tố này ảnh hưởng giá.
- Availability thay đổi liên tục; không dùng cached value để xác nhận giữ chỗ. POST booking phải kiểm tra authoritative và thực hiện reservation/transaction nguyên tử.
- Booking/payment status cần freshness phù hợp; nếu cache chỉ phục vụ UI, trả updatedAt và refresh ngắn. Luồng nhạy cảm phải đọc nguồn authoritative.
- Report popular rooms có aggregation đắt và cập nhật theo lô có thể cache theo query parameters, time window và tenant.
- Invalidation danh mục có thể phát event sau publish; TTL là lớp bảo vệ nếu event mất. Có version key để tránh phụ thuộc xóa đồng bộ mọi entry.
- Khi cache lỗi, giới hạn fallback QPS/concurrency, circuit breaker, stale catalog trong ngân sách và warm-up dần.
- So sánh p95/p99 latency, database QPS/CPU, cache hit theo endpoint, stale age, invalidation delay, memory/cost và error rate.
- Chỉ giữ cache nếu đạt mục tiêu hiệu năng/chi phí mà không vượt freshness/security budget; nếu nguồn đã đủ nhanh, bỏ cache để giảm độ phức tạp.

### Câu hỏi tự kiểm tra

1. Vì sao read-heavy là dấu hiệu tốt nhưng chưa đủ để quyết định cache?
2. Hit ratio cao có thể che giấu vấn đề nào?
3. TTL khác invalidation như thế nào?
4. Khi nào dùng in-process cache, distributed cache hay CDN?
5. Vì sao cùng một roomId có thể chưa đủ làm cache key?
6. Cache-aside xử lý cache miss thế nào và có rủi ro gì khi nhiều request miss cùng lúc?
7. Vì sao stale-while-revalidate không phù hợp cho mọi dữ liệu?
8. Cache outage có thể tạo database outage thứ cấp ra sao?
9. ETag, Cache-Control và Vary giúp HTTP cache hoạt động thế nào?
10. Những phép đo nào chứng minh cache tiết kiệm chi phí và cải thiện trải nghiệm?

Một quyết định cache tốt bắt đầu bằng **dữ liệu được tái sử dụng, nguồn đang tốn chi phí hoặc độ trễ đáng kể, và freshness budget nghiệp vụ có thể chấp nhận**. Chọn đúng key, tầng cache, TTL, invalidation và failure behavior quan trọng hơn việc tối đa hóa hit ratio. Cache chỉ nên được giữ lại khi phép đo cho thấy lợi ích rõ ràng và hệ thống vẫn đúng, an toàn, có thể phục hồi khi bản sao biến mất hoặc trở nên cũ.
