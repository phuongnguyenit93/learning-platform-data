# Cấu hình thời gian chờ gửi, nhận và xử lý phản hồi đến muộn trong Spring Messaging

## 1. Vì sao cần cấu hình timeout?

Trong hệ thống messaging, một thao tác có thể phải chờ ở nhiều điểm: gửi message vào channel, chờ message xuất hiện trong queue, chờ handler xử lý, hoặc chờ phản hồi quay lại. Nếu không giới hạn thời gian chờ, thread và tài nguyên có thể bị giữ quá lâu khi consumer chậm, broker mất kết nối hoặc phản hồi không bao giờ đến.

Spring Messaging cung cấp các API có tham số timeout cho thao tác gửi, nhận và request-reply. Tuy nhiên, mỗi timeout bảo vệ một giai đoạn khác nhau. Cấu hình đúng đòi hỏi hiểu rõ **đang chờ điều gì**, **ai đang chờ**, và **điều gì xảy ra với message sau khi bên chờ hết thời gian**.

Sau bài học, bạn cần có thể:

- Phân biệt send timeout, receive timeout và request-reply timeout.
- Dùng timeout trên MessageChannel, PollableChannel và GenericMessagingTemplate.
- Hiểu giá trị trả về khi hết thời gian chờ và các lỗi có thể phát sinh.
- Giải thích vì sao timeout của bên gửi không tự hủy công việc ở consumer.
- Thiết kế correlation ID và luồng xử lý phản hồi đến muộn.
- Tránh retry gây xử lý trùng và chọn timeout phù hợp với ngân sách thời gian toàn luồng.

## 2. Ba loại timeout chính

| Loại timeout | Bên chờ | Điều kiện kết thúc | API thường gặp |
|---|---|---|---|
| Send timeout | Producer | Channel chấp nhận message hoặc hết thời gian chờ | `MessageChannel.send(message, timeout)` |
| Receive timeout | Consumer | Có message để nhận hoặc hết thời gian chờ | `PollableChannel.receive(timeout)` |
| Request-reply timeout | Thành phần gửi request | Nhận được reply hoặc hết thời gian chờ chờ reply | `GenericMessagingTemplate.sendAndReceive(...)` |

Các timeout này không thay thế cho nhau:

- Send timeout giới hạn việc chờ channel nhận message theo semantics của channel.
- Receive timeout giới hạn việc consumer chờ một message có sẵn trong pollable channel.
- Request-reply timeout giới hạn thời gian bên gọi chờ phản hồi sau khi gửi request.

Một timeout ở phía gọi không mặc nhiên là deadline xử lý nghiệp vụ ở phía nhận. Nếu handler đã bắt đầu chạy, việc bên gọi ngừng chờ không có nghĩa handler bị dừng.

## 3. Send timeout: chờ channel nhận message

### 3.1 API của MessageChannel

`MessageChannel` có overload:

~~~java
boolean send(Message<?> message, long timeout);
~~~

Tham số timeout được tính bằng milliseconds. Nó cho channel biết producer sẵn sàng chờ bao lâu để thao tác gửi được chấp nhận theo cách hoạt động của implementation.

Ví dụ:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;

public class MessagePublisher {

    private final MessageChannel outputChannel;

    public MessagePublisher(MessageChannel outputChannel) {
        this.outputChannel = outputChannel;
    }

    public boolean publish(Message<?> message) {
        return outputChannel.send(message, 500);
    }
}
~~~

Trong ví dụ, producer chờ tối đa 500 milliseconds theo semantics của channel. Kết quả boolean cho biết thao tác gửi có được chấp nhận hay không. Tùy implementation, channel cũng có thể ném exception khi không thể gửi hoặc khi handler xử lý đồng bộ phát sinh lỗi.

### 3.2 Send timeout không phải thời gian xử lý

Ý nghĩa thực tế phụ thuộc loại channel:

- Với channel dạng queue, send có thể phải chờ tới khi còn chỗ trong queue.
- Với channel dispatch đồng bộ như DirectChannel, thao tác gửi có thể gọi handler ngay trên thread của producer. Thời gian gọi có thể bao gồm thời gian handler chạy; timeout không phải cơ chế cưỡng bức dừng method nghiệp vụ.
- Với channel dispatch qua executor, send có thể chỉ chờ việc tiếp nhận task hoặc dispatch theo implementation. Nó không chứng minh handler đã hoàn tất.
- Với adapter kết nối broker, thời gian gửi chịu ảnh hưởng của adapter và client broker; việc send trả về không nhất thiết có nghĩa message đã được consumer xử lý hoặc nghiệp vụ đã commit.

Do đó, hãy đọc semantics của channel hoặc adapter đang dùng. Không diễn giải mọi send timeout như một deadline chung cho toàn bộ pipeline.

### 3.3 Xử lý khi gửi không thành công

Nếu send trả về `false`, producer cần quyết định có thể thử lại hay phải chuyển sang luồng lỗi. Nếu thao tác ném exception, cần ghi nhận lỗi với correlation ID và thông tin đích gửi phù hợp.

Không retry vô hạn trong vòng lặp chặt. Nếu retry được phép, hãy dùng:

- Số lần thử tối đa.
- Backoff có giới hạn.
- Giới hạn tổng thời gian retry.
- Idempotency key hoặc cơ chế deduplication nếu lệnh có tác dụng phụ.
- Error flow hoặc dead-letter phù hợp với hạ tầng.

Một lần gửi thất bại ở tầng channel cũng không tự nói lên trạng thái của một lần gửi trước đó nếu hệ thống có retry, timeout mạng hoặc kết quả không xác định. Với nghiệp vụ quan trọng, cần thiết kế khả năng đối soát.

## 4. Receive timeout: chờ message trong PollableChannel

### 4.1 PollableChannel.receive(timeout)

`PollableChannel` cho phép consumer chủ động chờ message:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.PollableChannel;

public class MessageConsumer {

    private final PollableChannel inputChannel;

    public MessageConsumer(PollableChannel inputChannel) {
        this.inputChannel = inputChannel;
    }

    public void pollOnce() {
        Message<?> message = inputChannel.receive(1_000);

        if (message == null) {
            System.out.println("No message within the wait period");
            return;
        }

        handle(message);
    }

    private void handle(Message<?> message) {
        System.out.println("Received: " + message.getPayload());
    }
}
~~~

Consumer chờ tối đa 1.000 milliseconds theo hợp đồng của pollable channel. Nếu không có message trong thời gian đó, API thường trả về `null`. Khi nhận được message, consumer chuyển sang xử lý.

`PollableChannel` khác `SubscribableChannel`: consumer chủ động gọi receive thay vì đăng ký một handler để channel dispatch message tới.

### 4.2 Timeout của receive không giới hạn thời gian xử lý

Khi receive trả về một message, thời gian chờ nhận đã kết thúc. Nếu `handle(message)` chạy 30 giây, receive timeout 1 giây không tự dừng handler sau 1 giây.

Muốn giới hạn thời gian xử lý cần cơ chế riêng, ví dụ:

- Timeout cho lời gọi dịch vụ bên ngoài.
- Deadline hoặc cancellation được truyền qua tầng xử lý.
- Executor có giới hạn và chính sách quản lý task.
- Timeout cho transaction hoặc thao tác truy cập dữ liệu.
- Cơ chế bù trừ nếu nghiệp vụ đã tạo tác dụng phụ trước khi timeout.

Không nên dùng receive timeout để thay thế timeout của HTTP client, database, broker request hoặc nghiệp vụ.

### 4.3 Polling liên tục

Nếu consumer polling theo chu kỳ, hãy cân nhắc khoảng chờ và tải CPU. Poll với timeout bằng 0 hoặc vòng lặp không chờ có thể tạo busy loop khi queue trống. Poll chờ quá lâu có thể làm chậm shutdown hoặc phản ứng với tín hiệu điều khiển.

Chọn thời gian poll phù hợp với độ trễ mong muốn và lifecycle của consumer. Với listener container do Spring Integration hoặc adapter quản lý, hãy dùng các tùy chọn poller/consumer tương ứng thay vì tự tạo vòng lặp nếu framework đã cung cấp cơ chế đó.

## 5. Request-reply timeout với GenericMessagingTemplate

### 5.1 Cấu hình sendTimeout và receiveTimeout

`GenericMessagingTemplate` là tiện ích trong Spring Messaging để gửi, nhận và thực hiện request-reply qua MessageChannel. `GenericMessagingTemplate` is the concrete Spring Framework class in `org.springframework.messaging.core`. Spring Integration also provides `org.springframework.integration.core.MessagingTemplate`, which extends `GenericMessagingTemplate`; do not import the latter from the Spring Messaging package.

Có thể cấu hình thời gian chờ gửi và nhận:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.messaging.core.GenericMessagingTemplate;

public class RequestClient {

    private final MessageChannel requestChannel;
    private final GenericMessagingTemplate messagingTemplate;

    public RequestClient(MessageChannel requestChannel) {
        this.requestChannel = requestChannel;

        this.messagingTemplate = new GenericMessagingTemplate();
        this.messagingTemplate.setSendTimeout(500);
        this.messagingTemplate.setReceiveTimeout(1_500);
    }

    public Message<?> lookup(String orderId) {
        Message<String> request = MessageBuilder
                .withPayload(orderId)
                .setHeader("app.correlationId", "lookup-" + orderId)
                .build();

        return messagingTemplate.sendAndReceive(
                requestChannel,
                request
        );
    }
}
~~~

Đây là phần code trong một component đã được cung cấp `requestChannel` phù hợp và có handler trả lời qua cơ chế reply channel. Nó minh họa cách đặt giới hạn gửi và thời gian chờ phản hồi; channel, endpoint và service xử lý cần được cấu hình trong application context của dự án.

- `setSendTimeout(500)` đặt giới hạn chờ cho thao tác gửi theo semantics của channel.
- `setReceiveTimeout(1_500)` đặt thời gian chờ nhận reply.
- `sendAndReceive` gửi request và chờ phản hồi theo cơ chế request-reply.

Nếu không có reply trong thời gian chờ, kết quả có thể là `null`. Cần xử lý trường hợp này rõ ràng thay vì dereference reply ngay lập tức.

### 5.2 Phân biệt timeout với exception

Một request-reply có thể kết thúc theo nhiều cách:

- Có reply hợp lệ trong thời gian chờ.
- Hết thời gian chờ mà chưa có reply.
- Không gửi được request.
- Handler hoặc adapter phát sinh exception.
- Kết nối hoặc hạ tầng bên ngoài gặp lỗi.

Không gom tất cả thành một kết quả “timeout”. Hãy phân biệt không có phản hồi với lỗi gửi và lỗi xử lý. Điều đó giúp quyết định có nên retry, trả trạng thái pending, chuyển sang error flow hay báo lỗi ngay cho caller.

Tên exception cụ thể và cách truyền lỗi phụ thuộc channel, handler, adapter và phiên bản framework. Hãy kiểm tra exception thực tế của integration đang dùng thay vì bắt mọi exception rồi coi như hết timeout.

## 6. Timeout không tự hủy xử lý ở phía consumer

Đây là nguyên tắc quan trọng nhất khi làm request-reply.

Giả sử client gửi yêu cầu tra cứu đơn hàng và chờ 1,5 giây. Server nhận request, bắt đầu truy vấn một hệ thống chậm, nhưng mất 5 giây mới có kết quả. Sau 1,5 giây, client ngừng chờ. Request đã được gửi vẫn có thể tiếp tục được xử lý ở server.

~~~text
Client                    Server / consumer
  |                              |
  |------ request -------------->|
  |                              | bắt đầu xử lý
  |                              |
  | chờ reply                    | truy vấn hệ thống ngoài
  |                              |
  | timeout sau 1,5 giây         |
  |                              | xử lý vẫn tiếp tục
  |                              |
  |                              | tạo reply sau 5 giây
  |<----- reply đến muộn --------|
~~~

Timeout phía client chỉ cho biết caller không nhận được kết quả trong ngân sách thời gian của nó. Nó không chứng minh server chưa xử lý, đã hủy xử lý hoặc chưa tạo tác dụng phụ.

Nếu thao tác là tạo đơn hàng, thanh toán hoặc cập nhật dữ liệu, caller không nên gửi lại một lệnh mới chỉ vì lần chờ đầu tiên đã hết hạn. Lệnh đầu có thể đã thành công nhưng reply bị chậm hoặc thất lạc.

## 7. Phản hồi đến muộn và temporary reply channel

Trong request-reply, `GenericMessagingTemplate` có thể sử dụng reply channel tạm thời gắn với request. Caller chờ trên channel đó trong thời gian được cấu hình.

Nếu thời gian chờ đã kết thúc mà reply mới đến sau đó, caller không còn chờ trên luồng request ban đầu. Hành vi cụ thể của reply muộn phụ thuộc reply channel và adapter; nó có thể bị từ chối, không còn được tiêu thụ hoặc được ghi nhận như một lỗi giao nhận. Không nên dựa vào temporary reply channel như nơi lưu trữ kết quả lâu dài.

Một reply muộn cần một chiến lược rõ ràng:

- Ghi log hoặc metric với correlation ID để biết request đã hoàn tất sau deadline.
- Không trả kết quả cũ vào một request khác chỉ vì caller đã retry.
- Nếu kết quả còn giá trị, lưu kết quả vào nơi bền vững hoặc phát một event riêng.
- Nếu kết quả không còn giá trị, bỏ qua có kiểm soát và ghi nhận trạng thái.
- Có chính sách dọn dẹp cho các request đang chờ đã hết hạn.

Không giả định reply muộn luôn tự động được chuyển sang một hàng đợi có thể đọc lại. Nếu cần xử lý kết quả sau khi caller timeout, hãy thiết kế destination và storage rõ ràng.

## 8. Thiết kế correlation ID và luồng phản hồi bất đồng bộ

Với công việc có thể lâu hơn timeout đồng bộ, nên chuyển sang mô hình bất đồng bộ:

1. Client gửi command kèm một request ID hoặc idempotency key.
2. Server xác nhận đã nhận command bằng response ngắn hoặc trạng thái accepted.
3. Worker xử lý nghiệp vụ độc lập.
4. Kết quả được lưu lại hoặc phát thành event có cùng correlation ID.
5. Client nhận event khi đang kết nối, hoặc truy vấn trạng thái bằng request ID sau đó.

Ví dụ luồng:

~~~text
Client
  |
  | Submit command (requestId=R-123)
  v
API / messaging ingress
  |
  | accepted
  v
Client nhận trạng thái PENDING
  |
  v
Worker xử lý nghiệp vụ
  |
  | OrderProcessed (correlationId=R-123)
  v
Event destination / result store
  |
  +----> Client đang online nhận event
  |
  +----> Client reconnect và truy vấn kết quả
~~~

Correlation ID liên kết request và response. Idempotency key giúp server nhận diện những lần gửi lặp của cùng một thao tác. Hai khái niệm có thể dùng chung một giá trị nếu hợp đồng cho phép, nhưng mục đích khác nhau: correlation phục vụ liên kết và truy vết; idempotency ngăn tác dụng phụ bị thực hiện nhiều lần.

Không dùng correlation ID như một bí mật hoặc bằng chứng xác thực. Server vẫn phải xác minh người dùng có quyền đọc kết quả tương ứng.

## 9. Chọn timeout theo ngân sách toàn luồng

Một request có thể đi qua nhiều bước: gateway, channel, broker, consumer, database và dịch vụ ngoài. Nếu mỗi bước tự đặt timeout dài mà không xét tổng thể, thời gian hoàn thành có thể vượt xa deadline mà người dùng mong đợi.

Hãy xác định:

- **End-to-end deadline:** tổng thời gian caller sẵn sàng chờ.
- **Send budget:** phần thời gian dành cho việc gửi request.
- **Processing budget:** phần thời gian dành cho các bước xử lý.
- **Reply budget:** phần thời gian còn lại để nhận kết quả.
- **Cleanup budget:** thời gian dành cho ghi nhận timeout và giải phóng tài nguyên.

Ví dụ, caller chờ tối đa 3 giây. Có thể dành 300 ms cho gửi, khoảng 2 giây cho xử lý và phần còn lại cho phản hồi cùng overhead. Các con số chỉ là minh họa; cần đo p95/p99 latency và đặc tính hệ thống để chọn giá trị phù hợp.

Không nên cộng timeout một cách máy móc nếu các bước chạy song song. Cần tính theo deadline thực tế của toàn luồng. Với hệ thống nhiều service, có thể truyền deadline hoặc remaining budget qua metadata đã được xác thực và chuẩn hóa. Khi đo thời gian trong một tiến trình, dùng đồng hồ monotonic cho khoảng thời gian để tránh ảnh hưởng của việc đồng hồ hệ thống thay đổi.

## 10. Timeout, retry và idempotency

Timeout tạo ra trạng thái không chắc chắn: caller chưa biết xử lý ở phía nhận đã hoàn tất hay chưa. Retry trong tình huống đó có thể tạo message trùng.

Ví dụ:

- Lệnh tạo đơn được xử lý thành công.
- Reply bị chậm hơn timeout.
- Client tưởng thao tác thất bại và gửi lại.
- Server tạo đơn lần thứ hai nếu không có cơ chế chống trùng.

Để tránh tình huống này:

- Dùng idempotency key ổn định cho cùng một thao tác logic.
- Lưu trạng thái xử lý hoặc kết quả theo request ID.
- Khi nhận command trùng, trả lại trạng thái/kết quả đã biết thay vì thực hiện lại tác dụng phụ.
- Dùng retry có backoff và giới hạn tổng số lần thử.
- Phân biệt lỗi chắc chắn chưa gửi được với trạng thái không rõ kết quả.
- Thiết kế đối soát cho các thao tác không thể bảo đảm exactly-once ở toàn bộ hệ thống.

Không retry vô hạn và không sinh idempotency key mới cho mỗi lần thử của cùng một thao tác. Nếu key thay đổi mỗi lần, server không thể nhận diện các lần gửi đó là cùng một yêu cầu.

## 11. Phân biệt timeout với các giới hạn thời gian khác

Không gộp các loại thời gian sau thành một thiết lập duy nhất:

| Thiết lập | Ý nghĩa |
|---|---|
| Connection timeout | Thời gian thiết lập kết nối tới broker hoặc dịch vụ |
| Send timeout | Thời gian chờ channel chấp nhận message |
| Receive timeout | Thời gian chờ message trên pollable channel |
| Request-reply timeout | Thời gian caller chờ reply |
| Processing timeout | Giới hạn thời gian thực thi một bước nghiệp vụ |
| Transaction timeout | Giới hạn thời gian transaction được phép tồn tại |
| Message TTL / expiration | Thời gian message còn hiệu lực trong broker hỗ trợ |
| Heartbeat timeout | Phát hiện kết nối hoặc peer không còn hoạt động |

Một message hết TTL ở broker có thể bị loại bỏ trước khi consumer nhận, nhưng điều đó khác với caller timeout khi chờ reply. Heartbeat cũng không thay thế timeout nghiệp vụ. Mỗi lớp cần được cấu hình theo trách nhiệm của nó.

## 12. Quan sát và kiểm thử timeout

### 12.1 Dữ liệu cần quan sát

Nên ghi nhận:

- Correlation ID hoặc request ID.
- Channel hoặc destination liên quan.
- Thời gian gửi, nhận và xử lý.
- Send timeout, receive timeout hoặc reply timeout đã áp dụng.
- Số lần retry và trạng thái idempotency.
- Số lượng request đang chờ và request đã hết hạn.
- Số lượng reply đến muộn.
- Exception và trạng thái broker/consumer phù hợp.

Không log payload hoặc headers nhạy cảm một cách mặc định. Dùng metric tổng hợp để quan sát timeout rate, latency p95/p99 và queue depth.

### 12.2 Các trường hợp kiểm thử

- Channel nhận message ngay trong send budget.
- Queue đầy khiến send phải chờ hoặc không được chấp nhận.
- Pollable channel trống cho tới khi receive timeout.
- Reply đến trước request-reply timeout.
- Không có reply và caller nhận trạng thái timeout phù hợp.
- Consumer tiếp tục xử lý sau khi caller đã timeout.
- Reply đến muộn được xử lý theo chính sách đã thiết kế.
- Retry cùng idempotency key không tạo tác dụng phụ trùng.
- Shutdown trong khi consumer đang chờ hoặc đang xử lý.
- Exception khác timeout không bị phân loại nhầm.

Với test bất đồng bộ, dùng latch, future hoặc cơ chế đồng bộ có kiểm soát thay vì sleep tùy ý. Với broker thật, integration test cần xác minh semantics của adapter và broker, vì test một channel trong bộ nhớ không chứng minh được timeout mạng hoặc broker.

## 13. Các lỗi thường gặp

- **Coi send timeout là processing timeout:** handler có thể tiếp tục chạy sau khi thao tác send kết thúc.
- **Coi receive timeout là timeout của nghiệp vụ:** receive chỉ giới hạn việc chờ message.
- **Nghĩ caller timeout sẽ hủy request:** message đã gửi có thể vẫn được consumer xử lý.
- **Retry ngay sau timeout:** thao tác đầu có thể đã thành công và gây tác dụng phụ trùng.
- **Không xử lý reply null:** code có thể lỗi khi không có phản hồi trong thời gian chờ.
- **Gộp exception thành timeout:** che khuất lỗi gửi, lỗi handler hoặc lỗi kết nối.
- **Dùng temporary reply channel cho kết quả dài hạn:** reply đến muộn không có nơi lưu trữ để caller truy vấn lại.
- **Đặt timeout vô hạn:** thread hoặc tài nguyên có thể bị giữ không giới hạn.
- **Dùng timeout quá ngắn:** tạo retry và tải bổ sung dù hệ thống vẫn hoạt động bình thường.
- **Đặt timeout độc lập ở từng service:** tổng thời gian vượt deadline của caller.
- **Không có correlation ID:** khó xác định reply thuộc request nào khi có timeout và retry.
- **Dùng idempotency key mới ở mỗi lần retry:** không chống được xử lý lặp.

## 14. Checklist thiết kế

Trước khi triển khai gửi, nhận và request-reply, hãy kiểm tra:

- Đang giới hạn thời gian chờ gửi, nhận hay chờ reply?
- Channel là synchronous, executor-based hay pollable?
- Send trả về false hoặc ném exception được xử lý ra sao?
- Receive timeout có xử lý trường hợp không có message không?
- Request-reply có xử lý reply null và exception riêng biệt không?
- Caller timeout có thể để consumer tiếp tục chạy không?
- Reply muộn được lưu, phát event, bỏ qua hay ghi nhận theo chính sách nào?
- Correlation ID và idempotency key có ổn định qua retry không?
- Timeout từng bước có nằm trong ngân sách end-to-end không?
- Có metric cho timeout, latency, retry và late reply không?
- Integration test đã xác minh semantics của channel hoặc broker thật chưa?

Khi hiểu rõ mỗi timeout đang bảo vệ giai đoạn nào và phản hồi muộn được xử lý ra sao, bạn có thể giới hạn thời gian chờ mà vẫn giữ được tính đúng đắn của nghiệp vụ trong hệ thống messaging.