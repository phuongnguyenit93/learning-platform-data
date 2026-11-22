# Theo dõi bộ nhớ, eviction, expiration và tỷ lệ cache hit

## 1. Vì sao cache vẫn hoạt động nhưng hệ thống có thể đang gặp sự cố?

Giả sử một ứng dụng Spring Boot dùng **Spring Data Redis** để cache thông tin sản phẩm. Ban đầu, mỗi lần đọc Redis rất nhanh và database nhận ít truy vấn. Sau vài tuần vận hành, nhóm phát triển nhận thấy:

- Bộ nhớ Redis tăng gần giới hạn cấu hình.
- Cache miss tăng dù số lượng request không thay đổi nhiều.
- Một số khóa mới bị loại sớm, trước khi TTL hết.
- Database tăng CPU vì ứng dụng phải nạp lại cache.
- Có thời điểm Redis trả lỗi khi ghi cache.
- Người dùng phàn nàn API chậm nhưng Redis `PING` vẫn trả `PONG`.

Không thể kết luận nguyên nhân chỉ từ một con số “Redis đang sử dụng 85% memory”. Cần phân biệt **bộ nhớ dữ liệu**, **bộ nhớ quá trình Redis thực sự chiếm**, **khóa bị eviction vì áp lực bộ nhớ**, **khóa hết hạn vì TTL** và **số lần tìm cache thành công/thất bại**.

```text
HTTP requests
      |
      v
Spring Cache / RedisTemplate
      |
      +--- CACHE HIT -----------------------> Trả kết quả
      |
      +--- CACHE MISS ---> Database ---> Ghi cache ---> Trả kết quả
      |                         ^
      |                         |
      +--- Redis ERROR ----------+ (fallback nếu được thiết kế)
                     |
                     v
                   Redis
                     |
       +-------------+--------------+
       |             |              |
   Bộ nhớ         Eviction       Expiration
   tăng cao       vì maxmemory   theo TTL
```

Bốn nhóm thông tin quan trọng:

1. **Memory:** Redis đang sử dụng bao nhiêu bộ nhớ, so với `maxmemory` và RAM thực tế?
2. **Eviction:** Có bao nhiêu khóa bị loại để nhường bộ nhớ theo chính sách `maxmemory-policy`?
3. **Expiration:** Có bao nhiêu khóa bị xóa vì hết thời hạn TTL?
4. **Cache hit ratio:** Trong những lượt tra cứu cache, bao nhiêu lượt tìm được dữ liệu?

Bài học thuộc chương **Quan sát** trong **Spring Data Redis**. Trọng tâm là đọc các chỉ số từ Redis, đo bổ sung ở tầng Spring Boot, thiết kế dashboard/cảnh báo và diễn giải đúng các mối quan hệ giữa chúng.

## 2. Bốn khái niệm không được đánh đồng

### 2.1. Memory usage

Redis lưu dữ liệu trong bộ nhớ, đồng thời cần bộ nhớ cho metadata, client buffers, replication, allocator và các cấu trúc nội bộ.

Một ứng dụng không nên chỉ quan tâm:

```text
used_memory
```

mà bỏ qua:

```text
used_memory_rss
maxmemory
used_memory_peak
used_memory_dataset
mem_not_counted_for_evict
```

Các trường này mô tả **những góc nhìn khác nhau**, không phải các tên thay thế cho cùng một đại lượng.

### 2.2. Eviction

**Eviction** là khi Redis loại khóa theo chính sách quản lý bộ nhớ, thường vì một thao tác ghi làm bộ nhớ được xét cho giới hạn `maxmemory` vượt ngân sách.

Ví dụ:

```text
maxmemory = 1 GiB
memory pressure tăng
policy = allkeys-lru
Redis chọn một hoặc nhiều khóa để loại
```

Một khóa bị eviction **không nhất thiết đã hết TTL**. Redis đang hy sinh dữ liệu để giải phóng bộ nhớ theo chính sách.

### 2.3. Expiration

**Expiration** là khóa bị xóa vì thời hạn sống (TTL) đã kết thúc.

Ví dụ:

```redis
SET cache:product:42 "data" EX 60
```

Redis có thể xóa khóa khi nó hết hạn, bằng cơ chế phát hiện lúc truy cập (*passive expiration*) hoặc kiểm tra chủ động (*active expiration*).

Expiration thường là một phần **bình thường** của thiết kế cache có TTL.

### 2.4. Cache hit / miss

**Hit:** một lượt tra cứu tìm được giá trị phù hợp.

**Miss:** một lượt tra cứu hợp lệ không tìm thấy giá trị.

Ví dụ:

```text
GET cache:product:42 -> có dữ liệu   => hit
GET cache:product:43 -> không có key => miss
```

**Redis timeout không phải cache miss.** Nếu Redis mất kết nối, ứng dụng không biết khóa có tồn tại hay không. Phải thống kê lỗi riêng.

### 2.5. Bảng so sánh

| Chỉ số | Ý nghĩa | Không được suy ra |
|---|---|---|
| `used_memory` | Bộ nhớ Redis cấp phát cho hoạt động nội bộ theo thống kê allocator | Toàn bộ RAM hệ điều hành Redis đang chiếm |
| `used_memory_rss` | Bộ nhớ resident theo hệ điều hành | Tất cả đều là dữ liệu cache hữu ích |
| `evicted_keys` | Tổng khóa Redis đã loại theo eviction từ khi bộ đếm bắt đầu | Tất cả khóa đó đã hết TTL |
| `expired_keys` | Tổng khóa bị xóa vì hết hạn | Mọi khóa đều được xóa đúng tại mili giây TTL = 0 |
| `keyspace_hits` | Các lần tìm khóa thành công theo thống kê Redis | Hit riêng của `@Cacheable("products")` |
| `keyspace_misses` | Các lần tìm khóa không thành công theo thống kê Redis | Tất cả đều do eviction |
| `INFO keyspace` | Số key, số key có expiry và TTL trung bình được báo cáo | Thời gian hết hạn chính xác của từng key |

## 3. Bắt đầu quan sát bằng các lệnh Redis

Kết nối tới một Redis server có quyền phù hợp:

```bash
redis-cli INFO memory
redis-cli INFO stats
redis-cli INFO keyspace
```

Hoặc chạy riêng trong interactive CLI:

```redis
INFO memory
INFO stats
INFO keyspace
```

Những câu lệnh bổ sung:

```redis
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
MEMORY STATS
INFO clients
INFO commandstats
```

Trong môi trường Redis được quản lý, một số lệnh như `CONFIG GET` hoặc `MEMORY STATS` có thể bị giới hạn bởi ACL/nhà cung cấp. Khi đó cần dùng endpoint metrics mà dịch vụ cho phép.

**Không nên chỉ lấy một lần `INFO` rồi khẳng định xu hướng.** Memory có thể cần snapshot, nhưng eviction/expiration/hits/misses là **bộ đếm tích lũy**, nên phần lớn phân tích cần nhiều mẫu theo thời gian.

### 3.1. Bốn nhóm lệnh và câu hỏi tương ứng

| Lệnh | Câu hỏi chính |
|---|---|
| `INFO memory` | Bộ nhớ được cấp phát và RAM resident đang ra sao? |
| `INFO stats` | Eviction, expiration, hits/misses tăng với tốc độ nào? |
| `INFO keyspace` | Mỗi logical database còn bao nhiêu key và key có TTL? |
| `CONFIG GET maxmemory` | Redis có ngân sách memory eviction là bao nhiêu? |
| `CONFIG GET maxmemory-policy` | Redis chọn cách loại khóa nào? |
| `MEMORY STATS` | Phân rã bộ nhớ theo các thành phần nào? |
| `MEMORY USAGE <key>` | Một key cụ thể chiếm khoảng bao nhiêu bộ nhớ? |
| `INFO commandstats` | Nhóm lệnh nào được gọi nhiều hoặc tốn thời gian? |

## 4. Hiểu `INFO memory`

Đầu ra ví dụ minh họa:

```text
# Memory
used_memory:524288000
used_memory_human:500.00M
used_memory_rss:629145600
used_memory_rss_human:600.00M
used_memory_peak:671088640
used_memory_peak_human:640.00M
maxmemory:1073741824
maxmemory_human:1.00G
maxmemory_policy:allkeys-lru
mem_fragmentation_ratio:1.20
```

Những con số trên chỉ là **ví dụ**, không phải số liệu từ hệ thống thật.

### 4.1. `used_memory`

Đây là lượng bộ nhớ Redis cho biết đang được cấp phát qua cơ chế allocator cho dữ liệu và cấu trúc Redis.

Nó không đồng nhất với:

- Bộ nhớ container đang chiếm.
- Dung lượng file RDB/AOF trên đĩa.
- Tổng byte của riêng các JSON cache.
- Bộ nhớ vật lý tự do của máy chủ.

Nếu application value chỉ khoảng 100 MiB, `used_memory` vẫn có thể lớn hơn vì key names, metadata, cấu trúc dữ liệu, internal overhead và thành phần vận hành.

### 4.2. `used_memory_rss`

`used_memory_rss` biểu thị lượng bộ nhớ Redis process đang giữ resident theo hệ điều hành.

Nếu:

```text
used_memory = 500 MiB
used_memory_rss = 800 MiB
```

thì cần xem xét allocator fragmentation, RSS overhead, lịch sử cấp phát/giải phóng và cấu hình bộ nhớ, thay vì kết luận có thêm 300 MiB key dữ liệu chưa được tính.

RSS cũng có thể chịu ảnh hưởng từ hành vi allocator và hệ điều hành. Một key bị xóa không nhất thiết khiến RSS giảm ngay về cùng tỷ lệ.

### 4.3. `used_memory_peak`

`used_memory_peak` giúp thấy đỉnh cấp phát trong thời gian process hoạt động.

Ví dụ:

```text
used_memory hiện tại = 500 MiB
used_memory_peak     = 900 MiB
```

Hệ thống từng dùng nhiều bộ nhớ hơn hiện tại. Điều này hữu ích khi điều tra một đợt import dữ liệu hoặc cache warming. Tuy nhiên, giá trị peak phụ thuộc lịch sử process/cách Redis quản lý counters; không thay thế một chuỗi thời gian thu thập liên tục.

### 4.4. `maxmemory`

`maxmemory` là ngưỡng bộ nhớ cấu hình cho cơ chế quản lý bộ nhớ/eviction.

```redis
CONFIG GET maxmemory
```

Nếu kết quả là:

```text
maxmemory
1073741824
```

Redis có ngưỡng khoảng 1 GiB.

`maxmemory = 0` thường nghĩa là không áp dụng giới hạn maxmemory kiểu này trong cấu hình tương ứng, **không phải máy chủ có bộ nhớ vô hạn**. Redis vẫn bị giới hạn bởi RAM, container, operating system và khả năng hạ tầng.

### 4.5. `mem_not_counted_for_evict`

Redis có thể báo:

```text
mem_not_counted_for_evict
```

Trường này thể hiện các phần bộ nhớ không được tính vào phép so ngưỡng eviction theo cơ chế hiện hành, có thể gồm các buffer phục vụ persistence/replication.

Vì vậy, so sánh:

```text
used_memory / maxmemory
```

là một tín hiệu vận hành hữu ích, nhưng **không phải mô phỏng chính xác mọi phép kiểm tra eviction nội bộ**.

Đồng thời, **ngưỡng maxmemory không phải trần cứng cho RSS**. Cần dự trù chỗ cho client buffers, replication, allocator fragmentation, fork/copy-on-write, hệ điều hành và các thành phần khác.

### 4.6. `used_memory_dataset` và `used_memory_overhead`

Nếu Redis phiên bản đang dùng cung cấp:

```text
used_memory_dataset
used_memory_overhead
```

chúng giúp phân biệt phần bộ nhớ gắn với dataset và overhead nội bộ.

Một cache có key rất dài, nhiều object nhỏ hoặc Hash với nhiều metadata có thể có chi phí overhead cao hơn mong đợi.

Đừng giả định:

```text
used_memory_dataset == tổng kích thước JSON gốc
```

vì Redis encoding, dữ liệu nén/serialize và allocator có cách tổ chức riêng.

## 5. Đọc memory fragmentation đúng cách

Có thể quan sát:

```text
mem_fragmentation_ratio
allocator_frag_ratio
allocator_rss_ratio
rss_overhead_ratio
```

tùy phiên bản Redis và allocator.

### 5.1. Fragmentation ratio không đơn giản là phần trăm lãng phí

Nếu:

```text
used_memory_rss = 600 MiB
used_memory     = 500 MiB
```

thì tỉ lệ RSS/allocated xấp xỉ `1.2`.

Nhưng **không nên mặc định** “Redis đang lãng phí chính xác 20% RAM vì fragment”. Các khoản chênh còn có chi phí process, allocator và môi trường.

Đặc biệt, khi dataset rất nhỏ, các overhead cố định làm tỷ số trông cao dù tổng byte không đáng kể.

### 5.2. Kết hợp tỷ số với lượng byte thực tế

Hai trường hợp:

```text
Cache A:
  used_memory = 10 MiB
  rss         = 20 MiB
  ratio       = 2.0

Cache B:
  used_memory = 10 GiB
  rss         = 15 GiB
  ratio       = 1.5
```

Tỷ số của A cao hơn, nhưng B có khoảng chênh lớn hơn rất nhiều về byte.

Vì vậy cần quan sát đồng thời:

- `used_memory`.
- `used_memory_rss`.
- Chênh RSS - allocated.
- Các chỉ số allocator.
- Memory limit của host/container.
- Xu hướng theo thời gian sau tải cao hoặc xóa dữ liệu.

### 5.3. Active defragmentation không phải giải pháp cho mọi sự cố

Redis có các khả năng active defragmentation phụ thuộc phiên bản, allocator và cấu hình. Không bật hoặc điều chỉnh tùy tiện chỉ vì thấy ratio lớn.

Trước tiên phải xác định vấn đề là:

- Dữ liệu cache tăng.
- Bị giới hạn bởi `maxmemory`.
- Client/replication buffers tăng.
- Fragmentation sau biến động cấp phát.
- Hệ điều hành hoặc container bị thiếu RAM.

Mỗi nguyên nhân cần giải pháp khác nhau.

## 6. Theo dõi bộ nhớ theo từng key

Khi một cache region tăng bất thường, có thể điều tra bằng những lệnh có phạm vi nhỏ.

### 6.1. Một key chiếm bao nhiêu byte?

```redis
MEMORY USAGE cache:product:42
```

Redis trả một ước lượng theo cơ chế lưu trữ của key đó. Với cấu trúc phức tạp, có thể dùng lựa chọn `SAMPLES` được phiên bản hỗ trợ:

```redis
MEMORY USAGE cache:product:42 SAMPLES 5
```

Không dùng `MEMORY USAGE ... SAMPLES 0` hàng loạt trên các cấu trúc khổng lồ trong giờ cao điểm mà chưa đánh giá chi phí; `0` yêu cầu lấy mẫu toàn bộ ở những cấu trúc hỗ trợ và có thể tốn tài nguyên.

### 6.2. Xem kiểu dữ liệu và TTL

```redis
TYPE cache:product:42
PTTL cache:product:42
```

Nếu key là Hash:

```redis
HLEN cache:product:42
```

Nếu là List:

```redis
LLEN some:list
```

Những lệnh này giúp xác định số field/element nhưng **không thay cho phép đo bộ nhớ**.

### 6.3. Tìm key lớn mà không quét vô hạn

Có thể dùng công cụ kiểm tra big keys trên môi trường phù hợp, ví dụ:

```bash
redis-cli --bigkeys
```

Tùy nhu cầu có thể giới hạn bằng pattern hoặc các tham số hỗ trợ của phiên bản `redis-cli`.

Cần hiểu công cụ này vẫn phải duyệt keyspace và gửi lệnh đo. Không chạy liên tục trên Redis lớn như một phép đo metric mỗi vài giây.

Khi cần tự quét namespace:

```redis
SCAN 0 MATCH cache:product:* COUNT 100
```

Tiếp tục theo cursor cho tới khi về `0`.

`SCAN` có thể trả trùng, không phải snapshot và `COUNT` là gợi ý. Trong **Redis Cluster**, việc quét phải bao phủ các primary/partition liên quan; `SCAN` trên một node không chứng minh đã thấy mọi key toàn cụm.

### 6.4. Vì sao nhiều object nhỏ có thể gây overhead?

Ví dụ hai lựa chọn:

```text
1 key chứa String JSON lớn
```

và:

```text
1000 key String rất nhỏ
```

Tổng byte payload có thể tương đương, nhưng 1000 key cần thêm key names, dictionary entries và metadata.

Việc chuyển thành Hash hoặc gộp nhóm có thể giảm một số overhead trong một số workload, nhưng lại thay đổi cách cập nhật, TTL, concurrency và kích thước response. Không tối ưu chỉ dựa vào cảm giác; đo bằng `MEMORY USAGE` và độ trễ thực tế.

## 7. Eviction: điều gì xảy ra khi Redis thiếu bộ nhớ?

Redis có một chính sách `maxmemory-policy` để xác định cách ứng xử khi bộ nhớ phục vụ eviction đạt ngưỡng.

Xem cấu hình:

```redis
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
```

Ví dụ:

```text
maxmemory = 1073741824
maxmemory-policy = allkeys-lru
```

Khi có write và Redis cần giải phóng bộ nhớ, chính sách trên cho phép chọn khóa để loại.

### 7.1. Các chính sách eviction phổ biến

| Policy | Phạm vi khóa đủ điều kiện | Nguyên tắc chọn |
|---|---|---|
| `noeviction` | Không chủ động loại key theo maxmemory | Các lệnh ghi cần thêm bộ nhớ có thể nhận lỗi OOM |
| `allkeys-lru` | Tất cả key | Ưu tiên các key ít được dùng gần đây theo LRU xấp xỉ |
| `allkeys-lfu` | Tất cả key | Ưu tiên key có tần suất truy cập thấp theo LFU xấp xỉ |
| `allkeys-random` | Tất cả key | Chọn ngẫu nhiên |
| `volatile-lru` | Chỉ key có expiry | LRU xấp xỉ |
| `volatile-lfu` | Chỉ key có expiry | LFU xấp xỉ |
| `volatile-random` | Chỉ key có expiry | Ngẫu nhiên |
| `volatile-ttl` | Chỉ key có expiry | Ưu tiên key gần hết hạn hơn |

“LRU” và “LFU” ở Redis là các thuật toán có đặc tính xấp xỉ/điều chỉnh, không nên coi là danh sách sắp xếp tuyệt đối chính xác theo mọi lần truy cập.

### 7.2. `allkeys` khác `volatile`

Với:

```text
allkeys-lru
```

Redis có thể loại cả key **không có TTL**.

Với:

```text
volatile-lru
```

chỉ những key có expiration mới đủ điều kiện eviction. Nếu không có key đủ điều kiện mà Redis vẫn thiếu bộ nhớ, một số lệnh ghi có thể thất bại với lỗi OOM thay vì Redis tự xóa key khác.

Điều này rất quan trọng nếu cùng Redis lưu:

```text
cache:product:...
session:...
lock:...
stream:...
fence:sequence:...
```

Nếu toàn bộ dữ liệu dùng một Redis `allkeys-*`, một khóa không có TTL nhưng cần tồn tại bền vững cũng có thể bị eviction theo chính sách. Không nên lưu key bắt buộc không mất cùng vùng eviction với cache tùy tiện.

### 7.3. Eviction khác xóa chủ động

Khi ứng dụng gọi:

```redis
DEL cache:product:42
```

đó là **xóa chủ động**, không phải eviction do áp lực memory.

Tương tự, `@CacheEvict` trong Spring Cache thường dẫn tới thao tác xóa key theo contract cache; nó không có nghĩa bộ đếm Redis `evicted_keys` sẽ tăng.

Do đó:

```text
Keys bị xóa = eviction + expiration + explicit delete + ...
```

và `evicted_keys` chỉ đại diện cho một trong các cơ chế trên.

## 8. Theo dõi eviction qua `INFO stats`

Ví dụ:

```redis
INFO stats
```

Đầu ra có thể chứa:

```text
evicted_keys:1249
expired_keys:39842
keyspace_hits:721002
keyspace_misses:198332
```

Các con số này là **tích lũy theo tuổi thọ bộ đếm Redis**, không phải số key bị loại trong giây vừa rồi.

### 8.1. Không dùng trực tiếp số tích lũy làm tốc độ

Giả sử:

```text
12:00:00 evicted_keys = 1000
12:05:00 evicted_keys = 1300
```

Tốc độ eviction trung bình trong 5 phút:

\[
\frac{1300 - 1000}{300} = 1\ \text{key/giây}
\]

Tốc độ này hữu ích hơn một số `1300` đứng riêng.

Nếu Redis restart, chỉ số có thể quay về nhỏ hơn trước. Hệ thống giám sát phải nhận biết **counter reset**; không tính delta âm như một tỷ lệ âm có ý nghĩa.

### 8.2. Eviction có luôn là lỗi không?

**Không nhất thiết.** Với Redis chuyên dụng làm cache và chính sách `allkeys-lru`, eviction ở một mức ổn định có thể là hành vi đã dự kiến khi tập dữ liệu hoạt động lớn hơn bộ nhớ cho phép.

Tuy nhiên, eviction trở thành dấu hiệu cần điều tra nếu:

- Tốc độ eviction tăng đột ngột.
- Cache hit ratio giảm.
- Database load tăng do phải nạp lại dữ liệu.
- p95/p99 API tăng.
- Redis phải làm nhiều việc nhưng lượng hit thấp.
- Eviction xảy ra ở key mà nghiệp vụ mong đợi không bao giờ bị loại.
- Có OOM command errors.

**Eviction rate và hit ratio cần được xem cùng nhau.**

### 8.3. Eviction có thể làm hot key bị nạp lại liên tục

```text
GET product:42 -> MISS
      |
      v
DB query -> cache SET
      |
 Redis thiếu memory
      |
 Evict một key khác
      |
      v
GET key vừa bị loại -> MISS
      |
      v
DB query tiếp
```

Chu trình này có thể gây *cache churn*: ứng dụng bỏ công nạp cache nhưng dữ liệu không được giữ đủ lâu để mang lại lợi ích.

Với policy LFU/LRU, một workload có phân bố truy cập bất thường hoặc tập dữ liệu thay đổi nhanh vẫn có thể gặp churn. Cần đo lượng hit theo cache region và phân bố hot keys.

## 9. Expiration: theo dõi TTL và số key hết hạn

Redis hỗ trợ key expiration:

```redis
SET cache:product:42 "payload" EX 600
```

Sau đó:

```redis
TTL cache:product:42
PTTL cache:product:42
```

`TTL` trả số giây còn lại, `PTTL` trả mili giây.

### 9.1. Các giá trị TTL đặc biệt

| Kết quả | Ý nghĩa |
|---|---|
| Số dương | Key có thời hạn và còn thời gian |
| `-1` | Key tồn tại nhưng không có expiration |
| `-2` | Key không tồn tại |

Một giá trị TTL rất thấp không tự chứng minh Redis đã xóa key tại thời điểm đó.

### 9.2. Passive expiration và active expiration

Redis có hai cơ chế phổ biến:

**Passive expiration:** khi một lệnh truy cập key đã quá hạn, Redis có thể phát hiện và xử lý key hết hạn.

**Active expiration:** Redis định kỳ lấy mẫu/công việc nội bộ để tìm và loại các key đã quá hạn mà không cần chờ application truy cập.

```text
Key K có expireAt = T

T đến:
  K đã quá hạn về mặt logic

Sau T:
  (1) Request GET K -> Redis phát hiện K quá hạn
  hoặc
  (2) Active expiration cycle -> Redis loại K

Khi Redis thực sự xóa vì expiration:
  expired_keys tăng
```

Do Redis không cam kết xử lý mọi expiration đúng ở mili giây T, một key đã hết TTL về mặt logic có thể chưa bị thu hồi bộ nhớ ngay. Các metric expiration là tín hiệu vận hành, **không phải một đồng hồ định thời nghiệp vụ có độ chính xác tuyệt đối**.

### 9.3. Đo expired rate

Giả sử:

```text
12:00 expired_keys = 50000
12:05 expired_keys = 56000
```

Tốc độ trung bình:

\[
\frac{56000 - 50000}{300}
= 20\ \text{key/giây}
\]

Con số 20 key/giây có thể là hoàn toàn bình thường nếu ứng dụng chủ động tạo rất nhiều cache key TTL ngắn.

Không đặt cảnh báo “expired_keys tăng > 0” cho mọi hệ thống. Hãy so sánh với lượng key tạo mới, TTL, traffic và cache miss.

### 9.4. Expiration khác eviction trong kết quả nghiệp vụ

| Tình huống | Nguyên nhân khóa biến mất | Bộ đếm đặc trưng |
|---|---|---|
| Key có `EX 60` và đến hạn | Hết TTL | `expired_keys` có thể tăng khi Redis xóa |
| Key còn TTL nhưng Redis thiếu memory | Eviction theo policy | `evicted_keys` có thể tăng |
| Ứng dụng gọi `DEL` | Xóa chủ động | Không phải eviction hay expiration |
| `FLUSHDB`/`FLUSHALL` | Xóa quản trị | Không phải TTL |
| Dữ liệu biến mất do failover/restore | Trạng thái phục hồi | Không suy ra đơn giản từ hai counter |

Một **cache miss** có thể xảy ra sau bất kỳ tình huống nào, nên cache miss không phải bằng chứng riêng của eviction hoặc expiration.

## 10. `INFO keyspace`: keys, expires và avg_ttl

Lệnh:

```redis
INFO keyspace
```

Ví dụ:

```text
# Keyspace
db0:keys=180000,expires=150000,avg_ttl=420000
```

Ý nghĩa:

- `keys`: số key trong database được Redis báo ở thời điểm lấy thống kê.
- `expires`: số key có expiration.
- `avg_ttl`: TTL trung bình theo thống kê của Redis, thường tính bằng mili giây.

Trong Redis Cluster, database 0 là database được sử dụng; một node chỉ báo phần dữ liệu node đó đang giữ, không phải toàn bộ 16.384 slots.

### 10.1. Tỷ lệ key có TTL

Từ ví dụ:

\[
\text{TTL coverage} = \frac{150000}{180000} \times 100\%
\approx 83.3\%
\]

Đây là tỷ lệ các key đang có expiration tại thời điểm đo, **không phải xác nhận tất cả key cache đều được đặt TTL đúng**.

Tại sao?

- Redis có thể lưu non-cache keys không cần TTL.
- Một số key cache được thiết kế không TTL.
- Namespace cache khác nhau có thời hạn khác nhau.
- `INFO keyspace` không phân loại theo cache region.
- Một key có TTL quá dài cũng được tính như key “có TTL”.

### 10.2. avg_ttl không phải cam kết expiration

`avg_ttl` là thống kê tổng hợp được Redis báo, không phải SLA của ứng dụng. Không dùng nó để suy ra chính xác thời điểm hết hạn cho một session hoặc để quyết định một nghiệp vụ thời gian thực.

Muốn kiểm tra một key cụ thể, dùng `PTTL` hoặc khi cần deadline tuyệt đối dùng lệnh thích hợp của phiên bản Redis như `PEXPIRETIME`, kết hợp nguồn có thẩm quyền nếu quyết định nghiệp vụ yêu cầu tính chính xác.

## 11. Theo dõi cache hit ratio ở mức Redis

Redis báo:

```text
keyspace_hits
keyspace_misses
```

trong `INFO stats`.

Một phép tính thường dùng:

\[
\text{Hit ratio} =
\frac{\text{keyspace hits}}
{\text{keyspace hits} + \text{keyspace misses}}
\times 100\%
\]

Ví dụ:

```text
keyspace_hits   = 75.000
keyspace_misses = 25.000
```

Thì:

\[
\text{Hit ratio} = 75\%
\]

### 11.1. Không nên lấy toàn bộ lịch sử khi đánh giá lỗi đang xảy ra

Giả sử Redis đã phục vụ cả tháng:

```text
Tổng hits:   9.900.000
Tổng misses:   100.000
```

Tỷ lệ tích lũy = 99%. Nếu trong 5 phút gần đây hầu hết request đều miss do thay đổi namespace hoặc eviction, tỷ lệ tổng lịch sử có thể vẫn rất cao và **che mất sự cố**.

Cần tính trên **delta theo cửa sổ thời gian**.

Ví dụ:

| Mẫu | Hits | Misses |
|---|---:|---:|
| 12:00 | 1.000.000 | 250.000 |
| 12:05 | 1.015.000 | 255.000 |

Trong 5 phút:

```text
Delta hits   = 15.000
Delta misses =  5.000
```

Tỷ lệ hit mới:

\[
\frac{15000}{15000+5000} \times 100\% = 75\%
\]

Đây là cách tính nên dùng để đánh giá chất lượng cache ở một cửa sổ quan sát cụ thể.

### 11.2. Những gì `keyspace_hits/misses` thực sự đo

Đây là **counter ở mức Redis server** cho các lần tìm key thành công/thất bại theo các lệnh và ngữ nghĩa mà Redis thống kê.

Chúng **không tự phân biệt**:

- Cache `products` với cache `users`.
- Một microservice với microservice khác.
- Request của khách hàng với job batch.
- Lookup Redis do `@Cacheable` tạo với những lệnh khác cũng truy cập key.
- Miss hợp lệ với một số loại request truy cập key không tồn tại có chủ đích.

Vì vậy, tỷ lệ hit theo `INFO stats` là **chỉ số toàn Redis node**, không phải tỷ lệ hit chính xác của từng cache region hoặc endpoint trong Spring.

### 11.3. Khi mẫu có quá ít lookup

Giả sử trong 5 phút:

```text
delta hits   = 0
delta misses = 0
```

Mẫu không có lookup để tính tỷ lệ. Công thức phải trả **không có dữ liệu (N/A)** thay vì chia cho 0 hoặc tự gán hit ratio = 100%.

Nếu chỉ có một lần lookup mà miss:

```text
delta hits = 0
delta misses = 1
```

hit ratio là 0%, nhưng mẫu quá nhỏ để suy ra cả hệ thống có vấn đề.

Khi cảnh báo hit ratio, nên kèm **ngưỡng lưu lượng tối thiểu**.

## 12. Phân biệt cache hit ratio Redis và cache hit ratio ứng dụng

Giả sử một Spring Boot service dùng:

```java
@Cacheable("products")
public Product findProduct(long id) { ... }
```

Một hit ratio tổng từ Redis không đủ để biết `products` đang hoạt động ra sao nếu cùng Redis phục vụ `sessions`, `carts` và `rate_limits`.

Nên có hai lớp quan sát:

```text
Spring service
  |
  +--> App cache lookup metrics
  |      products: hit/miss/error
  |      users:    hit/miss/error
  |
  v
Redis
  |
  +--> INFO stats: keyspace_hits/misses
  +--> INFO memory: memory/eviction budget
```

### 12.1. Hit ở tầng ứng dụng còn liên quan đến bypass

Một số request có thể không sử dụng cache:

- Method không có `@Cacheable`.
- Biểu thức `condition` bỏ qua cache.
- `unless` khiến kết quả không được cache.
- Ứng dụng dùng cache local trước Redis.
- Request chứa cờ force-refresh.
- Redis lỗi và ứng dụng fallback sang database.

Một hệ thống đo tốt cần định nghĩa rõ:

```text
lookup_hit
lookup_miss
lookup_error
lookup_bypass
fallback_success
fallback_failure
```

Nếu lấy tổng HTTP request làm mẫu số của cache hit ratio mà không xét bypass, tỷ lệ có thể không phản ánh kết quả của những lượt thực sự tra cache.

### 12.2. Redis error không được biến thành miss

Ví dụ không nên dùng:

```java
try {
    return redis.opsForValue().get(key);
} catch (Exception ex) {
    return null;
}
```

Cách này làm:

```text
Redis timeout -> được ghi nhận như miss
```

Khi Redis bị lỗi, miss rate tăng giả tạo và có thể làm database quá tải nếu mọi request đều fallback.

Đúng hơn là đo:

```text
GET trả value -> HIT
GET trả null  -> MISS
GET ném lỗi   -> ERROR
```

Nếu dữ liệu Redis là cache có thể tái tạo, **fallback** là một quyết định riêng sau khi đã ghi nhận lỗi. Không xóa sự khác biệt giữa lỗi Redis và cache miss.

## 13. Đo cache hit/miss riêng tại Spring Boot với Micrometer

Khi cần biết một cache region thực sự có giá trị hay không, có thể instrument tại tầng service. Ví dụ dưới đây dùng **Spring Data Redis**, `StringRedisTemplate` và **Micrometer**.

### 13.1. Service có ba counter rõ ràng

```java
package com.example.redis.metrics;

import java.util.Optional;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheReader {

    private final StringRedisTemplate redis;

    private final Counter hits;
    private final Counter misses;
    private final Counter errors;

    public ProductCacheReader(
            StringRedisTemplate redis,
            MeterRegistry registry) {

        this.redis = redis;

        this.hits = Counter.builder("app.cache.lookup")
                .description("Product cache lookup outcomes")
                .tag("cache", "products")
                .tag("outcome", "hit")
                .register(registry);

        this.misses = Counter.builder("app.cache.lookup")
                .tag("cache", "products")
                .tag("outcome", "miss")
                .register(registry);

        this.errors = Counter.builder("app.cache.lookup")
                .tag("cache", "products")
                .tag("outcome", "error")
                .register(registry);
    }

    public Optional<String> findCachedProduct(long productId) {

        String key = "cache:products:v2:" + productId;

        try {
            String value = redis.opsForValue().get(key);

            if (value == null) {
                misses.increment();
                return Optional.empty();
            }

            hits.increment();
            return Optional.of(value);

        } catch (DataAccessException ex) {
            errors.increment();
            throw ex;
        }
    }
}
```

Ý nghĩa:

- `hits` tăng khi Redis trả về dữ liệu.
- `misses` tăng khi Redis trả `null`.
- `errors` tăng khi Redis operation ném lỗi thuộc nhóm đang được bắt.
- Metric chỉ có **nhãn cố định** `cache=products` và `outcome=hit/miss/error`.
- Không gắn `productId`, full Redis key hoặc payload làm metric label.

Đây là ví dụ cho đường `GET` cụ thể bằng `StringRedisTemplate`. Với serializer khác hoặc nhiều loại exception, cần điều chỉnh phân loại lỗi. Nếu dữ liệu business là JSON, còn phải tách lỗi giải mã JSON ra khỏi cache miss theo chính sách.

### 13.2. Vì sao không gắn full key vào metric?

Nếu mỗi request có:

```text
cache:products:v2:42
cache:products:v2:43
cache:products:v2:44
...
```

và dùng key làm tag, hệ thống có thể tạo hàng triệu time series. Điều này gây **cardinality explosion**, làm tăng RAM và chi phí lưu metrics.

Ngoài ra, cache keys có thể chứa ID cá nhân, email hoặc token. Chỉ dùng nhãn từ allowlist như:

```text
cache=products
operation=read
outcome=hit
```

### 13.3. Truy vấn và định dạng metric

Khi dùng Prometheus registry, Micrometer thường ánh xạ một counter có tên:

```text
app.cache.lookup
```

sang tên và nhãn Prometheus theo quy tắc của registry, ví dụ:

```text
app_cache_lookup_total{cache="products",outcome="hit"}
```

Tên thực tế phải được xác nhận bằng endpoint metrics của ứng dụng; không tự đoán từ tên Java nếu hệ thống đã cấu hình naming convention khác.

Tỷ lệ hit theo thời gian có thể tính từ **rate** của hai counter hit/miss:

```promql
sum(rate(app_cache_lookup_total{cache="products",outcome="hit"}[5m]))
/
clamp_min(
  sum(rate(app_cache_lookup_total{cache="products",outcome=~"hit|miss"}[5m])),
  0.001
)
```

Biểu thức là ví dụ minh họa khi các tên metric và label đúng như trên. Với mức lưu lượng rất nhỏ, cần thêm điều kiện sample volume trước khi coi tỷ lệ là đáng tin.

Nếu dùng Grafana, có thể nhân `100` hoặc chọn định dạng Percent dựa trên đơn vị metric.

## 14. Spring Cache và RedisCacheManager statistics

Nếu ứng dụng dùng annotation Spring Cache:

```java
@Cacheable(cacheNames = "products", key = "#id")
public Product findProduct(long id) {
    return productRepository.findById(id).orElse(null);
}
```

Spring Data Redis cung cấp `RedisCacheManager`. Trong những phiên bản có hỗ trợ thống kê, có thể bật **cache statistics**:

```java
package com.example.redis.config;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
public class CacheConfig {

    @Bean
    public RedisCacheManager cacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(10));

        return RedisCacheManager
                .builder(connectionFactory)
                .cacheDefaults(defaults)
                .enableStatistics()
                .build();
    }
}
```

### 14.1. Các statistics này có phạm vi nào?

Điểm dễ gây nhầm lẫn: statistics do Spring Data Redis CacheManager cung cấp thường là **thống kê local của từng cache instance trong process**, không phải bộ đếm tổng hợp toàn bộ Redis server.

Nếu có 10 Spring Boot instances:

```text
App 1 -> local products hits/misses
App 2 -> local products hits/misses
...
App 10 -> local products hits/misses
```

Muốn tổng hợp đúng, cần scrape metric từng instance và tính tỷ lệ từ **tổng số hit/miss hoặc tổng rate**, không lấy trung bình đơn giản của 10 tỷ lệ.

Các statistics có thể được reset khi instance restart. Cần dùng đúng logic counter/rate và hiểu version-specific behavior.

### 14.2. Ví dụ đọc statistics

Với phiên bản Spring Data Redis cung cấp `RedisCache.getStatistics()`:

```java
import org.springframework.data.redis.cache.RedisCache;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.cache.CacheStatistics;

RedisCache cache = (RedisCache) cacheManager.getCache("products");

if (cache != null) {
    CacheStatistics stats = cache.getStatistics();

    long hits = stats.getHitCount();
    long misses = stats.getMissCount();
}
```

Đây là thống kê được thu trong Spring Cache khi tính năng được bật. Không suy ra nó bao gồm mọi `RedisTemplate.opsForValue().get()` chạy ngoài Spring Cache abstraction.

Không nên giả định Spring Boot Actuator luôn tự xuất đủ các thống kê này dưới đúng một tên metric trên mọi phiên bản. Cần kiểm tra integration Micrometer/cache instrumentation của dependency thực tế, hoặc xuất metric theo cơ chế ứng dụng.

### 14.3. `@CacheEvict` không phải Redis eviction

Một phương thức:

```java
@CacheEvict(cacheNames = "products", key = "#id")
public void invalidate(long id) {
    // Thao tác nghiệp vụ.
}
```

có thể xóa một cache entry do ứng dụng chủ động invalidation.

Không cộng những lần `@CacheEvict` vào Redis `evicted_keys` một cách máy móc. Hai chỉ số trả lời hai câu hỏi khác nhau:

```text
Application invalidation: có bao nhiêu entry bị xóa do logic?
Redis eviction: Redis đã loại bao nhiêu key vì memory policy?
```

## 15. Tính tỷ lệ cache hit khi có nhiều ứng dụng hoặc nhiều node

### 15.1. Tỷ lệ hit không nên lấy trung bình không trọng số

Giả sử:

```text
Service A:  9 hit / 10 lookups  => 90%
Service B: 10 hit / 100 lookups => 10%
```

Trung bình đơn giản:

```text
(90% + 10%) / 2 = 50%
```

Nhưng tỷ lệ thực trên toàn bộ lookup:

\[
\frac{9+10}{10+100} \approx 17.27\%
\]

**Cách đúng:** cộng số hit và miss trước khi chia, hoặc cộng rate từ các instance trước khi tính tỷ lệ.

### 15.2. Redis Cluster phải thu số liệu từng node

Một Redis Cluster có nhiều primary:

```text
Primary A -> hits/misses, memory, evictions riêng
Primary B -> hits/misses, memory, evictions riêng
Primary C -> hits/misses, memory, evictions riêng
```

`INFO stats` trên Primary A không đại diện cho cả Cluster.

Trong dashboard nên có:

- Số liệu theo từng node/shard.
- Tổng cụm được tổng hợp theo quy tắc phù hợp.
- Giá trị cực đại theo node, đặc biệt memory pressure.
- Phân bố key/hot key giữa các slot.
- Role của node và thời điểm failover.

**Không chỉ nhìn memory tổng toàn Cluster.** Có thể Cluster còn nhiều RAM tổng nhưng một shard cụ thể đã gần giới hạn và eviction dữ dội.

### 15.3. Có nên cộng cả replica vào số liệu?

Điều này phụ thuộc câu hỏi.

Nếu muốn đo **tổng bộ nhớ vật lý Redis đang sử dụng**, phải xét tất cả Redis processes gồm primary và replica.

Nếu muốn đo **số lookup/eviction của dữ liệu authoritative theo primary**, cần định nghĩa phạm vi rõ ràng, tránh nhân đôi hoặc trộn số liệu của replica mà application có thể không đọc tới.

Với Lettuce `ReadFrom.REPLICA_PREFERRED`, replica có thể trực tiếp phục vụ một phần lệnh đọc. Khi đó:

- Hit/miss của **những request thực sự chạy trên replica** có thể xuất hiện ở node replica.
- Primary-only metric có thể bỏ sót lưu lượng đọc replica.
- Việc cộng mọi node có thể cần phân biệt lookup từ app và hoạt động nội bộ.

Cho mục tiêu đánh giá trải nghiệm cache ở tầng API, **application-level hit/miss** thường dễ định nghĩa hơn tỷ lệ toàn Redis Cluster.

### 15.4. Failover làm thay đổi chuỗi thời gian

Khi replica được promote, vai trò node thay đổi. Nếu dashboard chỉ theo nhãn:

```text
role=primary
```

mà không giữ `instance`, một time series có thể trông bị nhảy vì tập node primary thay đổi.

Cần lưu cả:

```text
cluster
node/instance
role
environment
```

và nhận biết counter reset, restarts cùng chuyển vai trò.

## 16. Cấu hình TTL trong Spring Data Redis và tác động tới metrics

Khi dùng RedisCacheManager, có thể đặt TTL mặc định và riêng cho từng cache:

```java
RedisCacheConfiguration defaults =
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(10));
```

Và theo từng vùng:

```java
Map<String, RedisCacheConfiguration> configs = Map.of(
        "products",
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(30)),
        "inventory",
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofSeconds(20))
);
```

Mã trên minh họa map cấu hình; khi dùng thực tế, đưa map vào builder tương ứng của RedisCacheManager và kiểm tra phiên bản Spring Data Redis.

### 16.1. TTL quá ngắn

```text
GET -> MISS -> load DB -> SET EX 5
5 giây sau
GET -> MISS -> load DB -> SET EX 5
```

Hệ quả có thể thấy:

- `expired_keys` tăng.
- Cache misses tăng.
- DB query tăng.
- Hit ratio giảm.
- API latency tăng.

Nếu dữ liệu ít thay đổi nhưng bị hết hạn quá thường xuyên, có thể cân nhắc TTL dài hơn kết hợp invalidation khi cập nhật.

### 16.2. TTL quá dài

TTL quá dài có thể làm:

- Dữ liệu stale.
- Bộ nhớ bị chiếm bởi entry ít truy cập.
- Cache churn/eviction nếu Redis không đủ sức giữ toàn bộ dữ liệu.
- Thay đổi nghiệp vụ không phản ánh kịp.

Điều đó cho thấy không nên tối ưu mỗi hit ratio rồi chọn TTL vô hạn. **Tính mới của dữ liệu và footprint memory** cũng là mục tiêu.

### 16.3. Dùng TTL có jitter để tránh hết hạn đồng loạt

Nếu hàng nghìn key được tạo cùng lúc với TTL giống nhau, chúng có thể cùng hết hạn gần một thời điểm:

```text
t0: SET 100.000 keys EX 600
t0 + 600s: nhiều keys cùng hết hạn
              |
              v
           Cache misses
              |
              v
         Database overload
```

Khi phù hợp, có thể phân bố TTL quanh một mức cơ sở để làm phẳng tải:

```text
TTL = 600s + random(-60s, +60s)
```

Nhưng chỉ dùng jitter nếu nghiệp vụ cho phép cửa sổ thời hạn biến đổi. Với session/token hết hạn chính xác theo chính sách bảo mật, **không tự kéo dài TTL** chỉ để cải thiện cache hit ratio.

## 17. Eviction, expiration và cache miss: đọc chung một biểu đồ

Giả sử dashboard cho thấy:

```text
Memory usage       tăng nhanh
Evictions/second   tăng mạnh
Expired/second     không đổi
Cache hit ratio    giảm
DB queries/second  tăng
```

Một giả thuyết hợp lý là **cache không đủ bộ nhớ so với working set**.

Nhưng nếu:

```text
Memory usage       ổn định
Evictions/second   gần 0
Expired/second     tăng cao
Cache hit ratio    giảm
DB queries/second  tăng
```

thì có thể TTL quá ngắn, nhiều key hết hạn đồng loạt, hoặc traffic chuyển sang các key chưa có cache.

### 17.1. Bảng diễn giải tình huống

| Memory | Eviction | Expiration | Hit ratio | Giả thuyết cần kiểm tra |
|---|---|---|---|---|
| Cao | Tăng | Bình thường | Giảm | Thiếu memory hoặc working set lớn |
| Thấp/vừa | Gần 0 | Cao | Giảm | TTL ngắn, expiration đồng loạt |
| Cao | Gần 0 | Thấp | Thấp | Cache chứa dữ liệu ít hữu ích, miss vì namespace/workload |
| Cao | Tăng | Tăng | Tốt | Cache có thể vẫn hoạt động như thiết kế nhưng tốn chi phí churn |
| Thấp | Gần 0 | Gần 0 | Thấp | Cache mới khởi động, key miss, không warm hoặc đọc sai key |
| Cao | Gần 0 | Thấp | Tốt | Cache ổn định, nhưng vẫn cần kiểm tra headroom |
| Vừa | Không đổi | Không đổi | Đột ngột giảm | Deployment, serializer, key prefix hoặc traffic mix |
| Cao | 0 với `noeviction` | Bất kỳ | Bất kỳ | Có thể gặp OOM khi ghi thay vì có eviction |

Bảng chỉ đưa ra **giả thuyết**, không phải suy luận nguyên nhân chắc chắn từ bốn con số.

### 17.2. Một ví dụ về cache churn

Mỗi phút:

```text
Keys mới được cache:       50.000
Keys bị eviction:          40.000
Keys bị expiration:         1.000
Cache hit ratio:              35%
```

Nếu phần lớn những key mới chỉ được đọc một lần, cache đang chứa lượng dữ liệu có chi phí ghi cao nhưng khả năng tái sử dụng thấp.

Các biện pháp có thể cân nhắc:

- Không cache những loại request chỉ dùng một lần.
- Giới hạn kích thước value.
- Tối ưu key namespace/serialization.
- Chọn TTL theo khả năng tái sử dụng thực tế.
- Điều chỉnh maxmemory/policy khi ngân sách cho phép.
- Tách cache region với dữ liệu không được eviction.
- Chặn cache penetration hoặc request key không hợp lệ.

Không thể kết luận “cần thêm RAM” nếu nguyên nhân chính là cache những giá trị không có lợi ích.

## 18. Redis trả lỗi OOM nhưng `evicted_keys` vẫn bằng 0

Một điểm thường gây nhầm:

```text
maxmemory = 512 MiB
maxmemory-policy = noeviction
```

Khi Redis cần cấp thêm memory cho một số lệnh ghi mà vượt ngưỡng, nó có thể trả lỗi dạng:

```text
OOM command not allowed when used memory > 'maxmemory'
```

Trong trường hợp này:

- `evicted_keys` có thể vẫn bằng 0.
- Redis không tự xóa key để giữ cho lệnh ghi tiếp tục.
- Ứng dụng có thể gặp lỗi ở `SET`, `HSET` hoặc thao tác khác cần thêm bộ nhớ.
- `GET` có thể vẫn phục vụ, tùy tình trạng cụ thể.

Do đó, **eviction = 0 không chứng minh Redis không có áp lực bộ nhớ**.

Khi quan sát memory cần kèm:

- Memory usage so với maxmemory.
- `maxmemory-policy`.
- OOM/errors.
- Write failure rate ở ứng dụng.
- Command latency và tình trạng server.

Trong một số phiên bản Redis, `INFO errorstats` hoặc số liệu exporter tương ứng có thể hỗ trợ theo dõi số lỗi loại OOM. Tên và khả năng có sẵn phụ thuộc phiên bản/triển khai, cần kiểm tra thực tế.

## 19. Monitoring với Redis Exporter, Prometheus và Grafana

Trong môi trường production, thao tác `INFO` thủ công là bước điều tra, không phải chiến lược giám sát dài hạn.

Một kiến trúc thường gặp:

```text
Redis nodes
   |
   | INFO / telemetry
   v
Redis exporter / managed metrics
   |
   v
Prometheus hoặc hệ thống time series
   |
   v
Grafana dashboard + Alert rules
   ^
   |
Micrometer / Spring Actuator
   |
Spring Boot services
```

### 19.1. Tách Redis-level và application-level metrics

**Redis-level:**

```text
memory used
RSS
maxmemory
evicted_keys
expired_keys
keyspace_hits
keyspace_misses
connected clients
commands per second
latency
```

**Application-level:**

```text
cache products hit/miss/error
cache users hit/miss/error
fallback to database
cache load duration
timeout/retry
business request p95/p99
database query volume
```

Cần cả hai để biết cache **tốn bao nhiêu tài nguyên** và **mang lại lợi ích gì cho ứng dụng**.

### 19.2. Tên metric exporter có thể khác

Một số Redis exporters dùng các tên tương tự:

```text
redis_memory_used_bytes
redis_memory_max_bytes
redis_evicted_keys_total
redis_expired_keys_total
redis_keyspace_hits_total
redis_keyspace_misses_total
```

Đây là **tên minh họa**, không phải hợp đồng bắt buộc của mọi Redis exporter hoặc dịch vụ Redis được quản lý. Phải kiểm tra endpoint `/metrics` và tài liệu phiên bản đang dùng.

Không xây dashboard bằng cách đoán tên metric rồi kết luận hệ thống không có eviction khi một query trả `No data`.

### 19.3. Truy vấn PromQL minh họa

**Tỷ lệ sử dụng memory so với cấu hình:**

```promql
100 *
redis_memory_used_bytes
/
redis_memory_max_bytes
```

Chỉ áp dụng khi `redis_memory_max_bytes > 0` và hai metric thuộc cùng node/instance. Nếu maxmemory bằng 0 hoặc không được expose, tỷ lệ này không có ý nghĩa và cần dùng hạn mức khác.

**Eviction rate trong 5 phút:**

```promql
rate(redis_evicted_keys_total[5m])
```

**Expiration rate trong 5 phút:**

```promql
rate(redis_expired_keys_total[5m])
```

**Redis-level hit ratio trong 5 phút:**

```promql
sum by (instance) (
  rate(redis_keyspace_hits_total[5m])
)
/
clamp_min(
  sum by (instance) (
    rate(redis_keyspace_hits_total[5m])
    +
    rate(redis_keyspace_misses_total[5m])
  ),
  0.001
)
```

Các biểu thức này phải được điều chỉnh theo labels và metric names của exporter thực tế. Khi tổng hợp nhiều node, phải quyết định có gồm replica không và metric nào đại diện cho đường đọc của application.

**Lưu ý:** `clamp_min` giúp tránh mẫu số bằng 0 nhưng khi gần như không có lookup, tỷ lệ không có ý nghĩa thống kê. Nên loại trừ khoảng có traffic quá thấp bằng điều kiện riêng.

### 19.4. Counters phải xử lý restart và failover

Prometheus `rate` được thiết kế để xử lý nhiều tình huống counter reset khi process restart. Nhưng cần:

- Scrape đều đặn.
- Label phân biệt các Redis instances.
- Hiểu vai trò node thay đổi sau failover.
- Không gộp bừa chuỗi metric từ primary và replica đã đổi vai trò.
- Không dùng raw `counter_now - counter_previous` khi counter vừa reset mà không kiểm tra.

## 20. Thiết kế dashboard theo câu hỏi vận hành

Một dashboard hữu ích có thể chia thành các nhóm.

### 20.1. Memory capacity

```text
used_memory
used_memory_rss
maxmemory
memory utilization %
used_memory_peak
mem_not_counted_for_evict
fragmentation / allocator stats
```

Mục tiêu: Redis còn bao nhiêu headroom, liệu RAM thực tế có bị đe dọa và bộ nhớ tăng do dữ liệu hay overhead?

### 20.2. Eviction và expiration

```text
evicted_keys/s
expired_keys/s
maxmemory-policy
keys with TTL / total keys
number of keys by logical DB
OOM error rate
```

Mục tiêu: key biến mất vì thiếu RAM hay vì TTL? Có key nào bị loại dù không nên bị loại không?

### 20.3. Cache effectiveness

```text
Redis-level hit ratio
Application cache hit ratio by region
Cache lookup errors
Cache load latency
Database fallback QPS
Cache invalidation count
Cache bypass count
```

Mục tiêu: cache có giảm được tải database và độ trễ API không?

### 20.4. Redis performance

```text
Commands/s
Client latency p95/p99
Server latency
Connected clients
Rejected connections
CPU
Network throughput
Slowlog count
```

Mục tiêu: việc tăng memory hay cache miss đang liên quan tới tài nguyên server, connection hoặc network?

### 20.5. Topology

Nếu là Redis Cluster hoặc Sentinel:

```text
Node role
Shard owner / primary
Replica lag
Failover events
Per-node memory
Per-node eviction rate
Per-node command rate
```

Mục tiêu: có node riêng lẻ đang gặp áp lực dù toàn hệ thống nhìn chung vẫn ổn không?

## 21. Đặt cảnh báo có ngữ cảnh

Không có một ngưỡng chung phù hợp mọi Redis server. Ví dụ một cache dùng `allkeys-lfu` có eviction ổn định vẫn đạt 98% hit, trong khi một Redis giữ session với `noeviction` có thể xem bất kỳ OOM write nào là lỗi nghiêm trọng.

### 21.1. Một bộ quy tắc minh họa

| Cảnh báo | Điều kiện minh họa | Phân tích tiếp |
|---|---|---|
| Memory pressure | Memory ratio trên 85% liên tục 10 phút | Xem headroom/RSS/fragmentation |
| High eviction | Eviction rate tăng gấp nhiều lần baseline | Xem hit ratio và cache churn |
| Low hit ratio | Hit ratio giảm dưới SLO khi đủ lookup volume | Xem TTL, key prefix, traffic, serializer |
| OOM write errors | Có OOM ghi khi Redis phải đáp ứng ghi | Xem `noeviction`, memory và ứng dụng |
| High RSS | RSS gần RAM/cgroup limit | Xem overhead, buffer, fragmentation |
| Cache load storm | DB fallback QPS tăng đột biến | Xem Redis lỗi, eviction hoặc expiration burst |
| Replica issue | Lag tăng hoặc link down | Xem stale reads và failover |
| Redis command timeout | Rate timeout vượt baseline | Xem server/network/client queues |

**85% và 10 phút chỉ là con số ví dụ** để minh họa cảnh báo theo thời gian. Ngưỡng thực cần dựa trên tải đỉnh, khả năng mở rộng, độ lớn write burst, replication, persistence và SLO.

### 21.2. Cảnh báo ghép nhiều tín hiệu

Một điều kiện đáng chú ý:

```text
memory_used/maxmemory cao
AND eviction_rate tăng
AND application_hit_ratio giảm
AND database_fallback_qps tăng
```

Chuỗi trên giúp phát hiện cache memory pressure có tác động thật tới ứng dụng.

Tuy vậy, không nên bắt buộc mọi điều kiện đều đúng trước khi cảnh báo **OOM errors hoặc rủi ro thiếu RAM nghiêm trọng**. Một số lỗi cần cảnh báo độc lập.

### 21.3. Đừng cảnh báo expired_keys > 0

Trong cache TTL hoạt động đúng, expired keys là chuyện bình thường. Điều đáng quan sát là:

- Expiration rate tăng bất thường so với traffic.
- TTL bị cấu hình sai sau deployment.
- Nhiều key cùng hết hạn tạo spike tải database.
- Cache hit ratio giảm hoặc DB load tăng theo.
- Session expiration có sai lệch so với hợp đồng nghiệp vụ không.

## 22. Tình huống thực tế: điều tra khi tỷ lệ hit giảm

Giả sử dashboard ứng dụng ghi nhận:

```text
09:00 - products cache hit ratio: 94%
09:15 - products cache hit ratio: 45%
09:15 - API p99 tăng
09:15 - Database queries/s tăng
```

### Bước 1: Xác minh mẫu đo

Kiểm tra:

- Hit/miss counters có bị reset vì deploy không?
- Lookup volume có đủ lớn không?
- Metric label/cache name có đổi không?
- Có trường hợp lỗi Redis bị tính thành miss không?

Nếu numerator/denominator sai, cả biểu đồ hit ratio cũng sai.

### Bước 2: Xem Redis memory và eviction

```redis
INFO memory
INFO stats
CONFIG GET maxmemory-policy
```

Nếu `evicted_keys` tăng nhanh trong đúng giai đoạn hit ratio giảm, có thể cache đang thiếu memory hoặc working set thay đổi.

### Bước 3: Xem expiration

Nếu evictions gần 0 nhưng expiration rate tăng đột ngột:

- Có thay TTL từ 30 phút xuống 30 giây không?
- Có job tạo hàng loạt key cùng TTL không?
- Có vừa xóa/đổi cache namespace không?
- Có nhiều key cùng được tạo sau một lần cache warm không?

### Bước 4: Xem key prefix và serializer

Sau deployment:

```text
V1: cache:product:42
V2: cache:products:v2:42
```

Ngay cả khi Redis còn nhiều memory, code mới có thể không đọc được cache cũ. Hit ratio giảm do **cold namespace** chứ không phải eviction.

Nếu serializer thay đổi, lỗi decode có thể xuất hiện; đừng biến lỗi này thành miss để biểu đồ trông đơn giản hơn.

### Bước 5: Xem số liệu từng region

Có thể chỉ riêng `products` có vấn đề:

```text
products hit: 45%
users hit:    97%
settings hit: 99%
```

Tỷ lệ hit Redis toàn server có thể vẫn cao vì các region khác chiếm phần lớn traffic.

### Bước 6: Chọn giải pháp phù hợp nguyên nhân

| Nguyên nhân | Hướng xử lý |
|---|---|
| Memory budget quá nhỏ | Đánh giá tăng memory hoặc giảm footprint |
| Eviction policy không phù hợp | Đổi policy khi đã thử workload |
| TTL quá ngắn | Điều chỉnh TTL/invalidation |
| Hết hạn đồng loạt | TTL jitter nếu nghiệp vụ cho phép, pre-warm có giới hạn |
| Đổi namespace | Kế hoạch warm/migration và giữ tương thích |
| Value quá lớn | Giảm payload, cache theo field hoặc tránh cache một số dữ liệu |
| Hot key / traffic skew | Tối ưu truy cập, shard và bảo vệ nguồn |
| Redis connection error | Sửa lỗi hạ tầng, không tính thành miss |
| Database fallback storm | Bulkhead/rate limit/single-flight theo key nếu phù hợp |

## 23. Tình huống thực tế: memory tăng nhưng hit ratio vẫn cao

Giả sử:

```text
Redis hit ratio      = 98%
used_memory          = 950 MiB
maxmemory            = 1 GiB
used_memory_rss      = 1.3 GiB
evictions/second     = 0
```

Hệ thống có thể vẫn phục vụ cache hiệu quả, nhưng:

- Redis gần ngân sách eviction.
- RSS cao hơn allocated memory và có thể tiến tới giới hạn RAM/container.
- Một đợt ghi lớn có thể kích hoạt eviction hoặc OOM.
- Hit ratio tốt không chứng minh đủ headroom.

Cần điều tra:

1. `maxmemory-policy` là gì?
2. Có bao nhiêu byte memory không tính vào eviction?
3. RSS/allocator fragmentation có tăng theo thời gian không?
4. Peak write burst lớn tới đâu?
5. Redis có chạy AOF rewrite hoặc snapshot khiến memory demand tăng không?
6. Host có đủ RAM dự phòng cho replication buffers và copy-on-write không?

Đây là ví dụ cho thấy **chỉ số cache hiệu quả không thay thế capacity monitoring**.

## 24. Tình huống thực tế: expiration cao nhưng hệ thống vẫn khỏe

Giả sử Redis phục vụ OTP và cache ngắn hạn:

```text
expired_keys/s       = 1.000
evicted_keys/s       = 0
app cache hit ratio  = 92%
API p99              = ổn định
DB load              = ổn định
```

Một lượng lớn expiration có thể đúng với thiết kế TTL ngắn. Không nên tự động tăng TTL để giảm số expired keys, vì OTP hoặc session có ràng buộc an toàn.

Điều cần theo dõi:

- TTL có đúng chính sách nghiệp vụ không?
- Entry sau deadline có bị xử lý như không còn hợp lệ không?
- Có burst cùng thời điểm gây tải không?
- Tỷ lệ hit/miss và downstream load có đáp ứng SLO không?

**Expiration rate là tín hiệu hành vi, không tự là chỉ số lỗi.**

## 25. Keyspace notifications có giúp đếm chính xác eviction/expiration không?

Redis có cơ chế **keyevent notifications**:

```text
__keyevent@0__:expired
__keyevent@0__:evicted
```

Có thể bật loại sự kiện tương ứng bằng `notify-keyspace-events` nếu được phép.

Ví dụ thử nghiệm:

```redis
CONFIG SET notify-keyspace-events Exe
```

Sau đó đăng ký:

```redis
PSUBSCRIBE __keyevent@0__:expired
```

hoặc:

```redis
PSUBSCRIBE __keyevent@0__:evicted
```

Tuy nhiên, cần hiểu các giới hạn:

- Notifications dựa trên **Redis Pub/Sub**.
- Khi subscriber offline, message có thể mất.
- Không có cơ chế ACK/replay mặc định.
- Trong Redis Cluster, keyspace/keyevent notifications có **phạm vi node phát sự kiện**; chỉ subscribe một node không nhận mọi event từ những node khác.
- Bật notifications có thêm chi phí vận hành.
- Listener nhiều instance có thể nhận cùng một event.

**Không dùng số message nhận được từ Pub/Sub để thay `expired_keys` hoặc `evicted_keys` như một counter tuyệt đối chính xác.**

Keyspace notifications hữu ích cho một số tác vụ phản ứng theo event, nhưng quan sát tỷ lệ trong production nên dựa trên counters và metrics có kế hoạch thu thập rõ ràng.

## 26. TTL, eviction và yêu cầu độ bền dữ liệu

Không nên sử dụng cùng một chính sách memory cho mọi kiểu key.

Ví dụ:

```text
cache:product:*           -> có thể eviction
cache:search:*            -> có thể eviction
session:*                 -> cần đánh giá bảo mật/nguồn dự phòng
idempotency:*             -> có thể cần giữ suốt cửa sổ chống lặp
lock:*                    -> lease với TTL, có ngữ nghĩa phối hợp
fencing:sequence:*        -> không được tự reset nếu dùng để bảo vệ resource
stream:orders             -> có message/consumer-group state quan trọng
```

Với `allkeys-*`, một Redis server có thể eviction cả những key không có TTL. Vì vậy nên cân nhắc:

- Tách Redis caches khỏi Redis dữ liệu phối hợp/queue quan trọng.
- Chọn memory policy riêng theo nhóm workload.
- Dùng nguồn authoritative cho dữ liệu không thể mất.
- Đặt TTL cho những key cần expiration.
- Có backup/persistence/failover tương ứng.

**Redis replication không tự ngăn eviction hoặc TTL expiration.** Khi primary loại một key theo chính sách, các thay đổi dữ liệu tương ứng có thể được truyền theo cơ chế replication. Replica không phải bản backup cho key đã được primary chủ động loại theo policy.

## 27. Quan sát Redis trong Sentinel và Cluster

### 27.1. Sentinel

Với Sentinel:

```text
Primary P      -> số liệu memory/stats riêng
Replica R1     -> số liệu memory/stats riêng
Replica R2     -> số liệu memory/stats riêng
```

Sau failover, R1 có thể trở thành primary. Dashboard nên gắn:

```text
node identity
role
replication status
failover timestamp
```

Nếu chỉ nhìn một hostname mà không xem role, có thể nhầm một replica cũ với primary hiện tại.

### 27.2. Redis Cluster

Với Cluster:

```text
Cluster:
  Primary A -> slot group A, local memory/eviction
  Primary B -> slot group B, local memory/eviction
  Primary C -> slot group C, local memory/eviction
```

Nếu Primary B gần maxmemory còn A và C có nhiều headroom, không thể coi tổng memory trống là bảo đảm B không eviction.

Một dashboard phù hợp nên hiển thị:

```text
cluster_total_used_memory
max(primary_memory_utilization)
per_shard_eviction_rate
per_shard_expiration_rate
per_shard_hit_ratio
per_shard_commands_per_second
```

Đây là **khái niệm metric cần thiết kế**, không phải tên có sẵn trong mọi exporter.

### 27.3. Định tuyến đọc replica làm thay đổi nơi tăng hit/miss

Với Lettuce có cấu hình đọc replica, ví dụ `REPLICA_PREFERRED`, lệnh đọc có thể được gửi tới replica.

Khi đó số `keyspace_hits` trên primary không thể tự đại diện cho toàn bộ lượt đọc ứng dụng. Cần quan sát đường đi của client và tổng hợp theo định nghĩa phù hợp.

**Nếu mục tiêu là hit ratio của `products` cache**, hãy đo ngay ở Spring Cache hoặc tầng access abstraction, còn Redis-level metrics dùng để phân tích phía hạ tầng.

## 28. Đọc memory đúng trong môi trường container

Khi Redis chạy trong Docker/Kubernetes, có ít nhất hai ngân sách:

1. `maxmemory`: cấu hình Redis dùng cho eviction.
2. Memory limit của container/pod/host: giới hạn tài nguyên thực.

Ví dụ:

```text
Container memory limit = 2 GiB
Redis maxmemory        = 1.8 GiB
```

Giá trị Redis `maxmemory` 1.8 GiB không chắc an toàn nếu còn:

- Overhead process và allocator.
- Client buffers.
- Replication/backlog.
- AOF rewrite / RDB snapshot và copy-on-write.
- Các workload khác trong container.

Nếu memory thực vượt giới hạn container, hệ điều hành có thể OOM-kill Redis process. Điều này khác với lỗi `OOM command not allowed` do Redis tự từ chối một số lệnh ghi theo `maxmemory-policy`.

Nên quan sát:

```text
redis_used_memory
redis_used_memory_rss
redis_maxmemory
container_memory_working_set
container_memory_limit
pod_restarts / OOMKilled
```

Tên metric của Kubernetes và exporter phụ thuộc stack, cần xác nhận thực tế.

### 28.1. Vì sao không đặt maxmemory bằng 100% RAM?

Vì Redis cần thêm bộ nhớ ngoài phần dataset được quản lý bởi maxmemory. Một cấu hình chỉ đủ chỗ cho dữ liệu nhưng không đủ headroom cho overhead, fork và biến động tải có thể dẫn tới OOM của hệ điều hành.

Không có tỷ lệ headroom cố định phù hợp mọi Redis setup; phải đo sự kiện persistence, replication, payload size, peak connections và fragmentation.

## 29. Quy trình kiểm thử/chẩn đoán trong môi trường an toàn

Không nên mô phỏng eviction bằng cách hạ `maxmemory` trên Redis production đang lưu dữ liệu thật. Hãy dùng một Redis thử nghiệm hoặc container riêng.

### 29.1. Baseline

Chạy:

```redis
INFO memory
INFO stats
INFO keyspace
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
```

Ghi lại:

```text
used_memory
used_memory_rss
maxmemory
evicted_keys
expired_keys
keyspace_hits
keyspace_misses
```

### 29.2. Thử expiration

```redis
SET it:cache:exp:1 "value" EX 2
```

Sau hơn 2 giây, kiểm tra:

```redis
GET it:cache:exp:1
TTL it:cache:exp:1
INFO stats
```

Kỳ vọng key không còn có thể truy cập theo TTL và bộ đếm expiration có thể tăng khi Redis thực sự xóa key. Không bắt buộc event được phát đúng từng mili giây.

### 29.3. Thử hit/miss

Trên Redis test:

```redis
SET it:cache:hit:1 "value" EX 120
GET it:cache:hit:1
GET it:cache:hit:not-found
INFO stats
```

So sánh counters **trước và sau** trên một môi trường cô lập, không có traffic khác, để thấy cách chúng thay đổi. Một số lệnh trong quy trình có thể cũng ảnh hưởng thống kê lookup; vì vậy không áp đặt rằng delta nhất định bằng đúng 1 trong mọi cấu hình/lệnh.

### 29.4. Thử eviction

Trên Redis test **chỉ chứa dữ liệu có thể xóa**, cấu hình policy và maxmemory đủ để tạo memory pressure:

```redis
CONFIG SET maxmemory-policy allkeys-lru
```

Có thể dùng lệnh `CONFIG SET maxmemory ...` để đặt ngân sách thích hợp cho container thử nghiệm, sau đó ghi nhiều key test với payload đủ lớn và theo dõi:

```redis
INFO memory
INFO stats
```

Không đưa một giá trị `maxmemory` quá thấp áp dụng nguyên xi cho mọi Redis vì lượng memory tối thiểu/overhead thực tế khác nhau.

Kết quả cần quan sát:

- Eviction rate có tăng không?
- `used_memory` có tiến tới ngưỡng không?
- Key đã ghi trước đó có thể bị loại dù TTL chưa hết không?
- Cache hit ratio và Redis latency thay đổi thế nào?
- Khi chuyển sang `noeviction`, các write cần thêm memory phản ứng ra sao?

### 29.5. Kết thúc test

Nếu là container hoàn toàn riêng, hủy container/volume theo quy trình thử nghiệm.

Nếu là Redis test chia sẻ, chỉ dọn những key demo thuộc namespace của bài:

```text
it:cache:*
```

Không chạy `FLUSHALL` lên Redis chưa xác minh là môi trường cô lập.

## 30. Bài tập thực hành với Spring Boot

### Bài tập A: Thống kê hit/miss ở tầng service

1. Tạo `ProductCacheReader` với ba counter `hit`, `miss`, `error`.
2. Gọi một key có sẵn.
3. Gọi một key không tồn tại.
4. Giả lập lỗi kết nối hoặc dùng môi trường test kiểm soát.
5. Xác nhận `error` không bị ghi nhầm vào `miss`.
6. Kiểm tra endpoint metrics của ứng dụng.

### Bài tập B: Đổi TTL rồi quan sát

1. Dùng một cache region test TTL 5 phút.
2. Ghi nhận `hit ratio`, `expired_keys/s`, DB queries/s.
3. Trên môi trường test, đổi TTL thành 20 giây.
4. Chạy cùng workload và so sánh.
5. Giải thích vì sao TTL ngắn có thể làm miss tăng.

### Bài tập C: Bật Redis Cache statistics

1. Cấu hình `RedisCacheManager` với `enableStatistics()`.
2. Sử dụng một method `@Cacheable("products")`.
3. Gọi nhiều lần cùng key để tạo hit.
4. Gọi key mới để tạo miss.
5. Quan sát thống kê được thu ở process ứng dụng.
6. Chạy thêm một instance để hiểu vì sao metrics này không tự là tỷ lệ toàn Redis.

### Bài tập D: So sánh eviction và expiration

1. Tạo các key có TTL trong Redis test.
2. Đợi hết hạn rồi đo `expired_keys`.
3. Tạo memory pressure có kiểm soát và policy cho phép eviction.
4. Đo `evicted_keys`.
5. Giải thích vì sao hai bộ đếm khác nhau dù kết quả cuối đều là key không còn tồn tại.

### Bài tập E: Mẫu số khi tính hit ratio

Giả sử hai service có counters:

```text
Service A: hits=9, misses=1
Service B: hits=10, misses=90
```

Tính hit ratio của từng service và toàn bộ lookup. Chỉ ra vì sao lấy trung bình hai tỷ lệ là sai.

### Bài tập F: Đọc dashboard sau deployment

Mô phỏng một thay đổi namespace từ `cache:products:v1:*` sang `cache:products:v2:*`, không backfill.

Phân tích:

- Memory có thể tăng hay giảm?
- Vì sao cache hit ratio v2 giảm?
- `evicted_keys` có bắt buộc tăng không?
- DB fallback tăng trong bao lâu?
- Cần cache warm có giới hạn hay lazy loading theo request?

### Bài tập G: Redis Cluster

Nếu có Cluster test nhiều primary:

1. Xác định mỗi primary có bao nhiêu slots.
2. Thu `INFO memory`, `INFO stats` theo node.
3. Tạo tập key phân bố không đều.
4. So sánh memory pressure và eviction trên từng shard.
5. Giải thích vì sao tổng memory cụm có thể bình thường nhưng một shard bị thiếu bộ nhớ.

## 31. Những lỗi thường gặp khi quan sát Redis cache

### Lỗi 1: Chỉ nhìn used_memory

Bỏ qua RSS, maxmemory, fragmentation, buffer và giới hạn container.

### Lỗi 2: Coi maxmemory là trần RAM tuyệt đối

Redis process có thể cần nhiều RAM hơn memory được xét cho eviction.

### Lỗi 3: Evicted_keys bằng 0 nghĩa là Redis không thiếu RAM

Với `noeviction`, ghi có thể trả OOM thay vì loại key.

### Lỗi 4: Coi expired_keys là dữ liệu bị mất ngoài ý muốn

Khóa cache có TTL được thiết kế để hết hạn; expiration bình thường không phải sự cố.

### Lỗi 5: Coi eviction và expiration là một

Hai cơ chế có nguyên nhân khác nhau, cần chính sách xử lý khác nhau.

### Lỗi 6: Chỉ lấy tổng counter

Số tích lũy không phản ánh lỗi vừa xuất hiện. Phải xem delta/rate và counter reset.

### Lỗi 7: Tính hit ratio tích lũy từ ngày khởi động

Sự cố trong 5 phút có thể bị che bởi hàng triệu hit lịch sử.

### Lỗi 8: Chia cho 0 khi không có lookup

Nếu delta hit + miss = 0, tỷ lệ không xác định, không tự gán 100%.

### Lỗi 9: Lấy trung bình hit ratio của nhiều node

Phải cộng hits và misses rồi chia; nếu không, node ít traffic bị cho trọng số quá lớn.

### Lỗi 10: Coi `keyspace_hits` là hit riêng của Spring Cache

Redis counters ở mức node và chứa lookup từ nhiều ứng dụng/lệnh.

### Lỗi 11: Tính Redis timeout thành miss

Che sự cố kết nối và làm tỷ lệ cache trông xấu sai nguyên nhân.

### Lỗi 12: Dùng `@CacheEvict` để giải thích `evicted_keys`

Xóa chủ động do ứng dụng khác với eviction theo maxmemory.

### Lỗi 13: Chỉ thu metrics từ một node Cluster

Bỏ sót áp lực memory và eviction trên những shard khác.

### Lỗi 14: Không phân biệt primary và replica

Có thể cộng trùng footprint hoặc bỏ sót những read được định tuyến tới replica.

### Lỗi 15: Dùng full Redis key làm metric label

Tạo cardinality cao và có thể lộ thông tin người dùng.

### Lỗi 16: Bật `KEYS *` hoặc full scan liên tục trong hệ thống metric

Lệnh quét lớn có thể tự gây tải và tăng latency. Sử dụng telemetry sẵn có, quét có giới hạn chỉ khi cần điều tra.

### Lỗi 17: Dùng Pub/Sub notifications để đếm chính xác expiration

Subscriber offline có thể mất event; trong Cluster thông báo gắn với node phát.

### Lỗi 18: Tăng TTL vô hạn để tăng hit ratio

Có thể gây dữ liệu stale và tăng footprint. Hit ratio chỉ là một mục tiêu trong nhiều mục tiêu.

### Lỗi 19: Tăng RAM mà không kiểm tra workload

Nếu cache chứa các key chỉ đọc một lần hoặc payload quá lớn, thêm memory có thể không giải quyết chi phí DB/cache churn.

### Lỗi 20: Lưu key quan trọng trong Redis `allkeys-lru` như cache thường

Key không TTL vẫn có thể bị eviction. Phải phân loại dữ liệu và yêu cầu độ bền.

### Lỗi 21: Dùng `SLOWLOG` hoặc MONITOR như nguồn metrics công khai

Các công cụ này có thể chứa key/arguments nhạy cảm và gây chi phí; cần giới hạn quyền và mục đích.

### Lỗi 22: Không tính tới restart/failover của Redis

Counters có thể reset, roles thay đổi và một node có thể được thay thế. Dashboard cần có identity và cơ chế tổng hợp phù hợp.

### Lỗi 23: Chỉ cảnh báo khi cache hit ratio giảm

Redis có thể gần OOM dù hit ratio rất tốt; cần cảnh báo capacity độc lập.

### Lỗi 24: Chỉ cảnh báo khi memory cao

Một cache bị miss 80% do namespace sai có thể gây DB overload dù Redis dùng rất ít memory.

## 32. Câu hỏi tự kiểm tra

**1. `used_memory` và `used_memory_rss` khác nhau thế nào?**

`used_memory` mô tả bộ nhớ Redis đã cấp phát theo allocator; RSS là bộ nhớ resident của process theo hệ điều hành. Hai giá trị không bắt buộc bằng nhau.

**2. Vì sao `used_memory / maxmemory` không phải toàn bộ bức tranh bộ nhớ?**

Vì còn allocator overhead, replication/client buffers, `mem_not_counted_for_evict`, RSS, RAM/container limit và các biến động khác.

**3. Eviction khác expiration ở đâu?**

Eviction loại key theo memory policy khi có áp lực bộ nhớ; expiration loại key vì TTL đã hết.

**4. `evicted_keys` bằng 0 có nghĩa không có memory pressure không?**

Không. Với `noeviction`, một số write có thể bị từ chối OOM thay vì Redis xóa key.

**5. `expired_keys` tăng có luôn là lỗi không?**

Không. TTL expiration là hành vi bình thường của cache nếu đúng chính sách.

**6. Tại sao phải tính hit ratio theo delta/rate trong 5 phút thay vì toàn bộ lịch sử?**

Vì tổng lịch sử có thể che những thay đổi hoặc sự cố mới xuất hiện.

**7. Redis `keyspace_hits/misses` có phân biệt cache `products` với `users` không?**

Không. Đây là thống kê mức Redis server/node, không trực tiếp phân loại theo Spring cache region.

**8. Nếu Redis GET bị timeout, có nên tăng counter cache miss không?**

Không. Timeout là lỗi dependency và nên được đếm riêng.

**9. Vì sao không nên lấy trung bình trực tiếp hit ratio của nhiều instance?**

Vì mỗi instance có lượng lookup khác nhau. Phải cộng số hit/miss hoặc rate trước khi chia.

**10. `@CacheEvict` có làm Redis `evicted_keys` tăng không?**

Không theo ngữ nghĩa eviction do maxmemory; đó là xóa/invalidation chủ động ở tầng ứng dụng.

**11. Redis Cluster có thể bị memory pressure trên một shard dù tổng Cluster còn RAM không?**

Có. Từng primary/shard quản lý dữ liệu và chịu tải riêng.

**12. `INFO keyspace` với `expires=1000` có nghĩa sẽ có đúng 1000 expiration trong giây tới không?**

Không. Nó chỉ cho biết số key hiện có expiration, không phải lịch hết hạn chi tiết.

**13. Redis keyspace notifications có thể dùng để đếm chính xác mọi expired event qua outage không?**

Không. Pub/Sub không có replay/ACK và trong Cluster thông báo có phạm vi node.

**14. Khi hit ratio giảm, tại sao cần xem cả DB load?**

Để đánh giá cache miss có làm tăng tải nguồn có thẩm quyền và ảnh hưởng API hay không.

**15. Vì sao maxmemory thấp hơn container memory limit vẫn cần headroom?**

Redis còn cần RSS/allocator overhead, buffers, persistence/replication và các chi phí khác ngoài dataset.

**16. Nếu cache hit ratio tăng sau khi đặt TTL dài hơn, đã chắc tối ưu thành công chưa?**

Chưa. Phải kiểm tra dữ liệu stale, memory footprint, eviction và hợp đồng thời hạn nghiệp vụ.

## 33. Ghi nhớ

- **Memory, eviction, expiration và cache hit ratio trả lời những câu hỏi khác nhau**, cần xem cùng nhau mới hiểu hiệu quả Redis cache.
- **`INFO memory`** cung cấp `used_memory`, RSS, peak và maxmemory; **maxmemory không phải giới hạn tuyệt đối của RAM process**.
- **`INFO stats`** cung cấp các counter tích lũy `evicted_keys`, `expired_keys`, `keyspace_hits`, `keyspace_misses`; phải tính delta/rate và xử lý reset.
- **Eviction do áp lực bộ nhớ**, còn **expiration do TTL**. `DEL` và `@CacheEvict` là xóa chủ động, không phải Redis eviction.
- **Hit ratio của Redis node không tương đương hit ratio của từng `@Cacheable` region**. Đo bổ sung tại Spring Cache/Micrometer, phân biệt hit, miss và error.
- **Redis CacheManager statistics có thể là local per-instance**; nhiều instance phải tổng hợp counters theo trọng số lookup.
- **Redis Cluster phải quan sát theo shard/node**, gồm primary/replica và topology; tổng memory không thể thay áp lực trên shard nóng.
- **Không tối ưu tỷ lệ hit một mình**: luôn xét TTL, tính mới dữ liệu, database fallback, p95/p99, OOM và working set.
- **Đặt dashboard/cảnh báo theo SLO và đặc tính workload**; expiration cao hoặc eviction khác 0 không tự động có nghĩa là hệ thống lỗi.

### Tài liệu tham khảo

- [Redis — INFO](https://redis.io/docs/latest/commands/info/).
- [Redis — MEMORY STATS](https://redis.io/docs/latest/commands/memory-stats/).
- [Redis — MEMORY USAGE](https://redis.io/docs/latest/commands/memory-usage/).
- [Redis — Key eviction](https://redis.io/docs/latest/develop/reference/eviction/).
- [Redis — Key expiration](https://redis.io/docs/latest/develop/use/keyspace/).
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/).
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/).
- [Redis — Keyspace notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/).
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html).
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
- [Micrometer — Concepts: Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html).
