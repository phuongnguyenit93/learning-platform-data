# AbstractMessageChannel và điểm mở rộng của kênh

## 1. Vai trò của AbstractMessageChannel

`MessageChannel` là abstraction mà producer dùng để gửi `Message<?>`. Producer chỉ cần biết channel, không cần biết message sẽ được chuyển tới handler nào, được đưa vào hàng đợi hay được gửi qua một adapter. Cách nhận và phân phối message do implementation của channel quyết định.

`org.springframework.messaging.support.AbstractMessageChannel` là lớp cơ sở trong Spring Framework dành cho các implementation của `MessageChannel`. Lớp này cung cấp phần xử lý chung của thao tác gửi, quản lý danh sách `ChannelInterceptor`, hỗ trợ tên bean và logger. Lớp con tập trung hiện thực cơ chế giao message thông qua extension point `sendInternal(...)`.

Điểm cần nhớ: `AbstractMessageChannel` là một phần của **Spring Framework Messaging**. Nó không phải broker, không tự lưu message bền vững, không tự tạo consumer và cũng không mặc định làm cho thao tác gửi trở thành bất đồng bộ.

## 2. API và hợp đồng gửi message

API `MessageChannel` có hai dạng gửi:

~~~java
boolean send(Message<?> message);
boolean send(Message<?> message, long timeout);
~~~

- `send(message)` dùng timeout vô hạn theo hợp đồng của `MessageChannel` (`INDEFINITE_TIMEOUT`).
- `send(message, timeout)` nhận thời gian chờ tính bằng millisecond; giá trị âm đặc biệt `MessageChannel.INDEFINITE_TIMEOUT` biểu thị chờ vô hạn, còn `0` yêu cầu không chờ khi channel chưa thể nhận message.
- `true` nghĩa là channel chấp nhận/gửi message thành công theo ngữ nghĩa của implementation.
- `false` có thể biểu thị timeout hoặc bị ngắt khi đang chờ.
- Lỗi không thể phục hồi có thể được ném dưới dạng runtime exception.

Đừng diễn giải `true` thành “consumer đã hoàn thành nghiệp vụ”. Với channel đồng bộ, handler có thể đã chạy xong trước khi `send()` trả về. Với channel bất đồng bộ hoặc channel đệm, `true` thường chỉ cho biết message đã được chấp nhận theo cơ chế của channel.

## 3. Luồng xử lý trong AbstractMessageChannel

`send()` của `AbstractMessageChannel` là `final`, vì vậy lớp con không override để thay toàn bộ pipeline. Lớp cơ sở điều phối việc gửi và gọi extension point `sendInternal(message, timeout)` để lớp con thực hiện hành vi cụ thể.

Luồng khái quát:

~~~text
Producer
   |
   v
AbstractMessageChannel.send(message, timeout)
   |
   v
ChannelInterceptor.preSend(...)
   |
   +---- trả null ----> hủy lần gửi, send() trả false
   |
   v
sendInternal(message, timeout)  <-- lớp con hiện thực
   |
   v
ChannelInterceptor.postSend(message, channel, sent)
   |
   v
ChannelInterceptor.afterSendCompletion(...)
   |
   v
Kết quả send()
~~~

Đây là sơ đồ khái niệm của đường gửi. Các callback completion được gọi để hoàn tất xử lý interceptor sau khi send kết thúc; nếu một interceptor từ chối message ở `preSend`, `sendInternal` không được gọi.

### 3.1. sendInternal là extension point chính

Chữ ký trong Spring Framework 6.2:

~~~java
protected abstract boolean sendInternal(Message<?> message, long timeout);
~~~

Lớp con phải quyết định:

1. Message được chuyển tới đâu: handler, cấu trúc đệm, transport hoặc thành phần nhận khác.
2. Việc gửi có đồng bộ hay bất đồng bộ.
3. Khi nào message được xem là đã được chấp nhận.
4. Timeout và dung lượng được xử lý thế nào.
5. Hành vi khi bị interrupt, đầy hàng đợi hoặc lỗi transport.
6. Exception nào cần truyền lên để caller biết lần gửi thất bại.

`sendInternal` nhận message đã qua bước interceptor `preSend` và timeout do caller cung cấp. Nó trả `true`/`false` theo kết quả chấp nhận message. Với channel có capacity hữu hạn, lớp con phải thực hiện đúng semantics chờ/timeout. Với channel chuyển trực tiếp tới handler trong cùng thread, không có hàng đợi để chờ capacity nên timeout có thể không được dùng để giới hạn thời gian chạy handler.

### 3.2. Vì sao send() là final?

Lớp cơ sở cần kiểm soát một điểm vào thống nhất để áp dụng interceptor, xử lý kết quả gửi và hoàn tất callback. Nếu mỗi lớp con tự override `send()`, các channel có thể thực hiện logging, interceptor và xử lý lỗi khác nhau hoặc bỏ qua chúng.

Khi cần thay đổi cơ chế vận chuyển, hãy hiện thực `sendInternal`. Khi cần thêm hành vi chung quanh thao tác gửi, cân nhắc `ChannelInterceptor`.

## 4. ChannelInterceptor: mở rộng hành vi mà không tạo channel mới

`ChannelInterceptor` cho phép quan sát hoặc điều chỉnh message tại ranh giới channel. Đây là lựa chọn phù hợp cho các hành vi dùng chung như logging, kiểm tra metadata, đo thời gian, kiểm soát message hoặc bổ sung header.

Các callback liên quan tới gửi:

| Callback | Thời điểm | Vai trò |
| --- | --- | --- |
| `preSend(message, channel)` | Trước `sendInternal` | Kiểm tra hoặc trả về message đã chỉnh sửa; trả `null` để ngăn gửi |
| `postSend(message, channel, sent)` | Sau khi thao tác gửi trả kết quả | Quan sát message và kết quả boolean |
| `afterSendCompletion(message, channel, sent, ex)` | Khi lần gửi hoàn tất | Dọn tài nguyên hoặc hoàn tất context kể cả khi có exception |

Với channel hỗ trợ polling, interceptor còn có các callback nhận:

- `preReceive(channel)`: trả `false` để không thực hiện lần nhận.
- `postReceive(message, channel)`: xem hoặc thay đổi message sau khi lấy khỏi channel; trả `null` để dừng chuỗi interceptor.
- `afterReceiveCompletion(message, channel, ex)`: hoàn tất xử lý receive kể cả khi có lỗi.

Các callback receive chỉ có ý nghĩa với implementation hỗ trợ `PollableChannel`; `AbstractMessageChannel` tự nó chỉ định nghĩa hợp đồng gửi của `MessageChannel`. Lớp con hoặc lớp cơ sở chuyên biệt cho pollable channel phải thực hiện đúng quy trình receive và interceptor tương ứng.

### 4.1. Thứ tự interceptor

Các interceptor được áp dụng theo thứ tự đăng ký trong giai đoạn trước thao tác. Các callback hoàn tất được gọi theo thứ tự ngược để phù hợp với mô hình vào-ra lồng nhau, giúp interceptor cuối cùng được mở trước sẽ được đóng sau cùng. Không nên dựa vào thứ tự thời gian của `preSend` và `postSend` để suy luận thời điểm consumer hoàn tất nếu channel đệm hoặc bất đồng bộ.

### 4.2. Ví dụ interceptor từ chối message

~~~java
ChannelInterceptor validationInterceptor = new ChannelInterceptor() {
    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        Object type = message.getHeaders().get("eventType");
        if (type == null) {
            return null;
        }
        return message;
    }
};

channel.addInterceptor(validationInterceptor);
~~~

Nếu header `eventType` không có, interceptor trả `null`; lần gửi bị ngăn trước khi `sendInternal` chạy và `send()` trả `false`. Đây là cách từ chối ở ranh giới channel. Với validation nghiệp vụ phức tạp, nên đặt logic trong component chuyên trách thay vì nhồi toàn bộ quy tắc domain vào interceptor.

Không dùng interceptor để âm thầm sửa dữ liệu nghiệp vụ quan trọng hoặc nuốt exception. Nếu thay đổi message, hãy tạo message mới qua `MessageBuilder` và ghi rõ quy tắc chuyển đổi.

## 5. Các lớp cơ sở và implementation liên quan

`AbstractMessageChannel` chỉ giải quyết phần chung của `MessageChannel`. Tùy cách channel phân phối message, có thể dùng lớp cơ sở chuyên biệt hơn.

### 5.1. AbstractSubscribableChannel

`AbstractSubscribableChannel` cũng thuộc `org.springframework.messaging.support`. Nó mở rộng `AbstractMessageChannel` và cung cấp nền tảng quản lý subscriber cho implementation của `SubscribableChannel`.

`SubscribableChannel` cho phép đăng ký và hủy đăng ký `MessageHandler`. Khi gửi, channel dispatch message tới handler đã đăng ký theo chiến lược của implementation. Lớp cơ sở này hữu ích khi custom channel cần registry subscriber thay vì một handler cố định.

### 5.2. ExecutorSubscribableChannel

`ExecutorSubscribableChannel` là implementation trong Spring Framework dựa trên `AbstractSubscribableChannel`. Nó sử dụng `Executor` để thực thi việc dispatch tới handler. Vì vậy caller có thể quay lại trước khi handler hoàn thành, tùy executor và cách dispatch.

Không nên nhầm executor dispatch với durable messaging. Một executor trong ứng dụng không tự lưu message qua restart, không cung cấp broker acknowledgement và không bảo đảm consumer chỉ nhận đúng một lần.

### 5.3. Phân biệt với Spring Integration

Trong Spring Integration có những channel implementation quen thuộc như `DirectChannel`, `QueueChannel` và `PublishSubscribeChannel`. Chúng nằm trong module Spring Integration, với các semantics và tính năng tích hợp riêng.

- `DirectChannel` thường dispatch trực tiếp tới một subscriber được chọn trong luồng gọi hiện tại.
- `QueueChannel` lưu message trong queue để consumer nhận bằng polling; loại queue và cấu hình quyết định capacity, timeout và persistence.
- `PublishSubscribeChannel` phát message tới nhiều subscriber theo chính sách dispatch của nó.

Đây là các khái niệm hữu ích để so sánh, nhưng không được nhầm chúng là các class cùng package hoặc cùng module với `AbstractMessageChannel` của Spring Framework. Khi dùng một channel cụ thể, hãy kiểm tra đúng artifact, package và phiên bản trong dependency.

## 6. Đồng bộ, bất đồng bộ và timeout

Channel đồng bộ thường gọi handler trong thread gửi. Điều này giúp luồng điều khiển đơn giản và exception từ handler có thể được phản ánh ngay trong lần gửi. Đổi lại, thời gian `send()` phụ thuộc thời gian xử lý handler.

Channel bất đồng bộ thường giao message cho executor hoặc cơ chế dispatch khác. Caller có thể nhận kết quả chấp nhận nhanh hơn, nhưng lỗi xử lý có thể xảy ra sau khi `send()` đã trả về. Khi đó cần error handling, logging và quan sát ở phía consumer.

Timeout của `send(message, timeout)` cần được hiểu theo khả năng nhận message của channel:

- Với channel có buffer hữu hạn, timeout giới hạn thời gian chờ để message được nhận vào buffer.
- Với channel không buffer và dispatch ngay, timeout không nhất thiết giới hạn thời gian chạy handler.
- Nếu executor bị nghẽn hoặc từ chối task, implementation cần định nghĩa rõ trả `false` hay ném exception.
- Timeout ở caller không tự hủy một handler đã bắt đầu chạy.

Không thêm một executor không giới hạn để “làm nhanh” channel. Cần đặt queue capacity, thread pool, rejection policy và quy tắc shutdown. Nếu producer nhanh hơn consumer trong thời gian dài, backlog sẽ tăng và cuối cùng gây áp lực bộ nhớ hoặc làm tăng latency.

## 7. Thiết kế một custom channel

Trước khi kế thừa `AbstractMessageChannel`, hãy xác định lý do cần implementation riêng. Các câu hỏi quan trọng:

1. Channel cần dispatch tới một handler, nhiều subscriber hay lưu message để polling?
2. Có cần buffer không? Nếu có, capacity bao nhiêu và khi đầy sẽ block, trả `false` hay từ chối?
3. Timeout tính bằng millisecond được xử lý thế nào? Giá trị âm và bằng zero có ý nghĩa gì?
4. Message được xử lý trên thread của producer hay executor riêng?
5. Ai sở hữu lifecycle của executor, socket, client hoặc connection?
6. Khi gửi thất bại, message có được retry không? Ai chịu trách nhiệm retry?
7. Có cần bảo toàn thứ tự không? Trong phạm vi toàn channel hay theo key?
8. Có cần hỗ trợ interceptor receive, metrics, tracing hoặc bean lifecycle không?
9. Hành vi khi shutdown là drain message, từ chối message mới hay bỏ message đang chờ?

Với channel dùng trong production, cần xem xét thread safety, memory visibility, giới hạn payload, observability, backpressure và failure semantics. Không nên xem `sendInternal` chỉ là nơi gọi một hàm `put()`; đó là ranh giới thực hiện hợp đồng gửi của channel.

## 8. Ví dụ hoàn chỉnh: custom channel dispatch đồng bộ

Ví dụ dưới đây tạo một channel tối giản kế thừa `AbstractMessageChannel`. Channel giữ một `MessageHandler` cố định và gọi handler trực tiếp trong `sendInternal`. Một interceptor ghi log trước và sau thao tác gửi.

Ví dụ này minh họa extension point và vòng đời interceptor; nó không có queue, không bất đồng bộ, không lưu bền vững và không mô phỏng broker.

Tạo Maven project:

~~~text
abstract-channel-demo/
  pom.xml
  src/main/java/com/example/messaging/AbstractChannelDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>abstract-channel-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.8</spring.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring.version}</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/com/example/messaging/AbstractChannelDemo.java`:

~~~java
package com.example.messaging;

import java.util.Objects;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.AbstractMessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageBuilder;

public final class AbstractChannelDemo {
    private AbstractChannelDemo() {
    }

    private static final class HandlerChannel extends AbstractMessageChannel {
        private final MessageHandler handler;

        private HandlerChannel(MessageHandler handler) {
            this.handler = Objects.requireNonNull(handler, "handler");
        }

        @Override
        protected boolean sendInternal(Message<?> message, long timeout) {
            handler.handleMessage(message);
            return true;
        }
    }

    public static void main(String[] args) {
        HandlerChannel channel = new HandlerChannel(
                message -> System.out.println("handled=" + message.getPayload()));

        channel.addInterceptor(new ChannelInterceptor() {
            @Override
            public Message<?> preSend(Message<?> message, MessageChannel channel) {
                System.out.println("preSend payload=" + message.getPayload());
                return message;
            }

            @Override
            public void postSend(Message<?> message, MessageChannel channel, boolean sent) {
                System.out.println("postSend sent=" + sent);
            }
        });

        Message<String> message = MessageBuilder
                .withPayload("order-42")
                .setHeader("eventType", "OrderPlaced")
                .build();

        boolean sent = channel.send(message);
        System.out.println("sendResult=" + sent);
    }
}
~~~

Biên dịch và chạy từ thư mục chứa `pom.xml` bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.AbstractChannelDemo
~~~

Stdout:

~~~text
preSend payload=order-42
handled=order-42
postSend sent=true
sendResult=true
~~~

Diễn giải:

1. `channel.send(message)` gọi phương thức `send()` final của `AbstractMessageChannel`.
2. `preSend` chạy trước khi channel thực hiện giao message.
3. `sendInternal` của `HandlerChannel` gọi `MessageHandler` trong cùng thread.
4. Handler in payload ra console; sau đó `sendInternal` trả `true`.
5. `postSend` nhận kết quả gửi và `send()` trả `true` cho caller.

Implementation cố ý không dùng tham số `timeout`, vì channel này không buffer và gọi handler trực tiếp. Nếu handler chặn lâu, caller cũng chờ lâu; timeout của `send()` không phải cơ chế tự ngắt handler. Một custom channel có capacity hoặc transport chờ nhận message phải tự triển khai semantics timeout phù hợp.

## 9. ExecutorChannelInterceptor và ranh giới xử lý handler

`ExecutorChannelInterceptor` mở rộng `ChannelInterceptor` cho các channel dispatch qua executor. Nó bổ sung callback như `beforeHandle(...)` và `afterMessageHandled(...)`, được gọi bên trong task của executor ngay trước/sau thao tác `MessageHandler.handleMessage(...)`.

Điểm khác biệt:

- `ChannelInterceptor.preSend/postSend` bao quanh thao tác gửi ở phía channel/caller.
- `ExecutorChannelInterceptor.beforeHandle/afterMessageHandled` bao quanh việc gọi handler trên thread thực thi.

Vì handler chạy ở thread khác, ThreadLocal hoặc context của caller không tự động có mặt ở consumer. Cần cơ chế truyền context phù hợp cho tracing, security hoặc tenant context. Cũng cần xác định exception của handler được chuyển đến đâu vì caller có thể đã nhận `send() = true` trước khi handler lỗi.

Không dùng `ExecutorChannelInterceptor` thay cho error handling của ứng dụng. Callback này giúp quan sát và quản lý vòng đời xử lý; nó không tự retry, lưu message hay phục hồi giao dịch.

## 10. Kiểm thử custom channel

Kiểm thử nên xác nhận hợp đồng quan sát được, không chỉ kiểm tra rằng phương thức `sendInternal` đã được gọi.

- **Gửi thành công:** message đến đúng handler, `send()` trả `true`.
- **Interceptor biến đổi message:** handler nhận đúng message sau `preSend`.
- **Interceptor từ chối:** `preSend` trả `null`, handler không chạy và `send()` trả `false`.
- **Handler ném exception:** xác nhận exception được phản ánh theo contract của channel và không bị nuốt.
- **Timeout:** với channel có capacity hữu hạn, gửi vào channel đầy với timeout zero phải trả ngay; timeout dương phải chờ không quá thời gian được quy định ở mức hợp lý.
- **Interrupt:** thread đang chờ phải dừng theo contract và giữ trạng thái interrupt nếu implementation xử lý `InterruptedException`.
- **Đồng thời:** nhiều producer/consumer không làm hỏng thứ tự hoặc cấu trúc nội bộ ngoài semantics đã công bố.
- **Shutdown:** không nhận thêm message khi đã đóng; các message đang chờ được xử lý theo chính sách drain hoặc discard đã định nghĩa.

Với channel đồng bộ như ví dụ trên, cần kiểm tra handler chạy trong thread gửi và thời gian handler ảnh hưởng thời gian `send()`. Với channel executor, kiểm tra việc dispatch, rejection và error handling ở thread consumer.

## 11. Lỗi thiết kế thường gặp

- **Override `send()` thay vì `sendInternal()`:** bỏ qua pipeline final và hành vi interceptor chung của lớp cơ sở.
- **Coi `send() == true` là xử lý nghiệp vụ đã hoàn tất:** với channel async, kết quả thường chỉ là message đã được chấp nhận.
- **Bỏ qua timeout:** channel có capacity hữu hạn có thể block vô hạn hoặc không tuân thủ hợp đồng gửi.
- **Dùng queue vô hạn:** backlog có thể tăng cho tới khi cạn bộ nhớ.
- **Tạo thread mới cho từng message:** khó giới hạn tài nguyên, khó shutdown và dễ quá tải.
- **Nuốt exception trong `sendInternal`:** caller không nhận biết được lỗi và observability mất thông tin.
- **Dùng interceptor cho nghiệp vụ phức tạp:** logic khó kiểm thử và có thể ảnh hưởng mọi message trên channel.
- **Cho rằng interceptor tự cung cấp retry hoặc durability:** interceptor chỉ quan sát/điều chỉnh thao tác; nó không thay broker hay storage.
- **Không phân biệt Spring Framework và Spring Integration:** nhầm package, artifact và semantics của channel implementation.
- **Dùng context ThreadLocal qua executor mà không truyền context:** log/tracing/security có thể mất hoặc dùng nhầm context.
- **Không định nghĩa hành vi khi shutdown:** message đang chờ có thể mất hoặc handler bị dừng giữa chừng.

## 12. Quy tắc chọn điểm mở rộng

| Nhu cầu | Điểm mở rộng phù hợp |
| --- | --- |
| Thay cách channel thực sự nhận/chuyển message | Kế thừa `AbstractMessageChannel`, hiện thực `sendInternal` |
| Cần registry và dispatch tới subscriber | Xem `AbstractSubscribableChannel` và `SubscribableChannel` |
| Cần dispatch subscriber qua executor | Xem `ExecutorSubscribableChannel` hoặc implementation phù hợp |
| Logging, metrics, kiểm tra hoặc điều chỉnh message quanh send | `ChannelInterceptor` |
| Hook chạy ngay quanh handler trên executor thread | `ExecutorChannelInterceptor` |
| Cần queue/polling với timeout và buffer | Dùng `PollableChannel`/implementation phù hợp; nếu custom, phải hiện thực cả send và receive semantics |
| Cần broker, persistence, ack, replay hoặc phân phối qua process | Dùng broker adapter/module phù hợp; `AbstractMessageChannel` tự nó không cung cấp các bảo đảm đó |

Ưu tiên implementation sẵn có khi semantics của nó đáp ứng yêu cầu. Custom channel chỉ nên xuất hiện khi có một cơ chế giao message đặc thù mà các implementation hiện có không đáp ứng được.

## 13. Checklist review

1. Lớp con có chỉ hiện thực `sendInternal` và giữ nguyên pipeline `send()` của lớp cơ sở không?
2. `sendInternal` có định nghĩa rõ lúc nào message được chấp nhận không?
3. Giá trị timeout âm, zero và dương có được xử lý đúng không?
4. Khi bị interrupt, implementation có trả kết quả phù hợp và giữ trạng thái interrupt không?
5. Interceptor có được chạy đúng thứ tự và callback completion có được gọi khi lỗi không?
6. Có phân biệt callback gửi và callback nhận của pollable channel không?
7. Handler chạy trên thread nào? Exception được xử lý ở đâu?
8. Capacity, concurrency, ordering và backpressure có giới hạn rõ ràng không?
9. Shutdown có quy tắc drain hoặc từ chối message mới không?
10. Có metrics/log/tracing đủ để phát hiện backlog, timeout, rejection và lỗi handler không?
11. Tên package và dependency có đúng module Spring Framework hay Spring Integration không?
12. Người dùng channel có hiểu `send() == true` đại diện cho việc được chấp nhận hay đã xử lý xong không?

## 14. Ghi nhớ

`AbstractMessageChannel` là lớp cơ sở cho channel trong Spring Framework. Hai phương thức `send()` là final để lớp cơ sở quản lý pipeline gửi và interceptor; lớp con định nghĩa hành vi giao message trong `sendInternal(message, timeout)`. `ChannelInterceptor` mở rộng thao tác gửi/nhận mà không cần viết channel mới; `AbstractSubscribableChannel` là nền tảng cho channel có subscriber, còn `ExecutorSubscribableChannel` hỗ trợ dispatch qua executor. Khi custom channel, phải công bố rõ semantics đồng bộ/bất đồng bộ, timeout, capacity, exception, thread, ordering và shutdown. Lớp cơ sở không tự cung cấp persistence, broker acknowledgement, retry hoặc replay.

### Tài liệu tham khảo

- [Spring Framework 6.2 — AbstractMessageChannel Javadoc](https://www.springframework.org/spring/docs/6.2.5/javadoc-api/org/springframework/messaging/support/AbstractMessageChannel.html).
- [Spring Framework 6.2 — AbstractSubscribableChannel Javadoc](https://www.springframework.org/spring/docs/6.2.5/javadoc-api/org/springframework/messaging/support/AbstractSubscribableChannel.html).
- [Spring Framework 6.2 — ChannelInterceptor Javadoc](https://www.springframework.org/spring/docs/6.2.18/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html).
- [Spring Framework 6.2 — PollableChannel Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0-M6/javadoc-api/org/springframework/messaging/PollableChannel.html).
- [Spring Integration 6.2 — Message Channels](https://docs.spring.io/spring-integration/docs/6.2.11/reference/html/channel.html).