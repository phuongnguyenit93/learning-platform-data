# Chủ động gọi poll và xử lý trạng thái không có thông điệp

Spring Cloud Stream hỗ trợ hai cách tiêu thụ message phổ biến. Với message-driven consumer, framework nhận message và gọi hàm xử lý khi message đến. Với pollable consumer, ứng dụng chủ động yêu cầu nguồn đầu vào kiểm tra và giao một message bằng cách gọi PollableMessageSource.poll(). Cách thứ hai hữu ích khi ứng dụng cần tự kiểm soát nhịp đọc, giới hạn số message trong một chu kỳ, phối hợp với lịch công việc hoặc chỉ xử lý khi tài nguyên sẵn sàng.

Một lần gọi poll không nhất thiết nhận được message. Phương thức trả về true khi có message được lấy và chuyển cho handler; trả về false khi lần poll đó không nhận được message. Kết quả false là một trạng thái bình thường của luồng xử lý, không phải lỗi nghiệp vụ hay dấu hiệu broker hỏng. Ứng dụng cần quyết định nên chờ, thử lại sau, kết thúc chu kỳ hiện tại hay ghi nhận trạng thái rảnh.

Bài học này tập trung vào API poll, ý nghĩa của kết quả boolean, cách xử lý message trong handler, cách tránh vòng lặp bận khi không có dữ liệu và cách giới hạn số message đọc trong một chu kỳ. Nội dung cũng đề cập lỗi xử lý, acknowledgement theo binder, kiểm thử, giám sát và shutdown an toàn.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của PollableMessageSource trong mô hình consumer chủ động.
- Sử dụng poll(MessageHandler) và diễn giải đúng kết quả true hoặc false.
- Phân biệt trạng thái không có message với exception khi đọc hoặc xử lý.
- Thiết kế một chu kỳ poll có giới hạn để xử lý batch mà không chiếm tài nguyên vô hạn.
- Chọn lịch polling, khoảng chờ và backoff phù hợp.
- Xử lý message trong handler và hiểu giới hạn của acknowledgement/redelivery theo binder.
- Kiểm thử cả trường hợp có message, không có message và handler phát sinh lỗi.
- Theo dõi empty poll, throughput, backlog và tình trạng consumer trong môi trường triển khai.

## 1. Pollable consumer là gì?

Pollable consumer cho phép ứng dụng quyết định khi nào yêu cầu broker giao message. Thay vì để framework tự động gọi một Consumer<T> mỗi khi message đến, ứng dụng lấy một đối tượng PollableMessageSource rồi gọi poll() trong lịch hoặc vòng điều khiển do mình quản lý.

API chính nằm trong package:

~~~java
org.springframework.cloud.stream.binder.PollableMessageSource
~~~

Một lần poll nhận một Message<?> và chuyển message đó cho MessageHandler. API cơ bản có dạng:

~~~java
boolean poll(MessageHandler handler);
~~~

Một overload khác cho phép chỉ rõ kiểu đích khi cần chuyển đổi payload:

~~~java
boolean poll(
        MessageHandler handler,
        ParameterizedTypeReference<?> type);
~~~

Chi tiết overload có thể khác theo phiên bản Spring Cloud Stream; hãy kiểm tra API của dependency đang dùng. Ý nghĩa quan trọng nhất của phương thức cơ bản là kết quả boolean cho biết lần poll có nhận được message hay không.

### 1.1. Khi nào nên dùng pollable consumer?

Pollable consumer phù hợp khi ứng dụng cần chủ động điều tiết tốc độ tiêu thụ, ví dụ:

- Chỉ đọc message khi một tài nguyên nội bộ còn dung lượng.
- Mỗi chu kỳ chỉ xử lý tối đa một số lượng message nhất định.
- Kết hợp đọc message với một scheduler hoặc một vòng xử lý batch.
- Điều khiển thời gian chờ giữa các lần kiểm tra queue.
- Tích hợp với một thành phần điều phối có sẵn trong ứng dụng.

Nếu chỉ cần xử lý message ngay khi đến và không có yêu cầu điều khiển nhịp đọc, message-driven consumer thường đơn giản hơn. Polling làm tăng trách nhiệm quản lý lịch, thời gian chờ, retry và shutdown cho ứng dụng.

## 2. Ý nghĩa của kết quả poll()

Kết quả trả về của poll() có hai trạng thái chính:

| Kết quả | Ý nghĩa | Hành động thường phù hợp |
|---|---|---|
| true | Có message được nhận và chuyển cho handler | Xử lý kết quả, có thể tiếp tục poll nếu còn ngân sách |
| false | Lần poll không nhận được message | Kết thúc chu kỳ hoặc chờ trước lần poll tiếp theo |

Khi không có message, handler không được gọi. Ứng dụng không nên tạo một message giả hoặc gọi handler với payload rỗng để biểu diễn queue trống. Trạng thái rỗng đã được thể hiện bằng kết quả false.

### 2.1. false không đồng nghĩa với lỗi

Queue có thể đang rỗng, message có thể chưa đến, hoặc message phù hợp chưa sẵn sàng để giao cho consumer tại thời điểm poll. Với Kafka, một consumer có thể không nhận record mới trong lần poll hiện tại dù topic vẫn tồn tại và các partition khác đang có hoạt động. Với RabbitMQ, queue có thể tạm thời không có message sẵn sàng để giao.

Vì vậy, false chỉ mô tả kết quả của lần poll đó. Nó không chứng minh rằng:

- Broker đã dừng.
- Destination không tồn tại.
- Consumer group bị lỗi.
- Không còn message nào được producer phát trong tương lai.
- Toàn bộ hệ thống không có message ở mọi partition hoặc queue.

Nếu cần chẩn đoán broker, hãy dùng health check, metrics và exception của binder. Không dùng số lần false làm bằng chứng duy nhất cho một sự cố kết nối.

### 2.2. Phân biệt false với exception

Một lần poll có thể không nhận được message và trả về false. Đây là kết quả bình thường. Những tình huống như lỗi kết nối, lỗi chuyển đổi, lỗi handler hoặc lỗi binder có thể được biểu diễn bằng exception.

| Tình huống | Dấu hiệu | Cách xử lý |
|---|---|---|
| Không có message | poll() trả false | Chờ hoặc kết thúc chu kỳ |
| Có message và xử lý thành công | poll() trả true | Cập nhật metrics thành công |
| Handler thất bại | Exception được ném ra từ quá trình poll/handler | Ghi nhận lỗi và áp dụng chính sách binder phù hợp |
| Broker hoặc kết nối gặp lỗi | Exception từ binder/client | Cảnh báo, backoff và phục hồi kết nối |
| Payload không chuyển đổi được | Exception chuyển đổi | Cách ly hoặc xử lý message lỗi theo chính sách |

Không nên bắt mọi exception rồi xem như queue rỗng. Nếu lỗi kết nối bị chuyển thành trạng thái false, ứng dụng có thể im lặng trong khi consumer thực tế đã ngừng hoạt động.

## 3. Thực hiện một lần poll

Giả sử ứng dụng đã có một input binding được cấu hình thành PollableMessageSource và Spring đã inject đối tượng đó vào consumer:

~~~java
import org.springframework.cloud.stream.binder.PollableMessageSource;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

public class OrderPoller {

    private final PollableMessageSource source;

    public OrderPoller(PollableMessageSource source) {
        this.source = source;
    }

    public boolean pollOnce() {
        return source.poll(message -> process(message));
    }

    private void process(Message<?> message) {
        System.out.println("Received: " + message.getPayload());
    }
}
~~~

Ví dụ tập trung vào thao tác poll; cách khai báo và inject pollable input binding phụ thuộc mô hình binding và phiên bản Spring Cloud Stream của ứng dụng. Khi wiring, phải bảo đảm đối tượng được inject là pollable source của đúng input binding.

pollOnce() trả lại boolean để tầng điều phối quyết định bước tiếp theo. Việc tách thao tác poll khỏi lịch chạy giúp unit test dễ hơn và cho phép cùng một consumer được gọi từ scheduler, executor hoặc một cơ chế điều phối khác.

### 3.1. Xử lý message trong handler

Handler nhận một Spring Message<?>. Payload là dữ liệu nghiệp vụ; header có thể chứa content type, correlation ID, event ID hoặc metadata của binder.

~~~java
private void process(Message<?> message) {
    Object payload = message.getPayload();
    Object eventId = message.getHeaders().get("eventId");
    Object correlationId = message.getHeaders().get("correlationId");

    // Kiểm tra kiểu và dữ liệu trước khi thực hiện tác động nghiệp vụ.
    orderService.handle(payload, eventId, correlationId);
}
~~~

Trong mã thực tế, nên kiểm tra kiểu payload và header bắt buộc trước khi ép kiểu hoặc gọi service. Không ghi toàn bộ payload nhạy cảm vào log. Nếu handler cần kiểu DTO cụ thể, có thể dùng overload với ParameterizedTypeReference khi binder và converter hỗ trợ chuyển đổi tương ứng.

## 4. Xử lý trạng thái không có message

Một chu kỳ poll thường có ba bước:

1. Gọi poll() để kiểm tra nguồn.
2. Nếu có message, handler xử lý message.
3. Nếu không có message, kết thúc chu kỳ hiện tại hoặc chờ theo lịch đã chọn.

Ví dụ một lần poll có xử lý rõ trạng thái rỗng:

~~~java
public void runOneCycle() {
    try {
        boolean received = source.poll(message -> process(message));

        if (received) {
            metrics.incrementReceived();
        } else {
            metrics.incrementEmptyPoll();
        }
    } catch (Exception ex) {
        metrics.incrementPollFailure();
        log.error("Polling order message failed", ex);
    }
}
~~~

Điểm quan trọng là tách ba trạng thái: có message, không có message và có lỗi. Trạng thái rỗng có thể được ghi nhận ở mức debug hoặc metrics; không nên phát cảnh báo lỗi mỗi lần queue tạm thời trống.

### 4.1. Không dùng vòng lặp bận

Đoạn code sau không phù hợp:

~~~java
while (true) {
    source.poll(this::process);
}
~~~

Khi queue rỗng, vòng lặp vẫn liên tục gọi poll mà không nghỉ. Điều này có thể tiêu thụ CPU, tạo log/metrics quá nhiều và tăng số lần gọi broker không cần thiết.

Thêm một khoảng chờ đơn giản giúp giảm tải:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    boolean received = source.poll(this::process);
    if (!received) {
        Thread.sleep(250);
    }
}
~~~

Đây chỉ là ví dụ minh họa. Ứng dụng production cần xử lý InterruptedException, dừng executor khi shutdown và phân biệt exception của poll với trạng thái rỗng. Với ứng dụng Spring, một scheduler thường dễ quản lý vòng đời hơn một vòng lặp tự chạy vô hạn.

### 4.2. Chọn khoảng chờ

Khoảng chờ ảnh hưởng trực tiếp đến độ trễ và tải:

- Khoảng chờ ngắn giúp phát hiện message mới nhanh hơn nhưng tạo nhiều lần poll khi queue rỗng.
- Khoảng chờ dài giảm số lần poll nhưng tăng thời gian message phải chờ trước khi được xử lý.
- Khoảng chờ cố định dễ dự đoán và phù hợp với tải ổn định.
- Backoff tăng dần phù hợp khi nguồn thường rỗng hoặc broker/dịch vụ phụ thuộc đang quá tải.

Không có một giá trị phù hợp cho mọi hệ thống. Hãy chọn dựa trên SLA độ trễ, lưu lượng message, giới hạn tài nguyên và chi phí mỗi lần poll.

## 5. Poll một message hay xử lý theo batch?

PollableMessageSource.poll(handler) xử lý một message cho mỗi lần gọi. Ứng dụng có thể gọi nhiều lần trong một chu kỳ để lấy batch, nhưng nên đặt giới hạn.

Ví dụ xử lý tối đa 50 message trong một chu kỳ:

~~~java
private static final int MAX_MESSAGES_PER_CYCLE = 50;

public int pollBatch() {
    int processed = 0;

    for (int i = 0; i < MAX_MESSAGES_PER_CYCLE; i++) {
        boolean received = source.poll(this::process);

        if (!received) {
            break;
        }

        processed++;
    }

    return processed;
}
~~~

Nếu poll trả false, chu kỳ dừng ngay vì hiện không có message sẵn sàng. Nếu đủ 50 message, chu kỳ cũng dừng dù nguồn có thể vẫn còn dữ liệu. Lần scheduler tiếp theo tiếp tục công việc.

### 5.1. Vì sao cần giới hạn batch?

Nếu vòng lặp tiếp tục cho đến khi queue rỗng, một đợt backlog lớn có thể khiến chu kỳ chiếm thread quá lâu. Các tác vụ khác như health check, cập nhật trạng thái hoặc công việc định kỳ có thể bị trì hoãn.

Giới hạn batch giúp:

- Phân bổ thời gian CPU giữa các công việc.
- Kiểm soát số message mà một lần chạy có thể xử lý.
- Tránh một nguồn có backlog lớn chiếm toàn bộ worker.
- Tạo điểm kiểm tra shutdown giữa các chu kỳ.
- Dễ đo thời gian xử lý và throughput theo batch.

### 5.2. Batch count không phải batch transaction

Gọi poll 50 lần không có nghĩa 50 message nằm trong một transaction chung. Mỗi lần poll có thể có vòng đời giao nhận riêng, tùy binder. Nếu nghiệp vụ cần tất cả message cùng thành công hoặc cùng rollback, cần một cơ chế transaction được hỗ trợ và phải xác minh phạm vi transaction thực tế.

Không nên tự gom message thành batch rồi xác nhận tất cả trước khi lưu kết quả nghiệp vụ. Nếu ứng dụng chết giữa batch, có thể mất tiến độ hoặc tạo duplicate tùy thứ tự acknowledgement.

## 6. Lập lịch polling bằng Spring

Một cách triển khai dễ quản lý là dùng @Scheduled để gọi một chu kỳ có giới hạn:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
class ScheduledOrderPoller {

    private final PollableMessageSource source;

    ScheduledOrderPoller(PollableMessageSource source) {
        this.source = source;
    }

    @Scheduled(fixedDelay = 500)
    public void pollAvailableMessages() {
        for (int i = 0; i < 50; i++) {
            boolean received = source.poll(this::process);
            if (!received) {
                return;
            }
        }
    }

    private void process(Message<?> message) {
        // Thực hiện xử lý nghiệp vụ.
    }
}
~~~

Ứng dụng cần bật scheduling bằng @EnableScheduling trong cấu hình Spring:

~~~java
@Configuration
@EnableScheduling
class SchedulingConfiguration {}
~~~

fixedDelay tính khoảng thời gian từ lúc một lần thực thi kết thúc đến lần kế tiếp. Cách này tránh việc lịch chạy mới được kích hoạt ngay khi lần trước còn đang thực hiện. Nếu cần cron hoặc lịch theo thời điểm, có thể dùng thuộc tính cron của @Scheduled.

### 6.1. Không để exception làm hỏng lịch

Trong ví dụ trên, nếu source.poll() hoặc handler ném exception, phương thức scheduled có thể kết thúc bất thường. Hãy bắt lỗi ở ranh giới chu kỳ, ghi nhận metrics và áp dụng backoff phù hợp:

~~~java
@Scheduled(fixedDelay = 500)
public void pollAvailableMessages() {
    try {
        pollBatch();
    } catch (Exception ex) {
        log.error("Order polling cycle failed", ex);
        metrics.incrementCycleFailure();
    }
}
~~~

Không nên bắt exception rồi bỏ qua hoàn toàn. Cần log đủ ngữ cảnh, tăng counter lỗi và tạo cảnh báo nếu lỗi kéo dài. Nếu lỗi thuộc loại dữ liệu không hợp lệ, cần xử lý message theo dead-letter hoặc error channel phù hợp với binder.

### 6.2. Backoff khi liên tục không có message

Nếu nguồn thường rỗng, lịch cố định quá ngắn có thể tạo nhiều lần poll không cần thiết. Có thể dùng một bộ điều khiển khoảng chờ tăng dần:

~~~java
Duration nextDelay(int emptyPolls) {
    long millis = Math.min(5000L, 250L * (1L << Math.min(emptyPolls, 4)));
    return Duration.ofMillis(millis);
}
~~~

Đây là ý tưởng thuật toán, không phải cấu hình trực tiếp cho @Scheduled. Để áp dụng delay thay đổi theo thời gian chạy, dùng TaskScheduler hoặc một cơ chế scheduling động. Đặt giới hạn tối đa và reset backoff khi nhận được message.

Nếu message cần được xử lý gần thời gian thực, không nên để backoff quá lớn. Nếu poller dùng để đọc batch nền, khoảng chờ lớn hơn có thể giúp giảm chi phí khi không có dữ liệu.

## 7. Handler thành công, handler thất bại và acknowledgement

Khi poll lấy được message, handler xử lý payload. Cách message được xác nhận, giữ lại hoặc giao lại khi handler ném exception phụ thuộc binder và cấu hình acknowledgement/transaction.

Một số nguyên tắc:

- Chỉ coi message đã xử lý thành công sau khi tác động nghiệp vụ cần thiết hoàn tất.
- Không nuốt exception nếu binder cần exception để áp dụng chính sách reject hoặc redelivery.
- Xác định cách message lỗi được chuyển tới error channel hoặc dead-letter destination.
- Kiểm tra cấu hình retry của binder, vì retry ở consumer và retry do broker có thể tương tác.
- Thiết kế consumer idempotent vì redelivery có thể khiến cùng message được xử lý lại.

### 7.1. Kafka

Với Kafka binder, tiến độ consumer được theo dõi bằng offset của partition. Cách commit offset khi xử lý pollable consumer phụ thuộc ack mode, transaction và cấu hình binder. Nếu offset được commit trước khi xử lý nghiệp vụ hoàn tất, ứng dụng có thể bỏ qua record sau khi gặp sự cố. Nếu xử lý xong nhưng chưa commit rồi bị dừng, record có thể được đọc lại.

Vì vậy, cần kiểm tra commit behavior của phiên bản Kafka binder đang dùng và chọn chính sách phù hợp. Không giả định poll() trả true đồng nghĩa offset đã được commit bền vững.

### 7.2. RabbitMQ

Với Rabbit binder, message thường được xác nhận theo acknowledgement mode và trạng thái xử lý. Nếu consumer dừng trước khi ack, broker có thể giao lại message. Cách reject, requeue và dead-letter phụ thuộc cấu hình container/binder.

Không giả định queue trống sau khi poll() trả false là queue đã được xử lý hết vĩnh viễn. Producer có thể gửi message mới ngay sau đó; message chưa được giao cũng có thể đang ở trạng thái khác trong broker.

### 7.3. Idempotency

Pollable consumer nên chịu được việc một message được giao nhiều lần. Có thể dùng event ID ổn định và lưu dấu đã xử lý trong database:

~~~java
void processOrder(Message<OrderCreated> message) {
    String eventId = (String) message.getHeaders().get("eventId");

    if (processedEventRepository.exists(eventId)) {
        return;
    }

    transactionTemplate.executeWithoutResult(status -> {
        orderService.apply(message.getPayload());
        processedEventRepository.markProcessed(eventId);
    });
}
~~~

Đoạn code minh họa cần bảo đảm kiểm tra và ghi dấu event ID có tính nguyên tử trong transaction phù hợp; chỉ gọi exists() rồi markProcessed() mà không có unique constraint hoặc khóa có thể vẫn gặp race condition khi nhiều instance xử lý cùng event.

## 8. Không có message và các trạng thái vận hành khác

Một consumer có thể quan sát nhiều trạng thái khác nhau:

| Trạng thái | Diễn giải | Phản ứng |
|---|---|---|
| Empty poll | Không có message trong lần kiểm tra | Chờ theo lịch |
| Message received | Có message được chuyển cho handler | Xử lý và ghi nhận kết quả |
| Handler failure | Xử lý nghiệp vụ thất bại | Áp dụng retry/DLQ và cảnh báo |
| Polling exception | Binder hoặc quá trình poll gặp lỗi | Backoff, phục hồi và cảnh báo |
| Conversion failure | Payload không thể chuyển thành kiểu cần thiết | Cách ly message lỗi |
| Shutdown requested | Ứng dụng cần dừng | Ngừng poll mới, hoàn tất hoặc để broker giao lại công việc dở |

Không gộp tất cả các trạng thái này thành một biến boolean duy nhất ở tầng ứng dụng. Boolean của poll chỉ cho biết lần gọi có nhận message hay không; lỗi và shutdown cần được biểu diễn riêng.

### 8.1. Empty poll có thể là tín hiệu bình thường

Một số hệ thống có tải theo đợt: ban đêm gần như không có message, đến giờ làm việc lưu lượng tăng. Trong trường hợp này, empty poll là một trạng thái hoạt động bình thường.

Không nên gửi cảnh báo mỗi khi poll() trả false. Thay vào đó, theo dõi tỷ lệ empty poll, thời gian không nhận được message và backlog ở nguồn. Chỉ cảnh báo khi trạng thái rỗng vượt kỳ vọng nghiệp vụ, ví dụ một nguồn được cam kết phải phát dữ liệu trong một khoảng thời gian nhất định nhưng không có message mới.

### 8.2. Empty poll không phải bằng chứng của consumer lag bằng không

Với hệ thống phân vùng, một lần poll không nhận message không chứng minh mọi partition đều không có dữ liệu. Consumer có thể đang được gán một tập partition, còn dữ liệu hoặc tiến độ ở partition khác. Hãy dùng consumer lag của Kafka hoặc queue depth của RabbitMQ để đo backlog thay vì suy luận từ một lần poll.

## 9. Kiểm thử pollable consumer

Kiểm thử cần xác minh cả hai nhánh boolean và nhánh exception.

### 9.1. Unit test kết quả có message

Có thể mock PollableMessageSource để kiểm tra handler được truyền vào và kết quả true:

~~~java
@Test
void reportsMessageReceived() {
    PollableMessageSource source = mock(PollableMessageSource.class);
    OrderPoller poller = new OrderPoller(source);

    when(source.poll(any(MessageHandler.class))).thenReturn(true);

    assertThat(poller.pollOnce()).isTrue();
}
~~~

Nếu cần kiểm tra handler thực sự xử lý payload, mock có thể lấy MessageHandler được truyền vào rồi gọi handleMessage(message) trong câu trả lời của stub.

### 9.2. Unit test empty poll

~~~java
@Test
void reportsNoMessageWithoutCallingBusinessHandler() {
    PollableMessageSource source = mock(PollableMessageSource.class);
    OrderPoller poller = new OrderPoller(source);

    when(source.poll(any(MessageHandler.class))).thenReturn(false);

    assertThat(poller.pollOnce()).isFalse();
    verify(source).poll(any(MessageHandler.class));
}
~~~

Test này xác minh ứng dụng nhận diện empty poll và không xem nó là lỗi. Nếu có metrics, hãy kiểm tra empty counter tăng đúng một lần.

### 9.3. Unit test exception

~~~java
@Test
void propagatesOrRecordsPollingFailure() {
    PollableMessageSource source = mock(PollableMessageSource.class);
    when(source.poll(any(MessageHandler.class)))
            .thenThrow(new IllegalStateException("broker unavailable"));

    OrderPoller poller = new OrderPoller(source);

    assertThatThrownBy(poller::pollOnce)
            .isInstanceOf(IllegalStateException.class);
}
~~~

Nếu lớp poller bắt exception và ghi nhận metrics thay vì ném lại, test cần xác minh counter lỗi và hành vi backoff tương ứng.

### 9.4. Integration test với binder

Test binder có thể xác minh input binding và message được nhận khi có dữ liệu. Với broker thật, nên kiểm thử:

- Poll khi queue/topic có message.
- Poll khi không có message.
- Message được ack sau khi handler thành công theo cấu hình.
- Handler lỗi dẫn tới retry, reject hoặc redelivery như mong đợi.
- Consumer dừng giữa lúc xử lý và message được phục hồi theo semantics của broker.
- Payload và header được chuyển đổi đúng.

Đối với Kafka, kiểm tra offset và consumer group. Đối với RabbitMQ, kiểm tra acknowledgement, requeue và dead-letter. Không dùng test mock để kết luận về semantics giao nhận của broker thật.

## 10. Quan sát và cảnh báo

Một pollable consumer cần metrics riêng cho hoạt động polling:

| Metric | Mục đích |
|---|---|
| poll.attempts | Tổng số lần gọi poll |
| poll.received | Số lần poll nhận được message |
| poll.empty | Số lần poll không nhận được message |
| poll.failures | Số lần poll/handler phát sinh lỗi |
| poll.duration | Thời gian mỗi lần poll hoặc chu kỳ |
| message.processing.duration | Thời gian xử lý nghiệp vụ |
| message.processing.failures | Số message xử lý thất bại |
| consumer.backlog | Số message đang chờ hoặc lag theo broker |
| consumer.last.success | Thời điểm xử lý thành công gần nhất |

Tên metric chỉ là gợi ý cho hệ thống quan sát; hãy chuẩn hóa theo convention của ứng dụng. Tránh dùng event ID hoặc customer ID làm label có cardinality cao.

### 10.1. Khi nào cần cảnh báo?

Có thể cảnh báo khi:

- Poll exception tăng liên tục.
- Không có message trong khoảng thời gian dài hơn SLA của nguồn.
- Thời gian xử lý tăng bất thường.
- Backlog hoặc consumer lag tăng liên tục.
- Tỷ lệ handler failure vượt ngưỡng.
- Consumer không có lần xử lý thành công trong khoảng thời gian dự kiến.

Empty poll đơn lẻ thường không cần cảnh báo. Cần kết hợp nó với kỳ vọng lưu lượng và backlog để tránh false alarm.

## 11. Shutdown và khả năng phục hồi

Khi ứng dụng nhận tín hiệu dừng, cần ngăn lịch tạo thêm chu kỳ poll mới. Nếu đang xử lý message, hãy xác định thời gian cho phép hoàn tất và cách broker xử lý message chưa được xác nhận.

Một số nguyên tắc:

- Dừng scheduler hoặc executor trước khi đóng binder connection.
- Không bắt đầu batch mới khi ứng dụng đang shutdown.
- Giữ thời gian graceful shutdown đủ dài cho một message/batch thông thường.
- Nếu handler chưa hoàn tất, để binder/broker áp dụng cơ chế giao lại theo cấu hình.
- Đảm bảo consumer idempotent để an toàn khi message được giao lại.
- Theo dõi số message đang xử lý và số lần redelivery sau khi khởi động lại.

Nếu dùng một vòng lặp thủ công, phải xử lý interrupt đúng cách và thoát vòng lặp khi thread bị interrupt. Không dùng Thread.sleep() mà bỏ qua InterruptedException, vì điều đó làm ứng dụng khó dừng.

## 12. Những lỗi thường gặp

1. **Coi false là lỗi broker**: empty poll chỉ nói rằng lần poll không nhận được message. Hãy phân biệt với exception và dùng health/metrics để chẩn đoán broker.
2. **Bỏ qua kết quả boolean**: ứng dụng không biết lúc nào nguồn rỗng và có thể tiếp tục gọi poll không cần thiết. Hãy kiểm tra kết quả sau mỗi lần gọi.
3. **Vòng lặp bận khi queue trống**: CPU tăng và tạo tải poll không cần thiết. Hãy dùng scheduler, delay hoặc backoff.
4. **Poll không giới hạn cho đến khi queue rỗng**: backlog lớn có thể chiếm worker quá lâu. Hãy giới hạn số message hoặc thời gian mỗi chu kỳ.
5. **Gộp exception với empty poll**: lỗi binder bị che giấu và consumer có thể ngừng hoạt động âm thầm. Hãy xử lý hai nhánh riêng.
6. **Nuốt exception trong handler**: binder có thể hiểu message đã xử lý thành công dù nghiệp vụ chưa hoàn tất. Hãy quyết định rõ khi nào exception cần được truyền ra.
7. **Giả định true có nghĩa offset đã commit**: kết quả poll chỉ phản ánh việc nhận message. Hãy kiểm tra acknowledgement/commit behavior của binder.
8. **Không thiết kế idempotency**: redelivery có thể tạo tác động nghiệp vụ lặp. Hãy dùng event ID và lưu dấu xử lý.
9. **Dùng polling quá nhanh**: tốn tài nguyên khi không có message. Hãy điều chỉnh interval theo SLA và tải thực tế.
10. **Cảnh báo mỗi lần empty poll**: tạo nhiễu và che mất lỗi thật. Hãy cảnh báo theo thời gian không hoạt động hoặc backlog.
11. **Không dừng scheduler khi shutdown**: poll mới có thể bắt đầu trong lúc binder đang đóng. Hãy quản lý vòng đời consumer.
12. **Chỉ kiểm thử nhánh có message**: lỗi xử lý trạng thái rỗng thường bị bỏ sót. Hãy kiểm thử true, false và exception.

## 13. Quy trình xây dựng pollable consumer

Khi triển khai consumer chủ động, thực hiện theo trình tự:

1. Xác định lý do cần polling thay vì message-driven consumer.
2. Khai báo input binding được expose dưới dạng PollableMessageSource.
3. Viết handler xử lý payload và header, có xác thực dữ liệu.
4. Gọi poll() và xử lý riêng kết quả true, false và exception.
5. Chọn một message mỗi lần hoặc batch có giới hạn.
6. Đặt lịch polling, delay hoặc backoff theo yêu cầu độ trễ.
7. Xác định acknowledgement, retry, reject và DLQ theo binder.
8. Thiết kế idempotency cho message có thể được giao lại.
9. Viết unit test cho có message, không có message và exception.
10. Integration test với broker thật cho ack, offset, redelivery và phục hồi.
11. Thiết lập metrics, cảnh báo và graceful shutdown.

## Kết luận

PollableMessageSource.poll() trao quyền điều khiển nhịp tiêu thụ cho ứng dụng. Kết quả true cho biết lần poll đã nhận message và chuyển cho handler; false cho biết không có message được nhận trong lần kiểm tra đó. Trạng thái rỗng là bình thường và cần được xử lý bằng cách kết thúc chu kỳ, chờ theo lịch hoặc áp dụng backoff. Exception phải được theo dõi riêng để không che giấu lỗi binder hoặc lỗi handler.

Một pollable consumer đáng tin cậy cần batch có giới hạn, lịch chạy phù hợp, chính sách acknowledgement theo binder, idempotency và kiểm thử cả ba nhánh có message, không có message và có lỗi. Theo dõi empty poll cùng backlog, thời gian xử lý và lần thành công gần nhất giúp phân biệt một nguồn đang rảnh bình thường với một consumer thực sự gặp sự cố.

## Tài liệu tham khảo

- [Spring Cloud Stream — Pollable Consumer](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
