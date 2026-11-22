# Seek sau lỗi

Trong Spring Kafka, khi listener xử lý một record và ném exception, consumer cần quay lại đúng vị trí để thử xử lý lại record đó hoặc chuyển nó sang luồng phục hồi. Cơ chế seek đặt lại vị trí đọc của một partition về offset được chọn. `DefaultErrorHandler` sử dụng seek để đưa record lỗi và các record chưa được xử lý trong poll trở lại luồng đọc, theo chính sách retry và recovery đã cấu hình.

Seek sau lỗi là một phần quan trọng của blocking retry. Nó cho phép listener container đọc lại record từ Kafka sau khi backoff kết thúc, thay vì tự tăng offset qua record lỗi. Khi hiểu đúng seek, committed offset và consumer position, đội phát triển có thể tránh mất record, kiểm soát thứ tự xử lý và chẩn đoán hiện tượng record được giao lại.

## 1. Seek là gì trong Kafka consumer?

Mỗi partition có một dãy offset tăng dần. Consumer duy trì **position** cho biết offset tiếp theo sẽ được đọc khi poll. Consumer group cũng có **committed offset** được lưu bền vững để member mới hoặc consumer khởi động lại biết cần tiếp tục từ đâu.

Hai khái niệm này khác nhau:

- **Consumer position** là vị trí đọc hiện tại trong consumer đang chạy. Gọi `seek()` thay đổi position của consumer đó.
- **Committed offset** là checkpoint đã được group lưu. Nó được dùng khi consumer khởi động lại hoặc partition được giao cho member khác.

Ví dụ consumer đang đọc partition `orders-0`:

~~~text
Committed offset: 100
Consumer position: 103

Đã poll:
  offset 100
  offset 101
  offset 102

seek(partition, 101)
        |
        v
Consumer position: 101
        |
        v
Poll tiếp theo có thể nhận lại:
  offset 101
  offset 102
  ...
~~~

Seek thay đổi position trong consumer hiện tại; nó không tự ghi committed offset mới lên broker. Nếu consumer dừng trước khi commit một offset mới, lần khởi động sau sẽ tiếp tục từ committed offset gần nhất. Vì vậy, cần xem xét cả position, commit và assignment khi điều tra record được đọc lại.

### 1.1. Vì sao phải seek khi listener thất bại?

Giả sử consumer poll các record offset 100, 101 và 102. Listener xử lý 100 thành công nhưng thất bại ở 101. Nếu consumer cứ tiếp tục từ 103 mà không lưu hoặc phục hồi 101, record lỗi sẽ bị bỏ qua.

Error handler cần bảo đảm offset của record chưa xử lý không bị xác nhận như đã hoàn tất. Với chiến lược seek mặc định của `DefaultErrorHandler`, consumer được đưa về vị trí của record lỗi và các record còn lại cần xử lý lại. Sau backoff, consumer poll lại và record được giao lại.

~~~text
Poll:          100 ----> 101 ----> 102
                 |         |
                 |         +---- Listener ném exception
                 |
                 +-------------- Thành công

DefaultErrorHandler
        |
        v
Seek về 101 và giữ phần còn lại cần xử lý
        |
        v
Backoff / retry
        |
        v
Poll lại:      101 ----> 102 ----> ...
~~~

Record 100 đã xử lý thành công có thể được commit theo ack mode và cách container quản lý offset. Record 101 và các record chưa xử lý cần được đọc lại.

## 2. Vai trò của DefaultErrorHandler

`DefaultErrorHandler` là common error handler của Spring Kafka cho record listener và các trường hợp batch được hỗ trợ. Nó kết hợp ba quyết định:

1. Exception có được retry hay không.
2. Nếu retry, chờ bao lâu và thử lại bao nhiêu lần.
3. Khi không retry nữa, recover record bằng cách nào.

Một cấu hình cơ bản:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

Gắn handler vào listener container factory:

~~~java
factory.setCommonErrorHandler(kafkaErrorHandler);
~~~

Trong ví dụ, `FixedBackOff(1_000L, 2L)` chờ một giây giữa các lần retry và cho phép hai lần retry sau lần xử lý ban đầu. Nếu record thất bại liên tục, listener có thể được gọi tổng cộng ba lần trước khi recoverer được gọi.

`DeadLetterPublishingRecoverer` là một ví dụ recoverer. Ứng dụng có thể cấu hình destination resolver, header và cách xử lý lỗi gửi DLT theo yêu cầu. Nếu recoverer hoàn tất thành công, container có thể tiếp tục theo chính sách commit đã cấu hình. Nếu recovery thất bại, không được coi record đã được lưu an toàn.

## 3. Seek behavior mặc định của DefaultErrorHandler

Với record listener, khi listener ném exception, `DefaultErrorHandler` mặc định sử dụng seek để đưa record thất bại và các record chưa được xử lý từ poll về vị trí đọc thích hợp. Sau khi backoff kết thúc, consumer poll lại các record đó.

Hành vi này có một số hệ quả:

- Record lỗi có thể được giao lại nhiều lần.
- Các record sau record lỗi trong cùng partition có thể phải chờ record lỗi được xử lý hoặc recover.
- Các record đã xử lý thành công trước record lỗi được xử lý theo ack mode và offset commit hiện tại.
- Việc seek không có nghĩa committed offset bị lùi trên broker ngay lập tức.
- Nếu consumer bị rebalance hoặc restart, committed offset vẫn quyết định vị trí phục hồi của group.

Với nhiều partition trong cùng một poll, container phải quản lý vị trí đọc và offset theo từng partition. Offset 50 của partition A không có quan hệ thứ tự với offset 50 của partition B. Việc commit hoặc seek ở một partition không xác nhận record ở partition khác.

### 3.1. Record lỗi và các record phía sau

Kafka consumer poll có thể trả về nhiều record từ một hoặc nhiều partition. Khi listener xử lý tuần tự và gặp lỗi ở một record, các record chưa được xử lý trong poll cũng cần được bảo toàn.

Ví dụ:

| Partition | Offset | Kết quả listener |
|---|---:|---|
| `orders-0` | 10 | Thành công |
| `orders-0` | 11 | Exception |
| `orders-0` | 12 | Chưa xử lý |
| `orders-1` | 20 | Chưa xử lý trong poll |

Container phải giữ lại khả năng xử lý các record chưa hoàn tất. Với seek-based error handling, consumer được seek để các record chưa xử lý có thể được poll lại. Chi tiết vị trí seek và commit phụ thuộc loại listener, poll result và trạng thái offset của từng partition.

Không tự suy luận rằng chỉ record gây exception sẽ được đọc lại. Hãy xem log của error handler và record thực tế được giao lại khi kiểm thử.

### 3.2. Record được giao lại không nhất thiết là record đã thất bại ở lần trước

Nếu nhiều record được trả về trong một poll và một record lỗi, một số record khác chưa được listener xử lý cũng có thể được giao lại. Do đó, consumer phải idempotent ngay cả khi listener không ném exception cho record đó ở lần đầu.

Đây là lý do không nên thực hiện side effect trước khi xác định thời điểm xử lý bền vững và commit offset. Một record có thể được giao lại sau lỗi ở record khác hoặc sau restart/rebalance.

## 4. Batch listener và BatchListenerFailedException

Batch listener nhận nhiều record trong một lần gọi. Nếu listener ném exception thông thường mà không cho biết record nào thất bại, container không thể xác định chắc chắn phần batch nào đã xử lý thành công.

Để chỉ ra vị trí record lỗi trong batch, Spring Kafka cung cấp `BatchListenerFailedException`. Listener ném exception này kèm index của record lỗi:

~~~java
@KafkaListener(topics = "orders", groupId = "billing")
public void listen(List<OrderCreated> events) {
    for (int i = 0; i < events.size(); i++) {
        try {
            billingService.processIdempotently(events.get(i));
        }
        catch (Exception ex) {
            throw new BatchListenerFailedException(
                    "Failed to process batch record",
                    ex,
                    i);
        }
    }
}
~~~

Với batch listener, `DefaultErrorHandler` có thể dùng index lỗi để xác định ranh giới:

- Các record trước record lỗi đã được xử lý thành công và có thể được commit theo cơ chế của container.
- Record lỗi được retry hoặc recover theo backoff và recoverer.
- Các record sau record lỗi cần được xử lý lại.

Đây là điểm quan trọng để tránh retry toàn bộ batch khi chỉ một record thất bại. Tuy nhiên, các side effect của record trước index lỗi vẫn cần idempotency vì sự cố có thể xảy ra trước khi offset commit hoàn tất.

### 4.1. Nếu batch listener không xác định record lỗi

Nếu batch listener ném exception thông thường thay vì `BatchListenerFailedException`, container không có index để phân biệt phần thành công và phần thất bại. Spring Kafka có fallback batch error handling để retry batch theo cơ chế riêng; việc retry có thể được thực hiện trong bộ nhớ thay vì seek từng record như trường hợp có index lỗi.

Vì vậy:

- Dùng `BatchListenerFailedException` khi xác định được chính xác index record lỗi.
- Dùng fallback behavior khi lỗi không thể gắn với một record cụ thể.
- Kiểm thử cả hai trường hợp để hiểu batch nào được gọi lại.
- Không giả định mọi batch exception đều dẫn đến cùng một seek pattern.

## 5. Cấu hình seekAfterError

Từ Spring Kafka 2.9, `DefaultErrorHandler` hỗ trợ tùy chọn `seekAfterError`. Giá trị mặc định là `true`, tức handler dùng seek để consumer đọc lại record chưa xử lý trong poll tiếp theo.

Có thể cấu hình trực tiếp:

~~~java
DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);

handler.setSeekAfterError(true);
~~~

Khi đặt `false`, container không thực hiện seek theo cách mặc định. Thay vào đó, các record chưa được xử lý được giữ lại trong bộ nhớ và được gửi lại listener sau khi error handler hoàn tất. Container thực hiện một lần poll ở trạng thái paused để giữ consumer hoạt động trong group.

~~~java
handler.setSeekAfterError(false);
~~~

### 5.1. So sánh hai chế độ

| Chế độ | Cách tiếp tục xử lý | Tác động vận hành |
|---|---|---|
| `seekAfterError=true` | Seek consumer về vị trí cần đọc lại; poll tiếp theo lấy record từ Kafka | Record được đọc lại từ broker; cần quan sát seek, poll và commit |
| `seekAfterError=false` | Giữ các record chưa xử lý trong bộ nhớ và gửi lại sau khi handler hoàn tất | Tránh seek trực tiếp nhưng giữ dữ liệu trong memory; container vẫn cần poll paused để duy trì group |

Chế độ `false` không có nghĩa là bỏ retry hoặc tự commit record. Nó chỉ thay đổi cách container giữ và đưa lại các record chưa xử lý. Error handler vẫn quyết định retry, backoff và recovery.

### 5.2. Khi nào chọn seekAfterError=false?

Có thể cân nhắc khi:

- Muốn tránh thao tác seek/re-fetch record từ broker trong luồng lỗi.
- Cần giữ tập record chưa xử lý của poll để gửi lại theo cơ chế container.
- Đã đánh giá lượng memory cần thiết cho batch và số consumer.
- Đã kiểm thử rebalance, shutdown và retry với phiên bản Spring Kafka đang chạy.

Không nên bật chỉ vì nghĩ rằng nó nhanh hơn. Giữ record trong bộ nhớ làm tăng phụ thuộc vào heap và vòng đời process. Nếu process dừng, các record chưa commit vẫn phải được khôi phục từ committed offset; ứng dụng cần idempotency để chịu được redelivery.

### 5.3. Khi nào giữ seekAfterError=true?

Đây là mặc định và thường phù hợp khi muốn hành vi retry rõ ràng dựa trên offset của Kafka. Record được poll lại từ broker, giúp bộ nhớ container không phải giữ toàn bộ phần record còn lại ngoài cơ chế poll thông thường.

Hãy chọn theo workload, kích thước record, batch size, số partition, thời gian backoff và hành vi rebalance. Không có lựa chọn đúng cho mọi ứng dụng.

## 6. Seek, retry và committed offset

Seek và commit offset là hai thao tác khác nhau, nhưng phải được phối hợp để bảo đảm record không bị bỏ qua.

Ví dụ partition có offset 200, 201, 202:

1. Consumer xử lý 200 thành công.
2. Listener xử lý 201 và ném exception.
3. Error handler seek về vị trí cần retry.
4. Sau backoff, consumer poll lại 201 và các record chưa xử lý.
5. Nếu 201 thành công, container tiếp tục xử lý 202.
6. Offset chỉ được commit theo ack mode và chính sách container.

Nếu consumer restart trước khi offset mới được commit, group có thể đọc lại từ committed offset cũ hơn. Đây là at-least-once behavior và là lý do idempotency cần thiết.

### 6.1. Ack mode ảnh hưởng commit

Ack mode quyết định thời điểm container xem record hoặc batch đã được xác nhận:

| Ack mode | Đặc điểm |
|---|---|
| `RECORD` | Commit theo record sau khi listener xử lý thành công |
| `BATCH` | Commit sau khi các record trong poll batch được xử lý thành công |
| `MANUAL` | Listener gọi acknowledge; container áp dụng commit theo semantics của mode |
| `MANUAL_IMMEDIATE` | Yêu cầu commit ngay khi acknowledge được gọi trên consumer thread; nếu gọi từ thread khác, xử lý được chuyển về consumer thread |

Khi dùng error handler, cần xét thêm cấu hình như `ackAfterHandle` và `commitRecovered` trong các tình huống recovery. `ackAfterHandle` quyết định container có acknowledge/commit sau khi error handler xử lý exception bình thường hay không. `commitRecovered` cho phép commit offset của record đã recover theo điều kiện ack mode được hỗ trợ, thường cần `MANUAL_IMMEDIATE`.

Không bật `commitRecovered` hoặc đổi ack mode mà không kiểm thử thứ tự commit. Hãy xác nhận committed offset thực tế trong consumer group sau cả success, retry và recovery.

### 6.2. Vì sao không nên tự commit offset lớn nhất?

Một custom error handler hoặc callback có thể bị cám dỗ commit offset cao nhất đã nhìn thấy. Cách này nguy hiểm khi còn record thấp hơn chưa xử lý. Commit offset 203 của partition đồng nghĩa group sẽ tiếp tục từ 203, dù record 201 hoặc 202 có thể chưa hoàn tất.

Hãy để `DefaultErrorHandler` phối hợp seek và commit theo container semantics. Nếu tự viết handler, phải theo dõi offset theo từng partition, xác định contiguous completed offset và xử lý rebalance/restart; đây là trách nhiệm phức tạp.

## 7. Backoff trong seek-based retry

Seek đưa consumer trở lại record cần thử lại; backoff quyết định thời điểm lần thử tiếp theo diễn ra.

Ví dụ:

~~~java
ExponentialBackOffWithMaxRetries backOff =
        new ExponentialBackOffWithMaxRetries(4);
backOff.setInitialInterval(1_000L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(10_000L);

DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);
~~~

Khoảng chờ tăng dần, tối đa mười giây, với bốn lần retry sau lần xử lý ban đầu theo semantics của `ExponentialBackOffWithMaxRetries`.

Trong blocking retry, record lỗi có thể giữ partition ở trạng thái chưa tiến lên trong lúc retry. Các record sau trong partition có thể bị trì hoãn để giữ thứ tự. Vì vậy, backoff dài có thể làm tăng record age và consumer lag.

### 7.1. Backoff handler và thời gian poll

Với backoff dài, cần cân nhắc ảnh hưởng đến consumer group và `max.poll.interval.ms`. Spring Kafka có hỗ trợ pausing backoff handler để container pause consumer trong thời gian chờ và tiếp tục poll theo cơ chế phù hợp, thay vì giữ consumer thread ngủ trong một khoảng quá dài.

Ví dụ cấu hình với `ContainerPausingBackOffHandler` ở các phiên bản hỗ trợ:

~~~java
DefaultErrorHandler handler =
        new DefaultErrorHandler(
                recoverer,
                backOff,
                new ContainerPausingBackOffHandler());
~~~

API constructor và cách cấu hình có thể thay đổi theo phiên bản. Hãy kiểm tra dependency và tài liệu tương ứng. Cần phân biệt pause do backoff với pause do `seekAfterError=false` đang chờ record chưa xử lý; cả hai đều ảnh hưởng đến việc consumer nhận record mới.

## 8. Khi retry hết và recoverer được gọi

Sau khi hết số lần retry hoặc exception được phân loại non-retryable, `DefaultErrorHandler` gọi recoverer. Với `DeadLetterPublishingRecoverer`, record có thể được gửi sang DLT.

~~~text
Listener thất bại
       |
       v
DefaultErrorHandler
       |
       +---- Retryable?
       |        |
       |        +---- Có ----> Backoff + seek/replay
       |        |                    |
       |        |                    +---- Thành công --> tiếp tục
       |        |                    |
       |        |                    +---- Lại lỗi ----> thử tiếp
       |        |
       |        +---- Không / hết retry
       |                     |
       v                     v
                 Recoverer / DLT
                         |
                   Publish thành công?
                     /       \
                   Có         Không
                   |            |
                   v            v
              Recovery OK   Báo lỗi recovery
              commit theo   và giữ khả năng
              cấu hình      xử lý lại
~~~

Không xem việc gọi recoverer là bằng chứng record đã được lưu. Nếu DLT publish thất bại, error handler cần nhận được lỗi và không được commit offset nguồn theo cách làm mất record.

### 8.1. Destination của DLT

Theo cách ánh xạ mặc định phổ biến của `DeadLetterPublishingRecoverer`, topic đích thường được tạo bằng cách thêm hậu tố `.DLT` vào topic nguồn và giữ partition tương ứng. Topic DLT cần có partition tương ứng nếu dùng mapping mặc định. Nếu muốn route sang topic hoặc partition khác, cấu hình destination resolver phù hợp.

DLT nên giữ metadata:

- Topic, partition và offset gốc.
- Key và event id.
- Exception class và thông tin lỗi.
- Timestamp, số lần retry và correlation id nếu có.

Không log toàn bộ payload nhạy cảm. Hạn chế quyền truy cập DLT và đặt retention đủ dài cho điều tra, replay.

### 8.2. Replay record đã recover

Sau khi sửa nguyên nhân, record trong DLT có thể được phát lại về topic chính hoặc luồng xử lý riêng. Replay cần giữ event id gốc và được thực hiện theo batch có giới hạn. Consumer phải idempotent vì record có thể đã tạo một phần tác động trước khi lỗi.

Không replay toàn bộ DLT ngay sau khi triển khai bản sửa mà chưa xác định nguyên nhân và thứ tự nghiệp vụ. Hãy thử một số record đại diện, quan sát kết quả và đối soát dữ liệu.

## 9. Seek và batch listener: các trường hợp cần phân biệt

Hành vi xử lý lỗi phụ thuộc loại listener:

| Listener | Cách chỉ ra lỗi | Hành vi xử lý |
|---|---|---|
| Record listener | Exception từ một lần gọi listener | Error handler có thể seek record lỗi và phần chưa xử lý để retry |
| Batch listener với `BatchListenerFailedException` | Index record lỗi trong batch | Commit phần trước lỗi theo chính sách, retry/recover record lỗi và phần sau |
| Batch listener với exception không xác định record | Không có index lỗi | Fallback batch error handling có thể retry toàn bộ batch theo cơ chế riêng |

Không dùng batch listener rồi giả định container luôn có thể xác định record nào đã thành công. Nếu batch có nhiều side effect, cần transaction hoặc idempotency theo từng record để chịu được việc cả batch được gọi lại.

### 9.1. Batch listener và index lỗi

Index trong `BatchListenerFailedException` phải trỏ đến vị trí record trong danh sách batch mà listener đang xử lý, không phải Kafka offset. Offset có thể không liên tiếp nếu batch chứa nhiều partition hoặc poll trả về record từ các partition khác nhau.

~~~java
for (int index = 0; index < records.size(); index++) {
    ConsumerRecord<String, OrderCreated> record = records.get(index);
    try {
        service.process(record.value());
    }
    catch (Exception ex) {
        throw new BatchListenerFailedException(
                "Record failed",
                ex,
                index);
    }
}
~~~

Không truyền Kafka offset vào vị trí index. Dùng nhầm hai giá trị có thể khiến error handler xác định sai ranh giới record cần retry.

## 10. Seek không giống retry topic

Seek-based retry là blocking retry: consumer quay lại vị trí của record chưa xử lý và thử lại trong cùng luồng listener container. Retry topics là non-blocking retry: record được chuyển sang topic khác để chờ lần thử tiếp theo.

| Tiêu chí | Seek-based blocking retry | Retry topics |
|---|---|---|
| Vị trí record | Đọc lại từ topic nguồn | Chuyển qua retry topic |
| Ảnh hưởng record sau | Có thể bị chặn trong partition nguồn | Consumer topic chính có thể tiếp tục |
| Thứ tự | Dễ giữ thứ tự partition hơn | Record retry có thể quay lại sau record mới |
| Backoff dài | Có thể giữ partition/consumer trong retry | Phù hợp hơn với thời gian chờ dài |
| Quản lý hạ tầng | Ít topic hơn | Cần quản lý retry topics và DLT |
| Cơ chế offset | Seek và commit theo container | Publish sang retry topic và xử lý offset nguồn |

Chọn theo yêu cầu thứ tự, SLA, thời gian phục hồi dependency và khả năng vận hành thêm topic. Không trộn nhiều tầng retry mà không tính tổng số attempt và thời gian xử lý.

## 11. Rebalance và restart trong lúc retry

Seek thay đổi position của consumer hiện tại. Nếu consumer bị revoke partition trong lúc retry, quyền sở hữu partition chuyển sang member khác và member mới dựa vào committed offset để tiếp tục.

Các tình huống có thể xảy ra:

- Consumer bị dừng trước khi record được commit: record có thể được giao lại.
- Listener đã hoàn tất database transaction nhưng chưa commit offset: record có thể được giao lại; cần idempotency.
- Partition bị revoke trong lúc backoff: container cần kết thúc hoặc xử lý retry theo lifecycle và assignment hiện tại.
- Consumer mới nhận partition: nó đọc từ committed offset của group, không kế thừa position trong memory của consumer cũ.

Vì vậy, không được dựa vào state trong memory của một consumer để coi record đã hoàn tất. Trạng thái nghiệp vụ cần được lưu bền vững và có thể khôi phục khi record được giao lại cho instance khác.

### 11.1. Poll interval và rebalance

Retry/backoff dài có thể ảnh hưởng đến khoảng cách giữa các lần poll. Nếu consumer vượt `max.poll.interval.ms`, group có thể xem member không còn tiến triển và kích hoạt rebalance.

Khi có retry kéo dài:

- Đo thời gian xử lý và backoff tổng cộng.
- Chọn backoff handler phù hợp nếu thời gian chờ dài.
- Đặt `max.poll.interval.ms` theo workload nhưng không dùng timeout lớn để che listener bị treo.
- Theo dõi rebalance count, lag và thời gian phục hồi.
- Kiểm thử shutdown/rebalance trong khi record đang retry.

## 12. Idempotency khi record được seek và giao lại

Seek-based retry có thể khiến cùng một record được listener xử lý nhiều lần. Ngoài ra, record đã hoàn tất một phần có thể được giao lại sau crash hoặc rebalance.

Với database, một mẫu phổ biến là inbox table:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Trong cùng một database transaction:

1. Ghi event id vào bảng `processed_events`.
2. Nếu event id đã tồn tại, bỏ qua side effect đã hoàn tất trước đó.
3. Nếu event id mới, cập nhật nghiệp vụ.
4. Commit transaction.
5. Để listener hoàn tất và container xử lý offset.

Với HTTP API hoặc hệ thống ngoài, dùng idempotency key nếu được hỗ trợ. Nếu timeout khiến kết quả không rõ, cần truy vấn trạng thái hoặc đối soát trước khi thực hiện lại thao tác không thể lặp.

Không tạo event id mới khi retry. Giữ nguyên định danh xuyên suốt retry, DLT và replay.

## 13. Observability cho seek và retry

Khi một record được giao lại, log phải giúp xác định nó đang ở lần thử nào và vì sao position bị đưa về trước.

Các thông tin hữu ích:

- Consumer group và listener id.
- Topic, partition và offset.
- Exception class và cause gốc.
- Số lần retry/attempt nếu có.
- Backoff duration và thời điểm lần thử tiếp theo.
- Seek position hoặc trạng thái retry nếu log framework cung cấp.
- Kết quả recoverer/DLT.
- Event id và correlation id để tra cứu log nghiệp vụ.

Metrics cần theo dõi:

| Metric | Ý nghĩa |
|---|---|
| Listener exception rate | Tần suất listener thất bại |
| Retry rate/count | Số lần xử lý lại record |
| Retry duration | Thời gian record nằm trong retry/backoff |
| Recoverer/DLT rate | Số record được chuyển sang recovery |
| DLT publish failure | Số lần gửi DLT thất bại |
| Consumer lag | Backlog của group theo partition |
| Oldest record age | Tuổi record cũ nhất chưa hoàn tất |
| Rebalance count/duration | Tác động của retry kéo dài đến membership |
| Listener processing duration | Thời gian xử lý mỗi lần gọi |

Không dùng event id, message key hoặc offset làm metric tag có cardinality cao. Đưa định danh chi tiết vào log có cấu trúc để điều tra một record cụ thể.

## 14. Runbook khi record bị retry lặp lại

### 14.1. Một record liên tục xuất hiện lại

1. Ghi nhận topic, partition, offset và event id.
2. Xác định exception class và cause gốc.
3. Kiểm tra exception có được phân loại retryable hay không.
4. Xem backoff, số lần retry và thời điểm recoverer được gọi.
5. Kiểm tra listener có thực hiện side effect trước khi ném exception không.
6. Kiểm tra committed offset của group và trạng thái DLT.
7. Sửa nguyên nhân hoặc chuyển record sang recovery theo chính sách.
8. Xác nhận record không tiếp tục quay lại ngoài dự kiến.

### 14.2. Record sau record lỗi không được xử lý

1. Kiểm tra blocking retry và backoff của record lỗi.
2. Xác định consumer đang pause hay seek/re-poll.
3. Kiểm tra exception có còn trong retry window không.
4. Xác nhận recoverer có hoàn tất không.
5. Kiểm tra consumer lag và record age theo partition.
6. Nếu nghiệp vụ cho phép bỏ qua record lỗi, xác nhận DLT đã lưu bền vững trước khi offset nguồn tiến lên.

### 14.3. Batch bị xử lý lại toàn bộ

1. Kiểm tra listener có ném `BatchListenerFailedException` không.
2. Xác nhận index truyền vào là index trong batch.
3. Nếu chỉ ném exception chung, xác định fallback batch handler đang được dùng.
4. Kiểm tra side effect của các record trước lỗi có idempotent không.
5. Điều chỉnh listener để xác định record lỗi nếu có thể.

### 14.4. Offset có vẻ đã tiến qua record chưa xử lý

1. Kiểm tra ack mode và auto commit.
2. Kiểm tra `ackAfterHandle` và `commitRecovered` nếu có cấu hình.
3. Xác định listener có ack trước khi nghiệp vụ bền vững không.
4. Kiểm tra custom error handler hoặc code gọi `commitSync`/`commitAsync`.
5. Đối chiếu committed offset theo từng partition.
6. Xác nhận record chưa xử lý còn trong log hoặc có bản sao trong DLT/outbox.

## 15. Kiểm thử seek behavior

Integration test nên xác nhận cả vị trí đọc, committed offset và tác động nghiệp vụ. Chỉ kiểm tra listener được gọi lại là chưa đủ.

Các kịch bản:

1. Record listener thất bại một lần rồi thành công; xác nhận record được giao lại.
2. Record listener thất bại hết retry; xác nhận recoverer nhận đúng record.
3. Recoverer/DLT publish thất bại; xác nhận nguồn không bị commit mất record.
4. Nhiều record trong một poll; record giữa batch thất bại; xác nhận các record chưa xử lý được đọc lại.
5. Batch listener ném `BatchListenerFailedException` với index cụ thể; xác nhận phần trước lỗi và phần sau lỗi được xử lý theo chính sách.
6. Batch listener ném exception chung; xác nhận fallback batch behavior.
7. Chạy với `seekAfterError=true` và `false`; quan sát pause, re-poll và record delivery.
8. Restart consumer trong lúc retry; xác nhận committed offset quyết định vị trí phục hồi.
9. Gây rebalance trong lúc retry; xác nhận record không mất khi partition đổi owner.
10. Kiểm tra idempotency khi database commit thành công nhưng offset chưa commit.

Kafka Testcontainers hoặc embedded broker phù hợp với phiên bản có thể dùng cho integration test. Dùng dữ liệu và số partition gần với cấu hình thực tế để kiểm tra behavior của poll batch.

## 16. Những lỗi thiết kế thường gặp

**Nhầm seek với commit:** Seek chỉ thay đổi position của consumer hiện tại; nó không tự cập nhật committed offset của group.

**Cho rằng chỉ record lỗi được đọc lại:** Các record chưa xử lý trong poll cũng có thể được đưa lại.

**Commit offset cao nhất:** Có thể bỏ qua offset thấp hơn chưa hoàn tất trong cùng partition.

**Không idempotent:** Record được giao lại có thể lặp side effect.

**Dùng exception chung cho batch:** Container không biết index record lỗi và có thể phải retry toàn batch.

**Dùng nhầm offset làm batch index:** `BatchListenerFailedException` cần index trong danh sách batch, không phải Kafka offset.

**Đặt backoff quá dài mà không theo dõi poll:** Consumer có thể vượt `max.poll.interval.ms` hoặc làm lag tăng.

**Ack khi publish DLT chưa thành công:** Có thể mất record nguồn nếu recovery không bền vững.

**Cho rằng seekAfterError=false loại bỏ retry:** Chế độ này giữ record trong memory và gửi lại, vẫn cần error handling và acknowledgement đúng.

**Dùng seek-based retry cho lỗi cần chờ lâu:** Partition có thể bị chặn; cân nhắc retry topics nếu yêu cầu thứ tự cho phép.

## 17. Checklist cấu hình và vận hành

### Error handler

- [ ] Listener container dùng `DefaultErrorHandler` hoặc handler phù hợp.
- [ ] Exception được phân loại retryable/non-retryable rõ ràng.
- [ ] Backoff có giới hạn và phù hợp SLA.
- [ ] Recoverer/DLT được cấu hình cho record hết retry.
- [ ] Lỗi publish DLT không làm record nguồn bị xác nhận sai.

### Seek và offset

- [ ] Đã hiểu consumer position khác committed offset.
- [ ] Seek behavior của record listener đã được kiểm thử.
- [ ] Batch listener dùng `BatchListenerFailedException` khi xác định được index lỗi.
- [ ] Fallback behavior cho batch exception chung đã được hiểu.
- [ ] Ack mode, `ackAfterHandle` và `commitRecovered` phù hợp.
- [ ] `seekAfterError` được đặt có chủ đích nếu thay đổi mặc định.

### Độ tin cậy

- [ ] Consumer idempotent khi record được giao lại.
- [ ] Side effect chỉ được xác nhận sau khi bền vững.
- [ ] Backoff không gây retry storm hoặc vượt SLA.
- [ ] Retry dài không làm consumer rời group ngoài dự kiến.
- [ ] Có metrics cho retry, lag, record age và DLT.
- [ ] Runbook có hướng xử lý record bị seek/retry lặp.

### Kiểm thử

- [ ] Đã kiểm thử record retry thành công và hết retry.
- [ ] Đã kiểm thử recoverer/DLT failure.
- [ ] Đã kiểm thử batch failure có index và không có index.
- [ ] Đã kiểm thử `seekAfterError` true/false nếu dùng cả hai.
- [ ] Đã kiểm thử restart/rebalance trong lúc retry.
- [ ] Đã kiểm thử duplicate delivery và idempotency.

## Kết luận

Seek sau lỗi cho phép `DefaultErrorHandler` đưa consumer về vị trí của record chưa xử lý để listener có thể thử lại mà không xác nhận nhầm offset. Với record listener, handler mặc định seek record lỗi và phần còn lại cần xử lý; với batch listener, `BatchListenerFailedException` giúp xác định index lỗi để xử lý phần trước và sau theo chính sách. `seekAfterError=true` dùng seek/re-poll, còn `false` giữ record chưa xử lý trong memory và gửi lại sau khi handler hoàn tất. Dù chọn cách nào, hãy phối hợp backoff, acknowledgement, recovery và idempotency, đồng thời kiểm tra committed offset thực tế để bảo đảm record không bị bỏ qua.
