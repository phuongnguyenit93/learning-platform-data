# Đánh giá nhu cầu phân mảnh, replication và cache cục bộ

Trong một hệ thống sử dụng **Spring Data Redis**, Redis thường được đặt giữa ứng dụng Java và database để giảm độ trễ đọc, giới hạn số truy vấn tới nguồn dữ liệu và hỗ trợ các cấu trúc dữ liệu cần truy cập nhanh. Khi tải tăng, ba lựa chọn thường được đặt lên bàn:

1. **Phân mảnh dữ liệu (sharding):** chia không gian key và tải xử lý sang nhiều Redis primary, thường bằng Redis Cluster.
2. **Replication:** duy trì replica của primary để tăng khả năng sẵn sàng, phục hồi và trong một số trường hợp phân tải đọc.
3. **Cache cục bộ (local/L1 cache):** giữ một phần dữ liệu ngay trong JVM của từng instance, ví dụ Caffeine, để không cần round-trip tới Redis cho các key được đọc nhiều.

Ba kỹ thuật này **giải quyết những nút thắt khác nhau**. Sharding tăng khả năng phân bổ dữ liệu và tải ghi trên nhiều primary; replication tạo thêm bản sao nhưng không tự chia tải ghi; local cache giảm số lần ứng dụng cần gọi Redis nhưng đổi lại làm tăng bộ nhớ của mỗi instance và rủi ro dữ liệu cũ.

Bài học tập trung vào **cách đánh giá khi nào cần mỗi giải pháp**, cách đo hiệu năng và chi phí, các ranh giới consistency, ví dụ tích hợp Spring Data Redis và quy trình thử nghiệm trước khi đưa thay đổi vào production.

## 1. Bắt đầu từ câu hỏi: hệ thống đang chậm ở đâu?

Không nên quyết định chuyển sang Redis Cluster chỉ vì số request HTTP tăng. Trước tiên phải xác định nút thắt thực sự.

Một request đọc có thể đi qua:

```text
Browser / API client
         |
         v
Load balancer
         |
         v
Spring Boot instance
         |
         +----> L1 cache trong JVM (nếu có)
         |           |
         |        Hit? -> trả ngay
         |
         +----> Spring Data Redis
         |           |
         |        Redis GET
         |           |
         |        Hit? -> trả dữ liệu
         |
         +----> Database / nguồn sự thật
                     |
                     v
              Trả kết quả và nạp cache
```

Độ trễ một request còn phụ thuộc:

- Thời gian tạo connection, TLS, network RTT giữa ứng dụng và Redis.
- Số lệnh Redis thực sự được gọi cho một request.
- Serialization/deserialization JSON hoặc JDK serialization.
- CPU và memory của Redis primary, độ dài command, big key/hot key.
- Tải CPU, thread pool, event loop và connection của ứng dụng Java.
- Tỷ lệ cache hit/miss, thời gian truy vấn database khi miss.
- Timeout, retry, failover hoặc GC.
- Số lượng instance và cách request phân bố vào các instance.

Một request chậm vì SQL query kém hoặc code Java deserialize object quá lớn **không nhất thiết được cải thiện bằng thêm Redis replica**. Ngược lại, nếu Redis đang quá tải network/CPU bởi hàng triệu `GET` cho một tập nhỏ key, thêm một lớp cache cục bộ có thể giúp nhiều hơn việc chia key sang nhiều shard.

### Bảng nhận diện triệu chứng

| Triệu chứng nổi bật | Nghi ngờ cần kiểm tra | Giải pháp có thể phù hợp |
|---|---|---|
| Redis primary gần đầy RAM và số key còn tăng | Working set lớn, TTL/eviction chưa phù hợp | Dọn dữ liệu, tối ưu key/value, rồi cân nhắc sharding |
| Redis primary CPU cao dù nhiều cache hit | QPS lệnh cao, big key, Lua/script, hot key | Tối ưu command; sharding nếu tải trải trên nhiều key; L1 nếu read hot |
| Network RTT app–Redis lớn, mỗi request nhiều round-trip | Topology mạng, số lệnh, vị trí Redis | Gom lệnh/pipeline phù hợp; L1 cho dữ liệu đọc lặp |
| Database tăng tải khi Redis miss | Hit rate thấp, TTL ngắn, cache stampede | Thiết kế cache key/TTL, request coalescing, warming |
| Muốn chịu lỗi primary | Availability và failover | Replication/Sentinel hoặc Redis Cluster HA |
| Nhiều GET, ít ghi, replica có khả năng phục vụ đọc | Primary read bottleneck | Read replicas khi chấp nhận eventual consistency |
| Một key cực nóng, nhiều request cùng một key | Hot key tập trung vào một slot | L1, request coalescing, giảm payload; shard thông thường chưa chắc giúp |
| Latency chỉ tăng khi deploy/GC ứng dụng | JVM, thread pool, cold start | Tối ưu ứng dụng; không vội đổi Redis topology |

**Nguyên tắc:** chọn biện pháp dựa trên **metric cho thấy nút thắt**, không dựa trên số lượng kỹ thuật hiện có trong kiến trúc.

## 2. Thiết lập baseline trước khi thay đổi

Một baseline tối thiểu nên thu thập trong giờ bình thường lẫn giờ cao điểm:

| Nhóm | Metric | Ý nghĩa |
|---|---|---|
| HTTP | QPS, lỗi, p50/p95/p99 latency | Trải nghiệm người dùng |
| Redis | GET/SET/DEL/EVAL ops/s | Loại và tần suất lệnh |
| Redis | Command latency, slowlog | Node có bị chặn bởi lệnh chậm không |
| Redis | CPU, memory, fragmentation, eviction | Nút thắt tài nguyên |
| Redis | Network ingress/egress | Giới hạn truyền dữ liệu |
| App | Connection pool, timeout, retry | Chi phí chờ Redis |
| Cache | Hit/miss theo cache name | Redis giúp tiết kiệm bao nhiêu truy vấn |
| Payload | Kích thước key/value trung bình và tail | Big key, network và serialization |
| DB | QPS, connection utilization, p95 query | Khả năng chịu tải lúc cache miss |
| HA | Replica lag, reconnect, failover time | Độ tin cậy khi thay đổi topology |

Ví dụ Redis CLI cho môi trường được phép quan sát:

```bash
redis-cli INFO stats
redis-cli INFO commandstats
redis-cli INFO memory
redis-cli INFO clients
redis-cli INFO replication
redis-cli SLOWLOG GET 10
```

Lưu ý:

- `SLOWLOG` đo thời gian xử lý lệnh trong Redis, **không** bao gồm toàn bộ thời gian mạng, chờ connection và deserialization phía Java.
- `INFO` của một Redis node không đại diện toàn bộ Redis Cluster.
- Metric theo thời gian mới phản ánh peak; một lần `INFO` vào lúc nhàn rỗi không đủ để quyết định.
- Không dùng `KEYS *` hoặc `MONITOR` kéo dài trên production chỉ để thu thập số liệu.

### Phân biệt throughput và latency

Redis có thể xử lý nhiều command/giây nhưng p99 vẫn tăng nếu có lệnh tốn thời gian, network congestion hoặc burst traffic. Cần nhìn cả **số lệnh thành công mỗi giây** lẫn **phân bố thời gian đáp ứng**.

Với workload nhiều request song song, một phép kiểm tra hữu ích là định luật Little:

```text
Số tác vụ đang xử lý trung bình
    ≈ throughput (tác vụ/giây) × thời gian hoàn tất trung bình (giây)
```

Nếu hệ thống phục vụ 10.000 request/s, trung bình mỗi request giữ một tài nguyên 20 ms, số tác vụ đồng thời tương ứng vào khoảng 200. Đây là công cụ ước lượng capacity, không phải bảo đảm Redis sẽ đáp ứng đúng con số đó khi có burst hoặc tail latency.

## 3. Ba phương án giải quyết ba loại bài toán

```text
Nhu cầu hiệu năng và sẵn sàng
             |
   +---------+----------+
   |         |          |
   v         v          v
Sharding  Replication  Local cache
   |         |          |
   v         v          v
Chia key  Bản sao /     Giảm GET từ
và tải    failover /    ứng dụng tới Redis
ghi       đọc stale
   |         |          |
   +---------+----------+
             |
             v
   Xác định consistency,
   vận hành, chi phí, test
```

### Ma trận so sánh

| Tiêu chí | Sharding / Redis Cluster | Replication | Cache cục bộ |
|---|---|---|---|
| Tăng tổng dung lượng dữ liệu | Có, chia dữ liệu theo primary | Không, replica sao chép cùng dữ liệu | Chỉ cache subset trên mỗi JVM |
| Phân tán write load | Có nếu nhiều key phân bố slot | Không tự tăng năng lực ghi của một primary | Không giải quyết write load |
| Phân tán read load | Có giữa các primary; có thể thêm replica | Có thể nếu định tuyến đọc sang replica | Có, khi hit L1 |
| Tăng khả năng sẵn sàng | Cần thiết kế replica/failover per shard | Mục đích chính | L1 chỉ che một số lỗi đọc, không thay Redis HA |
| Giảm network RTT tới Redis | Không nhất thiết | Không nhất thiết | Có khi hit local |
| Rủi ro stale data | Do nhiều key/reshard/routing, replica nếu dùng | Replica lag | L1 trên mỗi instance có thể cũ |
| Giới hạn multi-key/transaction | Hash slot / cross-slot | Vẫn phụ thuộc primary | Phải tự đồng bộ với Redis/DB |
| Chi phí vận hành | Topology/reshard phức tạp | Memory/replication/failover | Memory JVM/invalidation/cold start |
| Dùng hợp lý khi | Một primary không còn đủ CPU/RAM/throughput phân bố | Cần HA hoặc đọc scale chấp nhận stale | Dữ liệu đọc lặp cao, TTL/stale chấp nhận được |

Không có quy tắc rằng phải triển khai cả ba. Một hệ thống có thể chỉ cần Redis Standalone + replica; một hệ thống khác dùng Redis Cluster nhưng không cần L1; hệ thống chỉ có ít dữ liệu tra cứu tĩnh có thể hưởng lợi từ L1 mà không cần cluster.

## 4. Phân mảnh dữ liệu là gì?

**Sharding** chia tập key thành nhiều phần được quản lý bởi những Redis primary khác nhau. Với **Redis Cluster**, không gian khóa được chia thành **16.384 hash slot**; mỗi primary quản lý một tập slot.

```text
                 Spring Boot clients
                         |
                         v
                Lettuce Cluster client
                         |
       +-----------------+-----------------+
       |                 |                 |
       v                 v                 v
    Primary A         Primary B         Primary C
   slots 0..5000    slots 5001..11000  slots 11001..16383
       |                 |                 |
    Replica A         Replica B         Replica C
```

Các khoảng slot chỉ là ví dụ. Trong thực tế, slot được phân bổ theo topology của Redis Cluster và có thể được di chuyển khi mở rộng hoặc cân bằng lại.

Ứng dụng không tự chọn một primary cố định cho mỗi key. Client cluster-aware như Lettuce tính slot từ tên key, tìm node sở hữu slot và xử lý chuyển hướng theo cơ chế cluster.

### Khi sharding thực sự hữu ích

Sharding đáng cân nhắc khi:

- **Một Redis primary không còn đủ memory** cho working set và không thể đơn giản giảm dữ liệu, TTL hoặc dung lượng value.
- **Tổng tải đọc/ghi trải trên nhiều key** làm một primary bão hòa CPU hoặc network.
- Cần tăng khả năng mở rộng ngang bằng cách bổ sung primary rồi phân bố lại slot.
- Tải được thiết kế để các aggregate/tenant/key nằm trên nhiều slot thay vì tập trung vào một slot duy nhất.

Ví dụ ước lượng (không phải benchmark):

```text
Working set Redis: 90 GiB
Một primary đáp ứng an toàn: khoảng 35 GiB usable memory
Yêu cầu headroom: đã tính vào usable memory
Kết luận: cần nhiều primary hoặc giảm working set
```

Nếu chia dữ liệu tương đối đều trên 3 primary, trung bình khoảng 30 GiB/primary. Nhưng còn phải tính **replication, fragmentation, overhead index, big key, skew và thời gian reshard**. Không dùng phép chia đều lý tưởng làm kết luận capacity cuối cùng.

### Sharding không sửa hot key

Nếu 40% request GET đều nhắm vào cùng `config:global`, key đó nằm ở **một slot** và thường được một primary phục vụ. Thêm nhiều primary không tự chia một key nóng sang nhiều node.

Phương án có thể phù hợp hơn:

- L1 local cache với TTL phù hợp.
- Giảm kích thước payload.
- Tránh gọi GET lặp trong cùng HTTP request.
- Request coalescing/single-flight khi cache miss.
- Thiết kế dữ liệu có thể partition nếu ngữ nghĩa cho phép.
- Cân nhắc replication read scaling khi chấp nhận consistency.

Chỉ “chia tên key” thành nhiều bản sao để đọc có thể làm invalidation và consistency phức tạp; cần được đo và thiết kế riêng.

## 5. Redis Cluster: slot, hash tag và tác động tới Spring Data Redis

Redis Cluster xác định slot của một key từ key bytes theo quy tắc hash. Các key có cùng **hash tag** sẽ được đặt vào cùng slot.

```text
cart:{user-42}:items
cart:{user-42}:total
cart:{user-42}:version
```

Ba key trên dùng phần `{user-42}` để tính slot, hỗ trợ những thao tác nhiều key cần cùng slot.

Ngược lại:

```text
cart:user-42:items
cart:user-42:total
```

không có bảo đảm cùng slot dù trông giống chung một user.

### 5.1. Multi-key và CROSSSLOT

Một số lệnh như `MGET`, `MSET`, Lua script nhiều khóa hoặc transaction `MULTI`/`EXEC` phải tuân thủ giới hạn slot/topology. Nếu các khóa ở nhiều slot, Redis có thể từ chối bằng `CROSSSLOT`, hoặc một số API client có thể tách thao tác thành nhiều lệnh độc lập khi hỗ trợ.

**Tách thao tác client-side không tạo tính nguyên tử toàn cluster.**

Ví dụ:

```text
Primary A: order:{42}:status
Primary B: stock:{sku-1}:available

SET status thành công trên A
DECRBY stock lỗi trên B

=> Có thể xảy ra trạng thái một phần
```

Với những bất biến cần atomicity, nên đưa các key thật sự liên quan về cùng slot khi kiến trúc cho phép, hoặc giữ transaction authoritative ở database/nguồn phù hợp.

### 5.2. Tránh hash tag quá rộng

Không đặt tất cả key vào `{global}` chỉ để các multi-key command chạy:

```text
product:{global}:1
product:{global}:2
user:{global}:100
order:{global}:500
```

Khi đó phần lớn dữ liệu tập trung vào một slot và một primary, làm mất lợi ích sharding. Hash tag nên tương ứng **aggregate cần thao tác nguyên tử**, không phải toàn bộ hệ thống.

### 5.3. Serializer ảnh hưởng key vật lý

`StringRedisTemplate` dùng key serializer chuỗi. Một `RedisTemplate` với key serializer khác có thể tạo byte key khác, dẫn đến hash slot khác. Không tự tính slot từ Java String rồi bỏ qua serializer thực tế.

Khi chuyển từ Standalone sang Cluster, cần kiểm tra rằng namespace, serializer, key pattern và các Lua/multi-key operations thực sự tương thích.

## 6. Cấu hình Spring Data Redis kết nối Redis Cluster

Với Spring Boot sử dụng Lettuce, cấu hình có thể như sau:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-1.example.internal:6379
          - redis-2.example.internal:6379
          - redis-3.example.internal:6379
        max-redirects: 5
      timeout: 2s
```

Đây là ví dụ cấu hình, không phải địa chỉ server thật. Các node đóng vai trò **seed nodes**; driver khám phá topology và có thể kết nối nhiều node khác được Redis Cluster quảng bá.

Các điểm cần xác minh trong production:

- Tất cả địa chỉ node mà cluster quảng bá đều truy cập được từ mạng ứng dụng.
- TLS và ACL/credentials phù hợp.
- Lettuce cluster topology refresh đáp ứng thay đổi node, `MOVED`/`ASK` và failover.
- Application không hardcode IP primary cho từng key.
- Redis CacheManager, template và script executor cùng trỏ tới deployment mong muốn.
- Connection timeout, command timeout và retry budget có chủ đích.
- Read preference replica chỉ bật khi nghiệp vụ chấp nhận stale.

Đối với lệnh theo một key, `RedisTemplate` thường đủ; driver tự định tuyến theo slot. `RedisClusterConnection` cần thiết hơn cho chức năng tra cứu node/slot, quét từng primary và quản trị cụm.

### Đừng đặt kỳ vọng rằng sharding tự giảm latency

Một lệnh GET một-key trước và sau khi chuyển sang Cluster vẫn cần network round-trip và deserialize. Cluster có thể cải thiện tail latency **nếu primary cũ quá tải**, nhưng cũng có thể thêm redirect, topology overhead và số connection.

Vì vậy, hãy so sánh benchmark cùng workload và cùng điều kiện mạng. Lợi ích chính của sharding là **capacity/throughput scale-out**, không phải bảo đảm mọi lệnh đơn sẽ nhanh hơn.

## 7. Đánh giá khả năng phân bố tải và hot slots

Dữ liệu thường không phân bố hoàn toàn đều. Một tenant lớn, một chương trình khuyến mại hoặc một key dashboard có thể tạo hot slot.

Ví dụ:

```text
Primary A: 30% tổng key, 70% GET QPS
Primary B: 35% tổng key, 15% GET QPS
Primary C: 35% tổng key, 15% GET QPS
```

Dù memory phân bố tương đối đều, primary A vẫn có thể nghẽn CPU/network.

Những câu hỏi cần đo:

1. Các key có kích thước value khác biệt lớn không?
2. Một số key có QPS đọc quá cao so với phần còn lại không?
3. Tỷ lệ lệnh phức tạp như `ZRANGE` trên tập lớn hoặc Lua dài có tập trung trên một shard không?
4. Hash tag có làm tất cả dữ liệu của một tenant lớn dồn vào một slot không?
5. Có cluster-wide scan hoặc batch job tạo tải bất thường tại một node không?
6. Có lệnh `MGET` nhiều key bị tách/scatter khiến tổng số command tăng không?

Sharding có ý nghĩa khi có thể **phân bố cả dữ liệu lẫn tải**, không chỉ tăng số node trên sơ đồ.

### 7.1. Big key không tự biến mất

Một Redis Hash có hàng triệu field vẫn là **một key** và nằm trên một slot. Chia cluster thành nhiều primary không chia nội dung của key đó.

Nếu cần, thiết kế lại key:

```text
user-events:{user-42}:2026-01
user-events:{user-42}:2026-02
...
```

Nhưng việc đổi key cần xét truy vấn, retention và atomicity; đặt cùng hash tag `{user-42}` vẫn gom chúng vào cùng slot. Muốn phân tán theo tháng hoặc bucket, hash tag phải được thiết kế lại theo ranh giới nhất quán được phép.

### 7.2. Reshard cũng cần capacity dự phòng

Trong giai đoạn chuyển slot, Redis có thể chịu thêm network và I/O; client nhận redirect; cache miss hoặc retry tăng. Khi sizing Cluster, ngoài tải bình thường phải chừa headroom cho:

- Failover/mất một node.
- Resharding/migrating keys.
- Replication catch-up.
- Peak traffic trong lúc rolling deployment.
- Rebalancing khi xuất hiện hot slots.

## 8. Replication: bản sao giải quyết vấn đề gì?

**Redis replication** sao chép dữ liệu từ một primary sang một hoặc nhiều replica. Mục tiêu thường gồm:

- Tăng khả năng phục hồi khi primary gặp lỗi.
- Cho phép Sentinel hoặc Redis Cluster lựa chọn replica để promote theo cấu hình.
- Phục vụ một phần **read traffic** trên replica nếu consistency policy cho phép.
- Tách một số truy vấn đọc/reporting khỏi primary.

```text
               Spring Data Redis
                       |
                 Write to primary
                       |
                       v
                    Primary
                       |
            Async replication
                 /         \
                v           v
            Replica A    Replica B
                |           |
       Read traffic?   Read traffic?
        (nếu bật)        (nếu bật)
```

Replicas **sao chép cùng tập dữ liệu**. Nếu working set 40 GiB trên primary, thêm hai replica không làm primary chỉ giữ 13,3 GiB. Mỗi bản sao cần đủ memory và tài nguyên tương ứng.

Replication cũng không tự phân tải **write**: lệnh ghi vẫn đi tới primary chủ quản; replication còn tạo thêm network và công việc đồng bộ.

### 8.1. Replication không đồng nghĩa đồng bộ tuyệt đối

Redis replication thông thường là **bất đồng bộ**. Một ghi thành công trên primary có thể chưa xuất hiện trên replica ngay tại thời điểm client đọc.

```text
T0: App A SET order:42 PAID trên primary
T1: Primary trả thành công
T2: App B GET order:42 từ replica chưa bắt kịp
T3: Replica trả trạng thái PENDING
T4: Replica nhận bản cập nhật và trả PAID
```

Nếu dùng replica để đọc, ứng dụng phải **chấp nhận eventual consistency** hoặc thiết kế đường đọc authoritative cho những nghiệp vụ không được stale.

### 8.2. Read-your-writes không được bảo đảm mặc định

Trong Reactor hay Java đồng bộ:

```java
redis.opsForValue()
        .set("order:42:status", "PAID");

String state = redis.opsForValue()
        .get("order:42:status");
```

Lời gọi theo thứ tự ở client không đủ để bảo đảm `GET` đọc đúng giá trị vừa ghi nếu đường đọc định tuyến tới replica và replica còn lag.

Những lựa chọn:

- Đọc từ **primary** với thao tác yêu cầu độ mới.
- Dùng kết quả của lệnh ghi/script làm response khi phù hợp.
- Dùng version trong dữ liệu và kiểm tra mốc tối thiểu cần đọc.
- Dùng chính sách retry đọc có giới hạn nếu stale được phát hiện, không retry vô tận.
- Không bật replica reads cho những quyết định bảo mật/tiền/tồn kho nếu chưa có hợp đồng consistency đúng.

## 9. Sentinel, Redis Cluster HA và số replica

Hai mô hình thường gặp:

### 9.1. Standalone primary + replicas + Sentinel

```text
                 Application
                      |
               Sentinel discovery
                      |
                      v
                   Primary
                  /       \
                 v         v
             Replica A  Replica B

Primary lỗi
    |
    v
Sentinel chọn một replica làm primary mới
```

Sentinel giúp giám sát và điều phối failover, không tự phân mảnh keyspace thành nhiều primary chứa những tập key khác nhau.

### 9.2. Redis Cluster với replica mỗi shard

```text
                 Redis Cluster
          +------------+------------+
          |            |            |
       Primary A    Primary B    Primary C
          |            |            |
       Replica A    Replica B    Replica C
```

Cluster chia key theo slot giữa các primary; replica của mỗi primary giữ bản sao shard tương ứng. Đây là kết hợp **sharding và replication**.

Tăng primary giúp scale-out một tập lệnh/working set; tăng replica giúp mỗi shard có thêm phương án failover hoặc phục vụ đọc nếu bật. Số replica và phân bố AZ/host cần dựa trên yêu cầu availability, không chỉ số node tối thiểu.

### 9.3. Failover có thể gây mất hoặc lặp tác động

Redis không cung cấp cam kết rằng mọi ghi được primary xác nhận đều đã tới replica trước failover. Khi một primary chết sau khi phản hồi write nhưng replica chưa sao chép xong, dữ liệu mới có thể không còn trên primary được promote.

Ngoài ra, timeout mạng có thể khiến client không chắc `INCR` đã chạy chưa. Retry một lệnh có side effect không idempotent có thể làm nó chạy hai lần.

Vì vậy, replication giúp HA nhưng **không tạo exactly-once business semantics hoặc durability tuyệt đối**. Với dữ liệu cần bảo đảm mạnh, cần nguồn giao dịch phù hợp và quy trình idempotency/reconciliation.

## 10. Replication và khả năng mở rộng đọc: đánh đổi consistency

Nếu primary nhận quá nhiều `GET` trên nhiều key, có thể thử chuyển một phần đọc sang replicas.

Ví dụ tải:

```text
Primary:
    60.000 GET/s
    4.000 writes/s

Thêm replicas:
    Chuyển một phần GET sang replica
    Primary vẫn chịu phần lớn writes
```

Lợi ích chỉ xuất hiện nếu:

1. Driver/client thực sự định tuyến một phần đọc sang replica.
2. Replica có đủ CPU, memory và network.
3. Ứng dụng chấp nhận dữ liệu cũ theo độ trễ replication đo được.
4. Tốc độ ghi và replication traffic không làm primary bão hòa hơn.
5. Failover/reconnect/read preference được kiểm thử.

**Thêm replica nhưng mọi GET vẫn trỏ về primary sẽ không tăng read throughput** theo mục tiêu phân tải. Cần kiểm chứng bằng per-node command metrics.

### 10.1. Lettuce read preference

Lettuce cung cấp lựa chọn đọc từ primary/replica theo cấu hình client. Ví dụ định hướng ở nơi ứng dụng tự cấu hình `LettuceClientConfiguration`:

```java
import io.lettuce.core.ReadFrom;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;

LettuceClientConfiguration clientConfig =
        LettuceClientConfiguration.builder()
                .readFrom(ReadFrom.REPLICA_PREFERRED)
                .build();
```

Đây là **một phần cấu hình client**, chưa phải cấu hình factory đầy đủ. Ứng dụng cần tạo `LettuceConnectionFactory` với Redis topology và client configuration phù hợp; các mode Standalone/Sentinel/Cluster có cách discovery replica khác nhau. Không mặc định chỉ thêm `ReadFrom.REPLICA_PREFERRED` là đủ để đọc replica trong mọi deployment.

Nếu dùng Spring Boot auto-configuration, cần phối hợp cấu hình theo phiên bản Boot/Lettuce và tránh tạo bean connection factory trùng.

### 10.2. WAIT và giới hạn durability

Redis có lệnh `WAIT` để yêu cầu chờ một số replica xác nhận đã nhận các write trước đó từ connection tương ứng. Nó có thể giảm một số rủi ro replication lag đối với một chuỗi thao tác, nhưng **không biến Redis replication thành transaction đồng bộ tuyệt đối hoặc bảo đảm dữ liệu sẽ sống sót qua mọi failover/persistence failure**.

Không dùng `WAIT` như lời hứa “đã commit bền tuyệt đối”; cần kiểm tra timeout, số replica thực sự đáp ứng và các điều kiện failover/persistence.

### 10.3. Những dữ liệu không nên đọc stale

Những đường đọc cần cân nhắc đặc biệt:

- Session đăng nhập và session revocation.
- Permission/role vừa bị thu hồi.
- Idempotency keys, nonce và anti-replay tokens.
- Distributed lock state.
- Số dư, quota, tồn kho dùng để quyết định ghi.
- Trạng thái nghiệp vụ ngay sau khi commit.

Dùng read replica cho dashboard, catalog hoặc số liệu có độ trễ cho phép thường dễ hơn so với dùng cho quyết định truy cập nhạy cảm.

## 11. Cache cục bộ: L1 trước Redis L2

**Local cache** là cache nằm trong memory của chính instance Java. Ví dụ phổ biến là Caffeine.

```text
                   HTTP request
                        |
                        v
                Spring Boot instance
                        |
                        v
                 L1 Caffeine
                 /          \
              HIT           MISS
               |             |
               v             v
           Return          L2 Redis
                           /      \
                        HIT       MISS
                         |          |
                         v          v
                     Populate L1   Database
                                    |
                                    v
                              Populate L2 + L1
```

L1 có thể cho độ trễ rất thấp do không cần network round-trip. Redis vẫn là L2 chia sẻ giữa các instance; database là nguồn authoritative nếu Redis chỉ làm cache.

Nhưng L1 khiến mỗi instance có **bản sao riêng**:

```text
App A: L1 product:42 = version 5
App B: L1 product:42 = version 5
App C: L1 product:42 = version 5

Database/Redis được cập nhật version 6.

Nếu không có invalidation phù hợp:
App A/B/C vẫn có thể phục vụ version 5 đến khi L1 hết TTL.
```

Vì vậy, L1 không chỉ là tối ưu hiệu năng: nó bổ sung **một tầng consistency** phải được quản lý.

## 12. Đánh giá lợi ích L1 bằng hit rate

Giả sử hệ thống có:

- Tổng số đọc phù hợp cache: 20.000 request/giây.
- L1 hit rate: 80%.
- Với các request đã miss L1, Redis L2 hit rate: 90%.
- Giả định một request phát sinh tối đa một cache lookup trong ví dụ đơn giản.

Số lần Redis GET ước lượng:

```text
Redis GET/s = 20.000 × (1 - 0,80)
            = 4.000 GET/s
```

Số lần đọc database do miss cả hai tầng:

```text
DB reads/s = 20.000 × (1 - 0,80) × (1 - 0,90)
           = 400 reads/s
```

Ở đây **L2 hit rate là tỷ lệ có điều kiện trên những request đã miss L1**. Không cộng thẳng 80% + 90% thành 170% hit.

Trước khi có L1, giả sử Redis hit rate vẫn 90% trên toàn bộ 20.000 request/giây, database có thể nhận khoảng 2.000 reads/s. Nhưng thêm L1 cũng có thể thay đổi phân bố key được Redis nhìn thấy và thời gian TTL, nên **không mặc định L2 hit rate sẽ giữ nguyên**. Các con số là phép tính minh họa để lập kế hoạch benchmark.

### 12.1. L1 có lợi nhất khi nào?

- Dữ liệu được nhiều request trên **cùng instance** đọc lặp lại.
- Chi phí serialize/network tới Redis đáng kể so với local lookup.
- Value nhỏ, có giới hạn memory rõ ràng.
- Dữ liệu ít thay đổi hoặc chấp nhận stale tối đa bằng TTL.
- Có chiến lược invalidation khi cần độ mới tốt hơn TTL.
- Có khả năng đo hit/miss theo từng tầng, không chỉ tỷ lệ cache tổng hợp.

Nếu traffic trải đều trên hàng triệu key được đọc một lần, L1 hit rate có thể thấp. Caffeine khi đó chỉ chiếm memory và tăng GC, không mang lại nhiều lợi ích.

### 12.2. Cache cục bộ không chỉ có một instance

Nếu có 20 ứng dụng Java, mỗi instance cache tối đa 200 MiB, tổng L1 cache tiềm năng có thể đạt khoảng 4 GiB trên fleet (chưa tính overhead/khác biệt thực tế). Đây là memory **phân tán theo app**, không phải một tập dùng chung để tăng dung lượng Redis.

Nếu một key nóng xuất hiện ở tất cả instance, nó có thể có 20 bản sao. Điều này giảm Redis reads, nhưng phải chấp nhận chi phí invalidation và nhiều bản stale cùng lúc.

## 13. Ví dụ Caffeine L1 + Spring Data Redis L2

Ví dụ dùng **Spring Boot + Caffeine + StringRedisTemplate** với cache-aside cho catalog sản phẩm. Database là nguồn sự thật. Caffeine giữ một subset nhỏ, Redis giữ bản cache chia sẻ giữa nhiều instance.

Dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
```

Trong ứng dụng WebFlux reactive, không gọi `StringRedisTemplate` blocking trực tiếp trên event-loop; ví dụ dưới đây dành cho ứng dụng Java/Spring MVC đồng bộ. Với reactive stack cần `ReactiveRedisTemplate` và thiết kế cache interaction tương ứng.

### 13.1. Model và nguồn dữ liệu

```java
public record ProductView(
        String id,
        String name,
        long priceInCents,
        long version) {
}
```

```java
import java.util.Optional;

public interface ProductSource {
    Optional<ProductView> findById(String productId);
}
```

`version` là version nghiệp vụ do nguồn dữ liệu quản lý, không phải Redis TTL hoặc thời gian local lookup. Nó hữu ích khi cần phát hiện và tránh ghi đè snapshot cũ bằng bản mới.

### 13.2. Khai báo L1 với giới hạn memory

```java
import java.time.Duration;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ProductLocalCacheConfiguration {

    @Bean
    Cache<String, ProductView> localProductCache() {
        return Caffeine.newBuilder()
                .maximumSize(10_000)
                .expireAfterWrite(Duration.ofSeconds(10))
                .recordStats()
                .build();
    }
}
```

`maximumSize(10_000)` giới hạn theo **số entry**, không cam kết số byte cố định. Nếu một value lớn hơn hàng trăm lần value khác, có thể cân nhắc `maximumWeight` và `weigher` phù hợp. Cần đo heap footprint và GC dưới workload thật.

`expireAfterWrite(10s)` cho phép tối đa khoảng thời gian giữ một entry kể từ lần ghi local theo chính sách Caffeine. Không tự coi đó là cam kết chính xác từng nanosecond hoặc độ mới end-to-end: một snapshot có thể đã cũ từ trước khi được nạp vào L1 nếu L2 stale.

### 13.3. Service đọc theo L1 → L2 → nguồn

```java
import java.time.Duration;
import java.util.Optional;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.benmanes.caffeine.cache.Cache;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductReadService {

    private static final Logger log =
            LoggerFactory.getLogger(ProductReadService.class);

    private static final Duration REDIS_TTL =
            Duration.ofMinutes(5);

    private final Cache<String, ProductView> l1;
    private final StringRedisTemplate redis;
    private final ProductSource source;
    private final ObjectMapper mapper;

    public ProductReadService(
            Cache<String, ProductView> localProductCache,
            StringRedisTemplate redis,
            ProductSource source,
            ObjectMapper mapper) {

        this.l1 = localProductCache;
        this.redis = redis;
        this.source = source;
        this.mapper = mapper;
    }

    public Optional<ProductView> findById(String id) {
        ProductView local = l1.getIfPresent(id);
        if (local != null) {
            return Optional.of(local);
        }

        String key = redisKey(id);

        try {
            String json = redis.opsForValue().get(key);

            if (json != null) {
                ProductView fromRedis =
                        mapper.readValue(json, ProductView.class);

                if (fromRedis == null) {
                    throw new IllegalStateException(
                            "Unexpected null cache payload");
                }

                l1.put(id, fromRedis);
                return Optional.of(fromRedis);
            }
        } catch (DataAccessException redisError) {
            // Redis lỗi không được tính như MISS bình thường.
            log.warn("Redis product cache unavailable", redisError);
        } catch (JsonProcessingException invalidPayload) {
            // Đây là lỗi schema/cache payload, không phải key miss.
            log.warn("Invalid cached product JSON", invalidPayload);
        }

        Optional<ProductView> authoritative = source.findById(id);

        authoritative.ifPresent(product -> {
            try {
                String json = mapper.writeValueAsString(product);
                redis.opsForValue().set(key, json, REDIS_TTL);
            } catch (DataAccessException | JsonProcessingException error) {
                // Cache chỉ là tối ưu; caller vẫn nhận được dữ liệu nguồn.
                log.warn("Unable to refresh product Redis cache", error);
            }

            l1.put(id, product);
        });

        return authoritative;
    }

    public void evictLocal(String productId) {
        l1.invalidate(productId);
    }

    public String redisKey(String productId) {
        return "cache:product:v1:" + productId;
    }
}
```

Bài học từ ví dụ:

- L1 hit không chạm Redis.
- L1 miss và L2 hit đọc Redis rồi nạp L1.
- L1/L2 miss đọc nguồn.
- Lỗi Redis được ghi nhận riêng, không bị gộp vào cache miss.
- Khi nguồn không có sản phẩm, ví dụ không cache giá trị âm tính.
- TTL L1 (10 giây) ngắn hơn TTL L2 (5 phút); đây là cấu hình minh họa, phải điều chỉnh theo độ mới dữ liệu.
- Việc update/invalidate khi nguồn thay đổi cần một đường riêng, chưa có trong read service.
- Khi nhiều request đồng thời miss cùng key, code trên vẫn có thể gây cache stampede; production cần coalescing hoặc loading-cache policy nếu tải lớn.

**Đây là cache-aside với eventual consistency**, không phù hợp trực tiếp cho số dư, kiểm soát quyền hoặc dữ liệu cần đọc mới nhất ở mọi request.

## 14. Vấn đề consistency khi có L1 trên nhiều instance

Giả sử sản phẩm `p-42` vừa được cập nhật từ version 5 lên 6:

```text
DB:     Product version 6
Redis:  Product version 6
App A L1: version 5
App B L1: version 5
App C L1: version 6
```

Nếu chỉ cập nhật Redis và không xử lý L1, A và B có thể trả dữ liệu cũ đến khi TTL hết. Việc L2 đã đúng không buộc L1 tự cập nhật.

Có ba chiến lược phổ biến:

1. **TTL-only**: chấp nhận stale tối đa theo chính sách TTL và dữ liệu được nạp.
2. **Explicit invalidation**: khi nguồn thay đổi, phát sự kiện để các instance xóa L1 theo key.
3. **Version/validation**: kèm version, đọc hoặc so khớp với nguồn có thẩm quyền ở các điểm cần độ mới.

Trong thực tế có thể kết hợp cả ba để giảm rủi ro.

### 14.1. TTL-only: đơn giản nhưng phải định nghĩa stale budget

Ví dụ:

```text
L1 TTL = 10 giây
L2 TTL = 5 phút
Source update tại T0
```

Nếu chỉ có TTL mà không invalidate L2, một L1 mới được nạp từ L2 cũ gần thời điểm L2 hết hạn có thể tiếp tục giữ dữ liệu cũ thêm thời gian L1 TTL. Vì vậy, **độ cũ end-to-end không chỉ bằng TTL L1**.

Cần xác định đường nào làm mới L2, khi nào source được đọc lại và liệu một request có thể nạp dữ liệu cũ từ L2 sau khi L1 hết hạn không.

Nếu yêu cầu “không bao giờ trả quyền cũ sau khi revoke”, TTL-only thường không đủ.

### 14.2. Invalidation qua Redis Pub/Sub

Một cách tối ưu phản ứng nhanh:

```text
Product service cập nhật DB thành công
                 |
                 v
Xóa/ghi lại L2 Redis theo policy
                 |
                 v
PUBLISH product.changed: p-42, version 6
                 |
       +---------+---------+
       |         |         |
       v         v         v
     App A     App B     App C
    evict L1  evict L1  evict L1
```

Spring Data Redis có `RedisMessageListenerContainer` để đăng ký kênh. Mỗi instance nhận notification rồi `l1.invalidate(productId)`.

**Nhưng Redis Pub/Sub không lưu thông điệp cho subscriber offline.** Một instance đang deploy hoặc đứt kết nối có thể bỏ lỡ invalidation. Vì vậy, Pub/Sub chỉ nên là **tối ưu độ trễ invalidation**, đi kèm TTL hoặc đường reconcile/version nếu sự kiện bắt buộc được ghi nhận.

Không dùng Pub/Sub làm nguồn duy nhất để đảm bảo mọi session permission hoặc dữ liệu tài chính được revoke tức thì.

### 14.3. Ví dụ listener invalidate L1

```java
import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class ProductInvalidationListenerConfig {

    @Bean
    MessageListener productInvalidationListener(
            ProductReadService products) {

        return (message, pattern) -> {
            String productId = new String(
                    message.getBody(), StandardCharsets.UTF_8);
            products.evictLocal(productId);
        };
    }

    @Bean
    RedisMessageListenerContainer productInvalidationContainer(
            RedisConnectionFactory connectionFactory,
            MessageListener productInvalidationListener) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.addMessageListener(
                productInvalidationListener,
                new ChannelTopic("product.cache.invalidate.v1"));
        return container;
    }
}
```

Đây là ví dụ minh họa. Trong production, payload nên được version hóa và có scope như tenant, product ID, version và event ID nếu cần. Không nhận identifier tùy tiện rồi xóa mọi key trên một prefix không kiểm soát.

### 14.4. Thứ tự update DB, L2 và thông báo

Trình tự sai có thể tạo stale cache:

```text
T0: Publish invalidation
T1: App A xóa L1, ngay lập tức đọc L2 cũ
T2: App A lại nạp version 5 vào L1
T3: Database commit version 6
```

Vì vậy, đường invalidate thường phải **theo sau commit nguồn**; L2 cũng phải được xử lý phù hợp. Tuy nhiên, giữa DB commit và Redis evict/publish vẫn có khoảng lỗi **dual-write**.

Nếu không được phép bỏ lỡ invalidation, dùng transactional outbox hoặc sự kiện bền để worker phát và retry, kèm TTL/version như đường an toàn. Đừng coi một lời gọi `convertAndSend(...)` thành công là xác nhận mọi JVM đã invalidate: số subscriber Redis trả về không phải ACK xử lý.

## 15. Race condition giữa cache fill và invalidation

Ngay cả khi có Pub/Sub, một tình huống cạnh tranh có thể xảy ra:

```text
T0: App A đọc L2 version 5, chuẩn bị put vào L1
T1: DB cập nhật version 6
T2: Invalidation tới App A, xóa L1
T3: App A put version 5 vào L1 sau khi đã invalidate
```

Dữ liệu cũ bị **đưa trở lại** dù invalidation đã được phát thành công.

Các biện pháp tùy yêu cầu:

- Version trong payload và điều kiện chỉ chấp nhận version mới hơn.
- Coalescing/coordination theo key đối với read-fills.
- Không put bản cache cũ nếu local minimum-version watermark đã cao hơn.
- TTL ngắn như giới hạn độ cũ trong trường hợp race.
- Dùng nguồn authoritative đối với thao tác cần consistency chặt.
- Tránh lưu trạng thái ứng dụng bất biến bảo mật chỉ trong L1.

Một hệ thống chỉ invalidation theo Pub/Sub mà không có version hoặc reconciliation có thể vẫn phục vụ stale sau race; vấn đề không chỉ là listener có nhận notification hay không.

## 16. Negative caching và cache stampede

Khi một key không có trong L1 và L2, nhiều request đồng thời có thể cùng đọc database:

```text
1.000 requests cùng hỏi product p-404
             |
             v
L1 miss trên nhiều instance
             |
             v
L2 miss
             |
             v
1.000 database reads nếu không có coalescing
```

Để giảm tải:

- **Single-flight/request coalescing** trong cùng JVM theo key.
- Lock/lease có giới hạn ở Redis nếu thật sự cần coordination phân tán.
- **Negative caching** với TTL ngắn cho kết quả không tồn tại đã được nguồn xác nhận.
- TTL jitter để tránh nhiều key hết hạn cùng thời điểm.
- Refresh-ahead hoặc stale-while-revalidate khi chấp nhận dữ liệu cũ trong thời gian ngắn.
- Concurrency limit và bulkhead bảo vệ database.

Cần phân biệt:

- **Cache miss**: Redis đã xác nhận không có entry.
- **Negative cache hit**: Redis có entry biểu diễn “nguồn không có đối tượng”.
- **Redis access error**: không thể đọc Redis; không được tự gán “không có đối tượng”.

Khi L1 chứa negative entry, một sản phẩm mới tạo có thể tiếp tục bị trả “not found” đến hết TTL nếu không có invalidation. Thời gian negative TTL phải tương ứng khả năng dữ liệu xuất hiện mới.

## 17. Local cache và memory/GC trong JVM

L1 không miễn phí. Nếu value lớn, `maximumSize` tính theo số entry có thể chưa đủ để bảo vệ heap.

Ví dụ:

```text
10.000 entries
× 8 KiB trung bình/payload
≈ 80 MiB payload trước overhead Java object và cache metadata
```

Đây chỉ là phép tính payload; overhead thực tế có thể lớn do chuỗi, object graph, metadata và fragmentation. Với 30 JVM replica, tập cache lặp lại có thể tiêu thụ đáng kể memory toàn hệ thống.

Các điểm cần giám sát:

- Heap used và GC pause p99.
- Caffeine estimatedSize, eviction, hit/miss, load duration.
- Phân bố kích thước value, không chỉ trung bình.
- Memory khi cold start rồi warm-up nhanh.
- Số cache entry lặp trên nhiều JVM.
- Ảnh hưởng của L1 đến autoscaling và mức memory request/limit ở Kubernetes.

Nếu local cache làm JVM bị OOM hoặc tăng GC pause, p99 HTTP có thể **xấu hơn** dù Redis GET giảm.

### 17.1. Không lưu mutable entity thiếu kiểm soát trong L1

Nếu một thread nhận object cached rồi sửa trực tiếp:

```java
ProductView product = cache.getIfPresent(id);
// Tránh mutate object được chia sẻ nếu đó là mutable class.
```

các request khác cùng JVM có thể thấy trạng thái không mong muốn. Ưu tiên DTO immutable/record, copy-on-write hoặc mapping riêng cho response.

Caffeine cung cấp caching thread-safe ở cấu trúc, nhưng không tự biến object mutable của ứng dụng thành immutable.

## 18. Cache coherence trong kiến trúc nhiều tầng

Mô hình hai tầng có thể được nhìn theo ba nguồn:

```text
Database = nguồn authoritative
    |
    v
Redis L2 = bản sao dùng chung, TTL dài hơn
    |
    v
Caffeine L1 = bản sao trên từng instance, TTL ngắn hơn
```

Mục tiêu consistency có thể là:

- **Eventual consistency với stale budget**: cho phép dữ liệu cũ trong tối đa khoảng thời gian đã thỏa thuận.
- **Read-your-writes cho người vừa cập nhật**: sau thao tác update, chính caller cần thấy bản mới.
- **Monotonic reads**: sau khi thấy version mới, không thấy version cũ hơn.
- **Strong consistency ở điểm quyết định**: kiểm tra trực tiếp nguồn authoritative/transaction phù hợp.

Một TTL L1 10 giây chỉ tạo một giới hạn đơn giản cho entry local, không đồng nghĩa tự đảm bảo cả bốn tính chất trên.

### 18.1. Version là công cụ để tránh đi lùi

Ví dụ giá trị cached:

```json
{
  "id": "p-42",
  "priceInCents": 450000,
  "version": 107
}
```

Nếu instance đã thấy version 107, việc lấy lại version 106 từ replica/L2 cũ không nên ghi đè lên cache có version mới hơn.

Có thể lưu min-observed-version cho một số key hoặc yêu cầu database khi độ mới quan trọng. Nhưng phiên bản phải do nguồn có thẩm quyền cấp theo quy tắc đơn điệu; không dùng timestamp JVM không đồng bộ như version mạnh một cách tùy tiện.

### 18.2. TTL không thay thế event invalidation

- TTL giúp giới hạn thời gian giữ dữ liệu trong trường hợp mất notification.
- Invalidation giúp giảm thời gian stale sau update.
- Version/validation giúp tránh áp dụng bản cũ sau một race.
- Outbox/reconciliation giúp xử lý event bị mất hoặc xử lý sai thứ tự.

Mỗi cơ chế giải một phần khác nhau, nên phải chọn theo SLO của nghiệp vụ.

## 19. Chọn cache strategy theo loại dữ liệu

| Loại dữ liệu | Local cache | Redis replica read | Sharding | Điều kiện đáng chú ý |
|---|---|---|---|---|
| Feature flags ít đổi, có version | Thường phù hợp | Có thể | Chỉ khi dữ liệu/tải lớn | Cần invalidation hoặc refresh chính sách |
| Catalog sản phẩm | Phù hợp cho hot keys | Có thể nếu stale chấp nhận | Khi working set/tải lớn | TTL, giá/khuyến mại, invalidation |
| Giá hiển thị chưa chốt giao dịch | Có thể | Có thể | Tùy tải | Đừng dùng giá cached cũ để tính tiền cuối |
| Dashboard metrics | Có thể | Phù hợp khi chấp nhận lag | Khi dữ liệu lớn | Độ trễ hiển thị được công bố |
| Session đăng nhập | Thận trọng | Rất thận trọng | Có thể khi nhiều session | Revoke và consistency bảo mật |
| Role/permission có thể revoke tức thì | Thường không nên chỉ dựa L1 | Không nên đọc stale | Tùy dữ liệu | Nguồn authoritative và revoke policy |
| Số dư/tồn kho quyết định giao dịch | Không dùng L1 làm nguồn quyết định | Không dùng stale replica | Có thể bố trí cùng slot theo aggregate | Atomic command/Lua/database transaction |
| Idempotency/nonce | Thường không | Không đọc stale | Có thể theo slot | Cần tính đúng khi retry/failover |
| Dữ liệu tính toán tốn CPU, có thể tái tạo | Rất phù hợp nếu hit cao | Không bắt buộc | Tùy kích thước | Coalescing và bounded memory |

Bảng là gợi ý kiến trúc, không phải lệnh cấm tuyệt đối. Nếu một hệ thống có cơ chế consistency và invalidation đặc biệt, vẫn có thể dùng L1 cho dữ liệu nhạy cảm; phải chứng minh bằng test và threat model, không chỉ dựa vào cache hit rate.

## 20. Kết hợp sharding, replication và L1

Một kiến trúc lớn có thể sử dụng cả ba:

```text
                       API Clients
                            |
                        Load Balancer
                            |
             +--------------+--------------+
             |              |              |
             v              v              v
           App A          App B          App C
         Caffeine L1    Caffeine L1    Caffeine L1
             |              |              |
             +--------------+--------------+
                            |
                     Spring Data Redis
                            |
                     Lettuce Cluster
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
           Primary 1     Primary 2     Primary 3
              |             |             |
           Replica 1     Replica 2     Replica 3
                            |
                  Miss/fallback to DB
                            |
                            v
                     Authoritative DB
```

Cách này hữu ích khi:

- L1 gánh phần lớn hot-read traffic.
- Redis Cluster giữ working set lớn và phân tán phần còn lại.
- Replica giúp HA, và có thể phục vụ các read cho phép stale.
- Database không còn bị gọi với tần suất cao trong điều kiện bình thường.

Đổi lại, có nhiều chiều failure:

- L1 stale sau khi bỏ lỡ invalidation.
- Redis shard mất kết nối.
- Replica lag hoặc bị promote trong failover.
- Redis timeout gây bão fallback vào database.
- Reshard làm redirect/latency tăng.
- Một bản cập nhật nguồn chưa kịp xóa L2 hoặc gửi invalidation.
- Schema cached giữa hai bản ứng dụng không tương thích.

Kiến trúc nhiều tầng chỉ tốt hơn khi **lợi ích measured vượt chi phí vận hành và consistency**. Với một ứng dụng nhỏ, thêm ba tầng có thể tạo nhiều lỗi hơn mức latency tiết kiệm được.

## 21. Lựa chọn cấu hình cache qua Spring Cache abstraction

Spring Cache có thể tích hợp provider như Redis hoặc Caffeine thông qua `CacheManager`. Nhưng mặc định, khai báo hai cache manager không tự biến chúng thành một **hierarchical L1→L2 cache có đồng bộ hai chiều**.

Ví dụ:

```java
@Cacheable(cacheNames = "products", key = "#id")
public ProductView findProduct(String id) {
    return source.findById(id).orElse(null);
}
```

Annotation này sử dụng cache manager mà Spring chọn theo cấu hình. Nó không tự đảm bảo:

1. Đọc Caffeine trước rồi Redis sau.
2. L1 miss được nạp từ L2 hit.
3. L2 và L1 cùng evict đúng lúc.
4. Cross-instance invalidation thành công.
5. Lỗi Redis được phân loại riêng với local miss.

Để có hai tầng thật sự, cần một **composite/tiered cache implementation** được thiết kế đúng contract hoặc một service cache-aside rõ ràng như ví dụ trên.

### 21.1. Không giả định @CacheEvict xóa mọi L1 của các instance

`@CacheEvict` thường tác động vào cache manager/provider đang được sử dụng trong instance gọi. Nếu đó là Caffeine local cache, nó **không tự xóa cache trên các JVM còn lại**.

Nếu hệ thống cần invalidation toàn fleet:

- Phát event tới các instance sau commit.
- Có đường TTL/reconcile khi event bị bỏ lỡ.
- Có version để tránh stale-fill race.
- Giữ tên cache/prefix thống nhất qua các deployment.
- Test multiple instances chứ không chỉ một instance.

### 21.2. Không dùng local cache cho đối tượng có danh tính theo user mà thiếu key scope

Một cache key `product:42` có thể ổn cho catalog public. Nhưng nếu kết quả phụ thuộc tenant, locale, price list hoặc permission, key phải bao gồm các chiều đó theo contract:

```text
product:{tenant-7}:42:locale=vi-VN:priceList=retail
```

Không dùng L1 toàn cục trên instance cho dữ liệu người dùng khi key chỉ có `id` nhưng thiếu tenant/user scope; điều đó có thể trả dữ liệu của người này cho người khác.

Bên cạnh hiệu năng, **cache key correctness là vấn đề bảo mật**.

## 22. Tối ưu trước khi thêm node

Có những cải tiến rẻ hơn sharding/replica/local cache:

### 22.1. Giảm số round-trip

Nếu một request đọc năm field cùng một Redis Hash bằng năm `HGET` riêng, có thể cân nhắc `HMGET` hoặc `HGETALL` khi payload hợp lý. Với nhiều command độc lập, pipelining có thể giảm round-trip, nhưng **không tạo transaction**.

Không dùng `HGETALL` cho hash quá lớn nếu chỉ cần vài field. Một lệnh trả payload lớn có thể tệ hơn nhiều lệnh nhỏ được gom hợp lý.

### 22.2. Chọn cấu trúc dữ liệu và kích thước value

- Tránh lưu object graph không cần thiết.
- Dùng serialization compact có version.
- Đừng lưu mọi thuộc tính vào một big key.
- Đặt TTL theo đặc tính dữ liệu.
- Giảm duplicate data/namespace không còn dùng.
- Cân nhắc compression chỉ khi lợi ích network vượt chi phí CPU encode/decode.

### 22.3. Chặn cache stampede

Khi nhiều request cùng miss một hot key, nạp nguồn một lần theo key hoặc giới hạn concurrency. Nếu không, sharding Redis có thể vẫn không cứu database.

### 22.4. Giảm tải lệnh O(N)

Tránh những thao tác quét toàn bộ keyspace trong request, script Lua dài và thao tác collection lớn. Dùng `SCAN` theo lô cho maintenance và đo tác động trên từng node.

### 22.5. Đặt Redis gần ứng dụng theo latency budget

Nếu app và Redis khác vùng địa lý/AZ, RTT có thể chi phối latency GET ngắn. Đổi vị trí hạ tầng hoặc L1 có thể hiệu quả hơn tăng CPU Redis. Tuy nhiên, cần cân nhắc availability zone failure domain và chi phí mạng, không chỉ tối ưu độ trễ tối thiểu.

## 23. Phương pháp benchmark trước khi quyết định

Một benchmark tốt so sánh **cùng tập dữ liệu, cùng luồng request và cùng tiêu chí thành công** giữa các phương án.

### 23.1. Tập workload đại diện

Chuẩn bị:

- Tập key có kích thước và phân bố thật: hot/warm/cold.
- Tỷ lệ đọc/ghi, ví dụ 95/5 hoặc 80/20 theo dữ liệu thực.
- Payload percentile: P50, P95, P99.
- TTL distribution và thời điểm hết hạn đồng loạt.
- Kịch bản tăng đột biến traffic.
- Nhiều instance đồng thời, không chỉ một benchmark client.
- Kết nối TLS, latency mạng và topology tương tự production.
- Failover/cold start/reshard nếu phương án mới phụ thuộc vào chúng.

Đừng đo chỉ `redis-benchmark GET` trên loopback rồi suy ra p99 HTTP thực: benchmark ở cấp Redis không phản ánh mọi overhead Java, serialization, cache miss và database.

### 23.2. Các cấu hình để so sánh

| Phương án | Ý nghĩa |
|---|---|
| A. Baseline: Redis primary hiện tại | Kiểm tra vấn đề thật |
| B. Tối ưu key/TTL/pipeline, không đổi topology | Đánh giá cải tiến đơn giản |
| C. Redis Cluster nhiều primary | Đo memory/throughput scale-out |
| D. Primary + read replicas | Đo read throughput và stale |
| E. Baseline + Caffeine L1 | Đo giảm Redis QPS/latency và chi phí heap |
| F. Cluster + replica + L1 | Đo hệ thống phối hợp nhiều tầng khi thực sự cần |

Mỗi cấu hình nên có **warm-up**, thời gian chạy đủ dài để quan sát steady state, thời gian cold start và đủ nhiều samples cho p99. Khi so sánh, giữ cấu hình app/DB/traffic tương đối tương đương.

### 23.3. Các kết quả cần báo cáo

- HTTP p50/p95/p99, throughput, error rate.
- Redis command QPS theo node, CPU/memory/network.
- Replica lag, redirect, reconnect, timeout.
- L1 hit rate và memory/GC overhead.
- L2 hit rate **có điều kiện trên L1 misses**.
- Database QPS và latency khi miss/fallback.
- Thời gian dữ liệu stale sau update.
- Thời gian recovery sau failover.
- Tổng chi phí hạ tầng và độ phức tạp vận hành.

Đừng chọn cấu hình chỉ vì “Redis ops/s tăng 2 lần” nếu HTTP p99 không cải thiện hoặc lỗi stale tăng vượt mức cho phép.

## 24. Kiểm thử tính đúng đắn bên cạnh benchmark hiệu năng

Thử nghiệm performance không được chỉ đo tốc độ:

| Tình huống | Điều cần xác minh |
|---|---|
| Scale từ 1 lên 5 JVM | L1 hit/memory thay đổi ra sao, có dữ liệu khác giữa instance không |
| Product được cập nhật | L1/L2 đổi sang version mới theo SLA |
| Instance offline khi Pub/Sub invalidation phát | Sau khi quay lại, TTL/reconcile vẫn hạn chế stale |
| Read fill xảy ra đồng thời với invalidation | Không phục vụ version cũ quá chính sách |
| Redis primary failover | Command retries có idempotency; session/revoke policy phù hợp |
| Redis replica lag | Đường đọc yêu cầu dữ liệu mới không đọc nhầm stale |
| Cluster reshard hot slot | Không phá multi-key/script; latency trong ngưỡng |
| Redis outage | Database không sập theo do fallback storm |
| Caffeine đầy memory | Eviction/GC và p99 vẫn trong ngưỡng |
| Deploy hai phiên bản app | Schema/serializer cache tương thích |
| Key có nhiều tenant | Cache không trả chéo dữ liệu giữa tenant |
| L2 TTL hết đồng loạt | Coalescing/jitter tránh stampede |
| Big key tăng gấp nhiều lần | Memory/network/serialization không vượt capacity |

Các bài kiểm thử này đặc biệt quan trọng khi triển khai L1 và replica reads, vì **hệ thống có thể nhanh hơn trong benchmark nhưng sai dữ liệu trong tình huống cạnh tranh/failover**.

## 25. Đánh giá chi phí tổng thể

Một lựa chọn cần tính cả chi phí không hiện trên biểu đồ latency.

### Sharding

Chi phí:

- Nhiều primary/replica hơn.
- Vận hành slot distribution, failover, topology refresh.
- Migration từ standalone, kiểm thử multi-key/script.
- Backup/restore và monitoring theo shard.
- Thời gian reshard, dữ liệu không đều và hot slots.

Lợi ích:

- Chia memory/CPU/network/write throughput theo key.
- Tăng quy mô working set và tổng capacity.
- Có thể tăng khả năng chịu sự cố khi kết hợp replica per shard.

### Replication

Chi phí:

- Mỗi replica gần như cần dung lượng dữ liệu tương ứng.
- Replication traffic, CPU và network.
- Thêm failure modes/lag và failover.
- Rủi ro stale read khi phân tải.

Lợi ích:

- High availability/failover.
- Có thể scale đọc với workloads chấp nhận eventual consistency.
- Bảo vệ khỏi một số sự cố node, dù không bảo đảm durable tuyệt đối.

### L1 cache

Chi phí:

- Heap và GC trên tất cả JVM.
- Invalidation, TTL, version, cold-start warming.
- Rủi ro stale và cache stampede giữa L1/L2.
- Độ phức tạp observability, debug và test nhiều instance.

Lợi ích:

- Giảm network round-trip Redis cho hot reads.
- Giảm QPS và connection pressure tới Redis.
- Cải thiện latency mạnh khi hit rate cao.
- Có thể chống một số outage ngắn cho **dữ liệu được phép stale**, không thay auth/consistency.

Một kế hoạch tốt cần biết **mỗi đơn vị tiền/hạ tầng tăng thêm tạo ra thay đổi gì ở p99, throughput, error rate và SLA độ mới**, thay vì chỉ tính số node.

## 26. Checklist dữ liệu để ra quyết định kỹ thuật

Trước khi quyết định, nhóm có thể điền bảng:

| Câu hỏi | Số liệu cần có |
|---|---|
| Đọc/ghi peak là bao nhiêu? | GET/SET/EVAL QPS theo node và HTTP QPS |
| P99 HTTP chậm ở đâu? | Trace: JVM, Redis RTT, DB, serializer |
| Working set thực tế? | RAM used, key count, payload distribution |
| Dữ liệu có bị skew/hot key? | Top keys/slots và load per primary |
| Redis hiện có failover không? | Replica topology, RTO, replication lag |
| Có thể đọc stale bao lâu? | TTL/staleness SLO theo loại dữ liệu |
| L1 hit rate dự kiến? | Trace key reuse per instance, benchmark |
| Memory JVM còn bao nhiêu? | Heap/GC headroom cho từng replica |
| Invalidation đáng tin cậy đến đâu? | Pub/Sub loss, outbox, version/reconcile |
| Có multi-key/script không? | Danh sách operations và slot compatibility |
| Có thể scale DB khi Redis lỗi? | Fallback QPS budget, bulkhead |
| Mức chi phí/độ phức tạp cho phép? | Infrastructure cost, on-call, migration |

Không nên trả lời bảng bằng “thường là”, “chắc chắn nhanh hơn” hoặc một con số mượn từ benchmark hệ thống khác. Chỉ số từ chính workload là cơ sở chọn kỹ thuật.

## 27. Cây quyết định chọn hướng mở rộng

```text
        Spring Data Redis đang gặp vấn đề?
                       |
                       v
              Có baseline/trace?
                 /           \
               Chưa          Có
                |            |
                v            v
           Đo trước      Nút thắt chính?
                             |
            +----------------+----------------+
            |                |                |
            v                v                v
      Một primary      Read GET/RTT       Cần HA/failover
      hết capacity     tới Redis cao        |
            |                |              v
            v                v          Replication +
    Tối ưu value/TTL   Dữ liệu có lặp    Sentinel/Cluster
    và command trước   trên mỗi JVM?         |
            |           /          \         v
            v         Có           Không    Test durability
    Tải phân bố    |              |        và failover
    theo nhiều key? v              v
        /       \  L1 Caffeine    Tối ưu RTT,
      Có        Không  + TTL/       command/pipeline
       |          |    invalidation  hoặc replica
       v          v        |
    Sharding   Hot key?    v
    Cluster    /    \     Test stale và
               Có   Không  cold-start
               |      |
               v      v
           L1/giảm   Tối ưu dữ liệu
           tải hot   và workload
               |
               +-----------------------------+
                                             |
                                             v
                              Benchmark p95/p99, cost,
                              failure, consistency
                                             |
                                             v
                              Chỉ rollout khi đạt SLO
```

Không nhất thiết chỉ có một nhánh. Hệ thống vừa cần HA, vừa hết capacity có thể cần Redis Cluster với replica, nhưng vẫn nên triển khai theo giai đoạn và đo tác động từng thay đổi.

## 28. Một lộ trình triển khai ít rủi ro

### Giai đoạn 1: đo và tối ưu hiện trạng

- Thu metric HTTP/Redis/DB.
- Phân tích hot key, big key, key TTL và payload.
- Sửa serialization, giảm round-trip, giới hạn burst.
- Đặt latency budget, staleness SLO và memory headroom.

### Giai đoạn 2: thử L1 cho một cache ít nhạy cảm

- Chọn catalog/config read-heavy có version.
- Bật Caffeine với maximum size và TTL ngắn.
- Đo L1 hit/miss, heap/GC, Redis QPS, HTTP p99.
- Thử invalidation, miss burst, deploy và instance offline.
- Rollout canary trước khi áp dụng toàn bộ ứng dụng.

### Giai đoạn 3: bổ sung replica vì HA hoặc phân tải đọc

- Thử Sentinel/Cluster failover trên môi trường tương ứng.
- Đo replica lag ở peak.
- Chỉ bật replica reads cho đường có stale budget rõ.
- Kiểm tra các hành vi read-after-write, revoke và session.
- Không chuyển những thao tác kiểm tra bất biến sang stale replica.

### Giai đoạn 4: sharding khi một primary không còn đủ

- Lập inventory lệnh multi-key, Lua, transaction, scan.
- Thiết kế hash tag và phân bố slot hợp lý.
- Chọn Redis Cluster topology với headroom và replica per shard.
- Di chuyển dữ liệu/traffic có kế hoạch, đo redirect/latency.
- Thử reshard, failover, rollback plan và kết quả một phần.
- Theo dõi load skew/hot slots sau khi rollout.

### Giai đoạn 5: vận hành dài hạn

- Cảnh báo CPU/memory/eviction/replica lag theo node.
- Cảnh báo cache hit giảm và fallback DB tăng.
- Kiểm tra session/auth consistency khi có thay đổi topology.
- Điều chỉnh TTL/size theo metric, không đổi mù theo cảm giác.
- Diễn tập failover, cold-start và backlog tải theo định kỳ phù hợp.

## 29. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Tăng shard để giải một hot key duy nhất | Hot key vẫn nằm một slot | L1/coalescing/giảm payload hoặc partition thực |
| Tưởng replication chia RAM working set | Mỗi replica sao chép dữ liệu | Sharding hoặc giảm dữ liệu khi thiếu RAM |
| Thêm replica mà vẫn đọc toàn bộ từ primary | Read throughput không tăng | Kiểm tra read routing và per-node metrics |
| Đọc replica cho permission/revocation | Có thể trả trạng thái stale | Authoritative read và consistency policy |
| Coi Cluster là transaction toàn cục | Ghi nhiều slot có thể hoàn tất một phần | Gom aggregate cùng slot hoặc DB transaction |
| Hash tag `{all}` cho mọi key | Hot slot, mất khả năng mở rộng | Hash tag theo aggregate |
| Bật L1 nhưng không kiểm soát invalidation | Các JVM trả dữ liệu cũ | TTL + event + version/reconcile |
| Tin Pub/Sub invalidation không bao giờ mất | Instance offline bỏ lỡ update | Dùng TTL/outbox/version |
| Chỉ đặt TTL L1 mà không nghĩ về L2 | Stale end-to-end lâu hơn dự kiến | Thiết kế freshness toàn chuỗi |
| Để L1 không giới hạn size | Heap/GC tăng, OOM | Bounded cache/weight và metric |
| Lưu mutable entity trong L1 | Race giữa request cùng JVM | Immutable DTO/version |
| Cache key thiếu tenant/locale | Trả sai dữ liệu, rủi ro bảo mật | Key scope đầy đủ |
| Dùng Spring Cache hai provider và nghĩ tự thành L1/L2 | Đọc/evict không theo kỳ vọng | Composite cache hoặc cache-aside tường minh |
| Redis outage làm mọi request dồn vào DB | Cascading failure | Circuit breaker, bulkhead, rate limit |
| Chọn phương án từ benchmark loopback | Không phản ánh network/serializer/app | Test gần production, HTTP p99 |
| Không test failover/reshard | Lỗi tại tải cao và thời điểm đổi node | Diễn tập trên môi trường kiểm soát |
| Retry lệnh ghi không idempotent sau timeout | Tăng/giảm nhiều lần | Operation ID, đối soát, retry policy |
| Chỉ theo dõi hit rate toàn hệ thống | Che L1 và L2 hit/miss riêng | Metric cho từng tầng và loại lỗi |
| Không tính memory replica và L1 fleet | Chi phí/capacity ước lượng sai | Tính theo node và instance |
| Scale theo throughput trung bình | Không đủ capacity khi burst | Peak và tail latency/headroom |

## 30. Kết luận

Đánh giá nhu cầu **phân mảnh, replication và cache cục bộ** trong Spring Data Redis là bài toán **định vị nút thắt và chọn đánh đổi phù hợp**, không phải bài toán “càng nhiều node càng tốt”.

- **Sharding/Redis Cluster** phù hợp khi một primary không còn đủ memory hoặc throughput cho tập key có thể phân tán. Nó không tự xử lý một hot key và đưa vào ràng buộc hash slot, multi-key operations, reshard/failover.
- **Replication** phục vụ HA và có thể phân tải đọc, nhưng mỗi replica giữ bản sao dữ liệu, không tăng write capacity của primary và có nguy cơ **stale read** vì đồng bộ bất đồng bộ.
- **Local cache L1** có thể giảm mạnh Redis QPS và độ trễ cho hot reads, nhưng phải giới hạn heap, theo dõi hit rate và giải quyết invalidation, version, TTL và race trên nhiều JVM.
- **Kết hợp nhiều tầng** có thể rất hiệu quả khi workload đủ lớn và có SLO rõ, nhưng cũng làm tăng số kiểu lỗi và độ phức tạp nhất quán.

Một quyết định tốt phải bắt đầu từ **p95/p99 latency, Redis CPU/RAM/QPS, hit/miss theo từng tầng, dữ liệu stale được phép, replica lag và chi phí vận hành**. Sau đó benchmark bằng workload đại diện, thử thất bại/failover và rollout theo giai đoạn.

**Quy tắc cốt lõi:** Trước khi thêm shard, replica hay local cache, hãy chứng minh **nút thắt đang nằm ở đâu**, **phương án mới giảm được bao nhiêu tải/độ trễ**, và **đổi lại dữ liệu có thể cũ hoặc mất nhất quán trong những tình huống nào**.

