# Đo độ trễ, thông lượng và kích thước dữ liệu thực tế trong Spring Data Redis

## 1. Vì sao phải đo thay vì chỉ nói “Redis rất nhanh”?

Redis thường được lựa chọn vì lưu dữ liệu trong bộ nhớ và xử lý nhiều thao tác với độ trễ thấp. Spring Data Redis giúp ứng dụng Java gọi Redis qua `RedisTemplate`, `StringRedisTemplate`, Redis Cache, Redis Repository hoặc API reactive. Tuy nhiên, nhận định “Redis nhanh” không trả lời được những câu hỏi vận hành:

- Một lệnh `GET` mất bao nhiêu mili giây **từ góc nhìn ứng dụng**?
- Endpoint HTTP dùng cache có độ trễ p95/p99 bao nhiêu, và bao nhiêu phần thời gian nằm ở Redis?
- Một instance Spring Boot có thể phục vụ bao nhiêu request/giây trước khi p99 vượt ngưỡng?
- Một request thực tế phát sinh bao nhiêu Redis commands? `RPS` có bằng `Redis ops/s` không?
- Lưu một DTO JSON 1 KiB có thực sự tốn đúng 1 KiB RAM trên Redis không?
- Với một triệu key, lượng RAM cần dự trù là bao nhiêu, tính cả metadata, expiration, index và fragmentation?
- Pipelining có giảm thời gian toàn batch nhưng làm một số request khác chậm đi không?
- Khi tăng concurrency, bottleneck nằm ở Java serializer, event-loop, network, Redis server, Redis Cluster hay database tải lại khi cache miss?
- Một benchmark `redis-benchmark` đạt 100.000 requests/s có chứng minh ứng dụng thật đạt 100.000 business requests/s không?

Để trả lời, cần đo **ba nhóm chỉ số liên quan nhưng khác nhau**:

1. **Độ trễ (latency):** mỗi thao tác mất bao lâu, đặc biệt ở những percentile xấu như p95 và p99.
2. **Thông lượng (throughput):** số thao tác hoàn thành trong một đơn vị thời gian, kết hợp lưu lượng bytes và concurrency.
3. **Kích thước dữ liệu thực tế:** bytes của key/payload trên đường truyền, lượng bộ nhớ Redis thực sự dùng, overhead của cấu trúc dữ liệu, index và các thành phần hệ thống.

Một ứng dụng có thể có throughput cao nhưng p99 rất tệ. Một key JSON chỉ 500 byte có thể tiêu thụ nhiều hơn 500 byte trong RAM. Một lệnh Redis hoàn thành trong vài chục micro giây ở server vẫn có thể mất hàng chục mili giây tại endpoint Java vì network, serialization hoặc hàng đợi.

**Mục tiêu của đo hiệu năng không phải tìm ra một con số đẹp nhất, mà là xác định hành vi của hệ thống dưới workload giống production, đo được giới hạn và chứng minh thay đổi tối ưu thực sự có lợi.**

### Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt latency tại HTTP, service, Redis client, Redis server và network.
2. Đọc p50, p95, p99, max và phân phối độ trễ thay vì chỉ average.
3. Phân biệt RPS, Redis commands/s, records/s, bytes/s và tốc độ business operations.
4. Đo Spring Data Redis bằng Micrometer/Actuator và ghi nhận lỗi, timeout, hit/miss.
5. Sử dụng `INFO`, `SLOWLOG`, `LATENCY`, `MEMORY USAGE`, `SCAN` và benchmark Redis đúng phạm vi.
6. Đo kích thước payload đã serialize, key bytes và RAM thực tế cho từng loại Redis data structure.
7. Tính dung lượng ở mức dự trù dựa trên phân phối kích thước và số lượng key thực.
8. Thiết kế load test có warm-up, concurrency, read/write mix, hot keys, TLS và representative data.
9. Đánh giá pipeline, batch, TTL, serializer, Redis Cluster, Cache và Streams.
10. Chuyển số đo thành quyết định tối ưu có thể kiểm chứng và bộ chỉ số giám sát production.

## 2. Một request trong Spring Data Redis đi qua những đâu?

Xét API đọc sản phẩm dùng Redis Cache:

```text
Browser / API client
      |
      v
Ingress / Load balancer
      |
      v
Spring WebFlux / Spring MVC endpoint
      |
      +--> Security / validation
      |
      +--> Service
              |
              +--> Spring Cache / RedisTemplate
              |       |
              |       +--> Sinh key / serialize key
              |       +--> Lấy hoặc tạo Redis connection
              |       +--> Encode Redis command
              |       +--> Network request
              |       +--> Redis server queue/execute
              |       +--> Network response
              |       +--> Decode reply / deserialize value
              |
              +--> Cache miss?
                      |
                      +--> Database / external API
                      +--> Serialize + SET cache
              |
              v
         Map DTO / render response
              |
              v
        HTTP response
```

Nếu chỉ nhìn thời gian Redis xử lý `GET`, ta bỏ qua nhiều thành phần. Nếu chỉ nhìn HTTP latency, ta lại không biết Redis có phải thủ phạm.

Nên định nghĩa rõ từng phép đo:

| Phạm vi | Bắt đầu | Kết thúc | Điều được đo |
|---|---|---|---|
| HTTP end-to-end | Client gửi request | Client nhận response đầy đủ | App + mạng + proxy + Redis + dependency |
| Server HTTP latency | Request vào server | Server hoàn thành response | App và các dependency bên trong |
| Business service latency | Method nghiệp vụ bắt đầu | Method kết thúc | Tùy vị trí instrumentation |
| Redis operation latency từ ứng dụng | Bắt đầu lệnh qua Redis client | Client hoàn tất hoặc lỗi | Serialization/connection/network/Redis/response tùy điểm đặt timer |
| Redis command execution | Redis bắt đầu xử lý command | Redis hoàn thành xử lý nội bộ | Thời gian thực thi tại server, thường không bao gồm RTT mạng |
| Serialization latency | Bắt đầu chuyển DTO sang bytes | Hoàn tất bytes | CPU và allocation trong JVM |
| Network RTT | Gửi/nhận gói hoặc kiểm tra kết nối | Nhận phản hồi | Tầng mạng, không thay thế command timing |

Khi nói “Redis latency = 5 ms”, phải hỏi **5 ms đo ở đâu?** Cùng một hệ thống có thể ghi nhận:

```text
Server command execution:     0,05 ms
Redis client round-trip:      1,8 ms
Serialize + Redis + decode:   2,4 ms
HTTP endpoint end-to-end:    16,0 ms
```

Đây là số **minh họa**, không phải giá trị mặc định của Redis.

### 2.1. Độ trễ khác số lần gọi lệnh

Một method Java:

```java
public ProductDto getProduct(String id) {
    return cache.get(id);
}
```

có thể gây:

- Một `GET`.
- Hai lệnh vì logic kiểm tra TTL/metadata.
- Nhiều lệnh do repository/index.
- `GET` bị miss và một `SET` bổ sung.
- Retry command do timeout.
- Lệnh nhiều key hoặc pipeline.

Để đo chính xác, cần biết method phát sinh **bao nhiêu Redis operations**, không đoán dựa trên số dòng Java.

## 3. Latency: trung bình thường che giấu tail latency

Độ trễ của một thao tác là thời gian từ mốc bắt đầu đến mốc kết thúc đã xác định.

Các phép tổng hợp phổ biến:

- **Mean/average:** tổng thời gian chia số mẫu.
- **Median/p50:** khoảng 50% mẫu không vượt quá giá trị này.
- **p95:** khoảng 95% mẫu không vượt quá giá trị này.
- **p99:** khoảng 99% mẫu không vượt quá giá trị này.
- **Max:** mẫu lớn nhất trong tập đo.
- **Histogram:** phân phối số lượng mẫu theo các khoảng thời gian.
- **Error/timeout rate:** tỷ lệ thao tác thất bại hoặc không có response trong deadline.

Giả sử 1.000 lời gọi:

```text
990 lời gọi: khoảng 1 ms
 10 lời gọi: khoảng 200 ms
```

Mean gần 3 ms, nhìn khá thấp, nhưng 1% request bị trễ 200 ms. Trong hệ thống nhiều bước liên tiếp, một vài tail latencies có thể chi phối trải nghiệm người dùng và thời gian xử lý của cả endpoint.

**Không thay thế p99 bằng mean** khi đặt SLO cho API nhạy cảm với độ trễ.

### 3.1. Đọc percentile đúng cách

Nếu p99 latency của operation là 25 ms, cách diễn giải thông dụng là:

> Trong tập mẫu và khoảng thời gian được thống kê, xấp xỉ 99% operation có latency không vượt quá 25 ms.

Nó **không có nghĩa** mọi operation trong tương lai đều dưới 25 ms, cũng không nói request nhanh nhất hoặc chậm nhất là bao nhiêu.

Percentile của từng method cũng không thể cộng đơn giản:

```text
p99(GET) + p99(DB) != nhất thiết p99(HTTP)
```

vì các phân phối, tương quan thời gian và mức độ đồng thời khác nhau. Nếu cần p99 HTTP, hãy **đo HTTP**, không chỉ cộng các p99 thành phần.

### 3.2. Percentile phụ thuộc sample size và cửa sổ thời gian

Một test chỉ có 100 requests không đủ đại diện cho những hiện tượng hiếm như Redis failover, pause GC hoặc tail latency dưới tải lớn.

Cần ghi rõ:

```text
Khoảng đo:      15 phút
Requests:       1.200.000
Concurrency:    64
Payload:        theo phân phối production
Warm-up:        3 phút, không tính vào kết quả
Metric:         p50, p95, p99, max, error %
```

Các con số trên là ví dụ mô tả kết quả test; khi triển khai phải thay bằng số liệu đo thực tế.

### 3.3. Tail latency có thể xuất hiện do nhiều tầng

Các nguyên nhân thường gặp:

- Tranh chấp CPU trong JVM hoặc Redis.
- Garbage collection pause.
- Network jitter, TLS overhead hoặc packet retransmission.
- Queue phía client do concurrency vượt khả năng xử lý.
- Connection acquisition/pool wait.
- Redis slow command hoặc Lua script dài.
- Redis `fork`/persistence/resharding gây spike.
- Hot key/hot slot.
- Tăng số lệnh mỗi request do cache miss.
- Serialization JSON lớn.
- Thread pool hoặc event-loop bị block.
- Response payload lớn làm network/decoder mất nhiều thời gian.

Đừng chỉ tăng số Redis nodes trước khi xác định tầng gây p99.

## 4. Throughput: RPS không phải Redis ops/s

**Throughput** mô tả số lượng công việc hoàn thành trong một đơn vị thời gian. Nhưng “công việc” có nhiều đơn vị:

| Đơn vị | Ví dụ | Điều cần nêu rõ |
|---|---|---|
| HTTP requests/s (RPS) | 2.000 request/s | Endpoint nào? tỷ lệ lỗi? |
| Business operations/s | 1.000 checkout/s | Một checkout gồm các bước gì? |
| Redis commands/s | 8.000 commands/s | Tổng lệnh hay chỉ `GET`? |
| Redis Stream records/s | 5.000 `XADD` entry/s | Payload và consumer lag? |
| Messages/s | 20.000 Pub/Sub messages/s | Số subscriber và fan-out? |
| Bytes/s | 100 MiB/s nhận/gửi | Payload/wire overhead/TLS? |
| Keys/s | 50.000 new keys/s | TTL và memory growth? |

Ví dụ một HTTP request có:

```text
1 x GET session
1 x GET product
1 x HGETALL cart
1 x SET cache
```

Một business request tạo **4 Redis commands** trong kịch bản này.

Nếu hệ thống xử lý 2.000 RPS với mô hình đó:

```text
2.000 RPS x 4 Redis commands/request
    = 8.000 Redis commands/s
```

Trong thực tế, số command/request thay đổi theo cache hit/miss, batch size, retry và code path. Vì vậy cần lấy từ traces/metrics hoặc đo từng operation family.

### 4.1. Throughput luôn đi cùng latency và tỷ lệ lỗi

Một load test có thể báo:

```text
Throughput: 50.000 RPS
p99:        3.000 ms
Errors:     25%
```

Con số 50.000 chưa chứng minh hệ thống đáp ứng được 50.000 requests/s có ích. Nên yêu cầu đồng thời:

```text
Throughput >= target
p99 latency <= latency budget
Error rate <= threshold
No unbounded backlog
Stable resources
```

Khi vượt giới hạn, throughput hoàn thành có thể không tăng nữa trong khi latency và queue length tăng mạnh.

### 4.2. Concurrency và thời gian chờ

Một phép quan sát gần đúng theo Little's Law trong hệ thống ổn định:

\[
L = \lambda W
\]

Trong đó:

- \(L\): số công việc trung bình đang ở trong hệ thống.
- \(\lambda\): throughput hoàn thành trung bình, ví dụ requests/s.
- \(W\): thời gian lưu lại hệ thống trung bình, tính bằng giây.

Ví dụ throughput 1.000 requests/s và thời gian trong hệ thống trung bình 0,05 s:

```text
L ≈ 1.000 x 0,05 = 50 requests đang in-flight trung bình.
```

Công thức dùng để tư duy về concurrency/queueing, **không phải phép đo p99** và chỉ có ý nghĩa khi định nghĩa ranh giới hệ thống và điều kiện ổn định phù hợp.

### 4.3. Khi concurrency tăng quá mức

```text
Concurrency -> tăng
      |
      +--> Ban đầu throughput tăng
      |
      +--> Đạt giới hạn CPU/network/Redis
      |
      +--> Hàng đợi dài ra
      |
      +--> p95/p99 tăng
      |
      +--> Timeout/retry gây thêm tải
      |
      +--> Throughput hữu ích có thể giảm
```

Ngưỡng bắt đầu tăng latency mạnh được gọi không chính thức là **điểm gối (knee)** của đường cong tải. Mục tiêu capacity planning thường là hoạt động có headroom trước điểm ấy, không phải cố đạt đỉnh benchmark ngắn hạn.

## 5. Ba khái niệm về kích thước dữ liệu

Khi nói “key này nặng 1 KiB”, ít nhất phải phân biệt:

**(1) Kích thước dữ liệu logic:** số ký tự hoặc fields mà nghiệp vụ lưu.

**(2) Kích thước bytes khi serialize/truyền:** bytes của key, field/value, JSON/MessagePack/binary, RESP protocol và các phần mạng liên quan.

**(3) Redis memory usage:** bytes được Redis phân bổ để lưu key/value và các cấu trúc nội bộ ở RAM, cộng với overhead lớn hơn ở cấp instance.

Ví dụ:

```text
DTO Java:
    Product(id, name, price, attributes)

Serialize JSON:
    864 bytes UTF-8

Redis key:
    "product:123" = 11 bytes UTF-8

Redis MEMORY USAGE product:123:
    Có thể lớn hơn 864 + 11 bytes

Redis process RSS:
    Còn gồm allocator, overhead, fragmentation,
    connection buffers và các thành phần khác.
```

Không có hệ số chung áp dụng cho mọi key và mọi Redis version. `String`, `Hash`, `Set`, `Sorted Set`, `List`, `Stream`, TTL, giá trị lớn/nhỏ và cách encoding sẽ có overhead khác nhau.

### 5.1. Payload JSON 1 KiB không đồng nghĩa 1 KiB network

Một lệnh:

```redis
SET product:123 <json-1024-bytes> EX 600
```

trên đường truyền còn có:

- Tên command.
- Độ dài từng argument trong Redis Serialization Protocol (RESP).
- Key bytes.
- Timeout argument.
- Framing.
- TCP/IP và TLS overhead tùy hệ thống.

Khi đo network throughput, không được chỉ lấy `json.length()` rồi coi là tổng network bytes.

### 5.2. Payload 1 KiB không đồng nghĩa RAM Redis 1 KiB

Redis phải duy trì:

- Key name và value.
- Dictionary entry/metadata nội bộ.
- Object encoding và allocator overhead.
- Expiration metadata nếu key có TTL.
- Container metadata của Hash/List/Set/ZSet/Stream.
- Các field/key phụ do repository/index/cache tạo thêm.
- Instance overhead và memory fragmentation.

**Đo actual bytes trên Redis**, sau đó mới extrapolate từ mẫu đại diện.

## 6. Thiết lập hệ đo hiệu năng theo nhiều lớp

Một hệ thống Spring Boot có thể triển khai bốn nguồn thông tin:

```text
              Monitoring / Metrics

  HTTP request timing --------------------+
                                           |
  Spring service/custom Micrometer timers -+
                                           +--> Dashboard & correlation
  Lettuce/Redis client latency ------------+
                                           |
  Redis INFO/SLOWLOG/LATENCY/MEMORY --------+
```

Mỗi nguồn có tác dụng riêng:

| Nguồn | Điểm mạnh | Không cho biết đầy đủ |
|---|---|---|
| HTTP metrics | Trải nghiệm endpoint, p95/p99 thực | Redis chiếm bao nhiêu nếu không tách spans |
| Service metrics | Thời gian business method hoặc cache operation | Redis server có chậm thật không |
| Client command metrics | Round-trip, lỗi, remote node | Tổng HTTP và business correctness |
| Redis commandstats | Số lần và thời gian thực thi lệnh trên server | RTT, serialization, Java GC |
| Redis memory metrics | Dataset, overhead, RSS, eviction | Bytes từng payload ứng dụng nếu không đo thêm |
| Tracing | Một request đi qua các dependency nào | Thống kê throughput/capacity nếu chỉ sample ít trace |
| Load generator | RPS, latency nhìn từ bên ngoài | Nội bộ Redis/process nếu không có instrumentation |

Không nên chọn một con số từ `redis-benchmark` thay cho tất cả các nguồn trên.

### 6.1. Các thước đo cần thống nhất trước benchmark

Ví dụ một mục tiêu:

```text
Endpoint: GET /api/products/{id}
Workload: 90% cache hit, 10% cache miss
Dataset: 1 triệu products
Payload: p50 1 KiB, p99 12 KiB
Target:  3.000 RPS
SLO:     p99 server-side <= 50 ms
Errors:  < 0,1%
Redis:   không evict ngoài dự kiến
```

Toàn bộ số liệu là **ví dụ đề bài thử nghiệm**, không phải benchmark Redis đã đo. Mục tiêu cần xuất phát từ trải nghiệm người dùng và workload thực tế của dự án.

## 7. Micrometer và Spring Boot Actuator

Trong Spring Boot, **Micrometer** thường được dùng để ghi metrics, còn Actuator cung cấp các endpoint và tích hợp monitoring tùy dependency/config.

Dependency Maven minh họa:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
    <scope>runtime</scope>
</dependency>
```

Khi sử dụng Spring Boot dependency management, thông thường không cần khai báo phiên bản thủ công cho các artifact được quản lý.

Ví dụ `application.yml` cho môi trường quan sát có kiểm soát:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 3s

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
```

Cấu hình chính xác của metrics/observation có thể thay đổi theo Spring Boot version và loại exporter. Không suy rằng mọi Redis command timer đều tự xuất hiện chỉ vì đã thêm Actuator. Với Redis, có thể cần cấu hình driver instrumentation hoặc tự tạo timers ở service.

**Bảo mật:** các endpoint Actuator không nên mở công khai tùy tiện. Cần giới hạn network, authentication/authorization và loại bỏ tags chứa dữ liệu nhạy cảm.

### 7.1. Tìm metrics hiện có

Trong môi trường ứng dụng chạy, có thể thử:

```bash
curl http://localhost:8080/actuator/metrics
```

Để đọc một metric cụ thể:

```bash
curl http://localhost:8080/actuator/metrics/http.server.requests
```

Nếu đã cấu hình exporter Prometheus:

```bash
curl http://localhost:8080/actuator/prometheus
```

Tên metric chính xác và kiểu phân phối có thể khác do Spring version, instrumentation, exporter naming convention hoặc tag configuration. Hãy xác nhận từ endpoint thực tế, không tự giả định một metric tên `redis.latency` luôn được publish.

### 7.2. Sử dụng histogram thay vì tính average duy nhất

Để tổng hợp p95/p99 qua nhiều instance, histogram với buckets phù hợp thường hữu ích hơn việc lấy trung bình các percentile đã tính riêng trên từng instance.

Ví dụ không nên làm:

```text
Instance A p99 = 10 ms
Instance B p99 = 100 ms
=> global p99 = (10 + 100) / 2 = 55 ms
```

Đây không phải phép tính percentile đúng nếu traffic volumes/distributions khác nhau. Nên tổng hợp histogram raw buckets (nếu registry/monitoring hỗ trợ), hoặc lấy phân phối từ một nguồn có khả năng aggregate đúng.

## 8. Ví dụ đo Redis GET/SET tại service bằng Micrometer

Một mẫu đo đơn giản dùng `StringRedisTemplate` và `MeterRegistry`:

```java
package com.example.metrics;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class InstrumentedRedisGateway {

    private final StringRedisTemplate redis;
    private final MeterRegistry registry;

    public InstrumentedRedisGateway(
            StringRedisTemplate redis,
            MeterRegistry registry) {

        this.redis = redis;
        this.registry = registry;
    }

    public String get(String key) {
        long start = System.nanoTime();
        String outcome = "success";

        try {
            return redis.opsForValue().get(key);
        } catch (RuntimeException ex) {
            outcome = "error";
            throw ex;
        } finally {
            long elapsed = System.nanoTime() - start;

            Timer.builder("app.redis.operation.duration")
                .description("Spring Redis call latency")
                .tag("command", "GET")
                .tag("outcome", outcome)
                .publishPercentileHistogram()
                .register(registry)
                .record(elapsed, TimeUnit.NANOSECONDS);
        }
    }

    public void put(
            String key,
            String value,
            Duration ttl) {

        long start = System.nanoTime();
        String outcome = "success";

        try {
            redis.opsForValue().set(key, value, ttl);
        } catch (RuntimeException ex) {
            outcome = "error";
            throw ex;
        } finally {
            long elapsed = System.nanoTime() - start;

            Timer.builder("app.redis.operation.duration")
                .description("Spring Redis call latency")
                .tag("command", "SET")
                .tag("outcome", outcome)
                .publishPercentileHistogram()
                .register(registry)
                .record(elapsed, TimeUnit.NANOSECONDS);
        }
    }
}
```

Ở đây:

- `System.nanoTime()` phù hợp để đo **khoảng thời gian**, tránh lệ thuộc đồng hồ wall-clock.
- Timer được bắt đầu ngay trước lời gọi `StringRedisTemplate`.
- Thời gian bao gồm những gì xảy ra trong lời gọi này: Redis client, network, Redis và decode reply tùy API.
- Nó **không bao gồm** thời gian serialize DTO thành String nếu serialize xảy ra trước khi vào `put`.
- `null` từ `GET` thường là cache miss, nhưng ví dụ trên vẫn gắn `outcome=success` vì lệnh không ném exception.
- Nếu cần phân biệt hit/miss, thêm một **low-cardinality tag/counter riêng**, không gộp cache miss với Redis network error.

Đây là instrumentation cấp service, chưa phải phân tích toàn bộ thời gian HTTP request.

### 8.1. Không dùng key hoặc requestId làm metric tags

Sai:

```java
.tag("key", "product:" + productId)
.tag("requestId", requestId)
```

Nếu có một triệu product IDs, hệ monitoring có thể tạo một triệu series, gây cardinality explosion và tăng chi phí lưu metrics.

Tags nên có tập giá trị nhỏ:

```text
command: GET / SET / HGETALL / XADD
operation: product-read / session-load / cart-update
outcome: success / error / timeout
cache: product / cart / session
node_group: bounded label nếu thật sự cần
```

Không đưa payload, session token, Redis key đầy đủ hoặc URI chứa ID làm tags.

### 8.2. Tách hit/miss khỏi command latency

Với `GET`, có hai câu hỏi:

```text
Lệnh GET có hoàn thành không?
Dữ liệu có tồn tại không?
```

Một cache miss (`GET` trả `null`) thường vẫn là lệnh Redis hoàn thành thành công. Nếu đo hit rate, dùng counter riêng hoặc tag outcome có cardinality được kiểm soát:

```java
String value = redis.opsForValue().get(key);

registry.counter(
    "app.redis.cache.lookup",
    "cache", "product",
    "result", value == null ? "miss" : "hit"
).increment();
```

Đo hit/miss tại cache abstraction phù hợp nếu Spring Cache đã cung cấp instrumentation, tránh đếm trùng ở nhiều tầng.

## 9. Đo serialization riêng với Redis latency

Spring Data Redis thường cần serialize Java DTO trước khi Redis có thể lưu bytes. Nếu chỉ đo `redis.opsForValue().set(...)`, ta có thể bỏ sót chi phí tạo JSON từ DTO.

Ví dụ dùng Jackson:

```java
package com.example.metrics;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.time.Duration;

@Service
public class ProductCacheWriter {

    private final ObjectMapper objectMapper;
    private final StringRedisTemplate redis;
    private final Timer serializationTimer;
    private final Timer redisWriteTimer;
    private final DistributionSummary valueBytes;
    private final DistributionSummary keyBytes;

    public ProductCacheWriter(
            ObjectMapper objectMapper,
            StringRedisTemplate redis,
            MeterRegistry registry) {

        this.objectMapper = objectMapper;
        this.redis = redis;

        this.serializationTimer =
            Timer.builder("app.redis.serialization.duration")
                .tag("format", "json")
                .tag("operation", "product-write")
                .publishPercentileHistogram()
                .register(registry);

        this.redisWriteTimer =
            Timer.builder("app.redis.write.duration")
                .tag("operation", "product-write")
                .publishPercentileHistogram()
                .register(registry);

        this.valueBytes =
            DistributionSummary.builder("app.redis.value.bytes")
                .baseUnit("bytes")
                .tag("cache", "product")
                .register(registry);

        this.keyBytes =
            DistributionSummary.builder("app.redis.key.bytes")
                .baseUnit("bytes")
                .tag("cache", "product")
                .register(registry);
    }

    public void write(String productId, ProductDto dto)
            throws JsonProcessingException {

        String key = "product:" + productId;

        String json = serializationTimer.recordCallable(
            () -> objectMapper.writeValueAsString(dto)
        );

        byte[] payload = json.getBytes(StandardCharsets.UTF_8);
        byte[] keyPayload = key.getBytes(StandardCharsets.UTF_8);

        valueBytes.record(payload.length);
        keyBytes.record(keyPayload.length);

        redisWriteTimer.record(() ->
            redis.opsForValue()
                .set(key, json, Duration.ofMinutes(10))
        );
    }

    public record ProductDto(
        String id,
        String name,
        long priceInCents
    ) {}
}
```

Tùy Micrometer API phiên bản, helper `recordCallable(...)` có checked-exception contract khác nhau; nếu cần giữ nguyên `JsonProcessingException`, có thể đo thủ công bằng `System.nanoTime()` trong `try/finally`. Ví dụ minh họa ý đồ **đo serialization tách khỏi Redis I/O**.

Ở đây:

- `json.getBytes(UTF_8).length` phản ánh số bytes của String JSON mà ta định gửi.
- `key.getBytes(UTF_8).length` phản ánh số bytes tên key khi dùng String serialization tương ứng.
- `valueBytes.record` đo payload ứng dụng, **không phải `MEMORY USAGE` của Redis**.
- `redisWriteTimer` đo lời gọi ghi Redis với String đã serialize sẵn.
- Nếu đổi sang binary serializer, nên đo **bytes thực tế do serializer đó tạo**, không dùng độ dài String JSON giả định.
- Nếu object được compress, đo cả bytes trước và sau nén cùng chi phí CPU.

### 9.1. Tránh double-count khi tạo metrics

Nếu thư viện Lettuce đã publish command latency và gateway cũng publish timer, đây là **hai phép đo khác phạm vi**, không phải hai lệnh Redis. Dashboard cần đặt tên rõ, ví dụ `app.redis.write.duration` và `lettuce.command.latency`, thay vì cộng số lần được đếm từ hai timers như throughput.

### 9.2. Kích thước key cũng quan trọng

Key như:

```text
p:42
```

ngắn hơn:

```text
production:tenant-7:catalog:product:42:version:2026
```

Nếu có hàng triệu key, overhead của tên key dài có thể đáng kể. Tuy vậy, đổi tên key để tiết kiệm vài bytes phải cân nhắc debugging, namespace, multi-tenant safety và Redis Cluster hash tags.

**Không đặt tên key quá ngắn khiến xung đột hoặc không kiểm soát được định danh nghiệp vụ.** Đo chênh lệch thực tế rồi tối ưu có chủ đích.

## 10. ReactiveRedisTemplate: đo theo subscription, không theo lúc tạo Mono

Trong WebFlux, lời gọi reactive thường tạo Publisher lazy:

```java
Mono<String> value = reactiveRedisTemplate
    .opsForValue()
    .get("product:42");
```

Nếu bắt đầu timer **lúc tạo `Mono`** nhưng rất lâu sau mới subscribe, kết quả sẽ bao gồm thời gian chờ không liên quan command. Ngược lại, nếu không có subscriber, lệnh có thể chưa chạy.

Nên đo từ lúc subscription/attempt bắt đầu:

```java
package com.example.metrics;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ReactiveProductReader {

    private final ReactiveStringRedisTemplate redis;
    private final Timer timer;

    public ReactiveProductReader(
            ReactiveStringRedisTemplate redis,
            MeterRegistry registry) {

        this.redis = redis;

        this.timer = Timer.builder("app.redis.reactive.get.duration")
            .tag("cache", "product")
            .publishPercentileHistogram()
            .register(registry);
    }

    public Mono<String> get(String key) {
        return Mono.defer(() -> {
            long start = System.nanoTime();

            return redis.opsForValue()
                .get(key)
                .doFinally(signal -> {
                    long elapsed = System.nanoTime() - start;
                    timer.record(elapsed, TimeUnit.NANOSECONDS);
                });
        });
    }
}
```

`Mono.defer` giúp mỗi subscription tạo một mốc bắt đầu riêng. `doFinally` chạy khi Publisher kết thúc, lỗi hoặc bị cancel.

**Lưu ý về phạm vi:** timer trên ghi cả các subscription bị hủy; nếu muốn phân biệt cancellation/timeout/success, cần thêm counter/tags `signal` có cardinality thấp. Nếu có `retryWhen` bên ngoài phương thức, mỗi subscription attempt có thể được đo riêng; nếu retry nằm bên trong source được đo, timer có thể bao gồm nhiều attempts. Phải thống nhất định nghĩa metric trước khi so sánh.

### 10.1. Không block event-loop để benchmark

Tránh:

```java
String value = reactiveRedisTemplate
    .opsForValue()
    .get(key)
    .block();
```

trong WebFlux request handler để “đo cho dễ”. `.block()` có thể chặn thread và làm sai cả hiệu năng lẫn concurrency model.

Nên để WebFlux subscribe Publisher và đo bằng Micrometer, tracing hoặc load generator bên ngoài. Nếu làm integration test đồng bộ từ một test thread, `block()` có thể dùng có kiểm soát, nhưng không dùng kết quả đó làm benchmark đại diện cho ứng dụng WebFlux production.

### 10.2. Backpressure không đồng nghĩa Redis không có bottleneck

Reactor có thể điều tiết tốc độ tiêu thụ downstream, nhưng:

- Redis commands đã gửi vẫn tiêu tốn network và server capacity.
- Queue của client có thể tăng.
- Pipelining/concurrency cao có thể tăng thời gian chờ.
- SSE/Pub/Sub có đặc tính fan-out riêng.
- Một luồng Redis Streams có thể có backlog/PEL chưa ACK.

Đo throughput/latency cùng lượng công việc in-flight và backlog, không chỉ nhìn CPU Java.

## 11. Lettuce command latency và observation

**Lettuce** là driver phổ biến của Spring Data Redis, hỗ trợ quản lý connection, command execution, async/reactive APIs và thu thập command latency trong những cấu hình phù hợp.

Các thành phần quan sát khả dụng phụ thuộc:

- Lettuce version.
- Spring Boot/Spring Data Redis version.
- Client resources và cấu hình command latency collector.
- Micrometer/Tracing bridge có được cấu hình không.
- Loại lệnh, connection, Redis Cluster và topology.
- Metrics registry/exporter.

Một số triển khai dùng command latency collector của Lettuce, hoặc tích hợp Micrometer/Observation của Spring Boot ở các phiên bản hỗ trợ. **Không mặc định mọi dự án đều đã bật sẵn hoặc xuất cùng một metric name.**

### 11.1. Client latency cho biết gì?

Lettuce command latency thường có thể giúp nhìn:

```text
GET latency
SET latency
MGET latency
EVAL latency
XREADGROUP latency
...
```

theo các nhóm remote endpoint/command tùy khả năng cấu hình. Nó phản ánh thời gian ở phía client/driver hoặc các phase command mà collector ghi nhận, khác `cmdstat_get` của Redis server.

Một Redis server xử lý `GET` nhanh vẫn có thể xuất hiện client p99 cao do network hoặc event-loop client.

### 11.2. Đừng bật mọi metric tag không giới hạn

Một command latency metric nên có command type và các chiều label hữu hạn. Không nên gắn key name hay requestId vào mọi metric.

Khi dùng Redis Cluster, remote address/node label có thể tăng khi topology đổi; cần kiểm soát cardinality và tránh scrape dữ liệu quá chi tiết không hữu ích.

### 11.3. Metrics từ Redis client là dữ liệu quan sát, không phải SLA tự động

Tốc độ lấy mẫu, aggregation interval, histogram/percentiles và export delay ảnh hưởng số liệu. Nếu một metric báo p99 của 1 phút và HTTP metric báo p99 của 5 phút, không được so sánh như hai giá trị cùng cửa sổ.

Đối với latency regression, đồng nhất khoảng đo, workload, instance, routing và percentile method.

## 12. Redis INFO: xem throughput từ phía server

Redis cung cấp lệnh:

```redis
INFO
```

và các phần thông tin:

```redis
INFO stats
INFO commandstats
INFO memory
INFO clients
INFO cpu
INFO persistence
INFO keyspace
```

Một vài trường phổ biến:

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| `stats` | `total_commands_processed` | Tổng commands server đã xử lý từ lúc bắt đầu số đếm |
| `stats` | `instantaneous_ops_per_sec` | Ước lượng tốc độ commands gần thời điểm quan sát |
| `stats` | `total_net_input_bytes` | Bytes input mạng được Redis ghi nhận |
| `stats` | `total_net_output_bytes` | Bytes output mạng được Redis ghi nhận |
| `stats` | `keyspace_hits` | Số lookup hit được Redis ghi nhận |
| `stats` | `keyspace_misses` | Số lookup miss được Redis ghi nhận |
| `stats` | `evicted_keys` | Số key bị eviction |
| `stats` | `expired_keys` | Số key đã bị expiration xử lý |
| `clients` | `connected_clients` | Số kết nối client đang hoạt động |
| `memory` | `used_memory` | Bộ nhớ Redis dùng theo thống kê allocator |
| `memory` | `used_memory_rss` | Resident memory từ hệ điều hành |
| `cpu` | CPU time metrics | Mức sử dụng CPU theo loại thời gian |
| `commandstats` | `cmdstat_get`, `cmdstat_set`... | Count/time theo command |
| `persistence` | `rdb_bgsave_in_progress`... | Tình trạng snapshot/persistence |

Trường cụ thể có thể khác theo Redis version, nền tảng và managed service. Hãy dựa trên output thực của instance.

### 12.1. Tính throughput bằng chênh lệch counter

Giả sử:

```text
t0: total_commands_processed = 5.000.000
t1: total_commands_processed = 5.060.000
t1 - t0 = 10 giây
```

Tốc độ xấp xỉ:

```text
(5.060.000 - 5.000.000) / 10
    = 6.000 commands/s
```

Lưu ý:

- Counter có thể reset khi Redis restart.
- Tốc độ này gồm nhiều command types, kể cả command quản trị/monitoring và workload khác.
- Redis Cluster có nhiều node; cần phân biệt per-node rate và tổng hợp đúng.
- Một pipeline có thể chứa nhiều Redis commands trong một network round-trip.
- `commands/s` không bằng số HTTP requests/s.

### 12.2. `instantaneous_ops_per_sec` có giới hạn gì?

Đây là chỉ số tốc độ gần thời điểm quan sát, hữu ích cho dashboard. Nhưng nó không cho thấy đầy đủ:

- Workload đã dao động thế nào trong vài phút qua.
- Độ trễ p99.
- Bao nhiêu business operations đã thành công.
- Có bao nhiêu retries.
- Command nào chiếm phần lớn CPU.

Nên kết hợp với chênh lệch counters và throughput app, không dùng một mẫu instantaneous duy nhất để capacity planning.

## 13. INFO commandstats: command nào tốn thời gian server?

Ví dụ:

```redis
INFO commandstats
```

Output có thể chứa dòng tương tự:

```text
cmdstat_get:calls=100000,usec=550000,usec_per_call=5.50
cmdstat_hgetall:calls=12000,usec=240000,usec_per_call=20.00
cmdstat_eval:calls=5000,usec=750000,usec_per_call=150.00
```

Các giá trị ở trên **chỉ là minh họa**.

- `calls`: số lần command được thống kê.
- `usec`: tổng microseconds thực thi các command ở Redis server theo cách Redis đo.
- `usec_per_call`: thời gian trung bình thực thi một command type tại server.

Nếu `EVAL` có `usec_per_call` cao, có thể cần kiểm tra Lua script, kích thước dữ liệu hoặc truy cập nhiều phần tử. Nếu `HGETALL` ngày càng đắt, có thể Hash phình lớn và ứng dụng đang lấy toàn bộ fields không cần thiết.

### 13.1. Vì sao không thể lấy usec_per_call làm p99?

`usec_per_call` là **average server execution time**, không phải phân phối latency. Nó không thể cho biết 1% request chậm nhất.

Bảng:

```text
cmdstat_get usec_per_call = 5.5 µs
```

không chứng minh:

```text
p99 client GET <= 5.5 µs
```

Client còn network, Redis queue, serialization và response handling; server mean cũng không phải server p99.

### 13.2. Đếm command mix

Chụp số `calls` của từng `cmdstat_*` trước và sau một load test có thời gian cố định, rồi tính số lần gọi mỗi loại.

Ví dụ:

```text
GET       700.000
SET       100.000
HGETALL   120.000
EVAL       20.000
```

Tổng mix này giúp so sánh kết quả test với workload mong muốn. Nếu kịch bản dự kiến 90% read nhưng đo ra 30% write, có thể cache miss hoặc một thành phần khác đang ghi nhiều hơn kỳ vọng.

Không nên reset toàn bộ counters ở production chỉ để benchmark nếu điều đó làm gián đoạn hệ monitoring. Lấy **delta giữa hai mẫu** thường đủ.

## 14. SLOWLOG: tìm các lệnh thực thi chậm trên Redis server

Redis cung cấp slow log:

```redis
SLOWLOG LEN
SLOWLOG GET 10
```

Ngưỡng ghi slow log có thể được cấu hình:

```redis
CONFIG GET slowlog-log-slower-than
```

`slowlog-log-slower-than` thường tính bằng **microseconds**. Ví dụ ngưỡng 10.000 µs tương đương 10 ms về execution time, khi cấu hình ấy được áp dụng.

**Quan trọng:** Slow log chủ yếu ghi thời gian **thực thi command tại Redis**, không bao gồm thời gian client chờ network hay response đến Java.

Nếu Spring báo `GET` 80 ms nhưng `SLOWLOG` không thấy `GET` nào, có thể độ trễ nằm ở:

- Network RTT.
- Connection acquisition.
- Client command queue.
- Event-loop/CPU/GC Java.
- Response lớn/deserialize.
- Traffic tới node khác.
- Server-side wait/queue không nằm trong phần execution time được slowlog ghi.
- Ngưỡng slowlog quá cao hoặc log đã bị xoay/giới hạn.

### 14.1. Có nên đặt ngưỡng slowlog rất thấp?

Đặt ngưỡng quá thấp trên server có lưu lượng lớn có thể tăng overhead và số log entries. Việc thay `CONFIG SET slowlog-log-slower-than ...` cần theo chính sách vận hành và chỉ thực hiện trên môi trường được phép.

Không bật một cấu hình chẩn đoán rất chi tiết rồi quên tắt trên production.

### 14.2. `MONITOR` không phải công cụ benchmark thường trực

Lệnh:

```redis
MONITOR
```

có thể giúp quan sát lệnh đang đi qua Redis trong một phiên chẩn đoán, nhưng tạo overhead, tăng network và có nguy cơ lộ key/payload nhạy cảm.

**Tránh chạy `MONITOR` thường trực trên Redis production**, nhất là hệ thống có nhiều commands/s. Để biết command mix, `INFO commandstats` và tracing có kiểm soát thường phù hợp hơn.

## 15. Redis LATENCY monitoring: quan sát spikes

Redis có các lệnh thuộc hệ thống latency monitoring:

```redis
LATENCY LATEST
LATENCY HISTORY <event>
LATENCY DOCTOR
```

Ví dụ:

```redis
LATENCY LATEST
LATENCY DOCTOR
```

Các event được ghi nhận phụ thuộc cơ chế monitor, ngưỡng cấu hình và Redis version. Có thể xem:

```redis
CONFIG GET latency-monitor-threshold
```

Nếu latency monitor chưa bật/ngưỡng không phù hợp, việc không thấy event **không chứng minh server không có spike**.

### 15.1. Phân biệt LATENCY và SLOWLOG

| Công cụ | Quan sát chính |
|---|---|
| `INFO commandstats` | Tổng count và mean execution time theo command |
| `SLOWLOG` | Những commands có execution time vượt ngưỡng |
| `LATENCY` | Một số loại latency spikes/events nội bộ Redis khi monitoring phù hợp |
| Client timers | Round-trip từ phía Java client |
| HTTP metrics | Độ trễ của endpoint thực |
| Tracing | Đường đi/những spans trong một request |

Nên kết hợp, không thay một công cụ bằng công cụ khác.

### 15.2. Host-level intrinsic latency

`redis-cli` có chế độ đo intrinsic latency của host trong những môi trường phù hợp. Phép đo này cho biết jitter/scheduling nền của máy, không phải throughput HTTP của Spring Boot.

Việc chạy phép thử host-level có thể tiêu tốn CPU và cần quyền truy cập máy Redis. Chỉ dùng trong môi trường thử nghiệm hoặc theo runbook vận hành, không chạy tùy tiện trên production đang phục vụ traffic cao.

## 16. Đo kích thước key thật bằng MEMORY USAGE

Lệnh quan trọng:

```redis
MEMORY USAGE product:123
```

Redis trả số bytes bộ nhớ mà Redis tính cho key/value được chỉ định theo cơ chế memory accounting của nó.

Có thể thử:

```redis
SET lab:tiny a
MEMORY USAGE lab:tiny

SET lab:larger "A longer text value used for memory measurement"
MEMORY USAGE lab:larger
```

Không nên suy rằng memory usage sẽ tăng đúng bằng chênh lệch byte String. Redis có allocator size classes, object encoding và metadata.

### 16.1. Với nested data structures

Ví dụ:

```redis
HSET lab:profile name Alice city HCMC status ACTIVE
MEMORY USAGE lab:profile
```

Đối với một số cấu trúc có nhiều phần tử, `MEMORY USAGE` hỗ trợ tùy chọn:

```redis
MEMORY USAGE lab:profile SAMPLES 0
```

`SAMPLES 0` yêu cầu duyệt/ước lượng dựa trên tất cả phần tử lồng nhau theo ngữ nghĩa lệnh, có thể làm việc đo **tốn CPU hơn** với key rất lớn. Không quét hàng loạt key lớn trong giờ cao điểm mà không kiểm soát tác động.

Không phải mọi Redis data type/encoding đều có công thức overhead giống nhau. Cần đo các key đại diện.

### 16.2. Nếu key không tồn tại

`MEMORY USAGE missing:key` không cung cấp số bytes cho một key không tồn tại. Khi làm sampling, cần phân biệt:

```text
Key không tồn tại
Key có value rỗng nhưng vẫn tồn tại
Key có TTL và vừa hết hạn
Key bị eviction trong lúc đo
```

Không biến key missing thành mẫu `0 bytes` rồi tính average cho dữ liệu đang tồn tại, vì như vậy có thể làm sai phân phối.

### 16.3. `MEMORY USAGE` không phản ánh toàn bộ process RSS

Lệnh trả memory cho một key theo cách Redis tính. Tổng `MEMORY USAGE` của một nhóm key không nhất thiết bằng:

```redis
INFO memory -> used_memory_rss
```

vì RSS còn bao gồm overhead và fragmentation của allocator, memory chưa trả lại OS, memory buffers, persistence/COW và những thành phần ngoài dataset.

Khi capacity planning, cần kết hợp **per-key sample** với **instance-level memory metrics**.

## 17. Các lệnh đếm kích thước logic của dữ liệu Redis

Một số lệnh hỗ trợ biết độ lớn logic:

| Data type | Lệnh | Kết quả |
|---|---|---|
| String | `STRLEN key` | Số bytes của String value |
| Hash | `HLEN key` | Số field |
| List | `LLEN key` | Số phần tử |
| Set | `SCARD key` | Số member |
| Sorted Set | `ZCARD key` | Số member |
| Stream | `XLEN key` | Số entry hiện có trong Stream |
| Key chung | `TYPE key` | Data type |
| Key expiration | `TTL`/`PTTL` | Thời gian còn lại hoặc mã đặc biệt |

Ví dụ:

```redis
SET lab:json "{\"name\":\"Alice\",\"city\":\"HCMC\"}"
STRLEN lab:json
MEMORY USAGE lab:json
```

`STRLEN` không cho biết key overhead, expiration metadata hoặc process memory.

Với Hash:

```redis
HSET lab:hash name Alice city HCMC
HLEN lab:hash
MEMORY USAGE lab:hash
```

`HLEN` là số field, **không phải bytes**. Hash chứa 2 field giá trị 10 byte khác rất xa Hash chứa 2 field giá trị 1 MiB.

### 17.1. Một Stream có nhiều metadata hơn entry payload

Stream với consumer group có thể có:

```text
Stream entries
Consumer groups
Last-delivered IDs
Pending Entries List
Consumer metadata
```

`XLEN` đo số entry còn trong Stream; nó không phải tổng bytes RAM hoặc số pending messages.

Để hiểu Stream workloads, cần xem:

```redis
XLEN orders:events
XINFO STREAM orders:events
XINFO GROUPS orders:events
XPENDING orders:events workers
MEMORY USAGE orders:events
```

Với group lớn/PEL nhiều, việc chỉ lấy `average payload bytes * XLEN` có thể đánh giá thiếu memory thực tế.

## 18. Redis memory metrics ở cấp instance

Chạy:

```redis
INFO memory
MEMORY STATS
```

Một số trường quan trọng:

| Chỉ số | Ý nghĩa khái niệm |
|---|---|
| `used_memory` | Bytes Redis allocator đã phân bổ cho các mục đích được thống kê |
| `used_memory_human` | Biểu diễn dễ đọc của used memory |
| `used_memory_rss` | Resident Set Size mà OS báo cho process |
| `used_memory_peak` | Mức used memory cao nhất được ghi nhận |
| `used_memory_dataset` | Phần ước tính dành cho dataset |
| `used_memory_overhead` | Overhead do Redis thống kê |
| `mem_fragmentation_ratio` | Tỷ lệ fragmentation theo cách Redis tính |
| `maxmemory` | Giới hạn Redis memory policy nếu được cấu hình |
| `mem_not_counted_for_evict` | Một số memory không tính vào quyết định eviction |
| `allocator_*` metrics | Thông tin allocator nếu Redis version hỗ trợ |

Tên chỉ số/định nghĩa có thể khác theo phiên bản và triển khai.

### 18.1. used_memory khác RSS

```text
used_memory = 5 GiB
RSS         = 7 GiB
```

Điều này không tự có nghĩa có 2 GiB “data bị rò rỉ”. Chênh lệch có thể liên quan fragmentation, allocator behavior, memory overhead hoặc các thành phần hệ thống khác.

Cần nhìn thêm allocator metrics, workload thay đổi, mức peak trước đó và memory usage theo thời gian.

### 18.2. Memory fragmentation

Allocator cấp phát theo những kích thước có quy luật, làm dữ liệu thay đổi liên tục có thể khiến phân mảnh. Sau khi xóa một lượng lớn keys, process RSS có thể chưa giảm tương ứng.

Nếu `MEMORY USAGE` trên nhiều key thấp nhưng RSS vẫn cao, cần phân tích fragmentation/allocator, không chỉ thử rút ngắn JSON.

### 18.3. Copy-on-write và persistence

Khi Redis thực hiện `BGSAVE`/AOF rewrite, copy-on-write có thể làm tăng memory usage của hệ thống. Đây là phần headroom quan trọng nếu workload vừa ghi nhiều vừa snapshot.

**Không cấp phát production Redis sát 100% RAM của node chỉ từ tổng `MEMORY USAGE` sample**, vì còn buffers, fragmentation, COW, OS và vận hành khác.

## 19. Redis memory theo loại dữ liệu: không có hệ số chung

Xét ba cách lưu cùng dữ liệu:

**Phương án A — một JSON String:**

```redis
SET user:42 "{\"name\":\"Alice\",\"city\":\"HCMC\",\"tier\":\"GOLD\"}"
```

**Phương án B — Redis Hash:**

```redis
HSET user:42 name Alice city HCMC tier GOLD
```

**Phương án C — nhiều String keys:**

```redis
SET user:42:name Alice
SET user:42:city HCMC
SET user:42:tier GOLD
```

Tất cả có thể đáp ứng yêu cầu đọc/ghi nào đó, nhưng memory usage khác nhau:

- JSON có field names trong payload và chi phí parse/serialize.
- Hash lưu field/value trong cấu trúc Redis và có những encoding tối ưu với dữ liệu nhỏ tùy Redis version.
- Nhiều keys có thêm key dictionary metadata, tên key và expiration/index overhead trên từng key.
- Những thay đổi field có thể cần viết lại toàn bộ JSON String nếu dùng phương án A.
- Một Hash có TTL key-level theo API TTL thông thường; nhiều keys có TTL độc lập.
- JSON String có thể nén tốt tùy payload, nhưng thêm CPU và ảnh hưởng truy cập field.

**Không có kết luận “Hash luôn ít RAM hơn JSON” trong mọi trường hợp.** Đo các phương án với cùng dataset, cùng Redis version và yêu cầu thao tác tương đương.

### 19.1. OBJECT ENCODING

Redis có thể cung cấp:

```redis
OBJECT ENCODING user:42
```

để xem kiểu encoding nội bộ của key.

Encoding có thể thay đổi theo số phần tử/kích thước giá trị và Redis version. Nó giúp giải thích vì sao tăng số field từ vài chục lên vài trăm làm memory/latency biến đổi đột ngột.

Không nên code ứng dụng phụ thuộc trực tiếp vào một encoding nội bộ cụ thể như hợp đồng ổn định xuyên Redis versions.

### 19.2. Chọn data type theo access pattern, không chỉ RAM

Nếu API thường cần toàn bộ object, JSON String có thể đơn giản. Nếu API chủ yếu cập nhật một field, Hash có thể phù hợp hơn. Nếu cần membership, Set là cấu trúc có ngữ nghĩa tương ứng.

Một benchmark chỉ so memory nhưng bỏ qua CPU, number of commands, serialization và p99 latency là chưa đủ để chọn data type.

## 20. Đo kích thước dữ liệu với một mẫu đại diện

Một tập dữ liệu thật có thể có phân phối:

```text
80% product JSON:     0,5-2 KiB
15% product JSON:     2-8 KiB
 5% product JSON:     8-64 KiB
```

Nếu chỉ đo một product nhỏ nhất, công thức dự trù RAM sẽ sai. Nên lấy mẫu có chủ đích:

- Key ngắn và key dài.
- Payload nhỏ, trung bình, lớn.
- Hash ít fields và Hash nhiều fields.
- List/Set/ZSet có cardinality khác nhau.
- Keys có TTL và không TTL.
- Repository entities có index và shadow copies.
- Streams có group/PEL.
- Key nóng và key ít dùng.
- Tenant lớn và tenant nhỏ.

### 20.1. Thống kê theo bucket

Ví dụ mẫu 10.000 Redis keys:

| Nhóm | Số key mẫu | Payload p50 | Payload p99 | Redis memory/key p50 | Redis memory/key p99 |
|---|---:|---:|---:|---:|---:|
| Product cache | 4.000 | Đo thực tế | Đo thực tế | `MEMORY USAGE` | `MEMORY USAGE` |
| Session | 2.000 | Đo thực tế | Đo thực tế | `MEMORY USAGE` | `MEMORY USAGE` |
| Cart | 2.000 | Đo thực tế | Đo thực tế | `MEMORY USAGE` | `MEMORY USAGE` |
| Indexes | 1.000 | Đo thực tế | Đo thực tế | `MEMORY USAGE` | `MEMORY USAGE` |
| Streams | 1.000 | Đo thực tế | Đo thực tế | `MEMORY USAGE` | `MEMORY USAGE` |

Bảng là **mẫu biểu để điền số đo**, không cung cấp benchmark giả định.

### 20.2. Trung bình có trọng số

Giả sử có các nhóm key loại A, B, C, với số lượng tương ứng \(N_A,N_B,N_C\), memory/key trung bình \(m_A,m_B,m_C\). Ước tính memory cho dataset:

\[
M_{\text{dataset}} \approx N_A m_A + N_B m_B + N_C m_C
\]

Cần cộng thêm:

- Overhead instance không quy được hoàn toàn cho từng key.
- Memory fragmentation.
- Connection buffers.
- Replication/persistence buffers.
- Dự trù COW.
- Headroom cho traffic burst, data growth, failover.
- Redis Cluster slot/key distribution và từng primary.

Nếu lấy mẫu không ngẫu nhiên hoặc không đại diện, ngay cả công thức đúng cũng cho số sai.

### 20.3. Ví dụ tính toán capacity

Giả sử một workload dự kiến:

```text
1.000.000 keys
Measured average MEMORY USAGE = 1.200 bytes/key
```

Ước lượng dataset theo số đo mẫu:

```text
1.000.000 x 1.200 bytes = 1.200.000.000 bytes
```

Khoảng 1,2 GB theo hệ thập phân, **chưa cộng overhead cấp process, fragmentation và headroom**.

Không nên lấy kết quả này rồi chọn node RAM đúng 1,2 GB. Cần đo `used_memory`, RSS và peak dưới load, đồng thời dự trù tăng trưởng và failover.

## 21. Đo nhiều key mà không làm Redis production quá tải

Một cách đơn giản để tìm mẫu:

```redis
SCAN 0 MATCH product:* COUNT 100
```

Redis trả **cursor mới** và một danh sách keys. Tiếp tục dùng cursor tới khi về `0` để hoàn thành một lượt scan.

Ví dụ minh họa:

```redis
SCAN 0 MATCH product:* COUNT 100
SCAN <cursor-tra-ve> MATCH product:* COUNT 100
```

`COUNT` là gợi ý lượng công việc/mẫu được trả về, **không phải cam kết đúng 100 keys**. `SCAN` có thể trả kết quả lặp và dữ liệu thay đổi trong quá trình scan; khi tính thống kê phải hiểu hạn chế đó.

### 21.1. Không dùng KEYS * để quét production lớn

Tránh:

```redis
KEYS *
```

trên một keyspace lớn đang phục vụ traffic, vì lệnh có thể quét nhiều dữ liệu trong một command và gây ảnh hưởng latency.

Dùng `SCAN` với batch/cadence được giới hạn, hoặc đo từ dataset test đã được copy/anonymize.

### 21.2. Cluster có nhiều node

Trên Redis Cluster, việc scan keyspace và đo memory có thể cần duyệt các primary theo phạm vi được phân phối. Một kết quả từ một node không phải toàn bộ cluster.

Nên thống kê:

```text
Per primary:
  number of keys
  used_memory
  used_memory_rss
  ops/s
  command distribution
  latency
  top key/payload distributions
```

Sau đó mới tổng hợp theo cluster, đồng thời quan sát **max primary load** vì một primary quá tải có thể khiến những slot nó sở hữu có p99 cao dù tổng CPU cluster còn dư.

### 21.3. Lấy mẫu MEMORY USAGE có chi phí

Trên key rất lớn, nhất là nested structures, `MEMORY USAGE ... SAMPLES 0` có thể tốn thời gian. Có thể:

- Bắt đầu bằng sampling mặc định.
- Giới hạn số keys/ngày/phút.
- Chạy ở môi trường staging với dữ liệu representative.
- Ưu tiên tìm top categories/size buckets.
- Chỉ đo chi tiết một số outliers.
- Không quét toàn bộ node đúng giờ cao điểm.

Bài toán capacity cần dữ liệu đủ đại diện, **không nhất thiết phải lấy `MEMORY USAGE` chính xác nhất của mọi key mỗi giây**.

## 22. Redis Cache hit rate và cách diễn giải

Spring Cache với Redis thường có hai nhánh:

```text
Request product:42
       |
       v
Redis GET
   |
   +-- Hit  -> trả cache value
   |
   +-- Miss -> gọi database/service gốc
                |
                v
              SET Redis
```

Hit rate ở mức ứng dụng:

\[
\text{Hit rate} =
\frac{\text{cache hits}}
{\text{cache hits} + \text{cache misses}}
\]

Một cache có hit rate cao thường giảm tải source-of-truth, nhưng phải đánh giá cả:

- Hit latency.
- Miss latency.
- Độ trễ của database.
- Số lần `SET` cache.
- TTL/evictions.
- Payload sizes.
- Invalidations.
- Stale data risk.

### 22.1. `keyspace_hits` có phải ứng dụng cache hit không?

Trong `INFO stats`:

```redis
keyspace_hits
keyspace_misses
```

phản ánh lookup hits/misses theo cách Redis thống kê các thao tác tra key. Chúng có thể bao gồm các Redis commands từ nhiều ứng dụng và loại key.

Do đó:

```text
Redis global hit ratio != nhất thiết Spring Cache hit ratio
```

Nếu một instance Redis dùng chung cho sessions, counters, cart và cache, cần metric cache hit/miss ở tầng Spring Cache hoặc service để đánh giá riêng `products`.

### 22.2. Hit rate không nói hết chi phí

Một cache hit 99% nhưng giá trị mỗi hit 500 KiB có thể tốn network/deserialize rất lớn. Một cache hit 80% với payload 100 byte và database cực nhanh có thể đủ tốt.

Đo cùng lúc:

```text
Hit rate
Hit p95/p99
Miss p95/p99
Payload bytes
Redis memory/key
Database queries/s
HTTP latency
```

Không đặt mục tiêu “hit rate phải 100%” khi tăng TTL có thể làm dữ liệu stale vượt mức chấp nhận.

### 22.3. Spring Cache abstraction có overhead

Một lời gọi `@Cacheable` có thể còn đi qua:

- Proxy/interceptor.
- Cache key generation.
- Redis key prefix.
- Value serializer.
- Cache null handling.
- Cache configuration TTL.
- Database load nếu miss.

Nếu benchmark trực tiếp `GET product:42` nhanh hơn endpoint `@Cacheable`, điều đó bình thường. Cần đo cả ứng dụng thay vì quy mọi chênh lệch cho Redis server.

## 23. Spring Data Redis Repository và index có thể tăng memory đáng kể

Redis Repository có thể duy trì:

```text
Entity Hash
Secondary index Sets
Index bookkeeping metadata
TTL metadata
Shadow/phantom copies khi được bật
```

Ví dụ một entity có ba indexed fields có thể tạo nhiều Redis keys và thành viên Set phụ, không chỉ một Hash chính.

Vì thế, khi tính RAM:

```text
Entity JSON/Hash size
    + secondary indexes
    + metadata
    + expiration/shadow copies
```

Có thể hơn rất nhiều so với số bytes một DTO.

### 23.1. Đo đúng “đơn vị lưu”

Nếu một business entity tạo bốn Redis keys, không nên chỉ lấy:

```redis
MEMORY USAGE entity:42
```

rồi nhân với số entity. Cần xác định tất cả key families liên quan đến entity và index structures.

Tương tự, xóa một entity có thể thay đổi nhiều keys. Memory reduction không nhất thiết thể hiện ngay trong RSS do allocator fragmentation.

### 23.2. Dùng database query hay Redis index?

Secondary indexes giúp query một số thuộc tính trong Redis, nhưng thêm:

- Memory.
- Write amplification.
- Chi phí update index.
- Rủi ro cleanup khi TTL/notifications.
- Các giới hạn Redis Cluster nếu index truy cập nhiều key khác slot.

Một truy vấn hiếm, có thể giải quyết tốt ở database nguồn, không nhất thiết đáng để tạo thêm nhiều Redis indexes. Quyết định phải dựa trên **read latency + write cost + RAM + correctness**, không chỉ tốc độ `findBy...` trong một microbenchmark.

## 24. Benchmark Redis: công cụ và giới hạn

Redis cung cấp `redis-benchmark`, hữu ích để đo hiệu năng command theo điều kiện được cấu hình.

Ví dụ trên môi trường Redis thử nghiệm:

```bash
redis-benchmark -h 127.0.0.1 -p 6379 -n 100000 -c 50 -t get,set
```

Ý nghĩa thông dụng:

- `-h`: host Redis.
- `-p`: port.
- `-n`: tổng số requests benchmark.
- `-c`: số kết nối đồng thời.
- `-t`: chọn nhóm commands benchmark.

Đo với payload định trước và in kết quả ngắn:

```bash
redis-benchmark -h 127.0.0.1 -p 6379 \
  -n 100000 -c 50 -d 1024 -t get,set -q
```

`-d 1024` thiết lập kích thước data payload cho những lệnh benchmark phù hợp. Cú pháp và output có thể khác nhẹ theo redis-cli/redis-benchmark version, nên kiểm tra `redis-benchmark --help`.

**Các lệnh trên chỉ là hướng dẫn thử nghiệm, không phải kết quả benchmark.** Không chạy benchmark nặng trên Redis production mà không có kế hoạch tải và quyền thực hiện.

### 24.1. Test concurrency khác test payload

Một kết quả:

```text
-c 1, payload 100 B
```

không so sánh trực tiếp với:

```text
-c 200, payload 32 KiB
```

vì cả concurrency và lượng dữ liệu đều thay đổi.

Nên điều chỉnh **một yếu tố tại một thời điểm** khi cần xác định nguyên nhân tăng/giảm latency.

### 24.2. `-P` pipeline có thể thay đổi throughput mạnh

Ví dụ:

```bash
redis-benchmark -h 127.0.0.1 -p 6379 \
  -n 100000 -c 50 -P 16 -t get,set -q
```

`-P 16` dùng pipelining theo điều kiện benchmark. Pipeline giúp giảm số lượt chờ network trên nhiều command, nhưng **không có nghĩa ứng dụng thật cũng pipeline được 16 lệnh mỗi request**.

Nếu workload production chủ yếu gửi một `GET` rồi phải đợi kết quả trước khi tính lệnh tiếp theo, benchmark pipeline 16 có thể cho throughput đẹp nhưng không đại diện.

### 24.3. Redis benchmark không đo Spring DTO serialization

`redis-benchmark` không chạy:

- Jackson serializer của ứng dụng.
- Spring Cache key generator.
- HTTP server security/filter.
- R2DBC/JDBC database miss path.
- Custom Lua business logic trừ khi bạn benchmark đúng script ấy.
- Retry/interceptor từ Spring.
- Application connection-pool waiting.
- DTO mapping và response rendering.

Nó chủ yếu dùng để tìm hiểu giới hạn Redis/connection/command dưới workload command-level. Cần thêm load test **through real Spring endpoints**.

## 25. Thiết kế ma trận load test

Một bảng cấu hình test nên thay đổi từng tham số có chủ đích:

| Chiều đo | Những giá trị nên thử |
|---|---|
| Payload bytes | Small / median / p95 / p99 thực tế |
| Read/write ratio | 95/5, 80/20, 50/50 theo workload |
| Cache hit rate | Gần 100%, mức production, cold start |
| Concurrency | 1, 10, 50, 100, ... tùy hệ thống |
| Request rate | Tăng bậc thang đến SLO threshold |
| Key distribution | Uniform, hot-key/Zipf-like |
| TTL | Không TTL, TTL thường dùng, nhiều key hết hạn cùng lúc |
| Redis structure | String/Hash/Set/ZSet/Stream |
| Client type | Blocking `RedisTemplate`, reactive API |
| Network | Same host, same zone, cross zone, TLS |
| Redis topology | Standalone, Sentinel, Cluster |
| Persistence | RDB/AOF theo production |
| Failure mode | Healthy, retry, reconnect, failover |
| Result | p50/p95/p99, throughput, error rate, memory, CPU |

Không cần chạy mọi kết hợp ngay từ đầu. Bắt đầu bằng kịch bản baseline và tăng độ phức tạp theo rủi ro lớn nhất.

### 25.1. Warm-up

Lần đầu chạy:

- JIT compilation/JVM class loading.
- Connection establishment.
- TLS handshake.
- Cache chưa có dữ liệu.
- Micrometer instrumentation initialization.
- JSON serializer caches.
- Hệ điều hành/network chưa ổn định.

Các yếu tố đó có thể làm kết quả khác steady-state. Nên có pha warm-up được ghi riêng, và test cold-start nếu sản phẩm cần chịu tải sau restart.

**Cold-start không phải lỗi dữ liệu**: nó là một kịch bản vận hành riêng cần đo thay vì lọc bỏ toàn bộ.

### 25.2. Phân biệt cold và warm cache

**Warm cache:**

```text
Hầu hết keys đã có.
GET -> cache hit.
```

**Cold cache:**

```text
Nhiều keys chưa có.
GET -> miss -> DB -> SET.
```

Nếu chỉ benchmark warm cache, bạn có thể đánh giá thấp nguy cơ sau Redis restart/eviction/redeploy. Nếu chỉ benchmark cold cache, bạn có thể đánh giá thấp khả năng tải steady-state.

Cần cả hai nếu hệ thống cache quan trọng.

### 25.3. Key distribution: hot keys

Trong production, một số keys được đọc rất nhiều:

```text
product:popular
stock:flash-sale
config:global
```

Một benchmark dùng key ngẫu nhiên phân phối đều có thể bỏ qua:

- Hot slot trên Redis Cluster.
- Cạnh tranh update cùng counter.
- Kích thước response của những key nóng.
- Cache stampede khi hot key hết hạn.
- CPU của Lua script xử lý aggregate nóng.

Dùng workload phản ánh tần suất key thực tế; không chỉ lấy random uniform.

## 26. Coordinated omission: benchmark có thể bỏ sót độ trễ xấu

Một sai lệch phổ biến trong load test là **coordinated omission**: generator tạo request mới phụ thuộc việc request trước hoàn thành. Khi server chậm, generator cũng giảm tốc độ gửi, khiến số request bị chậm mà nó quan sát nhỏ hơn áp lực thực tế từ một nguồn tải độc lập.

Ví dụ:

```text
Mục tiêu thực: 1.000 request/s đều đặn.
Server tạm dừng 1 giây.
```

Trong một mô hình closed-loop, các worker đang đợi response và không gửi nhiều requests mới trong lúc server dừng. Bài test có thể ghi một số requests chậm nhưng bỏ qua backlog mà 1.000 arrival/s độc lập sẽ tạo ra.

Vì vậy, cần xác định load generator là:

- **Closed-loop/concurrency-based:** mỗi virtual user gửi request mới khi request trước xong.
- **Open-loop/arrival-rate-based:** phát request theo lịch/target arrival rate, dù request trước còn chờ.

Không có loại nào luôn sai: closed-loop phù hợp một số mô hình người dùng có think-time, open-loop phù hợp đo khả năng chịu external arrival rate. Quan trọng là **khớp mô hình tải mong muốn** và không rút kết luận quá mức từ số p99 đã bị che.

### 26.1. Nên báo cáo actual arrival rate và completed rate

Trong kịch bản tải cao, ghi:

```text
Requested arrival rate
Actual arrival rate
Completed responses/s
Timed-out requests
In-flight / queue length
Latency distribution
```

Nếu generator không thể phát đủ requested rate, kết quả không phản ánh mức tải mục tiêu.

### 26.2. Client benchmark cũng có thể là bottleneck

Load generator thiếu CPU/network có thể không tạo được yêu cầu hoặc làm client latency cao. Nên giám sát:

- CPU/RAM của máy chạy benchmark.
- Network bandwidth.
- TLS handshake/session reuse.
- Thread/connections.
- Số open files/sockets.
- Error/timeout ở generator.

Không kết luận Redis chạm giới hạn nếu máy tạo tải đã đầy CPU.

## 27. Cách đọc đường cong throughput–latency

Tăng load theo từng bậc:

```text
Load level 1:  500 RPS
Load level 2: 1000 RPS
Load level 3: 1500 RPS
Load level 4: 2000 RPS
Load level 5: 2500 RPS
```

Với mỗi bậc, ghi:

```text
Actual completed RPS
p50, p95, p99
error/timeout rate
Redis commands/s
Redis CPU/RSS
App CPU/GC
Network bytes/s
Connection queue
DB miss rate
```

Một đường cong có thể trông như:

```text
Latency
  ^
  |                             /   overload
  |                          __/
  |                       __/
  |                  ____/
  |            _____/
  |___________/
  +--------------------------------> Throughput
             stable    knee
```

“Đỉnh throughput” không nhất thiết là mức vận hành tốt. Nếu p99 đã vượt SLO tại mức thấp hơn, capacity phù hợp bị giới hạn bởi **SLO** chứ không phải throughput tối đa mà benchmark còn báo.

### 27.1. Mốc saturation không chỉ ở Redis CPU

Một instance Spring có thể bão hòa trước Redis vì:

- Số thread request.
- Pool kết nối blocking.
- GC.
- JSON serialization.
- Database cache-miss path.
- Network stack.
- Lock contention trong code.
- Remote dependency limit.

Nếu Redis CPU thấp nhưng HTTP p99 tăng, cần kiểm tra các tầng còn lại trước khi scale Redis.

## 28. Pipeline và batch trong Spring Data Redis

Khi cần gửi nhiều lệnh độc lập, **pipelining** có thể giảm số network round trips.

Ví dụ qua `StringRedisTemplate`:

```java
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.core.StringRedisTemplate;

public List<Object> batchGet(
        StringRedisTemplate redis,
        List<String> keys) {

    List<Object> replies = redis.executePipelined(connection -> {
        for (String key : keys) {
            byte[] rawKey =
                key.getBytes(StandardCharsets.UTF_8);

            connection.stringCommands().get(rawKey);
        }

        return null;
    });

    return replies;
}
```

Đây là ví dụ khái niệm dùng raw command và `StringRedisTemplate` với key UTF-8; kiểu callback/serialization cho `executePipelined` cần phù hợp với phiên bản Spring Data Redis, Redis connection factory và serializer đã cấu hình.

Nếu chỉ cần nhiều String keys trong cùng slot, `multiGet`/`MGET` có thể là lựa chọn khác. Trong Redis Cluster, nhiều lệnh hoặc một lệnh multi-key phải xét ràng buộc hash slots và mức hỗ trợ của driver.

### 28.1. Pipelining cải thiện gì?

Không pipeline:

```text
GET k1 -> đợi reply
GET k2 -> đợi reply
GET k3 -> đợi reply
...
```

Pipeline:

```text
GET k1
GET k2
GET k3
... gửi liên tiếp
  |
  v
Thu replies tương ứng
```

Tiềm năng lợi ích:

- Ít network wait giữa lệnh.
- Tăng commands/s.
- Giảm tổng thời gian hoàn thành batch trong một số workload.

Nhưng pipeline có trade-offs:

- Nhiều commands cùng in-flight.
- Redis/client cần buffer replies.
- Payload responses lớn làm tăng memory/network pressure.
- Một command chậm có thể ảnh hưởng latency các responses khác.
- Xử lý lỗi từng command phức tạp hơn.
- Không tự thành một transaction atomic.
- Concurrency lớn + pipeline sâu có thể làm p99 tệ đi.

### 28.2. Đo pipeline theo batch lẫn theo command

Không chỉ báo:

```text
Pipeline 1000 GET mất 50 ms.
```

Mà nên ghi:

```text
Batch completion latency
Number of commands in batch
Batch size distribution
Per-command outcome
Total bytes sent/received
Memory peak
p95/p99 latency của requests đồng thời khác
```

Một pipeline tăng tổng throughput nhưng làm user-facing request p99 tăng vẫn có thể là trade-off không phù hợp.

### 28.3. Pipeline không phải giải pháp cho mọi lệnh phụ thuộc nhau

Nếu lệnh thứ hai cần kết quả lệnh thứ nhất để quyết định điều kiện, pipeline hai lệnh trước khi biết kết quả có thể sai về nghiệp vụ. Khi cần read-modify-write atomic, dùng Redis command phù hợp, Lua hoặc transaction cùng slot thay vì chỉ pipeline.

## 29. Redis Cluster: đo per-node, per-slot, per-command

Redis Cluster chia key vào hash slots. Dù tổng cluster còn nhiều CPU, một primary có thể bị quá tải do hot slot.

```text
Cluster:
    Primary A: 90% CPU, p99 GET cao
    Primary B: 25% CPU
    Primary C: 30% CPU
```

Một dashboard tổng CPU trung bình có thể che giấu A đang quá tải.

### 29.1. Đo từng primary

Trên từng primary, theo dõi:

```text
instantaneous_ops_per_sec
used_memory / RSS
network input/output
connected_clients
cmdstat_* mix
SLOWLOG / latency
evicted_keys
replication/failover status
```

Dữ liệu tổng hợp phải giữ được thông tin **node lớn nhất/slot nóng**, không chỉ lấy trung bình mọi node.

### 29.2. Hash tag và hot slot

Key:

```text
cart:{c-101}:items
cart:{c-101}:total
```

cùng slot, thuận tiện cho multi-key atomic operation. Nhưng nếu tất cả key đều đặt dưới `{global}`, Redis Cluster không được tận dụng tốt.

Một kịch bản test uniform keys có thể không phát hiện điều này. Nên đo với chính quy tắc đặt tên key và phân phối tenant/aggregate thực tế.

### 29.3. MOVED/ASK và topology refresh

Khi Cluster resharding/failover, client có thể nhận redirect hoặc phải refresh topology. Thời gian đó có thể làm tail latency tăng. Benchmark trên Cluster vừa ổn định không dự đoán đầy đủ tình huống slot migration.

Nếu hệ thống cần SLO trong các lần failover/resharding, hãy **đo riêng failure scenario**, không trộn nó vào steady-state rồi giấu trong một con số average.

### 29.4. Lệnh nhiều key trên Cluster

`MGET`/`MSET`, Lua script và transaction nhiều key có những ràng buộc cùng hash slot. Một lệnh trên standalone chạy tốt có thể lỗi `CROSSSLOT` khi đổi topology.

Đây là vấn đề **correctness/configuration**, không phải latency optimization. Cần đo tỷ lệ lỗi bên cạnh throughput.

## 30. Redis Streams: throughput không chỉ là XADD/s

Với Redis Streams, có ít nhất ba tốc độ:

```text
Producer writes:
    XADD records/s

Consumer reads:
    XREADGROUP records/s

Processing:
    handler success + XACK records/s
```

Nếu producer đạt 20.000 entries/s nhưng consumer chỉ xử lý và ACK 10.000 entries/s, backlog/lag hoặc pending có thể tăng. Tốc độ `XADD` cao không chứng minh pipeline xử lý nghiệp vụ đáp ứng đủ.

Các lệnh quan sát:

```redis
XLEN orders:events
XINFO STREAM orders:events
XINFO GROUPS orders:events
XINFO CONSUMERS orders:events orders-workers
XPENDING orders:events orders-workers
```

### 30.1. Lag và pending là hai loại backlog

- **Group lag:** dữ liệu chưa được giao theo vị trí consumer group, khi metric tính được.
- **Pending:** entries đã giao nhưng chưa ACK.

Tình huống:

```text
Group lag = 0
Pending   = 100000
```

không có nghĩa workload đã xử lý xong. Có thể consumer đã nhận nhiều entries nhưng không ACK.

### 30.2. Kích thước Stream không chỉ là payload

Nếu có nhiều consumer groups/PEL entries, overhead có thể tăng. Đo:

```redis
MEMORY USAGE orders:events
XLEN orders:events
XINFO GROUPS orders:events
```

và quan sát memory Redis tổng thể khi tăng group/consumer count.

### 30.3. Batching trong Stream có trade-off

Tăng `COUNT` khi đọc có thể giảm round trips, nhưng:

- Tăng số pending cùng lúc.
- Tăng memory dùng bởi handler.
- Kéo dài latency của cuối batch.
- Tăng lượng work cần recover khi consumer crash.
- Có thể tăng throughput nếu xử lý batch hiệu quả.

Nên đo **records/s, acknowledgment latency, pending growth, handler p99 và memory** cùng nhau.

### 30.4. Không bỏ qua retention

`XADD ... MAXLEN`, `XTRIM` hoặc chính sách lưu lịch sử ảnh hưởng memory nhưng có thể làm mất payload mà consumer chậm cần để xử lý lại.

Không tối ưu memory bằng cách trim quá mạnh khi nghiệp vụ cần replay/PEL recovery.

## 31. Redis Pub/Sub: throughput cần tính fan-out

Với Pub/Sub:

```text
1 Publisher
  |
  +--> PUBLISH 1000 messages/s
           |
           +--> Subscriber A
           +--> Subscriber B
           +--> Subscriber C
           +--> Subscriber D
```

Publisher gửi 1.000 publications/s, nhưng Redis có thể phải phục vụ nhiều output streams do **fan-out** tới subscribers.

Các chỉ số nên xem:

```text
Published messages/s
Number of subscribers
Redis network output bytes/s
Subscriber receive rate
Subscriber drops/reconnects
Handler latency
Backpressure/buffering ở WebFlux/SSE
```

`PUBLISH` trả về count liên quan subscriber nhận theo ngữ nghĩa Redis, **không phải ACK rằng business handler đã xử lý**.

Nếu test chỉ có một subscriber trong khi production có hàng nghìn clients, network/output-buffer pressure có thể hoàn toàn khác.

### 31.1. Pub/Sub không phải benchmark job queue

Redis Pub/Sub không lưu backlog/replay mặc định. Nếu ứng dụng cần mọi message được xử lý, throughput đơn thuần của Pub/Sub không đo được reliability. Nên chọn Redis Streams hoặc broker phù hợp khi yêu cầu là job processing có ACK/retry.

## 32. Pipelining, batch và serialization tác động đến hiệu năng thế nào?

Một phép so sánh công bằng cần cùng dữ liệu và cùng công việc:

| Phương án | Redis commands | CPU Java | Network | Memory |
|---|---|---|---|---|
| N `GET` tuần tự | N | N lần decode | N round trips gần đúng | Thấp in-flight |
| N `GET` pipeline | N | N lần decode | Ít wait giữa commands | N replies có thể buffered |
| Một `MGET` same-slot | 1 | Decode N values | Một command multi-key | Response batch |
| JSON String lớn | Ít keys | Parse/serialize toàn object | Bytes JSON | Redis String overhead |
| Redis Hash fields | Một key, nhiều fields | Mapping fields | Tùy HGET/HMGET/HGETALL | Encoding Hash |
| Lua server-side | Một script call | Ít client round trips | Keys/args + reply | Script CPU ở Redis |

Không thể chỉ nhìn số Redis commands để quyết định phương án nhanh nhất. Một `HGETALL` trên Hash khổng lồ có thể tốn hơn nhiều lệnh `HGET` chỉ lấy fields cần thiết. Một Lua script dài có thể chặn Redis event loop đủ lâu để làm tail latency nhiều client khác tăng.

## 33. Payload compression: giảm bytes nhưng tăng CPU

Nén value có thể giảm:

- Bytes gửi/nhận qua network.
- Memory Redis cho value trong những workload có khả năng nén tốt.

Nhưng tăng:

- CPU serialize/compress ở Java.
- CPU decompress khi read.
- Latency truy cập.
- Chi phí copy bytes/allocation.
- Khả năng mất partial-field access với binary payload.

Một thiết kế benchmark:

```text
A. Plain JSON
B. Compressed JSON
```

Giữ nguyên:

```text
DTO
Key distribution
Read/write mix
Concurrency
TTL
Dataset count
Redis topology
```

Với mỗi phương án, đo:

```text
Raw payload bytes
Compressed payload bytes
Compression ratio
Serialize/compress p95/p99
Redis GET/SET p95/p99
End-to-end HTTP p95/p99
Redis MEMORY USAGE
CPU/RSS JVM và Redis
```

Nếu JSON chỉ 200 byte, compression header/metadata có thể khiến payload lớn hơn. Nếu payload 100 KiB và mạng xa, compression có thể hữu ích. **Không quyết định nén chỉ từ tên thuật toán.**

### 33.1. Format phải versioned

Nếu chuyển từ plaintext JSON sang compressed binary, các readers cần biết format nào đang được lưu. Có thể dùng schema version, magic header hoặc key namespace version.

Không tự đổi serializer và kỳ vọng mọi dữ liệu cache cũ được đọc chính xác; trong quá trình migrate, lỗi deserialize có thể biến thành cache misses và làm sai benchmark.

## 34. Đặt TTL ảnh hưởng thông lượng và RAM

TTL quyết định bao lâu một key có thể tồn tại:

```redis
SET product:42 payload EX 600
```

TTL ngắn:

- Giảm thời gian dữ liệu stale.
- Có thể giảm số key tồn tại.
- Tăng số cache misses và writes để tái tạo.
- Có thể tăng tải database.
- Nếu nhiều key hết hạn cùng lúc, tạo burst cache miss.

TTL dài:

- Tăng hit rate trong một số workload.
- Có thể tăng RAM.
- Tăng rủi ro stale dữ liệu.
- Giảm số lần recompute.

**Không tối ưu TTL theo memory mà bỏ qua database throughput và p99 HTTP.**

### 34.1. Cache stampede

Nếu một hot key hết hạn, 500 requests đồng thời có thể cùng miss rồi đổ vào database.

```text
Hot key expires
     |
     +--> 500 concurrent requests
               |
               +--> GET miss
               +--> Database read x 500
               +--> Redis SET nhiều lần
```

Hệ thống có thể thấy Redis hit rate giảm, HTTP p99 tăng và database CPU cao, dù Redis command execution không chậm.

Giải pháp cần đo hiệu quả:

- TTL jitter.
- Single-flight theo key.
- Prewarming.
- Stale-while-revalidate nếu nghiệp vụ cho phép.
- Giới hạn concurrency ở cache loader.
- Negative caching có TTL/consistency phù hợp.

### 34.2. TTL jitter là gì?

Thay vì tất cả keys có TTL đúng 600 giây:

```text
TTL = 600s ± một độ lệch có kiểm soát
```

để giảm hiện tượng cùng hết hạn.

Tuy nhiên, jitter không phù hợp nếu TTL mang deadline bảo mật/pháp lý chính xác như OTP expiry. Phải phân biệt **TTL cache** với **deadline nghiệp vụ**.

## 35. Performance test khi có Redis persistence

Nếu production bật RDB/AOF, load test có thể cần cấu hình tương đương. Bởi vì:

- `BGSAVE` có fork/copy-on-write.
- AOF có I/O và fsync/rewrite.
- Write-heavy workload làm COW tăng.
- Disk pressure gây spikes.
- Redis startup/restore làm mất warm cache hoặc tạo workload mới.

Một benchmark Redis test không bật persistence có thể khác production đáng kể.

Theo dõi:

```redis
INFO persistence
INFO memory
```

cùng `INFO stats`, client latency và OS disk/CPU metrics.

### 35.1. Nhìn p99 trong thời gian BGSAVE

Một cách đo:

```text
Period A: steady load, không có BGSAVE đang chạy
Period B: steady load, BGSAVE được kích hoạt theo quy trình test
```

So sánh HTTP/Redis client p99, Redis fork latency, COW và disk throughput. Không chỉ so throughput trung bình toàn test vì spikes ngắn có thể bị che đi.

### 35.2. Production durability và test durability phải tương đồng

Không nên tối ưu bằng cách tắt AOF/BGSAVE trong production chỉ vì benchmark nhanh hơn nếu nghiệp vụ yêu cầu khôi phục dữ liệu.

Performance là một trong nhiều ràng buộc: correctness, data durability, RPO/RTO và availability có thể quan trọng hơn việc tăng vài phần trăm throughput.

## 36. Latency khi connection timeout/retry

Một Redis operation có timeout 2 giây và retry 3 lần có thể chiếm **nhiều giây** tại request HTTP, ngay cả khi Redis server execution trung bình chỉ vài microseconds.

Ví dụ:

```text
Attempt 1 timeout: 2s
Backoff:           0,2s
Attempt 2 timeout: 2s
Backoff:           0,4s
Attempt 3 success: 0,01s

Total service latency: ~4,61s
```

Đây là phép tính minh họa; các deadline/cancellation và số lần retry thực tế cần kiểm tra.

Nên đo tách:

```text
Latency mỗi Redis attempt
Number of retries
End-to-end operation latency
Timeout rate
Unknown outcome
Connection reconnect time
```

Nếu chỉ đo attempt cuối thành công, bạn sẽ báo latency Redis rất thấp nhưng người dùng chờ vài giây.

### 36.1. Không retry mù các write non-idempotent

Các lệnh như `INCR`, `LPUSH`, `XADD *` có thể đã thực thi trước khi response bị mất. Retry có thể nhân đôi tác dụng phụ.

Khi thiết kế retry performance test, cần phân biệt:

- Lỗi trước khi gửi.
- Redis đã thực thi nhưng response mất.
- Reconnect/failover.
- Idempotency key/receipt.
- Business side effect đã commit chưa.

Một test đạt throughput rất cao bằng cách retry mọi thứ nhưng gây duplicate nghiệp vụ là **không đạt yêu cầu**.

## 37. Một quy trình benchmark end-to-end có thể lặp lại

### Bước 1 — Xác định câu hỏi

Ví dụ:

> “Spring Boot service có thể phục vụ 2.000 RPS với product cache 90% hit, JSON p99 dưới 8 KiB, p99 HTTP dưới 60 ms và Redis không evict bất thường không?”

Mục tiêu là một **giả thuyết đo được**, không phải “kiểm tra Redis nhanh không”.

### Bước 2 — Ghi cấu hình môi trường

Ghi:

```text
Spring Boot version
Spring Data Redis version
Lettuce version
JDK/GC
Redis version
Redis topology
CPU/RAM Redis host
Network/TLS
Serializer
TTL
Connection configuration
RDB/AOF settings
Dataset size
```

Nếu không có thông tin này, rất khó so sánh lần test A và B.

### Bước 3 — Chuẩn bị dataset đại diện

Nạp dữ liệu có:

```text
Số key dự kiến gần production
Phân phối payload sizes gần production
Key prefix/tag đúng production
TTL và tỷ lệ key có TTL
Hot keys
Repository indexes/Streams nếu sử dụng
```

Nếu dataset chỉ có 100 keys trong test nhưng production có 100 triệu keys, kết quả memory và hot-key behavior có thể khác.

### Bước 4 — Xác định workload mix

Ví dụ:

```text
GET product: 70%
GET session: 15%
UPDATE cart: 10%
XADD event: 5%
```

Đây chỉ là ví dụ. Thay bằng tỷ lệ request/Redis command từ telemetry thực tế.

### Bước 5 — Chạy warm-up

Khởi động app/Redis clients, JIT và preload cache theo kịch bản. Ghi riêng thời gian warm-up, sau đó chạy test steady-state với thời lượng đủ để quan sát p99.

### Bước 6 — Tăng tải có kiểm soát

Chạy các bậc tải, mỗi bậc đủ thời gian để hệ thống ổn định hoặc thể hiện tăng backlog:

```text
25% target
50% target
75% target
100% target
125% target (nếu môi trường test cho phép)
```

Không đẩy một production Redis đang chia sẻ traffic thật lên 125% target mà không có quyền và kế hoạch.

### Bước 7 — Thu metrics đồng thời

Ghi:

```text
HTTP p50/p95/p99 + error rate
App Redis call p50/p95/p99
Lettuce/driver command timing nếu có
Redis INFO stats/commandstats
Redis CPU/RSS/network
GC pauses
Payload bytes/memory usage distributions
DB load nếu có cache misses
```

Dùng chung thời gian/cửa sổ đo để tìm tương quan.

### Bước 8 — Xác định bottleneck

Ví dụ:

```text
HTTP p99 tăng mạnh
App Redis timer ổn định
DB query latency tăng
=> nguyên nhân có thể là cache miss/DB, không phải Redis execution.
```

Hoặc:

```text
HTTP p99 và Redis client p99 cùng tăng
SLOWLOG không xuất hiện command chậm
Network RTT tăng
=> kiểm tra network/client queue/connection.
```

Hoặc:

```text
Lua/EVAL usec_per_call tăng
Redis CPU cao
Cùng hot slot
=> kiểm tra script và data model.
```

### Bước 9 — Chỉ thay đổi một yếu tố

Ví dụ thử thay JSON String bằng Hash, hoặc pipeline batch size từ 1 lên 16, rồi đo lại cùng workload.

Nếu đồng thời đổi serializer, connection config, TTL và Redis instance size thì không thể xác định thay đổi nào tạo lợi ích.

### Bước 10 — Ghi báo cáo và guardrail

Báo cáo:

```text
Hypothesis
Environment
Dataset
Workload
Measured metrics
Confidence/limitations
Decision
Rollback plan
Monitoring after deploy
```

Không chỉ ghi “nhanh hơn 30%” mà thiếu p99, lỗi, CPU và RAM.

## 38. Mẫu báo cáo hiệu năng

Một bảng đo có thể dùng trực tiếp:

| Metric | Baseline | Candidate | Điều kiện |
|---|---|---|---|
| Actual RPS | Điền kết quả | Điền kết quả | Cùng arrival rate |
| p50 HTTP (ms) | Điền | Điền | Cùng workload |
| p95 HTTP (ms) | Điền | Điền | Cùng workload |
| p99 HTTP (ms) | Điền | Điền | Cùng workload |
| HTTP error rate | Điền | Điền | Cùng deadline |
| Redis GET p99 (ms) | Điền | Điền | Cùng method/metric |
| Redis ops/s | Điền | Điền | Per node + cluster |
| Cache hit ratio | Điền | Điền | Tách product/session |
| Value p50/p99 bytes | Điền | Điền | Serialized bytes |
| MEMORY USAGE/key p50 | Điền | Điền | Representative samples |
| Redis used_memory/RSS | Điền | Điền | Sau warm-up |
| Redis CPU peak | Điền | Điền | Cùng load |
| JVM CPU/GC pauses | Điền | Điền | Cùng JDK/GC |
| DB QPS | Điền | Điền | Nếu cache miss |
| Stream pending/lag | Điền | Điền | Nếu có worker |
| Observed bottleneck | Mô tả | Mô tả | Theo traces và counters |

Không điền số dự đoán vào cột measured. Nếu chưa đo một chỉ số, ghi rõ `NOT_MEASURED` thay vì biến giả định thành kết quả.

## 39. Những sai lầm phổ biến khi đo hiệu năng

### 39.1. Chỉ đo average GET

Average che mất tail latency, retry, GC và network spikes. Cần p50/p95/p99 và tỷ lệ lỗi.

### 39.2. So `SLOWLOG` với HTTP p99 như cùng một metric

SLOWLOG phản ánh execution tại Redis server, không bao gồm toàn bộ request path.

### 39.3. Nhân kích thước JSON với số key để tính RAM

Bỏ qua Redis key/object overhead, TTL metadata, indexes, fragmentation và process buffers.

### 39.4. Chỉ đo một key nhỏ rồi suy ra cả database

Dataset thật có nhiều loại payload, outliers và distribution lệch. Cần sampling theo key family.

### 39.5. Lấy `STRLEN` thay `MEMORY USAGE`

`STRLEN` chỉ là bytes String value, không phải RAM key đầy đủ.

### 39.6. Dùng `KEYS *` trên production

Có thể chặn Redis lâu khi keyspace rất lớn. Dùng SCAN có giới hạn hoặc dataset test.

### 39.7. Chạy redis-benchmark với -P 32 rồi báo HTTP RPS tương đương

Redis command pipeline benchmark không bao gồm ứng dụng Spring, serializer, endpoint và database.

### 39.8. Dùng một connection tuần tự để kết luận Redis quá chậm

Network RTT có thể chi phối. Cần test concurrency hợp lý, nhưng không vượt kiểm soát.

### 39.9. Chỉ tăng concurrency và bỏ qua p99

Có thể tăng throughput ngắn hạn nhưng hàng đợi và timeout tăng. Phải đo cả hai.

### 39.10. Benchmark lúc Redis rỗng

Memory, data encoding, cache hit rate và key distribution khác hoàn toàn hệ thống có dữ liệu thật.

### 39.11. Không tách warm cache khỏi cold cache

Hệ thống có thể nhanh lúc steady-state nhưng quá tải database sau restart.

### 39.12. Tắt RDB/AOF trong test khi production bật

Che mất ảnh hưởng fork/COW/fsync. Performance test nên phù hợp environment thực.

### 39.13. Đo Reactive Mono trước khi subscribe

Làm sai thời gian command; cần đo theo subscription/attempt.

### 39.14. Gắn Redis key vào metrics tag

Tạo cardinality explosion; dùng prefix/operation name có giới hạn.

### 39.15. Kết luận memory leak chỉ từ RSS không giảm sau DEL

Có thể là allocator fragmentation hoặc memory cache chưa trả lại OS. Cần thêm dữ liệu.

### 39.16. Nhầm Redis ops/s với business transactions/s

Một business transaction có nhiều commands, retries và dependency calls.

### 39.17. Chỉ đo producer XADD/s

Bỏ qua consumer xử lý, ACK, PEL/lag và retention.

### 39.18. So sánh hai benchmark khác Redis version/network/payload

Nếu các điều kiện thay đổi, kết luận “serializer A nhanh hơn B” có thể sai.

### 39.19. Chạy MONITOR liên tục để đo throughput

Có overhead và rủi ro lộ dữ liệu. Dùng INFO/counters/traces.

### 39.20. Tối ưu memory nhưng bỏ qua correctness

Rút TTL, trim Stream hoặc bỏ index có thể giảm RAM nhưng làm mất dữ liệu cần dùng, giảm hit rate hoặc hỏng query. Cần đo cả tính đúng đắn.

## 40. Bài thực hành 1 — Tách độ trễ HTTP và Redis GET

Tạo một API `GET /api/products/{id}` dùng `StringRedisTemplate`.

1. Đặt Micrometer timer quanh `GET`.
2. Bật HTTP metrics của Actuator.
3. Nạp 1.000 product keys với TTL đủ dài.
4. Chạy một workload warm cache có kiểm soát.
5. Ghi p50/p95/p99 Redis operation và HTTP request.
6. Thay một phần request thành cache miss.
7. So sánh Redis timer với HTTP latency.

Câu hỏi: tại sao HTTP p99 có thể tăng rất nhiều dù server Redis `GET` execution vẫn nhanh?

## 41. Bài thực hành 2 — Đo commandstats

Trên Redis thử nghiệm:

```redis
INFO commandstats
```

Ghi `calls` cho `GET`, `SET`, `HGETALL`.

Chạy 10.000 requests qua Spring service, rồi đọc lại `INFO commandstats`. Tính delta của từng command. Xác định số Redis commands trên một business request.

Phân tích khác biệt giữa predicted command mix và observed command mix. Nếu service dùng chung Redis với workload khác, báo cáo giới hạn của phép đo.

## 42. Bài thực hành 3 — Payload bytes so với MEMORY USAGE

Tạo một DTO JSON:

```json
{
  "id": "p-101",
  "name": "Laptop",
  "priceInCents": 1999900,
  "tags": ["electronics", "featured"]
}
```

Các bước:

1. Serialize bằng Jackson.
2. Đo `byte[].length` theo UTF-8.
3. Lưu bằng `StringRedisTemplate`.
4. Chạy `STRLEN product:p-101`.
5. Chạy `MEMORY USAGE product:p-101`.
6. Đo `INFO memory` trước/sau khi nạp 10.000 keys tương tự.
7. Giải thích vì sao bytes payload, memory/key và RSS không giống nhau.

## 43. Bài thực hành 4 — JSON String so với Redis Hash

Lưu cùng dữ liệu user theo hai phương án:

```redis
SET lab:user:json "{\"id\":\"u-1\",\"name\":\"Alice\",\"city\":\"HCMC\"}"
HSET lab:user:hash id u-1 name Alice city HCMC
```

Đo:

```redis
MEMORY USAGE lab:user:json
MEMORY USAGE lab:user:hash
STRLEN lab:user:json
HLEN lab:user:hash
OBJECT ENCODING lab:user:hash
```

Lặp với số fields và độ dài field tăng dần. Đo cả latency đọc toàn object và đọc một field, rồi rút kết luận theo access pattern thực tế thay vì chỉ dựa trên RAM.

## 44. Bài thực hành 5 — Pipelining

Trong Redis thử nghiệm, so sánh:

```bash
redis-benchmark -h 127.0.0.1 -p 6379 \
  -n 100000 -c 50 -P 1 -d 1024 -t get,set -q
```

và:

```bash
redis-benchmark -h 127.0.0.1 -p 6379 \
  -n 100000 -c 50 -P 16 -d 1024 -t get,set -q
```

Ghi throughput, latency output, Redis CPU và network throughput. Tạo thêm một test qua Spring endpoint để xem pipeline có thực sự áp dụng cho request path hay không.

Câu hỏi: pipeline tăng commands/s có đồng nghĩa p99 user endpoint tốt hơn không?

## 45. Bài thực hành 6 — Warm-cache và cold-cache

1. Chuẩn bị bảng sản phẩm trong database test.
2. Test warm cache với 90–100% hit rate.
3. Làm rỗng namespace cache thử nghiệm bằng cơ chế an toàn.
4. Test cold cache với cùng arrival rate.
5. Đo hit/miss, DB QPS, Redis GET/SET, HTTP p99.
6. Thử prewarm hoặc single-flight cho hot keys.
7. Đo lại.

Không `FLUSHALL` trên Redis chia sẻ môi trường. Hãy dùng một Redis test instance hoặc namespace riêng đã được cô lập.

## 46. Bài thực hành 7 — TTL burst và jitter

Tạo nhiều key cache với TTL tương đương nhau, khiến nhiều key hết hạn gần cùng mốc. Chạy workload đọc những key ấy và đo Redis hit/miss, DB QPS và p99.

Sau đó thử TTL jitter trong miền cho phép của cache và so sánh. Giải thích vì sao TTL jitter có thể giảm thundering herd nhưng không thích hợp để thay đổi deadline OTP.

## 47. Bài thực hành 8 — Hot slot Redis Cluster

Dùng một Redis Cluster thử nghiệm.

1. Tạo key naming theo `order:{orderId}:...`.
2. Đo commands/s và CPU từng primary.
3. Thử một workload tập trung vào một aggregate cực nóng.
4. Quan sát node sở hữu slot của aggregate.
5. Thử một key naming rất rộng kiểu `{global}` trong một namespace lab nhỏ.
6. So sánh phân bố tải.

Giải thích tại sao tổng cluster CPU trung bình có thể che primary bị bão hòa.

## 48. Bài thực hành 9 — Stream throughput và pending

Tạo Stream/group thử nghiệm:

```redis
XGROUP CREATE lab:events lab-workers 0 MKSTREAM
```

Producer tạo entries có payload đại diện. Consumer đọc/ACK với tốc độ thấp hơn producer.

Đo:

```redis
XLEN lab:events
XINFO GROUPS lab:events
XPENDING lab:events lab-workers
MEMORY USAGE lab:events
```

So sánh `XADD records/s`, handler success/s, `XACK records/s`, pending và group lag.

Giải thích vì sao producer throughput không phải business completion throughput.

## 49. Bài thực hành 10 — Serialization và nén payload

Chuẩn bị 10.000 DTO sản phẩm với kích thước phân phối tương tự thực tế.

1. Đo Jackson serialization time và JSON bytes.
2. Đo phiên bản nén payload.
3. Đo bytes sau nén.
4. Lưu cả hai phiên bản vào Redis namespace test.
5. Đo `MEMORY USAGE` của tập mẫu.
6. Đọc/deserialize qua Spring service.
7. So sánh end-to-end p95/p99, CPU và memory.

Kết luận có nên dùng compression cho nhóm payload nào, thay vì áp dụng toàn bộ.

## 50. Bài thực hành 11 — Latency sau network timeout

Trong môi trường kiểm thử có network proxy hoặc test adapter:

1. Chạy baseline Redis GET/SET.
2. Giả lập network delay.
3. Ghi p99 client command latency, HTTP latency, server commandstats.
4. Bật retry có giới hạn và backoff.
5. Quan sát thời gian end-to-end tăng ra sao.
6. Với một write non-idempotent, thiết kế request ID để tránh double effect.

Câu hỏi: Redis server vẫn xử lý command rất nhanh có bác bỏ việc ứng dụng đang chịu latency cao không?

## 51. Bài thực hành 12 — Báo cáo capacity

Giả sử dự án dự kiến:

```text
2 triệu product keys
500.000 session keys
100.000 cart keys
Read/write mix theo telemetry production
Peak traffic gấp 3 lần bình thường
```

Hãy lập kế hoạch:

1. Lấy mẫu representative memory/key cho từng nhóm.
2. Ước tính dataset bytes bằng số lượng và memory/key đo được.
3. Bổ sung indexes, TTL, fragmentation, COW và memory headroom.
4. Đo per-primary trên Redis Cluster.
5. Ước tính command rate từ RPS và command mix.
6. Xác định p99 latency budget.
7. Chạy load test tại 50%, 100% và peak target.
8. Chỉ ra primary/app/database bottleneck.
9. Đề xuất phương án scale và cách kiểm chứng.
10. Viết báo cáo có `NOT_MEASURED` cho các chỉ số chưa có.

Mục tiêu bài tập là xây dựng **phương pháp đo và lý giải**, không phải đoán một kích thước RAM “đúng” khi chưa có dataset.

## 52. Câu hỏi tự đánh giá

1. Latency của Redis command ở phía server khác latency đo tại Spring client như thế nào?
2. Vì sao một `GET` server mất 50 µs vẫn có thể làm HTTP endpoint chờ 20 ms?
3. p99 khác average ở điểm nào?
4. Vì sao không được cộng các p99 của nhiều bước để khẳng định p99 HTTP?
5. Số lượng mẫu/cửa sổ thời gian ảnh hưởng percentile ra sao?
6. Redis ops/s khác HTTP RPS như thế nào?
7. Một request có 4 Redis commands thì phải đo thêm gì khi ước tính tải Redis?
8. Khi tăng concurrency, vì sao throughput có thể ngừng tăng còn latency tăng?
9. Dữ liệu logic, serialized bytes và Redis memory usage khác nhau ra sao?
10. `STRLEN` đo gì, `MEMORY USAGE` đo gì?
11. Vì sao `MEMORY USAGE ... SAMPLES 0` cần dùng cẩn thận?
12. `used_memory` và `used_memory_rss` có giống nhau không?
13. Fragmentation/COW ảnh hưởng capacity planning như thế nào?
14. Vì sao một DTO Redis Repository có thể tạo nhiều keys/secondary indexes?
15. Actuator có tự phát mọi Redis command latency metric trong mọi phiên bản không?
16. Tại sao không đặt productId, requestId hoặc key name làm metrics tags?
17. Vì sao nên đo reactive Redis từ subscription thay vì lúc tạo `Mono`?
18. `INFO commandstats` đo mean client round-trip hay execution time của Redis?
19. Vì sao SLOWLOG không giải thích mọi spike latency của HTTP?
20. `LATENCY DOCTOR` không có dữ liệu có chứng minh Redis không chậm không?
21. Vì sao benchmark `-P 16` không trực tiếp dự báo RPS của Spring service?
22. Warm cache và cold cache có thể dẫn đến bottleneck khác nhau ở đâu?
23. Coordinated omission là gì và ảnh hưởng p99 như thế nào?
24. Một hash slot nóng ảnh hưởng Redis Cluster ra sao?
25. `XLEN` có phản ánh toàn bộ memory và pending của Redis Stream không?
26. Vì sao `XADD` throughput cao chưa đủ chứng minh consumer xử lý kịp?
27. Khi nào compression làm tốt hơn và khi nào có thể làm chậm hơn?
28. TTL ngắn có thể làm tăng tải database như thế nào?
29. Vì sao không thể đánh giá capacity chỉ từ một mẫu `instantaneous_ops_per_sec`?
30. Báo cáo load test đáng tin cậy cần nêu những điều kiện môi trường nào?

## 53. Ghi nhớ

- **Đo ba nhóm riêng biệt:** độ trễ (p50/p95/p99), thông lượng (RPS/commands/s/bytes/s) và kích thước dữ liệu thực tế (serialized bytes, `MEMORY USAGE`, process memory).
- **Latency phải có ranh giới đo rõ ràng.** Redis server execution, Redis client round-trip, Spring service latency và HTTP p99 là những phép đo khác nhau.
- **Average có thể che tail latency**; p95/p99 và error rate thường quan trọng khi đặt SLO.
- **Redis ops/s không phải business RPS.** Một request có thể sinh nhiều commands và retries.
- `INFO stats`, `INFO commandstats`, `SLOWLOG` và `LATENCY` bổ sung cho client/HTTP metrics, nhưng không công cụ nào thay thế tất cả.
- **`STRLEN`/`HLEN`/`XLEN` đo kích thước logic**, còn `MEMORY USAGE` đo RAM key/value theo cơ chế Redis; `used_memory_rss` còn chịu ảnh hưởng fragmentation, buffers và overhead cấp process.
- **Đo dữ liệu đại diện**, gồm p50/p95/p99 payload, key families, TTL, index, hot keys và những object lớn; không nhân một key nhỏ với số key rồi coi là capacity chính xác.
- Spring Data Redis có thể dùng **Micrometer/Actuator**, Lettuce command latency instrumentation và custom timers. Không dùng key/ID không giới hạn làm metric tags.
- Với Reactive Redis, **đo từ subscription** và không `.block()` trên WebFlux event-loop để benchmark.
- `redis-benchmark` hữu ích cho command-level capacity, nhưng **không thay thế load test qua endpoint Spring thực**.
- Pipelining có thể tăng throughput nhờ giảm network waits, nhưng cần xem batch latency, buffers, p99 và tính đúng đắn.
- Redis Cluster cần đo **per-primary/hot slot**, không chỉ tổng CPU trung bình; Streams cần đo cả producer throughput, consumer ACK throughput và pending/lag.
- TTL, serialization, compression, data type và persistence đều có trade-off về CPU, RAM, network, latency và correctness.
- Một benchmark đáng tin phải có **dataset đại diện, warm-up, workload mix, concurrency/arrival rate, cùng môi trường, latency distribution và tỷ lệ lỗi**.
- Chỉ tối ưu sau khi biết bottleneck, thay đổi một yếu tố và **đo lại**. Mục tiêu là đáp ứng yêu cầu nghiệp vụ với headroom, không phải có một con số requests/s lớn nhất.

### Tài liệu tham khảo chính thức

- [Redis — Latency optimization](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/)
- [Redis — Benchmarking Redis](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/)
- [Redis — INFO](https://redis.io/docs/latest/commands/info/)
- [Redis — SLOWLOG](https://redis.io/docs/latest/commands/slowlog/)
- [Redis — LATENCY](https://redis.io/docs/latest/commands/latency/)
- [Redis — MEMORY USAGE](https://redis.io/docs/latest/commands/memory-usage/)
- [Redis — MEMORY STATS](https://redis.io/docs/latest/commands/memory-stats/)
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/)
- [Redis — STRLEN](https://redis.io/docs/latest/commands/strlen/)
- [Redis — OBJECT ENCODING](https://redis.io/docs/latest/commands/object-encoding/)
- [Redis — Pipelining](https://redis.io/docs/latest/develop/using-commands/pipelining/)
- [Redis — Redis Cluster](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/)
- [Redis — Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html)
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer — Reference Documentation](https://docs.micrometer.io/micrometer/reference/)
- [Lettuce — Reference Guide](https://redis.github.io/lettuce/)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
