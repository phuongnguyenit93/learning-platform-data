# Giới hạn bộ nhớ, độ bền và tính nhất quán cần hiểu từ đầu

Redis thường được giới thiệu là kho dữ liệu rất nhanh vì phần lớn thao tác diễn ra trên bộ nhớ. Khi dùng **Spring Data Redis**, tốc độ truy cập chỉ là một phần câu chuyện. Trước khi đưa Redis vào hệ thống thật, cần trả lời ba câu hỏi độc lập:

1. **Bộ nhớ:** Dữ liệu có thể chiếm bao nhiêu RAM? Điều gì xảy ra khi Redis hết chỗ?
2. **Độ bền (durability):** Một giá trị vừa ghi có còn sau khi tiến trình, máy chủ hoặc ổ đĩa gặp sự cố?
3. **Tính nhất quán (consistency):** Sau khi cập nhật, những lần đọc khác có chắc chắn thấy dữ liệu mới nhất không?

Ba thuộc tính này liên quan với nhau nhưng không thay thế cho nhau. Một khóa có TTL vẫn có thể bị loại sớm vì thiếu RAM; một lệnh ghi đã trả về thành công vẫn có thể mất khi failover; và một bản ghi đã được lưu bền vững vẫn có thể là bản cũ so với dữ liệu trong database.

## 1. Phân biệt các khái niệm ngay từ đầu

| Khái niệm | Cơ chế chính | Điều **không** được bảo đảm |
|---|---|---|
| TTL / expiration | Xóa khóa khi hết thời gian sống | Không bảo đảm khóa còn tồn tại trước khi hết TTL |
| Eviction | Loại khóa theo chính sách khi Redis chịu áp lực bộ nhớ | Không phải cơ chế lưu trữ hoặc sao lưu |
| RDB / AOF | Lưu dữ liệu Redis xuống đĩa để phục hồi | Không mặc nhiên tạo một hệ thống không mất dữ liệu |
| Replication | Sao chép dữ liệu từ primary sang replica | Không mặc nhiên đồng bộ tức thời hoặc thay thế backup |
| Atomic command | Một lệnh Redis được thực thi nguyên tử tại máy chủ | Không biến cả chuỗi lệnh ứng dụng thành transaction |
| Cache invalidation | Xóa/cập nhật bản cache sau thay đổi ở nguồn | Không tự loại bỏ mọi race condition |

Một cách nhìn hữu ích là: **TTL/eviction quyết định khóa còn trong RAM hay không; persistence quyết định có thể phục hồi gì; replication và trình tự thao tác quyết định một client có thể nhìn thấy phiên bản nào.**

## 2. Giới hạn bộ nhớ: Redis nhanh nhưng RAM hữu hạn

### 2.1. `maxmemory` giới hạn điều gì?

Redis lưu các cấu trúc dữ liệu trong RAM. Ta có thể cấu hình giới hạn quản lý bộ nhớ bằng `maxmemory` và chọn hành vi khi đạt ngưỡng qua `maxmemory-policy`:

~~~conf
maxmemory 1gb
maxmemory-policy allkeys-lfu
~~~

Đây chỉ là **cấu hình minh họa cho một Redis dùng làm cache**. Không nên lấy `1gb` làm cấu hình mặc định cho mọi máy.

Cần phân biệt:

- `used_memory`: bộ nhớ Redis đã phân bổ qua allocator.
- `used_memory_dataset`: phần ước tính dành cho dữ liệu thực tế, sau khi trừ một số overhead.
- `used_memory_rss`: bộ nhớ cư trú của tiến trình mà hệ điều hành ghi nhận.
- `mem_not_counted_for_evict`: phần bộ nhớ không được tính vào quyết định eviction, có thể gồm các buffer liên quan đến replication/persistence tùy phiên bản và cấu hình.

**`maxmemory` không phải giới hạn cứng cho toàn bộ RAM của tiến trình hay container.** RAM thực tế còn dùng cho cấu trúc quản lý, client/output buffer, replication backlog, allocator fragmentation, và bộ nhớ tăng thêm khi tạo snapshot hoặc rewrite AOF. Khi chạy trong container, phải dành chỗ trước cả cho giới hạn RAM của container; nếu bị OOM-kill, Redis có thể chết trước khi xử lý tải như dự kiến.

Với Redis Cluster, việc đặt ngưỡng và theo dõi bộ nhớ được thực hiện trên **từng node**, không phải một ngân sách RAM duy nhất cho cả cluster.

### 2.2. TTL, eviction và xóa thủ công là ba việc khác nhau

~~~text
SET session:42 "..." EX 1800
                │
                ├── Hết 1.800 giây → khóa đủ điều kiện bị xóa do expiration
                ├── Thiếu RAM + chính sách phù hợp → có thể bị eviction sớm
                └── DEL session:42 → ứng dụng chủ động xóa ngay
~~~

Redis xử lý expiration bằng cách kiểm tra khi truy cập và chủ động quét các khóa hết hạn. Vì vậy thời điểm bộ nhớ thực sự được thu hồi có thể không trùng chính xác tới từng mili giây với thời điểm TTL hết hạn. Về mặt logic, một khóa đã hết hạn không còn được coi là giá trị hợp lệ khi được truy cập.

TTL còn có những chi tiết dễ bỏ sót:

~~~bash
SET demo:token "abc" EX 60
TTL demo:token          # số giây còn lại
SET demo:token "xyz"    # SET thông thường bỏ TTL cũ
TTL demo:token          # -1: khóa tồn tại nhưng không có thời hạn
DEL demo:token
TTL demo:token          # -2: khóa không tồn tại
~~~

- `SET` thông thường sẽ làm mất TTL hiện tại của khóa nếu không chỉ định tùy chọn giữ TTL.
- `EXPIRE` đặt thời hạn bằng một lệnh riêng; nếu `SET` thành công rồi ứng dụng lỗi trước `EXPIRE`, khóa có thể tồn tại vô hạn.
- Nên dùng một lệnh ghi **kèm TTL** khi đây là yêu cầu bắt buộc.
- TTL không phải cơ chế giới hạn dung lượng dự phòng. Nếu tốc độ tạo khóa vượt tốc độ hết hạn, RAM vẫn có thể đầy.

### 2.3. Chọn chính sách eviction dựa trên vai trò của Redis

| Chính sách | Hành vi khi chạm `maxmemory` | Khi cân nhắc |
|---|---|---|
| `noeviction` | Từ chối các lệnh ghi làm tăng sử dụng bộ nhớ theo điều kiện kiểm tra của Redis; đọc vẫn có thể tiếp tục | Dữ liệu không được phép bị loại tùy ý; ứng dụng phải xử lý lỗi ghi |
| `allkeys-lru` | Ưu tiên loại khóa ít được dùng gần đây trên toàn bộ keyspace | Cache truy cập theo độ mới |
| `allkeys-lfu` | Ưu tiên loại khóa có tần suất truy cập thấp theo thuật toán xấp xỉ | Cache có nhóm khóa “nóng” lâu dài |
| `allkeys-random` | Chọn ngẫu nhiên trong toàn bộ khóa | Một số cache có phân bố truy cập đặc biệt |
| `volatile-lru` / `volatile-lfu` | Chỉ chọn trong các khóa **có TTL** | Khi cố ý bảo vệ khóa không TTL khỏi eviction |
| `volatile-ttl` | Ưu tiên các khóa có thời hạn hết hạn gần hơn | Khi TTL phản ánh mức ưu tiên loại bỏ |
| `volatile-random` | Chọn ngẫu nhiên trong các khóa có TTL | Ít cần tối ưu thứ tự loại bỏ |

Các biến thể LRU/LFU dùng kỹ thuật xấp xỉ, không phải bảng xếp hạng tuyệt đối toàn bộ khóa. Với họ `volatile-*`, nếu không còn khóa phù hợp, hành vi dưới áp lực bộ nhớ tương tự `noeviction`; dữ liệu không TTL có thể khiến lệnh ghi thất bại dù đã chọn một eviction policy.

**Quy tắc thiết kế:** Nếu tất cả khóa đều là cache có thể tạo lại, `allkeys-lru` hoặc `allkeys-lfu` thường đáng cân nhắc. Nếu Redis chứa trạng thái nghiệp vụ không được phép mất, đừng trông cậy vào eviction policy để biến Redis thành database có bảo đảm tương đương hệ thống giao dịch.

### 2.4. Tính dung lượng cần dựa trên số đo thực tế

Giả sử hệ thống lưu 2 triệu khóa, mỗi khóa và giá trị chiếm trung bình khoảng 600 byte **theo `MEMORY USAGE`** ở tải thử nghiệm. Phần dữ liệu đo được xấp xỉ:

`2.000.000 × 600 = 1.200.000.000 byte`, tức khoảng **1,2 GB (thập phân)**.

Đây chưa phải RAM cần cấp cho máy chủ. Phải bổ sung ngân sách cho thay đổi tập dữ liệu khi tăng trưởng, buffer, fragmentation, persistence/fork, traffic tăng đột biến và biên an toàn theo số đo thực tế. Kích thước JSON gốc hoặc số ký tự của một key không đủ để ước tính chi phí lưu trữ của Redis.

Các lệnh quan sát hữu ích:

~~~bash
redis-cli INFO memory
redis-cli INFO stats
redis-cli CONFIG GET maxmemory
redis-cli CONFIG GET maxmemory-policy
redis-cli MEMORY USAGE cache:product:42
redis-cli TTL cache:product:42
~~~

Các chỉ số cần theo dõi cùng nhau gồm `used_memory`, `used_memory_rss`, `mem_not_counted_for_evict`, `evicted_keys`, `expired_keys`, độ trễ và tỷ lệ cache hit/miss. `evicted_keys` tăng nhanh là dấu hiệu RAM/cache policy đang ảnh hưởng đến khả năng giữ dữ liệu; `expired_keys` tăng có thể chỉ là TTL hoạt động bình thường.

Tránh khóa quá lớn (big key), lưu vô hạn các danh sách/hashes/sets chỉ tăng, hoặc dùng `KEYS *` trên hệ thống nhiều khóa. Dùng `SCAN` cho nhu cầu duyệt từng phần và thiết kế giới hạn kích thước ngay từ lớp ứng dụng.

### 2.5. Áp dụng TTL bằng Spring Data Redis

Với Spring Boot và `StringRedisTemplate`, đặt thời hạn trong **cùng thao tác ghi**:

~~~java
@Service
public class VerificationCodeStore {

    private final StringRedisTemplate redis;

    public VerificationCodeStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String requestId, String code) {
        String key = "verification:" + requestId;
        redis.opsForValue().set(key, code, Duration.ofMinutes(3));
    }

    public String find(String requestId) {
        return redis.opsForValue().get("verification:" + requestId);
    }
}
~~~

Ví dụ chỉ minh họa cách lưu giá trị có TTL; một hệ thống mã xác thực thật còn cần kiểm soát số lần thử, xóa sau khi dùng, xử lý lỗi và bảo vệ dữ liệu nhạy cảm.

Khi sử dụng Spring Cache, **TTL của `RedisCacheManager` phải được quyết định rõ**. Một cấu hình cơ bản:

~~~java
@Configuration
@EnableCaching
public class CacheConfig {

    @Bean
    RedisCacheManager cacheManager(RedisConnectionFactory connectionFactory) {
        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(5))
                        .disableCachingNullValues();

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .build();
    }
}
~~~

`@Cacheable` chỉ nói cách cache kết quả method, không tự đảm bảo mỗi cache có thời hạn phù hợp nghiệp vụ. Các nhóm dữ liệu có vòng đời khác nhau nên được cấp TTL riêng, thay vì gán một mức TTL cho mọi loại thông tin.

## 3. Độ bền dữ liệu: ghi thành công không đồng nghĩa đã an toàn trên đĩa

### 3.1. Ba cách vận hành phổ biến

| Chế độ | Điều Redis lưu để phục hồi | Mức rủi ro mất dữ liệu khi sự cố |
|---|---|---|
| Không persistence | Chỉ dữ liệu đang nằm trong bộ nhớ | Mất dữ liệu khi tiến trình khởi động lại mà không có nguồn phục hồi |
| RDB snapshot | Ảnh chụp dữ liệu ở các thời điểm tạo snapshot thành công | Có thể mất các thay đổi sau snapshot gần nhất |
| AOF | Nhật ký lệnh làm thay đổi dữ liệu, được ghi và đồng bộ xuống đĩa theo cấu hình | Phụ thuộc chu kỳ `fsync`, tình trạng hệ điều hành/đĩa và quá trình phục hồi |
| RDB + AOF | Kết hợp snapshot và AOF | Giảm một số rủi ro phục hồi, nhưng vẫn cần backup, giám sát và thử khôi phục |

**RDB** tạo snapshot của tập dữ liệu tại một thời điểm. Cách này hữu ích cho backup và phục hồi tương đối nhanh, nhưng các ghi sau snapshot có thể biến mất nếu Redis chết trước lần snapshot tiếp theo. Quá trình snapshot nền thường sử dụng `fork` và cơ chế copy-on-write, có thể làm tăng áp lực RAM trong lúc dữ liệu tiếp tục thay đổi.

**AOF** ghi lại chuỗi thao tác thay đổi dữ liệu để phát lại khi khởi động. Các tùy chọn `appendfsync` thường gặp:

- `always`: yêu cầu đồng bộ thường xuyên cho mỗi lần ghi AOF; chi phí I/O cao hơn, vẫn phụ thuộc giới hạn phần cứng/hệ điều hành.
- `everysec`: thường đồng bộ khoảng mỗi giây; là lựa chọn cân bằng phổ biến, **không phải cam kết tuyệt đối chỉ mất tối đa một giây** trong mọi thảm họa.
- `no`: để hệ điều hành quyết định thời điểm đồng bộ; cửa sổ mất dữ liệu có thể lớn hơn.

Các phiên bản Redis hiện đại có thể tổ chức AOF thành nhiều tệp và thực hiện AOF rewrite để tránh nhật ký tăng vô hạn. Rewrite làm thay đổi cách lưu trữ nội bộ, không biến AOF thành giao dịch phân tán với database bên ngoài.

Một ví dụ cho một instance cần lưu dữ liệu qua restart:

~~~conf
maxmemory 1gb
maxmemory-policy noeviction

appendonly yes
appendfsync everysec
save 300 10
~~~

Cấu hình trên chỉ minh họa cách kết hợp giới hạn bộ nhớ với AOF/RDB. Lệnh `save 300 10` yêu cầu xét việc tạo snapshot khi có ít nhất 10 thay đổi trong 300 giây; không có nghĩa cứ đúng mỗi 300 giây Redis sẽ tạo bản sao. Cần điều chỉnh cho tải, phiên bản Redis và khả năng lưu trữ thực tế.

Đừng chọn `noeviction` rồi hiểu nhầm là “an toàn tuyệt đối”: khi RAM hết, ứng dụng vẫn có thể nhận lỗi ghi; khi máy mất điện, độ bền còn tùy tệp persistence thực sự đã được đồng bộ và thiết bị lưu trữ còn hoạt động hay không.

### 3.2. Khởi động lại, failover và mất cả máy là các tình huống khác nhau

Giả sử client nhận được phản hồi thành công sau `SET order:42 "PAID"`:

1. **Tiến trình Redis lỗi nhưng đĩa còn tốt:** Redis có thể khôi phục những gì RDB/AOF đã lưu; thay đổi chưa được lưu bền có thể mất.
2. **Primary mất kết nối rồi replica lên làm primary mới:** Nếu lệnh ghi chưa đến replica được chọn, giá trị có thể mất khỏi tập dữ liệu sau failover.
3. **Mất volume hoặc hỏng vùng lưu trữ:** RDB/AOF cùng nằm trên volume đó không còn là phương án phục hồi đủ; cần bản sao lưu độc lập và quy trình restore được diễn tập.
4. **Bộ nhớ đầy:** Lệnh ghi có thể bị từ chối theo eviction policy; persistence không giúp lệnh thất bại tự thành công.

**Replica không phải backup.** Xóa nhầm khóa hoặc ghi sai dữ liệu có thể nhanh chóng được nhân bản sang replica. Backup phải có thời điểm khôi phục riêng và được kiểm tra định kỳ.

### 3.3. Replication thường bất đồng bộ

Ở cấu hình primary-replica thông thường, Redis trả lời thao tác ghi trên primary mà không đợi mọi replica xác nhận đã áp dụng thay đổi. Do đó có thể tồn tại một khoảng thời gian ngắn:

~~~text
Client A             Primary                    Replica
   | SET k=v2 ---------> |                          |
   | <----------- OK     | ---- gửi lệnh bất đồng bộ -> |
   |                     |                          |
Client B đọc replica cũ -------------------------> GET k = v1
~~~

Redis có lệnh `WAIT` để client chờ số replica xác nhận đã nhận luồng ghi trước đó, với timeout. Nhưng **`WAIT` không biến replication thành cơ chế đồng thuận mạnh**: việc xác nhận nhận dữ liệu không đồng nghĩa dữ liệu đã được lưu bền trên tất cả máy hoặc chắc chắn sẽ sống sót qua mọi lựa chọn primary lúc failover. Nếu cần kiểm tra đồng bộ AOF ở một số phiên bản hỗ trợ, có thể tìm hiểu thêm `WAITAOF` và giới hạn cụ thể của phiên bản đang triển khai.

## 4. Tính nhất quán: nguyên tử theo lệnh, không tự nguyên tử theo luồng nghiệp vụ

### 4.1. Một lệnh Redis khác với một chuỗi thao tác

Các lệnh đơn như `INCR counter`, `SET key value` hoặc `HSET` được xử lý nguyên tử trên một Redis server đối với các thao tác liên quan. Nhưng xét luồng:

~~~text
GET stock:42       → 10
Tính 10 - 1        → 9
SET stock:42 9
~~~

Nếu hai request cùng đọc 10 rồi cùng ghi 9, hệ thống có thể mất một lần trừ hàng. Thay thế bằng một phép cập nhật nguyên tử phù hợp (ví dụ `DECR` nếu bài toán cho phép), hoặc dùng `WATCH` cùng `MULTI/EXEC`, hay script Lua được thiết kế đúng, thay vì ghép các lệnh đọc-sửa-ghi độc lập.

Cần phân biệt các cơ chế:

| Cơ chế | Giúp ích gì? | Giới hạn quan trọng |
|---|---|---|
| Lệnh đơn (`INCR`, `SET ... NX EX`, …) | Thực hiện một thao tác nguyên tử | Không bao trùm logic ở database khác |
| Pipeline | Giảm số chuyến mạng cho nhiều lệnh | **Không** làm cả batch thành transaction |
| `MULTI/EXEC` | Gom lệnh thành một đợt thực thi tuần tự không bị lệnh client khác chen vào | Không rollback kiểu SQL khi một lệnh lúc thực thi báo lỗi |
| `WATCH` + `MULTI/EXEC` | Hủy transaction nếu khóa được theo dõi thay đổi trước `EXEC` | Ứng dụng phải retry và xử lý xung đột |
| Lua script | Chạy logic trên server như một đơn vị nguyên tử với các lệnh Redis khác | Script dài có thể chặn server; lỗi giữa script không bảo đảm undo mọi thay đổi đã chạy |

Trên Redis Cluster, thao tác nhiều khóa còn phải tuân thủ ràng buộc phân bố slot (ví dụ các khóa cần cùng hash slot khi lệnh yêu cầu); không thể giả định một transaction hay Lua script bất kỳ sẽ bao trùm khóa nằm trên nhiều shard.

### 4.2. Database và Redis là hai hệ thống khác nhau

Ứng dụng Spring thường dùng database quan hệ làm **nguồn dữ liệu chuẩn**, Redis làm lớp cache:

~~~mermaid
flowchart LR
    U[Request] --> S[Spring Service]
    S -->|1. Tìm trong cache| R[(Redis)]
    R -->|Cache hit| S
    S -->|2. Cache miss| D[(Database)]
    D -->|Bản ghi| S
    S -->|3. Cache với TTL| R
    S -->|Trả kết quả| U
~~~

Chiến lược này gọi là **cache-aside**. Khi cập nhật dữ liệu, một cách thông dụng là commit thay đổi ở database rồi xóa khóa cache tương ứng. Tuy nhiên, nó vẫn có race condition:

~~~text
Thời gian    Request A (đọc)           Request B (ghi)
   t1        Cache miss
   t2        Đọc DB → giá trị cũ V1
   t3                                  Ghi DB → V2, commit
   t4                                  Xóa cache thành công
   t5        Ghi V1 vào cache
   t6        Request sau đọc V1 từ cache, dù DB đã là V2
~~~

TTL giúp giá trị cũ không tồn tại vô hạn ở **lần ghi cache đó**, nhưng không chứng minh tất cả lần đọc sẽ thấy dữ liệu mới ngay lập tức. Cơ chế nâng cao như versioning, event-based invalidation, khóa phối hợp hoặc đọc bắt buộc từ nguồn chuẩn cần được chọn theo mức nhất quán nghiệp vụ; mỗi cơ chế có chi phí và các race riêng.

Một lưu ý quan trọng trong Spring:

- `@Transactional` của database không tự tạo transaction nguyên tử xuyên JDBC và Redis.
- `@Cacheable` / `@CacheEvict` giúp khai báo hành vi cache; **thứ tự cache eviction so với database commit** cần được thiết kế rõ.
- `RedisCacheManager.transactionAware()` có thể trì hoãn thao tác put/evict/clear cache đến sau khi transaction Spring commit thành công trong ngữ cảnh thích hợp. Việc Redis lỗi sau commit vẫn có thể làm cache sai hoặc cũ; không được xem đây là commit phân tán bảo đảm tuyệt đối.

Nếu nghiệp vụ cần các thao tác chuyển tiền, thanh toán hay điều chỉnh tồn kho chính xác, hãy đặt invariant tại kho dữ liệu có transaction phù hợp. Redis vẫn rất hữu ích để tăng tốc hoặc thực hiện một số thao tác nguyên tử cục bộ, nhưng phải xác định rõ nguồn dữ liệu chuẩn và phương án khôi phục.

### 4.3. Đọc replica có thể nhìn thấy dữ liệu cũ

Ngay cả khi dữ liệu trên primary đã đổi, replica có thể đi sau. Với các luồng cần **read-your-writes** (người dùng vừa sửa hồ sơ phải thấy ngay thay đổi), có thể:

- Đọc lại từ primary trong khoảng thời gian cần tính nhất quán cao.
- Không đọc bản cache/replica cũ sau một hành động cập nhật nhạy cảm.
- Áp dụng version/token để từ chối dữ liệu thấp hơn phiên bản ứng dụng đã biết.
- Theo dõi replication lag và đặt quy tắc fallback sang primary theo SLA.

Mỗi lựa chọn cần được xem xét với độ trễ, tải primary và khả năng failover. Đọc từ primary giải quyết trường hợp replica bị trễ ở thời điểm bình thường, nhưng **không** tạo bảo đảm không mất ghi qua một failover bất đồng bộ.

## 5. Các tình huống dễ gặp khi phát triển với Spring Data Redis

### Tình huống A: Cache danh mục sản phẩm

- **Bộ nhớ:** TTL vài phút theo yêu cầu tươi mới; có thể eviction sớm.
- **Độ bền:** Có thể tắt persistence cho cache thuần túy nếu database có thể tái tạo toàn bộ dữ liệu và ứng dụng chịu được cache cold start.
- **Nhất quán:** Chấp nhận stale ngắn; xóa khóa sau cập nhật và dùng TTL làm lớp dự phòng.
- **Khi Redis gặp sự cố:** Quyết định rõ có đọc trực tiếp database với giới hạn tải hay trả lỗi tạm thời.

### Tình huống B: Session đăng nhập

- **Bộ nhớ:** TTL phải phù hợp vòng đời session; chính sách eviction có thể khiến người dùng bị đăng xuất sớm.
- **Độ bền:** Nếu Redis là nơi duy nhất giữ session, restart/failover có thể làm mất phiên; phải thiết kế theo mức chấp nhận thực tế.
- **Nhất quán:** Logout, thu hồi token và thay đổi quyền cần có quy tắc vô hiệu hóa rõ, không chỉ dựa vào việc TTL sắp hết.

### Tình huống C: Giới hạn tần suất request

- **Bộ nhớ:** Nhiều khóa ngắn hạn; cần TTL và cơ chế dọn dẹp.
- **Độ bền:** Thường có thể mất một số bộ đếm sau sự cố, tùy mức độ bảo vệ yêu cầu.
- **Nhất quán:** `INCR` rồi `EXPIRE` bằng hai lệnh riêng có cửa sổ lỗi giữa hai thao tác; dùng script Lua hoặc cơ chế nguyên tử được thiết kế cho thuật toán giới hạn tần suất. Nếu nhiều node Redis độc lập, không tự cho rằng bộ đếm toàn hệ thống đã nhất quán.

### Tình huống D: Trạng thái đơn hàng hoặc số dư

- **Bộ nhớ:** Không thể tùy tiện eviction dữ liệu chuẩn.
- **Độ bền:** Cần yêu cầu rõ RPO (chấp nhận mất tối đa bao nhiêu dữ liệu) và RTO (thời gian phục hồi), lưu trữ bền, backup/restore và phương án xử lý lỗi.
- **Nhất quán:** Phải bảo vệ invariant xuyên request và giao dịch; cache Redis chỉ là ảnh chiếu tối ưu đọc nếu database giao dịch mới là nguồn chuẩn.

Điểm quyết định không nằm ở tên kiểu dữ liệu Redis, mà ở **hậu quả nghiệp vụ nếu khóa biến mất, ghi bị mất hoặc client nhìn thấy giá trị cũ**.

## 6. Quan sát sự cố và kiểm tra giả định vận hành

| Quan sát | Câu hỏi cần trả lời | Hướng xử lý |
|---|---|---|
| `used_memory` gần `maxmemory` | Có tốc độ tăng khóa bất thường, thiếu TTL hay big key không? | Đo kích thước/key count, điều chỉnh cấu trúc dữ liệu, TTL, dung lượng và chính sách |
| `evicted_keys` tăng, hit rate giảm | Cache bị đuổi quá sớm làm tải database tăng? | Xem lại working set, `allkeys-lru/lfu`, dung lượng và tải nguồn |
| Lỗi OOM từ Redis | Đang dùng `noeviction` hay không có khóa đủ điều kiện eviction? | Xử lý lỗi ghi ở app và sửa ngân sách bộ nhớ/chính sách |
| `used_memory_rss` cao hơn đáng kể `used_memory` | Fragmentation, bộ nhớ nền/buffer hay hoạt động persistence? | Đọc thêm chỉ số allocator và hệ điều hành; không kết luận chỉ từ một tỷ lệ |
| `aof_last_write_status` hoặc `rdb_last_bgsave_status` bất thường | Disk đầy, quyền ghi, fsync hay snapshot lỗi? | Xem log, dung lượng đĩa, quyền volume và quy trình khôi phục |
| Replica lag hoặc link down | Đọc từ replica có bị cũ, nguy cơ mất ghi khi failover? | Kiểm tra topology, network, policy đọc và thử tình huống failover |
| Cache trả dữ liệu cũ | Sai thời điểm invalidation, race, TTL quá dài hay đọc replica? | Truy lại luồng DB commit → evict → refill và đối chiếu phiên bản |

Lệnh khảo sát ban đầu:

~~~bash
redis-cli INFO memory
redis-cli INFO stats
redis-cli INFO persistence
redis-cli INFO replication
redis-cli INFO clients
redis-cli CONFIG GET maxmemory
redis-cli CONFIG GET maxmemory-policy
redis-cli TTL cache:product:42
~~~

Ví dụ `INFO persistence` cho thấy tình trạng lưu RDB/AOF ở thời điểm khảo sát; `INFO replication` cho biết vai trò và tình trạng liên kết replica. Hãy kết hợp thông tin này với log ứng dụng, độ trễ và các phép thử khôi phục thay vì chỉ dựa vào một lần chạy lệnh.

### 6.1. Thử các failure scenario trước khi vận hành

Một hệ thống Redis cần được thử theo **hành vi quan sát được của ứng dụng**:

1. Khi giới hạn bộ nhớ gần đầy, app nhận cache miss hay lỗi ghi? Có làm nghẽn database nguồn không?
2. Khi Redis restart, khóa nào còn, khóa nào mất và app có tự phục hồi được không?
3. Khi primary failover, một thao tác vừa được xác nhận có còn trên primary mới không?
4. Khi lệnh xóa cache thất bại sau khi database đã commit, khách hàng có thể thấy dữ liệu cũ bao lâu?
5. Khi replica đi sau, màn hình vừa cập nhật có đọc nhầm phiên bản cũ không?

Mức chấp nhận cần được xác định theo nghiệp vụ, ví dụ “cache sản phẩm có thể cũ tối đa trong một khoảng thời gian có kiểm soát”, khác hẳn “trạng thái thanh toán không được xử lý hai lần”.

## 7. Nguyên tắc thiết kế mang theo sang các bài Spring Data Redis tiếp theo

1. **Xác định vai trò của mỗi nhóm key**: cache tái tạo được, session, bộ đếm hay trạng thái nghiệp vụ. Đừng áp một eviction/persistence policy cho mọi loại dữ liệu chỉ vì cùng dùng Redis.
2. **Đặt TTL ở thời điểm ghi** khi khóa bắt buộc hết hạn; không dựa vào hai lệnh tách rời mà bỏ qua khoảng lỗi giữa chúng.
3. **Ước lượng RAM bằng dữ liệu đo** và dự phòng phần ngoài key/value; theo dõi cả eviction, RSS, buffer và tác động của persistence.
4. **Chọn RDB/AOF theo RPO/RTO và diễn tập restore**. Replication, AOF và backup xử lý những loại sự cố khác nhau.
5. **Đánh giá nhất quán theo toàn bộ đường đi của request**: database commit, cache invalidation, refill, replica read và failover. Một lệnh Redis nguyên tử không làm toàn bộ luồng trên Spring trở thành nguyên tử.
6. **Thiết kế khi Redis không sẵn sàng**: fallback, timeout, giới hạn tải, trả lỗi có kiểm soát và cơ chế tự phục hồi cần phù hợp mức quan trọng của dữ liệu.

Redis là công cụ mạnh khi ta biết rõ **dữ liệu được phép biến mất lúc nào, mất bao nhiêu khi có sự cố, và một client được phép đọc phiên bản cũ đến mức nào**. Ba câu trả lời đó phải có trước khi chọn annotation, RedisTemplate operation hay thông số triển khai.

## Tài liệu để đọc sâu

- [Redis — Key eviction](https://redis.io/docs/latest/develop/reference/eviction/)
- [Redis — Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
