# Khởi động, kiểm tra sẵn sàng và đóng kết nối có kiểm soát

Trong ứng dụng **Spring Data Redis**, việc tạo được bean `RedisTemplate` hoặc `ReactiveRedisTemplate` không có nghĩa Redis đã sẵn sàng để phục vụ mọi thao tác. Khi triển khai lên máy chủ, Docker hoặc Kubernetes, ứng dụng trải qua nhiều trạng thái: **khởi tạo cấu hình**, **thiết lập kết nối**, **làm nóng những tài nguyên cần thiết**, **nhận lưu lượng**, **chuyển sang trạng thái dừng**, **hoàn tất công việc đang xử lý**, rồi **giải phóng kết nối**.

Quản lý các giai đoạn này là vấn đề về **lifecycle**, không chỉ là cách gọi `PING` lúc khởi động. Redis có thể bị mất kết nối sau khi ứng dụng đã sẵn sàng; một Redis cache tùy chọn có chính sách khác với Redis chứa phiên đăng nhập; và một Redis Streams consumer cần dừng nhận message mới, xử lý hoặc để pending đúng cách trước khi JVM kết thúc.

Bài học trình bày cách thiết kế vòng đời **Spring Boot + Spring Data Redis + Lettuce**, kết hợp Spring Boot Actuator, graceful shutdown, Kubernetes probes, Redis Streams/Pub/Sub và các tình huống failover.

## 1. Mục tiêu của một vòng đời Redis an toàn

Một triển khai đáng tin cậy cần trả lời những câu hỏi sau:

1. **Khi khởi động:** ứng dụng đã đọc cấu hình, secret, TLS certificate và tạo connection factory hợp lệ chưa?
2. **Trước khi nhận request:** Redis có thật sự truy cập được qua endpoint cần thiết và có đủ quyền chạy các lệnh quan trọng không?
3. **Khi Redis lỗi tạm thời:** ứng dụng cần chờ, trả lỗi, dùng fallback hay rời trạng thái ready?
4. **Khi shutdown:** load balancer đã ngừng chuyển request mới đến instance chưa?
5. **Với worker nền:** đã ngừng poll/subscribe, hoàn tất tác vụ in-flight và chỉ ACK khi side effect thành công chưa?
6. **Với connection:** application có để Spring và driver giải phóng tài nguyên đúng thứ tự, thay vì đóng connection pool ngay khi handler còn chạy không?
7. **Khi rolling deployment:** ít nhất một instance khác có thể nhận tải và thực hiện phần công việc quan trọng không?
8. **Khi failover:** ứng dụng có xử lý kết quả lệnh không xác định, kết nối lại và phục hồi trạng thái cần thiết không?

Có thể mô tả các giai đoạn như sau:

```text
Container/process được tạo
           |
           v
Đọc cấu hình và tạo Spring context
           |
           v
Khởi tạo RedisConnectionFactory / Lettuce
           |
           v
Kiểm tra dependency thiết yếu
và khởi tạo group/worker khi cần
           |
           v
Readiness = ACCEPTING_TRAFFIC
           |
           v
Phục vụ HTTP + background processing
           |
           v
Nhận tín hiệu dừng / rollout / scale-down
           |
           v
Readiness = REFUSING_TRAFFIC
           |
           v
Ngừng nhận request và công việc mới
           |
           v
Drain công việc đang xử lý với deadline
           |
           v
ACK/commit đúng phần đã hoàn tất;
phần chưa xong còn khả năng recovery
           |
           v
Dừng listener, scheduler, worker và
giải phóng Redis connections
           |
           v
JVM/container kết thúc
```

**Điều cốt lõi:** sự kiện “ứng dụng chạy được” khác với “ứng dụng sẵn sàng nhận tải”; “đang dừng” khác với “mọi tác vụ đã hoàn tất”; và “đã gửi lệnh Redis” khác với “đã nhận được kết quả chắc chắn”.

## 2. Ba tín hiệu cần phân biệt: startup, liveness, readiness

Ở môi trường orchestrator như Kubernetes, ba loại kiểm tra phục vụ các mục tiêu khác nhau:

| Tín hiệu | Câu hỏi | Phản ứng điển hình |
|---|---|---|
| **Startup** | Tiến trình đã có đủ thời gian hoàn thành giai đoạn khởi động chưa? | Chưa vội đánh giá liveness trong startup dài |
| **Liveness** | Tiến trình còn có khả năng tự tiếp tục hoạt động hay đã bị kẹt nghiêm trọng? | Restart container khi thực sự không thể phục hồi |
| **Readiness** | Instance này **ngay bây giờ** có nên nhận thêm request/công việc mới không? | Ngừng chuyển request mới tới instance không ready |

Một sai lầm phổ biến là đưa mọi dependency vào liveness check:

```text
Redis tạm mất kết nối
       |
       v
Liveness trả DOWN
       |
       v
Kubernetes restart mọi API pod
       |
       v
Pod mới đồng loạt khởi động và kết nối Redis
       |
       v
Redis càng chịu áp lực, các pod tiếp tục restart
```

Nếu một ứng dụng còn hoạt động và có thể phục hồi khi Redis quay lại, **Redis outage thường không phải lý do tốt để đánh dấu liveness thất bại**. Readiness hoặc một trạng thái degraded phù hợp hơn, tùy vai trò Redis trong nghiệp vụ.

Ngược lại, nếu Redis là kho phiên đăng nhập bắt buộc và ứng dụng không thể xác thực request khi Redis unavailable, readiness của API có thể cần chuyển sang không sẵn sàng. Điều đó không nhất thiết đòi hỏi khởi động lại tiến trình.

### Quy tắc vận hành

- **Liveness:** tập trung vào tình trạng nội tại của process, không kiểm tra mọi hệ thống ở xa.
- **Readiness:** phản ánh khả năng nhận công việc mới; chỉ đưa dependency thiết yếu vào nếu việc dependency thất bại thực sự khiến instance không thể phục vụ.
- **Startup:** cấp ngân sách riêng cho khởi động chậm, chẳng hạn khởi tạo JVM, đọc secret hoặc warm-up bắt buộc.
- **Business health:** đo riêng tình trạng worker, backlog và nguồn sự thật; một `PONG` không chứng minh nghiệp vụ khỏe mạnh.

## 3. Bean Redis được tạo không đồng nghĩa Redis đã kết nối

Spring Boot có thể tự cấu hình `LettuceConnectionFactory` và `StringRedisTemplate`:

```text
Spring Boot application context
          |
          v
    Redis properties
          |
          v
 LettuceConnectionFactory
          |
          +--> StringRedisTemplate
          +--> RedisTemplate<K,V>
          +--> ReactiveRedisTemplate<K,V>
```

Tùy driver, cấu hình và lifecycle, một connection có thể được tạo hoặc sử dụng **lười (lazy)** ở lần thực thi command đầu. Ngay cả khi connection factory khởi tạo thành công, điều đó không chứng minh:

- DNS Redis resolve được từ ứng dụng.
- TLS handshake sẽ thành công.
- Redis ACL user có quyền lệnh cần dùng.
- Redis Cluster seed nodes quảng bá địa chỉ có thể truy cập.
- Sentinel discovery trả primary hiện hành mà ứng dụng tới được.
- Các namespace/serializer/script đang dùng tương thích.
- Redis sẽ còn sẵn sàng sau một giây nữa.

Ví dụ, một bean được inject thành công:

```java
@Service
public class ProductCache {

    private final StringRedisTemplate redis;

    public ProductCache(StringRedisTemplate redis) {
        this.redis = redis;
    }
}
```

không phải là bằng chứng `GET` đã chạy. Readiness chỉ có ý nghĩa khi kiểm tra đúng năng lực mà instance thật sự cần phục vụ, với timeout và chính sách lỗi rõ ràng.

## 4. Cấu hình Redis client có timeout và bảo mật

Ví dụ cấu hình Spring Boot dùng Lettuce và Redis endpoint nội bộ có TLS:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6379}
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      connect-timeout: 2s
      timeout: 2s
```

Các biến môi trường là ví dụ, không chứa credential thật.

Những điều cần xác nhận:

1. `REDIS_HOST` trỏ tới private endpoint phù hợp với môi trường.
2. Port đang chạy đúng giao thức, gồm TLS/plain TCP.
3. Certificate server được tin cậy và hostname được xác minh.
4. Username/password là Redis ACL credential còn hiệu lực.
5. Timeout phù hợp với latency budget của ứng dụng.
6. Driver và Redis server hỗ trợ topology được cấu hình.
7. Không log password hoặc connection URI có credential.
8. Không lạm dụng thời gian chờ quá lớn khiến shutdown hoặc readiness check bị treo lâu.

**Hai loại timeout có mục đích khác nhau:** connect timeout giới hạn thời gian thiết lập kết nối; command timeout giới hạn thời gian chờ phản hồi của thao tác. Ngoài ra, HTTP request còn có deadline tổng thể của riêng nó. Giá trị timeout phải được thiết kế cùng nhau, không tăng tất cả lên vài phút để che một sự cố mạng.

### 4.1. Redis Standalone, Sentinel và Cluster

Cùng là Spring Data Redis nhưng endpoint khác topology:

- **Standalone:** kết nối tới một địa chỉ Redis; nếu node không có HA, outage có thể kéo dài.
- **Sentinel:** client cần kết nối được tới Sentinel và Redis primary/replica được discovery.
- **Cluster:** client cần định tuyến theo hash slot và truy cập được những node Redis được topology quảng bá.

Một `PING` tới một seed node không chứng minh toàn bộ Redis Cluster phục vụ được mọi slot. Khi readiness yêu cầu mức bảo đảm cao hơn, cần kiểm tra các thao tác tiêu biểu hoặc giám sát topology theo cơ chế của driver, nhưng tránh biến mỗi HTTP health request thành một vòng kiểm tra nặng trên mọi shard.

## 5. Spring Boot Actuator và health endpoints

Spring Boot Actuator cung cấp health endpoint và các health groups để tích hợp với hệ thống triển khai.

Dependency thường dùng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Khi có Redis connection factory và auto-configuration phù hợp, Actuator có thể đăng ký một Redis health contributor. Contributor này kiểm tra kết nối/lệnh Redis theo hợp đồng phiên bản Spring Boot/Spring Data Redis tương ứng.

Ví dụ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info

  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
```

Những đường dẫn thường gặp:

```text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
```

Khi bật probes, Spring Boot dùng thông tin trạng thái ứng dụng để hỗ trợ liveness/readiness. **Không mặc định rằng Redis health contributor đã được đưa vào readiness group**: các nhóm probe mặc định chủ yếu dựa trên trạng thái availability. Muốn readiness phụ thuộc Redis, phải cấu hình rõ và hiểu tác động.

### 5.1. Chỉ thêm Redis vào readiness khi nó thiết yếu

Ví dụ ứng dụng không thể xử lý request nếu Redis unavailable:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,redis
```

Cách này giả định Redis health contributor được tạo với tên `redis` trong phiên bản/cấu hình hiện tại. Nếu ứng dụng không có contributor tương ứng hoặc dùng tên khác, cần điều chỉnh theo danh sách contributor thực tế thay vì để health group cấu hình sai.

Tác động mong muốn:

```text
ReadinessState = ACCEPTING_TRAFFIC
                  +
Redis health = UP
                  |
                  v
Readiness group = UP

ReadinessState = ACCEPTING_TRAFFIC
                  +
Redis health = DOWN
                  |
                  v
Readiness group = DOWN
```

Nhưng cần nhớ: nếu **mọi pod** dùng chung Redis và Redis lỗi, tất cả pod có thể đồng loạt chuyển sang not ready, khiến service không còn endpoint. Đó có thể là lựa chọn đúng nếu mọi request đều phụ thuộc Redis, nhưng không phù hợp nếu Redis chỉ là cache tùy chọn và vẫn có đường đọc database an toàn.

### 5.2. Redis là cache tùy chọn thì sao?

Nếu Redis chỉ dùng để tăng tốc catalog cache và ứng dụng có fallback được bảo vệ:

- Có thể giữ readiness `UP` khi Redis tạm lỗi.
- Ghi metric riêng `redis_unavailable`, `cache_fallback_total`, p95/p99 database.
- Giới hạn số request fallback để không gây cascading failure.
- Cảnh báo degradation, không giả thành cache miss bình thường.
- Nếu fallback bắt đầu vượt capacity, instance có thể cần chủ động giảm lưu lượng theo một chính sách riêng.

**Tùy chọn ở mức dữ liệu không có nghĩa fallback vô hạn.** Một Redis outage có thể làm database quá tải nếu hàng nghìn instance đồng loạt bỏ cache.

## 6. PING chỉ kiểm tra một phần năng lực

Một thao tác `PING` thường được dùng để xác định Redis trả lời lệnh cơ bản:

```bash
redis-cli --host private-redis.example.internal \
  --port 6379 PING
```

Với kết nối TLS/ACL, dùng tùy chọn xác thực và tin cậy certificate phù hợp; không đặt password thật trên dòng lệnh hoặc trong shell history.

Một kết quả `PONG` có ích nhưng **chưa chứng minh**:

- User ACL được phép `GET`/`SET` các key ứng dụng cần.
- Lua script hoặc Redis Streams hoạt động.
- Session repository ghi/đọc đúng schema và serializer.
- Tất cả slot Redis Cluster đều truy cập được.
- Replica reads đáp ứng freshness.
- Database downstream và business handler đang khỏe.
- Worker nền vẫn polling/ACK message.

Readiness có thể được thiết kế nhiều tầng:

| Mức kiểm tra | Nội dung | Chi phí/tác động |
|---|---|---|
| Process availability | Spring đã khởi động và chưa yêu cầu dừng | Nhẹ |
| Redis basic health | Ping/command đơn giản | Thường nhẹ, vẫn cần timeout |
| Capability check | Lệnh đúng quyền và namespace | Có thể cần key test/cleanup |
| Business readiness | Worker có thể xử lý, nguồn sự thật còn sẵn sàng | Có thể tốn chi phí nếu kiểm tra quá thường xuyên |
| End-to-end synthetic | Sự kiện test đi hết chuỗi xử lý | Nên chạy ở tần suất thấp và môi trường kiểm soát |

Không đưa một giao dịch ghi dữ liệu phức tạp vào liveness probe được gọi vài giây một lần. Có thể dùng kiểm thử synthetic riêng hoặc indicator đọc trạng thái đã đo ở background.

## 7. Kiểm tra Redis trước khi nhận traffic

Nếu Redis là dependency bắt buộc ngay khi khởi động, có thể thực hiện kiểm tra nhẹ trong một `ApplicationRunner`. Runner chạy trong giai đoạn startup trước khi Spring Boot công bố ứng dụng hoàn toàn ready.

Ví dụ:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class RedisStartupCheckConfiguration {

    @Bean
    ApplicationRunner verifyRedisBeforeReady(
            StringRedisTemplate redis) {

        return args -> {
            String pong = redis.execute(
                    (RedisCallback<String>) connection ->
                            connection.ping());

            if (!"PONG".equalsIgnoreCase(pong)) {
                throw new IllegalStateException(
                        "Redis PING did not return PONG");
            }
        };
    }
}
```

Trong ví dụ này, nếu Redis không thể kết nối hoặc PING không hợp lệ, startup thất bại. Đây là **một chính sách** phù hợp khi ứng dụng không thể hoạt động nếu không có Redis, không phải yêu cầu mặc định cho mọi cache.

### 7.1. Ưu điểm

- Phát hiện sớm cấu hình sai về host, TLS, credential, port.
- Không phục vụ request khi một dependency tối quan trọng chưa truy cập được.
- Log lỗi ngay tại startup thay vì để request đầu tiên thất bại khó hiểu.
- Có thể kết hợp với việc tạo consumer group hoặc chuẩn bị cấu trúc cần thiết nếu quy trình được thiết kế idempotent.

### 7.2. Giới hạn và rủi ro

- `PING` tại một thời điểm không đảm bảo Redis luôn sẵn sàng.
- Startup phụ thuộc Redis có thể gây **restart loop** nếu Redis outage tạm thời.
- Nhiều pod cùng startup có thể đồng loạt gây connection spike.
- Một cache tùy chọn không nhất thiết nên chặn toàn bộ ứng dụng.
- Health check chỉ dùng quyền `PING` có thể bỏ sót lỗi ACL với lệnh nghiệp vụ.
- Nếu khởi tạo dữ liệu/consumer group trong runner, thao tác phải idempotent khi nhiều replica cùng chạy.

Do đó, hãy chọn rõ một trong hai mô hình:

1. **Fail fast:** Redis không có thì ứng dụng không khởi động; phù hợp dependency bắt buộc với hệ thống restart được điều phối.
2. **Start but not ready/degraded:** context vẫn chạy để reconnect; readiness chặn traffic cần Redis hoặc ứng dụng có fallback giới hạn.

Không trộn hai mô hình thiếu chủ đích, ví dụ vừa fail startup ngay khi Redis outage, vừa kỳ vọng Actuator readiness tự chuyển lại UP mà không restart.

## 8. Retry khi khởi động: giới hạn, backoff và jitter

Khi Redis chưa lên kịp, ứng dụng có thể cần thử kết nối lại. Nhưng nếu mọi replica retry ngay mỗi 10 ms, Redis đang phục hồi sẽ chịu thêm tải.

Một chính sách retry có giới hạn nên xác định:

- Loại lỗi nào có thể transient: connection refused, DNS tạm thời, failover.
- Loại lỗi nào cần sửa cấu hình: password sai, certificate invalid, ACL `NOPERM`, key schema sai.
- Số lần thử tối đa hoặc startup deadline.
- Backoff tăng dần và jitter giữa các replica.
- Tổng thời gian chờ vẫn nằm trong ngân sách startup probe.
- Khi vượt deadline, ứng dụng sẽ fail fast hay tiếp tục không ready.

Ví dụ chính sách minh họa:

```text
Attempt 1: ngay khi startup
Attempt 2: sau khoảng 200 ms
Attempt 3: sau khoảng 500 ms
Attempt 4: sau khoảng 1 s
Attempt 5: sau khoảng 2 s
Sau đó: dừng và trả trạng thái startup failure
```

Thời gian trên chỉ là ví dụ. Retry một lệnh `PING` idempotent khác với retry `INCR` hoặc một script có side effect: **network timeout của lệnh ghi có thể có kết quả không xác định**.

Nếu ứng dụng sử dụng Redis Cluster, Lettuce có thể thực hiện reconnect và topology refresh theo driver configuration. Không tự viết vòng retry bao ngoài mọi lệnh rồi coi driver sẽ luôn ngăn được side effect trùng.

## 9. Làm nóng cache và khởi tạo dữ liệu khi startup

Một số ứng dụng cần prewarm key nóng, nạp feature flags hoặc tạo consumer group trước khi nhận traffic.

Cần phân biệt:

| Công việc | Có cần chặn readiness? | Lưu ý |
|---|---|---|
| Kiểm tra Redis bắt buộc | Có thể | Tránh false readiness |
| Tải configuration sống còn | Có thể | Phải có timeout và xử lý lỗi |
| Warm cache catalog | Thường không bắt buộc | Có thể chạy background có giới hạn |
| Nạp hàng triệu cache keys | Không nên chặn startup vô hạn | Làm theo batch, giới hạn tải |
| Tạo Redis Streams group | Cần trước khi consumer đọc | Idempotent khi nhiều replica |
| Chạy migration schema | Thường là tác vụ triển khai riêng | Không để mọi pod cùng migration |
| Kiểm tra vài key mẫu | Tùy yêu cầu | Không để health check ghi/xóa dữ liệu nghiệp vụ |

### 9.1. Không dùng warm-up như điều kiện chung cho mọi readiness

Ví dụ một ứng dụng catalog có 100.000 sản phẩm. Nếu mọi pod phải tải toàn bộ vào L1/Redis trước readiness, khi rolling deploy có thể tạo hàng trăm nghìn request database và làm rollout chậm.

Thay vào đó:

- Warm-up một tập hot key có giới hạn.
- Cho cache đi vào trạng thái warm-up sau khi app đã nhận traffic nếu nghiệp vụ cho phép.
- Áp concurrency limit để bảo vệ database/Redis.
- Tách warm-up khỏi đường request nếu có thời gian và ngân sách tài nguyên.
- Theo dõi hit-rate trong vài phút đầu sau deploy.

**Readiness cần biểu diễn khả năng phục vụ**, không phải “mọi dữ liệu có thể được cache đều đã cache xong”.

## 10. Redis Streams: khởi tạo consumer group không gây đụng độ

Nếu ứng dụng chạy một Redis Streams consumer group, cấu hình đầu vào cần xác định:

- Stream key và consumer group name.
- Consumer name riêng cho worker/instance.
- Offset khởi tạo nếu group chưa tồn tại.
- Chính sách xử lý group đã tồn tại.
- Pending recovery khi worker restart.
- Quy tắc ACK sau business commit.

Ví dụ Redis CLI:

```bash
redis-cli XGROUP CREATE stream:orders:v1 order-workers 0 MKSTREAM
```

`0` biểu thị group có thể nhận lịch sử còn lưu từ đầu stream; tạo bằng `$` sẽ bắt đầu từ cuối tại thời điểm tạo group và có thể bỏ qua event cũ khi đọc new messages.

Một lỗi `BUSYGROUP` có thể xuất hiện nếu group đã tồn tại. Trong ứng dụng nhiều replica, đây là tình huống có thể gặp khi các instance cùng startup.

**Không xóa và tạo lại group trên mỗi lần khởi động** để “sửa” `BUSYGROUP`. Việc đó có thể phá tiến độ phân phối và PEL của các event chưa ACK. Quy trình tạo group phải idempotent và chỉ xử lý lỗi đã được xác định rõ là group tồn tại; lỗi kết nối/ACL không được nuốt như thể khởi tạo thành công.

### 10.1. Chưa có event mới không có nghĩa consumer sẵn sàng sai

Một consumer có thể poll Redis rồi nhận danh sách rỗng vì stream chưa có event mới. Đây là kết quả bình thường nếu:

- Group và stream được cấu hình đúng.
- Redis vẫn truy cập được.
- Consumer vẫn có lịch polling.
- Không bị kẹt ở state xử lý lỗi.

Không đặt readiness DOWN chỉ vì `XREADGROUP ... >` trả empty. Hãy phân biệt **idle lành mạnh** với **worker thread đã chết**, **polling ngừng vì lỗi** và **PEL đang mắc kẹt**.

## 11. Readiness của API khác readiness của background consumer

Một process có thể vừa phục vụ HTTP vừa tiêu thụ Redis Streams. Khi đó có ít nhất hai loại “sẵn sàng”:

```text
Spring Boot process
       |
       +--> HTTP API
       |      |
       |      +-- Có thể nhận request không?
       |
       +--> Redis Streams consumer
              |
              +-- Đang poll?
              +-- Có năng lực xử lý?
              +-- PEL có được recovery?
```

Nếu worker lỗi nhưng API vẫn phục vụ request an toàn, có thể:

- Giữ HTTP readiness UP.
- Phát cảnh báo `stream_consumer_unhealthy`.
- Khôi phục worker hoặc điều phối một nhóm worker riêng.
- Tách worker khỏi API deployment khi nhu cầu scale và failure domain khác nhau.

Nếu API dùng Redis để xác thực session và Redis outage làm mọi request bảo vệ không hoạt động, việc chuyển HTTP readiness DOWN có cơ sở hơn.

**Một endpoint readiness duy nhất không phải lúc nào cũng đại diện được cho cả HTTP và tất cả background tasks.** Định nghĩa mục tiêu mỗi probe rõ ràng trước khi để Kubernetes điều phối pod.

## 12. Custom HealthIndicator cho khả năng phục vụ cụ thể

Đôi khi `PING` là quá ít, ví dụ một worker đã dừng poll nhưng Redis vẫn trả PONG. Có thể tạo custom health contributor quan sát trạng thái worker, miễn check **nhẹ và không tạo side effect**.

Ví dụ:

```java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("orderConsumer")
public class OrderConsumerHealthIndicator
        implements HealthIndicator {

    private final OrderConsumerState state;

    public OrderConsumerHealthIndicator(OrderConsumerState state) {
        this.state = state;
    }

    @Override
    public Health health() {
        if (state.isRunning()
                && state.secondsSinceLastSuccessfulPoll() < 30) {
            return Health.up().build();
        }

        return Health.down()
                .withDetail("reason", "consumer-not-polling")
                .build();
    }
}
```

`OrderConsumerState` là thành phần theo dõi trạng thái do ứng dụng định nghĩa. Khi Redis Stream lâu không có event, poll empty thành công vẫn phải cập nhật heartbeat; đừng chỉ cập nhật timestamp lúc nhận message, nếu không consumer khỏe nhưng nhàn rỗi sẽ bị báo DOWN.

Để đưa indicator vào readiness group khi thực sự cần:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,redis,orderConsumer
```

Chỉ dùng cấu hình khi cả hai contributor `redis` và `orderConsumer` thực sự có trong application context. Nếu consumer không quyết định HTTP readiness, có thể công bố một health group riêng thay vì làm mọi API pod not ready vì worker không cần thiết.

### 12.1. Tránh health check gây tải

Không nên để mỗi lần Kubernetes gọi readiness:

- Tạo và xóa consumer group.
- Scan toàn bộ PEL.
- Chạy `KEYS *` trên Redis.
- Gửi một event nghiệp vụ.
- Gọi database transaction dài.
- Thử script có side effect.
- Kiểm tra mọi slot/replica bằng hàng trăm lệnh mỗi giây.

Readiness endpoint được gọi rất thường xuyên; nếu probe tự tạo tải và timeout, nó có thể trở thành nguồn gây outage.

## 13. Kubernetes startup, readiness và liveness probes

Ví dụ Deployment cho Spring Boot có Actuator trên cổng ứng dụng 8080:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      terminationGracePeriodSeconds: 75
      containers:
        - name: app
          image: example/catalog-api:1.0
          ports:
            - containerPort: 8080

          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 5
            failureThreshold: 30

          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
            failureThreshold: 3

          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            failureThreshold: 2
```

Đây là ví dụ về cấu hình probe, không bao gồm `env`/`secretKeyRef`, resource requests/limits, Service, NetworkPolicy hoặc tài nguyên Redis cần thiết.

Ý nghĩa:

- `startupProbe` cho ứng dụng một khoảng khởi động đủ dài trước khi liveness bắt đầu kiểm tra bình thường.
- `livenessProbe` phát hiện tiến trình kẹt nghiêm trọng cần restart, không nên phụ thuộc trực tiếp vào mọi dịch vụ bên ngoài.
- `readinessProbe` quyết định pod có được đưa vào các endpoint phục vụ traffic hay không.
- `terminationGracePeriodSeconds` cho phép pod có thời gian xử lý SIGTERM và shutdown có kiểm soát trước khi bị cưỡng bức kết thúc.

Các ngưỡng trên chỉ là **giá trị minh họa**. Với ứng dụng khởi động chậm hơn, Redis TLS failover hoặc nhiều task in-flight dài, cần chọn thông số theo thời gian thực đo được.

### 13.1. Endpoints phục vụ trên management port khác?

Nếu Actuator chạy trên cổng management khác cổng HTTP chính, chỉ kiểm tra management port có thể không phát hiện trường hợp HTTP connector chính đang lỗi.

Spring Boot có cơ chế cấu hình thêm đường health probe trên cổng server chính theo phiên bản phù hợp. Hãy kiểm tra chính xác setup Actuator của dự án và xác nhận Kubernetes đang gọi đúng port/path thực tế.

Không tự giả định hai cổng có cùng trạng thái sống chỉ vì chung JVM.

### 13.2. Readiness fail không tự hủy các request cũ

Kubernetes ngừng định tuyến request **mới** tới pod không ready sau khi các endpoint và proxy cập nhật, nhưng:

- Một số request đã được chuyển đến pod vẫn đang chạy.
- Kết nối HTTP keep-alive có thể còn tồn tại.
- Có độ trễ lan truyền thay đổi endpoint.
- Traffic ngoài Kubernetes Service, ví dụ client gọi Pod IP trực tiếp, có hành vi khác.

Vì vậy, shutdown cần thêm **graceful HTTP draining**, không chỉ đánh dấu readiness DOWN.

## 14. Spring Boot graceful shutdown

Spring Boot hỗ trợ graceful shutdown cho embedded web server tương ứng. Ví dụ:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 25s
```

Khi ứng dụng được yêu cầu dừng bình thường, web server cố ngừng nhận request mới và cho các request in-flight có thời gian hoàn tất theo cơ chế của server/phase. Spring lifecycle có thể quản lý các thành phần `SmartLifecycle` theo thứ tự phase.

Những điều cần hiểu:

- `server.shutdown: graceful` hỗ trợ **HTTP web server**; nó **không tự cam kết mọi Redis Streams handler, scheduled task hoặc custom thread đã drain**.
- `timeout-per-shutdown-phase` là ngân sách cho **mỗi phase của lifecycle**, không phải một deadline duy nhất cho toàn bộ shutdown.
- Nếu có nhiều phase, thời gian tổng có thể cộng dồn; phải đặt phù hợp với `terminationGracePeriodSeconds`.
- Một request đang block vào Redis 2 phút không chắc hoàn tất trong 25 giây; timeout ở Redis client và HTTP request phải phối hợp.
- Khi hết Kubernetes grace period, container có thể bị buộc dừng; mọi tác vụ chưa xong cần cơ chế phục hồi.

### 14.1. Thứ tự dừng HTTP và Redis worker

Một chiến lược an toàn:

```text
Nhận SIGTERM
      |
      v
Readiness không nhận traffic mới
      |
      v
Graceful stop HTTP web server
      |
      v
Ngừng poll Redis/subscribe các luồng mới
      |
      v
Đợi in-flight handlers, ACK đúng event thành công
      |
      v
Dừng background listener/scheduler
      |
      v
Đóng Redis connection factory/driver resources
      |
      v
Kết thúc process
```

Tùy kiến trúc, worker cần bắt đầu draining song song với HTTP để không kéo dài thời gian shutdown. Điểm quan trọng không phải thứ tự từng millisecond mà là **không đóng Redis connection trước khi code còn cần dùng nó để hoàn tất ACK hoặc ghi kết quả**.

## 15. Spring lifecycle: @PreDestroy và SmartLifecycle khác nhau

Spring cung cấp nhiều hook:

| Cơ chế | Vai trò | Lưu ý |
|---|---|---|
| `@PostConstruct` | Khởi tạo bean sau dependency injection | Không nên làm blocking startup không giới hạn |
| `ApplicationRunner` / `CommandLineRunner` | Thực thi công việc trong quá trình Spring Boot startup | Có thể ảnh hưởng thời điểm ready |
| `ApplicationReadyEvent` | Sự kiện giai đoạn ứng dụng sẵn sàng | Không nên mặc định dùng cho việc bắt buộc phải hoàn tất trước ready |
| `AvailabilityChangeEvent` | Phát/cập nhật trạng thái availability | Dùng đúng trạng thái trong quy trình |
| `ContextClosedEvent` | Thông báo context đang đóng | Có thể đánh dấu draining hoặc phát tín hiệu dừng |
| `@PreDestroy` | Cleanup bean trước khi destroy | Không tự quản lý thứ tự drain mọi dependency |
| `SmartLifecycle` | Start/stop theo phase, có callback stop bất đồng bộ | Hữu ích khi có background worker cần drain |
| Container SIGTERM | Tín hiệu kết thúc process | Phải được chuyển tới JVM, không bị wrapper shell nuốt |

### 15.1. @PreDestroy phù hợp với việc gì?

Ví dụ một tài nguyên **do bean tự tạo và tự sở hữu**:

```java
import jakarta.annotation.PreDestroy;
import java.util.concurrent.ExecutorService;

public class LocalRefreshWorker {

    private final ExecutorService executor;

    public LocalRefreshWorker(ExecutorService executor) {
        this.executor = executor;
    }

    @PreDestroy
    public void requestStop() {
        executor.shutdown(); // Ngừng nhận task mới.
    }
}
```

Đây chỉ là bước **yêu cầu dừng**, chưa chứng minh mọi task kết thúc. Nếu tài nguyên là Spring-managed shared bean, trách nhiệm đóng tài nguyên phải được phân định rõ để tránh một component dừng executor mà component khác còn dùng.

**Không gọi `lettuceConnectionFactory.destroy()` tùy tiện trong `@PreDestroy` của một service** chỉ vì muốn “đóng Redis sớm”. Spring thường quản lý lifecycle của connection factory; đóng sớm có thể làm những service/listener khác mất kết nối khi đang hoàn tất công việc.

### 15.2. Khi nào cần SmartLifecycle?

Nếu một bean chủ động tạo thread polling Redis hoặc lắng nghe message nền, có thể dùng `SmartLifecycle` để:

- Khởi động khi application context sẵn sàng theo lifecycle.
- Dừng **nhận công việc mới** ngay khi context shutdown.
- Chờ in-flight tới một deadline.
- Gọi callback khi dừng xong để Spring tiếp tục phase.
- Bảo đảm Redis connection factory còn tồn tại tới khi worker không còn cần nó, thông qua ordering đã được xác minh.

**Không giả định mọi Redis listener container có cùng phase và hành vi stop**. Kiểm tra lifecycle contract của phiên bản Spring Data Redis thực tế.

## 16. Ví dụ SmartLifecycle cho một Redis Streams worker

Ví dụ sau minh họa một worker đồng bộ, quản lý đúng một thread poll Redis Streams. Consumer group đã được tạo trước bằng quy trình idempotent. Worker chỉ `XACK` sau khi handler hoàn tất thành công.

```java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.SmartLifecycle;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderStreamWorker implements SmartLifecycle {

    private static final Logger log =
            LoggerFactory.getLogger(OrderStreamWorker.class);

    private static final String STREAM = "stream:orders:v1";
    private static final String GROUP = "order-workers";
    private static final String CONSUMER = "order-worker-a";

    private final StringRedisTemplate redis;
    private final OrderEventHandler handler;

    private final AtomicBoolean acceptingWork =
            new AtomicBoolean(false);
    private final AtomicBoolean started =
            new AtomicBoolean(false);

    private final ExecutorService worker =
            Executors.newSingleThreadExecutor(r -> {
                Thread thread = new Thread(r, "redis-order-consumer");
                thread.setDaemon(false);
                return thread;
            });

    public OrderStreamWorker(
            StringRedisTemplate redis,
            OrderEventHandler handler) {
        this.redis = redis;
        this.handler = handler;
    }

    @Override
    public void start() {
        if (started.compareAndSet(false, true)) {
            acceptingWork.set(true);
            worker.execute(this::pollLoop);
        }
    }

    private void pollLoop() {
        while (acceptingWork.get()) {
            try {
                List<MapRecord<String, Object, Object>> records =
                        redis.opsForStream().read(
                                Consumer.from(GROUP, CONSUMER),
                                StreamReadOptions.empty()
                                        .count(10)
                                        .block(Duration.ofMillis(200)),
                                StreamOffset.create(
                                        STREAM,
                                        ReadOffset.lastConsumed()));

                if (records == null || records.isEmpty()) {
                    continue;
                }

                // Những entry trong batch đã được Redis giao,
                // vì vậy nếu dừng giữa batch cần recovery PEL.
                for (MapRecord<String, Object, Object> record : records) {
                    if (Thread.currentThread().isInterrupted()) {
                        return;
                    }

                    handler.handle(record.getValue());

                    // ACK chỉ sau khi side effect nghiệp vụ đã xong.
                    redis.opsForStream().acknowledge(
                            STREAM, GROUP, record.getId());
                }
            } catch (RuntimeException error) {
                log.warn("Redis Streams poll/handler failed", error);

                if (!acceptingWork.get()) {
                    return;
                }

                try {
                    Thread.sleep(250);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }
    }

    @Override
    public void stop(Runnable callback) {
        acceptingWork.set(false);
        worker.shutdown();

        Thread waiter = new Thread(() -> {
            try {
                boolean terminated =
                        worker.awaitTermination(
                                20, TimeUnit.SECONDS);

                if (!terminated) {
                    log.warn("Worker drain deadline exceeded");
                    worker.shutdownNow();
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                worker.shutdownNow();
            } finally {
                started.set(false);
                callback.run();
            }
        }, "redis-order-consumer-shutdown");

        waiter.setDaemon(true);
        waiter.start();
    }

    @Override
    public void stop() {
        acceptingWork.set(false);
        worker.shutdown();
    }

    @Override
    public boolean isRunning() {
        return started.get() && acceptingWork.get();
    }

    @Override
    public int getPhase() {
        return 10_000;
    }
}
```

Handler nghiệp vụ là interface của ứng dụng:

```java
import java.util.Map;

public interface OrderEventHandler {
    // Chỉ trả về khi side effect cần thiết đã commit.
    // Ném exception nếu không thể xác nhận thành công.
    void handle(Map<Object, Object> event);
}
```

### 16.1. Ý nghĩa của ví dụ

- `start()` khởi động poll loop đúng một lần trong vòng đời context.
- `acceptingWork=false` khiến loop không bắt đầu lần poll tiếp theo sau khi hoàn thành batch hiện tại.
- `block(200ms)` giữ lần poll có deadline tương đối ngắn để phản ứng với shutdown.
- `stop(Runnable)` trả quyền kiểm soát cho Spring và gọi callback sau quá trình đợi dừng có giới hạn.
- Handler được chạy trước `XACK`.
- Khi handler lỗi hoặc bị ngắt trước ACK, entry phải được phục hồi từ PEL.
- `getPhase()` là giá trị minh họa: phase lớn hơn được dừng trước phase nhỏ hơn. Cần xác minh phase của connection factory và những listener khác trong ứng dụng.
- Một tên consumer cố định không phù hợp nếu có nhiều instance cùng sử dụng tên đó mà không có quy tắc ownership. Production nên sinh consumer identity ổn định theo instance/slot hoặc dùng chiến lược quản lý consumer rõ ràng.
- Ví dụ giả định **một lần startup cho một context**; executor đã shutdown không thể dùng lại cho lifecycle restart trong cùng bean. Nếu cần start/stop/restart nhiều lần, phải thiết kế lại việc tạo executor và đồng bộ trạng thái.

### 16.2. Giới hạn của demo

Đây là một mẫu minh họa lifecycle, không phải framework Redis Streams production đầy đủ:

- Chưa có pending recovery `XCLAIM`/`XAUTOCLAIM`.
- Chưa có poison-message retry/DLQ.
- Chưa có business idempotency.
- Chưa có backpressure nhiều worker song song.
- Chưa có điều phối primary/replica hay Spring Security.
- `worker.shutdownNow()` chỉ gửi interrupt; nếu handler bỏ qua interrupt hoặc đang block I/O, task có thể chưa thực sự kết thúc.
- Callback sau deadline không có nghĩa mọi side effect chắc chắn hoàn tất; phải dựa vào commit/ACK/PEL để biết trạng thái.
- Logic dừng khi gặp exception và backoff cần điều chỉnh theo yêu cầu availability.

Trong production, cần đo thời gian xử lý tối đa, chọn deadline, và **thiết kế để những entry chưa ACK vẫn có thể recover sau khi process bị cưỡng bức kết thúc**.

## 17. Dừng poll không giống ACK mọi message đã nhận

Redis Streams consumer group giữ **Pending Entries List** cho entry đã giao nhưng chưa ACK:

```text
XREADGROUP nhận e1, e2, e3
          |
          v
PEL = {e1, e2, e3}
          |
          v
Handler e1 commit -> XACK e1
          |
          v
SIGTERM nhận trong lúc xử lý e2
          |
          +-- e2 chưa commit: KHÔNG ACK
          |
          +-- e3 đã giao nhưng chưa xử lý: KHÔNG ACK
          |
          v
Shutdown
          |
          v
Worker sau khởi động recover e2, e3 từ PEL
```

Lưu ý hai trường hợp:

1. **Dừng trước khi poll:** message mới còn trong stream, chưa được phân phối.
2. **Dừng sau khi đã nhận batch:** message chưa ACK có thể nằm trong PEL, không được tự giao lại khi chỉ đọc `XREADGROUP ... >`.

Một worker sau restart cần xử lý cả **new messages** và **pending recovery** theo quy trình phù hợp; không chỉ tạo subscription mới rồi giả định tất cả công việc đã tự trở lại.

### 17.1. Recovery pending

Các lệnh Redis có thể dùng:

```bash
redis-cli XPENDING stream:orders:v1 order-workers

redis-cli XAUTOCLAIM stream:orders:v1 \
  order-workers order-worker-b 60000 0-0 COUNT 100
```

`60000` là min idle threshold tính bằng milliseconds, chỉ là ví dụ. Một consumer mới không nên claim quá sớm khi worker cũ vẫn đang drain hợp lệ.

`XAUTOCLAIM` có cursor nên cần quét nhiều vòng nếu pending lớn. Claim không tự ACK; worker mới phải xử lý event và xác nhận sau thành công.

### 17.2. Crash sau DB commit nhưng trước ACK

```text
Worker A:
    DB commit ORDER_PAID thành công
    JVM chết trước XACK

Worker B:
    reclaim event
    handler chạy lại
```

Do đó, event cần `eventId`/version để handler **idempotent**. Redis consumer group giúp phục hồi trách nhiệm xử lý, không tự bảo đảm side effect nghiệp vụ đúng một lần.

## 18. Redis Pub/Sub listener: giới hạn trong giai đoạn shutdown

Đối với Redis Pub/Sub, nhiều ứng dụng dùng `RedisMessageListenerContainer`. Khác Redis Streams consumer group, Pub/Sub thông thường **không có PEL/ACK hay replay bền** cho những message phát trong lúc subscriber offline.

Nếu process shutdown:

```text
Publisher gửi event A
          |
          v
Listener đang kết nối -> có thể nhận A

Listener đã stop hoặc mất kết nối
          |
          v
Publisher gửi event B
          |
          v
Subscriber đó có thể bỏ lỡ B
```

Điều này quan trọng nếu Pub/Sub được dùng cho:

- Local cache invalidation.
- Notifications chỉ cần best effort.
- Broadcast lệnh làm mới trạng thái.
- Các tác vụ không có yêu cầu replay.

**Không dùng Pub/Sub như hàng đợi bền** cho payment, audit, idempotency hoặc nghiệp vụ bắt buộc xử lý. Nếu message không được phép mất khi deploy, cần Redis Streams, hàng đợi có ACK hoặc hệ thống sự kiện bền phù hợp.

### 18.1. Dừng listener container

Với listener do Spring quản lý:

- Để Spring điều phối lifecycle của container.
- Nếu cần, gọi stop theo contract của container trước khi tài nguyên Redis được giải phóng.
- Không tiếp tục nhận callback mới sau khi service đã chuyển sang trạng thái không nhận công việc.
- Cập nhật local state bằng dữ liệu an toàn; không phụ thuộc một notification cuối cùng chắc chắn sẽ tới.
- Khi khởi động lại, có TTL/version/reconciliation cho những invalidation có thể bỏ lỡ.

Không có một thứ tự dừng listener mặc định bảo đảm mọi Pub/Sub message gửi trước SIGTERM sẽ được xử lý. Phải định nghĩa chính sách dữ liệu thiếu và đồng bộ lại sau reconnect.

## 19. ReactiveRedisTemplate: subscription và cancellation khi dừng

Ở ứng dụng WebFlux, Spring Data Redis reactive trả `Mono`/`Flux`. Quá trình shutdown cần phân biệt:

- **Ngừng tạo subscription mới** cho các tác vụ định kỳ.
- **Cancel** subscription đang tiêu thụ vô hạn theo chính sách.
- **Đợi các async handler đang xử lý** hoàn tất trong giới hạn.
- **Không xem cancellation là rollback** một command Redis đã gửi.
- **Không ACK** Redis Stream trước khi handler reactive báo hoàn tất thành công.

Một mẫu reactive stream theo ý tưởng:

```java
receiver.receive(
        Consumer.from(group, consumerName),
        StreamOffset.create(
                stream, ReadOffset.lastConsumed()))
    .concatMap(record ->
        handleBusiness(record)
            .then(ackAfterCommit(record)));
```

Trong đó `handleBusiness` và `ackAfterCommit` là các publisher do ứng dụng định nghĩa.

Nếu dùng `flatMap` với concurrency cao mà không giới hạn, khi shutdown có thể còn rất nhiều handler đang chạy. Nên giới hạn in-flight và chọn timeout để có thể drain.

### 19.1. Cancellation không xóa tác dụng đã thực thi

Giả sử:

```text
T0: Reactive subscription gửi EVAL script tới Redis.
T1: Process nhận SIGTERM, subscription bị cancel.
T2: Redis vẫn có thể đang thực thi và hoàn tất script.
T3: Client không nhận được kết quả.
```

Không được suy luận từ cancellation rằng script chưa thay đổi dữ liệu. Với `INCR`, Lua script, đặt chỗ hoặc ghi nhiều bước, timeout/cancel có thể tạo **unknown outcome**. Mọi retry sau restart cần dựa trên idempotency/đối soát.

### 19.2. Không block event loop để drain

Không gọi `.block()` dài trên Reactor Netty event loop chỉ để đợi Redis hoàn tất. Thay vào đó, dùng lifecycle callback và async coordination phù hợp; nếu buộc dùng blocking adapter, cách ly trên scheduler/thread thích hợp và đặt deadline.

## 20. Connection pooling và giải phóng tài nguyên

Spring Data Redis dùng connection factory và driver để quản lý kết nối Redis. Với Lettuce, tài nguyên có thể bao gồm:

- Netty event loops.
- Redis client/cluster client.
- Kết nối vật lý đến Redis nodes.
- Connection pool nếu được bật cho use case nhất định.
- Pub/Sub connection và subscriptions.
- Topology discovery/reconnect tasks.
- Timeouts, pending command buffers và metrics.

Nguyên tắc **ownership**:

| Tài nguyên | Ai nên sở hữu lifecycle? |
|---|---|
| `LettuceConnectionFactory` bean do Spring tạo | Spring context / cấu hình infrastructure |
| `RedisTemplate`/`StringRedisTemplate` | Spring bean sử dụng connection factory |
| `RedisMessageListenerContainer` bean | Spring lifecycle hoặc component quản lý rõ ràng |
| `StreamMessageListenerContainer` bean | Spring lifecycle và worker orchestration |
| Executor do service tự tạo | Service phải dừng và giải phóng |
| Native Lettuce client tạo thủ công | Thành phần tạo nó phải đóng đúng contract |
| Redis connection lấy thủ công từ factory | Caller giải phóng theo API, thường `close()` |
| Reactive subscription/`Disposable` do service tạo | Service phải quản lý cancellation/cleanup |

### 20.1. Không đóng connection factory sau mỗi request

Sai về vòng đời:

```java
public String readAndClose(String key) {
    String value = redis.opsForValue().get(key);
    lettuceConnectionFactory.destroy(); // Không làm ở đây.
    return value;
}
```

Connection factory là shared infrastructure. Đóng nó giữa lúc ứng dụng đang chạy có thể làm tất cả lệnh Redis của request khác, cache manager, stream listener và session service thất bại.

### 20.2. Đóng low-level RedisConnection khi tự lấy

Nếu một công cụ vận hành cần connection thấp:

```java
import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.connection.RedisConnectionFactory;

public String pingRedis(RedisConnectionFactory factory) {
    try (RedisConnection connection = factory.getConnection()) {
        return connection.ping();
    }
}
```

Lưu ý việc `close()` trên abstraction có thể trả connection về pool hoặc giải phóng wrapper tùy implementation; không tự suy luận luôn đóng socket vật lý.

Với RedisTemplate, thường không cần lấy/đóng connection thấp thủ công: template và connection factory quản lý vòng đời của thao tác.

### 20.3. Shared connection của Lettuce

Lettuce có các cơ chế chia sẻ connection tùy kiểu command và cách factory được cấu hình. Không tự đóng native connection được dùng chung bên trong driver khi nó không do service sở hữu.

Nếu dùng native Lettuce client trực tiếp bên ngoài Spring, cần quản lý lifecycle qua API driver tương ứng và đảm bảo đóng **sau khi** các tác vụ sử dụng nó đã hoàn tất.

## 21. Thứ tự shutdown khi có nhiều loại workload

Một ứng dụng thực tế có thể đồng thời có:

- HTTP request phục vụ cache.
- Scheduled job làm ấm dữ liệu.
- Redis Pub/Sub listener để invalidation.
- Redis Streams consumer ghi database.
- Spring Session lưu phiên đăng nhập.
- Metrics/health endpoints.
- Một executor dùng để refresh cache background.

Nếu dừng sai thứ tự:

```text
SIGTERM
    |
    v
Đóng Redis connection factory ngay
    |
    v
Stream handler đang commit xong nhưng không XACK được
Cache refresh tasks lỗi
Session request chưa hoàn tất lỗi khi lưu
Listener ném exception
```

Một chiến lược có kiểm soát:

1. Phát tín hiệu ứng dụng **không nhận traffic mới**.
2. Để HTTP web server drain request đang xử lý.
3. Ngừng scheduler và consumer nhận thêm task.
4. Chờ tác vụ in-flight trong giới hạn.
5. Chỉ ACK/commit những kết quả thực sự hoàn tất.
6. Dừng Redis listener containers và subscriptions.
7. Đóng resource do application tự tạo.
8. Để Spring đóng connection factory khi các dependent beans đã dừng.
9. Ghi metric/log kết thúc **không chứa secret**, nêu số pending/in-flight còn lại.
10. Kết thúc process trong container grace period.

Thứ tự thực tế phải được xác minh theo phase và dependency graph của ứng dụng; một hệ thống có thể dừng HTTP và background song song để tiết kiệm thời gian. Nhưng **không để Redis shutdown cắt ngang những handler vẫn còn được hứa sẽ ACK**.

## 22. Rolling deployment: không để mọi replica unavailable cùng lúc

Trong Kubernetes, một rollout có thể diễn ra:

```text
Version v1: App A, App B, App C (ready)
              |
              v
Kubernetes tạo App D (v2)
              |
              v
App D startup -> readiness UP
              |
              v
Kubernetes cho App A (v1) dừng
              |
              v
App A graceful drain và kết thúc
              |
              v
Tiếp tục thay B/C
```

Để giảm downtime:

- Cấu hình RollingUpdate với `maxUnavailable` phù hợp.
- Chỉ đưa pod mới vào Service sau khi readiness UP.
- Đảm bảo startup probe đủ thời gian cho warm-up bắt buộc.
- Có `terminationGracePeriodSeconds` đủ cho request/worker drain.
- Chú ý giới hạn tài nguyên khi `maxSurge` tạo thêm pod.
- Không để mọi instance cùng chạy migration Redis không idempotent.
- Với Streams, mỗi worker cần consumer name/ownership phù hợp; worker cũ pending được recovery sau ngưỡng idle.
- Với cache/session serializer, v1 và v2 có thể cùng truy cập Redis trong một giai đoạn; cần compatibility và migration plan.

### 22.1. SIGTERM phải tới JVM

Một Dockerfile hoặc entrypoint shell có thể làm SIGTERM không được chuyển đúng tới Java process nếu không sử dụng cơ chế PID 1/`exec` phù hợp. Khi đó Kubernetes phải chờ timeout rồi gửi SIGKILL, khiến graceful shutdown không chạy.

Ví dụ một entrypoint shell thông thường:

```sh
#!/bin/sh
exec java -jar /app/app.jar
```

`exec` thay shell bằng JVM, giúp tiến trình Java nhận signal theo cách container runtime điều phối.

Với Java process chạy trực tiếp bằng dạng Dockerfile exec:

```dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

JVM cũng có thể làm PID 1. Việc xử lý signal còn phụ thuộc entrypoint, init process, orchestrator và chính sách hệ điều hành; phải **thử SIGTERM thật trong môi trường test** chứ không chỉ đọc Dockerfile.

## 23. PreStop và terminationGracePeriodSeconds

Kubernetes có thể gọi `preStop` hook trước khi kết thúc container. Một số đội dùng hook để báo instance draining hoặc chờ endpoint propagation.

Nhưng cần nhớ:

- Thời gian `preStop` **cũng tính trong** container termination grace period.
- `sleep` đơn thuần không đảm bảo handler, transaction hay Redis ACK hoàn tất.
- Nếu preStop bị kẹt, phần thời gian dành cho JVM nhận SIGTERM và shutdown sẽ giảm.
- Một hook gọi endpoint nội bộ nên có deadline và authentication/policy phù hợp.
- Đừng dựa hoàn toàn vào readiness DOWN mà quên các kết nối request đang tồn tại.

Ví dụ ngân sách minh họa:

```text
Container termination grace: 75 giây

Endpoint propagation / preStop: 5 giây
Web request graceful drain: 20 giây
Redis stream worker drain: 20 giây
Resource cleanup & margin: 10 giây
Tổng dự kiến: 55 giây
Headroom: 20 giây
```

Đây là phương án lập ngân sách, không phải Redis/Spring/Kubernetes default. Nếu các phase shutdown chạy tuần tự hoặc một handler chờ timeout dài, phải tính **thời gian tổng thực tế**. Nên đo worst-case trong load test và rolling deploy.

## 24. Không đồng nhất Redis unavailable với application dead

Redis có thể lỗi trong lúc ứng dụng đang phục vụ:

```text
Redis primary failover
        |
        v
Một số lệnh timeout/reconnect
        |
        v
Lettuce cập nhật kết nối/topology
        |
        v
Redis hoạt động lại
```

Ở thời điểm lỗi:

- **Liveness** của app có thể vẫn UP nếu process còn hoạt động.
- **Readiness** có thể DOWN nếu Redis là dependency bắt buộc, rồi trở lại UP sau khi phục hồi.
- Cache-only request có thể dùng fallback giới hạn.
- Session-based auth có thể phải fail closed.
- Stream consumer không được ACK message khi handler chưa thành công.
- Một lệnh ghi có side effect có thể có outcome không xác định nếu client timeout sau khi Redis đã thực thi.

### 24.1. Connection restored không đồng nghĩa công việc đã được phục hồi

Khi driver reconnect thành công:

- Pub/Sub cần subscription được tái thiết lập theo container/driver và vẫn có thể mất message trong outage.
- Redis Streams cần đọc message mới **và** recovery pending cũ.
- Một distributed lock lease có thể đã hết hạn; không được tiếp tục coi mình là lock owner chỉ vì reconnect.
- Một batch write timeout có thể đã áp dụng một phần; cần đối soát.
- Replica read có thể tạm stale sau failover.

**Readiness UP sau reconnect không chứng minh các side effect còn thiếu đã được hoàn tất.** Business recovery và infrastructure connectivity là hai trách nhiệm khác nhau.

## 25. Session Redis: shutdown ảnh hưởng người dùng thế nào?

Spring Session Data Redis có thể lưu `HttpSession` vào Redis. Khi rolling deployment:

- Request đang phục vụ cần thời gian hoàn tất và lưu session state theo chế độ Spring Session.
- Một pod mới phải dùng cùng session namespace/serializer/schema tương thích.
- Cookie của browser vẫn trỏ tới session ID lưu trong Redis.
- Redis failure có thể làm không xác nhận được session hiện hành.
- Không được cho phép request bảo vệ chỉ vì đọc session lỗi.

Một deployment có Redis shared session store có thể tránh mất phiên khi một pod bị thay, nhưng không tự bảo đảm mọi request in-flight hoàn tất. Nếu JVM bị SIGKILL ngay trong lúc lưu session hoặc Redis outage, phần cập nhật session có thể chưa persist.

Cần thử với nhiều replica: login qua v1, chuyển sang v2, logout/revoke, timeout và Redis failover. Không để session schema/serialization đổi không tương thích trong rolling deploy.

### 25.1. Đừng xóa toàn bộ session khi instance dừng

Session thuộc repository dùng chung, **không thuộc vòng đời của một app instance**. Nếu App A shutdown, nó không nên gọi `DEL spring:session:*` hoặc xóa mọi session chỉ vì không còn phục vụ request.

Thao tác xóa session phải xuất phát từ logout, timeout, revocation hoặc quản trị có chủ đích, không phải từ việc thay container.

## 26. Health check qua nhiều node Redis Cluster

Trong Redis Cluster, key được chia trên hash slot:

```text
Client
  |
  v
Lettuce Cluster
  |
  +--> Primary A: slot group A
  +--> Primary B: slot group B
  +--> Primary C: slot group C
```

Một health check chỉ ping một seed node có thể UP khi:

- Primary B không truy cập được.
- Client không theo được `MOVED`/`ASK` sau reshard.
- TLS certificate của một node khác sai hostname.
- Một nhóm slot bị lỗi.
- Replica lag quá giới hạn cho đường đọc từ replica.

Nhưng readiness probe **gọi tất cả primary trên mỗi lần kiểm tra** cũng có thể tạo tải không cần thiết và trở thành nguyên nhân tăng latency.

Một cách cân bằng:

1. Basic health ở Actuator với timeout ngắn.
2. Redis Cluster metrics riêng: cluster state, slot coverage, unavailable nodes, redirect/reconnect failures.
3. Synthetic check nhẹ theo một vài slot đại diện ở tần suất thấp.
4. Alert khi unavailable slot/shard hoặc command timeout tăng.
5. Chọn readiness policy theo năng lực nghiệp vụ: một số endpoint có thể degraded trong khi các endpoint khác vẫn hoạt động.

Với Sentinel, health cần quan tâm cả khả năng tìm primary mới và kết nối đến địa chỉ được quảng bá. PING thành công tới Sentinel **không đồng nghĩa** client đã kết nối tới Redis primary phục vụ data commands.

## 27. Đóng kết nối trong Redis Cluster/Sentinel

Khi app shutdown, Lettuce có thể đang duy trì kết nối tới nhiều node và topology/reconnect tasks. Những nguyên tắc vẫn giống Standalone nhưng cần chú ý:

- Không tự đóng một native connection đang được connection factory dùng chung.
- Dừng background stream/pipeline jobs trước khi driver resources bị giải phóng.
- Nếu có lệnh đang chờ response tại thời điểm shutdown, xác định chính sách timeout/unknown outcome.
- Dừng reconnect tasks khi ứng dụng thật sự kết thúc, không để thread của native client tự tạo giữ JVM sống ngoài ý muốn.
- Mọi node/replica cùng thuộc topology cần được giải phóng qua driver lifecycle, không chỉ seed connection.
- Không để health probe hoặc scheduled job tạo kết nối mới sau khi bắt đầu draining.

Nếu Spring Boot quản lý `LettuceConnectionFactory`, thông thường để lifecycle/destruction của Spring xử lý. Nếu ứng dụng tạo client riêng thủ công, component đó phải có cleanup riêng và đúng thứ tự.

## 28. Lỗi khi đóng ứng dụng và rủi ro mất dữ liệu

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Đóng Redis connection ngay khi SIGTERM | Handler chưa kịp ACK/persist | Drain worker trước cleanup connection |
| ACK toàn bộ batch khi dừng | Message chưa xử lý bị coi đã xong | ACK từng event sau business success |
| Chỉ đọc `>` khi restart | Bỏ quên PEL của worker cũ | Startup recovery pending |
| Chờ blocking read vô hạn | Shutdown không kết thúc kịp | Bounded BLOCK/interrupt/lifecycle |
| Liveness phụ thuộc trực tiếp Redis | Redis outage gây pod restart storm | Tách process liveness khỏi dependency |
| Readiness không kiểm Redis dù Redis bắt buộc | Pod nhận request rồi lỗi liên tục | Cân nhắc readiness contributor phù hợp |
| Redis cache tùy chọn làm mọi pod not ready | Không còn HTTP endpoints dù có fallback | Định nghĩa dependency theo nghiệp vụ |
| Dùng `PING` như kiểm thử toàn Cluster | Bỏ sót lỗi slot/ACL/business | Metrics, synthetic tests phù hợp |
| Startup fail mãi khi Redis đang failover ngắn | Restart loop/cold-start storm | Retry có giới hạn và readiness policy |
| Warm cache hàng triệu key trước khi ready | Rollout chậm, tăng tải database | Warm-up bounded/async |
| Pub/Sub listener dừng và giả định không mất event | Bỏ lỡ invalidation | TTL/version/reconciliation |
| Cancel reactive publisher và coi command rollback | Side effect có thể đã thực thi | Idempotency/unknown outcome |
| Dùng `@PreDestroy` đóng factory chung | Các bean khác mất Redis sớm | Để Spring quản lý factory |
| Không truyền SIGTERM tới JVM | Bị SIGKILL, cleanup không chạy | Entrypoint đúng, test termination |
| Grace period ngắn hơn handler timeout | Bị kill trước khi drain | Đặt deadline đồng bộ, recovery |
| Mọi replica khởi tạo group bằng xóa/tạo lại | Mất pending state | Tạo idempotent, giữ group bền |
| Session schema đổi không tương thích | Người dùng mất phiên trong rollout | Serialization/version migration |
| Health endpoint chạy write/scan nặng | Probe tự làm Redis quá tải | Probe nhẹ, kiểm thử synthetic riêng |
| Retry lệnh ghi sau timeout vô điều kiện | Side effect bị áp dụng trùng | Operation ID/idempotent handler |

## 29. Kiểm thử vòng đời khởi động và shutdown

Không nên chỉ kiểm tra “chạy ứng dụng và thấy log Started”. Cần xác minh từng hành vi ở mức hệ thống.

### 29.1. Startup tests

| Kịch bản | Điều cần xác nhận |
|---|---|
| Redis đang hoạt động | Readiness UP theo chính sách, command thật chạy được |
| Redis chưa lên | App fail fast hoặc không ready/degraded theo thiết kế |
| DNS Redis sai | Timeout hữu hạn, lỗi chẩn đoán được |
| TLS certificate không hợp lệ | Không bỏ qua certificate validation |
| Redis ACL user thiếu quyền | Không nhầm thành cache miss |
| Redis Cluster thiếu một slot | Health/metrics phát hiện vấn đề theo SLO |
| Consumer group đã tồn tại | Startup idempotent, không reset group |
| Redis Stream rỗng | Consumer idle lành mạnh, không false DOWN |
| Cache cold start | Latency/QPS không vượt ngân sách warm-up |
| Nhiều pod khởi động cùng lúc | Không tạo connection storm/migration race |

### 29.2. Readiness/liveness tests

- Redis outage ngắn không được gây vô hạn restart app vì liveness sai.
- Readiness DOWN khi dependency thật sự bắt buộc và unavailable.
- Readiness UP khi dependency phục hồi và process có thể tiếp tục xử lý.
- Nếu Redis chỉ là cache tùy chọn, fallback vẫn hoạt động trong giới hạn.
- Health checks không mở dữ liệu nhạy cảm ra Internet.
- Probe timeout không khiến Redis hoặc database chịu thêm tải quá lớn.
- App không bị nhận traffic trước khi các bước startup bắt buộc kết thúc.

### 29.3. Graceful shutdown tests

1. Khởi chạy nhiều API replicas và một worker xử lý Redis Streams.
2. Phát request HTTP dài hoặc tạo batch event.
3. Gửi SIGTERM tới một instance.
4. Quan sát readiness chuyển sang không nhận traffic mới.
5. Xác nhận request đã được tiếp nhận có cơ hội hoàn tất trong grace period.
6. Xác nhận worker ngừng nhận batch Redis mới.
7. Xác nhận event hoàn tất được ACK; event chưa hoàn tất vẫn pending.
8. Khởi động worker khác và claim/recover event pending.
9. Xác nhận business side effect không bị nhân đôi.
10. Xác nhận JVM/process kết thúc đúng deadline, không còn thread/connection rò rỉ.
11. Lặp lại với Redis failover đúng lúc shutdown.
12. Đo thực tế tổng thời gian và điều chỉnh grace period.

Không nhất thiết phải biến tất cả thành một integration test khổng lồ. Có thể tách test startup, HTTP drain, Redis worker stop, PEL recovery và failover để dễ chẩn đoán.

## 30. Ví dụ chuỗi triển khai có kiểm soát

Một rollout điển hình cho ứng dụng gồm API + Redis Streams worker:

```text
T0: App v1 phục vụ HTTP; consumer v1 đang xử lý.

T1: Kubernetes tạo App v2.
    App v2 tạo Spring context, Lettuce factory.
    Startup check kiểm Redis cần thiết.
    Consumer v2 được tạo group/identity phù hợp.

T2: App v2 vượt readiness.
    Kubernetes đưa v2 vào Service.

T3: App v1 nhận SIGTERM.
    Liveness vẫn mô tả process còn hoạt động;
    readiness từ chối traffic mới.

T4: Web server v1 drain request trong deadline.
    Redis Streams consumer v1 ngừng poll batch mới.
    Handler đã commit ACK event tương ứng.

T5: Nếu một event chưa hoàn tất:
    không ACK.
    Redis PEL giữ pending nếu payload còn.

T6: Worker v2 sau ngưỡng idle/ownership thích hợp
    claim pending và xử lý idempotent.

T7: App v1 stop listeners/executors,
    Spring đóng Lettuce factory.
    Process kết thúc trong grace period.

T8: Theo dõi Redis connection count,
    pending age, business success, HTTP p99.
```

Các bước không nhất thiết diễn ra tuần tự tuyệt đối trên mọi framework. Đây là **hợp đồng hành vi mong muốn** để thiết kế lifecycle/phase, không phải mô tả rằng Spring Boot tự thực hiện mọi bước Redis Streams.

## 31. Checklist trước khi lên production

**Cấu hình kết nối**

- Redis endpoint nằm trong mạng được phép, TLS/ACL hoạt động.
- Redis client timeouts rõ ràng.
- Lettuce topology/discovery phù hợp Standalone, Sentinel hoặc Cluster.
- Không hardcode secret; certificate và credential có phương án rotation.

**Khởi động**

- Biết Redis là dependency bắt buộc hay cache tùy chọn.
- Startup deadline/ retry có giới hạn.
- Không thực hiện migration nguy hiểm trên mỗi pod startup.
- Consumer group tạo idempotent; pending recovery có quy trình.
- Không chặn readiness vì warm-up không cần thiết.

**Health/readiness**

- Startup, liveness và readiness có mục đích riêng.
- Liveness không gắn Redis outage thoáng qua theo cách gây restart storm.
- Readiness phản ánh khả năng nhận request mới.
- Custom health contributor nhẹ, không có side effect.
- Redis Cluster metrics không chỉ dựa vào PING một seed node.
- Probe port/path đúng với cấu hình Actuator.

**Shutdown**

- SIGTERM thực sự tới JVM.
- `server.shutdown: graceful` và Spring lifecycle timeout được thiết lập phù hợp.
- Kubernetes termination grace period đủ cho các phase cần thiết.
- HTTP và background work không nhận thêm tải sau khi draining.
- ACK Redis Streams sau commit, không ACK sớm.
- Event pending còn khả năng phục hồi.
- Pub/Sub có cơ chế chịu việc bỏ lỡ notification.
- Reactive cancellation không bị hiểu sai là rollback.
- Connection factory được đóng sau consumer/handler phụ thuộc.

**Kiểm thử và quan sát**

- Đã thử Redis outage, failover, rolling deploy và SIGTERM dưới tải.
- Theo dõi p95/p99 HTTP, Redis command timeout, reconnect, pending count/age.
- Không log password/session ID/token.
- Có cảnh báo stuck worker, PEL quá lâu, readiness flapping, memory/connection tăng.
- Có quy trình rollback khi v2 không đọc được cache/session schema của v1.

## 32. Tổng kết

**Khởi động, kiểm tra sẵn sàng và đóng kết nối có kiểm soát** trong Spring Data Redis là việc quản lý cả **trạng thái ứng dụng** lẫn **trạng thái công việc**, không chỉ tạo connection factory và gọi `PING`.

Các nguyên tắc cần ghi nhớ:

1. **Bean đã tạo không đồng nghĩa Redis sẵn sàng.** Kiểm tra quyền, mạng, TLS, topology và thao tác thật khi cần.
2. **Liveness không phải readiness.** Redis outage có thể khiến ứng dụng không phục vụ được request mới nhưng tiến trình vẫn còn khả năng tự phục hồi.
3. **Readiness phụ thuộc vai trò Redis.** Một cache tùy chọn khác với kho session hoặc Redis stream bắt buộc.
4. **Graceful shutdown phải bao gồm background workers.** Dừng poll/subscription, drain in-flight và ACK sau side effect thành công.
5. **Đóng connection đúng ownership và đúng thứ tự.** Để Spring quản lý `LettuceConnectionFactory`; không tự đóng factory dùng chung khi handler còn làm việc.
6. **Redis Streams cần pending recovery và idempotency.** Redis reconnect hoặc process restart không tự đảm bảo mọi event đã được xử lý.
7. **Pub/Sub không có replay bền.** Listener dừng có thể bỏ lỡ message; invalidation cần TTL/version hoặc reconciliation.
8. **Timeout/cancellation có thể tạo kết quả không chắc chắn.** Một lệnh có side effect có thể đã chạy dù client không nhận response.
9. **Kubernetes probes, grace period và Spring lifecycle phải phối hợp.** Không để pod bị SIGKILL trước thời hạn drain đã cam kết.
10. **Kiểm thử vòng đời như một luồng nghiệp vụ.** Startup, dependency outage, readiness, rolling deploy, SIGTERM, pending recovery và connection cleanup đều cần được quan sát.

**Quy tắc cốt lõi:** chỉ nhận thêm công việc khi ứng dụng đủ năng lực phục vụ; khi chuẩn bị dừng, ngừng nhận công việc mới, hoàn tất đúng phần có thể hoàn tất, giữ đường phục hồi cho phần chưa xong và chỉ giải phóng Redis connections sau khi những thành phần phụ thuộc đã dừng.

