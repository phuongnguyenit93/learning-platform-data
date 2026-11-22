# Backoff tăng dần

Khi một Kafka listener gặp lỗi tạm thời, retry ngay lập tức nhiều lần thường làm tình trạng xấu hơn. Nếu database, HTTP service hoặc broker đang quá tải, các lần gọi lặp liên tiếp tiếp tục tạo áp lực đúng vào dependency đang gặp sự cố. **Backoff tăng dần** giải quyết vấn đề bằng cách tăng thời gian chờ giữa các lần thử lại.

Trong Spring Kafka, backoff có thể được dùng với cơ chế retry blocking của listener container, thường thông qua `DefaultErrorHandler`, hoặc với retry topic không blocking qua `@RetryableTopic`. Hai mô hình có cách vận hành khác nhau: blocking retry giữ record trong luồng xử lý hiện tại trong khi retry topic chuyển record sang topic có độ trễ để consumer tiếp tục công việc khác.

## 1. Vì sao cần backoff?

Giả sử listener nhận một sự kiện đơn hàng và gọi dịch vụ kiểm tra tồn kho. Dịch vụ này có thể tạm thời trả về timeout vì đang triển khai hoặc chịu tải cao. Nếu listener retry ngay, nhiều consumer có thể cùng gửi lại request liên tục, làm dịch vụ càng khó phục hồi.

Backoff tạo khoảng nghỉ giữa các lần thử:

```text
Lần thử 1: thất bại
     |
     +---- chờ 1 giây ----> Lần thử 2: thất bại
                               |
                               +---- chờ 2 giây ----> Lần thử 3: thất bại
                                                        |
                                                        +---- chờ 4 giây ----> Lần thử 4
```

Khoảng chờ tăng dần giúp:

- Giảm tốc độ request lặp khi dependency đang lỗi.
- Cho hệ thống phụ thuộc thời gian phục hồi.
- Tránh tiêu thụ CPU và network cho các lần retry quá dày.
- Giới hạn số lần thử và thời gian xử lý một record.
- Phân biệt lỗi tạm thời với lỗi dữ liệu hoặc nghiệp vụ không thể tự khắc phục.

Backoff không làm cho một thao tác lỗi trở nên thành công. Nó chỉ điều tiết thời điểm thử lại. Nếu nguyên nhân là dữ liệu không hợp lệ hoặc quy tắc nghiệp vụ bị vi phạm, chờ lâu hơn cũng không giải quyết được vấn đề.

## 2. Backoff cố định và backoff tăng dần

Với **fixed backoff**, mỗi lần retry đều chờ cùng một khoảng thời gian. Ví dụ, chờ 2 giây giữa mọi lần thử:

```text
Retry 1: 2 giây
Retry 2: 2 giây
Retry 3: 2 giây
Retry 4: 2 giây
```

Với **exponential backoff**, khoảng chờ tăng theo cấp số nhân. Một công thức đơn giản là:

\[
  d_n = \min(d_0 \times m^{n-1}, d_{max})
\]

Trong đó:

- \(d_n\) là thời gian chờ trước lần retry thứ \(n\).
- \(d_0\) là khoảng chờ ban đầu (`initialInterval`).
- \(m\) là hệ số nhân (`multiplier`), thường lớn hơn 1.
- \(d_{max}\) là giới hạn tối đa (`maxInterval`).

Ví dụ `initialInterval = 1 giây`, `multiplier = 2` và `maxInterval = 10 giây`:

| Lần retry | Khoảng chờ |
|---:|---:|
| 1 | 1 giây |
| 2 | 2 giây |
| 3 | 4 giây |
| 4 | 8 giây |
| 5 | 10 giây |
| 6 | 10 giây |

Khi đạt `maxInterval`, các lần retry tiếp theo không tăng thêm. Giới hạn này giúp thời gian chờ không tăng vô hạn.

## 3. Chọn initial interval, multiplier và max interval

Ba tham số chính quyết định hình dạng lịch retry:

| Tham số | Ý nghĩa | Tác động khi tăng |
|---|---|---|
| `initialInterval` | Thời gian chờ ban đầu | Giảm tốc độ retry ngay từ đầu. |
| `multiplier` | Hệ số tăng giữa các lần chờ | Khoảng chờ tăng nhanh hơn. |
| `maxInterval` | Khoảng chờ tối đa | Giới hạn thời gian nghỉ của mỗi lần retry. |

Chọn tham số theo đặc tính dependency và yêu cầu thời gian hoàn tất:

- Dependency thường phục hồi nhanh có thể dùng initial interval ngắn.
- Dịch vụ có thời gian phục hồi dài hơn có thể cần multiplier lớn hơn.
- `maxInterval` ngăn retry bị trì hoãn quá lâu.
- Số lần retry cần hữu hạn để một record không giữ tài nguyên vô thời hạn.
- Tổng thời gian chờ phải phù hợp với SLA, thời gian giữ partition và thời gian xử lý cho phép.

Không có một bộ tham số phù hợp cho mọi topic. Luồng xử lý thanh toán, cập nhật trạng thái và đồng bộ dữ liệu có thể có yêu cầu khác nhau về độ trễ, thứ tự và khả năng thử lại.

## 4. Cấu hình exponential backoff với DefaultErrorHandler

Trong Spring Kafka, `DefaultErrorHandler` xử lý exception từ listener và dùng một `BackOff` để quyết định thời điểm thử lại. Có thể dùng `ExponentialBackOffWithMaxRetries` để đặt số lần retry tối đa cùng lịch exponential.

Ví dụ cấu hình:

```java
@Configuration
public class KafkaErrorConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);

        var backOff = new ExponentialBackOffWithMaxRetries(5);
        backOff.setInitialInterval(1_000L);
        backOff.setMultiplier(2.0);
        backOff.setMaxInterval(10_000L);

        var handler = new DefaultErrorHandler(recoverer, backOff);
        handler.addNotRetryableExceptions(InvalidOrderException.class);
        return handler;
    }
}
```

Các import chính trong ví dụ thuộc Spring Kafka:

```java
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.support.ExponentialBackOffWithMaxRetries;
```

`ExponentialBackOffWithMaxRetries(5)` đặt tối đa năm lần retry sau lần xử lý ban đầu. Với các tham số trên, lịch chờ là 1, 2, 4, 8 và 10 giây. Tổng số lần listener có thể được gọi cho một record là một lần ban đầu cộng tối đa năm lần retry, nếu các lần thử đều thất bại và record chưa được phục hồi sớm.

`DeadLetterPublishingRecoverer` minh họa bước phục hồi sau khi hết retry: record được chuyển tới dead-letter topic (DLT) theo destination resolver mặc định hoặc resolver do ứng dụng cấu hình. Ứng dụng cần cấu hình serializer, topic đích và quyền ghi DLT phù hợp. Nếu không muốn publish DLT, có thể dùng recoverer khác, nhưng phải xác định rõ record sau khi hết retry sẽ được xử lý như thế nào.

### 4.1 Cấu hình ErrorHandler cho listener container

Nếu ứng dụng tự tạo listener container factory, gắn error handler vào factory:

```java
factory.setCommonErrorHandler(kafkaErrorHandler);
```

Trong Spring Boot, một bean `CommonErrorHandler` có thể được auto-configured cho listener container do Boot tạo, tùy phiên bản và cách ứng dụng tùy chỉnh factory. Nếu có factory tự định nghĩa, hãy kiểm tra factory đó đã dùng error handler mong muốn chưa.

Không khai báo một `DefaultErrorHandler` rồi mặc định cho rằng mọi listener đều dùng nó. Hãy xác định listener container thực tế và cấu hình error handler tại đúng nơi.

## 5. Backoff và số lần thử

Khi đọc cấu hình retry, cần phân biệt **lần giao ban đầu** với **số lần retry**. Trong `ExponentialBackOffWithMaxRetries`, đối số constructor là số lần retry tối đa. Ví dụ:

```java
var backOff = new ExponentialBackOffWithMaxRetries(3);
```

Nếu record thất bại liên tục, listener có thể được gọi tối đa bốn lần: một lần đầu và ba lần retry. Sau lần retry cuối cùng vẫn thất bại, error handler gọi recoverer.

Với các implementation `BackOff` khác, ý nghĩa tham số có thể khác. Ví dụ `FixedBackOff(interval, maxAttempts)` trong Spring Framework dùng số lần thử lại theo hợp đồng của `BackOffExecution`; hãy đọc đúng API đang dùng và kiểm tra số lần gọi thực tế trong integration test.

Một `BackOff` trả về khoảng chờ cho từng lần retry. Khi hết số lần thử, `nextBackOff()` trả về `BackOffExecution.STOP`; error handler chuyển sang recovery. Điều này tạo ranh giới rõ ràng giữa retry và xử lý record đã hết retry.

## 6. Retry chỉ cho lỗi có khả năng phục hồi

Không phải exception nào cũng nên retry. Hãy phân loại lỗi trước khi thiết kế backoff:

| Loại lỗi | Ví dụ | Chính sách thường phù hợp |
|---|---|---|
| Tạm thời | HTTP 503, timeout ngắn, database failover | Retry có giới hạn với backoff. |
| Lỗi kết nối có thể phục hồi | Broker hoặc service phụ thuộc tạm thời mất kết nối | Retry và theo dõi tình trạng dependency. |
| Dữ liệu không hợp lệ | Thiếu `orderId`, payload sai schema | Không retry nhiều lần; chuyển DLT/cách ly. |
| Vi phạm nghiệp vụ | Đơn hàng ở trạng thái không được phép cập nhật | Xử lý theo chính sách nghiệp vụ, thường không retry tự động. |
| Lỗi lập trình | Null pointer, mapping sai | Cần sửa code; retry lặp thường không giúp ích. |

`DefaultErrorHandler` có các exception được phân loại không retry theo mặc định, và cho phép bổ sung loại lỗi bằng `addNotRetryableExceptions()`. Có thể dùng `addRetryableExceptions()` để điều chỉnh phân loại theo nghiệp vụ. Hãy kiểm tra cấu hình phân loại của phiên bản Spring Kafka đang dùng, vì danh sách mặc định và cách xử lý có thể thay đổi theo phiên bản.

Nếu listener bắt exception rồi không ném lại, error handler không nhìn thấy lỗi đó và có thể xem listener đã xử lý thành công. Khi muốn retry, hãy để exception phù hợp truyền ra khỏi listener hoặc chuyển lỗi theo cơ chế được thiết kế rõ ràng.

## 7. Dead Letter Topic sau khi hết retry

Sau khi backoff hết số lần retry, record cần có một kết quả cuối cùng. DLT thường được dùng để giữ record lỗi cùng metadata hỗ trợ điều tra:

- Topic, partition và offset nguồn.
- Key, timestamp và headers của record.
- Exception hoặc thông tin nguyên nhân thất bại.
- Số lần retry hoặc thông tin delivery attempt nếu được cấu hình.
- Correlation ID hoặc event ID để truy vết nghiệp vụ.

DLT không tự sửa dữ liệu lỗi. Nó là nơi cách ly record để điều tra, sửa nguyên nhân và replay có kiểm soát. Trước khi phát lại, cần xác định lỗi đã được khắc phục, schema tương thích và nghiệp vụ có idempotent hay không.

Nếu publish DLT thất bại, không được âm thầm xem record gốc đã được xử lý thành công. Cần cấu hình recoverer và error handler để lỗi recovery tiếp tục được quan sát và xử lý theo chính sách. Một record không thể ghi vào DLT có thể cần được retry recovery hoặc giữ lại để tránh mất dữ liệu.

## 8. Blocking retry và tác động tới partition

Với retry blocking qua `DefaultErrorHandler`, record lỗi được retry trong luồng tiêu thụ hiện tại. Trong thời gian backoff và retry, partition có thể không tiếp tục xử lý các record phía sau theo thứ tự thông thường.

Điều này giữ semantics thứ tự tương đối rõ: record lỗi được xử lý lại trước khi consumer tiến tiếp. Nhưng một record lỗi kéo dài có thể làm tăng lag cho partition đó. Nếu backoff dài, consumer thread có thể dành nhiều thời gian chờ thay vì xử lý record mới.

Hãy cân nhắc:

- Tổng thời gian retry của một record.
- Số partition mà consumer member đang giữ.
- `max.poll.interval.ms` và thời gian xử lý giữa các lần poll.
- Khả năng dùng cơ chế pause container trong thời gian backoff dài.
- Tác động của việc một record chặn các record phía sau cùng partition.

Spring Kafka có `ContainerPausingBackOffHandler` cho những trường hợp cần pause container trong thời gian backoff dài. Thời gian pause thực tế chịu ảnh hưởng của `pollTimeout`; hãy cấu hình và kiểm thử theo phiên bản đang dùng. Không chỉ tăng `max.poll.interval.ms` mà bỏ qua tác động tới group membership và thời gian phục hồi.

## 9. Non-blocking retry bằng retry topic

Nếu không muốn một record lỗi chặn partition trong thời gian chờ dài, có thể dùng retry topic. Record được chuyển sang topic retry với thời gian xử lý phù hợp; consumer của topic chính tiếp tục xử lý các record khác. Khi retry topic đến thời điểm được xử lý, record được chuyển lại luồng listener; nếu tiếp tục thất bại, nó có thể đi qua các retry topic tiếp theo và cuối cùng vào DLT.

Ví dụ với `@RetryableTopic`:

```java
@RetryableTopic(
        attempts = "6",
        backoff = @Backoff(
                delay = 1_000,
                multiplier = 2.0,
                maxDelay = 10_000),
        dltTopicSuffix = ".dlt")
@KafkaListener(topics = "orders")
public void onOrder(Order order) {
    orderService.process(order);
}
```

Trong ví dụ này, `attempts = "6"` là tổng số lần thử, bao gồm lần giao ban đầu. `@Backoff` mô tả lịch delay tăng dần và giới hạn delay tối đa. Spring Kafka tạo các retry topic và định tuyến record theo cấu hình retry topic của annotation.

Non-blocking retry có ưu điểm là record lỗi không giữ consumer chính chờ toàn bộ khoảng backoff. Tuy nhiên, thứ tự xử lý có thể thay đổi: record phía sau cùng partition có thể được xử lý trước khi record lỗi được retry. Hãy chỉ dùng khi nghiệp vụ chấp nhận sự thay đổi thứ tự đó hoặc có versioning/idempotency để bảo vệ trạng thái.

Non-blocking retry topic có các giới hạn riêng theo phiên bản Spring Kafka, bao gồm giới hạn với batch listener và container transaction. Không kết hợp với container transaction nếu phiên bản đang dùng không hỗ trợ; kiểm tra tài liệu và kiểm thử semantics trước khi triển khai.

## 10. Jitter để tránh retry đồng loạt

Exponential backoff làm tăng khoảng chờ, nhưng nhiều consumer có thể cùng thất bại tại một thời điểm và cùng retry theo một lịch giống nhau. Khi đó các request có thể dồn lại thành từng đợt, tạo ra hiện tượng thundering herd.

**Jitter** thêm một thành phần ngẫu nhiên vào thời gian chờ để phân tán thời điểm retry. Ví dụ, thay vì mọi consumer cùng retry sau đúng 8 giây, mỗi consumer có thể retry trong một khoảng quanh mốc đó theo chính sách được chọn.

Jitter hữu ích khi:

- Nhiều partition hoặc nhiều service instance gọi cùng một dependency.
- Sự cố bắt đầu cùng thời điểm, khiến nhiều request thất bại đồng loạt.
- Dependency có giới hạn throughput và cần tránh đợt request tăng vọt.

Không nên giả định mọi `BackOff` của Spring Kafka tự thêm jitter. Hãy kiểm tra implementation cụ thể; nếu cần, dùng một implementation hỗ trợ randomization hoặc custom `BackOff` phù hợp. Khi thêm jitter, vẫn phải giữ giới hạn thời gian chờ tối đa và số lần retry để bảo đảm SLA.

## 11. Tính tổng thời gian retry

Thời gian xử lý một record bao gồm thời gian chạy listener ở từng lần thử cộng với các khoảng backoff giữa các lần thử. Với lịch 1, 2, 4, 8 và 10 giây, tổng thời gian chờ giữa các lần thử là 25 giây, chưa tính thời gian gọi nghiệp vụ và thời gian phục hồi.

Nếu mỗi lần xử lý mất trung bình 500 ms và có một lần ban đầu cộng năm lần retry, thời gian chạy nghiệp vụ có thể xấp xỉ 3 giây. Tổng thời gian xử lý lý thuyết khi đó khoảng 28 giây, chưa tính overhead của consumer, commit, recovery và scheduling.

Hãy tính tổng thời gian theo công thức:

\[
  T_{total} = \sum_{i=1}^{N} T_{process,i} + \sum_{j=1}^{N-1} d_j + T_{recovery}
\]

Trong đó \(N\) là tổng số lần gọi listener, \(T_{process,i}\) là thời gian xử lý ở lần thử thứ \(i\), \(d_j\) là khoảng backoff giữa hai lần thử, và \(T_{recovery}\) là thời gian đưa record vào DLT hoặc thực hiện recovery.

Tổng thời gian này cần phù hợp với yêu cầu nghiệp vụ. Nếu một sự kiện phải hoàn tất trong 10 giây, cấu hình backoff có tổng delay 25 giây không đáp ứng yêu cầu dù mỗi lần retry riêng lẻ đều hợp lệ.

## 12. Quan sát retry và backoff trong production

Theo dõi retry như một phần của sức khỏe hệ thống, không chỉ đếm exception:

- Số record retry theo topic, partition và loại exception.
- Số lần thử trung bình và phân bố số lần thử trước khi thành công.
- Số record hết retry và được chuyển vào DLT.
- Thời gian từ lần giao đầu tiên đến khi thành công hoặc recovery.
- Consumer lag theo partition trong thời gian retry tăng.
- Tỷ lệ lỗi và độ trễ của dependency được gọi từ listener.
- Lỗi publish DLT hoặc retry topic.

Log nên có topic, partition, offset, event ID, exception class và delivery attempt nếu có. Tránh đưa key có cardinality rất cao thành metric label; dùng log/trace hoặc metric đã được tổng hợp để tránh làm hệ thống monitoring quá tải.

Một đợt retry tăng đột ngột có thể là tín hiệu dependency đang lỗi, thay đổi schema hoặc một bản release tạo lỗi mapping. Hãy liên kết thời điểm retry với deployment, thay đổi cấu hình và metric của dependency để tìm nguyên nhân gốc.

## 13. Kiểm thử exponential backoff

Kiểm thử cần xác nhận cả số lần thử, khoảng chờ và hành vi sau khi hết retry. Có thể kiểm thử `BackOff` riêng bằng cách gọi `start()` và `nextBackOff()` để xác nhận lịch thời gian, sau đó dùng integration test với Kafka broker để kiểm tra error handler và recovery.

Các kịch bản nên có:

1. Listener thất bại ở hai lần đầu rồi thành công; xác nhận số lần gọi và khoảng retry theo cấu hình.
2. Listener thất bại liên tục; xác nhận số lần retry dừng đúng giới hạn.
3. Một exception được phân loại non-retryable; xác nhận không chờ các khoảng backoff đã cấu hình.
4. Sau khi hết retry, xác nhận record được chuyển vào đúng DLT và metadata nguồn được giữ lại.
5. Làm DLT publish thất bại; xác nhận recovery failure được quan sát và không âm thầm mất record.
6. Với retry topic, xác nhận record đi qua các topic theo delay và cuối cùng tới DLT.
7. Gửi nhiều record lỗi đồng thời; quan sát tải dependency và hiệu quả của jitter nếu implementation có hỗ trợ.
8. Kiểm tra thứ tự record khi dùng blocking retry và non-blocking retry.

Không dùng `Thread.sleep()` dài trong unit test chỉ để chờ backoff. Kiểm tra lịch `BackOff` trực tiếp hoặc dùng clock/test harness phù hợp. Với integration test, dùng timeout hữu hạn và điều kiện rõ ràng như số lần gọi listener hoặc record xuất hiện trong DLT.

## 14. Những lỗi cấu hình thường gặp

- **Retry không giới hạn:** record có thể giữ partition và tài nguyên vô thời hạn.
- **Multiplier quá lớn:** khoảng chờ nhanh chóng chạm max interval và làm record chờ quá lâu.
- **Không đặt max interval:** thời gian chờ có thể tăng vượt ngân sách nghiệp vụ nếu implementation cho phép.
- **Retry lỗi dữ liệu vĩnh viễn:** tạo tải mà không thể sửa nguyên nhân.
- **Không tính tổng thời gian retry:** record có thể vượt SLA dù từng khoảng chờ riêng lẻ có vẻ hợp lý.
- **Nhầm `attempts` của retry topic với số lần retry:** với `@RetryableTopic`, attempts bao gồm lần thử ban đầu.
- **Cho rằng blocking retry không ảnh hưởng record phía sau:** retry có thể giữ luồng xử lý partition.
- **Dùng retry topic nhưng vẫn giả định thứ tự ban đầu:** record phía sau có thể được xử lý trước record đang chờ retry.
- **Không theo dõi lỗi DLT publish:** record hết retry có thể không được phục hồi như dự kiến.
- **Giả định exponential backoff luôn có jitter:** các instance có thể retry đồng loạt nếu cùng lịch cố định.

## 15. Cách chọn chiến lược cho từng luồng

| Nhu cầu | Chiến lược nên cân nhắc |
|---|---|
| Lỗi tạm thời, số lần retry ít, cần giữ thứ tự partition | `DefaultErrorHandler` với exponential backoff blocking. |
| Dependency phục hồi trong vài giây và cần retry nhanh lúc đầu | Initial interval ngắn, multiplier vừa phải và max interval phù hợp. |
| Nhiều consumer cùng retry vào một dependency | Thêm jitter bằng implementation phù hợp và giới hạn tổng tải retry. |
| Retry có thể kéo dài, không muốn giữ partition chờ | Retry topic với `@RetryableTopic`, nếu thứ tự và giới hạn mô hình phù hợp. |
| Dữ liệu không hợp lệ hoặc lỗi không thể tự phục hồi | Phân loại non-retryable và chuyển DLT/cách ly. |
| Cần bảo đảm output và offset Kafka nguyên tử | Dùng container transaction và error handling tương thích; đánh giá riêng retry topic. |

Backoff tăng dần cần được thiết kế cùng số lần retry, loại exception, cơ chế recovery, thời gian xử lý và yêu cầu thứ tự. Hãy chọn khoảng chờ để dependency có cơ hội phục hồi, đặt giới hạn để record không chờ vô hạn và theo dõi retry như một tín hiệu vận hành. Khi retry hết giới hạn, record phải có đường đi rõ ràng để điều tra hoặc xử lý lại an toàn.
