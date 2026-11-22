# Kiểm thử Sentinel, Cluster và phục hồi sau sự cố

## 1. Tại sao kiểm thử Redis chạy được chưa đủ?

Giả sử một ứng dụng Spring Boot sử dụng Spring Data Redis để lưu cache, kiểm tra phiên đăng nhập và ghi trạng thái xử lý. Khi chạy trên máy phát triển chỉ có một Redis server, các kiểm thử như sau thường thành công:

```java
redisTemplate.opsForValue().set("demo:status", "READY");
assertEquals("READY", redisTemplate.opsForValue().get("demo:status"));
```

Nhưng khi triển khai Redis có **Sentinel** hoặc **Redis Cluster**, hệ thống xuất hiện những tình huống không có trong kiểm thử trên một node:

- Primary đột ngột không phản hồi.
- Replica được nâng thành primary mới.
- Redis client vẫn giữ kết nối hoặc địa chỉ node cũ.
- Một lệnh ghi đã chạy ở server nhưng ứng dụng bị timeout trước khi nhận phản hồi.
- Replica chưa sao chép kịp lệnh ghi gần nhất.
- Redis Cluster chuyển hash slot sang node khác và trả `MOVED` hoặc `ASK`.
- Có mạng chập chờn, DNS thay đổi hoặc ứng dụng phải reconnect nhiều lần.
- Một số key cache còn, số khác biến mất sau failover.
- Worker của Redis Streams cần phục hồi pending messages.
- Nhiều request retry đồng thời làm Redis mới phục hồi lại bị quá tải.

Một kiểm thử đáng tin cậy không chỉ hỏi **“GET và SET có hoạt động không?”** mà phải hỏi:

> Khi topology thay đổi hoặc xảy ra lỗi giữa chừng, ứng dụng có trở lại phục vụ được không, dữ liệu có giữ đúng cam kết không và những tác dụng phụ có bị thực hiện lặp không?

Bài học này thuộc chương **Kiểm thử** của **Spring Data Redis**, tập trung vào các kiểm thử tích hợp, kiểm thử lỗi và kiểm thử phục hồi trong môi trường **Sentinel**, **Redis Cluster** cùng cơ chế client như **Lettuce**.

## 2. Phân biệt ba kiểu triển khai Redis trước khi kiểm thử

### 2.1. Redis standalone

```text
Spring Boot
     |
     v
Redis server
```

Một server nhận lệnh đọc/ghi. Kiểm thử standalone giúp xác nhận serializer, RedisTemplate, lệnh và logic nghiệp vụ cơ bản. Nhưng nó **không kiểm chứng failover Sentinel hay việc định tuyến hash slot trong Cluster**.

### 2.2. Redis replication + Sentinel

```text
                    Spring Boot / Lettuce
                             |
                  Hỏi Sentinel topology
                             |
          +------------------+------------------+
          |                  |                  |
       Sentinel 1         Sentinel 2         Sentinel 3
          |                  |                  |
          +------------------+------------------+
                             |
                      Redis primary P
                      /             \
                     v               v
                Replica R1      Replica R2
```

Sentinel theo dõi tình trạng Redis primary, phối hợp quyết định failover và công bố primary hiện tại cho client.

Trong kiểu triển khai này:

- **Sentinel không phải proxy** xử lý mọi `GET`/`SET`.
- Ứng dụng thường kết nối trực tiếp đến Redis data node do Sentinel/driver khám phá.
- Replica có thể có **replication lag** vì Redis replication thông thường bất đồng bộ.
- Khi primary lỗi, Sentinel cần thời gian phát hiện, bầu chọn và chuyển vai trò.
- Client cần cập nhật thông tin và khôi phục kết nối tới primary mới.

### 2.3. Redis Cluster

```text
                 Spring Boot / cluster-aware client
                               |
        +----------------------+----------------------+
        |                      |                      |
        v                      v                      v
    Primary A              Primary B              Primary C
    slots ...              slots ...              slots ...
        |                      |                      |
        v                      v                      v
    Replica A1             Replica B1             Replica C1
```

Redis Cluster phân chia **16.384 hash slot** cho các primary. Client định tuyến lệnh theo slot của key.

Trong kiểu triển khai này:

- Có **nhiều primary**, mỗi primary sở hữu một phần keyspace.
- Một key có thể được chuyển sang owner mới khi reshard.
- Redis có thể trả chuyển hướng `MOVED` hoặc `ASK`.
- Client cần làm mới cluster topology khi slot thay đổi.
- Failover ảnh hưởng tới primary/replica của một shard cụ thể.
- Một Redis Cluster không được biến thành “một Redis standalone lớn” trong suy luận về lệnh nhiều key.

**Sentinel và Cluster là hai cơ chế kiến trúc khác nhau.** Không nên kiểm thử một topology rồi khẳng định topology kia đã được bảo vệ.

## 3. Kiểm thử phục hồi phải xác định hợp đồng trước

Trước khi viết test, cần mô tả **điều gì được phép xảy ra trong sự cố**.

Ví dụ một hệ thống có các loại dữ liệu khác nhau:

| Loại dữ liệu | Yêu cầu phục hồi có thể chấp nhận |
|---|---|
| Cache đọc từ PostgreSQL | Có thể mất một phần cache; lần đọc sau nạp lại |
| Session có TTL | Phải tuân thủ chính sách đăng nhập/hết hạn; không tự nối dài quyền |
| Danh sách sản phẩm hiển thị | Có thể chấp nhận stale trong giới hạn xác định |
| Counter chỉ lưu tại Redis | Phải xác định rõ có chấp nhận mất write sau failover không |
| Redis Stream chứa công việc | Cần xử lý pending/retry và idempotency |
| Distributed lock | Không cho owner cũ ghi đè tài nguyên sau khi mất lease |
| Idempotency keys | Không được làm tác dụng phụ nghiệp vụ chạy trùng ngoài chính sách |
| Các tác vụ thanh toán | Phải dựa vào nguồn có thẩm quyền và transaction/idempotency phù hợp |

Một số cam kết thường dùng:

- **Availability:** hệ thống chấp nhận timeout/ngắt quãng bao lâu?
- **Recovery Time Objective (RTO):** thời gian khôi phục dịch vụ tới ngưỡng chấp nhận.
- **Recovery Point Objective (RPO):** mất tối đa bao nhiêu dữ liệu hoặc cập nhật trong sự cố?
- **Consistency:** chấp nhận đọc dữ liệu cũ trong bao lâu?
- **Idempotency:** retry có thể tạo tác dụng phụ trùng hay không?
- **Degradation:** khi Redis không khả dụng, API trả lỗi, fallback hay giảm chức năng?

Không có giá trị RTO/RPO mặc định đúng cho mọi ứng dụng. Các ngưỡng trong bài là **ví dụ cho kế hoạch kiểm thử**, phải điều chỉnh theo yêu cầu thực tế.

## 4. Các cấp độ kiểm thử nên được tách rõ

| Cấp độ | Mục đích | Môi trường |
|---|---|---|
| Unit test | Kiểm tra phân loại lỗi, retry, fallback, idempotency trong code | Mock/fake có kiểm soát |
| Integration test standalone | Kiểm tra serializer, template, lệnh Redis, TTL | Redis thật một node |
| Integration test Sentinel | Kiểm tra Sentinel discovery, chuyển primary, reconnect | Nhiều Redis nodes + nhiều Sentinel |
| Integration test Cluster | Kiểm tra slot routing, `MOVED`, `ASK`, failover từng shard | Nhiều primary + replica |
| Fault-injection test | Kiểm tra lỗi giữa chừng, timeout, partition, process crash | Topology cô lập có quyền điều khiển |
| Soak/load test | Kiểm tra hệ thống phục hồi dưới tải và không leak tài nguyên | Môi trường gần production |
| Disaster recovery drill | Kiểm tra backup/restore, failover diện rộng, runbook | Môi trường được vận hành cho mục đích đó |

### 4.1. Unit test không thay thế topology thực

Có thể mock một `RedisConnectionFailureException` để kiểm tra service trả 503 hoặc fallback. Nhưng mock không thể xác nhận:

- Sentinel đã promote node nào.
- Lettuce phát hiện topology mới trong bao lâu.
- Cluster client theo `MOVED`/`ASK` đúng hay không.
- Lệnh nào bị mất trong thời điểm failover.
- Reconnect có gây giữ hàng đợi lệnh quá lâu không.

Vì vậy, ít nhất một nhóm kiểm thử tích hợp cần **Redis thật với đúng loại topology đang dùng**.

### 4.2. Testcontainers một Redis đơn lẻ chỉ là smoke test

Một ví dụ baseline:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import org.springframework.data.redis.core.StringRedisTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Testcontainers
@SpringBootTest
class RedisStandaloneSmokeIT {

    @Container
    static final GenericContainer<?> redis =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine")
            ).withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> redis.getMappedPort(6379)
        );
    }

    @Autowired
    StringRedisTemplate template;

    @Test
    void canWriteAndRead() {
        String key = "it:standalone:probe";
        try {
            template.opsForValue().set(key, "alive");
            assertEquals(
                    "alive",
                    template.opsForValue().get(key)
            );
        } finally {
            template.delete(key);
        }
    }
}
```

Kiểm thử trên chứng minh kết nối Redis standalone, dependency và serializer hoạt động. Nó **không kiểm thử Sentinel hoặc Cluster** vì container duy nhất không có Sentinel quorum, replica hay hash-slot routing.

Khi triển khai test thực tế, sử dụng phiên bản Spring Boot/Testcontainers tương thích và tách test profiles để tránh ghi nhầm Redis môi trường khác.

## 5. Xây dựng hạ tầng Sentinel để test

Một topology Sentinel có ý nghĩa thường có:

```text
Redis P1       Redis R1        Redis R2
  primary       replica         replica
     \             |               /
      +------------+--------------+
                   |
       +-----------+-----------+
       |           |           |
    Sentinel 1  Sentinel 2  Sentinel 3
                   |
                   v
             Spring Boot test
```

### 5.1. Vì sao nên dùng ba Sentinel?

Redis Sentinel có cơ chế xác định primary down và ra quyết định failover. Khi cấu hình quorum, cần hiểu:

- **Quorum** dùng để xác nhận một primary không còn khả dụng theo đánh giá các Sentinel.
- Một lần failover còn cần sự **ủy quyền theo cơ chế bầu chọn/đa số Sentinel** theo thuật toán Sentinel.

Nếu chỉ chạy một Sentinel trong một bài test, có thể kiểm tra một số hành vi discovery cơ bản nhưng không phản ánh những tình huống quorum và phân vùng mạng của một triển khai Sentinel thực tế.

### 5.2. Cấu hình mẫu của Redis data nodes

Primary có thể chạy Redis trên cổng 6379 trong mạng test riêng.

Replica R1:

```conf
port 6379
replicaof redis-primary 6379
appendonly yes
```

Replica R2:

```conf
port 6379
replicaof redis-primary 6379
appendonly yes
```

Đây là đoạn cấu hình minh họa; các file cấu hình hoàn chỉnh còn cần cấu hình bind/protected mode, ACL, persistence, đường dẫn và networking theo hạ tầng.

### 5.3. Cấu hình mẫu Sentinel

Tệp `sentinel.conf` trên mỗi Sentinel có thể chứa:

```conf
port 26379
sentinel monitor mymaster redis-primary 6379 2
sentinel down-after-milliseconds mymaster 5000
sentinel failover-timeout mymaster 30000
sentinel parallel-syncs mymaster 1
```

Ý nghĩa:

- `mymaster`: tên nhóm primary.
- `redis-primary`: địa chỉ primary ban đầu trong mạng test.
- `2`: quorum Sentinel cần để xác nhận primary down.
- `down-after-milliseconds`: thời gian quan sát trước khi đánh dấu nghi ngờ down theo cơ chế Sentinel.
- `failover-timeout`: tham số điều phối quá trình failover, không phải cam kết ứng dụng khôi phục chính xác tại mốc đó.
- `parallel-syncs`: giới hạn số replica có thể đồng bộ song song trong giai đoạn liên quan.

**Quan trọng:** Sentinel cần quyền cập nhật trạng thái vào file cấu hình của nó. Nếu mount file `sentinel.conf` ở chế độ chỉ đọc, Sentinel có thể không ghi lại topology sau failover như mong đợi. Vì vậy, môi trường test cần cấp vùng lưu cấu hình có quyền ghi phù hợp.

Với topology trên máy Docker, tên container/hostname do Sentinel công bố phải được **ứng dụng test và driver thực sự truy cập được**.

### 5.4. Test environment nên được tạo độc lập

Có thể dùng Docker Compose hoặc Testcontainers với một Docker network riêng, các node Redis và Sentinel mang alias ổn định. Tránh chia sẻ Redis đang phục vụ development chung.

**Đừng nhầm cổng mapping Docker với địa chỉ Sentinel công bố.** Sentinel có thể trả về:

```text
redis-replica-1:6379
```

Nếu bài test Java chạy ngoài Docker và không resolve được `redis-replica-1`, kết nối có thể thất bại dù ứng dụng kết nối thành công tới cổng Sentinel được publish ra máy host.

Hai cách xử lý:

1. Chạy cả ứng dụng test và Redis/Sentinel trong **cùng mạng container**, để các hostname/port công bố có thể truy cập.
2. Cấu hình announce/NAT/DNS một cách chủ đích để các địa chỉ Sentinel trả về cũng truy cập được từ JVM chạy test.

Không chỉ mở cổng 26379 của Sentinel rồi cho rằng primary/replica cũng truy cập được.

## 6. Cấu hình Spring Boot kết nối Sentinel khi kiểm thử

Với Spring Boot 3.x, cấu hình ví dụ:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
        nodes:
          - sentinel-1:26379
          - sentinel-2:26379
          - sentinel-3:26379
      connect-timeout: 2s
      timeout: 2s
```

Đây là cấu hình cho môi trường thử nghiệm mà hostnames trên có thể truy cập từ JVM test.

Lưu ý:

- `master` là **tên nhóm primary do Sentinel giám sát**, không phải IP primary cố định.
- `nodes` là địa chỉ **Sentinel**, không phải địa chỉ các Redis replicas.
- Spring Data Redis cần kết nối dữ liệu tới những Redis nodes mà client phát hiện từ Sentinel.
- Nếu dùng Spring Boot cũ, prefix có thể là `spring.redis` thay vì `spring.data.redis`.
- Nếu ứng dụng tự tạo `RedisConnectionFactory`, kiểm tra cấu hình thực sự có hiệu lực thay vì chỉ sửa YAML.

Trong nhiều dự án, Lettuce là driver chính. Nó hỗ trợ Redis topology và có các thiết lập timeout/reconnect tùy phiên bản.

### 6.1. Kiểm tra primary hiện tại qua Sentinel

Trên một Sentinel:

```bash
redis-cli -h sentinel-1 -p 26379 \
  SENTINEL get-master-addr-by-name mymaster
```

Quan sát các replica:

```bash
redis-cli -h sentinel-1 -p 26379 \
  SENTINEL replicas mymaster
```

Lấy vai trò của một Redis data node:

```bash
redis-cli -h redis-primary -p 6379 ROLE
```

Các lệnh này giúp quan sát topology trước khi gây lỗi. Không nên chỉ lấy kết quả cache read làm bằng chứng failover đã thực sự xảy ra.

## 7. Kiểm thử Sentinel: quy trình failover có kiểm soát

### 7.1. Test case cốt lõi

**Giả định:** có 3 Sentinel, 1 primary, 2 replica; ứng dụng test sử dụng Sentinel-aware connection factory.

**Bước 1 — Xác nhận trạng thái ban đầu**

- Các Sentinel đều nhận biết `mymaster`.
- Có một primary, các replica kết nối và replication hoạt động.
- Spring Boot thực hiện một lệnh ghi thử nghiệm thành công.

Ví dụ:

```redis
SET it:sentinel:status before-failover EX 120
GET it:sentinel:status
```

**Bước 2 — Kích hoạt chuyển primary**

Có thể yêu cầu một Sentinel khởi chạy failover phục vụ test:

```bash
redis-cli -h sentinel-1 -p 26379 SENTINEL FAILOVER mymaster
```

`OK` từ lệnh này **không đồng nghĩa toàn bộ failover đã hoàn tất và ứng dụng đã reconnect**. Test cần quan sát topology cho đến khi có primary mới và client kết nối được.

Một kịch bản khác là dừng process/container chứa primary trong môi trường cô lập để kiểm tra **phát hiện lỗi thật**, thay vì chỉ dùng lệnh failover thủ công.

**Bước 3 — Quan sát thời gian gián đoạn**

Trong lúc primary chuyển đổi, ghi lại:

- Thời điểm bắt đầu inject fault.
- Thời điểm request đầu tiên thất bại.
- Số timeout hoặc lỗi kết nối.
- Thời điểm Sentinel xác nhận primary mới.
- Thời điểm ứng dụng ghi thành công trở lại.
- Thời gian toàn API trở lại đạt mức SLO.

**Bước 4 — Xác minh ghi mới trên primary mới**

Sau khi topology ổn định:

```redis
SET it:sentinel:status after-failover EX 120
GET it:sentinel:status
```

Dùng **chính Spring Redis client đang được test** để ghi và đọc, không chỉ chạy `redis-cli` trực tiếp. Nếu CLI thành công nhưng Spring Boot vẫn bám node cũ, test chưa đạt.

**Bước 5 — Kiểm tra dữ liệu trước sự cố**

Xem các key trước failover còn hay mất, nhưng đánh giá theo hợp đồng RPO:

- Cache có thể tái tạo: một số key mất có thể chấp nhận.
- Dữ liệu bắt buộc không mất: cần cơ chế durability/nguồn có thẩm quyền phù hợp.
- Một write ngay sát failover có thể không được replica mới nhận do replication bất đồng bộ.

Không tự kết luận driver có lỗi chỉ vì một write đã được primary cũ trả `OK` nhưng không hiện diện sau failover. Phải phân biệt giới hạn replication và yêu cầu nghiệp vụ.

### 7.2. Điều gì cần kiểm chứng về lỗi?

| Sự kiện | Dấu hiệu mong đợi |
|---|---|
| Primary không phản hồi | Có lỗi/timeout được phân loại đúng |
| Sentinel phát hiện primary down | Trạng thái nhóm Sentinel thay đổi |
| Replica được promote | `ROLE` hoặc `INFO replication` xác nhận primary mới |
| Lettuce reconnect | Các thao tác từ ứng dụng hoạt động trở lại |
| Ghi trong lúc chuyển đổi | Có thể thất bại; không được báo thành công giả |
| Ghi sau phục hồi | Hoạt động theo primary mới |
| Lệnh ghi timeout | Không retry mù quáng thao tác không idempotent |
| Replica chậm | Đường đọc replica có thể stale |
| Kết nối cũ | Được thay thế/phục hồi, không leak vô hạn |

## 8. Không kiểm tra failover bằng Thread.sleep cố định

Một anti-pattern:

```java
triggerFailover();
Thread.sleep(10000);
assertEquals("OK", redis.opsForValue().get(key));
```

Cách này có ba vấn đề:

1. Failover có thể hoàn tất sau 2 giây, khiến test chờ thừa.
2. Failover có thể mất hơn 10 giây, khiến test flaky.
3. Ngủ xong không chứng minh topology đã đúng hoặc client đã reconnect.

Tốt hơn là **poll điều kiện có deadline rõ ràng**.

Ví dụ dùng Awaitility:

```java
import java.time.Duration;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;

await()
        .atMost(Duration.ofSeconds(60))
        .pollInterval(Duration.ofMillis(250))
        .ignoreExceptions()
        .untilAsserted(() -> {
            String key = "it:recovery:probe";
            redis.opsForValue().set(key, "after-recovery");
            assertEquals(
                    "after-recovery",
                    redis.opsForValue().get(key)
            );
        });
```

`ignoreExceptions()` trong phép chờ giới hạn **không có nghĩa production nên nuốt lỗi**. Trong test phục hồi, nó cho phép lặp lại probe trong thời gian Redis đang chuyển đổi. Cần lưu số lỗi và loại lỗi trong phép đo riêng để không che tình trạng phục hồi chậm.

Không nên lấy thời điểm `GET` đầu tiên thành công như bằng chứng đã phục hồi **mọi** chức năng. Đường ghi, đọc từ replica, consumer Stream và các lệnh nhiều key có thể cần được kiểm tra riêng.

## 9. Java integration test với Spring Data Redis

Một lớp test có thể sử dụng profile Sentinel đã chuẩn bị bởi test infrastructure:

```java
package com.example.redis.integration;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.data.redis.core.StringRedisTemplate;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@ActiveProfiles("sentinel-it")
@Tag("sentinel-it")
class SentinelRecoveryIT {

    @Autowired
    StringRedisTemplate redis;

    @Test
    void redisWorksAgainstCurrentPrimary() {
        String key = "it:sentinel:" + UUID.randomUUID();

        try {
            redis.opsForValue().set(
                    key,
                    "ready",
                    Duration.ofMinutes(2)
            );

            assertEquals(
                    "ready",
                    redis.opsForValue().get(key)
            );
        } finally {
            redis.delete(key);
        }
    }

    @Test
    void eventuallyAcceptsWritesAfterExternalFailover() {
        String key = "it:sentinel:recovery:" + UUID.randomUUID();

        // Hạ tầng test điều khiển fault injection và đồng bộ
        // thời điểm bắt đầu kiểm tra. Đây là recovery probe;
        // bản thân method này KHÔNG kích hoạt failover.
        try {
            await()
                    .atMost(Duration.ofSeconds(60))
                    .pollInterval(Duration.ofMillis(250))
                    .ignoreExceptions()
                    .untilAsserted(() -> {
                        redis.opsForValue().set(
                                key,
                                "healthy",
                                Duration.ofSeconds(90)
                        );

                        assertEquals(
                                "healthy",
                                redis.opsForValue().get(key)
                        );
                    });
        } finally {
            try {
                redis.delete(key);
            } catch (RuntimeException ignored) {
                // Cleanup của key demo; môi trường test cô lập
                // sẽ được hủy nếu Redis vẫn chưa khả dụng.
            }
        }
    }
}
```

Điểm cần hiểu:

- Test đầu tiên xác minh RedisTemplate với topology Sentinel đang có.
- Test thứ hai chỉ là **recovery probe**; nếu không có một orchestrator thật sự kích hoạt failover vào đúng lúc, test này **không chứng minh** failover.
- Để có test failover tự động hoàn chỉnh, orchestration phải kiểm tra *primary ban đầu*, inject fault, xác nhận *primary mới*, rồi chạy probe đến khi ứng dụng phục hồi.
- Key có namespace và UUID riêng để tránh xung đột giữa những test chạy song song.
- Test không dùng `FLUSHALL` trên Redis chia sẻ.
- Cleanup lỗi do hạ tầng đang down không nên làm mất kết quả đo nguyên nhân chính; cách hủy container/namespace cần được thiết kế riêng.

### 9.1. Tách phần điều khiển sự cố khỏi logic ứng dụng

Nên có một thành phần test harness độc lập:

```java
public interface SentinelFaultController {
    String currentPrimaryAddress();
    void requestFailover();
    boolean isDifferentPrimary(String previousAddress);
}
```

Một test orchestrator gọi:

```text
oldPrimary = currentPrimaryAddress()
verify app writes/reads
requestFailover()
await until currentPrimaryAddress() != oldPrimary
await until app writes/reads successfully
record duration and failure count
```

Interface này **chỉ mô tả hợp đồng**; phải có implementation thao tác được với Docker/test environment và cơ chế đồng bộ rõ ràng. Không giả vờ test đầy đủ khi mới chỉ định nghĩa interface.

## 10. Kiểm thử đọc replica và stale data

Nếu ứng dụng cấu hình Lettuce:

```java
ReadFrom.REPLICA_PREFERRED
```

một lần `SET` vào primary rồi `GET` ngay có thể thấy dữ liệu cũ ở replica.

```text
t0: SET profile:42 = v2 trên primary
t1: Primary trả OK
t2: GET từ replica -> có thể vẫn v1
t3: Replica nhận v2
```

Một integration test hợp lý:

- Dùng một template có chính sách `UPSTREAM` để đọc phiên bản chính.
- Dùng template `REPLICA_PREFERRED` cho đường đọc chấp nhận stale.
- Tạo nhiều version tăng dần.
- Ghi thời điểm từng replica thấy bản mới.
- Đo phân bố replication lag trong workload kiểm thử.
- Xác nhận đường đọc nghiệp vụ cần *read-your-writes* **không phụ thuộc replica stale**.

### 10.1. Không ép test phải quan sát được stale read

Trong môi trường local ít tải, replication có thể rất nhanh. Một bài test viết:

```java
assertNotEquals("v2", replicaTemplate.opsForValue().get(key));
```

có thể thất bại ngẫu nhiên vì replica đã đồng bộ ngay.

Thay vì yêu cầu replica **phải stale**, cần kiểm tra:

- Hệ thống chấp nhận eventual consistency ở đường đọc cho phép.
- Đường đọc primary trả kết quả sau ghi theo kỳ vọng.
- Nếu cần mô phỏng lag, fault injection phải tạo độ trễ có kiểm soát.
- Các quyết định nghiệp vụ quan trọng không được đưa ra dựa trên replica có thể stale.

### 10.2. Fallback không phải kiểm tra freshness

`REPLICA_PREFERRED` thường fallback sang primary khi không có replica phù hợp, **không phải** vì replica vẫn online nhưng chưa nhận write mới. Test phải phân biệt mất node và lag dữ liệu.

## 11. Xây dựng Redis Cluster test đúng mạng

Một Redis Cluster thường được kiểm thử với tối thiểu vài primary và replica để có thể quan sát failover.

Ví dụ:

```text
redis-7000   redis-7001   redis-7002   (primaries)
    |            |            |
redis-7003   redis-7004   redis-7005   (replicas)
```

Một lệnh tạo Cluster trong môi trường test có các node đã khởi động với cluster mode:

```bash
redis-cli --cluster create \
  redis-7000:7000 redis-7001:7001 redis-7002:7002 \
  redis-7003:7003 redis-7004:7004 redis-7005:7005 \
  --cluster-replicas 1 --cluster-yes
```

**Lưu ý:** lệnh trên cần các Redis nodes được khởi động bằng cấu hình `cluster-enabled yes` và có thông số node ID, config file, bus port và network hợp lệ. Đây là bước tạo topology, không phải hướng dẫn đầy đủ khởi tạo mọi container từ đầu.

### 11.1. Cluster announce addresses là lỗi test rất phổ biến

Một node Redis Cluster có thể công bố:

```text
172.19.0.4:7000
```

JVM test chạy ngoài Docker chưa chắc truy cập được địa chỉ này. Khi gửi `GET` tới một key có slot trên node khác, driver nhận `MOVED` tới địa chỉ công bố và kết nối thất bại.

Triệu chứng:

- Test trên một key ngẫu nhiên thành công.
- Test trên key khác trả lỗi connection.
- Redis node vẫn báo `cluster_state:ok`.
- Testcontainers/Docker mapping port có vẻ đúng.
- Client không theo được redirect vì địa chỉ node không truy cập được từ nơi JVM chạy.

Giải pháp:

1. Chạy ứng dụng test trong cùng Docker network với Cluster, hoặc
2. Cấu hình `cluster-announce-ip`, `cluster-announce-port` và bus address phù hợp với client network, hoặc
3. Dùng cơ chế NAT/endpoint translation của driver/test infrastructure đã được cấu hình và xác minh.

**Mở cổng Redis seed node chưa đủ.** Client phải truy cập được các địa chỉ Cluster công bố của mọi node cần định tuyến.

### 11.2. Kiểm tra topology

Dùng Redis CLI:

```bash
redis-cli -h redis-7000 -p 7000 CLUSTER INFO
redis-cli -h redis-7000 -p 7000 CLUSTER NODES
redis-cli -h redis-7000 -p 7000 CLUSTER SHARDS
```

Kiểm tra slot của key:

```bash
redis-cli -h redis-7000 -p 7000 \
  CLUSTER KEYSLOT it:cluster:alpha
```

`CLUSTER INFO` cần phản ánh topology đã sẵn sàng cho thao tác test, còn `CLUSTER SHARDS` hoặc `CLUSTER NODES` cung cấp thông tin vai trò primary/replica và slot owners.

## 12. Cấu hình Spring Data Redis cho Cluster

Với Spring Boot 3.x:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-7000:7000
          - redis-7001:7001
          - redis-7002:7002
      connect-timeout: 2s
      timeout: 2s
```

Danh sách `nodes` là các **seed addresses**. Một cluster-aware driver khám phá các node còn lại qua topology.

Không cần cấu hình mọi node làm seed trong mọi triển khai, nhưng các seed phải truy cập được, và kết quả discovery phải đưa tới các địa chỉ hoạt động được từ JVM.

### 12.1. Lettuce topology refresh

Khi slot owners thay đổi, client phải cập nhật topology. Lettuce có các thiết lập refresh như periodic refresh và adaptive refresh.

Ví dụ cấu hình theo API Lettuce:

```java
package com.example.redis.cluster;

import java.time.Duration;

import io.lettuce.core.cluster.ClusterClientOptions;
import io.lettuce.core.cluster.ClusterTopologyRefreshOptions;

import org.springframework.boot.autoconfigure.data.redis
        .LettuceClientConfigurationBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LettuceClusterRefreshConfig {

    @Bean
    public LettuceClientConfigurationBuilderCustomizer
    clusterTopologyCustomizer() {

        return builder -> {
            ClusterTopologyRefreshOptions refresh =
                    ClusterTopologyRefreshOptions.builder()
                            .enableAllAdaptiveRefreshTriggers()
                            .enablePeriodicRefresh(
                                    Duration.ofSeconds(30)
                            )
                            .build();

            ClusterClientOptions clientOptions =
                    ClusterClientOptions.builder()
                            .topologyRefreshOptions(refresh)
                            .build();

            builder.clientOptions(clientOptions);
        };
    }
}
```

Trong file Java thật, import đầy đủ phải viết liền:

```java
import org.springframework.boot.autoconfigure.data.redis.LettuceClientConfigurationBuilderCustomizer;
```

Không xuống dòng ở giữa tên package/class của một `import`.

Các API và hành vi mặc định tùy phiên bản Lettuce/Spring Boot. Cấu hình ví dụ thể hiện ý tưởng làm mới topology; không phải khuyến nghị mặc định 30 giây cho mọi hệ thống.

**Không lạm dụng refresh quá thường xuyên** trong một Cluster lớn, vì bản thân việc khám phá topology có chi phí.

## 13. Kiểm thử định tuyến slot và lệnh nhiều key

### 13.1. Ghi/đọc trên nhiều hash slot

Một test Cluster không nên chỉ dùng một key cố định. Cần chọn nhiều key thuộc các slot khác nhau:

```redis
CLUSTER KEYSLOT it:cluster:A
CLUSTER KEYSLOT it:cluster:B
CLUSTER KEYSLOT it:cluster:C
```

Sau đó từ **Spring Data Redis cluster-aware client**, ghi và đọc các key ấy:

```java
String keyA = "it:cluster:A";
String keyB = "it:cluster:B";

redis.opsForValue().set(keyA, "A");
redis.opsForValue().set(keyB, "B");

assertEquals("A", redis.opsForValue().get(keyA));
assertEquals("B", redis.opsForValue().get(keyB));
```

Kiểm tra slot thực tế để bảo đảm hai key không tình cờ cùng slot. Khi cần test toàn bộ primary, tạo bộ key theo slot và ghi nhận owner của từng key.

### 13.2. Lệnh nhiều key phải xét cùng slot

Redis Cluster yêu cầu nhiều thao tác atomic/multi-key phải nằm trong cùng hash slot.

Ví dụ:

```text
order:{42}:header
order:{42}:items
```

Hai key sử dụng hash tag `{42}`, nên có cùng slot.

Kiểm tra:

```redis
CLUSTER KEYSLOT order:{42}:header
CLUSTER KEYSLOT order:{42}:items
```

Khi cần `MULTI/EXEC`, Lua script hoặc một lệnh nhiều key, test phải xác nhận:

- Hai key nằm cùng slot nếu lệnh yêu cầu.
- Driver định tuyến đúng node owner.
- Không xuất hiện `CROSSSLOT` bất ngờ.
- Thay đổi namespace không làm mất tính cùng slot.
- Resharding được xử lý mà không làm giả định về owner cố định.

**Không dùng hash tag chung cho mọi key** vì như vậy có thể dồn toàn bộ tải lên một slot.

### 13.3. Không coi CROSSSLOT là lỗi cần retry mãi

Nếu script nhận hai key khác slot, `CROSSSLOT` là lỗi **thiết kế key**, không phải sự cố mạng tạm thời.

Retry 10 lần sẽ không giải quyết vấn đề. Test phải giúp phát hiện lỗi sớm và đánh giá code nên trả lỗi có nguyên nhân rõ ràng.

## 14. Kiểm thử MOVED và ASK khi resharding

Redis Cluster dùng cơ chế chuyển hướng:

- **`MOVED`**: node báo slot đang thuộc node khác; client cần cập nhật định tuyến.
- **`ASK`**: chuyển hướng tạm thời trong giai đoạn migration slot; client phải thực hiện quy trình ASKING thích hợp khi gửi lệnh tới node đích.

Một cluster-aware client như Lettuce thường xử lý các cơ chế này ở tầng driver khi cấu hình phù hợp. Application code không nên tự parse chuỗi lỗi `MOVED` rồi viết logic HTTP không cần thiết.

### 14.1. Test case resharding

1. Xác định một key test thuộc slot S trên Primary A.
2. Ghi và đọc key qua Spring client.
3. Bắt đầu chuyển slot S sang Primary B trong topology cô lập.
4. Trong quá trình chuyển slot, tiếp tục gửi các lệnh đọc/ghi có kiểm soát.
5. Ghi lại số lần lệnh gặp lỗi, timeout, latency.
6. Khi migration hoàn tất, xác nhận slot S có owner mới.
7. Xác nhận Spring client đọc/ghi được dữ liệu cần thiết trên owner mới.

```text
Trước reshard:
  key K -> slot S -> Primary A

Đang reshard:
  Client có thể gặp MOVED / ASK
  Topology cache có thể chưa cập nhật

Sau reshard:
  key K -> slot S -> Primary B
  Client phải truy cập B được
```

### 14.2. Đừng chỉ test sau khi mọi thứ đã ổn định

Nếu test chỉ chạy `GET` sau khi resharding xong, nó có thể xác minh routing cuối cùng nhưng chưa thử những request xảy ra **trong thời điểm slot đang di chuyển**.

Một bài test fault-injection có giá trị phải thu kết quả xuyên suốt quá trình:

```text
requests sent
requests succeeded
requests timed out
redirect-related failures
max/p95/p99 latency
time to stable recovery
```

Không mặc định mọi request trong resharding phải thành công. Tiêu chí đạt phụ thuộc timeout/retry/availability mà hệ thống đã công bố.

### 14.3. Không thay đổi slot của production để chạy integration test

Resharding và `CLUSTER SETSLOT` là thao tác quản trị tác động lên dữ liệu thực. Chỉ thực hiện trong Cluster test cô lập có quyền điều khiển, hoặc trong quy trình vận hành được phê duyệt.

## 15. Kiểm thử failover một shard trong Redis Cluster

### 15.1. Quy trình

Giả sử Primary A có replica A1.

**Chuẩn bị:**

- Cluster đang `cluster_state:ok`.
- Primary A giữ một tập slot có key test.
- Replica A1 đang theo A.
- App có thể đọc/ghi những key thuộc A.

**Kích hoạt failover có kiểm soát trong môi trường test:**

Một lựa chọn là yêu cầu replica thực hiện chuyển vai trò:

```bash
redis-cli -h redis-replica-a1 -p 7003 \
  CLUSTER FAILOVER
```

Lệnh chỉ có ý nghĩa khi gọi trên replica thuộc Cluster trong trạng thái phù hợp và được phép failover. Một số tùy chọn failover như `FORCE`/`TAKEOVER` có rủi ro khác; **không dùng tùy tiện** chỉ để làm test nhanh hơn.

Hoặc có thể dừng process/container primary A để kiểm tra failover tự động, trong điều kiện Cluster còn đủ điều kiện quorum và replicas phù hợp.

**Quan sát:**

```redis
CLUSTER INFO
CLUSTER NODES
CLUSTER SHARDS
```

Sau đó xác nhận:

- Replica được promote thành primary của các slot liên quan.
- App với Redis Cluster client theo được topology mới.
- Các key thuộc shard bị ảnh hưởng phục hồi theo hợp đồng.
- Các shard khác vẫn tiếp tục phục vụ theo kỳ vọng.
- Retry và pending commands không tăng vô hạn.

### 15.2. Kiểm thử cả shard không bị ảnh hưởng

Một lỗi trong client topology hoặc cơ chế retry có thể khiến **toàn bộ ứng dụng** ngừng phục vụ dù chỉ một shard failover.

Cần dùng hai nhóm key:

```text
affectedKeys   -> slots trên Primary A
unaffectedKeys -> slots trên Primary B/C
```

Trong lúc A failover:

- Kiểm tra các request tới nhóm `unaffectedKeys` có tiếp tục hoạt động.
- Kiểm tra lỗi của nhóm `affectedKeys` có được giới hạn và phục hồi.
- Xác nhận không có retry storm dồn vào mọi shard.

Đây là lợi ích quan trọng của kiểm thử Cluster thay vì chỉ test “Redis có online không?”.

## 16. Network partition, pause và lỗi một chiều

Không phải mọi sự cố đều là process crash.

| Fault | Hành vi cần quan sát |
|---|---|
| Kill Redis primary | Redis client thấy mất kết nối; failover/reconnect |
| Pause Redis process | Socket có thể vẫn tồn tại nhưng command timeout |
| Chặn mạng app → Redis | Client không gửi/nhận được lệnh |
| Chặn mạng Sentinel ↔ primary | Sentinel có thể coi primary down; tùy quorum |
| Chặn replication primary → replica | Replica lag tăng |
| DNS không resolve | Redis client không tìm được endpoint được công bố |
| Packet loss/latency tăng | Tail latency, timeout và retry tăng |
| Cluster bus connectivity lỗi | Các node không trao đổi topology đầy đủ |
| Application restart | Connections, subscriptions và pending state cần phục hồi |

Có thể dùng fault-injection tools, network rules hoặc container orchestration để mô phỏng, nhưng phải giữ môi trường cô lập.

### 16.1. Vì sao pause khác crash?

Crash thường làm kết nối bị đóng hoặc nhanh chóng lỗi. Pause có thể khiến client giữ socket nhưng không nhận phản hồi. Trong lúc đó:

```text
Ứng dụng gửi INCR
        |
        v
Lệnh có thể đã tới Redis
        |
        v
Không nhận được response kịp timeout
        |
        v
Ứng dụng không biết chắc lệnh đã thực thi hay chưa
```

Test cần phân biệt **timeout chưa biết kết quả** với **lệnh chắc chắn chưa được thực hiện**. Điều này quan trọng hơn việc chỉ đo Redis đã reconnect sau bao nhiêu giây.

### 16.2. Lỗi mạng không nhất thiết làm Sentinel failover

Nếu chỉ ứng dụng bị mất kết nối tới Redis nhưng các Sentinel vẫn thấy primary khỏe, Sentinel có thể không chuyển primary. Đây là tình huống khác với việc primary thật sự chết.

Test phải nêu rõ:

```text
Fault ảnh hưởng đường nào?
App -> Redis?
Sentinel -> primary?
Replica -> primary?
Node -> Cluster bus?
```

Không gọi mọi sự cố network là “failover” vì cơ chế và kết quả mong đợi khác nhau.

## 17. Kiểm thử write ambiguity: ghi có thể đã chạy nhưng phản hồi bị mất

Một nguyên tắc quan trọng của hệ thống phân tán: **client timeout không chứng minh Redis chưa thực hiện lệnh**.

Ví dụ:

```text
Client                        Redis
   |                            |
   | INCR metrics:counter -----> |
   |                            | Counter tăng
   |        [mất response]      |
   |                            |
   | timeout                    |
```

Nếu ứng dụng retry:

```redis
INCR metrics:counter
```

counter có thể tăng **hai lần** cho một sự kiện nghiệp vụ.

### 17.1. Các thao tác cần test riêng

| Thao tác | Rủi ro khi retry sau timeout |
|---|---|
| `GET` | Thường không tạo tác dụng phụ; có thể tăng tải |
| `SET` cùng value | Có thể idempotent về value, nhưng TTL/timing vẫn cần xét |
| `INCR` | Có thể tăng hai lần |
| `LPUSH` | Có thể thêm item trùng |
| `XADD` | Có thể sinh hai entry |
| `ZINCRBY` | Có thể cộng score hai lần |
| Lua script ghi | Phụ thuộc script có idempotent hay không |
| `XACK` | Redis có thể đã ACK; retry cần hiểu trạng thái |
| Payment workflow | Không được retry tác dụng nghiệp vụ thiếu idempotency |

### 17.2. Idempotency theo operation ID

Một lệnh nghiệp vụ có thể mang `operationId` riêng:

```json
{
  "operationId": "payment-42-confirm",
  "orderId": 42,
  "action": "CONFIRM"
}
```

Receiver hoặc storage có thẩm quyền dùng `operationId` để tránh thực thi tác dụng phụ hai lần, kể cả khi:

- Request được gửi lại.
- Redis failover giữa các bước.
- HTTP response mất.
- Consumer xử lý lại pending entry.

**Không mặc định Redis lock hoặc retry của Lettuce tự cung cấp đúng một lần.** Kiểm thử phải chứng minh điều kiện idempotency hoạt động ở điểm tác dụng phụ thực sự xảy ra.

### 17.3. Test tiêu chí của write ambiguity

Một fault-injection test có thể:

1. Gửi command có operation ID qua service.
2. Giả lập mất phản hồi sau khi server có thể đã xử lý.
3. Cho client retry theo policy.
4. Đọc trạng thái nghiệp vụ ở nguồn có thẩm quyền.
5. Xác nhận tác dụng phụ không lặp vượt hợp đồng.
6. Ghi nhận các request có kết quả chưa xác định.

Nếu chỉ kiểm tra “lần retry cuối trả 200”, test chưa chứng minh tính đúng đắn.

## 18. Redis persistence, replication và giới hạn không mất dữ liệu

Một cách hiểu sai phổ biến là “Sentinel hoặc Cluster có replica thì không thể mất write”.

Redis replication thường **bất đồng bộ**. Ví dụ:

```text
Primary P             Replica R
    |                      |
SET K=V2
    |
Trả OK cho client
    |
[Primary chết trước khi R nhận V2]
                           |
                           v
                        R được promote
                           |
                      K có thể vẫn là V1
```

Một integration test phải định nghĩa:

- Dữ liệu nào chỉ là cache và có thể tái tạo.
- Dữ liệu nào không thể chấp nhận mất.
- Persistence RDB/AOF được cấu hình ra sao.
- Replica đồng bộ và failover dưới điều kiện nào.
- Kết quả bất định của lệnh sát thời điểm sự cố được xử lý thế nào.

Các cơ chế như `WAIT` hoặc những tùy chọn durability của Redis có thể làm giảm rủi ro trong một số trường hợp, nhưng không mặc nhiên biến Redis thành một hệ thống đồng thuận có bảo đảm không mất mọi write.

### 18.1. Không viết test với cam kết sai

Một assert như:

```java
assertEquals(
    "latest",
    redis.opsForValue().get("it:critical:before-failover")
);
```

sau crash ngay lúc primary vừa trả `OK` có thể là **yêu cầu mạnh hơn** khả năng replication thực tế của topology.

Nếu nghiệp vụ đòi không mất dữ liệu, cần thay đổi kiến trúc/nguồn authoritative chứ không chỉ tăng timeout cho test.

### 18.2. Đo RPO bằng dữ liệu có trình tự

Ví dụ một test writer gửi các bản ghi có `sequenceNumber` tăng dần và lưu nhật ký những lần ứng dụng đã nhận kết quả ghi thành công ở nguồn điều phối test.

Sau failover:

1. Đọc các sequence còn tồn tại.
2. Đối chiếu với bản ghi đã được ứng dụng nhìn nhận là thành công.
3. Xác định những sequence bị thiếu.
4. Đo khoảng thời gian từ write cuối được bảo toàn tới fault.
5. Đánh giá theo RPO đã công bố.

Không chỉ so sánh tổng số key; những key khác nhau có thể bị ghi đè hoặc hết TTL.

## 19. Kiểm thử Redis Streams sau failover

Một ứng dụng có Redis Streams thường có consumer group và Pending Entries List (PEL).

Ví dụ:

```redis
XGROUP CREATE it:orders billing 0 MKSTREAM
XADD it:orders * type paid orderId O-42
XREADGROUP GROUP billing consumer-a COUNT 1 STREAMS it:orders >
```

Khi `consumer-a` nhận entry nhưng chưa `XACK`, entry có thể nằm trong PEL của group.

### 19.1. Test case cần có

1. Tạo Stream và group riêng cho test.
2. Đưa một sự kiện mang `eventId` duy nhất vào Stream.
3. Consumer nhận nhưng cố tình chưa ACK.
4. Dừng consumer hoặc gây lỗi Redis có kiểm soát.
5. Cho hệ thống phục hồi.
6. Kiểm tra trạng thái pending thực tế.
7. Consumer khác dùng cơ chế đọc lại/claim phù hợp, chẳng hạn `XAUTOCLAIM`.
8. Thực hiện nghiệp vụ idempotent.
9. Chỉ `XACK` sau khi nghiệp vụ hoàn tất.
10. Xác nhận không có tác dụng phụ trùng.

### 19.2. Vì sao không chỉ chờ XREADGROUP với dấu >?

```redis
XREADGROUP GROUP billing consumer-b STREAMS it:orders >
```

Dấu `>` nhận **entry mới chưa được giao cho group**. Nó không tự nhận mọi pending entry đã giao cho consumer chết.

Để kiểm tra recovery, cần dùng `XPENDING`, đọc pending history phù hợp hoặc cơ chế claim/reclaim như:

```redis
XAUTOCLAIM it:orders billing consumer-b 60000 0-0 COUNT 10
```

Ngưỡng idle 60 giây chỉ là ví dụ. Nếu đặt quá thấp, công việc đang xử lý bình thường có thể bị claim sớm; nếu quá cao, phục hồi chậm.

### 19.3. PEL và retention cũng có thể bị ảnh hưởng

Nếu Stream đã bị trim/xóa entry trong lúc consumer còn pending, PEL có thể chứa ID không còn payload tùy phiên bản Redis và cách xóa.

Test phục hồi phải phân biệt:

- Pending vì chưa ACK.
- Entry gốc vẫn còn payload hay đã bị trim.
- Consumer group còn metadata hay bị mất do thao tác khôi phục/cấu hình.
- Retry có thể hoàn tất hay cần dead-letter/reconciliation.

Việc Redis khởi động lại không tự giải quyết tất cả vấn đề delivery và xử lý nghiệp vụ.

## 20. Pub/Sub và keyspace notifications sau sự cố

Redis Pub/Sub thông thường không lưu hàng đợi message cho subscriber offline.

Ví dụ:

```text
Subscriber kết nối
      |
      | Mất kết nối 5 giây
      |
Publisher phát event X trong 5 giây đó
      |
Subscriber reconnect
      |
      v
Không tự nhận lại event X
```

Điều tương tự quan trọng với **keyspace/keyevent notifications**, ví dụ:

```text
__keyevent@0__:expired
```

### 20.1. Test case Pub/Sub

- Khi subscriber online, event phù hợp được nhận.
- Khi subscriber bị ngắt, event phát trong khoảng offline có thể bị mất.
- Sau reconnect, subscriber nhận được **event mới**.
- Không có giả định hệ thống phát lại event cũ.

Nếu nghiệp vụ cần không mất event, không được đánh dấu test đạt bằng cách “thấy listener reconnect”. Cần Redis Streams/queue bền vững hoặc một nguồn có thẩm quyền và reconciliation.

### 20.2. Keyevent trong Redis Cluster

Keyspace notifications gắn với **node phát sự kiện**. Một listener chỉ subscribe một node không tự bao phủ mọi sự kiện từ các primary khác.

Kiểm thử:

1. Xác định slot/owner của các khóa test.
2. Cấu hình notification trên các node có liên quan.
3. Đăng ký listener trên các node cần theo dõi.
4. Tạo key có TTL ngắn ở nhiều slot.
5. Quan sát nguồn node của sự kiện.
6. Thực hiện failover hoặc reshard.
7. Xác nhận subscription được cập nhật.
8. Ghi nhận khoảng thời gian event có thể bị mất.

Không dùng keyevent như đồng hồ tuyệt đối: sự kiện `expired` được phát khi Redis thực sự xóa khóa vì hết hạn, không nhất thiết đúng vào mili giây TTL về 0.

## 21. Kiểm thử cache và TTL trong lúc Redis phục hồi

### 21.1. Cache miss sau failover

Nếu cache bị mất một phần dữ liệu:

```text
Redis failover
      |
      v
Một số cache entries không còn
      |
      v
API cache miss
      |
      v
Database bị dồn lưu lượng đọc
```

Một test phục hồi cần xác minh:

- Cache miss được phân biệt với Redis connection error.
- Fallback nguồn dữ liệu được giới hạn concurrency.
- Không có thundering herd gây quá tải database.
- Sau Redis hồi phục, cache warm lại theo ngân sách.
- Không cache dữ liệu lỗi hoặc stale quá hợp đồng.

### 21.2. TTL không được kéo dài vô ý

Ví dụ session được tạo với TTL 30 giây. Một thao tác fallback hoặc retry có thể gọi `SET EX 30` lại và **vô tình kéo dài thời gian phiên**.

Test cần xác định liệu TTL có được phép gia hạn hay phải giữ deadline tuyệt đối. Nếu yêu cầu giữ hạn:

```text
createdAt + lifetime = expiresAt
```

Không suy ra chỉ cần kiểm tra `GET` có giá trị là đã bảo vệ đúng phiên.

### 21.3. Test serialization sau restart

Ứng dụng có thể khởi động lại với phiên bản code/serializer mới khi Redis còn dữ liệu cũ.

Kiểm thử:

- Key serializer đúng.
- Value serializer giải mã được dữ liệu đã tồn tại.
- Không xuất hiện `WRONGTYPE` do thay đổi String/Hash.
- Lỗi deserialize được phân loại, không nuốt thành cache miss.
- Những key từ phiên bản cũ có quy trình migration nếu cần.

Một Redis node khởi động thành công không đồng nghĩa **mọi ứng dụng đều đọc được dữ liệu**.

## 22. Test distributed lock và stale owner

Một Redis lock có TTL không tự đảm bảo một worker cũ đã hết lease không tiếp tục ghi vào database.

Ví dụ test:

```text
Worker A lấy lease, TTL=5 giây
Worker A bị pause 8 giây
Redis cho Worker B lấy lease mới
Worker B cập nhật tài nguyên
Worker A tỉnh lại và gửi cập nhật cũ
```

Nếu hệ thống chỉ dùng `SET NX PX` và không có bảo vệ tại tài nguyên nhận, A có thể ghi đè B.

Một test có giá trị cần xác minh:

- Worker A không xóa được khóa B khi release (compare-and-delete).
- Khi dùng fencing token, receiver từ chối thao tác mang token cũ **sau khi epoch/token mới đã có hiệu lực theo giao thức**.
- Những cập nhật có thứ tự/operation ID trong cùng lease được kiểm tra đúng.
- Kết quả ghi bền vững tại receiver không bị stale worker thay đổi sai.
- Failover Redis có thể khiến token/sequence bị lùi nếu phụ thuộc replication bất đồng bộ; test không được mặc định `INCR` là nguồn fencing bền vững tuyệt đối.

Đối với tài nguyên quan trọng, điều cần kiểm thử là **điểm ghi cuối cùng**, không chỉ Redis lock key.

## 23. Failover của Redis và việc giữ nguyên cause khi xử lý lỗi

Khi Redis timeout hoặc chuyển primary, Spring Data Redis/Lettuce có thể phát nhiều nhóm exception:

```text
Connection failure
Command timeout
Topology/redirect failure
Serialization failure
Redis command error
```

Một service tốt không nuốt mọi lỗi thành `null`:

```java
try {
    return redis.opsForValue().get(key);
} catch (Exception ignored) {
    return null;
}
```

Cách này biến Redis outage thành cache miss, có thể kéo theo đọc database ồ ạt và không còn thông tin nguyên nhân.

Nên:

- Phân biệt lỗi kết nối/timeout với cache miss thật.
- Khi bọc exception, giữ original cause.
- Retry có giới hạn và theo ngữ nghĩa lệnh.
- Không log Redis key chứa token, raw value, URI có password hoặc full command arguments.
- Đo failure category và root cause type an toàn.

Ví dụ:

```java
catch (DataAccessException ex) {
    throw new CacheAccessException(
            "product_cache_read",
            RedisFailureCategory.CONNECTION,
            ex
    );
}
```

Tên `CacheAccessException` và `RedisFailureCategory` trong ví dụ là **kiểu do ứng dụng tự định nghĩa**. Mục đích là giữ cause gốc, không phải khẳng định mọi `DataAccessException` đều là lỗi kết nối; code thật phải phân loại đúng các subtype.

## 24. Retry sau failover: tránh retry storm

Một kịch bản thường gặp:

```text
Primary chết
   |
   v
Nhiều request bị timeout
   |
   v
Tất cả retry ngay lập tức
   |
   v
Primary mới vừa phục hồi đã bị dồn lệnh
   |
   v
Timeout tiếp tục
```

Đây là **retry storm**. Một test recovery cần quan sát liệu cơ chế retry có làm hệ thống khó phục hồi hơn hay không.

Các chính sách thường cần:

- Retry chỉ những lỗi phù hợp.
- Số lần retry giới hạn.
- Backoff tăng dần và jitter.
- Timeout tổng của request.
- Rate limit/bulkhead cho Redis.
- Từ chối nhanh khi đã vượt ngân sách.
- Idempotency cho write có tác dụng phụ.
- Circuit breaker có thời gian thử lại và cơ chế half-open phù hợp.

### 24.1. Không dùng sleep vô hạn trong request

Một lỗi:

```java
while (true) {
    try {
        return redisRead();
    } catch (RuntimeException ex) {
        Thread.sleep(1000);
    }
}
```

Vòng lặp này giữ tài nguyên và không có deadline. Với WebFlux, việc `Thread.sleep` trong event loop còn làm nghẽn các request khác.

Nếu API phải phản hồi dưới 2 giây, không thể chờ Sentinel failover 30 giây ngay trong mọi request. Thay vào đó, API cần trả lỗi/fallback phù hợp rồi để request sau hoặc worker background tiếp tục khi dịch vụ hồi phục.

### 24.2. Đánh giá hồi phục dưới tải thực

Một test chỉ phát một `GET` mỗi giây có thể cho thấy Redis khôi phục tốt, nhưng khi 500 request/giây trở lại, latency và pending commands có thể tăng mạnh.

Nên thử:

1. Tải nền ổn định trước sự cố.
2. Inject fault.
3. Quan sát số lỗi và queue.
4. Cho failover hoàn tất.
5. Giữ tải ở mức đã định.
6. Xác minh throughput/p99 trở lại ngưỡng.
7. Xác minh không có retry kéo dài nhiều phút.

## 25. Một ma trận tình huống kiểm thử

| Mã | Topology | Fault | Điều cần chứng minh |
|---|---|---|---|
| S1 | Sentinel | Ghi/đọc thường | Client dùng primary hiện tại |
| S2 | Sentinel | Sentinel FAILOVER | Client cập nhật primary mới |
| S3 | Sentinel | Kill primary | Phát hiện lỗi và phục hồi có deadline |
| S4 | Sentinel | Mất một Sentinel | Hệ thống xử lý đúng theo quorum/majority |
| S5 | Sentinel | Replica lag | Đường đọc có thể stale, không quyết định sai |
| S6 | Sentinel | Pause primary | Timeout và write ambiguity được xử lý |
| S7 | Sentinel | App restart | Redis connections và subscriptions hoạt động lại |
| C1 | Cluster | Multi-slot read/write | Client định tuyến theo hash slot |
| C2 | Cluster | Lệnh nhiều key khác slot | `CROSSSLOT` được nhận biết |
| C3 | Cluster | Reshard slot | `MOVED`/`ASK` và topology refresh hoạt động |
| C4 | Cluster | Failover một shard | Shard ảnh hưởng phục hồi; shard khác không bị kéo sập |
| C5 | Cluster | Đổi node IP/hostname | Announced endpoints vẫn kết nối được |
| C6 | Cluster | Mất replica | Chính sách read-from/fallback phù hợp |
| C7 | Cluster | Pause node | Timeout và bounded pending commands |
| R1 | Sentinel/Cluster | Timeout sau write | Không tạo tác dụng phụ lặp ngoài hợp đồng |
| R2 | Sentinel/Cluster | Stream pending | Consumer reclaim/idempotency/ACK đúng |
| R3 | Sentinel/Cluster | Subscriber disconnect | Không giả định Pub/Sub có replay |
| R4 | Sentinel/Cluster | Cache outage | Fallback không quá tải database |
| R5 | Sentinel/Cluster | Failover + tải lớn | RTO/p99/retry count đạt ngưỡng công bố |
| R6 | Sentinel/Cluster | Restore từ backup | Kiểm tra schema, TTL và trạng thái nghiệp vụ |

Ma trận này là điểm xuất phát. Với mỗi trường hợp, cần ghi cụ thể **setup**, **fault**, **điều kiện chờ**, **assertion**, **metric** và **cleanup**.

## 26. Đo RTO, RPO và chất lượng phục hồi

### 26.1. RTO không chỉ là thời gian có primary mới

Ví dụ:

```text
T0: Primary lỗi
T1: Sentinel/Cluster quyết định primary mới
T2: Redis data node nhận lệnh
T3: Spring client reconnect/routing đúng
T4: API đáp ứng SLO p95/p99 trở lại
```

Nếu chỉ đo `T1 - T0`, bạn đã đo thời gian failover **tầng Redis**, chưa đo **RTO của ứng dụng**.

Đối với trải nghiệm người dùng, khoảng `T4 - T0` thường có ý nghĩa hơn.

### 26.2. RPO phải đo trên dữ liệu phù hợp

RPO không thể đo bằng “Redis trả PING”. Cần có bộ dữ liệu đánh dấu thời điểm/sequence và xác minh những write đã được ứng dụng coi là hoàn tất còn tồn tại sau phục hồi.

Phân biệt:

- Write chưa từng gửi.
- Write gửi nhưng timeout (kết quả mơ hồ).
- Write được primary cũ xác nhận.
- Write còn trên primary mới.
- Write được cơ chế nghiệp vụ/source authoritative xác nhận.

Chỉ so sánh một counter tổng có thể che những bản ghi bị thiếu hoặc ghi đè.

### 26.3. Một mẫu kết quả kiểm thử

```text
Scenario: Sentinel primary crash under read/write load
Topology: 1 primary, 2 replicas, 3 Sentinels
Fault at: T0
New primary elected: T1
Client first successful write: T2
API p99 back within target: T3

Observed:
  recovery duration = T3 - T0
  timeout count
  retry count
  successful writes
  ambiguous writes
  data revisions missing after failover
  number of duplicated business effects
```

Các mốc và con số phải được **đo thực**, không tự điền giá trị đẹp để báo cáo hoàn thành.

## 27. Thiết kế test cô lập và có thể lặp lại

### 27.1. Không dùng Redis production cho destructive fault injection

Các thao tác như:

```redis
SHUTDOWN
SENTINEL FAILOVER
CLUSTER FAILOVER
CLUSTER SETSLOT
FLUSHALL
```

có thể ảnh hưởng nghiêm trọng tới môi trường đang phục vụ dữ liệu thật.

Chỉ chạy khi test infrastructure được tạo riêng và có quyền điều khiển. Không dựa vào tên môi trường “test” nếu Redis endpoint thực tế vẫn trỏ tới production.

### 27.2. Không lạm dụng FLUSHALL để cleanup

Thay vì xóa cả Redis:

```redis
FLUSHALL
```

hãy dùng key prefix riêng:

```text
it:<runId>:sentinel:...
it:<runId>:cluster:...
```

và TTL thích hợp. Sau test, xóa đúng các key đã tạo hoặc hủy toàn bộ container/volume dành riêng cho run.

Với Redis Streams/consumer group, cleanup có thể cần xóa cả Stream key của namespace test khi không còn consumer sử dụng.

### 27.3. Test song song cần namespace độc lập

Nếu hai test dùng chung:

```text
it:order:42
```

chúng có thể ghi đè nhau, gây flaky test hoặc sai kết luận về failover.

Dùng:

```text
it:<testRunId>:order:42
```

Riêng các test cần failover/reshard phải có **quyền sở hữu topology độc lập**, bởi hai test cùng lúc đổi role/slot sẽ tương tác với nhau dù dữ liệu đã tách prefix.

### 27.4. Poll theo điều kiện thay vì sleep dài

Điều kiện có thể gồm:

- Node mới có `ROLE` = primary.
- `CLUSTER INFO` báo topology hoạt động.
- Slot owner đã thay đổi.
- Spring Redis client ghi thành công với key có TTL.
- API đạt tỷ lệ thành công mong muốn trong một cửa sổ quan sát.

Poll phải có timeout tối đa. Nếu quá hạn, test thất bại và ghi chẩn đoán an toàn: roles, node IDs, thời gian, error category.

### 27.5. Cleanup sau failover

Trong môi trường cô lập, sau test có thể xóa và khởi tạo lại toàn bộ topology để bảo đảm lần chạy sau bắt đầu từ trạng thái xác định.

Nếu tái sử dụng container:

- Sentinel có thể đã cập nhật cấu hình master.
- Redis replica có thể đã đổi vai trò.
- Cluster slot ownership có thể đã thay đổi.
- App connection pool có thể đang giữ địa chỉ cũ.
- Các subscriptions có thể vẫn hoạt động.

Chỉ restart một container không nhất thiết khôi phục topology ban đầu. **Reset hoàn chỉnh hoặc xác nhận state ban đầu** là điều kiện quan trọng cho test có thể lặp lại.

## 28. Tránh flaky test do môi trường CI

Một số lỗi integration test không xuất phát từ business code:

| Nguyên nhân | Biểu hiện |
|---|---|
| CPU CI bị giới hạn | Sentinel failover chậm bất thường |
| Docker DNS không ổn định | Client không resolve node được công bố |
| Port mapping sai | Seed connect được nhưng redirect thất bại |
| Các container chưa ready | Test ghi lệnh trước khi Cluster cover slot |
| Sentinel config read-only | Failover cập nhật topology không ổn định |
| Redis version không tương thích | Lệnh/cờ cấu hình khác kỳ vọng |
| Timeouts quá thấp | False failure dưới tải CI |
| Test chạy song song trên cùng topology | Cùng đổi primary/slot, trạng thái không xác định |
| Reuse Redis volumes | Dữ liệu/config từ test trước còn sót |
| Replica chưa đồng bộ trước fault | Test mất dữ liệu nhiều hơn giả định |
| Clock giữa các máy chênh lệch | Đo thời gian bằng đồng hồ wall-clock không chính xác |

### 28.1. Chờ readiness có ý nghĩa

Một container “process đã mở cổng” chưa có nghĩa Redis Cluster đã sẵn sàng.

Điều kiện readiness nên bao gồm:

- Các Redis nodes cần thiết có thể kết nối.
- Sentinel phát hiện nhóm master.
- Replica có trạng thái replication phù hợp với kịch bản.
- Cluster đã gán đủ hash slots và trạng thái tốt.
- JVM test truy cập được **mọi địa chỉ Redis công bố**.
- Spring Data Redis đã khởi tạo xong connection factory và có thể gửi lệnh.

### 28.2. Dùng monotonic clock để đo elapsed time

Thời lượng phục hồi nên đo bằng đồng hồ đo khoảng thời gian, chẳng hạn `System.nanoTime()` trong JVM:

```java
long started = System.nanoTime();

triggerFault();

awaitRecovery();

long elapsedMillis =
        java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started
        );
```

Đồng hồ wall-clock như `System.currentTimeMillis()` vẫn hữu ích để ghi timestamp, nhưng có thể thay đổi do đồng bộ thời gian; không nên chỉ dựa vào nó để đo duration cần độ chính xác.

## 29. Những lỗi phổ biến khi kiểm thử

### Lỗi 1: Một Redis container được gọi là Sentinel test

Không có Sentinel quorum hay replica thì chưa kiểm chứng failover Sentinel. Chỉ dùng standalone container làm test cơ bản.

### Lỗi 2: Chỉ test PING sau failover

PING thành công không chứng minh read/write routing đúng, dữ liệu còn hợp lệ hoặc API đã phục hồi.

### Lỗi 3: Chờ 10 giây rồi giả định failover xong

Thời gian phụ thuộc tải, mạng và cấu hình Sentinel/Cluster. Dùng condition polling có deadline.

### Lỗi 4: Sentinel công bố hostname không truy cập được

JVM có thể kết nối Sentinel nhưng không kết nối data node do Sentinel trả về. Kiểm tra network path toàn bộ.

### Lỗi 5: Cluster seed kết nối được nhưng MOVED thất bại

Driver không truy cập được địa chỉ node công bố trong redirect. Test phải chạy với các key thuộc nhiều slot.

### Lỗi 6: Mọi key test nằm cùng slot

Không phát hiện lỗi định tuyến các shard khác. Chọn và xác minh nhiều slot/primary.

### Lỗi 7: Chỉ test sau khi reshard hoàn tất

Bỏ qua `ASK`, redirect trong khi slot đang migrate và timeout của request đang chạy.

### Lỗi 8: Mọi lỗi GET bị coi là cache miss

Làm mất tín hiệu connection failure và che database overload. Phân biệt miss với Redis error.

### Lỗi 9: Retry INCR hoặc XADD vô điều kiện

Có thể tạo tác dụng phụ trùng nếu response đầu tiên bị mất. Test idempotency theo operation ID.

### Lỗi 10: Bắt buộc Redis async replication không mất write

Đòi cam kết mạnh hơn kiến trúc hiện tại và dẫn đến test sai. Định nghĩa RPO và nguồn dữ liệu có thẩm quyền.

### Lỗi 11: Đường đọc replica phải stale trong test

Replication nhanh có thể khiến replica thấy dữ liệu mới ngay. Test điều kiện nhất quán chứ không đòi xảy ra race ngẫu nhiên.

### Lỗi 12: Quên pending của Redis Streams

Consumer restart chỉ đọc `>` có thể bỏ lại công việc pending. Cần thử reclaim và idempotency.

### Lỗi 13: Giả định Pub/Sub phát lại khi reconnect

Pub/Sub không lưu lịch sử. Test recovery phải tính tới event có thể mất khi offline.

### Lỗi 14: Chỉ đo failover của Redis server

Ứng dụng có thể còn lỗi routing hoặc pending command queue sau khi Redis đã có primary mới. Đo phục hồi end-to-end.

### Lỗi 15: Không quan sát các shard không bị ảnh hưởng

Một shard lỗi có thể làm toàn app timeout nếu client/giới hạn tải thiết kế không tốt. Test cả affected và unaffected keys.

### Lỗi 16: Chạy failover tests song song trên cùng topology

Hai test thay primary/slot cùng lúc làm kết quả không thể diễn giải. Tách môi trường hoặc chạy tuần tự.

### Lỗi 17: FLUSHALL trên Redis dùng chung

Có thể xóa dữ liệu của test khác hoặc dữ liệu thật. Namespace hóa key và cleanup đúng phạm vi.

### Lỗi 18: Không xác minh phiên bản Redis và driver

Một lệnh/option khác nhau theo Redis/Lettuce/Spring Data Redis version. Test phải ghi nhận chính xác dependency và mode.

### Lỗi 19: Chỉ đo p50

Trong sự cố, p99, timeout và tỷ lệ request lỗi thường quan trọng hơn latency trung bình.

### Lỗi 20: Giả định timeout nghĩa là write chưa thực thi

Kết quả có thể mơ hồ; retry cần idempotency và kiểm tra trạng thái nghiệp vụ.

## 30. Một kế hoạch kiểm thử từ đầu đến cuối

### Giai đoạn A — Xác nhận chức năng cơ bản

- Chạy standalone integration test với Redis thật.
- Kiểm tra key/value/hash serializers.
- Kiểm tra TTL, cache hit/miss.
- Kiểm tra lệnh và cách phân loại lỗi.
- Ghi nhận phiên bản Redis/driver.

### Giai đoạn B — Xác nhận Sentinel

- Tạo môi trường 1 primary, 2 replica, 3 Sentinel.
- Kiểm tra discovery và primary routing.
- Kiểm tra đọc replica theo chính sách ứng dụng.
- Chủ động failover trong môi trường test.
- Chờ primary đổi, app reconnect và ghi lại được.
- Đối chiếu dữ liệu trước/sau theo RPO.

### Giai đoạn C — Xác nhận Cluster

- Tạo Cluster nhiều primary/replica.
- Xác nhận 16.384 slots được phân bổ.
- Kiểm tra route trên nhiều slot.
- Kiểm tra key nhiều phần cùng hash tag.
- Thực hiện reshard và quan sát `MOVED`/`ASK`.
- Failover một shard và kiểm tra các shard khác.

### Giai đoạn D — Xác nhận hành vi ứng dụng khi lỗi

- Phân biệt cache miss và lỗi Redis.
- Kiểm tra fallback chỉ cho lỗi phù hợp.
- Kiểm tra write ambiguity, idempotency và retry.
- Kiểm tra Streams pending/reclaim.
- Kiểm tra Pub/Sub mất sự kiện khi subscriber offline.
- Kiểm tra lock/fencing tại tài nguyên nhận khi cần.

### Giai đoạn E — Đo phục hồi và tải

- Phát traffic nền đại diện workload thật.
- Gây fault có timestamp.
- Thu latency, error rate, retry/pending commands.
- Đo RTO ở tầng API và RPO ở tầng dữ liệu.
- Xác nhận hệ thống tự phục hồi và trở lại trạng thái ổn định.
- Lưu báo cáo cùng topology, phiên bản và cấu hình test.

## 31. Câu hỏi tự kiểm tra

**1. Một test dùng một container Redis có kiểm thử được Sentinel failover không?**

Không. Nó chỉ kiểm tra Redis standalone; Sentinel failover cần các thành phần Sentinel, primary và replica phù hợp.

**2. Sentinel có đóng vai trò proxy nhận tất cả lệnh từ Spring Boot không?**

Không. Sentinel giúp khám phá topology và failover; client thường kết nối trực tiếp tới Redis data nodes.

**3. Vì sao Redis primary mới có thể thiếu một write đã được primary cũ trả OK?**

Vì replication thông thường bất đồng bộ; replica được promote có thể chưa nhận write đó trước khi primary cũ lỗi.

**4. Chỉ đợi `CLUSTER INFO` báo OK đã chứng minh ứng dụng phục hồi chưa?**

Chưa. Ứng dụng còn cần kết nối được các node công bố, route lệnh đúng và phục vụ theo SLO.

**5. `MOVED` và `ASK` có cùng ý nghĩa không?**

Không. `MOVED` chỉ tới slot owner hiện tại; `ASK` dùng trong giai đoạn slot migration với quy trình chuyển hướng tạm thời.

**6. Vì sao Docker mapped port đúng nhưng Cluster test vẫn lỗi?**

Vì địa chỉ mà node công bố trong redirect/topology có thể không truy cập được từ JVM.

**7. Có nên dùng `Thread.sleep(10000)` để xác nhận failover đã hoàn tất không?**

Không nên. Dùng polling theo điều kiện với deadline để giảm flaky và có bằng chứng topology/ứng dụng thật sự phục hồi.

**8. Vì sao không nên test rằng replica luôn trả dữ liệu cũ ngay sau write?**

Vì replica có thể đồng bộ rất nhanh. Race này không phải lúc nào cũng xảy ra.

**9. Timeout sau `INCR` có cho phép tự động retry an toàn không?**

Không chắc. Redis có thể đã tăng counter nhưng client không nhận phản hồi; retry có thể tăng lần nữa.

**10. Nếu Redis Streams consumer chết khi message còn pending, worker mới chỉ đọc `>` có lấy lại pending không?**

Không. Cần cơ chế đọc pending/reclaim như `XAUTOCLAIM`, cộng với idempotency và ACK khi hoàn thành.

**11. Pub/Sub subscriber reconnect có nhận lại sự kiện đã phát khi offline không?**

Không. Redis Pub/Sub thông thường không có replay/ACK cho các message đó.

**12. RTO của ứng dụng khác thời gian Sentinel bầu xong primary thế nào?**

Ứng dụng còn phải reconnect, định tuyến đúng, xử lý tải tồn đọng và phục vụ lại trong SLO. Cần đo đến mức dịch vụ thực sự hồi phục.

**13. Kiểm thử Cluster failover một shard cần quan sát những key nào?**

Cả key thuộc shard bị ảnh hưởng lẫn các key thuộc shard khác, để kiểm tra cô lập sự cố và phục hồi.

**14. Tại sao phải tránh `FLUSHALL` trên Redis dùng chung trong test?**

Vì nó xóa dữ liệu ngoài phạm vi test, có thể làm hỏng các bài test khác hoặc dữ liệu thật.

**15. Nếu Redis hết lỗi nhưng database bị quá tải vì cache miss hàng loạt, có xem là phục hồi thành công không?**

Không hoàn toàn. Phục hồi phải được đánh giá end-to-end theo tỷ lệ lỗi, độ trễ, tải phụ thuộc và SLO của ứng dụng.

## 32. Ghi nhớ

- **Sentinel và Redis Cluster là hai topology khác nhau**: Sentinel giám sát/promote primary; Cluster định tuyến theo hash slot và có thể thay đổi slot owner.
- **Test Redis standalone chưa phải test failover**. Muốn chứng minh phục hồi phải có Redis thật, topology thích hợp và fault injection có kiểm soát.
- **Kiểm tra điều kiện thay vì sleep cố định**: xác nhận primary/slot owner đã đổi, client đã reconnect và application read/write thực sự hoạt động.
- **Redis replication thông thường bất đồng bộ**; không mặc định mọi write được primary cũ xác nhận đều xuất hiện trên primary mới.
- **Redis Cluster phải test nhiều slot**, địa chỉ node công bố, `MOVED`/`ASK`, reshard và failover từng shard.
- **Timeout ghi có thể mơ hồ**: không retry `INCR`, `XADD` hoặc tác vụ nghiệp vụ có side effect mà thiếu idempotency.
- **Streams cần thử pending/reclaim**, Pub/Sub không có replay; cache cần fallback và warm lại có giới hạn.
- **Đo RTO/RPO ở tầng nghiệp vụ**, gồm error rate, p95/p99, retry storm, lost writes và duplicate effects.
- **Chỉ gây sự cố trên hạ tầng kiểm thử cô lập**, dùng namespace/TTL riêng và đảm bảo cleanup có thể lặp lại.

### Tài liệu tham khảo

- [Spring Data Redis — Redis connection modes](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html).
- [Spring Data Redis — Redis Configuration](https://docs.spring.io/spring-data/redis/reference/redis/redis-configuration.html).
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html).
- [Redis — Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/).
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/).
- [Redis — Cluster tutorial](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/).
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/).
- [Redis — CLUSTER FAILOVER](https://redis.io/docs/latest/commands/cluster-failover/).
- [Redis — CLUSTER SHARDS](https://redis.io/docs/latest/commands/cluster-shards/).
- [Redis — XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/).
- [Lettuce — High Availability and Sharding](https://redis.github.io/lettuce/ha-sharding/).
- [Testcontainers Java — Documentation](https://java.testcontainers.org/).
- [Awaitility — Project site](https://github.com/awaitility/awaitility).
