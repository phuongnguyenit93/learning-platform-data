# Checklist kiểm thử trước triển khai

## 1. Mục tiêu và phạm vi

Checklist này dùng để xác nhận một ứng dụng Spring Kafka đã sẵn sàng triển khai lên môi trường tích hợp, staging hoặc production. Phạm vi bao gồm producer gửi sự kiện bằng `KafkaTemplate`, consumer nhận sự kiện bằng `@KafkaListener`, và các thành phần Kafka liên quan như topic, partition, offset, consumer group, serialization, retry, dead-letter topic (DLT), transaction, xử lý đồng thời và observability.

Một bài test chỉ chứng minh được điều đã kiểm tra. Producer gửi thành công không chứng minh consumer xử lý đúng; consumer nhận được record không chứng minh offset commit đúng; transaction commit không chứng minh database và Kafka cùng atomic. Vì vậy cần kiểm thử theo luồng từ hợp đồng event đến hành vi vận hành khi có lỗi.

## 2. Cách sử dụng checklist

Đánh dấu từng mục sau khi có bằng chứng kiểm thử. Với mục không áp dụng, ghi rõ `N/A` và lý do; không bỏ trống vì chưa kiểm tra. Mỗi mục cần lưu ít nhất một bằng chứng phù hợp như test report, log, metric, cấu hình hiệu lực, kết quả CLI hoặc biên bản xác nhận.

- [ ] **PASS:** đã kiểm thử và có bằng chứng.
- [ ] **FAIL:** đã kiểm thử và chưa đạt; phải có người phụ trách và kế hoạch xử lý.
- [ ] **N/A:** không áp dụng, có lý do được ghi lại.
- [ ] **NOT TESTED:** chưa kiểm tra; không được xem là đạt điều kiện triển khai.

Không đánh dấu PASS chỉ vì cấu hình tồn tại trong YAML. Cần xác minh giá trị thực sự được ứng dụng và Kafka broker sử dụng ở môi trường đích.

## 3. Thông tin cần chuẩn bị trước khi kiểm thử

- [ ] Xác định phiên bản Java, Spring Boot, Spring Kafka và Kafka client đang chạy.
- [ ] Ghi lại địa chỉ bootstrap servers của môi trường kiểm thử.
- [ ] Ghi lại tên topic, partition count, replication factor và các topic retry/DLT.
- [ ] Ghi lại consumer group ID của từng listener.
- [ ] Ghi lại key/value schema, serializer, deserializer và quy tắc versioning event.
- [ ] Ghi lại AckMode, commit strategy, retry policy, DLT policy và transaction mode.
- [ ] Ghi lại concurrency của từng listener, số replica và số partition.
- [ ] Xác định authentication, TLS/SASL, principal và ACL cần có.
- [ ] Xác định SLO/SLA: throughput, p95/p99 processing latency, lag, thời gian phục hồi và tỷ lệ lỗi cho phép.
- [ ] Chuẩn bị test data đại diện: payload bình thường, payload lớn, dữ liệu biên, dữ liệu cũ và dữ liệu không hợp lệ.
- [ ] Xác định người phụ trách ứng dụng, Kafka platform, schema registry, bảo mật và vận hành.

Thông tin phiên bản rất quan trọng vì một số API và hành vi thay đổi giữa các dòng Spring Kafka/Kafka client. Test phải chạy với đúng dependency lock/BOM và cấu hình gần với artifact sẽ triển khai.

## 4. Kiểm tra cấu hình kết nối Kafka

### 4.1. Bootstrap và network

- [ ] Ứng dụng kết nối được tới tất cả bootstrap broker được khai báo.
- [ ] DNS và `advertised.listeners` trả về hostname/port mà pod hoặc VM ứng dụng truy cập được.
- [ ] Network policy, firewall, security group và routing cho phép kết nối hai chiều cần thiết.
- [ ] Ứng dụng xử lý được broker restart, leader movement và reconnect.
- [ ] Không dùng địa chỉ broker cục bộ hoặc hostname chỉ tồn tại trên máy developer trong cấu hình production.
- [ ] Timeout kết nối và request được đặt phù hợp với latency mạng của môi trường.

### 4.2. Authentication, TLS và ACL

- [ ] Producer, consumer và KafkaAdmin dùng đúng principal/service identity.
- [ ] Certificate chain và hostname broker được xác minh thành công khi dùng TLS.
- [ ] Keytab, JAAS, truststore, keystore và credential được lấy từ secret/config provider.
- [ ] Secret không xuất hiện trong Git, image, log, exception, test report hoặc artifact.
- [ ] Producer có quyền cần thiết trên topic đích.
- [ ] Consumer có quyền đọc topic và tham gia đúng consumer group.
- [ ] KafkaAdmin chỉ có quyền quản trị thực sự cần thiết.
- [ ] Nếu dùng transaction, principal có quyền trên transactional ID tương ứng.
- [ ] Kiểm thử một principal không đủ quyền và xác nhận broker từ chối đúng thao tác.
- [ ] Có quy trình rotate credential/certificate và đã kiểm tra reconnect sau rotation.

### 4.3. Cấu hình producer và consumer hiệu lực

- [ ] Xác minh `acks`, `enable.idempotence`, `retries`, `delivery.timeout.ms`, `request.timeout.ms` và `max.in.flight.requests.per.connection` theo yêu cầu độ bền.
- [ ] Nếu dựa vào producer idempotence, xác nhận cấu hình hiệu lực đáp ứng điều kiện Kafka client của phiên bản đang dùng.
- [ ] Xác minh `key.serializer` và `value.serializer` khớp kiểu dữ liệu thực tế.
- [ ] Xác minh `key.deserializer` và `value.deserializer` khớp serializer phía producer.
- [ ] Xác minh `group.id`, `auto.offset.reset`, `enable.auto.commit`, `isolation.level` và `max.poll.records`.
- [ ] Nếu Spring listener container quản lý commit, xác nhận auto commit không vô tình được bật trong Kafka consumer.
- [ ] Xác minh AckMode và listener acknowledgment phù hợp với commit strategy đã chọn.
- [ ] Kiểm tra không có cấu hình test như `localhost`, group ID dùng chung hoặc `auto.offset.reset=earliest` ngoài ý muốn ở production.
- [ ] Lưu lại effective configuration đã loại bỏ secret để phục vụ đối chiếu.

Ví dụ cấu hình producer ưu tiên độ bền có thể bắt đầu từ `acks=all` và idempotence, nhưng giá trị cuối cùng phải phù hợp Kafka version, replication factor, `min.insync.replicas` và yêu cầu latency của hệ thống. Không sao chép nguyên cấu hình mẫu vào production mà không kiểm tra broker.

Khi bật idempotence tường minh, kiểm tra các ràng buộc của Kafka client version đang dùng, đặc biệt `acks=all`, `retries` lớn hơn 0 và `max.in.flight.requests.per.connection` không vượt giới hạn hỗ trợ cho idempotence. Nếu dùng transaction, kiểm tra producer factory đã bật transaction và các producer properties không vô hiệu hóa semantics cần thiết.

## 5. Kiểm tra topic và partition

- [ ] Tất cả topic cần thiết đã tồn tại hoặc quy trình provision topic đã được kiểm chứng.
- [ ] Tên topic khớp chính xác với cấu hình listener và producer.
- [ ] Partition count đủ cho throughput và mức consumer concurrency mong muốn.
- [ ] Replication factor phù hợp với số broker và yêu cầu sẵn sàng.
- [ ] `min.insync.replicas` phù hợp với `acks=all` và chính sách chịu lỗi.
- [ ] Retention time/size đáp ứng thời gian replay, điều tra và khôi phục.
- [ ] `cleanup.policy` (`delete`, `compact` hoặc kết hợp) phù hợp semantics dữ liệu.
- [ ] Nếu dùng compacted topic, kiểm tra key ổn định và tombstone được xử lý đúng.
- [ ] Topic retry/DLT có partition, replication, retention và ACL phù hợp.
- [ ] Không tăng partition tùy tiện nếu ứng dụng phụ thuộc key-to-partition mapping hoặc thứ tự lâu dài.
- [ ] Đã kiểm thử hành vi khi topic được tạo mới, tăng partition hoặc metadata thay đổi.

Lưu ý: Kafka chỉ đảm bảo thứ tự trong một partition. Nếu các event cùng aggregate cần xử lý tuần tự, producer phải dùng key ổn định, ví dụ `orderId`, và consumer phải duy trì quy tắc xử lý phù hợp.

## 6. Kiểm thử hợp đồng event và serialization

### 6.1. Payload hợp lệ và dữ liệu biên

- [ ] Producer gửi được payload hợp lệ với đầy đủ field bắt buộc.
- [ ] Consumer deserialize đúng payload và mapping đúng kiểu dữ liệu.
- [ ] Kiểm tra field thiếu, field null, chuỗi rỗng, số âm, giá trị biên và timestamp.
- [ ] Kiểm tra timezone, định dạng ngày giờ, precision số thập phân và enum.
- [ ] Kiểm tra payload lớn gần giới hạn cấu hình của producer, broker, topic và consumer.
- [ ] Kiểm tra Unicode, ký tự tiếng Việt và dữ liệu đa ngôn ngữ.
- [ ] Kiểm tra header cần thiết: event ID, correlation ID, content type, schema/version và tenant nếu có.
- [ ] Kiểm tra key Kafka được tạo nhất quán với aggregate cần giữ thứ tự.

### 6.2. Tương thích schema

- [ ] Consumer phiên bản mới đọc được event do producer phiên bản hiện tại phát.
- [ ] Nếu hỗ trợ rolling deployment, consumer cũ xử lý được event mới trong phạm vi backward compatibility đã cam kết.
- [ ] Producer mới không phát field/enum khiến consumer cũ lỗi ngoài dự kiến.
- [ ] Kiểm thử thêm field optional, đổi default, deprecated field và enum value mới.
- [ ] Nếu dùng Schema Registry, kiểm tra compatibility mode và subject naming strategy.
- [ ] Nếu dùng JSON type headers hoặc trusted packages, xác nhận deserializer chỉ tin cậy các package cần thiết.
- [ ] Có fixture event của các version đang được lưu trữ/replay để regression test.

### 6.3. Payload lỗi và deserialization failure

- [ ] Gửi payload hỏng hoặc không đúng encoding và xác nhận lỗi được phân loại.
- [ ] Xác nhận deserialization error được xử lý trước khi listener method chạy.
- [ ] Nếu cần chuyển record lỗi sang error handler/DLT, cấu hình deserializer hỗ trợ giữ thông tin lỗi, ví dụ `ErrorHandlingDeserializer` trong Spring Kafka.
- [ ] Kiểm tra record lỗi không làm consumer lặp vô hạn tại cùng offset.
- [ ] Xác nhận DLT giữ được raw bytes và metadata cần thiết để điều tra hoặc replay.
- [ ] Không log toàn bộ payload nếu có dữ liệu cá nhân, credential hoặc thông tin nhạy cảm.

## 7. Kiểm thử producer dùng KafkaTemplate

- [ ] Gửi record thành công tới đúng topic.
- [ ] Xác nhận key, value, timestamp, partition và headers theo hợp đồng.
- [ ] Xác nhận `SendResult`/record metadata có topic, partition và offset hợp lệ.
- [ ] Kiểm tra partition routing khi có key và khi key null.
- [ ] Gửi nhiều event cùng key và xác nhận chúng đi cùng partition.
- [ ] Xác nhận thứ tự gửi cùng key trong điều kiện bình thường và khi producer retry.
- [ ] Kiểm tra callback/future khi broker xác nhận thành công.
- [ ] Kiểm tra callback/future khi topic không tồn tại, ACL bị từ chối hoặc broker unavailable.
- [ ] Xác nhận ứng dụng không bỏ qua exception bất đồng bộ từ `KafkaTemplate.send()`.
- [ ] Kiểm tra timeout và retry không tạo vòng lặp gửi không kiểm soát.
- [ ] Kiểm tra producer được đóng đúng lifecycle khi application shutdown.
- [ ] Nếu dùng nhiều producer factory, xác nhận serializer, security và transaction config của từng factory.

Ví dụ integration test tối thiểu với embedded broker:

```java
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@EmbeddedKafka(partitions = 3, topics = "orders")
@DirtiesContext
class OrderProducerIntegrationTest {

    @Autowired
    private KafkaTemplate<String, OrderCreated> kafkaTemplate;

    @Test
    void publishesOrderEvent() throws Exception {
        OrderCreated event = new OrderCreated("order-42", "CREATED");

        SendResult<String, OrderCreated> result = kafkaTemplate
                .send("orders", event.orderId(), event)
                .get(10, TimeUnit.SECONDS);

        assertEquals("orders", result.getRecordMetadata().topic());
        assertTrue(result.getRecordMetadata().offset() >= 0);
    }
}
```

`OrderCreated` trong ví dụ là DTO của ứng dụng. Ví dụ cần có `spring-kafka-test` (hoặc starter test tương ứng với Spring Boot version), topic test và application context đã cấu hình `KafkaTemplate`. API trả về của `KafkaTemplate.send()` khác nhau giữa các dòng Spring Kafka cũ và mới; `Future.get()` được dùng ở đây để chờ kết quả và không phụ thuộc callback style. Embedded broker phù hợp integration test nhanh; staging với broker cùng topology/security production vẫn cần thiết.

## 8. Kiểm thử consumer dùng @KafkaListener

- [ ] Listener subscribe đúng topic và group ID.
- [ ] Listener nhận đúng payload, key, headers và metadata.
- [ ] Trong trạng thái group ổn định, mỗi partition được assign cho tối đa một consumer trong cùng group.
- [ ] Mô phỏng side effect hoàn tất nhưng consumer chết/rebalance trước commit; xác nhận record có thể được giao lại và idempotency bảo vệ nghiệp vụ.
- [ ] Hai consumer group độc lập đều nhận được bản sao event theo semantics pub/sub.
- [ ] Consumer mới tham gia hoặc rời group không làm mất record đã commit.
- [ ] Kiểm tra `auto.offset.reset=earliest` và `latest` trong group chưa có offset.
- [ ] Kiểm tra group có offset đã commit sẽ tiếp tục từ vị trí đúng.
- [ ] Kiểm tra restart consumer sau khi xử lý thành công và trước/sau commit.
- [ ] Kiểm tra rebalance trong lúc listener đang xử lý.
- [ ] Kiểm tra concurrency nhiều consumer và phân phối partition.
- [ ] Xác nhận consumer dư so với partition không tạo kỳ vọng throughput sai.
- [ ] Xác nhận listener exception được chuyển tới error handler đúng cách.
- [ ] Xác nhận listener không nuốt exception nếu cần rollback/retry.
- [ ] Kiểm tra graceful shutdown và thời gian hoàn tất record đang xử lý.

`auto.offset.reset` chỉ có tác dụng khi group chưa có committed offset hợp lệ (hoặc offset không còn trong retention); nó không ghi đè offset đã commit. Test cần tạo group ID mới hoặc reset offset có chủ đích để kiểm tra `earliest`/`latest`.

### Kiểm thử offset và delivery semantics

- [ ] Xác định ứng dụng yêu cầu at-most-once, at-least-once hay consume-transform-produce exactly-once trong phạm vi Kafka.
- [ ] Kiểm tra AckMode và thời điểm offset commit.
- [ ] Mô phỏng crash sau khi side effect hoàn tất nhưng trước khi offset commit.
- [ ] Xác nhận duplicate delivery không gây side effect trùng hoặc đã được xử lý bằng idempotency.
- [ ] Mô phỏng commit offset thất bại sau rebalance.
- [ ] Xác nhận không commit offset trước khi nghiệp vụ hoàn tất nếu yêu cầu at-least-once.
- [ ] Với manual acknowledgment, xác nhận chỉ acknowledge sau khi xử lý thành công.
- [ ] Với batch listener, xác nhận commit/rollback theo đúng batch semantics.

Kafka consumer thông thường có thể giao lại record khi process lỗi trước commit. Thiết kế consumer cần idempotent theo event ID hoặc business key khi side effect có thể lặp. Không dùng correlation ID thay cho event ID để deduplicate nhiều event thuộc cùng một nghiệp vụ.

## 9. Kiểm thử retry, error handler và DLT

### 9.1. Phân loại lỗi

- [ ] Phân biệt lỗi transient (timeout, network tạm thời, service unavailable) và lỗi permanent (payload sai, business validation fail).
- [ ] Retry chỉ áp dụng cho loại lỗi có khả năng phục hồi.
- [ ] Exception không retry được được recover hoặc chuyển DLT theo policy.
- [ ] Kiểm tra số lần retry, delay, backoff multiplier, max delay và jitter nếu dùng.
- [ ] Kiểm tra tổng thời gian retry không vượt poll/transaction timeout theo cách gây rebalance hoặc abort ngoài dự kiến.
- [ ] Xác nhận error handler không retry vô hạn record độc hại.

### 9.2. Dead-letter topic

- [ ] Record thất bại sau số lần retry được gửi tới đúng DLT.
- [ ] DLT record giữ payload/raw bytes, key và headers cần thiết.
- [ ] Metadata gốc như topic, partition, offset, exception và delivery attempt được giữ theo cấu hình.
- [ ] Principal của recoverer có quyền ghi DLT.
- [ ] DLT có retention đủ dài và được giám sát.
- [ ] Có quy trình phân loại, sửa dữ liệu và replay DLT.
- [ ] Replay không tạo duplicate side effect; consumer downstream có idempotency.
- [ ] Không để DLT consumer tự động phát lại record lỗi vào main topic vô hạn.
- [ ] Kiểm tra trường hợp DLT publish thất bại: offset gốc có được commit hay vẫn retry theo policy?
- [ ] Cảnh báo khi DLT tăng nhanh hoặc có record tồn đọng quá lâu.

### 9.3. Retry topic và ordering

- [ ] Nếu dùng `@RetryableTopic`, kiểm tra topic retry, naming, partition và retention.
- [ ] Xác nhận số lần retry và delay thực tế.
- [ ] Kiểm tra ordering có thể thay đổi khi record được chuyển qua retry topic.
- [ ] Nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt theo key, xác nhận retry strategy không cho phép event sau vượt event trước theo cách sai nghiệp vụ.
- [ ] Kiểm tra non-blocking retry và DLT hoạt động khi service downstream phục hồi.

## 10. Kiểm thử transaction và exactly-once

- [ ] Transactional producer có `transactionIdPrefix` duy nhất giữa các application instance chạy đồng thời.
- [ ] Producer factory và `KafkaTemplate` dùng chung cấu hình transaction đúng.
- [ ] Gửi nhiều record trong một transaction và xác nhận tất cả cùng commit hoặc cùng abort.
- [ ] Mô phỏng exception trước commit và xác nhận record abort không hiển thị với consumer `read_committed`.
- [ ] Mô phỏng producer fencing bằng hai producer dùng cùng transactional ID trong test cô lập.
- [ ] Xác nhận producer bị fence không được tái sử dụng.
- [ ] Với consume-transform-produce, xác nhận output records và consumer offsets được commit trong cùng Kafka transaction.
- [ ] Xác nhận consumer dùng `isolation.level=read_committed` khi yêu cầu chỉ đọc dữ liệu đã commit.
- [ ] Kiểm tra transaction timeout và transaction coordinator unavailable.
- [ ] Kiểm tra retry/error handler khi listener transaction rollback.
- [ ] Xác nhận exception không bị nuốt trước khi transaction manager quyết định commit.
- [ ] Kiểm tra transactional ID ACL và topic ACL.
- [ ] Kiểm tra graceful shutdown trong lúc transaction đang mở.
- [ ] Kiểm tra commit timeout và khả năng đối soát kết quả chưa rõ ràng.

Exactly-once trong Kafka có phạm vi rõ ràng: transaction có thể atomically ghi output Kafka records và consumer offsets. Nó không tự làm cho thao tác database, HTTP hoặc side effect bên ngoài Kafka exactly-once. Nếu cần phối hợp database và Kafka, kiểm tra Transactional Outbox/CDC và Inbox/idempotency.

## 11. Kiểm thử partition ordering và concurrency

- [ ] Chọn key ổn định theo aggregate, ví dụ `orderId`, `accountId` hoặc `customerId`.
- [ ] Kiểm tra event cùng key được route vào cùng partition.
- [ ] Kiểm tra event khác key có thể chạy song song và không giả định global ordering.
- [ ] Xác nhận partition count đáp ứng mức song song cần thiết.
- [ ] Kiểm tra tổng consumer count = số replica × listener concurrency.
- [ ] Kiểm tra assignment khi consumer count nhỏ hơn, bằng và lớn hơn partition count.
- [ ] Kiểm tra tăng/giảm replica tạo rebalance dự kiến và group ổn định trở lại.
- [ ] Kiểm tra xử lý chậm không vượt `max.poll.interval.ms`.
- [ ] Kiểm tra `max.poll.records` với payload và thời gian xử lý thực tế.
- [ ] Xác nhận consumer thread không bị chặn vô hạn bởi HTTP, database hoặc `Thread.sleep()`.
- [ ] Nếu xử lý async, xác nhận acknowledgment và backpressure được thiết kế rõ ràng.
- [ ] Kiểm tra thread safety của service được gọi từ nhiều listener thread.

## 12. Kiểm thử bảo đảm dữ liệu và idempotency

- [ ] Mỗi event có event ID duy nhất và được lưu/truyền nhất quán.
- [ ] Consumer xử lý lại cùng event ID mà không lặp side effect ngoài ý muốn.
- [ ] Kiểm tra duplicate do producer retry, consumer restart, rebalance và DLT replay.
- [ ] Kiểm tra event đến trễ hoặc sai thứ tự theo chính sách nghiệp vụ.
- [ ] Kiểm tra event version cũ và event đã bị supersede.
- [ ] Nếu cập nhật database, dùng unique constraint/inbox hoặc cơ chế idempotency phù hợp.
- [ ] Nếu dùng tombstone, xác nhận consumer downstream xóa state đúng key.
- [ ] Có thể replay dữ liệu trong retention window mà không phá trạng thái hiện tại.
- [ ] Có quy trình đối soát record count hoặc business invariant giữa producer và consumer.

## 13. Kiểm thử observability và cảnh báo

- [ ] Log có service name, environment, topic, partition, offset, group ID và event ID khi phù hợp.
- [ ] Correlation ID được truyền qua Kafka headers và xuất hiện trong log downstream.
- [ ] MDC được cleanup sau mỗi record; không rò correlation ID giữa các consumer thread.
- [ ] Trace context được propagate nếu hệ thống dùng Micrometer Tracing/OpenTelemetry.
- [ ] Không đưa correlation ID, event ID, order ID hoặc offset vào metric tag có cardinality cao.
- [ ] Có metric producer send success/failure và latency.
- [ ] Có metric consumer record rate, processing duration, error rate và lag.
- [ ] Có metric retry count, DLT publish count và DLT backlog.
- [ ] Có metric transaction commit/abort/fencing nếu dùng transaction.
- [ ] Có metric rebalance rate, rebalance latency và consumer count.
- [ ] Dashboard phân biệt lỗi của từng topic, group và listener.
- [ ] Alert có ngưỡng, thời gian duy trì và hướng dẫn xử lý rõ ràng.
- [ ] Kiểm tra log/metric không chứa payload nhạy cảm, token hoặc secret.

Alert nên dựa trên xu hướng và SLO, không chỉ dựa vào một log đơn lẻ. Ví dụ lag tăng trong vài giây khi deploy có thể bình thường; lag tăng liên tục cùng processing latency cao cần cảnh báo.

## 14. Kiểm thử hiệu năng và tải

- [ ] Chạy tải bình thường theo throughput dự kiến.
- [ ] Chạy peak/burst load và xác nhận consumer lag phục hồi trong thời gian cho phép.
- [ ] Dùng payload có kích thước gần dữ liệu thực tế.
- [ ] Đo producer send latency p95/p99 và lỗi send.
- [ ] Đo consumer processing latency p95/p99.
- [ ] Đo lag theo từng partition để phát hiện hot partition.
- [ ] Kiểm tra throughput theo partition và key distribution.
- [ ] Kiểm tra CPU, heap, GC pause, network, disk và broker request queue.
- [ ] Kiểm tra buffer exhaustion, request timeout và backpressure.
- [ ] Kiểm tra consumer lag khi downstream database/service chậm.
- [ ] Xác nhận hệ thống không mất ổn định khi tải tăng rồi giảm.
- [ ] So sánh kết quả với SLO đã thống nhất, không dùng ngưỡng tùy ý.

Nếu một partition có key quá nóng, tăng consumer concurrency không giải quyết được vì một partition tại một thời điểm chỉ được một consumer trong group sở hữu. Cần xem lại key distribution hoặc cách phân vùng nghiệp vụ.

## 15. Kiểm thử phục hồi và tình huống lỗi

Thực hiện trong môi trường có kiểm soát và có người theo dõi.

- [ ] Dừng một broker và xác nhận producer/consumer phục hồi theo cấu hình replication.
- [ ] Restart leader broker của partition đang sử dụng.
- [ ] Tạm ngắt network giữa ứng dụng và broker.
- [ ] Làm downstream service timeout hoặc trả lỗi 5xx.
- [ ] Làm database chậm hoặc unavailable nếu listener phụ thuộc database.
- [ ] Restart consumer khi đang xử lý record.
- [ ] Kill process trước commit và sau commit để xác nhận delivery semantics.
- [ ] Scale consumer lên/xuống và quan sát rebalance.
- [ ] Làm coordinator unavailable trong môi trường thử nghiệm nếu có thể.
- [ ] Kiểm tra ứng dụng phục hồi sau khi dependency hoạt động trở lại.
- [ ] Xác nhận retry không tạo storm hoặc gây quá tải downstream.
- [ ] Xác nhận không có offset commit sai khiến record bị bỏ qua.
- [ ] Xác nhận duplicate delivery không phá dữ liệu nghiệp vụ.

Không thực hiện chaos test trực tiếp trên production nếu chưa có kế hoạch, giới hạn blast radius, phê duyệt vận hành và phương án dừng thử nghiệm.

## 16. Kiểm thử triển khai, rolling update và rollback

- [ ] Image/artifact triển khai đúng commit, version và dependency lock đã kiểm thử.
- [ ] Cấu hình môi trường được kiểm tra trước khi rollout.
- [ ] Consumer group ID giữ ổn định nếu mục đích là tiếp tục offset của cùng ứng dụng.
- [ ] Nếu đổi group ID, đã đánh giá việc đọc lại hoặc bỏ qua dữ liệu theo `auto.offset.reset`.
- [ ] Transaction ID prefix duy nhất giữa các replica và không bị dùng chung ngoài ý muốn.
- [ ] Rolling deployment không làm toàn bộ consumer dừng cùng lúc ngoài kế hoạch.
- [ ] Graceful shutdown cho listener container và producer factory được kiểm chứng.
- [ ] `terminationGracePeriodSeconds`/shutdown timeout đủ cho quá trình dừng an toàn.
- [ ] Phiên bản consumer mới tương thích event producer cũ trong thời gian rollout.
- [ ] Nếu rollback ứng dụng, consumer cũ vẫn đọc được event do producer mới đã phát.
- [ ] Schema/event version không làm rollback trở nên bất khả thi.
- [ ] Đã diễn tập rollback với dữ liệu test và consumer group thực tế.
- [ ] Readiness/liveness probe không gây restart liên tục khi Kafka tạm thời unavailable.
- [ ] Có canary hoặc rollout từng phần nếu mức độ rủi ro yêu cầu.

## 17. Kiểm thử runbook và khả năng vận hành

- [ ] Có hướng dẫn kiểm tra consumer group bằng `kafka-consumer-groups`.
- [ ] Có hướng dẫn kiểm tra topic, partition, retention và ACL.
- [ ] Có hướng dẫn xử lý consumer lag và rebalance liên tục.
- [ ] Có hướng dẫn xử lý serialization error, retry và DLT backlog.
- [ ] Có hướng dẫn xử lý transaction abort/fencing nếu bật transaction.
- [ ] Có hướng dẫn replay DLT và đối soát duplicate.
- [ ] Có dashboard liên kết correlation ID với trace ID khi có tracing.
- [ ] Có người nhận cảnh báo và escalation path.
- [ ] Có quy trình rotate credential và khôi phục khi secret hết hạn.
- [ ] Có kế hoạch xử lý khi broker cluster hoặc schema registry unavailable.
- [ ] Có runbook rollback và điều kiện dừng rollout.
- [ ] Đội vận hành đã thực hành ít nhất một tình huống lỗi đại diện.

## 18. Bộ test tối thiểu theo tầng

| Tầng kiểm thử | Mục tiêu | Công cụ/phương pháp thường dùng | Khi nào chạy |
|---|---|---|---|
| Unit test | Logic mapping, validation, key selection, retry classification | JUnit, Mockito, AssertJ | Mỗi commit |
| Serialization/contract test | Payload và schema tương thích | Serializer/deserializer thật, schema compatibility check | Mỗi thay đổi event contract |
| Embedded Kafka integration | Producer, listener, offset, header và error handler | `spring-kafka-test`, `@EmbeddedKafka` | Pull request/CI |
| Container integration | Khác biệt gần broker thật, security, KRaft và broker config | Testcontainers hoặc Kafka test cluster | CI/staging |
| End-to-end test | Luồng qua nhiều service/topic và side effect | Môi trường tích hợp | Trước release |
| Performance test | Throughput, latency, lag và tài nguyên | Load generator + metrics | Trước release lớn và khi thay topology |
| Resilience/chaos test | Broker/network/downstream failure và recovery | Fault injection có kiểm soát | Theo lịch hoặc thay đổi rủi ro cao |
| Production smoke test | Xác nhận kết nối, publish/consume và dashboard sau deploy | Synthetic event hoặc canary flow | Sau rollout |

Embedded Kafka hữu ích cho test nhanh và lặp lại. Nó không thay thế kiểm thử với broker topology, replication, ACL, TLS, quota và network giống môi trường đích.

## 19. Ma trận test case tối thiểu

| ID | Tình huống | Kết quả mong đợi | Bằng chứng |
|---|---|---|---|
| KAF-001 | Producer gửi event hợp lệ | Send thành công, đúng topic/key/partition | Test report + metadata |
| KAF-002 | Consumer nhận event | Listener nhận đúng payload và headers | Integration test |
| KAF-003 | Hai event cùng key | Cùng partition và giữ thứ tự theo thiết kế | Partition/offset assertion |
| KAF-004 | Payload không hợp lệ | Error handler phân loại và xử lý đúng | Log + DLT record |
| KAF-005 | Downstream timeout | Retry theo backoff và không retry vô hạn | Retry metrics/log |
| KAF-006 | Retry hết số lần | Record được chuyển DLT đúng policy | DLT metadata |
| KAF-007 | Consumer restart trước commit | Record có thể giao lại; idempotency bảo vệ side effect | Test + DB state |
| KAF-008 | Consumer group rebalance | Assignment ổn định lại, không mất record đã commit | Group state + offsets |
| KAF-009 | Transaction abort | `read_committed` không thấy record abort | Consumer integration test |
| KAF-010 | Producer fencing | Producer stale không tiếp tục ghi | Exception + broker/client log |
| KAF-011 | Broker tạm unavailable | Client reconnect, lag phục hồi | Metrics + recovery time |
| KAF-012 | Rolling deployment | Consumer mới tương thích event đang lưu chuyển | Deployment test |
| KAF-013 | DLT replay | Event được xử lý lại an toàn | Replay audit + business state |
| KAF-014 | Peak load | Latency/lag nằm trong SLO hoặc phục hồi trong RTO | Load test report |
| KAF-015 | Thiếu ACL | Broker từ chối đúng thao tác | Broker authorization log |

## 20. Điều kiện Go/No-Go trước triển khai

Chỉ cho phép rollout khi các điều kiện bắt buộc sau đều đạt:

- [ ] Không còn lỗi blocker trong unit, contract và integration test.
- [ ] Producer/consumer contract tương thích với phiên bản event đang được lưu trong Kafka.
- [ ] Topic, partition, replication, retention và ACL đã được provision đúng.
- [ ] Retry/DLT đã được kiểm thử cả nhánh thành công và nhánh lỗi.
- [ ] Offset/acknowledgment semantics và idempotency đã được xác nhận.
- [ ] Nếu dùng transaction, commit/abort/fencing và `read_committed` đã được kiểm thử.
- [ ] Security, secret management và TLS/SASL đã được xác nhận ở môi trường đích.
- [ ] Performance test đạt SLO đã thống nhất hoặc có chấp thuận ngoại lệ bằng văn bản.
- [ ] Dashboard, alert, runbook và người trực vận hành đã sẵn sàng.
- [ ] Có kế hoạch rollout, rollback và người có quyền quyết định dừng triển khai.
- [ ] Mọi NOT TESTED/FAIL còn lại đã được ghi nhận, đánh giá rủi ro và chấp thuận rõ ràng.

Không dùng số lượng test pass làm tiêu chí duy nhất. Một lỗi nghiêm trọng về offset, duplicate side effect, schema compatibility, DLT hoặc security có thể khiến release không an toàn dù phần lớn test khác đều xanh.

## 21. Hồ sơ bằng chứng cần lưu

- [ ] Commit SHA, build artifact version và dependency/BOM version.
- [ ] Test report unit, contract, integration và end-to-end.
- [ ] Kết quả topic/partition/replication/ACL validation.
- [ ] Cấu hình hiệu lực đã loại bỏ secret.
- [ ] Kết quả load test gồm throughput, p95/p99 latency, lag và tài nguyên.
- [ ] Kết quả failure/recovery test và thời gian phục hồi.
- [ ] Kết quả DLT/replay và transaction test nếu áp dụng.
- [ ] Dashboard/alert snapshot và runbook version.
- [ ] Danh sách FAIL, NOT TESTED, N/A và người chấp thuận ngoại lệ.
- [ ] Kế hoạch rollout/rollback cùng người phụ trách.

## 22. Checklist nhanh ngay sau triển khai

- [ ] Ứng dụng khởi động và kết nối được Kafka cluster.
- [ ] Producer canary gửi event và nhận acknowledgment.
- [ ] Consumer group có member và partition assignment như dự kiến.
- [ ] Synthetic event được xử lý đúng một lần về mặt nghiệp vụ hoặc duplicate được idempotency hấp thụ.
- [ ] Offset tiến lên sau xử lý thành công.
- [ ] Consumer lag không tăng liên tục.
- [ ] Không có serialization error, authorization error, retry storm hoặc DLT spike.
- [ ] Transaction commit/abort rate bình thường nếu dùng transaction.
- [ ] Dashboard, alert và log correlation hoạt động.
- [ ] Không có restart/rebalance bất thường sau rollout.
- [ ] Đội vận hành xác nhận hệ thống ổn định trước khi tăng rollout lên toàn bộ replica.

## 23. Tổng kết

- Kiểm thử trước triển khai phải bao phủ producer, consumer, topic/partition, offset/group, serialization, retry/DLT, transaction, concurrency và vận hành.
- Mỗi assertion cần bằng chứng; cấu hình có mặt trong file không đồng nghĩa cấu hình đã hoạt động.
- Kiểm thử duplicate, restart, rebalance, retry và DLT là phần bắt buộc để đánh giá độ tin cậy của consumer.
- Exactly-once của Kafka không tự bao phủ database hoặc hệ thống bên ngoài Kafka.
- Embedded Kafka phù hợp test nhanh; staging/container test cần xác nhận topology, security và broker config gần production.
- Go/No-Go dựa trên rủi ro và SLO, không chỉ dựa vào tỷ lệ test pass.
- Sau rollout cần smoke test và quan sát lag, error, rebalance, DLT cùng transaction metrics.

Một ứng dụng Spring Kafka chỉ nên được triển khai khi nhóm phát triển chứng minh được cả luồng thành công lẫn hành vi khi lỗi, đồng thời đội vận hành có đủ metric, cảnh báo và runbook để phát hiện và phục hồi sự cố.

## Tài liệu tham khảo

- [Spring Kafka Reference — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Kafka Reference — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring Kafka Reference — Receiving Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages.html)
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka Reference — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Apache Kafka — Producer Configs](https://kafka.apache.org/documentation/#producerconfigs)
- [Apache Kafka — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)
- [Apache Kafka — Topic Configs](https://kafka.apache.org/documentation/#topicconfigs)
