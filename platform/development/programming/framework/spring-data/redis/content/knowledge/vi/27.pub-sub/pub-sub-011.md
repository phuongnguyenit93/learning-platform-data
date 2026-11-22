# Kiểm tra hành vi Pub/Sub khi dùng Redis Sentinel hoặc Cluster trong Spring Data Redis

Trong ứng dụng Spring Data Redis, Pub/Sub thường được dùng để phát thông báo tức thời giữa các instance: làm mới bộ nhớ đệm, cập nhật giao diện theo sự kiện, hoặc thông báo một trạng thái vừa thay đổi. Khi chạy trên một Redis Standalone, việc kiểm tra tương đối đơn giản: một client `SUBSCRIBE`, một client `PUBLISH` và người nhận nhìn thấy thông điệp.

Nhưng hệ thống production thường dùng **Redis Sentinel** để tự chuyển master khi có lỗi, hoặc **Redis Cluster** để phân chia dữ liệu ra nhiều node. Hai topology này đặt ra các câu hỏi khác nhau:

- Với **Sentinel**, subscriber và publisher có tự tìm được master mới sau failover? Kết nối đăng ký có được khôi phục không? Những message xuất hiện trong khoảng gián đoạn đi đâu?
- Với **Cluster**, nếu publisher và subscriber kết nối tới hai node khác nhau thì message có tới không? `PUBLISH` báo bao nhiêu subscriber? Khác biệt giữa Pub/Sub thông thường và **sharded Pub/Sub** của Redis 7 là gì?
- Ở tầng **Spring Data Redis**, `RedisMessageListenerContainer`, `RedisConnectionFactory`, Lettuce hoặc Jedis ảnh hưởng đến kết nối lại, đăng ký lại, log lỗi và khả năng kiểm thử như thế nào?

Điểm nền tảng: **Redis Pub/Sub không phải hàng đợi lưu bền**. Message chỉ được phát tới subscriber đang có kết nối và đăng ký phù hợp; khi mất kết nối hoặc bỏ lỡ thời điểm phát, Redis không lưu một bản sao để người nhận nhận lại sau. Kiểm thử tốt phải phát hiện **khoảng mất thông điệp** thay vì chỉ kiểm tra ứng dụng kết nối lại được.

## 1. Nhắc lại mô hình Pub/Sub

Các lệnh Redis cơ bản:

| Lệnh | Ý nghĩa |
|---|---|
| `SUBSCRIBE channel` | Đăng ký nhận message trên một channel chính xác |
| `PSUBSCRIBE pattern` | Đăng ký các channel khớp pattern như `app:events:*` |
| `PUBLISH channel payload` | Phát message tới subscriber hiện đang đăng ký |
| `UNSUBSCRIBE` / `PUNSUBSCRIBE` | Hủy đăng ký channel hoặc pattern |
| `PUBSUB CHANNELS` | Liệt kê channel hiện có subscriber tại phạm vi node quan sát |
| `PUBSUB NUMSUB channel` | Đếm subscriber chính xác của channel theo phạm vi node |

Ví dụ trên Redis local:

Terminal A:

```bash
redis-cli -h 127.0.0.1 -p 6379 SUBSCRIBE app:events
```

Terminal B:

```bash
redis-cli -h 127.0.0.1 -p 6379 PUBLISH app:events "hello-001"
```

Terminal A sẽ hiển thị một frame `message` chứa channel `app:events` và payload `hello-001` nếu subscriber đã đăng ký thành công **trước** thời điểm phát. Nếu phát trước khi listener kết nối, message đó không xuất hiện sau này.

Một publisher có thể gửi message tới nhiều subscriber; mỗi subscriber phù hợp có thể nhận cùng message. Pub/Sub **không chia việc** giữa các consumer như một queue tiêu thụ cạnh tranh.

### Delivery semantics: at-most-once

Redis mô tả Pub/Sub bằng ngữ nghĩa **at-most-once**: một message đã phát sẽ không được Redis phát lại để bù cho việc subscriber offline hoặc xử lý lỗi. Do đó:

- Không có acknowledgment (ACK) theo message.
- Không có offset hoặc cursor để đọc lại.
- Không có consumer group theo nghĩa Redis Streams.
- Không có cam kết nhận đủ message qua failover, disconnect hay restart.
- Nếu ứng dụng tự retry một lần `PUBLISH` không rõ kết quả, receiver có thể **thấy payload lặp**; đó là hành vi ở tầng publisher/ứng dụng, không phải cơ chế replay bảo đảm của Pub/Sub.

Một subscriber có thể nhận lặp về mặt quan sát nếu đăng ký vừa channel vừa pattern khớp cùng message. Ví dụ `SUBSCRIBE app:events` và `PSUBSCRIBE app:*` có thể tạo hai callback cho cùng một lệnh `PUBLISH`, một frame `message` và một frame `pmessage`. Khi kiểm tra số lượng thông báo, phải tính tới hình thức đăng ký.

## 2. Sentinel và Cluster giải quyết hai vấn đề khác nhau

### 2.1. Redis Sentinel: độ sẵn sàng cao cho một nhóm master–replica

Mô hình minh họa:

```text
              Sentinel S1 (26379)
              Sentinel S2 (26380)
              Sentinel S3 (26381)
                   |
           Theo dõi master group
                   |
  Spring application / Lettuce hoặc Jedis
                   |
        Tìm địa chỉ master hiện tại
                   |
      Redis master M1 (6379)
                   |
           Replica R1 (6380)

Sau failover:
  Sentinel chọn R1 thành master mới.
  Client phải phát hiện topology mới và nối lại.
```

Sentinel **không phải** Redis data node thay thế master để lưu key hoặc truyền message ứng dụng. Sentinel là control plane để giám sát, bầu chọn và công bố thay đổi master. Ứng dụng thông thường kết nối **Redis data node** thông qua `RedisConnectionFactory` cấu hình Sentinel; không gửi `PUBLISH app:events ...` tới port Sentinel `26379`.

### 2.2. Redis Cluster: sharding nhiều nhóm master và replica

Mô hình minh họa:

```text
                     Redis Cluster

 Master A                Master B                Master C
 slots 0..5000           slots 5001..10000       slots 10001..16383
     |                       |                        |
 Replica A'              Replica B'               Replica C'

 Publisher --> Node A
 Subscriber --> Node C
```

Cluster phân chia Redis keyspace thành **16.384 hash slot**. Các lệnh liên quan đến key cần được định tuyến tới node sở hữu slot. Nhưng **Pub/Sub thông thường dùng channel, không phải key dữ liệu**, nên quy tắc phân phối của nó khác với `GET` hay `HSET`.

| So sánh | Sentinel | Cluster |
|---|---|---|
| Mục tiêu chính | Failover cho nhóm master/replica | Phân tán keyspace và failover giữa các shard |
| Phạm vi dữ liệu | Một nhóm master phục vụ một bộ dữ liệu | Nhiều master cùng phục vụ những slot khác nhau |
| Kết nối của ứng dụng | Tìm master theo tên qua Sentinel | Driver cluster-aware định tuyến tới các node |
| Pub/Sub thông thường | Gắn với Redis server/connection hiện tại, cần khôi phục qua failover | Có cơ chế chuyển tiếp thông điệp giữa các node Cluster |
| Thử nghiệm trọng tâm | Rớt subscription và resubscribe khi đổi master | Publish–subscribe khác node, node failure và phạm vi đếm subscriber |
| Rủi ro còn lại | Mất message trong thời gian ngắt kết nối | Mất message khi subscriber offline; tải broadcast và chuyển topology |

Không dùng cùng lúc cấu hình Sentinel và Cluster cho một `RedisConnectionFactory` với kỳ vọng chúng là hai tầng của cùng một topology. Trong Spring Boot, chọn một chế độ Redis connection phù hợp với hạ tầng đang sử dụng.

## 3. Chuẩn bị một publisher/subscriber kiểm thử bằng Spring Data Redis

Ví dụ dùng Spring Boot 3.x, Spring Data Redis, Lettuce mặc định và Redis local/test. Khi chuyển môi trường từ Standalone sang Sentinel hoặc Cluster, thành phần ứng dụng vẫn giữ nguyên phần lớn mã nghiệp vụ; khác biệt nằm ở cấu hình `RedisConnectionFactory` và hành vi connection recovery.

Dependency Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Ở đây dùng REST endpoint chỉ để phát thông điệp có thể quan sát. Với ứng dụng không dùng web, có thể gọi cùng service từ scheduled job hoặc command-line runner.

### 3.1. Lắng nghe bằng RedisMessageListenerContainer

`RedisMessageListenerContainer` quản lý subscription và luồng dispatch listener, giảm việc tự quản lý blocking connection cho từng subscriber. Container dùng `RedisConnectionFactory` giống phần còn lại của ứng dụng, vì vậy khi connection factory chạy ở Sentinel hoặc Cluster mode thì container cũng sử dụng topology đó.

```java
import java.nio.charset.StandardCharsets;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class PubSubConfig {

    private static final Logger log =
            LoggerFactory.getLogger(PubSubConfig.class);

    public static final String CHANNEL = "app:events";

    @Bean
    public MessageListener logMessageListener() {
        return (Message message, byte[] pattern) -> {
            String channel = new String(
                    message.getChannel(), StandardCharsets.UTF_8);
            String payload = new String(
                    message.getBody(), StandardCharsets.UTF_8);

            log.info("PUBSUB_RECEIVED channel={} payload={}",
                    channel, payload);
        };
    }

    @Bean
    public RedisMessageListenerContainer redisListenerContainer(
            RedisConnectionFactory connectionFactory,
            MessageListener logMessageListener) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.addMessageListener(
                logMessageListener,
                new ChannelTopic(CHANNEL));

        // Khoảng chờ giữa những lần thử khôi phục subscription
        // khi lỗi kết nối (tùy API/phiên bản Spring Data Redis).
        container.setRecoveryInterval(2_000L);

        container.setErrorHandler(error ->
                log.error("PUBSUB_LISTENER_ERROR", error));
        return container;
    }
}
```

Trong ví dụ, publisher sẽ dùng `StringRedisTemplate` nên payload là chuỗi UTF-8. Listener giải mã byte bằng UTF-8 tường minh. Nếu dùng `RedisTemplate<String, MyEvent>` và serializer JSON, phải thiết kế serializer/decoder cho payload tương ứng; không được tự đọc dữ liệu nhị phân bằng `new String(...)` rồi mong nhận lại đối tượng Java.

`RedisMessageListenerContainer` có khả năng thử đăng ký lại khi kết nối bị lỗi, sử dụng cơ chế recovery/backoff của phiên bản Spring Data Redis đang chạy. **Điều đó chỉ phục hồi kênh nghe cho các message tương lai**; không replay những message đã phát khi subscriber offline.

Để kiểm thử thời điểm đăng ký chính xác, có thể triển khai `SubscriptionListener` hoặc sử dụng công cụ/metric báo subscription active thay vì giả định listener đã sẵn sàng chỉ vì JVM khởi động. Container hỗ trợ callback xác nhận subscribe/unsubscribe; callback này hữu ích để đo khoảng downtime khi failover.

### 3.2. Publisher phát sự kiện có ID và số thứ tự

```java
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class PubSubPublisher {

    private final StringRedisTemplate template;

    public PubSubPublisher(StringRedisTemplate template) {
        this.template = template;
    }

    public long send(String source, long sequence) {
        String payload = "source=" + source
                + ";sequence=" + sequence
                + ";eventId=" + UUID.randomUUID()
                + ";sentAt=" + Instant.now();

        Long subscriberCount =
                template.convertAndSend(PubSubConfig.CHANNEL, payload);

        return subscriberCount == null ? 0 : subscriberCount;
    }
}
```

Với một Redis Cluster, giá trị `subscriberCount` do `PUBLISH` trả về **không phải tổng số subscriber của cả cluster**: Redis chỉ đếm các client nhận message kết nối với **cùng node** phục vụ lệnh publish. Vì vậy, kết quả `0` vẫn có thể đi kèm với việc subscriber ở node khác thực sự nhận được message.

Nếu dùng Pub/Sub để kiểm chứng độ phủ, hãy quan sát **log của từng subscriber**, không lấy giá trị trả về từ `convertAndSend` làm bằng chứng duy nhất.

### 3.3. REST endpoint phục vụ thực hành

```java
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PubSubTestController {

    private final PubSubPublisher publisher;

    public PubSubTestController(PubSubPublisher publisher) {
        this.publisher = publisher;
    }

    @PostMapping("/lab/pubsub/publish")
    public long publish(
            @RequestParam String source,
            @RequestParam long sequence) {
        return publisher.send(source, sequence);
    }
}
```

Gọi trong môi trường test:

```bash
curl -X POST "http://localhost:8080/lab/pubsub/publish?source=publisher-a&sequence=101"
```

Log subscriber:

```text
PUBSUB_RECEIVED channel=app:events
payload=source=publisher-a;sequence=101;eventId=...;sentAt=...
```

Đây là endpoint lab; **không mở công khai endpoint có thể phát message tùy ý** nếu chưa có xác thực, phân quyền và giới hạn tốc độ. Trong hệ thống thật, publisher nên là thành phần nghiệp vụ nội bộ với schema sự kiện ổn định.

### 3.4. Quy tắc ghi nhận kết quả thử nghiệm

Mỗi lần phát cần ít nhất:

```text
source          Mã định danh publisher
sequence        Số thứ tự tăng
eventId         Định danh duy nhất của lần publish
sentAt          Thời điểm publisher gửi
receivedAt      Thời điểm listener nhận tại từng instance
subscriberId    Instance/process nhận
topologyState   Master hoặc cluster node tại thời điểm thử
outcome         received / not-observed / failed / unknown
```

Không thể xác định mất message chỉ từ một log `PUBLISH done`. Cần so sánh tập message đã phát thành công được ghi nhận với tập message mà **mỗi subscriber dự kiến** đã nhận, xét cả lúc subscriber chưa đăng ký. Timestamp của những máy khác nhau có thể lệch; nên dùng sequence/eventId làm đối chiếu chính.

## 4. Thử nghiệm Pub/Sub qua Sentinel: cấu hình Spring Boot

Giả sử có ba Sentinel tại các cổng `26379`, `26380` và `26381`, quản lý một master group có tên `mymaster`. Cấu hình `application-sentinel.yml`:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
        nodes:
          - 127.0.0.1:26379
          - 127.0.0.1:26380
          - 127.0.0.1:26381
      timeout: 5s
```

Ví dụ dùng địa chỉ loopback vì hạ tầng test nằm trên một máy. Các node được Sentinel công bố cần có địa chỉ **truy cập được từ tiến trình Java**. Trong Docker/Kubernetes, địa chỉ container nội bộ hoặc IP private trả về từ Sentinel có thể không truy cập được từ ứng dụng ngoài mạng đó.

Chạy ứng dụng bằng profile `sentinel`. Spring Boot tạo `RedisConnectionFactory` dựa trên cấu hình Sentinel nếu dự án có dependency phù hợp. Trong Java configuration thủ công, có thể tạo `RedisSentinelConfiguration` và chuyển cho `LettuceConnectionFactory` hoặc `JedisConnectionFactory`.

### 4.1. Quan sát master hiện tại

Trước khi gây lỗi, hỏi Sentinel:

```bash
redis-cli -h 127.0.0.1 -p 26379 \
  SENTINEL get-master-addr-by-name mymaster
```

Kết quả là host/port của Redis master hiện tại, ví dụ:

```text
1) "127.0.0.1"
2) "6379"
```

Có thể kiểm tra vai trò data node:

```bash
redis-cli -h 127.0.0.1 -p 6379 ROLE
redis-cli -h 127.0.0.1 -p 6380 ROLE
```

Một node là master, replica báo vai trò slave/replica tùy cách hiển thị của lệnh/phiên bản. Không hardcode giả định `6379` luôn là master khi kiểm tra sau failover: hãy hỏi Sentinel lại.

### 4.2. Baseline trước khi failover

Khởi chạy hai instance subscriber (ví dụ ở hai cổng HTTP khác nhau) cùng dùng `RedisMessageListenerContainer`. Đợi log hoặc callback cho biết subscription sẵn sàng. Sau đó gửi 20 message từ một publisher:

```text
source=before-failover;sequence=1
source=before-failover;sequence=2
...
source=before-failover;sequence=20
```

Kỳ vọng trong điều kiện ổn định:

- Mỗi subscriber đang đăng ký đúng channel nhận thông điệp tương ứng.
- Thứ tự trong luồng phân phối đơn từ một publisher được quan sát nhất quán trên mỗi connection trong điều kiện không có lỗi.
- Việc nhiều subscriber nhận cùng message là đúng hành vi **fan-out**, không phải nhân đôi nhiệm vụ.

Nếu listener callback xử lý bất đồng bộ trên executor nhiều luồng, **thứ tự log xử lý hoàn tất** có thể khác thứ tự Redis gửi message tới connection. Để đánh giá ordering mạng, nên ghi lại thời điểm message vừa vào callback trước khi xử lý lâu hoặc chuyển việc.

### 4.3. Kích hoạt failover có kiểm soát

Chỉ thực hiện trên **Redis Sentinel test cluster** đã được chuẩn bị; thao tác này sẽ thay đổi master và có thể ngắt dịch vụ.

Một cách yêu cầu Sentinel thử failover:

```bash
redis-cli -h 127.0.0.1 -p 26379 SENTINEL FAILOVER mymaster
```

Lệnh này yêu cầu Sentinel chủ động thực hiện failover mà không cần đợi master thật sự ngừng hoạt động. Tùy trạng thái quorum, quyền và topology, failover có thể chưa hoàn tất ngay sau phản hồi từ lệnh. Quan sát:

```bash
redis-cli -h 127.0.0.1 -p 26379 \
  SENTINEL get-master-addr-by-name mymaster

redis-cli -h 127.0.0.1 -p 26379 \
  SENTINEL master mymaster
```

Trong thời gian đang chuyển master, tiếp tục phát sequence `21` đến `100` ở nhịp có kiểm soát (ví dụ mỗi 100–200 ms) và ghi nhận cả những lần publisher gặp lỗi kết nối. Nếu publisher tự retry, phải tách số lần **cố gắng gửi** khỏi số lần **Redis xác nhận đã nhận PUBLISH**.

Kiểm thử thêm tình huống master thật sự mất kết nối bằng cách dừng **node test** tương ứng, nhưng chỉ khi môi trường được phép gián đoạn. Không dừng node đang dùng chung với ứng dụng ngoài bài lab.

### 4.4. Kết quả đúng cần phân biệt

| Quan sát | Diễn giải |
|---|---|
| Listener nhận message trước failover | Baseline hoạt động |
| Trong lúc failover listener không nhận một số sequence | **Có thể xảy ra và đúng với at-most-once** |
| Kết nối bị reset và listener đăng ký lại | Driver/container đang phục hồi kết nối |
| Sau failover message mới tiếp tục được nhận | Đường kết nối và subscription đã phục hồi |
| Message đã mất trong khoảng failover tự xuất hiện lại | **Không phải bảo đảm của Redis Pub/Sub**; kiểm tra publisher retry, duplicate, hoặc cơ chế lưu bền ở tầng ứng dụng |
| Container không phục hồi subscription | Cần điều tra driver, endpoint Sentinel, network, ACL, timeout, recovery/backoff |

Điều cần đo là **khoảng mù subscription** giữa lần nhận cuối trước khi lỗi và lần nhận đầu sau khi kết nối lại. Kết nối tới master mới thành công chưa đủ: phải xác nhận **subscriber đã tái đăng ký channel**.

### 4.5. Phân biệt sự kiện Sentinel với message nghiệp vụ

Sentinel có các kênh sự kiện quản trị như:

```text
+switch-master
+sdown
+odown
```

Đây là thông báo **từ dịch vụ Sentinel** dành cho việc giám sát, không phải message từ `app:events` trên Redis data node.

Ví dụ quan sát sự kiện tại Sentinel:

```bash
redis-cli -h 127.0.0.1 -p 26379 \
  PSUBSCRIBE '+switch-master'
```

Nếu thấy `+switch-master`, chỉ có thể kết luận rằng Sentinel đang công bố thay đổi master. Không thể lấy sự kiện này thay thế cho việc xác minh Pub/Sub ứng dụng đã hoạt động ở data node mới. Cấu hình Sentinel master discovery và đăng ký application channel là **hai việc khác nhau**.

## 5. Vì sao Pub/Sub có thể mất message khi failover?

Một chuỗi thời gian điển hình:

```text
t0: Subscriber S đang SUBSCRIBE app:events ở master M1.
t1: Publisher P gửi event 100, S nhận được.
t2: M1 mất kết nối hoặc bị thay thế.
t3: P gửi event 101; có thể lỗi hoặc được node nào đó nhận.
t4: Client của S phát hiện connection bị đóng.
t5: Sentinel công bố master M2.
t6: Driver kết nối tới M2 và container SUBSCRIBE lại.
t7: P gửi event 102, S nhận được.
```

Message `101` **không được Redis giữ lại để chờ S**. Nếu Pub/Sub là tín hiệu “cần refresh cache” thì có thể chấp nhận việc này, với điều kiện có cơ chế TTL/reconciliation bổ sung. Nếu Pub/Sub là sự kiện phải được xử lý chính xác một lần để phát hành giao dịch, đây là lựa chọn công nghệ không đủ bảo đảm.

Không giả định rằng một lời gọi `PUBLISH` thành công tại publisher tương đương:

1. Mọi subscriber đều đã kết nối.
2. Mọi subscriber đều nhận message.
3. Ứng dụng listener đã xử lý xong nghiệp vụ.
4. Message đã được lưu bền vào Redis.

`PUBLISH` không cung cấp ACK theo ứng dụng; giá trị trả về không đại diện cho bốn điều trên.

## 6. Kiểm thử Redis Cluster: Pub/Sub thông thường

Ví dụ cấu hình `application-cluster.yml`:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - 127.0.0.1:7000
          - 127.0.0.1:7001
          - 127.0.0.1:7002
      timeout: 5s
```

Cluster cần được tạo sẵn có các master/replica phù hợp. Khai báo nhiều seed node **không tự tạo Cluster**. Trong thực tế, driver còn cần truy cập các địa chỉ node do Cluster công bố; cấu hình network/NAT sai có thể làm kết nối ban đầu được nhưng chuyển hướng lại thất bại.

### 6.1. Test publish ở node A, subscribe ở node B

Terminal A đăng ký trên một Redis node:

```bash
redis-cli -h 127.0.0.1 -p 7000 SUBSCRIBE app:events
```

Terminal B publish trên node khác:

```bash
redis-cli -h 127.0.0.1 -p 7001 \
  PUBLISH app:events "cluster-cross-node-001"
```

Với **Pub/Sub thông thường (global/classic Pub/Sub)** của Redis Cluster, message được phân phối qua cluster bus để subscriber ở node khác nhận được. Channel thường không bị ràng buộc vào một hash slot giống một Redis key.

Lặp lại:

1. Subscriber ở node `7000`, publisher ở `7001`.
2. Subscriber ở node `7002`, publisher ở `7000`.
3. Hai subscriber ở hai node khác nhau cùng nghe `app:events`, publisher ở node thứ ba.
4. Một listener dùng `PatternTopic("app:*")` và một listener dùng `ChannelTopic("app:events")` để quan sát channel/pattern.

Kết quả cần kiểm tra là **message tới những subscriber đã đăng ký ở nhiều node**, không chỉ “`PUBLISH` trả số lớn hơn 0”.

### 6.2. Vì sao PUBLISH có thể trả 0 mà subscriber vẫn nhận?

Tài liệu Redis quy định `PUBLISH` trên Cluster trả số client nhận message **đang kết nối với cùng node như publisher**, không phải tổng subscriber ở mọi node. Ví dụ:

```text
Node A (7000)                         Node B (7001)
  Subscriber S đang nghe app:events      Publisher P
       ^                                    |
       | <----- cluster bus -------------   | PUBLISH app:events X
       |                                    |
       +--- S nhận X                        +--- có thể trả 0
```

Đây là một trong những bẫy phổ biến nhất khi viết test:

```java
long count = template.convertAndSend("app:events", "hello");
if (count == 0) {
    // KHÔNG được kết luận chắc chắn:
    // "Không subscriber nào trong cluster nhận được".
}
```

`PUBSUB NUMSUB app:events` và các lệnh introspection khác cũng phản ánh **ngữ cảnh Pub/Sub của node** nhận lệnh, không phải danh sách subscriber toàn Cluster. Khi cần kiểm kê toàn cục, phải khảo sát các node liên quan hoặc dùng telemetry của chính các subscriber.

### 6.3. Cluster không biến Pub/Sub thành durable messaging

Pub/Sub thông thường có khả năng fan-out cross-node, nhưng vẫn **at-most-once**. Nếu một subscriber kết nối vào node đang failover hoặc một kết nối mạng bị mất, các message phát trong khoảng subscriber offline không được replay.

Việc cluster còn nhiều master hoạt động không có nghĩa mọi subscriber ở master bị lỗi vẫn liên tục nhận thông điệp. Cluster cung cấp availability/routing cho dữ liệu; application listener vẫn cần reconnect/resubscribe và vẫn có khoảng gián đoạn.

## 7. Sharded Pub/Sub của Redis 7: một trường hợp khác

Từ **Redis 7.0**, Cluster hỗ trợ **sharded Pub/Sub** bằng:

- `SSUBSCRIBE shard-channel`: đăng ký channel trong một shard.
- `SPUBLISH shard-channel payload`: phát message trong shard tương ứng.
- `SUNSUBSCRIBE`: hủy shard subscription.
- `PUBSUB SHARDCHANNELS` và `PUBSUB SHARDNUMSUB`: introspection cho sharded Pub/Sub.

Khác biệt:

| Tiêu chí | Pub/Sub thông thường | Sharded Pub/Sub |
|---|---|---|
| Subscribe | `SUBSCRIBE` / `PSUBSCRIBE` | `SSUBSCRIBE` |
| Publish | `PUBLISH` | `SPUBLISH` |
| Phạm vi | Cluster truyền thông điệp giữa các node | Chỉ truyền trong shard sở hữu slot của channel |
| Ánh xạ channel sang slot | Không dùng để hạn chế classic Pub/Sub | Dùng thuật toán hash slot như Redis key |
| Phù hợp | Fan-out toàn Cluster, lưu lượng vừa phải | Nhiều channel/lưu lượng lớn cần hạn chế cluster-bus traffic |
| Redis tối thiểu | Tính năng Redis Pub/Sub truyền thống | Redis **7.0+** |

Chính xác hơn, shard message cần được gửi đến node đang sở hữu slot của shard channel; các node trong cùng shard (master và replica của shard) có thể nhận và chuyển tiếp các shard message. Không phải mọi node trong cluster đều có subscription state của shard channel.

### 7.1. Kiểm tra slot và hash tag của shard channel

Channel sharded cũng được băm ra một slot. Ví dụ:

```bash
redis-cli -h 127.0.0.1 -p 7000 \
  CLUSTER KEYSLOT events:{tenant-42}:orders

redis-cli -h 127.0.0.1 -p 7000 \
  CLUSTER KEYSLOT events:{tenant-42}:inventory
```

Hai channel có cùng hash tag `{tenant-42}` sẽ thuộc cùng slot. Đây là một cách tạo tính cục bộ, nhưng đặt mọi tenant vào cùng một hash tag sẽ làm lệch tải. Nếu số channel rất lớn, chọn tên channel có phân bố slot hợp lý.

### 7.2. Thử nghiệm SSUBSCRIBE và SPUBLISH

Giả sử slot của `events:{tenant-42}:orders` thuộc shard master tại `7001` (phải xác nhận với `CLUSTER KEYSLOT` và `CLUSTER SLOTS` trên môi trường test thực tế).

Terminal subscriber:

```bash
redis-cli -h 127.0.0.1 -p 7001 \
  SSUBSCRIBE 'events:{tenant-42}:orders'
```

Terminal publisher:

```bash
redis-cli -h 127.0.0.1 -p 7001 \
  SPUBLISH 'events:{tenant-42}:orders' 'shard-001'
```

Subscriber đang kết nối tới master hoặc replica của shard sở hữu slot có thể nhận thông điệp. Nếu cố đăng ký hoặc phát tại node ngoài shard, server có thể trả chuyển hướng `MOVED`; cần dùng client/CLI hỗ trợ Cluster để định tuyến đúng. Trong ví dụ, port `7001` chỉ là giả định, không phải quy tắc ánh xạ slot.

**Không trộn hai bộ lệnh rồi mong chúng giao tiếp với nhau:**

```text
PUBLISH    --> SUBSCRIBE / PSUBSCRIBE    (classic Pub/Sub)
SPUBLISH   --> SSUBSCRIBE              (sharded Pub/Sub)
```

`PUBLISH` không phải alias của `SPUBLISH`. Một `RedisMessageListenerContainer` được cấu hình bằng `ChannelTopic` tiêu chuẩn dùng Pub/Sub thông thường qua driver/adapter tương ứng; **không nên giả định nó tự chuyển sang `SSUBSCRIBE`** chỉ vì Redis server đã nâng cấp lên 7.0. Nếu chọn sharded Pub/Sub, phải kiểm tra rõ API native của Lettuce/Jedis và mức hỗ trợ của phiên bản Spring Data Redis đang chạy.

### 7.3. Vì sao sharded Pub/Sub có thể cần thiết?

Với classic Pub/Sub, thông điệp trên Cluster được truyền giữa các node, làm tăng lưu lượng cluster bus. Khi số publisher/message lớn, broadcast toàn Cluster có thể tốn tài nguyên. Sharded Pub/Sub giới hạn truyền thông điệp trong shard, có thể mở rộng ngang tốt hơn khi channel được phân bố hợp lý.

Nhưng sharded Pub/Sub **không thêm replay, ACK hay bền vững**. Bài toán mất message khi subscriber offline vẫn còn nguyên. Nếu yêu cầu là message phải được xử lý sau khi một subscriber restart, giải pháp không chỉ là chuyển từ `PUBLISH` sang `SPUBLISH`.

## 8. Thử nghiệm failover của một node trong Cluster

Mục tiêu: phân biệt **fan-out liên node khi Cluster ổn định** với **khả năng khôi phục subscription khi node gặp lỗi**.

### 8.1. Thiết lập baseline

Trên môi trường Cluster test gồm master và replica:

1. Khởi chạy hai Spring subscriber hoặc hai Redis CLI subscriber ở các node khác nhau.
2. Gửi một dãy message `cluster-before-001` đến `cluster-before-020`.
3. Ghi nhận message đến từng subscriber.
4. Quan sát topology hiện tại:

```bash
redis-cli -h 127.0.0.1 -p 7000 CLUSTER INFO
redis-cli -h 127.0.0.1 -p 7000 CLUSTER NODES
```

### 8.2. Gây failover trong môi trường test

Trên **replica test** của một master, có thể yêu cầu chủ động failover bằng:

```bash
redis-cli -h 127.0.0.1 -p 7003 CLUSTER FAILOVER
```

Lệnh này chỉ dùng khi `7003` thực sự là một replica hợp lệ của node muốn chuyển vai trò. Nếu topology không có replica, lệnh không đáp ứng mục tiêu. Không chạy tùy tiện trên Cluster production.

Trong khi failover, publisher phát tiếp các sequence có log thời điểm và lỗi. Sau khi Cluster ổn định, gửi thêm nhóm message mới.

### 8.3. Quan sát

Các câu hỏi cần trả lời bằng dữ liệu:

- Subscriber gắn vào node failover có bị ngắt kết nối không?
- Driver Lettuce/Jedis phát hiện thay đổi topology và mở lại kết nối như thế nào?
- `RedisMessageListenerContainer` đăng ký lại channel vào thời điểm nào?
- Khi subscriber đã resubscribe, message **mới** có đến như trước không?
- Những sequence phát trong lúc subscription gián đoạn có bị thiếu không?
- Khi test classic Pub/Sub, message gửi từ node khác vẫn fan-out qua Cluster sau khi ổn định chứ?
- Khi test sharded Pub/Sub, subscription có được chuyển đúng shard/owner slot sau failover không?

Không nên coi “Cluster xanh trở lại” hoặc “`CLUSTER INFO` báo `cluster_state:ok`” là bằng chứng tự động rằng tất cả listener của ứng dụng đã đăng ký trở lại.

## 9. Các vấn đề đặc thù của Spring Data Redis và driver

### 9.1. RedisMessageListenerContainer dùng kết nối subscribe

Ở cấp thấp, lời gọi `RedisConnection.subscribe(...)` có thể chặn luồng chờ message, và kết nối ở trạng thái subscribe không được dùng tùy ý cho các lệnh dữ liệu thông thường. `RedisMessageListenerContainer` quản lý việc đăng ký, dispatch và tài nguyên giúp ứng dụng không phải tự giữ một luồng blocking cho từng listener.

Nếu cần đăng ký nhiều channel hoặc pattern, có thể:

```java
container.addMessageListener(
        logMessageListener,
        new ChannelTopic("app:events"));

container.addMessageListener(
        logMessageListener,
        new ChannelTopic("app:alerts"));
```

Hoặc dùng `PatternTopic("app:*")` cho classic Pub/Sub. Lưu ý các pattern quá rộng có thể tạo tải đáng kể trên Redis và trên consumer. Không dùng pattern trùng với exact subscription nếu hệ thống không mong muốn xử lý cùng message nhiều lần.

### 9.2. Lettuce và Jedis đều có cấu hình topology riêng

Trong ứng dụng Spring Data Redis:

- **Lettuce** dựa trên Netty, hỗ trợ async/reactive và các chế độ Sentinel/Cluster. Topology refresh, reconnect và địa chỉ được quảng bá bởi server ảnh hưởng khả năng phục hồi.
- **Jedis** hỗ trợ Sentinel/Cluster theo API và phiên bản cụ thể; cơ chế subscribe, pool và recovery có đặc điểm khác Lettuce.
- Spring Data Redis adapter và `RedisMessageListenerContainer` cung cấp một mức trừu tượng, nhưng không làm hai driver giống nhau trong tất cả trường hợp network failure.

Không có quy tắc “dùng Lettuce thì chắc chắn không mất message” hoặc “dùng Jedis thì phải restart listener sau failover”. **Mất message là hệ quả của delivery semantics at-most-once**; điều cần kiểm chứng với từng driver là khả năng nối lại, độ trễ resubscribe và hành vi khi topology thay đổi.

### 9.3. RedisStaticMasterReplicaConfiguration không phải Sentinel

Một điểm dễ nhầm: cấu hình **static master/replica** với `RedisStaticMasterReplicaConfiguration` không tự cung cấp topology discovery và failover như Sentinel. Tài liệu Spring Data Redis còn lưu ý chế độ static master/replica này **không hỗ trợ Pub/Sub** do thiếu cơ chế truyền Pub/Sub message giữa các server riêng lẻ trong kiểu kết nối đó.

Đừng dùng mẫu cấu hình static read-replica để suy luận hành vi Pub/Sub của Sentinel, hoặc ngược lại. Muốn thử khả năng failover của Sentinel, cần cấu hình Sentinel đúng và kiểm tra sự chuyển master.

### 9.4. Phân biệt lỗi của listener và lỗi của kết nối

`setErrorHandler(...)` giúp quan sát ngoại lệ khi xử lý listener. Nhưng cần theo dõi **cả**:

- Lỗi kết nối/tạo subscription và số lần retry.
- Sự kiện đã đăng ký/hủy đăng ký channel.
- Lỗi trong callback `onMessage` hoặc decoder.
- Lỗi publisher khi `convertAndSend(...)`.
- Tổng số message bị thiếu theo sequence, tách theo subscriber instance.

Đăng ký thành công rồi callback ném exception có nghĩa Redis đã phát message tới connection nhưng ứng dụng có thể không xử lý thành công. Pub/Sub không gửi lại message đó cho listener.

### 9.5. Phân biệt thứ tự phát và thứ tự xử lý

Trong điều kiện kết nối ổn định, Redis chuyển message theo thứ tự công bố trên một channel. Nhưng khi xử lý tại ứng dụng:

```text
Redis nhận: M1 -> M2 -> M3
Listener callback -> executor pool
Hoàn tất xử lý: M2 -> M1 -> M3 (có thể)
```

Nếu nhiệm vụ cần thứ tự xử lý, không chỉ thứ tự nhận, phải thiết kế bộ xử lý tuần tự theo channel/key hoặc thêm sequence và logic ordering. Pub/Sub không tự cung cấp exactly-once hay transaction bảo vệ tiến độ xử lý.

## 10. Bộ kịch bản kiểm tra có thể lặp lại

Chuẩn bị hai ứng dụng subscriber `S1` và `S2`, một publisher `P`. Mỗi message có `eventId` và `sequence`. Khi cần mô phỏng lỗi, chỉ dùng Redis topology dành riêng cho test.

| Mã | Môi trường | Thao tác | Kỳ vọng |
|---|---|---|---|
| TC01 | Sentinel ổn định | PUBLISH 20 message; S1/S2 đều subscribe | S1 và S2 đều quan sát đủ message được phát sau khi subscribe |
| TC02 | Sentinel | Kích hoạt failover khi đang publish | Có thể thiếu message; xác định thời gian reconnect/resubscribe |
| TC03 | Sentinel | Publish tiếp sau khi master mới ổn định | Listener hoạt động trở lại nếu driver/container phục hồi |
| TC04 | Sentinel | Dừng S2, PUBLISH, khởi động lại S2 | S2 **không nhận lại** message lúc offline |
| TC05 | Cluster ổn định | Subscribe ở A, publish ở B | Classic Pub/Sub chuyển message tới subscriber khác node |
| TC06 | Cluster ổn định | PUBLISH ở B, kiểm tra reply=0, S1 ở A | S1 vẫn có thể nhận; reply chỉ đếm local-node clients |
| TC07 | Cluster | Failover node đang giữ connection của S1 | Quan sát disconnect, resubscribe và thiếu sequence |
| TC08 | Cluster | Hai subscriber nghe cùng channel | Mỗi subscriber nhận message riêng; không chia tải như queue |
| TC09 | Redis 7+ Cluster | SPUBLISH/SSUBSCRIBE đúng shard | Shard subscriber nhận; message chỉ được truyền trong shard |
| TC10 | Redis 7+ Cluster | Dùng PUBLISH nhưng listener chỉ SSUBSCRIBE | Không coi đây là cùng cơ chế; không mong nhận cross-mode |
| TC11 | Cả hai | Listener callback cố tình ném exception trên một event | Không có Redis retry hoặc ACK tự động |
| TC12 | Cả hai | Publisher retry cùng payload sau timeout | Ứng dụng phải phát hiện/khử trùng nếu nghiệp vụ cần |

### 10.1. Quy tắc đánh giá kết quả

Một công thức quan sát cho từng subscriber:

```text
Expected = các event đã được phát khi subscriber được xem là sẵn sàng
Received = eventId thực tế có trong log của subscriber đó
Missing  = Expected - Received
Extra    = Received - Expected
```

Cần hiểu `Missing` là **đã không quan sát được**, không nhất thiết là server đã bỏ message: có thể publisher chưa phát thành công, subscriber chưa subscribe, callback lỗi hoặc log chưa được flush. Khi điều tra, đối chiếu trạng thái và log của từng thành phần.

Với Redis Cluster, **không dùng return count của PUBLISH** làm tập `Expected` vì reply count bị giới hạn theo node. Tập phát nên được ghi lại ở ứng dụng publisher kèm kết quả gọi Redis và thời điểm; nếu timeout, đánh dấu `unknown` thay vì khẳng định message đã hoặc chưa đến.

### 10.2. Readiness sau khi reconnect

Nếu kiểm thử phát ngay sau khi khởi động, có thể gửi message trước khi subscription được thiết lập. Kết quả thiếu message này không chứng minh Sentinel/Cluster có lỗi. Cần:

1. Đợi xác nhận subscriber đã đăng ký.
2. Sau đó mới bắt đầu đếm sequence baseline.
3. Khi gây failover, đo cả thời điểm connection rơi và thời điểm đăng ký lại.
4. Chỉ kết luận recovery thành công khi phát **message mới** sau thời điểm resubscribe và nhận được ở listener.

Trong hệ thống test có nhiều subscriber, readiness cần được xác nhận **từng instance**, không chỉ một instance trong nhóm.

## 11. Giám sát và xử lý sự cố

### 11.1. Redis CLI để quan sát classic Pub/Sub

```bash
# Có subscriber channel nào trên node đang hỏi?
redis-cli -h 127.0.0.1 -p 7000 PUBSUB CHANNELS "app:*"

# Số subscriber exact channel được node đó thấy
redis-cli -h 127.0.0.1 -p 7000 PUBSUB NUMSUB app:events

# Đếm pattern subscription trong phạm vi node
redis-cli -h 127.0.0.1 -p 7000 PUBSUB NUMPAT
```

Trong Cluster, các lệnh trên phản ánh **ngữ cảnh node**. Đừng lấy `PUBSUB NUMSUB` trên một node để kết luận số subscriber tổng trong toàn Cluster.

### 11.2. Redis CLI để quan sát sharded Pub/Sub

```bash
redis-cli -h 127.0.0.1 -p 7001 \
  PUBSUB SHARDCHANNELS 'events:*'

redis-cli -h 127.0.0.1 -p 7001 \
  PUBSUB SHARDNUMSUB 'events:{tenant-42}:orders'
```

Đây là các lệnh **sharded**, không phải introspection cho `SUBSCRIBE` thông thường. Trước khi gọi, xác nhận Redis phiên bản 7.0+ và kết nối đúng node/shard tương ứng.

### 11.3. Chỉ số quan trọng ở ứng dụng

| Metric/log | Tại sao hữu ích |
|---|---|
| `pubsub.subscription.active{instance,channel}` | Phát hiện listener không còn đăng ký |
| `pubsub.reconnect.count{instance}` | Phát hiện kết nối/topology bất ổn |
| `pubsub.resubscribe.duration` | Thời gian mù có thể mất message |
| `pubsub.received.count{instance,channel}` | Đo khối lượng thực nhận |
| `pubsub.sequence.gap.count` | Phát hiện lỗ hổng trong dãy message quan sát |
| `pubsub.listener.error.count` | Phân biệt mất kết nối và xử lý thất bại |
| `pubsub.publish.error.count` | Ghi nhận publisher không xác nhận được lệnh |
| `redis.cluster.redirect.count` | Phát hiện topology đổi thường xuyên khi dùng Cluster |

Tên metric chỉ là gợi ý; ứng dụng phải tự định nghĩa hoặc cấu hình instrumentation. Không giả định Spring Data Redis xuất sẵn mọi metric với những tên này.

### 11.4. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Điều nên kiểm tra |
|---|---|---|
| Sau failover vẫn publish được nhưng không nhận được | Subscriber chưa resubscribe | Log `RedisMessageListenerContainer`, connection factory, subscription readiness |
| Pub/Sub mất vài event khi Sentinel đổi master | At-most-once + reconnect gap | So sánh sequence, mốc failover, resubscribe |
| `PUBLISH` trên Cluster trả 0 nhưng người nghe vẫn thấy event | Reply chỉ đếm local-node receivers | Đối chiếu log từng subscriber/node |
| Spring app kết nối được Sentinel nhưng không kết nối master mới | Sentinel công bố IP/port không truy cập được, ACL/TLS sai | `SENTINEL get-master-addr-by-name` và kết nối từ host ứng dụng |
| Cluster subscriber mất tin sau rebalance | Connection đến node cũ bị ngắt, cần reconnect/đăng ký lại | Log topology, MOVED/ASK, listener recovery |
| Dùng `SSUBSCRIBE` mà `PUBLISH` không tới | Trộn classic và sharded Pub/Sub | Dùng đúng cặp `SPUBLISH`–`SSUBSCRIBE` |
| `SSUBSCRIBE` báo MOVED | Node không sở hữu slot của shard channel | Kiểm tra slot owner và dùng cluster-aware client |
| Listener nhận payload lạ/giải mã lỗi | Publisher/consumer dùng serializer khác nhau | Đồng bộ message codec, charset, schema |
| Cùng một event vào callback hai lần | Đăng ký channel và pattern trùng; publisher retry | Kiểm tra subscription, eventId và idempotency |
| Không thể dùng Pub/Sub với static master/replica setup | Giới hạn `RedisStaticMasterReplicaConfiguration` | Dùng Sentinel/Cluster hoặc topology phù hợp |
| Ứng dụng bỏ lỡ một phần dữ liệu nghiệp vụ | Pub/Sub không lưu message | Dùng Redis Streams/queue bền + reconciliation |

## 12. Khi nào cần Redis Streams thay cho Pub/Sub?

Redis Pub/Sub phù hợp với tín hiệu **best-effort**, nơi thông báo mới quan trọng hơn khả năng replay: cập nhật UI trực tiếp, “hãy refresh cache” hoặc broadcast trạng thái có thể đối chiếu lại từ dữ liệu bền vững.

Redis Streams phù hợp hơn khi hệ thống cần:

- Duy trì lịch sử message để đọc lại sau restart.
- Consumer group chia công việc và ghi nhận tiến độ.
- ACK, pending entries và retry khi xử lý lỗi.
- Khả năng khôi phục sau failover/disconnect với thiết kế độ bền tương ứng.

Ví dụ luồng chịu lỗi tốt hơn:

```text
Database / durable state
       |
       +--> Redis Stream (XADD)
       |      |
       |      +--> Consumer group đọc, ACK, retry
       |
       +--> Redis Pub/Sub (PUBLISH)
              |
              +--> Tín hiệu thời gian thực cho subscriber online
```

Pub/Sub có thể đóng vai trò **thông báo** để listener biết cần đọc trạng thái mới, trong khi bản ghi thực được lưu ở database hoặc stream. Khi reconnect, listener thực hiện **reconciliation** từ nguồn bền vững thay vì kỳ vọng Redis tự phát lại toàn bộ message đã mất.

**Lưu ý:** Streams không tự bảo đảm exactly-once processing end-to-end; ứng dụng vẫn phải quản lý ACK, duplicate, idempotency và độ bền của Redis. Nhưng Streams cung cấp khả năng lưu và đọc lại mà Pub/Sub không có.

## 13. Kết luận

Khi chạy Spring Data Redis Pub/Sub trên **Sentinel**, điều quan trọng nhất là kiểm tra sự thay đổi master, khả năng kết nối lại và đăng ký lại channel. Sentinel giúp phát hiện và chuyển master, **không bảo đảm delivery** cho những message đã phát trong lúc listener mất kết nối.

Khi chạy trên **Cluster**, Pub/Sub thông thường có thể truyền message giữa các node, nên publisher và subscriber không phải nhất thiết kết nối cùng node. Tuy nhiên, giá trị trả về của `PUBLISH` và kết quả introspection `PUBSUB NUMSUB` chỉ phản ánh **ngữ cảnh node**, không phải toàn Cluster. Với Redis 7.0+, sharded Pub/Sub phân phối thông điệp theo shard để giảm lưu lượng toàn Cluster, dùng `SSUBSCRIBE`/`SPUBLISH` riêng.

Ở tầng Spring, `RedisMessageListenerContainer` giúp quản lý subscription và phục hồi kết nối, nhưng **phục hồi subscription chỉ bảo đảm khả năng nhận các message mới** sau khi kết nối lại. Muốn đánh giá đúng hệ thống, hãy ghi eventId/sequence, tạo các kịch bản failover, xác nhận subscriber readiness, thống kê những event không quan sát được và thiết kế reconciliation hoặc durable messaging nếu mất event là không chấp nhận được.

## Tài liệu tham khảo

- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/): `PUBLISH`/`SUBSCRIBE`, at-most-once và sharded Pub/Sub.
- [Redis — PUBLISH](https://redis.io/docs/latest/commands/publish/): kết quả trả về và lưu ý chỉ đếm local-node subscriber trong Cluster.
- [Redis — PUBSUB NUMSUB](https://redis.io/docs/latest/commands/pubsub-numsub/): cách đếm subscriber theo node, không phải toàn Cluster.
- [Redis — Sharded Pub/Sub](https://redis.io/docs/latest/develop/pubsub/#sharded-pubsub): `SSUBSCRIBE`/`SPUBLISH` từ Redis 7.0.
- [Redis — Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/): master discovery, failover và các thông báo `+switch-master`.
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): phân chia slot và chuyển hướng node.
- [Spring Data Redis — Subscribing](https://docs.spring.io/spring-data/redis/reference/redis/pubsub-receiving.html): `RedisMessageListenerContainer`, `MessageListener` và subscription.
- [Spring Data Redis — Connection Modes](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html): Sentinel, Cluster và lưu ý về static master/replica.
- [Spring Data Redis API — RedisMessageListenerContainer](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/listener/RedisMessageListenerContainer.html): recovery, listener error handler và quản lý subscription.
- [Redis — Streams](https://redis.io/docs/latest/develop/data-types/streams/): mô hình stream cho dữ liệu cần replay và consumer groups.
