# Strip exception headers

Trong Spring Kafka, một record không xử lý được thường được chuyển sang **dead-letter topic (DLT)** để điều tra, sửa lỗi hoặc phát lại. Khi ghi record sang DLT, Spring Kafka có thể bổ sung các Kafka header mô tả exception, topic/partition/offset nguồn và thông tin cần cho recovery. Các header này rất hữu ích trong lần thất bại đầu tiên, nhưng có thể trở thành gánh nặng nếu record liên tục đi qua các luồng retry, DLT và re-drive.

**Strip exception headers** là cơ chế loại bỏ các header mô tả exception của **những lần thất bại trước đó** khi DeadLetterPublishingRecoverer chuẩn bị xuất bản record lỗi thêm một lần nữa. Mục tiêu là tránh tích lũy stack trace và thông báo lỗi qua mỗi chặng, đồng thời giữ bộ thông tin exception phù hợp với lần xử lý hiện tại.

Trong Spring Kafka, thuộc tính thường được nhắc tới là **stripPreviousExceptionHeaders** của DeadLetterPublishingRecoverer. Cần phân biệt nó với **appendOriginalHeaders**, với header do ứng dụng tự thêm, và với cách xử lý payload bị lỗi deserialize. Việc tách các khái niệm này giúp tránh xóa nhầm metadata cần cho recovery.

## 1. Header của Kafka là gì?

Mỗi Kafka record có topic, partition, offset, timestamp, key, value và một tập **Headers**. Header là các cặp tên/giá trị; giá trị được lưu dưới dạng byte array. Một record có thể chứa nhiều header cùng tên.

Ví dụ record nghiệp vụ:

    Topic: orders
    Partition: 2
    Offset: 418
    Key: order-123
    Value: {"eventId":"evt-001","type":"OrderCreated",...}

    Headers:
      event-id = evt-001
      trace-id = trace-abc
      schema-version = 3

Khi listener xử lý thất bại và recoverer phát record sang orders.DLT, record DLT có thể chứa thêm các header:

    kafka_dlt-original-topic = orders
    kafka_dlt-original-partition = 2
    kafka_dlt-original-offset = 418
    kafka_dlt-exception-fqcn = ...
    kafka_dlt-exception-message = ...
    kafka_dlt-exception-stacktrace = ...

Tên thực tế và tập header được thêm phụ thuộc phiên bản Spring Kafka và loại lỗi. Nên dùng các hằng số trong KafkaHeaders thay vì tự ghép chuỗi tên header trong code.

Vì Kafka Headers có thể chứa nhiều giá trị cùng tên, một công cụ đọc chỉ gọi lastHeader() có thể không cho thấy toàn bộ lịch sử header. Khi điều tra sự cố header tăng kích thước, nên kiểm tra cả danh sách headers() theo tên và tổng kích thước header.

## 2. Các nhóm header cần phân biệt

| Nhóm | Ví dụ | Mục đích |
|---|---|---|
| Header nghiệp vụ | event-id, tenant-id, schema-version | Định danh và diễn giải sự kiện |
| Header tracing | trace-id, correlation-id | Liên kết log qua nhiều service |
| Header nguồn DLT | DLT_ORIGINAL_TOPIC, DLT_ORIGINAL_PARTITION, DLT_ORIGINAL_OFFSET | Truy lại nơi phát sinh record |
| Header exception DLT | DLT_EXCEPTION_FQCN, DLT_EXCEPTION_MESSAGE, DLT_EXCEPTION_STACKTRACE | Chẩn đoán nguyên nhân thất bại |
| Header của deserializer | Thông tin DeserializationException do ErrorHandlingDeserializer thêm | Mô tả lỗi xảy ra trước listener |
| Header retry riêng | attempt, retry-stage, first-failed-at | Theo dõi chính sách retry của ứng dụng |

Các tên viết hoa trong bảng là cách gọi các hằng số thuộc KafkaHeaders; wire name thực tế là chuỗi header Kafka tương ứng.

**Strip exception headers** nhắm tới nhóm header exception DLT cũ mà recoverer quản lý. Nó không có nghĩa là xóa mọi header, không tự xóa event-id/trace-id, và không thay thế chính sách giữ lại metadata nguồn.

Nếu ứng dụng tự thêm một header mang stack trace dưới tên riêng, ví dụ x-error-trace, cơ chế mặc định không thể suy luận rằng đây cũng là header exception cần loại bỏ. Muốn kiểm soát header tự định nghĩa, cần một chính sách tùy chỉnh.

## 3. Vì sao exception headers có thể tích lũy?

Hãy xét quy trình recovery nhiều chặng:

    orders
      |
      | Listener thất bại: DatabaseTimeout
      v
    orders.DLT
      |
      | Nhân viên sửa dependency và re-drive
      v
    orders.replay
      |
      | Listener thất bại lần nữa: ValidationError
      v
    orders.replay.DLT

Nếu re-drive giữ toàn bộ header cũ và recoverer ở lần thất bại thứ hai tiếp tục bổ sung header exception mới, record sau cùng có thể mang cả thông tin lỗi DatabaseTimeout lẫn ValidationError.

Điều này dẫn tới một số vấn đề:

- Header stack trace thường dài, có thể tăng đáng kể kích thước record sau nhiều lần chuyển DLT.
- Công cụ phân tích có thể đọc nhầm exception cũ thành nguyên nhân hiện tại.
- Header chứa chi tiết nội bộ về class, đường gọi hàm hoặc thông điệp lỗi không nên phát tán quá nhiều.
- Tăng kích thước record làm tăng băng thông, lưu trữ và chi phí deserialize.
- Trong trường hợp xấu, kích thước record vượt giới hạn producer/broker và chính việc gửi DLT cũng thất bại.

Với một sự kiện có thể được phát lại nhiều lần, cần xác định rõ liệu hệ thống chỉ cần trạng thái lỗi **mới nhất** hay cần **lịch sử đầy đủ** của mọi lần thất bại. Nếu cần lịch sử, thường nên lưu nó trong một hệ thống điều tra hoặc một cấu trúc audit có giới hạn thay vì liên tục nối stack trace vào Kafka headers.

## 4. stripPreviousExceptionHeaders làm gì?

DeadLetterPublishingRecoverer hỗ trợ cấu hình:

~~~java
recoverer.setStripPreviousExceptionHeaders(true);
~~~

Khi bật, recoverer loại bỏ các exception header thuộc những lần recover trước đó mà nó nhận diện, rồi xây dựng thông tin exception cho lần recover hiện tại theo chính sách đang dùng.

Điểm quan trọng:

1. Nó tác động trong quá trình **recoverer chuẩn bị record để publish** sang DLT.
2. Nó xử lý các **exception header trước đó**, không mặc định xóa tất cả Kafka headers.
3. Nó không phải một hàm tự chạy trên mọi record đi qua Kafka.
4. Nó không xóa log/exception đã được ghi ở nơi khác.
5. Nó không ngăn code khác thêm lại header cũ sau khi recoverer tạo record.

Spring Kafka ở các dòng phiên bản hỗ trợ tùy chọn này thường bật việc strip exception header cũ theo mặc định. Tuy nhiên, hành vi mặc định, nhóm header được nhận diện và khả năng tùy chỉnh đã thay đổi theo các phiên bản. Hãy kiểm tra Javadoc của DeadLetterPublishingRecoverer đúng phiên bản đang chạy và cấu hình tường minh nếu đây là một yêu cầu vận hành.

Ví dụ so sánh:

| Trạng thái | Header exception trong DLT mới |
|---|---|
| Không strip các header cũ | Có thể giữ exception của chặng trước và bổ sung exception của chặng hiện tại |
| Strip các header cũ | Các exception header cũ do recoverer nhận diện bị loại bỏ; thông tin lỗi hiện tại được tạo mới |
| Tự xóa toàn bộ headers | Có thể mất event-id, tracing, nguồn DLT và metadata cần cho recovery |

Cấu hình strip phù hợp với mục tiêu hiển thị nguyên nhân mới nhất, nhưng không phải cơ chế lưu lịch sử. Nếu đội vận hành cần theo dõi nhiều lần re-drive, có thể tạo audit record chứa eventId, thời điểm, topic nguồn/đích và exception class, kèm giới hạn retention rõ ràng.

## 5. Cấu hình DefaultErrorHandler và DeadLetterPublishingRecoverer

Ví dụ dưới đây dùng Java Configuration trong Spring Kafka 3.x. Listener lỗi sẽ retry hai lần sau lần xử lý ban đầu; nếu vẫn thất bại, recoverer sẽ gửi record sang DLT.

~~~java
@Configuration
public class KafkaRecoveryConfiguration {

    @Bean
    CommonErrorHandler commonErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        // Không giữ exception headers từ những lần recover trước.
        recoverer.setStripPreviousExceptionHeaders(true);

        // Giữ logic metadata nguồn gốc theo lựa chọn riêng.
        recoverer.setAppendOriginalHeaders(false);

        DefaultErrorHandler handler = new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L)
        );

        handler.addNotRetryableExceptions(
                IllegalArgumentException.class
        );

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    kafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            CommonErrorHandler commonErrorHandler) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(commonErrorHandler);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
~~~

Các import chính:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;
~~~

OrderEvent là kiểu sự kiện của ứng dụng, cần tự định nghĩa. KafkaTemplate phải có producer serializer phù hợp với key/value thực tế khi gửi sang DLT. Ví dụ tập trung vào phần cấu hình error handler, chưa bao gồm khai báo topic hay toàn bộ Spring Boot application.

Trong ứng dụng có nhiều listener container factory, phải bảo đảm factory mà @KafkaListener dùng thực sự gọi setCommonErrorHandler(). Chỉ tạo bean recoverer nhưng không nối nó vào container sẽ không làm thay đổi hành vi của listener tương ứng.

## 6. Khác biệt giữa stripPreviousExceptionHeaders và appendOriginalHeaders

Hai thuộc tính này điều khiển hai nhóm metadata khác nhau.

**stripPreviousExceptionHeaders** quyết định có bỏ các exception header DLT từ những lần recover trước.

**appendOriginalHeaders** quyết định có tiếp tục thêm các header mô tả nguồn gốc record khi record lại được chuyển sang DLT, kể cả khi header nguồn đã tồn tại từ một lần trước.

Ví dụ:

    orders partition=2 offset=418
        |
        v
    orders.DLT partition=2 offset=57
        |
        | re-drive, giữ headers
        v
    orders.replay partition=0 offset=19
        |
        v
    orders.replay.DLT

Ở chặng cuối, hệ thống có thể cần biết cả vị trí ban đầu tại orders và vị trí replay. Nếu appendOriginalHeaders được bật, các header nguồn có thể được bổ sung ở nhiều chặng. Nếu tắt, chính sách của recoverer ưu tiên giữ thông tin nguồn đã có theo quy tắc của phiên bản đang dùng.

Một bảng phân biệt:

| Tùy chọn | Nhóm thông tin | Câu hỏi mà nó giải quyết |
|---|---|---|
| stripPreviousExceptionHeaders | Exception của những lần recover trước | Có giữ các lỗi cũ trong DLT mới không? |
| appendOriginalHeaders | Topic/partition/offset nguồn | Có bổ sung chuỗi metadata nguồn khi đi qua nhiều DLT không? |
| HeadersFunction / custom headers | Header do ứng dụng tạo | Cần thêm marker, correlation hoặc thông tin audit nào? |

Không nên bật appendOriginalHeaders chỉ để giữ lịch sử exception; thuộc tính đó không phục vụ mục đích này. Tương tự, tắt stripPreviousExceptionHeaders không tự bảo đảm bạn có một audit trail đầy đủ và đáng tin cậy, vì record có thể được tái tạo bởi một producer khác với tập header không giống ban đầu.

## 7. Một vòng đời recovery minh họa

Giả sử record đầu tiên có eventId evt-001.

**Lần thất bại thứ nhất:** listener orders gặp DatabaseTimeoutException. Recoverer xuất bản sang orders.DLT với metadata nguồn và exception hiện tại.

    event-id: evt-001
    DLT_ORIGINAL_TOPIC: orders
    DLT_ORIGINAL_PARTITION: 2
    DLT_ORIGINAL_OFFSET: 418
    DLT_EXCEPTION_FQCN: DatabaseTimeoutException
    DLT_EXCEPTION_MESSAGE: database unavailable
    DLT_EXCEPTION_STACKTRACE: ...first trace...

**Re-drive:** một tiến trình đọc orders.DLT, sửa dữ liệu và gửi lại tới orders.replay. Tiến trình này có thể giữ hoặc chủ động chọn những header cần thiết. Lần replay thất bại vì một ValidationException khác.

**Lần thất bại thứ hai với strip bật:** recoverer bỏ exception header cũ mà nó nhận diện, sau đó ghi thông tin lỗi ValidationException của lần xử lý hiện tại:

    event-id: evt-001
    DLT_ORIGINAL_TOPIC: orders
    ...
    DLT_EXCEPTION_FQCN: ValidationException
    DLT_EXCEPTION_MESSAGE: invalid state transition
    DLT_EXCEPTION_STACKTRACE: ...second trace...

Ví dụ thể hiện mục đích của cấu hình; không phải cam kết rằng mọi DLT record chỉ có một header exception. Header cho lỗi deserialize key/value, nội dung custom hoặc hành vi của version đang dùng có thể làm tập header khác đi.

Nếu mục tiêu nghiệp vụ là lưu lịch sử cả hai lỗi, hãy ghi một sự kiện audit riêng với eventId, attempt/replayId và exception class. Khi cần stack trace chi tiết, lưu theo thời gian giữ dữ liệu được kiểm soát trong hệ thống log hoặc incident management.

## 8. Header do ứng dụng thêm và cơ chế tùy chỉnh

Các producer và consumer có thể tự thêm header:

~~~java
record.headers().add(
    "event-id",
    eventId.getBytes(StandardCharsets.UTF_8)
);
~~~

Header này không tự động bị nhận diện là exception header của DeadLetterPublishingRecoverer. Nếu ứng dụng dùng tên như x-last-error hoặc x-retry-stacktrace, cần quản lý vòng đời của chúng riêng.

Có thể bổ sung header thông qua headers function của recoverer ở những phiên bản hỗ trợ API addHeadersFunction():

~~~java
recoverer.addHeadersFunction((record, exception) -> {
    Headers additional = new RecordHeaders();
    additional.add(
        "x-recovery-stage",
        "orders-consumer".getBytes(StandardCharsets.UTF_8)
    );
    return additional;
});
~~~

Các import liên quan:

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.Headers;
import org.apache.kafka.common.header.internals.RecordHeaders;
~~~

Mục đích của function trên là bổ sung marker để điều tra, không phải ghi lại stack trace mới ở mỗi chặng. Nếu cần thay thế một custom header cùng tên, hãy kiểm tra API hỗ trợ thay thế thay vì mặc định add() vì Kafka cho phép nhiều header trùng tên.

Một số phiên bản Spring Kafka hỗ trợ cơ chế như ExceptionHeadersCreator hoặc khả năng chỉ định tập exception headers được tạo. Những API này cho phép kiểm soát chi tiết hơn việc xuất bản class, message hoặc stack trace, nhưng tên và chữ ký phương thức có thể phụ thuộc phiên bản. Khi cần dùng, đối chiếu Javadoc với dependency của dự án trước khi cấu hình.

## 9. Có nên giữ DLT_EXCEPTION_STACKTRACE?

Stack trace rất hữu ích để điều tra lỗi code hoặc cách listener gọi dependency. Nhưng nó cũng thường là header lớn nhất, chứa tên package, method, dòng code và thông tin triển khai.

Có thể phân cấp lượng thông tin cần lưu:

| Mức | Thông tin giữ lại | Phù hợp |
|---|---|---|
| Tối thiểu | exception class, eventId, nguồn và timestamp | Luồng dữ liệu lớn, điều tra bằng log tập trung |
| Vừa phải | exception class, message, nguồn, correlation ID | Cần xem trực tiếp trong DLT |
| Chi tiết | stack trace và cause chain | DLT lưu lượng thấp, cần chẩn đoán sâu |
| Lịch sử nhiều lần | Audit ngoài Kafka headers với replayId và failure attempt | Quy trình re-drive nhiều chặng |

Nếu message hoặc stack trace có dữ liệu nhạy cảm, cần kiểm tra chính sách lưu trữ và quyền truy cập DLT. Thêm stack trace vào header là thêm dữ liệu vào Kafka log; dữ liệu đó có thể được sao chép, giữ theo retention và nhìn thấy bởi các consumer được cấp quyền.

Strip các header exception cũ giúp giảm tích lũy, nhưng không tự xóa thông tin nhạy cảm trong **exception hiện tại**. Hãy tránh ném exception có thông điệp chứa token, password, payload riêng tư hoặc nội dung chưa được làm sạch.

## 10. Lỗi deserialize cần xử lý riêng

Lỗi deserialize xảy ra trong lúc consumer đọc record, trước khi business listener nhận được object. Nếu dùng ErrorHandlingDeserializer, Spring Kafka có thể đưa thông tin DeserializationException vào header riêng để error handler xử lý.

Ví dụ cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: com.example.events
~~~

Một số phiên bản DeadLetterPublishingRecoverer phục hồi byte[] dữ liệu gốc bị lỗi deserialize để đưa sang DLT. Điều này đòi hỏi KafkaTemplate/serializer của DLT có khả năng xử lý đúng kiểu giá trị được gửi; không thể luôn giả định value trong DLT vẫn là OrderEvent.

Cần tách biệt:

- Header exception DLT mô tả lỗi mà recoverer công bố.
- Header từ ErrorHandlingDeserializer lưu thông tin lỗi deserialize để container nhận diện.
- Key/value gốc có thể vẫn cần giữ để điều tra lỗi schema hoặc encoding.

Đừng tự xóa tất cả các header có chữ exception bằng một hàm lọc tên đơn giản: có thể vô tình xóa dữ liệu mà Spring Kafka cần để phân loại lỗi deserialize hoặc tái tạo payload. Cấu hình stripPreviousExceptionHeaders và kiểm tra hành vi thực tế của phiên bản thư viện an toàn hơn một bộ lọc tùy tiện.

## 11. Header gốc và header mới khi đi qua nhiều topic

Có hai kiểu thông tin khác nhau mà đội vận hành thường cần:

**Original source** cho biết record bắt đầu từ đâu. Thông tin này hữu ích để truy lại producer hoặc dữ liệu đầu vào.

**Current failure location** cho biết lần xử lý hiện tại thất bại ở topic/partition/offset nào. Nếu một record được re-drive qua topic trung gian, thông tin này có thể khác original source.

Không phải mọi chương trình re-drive đều giữ nguyên tất cả header. Vì vậy, hãy quyết định rõ hợp đồng replay:

1. eventId phải giữ nguyên để consumer nhận diện cùng sự kiện.
2. correlationId/traceId chỉ giữ khi thực sự cần và theo chính sách dữ liệu.
3. Replay ID hoặc attempt ID mới cần được tạo khi muốn phân biệt những lượt re-drive.
4. Metadata nguồn gốc phải được ghi theo chính sách riêng.
5. Exception headers từ lần thất bại trước nên được xử lý bằng strip hoặc chuyển sang audit.

Một trường replayId có thể là marker nghiệp vụ, nhưng không nên thay eventId. ReplayId định danh một lượt phát lại; eventId định danh sự kiện gốc.

## 12. DLT publish cũng có thể thất bại

Strip headers có thể giảm kích thước record, nhưng không đảm bảo recoverer gửi DLT thành công. Các nguyên nhân lỗi vẫn gồm:

- DLT chưa tồn tại hoặc producer thiếu quyền publish.
- DLT có ít partition hơn partition mà resolver chỉ định.
- Serializer của KafkaTemplate không hỗ trợ key/value hoặc byte[] cần gửi.
- Broker không sẵn sàng, ISR không đạt yêu cầu hoặc message quá lớn.
- Delivery timeout khiến trạng thái publish không chắc chắn.

Trong các phiên bản hỗ trợ, có thể cấu hình recoverer phát hiện send result lỗi theo chính sách đồng bộ thích hợp:

~~~java
recoverer.setFailIfSendResultIsError(true);
recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(10));
~~~

Khi dùng hai cấu hình này, xem lại timeout, producer retries và hành vi của phiên bản Spring Kafka. Nếu recovery ném exception, error handler cần giữ khả năng thử lại hoặc khôi phục record nguồn theo chính sách đã định. Chỉ commit offset record gốc khi recovery đã hoàn tất đúng tiêu chí hệ thống.

Không coi việc header đã được strip là dấu hiệu DLT đã được lưu bền vững. Đây là hai vấn đề độc lập.

## 13. Bật strip có làm mất khả năng điều tra không?

Nó loại bỏ một phần thông tin về **lần thất bại cũ** khỏi bản record DLT mới. Đó là một đánh đổi có chủ đích: giảm dữ liệu dư thừa trong record hiện tại, trong khi lịch sử cần được lưu ở nơi phù hợp hơn nếu nghiệp vụ yêu cầu.

Có thể giữ khả năng điều tra qua:

- Log có cấu trúc theo eventId, replayId, topic, partition, offset và exception class.
- Trace hoặc correlation ID kết nối các lần xử lý.
- Audit table lưu attempt, timestamp, lỗi và quyết định re-drive.
- DLT retention và chính sách phân quyền phù hợp.
- Dashboard đếm số event vào DLT, số được re-drive, số thành công và số thất bại.

Chỉ số quan trọng không chỉ là số DLT record; cần biết một eventId bị lặp lại qua bao nhiêu vòng recovery và lần gần nhất thất bại vì lý do gì.

Nếu không có audit ngoài Kafka, một record được re-drive nhiều lần có thể chỉ còn chứa exception cuối cùng. Hãy làm rõ điều đó với đội vận hành trước khi chọn bật strip.

## 14. Kiểm tra headers bằng Kafka Consumer API

Khi đọc DLT, có thể kiểm tra tập header mà record thực sự nhận được.

~~~java
for (ConsumerRecord<String, byte[]> record : records) {
    Headers headers = record.headers();

    Header latest = headers.lastHeader(
        KafkaHeaders.DLT_EXCEPTION_FQCN
    );

    String errorClass = latest == null
            ? "unknown"
            : new String(latest.value(), StandardCharsets.UTF_8);

    int exceptionHeaderCount = 0;

    for (Header ignored : headers.headers(
            KafkaHeaders.DLT_EXCEPTION_FQCN)) {
        exceptionHeaderCount++;
    }

    log.info(
        "DLT event topic={} partition={} offset={} errorClass={} count={}",
        record.topic(),
        record.partition(),
        record.offset(),
        errorClass,
        exceptionHeaderCount
    );
}
~~~

Các import cần thiết:

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;
import org.springframework.kafka.support.KafkaHeaders;
~~~

Đây là đoạn minh họa đọc metadata, chưa bao gồm cơ chế tạo ConsumerRecords và cấu hình deserializer tương ứng. Nếu DLT chứa nhiều kiểu value (object và raw byte[]), nên dùng một consumer hoặc một định dạng payload có thể xử lý tất cả các trường hợp dự kiến.

Không in trực tiếp DLT_EXCEPTION_STACKTRACE hoặc toàn bộ headers vào log trong môi trường production. Có thể chỉ đo tổng byte length và exception class nếu cần quan sát kích thước.

## 15. Kiểm thử hành vi strip qua hai lần recover

Một integration test hữu ích phải tạo record có exception header cũ, cho recoverer xử lý thêm một exception mới, rồi đọc bản record được publish sang DLT. Mục tiêu là xác nhận nội dung header sau quá trình publish thực tế.

Kịch bản:

1. Tạo topic nguồn và DLT với đủ partition.
2. Tạo record có eventId cố định và một số header nghiệp vụ.
3. Cho listener thất bại và được chuyển sang DLT lần một.
4. Re-drive record, giữ những header theo hợp đồng ứng dụng.
5. Làm listener thất bại lần hai với exception class khác.
6. Đọc record DLT mới bằng consumer test.
7. Xác nhận exception header cũ đã bị loại bỏ theo cấu hình strip.
8. Xác nhận exception của lần thất bại hiện tại được đưa vào header phù hợp.
9. Xác nhận eventId và metadata nguồn cần giữ vẫn còn.
10. Xác nhận record không tăng vô hạn về kích thước header sau nhiều lần re-drive.

Dùng Embedded Kafka hoặc một broker test tương thích với phiên bản Spring Kafka của dự án. Cấu hình producer/consumer serializer cần phản ánh đúng payload production.

Một cách kiểm tra về mặt ý tưởng:

~~~java
Headers headers = dltRecord.headers();

Header current = headers.lastHeader(
    KafkaHeaders.DLT_EXCEPTION_FQCN
);

assertThat(current).isNotNull();

String currentClass = new String(
    current.value(),
    StandardCharsets.UTF_8
);

assertThat(currentClass).contains("ValidationException");

// Marker lỗi cũ không còn trong exception header tương ứng.
// Header event-id của ứng dụng vẫn phải giữ nguyên.
assertThat(headers.lastHeader("event-id")).isNotNull();
~~~

Đây là đoạn assertion minh họa; dltRecord là record được consumer test đọc từ DLT cuối. Nếu thư viện thêm header exception cho key hoặc value theo loại lỗi, test cần kiểm tra nhóm header tương ứng. Không dựa duy nhất vào số lượng header vì một số trường hợp hợp lệ có nhiều loại exception header khác nhau.

## 16. Kiểm soát kích thước và thông tin nhạy cảm

Một record DLT vẫn chịu giới hạn kích thước và retention như record Kafka khác. Exception header lớn có thể khiến lần publish DLT thất bại ngay cả khi payload nghiệp vụ không lớn.

Các biện pháp vận hành:

- Đo kích thước tổng headers trước và sau re-drive.
- Giới hạn nội dung các header tự định nghĩa.
- Không đưa payload nhạy cảm vào exception message.
- Dùng eventId/correlationId để liên kết log thay vì copy nguyên stack trace vào nhiều record.
- Đặt DLT retention theo nhu cầu điều tra và re-drive.
- Kiểm soát ACL đọc DLT vì nó có thể chứa dữ liệu lỗi và payload gốc.
- Phát cảnh báo khi DLT send failure hoặc kích thước record tăng bất thường.

Strip exception headers giúp tránh header bloat qua nhiều lần recover. Nó không làm giảm kích thước value, không thay đổi compression policy, cũng không thay thế kiểm tra cấu hình max.request.size và message.max.bytes khi cần.

## 17. Các tình huống thường gặp

| Tình huống | Hành vi cần cân nhắc |
|---|---|
| Record chuyển DLT lần đầu | Exception header hiện tại cần được thêm để điều tra |
| Re-drive từ DLT rồi lại lỗi | Strip exception cũ để record mới phản ánh lỗi hiện tại |
| Replay giữ eventId và traceId | Giữ header nghiệp vụ phục vụ idempotency và tracing |
| Cần toàn bộ lịch sử lỗi | Lưu audit ngoài Kafka header hoặc thiết kế lịch sử có giới hạn |
| Header stack trace rất lớn | Giảm thông tin exception và kiểm soát kích thước |
| ErrorHandlingDeserializer báo lỗi | Phân biệt deserialization header với DLT exception header |
| Ứng dụng tự thêm x-error-stacktrace | Tự quản lý header này; strip mặc định không đoán được |
| DLT publish thất bại | Không commit record nguồn như đã recover thành công |
| Header cùng tên xuất hiện nhiều lần | Kiểm tra danh sách headers(name), không chỉ lastHeader() |

## 18. Các lỗi cấu hình phổ biến

### Nhầm strip với xóa mọi header

Một số ứng dụng tự làm sạch bằng cách tạo Kafka record mới không có bất kỳ header nào. Điều đó có thể xóa eventId, traceId, metadata nguồn và thông tin schema, khiến DLT khó re-drive an toàn. Chỉ loại bỏ đúng nhóm header cần loại bỏ.

### Tắt strip để giữ lịch sử

Nếu tắt stripPreviousExceptionHeaders chỉ vì muốn giữ toàn bộ lịch sử lỗi, số header có thể tăng mãi qua các vòng re-drive. Lịch sử audit nên có cấu trúc, retention, phân quyền và giới hạn kích thước riêng.

### Giả định DLT chỉ có đúng một exception header

Một số lỗi liên quan đến key/value deserialization, cause chain hoặc header tùy chỉnh có thể làm tập header phức tạp. Kiểm tra exception header cụ thể và hợp đồng version thay vì viết logic chỉ dựa vào count == 1.

### Cấu hình recoverer nhưng listener không dùng

Nếu ứng dụng có nhiều ConcurrentKafkaListenerContainerFactory, bean handler phải được gắn vào factory mà @KafkaListener đang sử dụng. Sai factory khiến cấu hình strip không có tác dụng ở listener mong muốn.

### Không kiểm soát lỗi producer gửi DLT

Nếu publish DLT thất bại mà error handler xem recovery đã hoàn tất, record nguồn có thể được commit rồi không còn được xử lý lại. Cần kiểm tra đường gửi DLT, serializer, timeout, topic và khả năng recovery fail.

### Dùng tên header dạng string ở khắp code

Tên header có thể thay đổi giữa các phiên bản hoặc được phân biệt cho key/value. Nên dùng KafkaHeaders constants và gom phần đọc/ghi header vào một utility có phạm vi rõ ràng.

## 19. Khi nào không nên chỉ giữ exception mới nhất?

Một số hệ thống có yêu cầu điều tra lâu dài, ví dụ thanh toán, kiểm toán nghiệp vụ hoặc phản hồi sự cố liên quan nhiều dịch vụ. Khi đó, chỉ giữ lỗi cuối cùng trong DLT mới có thể không đủ để giải thích toàn bộ đường đi của event.

Thay vì tắt strip vô điều kiện, có thể:

1. Giữ exception mới nhất trong record DLT hiện tại.
2. Ghi audit event cho mỗi lần failure với eventId và replayId.
3. Lưu exception class/message đã được làm sạch và tham chiếu trace.
4. Giới hạn retention và quyền truy cập lịch sử.
5. Tạo màn hình hoặc query nối các lần failure theo eventId.

Cách này cho phép giảm kích thước Kafka headers mà vẫn giữ lịch sử điều tra có tổ chức. Nó cũng giúp tách quyền xem payload lỗi khỏi quyền xem stack trace nội bộ.

## 20. Vận hành và quan sát production

Nên theo dõi cả quy trình retry, DLT và re-drive:

**DLT**

- Số record chuyển sang DLT theo topic và exception class.
- Tỷ lệ publish DLT thành công/thất bại.
- Tuổi của record cũ nhất trong DLT.
- Kích thước record và headers trung bình/p95.
- Số record có nhiều exception header cùng loại.

**Re-drive**

- Số event được phát lại theo eventId/replayId.
- Tỷ lệ re-drive thành công.
- Số event quay lại DLT nhiều lần.
- Lỗi mới nhất và lỗi phổ biến qua các lần re-drive.
- Thời gian từ lần thất bại đầu đến khi nghiệp vụ phục hồi.

**Consumer**

- Consumer lag theo group/topic/partition.
- Thời gian xử lý record.
- Retry count và recovery failure.
- Rebalance và offset commit failure.
- Duplicate được phát hiện bởi idempotent consumer.

Log nên có eventId, topic, partition, offset, groupId, recovery stage và correlationId. Không log toàn bộ payload hay stack trace ở mọi lần retry chỉ để chứng minh header đã strip; điều đó có thể tạo dữ liệu nhạy cảm ngoài hệ thống Kafka.

## 21. Cân nhắc theo phiên bản Spring Kafka

Spring Kafka đã thay đổi API và hành vi retry/DLT qua các phiên bản. Khi áp dụng ví dụ:

- Xác nhận class DeadLetterPublishingRecoverer có setStripPreviousExceptionHeaders(boolean).
- Xác nhận giá trị mặc định trong phiên bản đang dùng; cấu hình rõ ràng giúp dễ bảo trì.
- Kiểm tra setAppendOriginalHeaders(boolean) và cách metadata nguồn được chọn sau nhiều lần recover.
- Kiểm tra cơ chế thêm exception headers và những header key/value deserialization liên quan.
- Nếu dùng custom exception headers creator, xác nhận nó tương tác thế nào với strip.
- Xác nhận cơ chế gửi DLT và điều kiện recoverer báo lỗi publish.
- Nếu dùng @RetryableTopic, kiểm tra framework có tự tạo recoverer riêng hay sử dụng recoverer mà ứng dụng đã cấu hình.

Cấu hình CommonErrorHandler phục vụ container error handling. Với @RetryableTopic, Spring Kafka có thêm các thành phần xử lý topic retry/DLT, nên không mặc định mọi recoverer trong hệ thống dùng chung bean cấu hình ở ví dụ. Hãy xác định đúng thành phần thực sự xuất bản từng chặng.

## 22. Nguyên tắc áp dụng

- Bật stripPreviousExceptionHeaders khi muốn exception headers trong DLT mới phản ánh lỗi hiện tại và tránh tích lũy lỗi cũ.
- Phân biệt exception headers, original metadata, business headers và deserializer headers.
- Dùng appendOriginalHeaders cho chiến lược metadata nguồn, không dùng nó để điều khiển lịch sử exception.
- Giữ eventId ổn định qua retry/DLT/re-drive để hỗ trợ idempotency.
- Không xóa hàng loạt headers khi chỉ cần loại một nhóm exception cũ.
- Nếu cần lịch sử nhiều lần thất bại, lưu audit có giới hạn riêng.
- Kiểm soát việc đưa stack trace và dữ liệu nhạy cảm vào DLT.
- Đảm bảo recoverer thật sự được gắn vào listener hoặc retry infrastructure cần áp dụng.
- Xác nhận publish DLT thành công trước khi xem record nguồn đã được recover.
- Kiểm thử đường đi nhiều chặng và đọc thực tế record DLT sau recover.
- Theo dõi kích thước headers, DLT failure, số vòng re-drive và offset commit.
- Đối chiếu Javadoc với phiên bản Spring Kafka mà ứng dụng đang chạy.

Strip exception headers giúp giữ bản record DLT sau mỗi lần recovery tập trung vào nguyên nhân hiện tại, tránh nhân lên các stack trace cũ và giảm rủi ro header bloat. Khi phối hợp với metadata nguồn, eventId ổn định, chính sách audit và cơ chế gửi DLT đáng tin cậy, hệ thống Spring Kafka có thể phát lại và điều tra lỗi nhiều lần mà vẫn kiểm soát được kích thước record và thông tin cần cho vận hành.
