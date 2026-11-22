# EOSMode.V2 và phiên bản framework trong Spring Kafka Reliability Operations

Nâng cấp một dịch vụ Spring Kafka đang dùng transaction từ dòng **2.x** lên **3.x hoặc 4.x** có thể làm thay đổi cách framework bảo vệ consumer group khỏi producer cũ (*zombie producer*). Cấu hình từng chạy ổn với `EOSMode.V1`, `ALPHA` hoặc `producerPerConsumerPartition=true` có thể không còn phù hợp. Nếu Kafka broker quá cũ, ứng dụng mới có thể không khởi động được transaction. Nếu `transactional.id` bị dùng chung giữa các pod, hệ thống có thể gặp `ProducerFencedException`. Nếu đầu ra được tiêu thụ bằng `read_uncommitted`, test còn có thể nhìn thấy những record thuộc giao dịch đã abort rồi kết luận sai rằng exactly-once không hoạt động.

Vì vậy, câu hỏi **“EOSMode.V2 và phiên bản framework”** không chỉ là đổi một enum. Đây là quyết định tương thích xuyên suốt **Spring Kafka → Kafka client → Kafka broker → producer identity → consumer group → listener container → integration test**.

Bài viết thuộc **Spring Kafka Reliability Operations → Nâng cấp và tương thích**. Nội dung giúp xác định điều kiện sử dụng `EOSMode.V2`, hiểu vì sao `V1` biến mất từ Spring Kafka 3.0, chuẩn bị nâng cấp theo thứ tự an toàn, cấu hình Spring Boot và kiểm chứng luồng **Kafka input → xử lý → Kafka output** bằng transaction. Các ví dụ cấu hình dùng chủ yếu **Spring Boot 3.x, Spring Kafka 3.x và Java 17**; phần tương thích 2.x và 4.x được ghi riêng để tránh sao chép API chéo phiên bản.

## 1. EOS trong Spring Kafka bảo đảm điều gì?

Khi ứng dụng nhận record từ Kafka, xử lý và gửi record mới lên Kafka, Spring Kafka có thể quản lý **consumer offsets và output records trong cùng một Kafka transaction**:

```text
Kafka topic: payments.in
       |
       v
Consumer trong listener container
       |
       v
BEGIN Kafka transaction
       |
       v
@KafkaListener xử lý input
       |
       v
KafkaTemplate.send("payments.out", ...)
       |
       v
Container gửi consumed offsets vào transaction
       |
       +------ COMMIT ------> output visible với read_committed
       |                       + group offset được commit
       |
       +------ ABORT -------> output bị che với read_committed
                               + group offset không được commit
                               + input có thể được đọc lại
```

Nói chính xác:

- Phần **đọc và xử lý** có thể được thực thi hơn một lần sau rollback. Listener không được bảo đảm “chỉ gọi một lần”.
- Phần **ghi Kafka output và commit consumed offsets** được điều phối qua Kafka transaction nhằm đạt exactly-once semantics cho chuỗi read–process–write trong phạm vi Kafka.
- Consumer downstream cần `isolation.level=read_committed` để không đọc output thuộc Kafka transaction đã abort.
- Ghi database, gọi REST API, thanh toán hoặc gửi email **không tự nằm trong Kafka transaction**. Exactly-once nghiệp vụ ngoài Kafka còn cần idempotency, outbox/inbox hoặc cơ chế consistency riêng.

Đây là nền tảng chung cho cả V1 và V2. **Sự khác biệt chính giữa V1/V2 là cách broker xác định một producer/consumer không còn sở hữu hợp lệ partition khi commit consumed offsets**, không phải V2 có thể biến side effect ngoài Kafka thành một transaction phân tán.

## 2. V1 và V2: khác nhau ở cơ chế fencing

Trong quá trình phát triển của Spring Kafka, EOS đã có hai cơ chế được gọi bằng các tên lịch sử khác nhau:

| Tên cũ | Tên mới | Cơ chế chính | Điều kiện |
| --- | --- | --- | --- |
| `ALPHA` | `EOSMode.V1` | Fencing dựa trên `transactional.id` gắn với danh tính `group.id/topic/partition` | Cơ chế cũ, dành cho những broker đời trước |
| `BETA` | `EOSMode.V2` | *Fetch-offset-request fencing*, sử dụng consumer group metadata cùng offsets trong transaction | **Kafka broker từ 2.5 trở lên** |
 
### Cơ chế V1: transaction ID theo partition

V1 bảo vệ zombie consumer bằng cách bố trí producer/`transactional.id` theo `group.id/topic/partition`. Khi partition được giao cho consumer mới, producer mới có thể sử dụng cùng transactional identity để broker fence producer cũ. Vì vậy V1 thường cần **producer theo mỗi consumer partition**, làm số lượng transactional producer tăng theo partition/concurrency.

```text
Consumer group G
  topic A / partition 0 ----> Producer txn ID cho G/A/0
  topic A / partition 1 ----> Producer txn ID cho G/A/1
  topic A / partition 2 ----> Producer txn ID cho G/A/2

Rebalance:
  instance mới sở hữu G/A/1
        |
        v
  dùng lại transactional identity phù hợp
        |
        v
  broker fence producer cũ
```

Mô hình đó phục vụ nhu cầu đảm bảo transaction/offset không bị producer đã mất ownership tiếp tục commit. Tuy nhiên, nó làm việc quản lý producer theo partition phức tạp hơn.

### Cơ chế V2: consumer group metadata hỗ trợ fencing

Theo **KIP-447**, producer gửi **consumer group metadata** cùng consumed offsets vào Kafka transaction. Broker có thể kiểm tra tính hợp lệ của ownership/group generation khi xử lý offsets, thay vì buộc ứng dụng quản lý một producer theo từng `group.id/topic/partition`.

```text
Consumer G / member M / generation N
                 |
                 v
         Nhận partition P
                 |
                 v
        Producer transactional
                 |
          send(output)
                 |
          sendOffsetsToTransaction(
              offsets,
              consumer.groupMetadata()
          )
                 |
                 v
        Broker xác nhận group ownership
                 |
         +-------+--------+
         |                |
      Hợp lệ          Stale member/
         |             generation
         v                |
      COMMIT              v
                     reject/fence transaction
```

Mã sau là **minh họa API Kafka client về nguyên lý**, không phải yêu cầu tự gọi trong `@KafkaListener`:

```java
producer.beginTransaction();
producer.send(outputRecord);

// consumer.groupMetadata() cung cấp ngữ cảnh group membership.
producer.sendOffsetsToTransaction(
        consumedOffsets,
        consumer.groupMetadata());

producer.commitTransaction();
```

Trong Spring Kafka, **listener container** thực hiện bước gửi offsets vào transaction nếu được cấu hình transaction manager đúng. Ứng dụng thông thường chỉ cần gọi `KafkaTemplate.send(...)` bên trong listener, không tự commit consumer offsets.

**Ý nghĩa về số producer:** với V2, không cần một transactional producer cho từng partition chỉ để fence zombie. Spring Kafka có thể dùng một cache các transactional producers phục vụ giao dịch thực tế, giúp giảm overhead và linh hoạt với concurrency. Nhưng V2 **không có nghĩa chỉ một producer duy nhất cho toàn bộ cluster**.

## 3. Dòng thời gian EOSMode qua các phiên bản

Những mốc sau hữu ích khi đọc một codebase đã tồn tại nhiều năm:

| Spring Kafka | EOS mode có liên quan | Điểm cần nhớ khi nâng cấp |
| --- | --- | --- |
| **Trước 2.5** | Các cơ chế transactional EOS cũ | Không giả định `EOSMode.V2` đã có; đọc docs chính xác của bản đang dùng |
| **2.5** | `ALPHA` / `BETA` | Bắt đầu hỗ trợ cơ chế V2 theo KIP-447, yêu cầu broker hỗ trợ |
| **2.6–2.7** | V2/BETA trở thành mặc định; V1/ALPHA vẫn tồn tại | Có giai đoạn client cũ hỗ trợ fallback giới hạn; không coi fallback là hợp đồng nâng cấp lâu dài |
| **2.8–2.9** | `V1` và `V2` cùng tồn tại; `ALPHA`/`BETA` là alias cũ | Với `kafka-clients` 3.0+, V2 **không tự fallback** về V1 khi broker dưới 2.5 |
| **3.0 trở lên** | **Chỉ hỗ trợ `EOSMode.V2`** | `V1`/`ALPHA` đã bị loại khỏi lựa chọn được hỗ trợ; Kafka broker tối thiểu cho giao dịch là **2.5** |
| **3.2 trở lên** | V2; bổ sung quản lý transactional ID suffix | Có `TransactionIdSuffixStrategy`, `DefaultTransactionIdSuffixStrategy` và vấn đề producer cache under concurrency |
| **4.x** | V2 tiếp tục là cơ chế EOS | Đồng thời cần kiểm tra tương thích Spring Framework/Boot/Kafka client và thay đổi test hạ tầng/KRaft |

**Hai mốc đặc biệt cần ghi nhớ:**

1. **Spring Kafka 2.6 đã mặc định V2**, nên nâng cấp từ 2.8 lên 2.9 không đồng nghĩa đến lúc đó mới bắt đầu sử dụng V2.
2. **Spring Kafka 3.0 chỉ còn V2**, do đó không thể giữ lâu dài một cấu hình production phụ thuộc `EOSMode.V1` để né yêu cầu nâng cấp Kafka broker.

Ở giai đoạn 2.8–2.9, tài liệu có hướng dẫn legacy dùng `V1` nếu broker còn dưới 2.5 và không hỗ trợ V2. Đó là **đường chuyển tiếp cho nhánh 2.x**, không phải cách cấu hình Spring Kafka 3.x.

### `ALPHA`/`BETA` không phải tính năng mới khác với `V1`/`V2`

Trong một số tài liệu cũ:

```text
ALPHA = V1  (transactional.id fencing)
BETA  = V2  (fetch-offset-request fencing)
```

Đây là **đổi tên mode**, không phải bốn chế độ hoạt động riêng. Nếu project có `EOSMode.BETA`, hãy nhận diện rằng nó đang chỉ cơ chế V2 rồi chuyển cấu hình sang API/default phù hợp phiên bản mới. Không nên dùng lại enum alias cũ trong code Spring Kafka 3.x/4.x.

## 4. Ma trận tương thích phải xem đủ bốn lớp

Nâng cấp Spring Kafka không thể chỉ nhìn một dòng version trong Gradle/Maven. Ít nhất phải xác định:

```text
Ứng dụng Java / Spring Boot
          |
          v
Spring Kafka library
          |
          v
Apache kafka-clients library
          |
          v
Kafka broker cluster + inter-broker protocol/features
          |
          v
Transactional ID / consumer group ownership
```

| Lớp | Cần xác minh | Nếu sai thì sao? |
| --- | --- | --- |
| **Spring Boot / Spring Framework** | BOM/dependency management có hỗ trợ Spring Kafka đang chọn không; Java baseline phù hợp không? | Lỗi class/API, auto-configuration, runtime incompatibility |
| **Spring Kafka** | `EOSMode`, listener container, producer factory, transaction manager có API nào? | Cấu hình cũ không compile hoặc transaction không được bật |
| **`kafka-clients`** | Kafka client version được dependency graph chọn; có bị override không? | Giao thức/client behavior thay đổi, lỗi runtime |
| **Kafka brokers** | Mọi broker cần phục vụ transactional EOS V2 đều đáp ứng **Kafka 2.5+** và cluster có transaction coordinator hoạt động | Transaction initialization/offset commit fail; không thể trông đợi fallback |
| **Deployment** | Prefix cho transactional producer có duy nhất giữa các application instance đồng thời không? | `ProducerFencedException` hoặc producer cạnh tranh |
| **Downstream** | Consumer đọc output với `read_committed` không? | Có thể quan sát record thuộc transaction abort và kết luận sai về EOS |

### Gợi ý mapping các dòng tương thích

Bảng tham chiếu mức **dòng sản phẩm** (version cụ thể phải theo BOM và compatibility matrix chính thức):

| Dòng ứng dụng | Spring Kafka thường đi cùng | Lưu ý |
| --- | --- | --- |
| Spring Boot 2.x đời cuối | Spring Kafka 2.8/2.9 theo bản Boot/BOM | Có thể còn legacy V1; kiểm tra broker trước khi nhảy lên 3.x |
| Spring Boot 3.1.x | Spring Kafka 3.0.x | EOS chỉ V2, Java 17 baseline của Boot 3 |
| Spring Boot 3.2.x | Spring Kafka 3.1.x | EOS chỉ V2 |
| Spring Boot 3.3.x | Spring Kafka 3.2.x | EOS chỉ V2, có thay đổi quản lý transaction suffix |
| Spring Boot 3.4.x | Spring Kafka 3.3.x | EOS chỉ V2 |
| Spring Boot 4.x | Spring Kafka 4.x theo bản Boot cụ thể | Kiểm tra Spring Framework 7/Kafka client 4.x, migration và test broker |

Đây là **gợi ý định hướng**, không phải khẳng định mọi tổ hợp minor/patch đều hợp lệ. Spring Kafka công bố compatibility matrix và Spring Boot quản lý dependency BOM; **ưu tiên dependency do BOM của dòng Boot đang dùng chọn**, chỉ override khi có lý do và đã test lại.

Để không gặp lỗi “build compile nhưng runtime dùng Kafka client khác”, có thể xem dependency tree tại bước kiểm thử của nhóm phát triển bằng các lệnh tương đương `gradle dependencies` / `dependencyInsight` hoặc Maven `dependency:tree`. **Bài này trình bày các lệnh tham khảo**, không yêu cầu chạy build/Gradle để thay đổi dự án tại đây.

### Broker từ 2.5 trở lên là điều kiện tối thiểu, không phải đích production

Điều kiện `broker >= 2.5` nói rằng giao thức EOS V2 có mặt. Điều đó **không** có nghĩa nên duy trì một broker 2.5 hết vòng hỗ trợ trong production. Các dòng Spring Kafka mới còn có client/protocol/features mới; cần xác minh compatibility, bảo mật và support policy theo bản hiện đang sử dụng.

Nếu đang nâng cấp Kafka broker lên **4.x**, cần lưu ý hướng chuyển sang **KRaft**, loại bỏ các thành phần ZooKeeper-based từ Kafka 4.0. Đây là **một trục migration hạ tầng khác** với EOSMode: ứng dụng EOS V2 có thể không cần thay code vì KRaft, nhưng vẫn phải test chính xác client/broker, ACL, transaction coordinator, rebalances và upgrade path của cluster.

## 5. Bảng quyết định nhanh khi nâng cấp

| Trạng thái hiện tại | Có thể chuyển thẳng Spring Kafka 3.x? | Quyết định |
| --- | --- | --- |
| 2.8/2.9, broker **>=2.5**, đang dùng V2 | **Có thể**, nếu Boot/Java/client tương thích | Bỏ cấu hình legacy, chuyển sang transaction prefix theo instance, test EOS |
| 2.8/2.9, broker **>=2.5**, đang ép V1 | **Có thể sau khi chuyển mode** | Test V2 trước trên nhánh hiện tại hoặc staging, rồi mới nâng framework |
| 2.8/2.9, broker **<2.5**, đang dùng V1 | **Không**, nếu còn cần transaction EOS | Nâng Kafka broker trước hoặc tiếp tục nhánh hỗ trợ V1 tạm thời |
| 2.7, dùng tên `ALPHA`/`BETA` | Phải review config và đường nâng cấp | Chuẩn hóa hiểu biết về V1/V2, nâng broker/client theo từng chặng |
| Spring Kafka 3.x đang chạy EOS V2 | Chuyển 4.x cần kiểm tra thêm Spring Boot/Framework/client | Không chỉ xét EOS; test build, listener/transaction API và Kafka broker |
| Multi-pod có cùng `transaction-id-prefix` | Rủi ro kể cả broker đã hỗ trợ V2 | Đặt prefix riêng cho instance đang chạy đồng thời |

Nếu một hệ thống chỉ **consume** mà không produce output trong Kafka transaction, không nên tự tuyên bố đã bật “Kafka exactly-once” chỉ vì thêm `transaction-id-prefix`. EOS read–process–write cần **container transaction** và việc output/offset thực sự tham gia cùng giao dịch.

## 6. Migration từ code legacy V1 sang V2

Trong ứng dụng Spring Kafka **2.8/2.9**, có thể gặp cấu hình legacy như sau:

```java
// Legacy illustration: dùng với Spring Kafka 2.8/2.9,
// KHÔNG sao chép vào Spring Kafka 3.x.
import org.springframework.kafka.listener.ContainerProperties;

// Kafka listener container factory được ứng dụng tự cấu hình.
factory.getContainerProperties()
        .setEosMode(ContainerProperties.EOSMode.V1);

// V1 thường dùng producer theo group/topic/partition.
producerFactory.setProducerPerConsumerPartition(true);

// Batch listener ở V1 có thể được cấu hình:
factory.getContainerProperties()
        .setSubBatchPerPartition(true);
```

Mã trên là **trích đoạn cấu hình legacy**, giả định project đã khai báo `factory` và `producerFactory` đúng kiểu. Các lựa chọn V1 gắn với việc fence theo transactional ID của partition; chúng không nên được mang nguyên sang Spring Kafka 3.x.

Khi chuyển sang **Spring Kafka 3.x**:

- **Bỏ `setEosMode(V1)` / `ALPHA`**. V1 không còn được hỗ trợ.
- Không cần ép `setEosMode(V2)` trong cấu hình thông thường; **V2 là mode duy nhất** ở nhánh 3.x.
- Rà soát `producerPerConsumerPartition`, một tùy chọn legacy không cần thiết cho V2, và tránh phụ thuộc vào cách tạo transactional ID theo partition của V1.
- Rà soát `subBatchPerPartition` nếu từng bật riêng để phục vụ V1. V2 không cần cấu hình đó để đảm bảo fencing; chỉ giữ nếu có lý do rõ và API/version hỗ trợ.
- **Cấp `transactionIdPrefix` duy nhất cho từng application instance đang chạy đồng thời**, không dùng chung một prefix trên toàn bộ replica.
- Xác minh `KafkaTemplate` và transaction manager dùng **cùng ProducerFactory** hỗ trợ transactions.
- Xác minh listener container thực sự mở transaction và gửi offsets bằng metadata consumer group.

### V2 không cần một “feature flag” Kafka riêng

Trong Spring Kafka 3.x, nhiều project có thể thấy các snippet như:

```java
factory.getContainerProperties()
        .setEosMode(ContainerProperties.EOSMode.V2);
```

Nếu API vẫn có ở version đang dùng, gọi V2 là hợp lệ về ý nghĩa nhưng **không cần thiết** để bật transaction. Việc **bật transaction** nằm ở producer factory có transactional ID prefix và listener container được gắn Kafka transaction manager. Một ứng dụng chỉ đặt enum V2 nhưng container không có transaction manager thì không được tự động hưởng EOS.

Đừng tạo một property tự đặt như `spring.kafka.eos-mode: V2` rồi nghĩ Spring Boot sẽ luôn hiểu. Trong Spring Boot 3.x, cấu hình chuẩn thường là `spring.kafka.producer.transaction-id-prefix`; EOS mode là logic của framework, không phải một property phổ quát cần người dùng khai báo.

## 7. Cấu hình Spring Boot 3.x điển hình cho V2

Ví dụ YAML dành cho ứng dụng Spring Kafka **3.x** sử dụng auto-configuration do Spring Boot quản lý:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      transaction-id-prefix: "orders-tx-${HOSTNAME:local}-"

    consumer:
      group-id: orders-processing
      enable-auto-commit: false
      auto-offset-reset: earliest
      isolation-level: read_committed
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer

app:
  kafka:
    input-topic: orders.in
    output-topic: orders.out
```

Ở Spring Boot 3.x, khi `spring.kafka.producer.transaction-id-prefix` được cấu hình và ứng dụng dùng Kafka auto-configuration thông thường, Boot tạo `KafkaTransactionManager` và cấu hình listener container để sử dụng nó. **Nếu project tự khai báo `ConcurrentKafkaListenerContainerFactory` hoặc transaction manager**, phải xác minh factory riêng đã được nối đúng với manager và producer factory, không giả định auto-configuration sẽ tự sửa mọi bean tùy chỉnh.

Các thuộc tính quan trọng:

| Thuộc tính | Vai trò |
| --- | --- |
| `transaction-id-prefix` | Cho phép Kafka producer transaction; Spring cấp các suffix cho producer thực tế |
| `enable-auto-commit=false` | Không cho consumer tự commit offset ngoài transaction |
| `isolation-level=read_committed` | Consumer này không nhìn thấy output Kafka đã abort ở upstream |
| `group-id` | Danh tính consumer group mà offsets được commit |
| `auto-offset-reset=earliest` | Chỉ áp dụng khi group chưa có committed offset hợp lệ; không quyết định replay sau rollback |
| Serializer/deserializer | Bảo đảm record được gửi/đọc đúng định dạng |
| Instance-specific prefix | Tránh transaction ID xung đột giữa các replica |

`HOSTNAME` trong YAML chỉ là **ví dụ nguồn định danh**. Nếu hạ tầng cung cấp hostname không duy nhất hoặc được tái sử dụng đồng thời, cần dùng một ID instance/pod phù hợp hơn. Với Kubernetes, có thể inject `POD_NAME` hoặc `POD_UID` từ Downward API theo chính sách triển khai. Quan trọng là **không có hai instance đang hoạt động dùng cùng tập transactional IDs**.

### Chú ý về thứ tự cấu hình auto-commit

Trong các phiên bản Spring Kafka hiện đại, container thường điều chỉnh consumer auto-commit nếu không được ứng dụng đặt tường minh. Với luồng transactional, vẫn nên **kiểm tra runtime** rằng `enable.auto.commit=false`, không dựa vào một giả định nếu bean/custom properties đã ghi đè cấu hình.

### Cấu hình producer bên ngoài listener

Khi producer không được gọi từ listener mà do API/scheduler khởi phát, có thể sử dụng `KafkaTemplate.executeInTransaction(...)` hoặc transaction manager trong phạm vi phù hợp. Đó là **producer-initiated transaction**. Với listener container transactional, không tự bọc mọi `KafkaTemplate.send` bằng `executeInTransaction` nếu mục tiêu là tham gia **chính transaction của container**; tạo giao dịch độc lập có thể phá tính nguyên tử với consumed offsets.

## 8. Ví dụ listener đúng phạm vi Kafka transaction

Ví dụ xử lý input và gửi output:

```java
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderProjectionListener {

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final String outputTopic;

    public OrderProjectionListener(
            KafkaTemplate<String, String> kafkaTemplate,
            @Value("${app.kafka.output-topic}") String outputTopic) {
        this.kafkaTemplate = kafkaTemplate;
        this.outputTopic = outputTopic;
    }

    @KafkaListener(topics = "${app.kafka.input-topic}")
    public void handle(ConsumerRecord<String, String> input)
            throws Exception {

        String result = "validated:" + input.value();

        // Gửi output trong transaction của listener container.
        kafkaTemplate.send(outputTopic, input.key(), result)
                .get(10, TimeUnit.SECONDS);
    }
}
```

Ví dụ `get(...)` chờ broker xác nhận send, giúp trình bày điểm lỗi rõ ràng; throughput thực tế có thể dùng cách gửi bất đồng bộ khác nhưng phải giữ semantics transaction. Mấu chốt:

- Container bắt đầu transaction **trước khi gọi listener**, nếu factory được cấu hình transaction.
- `KafkaTemplate` tham gia transaction vì dùng đúng producer factory/transaction context.
- Listener trả về thành công: container gửi offsets vào transaction rồi commit.
- Listener ném exception: transaction rollback, offsets không commit trong giao dịch đó, input có thể được giao lại.

**Không commit consumer offset thủ công** bằng `consumer.commitSync()` trong listener transactional. Việc đó tạo đường commit offset độc lập và có thể phá ranh giới commit cùng output.

**Không nuốt exception** rồi trả về bình thường khi nghiệp vụ chưa hoàn tất. Container có thể coi record được xử lý thành công và commit offset/output không đúng kỳ vọng.

## 9. Producer identity trong V2: prefix và suffix

V2 không dùng producer-per-partition để fence theo cách V1, nhưng **`transactional.id` vẫn là danh tính quan trọng** của Kafka transactional producer.

```text
Application pod A:
  transactionIdPrefix = orders-tx-podA-
  ProducerFactory cấp:
    orders-tx-podA-0
    orders-tx-podA-1
    ...

Application pod B:
  transactionIdPrefix = orders-tx-podB-
  ProducerFactory cấp:
    orders-tx-podB-0
    orders-tx-podB-1
    ...
```

Nếu A và B cùng dùng prefix `orders-tx-`, các producer có thể sinh trùng full `transactional.id`. Broker có quyền **fence producer cũ** khi producer mới cùng ID khởi tạo, dẫn đến lỗi `ProducerFencedException`/`InvalidProducerEpochException` hoặc transaction bị hủy ngoài dự kiến.

| Quy tắc | Vì sao |
| --- | --- |
| Prefix khác nhau giữa **các instance đồng thời** | Tránh cùng transactional producer identity |
| Suffix do producer factory quản lý | Tái sử dụng/cấp mới producer phù hợp concurrency |
| Không lấy `group.id/topic/partition` làm ID theo công thức V1 cũ | V2 dùng consumer group metadata cho fencing ownership |
| Theo dõi `ProducerFencedException` | Có thể do ID trùng hoặc producer idle bị broker hết hạn |
| Cấu hình producer cache phù hợp | Tránh thiếu producer khi có nhiều transaction đồng thời |
| Không ghi transaction ID có dữ liệu nhạy cảm | Giữ log vận hành an toàn |

Đối với rolling deployment, phải tính cả **các pod cũ chưa tắt** và **pod mới vừa start**. Prefix “unique theo replica index” có thể bị trùng nếu process cũ chưa dừng nhưng instance mới với cùng index đã lên; cần điều phối lifecycle/fencing hợp lý.

### `maxAge` và `transactional.id.expiration.ms`

Broker có cơ chế hết hạn transactional IDs không được sử dụng trong thời gian dài. Khi cached producer ở ứng dụng **idle quá lâu**, broker có thể hết hạn ID của nó và lần dùng lại phát sinh `ProducerFencedException`, kể cả không có consumer rebalance.

Spring Kafka hỗ trợ `DefaultKafkaProducerFactory.maxAge` để làm mới producer trong cache **trước** khoảng hết hạn do broker quy định:

```java
// Trích đoạn cấu hình trong Spring Kafka 3.x.
// producerFactory là bean DefaultKafkaProducerFactory đã tạo.
producerFactory.setMaxAge(Duration.ofHours(12));
```

Đây là **giá trị minh họa**, không phải ngưỡng mặc định phù hợp cho mọi cluster. Chọn `maxAge` nhỏ hơn `transactional.id.expiration.ms` của broker, có xét margin vận hành. Không nhầm `maxAge` (tuổi producer trong cache) với `transaction.timeout.ms` (giới hạn thời gian của một Kafka transaction).

Nếu flow ít traffic, cần test gửi giao dịch sau nhiều giờ idle để phát hiện lỗi này, thay vì chỉ test lúc deploy hệ thống đang hoạt động liên tục.

## 10. Thay đổi trong Spring Kafka 3.2: `TransactionIdSuffixStrategy`

Từ **Spring Kafka 3.2**, framework có `TransactionIdSuffixStrategy` để quản lý hậu tố của `transactional.id`. Với `DefaultTransactionIdSuffixStrategy`:

- Khi `maxCache > 0`, một tập suffix cố định có thể được cấp/phân phối lại.
- Khi `maxCache = 0`, suffix có thể được tạo tăng dần, phù hợp với chiến lược của version.
- Nếu giới hạn cache đã được dùng hết và không còn transactional producer trống, có thể nhận `NoProducerAvailableException`.
- Ứng dụng có thể dùng retry với backoff phù hợp cho lỗi thiếu producer tạm thời, nhưng **không nên retry vô hạn** nếu concurrency thực sự vượt sizing.

Ví dụ khái niệm về quan hệ số lượng:

```text
Listener concurrency = 6
Nested transactional producer activity = 2 (có thể)

Required transactional producer capacity
  phụ thuộc số transaction đồng thời tối đa
  và cấu hình factory/containers thực tế.

Nếu maxCache nhỏ hơn nhu cầu thực tế:
  -> NoProducerAvailableException
  -> cần sizing hoặc thay đổi concurrency
```

Không có công thức “`maxCache=concurrency` luôn đúng” cho mọi ứng dụng, vì nested transactions, nhiều listener container và các producer-initiated transactions có thể cần thêm transactional producers.

**Khi nâng từ 3.1 lên 3.2/3.3**, hãy rà soát cấu hình producer cache, load test concurrency và thống kê lỗi `NoProducerAvailableException`, ngoài việc kiểm tra mode V2 vốn không đổi.

## 11. Những thay đổi không phải EOSMode nhưng ảnh hưởng upgrade

Một dự án nâng từ Spring Kafka 2.x lên 3.x/4.x có thể vấp nhiều thay đổi cùng lúc:

| Vùng | Rủi ro nâng cấp | Hướng kiểm tra |
| --- | --- | --- |
| Java/Spring Framework baseline | Class hoặc API không còn tương thích | Dùng Java và Spring Framework đúng dòng Boot/Kafka |
| `kafka-clients` | Thay protocol, default, version serialization | Kiểm tra dependency tree/BOM, client-broker matrix |
| Listener/container error handling | Các handler cũ được thay bằng API chung mới | Rà soát `CommonErrorHandler`, rollback/retry/DLT |
| Transaction ID prefix | Logic V1 theo partition không còn cần | Unique per instance, không tái sử dụng sai |
| Producer cache | Suffix/caching/concurrency thay đổi | Load test, theo dõi `NoProducerAvailableException` |
| Transaction timeouts | Broker/client timeout không thống nhất | Test transaction dài, record xử lý chậm |
| Batch listeners | Phạm vi transaction, error handling theo batch | Test partial batch failure và replay |
| Kafka 4.x cluster | KRaft và client/broker feature compatibility | Tách migration broker khỏi code upgrade nếu có thể |
| Embedded Kafka tests | Một số API ZooKeeper-based bị loại ở Spring Kafka 4.x | Chuyển sang KRaft-based embedded broker/test harness |
| Observability | Metric/log/tracing có thể thay đổi tên hoặc tags | Giữ alert logic dựa trên outcome, test dashboard |

**Spring Kafka 4.0** nâng cấp mạnh về client/test hạ tầng; ví dụ `EmbeddedKafkaZKBroker` không còn là hướng test phù hợp khi Kafka 4 chuyển hoàn toàn sang KRaft. Đây là vấn đề cần dự liệu nếu một bộ integration tests EOS từng phụ thuộc ZooKeeper-based EmbeddedKafka. Không đồng nhất việc sửa test broker với việc “bật EOSMode.V2”.

## 12. Thứ tự nâng cấp khi đang dùng V1 và broker cũ

Giả sử production hiện có:

```text
Spring Boot 2.x
Spring Kafka 2.8
kafka-clients 3.x
Kafka broker 2.4
EOSMode.V1
Producer-per-consumer-partition = true
```

Không thể chỉ tăng `spring-kafka` lên 3.x rồi mong giao dịch vẫn chạy: **Spring Kafka 3.x không còn hỗ trợ V1**, còn Kafka 2.4 chưa đáp ứng điều kiện broker cho V2.

Một trình tự triển khai an toàn hơn:

1. **Inventory cấu hình hiện tại:** dependency versions, broker versions, `EOSMode`, container factories, producer factory, transactional ID prefix, consumer groups, DLT/retry policy.
2. **Chốt baseline:** ghi lại tỷ lệ commit/abort, consumer lag, output số lượng, transaction duration, lỗi producer fencing, end-to-end business metrics.
3. **Nâng broker trước:** đưa cluster lên một phiên bản được hỗ trợ có giao thức EOS V2 (tối thiểu 2.5, thực tế nên chọn một dòng mới còn support); áp dụng rolling/broker upgrade theo hướng dẫn Kafka.
4. **Giữ application version ổn định trong lúc nâng broker** nếu compatibility cho phép; test transaction xuyên cluster khi broker đang rolling upgrade và sau khi hoàn tất.
5. **Chuyển legacy application từ V1 sang V2** khi các broker cần thiết đã hỗ trợ; bỏ phụ thuộc vào `producerPerConsumerPartition` khi thích hợp và kiểm tra transaction ID prefix.
6. **Chạy integration tests EOS V2:** happy path, fail after output send, rollback/replay, offset commit, fencing/rebalance, DLT.
7. **Nâng Spring Boot/Java/Spring Kafka theo phiên bản tương thích**. Không override từng thư viện ngẫu nhiên để ép một tổ hợp chưa được hỗ trợ.
8. **Canary/rolling application deployment:** quan sát producer identities, group rebalances, transaction abort rate, output/offset correctness.
9. **Hoàn thiện cleanup legacy config:** bỏ `V1`/`ALPHA`, batch partition behaviors chỉ dùng để hỗ trợ V1, và code tạo transactional ID theo partition nếu không còn phù hợp.
10. **Ghi runbook rollback:** nếu ứng dụng mới lỗi, xác định rollback tới version nào còn tương thích broker mới, và lưu ý cách transaction IDs/consumer group được giữ nguyên.

Không nhất thiết phải tách đúng từng đợt release như trên ở mọi tổ chức, nhưng **không nên nâng broker, client, framework và retry policy đồng thời** nếu không có test/migration plan đủ mạnh; khi lỗi, rất khó xác định nguồn thay đổi.

## 13. Rolling upgrade và ranh giới giữa phiên bản cũ/mới

Khi canary một consumer group, có thể có lúc:

```text
Consumer group: orders-processing
   |
   +-- Pod A: Spring Kafka 2.9 / V2
   +-- Pod B: Spring Kafka 3.3 / V2
   +-- Pod C: Spring Kafka 3.3 / V2
```

Điều này **không tự động bảo đảm tương thích production** chỉ vì tất cả đều nói V2. Cần test:

- Các version client cùng có thể làm thành viên group theo protocol/assignor đã cấu hình.
- Rebalance không cho phép instance cũ commit offsets với membership stale.
- Transactional ID prefix không trùng giữa pod cũ và mới đang sống cùng lúc.
- Serializer/schema của output tương thích với downstream trong suốt rolling deployment.
- Retry/DLT không tạo thêm output có định dạng khác giữa hai version.
- Khi tăng concurrency, producer cache và group assignment ổn định.

**Không chuyển một phần pod sang V2 trong khi broker thực tế cần phục vụ commit vẫn không hỗ trợ V2.** Với cluster đang rolling upgrade version broker, phải theo quy trình Kafka dành cho feature/protocol upgrade, không mặc định rằng kết nối tới một bootstrap broker mới là đủ.

### Khi cần rollback ứng dụng

Một rollback đúng nghĩa cần trả lời:

1. Version cũ có còn tương thích với Kafka broker/client/protocol mới không?
2. Cấu hình `transactional.id` cũ sẽ tạo identity nào? Có collide với pod mới chưa dừng hết không?
3. Input group offsets đã tiến đến đâu trong các transaction mới?
4. Schema output mới có khiến consumer cũ đọc lỗi không?
5. Có side effect ngoài Kafka đã thực hiện không? Có cần đối soát/idempotency không?

Không “lùi consumer offset” một cách tùy tiện để chữa lỗi deploy: đó là **replay nghiệp vụ**, có thể tái tạo output/side effect dù transaction trước đã commit. Việc reset offset cần thủ tục riêng, xác nhận consumer group không đang hoạt động và dữ liệu có thể phát lại.

## 14. Test tương thích bằng Kafka broker thật

Một unit test mock `KafkaTemplate` không xác nhận V2. Các assertion như “`send()` được gọi đúng một lần” bỏ qua broker fencing, Kafka transaction outcome và consumed offset commit.

Một integration test EOS cần:

```text
Producer test gửi INPUT topic offset N
           |
           v
Spring Kafka transactional listener
           |
       send OUTPUT
           |
       cố ý throw trước commit
           |
         ABORT
           |
     input được replay
           |
       send OUTPUT
           |
         COMMIT
           |
           +--> read_committed OUTPUT có đúng một result
           |
           +--> group committed offset == N + 1
```

Test nên chạy trên Kafka broker với protocol phù hợp dòng framework đang kiểm tra, ví dụ `@EmbeddedKafka` hoặc Testcontainers.

### Cấu hình `@EmbeddedKafka` minh họa

Đối với Spring Kafka 3.x trong test với một broker:

```java
import org.springframework.kafka.test.context.EmbeddedKafka;

@EmbeddedKafka(
        partitions = 1,
        topics = {"eos-upgrade.input", "eos-upgrade.output"},
        brokerProperties = {
            "transaction.state.log.replication.factor=1",
            "transaction.state.log.min.isr=1",
            "offsets.topic.replication.factor=1"
        },
        bootstrapServersProperty =
                "spring.kafka.bootstrap-servers")
class EosUpgradeIT {
    // @SpringBootTest và các test được định nghĩa tiếp bên dưới.
}
```

Các replication settings `=1` **chỉ để broker test một node** thực hiện được transaction. Production phải cấu hình replication/ISR phù hợp HA và chính sách durability; không mang `replication.factor=1` vào cluster thật.

### Listener cố ý lỗi lần đầu

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class FailingOnceProjection {

    private final KafkaTemplate<String, String> template;
    private final AtomicBoolean failFirst = new AtomicBoolean(true);
    private final AtomicInteger attemptCount = new AtomicInteger();

    public FailingOnceProjection(
            KafkaTemplate<String, String> template) {
        this.template = template;
    }

    @KafkaListener(
            topics = "eos-upgrade.input",
            groupId = "eos-upgrade-group")
    public void handle(ConsumerRecord<String, String> record)
            throws Exception {

        attemptCount.incrementAndGet();

        template.send(
                "eos-upgrade.output",
                record.key(),
                "processed:" + record.value())
                .get(10, TimeUnit.SECONDS);

        if (failFirst.compareAndSet(true, false)) {
            throw new IllegalStateException(
                    "Fault injected after broker ACK but before commit");
        }
    }

    public int attempts() {
        return attemptCount.get();
    }
}
```

Ứng dụng test phải bật `transaction-id-prefix` và listener container transaction manager thật. `get(...)` bảo đảm vị trí fault injection nằm **sau khi broker xác nhận send**, không phải ngay sau khi enqueue future. Lỗi ném ra ngoài listener phải khiến transaction **abort**, sau đó after-rollback processing cho phép retry input.

### Assertion cần có

Trong một test có **topic/group mới, input đầu tiên offset 0 trên partition 0**, có thể kiểm tra:

```java
// Pseudocode của integration test có consumer/producer test thực.
// Observer phải cấu hình isolation.level=read_committed.

assertTrue(failingOnceProjection.attempts() >= 2);

ConsumerRecord<String, String> result =
        KafkaTestUtils.getSingleRecord(
                readCommittedConsumer,
                "eos-upgrade.output",
                Duration.ofSeconds(30));

assertEquals("processed:paid", result.value());

// Poll thêm để phát hiện duplicate committed records.
assertEquals(0,
        readCommittedConsumer.poll(Duration.ofSeconds(2)).count());

// Committed offset của chính group xử lý input:
TopicPartition tp =
        new TopicPartition("eos-upgrade.input", 0);
var committed = groupInspector.committed(
        Set.of(tp), Duration.ofSeconds(10));

assertNotNull(committed.get(tp));
assertEquals(1L, committed.get(tp).offset());
```

Đây là **pseudocode trích phần assertions**: `readCommittedConsumer`, `groupInspector` và producer gửi input phải được tạo bằng test fixture riêng. Test dùng `Duration`, `Set`, `TopicPartition`, `KafkaTestUtils` và JUnit assertions tương ứng.

Trong test thực, phải đợi đúng điều kiện commit/offset, dùng topic/group/transaction prefix riêng cho từng scenario. Với topic đã có dữ liệu, **không hardcode offset=1**: lấy metadata offset của input thực tế rồi assert `committed == input.offset() + 1`. Đừng chỉ dùng `Thread.sleep` để đoán khi nào rollback/commit hoàn tất.

## 15. Test bổ sung phải chạy trước cutover

| Scenario | Vì sao quan trọng | Điều cần xác nhận |
| --- | --- | --- |
| Happy path | Luồng giao dịch cơ bản | Output và consumed offset commit cùng nhau |
| Lỗi trước output send | Không có output đã gửi | Input replay; offset không bị commit sai |
| **Lỗi sau output ACK, trước commit** | Cửa sổ rủi ro duplicate lớn nhất | Aborted output không lộ với `read_committed`; chỉ một output committed sau retry |
| Process crash giữa transaction | Kafka transaction mở có thể cần timeout/fencing | Sau restart vẫn có kết quả đúng, không mất/nhân đôi committed output |
| Consumer rebalance | Stale group member có thể cố commit | V2 fencing không cho commit offsets của member không hợp lệ |
| Transactional ID collision | Rolling deploy có thể tạo producer trùng identity | Không có `ProducerFencedException` ngoài thiết kế |
| Long-idle producer | Broker hết hạn ID trong producer cache | `maxAge`/cache phù hợp và gửi lại sau idle hoạt động |
| High concurrency | Hết producer suffix/cache | Không có `NoProducerAvailableException` bất thường |
| Batch listener partial failure | Một poll chứa nhiều records | Transaction/offsets rollback theo phạm vi batch đã cấu hình |
| Poison pill và DLT | Retry có thể làm record đứng vĩnh viễn | DLT/recovered offset đúng policy, không nuốt lỗi |
| Consumer downstream `read_committed` | Không hiển thị aborted data | Downstream không nhận output của transaction abort |
| Kafka + DB side effect | Kafka EOS không bao gồm DB | Domain effect idempotent, không tạo duplicate khi replay |
| Mixed old/new version | Rolling migration | Rebalance, group join, serializer và transaction outcomes đúng |
| Shutdown/restart | Quá trình kết thúc và producer cleanup | Không để instance cũ xử lý tiếp sau khi mất ownership |

**Đừng dùng `attemptCount == 1` làm assertion cho exactly-once.** Phần read/process có thể được thực thi nhiều lần; kết quả Kafka output/offset mới là đối tượng được kiểm tra.

### Lưu ý khi test Spring Kafka 4.x

Với Spring Kafka 4.x, Kafka test infrastructure đã chuyển hoàn toàn sang **KRaft-based Embedded Kafka**, các API test ZooKeeper-based cũ không còn phù hợp. Nếu một test EOS thất bại ngay lúc khởi tạo broker sau nâng 4.x, cần phân biệt **test harness migration** với lỗi EOS V2 của ứng dụng. Hãy dùng `spring-kafka-test` cùng dòng framework và broker/container phiên bản tương thích.

## 16. Error handling, retry và DLT khi đổi framework

Tính đúng đắn của EOS phụ thuộc vào exception handling, không chỉ transaction manager.

Ví dụ một listener bắt exception nhưng trả về bình thường:

```java
@KafkaListener(topics = "orders.in")
void consume(String payload) {
    try {
        process(payload);
    } catch (Exception e) {
        log.error("Could not process", e);
        // NGUY HIỂM: return như thể xử lý thành công.
    }
}
```

Nếu `process` không tạo output hợp lệ nhưng method return bình thường, container có thể coi giao dịch thành công và commit consumed offset. Điều đó **không phải lỗi V2**; đó là failure policy sai.

Trong listener transactional:

- Lỗi cần rollback phải được **đưa tới container** theo chính sách đã cấu hình.
- Retry/after-rollback processing quyết định cách giao lại record.
- `DefaultAfterRollbackProcessor` và recoverer có thể xử lý record lỗi sau số lần thử.
- Với Dead Letter Topic, cần test rằng **DLT publish** và **commit recovered offset** có quan hệ transaction/chính sách đúng, không để record biến mất khi DLT send lỗi.
- `CommonErrorHandler` và các cấu hình retry non-blocking cần được xem xét riêng theo version; không mặc định mọi retry topic đều có cùng transaction boundary với listener gốc.

Nếu trước đây V1 có thể chia batch transaction theo partition bằng `subBatchPerPartition`, khi lên V2 và đổi cấu hình batch listener, phạm vi failure/replay của một poll có thể khác. Đó là lý do nên test **partial batch failure**, không chỉ record listener một record.

## 17. V2 không làm DB transaction trở thành Kafka transaction

Một luồng thường gặp:

```text
Kafka input
   |
   v
@KafkaListener transactional
   |
   +--> UPDATE accounts SET balance = balance - 100
   |          (DB transaction có thể commit riêng)
   |
   +--> KafkaTemplate.send("payments.out", ...)
   |
   X Kafka transaction ABORT
   |
   v
Kafka input được giao lại
   |
   v
DB UPDATE có nguy cơ chạy lại
```

Kafka EOS V2 chỉ bảo đảm tính nguyên tử của các tác động **nằm trong cùng Kafka transaction**. Nếu DB commit trước nhưng Kafka transaction abort, Kafka không tự rollback DB. `@Transactional` với một transaction manager và synchronization phức tạp cũng không mặc nhiên tạo một giao dịch ACID phân tán bao phủ cả DB và Kafka.

Các phương án cho end-to-end reliability:

| Thiết kế | Bảo vệ |
| --- | --- |
| **Inbox table / dedup** theo `eventId` với unique key | Khi input replay, DB biết nghiệp vụ đã xử lý |
| **Transactional outbox** | Domain update + outbox row nằm trong **cùng DB transaction** |
| **Idempotent API** ở hệ thống đích | Retry cùng key không nhân đôi side effect |
| **Reconciliation** | Phát hiện mất/nhân đôi/sai trạng thái giữa các hệ thống |
| **Saga/compensation** | Bù trừ những bước nghiệp vụ đã hoàn tất từng phần |

Bên cạnh test output Kafka, phải test **DB row count hoặc business effect** nếu hệ thống thực hiện tác động ngoài Kafka. Một Kafka transaction commit duy nhất không tự chứng minh “tiền chỉ bị trừ một lần”.

## 18. Vấn đề producer fencing: khi nào là tín hiệu tốt, khi nào là cấu hình sai?

`ProducerFencedException` không phải lúc nào cũng có cùng nguyên nhân:

| Tình huống | Giải thích | Hướng xử lý |
| --- | --- | --- |
| Pod mới và pod cũ dùng chung `transactional.id` | Producer mới làm producer cũ bị fence | Đặt prefix riêng cho các instance đồng thời, kiểm tra rollout |
| Producer cached idle quá lâu | Broker hết hạn transactional identity | Xem `maxAge` và `transactional.id.expiration.ms` |
| Rebalance làm consumer mất partition | Member cũ có thể không được commit offsets hợp lệ | Quan sát group membership, xử lý/retry theo lifecycle |
| Client/broker lệch phiên bản | Transaction protocol/API không tương thích | Kiểm tra client-broker compatibility và minimum broker |
| Transaction timeout | Giao dịch kéo dài quá giới hạn | Chia nhỏ processing, đo thời lượng, sửa blocking calls |
| Producer factory bị share không đúng | Template/container dùng identity/context khác mong muốn | Xác nhận producer factory và manager đúng bean |
| Rolling upgrade tăng producer concurrency | Hết cache/suffix, transaction bị tranh chấp | Sizing producer cache và load test |

V2 dùng group metadata để fence zombie khi gửi offsets vào transaction, **không loại bỏ `transactional.id`**. Việc đặt prefix duy nhất là yêu cầu vận hành bắt buộc khi có nhiều instance.

Không nên **catch `ProducerFencedException` rồi cố dùng lại cùng producer** như thể đây là một lỗi gửi record thông thường. Producer đã bị fence là trạng thái transaction không thể tiếp tục an toàn; framework và lifecycle của producer/container phải xử lý/recreate theo hướng dẫn version đang chạy.

## 19. Monitoring trước và sau migration

Các chỉ số nên giữ như một baseline để so sánh:

| Nhóm | Chỉ số hoặc log cần có | Dấu hiệu cảnh báo |
| --- | --- | --- |
| Kafka transactions | Commit rate, abort rate, transaction duration, timeout | Tăng abort/timeout sau nâng |
| Producers | `ProducerFencedException`, `NoProducerAvailableException`, cache pressure | Prefix collision hoặc thiếu producer |
| Consumers | Rebalance count, partition assignments, group offsets, lag | Rebalance liên tục, offset không tiến |
| Output | Committed output count theo business/event key | Duplicate hoặc mất dữ liệu thực sự |
| Error handling | Retry attempts, DLT records, recovered offsets | Poison pill không được xử lý đúng |
| Client/broker | Version, coordinator errors, unsupported protocol | Broker/client chưa tương thích |
| Deployment | Instance ID, transaction prefix, app version | Hai pod đồng thời dùng chung prefix |
| External effects | Unique business effects trong DB/API | Idempotency không còn bảo đảm |

Dùng **Kafka consumer `read_committed`** khi đo committed business output. Consumer `read_uncommitted` có thể nhìn thấy dữ liệu thuộc aborted transaction; đếm nó như output hợp lệ sẽ làm dashboard báo duplicate sai. Ngược lại, log gửi thành công của `KafkaTemplate.send` chưa chứng minh transaction đã commit.

`consumer lag` có thể khác giữa các công cụ khi có transaction đang mở và last stable offset. Khi điều tra V2, kết hợp **group committed offsets, transaction outcome và downstream visibility**, không chỉ một số lag.

### Structured log gợi ý

```json
{
  "eventType": "kafka.transaction.result",
  "service": "orders-projection",
  "frameworkLine": "spring-kafka-3.x",
  "instanceId": "orders-pod-a",
  "consumerGroupId": "orders-processing",
  "inputTopic": "orders.in",
  "inputPartition": 0,
  "inputOffset": 42,
  "transactionOutcome": "COMMITTED",
  "outputTopic": "orders.out",
  "attempt": 2
}
```

Đây là **schema minh họa của ứng dụng**, không phải các trường Spring Kafka tự động ghi nguyên dạng. Không log toàn bộ payload, token, dữ liệu nhạy cảm hoặc secrets trong Kafka records.

## 20. Runbook khi deployment sau nâng cấp gặp lỗi

### Tình huống A — Giao dịch không thể khởi tạo

**Triệu chứng:** transaction initialization timeout hoặc lỗi broker không hỗ trợ giao thức.

Kiểm tra:
1. Spring Kafka/client version thực sự có trong dependency runtime.
2. Broker/controller/transaction coordinator version và cluster feature level.
3. Với broker dưới 2.5: nhánh Spring Kafka 3.x không có V1 fallback.
4. Producer transaction prefix có được cấu hình trong producer factory mà listener dùng không?
5. Kafka transaction state topic, ISR, ACL, timeout và broker health.

**Hành động:** ưu tiên khôi phục compatibility/hạ tầng; không tắt transaction rồi để consumer tự commit nhằm “chạy cho xong” nếu dữ liệu cần EOS.

### Tình huống B — `ProducerFencedException` tăng sau rolling deploy

Kiểm tra:
1. Transactional ID/prefix của từng pod, including pod cũ đang drain.
2. Instance IDs có thực sự khác nhau trong giai đoạn overlap không?
3. Cached producer có idle vượt broker expiration không?
4. Group rebalances/ownership có thay đổi nhanh không?
5. Có thể có một producer factory dùng chung sai giữa nhiều listener/app instance không?

**Hành động:** sửa prefix/lifecycle, giới hạn rollout và phục hồi giao dịch qua listener container; không nuốt lỗi fencing.

### Tình huống C — Output xuất hiện trùng trong test

Kiểm tra:
1. Consumer observer có `isolation.level=read_committed` không?
2. Record xuất từ cùng input hay input đã có duplicate business event?
3. `KafkaTemplate` gửi output có cùng transaction với listener container không?
4. Có dùng `executeInTransaction` tách riêng transaction trong listener không?
5. Consumed offsets có commit cùng transaction hay ngoài luồng?
6. Có external writer hoặc producer khác tạo cùng output không?

**Hành động:** test lại bằng broker-backed integration test, kiểm tra output + offsets, tách Kafka EOS khỏi business dedup.

### Tình huống D — Consumer group lag tăng nhưng output không xuất hiện

Kiểm tra:
1. Transaction đang mở lâu, last stable offset chưa tiến?
2. `max.poll.interval.ms` có bị vượt do xử lý chậm?
3. Producer timeout/transaction timeout làm abort lặp?
4. Retry/after-rollback đang replay poison pill?
5. Transaction producer cache có thiếu khi concurrency tăng?
6. DLT/recoverer có lỗi và khiến input bị giữ lại?

**Hành động:** xác định record/partition và điểm lỗi; không đơn giản tăng timeout vô hạn hoặc reset offsets.

### Tình huống E — Rollback ứng dụng sau khi đã chuyển V2

Kiểm tra version cũ có còn **tương thích broker** và schema output mới, consumer group offset đã commit đến đâu, liệu việc đổi transaction prefix có tạo collision với pod chưa tắt, và external effects đã ghi gì. Nếu reset offsets để replay, phải có kế hoạch idempotency/đối soát. Không quay về V1 trên framework không còn hỗ trợ nó.

## 21. Checklist chấp nhận trước khi phát hành

Một nhóm triển khai có thể dùng các câu hỏi sau khi review migration:

- [ ] Broker cluster phục vụ transaction đã hỗ trợ protocol EOS V2; với Spring Kafka 3.x minimum broker **2.5**.
- [ ] Java, Spring Boot, Spring Framework, Spring Kafka và `kafka-clients` đúng compatibility matrix/BOM.
- [ ] Không còn code phụ thuộc `EOSMode.V1` / `ALPHA` hoặc prefix theo công thức V1 ngoài chủ đích.
- [ ] Spring Boot `transaction-id-prefix` được inject đúng, mỗi instance đang chạy có prefix riêng.
- [ ] Listener container thực sự có Kafka transaction manager; KafkaTemplate dùng producer factory tương thích.
- [ ] Consumer auto-commit tắt; output consumers cần EOS dùng `read_committed`.
- [ ] Exception làm rollback không bị nuốt; after-rollback/retry/DLT theo policy có test.
- [ ] Có integration test lỗi **sau output ACK, trước commit** với assertions cả output và consumed offset.
- [ ] Có test crash/rebalance/fencing phù hợp với topology thực.
- [ ] Có test producer idle và sizing cache/concurrency nếu ứng dụng có nhiều listener.
- [ ] Có cơ chế idempotency/outbox cho DB/API nếu yêu cầu exactly-once nghiệp vụ ngoài Kafka.
- [ ] Canary có metrics transaction abort/fencing, group lag, committed outputs và DLT.
- [ ] Rollback plan tương thích với broker version, transactional IDs, schema và offset history.
- [ ] Khi nâng Spring Kafka 4.x, hạ tầng Embedded Kafka test được chuyển theo KRaft nếu trước đó dùng ZooKeeper.

Checklist này là **tiêu chí vận hành**, không phải cơ chế kiểm tra tự động của Spring Kafka. Test còn phải điều chỉnh theo loại record/batch listener, số partition, retry policy và cấu trúc nghiệp vụ của hệ thống.

## 22. Những hiểu nhầm thường gặp

| Nhận định sai | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “Muốn EOS trong 3.x phải set `EOSMode.V2` bằng tay” | V2 là mode duy nhất của Spring Kafka 3.x | Bật Kafka transactions đúng producer/container và kiểm chứng |
| “`EOSMode.V2` chạy được với mọi broker” | V2 yêu cầu giao thức từ Kafka broker 2.5 | Nâng broker hoặc ở nhánh legacy hỗ trợ V1 tạm thời |
| “V2 không cần `transactional.id`” | Identity vẫn cần cho Kafka producer transaction | Prefix duy nhất mỗi instance, suffix factory cấp |
| “V2 nghĩa là listener chỉ chạy một lần” | Read/process có thể replay sau rollback | Kiểm tra output committed và offsets |
| “Có `KafkaTemplate` transactional là đủ” | Listener container có thể chưa dùng transaction manager | Xác nhận output và offsets tham gia cùng transaction |
| “`read_uncommitted` đếm thấy hai output là EOS hỏng” | Consumer đó có thể thấy aborted records | Dùng `read_committed` cho committed output |
| “V2 bao phủ cả database transaction” | Kafka transaction không tự bao phủ DB/API | Dùng outbox/inbox/idempotency |
| “Gắn một prefix chung cho mọi pod tiện hơn” | Producer có thể fence nhau | Prefix riêng cho instance đồng thời |
| “Client mới sẽ tự fallback về V1” | Với Kafka client 3.0+ và Spring Kafka 3.x không có đường fallback này | Upgrade broker, chuyển V2 |
| “`producerPerConsumerPartition=true` bắt buộc” | Đó là cách hỗ trợ fencing của V1 | Với V2 không cần producer theo mỗi partition cho fencing |
| “Commit offset thủ công giúp an toàn hơn” | Có thể phá nguyên tử output-offset | Để transactional container gửi offsets vào transaction |
| “Broker lên Kafka 4 là EOS tự đổi V3” | Kafka 4/KRaft là trục nâng hạ tầng riêng | EOS mode Spring Kafka hiện đại vẫn V2 |
| “Unit test mock `send` là đủ” | Không có broker transaction/offset/fencing thật | Test `@EmbeddedKafka` hoặc Testcontainers |
| “Consumer lag bằng 0 chứng minh exactly once” | Lag không xác minh output/offset atomicity | Test commit/abort trực tiếp và business outcome |
| “Rollback app chỉ là đổi image tag” | Có thể khác schema, transactional ID, offsets đã tiến | Cần rollback plan có đối soát và compatibility |

## 23. Tài liệu tham khảo chính thức

Tài liệu phải được đọc theo **dòng phiên bản đang sử dụng**, không chỉ theo trang `/reference` mới nhất:

- [Spring Kafka — Exactly Once Semantics (reference)](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Spring Kafka — Transactions và transactionIdPrefix](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Kafka — Change History, 3.0 removal of EOSMode.V1](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html)
- [Spring Kafka 2.9 — Reference, V1/V2 migration](https://docs.spring.io/spring-kafka/docs/2.9.13/reference/html/)
- [Spring Kafka 2.9 — ContainerProperties EOSMode API](https://docs.spring.io/spring-kafka/docs/2.9.13/api/org/springframework/kafka/listener/ContainerProperties.html)
- [Spring Kafka 3.0 — Exactly Once Semantics và broker minimum](https://docs.spring.io/spring-kafka/docs/3.0.17/reference/html/)
- [Spring Kafka — Testing with Embedded Kafka](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Kafka — After-Rollback Processor và exception handling](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka Project — Compatibility Matrix](https://spring.io/projects/spring-kafka/)
- [Apache Kafka — KIP-447: Producer scalability for exactly once semantics](https://cwiki.apache.org/confluence/display/KAFKA/KIP-447%3A+Producer+scalability+for+exactly+once+semantics)
- [Apache Kafka — Compatibility Matrix](https://kafka.apache.org/40/getting-started/compatibility/)
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)

**Kết luận:** `EOSMode.V2` là cơ chế exactly-once hiện đại của Spring Kafka, sử dụng **consumer group metadata để bảo vệ việc commit offsets trong Kafka transaction**. Nó đã trở thành mặc định từ Spring Kafka 2.6 và là **mode duy nhất được hỗ trợ kể từ 3.0**, với yêu cầu Kafka broker **từ 2.5 trở lên**. Nâng cấp an toàn đòi hỏi loại bỏ cấu hình V1 cũ, kiểm soát `transactional.id` theo từng instance, giữ output và consumed offsets chung transaction, và kiểm chứng rollback/replay bằng broker thật với consumer `read_committed`. Khi mở rộng sang database/API hoặc chuyển lên Kafka/Spring Kafka 4.x, cần bổ sung kiểm thử idempotency và tương thích hạ tầng riêng — **không được hiểu EOS V2 là cam kết “mỗi dòng code nghiệp vụ chỉ chạy đúng một lần”**.
