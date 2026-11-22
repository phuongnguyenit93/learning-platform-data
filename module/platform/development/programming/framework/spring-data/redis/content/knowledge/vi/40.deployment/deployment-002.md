# Cấu hình giới hạn bộ nhớ và chính sách eviction theo mục đích trong Spring Data Redis

## 1. Vấn đề triển khai: Redis dùng hết bộ nhớ thì điều gì xảy ra?

Redis giữ phần lớn dữ liệu đang phục vụ trong RAM. Khi số lượng key, kích thước value hoặc tải tăng, một Redis instance có thể chạm ngưỡng bộ nhớ. Nếu không có chính sách rõ ràng, ứng dụng Spring Boot có thể gặp các tình huống khó xử lý:

- Cache không ghi được dữ liệu mới.
- Những cache entries đang được dùng nhiều lại bị đẩy ra, gây tăng tải database.
- Session người dùng biến mất sớm, dù TTL chưa kết thúc.
- Rate limit, idempotency key hoặc distributed lock bị loại bỏ, làm hỏng bảo đảm nghiệp vụ.
- Redis process bị hệ điều hành/container OOM-kill vì tổng memory RSS vượt giới hạn, dù đã đặt `maxmemory`.
- Một shard Redis Cluster hết chỗ trong khi những shard khác còn nhiều RAM.
- Replica được promote lên primary có hành vi ghi/eviction khác kỳ vọng vì cấu hình giữa các nodes không nhất quán.

Ví dụ một Spring Boot service có bốn loại key:

```text
Spring Boot
   |
   +-- cache:product:42         -> có thể đọc lại từ PostgreSQL
   +-- session:user:1001        -> trạng thái đăng nhập
   +-- ratelimit:user:1001      -> giới hạn request
   +-- idempotency:order:9001   -> ngăn xử lý đơn hàng trùng
   |
   v
Redis (RAM hữu hạn)
```

Nếu cấu hình `allkeys-lru`, **cả bốn loại key đều có thể trở thành đối tượng bị eviction** khi Redis chịu áp lực bộ nhớ. Tất cả các key đều có prefix khác nhau, nhưng prefix không cung cấp bảo vệ bộ nhớ.

Đây là lý do không thể hỏi chung: “Policy eviction nào tốt nhất cho Redis?”. Câu hỏi đúng hơn là:

> **Dữ liệu nào được phép biến mất trước thời hạn, dữ liệu nào bắt buộc phải giữ cho tới khi hết TTL hoặc được xóa có chủ đích, và khi hết RAM thì ứng dụng chấp nhận mất key hay chấp nhận lỗi ghi?**

Bài này hướng dẫn cấu hình `maxmemory`, lựa chọn `maxmemory-policy`, áp dụng cùng Spring Data Redis/Spring Cache, giám sát và kiểm thử trước khi triển khai production.

## 2. Ba khái niệm phải phân biệt

| Khái niệm | Câu hỏi | Cơ chế |
| --- | --- | --- |
| Giới hạn bộ nhớ | Redis có thể dùng bao nhiêu memory để lưu dữ liệu được tính trong eviction accounting? | `maxmemory` |
| Eviction | Khi vượt ngưỡng bộ nhớ, Redis được phép loại bỏ key nào để có chỗ cho thao tác tiếp theo? | `maxmemory-policy` |
| Expiration/TTL | Một key được coi là hết hạn vào thời điểm nào? | `EXPIRE`, `SET EX/PX`, Spring `Duration` |

Một ví dụ:

```redis
SET cache:product:42 "{...}" EX 300
```

TTL 300 giây có nghĩa key hết hạn theo thời gian được đặt. Nhưng nếu Redis bật `allkeys-lru` và thiếu RAM, key có thể bị **eviction trước 300 giây**.

Ngược lại, một key không có TTL có thể vẫn bị eviction theo `allkeys-lru` hoặc `allkeys-lfu`.

**TTL không phải lời hứa về tuổi thọ tối thiểu.** Nó là giới hạn thời gian tồn tại theo chính sách expiration, trong khi eviction có thể kết thúc sự tồn tại của key sớm hơn dưới một số chính sách.

## 3. maxmemory là gì?

Redis có tham số:

```conf
maxmemory 768mb
```

Đây là ngưỡng Redis dùng để ra quyết định kiểm soát bộ nhớ/eviction, không phải cam kết rằng **RAM/RSS của Redis process luôn nhỏ hơn 768 MB**.

Redis còn có:

- Memory overhead của object, dictionary, allocator.
- Fragmentation của memory allocator.
- Buffers của clients và replication.
- Cơ chế persistence RDB/AOF, background save/rewrite và copy-on-write.
- Memory hệ điều hành, shared libraries, process/runtime khác.
- Các thành phần được loại trừ trong việc tính memory cho eviction ở một số phiên bản/cấu hình.

Vì vậy cần tách:

```text
Redis maxmemory threshold
          !=
Redis process resident memory (RSS)
          !=
Container memory limit
          !=
Total host memory
```

Không đặt `maxmemory` ngang chính xác với giới hạn RAM của container rồi giả định OOM-kill sẽ không xảy ra.

### Redis không có maxmemory thì sao?

Trong nhiều môi trường Redis OSS 64-bit, giá trị `maxmemory 0` có nghĩa không có giới hạn dữ liệu do chính tùy chọn này đặt ra. Nhưng Redis vẫn bị ràng buộc bởi RAM vật lý, cgroups/container, cloud provider quota và giới hạn hệ điều hành.

Nếu không kiểm soát dung lượng, tiến trình vẫn có thể bị kill khi hết bộ nhớ, gây gián đoạn và nguy cơ dữ liệu tùy mức persistence/replication.

Managed Redis có thể đặt giới hạn qua instance size hoặc control plane riêng; cần xem policy của nhà cung cấp, không giả định `CONFIG SET` sẽ được cho phép.

## 4. Vì sao không đặt maxmemory bằng toàn bộ RAM?

Giả sử Redis container có memory limit 4 GiB và dataset có thể tăng nhanh.

Một cấu hình quá sát:

```conf
maxmemory 4gb
```

có thể gây rủi ro vì Redis còn phải dùng memory ngoài dataset/eviction accounting; RDB/AOF background work hoặc COW pages cũng cần headroom.

Một ví dụ minh họa có headroom:

```text
Container memory limit: 4 GiB
maxmemory:             2.5 GiB
remaining headroom:    dành cho RSS overhead, buffers,
                       fragmentation, fork/COW và đột biến
```

**2.5 GiB không phải tỷ lệ chuẩn bắt buộc.** Ngưỡng thực tế cần dựa trên:

1. Redis version và memory accounting.
2. Kích thước dataset, data types và key/value overhead.
3. Peak read/write traffic.
4. Persistence settings và tần suất snapshot/rewrite.
5. Replication topology và client output buffers.
6. Container/cgroup memory limit.
7. Fragmentation/RSS và biến động khi deploy/scale.
8. Memory reserve cho hệ điều hành và process khác nếu cùng host.

Mục tiêu là có **headroom có đo đạc**, không dựa vào một tỷ lệ đoán trước như “luôn dành 10%”.

## 5. Cấu hình maxmemory trong redis.conf

Ví dụ một Redis instance chuyên dùng cho cache:

```conf
port 6379
maxmemory 768mb
maxmemory-policy allkeys-lfu
maxmemory-samples 10
```

Ở đây:

- `maxmemory 768mb`: ngưỡng memory theo Redis.
- `maxmemory-policy allkeys-lfu`: khi thiếu RAM, chọn candidate trong toàn bộ keyspace theo ước lượng tần suất sử dụng.
- `maxmemory-samples 10`: số mẫu tham gia thuật toán xấp xỉ ở những policy tương ứng; số lớn hơn có thể tăng chi phí CPU cho việc chọn key.

Nếu Redis chỉ giữ cache được tái tạo, cho phép eviction có thể phù hợp. Nếu cùng instance còn lưu token/lock/idempotency quan trọng, cấu hình này **có thể không phù hợp**.

### Kiểm tra cấu hình đang áp dụng

```bash
redis-cli -h redis.internal -p 6379 CONFIG GET maxmemory
redis-cli -h redis.internal -p 6379 CONFIG GET maxmemory-policy
redis-cli -h redis.internal -p 6379 CONFIG GET maxmemory-samples
```

Trong managed Redis, `CONFIG GET` có thể bị giới hạn và cấu hình được xem qua portal/API của nhà cung cấp.

## 6. Các policy eviction Redis thường gặp

Redis hỗ trợ các policy quan trọng:

| Policy | Key đủ điều kiện eviction | Cách chọn |
| --- | --- | --- |
| `noeviction` | Không eviction chủ động để giải phóng data keys | Từ chối những write cần thêm memory khi không thể phục vụ |
| `allkeys-lru` | Tất cả keys | Ước lượng key ít được truy cập gần đây |
| `allkeys-lfu` | Tất cả keys | Ước lượng key ít được sử dụng thường xuyên |
| `allkeys-random` | Tất cả keys | Lựa chọn ngẫu nhiên |
| `volatile-lru` | Chỉ keys có expiration | Ước lượng ít được truy cập gần đây |
| `volatile-lfu` | Chỉ keys có expiration | Ước lượng tần suất sử dụng thấp |
| `volatile-random` | Chỉ keys có expiration | Ngẫu nhiên trong nhóm TTL keys |
| `volatile-ttl` | Chỉ keys có expiration | Ưu tiên những key có TTL còn lại ngắn hơn |

**Không được hiểu `volatile-*` là chỉ loại bỏ các key đã hết hạn.** Đây là eviction *trước hạn* trong số các keys có expiration, nhằm giải phóng memory khi thiếu chỗ.

Một số tên policy/chi tiết triển khai có thể phát triển theo Redis version, nhưng các nhóm trên là cơ sở thường gặp để thiết kế triển khai.

## 7. noeviction: ưu tiên giữ key hơn khả năng chấp nhận ghi

Ví dụ:

```conf
maxmemory 1gb
maxmemory-policy noeviction
```

Khi memory được tính vượt ngưỡng và lệnh cần cấp thêm bộ nhớ, Redis có thể từ chối lệnh với lỗi kiểu:

```text
OOM command not allowed when used memory > 'maxmemory'
```

Thông điệp chính xác có thể khác theo Redis version và command.

Các hệ quả:

- Redis không chủ động đẩy các key còn tồn tại theo eviction policy để nhận thêm write.
- Key có TTL **vẫn có thể hết hạn** theo expiration.
- Một số lệnh đọc hoặc lệnh không tăng memory có thể vẫn hoạt động tùy ngữ nghĩa lệnh và trạng thái server.
- Application không được mặc định mọi write đều thành công khi Redis còn `PING`.
- Redis process vẫn có thể chịu OS OOM nếu quản lý memory headroom/storage/buffers không phù hợp.

### noeviction phù hợp khi nào?

Có thể phù hợp cho workload không chấp nhận mất key sớm và muốn **báo lỗi rõ ràng khi capacity hết**, ví dụ một lớp kiểm soát phối hợp có thiết kế failure policy nghiêm ngặt.

Tuy vậy, `noeviction` **không tự biến Redis thành nguồn dữ liệu bền vững**: restart, failover, replication bất đồng bộ, mất disk hoặc hết TTL vẫn có thể làm trạng thái biến mất.

Nếu Redis lưu trạng thái tiền bạc hoặc thanh toán có thẩm quyền, còn cần database/ledger phù hợp, không chỉ `noeviction`.

## 8. allkeys-lru: ưu tiên những key mới được dùng

Ví dụ:

```conf
maxmemory 2gb
maxmemory-policy allkeys-lru
```

Policy này ước lượng least-recently-used trong **toàn bộ keys**.

Thích hợp khi:

- Hầu hết dữ liệu là cache có thể tái tạo.
- Key truy cập gần đây thường có cơ hội được truy cập lại.
- Có nhiều key ít được sử dụng sau khi tạo.
- Chấp nhận eviction trước TTL.
- Miss được xử lý an toàn bởi nguồn dữ liệu chuẩn.

### LRU Redis là gần đúng

Redis sử dụng cơ chế lựa chọn dựa trên mẫu/thuật toán xấp xỉ, không phải một danh sách LRU chính xác có chi phí cập nhật trên mọi key như một mô hình sách giáo khoa.

Vì vậy không được viết test theo giả định “key lâu nhất chắc chắn luôn bị evict đầu tiên”.

Khi chạm ngưỡng, những key vừa được sử dụng có xác suất sống sót cao hơn, nhưng kết quả cụ thể còn chịu sampling, memory usage và workload.

## 9. allkeys-lfu: ưu tiên tần suất sử dụng

Ví dụ:

```conf
maxmemory 2gb
maxmemory-policy allkeys-lfu
```

LFU là least-frequently-used dựa trên bộ đếm/timing xấp xỉ của Redis.

Phù hợp khi:

- Một số key “hot” được truy cập lặp lại rất nhiều.
- Key quan trọng về hiệu năng cần được giữ lâu hơn dù có khoảng ngắt truy cập ngắn.
- Cache có dạng phân phối không đều, ví dụ sản phẩm phổ biến hoặc cấu hình dùng chung.
- Workload và chính sách cập nhật phù hợp với ước lượng tần suất sử dụng.

### LFU không đếm chính xác mọi lần truy cập

Redis LFU dùng cơ chế probabilistic counter và decay theo thời gian. Không suy ra từ metadata LFU rằng một key đã được đọc đúng 10.000 lần.

Một số cấu hình:

```conf
lfu-log-factor 10
lfu-decay-time 1
```

`lfu-log-factor` ảnh hưởng cách bộ đếm LFU tăng theo tần suất; `lfu-decay-time` điều chỉnh nhịp suy giảm theo thời gian. Giá trị cần được thử với workload thực, không chọn chỉ vì một ví dụ.

## 10. LRU và LFU khác nhau như thế nào?

Xét cache sản phẩm:

```text
Product A: được đọc 5.000 lần hôm qua, hôm nay chưa ai đọc
Product B: mới được đọc một lần cách đây một phút
Product C: được đọc đều 100 lần/giờ
```

LRU quan tâm hơn đến **tính gần đây** của lần truy cập. LFU cố gắng giữ những key có **tần suất cao** theo cơ chế decay.

| Tình huống | LRU có thể phù hợp | LFU có thể phù hợp |
| --- | --- | --- |
| Dữ liệu truy cập theo phiên làm việc | Có | Có thể |
| Tin tức bùng nổ ngắn hạn | Có thể | Có thể cần tuning |
| Catalog có một số sản phẩm rất phổ biến | Có | Thường đáng thử |
| Workload truy cập luân phiên nhiều keys | Có | Cần thử |
| Key truy cập một lần rồi không đọc lại | Dễ bị loại khi ít truy cập mới | Có thể bị giảm ưu tiên |
| Truy cập thay đổi theo mùa/ngày | Cần đo | Cần xem decay |

Không có policy luôn tốt nhất. Cần đo hit ratio, evictions, DB fallback load, Redis CPU và latency dưới workload thực.

## 11. allkeys-random: loại ngẫu nhiên từ toàn bộ keys

Ví dụ:

```conf
maxmemory-policy allkeys-random
```

Ưu điểm: đơn giản và ít phụ thuộc giả định về locality/tần suất.

Điểm hạn chế: có thể loại cả key đang được sử dụng nhiều vì không chọn theo recent/frequent access.

Có thể cân nhắc khi:

- Các key có xác suất truy cập gần tương đương.
- Workload không có locality rõ.
- Đơn giản hóa lựa chọn candidate quan trọng hơn tối ưu hit ratio.
- Có kết quả benchmark chứng minh phù hợp.

Với cache phân bố truy cập không đều, LRU/LFU thường đáng đánh giá trước random. Nhưng quyết định production nên dựa trên số liệu, không chỉ trực giác.

## 12. volatile-lru và volatile-lfu: chỉ chọn key có TTL

Ví dụ:

```conf
maxmemory 1gb
maxmemory-policy volatile-lru
```

Policy này **chỉ được phép eviction các keys có expiration**, không chọn key không TTL làm candidate.

Ví dụ:

```text
config:global       -> không TTL
cache:product:42    -> TTL 5 phút
cache:product:99    -> TTL 5 phút
```

Khi thiếu bộ nhớ, những keys có TTL là đối tượng eviction; `config:global` không thuộc nhóm candidate.

### Bẫy quan trọng

Nếu cùng instance có:

```text
lock:order:42             TTL 30 giây
idempotency:payment:9001  TTL 24 giờ
session:user:1001         TTL 20 phút
cache:product:42          TTL 5 phút
```

thì **cả lock, idempotency key, session và cache đều đủ điều kiện eviction** dưới policy `volatile-lru`/`volatile-lfu`.

Vì vậy `volatile-*` không thể phân biệt “TTL key nào chỉ là cache” và “TTL key nào bảo vệ nghiệp vụ”.

**Có TTL không đồng nghĩa được phép mất trước TTL.** Đây là một sai lầm triển khai rất nghiêm trọng.

## 13. volatile-random và volatile-ttl

### volatile-random

```conf
maxmemory-policy volatile-random
```

Redis chọn ngẫu nhiên trong nhóm key có expiration. Nó không tự ưu tiên cache key, session hay token.

### volatile-ttl

```conf
maxmemory-policy volatile-ttl
```

Policy ưu tiên những keys có TTL còn lại ngắn hơn trong nhóm keys có expiration. Ý tưởng là chọn một key sắp hết hạn sớm để giải phóng chỗ.

Nhưng điều đó **không bảo đảm**:

- Chỉ key thật sự đã hết hạn mới bị xóa.
- Một session có TTL ngắn sẽ không bị đẩy sớm.
- Key quan trọng có TTL dài chắc chắn an toàn.
- Mọi key đều có TTL.
- Khi không có TTL candidates, Redis luôn tìm ra cách giải phóng đủ RAM.

`volatile-ttl` có thể phù hợp khi toàn bộ expiring keys đều có thể bị loại sớm và TTL còn lại là tín hiệu ưu tiên hữu ích. Nó không phải giải pháp bảo vệ state nghiệp vụ critical chỉ bằng prefix.

## 14. Khi volatile policy không còn key có TTL

Một tình huống:

```text
maxmemory 512mb
maxmemory-policy volatile-lru

Key A: 250 MB, không TTL
Key B: 250 MB, không TTL
```

Khi không có key phù hợp để eviction, Redis không thể tiếp tục loại các key không TTL bằng `volatile-lru`. Nếu thao tác cần tăng memory vượt ngưỡng, Redis có thể từ chối write theo behavior tương tự `noeviction`.

Điều này có thể xảy ra khi:

- Cache adapter quên gắn TTL.
- Có nhiều keys không TTL chiếm gần hết memory.
- Các keys có TTL đã bị loại hết.
- Dữ liệu được ghi bằng một đường khác không thực hiện expiration.

Đừng xem `volatile-*` là bảo đảm hệ thống luôn còn chỗ cho những key mới. Cần quan sát tỷ lệ keys có TTL và kiểm tra producer nào tạo ra keys không TTL.

## 15. TTL và eviction không phải một sự kiện giống nhau

Redis có những lý do key biến mất khác nhau:

- **Expiration:** TTL đã hết.
- **Eviction:** Redis chủ động đẩy key trước hạn theo memory policy.
- **Application delete:** `DEL`, `UNLINK`, xóa từ Spring Cache.
- **Logical overwrite:** ứng dụng ghi đè hoặc đổi trạng thái.
- **Failover/replication loss:** state thay đổi do promotion và lag.
- **Restart không có persistence đầy đủ:** dữ liệu không được phục hồi.
- **Admin operation:** xóa dữ liệu, flush hoặc thay đổi topology.

Đừng chỉ thấy cache miss rồi kết luận “TTL đã hết”. Cần xem `evicted_keys`, `expired_keys`, thời điểm ghi, Redis metrics và logs.

### Keyspace notifications

Redis có thể phát events về `expired` hoặc `evicted` nếu cấu hình keyspace notifications phù hợp, nhưng Pub/Sub events có thể bị mất khi subscriber offline.

Không dùng Redis expired/evicted notifications làm nguồn nghiệp vụ duy nhất cho công việc bắt buộc phải thực hiện. Nếu cần deadline bền vững, dùng scheduler/queue/ledger có khả năng đối soát.

## 16. Quy tắc chọn policy theo mục đích dữ liệu

| Mục đích Redis | Cho phép key biến mất sớm? | Định hướng policy |
| --- | --- | --- |
| Cache trang sản phẩm có thể tái tạo | Có | `allkeys-lfu` hoặc `allkeys-lru` |
| Cache truy vấn đọc nhiều, nguồn chuẩn ở DB | Có | `allkeys-lru`/`allkeys-lfu`, benchmark |
| Cache transient dùng một lần | Có | Có thể xem `allkeys-random` nếu workload phù hợp |
| Session login | Thường không mong mất trước TTL | Tách instance hoặc chọn policy bảo vệ phù hợp |
| Idempotency keys | Không nếu dùng chống xử lý trùng | Ưu tiên không eviction, capacity/TTL/nguồn chuẩn |
| Distributed locks | Không được mất do eviction trước TTL | Tách instance/không eviction, xem toàn bộ lock semantics |
| Rate limiter critical | Không được fail-open không kiểm soát | Tách instance, policy lỗi rõ |
| Queue/Redis Streams quan trọng | Không tự cho phép mất dữ liệu vì eviction | Đánh giá durability, retention, noeviction/kiến trúc khác |
| Redis là source of truth | Mất key không thể tái tạo là rủi ro cao | Không chỉ dựa eviction; kiến trúc lưu trữ phù hợp |

Bảng là định hướng thiết kế. `noeviction` không tự giải quyết persistence hoặc RPO, còn cache có thể có yêu cầu đặc biệt về tỷ lệ miss và latency.

## 17. Tại sao trộn cache và critical state rất nguy hiểm?

Một instance dùng:

```text
cache:catalog:*          700 MB
session:*                100 MB
lock:*                     5 MB
idempotency:*             25 MB
```

Nếu chọn `allkeys-lru`, bất kỳ key nào có thể bị eviction, bao gồm lock và idempotency.

Nếu chọn `volatile-lru`, các lock/session/idempotency keys thường **cũng có TTL**, nên vẫn là candidates.

Nếu chọn `noeviction`, cache tự tăng sẽ khiến các writes quan trọng bị lỗi OOM khi đạt memory threshold.

Như vậy một pool chung có thể khiến cả ba lựa chọn đều có đánh đổi khó chấp nhận.

### Giải pháp: tách Redis deployment theo lớp dữ liệu

Ví dụ:

```text
Spring Boot
    |
    +--> Redis Cache Pool
    |      maxmemory-policy allkeys-lfu
    |      có thể evict trước TTL
    |      cache miss -> source of truth
    |
    +--> Redis Coordination Pool
           maxmemory-policy noeviction
           capacity được giám sát chặt
           có policy khi write fail
```

Đây là ví dụ kiến trúc, không có nghĩa mỗi key type phải có một Redis cluster riêng. Mức cô lập phụ thuộc chi phí, rủi ro và vận hành.

**Redis logical databases (`SELECT 0`, `SELECT 1`) hoặc key prefixes không tạo ra giới hạn RAM và eviction policy độc lập** trong cùng Redis instance. Nếu cần chính sách khác nhau, thông thường cần tách Redis instances/deployments (hoặc dùng các cơ chế isolation được nền tảng cung cấp và đã xác minh).

## 18. Cache thuần: ví dụ lựa chọn allkeys-lfu

Yêu cầu:

- PostgreSQL là nguồn chuẩn.
- Redis chỉ lưu sản phẩm, bài viết và kết quả truy vấn.
- Cache miss có thể tính lại.
- Một số key hot bị đọc lặp nhiều lần.
- Giới hạn RAM 1.5 GiB đã được chọn sau capacity testing.

Cấu hình minh họa:

```conf
maxmemory 1536mb
maxmemory-policy allkeys-lfu
maxmemory-samples 10
lfu-log-factor 10
lfu-decay-time 1
```

Spring app vẫn cần:

- TTL cho stale-data control.
- Serialization/versioning ổn định.
- Tránh cache stampede khi evictions nhiều.
- Fallback database có giới hạn tải.
- Theo dõi hit ratio và số evictions.
- Capacity plan và thí nghiệm với LRU.

LFU không đảm bảo key hot sống vĩnh viễn; nó chỉ thay đổi cách ưu tiên trong điều kiện memory pressure.

## 19. Session: eviction trước TTL là lỗi trải nghiệm hoặc an ninh

Một session có thể được đặt TTL:

```redis
SET session:user:1001 "..." EX 1800
```

Nếu session nằm trong Redis cache pool với `allkeys-*`, Redis có thể evict trước 30 phút khi thiếu chỗ.

Hệ quả:

- Người dùng bị logout đột ngột.
- Một phần session state mất, làm phát sinh lỗi không nhất quán.
- Quá trình đăng nhập có thể tạo thêm tải.
- Nếu session chứa security context, cần đánh giá hành vi khi thiếu key: thường phải từ chối/đòi đăng nhập lại, không tự khôi phục quyền từ dữ liệu không đáng tin.

Một Redis session deployment nên có capacity headroom và policy được chọn với mục tiêu **không mất session trước TTL**, hoặc chấp nhận rõ khả năng mất session nếu business cho phép.

`noeviction` là một hướng nhưng có thể khiến tạo/cập nhật session mới lỗi khi hết RAM. Application phải xử lý lỗi đó rõ ràng, không “bịa session thành công”.

## 20. Distributed lock: eviction có thể phá vỡ tính đúng

Giả sử:

```redis
SET lock:order:42 worker-A NX PX 30000
```

Worker A tin rằng mình có lock 30 giây. Nếu Redis cho phép eviction key lock sau 3 giây:

```text
T0 Worker A tạo lock và bắt đầu xử lý
T3 Redis evicts lock vì memory pressure
T4 Worker B tạo lock cùng tên và bắt đầu xử lý
T5 Cả A và B cùng tác động lên tài nguyên
```

Đây là rủi ro double processing hoặc race condition.

**TTL của lock là giới hạn an toàn thời gian, không phải cho phép eviction trước hạn.** Với những lock quan trọng, cần cô lập dữ liệu, quản lý capacity, dùng owner token/fencing hoặc một cơ chế điều phối có hợp đồng phù hợp.

Dù `noeviction`, Redis failover và replication bất đồng bộ vẫn có những failure cases riêng cho lock. Không dùng eviction policy như lời bảo đảm tuyệt đối cho distributed lock correctness.

## 21. Idempotency keys: eviction có thể tạo tác dụng phụ trùng

Một service thanh toán xử lý request ID:

```text
idempotency:payment:req-123 -> ALREADY_PROCESSED
TTL 24 giờ
```

Nếu key bị evict sau 2 giờ vì cache pressure, cùng request ID được gửi lại có thể bị coi là request mới.

Có thể dẫn tới:

- Thực thi một side effect lần nữa.
- Tạo thêm order/job/message.
- Sai lệch counter hoặc double charge nếu không có ledger độc lập.

Vì vậy idempotency state quan trọng không nên chỉ nằm trong Redis eviction pool; có thể cần lưu record kết quả ở database có thẩm quyền và đồng bộ cache để tăng tốc.

`volatile-*` cũng không bảo vệ idempotency key vì nó có TTL. Chính sách phải dựa vào **ý nghĩa dữ liệu**, không phải sự hiện diện của expiration.

## 22. Rate limiting: chọn fail-open/fail-closed có chủ đích

Rate limiter Redis thường dùng counter/window TTL:

```text
rate:user-42:window-123 -> 40
TTL 60 giây
```

Với `allkeys-*` hoặc `volatile-*`, key có thể bị evict sớm, khiến counter trở về 0 và user nhận thêm quota ngoài ý định.

Có thể chấp nhận đối với limiter mang tính bảo vệ tải mềm; có thể không chấp nhận với kiểm soát abuse nghiêm ngặt.

Nếu dùng `noeviction`, command tăng counter có thể bị từ chối khi hết memory.

Application cần xác định:

| Redis lỗi | Mục tiêu ưu tiên | Chính sách cân nhắc |
| --- | --- | --- |
| Cache sản phẩm | Tính sẵn sàng đọc | Fallback DB có kiểm soát |
| Rate limit mềm | Trải nghiệm người dùng | Fail-open có giới hạn và monitoring |
| Rate limit chống abuse | Ngăn vượt quota | Fail-closed hoặc cơ chế thay thế |
| OTP/login attempts | Security correctness | Không mặc định chấp nhận request |
| Lock/coordination | Tính đúng của đồng bộ | Không coi Redis key vắng là đủ bằng chứng an toàn |

Không có một chính sách lỗi chung cho mọi Redis use case.

## 23. Redis Streams và queues

Redis Streams hoặc lists có thể được dùng làm queue. Nếu dữ liệu hàng đợi không thể mất, không được chọn eviction policy chỉ vì muốn “Redis luôn tiếp tục nhận message”.

Ví dụ nguy hiểm: `allkeys-lru` có thể làm biến mất những key chứa dữ liệu queue khi thiếu RAM, phá vỡ khả năng xử lý đầy đủ. Cơ chế pending entries, consumer groups và retries không thay thế durable storage hay backup.

Cần cân nhắc:

- `noeviction` và capacity/quota.
- Stream trimming/retention theo chính sách riêng.
- Persistence/replication phù hợp.
- Idempotency của consumer.
- Outbox/queue bền vững bên ngoài nếu yêu cầu không bỏ sót.
- Alert khi write bị từ chối vì memory.
- Mục tiêu RPO/RTO rõ ràng.

**Trimming theo policy của queue** không giống Redis memory eviction tùy ý. Một queue có retention có chủ đích phải xác định được điều gì được xóa và khi nào.

## 24. maxmemory và Spring Boot là hai lớp cấu hình khác nhau

Spring Data Redis/Spring Boot quyết định **cách application kết nối và thao tác**:

```yaml
spring:
  data:
    redis:
      host: redis-cache.internal
      port: 6379
      timeout: 3s
```

Redis server quyết định giới hạn bộ nhớ và eviction:

```conf
maxmemory 768mb
maxmemory-policy allkeys-lru
```

**Không được giả định Spring Boot property `spring.data.redis.*` tự đặt maxmemory trên Redis server.**

Ngay cả khi Java có quyền gửi `CONFIG SET`, việc thay đổi policy toàn Redis từ một service ứng dụng có thể ảnh hưởng các service khác. Cấu hình memory nên thuộc lớp **infrastructure/ops** như Redis config, Helm chart, Operator, Terraform hoặc managed-service parameter group.

## 25. Spring Data Redis: luôn đặt TTL cho cache phù hợp

Một service dùng `StringRedisTemplate`:

```java
package com.example.cache;

import java.time.Duration;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheWriter {

    private final StringRedisTemplate redis;

    public ProductCacheWriter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void put(String productId, String json) {
        redis.opsForValue().set(
            "cache:product:" + productId,
            json,
            Duration.ofMinutes(5)
        );
    }

    public String get(String productId) {
        return redis.opsForValue().get(
            "cache:product:" + productId
        );
    }
}
```

TTL 5 phút giải quyết freshness và eventual cleanup. Nó **không giữ key ít nhất 5 phút** nếu server bật `allkeys-*`/`volatile-*` cho key đó.

Với ứng dụng cache-aside:

```text
GET cache -> hit -> trả snapshot
          -> miss -> đọc database -> ghi cache TTL -> trả snapshot
```

Ứng dụng cần chấp nhận cache miss do TTL **hoặc** eviction và thiết kế đường fallback phù hợp.

## 26. Spring Cache với cấu hình TTL mặc định

Nếu dùng Spring Cache abstraction:

```java
@Service
public class ProductQueryService {

    private final ProductRepository products;

    public ProductQueryService(ProductRepository products) {
        this.products = products;
    }

    @Cacheable(cacheNames = "productById", key = "#id")
    public ProductView findById(String id) {
        return products.findById(id).orElseThrow();
    }
}
```

Khi Spring Boot dùng Redis CacheManager, có thể đặt TTL mặc định ở phiên bản hỗ trợ:

```yaml
spring:
  cache:
    type: redis
    redis:
      time-to-live: 10m
      cache-null-values: false
```

**Lưu ý:** Đây là **TTL mà Spring Cache đặt trên entries**, không phải server `maxmemory`. Cấu hình eviction của Redis vẫn được quản lý ở phía Redis server.

Phải bật caching/proxy phù hợp, ví dụ `@EnableCaching` khi project yêu cầu; annotation không tự hoạt động trên object được tạo bằng `new` ngoài Spring proxy.

## 27. TTL theo từng cache bằng RedisCacheManager

Mỗi loại cache có nhu cầu freshness khác nhau.

Ví dụ:

```java
package com.example.cache;

import java.time.Duration;
import java.util.Map;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class RedisCachingConfig {

    @Bean
    public RedisCacheManager redisCacheManager(
            RedisConnectionFactory factory) {

        RedisCacheConfiguration defaults =
            RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(10))
                .disableCachingNullValues();

        Map<String, RedisCacheConfiguration> perCache =
            Map.of(
                "productById",
                defaults.entryTtl(Duration.ofMinutes(5)),
                "publicConfig",
                defaults.entryTtl(Duration.ofMinutes(30))
            );

        return RedisCacheManager.builder(factory)
            .cacheDefaults(defaults)
            .withInitialCacheConfigurations(perCache)
            .build();
    }
}
```

Nếu ứng dụng cần lưu object JSON, hãy cấu hình value serializer phù hợp với DTO/schema và bảo mật dữ liệu; default serializer của một số Spring Data Redis configurations có thể không phù hợp cho triển khai đa ngôn ngữ hoặc deployment nhiều phiên bản.

Các cache entries có TTL khác nhau **không có memory quota riêng**. Redis eviction policy vẫn áp dụng trên instance chung.

Nếu vừa tự định nghĩa `RedisCacheManager` vừa đặt các `spring.cache.redis.*` properties, cần hiểu auto-configuration không tự đảm bảo áp dụng mọi property vào custom bean.

## 28. Không nhầm key prefix với quota bộ nhớ

Spring Cache có thể tạo các key dạng:

```text
productById::42
publicConfig::feature-x
```

Còn `StringRedisTemplate` có thể dùng:

```text
cache:product:42
cache:config:feature-x
```

Prefix giúp:

- Tránh đụng key.
- Phân nhóm và cleanup có kiểm soát.
- Quan sát nguồn tạo key.
- Version schema/serializer.
- Phân biệt môi trường/tenant khi cần.

Nhưng prefix **không**:

- Cung cấp namespace memory cap.
- Áp dụng eviction policy riêng.
- Bảo vệ key khỏi `allkeys-*`.
- Bảo đảm cache name này được giữ ưu tiên hơn cache name khác.
- Tạo isolation giống một Redis process riêng.

Nếu hai nhóm dữ liệu cần chính sách eviction khác nhau, tách deployment/instance hoặc dùng capability isolation được platform hỗ trợ và đã kiểm chứng.

## 29. Container/Kubernetes: cgroups và memory headroom

Trong Kubernetes, một container Redis có thể có:

```yaml
resources:
  requests:
    memory: "2Gi"
  limits:
    memory: "3Gi"
```

Đó là giới hạn hạ tầng của container, không phải Redis `maxmemory`.

Một Redis config riêng có thể đặt:

```conf
maxmemory 2gb
maxmemory-policy allkeys-lru
```

**Các con số minh họa, không phải template an toàn cho mọi workload.** Cần đo RSS, allocator fragmentation, replication buffers, client buffers và persistence fork/COW.

Một sơ đồ:

```text
Container memory limit
    |
    +-- Redis managed data / maxmemory accounting
    +-- Redis process overhead
    +-- client/output/replication buffers
    +-- memory allocator fragmentation
    +-- persistence background activity (fork/COW)
    +-- OS/runtime overhead trong giới hạn liên quan
```

Nếu giới hạn container quá thấp, process có thể bị OOM-kill trước khi Redis eviction giải phóng đủ bộ nhớ hoặc trong lúc background save.

### Ephemeral filesystem và persistence

Eviction giải quyết RAM pressure, không thay thế RDB/AOF/persistence. Nếu Redis lưu dữ liệu phải phục hồi sau restart, cần quản lý disk/volume và backup riêng. Một `PersistentVolume` cũng không thay memory headroom hoặc policy phù hợp.

## 30. Replication làm maxmemory phức tạp hơn

Ở topology primary–replicas:

```text
Redis primary A ----replication----> Replica B
       |                                  |
   maxmemory A                        maxmemory B
   policy A                           policy B
```

Mỗi Redis process có config và memory usage riêng. Replication gửi thay đổi từ primary sang replicas, nhưng không có nghĩa memory/RSS ở hai nodes bằng nhau ở mọi thời điểm.

Khi primary evict một key, tác động xóa được truyền sang replicas theo cơ chế replication phù hợp. Replica có thể vẫn chậm do replication bất đồng bộ.

Một số Redis versions/configurations có `replica-ignore-maxmemory` khiến replica thường bỏ qua quyết định maxmemory eviction cục bộ trong vai trò replica. Sau failover, node được promote trở thành primary và có thể phải thực thi eviction policy của **chính process đó**.

Vì vậy cần:

- Đồng bộ cấu hình memory policy có chủ đích giữa các nodes có khả năng được promote.
- Giám sát used memory/RSS cả primary và replicas.
- Xác nhận behavior của Redis version với `replica-ignore-maxmemory`.
- Tránh chỉ thử memory pressure trên primary ban đầu.
- Test node sau promotion có còn headroom và policy đúng không.

## 31. Sentinel failover và memory policy

Redis Sentinel giúp promote một replica thành master khi đáp ứng quorum/election conditions. Nó **không tự biến maxmemory policy trên replica thành chính sách chuẩn của primary cũ**.

Ví dụ:

```text
Trước:
  Redis A primary: maxmemory 1gb / allkeys-lfu
  Redis B replica: maxmemory 512mb / noeviction

Failover:
  B được promote thành primary
```

Nếu B không được cấu hình phù hợp với tải và dữ liệu sau promotion, ứng dụng có thể thấy write failures hoặc eviction behavior khác.

Monitoring cần xem:

- Master identity hiện tại.
- `CONFIG GET maxmemory` và `maxmemory-policy` của node hiện tại.
- Used memory/RSS sau promotion.
- Eviction/write error rate sau failover.
- Read fallback/database load.
- Replica sync và persistence.

**Đừng coi việc một `SENTINEL switch-master` event xảy ra là bằng chứng ứng dụng tiếp tục hoạt động tốt dưới cùng memory budget.**

## 32. Redis Cluster: maxmemory theo từng primary/shard

Redis Cluster sharding keyspace trên 16.384 hash slots. Giả sử có ba primaries:

```text
Primary A: 1 GiB memory limit, slots A
Primary B: 1 GiB memory limit, slots B
Primary C: 1 GiB memory limit, slots C
```

`maxmemory` thường được cấu hình trên **từng Redis node**, không phải một global pool 3 GiB tự cân bằng mọi key.

Nếu shard A nhận nhiều hot keys hoặc các payload lớn, nó có thể chạm memory pressure trong khi B/C còn trống.

Những điều cần theo dõi:

- Used memory / maxmemory **theo từng primary**.
- Eviction rate theo shard.
- Hit/miss/fallback rate cho key thuộc shard.
- Redis Cluster slot ownership.
- Hot key hoặc hot hash tag.
- Memory pressure trên replica sau failover.
- Khả năng reshard/scale-out và ảnh hưởng migration.

Thêm replica **không tăng dung lượng logical dataset** của shard; replicas sao chép dữ liệu, không chia keyspace thành shards mới.

Thêm primary và reshard có thể phân phối lại slots, nhưng một hot key vẫn thuộc một slot; không tự tách key nóng thành nhiều nodes.

## 33. Hash tags có thể làm một shard hết RAM sớm

Redis Cluster dùng hash tags:

```text
cart:{user-42}:items
cart:{user-42}:total
```

Hai keys vào cùng hash slot. Đây là tính năng hữu ích cho multi-key operations/Lua cần cùng slot.

Nhưng nếu mọi key dùng cùng tag:

```text
cache:{global}:product:1
cache:{global}:product:2
cache:{global}:product:3
```

toàn bộ workload có thể dồn vào một slot/shard, gây memory imbalance và eviction tập trung.

**Không dùng một hash tag toàn cục chỉ để tránh `CROSSSLOT`.** Phân phối hash tags theo aggregate cần tính nguyên tử, đồng thời đo slot distribution/hotspots.

## 34. Memory metrics: INFO memory

Lệnh:

```bash
redis-cli -h redis-cache.internal -p 6379 INFO memory
```

Các trường quan trọng thường gặp:

| Trường | Ý nghĩa |
| --- | --- |
| `used_memory` | Lượng memory Redis allocator sử dụng theo accounting nội bộ |
| `used_memory_human` | Dạng dễ đọc của used_memory |
| `used_memory_rss` | Memory resident được OS báo |
| `used_memory_peak` | Đỉnh memory nội bộ đã ghi nhận |
| `maxmemory` | Ngưỡng cấu hình |
| `maxmemory_policy` | Chính sách eviction đang dùng |
| `used_memory_dataset` | Phần ước lượng dataset |
| `used_memory_overhead` | Phần overhead theo Redis metrics |
| `mem_fragmentation_ratio` | Một chỉ số liên quan fragmentation/RSS, cần diễn giải cẩn trọng |
| `mem_not_counted_for_evict` | Memory không tính vào eviction budget theo Redis |
| `allocator_frag_ratio` | Tín hiệu phân mảnh allocator ở những versions hỗ trợ |

Không phải phiên bản Redis nào cũng có đầy đủ trường giống nhau.

### RSS lớn hơn maxmemory có phải lỗi?

Không nhất thiết. `maxmemory` không phải hard cap của RSS. Fragmentation, client/replication buffers, persistence activity và memory accounting có thể khiến RSS cao hơn.

**Nhưng RSS gần hoặc vượt container memory limit là nguy cơ cần hành động**, kể cả khi data memory còn thấp hơn `maxmemory`.

Theo dõi cả:

```text
used_memory
used_memory_rss
maxmemory
used_memory_peak
mem_not_counted_for_evict
container_working_set / cgroup memory
```

## 35. INFO stats: theo dõi eviction và cache misses

Lệnh:

```bash
redis-cli -h redis-cache.internal -p 6379 INFO stats
```

Những trường thường cần:

- `evicted_keys`: số keys bị eviction do memory policy, thường là bộ đếm từ khi process/metric reset.
- `expired_keys`: số keys được Redis expiration.
- `keyspace_hits`: số lần key lookup thành công theo định nghĩa Redis stats.
- `keyspace_misses`: số lần key lookup không tìm thấy.
- Counters về connections/commands/latency khác có thể hỗ trợ chẩn đoán.

**Phân biệt eviction và expiration:**

```text
evicted_keys tăng -> Redis đang loại key vì memory pressure
expired_keys tăng -> key đang hết TTL theo cơ chế expiration
```

Không thể chỉ dùng `keyspace_hits/misses` để kết luận cache-aside hit ratio nghiệp vụ hoàn toàn chính xác, vì Redis còn nhiều thao tác đọc key từ các consumer khác nhau và command semantics ảnh hưởng cách thống kê.

Tại tầng Spring Boot, nên đo cache hit/miss **theo cache name/use case** nếu cần điều hành tải downstream.

## 36. Những công cụ memory khác

Một số lệnh hữu ích:

```bash
redis-cli -h redis.internal -p 6379 MEMORY STATS
redis-cli -h redis.internal -p 6379 MEMORY USAGE cache:product:42
redis-cli -h redis.internal -p 6379 MEMORY DOCTOR
redis-cli -h redis.internal -p 6379 INFO keyspace
```

Ý nghĩa:

- `MEMORY STATS`: breakdown memory usage.
- `MEMORY USAGE`: ước lượng memory cho một key cụ thể, có tùy chọn samples cho một số data types.
- `MEMORY DOCTOR`: gợi ý chẩn đoán theo heuristics của Redis.
- `INFO keyspace`: số lượng keys và keys có expiration theo database.

Không nên quét toàn bộ production keyspace bằng cách lặp `MEMORY USAGE` trên mọi key lúc tải cao nếu chưa tính chi phí. Lệnh `KEYS *` có thể gây gián đoạn trên dataset lớn; nếu cần duyệt keys, dùng `SCAN` có kiểm soát và hiểu tính nhất quán khi keyspace thay đổi.

## 37. Dashboard cache memory

Một dashboard thực dụng có ít nhất bốn khu vực.

### Dung lượng

```text
used_memory / maxmemory
used_memory_rss / container_limit
used_memory_peak
mem_not_counted_for_evict
```

### Eviction và expiration

```text
evicted_keys rate
expired_keys rate
cache key count
keys-with-expiration ratio
```

### Tác động tới Spring app

```text
cache hit ratio by cache
cache miss rate
database fallback rate
Redis command latency p95/p99
Redis write errors / OOM exceptions
HTTP latency / error rate
```

### Topology và phục hồi

```text
node role / master identity
replication lag
memory per Redis Cluster shard
failover event count
eviction spike after promotion
```

Tên metric ở trên là mô tả semantics, không mặc định tồn tại đúng tên trong exporter. Cần xác nhận metric names và labels của Redis exporter/Micrometer đang dùng.

## 38. Alert khi eviction tăng

Một cảnh báo kiểu:

```text
evicted_keys rate > 0
```

không phải lúc nào cũng là incident. Trong cache pool bật `allkeys-*`, eviction **có thể là hành vi thiết kế bình thường**.

Điều cần xem là **hệ quả**:

- Eviction rate có tăng bất thường so với baseline không?
- Cache hit ratio có giảm mạnh không?
- Database fallback có tăng không?
- API p95/p99 latency có tăng không?
- CPU Redis có cao khi sampling eviction không?
- Memory RSS có tiến sát container limit không?
- Có key critical bị đặt nhầm trong cache pool không?

Với coordination pool dùng `noeviction`, `evicted_keys` tăng có thể là dấu hiệu cấu hình bị thay đổi hoặc trỏ nhầm instance, cần điều tra khác.

### Cảnh báo OOM write

Nếu Redis từ chối write vì memory, ứng dụng phải ghi nhận rõ loại lỗi. Đừng gom OOM của Redis vào chung lỗi timeout hoặc cache miss.

Với key không được phép mất, write reject phải có policy **fail request hoặc retry có điều kiện**, không tự coi thao tác đã thành công.

## 39. Theo dõi cache hit ratio cho đúng

Một tỷ lệ có thể định nghĩa:

```text
hit_ratio =
    hits / (hits + misses)
```

Nhưng phải biết “hits/misses” lấy từ đâu:

- Redis `INFO stats` theo command keyspace lookup.
- Spring Cache abstraction/cache manager metrics.
- Business service tự đo cache-aside hit/miss.

Chúng có thể khác nhau vì:

- Một request gọi nhiều Redis commands.
- Redis còn lưu keys ngoài cache.
- Một cache miss có thể dẫn tới nhiều Redis lookups.
- Spring local caches nằm phía trước Redis.
- Application fallback hay bypass Redis.
- Một key bị evict có thể được warm lại nhanh.

Để điều chỉnh `allkeys-lru`/`allkeys-lfu`, nên dùng metric gần với **workload ứng dụng và chi phí miss**, không chỉ một con số Redis toàn instance.

## 40. Eviction và cache stampede

Giả sử key nóng `cache:product:42` bị evict:

```text
1.000 requests gần đồng thời
    |
    v
GET cache:product:42 -> MISS
    |
    +--> 1.000 truy vấn PostgreSQL
```

Điều này gây **cache stampede**, ngay cả khi database là nguồn chuẩn.

Các biện pháp có thể cân nhắc:

- Request coalescing/single-flight theo key.
- Cache local ngắn hạn cho dữ liệu không nhạy consistency.
- TTL jitter để giảm các đợt expire đồng thời.
- Stale-while-revalidate khi hợp đồng dữ liệu cho phép.
- Warm-up các key nóng sau deploy/failover.
- Giới hạn số fallback requests.
- Caching negative results có thời gian ngắn nếu nghiệp vụ cho phép.
- Scale Redis hoặc tăng headroom nếu eviction là do thiếu capacity.

TTL jitter giải quyết đồng loạt hết hạn, **không làm biến mất memory pressure do tổng dataset vượt ngưỡng**.

## 41. TTL jitter không phải thay thế capacity planning

Ví dụ Spring code gắn TTL jitter:

```java
package com.example.cache;

import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CatalogCacheWriter {

    private final StringRedisTemplate redis;

    public CatalogCacheWriter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void cache(String id, String json) {
        long extraSeconds =
            ThreadLocalRandom.current().nextLong(0, 31);

        Duration ttl =
            Duration.ofSeconds(300 + extraSeconds);

        redis.opsForValue().set(
            "cache:catalog:" + id,
            json,
            ttl
        );
    }
}
```

Ví dụ này phân tán TTL trong khoảng khoảng 5 phút đến 5 phút 30 giây để tránh nhiều keys có cùng expiration deadline.

Không áp dụng jitter tùy tiện cho token, OTP, idempotency hoặc lock nếu expiration time có ý nghĩa nghiệp vụ bắt buộc.

Thay đổi TTL cũng không làm redis capacity tự tăng; cần đảm bảo working set phù hợp giới hạn bộ nhớ.

## 42. Chọn TTL dựa trên freshness và chi phí tái tạo

Với cache có thể eviction:

| Loại dữ liệu | Điều cân nhắc khi chọn TTL |
| --- | --- |
| Product catalog | Mức chấp nhận stale, tần suất cập nhật |
| Giá sản phẩm | Cần kiểm tra nguồn chuẩn khi quyết định thanh toán |
| Feature flags | Độ trễ phản ánh thay đổi, fallback |
| Dữ liệu public tĩnh | TTL có thể dài hơn nếu invalidation hiệu quả |
| Kết quả truy vấn đắt | Chi phí re-compute, dữ liệu đầu vào thay đổi |
| Negative cache | Tránh giữ “không tồn tại” quá lâu khi entity mới xuất hiện |

TTL là lựa chọn consistency/freshness; eviction policy là lựa chọn ứng phó memory pressure. Chúng phối hợp nhưng không thay thế nhau.

Ví dụ TTL 30 phút + `allkeys-lfu`: entry có thể hết hạn sau 30 phút hoặc bị evict sớm khi thiếu memory.

## 43. Redis eviction không bảo vệ tính đúng của nguồn chuẩn

Một kiến trúc an toàn cho cache:

```text
Spring API
    |
    +-- GET Redis cache
    |      |
    |      +-- hit -> trả snapshot phù hợp policy
    |      |
    |      +-- miss / evicted
    |             |
    |             v
    +---------- PostgreSQL source of truth
                  |
                  v
             SET Redis cache TTL
```

Nếu Redis cache mất tất cả dữ liệu, business state vẫn còn ở database. Tuy nhiên có thể chịu chi phí warm-up.

Nếu Redis là nơi duy nhất lưu giỏ hàng, session hoặc reservation, eviction sẽ là **mất trạng thái**, không chỉ giảm hiệu năng. Phải định nghĩa rõ “nguồn chuẩn” trước khi chọn policy.

## 44. Vì sao noeviction vẫn cần kế hoạch khi hết RAM?

Một Redis coordination pool:

```conf
maxmemory 512mb
maxmemory-policy noeviction
```

Khi bộ nhớ vượt ngưỡng:

- Write tạo key mới có thể thất bại.
- Tăng counters hoặc cập nhật data structures có thể bị lỗi tùy command.
- Một số reads có thể còn thành công.
- Keys có TTL vẫn expire.
- Nếu application không xử lý error, business behavior có thể sai.

Cần thiết kế:

1. **Capacity alert trước ngưỡng**.
2. **Quota hoặc admission control** ở tầng ứng dụng nếu cần.
3. **Không tiếp tục business action khi write bắt buộc đã fail**.
4. **Retry có idempotency**, không retry vô hạn.
5. **Scale/shard/cleanup hợp lệ** theo chính sách, không xóa critical keys tùy tiện.
6. **Runbook** cho pressure và phương án phục hồi.

Giữ key bằng `noeviction` có nghĩa có thể phải hy sinh write availability khi capacity cạn. Đó là một đánh đổi chủ động.

## 45. Redis ACL và quyền đổi cấu hình

Các lệnh:

```redis
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
CONFIG SET maxmemory-policy allkeys-lru
CONFIG REWRITE
```

có thể yêu cầu quyền quản trị Redis tương ứng. Không cấp quyền `CONFIG SET` cho mọi business service chỉ để “tự chữa” memory pressure.

Một số Redis managed services không cho phép thay cấu hình qua `CONFIG SET`; phải dùng control plane/provider parameters.

Không nên để application startup tự override eviction policy toàn Redis nếu nhiều team chia sẻ instance, vì một deploy có thể bất ngờ làm mất critical state.

## 46. Thay đổi maxmemory-policy trong thời gian chạy

Redis có thể hỗ trợ thay đổi một số cấu hình runtime:

```bash
redis-cli -h redis-test.internal -p 6379 \
  CONFIG SET maxmemory-policy allkeys-lfu

redis-cli -h redis-test.internal -p 6379 \
  CONFIG SET maxmemory 768mb
```

**Chỉ dùng trên môi trường test hoặc theo quy trình thay đổi được phê duyệt.**

Lưu ý:

- Runtime `CONFIG SET` có thể không được lưu sau restart nếu không có cơ chế persistence/config management phù hợp.
- `CONFIG REWRITE` có điều kiện quyền và khả năng ghi file; không nên coi nó thay thế cấu hình declarative do hạ tầng quản lý.
- Nếu automation quản lý `redis.conf`, thay đổi thủ công có thể bị ghi đè ở lần deploy tiếp theo.
- Giảm `maxmemory` đột ngột có thể gây nhiều evictions hoặc write errors.
- Đổi từ `noeviction` sang `allkeys-*` có thể làm mất key quan trọng trước TTL.

Phải xem change này là **thay đổi hợp đồng dữ liệu**, không chỉ tuning hiệu năng.

## 47. Thiết kế kiểm thử memory pressure trên Redis test

Dùng một Redis instance/container test riêng, không dùng production.

Một cấu hình có giới hạn nhỏ để quan sát:

```conf
maxmemory 32mb
maxmemory-policy allkeys-lru
```

Kịch bản:

1. Bảo đảm Redis test chứa namespace riêng và không có dữ liệu cần giữ.
2. Ghi những keys với payload kích thước biết trước.
3. Quan sát `INFO memory`, `INFO stats`.
4. Tăng số keys đến khi eviction bắt đầu.
5. Kiểm tra `evicted_keys` tăng.
6. Kiểm tra cache miss vẫn fallback đến nguồn chuẩn.
7. Ghi nhận memory/RSS và command latency.
8. Chuyển policy sang `noeviction` trong **môi trường test**.
9. Thử tiếp tục ghi và ghi nhận OOM errors.
10. Không coi một lần test nhỏ là bằng chứng production an toàn.

Nếu muốn so sánh LRU với LFU, cần một workload truy cập có tính chất cụ thể (hot keys, cold keys, burst) và đo hit ratio/DB fallback dưới cùng giới hạn memory.

## 48. Tạo workload test có kiểm soát

Một thuật toán test ở cấp ứng dụng:

```text
for i = 1..N:
    SET cache:test:i payload EX 300

for request in workload:
    GET cache:test:hot-key
    GET cache:test:random-key

periodically:
    INFO memory
    INFO stats
    collect API latency and DB fallback
```

Không chạy hàng triệu lệnh vào Redis production chỉ để thấy eviction.

### Khi so sánh policy

Giữ ổn định:

- Redis version.
- Dataset/size distribution.
- Số clients và concurrency.
- Command mix.
- TTL distribution.
- Memory limit.
- Replication/persistence config.
- Khoảng warm-up.
- Các phép đo p95/p99 và total CPU.

Nếu thay đổi đồng thời dữ liệu, tải, maxmemory và policy, rất khó xác định nguyên nhân của thay đổi hit ratio.

## 49. Kiểm thử volatile policy khi không có TTL

Một bài test quan trọng:

```conf
maxmemory 32mb
maxmemory-policy volatile-lru
```

Bước thử trong Redis test:

1. Ghi nhiều keys không TTL.
2. Ghi một nhóm keys có TTL.
3. Đẩy memory pressure gần vượt giới hạn.
4. Quan sát những keys có TTL bị eviction.
5. Khi không còn TTL candidates mà vẫn cần memory, quan sát lỗi ghi.
6. Đối chiếu `evicted_keys` và `expired_keys`.

Bài tập giúp hiểu rằng `volatile-*` **không phải** một thuật toán tự giải phóng bất kỳ key nào có sẵn; nó bị giới hạn ở nhóm có expiration.

Không dùng test trên Redis đang giữ session/lock thật.

## 50. Kiểm thử sự kiện eviction

Có thể cấu hình Redis keyspace notifications để nghe các events phù hợp trong môi trường test. Tuy nhiên:

- Cần bật `notify-keyspace-events` với flags phù hợp.
- Event delivery dựa trên Pub/Sub nên at-most-once.
- Subscriber offline có thể bỏ lỡ event.
- Notification tới sau sự kiện; không nên dùng để ngăn key mất.
- Nhiều key bị evict có thể gây lượng events/log cao.
- Không nên dùng listener eviction làm cách duy nhất đếm mất key; metrics Redis vẫn cần.

Ví dụ kiểm chứng ở integration test: ghi key có TTL dài, gây memory pressure và xác nhận key mất **trước TTL** cùng `evicted_keys` tăng. Không cần phụ thuộc notification timing để chứng minh eviction behavior.

## 51. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| Redis OOM dù có `allkeys-*` | Memory accounting, evictions không đủ nhanh, command overhead, policy thực tế |
| Redis OOM dưới `volatile-*` | Không đủ keys có TTL để evict |
| Redis process bị OOM-kill | RSS/cgroup pressure ngoài `maxmemory` |
| Session tự logout sớm | Session key bị eviction hoặc TTL sai |
| Idempotency bị trùng | Key bị evict/mất state trước thời hạn |
| Cache misses tăng đột biến | Evictions, TTL đồng loạt, deploy/flush, topology |
| Database latency tăng | Cache stampede sau eviction |
| Evicted keys tăng nhưng hit ratio ổn | Có thể là hành vi cache bình thường |
| Primary đổi thì write errors tăng | Config/headroom khác ở replica được promote |
| Một Cluster shard liên tục OOM | Hot slot, imbalance, `maxmemory` per-node |
| Key không hết hạn như mong muốn | TTL không được đặt hoặc bị update làm mất expiration |
| Cache không thay đổi dù property TTL đã sửa | Custom cache manager override, bean configuration |
| Read replica thấy data cũ | Replication lag, không phải eviction |
| `expired_keys` tăng | TTL expiration, không đồng nghĩa eviction |

### Cách tiếp cận chẩn đoán

1. Xem `maxmemory` và policy thực tế.
2. Xem `INFO memory`/RSS và cgroup.
3. Xem `INFO stats` eviction/expiration/hit/miss.
4. Xác định dữ liệu nào đang nằm trên instance.
5. Kiểm tra Spring Cache TTL và key prefix.
6. Xem replicas/Cluster shard.
7. Đối chiếu metrics ứng dụng và database.
8. Xem các thay đổi deployment gần thời điểm sự cố.

Không khắc phục bằng cách tăng `maxmemory` tùy tiện nếu container không còn headroom.

## 52. Runbook: used_memory tiến gần maxmemory

### Bước 1 — Xác minh telemetry

```bash
redis-cli -h redis.internal -p 6379 INFO memory
redis-cli -h redis.internal -p 6379 INFO stats
redis-cli -h redis.internal -p 6379 CONFIG GET maxmemory
redis-cli -h redis.internal -p 6379 CONFIG GET maxmemory-policy
```

### Bước 2 — Phân loại instance

- Chuyên cache có thể tái tạo?
- Chứa sessions/locks/idempotency?
- Chứa queue/Streams quan trọng?
- Là một shard của Redis Cluster?
- Có replicas và persistence không?

### Bước 3 — Xác định rủi ro hiện tại

- Eviction đang xảy ra hay không?
- Write errors đang tăng hay không?
- RSS có gần cgroup limit không?
- Cache hit ratio và DB fallback đang ra sao?
- Có hot key/shard nào bất thường không?
- Replica mới có đủ headroom nếu failover không?

### Bước 4 — Chọn hành động theo dữ liệu

Với **cache pool**:

- Có thể tăng capacity/scale/reshard.
- Xem LRU/LFU phù hợp chưa.
- Giảm payload lớn không cần thiết.
- Chọn TTL/freshness và invalidation đúng.
- Giảm stampede/fallback.
- Không xóa toàn cache khi chưa cần.

Với **critical state pool**:

- Không đổi vội sang `allkeys-*`.
- Chặn/giảm tải ghi khi cần.
- Xử lý write failures có chủ đích.
- Scale hoặc di chuyển workload có kiểm soát.
- Không xóa key điều phối đang hoạt động.
- Đánh giá RPO/RTO và nguồn có thẩm quyền.

### Bước 5 — Xác nhận phục hồi

- Memory/RSS ổn định với headroom.
- Eviction/write error rate trở lại phạm vi mong muốn.
- Cache hit ratio và DB latency phục hồi.
- Redis role/replication đúng.
- Không còn critical state bị lưu trên cache pool nhầm.
- Alert và runbook được cập nhật.

## 53. Khi eviction policy bị thay trong failover

Một tình huống khó phát hiện:

```text
T0 Primary A: allkeys-lru / maxmemory 2gb
T1 Replica B: noeviction / maxmemory 1gb
T2 A lỗi, B được promote
T3 Spring writes tăng; B từ chối ghi vì hết memory
```

Một cách vận hành:

1. Quản lý Redis config nhất quán trên mọi node có thể được promote.
2. Gắn version/config checksum cho deployment.
3. Thu thập `maxmemory`, `maxmemory-policy` theo node.
4. Diễn tập failover trong môi trường test.
5. Kiểm tra memory budget của replica khi trở thành primary.
6. Kiểm tra application error handling khi Redis OOM.
7. Không chỉ quan sát primary ban đầu và bỏ qua replicas.

Redis HA giúp đổi vai trò, không tự bảo đảm các node thay thế có đủ RAM hoặc policy nhất quán.

## 54. Không dùng eviction làm cơ chế xóa dữ liệu có thứ tự nghiệp vụ

Eviction chọn key theo chính sách memory, không phải theo:

- Ngày tạo order.
- Trạng thái đã xử lý của message.
- Quyền ưu tiên business.
- Khả năng phục hồi dữ liệu quan trọng.
- TTL tối thiểu cần giữ của token.
- Thứ tự commit của database.
- Trạng thái người dùng đang giao dịch.

Nếu cần xóa có chủ đích, thiết kế expiration/retention/trimming hoặc garbage collection theo schema nghiệp vụ.

Ví dụ Redis Stream `XTRIM` có retention logic riêng; không dùng eviction toàn key để thay cơ chế giữ lại messages đã được xác nhận.

## 55. Một số nguyên tắc về capacity planning

### Ước lượng logical dataset

Cần biết:

```text
số keys trung bình và đỉnh
distribution kích thước value
data types: String, Hash, Set, ZSet, Stream
key/prefix overhead
TTL và arrival rate
read/write distribution
```

Một ước lượng quá thô:

```text
1 triệu keys x 200 bytes payload = 200 MB
```

không đủ cho RAM thật, vì Redis object overhead, key names, allocator và data structures có thể làm tổng dùng memory lớn hơn đáng kể.

### Đo bằng workload thực

Có thể dùng `MEMORY USAGE` cho representative keys và `INFO memory` dưới workload test để có số liệu thực tế.

### Tính đến số replicas

Logical dataset capacity nằm trên primaries/shards; replicas cần memory riêng để sao chép cùng dữ liệu.

### Tính đến tăng trưởng

Chỉ đo average không đủ; cần biết peak traffic, sự kiện promotion, restart cache warm-up, burst writes và resharding.

### Cân nhắc memory vs latency

Một dataset vừa dưới maxmemory có thể tránh eviction bình thường, nhưng chỉ một burst có thể gây spike. Cần dành headroom cho hoạt động biến động.

## 56. Checklist triển khai

**Redis server**

- `maxmemory` đã được chọn từ RAM/RSS measurements, không phải lấy bằng cgroup limit.
- `maxmemory-policy` phù hợp với khả năng mất key của workload.
- Có `maxmemory-samples`/LFU tuning nếu cần và đã thử tải.
- Có memory headroom cho replication, client buffers, AOF/RDB và COW.
- Có monitoring `INFO memory`, `INFO stats`, RSS, cgroup memory.
- Có alert khi write OOM và process OOM-kill.
- Policies nhất quán theo nodes có thể được promote.
- Có capacity/scale plan khi cache growth cao hơn dự kiến.

**Spring Data Redis**

- Cache keys có TTL phù hợp freshness, không dùng TTL như bảo đảm tồn tại tối thiểu.
- Redis CacheManager cấu hình TTL theo cache name nếu cần.
- Serializer tương thích và key prefix rõ ràng.
- Cache miss có fallback tới nguồn chuẩn.
- Cache stampede được giảm tải.
- Redis errors và OOM không bị che thành cache miss khi không phù hợp.
- Idempotency/locks/rate limiter có failure policy rõ.
- Không dùng app startup tùy tiện đổi toàn Redis policy.

**Kiến trúc**

- Cache có thể tái tạo tách khỏi critical state khi cần policy khác.
- Logical Redis DB/prefix không được coi là memory isolation.
- Redis Cluster được giám sát theo shard.
- Replica failover được test với config/capacity mới.
- Backup/persistence không bị nhầm với eviction.
- Có runbook xử lý memory pressure.

## 57. Bài tập A — Chọn policy cho cache catalog

Một service có:

```text
3 triệu cache product keys
một số ít sản phẩm rất hot
nguồn chuẩn PostgreSQL
có thể cache miss và tái tạo
```

Hãy:

1. Lựa chọn `allkeys-lru` hoặc `allkeys-lfu` và giải thích.
2. Chọn TTL theo freshness.
3. Xác định các metrics để so sánh hai policy.
4. Mô tả cache stampede khi hot key bị evict.
5. Thiết kế một load test Redis riêng với cùng dataset/traffic.

## 58. Bài tập B — Phân biệt TTL và eviction

Một key:

```redis
SET cache:item:42 "v1" EX 600
```

Redis `maxmemory-policy allkeys-lru`, memory pressure bắt đầu sau 60 giây.

Hỏi:

1. Key có thể biến mất trước 600 giây không?
2. Nếu key mất ở giây 80, có thể do TTL không?
3. Redis `INFO stats` có thể giúp phân biệt gì?
4. Có thể dựa duy nhất vào keyspace notification để quyết định nguyên nhân không?
5. Spring service nên xử lý cache miss thế nào?

## 59. Bài tập C — Tại sao volatile-lru không bảo vệ session?

Redis chứa:

```text
cache:product:42         TTL 5 phút
session:user:1001        TTL 30 phút
lock:order:42            TTL 30 giây
idempotency:order:9001   TTL 24 giờ
```

Policy `volatile-lru`.

Hãy:

1. Liệt kê các key đủ điều kiện eviction.
2. Giải thích vì sao TTL không đồng nghĩa key có thể mất sớm.
3. Đề xuất cách cô lập cache và critical state.
4. Nêu chính sách khi critical pool hết memory.
5. Mô tả vì sao `noeviction` vẫn cần idempotency/recovery.

## 60. Bài tập D — Container bị OOM dù maxmemory chưa chạm

Redis container:

```text
container limit: 2 GiB
maxmemory:      1.8 GiB
```

Trong lúc RDB snapshot, process bị OOM-kill.

Hãy:

1. Giải thích vì sao maxmemory không giới hạn RSS tuyệt đối.
2. Xác định metrics cần thu thập.
3. Tìm các yếu tố fork/COW, buffers, fragmentation.
4. Thiết kế headroom mới dựa trên đo đạc.
5. Kiểm thử lại với workload/persistence tương đương.

## 61. Bài tập E — Redis Cluster thiếu RAM một shard

Một Redis Cluster có ba primaries:

```text
A: 95% maxmemory, eviction tăng mạnh
B: 40% maxmemory
C: 35% maxmemory
```

Hãy:

1. Xác định slot/key distribution và hot hash tags.
2. Giải thích vì sao maxmemory không phải một ngân sách toàn cluster.
3. Đề xuất scale/reshard có kiểm soát.
4. Nêu giới hạn của việc thêm replica.
5. Xác định metrics ở từng shard trước/sau thay đổi.

## 62. Bài tập F — noeviction làm write thất bại

Redis coordination pool có `noeviction`. Application gửi `SET idempotency:order:9001 ...` rồi nhận lỗi do memory.

Hãy:

1. Thiết kế error response/failure policy.
2. Giải thích vì sao không được coi request đã được bảo vệ idempotency.
3. Xác định có thể retry với request ID nào.
4. Chọn biện pháp scale/cleanup hợp lệ.
5. Thiết kế alert để phát hiện trước khi toàn bộ writes bị từ chối.

## 63. Các câu hỏi thường gặp

**Redis maxmemory có giới hạn RSS process không?**

Không tuyệt đối. Memory RSS có thể lớn hơn maxmemory vì fragmentation, buffers, persistence activity và các thành phần memory accounting khác.

**Có nên chọn allkeys-lru cho mọi Redis instance?**

Không. Nó cho phép evict mọi key, bao gồm session, lock và idempotency. Chỉ hợp lý khi mọi key đủ điều kiện mất sớm hoặc hệ thống chấp nhận hệ quả.

**Khác biệt allkeys-lru và allkeys-lfu?**

LRU ưu tiên những keys vừa được sử dụng; LFU ước lượng tần suất sử dụng với cơ chế decay. Hãy đo theo workload thật.

**volatile-lru có chỉ xóa key đã hết hạn không?**

Không. Nó có thể evict key **chưa hết TTL** nếu key đó có expiration.

**volatile-ttl có bảo vệ session lâu hơn cache không?**

Không có bảo đảm dựa trên loại dữ liệu. Nó chỉ ưu tiên keys có TTL còn lại ngắn hơn, và session vẫn là candidate nếu có TTL.

**Nếu volatile policy không có key TTL nào thì sao?**

Redis có thể không giải phóng được bộ nhớ bằng eviction và từ chối writes cần thêm memory.

**noeviction có nghĩa không bao giờ mất key không?**

Không. Keys vẫn expire theo TTL, bị ứng dụng xóa, mất do persistence/failover failures hoặc các nguyên nhân khác. Nó chỉ tắt eviction chủ động theo memory policy.

**Có nên đặt TTL cho mọi cache entry không?**

TTL thường hữu ích để giới hạn độ cũ và vòng đời dữ liệu, nhưng policy cụ thể theo freshness/invalidation. `allkeys-*` vẫn có thể evict cache không TTL; `volatile-*` chỉ xét key có TTL.

**Spring Boot có tự cấu hình Redis maxmemory qua spring.data.redis không?**

Không theo nghĩa property kết nối thông thường. maxmemory là cấu hình Redis server/managed service.

**Có thể gán maxmemory-policy khác nhau cho Redis DB 0 và DB 1 không?**

Không trong một Redis instance theo cách này. Redis logical DB không tạo memory policy riêng.

**Tại sao eviction tăng nhưng Redis vẫn hoạt động bình thường?**

Với cache pool, eviction có thể là behavior thiết kế để giữ memory trong budget. Cần xem hit ratio, database fallback và latency.

**Tại sao có write OOM dù process còn sống?**

`noeviction` hoặc `volatile-*` không còn candidates phù hợp có thể khiến Redis từ chối các writes cần memory dù `PING` vẫn thành công.

**Redis Cluster có một maxmemory chung cho tất cả nodes không?**

Thông thường không. maxmemory được quản lý per node; cần theo dõi từng shard.

**Replica có cùng policy với primary sau failover không?**

Chỉ nếu bạn quản lý cấu hình và version phù hợp. Không giả định Sentinel/Cluster tự áp dụng policy của primary cũ cho node mới.

**Eviction có thể ảnh hưởng distributed lock không?**

Có. Nếu lock key bị evict trước TTL, một worker khác có thể chiếm lại khóa; cần isolation và cơ chế bảo vệ nghiệp vụ phù hợp.

**Eviction có thể làm idempotency sai không?**

Có, vì key chống trùng bị xóa trước retention có thể khiến retry được coi là request mới.

**AOF/replication có cứu key bị eviction không?**

Eviction là thay đổi keyspace được truyền/lưu theo cơ chế Redis tương ứng; persistence và replication không phải cơ chế khôi phục lịch sử key bị loại theo policy.

**Nếu cache hit ratio giảm, cứ tăng maxmemory được không?**

Không phải lúc nào cũng đúng. Cần xem RAM/RSS headroom, hot key, TTL, workload, serialization size, cache stampede và khả năng scale.

## 64. Tổng kết

Cấu hình giới hạn bộ nhớ và eviction trong Spring Data Redis cần bắt đầu từ **mục đích dữ liệu**, không bắt đầu từ một policy mặc định:

1. `maxmemory` điều chỉnh ngưỡng memory Redis dùng cho eviction/write decisions; nó **không phải giới hạn RSS tuyệt đối**.
2. `allkeys-lru` và `allkeys-lfu` phù hợp với nhiều **cache có thể tái tạo**; chọn dựa trên working set và benchmark.
3. `volatile-*` chỉ evict keys có TTL, nhưng **không bảo vệ session, lock hoặc idempotency key cũng có TTL**.
4. `noeviction` ưu tiên không làm mất key sớm do memory pressure, đổi lại **writes có thể thất bại** khi cạn memory.
5. TTL điều chỉnh **expiration/freshness**, không phải cam kết key luôn tồn tại ít nhất tới thời điểm TTL.
6. Redis server memory policy khác với Spring Cache TTL; Spring Boot application không nên tự thay server policy toàn cục.
7. Prefix và Redis logical DB không tạo isolation memory policy; cần tách instance/deployment khi lớp dữ liệu có hợp đồng khác nhau.
8. Đo cả `used_memory`, `used_memory_rss`, `evicted_keys`, `expired_keys`, cache hit/miss, DB fallback và application errors.
9. Với Sentinel/Cluster, theo dõi per-node/per-shard config, memory headroom và hành vi sau failover.
10. Tạo runbook và bài kiểm thử memory pressure trong môi trường cô lập trước khi triển khai production.

**Một chính sách tốt là chính sách khiến Redis giải phóng đúng những key được phép mất, ở thời điểm áp lực tài nguyên xảy ra, trong khi ứng dụng vẫn có hành vi xác định với cache miss hoặc lỗi ghi.**

## Tài liệu tham khảo

- [Redis – Key eviction](https://redis.io/docs/latest/develop/reference/eviction/)
- [Redis – Redis configuration](https://redis.io/docs/latest/operate/oss_and_stack/management/config/)
- [Redis – INFO](https://redis.io/docs/latest/commands/info/)
- [Redis – MEMORY STATS](https://redis.io/docs/latest/commands/memory-stats/)
- [Redis – MEMORY USAGE](https://redis.io/docs/latest/commands/memory-usage/)
- [Redis – EXPIRE](https://redis.io/docs/latest/commands/expire/)
- [Redis – SET](https://redis.io/docs/latest/commands/set/)
- [Redis – Redis replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis – Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Redis – Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Spring Data Redis – Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Boot – Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Spring Boot – Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
