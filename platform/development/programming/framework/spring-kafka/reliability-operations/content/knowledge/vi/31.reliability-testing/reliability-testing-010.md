# Test rebalance trong Spring Kafka: kiểm thử độ tin cậy của consumer group

## 1. Mục tiêu và bài toán

Trong một hệ thống nhận sự kiện qua Apache Kafka, Spring Kafka thường chạy nhiều consumer instance cùng `group.id` để chia tải. Khi một instance mới tham gia, một instance bị dừng, một consumer mất heartbeat hoặc số partition của topic thay đổi, Kafka có thể thực hiện **consumer group rebalance**: thu hồi và phân phối lại quyền đọc các partition.

Ở môi trường phát triển, một `@KafkaListener` duy nhất có thể chạy ổn định nhiều giờ. Nhưng khi đưa lên Kubernetes và tăng replica từ hai lên ba, hệ thống đột nhiên có bản ghi bị xử lý lặp, consumer lag tăng, offset commit thất bại hoặc một số partition ngừng được xử lý. Những tình huống ấy thường chỉ xuất hiện **ngay lúc thay đổi quyền sở hữu partition**.

Bài **“Test rebalance”** thuộc nhóm **Kiểm thử tin cậy** của module **Spring Kafka Reliability Operations** tập trung kiểm chứng hành vi ứng dụng khi consumer group thay đổi thành viên.

Sau bài học, bạn có thể:

1. Giải thích rebalance, partition assignment, revocation và quan hệ với `group.id`.
2. Phân biệt rebalance chủ động khi member gia nhập/rời nhóm với tình huống mất kết nối, process crash và vượt `max.poll.interval.ms`.
3. Dùng `spring-kafka-test` và embedded Kafka broker để tạo một integration test rebalance có kiểm soát.
4. Xác minh tất cả partition được phân công, không có hai member ổn định sở hữu cùng partition, và dữ liệu vẫn tiếp tục được tiêu thụ sau thay đổi thành viên.
5. Kiểm tra offset, retry, tính idempotent của business handler và giới hạn của bảo đảm at-least-once.
6. Quan sát callback `onPartitionsAssigned`, `onPartitionsRevoked` và trường hợp mất quyền sở hữu partition.
7. Tránh test flaky do giả định thứ tự partition, thời gian ngủ cố định, group ID dùng chung hoặc chờ sai sự kiện.
8. Thiết kế test tình huống rolling deployment, scale up/down, xử lý chậm và crash bằng hạ tầng phù hợp.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Kafka 3.x, Apache Kafka broker và JUnit 5. Tên API hoặc chiến lược group protocol có thể thay đổi theo bản Kafka/Spring Kafka; các ví dụ dưới đây nêu rõ giả định về môi trường test.

## 2. Rebalance là gì?

Một consumer group có thể gồm một hoặc nhiều consumer cùng `group.id`. Với topic có nhiều partition, mỗi partition được Kafka gán cho **tối đa một member trong cùng group tại một thời điểm khi trạng thái group đã ổn định**. Một consumer có thể sở hữu nhiều partition; nếu số consumer lớn hơn số partition, có consumer không nhận được partition nào.

Ví dụ topic `orders.events` có bốn partition:

```text
Trước khi scale:
  Consumer group: order-processors

  Member A
    ├── orders.events-0
    ├── orders.events-1
    ├── orders.events-2
    └── orders.events-3

Sau khi Member B gia nhập:
  Member A                      Member B
    ├── orders.events-0           ├── orders.events-2
    └── orders.events-1           └── orders.events-3
```

Phân phối chính xác phụ thuộc assignor, subscriptions và metadata; Kafka không cam kết mọi lần đều phân chia 0,1 cho A và 2,3 cho B như sơ đồ. Điều cần kiểm chứng là **tập partition được bao phủ đúng**, không chồng lấn khi assignment đã ổn định và ứng dụng xử lý tiếp được.

### Những sự kiện thường kích hoạt rebalance

| Tình huống | Ví dụ thực tế | Ý nghĩa kiểm thử |
| --- | --- | --- |
| Thêm member | Tăng replica hoặc tăng số consumer thread có cùng group | Partition có thể được chuyển từ member cũ sang member mới |
| Member rời nhóm có chủ đích | Rolling deploy gọi `stop()` và shutdown tử tế | Partition được trả lại nhóm tương đối nhanh |
| Consumer crash | Container bị kill, JVM mất mạng | Coordinator phát hiện mất thành viên qua heartbeat/session timeout hoặc cơ chế group tương ứng |
| Poll loop bị chặn quá lâu | Xử lý đồng bộ kéo dài vượt `max.poll.interval.ms` | Consumer có thể bị loại khỏi nhóm, mất quyền sở hữu |
| Thay đổi subscription/topic | Thêm topic, thay regex subscription | Assignment được tính lại |
| Thay đổi số partition | Topic tăng partition từ 4 lên 8 | Assignment cần bao phủ partition mới |
| Coordinator/group protocol thay đổi trạng thái | Broker/coordinator failover, các thay đổi group | Consumer cần hồi phục sau một giai đoạn bất ổn |

**Không phải mọi lần thay đổi cấu hình đều là rebalance.** Ví dụ `pause()` một consumer container thường chỉ tạm dừng poll/delivery theo cơ chế của container, không có nghĩa consumer đã rời group. Test pause/resume không thay thế test rebalance.

## 3. Các khái niệm để viết assertion đúng

- **Group member**: một consumer được coordinator quản lý trong consumer group.
- **TopicPartition**: cặp tên topic và số partition, ví dụ `orders.events-2`.
- **Assigned partitions**: tập partition một member được phép tiêu thụ ở trạng thái hiện tại.
- **Revoked partitions**: partition mà consumer đang chuyển giao/trả lại cho group theo callback.
- **Lost partitions**: partition mà consumer đã mất quyền sở hữu, có thể chưa kịp thực hiện đường revoke thông thường.
- **Offset**: vị trí bản ghi trong một partition; mỗi partition có sequence offset riêng.
- **Committed offset**: vị trí tiếp theo được ghi nhận cho group, thường dùng làm điểm bắt đầu khi một member khác tiếp quản.
- **Consumer position**: vị trí đọc tiếp của một consumer trong lúc chạy, không nhất thiết đồng bộ ngay với committed offset.
- **Lag**: chênh lệch giữa vị trí cuối topic và vị trí đã tiêu thụ/commit theo cách hệ thống giám sát định nghĩa.

Trong một bài test, không nên chỉ kiểm tra “consumer B đã start”. Một consumer có thể chạy nhưng chưa được group giao partition nào hoặc vẫn đang đợi assignment.

Cũng không nên coi việc nhận đủ số bản ghi ở một lần chạy là bằng chứng không có duplicate trong mọi kịch bản crash. Với mô hình at-least-once, việc đã xử lý business side effect nhưng chưa commit offset có thể khiến bản ghi được giao lại sau rebalance.

## 4. Những bất biến quan trọng cần kiểm thử

Đối với group tiêu thụ một topic có bốn partition và hai member đang hoạt động, nên kiểm tra:

| Bất biến | Assertion phù hợp | Điều tránh giả định |
| --- | --- | --- |
| Bao phủ partition | Hợp tập assignment của các member là đủ 4 partition | Không gắn cứng partition 0 luôn thuộc A |
| Không chồng quyền sở hữu khi ổn định | Giao hai tập assignment rỗng | Không assert trong giai đoạn chuyển tiếp |
| Consumer mới có thể nhận việc | Sau join, B được giao ít nhất một partition (với dữ liệu/assignor test phù hợp) | Không chỉ assert `isRunning()` |
| Member rời nhóm không làm kẹt partition | Khi B stop, A nhận lại toàn bộ partition | Không nhầm stop có chủ đích với crash |
| Dữ liệu tiếp tục được xử lý | Gửi event sau rebalance, nhận đủ business key | Không chỉ dựa vào callback assign |
| Có thể phục hồi offset | Sau commit và chuyển quyền, event mới vẫn được đọc; event cũ không bị bỏ qua ngoài chính sách | Không mặc định exactly-once |
| Kết quả nghiệp vụ đúng khi đọc lại | Business sink có khóa idempotency hoặc kiểm soát version | Không dùng tổng số callback làm số nghiệp vụ duy nhất |
| Giới hạn thời gian hợp lý | Chờ có timeout đến khi assignment ổn định | Không dùng `Thread.sleep(5000)` rồi đoán group đã ổn định |

Các bất biến nên được kiểm chứng tại **thời điểm group đã ổn định**. Trong lúc rebalance, callback và assignment tại mỗi member có thể cập nhật lệch thời gian. Test cần chờ tới điều kiện cuối mong muốn thay vì chụp một snapshot ngẫu nhiên.

## 5. Eager và cooperative rebalance ảnh hưởng đến test thế nào?

Kafka có nhiều chiến lược phân công partition. Hai kiểu cần hiểu:

**Eager rebalancing:** một lần rebalance có thể yêu cầu member trả lại các assignment trước khi nhận assignment mới. Ứng dụng có thể tạm dừng xử lý rộng hơn.

**Cooperative/incremental rebalancing:** một số partition tiếp tục nằm ở owner cũ; chỉ những partition cần chuyển mới được revoke qua một hoặc nhiều vòng. Điều này có thể giảm phạm vi gián đoạn khi membership thay đổi.

Ví dụ cấu hình consumer với assignor cooperative:

```properties
spring.kafka.consumer.properties.partition.assignment.strategy=org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

Khi dùng cơ chế này, **không assert rằng mọi partition của A đều phải bị revoke** mỗi lần B join. Chỉ một tập con có thể chuyển quyền.

Ngoài assignor, các phiên bản Kafka mới có thay đổi liên quan **consumer group protocol** và chiến lược assignment phía broker. Test nên ghi rõ Kafka broker version, consumer client version, protocol và assignor đang dùng. Không thể suy ra toàn bộ thứ tự callback cho mọi cấu hình chỉ từ một sơ đồ.

### Ý nghĩa của callback

Với Spring Kafka, `ConsumerAwareRebalanceListener` cho phép quan sát:

- `onPartitionsAssigned(Consumer, partitions)`: callback khi có assignment.
- `onPartitionsRevokedBeforeCommit(Consumer, partitions)`: callback trước bước commit liên quan revocation theo vòng đời container.
- `onPartitionsRevokedAfterCommit(Consumer, partitions)`: callback sau bước commit liên quan revocation.
- Callback mất partition khi phiên bản API hỗ trợ: giúp phân biệt revocation có kiểm soát với quyền sở hữu đã mất.

Đừng dùng một callback làm điều kiện duy nhất của test. Để kiểm chứng người nào đang sở hữu partition ở cuối rebalance, đọc trạng thái assignment từ container hoặc consumer metrics phù hợp.

## 6. Chọn mức độ test: unit, embedded broker, Testcontainers và staging

Không phải test nào cũng cần dựng cluster ba broker. Chọn đúng tầng giúp test nhanh và vẫn có ý nghĩa.

| Tầng | Mục đích | Giới hạn |
| --- | --- | --- |
| Unit test listener/handler | Kiểm tra logic khi nhận assigned/revoked, cleanup local state, idempotent handler | Không mô phỏng coordinator hoặc rebalance thật |
| Embedded Kafka integration test | Khởi tạo broker thật ngay trong test JVM, tạo group, join/leave, gửi và nhận message | Không mô phỏng đầy đủ lỗi mạng/container/process độc lập |
| Testcontainers hoặc cluster test riêng | Tạo broker và nhiều consumer process/container độc lập; kill, restart, network failure | Chậm và cần Docker/hạ tầng phù hợp |
| Staging/chaos test | Rolling deploy, autoscaling, coordinator disruption, lag và alert thực tế | Tốn tài nguyên, không dùng làm unit test trên mỗi commit |

Bài thực hành đầu tiên sẽ dùng **embedded broker** để kiểm chứng rebalance khi member gia nhập và rời nhóm có chủ đích. Các kịch bản crash và mất heartbeat được tách riêng vì chúng cần cơ chế fault injection khác.

## 7. Dependency cho integration test

Ví dụ project Gradle dùng Spring Boot 3.x và dependency versions do Spring Boot quản lý:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.awaitility:awaitility'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Các thành phần:

- `spring-kafka`: listener container, KafkaTemplate, consumer factory.
- `spring-kafka-test`: `@EmbeddedKafka`, `EmbeddedKafkaBroker`, các tiện ích `KafkaTestUtils` và `ContainerTestUtils`.
- `spring-boot-starter-test`: JUnit 5, AssertJ/Mockito và các tiện ích test theo phiên bản.
- `awaitility`: chờ điều kiện bất đồng bộ với timeout, thay vì `Thread.sleep` cố định.

Bạn có thể dùng `@SpringBootTest` nếu cần kiểm tra cấu hình `@KafkaListener` thực tế của ứng dụng. Bài test dưới đây sử dụng `@SpringJUnitConfig` và tự tạo listener container để điều khiển thành viên A/B một cách tường minh, không bị ảnh hưởng bởi các listener khác trong Spring Boot context.

## 8. Mô hình test chủ động tạo hai group member

Giả sử topic test có bốn partition:

```text
Embedded Kafka broker
  Topic: orders.rebalance.it
  Partitions: 0, 1, 2, 3

Group: rebalance-it-group
   |
   +-- Container A
   |     concurrency = 1
   |     groupId = rebalance-it-group
   |
   +-- Container B
         concurrency = 1
         groupId = rebalance-it-group
```

Chuỗi thử nghiệm:

1. Start A, chờ A được giao cả bốn partition.
2. Start B, chờ cả A và B được giao partition.
3. Kiểm tra tổng assignment bao phủ bốn partition và hai member không trùng nhau.
4. Publish một event trực tiếp vào mỗi partition, kiểm tra chúng được xử lý.
5. Stop B, chờ A nhận lại cả bốn partition.
6. Publish thêm event, kiểm tra ứng dụng tiếp tục tiêu thụ.
7. Dừng container và giải phóng producer trong `finally`.

Lựa chọn bốn partition giúp hai member đều có thể nhận việc mà không phải dựa vào thứ tự phân phối cụ thể.

## 9. Mẫu integration test rebalance với Spring Kafka

Đây là một test tự chứa dùng Spring Kafka 3.x, JUnit 5 và Awaitility. Để tập trung vào group assignment, nó tạo `ConcurrentMessageListenerContainer` trực tiếp thay vì một `@KafkaListener` tự động start.

```java
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;

import org.junit.jupiter.api.Test;

import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;
import org.springframework.kafka.listener.ConsumerAwareRebalanceListener;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.MessageListener;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(classes = RebalanceIntegrationTest.Config.class)
@EmbeddedKafka(
    partitions = 4,
    topics = "orders.rebalance.it"
)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class RebalanceIntegrationTest {

    private static final String TOPIC = "orders.rebalance.it";
    private static final String GROUP = "rebalance-it-group";

    @Autowired
    EmbeddedKafkaBroker broker;

    @Configuration
    static class Config {
    }

    private ConcurrentMessageListenerContainer<String, String>
    newMember(
            ConsumerFactory<String, String> consumerFactory,
            String memberName,
            ConcurrentMap<String, String> receivedBy,
            List<String> transitions) {

        ContainerProperties properties =
            new ContainerProperties(TOPIC);

        properties.setGroupId(GROUP);
        properties.setAckMode(ContainerProperties.AckMode.RECORD);

        properties.setMessageListener(
            (MessageListener<String, String>) record ->
                receivedBy.put(record.key(), memberName)
        );

        properties.setConsumerRebalanceListener(
            new ConsumerAwareRebalanceListener() {

                @Override
                public void onPartitionsAssigned(
                        Consumer<?, ?> consumer,
                        Collection<TopicPartition> partitions) {

                    transitions.add(
                        memberName + ":ASSIGNED:" + partitions
                    );
                }

                @Override
                public void onPartitionsRevokedBeforeCommit(
                        Consumer<?, ?> consumer,
                        Collection<TopicPartition> partitions) {

                    transitions.add(
                        memberName + ":REVOKED:" + partitions
                    );
                }
            }
        );

        ConcurrentMessageListenerContainer<String, String> container =
            new ConcurrentMessageListenerContainer<>(
                consumerFactory, properties
            );

        container.setBeanName(memberName);
        container.setConcurrency(1);
        return container;
    }

    private static Set<TopicPartition> assigned(
            ConcurrentMessageListenerContainer<?, ?> container) {

        Collection<TopicPartition> current =
            container.getAssignedPartitions();

        return current == null
            ? Set.of()
            : Set.copyOf(current);
    }

    @Test
    void reassignsPartitionsOnJoinAndLeave()
            throws Exception {

        Map<String, Object> consumerProps =
            new HashMap<>(
                KafkaTestUtils.consumerProps(
                    GROUP, "false", broker
                )
            );

        consumerProps.put(
            "auto.offset.reset", "earliest"
        );

        DefaultKafkaConsumerFactory<String, String> consumerFactory =
            new DefaultKafkaConsumerFactory<>(
                consumerProps,
                new StringDeserializer(),
                new StringDeserializer()
            );

        DefaultKafkaProducerFactory<String, String> producerFactory =
            new DefaultKafkaProducerFactory<>(
                KafkaTestUtils.producerProps(broker),
                new StringSerializer(),
                new StringSerializer()
            );

        KafkaTemplate<String, String> producer =
            new KafkaTemplate<>(producerFactory);

        ConcurrentMap<String, String> receivedBy =
            new ConcurrentHashMap<>();

        List<String> transitions =
            new CopyOnWriteArrayList<>();

        ConcurrentMessageListenerContainer<String, String> a =
            newMember(
                consumerFactory, "A", receivedBy, transitions
            );

        ConcurrentMessageListenerContainer<String, String> b =
            newMember(
                consumerFactory, "B", receivedBy, transitions
            );

        try {
            // Ban đầu nhóm chỉ có member A.
            a.start();

            await()
                .atMost(Duration.ofSeconds(30))
                .untilAsserted(() ->
                    assertEquals(4, assigned(a).size())
                );

            // Member B gia nhập, Kafka phân công lại partition.
            b.start();

            await()
                .atMost(Duration.ofSeconds(30))
                .untilAsserted(() -> {
                    Set<TopicPartition> pa = assigned(a);
                    Set<TopicPartition> pb = assigned(b);

                    assertFalse(pa.isEmpty());
                    assertFalse(pb.isEmpty());
                    assertTrue(Collections.disjoint(pa, pb));

                    Set<TopicPartition> all =
                        new HashSet<>(pa);

                    all.addAll(pb);
                    assertEquals(4, all.size());
                });

            // Gửi trực tiếp một message tới mỗi partition.
            for (int partition = 0; partition < 4; partition++) {
                String key = "after-join-" + partition;

                producer.send(
                    TOPIC, partition, key, "payload"
                ).get(10, TimeUnit.SECONDS);
            }

            await()
                .atMost(Duration.ofSeconds(30))
                .untilAsserted(() -> {
                    for (int partition = 0; partition < 4; partition++) {
                        assertTrue(
                            receivedBy.containsKey(
                                "after-join-" + partition
                            )
                        );
                    }
                });

            // B rời group có chủ đích.
            b.stop();

            await()
                .atMost(Duration.ofSeconds(30))
                .untilAsserted(() ->
                    assertEquals(4, assigned(a).size())
                );

            producer.send(
                TOPIC, 3, "after-leave", "payload"
            ).get(10, TimeUnit.SECONDS);

            await()
                .atMost(Duration.ofSeconds(30))
                .untilAsserted(() ->
                    assertTrue(
                        receivedBy.containsKey("after-leave")
                    )
                );

            assertTrue(
                transitions.stream()
                    .anyMatch(t -> t.startsWith("B:ASSIGNED:"))
            );

        } finally {
            if (b.isRunning()) {
                b.stop();
            }

            if (a.isRunning()) {
                a.stop();
            }

            producerFactory.destroy();
        }
    }
}
```

### Test đã chứng minh điều gì?

- Có một Kafka broker và một consumer group thực sự tham gia giao thức group.
- A nhận đủ partition khi chạy một mình.
- B gia nhập và group chuyển sang trạng thái có hai owner, không chồng lấn assignment khi điều kiện chờ được thỏa.
- Sau khi phân công, producer gửi được message tới bốn partition và handler nhận các key tương ứng.
- Khi B dừng tử tế, A nhận lại toàn bộ partition và tiếp tục xử lý message mới.

### Test chưa chứng minh điều gì?

- Không giả lập process crash hoặc mất mạng; `b.stop()` là **graceful leave**.
- Không đo chính xác thời gian failover khi heartbeat timeout.
- Không kiểm chứng exactly-once end-to-end.
- Không kiểm tra side effect của business handler vì ví dụ chỉ ghi nhận key trong `ConcurrentHashMap`.
- Không test một `@KafkaListener` cụ thể trong ứng dụng production.
- Không bảo đảm callback sẽ xuất hiện cùng một thứ tự trong mọi assignor và Kafka protocol.

**Lưu ý:** `receivedBy.put(key, memberName)` làm mất thông tin số lần giao lại một key. Nó chỉ phù hợp để kiểm tra **có event được tiêu thụ**. Muốn kiểm tra duplicate, cần một bộ đếm theo key hoặc bảng nghiệp vụ có idempotency key.

## 10. Vì sao dùng Awaitility thay vì Thread.sleep?

Rebalance là quy trình bất đồng bộ: member phải khởi động, subscribe, poll, phối hợp với coordinator và nhận assignment. Thời gian thực hiện phụ thuộc CPU, broker test và cả CI runner.

Test dễ flaky nếu dùng:

```java
b.start();
Thread.sleep(3000);
assertEquals(2, assigned(a).size());
```

Có hai vấn đề:

1. Ba giây có thể quá ngắn trên CI chậm hoặc quá dài khi chạy local.
2. Con số đúng `2` không phải lúc nào cũng là điều kiện cần trong một topology khác; policy assignment có thể khác kỳ vọng cứng.

Cách tốt hơn:

```java
b.start();

await()
    .atMost(Duration.ofSeconds(30))
    .untilAsserted(() -> {
        Set<TopicPartition> pa = assigned(a);
        Set<TopicPartition> pb = assigned(b);

        assertFalse(pa.isEmpty());
        assertFalse(pb.isEmpty());

        Set<TopicPartition> all = new HashSet<>(pa);
        all.addAll(pb);

        assertTrue(Collections.disjoint(pa, pb));
        assertEquals(4, all.size());
    });
```

Test chờ **điều kiện hệ thống cần đạt**, có timeout hữu hạn. Nếu timeout, báo cáo lỗi rõ hơn khi biết tập assignment cuối cùng của A/B thay vì chỉ thấy assertion thất bại sau một khoảng ngủ.

Tránh đặt timeout vài trăm mili-giây cho CI. Cũng tránh timeout quá dài khiến một bug thật tốn nhiều phút để phát hiện. Khoảng 20–60 giây thường là điểm bắt đầu phù hợp cho embedded group test, sau đó điều chỉnh dựa trên môi trường và startup thực tế.

## 11. Quan sát rebalance khi dùng @KafkaListener

Trong ứng dụng thật, consumer thường được tạo bởi `@KafkaListener`:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @KafkaListener(
        id = "order-events-listener",
        topics = "orders.events",
        groupId = "order-processors",
        containerFactory = "kafkaListenerContainerFactory"
    )
    public void handle(ConsumerRecord<String, String> record) {
        // Xử lý nghiệp vụ theo record.key() và record.value().
    }
}
```

Để quan sát assignment của một listener cụ thể, có thể lấy container từ `KafkaListenerEndpointRegistry`:

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;

MessageListenerContainer container =
    registry.getListenerContainer("order-events-listener");
```

`registry` giả định là một bean `KafkaListenerEndpointRegistry` đã được inject. Bạn có thể dùng `container.start()`/`stop()` trong test kiểm soát vòng đời của listener. Tuy nhiên, muốn test hai member cùng group, phải có **hai consumer thực sự** — chẳng hạn hai container độc lập, hai listener instance có `groupId` giống nhau, hoặc hai application instance.

Cẩn thận: ID của `@KafkaListener` là ID của endpoint/container. Khi một listener không chỉ định `groupId` rõ ràng, thuộc tính ID có thể ảnh hưởng group ID theo cơ chế annotation. Trong bài test về rebalance, luôn ghi rõ `groupId` để không vô tình tạo hai group khác nhau.

### Đăng ký ConsumerAwareRebalanceListener trên container factory

Ví dụ một cấu hình factory có callback quan sát:

```java
import java.util.Collection;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ConsumerAwareRebalanceListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderKafkaContainerConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(
            OrderKafkaContainerConfiguration.class
        );

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
    orderKafkaContainerFactory(
            ConsumerFactory<String, String> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<
                String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(2);

        factory.getContainerProperties()
            .setConsumerRebalanceListener(
                new ConsumerAwareRebalanceListener() {

                    @Override
                    public void onPartitionsAssigned(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {

                        log.info(
                            "event=kafka.partitions.assigned partitions={}",
                            partitions
                        );
                    }

                    @Override
                    public void onPartitionsRevokedBeforeCommit(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {

                        log.info(
                            "event=kafka.partitions.revoked partitions={}",
                            partitions
                        );
                    }
                }
            );

        return factory;
    }
}
```

Listener sử dụng factory này cần khai báo `containerFactory="orderKafkaContainerFactory"`. Ví dụ cho thấy cách quan sát lifecycle, không bắt buộc mọi ứng dụng phải log chi tiết danh sách partition ở mức `INFO` liên tục. Khi group có nhiều topic/partition và rebalance thường xuyên, cần kiểm soát lượng log.

**Không làm công việc chậm, gọi API với timeout dài hoặc chờ lock tùy tiện trong callback rebalance.** Callback được thực hiện theo luồng poll/consumer; việc chặn lâu có thể làm trì hoãn group và gây thêm lần rebalance khác.

## 12. Offset là trọng tâm của độ tin cậy khi rebalance

Giả sử một partition có các record với offset 100, 101, 102. Consumer A nhận 100 và cập nhật database, nhưng process bị dừng trước khi offset tương ứng được commit.

```text
Partition 0:  ... 100 101 102 ...

Consumer A:
  poll offset 100
  xử lý và ghi business DB -> COMMITTED
  chưa commit Kafka offset 101
                |
                X process crash
                |
                v
Consumer B nhận Partition 0:
  đọc từ committed offset cũ
  có thể nhận lại offset 100
```

Đó là lý do **at-least-once delivery có thể dẫn đến duplicate processing**. Rebalance không tự tạo exactly-once ở database hoặc API ngoài Kafka.

### Những offset cần phân biệt

| Giá trị | Ý nghĩa |
| --- | --- |
| `record.offset()` | Offset của record đang xử lý |
| Consumer position | Vị trí đọc tiếp của consumer trong phiên hiện tại |
| Committed offset | Offset tiếp theo đã lưu cho group |
| End offset | Vị trí cuối hiện tại của partition |
| Business processed key | Dấu vết ứng dụng đã hoàn tất side effect nào |

Không nên khẳng định “consumer đã nhận message” là “offset đã commit”. Thời điểm nhận record, hoàn tất handler, hoàn tất transaction nghiệp vụ và commit Kafka offset là các sự kiện khác nhau.

### AckMode và auto-commit

Trong ví dụ test, `KafkaTestUtils.consumerProps(GROUP, "false", broker)` sử dụng cấu hình auto-commit bị tắt; container đặt `AckMode.RECORD` để container quản lý commit theo vòng đời record.

Ở Spring Kafka, cần xem cấu hình:

- `enable.auto.commit` phía Kafka consumer.
- `ContainerProperties.AckMode` ở listener container.
- Sử dụng acknowledgment thủ công nếu có.
- Transaction manager/kafka transaction nếu dùng.
- Error handler, retry topic/DLT và hành vi seek/recover.

Không nên trộn auto-commit, manual ack và transaction một cách không chủ đích. Mỗi mô hình có ranh giới xác nhận khác nhau.

## 13. Kiểm thử dữ liệu không mất sau chuyển quyền

Một integration test nên gửi nhiều record vào **từng partition**, sau đó rebalance và kiểm tra mọi business key đã được xử lý cuối cùng.

Ví dụ gửi một record đúng partition:

```java
for (int partition = 0; partition < 4; partition++) {
    producer.send(
        "orders.rebalance.it",
        partition,
        "event-" + partition,
        "payload"
    ).get(10, TimeUnit.SECONDS);
}
```

Khi muốn kiểm tra toàn bộ một batch 100 record, hãy dùng key duy nhất theo nghiệp vụ như `orderId + eventVersion` và một bộ lưu kết quả có thể truy vấn theo key.

Các assertion phù hợp:

1. Mọi key đã publish được ghi nhận thành công ở output trong thời hạn.
2. Một khi group ổn định, mỗi partition có một owner cuối cùng.
3. Khi một member dừng, các partition của nó chuyển sang member khác.
4. Ở chế độ at-least-once, nếu test cố tình tạo vùng lỗi quanh commit, trùng xử lý có thể xuất hiện nhưng **business output vẫn đúng** nhờ idempotency.
5. Không có partition nào giữ lag tăng mãi sau khi group ổn định.

Điều này khác với một assertion quá mạnh:

```java
assertEquals(100, callbackInvocationCount.get());
```

Nếu bài test thực sự mô phỏng crash/rollback quanh commit, 100 business event duy nhất có thể gây hơn 100 lần gọi callback. Số callback không phải số side effect hợp lệ. Hãy kiểm tra business key hoặc kết quả dữ liệu cuối.

## 14. Test idempotent processing quanh rebalance

Một phương án hữu ích là writer bảo vệ kết quả theo **business idempotency key**. Với event mang `eventId` và phiên bản:

```sql
CREATE TABLE processed_kafka_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
```

Ứng dụng xử lý trong một transaction database:

```java
@Transactional
public void applyOrderEvent(OrderEvent event) {
    int inserted = jdbc.update(
        """
        INSERT INTO processed_kafka_event (
            consumer_name, event_id
        )
        VALUES (?, ?)
        ON CONFLICT (consumer_name, event_id)
        DO NOTHING
        """,
        "order-projection",
        event.eventId()
    );

    if (inserted == 0) {
        // Sự kiện này đã được áp dụng thành công trước đó.
        return;
    }

    jdbc.update(
        """
        INSERT INTO order_projection (
            order_id, current_status
        )
        VALUES (?, ?)
        ON CONFLICT (order_id)
        DO UPDATE SET
            current_status = EXCLUDED.current_status
        """,
        event.orderId(),
        event.status()
    );
}
```

Đoạn mã giả định có `JdbcTemplate jdbc`, mô hình `OrderEvent`, bảng `order_projection` và transaction manager JDBC phù hợp. SQL sử dụng PostgreSQL. Trong cùng transaction, insert marker và cập nhật projection commit/rollback cùng nhau trên một datasource.

**Cần lưu ý thứ tự event và tính đơn điệu của version.** Nếu một event cũ được phát lại sau event mới, upsert không điều kiện có thể làm trạng thái quay ngược. Với projection yêu cầu thứ tự/phiên bản, thêm `eventVersion` và chỉ cập nhật khi version mới hơn; marker chống duplicate chỉ giải quyết một phần bài toán.

### Kiểm thử vùng lỗi giữa business commit và offset commit

Để kiểm tra thiết kế idempotent thực sự, bài test có thể:

1. Tạo consumer A nhận event X.
2. Cho DB transaction xử lý X và commit thành công.
3. Gây mất process/consumer **trước khi Kafka offset của X được commit**.
4. Cho member B tiếp quản partition.
5. Xác nhận X có thể được giao lại.
6. Kiểm tra bảng `processed_kafka_event` chỉ có một marker hợp lệ và projection không bị áp dụng trùng.

Điểm số 3 đòi hỏi fault injection đúng vị trí; **không thể bảo đảm bằng cách gọi `container.stop()` ngẫu nhiên sau một `Thread.sleep`**. Graceful stop có thể chờ handler kết thúc và commit offset trước khi consumer rời nhóm.

Có thể dùng consumer process/container độc lập và kill process, kết hợp cổng chặn có tín hiệu/điểm fault injection của ứng dụng. Test cần chứng minh committed offset thực tế vẫn ở vị trí cũ trước khi kỳ vọng replay.

## 15. Test graceful leave khác test consumer crash

Hai kịch bản thường bị nhầm:

### Graceful leave

```text
Member B đang chạy
      |
      v
container.stop()
      |
      v
Đóng/leave group có kiểm soát
      |
      v
Coordinator phân phối lại partition
      |
      v
Member A tiếp quản
```

Lợi ích của test:

- Đánh giá rolling deployment thông thường.
- Kiểm tra callback revoke/assign.
- Kiểm tra container cleanup và tiếp tục tiêu thụ sau shutdown.
- Có thể thực hiện nhanh trong embedded integration test.

Nhưng graceful leave không đại diện chính xác việc **mất điện, SIGKILL hoặc mất mạng hoàn toàn**.

### Crash hoặc mất heartbeat

```text
Member B đang chạy
      |
      X mất process / mất kết nối
      |
      v
Coordinator chờ phát hiện membership failure
      |
      v
Member B mất ownership
      |
      v
Member A được assign partition
      |
      v
Có thể đọc lại record chưa commit
```

Test cần dùng Testcontainers, một tiến trình độc lập hoặc môi trường staging có khả năng kill/network partition. Cần quan sát session timeout và group protocol thực sự đang dùng, không giả định mọi bản Kafka đều áp dụng đúng một công thức timeout giống nhau.

### Ma trận kỳ vọng

| Kịch bản | Cách kích hoạt | Điều quan trọng |
| --- | --- | --- |
| Join | Start B cùng group | Assignment phân chia, tiếp tục xử lý |
| Leave | Stop B tử tế | A tiếp quản, không kẹt partition |
| Crash | Kill process B, không gửi graceful close | Timeout/failover, replay và idempotency |
| Network partition | Chặn đường kết nối giữa B và broker | Phát hiện mất membership, phản ứng khi tái kết nối |
| Poll timeout | Block processing vượt max poll interval có kiểm soát | Lost assignment, commit failure/recovery và kết quả xử lý |
| Scale down | Giảm số replica | Lag ổn định trở lại, không bỏ sót |
| Rolling upgrade | Thay tuần tự nhiều member | Tối thiểu gián đoạn theo strategy, không sai dữ liệu |

## 16. Test xử lý chậm và max.poll.interval.ms

Kafka consumer cần gọi `poll()` đủ thường xuyên. Nếu xử lý đồng bộ một batch quá lâu và không quay lại poll trong khoảng giới hạn, group có thể xem member không còn khả năng tiến triển.

Các property thường cần hiểu:

```properties
spring.kafka.consumer.properties.max.poll.interval.ms=300000
spring.kafka.consumer.properties.session.timeout.ms=45000
spring.kafka.consumer.max-poll-records=500
```

Các giá trị là **ví dụ cấu hình**, không phải khuyến nghị dùng y nguyên cho mọi workload. Hiệu lực của session timeout và heartbeat phụ thuộc group protocol và Kafka version. Những bản Kafka mới có thể quản lý timeout theo group protocol/broker khác với mô hình classic.

Bài test có thể sử dụng một message listener giả lập chờ tại một `CountDownLatch`:

```java
CountDownLatch handlerEntered = new CountDownLatch(1);
CountDownLatch releaseHandler = new CountDownLatch(1);

MessageListener<String, String> slowHandler = record -> {
    handlerEntered.countDown();

    boolean released;
    try {
        released = releaseHandler.await(
            20, TimeUnit.SECONDS
        );
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException(
            "Handler interrupted", ex
        );
    }

    if (!released) {
        throw new IllegalStateException(
            "Controlled test timeout"
        );
    }
};
```

Để test `max.poll.interval.ms`, dùng ngưỡng **ngắn và phù hợp môi trường test**, nhưng tránh cấu hình quá thấp làm member bị loại ngay khi CI chậm. Sau khi xác nhận handler đang xử lý bằng `handlerEntered.await(...)`, giữ nó đủ lâu để tạo tình huống mục tiêu, quan sát assignment rồi release trong `finally`.

Trong Spring Kafka, container có thể sử dụng cơ chế pause để duy trì poll khi listener xử lý bất đồng bộ; do đó cần hiểu cách ứng dụng thật tiêu thụ và ack. Không suy ra mọi handler chậm luôn dẫn đến rebalance.

### Điều không nên làm

- Không khóa vô thời hạn thread trong test.
- Không phụ thuộc tuyệt đối vào `Thread.sleep()` để tạo đúng thời điểm callback.
- Không giảm timeout đến mức test thất bại ngẫu nhiên trên máy CI.
- Không gọi API mạng thật từ callback listener khi chỉ cần mô phỏng lỗi.
- Không nhầm `max.poll.interval.ms` với `session.timeout.ms` — một cái liên quan tiến độ poll, một cái liên quan phát hiện thành viên không còn đáp ứng group heartbeat/protocol.

## 17. Rebalance và thứ tự xử lý theo key

Kafka bảo đảm thứ tự record **trong một partition** theo offset khi đọc tuần tự; nó không bảo đảm một thứ tự tổng thể giữa các partition.

Nếu record cùng `orderId` được gửi với key ổn định và cùng partitioner, chúng thường đi vào cùng partition (trong điều kiện cấu hình số partition/partitioner nhất quán). Khi partition chuyển owner vì rebalance, member mới tiếp tục đọc theo offset đã commit của group.

Nhưng thứ tự hiệu quả ở business sink còn phụ thuộc:

- Retry/seek có đưa một record cũ vào xử lý lại không?
- Handler có xử lý bất đồng bộ và trả ack trước khi công việc thực sự hoàn tất không?
- Một record lỗi được gửi sang retry topic, gây thay đổi thứ tự so với topic chính không?
- Event có version để tránh trạng thái cũ ghi đè trạng thái mới không?
- Producer có thay đổi key, partition count hoặc partitioner giữa các lần phát không?

### Test thứ tự đơn giản

Gửi lần lượt vào cùng partition:

```text
order-42 version 1
order-42 version 2
order-42 version 3
```

Cho consumer A tiêu thụ một phần, sau đó thêm B hoặc chuyển ownership có kiểm soát. Cuối cùng kiểm tra business projection không bị giảm version và mọi version cần thiết đã được phản ánh.

Nếu mục tiêu là xác minh **strict processing order**, handler cần ghi lại danh sách offset/version theo từng partition; đừng đánh giá bằng timestamp từ log của nhiều thread, vì log có thể xen kẽ.

## 18. Test với retry, DLT và error handler

Trong hệ thống có lỗi nghiệp vụ/hạ tầng, rebalance có thể xảy ra khi container đang retry record hoặc xử lý DLT.

Những cơ chế cần phân biệt:

- `DefaultErrorHandler` với seek/retry có giới hạn trong listener container.
- Non-blocking retry thông qua retry topics, nếu ứng dụng sử dụng.
- Dead-letter publishing qua `DeadLetterPublishingRecoverer`.
- Kafka transaction và ranh giới commit offset.
- Manual acknowledgment và trạng thái record chưa ack.

Một kịch bản test đáng giá:

1. A đang xử lý record X; handler ném lỗi tạm thời.
2. Trước hoặc trong retry, B gia nhập group.
3. Partition chứa X có thể chuyển owner.
4. X cuối cùng được xử lý thành công hoặc gửi tới DLT theo policy đã cấu hình.
5. Hệ thống không bị lặp retry vô hạn, không mất message và không tạo side effect trùng.

**Không mặc định rằng việc gửi X vào DLT đồng nghĩa business X đã được xử lý thành công.** DLT là kênh cách ly/lưu dấu vết lỗi. Test nên kiểm tra cả trạng thái đầu ra, số retry, DLT record và committed offset.

Với Spring Kafka và Kafka transaction, exactly-once có giới hạn phạm vi: các thao tác consume-transform-produce trong Kafka transaction có thể được phối hợp với offset commit, nhưng tác động tới HTTP hoặc database ngoài Kafka không tự được bảo đảm exactly-once. Cần idempotency/outbox hoặc cơ chế kết hợp riêng.

## 19. Static membership, cooperative assignor và rolling deployment

Một số hệ thống sử dụng static membership với `group.instance.id` để giảm những lần rebalance không cần thiết khi cùng member khởi động lại nhanh.

Khái niệm:

```text
Dynamic membership:
  member rời nhóm và quay lại thường có identity
  được coordinator xử lý theo phiên mới.

Static membership:
  member có group.instance.id ổn định,
  coordinator có thể nhận diện cùng logical member.
```

Static membership không loại bỏ mọi rebalance và có thể làm việc tiếp quản chậm hơn trong một số tình huống crash vì coordinator chờ timeout. Khi test, cần cấu hình ID duy nhất cho mỗi live member; hai consumer cùng `group.instance.id` có thể gây fencing hoặc lỗi membership.

Với rolling deployment:

- Ghi nhận thời điểm member A bị dừng.
- Xác định partition được giao lại cho B/C.
- Theo dõi consumer lag và thời gian phục hồi.
- Kiểm tra không có side effect trùng ở dữ liệu nghiệp vụ.
- Lặp lại khi một thành viên bị kill thay vì dừng tử tế.

Việc dùng cooperative assignment, static membership và thời gian shutdown tối ưu cần được quyết định dựa trên đo đạc thực tế. Không nên tăng mọi timeout chỉ để test “pass”, vì điều đó có thể kéo dài thời gian khôi phục sau crash.

## 20. Quan sát rebalance qua log và metric

Để điều tra sau test, thông điệp log nên giúp liên hệ **group, member, topic, partition và thời điểm**.

Ví dụ:

```text
INFO event=kafka.member.started group=order-processors member=pod-A
INFO event=kafka.partitions.assigned group=order-processors member=pod-A partitions=[orders.events-0,orders.events-1]
INFO event=kafka.partitions.revoked group=order-processors member=pod-A partitions=[orders.events-1]
INFO event=kafka.partitions.assigned group=order-processors member=pod-B partitions=[orders.events-1]
INFO event=kafka.message.handled group=order-processors partition=1 offset=321 eventId=evt-42
```

Trường hữu ích:

| Trường | Vai trò |
| --- | --- |
| `groupId` | Group đang rebalance |
| `memberName` hoặc instance ID | Node/container xử lý |
| `topic` và `partition` | Quyền sở hữu partition |
| `event` | Assigned/revoked/lost/handled/committed |
| `offset` | Vị trí record |
| `eventId` | Correlation đến business outcome |
| `timestamp` | Phân tích khoảng ngưng xử lý |
| `exceptionType` | Lỗi commit, poll, handler hoặc coordinator |
| `lag` | Độ trễ tiêu thụ theo metric được định nghĩa |

Metric quan trọng có thể gồm:

- Số lần consumer group rebalance trong một khoảng thời gian.
- Thời gian rebalance và thời gian không có tiến triển.
- Consumer lag trước, trong và sau rebalance.
- Số partition đang được gán trên mỗi member.
- Tần suất commit failure/retry.
- Thời gian xử lý record và poll loop.
- Số business event duy nhất được xử lý và số lần delivery trùng.

Các metric cụ thể phụ thuộc Kafka client, Micrometer và cấu hình instrumentation; không giả định mọi tên metric đều tự xuất hiện chỉ vì có Spring Kafka. Một số số liệu như ownership của từng partition cần lấy từ container/Kafka AdminClient hoặc metric exporter.

**Không dùng event ID riêng cho từng message làm label metric time series** nếu muốn tránh cardinality lớn. Event ID thích hợp hơn trong log, trace hoặc bảng audit.

## 21. Những nguyên nhân khiến test rebalance flaky

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Test timeout khi chờ assignment | Broker chưa sẵn sàng hoặc consumer chưa poll | Chờ điều kiện thực, tăng timeout hợp lý, xem broker logs |
| A vẫn giữ cả bốn partition sau B.start | B chưa join đúng group hoặc group ID khác | Kiểm tra `group.id`, subscription, container state |
| Hai member đều không nhận partition | Không có topic, metadata chưa sẵn sàng, config sai | Tạo topic trước, xem startup/consumer errors |
| Test đòi A luôn có partition 0,1 | Assignment phụ thuộc assignor | Assert union, disjoint và nonempty |
| Callback revoke xảy ra nhiều lần | Nhiều vòng assignment/cooperative strategy | Không đếm “đúng một lần” nếu không có căn cứ |
| Không thấy revoke ở tình huống kỳ vọng | Listener chưa đăng ký, group protocol khác, callback khác | Kiểm tra wiring và quan sát assignment cuối |
| Stop() không tái hiện duplicate | Graceful shutdown commit offset | Dùng process kill/fault injection để test crash |
| Event cũ từ lần test trước xuất hiện | Group ID/topic/offset cũ hoặc test dùng broker chung | Isolate group ID/topic, cleanup context |
| `auto.offset.reset=latest` khiến test bỏ qua event | Producer gửi trước khi consumer được assign | Dùng earliest cho test hoặc gửi sau assignment |
| `@KafkaListener` tự start ngoài ý muốn | Context tạo nhiều consumer không kiểm soát | Tắt auto startup hoặc test trực tiếp container riêng |
| Test pass local nhưng fail CI | Thread scheduling, startup, CPU khác nhau | Awaitility, timeout, resource limits, diagnostics |
| Topic chỉ có một partition | Member thứ hai không có partition | Tạo nhiều partition hơn số member cần quan sát |
| `max.poll.interval.ms` quá thấp | Test environment chậm hơn dự tính | Điều chỉnh ngưỡng và có tín hiệu chính xác |
| Không thấy record sau rebalance | Consumer chưa commit, error handler đang retry hoặc paused | Xem committed offset, assignment, pause, logs |
| Đếm callback bằng đúng số message publish | Redelivery/retry làm tăng callback | Assert business key duy nhất |
| Test order fail dù Kafka giữ order trong partition | Handler bất đồng bộ/retry topic làm thay đổi thứ tự business | Test theo partition/version và chính sách xử lý |
| Duplicate xuất hiện ở DB | Side effect commit trước Kafka offset | Unique key, idempotency marker, transactional design |
| Test chạy nhiều lần để lại container | Thiếu `finally` cleanup, context không đóng | Stop container và destroy producer |
| Static member bị fenced | Trùng `group.instance.id` | Mỗi live member một ID riêng |
| Lag tăng sau rebalance | Member chưa được assign, backpressure hoặc writer chậm | Đo poll, DB latency, assignment và queue |

## 22. Ma trận kiểm thử độ tin cậy có thể dùng cho dự án

Để biến bài học thành một bộ kiểm thử có hệ thống:

| Mã test | Kịch bản | Kỳ vọng về assignment | Kỳ vọng về dữ liệu |
| --- | --- | --- | --- |
| RB-01 | Một member khởi động | A nhận toàn bộ partition | Các event sau đó được xử lý |
| RB-02 | Thêm member B | A/B cùng nhận một phần, không chồng | Không mất event |
| RB-03 | Dừng B tử tế | A lấy lại toàn bộ partition | Tiếp tục xử lý event mới |
| RB-04 | Stop A khi B đang chạy | B tiếp quản các partition của A | Không mất event; output đúng |
| RB-05 | Hai member start gần nhau | Group ổn định | Không có duplicate side effect |
| RB-06 | Kill consumer process | Coordinator phát hiện mất member | Replay được xử lý idempotent |
| RB-07 | Xử lý vượt poll interval | Member có thể mất quyền sở hữu | Có recovery rõ ràng |
| RB-08 | Retry trong lúc join | Assignment thay đổi theo policy | Record xử lý hoặc DLT đúng kỳ vọng |
| RB-09 | Gửi theo cùng key trong một partition | Owner thay đổi theo rebalance | Business version/order đúng |
| RB-10 | Scale 1 → 2 → 3 → 1 | Phân công lại không mất partition | Tổng số business event duy nhất đúng |
| RB-11 | Cooperative assignor | Chỉ partition cần thiết có thể di chuyển | Không áp đặt full revoke |
| RB-12 | Static membership restart | Member quay lại với identity hợp lệ | Phục hồi theo timeout/protocol |
| RB-13 | Topic tăng partition | Assignment bao phủ partition mới | Event mới được xử lý |
| RB-14 | Tắt/bật broker trong lab | Consumer reconnect/rebalance | Phục hồi trong SLA thiết kế |
| RB-15 | Crash giữa DB commit và offset commit | Record có khả năng replay | Một tác động nghiệp vụ duy nhất |

RB-01 đến RB-04 thích hợp với embedded broker và container lifecycle. RB-06, RB-14, RB-15 phù hợp hơn với process/container độc lập hoặc hạ tầng test có fault injection đúng điểm. Không biến mọi kịch bản thành một test CI nhanh duy nhất; phân tầng giúp suite ổn định và dễ điều tra.

## 23. Đề xuất test với Testcontainers hoặc cluster độc lập

Embedded Kafka đủ để kiểm chứng group coordination cơ bản. Khi cần **crash thực**, hãy chạy consumer A và B ở hai JVM/container độc lập, kết nối tới cùng Kafka broker test:

```text
Test runner
   |
   +-- Kafka broker/container
   |
   +-- Consumer application A/container
   |       group=order-processors-it
   |
   +-- Consumer application B/container
   |       group=order-processors-it
   |
   +-- Business DB test/container
```

Quy trình:

1. Tạo topic và đảm bảo số partition mong muốn.
2. Khởi động A và chờ assignment có thể quan sát.
3. Khởi động B, xác nhận rebalance ổn định.
4. Publish dữ liệu có business keys và source offsets đã biết.
5. Gây fault bằng kill process hoặc chặn network theo điểm kiểm thử.
6. Chờ group phân công lại.
7. Đối chiếu dữ liệu ở DB và committed offset.
8. Khởi động lại member, đảm bảo không có side effect trùng.
9. Dọn container/topic/data sau test.

Các phương án điều khiển fault phụ thuộc nền tảng, ví dụ Docker stop/kill, network proxy hoặc orchestration API. **Dừng container tử tế có thể vẫn cho ứng dụng xử lý shutdown hook**, nên để mô phỏng crash phải dùng cơ chế ngắt đủ mạnh và xác minh producer/consumer process đã mất.

Không cần một cluster sản xuất chỉ để thử RB-02. Nhưng đối với yêu cầu SLA/failover khi broker lỗi, test một broker embedded không thể chứng minh hành vi quorum, leadership và replication của cluster production.

## 24. Các lỗi suy luận về Kafka rebalance thường gặp

### “B đã start nghĩa là B đã nhận partition”

Sai. `isRunning()` phản ánh trạng thái vòng đời container; việc group assign partition là bất đồng bộ. Cần chờ assignment và/hoặc message consumption.

### “Rebalance chỉ xảy ra khi có member chết”

Sai. Scale up/down, đổi subscription, tăng partition hoặc coordinator thay đổi có thể gây rebalance.

### “Tăng concurrency luôn làm xử lý nhanh hơn”

Không. Nếu topic có bốn partition và tạo tám consumer threads cùng group/subscription, một số consumer không nhận được partition. Throughput còn phụ thuộc CPU, DB, network và chi phí rebalance.

### “Bất kỳ lỗi log nào trong rebalance là mất message”

Sai. Có những log revoke/commit/retry trong quá trình chuyển quyền. Cần kiểm tra committed offset và business output trước khi kết luận mất dữ liệu.

### “Cùng một message chỉ được xử lý đúng một lần”

Không mặc định. Với at-least-once và lỗi quanh commit, record có thể được redeliver. Muốn kết quả nghiệp vụ không bị nhân đôi, cần idempotency hoặc ranh giới transaction phù hợp.

### “Dừng listener có chủ đích mô phỏng crash đầy đủ”

Sai. Graceful stop thường có cơ hội hoàn tất xử lý và commit; process crash có thể làm mất quyền sở hữu không qua đường cleanup bình thường.

### “Mỗi rebalance phải revoke toàn bộ partition”

Không đúng với cooperative assignment. Chỉ partition thực sự cần chuyển có thể bị revoke.

### “Một consumer giữ order toàn bộ topic”

Sai. Kafka duy trì thứ tự trong mỗi partition; xử lý song song nhiều partition không có tổng thứ tự toàn cục.

### “Chỉ cần kiểm tra assignment là đủ”

Sai. Assignment đúng không bảo đảm handler không bị kẹt, error handler không lặp mãi hoặc dữ liệu nghiệp vụ không bị ghi trùng. Phải test cả liveness và business correctness.

## 25. Bài tập thực hành

Xây dựng một ứng dụng Spring Kafka xử lý event `OrderStatusChanged` có `eventId`, `orderId`, `version` và `status`.

### Phần A — Embedded integration test

1. Tạo topic bốn partition với `@EmbeddedKafka`.
2. Tạo hai listener container A và B cùng `group.id`.
3. Khởi động A rồi B; ghi log assigned/revoked.
4. Kiểm tra hợp assignment bao phủ cả bốn partition và giao rỗng.
5. Publish 40 event vào các partition, chờ 40 event key duy nhất được nhận.
6. Stop B, chờ A nhận lại toàn bộ partition.
7. Publish thêm 10 event và kiểm tra ứng dụng tiếp tục xử lý.

### Phần B — Business idempotency

1. Tạo bảng `processed_event` có unique key theo business event ID.
2. Trong cùng DB transaction, ghi marker và cập nhật trạng thái order.
3. Gửi cùng event ID nhiều lần để mô phỏng replay.
4. Kiểm tra projection chỉ phản ánh một lần áp dụng cho mỗi event.
5. Thêm quy tắc version để event cũ không ghi đè event mới.

### Phần C — Crash và offset

1. Chạy consumer trong process/container độc lập.
2. Gây crash sau DB commit nhưng trước offset commit có kiểm soát.
3. Cho consumer khác tiếp quản partition.
4. Quan sát cùng offset/event có thể được đọc lại.
5. Kiểm tra business result không bị nhân đôi.
6. Ghi nhận thời gian từ crash đến khi consumption hồi phục.

### Phần D — Nâng độ khó

Thử cooperative assignor, graceful rolling deploy và tăng số partition. So sánh những trường hợp **revoke một phần**, **revoke toàn bộ**, **member lost** và **không có rebalance**. Giải thích callback và metric nào giúp phân biệt chúng.

Báo cáo mỗi kịch bản nên chứa: group ID, broker/client version, assignor/protocol, số partition, số member, trình tự kích hoạt, tập assignment trước/sau, số event publish, số event key duy nhất đã xử lý, số lần redelivery và thời gian phục hồi.

## 26. Kết luận

**Test rebalance** trong Spring Kafka không dừng lại ở việc nhìn thấy consumer start/stop. Bài test đáng tin cậy phải xác minh Kafka group thực sự chuyển quyền sở hữu partition, các member tiếp tục tiêu thụ sau thay đổi, và dữ liệu nghiệp vụ vẫn đúng ngay cả khi record có thể được xử lý lại quanh ranh giới offset commit.

Với **embedded Kafka**, bạn có thể kiểm thử join, graceful leave, partition assignment và luồng dữ liệu một cách nhanh, xác định hơn bằng Awaitility cùng assertion trên tập partition. Với **process crash, mất heartbeat, timeout, network partition hoặc lỗi ngay sau business commit**, cần test fault injection ở tầng container/cluster để mô phỏng chính xác. Dù chọn tầng nào, hãy phân biệt assignment cuối với callback chuyển tiếp, offset đã commit với record đã xử lý, và at-least-once delivery với business idempotency.

Khi kết hợp ma trận test, log/metric về group ownership và kiểm tra dữ liệu đầu ra, ứng dụng Spring Kafka có thể được vận hành qua scale up/down, rolling deployment và consumer failure mà không bỏ sót công việc hoặc tạo tác động nghiệp vụ sai lệch.
