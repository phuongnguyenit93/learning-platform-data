# Error event và dead-letter trong Debezium

## 1. Bài toán: một CDC event lỗi thì dữ liệu đi về đâu?

Trong module **SPRING_INTEGRATION_ADAPTERS**, dữ liệu từ hệ thống ngoài đi vào Spring Integration thông qua inbound adapter hoặc gateway, được chuyển qua `MessageChannel`, xử lý bởi transformer, router, filter, service activator, rồi có thể được gửi ra Kafka, JMS, AMQP, HTTP, SFTP, file hoặc cơ sở dữ liệu bằng outbound adapter. Với bài toán đồng bộ cơ sở dữ liệu, **Debezium** đọc transaction log của nguồn và tạo những sự kiện *Change Data Capture* (CDC) để một luồng Spring Integration tiếp tục xử lý.

Một sự kiện CDC có thể gặp lỗi ở nhiều điểm:

- Debezium không còn đọc được binlog/WAL hoặc không giải mã được thay đổi từ database nguồn.
- Kafka Connect không chuyển đổi được dữ liệu sang định dạng message hoặc một SMT (*Single Message Transform*) gặp exception.
- Kafka consumer của Spring Integration không deserialize được record.
- Transformer nhận một schema mới, thiếu field bắt buộc hoặc không hiểu `op`.
- Service activator ghi sang database đích bị timeout, deadlock hoặc vi phạm ràng buộc.
- Adapter gửi tới HTTP/JMS/AMQP hoặc outbound sink gặp lỗi kết nối.

Nếu mọi lỗi đều được retry vô hạn, **một bản ghi lỗi cố định** (*poison pill*) có thể giữ một Kafka partition không tiến lên. Nếu ứng dụng bỏ qua bản ghi quá sớm, projection có thể **mất một thay đổi nghiệp vụ**. Một cơ chế **dead-letter** (DLQ/DLT) giúp cô lập những message không thể xử lý theo chính sách đã định, lưu đủ ngữ cảnh để điều tra và phát lại sau khi sửa nguyên nhân.

Điểm cần nắm ngay: **Debezium không có một loại `op="error"` chuẩn chung trong row-change envelope cho mọi lỗi**, và “dead-letter” không phải một kênh tự động duy nhất xuyên suốt database → Debezium → Kafka → Spring Integration. Mỗi lớp có cách báo lỗi, retry và checkpoint riêng.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt lỗi nguồn CDC, lỗi Kafka Connect sink và lỗi consumer Spring Integration.
2. Giải thích sự khác nhau giữa **lỗi trong log/metrics**, **ErrorMessage** ở Spring Integration và **dead-letter record** trên Kafka.
3. Chọn retry, fail-fast, cảnh báo hoặc DLQ dựa trên loại lỗi và yêu cầu không mất dữ liệu.
4. Cấu hình Kafka Connect sink DLQ và Spring Kafka dead-letter recoverer theo đúng lớp đang xử lý.
5. Thiết kế metadata DLQ, offset acknowledgment, redrive, idempotency, quan sát và quy trình phục hồi.

## 2. Định vị lỗi trên toàn tuyến

~~~mermaid
flowchart TD
    DB[(MySQL / PostgreSQL)] --> CDC[Debezium<br/>source connector]
    CDC -->|CDC records| TOPIC[(Kafka CDC topic)]
    TOPIC --> IN[Spring Integration<br/>Kafka inbound adapter]
    IN --> CH[MessageChannel]
    CH --> HANDLER[Transformer / service activator]
    HANDLER --> SINK[(Database / HTTP / JMS / AMQP)]
    DB -. mất log / quyền .-> SOURCEERR[Connector/task FAILED<br/>log + metrics + alert]
    CDC -. giải mã binlog lỗi .-> SOURCEERR
    IN -. deserialize / process lỗi .-> RETRY[Consumer retry / recoverer]
    HANDLER -. exception đồng bộ .-> RETRY
    RETRY -->|hết retry, gửi thành công| DLT[(Kafka DLT topic)]
    RETRY -. lỗi gửi DLT .-> STOP[Giữ lỗi / tiếp tục retry<br/>theo chính sách]
    TOPIC --> CONNECTSINK[Kafka Connect sink<br/>nếu có]
    CONNECTSINK -. lỗi hỗ trợ bởi Connect .-> CONNECTDLQ[(Connect sink DLQ)]
~~~

**Sơ đồ là kiến trúc minh họa.** Một hệ thống không nhất thiết đồng thời có Spring Integration consumer và Kafka Connect sink. Nhánh Connect sink được vẽ riêng để phân biệt tính năng DLQ của Connect với cơ chế DLT phía Spring Kafka.

| Vị trí lỗi | Ví dụ | Công cụ quan sát/chính sách thích hợp | Có tự tạo DLQ Kafka không? |
|---|---|---|---|
| Database nguồn | Mất replication slot, binlog đã purge, thiếu quyền đọc | Database logs, Debezium task status, source offset, alert và quy trình recovery | **Không**; có thể chưa tạo được CDC record nào |
| Debezium source connector | Không giải mã được sự kiện log, schema history lỗi | Debezium logs, connector config, task status, metrics | Không mặc định; cần giải quyết ở nguồn/connector |
| Kafka Connect converter/SMT | Kiểu dữ liệu không chuyển đổi được | Connect error handling; tùy source/sink và phiên bản | Tính năng **built-in DLQ** chủ yếu dành cho **sink connector** |
| Kafka Connect sink | Không xử lý được record đã đọc | Connect tolerance/retry/log/DLQ khi loại lỗi được hỗ trợ | Có thể dùng Connect sink DLQ |
| Spring Kafka consumer | Deserialization/conversion lỗi | `ErrorHandlingDeserializer`, listener container error handler, recoverer | Có, **nếu** cấu hình recoverer xuất DLT |
| Spring Integration flow | Validator lỗi, service activator ném exception | `errorChannel`, retry advice, đồng bộ lỗi với Kafka listener container | `errorChannel` tự nó **không** phải Kafka DLT |
| Hệ thống đích | Timeout DB, HTTP 503, JMS broker lỗi | Retry có giới hạn, kiểm tra tính idempotent, circuit breaker | Tùy thiết kế flow/recoverer |

Một source connector bị dừng do mất WAL sẽ không thể “đẩy bản ghi hỏng vào DLT rồi tiếp tục” nếu chưa có record có thể xử lý. Để khôi phục, cần kiểm tra khả năng còn log, offset, snapshot và trạng thái schema của nguồn.

## 3. “Error event” có thể mang ba ý nghĩa khác nhau

### 3.1. Exception hoặc trạng thái lỗi ở connector

Debezium source có thể ghi stack trace, vị trí log lỗi hoặc trạng thái `FAILED` ở Kafka Connect task. Đây là **tín hiệu vận hành**, không nhất thiết là một CDC message trên topic nghiệp vụ. Ví dụ MySQL source lỗi khi đọc một binlog event bị hỏng; Kafka topic có thể **không chứa record tương ứng**, nên consumer downstream không có gì để nhận và đưa vào DLT.

Các luồng heartbeat, transaction metadata hay schema change notification của Debezium cũng có hợp đồng riêng; không nên coi chúng là “error event” chỉ vì khác cấu trúc `before/after/op` của row CDC.

### 3.2. Spring Integration ErrorMessage

Trong Spring Integration, khi một số thành phần hoặc endpoint gặp exception, framework có thể đưa một `ErrorMessage` chứa exception vào `errorChannel` (toàn cục hoặc cấu hình riêng). Đây là **Spring message biểu diễn lỗi của luồng**, không mặc định là Kafka record.

Ví dụ:

~~~text
cdcRawChannel
    -> transform envelope
    -> orderProjectionHandler
               |
               +-- exception --> orderErrorChannel
                                     |
                                     +-- audit / alert / recovery decision
~~~

Nếu chỉ gửi lỗi đến một handler ghi log rồi handler kết thúc bình thường, listener container **có thể coi việc xử lý message đã thành công**, tùy cách adapter nối với flow. Cần quyết định rõ: exception nào được ném ngược về Kafka listener để retry, exception nào đi nhánh recovery đã xác nhận bền vững, và khi nào mới được commit consumer offset.

### 3.3. Kafka dead-letter record

**DLQ** (*Dead Letter Queue*) là khái niệm chỉ nơi giữ message không thể xử lý; **DLT** (*Dead Letter Topic*) thường chỉ một Kafka topic dùng cho mục đích đó. Hai thuật ngữ thường được dùng gần nghĩa trong kiến trúc Kafka.

Record gửi vào DLT có thể:

- Giữ **key và value gốc** và kèm header về exception, topic/partition/offset.
- Hoặc là một **error envelope do ứng dụng tự định nghĩa** với reference tới payload gốc.

Không nên mặc định payload DLT có trường `error`, `reason`, `originalEvent` hay `retryCount`: các trường này chỉ tồn tại nếu framework hoặc chính ứng dụng tạo ra. Đặc biệt, Spring Kafka `DeadLetterPublishingRecoverer` thường chuyển bản ghi với key/value gốc và metadata lỗi qua headers, còn Kafka Connect sink DLQ thêm error context theo cấu hình riêng.

## 4. Phân loại lỗi để chọn retry hoặc dead-letter

Quyết định xử lý phải dựa vào khả năng phục hồi và ý nghĩa dữ liệu:

| Nhóm lỗi | Ví dụ | Hướng xử lý thường phù hợp |
|---|---|---|
| **Tạm thời** | DB đích timeout, HTTP 503, broker mất kết nối ngắn | Retry có backoff và giới hạn số lần/thời gian, giữ idempotency |
| **Record hỏng hoặc không tương thích** | JSON không parse được, field bị đổi kiểu, schema/version chưa hỗ trợ | Hạn chế retry mù; quarantine/DLT, triển khai bản sửa rồi redrive |
| **Vi phạm hợp đồng nghiệp vụ** | `amount < 0` không hợp lệ theo chính sách nhận | Đưa vào luồng lỗi có audit, can thiệp và quyết định sửa nguồn hoặc bỏ có kiểm soát |
| **Lỗi nguồn/CDC** | Missing binlog/WAL, schema history không hợp lệ, connector không đọc được log | Fail-fast/alert; khôi phục connector hoặc snapshot/đối soát có kiểm soát |
| **Lỗi cấu hình hoặc hệ thống** | Sai credentials, topic không tồn tại, ACL deny | Sửa cấu hình/hạ tầng; tránh tự động đưa hàng loạt bản ghi vào DLT |
| **Lỗi lập trình** | `NullPointerException` trong transformer, mapper đọc sai field | Sửa code, kiểm thử với event thực; bảo toàn record để replay |
| **Thông điệp hợp lệ nhưng đặc biệt** | `op="r"`, Debezium tombstone, heartbeat | Định tuyến đúng contract; **không** coi là lỗi chỉ vì không có `after` |

Nếu một bản ghi lỗi **cố định** chặn tiến độ, DLT có thể cho phép luồng tiếp tục sau khi record đã được cô lập thành công. Nhưng bỏ qua một update trong chuỗi có quan hệ phụ thuộc cũng có thể khiến các update sau áp dụng sai. Bởi vậy với nghiệp vụ nhạy cảm về thứ tự, đôi khi cần **dừng xử lý key/partition**, sửa lỗi rồi replay theo thứ tự trước khi cho các event mới đi qua.

## 5. Lỗi ở Debezium source: đừng nhầm với Kafka Connect sink DLQ

### 5.1. Xử lý lỗi khi đọc transaction log

Một số Debezium connector (ví dụ MySQL, tùy phiên bản) có tùy chọn:

~~~properties
# Ví dụ thuộc tính Debezium source connector, không phải Spring Integration.
event.processing.failure.handling.mode=fail
~~~

Với MySQL connector ở những phiên bản hỗ trợ, các chế độ có thể gồm:

| Giá trị | Ý nghĩa thực tế | Rủi ro |
|---|---|---|
| `fail` | Báo lỗi và dừng connector/task khi không xử lý được sự kiện nguồn | Luồng CDC gián đoạn, cần người vận hành xử lý |
| `warn` | Ghi cảnh báo về sự kiện/vị trí lỗi rồi bỏ qua event đó | **Có thể mất một thay đổi**; projection thiếu dữ liệu |
| `ignore` | Bỏ qua sự kiện lỗi mà không ghi cảnh báo tương ứng | Nguy cơ sai lệch khó phát hiện |

**Tên thuộc tính và tập giá trị phải xác minh theo Debezium connector/version.** Chẳng hạn tài liệu MySQL sử dụng `warn` và `ignore` cho `event.processing.failure.handling.mode`, trong khi một số thuộc tính xử lý bất nhất schema có giá trị `skip`; không tráo lẫn các cấu hình này.

Trong bài toán cần tính đúng dữ liệu, nên ưu tiên **`fail` và cảnh báo rõ ràng** khi connector không thể giải mã một event quan trọng. Chọn `warn`/`ignore` chỉ khi đã chấp nhận mất bản ghi, có kiểm tra đối soát và có quy trình phục hồi. Không có DLT record nào chắc chắn được sinh ra cho event đã bị bỏ qua ngay tại lớp nguồn.

### 5.2. Source offset và điều kiện đọc lại

Giả sử offset bền vững đang ở `mysql-bin.000021:1000`, Debezium đọc một event lỗi ở vị trí sau đó rồi dừng:

1. Điều tra **nguyên nhân**: schema history, thay đổi DDL, dữ liệu hỏng, quyền, cấu hình hay log không còn.
2. Ghi lại nguồn, connector/task, thời điểm và tọa độ log/offset được báo.
3. Xác minh đoạn binlog/WAL cần đọc còn tồn tại.
4. Sửa nguyên nhân và thử resume theo cơ chế connector hỗ trợ.
5. Nếu không thể đọc lại, lên kế hoạch snapshot/đối soát từ một ranh giới nhất quán; không tùy ý “nhảy” offset để bỏ qua lỗi.

Nếu Kafka Connect sink DLQ đang có sẵn ở phía downstream thì nó **không khôi phục được** một event Debezium source chưa bao giờ phát ra.

### 5.3. Connect error tolerance không bao phủ mọi lỗi

Kafka Connect có `errors.tolerance`, `errors.retry.timeout`, `errors.log.enable` và các thuộc tính error reporting. Chúng không tạo ra lời hứa rằng mọi lỗi đọc binlog, lỗi quyền, mất log hay sự cố schema history của **Debezium source connector** đều được chuyển sang DLQ rồi tiếp tục.

Tương tự, nếu người học dùng Debezium Engine nhúng trong ứng dụng Java, cần xem **cơ chế xử lý exception và offset commit của Engine**, không thể áp dụng máy móc cấu hình Kafka Connect worker hoặc Spring Kafka consumer.

## 6. Kafka Connect sink DLQ: cấu hình đúng ngữ cảnh

Kafka Connect hỗ trợ ghi những record lỗi vào topic dead-letter trong đường **sink connector** (ví dụ sink tiêu thụ Kafka rồi ghi hệ thống đích), đối với các giai đoạn lỗi thuộc phạm vi cơ chế Connect như converter, SMT và xử lý sink được hỗ trợ.

**Ví dụ thuộc tính của một Kafka Connect *sink connector***:

~~~properties
# Chấp nhận bỏ qua record lỗi sau khi thực hiện error reporting/recovery.
errors.tolerance=all

# Retry những lỗi thuộc phạm vi Connect tối đa 60 giây.
errors.retry.timeout=60000
errors.retry.delay.max.ms=5000

# Ghi log lỗi; không đưa nguyên bản message vào log ứng dụng.
errors.log.enable=true
errors.log.include.messages=false

# DLQ cho sink connector:
errors.deadletterqueue.topic.name=orders-connect-sink-dlq
errors.deadletterqueue.context.headers.enable=true
~~~

Ý nghĩa:

- `errors.tolerance=none` là hành vi mặc định fail khi lỗi không được dung thứ; `all` cho phép bỏ qua những record lỗi thuộc cơ chế error tolerance sau khi thực hiện reporting theo cấu hình. **Không bật `all` tùy tiện** nếu yêu cầu bảo toàn mọi thay đổi.
- `errors.retry.timeout`/`errors.retry.delay.max.ms` chi phối các retry mà Connect error handling hỗ trợ; chúng không thay thế retry nghiệp vụ ở Spring Integration.
- `errors.deadletterqueue.topic.name` chỉ định DLQ Kafka cho **sink connector**; topic phải có retention, partition, replication và quyền ghi/đọc phù hợp.
- `errors.deadletterqueue.context.headers.enable=true` bổ sung các header ngữ cảnh lỗi, với tiền tố như `__connect.errors.`. Đừng giả định nội dung lỗi nằm trong JSON value.
- `errors.log.include.messages=false` tránh ghi key/value thô vào application log, đặc biệt khi CDC chứa thông tin cá nhân; vẫn cần kiểm soát quyền đọc DLQ.

Kafka Connect source như Debezium thường được cấu hình để **phát** CDC records. Nếu muốn xử lý lỗi ở consumer Spring Integration, hãy cấu hình **Spring Kafka/Spring Integration error handling** ở consumer đó thay vì cho rằng `errors.deadletterqueue.topic.name` đặt trên Debezium source sẽ tạo đúng quy trình DLT mong muốn.

## 7. Spring Integration: errorChannel, retry và Kafka DLT

### 7.1. Phân biệt `errorChannel` và DLT

Trong Spring Integration, `errorChannel` là **MessageChannel** dùng để chuyển thông tin exception, thường dưới dạng `ErrorMessage`. Nó có thể kết nối service activator ghi audit, gửi alert, hoặc một outbound adapter phát record sang Kafka DLT.

Ví dụ:

~~~text
KafkaMessageDrivenChannelAdapter
    -> cdcInboundChannel
        -> parse + validate
        -> orderProjectionHandler
            |
            +-- exception --> errorChannel
                                  -> errorAuditHandler
                                  -> (tùy thiết kế) Kafka DLT outbound adapter
~~~

Hãy phân biệt hai trường hợp:

- **Xử lý đồng bộ:** exception từ service activator/transformer có thể truyền ngược về listener container để Spring Kafka `DefaultErrorHandler` retry hoặc thực hiện recovery.
- **Bàn giao bất đồng bộ:** nếu message được chuyển vào `ExecutorChannel` hay queue nội bộ rồi listener nhận tín hiệu thành công trước khi worker xử lý xong, lỗi ở downstream có thể chỉ đi vào `errorChannel` và **không làm listener retry record gốc**. Khi đó ứng dụng phải xây riêng cơ chế xác nhận bàn giao bền vững, recovery và DLQ.

Không xem việc gửi được một `ErrorMessage` là bằng chứng record CDC đã được lưu an toàn trong DLT.

### 7.2. Spring Kafka `DefaultErrorHandler` với DLT

Khi Spring Integration sử dụng **Kafka message-driven channel adapter**, một cách triển khai phổ biến là cấu hình Spring Kafka listener container với `DefaultErrorHandler` và `DeadLetterPublishingRecoverer`.

Đoạn Java sau minh họa **bean error handler**; ứng dụng cần gắn nó vào đúng listener container mà Kafka inbound adapter đang dùng:

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class CdcKafkaErrorHandling {

    @Bean
    DefaultErrorHandler cdcErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                (record, error) -> new TopicPartition(
                        record.topic() + "-dlt",
                        record.partition()));

        // Backoff 1 giây, 2 lần retry sau lần xử lý đầu:
        // tối đa 3 lần thử trước khi chuyển sang recoverer.
        return new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L));
    }
}
~~~

**Lưu ý khi tích hợp:**

1. Bean trên **chưa tự động gắn** vào mọi Kafka listener container; cần cấu hình container/adapter sử dụng đúng handler.
2. `KafkaTemplate` cần serializer và quyền producer thích hợp với key/value của bản ghi có lỗi, kể cả dữ liệu gốc dạng `byte[]` khi deserialize thất bại.
3. Ví dụ giữ nguyên partition gốc khi xuất sang `-dlt`, nên DLT phải có ít nhất số partition tương ứng. Có thể chọn partition bằng chính sách khác nếu cần.
4. Khi recoverer và container hoàn tất thành công, record có thể được xem là *recovered* để consumer đi tiếp. Việc commit offset chính xác phụ thuộc ack mode, transaction mode, cấu hình container và phiên bản Spring Kafka.
5. Phải kiểm tra hành vi khi **publish DLT thất bại**. Không được đánh dấu đã bỏ qua record chỉ vì đã gọi phương thức gửi bất đồng bộ; cần cấu hình kiểm tra kết quả gửi và cách báo lỗi phù hợp.
6. Đoạn code dùng Spring Kafka API trong những phiên bản có `DefaultErrorHandler`. Kiểm tra API Spring Boot/Spring Kafka/Spring Integration đang sử dụng trước khi đưa vào dự án.

Một số môi trường sử dụng transaction Kafka; khi đó error/recovery có thể đi qua `DefaultAfterRollbackProcessor` hoặc một cơ chế transaction khác. Đừng trộn cấu hình transaction và non-transaction mà không kiểm chứng hành vi commit/rollback.

### 7.3. Deserialization failure và `ErrorHandlingDeserializer`

Một message có bytes không giải mã được có thể làm consumer lỗi **trước khi record đi vào Spring Integration MessageChannel**. Vì vậy đặt try/catch trong service activator có thể không bắt được lỗi này.

Spring Kafka cung cấp `ErrorHandlingDeserializer` để biểu diễn lỗi deserialization qua metadata/header cho listener container xử lý theo chính sách recoverer; trong các phiên bản hỗ trợ, DLT recoverer có thể phục hồi **bytes gốc** của value (hoặc key) bị lỗi để lưu lại. Cần cấu hình deserializer delegate, serializer của KafkaTemplate và chính sách lỗi cho cả **key** lẫn **value**.

Nếu message là Avro/Protobuf dùng Schema Registry, một lỗi tương thích schema hoặc lỗi kết nối Registry cần được phân loại cẩn thận. Đưa mọi lỗi Registry tạm thời vào DLT có thể khiến hàng loạt record hợp lệ bị cách ly do sự cố hạ tầng.

## 8. Thiết kế bản ghi dead-letter có thể điều tra và redrive

Trước khi đưa một CDC message vào DLT, cần biết sau này sẽ **đọc lại dữ liệu gì**, **sửa lỗi ở đâu** và **chạy lại thế nào**.

Một hợp đồng quan sát hữu ích:

| Nhóm | Dữ liệu nên giữ | Tại sao? |
|---|---|---|
| Nguồn Kafka | Topic, partition, offset, timestamp | Tìm record chính xác để điều tra hoặc replay |
| Khóa | Kafka record key và schema/encoding nếu có | Xác định đối tượng nghiệp vụ và giữ thứ tự theo key |
| Nội dung gốc | Key/value bytes hoặc tham chiếu lưu trữ bền vững | Sau khi sửa converter, có thể parse lại theo đúng dữ liệu ban đầu |
| Loại lỗi | Mã lỗi, loại exception, bước xử lý | Phân biệt deserialization, validation và lỗi sink |
| Tình trạng retry | Số lần thử, lần lỗi đầu/cuối, thời điểm retry tiếp | Quan sát poison pill và chính sách khắc phục |
| Thông tin Debezium | `op`, `source`, log position, transaction ID **nếu đọc được** | Đối soát CDC và phân biệt replay |
| Trace | Correlation ID, phiên bản consumer/configuration | Liên kết logs, metric và lần triển khai gây lỗi |
| Quản trị DLQ | Trạng thái OPEN/REPLAYED/RESOLVED, người xác minh, lý do | Tránh replay lặp hoặc bỏ quên bản ghi lỗi |

**Không phải mọi field đều có thể lấy ra.** Nếu deserialization thất bại trước khi đọc envelope, có thể chỉ còn raw bytes và Kafka metadata; không tự bịa `op` hay source log position. Nếu lỗi xảy ra tại Debezium source, có thể **chưa có Kafka topic/partition/offset**.

### 8.1. Ví dụ error envelope do ứng dụng tự định nghĩa

Thay vì sao chép toàn bộ dữ liệu nhạy cảm vào nhiều nơi, ứng dụng có thể lưu raw bytes tại kho bảo mật và đưa một metadata record vào topic quản trị:

~~~json
{
  "errorId": "err-orders-000042",
  "stage": "spring-integration-projection",
  "classification": "NON_RETRYABLE_SCHEMA",
  "reason": "Missing required order status mapping",
  "original": {
    "topic": "shop-cdc.sales.orders",
    "partition": 1,
    "offset": 2058,
    "keyRef": "secure://cdc-errors/000042/key",
    "valueRef": "secure://cdc-errors/000042/value"
  },
  "attempts": 3,
  "state": "OPEN"
}
~~~

**Đây là hợp đồng tự thiết kế, không phải payload mặc định** của Debezium, Kafka Connect hoặc Spring Kafka. `secure://...` chỉ là địa chỉ minh họa cho kho lưu trữ do ứng dụng quản lý, không phải URL thực.

Trong cấu hình mặc định của `DeadLetterPublishingRecoverer`, key/value thường là record gốc và thông tin lỗi thường được thêm vào **Kafka headers**. Nếu consumer DLT chỉ mong JSON giống ví dụ trên, phải thêm bước biến đổi rõ ràng trước khi ghi.

### 8.2. Giữ dữ liệu an toàn

CDC có thể chứa tên khách hàng, địa chỉ, mã định danh hoặc thông tin giao dịch. Khi gửi vào DLT:

- Không ghi toàn bộ payload/exception chứa dữ liệu nhạy cảm vào logs mở rộng.
- Phân quyền ACL cho DLQ/DLT và kho raw payload theo nguyên tắc tối thiểu.
- Áp dụng mã hóa, retention, quy trình xóa dữ liệu và audit truy cập phù hợp.
- Tránh cho DLT vô tình được tiêu thụ như CDC topic chính; nên đặt tên và group riêng.
- Xác định chuyện gì xảy ra nếu topic DLQ đầy, bị xóa hoặc không publish được.

Một DLT có thời hạn lưu ngắn hơn thời gian đội vận hành có thể sửa lỗi sẽ khiến khả năng redrive bị mất. Đồng thời lưu giữ vô hạn dữ liệu nhạy cảm cũng tạo chi phí/rủi ro. Cần chính sách retention phù hợp.

## 9. Retry, DLT và commit offset: ranh giới bảo toàn dữ liệu

Xét Kafka consumer đọc record tại offset `2058` và service activator cập nhật projection:

~~~mermaid
sequenceDiagram
    participant K as Kafka CDC topic
    participant C as Spring Kafka / Integration
    participant DB as Projection DB
    participant D as DLT
    K->>C: Record offset 2058
    C->>DB: Ghi projection
    DB-->>C: Timeout
    C->>DB: Retry có backoff
    DB-->>C: Timeout tiếp
    C->>D: Gửi record gốc + ngữ cảnh lỗi
    alt DLT publish xác nhận thành công
        D-->>C: Đã lưu
        C->>C: Recover/tiến offset theo cấu hình
    else DLT publish thất bại
        D-->>C: Lỗi
        C->>C: Giữ tình trạng lỗi, retry/dừng theo policy
    end
~~~

Với delivery **at-least-once**, ba ranh giới cần chú ý:

1. **Ghi đích xong, chưa commit Kafka offset:** restart có thể phát lại record; upsert/delete và side effect phải idempotent.
2. **Gửi DLT xong, chưa commit offset:** record có thể xuất hiện lại ở DLT hoặc được thử xử lý lại; nên có dedupe/idempotent redrive.
3. **Commit offset trước khi ghi đích hoặc DLT an toàn:** có thể làm một thay đổi bị bỏ qua ở consumer group mà chưa có bản sao để xử lý lại.

Do đó, quy trình chỉ “log lỗi rồi return success” không tương đương với đã xử lý record. Nếu quy tắc nghiệp vụ cho phép cách ly record và tiếp tục, cần xác minh nó đã được lưu bền vững ở DLT/queue quản trị trước khi consumer được phép tiến theo cấu hình của framework.

### Cảnh báo về thứ tự theo key

Giả sử event `E1` cập nhật `orders.id=42` từ `NEW` sang `PAID` bị gửi DLT; event `E2` sau đó cập nhật từ `PAID` sang `SHIPPED` được xử lý thành công. Khi redrive `E1`, nếu chỉ thực hiện upsert vô điều kiện, projection có thể **lùi từ SHIPPED về PAID**.

Giải pháp tùy nghiệp vụ:

- Dừng xử lý tiếp theo đối với key/partition đang lỗi cho đến khi sửa record cũ.
- Giữ version/order tin cậy để từ chối update cũ, hoặc áp dụng reconciliation từ trạng thái hiện tại.
- Khi redrive, đối soát lịch sử và xác định bản ghi có còn cần áp dụng hay đã được các update sau bao phủ.

**DLT không tự giải quyết thứ tự**, và Kafka không bảo đảm một transaction ở hai topic/partition sẽ có thứ tự xử lý thống nhất.

## 10. Quy trình redrive an toàn

Đưa record từ DLT trở lại hệ thống xử lý gọi là *redrive* hoặc *replay*. Nó cần có trạng thái rõ ràng, đặc biệt khi sửa code xử lý CDC.

1. **Xác định nguyên nhân:** lập nhóm theo connector, topic, partition, exception, schema version, thời điểm và bản triển khai.
2. **Sửa lỗi gốc:** cập nhật converter, DTO, transformer, mapping database hoặc hạ tầng; kiểm thử với raw record đã gây lỗi.
3. **Đánh giá dữ liệu và thứ tự:** kiểm tra key đó có những event mới hơn không, projection đang ở trạng thái nào và có side effect nào đã xảy ra.
4. **Lập kế hoạch replay:** dùng consumer group/worker redrive riêng, giữ record key, metadata cần thiết và giới hạn tốc độ; quyết định gửi lại Kafka topic chính hay gọi handler chuyên biệt.
5. **Thiết kế idempotency:** có thể một record đã được ghi đích nhưng timeout trả về, nên tránh cộng dồn, gửi email hoặc trừ tiền lần hai.
6. **Theo dõi và xác nhận:** đánh dấu các record đã phục hồi, đối soát dữ liệu đích với nguồn và kiểm tra DLQ backlog giảm đúng kỳ vọng.
7. **Khôi phục giám sát:** bảo đảm alert/metric quay về trạng thái bình thường; ghi nhận bài học để sửa contract hoặc kiểm thử.

Không tự xóa DLT ngay khi một lần replay “không ném exception”: cần kiểm tra nội dung đích đã đúng. Cũng không xóa **Debezium source offset** để redrive một message ở consumer; làm vậy có thể phát lại lượng lớn CDC và gây sai lệch thêm.

### Mô hình trạng thái đề xuất

~~~text
OPEN -> TRIAGED -> FIXED -> REPLAYING -> RESOLVED
                    |           |
                    |           +-> FAILED_REDRIVE -> TRIAGED
                    +-> CANCELLED_WITH_REASON (cần phê duyệt nghiệp vụ)
~~~

Những trạng thái trên là quy ước vận hành do ứng dụng đặt ra, không phải enum sẵn có của Kafka Connect hay Debezium.

## 11. Monitoring và cảnh báo để DLQ không trở thành “nghĩa trang message”

DLT chỉ hữu ích khi có người chịu trách nhiệm xử lý. Một pipeline có thể vẫn “RUNNING” nhưng đã đưa quá nhiều event vào DLQ và projection ngày càng lệch so với database.

| Chỉ số/tín hiệu | Diễn giải | Câu hỏi vận hành |
|---|---|---|
| Debezium connector/task status | `RUNNING`, `FAILED`, restart lặp | Có còn đọc được log nguồn không? |
| Source lag / vị trí log / replication slot lag | Debezium đang chậm hay log bị giữ lâu | Có nguy cơ hết retention binlog/WAL không? |
| CDC topic throughput | Số thay đổi đang được phát | Có đột ngột ngừng hoặc tăng khác thường không? |
| Kafka consumer lag | Consumer Spring Integration còn bao nhiêu record chưa đọc | Handler/adapter có bị kẹt không? |
| Retry attempts / failures | Số lần và thời gian lỗi theo loại | Lỗi tạm thời hay poison pill? |
| DLT records, tuổi record cũ nhất | Lượng message cần xử lý và mức độ tồn đọng | Có ai đang triage và giải quyết đúng hạn không? |
| DLT producer failures | Lỗi publish record thất bại | Có đang làm rơi bản ghi do policy sai không? |
| Projection consistency | Đối soát số bản ghi, khóa, trạng thái nghiệp vụ | CDC chạy nhưng dữ liệu đích có đúng không? |
| Error-channel backlog | Lỗi flow bên trong Spring Integration | Có lỗi bị ghi log nhưng không được recover không? |

Gắn alert với **mức ảnh hưởng**, không chỉ tổng số lỗi. Ví dụ một event update thanh toán bị cách ly có thể quan trọng hơn hàng trăm bản ghi analytics có thể tái tạo. Đồng thời cần báo động khi DLT không có người xử lý hoặc xuất hiện nhóm lỗi mới sau triển khai.

## 12. Tình huống thực tế: schema mới làm consumer dừng

Hệ thống đơn hàng đang có:

~~~text
MySQL sales.orders
  -> Debezium MySQL source
  -> Kafka topic shop-cdc.sales.orders
  -> Spring Integration Kafka inbound adapter
  -> orderChangesChannel
  -> orderProjectionHandler
  -> PostgreSQL reporting.orders
~~~

### Diễn biến

1. Đội dữ liệu thêm cột `coupon_code` vào `sales.orders`.
2. Debezium vẫn đọc binlog bình thường và phát row event có field mới.
3. Consumer Spring Integration dùng schema/DTO cũ, không parse được một record.
4. Nếu không có error handler phù hợp, record có thể bị retry liên tục và một Kafka partition ngừng tiến.

### Cách xử lý

**Ở lớp Debezium:** kiểm tra task vẫn RUNNING, topic có record mới và source offset tiếp tục tiến. Nếu đúng, không cần reset source connector để sửa mapper của consumer.

**Ở lớp Spring Kafka:** cấu hình error handler, phân loại lỗi converter/schema là không nên retry quá lâu nếu dữ liệu cố định; cô lập raw record vào DLT với topic/partition/offset và exception. Đối với deserialization failure, cấu hình `ErrorHandlingDeserializer` hoặc cơ chế tương đương để record lỗi được container xử lý.

**Ở lớp Spring Integration:** cập nhật DTO/transformer để chấp nhận event trước và sau DDL. Nếu message đi qua channel bất đồng bộ, xác minh exception có được chuyển tới cơ chế recovery đáng tin cậy.

**Khi redrive:** kiểm tra key đã có event mới hơn hay chưa, dùng idempotency/version nếu cần, kiểm tra projection và chỉ đóng ticket khi dữ liệu đích đúng.

### Phản ví dụ: mất binlog ở nguồn

Nếu Debezium dừng nhiều ngày và MySQL purge binlog cần đọc, Spring consumer DLT hoàn toàn **không đủ** để khôi phục các event chưa bao giờ có trên Kafka. Đây là lỗi tầng source, cần phương án khôi phục/resnapshot và đối soát theo database cùng trạng thái offset thực tế.

## 13. Bài tập thực hành

### Bài 1 — Phân loại lỗi

Hãy chọn phương án xử lý chính cho mỗi sự cố:

| Tình huống | Bạn chọn fail-fast, retry hay DLT/quarantine? |
|---|---|
| A. Debezium MySQL không tìm được binlog chứa offset đã lưu | ? |
| B. Spring Integration outbound HTTP adapter gặp HTTP 503 trong 30 giây | ? |
| C. Một Kafka record có JSON lỗi cú pháp không thay đổi qua các lần retry | ? |
| D. Kafka Connect sink không chuyển đổi được kiểu một record | ? |
| E. Một Kafka tombstone với value null đến sau delete event hợp lệ | ? |

### Bài 2 — Chọn đúng công cụ

Một nhóm đặt các thuộc tính sau trên **Debezium source connector**:

~~~properties
errors.tolerance=all
errors.deadletterqueue.topic.name=debezium-source-errors
~~~

Họ kỳ vọng khi PostgreSQL replication slot bị mất, Debezium sẽ đưa “bản ghi lỗi” vào Kafka topic đó rồi tự động tiếp tục. Giải thích vì sao kỳ vọng này không đúng và cần triển khai cơ chế nào ở tầng nguồn.

### Bài 3 — Redrive có thể làm lùi trạng thái không?

Hai event có cùng Kafka key `{"id":42}`:

- `E1`: `op="u"`, `after.status="PAID"`, bị cô lập vào DLT.
- `E2`: `op="u"`, `after.status="SHIPPED"`, xử lý thành công sau đó.

Nếu gửi `E1` trở lại topic chính và handler dùng UPSERT không có version, projection sẽ thế nào? Đề xuất cách bảo vệ.

<details>
<summary>Gợi ý lời giải</summary>

1. A: dừng/alert, kiểm tra source offset và khả năng khôi phục log; B: retry có giới hạn và backoff, idempotency; C: DLT/quarantine để sửa data/consumer; D: Connect sink DLQ nếu thuộc phạm vi hỗ trợ, giữ record lỗi và metadata; E: xử lý như tombstone hợp lệ theo contract, không phải mặc định đưa DLT.
2. Cấu hình Connect sink DLQ không tái tạo được record chưa được source connector xuất ra, và mất replication slot là lỗi đọc nguồn/offset. Phải kiểm tra slot/WAL, source offset, logs, khả năng resume hoặc resnapshot có đối soát.
3. `E1` có thể ghi đè `SHIPPED` thành `PAID`. Cần version/order phù hợp, cơ chế khóa xử lý theo key, hoặc đối soát trạng thái mới nhất trước redrive; không replay mù một event cũ.

</details>

## 14. Checklist khi triển khai error handling cho CDC

- [ ] Phân định lỗi nằm ở Debezium source, Kafka Connect sink, Kafka consumer hay Spring Integration flow.
- [ ] Xác định rõ các event đặc biệt: `r/c/u/d`, tombstone, heartbeat, schema notification và transaction metadata.
- [ ] Chọn **fail-fast** cho lỗi nguồn có nguy cơ mất dữ liệu; không coi skipped source event là đã được lưu DLT.
- [ ] Nếu dùng Kafka Connect sink DLQ, cấu hình error tolerance, retry, log, topic và context headers đúng connector.
- [ ] Nếu dùng Spring Integration Kafka inbound adapter, cấu hình listener container error handler và recoverer phù hợp.
- [ ] Xử lý deserialization failure trước khi vào channel, bảo toàn raw key/value khi cần.
- [ ] Phân biệt `errorChannel` trong Spring Integration với Kafka DLT vật lý.
- [ ] Dùng retry giới hạn và backoff cho lỗi tạm thời; quy định hành vi với poison pill.
- [ ] Chỉ cho consumer tiến offset theo chính sách đã kiểm chứng sau khi xử lý đích hoặc chuyển DLT thành công.
- [ ] Bảo toàn Kafka topic/partition/offset, key/value và exception context ở DLT; bảo vệ dữ liệu nhạy cảm.
- [ ] Đánh giá thứ tự theo key và idempotency trước khi redrive.
- [ ] Giám sát connector status, source lag, consumer lag, DLQ volume/age và lỗi publish DLT.
- [ ] Kiểm thử crash tại thời điểm ghi đích, trước commit offset, trong lúc publish DLT và khi replay.
- [ ] Có runbook phân công triage, khắc phục, đối soát và đóng record DLQ.

## 15. Tài liệu tham khảo kỹ thuật

- [Debezium MySQL connector — cấu hình xử lý lỗi nguồn](https://debezium.io/documentation/reference/stable/connectors/mysql.html): xem `event.processing.failure.handling.mode`, khả năng log và các yêu cầu phục hồi.
- [Apache Kafka Connect User Guide — Error Reporting](https://kafka.apache.org/44/kafka-connect/user-guide/): phạm vi tolerance, retry, logging và dead-letter queue cho sink connector.
- [Apache Kafka Connect Configs](https://kafka.apache.org/44/configuration/kafka-connect-configs/): cấu hình `errors.*`.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, `ErrorHandlingDeserializer` và recovery/offset handling.
- [Spring Integration Reference — Kafka Support](https://docs.spring.io/spring-integration/reference/kafka.html): inbound adapter và cơ chế kết nối Kafka với `MessageChannel`.

Các ví dụ cấu hình trong bài nhằm giải thích cơ chế, cần đối chiếu **phiên bản Debezium, Kafka Connect, Spring Kafka và Spring Integration đang dùng** trước khi áp dụng.

**Ghi nhớ:** Lỗi source Debezium, lỗi Kafka Connect sink và lỗi downstream Spring Integration có **biên phục hồi khác nhau**. Dead-letter lưu record đã có và chưa được xử lý theo chính sách; nó không phục hồi transaction log đã mất, không tự giữ đúng thứ tự nghiệp vụ và cũng không đảm bảo exactly-once. Một pipeline CDC đáng tin cậy cần xử lý lỗi đúng tầng, giữ checkpoint hợp lệ, retry có giới hạn, DLT bền vững, redrive có đối soát và xử lý idempotent.
