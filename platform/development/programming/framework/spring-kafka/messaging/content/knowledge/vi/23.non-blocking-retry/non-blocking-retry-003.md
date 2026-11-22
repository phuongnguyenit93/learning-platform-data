# Backoff giữa các retry topic

Non-blocking retry cho phép ứng dụng chuyển một record gặp lỗi sang retry topic để xử lý lại sau một khoảng chờ. Consumer của topic chính có thể tiếp tục nhận các record khác trong khi record lỗi đi qua luồng retry riêng. Khoảng chờ giữa các lần thử được gọi là backoff. Chọn backoff hợp lý giúp dịch vụ phụ thuộc có thời gian phục hồi, giảm áp lực khi đang quá tải và tránh retry dồn dập.

Trong Spring Kafka, có thể khai báo lịch backoff cho retry topic bằng `@RetryableTopic` và `@Backoff`. Lịch này có thể cố định hoặc tăng dần theo cấp số nhân. Cần hiểu số lần thử, khoảng chờ và cách tạo retry topic để dự đoán thời điểm xử lý lại cũng như tác động đến thứ tự sự kiện.

## 1. Backoff hoạt động trong non-blocking retry

Với non-blocking retry, khi listener ném exception thuộc nhóm được retry, Spring Kafka chuyển record sang retry topic tương ứng. Retry listener nhận record từ topic đó và chỉ xử lý khi khoảng backoff của lần thử đã đến hạn. Nếu listener tiếp tục thất bại, record được chuyển sang bước retry tiếp theo. Khi hết số lần thử, record đi tới dead-letter topic (DLT) nếu luồng được cấu hình DLT.

Luồng tổng quát:

```text
orders
   |
   | listener thất bại
   v
orders-retry (lần 1, chờ theo backoff)
   |
   | retry listener vẫn thất bại
   v
orders-retry (lần tiếp theo)
   |
   | hết attempts
   v
orders-dlt
```

Tên topic thực tế phụ thuộc topic suffix, chiến lược đặt suffix và cấu hình của ứng dụng. Spring Kafka tạo hoặc sử dụng các retry topic theo lịch backoff đã khai báo. Một retry topic có thể đại diện cho một khoảng chờ hoặc được tái sử dụng tùy cấu hình; không nên suy luận tên topic chỉ từ số lần thử.

Backoff là thời gian chờ trước một lần thử lại, không phải thời gian xử lý listener. Tổng thời gian thực tế còn phụ thuộc thời gian xử lý mỗi lần, thời gian publish/consume, tải broker và lịch điều phối của retry listener.

## 2. Backoff cố định

Backoff cố định dùng cùng một khoảng chờ giữa các lần retry. Ví dụ, nếu đặt `delay = 2_000`, mỗi lần chuyển sang retry tiếp theo sẽ có khoảng chờ mục tiêu hai giây.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    private final OrderService orderService;

    OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(delay = 2_000L),
            dltTopicSuffix = "-dlt")
    @KafkaListener(topics = "${app.kafka.orders-topic}")
    public void onOrder(OrderCreated event) {
        orderService.handle(event);
    }
}
```

`attempts = "4"` là tổng số lần xử lý, bao gồm lần đầu trên topic chính. Vì vậy ví dụ có tối đa ba lần retry. Nếu cả bốn lần đều thất bại, record được chuyển tới DLT theo cấu hình. Với backoff cố định hai giây, thời gian chờ mục tiêu trước các lần retry lần lượt là hai giây, hai giây và hai giây.

Backoff cố định phù hợp khi dịch vụ phụ thuộc thường phục hồi nhanh và tải retry ổn định. Tuy nhiên, nếu một hệ thống đang quá tải, nhiều record cùng retry sau đúng một khoảng thời gian có thể tạo thành một đợt tải mới.

## 3. Exponential backoff

Exponential backoff tăng khoảng chờ sau mỗi lần thất bại. Công thức cơ bản:

\[
d_n = \min(d_0 \times m^{n-1}, d_{max})
\]

Trong đó:

- \(d_0\) là khoảng chờ ban đầu (`delay`).
- \(m\) là hệ số tăng (`multiplier`), thường lớn hơn 1.
- \(d_{max}\) là giới hạn tối đa (`maxDelay`).
- \(n\) là thứ tự lần retry, bắt đầu từ 1.

Ví dụ cấu hình `delay = 1 giây`, `multiplier = 2` và `maxDelay = 6 giây` tạo lịch chờ 1, 2, 4, 6, 6 giây cho các lần retry liên tiếp. Giới hạn tối đa ngăn khoảng chờ tăng vô hạn.

```java
@RetryableTopic(
        attempts = "6",
        backoff = @Backoff(
                delay = 1_000L,
                multiplier = 2.0,
                maxDelay = 6_000L),
        dltTopicSuffix = "-dlt")
@KafkaListener(topics = "${app.kafka.orders-topic}")
public void onOrder(OrderCreated event) {
    orderService.handle(event);
}
```

Với `attempts = "6"`, listener có một lần xử lý ban đầu và tối đa năm lần retry. Lịch thời gian chờ mục tiêu trước các lần thử là:

| Lần xử lý | Nơi nhận record | Backoff trước lần này |
| --- | --- | ---: |
| 1 | Topic chính | 0 giây |
| 2 | Retry topic lần 1 | 1 giây |
| 3 | Retry topic lần 2 | 2 giây |
| 4 | Retry topic lần 3 | 4 giây |
| 5 | Retry topic lần 4 | 6 giây |
| 6 | Retry topic lần 5 | 6 giây |
| Sau lần 6 thất bại | DLT | Không còn retry |

Tổng thời gian chờ mục tiêu trước lần xử lý thứ sáu là 19 giây, chưa tính thời gian xử lý và độ trễ vận chuyển record. Bảng giúp ước lượng thời gian phục hồi và đặt giới hạn phù hợp với yêu cầu nghiệp vụ.

## 4. Đọc đúng các thuộc tính backoff

Các thuộc tính thường dùng trong `@Backoff`:

| Thuộc tính | Ý nghĩa | Cách chọn |
| --- | --- | --- |
| `delay` | Khoảng chờ đầu tiên hoặc khoảng chờ cố định, tính bằng mili giây | Đặt theo thời gian tối thiểu cần để dịch vụ phụ thuộc phục hồi |
| `multiplier` | Hệ số nhân khoảng chờ sau mỗi lần retry | Dùng giá trị lớn hơn 1 để tăng dần; giá trị 1 giữ khoảng chờ không đổi |
| `maxDelay` | Giới hạn khoảng chờ khi dùng exponential backoff | Đặt giới hạn để thời gian retry không vượt quá SLA hoặc thời hạn xử lý |
| `random` | Bật biến thiên ngẫu nhiên cho lịch exponential backoff theo hỗ trợ của Spring Retry | Cân nhắc để tránh nhiều record cùng retry tại một thời điểm |

`@Backoff` là annotation của Spring Retry, được Spring Kafka sử dụng khi khai báo backoff cho retry topic. Các giá trị phải phù hợp với phiên bản dependency của dự án. Nếu chỉ khai báo `delay`, lịch là cố định. Khi dùng `multiplier`, hãy đặt `maxDelay` rõ ràng để dễ dự đoán giới hạn trên.

## 5. Attempts và số retry

`attempts` biểu thị tổng số lần listener được gọi, tính cả lần đầu trên topic chính. Số lần retry tối đa là:

\[
\text{retries} = \text{attempts} - 1
\]

Ví dụ:

| `attempts` | Lần đầu | Số lần retry tối đa |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 3 | 1 | 2 |
| 4 | 1 | 3 |
| 6 | 1 | 5 |

Đừng đặt `attempts` theo số lần retry mong muốn mà quên lần xử lý đầu tiên. Nếu cần một lần đầu và bốn lần retry, hãy đặt `attempts = "5"`.

Không phải mọi exception đều nên đi qua lịch retry. Có thể dùng `include` để chỉ định nhóm exception được retry hoặc `exclude` để loại trừ lỗi không thể phục hồi, tùy chính sách và phiên bản Spring Kafka. Ví dụ, lỗi timeout dịch vụ đối tác có thể retry, trong khi lỗi validation dữ liệu cố định nên đi thẳng tới DLT.

## 6. Retry topic và việc định tuyến theo khoảng chờ

Spring Kafka dùng lịch backoff để xác định retry topic mà record sẽ được chuyển tới. Với lịch exponential, mỗi khoảng chờ khác nhau có thể cần một retry topic riêng. Với lịch cố định, framework có thể tái sử dụng retry topic theo chiến lược được cấu hình.

Một số lựa chọn cấu hình ảnh hưởng đến topology:

- `retryTopicSuffix` và `dltTopicSuffix`: hậu tố tên retry topic và DLT.
- `topicSuffixingStrategy`: cách tạo hậu tố cho từng retry topic, ví dụ theo chỉ số hoặc theo khoảng chờ.
- `sameIntervalTopicReuseStrategy`: cách tái sử dụng topic khi nhiều lần retry có cùng khoảng chờ, nếu phiên bản Spring Kafka hỗ trợ cấu hình này.
- `autoCreateTopics` hoặc cấu hình topic do ứng dụng quản lý: quyết định cách tạo topic và số partition/replica.

Hãy kiểm tra topology được tạo ra ở môi trường thực tế. Không nên giả định một topic duy nhất cho mọi retry hoặc tự tạo tên topic theo một ví dụ mà không đối chiếu suffix strategy đang dùng.

Retry topic cần được cấp số partition, replication factor và ACL phù hợp. Số partition ảnh hưởng khả năng xử lý song song; concurrency của retry listener không thể vượt qua giới hạn phân vùng có thể phân công. Theo dõi lag của từng retry topic để phát hiện một nhóm khoảng chờ bị tồn đọng.

## 7. Backoff và thứ tự xử lý sự kiện

Non-blocking retry cho phép topic chính tiếp tục xử lý record sau khi một record lỗi đã được chuyển sang retry topic. Vì vậy, thứ tự xử lý tổng thể có thể thay đổi. Ví dụ, sự kiện `OrderCreated` bị lỗi và được chuyển sang retry topic; `OrderCancelled` đến sau có thể được xử lý trước khi `OrderCreated` được retry thành công.

Điều này đặc biệt quan trọng khi các sự kiện cùng key hoặc cùng aggregate phụ thuộc vào thứ tự. Nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt, cần cân nhắc blocking retry bằng `DefaultErrorHandler`, thiết kế sequence/version check trong consumer hoặc tách luồng sự kiện theo cách phù hợp. Không nên dùng non-blocking retry chỉ vì backoff linh hoạt mà bỏ qua yêu cầu ordering.

## 8. Chọn backoff theo đặc tính lỗi

| Tình huống | Backoff phù hợp | Lý do |
| --- | --- | --- |
| Lỗi dịch vụ phụ thuộc thường hồi phục trong thời gian ngắn | Fixed backoff | Lịch đơn giản, dễ dự đoán |
| Dịch vụ có thể quá tải kéo dài | Exponential backoff có `maxDelay` | Tăng dần thời gian nghỉ, giảm áp lực retry |
| Nhiều record có thể thất bại đồng thời | Exponential backoff có random/jitter nếu phù hợp | Giảm hiện tượng retry đồng loạt |
| Sự kiện có thời hạn xử lý ngắn | Backoff ngắn, ít attempts | Tránh retry sau khi kết quả không còn giá trị |
| Sự kiện cần thứ tự tuyệt đối trong partition | Xem xét blocking retry hoặc thiết kế ordering riêng | Retry topic có thể làm record sau vượt trước record lỗi |

Backoff quá ngắn có thể tạo retry storm. Backoff quá dài làm tăng thời gian xử lý cuối cùng và tồn đọng ở retry topic. Hãy chọn số lần thử và lịch chờ dựa trên SLA, thời gian phục hồi thực tế của dịch vụ phụ thuộc và mức độ quan trọng của sự kiện.

## 9. Quan sát và vận hành

Để biết lịch backoff có hiệu quả, hãy theo dõi:

- Số record được chuyển vào từng retry topic và DLT.
- Consumer lag và tuổi của record cũ nhất trên từng retry topic.
- Tỷ lệ retry thành công ở từng lần thử.
- Tổng thời gian từ lần nhận đầu tiên đến khi xử lý thành công hoặc vào DLT.
- Lỗi publish sang retry topic, lỗi deserialize và lỗi xử lý tại retry listener.
- Số record được phát lại từ DLT và tỷ lệ phát lại thành công.

Khi thay đổi `attempts`, `delay`, `multiplier` hoặc `maxDelay`, topology retry topic có thể thay đổi. Cần triển khai topic tương ứng, kiểm tra quyền truy cập và có kế hoạch xử lý record đang nằm trong topic cũ trước khi thay đổi cấu hình ở production.

## 10. Kiểm thử lịch backoff

Kiểm thử nên xác nhận số lần gọi listener, thứ tự chuyển topic và thời gian chờ theo lịch, nhưng không nên phụ thuộc vào so sánh thời gian chính xác đến từng mili giây. Có thể dùng embedded Kafka hoặc broker kiểm thử, kết hợp spy/mock service để đếm số lần xử lý.

1. Gửi một record khiến listener thất bại ở các lần đầu và thành công ở lần sau; xác minh record được chuyển qua retry topic theo đúng thứ tự.
2. Với fixed backoff, xác minh khoảng chờ giữa các lần thử gần bằng `delay` đã cấu hình trong giới hạn sai số của môi trường test.
3. Với exponential backoff, xác minh các khoảng chờ tăng theo `multiplier` và không vượt `maxDelay`.
4. Kiểm tra `attempts` bao gồm lần đầu, số lần retry thực tế bằng `attempts - 1`.
5. Làm listener thất bại ở tất cả lần thử; xác minh record cuối cùng tới DLT.
6. Gửi hai sự kiện cùng key, trong đó sự kiện đầu bị retry; xác minh ứng dụng xử lý đúng yêu cầu ordering đã chọn.

## 11. Checklist triển khai

- [ ] `@RetryableTopic` khai báo `attempts` theo tổng số lần xử lý, gồm lần đầu.
- [ ] `@Backoff` có `delay` phù hợp; nếu dùng exponential, đã đặt `multiplier` và `maxDelay` rõ ràng.
- [ ] Đã quyết định có dùng random/jitter để tránh retry đồng loạt hay không.
- [ ] Exception retryable và not retryable được phân loại theo nguyên nhân nghiệp vụ.
- [ ] Retry topic và DLT có tên, partition, replication và ACL phù hợp.
- [ ] Đã xem xét ảnh hưởng của retry topic đến thứ tự sự kiện cùng key/partition.
- [ ] Có metric cho lag, tuổi record, tỷ lệ retry thành công và số record vào DLT.
- [ ] Đã kiểm thử lịch backoff, giới hạn attempts, DLT và trường hợp retry thất bại liên tục.

Backoff giữa các retry topic là công cụ điều tiết thời điểm thử lại. Một lịch cố định phù hợp với lỗi ngắn hạn và ổn định; exponential backoff phù hợp khi hệ thống cần thêm thời gian phục hồi sau nhiều lần thất bại. Kết hợp lịch chờ với phân loại exception, DLT, yêu cầu ordering và giám sát sẽ giúp luồng non-blocking retry hoạt động có kiểm soát.
