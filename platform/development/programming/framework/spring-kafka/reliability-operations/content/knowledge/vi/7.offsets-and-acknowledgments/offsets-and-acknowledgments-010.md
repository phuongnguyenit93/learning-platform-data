# commitRetries

Trong Spring Kafka, **commitRetries** là cấu hình của listener container quy định số lần container thử lại thao tác commit offset đồng bộ khi gặp một lỗi commit có thể retry. Tham số này giúp consumer chịu được một số lỗi tạm thời trong quá trình gửi offset lên Kafka, chẳng hạn coordinator hoặc kết nối đang chuyển trạng thái.

commitRetries thuộc về bước ghi nhận tiến độ consumer group. Nó không retry logic xử lý record, không gửi lại record đầu ra và không điều khiển số lần listener được gọi lại. Khi xử lý record thành công nhưng commit offset chưa được ghi nhận, record có thể được đọc lại sau restart hoặc rebalance. Vì vậy, retry commit giúp tăng khả năng hoàn tất thao tác commit, còn ứng dụng vẫn cần thiết kế side effect idempotent để chịu được trường hợp replay.

## 1. Offset commit nằm ở đâu trong vòng đời consumer?

Kafka consumer đọc record từ partition và tiến tới các offset tiếp theo. Ứng dụng cần commit offset để Kafka lưu tiến độ của consumer group. Khi consumer khởi động lại hoặc partition được giao cho member khác, group có thể tiếp tục từ committed offset đã lưu.

Với Spring Kafka listener container, vòng đời đơn giản thường là:

~~~
Consumer poll()
      |
      v
Listener xử lý record hoặc batch
      |
      v
Container xác định offset cần commit theo AckMode
      |
      v
Gửi offset commit đến Kafka
      |
      +---- Thành công: group ghi nhận tiến độ
      |
      +---- Lỗi retriable: container thử commit lại
      |
      +---- Lỗi không retry được: xử lý theo lỗi và trạng thái group
      |
      v
Tiếp tục poll()
~~~

Committed offset thường là offset tiếp theo cần đọc. Nếu listener đã xử lý record ở offset 41 và commit offset 42, lần đọc tiếp theo của group bắt đầu từ 42.

Offset commit được lưu trong cơ chế quản lý consumer group của Kafka, thông qua coordinator và topic nội bộ **__consumer_offsets**. Việc commit thành công cho biết broker đã ghi nhận tiến độ group theo protocol. Nó không tự chứng minh rằng mọi side effect bên ngoài Kafka đều đã hoàn tất đúng một lần.

## 2. commitRetries làm gì?

Trong Spring Kafka, **ContainerProperties** có thuộc tính **commitRetries**. Khi listener container thực hiện commit đồng bộ và gặp **RetriableCommitFailedException**, container có thể thử lại thao tác commit theo số lần được cấu hình.

Ví dụ:

~~~java
factory.getContainerProperties().setCommitRetries(5);
~~~

Giá trị 5 có nghĩa container được phép thử lại tối đa năm lần sau lần commit ban đầu đối với loại lỗi mà cơ chế này hỗ trợ. Tổng số lần gọi có thể gồm lần đầu cộng các lần retry. Giá trị mặc định thường là 3; hãy xác nhận API và mặc định của phiên bản Spring Kafka đang sử dụng.

Điểm cần nhớ:

- commitRetries được dùng cho commit đồng bộ.
- Cấu hình chỉ có tác dụng khi **syncCommits=true**.
- Cơ chế này nhắm đến lỗi commit có thể retry, điển hình là **RetriableCommitFailedException**.
- Lỗi không thể retry, lỗi quyền truy cập hoặc lỗi do consumer không còn là thành viên hợp lệ của group không được biến thành lỗi có thể phục hồi chỉ bằng cách tăng commitRetries.
- Tham số không điều khiển retry của producer, retry của listener hay retry topic.

Với listener container Spring Kafka, commit đồng bộ là lựa chọn mặc định trong nhiều cấu hình. Nếu ứng dụng chuyển sang commit bất đồng bộ, commitRetries không được áp dụng cho thao tác commitAsync.

## 3. Phân biệt commitRetries với các cơ chế retry khác

Tên các cấu hình retry trong hệ thống Kafka khá giống nhau, nhưng chúng xử lý những giai đoạn khác nhau.

| Cơ chế | Đối tượng được thử lại | Mục đích |
|---|---|---|
| Kafka producer retries | Request gửi record của producer | Khắc phục lỗi gửi tạm thời trong giới hạn giao record |
| Spring Kafka listener retry / error handler | Việc xử lý record bị listener ném lỗi | Thử lại xử lý nghiệp vụ hoặc phục hồi record lỗi |
| Non-blocking retry topic | Record được chuyển sang topic retry | Hoãn lần xử lý tiếp theo và cho consumer chính tiếp tục |
| commitRetries | Thao tác commit offset đồng bộ của consumer container | Thử lại việc lưu tiến độ group khi commit gặp lỗi retriable |
| Retry do ứng dụng tự viết | Một thao tác nghiệp vụ do code điều khiển | Phục hồi một quy trình theo chính sách riêng |

Ví dụ, listener đọc record thành công, gọi database và sau đó container commit offset. Nếu commit gặp lỗi retriable, commitRetries có thể thử lại thao tác commit. Nó không gọi lại listener chỉ vì commit cần retry.

Ngược lại, nếu listener ném exception trước khi xử lý hoàn tất, container đi vào cơ chế rollback/error handler. Đó là retry xử lý record, không phải commitRetries.

Không nên dùng commitRetries để che một listener bị treo, một database timeout hoặc một record dữ liệu lỗi. Hãy xác định lỗi nằm ở bước xử lý hay ở bước lưu offset.

## 4. commit đồng bộ và commit bất đồng bộ

Spring Kafka cho phép container sử dụng commit đồng bộ hoặc bất đồng bộ thông qua thuộc tính **syncCommits**.

### 4.1. Commit đồng bộ

Khi **syncCommits=true**, container sử dụng **Consumer.commitSync()** để gửi offset và chờ kết quả. Nếu commit hoàn tất, container biết thao tác đã thành công theo phản hồi của Kafka. Nếu commit thất bại bằng lỗi retriable mà Spring Kafka hỗ trợ, container có thể thử lại theo commitRetries.

Ưu điểm:

- Container nhận được kết quả commit trong luồng điều khiển.
- Dễ xác định thời điểm commit hoàn tất trước khi tiếp tục chu kỳ xử lý.
- Có thể retry một số lỗi commit tạm thời thông qua commitRetries.

Đổi lại, consumer thread phải chờ commit hoàn tất. Nếu coordinator hoặc broker phản hồi chậm, thời gian xử lý chu kỳ có thể tăng. Cần theo dõi commit latency và cấu hình timeout hợp lý.

### 4.2. Commit bất đồng bộ

Khi **syncCommits=false**, container sử dụng **Consumer.commitAsync()**. Lời gọi không chờ broker hoàn tất commit; kết quả được chuyển qua callback nếu được cấu hình.

Ưu điểm là giảm thời gian chờ trong consumer thread. Tuy nhiên, ứng dụng không nhận kết quả đồng bộ trước khi tiếp tục. Kafka client không tự retry commitAsync theo cùng cách commitSync, một phần vì việc gửi lại một commit cũ sau một commit mới có thể làm offset group bị lùi.

Trong chế độ này, **commitRetries không có tác dụng**. Ứng dụng nên quan sát callback, log lỗi và hiểu rằng commit tiếp theo có thể ghi nhận offset mới hơn. Không tự gửi lại một map offset cũ sau khi consumer đã tiếp tục xử lý và commit tiến độ mới.

### 4.3. Bảng so sánh

| Tiêu chí | syncCommits=true | syncCommits=false |
|---|---|---|
| API chính | commitSync | commitAsync |
| Chờ kết quả broker | Có | Không chờ trong lời gọi |
| Callback | Không phải cơ chế chính để nhận kết quả | Có thể nhận kết quả qua commit callback |
| commitRetries | Có áp dụng cho lỗi retriable được hỗ trợ | Không áp dụng |
| Ảnh hưởng latency | Có thể tăng thời gian consumer thread chờ | Ít chờ hơn trong luồng gọi |
| Rủi ro khi tự retry | Container kiểm soát retry commit đồng bộ | Retry commit cũ thủ công có thể ghi đè tiến độ mới |

Lựa chọn đồng bộ hay bất đồng bộ cần dựa trên yêu cầu về commit latency, khả năng quan sát kết quả và hành vi phục hồi. Không nên chuyển sang async chỉ để giảm một chỉ số latency mà không có kế hoạch xử lý callback failure.

## 5. Cấu hình commitRetries trong Spring Kafka

Có thể cấu hình commitRetries trên **ContainerProperties** của listener container factory. Ví dụ:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);

    ContainerProperties properties = factory.getContainerProperties();
    properties.setSyncCommits(true);
    properties.setCommitRetries(5);
    properties.setAckMode(ContainerProperties.AckMode.BATCH);

    return factory;
}
~~~

Trong ví dụ, container sử dụng commit đồng bộ, cho phép tối đa năm lần retry commit theo cơ chế được hỗ trợ và commit offset theo batch sau khi listener xử lý xong các record thuộc poll.

Có thể cấu hình timeout cho commit đồng bộ bằng **syncCommitTimeout**:

~~~java
properties.setSyncCommitTimeout(Duration.ofSeconds(10));
~~~

Kiểu tham số và API setter có thể khác giữa các phiên bản Spring Kafka. Hãy kiểm tra Javadoc của phiên bản đang dùng. Timeout của mỗi lần commit và số lần retry cùng ảnh hưởng đến thời gian container có thể chờ trước khi kết luận commit không hoàn tất.

Nếu dùng Spring Boot, consumer properties như **default.api.timeout.ms** có thể ảnh hưởng timeout mặc định của Kafka client. Khi cấu hình timeout tường minh ở ContainerProperties, cần hiểu giá trị nào đang có hiệu lực.

### 5.1. Cấu hình consumer cơ bản

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      properties:
        default.api.timeout.ms: 10000
~~~

Spring Kafka listener container thường quản lý offset commit thay cho auto commit của consumer. Giữ auto commit tắt giúp container kiểm soát thời điểm commit theo AckMode, retry và transaction. Nếu bật auto commit thủ công, đừng giả định commitRetries sẽ kiểm soát những lần auto commit do Kafka client thực hiện.

## 6. AckMode quyết định khi nào commit xảy ra

commitRetries chỉ có cơ hội hoạt động khi container thực hiện một commit đồng bộ. AckMode quyết định thời điểm và phạm vi offset mà container cần commit.

| AckMode | Thời điểm commit điển hình | Tác động đến commit |
|---|---|---|
| RECORD | Sau khi từng record listener xử lý thành công | Có thể tạo nhiều lần commit hơn |
| BATCH | Sau khi tất cả record trong poll được xử lý thành công | Commit một nhóm offset sau batch |
| TIME | Khi đủ khoảng thời gian cấu hình và có offset cần commit | Commit theo thời gian |
| COUNT | Khi đủ số lượng record cấu hình | Commit theo số lượng |
| COUNT_TIME | Khi đạt điều kiện count hoặc time | Commit theo một trong hai ngưỡng |
| MANUAL | Khi listener acknowledge; container commit theo chu kỳ phù hợp | Listener chủ động báo record đã xử lý |
| MANUAL_IMMEDIATE | Commit ngay khi acknowledge được gọi trên consumer thread | Có thể commit sớm hơn so với MANUAL |

Chi tiết cụ thể còn phụ thuộc record listener hay batch listener, việc gọi acknowledge trên consumer thread hay thread khác, error handler và phiên bản Spring Kafka.

Ví dụ với RECORD:

~~~java
factory.getContainerProperties()
       .setAckMode(ContainerProperties.AckMode.RECORD);
~~~

Ví dụ với BATCH:

~~~java
factory.getContainerProperties()
       .setAckMode(ContainerProperties.AckMode.BATCH);
~~~

Nếu RECORD tạo nhiều commit hơn BATCH, số lần gặp lỗi commit cũng có thể tăng theo số lần commit. Tuy nhiên, BATCH làm phạm vi offset được commit lớn hơn sau một poll; khi batch thất bại, nhiều record có thể phải đọc lại. Hãy chọn AckMode theo delivery semantics và phạm vi xử lý, rồi điều chỉnh commitRetries dựa trên đặc tính commit thực tế.

## 7. Lỗi nào có thể được commitRetries xử lý?

Không phải mọi lỗi trong lúc commit đều có thể được khắc phục bằng cách thử lại cùng thao tác.

### 7.1. RetriableCommitFailedException

Đây là loại lỗi Spring Kafka dùng để nhận biết một số commit failure có thể retry. Ví dụ có thể liên quan đến lỗi tạm thời trong quá trình commit offset hoặc thay đổi trạng thái coordinator mà Kafka client đánh dấu có thể thử lại.

Trong chế độ commit đồng bộ, container có thể thử lại số lần được cấu hình. Nếu commit thành công ở một lần sau, group ghi nhận offset và container tiếp tục hoạt động theo luồng bình thường.

### 7.2. CommitFailedException do mất membership

Nếu consumer không còn là thành viên hợp lệ của group hoặc generation đã thay đổi, commit có thể bị từ chối. Một commit cũ từ consumer đã mất quyền sở hữu partition không nên được ép thực hiện bằng cách retry vô hạn.

Nguyên nhân có thể là rebalance, consumer xử lý quá lâu, session hết hạn hoặc consumer đã bị thu hồi partition. Hướng xử lý là để consumer hoàn tất quá trình rejoin/assignment theo protocol, xác định offset hợp lệ và chấp nhận replay nếu offset chưa được commit.

### 7.3. AuthorizationException

Nếu principal không có quyền commit offset hoặc thao tác liên quan bị từ chối, retry cùng credential và ACL không thay đổi sẽ tiếp tục thất bại. Cần sửa quyền truy cập hoặc cấu hình bảo mật.

### 7.4. Timeout hoặc lỗi kết nối

Timeout có thể xuất hiện khi coordinator hoặc broker phản hồi chậm, hoặc acknowledgement bị mất. Có trường hợp broker đã ghi commit nhưng client không nhận được phản hồi. Vì vậy, kết quả của một lần commit timeout có thể chưa rõ ràng.

Khi container thử lại cùng offset, việc commit cùng một offset về cơ bản không làm group tiến lùi. Tuy nhiên, nếu ứng dụng tự retry một offset cũ sau khi đã có commit mới hơn, nó có thể làm tiến độ group bị lùi. Để container quản lý retry trong đúng luồng commit giúp tránh việc tự tạo thứ tự commit không an toàn.

### 7.5. Phân loại lỗi

| Nhóm lỗi | Ví dụ | commitRetries có giải quyết không? | Hành động |
|---|---|---|---|
| Commit failure retriable | RetriableCommitFailedException | Có, khi syncCommits bật và lỗi thuộc loại được hỗ trợ | Cho container retry trong giới hạn |
| Mất membership/generation | CommitFailedException do rebalance hoặc consumer không còn hợp lệ | Không nên dựa vào retry cùng commit cũ | Rejoin group, xử lý replay và kiểm tra poll/rebalance |
| Quyền truy cập | GroupAuthorizationException hoặc lỗi authorization tương ứng | Không | Sửa ACL/principal |
| Lỗi cấu hình | Cấu hình client hoặc group không hợp lệ | Không | Sửa cấu hình |
| Lỗi kết nối/timeout | Coordinator unavailable, timeout | Chỉ khi được chuyển thành lỗi retriable phù hợp | Kiểm tra broker/network; đánh giá kết quả commit chưa rõ |
| Commit async thất bại | Lỗi trong callback commitAsync | Không | Quan sát callback và để commit mới hơn theo đúng thứ tự |

Tên exception chính xác phụ thuộc Kafka client và Spring Kafka version. Hãy kiểm tra exception gốc và log của consumer thay vì giả định mọi lỗi có chữ "commit" đều thuộc nhóm retry.

## 8. commitRetries và thời gian chờ

Tăng commitRetries có thể tăng khả năng vượt qua một lỗi tạm thời, nhưng cũng có thể làm consumer thread chờ lâu hơn nếu mỗi lần commit mất nhiều thời gian.

Tổng thời gian chờ phụ thuộc:

- Timeout của từng lần commit đồng bộ.
- Số lần thử lại bổ sung.
- Thời gian thực tế broker/coordinator phản hồi.
- Các timeout API của Kafka client.
- Thời gian xử lý và commit khác trong cùng poll cycle.

Ước lượng thô khi mỗi lần commit thường chạm timeout:

~~~
T_commit_budget ≈ (1 + commitRetries) × syncCommitTimeout
~~~

Đây là phép ước lượng bảo thủ, không phải bảo đảm thời gian chính xác. Một số lần retry có thể kết thúc nhanh hơn timeout; các tầng timeout và retry nội bộ của Kafka client cũng có thể làm thời gian thực tế khác đi.

Ví dụ, syncCommitTimeout là 10 giây và commitRetries là 3. Nếu cả bốn lần thử đều gần chạm timeout, consumer có thể dành khoảng 40 giây cho commit. Nếu thời gian đó nằm trong poll cycle, nó có thể góp phần làm consumer tiến gần max.poll.interval.ms.

Không tăng commitRetries mà bỏ qua ngân sách poll. Hãy xem commit latency cùng thời gian xử lý listener, retry/backoff và max.poll.interval.ms. Nếu commit chậm kéo dài, cần điều tra coordinator, broker, network và tình trạng cluster.

## 9. Quan hệ với max.poll.interval.ms và rebalance

Consumer phải tiếp tục gọi poll() theo giới hạn max.poll.interval.ms. Khi xử lý record hoặc chờ commit quá lâu, consumer có thể không poll đúng hạn và bị xem là không còn tiến triển.

Một tình huống:

~~~
poll() nhận batch
      |
      v
Listener xử lý thành công
      |
      v
Container commit offset đồng bộ
      |
      v
Commit gặp lỗi retriable
      |
      v
Container retry commit
      |
      v
Tổng thời gian xử lý + commit quá dài
      |
      v
Consumer vượt max.poll.interval.ms
      |
      v
Group rebalance / partition bị thu hồi
~~~

Nếu commitRetries làm chu kỳ commit kéo dài, nó có thể góp phần gây rebalance. Khi đó retry commit nhiều hơn không nhất thiết cải thiện độ tin cậy tổng thể. Hãy đo:

- Thời gian xử lý listener/batch.
- Commit latency và số lần retry commit.
- Khoảng cách giữa hai lần poll.
- Số lần rebalance và lý do rời group.
- Thời gian coordinator/broker phản hồi.

Nếu thời gian xử lý đã sát max.poll.interval.ms, cần giảm công việc mỗi poll, tối ưu dependency hoặc điều chỉnh timeout có căn cứ. Đừng chỉ tăng commitRetries để cố gắng vượt một cluster đang mất ổn định.

## 10. commitRetries trong transactional listener

Khi listener container dùng Kafka transaction manager, offset input có thể được gửi vào cùng Kafka transaction với record output. Khi đó container không đơn thuần gọi consumer.commitSync() cho offset như luồng non-transactional.

Luồng transactional:

1. Container bắt đầu Kafka transaction.
2. Listener xử lý record và gửi output qua KafkaTemplate.
3. Container đưa offset đã xử lý vào transaction.
4. Producer commit transaction.
5. Kafka commit output records và offset theo cùng transaction.

Nếu transaction commit thất bại, việc xử lý thuộc transaction protocol, producer state và rollback/error handling của Spring Kafka. **commitRetries không phải cơ chế retry transaction commit** và không nên được dùng để suy luận số lần retry của Kafka transaction.

Phân biệt hai trường hợp:

| Cách chạy | Cách offset được ghi | Vai trò commitRetries |
|---|---|---|
| Listener non-transactional, sync commit | Consumer.commitSync() | Có thể retry commit failure retriable được hỗ trợ |
| Listener transactional với KafkaTransactionManager | Offset được gửi vào producer transaction | Không điều khiển việc retry/commit Kafka transaction |
| Container dùng async commit | Consumer.commitAsync() | Không áp dụng |

Nếu transaction abort, offset không được commit cùng output. Record đầu vào có thể được xử lý lại; side effect ngoài Kafka vẫn cần idempotency hoặc cơ chế phối hợp tài nguyên riêng.

## 11. Quan sát commit và phát hiện vấn đề

Một dashboard consumer tốt cần thể hiện riêng thời gian xử lý và thời gian commit. Nếu chỉ theo dõi consumer lag, khó phân biệt listener chậm với coordinator commit chậm.

Các tín hiệu hữu ích:

| Tín hiệu | Ý nghĩa |
|---|---|
| Commit latency | Thời gian commit đồng bộ hoặc thời gian phản hồi callback |
| Commit failure count | Số lần commit không thành công |
| Retriable commit failure count | Tần suất lỗi commit có thể retry |
| Commit retry attempts | Số lần container phải thử lại |
| Commit callback error | Kết quả commit bất đồng bộ thất bại |
| Committed offset progress | Offset group có tiếp tục tiến lên không |
| Consumer lag | Khoảng cách giữa log end và committed offset |
| Rebalance count/duration | Commit chậm hoặc poll chậm có làm group thay đổi liên tục không |
| Coordinator/network errors | Có sự cố phía Kafka hoặc kết nối không |

Tên metric phụ thuộc Kafka client, Spring Kafka, Micrometer và exporter. Không giả định mọi phiên bản đều export metric riêng cho commitRetries; nếu cần đo chính xác số lần retry, có thể dùng log/observation phù hợp hoặc instrumentation tại lớp quản lý container mà không làm thay đổi luồng commit.

### 11.1. Log commit có ích

Log nên ghi:

- Consumer group ID.
- Topic và partition liên quan.
- Offset đang được commit.
- Loại exception gốc.
- Số lần retry nếu có thể quan sát.
- Thời gian commit và kết quả cuối cùng.
- Consumer ID/client ID để liên hệ với member cụ thể.

Tránh log payload hoặc thông tin xác thực. Offset và topic thường đủ để tra cứu record trong môi trường vận hành có quyền truy cập phù hợp.

### 11.2. Dùng CLI để xác nhận tiến độ

Có thể kiểm tra committed offset và lag bằng:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group billing-service
~~~

Nếu commit retries tăng nhưng committed offset vẫn tiến triển, lỗi có thể là tạm thời và container đã phục hồi. Nếu offset đứng yên, hãy kiểm tra group state, member assignment, lỗi commit cuối cùng và listener processing. Nếu group không có member, cần xác định consumer đã dừng hay đang trong quá trình khởi động lại.

## 12. Kiểm thử commitRetries

Kiểm thử nên tập trung vào hành vi của offset và group khi commit gặp lỗi, không chỉ kiểm tra rằng cấu hình đã được gán.

Các tình huống có thể kiểm thử trong môi trường Kafka thử nghiệm:

1. **Commit thành công bình thường:** xử lý record, commit offset và xác nhận group tiến lên.
2. **Coordinator tạm thời không sẵn sàng:** tạo lỗi commit retriable có kiểm soát, quan sát container retry và phục hồi khi coordinator sẵn sàng.
3. **Rebalance trong lúc xử lý:** xác nhận commit cũ không được ép thực hiện sau khi consumer mất membership; record được replay theo committed offset.
4. **Authorization lỗi:** xác nhận retry không che giấu lỗi ACL và cảnh báo được phát.
5. **Async commit:** đặt syncCommits=false, xác nhận commitRetries không tham gia và callback được quan sát.
6. **Transactional listener:** xác nhận output và offset cùng commit/abort; không nhầm commitRetries với transaction retry.
7. **Poll interval:** tạo commit delay đủ lớn để xem ảnh hưởng đến nhịp poll và rebalance.

Không nên mô phỏng lỗi production bằng cách ngắt broker tùy tiện trên cluster dùng chung. Dùng môi trường thử nghiệm, fault injection có giới hạn hoặc công cụ kiểm thử được phê duyệt.

## 13. Chọn giá trị commitRetries

Không có một giá trị tối ưu cho mọi consumer group. Giá trị cần cân bằng giữa khả năng chịu lỗi commit tạm thời và thời gian consumer thread có thể chờ.

Các yếu tố quyết định:

- Độ ổn định của broker và group coordinator.
- Tần suất lỗi retriable commit quan sát được.
- Timeout đồng bộ cho mỗi lần commit.
- max.poll.interval.ms và ngân sách xử lý một poll.
- AckMode và tần suất commit.
- Tác động của commit chậm lên lag và rebalance.
- Có sử dụng transaction hay async commit không.

Nếu cluster ổn định và commit failure hiếm, giá trị mặc định thường là điểm bắt đầu hợp lý. Nếu tăng retry, cần đo tỷ lệ phục hồi sau retry và tổng thời gian chờ. Nếu phần lớn lỗi là authorization hoặc mất membership, tăng số retry không giải quyết nguyên nhân.

Không nên đặt commitRetries rất lớn với hy vọng consumer sẽ luôn commit thành công. Một consumer đã mất quyền sở hữu partition không nên cố ghi offset cũ. Một cluster mất kết nối kéo dài cần cảnh báo và phục hồi hạ tầng, không cần một vòng lặp commit dài vô hạn.

## 14. Các lỗi cấu hình thường gặp

| Cách làm | Hậu quả | Cách xử lý |
|---|---|---|
| Đặt commitRetries nhưng syncCommits=false | Cấu hình không có tác dụng | Bật sync commit nếu cần cơ chế retry này hoặc xử lý async callback |
| Nghĩ commitRetries retry listener | Hiểu sai số lần nghiệp vụ được thực hiện | Dùng error handler/retry policy cho listener |
| Tăng commitRetries để xử lý ACL | Lỗi vẫn tồn tại, chỉ làm chậm cảnh báo | Sửa authorization và credential |
| Retry commit cũ sau khi đã có commit mới | Có thể làm committed offset lùi | Để container quản lý thứ tự commit; tránh replay commitAsync cũ |
| Tăng timeout và retries mà không tính poll interval | Consumer có thể vượt max.poll.interval.ms | Tính ngân sách xử lý + commit và theo dõi rebalance |
| Dùng commitRetries cho transactional listener | Nhầm lẫn giữa consumer commitSync và transaction commit | Dùng cơ chế rollback/transaction handling của Spring Kafka |
| Commit offset trước khi side effect hoàn tất | Lag giảm nhưng nghiệp vụ có thể mất | Chọn AckMode và thời điểm commit phù hợp |
| Chỉ theo dõi lag | Không phân biệt được xử lý chậm với commit chậm | Theo dõi commit latency, failure và processing latency riêng |

## 15. Checklist vận hành commitRetries

Trước khi cấu hình hoặc điều tra commit failure, hãy xác định:

1. Listener container đang dùng syncCommits hay async commit?
2. commitRetries đang đặt bao nhiêu và phiên bản Spring Kafka có hỗ trợ cấu hình này như thế nào?
3. Exception gốc có phải lỗi commit retriable mà container hỗ trợ không?
4. Timeout của từng lần commit có phù hợp với ngân sách poll không?
5. AckMode hiện tại commit theo record, batch, thời gian hay manual?
6. Consumer có còn là thành viên hợp lệ của group và còn sở hữu partition không?
7. Có lỗi coordinator, broker, network hoặc authorization không?
8. Consumer lag và committed offset có tiến triển sau khi retry không?
9. Side effect có an toàn khi record được đọc lại sau commit failure không?
10. Nếu dùng transaction hoặc async commit, cơ chế phục hồi đúng của chế độ đó là gì?

commitRetries là một lớp bảo vệ hẹp cho thao tác commit offset đồng bộ trong Spring Kafka. Cấu hình đúng giúp container vượt qua một số lỗi commit tạm thời, nhưng hiệu quả phụ thuộc syncCommits, loại exception, timeout, AckMode và trạng thái consumer group. Khi offset không tiến triển, hãy điều tra coordinator, rebalance và thời gian xử lý trước khi tăng số lần retry; đồng thời giữ consumer idempotent để xử lý an toàn khi record được phát lại.
