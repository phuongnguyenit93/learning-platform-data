# ChannelInterceptor và các điểm chặn gửi hoặc nhận trong Spring Messaging

## 1. Vai trò của ChannelInterceptor

Trong Spring Messaging, message đi qua một `MessageChannel` trước khi tới handler hoặc consumer. Channel là ranh giới thích hợp để áp dụng những hành vi dùng chung mà không phải lặp lại trong từng handler.

`ChannelInterceptor` là strategy interface cho phép quan sát hoặc biến đổi message tại các điểm gửi và nhận. Interceptor thường được dùng cho:

- Ghi log metadata phục vụ truy vết.
- Bổ sung correlation ID hoặc header kỹ thuật.
- Đo thời gian và đếm số message.
- Kiểm tra điều kiện trước khi cho phép gửi hoặc nhận.
- Biến đổi message theo quy tắc hạ tầng.
- Dọn dẹp tài nguyên sau khi thao tác hoàn tất, kể cả khi có exception.

Interceptor phù hợp với concern xuyên suốt của messaging. Quy tắc nghiệp vụ như tính giá, quyết định trạng thái đơn hàng hoặc cập nhật dữ liệu domain nên nằm trong service hoặc handler chuyên trách.

Sau bài học, bạn cần có thể:

- Giải thích vòng đời callback send và receive.
- Phân biệt ChannelInterceptor với handler và ExecutorChannelInterceptor.
- Đăng ký interceptor vào channel hỗ trợ interception.
- Biến đổi hoặc chặn message ở đúng thời điểm.
- Hiểu rằng receive interception chỉ áp dụng cho PollableChannel.
- Quản lý exception, thứ tự callback, concurrency và dữ liệu nhạy cảm.

## 2. ChannelInterceptor và các callback

Interface `org.springframework.messaging.support.ChannelInterceptor` cung cấp sáu callback:

~~~java
public interface ChannelInterceptor {

    Message<?> preSend(Message<?> message, MessageChannel channel);

    void postSend(
            Message<?> message,
            MessageChannel channel,
            boolean sent);

    void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex);

    boolean preReceive(MessageChannel channel);

    Message<?> postReceive(
            Message<?> message,
            MessageChannel channel);

    void afterReceiveCompletion(
            Message<?> message,
            MessageChannel channel,
            Exception ex);
}
~~~

Trong Spring Framework hiện đại, các callback này có default implementation. Callback không được override thường là no-op; callback trả về Message mặc định trả lại message đầu vào, còn preReceive mặc định cho phép thao tác receive tiếp tục.

Không phải mọi thao tác đều chạy cả sáu callback. Send và receive có vòng đời riêng. Receive chỉ liên quan tới channel hỗ trợ polling.

## 3. Vòng đời gửi message

### 3.1 preSend: trước khi gửi

`preSend(message, channel)` được gọi trước khi channel thực hiện thao tác gửi. Đây là điểm để kiểm tra hoặc biến đổi message trước khi dispatch.

Callback có thể:

- Trả lại message gốc nếu không cần thay đổi.
- Trả một message mới đã được bổ sung hoặc biến đổi header/payload.
- Trả về `null` để chặn thao tác gửi tiếp tục.

Ví dụ, interceptor bổ sung correlation ID nếu message chưa có:

~~~java
import java.util.UUID;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageBuilder;

public class CorrelationIdInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        return MessageBuilder.fromMessage(message)
                .setHeaderIfAbsent(
                        "app.correlationId",
                        UUID.randomUUID().toString())
                .build();
    }
}
~~~

`setHeaderIfAbsent` giữ correlation ID đã được tầng trước cung cấp. Nếu chưa có, interceptor tạo ID mới. Cách này tránh ghi đè định danh đã được tạo ở gateway hoặc upstream service.

Nếu muốn chặn message, có thể trả `null` sau khi ghi nhận lý do. Việc chặn cần được quan sát rõ ràng; nếu không, producer có thể chỉ thấy send không tiếp tục mà không biết nguyên nhân.

### 3.2 postSend: ngay sau thao tác send

`postSend(message, channel, sent)` được gọi sau khi channel thực hiện thao tác gửi. Tham số `sent` phản ánh kết quả boolean của thao tác send.

Có thể dùng callback này để:

- Đếm số lần gửi được chấp nhận hoặc bị từ chối.
- Ghi nhận channel nào đang có vấn đề.
- Cập nhật metric theo kết quả gửi.

`sent == true` không chứng minh handler đã hoàn tất nghiệp vụ hoặc dữ liệu đã được commit vào database. Nó chỉ phản ánh kết quả của lời gọi send theo semantics của channel.

Nếu channel dispatch đồng bộ, handler có thể đã được gọi trước khi send trả về. Nếu channel dispatch bất đồng bộ, handler có thể còn chưa chạy. Vì vậy, postSend không phải callback xác nhận xử lý nghiệp vụ.

### 3.3 afterSendCompletion: cleanup sau khi gửi

`afterSendCompletion(message, channel, sent, ex)` được gọi sau khi thao tác send hoàn tất, kể cả khi có exception, nhằm hỗ trợ cleanup.

Đây là nơi phù hợp để:

- Kết thúc timer hoặc span cục bộ.
- Giải phóng tài nguyên được tạo trong preSend.
- Ghi nhận exception của thao tác gửi.
- Xóa trạng thái tạm được lưu theo phạm vi thực thi.

Callback này chỉ được gọi khi preSend hoàn tất thành công và trả về một Message. Nếu preSend trả về null, channel đã chặn send và afterSendCompletion không được gọi cho interceptor đó theo hợp đồng callback.

Khi có nhiều interceptor, afterSendCompletion được gọi theo thứ tự ngược lại với thứ tự preSend. Điều này hữu ích khi interceptor lồng nhau có tài nguyên cần được dọn theo kiểu stack.

## 4. Vòng đời nhận message

### 4.1 Chỉ áp dụng cho PollableChannel

Các callback receive là:

- `preReceive(channel)`
- `postReceive(message, channel)`
- `afterReceiveCompletion(message, channel, ex)`

Chúng chỉ áp dụng cho `PollableChannel`, nơi consumer chủ động gọi `receive()`. `SubscribableChannel` không định nghĩa receive; message được gửi tới subscriber theo semantics của channel.

Ví dụ, `QueueChannel` của Spring Integration là pollable channel. Khi consumer gọi receive, interceptor có thể kiểm soát hoặc quan sát thao tác lấy message khỏi queue.

### 4.2 preReceive: trước khi lấy message

`preReceive(channel)` chạy khi receive được gọi, trước khi message được lấy khỏi channel.

- Trả `true` để tiếp tục nhận.
- Trả `false` để ngăn thao tác receive tiếp tục.

Có thể dùng nó để chặn polling theo trạng thái vận hành hoặc áp dụng một điều kiện hạ tầng. Nếu chặn receive, hãy ghi metric hoặc log có kiểm soát để phân biệt với trường hợp queue đơn giản là không có message.

### 4.3 postReceive: sau khi lấy message

`postReceive(message, channel)` được gọi sau khi channel lấy được message và trước khi trả message cho caller.

Interceptor có thể trả lại message gốc hoặc một message mới đã được biến đổi. Trả về `null` sẽ ngăn message tiếp tục qua chuỗi interceptor và không chuyển message đó cho caller như một kết quả nhận bình thường.

Từ Spring Integration 5.1, postReceive không còn được gọi khi không nhận được message. Nếu cần cleanup hoặc ghi nhận kết quả receive bất kể có message hay không, hãy dùng afterReceiveCompletion.

### 4.4 afterReceiveCompletion: cleanup

`afterReceiveCompletion(message, channel, ex)` được gọi sau khi receive hoàn tất, kể cả khi có exception. Callback này phù hợp để giải phóng tài nguyên hoặc kết thúc trạng thái tạm đã tạo trong preReceive.

Nó chỉ được gọi nếu preReceive của interceptor hoàn tất thành công và trả về true. Khi nhiều interceptor được đăng ký, completion callback chạy theo thứ tự ngược lại với preReceive.

## 5. Đăng ký interceptor vào channel

Không phải mọi biến có kiểu `MessageChannel` đều cung cấp phương thức addInterceptor. Việc đăng ký yêu cầu channel implementation hỗ trợ `InterceptableChannel`.

Ví dụ với `ExecutorSubscribableChannel` thuộc Spring Messaging:

~~~java
import org.springframework.messaging.support.ExecutorSubscribableChannel;

public class ChannelSetup {

    public ExecutorSubscribableChannel createChannel() {
        ExecutorSubscribableChannel channel =
                new ExecutorSubscribableChannel();

        channel.addInterceptor(new CorrelationIdInterceptor());
        return channel;
    }
}
~~~

Channel này phù hợp minh họa send interception. Nó là subscribable channel nên không có thao tác receive để kích hoạt các callback preReceive, postReceive và afterReceiveCompletion.

Để minh họa receive interception, dùng pollable channel, ví dụ `QueueChannel` của Spring Integration:

~~~java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.support.ChannelInterceptor;

public class PollableChannelSetup {

    public QueueChannel createChannel(ChannelInterceptor interceptor) {
        QueueChannel channel = new QueueChannel();
        channel.addInterceptor(interceptor);
        return channel;
    }
}
~~~

Ví dụ QueueChannel cần dependency Spring Integration Core. Trong dự án thực tế, ưu tiên khai báo channel thành bean để application context quản lý lifecycle và cấu hình.

Có thể đăng ký nhiều interceptor. Hãy xác định thứ tự đăng ký có ý nghĩa hay không, đặc biệt khi interceptor trước biến đổi message mà interceptor sau đọc metadata đó.

## 6. Ví dụ interceptor cho send và receive

Một interceptor có thể chỉ override các callback cần thiết:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;

public class AuditChannelInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        System.out.println("preSend: " + channel);
        return message;
    }

    @Override
    public void postSend(
            Message<?> message,
            MessageChannel channel,
            boolean sent) {

        System.out.println("postSend accepted: " + sent);
    }

    @Override
    public void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex) {

        if (ex != null) {
            System.err.println("send failed: " + ex.getClass().getSimpleName());
        }
    }

    @Override
    public boolean preReceive(MessageChannel channel) {
        System.out.println("preReceive: " + channel);
        return true;
    }

    @Override
    public Message<?> postReceive(
            Message<?> message,
            MessageChannel channel) {

        System.out.println("postReceive: " + channel);
        return message;
    }

    @Override
    public void afterReceiveCompletion(
            Message<?> message,
            MessageChannel channel,
            Exception ex) {

        if (ex != null) {
            System.err.println("receive failed: " + ex.getClass().getSimpleName());
        }
    }
}
~~~

Có thể đăng ký cùng một interceptor vào các channel phù hợp, nhưng callback receive chỉ chạy trên pollable channel. Với subscribable channel, chỉ vòng đời send được áp dụng.

Ví dụ chỉ minh họa điểm đặt callback. Trong ứng dụng thật, hãy dùng logger và metrics thay cho System.out/System.err; tránh ghi payload hoặc headers nhạy cảm vào log.

## 7. Thứ tự gọi callback

### 7.1 Thứ tự trong một thao tác send

Với các interceptor đã được gọi thành công:

1. preSend chạy theo thứ tự đăng ký.
2. Channel thực hiện send.
3. postSend chạy sau thao tác send.
4. afterSendCompletion chạy để cleanup theo thứ tự ngược lại.

Nếu preSend trả null, thao tác send bị ngăn. Những interceptor chưa được gọi không có completion callback tương ứng; interceptor đã tham gia chuỗi được xử lý theo stack cleanup của channel.

### 7.2 Thứ tự trong một thao tác receive

Với pollable channel:

1. preReceive chạy theo thứ tự đăng ký.
2. Channel thực hiện receive nếu tất cả interceptor cho phép.
3. postReceive chạy sau khi message được lấy.
4. afterReceiveCompletion chạy để cleanup theo thứ tự ngược lại.

Nếu preReceive trả false, việc nhận bị chặn. Nếu postReceive trả null, message không tiếp tục tới caller theo luồng nhận bình thường.

### 7.3 Không giả định thứ tự send và receive giữa hai thread

Khi sender và receiver chạy ở các thread khác nhau, thứ tự callback send và receive có thể đan xen. Receiver có thể đang chờ trước khi sender gửi, hoặc chỉ bắt đầu polling sau khi sender đã hoàn tất.

Vì vậy, chỉ dựa vào thứ tự trong từng thao tác riêng: preSend trước postSend, và preReceive trước postReceive. Không dùng thứ tự tổng thể giữa sender và receiver làm điều kiện đúng đắn của nghiệp vụ.

## 8. Dùng interceptor cho logging, metrics và tracing

Các concern xuyên suốt phù hợp với interceptor gồm:

- Đếm số lần gửi được chấp nhận và bị từ chối.
- Đo thời gian trong phạm vi lời gọi channel.
- Gắn hoặc kiểm tra correlation ID.
- Ghi nhận channel name và message type.
- Tạo trace context hoặc chuyển tiếp metadata quan sát được theo quy ước của ứng dụng.

Nếu dùng bộ đếm trong interceptor có thể được nhiều thread gọi đồng thời, hãy dùng cấu trúc thread-safe như `LongAdder` hoặc `AtomicLong`. Không dùng biến số nguyên thông thường rồi cập nhật đồng thời mà không có đồng bộ.

Cũng cần phân biệt thời gian send với thời gian xử lý nghiệp vụ. Với asynchronous channel, send có thể kết thúc trước khi handler hoàn thành. Muốn đo processing latency, cần instrument ở handler hoặc tầng thực thi tương ứng.

## 9. Chặn và biến đổi message có chủ đích

### 9.1 Chặn send bằng preSend

Có thể trả null khi message không thỏa điều kiện hạ tầng:

~~~java
@Override
public Message<?> preSend(
        Message<?> message,
        MessageChannel channel) {

    if (message.getPayload() == null) {
        return null;
    }

    return message;
}
~~~

Trong thực tế, MessageBuilder thường không tạo message có payload null theo cách thông thường, nên ví dụ chỉ minh họa cơ chế chặn. Điều kiện chặn cần phản ánh một quy tắc rõ ràng và được ghi nhận. Nếu lỗi đầu vào cần phản hồi cho caller, có thể ném exception phù hợp thay vì âm thầm trả null.

### 9.2 Biến đổi message

Có thể trả message mới để bổ sung metadata kỹ thuật:

~~~java
@Override
public Message<?> preSend(
        Message<?> message,
        MessageChannel channel) {

    return MessageBuilder.fromMessage(message)
            .setHeaderIfAbsent("app.channelName", channel.toString())
            .build();
}
~~~

Không sửa trực tiếp headers của message đã tạo. Tạo message mới giúp các thành phần phía sau nhận một message đã được hoàn thiện.

### 9.3 Chặn receive bằng preReceive

Một pollable channel có thể bị ngăn nhận trong một trạng thái vận hành nhất định:

~~~java
@Override
public boolean preReceive(MessageChannel channel) {
    return consumerEnabled;
}
~~~

Nếu dùng trạng thái như `consumerEnabled`, interceptor được gọi đồng thời phải đọc trạng thái thread-safe hoặc bất biến. Việc bật/tắt consumer nên có cơ chế điều phối rõ ràng để tránh trạng thái thay đổi giữa các lần polling.

## 10. Phân biệt ChannelInterceptor và ExecutorChannelInterceptor

`ChannelInterceptor` bao quanh thao tác gửi hoặc nhận ở cấp channel.

`ExecutorChannelInterceptor` là extension dành cho channel thực thi handler thông qua executor. Nó cung cấp thêm callback quanh việc một handler cụ thể được gọi, ví dụ trước và sau khi xử lý message.

Hãy chọn theo phạm vi cần quan sát:

- Cần biết message được gửi vào channel, bị chặn hay nhận từ pollable channel: ChannelInterceptor.
- Cần biết từng handler bắt đầu và hoàn tất xử lý trên executor: ExecutorChannelInterceptor hoặc instrumentation ở handler.
- Cần theo dõi nghiệp vụ qua nhiều service: tracing/observability ở tầng ứng dụng và messaging phù hợp.

Không dùng ChannelInterceptor để giả định rằng mọi handler đã xử lý xong. Đặc biệt với executor channel, thời điểm send completion khác với thời điểm handler completion.

## 11. Wire Tap và quan sát luồng message

Spring Integration cung cấp Wire Tap pattern để gửi bản sao message sang một channel khác phục vụ monitoring, logging hoặc debugging mà không thay đổi luồng xử lý chính.

Wire Tap phù hợp khi cần quan sát sự kiện mà không muốn viết logic sao chép vào mọi handler. Tuy nhiên, channel tap vẫn cần được cấu hình tải và bảo mật phù hợp. Nếu kênh quan sát chậm hoặc đầy, hãy xác định rõ tác động lên luồng chính theo cấu hình thực tế.

Không gửi toàn bộ payload nhạy cảm sang kênh audit. Có thể chỉ trích xuất metadata cần thiết, che dữ liệu nhạy cảm hoặc dùng sampling cho luồng có lưu lượng cao.

## 12. Lỗi thường gặp

- **Cài receive interceptor lên SubscribableChannel:** interface này không có receive; callback receive không được gọi.
- **Nghĩ preSend chỉ để logging:** nó có thể thay đổi message hoặc chặn send bằng cách trả null.
- **Nghĩ postSend là xác nhận nghiệp vụ:** sent chỉ là kết quả của thao tác send theo semantics channel.
- **Bỏ qua afterSendCompletion:** tài nguyên tạm có thể không được cleanup khi có exception.
- **Trả null ngoài ý muốn:** message bị chặn hoặc dừng ở chuỗi interceptor.
- **Không xử lý exception của interceptor:** lỗi cross-cutting có thể làm send/receive thất bại.
- **Giả định thứ tự send/receive giữa thread:** callback của hai phía có thể đan xen tùy timing.
- **Dùng interceptor chứa nghiệp vụ:** tạo coupling và khiến flow khó kiểm thử.
- **Chia sẻ mutable state không thread-safe:** interceptor có thể được gọi đồng thời bởi nhiều message.
- **Ghi log toàn bộ payload:** có thể làm lộ dữ liệu cá nhân, token hoặc thông tin nhạy cảm.
- **Đo processing latency ở postSend:** không chính xác với dispatch bất đồng bộ.
- **Dùng interceptor như cơ chế bảo đảm giao nhận:** interceptor không thay thế broker acknowledgement, transaction hoặc retry policy.

## 13. Checklist triển khai

Trước khi đăng ký ChannelInterceptor, hãy kiểm tra:

- Channel implementation có hỗ trợ InterceptableChannel không?
- Cần can thiệp send, receive hay cả hai?
- Channel có phải PollableChannel nếu cần callback receive không?
- preSend có thể trả null trong trường hợp nào và lý do có được quan sát không?
- postSend có được hiểu đúng là kết quả gửi, không phải xử lý nghiệp vụ?
- afterSendCompletion và afterReceiveCompletion có cleanup tài nguyên đúng cách không?
- Thứ tự interceptor có được xác định và kiểm thử khi có phụ thuộc không?
- Interceptor có an toàn khi được gọi đồng thời không?
- Có tránh log payload và headers nhạy cảm không?
- Cần đo send latency hay handler processing latency?
- Có integration test cho channel implementation thật đang dùng không?

Khi đặt interceptor đúng ranh giới, bạn có thể bổ sung logging, metrics, tracing, kiểm tra và biến đổi message một cách nhất quán mà không làm mỗi handler phải tự triển khai cùng một concern.