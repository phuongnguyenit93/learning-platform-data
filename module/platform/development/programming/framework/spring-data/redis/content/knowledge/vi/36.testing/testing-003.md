# Dùng Testcontainers với Redis Server phù hợp production trong Spring Data Redis

Kiểm thử Spring Data Redis chỉ bằng mock `RedisTemplate`, một Redis giả trong bộ nhớ hoặc một Redis đã được cài sẵn trên máy lập trình viên thường bỏ sót những lỗi chỉ xuất hiện khi ứng dụng thực sự giao tiếp với Redis Server: serializer không tương thích, TTL hết hạn không như mong đợi, Lua trả sai kiểu, lệnh bị lỗi `WRONGTYPE`, cache key có prefix khác, Redis ACL từ chối truy cập, hoặc các giới hạn của Redis Cluster. **Testcontainers** giúp mỗi bộ kiểm thử khởi động một Redis Server thực bên trong Docker container, chạy các integration test bằng chính `RedisConnectionFactory` và các API Spring Data Redis mà ứng dụng sử dụng.

Tuy nhiên, **có một Redis container không đồng nghĩa môi trường đã giống production**. Muốn kết quả kiểm thử có giá trị, phải xác định sự tương thích về **phiên bản Redis, bản phân phối và module, cấu hình, serializer, mạng, bảo mật, topology, persistence, giới hạn tài nguyên và đặc điểm tải**. Nếu production dùng Redis Sentinel hoặc Cluster, một `GenericContainer` chứa Redis standalone chỉ chứng minh hành vi standalone, không thể tự chứng minh failover, redirect hay ràng buộc hash slot.

Bài học này trình bày cách sử dụng Testcontainers với Spring Boot, JUnit 5 và Spring Data Redis; giải thích cách mô phỏng các yếu tố production quan trọng; đưa ra những bài kiểm thử Redis thực có thể áp dụng; và chỉ ra khi nào cần chuyển từ một container đơn lẻ sang topology nhiều container.

## 1. Mục tiêu của integration test với Redis thật

Một phép kiểm thử Redis có thể được chia thành các mức:

| Mức kiểm thử | Cách thực hiện | Điều có thể chứng minh |
|---|---|---|
| Unit test | Mock repository/service, `RedisTemplate`, hoặc abstraction riêng | Logic gọi method, nhánh xử lý, mapping kết quả |
| Integration test một Redis thật | Testcontainers chạy Redis standalone, Spring Data Redis kết nối tới đó | Serialization, TTL, data types, Lua, cache manager, lỗi Redis thực |
| Integration test theo topology | Nhiều container Redis + Sentinel/Cluster | Failover, discovery, slot routing, reconnect, cross-slot |
| Resilience/chaos test | Toxiproxy hoặc điều khiển lỗi trong môi trường cô lập | Timeout, packet loss, connection cut, khôi phục, unknown outcome |
| Load/capacity test | Dataset và tải gần production, có memory/disk limit | Throughput, p95/p99, OOM, eviction, persistence overhead |
| Staging/end-to-end | Ứng dụng và hạ tầng gần production | Hành vi hệ thống khi nhiều thành phần phối hợp |

Điểm quan trọng: **không dùng kết quả một mức để tuyên bố đã bao phủ mức khác**. `@SpringBootTest` kết nối Redis standalone thật không tự kiểm tra được Redis Cluster, còn Testcontainers test chạy vài `SET`/`GET` không thay thế được benchmark hoặc kiểm thử khôi phục dữ liệu.

### 1.1. Những lỗi Redis giả hoặc mock khó phát hiện

- `StringRedisSerializer` và `GenericJackson2JsonRedisSerializer` ghi/đọc các byte khác nhau.
- Key tồn tại dưới kiểu String nhưng code gọi `HGET`, dẫn đến `WRONGTYPE`.
- `@Cacheable` trả `null` nhưng `RedisCacheManager` cấu hình không cache null.
- Tên cache/prefix khác nên `@CacheEvict` không xóa được entry mong muốn.
- `SET` có TTL nhưng test chỉ xác nhận giá trị ngay sau khi ghi.
- Lua thực thi tại Redis trả giá trị `Long`, `List` hoặc error không đúng giả định.
- Script dùng nhiều key ở các slot khác nhau khi triển khai Cluster.
- Redis `maxmemory-policy` khiến dữ liệu bị eviction hoặc ghi bị từ chối.
- AOF/snapshot có chi phí hoặc trạng thái khác dự tính.
- Client không xác thực được với Redis ACL/TLS.
- Container Redis cũ hỗ trợ tập lệnh khác Redis production.

Mock vẫn hữu ích cho unit test. Nhưng khi mục tiêu là kiểm tra **hợp đồng thực giữa Spring Data Redis và Redis Server**, cần một Redis Server thật.

## 2. “Phù hợp production” nghĩa là gì?

Không nhất thiết phải sao chép nguyên xi toàn bộ production vào CI. “Phù hợp” nghĩa là những đặc tính **có khả năng thay đổi kết quả của bài test** phải được mô phỏng đủ sát.

| Khía cạnh | Cần đối chiếu với production | Vì sao quan trọng |
|---|---|---|
| Redis version | Major/minor, đôi khi patch | Tập lệnh, định dạng persistence, hành vi module và bug fix |
| Redis distribution | Redis OSS/Redis Stack, managed-compatible image | Các module và command được cung cấp |
| Topology | Standalone, Sentinel, Cluster, replica | Routing, failover, giới hạn multi-key |
| Spring Data Redis/driver | Spring Boot, Spring Data Redis, Lettuce/Jedis | Serialization, connection, retry, hỗ trợ lệnh |
| Persistence | RDB/AOF, `appendfsync`, auto-rewrite | Durability, disk pressure, restart |
| Memory | `maxmemory`, eviction policy, cgroup limit | OOM, `OOM command not allowed`, eviction |
| TTL | Key expiration, cache TTL, null-cache behavior | Tính đúng đắn của cache |
| Security | Password, ACL, TLS, network policy | Authentication/authorization |
| Key schema | Prefix, key serializer, hash tag | Tương thích dữ liệu và Cluster slots |
| Modules | JSON, Search, Bloom hoặc module khác | Lệnh module sẽ không có trên Redis thường |
| Dataset | Số key, kích thước value, loại dữ liệu | Memory footprint và command latency |
| Failure model | Crash, disconnect, failover, slow network | Hành vi retry và tính nhất quán |

Ví dụ nếu production là Redis 7.x standalone dùng AOF và `noeviction`, container test dùng Redis 6.x mặc định, không AOF và `allkeys-lru` **không phản ánh đúng các tình huống liên quan persistence và memory policy**.

Ngược lại, một test thuần serializer String có thể không cần topology nhiều node. Nên tổ chức các suite theo mức độ trung thực thay vì bắt mọi test phải chạy cả cụm phức tạp.

## 3. Chọn image Redis và quản lý phiên bản

Testcontainers chạy Docker image. Với Redis Server thông thường, có thể dùng official Redis image:

```text
redis:7.2.5-alpine
```

Đây là một **ví dụ về image có tag phiên bản cụ thể**, không phải khuyến nghị production phải chạy Redis 7.2.5. Khi áp dụng, thay bằng tag/digest tương ứng với hệ thống thực.

Không nên viết test quan trọng dựa trên:

```text
redis:latest
```

vì image mới có thể thay đổi major version mà code/test không đổi, gây kết quả CI bất ngờ.

### 3.1. Ghim tag hoặc digest

Có thể chọn:

```java
DockerImageName.parse("redis:7.2.5-alpine")
```

Đối với CI cần tính tái lập chặt, cân nhắc **pin digest** của image đã phê duyệt:

```text
redis@sha256:<digest-đã-xác-minh>
```

Digest phải được lấy từ registry và đúng kiến trúc/manifest mong muốn, không tự điền một hash ví dụ rồi coi là chạy được. Ghim digest giúp tránh việc nội dung image bị thay đổi dưới cùng tag; đổi lại, quy trình cập nhật image cần được quản lý chủ động để nhận các bản vá bảo mật.

### 3.2. Không nhầm Redis Server thường với Redis Stack

Nếu production dùng Redis Stack/Redis có module JSON hoặc Search:

```redis
JSON.SET ...
FT.SEARCH ...
```

thì image `redis:...` thông thường có thể **không có những lệnh module đó**. Khi ấy cần dùng image/bản phân phối phù hợp hoặc nạp đúng module như production.

Test `SET`/`GET` trên Redis thường không thể xác nhận repository đang sử dụng RediSearch index, JSONPath hoặc RedisBloom hoạt động đúng.

### 3.3. Có nên chạy nhiều phiên bản Redis trong CI?

Nếu ứng dụng phải hỗ trợ nhiều Redis versions, có thể dùng một **test matrix**:

```text
Redis version A -> integration suite
Redis version B -> integration suite
Redis version C -> integration suite
```

Nhưng với mục tiêu kiểm thử hành vi production, ít nhất phải có một profile bám sát version thực đang triển khai. Đừng để việc “test mọi phiên bản” thay thế việc test **đúng phiên bản** mà hệ thống sử dụng.

## 4. Dependency Testcontainers với Spring Boot và JUnit 5

Một dự án Gradle Groovy DSL có thể khai báo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Ở đây, các phiên bản Testcontainers thường được quản lý qua BOM/dependency management tương ứng với Spring Boot hoặc BOM riêng của dự án. Không nên kết hợp ngẫu nhiên các module Testcontainers thuộc nhiều major version.

Nếu dùng Spring WebFlux:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
```

và bộ test còn có thể cần `reactor-test`, tùy dependency đã được kéo vào qua starter test.

Nếu muốn dùng `@ServiceConnection` của Spring Boot khi phiên bản hỗ trợ:

```groovy
testImplementation 'org.springframework.boot:spring-boot-testcontainers'
```

Không cần thêm một thư viện “embedded Redis” chỉ để chạy server thật. Testcontainers yêu cầu môi trường container có thể chạy Docker image, không dựa trên một bản mô phỏng Redis viết bằng Java.

### 4.1. Những điều kiện của môi trường chạy test

- Docker daemon hoặc container runtime tương thích với Testcontainers.
- Máy CI có quyền kéo image và tạo/dừng container.
- Đường mạng cho phép JVM test kết nối tới port mà Testcontainers map.
- Tài nguyên CPU/RAM/disk đủ cho Redis và ứng dụng test.
- Cấu hình mạng/proxy registry phù hợp môi trường doanh nghiệp.
- Chính sách dọn container sau test để không gây rò rỉ tài nguyên.

**Nếu CI không chạy được Docker, test nên báo rõ lỗi hạ tầng** thay vì âm thầm chuyển sang Redis public/production hoặc skip toàn bộ bài test quan trọng.

## 5. Ví dụ đơn giản: `GenericContainer` chạy Redis thật

Không bắt buộc cần một class `RedisContainer` chuyên biệt. `GenericContainer` dùng được cho Redis Server vì ta biết image, port và lệnh khởi động.

```java
package com.example.redis;

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
import org.testcontainers.containers.wait.strategy.Wait;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@Testcontainers
class RedisRealServerIT {

    private static final int REDIS_PORT = 6379;

    @Container
    static final GenericContainer<?> redis =
            new GenericContainer<>(
                DockerImageName.parse("redis:7.2.5-alpine")
            )
            .withExposedPorts(REDIS_PORT)
            .waitingFor(Wait.forListeningPort());

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.redis.host",
            redis::getHost
        );
        registry.add(
            "spring.data.redis.port",
            () -> redis.getMappedPort(REDIS_PORT)
        );
    }

    @Autowired
    StringRedisTemplate template;

    @Test
    void canWriteAndReadThroughSpringDataRedis() {
        String key = "it:redis:roundtrip";

        try {
            template.opsForValue().set(key, "hello");
            assertEquals("hello", template.opsForValue().get(key));
        } finally {
            template.delete(key);
        }
    }
}
```

Đây là một integration test:

1. JUnit/Testcontainers khởi động Redis container.
2. Spring Test nhận địa chỉ Redis thực qua `@DynamicPropertySource`.
3. Spring Boot tạo `RedisConnectionFactory` từ những properties đó, nếu không bị bean khác override.
4. `StringRedisTemplate` kết nối Redis thật và chạy lệnh.
5. Test xác nhận kết quả rồi xóa key.
6. Testcontainers dừng container theo vòng đời test.

### 5.1. Vì sao phải dùng `getHost()` và `getMappedPort()`?

Trong container, Redis lắng nghe port `6379`. Trên host hoặc CI runner, Testcontainers có thể ánh xạ nó thành một port động:

```text
Redis trong container :6379
          |
          v
Docker mapped port trên host :32781
          |
          v
Spring application test
```

Vì thế, không hardcode:

```java
registry.add("spring.data.redis.port", () -> 6379);
```

và không mặc định host luôn là `localhost`.

Cách đúng:

```java
registry.add("spring.data.redis.host", redis::getHost);
registry.add("spring.data.redis.port", () -> redis.getMappedPort(6379));
```

`getHost()` có thể khác trên môi trường Docker remote; Testcontainers cung cấp endpoint thích hợp cho **JVM đang chạy test**.

### 5.2. Tại sao container là field `static`?

Với JUnit 5 Testcontainers extension, `@Container static` tạo container dùng chung trong vòng đời **một test class**. Không cần khởi động Redis cho mỗi method test, giúp tiết kiệm thời gian.

Điều đó **không tự bảo đảm dữ liệu giữa các test method được cô lập**. Nếu test A ghi key `user:42` mà không xóa, test B vẫn có thể nhìn thấy nó. Cần có chiến lược namespace, cleanup hoặc container riêng theo yêu cầu.

### 5.3. Vì sao không dùng `@BeforeAll` để gọi `start()` thêm lần nữa?

Với `@Testcontainers` và `@Container`, extension quản lý lifecycle. Tự gọi `redis.start()` ở nơi khác không cần thiết và có thể làm vòng đời khó hiểu.

Một phương án khác là quản lý singleton container bằng code riêng, nhưng khi đó phải quản lý readiness, startup, shutdown và Spring context cache đúng cách. Không trộn các chiến lược lifecycle mà không có lý do.

## 6. `@DynamicPropertySource` và phạm vi cấu hình Spring

`@DynamicPropertySource` ghi đè các property được đăng ký vào Spring test environment khi context được dựng.

```java
@DynamicPropertySource
static void overrideRedis(DynamicPropertyRegistry registry) {
    registry.add("spring.data.redis.host", redis::getHost);
    registry.add("spring.data.redis.port", () -> redis.getMappedPort(6379));
}
```

Điều này đặc biệt hữu ích khi dự án có `application.yml` mặc định trỏ tới Redis ở một môi trường khác. Test phải **chủ động ép Spring sử dụng container** thay vì vô tình kết nối tới Redis của developer hoặc staging.

### 6.1. Cẩn thận khi có `RedisConnectionFactory` viết tay

Nếu cấu hình ứng dụng đã tạo bean:

```java
@Bean
RedisConnectionFactory connectionFactory() {
    return new LettuceConnectionFactory("redis-production", 6379);
}
```

thì việc đăng ký `spring.data.redis.host` có thể **không thay đổi** endpoint mà bean này dùng. Vì bean tự tạo không nhất thiết đọc các Boot properties.

Trước khi tin vào integration test, phải bảo đảm bean thực mà `RedisTemplate` sử dụng trỏ tới container hoặc được cấu hình để nhận endpoint động trong môi trường test.

Đây là một trong những cách khiến test **chạy xanh nhưng thực tế đã kết nối Redis ngoài ý muốn**. Nên có một test quan sát Redis container, dùng namespace riêng và cấu hình cấm kết nối tới production từ CI.

### 6.2. Spring Boot versions và prefix

Trong Spring Boot 3.x, nhóm properties phổ biến là:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Các phiên bản Boot cũ có thể sử dụng prefix khác. Khi chuyển version, luôn dùng nhóm property đúng với version ứng dụng đang chạy; đừng tự kết luận `@DynamicPropertySource` bị lỗi chỉ vì test dùng property name cũ.

## 7. Tùy chọn `@ServiceConnection` khi Spring Boot hỗ trợ

Spring Boot các phiên bản hỗ trợ Testcontainers service connections có thể tự tạo connection details từ container được khai báo phù hợp, tránh viết host/port properties bằng tay.

Ví dụ ý tưởng:

```java
@SpringBootTest
@Testcontainers
class RedisServiceConnectionIT {

    @Container
    @ServiceConnection(name = "redis")
    static GenericContainer<?> redis =
        new GenericContainer<>(
            DockerImageName.parse("redis:7.2.5-alpine")
        ).withExposedPorts(6379);

    // @Autowired StringRedisTemplate template;
}
```

Đoạn trên cần các import tương ứng, ví dụ `org.springframework.boot.testcontainers.service.connection.ServiceConnection`, và dependency `spring-boot-testcontainers`.

**Không nên mặc định ví dụ này phù hợp mọi Spring Boot version hoặc mọi image Redis tùy biến.** Service connection nhận dạng container theo image/type và cơ chế factory của Boot version thực tế. Với `GenericContainer` dùng image riêng, thuộc tính `name = "redis"` có thể giúp nhận dạng service, nhưng vẫn phải xác nhận connection details được tạo đúng.

Nếu image production có nhiều port, TLS/ACL đặc biệt hoặc topology Sentinel/Cluster, `@ServiceConnection` đơn giản có thể chưa biểu diễn đủ. Khi ấy `@DynamicPropertySource` hoặc cấu hình test chuyên biệt giúp kiểm soát endpoint rõ hơn.

### 7.1. Chọn cách nào?

| Cách | Ưu điểm | Phạm vi phù hợp |
|---|---|---|
| `@DynamicPropertySource` | Tường minh host/port/password, dễ thấy cấu hình | Nhiều version Spring Boot, Redis cấu hình riêng |
| `@ServiceConnection` | Ít boilerplate nếu Boot nhận diện service | Boot version hỗ trợ và container được nhận diện |
| Spring test `@Import` configuration | Dùng lại bean production có tham số | Cấu hình tự viết phức tạp |
| Testcontainers singleton tự quản lý | Có thể chia sẻ container xuyên test classes | Cần quản lý Spring context cache/lifecycle cẩn thận |

Với bài học này, dùng `@DynamicPropertySource` làm ví dụ chính để nhìn rõ **container endpoint được đưa vào Spring Data Redis như thế nào**.

## 8. Cấu hình Redis container giống production hơn

Mặc định official Redis image chạy với những setting nhất định. Nếu production có AOF, memory cap, policy không eviction hoặc keyspace notifications, cần bật đúng các yếu tố mà test đang muốn kiểm tra.

Ví dụ test-only configuration:

```java
@Container
static final GenericContainer<?> redis =
    new GenericContainer<>(
        DockerImageName.parse("redis:7.2.5-alpine")
    )
    .withExposedPorts(6379)
    .withCommand(
        "redis-server",
        "--appendonly", "yes",
        "--appendfsync", "everysec",
        "--save", "",
        "--maxmemory", "256mb",
        "--maxmemory-policy", "noeviction",
        "--notify-keyspace-events", "Ex"
    )
    .waitingFor(Wait.forListeningPort());
```

Các setting có ý nghĩa:

| Setting | Mục tiêu |
|---|---|
| `appendonly yes` | Bật AOF |
| `appendfsync everysec` | Chọn policy fsync minh họa |
| `save ""` | Tắt trigger RDB snapshot tự động trong ví dụ |
| `maxmemory 256mb` | Giới hạn logic memory cho Redis lab |
| `maxmemory-policy noeviction` | Khi hết ngưỡng, không tự loại key theo LRU |
| `notify-keyspace-events Ex` | Bật thông báo expiration theo cấu hình phù hợp |

Đây **không phải** bản sao một production configuration hoàn chỉnh. Mục tiêu là mô phỏng một tập setting có tác động trực tiếp tới bài test.

### 8.1. Không chọn giới hạn memory quá nhỏ cho mọi test

Một `maxmemory 32mb` có thể khiến Redis không nạp được fixture lớn hoặc AOF rewrite thất bại, dù production có hàng chục GiB. Ngược lại, nếu muốn thử `noeviction` và lỗi OOM logic, cần một suite riêng với ngưỡng thấp và data phù hợp.

**Một bộ test chức năng và một bộ test áp lực memory có thể cần cấu hình Redis khác nhau.** Không nên làm tất cả các integration test thường ngày flaky chỉ vì đặt memory limit cực thấp.

### 8.2. Cần tính cả cgroup memory

`--maxmemory 256mb` là ngưỡng do Redis sử dụng cho data/memory policy; nó **không phải** Docker container memory limit. Fork/COW khi RDB/AOF rewrite, allocator overhead, buffers và page cache có thể khiến memory thật cao hơn `maxmemory`.

Muốn kiểm thử tình huống OOM, cần cấu hình tài nguyên container/host và metric cgroup thích hợp, thay vì chỉ nhìn `INFO memory`.

## 9. Dùng file `redis.conf` riêng khi cấu hình lớn

Khi test cần nhiều tham số, việc nhét mọi flag vào `withCommand` trở nên khó đọc. Có thể lưu một file cấu hình test trong `src/test/resources/redis/redis-test.conf`:

```conf
bind 0.0.0.0
protected-mode yes
port 6379

appendonly yes
appendfsync everysec
save ""

maxmemory 256mb
maxmemory-policy noeviction

notify-keyspace-events Ex
```

Sau đó copy file vào container và chạy Redis với file đó:

```java
import org.testcontainers.utility.MountableFile;

@Container
static final GenericContainer<?> redis =
    new GenericContainer<>(
        DockerImageName.parse("redis:7.2.5-alpine")
    )
    .withCopyFileToContainer(
        MountableFile.forClasspathResource(
            "redis/redis-test.conf"
        ),
        "/usr/local/etc/redis/redis.conf"
    )
    .withExposedPorts(6379)
    .withCommand(
        "redis-server",
        "/usr/local/etc/redis/redis.conf"
    );
```

**Phạm vi an toàn:** nếu Redis bind `0.0.0.0` và bật `protected-mode yes`, hành vi chấp nhận kết nối phụ thuộc xác thực/network của Redis. Ví dụ trên cần test xác minh kết nối thực sự được phép từ JVM. Với cấu hình mạng và Redis version khác nhau, cần thiết kế ACL/password/TLS phù hợp. Không lấy một file lab thiếu security rồi mang thẳng lên production.

### 9.1. Tạo config theo phiên bản production

Nên giữ một **profile Redis config cho integration test** được đối chiếu với production:

```text
Redis test config
  |
  +-- tập setting ảnh hưởng business behavior
  +-- timeout/limits cho CI
  +-- endpoints & credentials giả phục vụ test
```

Không nhất thiết sao chép secrets, dữ liệu thật hoặc hostnames production. Các giá trị môi trường như password test, cert test và resource limit có thể khác, nhưng **ngữ nghĩa quan trọng** của Redis cần được mô phỏng.

### 9.2. Xác nhận config thực sự được áp dụng

Một lỗi dễ bỏ sót: container khởi động nhưng flag bị sai hoặc một file config khác đang được dùng. Có thể kiểm tra qua Redis CLI trong container:

```java
var result = redis.execInContainer(
    "redis-cli",
    "CONFIG",
    "GET",
    "appendonly"
);

assertEquals(0, result.getExitCode());
// Kiểm tra output thực tế phù hợp "yes".
```

Hoặc:

```java
var info = redis.execInContainer(
    "redis-cli",
    "INFO",
    "server"
);

assertEquals(0, info.getExitCode());
// Đọc redis_version từ output để đối chiếu image thực.
```

Khi bật password/TLS, các lệnh Redis CLI cũng cần cấu hình xác thực tương ứng; test không được đưa password production vào code hoặc log.

## 10. Test cấu hình password/ACL đúng cách

Một Redis mặc định không xác thực không thể chứng minh ứng dụng đã cấu hình credentials đúng.

Ví dụ **password chỉ dùng cho lab**:

```java
private static final String TEST_PASSWORD = "test-only-password";

@Container
static final GenericContainer<?> redis =
    new GenericContainer<>(
        DockerImageName.parse("redis:7.2.5-alpine")
    )
    .withExposedPorts(6379)
    .withCommand(
        "redis-server",
        "--requirepass", TEST_PASSWORD
    );

@DynamicPropertySource
static void redisProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.data.redis.host", redis::getHost);
    registry.add(
        "spring.data.redis.port",
        () -> redis.getMappedPort(6379)
    );
    registry.add(
        "spring.data.redis.password",
        () -> TEST_PASSWORD
    );
}
```

`requirepass` là cơ chế tương thích đơn giản, **không thay thế một bài kiểm thử Redis ACL với nhiều user, quyền lệnh và key patterns**.

Điểm cần nhớ:

- Official Redis Docker image không mặc định bật mật khẩu chỉ vì có environment variable tên `REDIS_PASSWORD`. Phải cấu hình Redis server thực sự theo image đang dùng.
- Không ghi credential production vào annotation, Git repository hoặc CI logs.
- Nếu production dùng ACL `user`, `~key-pattern`, `+command`, cần kiểm thử cả thao tác **được phép** và **bị từ chối**.
- Nếu production dùng TLS, chỉ mở Redis port thường với password không phải kiểm thử TLS parity; cần cấu hình certificate, truststore và TLS port theo hạ tầng tương ứng.
- Redis password/test certificates nên là dữ liệu giả có thể hủy, không chia sẻ với hệ thống thật.

## 11. Kiểm thử dữ liệu String, TTL và expiration thực

Một test hữu ích không chỉ xác nhận `SET` rồi `GET` mà còn phải xác nhận key tự hết hạn theo Redis Server.

Ví dụ:

```java
package com.example.redis;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;

import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Testcontainers
class RedisTtlIT {

    // Giả định class có container Redis và DynamicPropertySource
    // giống ví dụ ở phần 5, hoặc kế thừa test base tương ứng.

    @Autowired
    StringRedisTemplate redis;

    @Test
    void valueExpiresOnRealRedisServer() {
        String key = "it:ttl:" + UUID.randomUUID();

        redis.opsForValue().set(
            key,
            "temporary",
            Duration.ofSeconds(2)
        );

        assertEquals(
            "temporary",
            redis.opsForValue().get(key)
        );

        Long ttl = redis.getExpire(key, TimeUnit.SECONDS);
        assertNotNull(ttl);
        assertTrue(ttl >= 0 && ttl <= 2);

        // Kiểm tra key thực sự biến mất bằng polling có timeout,
        // thay vì giả định JVM có thể điều khiển đồng hồ Redis.
        long deadline = System.nanoTime()
                + Duration.ofSeconds(10).toNanos();

        while (Boolean.TRUE.equals(redis.hasKey(key))
                && System.nanoTime() < deadline) {
            try {
                Thread.sleep(100);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                fail("Test interrupted", ex);
            }
        }

        assertFalse(Boolean.TRUE.equals(redis.hasKey(key)));
    }
}
```

Đây là một ví dụ về **kiểm thử thực với Redis time**. Trong dự án thật có thể dùng Awaitility để viết polling gọn hơn, nhưng điều kiện quan trọng vẫn là **không kiểm tra ngay sau SET rồi tuyên bố expiration đã hoạt động**.

### 11.1. TTL trên Redis dùng thời gian thực của server

`StepVerifier.withVirtualTime(...)` hoặc clock mock trong Java **không làm đồng hồ Redis Server nhảy thời gian**. Khi test TTL của một key Redis thật, cần:

- Chờ thời gian thực hoặc dùng cơ chế test phù hợp.
- Chọn TTL ngắn vừa đủ để test nhanh nhưng không flaky vì scheduling.
- Dùng polling với timeout, không chỉ `Thread.sleep` một lần rồi assert.
- Hiểu `TTL` trả về giây có độ phân giải và giá trị đặc biệt.
- Xóa key còn lại sau test nếu cần.

Redis `TTL` thường có những giá trị:

| Kết quả | Ý nghĩa |
|---|---|
| Số không âm | Số giây còn lại |
| `-1` | Key có tồn tại nhưng không có TTL |
| `-2` | Key không tồn tại |

Nếu muốn đo sát thời điểm expiration, có thể dùng `PTTL` với độ phân giải mili giây theo command/API phù hợp. Đừng viết assertion quá chặt dựa trên đúng một mốc thời gian trên CI bị chia sẻ tài nguyên.

### 11.2. Test expiration event khác test TTL

Nếu ứng dụng có `RedisMessageListenerContainer` subscribe keyspace/keyevent notifications, test cần bật:

```conf
notify-keyspace-events Ex
```

và listener subscribe đúng channel. Tuy nhiên, Redis keyevent notification dùng Pub/Sub và không lưu message cho subscriber offline. Test event có thể trở nên flaky nếu listener chưa subscribe khi key hết hạn.

Cần tách:

- **TTL semantics:** key biến mất.
- **Notification semantics:** listener đang online nhận event phù hợp.

Không lấy event được phát làm bằng chứng mọi subscriber xử lý thành công.

## 12. Test serialization và giá trị không tương thích

Một vấn đề phổ biến khi di chuyển từ Redis giả sang server thật là key/value được serialize khác kỳ vọng.

Ví dụ:

```java
StringRedisTemplate strings;
RedisTemplate<String, ProductDto> products;
```

Hai template có thể dùng serializer khác nhau. Redis lưu byte; nếu cùng key được ghi bằng JSON serializer rồi đọc bằng JDK serialization hoặc String serializer không tương thích, kết quả có thể lỗi.

### 12.1. Test round-trip DTO

Giả sử production định nghĩa một bean `RedisTemplate<String, ProductDto>` với key serializer String và value serializer JSON. Integration test:

```java
record ProductDto(String id, String name) {}

@Autowired
RedisTemplate<String, ProductDto> productRedisTemplate;

@Test
void productSerializerRoundTrip() {
    String key = "it:product:" + UUID.randomUUID();

    ProductDto expected = new ProductDto("p-42", "Desk");

    try {
        productRedisTemplate.opsForValue().set(key, expected);

        ProductDto actual =
                productRedisTemplate.opsForValue().get(key);

        assertEquals(expected, actual);
    } finally {
        productRedisTemplate.delete(key);
    }
}
```

Test này chỉ có giá trị khi `productRedisTemplate` chính là bean serializer mà service production sử dụng. Tạo một template test hoàn toàn khác sẽ không xác nhận được hợp đồng thực.

### 12.2. Kiểm tra dữ liệu từ Redis CLI khi cần

Có thể kiểm tra raw value trên Redis bằng CLI để xem Redis đang lưu dạng String/JSON/binary gì. Với serializer có metadata kiểu, cần kiểm tra khả năng đọc chéo giữa hai phiên bản ứng dụng khi rolling deployment.

Những trường hợp đáng thử:

- DTO mới thêm field.
- DTO bỏ/đổi tên field.
- Giá trị `null` trong cache.
- `Optional.empty()` khi qua Spring Cache abstraction.
- Key Unicode, dấu cách và ký tự đặc biệt.
- Giá trị lớn; cấu trúc lồng nhau.
- Giữa String và Hash có cùng namespace, tránh `WRONGTYPE`.

**Không dùng Java object equality của mock serializer làm bằng chứng raw Redis data đã tương thích giữa các service**.

## 13. Kiểm thử `RedisCacheManager` đúng cấu hình production

Trong ứng dụng có `@Cacheable`, `@CachePut` hoặc `@CacheEvict`, cần test **cache manager thực**: tên cache, key prefix, serializer, TTL và policy với null.

Ví dụ một kiểm thử trực tiếp với Spring Cache:

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.data.redis.cache.RedisCache;

import static org.junit.jupiter.api.Assertions.*;

class RedisCacheContractIT {

    @Autowired
    CacheManager cacheManager;

    @Test
    void cacheManagerStoresAndEvictsEntry() {
        Cache cache = cacheManager.getCache("products");
        assertNotNull(cache);
        assertInstanceOf(RedisCache.class, cache);

        String key = "it:" + UUID.randomUUID();

        cache.put(key, "cached-value");
        assertEquals(
            "cached-value",
            cache.get(key, String.class)
        );

        cache.evict(key);
        assertNull(cache.get(key));
    }
}
```

Đoạn code giả định được chạy **bên trong Spring test context** đã bật Spring Cache, có `RedisCacheManager` và container Redis. Phương thức test được trình bày riêng để tập trung vào contract; nếu dùng thành một class hoàn chỉnh, thêm các annotation/context setup giống phần 5.

### 13.1. Kiểm thử method caching chứ không chỉ Cache API

Thao tác trực tiếp với `CacheManager` chưa kiểm tra proxy/interceptor của Spring Cache. Với `@Cacheable`, nên có một integration test gọi method qua Spring bean:

```text
Call 1 -> gọi repository -> ghi Redis
Call 2 -> đọc Redis -> không gọi repository
Evict  -> entry bị xóa
Call 3 -> gọi repository lại
```

Nếu method được gọi bằng `this.cachedMethod()` trong cùng object, Spring proxy có thể không intercept như trường hợp gọi từ một bean khác. Test cần mô phỏng đúng đường gọi trong ứng dụng.

### 13.2. Test `null` và serializer của Spring Cache

Nếu muốn cache negative lookup bằng `null`, cần xác nhận:

- `RedisCacheConfiguration` đang cho phép cache null.
- Serializer hỗ trợ biểu diễn internal null marker phù hợp.
- TTL của negative cache đúng với yêu cầu.
- Không có `unless = "#result == null"` vô tình ngăn ghi cache.
- Lần gọi thứ hai thực sự không truy vấn nguồn dữ liệu.

`null` từ `StringRedisTemplate.opsForValue().get(key)` thường là Redis cache miss; nó **khác** với marker null mà Spring Cache abstraction có thể ghi khi provider cho phép cache kết quả null.

## 14. Kiểm thử các nhóm Redis data types

Redis thật giúp xác nhận data structure mà code thực sự dùng:

| Nhóm Spring Data Redis | Lệnh/kiểu Redis | Kiểm thử đáng làm |
|---|---|---|
| `opsForValue()` | String, counters | `SET`, `GET`, `INCR`, TTL |
| `opsForHash()` | Hash | Field get/put, mapping serializer, `HGETALL` |
| `opsForList()` | List | `LPUSH`/`RPOP`, ordering, empty list |
| `opsForSet()` | Set | Membership và tính duy nhất |
| `opsForZSet()` | Sorted Set | Score, rank và thứ tự |
| `opsForGeo()` | Geo | Long/lat, radius, distance |
| `opsForHyperLogLog()` | HyperLogLog | Ước lượng cardinality, không test như count chính xác |
| `opsForStream()` | Stream | `XADD`, read offset, group, ACK, pending |
| Lua scripting | `EVAL`/`EVALSHA` | Tính nguyên tử và kiểu trả về |
| Pub/Sub | `PUBLISH`, `SUBSCRIBE` | Subscription lifecycle, message delivery, reconnect |

Không cần chạy một test cực dài chứa mọi kiểu dữ liệu. Nên viết các integration test theo từng service hoặc contract để khi thất bại biết chính xác thao tác nào sai.

### 14.1. Test `WRONGTYPE`

Một negative test có giá trị:

```java
String key = "it:wrongtype:" + UUID.randomUUID();

try {
    redis.opsForValue().set(key, "not-a-hash");

    assertThrows(
        RuntimeException.class,
        () -> redis.opsForHash().get(key, "field")
    );
} finally {
    redis.delete(key);
}
```

Kiểu exception cụ thể thường được Spring Data Redis dịch từ driver; trong test project thật nên assert đúng loại `DataAccessException`/lỗi Redis mà code có trách nhiệm xử lý, thay vì cố định message error theo một driver version.

Quan trọng: dùng một key của chính test, không tạo key `profile:production-user` rồi phá dữ liệu thật.

## 15. Kiểm thử Lua script trên Redis Server thật

Lua script được Redis thực thi ở server; mock Java không thể xác nhận hoàn toàn semantics của `redis.call`, giá trị trả về, lỗi Lua và tính nguyên tử.

Ví dụ dùng `DefaultRedisScript<Long>`:

```java
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RedisLuaIT {

    @Autowired
    StringRedisTemplate redis;

    @Test
    void incrbyScriptReturnsNewValue() {
        String key = "it:lua:" + UUID.randomUUID();

        DefaultRedisScript<Long> script =
                new DefaultRedisScript<>();

        script.setScriptText(
            "return redis.call('INCRBY', KEYS[1], tonumber(ARGV[1]))"
        );
        script.setResultType(Long.class);

        try {
            Long result = redis.execute(
                script,
                List.of(key),
                "2"
            );

            assertEquals(2L, result);
            assertEquals(
                "2",
                redis.opsForValue().get(key)
            );
        } finally {
            redis.delete(key);
        }
    }
}
```

Đoạn này được dùng trong context Spring test có `StringRedisTemplate` kết nối container thực.

### 15.1. Vì sao phải test với image/Redis version đúng?

Redis script behavior và bộ lệnh có thể khác theo Redis version; Lua script cũng có thể phụ thuộc serialization, key type và lệnh mở rộng.

Ngoài happy path, cần thử:

- Key không tồn tại.
- Key sai type.
- `ARGV` thiếu hoặc sai định dạng.
- Kết quả vượt phạm vi mà Java type xử lý.
- Gửi hai request đồng thời vào cùng key để kiểm tra invariant.
- Với Cluster, mọi key script sử dụng có cùng hash slot.
- Sau failover/restart, cơ chế `EVALSHA`/`NOSCRIPT` có fallback đúng không.

Test script trên một Redis standalone không thể xác nhận `CROSSSLOT`; đó là trách nhiệm của suite Cluster riêng.

## 16. Test Redis Streams và consumer group

Nếu service sử dụng `StreamOperations`, test không nên dừng ở việc `XADD` trả về một ID. Cần kiểm tra ngữ nghĩa đọc, ACK và recovery khi consumer lỗi.

Một chuỗi test cơ bản:

```text
1. Tạo stream với namespace riêng.
2. Tạo consumer group ở offset đã chọn.
3. XADD một entry có eventId rõ ràng.
4. XREADGROUP bằng consumer name riêng.
5. Xác nhận entry được giao và đang pending.
6. Thực thi handler.
7. XACK sau khi handler thành công.
8. Xác nhận entry không còn pending.
```

Một phép thử khác:

```text
1. Đọc entry qua XREADGROUP.
2. Không ACK (giả lập consumer lỗi).
3. Kiểm tra XPENDING.
4. Dùng consumer/reclaim policy phù hợp để xử lý lại.
5. XACK sau khi xử lý idempotent.
```

Những bài test này cần server Redis thật để quan sát Pending Entries List (PEL).

### 16.1. Ranh giới của một Redis container

Một container standalone có thể test XADD, XREAD, XREADGROUP, XACK và pending tại một server. Nhưng nó chưa kiểm chứng:

- Sự mất dữ liệu do primary failover sang replica chưa đồng bộ.
- Consumer reconnect sau Sentinel/Cluster failover.
- Stream key routing trên Cluster.
- `XREAD` nhiều stream khác hash slot.
- Persistence và khả năng replay sau node crash.

Khi những đặc tính ấy là yêu cầu, cần một topology test tương ứng.

## 17. Kiểm thử Pub/Sub: lifecycle và giới hạn delivery

`RedisMessageListenerContainer` quản lý subscription và chuyển message tới listener. Test với Redis thật có thể xác nhận:

1. Container đăng ký `ChannelTopic` hoặc `PatternTopic`.
2. Publisher `convertAndSend(...)` đưa message đúng channel.
3. Listener deserialize đúng payload.
4. Lỗi parse được ghi nhận qua `ErrorHandler` phù hợp.
5. Subscriber reconnect theo behavior driver/container khi connection bị cắt.

Tuy nhiên, Pub/Sub là mô hình không có durable backlog. Nếu publisher phát message **trước khi listener hoàn tất subscribe**, message có thể mất.

### 17.1. Tránh test flaky do race subscribe/publish

Một test kiểu:

```text
start listener asynchronously
immediately PUBLISH message
assert listener received it
```

có thể thất bại ngẫu nhiên vì chưa hoàn thành subscription.

Thay vào đó:

- Đảm bảo Spring context và `RedisMessageListenerContainer` đã ở trạng thái subscription sẵn sàng.
- Dùng một tín hiệu/latch thích hợp để đợi listener sẵn sàng.
- Khi cần, quan sát trạng thái đăng ký trên Redis/container theo cách không phụ thuộc timing ngẫu nhiên.
- Gửi message sau readiness, có timeout chờ callback.
- Không sleep cố định quá ngắn rồi kỳ vọng hạ tầng CI luôn nhanh như máy developer.

Không được coi `PUBLISH` trả số subscriber khác 0 là bằng chứng listener đã xử lý nghiệp vụ thành công.

## 18. ReactiveRedisTemplate và `StepVerifier`

Nếu ứng dụng dùng Spring WebFlux, nên test Redis bằng chính `ReactiveRedisTemplate`/`ReactiveStringRedisTemplate`, không thay bằng synchronous template rồi suy luận API reactive cũng đúng.

Ví dụ:

```java
import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;

import reactor.test.StepVerifier;

class ReactiveRedisIT {

    @Autowired
    ReactiveStringRedisTemplate redis;

    @Test
    void reactiveRoundTrip() {
        String key = "it:reactive:" + UUID.randomUUID();

        StepVerifier.create(
            redis.opsForValue()
                .set(key, "value", Duration.ofSeconds(30))
                .then(redis.opsForValue().get(key))
        )
            .expectNext("value")
            .verifyComplete();
    }
}
```

Đoạn code được đặt trong Spring test context có container và bean reactive.

Những lỗi muốn phát hiện:

- Publisher được tạo nhưng không subscribe.
- `.block()` trên WebFlux event-loop.
- `Mono.empty()` bị nhầm với lỗi Redis.
- Serializer reactive không tương thích với synchronous template.
- `flatMap` xử lý nhiều key làm overload.
- Timeout/retry lệnh ghi không idempotent.

`StepVerifier.withVirtualTime` không làm Redis Server hết hạn TTL nhanh hơn. TTL là cơ chế thời gian thực ở server, phải test bằng đồng hồ thật hoặc kiểm soát server tương ứng.

## 19. Cô lập dữ liệu giữa các test

Một static Redis container được chia sẻ trong test class. Nếu chạy nhiều test method:

```text
Test A ghi cache:product:p1
Test B giả định cache:product:p1 không tồn tại
```

thì kết quả của test B phụ thuộc thứ tự chạy.

Các cách cô lập:

### 19.1. Namespace riêng cho từng test

```java
String key = "it:" + UUID.randomUUID() + ":product:p1";
```

Ưu điểm:

- Không đụng key của test khác.
- Có thể chạy song song khi mỗi test chỉ dùng namespace của mình.
- Không cần xóa toàn bộ DB.

Nhược điểm:

- Nếu app code tự tạo key cố định, cần cấu hình key prefix/test profile phù hợp.
- Cần cleanup hoặc TTL để tránh tích tụ dữ liệu trong test container sống lâu.

### 19.2. Cleanup theo key

```java
try {
    // Test logic.
} finally {
    redis.delete(key);
}
```

Phù hợp với một vài key rõ ràng. Với một service sinh nhiều key/index, cần một cleanup strategy được thiết kế riêng.

### 19.3. `FLUSHDB` chỉ trong Redis cô lập

Có thể dùng `FLUSHDB` trong một Redis container chỉ thuộc **một test suite cô lập**. Không dùng `FLUSHDB` khi container/DB được chia sẻ bởi test chạy song song, vì test này có thể xóa dữ liệu của test khác.

**Tuyệt đối không chạy lệnh dọn keyspace trên Redis production hoặc staging dùng chung chỉ vì test class có annotation `@BeforeEach`.**

### 19.4. Không dùng `SELECT` như giải pháp chung cho Cluster

Standalone Redis có thể hỗ trợ nhiều logical DB theo cấu hình. Redis Cluster thường dùng database `0` và không hỗ trợ phân chia bằng `SELECT 1`, `SELECT 2` theo cách tương tự.

Vì vậy, nếu code sau này sẽ chạy Cluster, namespace/prefix riêng thường là chiến lược phù hợp hơn việc gán một DB index riêng cho mỗi test.

## 20. Static container, Spring context cache và test chạy song song

Spring Test có cơ chế cache `ApplicationContext` để giảm thời gian dựng context. Testcontainers extension có vòng đời container theo test class.

Một tình huống cần chú ý:

```text
TestClassA:
  static Redis container A
  Spring context A -> host:port của A

TestClassA kết thúc -> container A dừng

TestClassB:
  Spring có thể cache/reuse context phù hợp
  nhưng endpoint A đã không còn hợp lệ
```

Đây là một trong những nguồn test flaky khi tái sử dụng Spring context với dynamic properties và container có lifecycle không khớp.

Các hướng xử lý:

- Chia sẻ container trong một test base/context scope có vòng đời rõ.
- Khi property endpoint thay đổi giữa các test classes, dùng cơ chế làm mới context (`@DirtiesContext`) nếu cần.
- Không để một context sống lâu giữ connection factory trỏ tới container đã dừng.
- Không dùng `@Testcontainers` static một cách máy móc cùng với singleton pattern tự quản lý.
- Khi chạy test song song, bảo đảm namespace và side effect riêng.

Testcontainers có tùy chọn container reuse ở môi trường developer, nhưng sử dụng reuse trong CI cần cân nhắc **dữ liệu cũ, config drift và tính tái lập**. Mặc định nên ưu tiên test không phụ thuộc trạng thái của các run trước.

## 21. Đợi Redis readiness, không chỉ đợi Docker báo container running

Redis container có thể đang ở trạng thái `running` nhưng chưa sẵn sàng phục vụ thao tác, ví dụ đang load AOF lớn hoặc khởi động module.

Testcontainers có thể dùng wait strategy:

```java
.waitingFor(Wait.forListeningPort())
```

Điều này thường đủ cho một Redis standalone nhỏ, nhưng khi cần kiểm tra readiness chặt, có thể thêm probe:

```text
redis-cli PING -> PONG
```

hoặc chờ trạng thái cụ thể qua Redis command tương ứng.

### 21.1. Port mở không đồng nghĩa ứng dụng sẽ được phép kết nối

Nếu Redis yêu cầu ACL/TLS, test readiness có thể cần authentication. Một health check chỉ gửi `PING` không credentials có thể nhận `NOAUTH`, dù server đã chạy và ứng dụng được cấu hình đúng sẽ kết nối được.

Nếu dùng Cluster hoặc Sentinel, readiness còn bao gồm:

- Sentinel đã discover primary và replica.
- Cluster đã có đủ 16.384 hash slot được phân bổ.
- Các Redis node có thể nhìn thấy nhau.
- Endpoint node do Redis/Sentinel quảng bá **truy cập được từ JVM**.
- Client đã được cấu hình đúng credentials/TLS.

**Chọn readiness theo contract test**, không dùng chung một điều kiện "port listening" cho mọi topology.

## 22. Khi production dùng Redis Sentinel

Một Redis standalone container không mô phỏng được failover qua Sentinel. Nếu production sử dụng Sentinel, nên xây một suite riêng gồm:

```text
                   Spring Boot test
                         |
                   Sentinel seeds
                         |
        +----------------+----------------+
        |                |                |
     Sentinel 1       Sentinel 2       Sentinel 3
                         |
              Redis primary + replicas
```

Những điều cần test:

1. Spring `RedisConnectionFactory` dùng **Sentinel configuration** chứ không phải một host Redis cố định.
2. `SENTINEL get-master-addr-by-name` có thể trả địa chỉ primary.
3. Các replica đồng bộ với primary trước khi tiêm lỗi.
4. Khi primary bị dừng trong lab, Sentinel có thể promote replica mới.
5. Client Redis có thể discover/reconnect đến primary mới.
6. Lệnh `SET`/`GET` từ Spring Data Redis thành công trở lại.
7. Những write đang bay trong lúc chuyển primary có thể có outcome không chắc chắn.
8. Primary cũ quay lại theo role phù hợp, không giữ client ở endpoint cũ.

### 22.1. Bẫy địa chỉ Docker

Trong một Docker network, Sentinel có thể công bố địa chỉ Redis nội bộ như:

```text
redis-primary:6379
```

Trong khi Spring test chạy **ngoài Docker network**, JVM cần truy cập host/mapped port.

Một cấu hình có vẻ hoạt động khi hỏi Sentinel vẫn có thể thất bại lúc client nhận địa chỉ primary/replica mà nó không thể kết nối. Cần cấu hình network alias, announce/port và client routing phù hợp môi trường test.

Không thể khắc phục vấn đề chỉ bằng `.withExposedPorts(6379)` ở một container; phải xét toàn bộ mạng/topology.

## 23. Khi production dùng Redis Cluster

Redis Cluster phân phối các key qua **16.384 hash slot**. Một container Redis standalone mặc định không thể phát sinh những lỗi Redis Cluster thật như:

```text
CROSSSLOT Keys in request don't hash to the same slot
MOVED ...
ASK ...
```

Một suite phù hợp Cluster thường cần:

- Nhiều Redis primary container.
- Replica khi muốn test failover.
- Cluster enabled, node identity và cluster bus/network connectivity.
- Phân bổ slot hoàn chỉnh.
- Client Spring Data Redis dùng `RedisClusterConfiguration`/Boot cluster properties.
- Endpoint được cluster quảng bá có thể truy cập từ JVM test.

Những bài test quan trọng:

| Test | Mục tiêu |
|---|---|
| `SET`/`GET` key thuộc các slot khác nhau | Client route đúng |
| `MGET` với key cùng hash tag | Multi-key same-slot hợp lệ |
| `MGET` với key cross-slot | Nhận diện giới hạn hoặc hành vi fan-out cụ thể của driver |
| Lua script với hai key khác slot | Kiểm tra `CROSSSLOT`/key slot constraints |
| Pipeline nhiều slot | Hành vi client/driver và kết quả |
| Resharding khi có request | `MOVED`, `ASK`, topology refresh |
| Failover primary | Reconnect, redirect, unknown outcomes |
| Spring Cache clear | Phạm vi xóa cache trên nhiều node |

**Đừng dùng một “cluster mode” giả với chỉ một node để kết luận ứng dụng chạy được trên Cluster nhiều shard**. Một node có thể không bộc lộ lỗi cross-slot trong các luồng như production.

### 23.1. Key serializer ảnh hưởng hash slot

Redis tính hash slot từ byte key thực. Nếu `StringRedisSerializer` và một serializer nhị phân khác nhau, slot của key thực cũng có thể khác.

Khi dùng hash tag:

```text
cart:{customer-42}:items
cart:{customer-42}:total
```

cần đảm bảo cả hai key được serialize theo cách giữ nguyên tag dự kiến. Test nên chạy qua **template production thực** và dùng `CLUSTER KEYSLOT` trên key lưu thực tế khi điều tra.

## 24. Kiểm thử lỗi mạng với Toxiproxy

Một Redis container chạy ổn định không giúp phát hiện cách ứng dụng xử lý Redis chậm hoặc bị cắt kết nối.

Testcontainers có tích hợp **Toxiproxy** ở những phiên bản/module phù hợp, cho phép đặt proxy giữa JVM và Redis:

```text
Spring Data Redis
       |
       v
Toxiproxy endpoint
       |
       v
Redis container
```

Có thể mô phỏng:

- Connection cut.
- Độ trễ mạng tăng.
- Bandwidth bị giới hạn.
- Connection reset.
- Một số tình huống mất liên lạc tạm thời.

### 24.1. Các câu hỏi cần test

1. `GET` bị timeout thì service fallback thế nào?
2. `SET` đã được Redis thực thi nhưng phản hồi mất thì code xử lý unknown outcome ra sao?
3. `INCR` có bị retry thành hai lần không?
4. Lettuce/Jedis có reconnect sau khi kết nối được khôi phục không?
5. `RedisMessageListenerContainer` có tiếp tục nhận Pub/Sub event mới không?
6. Reactor `Mono` phát `onError` và `timeout` theo chính sách nào?
7. API có trả 404 sai khi Redis lỗi mà bị hiểu nhầm là cache miss không?

### 24.2. Vì sao không retry mù `INCR`, `LPUSH`, `XADD *`?

Ví dụ:

```text
Client gửi INCR
       |
       v
Redis thực thi tăng counter
       |
       X response bị mất
       |
Client timeout
       |
Client retry INCR
       |
       v
Counter có thể tăng lần hai
```

Test resilience nên kiểm tra **idempotency và kết quả cuối ở Redis**, không chỉ assert HTTP cuối cùng trả `200`.

Toxiproxy chỉ mô phỏng một số lỗi mạng; nó không thay thế được Sentinel/Cluster promotion hoặc kiểm thử mất điện/durability.

## 25. Kiểm thử memory eviction và `noeviction`

Production có thể dùng:

```conf
maxmemory 256mb
maxmemory-policy noeviction
```

hoặc:

```conf
maxmemory 256mb
maxmemory-policy allkeys-lru
```

Hai policy có hành vi rất khác khi Redis gần đầy:

- `noeviction`: một số lệnh làm tăng bộ nhớ có thể bị từ chối.
- `allkeys-lru`: Redis có thể evict các key để giải phóng memory theo policy.

Integration test cho cache nên thử:

- Key có TTL vẫn tuân theo TTL.
- Khi memory pressure xuất hiện, code chịu được cache miss.
- Không coi Redis eviction là database record không tồn tại.
- Với `noeviction`, Spring Data Redis phát lỗi phù hợp và service xử lý theo policy.
- Không đặt những state không thể mất cùng instance với cache được phép eviction mà không có phân tách rủi ro.

### 25.1. Không đồng nhất maxmemory với Docker memory limit

`maxmemory` là giới hạn do Redis dùng trong xử lý bộ nhớ; container vẫn có RSS, buffers, COW khi fork và filesystem cache.

Nếu muốn kiểm thử OOM-kill hoặc RDB/AOF rewrite memory peak, cần một suite áp lực riêng có resource monitoring, không chỉ set `maxmemory` nhỏ trong một test method thông thường.

## 26. Kiểm thử RDB/AOF và durability

Một `SET` rồi `GET` trong cùng tiến trình Redis **không chứng minh** dữ liệu đã được lưu bền vững trên disk.

Nếu production bật AOF:

```conf
appendonly yes
appendfsync everysec
```

các test thông thường có thể xác nhận Redis thực sự khởi động với AOF, nhưng **kiểm thử crash/restore** cần phương pháp riêng:

1. Dùng container có persistence storage được cấu hình có chủ đích.
2. Ghi các key có ID/sequence rõ ràng.
3. Ghi ACK log bên ngoài Redis.
4. Gây lỗi trong lab bằng cách đã định nghĩa.
5. Khởi động lại Redis từ cùng dữ liệu persistent.
6. Đối chiếu key/value với ACK log.
7. Tính số write đã được xác nhận nhưng mất.

### 26.1. Bẫy: `stop()` rồi `start()` GenericContainer

Nếu Testcontainers tạo một container mới với filesystem tạm, dữ liệu persistence bên trong container cũ **không tự có trong container mới**. Vì vậy:

```text
container.stop()
container.start()
assert data still exists
```

không phải mặc định là một bài kiểm thử durability đúng.

Cần thiết kế rõ:

- Reuse chính filesystem/container khi phù hợp và API cho phép.
- Hoặc dùng Docker volume/bind mount chứa persistence data.
- Hoặc xuất/nhập bộ file persistence đúng quy trình.
- Đảm bảo quyền file, cấu trúc AOF manifest trên Redis 7+ và cấu hình redis.conf nhất quán.

Không dùng startup cùng một Redis image nhưng filesystem rỗng rồi kết luận Redis đã mất dữ liệu vì lỗi AOF.

### 26.2. Mất process khác mất điện

`kill` Redis process trong container và crash cả OS/storage có các đặc tính durability khác nhau. Dữ liệu trong OS page cache có thể còn sau khi Redis process bị dừng, trong khi mất điện có thể làm mất những write chưa fsync.

Vì vậy bài test Testcontainers có thể kiểm chứng nhiều failure mode hữu ích, nhưng **không chứng minh tuyệt đối** RPO của sự cố mất điện production.

## 27. Test thời gian thực, concurrency và tính quyết định

Redis Server thật có scheduling, network, expiration và nhiều client. Test không nên giả định mọi thao tác hoàn tất theo thời gian chính xác từng mili giây.

### 27.1. Tránh `Thread.sleep(100)` để “đợi Redis”

Một lời gọi ngủ cố định rất ngắn có thể chạy được trên laptop nhưng thất bại trên CI có CPU contention.

Ưu tiên:

- Polling tới điều kiện thực với timeout.
- Awaitility khi có dependency phù hợp.
- Latch/tín hiệu readiness cho listener.
- Chờ Redis `INFO` hoặc status có ý nghĩa.
- Đặt deadline đủ dài theo hạ tầng test, không vô hạn.

### 27.2. Cần kiểm tra concurrency khi code phụ thuộc tính nguyên tử

Ví dụ một service tăng counter:

```java
redis.opsForValue().increment("it:counter");
```

có thể test nhiều thread gọi đồng thời, sau đó kiểm tra giá trị cuối đúng tổng số lần tăng thành công.

Ngược lại, một mẫu `GET` → tăng trong Java → `SET` có thể tạo lost update khi nhiều client song song. Test với Redis thật và barrier bắt đầu gần đồng thời giúp bộc lộ lỗi này.

Tuy nhiên, benchmark concurrency không nên phụ thuộc vào thứ tự thread Java không xác định để tạo một assertion cứng về thứ tự completion.

## 28. Tối ưu tốc độ test mà không đánh đổi độ tin cậy

Testcontainers cần kéo image, khởi động Redis và Spring context. Có thể giảm thời gian:

- Dùng container static dùng chung trong một test class/suite có lifecycle rõ.
- Dùng image có sẵn trong CI cache/registry mirror.
- Tránh `@DirtiesContext` nếu không cần reset context.
- Chia unit tests (nhanh) và integration tests (Redis thật) theo nhãn Gradle/JUnit.
- Dùng namespace riêng thay vì restart Redis cho từng method.
- Không bật AOF, TLS, Cluster trong các test không liên quan tới những tính năng đó nếu mục tiêu là tốc độ.
- Chạy suite topology/failover ở pipeline riêng nhưng bắt buộc trước release khi cần.

**Đừng tối ưu bằng cách thay Redis thật bằng một fake ở chính suite được tạo để phát hiện khác biệt Redis Server.** Unit test có thể dùng mock; integration test nên giữ server thật.

### 28.1. Không lạm dụng container reuse

Testcontainers hỗ trợ các cơ chế reuse trong môi trường có cấu hình phù hợp, nhưng reuse có thể giữ dữ liệu/config từ run trước và làm mất tính tái lập.

Trong CI, thông thường nên ưu tiên container được tạo và dọn theo test lifecycle, trừ khi đội ngũ có quy trình cô lập dữ liệu/lifecycle rất rõ.

## 29. Thiết kế CI pipeline cho Redis integration test

Một pipeline hữu ích:

```text
Build / Compile
       |
       v
Unit tests (mock)
       |
       v
Integration tests:
  - Redis standalone Testcontainers
  - production-compatible Redis image
  - Spring Boot context + RedisTemplate
       |
       v
Specialized tests:
  - auth/ACL/TLS
  - Redis Streams/PubSub
  - Cluster/Sentinel
  - failure injection
       |
       v
Performance / durability tests trên staging
```

Không phải tất cả các tầng đều phải chạy trên mỗi commit. Ví dụ:

| Tần suất | Bộ test |
|---|---|
| Mỗi pull request | Unit + Redis standalone integration cốt lõi |
| Khi thay cấu hình Redis/serializer | Cache, TTL, key schema, ACL, script |
| Khi thay client/Boot/Redis version | Full Redis compatibility suite |
| Trước release | Sentinel/Cluster, reconnect, failure injection nếu dùng |
| Định kỳ trên staging | Load, memory pressure, persistence, RTO/RPO |

Một lệnh thực thi test thường gặp:

```bash
./gradlew test
```

Nếu dự án tách `integrationTest` thành Gradle source set/task riêng, chạy task đó theo quy trình project. Đoạn này chỉ mô tả cách tổ chức pipeline; **không có nhu cầu chạy Gradle để soạn tài liệu này**.

### 29.1. Khi Docker daemon không sẵn sàng

Thông báo lỗi test hạ tầng cần chỉ rõ Testcontainers không truy cập được container runtime. Không chuyển sang:

```yaml
spring:
  data:
    redis:
      host: some-shared-redis
```

để “làm test xanh”, vì có thể kết nối tới hệ thống ngoài kiểm soát và gây thay đổi dữ liệu.

Không nên mặc định bật `disabledWithoutDocker = true` cho các integration test là **release gate quan trọng** nếu điều đó khiến chúng bị skip im lặng. Nếu muốn skip ở môi trường developer không có Docker, cần có policy CI riêng đảm bảo suite bắt buộc được chạy và báo cáo kết quả.

## 30. Bảng lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng điều tra |
|---|---|---|
| `Connection refused` | Dùng port 6379 host thay vì mapped port | `getHost()`/`getMappedPort()` |
| Test treo khi context khởi tạo | Container chưa ready hoặc Redis đang load AOF | Wait strategy, logs, timeout |
| Test vô tình kết nối Redis khác | Bean `RedisConnectionFactory` tự viết, property override không có tác dụng | Bean wiring, endpoint và namespace |
| `NOAUTH Authentication required` | Redis bật password nhưng client chưa cấu hình | Password/username/ACL của test |
| `WRONGPASS` | Credentials sai hoặc user bị disable | Kiểm tra ACL test-only |
| `WRONGTYPE` | Ghi String nhưng đọc Hash hoặc ngược lại | Key schema và serializer |
| Deserialize error | Test serializer không giống production | `RedisSerializationContext`, DTO schema |
| `@Cacheable` không cache | Chưa bật caching, self-invocation, `unless`, cache manager sai | Spring proxy/cache config |
| TTL test flaky | Timing assertion quá chặt | Polling với deadline |
| Redis bị OOM trong test | Limit quá thấp, nhiều fixture, fork/COW | INFO memory + cgroup |
| `CROSSSLOT` chỉ xuất hiện production | CI chỉ dùng standalone | Thêm Cluster suite |
| `MOVED`/`ASK` làm test fail | Client không Cluster-aware hoặc topology stale | Driver config/topology |
| Listener không nhận message | Publish trước khi subscribe | Readiness/latch |
| Test Streams không thấy pending | ACK tự động hoặc sai group/offset | `XREADGROUP`, `XPENDING`, ACK policy |
| Data sau restart biến mất | Container mới không dùng persistent volume | Test storage lifecycle |
| Test pass local, fail CI | Network host/mapped port, CPU contention, image availability | Logs, Docker environment, timeouts |
| Flaky khi test song song | Key collision hoặc `FLUSHDB` chung | Namespace riêng, cleanup |
| Cache Redis bị xóa sau test khác | Container/static lifecycle và context cache không khớp | Tách context/định nghĩa lifecycle |

Đừng xử lý mọi lỗi bằng cách tăng timeout. Lỗi cấu hình serializer, sai key type hoặc sai slot **không tự biến mất** khi chờ lâu hơn.

## 31. Kịch bản đầy đủ: kiểm thử service cache-aside với Redis thật

Một ứng dụng thường có luồng:

```text
Controller
    |
    v
ProductService
    |
    +-- Redis GET key
    |      |
    |      +-- hit  -> trả DTO
    |      |
    |      +-- miss -> Repository
    |                    |
    |                    +-- tìm thấy -> Redis SET có TTL
    |                    +-- không thấy -> theo policy negative cache
    |
    v
Response
```

Integration test có thể sử dụng Redis Testcontainers và một nguồn dữ liệu test/fake có thể đếm số lần gọi. Mục tiêu không phải mock Redis, mà là **giữ Redis Server thật** và chủ động kiểm soát dữ liệu nguồn.

Ví dụ kế hoạch:

**Test 1 — cache miss rồi hit**

1. Xóa Redis key của sản phẩm thử nghiệm.
2. Đặt repository test trả một DTO xác định.
3. Gọi service lần đầu.
4. Xác nhận repository được gọi một lần.
5. Gọi service lần hai.
6. Xác nhận repository không được gọi lại.
7. Đọc Redis và xác nhận entry có TTL/phân dạng phù hợp.

**Test 2 — update và eviction**

1. Nạp cache với dữ liệu cũ.
2. Thực hiện cập nhật qua service ghi.
3. Kiểm tra Redis key bị xóa hoặc cập nhật sau transaction commit theo policy.
4. Đọc lại qua service.
5. Xác nhận dữ liệu mới được trả về.

**Test 3 — negative cache**

1. Repository trả không tìm thấy.
2. Service lưu negative marker nếu cấu hình cho phép.
3. Request tiếp theo không gọi repository.
4. Sau TTL hoặc invalidation, repository được gọi lại.
5. Không nhầm lỗi Redis với kết quả không tìm thấy.

**Test 4 — Redis unavailable**

1. Dùng proxy cắt kết nối.
2. Gọi service.
3. Quan sát fallback/exception đã định nghĩa.
4. Khôi phục kết nối.
5. Xác nhận ứng dụng phục hồi và không trả dữ liệu sai.

**Test 5 — triển khai theo topology production**

Nếu production dùng Cluster, chạy lại những luồng nhiều key/script trên topology Cluster. Nếu dùng Sentinel, test chuyển primary trong khi service vẫn xử lý request.

### 31.1. Vì sao nên test cả dữ liệu Redis lẫn kết quả nghiệp vụ?

Một assertion:

```java
assertEquals(expected, service.findById(id));
```

chỉ cho biết kết quả trả về đúng. Service có thể đã bỏ qua cache và đọc database mọi lần.

Ngược lại, thấy một Redis key được tạo cũng chưa chứng minh service đọc lại cache đúng hoặc invalidation hoạt động.

Integration test tốt nên có **ít nhất một quan sát end-to-end** và những kiểm chứng trực tiếp đủ để xác nhận cơ chế cache dự kiến thực sự được sử dụng.

## 32. Hướng tiếp cận theo mức độ tương thích production

Không có một cấu hình Testcontainers duy nhất phù hợp mọi dự án. Có thể dùng ba profile rõ ràng:

### Profile A — Nhanh, bám sát Redis Server API

- Redis thật một container.
- Image version tương ứng production.
- Spring Boot context thật.
- Cùng serializers và `RedisCacheManager`.
- Test GET/SET, TTL, Hash, Lua, cache, Stream cơ bản.
- Dùng mỗi pull request.

### Profile B — Cấu hình Redis production-like

- Bật AOF/RDB theo policy cần test.
- Dùng ACL/password/TLS test-only tương ứng.
- Maxmemory và eviction policy được đối chiếu.
- Test persistence behavior, negative cache, error responses.
- Chạy khi thay config hoặc trước release.

### Profile C — Topology và resilience

- Sentinel/Cluster nhiều container.
- Test server discovery, redirect, reshard, failover.
- Fault injection với proxy/network tool.
- Đo reconnect, lỗi, idempotency và RTO/RPO quan sát.
- Chạy ở pipeline có tài nguyên/cách cô lập phù hợp.

Tách profile giúp tránh một tình huống: suite nhanh bị phức tạp và chậm vì cố mô phỏng production toàn bộ, trong khi các tính năng failover/Cluster lại chưa được kiểm tra đúng mức.

## 33. Checklist trước khi coi test là production-compatible

### Redis Server

- [ ] Image đúng Redis major/minor và distribution liên quan.
- [ ] Image tag/digest được kiểm soát, không dùng `latest` tùy tiện.
- [ ] Module cần thiết có mặt và cùng khả năng lệnh.
- [ ] Redis config thiết yếu được áp dụng và xác minh.
- [ ] `maxmemory`, eviction, AOF/RDB, notifications phản ánh yêu cầu test.

### Spring Data Redis

- [ ] `RedisConnectionFactory` trỏ tới container, không phải shared/production Redis.
- [ ] Test dùng chính template/serializer/cache manager của ứng dụng.
- [ ] Host và port lấy từ Testcontainers, không hardcode.
- [ ] Đã kiểm tra cache miss, TTL, null, serializer, wrong type.
- [ ] Đã thử Lua/Stream/PubSub nếu ứng dụng có dùng.
- [ ] Reactive operations được subscribe và kiểm tra bằng Reactor test khi cần.

### Test isolation

- [ ] Mỗi test có key namespace hoặc cleanup phù hợp.
- [ ] Không dùng `FLUSHDB` trên Redis chia sẻ.
- [ ] Không để context trỏ tới container đã dừng.
- [ ] Test song song không giẫm key hoặc consumer group của nhau.
- [ ] Không phụ thuộc dữ liệu từ lần chạy trước.
- [ ] CI thất bại rõ nếu Docker/image không khả dụng.

### Production-specific behavior

- [ ] Sentinel/Cluster được kiểm thử riêng nếu production sử dụng.
- [ ] Đã test TLS/ACL nếu bảo mật là phần bắt buộc.
- [ ] Test failover/reconnect và error policy nếu có yêu cầu HA.
- [ ] Đã thử memory/eviction và persistence theo phạm vi thích hợp.
- [ ] Có load/resilience test tách khỏi functional test khi cần.
- [ ] Các giả định về durability và retry được ghi rõ.

## 34. Những hiểu lầm thường gặp

**“`@SpringBootTest` là integration test với Redis thật.”** Chỉ đúng khi Spring context thực sự dùng Redis Server mà test điều khiển. Nếu Redis template bị mock hoặc connection factory trỏ tới hệ thống khác, kết quả không chứng minh điều đó.

**“Có Docker container Redis là tương đương production.”** Sai nếu version, module, topology, ACL, persistence hoặc memory policy khác.

**“Dùng `redis:latest` giúp test luôn mới và an toàn.”** Không bảo đảm tái lập; có thể đổi version và hành vi không chủ đích.

**“Đặt `spring.data.redis.port=6379` là luôn đúng.”** Không đúng khi Testcontainers map port động hoặc dùng Docker remote host.

**“`@DynamicPropertySource` luôn ghi đè mọi Redis connection factory.”** Không đúng nếu ứng dụng tạo bean cố định không đọc properties đó.

**“Static container nghĩa là mỗi method có DB Redis sạch.”** Sai. Dữ liệu tồn tại trong cả vòng đời container.

**“`FLUSHDB` trong `@BeforeEach` luôn an toàn.”** Chỉ khi DB/container thực sự thuộc test cô lập, không có test song song chia sẻ.

**“Mock Redis kiểm tra được Lua và TTL chính xác.”** Không thay thế Redis Server thật.

**“`StepVerifier.withVirtualTime` làm Redis TTL hết nhanh hơn.”** Không. Đồng hồ Redis Server độc lập với virtual clock của Reactor.

**“Một Redis standalone Testcontainer đủ để phát hiện `CROSSSLOT`.”** Không. Cần Redis Cluster thật.

**“`@ServiceConnection` tự mô phỏng Sentinel/Cluster.”** Không; nó giúp wiring connection details trong trường hợp được hỗ trợ, không tạo topology phức tạp.

**“`SET` rồi `GET` thành công chứng minh dữ liệu bền vững trên đĩa.”** Không. Cần kiểm thử crash/restore và persistence storage đúng cách.

**“Stop/start container là persistence test đầy đủ.”** Không nếu filesystem ephemeral không được giữ lại hoặc lỗi mô phỏng không đúng.

**“Tăng timeout sẽ sửa mọi test flaky.”** Không; phải xử lý readiness, key collision, resource pressure, network và config.

**“Test chạy nhanh là quan trọng hơn mọi thứ.”** Một test nhanh nhưng dùng Redis giả hoặc version sai có thể bỏ sót chính lỗi cần phát hiện. Nên phân tầng suite để có cả tốc độ và độ tin cậy.

## 35. Kết luận

**Testcontainers với Redis Server thật** là cách hiệu quả để kiểm thử Spring Data Redis ở mức gần runtime thực tế hơn unit test dùng mock. Một Redis `GenericContainer` kết hợp `@SpringBootTest`, JUnit 5 và `@DynamicPropertySource` đã đủ để xác nhận nhiều tính năng quan trọng: serializer, TTL, Redis data types, Lua, Spring Cache và các luồng đọc/ghi.

Tuy nhiên, giá trị của integration test phụ thuộc việc **mô phỏng đúng những yếu tố của production đang tác động tới chức năng cần kiểm tra**:

1. **Dùng Redis image có version và distribution xác định**, tương thích các command/module production.
2. **Đưa host/port động vào Spring đúng cách**, bảo đảm template thực sự kết nối Testcontainers Redis.
3. **Đối chiếu cấu hình có tác động tới behavior**, như persistence, ACL, TTL notifications, maxmemory và eviction.
4. **Test Redis logic thật**, gồm expiration, serializer, cache manager, Lua, Streams, Pub/Sub, không chỉ `PING`.
5. **Cô lập dữ liệu và quản lý lifecycle**, tránh test phụ thuộc thứ tự chạy hoặc context giữ connection cũ.
6. **Dùng topology phù hợp khi cần**: Sentinel để kiểm tra failover, Cluster để kiểm tra hash slot/routing, Toxiproxy để kiểm tra lỗi mạng.
7. **Giữ riêng performance/durability/chaos tests** với các assertion, tài nguyên và điều kiện quan sát đúng mức.

Một suite Testcontainers được thiết kế tốt không cố giả vờ rằng mọi thứ đã giống production chỉ vì có Redis trong Docker. Nó xác định rõ **đặc tính nào được kiểm chứng**, **những khác biệt nào còn lại**, và cung cấp bằng chứng đáng tin cậy rằng Spring Data Redis sẽ vận hành đúng trong môi trường mục tiêu.
