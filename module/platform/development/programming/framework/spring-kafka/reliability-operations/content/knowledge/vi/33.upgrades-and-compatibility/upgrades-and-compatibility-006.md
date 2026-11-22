# Thay đổi retry topic infrastructure trong Spring Kafka: nâng cấp an toàn và tương thích

Khi nâng cấp Spring Kafka hoặc thay cấu hình `@RetryableTopic`, một ứng dụng có thể vẫn khởi động bình thường nhưng **retry topics, consumer groups, backoff, DLT routing hoặc serializer** đã thay đổi. Tình huống nguy hiểm là dữ liệu ở retry topic cũ chưa được xử lý, trong khi bản mới chỉ subscribe retry topic mới. Dashboard có thể báo consumer mới không có lag dù những record quan trọng vẫn bị bỏ lại trên broker.

**Retry topic infrastructure** là toàn bộ hệ thống giúp Spring Kafka thực hiện *non-blocking retries*: cấu hình `@RetryableTopic` hoặc `RetryTopicConfiguration`, cơ chế bootstrap, destination resolver, topic naming, retry/DLT topics, retry listener containers, consumer groups, KafkaTemplate/producer serializers, backoff timestamp/headers, exception classifier và DLT handler. **Thay đổi infrastructure** vì vậy là một thay đổi về *topology dữ liệu và hợp đồng vận hành*, không chỉ là refactor một annotation.

Trong **Spring Kafka Reliability Operations → Nâng cấp và tương thích**, bài này hướng dẫn nhận diện những thay đổi liên quan Spring Kafka 2.9, 3.x và 4.1; kiểm kê topology hiện tại; cấu hình tường minh; nâng cấp mà không bỏ rơi retry backlog; kiểm soát ordering, idempotency, partitions và serialization; triển khai, kiểm thử, giám sát và rollback có bằng chứng.

Ví dụ dùng Java 17+, Spring Boot 3.x và Spring Kafka 3.x/4.x làm bối cảnh. API và giá trị mặc định có thể khác giữa các bản; khi áp dụng cần khóa đúng release của dự án và kiểm tra release notes/documentation dành cho phiên bản đó.

## 1. Non-blocking retry: dữ liệu đi qua những đâu?

Khi listener chính ném exception thuộc loại được phép retry, Spring Kafka có thể **publish record sang một retry topic** kèm thông tin thời điểm xử lý tiếp. Consumer retry topic kiểm tra thời điểm đến hạn, pause partition nếu còn phải chờ, rồi resume để xử lý lại. Sau khi hết attempts hoặc gặp lỗi không được retry, event có thể được gửi tới Dead Letter Topic (DLT).

~~~mermaid
flowchart TD
    A["orders.events / main listener"] --> B{"Xử lý thành công?"}
    B -->|Có| C["Hoàn tất business effect"]
    B -->|Lỗi được retry| D["Forward sang retry topic"]
    D --> E["Retry listener\npause đến hạn theo timestamp"]
    E --> F["Xử lý lại"]
    F -->|Thành công| C
    F -->|Còn attempts| D
    F -->|Hết attempts hoặc fatal| G["orders.events-dlt"]
    G --> H["DLT handler / quarantine / replay"]
~~~

Điểm khác **blocking retry**: thay vì giữ luồng xử lý nguồn chờ trong cùng container, non-blocking retry gửi record sang **topic khác** để xử lý sau. Vì có thêm broker topics và consumer groups, topology có thể thay đổi giữa các phiên bản dù code xử lý nghiệp vụ không đổi.

### Thành phần phải kiểm kê

| Thành phần | Nhiệm vụ | Rủi ro khi nâng cấp |
|---|---|---|
| `@RetryableTopic` | Khai báo attempts, backoff, suffix, DLT và lỗi được retry. | Default mới thay topology hoặc ngữ nghĩa. |
| `RetryTopicConfiguration` | Cấu hình retry tập trung bằng bean/builder. | Xung đột với annotation cùng topic. |
| `@EnableKafkaRetryTopic` / `RetryTopicConfigurationSupport` | Bootstrap và global customization. | Duplicate infrastructure hoặc customizer bị mất. |
| Retry topic names | Chỉ định destination theo delay/index/reuse. | Topic cũ bị orphan, consumer mới không đọc. |
| Retry listener containers | Chờ và tiêu thụ retry records. | Concurrency/group ID thay đổi. |
| `KafkaTemplate` và serializers | Forward DTO/raw bytes sang retry/DLT. | Publish lỗi ở producer. |
| Backoff/attempt headers | Lưu thời điểm và lịch sử thử lại. | Delay/attempt hoặc observability sai. |
| Exception classifier | Xác định retry, fatal, DLT. | Retry vô hạn hoặc DLT quá sớm. |
| DLT handler | Phân loại record không phục hồi tự động. | DLT tồn đọng hoặc bị consume mà chưa xử lý. |
| Kafka consumer group offsets | Tiến độ đọc từng topic. | Duplicate, reset offset hoặc backlog không thấy. |

**Quan trọng:** Kafka không tự chuyển một record từ `orders.events-retry-1` sang `orders.events-retry` khi ứng dụng đổi cấu hình. Những topic là các log độc lập trên broker.

## 2. Chốt invariants trước khi thay đổi

Một migration retry infrastructure an toàn cần chứng minh:

1. **Không có retry record bị bỏ rơi** ở topology cũ hoặc mới.
2. Event đã xử lý thành công không tạo side effect nghiệp vụ lần hai khi replay/restart.
3. Attempts, backoff và fatal/non-retryable exceptions đúng hợp đồng nghiệp vụ.
4. DLT có topic, owner, retention, consumer/remediation và lộ trình replay.
5. Backoff không khiến retry records bị xóa bởi retention trước khi đến hạn.
6. Consumer groups/partitions và ACL phù hợp các destination đang sử dụng.
7. Dữ liệu do bản cũ republish vẫn được bản mới decode hoặc có đường migration.
8. Rolling deployment và rollback đều có thể xử lý **backlog đang bay**.
9. Có thể chứng minh record nguồn cuối cùng thành công, ở DLT hoặc được xử lý theo một disposition được phê duyệt.

Nếu job có output vào database, cần kiểm tra business key và dữ liệu đã commit. Retry ở Kafka có thể xảy ra nhiều lần; số listener callbacks **không** bằng số business effects duy nhất.

## 3. Các mốc thay đổi Spring Kafka cần lưu ý

| Mốc | Điều đáng chú ý | Việc phải làm khi migrate |
|---|---|---|
| **Spring Kafka 2.7** | Có hỗ trợ non-blocking retry qua `@RetryableTopic` và `RetryTopicConfiguration`. | Kiểm kê nếu ứng dụng từng tự xây retry topics. |
| **Spring Kafka 2.9** | Thay cơ chế bootstrap và customize infrastructure beans. | Kiểm tra cách enable, extends support class và các overrides cũ. |
| **Spring Kafka 3.0** | Có thể chỉnh concurrency retry containers riêng; một số default liên quan topic creation đổi. | Đối chiếu số consumer tasks, topics và broker settings. |
| **Spring Kafka 3.2** | Hỗ trợ `@RetryableTopic` với `@KafkaListener` ở cấp class; cải tiến reuse trong các kiểu backoff. | Kiểm tra annotation discovery và topic topology. |
| **Spring Kafka 4.1** | Mặc định dùng lại **một retry topic cho những khoảng delay giống nhau**. | Kiểm tra fixed-delay/multiple-attempt topology và xử lý old retry topics. |

Đây là các mốc tính năng, không phải ma trận compatibility hoàn chỉnh. Trong dự án thực tế phải xác nhận Spring Boot BOM, Java, Kafka clients, phiên bản broker, loại serializer và các API bị deprecated/removed. Không dùng một snippet từ Spring Kafka 4.x để biên dịch trực tiếp trong dự án 3.x nếu API chưa tồn tại.

### Thay đổi mặc định đặc biệt quan trọng ở 4.1

Giả sử policy fixed backoff 1 giây, tổng 4 attempts:

~~~text
Attempt 1: orders.events
Attempt 2: retry delay 1000 ms
Attempt 3: retry delay 1000 ms
Attempt 4: retry delay 1000 ms
Sau đó: DLT nếu vẫn lỗi
~~~

Với **multi-topic strategy**, có thể tạo:

~~~text
orders.events-retry-0
orders.events-retry-1
orders.events-retry-2
orders.events-dlt
~~~

Với **single-topic reuse strategy**, có thể chỉ tạo:

~~~text
orders.events-retry
orders.events-dlt
~~~

Từ Spring Kafka 4.1, các khoảng retry delay bằng nhau được **reuse theo mặc định**. Muốn tạo nhiều retry topics cho từng attempt ở API phiên bản hỗ trợ, cần chọn chiến lược như `SameIntervalTopicReuseStrategy.MULTIPLE_TOPICS`. Tên cụ thể còn phụ thuộc suffixing policy, index/delay và cấu hình riêng: đừng coi danh sách minh họa trên là tên được bảo đảm cho mọi deployment.

Một nguồn rủi ro tương tự là exponential backoff chạm `maxInterval`: nhiều attempts sau có **cùng delay tối đa**, nên cách reuse có thể làm thay số retry topics so với chiến lược cũ. Cần tính/kiểm tra toàn bộ topology thực, không chỉ nhìn `retryTopicSuffix`.

## 4. Lập inventory topology cũ và mới

Trước khi đổi dependency, ghi lại đầy đủ:

| Thuộc tính | Cũ | Dự kiến mới |
|---|---|---|
| Spring Kafka / Spring Boot version | Điền release đang chạy | Điền release đích |
| Source topic | `orders.events` | `orders.events` |
| Main consumer group | `orders-processor` | `orders-processor` |
| Attempts | 4 tổng cộng | 4 tổng cộng |
| Backoff | Fixed 1000 ms | Fixed 1000 ms |
| Retry topic names | `orders.events-retry-0/1/2` | `orders.events-retry` hoặc giữ cũ |
| Retry consumer groups | Đo trên broker | Xác minh từ context/broker |
| DLT topic/handler | `orders.events-dlt` | Giữ hoặc thay có chủ đích |
| Partition count | 6 | 6 hoặc mapping được thiết kế |
| Topic retention | Giá trị thực | Đủ max delay + thời gian outage |
| Consumer concurrency | Main/retry theo thực tế | Đặt mục tiêu, đo tải |
| Serializer/deserializer | Kèm type headers | Kèm compatibility plan |
| Old retry backlog | Có thể còn | Phải drain/bridge/giữ đọc |

Đừng điền bảng bằng suy đoán từ tên annotation. Hãy kiểm tra topics thật, partition counts, consumer-group offsets và cấu hình app đang chạy. Nếu bản 3.x đã cấu hình reuse từ trước, việc lên 4.1 **có thể không làm thay topology**, nên phải dựa vào bằng chứng chứ không giả định có thay đổi.

### Nhìn cả topics và consumer groups

~~~text
Main group: orders-processor
  subscribes: orders.events

Retry group(s): group ID liên quan main group + suffix
  subscribes: orders.events-retry-0
              orders.events-retry-1
              ...

DLT consumer:
  subscribes: orders.events-dlt
~~~

Retry containers thường sử dụng group IDs hình thành từ group chính và topic suffix. Nếu suffix/group ID đổi, offsets cũ **không chuyển theo**. Một group mới có thể sử dụng `auto.offset.reset` và tiêu thụ từ earliest/latest khi chưa có committed offset. Cả hai lựa chọn đều có rủi ro nếu không phù hợp migration: earliest có thể replay, latest có thể bỏ dữ liệu cần xử lý.

## 5. Bootstrap infrastructure: cách cấu hình mới

Có ba mức cấu hình phổ biến:

1. **`@RetryableTopic` đặt ở listener:** cách đơn giản; framework tự bootstrap retry/DLT infrastructure cần thiết.
2. **`RetryTopicConfiguration` bean:** cấu hình policy qua builder cho những topics được chọn.
3. **Global configuration:** dùng một trong hai con đường `@EnableKafkaRetryTopic` **hoặc** extends `RetryTopicConfigurationSupport` khi cần thay đổi global behavior.

### Dùng @EnableKafkaRetryTopic

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafkaRetryTopic;

@Configuration
@EnableKafkaRetryTopic
public class RetryInfrastructureConfig {
    // Các RetryTopicConfiguration beans nếu cần.
}
~~~

`@EnableKafkaRetryTopic` đã meta-annotate `@EnableKafka`. Đây là con đường enable/import các infrastructure beans, không phải một yêu cầu phải thêm cho mọi listener đã dùng `@RetryableTopic`.

### Dùng RetryTopicConfigurationSupport

Khi cần advanced/global customization:

~~~java
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.retrytopic.RetryTopicConfigurationSupport;

@EnableKafka
@Configuration
public class CustomRetryInfrastructure
        extends RetryTopicConfigurationSupport {

    @Override
    protected void manageNonBlockingFatalExceptions(
            List<Class<? extends Throwable>> fatalExceptions) {
        fatalExceptions.add(UnsupportedEventSchemaException.class);
    }
}
~~~

`UnsupportedEventSchemaException` là exception do ứng dụng định nghĩa. Ví dụ đánh dấu lỗi schema không tương thích là fatal thay vì retry nhiều lần cùng payload.

**Không dùng đồng thời `@EnableKafkaRetryTopic` và một `@Configuration` extends `RetryTopicConfigurationSupport`**. Đồng thời chỉ nên có **một** configuration class extends support trong context. Spring Kafka 2.9 thay cách bootstrap/customize infrastructure nên những bean-overrides nội bộ của bản rất cũ cần được chuyển theo hook được hỗ trợ, không chỉ đổi import và tên class.

Các chỗ cần rà soát khi migrate:

~~~text
@RetryableTopic
@EnableKafkaRetryTopic
@EnableKafka
RetryTopicConfigurationSupport
RetryTopicConfigurationBuilder
RetryTopicConfiguration
DeadLetterPublishingRecoverer
DefaultErrorHandler / CommonErrorHandler
@DltHandler
KafkaTemplate bean names
ConsumerFactory / KafkaListenerContainerFactory
~~~

Đây là danh sách nhận diện phạm vi, **không phải** danh sách class buộc phải xóa. Quan trọng là biết thành phần nào chịu trách nhiệm tạo topology và customizer nào được gọi thật sau upgrade.

## 6. Cấu hình @RetryableTopic một cách tường minh

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000, multiplier = 2.0),
        retryTopicSuffix = "-retry",
        dltTopicSuffix = "-dlt",
        autoCreateTopics = "false"
    )
    @KafkaListener(
        topics = "orders.events",
        groupId = "orders-processor"
    )
    public void handle(String eventId) {
        orderService.processIdempotently(eventId);
    }
}
~~~

`orderService` là dependency ứng dụng do ví dụ lược bỏ phần khai báo/injection; trọng tâm là annotation cấu hình. Trong ứng dụng thực, cần bean service, serializer/deserializer, KafkaTemplate và infrastructure phù hợp.

Giải thích:

- `attempts="4"` thường tính cả một lần xử lý ở main topic, tức tối đa ba non-blocking retry attempts trước DLT nếu không có timeout/fatal policy can thiệp.
- Backoff exponential có thể tạo những retry topic theo các delay khác nhau. Không giả định luôn có đúng ba retry topics nếu reuse strategy áp dụng.
- Suffix được khai báo tường minh nhưng **cách thêm index/delay và reuse** vẫn cần kiểm soát.
- `autoCreateTopics="false"` ngăn cấu hình này tạo topic tự động; DevOps cần provision đúng retry/DLT topic names và ACL trước khi publish.
- Group ID được chỉ định rõ để việc đối chiếu offsets/groups trong migration ít mơ hồ hơn.

### Khi muốn giữ multi-topic strategy trên 4.1

Với phiên bản hỗ trợ `SameIntervalTopicReuseStrategy`:

~~~java
import org.springframework.kafka.retrytopic.SameIntervalTopicReuseStrategy;

@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 1_000),
    sameIntervalTopicReuseStrategy =
        SameIntervalTopicReuseStrategy.MULTIPLE_TOPICS
)
@KafkaListener(topics = "orders.events", groupId = "orders-processor")
public void handle(String value) {
    // Xử lý nghiệp vụ.
}
~~~

Đây là fragment minh họa **chủ đích chọn topology**, không copy nguyên vào Spring Kafka cũ chưa có attribute/enum này. Hãy đối chiếu docs đúng release. Với những bản trước có API/deprecated strategy khác, migration phải thay sang API đang được hỗ trợ và test được tên topics.

## 7. RetryTopicConfigurationBuilder khi cần quản lý tập trung

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.retrytopic.RetryTopicConfiguration;
import org.springframework.kafka.retrytopic.RetryTopicConfigurationBuilder;

@Configuration
public class OrdersRetryConfig {

    @Bean
    RetryTopicConfiguration ordersRetryPolicy(
            KafkaTemplate<String, String> template) {

        return RetryTopicConfigurationBuilder.newInstance()
            .exponentialBackoff(1_000, 2.0, 8_000)
            .maxAttempts(4)
            .includeTopics(List.of("orders.events"))
            .create(template);
    }
}
~~~

Với builder, có thể tập trung policy nhiều topics. Tuy nhiên cần tránh **nhiều cấu hình khác nhau cùng nhận một source topic**. Nhiều `@KafkaListener` trên cùng topic không bảo đảm mỗi annotation có topology độc lập: framework có thể áp một retry configuration cho các listener cùng source topic. Nếu hai listener có policy retry mâu thuẫn, đừng dựa vào thứ tự quét bean hoặc kỳ vọng framework sẽ tự chọn theo listener; hãy thiết kế cấu hình thống nhất hoặc tách kiến trúc.

### Checklist nhiều listener cùng topic

- Có bao nhiêu `@KafkaListener` nhận cùng topic?
- Các listener dùng cùng hay khác consumer group?
- Có bao nhiêu `@RetryableTopic`/`RetryTopicConfiguration` cho topic đó?
- Retry/DLT suffix hoặc naming strategy có chồng lấn không?
- Có thể tạo hai retry publisher với cấu hình khác nhau không?
- Một record retry từ version cũ có thể bị version mới hiểu khác policy không?

Nếu ứng dụng đổi từ method-level annotation sang class-level `@KafkaListener` ở Spring Kafka 3.2+, phải kiểm tra thêm `@KafkaHandler` dispatch, DLT handler selection và policy áp dụng cho từng event type. Nên tránh refactor annotation placement cùng lúc với đổi topic naming nếu chưa cần.

## 8. Quy tắc naming: suffix không phải toàn bộ tên

Retry topic thường được đặt tên từ source topic, retry suffix và **delay hoặc attempt index**. Ví dụ:

~~~text
orders.events-retry-1000
orders.events-retry-2000
orders.events-retry-4000
orders.events-dlt
~~~

Hoặc:

~~~text
orders.events-retry-0
orders.events-retry-1
orders.events-retry-2
orders.events-dlt
~~~

Trong những trường hợp fixed delay và reuse:

~~~text
orders.events-retry
orders.events-dlt
~~~

Ngoài suffix còn có:

| Tùy chọn | Hệ quả |
|---|---|
| Suffix theo **delay** | Tên có thể phản ánh 1000/2000/4000 ms. |
| Suffix theo **index** | Tên phản ánh thứ tự retry stages. |
| Single topic for same intervals | Nhiều attempts cùng delay vào một topic. |
| Multiple topics | Có topic riêng cho từng attempt. |
| Exponential max interval reuse | Các attempts sau có cùng max delay dùng chung topic. |
| Custom `RetryTopicNamesProviderFactory` | Tên có thể khác hoàn toàn quy ước mặc định. |
| Custom DLT exception routing | Có thể thêm DLT theo exception type với suffix riêng. |

Khi nâng cấp, snapshot phải ghi **tên chính xác được tạo/được subscribe**, không chỉ retry suffix. Nếu hạ tầng cần precreate topics và cấu hình `autoCreateTopics=false`, lệch một ký tự vẫn có thể làm publisher/consumer không hoạt động.

## 9. Thay topic naming khi còn backlog: tình huống điển hình

Giả sử trước rollout:

~~~text
orders.events-retry-0: 12 records chưa xong
orders.events-retry-1:  5 records chưa xong
orders.events-retry-2:  3 records chưa xong
orders.events-dlt:      7 records cần remediation
~~~

Bản mới chuyển sang:

~~~text
orders.events-retry
orders.events-dlt
~~~

**Hai mươi retry records cũ không tự xuất hiện trong topic mới.** Nếu bản mới chỉ subscribe `orders.events-retry`, những bản ghi cũ có thể còn trên Kafka cho đến khi retention hết mà không ai xử lý.

### Lựa chọn migration

| Phương án | Ý tưởng | Khi nào phù hợp | Rủi ro |
|---|---|---|---|
| **Giữ topology cũ** | Cố định naming/reuse để bản mới vẫn đọc old retry topics. | Version mới còn API tương thích. | Header/deserializer/offset vẫn phải kiểm tra. |
| **Drain trước cutover** | Ngừng tạo retry mới vào old topics, để old consumers hoàn tất backlog. | Retry delay ngắn, lượng pending có hạn. | Phải chờ qua cửa sổ max backoff/outage. |
| **Bridge consumer** | Đọc old topics và đưa record sang đường mới có kiểm soát. | Topology mới bắt buộc đổi, backlog khó drain. | Attempt headers, idempotency, duplicate. |
| **Parallel old/new** | Giữ old retry consumers khi new publisher đã hoạt động. | Zero-downtime rollout có thiết kế. | Rủi ro cùng event được xử lý trên hai đường. |
| **Replay có phê duyệt** | Reprocess từ nguồn hoặc DLT khi có key và audit. | Không thể drain/bridge trực tiếp. | Có thể nhân đôi business effect nếu không idempotent. |

**Drain** không chỉ là lag=0 tại một thời điểm. Cần biết mọi producer cũ đã ngừng phát sinh retry mới, các retry events đã đến hạn/được xử lý, groups liên quan không còn pending và DLT có disposition riêng. Nếu max backoff dài hàng giờ, vài phút yên tĩnh chưa đủ kết luận.

### Mixed-version deployment

~~~text
Pod A: Spring Kafka 3.x -> multiple retry topics
Pod B: Spring Kafka 4.1 -> single retry topic
~~~

Trong rolling deploy, hai pods có thể cùng tham gia main consumer group nhưng khi lỗi lại forward tới **hai topology khác nhau**. Một phần retries nằm ở topics cũ, phần khác nằm ở topic mới. Vì vậy nếu không có kế hoạch tương thích:

- Old retry consumers có thể bị scale về 0 quá sớm.
- New retry consumers không đọc old topics.
- DLT handlers hoặc serializers khác nhau giữa hai versions.
- Rebalance làm một event bị redeliver.
- Business effect ở DB/API có thể bị nhân đôi.

Không đánh giá rollout chỉ bằng “pod Ready”. Cần test event đi qua main, old/new retry destinations, DLT và downstream theo **business key duy nhất**.

## 10. Provision Kafka topics đúng theo topology

Một retry infrastructure cần có topics thực với partitions, replication, retention, cleanup policy, ACL và quota phù hợp.

### Test: cho phép auto-creation

~~~java
@RetryableTopic(
    attempts = "3",
    backoff = @Backoff(delay = 500),
    autoCreateTopics = "true",
    numPartitions = "1",
    replicationFactor = "1"
)
@KafkaListener(topics = "orders.events")
void handle(String value) {
    // Test demo.
}
~~~

Thông số replication factor 1 phù hợp với test broker một node, **không phải** mặc định production. Tạo topic tự động cần KafkaAdmin/permissions phù hợp; khi thiếu quyền hoặc broker không đủ replicas, topic creation có thể thất bại.

### Production: provision trước, tắt auto-create

~~~java
@RetryableTopic(
    attempts = "4",
    autoCreateTopics = "false",
    retryTopicSuffix = "-retry",
    dltTopicSuffix = "-dlt"
)
@KafkaListener(topics = "orders.events", groupId = "orders-processor")
void handle(String eventId) {
    // Business processing.
}
~~~

Trước rollout, hạ tầng phải tạo **đủ topics đúng tên đã xác minh**. Một inventory ví dụ:

~~~yaml
# Khai báo inventory minh họa, KHÔNG phải Kafka CRD đầy đủ.
sourceTopic: orders.events
sourcePartitions: 6
retryPolicy:
  maxAttempts: 4
  backoff: exponential
  initialDelayMs: 1000
  multiplier: 2
topics:
  - name: orders.events-retry-1000
    partitions: 6
  - name: orders.events-retry-2000
    partitions: 6
  - name: orders.events-retry-4000
    partitions: 6
  - name: orders.events-dlt
    partitions: 6
owner: kafka-platform
~~~

Danh sách trên chỉ đúng cho **một topology đã chọn**; fixed backoff, reuse strategy hoặc custom naming sẽ cho tên khác. Hạ tầng và code phải chia sẻ **một source of truth cho destination names**.

### Partition routing

Retry/DLT publisher thường cố giữ original partition. Nếu source có 6 partitions còn retry topic có 3, gửi lại record từ partition 5 có thể lỗi vì destination không có partition đó. Có thể cấu hình partition resolver trả `null` để producer tự chọn partition trong những kiến trúc cho phép, nhưng việc ấy thay đổi key affinity và ordering.

Kiểm tra:

- Partition count và producer routing của mọi retry/DLT topic.
- Replication factor tương thích số broker.
- Retention **dài hơn max backoff và cửa sổ khắc phục sự cố**.
- Producer có quyền WRITE vào retry/DLT; consumers có READ/group permissions.
- Message size/header growth và compression config.
- Có topic quotas hoặc throttling làm retry publisher timeout không?

Một số default provisioning thay theo release, chẳng hạn replication factor có thể dùng broker default. Đừng để bản nâng cấp bất ngờ tạo topics với độ bền hoặc partitions khác với tiêu chuẩn hạ tầng.

## 11. Consumer groups, offsets và concurrency

Retry topics có listener containers và consumer groups riêng. Group IDs thường kết hợp main group ID và suffix của retry destination. Nếu đổi tên topic hoặc listener group configuration, offsets trước đó **không tự xuất hiện** ở group mới.

| Điều thay đổi | Có thể xảy ra |
|---|---|
| Group ID khác | Offset reset behavior khác, replay hoặc bỏ dữ liệu cũ. |
| Concurrency retry container tăng | Throughput tăng nhưng DB/API downstream có thể quá tải. |
| Concurrency giảm | Retry backlog/latency tăng, cần điều chỉnh SLO. |
| Partition count tăng | Có thêm partition assignment, không tự bảo đảm ordering end-to-end. |
| Pod count và group rebalance | Record có thể được redeliver tại ranh giới commit. |

Từ Spring Kafka 3.0 có thể tùy chỉnh concurrency retry containers khác main container ở các API hỗ trợ. Một cấu hình main concurrency 6, retry concurrency 1 có thể hữu ích khi API downstream đang quá tải, nhưng phải đo thời gian drain backlog. Không tăng retry concurrency chỉ để “job chạy nhanh” nếu đó là nguyên nhân làm hệ thống đích thất bại.

**Không lấy lag của group mới bằng 0 làm bằng chứng toàn bộ retry đã xong.** Old groups có thể còn pending, và topic cũ có thể không còn được group nào subscribe.

## 12. Backoff timestamp, attempts và timeout

Ví dụ:

~~~text
T0           original attempt
T0 + ~1000ms retry attempt 2
Sau thất bại + ~2000ms retry attempt 3
Sau thất bại + ~4000ms retry attempt 4
Sau thất bại  DLT
~~~

Đây là thời gian **mong muốn**, không phải lịch chạy real-time chính xác. Scheduling, consumer pause/resume, broker lag, rebalance và downstream load có thể làm record đến muộn hơn.

Những điểm dễ nhầm:

- `maxAttempts=4` thường bao gồm original attempt.
- Topic count **không** luôn bằng attempts trừ một khi có reuse.
- Timeout toàn chuỗi retry có thể làm record đi DLT trước khi dùng hết số attempts.
- Blocking retry nếu được cấu hình kết hợp có thể phát sinh thêm lượt gọi listener.
- Header attempt/timestamp là một phần của semantics; đổi cách lưu/đọc headers có thể ảnh hưởng custom monitoring/compatibility.

Qua các phiên bản, Spring Kafka có lựa chọn giữ nhiều hay chỉ một giá trị của một số retry headers để hạn chế header growth. Nếu code vận hành đang đọc internal headers trực tiếp, hãy inventory tên header, trường hợp multi-value, và chính sách retain/strip trước khi nâng version.

## 13. Exception policy có thể làm topology trông đúng nhưng nghiệp vụ sai

Một record lỗi tạm thời nên được thử lại có giới hạn. Một record corrupt vĩnh viễn thường không tự trở nên hợp lệ chỉ nhờ gửi lại cùng bytes qua retry topics.

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 1_000, multiplier = 2.0),
    include = {TransientPartnerException.class},
    exclude = {InvalidOrderException.class}
)
@KafkaListener(topics = "orders.events", groupId = "orders-processor")
void handle(String eventId) {
    // Service xử lý event và có thể ném exception.
}
~~~

`TransientPartnerException` và `InvalidOrderException` trong ví dụ là exception tự định nghĩa. Cần xác nhận API include/exclude và cause traversal đúng release.

| Lỗi | Chính sách gợi ý |
|---|---|
| HTTP 503/429 với API idempotent | Retry có backoff, timeout và limits. |
| Deadlock database tạm thời | Retry khi transaction/replay an toàn. |
| JSON malformed vĩnh viễn | Thường DLT/stop, không retry cùng bytes vô hạn. |
| Sai schema version không tương thích | DLT/stop và sửa producer/consumer. |
| Authorization/ACL lỗi ghi retry topic | Sửa hạ tầng, không coi là lỗi dữ liệu của item. |
| Validation nghiệp vụ vĩnh viễn | Không retry mù quáng. |
| Bug code như NPE | Fail/escalate, tránh che lỗi bằng retries dài. |
| Schema registry tạm không khả dụng | Phân loại dựa vào khả năng hồi phục thực của client. |

Spring Kafka có các danh sách **fatal exceptions** trong non-blocking retry, và những API global để thêm/bớt danh sách đó. Sau upgrade, kiểm chứng một exception cụ thể được route qua retry stages hay thẳng DLT; chỉ so topic count không kiểm chứng được lỗi classifier.

## 14. Serialization và ErrorHandlingDeserializer là điểm migration nhạy cảm

Retry/DLT record có thể chứa:

- DTO hoặc String đã deserialize thành công, sau đó listener ném exception.
- **Raw `byte[]`** khi value deserialization thất bại và `ErrorHandlingDeserializer` giữ bytes gốc cho recoverer.
- Raw key bytes khi **key deserialization** thất bại.
- Headers của producer/consumer đời cũ với schema/type information khác đời mới.

Vì vậy retry/DLT `KafkaTemplate` có thể cần serializer hỗ trợ nhiều runtime types.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.apache.kafka.common.serialization.Serializer;
import org.springframework.kafka.support.serializer.DelegatingByTypeSerializer;
import org.springframework.kafka.support.serializer.JsonSerializer;

Map<Class<?>, Serializer<?>> serializers = new LinkedHashMap<>();
serializers.put(byte[].class, new ByteArraySerializer());
serializers.put(OrderEvent.class, new JsonSerializer<>());

var retryValueSerializer = new DelegatingByTypeSerializer(serializers);
~~~

`OrderEvent` là DTO ứng dụng; đây là fragment minh họa, chưa phải một `ProducerFactory` đầy đủ. Với Spring Kafka 4.x, kiểm tra serializer JSON/Jackson API tương ứng phiên bản đích, không sao chép nguyên import từ bản 3.x mà không kiểm chứng. Nếu key cũng có thể là raw bytes, key serializer phải hỗ trợ tương ứng; `StringSerializer` đơn lẻ không xử lý được mọi tình huống.

### Compatibility của retry backlog cũ

Nếu producer version cũ đã gửi một serialized DTO vào retry topic, consumer version mới phải:

1. Đọc đúng format bytes cũ.
2. Xử lý type headers/target package theo policy bảo mật.
3. Giữ event ID và ngữ nghĩa nghiệp vụ.
4. Bảo đảm exception metadata có đủ để phân loại/recover.
5. Không deserialize class không tin cậy chỉ để cho migration đi qua.

Khi đổi JSON serializer, schema registry hoặc event class, nên có **compatibility integration test** mà app cũ tạo record, app mới consume record đó. Không đánh giá đủ chỉ bằng test nơi app mới tự publish rồi tự consume.

## 15. DLT infrastructure cũng phải được migrate

Dead Letter Topic là nơi record đã hết retry hoặc bị phân loại fatal được cách ly. Nó có topic, producer, consumer group/handler, retention và quy trình remediation riêng.

~~~java
@DltHandler
public void handleDlt(String payload) {
    quarantineService.storeForReview(payload);
}
~~~

Đoạn trên là fragment: `quarantineService` thuộc ứng dụng, cần xử lý dữ liệu nhạy cảm an toàn, idempotency và transaction phù hợp.

Những điều cần kiểm tra:

- Tên DLT vẫn đúng không? Có custom DLT theo exception type không?
- DLT topic đã provision/ACL đúng chưa?
- Khi không có `@DltHandler`, mặc định handler/consumer logging có phù hợp nghiệp vụ không?
- Nếu DLT do service khác xử lý, có cần disable auto-start DLT handler trong app hiện tại không?
- Khi DLT handler lỗi, chính sách `ALWAYS_RETRY_ON_ERROR` hay `FAIL_ON_ERROR` được dùng?
- Những DLT records cũ có schema đọc được bởi handler mới không?
- Retention có đủ cho thời gian điều tra/replay?

Một DLT consumer **đọc và ghi log** không đồng nghĩa event nghiệp vụ đã được sửa hoặc được phê duyệt bỏ. Phải có trạng thái remediation và owner chịu trách nhiệm.

## 16. Những giới hạn tính năng không thể bỏ qua

Non-blocking retries của Spring Kafka có các giới hạn chính thức quan trọng:

- **Không hỗ trợ non-blocking retries với batch listeners** theo feature này.
- **Không kết hợp non-blocking retries với container transactions** theo semantics hỗ trợ.

Nếu cùng một upgrade bạn chuyển `@KafkaListener` record-level sang batch-level hoặc bật container transactions, phải thiết kế lại recovery path. Không giữ annotation rồi suy rằng framework sẽ xử lý tương tự.

Các lựa chọn khác có thể là blocking retries, transaction rollback/after-rollback handling hoặc kiến trúc durable intent riêng, tùy yêu cầu Kafka offset và business transaction. Sự lựa chọn phải được kiểm thử trên đúng loại container và broker.

## 17. Non-blocking retry làm thay đổi ordering

Ví dụ trên một partition:

~~~text
offset 100: OrderUpdated(order-A, version=1) -> fail -> retry topic
offset 101: OrderUpdated(order-A, version=2) -> success trên main topic

Sau đó:
retry consumer xử lý version=1
~~~

Kafka giữ thứ tự **trong một partition của một topic**, nhưng khi record v1 được chuyển sang retry topic, handler có thể áp dụng v2 trước rồi mới v1. Nếu writer cập nhật database “last write wins” không kiểm tra version, trạng thái sẽ bị quay lùi.

Do đó nếu chuyển từ blocking retry sang non-blocking retry:

- Thiết kế `aggregateVersion`/sequence và optimistic locking.
- Đảm bảo consumer idempotent theo event ID.
- Có chính sách xử lý event đến muộn hoặc ngoài thứ tự.
- Với nghiệp vụ cần strict ordering, cân nhắc giữ blocking retry hoặc mô hình khác.

Đây là thay đổi **semantic nghiệp vụ**, không chỉ là tối ưu throughput.

## 18. Migration an toàn theo hai giai đoạn

### Giai đoạn A — Nâng thư viện, giữ topology hiện tại

1. Chốt version và topology cũ từ broker/config.
2. Chuyển global bootstrap config theo API tương thích nếu cần.
3. Cố định attempts, suffixing, reuse, timeout, fatal exceptions và DLT strategy tường minh.
4. Giữ names và consumer groups cũ nếu có thể.
5. Chạy test payload từ app cũ trên consumer bản mới.
6. Xác minh retry topics đang chờ được đọc tiếp và DLT vẫn hoạt động.
7. Deploy canary/rolling và theo dõi cả old/new retries.

### Giai đoạn B — Thay topic reuse/naming có chủ đích

1. Chọn topology mới và reasons (giảm topic count, quản lý dễ hơn, giảm broker load...).
2. Provision topics, partitions, replication và ACL.
3. Drain/bridge backlogs ở topology cũ.
4. Chuyển publishers/listeners theo cutover plan.
5. Kiểm tra business idempotency và DLT.
6. Chỉ decommission old topics khi không còn record cần xử lý.

Nếu phải gộp hai giai đoạn vào một deploy, cần test cross-version bridge/rollback cẩn thận hơn; không thể coi nó là một dependency bump thông thường.

## 19. Runbook cutover retry topology

### Trước cutover

| Việc | Chứng cứ mong đợi |
|---|---|
| Snapshot names/partitions/groups cũ | Inventory lưu theo deployment ID. |
| Tính max backoff + retention window | Đủ thời gian drain và điều tra. |
| Xác định ai còn publish vào old retries | Danh sách producers và thời điểm dừng. |
| Provision new retry/DLT topics | Topic settings và ACL được xác nhận. |
| Kiểm tra rollback plan | Có consumer/bridge đọc new topics nếu phải quay về cũ. |
| Test idempotency | Một event replay hai lần vẫn chỉ một business effect. |
| DLT remediation owner | Có người/kênh chịu trách nhiệm records thất bại. |

### Trong cutover

1. Ghi thời điểm cụ thể kèm timezone, versions và thay đổi config.
2. Hạn chế producers cũ phát sinh retry destinations mới theo kế hoạch.
3. Giữ old retry consumers hoặc bridge cho tới khi đủ bằng chứng drain.
4. Bật new consumers, kiểm tra partition assignments/group IDs.
5. Gửi event probe có business ID riêng, tạo transient/permanent failures.
6. Kiểm tra retry delay, attempts, suffix, DLT và publish acknowledgement.
7. Theo dõi **old topics và new topics đồng thời**.

### Sau cutover

Đóng migration chỉ khi old retry backlog không bị orphan, không có producer gửi tiếp old topics, DLT có disposition phù hợp và business outputs được đối soát. Không xóa old topics ngay nếu cần audit/retention hoặc khi có khả năng rollback.

## 20. Một integration test kiểm chứng retry chain

Unit test gọi listener trực tiếp **không kiểm chứng** topic names, broker forwarding, consumer groups hoặc delay. Cần tích hợp Kafka broker trong test: Embedded Kafka hoặc Testcontainers/cluster test.

### Listener test probe

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
public class RetryProbeListener {

    private final ConcurrentHashMap<String, AtomicInteger> counts =
        new ConcurrentHashMap<>();
    private final CountDownLatch completed = new CountDownLatch(1);

    @RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 500),
        autoCreateTopics = "true",
        numPartitions = "1",
        replicationFactor = "1"
    )
    @KafkaListener(topics = "upgrade.orders", groupId = "upgrade-probe")
    public void onMessage(String id) {
        int attempt = counts.computeIfAbsent(
            id, ignored -> new AtomicInteger()).incrementAndGet();

        if (attempt <= 2) {
            throw new TestTransientException("TEST_TRANSIENT");
        }

        completed.countDown();
    }

    public boolean awaitCompletion() throws InterruptedException {
        return completed.await(20, TimeUnit.SECONDS);
    }

    public int attempts(String id) {
        AtomicInteger n = counts.get(id);
        return n == null ? 0 : n.get();
    }
}
~~~

`TestTransientException` là exception test tự định nghĩa. Probe dùng in-memory state chỉ để quan sát trong test cô lập, không dùng làm bộ đếm bền vững cho production hoặc multi-node.

### Khung Embedded Kafka test

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;

@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = {"upgrade.orders"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class RetryUpgradeIntegrationTest {

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    RetryProbeListener probe;

    @Test
    void transientFailureIsRetriedThenSucceeds() throws Exception {
        String eventId = "upgrade-test-001";

        kafkaTemplate.send("upgrade.orders", eventId, eventId)
            .get(10, TimeUnit.SECONDS);

        assertThat(probe.awaitCompletion()).isTrue();
        assertThat(probe.attempts(eventId)).isEqualTo(3);
    }
}
~~~

**Giả định:** context có KafkaTemplate và RetryProbeListener được cấu hình; KafkaAdmin/`@RetryableTopic` tạo các topics theo test policy, container đủ thời gian assign partition. Test không chạy chồng với suite khác dùng cùng group/topic/state. Cần tạo test exception class, producer config và Kafka broker test phù hợp.

Test trên chứng minh listener được gọi lại và hoàn tất, nhưng **chưa đủ** để chứng minh migration. Phải mở rộng assertion về retry topic names, actual consumer groups, DLT và old backlog.

## 21. Test topology cũ sang topology mới

Để kiểm tra compatibility, xây một tình huống:

~~~text
T0: old app gửi record R vào orders.events-retry-1
T1: old app dừng
T2: new app start với orders.events-retry
T3: ai xử lý R?
~~~

Các đáp án đúng phụ thuộc phương án:

- **Giữ topic cũ:** new consumer thực sự subscribe old topic và xử lý R.
- **Drain:** old consumer vẫn chạy cho đến khi R có outcome cuối.
- **Bridge:** component chuyển R sang path mới, giữ event ID và retry semantics được phê duyệt.
- **Reprocess:** có record audit và idempotency bảo đảm replay không ghi trùng.

**Không chấp nhận “new consumer lag=0” là kết quả test**. Nó không đo lag của old topic. Nếu có thể, dùng hai version app thực tế: cho old app tạo retry record/headers, sau đó new app consume. Cách này đáng tin hơn tự giả lập headers nội bộ bằng suy đoán.

### DLT test

Gửi record cố ý lỗi vĩnh viễn, kiểm tra:

1. Đúng số attempts theo policy đã chọn.
2. Event tới đúng DLT topic.
3. Metadata nguồn/exception headers đủ truy vết.
4. DLT producer serializer phù hợp cả DTO và raw bytes nếu được dùng.
5. DLT consumer/quarantine có outcome rõ, không chỉ ghi log.

Nếu DLT publish fail, phải test offset/recovery semantics: không được coi record gốc đã recovery thành công một cách âm thầm theo những hợp đồng yêu cầu không mất event.

## 22. Test rollback và duplicate khi rolling deploy

Với non-blocking retry, một event có thể được handler nhìn thấy nhiều lần. Nếu handler ghi DB:

~~~sql
-- Anti-pattern khi event có thể replay.
UPDATE account
SET balance = balance + :amount
WHERE account_id = :accountId;
~~~

Nếu lệnh trên đã commit rồi lỗi xảy ra trước Kafka ack/offset commit, retry có thể cộng tiền lần nữa. Tăng rủi ro khi hai phiên bản cùng chạy.

Thay vào đó cần:

- Event ID bền vững từ producer.
- Unique processed-event marker cùng DB transaction với business update.
- Idempotency key/tra trạng thái remote API.
- Version guard nếu ordering theo aggregate quan trọng.
- Đối chiếu dữ liệu cuối theo event ID thay vì đếm callback.

Test fault injection:

~~~text
Attempt 1: business DB commit -> crash trước Kafka ack
Attempt 2: record được redeliver -> business effect KHÔNG tăng lần hai
~~~

Đồng thời test một record được bản cũ republish rồi bản mới xử lý và ngược lại nếu có rollback. **Kafka producer idempotence không thay thế idempotency nghiệp vụ** khi nhiều application attempts phát cùng event.

## 23. Ma trận kiểm thử upgrade

| ID | Kịch bản | Kết quả phải xác minh |
|---|---|---|
| U-01 | Valid event. | Main listener xử lý đúng, không retry. |
| U-02 | Transient exception vài lần rồi thành công. | Retry attempts/route đúng. |
| U-03 | Permanent exception. | DLT/stop đúng policy, không retry vô hạn. |
| U-04 | Hết max attempts. | DLT có record và metadata nguồn. |
| U-05 | Fixed-delay reuse khác giữa versions. | Topic names/consumer groups đúng thiết kế. |
| U-06 | Exponential đạt max interval. | Reuse hoặc multiple-topic strategy đúng. |
| U-07 | Old retry topic còn backlog. | Record được drain/bridge/xử lý, không orphan. |
| U-08 | Mixed-version rolling deploy. | Không mất/trùng business effects. |
| U-09 | Retry destination thiếu partition. | Publish error được báo, không silent loss. |
| U-10 | Topic chưa được provision / thiếu ACL. | Startup/publish được giám sát và có rollback. |
| U-11 | DLT producer sai serializer raw bytes. | Recovery failure được phát hiện. |
| U-12 | Key deserialization thất bại. | Raw key được xử lý qua publisher phù hợp. |
| U-13 | Consumer group ID thay. | Offset reset/replay theo kế hoạch. |
| U-14 | Retry consumer rebalance. | Backoff/progression/duplicate tolerance đúng. |
| U-15 | App crash sau retry publish ACK. | Không nhân đôi business effect. |
| U-16 | DLT handler lỗi. | DLT failure strategy/alert đúng. |
| U-17 | JSON/type headers từ version cũ. | New consumer decode hoặc route an toàn. |
| U-18 | Hai listeners cùng một source topic. | Không có policy conflict ngầm. |
| U-19 | Retry concurrency thay. | Không làm downstream overload. |
| U-20 | Retention ngắn hơn recovery window. | Rủi ro được phát hiện trước khi mất record. |
| U-21 | Rollback từ new sang old deployment. | New retry backlog vẫn có đường recovery. |
| U-22 | Reprocess từ DLT. | Event ID được giữ, audit/idempotency đúng. |

Nên ưu tiên U-05, U-07, U-08 và U-21 vì đây là các lỗi đặc trưng của **migration retry infrastructure**, không xuất hiện trong test listener happy path thông thường.

## 24. Observability trong thời gian migration

Một dashboard chỉ theo dõi source topic chưa đủ. Cần số liệu từ **cả topology cũ và mới**:

| Khu vực | Tín hiệu |
|---|---|
| Main topic | Processing rate, failure, lag, rebalance, consumer groups. |
| Old retry topics | Lag theo old groups, số pending records, lần cuối có publisher. |
| New retry topics | Publish success/failure, retry rate, lag, oldest pending age. |
| DLT | Incoming rate, backlog chưa remediation, failed DLT handler. |
| Producer forwarding | Serialization errors, Kafka ACK failures, ACL/quota errors. |
| Retry containers | Active containers, partitions assigned, pause/resume, concurrency. |
| Business output | Dedup count, mismatched versions, missing/duplicate event IDs. |
| End-to-end | Source event → completed/DLT/replayed/quarantined outcome. |

Ví dụ structured log (ứng dụng tự định nghĩa):

~~~json
{
  "event": "kafka.retry.forwarded",
  "deploymentVersion": "orders-vNext",
  "sourceTopic": "orders.events",
  "destinationTopic": "orders.events-retry",
  "consumerGroup": "orders-processor",
  "attempt": 2,
  "errorCategory": "PARTNER_TEMPORARY_FAILURE",
  "result": "PUBLISHED"
}
~~~

Không log raw payload, credential hoặc full headers chứa exception stack traces chưa được đánh giá. Không dùng event ID/offset làm metric label cardinality cao; ID chi tiết có thể lưu trong audit/tracing được bảo vệ.

### Vì sao “lag=0” chưa chứng minh drained?

Lag bằng 0 của một consumer group chỉ phản ánh tiến độ group đó trên các partitions được xác định. Nó không chứng minh không có producer mới gửi tiếp, không có old group khác, không có DLT chưa xử lý, hoặc downstream DB đã đúng. Decommission phải dựa trên **inventory producers + groups + pending records + business outcomes**.

## 25. Rollback khi deployment mới không đúng

Rollback application image về version cũ **không đủ** nếu version mới đã publish record sang new retry topics mà version cũ không subscribe.

Quy trình:

1. Chốt thời gian, version, destination topics mà bản mới đã ghi.
2. Tạm ngừng thay đổi topology tiếp theo theo phê duyệt.
3. Inventory backlog trong **new retry topics và DLT**.
4. Xác định old version có thể đọc new destination hay cần bridge/compatibility consumer.
5. Khôi phục app cũ và kiểm tra main/retry groups.
6. Xử lý record ở cả old/new topology, đối soát theo event ID.
7. Kiểm tra serializer/schema của payload do app mới tạo.
8. Chỉ dọn new topics khi đã có bằng chứng mọi record có disposition cuối và không cần retention/audit.

**Không xóa mọi topic mới để dashboard trông xanh.** Điều đó có thể xóa những event chưa có kết quả. Tương tự, không reset consumer group offsets chỉ để consumer chạy tiếp khi chưa có kế hoạch replay/idempotency.

## 26. Runbook điều tra sau upgrade

Khi record lỗi không còn retry hoặc DLT thiếu event:

**A. Xác định record và trạng thái**

~~~text
springKafkaVersion / deploymentVersion
sourceTopic / partition / offset
consumerGroup / listenerId
businessEventId
expected exception category
expected attempts / backoff
last observed destination
~~~

**B. Kiểm tra configuration**

- `@RetryableTopic` có được phát hiện không?
- Có đồng thời hai con đường global bootstrap không?
- Có `RetryTopicConfiguration` bean khác áp lên cùng source topic không?
- Retry naming/reuse/index/delay strategy đã đổi chưa?
- KafkaTemplate producer serializers có đọc/ghi được record cũ không?
- Fatal exception list và DLT routing có thay không?

**C. Kiểm tra broker**

- Topics thực đã tồn tại đủ partitions/replication chưa?
- Publisher có quyền WRITE và nhận ACK từ retry/DLT không?
- Retry consumer groups có assigned partitions và committed offsets đúng không?
- Old retry topics có orphan backlog?
- DLT consumer/handler đang chạy theo policy?

**D. Quyết định recovery**

- Có record nào đã tạo business side effect?
- Retry records đang ở topology cũ hay mới?
- Cần drain, bridge, rollback hoặc replay?
- Có duplicate/out-of-order event cần đối soát?
- Ai phê duyệt hành động thay data/topic/offset?

**E. Tiêu chí đóng**

Đóng sự cố khi các event cần xử lý đã có outcome, old/new backlog không còn orphaned, DLT được quản lý và dữ liệu nghiệp vụ không sai hoặc trùng ngoài hợp đồng. “Pod Running” không phải điều kiện đóng duy nhất.

## 27. Những anti-pattern thường gặp

**“Chỉ nâng dependency, retry infrastructure chắc không đổi.”** Mặc định naming/reuse, global bootstrap và các hooks có thể đã thay.

**“Suffix vẫn là -retry nghĩa names giống nhau.”** Có thể thêm delay/index hoặc reuse làm tên khác.

**“Spring Kafka tự migrate records sang topic mới.”** Không; Kafka topics là các logs riêng.

**“Dùng cả `@EnableKafkaRetryTopic` và extends `RetryTopicConfigurationSupport` cho chắc.”** Có thể gây duplicate beans và context failure.

**“Mỗi `@RetryableTopic` trên cùng source topic có cấu hình riêng tuyệt đối.”** Không luôn; phải tránh policy conflict.

**“maxAttempts=4 nghĩa phải có bốn retry topics.”** Không; thường bao gồm original attempt, còn topic count phụ thuộc reuse.

**“Backoff=1000ms là deadline đúng tuyệt đối.”** Scheduling/consumer lag/rebalance khiến actual handling trễ hơn.

**“Group ID mới không ảnh hưởng dữ liệu.”** Offset tracking thuộc group; có nguy cơ replay/skip.

**“DLT có record là nghiệp vụ hoàn tất.”** DLT là nơi cách ly, cần remediation.

**“Non-blocking retry vẫn giữ order theo key với source topic.”** Không giữa các topics; event sau có thể chạy trước.

**“Non-blocking retries hỗ trợ mọi batch listener và container transaction.”** Không theo giới hạn feature.

**“Chỉ cần JsonSerializer cho mọi retry/DLT record.”** Deserialization error có thể cần raw byte[] producer.

**“Old retry lag bằng 0 ngay lúc deploy là đủ để xóa topic.”** Còn producers đang gửi, DLT hoặc các groups khác.

**“Rollback chỉ đổi app image.”** Cần xử lý records mà version mới đã publish.

**“Để topic retention ngắn cho tiết kiệm.”** Retry backoff và outage có thể vượt retention, dẫn tới mất record trước khi tới hạn.

## 28. Checklist thay đổi retry topic infrastructure

### Trước thay đổi

- [ ] Khóa version cũ/mới của Spring Boot, Spring Kafka, Kafka clients và broker.
- [ ] Inventory `@RetryableTopic`, beans, support class và listeners cùng source topic.
- [ ] Chốt attempts, backoff, timeout, fatal exceptions, DLT, topic suffix/index/delay/reuse.
- [ ] Ghi chính xác old retry/DLT topics, partitions, ACL, retention và consumer groups.
- [ ] Xác định old backlog và mọi producer còn ghi tới old topics.
- [ ] Kiểm tra serializer cho DTO, raw byte[] và payload phiên bản cũ.
- [ ] Chọn giữ topology, drain hoặc bridge có owner.
- [ ] Kiểm tra compatibility với batch listeners/container transactions.
- [ ] Có rollback plan cho **cả Kafka data**, không chỉ application binary.

### Trong thử nghiệm và rollout

- [ ] Provision destinations đúng topology đích.
- [ ] Test transient/permanent errors, attempts, DLT và retry timestamps.
- [ ] Test records ở old retry topics sau upgrade.
- [ ] Test Kafka groups/offset progression và mixed-version deploy.
- [ ] Test DLT publish failures, serializer mismatch và partitions.
- [ ] Test business idempotency, duplicate và ordering guard.
- [ ] Quan sát old/new retry lag và consumers cùng lúc.

### Sau rollout

- [ ] Không còn record cần xử lý bị orphan ở old topics.
- [ ] Không còn publisher nào bất ngờ gửi sang old retry destinations.
- [ ] DLT có owner và các event có disposition/replay phù hợp.
- [ ] Business output được đối soát theo event IDs/version.
- [ ] Recovery/rollback vẫn có thể thực hiện nếu xuất hiện sự cố.
- [ ] Chỉ decommission old topics khi đã được phê duyệt và có bằng chứng.
- [ ] Cập nhật runbook, topic manifest, dashboards và tài liệu topology.

## 29. Tài liệu chính thức và cách dùng đúng phiên bản

Để xác minh sự khác biệt trong dự án, tham khảo tài liệu **cùng version với Spring Kafka đang chạy hoặc sẽ triển khai**:

- [Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html) — cơ chế hoạt động và các giới hạn.
- [Retry Topic Configuration](https://docs.spring.io/spring-kafka/reference/retrytopic/retry-config.html) — annotation, builder và global bootstrap.
- [Topic Naming](https://docs.spring.io/spring-kafka/reference/retrytopic/topic-naming.html) — suffix, delay/index, single/multiple topic reuse.
- [Retry Topic Features](https://docs.spring.io/spring-kafka/reference/retrytopic/features.html) — backoff, classifier, timeout, headers, DLT routing.
- [DLT Strategies](https://docs.spring.io/spring-kafka/reference/retrytopic/dlt-strategies.html) — DLT handler và failure policy.
- [Kafka Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html) — transaction semantics và giới hạn với non-blocking retry.

Các trang reference không có version cụ thể thường hiển thị stable release hiện tại. Hãy dùng version selector/tài liệu 3.x nếu dự án đang ở 3.x; không copy thuộc tính chỉ có trong 4.1 vào source code cũ rồi coi đó là migration tương thích.

## Kết luận

**Thay đổi retry topic infrastructure** là một thay đổi có thể ảnh hưởng trực tiếp đến **đường đi của record lỗi, consumer-group offsets và tính nhất quán của kết quả nghiệp vụ**. Spring Kafka 2.9 thay cách bootstrap/customize infrastructure; các phiên bản 3.x mở rộng API và chiến lược reuse; Spring Kafka 4.1 thay default reuse các retry intervals giống nhau. Vì vậy, cùng một policy attempts/backoff không bảo đảm luôn sinh cùng topic names ở mọi release.

Muốn nâng cấp tin cậy, hãy **chốt topology cũ trước khi sửa code**, cấu hình tường minh những default có thể đổi, kiểm tra records đang chờ trên old retry topics, thực hiện drain/bridge hoặc giữ topology tương thích, rồi thử lỗi và rollback trên Kafka broker thật trong test. Sau deployment, quan sát cả old/new topics, DLT, offsets, serialization và business idempotency. Chỉ khi mọi record có kết quả kiểm chứng được và không còn backlog bị bỏ rơi, migration mới thật sự hoàn tất.
