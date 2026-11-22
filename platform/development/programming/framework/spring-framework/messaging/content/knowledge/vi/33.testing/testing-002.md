# Kiểm thử MessageHandler và điều kiện chặn của interceptor

## Mục tiêu

Trong Spring Messaging, MessageHandler nhận và xử lý một Message, còn MessageChannel chịu trách nhiệm chuyển message tới handler đã đăng ký. ChannelInterceptor đứng trên đường gửi hoặc nhận của channel để quan sát, biến đổi hoặc chặn message trước khi nó đi tiếp. Khi dùng channel có executor, ExecutorChannelInterceptor còn có thể can thiệp riêng vào lần gọi từng subscriber.

Kiểm thử đúng các lớp này giúp trả lời những câu hỏi quan trọng:

- Handler có nhận đúng payload và headers không?
- Điều kiện cho phép có chuyển message tới handler không?
- Điều kiện từ chối có chặn toàn bộ channel hay chỉ một handler?
- send() trả true hoặc false trong từng trường hợp có ý nghĩa gì?
- Callback postSend, afterSendCompletion và afterMessageHandled được gọi khi nào?
- Khi handler ném exception, lỗi được quan sát ở đâu?

Bài học sử dụng API Spring Framework 6.1, Java 17+ và JUnit Jupiter. Ví dụ tập trung vào Spring Messaging core; kiểm thử adapter STOMP, RSocket hoặc Spring Integration cần thêm lớp kiểm thử riêng phù hợp với adapter đó.

## 1. Các thành phần cần kiểm thử

### 1.1. Message và MessageBuilder

Message là đơn vị dữ liệu được chuyển qua hệ thống messaging. Một Message gồm payload và headers. Payload chứa nội dung chính; headers chứa metadata như content type, correlation id, tenant context hoặc destination.

Dùng MessageBuilder để tạo message trong test:

~~~java
Message<String> message = MessageBuilder.withPayload("order-42")
        .setHeader("tenantId", "acme")
        .setHeader("eventType", "ORDER_CREATED")
        .build();
~~~

MessageBuilder tạo một GenericMessage và cung cấp API để đặt, sao chép hoặc xóa headers. Cách này giúp test kiểm soát rõ đầu vào mà không cần khởi động broker hoặc transport.

Không nên đưa quá nhiều chi tiết transport vào test handler thuần. Nếu mục tiêu là kiểm tra logic xử lý payload và headers, hãy tạo Message trực tiếp. Chỉ dùng WebSocket, STOMP hoặc RSocket khi cần xác minh thêm giao thức, codec, route và cấu hình kết nối.

### 1.2. MessageHandler

MessageHandler là functional interface với một phương thức:

~~~java
void handleMessage(Message<?> message);
~~~

Handler nhận một Message và xử lý nó. Phương thức không trả về một giá trị nghiệp vụ; nếu cần gửi response, handler hoặc adapter phải thực hiện theo cơ chế reply của hệ thống.

Có thể tạo MessageHandler bằng lambda:

~~~java
MessageHandler handler = message -> {
    String orderId = (String) message.getPayload();
    String tenantId = (String) message.getHeaders().get("tenantId");

    // Xử lý message hoặc gọi service.
};
~~~

Trong unit test, kiểm tra handler nhận đúng payload/header, gọi đúng dependency, tạo side effect đúng hoặc ném exception đúng loại. Không cần dựng channel nếu test chỉ nhắm vào logic bên trong handler.

### 1.3. MessageChannel và SubscribableChannel

MessageChannel định nghĩa thao tác send. Giá trị boolean của send() cho biết message có được channel chấp nhận để gửi hay không. Một số lỗi không thể phục hồi có thể được biểu diễn bằng RuntimeException.

SubscribableChannel cho phép đăng ký một hoặc nhiều MessageHandler. Khi gửi message, channel chuyển message tới các subscriber theo implementation cụ thể.

**ExecutorSubscribableChannel** là implementation trong Spring Messaging. Nó gửi message tới từng subscriber; có thể chạy ngay trên thread gọi send() hoặc dùng Executor được cung cấp. Constructor không có Executor chạy các handler trong thread của caller, rất hữu ích cho test đồng bộ, dễ dự đoán.

### 1.4. ChannelInterceptor

ChannelInterceptor là strategy can thiệp vào thao tác gửi/nhận của MessageChannel. Các callback chính gồm:

| Callback | Thời điểm | Có thể chặn? |
|---|---|---|
| preSend | Trước khi channel thực hiện send | Có; trả null để dừng send |
| postSend | Ngay sau khi send được gọi | Không; chỉ quan sát kết quả sent |
| afterSendCompletion | Sau khi send kết thúc, kể cả khi có exception | Không; dùng cleanup/đo lường |
| preReceive | Trước khi channel lấy message | Có; trả false để dừng receive |
| postReceive | Sau khi lấy message, trước khi trả cho caller | Có thể trả null để hủy tiếp tục xử lý interceptor |
| afterReceiveCompletion | Sau khi receive kết thúc, kể cả khi có exception | Không; dùng cleanup |

Các callback receive chỉ áp dụng cho PollableChannel. SubscribableChannel không cung cấp receive(), vì message được gửi trực tiếp tới subscriber.

## 2. Điều kiện chặn ở preSend

### 2.1. Trả null để chặn toàn bộ channel

preSend được gọi trước khi message được gửi thực sự vào channel. Interceptor có thể trả về:

- Chính message ban đầu để cho phép đi tiếp.
- Một message mới để thay đổi payload hoặc headers trước khi gửi.
- null để ngăn send invocation diễn ra.

Ví dụ chỉ cho phép message thuộc tenant đã được chấp nhận:

~~~java
public class TenantGuardInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        Object tenantId = message.getHeaders().get("tenantId");

        if (!"acme".equals(tenantId)) {
            return null;
        }

        return message;
    }
}
~~~

Khi preSend trả null, AbstractMessageChannel không gọi sendInternal. Lời gọi channel.send(message) trả false. Handler không nhận message đó.

Điều này là một quyết định lọc message ở cấp channel. Toàn bộ việc gửi qua channel bị dừng; không subscriber nào nhận message đó.

### 2.2. Phân biệt trả null và ném exception

Hai cách biểu diễn có ý nghĩa khác nhau:

| Hành vi của preSend | Ý nghĩa |
|---|---|
| Trả lại message | Cho phép gửi tiếp |
| Trả message mới | Cho phép gửi tiếp với nội dung đã biến đổi |
| Trả null | Từ chối gửi theo điều kiện lọc; send() trả false |
| Ném RuntimeException | Send thất bại do lỗi; AbstractMessageChannel có thể bọc lỗi thành MessageDeliveryException |
| Ném MessagingException | Lỗi messaging được truyền theo cơ chế exception của Spring |

Dùng null khi đây là điều kiện chặn có chủ đích và caller có thể xử lý kết quả false. Dùng exception khi có lỗi cần được báo rõ, ví dụ interceptor không thể truy cập một dependency bắt buộc hoặc phát hiện trạng thái cấu hình sai.

Nếu client cần nhận một phản hồi có mã lỗi như UNAUTHORIZED hoặc INVALID_MESSAGE, việc trả null chỉ làm dừng send tại channel và có thể không tạo response cho client. Hãy thiết kế phản hồi tại tầng protocol/controller phù hợp thay vì kỳ vọng interceptor tự tạo response.

### 2.3. Vòng đời callback khi bị chặn

Với một interceptor trả null từ preSend:

- sendInternal không được gọi.
- postSend không được gọi cho lần gửi đó.
- afterSendCompletion của chính interceptor trả null không được gọi, vì callback này chỉ áp dụng khi preSend đã trả về một Message.
- Nếu các interceptor đứng trước đã trả về message thành công, chúng vẫn có thể nhận afterSendCompletion với sent=false để cleanup.

Khi send thực sự diễn ra, postSend nhận giá trị sent mà channel trả về. afterSendCompletion được gọi sau khi hoàn tất send để giải phóng tài nguyên hoặc ghi nhận kết quả. Không dùng afterSendCompletion để thay đổi quyết định gửi; lúc đó send đã hoàn tất.

## 3. Điều kiện chặn riêng từng MessageHandler

### 3.1. ExecutorChannelInterceptor.beforeHandle

ExecutorChannelInterceptor mở rộng ChannelInterceptor với hai callback:

- beforeHandle chạy ngay trước khi một MessageHandler cụ thể được gọi.
- afterMessageHandled chạy sau khi handler hoàn tất, kể cả khi handler ném exception.

Với ExecutorSubscribableChannel, các callback này chạy trong task được gửi tới Executor. Interceptor có thể trả null từ beforeHandle để bỏ qua đúng subscriber đang được xử lý.

Ví dụ:

~~~java
public class SubscriberGuardInterceptor
        implements ExecutorChannelInterceptor {

    @Override
    public Message<?> beforeHandle(
            Message<?> message,
            MessageChannel channel,
            MessageHandler handler) {

        if (shouldSkip(message, handler)) {
            return null;
        }

        return message;
    }

    private boolean shouldSkip(
            Message<?> message,
            MessageHandler handler) {
        // Điều kiện lọc riêng cho subscriber.
        return false;
    }
}
~~~

Khác biệt quan trọng:

- ChannelInterceptor.preSend chặn message trước khi channel dispatch. Mọi subscriber đều không nhận message.
- ExecutorChannelInterceptor.beforeHandle chặn ngay trước một handler cụ thể. Những subscriber khác vẫn có thể xử lý cùng message.

Vì vậy, với ExecutorSubscribableChannel, send() có thể trả true dù một subscriber đã bị bỏ qua bởi beforeHandle. Kết quả true nói rằng channel đã nhận và dispatch message theo cơ chế của nó; nó không chứng minh mọi handler đều đã chạy hoặc nghiệp vụ đã thành công.

### 3.2. Khi nào dùng từng callback?

| Nhu cầu | Callback phù hợp |
|---|---|
| Chặn mọi message không đạt điều kiện trước khi vào channel | ChannelInterceptor.preSend |
| Chuẩn hóa header dùng chung cho mọi subscriber | ChannelInterceptor.preSend |
| Chỉ bỏ qua một handler trong nhiều subscriber | ExecutorChannelInterceptor.beforeHandle |
| Ghi nhận send thành công hay thất bại | ChannelInterceptor.postSend |
| Giải phóng tài nguyên sau send | ChannelInterceptor.afterSendCompletion |
| Ghi nhận kết quả xử lý của từng handler | ExecutorChannelInterceptor.afterMessageHandled |
| Chặn thao tác lấy message từ pollable channel | ChannelInterceptor.preReceive |

Không dùng beforeHandle cho một MessageChannel implementation không hỗ trợ ExecutorChannelInterceptor. Callback này được hỗ trợ trên các channel có khả năng cấu hình Executor, điển hình là ExecutorSubscribableChannel.

## 4. Kiểm thử MessageHandler trực tiếp

Một unit test handler nên kiểm tra message thực tế mà handler nhận. Ví dụ dưới đây dùng AtomicReference để giữ lại Message:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

class MessageHandlerTests {

    @Test
    void handlerReceivesPayloadAndHeaders() {
        AtomicReference<Message<?>> received = new AtomicReference<>();
        MessageHandler handler = received::set;

        Message<String> message = MessageBuilder
                .withPayload("order-42")
                .setHeader("tenantId", "acme")
                .build();

        handler.handleMessage(message);

        assertNotNull(received.get());
        assertEquals("order-42", received.get().getPayload());
        assertEquals(
                "acme",
                received.get().getHeaders().get("tenantId"));
    }
}
~~~

Test này xác minh hợp đồng MessageHandler: handler nhận được payload và header đúng như đầu vào. Với handler thật, thay AtomicReference bằng việc gọi handler và kiểm tra dependency bằng Mockito hoặc kiểm tra trạng thái kết quả.

Nếu handler có thể ném lỗi:

~~~java
MessageHandler handler = message -> {
    throw new IllegalStateException("invalid order state");
};
~~~

Dùng assertThrows để xác minh exception. Nếu test trực tiếp handler, test quan sát exception tại nơi gọi handleMessage. Khi handler được channel gọi, implementation channel có thể bọc exception không phải MessagingException thành MessageDeliveryException. Vì vậy, hãy viết assertion theo đúng tầng đang được kiểm thử.

## 5. Kiểm thử preSend chặn toàn bộ channel

Test dưới đây dùng ExecutorSubscribableChannel không truyền Executor. Các handler chạy đồng bộ trong thread gọi send(), nên có thể assert ngay sau khi send trả về.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

class ChannelInterceptorTests {

    @Test
    void preSendNullBlocksTheWholeChannel() {
        AtomicInteger handled = new AtomicInteger();
        AtomicInteger postSendCalls = new AtomicInteger();
        AtomicInteger completionCalls = new AtomicInteger();

        ExecutorSubscribableChannel channel =
                new ExecutorSubscribableChannel();

        channel.subscribe(message -> handled.incrementAndGet());

        channel.addInterceptor(new ChannelInterceptor() {

            @Override
            public Message<?> preSend(
                    Message<?> message,
                    MessageChannel channel) {

                Object tenantId =
                        message.getHeaders().get("tenantId");

                return "acme".equals(tenantId) ? message : null;
            }

            @Override
            public void postSend(
                    Message<?> message,
                    MessageChannel channel,
                    boolean sent) {
                postSendCalls.incrementAndGet();
            }

            @Override
            public void afterSendCompletion(
                    Message<?> message,
                    MessageChannel channel,
                    boolean sent,
                    Exception ex) {
                completionCalls.incrementAndGet();
            }
        });

        Message<String> accepted = MessageBuilder
                .withPayload("order-42")
                .setHeader("tenantId", "acme")
                .build();

        Message<String> rejected = MessageBuilder
                .withPayload("order-43")
                .setHeader("tenantId", "other")
                .build();

        assertTrue(channel.send(accepted));
        assertFalse(channel.send(rejected));

        assertEquals(1, handled.get());
        assertEquals(1, postSendCalls.get());
        assertEquals(1, completionCalls.get());
    }
}
~~~

Các assertion chứng minh:

- Message có tenantId acme được gửi và handler chạy một lần.
- Message có tenantId other bị chặn trước sendInternal.
- send() của message bị chặn trả false.
- postSend và afterSendCompletion của interceptor chỉ được gọi cho message đã qua preSend.

Ở đây completionCalls bằng 1 vì interceptor duy nhất đã trả null cho message bị từ chối; callback afterSendCompletion của interceptor từ chối không chạy. Nếu có interceptor đứng trước đã chấp nhận message, interceptor đứng trước đó vẫn được cleanup qua afterSendCompletion khi một interceptor phía sau chặn.

## 6. Kiểm thử beforeHandle chặn một subscriber

Bài test tiếp theo có hai MessageHandler đăng ký cùng một channel. ExecutorChannelInterceptor chỉ bỏ qua handler được chọn; handler còn lại vẫn xử lý message.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.ExecutorChannelInterceptor;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

class ExecutorChannelInterceptorTests {

    @Test
    void beforeHandleCanSkipOneSubscriber() {
        AtomicInteger acceptedCalls = new AtomicInteger();
        AtomicInteger skippedCalls = new AtomicInteger();
        AtomicInteger afterHandledCalls = new AtomicInteger();

        MessageHandler acceptedHandler =
                message -> acceptedCalls.incrementAndGet();

        MessageHandler skippedHandler =
                message -> skippedCalls.incrementAndGet();

        ExecutorSubscribableChannel channel =
                new ExecutorSubscribableChannel();

        channel.subscribe(acceptedHandler);
        channel.subscribe(skippedHandler);

        channel.addInterceptor(new ExecutorChannelInterceptor() {

            @Override
            public Message<?> beforeHandle(
                    Message<?> message,
                    MessageChannel channel,
                    MessageHandler handler) {

                return handler == skippedHandler ? null : message;
            }

            @Override
            public void afterMessageHandled(
                    Message<?> message,
                    MessageChannel channel,
                    MessageHandler handler,
                    Exception ex) {
                afterHandledCalls.incrementAndGet();
            }
        });

        Message<String> message = MessageBuilder
                .withPayload("order-42")
                .build();

        assertTrue(channel.send(message));

        assertEquals(1, acceptedCalls.get());
        assertEquals(0, skippedCalls.get());
        assertEquals(1, afterHandledCalls.get());
    }
}
~~~

Vì channel được tạo không có Executor, các SendTask chạy ngay trong thread gọi send(). Do đó các bộ đếm đã có giá trị cuối cùng khi assertion chạy.

Test cũng cho thấy một chi tiết dễ nhầm: channel.send(message) trả true dù skippedHandler không được gọi. Channel đã nhận message và dispatch tới các subscriber; bộ lọc ở beforeHandle chỉ bỏ qua một lần gọi handler. afterMessageHandled chỉ được gọi cho handler mà beforeHandle trả về một Message. Với subscriber bị bỏ qua, callback này không được gọi cho interceptor đã trả null.

Nếu channel được cấu hình với Executor bất đồng bộ, không được assert các bộ đếm ngay sau send(). Hãy đồng bộ test bằng CountDownLatch, CompletableFuture hoặc một cơ chế chờ có timeout. Tránh dùng Thread.sleep vì thời gian xử lý phụ thuộc lịch chạy thread và có thể làm test chập chờn.

## 7. Kiểm thử điều kiện allow/deny

Điều kiện chặn nên được kiểm tra cả nhánh cho phép và nhánh từ chối. Chỉ test nhánh từ chối có thể bỏ sót lỗi như interceptor luôn trả null; chỉ test nhánh cho phép có thể bỏ sót việc message không hợp lệ vẫn đi qua.

Một ma trận kiểm thử mẫu:

| Điều kiện | Kết quả mong đợi | Assertion |
|---|---|---|
| Header tenantId được cho phép | Handler được gọi | send true, handled tăng 1 |
| Header tenantId không được phép | Channel chặn message | send false, handled không tăng |
| Header bắt buộc bị thiếu | Chặn hoặc báo lỗi theo policy đã chọn | Kiểm tra false hoặc exception đúng hợp đồng |
| Message type nằm trong allow list | Cho phép gửi | Handler nhận đúng payload |
| Message type nằm ngoài allow list | Chặn hoặc route tới xử lý lỗi | Handler nghiệp vụ không được gọi |
| Message đã hết hạn | Chặn trước dispatch | Không phát sinh side effect |
| Rate limit bị vượt | Từ chối theo policy | Đếm đúng số message bị chặn |
| beforeHandle từ chối một subscriber | Subscriber đó không chạy | Subscriber khác vẫn chạy |

Mỗi test nên chuẩn bị dữ liệu riêng, đăng ký interceptor rõ ràng và kiểm tra cả kết quả send lẫn side effect ở handler. Không nên chỉ assert rằng interceptor đã được gọi; điều cần chứng minh là message có đi đến đúng handler hay bị chặn đúng phạm vi.

## 8. Kiểm thử thứ tự và callback của interceptor

Một channel có thể có nhiều interceptor. Interceptor được thêm bằng addInterceptor(interceptor) sẽ được nối vào cuối danh sách; overload addInterceptor(index, interceptor) cho phép đặt vị trí. setInterceptors(list) thay toàn bộ danh sách hiện tại, vì vậy dùng nó trong cấu hình có thể vô tình xóa interceptor đã đăng ký trước đó.

Khi kiểm thử thứ tự, có thể dùng AtomicReference hoặc List để ghi lại callback:

- Interceptor A thêm header đã chuẩn hóa trong preSend.
- Interceptor B kiểm tra header đó trong preSend.
- Handler kiểm tra message cuối cùng mà nó nhận.
- postSend ghi lại kết quả sent.
- afterSendCompletion xác nhận cleanup sau khi send kết thúc.

Nếu interceptor trả về một Message mới, message mới sẽ được chuyển tới các interceptor tiếp theo và channel. Dùng MessageBuilder.fromMessage(message) khi cần tạo bản sao giữ lại các header hiện có rồi cập nhật một số trường.

~~~java
Message<?> normalized = MessageBuilder
        .fromMessage(message)
        .setHeader("normalized", true)
        .build();

return normalized;
~~~

Không sửa trực tiếp MessageHeaders của một message đã được publish như thể đó là Map mutable. Message và headers được thiết kế theo hướng bất biến; hãy tạo message mới hoặc dùng MessageHeaderAccessor đúng vòng đời khi cần thay đổi header.

Với send bình thường:

1. preSend chạy trước sendInternal.
2. postSend chạy sau sendInternal và nhận boolean sent.
3. afterSendCompletion chạy sau cùng để cleanup, kể cả khi send phát sinh exception, miễn là interceptor đã cho preSend đi qua.

Nếu preSend trả null, sendInternal và postSend không chạy. afterSendCompletion chỉ áp dụng cho các interceptor đã chấp nhận message trước đó; interceptor trả null không nhận callback hoàn tất của chính nó.

## 9. Điều kiện chặn ở receive

ChannelInterceptor cũng có callback cho receive, nhưng phạm vi áp dụng hẹp hơn:

- preReceive trả false để ngăn channel lấy message.
- postReceive chạy sau khi lấy được message và có thể biến đổi message.
- Các callback receive này chỉ áp dụng cho PollableChannel.

SubscribableChannel gửi message trực tiếp tới subscriber và không có API receive(). Vì vậy, không viết test preReceive trên ExecutorSubscribableChannel; test đó không kiểm tra được đường xử lý thực tế.

Nếu hệ thống sử dụng PollableChannel, hãy kiểm thử riêng các trường hợp preReceive cho phép, preReceive từ chối và không có message để nhận. Chỉ xác minh các callback phù hợp với implementation channel đang dùng.

## 10. Kiểm thử handler annotation và adapter

Một phương thức có @MessageMapping không tự nó là MessageHandler. Spring tạo adapter/handler mapping để tìm phương thức tương ứng với message, resolve tham số, convert payload rồi gọi method.

Vì vậy nên chia kiểm thử thành các lớp:

| Lớp test | Điều cần chứng minh |
|---|---|
| Unit test service/controller method | Logic nghiệp vụ, kết quả và exception |
| Unit test MessageHandler | Payload/header được xử lý đúng |
| Channel test | Channel dispatch và interceptor allow/deny đúng |
| Handler mapping test | Destination/route được ánh xạ tới đúng method |
| Adapter integration test | Codec, header mapping, authentication và protocol hoạt động đúng |
| End-to-end test | Client thực gửi message qua transport và nhận kết quả mong đợi |

Gọi trực tiếp một phương thức controller trong unit test không kiểm tra @MessageMapping, argument resolver, message converter hay interceptor của channel. Khi cần xác minh các phần này, hãy tạo test với cấu hình adapter thực tế hoặc dùng client test tương ứng, chẳng hạn STOMP client cho WebSocket/STOMP hoặc RSocketRequester cho RSocket.

Không nên đưa toàn bộ Spring ApplicationContext và transport vào mọi test. Unit test nhỏ chạy nhanh và chỉ rõ nguyên nhân; integration test ít hơn nhưng xác minh được wiring giữa các tầng.

## 11. Những lỗi kiểm thử thường gặp

| Lỗi | Vì sao sai | Cách sửa |
|---|---|---|
| Chỉ kiểm tra interceptor được gọi | Chưa chứng minh handler có chạy hay không | Assert send result và số lần handler được gọi |
| Nghĩ send true nghĩa là mọi handler đã xử lý xong | send xác nhận channel chấp nhận/dispatch theo implementation | Kiểm tra side effect hoặc completion riêng |
| Dùng preSend để chặn một subscriber | preSend chặn toàn bộ channel | Dùng ExecutorChannelInterceptor.beforeHandle nếu channel hỗ trợ |
| Nghĩ beforeHandle null làm send false | beforeHandle chạy ở từng subscriber sau channel dispatch | Assert subscriber bị bỏ qua và subscriber khác vẫn chạy |
| Test async rồi assert ngay | Handler có thể chưa chạy khi assertion bắt đầu | Dùng latch/future có timeout |
| Dùng Thread.sleep để chờ | Test phụ thuộc timing và dễ flaky | Đồng bộ theo tín hiệu hoàn tất |
| Kiểm thử preReceive trên SubscribableChannel | SubscribableChannel không có receive() | Dùng PollableChannel thực tế |
| Chỉ test nhánh deny | Có thể interceptor chặn mọi message | Test cả allow và deny |
| Dùng setInterceptors vô tình xóa cấu hình khác | API này thay danh sách hiện tại | Dùng addInterceptor hoặc cấu hình danh sách đầy đủ |
| Dùng header do client tự gửi làm danh tính tin cậy | Header có thể bị giả mạo | Dựa trên Principal/session đã xác thực và policy server |
| Chờ handler trả kết quả từ MessageHandler | handleMessage trả void | Kiểm tra side effect, output channel hoặc adapter reply |
| Test trực tiếp method @MessageMapping nhưng kết luận route đúng | Không chạy handler mapping | Thêm integration test cho adapter |

## 12. Thiết kế interceptor an toàn

Interceptor thường nằm trên đường đi của mọi message trong channel. Vì vậy:

- Giữ preSend và beforeHandle nhanh, tránh gọi dịch vụ mạng hoặc truy vấn database đồng bộ.
- Chỉ kiểm tra các điều kiện cần thiết ở tầng channel; xử lý nghiệp vụ phức tạp trong handler/service.
- Không dùng header do client kiểm soát làm bằng chứng danh tính. Dùng thông tin principal/session được xác thực và kiểm tra quyền ở server.
- Phân biệt chặn có chủ đích với lỗi vận hành: null là lọc message; exception là lỗi cần quan sát.
- Ghi nhận số message bị chặn theo lý do, nhưng tránh log token, cookie, payload cá nhân hoặc dữ liệu bí mật.
- Không tạo side effect nghiệp vụ trong interceptor vì callback có thể chạy ở thread gửi hoặc thread executor tùy channel.
- Khi thay đổi message, tạo message mới và giữ các header cần thiết.
- Với async channel, bảo đảm mọi state dùng chung trong interceptor an toàn luồng.

Một interceptor chặn không nên âm thầm làm mất command quan trọng mà không có metric hoặc log phù hợp. Nếu message bị từ chối cần được retry, dead-letter hoặc trả lỗi cho client, hãy thiết kế đường xử lý đó rõ ràng; giá trị false của send() tự nó không phải một phản hồi nghiệp vụ.

## 13. Checklist cho một bộ test tốt

Trước khi kết luận MessageHandler và interceptor hoạt động đúng, hãy xác nhận:

1. Test tạo Message với payload và headers đúng kiểu.
2. Handler trực tiếp nhận đúng message và thực hiện đúng hành vi.
3. preSend cho phép message hợp lệ.
4. preSend trả null chặn message không hợp lệ và send() trả false.
5. Handler không được gọi khi toàn channel bị chặn.
6. postSend và afterSendCompletion được kiểm tra đúng vòng đời.
7. beforeHandle trả null chỉ bỏ qua subscriber được chọn.
8. Subscriber khác vẫn nhận message khi một subscriber bị bỏ qua.
9. Test bất đồng bộ có cơ chế chờ deterministic và timeout hữu hạn.
10. preReceive chỉ được test trên PollableChannel.
11. Integration test kiểm tra mapping, conversion và transport khi cần.
12. Test kiểm tra cả side effect và metric/log quan trọng, không chỉ kiểm tra callback đã chạy.

## Ghi nhớ

MessageHandler là nơi xử lý Message; MessageChannel điều phối việc gửi; ChannelInterceptor can thiệp ở ranh giới channel. preSend trả null chặn toàn bộ send và khiến send() trả false. ExecutorChannelInterceptor.beforeHandle trả null bỏ qua đúng một MessageHandler trong quá trình dispatch của ExecutorSubscribableChannel; send() vẫn có thể trả true vì channel đã nhận message.

Để kiểm thử rõ ràng, hãy dùng MessageBuilder tạo đầu vào, gọi MessageHandler trực tiếp cho unit test, dùng ExecutorSubscribableChannel để kiểm tra dispatch và interceptor, rồi bổ sung integration test khi cần xác minh adapter hoặc protocol. Luôn kiểm tra cả kết quả send, số lần handler chạy, callback hoàn tất và side effect thực tế.

## Tài liệu tham khảo

- [MessageHandler — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/MessageHandler.html)
- [MessageChannel — Spring Framework 6.1.x API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/MessageChannel.html)
- [ChannelInterceptor — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [ExecutorChannelInterceptor — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/ExecutorChannelInterceptor.html)
- [ExecutorSubscribableChannel — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html)
- [AbstractMessageChannel — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/AbstractMessageChannel.html)
- [InterceptableChannel — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/InterceptableChannel.html)
- [MessageBuilder — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
- [Spring Framework Messaging package](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/package-summary.html)
