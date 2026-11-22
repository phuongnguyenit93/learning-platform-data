# Đánh đổi giữa bộ nhớ đệm cục bộ và dùng chung

Khi một microservice phải đọc đi đọc lại cùng dữ liệu sản phẩm, cấu hình, quyền truy cập hoặc kết quả tính toán, **cache** có thể giảm độ trễ và giảm tải lên database hay service phụ thuộc. Nhưng chọn đặt cache trong bộ nhớ từng tiến trình hay trong một hệ thống dùng chung không đơn thuần là quyết định “cái nào nhanh hơn”. Hai cách này tạo ra khác biệt về **phạm vi chia sẻ, nhất quán, độ sẵn sàng, chi phí, khả năng mở rộng, quyền truy cập và vận hành**.

**Bộ nhớ đệm cục bộ (local/in-process cache)** lưu dữ liệu trong bộ nhớ của một instance ứng dụng; đọc thường không cần chuyến đi qua mạng. **Bộ nhớ đệm dùng chung (shared/distributed cache)** lưu dữ liệu trong dịch vụ cache riêng, ví dụ Redis hoặc Memcached, để nhiều instance có thể truy cập cùng một không gian dữ liệu logic. Một số hệ thống kết hợp cả hai thành **L1/L2 cache**.

Mục tiêu là chọn kiến trúc theo đặc tính dữ liệu và yêu cầu nghiệp vụ, biết sự đánh đổi khi cache sai hoặc dữ liệu thay đổi, đồng thời thiết kế được biện pháp bảo vệ trước các lỗi phổ biến như stampede, stale data và cache outage.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả đường đi đọc/ghi của local cache, shared cache và mô hình hai tầng.
2. So sánh cache hit latency, network hop, dữ liệu bị nhân bản, hiệu quả bộ nhớ và chi phí vận hành.
3. Giải thích vì sao tăng số replicas có thể làm hit ratio của local cache giảm hoặc làm hiệu ứng warm-up mạnh hơn.
4. Phân biệt TTL, eviction, invalidation, cache-aside, write-through, write-around và write-behind.
5. Thiết kế consistency contract cho dữ liệu có thể thay đổi: độ cũ cho phép, điểm cập nhật và quy tắc bỏ cache.
6. Chống cache stampede, hot key, cache penetration, negative caching và thundering herd.
7. Đánh giá rủi ro dùng Redis/shared cache như một dependency mới trong đường request.
8. Thiết lập các metric hit/miss, load latency, memory pressure và freshness để ra quyết định có bằng chứng.
9. Chọn local, shared hoặc L1/L2 cho một tình huống microservices cụ thể.

## 2. Cache đứng ở đâu trong hệ thống?

Xét hệ thống thương mại điện tử có bốn service:

~~~text
                     +----------------+
                     |  API Gateway   |
                     +--------+-------+
                              |
                              v
                +-------------+-------------+
                |        Catalog API        |
                |      Pod A / Pod B        |
                +-------------+-------------+
                              |
                 +------------+------------+
                 |                         |
                 v                         v
          Product Database          Pricing Service
                                          |
                                          v
                                      Database
~~~

Endpoint `GET /products/{id}` có thể được gọi hàng nghìn lần cho một nhóm sản phẩm phổ biến; giá niêm yết và mô tả thay đổi ít, nhưng tồn kho có thể thay đổi liên tục. Cache cả ba trường vào cùng một object với TTL dài sẽ làm giảm truy vấn, nhưng có thể trả tồn kho sai. Kiến trúc thường cần **tách dữ liệu theo đặc tính cập nhật**.

Điều cần xác định trước khi chọn loại cache:

- Dữ liệu nào được cache? Bản ghi sản phẩm, catalog, access policy, giá, inventory hay kết quả tính toán?
- Cập nhật thường xuyên đến mức nào và do service nào sở hữu?
- Độ cũ tối đa được chấp nhận là bao lâu?
- Read/write ratio và phân phối key có tập trung vào một số key nóng không?
- Một request có bắt buộc đọc đúng giá trị mới nhất không?
- Khi cache không hoạt động, hệ thống có thể quay về source of truth hay phải từ chối request?
- Cache miss gây tải bao nhiêu cho database/downstream?
- Có dữ liệu nhạy cảm, tenant isolation hay giới hạn vùng địa lý không?

**Cache không phải source of truth** trừ khi hệ thống cố ý thiết kế một data store với hợp đồng bền vững riêng. Một key tồn tại trong Redis hoặc Caffeine chưa chứng minh dữ liệu đó là mới nhất, hợp lệ hay có quyền sử dụng.

## 3. Cơ chế local cache

Local cache nằm bên trong một tiến trình:

~~~text
Client
  |
  v
Load Balancer
  |
  +--> Catalog Pod A ----> Local Cache A ----\
  |                                          |
  +--> Catalog Pod B ----> Local Cache B ----+--> Catalog Database
  |                                          |
  +--> Catalog Pod C ----> Local Cache C ----/
~~~

Mỗi Pod có không gian nhớ riêng. Key `product:42` có thể nằm trong A nhưng không có trong B; khi B nhận request, nó vẫn phải load dữ liệu từ database. Khi Pod A restart, cache A bị mất; B và C không bị mất theo.

### Ưu điểm

- **Truy cập nhanh:** lấy từ RAM của process, tránh network hop đến dịch vụ cache.
- **Ít dependency hơn:** local cache không cần một server cache hay kết nối riêng cho từng lần đọc.
- **Giảm tải mạng:** request hit local không tạo traffic tới Redis/DB.
- **Hoạt động được khi shared cache bị lỗi:** nếu local còn dữ liệu hợp lệ và policy cho phép, nó có thể giảm tác động.
- **Đơn giản cho dữ liệu chỉ dùng trong một service:** một bảng tra cứu nhỏ, schema/metadata cố định hoặc cấu hình gần bất biến.

### Hạn chế

- **Dữ liệu lặp trên nhiều replicas:** 10 pods cùng giữ một tập hot keys sẽ nhân bản bộ nhớ.
- **Dễ khác nhau giữa instances:** A nhận bản cập nhật nhưng B chưa invalidated, làm kết quả phụ thuộc routing.
- **Không chia sẻ hit giữa pods:** thêm replica có thể làm giảm hit ratio trong giai đoạn cache cold hoặc khi key phân bố rộng.
- **Cold start và restart:** mỗi instance phải warm cache; một đợt rollout có thể tạo tải đồng thời lên database.
- **Áp lực JVM heap/GC:** cache lớn làm tăng memory footprint, GC pause hoặc OOM.
- **Khó điều phối invalidation toàn cụm:** gửi sự kiện đến từng instance có thể bị trễ/mất hoặc bỏ sót instance mới.

Local cache không sai vì thiếu nhất quán hoàn toàn; nó phù hợp khi hệ thống **có hợp đồng freshness chấp nhận eventual consistency** hoặc data không nhạy với thời điểm cập nhật.

## 4. Cơ chế shared cache

Shared cache là một service riêng có nhiều client:

~~~text
           Catalog Pod A ---\
           Catalog Pod B ----+----> Shared Cache Cluster ---> Catalog DB
           Catalog Pod C ---/
~~~

Các Pod cùng tra key logic `catalog:product:42`. Nếu A đã nạp vào shared cache, B có thể dùng kết quả. Cache có thể triển khai một node, primary/replica, cluster sharding hoặc managed service; topology thực tế tác động trực tiếp tới latency và consistency.

### Ưu điểm

- **Dùng chung kết quả đọc:** nhiều replicas không phải tự nạp cùng key.
- **Đầu mối invalidation rõ:** cập nhật/delete một key trên shared cache có thể ảnh hưởng các client truy cập sau đó.
- **Quản lý dung lượng tập trung:** memory budget và chính sách eviction có thể điều phối ở cấp cache cluster.
- **Thường hữu ích cho dữ liệu có tập key lớn:** nhiều service instances cùng hưởng lợi từ warm cache.
- **Tách lifecycle cache khỏi Pod:** Pod restart không làm mất dữ liệu đã ở shared cache.
- **Tạo điểm quan sát tập trung:** có thể theo dõi hit, miss, memory, ops, network, eviction theo cache server.

### Hạn chế

- **Network hop:** mỗi request tới cache đi qua client connection, mạng và server; p99 có thể tăng khi cache hoặc mạng chậm.
- **Dependency mới trong critical path:** cache outage, timeout hoặc pool exhaustion có thể ảnh hưởng rất nhiều request cùng lúc.
- **Chi phí vận hành:** HA, backup khi cần, failover, TLS, auth, patch, topology, sharding, capacity và on-call.
- **Hot key/bottleneck:** một key hoặc shard có thể chịu tải rất cao, tạo điểm nóng.
- **Không tự đảm bảo consistency mạnh:** TTL, failover, replica lag, cập nhật cache và database vẫn cần thiết kế.
- **Dữ liệu nhạy cảm di chuyển qua mạng:** phải kiểm soát quyền, mã hóa, tenant isolation và retention.

Shared cache có thể là thành phần chung cho nhiều service, nhưng không nên biến nó thành **database chung không có chủ sở hữu schema và lifecycle**. Đặc biệt không để service A tự sửa dữ liệu cache thuộc sở hữu service B rồi kỳ vọng mọi thứ vẫn đúng.

## 5. So sánh hai lựa chọn theo tiêu chí thiết kế

| Tiêu chí | Local cache | Shared cache |
|---|---|---|
| Hit latency | Thường rất thấp, truy cập trong process | Có network + client/server processing |
| Network dependency | Không có ở lúc hit | Có ở mỗi lần truy cập cache |
| Memory | Nhân bản giữa replicas | Tập trung; client có overhead nhỏ |
| Hit chia sẻ qua replicas | Không | Có |
| Ảnh hưởng restart Pod | Pod mất cache riêng | Shared cache còn nếu service cache vẫn sống |
| Invalidation xuyên instance | Cần TTL/event/broadcast hoặc chiến lược khác | Xóa/cập nhật key chung; vẫn có race/replica lag |
| Khả năng mở rộng | Scale app làm tổng cache memory tăng | Scale cache tách khỏi app, cần sharding/HA |
| Cách chịu lỗi | Lỗi cache thường gắn với Pod, có thể fallback | Sự cố cache có thể ảnh hưởng hàng loạt service |
| Observability | Phải tổng hợp metric từ từng instance | Có cả metric client và cache server |
| Bảo mật | Secret/dữ liệu nằm trong memory mỗi process | Dữ liệu được chia sẻ qua network và infrastructure |
| Phù hợp | Key nhỏ/hot, dữ liệu ít đổi, TTL ngắn, latency cực thấp | Nhiều replicas, bộ key dùng chung lớn, cần reuse qua processes |
| Độ phức tạp | Cài đặt đơn giản, consistency xuyên Pod khó | Hạ tầng phức tạp hơn, logic cache và consistency vẫn phải có |

Không có lựa chọn thắng tuyệt đối. Cần đo bằng workload thực tế, kể cả khi tăng replicas, traffic biến động, xảy ra lỗi và dữ liệu được cập nhật.

## 6. Phân biệt hit ratio, latency và chi phí

**Hit ratio** là tỷ lệ lookup được phục vụ bởi cache. Chỉ số này quan trọng, nhưng một hit ratio cao chưa chắc giúp hiệu năng nếu cache lookup quá chậm hoặc serialization/deserialization tốn nhiều CPU.

Với một tầng cache:

~~~text
H = số lần cache hit / tổng số lần tra cache

Expected latency xấp xỉ:
E[T] = H × T_hit + (1-H) × (T_miss_lookup + T_origin)
~~~

Công thức chỉ minh họa; real latency còn có queueing, concurrency, serialization, timeout, tail latency và retry. Khi tính phải quy ước rõ `T_hit` là toàn bộ thời gian lookup thành công hay chỉ thời gian xử lý phần cache, tránh cộng trùng.

### Ví dụ local và shared

Giả sử source of truth là database có latency 40 ms cho thao tác đọc điển hình.

- Local hit: 0,2 ms; local hit ratio đo được là 65%.
- Shared hit: 2,5 ms; shared hit ratio đo được là 90%.
- Khi miss, đường đi lookup cache rồi query DB; bỏ qua network jitter cho ví dụ.

Tính gần đúng:

~~~text
Local:  0,65 × 0,2 + 0,35 × (0,2 + 40)
      = 0,13 + 14,07 = 14,20 ms

Shared: 0,90 × 2,5 + 0,10 × (2,5 + 40)
      = 2,25 + 4,25 = 6,50 ms
~~~

Mặc dù mỗi local hit nhanh hơn, shared cache có thể có **trung bình toàn request** tốt hơn vì chia sẻ được nhiều hit hơn. Các tỷ lệ hit trong ví dụ là giả định; phải đo trên cùng workload mới so sánh có ý nghĩa.

Ngược lại, với một bảng tra cứu vài trăm key nằm sẵn trong mỗi Pod và rất ít thay đổi, local hit ratio gần 100% có thể giúp local thắng rõ rệt, đồng thời không cần vận hành Redis.

### Những chi phí dễ bỏ sót

- **Memory duplication:** số replicas × footprint local cache.
- **Network cost:** bytes và số request đến shared cache, cross-zone traffic.
- **Compute:** serialize/deserialize, nén, hash key, client pool, GC của JVM.
- **Operational:** HA, monitoring, patching, backup và on-call.
- **Cold start:** database bị spike khi nhiều Pod hoặc cache cluster restart.
- **Freshness failure:** hệ quả của việc trả dữ liệu cũ, có thể lớn hơn tiền tiết kiệm từ hit.

## 7. Tác động của scale-out và phân phối lưu lượng

Một local cache không “biết” rằng Pod khác đã tải cùng key. Khi nhân replicas từ 2 lên 20:

1. Tổng lượng RAM dành cho cache có thể tăng gần theo số Pod.
2. Cùng một hot key có thể tồn tại nhiều bản sao; hữu ích cho latency nhưng tốn bộ nhớ.
3. Nếu traffic được phân phối ngẫu nhiên, mỗi Pod cần đủ request để làm ấm tập key.
4. Một Pod mới có tỷ lệ miss cao trong giai đoạn khởi động.
5. Khi autoscaling đồng loạt, các Pod mới có thể cùng query DB cho những key giống nhau.
6. Các phiên bản code đang chạy song song có thể cache cùng key nhưng hiểu schema khác nhau.

**Session affinity/sticky routing** đôi khi cải thiện local hit ratio, nhưng có thể gây tải lệch, giảm khả năng chuyển failover và tạo coupling giữa việc phân phối request với caching. Không dùng sticky routing làm biện pháp duy nhất giải quyết cache consistency.

Shared cache giảm sự trùng lặp load, nhưng có thể gặp **hot shard** khi số replicas tăng. Trọng tâm chuyển từ memory ở từng app instance sang network, server CPU và hot-key distribution của cache cluster.

## 8. Cache key là một phần thiết kế dữ liệu

Key cần phản ánh chính xác dữ liệu được cache và các yếu tố làm thay đổi kết quả.

Ví dụ:

~~~text
catalog:v3:product:42
pricing:v2:region:vn:sku:ABC123
settings:v1:tenant:T42:feature:F01
inventory:v2:warehouse:W03:sku:ABC123
~~~

Một key tốt nên có:

- Namespace/prefix rõ để tránh đè giữa services.
- Schema hoặc logical version khi cấu trúc dữ liệu có thể thay đổi.
- Các biến ảnh hưởng đến kết quả: region, locale, currency, tenant, feature cohort.
- Độ dài được giới hạn, không chứa secret/PII thô.
- Giá trị canonical: chữ hoa/chữ thường, encoding và thứ tự tham số phải nhất quán.
- Quy tắc lifecycle: ai tạo, ai cập nhật, TTL bao lâu, lúc nào invalidated.

**Thiếu tenant trong key** có thể gây lộ dữ liệu chéo tenant. **Nhét toàn bộ URL có token vào key** có thể gây rò rỉ qua cache server metrics, command logs hoặc dumps. Nếu cần ID nhạy cảm trong key, phải thiết kế token hóa/định danh thay thế có kiểm soát, không mặc định hash thô là ẩn danh.

### Tách dữ liệu có mức độ tươi khác nhau

Không nên cache object “product page” gồm mô tả ít đổi, giá thay đổi vài lần một ngày và số tồn kho đổi từng giây với cùng một TTL dài. Có thể tách:

~~~text
catalog:product:42      -> tên, mô tả, hình ảnh    TTL dài hơn
pricing:sku:42          -> giá theo điều kiện     TTL trung bình
inventory:sku:42:W01    -> số lượng tồn kho       TTL rất ngắn/bypass
~~~

Đường xác nhận thanh toán hoặc chốt số lượng cần đọc và kiểm tra tại source of truth, transaction hoặc cơ chế consistency riêng. Cache hiển thị tồn kho không được trở thành cơ sở duy nhất quyết định bán vượt số lượng.

## 9. TTL, expiry, eviction và invalidation

Các từ này liên quan nhưng khác nhau:

- **TTL (time to live):** dữ liệu được coi là hợp lệ tối đa theo thời gian từ một mốc xác định, thường là lúc write.
- **Expire after write:** hết hạn kể từ lần ghi gần nhất.
- **Expire after access:** có thể kéo dài thời gian sống khi được truy cập, phù hợp một số workload nhưng có rủi ro giữ dữ liệu cũ nếu không có giới hạn freshness riêng.
- **Eviction:** loại bỏ key để giải phóng dung lượng vì chính sách kích thước, áp lực bộ nhớ hoặc thuật toán thay thế.
- **Invalidation:** chủ động xóa/vô hiệu hóa key khi sự kiện nghiệp vụ làm nó không còn hợp lệ.
- **Refresh:** nạp lại từ source of truth, có thể đồng bộ hoặc bất đồng bộ.

TTL là **giới hạn gần đúng đối với độ cũ**, không phải lời hứa dữ liệu luôn chính xác. Nếu cache đi qua nhiều tầng và TTL bắt đầu ở những thời điểm khác nhau, dữ liệu có thể cũ hơn dự kiến. Thêm random jitter cho TTL có thể chống hết hạn đồng loạt nhưng cần tính lại freshness bound.

### Khi nào chỉ TTL là đủ?

Có thể dùng TTL đơn giản nếu:

- Dữ liệu thay đổi ít và chấp nhận độ cũ.
- Nguồn dữ liệu có khả năng chịu các lần reload.
- Mọi consumer hiểu freshness contract.
- Trả dữ liệu cũ không tạo vi phạm bảo mật hoặc đúng đắn nghiệp vụ.
- Không cần xóa ngay khi user bị thu hồi quyền hoặc tài khoản bị khóa.

Ví dụ loại bỏ quyền truy cập đã bị thu hồi thường đòi hỏi cơ chế xác minh/invalidations nghiêm ngặt hơn. Cache authorization decisions với TTL dài có thể tiếp tục cho phép truy cập sau khi quyền bị xóa.

## 10. Các mẫu đọc/ghi phổ biến

### 10.1. Cache-aside (lazy loading)

Ứng dụng tự tra cache, nếu miss thì lấy dữ liệu gốc và đặt vào cache:

~~~text
read(key):
    value = cache.get(key)
    if value exists and valid:
        return value
    value = database.read(key)
    cache.set(key, value, ttl)
    return value
~~~

Ưu điểm: chỉ cache dữ liệu được dùng, dễ áp dụng local/shared. Hạn chế: miss phải đi qua source; dữ liệu có thể stale; một key nóng cùng miss tạo stampede. Cần thiết kế khi database trả về “không tồn tại”, timeout hoặc exception; đừng cache mọi lỗi như một response hợp lệ.

### 10.2. Write-through

Ứng dụng cập nhật source và cache trong luồng ghi theo một giao thức nhất quán được thiết kế. Tên “write-through” không tự làm hai hệ thống thành transaction nguyên tử. Cần phân tích nếu cache thành công nhưng database thất bại hoặc ngược lại.

### 10.3. Write-around

Chỉ cập nhật source of truth, rồi invalidates cache hoặc chờ TTL; phù hợp dữ liệu ghi nhiều nhưng ít đọc. Nếu bỏ qua invalidation, dữ liệu cũ có thể phục vụ trong suốt TTL.

### 10.4. Write-behind / write-back

Ghi cache trước và đồng bộ source sau. Có thể giảm write latency nhưng tăng nguy cơ mất dữ liệu nếu cache crash trước khi flush. Chỉ dùng khi đã có durability/replay, ordering, failure recovery và tính đúng đắn được thiết kế rõ; không sử dụng như một tối ưu hóa mặc định cho giao dịch tiền hoặc đơn hàng.

### 10.5. Read-through và refresh-ahead

Một thư viện hoặc cache service có thể thay ứng dụng thực hiện load khi miss. Refresh-ahead nạp lại trước khi hết hạn cho key nóng, giảm latency do miss nhưng có thể tạo nhiều tác vụ nền và load dữ liệu không còn được dùng. Phải giới hạn concurrency, xử lý lỗi và tránh refresh quá tải source.

## 11. Invalidation: khác biệt lớn nhất giữa local và shared

Giả sử Catalog Service cập nhật mô tả sản phẩm `42`:

~~~text
T0: Database product 42 = "Blue Shirt"
T1: Pod A cache = "Blue Shirt"
T1: Pod B cache = "Blue Shirt"
T2: Database product 42 đổi thành "Navy Shirt"
T3: Pod A nhận invalidation và xóa key
T4: Pod B chưa nhận event
T5: Request tới A -> "Navy Shirt"
T6: Request tới B -> "Blue Shirt"
~~~

Local cache cần cơ chế để tất cả Pod học về cập nhật:

- Chờ TTL hết hạn.
- Phát sự kiện invalidation qua broker/pub-sub.
- Dùng version/epoch chung để nhận biết entry cũ.
- Hoặc chấp nhận khác nhau tạm thời theo freshness contract.

Shared cache giúp việc xóa một key có tác dụng đối với nhiều client của cùng cache, nhưng vẫn có race giữa DB update và cache write. Ví dụ:

~~~text
T1 Reader R cache miss, đọc database phiên bản cũ V1
T2 Writer W ghi database phiên bản mới V2
T3 Writer W xóa cache key
T4 Reader R đặt V1 vào cache (do đọc trước lúc W ghi)
T5 Các request sau nhận V1 dù update đã hoàn thành
~~~

Đây là **stale repopulation race**. Xóa cache sau DB commit thường được dùng, nhưng không tự loại bỏ mọi race. Cách giảm rủi ro tùy yêu cầu:

- TTL giới hạn thời gian entry cũ tồn tại.
- Đưa version của bản ghi/schema vào key hoặc value.
- So sánh version khi ghi cache; không cho dữ liệu phiên bản cũ ghi đè mới.
- Dùng cache value gắn revision/etag từ source.
- Dùng event có thứ tự per key và xử lý update/invalidation có version.
- Với đường nghiệp vụ yêu cầu tính đúng đắn cao, đọc/validate lại source of truth trong transaction.

**Một lệnh `DEL` không phải cơ chế nhất quán mạnh xuyên database và cache.**

## 12. Pub/sub invalidation cho local cache

Một cách kết hợp là mỗi Pod giữ L1 local, còn một broker gửi invalidation:

~~~text
Product update
   |
   v
Database commit
   |
   v
Outbox / Event publisher
   |
   +--> Pod A: invalidate product:42
   +--> Pod B: invalidate product:42
   +--> Pod C: invalidate product:42
~~~

Các rủi ro:

- Pod đang restart/offline có thể bỏ lỡ event nếu dùng pub/sub không lưu bền.
- Event có thể đến trễ hoặc khác thứ tự theo partition.
- Hai phiên bản ứng dụng có thể dùng cache key/schema khác.
- Việc publisher thành công không bảo đảm mọi Pod đã xử lý.
- Một subscriber xử lý chậm có thể tiếp tục phục vụ dữ liệu cũ.
- Broker outage có thể khiến nhiều Pod mất tín hiệu invalidation.

Để nâng độ tin cậy, có thể kết hợp TTL, event có version, outbox, replay hoặc epoch/revision check theo khả năng hệ thống. Nếu yêu cầu dữ liệu **không được stale ngay sau revoke**, phải thiết kế kiểm tra quyền trên source/chính sách đặc biệt; không trông cậy thuần vào event eventual consistency.

## 13. Mô hình hai tầng: L1 local + L2 shared

Hai tầng kết hợp tốc độ local với khả năng chia sẻ của remote:

~~~text
            +------------------+
Request --->| App Pod          |
            |  L1 Local Cache  |
            +---------+--------+
                      | L1 miss
                      v
            +------------------+
            | L2 Shared Cache  |
            +---------+--------+
                      | L2 miss
                      v
            +------------------+
            |  Database/API    |
            +------------------+
~~~

Quy trình:

~~~text
get(key):
    v1 = L1.get(key)
    if L1 hit and still acceptable:
        return v1

    v2 = L2.get(key)
    if L2 hit:
        L1.set(key, v2, shortTTL)
        return v2

    v3 = source.load(key)
    L2.set(key, v3, longTTL)
    L1.set(key, v3, shortTTL)
    return v3
~~~

Ví dụ TTL: L1 5 giây, L2 60 giây. Đây chỉ là giả định để minh họa: với quyền truy cập, tồn kho hoặc giá nhạy cảm, TTL phải ngắn hơn hoặc bypass theo tính đúng đắn thực tế.

### Lợi ích

- Phần lớn hot reads phục vụ ở local nhanh nhất.
- Các Pod mới có thể lấy từ L2 thay vì đánh thẳng vào DB.
- L2 giảm trùng lặp khi cùng key xuất hiện trên nhiều Pod.
- Có thể dùng local stale fallback trong ngắn hạn nếu policy cho phép và L2 đang lỗi.

### Giá phải trả

- Dữ liệu có thể stale ở **cả L1 và L2**.
- Invalidation phải xử lý L2 và L1 đúng thứ tự/semantics.
- Có thêm bộ nhớ ở app và chi phí vận hành cache server.
- Khi L2 trả V2, Pod A có thể vẫn có V1 trong L1 cho đến khi hết TTL hoặc nhận invalidation.
- Metrics phải phân biệt L1 hit, L2 hit và source hit.
- Code và failure modes phức tạp hơn; không nên mặc định L1/L2 cho mọi service.

### Công thức độ trễ trung bình hai tầng

Đặt:

- `p1`: xác suất L1 hit.
- `p2`: xác suất L2 hit **khi đã L1 miss**.
- `t1`: thời gian lookup L1.
- `t2`: thời gian lookup L2 sau L1 miss.
- `to`: thời gian source lookup khi cả hai miss.

Khi các thời gian là giá trị trung bình ổn định, xấp xỉ:

~~~text
E[T] ≈ t1 + (1-p1) × t2 + (1-p1) × (1-p2) × to
~~~

Ví dụ `p1=0,70`, `p2=0,80`, `t1=0,2 ms`, `t2=3 ms` và `to=45 ms`:

~~~text
E[T] = 0,2 + 0,30×3 + 0,30×0,20×45
     = 0,2 + 0,9 + 2,7
     = 3,8 ms
~~~

Cả hai cache miss có xác suất `0,30×0,20=0,06`, nghĩa là khoảng 6% yêu cầu đọc tới origin theo mô hình này. Đây là **mean**, không phản ánh p99 hoặc queueing khi hàng nghìn request miss đồng thời.

## 14. Java: local cache bằng Caffeine

Caffeine là thư viện local cache phổ biến cho ứng dụng JVM. Ví dụ dưới đây mô tả cache-aside với maximum size và TTL:

~~~java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

import java.time.Duration;

public final class ProductLookupService {
    private final ProductRepository repository;

    private final Cache<String, ProductDto> cache =
            Caffeine.newBuilder()
                    .maximumSize(10_000)
                    .expireAfterWrite(Duration.ofMinutes(2))
                    .recordStats()
                    .build();

    public ProductLookupService(ProductRepository repository) {
        this.repository = repository;
    }

    public ProductDto findProduct(String productId) {
        String key = "product:" + productId;
        return cache.get(key, ignored ->
                repository.findProduct(productId));
    }

    public void onProductChanged(String productId) {
        cache.invalidate("product:" + productId);
    }

    public interface ProductRepository {
        ProductDto findProduct(String productId);
    }

    public record ProductDto(
            String id,
            String name,
            long priceInMinorUnit) {
    }
}
~~~

Đây là code minh họa; cần dependency Caffeine và xử lý null/missing product, exception và chính sách domain cụ thể. Loader của Caffeine có cơ chế phối hợp concurrent loads theo key trong một cache instance khi dùng API phù hợp, nhưng **không phối hợp qua những Pods khác nhau**.

Lưu ý:

1. `maximumSize(10_000)` giới hạn số entries xấp xỉ theo chính sách, không phải bytes. Một entry quá lớn có thể gây áp lực heap.
2. `expireAfterWrite` giới hạn tuổi từ lần ghi; không tự hiểu event cập nhật ở DB nếu không gọi invalidation.
3. `onProductChanged` chỉ xóa cache trong instance hiện tại. Cần broadcast/invalidation hoặc TTL nếu có nhiều instances.
4. Khi repository không tìm thấy sản phẩm, phải xác định cơ chế negative caching; tránh việc các request key không tồn tại liên tục đánh vào DB.
5. `recordStats()` cung cấp metric hữu ích nhưng cần xuất qua monitoring, không dùng log mọi key.
6. Không cache mutable object rồi cho caller tự sửa instance reference; cân nhắc immutable DTO như `record`.

Trong ứng dụng Spring Boot, Spring Cache có thể kết nối với Caffeine hoặc Redis thông qua các CacheManager phù hợp. Tuy nhiên, đặt annotation `@Cacheable` **không giải quyết tự động** bài toán tenant key, TTL đúng, invalidation giữa instances và consistency khi update.

## 15. Shared cache: cache-aside với Redis ở mức khái niệm

Một luồng shared cache thông thường:

~~~text
GET product:42
  |
  +--> Redis GET "catalog:v3:product:42"
         |
         +-- hit --> deserialize -> return
         |
         +-- miss --> repository.load(42)
                       |
                       v
                    serialize
                       |
                       v
                Redis SET key value EX 120
                       |
                       v
                     return
~~~

Pseudocode:

~~~java
ProductDto getProduct(String id) {
    String key = "catalog:v3:product:" + id;

    String raw;
    try {
        raw = redis.get(key);
    } catch (CacheUnavailableException error) {
        // Theo policy: truy vấn nguồn khi cache lỗi,
        // nhưng phải bảo vệ source khỏi bị quá tải.
        return repository.findProduct(id);
    }

    if (raw != null) {
        return deserializeValidated(raw);
    }

    ProductDto data = repository.findProduct(id);
    if (data != null) {
        try {
            redis.setWithTtl(key, serialize(data), Duration.ofSeconds(120));
        } catch (CacheUnavailableException ignored) {
            // Nguồn dữ liệu đã trả thành công.
            // Ghi metric lỗi cache, không biến read thành lỗi nếu policy cho phép.
        }
    }
    return data;
}
~~~

Các kiểu `CacheUnavailableException`, `redis`, `repository` và hàm serialize là abstractions giả định để minh họa, không phải mã compile độc lập. Trong implementation thật, cấu hình timeout, connection pooling, binary format, ACL, TLS, retries và circuit breaker theo cache client cụ thể.

**Không mặc định cache lỗi là “database trả không có dữ liệu”.** Chỉ negative cache khi origin xác nhận thật sự không tồn tại; timeout hoặc 5xx phải có đường xử lý khác.

### Nguyên tắc Redis key/value

- Prefix theo service và schema version.
- Không trộn user/tenant khi access scope khác nhau.
- TTL áp từ lúc đặt key; không vô tình reset TTL vô hạn khi cập nhật.
- Giới hạn kích thước value và thời gian serialize/deserialize.
- Dùng namespace/key rõ ràng để cleanup khi schema thay đổi.
- Không dùng lệnh xóa toàn bộ keys bừa bãi khi deploy hoặc invalidation.
- Kiểm soát độ tin cậy của failover/replication khi dữ liệu có yêu cầu consistency nhất định.

## 16. Cache stampede và thundering herd

Một key nóng `product:42` hết hạn đúng lúc 10.000 request đến trong vài giây. Nếu từng request miss rồi tự load DB, cache vô tình khuếch đại tải lên source:

~~~text
10.000 concurrent requests
          |
          v
cache miss product:42
          |
          +----> database query
          +----> database query
          +----> database query
          ...
          +----> database query
~~~

Hệ quả: database queue tăng, timeout, retries, cascading failure. Cần phối hợp ở từng lớp.

### 16.1. Single-flight per key tại local cache

Trong một Pod, chỉ một request nạp key tại một thời điểm; những request còn lại chờ hoặc dùng stale value hợp lệ. Caffeine `cache.get(key, mappingFunction)` thường hữu ích cho tính toán atomically per key trong cache instance, với điều kiện loader không gây deadlock hoặc blocking quá lâu.

Giới hạn: Pod A và B vẫn có thể đồng thời load cùng key; single-flight local không phải distributed coordination.

### 16.2. Thời gian hết hạn có jitter

Nếu 1 triệu keys cùng được nạp khi deploy và TTL đều 60 giây, chúng có thể hết hạn đồng loạt. Đặt TTL có biến thiên, ví dụ quanh 60 giây với jitter, giúp phân tán misses. Nhưng jitter phải được thiết kế để **không vượt freshness requirement**; không thêm ngẫu nhiên vô hạn cho dữ liệu cần cập nhật sớm.

### 16.3. Stale-while-revalidate

Với dữ liệu cho phép cũ tạm thời:

~~~text
Fresh:        trả ngay
Slight stale: trả bản cũ + kích hoạt một refresh nền
Too stale:    load source hoặc từ chối theo policy
~~~

Cần có **hard expiry** riêng để tránh phục vụ dữ liệu cũ vô hạn nếu refresh liên tục lỗi. Ví dụ UI catalog có thể dùng stale ngắn hạn, còn xác thực quyền hoặc giao dịch tài chính thì thường không phù hợp.

### 16.4. Giới hạn source load và distributed coordination

Với nhiều Pods, có thể dùng distributed lock/lease hoặc coordinator để chỉ ít request load source, nhưng phải xử lý expiry, node crash và chủ sở hữu lease. Nếu cache value là dữ liệu cần correctness, lock thuê ngắn không phải cơ chế giao dịch mạnh; đôi khi cần fencing token hoặc version check tại nơi ghi. Không dựa vào một distributed lock đơn giản để đảm bảo đúng đắn của thanh toán hoặc tồn kho.

Giảm concurrent misses bằng:

- Token bucket/rate limit cho source load.
- Timeout và retry budgets rõ.
- Warm-up có giới hạn concurrency.
- Request coalescing khi phù hợp.
- Trả fallback/stale có điều kiện cho dữ liệu cho phép.
- Load-shedding thay vì để cache outage kéo sập database.

## 17. Cache penetration và negative caching

**Cache penetration** xảy ra khi các request liên tục hỏi những key không có trong source, khiến lookup luôn miss. Ví dụ bot gọi hàng triệu `productId` giả.

Cách xử lý:

- Validate key sớm và áp rate limit tại edge/API.
- Negative cache kết quả “đã kiểm tra và không tồn tại” với TTL ngắn, có giới hạn.
- Không cache 401/403 hoặc policy denial sai ngữ cảnh rồi cho người khác dùng.
- Chỉ negative cache khi origin trả trạng thái xác định; không ghi cache cho timeout hay lỗi 5xx như “không tồn tại”.
- Với domain nhiều keys vô hiệu, kiểm tra giới hạn cardinality và bộ nhớ.
- Nếu dùng probabilistic filter/Bloom filter, hiểu khả năng false positive và quy trình cập nhật khi entity mới được tạo.

Negative caching phù hợp với product not found có thể không phù hợp với user profile vừa được tạo, đơn hàng đang chờ đồng bộ hoặc kết quả authorization dễ thay đổi. Ngữ nghĩa của “không tìm thấy” phải được xác định trước.

## 18. Hot key và phân phối tải

Một số sản phẩm, config hoặc token public có thể được tra nhiều hơn hàng triệu lần so với key khác.

**Local cache:** hot key được nhân bản lên mỗi Pod; đọc cực nhanh nhưng mỗi Pod chiếm bộ nhớ nhỏ và mỗi instance cần làm ấm.

**Shared cache:** tất cả Pod có thể dồn vào một key và một shard. Dù hit ratio cao, shared server/connection/network có thể trở thành bottleneck. Giải pháp có thể là L1 local cho hot keys, read replicas theo policy, request coalescing, CDN cho nội dung public hoặc phân tán reads theo topology phù hợp.

Không tùy tiện dùng random suffix cho hot key để “chia tải” nếu ứng dụng cần invalidation đúng hoặc cache entries có giá trị khác nhau. Việc nhân bản một key trong cache cluster phải đi cùng chính sách cập nhật/invalidation và đánh giá chi phí memory.

### Cache theo mức phù hợp

- **CDN/HTTP cache:** gần người dùng, phù hợp asset và responses public có cache-control hợp lệ.
- **Application local cache:** gần business code, phù hợp hot lookups an toàn.
- **Shared cache:** dùng lại giữa app instances hoặc services có owner rõ.
- **Database buffer cache:** được DB quản lý, không thay thế hoàn toàn app cache.
- **Precomputed/materialized views:** phù hợp truy vấn nặng có lịch cập nhật riêng.

Trước khi thêm Redis, kiểm tra xem HTTP cache/CDN hay tối ưu query/index có đáp ứng được mục tiêu đơn giản hơn không.

## 19. Khi shared cache bị lỗi thì điều gì xảy ra?

Lỗi Redis/shared cache không chỉ là “miss” thông thường. Nó có thể là timeout hàng giây, hết connection pool, failover, authentication errors hoặc một partition chậm.

~~~text
Normal:
App -> Redis hit -> Response

Cache degraded:
App -> Redis timeout -> Database fallback -> Response delayed

Cache outage + unbounded fallback:
Tất cả Pods -> Database -> overloaded -> timeouts -> retries -> outage lan rộng
~~~

Hệ thống cần quyết định **fail-open hay fail-closed** theo loại dữ liệu:

- Cache kết quả catalog public: thường có thể bypass và đọc DB nếu còn budget, hoặc trả stale trong giới hạn.
- Cache feature config không nhạy: có thể dùng bản local gần nhất trong thời gian ngắn nếu được thiết kế.
- Cache quyền truy cập: không được “fail-open” cho phép hành động chỉ vì cache authorization không truy cập được; cần nguồn xác minh đáng tin hoặc fail-closed.
- Cache dùng như session store/source of truth: outage có thể là failure thật, không thể giả vờ miss và trả nội dung mặc định.

### Bộ bảo vệ fallback

1. Timeout cache lookup ngắn và nằm trong request deadline.
2. Retry có giới hạn, không tạo retry storm lên Redis.
3. Circuit breaker phù hợp khi cache endpoint lỗi kéo dài.
4. Rate limit hoặc bulkhead trên số concurrent origin loads.
5. Phân biệt cache error với cache miss trong metric.
6. Stale fallback nếu business chấp nhận, có hard expiry.
7. Load shedding nếu DB không đủ capacity cho full traffic không cache.
8. Khi cache hồi phục, tránh mọi Pod warm-up cùng lúc.

Không nên thiết kế “Redis có HA nên không bao giờ lỗi”. HA giảm một số rủi ro nhưng failover thường vẫn có khoảng gián đoạn, network partition, replication lag và các trường hợp cấu hình sai.

## 20. Cách chọn consistency contract

Trước khi chọn local/shared, hãy viết yêu cầu rõ ràng:

| Dữ liệu | Gợi ý về freshness | Quyết định cache |
|---|---|---|
| Tên/mô tả sản phẩm public | Có thể chấp nhận cũ vài phút tùy business | Local hoặc shared, TTL + invalidation |
| Category/navigation tree | Thay đổi ít, nhiều reads | Local phù hợp; shared giúp warm nhanh khi nhiều replicas |
| Giá hiển thị | Có thể chấp nhận stale rất ngắn nhưng checkout cần revalidate | Shared/L1-L2 cho hiển thị, source để chốt |
| Tồn kho hiển thị | Thường thay đổi nhanh | TTL ngắn hoặc streaming updates; checkout phải dùng transaction/reservation |
| User permission/role | Revoke phải có hiệu lực theo chính sách | Không dùng TTL dài; kiểm tra quyền tại nguồn đáng tin ở thao tác nhạy cảm |
| Feature flag | Cần cập nhật theo cohort và default an toàn | Local SDK cache + refresh/event, thiết kế fallback |
| API rate-limit counters | Cần chia sẻ giữa replicas khi quota toàn cụm | Shared counter/coordination có semantics phù hợp |
| Session data | Cần chia sẻ giữa Pods nếu không stateless | Shared store với durability/consistency xác định |
| Kết quả ML recommendation | Có thể stale theo thời gian và model version | Cache theo model/cohort/tenant, TTL và version key |

Đây là gợi ý, không phải chính sách chung. Với luật/quy định, tài khoản tài chính hoặc dữ liệu nhạy cảm, thời gian stale chấp nhận có thể bằng 0 cho những điểm quyết định quan trọng. Khi đó cache chỉ nên dùng làm hint và phải xác nhận bằng nguồn đúng đắn.

### Session và rate-limiting là trường hợp đặc biệt

Một local cache không thể tự đảm bảo quota tổng trên 20 Pod. Nếu mỗi Pod cho phép 100 requests/phút, quota thực tế có thể tăng theo replicas. Distributed counter hoặc rate limiter tập trung giúp thực thi quota toàn cụm, nhưng cần xem atomicity, clock, failover và fallback policy. Đây là bài toán phối hợp trạng thái, không chỉ là tăng hit ratio.

## 21. Tính nhất quán khi cập nhật: thiết kế đường ghi

Giả sử Order Service đổi trạng thái đơn hàng:

~~~text
Order DB: status PENDING -> PAID
Cache:    order:123
~~~

Một cách phổ biến là cập nhật DB trong transaction, sau khi commit thành công thì invalidates cache. Nhưng:

- Nếu invalidation thất bại, entry cũ còn cho tới TTL.
- Nếu reader đã load bản cũ nhưng ghi vào cache sau lúc invalidation, stale có thể xuất hiện lại.
- Nếu publish invalidation trước DB commit, consumer có thể load trạng thái cũ.
- Nếu event bị lặp, handler phải idempotent.
- Nếu message đến sai thứ tự, event cũ không được xóa/ghi đè trạng thái mới theo semantics không mong muốn.

Với dữ liệu quan trọng, có thể dùng outbox phát sau commit, version/revision per entity, conditional write và TTL bounded. Dù vậy, **không thể giả định transactional consistency xuyên DB và Redis** nếu không có giao thức riêng. Quan trọng hơn là xác định thao tác nào được phép đọc stale và thao tác nào phải dùng nguồn chuẩn.

### Cache invalidation theo schema/version

Khi thay đổi serialization từ `ProductDto v2` sang `ProductDto v3`:

- Có thể đặt namespace key mới `catalog:v3:...` để code mới không deserialize nhầm dữ liệu cũ.
- Giữ key cũ hết TTL hoặc dọn theo một kế hoạch có kiểm soát.
- Không xóa hàng loạt cache chung của các service nếu chưa hiểu tác động.
- Tránh dùng cùng key với hai kiểu object không tương thích trong rolling rollout.

## 22. Chi phí bộ nhớ và chính sách eviction

Một local cache 100 MB trên 30 Pods cần khoảng 3 GB RAM cho các bản sao (bỏ qua overhead và độ chênh workload). Nếu Pod đã có heap chật, thêm local cache có thể làm tăng GC pause, OOM và chi phí replicas. Tuy nhiên, những bản sao này có thể giảm network và giảm tải shared cache ở những hot keys.

Shared cache lưu cùng tập dữ liệu tập trung hơn, nhưng còn overhead cho key, allocator, replication và persistence. Nếu cluster gồm primary/replica hoặc nhiều zones, tổng RAM vật lý có thể lớn hơn kích thước data logic nhiều lần.

### Giới hạn theo entry count hay weight?

`maximumSize(10_000)` của local cache không bảo đảm bytes nếu entry khác nhau nhiều về kích thước. Nên cân nhắc maximum weight và weigher thích hợp hoặc giới hạn kích thước payload trước cache. Với Redis, đặt memory budget, maxmemory policy và hiểu eviction/no-eviction semantics theo dữ liệu.

**Eviction không phải TTL.** Một entry hợp lệ có thể bị loại vì hết RAM; sau đó request phải load lại. Ngược lại, key hết TTL không nhất thiết lập tức trả lại memory cho hệ thống theo mọi implementation. Metrics cần theo dõi cả expiration và eviction.

## 23. Bảo mật và phân tách tenant

Cache có thể chứa dữ liệu nhạy cảm hơn dự kiến vì developer coi nó chỉ là “tạm thời”.

Nguyên tắc:

- Không dùng key dùng chung cho dữ liệu có kết quả phụ thuộc user/tenant nếu key không chứa phạm vi tương ứng.
- Không lưu bearer tokens, cookie hoặc password trong cache nếu không có lý do và mô hình bảo vệ rất rõ.
- Shared cache cần TLS/auth/ACL, network isolation và identity riêng theo service hoặc namespace.
- Local cache vẫn nằm trong process memory; heap dump, debug endpoint hoặc container compromise có thể làm lộ dữ liệu.
- Không đưa raw PII vào metric labels, cache key logs hay trace attributes.
- Thiết lập retention/TTL và quy trình purge khi yêu cầu xóa dữ liệu.
- Không tin cache là lớp kiểm tra authorization cuối cùng cho giao dịch nhạy cảm.
- Tách namespace/key và có owner dữ liệu; “cùng Redis cluster” không có nghĩa mọi service được đọc/sửa mọi key.

Mã hóa lưu trữ ở backend không thay thế việc giới hạn ai có quyền GET cache entry. Một cache nhầm tenant key có thể gây sự cố quyền riêng tư dù hệ thống dùng TLS.

## 24. Theo dõi cache bằng metric và trace

Các chỉ số nên có theo cache level:

| Metric | Ý nghĩa |
|---|---|
| `cache_requests_total{level,result}` | Số lần lookup và trạng thái hit/miss/error |
| `cache_hit_ratio` | Mức sử dụng cache, tính trên mẫu đủ lớn |
| `cache_load_duration` | Thời gian lấy source khi miss |
| `cache_lookup_duration` | Thời gian lookup local/remote, theo phân phối |
| `cache_evictions_total` | Entry bị loại do capacity/policy |
| `cache_expirations_total` | Entry hết hạn theo TTL |
| `cache_memory_used_bytes` | Memory đã dùng tại app/server cache |
| `cache_entry_count` | Số entries |
| `cache_fallback_total` | Số lần fallback vì cache lỗi |
| `cache_refresh_failures_total` | Số lần refresh thất bại |
| `cache_origin_loads_total` | Số lần query origin do miss |
| `cache_stale_served_total` | Số lần trả stale theo policy |
| `cache_client_timeouts_total` | Lookup remote timeout |
| `cache_hot_key_skew` | Mức lệch tải giữa keys/shards theo phương pháp tổng hợp an toàn |

Các tên metric là ví dụ, cần thống nhất naming convention. Không dùng user ID, raw key, email hay full URL làm metric label vì tạo cardinality cao và rủi ro riêng tư.

Trace có thể phân tách:

~~~text
HTTP GET /products/{id}
  |
  +-- L1 lookup (hit/miss, duration)
  |
  +-- L2 Redis GET (nếu L1 miss)
  |
  +-- DB SELECT (nếu cả hai miss)
~~~

Có thể không cần span cho mọi local lookup cực nhanh vì tạo telemetry overhead lớn. Chỉ instrument những bước có giá trị chẩn đoán, dùng metrics tổng hợp cho đường cực nóng. Không đưa toàn bộ cache value vào span attributes.

### Dấu hiệu cần xem lại kiến trúc

- Local hit ratio giảm mạnh sau khi scale replicas.
- L1 cache làm GC pause hoặc OOM tăng.
- Shared cache p99 tăng dù hit ratio tốt.
- Redis connection pool saturation và timeout tăng.
- DB load spike khi L1/L2 cùng hết hạn.
- Evictions tăng, working set vượt memory.
- Người dùng thấy dữ liệu khác nhau khi request được route tới Pod khác.
- Số lỗi sau rotation/invalidation tăng.
- Stale data gây vi phạm correctness hoặc mất doanh thu.

## 25. Kiểm thử các tình huống thường bị bỏ qua

| Kịch bản | Điều cần quan sát |
|---|---|
| L1 cold start | Số query DB/Redis tăng bao nhiêu khi Pod mới bắt đầu |
| Scale từ 2 lên 20 Pods | Local hit ratio, CPU, RAM và origin traffic |
| Cache key hot hết TTL cùng lúc | Có stampede không; maximum concurrent loads |
| Một bản ghi bị cập nhật | Bao lâu các Pods và L2 nhìn thấy bản mới |
| Event invalidation bị trễ hoặc mất | TTL/epoch có giới hạn staleness không |
| Redis timeout 1–2 giây | Request deadline, fallback load, circuit breaker |
| DB chậm khi cache outage | Có bảo vệ nguồn bằng bulkhead/rate limit không |
| L1 có schema cũ khi deploy version mới | Serialization/version namespace có an toàn không |
| Tenant A và B có cùng entity ID | Cache key có ngăn trả dữ liệu chéo tenant không |
| Entry không tồn tại bị hỏi liên tục | Negative caching/rate limit có hiệu quả không |
| Cache memory vượt budget | Evictions, OOM và performance |
| Rollout và rollback | Cache schema/TTL/invalidation tương thích giữa phiên bản |
| Các replica shared cache có lag | Đường đọc có đáp ứng freshness contract không |
| Xóa dữ liệu theo yêu cầu | Key local/shared và bản sao có thực sự hết hạn hoặc được purge không |

Test nên chạy với workload và topology đại diện: cùng số replicas, network latency, kích thước object, phân phối hot keys và tần suất cập nhật. Benchmark 100% hit trong một JVM không thể kết luận về shared cache trên cluster thật.

## 26. Quy trình lựa chọn dựa trên dữ liệu

**Bước 1 — Ghi SLO và correctness requirement.** Độ trễ p95/p99 nào cần giảm? Có dữ liệu nào không được stale? Nếu không cho phép stale, cache không thể dùng làm nguồn quyết định duy nhất.

**Bước 2 — Đo working set.** Có bao nhiêu keys thực sự được đọc mỗi phút? Phân phối truy cập, kích thước value, tần suất update và tỷ lệ reads/writes.

**Bước 3 — Đo origin.** Mỗi miss gây bao nhiêu latency/CPU/IO? DB có chịu được khi cache mất không?

**Bước 4 — Thử local cache nhỏ.** Với key ít đổi và traffic hot, đo hit ratio, p99 latency, heap/GC, cold start theo số replicas.

**Bước 5 — Thử shared cache nếu cần reuse.** Đo latency client→cache, network, failure rate, memory budget và impact khi các Pods share warm values.

**Bước 6 — Cân nhắc L1/L2 nếu cả hai có lợi.** Chọn TTL L1 ngắn hơn, versioning/invalidation rõ, đo số requests đến L2/origin.

**Bước 7 — Thiết kế failure policy.** Cache miss, cache timeout, DB timeout, stampede và stale fallback có hành vi khác nhau; không gộp thành một catch-all trả giá trị mặc định.

**Bước 8 — Kiểm thử consistency.** Update, delete, permission revoke, tenant boundary và rolling deploy phải có kịch bản.

**Bước 9 — Theo dõi production.** Ghi lại trước/sau về p95, p99, origin QPS, hit ratios, memory, chi phí và sự cố consistency.

**Bước 10 — Định kỳ đánh giá lại.** Khi workload, số replicas, schema hoặc SLO thay đổi, chiến lược cache tối ưu có thể đổi theo.

## 27. Bài tập: chọn cache cho Catalog, Pricing và Inventory

Giả sử hệ thống có:

~~~text
API Gateway
  |
  +--> Catalog Service: 24 Pods
  |        dữ liệu tên/mô tả hiếm khi đổi
  |
  +--> Pricing Service: 12 Pods
  |        giá theo khu vực, thay đổi vài lần mỗi ngày
  |
  +--> Inventory Service: 16 Pods
           số lượng thay đổi sau mỗi đơn hàng
~~~

Mục tiêu:

- Product listing p95 không vượt 120 ms.
- Cùng một người dùng không nên nhìn thấy giá quá cũ khi vào checkout.
- Tồn kho hiển thị có thể lệch nhẹ trong thời gian ngắn; xác nhận mua phải đúng transaction.
- Khi Redis lỗi, hệ thống không được đồng loạt làm database quá tải.
- Có quy trình triển khai phiên bản schema mới trong lúc Pods cũ vẫn chạy.

**Câu hỏi:**

1. Dữ liệu Catalog nên dùng local, shared hay L1/L2? Vì sao?
2. Key của Pricing cần chứa những yếu tố nào? TTL có thể giống Catalog không?
3. Inventory có nên dùng cache tại bước xác nhận giao dịch không?
4. Nếu 24 Catalog Pods cùng restart, làm sao tránh thundering herd?
5. Nếu update giá xong nhưng Pod A còn L1 cũ, chọn invalidation/TTL/version nào phù hợp?
6. Khi Redis timeout, làm sao ngăn fallback đồng loạt và đảm bảo request deadline?
7. Khi rollout đổi ProductDto schema, key version và reader cũ phải xử lý thế nào?
8. Nếu response phụ thuộc tenant, cache key và quyền truy cập cần thiết kế ra sao?

**Hướng phân tích:**

- Catalog ít đổi và rất hot: local có lợi về latency; nếu working set lớn/nhiều Pods, L1/L2 có thể giảm cold-start tải DB.
- Pricing cần region/currency/tenant hoặc các tham số thực sự ảnh hưởng giá trong key; checkout phải xác minh giá có hiệu lực từ hệ thống chủ.
- Inventory hiển thị có thể dùng TTL ngắn và invalidation, nhưng reserve/commit tồn kho phải dùng source of truth và đồng bộ đúng.
- Để tránh stampede: giới hạn warm-up, single-flight, jitter, shared L2, rate limit origin và stale fallback nếu cho phép.
- L1 stale cần hard TTL, invalidation event có version hoặc thay đổi key theo revision; không trông cậy delete shared cache sẽ tự xóa bản local.
- Redis timeout phải có timeout budget, circuit breaker, fallback được giới hạn và bảo vệ DB bằng bulkhead/load shedding.
- Đặt cache key schema version, giữ rolling compatibility và migration; không dùng chung key cho payload không tương thích.
- Tenant ID và quyền phải được xác minh; không lấy tenant từ input không tin cậy để xem dữ liệu của người khác.

## 28. Những sai lầm phổ biến

1. **Chọn local chỉ vì lookup nhanh:** bỏ qua cache miss khi scale và cold start.
2. **Chọn Redis cho mọi thứ:** thêm network dependency và chi phí dù bảng tra cứu nhỏ đã nằm trong RAM.
3. **Cho rằng shared cache tự đảm bảo nhất quán:** vẫn có race DB/cache, TTL, replication lag và thứ tự event.
4. **Chỉ xóa Redis khi update nhưng giữ L1 quá lâu:** Pod khác tiếp tục trả dữ liệu cũ.
5. **Dùng TTL vô hạn:** stale data có thể tồn tại lâu sau khi mất invalidation.
6. **Cache lỗi như “not found”:** timeout biến thành phản hồi 404 sai và negative cache sai.
7. **Không giới hạn kích thước local cache:** heap phình và GC/OOM.
8. **Đặt raw user ID/email trong metric labels hoặc key:** tăng cardinality và rò rỉ dữ liệu.
9. **Không có chống stampede:** một đợt cache miss làm database sụp.
10. **Tự retries vô hạn khi Redis lỗi:** làm latency và downstream QPS tăng.
11. **Dùng Redis lock đơn giản làm bảo đảm giao dịch:** lease expiry và failover vẫn có race; correctness cần cơ chế bền vững.
12. **Trộn schema versions trong cùng key:** deserialize lỗi khi rolling deploy.
13. **Đưa authorization vào local cache quá lâu:** revoke không có hiệu lực đúng thời gian yêu cầu.
14. **Coi hit ratio cao là mục tiêu duy nhất:** không đo p99 latency, stale correctness, chi phí và memory.
15. **Không tách dữ liệu có tần suất cập nhật khác nhau:** cache description và tồn kho chung TTL làm thay đổi sai.
16. **Cho rằng HA Redis không bao giờ downtime:** failover, partition và client timeouts phải có đường xử lý.
17. **Không kiểm tra tenant scope trong key:** có nguy cơ lộ dữ liệu giữa khách hàng.
18. **Tăng replicas mà không làm warm-up có kiểm soát:** origin gặp spike ngay lúc autoscaling.

## 29. Checklist thiết kế cho một quyết định cache

- [ ] Xác định source of truth và người sở hữu dữ liệu.
- [ ] Định nghĩa dữ liệu nào được cache và loại dữ liệu nào phải bypass.
- [ ] Ghi freshness contract, TTL/hard expiry và hành vi khi stale.
- [ ] Thiết kế key có schema version, tenant/region/context khi cần.
- [ ] Ước lượng working set, entry size, replicas và memory budget.
- [ ] Đo hit ratio theo từng tầng và theo các giai đoạn warm/cold.
- [ ] Đo p95/p99, source QPS, cache CPU/memory/network và chi phí.
- [ ] Có chống stampede, concurrency limit, timeout và retry budget.
- [ ] Có invalidation/versioning cho cập nhật, xóa và rollback.
- [ ] Phân biệt miss, error, stale và negative caching.
- [ ] Có đường ứng xử khi Redis/shared cache hỏng, bảo vệ origin.
- [ ] Có kiểm soát ACL/TLS/tenant isolation và không log secrets.
- [ ] Có test với nhiều replicas và sự kiện cập nhật đồng thời.
- [ ] Có kịch bản scale-out, restart, cache eviction và cold-start.
- [ ] Chứng minh cache cải thiện kết quả người dùng chứ không chỉ tăng một metric.

## 30. Kết luận

**Local cache** đổi memory bị nhân bản và chi phí invalidation xuyên Pods để lấy độ trễ hit cực thấp, giảm network và có thể giảm phụ thuộc hạ tầng. **Shared cache** đổi một network hop cùng chi phí HA/vận hành để lấy khả năng chia sẻ dữ liệu giữa instances, quản lý dung lượng tập trung và giảm cold miss toàn cụm. **L1/L2** kết hợp ưu điểm nhưng phải xử lý hai tầng stale state, nhiều failure modes và monitoring phức tạp hơn.

Lựa chọn đúng phụ thuộc vào **working set, số replicas, tốc độ cập nhật, tính nhất quán nghiệp vụ, SLO và khả năng chịu sự cố**. Đừng dùng cache để thay thế tính đúng đắn của database hay authorization: xác định nơi được phép stale, đo trên workload thật, và thiết kế đường fallback đủ an toàn để cache cải thiện hiệu năng mà không trở thành nguyên nhân của sự cố diện rộng.
