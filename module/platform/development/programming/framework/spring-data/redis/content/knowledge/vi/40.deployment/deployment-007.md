# Nâng cấp Redis Server, Spring Data Redis và trình điều khiển

## 1. Vì sao nâng cấp Redis không đơn giản là đổi số phiên bản?

Một ứng dụng Spring Boot thường không nói chuyện trực tiếp với Redis Server. Luồng thực tế là:

```text
Business application
    |
    +-- Spring Cache / Redis Repository / RedisTemplate
    |
    v
Spring Data Redis
    |
    v
Redis driver
    +-- Lettuce hoặc Jedis
    |
    v
RESP protocol + TCP/TLS
    |
    v
Redis Server
    +-- Standalone
    +-- Sentinel-managed primary/replica
    +-- Redis Cluster
    +-- Managed Redis service
    |
    v
Dữ liệu Redis, RDB/AOF, replication, ACL, scripts, Streams...
```

Một thay đổi phiên bản ở **bất cứ tầng nào** cũng có thể tác động đến cách các tầng còn lại hoạt động:

- Redis Server có thể thay đổi command behavior, persistence format, ACL, clustering, default configuration hoặc cơ chế vận hành.
- Spring Data Redis có thể thay đổi API Java, serializers, mapping, Redis Repository, cache, reactive support hoặc dependency requirements.
- Lettuce/Jedis có thể thay đổi connection initialization, pooling, timeout, auto-reconnect, topology discovery, RESP negotiation, TLS hay exception behavior.
- Spring Boot BOM có thể quản lý một tập phiên bản liên quan; override một dependency có thể phá vỡ bộ dependency đã được kiểm thử.
- Java runtime/JDK hoặc Spring Framework version có thể đặt ra giới hạn tương thích cho thư viện mới.
- Giá trị hiện có trong Redis vẫn phải được code mới **deserialize đúng**, chứ không chỉ kết nối thành công.

Vì vậy, nâng cấp cần được coi là **một thay đổi hệ thống có trạng thái** (*stateful deployment*), không phải một thao tác tìm-thay số phiên bản.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xây dựng ma trận tương thích giữa Redis Server, Spring Boot, Spring Data Redis, Lettuce/Jedis và JDK.
2. Phân biệt cập nhật dependency Java với nâng cấp Redis Server.
3. Đọc release notes/migration guides theo những loại breaking changes thực sự ảnh hưởng ứng dụng.
4. Xác định rủi ro với Redis key format, serialization, cache, repository, Lua, Pub/Sub, Streams, TTL và Redis Cluster.
5. Lập kế hoạch nâng cấp Redis standalone, Sentinel và Cluster theo mức downtime/rủi ro khác nhau.
6. Chuẩn bị backup, restore test và chiến lược rollback không giả định RDB/AOF backward-compatible.
7. Tạo bộ integration, load, failure và compatibility tests cho cả bản cũ lẫn bản mới.
8. Triển khai canary theo các chỉ số có ngưỡng dừng rõ ràng.
9. Thiết kế runbook khi reconnect, failover, authentication, command routing hoặc data migration lỗi.
10. Báo cáo tình trạng nâng cấp bằng bằng chứng đo và khả năng khôi phục thay vì chỉ ghi “deployment succeeded”.

---

## 2. Ba nhóm nâng cấp phải phân biệt

### 2.1. Nâng cấp Redis Server

Ví dụ ở mức khái niệm:

```text
Redis Server version A
    |
    v
Redis Server version B
```

Ảnh hưởng có thể liên quan:

- Server hiểu command nào.
- RESP2/RESP3 và cách client bắt tay.
- ACL và authentication.
- Tính năng/giới hạn của Redis Cluster.
- RDB/AOF read/write format và persistence.
- Replication protocol, failover, resharding.
- Configuration names/default values.
- Memory behavior, performance, eviction, latency.
- Redis Modules hoặc features của managed provider.

Nâng cấp server **không tự cập nhật Spring Data Redis hoặc driver** trên các application instances.

### 2.2. Nâng cấp Spring Data Redis

Ví dụ:

```text
spring-data-redis version X
    |
    v
spring-data-redis version Y
```

Ảnh hưởng có thể liên quan:

- API `RedisTemplate`, `RedisOperations`, `ReactiveRedisTemplate`.
- CacheManager defaults và serializers.
- Redis Repository mapping/index/TTL.
- Spring Data Commons, Spring Framework, Reactor.
- Định nghĩa interfaces, method signatures, deprecations.
- Exception translation và integration behavior.
- Cấu hình connection factories hoặc transaction support.

Một bản Spring Data Redis mới **không tự cài Redis Server mới**. Và một server Redis mới không có nghĩa `spring-data-redis` cũ đã được kiểm thử hoặc hỗ trợ chính thức.

### 2.3. Nâng cấp driver Lettuce/Jedis

Driver chịu trách nhiệm:

- Mở TCP/TLS connections.
- Encode/decode RESP commands và replies.
- Authentication, HELLO/capability negotiation.
- Timeouts, reconnect và command queue.
- Topology discovery/redirect ở Cluster.
- Support Sentinel, pipeline, transaction.
- Async/reactive APIs, client threading.
- Command availability và result decoding.

Một thay đổi driver có thể ảnh hưởng ứng dụng **ngay cả khi Redis Server không đổi**.

### 2.4. Nâng cấp Spring Boot/JDK đi kèm

Đôi khi không thể chỉ nâng `spring-data-redis` vì release mới yêu cầu Spring Framework/Data Commons hoặc JDK mới hơn.

Một nâng cấp Spring Boot major version có thể kéo theo:

```text
Spring Boot
  -> Spring Framework
  -> Spring Data release train
  -> Spring Data Redis
  -> Lettuce/Jedis compatible range
  -> Reactor / Micrometer / Jakarta libraries
  -> Java runtime requirement
```

Ví dụ sự chuyển đổi hệ sinh thái Java từ các API `javax.*` sang `jakarta.*` ở những phiên bản Spring major là một loại breaking change rộng hơn Redis. Không nên coi nó như một sửa đổi Redis thuần túy.

---

## 3. Nguyên tắc số một: kiểm tra compatibility matrix chính thức

**Không có công thức “Redis mới nhất + Spring Data mới nhất + driver mới nhất chắc chắn chạy tốt”.**

Một bộ phiên bản đúng cần đồng thời thỏa:

```text
JDK được Spring Boot/Spring Data hỗ trợ
AND
Spring Framework/Data Commons đồng bộ release train
AND
Spring Data Redis hỗ trợ driver/runtime theo thông tin công bố
AND
Driver giao tiếp được Redis Server/protocol/topology
AND
Application sử dụng những APIs/commands phù hợp
AND
Managed Redis vendor cho phép các tính năng đó
```

### 3.1. Mẫu ma trận trước nâng cấp

| Tầng | Production hiện tại | Phiên bản đích | Nguồn xác nhận |
|---|---|---|---|
| JDK | Điền phiên bản thực | Điền | Spring Boot/JDK support policy |
| Spring Boot | Điền | Điền | Release notes, support matrix |
| Spring Framework | BOM hiện tại | BOM đích | Spring Boot dependency management |
| Spring Data release train | Điền | Điền | Spring Data release notes |
| Spring Data Redis | Điền | Điền | Spring Data Redis reference |
| Lettuce | Điền nếu dùng | Điền | Lettuce release notes |
| Jedis | Điền nếu dùng | Điền | Jedis compatibility notes |
| Redis Server | Điền | Điền | Redis upgrade/release notes |
| Redis topology | Standalone/Sentinel/Cluster | Dự kiến | Redis/admin documentation |
| RESP mode | RESP2/RESP3 theo thực tế | Dự kiến | Driver/server compatibility |
| Security | Password/ACL/TLS | Dự kiến | Redis/security/provider docs |
| Persistence | RDB/AOF/backup | Dự kiến | Redis persistence docs |
| Managed provider | Service/tier/engine | Dự kiến | Vendor compatibility guide |

Không điền phiên bản **theo phỏng đoán**. Cần lấy từ deployment thực tế và tài liệu phiên bản đích tại thời điểm nâng cấp.

### 3.2. Không chỉ hỏi “có kết nối được không?”

Một driver có thể `PING` được Redis nhưng vẫn gặp lỗi khi:

- `XREADGROUP` hoặc `XAUTOCLAIM`.
- Thực thi `EVAL`/`EVALSHA`.
- Dùng `SCAN` ở Cluster.
- Phân tích reply của một command Redis mới.
- Kết nối Sentinel sau failover.
- Dùng Redis ACL user có quyền bị giới hạn.
- Đọc JSON cũ đã lưu bằng serializer khác.
- Gọi Pub/Sub pattern listener hoặc reactive streams.
- Thực thi multi-key operations khi hash slot không hợp lệ.

**Tương thích đường kết nối tối thiểu khác tương thích chức năng ứng dụng.**

---

## 4. Khảo sát hệ thống trước khi chọn phiên bản

Trước khi sửa dependency hoặc thay server, lập inventory.

### 4.1. Server và topology

Trong môi trường được phép, các command thường hữu ích:

```redis
INFO server
INFO replication
INFO persistence
INFO memory
INFO stats
INFO commandstats
```

Với Redis Cluster:

```redis
CLUSTER INFO
CLUSTER NODES
CLUSTER SLOTS
```

Với môi trường hỗ trợ, cũng có thể xem `CLUSTER SHARDS` hoặc interface tương ứng tùy phiên bản.

Ghi:

```text
Redis Server version
Role của từng node
Primary/replica mapping
Slot ownership
Cluster health
Replication offsets/lag
RDB/AOF state
Memory/RSS/evictions
Client connections
Command mix
Load p50/p95/p99 ở app
```

Không đưa `INFO` hoặc `CLIENT LIST` nguyên văn vào tài liệu chia sẻ rộng nếu output chứa địa chỉ nội bộ, usernames hoặc metadata nhạy cảm.

### 4.2. Application và dependency graph

Xác định:

```text
Spring Boot version
Java/JDK runtime
Spring Data Redis jar
Lettuce hoặc Jedis jar
Reactor/Micrometer nếu dùng
commons-pool2 nếu dùng pool
Jackson/serializer libraries
Netty version nếu dùng Lettuce
Spring Data Commons
Custom Redis libraries
```

Điều quan trọng là **resolved dependency versions** trong artifact chạy thật, không chỉ những phiên bản được viết trong build script.

Một BOM hoặc dependency conflict có thể khiến JAR thực tế khác điều developer nghĩ.

### 4.3. Tìm các Redis operations có tính năng đặc biệt

Lập danh sách:

| Nhóm | Các thao tác cần kiểm tra |
|---|---|
| String/TTL | `GET`, `SET`, `MGET`, `MSET`, `EXPIRE`, `PTTL` |
| Hash/Set/ZSet | `HGETALL`, `HSCAN`, `SADD`, `ZRANGE`, index operations |
| Cache | `@Cacheable`, `@CachePut`, `@CacheEvict`, `RedisCacheManager` |
| Repository | `@RedisHash`, `@Indexed`, `@TimeToLive`, entity IDs |
| Transaction | `MULTI`, `EXEC`, `WATCH`, Spring transaction integration |
| Lua | `EVAL`, `EVALSHA`, cached scripts, `RedisScript` |
| Pub/Sub | `SUBSCRIBE`, `PSUBSCRIBE`, listener containers |
| Streams | `XADD`, `XREADGROUP`, `XACK`, `XPENDING`, `XAUTOCLAIM` |
| Cluster | MOVED/ASK, hash tags, multi-key, slot discovery |
| Security | ACL username, password, TLS, certificates |
| Operations | RDB/AOF, memory limits, eviction policy, client limits |

Các thao tác này trở thành **hợp đồng hồi quy** cho bước kiểm thử.

---

## 5. Chọn chiến lược nâng cấp theo rủi ro

Có vài hình thức thường gặp:

### 5.1. Dependency-only upgrade

Giữ Redis Server, nâng Spring Data Redis và/hoặc driver:

```text
Redis Server: giữ nguyên
Spring Boot:  có thể giữ hoặc nâng
Spring Data Redis: X -> Y
Lettuce/Jedis: A -> B
```

Thích hợp khi cần sửa lỗi client, security fixes, JDK compatibility hoặc nâng ứng dụng.

Rủi ro chính: Java compatibility, API changes, serializers, defaults, connection/retry behavior.

### 5.2. Server-only upgrade

Giữ app/client version và thay Redis Server:

```text
Application artifacts: giữ nguyên
Redis Server: version A -> B
```

Thích hợp nếu application driver đã được kiểm tra tương thích cả phiên bản cũ lẫn mới.

Rủi ro: protocol/command/persistence/topology/configuration và đường rollback.

### 5.3. Staged upgrade

Đổi từng tầng theo các chặng được kiểm thử:

```text
Chặng 1: app + driver compatible với Redis A và B
Chặng 2: Redis A -> B
Chặng 3: loại bỏ compatibility code
```

Hoặc một thứ tự khác nếu compatibility matrix và vendor guide yêu cầu.

**Không có thứ tự phổ quát luôn đúng.** Phải chọn sao cho mỗi trạng thái trung gian là một tổ hợp được hỗ trợ:

```text
App old + Redis old
App new + Redis old
App new + Redis new
```

Nếu `App new + Redis old` không được hỗ trợ, không thể sử dụng chặng trung gian đó dù nó trông thuận tiện.

### 5.4. Blue/green với stateful Redis

Với ứng dụng HTTP stateless, blue/green thường đơn giản. Với Redis, hai môi trường có **state khác nhau**.

```text
Blue Redis data   !=   Green Redis data
```

Nếu chỉ dựng Redis mới rồi chuyển endpoint sang green, các writes đang diễn ra trên blue có thể không có ở green.

Blue/green Redis cần kế hoạch:

- Snapshot + catch-up hoặc migration được hỗ trợ.
- Application dual-write có kiểm soát nếu cần.
- Cửa sổ cutover, freeze writes hoặc replication migration theo vendor.
- Conflict resolution.
- Idempotency và xác minh dữ liệu.
- Rollback khi đã có writes trên green.

Không dùng “đổi DNS là rollback xong” như lời bảo đảm cho một database stateful.

---

## 6. Release notes: đọc những gì?

Trước khi đổi version, cần đọc tài liệu công bố **của từng bước nhảy**.

### 6.1. Redis Server

Tập trung vào:

- Supported upgrade paths và yêu cầu intermediate versions.
- Những major breaking changes.
- Deprecated/renamed/removed configuration directives.
- Persistence RDB/AOF format và downgrade restrictions.
- Replication compatibility giữa versions.
- Cluster protocol/failover/resharding changes.
- ACL/security/TLS changes.
- Command availability/semantics.
- Modules/functions/search support nếu sử dụng.
- Performance/memory changes và defaults.
- Behavior khi startup với data files cũ.
- Những thay đổi liên quan Redis distribution/licensing/vendor nếu ảnh hưởng deployment.

### 6.2. Spring Data Redis

Tập trung vào:

- Minimum Java/Spring versions.
- Spring Data release train alignment.
- API signature hoặc package changes.
- CacheManager settings, default serializer/key prefix/TTL.
- Redis Repository mapping/index/TTL semantics.
- Reactive API support.
- ConnectionFactory và transaction behavior.
- Exception translation.
- Support của Redis Server/driver versions.
- Những deprecations cần loại bỏ.

### 6.3. Lettuce/Jedis

Tập trung vào:

- Minimum JDK.
- RESP negotiation.
- Authentication/TLS.
- Cluster topology refresh, MOVED/ASK, redirects.
- Auto-reconnect, command queue, timeout defaults.
- Pooling/connection sharing.
- Async/reactive threading.
- Pub/Sub resubscription.
- Command codec/result decoding.
- Security advisories và dependency vulnerabilities.

### 6.4. Không bỏ qua release train

Nếu dự án dùng Spring Boot starter, nhiều thư viện được Boot BOM chọn thành **một bộ có kiểm thử tích hợp**.

Override một dependency đơn lẻ có thể khiến:

```text
Spring Boot A
  -> Spring Data Redis B (bị override)
       -> Spring Data Commons C (từ BOM khác)
  -> Spring Framework D
```

với các interfaces/methods không tương thích. Có thể gây `NoSuchMethodError`, `ClassNotFoundException`, lỗi runtime hiếm hoặc chỉ xảy ra trên path Redis ít dùng.

Nguyên tắc là **ưu tiên BOM tương thích**, chỉ override khi có lý do, có chứng cứ support và integration tests.

---

## 7. Spring Boot dependency management: tránh phiên bản trôi nổi

### 7.1. Maven với Spring Boot parent/BOM

Ví dụ tối giản:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
```

Trong dự án dùng Spring Boot dependency management đúng cách, không tự chỉ định phiên bản cho từng thành phần đã được BOM quản lý trừ khi thật sự cần.

Nếu muốn dùng Jedis thay Lettuce, cần cấu hình dependencies/client type tương ứng với Boot version và kiểm tra rằng không vô tình để hai drivers cùng tồn tại tạo ambiguity.

### 7.2. Kiểm tra resolved dependencies

Có thể sử dụng công cụ dependency tree của build system trong môi trường phát triển/CI.

Ví dụ Maven:

```bash
mvn dependency:tree
```

Hoặc Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Đây là các lệnh **tham khảo cho người học**, không phải yêu cầu worker STEP 4 chạy build. Kết quả cần được kiểm tra cho phiên bản thực sự xuất hiện trong runtime classpath.

### 7.3. Vì sao cần dependency lock và reproducible builds?

Nếu build dùng version ranges/dynamic versions, hai artifact được build ở thời điểm khác nhau có thể dùng Lettuce/Netty khác nhau mà source code không thay đổi.

Đối với nâng cấp stateful database:

- Pin hoặc lock dependency versions theo policy.
- Lưu SBOM/dependency inventory.
- Build immutable artifacts.
- Gắn artifact digest vào deployment record.
- Không thay đổi nhiều dependency ngoài phạm vi mà không biết.
- Dùng CI repeatable để so sánh baseline/candidate.

### 7.4. Nâng Redis driver riêng với Spring Data Redis

Không phải mọi Lettuce/Jedis release đều được Spring Data Redis version đang dùng kiểm thử. Trước khi override:

```text
Check Spring Data Redis supported driver range
Check Spring Boot BOM release notes
Check driver breaking changes
Run integration tests on actual Redis Server target
```

Không dùng “compiles successfully” làm bằng chứng compatibility hoàn chỉnh.

---

## 8. Cấu hình Spring Boot Redis thay đổi giữa các major releases

Với các phiên bản Spring Boot hiện đại, cấu hình thường nằm dưới nhóm thuộc tính Redis được Boot công bố.

Ví dụ hình thức:

```yaml
spring:
  data:
    redis:
      host: redis.internal.example
      port: 6379
      timeout: 3s
```

Nhưng **property prefix, các tên tùy chọn, cách bật SSL, cluster, pooling và client customization** có thể thay đổi giữa các thế hệ Spring Boot.

Một số dự án cũ có thể đang dùng prefix/thuộc tính thuộc phiên bản Boot trước.

Khi nâng Boot:

1. Xem Spring Boot configuration properties documentation cho version đích.
2. Xem diagnostics về property deprecated/unbound.
3. Kiểm tra custom `LettuceConnectionFactory` hoặc `JedisConnectionFactory` bean.
4. Kiểm tra xem auto-configuration bị override ngoài ý muốn không.
5. Chạy integration test xác nhận **đang kết nối đúng Redis instance**.
6. Không chỉ tin rằng application start không có exception.

### 8.1. Nhầm environment là lỗi rất nguy hiểm

Một property bị bỏ qua có thể khiến app rơi về default host/port hoặc bean khác, kết nối vào Redis không đúng môi trường.

Nên xác nhận:

```text
Environment
Redis topology
Expected hostname/port
TLS enabled/disabled theo policy
ACL username
Database index nếu standalone
Key namespace/prefix
```

Không in password/secret ra logs khi kiểm tra cấu hình.

### 8.2. Connection factory tự viết cần kiểm tra đặc biệt

Ví dụ:

```java
@Bean
LettuceConnectionFactory redisConnectionFactory(...) {
    // ...
}
```

Nếu ứng dụng tự tạo factory, Spring Boot không nhất thiết áp dụng mọi `spring.data.redis.*` property theo cách bạn kỳ vọng.

Cần test trực tiếp connection settings, topology, timeouts, TLS và pooling, nhất là khi custom factory được tạo nhiều năm trước.

---

## 9. Lettuce hay Jedis: nâng cấp không có nghĩa phải đổi driver

**Lettuce** và **Jedis** đều có thể phục vụ các ứng dụng dùng Redis qua Spring Data Redis, nhưng có khác biệt về API, threading, connection management và hỗ trợ features theo version.

Một driver swap:

```text
Lettuce -> Jedis
```

không phải “chỉ thay dependency”. Nó có thể thay đổi:

- Sync/async/reactive support.
- Thread safety và connection sharing.
- Pooling defaults/requirements.
- Timeout/reconnect handling.
- Cluster/sentinel behavior.
- Exception types và translation.
- Serialization/connection lifecycle.
- Monitoring và command latency collector.

Nếu không có yêu cầu cụ thể, nâng driver hiện tại theo compatibility matrix thường ít rủi ro hơn thay cả driver trong cùng đợt nâng Redis Server.

### 9.1. Đường reactive phải xét riêng

`ReactiveRedisTemplate` và các listener/receiver reactive thường gắn với khả năng reactive của connector. Không được mặc định mọi driver hỗ trợ tương đương Spring Reactive Redis API.

Trước khi chuyển driver, kiểm tra tất cả beans:

```text
StringRedisTemplate
RedisTemplate<K,V>
ReactiveRedisTemplate<K,V>
ReactiveStringRedisTemplate
RedisMessageListenerContainer
StreamMessageListenerContainer
ReactiveRedisMessageListenerContainer
StreamReceiver
```

Nếu một bean phụ thuộc Lettuce-specific API hoặc Netty resources, việc thay Jedis có thể yêu cầu kiến trúc khác.

### 9.2. Threading, event loop và blocking

Lettuce có event loop và hỗ trợ async/reactive; code Java có thể vô tình block event loop hoặc sử dụng connection theo cách không phù hợp.

Một nâng cấp driver có thể thay đổi scheduling/resource usage đủ để bộc lộ bottleneck trước đây chưa thấy. Do đó, đo:

```text
Redis command latency
Spring HTTP p95/p99
Event-loop health
Pool wait time nếu dùng pool
CPU/GC
Connection count
Timeout/reconnect rate
```

Không đánh giá driver mới chỉ bằng thời gian chạy một `GET` trong unit test.

---

## 10. RESP2 và RESP3: protocol negotiation cũng là điểm tương thích

Redis dùng **RESP** làm giao thức giữa client và server. Các phiên bản có thể sử dụng RESP2 hoặc RESP3 theo hỗ trợ và negotiation.

Cần phân biệt:

```text
Redis Server hỗ trợ RESP3
    !=
Ứng dụng chắc chắn đang nói RESP3
```

Driver có thể dùng RESP2 theo mặc định hoặc chọn RESP3 qua cấu hình/handshake; hành vi phụ thuộc version.

Một thay đổi protocol có thể ảnh hưởng:

- Reply types và cách driver decode.
- Pub/Sub/messaging behavior ở connection.
- Bắt tay `HELLO`.
- Authentication và connection startup.
- Redis modules/custom commands.
- RESP codec do ứng dụng tự viết.

### 10.1. Không hardcode parser response nếu dùng driver chuẩn

Spring Data Redis và driver có trách nhiệm decode protocol. Nhưng nếu ứng dụng có custom low-level Redis client, raw RESP parser hoặc dùng native commands, cần test đúng RESP mode.

### 10.2. Kiểm thử mixed server versions

Trong một rolling upgrade, client có thể kết nối vào nhiều Redis nodes với versions khác nhau trong khoảng chuyển tiếp, tùy topology và đường nâng cấp được vendor hỗ trợ.

Nếu driver mới chỉ hoạt động đúng với server target nhưng không tương thích server cũ, kế hoạch “nâng app trước” có thể fail.

Phải xác định trạng thái mixed-version nào được support. Không ép cluster vào mixed-version lâu dài nếu release notes không cho phép.

---

## 11. ACL, AUTH, TLS và chứng chỉ

Từ góc nhìn ứng dụng, nâng Redis Server/driver có thể tạo lỗi xác thực ngay khi startup.

Cần kiểm tra:

- Redis có dùng user/password qua ACL hay chỉ password?
- Application dùng `username` nào?
- Redis user có quyền command categories phù hợp không?
- Có key-pattern restrictions?
- TLS có được bật và yêu cầu client certificate không?
- Certificate chain/hostname verification có đúng?
- Proxy hoặc managed service có chấp nhận RESP/HELLO startup mới không?
- Rotation secrets có diễn ra cùng thời điểm nâng cấp không?

### 11.1. Không dùng tài khoản admin để “làm test pass”

Nếu ứng dụng gặp `NOPERM`, tăng quyền thành `+@all` một cách mù quáng có thể che lỗi ACL và mở rộng rủi ro bảo mật.

Cần kiểm tra command set thực tế, ví dụ:

```text
GET/SET/HGET/HSET/DEL/EXPIRE
EVAL/EVALSHA nếu app dùng Lua
XADD/XREADGROUP/XACK/XPENDING nếu app dùng Streams
SUBSCRIBE/PSUBSCRIBE/PUBLISH nếu app dùng Pub/Sub
CLUSTER-specific operations nếu client cần
```

Quyền cụ thể phụ thuộc ACL categories, key patterns và Redis version. Không sao chép nguyên một mẫu ACL có quyền rộng vào production.

### 11.2. TLS failure có thể chỉ xảy ra ở một node

Trong Redis Cluster, client khám phá các endpoints từ topology. Nếu certificate SAN, advertised endpoint, DNS hoặc private networking không khớp, application có thể kết nối seed node thành công nhưng thất bại khi đi tới node khác.

Kiểm thử:

```text
Connect to seed
Discover topology
Route GET/SET tới nhiều slots
Reconnect after failover
TLS handshake tới mỗi node liên quan
```

Chỉ test `PING` vào một node không đủ.

### 11.3. Không log credentials để debug

Không đưa password, session token, TLS private key, URL chứa credentials hay full Redis command arguments vào logs/tickets. Dùng sanitized connection metadata và exception category.

---

## 12. Serializer compatibility: một trong những rủi ro lớn nhất

Redis lưu key/value dưới dạng dữ liệu theo Redis types; Spring Data Redis có thể serialize Java objects sang bytes.

Một serializer upgrade có thể làm ứng dụng mới không đọc được dữ liệu cũ.

Ví dụ:

```text
Old app:
  Redis key = product:42
  Value bytes = JDK-serialized ProductV1

New app:
  Redis key = product:42
  Expected bytes = JSON ProductV2

=> Deserialization exception hoặc kết quả sai.
```

**Redis Server upgrade không tự chuyển value bytes sang format mà Java mới hiểu.**

### 12.1. Những serializer thường gặp

- `StringRedisSerializer`: chuyển String key/value thành bytes theo charset.
- `JdkSerializationRedisSerializer`: Java native serialization, phụ thuộc class/schema/compatibility và có những rủi ro bảo mật với dữ liệu không đáng tin.
- Jackson-based serializers: JSON serialization có thể phụ thuộc type metadata, class names, ObjectMapper configuration và phiên bản.
- Custom codecs: Protobuf, MessagePack, Kryo, compressed/encrypted bytes, schema version.

Cấu hình serializer có thể nằm ở:

```text
RedisTemplate
StringRedisTemplate
RedisCacheManager
RedisSerializer implementations
Redis Repository mapping
ReactiveRedisTemplate SerializationContext
```

Không được giả định đổi một `RedisTemplate` bean là đã sửa mọi đường cache/repository/reactive.

### 12.2. Vấn đề class rename và JDK serialization

Một Java class thay package:

```text
com.example.old.Product
    ->
com.example.catalog.Product
```

có thể khiến dữ liệu đã serialize bằng Java native format không đọc được ở app mới nếu không có chiến lược tương thích.

Đây không phải lỗi Redis Server, nhưng thường xuất hiện ngay sau nâng Spring Boot/Spring Data hoặc refactor code.

Nếu buộc đọc dữ liệu cũ, cần có migration plan; nếu chỉ là cache tái tạo được, có thể dùng versioned namespace hoặc invalidate an toàn.

### 12.3. Jackson type metadata và ObjectMapper

Một số cấu hình JSON serializer có type hints để deserialize polymorphic objects. Thay đổi ObjectMapper/default typing, type aliases hoặc tên Java class có thể làm JSON cũ không được đọc như trước.

Không bật unsafe polymorphic deserialization để “chữa lỗi cache” nếu dữ liệu có thể bị điều khiển bởi nguồn không đáng tin.

Nên dùng schema/version hợp lý, DTO ổn định và test bằng **bytes thực tế từ bản cũ**.

### 12.4. Null values và Redis Cache

Spring Cache có thể có cách biểu diễn null/special cache values. Thay đổi serializer/default giữa versions có thể khiến app mới hiểu nhầm null marker cũ hoặc cache key prefix.

Kiểm tra:

```text
Cached nulls
TTL của null
Key prefix
Cache-specific serializer
Cache-wide defaults
Value type metadata
```

### 12.5. Key serializer còn ảnh hưởng Redis Cluster hash slot

Hash slot được tính từ **bytes tên key thực**. Nếu trước đây dùng String serializer:

```text
order:{o-101}:status
```

nhưng bản mới dùng serializer khác, bytes Redis key có thể không còn chứa tag như mong muốn.

Hậu quả:

- Không tìm thấy key cũ.
- Multi-key command bị `CROSSSLOT`.
- Key distribution/hot slots thay đổi.
- Cache hit rate rơi mạnh.
- Application “mất dữ liệu” dù dữ liệu vẫn nằm ở key cũ.

Do đó key serializer phải được kiểm chứng riêng với value serializer.

---

## 13. Chiến lược migration dữ liệu khi đổi serializer

Có ba cách tiếp cận chính.

### 13.1. Giữ backward compatibility

New app đọc được format cũ, nhưng ghi format mới theo policy.

Ví dụ:

```text
Read:
  if prefix/version V2 -> decode V2
  else if format V1 -> decode V1
Write:
  encode V2
```

Cần tránh nhầm một payload lỗi thành V1. Nên có header/schema version rõ thay vì thử deserialize bừa mọi format.

Nếu có mixed app versions, cũng cần hỏi:

```text
Old app có đọc được V2 không?
```

Nếu không, đừng cho old và new writers dùng cùng key namespace mà vẫn cho phép rollback app tùy ý.

### 13.2. Versioned namespace

Ví dụ:

```text
product-cache:v1:<id>
product-cache:v2:<id>
```

Đối với cache tái tạo được từ database, versioned namespace có thể đơn giản:

1. New app đọc/ghi v2.
2. Old app tiếp tục dùng v1 trong giai đoạn chuyển tiếp.
3. Cache miss ở v2 được load từ source-of-truth.
4. Sau ổn định, v1 hết hạn hoặc được dọn theo quy trình.

Đánh đổi: tăng memory tạm thời, tăng cache misses, có thể xuất hiện stale dữ liệu nếu không thiết kế invalidation.

### 13.3. Migration state có kiểm soát

Nếu Redis chứa state không thể tái tạo:

1. Chụp backup độc lập.
2. Xác định tất cả key families và data types.
3. Xây reader cho old format, writer cho new format.
4. Đảm bảo TTL/deadline được bảo toàn.
5. Xử lý concurrent writes hoặc freeze traffic theo policy.
6. Chuyển dữ liệu từng phần với checksums/counts.
7. Readback qua app mới.
8. Có cutover và rollback state plan.
9. Chạy reconciliation cho các records thay đổi trong cửa sổ migration.

Không “đổi serializer rồi `FLUSHDB`” nếu dữ liệu đang là source-of-truth.

### 13.4. Bảo toàn TTL

Khi copy key cũ sang key mới, không tùy tiện đặt TTL từ đầu nếu key đã sắp hết hạn.

Ví dụ session có deadline:

```text
Expire at 15:00
Migration at 14:58
```

Nếu new app tạo TTL 30 phút từ 14:58, session sẽ bị gia hạn sai.

Cần xét `PTTL`/deadline và race giữa thời gian đọc và ghi. Với token, lock, session hoặc OTP, migration phải được xem xét thêm về correctness và bảo mật.

---

## 14. Redis Repository: upgrade có thể tác động tới nhiều key

Spring Data Redis Repository có thể lưu:

```text
Entity Hash
Secondary index sets
Keyspace metadata
TTL metadata
Shadow copies
```

Nâng Spring Data Redis có thể ảnh hưởng:

- Mapping rules.
- Custom converters.
- Entity ID encoding.
- Indexed fields/index maintenance.
- TTL và expiration listener behavior.
- Schema/class serialization.
- Event listeners và Redis keyspace notifications.

Một test chỉ chạy `repository.save()` rồi `findById()` trên Redis rỗng chưa chứng minh migration an toàn cho **dữ liệu thực tế từ bản cũ**.

### 14.1. Contract tests

Nên test:

```text
Old app writes -> New app reads
New app writes -> Old app reads (nếu rollback old app cần)
Index query sau upgrade
Update indexed field
Delete entity + index cleanup
Entity expiration + TTL
Concurrent save/findById
Data from previous RDB restore
```

Nếu một release mới không còn hỗ trợ backward read cho old app, rollout phải thiết kế kiểu **forward-only** hoặc có dual-format strategy rõ ràng.

### 14.2. Redis Cluster và repository indexes

Repository secondary indexes có thể nằm khác hash slot với entity keys. Một nâng cấp client/server không tự chữa những hạn chế multi-key của Cluster.

Cần test đúng topology production, không dùng standalone Redis để khẳng định toàn bộ Repository behavior sẽ tương đương trên Cluster.

---

## 15. Spring Cache: xem lại defaults và cache key semantics

Ứng dụng có thể dùng:

```java
@Cacheable(cacheNames = "products", key = "#productId")
public ProductDto findProduct(String productId) {
    return repository.findProduct(productId);
}
```

Những điểm cần xác minh sau nâng cấp:

- Cache name và key prefix.
- Key serializer và value serializer.
- `RedisCacheManager` configuration.
- Default TTL và TTL theo cache.
- Null caching.
- `@CacheEvict` behavior.
- Batch deletion strategy.
- Transaction-aware cache behavior.
- Cache hit/miss rate sau deployment.
- Serialization failure trên cache entries cũ.

### 15.1. Cache miss spike là tín hiệu migration

Nếu cache hit rate trước nâng cấp là 95% và sau nâng cấp tụt mạnh, có thể do:

```text
- Key prefix thay đổi
- Key serializer thay đổi
- Cache name khác
- Redis DB/instance khác
- TTL default ngắn hơn
- Data load bị invalidate
- Mất dữ liệu trong server migration
```

Không kết luận ngay “Redis mới chậm” khi root cause là **ứng dụng không còn tìm được key cũ**.

### 15.2. Cache data có thể tái tạo, nhưng nguồn gốc có chịu nổi không?

Khi nâng cấp đổi namespace, tất cả app instances có thể đồng thời miss rồi tải database.

Cần chuẩn bị:

- Cache prewarming.
- Request coalescing/single-flight.
- Rate limit/bulkhead.
- Load test cold cache.
- Theo dõi database QPS/latency.
- TTL jitter nếu phù hợp.
- Rollout theo phần trăm traffic.

Một cache migration đúng chức năng vẫn có thể gây outage vì cache stampede.

---

## 16. Lua script, Redis Functions và server-side logic

Nếu ứng dụng dùng `RedisScript`:

```java
Long result = redisTemplate.execute(
    script,
    List.of(key1, key2),
    arg1,
    arg2
);
```

cần kiểm tra:

- `KEYS` và `ARGV` serialization.
- Same-slot restrictions trong Redis Cluster.
- `EVAL`/`EVALSHA` behavior.
- Script cache sau restart/failover.
- Lua version/semantics theo Redis release.
- Script error handling.
- Long-running script latency.
- Redis ACL permissions cho commands script gọi.
- Nơi lưu script và cách deploy resource.

### 16.1. EVALSHA cache có thể bị mất

Redis script cache là state phía server. Sau restart hoặc thay node, SHA đã biết phía client có thể chưa được nạp ở server mới.

Một implementation chuẩn có thể fallback từ `EVALSHA` sang `EVAL` khi gặp lỗi script-not-loaded tùy API/driver, nhưng **phải test** với Redis Server và Spring Data Redis version đang dùng.

Không dựa vào giả định một SHA đã load vĩnh viễn trên mọi primary trong Cluster.

### 16.2. Redis Functions

Nếu ứng dụng dùng Redis Functions hoặc server-side modules, kiểm tra:

- Function library có được deploy trên tất cả primary cần thiết không?
- Upgrade có yêu cầu reload/migration không?
- Function APIs và ACL permissions có đổi không?
- Backup/restore có chứa đúng function state theo version không?
- Kết quả có tương thích các callers cũ/mới không?

Không coi Redis Functions như Java library tự đi cùng file JAR Spring Boot.

### 16.3. Key handling trong Cluster

Hai key:

```text
cart:{c-101}:items
cart:{c-101}:total
```

cùng hash slot; hai key:

```text
cart:{c-101}:items
stock:{sku-42}:available
```

thường không.

Nâng Redis/driver có thể làm routing/validation được thực hiện khác, nhưng không biến một transaction xuyên slots thành hợp lệ.

Cần có integration test với các key cùng-slot và khác-slot để xác nhận lỗi `CROSSSLOT` được xử lý đúng, không bị nuốt hoặc retry vô hạn.

---

## 17. Pub/Sub: nâng cấp phải kiểm tra kết nối dài hạn

Redis Pub/Sub không giống `GET`/`SET` ngắn.

Một subscriber có thể giữ connection lâu:

```text
Spring RedisMessageListenerContainer
        |
        v
Redis SUBSCRIBE / PSUBSCRIBE
        |
        v
Messages continuously received
```

Trong upgrade/failover:

- Connection có thể bị ngắt.
- Subscription có thể cần thiết lập lại.
- Messages phát trong khoảng đứt kết nối có thể mất.
- Pattern subscription cần được khôi phục đúng.
- Handler concurrency/order có thể thay đổi theo container configuration.
- Duplicate hoặc stale notifications có thể xảy ra ở workflow bên ngoài.

**Redis Pub/Sub thông thường không lưu backlog để replay sau reconnect.**

### 17.1. Test Pub/Sub sau nâng cấp

Một test hữu ích:

1. Kết nối subscriber trước.
2. Publish message có event ID giả.
3. Xác nhận handler nhận.
4. Mô phỏng restart/failover trong test.
5. Đợi reconnect/resubscribe.
6. Publish message mới.
7. Xác nhận handler tiếp tục nhận.
8. Ghi nhận messages trong thời gian disconnect không được bảo đảm replay.

Không test bằng cách publish một message đúng lúc subscriber offline rồi mong nó xuất hiện lại.

### 17.2. Keyspace notifications

Nếu dùng expiration/keyspace events, cần kiểm tra cấu hình `notify-keyspace-events`, listener subscription và application behavior.

Keyspace notifications là Pub/Sub kiểu best-effort. Không dùng chúng làm cơ chế duy nhất bảo đảm xử lý nghiệp vụ khi Redis restart hoặc nâng cấp.

---

## 18. Redis Streams: upgrade có thể ảnh hưởng consumer group và PEL

Redis Streams có trạng thái bền hơn Pub/Sub theo cơ chế Stream data và consumer group:

```text
Stream entries
Consumer group
Last-delivered ID
Pending Entries List (PEL)
Consumer ownership
ACK status
```

Khi nâng Redis Server hoặc driver, cần test:

- Producer `XADD`.
- Consumer `XREADGROUP`.
- Pending query `XPENDING`.
- `XACK`.
- `XAUTOCLAIM`/`XCLAIM` nếu sử dụng.
- Offset/chế độ đọc của Spring listener/receiver.
- Retry/DLQ.
- Stream retention và trimming.
- Kích thước message/serializer.
- Reconnect và event ordering.

### 18.1. Không xóa PEL để “làm sạch” sau nâng cấp

Pending entries có thể là công việc chưa xử lý xong. Việc xóa group/Stream hoặc đổi consumer group name trong deployment có thể làm mất dấu công việc.

Một kế hoạch nâng cấp tốt cần định nghĩa:

```text
Trước nâng cấp:
    Kiểm tra pending count/oldest idle.
    Có thể tạm giảm producer rate.
    Đợi/drain work nếu nghiệp vụ yêu cầu.

Sau nâng cấp:
    Consumer reconnect.
    Reclaim pending đủ điều kiện.
    Xử lý idempotent.
    ACK đúng group/entry.
```

### 18.2. Mixed consumer versions

Nếu hai phiên bản app chạy song song:

```text
Worker v1 -> serializer/event schema V1
Worker v2 -> serializer/event schema V2
```

cần bảo đảm cả hai có thể xử lý event schema được producer gửi trong cửa sổ mixed-version.

Nếu producer mới chỉ ghi V2 mà worker cũ không hiểu, canary app có thể gây poison messages cho workers cũ.

Dùng schema version/compatibility contract, hoặc triển khai worker hỗ trợ đọc V2 **trước** khi producer bắt đầu ghi V2.

### 18.3. `XREADGROUP` reply mất khi reconnect

Nếu Redis đã giao entry và ghi vào PEL nhưng application mất connection trước khi nhận payload, entry có thể ở pending. Sau reconnect, chỉ đọc offset `>` không tự bảo đảm đọc lại entry ấy.

Cần recovery strategy cho pending messages; đừng nhầm connection-level reconnect với message-level acknowledgment/recovery.

---

## 19. Transaction, pipelining và connection semantics

Spring Data Redis có thể sử dụng pipeline hoặc transaction:

```text
Pipeline:
    gửi nhiều commands, thu replies
    không tự atomic

MULTI/EXEC:
    Redis transaction theo ngữ nghĩa Redis
    không tạo distributed ACID với SQL database
```

Một driver upgrade có thể thay đổi:

- Thứ tự/định dạng responses được decode.
- Connection pinning trong transaction.
- Pipeline buffering.
- Error translation.
- Retry behavior khi connection mất.
- Command queue và cancellation.

### 19.1. Chỉ test happy path chưa đủ

Cần test:

```text
Pipeline với 100 commands, một command lỗi
MULTI/EXEC success
WATCH conflict
Transaction timeout trước/đúng lúc EXEC
Connection drop sau gửi command
Retry cùng request ID
```

Lỗi timeout có thể để operation outcome không xác định. Retry mù `INCR`, `LPUSH` hoặc `XADD *` có thể tạo duplicate side effects.

Nâng driver không tự cung cấp exactly-once semantics.

### 19.2. Reconnect không đồng nghĩa an toàn khi retry

Một client tự reconnect là hữu ích để phục hồi network, nhưng cần phân biệt:

```text
Connection restored
    !=
Original command definitely not executed
```

Nếu Redis đã xử lý `INCR` nhưng response bị mất, application retry nguyên `INCR` có thể tăng hai lần.

Vì vậy, test upgrade nên bao gồm idempotency/receipt logic và unknown-outcome handling.

---

## 20. Một điểm khởi đầu an toàn: baseline trước khi nâng cấp

Không thể xác nhận “không suy giảm hiệu năng” nếu không có số đo trước.

Ghi baseline có thời gian đo rõ ràng:

| Nhóm | Baseline cần thu |
|---|---|
| App | HTTP p50/p95/p99, error rate, RPS |
| Redis client | GET/SET/EVAL/XADD latency, timeouts |
| Connection | Active connections, reconnect count, pool wait |
| Redis server | `instantaneous_ops_per_sec`, `INFO commandstats` |
| Memory | `used_memory`, RSS, evictions, fragmentation |
| Persistence | BGSAVE/AOF status, lag, disk usage |
| Cluster | Per-primary CPU/ops/s, slot health, redirects |
| Sentinel | Replication/failover status |
| Cache | Hit rate, miss rate, database fallback rate |
| Streams | XADD rate, group lag, pending, ACK rate |
| Pub/Sub | Subscriber connected/reconnected, messages received |
| Data | Key count, sample TTL/value compatibility |
| Security | ACL denials, TLS handshake errors |

Các values cần đo từ hệ thống thật; không được điền “dự kiến” vào cột observed.

### 20.1. Baseline phải có workload đại diện

Một instance Redis thử nghiệm chỉ có 20 keys và một Java thread không thể đại diện production có nhiều keys/traffic.

Nếu không thể dùng dữ liệu thật vì bảo mật, tạo dataset đã tổng hợp/anonymize phản ánh:

```text
Key count distribution
Value sizes
TTL distribution
Read/write ratio
Hot keys
Cluster hash tags
Streams pending/lag
Concurrency
Network/TLS topology
```

### 20.2. Không log secret để tạo baseline

Dùng metrics/timing theo command family, không chụp raw MONITOR payload ở production chỉ để so “trước và sau”.

---

## 21. Xây compatibility test trước khi thay đổi Redis Server

Một ma trận chạy test hữu ích:

| Tổ hợp | Mục đích |
|---|---|
| App cũ + Redis cũ | Baseline đã biết |
| App mới + Redis cũ | Xác minh có thể nâng app trước |
| App cũ + Redis mới | Xác minh có thể nâng server trước |
| App mới + Redis mới | Trạng thái đích |
| Mixed app old/new + Redis đang chuyển đổi | Canary/rolling behavior |
| Restore dữ liệu cũ + app mới | Backward data readability |
| Client mới sau failover/restart | Reconnect và state recovery |

Không nhất thiết tổ hợp nào cũng được hỗ trợ. Nếu release notes loại trừ một tổ hợp, **đừng ép chạy production theo tổ hợp đó**.

### 21.1. Test dữ liệu được ghi từ phiên bản cũ

Đây là bước dễ bị bỏ quên:

```text
1. Chạy app cũ.
2. Tạo data: String, Hash, Cache, Repository, TTL, Stream.
3. Lưu data hoặc snapshot.
4. Chạy app mới.
5. Đọc và đối chiếu.
6. Sửa/ghi/xóa dữ liệu theo contract.
7. Nếu có rollback, chạy app cũ đọc data sau app mới ghi.
```

Một test chỉ tạo dữ liệu mới dưới app mới có thể bỏ sót serializer backward-compatibility.

### 21.2. Test error-path và concurrency

Một số regression chỉ xuất hiện ở:

```text
Redis connection timeout
ACL denied
Wrong type
CROSSSLOT
NOSCRIPT
Primary failover
READONLY on old primary
MOVED/ASK redirects
Consumer pending recovery
Concurrent cache misses
```

Cần đưa các case này vào suite theo mức rủi ro.

---

## 22. Integration test bằng Spring Boot và Redis thật

Unit tests mock `RedisTemplate` không phát hiện được:

- RESP compatibility.
- TLS/ACL.
- Serializer wire format.
- Cluster redirects.
- Lua execution.
- Actual Redis Stream semantics.
- Replication/failover.
- Persistence startup.

Nên dùng integration tests với **Redis Server version đích thật** trong container hoặc test environment riêng.

### 22.1. Ví dụ Testcontainers ý tưởng

Một class test minh họa:

```java
package com.example.redis;

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

@SpringBootTest
@Testcontainers
class RedisCompatibilityIT {

    @Container
    static GenericContainer<?> redis =
        new GenericContainer<>(
            "redis:" + System.getProperty(
                "test.redis.version",
                "REPLACE_WITH_APPROVED_VERSION"
            )
        ).withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.redis.host",
            redis::getHost
        );
        registry.add(
            "spring.data.redis.port",
            () -> redis.getMappedPort(6379)
        );
    }

    @Autowired
    StringRedisTemplate template;

    @Test
    void stringAndTtlRoundTrip() {
        String key = "upgrade-test:item:1";

        template.opsForValue().set(
            key,
            "hello",
            Duration.ofMinutes(2)
        );

        assertThat(
            template.opsForValue().get(key)
        ).isEqualTo("hello");

        assertThat(
            template.getExpire(key)
        ).isPositive();
    }
}
```

Đây là **mẫu ý tưởng**: thay `REPLACE_WITH_APPROVED_VERSION` bằng image tag đã pin và được phê duyệt trước khi chạy. Thêm dependencies cho JUnit 5, Testcontainers, AssertJ và Spring Boot test theo BOM/phiên bản dự án. Tên configuration properties phải khớp Spring Boot version mà project dùng.

### 22.2. Tránh phụ thuộc tag latest

Không dùng:

```text
redis:latest
```

làm nguồn duy nhất cho compatibility tests vì image có thể đổi sau khi bạn đã ghi nhận kết quả. Cần pin phiên bản/digest tương ứng server candidate.

Nếu test upgrade chính xác, nên chạy cả old và new server images trong CI theo ma trận.

### 22.3. Testcontainer standalone không test Cluster

Một Redis container đơn lẻ không tự kiểm tra:

```text
Slot routing
MOVED/ASK
Hash tags/CROSSSLOT
Primary/replica failover
Topology refresh
Sentinel discovery
```

Với hệ thống production Redis Cluster/Sentinel, cần môi trường integration/soak tương ứng topology.

---

## 23. Bộ smoke test tối thiểu sau nâng cấp

Sau khi deployment, smoke tests có thể dùng dữ liệu giả trong namespace được phép.

### 23.1. Connectivity

```redis
PING
```

Kết nối thành công ở một node chưa chứng minh được tất cả routes hoạt động trong Redis Cluster.

### 23.2. String/TTL

```redis
SET upgrade:smoke:string ok EX 120
GET upgrade:smoke:string
TTL upgrade:smoke:string
```

### 23.3. Hash

```redis
HSET upgrade:smoke:hash field value
HGET upgrade:smoke:hash field
```

### 23.4. Lua

Một script không gây hại:

```redis
EVAL "return redis.call('GET', KEYS[1])" 1 upgrade:smoke:string
```

Nếu application dùng `RedisScript`, cần chạy qua chính API Spring Data Redis, không chỉ CLI.

### 23.5. Pub/Sub

Một subscriber lab nhận notification giả từ publisher lab.

### 23.6. Streams

```redis
XGROUP CREATE upgrade:smoke:stream upgrade-smoke-group 0 MKSTREAM
XADD upgrade:smoke:stream * kind demo
XREADGROUP GROUP upgrade-smoke-group worker-1 COUNT 1 STREAMS upgrade:smoke:stream >
```

Sau khi lấy Stream ID thực, có thể `XACK` bằng ID đó. Dùng key/group riêng, không thao tác lên business Stream production.

### 23.7. Serializer/Cache/Repository

Dùng ứng dụng Spring Data Redis để đọc các entries **được tạo ở phiên bản trước**, không chỉ smoke keys mới.

### 23.8. Cleanup

Xóa test keys theo namespace riêng và đúng quyền; không dùng `FLUSHDB`/`FLUSHALL` trên Redis chia sẻ chỉ để dọn smoke test.

---

## 24. Standalone Redis: nâng cấp có thể cần downtime

Một Redis standalone không có replica chịu tải đồng thời có ít lựa chọn rolling upgrade thực sự.

Kế hoạch điển hình:

```text
1. Backup và restore test
2. Đặt ứng dụng vào maintenance/freeze writes nếu cần
3. Dừng hoặc chuyển traffic theo runbook
4. Stop Redis đúng cách
5. Nâng binary/image/config
6. Start Redis
7. Xác nhận load RDB/AOF thành công
8. Smoke tests
9. Mở traffic
10. Theo dõi
```

Nhưng chi tiết shutdown/backup **phụ thuộc Redis version, persistence, storage và SLA**. Không mặc định `SHUTDOWN NOSAVE` hoặc `SHUTDOWN SAVE` là đúng cho mọi trường hợp.

### 24.1. Nếu Redis chỉ là cache

Ứng dụng có thể chấp nhận Redis downtime hoặc cold cache sau restart nếu source-of-truth vẫn tồn tại.

Nhưng cần kiểm tra:

- Load database khi cache miss.
- Fallback khi Redis unavailable.
- Cache stampede.
- Rate limits.
- Session impacts.
- SLO của service.

### 24.2. Nếu Redis chứa state duy nhất

Downtime và mất dữ liệu không thể được quyết định chỉ bằng một lệnh deployment.

Cần xác định:

```text
RPO
RTO
Last durable snapshot/AOF state
Backup ngoài host
Write freeze/cutover point
No-replay versus replay policy
Rollback data path
```

Nếu không có replica và ứng dụng không chịu downtime, cần đổi kiến trúc HA hoặc sử dụng migration mechanism được hỗ trợ thay vì kỳ vọng standalone có zero-downtime magic.

---

## 25. Sentinel: nâng cấp dựa trên replication và failover

Trong một topology Redis Sentinel điển hình:

```text
           Sentinels
               |
          Monitor topology
               |
       +-------+-------+
       |               |
    Primary         Replica(s)
       |               |
       +--- replication+
```

Một chiến lược nâng cấp có thể khai thác replica để giảm downtime, nhưng phải tuân theo **tài liệu Redis/vendor cho cặp phiên bản cụ thể**.

Một luồng tư duy:

1. Kiểm tra tất cả Sentinel/Redis nodes healthy.
2. Backup và test restore.
3. Xác nhận phiên bản mixed replication được hỗ trợ.
4. Nâng/cập nhật replica trước khi đổi primary nếu vendor guide cho phép.
5. Đợi replica đồng bộ và kiểm tra lag.
6. Chuyển primary/failover có kiểm soát theo runbook.
7. Xác nhận app driver khám phá primary mới.
8. Nâng node còn lại.
9. Kiểm tra replication, Sentinel quorum và client reconnect.
10. Theo dõi lâu hơn một khoảng traffic thực tế.

### 25.1. Failover không phải zero-risk write commit

Redis replication thường bất đồng bộ. Primary có thể xác nhận write cho client trước khi replica nhận.

Nếu failover trong khoảng ấy, một số writes có thể mất. Không tuyên bố “rolling upgrade không mất một byte dữ liệu” nếu cơ chế replication/persistence không cung cấp mức bảo đảm ấy.

### 25.2. Kiểm tra Spring connection behavior

Application cần test:

```text
Current primary write
Sentinel failover
Old primary no longer writable
Client re-discovery
New primary write
Pub/Sub reconnect
Streams pending recovery
```

Một service chỉ start thành công trước failover chưa đủ.

### 25.3. Nâng Sentinel riêng hay cùng đợt?

Sentinel processes cũng có versions/configuration. Kế hoạch nâng chúng cần theo compatibility documentation; không tự động gộp tất cả vào một đợt nếu làm giảm quorum hoặc khả năng tự failover.

---

## 26. Redis Cluster: nâng cấp từng node mà không phá slot availability

Redis Cluster phân bố 16.384 slots qua các primary, mỗi primary có thể có replica.

```text
Primary A <-> Replica A
Primary B <-> Replica B
Primary C <-> Replica C
```

Một chiến lược rolling upgrade thường cân nhắc nâng replica rồi chuyển role và nâng primary cũ, nhưng **không áp dụng như công thức chung** nếu cặp versions/topology không được nhà cung cấp hỗ trợ.

### 26.1. Kiểm tra Cluster trước nâng cấp

Trong môi trường được phép:

```redis
CLUSTER INFO
CLUSTER NODES
```

Xác nhận:

- Cluster đang `ok` theo tiêu chí của deployment.
- Slots cần thiết đã được gán.
- Không có primary thiếu replica theo yêu cầu HA.
- Không có resharding/migration dang dở nếu kế hoạch yêu cầu trạng thái ổn định.
- Replication lag trong ngưỡng chấp nhận.
- Không có node đã degraded.
- Network/TLS/ACL của các node hoạt động.
- Memory headroom đủ để failover và RDB/AOF operations.

### 26.2. Nguy cơ khi nhiều node cùng được nâng

Nếu cùng lúc restart primary và replica của một nhóm slot:

```text
Primary A down
Replica A down
```

thì có thể mất availability cho slots của A. Vì vậy giới hạn concurrency của rollout là quyết định quan trọng.

Không restart hàng loạt Cluster nodes chỉ vì orchestrator có một `rollingUpdate` mặc định mà không xét primary/replica placement.

### 26.3. MOVED, ASK và topology refresh

Trong upgrade/resharding, clients có thể nhận:

```text
MOVED
ASK
TRYAGAIN
READONLY
Connection reset
```

Tùy bối cảnh và Redis version. Lettuce/Jedis cluster-aware clients có thể xử lý topology changes, nhưng phải test:

- Redirect handling.
- Dynamic node addresses.
- DNS/TLS certificates.
- Topology refresh intervals.
- Request deadlines.
- Retry/idempotency.
- Pipelined/multi-key operations.

Không sửa `CROSSSLOT` bằng cách retry vô hạn; đó thường là lỗi data/key design.

### 26.4. Topology version skew

Application instances mới và cũ có thể có cache topology ở những thời điểm khác nhau. Nếu cluster thay đổi role/slots, client cần refresh đúng.

Để đánh giá, đo:

```text
Redirect rate
Timeout rate
Connection failures
Per-node ops/s
p95/p99 Redis command latency
Failed commands
Cluster slot coverage
```

### 26.5. Hash tag không đổi trong nâng cấp

Giữ nguyên quy tắc:

```text
order:{o-101}:status
order:{o-101}:items
```

Nếu đồng thời đổi key naming/hash tag, khó phân biệt lỗi do Redis Server upgrade với lỗi do data repartitioning.

Nên tách data model migration ra một đợt riêng khi có thể.

---

## 27. Managed Redis: vendor contract là nguồn quyết định

Với một dịch vụ Redis managed, người vận hành có thể không có quyền:

```text
CONFIG SET
BGSAVE
SHUTDOWN
CLUSTER FAILOVER
Truy cập file RDB/AOF
Cài binary Redis trực tiếp
```

Vendor có thể hỗ trợ in-place engine upgrade, maintenance window hoặc migration đặc thù.

Quy trình cần hỏi:

1. Cặp Redis engine versions nào được hỗ trợ?
2. Có yêu cầu nâng qua intermediate versions không?
3. Downtime/failover behavior là gì?
4. Có automated snapshot trước upgrade không?
5. Backup/restore có thể thử độc lập không?
6. Rollback/downgrade có thực sự được hỗ trợ không?
7. Có thay đổi endpoint/TLS/ACL/password không?
8. Redis modules/features có còn tương thích không?
9. Có quota/concurrency/version restrictions không?
10. Cần nâng client trước hoặc sau server theo vendor guidance?

**Không sao chép runbook tự quản lý Redis sang managed service mà không kiểm tra các giới hạn cụ thể.**

### 27.1. Cửa sổ maintenance không miễn kiểm thử client

Dù nhà cung cấp hứa thực hiện engine upgrade, Spring app vẫn có thể gặp reconnect, timeout, moved topology hoặc command changes.

Nên có app canary, client observation và alerting sẵn sàng theo dõi chính thời điểm maintenance.

---

## 28. RDB/AOF: backup trước upgrade và tính một chiều của format

Redis có thể lưu persistence dưới dạng:

- RDB snapshot.
- AOF log/rewrite format.
- Cơ chế kết hợp tùy Redis version.
- Snapshot/backup do managed service tạo.

Một bản Redis mới có thể đọc một số file cũ, nhưng **không được mặc định bản Redis cũ có thể đọc file mà Redis mới vừa tạo**.

Đây là rủi ro rollback quan trọng.

### 28.1. Backup là điều kiện cần, không phải rollback plan hoàn chỉnh

Trước nâng cấp:

```text
Tạo backup nhất quán phù hợp topology
Xác minh file/backup location
Ghi Redis version và format metadata
Restore thử vào môi trường cô lập
Chạy contract tests bằng Spring app
Lưu bản backup pre-upgrade độc lập
```

Không chỉ kiểm tra “có file dump.rdb”.

### 28.2. Một rollback server binary có thể không load data file mới

Giả sử:

```text
Redis A -> Redis B
Redis B tạo RDB/AOF mới
Muốn đổi binary về Redis A
```

Redis A có thể không đọc được format file do B tạo. Nếu thay image về bản cũ mà không có data plan, instance có thể không khởi động được hoặc không phục hồi như kỳ vọng.

Đó là lý do cần:

- Kiểm tra downgrade support chính thức.
- Giữ snapshot trước nâng cấp.
- Định nghĩa cách xử lý writes sau cutover.
- Phân biệt application rollback với **data rollback**.
- Có alternative forward-fix strategy khi downgrade không được hỗ trợ.

### 28.3. Restore snapshot cũ làm mất thay đổi mới

Nếu đã chạy Redis B trong 30 phút và có writes, rollback sang snapshot được chụp trước nâng cấp có thể khiến các writes ấy biến mất.

Ví dụ:

```text
10:00 Backup trên Redis A
10:10 Nâng Redis B
10:15-10:45 Ứng dụng ghi nhiều orders
10:50 Rollback data từ backup 10:00
```

Nếu Redis là source-of-truth, các orders sau 10:00 có thể mất, trừ khi có journal/catch-up/reconciliation được thiết kế.

Do đó, lời hứa “rollback bằng restore backup” phải đi kèm **RPO và chiến lược replay**, không phải bước mặc định an toàn.

### 28.4. Data loss còn liên quan replication

Trong failover, replica có thể chưa nhận write cuối. Kết hợp sự cố persistence và async replication có thể gây mất writes mà client từng thấy thành công.

Nếu dữ liệu không được phép mất, cần thiết kế source-of-truth/persistence/consistency phù hợp. Nâng cấp không tự biến Redis replication thành đồng bộ với transaction commit tuyệt đối.

---

## 29. RPO, RTO và correctness là ba tiêu chí riêng

**RPO (Recovery Point Objective)**: lượng thay đổi theo thời gian hệ thống chấp nhận mất.

**RTO (Recovery Time Objective)**: thời gian khôi phục dịch vụ đến trạng thái hoạt động.

**Correctness**: dữ liệu sau upgrade/failover có còn thỏa bất biến nghiệp vụ không?

Một nâng cấp có thể:

```text
RTO thấp:
    Service restart nhanh.

RPO xấu:
    Redis khôi phục snapshot quá cũ.

Correctness xấu:
    Counter quay lùi, token revocation mất,
    consumer xử lý message trùng.
```

Do đó, `PING` thành công sau rollback không đủ chứng minh upgrade/recovery thành công về nghiệp vụ.

### 29.1. Chia dữ liệu theo criticality

| Loại dữ liệu | Có thể rebuild? | Nguy cơ khi restore cũ |
|---|---|---|
| Product cache | Thường có | Cache miss/stale |
| Analytics cache | Tùy nguồn | Sai hoặc chậm dashboard |
| Session | Tùy kiến trúc | Mất session hoặc hồi sinh session |
| Rate-limit counter | Có thể không | Counter quay lùi |
| Inventory reservation | Thường cần nguồn bền vững | Đặt chỗ lặp/mất |
| Payment ledger | Không nên coi là cache | Mất/đảo trạng thái giao dịch |
| Stream consumer group | Cần recovery/idempotency | Message trùng/mất ACK state |
| Token revocation | Security-sensitive | Key đã DEL có thể xuất hiện lại |

Nếu Redis chỉ là cache, đôi khi rollback data bằng cách xóa/rebuild cache sẽ an toàn hơn phục hồi snapshot cũ có stale state. Nếu Redis là source-of-truth, backup/replication/transaction strategy phải được đánh giá chặt.

---

## 30. Quan sát ngay trước khi nâng cấp

Bảo đảm có dashboard và alerting đã hoạt động trước rollout.

### 30.1. Server signals

```redis
INFO server
INFO clients
INFO stats
INFO commandstats
INFO memory
INFO persistence
INFO replication
```

Trong Cluster thêm:

```redis
CLUSTER INFO
CLUSTER NODES
```

Các trường cụ thể khác theo Redis version/vendor.

### 30.2. Application signals

Ví dụ:

```text
HTTP p50/p95/p99
Redis command RTT p95/p99
Connection timeout/reconnect
Pool wait/active
Cache hit/miss
Serializer exceptions
NOSCRIPT/CROSSSLOT/NOPERM/READONLY errors
Stream pending/lag and ACK throughput
Pub/Sub listener reconnect
Business operation success/error
```

### 30.3. Dùng threshold để dừng rollout

Không nên quyết định chỉ bằng “deployment success” trong orchestrator.

Ví dụ một **mẫu chính sách**, không phải ngưỡng chuẩn:

```text
Stop rollout if:
    Redis command timeout rate vượt baseline rõ rệt.
    HTTP p99 vượt SLO liên tiếp trong cửa sổ quan sát.
    New serializer errors > 0.
    Cluster state degraded.
    Stream pending backlog tăng mà không hồi phục.
    Cache miss spike đe dọa database.
    Security NOPERM/TLS handshake errors xuất hiện.
```

Ngưỡng cụ thể phải dựa trên baseline/SLO của hệ thống.

---

## 31. Phương pháp canary app khi nâng Spring Data Redis

Một quy trình:

```text
Build ứng dụng mới
       |
       v
Deploy 1% traffic vào canary
       |
       +--> So sánh metrics với baseline
       |
       +--> Đọc data cũ
       |
       +--> Ghi data theo compatibility contract
       |
       +--> Không lỗi serializer/Redis commands?
       |
       v
5% -> 25% -> 50% -> 100% theo runbook
```

### 31.1. Canary có thể làm hỏng data cho old app

Nếu ứng dụng mới bắt đầu **ghi value schema V2** mà ứng dụng cũ chỉ hiểu V1, ngay cả 1% canary cũng có thể làm old app fail khi đọc một key do canary ghi.

Vì vậy canary deployment cần hỏi:

```text
Old readers read new writes?
New readers read old writes?
Keys namespace chung hay tách?
Cache null marker compatible?
TTL semantics same?
Repository index updates compatible?
```

Chỉ tăng traffic sau khi contract được kiểm chứng.

### 31.2. Không gộp nhiều biến lớn trong cùng canary

Nếu cùng lúc:

```text
Upgrade Spring Boot
Upgrade Lettuce
Upgrade Redis Server
Change serializer
Change cache key naming
Enable RESP3
```

và p99 tăng, khó biết nguyên nhân.

Tách thành các đợt có compatibility states rõ ràng khi có thể.

### 31.3. Canary traffic phải đủ đại diện

Một canary nhận 1% traffic có thể không gặp:

- Rare Streams messages.
- Large Repository entities.
- Cluster slots ít truy cập.
- Lua code path theo feature flag.
- High-concurrency race.
- End-of-day batch jobs.

Do đó, ngoài canary HTTP cần có targeted synthetic tests và quan sát một chu kỳ nghiệp vụ đủ dài.

---

## 32. Hành vi auto-reconnect và timeout có thể thay đổi

Sau khi nâng driver, ngay cả API `redis.opsForValue().set(...)` giống hệt, kết quả runtime có thể thay đổi vì:

- Command timeout option.
- Connect timeout.
- Auto reconnect.
- In-flight command queue.
- Retry policy tầng application.
- Cluster topology refresh.
- Connection close/shutdown semantics.
- Pool max wait.
- Event loop resources.

### 32.1. Không coi timeout là “command chưa chạy”

Ví dụ:

```text
App gửi INCR.
Redis đã tăng counter.
Connection đứt trước response.
App nhận timeout.
```

Nếu Spring Retry/Resilience4j hoặc code tự gọi lại `INCR`, counter có thể tăng hai lần.

Nâng driver có thể thay đổi tần suất/hình thức exception nhưng không loại bỏ bài toán unknown outcome. Cần idempotency khi retry mutations.

### 32.2. Test reconnect sau failover

Trong test environment:

1. Gửi workload bình thường.
2. Thực hiện failover được phép.
3. Đo reconnect time.
4. Xác nhận new writes thành công.
5. Kiểm tra có duplicate side effects không.
6. Kiểm tra Pub/Sub resubscription.
7. Kiểm tra Streams pending recovery.
8. Đảm bảo không giữ vô hạn command queue.
9. Đo HTTP p99 và timeout budget.

### 32.3. Connection pooling: không tự tăng pool size để giải quyết mọi lỗi

Lettuce có khả năng chia sẻ connection cho nhiều sync/async operations trong các điều kiện phù hợp; Jedis có những đặc tính khác. Transaction/blocking commands có thể yêu cầu quản lý connection khác.

Tăng pool size có thể làm:

- Nhiều Redis client connections.
- Tăng resource usage.
- Không sửa server CPU bottleneck.
- Che một connection leak.
- Tăng contention.

Đo trước khi tối ưu pool; xem behavior được khuyến nghị cho driver/Spring version đích.

---

## 33. Java runtime và security dependency upgrades

Đôi khi lý do nâng Redis stack là vá vulnerability.

Không nên chỉ nâng Lettuce/Netty trong production rồi bỏ qua:

- Minimum JDK version.
- TLS provider compatibility.
- Security patches ở transitive libraries.
- Object deserialization risks.
- Netty native transport.
- Certificate/hostname validation.
- CVEs ở runtime/container OS.
- Supported maintenance window.

Nếu chuyển JDK major version, có thể ảnh hưởng GC pause, TLS cipher suites, DNS caching, memory footprint và startup behavior. Cần tách ảnh hưởng JDK khỏi ảnh hưởng Redis driver khi phân tích.

### 33.1. Không dùng JDK native serialization cho dữ liệu không tin cậy nếu chưa đánh giá

Nếu hệ thống từng dùng `JdkSerializationRedisSerializer`, cần đánh giá security policy về Java deserialization. Đổi format là một migration có rủi ro, không chỉ thay dependency.

Không “bật lại deserialization rộng” để xử lý data compatibility khi không kiểm soát nguồn bytes và class allowlist.

---

## 34. Rollback: chia ba loại

### 34.1. Application rollback

Đổi deployment Spring Boot JAR về build cũ.

Có thể làm nhanh **nếu**:

- Old app vẫn đọc được Redis data do new app ghi.
- Không có schema/serializer/key format breaking writes.
- Redis Server mới vẫn hỗ trợ old driver.
- Không dùng command/function mới mà old app không hiểu.
- Không có business workflow state chỉ new app xử lý được.

Nếu một trong các điều kiện không đúng, rollback app có thể tạo lỗi mới.

### 34.2. Server rollback

Đổi Redis Server binary/image về version cũ.

Phải kiểm tra:

- Official downgrade support.
- Persistence format compatibility.
- ACL/config compatibility.
- Cluster/replication mixed-version restrictions.
- Data written after upgrade.
- Backups và restore path.

Không mặc định an toàn.

### 34.3. Data rollback

Phục hồi snapshot/RDB/AOF hoặc dataset từ thời điểm trước.

Đây là thao tác có thể làm **mất mọi writes sau snapshot** hoặc tạo dữ liệu nghiệp vụ stale, nên phải được phê duyệt theo RPO/correctness plan.

### 34.4. Forward fix

Trong một số trường hợp downgrade không được hỗ trợ, chiến lược an toàn nhất là **giữ Redis Server đích** rồi sửa cấu hình/app hoặc nâng driver, thay vì ép data file mới vào Redis cũ.

Runbook cần định nghĩa khi nào chọn forward fix và khi nào chấp nhận restore state.

---

## 35. Khi nào cần dừng rollout ngay?

Các tín hiệu nghiêm trọng:

- Dữ liệu Redis không được load sau upgrade.
- Server báo persistence corruption hoặc backup không hợp lệ.
- Cluster mất slot coverage.
- Primary/replica không thể sync trong thời gian chấp nhận.
- `NOPERM` cho business commands thiết yếu.
- Serializer exceptions trên dữ liệu production cũ.
- Cache key namespace bị thay đổi ngoài ý muốn.
- Stream consumer không ACK và PEL tăng không giới hạn.
- Business write duplicate/missing.
- `READONLY`/`MOVED` errors không được client xử lý.
- p99/timeout vi phạm SLO ở mức kéo dài.
- Memory/CPU/RSS tăng tới giới hạn, eviction bất thường.
- TLS failure hoặc authentication outage.
- Unexpected reprocessing of operations có side effects ngoài Redis.

### 35.1. Không chữa lỗi compatibility bằng FLUSHALL

Một ứng dụng mới không đọc được cache có thể khiến người vận hành nghĩ:

```redis
FLUSHALL
```

là giải pháp.

Trên Redis chia sẻ hoặc Redis chứa state, thao tác này có thể phá hủy dữ liệu không thể khôi phục. Phải xác định keyspace, nguồn dữ liệu và policy trước khi xóa.

Nếu chỉ có cache tái tạo được, có thể invalidate **namespace riêng** hoặc đổi versioned key prefix theo runbook.

---

## 36. Diễn tập rollback trước khi nâng thực

Một kế hoạch có khả năng xem xét cần chứng minh rollback path trên staging.

Ví dụ:

```text
1. Load dataset bằng Redis Server A.
2. Chụp backup A và xác minh restore.
3. Nâng Redis B.
4. Chạy ứng dụng mới, tạo writes thật trong staging.
5. Cố rollback app, kiểm tra data compatibility.
6. Kiểm tra server downgrade support theo official guide.
7. Nếu cần restore backup A, xác định writes sau backup sẽ ra sao.
8. Chạy reconciliation giả lập.
9. Đo RTO và RPO thực tế.
10. Ghi rõ những điều kiện rollback KHÔNG được phép.
```

**Một rollback plan chưa được thử với dữ liệu cũ thật hoặc đại diện không phải bằng chứng rollback có thể thực hiện an toàn.**

---

## 37. Migration không tương thích: dùng expand-and-contract

Khi đổi serializer/key namespace hoặc event schema, có thể áp dụng một chiến lược nhiều pha:

```text
Phase 1 - Expand:
    New readers đọc V1 và V2.
    Old writers vẫn ghi V1.

Phase 2 - Transition:
    Tùy contract, chuyển writes sang V2.
    Đảm bảo old readers không bị hỏng
    hoặc dừng old readers trước.

Phase 3 - Contract:
    Sau khi không còn V1 readers/writers,
    dọn compatibility code và old data.
```

Cần thiết kế chính xác thứ tự dựa vào **khả năng đọc/ghi của từng version**.

### 37.1. Không dual-write tùy tiện

Nếu code ghi cùng dữ liệu vào hai key namespaces:

```text
SET v1:key
SET v2:key
```

hai lệnh riêng có thể thành công một phần khi Redis timeout. Có thể cần Lua/transaction same-slot hoặc reconciliation, nhưng cũng phải xét khác hash slots nếu key format đổi.

Dual-write là một migration architecture có trạng thái, không phải “ghi gấp đôi cho chắc”.

### 37.2. Event schema changes

Với Redis Streams hoặc Pub/Sub:

- Gắn version vào event envelope.
- New consumers đọc cả V1/V2 trước khi producers phát V2.
- Tránh xóa V1 decoder khi Stream còn V1 entries/pending.
- Retention phải đủ để drain/reprocess.
- Có kế hoạch DLQ và re-drive.

Nếu backward-compatible không thể, cần tách Stream/channel version và có cutover rõ.

---

## 38. Deploy Redis Server theo các mốc kiểm soát

Một runbook cấp cao cho server upgrade:

### Preflight

```text
[ ] Compatibility matrix approved
[ ] Release notes reviewed
[ ] Backup completed + restore test passed
[ ] RPO/RTO and rollback choices signed off
[ ] Redis topology healthy
[ ] Replication lag within policy
[ ] Persistence/disk/memory headroom available
[ ] Metrics and alerts active
[ ] Test suite passed for candidate versions
[ ] Client/network/TLS readiness confirmed
```

### During change

```text
[ ] Freeze conflicting admin operations
[ ] Follow topology-specific official rolling steps
[ ] Limit concurrent node restarts
[ ] Verify node readiness and data after each node
[ ] Confirm replication/slot health
[ ] Keep application errors within threshold
[ ] Record exact versions, timestamps, commands and state
[ ] Pause if stop conditions occur
```

### Post-change

```text
[ ] All nodes on intended version
[ ] No unexpected mixed-version state
[ ] Cluster/Sentinel health stable
[ ] App smoke tests pass
[ ] Old data can be read
[ ] Redis Cache metrics stable
[ ] Streams/PubSub work
[ ] p95/p99/timeout/eviction near baseline
[ ] Persistence successful
[ ] Backup after upgrade completed
[ ] Incident/runbook notes documented
```

Bộ checklist là khung điều phối; chi tiết thao tác `CLUSTER FAILOVER`, restart hoặc resharding phải lấy từ tài liệu cho phiên bản/topology cụ thể.

---

## 39. Deploy ứng dụng Spring theo các mốc kiểm soát

### Preflight

- Build immutable artifact với dependency versions đã khóa.
- Xác nhận Spring Boot/JDK/Spring Data Redis/driver compatibility.
- Dùng Testcontainers hoặc Redis test tương đương production.
- Chạy compatibility test trên old data.
- Chạy serialization, cache, repository, Stream và Lua tests.
- Đảm bảo có rollback app binary cùng schema strategy.
- Chuẩn bị dashboard và stop conditions.

### Canary

- Triển khai ít instances.
- Kiểm tra actual Redis endpoint.
- Đọc dữ liệu đã tồn tại.
- Ghi key test ở namespace riêng.
- Test ACL/TLS/auth.
- Theo dõi errors và latency.
- Theo dõi old/new app data interoperability.

### Rollout

- Tăng tỷ lệ traffic dần.
- Không thay key naming/payload schema ngoài kế hoạch.
- Giới hạn background job concurrency nếu cần.
- Theo dõi consumer group assignments và pending.
- Bảo đảm startup/reconnect không publish duplicate business events.

### Verify

- So sánh metrics với baseline.
- Kiểm tra data consistency.
- Kiểm tra source-of-truth.
- Theo dõi ít nhất một vòng workload quan trọng.
- Xác nhận rollback window và expiry của compatibility code.

---

## 40. Những thay đổi nhỏ gây lỗi lớn

### 40.1. Default serializer thay đổi

App mới đọc giá trị cũ:

```text
SerializationException
```

Nguyên nhân có thể là serializer/Java type schema, không phải Redis server mất dữ liệu.

### 40.2. Redis connection host thay đổi

Boot property bị bỏ qua làm app kết nối Redis khác môi trường.

### 40.3. TLS certificate mismatch

Cluster seed node kết nối được nhưng node được discover không hợp lệ với certificate hoặc DNS.

### 40.4. Cluster redirects tăng

New Lettuce config không refresh topology phù hợp hoặc advertised addresses không route được.

### 40.5. NOSCRIPT sau restart

Lua script SHA cache mất; client phải load/fallback đúng.

### 40.6. Pub/Sub không tự replay

Subscriber reconnect xong nhưng đã bỏ qua notifications trong downtime.

### 40.7. Stream pending bị bỏ quên

Worker chỉ đọc `>` mà không reclaim pending từ consumer cũ.

### 40.8. ACL NOPERM

Server/driver mới gọi command khởi tạo hoặc application code path cần quyền chưa được cấp.

### 40.9. Cache stampede

Versioned namespace mới làm toàn bộ cache cold, database quá tải.

### 40.10. Persistence file không downgrade được

Redis binary cũ không đọc file mới sau nâng cấp, server rollback thất bại.

### 40.11. Retry tạo duplicate

Driver/app reconnect rồi retry `INCR` hoặc `XADD *` mà không có request ID.

### 40.12. Timeouts khác

New driver/client defaults khiến những request trước đây hoàn thành trở thành timeout hoặc queue lâu.

### 40.13. Redis Module không tương thích

Function/module hoặc custom command có thay đổi, dù `GET`/`SET` vẫn hoạt động.

### 40.14. Repository index không được xây lại

Entity có thể đọc qua ID nhưng query theo indexed field không ra kết quả.

### 40.15. Memory/eviction tăng

Encoding/allocator/workload thay đổi hoặc dataset mới tạo thêm key/index; làm evict state không nên evict.

### 40.16. Stale config

New config property không được bind; app dùng Redis connection factory mặc định ngoài dự kiến.

---

## 41. Kiểm thử lỗi kết nối sau khi gửi command

Một kịch bản quan trọng trong nâng driver:

```text
App gửi INCR counter.
Redis thực thi.
Network mất response.
App nhận timeout.
```

Nếu app retry `INCR` vô điều kiện, có thể tăng hai lần.

Một test regression đúng cần phân biệt:

1. Request **chưa tới Redis**, nên retry cần thực thi.
2. Request **đã thực thi nhưng response bị mất**, nên retry phải không gây duplicate effect.
3. Primary failover khiến state/receipt có thể rollback.
4. Lệnh `EXEC` đã chạy nhưng reply không nhận.
5. `XADD *` tạo event trùng nếu publisher retry.
6. Consumer nhận duplicate Streams messages.

Cơ chế:

```text
Stable requestId
+ Atomic dedupe/receipt cùng Redis slot nếu side effect chỉ ở Redis
+ Durable idempotency ở source-of-truth nếu side effect ở SQL/payment
+ Backoff và bounded retries
+ Reconciliation cho unknown outcomes
```

**Đổi driver không chữa được lỗi exactly-once ở nghiệp vụ.**

---

## 42. Đo performance regression đúng cách

Sau nâng cấp, một benchmark ngắn không đủ. Đo nhiều lớp:

| Chỉ số | Ý nghĩa |
|---|---|
| Redis command p50/p95/p99 | Round-trip ở client |
| Server `INFO commandstats` | Count/mean execution |
| HTTP p95/p99 | Tác động đến người dùng |
| CPU/RSS Redis | Tải server |
| JVM CPU/GC | Tải ứng dụng |
| Commands/request | Write/read amplification |
| Hit/miss | Hiệu quả cache |
| Network bytes/s | Wire overhead |
| Timeout/reconnect | Sự cố client |
| Stream pending/lag | Worker throughput |
| Replication lag | HA risk |
| Persistence time/errors | Durability |
| Error classes | Compatibility failures |

### 42.1. Cùng workload trước và sau

Cần cùng:

```text
Dataset size
Read/write mix
Key distribution/hot keys
Payload sizes
TTL
TLS
Topology
Concurrency
Benchmark duration
Persistence configuration
```

Nếu đổi cả Redis version và dataset size, không thể kết luận hiệu năng chênh lệch do Redis upgrade.

### 42.2. Tăng throughput có thể làm p99 xấu hơn

Một bản driver mới có thể pipeline/queue nhiều commands hơn, tăng throughput nhưng làm p99 dưới tải cao kém đi.

Với user-facing API, mục tiêu là **SLO phù hợp**, không phải commands/s tối đa trong benchmark.

---

## 43. Ví dụ kế hoạch nâng cấp có mốc dừng

Giả sử hệ thống dùng:

```text
Spring Boot App
Spring Data Redis
Lettuce
Redis Cluster (3 primary, có replicas)
Redis Cache + Redis Streams
```

Đây là một kế hoạch **khung**, không phải thao tác production được áp dụng ngay:

**Phase A — Investigation**

- Ghi version hiện tại/đích.
- Xem compatibility matrix.
- Đọc release notes cả hai tầng.
- Xác định cache/Streams/schema/serializer.
- Thử old/new compatibility trên staging.

**Phase B — Prepared application**

- Nếu được hỗ trợ, deploy app/driver tương thích với cả server old/new.
- Giữ serializer/keys unchanged.
- Kiểm tra canary + telemetry.

**Phase C — Redis Server rollout**

- Backup/restore test trước.
- Nâng nodes theo official Cluster runbook.
- Giới hạn concurrency.
- Kiểm tra slots/replication/errors sau mỗi node.

**Phase D — Stabilize**

- Đo p99, errors, cache hit, Stream lag, memory.
- Bảo đảm consumer pending recovery.
- Tạo post-upgrade backup.
- Kết thúc change window theo policy.

**Phase E — Cleanup**

- Chỉ loại compatibility code sau khi không còn old readers/writers.
- Dọn old cache namespace khi đã an toàn.
- Cập nhật runbook/SBOM/alerts.

Nếu App mới không thể chạy trên Redis cũ, Phase B phải được thay thế bằng kế hoạch có trạng thái trung gian khác được vendor hỗ trợ. Không suy rằng sequence này luôn hợp lệ.

---

## 44. Bài thực hành 1 — Lập compatibility matrix

Cho stack giả định:

```text
Spring Boot version A
Spring Data Redis version B
Lettuce version C
JDK version D
Redis Server version E
```

Yêu cầu:

1. Viết bảng old/target versions.
2. Liệt kê tài liệu chính thức phải đọc.
3. Xác định cặp versions cần integration test.
4. Ghi rõ tổ hợp nào không thể chạy mixed-version.
5. Phân biệt điều đã xác minh với điều chưa được đo.
6. Đề xuất một upgrade path có intermediate states hợp lệ.

Không dùng số phiên bản tùy đoán để khẳng định support; phải dựa trên tài liệu thực của phiên bản được chọn.

## 45. Bài thực hành 2 — Dữ liệu cũ và serializer mới

Tạo một app thử nghiệm V1 ghi cache/DTO vào Redis.

Sau đó app V2 dùng serializer mới:

1. Đọc entry từ V1.
2. So sánh key bytes và value bytes.
3. Xác định type metadata/class name differences.
4. Thiết kế backward reader hoặc versioned key namespace.
5. Kiểm tra old app đọc new writes được không.
6. Đề xuất migration nếu Redis là source-of-truth.

Giải thích vì sao server Redis vẫn chạy bình thường mà application có thể báo lỗi deserialize.

## 46. Bài thực hành 3 — Spring Cache upgrade

Tạo `@Cacheable` service:

```java
@Cacheable(cacheNames = "products", key = "#productId")
public ProductDto getProduct(String productId) {
    return database.findProduct(productId);
}
```

Chạy V1 để tạo entries, đổi sang V2 và kiểm tra:

```text
Key prefix
Serializer
TTL
Null behavior
Hit/miss rate
DB QPS
```

Lập giải pháp nếu app mới chuyển namespace khiến cold cache.

## 47. Bài thực hành 4 — Redis Repository data compatibility

Tạo entity có:

```text
@RedisHash
@Id
@Indexed
@TimeToLive
```

Trên Redis test:

1. V1 lưu entity.
2. V2 đọc `findById`.
3. V2 query theo indexed field.
4. V2 sửa indexed field.
5. V2 xóa entity.
6. Kiểm tra TTL và index cleanup.
7. Kiểm tra old app đọc data nếu rollback cần.

Bài tập đòi hỏi test dữ liệu từ V1 thật, không chỉ dữ liệu V2 tự tạo.

## 48. Bài thực hành 5 — Redis Server backup/restore

Trong Redis test cô lập:

1. Ghi data mẫu.
2. Tạo snapshot theo cơ chế được phép.
3. Xác minh backup có thể restore.
4. Ghi Redis version/format metadata.
5. Nâng Redis test sang target.
6. Chạy smoke tests.
7. Tạo thêm writes.
8. Nghiên cứu downgrade support chính thức.
9. Mô tả data loss nếu restore backup trước nâng cấp.

Không tự chạy downgrade production để “thử xem file có đọc được không”.

## 49. Bài thực hành 6 — Sentinel failover

Trong test cluster Sentinel được kiểm soát:

1. Ghi trạng thái primary/replica.
2. Tạo workload read/write.
3. Mô phỏng failover theo runbook.
4. Xác nhận `LettuceConnectionFactory`/driver reconnect.
5. Xác nhận writes tới new primary.
6. Đo timeout/p99.
7. Test Pub/Sub resubscribe.
8. Phân tích rủi ro writes chưa replicated.

## 50. Bài thực hành 7 — Redis Cluster routing

Trong Redis Cluster test:

1. Chuẩn bị key families với hash tags.
2. Ghi các keys thuộc nhiều slots.
3. Nâng/tái khởi động một node test theo tài liệu.
4. Quan sát `MOVED`/topology refresh.
5. Test `MGET` với same-slot keys.
6. Test `CROSSSLOT` có chủ đích.
7. Kiểm tra health/slot coverage.
8. Không ghi đè dữ liệu thuộc slots khác.

## 51. Bài thực hành 8 — Pub/Sub và Streams sau reconnect

Tạo:

```text
RedisMessageListenerContainer subscriber
Stream consumer group
```

Trong lab:

1. Publish message trước và sau reconnect.
2. Quan sát Pub/Sub không replay offline messages.
3. XADD Stream entry.
4. XREADGROUP, làm pending.
5. Reconnect worker.
6. XPENDING và claim/reprocess.
7. XACK đúng entry.
8. Đảm bảo business handler idempotent.

Giải thích tại sao hai mô hình cần chiến lược recovery khác nhau.

## 52. Bài thực hành 9 — Lua script cache

Trong Redis test:

1. Gọi `RedisScript` từ Spring Data Redis.
2. Kiểm tra results.
3. Restart server test để thay đổi script-cache state.
4. Gọi lại script.
5. Xác minh Spring API handling `NOSCRIPT`/fallback theo phiên bản.
6. Test ACL permissions và serialization của KEYS/ARGV.

Không giả định mọi script SHA đã tồn tại trên new primary sau failover.

## 53. Bài thực hành 10 — Canary và dashboard

Dựng hai app instances V1/V2 trên môi trường test cùng Redis phù hợp.

Theo dõi:

```text
HTTP p95/p99
Redis timeouts
Serializer errors
Cache hit ratio
Stream pending
ACL errors
Redis used_memory
Redis node CPU
```

Tạo stop conditions cụ thể trước khi rollout. Cố ý gây serializer incompatibility trong lab, xác định metric nào phát hiện nhanh nhất.

## 54. Bài thực hành 11 — Data rollback không phải app rollback

Timeline giả định:

```text
10:00 Backup Redis A.
10:10 Nâng Redis B.
10:20 100 đơn hàng mới được ghi.
10:30 Redis B gặp lỗi.
```

Hãy phân biệt:

- Rollback Spring application.
- Downgrade Redis server binary.
- Restore Redis data backup 10:00.
- Forward fix.

Giải thích cần xử lý 100 đơn hàng mới thế nào trước khi chấp nhận rollback state.

## 55. Bài thực hành 12 — Migration expand-and-contract

Cho hai format:

```text
v1: Java native serialized object
v2: JSON with schemaVersion=2
```

Thiết kế:

1. Versioned key namespace.
2. Backward read.
3. Mixed readers/writers.
4. TTL preservation.
5. Data backfill nếu cần.
6. Retention của old keys.
7. Rollback window.
8. Migration monitoring.

Lưu ý trường hợp Spring Cache nulls và Repository indexes.

## 56. Bài thực hành 13 — Fault injection connection loss

Trong test adapter/proxy:

1. Gửi `INCR` thành công ở Redis.
2. Cố tình làm client thấy timeout.
3. Retry nguyên lệnh và quan sát double increment.
4. Thay bằng idempotency request ID + atomic receipt.
5. Mô phỏng failover/receipt rollback.
6. Ghi rõ những guarantee còn thiếu sau nâng driver.

Mục tiêu là kiểm tra **ngữ nghĩa operation** chứ không chỉ reconnect thành công.

## 57. Bài thực hành 14 — Báo cáo sau nâng cấp

Viết report gồm:

```text
Versions old -> target
Change window
Topology before/after
Release notes reviewed
Dependency graph
Tests passed/failed
Backup location and restore test result
RPO/RTO assumptions
Canary progression
HTTP and Redis p95/p99
Redis error classes/timeouts
Cache hit ratio
Stream lag/PEL
Persistence/replication status
Rollback/forward-fix decision
Known limitations and follow-ups
```

Tách kết quả đo được khỏi giả định; không ghi “zero data loss guaranteed” nếu hệ thống không có cơ chế và bằng chứng hỗ trợ.

---

## 58. Những ngộ nhận thường gặp

### “Nâng Redis Server xong app tự tương thích”

Không. Client/protocol, commands, serialization và Redis topology đều cần kiểm chứng.

### “Nâng Lettuce/Jedis không cần test vì chỉ là networking library”

Không. Driver quản lý reconnect, timeout, decoding, cluster routing và subscriptions.

### “Spring Boot BOM là optional, tôi cứ ép mọi library lên latest”

Có thể tạo dependency conflicts hoặc unsupported combinations.

### “App start và PING pass là migration thành công”

Không. Cần old-data reads, cache, repository, scripts, Streams và failure-path tests.

### “Redis có RDB nên downgrade server lúc nào cũng được”

Không. File persistence do bản mới ghi có thể không đọc được bằng bản cũ.

### “Restore pre-upgrade backup là rollback không mất dữ liệu”

Không nếu đã có writes sau snapshot.

### “Nâng Redis Cluster chỉ cần restart mọi container”

Có thể mất availability khi restart primary/replica cùng lúc và phá slot coverage.

### “Canary 1% không thể gây lỗi dữ liệu”

Canary writer có thể ghi schema mới khiến old readers không đọc được.

### “Đổi cache key prefix chỉ ảnh hưởng performance nhẹ”

Có thể gây cache stampede và database overload; cần kế hoạch warm-up.

### “RESP3/ACL/TLS đã kết nối một node thì mọi node đều ổn”

Cluster endpoints/certificates/permissions cần test trên nhiều slots.

### “Lua SHA luôn tồn tại sau failover”

Script cache có thể không còn trên node mới, cần handling `NOSCRIPT`.

### “Pub/Sub sẽ tự nhận lại message trong thời gian downtime”

Pub/Sub thường không có replay.

### “Redis Stream đã có ACK nên không cần xử lý pending sau restart”

PEL/recovery và idempotency vẫn cần.

### “Retry sau timeout luôn an toàn nếu lệnh atomic”

Atomic command có thể được thực thi hai lần khi retry; cần idempotency.

### “Lỗi NOPERM thì bật admin privilege là xong”

Mở rộng quyền không kiểm soát có thể gây rủi ro bảo mật.

### “p99 tăng sau nâng cấp nên chắc Redis bản mới chậm”

Có thể do network, driver queue, serializer, cache miss hoặc topology. Cần đo nhiều lớp.

### “Một rollback script là đủ”

Cần rollback binary, config, schema và data theo cùng một strategy có thể thực hiện được.

---

## 59. Checklist quyết định triển khai

Trước khi bắt đầu upgrade, xác nhận:

- [ ] Đã liệt kê versions thực tế: Redis Server, Spring Boot, Spring Data Redis, Lettuce/Jedis, JDK?
- [ ] Đã xem compatibility matrix và release notes chính thức của các versions đích?
- [ ] Đã biết topology standalone/Sentinel/Cluster/managed?
- [ ] Đã kiểm tra mixed-version states được vendor hỗ trợ?
- [ ] Đã inventory Redis commands và features dùng thực tế?
- [ ] Đã có test đọc dữ liệu từ bản cũ bằng bản mới?
- [ ] Đã kiểm tra serializers, key naming, null caching, TTL và repository indexes?
- [ ] Đã kiểm tra scripting/ACL/RESP/TLS?
- [ ] Đã kiểm tra Streams PEL/reconnect và Pub/Sub resubscription?
- [ ] Đã test multi-key/Cluster redirects?
- [ ] Đã tạo backup và thử restore thành công?
- [ ] Đã hiểu RDB/AOF backward compatibility và downgrade restrictions?
- [ ] Đã có RPO/RTO/correctness requirements?
- [ ] Đã định nghĩa rollback app, server, data và forward-fix riêng?
- [ ] Đã đo baseline p95/p99, timeout, hit/miss, CPU/RSS, replication lag?
- [ ] Đã có canary/rolling plan và stop conditions?
- [ ] Đã kiểm tra compatibility của old/new writers trong cửa sổ mixed app versions?
- [ ] Đã có cách xử lý cache stampede và dataset migration?
- [ ] Đã kiểm thử failover/connection loss theo môi trường phù hợp?
- [ ] Đã có on-call ownership, change window và cách ghi nhận từng bước?
- [ ] Đã có post-upgrade backup, smoke tests và monitoring window?
- [ ] Đã phân loại điều gì được phép làm khi rollback và điều gì không?

**Không phải cứ tick đủ một danh sách là an toàn tuyệt đối**. Giá trị của checklist là buộc nhóm triển khai chứng minh các giả định quan trọng bằng dữ liệu và bài kiểm thử.

## 60. Câu hỏi tự đánh giá

1. Spring Data Redis và Lettuce/Jedis có vai trò gì khác nhau?
2. Vì sao Redis Server version mới không tự quyết định Java client version?
3. Tại sao cần xem JDK/Spring Boot/Spring Data release train cùng nhau?
4. Một Spring Boot BOM giúp tránh vấn đề gì?
5. Vì sao override riêng Lettuce có thể gây lỗi runtime?
6. Nên ghi những phiên bản nào trong compatibility matrix?
7. “PING pass” chưa kiểm tra được những tính năng nào?
8. RESP2/RESP3 ảnh hưởng đường kết nối ra sao?
9. Vì sao TLS seed node pass chưa chứng minh Redis Cluster toàn bộ hoạt động?
10. ACL `NOPERM` nên được điều tra như thế nào?
11. Dữ liệu JDK serialized có thể gặp lỗi gì khi đổi Java class package?
12. Cache value JSON với type metadata có những rủi ro gì khi đổi serializer?
13. Key serializer có ảnh hưởng Redis Cluster hash slot không?
14. Vì sao `@Cacheable` có thể tạo cache stampede sau đổi prefix?
15. Tại sao Redis Repository có thể dùng nhiều keys cho một entity?
16. Test data được V1 ghi và V2 đọc quan trọng ở đâu?
17. Vì sao mixed old/new app có thể phá tương thích dù canary ít traffic?
18. Script cache có thể bị ảnh hưởng khi Redis restart thế nào?
19. Redis Streams PEL và Pub/Sub có cách recovery giống nhau không?
20. Vì sao pipeline không tự biến một batch thành transaction?
21. Sau timeout `EXEC`, có thể kết luận transaction chưa chạy không?
22. Khi driver reconnect, vì sao retry `INCR` có thể làm tăng hai lần?
23. Một Redis standalone duy nhất có thật sự rolling zero-downtime upgrade không?
24. Sentinel failover có loại trừ hoàn toàn mất write do async replication không?
25. Khi upgrade Redis Cluster, tại sao không restart primary và replica cùng lúc?
26. Lỗi `MOVED`/`ASK` liên quan client topology refresh như thế nào?
27. RDB do Redis mới ghi có chắc đọc được bằng Redis cũ không?
28. Vì sao restore snapshot cũ có thể làm mất dữ liệu nghiệp vụ mới?
29. App rollback và data rollback khác nhau như thế nào?
30. Khi nào nên dùng forward fix thay vì downgrade?
31. Monitoring nào giúp phát hiện serializer incompatibility?
32. Vì sao Redis ops/s và HTTP p99 đều cần đo?
33. Tại sao phải có stop conditions trước khi bắt đầu canary?
34. Managed Redis có thể giới hạn những thao tác nâng cấp nào?
35. Một runbook đáng tin cần chứng minh điều gì trước khi production cutover?

## 61. Ghi nhớ

- **Nâng Redis là thay đổi hệ thống có trạng thái**, liên quan Redis Server, Spring Data Redis, Lettuce/Jedis, Spring Boot/JDK, protocol, topology và data format.
- **Compatibility matrix và official release notes** là điểm bắt đầu; không có “latest everything” luôn đúng.
- **Ưu tiên dependency set được quản lý bởi Spring Boot BOM**; chỉ override driver/library khi có bằng chứng support.
- **Tương thích kết nối khác tương thích nghiệp vụ.** `PING` thành công không kiểm tra cache, serializer, Repository, Lua, Streams, Pub/Sub, Cluster và failover.
- **Serializer/key format là hợp đồng dữ liệu.** App mới phải đọc được data cũ; old app đọc new writes hay không quyết định khả năng rollback.
- **Không đổi schema, Redis Server, driver và key naming cùng lúc** nếu có thể tách thành những giai đoạn được kiểm thử.
- **Redis Cluster/Sentinel upgrades cần topology-aware rollout**, replication health, limited concurrency và kiểm tra reconnect/slot routing.
- **Pub/Sub không tự replay**, Redis Streams cần PEL/ACK recovery và idempotency, Lua script cache có thể mất sau restart.
- **Redis transaction và command atomicity không chống duplicate retries** sau timeout; unknown outcomes cần request ID/receipt/reconciliation.
- **Backup RDB/AOF là cần thiết, nhưng không chứng minh rollback server hoặc data an toàn.** File mới có thể không backward-compatible; snapshot cũ có thể mất writes sau cutover.
- **Đặt RPO/RTO và correctness cạnh performance.** Đừng đánh đổi dữ liệu nghiệp vụ chỉ để deployment nhanh.
- **Canary cần khả năng tương thích dữ liệu mixed versions**, metrics rõ ràng và stop conditions trước khi mở rộng traffic.
- **Kiểm thử trên Redis thật theo topology production**, có old/new data, failover, reconnect, Lua, serializer, ACL/TLS và load.
- **Một nâng cấp hoàn tất khi dữ liệu được đọc đúng, hệ thống ổn định và rollback/forward-fix path đã rõ**, không chỉ khi container/JAR mới ở trạng thái running.

### Tài liệu tham khảo chính thức

- [Redis — Documentation](https://redis.io/docs/latest/)
- [Redis — Redis configuration](https://redis.io/docs/latest/operate/oss_and_stack/management/config/)
- [Redis — Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis — Redis Cluster](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/)
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Redis — Security](https://redis.io/docs/latest/operate/oss_and_stack/management/security/)
- [Redis — ACL](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/)
- [Redis — HELLO](https://redis.io/docs/latest/commands/hello/)
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/)
- [Redis — EVALSHA](https://redis.io/docs/latest/commands/evalsha/)
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/)
- [Redis — XPENDING](https://redis.io/docs/latest/commands/xpending/)
- [Redis — INFO](https://redis.io/docs/latest/commands/info/)
- [Spring Data Redis — Reference Documentation](https://docs.spring.io/spring-data/redis/reference/)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html)
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html)
- [Spring Data Redis — Pub/Sub](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html)
- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html)
- [Spring Boot — Dependency Versions](https://docs.spring.io/spring-boot/appendix/dependency-versions/)
- [Spring Boot — Data Redis](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Spring Boot — Actuator](https://docs.spring.io/spring-boot/reference/actuator/)
- [Lettuce — Reference Guide](https://redis.github.io/lettuce/)
- [Jedis — Documentation](https://redis.github.io/jedis/)
- [Testcontainers — Redis](https://java.testcontainers.org/modules/databases/redis/)
