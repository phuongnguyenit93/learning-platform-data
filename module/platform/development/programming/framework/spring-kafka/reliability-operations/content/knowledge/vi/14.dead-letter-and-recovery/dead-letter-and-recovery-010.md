# Fail khi DLT publish thất bại

Dead Letter Topic (DLT) là đích phục hồi cho những record mà consumer không thể xử lý thành công theo chính sách retry. Trong Spring Kafka, một lỗi ở listener có thể được chuyển tới **DeadLetterPublishingRecoverer** để publish record sang DLT. Tuy nhiên, bản thân việc publish DLT cũng là một thao tác Kafka producer và **có thể thất bại** vì broker, authorization, serialization, cấu hình topic, kích thước record hoặc timeout.

Nếu ứng dụng coi record đã được phục hồi trong khi record đó chưa thực sự được ghi vào DLT, offset nguồn có thể được commit và dữ liệu không còn đi qua đường xử lý thông thường. Đây là một rủi ro **silent loss** nghiêm trọng: consumer group trông như đang tiến triển, nhưng nghiệp vụ chưa được xử lý và record lỗi cũng không nằm ở nơi điều tra.

Thiết kế đáng tin cậy cần phân biệt ba trạng thái:

1. **Listener xử lý nghiệp vụ thất bại.**
2. **Recoverer đã thử publish sang DLT**, nhưng kết quả có thể chưa biết hoặc đã thất bại.
3. **Recovery được xác nhận thành công** theo cơ chế publish và chính sách xác nhận đã chọn; khi đó offset nguồn mới có thể tiến lên theo delivery semantics.

Không được đánh đồng việc gọi hàm gửi DLT với việc broker đã chấp nhận record. Bài học này tập trung vào cách để **recovery fail rõ ràng khi DLT publish thất bại**, cách consumer xử lý lại record, các cửa sổ duplicate và runbook vận hành.

## 1. DLT nằm ở đâu trong quy trình xử lý lỗi?

Với một record listener thông thường, quy trình là:

~~~text
orders.events
      |
      v
@KafkaListener xử lý record
      |
      +--- Thành công ------------------> Offset tiến lên theo AckMode
      |
      +--- Thất bại
               |
               v
        DefaultErrorHandler
               |
          Retry/backoff
               |
       +-------+-------+
       |               |
   Retry thành công   Hết retry / non-retryable
       |               |
       v               v
   Tiếp tục       DeadLetterPublishingRecoverer
                       |
                       v
                  Publish sang DLT
                       |
                +------+------+
                |             |
             Thành công     Thất bại
                |             |
                v             v
         Recovery hoàn tất  Recovery phải
         theo chính sách    được xem là lỗi
~~~

Error handler điều khiển việc thử lại record đầu vào; recoverer quyết định record nào cần chuyển DLT và gọi producer để publish. Vì producer gửi bất đồng bộ, recoverer phải có chính sách quan sát kết quả gửi để xác định recovery đã hoàn tất hay chưa.

Với Spring Kafka, có hai mô hình liên quan:

- **Blocking retry:** thường dùng DefaultErrorHandler cùng DeadLetterPublishingRecoverer.
- **Non-blocking retry:** dùng retry-topic infrastructure, ví dụ @RetryableTopic, trong đó record đi qua các retry topic rồi đến DLT.

Hai mô hình có các thành phần và thời điểm commit khác nhau, nhưng đều phải xử lý tình huống publish sang topic phục hồi thất bại.

## 2. “DLT publish thất bại” bao gồm những trường hợp nào?

Thao tác publish có thể thất bại ngay lúc chuẩn bị record hoặc sau khi request đã được gửi đến broker.

### 2.1. Lỗi đồng bộ trước khi gửi

Ví dụ:

- Serializer không thể chuyển key/value thành byte.
- DLT record bị tạo với topic hoặc partition không hợp lệ.
- Producer đang ở trạng thái đóng hoặc fatal.
- Client thiếu cấu hình producer cần thiết.
- Record hoặc header gây lỗi trong quá trình chuyển đổi.

Một exception có thể được ném ngay trong quá trình tạo request hoặc gọi send(). Không có future thành công để chờ khi thao tác không thể bắt đầu.

### 2.2. Lỗi bất đồng bộ sau khi gửi

Ví dụ:

- Broker leader đổi hoặc mất kết nối.
- Producer không nhận được acknowledgement.
- Topic DLT chưa tồn tại và metadata không sẵn sàng.
- Authorization bị từ chối.
- Replication/ISR không đáp ứng điều kiện của producer.
- Record hết delivery timeout.

Producer có thể trả về future rồi mới báo lỗi sau đó. Nếu recoverer không kiểm tra future, việc gọi send() thành công chỉ có nghĩa lần gửi đã được chấp nhận để xử lý bởi client, **không phải** broker đã ghi record bền vững.

### 2.3. Kết quả chưa rõ sau timeout

Timeout không phải lúc nào cũng chứng minh record DLT chưa được ghi. Có tình huống broker đã append record nhưng acknowledgement không về kịp. Nếu recoverer thất bại và record nguồn được giao lại, record có thể được publish DLT lần thứ hai.

Vì vậy, policy “không commit offset nguồn khi DLT publish không được xác nhận” giúp tránh bỏ qua record, nhưng **không tự bảo đảm DLT chỉ có một bản sao**. Hệ thống cần event ID ổn định và cách chống duplicate ở DLT consumer hoặc quy trình replay.

## 3. Rủi ro khi recoverer không xác nhận kết quả gửi

Một hành vi nguy hiểm có thể xảy ra:

~~~text
Listener xử lý lỗi
        |
        v
DeadLetterPublishingRecoverer gọi KafkaTemplate.send()
        |
        v
send() trả về future chưa hoàn tất
        |
        v
Recoverer trả về bình thường
        |
        v
Container xem record đã recover
        |
        v
Offset nguồn được commit theo policy
        |
        v
Producer future sau đó báo DLT publish thất bại
~~~

Khi đó DLT thiếu record, trong khi committed offset của consumer group đã tiến lên. Restart consumer không tự động đọc lại record nguồn vì group bắt đầu từ offset đã commit.

Với các phiên bản Spring Kafka có hỗ trợ, **DeadLetterPublishingRecoverer.setFailIfSendResultIsError(true)** cho phép recoverer ném exception khi kết quả publish báo lỗi. Hãy xác nhận cấu hình thực tế và API của phiên bản đang dùng; không nên dựa vào mặc định mà không kiểm tra.

Nguyên tắc:

- Recovery chỉ được xem là thành công sau khi đạt điều kiện xác nhận mà nghiệp vụ lựa chọn.
- Nếu publish DLT thất bại, exception phải được đưa trở lại luồng xử lý lỗi/recovery thay vì chỉ ghi log.
- Offset nguồn không nên được chủ động commit với nhãn “đã recover” khi record lỗi chưa được lưu theo yêu cầu.
- Nếu kết quả publish chưa rõ, ưu tiên khả năng replay an toàn và chấp nhận duplicate có kiểm soát hơn là silent loss.

## 4. Cấu hình fail khi DLT send thất bại

Ví dụ cấu hình Spring Kafka cho listener non-transactional:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DeadLetterPublishingRecoverer deadLetterRecoverer(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(dltKafkaTemplate);

    // Recovery không được coi là thành công nếu producer báo lỗi.
    recoverer.setFailIfSendResultIsError(true);

    // Giới hạn thời gian recoverer chờ kết quả send.
    recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(15));

    return recoverer;
}

@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer deadLetterRecoverer) {

    DefaultErrorHandler handler = new DefaultErrorHandler(
        deadLetterRecoverer,
        new FixedBackOff(1_000L, 3L)
    );

    // Sau một lần recovery thất bại, có thể chạy lại backoff sequence.
    handler.setResetStateOnRecoveryFailure(true);

    return handler;
}
~~~

Ví dụ thể hiện ba quyết định:

1. Listener có một ngân sách retry xử lý record hữu hạn trước khi recovery.
2. Recoverer kiểm tra kết quả publish DLT và báo lỗi nếu gửi không thành công theo cơ chế xác nhận được cấu hình.
3. Khi recovery thất bại, error handler có thể khởi động lại chuỗi backoff cho lần xử lý kế tiếp.

Tên setter và kiểu timeout cần được kiểm tra theo Javadoc của phiên bản Spring Kafka đang dùng. Đặc biệt, thời gian chờ kết quả gửi phải phù hợp với timeout cấu hình của producer. Không đặt thời gian chờ vô hạn chỉ để tránh exception.

### 4.1. Cơ chế xác nhận thực sự bảo đảm điều gì?

Khi send future hoàn tất thành công, producer nhận được acknowledgement theo chính sách acks của nó. Nếu producer dùng **acks=all**, broker xác nhận theo điều kiện replica trong ISR và min.insync.replicas; nó không có nghĩa mọi replica đang tồn tại đều đã xác nhận.

Nếu yêu cầu recovery có độ bền cao, nên xem xét:

- Producer acks=all.
- Idempotent producer phù hợp.
- Topic DLT có replication factor đủ.
- min.insync.replicas phù hợp với replication factor.
- Retention và quyền truy cập được quản lý.
- Alert khi send result không được xác nhận.

Không thể tạo độ bền chỉ bằng cách chờ future nếu topic DLT có replication factor không phù hợp hoặc producer đang sử dụng mức acknowledgement quá yếu.

## 5. Chọn timeout khi chờ DLT publish

Recoverer có thể chờ kết quả KafkaTemplate.send(). Thời gian chờ cần đủ để producer có cơ hội retry các lỗi retriable và nhận phản hồi, nhưng không nên lớn đến mức giữ consumer thread quá lâu.

Các giới hạn thời gian liên quan:

| Tham số | Vai trò |
|---|---|
| delivery.timeout.ms | Giới hạn tổng thời gian producer cố giao một record |
| request.timeout.ms | Thời gian chờ phản hồi của từng request broker |
| linger.ms | Khoảng chờ batching trước khi gửi nếu cấu hình |
| Wait-for-send-result timeout của recoverer | Thời gian recoverer chờ future gửi DLT |
| max.poll.interval.ms | Giới hạn tiến độ poll của consumer |
| BackOff của error handler | Khoảng chờ trước lần thử xử lý/recovery tiếp theo |

Nếu recoverer chỉ chờ 2 giây trong khi producer delivery timeout là 120 giây, recoverer có thể hết thời gian chờ nhưng request vẫn đang được xử lý. Record DLT có thể xuất hiện sau đó, và một lần retry khác có thể publish thêm bản sao.

Nếu recoverer chờ 120 giây trên consumer thread, các lần chờ lặp lại có thể làm chu kỳ xử lý kéo dài và ảnh hưởng nhịp poll. Hãy thiết kế dựa trên SLO, đo latency thực tế, tính retry budget và dùng producer timeout hữu hạn.

Một ước lượng thô cho trường hợp recovery liên tục timeout:

~~~text
Thời gian trước lần poll tiếp theo
    ≈ thời gian listener + listener backoff
      + số lần recovery × timeout chờ DLT
      + overhead
~~~

Không có một timeout phù hợp cho mọi ứng dụng. Nếu DLT là đường bảo vệ dữ liệu bắt buộc, thường nên ưu tiên fail và giữ khả năng redelivery khi không xác nhận được publish, thay vì giảm timeout rồi tự coi gửi thành công.

## 6. Nguyên nhân thường gặp khiến DLT publish thất bại

| Nguyên nhân | Dấu hiệu | Hướng điều tra |
|---|---|---|
| Topic DLT không tồn tại | Metadata timeout, unknown topic/partition | Kiểm tra provision topic và quyền auto-create |
| Sai tên hoặc partition DLT | Invalid topic/partition, metadata không phù hợp | Kiểm tra destination resolver và partition count |
| Thiếu quyền ghi | TopicAuthorizationException hoặc authorization error | Kiểm tra principal, ACL, credential |
| Serializer không xử lý được giá trị | SerializationException | Kiểm tra serializer của DLT KafkaTemplate và kiểu payload |
| Record quá lớn | RecordTooLargeException hoặc lỗi size limit | Kiểm tra serialized bytes, header, max.request.size và broker/topic limits |
| Broker/leader/ISR không ổn định | NotEnoughReplicas, timeout, leader error | Kiểm tra ISR, leader, replication và broker health |
| Producer buffer bị đầy | Block timeout, queue backlog | Kiểm tra throughput, buffer và broker latency |
| Producer bị đóng hoặc lỗi fatal | IllegalStateException hoặc producer fatal exception | Khôi phục producer, xem transaction/fencing nếu có |
| Network/DNS/TLS | Disconnect, authentication/handshake error | Kiểm tra endpoints, certificates và kết nối |

Không xem mọi timeout là lỗi mạng tạm thời. Một topic chưa được tạo hoặc endpoint sai có thể tiếp tục gây timeout cho đến khi sửa cấu hình. Root cause quyết định liệu retry có ý nghĩa hay không.

## 7. Topic DLT không tồn tại hoặc sai partition

Với DeadLetterPublishingRecoverer mặc định, destination thường được xác định từ topic gốc và giữ partition tương ứng. Ví dụ một record từ topic orders partition 7 có thể được gửi đến orders.DLT partition 7.

Nếu topic DLT chỉ có 3 partition, destination partition 7 không hợp lệ. Việc publish có thể thất bại hoặc framework kiểm tra partition rồi áp dụng logic xử lý theo phiên bản và cấu hình. Hãy xác nhận destination resolver và khả năng kiểm tra partition của recoverer.

Một cách định tuyến minh họa:

~~~java
DeadLetterPublishingRecoverer recoverer =
    new DeadLetterPublishingRecoverer(
        dltKafkaTemplate,
        (record, exception) ->
            new TopicPartition(record.topic() + ".DLT", -1)
    );
~~~

Đặt partition âm trong destination resolver có thể để producer chọn partition thay vì ép cùng partition nguồn, theo contract của recoverer. Cách này tránh yêu cầu topic DLT có cùng số partition, nhưng **không bảo đảm thứ tự hoặc phép ánh xạ partition gốc sang DLT**.

Nếu cần giữ partition gốc để điều tra dễ dàng, hãy provision DLT đủ partition và lưu original topic/partition/offset trong header. Trong production, tạo topic bằng IaC và khai báo replication, retention, ACL rõ ràng; không dựa vào auto-create ngoài ý muốn.

## 8. Serializer không tương thích với record lỗi

Một lỗi đặc biệt phổ biến xảy ra khi record đầu vào không deserialize được. Khi dùng **ErrorHandlingDeserializer**, framework có thể chuyển lỗi deserialization thành thông tin trong header và cho phép recoverer gửi giá trị gốc dạng byte[] sang DLT.

Tuy nhiên, KafkaTemplate dùng cho DLT có thể đang cấu hình JSON serializer chỉ nhận object đã deserialize, không xử lý byte[]. Khi đó:

~~~text
Record nguồn chứa bytes không hợp lệ
         |
         v
ErrorHandlingDeserializer ghi nhận lỗi
         |
         v
DeadLetterPublishingRecoverer cố gửi raw bytes
         |
         v
DLT KafkaTemplate dùng serializer không hỗ trợ bytes
         |
         v
SerializationException: DLT publish thất bại
~~~

Hướng khắc phục là cấu hình serializer cho DLT hỗ trợ các kiểu giá trị cần gửi, ví dụ dùng **DelegatingByTypeSerializer** để chọn ByteArraySerializer cho byte[] và JSON serializer cho object thông thường.

Ý tưởng cấu hình:

~~~java
Map<Class<?>, Serializer<?>> serializers = new LinkedHashMap<>();
serializers.put(byte[].class, new ByteArraySerializer());
serializers.put(OrderEvent.class, new JsonSerializer<OrderEvent>());

DelegatingByTypeSerializer valueSerializer =
    new DelegatingByTypeSerializer(serializers, true);
~~~

Ví dụ chỉ minh họa cách chọn serializer theo kiểu Java. Cần điều chỉnh cho các lớp payload thực tế, key serializer, cách chọn serializer theo thứ tự, cấu hình trusted packages và API của phiên bản Spring Kafka.

Không đơn giản serialize mọi giá trị lỗi lại thành JSON nếu điều đó làm mất original bytes cần để debug. Với lỗi deserialize, original bytes và metadata là bằng chứng quan trọng để phân tích schema hoặc payload hỏng.

## 9. Authorization, authentication và lỗi cấu hình

DLT publish là thao tác **produce tới một topic khác**. Principal có quyền consume topic nguồn chưa chắc có quyền write topic DLT.

Một deployment có thể đọc orders.events bình thường nhưng fail khi ghi orders.events.DLT vì:

- ACL chỉ cho phép read topic nguồn.
- DLT topic được provision bởi cluster khác hoặc trong namespace khác.
- KafkaTemplate cho DLT sử dụng principal khác.
- Credential/TLS certificate bị thay đổi.
- Topic DLT có policy riêng.

Những lỗi này thường không được giải quyết bằng retry cùng thông tin xác thực. Cần sửa ACL, credential hoặc routing rồi kiểm tra lại.

Nên đưa quyền ghi DLT vào bước kiểm tra trước rollout. Nếu DLT là đường recovery thiết yếu, việc ứng dụng chỉ phát hiện thiếu ACL khi có poison record đầu tiên là quá muộn.

## 10. Recovery thất bại thì DefaultErrorHandler làm gì?

Với blocking retry và DefaultErrorHandler, sau khi listener hết retry hoặc gặp exception non-retryable, handler gọi recoverer. Nếu recoverer ném exception, **recovery chưa hoàn tất thành công**.

Trong các phiên bản Spring Kafka hỗ trợ, DefaultErrorHandler có cơ chế reset backoff state khi recovery thất bại. Sau đó record có thể được giao lại và quy trình retry/recovery tiếp tục, thay vì bị coi là đã xử lý chỉ vì recoverer đã được gọi.

Ví dụ:

~~~text
Record X ở offset 53
      |
      v
Listener lỗi nghiệp vụ
      |
      v
Retry listener hết policy
      |
      v
Recoverer publish DLT
      |
      v
DLT send thất bại -> recoverer ném exception
      |
      v
DefaultErrorHandler chưa đánh dấu recovery thành công
      |
      v
Record X tiếp tục là công việc chưa được phục hồi
      |
      v
Backoff / redelivery / recovery lại theo cấu hình
~~~

Điểm cần kiểm tra trong phiên bản cụ thể:

- Recoverer có thực sự ném exception khi DLT send thất bại không?
- State của error handler có reset khi recovery thất bại không?
- AckMode, manual ack và commit recovered được cấu hình thế nào?
- Record có được seek/re-submit để xử lý lại không?
- Container có bị dừng do exception không được xử lý không?

Không nên giả định một cấu hình DefaultErrorHandler bất kỳ đều cho đúng behavior nếu code listener tự catch exception hoặc tự acknowledge record trước khi recovery hoàn tất.

## 11. Offset commit: giữ record khi DLT không được lưu

Trong mô hình at-least-once, mục tiêu quan trọng là **không làm mất cơ hội xử lý lại record nguồn** khi DLT publish thất bại.

Hãy phân biệt:

| Trạng thái | Điều ứng dụng biết | Hành động offset phù hợp |
|---|---|---|
| Listener thành công | Nghiệp vụ hoàn tất | Commit theo AckMode |
| Listener lỗi, DLT publish đã xác nhận thành công | Record được lưu ở luồng recovery | Có thể commit theo recovery policy |
| Listener lỗi, DLT publish bị từ chối | Recovery chưa thành công | Không đánh dấu record đã recover |
| Listener lỗi, DLT send timeout/kết quả chưa rõ | Có thể DLT đã ghi hoặc chưa | Giữ khả năng replay, chấp nhận duplicate DLT |
| DLT thành công nhưng commit offset nguồn thất bại | DLT đã có record, group chưa ghi nhận tiến độ | Record nguồn có thể được đọc lại và DLT có duplicate |

Với **AckMode.MANUAL_IMMEDIATE**, một số cách cấu hình DefaultErrorHandler có thể sử dụng commitRecovered để commit offset của record đã recover. Chỉ bật cơ chế đó khi phù hợp với AckMode và chắc chắn recoverer trả về thành công theo điều kiện mong muốn.

Với các AckMode khác, container quản lý commit theo quy tắc riêng. Không áp dụng cùng một lời khẳng định “recoverer xong là offset commit ngay” cho mọi cấu hình.

Không viết logic kiểu:

~~~java
try {
    publishToDlt(record);
}
catch (Exception ex) {
    log.error("DLT failed", ex);
}
acknowledgment.acknowledge(); // nguy hiểm nếu DLT chưa lưu record
~~~

Nếu recoverer thất bại, phải chuyển lỗi về luồng error handling phù hợp, hoặc giữ record trong cơ chế phục hồi bền vững khác. Chỉ log rồi acknowledge làm mất thông tin rằng nghiệp vụ chưa được xử lý và DLT chưa được ghi.

## 12. DLT đã ghi nhưng nguồn chưa commit: duplicate hợp lệ

Ngay cả khi recoverer kiểm tra send result và broker đã xác nhận DLT publish, commit offset của consumer nguồn vẫn có thể thất bại.

~~~text
Publish DLT: thành công
        |
        v
Record tồn tại ở orders.DLT
        |
        v
Ứng dụng crash trước khi commit offset orders
        |
        v
Consumer khác đọc lại record nguồn
        |
        v
Publish DLT lần nữa
~~~

Trong mô hình non-transactional, không có bảo đảm nguyên tử tự động giữa publish DLT và commit offset nguồn. Đó là lý do **DLT nên chấp nhận duplicate**.

Để chống tác động nghiệp vụ lặp:

- Giữ original topic, partition và offset trong header DLT.
- Giữ event ID/business key ổn định.
- DLT consumer hoặc workflow replay dùng idempotency key.
- Không coi offset mới của DLT là định danh nghiệp vụ.
- Khi replay, ghi nhận record nào đã được xử lý hoặc đã được đưa vào workflow.

Một khóa nhận diện kỹ thuật có thể kết hợp original topic + original partition + original offset. Nếu một nghiệp vụ có thể được publish nhiều lần thành các record nguồn khác nhau, event ID ở tầng nghiệp vụ vẫn cần để chống duplicate xuyên các lần publish đó.

## 13. Nếu producer timeout nhưng DLT đã được ghi

Một producer timeout có thể tạo kết quả chưa rõ:

1. Recoverer gửi request publish DLT.
2. Broker ghi record.
3. Mạng mất acknowledgement.
4. Future báo lỗi hoặc recoverer hết thời gian chờ.
5. Error handler thử phục hồi lại record nguồn.
6. DLT nhận thêm một bản sao.

Không thể giải quyết hoàn toàn trường hợp này bằng cách tăng wait timeout hoặc bật idempotence. Idempotent producer bảo vệ retry protocol nội bộ trong phạm vi producer session; một lần gọi send mới của recoverer khi record được giao lại có thể được xem là record mới.

Với hệ thống đòi hỏi chính xác một lần ở cấp nghiệp vụ, cần thiết kế idempotency khi đọc DLT/replay hoặc transaction có phạm vi phù hợp. Không dựa vào “DLT send chỉ được gọi một lần” như một invariant.

## 14. DLT fail và retry storm

Nếu broker DLT ngừng hoạt động, mỗi record lỗi có thể tiếp tục:

~~~text
Listener thất bại -> Hết retry
          |
          v
DLT publish thất bại
          |
          v
Recovery retry
          |
          v
DLT publish lại
          |
          v
Tiếp tục lỗi ...
~~~

Khi nhiều consumer cùng gặp vấn đề, có thể xảy ra retry storm: producer gửi nhiều request lỗi, timeout và retry cùng lúc, làm broker hoặc network tiếp tục quá tải.

Biện pháp:

- Backoff có giới hạn và đủ dài khi recovery failure kéo dài.
- Phân loại lỗi DLT có thể phục hồi và không thể phục hồi.
- Giới hạn concurrency và các request đến broker.
- Cảnh báo ngay khi DLT publish failure tăng.
- Theo dõi producer retry rate và delivery timeout.
- Có quy trình dừng/pause consumer có kiểm soát nếu không thể lưu record lỗi.
- Khôi phục topic, ACL, cluster và serializer trước khi cho hệ thống xả backlog.

Không tự động vô hạn hóa mọi retry recovery. Nếu DLT topic bị cấu hình sai, các lần thử không giải quyết được nguyên nhân.

## 15. Blocking retry và non-blocking retry khi DLT thất bại

Với **blocking retry**, DefaultErrorHandler và DeadLetterPublishingRecoverer có thể điều phối redelivery khi recovery không thành công.

Với **non-blocking retry**, retry-topic infrastructure publish record qua các retry topics và cuối cùng đến DLT. Nếu publish của một chặng chuyển topic hoặc DLT thất bại, cần bảo đảm record nguồn của chặng đó chưa bị xem là đã recover trước khi kết quả publish được xác nhận theo cấu hình.

Các điểm khác nhau:

| Khía cạnh | Blocking retry | Non-blocking retry |
|---|---|---|
| Luồng phục hồi | Error handler xử lý record nguồn | Retry-topic routing giữa nhiều topic |
| Ranh giới chuyển dữ liệu | Khi recoverer publish DLT | Mỗi lần publish sang retry topic/DLT |
| Thứ tự | Dễ kiểm soát hơn trong partition gốc | Có thể thay đổi |
| Số consumer/offset | Chủ yếu container nguồn | Mỗi retry topic có consumer và offset riêng |
| Lỗi publish | Recovery chưa hoàn tất nếu xác nhận send thất bại | Chặng chuyển topic chưa hoàn tất nếu publish thất bại |
| Quan sát | Record retry, DLT send, offset nguồn | Cần theo dõi tất cả retry stages và DLT |

Đừng áp dụng trực tiếp một assumption từ DefaultErrorHandler vào @RetryableTopic mà không kiểm tra phiên bản và bean recoverer thực tế. Retry-topic infrastructure có thể tạo recoverer, listener container và error handler riêng.

## 16. Phân biệt DLT publish failure và DLT listener failure

Hai sự cố dễ bị nhầm:

1. **DLT publish failure:** producer không thể ghi record vào topic DLT.
2. **DLT listener/handler failure:** record đã nằm trong DLT, nhưng listener tiêu thụ hoặc xử lý DLT lại ném exception.

Ví dụ:

~~~text
Source listener lỗi
      |
      v
Publish DLT lỗi                 <-- DLT publish failure

Source listener lỗi
      |
      v
Publish DLT thành công
      |
      v
@DltHandler xử lý DLT lỗi       <-- DLT processing failure
~~~

Trong retry-topic pattern, enum **DltStrategy** có các lựa chọn như FAIL_ON_ERROR, ALWAYS_RETRY_ON_ERROR hoặc NO_DLT theo phiên bản. Những chiến lược này liên quan tới **hành vi xử lý record ở DLT** hoặc việc có tạo DLT hay không; **không được nhầm** DltStrategy.FAIL_ON_ERROR với cấu hình khiến DeadLetterPublishingRecoverer fail khi **producer gửi DLT** thất bại.

Nếu mục tiêu là bảo đảm producer send sang DLT được kiểm tra, hãy xem cấu hình send-result verification của recoverer. Nếu mục tiêu là DLT handler lỗi phải dừng hay được retry, hãy xem DltStrategy và error handler của DLT listener.

Đây là hai failure boundary khác nhau và cần metric, alert khác nhau.

## 17. Transactional listener cần cách phục hồi riêng

Với listener container có Kafka transaction, output Kafka và offset đầu vào có thể được đưa vào cùng transaction. Khi listener exception gây rollback, **DefaultAfterRollbackProcessor** thường chịu trách nhiệm retry/recovery, thay vì chỉ dùng DefaultErrorHandler như luồng non-transactional.

Một số cấu hình Spring Kafka hỗ trợ publish recovered record trong transaction mới và đưa offset nguồn vào transaction đó theo policy phù hợp. Khi đó cần kiểm tra:

- Recoverer có gửi DLT trong transaction được thiết lập không?
- Offset gốc có được commit cùng transaction recovery không?
- Producer transaction commit có thành công không?
- Nếu transaction abort, record có được giao lại đúng cách không?
- Có producer fencing, timeout hoặc transaction coordinator error không?

**Không giả định một lần publish DLT và commit offset nguồn là nguyên tử chỉ vì có @Transactional trên một method Java.** Kafka transaction cần được cấu hình ở đúng producer/container boundary, và Spring Kafka phiên bản đang dùng quyết định API tương ứng.

Kafka transaction cũng không tự bao gồm thay đổi database hoặc HTTP side effect. Nếu một thao tác ngoài Kafka đã thành công nhưng recovery transaction thất bại, record vẫn có thể được xử lý lại. Idempotency vẫn cần thiết.

## 18. Thiết kế fallback khi DLT không khả dụng

DLT là kênh recovery chính, nhưng vẫn có thể mất khả năng ghi. Cần quyết định làm gì khi DLT không khả dụng trong một khoảng thời gian vượt giới hạn.

Các lựa chọn:

| Chính sách | Ưu điểm | Đổi lại |
|---|---|---|
| Giữ record nguồn chưa recovered và retry có backoff | Không cố ý bỏ qua record | Lag tăng, partition có thể bị chặn |
| Pause/dừng consumer có kiểm soát | Giảm retry storm, giữ vị trí nguồn | Chậm toàn bộ hoặc một phần luồng tiêu thụ |
| Fallback durable storage được thiết kế riêng | Có thể lưu record để xử lý sau khi Kafka DLT hỏng | Thêm hệ thống, quyền, transaction và quy trình reconcile |
| Fallback DLT ở cluster khác | Tách failure domain | Phức tạp bảo mật, routing, consistency và monitoring |
| Báo sự cố và can thiệp thủ công | Rõ ownership và kiểm soát dữ liệu quan trọng | Giảm tự động hóa |

Nếu sử dụng fallback storage, chỉ đánh dấu recovery hoàn tất sau khi ghi thành công theo durability yêu cầu. Không tự gọi một API fallback rồi swallow exception và commit offset. Cần event ID, checksum hoặc định danh nguồn để reconcile bản sao có thể xuất hiện ở nhiều nơi.

Phương án phù hợp phụ thuộc dữ liệu quan trọng đến đâu, thời gian lưu Kafka, SLO xử lý và khả năng đội vận hành phục hồi.

## 19. Producer DLT nên được cấu hình thế nào?

KafkaTemplate dùng cho DLT là producer. Nó có thể dùng cùng ProducerFactory hoặc một factory riêng; nếu dùng factory riêng, cần kiểm tra toàn bộ security, serializer và reliability properties.

Ví dụ Spring Boot:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
        max.in.flight.requests.per.connection: 5
~~~

Đây là cấu hình minh họa. Khi DLT KafkaTemplate có producer factory riêng, các thuộc tính cần được áp dụng tới **đúng producer factory của DLT**, không chỉ producer mặc định.

Lưu ý:

- acks=all không thay thế replication factor và min.insync.replicas.
- Idempotence hỗ trợ retry protocol producer, không tự deduplicate lần publish nghiệp vụ mới.
- delivery.timeout.ms phải phù hợp thời gian recoverer có thể chờ và SLO.
- Producer buffer và batch config có thể ảnh hưởng latency.
- Serializer phải tương thích cả record bình thường lẫn payload lỗi cần đưa DLT.
- DLT có thể chứa dữ liệu nhạy cảm; cần chính sách truy cập và retention phù hợp.

## 20. Quan sát DLT publish failure

Consumer lag thấp chưa chắc có nghĩa recovery hoạt động. Nếu recoverer không xác nhận send result và offset đã commit, lỗi DLT có thể không còn biểu hiện qua lag nguồn.

Nên theo dõi:

| Tín hiệu | Mục đích |
|---|---|
| DLT publish attempts | Lượng record được thử gửi DLT |
| DLT publish success | Lượng record nhận được xác nhận gửi thành công |
| DLT publish failure theo exception | Phát hiện authorization, serialization, timeout, metadata |
| DLT producer send latency | Phát hiện broker hoặc producer chậm |
| Recovery failure count | Xác định recoverer không hoàn tất |
| Source partition lag | Record nguồn có bị kẹt do recovery failure không |
| DLT incoming rate | Kiểm tra record thực sự tới DLT |
| DLT consumer lag | Theo dõi lượng record chưa xử lý trên DLT |
| Oldest unrecovered record age | Phát hiện record bị giữ quá SLO |
| Rebalance rate | Recovery chờ quá lâu có ảnh hưởng poll/group không |
| Kafka broker ISR/leader status | Phát hiện nguyên nhân hạ tầng |

Không phải mọi metric có sẵn cùng tên trong mọi phiên bản Kafka/Spring Kafka. Có thể sử dụng Micrometer observations, producer metrics, error handler logging hoặc instrumentation ở recoverer phù hợp.

Gắn metric theo topic, stage và nhóm exception; tránh dùng event ID làm metric label vì cardinality rất cao. Event ID nên đi trong log hoặc trace.

### 20.1. Log phục hồi nên chứa gì?

Một log có ích cho on-call thường có:

- Consumer group, client ID.
- Original topic, partition, offset.
- DLT destination topic và partition.
- Event ID/correlation ID.
- Exception gốc của listener.
- Exception mới của producer/recoverer.
- Thời gian chờ và kết quả xác nhận DLT.
- Retry attempt hoặc recovery attempt nếu có.

Không log credential, access token hoặc toàn bộ payload nhạy cảm. Một sự cố DLT thường cần metadata để điều tra đường đi; không cần sao chép toàn bộ dữ liệu cá nhân vào log.

## 21. Runbook khi DLT publish thất bại

### Bước 1: Xác định failure boundary

Xác nhận rằng lỗi xảy ra khi publish DLT, không phải khi listener xử lý record gốc hoặc khi DLT consumer xử lý record đã ghi. Tìm exception từ DeadLetterPublishingRecoverer hoặc Kafka producer send result.

### Bước 2: Kiểm tra record và destination

- Original topic/partition/offset là gì?
- DLT destination được resolver chọn là topic/partition nào?
- Topic DLT có tồn tại và có đủ partition không?
- Principal producer có quyền Describe/Write cần thiết không?
- Serializer có xử lý được key/value của record lỗi không?

### Bước 3: Kiểm tra hạ tầng Kafka

- DLT partition có leader không?
- ISR có đáp ứng min.insync.replicas không?
- Broker request latency và network có bất thường không?
- Producer có bị metadata timeout hoặc buffer exhaustion không?
- Có lỗi authentication/TLS hoặc thay đổi ACL gần đây không?

### Bước 4: Giữ an toàn dữ liệu

Nếu DLT publish chưa xác nhận thành công, không tự đánh dấu record đã recover hoặc commit offset chỉ để xóa lag. Tùy chính sách, để error handler retry recovery, pause container hoặc kích hoạt quy trình fallback bền vững.

Nếu send timeout, ghi nhận kết quả **chưa rõ** và chuẩn bị xử lý duplicate DLT nếu record được redeliver.

### Bước 5: Khôi phục nguyên nhân

Sửa topic, ACL, serializer, kích thước payload hoặc broker/ISR tùy lỗi. Tránh chỉ tăng timeout hoặc retry count khi root cause là permanent.

### Bước 6: Xác nhận end-to-end

Sau khi sửa, xác minh record lỗi được ghi vào DLT, offset nguồn tiến triển đúng cách, retry/recovery failures giảm và DLT consumer hoặc quy trình xử lý sau có thể đọc được record. Nếu có duplicate, kiểm tra event ID và metadata nguồn.

### Bước 7: Đóng sự cố

Ghi lại số record ảnh hưởng, khoảng thời gian DLT không ghi được, các offset nguồn chưa recovered, record có kết quả chưa rõ, thời gian bắt kịp và hành động ngăn tái diễn.

## 22. Các lỗi thiết kế thường gặp

| Cách làm | Rủi ro | Hướng điều chỉnh |
|---|---|---|
| Gọi KafkaTemplate.send rồi coi là DLT thành công | Future có thể fail sau khi recoverer trả về | Bật send-result verification phù hợp |
| Chỉ log lỗi DLT rồi acknowledge nguồn | Silent loss nếu DLT chưa ghi | Đưa lỗi trở lại recovery/error handler |
| Cho rằng timeout chứng minh DLT chưa ghi | Redelivery có thể tạo duplicate | Dùng event ID và dedup ở DLT/replay |
| Không tạo topic DLT trước deploy | Metadata timeout, publish fail | Provision topic bằng IaC |
| DLT có ít partition hơn partition đích | Invalid destination hoặc send fail | Tạo đủ partition hoặc dùng resolver phù hợp |
| Serializer DLT chỉ hỗ trợ object hợp lệ | Raw bytes lỗi deserialize không gửi được | Dùng serializer hỗ trợ byte[] và payload thực tế |
| Consumer có Read ACL nhưng producer thiếu Write ACL DLT | Lỗi authorization khi phục hồi | Kiểm tra quyền producer DLT |
| Retry recovery vô hạn với lỗi permanent | Partition bị kẹt và retry storm | Phân loại lỗi, alert và can thiệp |
| Bật DltStrategy.FAIL_ON_ERROR để sửa lỗi producer DLT | Nhầm failure của DLT handler với publish | Cấu hình recoverer send-result verification |
| Chỉ nhìn lag của topic chính | Không thấy record recover lỗi hoặc backlog DLT | Theo dõi toàn pipeline |
| Tin rằng idempotent producer bảo đảm DLT không duplicate | Redelivery tạo lần publish mới | Dedup ở tầng nghiệp vụ |
| Nhầm @Transactional Java với Kafka transaction | Không có atomicity như mong đợi | Cấu hình đúng Kafka transaction/after-rollback processing |

## 23. Checklist kiểm thử trước production

Nên có các tình huống kiểm thử chức năng và fault injection có kiểm soát:

1. Listener lỗi và DLT publish thành công: xác nhận recoverer hoàn tất và offset theo policy.
2. DLT topic không tồn tại: recovery báo lỗi và record nguồn không bị bỏ qua.
3. Producer DLT thiếu Write ACL: authorization error được quan sát, có alert.
4. DLT serializer không hỗ trợ raw byte[]: lỗi được báo rõ và không bị nuốt.
5. Broker DLT không có leader hoặc ISR thiếu: kiểm tra retry và hành vi khi hết timeout.
6. DLT send được broker ghi nhưng acknowledgement mất: kiểm tra khả năng duplicate.
7. DLT publish thành công nhưng source offset commit thất bại: record có thể redeliver và được xử lý idempotent.
8. Recoverer fail liên tục: kiểm tra backoff, lag, rebalance và khả năng pause.
9. DLT lỗi khi record quá lớn: xác nhận có đường sửa payload hoặc fallback.
10. DLT publish failure khác DLT handler failure: kiểm tra metric và chính sách riêng.
11. Nếu dùng transaction: kiểm tra recovery transaction, abort và offset commit.
12. Nếu dùng retry topics: kiểm tra failure ở cả bước publish retry topic lẫn publish DLT.

Thử nghiệm không nên dựa vào việc ngắt broker sản xuất hoặc xóa topic DLT trên cluster dùng chung. Dùng môi trường Kafka riêng, quyền và topic thử nghiệm hoặc fault injection được kiểm soát.

## 24. Checklist cấu hình vận hành

Trước khi đưa DeadLetterPublishingRecoverer vào production, hãy xác nhận:

- Recoverer có kiểm tra kết quả producer send và ném lỗi khi DLT publish không thành công không?
- Timeout chờ send result có hữu hạn và phù hợp producer delivery timeout không?
- DLT KafkaTemplate có đúng serializer, security và acks không?
- DLT topic có tồn tại, đủ partition, replication, ISR và ACL không?
- AckMode và commit recovered policy có bảo đảm không cố ý bỏ qua record khi recovery thất bại không?
- DefaultErrorHandler hoặc AfterRollbackProcessor có xử lý được recovery failure không?
- Có thể redeliver record khi DLT fail mà không nhân đôi side effect không?
- Record DLT có event ID và metadata gốc để deduplicate và điều tra không?
- Có alert về DLT publish failure, recovery failure và oldest unrecovered record age không?
- Có runbook cho lỗi permanent như ACL/serializer và lỗi transient như broker/ISR không?
- Có phương án fallback hoặc pause an toàn nếu DLT không ghi được trong outage kéo dài không?
- Có phân biệt lỗi publish DLT với lỗi xử lý của DLT consumer không?

**Nguyên tắc cốt lõi:** DLT là đường lưu giữ record lỗi, không phải một thao tác luôn thành công. Nếu publish DLT thất bại, recovery cũng phải được xem là thất bại theo chính sách đã chọn; không được tiếp tục commit offset nguồn như thể record đã được lưu an toàn. Khi không thể biết chắc DLT đã nhận record hay chưa, hãy bảo toàn khả năng replay, chấp nhận duplicate có kiểm soát và sử dụng idempotency để bảo vệ nghiệp vụ. Đây là cách ưu tiên tính toàn vẹn dữ liệu hơn một chỉ số consumer lag nhìn có vẻ đẹp.
