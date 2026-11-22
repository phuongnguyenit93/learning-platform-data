# Mô phỏng rebalance trong Spring Kafka: thực hành và quan sát an toàn

Một dịch vụ Spring Kafka đang chạy ổn định với một consumer instance. Khi triển khai thêm một replica để tăng throughput, Kafka bắt đầu **rebalance**: các consumer trong cùng group phải nhận lại partition assignment. Trong khoảng chuyển đổi này, một số partition tạm thời không có worker xử lý; record đang làm dở có thể được giao lại, consumer lag tăng và những thao tác nghiệp vụ không idempotent có nguy cơ tạo kết quả trùng. Ngược lại, nếu giảm replica mà không hiểu rebalance, đội vận hành có thể nhầm consumer tạm dừng với Kafka bị mất dữ liệu.

Bài học thuộc **Spring Kafka Reliability Operations → Thực hành vận hành** và tập trung vào việc **mô phỏng rebalance một cách có thể quan sát, tái hiện và kiểm chứng**. Ta sẽ dùng **Java 17, Spring Boot 3.x, Spring Kafka 3.x, JUnit 5 và Embedded Kafka** để chủ động cho consumer A tham gia group, thêm consumer B, rồi dừng B; kiểm tra partition assignment và dữ liệu được tiếp nhận ở từng giai đoạn. Tiếp theo là bài thực hành với Kafka CLI/Kubernetes, khác biệt giữa graceful shutdown và crash, tác động của assignor, các timeout liên quan và cách phòng mất hoặc xử lý trùng record.

Các tên topic, group và con số dưới đây là **dữ liệu lab**. Không chạy lệnh dừng hoặc scale consumer trên cluster production nếu chưa có phê duyệt vận hành, giới hạn tải và kế hoạch phục hồi.

## 1. Rebalance là gì và vì sao phải mô phỏng?

Trong một **consumer group**, Kafka phân phối partition cho những consumer member cùng group. Với cách tiêu thụ thông thường, **mỗi partition được gán cho tối đa một member trong group tại một thời điểm**. Khi tập member hoặc topology thay đổi, Kafka cần điều chỉnh phân công công việc. Quá trình điều chỉnh đó được gọi là **consumer group rebalance**.

```text
Topic: orders.rebalance.lab
Partitions: P0, P1, P2, P3
Group: orders-rebalance-lab-group

Giai đoạn A: chỉ một consumer

    P0 ─┐
    P1 ─┤
    P2 ─┼──> Consumer A
    P3 ─┘

Giai đoạn B: thêm consumer

    P0 ─┐
    P1 ─┴──> Consumer A

    P2 ─┐
    P3 ─┴──> Consumer B

Giai đoạn C: Consumer B rời group

    P0 ─┐
    P1 ─┤
    P2 ─┼──> Consumer A
    P3 ─┘
```

Sơ đồ minh họa một assignment thuận tiện, **không phải thứ tự partition Kafka cam kết**. Phân chia thực tế phụ thuộc assignor, subscription, số member, static membership, phiên bản group protocol và trạng thái cluster.

### 1.1. Những sự kiện thường dẫn tới rebalance

| Sự kiện | Mô tả | Rủi ro nếu không kiểm soát |
| --- | --- | --- |
| Consumer mới tham gia | Tăng replica, tạo thêm listener member | Partition chuyển owner, lag tăng ngắn hạn |
| Consumer dừng bình thường | Rolling deployment, scale down, stop container | Worker khác phải nhận partition còn lại |
| Consumer crash hoặc mất mạng | Member không còn heartbeat/không gửi leave phù hợp | Chờ timeout/phát hiện rồi phân lại partition |
| Xử lý quá lâu, không poll kịp | Vượt điều kiện `max.poll.interval.ms` | Member có thể bị coi là không còn xử lý đúng hạn |
| Thay số partition topic | Topic có thêm partition | Group cần nhận thêm phần việc |
| Thay subscription | Consumer subscribe thêm/bớt topic | Phân công được tính lại |
| Thay assignor/group protocol | Triển khai cấu hình mới | Có thể đổi cách thu hồi và cấp partition |

**Không phải thao tác nào cũng là rebalance.** `pause()` một consumer/container thường tạm ngừng tiêu thụ nhưng **không tự chuyển quyền sở hữu partition sang member khác**. Gửi thêm message, tăng lượng backlog hoặc đặt `Thread.sleep(...)` trong test cũng không phải cách tin cậy để chủ động tạo rebalance.

### 1.2. Cần xác nhận điều gì trong bài thực hành?

Một bài test rebalance đáng tin cậy không chỉ assert rằng listener được gọi:

1. **Membership:** cả A và B thực sự thuộc **cùng một consumer group**.
2. **Ownership:** lúc đầu A sở hữu bốn partition; khi B tham gia, tổng assignment vẫn là bốn, không partition nào đồng thời thuộc hai member.
3. **Reassignment:** khi B rời group, A nhận lại toàn bộ partition.
4. **Progress:** record gửi vào các partition trước/sau chuyển đổi vẫn được consumer group xử lý.
5. **Offset:** xử lý lại record sau lỗi/rebalance không được hiểu thành record mới.
6. **Side effect:** nếu record được giao lại, DB/API đích không tạo kết quả trùng hoặc mất dữ liệu.
7. **Observability:** có thể nhìn thấy thời điểm revoke/assign, lag, lỗi và thời gian hồi phục.

Mục tiêu của Embedded Kafka test cơ bản là kiểm tra **assignment và record progress**. Kiểm tra crash của process, network partition, multi-broker failover và cam kết end-to-end cần các bài test nâng cao riêng.

## 2. Các thành phần và trạng thái liên quan

```text
                Kafka cluster / group coordinator
                              |
                       member assignment
                              |
                 +------------+-------------+
                 |                          |
           Spring consumer A           Spring consumer B
                 |                          |
            poll / commit                poll / commit
                 |                          |
           @KafkaListener A           @KafkaListener B
                 |                          |
                 +-----------+--------------+
                             |
                        Business sink
```

| Khái niệm | Ý nghĩa | Điều quan sát trong lab |
| --- | --- | --- |
| `group.id` | Định danh consumer group | A và B dùng cùng group |
| `client.id` | Định danh phía client cho metrics/log | Phân biệt instance, không thay thế group ID |
| Topic partition | Đơn vị được phân công | Tập `TopicPartition` của mỗi member |
| `position` | Offset tiếp theo ở consumer hiện tại | Có thể tiến trước khi offset được commit |
| Committed offset | Tiến độ lưu cho consumer group | Member mới tiếp tục từ vị trí được ghi nhận |
| Assignment | Partition consumer đang sở hữu | Thay đổi khi join/leave |
| Revocation | Partition bị thu hồi khỏi member | Nơi cần xử lý state/flush phù hợp |
| Rebalance listener | Callback về partition assign/revoke/lost | Dùng để quan sát lifecycle |
| Consumer lag | Chênh lệch giữa vị trí cuối và tiến độ đã commit theo cách đo | Có thể tăng ngắn hạn khi rebalance |

Kafka offset là **vị trí trong từng partition**. Offset 7 ở P0 và offset 7 ở P3 không phải cùng một message. Khi một record được giao lại vì owner đổi, hãy so sánh **topic, partition, offset** và business event ID; không chỉ dựa vào key hoặc giá trị payload.

## 3. Rebalance không có nghĩa Kafka xóa hoặc chuyển record

Kafka lưu record trong partition log. Khi member B nhận P2 và P3 từ A, Kafka **không di chuyển dữ liệu vật lý** giữa partition để phục vụ rebalance. Điều thay đổi là consumer member nào được phép poll và xử lý những partition đó.

```text
P2 log:
offset 10 ── offset 11 ── offset 12 ── offset 13 ──>
                     ^
               committed offset

Trước rebalance: A đọc P2
Sau rebalance:   B đọc P2 từ vị trí phù hợp committed offset
```

Khi Kafka commit offset **12**, ý nghĩa thông thường là vị trí sẽ đọc tiếp **offset 12**, tức những record trước đó đã được ghi nhận xử lý theo hợp đồng của consumer group. Nếu application hoàn tất business side effect nhưng chưa commit offset 12 rồi mất assignment, member mới có thể đọc lại record đã gây side effect.

Vì vậy:

```text
Rebalance + commit chưa hoàn tất
    -> có thể redelivery
    -> business handler phải chịu được duplicate
```

**At-least-once** là thiết kế phổ biến khi consumer xử lý dữ liệu rồi commit offset sau. Nó ưu tiên không bỏ sót record nhưng cần idempotency để xử lý duplicate. Nếu commit trước khi ghi kết quả hoặc bỏ lỗi mà vẫn commit, hệ thống có thể mất dữ liệu nghiệp vụ. Không chuyển sang auto-commit chỉ để test rebalance “hết lỗi”.

## 4. Hai kiểu rebalance: eager và cooperative

Không phải mọi assignor đều thu hồi partition theo cùng cách. Hiểu khác biệt giúp đọc đúng log và tránh test có assertion quá cứng.

### 4.1. Eager rebalance

Với một **eager assignor** như `RangeAssignor` trong ngữ cảnh group protocol hỗ trợ, các member có thể bị thu hồi assignment rồi được cấp lại theo một vòng điều phối. Kể cả partition cuối cùng vẫn thuộc A, callback revoked/assigned có thể xuất hiện trong quá trình group ổn định.

```text
A đang giữ P0 P1 P2 P3
        |
        | B join
        v
   Revoke assignments
        |
        v
A nhận P0 P1       B nhận P2 P3
```

### 4.2. Cooperative rebalance

Với `CooperativeStickyAssignor` và cấu hình tương thích, group có thể **thu hồi tăng dần những partition thực sự cần chuyển** thay vì luôn thu hồi tất cả. Điều này có thể giảm gián đoạn khi rolling deploy.

```text
A: P0 P1 P2 P3
       |
       | B join
       v
A giữ P0 P1, lần lượt nhả P2 P3
                           |
                           v
B nhận P2 P3 sau khi ownership được chuyển
```

Sơ đồ chỉ thể hiện ý tưởng: cooperative rebalance có thể trải qua nhiều vòng và callback khác với eager. Không nên assert “mọi partition đều được revoke đúng một lần” cho cả hai kiểu.

**Phạm vi phiên bản:** Kafka có các thế hệ group protocol khác nhau (classic và consumer group protocol mới hơn). Tên config và tính năng của assignor có thể khác theo broker/client và protocol. Khi làm lab, cố định cấu hình `RangeAssignor` để dễ dự đoán; khi làm production, kiểm tra group protocol và assignor thực tế rồi mới quyết định migration.

## 5. Chuẩn bị dự án lab

Yêu cầu:

- Java 17 trở lên theo tương thích của phiên bản Spring Boot dự án.
- Spring Boot 3.x và Spring Kafka 3.x tương ứng.
- JUnit 5, AssertJ, `spring-kafka-test`.
- Không cần Kafka cluster ngoài cho **bài lab join/leave cơ bản** vì dùng Embedded Kafka.

Ví dụ dependency Gradle (khi dự án đã dùng Spring Boot BOM và plugin tương ứng):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot dependency management cần quản lý phiên bản Spring Kafka tương thích. Không tự chọn ngẫu nhiên một version Kafka client khác để “tránh lỗi rebalance” mà chưa xem compatibility matrix của ứng dụng.

Một cấu trúc thư mục:

```text
src/
├── main/java/com/example/kafka/
│   └── ReliabilityApplication.java
└── test/java/com/example/kafka/
    └── RebalanceSimulationTest.java
```

Phần test dưới đây đặt listener fixture và Spring configuration **ngay trong file test** để không phải đọc thêm source khác.

## 6. Kịch bản test: A → A+B → A

Topic cố định **4 partition** và một group:

```text
Topic: rebalance.orders.input
Partitions: 4
Group: rebalance-lab-group
```

Các giai đoạn:

| Giai đoạn | Hành động | Assignment dự kiến | Record thử |
| --- | --- | --- | --- |
| 1 | Start A, B chưa start | A: 4, B: 0 | `phase1-p0` ... `phase1-p3` |
| 2 | Start B trong cùng group | A: 2, B: 2 | `phase2-p0` ... `phase2-p3` |
| 3 | Stop B bình thường | A: 4, B: 0 | `phase3-p0` ... `phase3-p3` |

Ta đặt `RangeAssignor` để việc phân phối **4 partition trên 2 member cùng subscribe một topic** có kết quả hai partition/member khi group ổn định. Đừng hardcode rằng A luôn sở hữu P0, P1: identity/order của member và cách assignor chạy không phải hợp đồng kinh doanh.

`@KafkaListener(autoStartup = "false")` cho phép test tự điều khiển thời điểm start A và B. Không tạo một consumer group mới cho B: hai member phải dùng **chính xác cùng `groupId`** để có rebalance giữa chúng.

## 7. Integration test với Embedded Kafka

Ví dụ sau là **một file Java hoàn chỉnh** cho bài thực hành, sử dụng `KafkaListenerEndpointRegistry` để start/stop hai listener container. `RecordingConsumers` ghi lại người xử lý cùng record identity trong một `ConcurrentLinkedQueue` để test quan sát thread-safe.

`RebalanceSimulationTest.java`:

```java
package com.example.kafka;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.Collection;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

@SpringBootTest(
    classes = RebalanceSimulationTest.TestApp.class,
    properties = {
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.consumer.enable-auto-commit=false",
        "spring.kafka.consumer.key-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.consumer.value-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.producer.key-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.listener.ack-mode=record",
        "spring.kafka.consumer.properties.partition.assignment.strategy="
            + "org.apache.kafka.clients.consumer.RangeAssignor"
    }
)
@EmbeddedKafka(
    partitions = 4,
    topics = "rebalance.orders.input",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class RebalanceSimulationTest {

    private static final String TOPIC = "rebalance.orders.input";
    private static final int PARTITIONS = 4;

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableKafka
    static class TestApp {
        @Bean
        RecordingConsumers recordingConsumers() {
            return new RecordingConsumers();
        }
    }

    static class RecordingConsumers {

        record Delivery(
                String member,
                String topic,
                int partition,
                long offset,
                String value) {}

        private final ConcurrentLinkedQueue<Delivery> deliveries =
                new ConcurrentLinkedQueue<>();

        @KafkaListener(
            id = "member-a",
            topics = TOPIC,
            groupId = "rebalance-lab-group",
            autoStartup = "false")
        public void consumeA(ConsumerRecord<String, String> record) {
            capture("A", record);
        }

        @KafkaListener(
            id = "member-b",
            topics = TOPIC,
            groupId = "rebalance-lab-group",
            autoStartup = "false")
        public void consumeB(ConsumerRecord<String, String> record) {
            capture("B", record);
        }

        private void capture(
                String member, ConsumerRecord<String, String> record) {
            deliveries.add(new Delivery(
                    member,
                    record.topic(),
                    record.partition(),
                    record.offset(),
                    record.value()));
        }

        List<Delivery> snapshot() {
            return List.copyOf(deliveries);
        }
    }

    @Autowired
    private KafkaListenerEndpointRegistry registry;

    @Autowired
    private KafkaTemplate<String, String> producer;

    @Autowired
    private RecordingConsumers recorder;

    private MessageListenerContainer container(String id) {
        MessageListenerContainer result =
                registry.getListenerContainer(id);
        if (result == null) {
            throw new IllegalStateException(
                    "Missing test listener container: " + id);
        }
        return result;
    }

    private Set<TopicPartition> owned(
            MessageListenerContainer container) {
        Collection<TopicPartition> assigned =
                container.getAssignedPartitions();
        return assigned == null
                ? Set.of()
                : new HashSet<>(assigned);
    }

    private static void await(
            BooleanSupplier condition, Duration timeout, String reason)
            throws InterruptedException {

        long deadline = System.nanoTime() + timeout.toNanos();
        while (System.nanoTime() < deadline) {
            if (condition.getAsBoolean()) {
                return;
            }
            Thread.sleep(50); // Bounded polling, không phải sleep đoán.
        }
        throw new AssertionError(
                "Timed out while waiting for " + reason);
    }

    private void sendOnePerPartition(String phase) throws Exception {
        for (int partition = 0; partition < PARTITIONS; partition++) {
            producer.send(
                    TOPIC,
                    partition,
                    "order-" + partition,
                    phase + "-p" + partition)
                    .get(10, TimeUnit.SECONDS);
        }
    }

    private void awaitPhase(String phase) throws Exception {
        Set<String> expected =
                IntStream.range(0, PARTITIONS)
                        .mapToObj(p -> phase + "-p" + p)
                        .collect(Collectors.toSet());

        await(
                () -> recorder.snapshot().stream()
                        .map(RecordingConsumers.Delivery::value)
                        .collect(Collectors.toSet())
                        .containsAll(expected),
                Duration.ofSeconds(20),
                "all records of " + phase);
    }

    @AfterEach
    void stopContainers() {
        container("member-b").stop();
        container("member-a").stop();
    }

    @Test
    void redistributesPartitionsWhenMemberJoinsAndLeaves()
            throws Exception {

        MessageListenerContainer a = container("member-a");
        MessageListenerContainer b = container("member-b");

        // PHASE 1: chỉ A đang chạy.
        a.start();
        await(
                () -> owned(a).size() == PARTITIONS,
                Duration.ofSeconds(20), "A owns four partitions");

        assertThat(owned(b)).isEmpty();
        sendOnePerPartition("phase1");
        awaitPhase("phase1");

        assertThat(recorder.snapshot().stream()
                .filter(e -> e.value().startsWith("phase1"))
                .allMatch(e -> "A".equals(e.member())))
                .isTrue();

        // PHASE 2: B tham gia chính group của A.
        b.start();
        await(
                () -> owned(a).size() == 2 && owned(b).size() == 2,
                Duration.ofSeconds(30),
                "A and B each own two partitions");

        Set<TopicPartition> aOwned = owned(a);
        Set<TopicPartition> bOwned = owned(b);
        Set<TopicPartition> union = new HashSet<>(aOwned);
        union.addAll(bOwned);

        assertThat(aOwned).doesNotContainAnyElementsOf(bOwned);
        assertThat(union).hasSize(PARTITIONS);

        sendOnePerPartition("phase2");
        awaitPhase("phase2");

        Set<String> phase2Members = recorder.snapshot().stream()
                .filter(e -> e.value().startsWith("phase2"))
                .map(RecordingConsumers.Delivery::member)
                .collect(Collectors.toSet());

        assertThat(phase2Members).contains("A", "B");

        // PHASE 3: B dừng có kiểm soát.
        b.stop();
        await(
                () -> owned(a).size() == PARTITIONS,
                Duration.ofSeconds(30),
                "A owns all partitions again");

        sendOnePerPartition("phase3");
        awaitPhase("phase3");

        assertThat(recorder.snapshot().stream()
                .filter(e -> e.value().startsWith("phase3"))
                .allMatch(e -> "A".equals(e.member())))
                .isTrue();

        Set<String> distinctValues = recorder.snapshot().stream()
                .map(RecordingConsumers.Delivery::value)
                .collect(Collectors.toSet());
        assertThat(distinctValues).hasSize(12);
    }
}
```

Trong ví dụ:

- `@EmbeddedKafka` tạo topic với **bốn partition** trên broker test.
- Hai method `@KafkaListener` có `id` riêng nhưng **chung `groupId`**, và không tự start ở thời điểm Spring context được tạo.
- `registry.getListenerContainer(...)` lấy container thực để điều khiển membership.
- `getAssignedPartitions()` cho phép quan sát assignment **sau khi chờ điều kiện ổn định**.
- Producer gửi **một message vào từng partition**, tránh phụ thuộc phân bố hash của bốn key ngẫu nhiên.
- Dùng `await(...)` với timeout hữu hạn để đồng bộ theo **sự kiện thật**, thay vì `Thread.sleep(2000)` rồi đoán group đã ổn định.
- Cấu hình `ack-mode=record` và tắt Kafka auto-commit để container quản lý tiến độ cho record listener không transactional trong lab.

Đây là bài test **membership/assignment và delivery progress**, không phải kiểm chứng exactly-once. Dù đã quan sát đủ **12 giá trị riêng biệt**, một số record vẫn có thể được giao lại nếu sự cố xảy ra giữa business side effect và offset commit. Việc lưu `Delivery` vào queue xảy ra **trong listener, trước khi offset commit**; vì vậy queue không chứng minh side effect đã được giao dịch hóa.

### 7.1. Vì sao không assert “mỗi record chỉ gọi một lần”?

Trong hệ thống at-least-once, record xử lý xong nhưng offset chưa commit có thể được giao lại khi rebalance hoặc crash. Nếu assert callback count luôn bằng 12, test có thể **flaky** hoặc vô tình kiểm tra một cam kết Kafka không cung cấp.

Ở lab này, ta assert:

```text
Tất cả 12 eventId/value mong đợi đã được quan sát.
Ownership không bị trùng.
Member B thực sự xử lý record khi được phân partition.
Member A tiếp tục sau khi B rời group.
```

Nếu nghiệp vụ yêu cầu “không tạo 2 hóa đơn”, test phải kiểm tra **sink có idempotency**, chẳng hạn unique constraint `(event_id)` trong DB, thay vì giả định listener không bao giờ được gọi hai lần.

### 7.2. Vì sao chọn `RangeAssignor`?

Với **một topic có bốn partition** và hai members cùng subscribe topic, Range assignor giúp bài lab xác định giai đoạn 2 có hai partition/member sau khi group ổn định. Với `CooperativeStickyAssignor`, mục tiêu test vẫn là mọi partition có owner đúng, nhưng số lần và thứ tự callback revoked/assigned có thể khác.

Muốn test **cơ chế cooperative** đúng nghĩa, tạo một cấu hình/test khác và ghi lại callback theo từng vòng. Không áp dụng cùng assertion về “revoke toàn bộ partition” cho cả hai cơ chế.

### 7.3. Tránh nhiễu từ test khác

Đoạn test sử dụng một topic/group cố định, nên nên chạy **trong context/broker test cô lập**. Nếu suite chứa nhiều class cùng tên topic/group hoặc chạy parallel, kết quả assignment và callback có thể khác. Có thể dùng topic/group duy nhất cho mỗi fixture hoặc lifecycle context phù hợp; không chỉ tăng timeout để che nhóm consumer ngoài test đang tham gia.

## 8. Quan sát callback `assigned`, `revoked` và `lost`

Test ở phần 7 đọc snapshot assignment. Để biết **rebalance diễn ra khi nào**, Spring Kafka hỗ trợ `ConsumerAwareRebalanceListener`. Nó được cấu hình vào `ContainerProperties` của listener container:

```java
import java.util.Collection;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.listener.ConsumerAwareRebalanceListener;

ConsumerAwareRebalanceListener tracer =
        new ConsumerAwareRebalanceListener() {

    @Override
    public void onPartitionsRevokedBeforeCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {
        System.out.println(
                "rebalance_revoked_before_commit partitions=" + partitions);
    }

    @Override
    public void onPartitionsAssigned(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {
        System.out.println(
                "rebalance_assigned partitions=" + partitions);
    }
};

factory.getContainerProperties()
        .setConsumerRebalanceListener(tracer);
```

Đây là **fragment cấu hình**: `factory` là một `ConcurrentKafkaListenerContainerFactory` được dự án khai báo, và callback cần được gắn **trước khi container start**. Một chương trình production nên dùng logger có cấu trúc thay cho `System.out.println`.

Các callback quan trọng:

| Callback | Khi nào đáng chú ý? | Nguyên tắc xử lý |
| --- | --- | --- |
| `onPartitionsAssigned` | Member nhận partition | Nạp state/cache theo partition nếu cần; ghi dấu owner mới |
| `onPartitionsRevokedBeforeCommit` | Sắp hoàn tất quy trình thu hồi với cơ hội xử lý trước commit phù hợp | Hoàn tất state/flush theo thiết kế; tránh I/O kéo dài |
| `onPartitionsRevokedAfterCommit` | Sau điểm commit offset liên quan trong đường callback hỗ trợ | Dọn state đã không còn sở hữu |
| `onPartitionsLost` | Partition đã mất ownership, có thể không còn quyền commit an toàn | Không cố commit như thể vẫn là owner |

Các callback và thứ tự chi tiết phụ thuộc container, assignor, group protocol và phiên bản. Không mặc định `onPartitionsRevoked...` sẽ được gọi trong **mọi** loại crash: khi process chết, chính process đó không thể tự chạy callback nữa. Member khác nhận assignment thông qua coordinator sau khi phát hiện member cũ không còn hợp lệ.

### 8.1. Callback phải nhẹ và có tính an toàn

Không dùng rebalance callback để:

- Gọi HTTP API không timeout trong nhiều phút.
- Ghi DB không có giới hạn hoặc mở transaction quá dài.
- Tự `commitSync()` vào một partition đã **lost** chỉ để làm log trông đẹp.
- Thực hiện công việc bất đồng bộ rồi coi rằng state đã flush trước khi partition chuyển owner.
- Gửi message vào topic đích mà không có idempotency hoặc transaction phù hợp.

Callback chậm có thể kéo dài gián đoạn của cả group. Nếu có local state theo partition, hãy thiết kế checkpoint/snapshot gọn, phân biệt revoked với lost và dựa vào storage bền vững khi cần phục hồi.

### 8.2. Phân biệt trace callback với lịch sử đủ tin cậy

```text
2026-... group=orders-rebalance-lab-group
  event=partitions_assigned member=A partitions=[P0,P1,P2,P3]

2026-... group=orders-rebalance-lab-group
  event=partitions_revoked member=A partitions=[P2,P3]

2026-... group=orders-rebalance-lab-group
  event=partitions_assigned member=B partitions=[P2,P3]
```

Đây chỉ là **log minh họa**. Với eager assignor, callback thu hồi có thể gồm toàn bộ assignment và sau đó cấp lại. Với cooperative, một số partition giữ nguyên. Không dùng số lượng callback làm số lượng record đã xử lý hoặc số lần retry.

## 9. Kiểm tra consumer group bằng Kafka CLI

Trong môi trường có Kafka CLI và quyền `DESCRIBE` phù hợp, có thể xem trạng thái group từ bên ngoài ứng dụng:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server broker-1:9092 \
  --group rebalance-lab-group \
  --describe
```

Một output minh họa:

```text
GROUP                  TOPIC                    PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
rebalance-lab-group    rebalance.orders.input   0          101             105             4
rebalance-lab-group    rebalance.orders.input   1          203             204             1
rebalance-lab-group    rebalance.orders.input   2          312             312             0
rebalance-lab-group    rebalance.orders.input   3          418             423             5
```

Kiểm tra member và assignment:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server broker-1:9092 \
  --group rebalance-lab-group \
  --describe --members --verbose
```

Tùy Kafka CLI version và group protocol, cách trình bày member ID, host, client ID, assignment và trạng thái có thể khác. Trong lúc rebalance, một số thông tin sẽ tạm thời không ổn định; **chụp nhiều snapshot** thay vì kết luận chỉ từ một lần chạy.

### 9.1. Các bước thực hành thủ công

1. Tạo topic test với ít nhất bốn partition.
2. Khởi động **một** instance consumer có group `rebalance-lab-group`.
3. Dùng `--describe --members --verbose` để xác minh instance đầu sở hữu tất cả partition.
4. Bắt đầu **instance thứ hai** cùng group, khác `client.id`.
5. Quan sát log assign/revoke và kiểm tra lại assignment.
6. Gửi message vào từng partition, xác nhận dữ liệu được xử lý bởi owner tương ứng.
7. Dừng instance thứ hai bình thường, rồi quan sát instance đầu nhận lại assignment.
8. Kiểm tra lag giảm, DLT không tăng bất thường và dữ liệu đích không bị duplicate.

Nếu muốn mô phỏng rolling deployment, lặp lại trình tự với nhiều replica nhưng chỉ thay đổi **một member mỗi lần** và đo thời gian gián đoạn; tránh đồng thời khởi động/dừng toàn bộ group khi mục tiêu là chứng minh graceful rollout.

## 10. Mô phỏng rebalance với Kubernetes

Giả sử có Deployment chỉ dành cho lab:

```text
Namespace: kafka-lab
Deployment: orders-consumer-lab
Topic: rebalance.orders.input
Consumer group: rebalance-lab-group
```

Các lệnh sau chỉ là hướng dẫn thực hành, **không được chạy trên production**:

```bash
# Đảm bảo đúng Kubernetes context/namespace trước khi thay đổi.
kubectl config current-context
kubectl -n kafka-lab get deployment orders-consumer-lab

# Giai đoạn 1: một member (giả sử mỗi pod concurrency=1).
kubectl -n kafka-lab scale deployment/orders-consumer-lab --replicas=1

# Giai đoạn 2: thêm member, gây rebalance.
kubectl -n kafka-lab scale deployment/orders-consumer-lab --replicas=2

# Giai đoạn 3: giảm member.
kubectl -n kafka-lab scale deployment/orders-consumer-lab --replicas=1
```

Sau mỗi bước, kiểm tra group assignment bằng Kafka CLI hoặc dashboard. Không đồng nhất **số pod** với **số consumer member** nếu trong một pod cấu hình `spring.kafka.listener.concurrency > 1` hoặc ứng dụng có nhiều listener cùng group.

### 10.1. Cấu hình consumer trong Spring Boot

Ví dụ một service dùng một record listener trên topic lab:

```yaml
app:
  kafka:
    topic: rebalance.orders.input

spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    consumer:
      group-id: rebalance-lab-group
      enable-auto-commit: false
      auto-offset-reset: earliest
      max-poll-records: 100
      properties:
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
    listener:
      concurrency: 1
      ack-mode: record
```

Config này là ví dụ **classic protocol với cooperative assignor khi client/broker hỗ trợ**, không áp dụng mù quáng khi cluster đã bật hoặc chuyển sang group protocol mới với cơ chế assignment khác. Producer/consumer serializer, security, timeout và error handling phải được cấu hình theo ứng dụng.

`auto-offset-reset: earliest` **không** khiến group đọc lại toàn topic khi đã có committed offsets hợp lệ. Khi member mới nhận partition, nó đọc theo vị trí/offset của group phù hợp. Không reset offset như một phần của rebalance bình thường.

### 10.2. Rolling update an toàn

Một trình tự triển khai cần cân nhắc:

```text
New pod ready to run consumer
         |
         v
Join consumer group
         |
         v
Partition assignment changes
         |
         v
Old pod stops accepting work / leaves safely
         |
         v
New owner continues from committed offsets
```

Thứ tự thực tế phụ thuộc strategy deployment (`RollingUpdate`, `maxSurge`, `maxUnavailable`), readiness/liveness probe, startup latency, termination grace period và container shutdown. **Readiness của web server không tự chứng minh Kafka listener đã nhận partition**. Với service chỉ làm Kafka consumer, readiness nên phản ánh những điều kiện sống/có thể xử lý thích hợp và tránh restart loop khi Kafka tạm rebalance.

Nên kiểm soát:

- Không deploy đồng loạt làm toàn group đổi member cùng lúc khi không cần thiết.
- Có đủ thời gian để record đang xử lý hoàn thành, commit offset hoặc rollback an toàn.
- Khi pod nhận SIGTERM, có lộ trình đóng listener/container hợp tác với Kubernetes shutdown.
- Không đánh dấu pod “khỏe” chỉ vì JVM còn sống trong khi consumer thread bị chặn lâu.
- Quan sát số partition đang assigned, rebalance time, lag và số instance trong giai đoạn rollout.

Graceful shutdown **giảm nguy cơ xử lý dở dang**, không biến consumer at-least-once thành exactly-once.

## 11. Graceful leave khác crash như thế nào?

Trong test phần 7, ta gọi:

```java
container("member-b").stop();
```

Đó là **rời group có kiểm soát**. Spring Kafka có cơ hội dừng listener, đóng consumer và thực hiện lifecycle phù hợp. Nó không tương đương với:

```text
kill -9 JVM
pod bị node failure
mất network và không thể heartbeat
process bị OOMKilled
```

### 11.1. Graceful stop

```text
Member B đang giữ P2,P3
       |
       v
Stop requested
       |
       +--> hoàn tất/dừng processing theo container policy
       +--> commit/rollback phù hợp
       +--> rời group/đóng consumer
       |
       v
Group reassigns P2,P3
       |
       v
Member A xử lý tiếp
```

Thời gian dừng và commit phụ thuộc kiểu listener, ack mode, transaction, thread state và timeout. Không giả định mọi offset chắc chắn đã commit chỉ vì phương thức `stop()` đã được gọi.

### 11.2. Crash hoặc mất heartbeat

```text
Member B crash bất ngờ
       |
       X--> Không thể chạy callback cleanup của chính B
       |
       v
Coordinator phát hiện member không còn hợp lệ
       |
       v
Rebalance / reassignment
       |
       v
A nhận P2,P3 từ committed offsets
       |
       v
Record chưa commit có thể được giao lại
```

Khi mô phỏng crash, dùng **process/container riêng** hoặc môi trường Testcontainers/Kubernetes lab. Dừng cả JVM chạy JUnit không phải cách thuận tiện để chứng minh nhiều kịch bản vì test process sẽ mất khả năng ghi assertion; nên điều khiển worker từ một process độc lập, rồi kiểm tra dữ liệu/offset từ một observer còn sống.

### 11.3. So sánh nên đo

| Hiện tượng | Graceful stop | Crash |
| --- | --- | --- |
| Consumer có cơ hội thực hiện shutdown callback | Có theo lifecycle | Không bảo đảm |
| Có thể gửi leave/đóng consumer bình thường | Thường có, tùy group protocol và state | Không |
| Thời gian phát hiện member vắng mặt | Thường ngắn hơn | Có thể phụ thuộc timeout |
| Record đang xử lý có thể bị giao lại | Vẫn có thể | Có thể cao hơn khi offset chưa commit |
| Business side effect tự rollback | Không | Không |
| Cần idempotency | Có | Có |

Không dựa vào một số giây cố định để kết luận crash recovery; đo thực tế và ghi rõ cấu hình session timeout, poll timeout, static membership, group protocol và tải.

## 12. Những timeout ảnh hưởng đến rebalance

Một số thuộc tính Kafka consumer thường gặp:

| Thuộc tính | Liên quan đến | Sai lầm thường gặp |
| --- | --- | --- |
| `session.timeout.ms` | Phát hiện member không còn heartbeat trong classic group protocol, theo broker constraints | Chọn quá dài khiến nhận biết crash chậm, quá ngắn khiến false failure |
| `heartbeat.interval.ms` | Tần suất heartbeat trong classic protocol; phải phối hợp session timeout | Coi như timeout cho business processing |
| `max.poll.interval.ms` | Thời gian tối đa giữa các lần `poll()` mà consumer phải tuân thủ | Xử lý record lâu, không poll và bị coi mất khả năng tiến |
| `max.poll.records` | Số record tối đa một lần `poll()` trả về | Chọn quá lớn khiến một poll mất nhiều thời gian xử lý |
| `partition.assignment.strategy` | Cách partition được cấp/revoke trong classic protocol | Đổi assignor đột ngột khi rollout mixed |
| `group.instance.id` | Static membership khi có cấu hình phù hợp | Trùng ID giữa pod hoặc hiểu nhầm static member không bao giờ rebalance |

Các group protocol mới có thể chuyển một số cấu hình heartbeat/session sang phía broker hoặc dùng property khác. Không áp một bộ timeout cho mọi cluster/phiên bản Kafka.

### 12.1. `max.poll.interval.ms` là bẫy của processor chậm

Giả sử một poll trả 500 record, và mỗi record cần 3 giây xử lý tuần tự:

```text
500 × 3 seconds = 1.500 seconds
```

Nếu khoảng thời gian giữa các lần poll vượt giới hạn cấu hình, consumer có thể mất quyền sở hữu partition hoặc bị đưa vào quy trình reassignment. Với Spring Kafka, hành vi cụ thể còn phụ thuộc container polling, concurrency, pause và logic listener. Nhưng bài toán gốc vẫn là **không để một poll bị chiếm quá lâu**.

Các hướng cải thiện:

- Giảm `max.poll.records` theo thời gian xử lý thực.
- Tối ưu truy vấn DB/API, có timeout và giới hạn concurrency.
- Tách công việc dài ra queue/outbox nếu cần, nhưng phải giữ contract commit/idempotency.
- Chọn batch listener hoặc worker design phù hợp khi cần throughput cao.
- Dùng metric poll interval, processing duration và lag thay vì tăng timeout mù quáng.

**Không sửa chỉ `session.timeout.ms` để chữa `max.poll.interval.ms`**: chúng quản lý những cơ chế khác nhau.

## 13. Static membership và cooperative rebalance để giảm churn

Trong một số hệ thống, pod có định danh ổn định và thường restart ngắn. Kafka **static membership** (`group.instance.id`) có thể giúp giảm một số rebalance không cần thiết, tùy Kafka group protocol và deployment. Điều kiện quan trọng:

- Mỗi instance chạy đồng thời phải có **`group.instance.id` duy nhất**.
- ID nên ổn định qua restart tương ứng với cùng logical instance.
- Không gán cùng một ID tĩnh cho nhiều pod trong Deployment thông thường; trùng ID có thể gây fencing/loại member.
- Static membership không chữa xử lý chậm, không chặn mọi rebalance và không thay thế timeout/monitoring.

Ví dụ một StatefulSet có identity ổn định có thể thuận lợi hơn một Deployment với pod name ngẫu nhiên cho static membership. Nhưng đây là **quyết định triển khai**, không phải một thuộc tính nên bật mặc định ở mọi Spring Kafka service.

**CooperativeStickyAssignor** có thể giảm số partition bị revoke khi membership thay đổi, nhưng phải kiểm tra tương thích giữa các member đang chạy và thứ tự migration assignor. Trong rolling upgrade, không tùy tiện để các member cùng group sử dụng các protocol/assignor không tương thích mà không có kế hoạch.

## 14. Consumer lag và tiến độ sau rebalance

Một lần rebalance có thể tạo ra đồ thị:

```text
Lag
 ^
 |                 /----\
 |                /      \
 |               /        \__
 |______________/             \__________> Time
                 rebalance
```

Producer vẫn ghi record trong khi consumer có thể tạm dừng phân công hoặc chưa xử lý kịp, nên lag tăng. Sau khi group ổn định và throughput xử lý lớn hơn tốc độ input, lag có thể giảm.

| Chỉ số | Ý nghĩa |
| --- | --- |
| Số lần rebalance theo consumer/group | Tần suất membership/assignment thay đổi |
| Rebalance duration | Độ dài gián đoạn/chi phí điều phối |
| Assigned partition count | Có member bị idle hoặc mất assignment bất thường không |
| Committed offset | Tiến độ đã ghi nhận cho group |
| Position/current offset | Vị trí consumer đang đọc, không luôn bằng committed offset |
| Consumer lag theo partition | Partition nào đang tụt lại |
| Processing latency | Business handler có chậm vượt SLA không |
| Commit failures / lost partitions | Tiến độ có bị gián đoạn khi ownership thay đổi không |
| DLQ/DLT events | Có record lỗi không thể xử lý hoặc recovery không |
| Duplicate business event count | Side effect đã được chống trùng ra sao |

Spring Kafka/Micrometer và Kafka client metrics có thể cung cấp các đo lường liên quan, nhưng **tên metric và tags thay đổi theo phiên bản/registry**. Kiểm tra metric thực tế trên runtime thay vì dựng alert bằng tên đoán trước.

Không dùng `orderId` hoặc Kafka offset làm metric label: cardinality quá cao. Dùng topic, partition, group, client ID và error code trong phạm vi hợp lý; trace chi tiết record bằng log/audit có phân quyền.

### 14.1. Tiêu chí xác nhận dịch vụ hồi phục

Không chỉ “group đã STABLE” là đủ:

1. Mọi partition cần đọc đều có owner phù hợp.
2. Không còn consumer member bất thường hoặc duplicate static member ID.
3. Lag có xu hướng giảm theo tốc độ input/output, không kẹt mãi ở một partition.
4. Error/commit failure rate trở lại ngưỡng cho phép.
5. Record/business event được đối soát, không có missing hoặc duplicate side effect ngoài policy.
6. DLT/retry backlog có kết quả xử lý rõ ràng.

Một group có assignment ổn định vẫn có thể bị **poison record** ở một offset khiến lag không giảm. Rebalance không phải cơ chế tự sửa dữ liệu lỗi.

## 15. Rebalance và tính đúng đắn dữ liệu: xử lý lặp là tình huống phải thiết kế

Giả sử listener:

```java
@KafkaListener(topics = "orders.rebalance.lab",
               groupId = "orders-rebalance-lab-group")
public void consume(OrderCreated event) {
    paymentService.charge(event.orderId());
    // Offset được commit theo container sau khi listener hoàn tất.
}
```

Đường lỗi:

```text
A nhận offset 10
    |
    +--> paymentService.charge() SUCCESS
    |
    +--> A crash trước offset commit
    |
    v
Rebalance -> B nhận offset 10
    |
    +--> paymentService.charge() AGAIN?
```

Kafka consumer group không thể tự rollback khoản tiền đã trừ ở một hệ thống HTTP bên ngoài. Cần **idempotency key ổn định** ở payment service hoặc cơ chế inbox/outbox.

### 15.1. Ví dụ inbox có unique constraint

Một cách chống trùng khi xử lý Kafka event vào database:

```sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(150) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Trong **một DB transaction**, ứng dụng có thể ghi dấu `event_id` và update business state. Nếu `event_id` đã tồn tại, xử lý theo quy tắc duplicate an toàn. Sau khi transaction nghiệp vụ commit thành công, container mới được phép commit tiến độ Kafka theo hợp đồng được cấu hình.

Không tách thao tác “insert inbox marker” và “ghi business state” thành hai transaction không được phối hợp rồi nghĩ rằng có exactly-once. Khi một transaction thành công nhưng transaction kia thất bại, vẫn có nguy cơ mất hoặc lặp công việc.

### 15.2. Kafka transactions không tự gộp mọi side effect

Với luồng **consume Kafka → process → produce Kafka**, transaction của Spring Kafka có thể phối hợp offset và các Kafka record đầu ra để đạt các bảo đảm phù hợp khi cấu hình đúng. Nhưng database, HTTP, email và hệ thống thanh toán bên ngoài **không tự tham gia cùng Kafka transaction**.

Nếu ứng dụng dùng transaction Kafka:

- Kiểm tra rollback/redelivery/after-rollback processor riêng.
- Observer Kafka dùng `isolation.level=read_committed` khi cần xem kết quả đã commit.
- Không hiểu rebalance test “giao đủ record” thành bằng chứng end-to-end exactly-once.
- Thử crash sau side effect nhưng trước commit để xác nhận sink có khả năng chống trùng.

## 16. Test nâng cao: gây rebalance khi một record đang xử lý

Bài test A→A+B→A ở phần 7 chuyển membership **sau khi dữ liệu mỗi giai đoạn đã được quan sát**. Để kiểm tra failure mode khó hơn, ta cần một worker đang xử lý dở:

```text
Time        Consumer A                         Consumer B
----        ----------                         ----------
T0          owns P0-P3
T1          polls event-42 on P2
T2          begins database/API work
T3                                             joins group
T4          rebalance / revoked or delayed
T5          processing ends, commit?
T6                                             may receive P2
T7                                             may redeliver event-42
```

Để mô phỏng có kiểm soát, dùng **`CountDownLatch`** trong test double cho phép A bị giữ ở một điểm xác định và chỉ nhả sau khi B join:

```java
CountDownLatch enteredHandler = new CountDownLatch(1);
CountDownLatch releaseHandler = new CountDownLatch(1);

void simulateSlowProcessing() throws InterruptedException {
    enteredHandler.countDown();
    if (!releaseHandler.await(15, TimeUnit.SECONDS)) {
        throw new IllegalStateException("TEST_HANDLER_TIMEOUT");
    }
}
```

Đây là **fixture minh họa**, không phải listener hoàn chỉnh. Đừng để `releaseHandler` không được giải phóng trong `finally`; test có thể treo. Cũng đừng dùng latch để giả lập toàn bộ semantics Kafka: nếu A còn xử lý trên poll thread, thời điểm coordinator xác định member/ownership phụ thuộc timeout và protocol, **không chắc partition lập tức chuyển cho B khi `b.start()`**.

Một test chính xác cần chủ động chọn kịch bản:

| Kịch bản | Cách kích hoạt | Điều phải xác minh |
| --- | --- | --- |
| B join khi A đang xử lý | Start B lúc A ở test latch | Không có hai owner đồng thời; processing/commit đúng policy |
| A vượt `max.poll.interval.ms` | Giữ handler lâu có timeout/test config rõ | Member mất khả năng tiến; record có thể redeliver |
| A crash sau DB commit | Worker process riêng bị dừng trước offset commit | Unique business result vẫn chỉ một |
| A graceful stop | Container stop với lifecycle hợp lệ | B nhận partition, lag hồi phục |
| Broker/network outage | Testcontainers/network fault trong lab riêng | Không mất bản ghi đã có contract durability |
| Transaction Kafka abort | Listener ném exception sau `KafkaTemplate.send` | Output aborted không visible với `read_committed` |

Đối với crash test, đừng dùng `kill -9` trên cùng JVM chạy JUnit. Một **controller test process** phải còn sống để điều khiển producer, quan sát group và đối soát sink sau khi worker process bị dừng.

### 16.1. Các assertion nên có cho crash test

- Record test được gửi với `eventId` ổn định.
- Worker A đã bắt đầu xử lý event theo một tín hiệu xác định.
- Side effect đã/đang được commit ở thời điểm được điều khiển.
- Worker A bị dừng theo fault injection đã chọn.
- Worker B tiếp nhận partition và, nếu cần, redeliver cùng topic-partition-offset.
- Sink chỉ có **một** business result hoặc một idempotency marker phù hợp.
- DLT/offset lag không bị bỏ qua âm thầm; recovery chạy tới kết quả cuối.

Không đòi `listener invocation count == 1` nếu thiết kế hướng at-least-once. **Có thể xử lý lại ở consumer nhưng không được tạo tác dụng phụ trùng tại sink**.

## 17. Những bài test sai dễ cho kết luận giả

| Anti-pattern | Vì sao sai? | Thay bằng |
| --- | --- | --- |
| Start B với group ID khác A | Hai group đọc độc lập, không cùng rebalance | Cùng `group.id` |
| Chỉ dùng `Thread.sleep(2000)` sau start | CI/broker scheduling không cố định | Wait condition với timeout |
| Gửi 4 key rồi giả định mỗi partition có 1 message | Hash không bảo đảm phân bố đều ở mẫu nhỏ | Gửi chỉ định partition trong test |
| Chỉ đếm callback revoke/assign | Callback khác theo eager/cooperative/protocol | Kiểm tra assignment thực |
| Giữ topic/group chung với test khác | Thành viên ngoài test làm thay đổi ownership | Isolate test context/topic/group |
| Dùng `pause()` để “buộc rebalance” | Pause không có nghĩa rời group | Start/stop member hoặc thay subscription |
| Assert mọi event được gọi đúng một lần | Rebalance/crash có thể tạo redelivery | So distinct event IDs và sink idempotency |
| Không ghi nhận committed offsets | Position đọc được không phải commit | Check group offset sau ổn định |
| Commit offset trước side effect | Crash có thể mất công việc | Commit sau outcome nghiệp vụ an toàn |
| Xử lý callback revoke bằng HTTP không timeout | Kéo dài group interruption | Flush nhẹ, bounded I/O, checkpoint |
| Coi graceful stop bằng crash | Không tái hiện session timeout/mất callback | Test process riêng/chaos |
| Coi lag 0 là không có duplicate | Offset tiến nhưng sink có thể ghi trùng | Reconcile event IDs, unique constraints |
| Coi group STABLE là toàn hệ thống thành công | Poison record/DB lỗi vẫn có thể tồn tại | Kiểm tra throughput, lag, sink, DLT |
| Đổi `group.instance.id` tùy ý khi scale | Trùng static ID, member fencing | ID duy nhất/ổn định theo topology |
| Dump raw key/value vào log rebalance | Có nguy cơ lộ dữ liệu nhạy cảm | Log topic, partition, offset, mã lỗi an toàn |

## 18. Checklist vận hành khi thấy rebalance liên tục

Nếu dashboard cho thấy group rebalance rất thường xuyên, trước khi tăng timeout hãy xác định **nguyên nhân gốc**:

1. **Membership:** pod có đang liên tục restart, autoscaling có dao động hay Deployment rollout đang xảy ra?
2. **Processing:** handler có block I/O khiến poll vượt giới hạn, thread có GC pause kéo dài không?
3. **Connection:** broker/client có lỗi network, DNS, TLS, authentication hoặc coordinator request timeout không?
4. **Assignment:** số partition, assignor/group protocol và subscription của member có đồng nhất không?
5. **Static membership:** có `group.instance.id` trùng nhau hoặc identity không ổn định không?
6. **Resource:** worker có đủ CPU, memory, DB connection, và downstream API quota không?
7. **Lag:** partition nào tăng lag, có liên quan đến một hot key hoặc poison message không?
8. **Commit:** có commit failure, `CommitFailedException`, `RebalanceInProgressException` hoặc lost partition không?
9. **Shutdown:** readiness/termination grace có cho consumer kết thúc hợp tác không?
10. **Data correctness:** business sink có duplicate hoặc missing event dù group đã hồi phục không?

Hướng xử lý có thể là ổn định autoscaling, giảm thời gian xử lý mỗi poll, bổ sung timeout/queue bền vững, dùng cooperative assignor hợp lý, cấu hình static membership phù hợp hoặc giảm số lượng consumer thừa. **Tăng session timeout cực lớn** chỉ làm phát hiện crash chậm và che một số triệu chứng, không giải quyết handler bị kẹt.

## 19. Bài thực hành mở rộng

Sau khi chạy được integration test cơ bản:

1. **Rebalance hai member:** dùng bốn partition, bắt đầu A rồi B, kiểm tra assignment tổng cộng luôn đủ bốn partition khi group ổn định.
2. **Scale down:** dừng B, xác nhận A nhận lại tất cả và xử lý đủ record của từng partition.
3. **Không nhầm group:** cố ý đổi `groupId` của B, giải thích vì sao không có rebalance giữa A và B mà mỗi group độc lập.
4. **Nhiều hơn số partition:** tạo sáu consumer member cho topic bốn partition, kiểm tra có member không được assigned partition.
5. **So eager/cooperative:** chạy lab lần lượt với `RangeAssignor` và `CooperativeStickyAssignor` trên cấu hình protocol phù hợp; so các callback revoked/assigned.
6. **Rebalance listener:** bổ sung trace với `ConsumerAwareRebalanceListener`, ghi lại thời gian, member và partition được thu hồi/cấp mới.
7. **Lag:** gửi một lượng record trong lúc thay member và so committed offset/lag trước, trong và sau rebalance.
8. **Slow handler:** dùng latch giữ một record đang xử lý, thêm member rồi quan sát rebalancing/timeout; bảo đảm giải phóng latch trong `finally`.
9. **Crash test:** tách consumer thành process/container khác, tạo crash trước commit, xác nhận record được giao lại và dữ liệu đích không trùng.
10. **External side effect:** cho handler insert một bảng với unique `event_id`, rồi mô phỏng redelivery. Chứng minh có thể nhận event nhiều lần nhưng business result chỉ một.
11. **Rolling deployment:** trên namespace lab, scale từ một lên hai replica rồi quay lại một, đo latency rebalance, lag và recovery time.
12. **Static membership:** nếu dùng StatefulSet, cấu hình ID tĩnh duy nhất và thử restart ngắn; so với dynamic membership nhưng không giả định mọi rebalance biến mất.
13. **Poison record:** gửi record khiến listener luôn lỗi, xác định DLT/recovery policy; quan sát lag tại partition đó khác với lag do rebalance.
14. **Báo cáo vận hành:** lập bảng mỗi lần test gồm tác nhân kích hoạt, số member/partition, thời gian mất/nhận ownership, lag trước/sau, số event distinct, số duplicate attempt và số business result.

## 20. Tổng kết

**Mô phỏng rebalance** giúp kiểm chứng điều mà một unit test gọi trực tiếp `@KafkaListener` không thể thấy: **ownership của partition thực sự chuyển như thế nào khi consumer member join, leave hoặc mất khả năng hoạt động**. Với Spring Kafka, `@EmbeddedKafka`, `KafkaListenerEndpointRegistry`, `MessageListenerContainer.getAssignedPartitions()` và listener callback cho phép dựng một bài lab rõ ràng mà không phải can thiệp production.

Rebalance không đồng nghĩa với mất dữ liệu, nhưng **khoảng chuyển quyền sở hữu** có thể làm tăng lag và redelivery nếu offset chưa commit. Vì vậy một thử nghiệm đáng tin cậy phải đo cả **assignment, tiến độ offset, dữ liệu được xử lý và tính idempotent của side effect**, đồng thời phân biệt graceful shutdown với crash, eager với cooperative và Kafka transaction với transaction của hệ thống ngoài. Khi những điểm này được kiểm thử và giám sát, rolling deployment/scale consumer sẽ dễ dự đoán và phục hồi an toàn hơn.
