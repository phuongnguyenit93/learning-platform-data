# Dead-letter topic

## Dead-letter topic giải quyết vấn đề gì?

Trong Kafka, consumer đọc record từ topic và thực hiện xử lý nghiệp vụ. Có những record khiến consumer liên tục thất bại: payload không đúng schema, dữ liệu thiếu, trạng thái nghiệp vụ không hợp lệ hoặc dịch vụ phụ thuộc đang gặp sự cố. Nếu consumer cứ nhận lại cùng một record mà không có chính sách xử lý, một lỗi đơn lẻ có thể làm chậm hoặc chặn cả luồng xử lý.

**Dead-letter topic (DLT)** là topic riêng dùng để chuyển các record đã thất bại sau chính sách retry sang một luồng xử lý lỗi. Record được giữ lại để điều tra, sửa dữ liệu hoặc phát lại sau khi nguyên nhân được khắc phục.

Ví dụ, ứng dụng Fulfillment đọc OrderConfirmed từ topic commerce.orders.v1. Nếu một record lỗi không thể xử lý sau số lần thử đã cấu hình, consumer có thể chuyển record đó tới commerce.orders.v1.DLT. Các record hợp lệ tiếp theo vẫn có thể được xử lý, trong khi đội vận hành điều tra record lỗi.

~~~mermaid
flowchart TD
    A[Kafka topic: commerce.orders.v1] --> B[Fulfillment consumer]
    B -->|Xử lý thành công| C[Commit offset]
    B -->|Lỗi tạm thời| D[Retry policy]
    D -->|Thành công| C
    D -->|Hết số lần thử| E[Dead-letter topic]
    E --> F[DLT consumer / Operations]
    F --> G[Điều tra và sửa nguyên nhân]
    G --> H[Replay có kiểm soát]
~~~

DLT không tự sửa record và cũng không chứng minh nghiệp vụ đã hoàn tất. Nó tạo một nơi lưu giữ có thể quan sát cho các record chưa xử lý thành công.

## Phân biệt DLT với retry topic và Event Publication Registry

Ba cơ chế có liên quan đến lỗi nhưng nằm ở các chặng khác nhau:

| Cơ chế | Phạm vi | Mục đích |
|---|---|---|
| Retry topic | Giữa broker và consumer | Thử lại record sau một khoảng chờ hoặc theo lịch retry |
| Dead-letter topic | Phía consumer | Giữ record đã hết retry hoặc được phân loại không thể retry |
| Event Publication Registry | Trong ứng dụng Spring Modulith | Theo dõi publication của application event tới listener, bao gồm publication externalization |

Trong Spring Modulith, Event Publication Registry theo dõi publication được tạo khi application event được phát và có listener được quản lý. Khi externalization adapter không gửi được event tới Kafka, publication tương ứng có thể còn chưa hoàn tất để ứng dụng xử lý lại theo cơ chế registry và cấu hình đang dùng.

DLT thường xuất hiện ở chặng sau: Kafka đã nhận record, nhưng consumer không thể xử lý record đó thành công. Khi đó, retry topic và DLT là cơ chế của phía consumer/broker integration.

Ví dụ hai lỗi khác nhau:

- **Lỗi producer/externalization:** Kafka tạm thời không sẵn sàng khi Spring Modulith adapter gửi event. Cần xử lý lỗi gửi và trạng thái publication phía ứng dụng.
- **Lỗi consumer:** Kafka đã lưu record, nhưng Fulfillment không deserialize được payload hoặc xử lý nghiệp vụ thất bại. Consumer retry rồi có thể chuyển record sang DLT.

Không dùng DLT để thay thế Event Publication Registry. Cũng không coi publication đã hoàn tất trong ứng dụng là bằng chứng consumer downstream đã xử lý message.

## Vòng đời của một record lỗi

Một quy trình DLT thường có các bước:

1. Consumer nhận record từ topic gốc.
2. Consumer gọi logic nghiệp vụ và phát sinh exception.
3. Error handler phân loại exception để quyết định retry hay không.
4. Với lỗi có thể phục hồi, record được thử lại theo backoff hoặc được chuyển qua retry topic.
5. Khi hết số lần thử, recoverer gửi record đến DLT.
6. Consumer group của topic gốc được phép tiến tiếp theo acknowledgement/offset policy đã cấu hình.
7. DLT consumer hoặc quy trình vận hành đọc record lỗi, ghi nhận nguyên nhân và quyết định cách khắc phục.
8. Sau khi xử lý nguyên nhân, record có thể được phát lại theo quy trình kiểm soát.

Mỗi bước cần có kết quả quan sát được. Nếu việc gửi record vào DLT thất bại, ứng dụng phải có chính sách rõ ràng để không âm thầm đánh dấu record gốc đã được xử lý thành công.

## Retry trước khi đưa vào DLT

Không phải mọi lỗi đều cần chuyển thẳng vào DLT. Nên phân loại lỗi:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi tạm thời | Timeout, broker phụ thuộc tạm ngắt, HTTP 503 | Retry có backoff |
| Lỗi giới hạn tài nguyên | Database connection pool bận, rate limit | Retry có giới hạn và giãn cách |
| Lỗi dữ liệu cố định | Payload sai schema, thiếu trường bắt buộc | Thường không retry nhiều lần; chuyển DLT |
| Lỗi nghiệp vụ không thể tự phục hồi | Đơn hàng đã bị hủy hoặc trạng thái không hợp lệ | Ghi nhận để xử lý nghiệp vụ |
| Lỗi lập trình | Null pointer, invariant bị vi phạm | Giới hạn retry, cảnh báo và điều tra |

Retry liên tục một lỗi dữ liệu cố định chỉ tiêu tốn tài nguyên và kéo dài thời gian phát hiện. Ngược lại, chuyển một lỗi timeout thoáng qua thẳng vào DLT có thể tạo lượng record lỗi không cần thiết.

Backoff giúp giảm áp lực lên dịch vụ đang lỗi. Ví dụ, khoảng chờ tăng dần 1 giây, 2 giây, 4 giây có thể giúp dependency phục hồi. Có thể thêm jitter để nhiều consumer không cùng retry tại một thời điểm.

Cần xác định số lần thử, thời gian chờ tối đa và nhóm exception được retry. Chính sách phải phù hợp với SLA nghiệp vụ và thời gian record được phép nằm trong luồng retry.

## Dùng Spring Kafka để cấu hình retry topic và DLT

Spring Kafka cung cấp cơ chế non-blocking retry bằng annotation @RetryableTopic. Cơ chế này tạo các retry topic và DLT theo cấu hình, rồi chuyển record qua các topic retry khi listener thất bại.

Ví dụ:

~~~java
@Component
public class OrderEventConsumer {

    @RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
            delay = 1_000,
            multiplier = 2.0
        )
    )
    @KafkaListener(
        topics = "commerce.orders.v1",
        groupId = "fulfillment"
    )
    public void consume(OrderConfirmed event) {
        fulfillmentService.prepareShipment(event.orderId());
    }

    @DltHandler
    public void handleDeadLetter(OrderConfirmed event) {
        deadLetterService.recordFailure(event);
    }
}
~~~

Trong ví dụ:

- @KafkaListener đăng ký consumer cho topic gốc.
- @RetryableTopic thiết lập tổng số lần thử, gồm lần xử lý ban đầu và các lần retry theo semantics của Spring Kafka.
- @Backoff cấu hình thời gian chờ tăng theo hệ số nhân.
- Khi record hết retry, Spring Kafka chuyển record đến DLT được tạo theo quy ước của cấu hình.
- @DltHandler chỉ định method xử lý record từ DLT trong cùng bean listener.

Đây là ví dụ minh họa. Cấu hình cụ thể còn phụ thuộc phiên bản Spring Kafka, cách đặt tên retry/DLT topic, serializer, số partition và error handler. Cần xác nhận API đang dùng trong dự án trước khi áp dụng.

Có thể cấu hình thêm exception không retry, số lần thử, thời gian backoff, topic suffix, auto-creation và handler riêng. Đối với lỗi không thể khắc phục bằng retry, hãy phân loại để chuyển DLT sớm thay vì đợi hết mọi lần thử.

## Dùng error handler và recoverer

Ngoài @RetryableTopic, Spring Kafka hỗ trợ error handler ở mức container. DefaultErrorHandler có thể dùng BackOff để retry và DeadLetterPublishingRecoverer để gửi record đã phục hồi thất bại đến DLT.

Mô hình khái niệm:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> template) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
            template,
            (record, exception) -> new TopicPartition(
                record.topic() + ".DLT",
                record.partition()
            )
        );

    DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );

    handler.addNotRetryableExceptions(
        IllegalArgumentException.class
    );

    return handler;
}
~~~

Trong ví dụ, recoverer định tuyến record lỗi tới topic DLT có hậu tố .DLT và giữ partition tương ứng. Vì vậy DLT phải có đủ partition tương ứng với partition gốc nếu resolver yêu cầu giữ nguyên partition. Nếu topic đích không tồn tại hoặc không có partition phù hợp, việc gửi DLT có thể thất bại.

FixedBackOff(1_000L, 2L) minh họa khoảng chờ cố định và số lần retry theo API Spring Kafka. Exception IllegalArgumentException được phân loại không retry trong cấu hình này. Hãy kiểm tra semantics và constructor theo phiên bản thư viện đang dùng.

Chỉ chọn một cách quản lý retry chủ đạo cho mỗi listener. Tránh cấu hình annotation retry topic và container error handler chồng chéo nếu chưa hiểu rõ thứ tự thực thi, vì có thể dẫn tới số lần thử khác dự kiến hoặc route sai topic.

## Thiết kế DLT topic và partition

DLT là một Kafka topic thật, vì vậy cần thiết kế như một phần của topology messaging:

- Tên topic dễ liên hệ với topic gốc.
- Số partition phù hợp với chiến lược định tuyến và khả năng xử lý lỗi.
- Replication factor và min in-sync replicas phù hợp với yêu cầu durability.
- Retention đủ dài để điều tra và phục hồi.
- Quyền publish cho consumer/recoverer và quyền đọc cho nhóm vận hành.
- Monitoring cho message count, tuổi record cũ nhất và tốc độ phát sinh.

Nếu recoverer gửi record tới cùng partition number của topic gốc, DLT cần có số partition ít nhất tương ứng. Nếu resolver chọn partition khác hoặc phân phối lại, phải xác định rõ ảnh hưởng đến thứ tự và khả năng xử lý song song.

Không nên để DLT dùng retention quá ngắn khiến record biến mất trước khi được điều tra. Cũng không nên giữ vô hạn mà không có chính sách dung lượng, archive và xóa dữ liệu.

## Nội dung cần giữ trong dead-letter record

Để điều tra và replay, DLT record cần giữ đủ ngữ cảnh:

| Dữ liệu | Mục đích |
|---|---|
| Original topic | Biết record xuất phát từ luồng nào |
| Original partition và offset | Truy nguyên vị trí record gốc |
| Message key | Hiểu nhóm định tuyến hoặc aggregate |
| Payload gốc | Phục vụ phân tích và replay |
| Event type/schema version | Xác định cách deserialize |
| Event ID/correlation ID | Liên kết log, trace và nghiệp vụ |
| Exception class/message | Biết lý do xử lý thất bại |
| Timestamp và retry metadata | Xác định thời điểm, số lần thử |
| Consumer group/application | Biết thành phần đã thất bại |

Spring Kafka có thể bổ sung các header chứa thông tin topic, partition, offset và exception khi sử dụng DeadLetterPublishingRecoverer. Tên header và cách lưu cần được xác nhận theo phiên bản. Không tự giả định payload đã được bọc thêm một envelope mới nếu adapter chỉ thêm metadata vào Kafka headers.

Cần bảo vệ dữ liệu trong DLT như dữ liệu production. Payload lỗi vẫn có thể chứa thông tin cá nhân hoặc bí mật. Giới hạn quyền đọc, retention, logging và thao tác tải xuống theo nguyên tắc tối thiểu.

## Xử lý record trong DLT

DLT không phải nơi để consumer đọc rồi bỏ qua. Cần có quy trình xác định record sẽ được xử lý thế nào:

1. Ghi nhận record và nguyên nhân lỗi vào hệ thống theo dõi.
2. Phân loại lỗi: dữ liệu, schema, dependency hay lỗi lập trình.
3. Xác định owner của topic gốc và consumer group liên quan.
4. Sửa lỗi dữ liệu hoặc triển khai bản sửa consumer.
5. Kiểm tra record có còn hợp lệ theo trạng thái nghiệp vụ hiện tại không.
6. Chọn replay, chuyển sang luồng bù trừ hoặc đóng lỗi với lý do rõ ràng.
7. Ghi lại người thực hiện, thời điểm và kết quả.

Một số record không nên replay vì trạng thái nghiệp vụ đã thay đổi. Ví dụ, một OrderConfirmed cũ có thể không còn phù hợp nếu đơn hàng đã bị hủy. Replay cần kiểm tra điều kiện hiện tại và bảo đảm idempotency.

## Replay từ DLT an toàn

Replay là gửi lại record đã lưu trong DLT tới topic gốc hoặc một topic xử lý lại được thiết kế riêng. Không nên xóa DLT record trước khi xác nhận việc replay đã thành công và có thể truy vết.

Một quy trình replay an toàn nên:

- Chọn record theo event ID, partition/offset hoặc khoảng thời gian.
- Kiểm tra nguyên nhân gốc đã được khắc phục.
- Giữ lại payload và metadata cần thiết.
- Gửi lại với key phù hợp để duy trì partitioning.
- Ghi nhận nguồn replay và thời điểm replay.
- Chống việc chạy cùng một batch replay nhiều lần gây tác động trùng.
- Theo dõi kết quả consumer sau replay.

Nếu gửi lại DLT record vào topic gốc, cần tránh để record lỗi lập tức quay lại DLT mà không có giới hạn. Có thể dùng một replay topic hoặc một thao tác có kiểm soát để phân biệt message được replay. Tuy nhiên, không sửa event ID gốc nếu event ID được dùng cho idempotency; hãy thêm replay attempt ID hoặc metadata riêng.

Nếu replay bằng cách publish một record mới, offset và timestamp broker sẽ thay đổi. Cần giữ original topic/partition/offset trong metadata để còn khả năng truy nguyên.

## DLT và thứ tự xử lý

Retry topic có thể làm thay đổi thứ tự quan sát. Khi một record lỗi được chuyển sang retry topic, consumer của topic gốc có thể tiếp tục với record tiếp theo. Record sau có thể được xử lý trước record đang retry.

Ví dụ:

1. OrderPlaced của đơn hàng A được xử lý.
2. OrderConfirmed của đơn hàng A bị lỗi và được chuyển sang retry topic.
3. OrderCancelled của đơn hàng A được đọc tiếp từ topic gốc.
4. OrderCancelled có thể được xử lý trước khi OrderConfirmed retry thành công.

Nếu nghiệp vụ phụ thuộc thứ tự theo aggregate, cần lựa chọn chiến lược cẩn thận:

- Dùng blocking retry nếu cần giữ partition chờ record lỗi, chấp nhận ảnh hưởng throughput.
- Dùng sequence/version của aggregate để phát hiện event đến sai thứ tự.
- Lưu event chưa thể xử lý vào trạng thái chờ và xử lý lại khi thiếu event được bổ sung.
- Chọn key theo aggregate để giữ các event cùng aggregate trên cùng partition của topic gốc.
- Thiết kế consumer idempotent và có quy tắc cho event cũ hoặc trùng.

Dùng cùng key không tự bảo đảm thứ tự xuyên qua nhiều retry topic. Cần kiểm tra cách framework ánh xạ partition và cách consumer xử lý record từ các topic retry.

## Kiểm thử retry và dead-letter

Kiểm thử cần chứng minh record đi đúng luồng khi thành công, lỗi tạm thời và lỗi không thể retry.

| Tình huống | Điều cần xác nhận |
|---|---|
| Consumer xử lý thành công | Không phát sinh record DLT |
| Lỗi tạm thời rồi phục hồi | Record được retry và xử lý thành công |
| Hết số lần thử | Record được gửi đến DLT đúng topic |
| Exception không retry | Record chuyển sang recoverer theo cấu hình |
| DLT publish thất bại | Lỗi được quan sát và record gốc không bị âm thầm coi là thành công |
| Payload lỗi schema | DLT vẫn giữ đủ metadata để điều tra |
| Replay | Record được gửi lại đúng destination và không gây tác động trùng |
| Nhiều partition | Record được định tuyến đến partition DLT phù hợp |
| Retry topic | Backoff và số lần thử khớp cấu hình |

Integration test nên chạy với Kafka broker test hoặc container tương đương để xác nhận topic, partition, header, offset và redelivery. Unit test chỉ kiểm tra exception classifier hoặc hàm xử lý DLT không đủ chứng minh broker đã nhận record.

Với listener bất đồng bộ, dùng điều kiện chờ có giới hạn thời gian. Tránh sleep cố định vì thời gian xử lý có thể thay đổi giữa các môi trường.

## Quan sát DLT trong production

DLT cần được theo dõi như một chỉ số chất lượng giao sự kiện. Các metric nên có:

- Số record mới vào DLT theo topic gốc và consumer group.
- Tuổi của record cũ nhất trong DLT.
- Tỷ lệ record lỗi trên tổng record đã xử lý.
- Nhóm exception thường gặp.
- Số lần retry trung bình và tỷ lệ retry thành công.
- Số record đang chờ điều tra hoặc replay.
- Thời gian từ lúc vào DLT đến khi được xử lý xong.

Có thể đặt cảnh báo khi DLT xuất hiện record mới, khi số lượng vượt ngưỡng hoặc khi record cũ nhất vượt SLA xử lý. Một DLT tăng liên tục thường là dấu hiệu schema drift, lỗi consumer, dependency không ổn định hoặc dữ liệu nghiệp vụ không hợp lệ.

Không dùng event ID hoặc order ID làm metric label vì cardinality có thể tăng không giới hạn. Đưa các giá trị đó vào log hoặc trace có kiểm soát. Dashboard nên nhóm theo topic gốc, consumer group và exception type.

## Những lỗi thường gặp

- **Xem DLT như nơi lưu message lâu dài:** DLT vẫn cần retention, archive và cleanup.
- **Chuyển mọi exception sang retry:** lỗi dữ liệu cố định không thể tự phục hồi; cần phân loại non-retryable.
- **Replay mà không idempotent:** cùng nghiệp vụ có thể được thực hiện nhiều lần.
- **Xóa record sau khi bắt đầu replay:** có thể mất dấu vết nếu publish lại thất bại.
- **Không giữ metadata gốc:** khó truy nguyên topic, partition, offset và nguyên nhân.
- **Không cấp đủ partition cho DLT:** recoverer có thể không gửi được record khi giữ partition gốc.
- **Cho rằng retry topic giữ nguyên ordering:** record sau có thể vượt record đang retry.
- **Coi DLT là cơ chế xử lý lỗi producer:** lỗi externalization trước khi broker nhận thuộc chặng ứng dụng/registry.

## Quy trình vận hành DLT

Khi một record xuất hiện trong DLT:

1. Xác định topic gốc, consumer group, event ID và thời điểm lỗi.
2. Đọc exception metadata và kiểm tra log/trace liên quan.
3. Phân loại lỗi tạm thời, lỗi dữ liệu, schema hay lỗi lập trình.
4. Xác định số record bị ảnh hưởng và có cần dừng consumer hay không.
5. Sửa nguyên nhân ở consumer, schema hoặc dữ liệu.
6. Kiểm tra điều kiện nghiệp vụ hiện tại và idempotency.
7. Thực hiện replay có kiểm soát hoặc quy trình bù trừ.
8. Xác nhận consumer xử lý thành công và lưu kết quả điều tra.
9. Chỉ dọn record theo chính sách retention sau khi hoàn tất lưu vết.

Dead-letter topic giúp cô lập record gây lỗi để luồng Kafka tiếp tục vận hành và tạo điểm bắt đầu cho việc điều tra, sửa chữa, replay. Khi kết hợp phân loại exception, retry có giới hạn, metadata đầy đủ, consumer idempotent và quy trình vận hành rõ ràng, DLT trở thành một phần của chiến lược giao sự kiện đáng tin cậy thay vì nơi tập trung các message bị bỏ quên.

## Tài liệu tham khảo

- Spring Kafka Reference — Handling Exceptions: https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html
- Spring Kafka Reference — Non-Blocking Retries: https://docs.spring.io/spring-kafka/reference/retrytopic.html
- Spring Modulith Reference — Working with Application Events: https://docs.spring.io/spring-modulith/reference/events.html
- Apache Kafka Documentation: https://kafka.apache.org/documentation/
