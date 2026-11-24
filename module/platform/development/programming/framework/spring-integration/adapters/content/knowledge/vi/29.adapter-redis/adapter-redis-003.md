# Redis store inbound adapter

## Mục tiêu học tập

Hoàn thành bài học, bạn có thể:

- Giải thích **Redis store inbound channel adapter** đưa một **Redis collection view** vào **Spring Integration MessageChannel** bằng cách **poll định kỳ**.
- Phân biệt rõ **RedisStoreMessageSource** với Redis **Pub/Sub inbound** và **Redis queue inbound**: một bên phát **view của store**, một bên nhận notification, bên còn lại pop phần tử.
- Liệt kê năm **CollectionType** được hỗ trợ: **LIST**, **SET**, **ZSET**, **PROPERTIES**, **MAP**, và chọn kiểu phù hợp.
- Cấu hình **RedisConnectionFactory**, **Redis.storeInboundChannelAdapter(...)**, **Pollers.fixedDelay(...)**, **MessageChannel**, transformer và service activator.
- Dùng **RedisZSet.rangeByScore(...)** để truy vấn các công việc đến hạn; hiểu vì sao một lần poll không đồng nghĩa một job đã được claim/ACK.
- Phân tích **key/key-expression**, serializer, snapshot so với live view, concurrent modifications, xử lý trùng và điều kiện dữ liệu bị xóa.
- Sử dụng **transaction synchronization** một cách đúng phạm vi; phân biệt after-commit callback với Redis/database transaction nguyên tử.
- Thiết kế checkpoint, idempotency, retry, lease/claim và phương án thay thế bằng **Redis Streams** hoặc durable work queue khi nhiệm vụ không được mất.
- Kiểm thử behavior khi store rỗng, dữ liệu thay đổi giữa hai lần poll, nhiều application replicas, mất kết nối và lỗi business.

## 1. Redis store inbound adapter giải quyết bài toán nào?

Giả sử một dịch vụ **ReminderService** lưu các tác vụ nhắc việc trong **Redis Sorted Set (ZSET)**. Mỗi member là một **jobId**, score là thời điểm được phép xử lý theo Unix epoch milliseconds:

~~~text
Key: reminders:{notify}:due

Member             Score (epoch milliseconds)
------------------------------------------------
reminder-1001      1795402800000
reminder-1002      1795403100000
reminder-1003      1795410000000
~~~

Ứng dụng muốn **định kỳ xem tập dữ liệu** và chọn các reminder đã đến hạn. Thay vì tự viết một scheduled method nối vào nhiều nghiệp vụ khác nhau, Spring Integration cung cấp **Redis store inbound channel adapter** để kết nối Redis store với một integration flow:

~~~mermaid
flowchart LR
    P["Reminder writer"] --> R[("Redis ZSET<br/>reminders:due")]
    T["Spring Integration Poller<br/>mỗi 2 giây"] --> I["RedisStoreMessageSource"]
    R -. "Bound collection view" .-> I
    I --> M["Spring Message<br/>payload: RedisStore"]
    M --> C["MessageChannel"]
    C --> Q["Query due members"]
    Q --> V["Validate / deduplicate"]
    V --> H["Reminder service"]
~~~

**Điểm dễ nhầm nhất:** Store inbound adapter **không mặc nhiên đọc, xóa và phát một phần tử mỗi lần poll**. Thành phần nền tảng **RedisStoreMessageSource** trả về một **RedisStore view gắn với key/collection**. Các bước tiếp theo quyết định **truy vấn những phần tử nào** và **có xóa/claim chúng hay không**.

Do đó Redis store inbound khác với:

- **Redis queue inbound adapter**: nhận item qua thao tác pop từ Redis List.
- **Redis Pub/Sub inbound adapter**: nhận message mà publisher gửi tới channel.
- **Redis Streams consumer**: đọc records có ID, retention, consumer groups và ACK riêng.

Bài học thuộc chương **Adapter Redis** trong module **SPRING_INTEGRATION_ADAPTERS**. Nội dung đặt Redis vào đúng mô hình inbound/outbound adapter, gateway, poller và MessageChannel, đồng thời chú trọng hợp đồng message, xử lý lỗi và vòng đời kết nối, tương tự khi tích hợp File, SFTP, HTTP, JMS, AMQP, Kafka và database.

## 2. Cơ chế thật: Poller → MessageSource → RedisStore view

Spring Integration sử dụng một **polling consumer** để gọi phương thức receive của message source theo lịch. Với Redis store, source có thể được biểu diễn bằng lớp:

~~~java
org.springframework.integration.redis.inbound.RedisStoreMessageSource
~~~

Luồng logic:

~~~mermaid
sequenceDiagram
    participant P as Poller
    participant S as RedisStoreMessageSource
    participant R as Redis
    participant C as MessageChannel
    participant H as Handler
    P->>S: receive()
    S-->>P: Spring Message<RedisStore view>
    P->>C: send(message)
    C->>H: Handle view
    H->>R: Query current members
    R-->>H: Members at query time
    Note over S,H: Không tự pop/ACK từng phần tử
~~~

### 2.1. View không phải snapshot

**RedisStore view** là một **đối tượng Java được gắn với dữ liệu Redis**; các lệnh như rangeByScore hoặc size có thể truy vấn Redis khi được gọi. Đừng coi nó là một bản snapshot bất biến chứa toàn bộ phần tử tại chính thời điểm poll.

Ví dụ:

~~~text
10:00:00.000  Poller nhận RedisZSet view
10:00:00.100  Publisher thêm reminder-X
10:00:00.200  Handler gọi rangeByScore(...)

Handler có thể nhìn thấy reminder-X, dù X chưa tồn tại khi poller bắt đầu.
~~~

Nếu handler giữ view trong một QueueChannel rồi xử lý vài giây sau, dữ liệu trong Redis có thể thay đổi thêm. Cần quyết định rõ **đọc hiện trạng**, **snapshot giá trị** hay **claim từng job**; chúng không đồng nghĩa.

### 2.2. Store inbound có thể phát message dù không có job mới

Một polling MessageSource cung cấp view vào store có thể phát message định kỳ, bất kể có phần tử mới hay không. Vì thế:

- **Mỗi poll không tương đương một dữ liệu mới**.
- Poller maxMessagesPerPoll không mặc nhiên là tối đa từng member trong Redis collection.
- Nếu handler xử lý toàn bộ members mỗi lần mà không có checkpoint, các members cũ có thể bị xử lý lặp.

Kiểm tra behavior cụ thể khi key chưa tồn tại hoặc store rỗng trên phiên bản thư viện đang dùng; **không dựa vào một poll liên tục để suy ra job mới được tạo**.

### 2.3. Đây là polled inbound, không phải message-driven queue

| Thành phần | Ai kích hoạt? | Dữ liệu nhận | Có cần Spring Integration poller? |
| --- | --- | --- | --- |
| **Redis store inbound** | Poller theo fixedDelay/fixedRate/trigger | RedisStore view | **Có** |
| **Redis queue inbound** | Endpoint loop chờ blocking POP | Một item đã pop | **Không**, với message-driven endpoint |
| **Redis Pub/Sub inbound** | Redis client listener callback | Một notification | **Không** |
| **HTTP inbound gateway** | Request từ client | Request, có thể cần reply | **Không** theo nghĩa Poller |

Đặt Pollers.fixedDelay(...) ở store inbound là đúng. Đặt cùng poller vào queue inbound message-driven rồi mong nó thêm ACK/replay là nhầm mô hình.

## 3. Năm loại Redis collection mà adapter hỗ trợ

Theo hợp đồng Redis Store Inbound, giá trị **collection-type** thuộc:

| CollectionType | Redis structure | Ví dụ sử dụng | Lưu ý |
| --- | --- | --- | --- |
| **LIST** | List | Danh sách jobs/logs đơn giản | View không tự pop một item |
| **SET** | Set | Tập sản phẩm cần reconcile | Không có thứ tự ổn định |
| **ZSET** | Sorted set | Jobs theo dueAt/priority score | Score hỗ trợ range query; cần claim an toàn |
| **PROPERTIES** | Property-like store | Key/value cấu hình nhỏ | Không mặc định biểu diễn một event |
| **MAP** | Hash/map | Trạng thái của các records | Live map, giá trị có thể đổi trong khi handler xử lý |

Trong Java, enum được khai báo bởi **RedisCollectionFactoryBean.CollectionType** của Spring Data Redis trong những phiên bản tương ứng.

### 3.1. RedisStore API do Spring Data Redis cung cấp

Lớp source trả về một payload kế thừa từ loại **RedisStore** của Spring Data Redis. Kiểu cụ thể phụ thuộc collection-type, chẳng hạn **RedisZSet** khi chọn ZSET.

Đừng cấu hình LIST rồi viết handler nhận RedisZSet. Nếu **Redis key thực tế** cũng là kiểu dữ liệu khác với cấu hình, Redis có thể trả lỗi **WRONGTYPE** khi truy vấn.

### 3.2. LIST khác Redis queue inbound

Ở **store inbound với CollectionType.LIST**, payload là **view** của List. Handler có thể duyệt/truy vấn hoặc chủ động xóa phần tử theo hợp đồng riêng.

Ở **Redis queue inbound**, endpoint thường thực hiện blocking POP để trả **item**. Vì vậy việc chọn **LIST** ở store inbound không làm nó trở thành một queue consumer tự ACK hoặc tự xóa item.

### 3.3. SET không có ordering

SET hữu ích nếu muốn lưu một tập IDs cần quét và không cần thứ tự. Nhưng khi hai workers cùng duyệt SET, họ có thể đọc trùng cùng members. Muốn một worker chịu trách nhiệm xử lý một ID, phải dùng atomic claim/lock/idempotency hoặc mô hình dữ liệu phù hợp.

### 3.4. ZSET có score, nhưng score chưa phải acknowledgment

ZSET có thể sắp xếp reminders theo **dueAt** hoặc **priority**. Một lần **ZRANGEBYSCORE/rangeByScore** chỉ đọc tập phù hợp; nó không tự mark một job **PROCESSING** và cũng không loại bỏ job sau khi xử lý.

### 3.5. PROPERTIES và MAP

Hai kiểu này hữu ích khi cần tham chiếu **những thuộc tính/config/state** trong Redis và đi qua flow để kiểm tra/đối chiếu. Chúng không phải message log có per-item ACK. Khi dùng hash/map, cần nghĩ tới **consistency** và **serializer của hash keys/values**.

## 4. Khi nào nên chọn Redis store inbound?

| Bài toán | Có phù hợp? | Vì sao |
| --- | --- | --- |
| Định kỳ kiểm tra dữ liệu Redis ZSET đến hạn | **Có**, nếu tự thiết kế claim/checkpoint | Poller truy cập view và query range |
| Quét Redis SET để reconcile với database | **Có** | Tự xác định members mới/đã xử lý |
| Theo dõi trạng thái MAP/PROPERTIES theo lịch | **Có** | Quan sát view tại thời điểm query |
| Nhận từng Redis Pub/Sub notification | **Không** | Dùng Redis Pub/Sub inbound |
| Lấy từng job FIFO bằng blocking List POP | **Không nên dùng store inbound như queue tự pop** | Dùng Redis queue inbound phù hợp |
| Đòi hỏi consumer groups, pending/ACK/replay | **Không mặc định có** | Dùng Redis Streams hoặc broker hỗ trợ |
| Làm một tác vụ phải hoàn thành chính xác một lần | **Không đủ nếu chỉ cấu hình adapter** | Cần transactional/idempotent business design |

**Câu hỏi thiết kế:** Bạn muốn **quan sát và xử lý một tập dữ liệu** hay **lấy quyền sở hữu một công việc duy nhất**? Câu trả lời quyết định liệu store inbound/poller có thích hợp hơn một consumer group/work queue hay không.

## 5. Thiết kế hợp đồng dữ liệu cho ZSET reminder

Để hiểu source và handler, ta dùng một bài toán cụ thể: **quét reminders đến hạn** trong Redis ZSET. Mỗi member là **ID ổn định**, score là thời gian đến hạn, còn thông tin reminder nằm trong nguồn dữ liệu chuẩn.

~~~text
ZSET: reminders:{notify}:due
  reminder-1001 -> 1795402800000.0
  reminder-1002 -> 1795403100000.0

Database / domain API:
  reminder-1001 -> tenant T1, recipient R1, status PENDING
  reminder-1002 -> tenant T2, recipient R2, status PENDING
~~~

**Tại sao nên để ZSET member là jobId?** Nếu nhét một JSON dài trực tiếp làm member, việc cập nhật/removal theo ID, đối chiếu và phân quyền khó hơn. Một member ID ngắn giúp:

- Deduplicate theo jobId.
- Dùng unique constraint trong bảng trạng thái.
- Lấy thông tin nghiệp vụ mới nhất từ database.
- Không lưu PII quá lâu trong Redis ZSET.
- Giảm rủi ro deserialize một payload không được tin cậy.

### 5.1. Score là thời điểm hay priority?

ZSET chỉ biết số điểm **double**, không biết ý nghĩa nghiệp vụ. Nếu dùng epoch milliseconds:

~~~text
score = dueAtEpochMillis
due   = score <= nowEpochMillis
~~~

Nếu dùng priority, score nhỏ nhất có thể là công việc ưu tiên cao nhất hoặc ngược lại theo hợp đồng. Không tái sử dụng một ZSET với hai quy tắc score khác nhau nếu không có schema/version rõ.

### 5.2. Thời gian và múi giờ

Với lịch nhắc việc, application phải quy đổi thời gian domain sang **Instant/UTC epoch milliseconds** trước khi ghi score. Không đặt score bằng chuỗi giờ địa phương như 09:00 và suy rằng ZSET tự hiểu Asia/Ho_Chi_Minh hoặc DST.

**Tránh phụ thuộc vào thời gian client không đồng bộ** nếu hệ thống nhiều nodes: cần đồng bộ clock/NTP và quyết định policy cho scheduling drift. Các khoảng milliseconds hiện nay nằm trong giới hạn số nguyên biểu diễn chính xác của double, nhưng luôn xác minh range, overflow và contract đơn vị giây/milliseconds.

### 5.3. Trạng thái nghiệp vụ ở nguồn tin cậy

Ví dụ bảng database:

~~~text
reminder_jobs
  job_id          VARCHAR PRIMARY KEY
  tenant_id       VARCHAR
  due_at          TIMESTAMP UTC
  status          PENDING / PROCESSING / SENT / CANCELLED
  version         BIGINT
  attempts        INTEGER
  updated_at      TIMESTAMP UTC
~~~

Redis ZSET trong tình huống này có thể là một **index hỗ trợ tìm kiếm jobs đến hạn**. Khi ZSET bị mất hoặc stale, database giúp rebuild. Nếu Redis là nguồn duy nhất cho job, yêu cầu bảo đảm lưu bền và claim sẽ cao hơn nhiều.

### 5.4. Tránh ghi lại toàn bộ PII trong member

Không đặt email, access token, URL signed hoặc nội dung riêng tư trong ZSET member chỉ vì rangeByScore trả về String dễ dàng. Lưu **ID** rồi truy vấn dữ liệu có phân quyền tại handler.

## 6. Chuẩn bị dependencies và Redis connection

Ví dụ dựa trên Spring Boot với Spring Integration Redis và Spring Data Redis:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-redis</artifactId>
    </dependency>
</dependencies>
~~~

Sử dụng **Spring Boot BOM/dependency management** để bảo đảm Spring Integration, Spring Data Redis và Redis client cùng hệ phiên bản. Một số API Java DSL, serializer và transaction synchronization có thể khác theo thế hệ library; ví dụ cần được biên dịch và kiểm thử bằng version thực tế trước production.

Ví dụ local/test:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 3s
      timeout: 3s
~~~

Trong production phải có credential management, ACL, TLS, timeout và topology Sentinel/Cluster phù hợp. Redis không có virtual host giống RabbitMQ: xác định đúng **Redis instance/database index/namespace** và key ownership. Các thế hệ Spring Boot khác nhau có thể dùng key cấu hình khác nhau, cần kiểm tra version.

### 6.1. RedisConnectionFactory không tự tạo một store inbound flow

RedisConnectionFactory cung cấp kết nối; **RedisStoreMessageSource** chọn Redis key/type và **Poller** kích hoạt receive; **MessageChannel** nối tới transformer/service activator. Thiếu poller, một MessageSource chưa tự chạy theo lịch.

### 6.2. Không kết hợp hai cách khởi tạo template trong cùng endpoint

Store inbound có thể dùng **RedisConnectionFactory** để tự tạo template mặc định hoặc **RedisTemplate** đã cấu hình serializer. Trong XML/DSL có các lựa chọn tương ứng; **không cùng lúc chỉ định cả redis-template và connection-factory cho cùng source** nếu API không hỗ trợ.

### 6.3. Serializer phải khớp dữ liệu đã lưu

Theo cơ chế mặc định của source tạo từ RedisConnectionFactory, **StringRedisTemplate** được dùng với **StringRedisSerializer** cho key/value/hash key/hash value trong các phiên bản tương ứng.

Nếu producer ghi dữ liệu bằng một RedisTemplate dùng **JDK serialization** hoặc JSON serializer khác, các giá trị khi đọc có thể không giải mã đúng. **Lỗi serializer không phải do poller quá chậm**; cần test read/write với cùng wire format.

## 7. Producer: ghi reminders vào Redis ZSET

Một producer mẫu ghi ID và due time bằng StringRedisTemplate:

~~~java
import java.time.Instant;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ReminderIndexWriter {

    public static final String DUE_KEY =
        "reminders:{notify}:due";

    private final StringRedisTemplate redisTemplate;

    public ReminderIndexWriter(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public void schedule(String jobId, Instant dueAt) {
        if (jobId == null
                || !jobId.matches("[A-Za-z0-9_-]{1,80}")
                || dueAt == null) {
            throw new IllegalArgumentException(
                "Invalid reminder index entry");
        }

        redisTemplate.opsForZSet().add(
            DUE_KEY,
            jobId,
            (double) dueAt.toEpochMilli());
    }
}
~~~

**Điều hàm này làm:** đặt một member jobId với score dueAt vào ZSET. Redis ZSET không tự phát notification tới store inbound adapter; poller sẽ truy cập store theo lịch. **Boolean trả về của ZADD** hay trạng thái ghi thành công cũng không chứng minh reminder đã được gửi.

### 7.1. Dữ liệu test bằng Redis CLI

Trong Redis test riêng:

~~~bash
redis-cli ZADD reminders:{notify}:due 1795402800000 reminder-1001
redis-cli ZADD reminders:{notify}:due 1795403100000 reminder-1002
redis-cli ZRANGEBYSCORE reminders:{notify}:due -inf +inf WITHSCORES
~~~

Không dùng DEL/FLUSHDB trên Redis production để làm lab. Để test jobs “đến hạn”, nên tạo scores theo thời điểm test đang chạy; các số cố định trong ví dụ chỉ minh họa cấu trúc.

### 7.2. ZADD và transaction nghiệp vụ

Nếu database lưu reminder đã commit nhưng Redis ZADD thất bại, ZSET index có thể thiếu một job. Nếu Redis ZADD trước rồi database rollback, ZSET có thể chứa ID không còn hợp lệ.

Khi Redis chỉ là một index được rebuild, dùng periodic reconciliation theo database. Nếu index bắt buộc đồng bộ ngay, cần thiết kế **outbox/change capture**, trạng thái cập nhật và phép kiểm tra nhất quán. Không nói rằng @Transactional trên JDBC tự rollback Redis ZADD.

### 7.3. Không dùng ZSET score làm dấu đã ACK

Một job dueAt cũ vẫn nằm trong ZSET thì các lần poll sau vẫn có thể trả lại job đó. Redis không thay score/xóa member chỉ vì Spring Integration handler đã chạy. Nếu muốn cập nhật trạng thái, ứng dụng phải chọn hành động rõ ràng: **remove**, đổi score, move sang processing, hoặc checkpoint ở database.

## 8. Java DSL: Redis store inbound với Pollers.fixedDelay

Đây là cách cấu hình trực tiếp **Redis store inbound channel adapter**, dùng factory Java DSL hỗ trợ trong Spring Integration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.support.collections.RedisCollectionFactoryBean.CollectionType;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.redis.dsl.Redis;

@Configuration
@EnableIntegration
public class ReminderStoreInboundConfig {

    @Bean
    public IntegrationFlow reminderStoreInboundFlow(
            RedisConnectionFactory redisConnectionFactory,
            ReminderStoreObserver observer) {

        return IntegrationFlow
            .from(Redis.storeInboundChannelAdapter(
                    redisConnectionFactory,
                    ReminderIndexWriter.DUE_KEY)
                    .collectionType(CollectionType.ZSET),
                endpoint -> endpoint
                    .poller(Pollers.fixedDelay(2000)
                        .maxMessagesPerPoll(1))
                    .id("reminderStorePoller"))
            .handle((payload, headers) -> {
                observer.observe(payload);
                return null;
            })
            .get();
    }
}
~~~

### 8.1. Import và version

DSL factory **Redis.storeInboundChannelAdapter(...)** và **Pollers.fixedDelay(...)** được mô tả trong tài liệu Spring Integration tương ứng. Kiểu **CollectionType** thuộc lớp RedisCollectionFactoryBean của Spring Data Redis. Khi package/API thay đổi theo phiên bản, kiểm tra thư viện thực tế thay vì suy một setter không tồn tại.

### 8.2. Observer không nên xử lý lặp toàn bộ store

~~~java
import org.springframework.data.redis.support.collections.RedisStore;
import org.springframework.stereotype.Service;

@Service
public class ReminderStoreObserver {

    public void observe(Object payload) {
        if (!(payload instanceof RedisStore)) {
            throw new IllegalArgumentException(
                "Expected a RedisStore view");
        }

        // Trong lab: ghi nhận source đã đưa một view vào flow.
        // Không coi poll này là một job đã được claim.
    }
}
~~~

**Mục đích ví dụ đầu tiên:** chứng minh integration endpoint phát **RedisStore view** và poller được kích hoạt. Để chọn đúng reminder đến hạn, chuyển sang handler dùng **RedisZSet.rangeByScore(...)** ở mục sau.

### 8.3. maxMessagesPerPoll(1) không phải giới hạn một job

Ở ví dụ:

- Poller gọi source nhận một **message chứa RedisStore view**.
- Handler có thể query **0, 10 hoặc hàng nghìn** members.
- Vì vậy maxMessagesPerPoll(1) **không giới hạn số members** được handler lấy ra.

Nếu xử lý một batch lớn, cần giới hạn ở **range query hoặc application batching**, không chỉ ở cấu hình số lần receive của poller.

### 8.4. Không dùng một QueueChannel vô hạn để lưu view

Nếu bạn thêm QueueChannel sau source:

~~~text
Poll 1 -> RedisZSet view A -> QueueChannel
Poll 2 -> RedisZSet view B -> QueueChannel
Poll 3 -> RedisZSet view C -> QueueChannel
~~~

Cả ba views có thể cùng trỏ về **cùng Redis key** và khi được consume sau đó chúng có thể nhìn thấy hiện trạng tương tự, không phải ba snapshots độc lập. Đệm views không tạo event history hoặc backlog theo thời điểm poll.

## 9. Java annotation: RedisStoreMessageSource và @InboundChannelAdapter

Ngoài Java DSL, bạn có thể khai báo MessageSource trực tiếp bằng annotation:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.support.collections.RedisCollectionFactoryBean.CollectionType;
import org.springframework.expression.common.LiteralExpression;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.redis.inbound.RedisStoreMessageSource;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class ReminderStoreAnnotationConfig {

    @Bean
    public MessageChannel reminderStoreViews() {
        return new DirectChannel();
    }

    @Bean
    @InboundChannelAdapter(
        channel = "reminderStoreViews",
        poller = @Poller(fixedDelay = "2000"))
    public RedisStoreMessageSource reminderStoreSource(
            RedisConnectionFactory redisConnectionFactory) {

        var source = new RedisStoreMessageSource(
            redisConnectionFactory,
            new LiteralExpression(ReminderIndexWriter.DUE_KEY));

        source.setCollectionType(CollectionType.ZSET);
        return source;
    }
}
~~~

**Hai cách cấu hình là thay thế nhau:** Đoạn này và Java DSL ở mục 8 cùng mô tả **một store source được poll theo lịch**. Nếu đưa cả hai vào một ApplicationContext, chúng sẽ tạo **hai pollers** trên cùng Redis key, dễ gọi cùng business handler nhiều lần. Chọn một cách cho một use case, hoặc tách key/consumer ownership thật rõ.

### 9.1. Vì sao dùng LiteralExpression?

**keyExpression** được đánh giá khi source nhận dữ liệu. Nếu tên key cố định, **LiteralExpression** làm ý định rõ ràng và tránh việc một giá trị trông như SpEL lại bị diễn giải thành expression.

### 9.2. Khi nào dùng SpEL key-expression động?

Khi cần chọn store key theo thời điểm/environment/tenant đã kiểm soát. Tuy nhiên, source nhận message theo poller nên không có một user request payload để tùy ý chọn key theo từng phần tử. Expression dynamic có thể được đánh giá lại qua các polls, gây thay đổi source đột ngột nếu biến cấu hình thay đổi.

Nếu keyExpression lấy từ nguồn không tin cậy, phải có allowlist và tenancy validation; không để người dùng nhập tùy ý tên Redis key để process đọc store nội bộ.

### 9.3. Không dùng annotation method để vừa nhận vừa xóa toàn bộ collection

Method được annotation trả về **MessageSource**. Nó không phải business handler thực hiện từng job. Xóa tất cả members mỗi lần source được poll sẽ làm mất khả năng phân loại due/undue, lỗi transient, concurrency và recovery.

## 10. Xử lý RedisZSet view để đọc members đến hạn

Để làm việc với đúng kiểu store, handler có thể nhận **RedisZSet** và gọi **rangeByScore**. Ví dụ sau dùng Spring Integration service activator:

~~~java
import java.util.Set;

import org.springframework.data.redis.support.collections.RedisZSet;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Service;

@Service
public class ReminderDueInspector {

    @ServiceActivator(inputChannel = "reminderStoreViews")
    public void inspect(RedisZSet<String> view) {
        double nowMillis = (double) System.currentTimeMillis();

        Set<String> due = view.rangeByScore(
            Double.NEGATIVE_INFINITY, nowMillis);

        if (due == null || due.isEmpty()) {
            return;
        }

        // Chỉ quan sát trong ví dụ đầu tiên;
        // không giả định đây là các jobs đã claim.
        for (String jobId : due) {
            System.out.println("Candidate due reminder: " + jobId);
        }
    }
}
~~~

Code dùng output channel **reminderStoreViews** ở mục 9, không dùng thêm cùng handler vào flow Java DSL mục 8. Khi học, hãy chạy **một cấu hình** để quan sát và đo số callbacks.

### 10.1. Vì sao chọn ZSET cho bài toán này?

**rangeByScore(min, max)** chọn members có score trong khoảng. ZSET phù hợp cho reminder dueAt, rate-limit window hoặc các dữ liệu sắp xếp bằng score. Nhưng:

- **rangeByScore là thao tác đọc**, không claim.
- Nó có thể trả nhiều member, cần giới hạn batch khi dữ liệu lớn.
- Một job chưa bị xóa/đổi trạng thái sẽ tiếp tục xuất hiện ở poll sau.
- Nếu một producer sửa score cùng lúc, kết quả phụ thuộc thời điểm truy vấn.

### 10.2. Truy vấn chỉ ra candidates, không chứng minh đã gửi

~~~text
Poll 1: rangeByScore -> [reminder-1001, reminder-1002]
Poll 2: rangeByScore -> [reminder-1001, reminder-1002]
Poll 3: rangeByScore -> [reminder-1001, reminder-1002]
~~~

Nếu handler gửi email ngay trong vòng for mà không idempotency/checkpoint, cùng người nhận có thể nhận nhiều email. RedisStoreMessageSource không có bộ nhớ **reminder-1001 đã gửi**.

### 10.3. Đừng duyệt toàn bộ ZSET quá lớn

Một collection có một triệu members có thể gây:

- Redis command/serialization latency tăng.
- Memory pressure ở JVM khi materialize Set lớn.
- Poller bị giữ quá lâu, miss mục tiêu cadence.
- Handler reprocess cùng một tập.

Chỉ lấy những members đủ điều kiện và giới hạn kích thước batch; có thể dùng **RedisTemplate.opsForZSet().rangeByScore(key, min, max, offset, count)** hoặc API range tương thích phiên bản, sau khi thiết kế cách claim/recover đúng.

**Mẫu truy vấn khác bằng RedisTemplate là chiến lược của handler**, không thay đổi ngữ nghĩa store inbound adapter.

## 11. Poller: fixedDelay, fixedRate và maxMessagesPerPoll

Spring Integration Poller là bộ điều khiển **khi nào gọi source.receive()**.

| Cấu hình | Ý nghĩa | Rủi ro nếu hiểu sai |
| --- | --- | --- |
| **fixedDelay(2000)** | Khoảng nghỉ định kỳ giữa các lần thực thi theo trigger | Handler chậm có thể làm thời gian thực giữa polls dài hơn |
| **fixedRate** | Mốc lập lịch theo nhịp | Khi job chậm và executor concurrency, cần xét chồng lấn |
| **maxMessagesPerPoll(1)** | Giới hạn số message source được poll trong một lần trigger | Không giới hạn một member Redis trong view |
| **TaskScheduler** | Tài nguyên kích hoạt poller | Scheduler chung bão hòa có thể làm nhiều flows bị trễ |
| **receiveTimeout/sendTimeout** | Timeout tùy endpoint/channel | Không phải business retry/backoff hoặc ACK |
| **transactional/advice** | Advice bao quanh polling task | Không tạo distributed transaction Redis + DB |

### 11.1. Fixed delay không phải TTL của Redis ZSET

**Poller 2 giây** là tần suất kiểm tra. **Score dueAt** là điều kiện chọn member. Redis ZSET không tự đẩy member khi score đạt now; đến hạn chỉ có ý nghĩa nếu application/query dùng thời gian để so sánh.

### 11.2. Một poller trigger có thể xử lý nhiều jobs

Một RedisStore view có thể cho phép handler đọc 50 IDs trong một lần nhận. maxMessagesPerPoll(1) không tự giới hạn 50. Nếu muốn 10 jobs mỗi batch:

1. Chọn tối đa 10 candidates trong query.
2. Áp claim/lock/checkpoint cho từng candidate.
3. Ghi nhận success/failure riêng từng job.
4. Không xóa cả range chỉ vì 9/10 jobs thành công.

### 11.3. Poller vẫn có thể chạy khi store rỗng

Ở loại source trả về view, source có thể tạo một Spring Message dù ZSET không có member đến hạn. Nếu bạn đo **adapter receive count** như **processed jobs count**, dashboard sẽ sai. Chỉ tăng business success counter sau khi handler xác nhận hoàn tất công việc cụ thể.

### 11.4. Scheduler và thread model

Với **DirectChannel**, handler chạy đồng bộ theo đường gọi poller; nếu handler chậm, task poller có thể bị giữ lâu. Với **ExecutorChannel**, poller có thể gửi view vào executor rồi return, khiến công việc thật diễn ra sau. Transaction synchronization sau poller có thể **chạy trước khi handler async hoàn tất**, một nguy cơ nghiêm trọng khi dùng afterCommit để xóa dữ liệu.

Để cleanup sau kết quả nghiệp vụ, giữ xử lý **đồng bộ trong transaction boundary đã xác định**, hoặc tách thành một durable job state machine có ACK riêng.

## 12. Snapshot, live view và data races

Một cách nghĩ đúng:

~~~text
RedisStore view:
  "Đây là đối tượng cho phép thao tác với store X"

Không phải:
  "Đây là bản sao bất biến của toàn bộ store X lúc 10:00:00"
~~~

### 12.1. Hai lần query có thể khác nhau

~~~mermaid
sequenceDiagram
    participant H as Handler A
    participant R as Redis ZSET
    participant P as Producer
    H->>R: rangeByScore(0, now)
    R-->>H: [job-1, job-2]
    P->>R: ZADD job-3 dueAt=now
    H->>R: rangeByScore(0, now)
    R-->>H: [job-1, job-2, job-3]
~~~

Nếu handler cần xử lý **một tập xác định**, hãy materialize IDs trước, lưu batch/claim state và dùng các điều kiện idempotency. Không chuyển RedisStore view nguyên dạng qua HTTP/Kafka/SFTP rồi nghĩ nó là snapshot có thể serialize; nó gắn với Redis client và khả năng truy cập Redis ở thời điểm sau.

### 12.2. Tranh chấp khi nhiều pollers đọc cùng key

Hai replicas có thể cùng đọc:

~~~text
Node A: rangeByScore -> job-1, job-2
Node B: rangeByScore -> job-1, job-2
~~~

Nếu cùng gửi email, mỗi reminder có thể bị gửi hai lần. Sự khác nhau giữa **view** và **claim** là quyết định: một query chỉ đọc không phân phối quyền sở hữu riêng cho một worker.

### 12.3. Thay đổi member/score khi đang xử lý

Producer có thể **cancel** reminder hoặc đổi dueAt. Nếu handler chỉ đọc candidate ở t0 rồi gửi thông báo ở t1 mà không kiểm tra trạng thái mới, có thể gửi một reminder đã bị hủy hoặc chưa đến hạn theo lịch mới.

Hãy kiểm tra **status/version/dueAt** ở nguồn nghiệp vụ trước side effect cuối cùng, đặc biệt khi event có điều kiện thời gian quan trọng.

## 13. Transaction synchronization: trước và sau commit

Spring Integration hỗ trợ **transaction synchronization** cho poller, để thực hiện hành động phụ vào các thời điểm **beforeCommit**, **afterCommit** hoặc **afterRollback** của transaction context.

Ví dụ tài liệu Redis store inbound dùng một **Redis ZSET view** và **removeByScore(...)** trong biểu thức afterCommit. Ý tưởng logic:

~~~mermaid
sequenceDiagram
    participant P as Poller
    participant S as RedisStore view
    participant H as Business handler
    participant TX as Transaction context
    participant R as Redis
    P->>S: receive view
    P->>TX: Begin transaction advice
    P->>H: Process candidates
    H-->>P: Success
    P->>TX: Commit
    TX->>R: afterCommit cleanup (nếu cấu hình)
~~~

### 13.1. PseudoTransactionManager có nghĩa gì?

**PseudoTransactionManager** của Spring Integration có thể được dùng khi không có một real database transaction manager, nhằm cung cấp **transaction synchronization callbacks**.

Nó **không biến các thao tác Redis thành transaction nguyên tử**, không rollback một email đã gửi, và không kết hợp Redis ZSET update với JDBC/object storage thành distributed transaction.

### 13.2. Ví dụ minh họa cú pháp poller transaction

Theo dạng Java DSL, một flow có thể cấu hình poller transactional với synchronization factory:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.support.collections.RedisCollectionFactoryBean.CollectionType;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.redis.dsl.Redis;
import org.springframework.integration.transaction.PseudoTransactionManager;
import org.springframework.integration.transaction.TransactionSynchronizationFactory;

@Configuration
@EnableIntegration
public class ReminderStoreSyncFlow {

    @Bean
    public IntegrationFlow reminderStoreFlowWithSync(
            RedisConnectionFactory factory,
            TransactionSynchronizationFactory syncFactory,
            ReminderStoreObserver observer) {

        return IntegrationFlow.from(
            Redis.storeInboundChannelAdapter(
                    factory, ReminderIndexWriter.DUE_KEY)
                .collectionType(CollectionType.ZSET),
            endpoint -> endpoint.poller(
                Pollers.fixedDelay(2000)
                    .transactional(new PseudoTransactionManager())
                    .transactionSynchronizationFactory(syncFactory)))
            .handle((payload, headers) -> {
                observer.observe(payload);
                return null;
            })
            .get();
    }
}
~~~

**Đây là cấu hình thay thế** cho các cấu hình poller khác, không nên tạo đồng thời nhiều bean polling cùng một ZSET khi đang thử logic xử lý task. **TransactionSynchronizationFactory cần được khai báo riêng** và phải chứa một processor có callback cụ thể; không phải chỉ thêm dòng transactional là tự xóa members.

### 13.3. Biểu thức cleanup sau commit

Một ví dụ học cơ chế:

~~~text
afterCommit expression:
    payload.removeByScore(1, 3)
~~~

Ở đây payload **phải** là RedisZSet view tương thích; biểu thức yêu cầu xóa các members trong khoảng score 1..3. Đây là **minh họa API**, không phải chính sách production cho reminder đến hạn.

**Vì sao không copy nguyên mẫu này vào production?**

- afterCommit xóa **cả range**, có thể bao gồm members mới được thêm vào sau khi handler đọc candidates.
- Nếu trong range có 20 jobs mà chỉ 19 jobs xử lý thành công, xóa cả range có thể làm mất job thứ 20.
- Handler dùng ExecutorChannel có thể trả control sớm, khiến transaction context commit trước business hoàn tất.
- Nếu Redis cleanup lỗi sau DB commit, công việc đã xử lý có thể xuất hiện lại và cần idempotency.

**Khuyến nghị:** Cleanup theo **job ID đã claim và đã xử lý xong**, kiểm tra owner/version và bảo vệ duplicate. Dùng một nguồn trạng thái bền vững để phân biệt PENDING, PROCESSING, DONE, FAILED thay vì xóa rộng theo range.

### 13.4. Synchronization callbacks không thay Redis MULTI/EXEC

| Cơ chế | Bảo đảm chính | Không bảo đảm |
| --- | --- | --- |
| Spring transaction synchronization | Chạy callback trước/sau commit/rollback của transaction context | Redis operations tự rollback nếu không tham gia transaction thật |
| PseudoTransactionManager | Tạo cơ hội đồng bộ callbacks | JDBC+Redis+email atomicity |
| JDBC @Transactional | Atomicity của các thao tác trong DB transaction | Redis ZADD/ZREM tự rollback và HTTP API atomicity |
| Redis MULTI/EXEC | Nhóm lệnh Redis theo semantics Redis | Business code/database transaction ngoài Redis atomicity |
| Lua script Redis | Atomicity của các lệnh trên một server/shard trong script | End-to-end commit với object storage và database |

### 13.5. Khoảng lỗi sau DB commit

~~~text
Handler gửi notification, DB commit
  -> process crash trước afterCommit cleanup Redis
  -> ZSET vẫn giữ job
  -> poller sau đọc lại
  -> notification có thể được gửi lại
~~~

Vì vậy cần **idempotent side effects**, một trạng thái DONE có thể kiểm tra, và cơ chế reconcile cleanup. Không coi afterCommit cleanup là một ACK broker bền vững.

## 14. TransactionSynchronizationFactory hoạt động ra sao?

Trong các phiên bản Spring Integration hỗ trợ Java API tương ứng, một **TransactionSynchronizationFactory** tạo đối tượng đồng bộ cho mỗi transaction/poll. **ExpressionEvaluatingTransactionSynchronizationProcessor** có thể áp **SpEL expressions** hoặc gửi kết quả lên những channels sau commit/rollback.

Sơ đồ trách nhiệm:

~~~mermaid
flowchart TD
    POLL["Poller task"] --> ADVICE["Transaction advice"]
    ADVICE --> RECV["RedisStoreMessageSource.receive"]
    RECV --> HAND["Synchronous flow"]
    HAND --> DEC{"Transaction outcome"}
    DEC -->|"Commit"| AC["afterCommit callback"]
    DEC -->|"Rollback"| AR["afterRollback callback"]
    AC --> C["Optional cleanup / audit"]
    AR --> F["Optional failure record / alert"]
~~~

### 14.1. Phạm vi dữ liệu callback

RedisStoreMessageSource có thể đặt **RedisStore reference trong integration resource holder**, để synchronization processor truy cập store. Đây là cơ chế runtime cho callback, không phải một record bền vững tự lưu ở Redis.

### 14.2. Callback có thể làm gì an toàn?

Các lựa chọn tương đối dễ kiểm soát:

- Ghi metric/audit cho một batch đã xử lý.
- Đặt tín hiệu reconcile cho các job IDs cụ thể.
- Xóa theo ID/version đã được claim nếu logic xác minh ownership.
- Trả về thông tin kết quả cho một **dedicated channel** sau commit.

Cần thận trọng với:

- Xóa toàn bộ rangeByScore không xác minh từng item.
- Phát message tới hệ thống khác mà không xử lý kết quả publish UNKNOWN.
- Gọi network trong afterCommit rồi giả định rollback DB được nếu call thất bại.
- Sử dụng thông tin ThreadLocal transaction sau khi flow đã chuyển sang thread bất đồng bộ.

### 14.3. Nếu không có real transaction?

PseudoTransactionManager chỉ mở ra callbacks, **không tạo một giao dịch durable**. Nếu nghiệp vụ bắt buộc có atomicity, cần một database transaction thật cùng outbox hoặc một quy trình claim/ACK bền vững. Không thể “bật transaction trên poller” để biến mọi Redis collection thành message broker exactly-once.

### 14.4. Error flow có thể ảnh hưởng transaction outcome

Nếu handler ném exception nhưng error flow hấp thụ và trả về bình thường, transaction advice có thể coi poll thành công tùy configuration, dẫn đến **afterCommit được gọi** dù nghiệp vụ thực tế chưa hoàn tất. Test phải kiểm tra cách exception lan truyền và đường outcome thay vì chỉ thấy error log.

### 14.5. Khi nào không cần synchronization?

Nếu store inbound chỉ dùng để **đọc trạng thái theo lịch, so sánh metric hoặc reconcile các IDs** mà không sửa Redis trong poll, có thể không cần transaction synchronization. Thêm cơ chế transaction vào một flow read-only không tự nâng độ tin cậy và có thể làm code khó hiểu hơn.

## 15. Xác thực key-expression, collection type và serializer

Store source gắn vào Redis key được chỉ định. Key có thể là literal hoặc expression được đánh giá khi nhận dữ liệu.

### 15.1. Key literal

~~~java
new RedisStoreMessageSource(
    redisConnectionFactory,
    new LiteralExpression("reminders:{notify}:due"));
~~~

Với key cố định, cách này đơn giản, dễ debug và tránh việc một expression tham chiếu ngầm đến bean/context không mong đợi.

### 15.2. Key-expression động

Một key-expression được đánh giá **mỗi lần source.receive()**. Nếu expression có thể đổi giữa các lần poll, một endpoint có thể lần lượt đọc:

~~~text
Poll 1 -> reminders:{notify}:due:current
Poll 2 -> reminders:{notify}:due:previous
Poll 3 -> reminders:{notify}:due:current
~~~

Đây có thể là một kỹ thuật có chủ đích, nhưng dễ gây bỏ sót/đọc trùng nếu đổi key không kèm checkpoint và provenance. Đừng thay tên key dựa trên raw user input hoặc một tenant header không xác thực.

### 15.3. WRONGTYPE và serializer mismatch

Nếu key đang chứa Redis String nhưng source cấu hình ZSET, thao tác range sẽ lỗi WRONGTYPE. Nếu producer ghi bytes bằng JDK serializer còn source mặc định là StringRedisTemplate, member có thể bị giải mã sai hoặc không đúng contract.

Checklist kiểm tra:

1. Redis instance/database/key có đúng không?
2. **TYPE key** trả zset/list/set/hash như dự kiến không?
3. RedisTemplate source đang dùng serializer nào cho key/value/hash?
4. Producer có cùng serialization contract không?
5. Có một thành phần khác đang ghi đè key với Redis structure khác không?

### 15.4. MAP và PROPERTIES cần hash serializers nhất quán

Với Redis hash/map, các **field names và values** có serializer riêng. Không chỉ cấu hình value serializer rồi bỏ qua hashKeySerializer/hashValueSerializer. Đừng dùng JDK native serialization với dữ liệu đến từ nhiều service không tin cậy.

### 15.5. Redis key naming và Cluster hash tag

Ví dụ **reminders:{notify}:due** có hash tag notify, hữu ích nếu thiết kế sau này cần multi-key atomic commands trong Redis Cluster với các key cùng slot. Nhưng **chỉ có hash tag không khiến polling/claim của nhiều application replicas trở thành atomic**; vẫn phải có thuật toán ownership.

## 16. Từ “due candidates” đến “đã claim job”: hai bài toán khác nhau

Store inbound giúp **tìm những phần tử có thể xử lý**, nhưng với nhiều pollers/workers, bạn cần bước **claim** riêng trước khi side effect.

~~~mermaid
flowchart TD
    Z["ZSET due index"] --> POLL["Store inbound poller"]
    POLL --> R["rangeByScore(..., now)"]
    R --> C{"Claim jobId thành công?"}
    C -->|"Không"| SKIP["Bỏ qua: worker khác sở hữu"]
    C -->|"Có"| V["Validate status/version"]
    V --> H["Business handler"]
    H --> S{"Kết quả?"}
    S -->|"Success"| ACK["Persist DONE + cleanup index"]
    S -->|"Transient error"| RETRY["Durable retry / lease expiry"]
    S -->|"Permanent error"| DEAD["Final failed state"]
~~~

### 16.1. Read-check-write không nguyên tử

Mẫu sai:

~~~text
Worker A: EXISTS job in ZSET -> true
Worker B: EXISTS job in ZSET -> true
Worker A: send reminder
Worker B: send reminder
Worker A: ZREM
Worker B: ZREM
~~~

**ZREM sau khi gửi** không ngăn hai workers cùng gửi. Cần **claim nguyên tử** trước side effect hoặc một kho idempotency/status có unique constraint/fencing.

### 16.2. Claim bằng database state

Nếu database là source of truth, một thiết kế:

~~~sql
-- Pseudo SQL: thay đổi theo database/schema/locking thực tế.
UPDATE reminder_jobs
SET status = 'PROCESSING',
    lease_owner = :worker,
    lease_until = :deadline,
    version = version + 1
WHERE job_id = :jobId
  AND status = 'PENDING'
  AND due_at <= CURRENT_TIMESTAMP
  AND version = :expectedVersion;
~~~

Affected rows = 1 nghĩa là một worker claim được theo điều kiện hiện tại. Affected rows = 0 nghĩa là worker khác đã thay đổi hoặc job đã không còn eligible. Cần transaction và kiểm tra version/status theo nguồn tin cậy.

### 16.3. Lệnh ZREM có thể dùng để claim không?

Nếu chỉ cần một worker xóa member và không cần recovery sau crash, một thao tác nguyên tử như **ZREM** có thể giúp tránh hai workers cùng xóa thành công. Nhưng nếu **xóa member trước business commit**, crash có thể làm mất job khỏi index.

Vì thế:

- Xóa để claim có thể tránh double claim ở Redis.
- Nó **không tự là ACK** chứng minh job hoàn tất.
- Cần processing state/lease và khả năng phục hồi.

### 16.4. ZPOPMIN không tự kiểm tra dueAt

**ZPOPMIN** lấy phần tử score nhỏ nhất, **kể cả khi score đó là một thời điểm tương lai**. Nếu chỉ được claim jobs đã đến hạn, cần check cutoff trong một thao tác phối hợp nguyên tử, chẳng hạn Lua script có validation, hoặc dùng database conditional claim.

Đừng gọi ZPOPMIN rồi “đẩy lại nếu chưa due” mà không xét unknown outcome, ordering và race.

### 16.5. Atomic claim bằng Lua: ý tưởng

Mẫu logic sau chọn tối đa một due job và chuyển từ due ZSET sang processing ZSET trong cùng Redis server/hash slot.

~~~lua
-- KEYS[1] = due ZSET
-- KEYS[2] = processing ZSET
-- ARGV[1] = nowEpochMillis
-- ARGV[2] = leaseDeadlineEpochMillis

local candidates = redis.call(
    'ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, 1)

if #candidates == 0 then
    return nil
end

local member = candidates[1]
local removed = redis.call('ZREM', KEYS[1], member)
if removed == 1 then
    redis.call('ZADD', KEYS[2], ARGV[2], member)
    return member
end
return nil
~~~

**Giới hạn của ví dụ:** Script nguyên tử về thao tác trên Redis shard liên quan, nhưng không tự:

- Gắn owner, fencing token hoặc attempt count.
- Giữ lịch sử dueAt gốc (nếu cần, lưu job registry).
- Kiểm tra member không đang PROCESSING từ vòng trước.
- Chứng minh script đã được lưu bền qua mọi failover/RPO.
- Đảm bảo email/object storage/database side effect đã commit.

Nếu cùng một member được producer đưa vào due lần nữa khi đang processing, phải có contract chống duplicate/fencing. Không copy script đơn giản này vào production mà không hoàn thiện state machine.

### 16.6. Polling view và worker claim có thể tách rời

RedisStoreMessageSource có thể:

1. Kích hoạt việc kiểm tra store theo lịch.
2. Đo backlog/candidates.
3. Gọi **claim service** dùng Redis Lua hoặc database conditional claim.
4. Chỉ gửi **claimed job IDs** tới worker flow.

Như vậy **inbound adapter vẫn giữ đúng vai trò store polling**, còn lớp claim chịu trách nhiệm phân phối quyền sở hữu. Không chuyển nguyên RedisStore view sang executor và coi dispatch đã đồng nghĩa claim.

## 17. Retry và lease: phục hồi khi worker gặp sự cố

Một job PROCESSING có thể không hoàn tất vì worker crash, mất kết nối, timeout hoặc phụ thuộc ngoài hỏng. Muốn retry sau restart, cần **durable attempt state** và **lease/reclaimer**.

### 17.1. State machine tối thiểu

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> PROCESSING: claim thành công
    PROCESSING --> DONE: business committed
    PROCESSING --> RETRY_WAIT: lỗi transient
    PROCESSING --> FAILED: lỗi permanent / max attempts
    PROCESSING --> RETRY_WAIT: lease expired + reclaimer
    RETRY_WAIT --> PENDING: nextAttemptAt đã đến
    DONE --> [*]
    FAILED --> [*]
~~~

### 17.2. Vì sao lease quá ngắn nguy hiểm?

~~~text
Worker A: claim reminder-1001; lease 5 giây
Worker A: gọi email provider, mất 8 giây
Reclaimer: sau 5 giây coi A chết, cho B claim lại
Worker B: cũng gọi email provider
~~~

Nếu cả A và B có thể gửi cùng reminder, business side effect bị lặp. Cần:

- Heartbeat/lease extension cho công việc lâu.
- Fencing token hoặc version để owner cũ không ghi trạng thái mới.
- Provider-side idempotency key nếu có.
- Trạng thái DONE và unique eventId khi commit.
- Reclaimer có delay và chính sách xử lý UNKNOWN outcomes.

### 17.3. Retry budget có phạm vi nào?

Phải phân biệt:

- **Attempt trong JVM**: RetryTemplate có thể retry ngắn trong một handler call.
- **Delivery/claim attempt bền vững**: nhiều lần claim sau crash hoặc lease expiry.
- **Publish attempt**: producer ghi lại dữ liệu vào Redis.
- **Business side effect attempt**: một lần gọi provider có thể đã thành công dù response timeout.

Không dùng mỗi RetryTemplate.maxAttempts(3) để tuyên bố đã giới hạn tổng số email gửi qua nhiều lần restart.

### 17.4. Backoff/nextRetryAt

Có thể dùng **Redis ZSET score = nextRetryAt** để giữ delayed jobs, trong khi **database/job state table** lưu attempts/owner/errorCategory. Một scheduler chuyển job khi đến hạn, có giới hạn attempts và final failed state.

**Store inbound poller không tự thay score hoặc tự đưa job về pending sau lỗi**. Mọi cập nhật state là trách nhiệm của handler/claim/reclaimer design.

### 17.5. Poison job

Job sai schema, thiếu tenant, destination email không hợp lệ hoặc object key không được phép thường không tự sửa sau mỗi retry. Nếu cứ giữ nó trong ZSET due mà không cập nhật trạng thái, **poller có thể thấy job đó mỗi 2 giây mãi mãi**.

Phải phân loại:

| ErrorCategory | Có retry? | Hành động |
| --- | --- | --- |
| INVALID_SCHEMA | Không | Final FAILED + audit |
| UNSUPPORTED_VERSION | Thường không ngay | Alert, xử lý compatibility |
| PERMISSION_DENIED | Không retry nóng | Sửa policy/config, điều tra |
| PROVIDER_TIMEOUT | Có giới hạn | Retry with backoff + idempotency |
| DB_UNAVAILABLE | Có giới hạn | Backoff/circuit breaker |
| UNKNOWN_PROVIDER_RESULT | Cần đối soát | Check status trước khi gửi lại |

### 17.6. Khi nào dùng Redis Streams thay ZSET + custom lease?

Nếu yêu cầu là **mỗi event có record ID, consumer groups, pending và reclaim**, Redis Streams cung cấp các khái niệm tương ứng. ZSET phù hợp cho **due-time index/scheduling**, nhưng không mặc nhiên là một message log.

Một kiến trúc có thể dùng:

~~~text
ZSET due index -> claim scheduler -> Redis Stream / durable broker
                                   -> consumer group -> business handler
~~~

Tuy nhiên bước ZSET → Stream vẫn cần **atomic handoff, duplicate protection và recovery**; không có exactly-once tự sinh chỉ vì hai cấu trúc cùng ở Redis.

## 18. Idempotency và transaction của business service

Với ReminderService, một jobId có thể được xử lý lại vì:

- Hai pollers cùng nhìn thấy candidate.
- Claim lease hết hạn và reclaimer cho worker khác nhận.
- Worker commit thành công nhưng chết trước cleanup.
- Producer schedule lại cùng ID.
- Operator replay failed task.

### 18.1. Bảng jobs có unique key

~~~text
reminder_jobs
    job_id         PRIMARY KEY
    business_key   UNIQUE (nếu contract yêu cầu)
    status         PENDING/PROCESSING/DONE/FAILED
    lease_owner
    lease_until
    version
    attempt_count
    result_id
    updated_at
~~~

**Unique constraint** trên jobId hoặc business key bảo vệ khỏi race giữa hai workers. Một check-then-insert thiếu constraint không đủ khi concurrency.

### 18.2. Hai cửa sổ crash đối lập

~~~text
Tình huống A:
  Xóa/ACK Redis job trước khi gửi hoặc commit nghiệp vụ.
  -> Process crash.
  -> Có thể mất công việc.

Tình huống B:
  Provider/DB đã commit.
  -> Process crash trước khi cleanup Redis / mark DONE.
  -> Job được xử lý lại.
  -> Có thể tạo duplicate nếu không idempotent.
~~~

Đừng tuyên bố @Transactional bao cả Redis, email provider, object storage và JDBC thành một giao dịch. Với external APIs, cần idempotency key, outbox, reconciliation và trạng thái UNKNOWN.

### 18.3. Fencing token/optimistic version

Nếu lease owner A hết hạn nhưng vẫn hoàn tất muộn, B có thể đã claim cùng job. **Fencing token** tăng dần theo lượt claim giúp hệ thống đích hoặc database từ chối update từ owner có token cũ.

Tuy nhiên fencing chỉ hữu ích **nếu nơi có side effect thực sự kiểm tra token**. Ghi token vào log mà provider không enforce sẽ không chống duplicate.

### 18.4. Đồng bộ hóa Redis index sau business commit

Sau khi job DONE:

1. Ghi business result và trạng thái DONE trong nguồn bền vững.
2. Cleanup ZSET member đúng jobId/version theo policy.
3. Nếu cleanup Redis thất bại, poll sau nhìn thấy jobId nhưng handler kiểm tra DB DONE và skip.
4. Periodic reconciliation sửa index stale.

Cách này ưu tiên **không mất business state**, chấp nhận đọc lại candidate để dọn index. Nó thường dễ vận hành hơn xóa rộng cả score range và hy vọng không có race.

### 18.5. Nếu Redis là nguồn dữ liệu duy nhất?

Khi không có DB/outbox/stream và không thể rebuild ZSET, phải đánh giá:

- Redis persistence/failover RPO/RTO.
- Atomic claim và processing store.
- Unique IDs và transaction ownership.
- Recovery khi crash, retry và final failed state.
- Retention/eviction, memory pressure, backup/restore.

Chỉ một store inbound adapter với poller **không đáp ứng hết những yêu cầu này**.

## 19. Vòng đời endpoint, Redis outage và graceful shutdown

Store inbound là **polling endpoint**, nên có các trạng thái:

~~~mermaid
flowchart TD
    S["Application startup"] --> E["Initialize Redis store source"]
    E --> P["Start poller"]
    P --> Q{"Redis available?"}
    Q -->|"Có"| R["Receive RedisStore view"]
    R --> H["Query + business flow"]
    H --> P
    Q -->|"Không"| ERR["Error / recovery strategy"]
    ERR --> P
    P -->|"Shutdown"| STOP["Stop scheduling polls"]
    STOP --> DRAIN["Finish / recover in-flight work"]
~~~

### 19.1. Auto-startup và phase

Spring Integration endpoints có lifecycle/start-stop conventions. Có thể dùng **autoStartup** và **phase** khi cần phối hợp thứ tự khởi động nhiều thành phần.

Tuy nhiên, một poller được đánh dấu started **không chứng minh Redis thật sự đang truy cập được**. Redis outage/ACL sai có thể chỉ xuất hiện ở lần query. Readiness cần giám sát Redis connectivity và khả năng thực hiện thao tác thực tế khi nghiệp vụ yêu cầu.

### 19.2. RedisConnectionFactory và client resources

RedisConnectionFactory tạo kết nối theo Spring Data Redis client và topology đã cấu hình. Khi sử dụng Redis Cluster/Sentinel, cần test:

- Redis node reconnect/failover.
- Redis key/slot routing đúng.
- Timeouts và retry của client không khiến poller block không giới hạn.
- Các operation đa key có dùng cùng hash slot nếu yêu cầu.
- Quyền truy cập các ZSET/HASH khác nhau theo namespace.

**Không tự tạo một Redis client hoặc kết nối mới cho từng RedisStore view** trong handler nếu adapter/source đã quản lý connection thông qua RedisTemplate. Giữ dependencies được Spring quản lý để tránh leak resources.

### 19.3. Graceful shutdown

Khi dừng ứng dụng:

1. Ngừng poll/claim jobs mới.
2. Cho các business handlers đang chạy hoàn tất trong timeout hữu hạn.
3. Nếu có lease, để scheduler/reclaimer xử lý jobs không hoàn tất khi restart.
4. Flush các metrics/logs cần thiết.
5. Đóng client resources theo Spring lifecycle.
6. Sau restart, đối soát jobs PROCESSING quá hạn và index stale.

**Stop thành công không chứng minh mọi reminder đã được gửi**. Với claim state, cần kiểm tra trạng thái thực của từng job.

### 19.4. Poller crash và transaction sync

Nếu process crash:

- Trước khi query, job có thể còn ở ZSET chờ poll kế tiếp.
- Sau khi query nhưng chưa claim, job vẫn có thể còn, nhiều workers sẽ thấy lại.
- Sau claim trước xử lý, job cần lease/reclaimer để khôi phục.
- Sau business commit trước cleanup, index có thể giữ member và tạo duplicate candidate.

Do đó shutdown và restart correctness phải được kiểm thử ở **cả bốn khoảng này**, không chỉ một happy-path smoke test.

### 19.5. Clock drift của scheduler

Khi score biểu diễn dueAt, nhiều nodes có clock lệch có thể chọn jobs sớm hoặc trễ. Chọn policy dùng clock của database/Redis/application một cách nhất quán; đo clock skew và chấp nhận jitter theo SLA. Không gọi poller fixedDelay(2000) là bảo đảm job được thực hiện chính xác trong 2 giây sau dueAt.

## 20. Bảo mật: Redis key, SpEL, serializer và dữ liệu nghiệp vụ

### 20.1. Redis ACL và quyền tối thiểu

Một source chỉ đọc ZSET có thể được giới hạn quyền trên Redis key tương ứng. Claim service cần thêm quyền để ZREM/ZADD hoặc dùng Lua theo thiết kế. Tách quyền:

| Actor | Quyền tối thiểu về ý nghĩa |
| --- | --- |
| Reminder writer | Ghi ZSET members thuộc namespace được phép |
| Store observer | Đọc ZSET/metadata, không xóa dữ liệu |
| Claim service | Đọc và claim các jobs đủ điều kiện |
| Reclaimer | Xem/đổi processing state theo lease |
| Operator | Điều tra/replay theo quyền được cấp, có audit |

Quy tắc ACL phụ thuộc phiên bản Redis và commands/scripts được dùng. Đừng cấp quyền nguy hiểm rộng cho worker chỉ để tránh lỗi NOAUTH/NOPERM.

### 20.2. Key-expression không phải một API đọc Redis tùy ý

Nếu ứng dụng cho người dùng tùy ý nhập tên key rồi đưa vào SpEL/key-expression, họ có thể khiến poller đọc **store ngoài phạm vi tenant** hoặc sai cấu trúc dữ liệu.

Hãy dùng:

- Danh sách key/namespaces được phép.
- Tenant identity từ nguồn xác thực.
- Không đưa raw user-provided SpEL expression vào Spring parser.
- Tách Redis users/instances khi cần isolation cao.

### 20.3. Redis ZSET member có thể là dữ liệu độc hại

Member **jobId** được producer ghi chưa chắc hợp lệ. Validate:

- Độ dài/format ID và schema version ở business state.
- Tenant/owner của job.
- Trạng thái PENDING, dueAt và revision hiện tại.
- Quyền truy cập recipient/template/destination.
- Rate limits để tránh một producer tạo hàng triệu due jobs.

Không suy rằng việc member xuất hiện trong key có tên **reminders:due** đồng nghĩa người gửi được cấp quyền gửi email cho mọi tenant.

### 20.4. Tránh deserialize không tin cậy

Khi dùng RedisTemplate với JDK serializer, phải hiểu rủi ro khi dữ liệu có thể do hệ thống khác ghi. Không tự bật deserialization polymorphic/trust-all types cho object tùy ý.

Ưu tiên **String IDs** trong ZSET và JSON/typed DTO đã validate ở nguồn nghiệp vụ. Với MAP/PROPERTIES, các value phức tạp phải có serialization/schema rõ, không biến một Redis hash thành đường thực thi Java objects tùy ý.

### 20.5. Đường dẫn và secrets

Không log raw payload chứa recipient, token hoặc thông tin người dùng; không lưu Redis password trong source. Không mang RedisStore live view hoặc native Redis client qua HTTP message body, Kafka payload hoặc serialization như thể chúng là DTO.

## 21. Monitoring: Poll rate khác business completion rate

Một dashboard tốt phải phân biệt **poll**, **query**, **candidate**, **claim** và **business success**.

| Tín hiệu | Ý nghĩa | Không được suy ra |
| --- | --- | --- |
| Poller executions | Số lần trigger | Số jobs mới |
| Source messages emitted | Số RedisStore views được phát | Số members đã xử lý |
| Redis query latency | Thời gian Redis trả range/size | Email/provider đã gửi thành công |
| Due candidate count | Jobs đến hạn theo query | Jobs được claim độc quyền |
| Claim success/failure | Ownership decisions | Business committed |
| Processing/in-flight count | Jobs đang xử lý | Jobs đã DONE |
| Business completed rate | Jobs hoàn tất | Cleanup index đã chạy thành công |
| Cleanup failure | ZSET stale sau commit | Business transaction rollback |
| Lease expired/reclaimed | Jobs cần khôi phục | Worker trước chắc chắn chưa side effect |
| Duplicate skipped | Idempotency hoạt động | Producer hoàn toàn không gửi trùng |

### 21.1. Metric naming minh họa

~~~text
redis_store_poller_executions_total{store="reminders-due"}
redis_store_source_emitted_total{store="reminders-due"}
redis_store_query_duration_seconds{store="reminders-due"}
reminder_due_candidates_total
reminder_claim_success_total
reminder_claim_conflict_total
reminder_completed_total
reminder_retry_exhausted_total{reason="PROVIDER_TIMEOUT"}
reminder_reclaimed_total
reminder_index_cleanup_failed_total
~~~

Các tên này là **gợi ý instrumentation**, không phải cam kết framework tự xuất toàn bộ. Với Micrometer/Observation, không dùng **jobId, tenantId hoặc email** làm metric labels có cardinality cao. Những IDs phù hợp hơn với logs/traces đã bảo vệ.

### 21.2. “Store size = 0” chưa đủ

Nếu handler claim bằng ZREM ngay rồi gửi email trong một queue nội bộ, ZSET due có thể rỗng trong khi jobs vẫn đang xử lý; khi worker crash, bạn có thể mất những jobs đó nếu không có processing store.

Trong mô hình reliable job state:

~~~text
Due ZSET count       = 0
Processing job count = 100
Business DONE count  = 0
~~~

Không hiển thị “all completed” chỉ từ ZCARD của due ZSET.

### 21.3. Cảnh báo theo SLA

Các ngưỡng quan trọng:

- Oldest overdue job vượt SLA.
- Poller lâu không chạy hoặc Redis queries liên tục lỗi.
- Query duration tăng sau thay đổi ZSET cardinality.
- Claim conflicts tăng bất thường do replicas cùng quét.
- PROCESSING lease expired backlog tăng.
- Retry exhausted/FAILED jobs vượt ngưỡng.
- Cleanup failures/DB DONE nhưng ZSET member còn tăng.
- Redis memory/eviction/failover hoặc ACL failures.

### 21.4. Log một job an toàn

~~~text
endpoint=reminderStoreInbound
storeKeyAlias=reminders-due
collectionType=ZSET
jobId=reminder-1001
dueAtEpochMillis=1795402800000
claimState=ACQUIRED
jobStatus=PROCESSING
attempt=2
errorCategory=NONE
~~~

**Không log nguyên RedisStore object** vì nó không phải DTO bất biến; nó có thể chứa thông tin connection/context hoặc gọi methods nguy hiểm khi debug. Dùng key alias, jobId và trạng thái đã validate.

## 22. Ma trận kiểm thử end-to-end với Redis thật

Unit test business handler **không chứng minh** RedisStoreMessageSource thực sự tạo đúng view, keyExpression được đánh giá ra sao, poller có được kích hoạt hay serializer có đọc đúng value không. Cần integration test với Redis server thật trong môi trường cô lập.

| Test case | Thiết lập | Kết quả cần kiểm chứng |
| --- | --- | --- |
| **Source emits view** | Poller và Redis key ZSET hợp lệ | Handler nhận RedisZSet/RedisStore view, không phải một String jobId |
| **Empty store** | Key không tồn tại hoặc ZSET rỗng | Flow không crash, không tuyên bố một job đã processed |
| **Due range** | Thêm job quá hạn và job tương lai | rangeByScore chỉ trả candidates đủ điều kiện |
| **Live view vs snapshot** | Poll rồi producer thêm member trước lúc query | Handler có thể thấy thay đổi mới, test không giả định snapshot |
| **No destructive pop** | Một poller nhận view và handler chỉ đọc | ZSET member vẫn tồn tại sau poll |
| **Repeated poll** | Giữ một due member không cleanup | Cùng candidate xuất hiện qua nhiều polls |
| **maxMessagesPerPoll** | Nhiều members trong ZSET | Một source message vẫn có thể dẫn tới nhiều candidates |
| **Unsupported CollectionType** | Source ZSET nhưng Redis key chứa String | WRONGTYPE/error được quan sát |
| **Serializer mismatch** | Producer ghi JDK bytes, source dùng String serializer | Fail/garbled data được phát hiện |
| **SET view** | Source CollectionType.SET với Redis SET key | Nhận RedisSet view, không mặc định thứ tự |
| **MAP/PROPERTIES view** | Hash có fields | Đọc đúng fields/serializer và key |
| **Two poller replicas** | Cùng quét due ZSET | Có read overlap; claim service chỉ một worker được quyền xử lý |
| **Claim race** | Hai workers tranh cùng jobId | Đúng một conditional claim thành công |
| **Lua cross-slot** | ZSET keys khác hash slot trong Cluster test | Phát hiện lỗi cross-slot, không âm thầm mất job |
| **Crash before claim** | Kill handler sau query, trước claim | Job vẫn eligible và có thể được xử lý sau |
| **Crash after claim** | Kill sau claim, trước commit | Processing state còn, lease/reclaimer có thể recover |
| **Crash after commit** | Kill sau external/DB commit trước cleanup | Redis stale nhưng idempotency ngăn side effect trùng |
| **Transaction sync success** | Business xử lý đồng bộ và success | Callback afterCommit thực hiện theo cấu hình |
| **Transaction sync failure** | Handler ném exception không bị nuốt | Đường rollback/afterCommit behavior đúng ý định |
| **ErrorChannel swallow** | Error flow log rồi return | Không nhầm log lỗi với business rollback |
| **Async handoff** | ExecutorChannel trả về trước business | Xác minh cleanup không chạy sớm |
| **Key-expression changes** | Thay cấu hình key giữa các polls | Source đọc đúng key; không lẫn dữ liệu tenants |
| **Redis restart** | Restart Redis test giữa polls | Connection recovery, metrics, state reconciliation |
| **Stop/start poller** | Dừng endpoint rồi ZADD | Khi start lại source có thể đọc store hiện tại |
| **Poison member** | jobId sai format/trạng thái | Final failed state hoặc alert, không hot loop |
| **Expired lease** | Worker xử lý lâu hơn lease | Reclaim có fencing/idempotency, không ghi đè DONE |
| **Large ZSET** | Hàng chục nghìn members | Batch limits và latency ổn định, không materialize vô hạn |
| **Security** | Redis user thiếu permission hoặc tenant key sai | Lỗi rõ ràng; không bypass ACL |
| **Wrong Redis topology** | Publisher/reader khác database index | Test phát hiện không cùng store key/state |

### 22.1. Test một lần poll không xóa store

Một quy trình test cô lập:

1. Tạo Redis ZSET **test:reminders:due** và thêm job-1.
2. Start Spring Integration flow với RedisStoreMessageSource(CollectionType.ZSET).
3. Bắt một Spring Message đầu ra và xác nhận payload là một **RedisZSet view**.
4. Gọi rangeByScore để đọc job-1.
5. Kiểm tra **ZCARD** vẫn là 1 nếu handler không chủ động remove.

Đây là phép thử phân biệt store inbound với Redis queue inbound destructive POP.

### 22.2. Test poller với CountDownLatch

Test handler có thể dùng latch để xác nhận callback đã được gọi:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class RedisStoreCapturingSink {

    private final CountDownLatch latch = new CountDownLatch(1);
    private final AtomicReference<Object> payload =
        new AtomicReference<>();

    public void accept(Object view) {
        payload.set(view);
        latch.countDown();
    }

    public Object awaitView() throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("RedisStore view not received");
        }
        return payload.get();
    }
}
~~~

**Helper này chưa phải test Spring context hoàn chỉnh.** Cần nối nó vào test IntegrationFlow, start poller, dùng Redis test riêng và tránh chạy thêm poller khác cùng key. Bởi source có thể phát view ngay cả khi chưa có due members, nên **latch chỉ xác minh poller gọi handler**, không xác minh có một job mới.

### 22.3. Test transaction synchronization không chỉ đếm callback

Với callback cleanup sau commit, test cần xác nhận:

1. Handler đồng bộ xử lý đúng tập job IDs.
2. Transaction context thực sự thành công hoặc rollback theo trường hợp.
3. Callback chạy đúng pha.
4. Redis state sau callback khớp **IDs đã xử lý**.
5. Member mới được thêm trong khi xử lý **không bị xóa nhầm**.
6. Nếu afterCommit cleanup thất bại, lần poll tiếp theo **không gửi side effect trùng**.

Một test chỉ quan sát “afterCommit đã chạy” không chứng minh Redis ZSET cleanup an toàn khi có concurrent producers.

### 22.4. Test service không cần Redis

Unit test của ReminderHandler có thể giả lập một **claimed jobId** và DB job state. Kiểm tra:

- PENDING hợp lệ → PROCESSING → DONE.
- Unsupported schema/tenant → từ chối.
- JobId DONE → skip side effect.
- Timeout provider → UNKNOWN hoặc retry theo contract.
- Version cũ/owner sai → không ghi đè state.
- Two workers conditional claim cùng ID → chỉ một thành công.

Tách unit test domain khỏi Redis store polling giúp phát hiện lỗi nghiệp vụ mà không cần phụ thuộc vào scheduler timing.

### 22.5. Không thử nghiệm trên Redis production

Không DEL/FLUSHDB, cố ý WRONGTYPE, đổi ACL hay restart Redis đang phục vụ hệ thống thật. Dùng test namespace/Redis instance riêng, credential giới hạn và test data cleanup có kiểm soát.

## 23. Các loại collection khác: LIST, SET, MAP và PROPERTIES

Dù bài toán ZSET là ví dụ chính, **Redis store inbound adapter không chỉ đọc Sorted Set**.

### 23.1. LIST: xem collection, không phải BRPOP

~~~text
Redis LIST: import:{catalog}:candidates
  [file-1, file-2, file-3]

Poller -> RedisList view
Handler -> xem collection / chọn tập phù hợp
~~~

Nếu handler dùng list view để duyệt tất cả items, lần poll tiếp theo có thể đọc lại cùng items. **Không tự có consumer acknowledgment**. Muốn xử lý công việc FIFO bằng destructive pop, dùng Redis queue inbound thích hợp; muốn bảo vệ sau crash, cân nhắc Redis Streams/processing-list contract.

### 23.2. SET: tập IDs cần đối soát

~~~text
Redis SET: catalog:{refresh}:stale-product-ids
  {P-1, P-2, P-3}
~~~

Một handler có thể đọc các IDs để so sánh với database. Nhưng **Set không có thứ tự đảm bảo**, nhiều pollers có thể chọn cùng productId. Khi xóa member sau refresh, phải tránh race với producer vừa đánh dấu lại cùng ID trong lúc refresh đang chạy.

### 23.3. MAP: state lookup

~~~text
Redis HASH: catalog:{config}:flags
  newSearch = true
  resultLimit = 100
~~~

Một MAP view có thể phục vụ kiểm tra cấu hình theo lịch. Nhưng một handler duyệt các fields khi producer đang update có thể thấy dữ liệu thay đổi; nếu cần **snapshot nhất quán của nhiều fields**, thiết kế versioning/atomic writes hoặc đọc thành một cấu trúc versioned có contract rõ.

### 23.4. PROPERTIES: thuộc tính đơn giản

PROPERTIES là kiểu collection view được Spring Data Redis hỗ trợ; có thể dùng cho các thuộc tính đơn giản do ứng dụng quản lý. Nó **không tương đương Java application.properties file** tự load cấu hình vào mọi beans khi Redis thay đổi.

Khi muốn thay cấu hình runtime, cần quy tắc về ownership, schema/defaults, validation và tính nhất quán; không thay đổi bean configuration ngầm bằng cách poll một Redis store.

### 23.5. Mỗi loại store cần một contract query/remove khác nhau

| Store | Truy vấn ứng dụng | Rủi ro nếu cleanup sai |
| --- | --- | --- |
| LIST | View/iteration/index | Xóa nhầm vị trí khi có concurrent push/pop |
| SET | Membership/iteration | Xóa member vừa được producer đánh dấu lại |
| ZSET | Range by score/rank | Xóa nguyên range chứa jobs chưa xử lý |
| MAP | Field get/entries | Ghi đè/xóa field vừa được cập nhật |
| PROPERTIES | Property lookup | Mất cấu hình hoặc race với writer |

Không copy nguyên **removeByScore** từ ZSET sang SET/MAP/LIST và nghĩ rằng các collection có cùng API hoặc cùng bảo đảm.

## 24. Troubleshooting: poller chạy nhưng không xử lý đúng dữ liệu

Khi Redis store inbound flow không có business output, hãy tìm nguyên nhân theo **từng ranh giới** thay vì chỉnh interval tùy tiện:

~~~mermaid
flowchart TD
    A["Poller trigger"] --> B{"Source nhận view?"}
    B -->|"Không"| E1["Endpoint/lifecycle/config"]
    B -->|"Có"| C{"Đúng key/type/serializer?"}
    C -->|"Không"| E2["Redis WRONGTYPE / RedisTemplate"]
    C -->|"Có"| D{"Query có candidates?"}
    D -->|"Không"| E3["Score/cutoff/clock hoặc store rỗng"]
    D -->|"Có"| E{"Claim thành công?"}
    E -->|"Không"| E4["Replica conflict / stale state"]
    E -->|"Có"| F{"Business success?"}
    F -->|"Không"| E5["Provider/DB/validation"]
    F -->|"Có"| G["DONE + cleanup/reconcile"]
~~~

### 24.1. Poller log đều nhưng handler không thấy job

Có thể source đã phát view, nhưng:

- ZSET score nằm **trong tương lai**.
- Worker dùng **seconds** còn producer dùng **milliseconds**.
- Redis key sai environment/database.
- Handler type mismatch, đọc RedisList thay vì RedisZSet.
- Serializer không khớp member.
- Business filter loại job đã DONE/CANCELLED.
- Client clock lệch hoặc dueAt chưa thật sự đến.

**Tăng maxMessagesPerPoll không giải quyết trường hợp handler query sai score.**

### 24.2. Handler chạy lại cùng IDs mỗi hai giây

Đây có thể là hành vi bình thường nếu:

- rangeByScore chỉ đọc.
- Members chưa bị remove/mark DONE.
- Bước cleanup Redis thất bại.
- Hai pollers cùng đọc một ZSET.
- Source phát RedisStore view cho mỗi lần poll.

Giải pháp là **idempotency, claim, checkpoint và cleanup có điều kiện**, không chỉ đổi fixedDelay thành fixedRate.

### 24.3. Bị WRONGTYPE

Ví dụ source cấu hình CollectionType.ZSET nhưng key thật đã bị một service dùng SET đổi thành Redis String:

~~~bash
redis-cli TYPE reminders:{notify}:due
~~~

Lệnh TYPE ở môi trường được phép giúp xác định Redis data structure. Không tự DEL key production chỉ để bỏ lỗi WRONGTYPE; có thể đang chứa dữ liệu quan trọng của một service khác. Cần sửa key namespace/producer hoặc migration.

### 24.4. Handler nhận object khác RedisZSet

Kiểm tra:

- CollectionType được cấu hình gì?
- Endpoint nào thực sự gửi vào input channel?
- Có nhiều sources cùng gửi vào một channel không?
- Có transformer đổi payload trước handler không?
- Thư viện Spring Data Redis/Integration đang ở phiên bản nào?

Tránh ép kiểu không kiểm tra rồi dùng catch(ClassCastException) để bỏ qua. Kiểu payload là phần của integration contract.

### 24.5. Cleanup chạy nhưng mất jobs

Nếu xóa **range 0..now** sau khi xử lý một batch nhỏ, bạn có thể loại bỏ cả những jobs **chưa xử lý** có score tương tự. Đây là lỗi data loss, không phải lỗi scheduling. Dừng cleanup không an toàn, đối soát với database và bổ sung cơ chế **remove đúng IDs đã commit**.

### 24.6. Store rỗng mà metrics receive vẫn tăng

Source có thể phát view dù key chưa có member. Đừng lấy **source receive count** làm số jobs. Thay bằng các metric due candidates, claim success, business success, cleanup.

### 24.7. Poller chậm

Kiểm tra Redis query latency, number of members, response materialization, handler latency, executor saturation, transaction callback và scheduler pool. Không tăng tần suất lên 100ms khi mỗi query đang mất 2 giây và downstream chưa đủ capacity.

### 24.8. Redis connection UNKNOWN result

Nếu lệnh claim/xóa thất bại do network ở ranh giới response, application có thể không biết Redis đã thực hiện lệnh hay chưa. **Không giả định thất bại chắc chắn chưa thực hiện**. Kiểm tra state bằng jobId/owner/version và retry idempotent theo policy.

## 25. Tình huống kiến trúc thực tế

### 25.1. Case A – Reminder due index có database nguồn chuẩn

Một hệ thống gửi thông báo lịch hẹn:

~~~mermaid
flowchart LR
    API["Create reminder API"] --> DB[("Reminder DB")]
    DB --> IDX["ZSET due index"]
    IDX --> POLL["Redis store inbound<br/>poller"]
    POLL --> CL["Conditional DB claim"]
    CL --> SEND["Reminder provider"]
    SEND --> DONE["Mark DONE / cleanup"]
    DB --> REC["Reconciliation job"]
    REC --> IDX
~~~

**Phù hợp** nếu:

- DB là source of truth.
- ZSET làm index tăng tốc chọn candidates.
- Claim bằng DB conditional update/owner lease.
- Provider có idempotency hoặc có thể đối soát.
- Nếu index bị mất, reconciliation có thể rebuild từ DB.

**Không phù hợp** nếu team cho rằng poller tự bảo đảm mọi reminder được gửi đúng một lần mà không cần claim/lease/checkpoint.

### 25.2. Case B – Kiểm tra Redis SET những sản phẩm cần refresh

Một dịch vụ catalog lưu SET các productIds cần đối chiếu:

~~~text
Redis SET catalog:{refresh}:stale
    -> Redis store inbound poller (CollectionType.SET)
    -> Read IDs
    -> Validate current productVersion from DB
    -> Refresh search index
    -> Conditional cleanup / reconciliation
~~~

Rủi ro: khi handler đang refresh **P-1001**, publisher có thể lại đánh dấu P-1001 stale. Nếu worker xóa member vô điều kiện sau refresh, tín hiệu mới có thể mất. Một cách cải thiện là lưu **version/token** thay vì SET member đơn thuần, hoặc dùng durable task records.

### 25.3. Case C – Dynamic configuration từ Redis MAP

Một ứng dụng cần kiểm tra các flags từ Redis Hash:

~~~text
Redis HASH config:search:flags
    -> CollectionType.MAP
    -> Poller
    -> Validate schema/tenant
    -> Compare with last applied version
    -> Apply safe runtime configuration
~~~

Không tự load mọi field thành Spring bean settings hoặc cho một Redis writer bất kỳ thay cấu hình bảo mật runtime. Cần **versioning, allowlist, consistent state** và policy rollback.

### 25.4. Case D – SFTP import → Redis ZSET reconciliation

File inbound adapter đồng bộ CSV từ SFTP; parser ghi job IDs và due scores:

~~~mermaid
flowchart LR
    SFTP["SFTP inbound adapter<br/>poller"] --> PAR["CSV parser"]
    PAR --> DB[("Import DB + outbox")]
    DB --> Z["Redis ZSET<br/>due index"]
    Z --> SI["Redis store inbound<br/>poller"]
    SI --> V["Claim / validate"]
    V --> H["Row business handler"]
    H --> DB
~~~

**Hai pollers phục vụ hai nguồn khác nhau:** SFTP poller tìm file mới; Redis store poller xem collection/index hiện tại. Không đánh dấu import hoàn tất chỉ vì Redis ZADD đã thành công; phải theo dõi trạng thái từng row và downstream outcomes.

### 25.5. Case E – Redis ZSET → Kafka/AMQP

Nếu handler quét ZSET rồi publish từng member sang Kafka hoặc RabbitMQ:

~~~text
Redis store inbound -> select candidates
    -> claim
    -> Kafka/AMQP outbound adapter
    -> confirm/ACK publish theo broker đích
    -> mark dispatched + cleanup
~~~

Khoảng lỗi:

- Claim thành công rồi publish thất bại → cần retry.
- Publish thành công nhưng response UNKNOWN → có thể duplicate khi retry.
- Mark dispatched trước khi broker xác nhận → có thể mất event.
- Cleanup rộng theo score khi chỉ một phần batch publish thành công → mất các jobs còn lại.

Cần eventId ổn định, confirms/returns/producer ACK theo broker cụ thể, durable state và idempotent consumer. **MessageChannel.send thành công không tự chứng minh Kafka/RabbitMQ đã lưu và consumer downstream đã xử lý.**

### 25.6. Case F – Định kỳ kiểm tra dashboard/cache

Nếu mục đích chỉ là **đọc số lượng thành viên và cảnh báo**, Redis store inbound rất hợp lý:

~~~text
Poller -> RedisStore view -> read size/status -> alert if threshold
~~~

Không cần biến một flow chỉ đọc thành hệ thống retry/ACK phức tạp. Hãy định nghĩa view/query cost, cadence, metric cardinality và truy cập Redis read-only. Đây là use case tận dụng đúng bản chất **collection observation** của store inbound.

## 26. Những hiểu lầm thường gặp

**“Redis store inbound là Redis queue inbound đổi tên.”** Không. Store inbound là **polling source phát RedisStore view**; queue inbound là message-driven endpoint thường pop từng item từ Redis List.

**“Chọn CollectionType.LIST là mỗi poll lấy một List item.”** Không mặc định. View của List được trả về; việc đọc/xóa phần tử là quyết định của handler.

**“Store inbound dùng Redis PUBLISH/SUBSCRIBE.”** Không. Pub/Sub inbound là adapter khác, nhận notification từ channels/patterns.

**“Không cần Spring Integration Poller vì Redis có sẵn dữ liệu.”** RedisStoreMessageSource là polled MessageSource; cần poller hoặc một client chủ động gọi receive().

**“Một lần poll = một job.”** Một message source chứa RedisStore view có thể cho phép handler đọc nhiều members hoặc không có candidate nào.

**“maxMessagesPerPoll(1) giới hạn một Redis ZSET member.”** Nó giới hạn số messages nhận từ MessageSource, không số phần tử query từ view.

**“RedisStore là một snapshot bất biến.”** View có thể truy cập dữ liệu Redis tại thời điểm handler gọi method, sau khi producer đã thay đổi store.

**“Đưa RedisStore view vào QueueChannel tạo event history.”** Những view vẫn có thể trỏ cùng Redis key; việc đệm không bảo đảm snapshot theo mỗi lần poll.

**“ZSET đến dueAt sẽ tự push thông điệp cho handler.”** ZSET không tự tạo notification theo score; poller hoặc scheduler phải query.

**“rangeByScore đã claim jobs.”** Nó chỉ đọc candidates; nhiều workers có thể đọc cùng IDs.

**“ZREM sau side effect chống mọi duplicate.”** Hai workers có thể cùng side effect trước khi một worker xóa thành công.

**“ZPOPMIN chỉ lấy jobs đã đến hạn.”** ZPOPMIN lấy member score thấp nhất kể cả khi score nằm trong tương lai.

**“Xóa ZSET score range sau commit luôn an toàn.”** Range có thể chứa members mới hoặc members chưa xử lý thành công.

**“afterCommit cleanup là transaction nguyên tử với Redis.”** Callback đồng bộ hóa thời điểm thực hiện; nó không biến Redis và database thành transaction phân tán.

**“PseudoTransactionManager ghi transaction bền vững.”** Nó giúp kích hoạt transaction synchronization khi không có transaction manager thật; không tự bảo vệ Redis hoặc external APIs.

**“Bật @Transactional khiến Redis ZREM tự rollback khi JDBC rollback.”** Không trừ khi có cơ chế transaction riêng được thiết kế phù hợp; không coi JDBC transaction tự bao mọi Redis operations.

**“ExecutorChannel giữ nguyên thời điểm afterCommit.”** Handler bất đồng bộ có thể chưa xử lý xong khi poller callback/transaction đã hoàn thành.

**“Spring MessageHeaders.ID là business jobId.”** Message ID của Spring có thể thay đổi khi Message được tạo lại. JobId/eventId cần hợp đồng ổn định.

**“ZSET score là trạng thái ACK.”** Score chỉ là số theo contract; dùng dueAt/priority không tự có ACK.

**“SET/MAP/PROPERTIES có cùng API xóa score như ZSET.”** Các Redis collection có operations và semantics khác nhau.

**“Đã thấy RedisStore view nghĩa là Redis data đã được serialize thành Java DTO.”** View là đối tượng truy cập store; handler phải query/convert dữ liệu.

**“Nếu store rỗng, adapter chắc chắn không emit message.”** Source có thể vẫn phát RedisStore view; phải test behavior thực và dùng candidate count để đo business.

**“RedisConnectionFactory và RedisTemplate luôn dùng cùng serializer.”** Cách tạo source quyết định default template; custom template có thể khác producer.

**“Có thể chỉ định cả redis-template và connection-factory trên cùng source mà không sao.”** Hai lựa chọn không được trộn khi API quy định mutually exclusive.

**“key-expression có thể lấy tùy ý từ input của người dùng.”** Điều đó có thể đọc nhầm key/tenant hoặc mở ra biểu thức không an toàn.

**“CollectionType.ZSET sẽ tự sửa một key Redis String thành ZSET.”** Redis thao tác sai cấu trúc có thể trả WRONGTYPE; migration phải có chủ đích.

**“Ba replicas quét cùng store sẽ tự phân chia member độc quyền.”** Mỗi replica có thể nhận view cùng key và đọc cùng candidates; cần claim/lock/idempotency.

**“Sử dụng Lua script nghĩa là side effect email được commit cùng Redis.”** Lua nguyên tử trên Redis shard liên quan, không trên SMTP/HTTP/JDBC.

**“Lease hết hạn nghĩa là worker cũ chắc chắn đã dừng.”** Worker cũ có thể tiếp tục; cần fencing/idempotency khi reclaim.

**“Đưa job vào processing là đã xử lý thành công.”** PROCESSING mới là trạng thái claim; DONE phải được xác nhận sau business outcome.

**“Redis Cluster multi-key operations luôn chạy giữa mọi slots.”** Cross-slot commands cần key hash slot phù hợp, ví dụ dùng cùng hash tag.

**“Đo số lần poll là đủ để báo completed jobs.”** Poll counts, candidate counts, claim counts và business success phải tách biệt.

**“Tăng số pollers giúp xử lý nhanh mà không cần nhìn downstream.”** Có thể chỉ tăng query load, claim conflicts, duplicates và transaction races.

**“Test happy path có thể chứng minh at-least-once.”** Cần fault injection ở các mốc query, claim, commit, cleanup, lease expiry, failover.

**“Redis Streams tương đương ZSET có score.”** Streams có record IDs, pending/consumer groups/ACK riêng; ZSET không có các ngữ nghĩa đó mặc định.

## 27. Checklist thiết kế trước production

| Nhóm | Câu hỏi phải trả lời |
| --- | --- |
| **Đúng endpoint?** | Muốn poll collection view, pop List item hay nhận Pub/Sub notification? |
| **CollectionType** | LIST, SET, ZSET, PROPERTIES hay MAP? Redis key có đúng type? |
| **Key** | Literal hay key-expression? Ai được quyền chọn key? |
| **Serializer** | Key/value/hash serializers của source và producer có khớp không? |
| **Source payload** | Handler có nhận RedisStore view hay đang nhầm với một item DTO? |
| **Poller** | fixedDelay/fixedRate, maxMessagesPerPoll, scheduler pool, timing drift? |
| **Snapshot semantics** | Cần hiện trạng live, tập IDs materialized, hay một batch được claim? |
| **Query** | rangeByScore cutoff/limit chính xác? Score là seconds hay milliseconds? |
| **Claim** | Làm sao hai replicas không cùng xử lý job? |
| **Transaction** | DB transaction và Redis cleanup thuộc những ranh giới nào? |
| **Synchronization** | afterCommit/afterRollback có chạy đúng theo outcome handler không? |
| **Cleanup** | Xóa đúng IDs đã xử lý hay xóa range có thể chứa jobs khác? |
| **Idempotency** | JobId/business key unique, provider idempotency, DONE state? |
| **Retry** | In-process attempts khác durable attempts như thế nào? |
| **Lease/reclaim** | Ai nhận lại PROCESSING job, có fencing/heartbeat không? |
| **Poison jobs** | Lỗi cố định đi đâu, owner nào xử lý, có retention/audit? |
| **Concurrency** | Poller/handler/executor đang chạy bao nhiêu copies? |
| **Redis HA** | AOF/RDB/replication/failover phù hợp RPO/RTO? |
| **Redis Cluster** | Multi-key Lua/commands cần cùng slot không? |
| **Security** | ACL, TLS, key namespace, tenant checks, SpEL input? |
| **Capacity** | ZSET size, query latency, memory limits, batch size, poll interval? |
| **Observability** | Tách poll, candidates, claim, DONE, cleanup, lease expiry? |
| **Testing** | Redis thật, live view, repeated polls, crash windows và unknown outcomes? |
| **Fallback** | Nếu Redis index mất/stale, có source of truth để reconcile? |
| **API version** | Java DSL/annotation/transaction synchronization đã biên dịch bằng BOM hiện tại? |

### 27.1. Quy tắc quyết định nhanh

**Redis store inbound** phù hợp nếu:

- Bạn muốn **kiểm tra một Redis collection theo lịch**, không đòi một notification cho từng thay đổi.
- Có một contract rõ cho kiểu collection, query và phần tử.
- Có cơ chế idempotency/checkpoint nếu sẽ thực hiện side effect.
- Có nguồn sự thật/recovery khi dữ liệu cần bảo đảm cao.

**Redis queue inbound** phù hợp khi muốn **pop từng List item**, nhưng phải hiểu cửa sổ mất sau pop. **Redis Pub/Sub inbound** dành cho notification best-effort tới subscribers online. **Redis Streams** phù hợp hơn khi cần event log/pending/replay với consumer group.

### 27.2. Đừng thêm transaction synchronization nếu chỉ quan sát

Nếu mục tiêu duy nhất là quan sát một ZSET/SET rồi ghi metrics, để flow **read-only** đơn giản. Transaction synchronization phù hợp khi cần điều phối callback theo outcome, nhưng chỉ nên thêm khi biết rõ:

- Transaction nào thực sự tồn tại.
- Payload/resource nào callback truy cập.
- Những Redis mutations nào callback thực hiện.
- Nếu callback lỗi sau commit thì khôi phục ra sao.

### 27.3. Lộ trình tăng reliability

~~~text
Giai đoạn 1:
  Poll RedisStore view -> query -> observe/reconcile

Giai đoạn 2:
  Poll -> query bounded candidates -> idempotent handler
       -> mark DONE -> cleanup theo ID

Giai đoạn 3:
  Poll -> atomic claim -> durable processing state
       -> lease/reclaim -> retries -> final failed state
       -> fencing/idempotency -> audit/monitoring

Giai đoạn 4:
  Đánh giá liệu Redis Streams / AMQP / Kafka / DB job table
  có phù hợp hơn tự duy trì protocol claim và cleanup không.
~~~

Không nên nhảy thẳng tới custom Lua/lease implementation nếu bài toán chỉ là một dashboard read-only; cũng không nên giữ một rangeByScore read-only như thể đã có message delivery guarantee cho tác vụ thanh toán.

## 28. Câu hỏi tự kiểm tra

1. Redis store inbound channel adapter được kích hoạt bằng cơ chế nào? Vì sao cần Spring Integration Poller?
2. RedisStoreMessageSource trả về **một member Redis** hay **một RedisStore view**? Sự khác biệt này ảnh hưởng ra sao tới business handler?
3. Redis store inbound khác Redis queue inbound message-driven ở những điểm nào?
4. Redis store inbound khác Redis Pub/Sub inbound như thế nào về nguồn dữ liệu và thời điểm kích hoạt?
5. Nêu năm CollectionType được hỗ trợ và một use case cho mỗi loại.
6. Redis List view có tự BRPOP một item và gửi ACK cho handler không?
7. Tại sao RedisZSet.rangeByScore không được coi là lệnh claim job?
8. Một ZSET member có score lớn hơn nowEpochMillis có nên được xử lý ngay khi dùng score làm dueAt không?
9. ZPOPMIN có bảo đảm chỉ pop member đến hạn không? Nếu không, cần bổ sung điều kiện gì?
10. Vì sao mỗi poller execution không nhất thiết tương ứng một job mới?
11. maxMessagesPerPoll(1) có hạn chế số members handler đọc được từ RedisStore view không?
12. RedisStore view khác một snapshot bất biến của Redis collection ở đâu?
13. Nếu QueueChannel giữ ba RedisStore views của cùng key, chúng có trở thành ba phiên bản snapshot độc lập không?
14. Hai pollers cùng đọc rangeByScore có thể thấy cùng jobId không? Làm sao bảo đảm chỉ một worker được claim?
15. Trong Java DSL, CollectionType.ZSET được cấu hình ở source hay ở handler?
16. Có thể khai báo RedisStoreMessageSource bằng @InboundChannelAdapter và @Poller thay cho Java DSL không?
17. Vì sao không chạy đồng thời hai pollers cùng key trong một lab cần đo đúng một business handler?
18. Sự khác nhau giữa key literal và key-expression là gì? Vì sao dynamic key cần kiểm soát tenancy?
19. RedisConnectionFactory khác RedisTemplate ở trách nhiệm và serializer như thế nào?
20. Nếu source mặc định dùng StringRedisTemplate còn producer ghi JDK-serialized members, những rủi ro nào xuất hiện?
21. WRONGTYPE nghĩa là gì khi source cấu hình ZSET nhưng key Redis chứa String?
22. MAP/PROPERTIES có nên dùng cùng removeByScore như ZSET không? Vì sao?
23. Redis SET có bảo đảm thứ tự duyệt members không? Thế nào là một cleanup race khi producer thêm lại cùng ID?
24. Nếu ZSET score là Unix epoch milliseconds, cần quy đổi giờ địa phương ra sao để tránh chạy quá sớm hoặc quá muộn?
25. Một reminder đến hạn nhưng đã CANCELLED trong database có nên gửi không?
26. Nếu handler chỉ rangeByScore và in log, cùng jobId có thể xuất hiện ở những lần poll tiếp theo không?
27. PseudoTransactionManager cung cấp loại hỗ trợ nào và không cung cấp bảo đảm atomicity nào?
28. TransactionSynchronizationFactory có thể tổ chức những pha callback nào?
29. Vì sao afterCommit expression xóa cả score range có nguy cơ xóa jobs chưa xử lý hoặc jobs mới được thêm?
30. Nếu handler dùng ExecutorChannel, afterCommit có thể chạy trước khi async worker hoàn tất không?
31. Lệnh Redis MULTI/EXEC hoặc Lua có tự commit email provider/JDBC trong cùng transaction không?
32. Nếu job đã DONE ở database nhưng afterCommit Redis cleanup thất bại, lần poll tiếp theo nên xử lý thế nào?
33. Claim job bằng DB conditional update phải dựa vào những điều kiện status/version nào để chống race?
34. Nếu nhiều workers dùng cùng due ZSET, khi nào cần owner/lease/fencing token?
35. Lease hết hạn có chứng minh worker cũ đã dừng hoàn toàn không?
36. Fencing token chỉ có giá trị khi được hệ thống đích kiểm tra như thế nào?
37. ZSET chỉ làm due index thì source of truth nên nằm ở đâu và làm sao rebuild khi Redis index bị mất?
38. Nếu Redis là nguồn dữ liệu duy nhất và bị failover, cần đánh giá những yêu cầu RPO/RTO và persistence nào?
39. Nếu dùng Lua claim với hai keys trong Redis Cluster, các keys phải đáp ứng điều kiện hash slot nào?
40. Vì sao jobId là member ngắn có thể an toàn/dễ xử lý hơn lưu toàn bộ email/PII trong ZSET member?
41. Trong bài toán SFTP import → ZSET, vì sao không đánh dấu import hoàn tất chỉ vì Redis ZADD thành công?
42. Khi bridge Redis ZSET → Kafka/AMQP, làm sao phân biệt kết quả broker publish với business consumer đã xử lý xong?
43. Những metric nào phải tách riêng: poll count, candidate count, claim success, business DONE và cleanup failure?
44. Unit test handler có chứng minh RedisStoreMessageSource đã được poll với đúng key/type không?
45. Một integration test nào chứng minh Redis store inbound **không tự xóa member**?
46. Vì sao phải test crash sau claim nhưng trước commit và crash sau commit trước cleanup?
47. Nếu sau deploy due candidate count tăng nhưng job success bằng 0, bạn kiểm tra theo thứ tự nào?
48. Redis store inbound read-only nên cấu hình quyền Redis như thế nào?
49. Trường hợp nào nên chuyển từ ZSET + custom claim sang Redis Streams consumer group hoặc broker có ACK?
50. Hãy phác thảo một flow tối thiểu dùng RedisStoreMessageSource để **chỉ quan sát** ZSET mà không gây side effect.

## 29. Nguồn tham khảo và phạm vi phiên bản

Nên đối chiếu với tài liệu **Spring Integration Redis Support** và Spring Data Redis Javadocs trước khi đưa code vào dự án:

- [Spring Integration – Redis Support, Redis Store Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/redis.html): Java DSL, Java annotations, XML, CollectionType, default serializer và transaction synchronization.
- [Spring Integration – RedisStoreMessageSource API](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/redis/inbound/RedisStoreMessageSource.html): source trả về RedisStore view, constructor nhận RedisConnectionFactory hoặc RedisTemplate, keyExpression.
- [Spring Data Redis – RedisStore interface](https://docs.spring.io/spring-data/redis/docs/3.5.x/api/org/springframework/data/redis/support/collections/RedisStore.html): abstraction của các Redis-backed collection views.
- [Spring Data Redis – RedisZSet API](https://docs.spring.io/spring-data/redis/docs/3.5.x/api/org/springframework/data/redis/support/collections/RedisZSet.html): rangeByScore, removeByScore và thao tác ZSET.

Những ví dụ sử dụng RedisStoreMessageSource, Redis.storeInboundChannelAdapter, Pollers và PseudoTransactionManager theo **hệ API được mô tả trong tài liệu tương ứng**. Trong thực tế cần kiểm tra BOM/phiên bản Spring Boot–Spring Integration–Spring Data Redis, biên dịch, rồi chạy integration tests với Redis thật. Bài học này là tài liệu khái niệm và thực hành, **không tự nhận đã chạy build hoặc Content QA chuyên sâu** trên dự án cụ thể.

## Tổng kết

**Redis store inbound adapter** là một **polled inbound channel adapter**: Spring Integration Poller kích hoạt RedisStoreMessageSource, source trả **Spring Message chứa RedisStore view** gắn với một Redis key, và MessageChannel đưa view tới transformer/router/service activator. Nó hỗ trợ các collection types **LIST, SET, ZSET, PROPERTIES và MAP**. Khác biệt sống còn là **store view không đồng nghĩa một item vừa bị pop, một snapshot bất biến hay một công việc đã được ACK**.

Trong ví dụ **reminder due ZSET**, poller định kỳ phát view; handler dùng rangeByScore để tìm **candidates** theo thời gian. Việc **query, claim, business processing, mark DONE và cleanup Redis** là những hành động riêng. Nếu nhiều replicas cùng quét, cần atomic claim/conditional DB update, idempotency và lease/fencing khi xử lý lâu; nếu không, cùng member có thể được xử lý lặp. **maxMessagesPerPoll** chỉ giới hạn lượt source receive, không giới hạn số members của Redis collection.

**Transaction synchronization** cho phép gắn callback vào beforeCommit/afterCommit/afterRollback, nhưng không tự tạo distributed transaction Redis + JDBC + external service. Xóa **cả score range** sau commit có thể gây mất job khi có concurrent producers hoặc partial batch failure. Thiết kế production nên cleanup theo **jobId/version đã xác nhận**, duy trì durable state/reconciliation, và kiểm thử crash/restart/race.

Khi tích hợp Redis với File, SFTP, HTTP, JMS, AMQP, Kafka và database trong **SPRING_INTEGRATION_ADAPTERS**, hãy luôn phân biệt **đã poll source**, **đã đọc candidate**, **đã claim trách nhiệm**, **đã lưu bền kết quả**, và **đã hoàn tất side effect nghiệp vụ**. Chọn Redis store inbound cho bài toán **quan sát/truy vấn collection theo lịch**; khi cần message log, consumer groups, pending records hoặc broker acknowledgment, cân nhắc Redis Streams hay một durable messaging system phù hợp hơn.
