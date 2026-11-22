# spring.data.redis.* và cấu hình kết nối, timeout

## 1. Redis là một phụ thuộc tích hợp, không chỉ là một địa chỉ host

Trong mô-đun **SPRING_BOOT_INTEGRATION**, một ứng dụng Spring Boot có thể truy cập cơ sở dữ liệu, gọi HTTP API, dùng cache, giao tiếp với broker và xử lý message qua Spring Integration. **Redis** thường xuất hiện ở nhiều vai trò: cache dữ liệu đọc, lưu khóa tạm thời, lưu trạng thái phiên, rate limiting, deduplication, hoặc làm một nguồn dữ liệu key-value chuyên biệt.

Dù mục đích sử dụng khác nhau, client vẫn phải kết nối qua mạng. Nếu cấu hình sai địa chỉ, TLS, credentials hoặc timeout, lỗi Redis có thể ảnh hưởng đến toàn bộ flow:

- Cache miss không thể truy cập Redis khiến một HTTP request chậm hoặc lỗi.
- Retry Redis không giới hạn làm bão hòa thread của service và gây áp lực lên database.
- Một flow ghi trạng thái idempotency vào Redis bị timeout có nguy cơ chạy side effect lặp nếu coi timeout là “chưa ghi”.
- Một consumer message chạy trong Spring Integration có thể báo lỗi và bị redelivery; cấu hình timeout không hợp lý tạo ra vòng retry ngoài dự kiến.

Vì thế, mục tiêu bài này là hiểu nhóm thuộc tính **`spring.data.redis.*`** trong Spring Boot: cách auto-configuration tạo Redis client, các trường cấu hình kết nối, thời gian chờ, Lettuce/Jedis, Redis standalone/Sentinel/Cluster, TLS và credentials, hành vi lỗi, kiểm thử và quan sát.

```mermaid
flowchart LR
    A["HTTP / Service / Integration Flow"] --> B["RedisTemplate / StringRedisTemplate"]
    A --> C["Spring Cache (nếu dùng)"]
    B --> D["RedisConnectionFactory"]
    C --> D
    D --> E["Lettuce / Jedis"]
    E --> F[("Redis server / Sentinel / Cluster")]
    G["spring.data.redis.*"] -. "Kết nối / timeout / TLS" .-> D
```

**Phạm vi phiên bản:** ví dụ dựa trên Spring Boot **3.x**, nơi nhóm thuộc tính chính là `spring.data.redis.*` và client mặc định thường là Lettuce. Ở Spring Boot 2.x, các thuộc tính Redis có thể có prefix khác, như `spring.redis.*`; khi nâng cấp không được bê nguyên file cấu hình cũ mà chưa kiểm tra metadata của phiên bản đang chạy.

## 2. Các lớp trách nhiệm: Boot, Spring Data Redis, client và server

| Thành phần | Vai trò | Điều không tự làm |
| --- | --- | --- |
| Spring Boot auto-configuration | Đọc properties và chuẩn bị bean Redis khi đủ điều kiện | Không tự tạo Redis server |
| Spring Data Redis | Cung cấp `RedisTemplate`, `StringRedisTemplate`, repositories và abstraction liên quan | Không thay thế quy tắc bảo mật/HA của Redis |
| `RedisConnectionFactory` | Điểm chung cung cấp kết nối Redis cho abstraction | Không bảo đảm mọi Redis command thành công |
| Lettuce hoặc Jedis | Thư viện client nói giao thức Redis qua network | Không biết hợp đồng nghiệp vụ của bạn |
| Redis server / Cluster / Sentinel | Lưu dữ liệu và phục vụ Redis commands | Không cung cấp transaction phân tán với database hay HTTP |
| Spring Cache | Annotation `@Cacheable`, `@CacheEvict` cùng `CacheManager` | Không mặc nhiên phù hợp cho idempotency/lock nghiệp vụ |

Một số bean thường thấy trong Spring Boot có `spring-boot-starter-data-redis`:

- `RedisConnectionFactory`: thường là `LettuceConnectionFactory` khi dùng client Lettuce.
- `RedisTemplate<Object, Object>`: tiện ích thao tác Redis có serializer do bean/configuration quyết định.
- `StringRedisTemplate`: thao tác key/value dạng chuỗi qua serializer string.
- Các thành phần reactive như `ReactiveRedisTemplate` có thể hiện diện khi dependency/client hỗ trợ, với cấu hình tương ứng.

**Có bean `RedisConnectionFactory` chưa đồng nghĩa Redis đang chạy.** Một số client tạo kết nối khi thực thi command. Lỗi DNS, authentication hoặc timeout có thể chỉ bộc lộ ở request đầu tiên.

Ngược lại, nếu ứng dụng tự khai báo một `RedisConnectionFactory` tùy chỉnh, Spring Boot có thể **back off** việc tạo factory mặc định. Khi đó thay `spring.data.redis.host` chưa chắc làm bean custom đổi địa chỉ. Muốn biết ai sở hữu cấu hình, phải kiểm tra actual bean và auto-configuration conditions.

## 3. Dependency tối thiểu và cách bật Spring Data Redis

Với Maven có Spring Boot parent hoặc BOM quản lý versions:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

Gradle:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
}
```

Starter phổ biến này bao gồm Spring Data Redis cùng Lettuce và các dependency cần thiết. Nó **không khởi động Redis server**. Bạn cần một Redis instance local, container, dịch vụ managed hoặc hạ tầng đã được provision.

Nếu ứng dụng chỉ muốn dùng Redis như một provider của Spring Cache:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-cache</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

`spring-boot-starter-cache` phục vụ Spring Cache annotations; `spring-boot-starter-data-redis` cung cấp client Redis. Có thể dùng `RedisTemplate` mà không bật `@EnableCaching`. Ngược lại, muốn annotation cache thực sự được intercept thì cần bật caching advice (thường bằng `@EnableCaching`) và có `CacheManager` phù hợp.

## 4. Cấu hình Redis standalone: host, port, database, username và password

Một cấu hình local cơ bản:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      database: 0
      connect-timeout: 2s
      timeout: 3s
      client-type: lettuce
```

Giải thích:

| Property | Ý nghĩa | Sai lầm thường gặp |
| --- | --- | --- |
| `spring.data.redis.host` | Host Redis (standalone) | Dùng tên container khi app chạy trên host thay vì trong Docker network |
| `spring.data.redis.port` | Port Redis (standalone), mặc định thường là 6379 | Hard-code host port dù Docker mapping động |
| `spring.data.redis.database` | Logical database index, thường mặc định 0 | Đặt database khác 0 trong Redis Cluster |
| `spring.data.redis.username` | ACL username khi Redis yêu cầu | Nhầm username trong app với Linux/Docker user |
| `spring.data.redis.password` | Password Redis (hoặc ACL password phù hợp) | Commit plaintext password vào Git |
| `spring.data.redis.connect-timeout` | Giới hạn thời gian thiết lập network connection | Coi là SLA tổng của một HTTP request |
| `spring.data.redis.timeout` | Timeout cho việc thực thi/đọc command Redis theo client | Coi như retry policy hoặc TCP connect timeout |
| `spring.data.redis.client-type` | Chọn Lettuce hoặc Jedis khi classpath phù hợp | Đổi sang Jedis nhưng chưa bổ sung dependency |

Thời gian dùng kiểu Spring Boot `Duration`: `2s`, `500ms`, `1m`. Nên ghi **đơn vị tường minh** để tránh đọc nhầm số nguyên thành giây hay mili-giây.

### 4.1. Cấu hình production dùng biến môi trường

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6379}
      database: 0
      username: ${REDIS_USERNAME:}
      password: ${REDIS_PASSWORD}
      connect-timeout: ${REDIS_CONNECT_TIMEOUT:2s}
      timeout: ${REDIS_COMMAND_TIMEOUT:3s}
      client-type: lettuce
```

Các placeholder `${...}` của Spring được resolve từ environment. Không đặt mật khẩu production trực tiếp trong YAML được commit; dùng secret manager, Kubernetes Secret hoặc hệ thống cấp credentials của tổ chức.

**Chú ý cấu hình rỗng:** `username: ${REDIS_USERNAME:}` chỉ phù hợp nếu client/server chấp nhận cấu hình username rỗng (ví dụ Redis chỉ xác thực user mặc định). Trong hệ thống dùng Redis ACL, nên cấp username/password rõ ràng và kiểm thử. Tránh đưa secret vào startup logs, Actuator `/env` hay exception detail.

### 4.2. Spring Boot chạy trên host hay trong container?

Hai cách chạy không dùng cùng hostname:

- App chạy trên **máy phát triển**, Redis trong Compose có `ports: ["6379:6379"]`: app thường kết nối `localhost:6379`.
- App chạy **cùng Compose network**, Redis có service name `redis`: app thường kết nối `redis:6379` và không cần expose port cho giao tiếp giữa container.
- App chạy ở Kubernetes/cloud: host/port do Service DNS, Redis endpoint hoặc connection details cấp.

Đừng lấy hostname `redis` của Docker Compose để dùng từ IDE chạy trên host nếu máy không resolve được tên đó. Cũng đừng dùng `localhost` trong app container nếu Redis nằm ở container khác: `localhost` lúc đó chỉ container ứng dụng.

## 5. Redis URL và độ ưu tiên so với các property riêng lẻ

Spring Boot hỗ trợ cấu hình Redis connection URL cho kết nối phù hợp:

```yaml
spring:
  data:
    redis:
      url: ${REDIS_URL}
      connect-timeout: 2s
      timeout: 3s
```

Ví dụ URL (không chứa secret thật):

```text
redis://localhost:6379/0
rediss://user:password@redis.example.org:6380/0
```

- `redis://` là kết nối Redis không dùng TLS.
- `rediss://` thường biểu thị kết nối Redis có TLS, nếu client/provider được cấu hình phù hợp.
- URL có thể bao gồm host, port, database và credentials theo cấu trúc Redis URI được client hỗ trợ.

Trong Spring Boot 3.x, **`spring.data.redis.url` có thể ưu tiên hơn `host`, `port`, `username` và `password`** trong cấu hình kết nối auto-configured. Nếu vừa đặt URL vừa đặt property riêng lẻ rồi thấy app kết nối “sai”, hãy kiểm tra thực tế bean `RedisConnectionFactory` và giá trị URL đã được nạp.

Nên chọn **một nguồn sự thật**: hoặc URL, hoặc host/port/auth fields, trừ khi có lý do rõ ràng. Đừng in URL chứa password vào log, metric tag hoặc exception message. Đối với Sentinel và Cluster, sử dụng nhóm property topology tương ứng thay vì giả định URL standalone biểu diễn đầy đủ các node/chiến lược failover.

## 6. Phân biệt connect-timeout, command timeout và deadline nghiệp vụ

Một câu hỏi phổ biến: “Đã đặt `timeout=2s` mà vì sao HTTP request vẫn mất hơn 2 giây?”

Vì một luồng nghiệp vụ có nhiều pha:

```mermaid
flowchart LR
    A["HTTP request"] --> B["Lấy connection / connect Redis"]
    B --> C["Thực thi lệnh Redis"]
    C --> D["Đọc DB hoặc gọi HTTP downstream"]
    D --> E["Ghi trạng thái / trả response"]
    F["connect-timeout"] -.-> B
    G["timeout (Redis command)"] -.-> C
    H["Deadline của HTTP/business flow"] -.-> E
```

### 6.1. Connect timeout

`spring.data.redis.connect-timeout` giới hạn một nỗ lực **kết nối** tới Redis. Nó không bảo đảm tổng thời gian request chỉ bằng giá trị đó. DNS resolution, TLS handshake, connection pool wait và các bước retry/failover có thể tác động đến tổng latency tùy client/transport.

Ví dụ `connect-timeout: 2s` không có nghĩa service chỉ đợi tối đa 2 giây cho **mọi thao tác** khi Redis down: cơ chế retry hoặc số bước gọi trong luồng vẫn có thể làm thời gian lâu hơn.

### 6.2. Redis command timeout

`spring.data.redis.timeout` kiểm soát thời gian chờ command/đọc response của Redis client theo cơ chế Spring Data Redis và client được chọn. Với Lettuce, command timeout khác với connect timeout; một kết nối TCP đã có có thể tiếp tục bị trễ khi Redis xử lý lệnh, đang bị failover hoặc network gặp sự cố.

Timeout command không chứng minh Redis **chưa thực thi lệnh**. Ví dụ client gửi `INCR orders:counter`, Redis đã tăng counter nhưng response bị thất lạc. Retry ngay cùng `INCR` sẽ tăng thêm lần nữa. Đây là khác biệt cốt lõi giữa lỗi transport và kết quả nghiệp vụ.

### 6.3. Deadline toàn luồng

Một HTTP endpoint gọi Redis hai lần, database một lần và HTTP downstream một lần có tổng latency lớn hơn từng timeout thành phần. Vì vậy nên phân bổ ngân sách thời gian rõ ràng:

| Hạng mục | Giá trị minh họa | Ghi chú |
| --- | --- | --- |
| Redis connect timeout | 1 giây | Giới hạn thiết lập connection |
| Redis command timeout | 2 giây | Giới hạn thao tác Redis |
| HTTP downstream timeout | 3 giây | Phải tùy upstream |
| Deadline HTTP tổng | 5 giây | Có thể nhỏ hơn tổng worst-case khi có retry/parallelism |
| Retry budget | 0–2 lần theo loại thao tác | Không retry vô hạn |

Các giá trị trên **không phải khuyến nghị cố định** cho production. Cần đo p95/p99 latency, network hops, cluster failover behavior và SLA trước khi chốt.

### 6.4. Reactive Redis và timeout

Nếu dùng `ReactiveRedisTemplate` với Lettuce, thao tác trả `Mono`/`Flux`; có thể đặt `timeout(Duration)` trên publisher tại tầng nghiệp vụ để giới hạn thời gian chờ tín hiệu. Nhưng timeout reactive có thể **hủy subscription của client mà không hủy một command Redis đã được server thực thi**. Hãy thiết kế idempotency và đối soát tương tự kiểu blocking.

Đừng đặt timeout vô hạn hoặc quá dài rồi để thread HTTP, executor hoặc message listener mắc kẹt trong lúc Redis có sự cố.

## 7. Lettuce và Jedis: chọn client theo mô hình thực thi

Spring Data Redis có thể sử dụng **Lettuce** hoặc **Jedis**. Trong các dự án Spring Boot 3.x thông dụng, Lettuce là lựa chọn mặc định khi dùng starter Redis.

| Đặc điểm | Lettuce | Jedis |
| --- | --- | --- |
| Mô hình client | Netty, hỗ trợ API đồng bộ/bất đồng bộ và reactive | Client đồng bộ truyền thống, có pool tùy cách dùng |
| `RedisConnectionFactory` phổ biến | `LettuceConnectionFactory` | `JedisConnectionFactory` |
| Tích hợp Reactive Redis | Phù hợp cho Spring Data Redis reactive | Không thay thế reactive Lettuce path |
| Connection sharing | Lettuce hỗ trợ chia sẻ connection theo cấu hình; không luôn cần pool | Pool thường quan trọng với kết nối đồng thời |
| Kết nối Cluster/Sentinel | Có hỗ trợ theo client/configuration | Có hỗ trợ theo client/configuration và version |
| Khi cân nhắc | Đa số app Boot, reactive hoặc mixed workloads | Có ràng buộc thư viện/cấu hình cụ thể cần Jedis |

Chọn Lettuce tường minh:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      connect-timeout: 2s
      timeout: 3s
```

Để dùng Jedis, phải có dependency Jedis tương thích và cấu hình:

```yaml
spring:
  data:
    redis:
      client-type: jedis
      connect-timeout: 2s
      timeout: 3s
```

Chỉ đổi property sang `jedis` nhưng classpath không có Jedis **không tự tải dependency**. Trong một số project cần loại bỏ các cấu hình Lettuce chuyên biệt và kiểm tra bean factory đang dùng. Trước khi chuyển client production, đo lại latency, socket usage, pool saturation, connection leak và hành vi failover.

**Không đánh đồng “Jedis là blocking” với “Lettuce luôn non-blocking”.** Sử dụng `RedisTemplate` trong Spring MVC vẫn là API đồng bộ ở phía gọi dù bên dưới là Lettuce. Muốn reactive end-to-end, cần sử dụng reactive APIs và tránh bước blocking khác trong chain.

## 8. Lettuce pool: cần hay không và cấu hình thế nào?

Một cách hiểu sai thường gặp là “cứ có nhiều HTTP requests thì phải bật pool Redis lớn”. Lettuce có khả năng dùng chung một số connection phù hợp; mở nhiều connection không mặc nhiên làm hiệu năng cao hơn.

Pool có thể hữu ích cho các đường thực thi cần kết nối chuyên biệt, transaction/blocking operations hoặc chính sách tách workload. Cần đánh giá thực nghiệm trước khi bật.

Để cấu hình pooling trong Boot 3.x khi các dependency pool phù hợp có mặt, ví dụ:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-pool2</artifactId>
</dependency>
```

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      lettuce:
        pool:
          enabled: true
          max-active: 16
          max-idle: 8
          min-idle: 0
          max-wait: 500ms
```

Ý nghĩa:

- `max-active`: số kết nối có thể được pool cấp phát đồng thời theo cấu hình pool.
- `max-idle` và `min-idle`: giới hạn số kết nối idle.
- `max-wait`: thời gian chờ lấy được connection từ pool, **khác** Redis command timeout.
- `enabled`: yêu cầu bật pooling ở những phiên bản Boot hỗ trợ thuộc tính tương ứng.

Trong ứng dụng nhiều instance, 16 connection mỗi instance x 20 instance đã có thể tạo 320 kết nối; Redis server, NAT/proxy và network policy cần chịu được tổng tải đó. Tránh tăng `max-active` chỉ để chữa timeout do Redis server xử lý chậm hoặc command quá nặng.

Nếu sử dụng Jedis, cấu hình pool nằm dưới `spring.data.redis.jedis.pool.*` với các thuộc tính tương ứng khi được hỗ trợ; không copy nguyên `lettuce.pool` sang `jedis.pool` mà chưa kiểm tra version/properties.

## 9. Cấu hình TLS, xác thực Redis ACL và secret

Redis có thể được cung cấp trong môi trường managed với TLS bắt buộc, ví dụ cổng 6380. Spring Boot 3.x hỗ trợ cấu hình SSL cho Redis:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6380}
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      connect-timeout: 2s
      timeout: 3s
```

Một số bản Spring Boot 3.x còn hỗ trợ **SSL bundles** để dùng trust/key material được quản lý tập trung, ví dụ:

```yaml
spring:
  ssl:
    bundle:
      jks:
        redis-client:
          truststore:
            location: classpath:certs/redis-truststore.p12
            password: ${REDIS_TRUSTSTORE_PASSWORD}
            type: PKCS12
  data:
    redis:
      ssl:
        enabled: true
        bundle: redis-client
```

Đây là ví dụ cấu trúc cấu hình, **không kèm certificate thật**; `certs/redis-truststore.p12` phải được provision riêng và phân phối an toàn. Khi dùng Spring Boot version khác hoặc provider yêu cầu mTLS, cần kiểm tra chính xác SSL bundle support, key store/trust store và dạng credentials mong muốn.

**Không tắt hostname/certificate verification** chỉ để “cho kết nối qua”. Nếu TLS handshake thất bại, xác minh CA/truststore, host name, thời gian hệ thống, SNI và server certificate chain. Không in private key, token hoặc Redis password vào logs.

### 9.1. Redis ACL khác network access

Một TCP connection đến được Redis không có nghĩa đã được phép `GET`/`SET`. Redis ACL có thể giới hạn command/key prefix:

- User chỉ đọc cache: cần quyền đọc đúng key space, không nên cấp mọi lệnh quản trị.
- Worker dùng trạng thái idempotency: cần quyền ghi key phù hợp và atomic operations cần thiết.
- Health check: có thể yêu cầu `PING`, nhưng tài khoản production bị giới hạn có thể cần health policy riêng.

Nếu nhận lỗi `NOAUTH`/`WRONGPASS`/`NOPERM`, không xử lý như cache miss. Cần kiểm tra user/password, ACL, TLS endpoint và key namespace. Trong production, Redis thường nằm trong private network và được bảo vệ bằng authentication/ACL, TLS nếu hạ tầng yêu cầu và giới hạn quyền theo service.

## 10. Redis Sentinel: phát hiện primary khi failover

Với **Redis Sentinel**, ứng dụng không chỉ có một host/port server cố định. Client kết nối tới các Sentinel nodes, hỏi service name của primary rồi tìm Redis instance đang giữ vai trò primary.

Ví dụ cấu hình cấu trúc thường dùng:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
        nodes:
          - sentinel-1.example.org:26379
          - sentinel-2.example.org:26379
          - sentinel-3.example.org:26379
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      connect-timeout: 2s
      timeout: 3s
```

`mymaster` là **tên master do Sentinel quản lý**, không phải hostname. Các giá trị host Sentinel minh họa cần được thay bằng hạ tầng thực.

Điểm cần lưu ý:

1. `spring.data.redis.sentinel.nodes` là danh sách **Sentinel endpoints**, không phải các Redis data nodes.
2. Quy tắc credentials của Sentinel **có thể khác** Redis data nodes; ở các bản Boot/client có hỗ trợ, kiểm tra các thuộc tính `sentinel.username`/`sentinel.password` nếu Sentinel yêu cầu xác thực riêng.
3. Khi failover, client có thể cần phát hiện primary mới/reconnect; các command đang chạy vẫn có thể timeout hoặc thất bại.
4. Sentinel không tạo “transaction xuyên failover”: một response mất sau khi write được primary cũ chấp nhận có thể làm trạng thái chưa rõ ràng, cần idempotency hoặc đối soát.
5. Test cần mô phỏng Sentinel failover và đo thời gian phục hồi, không chỉ test với một Redis standalone trên localhost.

Đừng cấu hình cả `sentinel` và `cluster` với kỳ vọng client tự kết hợp chúng. Đây là hai topology Redis khác nhau và cần lựa chọn theo deployment thực tế.

## 11. Redis Cluster: node list, redirection và database index

Trong **Redis Cluster**, dữ liệu được phân vùng theo hash slots giữa các primary nodes. Client cần cluster-aware routing và có thể nhận redirection như `MOVED`/`ASK` khi topology thay đổi.

Ví dụ:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-1.example.org:6379
          - redis-2.example.org:6379
          - redis-3.example.org:6379
        max-redirects: 5
      connect-timeout: 2s
      timeout: 3s
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
```

Các node khai báo ở trên thường là **seed nodes** để client khám phá cluster; đó không phải danh sách đầy đủ mọi node sẽ tồn tại mãi mãi. Mức độ tự cập nhật topology, refresh interval/adaptive refresh và failover phụ thuộc Lettuce/Jedis cùng cấu hình cụ thể.

**Redis Cluster chỉ hỗ trợ database index 0 theo mô hình Redis Cluster thông dụng.** Không đặt `spring.data.redis.database: 1` rồi kỳ vọng việc `SELECT 1` hoạt động như standalone. Phân tách dữ liệu giữa app/tenant bằng key prefix và quyền phù hợp, không bằng logical DB index.

Hạn chế quan trọng khác:

- Multi-key operations có thể yêu cầu các key thuộc **cùng hash slot**.
- Redis key hash tags `{...}` giúp gán các key liên quan vào một slot khi thật sự cần thao tác multi-key.
- Lua scripts/transactions trên nhiều key khác slot có thể thất bại.
- Cluster không bảo đảm atomic transaction với database PostgreSQL hoặc một message broker.
- Cấu hình timeout cần tính đến redirections, reconnect và failover; không đánh đồng “một command 2 giây” với toàn bộ yêu cầu nghiệp vụ.

Ví dụ key có hash tag:

```text
order:{ord-1024}:status
order:{ord-1024}:attempts
```

Hai key này thường được hash cùng slot nhờ phần trong dấu ngoặc nhọn. Không sử dụng hash tag tùy tiện làm các key nóng dồn vào một slot; cần hiểu mô hình phân tải.

## 12. Service Connections và nguồn cấu hình ưu tiên

Trong môi trường local, `spring-boot-docker-compose` hoặc Spring Boot Testcontainers có thể tạo **RedisConnectionDetails** từ container Redis đã được nhận diện. Khi bean connection details có mặt, auto-configuration có thể lấy endpoint/credentials từ đó **thay cho một số thuộc tính `spring.data.redis.*`**.

Ví dụ Compose:

```yaml
services:
  redis:
    image: redis:7
    ports:
      - "6379"
```

Docker có thể ánh xạ container port 6379 thành host port ngẫu nhiên, chẳng hạn 49170. Spring Boot phát hiện mapped port và cung cấp connection details để Redis client kết nối đúng host port.

**Tình huống gây nhầm:** bạn đã cấu hình `spring.data.redis.host=localhost` và `port=6379` nhưng app lại kết nối mapped port 49170. Điều đó có thể là **hành vi đúng** khi Compose service connection được ưu tiên.

Khi cần kiểm tra:

1. Có module Docker Compose/Testcontainers trên runtime classpath không?
2. Có bean `RedisConnectionDetails` trong context không?
3. Có bean `RedisConnectionFactory` custom đang bỏ qua auto-configuration không?
4. App chạy trên host hay trong container, mapped port là bao nhiêu?
5. Test và production có dùng cùng nguồn connection details không?

Không nên vô hiệu hóa connection details chỉ để ép app dùng `localhost:6379` nếu Compose đang map port động. Chọn một cơ chế rõ cho từng môi trường: local Compose, test container hoặc production endpoint qua secret/config.

## 13. Spring Cache và RedisTemplate: hai tầng cấu hình khác nhau

Một lỗi phổ biến là dùng sai namespace:

- **`spring.data.redis.*`**: cấu hình **kết nối Redis client**—host, port, username, password, TLS, connect timeout, command timeout, topology, pool.
- **`spring.cache.redis.*`**: cấu hình **cache behavior** của `RedisCacheManager` khi Spring Cache dùng Redis—TTL, null caching, key prefix, cache names, v.v.

Ví dụ:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
  cache:
    type: redis
    redis:
      time-to-live: 5m
      cache-null-values: false
      use-key-prefix: true
```

`spring.data.redis.timeout: 3s` **không phải** TTL ba giây của cache. `spring.cache.redis.time-to-live: 5m` **không phải** timeout kết nối Redis.

Tương tự, khi gọi `StringRedisTemplate.opsForValue().set(key, value, Duration.ofMinutes(5))`, TTL do **command của bạn** yêu cầu; nó không tự lấy từ `spring.cache.redis.time-to-live`. Nếu dùng RedisTemplate với serializer tùy chỉnh, phải thiết kế version key/value và tránh deserialize dữ liệu không tin cậy bằng serializer nguy hiểm.

### 13.1. Ví dụ StringRedisTemplate với TTL tường minh

```java
import java.time.Duration;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class InventorySnapshotStore {

    private final StringRedisTemplate redis;

    public InventorySnapshotStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String sku, String json) {
        redis.opsForValue().set(
            "inventory:snapshot:v1:" + sku,
            json,
            Duration.ofMinutes(5)
        );
    }

    public String find(String sku) {
        return redis.opsForValue().get(
            "inventory:snapshot:v1:" + sku
        );
    }
}
```

Ở ví dụ này, `json` là payload JSON đã được serialize theo contract của ứng dụng; nên validate và đặt giới hạn kích thước khi ghi/đọc. Key prefix có version giúp tránh xung đột khi DTO đổi cấu trúc.

**Về tính đúng đắn:** cache snapshot tồn kho có thể stale. Để tạo reservation/đặt hàng thật, owner service phải xác thực trạng thái tồn kho atomically trong transaction/cơ chế đồng bộ phù hợp, thay vì chỉ tin cache.

## 14. Phân loại lỗi kết nối và chính sách phục hồi

Trong một hệ tích hợp, lỗi Redis cần phân biệt theo nguồn gốc:

| Triệu chứng | Nguyên nhân thường gặp | Hành động phù hợp |
| --- | --- | --- |
| Connection refused | Sai host/port, server chưa chạy, firewall | Xác nhận endpoint, port mapping, network policy |
| Connect timeout | Network không thiết lập được kết nối đúng hạn | Xem DNS, route, TLS, connection count, outage |
| Command/read timeout | Redis chậm, network nghẽn, failover, command nặng | Đo slowlog/latency, xem pool và request deadline |
| NOAUTH / WRONGPASS | Thiếu/sai credential | Kiểm tra secret/ACL, không retry nóng vô hạn |
| NOPERM | ACL không cho phép command/key | Sửa policy cấp quyền, không dùng fallback che lỗi |
| TLS handshake error | CA/truststore/SNI/cert mismatch | Sửa trust chain và endpoint; không tắt verify |
| MOVED / ASK bất thường | Cluster client/topology sai | Xác minh cluster-aware client, node reachability |
| READONLY | Ghi vào replica, failover hoặc topology stale | Kiểm tra primary routing, retry có giới hạn |
| Serialization failure | DTO/serializer/schema không tương thích | Cố định schema/version, migration hoặc cache invalidation |
| Redis reachable nhưng lệnh nghiệp vụ sai | Key prefix, TTL, type hoặc command semantics | Xác minh contract, test theo key pattern |

Trong Spring, exception có thể được chuyển sang các subtype của `DataAccessException` như `RedisConnectionFailureException`, `QueryTimeoutException` hoặc exception từ client/thư viện tùy thao tác. Không viết logic recovery chỉ bằng cách so sánh chuỗi message của exception.

### 14.1. Redis timeout không đồng nghĩa “lệnh chưa chạy”

Xét thao tác:

```text
Client -> Redis: INCR notification:sent-counter
Redis thực thi tăng counter
Network làm thất lạc response
Client timeout
```

Retry cùng lệnh sẽ đếm thêm một lần. Với thao tác tạo trạng thái idempotency, lưu checkpoint hoặc phát sự kiện, nên dùng **business id ổn định** và atomic conditional operations nếu phù hợp. Nếu cần bảo đảm trạng thái giữa database và Redis, transaction local của DB **không tự bao phủ Redis**.

### 14.2. Fallback cache và fail-open/fail-closed

Nếu Redis chỉ là cache cho dữ liệu đọc không nhạy cảm, có thể fallback xuống DB/HTTP provider **với concurrency limit** khi Redis lỗi. Nhưng:

- Fallback hàng loạt có thể tạo cache stampede, đánh sập nguồn dữ liệu thật.
- Redis dùng cho idempotency, rate limiting hoặc distributed lock không còn là cache tùy chọn; fallback mở có thể gây side effect trùng hoặc vượt quota.
- Dữ liệu phân quyền, giá quan trọng hoặc tồn kho cần chính sách stale data rõ ràng.
- Retry phải có budget, backoff và circuit breaker phù hợp; không retry mọi lỗi khi ACL sai hoặc TLS hỏng.

## 15. Kiểm thử kết nối, timeout và lỗi trên Redis thật

Unit test một repository với mock `StringRedisTemplate` kiểm tra cách gọi method, nhưng **không kiểm tra kết nối, serializer, TLS, Redis command semantics hoặc timeout**. Đối với bài học cấu hình, nên có integration test dùng Redis thật trong môi trường kiểm soát.

### 15.1. Redis với Testcontainers và DynamicPropertySource

Ví dụ với JUnit 5, Spring Boot Test và Testcontainers; project cần dependency `org.testcontainers:junit-jupiter` cùng những dependency Spring Boot phù hợp.

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
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

@Testcontainers
@SpringBootTest
class RedisConnectionIntegrationTest {

    @Container
    static GenericContainer<?> redis =
        new GenericContainer<>(DockerImageName.parse("redis:7.2"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> redis.getMappedPort(6379)
        );
        registry.add("spring.data.redis.connect-timeout", () -> "1s");
        registry.add("spring.data.redis.timeout", () -> "2s");
    }

    @Autowired
    StringRedisTemplate template;

    @Test
    void writesAndReadsValueWithTtl() {
        String key = "test:redis:configuration:sku-123";

        template.opsForValue().set(key, "available", Duration.ofSeconds(30));

        assertThat(template.opsForValue().get(key))
            .isEqualTo("available");

        Long ttl = template.getExpire(key);
        assertThat(ttl).isNotNull();
        assertThat(ttl).isPositive();
    }
}
```

**Điều kiện test:** Docker daemon chạy được, image Redis test được kéo, Redis starter có trên classpath và không có custom connection factory/`RedisConnectionDetails` khác ghi đè property này. Nếu ứng dụng có service connection từ Compose hoặc testcontainers bằng bean khác, cần đảm bảo không có hai nguồn endpoint mâu thuẫn.

Dùng namespace riêng và TTL ngắn để tránh đụng dữ liệu của test khác. Test này xác minh I/O thực và TTL, **không tự kiểm tra timeout** khi Redis mất mạng.

### 15.2. Thiết kế test timeout và failover

Nhóm test quan trọng:

1. **Host/port sai**: connect timeout hữu hạn, exception được phân loại, không chờ vô hạn.
2. **Lệnh chậm/Redis bị treo**: command timeout có tác dụng, số retry đúng policy.
3. **Redis restart**: client reconnect, request đang chạy báo lỗi rõ và recovery có kiểm soát.
4. **Sai credentials/ACL**: không fallback hoặc retry vô hạn che lỗi bảo mật.
5. **TLS trust failure**: ứng dụng fail rõ, không tự bỏ certificate verification.
6. **Redis Cluster failover/MOVED**: client phát hiện topology mới; key routing đúng.
7. **Sentinel switch-over**: phát hiện primary mới và bảo toàn semantics business.
8. **Nhiều instance**: connection limits, pool saturation và cache invalidation chung.
9. **Timeout sau write thành công**: thao tác side effect không bị chạy lặp ngoài ý muốn.

Có thể dùng Toxiproxy hoặc một network fault-injection tool trong integration test để gây timeout được kiểm soát. Đừng dùng `Thread.sleep` ngẫu nhiên để đo timeout hoặc ép production Redis ngừng hoạt động trong bộ test tự động.

### 15.3. Kiểm tra đúng phiên bản property

Khi cập nhật từ Boot 2.x sang 3.x, hãy viết một test application context xác minh `RedisConnectionFactory` có type, endpoint và timeout dự kiến. Đừng dựa vào việc `application.yml` “trông hợp lệ”: property sai prefix có thể bị bỏ qua, dẫn tới client dùng `localhost:6379` mặc định.

## 16. Quan sát, bảo mật và vận hành thực tế

Để xem cấu hình hoạt động, có thể kiểm tra:

- **Startup/conditions**: ứng dụng dùng `LettuceConnectionFactory` hay `JedisConnectionFactory`; có bean custom/`RedisConnectionDetails` không.
- **Redis client**: lệnh/connection latency, timeout, error rate, pool wait và active connections nếu được instrument.
- **Redis server**: memory usage, evictions, connected clients, command latency, slowlog, failover và replication health.
- **Spring Cache**: hit/miss ratio, TTL, cache key cardinality, stale entries; kiểm tra metrics phù hợp provider.
- **Business flows**: request p95/p99, consumer lag, retry count, duplicate event count, số lần fallback và số job bị kẹt.

Khi dùng Spring Boot Actuator, có thể có Redis health indicator và metrics khi dependency/configuration phù hợp. Một Redis health check “UP” chỉ chứng minh mức kết nối/probe được cấu hình; không bảo đảm mọi key schema, ACL hoặc lệnh nghiệp vụ đều đúng.

### 16.1. Checklist tìm lỗi khi app không kết nối Redis

1. **Xác minh nơi app chạy**: host, Docker Compose container hay Kubernetes.
2. **Xem endpoint được resolve**: URL, host/port, Sentinel/Cluster, service connection precedence.
3. **Kiểm tra Redis instance thực tế**: server nghe port, DNS, firewall, TLS/ACL.
4. **Kiểm tra client implementation**: Lettuce/Jedis và version tương thích.
5. **Đối chiếu connect timeout, command timeout và deadline HTTP/message flow**.
6. **Kiểm tra pool và số instance**: số connection tổng, queue wait, thread saturation.
7. **Phân loại lỗi**: transport, auth, ACL, TLS, serialization, topology, wrong database.
8. **Kiểm tra hậu quả nghiệp vụ**: idempotency, stale cache, retry và trạng thái DB/broker.

Tránh log password, full Redis URL chứa credentials, access tokens, raw payload chứa PII hoặc cache keys chứa thông tin nhạy cảm. Với metric labels, không dùng key Redis tùy ý làm label vì cardinality tăng rất nhanh.

### 16.2. Cấu hình profile rõ cho từng môi trường

```yaml
# application-dev.yml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 1s
      timeout: 2s
```

```yaml
# application-prod.yml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6380}
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      connect-timeout: 2s
      timeout: 3s
```

Các đoạn trên là **minh họa của hai file cấu hình khác nhau**, không phải đề xuất ghi chúng vào cùng một YAML không có profile. Trong hệ thống managed Redis, có thể cần URL, Cluster/Sentinel settings, SSL bundle và timeout khác; kiểm tra contract vận hành của nhà cung cấp.

## 17. Tình huống tổng hợp: Redis trong luồng Order → DB → Event

Giả sử Order Service nhận HTTP request, đọc snapshot tồn kho từ Redis, ghi order trong PostgreSQL và phát `OrderCreated` qua broker:

```mermaid
flowchart TD
    A["POST /orders"] --> B["Đọc Redis snapshot"]
    B --> C["Kiểm tra nghiệp vụ ở owner service"]
    C --> D["DB transaction: order + outbox"]
    D --> E["Outbox publisher"]
    E --> F[("Broker")]
    F --> G["Consumer inbox / idempotency"]
    G --> H["Redis cache invalidation (khi phù hợp)"]
```

Một cấu hình production ban đầu có thể là:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6380}
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      client-type: lettuce
      connect-timeout: 2s
      timeout: 3s
  cache:
    type: redis
    redis:
      time-to-live: 2m
      cache-null-values: false
```

**Đường lỗi cần mô tả rõ:**

- Redis timeout khi đọc snapshot: có thể fallback sang source of truth nếu policy cho phép; không tự trả “tồn kho = 0” cho mọi lỗi.
- Redis timeout sau lệnh ghi trạng thái idempotency: cần xác minh lệnh đã chạy hay chưa và dùng key/operation idempotent nếu có thể.
- PostgreSQL commit nhưng broker publish thất bại: outbox cho phép retry mà không phát sự kiện từ transaction chưa commit.
- Consumer nhận lại event: inbox/deduplication ngăn xử lý lặp.
- Redis failover hoặc key schema đổi khi rolling deploy: test kết nối, serializer và điều kiện nhất quán theo nghiệp vụ.

### Checklist trước khi triển khai

- [ ] Dùng `spring-boot-starter-data-redis` đúng phiên bản và có Redis server thực?
- [ ] Chọn đúng standalone/URL, Sentinel hoặc Cluster và không trộn topology tùy tiện?
- [ ] Địa chỉ host/port đúng với nơi app chạy, kể cả Docker mapped port/Service Connection?
- [ ] Credential/ACL/TLS được quản lý an toàn và test lỗi xác thực?
- [ ] Có `connect-timeout`, `timeout` và deadline tổng; đã thử failure injection?
- [ ] Đã xác định Lettuce/Jedis, nhu cầu pool và giới hạn số connection?
- [ ] Không nhầm `spring.data.redis.timeout` với `spring.cache.redis.time-to-live`?
- [ ] Key namespace, TTL, serializer, schema version và quyền theo tenant rõ ràng?
- [ ] Retry không biến non-idempotent command thành side effect lặp?
- [ ] Có test Redis thật, reconnect/failover, logging/metrics và kế hoạch xử lý outage?

**Kết luận:** `spring.data.redis.*` là vùng cấu hình chủ đạo để Spring Boot tạo kết nối Redis: endpoint, ACL credentials, TLS, client, topology và timeout. **`connect-timeout`** giới hạn thiết lập kết nối, còn **`timeout`** quản lý chờ command theo client; cả hai không phải SLA tổng hay TTL của cache. Trong một luồng tích hợp Spring Boot, phải kết hợp cấu hình này với quản lý contract dữ liệu, cache invalidation, transaction, retry/idempotency, kiểm thử trên Redis thật và quan sát lỗi để Redis giúp tăng hiệu năng mà không làm sai nghiệp vụ.
