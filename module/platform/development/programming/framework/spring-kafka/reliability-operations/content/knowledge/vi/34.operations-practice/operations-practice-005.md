# Mô phỏng poison pill trong Spring Kafka: retry, DLT và phục hồi consumer

Một consumer Kafka đang xử lý sự kiện theo thứ tự trong một partition. Hai record đầu được xử lý bình thường, nhưng record thứ ba luôn làm listener ném exception. Consumer thử lại mãi, offset không tiến, các record phía sau bị giữ lại dù chúng hoàn toàn hợp lệ. Đây là tình huống **poison pill** — một bản ghi mà luồng xử lý hiện tại không thể hoàn tất thành công nếu cứ phát lại theo cùng một cách.

Trong **Spring Kafka Reliability Operations → Thực hành vận hành**, mô phỏng poison pill không chỉ là gửi một chuỗi sai vào Kafka. Bài thực hành cần quan sát **offset trước/sau lỗi, số lần retry, thứ tự xử lý trong partition, cách record đi vào Dead Letter Topic (DLT), và khả năng consumer tiếp tục đọc các bản ghi phía sau**. Đồng thời phải phân biệt lỗi xảy ra **trong listener** với lỗi xảy ra **trước listener, tại deserializer** — hai tình huống này cần cách cấu hình khác nhau.

Bài dùng **Spring Boot 3.x, Spring Kafka 3.x, Java 17** làm mốc API. Những phần liên quan `DefaultErrorHandler`/`ErrorHandlingDeserializer` được viết theo Spring Kafka 3.x; với Spring Kafka 4.x phải đối chiếu tên class và API cùng phiên bản dự án. Phần chính mô phỏng **record listener, không bật Kafka container transactions**, vì vậy sử dụng `DefaultErrorHandler`. Ở cuối bài có phần riêng cho **consumer transactional/EOS**, vốn sử dụng after-rollback processing.

## 1. Mục tiêu thực hành

Ta muốn tạo một test có luồng sau:

```text
Topic: poison.lab.input       Partition 0
       |
       +-- offset 0: GOOD-1
       |
       +-- offset 1: POISON    <-- listener luôn ném exception
       |
       +-- offset 2: GOOD-2
       |
       v
Spring Kafka @KafkaListener
       |
       +-- GOOD-1 --> xử lý thành công
       |
       +-- POISON --> fail lần 1
       |               wait / retry
       |               fail lần 2
       |               wait / retry
       |               fail lần 3
       |                    |
       |                    v
       |              DeadLetterPublishingRecoverer
       |                    |
       |                    v
       |           poison.lab.input-dlt
       |
       +-- GOOD-2 --> tiếp tục xử lý
```

**Điều kiện đạt:**

1. `GOOD-1` và `GOOD-2` được xử lý thành công; không có record hợp lệ nào bị bỏ quên sau poison pill.
2. `POISON` thất bại đủ **ba lần** theo cấu hình `FixedBackOff(200ms, 2L)` — một lần đầu và hai lần retry.
3. Chỉ có **một record** tương ứng `POISON` được publish vào DLT, với key/value và metadata nguồn phù hợp.
4. Consumer group cuối cùng commit đến offset **sau `GOOD-2`** khi tất cả record đã được xử lý hoặc recover thành công.
5. Nếu DLT không publish được, không được âm thầm coi record đã recover và bỏ qua nó.
6. Có cách phân biệt lỗi dữ liệu vĩnh viễn với lỗi hạ tầng tạm thời để không gửi mọi exception vào DLT.

Đây là bài lab **có chủ đích gây lỗi**, chỉ chạy trong môi trường test/staging với topic và consumer group dành riêng. Không gửi một record lỗi vào production topic đang vận hành chỉ để thử retry hoặc alert.

## 2. Poison pill là gì, và không phải lỗi nào cũng là poison pill?

| Tình huống | Ví dụ | Retry cùng payload có giúp không? | Phương án thường hợp lý |
| --- | --- | --- | --- |
| **Dữ liệu sai không thể parse** | JSON sai syntax, Avro/Protobuf schema không tương thích | Thường không, nếu không đổi code/schema | `ErrorHandlingDeserializer`, phân loại và DLT/quarantine |
| **Dữ liệu parse được nhưng sai nghiệp vụ** | Trạng thái không được hỗ trợ, thiếu mã khách hàng | Thường không | Mã lỗi rõ, fail-fast hoặc DLT theo chính sách |
| **Bug logic chỉ bộc lộ với một input** | `NullPointerException` cho một cấu trúc hiếm gặp | Có thể không cho tới khi sửa code | DLT/quarantine có bằng chứng, sau đó sửa và replay |
| **Lỗi hạ tầng tạm thời** | DB timeout, API 503, broker không sẵn sàng | Có thể | Retry hữu hạn, backoff; không vội xem record là dữ liệu xấu |
| **Lỗi cấu hình toàn hệ thống** | Sai credential database, sai schema của toàn bộ message | Retry từng record không giúp | Dừng/alert và sửa cấu hình, tránh đổ cả topic vào DLT |
| **Tắc nghẽn do dependency** | API rate limit kéo dài | Có thể sau thời gian chờ | Backoff/circuit breaker/orchestration phù hợp |

Một **poison pill** là khái niệm vận hành: record gây kẹt đường xử lý lặp đi lặp lại. Nó có thể do dữ liệu hoặc bug code, không nhất thiết chỉ là lỗi `JsonDeserializer`. Ngược lại, lỗi một lần rồi retry thành công **chưa phải bản ghi vĩnh viễn không xử lý được**.

Điều quan trọng là **đừng nuốt exception trong listener rồi trả về bình thường**. Khi đó container có thể coi record đã xử lý xong và commit offset, làm mất cơ hội retry hoặc chuyển DLT dù nghiệp vụ chưa thành công.

## 3. Vì sao một poison pill có thể chặn cả partition?

Kafka lưu record theo thứ tự offset **trong từng partition**. Consumer thường đọc qua `poll()` và commit offset biểu thị **vị trí tiếp theo** sau record đã xử lý. Nếu record tại offset 41 luôn lỗi nhưng chưa được recover, consumer không thể đơn giản commit thẳng 42 mà không có một quyết định rõ ràng về việc bỏ qua record ấy.

```text
Partition 0:
  40 GOOD   -> processed
  41 BAD    -> listener throws
  42 GOOD   -> waiting
  43 GOOD   -> waiting

DefaultErrorHandler:
  seek/resubmit offset 41
  retry 41
  retry 41
  -> nếu không có giới hạn, các offset phía sau có thể bị trì hoãn lâu
```

**Không đồng nghĩa cả topic dừng**: topic có nhiều partition, mỗi partition có thể được gán cho consumer thread khác; lỗi ở một partition có thể không dừng tất cả partition. Tuy nhiên, nếu container có ít thread và xử lý lỗi giữ thread, một poison pill có thể làm tăng lag và ảnh hưởng các partition khác do cùng listener quản lý. Thiết kế phải cân nhắc retry, concurrency và poll interval.

Với `DefaultErrorHandler`, Spring Kafka có thể *seek* về offset lỗi hoặc giữ records trong container rồi gửi lại tùy cấu hình `seekAfterError`. Dù kỹ thuật khác nhau, mục tiêu là **không lặng lẽ bỏ mất record lỗi** trước khi recoverer quyết định nó đã được xử lý.

## 4. Chọn chiến lược của bài lab

Ta chọn mô hình đơn giản để dễ chứng minh:

| Thành phần | Lựa chọn |
| --- | --- |
| Source topic | `poison.lab.input` |
| DLT | `poison.lab.input-dlt` |
| Partitions | 1 cho mỗi topic |
| Consumer group | `poison-lab-group` |
| Input data | String, dùng `StringDeserializer` |
| Loại poison pill chính | Chuỗi `POISON` làm listener ném `PoisonRecordException` |
| Retry | `FixedBackOff(200L, 2L)`: **2 lần retry**, tổng 3 delivery attempts |
| Sau hết retry | `DeadLetterPublishingRecoverer` đưa record sang DLT |
| Commit | Container record listener quản lý commit sau xử lý/recovery thành công |
| Test | `@EmbeddedKafka` với Kafka broker thật trong test |
| Transaction | **Không bật container transaction** trong lab chính |

Mô hình này tập trung vào **blocking retry và DLT**. Nó phù hợp để quan sát poison pill ngay trong cùng partition. Nếu production dùng `@RetryableTopic` (non-blocking retry) hoặc Kafka transactions, không copy nguyên error handler mà chưa đánh giá những khác biệt ở mục 15 và 16.

## 5. Dependencies cho ứng dụng thử nghiệm

Ví dụ `build.gradle` trong dự án Spring Boot đã có plugin/BOM phù hợp:

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

Spring Kafka chứa `@KafkaListener`, `DefaultErrorHandler` và `DeadLetterPublishingRecoverer`. `spring-kafka-test` có `@EmbeddedKafka` và `KafkaTestUtils`. Các ví dụ dưới đây dùng **Spring Kafka 3.x**; Spring Boot 3.x cần Java 17 trở lên. Hãy để Spring Boot BOM chọn các patch version tương thích; nếu dùng một dòng khác, đối chiếu chữ ký API trước khi sao chép.

## 6. Cấu hình consumer, producer và listener

Tạo `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: poison-pill-lab

  kafka:
    bootstrap-servers: localhost:9092

    consumer:
      group-id: poison-lab-group
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer

    listener:
      ack-mode: record

app:
  kafka:
    input-topic: poison.lab.input
    dlt-topic: poison.lab.input-dlt
```

Giải thích:

- `enable-auto-commit=false`: để listener container và error handler điều khiển commit theo kết quả xử lý, không để consumer tự commit offset bất kể lỗi.
- `ack-mode=record`: với **record listener** không giao dịch, container xác nhận từng record đã xử lý xong theo cơ chế ack mode.
- `auto-offset-reset=earliest`: consumer group mới chưa có committed offset sẽ bắt đầu đọc từ đầu; **không ảnh hưởng** đến một group đã có committed offset hợp lệ.
- `StringDeserializer`: ở bài lab đầu tiên, Kafka bytes được giải mã thành String hợp lệ; lỗi được tạo **trong listener**. Điều này khác với test JSON deserialization poison pill.
- Không có `spring.kafka.producer.transaction-id-prefix` trong bài lab chính. Nếu bật property này và container được auto-configure transactional, cơ chế error handling thay đổi và phải dùng phần hướng dẫn transactional riêng.

Chỉ cấu hình `ack-mode` không bảo đảm ứng dụng dùng đúng error handler: cần đăng ký bean `DefaultErrorHandler` ở mục sau.

## 7. Tạo hai topic riêng cho bài lab

Dùng bean `NewTopic` để khai báo một input topic và một DLT cùng số partition. Với Spring Boot và `KafkaAdmin`, topic chưa tồn tại sẽ được tạo khi ứng dụng có quyền:

```java
package com.example.poison;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class PoisonTopicsConfig {

    public static final String INPUT = "poison.lab.input";
    public static final String DLT = "poison.lab.input-dlt";

    @Bean
    NewTopic poisonInputTopic() {
        return TopicBuilder.name(INPUT)
                .partitions(1)
                .replicas(1)
                .build();
    }

    @Bean
    NewTopic poisonDltTopic() {
        return TopicBuilder.name(DLT)
                .partitions(1)
                .replicas(1)
                .build();
    }
}
```

`replicas(1)` phục vụ **test một broker**, không phải khuyến nghị production. Nếu chọn DLT giữ **cùng partition** với record nguồn, DLT phải có partition tương ứng. Trong production, tạo topic/partition/retention/ACL bằng hạ tầng quản lý chuẩn và xác định rõ ai có quyền đọc payload lỗi.

## 8. Viết listener cố ý ném exception cho một record

Đầu tiên khai báo kiểu lỗi riêng:

```java
package com.example.poison;

public final class PoisonRecordException extends RuntimeException {
    public PoisonRecordException(String message) {
        super(message);
    }
}
```

Sau đó viết record listener. Để quan sát trong lab, class dùng `AtomicInteger` và `CountDownLatch`; đây là **state hỗ trợ test**, không nên dùng để làm đếm nghiệp vụ bền vững trong production:

```java
package com.example.poison;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class PoisonLabListener {

    private static final Logger log =
            LoggerFactory.getLogger(PoisonLabListener.class);

    public final AtomicInteger poisonAttempts =
            new AtomicInteger();

    public final Set<String> goodValues =
            ConcurrentHashMap.newKeySet();

    public final CountDownLatch goodRecordsProcessed =
            new CountDownLatch(2);

    @KafkaListener(
            topics = PoisonTopicsConfig.INPUT,
            groupId = "poison-lab-group")
    public void onRecord(ConsumerRecord<String, String> record) {
        log.info("Consuming topic={} partition={} offset={} key={}",
                record.topic(),
                record.partition(),
                record.offset(),
                record.key());

        if ("POISON".equals(record.value())) {
            int attempt = poisonAttempts.incrementAndGet();
            log.warn("Injected poison pill failure: attempt={} " +
                            "partition={} offset={}",
                    attempt, record.partition(), record.offset());

            throw new PoisonRecordException(
                    "POISON_PAYLOAD");
        }

        // Chỉ dùng để quan sát test; thay bằng nghiệp vụ thật.
        goodValues.add(record.value());
        goodRecordsProcessed.countDown();
    }
}
```

Trong bài lab, record `POISON` **luôn lỗi**; retry lần sau không thể thành công nếu code không đổi. Điều này giúp test khẳng định chiến lược xử lý khi số lần thử bị vượt quá giới hạn.

**Không khuyến nghị viết `if (payload.equals("POISON"))` vào business code production.** Trong hệ thống thật, lỗi cần phân loại theo contract dữ liệu, exception từ parser hoặc validator và fault injection phải nằm trong test fixture/profile riêng.

Không dùng `catch (PoisonRecordException e) { log.warn(...); }` rồi return bình thường: như vậy container sẽ coi input đã xử lý thành công, trái với mục tiêu test.

## 9. Cấu hình retry hữu hạn và Dead Letter Topic

Spring Kafka 3.x dùng `DefaultErrorHandler` cho **record listener không giao dịch**. Ta cấu hình tối đa hai lần retry rồi gửi record lỗi vào DLT:

```java
package com.example.poison;

import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class PoisonErrorHandlingConfig {

    @Bean
    DefaultErrorHandler poisonErrorHandler(
            KafkaTemplate<String, String> template) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(
                        template,
                        (record, exception) ->
                                new TopicPartition(
                                        PoisonTopicsConfig.DLT,
                                        record.partition()));

        // Nếu publish DLT lỗi, không coi record đã recover.
        recoverer.setFailIfSendResultIsError(true);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        recoverer,
                        new FixedBackOff(200L, 2L));

        return handler;
    }
}
```

Trong Spring Boot 3.x, nếu chỉ dùng `ConcurrentKafkaListenerContainerFactory` do Boot tự cấu hình, một bean `CommonErrorHandler`/`DefaultErrorHandler` sẽ được gắn vào factory đó. **Nếu ứng dụng có factory riêng**, cần gắn trực tiếp `factory.setCommonErrorHandler(handler)`; tạo bean không có nghĩa mọi custom factory đều sử dụng nó.

### Đọc đúng `FixedBackOff`

`new FixedBackOff(200L, 2L)` có:

```text
Delivery #1: listener gọi lần đầu
     |
     +-- fail
     |
     +-- backoff 200 ms
     |
Delivery #2: retry lần thứ nhất
     |
     +-- fail
     |
     +-- backoff 200 ms
     |
Delivery #3: retry lần thứ hai
     |
     +-- fail
     |
     v
DeadLetterPublishingRecoverer
     |
     +-- publish DLT thành công
     |
     v
Record nguồn được coi là recovered;
container có thể tiến sang record tiếp theo.
```

Tham số thứ hai là **số lần retry sau lần delivery ban đầu**, không phải tổng số lần listener được gọi. Với lỗi được phân loại *not retryable*, `DefaultErrorHandler` có thể gọi recoverer ngay mà không áp dụng hai lần retry này.

### Lưu ý về commit offset sau recovery

Với record listener, `AckMode.RECORD` và `DefaultErrorHandler` xử lý thành công, container có thể commit offset của record đã được recover theo quy tắc `ackAfterHandle` (mặc định `true`), rồi tiếp tục. Với `AckMode.MANUAL_IMMEDIATE`, muốn commit recovered offset cần xét thêm `setCommitRecovered(true)` theo tài liệu và cấu hình ack cụ thể.

**Không tự gọi `consumer.commitSync()` bên trong recoverer** để “bỏ qua” một record: thao tác thủ công có thể bỏ sót record khác, phá quy tắc thứ tự xử lý và làm mất khả năng retry khi DLT publish lỗi.

### Lỗi nào bỏ retry, lỗi nào nên thử lại?

`DefaultErrorHandler` có danh sách exception được coi là **fatal/not-retryable** theo mặc định, trong đó có `DeserializationException` và một số lỗi conversion/argument mapping; các lỗi đó thường không tự hết chỉ nhờ gửi lại cùng record.

Với lỗi nghiệp vụ rõ ràng, có thể phân loại thêm:

```java
handler.addNotRetryableExceptions(
        InvalidSchemaException.class,
        UnsupportedEventTypeException.class);
```

`InvalidSchemaException` và `UnsupportedEventTypeException` ở đây là **class do ứng dụng định nghĩa**, không phải sẵn có từ Spring Kafka. Khi thêm chúng, test nên kỳ vọng **chuyển DLT ngay** chứ không phải ba delivery attempts.

Đối với `PoisonRecordException` của bài lab, **không** thêm vào danh sách not-retryable để còn quan sát được ba lần thử như mục tiêu ban đầu.

## 10. Chạy thử bằng producer trong test hoặc một công cụ gửi message

Dữ liệu đầu vào cần đi theo **đúng thứ tự một partition**:

| Offset dự kiến trong topic mới | Key | Value | Kỳ vọng |
| --- | --- | --- | --- |
| 0 | `event-001` | `GOOD-1` | Xử lý thành công |
| 1 | `event-002` | `POISON` | Thất bại ba lần, gửi DLT |
| 2 | `event-003` | `GOOD-2` | Tiếp tục sau khi recover poison pill |

Với `KafkaTemplate`:

```java
template.send("poison.lab.input", 0, "event-001", "GOOD-1")
        .get(10, TimeUnit.SECONDS);

template.send("poison.lab.input", 0, "event-002", "POISON")
        .get(10, TimeUnit.SECONDS);

template.send("poison.lab.input", 0, "event-003", "GOOD-2")
        .get(10, TimeUnit.SECONDS);
```

Đây là **đoạn gửi minh họa**: `template` phải là bean `KafkaTemplate<String,String>`, và `TimeUnit` được import từ `java.util.concurrent.TimeUnit`. Chờ từng future giúp biết broker đã nhận record theo thứ tự gửi; trong sản xuất không nhất thiết phải gửi đồng bộ từng record như vậy.

Khi theo dõi log, một sequence điển hình:

```text
INFO  Consuming offset=0 key=event-001       -> GOOD-1
INFO  Consuming offset=1 key=event-002       -> POISON
WARN  Injected poison pill failure attempt=1
INFO  Consuming offset=1 key=event-002       -> POISON
WARN  Injected poison pill failure attempt=2
INFO  Consuming offset=1 key=event-002       -> POISON
WARN  Injected poison pill failure attempt=3
INFO  Published failed record to DLT
INFO  Consuming offset=2 key=event-003       -> GOOD-2
```

Dòng “Published failed record to DLT” là **sự kiện cần instrument** nếu muốn ghi log như trên, không phải một câu mặc định Spring Kafka luôn phát ra với cùng wording. Trong test, phải đọc DLT thật, không tin mỗi log.

## 11. Integration test với `@EmbeddedKafka`

Unit test ném `PoisonRecordException` chứng minh listener có thể fail, nhưng không kiểm chứng Kafka offset, DLT publish và consumer replay. Vì vậy bài lab dùng **Kafka broker nhúng** trong Spring Kafka test.

### 11.1. Cấu hình context test

```java
package com.example.poison;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

@SpringBootTest(
        classes = PoisonPillIT.TestApplication.class,
        properties = {
                "spring.kafka.consumer.group-id=poison-lab-group",
                "spring.kafka.consumer.enable-auto-commit=false",
                "spring.kafka.consumer.auto-offset-reset=earliest",
                "spring.kafka.consumer.key-deserializer=" +
                    "org.apache.kafka.common.serialization.StringDeserializer",
                "spring.kafka.consumer.value-deserializer=" +
                    "org.apache.kafka.common.serialization.StringDeserializer",
                "spring.kafka.producer.key-serializer=" +
                    "org.apache.kafka.common.serialization.StringSerializer",
                "spring.kafka.producer.value-serializer=" +
                    "org.apache.kafka.common.serialization.StringSerializer",
                "spring.kafka.listener.ack-mode=record"
        }
)
@EmbeddedKafka(
        partitions = 1,
        topics = {
                PoisonTopicsConfig.INPUT,
                PoisonTopicsConfig.DLT
        },
        bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@DirtiesContext
class PoisonPillIT {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableKafka
    @Import({
            PoisonTopicsConfig.class,
            PoisonErrorHandlingConfig.class,
            PoisonLabListener.class
    })
    static class TestApplication {
    }

    // Test được bổ sung ở mục 11.2.
}
```

Đây là **skeleton test class**, chưa có test method. `@EmbeddedKafka` tạo topic và broker test; `bootstrapServersProperty` bảo đảm Spring Boot producer/consumer kết nối đúng broker nhúng thay vì `localhost:9092` của một Kafka local khác. `@DirtiesContext` giúp giảm rủi ro context/broker bị dùng lại không đúng sau test.

Trong cùng một context, bean `NewTopic` đã khai báo cũng không tạo lại topic nếu nó tồn tại phù hợp. Khi triển khai test suite thật, nên **đổi topic/group theo từng test context** hoặc cô lập context để tránh lịch sử cũ làm lệch offset mong đợi.

### 11.2. Test DLT và record phía sau

Đặt các import sau vào class test:

```java
import java.time.Duration;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;

import static org.junit.jupiter.api.Assertions.*;
```

Bổ sung các field và test method vào `PoisonPillIT`:

```java
@Autowired
KafkaTemplate<String, String> template;

@Autowired
EmbeddedKafkaBroker broker;

@Autowired
PoisonLabListener listener;

@Test
void poisonPillGoesToDltAndNextRecordStillProcesses()
        throws Exception {

    Map<String, Object> observerProps =
            KafkaTestUtils.consumerProps(
                    "dlt-observer-" + UUID.randomUUID(),
                    "false",
                    broker);

    observerProps.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
    observerProps.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
    observerProps.put(
            ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

    try (Consumer<String, String> dltObserver =
                 new DefaultKafkaConsumerFactory<String, String>(
                         observerProps).createConsumer()) {

        // Đọc từ đầu DLT; observer là group riêng.
        broker.consumeFromAnEmbeddedTopic(
                dltObserver, PoisonTopicsConfig.DLT);

        template.send(PoisonTopicsConfig.INPUT,
                     0, "event-001", "GOOD-1")
                .get(10, TimeUnit.SECONDS);

        template.send(PoisonTopicsConfig.INPUT,
                     0, "event-002", "POISON")
                .get(10, TimeUnit.SECONDS);

        var lastSend = template.send(
                PoisonTopicsConfig.INPUT,
                0,
                "event-003",
                "GOOD-2").get(10, TimeUnit.SECONDS);

        // Consumer vẫn đi qua record phía sau poison pill.
        assertTrue(
                listener.goodRecordsProcessed.await(
                        30, TimeUnit.SECONDS));

        assertTrue(listener.goodValues.contains("GOOD-1"));
        assertTrue(listener.goodValues.contains("GOOD-2"));

        // 1 lần đầu + 2 retries theo FixedBackOff.
        assertEquals(3, listener.poisonAttempts.get());

        ConsumerRecord<String, String> dead =
                KafkaTestUtils.getSingleRecord(
                        dltObserver,
                        PoisonTopicsConfig.DLT,
                        Duration.ofSeconds(20));

        assertEquals("event-002", dead.key());
        assertEquals("POISON", dead.value());
        assertEquals(0, dead.partition());

        // DLT observer không thấy message khác trong khoảng kiểm tra.
        assertEquals(0,
                dltObserver.poll(
                        Duration.ofSeconds(2)).count());

        // Offset commit là vị trí tiếp theo sau record cuối.
        long expectedNextOffset =
                lastSend.getRecordMetadata().offset() + 1;

        TopicPartition inputPartition =
                new TopicPartition(PoisonTopicsConfig.INPUT, 0);

        Map<String, Object> inspectorProps =
                KafkaTestUtils.consumerProps(
                        "poison-lab-group",
                        "false",
                        broker);
        inspectorProps.put(
                ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        inspectorProps.put(
                ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);

        try (Consumer<String, String> inspector =
                     new DefaultKafkaConsumerFactory<String, String>(
                             inspectorProps).createConsumer()) {

            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(20);

            Long committedOffset = null;

            while (System.nanoTime() < deadline) {
                var committed = inspector.committed(
                        Set.of(inputPartition),
                        Duration.ofSeconds(5));
                var offset = committed.get(inputPartition);

                if (offset != null) {
                    committedOffset = offset.offset();
                }
                if (Long.valueOf(expectedNextOffset)
                        .equals(committedOffset)) {
                    break;
                }

                Thread.sleep(100L);
            }

            assertEquals(
                    Long.valueOf(expectedNextOffset),
                    committedOffset);
        }
    }
}
```

**Đọc kết quả test đúng cách:**

- `goodRecordsProcessed.await(...)` chứng minh listener đã đi tới record `GOOD-2`, không kẹt vĩnh viễn tại `POISON`.
- `poisonAttempts == 3` xác nhận chính policy 2 retries, **không** phải listener “chỉ chạy một lần”.
- Consumer DLT đọc đúng `key=event-002` và `value=POISON`.
- Việc query `committed(...)` dùng **group `poison-lab-group`**, chứ không phải group mới của DLT observer. Offset được so với `lastSend.offset + 1` thay vì hardcode 3, nên dễ điều chỉnh nếu topic đã có dữ liệu.
- Phần `poll(2 giây)` là **quan sát không có duplicate trong một cửa sổ hữu hạn**, không thể chứng minh toán học rằng sẽ không bao giờ có duplicate ở tương lai.
- Test cố ý tạo source topic **một partition**, nên thứ tự ba record và offset có ý nghĩa đơn giản.

Đây là một integration test **cho kịch bản non-transactional record listener**. Nó không xác nhận exactly-once giữa input và output Kafka transaction; nếu có yêu cầu EOS, cần test khác như mục 16.

### 11.3. Kiểm tra DLT headers

`DeadLetterPublishingRecoverer` có thể thêm metadata để truy vết lỗi nguồn, gồm:

| Header | Ý nghĩa |
| --- | --- |
| `KafkaHeaders.DLT_ORIGINAL_TOPIC` | Topic chứa record gốc |
| `KafkaHeaders.DLT_ORIGINAL_PARTITION` | Partition nguồn |
| `KafkaHeaders.DLT_ORIGINAL_OFFSET` | Offset nguồn |
| `KafkaHeaders.DLT_ORIGINAL_TIMESTAMP` | Timestamp gốc |
| `KafkaHeaders.DLT_EXCEPTION_FQCN` | Kiểu exception mà recoverer ghi nhận |
| `KafkaHeaders.DLT_EXCEPTION_CAUSE_FQCN` | Kiểu nguyên nhân bên trong khi có |
| `KafkaHeaders.DLT_EXCEPTION_MESSAGE` | Thông điệp exception |
| `KafkaHeaders.DLT_EXCEPTION_STACKTRACE` | Stack trace có thể được đưa vào header |

Có thể mở rộng test để xác nhận `dead.headers().lastHeader(KafkaHeaders.DLT_ORIGINAL_TOPIC)` tồn tại và giải mã bằng UTF-8. Với partition/offset, dùng kiểu byte encoding mà Spring Kafka ghi cho header thay vì coi mọi header là chuỗi text.

Không nên giả định mọi header sẽ có trong mọi phiên bản hoặc mọi đường publish. Nên xác nhận **topic/partition/offset/key** của nguồn và mã lỗi quan trọng; kiểm tra header thực tế ở phiên bản đang dùng.

**Cảnh báo bảo mật:** DLT có thể lưu cả payload lỗi và exception message/stack trace. Đặt retention, ACL và chính sách che dữ liệu phù hợp; không gửi raw PII hoặc token vào log quan sát.

## 12. Mô phỏng lỗi tạm thời để đối chứng poison pill

Một bài kiểm thử hữu ích phải phân biệt:

```text
Event A: TRANSIENT-1
  lần 1 -> DatabaseTimeoutException
  lần 2 -> thành công
  -> không gửi DLT

Event B: POISON
  lần 1 -> PoisonRecordException
  lần 2 -> PoisonRecordException
  lần 3 -> PoisonRecordException
  -> DLT
```

Có thể tạo một counter cho key `TRANSIENT-1` trong test fixture:

```java
private final AtomicInteger transientAttempts =
        new AtomicInteger();

private void processTestValue(String value) {
    if ("TRANSIENT-1".equals(value)
            && transientAttempts.incrementAndGet() == 1) {
        throw new IllegalStateException(
                "Injected temporary dependency timeout");
    }
}
```

Khi dùng cùng `DefaultErrorHandler`, event tạm thời sẽ được retry và thành công; DLT không nhận nó. Test nên kiểm tra **lần sau thành công, offset tiến và số lần gọi**.

Trong production, exception transient nên được phân loại theo nguyên nhân thực (timeout, rate limit, connection pool), sử dụng backoff phù hợp; tránh lập trình “retry 3 lần cho mọi lỗi” bất kể bản chất.

## 13. Poison pill xuất hiện ngay trong deserializer

Kịch bản ở trên dùng `StringDeserializer` và listener ném lỗi. Một tình huống khác khó hơn là broker chứa **bytes không thể deserialize thành kiểu Java**.

Ví dụ consumer mong nhận JSON:

```json
{"orderId":"ORD-101","quantity":2}
```

Nhưng producer đã gửi:

```text
{"orderId": ???, "quantity": }
```

Nếu cấu hình trực tiếp `JsonDeserializer`, exception có thể phát sinh **trước khi `poll()` trả về record bình thường**, và listener không được gọi. Không thể xử lý chỉ bằng một `try/catch` bên trong `@KafkaListener`.

### 13.1. `ErrorHandlingDeserializer` làm gì?

Spring Kafka cung cấp `ErrorHandlingDeserializer`, bọc deserializer thật:

```text
Kafka bytes
    |
    v
ErrorHandlingDeserializer
    |
    v
JsonDeserializer (delegate)
    |
    +-- success --> object đưa tới @KafkaListener
    |
    +-- fail ----> tạo metadata DeserializationException
                    trong headers, chứa thông tin lỗi/raw bytes
                    |
                    v
               container error handling
                    |
                    v
               DLT hoặc policy khác
```

Với **record listener**, khi header mang `DeserializationException`, Spring Kafka có thể đưa record lỗi thẳng tới container error handler mà không gọi listener nghiệp vụ. `DefaultErrorHandler` xem `DeserializationException` là loại fatal/not-retryable mặc định, bởi thử parse lại cùng bytes bằng cùng schema thường không thay đổi kết quả.

### 13.2. Cấu hình deserializer đúng tầng

Ví dụ **Spring Kafka 3.x** với `JsonDeserializer`:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.events.OrderEvent
        "[spring.json.trusted.packages]": com.example.events
```

`OrderEvent` là DTO nghiệp vụ do ứng dụng tự định nghĩa. Cần thay package và tên class theo dự án thực tế. Với Spring Kafka 4.x, các API Jackson JSON serializer/deserializer có thay đổi, vì vậy **không sao chép nguyên `JsonDeserializer` của Spring Kafka 3.x** sang 4.x mà không đối chiếu tài liệu.

Khi cấu hình lỗi deserialize, DLT producer cần có khả năng gửi **raw byte[]**. Spring Kafka có thể khôi phục bytes gốc làm value cho DLT khi dùng `DeadLetterPublishingRecoverer` kết hợp `ErrorHandlingDeserializer`. **Không dùng một `StringSerializer` hoặc `JsonSerializer<OrderEvent>` cho mọi case** rồi nghĩ raw bytes chắc chắn được publish chính xác.

Một mẫu cấu hình recoverer nhiều template:

```java
// Trích đoạn ý tưởng trong @Configuration của Spring Kafka 3.x.
// stringTemplate và bytesTemplate phải dùng producer factories
// có serializer tương ứng.

Map<Class<?>, KafkaOperations<?, ?>> templates =
        new LinkedHashMap<>();

templates.put(byte[].class, bytesTemplate);
templates.put(String.class, stringTemplate);

DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(templates);
```

Các import chính: `java.util.Map`, `java.util.LinkedHashMap`, `org.springframework.kafka.core.KafkaOperations`, `org.springframework.kafka.listener.DeadLetterPublishingRecoverer`. Với dữ liệu JSON thành object `OrderEvent`, cần thêm template phù hợp loại object thường được gửi DLT, hoặc dùng `DelegatingByTypeSerializer` theo các kiểu value. Đây là **trích đoạn cấu hình** để minh họa ý tưởng, không phải đầy đủ producer factory/bean wiring.

### 13.3. Test deserialization error

Một kịch bản riêng:

1. Consumer dùng `ErrorHandlingDeserializer` với JSON delegate và đúng `OrderEvent`.
2. Producer test dùng `ByteArraySerializer` gửi **raw bytes JSON bị cắt hoặc sai cú pháp**.
3. Ghi vào một topic/group riêng; chờ error handler nhận exception.
4. Assert **listener nghiệp vụ không được gọi** cho record lỗi (trừ khi cấu hình `failedDeserializationFunction` thay đổi hành vi).
5. Assert DLT chứa **đúng raw bytes** hoặc định dạng quarantine đã được quyết định.
6. Kiểm tra headers nguồn và loại exception.
7. Assert record hợp lệ phía sau vẫn được tiêu thụ sau recovery.

Đây là test **riêng** với case `POISON` trong listener. Đừng dùng cùng một StringDeserializer để mô phỏng JSON parse failure, vì nó sẽ chuyển bytes thành String và listener vẫn có thể nhận được chúng.

## 14. Điều gì xảy ra nếu DLT cũng bị lỗi?

Một runbook đáng tin cần thử cả **recovery failure**. Những nguyên nhân:

- DLT topic không tồn tại và auto-create bị tắt.
- Producer DLT không có quyền `WRITE`.
- DLT có ít partition hơn partition nguồn khi resolver chọn cùng partition.
- Serializer của DLT producer không xử lý đúng kiểu payload.
- Broker/DLT partition leader không khả dụng.
- Payload và headers quá lớn sau nhiều lần republish.
- DLT send timeout nhưng ứng dụng không kiểm tra result.

```text
POISON offset 41
   |
   v
3 lần xử lý thất bại
   |
   v
DeadLetterPublishingRecoverer
   |
   +-- DLT publish thành công
   |        |
   |        v
   |   record recovered; tiếp tục xử lý
   |
   +-- DLT publish THẤT BẠI
            |
            v
      KHÔNG được xem là recovered
            |
      retry/seek/alert theo policy
```

Khi recoverer **ném exception**, `DefaultErrorHandler` sẽ giữ record lỗi trong luồng retry/seek theo cấu hình và không xem nó đã recover thành công. Cấu hình `recoverer.setFailIfSendResultIsError(true)` giúp tăng khả năng phát hiện DLT send thất bại thay vì coi một future gửi không thành công là thành công.

Nên có test tiêu cực: tạm làm DLT publish fail trong broker/container test, rồi xác minh **offset record lỗi chưa được commit như recovered**. Sau khi khôi phục DLT, record phải được publish và consumer tiếp tục. Không dựa vào một lần `Thread.sleep` để suy luận offset; dùng một cửa sổ theo dõi có điều kiện và bounded timeout.

**Lưu ý:** nếu production dùng một async producer/client nhưng test chỉ nhìn `KafkaTemplate.send()` trả future, chưa chắc đã xác nhận DLT commit. Phải xét chính sách xác nhận của recoverer và sự bền vững của nơi lưu.

## 15. Retry blocking và `@RetryableTopic` có khác nhau không?

Có. Bài lab chính dùng **blocking retry**: `DefaultErrorHandler` chờ rồi giao lại record trong cùng luồng xử lý container.

Một thiết kế khác là **non-blocking retry** bằng các retry topics do `@RetryableTopic`/`RetryTopicConfiguration` cung cấp. Record lỗi được publish sang retry topic có delay, consumer chính có thể tiến tiếp thay vì luôn giữ record cũ.

| Tiêu chí | `DefaultErrorHandler` blocking retry | `@RetryableTopic` non-blocking retry |
| --- | --- | --- |
| Vị trí retry | Cùng source topic/partition, seek hoặc resubmit | Các topic retry riêng |
| Thứ tự xử lý | Gần với thứ tự partition vì record lỗi có thể chặn phía sau | Có thể **thay đổi thứ tự xử lý** khi record phía sau đi trước |
| Backoff dài | Có thể giữ/pause container; cần xét poll interval | Delay qua retry topic/topic scheduling |
| Tạo thêm topic | Không cần topic retry; cần DLT nếu sử dụng | Thường cần retry topics và DLT |
| Batch listeners | `DefaultErrorHandler` hỗ trợ semantics riêng cho batch | **Non-blocking retry không hỗ trợ batch listeners** theo tài liệu |
| Container transactions | Có thể dùng after-rollback policy thay thế | **Không kết hợp trực tiếp non-blocking retries với container transactions** |
| Mục tiêu | Giữ thứ tự và xử lý lỗi gần source | Không để một poison pill giữ consumer chính quá lâu |

Đừng trộn cả hai mô hình trong một test rồi kỳ vọng cùng thứ tự hoặc cùng số offset. Với thứ tự quan trọng theo `accountId`/`orderId`, chuyển record lỗi sang retry topic có thể cho phép record sau vượt qua nó; ứng dụng phải thiết kế lại idempotency/ordering.

## 16. Nếu listener dùng Kafka transactions/EOS thì sao?

**Phần lab chính không bật transactions.** Với **Kafka transactional listener**, framework thường không cấu hình `DefaultErrorHandler` mặc định như record listener không giao dịch; exception phải gây rollback transaction, sau đó **`DefaultAfterRollbackProcessor`** xử lý việc seek/retry/recover.

```text
Transaction T1:
  read input offset 41
  KafkaTemplate.send(output)
  listener throws
     |
     v
  ABORT Kafka transaction T1
     |
     +-- output aborted không visible với read_committed
     +-- consumer offset chưa commit trong T1
     |
     v
  AfterRollbackProcessor
     |
     +-- retry cùng record
     +-- hoặc recover vào DLT theo policy
```

Ví dụ cấu hình **khái niệm** cho Spring Kafka 3.x:

```java
// Cấu hình trên listener container factory transactional.
// Đây là trích đoạn; cần gắn đúng KafkaTransactionManager,
// ProducerFactory và KafkaTemplate theo version dự án.
DefaultAfterRollbackProcessor<String, String> processor =
        new DefaultAfterRollbackProcessor<>(
                recoverer,
                new FixedBackOff(500L, 2L));

factory.setAfterRollbackProcessor(processor);
```

Với transactional recovery, nếu muốn **DLT publish và recovered consumed offset được commit cùng một Kafka transaction mới**, cần cấu hình `DefaultAfterRollbackProcessor` và transactional KafkaTemplate/`commitRecovered` theo hướng dẫn version. Không tự copy bean `DefaultErrorHandler` của bài lab chính rồi kết luận đã kiểm thử exactly-once.

Ngoài ra, **`@RetryableTopic` non-blocking retries không kết hợp trực tiếp với container transactions**, và batch listener có semantics rollback khác record listener. Đây là hai giới hạn cần thể hiện rõ khi chuyển từ lab sang luồng production dùng EOS.

### Test transactional poison pill cần kiểm tra thêm gì?

- Output Kafka của transaction lỗi **không visible** với `read_committed`.
- Input offset **không commit** từ transaction bị abort.
- Retry rồi recovery/DLT tuân thủ policy của after-rollback processor.
- Nếu recovered offset được commit trong transaction mới, nó phải phù hợp với DLT publish outcome.
- Side effect ở **database/API ngoài Kafka transaction** vẫn cần idempotency; Kafka EOS không tự bảo đảm exactly-once end-to-end.

## 17. Batch listener, multiple partitions và thứ tự xử lý

Bài lab dùng **record listener một partition**. Khi bật batch listener hoặc concurrency cao, có thêm vấn đề:

### Batch listener

Giả sử listener nhận một poll có 5 record và record thứ ba lỗi:

```text
Batch: [GOOD-1, GOOD-2, POISON, GOOD-3, GOOD-4]
                         |
                         v
                 throw exception
```

Nếu không chỉ ra index/record gây lỗi, error handler có thể phải retry **cả batch**. Spring Kafka hỗ trợ `BatchListenerFailedException` để định vị record thất bại trong batch và cho phép xử lý/retry phù hợp.

```java
for (int i = 0; i < records.size(); i++) {
    try {
        process(records.get(i));
    } catch (RuntimeException ex) {
        throw new BatchListenerFailedException(
                "Failed at batch index " + i, ex, i);
    }
}
```

Đoạn này chỉ là trích đoạn batch listener; `records` là list mà container truyền vào và `BatchListenerFailedException` thuộc `org.springframework.kafka.listener.BatchListenerFailedException` ở Spring Kafka 3.x. Khi dùng transactions, phạm vi rollback/replay của batch còn khác và phải test riêng.

### Nhiều partitions

```text
Partition 0: GOOD / POISON / GOOD -> bị trì hoãn khi retry
Partition 1: GOOD / GOOD          -> có thể tiếp tục
Partition 2: GOOD / GOOD          -> có thể tiếp tục
```

Tùy concurrency và cách container xử lý retries, ảnh hưởng có thể lan tới thread nhận nhiều partitions. **Không kết luận “chỉ partition 0 bị ảnh hưởng” khi chưa thử topology thật.** Test đa partition nên dùng keys/partition cố định, xem assignments, consumer lag theo partition và không chỉ xem tổng lag group.

### `max.poll.interval.ms` và backoff

Blocking retry dài có thể làm listener xử lý lâu, ảnh hưởng tần suất `poll()` và group membership. Spring Kafka có `ContainerPausingBackOffHandler` cho những delay dài; nhưng chọn backoff, `max.poll.interval.ms` và poll timeout phải theo khối lượng/latency thực tế.

Không dùng `FixedBackOff.UNLIMITED_ATTEMPTS` trên production chỉ vì “không muốn mất message”. Nó có thể khiến một poison pill không bao giờ được xử lý/recover, gây lag kéo dài và che lỗi cấu hình hệ thống.

## 18. Phân loại exception để tránh DLT sai mục đích

Giả sử một service có:

```java
void handle(OrderEvent event) {
    validate(event);          // InvalidOrderException
    repository.save(event);   // DataAccessResourceFailureException
    api.notify(event);        // HttpServerErrorException
}
```

Một chính sách khả thi:

| Exception | Thường retry? | Hướng xử lý |
| --- | --- | --- |
| `InvalidOrderException` | Không hoặc rất ít | DLT/quarantine với reason code và phiên bản schema |
| `DeserializationException` | Không | DLT raw bytes hoặc dừng vì lỗi schema toàn hệ thống |
| `DataAccessResourceFailureException` | Có giới hạn | Backoff; nếu kéo dài, cảnh báo sự cố DB |
| API 503/rate limit | Có với backoff phù hợp | Tránh làm quá tải downstream; có thể circuit breaker |
| `NullPointerException` do bug | Theo policy, thường không vô hạn | Lưu input lỗi an toàn, sửa code và replay |
| `AuthorizationException`/sai credential | Retry record hiếm khi giúp | Alert và sửa quyền/cấu hình, có thể tạm dừng consumer |
| `ProducerFencedException` trong transactional flow | Không dùng lại producer bị fence | Để framework/lifecycle xử lý producer mới và điều tra identity |

**Đưa mọi lỗi vào DLT không có nghĩa reliability cao.** Ví dụ database down 30 phút có thể đẩy hàng triệu record hợp lệ vào DLT và làm nhóm vận hành phải replay thủ công. Nên tách validation poison pill khỏi dependency outage.

Nếu cần DLT vì chính sách bảo toàn input, phải có **quy trình triage và replay**, không xem DLT như nơi gửi rồi quên.

## 19. Runbook khi production gặp poison pill

### Bước 1 — Xác nhận hiện tượng

Quan sát consumer lag theo topic/partition, committed offset và record đang gây lỗi lặp. Thu thập tối thiểu:

```text
consumerGroupId = orders-worker
topic           = orders.events
partition       = 3
offset          = 41802
eventId         = evt-...
exceptionType   = InvalidOrderStateException
firstSeen       = ...
deliveryAttempt = ...
appVersion      = ...
schemaVersion   = ...
```

Không cần in toàn bộ payload nhạy cảm lên dashboard. Nếu cần xem raw bytes, dùng công cụ/ACL dành riêng.

### Bước 2 — Phân loại root cause

Kiểm tra lỗi:
- Deserialize: consumer có nhận được object không, hay fail trước listener?
- Validation: input có vi phạm hợp đồng thực sự không?
- Business: code xử lý trường hợp này chưa đúng hay dữ liệu nguồn sai?
- Infrastructure: DB/API/Kafka broker có đang lỗi diện rộng không?
- Deployment/schema: chỉ pod phiên bản mới lỗi hay mọi pod đều lỗi?

Đừng gửi lại record ngay trước khi biết failure đến từ đâu; replay cùng payload có thể tiếp tục fail và khuếch đại log.

### Bước 3 — Kiểm tra retry/DLT policy

Xác nhận số lần thử, backoff, retry classification, recoverer result, tên DLT, partition, ACL và khả năng DLT producer serialize được value.

Nếu DLT publish đã thành công, đối chiếu record nguồn bằng **topic + partition + offset** và metadata trong DLT. Nếu không có DLT record, chưa chắc record bị mất: nó có thể còn đang retry hoặc recoverer đã lỗi.

### Bước 4 — Chọn hành động phục hồi

| Trường hợp | Hành động |
| --- | --- |
| Dữ liệu sai thật | Sửa tại hệ thống nguồn hoặc tạo record sửa có version/correlation rõ |
| Bug ứng dụng | Fix code, deploy, rồi replay DLT được kiểm soát |
| Schema producer/consumer lệch | Điều chỉnh contract và deploy compatibility trước khi replay |
| Hạ tầng mất kết nối | Khôi phục dependency, để retry tiếp hoặc khởi động lại đúng runbook |
| DLT quá tải | Hạn chế tốc độ replay, xử lý batch theo nhóm reason code |
| Chưa rõ side effect có commit chưa | Đối soát database/API, thiết kế idempotency trước khi phát lại |

### Bước 5 — Replay DLT có kiểm soát

Không đơn giản sửa consumer group offset lùi lại hoặc gửi tất cả record DLT về source topic mà không có kế hoạch. Một quy trình replay nên:

1. Chọn record theo `reasonCode`, thời điểm, schema version và dữ liệu đã được sửa.
2. Giữ `eventId`/business key và liên kết tới original topic/partition/offset để audit.
3. Chỉ định **điểm đến**: source topic cũ, retry topic, hoặc repair topic riêng.
4. Bảo đảm consumer/writer idempotent; tránh record được xử lý hai lần khi dữ liệu nguồn và DLT cùng tồn tại.
5. Giới hạn concurrency/rate để tránh tái tạo outage.
6. Đếm số record đã đưa lại, hoàn tất, còn lỗi; lưu bằng chứng đối soát.
7. Không xóa DLT ngay sau khi bắt đầu replay; chỉ cleanup theo retention và quy trình được phê duyệt.

**Thứ tự xử lý:** replay vào cuối topic sẽ tạo offset mới, có thể làm thay đổi thứ tự so với các record đến sau poison pill. Nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt theo account/order, cần thiết kế đặc biệt trước khi recover/skip.

## 20. Observability và cảnh báo

Một hệ thống cần biết có poison pill **trước khi DLT đầy hoặc consumer lag tăng kéo dài**.

| Chỉ số/sự kiện | Mục đích |
| --- | --- |
| Listener failure count theo exception class | Nhận diện lỗi dữ liệu và bug lặp |
| Retry attempts distribution | Phát hiện record cần quá nhiều lần thử |
| DLT publishing success/failure | Bảo đảm recoverer không âm thầm bỏ record |
| DLT ingress rate | Phát hiện lỗi schema/producer triển khai diện rộng |
| Consumer lag theo partition | Thấy partition bị giữ tại một offset |
| Time since last committed offset movement | Phát hiện stuck consumer |
| `consumer.assignment`/rebalances | Đánh giá tác động backoff và concurrency |
| DLT age / oldest unresolved item | Theo dõi backlog cần sửa |
| Business idempotency violations | Phát hiện duplicate side effects do replay |
| Input schema version vs app version | Khoanh vùng lỗi compatibility |

Sự kiện log có cấu trúc tham khảo:

```json
{
  "eventType": "kafka.poison-pill.detected",
  "service": "orders-worker",
  "consumerGroupId": "orders-worker",
  "topic": "orders.events",
  "partition": 3,
  "offset": 41802,
  "eventId": "evt-41802",
  "errorType": "InvalidOrderStateException",
  "reasonCode": "UNSUPPORTED_ORDER_STATE",
  "attempt": 3,
  "action": "PUBLISH_DLT",
  "schemaVersion": "2"
}
```

Đây là **schema ứng dụng tự định nghĩa**, không phải event Spring Kafka tự xuất đúng định dạng này. Không dùng `eventId`, `topic` hoặc `offset` có cardinality cao làm **Prometheus label** không kiểm soát; giữ chúng trong structured log/trace, dùng metrics theo nhóm ít cardinality.

### Cảnh báo nào đáng quan tâm?

- DLT publish fail hoặc thiếu quyền ghi: mức ưu tiên cao, vì lỗi recoverer có thể khiến offset kẹt.
- Một reason code đột ngột tăng nhiều lần: có thể lỗi triển khai schema toàn hệ thống.
- Lag một partition không giảm dù consumer healthy: có thể poison pill hoặc retry vô hạn.
- Quá nhiều record bị DLT trong một kỳ: quality gate cần dừng downstream thay vì coi mọi thứ đã ổn.
- DLT tồn tại quá thời hạn xử lý: backlog không được giải quyết.

## 21. Những lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| Listener lặp mãi cùng offset | Retry vô hạn hoặc DLT recoverer thất bại | Giới hạn backoff, kiểm tra DLT/ACL/serializer |
| Poison pill không vào DLT | Default error handler chỉ log, không có recoverer phù hợp | Cấu hình `DeadLetterPublishingRecoverer` |
| Số lần thử khác dự kiến | Hiểu nhầm `FixedBackOff(maxAttempts)` hoặc exception được phân loại fatal | Đếm **initial attempt + retries**, kiểm tra classifications |
| Bản ghi phía sau không được xử lý | Record lỗi chưa được recover, partition giữ thứ tự | Test thành công DLT và committed offset |
| DLT chỉ thấy `null` hoặc serialization fail | Lỗi xảy ra trong deserializer, DLT template không xử lý `byte[]` | `ErrorHandlingDeserializer` và serializer/template phù hợp raw bytes |
| Consumer chết trước listener | Deserializer ném lỗi ngoài `poll()` | Bọc bằng `ErrorHandlingDeserializer` |
| Ghi DLT xong nhưng source vẫn retry | Recovery fail, commit offset chưa thành công hoặc ack policy sai | Kiểm tra recoverer result, ack mode và group committed offset |
| DLT có duplicate | Retry send/timeout, replay hoặc nhiều consumer path | DLT consumer idempotency, kiểm tra headers và producer outcome |
| Test pass vì không thấy DLT | Observer bắt đầu `latest` hoặc consumer không nhận được message | Subscribe/assign trước khi gửi, seek beginning |
| Test flaky khi chạy CI | Reuse topic/group/offset, timing bằng sleep | Cô lập test, chờ điều kiện và timeout rõ |
| Cả topic bị chậm | Partition chia sẻ consumer thread hoặc retry quá dài | Xem assignment/concurrency, backoff/pause |
| Lỗi DB hàng loạt bị đẩy DLT | Phân loại transient sai | Circuit breaker, retry và outage policy |
| `@RetryableTopic` làm sai thứ tự | Record lỗi đi retry topic và record sau vượt qua | Xác định ordering requirement trước khi dùng |
| Dùng `DefaultErrorHandler` trong EOS và nuốt exception | Transaction không rollback theo kỳ vọng | Dùng after-rollback processing và giữ transaction exception |
| DLT chứa PII | Lưu raw payload/exception headers không kiểm soát | ACL, retention, masking, quarantine policy |
| Replay tạo tác động trùng | Writer không idempotent, input đã từng side effect | Unique business key/inbox/outbox và đối soát |
| Batch listener retry cả batch | Không có `BatchListenerFailedException` định vị record | Ném exception kèm index/record phù hợp |
| Record lỗi do deploy mới, deploy cũ chạy bình thường | Schema compatibility hoặc code bug | Canary, version contract, replay sau fix |

## 22. Bài tập mở rộng

**Bài tập A — Không có DLT:** thay `DefaultErrorHandler` bằng retry policy cố ý không có recoverer, quan sát offset bị giữ tại `POISON` và lag tăng. Chỉ thực hiện trên topic test và dừng sau thời gian ngắn; khôi phục cấu hình trước khi dùng nguồn thật.

**Bài tập B — Mark not-retryable:** thêm `PoisonRecordException.class` vào `addNotRetryableExceptions`; gửi lại ba record trên topic/group **mới**, xác nhận poison pill vào DLT sau một lần delivery, `GOOD-2` vẫn được xử lý.

**Bài tập C — Lỗi tạm thời:** cho một record thất bại một lần rồi thành công; assert nó **không** vào DLT và group offset tiến.

**Bài tập D — DLT write failure:** tạo broker/topic/ACL test khiến publish DLT lỗi, bật `setFailIfSendResultIsError(true)`, xác nhận record không bị coi là recovered. Sau khi sửa DLT, test consumer có thể tiếp tục.

**Bài tập E — JSON raw bytes:** gửi JSON lỗi bằng `ByteArraySerializer`, dùng `ErrorHandlingDeserializer` và DLT producer hỗ trợ `byte[]`; assert listener không được gọi và raw input được bảo toàn theo policy.

**Bài tập F — Multi-partition:** dùng 3 partitions, poison ở partition 1, ghi lag và record movement theo từng partition, thử với concurrency 1 và 3. So sánh rủi ro ảnh hưởng giữa các partition.

**Bài tập G — Transactional flow:** bật Kafka transactions, chuyển error recovery sang `DefaultAfterRollbackProcessor` và kiểm tra output aborted không visible qua `read_committed`; kiểm tra DLT và recovered offset theo một transaction policy được cấu hình đúng.

**Bài tập H — Replay DLT:** tạo một repair consumer có dedup key, phát lại record sau khi sửa dữ liệu và xác minh business table không có side effect trùng; kiểm tra audit mapping original offset → replay offset.

## 23. Tài liệu tham khảo chính thức

- [Spring Kafka — Handling Exceptions, DefaultErrorHandler](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka — Publishing Dead-letter Records](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html#dead-letters)
- [Spring Kafka — Serialization, Deserialization and ErrorHandlingDeserializer](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Spring Kafka — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html)
- [Spring Kafka — Transactions và after-rollback behavior](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Kafka — Testing Applications with Embedded Kafka](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Apache Kafka — Consumer Concepts và Offset Management](https://kafka.apache.org/documentation/)

**Kết luận:** Mô phỏng poison pill tốt phải quan sát được **failure ở một offset cụ thể**, các lần retry có giới hạn, kết quả đưa vào **DLT**, việc **consumer group tiếp tục commit offset** và các record phía sau vẫn được xử lý. Với lỗi trong listener, dùng `DefaultErrorHandler`/`DeadLetterPublishingRecoverer` cho record listener không giao dịch; với lỗi trước listener, dùng `ErrorHandlingDeserializer` và DLT serializer thích hợp cho raw bytes. Khi ứng dụng bật Kafka transactions, kiểm tra `DefaultAfterRollbackProcessor` và transaction outcome riêng. DLT chỉ là **cơ chế cô lập bản ghi lỗi** — độ tin cậy vận hành đến từ phân loại lỗi đúng, giám sát backlog, bảo vệ dữ liệu, idempotency và quy trình replay có kiểm soát.
