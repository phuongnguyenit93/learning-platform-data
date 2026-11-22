## Mục tiêu

Trong một consumer Kafka, có những bản ghi không thể xử lý thành công dù listener đã thử lại nhiều lần. Nếu chỉ ghi log rồi bỏ qua, hệ thống sẽ mất dấu sự kiện lỗi; nếu để consumer dừng mãi tại bản ghi đó, các sự kiện phía sau trên cùng partition cũng bị chặn. Dead-letter topic (DLT) cung cấp một nơi lưu riêng những bản ghi đã vượt quá chính sách retry để đội vận hành có thể điều tra và quyết định xử lý lại.

Spring Kafka cung cấp **DeadLetterPublishingRecoverer** để xuất bản ghi đã phục hồi lỗi sang DLT. Thành phần này thường được kết hợp với **DefaultErrorHandler** trong consumer không dùng transaction. Bài học này giải thích cách hai thành phần phối hợp, cách đặt tên và phân vùng DLT, cách cấu hình retry, cũng như cách theo dõi và phát lại bản ghi lỗi.

## 1. Luồng xử lý lỗi và vai trò của Recoverer

Một luồng xử lý record listener điển hình gồm các bước:

1. Consumer poll bản ghi từ topic nguồn, ví dụ **orders**.
2. Listener gọi nghiệp vụ để xác thực hoặc xử lý sự kiện.
3. Nếu listener ném exception, **DefaultErrorHandler** áp dụng chính sách retry đã cấu hình.
4. Khi hết số lần retry, error handler gọi recoverer.
5. **DeadLetterPublishingRecoverer** tạo bản ghi đích và gửi nó bằng **KafkaTemplate** tới DLT.
6. Khi việc phục hồi được xem là thành công, container tiếp tục xử lý theo offset và chính sách commit đã cấu hình.

**DefaultErrorHandler** quyết định **khi nào** dừng retry và chuyển sang phục hồi. **DeadLetterPublishingRecoverer** quyết định **gửi bản ghi lỗi đi đâu và gửi như thế nào**. Việc tách hai trách nhiệm này giúp thay đổi retry policy mà không phải viết lại logic định tuyến DLT.

Với cấu hình mặc định phổ biến, tên DLT được tạo bằng cách nối hậu tố **.DLT** vào tên topic nguồn và giữ nguyên số partition của bản ghi. Ví dụ, bản ghi ở **orders**, partition 2 được chuyển tới **orders.DLT**, partition 2. Vì vậy, nếu giữ định tuyến mặc định, DLT cần có ít nhất số partition bằng topic nguồn.

DLT không tự sửa dữ liệu và cũng không tự chạy lại nghiệp vụ. Nó lưu lại bản ghi cùng metadata phục vụ điều tra. Việc sửa dữ liệu, phát lại hoặc đưa bản ghi sang luồng xử lý khác là một quyết định vận hành riêng.

## 2. Cấu hình DeadLetterPublishingRecoverer

Recoverer cần một **KafkaTemplate** có serializer tương thích với dữ liệu mà consumer nhận. Ví dụ dưới đây dùng key và value dạng chuỗi; trong ứng dụng dùng JSON hoặc Avro, hãy cấu hình producer factory và serializer tương ứng.

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;

@Configuration
public class DeadLetterConfig {

    @Bean
    DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
            KafkaTemplate<String, String> kafkaTemplate) {

        return new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                (record, exception) -> new TopicPartition(
                        record.topic() + ".DLT",
                        record.partition()));
    }
}
~~~

Constructor nhận một hàm định tuyến với đầu vào là record gốc và exception gây lỗi. Hàm trả về **TopicPartition** đích. Đoạn mã trên thể hiện rõ quy tắc topic nguồn cộng hậu tố **.DLT**, đồng thời giữ partition ban đầu. Nếu không cần tự định tuyến, có thể dùng constructor chỉ nhận **KafkaTemplate** để áp dụng quy tắc mặc định của Spring Kafka.

Có thể định tuyến theo loại lỗi hoặc theo topic nghiệp vụ:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                (record, exception) -> {
                    String destination = exception instanceof InvalidOrderException
                            ? "orders.invalid.DLT"
                            : record.topic() + ".DLT";

                    return new TopicPartition(destination, record.partition());
                });
~~~

Khi dùng nhiều DLT, hãy đặt quy tắc tên nhất quán và bảo đảm topic đích đã được tạo. Nếu muốn Kafka tự chọn partition, có thể dùng partition âm trong **TopicPartition** theo hành vi được hỗ trợ bởi phiên bản Spring Kafka đang chạy; cần kiểm thử cách phân phối thực tế trước khi áp dụng. Khi cần giữ thứ tự tương đối theo partition nguồn, hãy giữ nguyên partition và tạo DLT có đủ partition tương ứng.

Recoverer cũng bổ sung các header mô tả nguồn gốc và exception. Các header thường dùng gồm topic, partition, offset gốc và thông tin exception như tên lớp, message, stack trace. Consumer đọc DLT có thể dùng chúng để tìm lại bản ghi nguồn và hiểu nguyên nhân thất bại. Không nên đưa bí mật, token hoặc dữ liệu cá nhân nhạy cảm vào exception message hay log.

## 3. Kết hợp với DefaultErrorHandler

Trong record listener không dùng transaction, **DefaultErrorHandler** là điểm cấu hình retry và recoverer. Ví dụ sau thực hiện lần giao nhận đầu tiên, sau đó retry tối đa hai lần với khoảng nghỉ một giây. Lỗi dữ liệu không hợp lệ được phân loại là không retry, nên được chuyển sang DLT ngay sau lần xử lý thất bại đầu tiên.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;
import org.apache.kafka.common.TopicPartition;

@Configuration
public class KafkaErrorHandlerConfig {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<String, String> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(
                        kafkaTemplate,
                        (record, exception) -> new TopicPartition(
                                record.topic() + ".DLT",
                                record.partition()));

        // Cho phép error handler nhận biết lỗi gửi DLT qua send result.
        recoverer.setFailIfSendResultIsError(true);

        // Hai lần retry sau lần xử lý đầu tiên, mỗi lần cách nhau 1 giây.
        DefaultErrorHandler handler =
                new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 2L));

        handler.addNotRetryableExceptions(InvalidOrderException.class);
        return handler;
    }
}
~~~

Để áp dụng handler cho listener container, gắn nó vào **ConcurrentKafkaListenerContainerFactory** mà ứng dụng sử dụng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;

@Bean
ConcurrentKafkaListenerContainerFactory<String, String> kafkaListenerContainerFactory(
        ConsumerFactory<String, String> consumerFactory,
        DefaultErrorHandler kafkaErrorHandler) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
~~~

Nếu ứng dụng dùng Spring Boot, hãy bảo đảm listener thực sự dùng factory này; có thể cấu hình factory mặc định hoặc chỉ định tên factory trên **@KafkaListener**. Khi tự tạo factory, cần giữ lại các thiết lập khác mà ứng dụng cần như concurrency, ack mode, record interceptor và consumer properties.

Listener có thể giữ nguyên cách ném exception khi nghiệp vụ thất bại:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @KafkaListener(
            topics = "orders",
            groupId = "order-service",
            containerFactory = "kafkaListenerContainerFactory")
    public void consume(ConsumerRecord<String, String> record) {
        validateAndProcess(record.value());
    }

    private void validateAndProcess(String payload) {
        if (payload == null || payload.isBlank()) {
            throw new InvalidOrderException("Order payload is empty");
        }

        // Gọi nghiệp vụ xử lý đơn hàng tại đây.
    }
}
~~~

Ví dụ minh họa giả định **InvalidOrderException** là exception do ứng dụng định nghĩa. Trong dự án thực tế, hãy phân loại exception theo khả năng phục hồi:

| Nhóm lỗi | Ví dụ | Hướng xử lý thường dùng |
|---|---|---|
| Tạm thời | Timeout dịch vụ phụ thuộc, lỗi kết nối ngắn hạn | Retry có giới hạn và backoff |
| Dữ liệu không hợp lệ | Thiếu trường bắt buộc, sai định dạng | Không retry hoặc retry rất ít, sau đó chuyển DLT |
| Lỗi cấu hình hoặc quyền | Sai ACL, serializer không tương thích | Cảnh báo và sửa cấu hình; retry liên tục thường không giúp ích |
| Lỗi nghiệp vụ cần can thiệp | Trạng thái đơn hàng không cho phép chuyển tiếp | Chuyển DLT hoặc luồng xử lý thủ công theo quy tắc nghiệp vụ |

Không nên retry vô hạn. Một lỗi không thể tự hết sẽ giữ consumer tại cùng record và làm chậm các record phía sau trên partition đó. Ngược lại, retry quá ngắn với lỗi phụ thuộc tạm thời có thể đẩy nhiều record hợp lệ sang DLT. Hãy chọn số lần retry và khoảng nghỉ dựa trên đặc tính dịch vụ phụ thuộc, thời gian xử lý cho phép và yêu cầu độ trễ.

**setFailIfSendResultIsError(true)** yêu cầu recoverer báo lỗi khi kết quả gửi DLT thất bại. Điều này giúp tránh coi một lần publish DLT không thành công là phục hồi hoàn tất. Hãy kiểm tra API và hành vi send result trên phiên bản Spring Kafka của dự án; các tùy chọn timeout và xử lý send result có thể khác nhau giữa các phiên bản.

## 4. Tạo và cấu hình dead-letter topic

DLT là một Kafka topic bình thường, vì vậy cần được cấp phát và vận hành như các topic khác. Có thể khai báo topic bằng **KafkaAdmin**/**NewTopic** trong ứng dụng hoặc quản lý bằng công cụ hạ tầng:

~~~java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.TopicBuilder;

@Bean
NewTopic ordersDeadLetterTopic() {
    return TopicBuilder.name("orders.DLT")
            .partitions(6)
            .replicas(3)
            .build();
}
~~~

Số partition và replication factor trong ví dụ chỉ là giá trị minh họa. Nếu recoverer giữ partition nguồn, DLT phải có partition tương ứng với mọi partition nguồn có thể phát sinh lỗi. Replication factor phải phù hợp với số broker và chính sách độ bền của cụm. Trong môi trường production, nên tạo topic bằng quy trình quản lý hạ tầng thống nhất thay vì phụ thuộc vào auto-create topic.

Khi thiết kế DLT, cần xác định:

- **Retention:** giữ bản ghi đủ lâu để điều tra và khắc phục, nhưng có giới hạn để tránh tăng dung lượng vô hạn. Chọn **retention.ms** và **retention.bytes** theo tốc độ phát sinh lỗi, dung lượng record và thời gian phản hồi sự cố.
- **Replication và phân vùng:** chọn replication factor, **min.insync.replicas** và số partition phù hợp với mức sẵn sàng mong muốn. Kiểm tra cấu hình producer **acks** tương ứng.
- **Quyền truy cập:** consumer nghiệp vụ thường chỉ cần quyền đọc topic nguồn; chỉ service vận hành hoặc quy trình replay được cấp quyền đọc DLT. Producer của recoverer cần quyền ghi DLT.
- **Mã hóa và dữ liệu nhạy cảm:** áp dụng cùng chính sách bảo vệ dữ liệu như topic nguồn. DLT có thể chứa payload chưa xử lý được và thông tin exception.
- **Quy trình phát lại:** xác định ai được replay, replay vào topic nào, cách kiểm soát tốc độ và cách tránh xử lý trùng.

Không mặc định bật log compaction cho mọi DLT. DLT thường lưu từng lần thất bại để phục vụ điều tra; compaction có thể loại bỏ các record cũ có cùng key và làm mất lịch sử cần thiết. Chỉ bật compaction khi mô hình dữ liệu và yêu cầu lưu trữ đã được phân tích rõ.

## 5. Đọc DLT, điều tra và phát lại

Một consumer giám sát DLT có thể ghi nhận metadata để tạo cảnh báo hoặc đưa record vào giao diện vận hành. Ví dụ:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class DeadLetterListener {

    @KafkaListener(topics = "orders.DLT", groupId = "orders-dlt-inspector")
    public void inspect(
            ConsumerRecord<String, String> record,
            @Header(KafkaHeaders.DLT_EXCEPTION_MESSAGE) String errorMessage) {

        // Ghi nhận topic/partition/offset gốc và mã tương quan.
        // Đưa thông tin vào quy trình điều tra; không tự động replay tại đây.
        System.out.printf(
                "DLT record key=%s, source=%s, dltPartition=%d, dltOffset=%d, error=%s%n",
                record.key(),
                new String(record.headers()
                        .lastHeader(KafkaHeaders.DLT_ORIGINAL_TOPIC).value()),
                record.partition(),
                record.offset(),
                errorMessage);
    }
}
~~~

Đoạn code trên minh họa việc đọc header; khi triển khai, hãy kiểm tra header có tồn tại trước khi truy cập và chuyển giá trị header byte[] thành chuỗi phù hợp. Dùng header partition/offset gốc để đối chiếu. **record.partition()** và **record.offset()** trong consumer DLT là vị trí của record trong DLT, không phải vị trí của record trong topic nguồn.

Quy trình xử lý DLT nên có các bước rõ ràng:

1. Xác định nguyên nhân từ exception header, payload và log có correlation ID.
2. Phân loại lỗi do dữ liệu, do dependency, do cấu hình hay do lỗi nghiệp vụ.
3. Khắc phục nguyên nhân; nếu cần, sửa dữ liệu bằng một quy trình có audit.
4. Chọn cách xử lý: phát lại vào topic nguồn, gửi sang topic phục hồi riêng hoặc xử lý thủ công.
5. Ghi nhận người thực hiện, thời điểm, số lượng record và kết quả replay.

Replay có thể khiến nghiệp vụ chạy lần thứ hai. Consumer vì thế nên có tính idempotent, chẳng hạn lưu event ID đã xử lý, dùng unique constraint hoặc kiểm tra trạng thái nghiệp vụ trước khi ghi. Nếu gửi lại vào topic nguồn, cần cân nhắc thứ tự: một sự kiện cũ được replay sau các sự kiện mới có thể làm trạng thái bị lùi nếu nghiệp vụ không kiểm soát version hoặc sequence.

Không nên tự động đọc DLT rồi gửi lại ngay vào topic nguồn theo vòng lặp không giới hạn. Khi nguyên nhân chưa được sửa, cách làm này tạo vòng lặp lỗi, tăng tải và làm khó việc điều tra. Nếu cần replay hàng loạt, hãy giới hạn tốc độ, chia batch, hỗ trợ dry run và lưu lại kết quả từng batch.

## 6. Partition, ordering và ảnh hưởng tới consumer group

Kafka chỉ đảm bảo thứ tự trong một partition. Khi record lỗi được retry, consumer có thể phải chờ xử lý lại record đó trước khi tiếp tục tiến lên trên partition. Điều này giúp giữ thứ tự xử lý trong partition nhưng làm giảm thông lượng nếu một record liên tục thất bại.

Khi record được chuyển sang DLT, consumer nguồn có thể tiếp tục xử lý các record tiếp theo sau khi recover thành công. Lúc đó, một sự kiện cũ nằm trong DLT trong khi sự kiện mới hơn đã được xử lý. Nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt, cần có chiến lược replay theo partition và offset, hoặc thiết kế nghiệp vụ dựa trên sequence/version để từ chối cập nhật cũ.

Giữ nguyên partition khi định tuyến sang DLT giúp truy vết và replay theo partition dễ hơn, nhưng không tự bảo đảm thứ tự nghiệp vụ sau khi phát lại. Nếu chọn partition khác hoặc để broker phân phối, cần lưu rõ thông tin partition và offset nguồn trong header để không mất khả năng đối chiếu.

Đối với batch listener, cách xử lý khác record listener: error handler cần biết record nào trong batch thất bại. Có thể sử dụng **BatchListenerFailedException** để chỉ ra vị trí lỗi; nếu không xác định được record lỗi, cả batch có thể bị retry hoặc xử lý lại tùy cấu hình. Hãy thiết kế và kiểm thử riêng cho batch listener thay vì sao chép nguyên cấu hình record listener.

## 7. Trường hợp sử dụng Kafka transaction

Ví dụ **DefaultErrorHandler** ở trên phù hợp với luồng listener không dùng transaction. Nếu container dùng Kafka transaction, exception thường làm transaction hiện tại rollback. Khi đó, cần thiết kế bước retry và phục hồi theo transaction flow của Spring Kafka, thường sử dụng **DefaultAfterRollbackProcessor** cùng **DeadLetterPublishingRecoverer**.

Trong mô hình này, cần cấu hình việc publish DLT và commit offset đã phục hồi trong transaction phù hợp. Nếu publish DLT không thành công, offset nguồn không được coi là đã phục hồi thành công. Hãy dùng transactional **KafkaTemplate** và cấu hình **commitRecovered**/template theo hướng dẫn của đúng phiên bản Spring Kafka, sau đó kiểm thử cả trường hợp broker lỗi giữa lúc publish DLT và commit offset. Không trộn cấu hình transactional này với ví dụ non-transactional mà chưa xác định rõ ranh giới transaction.

## 8. Kiểm thử và giám sát

Một bài kiểm thử tích hợp nên xác nhận cả kết quả nghiệp vụ lẫn trạng thái Kafka:

- Gửi một record hợp lệ và xác nhận listener xử lý đúng, không xuất hiện trong DLT.
- Gửi một record gây lỗi tạm thời; xác nhận số lần gọi listener và khoảng retry theo cấu hình.
- Gửi một record thuộc nhóm không retry; xác nhận record được chuyển DLT sau lần xử lý đầu tiên.
- Kiểm tra key, value, header nguồn gốc, tên topic và partition đích của record DLT.
- Làm cho việc publish DLT thất bại (ví dụ thiếu quyền ghi hoặc topic không tồn tại) và xác nhận lỗi được báo ra, không bị coi là phục hồi thành công.
- Phát lại một record đã khắc phục và xác nhận nghiệp vụ idempotent, không tạo tác dụng phụ trùng lặp.

Có thể dùng Embedded Kafka trong kiểm thử Spring Kafka hoặc Kafka Testcontainers để kiểm tra hành vi với broker thật. Với kiểm thử retry, nên dùng backoff ngắn có kiểm soát và tránh phụ thuộc vào thời gian chờ dài, dễ gây flaky test.

Trong production, theo dõi ít nhất:

| Tín hiệu | Điều cần phát hiện |
|---|---|
| Số record và tốc độ tăng của DLT | Lỗi mới xuất hiện hoặc tăng đột biến |
| Tỷ lệ retry và recover | Dependency chập chờn hoặc dữ liệu đầu vào lỗi |
| Lỗi gửi DLT | Thiếu topic, ACL, quota, serializer hoặc broker không sẵn sàng |
| Consumer lag của topic nguồn | Retry kéo dài hoặc consumer không theo kịp |
| Tuổi của record cũ nhất trong DLT | Sự cố tồn đọng chưa được điều tra |
| Dung lượng và retention DLT | Nguy cơ hết dung lượng hoặc mất dữ liệu trước khi xử lý |

Đặt ngưỡng cảnh báo dựa trên baseline của hệ thống. Một record DLT có thể chấp nhận được trong một số nghiệp vụ, nhưng tốc độ tăng cao hoặc record tồn đọng quá lâu thường cần người xử lý. Log nên có event ID, topic nguồn, partition, offset và correlation ID; tránh log toàn bộ payload nếu payload có dữ liệu nhạy cảm.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không thấy record trong DLT | Recoverer chưa được gắn vào listener container, listener dùng factory khác hoặc chưa hết retry | Kiểm tra factory thực tế, log error handler và retry policy |
| Publish DLT lỗi Invalid partition | DLT có ít partition hơn partition nguồn được giữ nguyên | Tăng số partition DLT hoặc thay đổi resolver có chủ đích |
| Publish DLT bị từ chối | ACL thiếu quyền ghi, topic chưa tồn tại hoặc cluster lỗi | Kiểm tra producer log, quyền và trạng thái topic |
| Record lặp lại lâu trên topic nguồn | Exception được retry, hoặc publish DLT không thành công | Kiểm tra exception gốc và send result của recoverer |
| DLT tăng nhanh dù dependency đã phục hồi | Retry policy quá ngắn, exception bị phân loại không retry hoặc lỗi dữ liệu hàng loạt | Kiểm tra phân loại exception và thời điểm phát sinh |
| Replay làm dữ liệu nghiệp vụ sai | Xử lý trùng hoặc sự kiện cũ đến sau sự kiện mới | Kiểm tra idempotency, event ID và sequence/version |

Khi nâng cấp Spring Kafka, hãy kiểm tra thay đổi API của error handler, cách xử lý send result, header DLT và cấu hình transaction. Tài liệu của phiên bản đang dùng là nguồn quyết định cho các thuộc tính và constructor có sẵn.

## 10. Nguyên tắc triển khai

Một cấu hình DLT đáng tin cậy cần có retry hữu hạn, phân loại lỗi hợp lý, topic đích được cấp phát trước, quyền ghi/đọc rõ ràng và cảnh báo khi record tồn đọng. Recoverer phải báo được lỗi publish để offset nguồn không bị coi là đã xử lý khi bản ghi chưa được lưu an toàn vào DLT.

Hãy coi DLT là một phần của quy trình vận hành sự kiện: mỗi record phải truy vết được về nguồn, có người hoặc quy trình chịu trách nhiệm điều tra, có chính sách retention và có cách replay được kiểm soát. Khi kết hợp các yếu tố đó với consumer idempotent và quy tắc ordering rõ ràng, **DeadLetterPublishingRecoverer** giúp hệ thống Kafka cô lập lỗi mà vẫn giữ được khả năng phục hồi dữ liệu.
