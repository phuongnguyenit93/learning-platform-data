# Bộ đệm ứng dụng: tỷ lệ trúng, vô hiệu hóa và độ tươi dữ liệu

Bộ đệm ứng dụng giữ bản sao dữ liệu ở gần nơi xử lý request để giảm thời gian truy cập và số lần đọc từ cơ sở dữ liệu. Khi dữ liệu phù hợp đã có trong cache, ứng dụng có thể trả lời nhanh mà không phải thực hiện lại toàn bộ truy vấn. Nhưng cache chỉ cải thiện hệ thống khi dữ liệu được lưu đúng khóa, được làm mới đúng lúc và được vô hiệu hóa khi nguồn dữ liệu thay đổi. Một cache có tỷ lệ trúng cao nhưng chứa dữ liệu cũ, trộn dữ liệu giữa tenant hoặc tạo tải đột biến khi hết hạn vẫn có thể gây sự cố nghiêm trọng.

Trong module **DATABASE_PERFORMANCE**, tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Chương **Mở rộng hệ thống** xem xét cách phân phối tải và giảm áp lực lên nguồn dữ liệu khi số lượng request tăng. Bài học này tập trung vào bộ đệm ứng dụng: cách tính tỷ lệ trúng, lựa chọn chính sách đọc/ghi, thiết kế cache key, kiểm soát TTL, vô hiệu hóa dữ liệu, đánh giá độ tươi và duy trì hành vi ổn định khi cache hoặc cơ sở dữ liệu gặp sự cố.

Sau bài học, người học có thể:

- Giải thích vai trò của cache trong đường đi của request và phân biệt cache ứng dụng với buffer cache của DBMS.
- Tính request hit ratio, miss ratio, byte hit ratio và đánh giá giới hạn của từng chỉ số.
- Chọn cache-aside, read-through, write-through, write-behind hoặc refresh-ahead theo yêu cầu.
- Thiết kế cache key bao gồm tenant, quyền truy cập, phiên bản và các tham số ảnh hưởng kết quả.
- Chọn TTL và chiến lược hết hạn phù hợp với mức độ thay đổi của dữ liệu.
- Phân biệt invalidation, refresh và eviction; nhận diện race condition khi cập nhật dữ liệu.
- Xác định freshness SLO, độ trễ lan truyền và mức staleness có thể chấp nhận.
- Phòng tránh cache stampede, cache penetration và cache avalanche.
- Đo hiệu quả cache cùng latency, tải DB, chi phí mạng và độ chính xác dữ liệu.
- Thiết kế fallback và kiểm thử khi cache hoặc hệ thống phát sự kiện invalidation bị gián đoạn.

## 1. Cache nằm ở đâu trong đường đi của request?

### 1.1. Mục tiêu của cache ứng dụng

Khi ứng dụng nhận request, dữ liệu có thể được lấy từ nhiều tầng:

1. Cache cục bộ trong process ứng dụng.
2. Cache phân tán dùng chung giữa nhiều instance.
3. Cơ sở dữ liệu hoặc dịch vụ nguồn.
4. Các dịch vụ phụ trợ cần thiết để tạo kết quả.

Cache giữ bản sao của một giá trị đã được tính hoặc đọc trước đó. Nếu bản sao còn hợp lệ, ứng dụng dùng lại nó. Việc này có thể giảm:

- Số query gửi đến DBMS.
- Số lần đọc index và trang dữ liệu.
- Network round trip giữa ứng dụng và DBMS.
- CPU dành cho join, aggregate hoặc tính toán lặp lại.
- Latency của request thường xuyên đọc cùng một dữ liệu.

Cache không làm cho truy vấn nguồn nhanh hơn. Nó giảm số lần truy vấn nguồn được thực hiện. Khi miss, cache vẫn phải lấy dữ liệu từ nguồn và có thể còn thêm chi phí ghi cache.

### 1.2. Cache ứng dụng khác buffer cache của DBMS

DBMS có buffer pool hoặc buffer cache để giữ trang dữ liệu và index đã đọc từ storage. Cache ứng dụng thường giữ giá trị ở mức nghiệp vụ hoặc kết quả đã được chuyển đổi cho ứng dụng.

Ví dụ:

- DBMS buffer cache giữ trang của bảng customer.
- Cache ứng dụng giữ hồ sơ khách hàng theo customer ID.
- Cache ứng dụng có thể giữ danh sách sản phẩm theo danh mục.
- Cache ứng dụng có thể giữ kết quả tổng hợp đã tính theo tenant và khoảng thời gian.

Hai tầng có mục đích và cơ chế nhất quán khác nhau. DBMS quản lý trang theo cơ chế storage engine; ứng dụng chịu trách nhiệm xác định key, TTL, invalidation và quyền sử dụng giá trị nghiệp vụ.

### 1.3. L1 cache và L2 cache

Một hệ thống có thể dùng nhiều tầng:

- **L1:** cache cục bộ trong từng process, thường có latency thấp nhưng mỗi instance có bản sao riêng.
- **L2:** cache phân tán dùng chung, ví dụ Redis hoặc Memcached, chia sẻ giữa nhiều instance.
- **Source:** DBMS hoặc dịch vụ nguồn có dữ liệu chuẩn.

Đường đọc có thể là:

~~~text
Request
   |
   v
L1 local cache
   | hit
   +----------------------> Return value
   |
   | miss
   v
L2 distributed cache
   | hit
   +----------------------> Fill L1 -> Return value
   |
   | miss
   v
Database / source service
   |
   +----------------------> Fill L2 -> Fill L1 -> Return value
~~~

L1 giảm network call đến L2 nhưng có thể giữ dữ liệu cũ sau khi L2 đã được cập nhật. Nếu có nhiều instance, invalidation cần truyền đến tất cả L1 hoặc L1 phải có TTL rất ngắn. Một cách khác là đưa version vào key để bản sao cũ tự trở nên không còn được tham chiếu.

### 1.4. Cache không phải nguồn dữ liệu chuẩn

Trong phần lớn hệ thống nghiệp vụ, DBMS hoặc dịch vụ nguồn vẫn là nơi lưu dữ liệu chuẩn. Cache là bản sao có thể bị xóa, hết hạn hoặc mất khi restart.

Ứng dụng cần có đường xử lý khi:

- Key chưa có.
- Key đã hết hạn.
- Cache node không khả dụng.
- Giá trị cache không đọc được hoặc không giải mã được.
- Cache trả về version cũ.
- Invalidation event bị chậm hoặc thất lạc.

Không nên phụ thuộc vào cache để bảo đảm dữ liệu đã được ghi bền vững. Nếu nghiệp vụ yêu cầu durability, phải xác nhận commit tại nguồn.

## 2. Hit, miss và cách tính tỷ lệ trúng

### 2.1. Request hit ratio

Một cache hit xảy ra khi yêu cầu một key và nhận được giá trị hợp lệ từ cache. Cache miss xảy ra khi key không tồn tại, đã hết hạn, bị evict hoặc không thể sử dụng.

Request hit ratio:

\[
HitRatio = \frac{Hits}{Hits + Misses}
\]

Miss ratio:

\[
MissRatio = 1 - HitRatio
\]

Ví dụ, trong một phút cache nhận 100.000 lượt đọc; 92.000 lượt hit và 8.000 lượt miss:

\[
HitRatio = \frac{92.000}{100.000} = 92\%
\]

Chỉ số này dễ theo dõi và hữu ích khi mỗi request có chi phí tương đương. Tuy nhiên, 92% hit không tự động có nghĩa cache đã giảm 92% tải DB.

### 2.2. Request hit ratio có thể che giấu chi phí thật

Giả sử 90.000 request hit chỉ đọc một cấu hình nhỏ, trong khi 10.000 request miss đọc một tập dữ liệu lớn và chạy join nặng. Hit ratio 90% nhưng DBMS vẫn có thể chịu phần lớn CPU và I/O.

Ngược lại, một cache có hit ratio 60% vẫn có thể giảm đáng kể tải nếu các hit tránh được truy vấn rất đắt.

Do đó, hãy theo dõi thêm:

- CPU và elapsed time của các query được cache thay thế.
- Logical reads và physical reads tránh được.
- Số byte đọc từ DBMS.
- Số request và concurrency ở nguồn.
- Latency p50, p95 và p99.
- Chi phí thao tác cache, serialization và mạng.

### 2.3. Byte hit ratio

Với dữ liệu có kích thước rất khác nhau, có thể tính tỷ lệ theo byte:

\[
ByteHitRatio =
\frac{BytesServedFromCache}
{BytesServedFromCache + BytesFetchedFromSource}
\]

Ví dụ, cache hit 80% số request nhưng những request miss chứa payload lớn. Byte hit ratio có thể chỉ 35%. Điều này cho thấy cache tránh được nhiều lượt đọc nhỏ nhưng vẫn truyền phần lớn dữ liệu từ nguồn.

Cần định nghĩa rõ byte đang đo ở tầng nào: kích thước object, payload sau serialization hay byte truyền qua mạng. Không trộn các đơn vị khác nhau vào cùng một phép tính.

### 2.4. Origin offload và cache effectiveness

Một chỉ số vận hành hữu ích là mức giảm tải nguồn:

\[
OriginOffload =
1 - \frac{OriginRequestsWithCache}
{OriginRequestsWithoutCache}
\]

Để tính đúng, cần một baseline hoặc mô hình phản thực tế đáng tin cậy. Trong thực tế, có thể so sánh số query nguồn trước/sau thay đổi dưới workload tương đương, hoặc đo số request được cache phục vụ mà không gọi nguồn.

Cache effectiveness nên phản ánh kết quả hệ thống:

- DBMS giảm bao nhiêu CPU, I/O và query executions?
- Latency người dùng giảm bao nhiêu?
- Cache thêm bao nhiêu network và memory cost?
- Tỷ lệ dữ liệu cũ hoặc sai có tăng không?
- Khi cache down, nguồn có chịu được tải fallback không?

### 2.5. Đo theo keyspace và nhóm workload

Một tỷ lệ tổng hợp có thể che giấu key nóng hoặc nhóm dữ liệu ít hiệu quả. Nên phân loại theo:

- Nhóm API hoặc query fingerprint.
- Tenant hoặc loại khách hàng nếu chính sách cho phép.
- Loại dữ liệu: cấu hình, hồ sơ, danh mục, kết quả tổng hợp.
- Kích thước payload.
- TTL class.
- Cache tier L1/L2.
- Kết quả hit, miss, expired, evicted và error.

Không đưa ID cá nhân hoặc dữ liệu nhạy cảm vào metric label có cardinality cao. Dùng nhóm phân loại và sampling để tránh làm hệ thống giám sát quá tải.

## 3. Các chính sách đọc và ghi phổ biến

### 3.1. Cache-aside (lazy loading)

Trong cache-aside, ứng dụng chủ động kiểm tra cache. Khi miss, ứng dụng đọc nguồn rồi ghi kết quả vào cache:

~~~text
1. GET key từ cache
2. Nếu hit: trả giá trị
3. Nếu miss:
   a. Đọc DBMS hoặc nguồn chuẩn
   b. Ghi giá trị vào cache với TTL
   c. Trả giá trị
~~~

Ví dụ pseudocode:

~~~java
CustomerProfile getCustomer(long customerId) {
    String key = "customer-profile:" + customerId;

    CustomerProfile cached = cache.get(key);
    if (cached != null) {
        return cached;
    }

    CustomerProfile loaded = repository.findProfile(customerId);
    if (loaded != null) {
        cache.set(key, loaded, ttl);
    }
    return loaded;
}
~~~

Ưu điểm:

- Chỉ cache dữ liệu thực sự được yêu cầu.
- Dễ triển khai và dễ quan sát.
- Cache có thể mất mà ứng dụng vẫn đọc được nguồn.

Nhược điểm:

- Miss làm tăng latency vì phải đọc nguồn rồi ghi cache.
- Nhiều request cùng miss một key có thể cùng truy vấn nguồn.
- Dữ liệu có thể cũ nếu invalidation không đúng.
- Cache không được làm nóng trước khi có traffic.

### 3.2. Read-through

Với read-through, ứng dụng gọi cache như nơi đọc dữ liệu; cache layer tự gọi loader khi key miss. Loader chịu trách nhiệm đọc nguồn và điền cache.

Mô hình này tách logic cache khỏi code nghiệp vụ, nhưng cần hiểu rõ cách cache layer xử lý concurrency, timeout, exception, TTL và lỗi nguồn. Một số thư viện local cache hỗ trợ loader; một số hệ thống phân tán cần triển khai service wrapper.

### 3.3. Write-through

Với write-through, thao tác ghi đi qua cache layer và cập nhật nguồn cùng cache theo quy trình của cơ chế đó.

Lợi ích là dữ liệu cache được cập nhật ngay trong luồng ghi nếu thao tác hoàn tất. Nhưng không phải mọi implementation đều có transaction nguyên tử giữa cache và DBMS. Nếu DB commit thành công nhưng cache update thất bại, hoặc ngược lại, hệ thống vẫn có thể lệch trạng thái.

Cần định nghĩa thứ tự ghi, retry và cơ chế phục hồi. Không mô tả write-through như một distributed transaction nếu không thực sự có giao thức bảo đảm điều đó.

### 3.4. Write-behind hoặc write-back

Với write-behind, ứng dụng ghi vào cache trước, rồi cache hoặc worker ghi thay đổi xuống nguồn sau. Cách này có thể gộp nhiều lần ghi và giảm tải DBMS, nhưng cache trở thành nơi giữ thay đổi chưa được commit vào nguồn.

Rủi ro:

- Cache node hỏng trước khi flush.
- Worker ghi nguồn bị chậm hoặc thất bại.
- Thay đổi bị ghi sai thứ tự.
- Retry gây ghi lặp nếu thao tác không idempotent.
- Người đọc nguồn trực tiếp thấy giá trị cũ.
- Khó bảo đảm durability và read-your-writes.

Chỉ dùng khi nghiệp vụ chấp nhận độ trễ ghi và có durable queue/log, retry, deduplication, ordering và quy trình phục hồi rõ ràng. Không dùng write-behind cho dữ liệu tài chính hoặc trạng thái quan trọng chỉ vì muốn giảm query.

### 3.5. Refresh-ahead

Refresh-ahead làm mới key trước khi hết hạn hoặc trước khi có request tiếp theo, dựa trên tần suất truy cập và chi phí tải nguồn. Nó có thể giảm miss latency cho key nóng.

Cần giới hạn refresh concurrency. Nếu làm mới mọi key cùng lúc hoặc refresh các key không còn được dùng, nguồn và cache có thể chịu tải không cần thiết. Refresh nên dùng version hoặc compare-and-set để không ghi đè dữ liệu mới hơn bằng kết quả cũ.

### 3.6. So sánh chính sách

| Chính sách | Khi đọc | Khi ghi | Điểm cần chú ý |
|---|---|---|---|
| Cache-aside | Ứng dụng kiểm tra cache rồi đọc nguồn khi miss | Ứng dụng cập nhật nguồn và invalidation/cache | Đơn giản, cần xử lý race và stampede |
| Read-through | Cache gọi loader khi miss | Theo cơ chế riêng | Tách loader, cần kiểm soát concurrency |
| Write-through | Đọc từ cache | Cập nhật cache và nguồn theo một luồng | Phải hiểu tính nguyên tử và lỗi một phần |
| Write-behind | Đọc từ cache | Ghi cache trước, flush nguồn sau | Durability, ordering và retry phức tạp |
| Refresh-ahead | Đọc cache | Làm mới trước khi hết hạn | Tránh refresh thừa và ghi đè version mới |

## 4. Thiết kế cache key đúng và an toàn

### 4.1. Key phải đại diện cho mọi đầu vào ảnh hưởng kết quả

Cache key cần bao gồm các tham số làm thay đổi giá trị được trả về. Ví dụ, một danh sách sản phẩm có thể phụ thuộc:

- Tenant.
- Người dùng hoặc nhóm quyền.
- Ngôn ngữ.
- Đơn vị tiền tệ.
- Bộ lọc.
- Thứ tự sắp xếp.
- Trang hoặc cursor.
- Phiên bản schema hoặc thuật toán tính.
- Trạng thái feature flag.

Nếu bỏ một chiều, ứng dụng có thể trả dữ liệu của tenant khác, dùng sai ngôn ngữ hoặc trả kết quả chưa được lọc theo quyền.

Ví dụ key:

~~~text
product-list:v3:tenant-42:locale-vi-VN:currency-VND:category-8:sort-price-asc:page-1
~~~

Key thực tế nên được chuẩn hóa, có giới hạn chiều dài và tránh đưa dữ liệu nhạy cảm trực tiếp vào tên key.

### 4.2. Quyền truy cập phải được tính vào cache boundary

Nếu kết quả phụ thuộc quyền của người dùng, có hai cách thường gặp:

- Cache dữ liệu nền không phụ thuộc quyền, sau đó áp dụng authorization ở mỗi request.
- Cache kết quả đã lọc quyền với key chứa security scope hoặc permission version.

Không dùng cùng key cho hai người dùng có quyền khác nhau nếu giá trị đã được lọc theo quyền. Không coi cache hit là bằng chứng người dùng được phép đọc dữ liệu; authorization vẫn phải được thực hiện theo mô hình bảo mật của ứng dụng.

### 4.3. Chuẩn hóa key và tham số

Các tham số tương đương cần tạo key ổn định. Ví dụ, hai filter giống nhau nhưng thứ tự tham số khác có thể tạo hai key khác nhau nếu serialize trực tiếp một map không có thứ tự.

Nên:

- Chuẩn hóa thứ tự tham số.
- Chuẩn hóa timezone và định dạng ngày.
- Chuẩn hóa chữ hoa/chữ thường nếu semantics không phân biệt.
- Phân biệt giá trị null, rỗng và không được truyền.
- Bao gồm version của cấu trúc key.
- Hash phần tham số dài nhưng giữ metadata cần thiết để chẩn đoán.

### 4.4. Cardinality và cache pollution

Một endpoint có hàng triệu giá trị filter khác nhau có thể tạo keyspace khổng lồ. Nếu mỗi key chỉ được dùng một lần, cache giữ dữ liệu ít giá trị và đẩy key nóng ra ngoài.

Cần kiểm tra:

- Số key duy nhất mỗi giờ.
- Tần suất truy cập theo key.
- Tỷ lệ key chỉ được dùng một lần.
- Kích thước object.
- Eviction rate.
- Memory fragmentation hoặc overhead metadata.

Không cache mọi kết quả truy vấn một cách tự động. Chọn nhóm dữ liệu có tính tái sử dụng và chi phí nguồn đủ cao.

## 5. TTL, hết hạn và độ tươi dữ liệu

### 5.1. TTL là giới hạn thời gian sống

TTL (time to live) xác định thời gian một entry được xem là còn hiệu lực kể từ lúc được ghi hoặc làm mới. Khi TTL hết, cache có thể xóa entry ngay hoặc đánh dấu nó không còn được phục vụ, tùy implementation.

TTL giúp giới hạn thời gian tồn tại của bản sao cũ nếu invalidation bị bỏ lỡ. Nhưng TTL không bảo đảm mọi thay đổi đều xuất hiện ngay sau khi commit. Nếu TTL là 10 phút, dữ liệu có thể cũ gần 10 phút trong trường hợp xấu nhất, cộng thêm độ trễ refresh hoặc propagation tùy chính sách.

### 5.2. Chọn TTL theo độ biến động và hậu quả của dữ liệu cũ

TTL cần dựa trên:

- Tần suất thay đổi của dữ liệu nguồn.
- Mức độ chấp nhận dữ liệu cũ.
- Chi phí truy vấn nguồn.
- Số lần truy cập lại trong TTL.
- Khả năng invalidation đáng tin cậy.
- Hậu quả nghiệp vụ nếu giá trị cũ được trả về.

Ví dụ minh họa:

| Loại dữ liệu | Đặc điểm | Chính sách có thể cân nhắc |
|---|---|---|
| Danh mục ít đổi | Tái sử dụng cao, thay đổi hiếm | TTL dài và invalidation khi quản trị cập nhật |
| Cấu hình feature | Cần lan truyền tương đối nhanh | TTL ngắn hoặc event invalidation |
| Hồ sơ khách hàng | Có thể đổi theo nghiệp vụ | TTL vừa, version/invalidation |
| Giá và tồn kho | Thay đổi thường xuyên, tác động trực tiếp | TTL ngắn, event hoặc đọc nguồn cho thao tác quyết định |
| Số liệu dashboard | Có thể chấp nhận trễ | TTL theo chu kỳ tổng hợp và freshness SLO |

Không áp dụng TTL mẫu một cách máy móc. Dữ liệu có cùng tốc độ thay đổi vẫn có thể cần freshness khác nhau vì hậu quả nghiệp vụ khác nhau.

### 5.3. TTL tuyệt đối và sliding expiration

- **TTL tuyệt đối:** entry hết hạn sau một khoảng thời gian cố định kể từ lúc được tạo hoặc refresh.
- **Sliding expiration:** mỗi lần truy cập có thể kéo dài thời hạn.

Sliding expiration giúp giữ key nóng trong cache, nhưng một key ít thay đổi vẫn có thể tồn tại rất lâu nếu được truy cập liên tục. Khi dữ liệu nguồn thay đổi mà invalidation thất bại, giá trị cũ có thể tiếp tục được phục vụ. Vì vậy, sliding expiration nên có hard maximum age hoặc kết hợp version/invalidation.

### 5.4. TTL jitter

Nếu hàng triệu key được ghi cùng một thời điểm với cùng TTL, chúng có thể hết hạn đồng loạt và tạo tải nguồn đột biến. TTL jitter cộng một lượng ngẫu nhiên nhỏ vào thời hạn để phân tán thời điểm hết hạn.

Ví dụ, TTL cơ sở 10 phút có thể được cộng/trừ một khoảng ngẫu nhiên đã xác định. Jitter cần giữ trong giới hạn freshness SLO. Không thêm jitter vượt quá mức dữ liệu cũ nghiệp vụ cho phép.

### 5.5. Freshness khác với TTL

Freshness mô tả mức độ gần với dữ liệu chuẩn hiện tại. TTL chỉ là một cơ chế giới hạn tuổi entry. Một entry TTL còn hiệu lực vẫn có thể đã cũ nếu nguồn thay đổi ngay sau khi entry được tạo.

Nên theo dõi:

- Entry age: tuổi của bản sao đang được phục vụ.
- Source version: version hoặc sequence của dữ liệu nguồn.
- Invalidation lag: thời gian từ commit đến lúc cache nhận invalidation.
- Refresh lag: thời gian từ lúc cần refresh đến khi giá trị mới sẵn sàng.
- Stale response rate: tỷ lệ request nhận giá trị vượt ngưỡng tuổi cho phép.

Freshness SLO có thể quy định, ví dụ: 99% request đọc danh mục nhận dữ liệu có tuổi dưới 60 giây; các thao tác kiểm tra tồn kho trước khi chốt đơn phải đọc nguồn hoặc xác minh lại trong transaction. Đây chỉ là ví dụ về cách định nghĩa, không phải ngưỡng mặc định.

### 5.6. Stale-while-revalidate

Với stale-while-revalidate, cache có thể tiếp tục trả giá trị cũ trong một khoảng stale window trong khi một worker làm mới dữ liệu nền. Cách này giảm latency và tránh nhiều request cùng chờ refresh.

Chỉ dùng khi nghiệp vụ chấp nhận dữ liệu cũ trong khoảng đã định. Các thao tác quyết định như xác nhận số dư, quyền truy cập, giá cuối cùng hoặc số lượng tồn kho cần quy tắc freshness chặt hơn. Có thể dùng stale cho hiển thị sơ bộ rồi xác minh lại trước khi commit hành động.

## 6. Invalidation và cập nhật dữ liệu

### 6.1. Eviction, expiration và invalidation khác nhau

- **Eviction:** cache loại entry để giải phóng bộ nhớ, ví dụ LRU/LFU hoặc chính sách admission.
- **Expiration:** entry hết hạn theo TTL.
- **Invalidation:** ứng dụng chủ động đánh dấu hoặc xóa entry vì dữ liệu nguồn đã thay đổi.
- **Refresh:** đọc giá trị mới từ nguồn và ghi lại cache.

Eviction không nhất thiết có nghĩa dữ liệu sai; entry chỉ bị loại để nhường bộ nhớ. Expiration là cơ chế theo thời gian. Invalidation liên quan đến thay đổi dữ liệu. Refresh tạo giá trị mới.

### 6.2. Cache-aside khi ghi

Một luồng phổ biến:

~~~text
1. Cập nhật bản ghi trong DBMS
2. COMMIT transaction
3. Xóa hoặc đánh dấu stale cache key
4. Request tiếp theo miss và đọc dữ liệu mới từ DBMS
5. Ghi bản mới vào cache
~~~

Cập nhật DB trước rồi invalidation sau thường tránh cache bị xóa trong khi transaction nguồn còn rollback. Nhưng giữa commit và invalidation, request có thể đọc giá trị cũ. Nếu invalidation event được gửi bất đồng bộ, khoảng trễ có thể dài hơn.

Đối với dữ liệu cần read-your-writes ngay lập tức, ứng dụng có thể trả giá trị đã commit trực tiếp từ luồng ghi, đọc nguồn trên request tiếp theo hoặc dùng version để không chấp nhận entry cũ.

### 6.3. Race condition: giá trị cũ được ghi lại sau invalidation

Một tình huống thường gặp:

1. Request A cache miss và đọc giá trị cũ từ DB.
2. Request B cập nhật DB và commit giá trị mới.
3. Request B xóa cache key.
4. Request A tiếp tục và ghi giá trị cũ vào cache sau khi key đã bị xóa.
5. Request tiếp theo nhận giá trị cũ cho đến khi TTL hết hoặc có invalidation khác.

Đây là race condition giữa loader và writer. Chỉ thực hiện delete sau commit chưa đủ để loại bỏ mọi trường hợp ghi lại dữ liệu cũ.

### 6.4. Cách hạn chế stale repopulation

Một số kỹ thuật:

- **Versioned value:** lưu version cùng giá trị và chỉ chấp nhận ghi nếu version mới hơn version hiện tại.
- **Generation key:** key gồm generation/version; khi cập nhật, tăng generation để mọi entry cũ không còn được tham chiếu.
- **Per-key lock hoặc singleflight:** chỉ một loader được phép nạp key trong cùng thời điểm; writer có thể phối hợp với loader.
- **Write fence:** writer đặt marker/version mới trước khi loader được phép publish kết quả.
- **Compare-and-set:** chỉ ghi cache nếu token/version vẫn đúng.
- **TTL ngắn và refresh:** giảm thời gian ảnh hưởng nếu race vẫn xảy ra.

Khóa phân tán cần lease, timeout và fencing token; khóa hết hạn trong lúc loader vẫn chạy có thể cho phép hai loader đồng thời. Không xem distributed lock là bảo đảm tuyệt đối nếu không có fencing/version.

### 6.5. Invalidate theo key, tag hoặc entity version

Một thay đổi có thể ảnh hưởng nhiều cache key. Ví dụ sửa tên sản phẩm có thể ảnh hưởng:

- Cache chi tiết sản phẩm.
- Danh sách theo danh mục.
- Kết quả tìm kiếm.
- Trang tổng hợp theo thương hiệu.

Có thể:

- Liệt kê và xóa các key phụ thuộc.
- Dùng tag để gom key theo entity hoặc nhóm dữ liệu.
- Tăng version của entity hoặc collection.
- Dùng generation cho toàn bộ một namespace.

Xóa hàng triệu key đồng bộ trong một transaction ghi có thể gây latency và tải cache lớn. Versioned namespace hoặc invalidation theo tag có thể giảm chi phí, nhưng cần kiểm soát rác key cũ và vòng đời generation.

### 6.6. Transactional outbox và CDC

Nếu ứng dụng cập nhật DB rồi phát event invalidation, có nguy cơ DB commit thành công nhưng gửi event thất bại. Transactional outbox giải quyết bằng cách ghi dữ liệu nghiệp vụ và bản ghi sự kiện trong cùng transaction DB. Một worker đọc outbox rồi phát event, retry cho đến khi xử lý thành công.

Change Data Capture (CDC) có thể lấy thay đổi từ transaction log để phát invalidation hoặc cập nhật cache. Cần xem:

- Event ordering theo entity hoặc partition.
- Duplicate delivery.
- Consumer retry và dead-letter.
- Consumer lag.
- Event bị xử lý sai thứ tự.
- Rebuild cache sau outage.
- Idempotency của thao tác invalidation.

Consumer nên idempotent: xử lý lại cùng event không làm trạng thái xấu đi. Nếu event đến muộn, version giúp bỏ qua invalidation cũ hoặc ngăn ghi đè dữ liệu mới.

## 7. Cache stampede, penetration và avalanche

### 7.1. Cache stampede

Cache stampede xảy ra khi một key nóng hết hạn hoặc bị evict, nhiều request cùng miss rồi đồng thời truy vấn nguồn. Một key trước đó giảm 1.000 query/giây xuống gần 0 có thể đột ngột tạo 1.000 query/giây vào DBMS.

Cách xử lý:

- Singleflight: gộp nhiều request cùng key vào một lần load.
- Per-key lock có lease và fencing.
- Refresh-ahead trước khi hết hạn.
- Stale-while-revalidate trong stale window được phép.
- TTL jitter để phân tán expiry.
- Giới hạn concurrency của loader.
- Request coalescing tại gateway hoặc cache layer.

Không dùng một global lock cho mọi key nếu nó khiến các key độc lập chờ nhau.

### 7.2. Cache penetration

Cache penetration xảy ra khi request liên tục hỏi key không tồn tại hoặc dữ liệu không bao giờ được cache. Mỗi request đều đi xuống nguồn, có thể do client gửi ID ngẫu nhiên hoặc bot quét.

Biện pháp:

- Negative caching: cache kết quả “không tồn tại” trong TTL ngắn.
- Validate định dạng và phạm vi ID trước khi truy vấn DB.
- Rate limit theo client/tenant.
- Bloom filter hoặc cấu trúc membership để loại sớm key chắc chắn không tồn tại.
- Theo dõi miss rate theo nhóm key và nguồn request.

Negative caching cần phân biệt “không tồn tại” với lỗi tạm thời, timeout hoặc quyền truy cập bị từ chối. Không cache exception của DBMS như thể bản ghi không tồn tại.

### 7.3. Cache avalanche

Cache avalanche là hiện tượng nhiều key hết hạn hoặc cache node gặp sự cố cùng lúc, khiến lượng lớn request chuyển xuống nguồn. Nguyên nhân có thể là TTL đồng nhất, restart cache, mất kết nối mạng hoặc deploy làm mất toàn bộ local cache.

Biện pháp:

- TTL jitter.
- Warm-up có giới hạn concurrency.
- Phân tán key và shard hợp lý.
- Rate limit và admission control ở tầng nguồn.
- Fallback có giới hạn, circuit breaker.
- Giữ stale value trong một khoảng được phép.
- Thử nghiệm cache cold-start và node failure.

### 7.4. Phân biệt ba dạng sự cố

| Hiện tượng | Nguyên nhân thường gặp | Biện pháp chính |
|---|---|---|
| Stampede | Một hoặc vài key nóng cùng miss | Singleflight, lock, stale refresh |
| Penetration | Nhiều key không tồn tại liên tục miss | Negative cache, validate, Bloom filter |
| Avalanche | Nhiều key hoặc toàn cache mất hiệu lực | TTL jitter, warm-up, load shedding |

## 8. Nhất quán giữa nhiều instance và nhiều tầng cache

### 8.1. Vấn đề bản sao phân tán

Khi ứng dụng có nhiều instance, mỗi instance có thể giữ L1 local cache. Nếu một instance cập nhật dữ liệu, các instance khác không tự biết bản sao của chúng đã cũ.

Ví dụ:

1. Instance A đọc hồ sơ khách hàng version 12 và lưu vào L1.
2. Instance B cập nhật hồ sơ trong DBMS, tạo version 13.
3. B xóa key trong L2 nhưng không gửi invalidation đến L1 của A.
4. A tiếp tục trả version 12 cho request tiếp theo.

TTL của L1 giới hạn thời gian tồn tại của dữ liệu cũ nhưng không loại bỏ khoảng stale ngay sau commit.

### 8.2. Broadcast invalidation

Có thể phát sự kiện khi dữ liệu thay đổi để các instance xóa hoặc đánh dấu stale key liên quan. Các phương tiện thường gặp gồm message broker, pub/sub, CDC hoặc event stream.

Cần thiết kế:

- Event có entity ID và version.
- Consumer xử lý idempotent.
- Event ordering được bảo đảm theo key nếu cần.
- Consumer theo dõi offset hoặc checkpoint.
- Có cách phát hiện consumer lag.
- Có cơ chế rebuild hoặc full refresh khi bỏ lỡ event.
- Có TTL làm lớp bảo vệ cuối cùng.

Pub/sub chỉ phát sự kiện cho subscriber đang kết nối thường không đủ nếu subscriber có thể offline. Cần durable event log, replay hoặc cơ chế đồng bộ lại.

### 8.3. Versioned key giúp bản sao cũ mất hiệu lực

Thay vì chỉ dùng key cố định, có thể đưa version vào key:

~~~text
customer-profile:customer-42:version-13
~~~

Một metadata key hoặc version store giữ version hiện hành. Khi entity được cập nhật, version tăng từ 12 lên 13. Request mới tra version hiện hành và chỉ đọc key version 13; bản version 12 có thể còn trong cache nhưng không còn được tham chiếu.

Cách này tránh một số race khi loader cũ cố ghi lại key cũ. Tuy nhiên, metadata version phải được cập nhật đáng tin cậy và đọc nhất quán đủ cho yêu cầu. Nếu version lookup cũng cache quá lâu, stale có thể tiếp tục xuất hiện.

### 8.4. L1 local và L2 distributed

Khi có L1 và L2, cần định nghĩa:

- L1 TTL tối đa bao lâu?
- L2 invalidation có được broadcast đến mọi L1 không?
- Khi L2 down, L1 có được tiếp tục phục vụ không?
- Một giá trị L1 có version để so sánh với L2 không?
- Khi một instance restart, cache warm-up có gây tải đột biến không?
- Có thể chấp nhận hai instance trả version khác nhau trong bao lâu?

Một chính sách thực tế có thể dùng L1 TTL ngắn, L2 TTL dài hơn và invalidation event để xóa L1 sớm. Với dữ liệu nhạy cảm về quyền truy cập hoặc trạng thái quyết định nghiệp vụ, cần kiểm tra nguồn hoặc dùng version mạnh hơn.

## 9. Chọn mức nhất quán và độ cũ được phép

### 9.1. Eventual consistency

Với eventual consistency, các bản sao có thể khác nhau trong một khoảng thời gian nhưng sẽ hội tụ nếu không có cập nhật mới và hệ thống truyền thay đổi thành công.

Mô hình này thường phù hợp với:

- Danh mục sản phẩm.
- Nội dung hiển thị.
- Dữ liệu dashboard.
- Thống kê tổng hợp.
- Cấu hình có thể chấp nhận lan truyền chậm.

Cần định nghĩa thời gian hội tụ mục tiêu và cách xử lý khi event bị trễ hoặc mất.

### 9.2. Read-your-writes

Read-your-writes nghĩa là sau khi một người dùng cập nhật dữ liệu thành công, lần đọc tiếp theo của chính người đó nhìn thấy thay đổi vừa ghi.

Có thể đáp ứng bằng cách:

- Trả trực tiếp giá trị đã commit từ write path.
- Bỏ qua cache trong một khoảng ngắn sau khi ghi.
- Gắn version trả về từ write vào request đọc tiếp theo.
- Đọc từ primary hoặc nguồn có version ít nhất bằng version vừa commit.
- Cập nhật cache theo version sau khi transaction commit.

Không nên giả định invalidation bất đồng bộ bảo đảm read-your-writes ngay lập tức.

### 9.3. Monotonic reads

Monotonic reads bảo đảm một client không nhìn thấy version cũ hơn sau khi đã nhìn thấy version mới hơn. Nếu request đầu được phục vụ từ replica hoặc cache version 13, request sau không nên quay về version 12.

Có thể dùng version token trong session/request context, sticky routing đến nguồn phù hợp hoặc kiểm tra version tối thiểu trước khi trả cache. Điều này quan trọng khi traffic đi qua nhiều application instance và nhiều replica.

### 9.4. Bounded staleness

Bounded staleness đặt giới hạn rõ cho tuổi dữ liệu hoặc độ trễ cập nhật. Ví dụ, một dashboard có thể chấp nhận dữ liệu chậm tối đa 2 phút; một trang thông tin sản phẩm có thể chấp nhận 30 giây.

Giới hạn cần được đo theo thời gian từ commit nguồn đến lúc cache trả version mới, không chỉ dựa vào TTL cấu hình. Invalidation queue lag, consumer downtime và refresh duration đều ảnh hưởng.

### 9.5. Khi nào cần đọc nguồn?

Cache không nên quyết định những hành động mà dữ liệu cũ có hậu quả lớn nếu nghiệp vụ yêu cầu xác nhận mới nhất.

Ví dụ:

- Kiểm tra số dư trước khi ghi giao dịch.
- Xác nhận tồn kho trước khi chốt đơn.
- Kiểm tra quyền truy cập vừa bị thu hồi.
- Xác nhận trạng thái đơn hàng trước một chuyển trạng thái không thể đảo ngược.
- Kiểm tra quota hoặc giới hạn cần áp dụng chính xác.

Có thể dùng cache để hiển thị hoặc gợi ý, nhưng bước commit cuối cùng cần xác minh bằng transaction hoặc cơ chế đồng bộ phù hợp.

## 10. Dung lượng cache, eviction và admission

### 10.1. Cache có ngân sách bộ nhớ hữu hạn

Mỗi entry chiếm bộ nhớ cho key, value, metadata, expiration, object header và cấu trúc quản lý. Payload 1 KB có thể tiêu tốn nhiều hơn 1 KB RAM thực tế.

Ước lượng bộ nhớ:

\[
CacheMemory \approx
\sum_{i=1}^{N}(KeyBytes_i + ValueBytes_i + Metadata_i)
\]

Cần cộng thêm replication, allocator fragmentation, client buffers và overhead của cache server. Đo bộ nhớ thực tế dưới tải thay vì chỉ cộng kích thước serialized payload.

### 10.2. Eviction policy

Khi vượt ngân sách, cache phải chọn entry để loại bỏ. Các chính sách thường gặp:

- **LRU:** loại entry ít được dùng gần đây.
- **LFU:** ưu tiên giữ entry có tần suất truy cập cao.
- **TTL-based:** loại entry hết hạn.
- **Size-aware:** xét kích thước entry và giá trị tái sử dụng.
- **Admission policy:** quyết định có nên đưa entry mới vào cache hay không.

LRU phù hợp với locality theo thời gian nhưng một đợt scan lớn có thể đẩy key nóng ra ngoài. LFU có thể giữ key từng rất nóng nhưng phản ứng chậm với thay đổi workload nếu không aging frequency. Một số cache dùng chính sách kết hợp như TinyLFU để hạn chế cache pollution.

### 10.3. Admission control cho cache

Không phải mọi miss đều đáng được cache. Một key chỉ được đọc một lần có thể làm mất chỗ của key được đọc hàng nghìn lần.

Có thể chỉ cache khi:

- Key có tần suất truy cập đủ cao.
- Giá trị có chi phí tính toán hoặc truy vấn nguồn đáng kể.
- Payload nằm trong giới hạn kích thước.
- Dữ liệu có TTL và semantics rõ.
- Cache còn dung lượng và nhóm workload được phép sử dụng.

Với dữ liệu lớn, có thể cache metadata hoặc phần thường dùng thay vì toàn bộ LOB. Cần theo dõi tỷ lệ key bị đọc một lần và số byte bị eviction.

### 10.4. Serialization và version schema

Cache phân tán thường lưu giá trị đã serialize. Khi deploy phiên bản ứng dụng mới, cấu trúc object có thể thay đổi. Nếu code mới đọc payload cũ không tương thích, lỗi decode có thể làm request thất bại hoặc tạo miss hàng loạt.

Biện pháp:

- Đưa schema version vào key hoặc payload.
- Hỗ trợ đọc nhiều version trong giai đoạn rollout nếu cần.
- Dùng format có version và field compatibility.
- Đặt TTL để dọn payload cũ.
- Tránh xóa toàn bộ cache cùng lúc nếu không cần thiết.
- Có kế hoạch warm-up theo tốc độ giới hạn.

Không dùng Java native serialization hoặc định dạng phụ thuộc implementation mà không đánh giá tương thích và bảo mật. Cần kiểm soát nguồn gốc payload và tránh deserialize dữ liệu không tin cậy.

## 11. Vận hành khi cache hoặc nguồn gặp sự cố

### 11.1. Cache down không được làm nguồn sụp đổ

Nếu cache ngừng hoạt động, mọi request có thể chuyển xuống DBMS cùng lúc. Một hệ thống trước đó chịu 10.000 request/giây nhờ cache có thể bất ngờ đẩy phần lớn tải đó về nguồn.

Cần chuẩn bị:

- Giới hạn số request fallback xuống DBMS.
- Admission control và queue có giới hạn.
- Circuit breaker cho cache và nguồn.
- Timeout ngắn, phù hợp cho cache call.
- Retry có backoff và jitter.
- Stale fallback khi dữ liệu được phép cũ.
- Giảm tải có kiểm soát hoặc trả lỗi có thể retry.
- Capacity plan cho cache cold-start.

Không retry vô hạn hoặc retry đồng loạt. Retry storm có thể làm cache và DBMS khó phục hồi hơn.

### 11.2. Stale fallback

Nếu cache server không khả dụng nhưng process có bản sao local còn trong stale window, ứng dụng có thể tiếp tục phục vụ dữ liệu đó khi nghiệp vụ cho phép. Cần hiển thị hoặc ghi metric về việc đang phục vụ stale data.

Không phục vụ stale cho dữ liệu mà quyền truy cập đã bị thu hồi hoặc trạng thái quyết định đã thay đổi nếu điều đó tạo rủi ro. Mỗi nhóm dữ liệu cần freshness policy riêng.

### 11.3. Circuit breaker và bulkhead

Circuit breaker tạm ngừng gọi một dependency đang lỗi để tránh request chờ timeout liên tục. Sau một khoảng nghỉ, hệ thống thử lại có giới hạn.

Bulkhead tách tài nguyên theo workload hoặc dependency, ví dụ pool riêng cho cache refresh và DB query. Khi refresh bị kẹt, nó không được phép chiếm toàn bộ thread hoặc connection phục vụ OLTP.

Cần tránh để circuit breaker đóng/mở đồng bộ trên mọi instance. Jitter và phân tán thời điểm thử lại giúp tránh tất cả instance cùng tạo tải khi dependency hồi phục.

### 11.4. Cache warm-up

Sau restart hoặc flush cache, warm-up có thể giảm miss trong giai đoạn đầu. Nhưng nạp toàn bộ key nóng cùng lúc có thể tạo một đợt query lớn.

Nên:

- Chọn key có tần suất và giá trị cao.
- Warm-up theo batch và concurrency giới hạn.
- Ưu tiên dữ liệu cần cho traffic sắp tới.
- Đo DBMS load trong warm-up.
- Cho phép request bình thường cùng tham gia nạp cache.
- Không giữ cache entry nếu dữ liệu đã hết hạn hoặc version không còn đúng.

## 12. Đo lường cache trong hệ thống cơ sở dữ liệu

### 12.1. Nhóm metric cần có

Một dashboard cache nên có:

| Nhóm | Metric | Ý nghĩa |
|---|---|---|
| Lưu lượng | Hits, misses, sets, deletes | Mức sử dụng cache |
| Tỷ lệ | Request hit ratio, byte hit ratio | Bao nhiêu request/byte được phục vụ từ cache |
| Nguồn | DB query count, CPU, logical/physical reads | Cache giảm tải DB đến đâu |
| Độ trễ | Cache get p95/p99, source query p95/p99 | Chi phí từng đường đọc |
| Freshness | Entry age, source version, invalidation lag | Dữ liệu cũ đến mức nào |
| Bộ nhớ | Used memory, key count, evictions | Áp lực dung lượng |
| Sự cố | Timeouts, errors, reconnects, failovers | Độ tin cậy của cache |
| Đồng thời | Loader concurrency, lock wait, queue depth | Nguy cơ stampede và nghẽn |
| Kết quả | Stale response rate, correctness checks | Chất lượng dữ liệu trả về |

### 12.2. Đo theo cùng một cửa sổ tải

So sánh hit ratio trước và sau deploy mà không kiểm soát workload có thể gây hiểu nhầm. Traffic mix, tenant, thời gian trong ngày và cache warm/cold đều ảnh hưởng.

Khi benchmark, giữ ổn định:

- Tập request và phân bố key.
- Tỷ lệ đọc/ghi.
- Số application instance.
- Cache capacity và TTL.
- Mức concurrency.
- Dữ liệu nguồn và statistics.
- Thời gian warm-up.
- Thời lượng đo đủ dài để quan sát expiry và eviction.

### 12.3. Hit ratio cao nhưng latency vẫn xấu

Một cache có hit ratio cao vẫn có thể gây latency do:

- Cache server ở xa hoặc network RTT cao.
- Object quá lớn và deserialize tốn CPU.
- Cache get bị contention hoặc hot key.
- L1 miss nhưng L2 hit chậm.
- Cache hit xảy ra nhưng ứng dụng vẫn gọi DB để xác minh.
- Miss của một số query rất đắt chiếm phần lớn p99.
- Cache refresh chạy song song làm tranh chấp CPU hoặc network.

Hãy đo latency theo từng tầng và theo từng nhóm key. Hit ratio không thay thế latency histogram.

### 12.4. Cache hit không có nghĩa query cost bằng không

Ngay cả khi hit, ứng dụng vẫn có thể phải:

- Xác thực quyền.
- Kiểm tra version.
- Giải mã payload.
- Ánh xạ object.
- Chuyển đổi timezone hoặc currency.
- Tạo response.
- Gửi dữ liệu qua mạng đến người dùng.

Cache giảm một số chi phí, nhưng không loại bỏ toàn bộ đường đi của request.

## 13. Tình huống thực tế: hit ratio cao nhưng dữ liệu cũ sau cập nhật

### 13.1. Hiện tượng

Một hệ thống thương mại cache hồ sơ sản phẩm ở L1 trong mỗi application instance và L2 trong Redis. Dashboard cho thấy request hit ratio 96%, DB query count giảm rõ rệt. Tuy nhiên, sau khi nhân viên cập nhật giá hoặc trạng thái sản phẩm, một số người dùng vẫn thấy giá cũ trong vài phút.

### 13.2. Điều tra

Nhóm vận hành phát hiện:

- Write path commit dữ liệu vào DBMS.
- Sau commit, service gửi invalidation qua pub/sub.
- Một application instance tạm mất kết nối subscriber.
- Pub/sub không lưu event để instance đọc lại sau reconnect.
- L1 của instance đó vẫn giữ giá cũ đến khi TTL 5 phút hết.
- Metric chỉ có hit/miss, chưa có entry age hoặc invalidation lag.

Hit ratio cao phản ánh khả năng tái sử dụng bản sao, không chứng minh bản sao còn mới.

### 13.3. Thay đổi thử nghiệm

1. Thêm source version vào event invalidation.
2. Dùng durable event stream hoặc outbox để instance có thể replay event.
3. Khi subscriber reconnect, phát hiện khoảng offset bị thiếu và đồng bộ lại.
4. Giảm L1 TTL để giới hạn stale window trong lúc cơ chế event phục hồi.
5. Thêm metric consumer lag, entry age và stale response rate.
6. Với thao tác chốt giá, xác minh version từ nguồn trước khi commit đơn hàng.
7. Dùng generation key cho nhóm sản phẩm nếu cần invalidation theo collection.

### 13.4. Kết quả minh họa

| Chỉ số | Trước | Sau thử nghiệm |
|---|---:|---:|
| Request hit ratio | 96% | 94% |
| Invalidation lag p99 | Không đo | 2,5 giây |
| Stale response sau cập nhật | Tối đa gần 5 phút | Dưới 3 giây trong thử nghiệm |
| Query đọc hồ sơ sản phẩm | Thấp | Tăng nhẹ |
| Latency p95 của trang danh sách | 42 ms | 45 ms |

Các con số chỉ minh họa. Hit ratio giảm nhẹ do L1 TTL ngắn và invalidation chính xác hơn, nhưng độ tươi được cải thiện rõ. Với thao tác nghiệp vụ nhạy cảm, hệ thống còn kiểm tra version từ nguồn ở bước quyết định cuối cùng.

## 14. Quy trình thiết kế và kiểm chứng cache

Có thể áp dụng theo trình tự:

1. **Xác định dữ liệu:** key nào được đọc lặp lại và query nguồn nào tốn kém?
2. **Xác định freshness:** dữ liệu cũ tối đa bao lâu và hành động nào cần xác minh nguồn?
3. **Thiết kế key:** bao gồm tenant, security scope, filter, locale, version và các chiều ảnh hưởng kết quả.
4. **Chọn policy:** cache-aside, read-through, write-through, write-behind hoặc refresh-ahead.
5. **Chọn TTL:** theo độ biến động, hậu quả dữ liệu cũ và khả năng invalidation.
6. **Thiết kế invalidation:** key/tag/version, outbox hoặc CDC, retry và replay.
7. **Xử lý concurrency:** singleflight, lock/fencing, bounded loader và TTL jitter.
8. **Đặt giới hạn cache:** memory budget, max object size, admission và eviction.
9. **Thiết kế fallback:** cache down, source overload, stale window và circuit breaker.
10. **Instrument:** hit/miss, byte ratio, entry age, invalidation lag, latency, DB load và eviction.
11. **Benchmark:** warm/cold cache, read/write mix, key skew và concurrency.
12. **Fault injection:** mất cache, mất subscriber, event duplicate/out-of-order, node restart và source timeout.
13. **Kiểm chứng dữ liệu:** read-your-writes, quyền truy cập, không trộn tenant và không ghi đè version mới bằng version cũ.
14. **Theo dõi sau triển khai:** freshness SLO, DB query load, latency p95/p99 và chi phí bộ nhớ.

### 14.1. Ma trận kiểm thử

| Tình huống | Kỳ vọng cần xác minh |
|---|---|
| Key chưa có | Loader chỉ chạy số lần được kiểm soát |
| Key nóng vừa hết hạn | Không tạo stampede |
| Nhiều key hết hạn cùng lúc | TTL jitter và admission bảo vệ nguồn |
| Entity được cập nhật | Invalidation/version khiến request mới thấy dữ liệu phù hợp |
| Loader đọc version cũ hoàn tất muộn | Không ghi đè entry version mới |
| Consumer mất kết nối | Replay hoặc rebuild khôi phục invalidation |
| Cache node down | Fallback không làm DBMS quá tải |
| Cache cold-start | Warm-up có giới hạn |
| Người dùng khác tenant | Không nhận nhầm cache entry |
| Quyền bị thu hồi | Request không dùng bản sao vượt quyền |
| Payload schema đổi | Cache version cũ được xử lý an toàn |
| Client retry cùng write | Không tạo trạng thái sai do event hoặc ghi lặp |

### 14.2. Tiêu chí chấp nhận

Một thiết kế cache có thể được chấp nhận khi:

- DB query count hoặc chi phí nguồn giảm dưới workload tương đương.
- Latency p95/p99 đạt mục tiêu.
- Hit ratio và byte hit ratio được hiểu theo đúng đơn vị.
- Freshness SLO được đo và đạt.
- Invalidation event không bị mất âm thầm.
- Stampede, penetration và avalanche được kiểm soát.
- Cache down không làm nguồn sụp đổ.
- Memory usage và eviction nằm trong ngân sách.
- Quyền truy cập và tenant isolation được bảo toàn.
- Có thể phục hồi sau restart, replay event và warm-up có giới hạn.

## 15. Những sai lầm thường gặp

**Chỉ tối ưu hit ratio.**  
Hit ratio cao không chứng minh latency thấp, DB load giảm tương ứng hoặc dữ liệu còn mới.

**Đặt TTL dài để tăng hit.**  
TTL dài có thể kéo dài thời gian phục vụ dữ liệu cũ khi invalidation thất bại.

**Xóa cache trước khi DB commit.**  
Request có thể nạp lại giá trị cũ trong lúc transaction chưa commit.

**Cho rằng xóa key sau commit loại bỏ mọi race.**  
Loader cũ có thể hoàn tất muộn và ghi lại giá trị cũ sau invalidation.

**Dùng pub/sub không có replay làm cơ chế duy nhất.**  
Instance mất kết nối có thể bỏ lỡ event và giữ L1 stale đến khi TTL hết.

**Dùng cùng cache key cho mọi tenant hoặc quyền.**  
Có thể làm lộ dữ liệu giữa tenant hoặc trả kết quả đã lọc quyền sai người.

**Cache mọi query.**  
Key ít được dùng và payload lớn có thể làm cache pollution, eviction key nóng.

**Không có negative cache.**  
Request liên tục hỏi ID không tồn tại có thể đẩy toàn bộ tải xuống DBMS.

**Để mọi key có cùng TTL.**  
Nhiều key hết hạn cùng lúc có thể gây avalanche.

**Dùng distributed lock mà không có fencing.**  
Loader cũ có thể tiếp tục ghi sau khi lease hết hạn và một loader mới đã chạy.

**Fallback không giới hạn khi cache down.**  
DBMS có thể nhận toàn bộ traffic trước đó được cache hấp thụ.

**Cache trạng thái cần quyết định chính xác.**  
Dữ liệu cũ về số dư, tồn kho, quyền hoặc giá cuối cùng có thể gây lỗi nghiệp vụ.

**Không version hóa payload.**  
Deploy mới có thể không đọc được object cũ và tạo miss hàng loạt.

## 16. Kết luận

Bộ đệm ứng dụng giúp giảm query nguồn và latency khi dữ liệu được tái sử dụng, nhưng hiệu quả phải được đánh giá bằng cả hit ratio, byte hit ratio, DB load, latency và freshness. Cache key phải đại diện cho mọi tham số ảnh hưởng kết quả, bao gồm tenant và security scope. TTL giới hạn tuổi entry, còn invalidation và version quyết định cách phản ánh thay đổi từ nguồn.

Cache-aside là điểm bắt đầu phổ biến, nhưng cần xử lý race giữa loader và writer, gộp request cùng key, phát invalidation bền vững và kiểm soát stale window. L1/L2 cần cơ chế đồng bộ hoặc TTL phù hợp. Khi cache down, fallback phải có giới hạn để DBMS không bị quá tải. Với dữ liệu có hậu quả nghiệp vụ cao, cache chỉ nên hỗ trợ hiển thị hoặc tăng tốc; bước quyết định cuối cần xác minh theo consistency yêu cầu.

Một cache tốt không chỉ có nhiều hit. Nó phục vụ đúng dữ liệu, đúng tenant, trong giới hạn tuổi được chấp nhận, giảm chi phí nguồn và vẫn duy trì hệ thống ổn định khi hết hạn, mất node hoặc mất event.

## Câu hỏi tự kiểm tra

1. Cache ứng dụng khác buffer cache của DBMS ở mục đích và đơn vị dữ liệu như thế nào?
2. Request hit ratio và byte hit ratio có thể dẫn đến kết luận khác nhau ra sao?
3. Vì sao hit ratio cao không đồng nghĩa DBMS đã giảm tải theo cùng tỷ lệ?
4. Cache-aside và read-through khác nhau ở thành phần chịu trách nhiệm load dữ liệu nào?
5. Write-behind cần những cơ chế durability, ordering và retry nào?
6. Cache key cần bao gồm những chiều nào để tránh trộn tenant hoặc quyền truy cập?
7. TTL và freshness khác nhau như thế nào?
8. Vì sao sliding expiration cần hard maximum age hoặc invalidation?
9. Hãy mô tả race khi loader đọc version cũ rồi ghi cache sau invalidation.
10. Versioned key, compare-and-set và fencing token giúp giảm race như thế nào?
11. Transactional outbox hoặc CDC giải quyết vấn đề gì khi phát invalidation?
12. Cache stampede, penetration và avalanche khác nhau như thế nào?
13. Khi nào negative caching có thể tạo lỗi nghiệp vụ?
14. Vì sao cache down cần admission control và fallback giới hạn?
15. Thiết kế một freshness SLO cho danh mục sản phẩm và một quy tắc xác minh nguồn cho thao tác chốt đơn.
16. Hãy đề xuất dashboard theo dõi hit ratio, byte ratio, invalidation lag, entry age, DB load và latency p99.
17. Thiết kế fault test khi một application instance mất subscriber rồi kết nối lại, bảo đảm L1 không tiếp tục trả version cũ vô thời hạn.

Khi đánh giá một cache, hãy hỏi: cache đang tránh chi phí nào, giá trị được định danh bằng key nào, thay đổi nguồn lan truyền đến mọi bản sao trong bao lâu và hệ thống làm gì khi cache không thể trả lời. Những câu hỏi đó giúp cân bằng hiệu năng với tính đúng đắn của dữ liệu.



