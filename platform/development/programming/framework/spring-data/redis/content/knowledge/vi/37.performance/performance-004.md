# Kiểm soát kích thước giá trị, số thành viên và số lượng khóa trong Spring Data Redis

Redis thường rất nhanh khi thao tác trên dữ liệu nhỏ, nhưng hiệu năng của một ứng dụng Spring Data Redis có thể giảm mạnh nếu **một value quá lớn**, **một collection chứa quá nhiều phần tử**, hoặc **số key tăng không giới hạn**. Ba vấn đề này có triệu chứng và giải pháp khác nhau: một `GET` trả về JSON vài MB tiêu thụ băng thông và bộ nhớ JVM; một `SMEMBERS` trên Set hàng triệu thành viên có thể tạo response lớn và chặn ứng dụng; còn hàng triệu key nhỏ làm tăng overhead quản lý bộ nhớ, quét keyspace và thời gian khôi phục.

Bài học tập trung vào cách **thiết kế giới hạn ở tầng dữ liệu và tầng ứng dụng** khi dùng `RedisTemplate`, `StringRedisTemplate`, `ReactiveRedisTemplate`, Spring Cache hoặc Redis Streams. Nội dung gồm cách đo Redis key thật, so sánh lựa chọn mô hình dữ liệu, hạn chế lệnh trả nhiều phần tử, kiểm soát sự tăng trưởng, phương pháp dọn dẹp an toàn và các bài kiểm thử hiệu năng có thể lặp lại.

> **Nguyên tắc:** Không tồn tại một con số tối đa duy nhất phù hợp cho mọi hệ thống. Mọi ngưỡng trong bài là **ví dụ về chính sách ứng dụng**, phải hiệu chỉnh theo dung lượng RAM, số request/giây, latency SLO, serializer, network, workload và Redis version.

## 1. Ba chiều tăng trưởng phải kiểm soát riêng

Ví dụ một nền tảng thương mại điện tử dùng các key:

```text
product:100:detail             -> String chứa JSON
product:100:viewers            -> Set các user ID
ranking:daily                  -> Sorted Set
cart:42                        -> Hash
events:checkout               -> Stream
session:aaaaaaaa...            -> String có TTL
```

Có ít nhất ba chiều kích thước:

| Chiều | Ví dụ | Rủi ro chính |
|---|---|---|
| **Kích thước một value** | JSON sản phẩm 5 MB | Response lớn, serialize/deserialize tốn CPU, heap/GC và băng thông |
| **Số thành viên trong một collection** | Set có 2 triệu user ID, Hash có 300.000 field | Lệnh đọc toàn bộ O(N), response lớn, hot key, thao tác xóa tốn công |
| **Tổng số Redis key** | Mỗi session/event tạo một key không TTL | Overhead per-key, RAM tăng liên tục, chi phí persistence/replication/scan và eviction |

Cần bổ sung chiều thứ tư là **tần suất truy cập**. Một key 500 KB được đọc hàng chục nghìn lần mỗi giây có thể tệ hơn một key 5 MB hiếm khi đọc. Đây là vấn đề **hot key**, không chỉ big key.

### 1.1. Phân biệt big key và hot key

```text
Big key:
  Khối lượng bytes hoặc thành viên lớn
  -> RAM, network payload, O(N), deletion, serialization

Hot key:
  Số thao tác/giây tập trung vào cùng key/slot
  -> CPU/node bottleneck, contention, request queue

Big + hot:
  Nhiều request tải cùng một collection rất lớn
  -> thường là trường hợp nguy hiểm nhất
```

Một Redis Cluster chia **key** qua hash slot, nhưng không tự chia **một key khổng lồ** ra nhiều master. Chuyển Standalone sang Cluster có thể giúp phân phối hàng triệu key, nhưng một Set rất nóng vẫn chỉ thuộc một slot tại một thời điểm.

## 2. Vì sao một key lớn làm chậm cả hệ thống?

Chi phí không chỉ là số byte được lưu trong Redis. Một lệnh đọc có thể đi qua:

```text
Redis memory
    |
    v
Redis xử lý command và tạo reply
    |
    v
Socket / network / TLS
    |
    v
Lettuce hoặc Jedis nhận bytes
    |
    v
Spring Data Redis deserializer
    |
    v
Java String / DTO / Collection
    |
    v
Business logic / JSON HTTP response
```

Nếu value là JSON 2 MB, ứng dụng còn có thể tạo thêm các bản biểu diễn trong bộ nhớ: byte array khi nhận, String/JsonNode, DTO, response JSON và buffer I/O. **2 MB lưu trong Redis không đồng nghĩa request chỉ chiếm 2 MB RAM của JVM.**

Tương tự, lệnh `HGETALL` trên Hash 200.000 field có thể tạo một Map lớn, nhiều đối tượng nhỏ, GC pressure và response khổng lồ. Không nên đánh giá một lệnh chỉ theo độ phức tạp danh nghĩa: **kích thước phản hồi** và **chi phí decode** cũng quyết định latency.

### 2.1. Bốn nơi cần đo

1. **Redis RAM:** bytes/key, total memory, fragmentation, dataset size.
2. **Redis CPU/latency:** lệnh chậm, payload lớn, blocking operations, hot shard.
3. **Network:** số byte mỗi response, bandwidth, TLS overhead và round trips.
4. **Java application:** deserialize time, allocation rate, heap, GC, p95/p99 request latency.

Chỉ nhìn `INFO memory` không phát hiện mọi vấn đề. Ví dụ Redis còn nhiều RAM nhưng một HTTP request `SMEMBERS` có thể timeout vì phải chuyển và decode hàng trăm nghìn phần tử.

## 3. Đo kích thước value và số thành viên bằng Redis CLI

Trên một Redis **test** hoặc tài khoản quan sát có quyền phù hợp, bắt đầu bằng các lệnh ít ảnh hưởng:

```bash
redis-cli -h 127.0.0.1 -p 6379 TYPE product:100:detail
redis-cli -h 127.0.0.1 -p 6379 STRLEN product:100:detail
redis-cli -h 127.0.0.1 -p 6379 MEMORY USAGE product:100:detail

redis-cli -h 127.0.0.1 -p 6379 HLEN cart:42
redis-cli -h 127.0.0.1 -p 6379 SCARD product:100:viewers
redis-cli -h 127.0.0.1 -p 6379 ZCARD ranking:daily
redis-cli -h 127.0.0.1 -p 6379 LLEN notifications:42
redis-cli -h 127.0.0.1 -p 6379 XLEN events:checkout
```

| Lệnh | Đo gì? | Không đo gì? |
|---|---|---|
| `STRLEN key` | Độ dài value của Redis String tính bằng **bytes** | Không bao gồm overhead key/allocator |
| `HLEN key` | Số field của một Redis Hash | Không phải số byte trong Hash |
| `SCARD key` | Số thành viên Redis Set | Không phải size bytes hay tần suất truy cập |
| `ZCARD key` | Số thành viên Sorted Set | Không phải size bytes |
| `LLEN key` | Số phần tử List | Không phải dung lượng RAM |
| `XLEN key` | Số entry còn trong Stream | Không phải số pending/ACK hay bytes/entry |
| `MEMORY USAGE key` | Ước lượng RAM Redis dùng cho key và value, gồm overhead | Không bao gồm mọi chi phí network/JVM hay tổng chi phí replication |
| `TYPE key` | Kiểu dữ liệu Redis | Không xác định serializer/schema Java |

Một String Java có ký tự Unicode không nhất thiết có `String.length()` bằng `STRLEN` của Redis. Redis đo **bytes**, không đo số ký tự UTF-16 của Java.

### 3.1. MEMORY USAGE và SAMPLES

```redis
MEMORY USAGE cart:42
MEMORY USAGE cart:42 SAMPLES 20
MEMORY USAGE cart:42 SAMPLES 0
```

Với cấu trúc có nhiều phần tử lồng nhau, Redis có thể **lấy mẫu** để ước lượng kích thước. Mặc định thường lấy vài mẫu; `SAMPLES 0` duyệt tất cả phần tử để ước lượng đầy đủ hơn, đổi lại có thể tốn CPU trên collection rất lớn. Không chạy `SAMPLES 0` hàng loạt trên production bận rộn mà chưa đánh giá tác động.

`MEMORY USAGE` phản ánh cấu trúc nội bộ, overhead và allocator; cùng một số bytes payload có thể tiêu thụ RAM khác nhau giữa các encoding, Redis version và kiến trúc hệ thống. Không lấy `STRLEN` thay thế `MEMORY USAGE` khi lập ngân sách RAM.

### 3.2. Kiểm tra kiểu trước khi đo

`STRLEN` chỉ dùng cho Redis String. Nếu key là Hash, chạy `STRLEN` sẽ nhận `WRONGTYPE`. Tương tự, `HLEN` không áp dụng cho Set. Một công cụ inventory nên gọi `TYPE` hoặc biết rõ namespace/schema trước khi chọn cardinality command.

## 4. Tổng số key và mức tiêu thụ bộ nhớ

Các lệnh quan sát cấp instance:

```bash
redis-cli -h 127.0.0.1 -p 6379 INFO memory
redis-cli -h 127.0.0.1 -p 6379 INFO keyspace
redis-cli -h 127.0.0.1 -p 6379 INFO stats
redis-cli -h 127.0.0.1 -p 6379 DBSIZE
redis-cli -h 127.0.0.1 -p 6379 MEMORY STATS
```

Các trường đáng chú ý:

| Nhóm | Ví dụ trường | Ý nghĩa |
|---|---|---|
| RAM | `used_memory`, `used_memory_human` | Redis đang sử dụng bao nhiêu memory |
| Cấu hình | `maxmemory`, `maxmemory_policy` | Giới hạn bộ nhớ và eviction policy |
| Fragmentation | `mem_fragmentation_ratio`, các chỉ số allocator | Overhead/phân mảnh; không diễn giải một chỉ số riêng lẻ |
| Keyspace | `db0:keys=...,expires=...,avg_ttl=...` | Số key, số key có expire và TTL trung bình được báo |
| Eviction | `evicted_keys` | Key bị loại do chính sách bộ nhớ |
| Expiration | `expired_keys` | Key đã hết hạn và bị xử lý expiration |
| Cache access | `keyspace_hits`, `keyspace_misses` | Tín hiệu phục vụ truy cập, không tự kết luận chất lượng cache |

`DBSIZE` đếm key trong **database của connection hiện tại**. Với Redis Cluster, mỗi node giữ một phần keyspace; `DBSIZE` trên một master **không** phải số key của toàn Cluster. Redis Cluster dùng logical database `0`.

### 4.1. Số key nhiều vẫn có thể tốn hơn gộp thành collection

Một triệu key String nhỏ mang overhead cho:

- Tên key và value.
- Entry trong dictionary Redis.
- Metadata expiration nếu có TTL.
- Định dạng dữ liệu và phân bổ bộ nhớ nội bộ.
- Persistence, replication và các lần scan/expire.

Không thể tính chính xác bằng công thức chỉ lấy độ dài value. Cách làm tốt hơn là benchmark **trên Redis version và cấu hình thực tế**:

```text
M1 = used_memory khi Redis test rỗng
Tạo N key với key/value điển hình
M2 = used_memory sau khi ổn định

Memory-per-key mẫu ≈ (M2 - M1) / N
```

Lặp với các cấu trúc String, Hash, Set, ZSet và các serializer khác nhau. Cần có headroom cho fragmentation, buffer, persistence fork/copy-on-write và đỉnh tải, không cấu hình `maxmemory` bằng đúng tổng payload ước lượng.

## 5. Tìm big keys một cách an toàn hơn KEYS *

Redis CLI hỗ trợ phân tích keyspace:

```bash
# Phát hiện String rất dài, Hash/Set/List/ZSet có nhiều thành viên.
redis-cli -h 127.0.0.1 -p 6379 --bigkeys

# Phát hiện key dùng RAM lớn theo kết quả MEMORY USAGE.
redis-cli -h 127.0.0.1 -p 6379 --memkeys

# Một số phiên bản redis-cli còn có thống kê phân phối/Top N.
redis-cli -h 127.0.0.1 -p 6379 --keystats
```

`--bigkeys` dùng cách đo phù hợp từng kiểu, ví dụ độ dài String hoặc số thành viên collection. Nó **không đồng nghĩa tìm đúng key tiêu thụ RAM lớn nhất**, vì một Hash ít field nhưng mỗi field rất lớn vẫn có thể dùng nhiều RAM. `--memkeys` / `--keystats` giúp phân tích memory hơn; tính sẵn có của option phụ thuộc Redis CLI version.

Các chế độ này dùng scan, không phải một thao tác snapshot tức thời. Quét toàn bộ dữ liệu vẫn tạo tải; với production, thực hiện trong cửa sổ được phép, giới hạn tốc độ và ghi lại node/cursor/phạm vi quét.

### 5.1. Giới hạn tốc độ quét

Theo tài liệu Redis CLI, có thể dùng tùy chọn `-i` để nghỉ giữa các nhóm lệnh:

```bash
redis-cli -h 127.0.0.1 -p 6379 --bigkeys -i 0.1
```

Con số `0.1` chỉ minh họa thời gian nghỉ phù hợp cho một lượt điều tra. Nó không tự bảo đảm không có ảnh hưởng latency. Nếu traffic Redis rất cao, cân nhắc chạy ở replica được phép quan sát, nhưng cần ghi nhận replication lag và giới hạn đọc replica.

### 5.2. Tại sao không dùng KEYS *?

```redis
KEYS *
```

Lệnh này có thể quét toàn bộ keyspace trong một lần và làm Redis xử lý lâu, gây trễ cho các client khác. Trên ứng dụng Spring, `redisTemplate.keys("*")` thường dùng lệnh `KEYS` phía server; không nên gọi trong endpoint hoặc scheduled job production để đếm/xóa theo prefix.

Thay bằng `SCAN` có cursor và giới hạn công việc mỗi lượt. Nhưng **SCAN không phải free**: quét hàng triệu key vẫn tiêu tốn tổng CPU/network và thời gian.

## 6. SCAN, HSCAN, SSCAN, ZSCAN: phân lô thay vì tải hết

Các lệnh duyệt từng phần:

```redis
SCAN 0 MATCH app:cache:* COUNT 100
HSCAN cart:42 0 COUNT 100
SSCAN product:100:viewers 0 COUNT 100
ZSCAN ranking:daily 0 COUNT 100
```

Kết quả có dạng:

```text
1) next-cursor
2) entries của lượt hiện tại
```

Ứng dụng lấy cursor trả về để gọi lượt tiếp theo, kết thúc **chỉ khi cursor trở lại 0**.

Điểm cần nhớ:

1. `COUNT 100` là **hint về công việc Redis thực hiện**, không phải cam kết “tối đa 100 phần tử/response”.
2. Một lượt có thể trả **0 phần tử** nhưng cursor chưa phải 0.
3. Trong quá trình dữ liệu thay đổi, một phần tử có thể được trả **hơn một lần**; ứng dụng cần thao tác idempotent/deduplicate nếu cần.
4. Đây không phải snapshot nhất quán của keyspace.
5. `SCAN MATCH` lọc theo pattern, không tự biến việc quét thành O(1) tìm đúng prefix.
6. Một số collection lưu dưới compact encoding có thể trả toàn bộ phần tử trong một lượt dù `COUNT` nhỏ, theo Redis version và ngưỡng encoding.

### 6.1. Vì sao các lệnh đọc toàn bộ collection nguy hiểm?

| Lệnh | Vấn đề khi collection lớn | Lựa chọn |
|---|---|---|
| `SMEMBERS key` | Trả toàn bộ Set | `SSCAN`, hoặc thiết kế phân trang dựa vào index |
| `HGETALL key` | Trả mọi field/value | `HMGET` field cần thiết, `HSCAN` để inventory |
| `LRANGE key 0 -1` | Trả toàn bộ List | `LRANGE` theo khoảng nhỏ |
| `ZRANGE key 0 -1` | Trả toàn bộ Sorted Set | `ZRANGE`/`ZREVRANGE` theo trang |
| `XRANGE stream - +` | Trả toàn bộ lịch sử Stream | `XRANGE ... COUNT n` và cursor ID |
| `KEYS pattern` | Duyệt toàn keyspace trong một lệnh | `SCAN` và cursor |

`HSCAN`/`SSCAN` không tự tạo một **trang phân trang ổn định cho người dùng** khi collection bị ghi/xóa đồng thời. Nếu API cần phân trang có thứ tự, một Sorted Set với score/member thích hợp hoặc một database có index rõ ràng thường phù hợp hơn.

## 7. Đặt ngân sách kích thước value theo **bytes sau serialization**

Giả sử endpoint lưu một cấu hình nhỏ vào Redis:

```text
Key:    app:settings:{tenant-42}
Value:  JSON config
Policy: không quá 32 KiB bytes UTF-8 cho mỗi document
TTL:    15 phút
```

**32 KiB chỉ là ví dụ** về giới hạn nghiệp vụ, không phải giới hạn tối đa của Redis String. Khi chọn mức thực tế, đo p95/p99 kích thước JSON, payload network và latency.

### 7.1. Sai lầm: đếm Java String.length()

```java
if (json.length() > 32_768) {
    throw new IllegalArgumentException("Too large");
}
```

`String.length()` đếm UTF-16 code units, không phải số byte mà `StringRedisSerializer` ghi vào Redis. Ví dụ ký tự tiếng Việt hoặc emoji có thể sử dụng nhiều byte UTF-8.

Đúng hơn với String:

```java
byte[] bytes = json.getBytes(java.nio.charset.StandardCharsets.UTF_8);
if (bytes.length > 32 * 1024) {
    throw new IllegalArgumentException(
            "Redis JSON exceeds 32 KiB policy");
}
```

Nếu dùng JDK serialization, JSON serializer, compression hoặc encryption thì phải đo **bytes thực sự do serializer tạo ra**, không suy ra từ `toString()` của Java object.

### 7.2. Ví dụ Spring service giới hạn JSON value

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class BoundedSettingsCache {

    private static final int MAX_JSON_BYTES = 32 * 1024;
    private static final Duration TTL = Duration.ofMinutes(15);

    private final StringRedisTemplate redis;
    private final ObjectMapper mapper;

    public BoundedSettingsCache(
            StringRedisTemplate redis,
            ObjectMapper mapper) {
        this.redis = redis;
        this.mapper = mapper;
    }

    public void store(String tenantId, SettingsDto settings) {
        if (tenantId == null ||
                !tenantId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid tenantId");
        }
        try {
            String json = mapper.writeValueAsString(settings);
            int bytes = json.getBytes(StandardCharsets.UTF_8).length;

            if (bytes > MAX_JSON_BYTES) {
                throw new IllegalArgumentException(
                        "Settings payload exceeds limit: " + bytes);
            }

            String key = "app:settings:{" + tenantId + "}";
            redis.opsForValue().set(key, json, TTL);
        } catch (JsonProcessingException error) {
            throw new IllegalArgumentException(
                    "Cannot serialize settings", error);
        }
    }
}
```

`SettingsDto` là DTO nghiệp vụ do ứng dụng định nghĩa. Ví dụ cố ý dùng `StringRedisTemplate` để bytes được lưu là UTF-8 của đúng JSON String đã đo; nếu chuyển sang `RedisTemplate<String, SettingsDto>`, phải đo bằng serializer được gắn vào **template đó**. Cũng cần đặt giới hạn ở HTTP/API ingress để không parse một payload khổng lồ rồi mới phát hiện quá ngưỡng.

### 7.3. Kiểm tra cả kích thước key

Tên key quá dài tạo memory overhead và tăng bytes trên mỗi command. Dùng schema ngắn nhưng dễ vận hành:

```text
Hợp lý:
  p:100:detail
  session:7f8a...

Không hợp lý khi nhân rộng:
  org:production:service:catalog:region:...:<toàn bộ JSON yêu cầu>
```

Không rút ngắn key đến mức trùng tên hoặc mất khả năng phân biệt tenant và môi trường. Với Redis Cluster, hash tag trong key còn quyết định slot; thay tên key có thể ảnh hưởng placement.

## 8. Khi value lớn, nên chia dữ liệu hay chuyển sang storage khác?

Một anti-pattern:

```text
report:2026-11-13 -> 20 MB JSON gồm 50.000 dòng kết quả
```

Mỗi lần `GET` kéo cả báo cáo về ứng dụng, dù người dùng chỉ cần 20 dòng đầu. Khi dữ liệu là document lớn hoặc binary asset, có các lựa chọn:

| Giải pháp | Phù hợp | Cần lưu ý |
|---|---|---|
| Giữ một Redis String | Value nhỏ, đọc/ghi nguyên object | Luôn chuyển toàn value |
| Chia thành các key theo page/chunk | Có thể đọc một phần độc lập | Manifest, partial write, versioning, cleanup, key count |
| Redis Hash theo nhóm field | Chỉ cần đọc field cụ thể | Hạn chế field count, encoding, TTL cả key |
| Redis Sorted Set | Phân trang có thứ tự theo score/rank | Cần quản lý cardinality, ordering và cập nhật |
| Object storage + Redis pointer | Tài liệu lớn, media, snapshot | Độ trễ tải object, quyền truy cập, lifecycle hai hệ |
| Database có index | Truy vấn/phân trang theo nhiều thuộc tính | Chi phí vận hành và đặc tính transactional |

Không tự động tách một JSON 20 MB thành 20.000 key mỗi key 1 KB. Cách đó đổi vấn đề **big value** thành **key explosion**. Chọn phân vùng theo cách ứng dụng **thực sự truy cập**.

### 8.1. Mẫu reference thay vì lưu nội dung lớn

```text
Redis:
  report:913:meta -> {
      "objectId": "reports/913/v4.json",
      "etag": "...",
      "status": "READY",
      "byteSize": 20000000
  }

Object storage:
  reports/913/v4.json -> file lớn
```

Reader chỉ lấy metadata nhỏ qua Redis; khi người dùng yêu cầu report thì dùng signed URL hoặc service tải object có kiểm soát. Không để đường dẫn hoặc object ID từ Redis trở thành quyền truy cập public không kiểm tra.

### 8.2. Nếu buộc phải chia chunk

Ví dụ tên key:

```text
document:{913}:v4:chunk:0001
document:{913}:v4:chunk:0002
document:{913}:v4:chunk:0003
document:{913}:current -> v4
```

Ghi các chunk của version mới trước, xác minh đầy đủ, sau đó cập nhật pointer `current` **cuối cùng**. Reader chỉ dùng version được publish để tránh đọc nửa document cũ/nửa mới. Cần thêm checksum, số chunk dự kiến, TTL/cleanup và xử lý crash giữa chừng. Các key chung hash tag cùng slot, hữu ích cho locality nhưng có nguy cơ hot slot nếu một document cực lớn.

Trong Redis Cluster, các thao tác multi-key có ràng buộc hash slot. Không giả định pipeline hoặc nhiều lệnh `SET` tự trở thành một transaction nguyên tử.

## 9. Compression và serializer: giảm bytes nhưng có chi phí khác

Khi payload JSON có nhiều field lặp và đọc không quá thường xuyên, compression có thể giảm network và RAM. Tuy nhiên:

- Có thêm CPU compress/decompress và allocation.
- Không thể đọc trực tiếp bằng Redis CLI hoặc `StringRedisTemplate` nếu lưu binary nén.
- Payload nhỏ đôi khi nén **to hơn** do header/metadata.
- Không thể truy vấn từng field của một blob đã nén.
- Cần version format để reader cũ và mới cùng hoạt động.

Một contract có thể là:

```text
payloadBytes = JSON UTF-8
compressedBytes = gzip(payloadBytes) nếu vượt ngưỡng và tiết kiệm đủ
envelope = version + codec + payloadBytes
```

Hãy benchmark **bytes sau toàn bộ pipeline serialize → compress/encrypt** và thời gian CPU/p95, không chỉ tỷ lệ nén trung bình. Nếu hai service dùng chung key, cần contract về format; đổi serializer không chỉ là tối ưu nội bộ.

## 10. Kiểm soát số thành viên: các collection có ranh giới hữu hạn

Một Set có thể tăng nếu code luôn gọi:

```java
redis.opsForSet().add("product:100:viewers", userId);
```

Nếu Set dùng để lưu **tất cả** user từng xem sản phẩm, số thành viên có thể tăng không có điểm dừng. Đặt TTL cho **Redis key** không tự xóa từng member cũ khi Set vẫn được gia hạn liên tục.

Các lựa chọn:

1. **Hard cap:** từ chối thêm thành viên khi đạt ngưỡng.
2. **Sliding window:** chỉ giữ thành viên còn hoạt động trong khoảng thời gian gần đây.
3. **Top-N:** chỉ giữ N đối tượng có score cao nhất.
4. **Bucketing:** chia dữ liệu thành nhiều key theo thời gian, tenant hoặc phân vùng.
5. **Approximate cardinality:** nếu chỉ cần đếm unique, cân nhắc HyperLogLog thay vì lưu mọi ID.
6. **Cold storage:** chuyển lịch sử chi tiết khỏi Redis, giữ index/cache nhỏ.

Các chiến lược khác nhau về semantics. **Không áp dụng hard cap một cách im lặng** nếu ứng dụng cần lịch sử đầy đủ để kiểm toán.

## 11. Tránh race khi kiểm tra SCARD rồi SADD

Đoạn Java tưởng như đúng:

```java
Long count = redis.opsForSet().size(key);
if (count != null && count < 10_000) {
    redis.opsForSet().add(key, member);
}
```

Nhưng hai worker có thể cùng thấy `count = 9999`, rồi đều `SADD` thành viên khác nhau, khiến Set vượt 10.000. **Kiểm tra cardinality và thêm member phải là một thao tác nguyên tử** nếu ngưỡng là ràng buộc cứng.

### 11.1. Lua giới hạn số member của Set

Một script nhận `KEYS[1]` là Set, `ARGV[1]` là member, `ARGV[2]` là max:

```lua
local key = KEYS[1]
local member = ARGV[1]
local maxMembers = tonumber(ARGV[2])

if not maxMembers or maxMembers < 1 then
    return redis.error_reply('Invalid maxMembers')
end

-- Thành viên đã tồn tại: thao tác idempotent.
if redis.call('SISMEMBER', key, member) == 1 then
    return 0
end

if redis.call('SCARD', key) >= maxMembers then
    return -1
end

redis.call('SADD', key, member)
return 1
```

Quy ước kết quả:

| Kết quả | Ý nghĩa |
|---|---|
| `1` | Thêm một member mới |
| `0` | Member đã có, không tăng cardinality |
| `-1` | Set đã đầy, từ chối thêm |

Lua giúp `SISMEMBER`, `SCARD` và `SADD` chạy không bị các client Redis khác xen vào **trong cùng node thực thi script**. Trên Cluster, script có một Redis key nên dễ route theo slot của key đó. Đây là giới hạn **cardinality**, không phải giới hạn số bytes/member: một member dài 1 MB vẫn rất lớn và phải được kiểm tra ở Java trước khi gọi script.

### 11.2. Gọi script từ Spring Data Redis

```java
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

@Component
public class BoundedMemberSet {

    private static final int MAX_MEMBERS = 10_000;
    private static final int MAX_MEMBER_BYTES = 128;

    private static final String LUA = """
        local key = KEYS[1]
        local member = ARGV[1]
        local max = tonumber(ARGV[2])
        if redis.call('SISMEMBER', key, member) == 1 then
            return 0
        end
        if redis.call('SCARD', key) >= max then
            return -1
        end
        redis.call('SADD', key, member)
        return 1
        """;

    private static final DefaultRedisScript<Long> SCRIPT =
            new DefaultRedisScript<>(LUA, Long.class);

    private final StringRedisTemplate redis;

    public BoundedMemberSet(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean add(String productId, String memberId) {
        if (productId == null ||
                !productId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid productId");
        }
        if (memberId == null || memberId.isBlank() ||
                memberId.getBytes(StandardCharsets.UTF_8).length
                        > MAX_MEMBER_BYTES) {
            throw new IllegalArgumentException("Invalid memberId");
        }

        String key = "product:{" + productId + "}:viewers";
        Long result = redis.execute(
                SCRIPT, List.of(key),
                memberId, Integer.toString(MAX_MEMBERS));

        if (result == null) {
            throw new IllegalStateException("Result unavailable");
        }
        if (result == -1L) {
            throw new IllegalStateException("Set reached hard cap");
        }
        return result == 1L;
    }
}
```

Trong ví dụ, giới hạn `10.000` và `128 bytes` là chính sách thử nghiệm. Nếu cần Set tự expire, phải thiết kế **thêm** TTL; code trên cố tình không tự gia hạn hoặc xóa TTL để tránh thay đổi semantics ngoài phạm vi mẫu.

**Lưu ý thực tế:** một Set hard-capped có thể từ chối user mới vĩnh viễn nếu không có cơ chế xóa thành viên cũ. Nếu nghiệp vụ cần dữ liệu “đang hoạt động trong 15 phút”, nên chọn Sorted Set theo timestamp và dọn theo thời gian, thay vì một Set không có độ tuổi member.

## 12. Sliding window với Sorted Set

Ví dụ cần biết các user tương tác trong 15 phút gần đây. Với Sorted Set:

```text
Key:    activity:{product-100}
Member: userId
Score:  timestamp milliseconds
```

Mỗi lần user hoạt động, ghi:

```redis
ZADD activity:{product-100} 1763000000000 user-42
```

Dọn lịch sử cũ:

```redis
ZREMRANGEBYSCORE activity:{product-100} -inf 1762999100000
```

Giá trị timestamp trong ví dụ chỉ minh họa. Trong hệ thống thật, mốc cutoff được tính theo thời điểm hiện tại và duration chính sách. Nếu timestamp đến từ client không đáng tin, có thể có sai lệch clock; cân nhắc sử dụng clock server/phương pháp xác nhận thời gian.

Đếm thành viên còn giữ:

```redis
ZCARD activity:{product-100}
```

### 12.1. Phải dọn thường xuyên, không chỉ đếm

Nếu không gọi `ZREMRANGEBYSCORE` hoặc không có TTL key phù hợp, Sorted Set vẫn tăng vô hạn. Dọn theo mọi lần ghi, theo lịch hoặc theo chiến lược kết hợp; với Set rất lớn, việc xóa hàng loạt cũng có chi phí O(M) với số phần tử bị loại.

Nếu cần **giới hạn cứng** tối đa N thành viên ngoài giới hạn thời gian, thêm bước xóa phần tử rank thấp/cũ nhất có kiểm soát. Khi chạy đồng thời, dùng Lua để làm `ZADD`/`ZREMRANGEBYSCORE`/trim theo rank một cách nguyên tử nếu cần bảo đảm invariant.

### 12.2. Cẩn trọng với TTL

`EXPIRE activity:{product-100} 900` đặt TTL **cho toàn bộ Sorted Set**, không đặt TTL riêng cho từng member. Nếu cứ `EXPIRE` lại sau mỗi hoạt động, key có thể tồn tại mãi trong khi member cũ vẫn còn nếu không xóa theo score.

Không nhầm “key có TTL” với “collection tự giới hạn số member”. Hai chính sách độc lập.

## 13. Top-N với Sorted Set: chỉ giữ phần tử quan trọng nhất

Một bảng xếp hạng chỉ cần **100 sản phẩm có điểm cao nhất** không nên giữ vô hạn mọi sản phẩm trong cùng key chỉ để mỗi request gọi `ZREVRANGE 0 99`.

Ví dụ:

```redis
ZADD ranking:daily 98 product-100
ZADD ranking:daily 87 product-101

# Giữ lại tối đa 100 member có score cao nhất.
ZREMRANGEBYRANK ranking:daily 0 -101

# Chỉ đọc 20 phần tử đứng đầu.
ZREVRANGE ranking:daily 0 19 WITHSCORES
```

`ZREMRANGEBYRANK key 0 -101` loại các phần tử có rank thấp nhất, chừa tối đa 100 phần tử cuối (cao điểm nhất). Thao tác này không thay thế yêu cầu xếp hạng toàn bộ nếu ứng dụng thực sự cần truy vấn mọi sản phẩm: với một leaderboard chỉ lưu Top 100, phần tử xếp hạng 101 trở xuống đã bị loại.

Nếu nhiều writer cùng cập nhật ranking và phải giữ cap **tại mọi thời điểm**, gộp `ZADD` và trim rank trong Lua hoặc thiết kế writer duy nhất có kiểm soát. Hai lệnh độc lập có cửa sổ collection vượt ngưỡng.

### 13.1. Tránh đọc toàn bộ leaderboard

Trong Spring Data Redis:

```java
import java.util.Set;
import org.springframework.data.redis.core.StringRedisTemplate;

public Set<String> topProducts(
        StringRedisTemplate redis, int page, int size) {

    if (page < 0 || size < 1 || size > 100) {
        throw new IllegalArgumentException("Invalid page");
    }
    long start = (long) page * size;
    long end = start + size - 1;

    return redis.opsForZSet()
            .reverseRange("ranking:daily", start, end);
}
```

Truy vấn trả **một trang**, không tạo Map/List chứa toàn bộ Sorted Set. Tuy nhiên, phân trang theo rank không cung cấp snapshot ổn định khi score/member thay đổi đồng thời: các trang liên tiếp có thể bị trùng/thiếu vì thứ hạng thay đổi. Với yêu cầu phân trang bất biến, cần snapshot/version hoặc cursor theo score/member và quy tắc tie-break rõ.

## 14. Giới hạn List và phân biệt ring buffer với queue tin cậy

Một List chứa 100 log message gần nhất có thể dùng:

```redis
LPUSH audit:recent "event-101"
LTRIM audit:recent 0 99
```

`LPUSH` đưa phần tử mới lên đầu; `LTRIM 0 99` giữ 100 phần tử đầu. Nhưng nếu hai writer chạy đồng thời giữa hai lệnh, giới hạn có thể tạm vượt ngưỡng. Nếu cần atomic cap, dùng Lua:

```lua
redis.call('LPUSH', KEYS[1], ARGV[1])
redis.call('LTRIM', KEYS[1], 0, tonumber(ARGV[2]) - 1)
return redis.call('LLEN', KEYS[1])
```

Đây là **ring buffer best-effort** hoặc danh sách gần đây. Nó **không phải** hàng đợi xử lý công việc có ACK/replay: `LTRIM` xóa phần tử cũ ngay cả khi consumer chưa xử lý. Nếu message không được phép mất, dùng Redis Streams với consumer group hoặc hệ thống queue phù hợp.

### 14.1. Đọc theo khoảng

```redis
LRANGE audit:recent 0 19
LRANGE audit:recent 20 39
```

Trong Spring:

```java
List<String> firstPage =
        redis.opsForList().range("audit:recent", 0, 19);
```

Đừng gọi `range(key, 0, -1)` trong endpoint khi List có thể chứa hàng trăm nghìn phần tử.

## 15. Giới hạn Hash: số field và độ dài từng field-value

Ví dụ:

```text
user:{42}:preferences
  theme             -> "dark"
  locale            -> "vi-VN"
  notificationOptIn -> "true"
```

Một Hash gọn cho các thuộc tính liên quan có thể hiệu quả hơn việc tạo mỗi thuộc tính thành một Redis String riêng. Nhưng nếu một Hash chứa **một field cho mọi lần click của người dùng**, số field có thể tăng không giới hạn và trở thành big key.

Kiểm tra:

```redis
HLEN user:{42}:preferences
HSTRLEN user:{42}:preferences locale
HSCAN user:{42}:preferences 0 COUNT 50
MEMORY USAGE user:{42}:preferences
```

`HSTRLEN` đo độ dài bytes của một **field value kiểu String trong Hash**, không phải toàn bộ Hash. `HLEN` đo số field. Để đọc vài field đã biết, dùng `HMGET`/`HGET` thay vì `HGETALL`.

### 15.1. Compact encoding và listpack

Redis tối ưu nhiều aggregate nhỏ bằng compact encoding. Với Redis 7.x, Hash hoặc Sorted Set nhỏ có thể dùng **listpack**, chuyển sang biểu diễn khác khi vượt một số ngưỡng như:

```conf
hash-max-listpack-entries 512
hash-max-listpack-value 64
zset-max-listpack-entries 128
zset-max-listpack-value 64
```

Đây là **ví dụ default của một số Redis 7.x**, không phải cam kết mọi phiên bản Redis đều dùng cùng cấu hình. Khi collection vượt ngưỡng số lượng hoặc kích thước thành viên, Redis có thể đổi encoding và memory-per-entry thay đổi đáng kể.

Không tối ưu bằng cách tăng `hash-max-listpack-entries` lên hàng triệu mà chưa benchmark CPU và latency. Compact encoding tiết kiệm RAM nhưng một số thao tác có thể phải duyệt nhiều phần tử liên tiếp; Redis docs xem đó là tradeoff giữa bộ nhớ và CPU.

### 15.2. Hash có TTL ở cấp key

`EXPIRE user:{42}:preferences 600` đặt TTL cho toàn bộ Hash key. Các phiên bản Redis mới có thêm cơ chế expiration cấp field cho Hash, nhưng khả năng dùng qua Spring Data Redis phụ thuộc Redis version, driver và API cụ thể. Với hệ thống cần chạy nhiều phiên bản, không nên mặc định mỗi Hash field đều tự hết hạn như một Redis key độc lập.

Nếu muốn TTL riêng cho từng thuộc tính, cân nhắc các key riêng hoặc thiết kế value có timestamp và cleanup logic, đồng thời kiểm soát key count.

## 16. Redis Streams: MAXLEN, MINID, pending và retention

Một Stream luôn nhận sự kiện mới:

```redis
XADD events:checkout * eventId evt-001 type CREATED
```

Nếu không có retention, lịch sử có thể tăng vô hạn. Redis hỗ trợ thêm và trim gần như cùng lúc:

```redis
XADD events:checkout MAXLEN ~ 10000 * eventId evt-002 type CREATED
```

Dấu `~` yêu cầu **approximate trimming**, thường hiệu quả hơn cắt chính xác. Vì vậy `XLEN events:checkout` có thể **lớn hơn 10.000** trong thời gian nhất định, tùy tổ chức macro-node và phiên bản Redis. Nếu chính sách yêu cầu hard cap, xem `MAXLEN =` và đánh giá chi phí; nhưng một hard cap không có nghĩa retention phù hợp với consumer chậm.

### 16.1. Không trim dữ liệu chưa xử lý một cách mù quáng

Với consumer group:

```text
events:checkout
       |
       +--> billing-workers: PEL có message chưa ACK
       |
       +--> analytics-workers: đang đọc chậm
```

Nếu trim bản ghi cũ chỉ theo `MAXLEN`, message mà worker còn cần có thể bị xóa khỏi Stream trước khi recovery đọc lại. Một số phiên bản Redis có chính sách xử lý tham chiếu consumer group khi trim, nhưng phải xem đúng contract phiên bản server; không mặc định pending metadata bảo đảm payload còn lưu.

Xác định retention theo:

- Tốc độ sự kiện vào.
- Tốc độ tiêu thụ của group chậm nhất.
- Thời gian retry/backoff.
- Downtime có thể chấp nhận.
- Dung lượng RAM/disk.
- Khả năng archive sang nguồn dữ liệu bền vững hơn.

Một Stream hàng triệu entry có thể còn đọc được theo batch, nhưng server vẫn cần RAM và persistence; không nên coi Stream là kho lịch sử vô hạn miễn phí.

### 16.2. Truy vấn một phần lịch sử

```redis
XLEN events:checkout
XINFO STREAM events:checkout
XINFO GROUPS events:checkout
XRANGE events:checkout - + COUNT 100
```

Phân trang bằng Stream ID sau record cuối, không liên tục gọi `XRANGE - +` không giới hạn. Khi đọc theo consumer group, cần thiết kế recovery PEL riêng thay vì chỉ giới hạn batch size của `XREADGROUP`.

## 17. Tổng số key: TTL, namespace và vòng đời dữ liệu

Một code path nguy hiểm:

```java
redis.opsForValue().set(
        "request:" + requestId,
        json);
```

Nếu mỗi request tạo một key mới và **không có TTL/cleanup**, số key sẽ tăng theo tổng request tích lũy. Chẳng hạn, một ứng dụng có 500 request/giây tạo key mới sẽ sinh 43,2 triệu key sau một ngày — đây chỉ là phép tính sản lượng, chưa kể memory overhead.

Nếu chỉ cần dữ liệu trong thời gian ngắn, đặt TTL khi tạo:

```java
redis.opsForValue().set(
        "request:" + requestId,
        json,
        java.time.Duration.ofMinutes(30));
```

**Không phải dữ liệu nào cũng nên có TTL.** Key nghiệp vụ cần tồn tại đến khi được xác nhận/xử lý không nên bị xóa chỉ vì đã đủ một thời gian cố định. Cần phân loại:

| Loại dữ liệu | Vòng đời gợi ý |
|---|---|
| Cache | TTL theo độ mới và tải nguồn |
| Session | Expiration theo chính sách phiên |
| Deduplication key | TTL dài hơn khoảng retry/replay hợp lệ |
| Queue/Stream chưa ACK | Retention theo tiến độ xử lý và downtime |
| Temporary upload/chunk | TTL và cleanup cho version chưa publish |
| Lock | Lease TTL có gia hạn/ownership an toàn |
| Index phụ trợ | Đồng bộ vòng đời với dữ liệu mà nó mô tả |

### 17.1. TTL không phải giới hạn cứng của tổng số key

Giả sử số request/giây tăng gấp 10: cùng TTL 30 phút vẫn có thể tạo gấp 10 lần key đang sống. TTL giới hạn **thời gian** tồn tại, không trực tiếp giới hạn **tổng số lượng đồng thời**.

Muốn có ngân sách key, ước lượng:

```text
liveKeys ≈ newKeysPerSecond × averageLifetimeSeconds
```

Công thức gần đúng này giả định lưu lượng tương đối ổn định và ít xóa sớm. Thực tế cần dự phòng đỉnh traffic, expiration backlog, retry và phân bố TTL.

### 17.2. Tránh mọi key hết hạn cùng giây

Nếu một triệu cache key cùng được tạo trong batch và TTL đều 3600 giây, chúng có thể hết hạn gần nhau, gây spike làm mới cache, tăng DB load và tạo cache stampede. Khi nghiệp vụ cho phép, thêm **TTL jitter**:

```java
long baseSeconds = 3_600;
long jitterSeconds =
        java.util.concurrent.ThreadLocalRandom.current()
                .nextLong(0, 301);

java.time.Duration ttl =
        java.time.Duration.ofSeconds(
                baseSeconds + jitterSeconds);
```

Jitter trong ví dụ làm TTL dài thêm tối đa 300 giây. Nếu có hạn tối đa về độ cũ của dữ liệu, chọn khoảng jitter phù hợp và không để dữ liệu tồn tại vượt SLA.

## 18. maxmemory và eviction policy không thay thế thiết kế giới hạn

Redis có:

```redis
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
INFO memory
INFO stats
```

Các eviction policy thường gặp:

| Policy | Hành vi khái quát |
|---|---|
| `noeviction` | Không tự evict để phục vụ ghi mới; lệnh cần thêm memory có thể báo lỗi |
| `allkeys-lru` | Chọn key theo chính sách LRU gần đúng trên toàn keyspace |
| `allkeys-lfu` | Chọn key theo tần suất truy cập gần đúng |
| `volatile-lru` | Chỉ xét key có expiration |
| `volatile-ttl` | Ưu tiên key có expiration gần hơn theo chính sách |

**Không dùng eviction như cơ chế đảm bảo nghiệp vụ.** Nếu Redis vừa chứa cache có thể mất vừa chứa job chưa xử lý, `allkeys-lru` có thể xóa cả key job. Với dữ liệu quan trọng, tách instance/Cluster hoặc đảm bảo dùng storage phù hợp thay vì trộn chung một vùng RAM có eviction.

`maxmemory` cũng không đồng nghĩa toàn bộ process Redis luôn chiếm RAM nhỏ hơn đúng con số đó: replication/persistence buffers, allocator fragmentation, fork copy-on-write và các vùng memory khác có quy tắc tính riêng. Cần monitor memory RSS và headroom thực tế.

### 18.1. Khi memory chạm trần

Quan sát ít nhất:

- `used_memory` và `maxmemory`.
- `evicted_keys` tăng ra sao.
- `expired_keys` và số key có TTL.
- p95/p99 latency, error rate từ Spring.
- Các key/namespace nào đang tăng cardinality.
- Redis replication/persistence lag hoặc bị lỗi.

Không tăng `maxmemory` liên tục mà chưa xác định nguồn tăng trưởng. Nếu nguyên nhân là một Set không bao giờ xóa thành viên, RAM mới chỉ trì hoãn lỗi.

## 19. Spring Cache: tránh cache object và danh sách quá lớn

Ví dụ:

```java
@Cacheable(cacheNames = "productSearch", key = "#query")
public List<ProductDto> search(String query) {
    return productRepository.search(query);
}
```

Nếu truy vấn có thể trả 100.000 sản phẩm, cache **toàn bộ List** vào một key làm value quá lớn. Những client chỉ cần trang đầu vẫn phải deserialize cả List.

Thiết kế tốt hơn:

```java
@Cacheable(
        cacheNames = "productSearchPages",
        key = "#query + ':' + #page + ':' + #size")
public PageDto<ProductDto> searchPage(
        String query, int page, int size) {

    if (size < 1 || size > 100) {
        throw new IllegalArgumentException("Invalid size");
    }
    return productRepository.searchPage(query, page, size);
}
```

`ProductDto`, `PageDto` và repository là thành phần do dự án định nghĩa. Với `PageDto`, nên tránh serialize toàn bộ entity graph hoặc lazy relationship không cần thiết. Một trang 100 phần tử vẫn có thể rất lớn nếu mỗi ProductDto chứa hình ảnh nhúng hoặc nested object khổng lồ.

### 19.1. Trang riêng làm tăng số key

Page cache đổi một value lớn thành nhiều key nhỏ. Vì thế phải kiểm soát:

- Page size tối đa.
- Số query combinations được phép cache.
- Key generator/canonicalization.
- TTL và invalidation.
- Tần suất truy cập; không cache mọi query độc nhất của bot.
- Tổng key budget theo cache namespace.

Nếu mỗi người dùng tìm một chuỗi ngẫu nhiên và mỗi chuỗi tạo 100 key page, tổng key có thể bùng nổ dù từng value đều nhỏ. Cân nhắc chỉ cache query phổ biến hoặc dùng admission policy riêng.

### 19.2. Cache serializer cũng có overhead

`RedisCacheManager` có serializer riêng, không nhất thiết dùng serializer của `StringRedisTemplate`. Khi benchmark kích thước cache entry, hãy đo bytes **thực tế trong Redis**, không chỉ kích thước JSON bạn dự đoán. Type metadata, wrapper object và key prefix có thể làm tăng size.

## 20. Phân vùng collection để tránh một key không giới hạn

Một Hash toàn hệ thống:

```text
all:orders -> hàng triệu field orderId
```

khó mở rộng theo Cluster vì cả Hash chỉ nằm trên một slot. Một số thiết kế phân vùng:

```text
orders:{tenant-42}:2026-11
orders:{tenant-42}:2026-12

orders:{tenant-43}:2026-11
orders:{tenant-43}:2026-12
```

Nhưng ví dụ trên đều dùng `{tenant-42}` cho hai tháng của cùng tenant, nên các key đó **vẫn cùng hash slot**. Nếu muốn phân phối giữa tháng hoặc bucket, tag phải chứa bucket:

```text
orders:{tenant-42:2026-11}:part-00
orders:{tenant-42:2026-11}:part-01
orders:{tenant-42:2026-12}:part-00
```

Các key cùng tag `tenant-42:2026-11` lại cùng slot. Khi cần phân bố **ngay trong một tháng**, có thể dùng tag riêng theo partition:

```text
orders:{tenant-42:2026-11:p00}
orders:{tenant-42:2026-11:p01}
orders:{tenant-42:2026-11:p02}
```

Sự lựa chọn phụ thuộc nhu cầu atomic multi-key và cách truy vấn. Đưa mọi dữ liệu vào một tag chung có thể giữ locality nhưng gây **hot slot**. Chia nhỏ theo tag làm giảm khả năng transaction nhiều key xuyên partition.

### 20.1. Ước lượng số partition

Ví dụ target trung bình 5.000 member/partition và dự kiến tối đa 200.000 member:

```text
Số partition tối thiểu theo trung bình = ceil(200000 / 5000) = 40
```

Đây là phép tính capacity planning, không bảo đảm mọi partition chỉ có 5.000 member khi hash phân phối không đều. Với ràng buộc cứng, vẫn cần guard cardinality và kế hoạch tăng partition. Ngoài ra phải tính metadata key và tác động khi query phải fan-out nhiều partition.

### 20.2. Tránh một thao tác tìm tất cả

Khi chia dữ liệu thành 40 partition, một request “lấy mọi member” có thể tạo 40 truy vấn và vẫn tải 200.000 member — vấn đề chỉ được chuyển chỗ. Nên thiết kế API phân trang, index theo nhu cầu, hoặc chuyển truy vấn tổng hợp sang storage chuyên trách.

## 21. SCAN bằng StringRedisTemplate và đóng Cursor

Ví dụ quét key theo namespace để **kiểm kê có giới hạn**:

```java
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

public List<String> sampleKeys(
        StringRedisTemplate redis, String prefix, int maxKeys) {

    if (prefix == null ||
            !prefix.matches("[A-Za-z0-9:_-]{1,64}")) {
        throw new IllegalArgumentException("Invalid prefix");
    }
    if (maxKeys < 1 || maxKeys > 1_000) {
        throw new IllegalArgumentException("Invalid cap");
    }

    List<String> result = new ArrayList<>();
    ScanOptions options = ScanOptions.scanOptions()
            .match(prefix + "*")
            .count(100)
            .build();

    try (Cursor<String> cursor = redis.scan(options)) {
        while (cursor.hasNext() && result.size() < maxKeys) {
            result.add(cursor.next());
        }
    }
    return result;
}
```

Điểm cần hiểu:

- `maxKeys` giới hạn **số key trả về trong List ở Java**, không bảo đảm Redis chỉ phải xét `maxKeys` key.
- `SCAN` có thể trả trùng khi keyspace thay đổi. Nếu cần unique, dùng `Set` ở client, vẫn giới hạn memory.
- `Cursor` phải được đóng.
- Không dùng kết quả của một lượt sample làm số key chính xác của namespace.
- Phạm vi `scan` trên Cluster phụ thuộc adapter/API/driver; một scan trên connection/node không nhất thiết duyệt toàn Cluster. Muốn inventory toàn Cluster phải xác định tất cả master/shard.

Với keyspace rất lớn, một hệ thống monitoring chuyên biệt hoặc thống kê tại thời điểm ghi/xóa có thể thích hợp hơn việc liên tục scan hàng triệu key để tính tổng.

## 22. Dọn big keys: UNLINK, batching và quyền sở hữu dữ liệu

Khi cần xóa một Set/Hash/List lớn khỏi Redis, `DEL` có thể tốn thời gian giải phóng cấu trúc dữ liệu. Redis cung cấp:

```redis
UNLINK old:oversized:set
```

`UNLINK` gỡ key khỏi keyspace và giải phóng phần lớn memory của value ở background, giúp giảm độ trễ trên luồng xử lý lệnh so với `DEL` đối với những đối tượng lớn. Nhưng việc **RAM thực tế được trả về** có thể xảy ra sau lệnh và tùy allocator; đừng mong `used_memory_rss` giảm tức thì.

Trong Spring Data Redis:

```java
Boolean removed = redis.unlink("old:oversized:set");
```

Chỉ xóa key khi đã xác định đúng namespace, quyền sở hữu và chính sách retention. Không dùng `SCAN app:*` rồi `UNLINK` hàng triệu key một lúc trong request path; nên:

1. Chạy cleanup job có giới hạn rate/batch.
2. Ghi lý do xóa và xác minh key pattern chặt.
3. Dùng cursor để tìm key, xử lý idempotent khi key đã biến mất.
4. Theo dõi Redis latency, background free backlog và memory.
5. Có kế hoạch ngừng/rollback nếu xóa nhầm phạm vi.

Nếu key vẫn được writer tạo lại hoặc thêm member sau cleanup, việc xóa một lần chỉ xử lý triệu chứng. Phải sửa **đường ghi** để dữ liệu không tiếp tục tăng vô hạn.

## 23. Khi nào dùng HyperLogLog, Bitmap hoặc Bloom filter?

Một số ứng dụng lưu Set chỉ để biết **có khoảng bao nhiêu user duy nhất**, không cần lấy lại danh sách ID.

Ví dụ:

```redis
PFADD visitors:daily:2026-11-13 user-42
PFADD visitors:daily:2026-11-13 user-43
PFCOUNT visitors:daily:2026-11-13
```

Redis HyperLogLog cho phép **ước lượng số phần tử distinct** với memory nhỏ, nhưng không thể liệt kê toàn bộ member. Nó có sai số thống kê, không phù hợp khi yêu cầu đếm tuyệt đối chính xác hoặc tra cứu membership chính xác.

| Cấu trúc | Có thể hỏi | Không phù hợp khi |
|---|---|---|
| Set | Membership chính xác, liệt kê member | Số ID cực lớn mà chỉ cần thống kê tổng |
| HyperLogLog | Distinct count ước lượng | Cần biết chính xác từng ID hoặc count tuyệt đối |
| Bitmap | Trạng thái bit theo integer offset | ID thưa/khổng lồ không ánh xạ tốt thành offset |
| Bloom filter (module/implementation phù hợp) | Membership **có thể có**, với false positives | Không chấp nhận false positive hoặc cần liệt kê phần tử |

Không tự chuyển Set chứa userId sang HyperLogLog nếu nghiệp vụ cần xuất danh sách user đã xem. Lựa chọn tối ưu RAM không được làm mất yêu cầu dữ liệu.

## 24. Redis Cluster: giới hạn theo node, slot và big/hot keys

Redis Cluster dùng 16.384 hash slot:

```text
Redis key bytes --> CRC16 --> slot --> master node
```

Các lệnh đo như `MEMORY USAGE key` và `SCARD key` phải được gửi tới node đang phục vụ key; cluster-aware client có thể route giúp ứng dụng. Nhưng lệnh `INFO memory` trả số liệu **node** đang hỏi, không tự là tổng toàn Cluster.

### 24.1. Một big key không được chia ra nhờ Cluster

```text
giant:set -> slot s -> Master B
```

Thêm Master C không khiến `giant:set` tách thành hai phần. Muốn phân phối một tập rất lớn, phải **đổi data model** thành nhiều key/partition với quy tắc phân bố slot.

### 24.2. Hash tag có thể gây nóng cả shard

```text
user:{enterprise}:1
user:{enterprise}:2
user:{enterprise}:3
... tất cả cùng slot
```

Tag chung `{enterprise}` tạo locality nhưng cũng tập trung tải vào một master. Đặt hash tag theo **đơn vị thật sự cần multi-key atomicity**, thay vì toàn bộ dữ liệu của một tenant lớn.

### 24.3. Đừng nhầm SCAN một node với toàn Cluster

`SCAN` chỉ nhìn key mà node/connection đang duyệt. Một dashboard muốn tổng key/bytes toàn Cluster cần lấy dữ liệu theo master/shard, tránh đếm trùng replica và chú ý resharding/failover trong lúc snapshot. Redis `CLUSTER SHARDS` có thể dùng để khám phá topology trên Redis version hỗ trợ.

## 25. Reactive Redis: backpressure không tự chia nhỏ lệnh

Với `ReactiveRedisTemplate`, downstream có backpressure và cancellation. Nhưng:

```java
reactiveRedis.opsForSet().members("huge:set")
```

Việc API trả `Flux` không nhất thiết biến một lệnh Redis trả **toàn bộ Set** thành các lệnh `SSCAN` nhỏ. Nếu tầng driver đã yêu cầu toàn bộ collection, client vẫn có thể nhận một reply lớn trước khi downstream xử lý từng phần tử.

Muốn incremental iteration, chọn **API/command thực sự dùng SCAN** và kiểm tra nó có streaming/scan semantics, ví dụ `ReactiveSetOperations.scan(...)` trên phiên bản Spring Data Redis hỗ trợ. Phải đo network bytes, connection lifetime, backpressure và giới hạn concurrency.

### 25.1. Giới hạn request và xử lý theo batch

Một chuỗi reactive có thể giới hạn số request đồng thời:

```java
Flux.fromIterable(ids)
    .flatMap(
        id -> reactiveRedis.opsForValue().get("product:" + id),
        16
    );
```

`flatMap(..., 16)` giới hạn số Publisher inner được subscribe đồng thời, **không** giới hạn kích thước value của mỗi `GET`. Nếu mỗi product value là 5 MB, 16 lượt song song vẫn có thể tiêu thụ nhiều memory. Cần kết hợp:

- Giới hạn bytes/value.
- Giới hạn số ID/request.
- Concurrency hợp lý.
- Timeout, circuit breaker và đo latency.
- Không `collectList()` một Flux vô hạn hoặc cực lớn.

Reactive programming không thể sửa một data model chứa big key chỉ bằng operator.

## 26. Quan sát hiệu năng bằng SLOWLOG và latency

Một số lệnh Redis:

```redis
SLOWLOG LEN
SLOWLOG GET 20
LATENCY LATEST
INFO commandstats
INFO memory
INFO stats
```

`SLOWLOG` ghi thời gian **Redis thực thi lệnh** vượt ngưỡng được cấu hình, không đo toàn bộ network round trip hay thời gian deserialize trong JVM. Một response JSON 10 MB có thể làm HTTP request chậm nhưng không nhất thiết xuất hiện nổi bật trong SLOWLOG nếu bản thân việc tra key nhanh và chi phí transfer/parse nằm ngoài phần Redis command execution được đo.

Theo dõi cùng lúc:

| Thành phần | Chỉ số |
|---|---|
| Redis | command latency, slowlog, CPU, memory, evicted keys |
| Network | bytes/sec, bandwidth, socket timeouts |
| Lettuce/Jedis | command timeout, pool/connection pressure |
| Java | heap usage, allocation, GC pauses, deserialization time |
| HTTP | p50/p95/p99 latency, response bytes, error rate |
| Data model | max value bytes, max members/key, total keys/namespace |

Đừng áp dụng sửa Redis server khi nguyên nhân thật là một controller chuyển 100.000 DTO thành JSON mỗi lần gọi.

## 27. Đặt budget/guardrail theo namespace

Một bảng chính sách mẫu:

| Namespace | Kiểu | Giới hạn minh họa | Vòng đời | Đường đọc |
|---|---|---|---|---|
| `cache:product:*` | String JSON | 64 KiB/value | TTL 30 phút ± jitter | `GET` |
| `session:*` | String | 8 KiB/value | TTL theo session | `GET` |
| `cart:{user}:items` | Hash | 200 fields | TTL theo cart | `HMGET` |
| `activity:{product}` | ZSet | 10.000 members | Sliding window 15 phút | `ZRANGE` theo trang |
| `ranking:daily` | ZSet | Top 1000 | Rebuild theo ngày | Top-N pages |
| `events:checkout` | Stream | Retention theo backlog/SLA | XTRIM/archiving an toàn | Consumer group |
| `request:*` | String | 2 KiB/value | TTL 30 phút | Đọc theo ID |

**Các con số chỉ để minh họa cách viết policy**, chưa được benchmark. Một namespace có thể có thêm giới hạn tổng key count và tổng memory:

```text
namespace:
  maxValueBytes
  maxMemberBytes
  maxMembersPerKey
  maxKeysEstimate
  maxRetentionAge
  maxScanWorkPerJob
  maxReadPageSize
  expectedReadRate
  priorityForEviction
```

Redis không có cấu hình built-in áp dụng tất cả những quota này tự động theo prefix. Phần lớn phải được thực thi ở tầng ứng dụng, Lua/script, scheduler, proxy hoặc kiến trúc namespace/instance.

## 28. Kiểm thử kích thước, cardinality và số key với Spring Data Redis

Một bài test tốt không chỉ kiểm tra return value mà còn đo **state thật trong Redis**.

### 28.1. Testcontainers trên Redis riêng

Ví dụ khung test Spring Boot 3.x + JUnit 5:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
```

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class RedisSizePolicyIntegrationTest {

    @Container
    static final GenericContainer<?> redis =
            new GenericContainer<>(
                DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisSettings(DynamicPropertyRegistry props) {
        props.add("spring.data.redis.host", redis::getHost);
        props.add("spring.data.redis.port",
                () -> redis.getMappedPort(6379));
    }

    @Autowired
    StringRedisTemplate template;

    @Test
    void redisIsAvailable() {
        // Thêm assertions có ý nghĩa ở các test phía sau.
    }
}
```

Testcontainers yêu cầu Docker/compatible runtime; code chỉ minh họa test để triển khai trong dự án. Không dùng production Redis làm target của load test. Khi nâng phiên bản Redis, kiểm tra cả hành vi memory/encoding trên phiên bản thực tế.

### 28.2. Test giới hạn UTF-8 bytes

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Test
void rejectValueExceedingByteLimit() {
    String payload = "🚀".repeat(10_000);

    assertThatThrownBy(() ->
            boundedCache.store("tenant42",
                    new SettingsDto(payload)))
        .isInstanceOf(IllegalArgumentException.class);
}
```

`boundedCache` và `SettingsDto` là những thành phần nghiệp vụ phù hợp với service ở mục 7. Test nên kiểm tra sau lỗi **không tạo Redis key**, và kiểm tra riêng giá trị đúng bằng limit có được chấp nhận theo policy hay không.

### 28.3. Test giới hạn Set atomic dưới cạnh tranh

1. Chọn một key test và cap nhỏ, ví dụ `maxMembers = 10`.
2. Khởi chạy 50 tác vụ thêm **50 member khác nhau** đồng thời.
3. Đợi tất cả kết thúc.
4. Kiểm tra `SCARD` không vượt `10`.
5. Thử thêm lại một member đã có; trạng thái không bị xem là vượt ngưỡng theo semantics thiết kế.

Không khẳng định code `SCARD` rồi `SADD` hai lệnh độc lập là atomic chỉ vì test hiếm khi tái hiện race; phải dùng một primitive bảo đảm đúng, ví dụ Lua của mục 11.

### 28.4. Test giá trị lớn và memory/latency

Với Redis test:

```text
Dataset A: 10.000 String, mỗi value 100 B
Dataset B: 10.000 String, mỗi value 10 KiB
Dataset C: 1 Hash với 10.000 field
Dataset D: 10.000 Hash với 1 field
```

Đo:

- `INFO memory` trước/sau.
- `MEMORY USAGE` của key mẫu.
- Latency `GET`/`HGET`/`HSCAN`.
- Java allocations/GC khi đọc 10, 100, 1.000 phần tử.
- Thời gian load RDB và network traffic nếu liên quan.

Không dùng những con số thu được từ laptop làm ngưỡng production không cần kiểm chứng. So sánh theo nhiều kích thước payload, số request đồng thời và topology tương ứng.

## 29. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| `GET` đơn lẻ rất chậm | Value quá lớn, deserialize/HTTP response nặng | Đo bytes, chuyển sang page/reference |
| Redis memory tăng dù QPS không đổi | Key không TTL hoặc collection tích lũy member | Đo namespace cardinality, lifecycle |
| `SMEMBERS` làm request timeout | Đọc toàn Set lớn | `SSCAN` hoặc index phân trang |
| `HGETALL` tạo GC spike | Hash nhiều field/value | `HMGET` field cần, phân trang hoặc split |
| `SCAN COUNT 100` trả hơn 100 | COUNT chỉ là hint | Giới hạn application output, không giả định batch exact |
| `MEMORY USAGE` nhỏ hơn dự đoán hoặc biến động | Sampling/encoding/allocator | Quan sát SAMPLES, Redis version, dataset |
| Set vượt cap dù có `SCARD` check | Race giữa check và add | Lua atomic hoặc mô hình khác |
| TTL tăng mãi nhưng Set vẫn phình | TTL ở cấp key được refresh, member cũ không xóa | Sliding window theo score |
| Redis key count tăng dù data gốc nhỏ | Per-request/per-field key explosion | Chọn aggregation/bucketing và TTL |
| Redis Cluster vẫn có một master quá tải | Hot key/hash tag quá rộng | Chia data model thành nhiều key/slot |
| Cache nhiều key nhưng ít hit | Cache key cardinality theo query người dùng | Cân nhắc admission/cache only hot queries |
| `XADD MAXLEN ~ N` có `XLEN > N` | Approximate trimming | Chấp nhận headroom hoặc đổi policy |
| Stream trim làm worker mất record pending | Retention không xét consumer group | Phối hợp ACK/retention/archiving |
| `DEL` big key gây latency spike | Free cấu trúc lớn trên đường command | `UNLINK` và bounded cleanup |
| `used_memory` thấp nhưng HTTP chậm | Bottleneck network/JVM/response serialization | Đo end-to-end, không chỉ Redis |
| Eviction xóa cả dữ liệu quan trọng | Trộn cache và job data dưới allkeys policy | Tách deployment hoặc chọn storage phù hợp |
| `redisTemplate.keys("*")` ảnh hưởng production | Dùng KEYS quét toàn bộ | SCAN hoặc thống kê phát sinh từ writer |
| Thay serializer khiến value lớn bất ngờ | Metadata/UTF-8/compression format | Đo serialized bytes và contract test |
| Xóa bớt key nhưng RAM RSS chưa giảm ngay | Allocator/fragmentation/async free | Theo dõi INFO memory và memory pressure thực |

## 30. Bài thực hành

### Bài 1 — Phân biệt bytes, members và RAM

1. Ghi một String có Unicode và một Hash 50 field.
2. Dùng `STRLEN`/`HLEN`/`MEMORY USAGE`.
3. Giải thích tại sao `STRLEN` và `MEMORY USAGE` không trả cùng một số.
4. Thêm 5.000 field vào Hash test, quan sát memory và thời gian `HGETALL`.
5. Dùng `HSCAN` với cursor để duyệt có giới hạn.

### Bài 2 — Phát hiện big keys

1. Tạo vài String, Hash, Set, ZSet với kích thước khác nhau trên Redis test.
2. Chạy `redis-cli --bigkeys` và `--memkeys`.
3. So sánh key có nhiều member nhất với key dùng RAM lớn nhất.
4. Chạy `MEMORY USAGE key SAMPLES 0` **chỉ trên collection test**.
5. Ghi lại chi phí và nhận xét về sampling.

### Bài 3 — Đo giá trị JSON sau serialization

1. Tạo DTO chứa tiếng Việt/emoji.
2. Serialize thành UTF-8 bytes.
3. Đo `bytes.length` và `String.length()`.
4. Áp dụng cap ví dụ 32 KiB.
5. Test payload ngay dưới, bằng và vượt cap; bảo đảm payload vượt cap không được ghi.

### Bài 4 — Giới hạn Set không race

1. Thử mẫu `SCARD` rồi `SADD` dưới 20 worker đồng thời.
2. Thay bằng Lua atomic.
3. Đo `SCARD` cuối cùng.
4. Thử member đã tồn tại khi Set đầy.
5. Thêm limit bytes/member để ngăn một thành viên quá lớn.

### Bài 5 — Sliding window và Top-N

1. Dùng Sorted Set ghi activity với score timestamp.
2. Xóa member cũ bằng `ZREMRANGEBYSCORE`.
3. Dùng `ZCARD` xác nhận cardinality.
4. Tạo leaderboard và trim theo rank để giữ Top 100.
5. Đọc theo trang thay vì tải toàn bộ Set.

### Bài 6 — So sánh key explosion với Hash

1. Tạo 10.000 key String mỗi key chứa một field giả lập.
2. Đo `INFO memory`.
3. Dọn key test có kiểm soát.
4. Tạo cùng dữ liệu trong một hoặc vài Hash theo business boundary.
5. Đo lại memory, latency và chi phí đọc field riêng.
6. Giải thích tradeoff: Hash ít key hơn nhưng có thể thành big/hot key.

### Bài 7 — Giới hạn Streams

1. Tạo Stream test bằng `XADD MAXLEN ~ 1000`.
2. Ghi nhiều hơn 1000 entry.
3. Quan sát `XLEN` có thể vượt 1000.
4. Tạo consumer group và để một message pending.
5. Đánh giá tác động retention tới PEL/payload; thiết kế theo thời gian downtime thực tế.

### Bài 8 — Redis Cluster và hot slot

1. Với Cluster test, tạo các key cùng hash tag `{all}` và ghi `CLUSTER KEYSLOT`.
2. Tạo key có tag theo partition.
3. Quan sát slot distribution.
4. Giải thích vì sao một big key không tự phân tán khi thêm master.
5. Đề xuất phân vùng đáp ứng cả yêu cầu cùng-slot và scale.

## 31. Checklist thiết kế trước khi đưa vào production

1. Mỗi namespace đã có **max value bytes** sau serialization chưa?
2. Có giới hạn độ dài key và member ID chưa?
3. Đã chọn structure phù hợp với truy vấn: String, Hash, Set, ZSet, Stream?
4. Có giới hạn cardinality hoặc retention trên collection luôn tăng?
5. Ràng buộc hard cap có được thực thi nguyên tử dưới concurrency?
6. Endpoint có page size tối đa và không tải toàn collection?
7. `SCAN` có cursor, đóng tài nguyên và giới hạn ảnh hưởng vận hành?
8. Đã loại bỏ `KEYS *`/`SMEMBERS`/`HGETALL` từ đường xử lý có thể gặp dữ liệu lớn?
9. Có TTL/cleanup hoặc nguồn sự thật để khôi phục dữ liệu tạm?
10. Đã tính key count theo traffic × lifetime và dự phòng đỉnh tải?
11. Có phân biệt big key với hot key và hot slot?
12. Có đo Redis `MEMORY USAGE`/`INFO memory` bên cạnh network/JVM p99?
13. Eviction policy có phù hợp mức quan trọng của dữ liệu?
14. Với Spring Cache, có giới hạn page/query combinations và serializer?
15. Với Redis Streams, retention có xét PEL, ACK và consumer chậm?
16. Với Cluster, có kiểm tra data distribution trên từng master?
17. Dọn dẹp big key có dùng `UNLINK`/bounded job khi phù hợp?
18. Có integration test với dữ liệu gần cỡ production và kiểm tra concurrency?
19. Các ngưỡng có dashboard/alert và owner xử lý khi vượt?
20. Có phương án migration/repartition nếu dataset tăng vượt thiết kế ban đầu?

## 32. Kết luận

Kiểm soát hiệu năng Redis không thể chỉ dựa vào việc “Redis chạy trong RAM”. **Kích thước một value**, **số phần tử của một collection** và **tổng số key** là ba nguồn chi phí khác nhau; hot key và hot slot làm chúng trầm trọng hơn.

Với value, đo **bytes sau serialization**, đặt giới hạn ngay tại đường ghi và dùng pagination/reference thay cho một JSON khổng lồ. Với Set/Hash/List/ZSet, đo cardinality bằng lệnh chuyên biệt, tránh tải toàn bộ collection và dùng Lua khi cần áp dụng một hard cap không race. Với Streams, đặt retention theo consumer group và chấp nhận rằng `MAXLEN ~` là giới hạn gần đúng. Với tổng key count, thiết kế TTL/lifecycle, budget theo traffic, dọn dẹp có kiểm soát và tránh tạo một key cho mọi sự kiện ngắn hạn.

Cuối cùng, dùng `MEMORY USAGE`, `INFO memory`, `--bigkeys`/`--memkeys` và `SCAN` để hiểu dữ liệu thực; kết hợp SLOWLOG, network, JVM/GC và p99 latency để tìm đúng bottleneck. **Giới hạn phải được kiểm thử ở Redis thật theo workload và phiên bản triển khai**, bởi một hệ thống có hàng triệu key nhỏ và một hệ thống có một Hash triệu field cần hai chiến lược tối ưu hoàn toàn khác nhau.

## Tài liệu tham khảo

- [Redis — MEMORY USAGE](https://redis.io/docs/latest/commands/memory-usage/): bytes/key, overhead và `SAMPLES`.
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/): cursor, `COUNT`, tính lặp và giới hạn consistency.
- [Redis — Redis CLI](https://redis.io/docs/latest/develop/tools/cli/): `--bigkeys`, `--memkeys`, `--keystats` và tùy chọn scan.
- [Redis — STRLEN](https://redis.io/docs/latest/commands/strlen/): độ dài bytes của Redis String.
- [Redis — HLEN](https://redis.io/docs/latest/commands/hlen/): đếm fields của Hash.
- [Redis — SCARD](https://redis.io/docs/latest/commands/scard/): đếm members của Set.
- [Redis — ZCARD](https://redis.io/docs/latest/commands/zcard/): đếm members của Sorted Set.
- [Redis — LLEN](https://redis.io/docs/latest/commands/llen/): đếm List entries.
- [Redis — XADD](https://redis.io/docs/latest/commands/xadd/): `MAXLEN` và trimming của Stream.
- [Redis — UNLINK](https://redis.io/docs/latest/commands/unlink/): xóa key và giải phóng bộ nhớ bất đồng bộ.
- [Redis — Memory optimization](https://redis.io/docs/latest/management/optimization/memory-optimization/): compact encoding, listpack và tradeoff CPU/RAM.
- [Redis — Diagnosing latency](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/): big collections, blocking commands và đo latency.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): template, serializers và thao tác Redis.
- [Spring Data Redis — RedisTemplate API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/RedisTemplate.html): `scan`, `unlink` và quản lý Cursor.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): cache configuration, serializer, TTL và prefix.
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): stream retention và consumer groups.
