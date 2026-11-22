# Phân biệt consumer lag bằng số bản ghi với độ trễ nghiệp vụ

Consumer lag và độ trễ nghiệp vụ đều giúp đánh giá khả năng theo kịp luồng sự kiện, nhưng chúng đo hai điều khác nhau. **Consumer lag theo offset** cho biết vị trí đọc hoặc vị trí đã commit của consumer cách cuối log bao nhiêu offset. **Độ trễ nghiệp vụ** cho biết một sự kiện mất bao lâu từ thời điểm xảy ra đến khi ứng dụng hoàn thành xử lý hoặc tạo ra kết quả nghiệp vụ.

Một consumer có thể có lag lớn trong lúc đang bắt kịp một đợt tải đột biến, nhưng vẫn xử lý các sự kiện mới trong giới hạn thời gian chấp nhận được. Ngược lại, lag có thể gần bằng 0 trong khi quy trình nghiệp vụ vẫn chậm do xử lý bất đồng bộ, chờ dịch vụ ngoài hoặc commit offset trước khi công việc hoàn tất. Vì vậy, không dùng một chỉ số thay cho chỉ số còn lại.

## 1. Consumer lag theo offset đo điều gì?

Kafka gán offset tăng dần cho record trong từng partition. Offset là vị trí trong log của partition, không phải số thứ tự toàn cục của topic. Khi consumer xử lý một partition, nó có một vị trí đọc hiện tại và group có thể lưu một committed offset để ghi nhớ vị trí tiếp tục ở lần chạy sau.

Committed offset trong Kafka biểu thị **offset kế tiếp cần đọc**, không phải offset cuối cùng đã xử lý. Ví dụ, nếu consumer đã xử lý record có offset `41` và commit `42`, lần tiếp tục sẽ bắt đầu từ offset `42`.

Một cách biểu diễn phổ biến của lag là:

\[
\text{offset lag} = \text{end offset} - \text{committed offset}
\]

Giả sử end offset của partition là `1.000` và group đã commit `920`. Offset distance là `80`. Có thể diễn giải consumer đang cách điểm cuối nhìn thấy 80 vị trí offset. Tuy nhiên, không nên tự động kết luận chắc chắn còn đúng 80 record thực tế đang chờ xử lý.

Trong lúc consumer đang chạy, cần phân biệt hai cách đo:

- **Committed lag:** end offset trừ committed offset của consumer group. Chỉ số này thể hiện tiến độ đã được lưu bền vững cho group.
- **Position lag:** end offset trừ `position()` hiện tại của consumer. `position()` là vị trí tiếp theo mà consumer sẽ trả về khi poll; nó có thể tiến xa hơn committed offset nếu ứng dụng đã đọc record nhưng chưa commit.

Committed lag phù hợp để xem tiến độ có thể phục hồi sau restart. Position lag hữu ích khi chẩn đoán consumer đang chạy. Nếu ứng dụng xử lý bất đồng bộ, cả hai chỉ số vẫn có thể không phản ánh chính xác số công việc đang thực sự nằm trong hàng đợi nội bộ hoặc đang được xử lý dở.

## 2. Vì sao offset distance không luôn bằng số record đang chờ?

Offset tăng theo vị trí record được ghi vào log, nhưng log Kafka có thể có khoảng trống offset mà consumer không nhận được như một record thông thường. Một số nguyên nhân gồm:

- **Log compaction:** Kafka có thể loại bỏ phiên bản cũ của key trong quá trình compact. Offset không được đánh lại số sau khi record bị loại bỏ.
- **Giao dịch bị abort:** record thuộc giao dịch bị hủy không được consumer `read_committed` trả về như record đã commit, dù vị trí offset vẫn tồn tại trong log.
- **Control record và cấu trúc nội bộ:** log có thể chứa các record phục vụ giao dịch hoặc điều khiển mà ứng dụng không nhìn thấy như một event thông thường.
- **Retention và xóa dữ liệu:** dữ liệu cũ có thể bị xóa theo thời gian hoặc kích thước; offset vẫn là không gian vị trí của log, không được đánh lại từ 0.

Vì thế, hiệu `end offset - committed offset` là khoảng cách vị trí. Với topic không compact và không có các khoảng trống liên quan, nó có thể gần với số record còn lại. Với topic compacted hoặc dùng giao dịch, nó có thể khác đáng kể. Các công cụ hiển thị cột `LAG` thường tính từ offset; cần xem định nghĩa của công cụ và phiên bản đang dùng.

Ngoài ra, lag tổng của group có thể che khuất partition bị nghẽn. Ví dụ, ba partition có lag lần lượt là `0`, `0`, `900`; tổng là `900`, nhưng vấn đề tập trung ở partition thứ ba. Nếu chỉ theo dõi trung bình, một partition bị đói consumer hoặc một key nóng có thể bị che lấp.

## 3. End offset nào được dùng để tính lag?

“Điểm cuối log” cũng cần được định nghĩa rõ. Với partition Kafka, một số mốc thường gặp là:

- **Log End Offset (LEO):** vị trí cuối của log trên replica, tức offset kế tiếp sau phần log hiện có ở replica đó.
- **High Watermark (HW):** ranh giới dữ liệu đã được sao chép/đánh dấu commit theo cơ chế replication của partition. Consumer `read_uncommitted` chỉ đọc dữ liệu đến ranh giới có thể đọc tương ứng với HW.
- **Last Stable Offset (LSO):** ranh giới đọc ổn định cho consumer `read_committed`; nó không vượt qua giao dịch đang mở sớm nhất có thể ảnh hưởng đến tính ổn định của dữ liệu.

Với consumer `read_committed`, end offset mà API `endOffsets()` trả về là LSO. Với `read_uncommitted`, end offset phản ánh ranh giới đọc thông thường dựa trên HW. Các công cụ quản trị và exporter có thể dùng nguồn end offset khác nhau, ví dụ LEO hoặc HW. Vì vậy, lag từ hai dashboard có thể không giống nhau dù cùng theo dõi một group.

Khi so sánh lag, hãy ghi rõ:

1. Offset bắt đầu là committed offset hay position hiện tại.
2. End offset lấy từ LEO, HW hay LSO.
3. Consumer dùng `read_committed` hay `read_uncommitted`.
4. Công cụ tính lag theo từng partition, tổng group hay max partition.

Không so sánh trực tiếp hai con số lag nếu các nguồn dùng định nghĩa khác nhau.

## 4. Độ trễ nghiệp vụ đo điều gì?

Độ trễ nghiệp vụ đo thời gian từ khi một sự kiện xảy ra trong miền nghiệp vụ đến khi hệ thống hoàn thành hành động cần thiết. Ví dụ, với sự kiện `OrderPlaced`, thời điểm bắt đầu có thể là lúc khách hàng đặt hàng; thời điểm kết thúc có thể là lúc hệ thống xác nhận thanh toán và cập nhật trạng thái đơn hàng.

Có thể tách thành các khoảng thời gian để tìm đúng nút thắt:

| Chỉ số thời gian | Cách tính | Ý nghĩa |
|---|---|---|
| Event age khi consume | Thời điểm consumer bắt đầu xử lý trừ thời điểm sự kiện xảy ra | Sự kiện đã cũ bao lâu khi tới ứng dụng |
| Kafka residence time | Thời điểm consumer nhận record trừ thời điểm broker append record | Thời gian record nằm trong Kafka, nếu timestamp phản ánh append time |
| Processing duration | Thời điểm xử lý xong trừ thời điểm bắt đầu xử lý | Thời gian ứng dụng xử lý record |
| Downstream wait | Thời điểm hoàn tất bước nghiệp vụ trừ thời điểm consumer bắt đầu xử lý, sau khi trừ các khoảng xử lý nội bộ nếu đo riêng | Thời gian chờ database, API hoặc hệ thống phụ thuộc |
| End-to-end business latency | Thời điểm hoàn thành nghiệp vụ trừ thời điểm sự kiện xảy ra | Thời gian người dùng hoặc hệ thống nghiệp vụ thực sự phải chờ |

Ví dụ, khách hàng đặt đơn lúc `10:00:00`, record được broker append lúc `10:00:01`, consumer nhận lúc `10:00:03`, xử lý xong lúc `10:00:04`, nhưng thanh toán bên ngoài chỉ xác nhận lúc `10:00:12`. Consumer chỉ mất một giây để xử lý, Kafka residence khoảng hai giây, còn độ trễ nghiệp vụ là mười hai giây. Nếu chỉ nhìn lag theo offset hoặc processing duration, thời gian chờ thanh toán có thể bị bỏ sót.

## 5. Timestamp phải có ý nghĩa rõ ràng

Kafka record có timestamp, nhưng timestamp đó không mặc nhiên là thời điểm nghiệp vụ xảy ra. Cần phân biệt:

- `CreateTime`: timestamp do producer gắn vào record. Nó có thể đại diện thời điểm tạo record ở producer, hoặc được ứng dụng đặt theo thời điểm sự kiện xảy ra.
- `LogAppendTime`: broker gán timestamp khi append record vào log nếu topic/broker được cấu hình dùng chế độ này.
- `eventOccurredAt`: thời điểm xảy ra sự kiện trong miền nghiệp vụ, thường được lưu rõ trong payload hoặc metadata hợp đồng.
- `processingStartedAt` và `processingCompletedAt`: thời điểm ứng dụng bắt đầu và hoàn tất xử lý.

Nếu dùng Kafka timestamp để tính event age, hãy xác nhận `TimestampType` và cấu hình `message.timestamp.type` của topic/broker. Với `CreateTime`, đồng hồ producer có thể lệch so với consumer. Với `LogAppendTime`, timestamp phản ánh thời điểm broker ghi nhận record, không thể thay thế thời điểm sự kiện xảy ra trước khi publish.

Để đo độ trễ nghiệp vụ, nên đưa trường thời gian có ý nghĩa rõ ràng như `occurredAt` vào event contract. Dùng UTC và định dạng nhất quán (ví dụ ISO-8601 hoặc epoch milliseconds). Đồng bộ đồng hồ giữa các máy bằng NTP hoặc cơ chế tương đương. Nếu đồng hồ lệch, phép trừ timestamp có thể âm hoặc tạo ra latency giả.

Đối với thời gian xử lý bên trong một tiến trình, dùng `System.nanoTime()` để đo duration vì nó là đồng hồ monotonic, không bị điều chỉnh như wall clock. Dùng `Instant.now()` hoặc đồng hồ wall clock đã đồng bộ khi cần so sánh mốc thời gian giữa các hệ thống.

## 6. Các tình huống lag và độ trễ nghiệp vụ không đồng nhất

| Tình huống | Lag theo offset | Độ trễ nghiệp vụ | Cách diễn giải |
|---|---|---|---|
| Tải tăng đột biến, consumer đang bắt kịp | Cao và có thể tăng nhanh | Có thể vẫn thấp nếu event mới được xử lý đúng hạn | Xem tốc độ tăng/giảm lag và latency theo cohort sự kiện |
| Một partition ít traffic nhưng có một event cũ | Có thể rất thấp | Có thể cao | Đo tuổi của event thực tế, không chỉ nhìn số offset |
| Consumer commit trước khi xử lý xong | Thấp hoặc bằng 0 | Có thể cao hoặc event chưa hoàn tất | Lag dựa trên committed offset không thấy công việc đang bay |
| Consumer đọc nhanh nhưng downstream chậm | Có thể thấp nếu offset được tiến/commit | Cao | Đo thời gian chờ downstream và thời điểm hoàn thành nghiệp vụ |
| Topic compacted hoặc có aborted transaction | Offset distance có thể cao hơn số record đọc được | Có thể thấp | Offset gap không tương đương số event thực tế |
| Một partition bị nghẽn, partition khác rảnh | Tổng lag có thể bị trung bình hóa | Một nhóm nghiệp vụ có thể trễ cao | Xem lag và latency theo partition/key/event type |
| Replay từ offset cũ | Lag tăng đột ngột | Event age có thể rất cao dù replay đang chạy đúng kế hoạch | Gắn nhãn replay và tách SLO phát lại khỏi SLO realtime |

Hai ví dụ thường gặp cần chú ý:

**Lag cao nhưng độ trễ vẫn trong SLO:** một topic nhận burst 100.000 sự kiện trong vài giây. Consumer xử lý nhanh hơn tốc độ đến sau burst và lag đang giảm. Nếu các event quan trọng vẫn hoàn thành trong giới hạn nghiệp vụ, cảnh báo chỉ dựa trên lag tuyệt đối có thể gây nhiễu. Hãy quan sát tốc độ drain và p95/p99 event age.

**Lag thấp nhưng nghiệp vụ chậm:** consumer nhận record, đưa công việc vào executor rồi commit offset ngay. Executor bị nghẽn hoặc API thanh toán phản hồi chậm. Group lag gần bằng 0 vì Kafka đã ghi nhận tiến độ, nhưng các công việc chưa hoàn tất vẫn tồn tại trong hàng đợi ứng dụng. Cần đo số công việc in-flight, thời gian chờ executor, downstream latency và business completion.

## 7. Đo lag theo consumer group bằng công cụ Kafka

Lệnh `kafka-consumer-groups.sh --describe` hiển thị committed offset, log end offset và lag theo partition:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server broker-1:9092 \
  --command-config admin.properties \
  --group order-service \
  --describe
```

Kết quả thường có các cột:

| Cột | Ý nghĩa |
|---|---|
| `TOPIC` | Topic đang được group tiêu thụ |
| `PARTITION` | Partition tương ứng |
| `CURRENT-OFFSET` | Committed offset của group, tức vị trí tiếp theo cần đọc |
| `LOG-END-OFFSET` | End offset được công cụ dùng làm mốc so sánh |
| `LAG` | Khoảng cách offset giữa end offset và committed offset |
| `CONSUMER-ID`, `HOST`, `CLIENT-ID` | Thông tin consumer đang được gán partition nếu có |

Chạy lệnh nhiều lần để xem xu hướng. Một snapshot cho biết trạng thái tại một thời điểm; chuỗi snapshot mới cho thấy lag đang tăng, giảm hay ổn định. Nếu group không có committed offset hoặc partition chưa có consumer assignment, kết quả có thể hiển thị giá trị đặc biệt hoặc không có lag; cần xác định trạng thái group trước khi kết luận.

### Metric ở Kafka consumer client

Kafka consumer client cũng xuất các metric qua JMX. Một số metric thường dùng gồm:

| Metric | Ý nghĩa và cách dùng |
|---|---|
| `records-lag-max` | Giá trị lag lớn nhất trong các partition consumer đang theo dõi |
| `records-lag-avg` | Giá trị lag trung bình trên các partition consumer đang theo dõi |
| `records-consumed-rate` | Tốc độ record được consumer nhận |
| `records-consumed-total` | Tổng số record consumer đã nhận kể từ khi khởi tạo metric |
| `fetch-rate` và `fetch-latency-avg/max` | Tốc độ và thời gian phản hồi fetch request |
| `commit-latency-avg/max` | Thời gian thực hiện commit offset |
| `rebalance-latency-avg/max` | Thời gian hoàn tất rebalance nếu metric có trong phiên bản client |
| `heartbeat-rate` và `heartbeat-response-time-max` | Nhịp heartbeat và thời gian phản hồi heartbeat của group coordinator |

Metric lag của client thường dựa trên offset và phạm vi partition mà consumer đang quan sát; nó không đo thời gian nghiệp vụ. Tên metric, nhóm JMX và cách exporter chuẩn hóa tên có thể khác theo phiên bản. Hãy kiểm tra metric do client đang chạy thực sự xuất ra và đối chiếu với định nghĩa của phiên bản đó.

Với ứng dụng cần đo cả committed lag và position lag, có thể dùng Java Consumer API. Ví dụ sau chỉ minh họa phép đo cho các partition đang được consumer hiện tại assign:

```java
import java.util.Map;
import java.util.Set;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

void reportLag(Consumer<String, OrderEvent> consumer) {
    Set<TopicPartition> assigned = consumer.assignment();
    if (assigned.isEmpty()) {
        return;
    }

    Map<TopicPartition, OffsetAndMetadata> committed =
        consumer.committed(assigned);
    Map<TopicPartition, Long> ends = consumer.endOffsets(assigned);
    Map<TopicPartition, Long> beginnings =
        consumer.beginningOffsets(assigned);

    for (TopicPartition partition : assigned) {
        OffsetAndMetadata saved = committed.get(partition);
        if (saved == null) {
            // Group chưa có committed offset; áp dụng reset policy.
            continue;
        }

        long committedNextOffset = saved.offset();
        long endOffset = ends.get(partition);
        long beginningOffset = beginnings.get(partition);

        if (committedNextOffset < beginningOffset
                || committedNextOffset > endOffset) {
            // Offset đã commit nằm ngoài phạm vi log hiện tại.
            continue;
        }

        long committedLag = endOffset - committedNextOffset;
        long currentPosition = consumer.position(partition);
        long positionLag = Math.max(0L, endOffset - currentPosition);

        System.out.printf(
            "%s committedLag=%d positionLag=%d%n",
            partition, committedLag, positionLag
        );
    }
}
```

Đoạn mã phải được gọi trong luồng sở hữu `KafkaConsumer`; Kafka Consumer không an toàn cho việc nhiều thread gọi đồng thời. Nếu cần quan sát toàn bộ group từ một service riêng, nên dùng Admin API để lấy group offsets và end offsets thay vì tạo consumer giành assignment với group thật.

Lưu ý: `endOffsets()` phụ thuộc `isolation.level` của consumer. Với `read_committed`, mốc end là LSO; với `read_uncommitted`, mốc đọc là HW. So sánh kết quả này với exporter đang dùng LEO hoặc HW có thể tạo ra chênh lệch hợp lệ.

## 8. Đo event age và độ trễ nghiệp vụ trong Java

Một cách thực tế là lưu thời điểm xảy ra sự kiện trong payload và đo tại các mốc xử lý:

```java
import java.time.Duration;
import java.time.Instant;

void handle(OrderEvent event) {
    Instant processingStartedAt = Instant.now();

    Duration eventAgeAtStart = Duration.between(
        event.occurredAt(), processingStartedAt
    );

    long startNanos = System.nanoTime();
    paymentService.authorize(event);
    orderService.markPaid(event.orderId());
    long processingNanos = System.nanoTime() - startNanos;

    Instant processingCompletedAt = Instant.now();
    Duration businessLatency = Duration.between(
        event.occurredAt(), processingCompletedAt
    );

    metrics.recordEventAge(eventAgeAtStart);
    metrics.recordProcessingDuration(Duration.ofNanos(processingNanos));
    metrics.recordBusinessLatency(businessLatency);
}
```

`event.occurredAt()` là thời điểm nghiệp vụ đã được xác định trong hợp đồng event, không phải thời điểm consumer tự tạo khi nhận record. `eventAgeAtStart` đo tuổi event lúc bắt đầu xử lý; `processingDuration` đo thời gian xử lý trong tiến trình; `businessLatency` đo đến lúc hoàn tất hai thao tác minh họa. Nếu nghiệp vụ còn chờ callback hoặc bước xử lý bất đồng bộ, chỉ ghi nhận hoàn tất sau khi bước cuối cùng thực sự thành công.

Trong thực tế, không nhất thiết ghi mọi timestamp vào log. Nên xuất histogram cho event age, processing duration và end-to-end latency; gắn nhãn có cardinality thấp như topic, event type, consumer group và kết quả. Không dùng order ID, correlation ID hoặc user ID làm label metric vì sẽ tạo cardinality rất lớn. Có thể đưa ID vào trace hoặc log có kiểm soát để điều tra từng trường hợp.

## 9. Đánh giá backlog và năng lực xử lý

Lag là một gauge; tốc độ tăng/giảm của lag thường hữu ích hơn một con số riêng lẻ. Gọi:

- `λ` là tốc độ record đến (records/second) theo partition hoặc group.
- `μ` là tốc độ record consumer xử lý (records/second).
- `B` là backlog ước lượng theo offset distance.

Khi `μ` lớn hơn `λ`, consumer có khả năng làm giảm backlog. Nếu tốc độ ổn định và các điều kiện không đổi, thời gian drain gần đúng có thể ước lượng:

\[
T_{drain} \approx \frac{B}{\mu - \lambda}
\]

Ví dụ, backlog là 60.000 offset, tốc độ xử lý 5.000 record/giây và tốc độ đến 2.000 record/giây. Thời gian drain xấp xỉ `60.000 / (5.000 - 2.000) = 20` giây. Đây chỉ là ước lượng thô: offset distance có thể khác số record thực tế, tốc độ xử lý thay đổi theo payload, partition và downstream, còn consumer có thể bị giới hạn bởi số partition được assign.

Nếu `μ` nhỏ hơn hoặc bằng `λ` trong thời gian dài, backlog sẽ không được giải quyết bằng cách chờ. Cần tìm nguyên nhân giới hạn: consumer thiếu instance, số partition không đủ để tăng song song, key nóng, xử lý tuần tự, batch/poll không phù hợp, downstream chậm, lỗi retry hoặc rebalance liên tục.

Không tăng consumer instance một cách mù quáng. Trong consumer group truyền thống, một partition tại một thời điểm chỉ được assign cho tối đa một consumer trong group. Nếu group đã có số consumer bằng hoặc lớn hơn số partition, thêm instance có thể không tăng khả năng xử lý.

## 10. Replay và cách diễn giải lag

Khi reset offset hoặc replay dữ liệu cũ, lag theo offset có thể tăng mạnh vì group quay về vị trí trước đó. Điều này không nhất thiết là sự cố. Cần phân biệt luồng realtime với luồng replay:

- Ghi nhận thời điểm và lý do reset offset, partition bị ảnh hưởng, offset cũ và offset mới.
- Theo dõi tốc độ replay, backlog còn lại và thời gian dự kiến hoàn tất.
- Đo event age của record đang phát lại; event age có thể lớn vì record được tạo từ nhiều giờ hoặc nhiều ngày trước.
- Tách SLO xử lý realtime khỏi tiến độ replay nếu hai luồng có mục tiêu khác nhau.
- Bảo đảm thao tác replay không làm consumer realtime hoặc downstream vượt quá năng lực phục vụ.

Nếu replay dùng cùng group, committed offset của group thay đổi theo tiến trình phát lại và dashboard lag sẽ phản ánh vị trí mới. Nếu dùng group riêng, dashboard cần gắn đúng group ID để không nhầm lag replay với lag realtime. Với các quy trình cập nhật trạng thái nghiệp vụ, cần idempotence hoặc cơ chế chống xử lý trùng vì replay có thể phát lại event đã từng được xử lý.

## 11. Xây dựng cảnh báo có ý nghĩa

Không nên đặt cảnh báo chỉ dựa vào `LAG > 1000` cho mọi topic. Một nghìn offset có thể là vài giây với topic có lưu lượng cao, nhưng có thể là nhiều giờ với topic ít traffic; trên topic compacted, offset distance còn không tương ứng số record thực tế.

Một bộ cảnh báo cân bằng có thể gồm:

| Nhóm | Chỉ số nên theo dõi | Câu hỏi vận hành |
|---|---|---|
| Tiến độ group | Committed lag theo partition, tổng lag, max lag | Group đang tụt lại ở partition nào? |
| Xu hướng backlog | Tốc độ tăng/giảm lag, arrival rate, processing rate | Consumer có đang bắt kịp không? |
| Độ mới của dữ liệu | Tuổi record cũ nhất đang chờ, event age khi consume | Sự kiện đang chờ bao lâu? |
| Kết quả nghiệp vụ | End-to-end latency p95/p99, tỷ lệ hoàn tất đúng hạn | Người dùng có nhận kết quả đúng hạn không? |
| Sức khỏe consumer | Poll interval, rebalance, commit failure, retry, in-flight work | Vì sao tiến độ bị chậm hoặc báo sai? |
| Downstream | Database/API latency, timeout, queue depth, lỗi | Consumer có đang chờ hệ thống phụ thuộc không? |

Ví dụ chính sách:

- Cảnh báo khi business latency p99 vượt SLO trong nhiều cửa sổ liên tiếp.
- Cảnh báo khi event age của record đang chờ vượt ngưỡng tối đa cho phép, kể cả khi offset lag nhỏ.
- Cảnh báo khi lag tăng liên tục và processing rate không vượt arrival rate trong một khoảng đủ dài.
- Cảnh báo khi committed lag thấp nhưng số công việc in-flight, executor queue hoặc downstream wait tăng bất thường.
- Cảnh báo theo max partition lag để phát hiện một partition nóng hoặc consumer không được assign.

Chọn ngưỡng theo SLO, baseline và đặc tính từng topic. Topic giao dịch thời gian thực, topic audit và topic replay thường có yêu cầu độ trễ khác nhau.

## 12. Quy trình điều tra khi lag hoặc độ trễ tăng

1. Xác định group, topic và partition bị ảnh hưởng; kiểm tra lag theo từng partition thay vì chỉ nhìn tổng.
2. Lấy committed offset, current position và end offset; xác định nguồn end offset là LEO, HW hay LSO.
3. Đo tốc độ record đến và tốc độ xử lý. Nếu lag tăng, kiểm tra `μ` có thấp hơn `λ` không.
4. Kiểm tra event age của các record mới được xử lý và thời điểm hoàn thành nghiệp vụ. So sánh event age với processing duration để tách thời gian chờ khỏi thời gian thực thi.
5. Kiểm tra consumer assignment, số partition, rebalance, poll loop, commit failure, retry và hàng đợi bất đồng bộ.
6. Kiểm tra downstream latency, timeout, connection pool, database lock và giới hạn tài nguyên.
7. Xem cấu hình `isolation.level`, compaction, transaction và retention để giải thích khoảng cách offset bất thường.
8. Nếu đang replay, xác nhận reset offset và group ID; so sánh tiến độ replay với SLO realtime riêng.

Khi sửa, thay đổi từng yếu tố và quan sát cả lag lẫn business latency. Tăng tốc độ poll có thể làm position lag giảm nhưng không làm nghiệp vụ hoàn tất nhanh hơn nếu bottleneck nằm ở database. Tăng consumer count cũng không giúp nếu partition không đủ hoặc downstream đã quá tải.

## 13. Nguyên tắc lựa chọn chỉ số

Dùng offset lag để theo dõi vị trí đọc đã commit hoặc vị trí consumer hiện tại so với điểm cuối log. Dùng event age để biết record đã cũ bao lâu khi được xử lý. Dùng processing duration để đo hiệu năng code và end-to-end business latency để xác nhận kết quả mà nghiệp vụ cần.

Một hệ thống Kafka khỏe không nhất thiết luôn có lag bằng 0. Điều quan trọng là backlog nằm trong khả năng drain, sự kiện được xử lý trong SLO, các partition không bị nghẽn kéo dài và offset chỉ được commit theo đúng ngữ nghĩa hoàn tất mà ứng dụng cam kết. Khi các chỉ số này được đo riêng và đối chiếu với nhau, đội vận hành có thể phân biệt tải tăng bình thường với độ trễ nghiệp vụ thực sự.
