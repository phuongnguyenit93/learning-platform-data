# Kiểm thử gửi nhận qua kênh với executor có kiểm soát

Trong Spring Messaging, một message được gửi qua MessageChannel và được chuyển đến một hoặc nhiều MessageHandler. Khi kênh dùng executor, việc gửi message và việc handler thực sự xử lý message diễn ra ở hai thời điểm khác nhau. Vì vậy, test chỉ gọi send() rồi kiểm tra ngay kết quả handler có thể bị race condition: test chạy trước khi worker thread xử lý xong.

Một executor có kiểm soát giúp kiểm thử luồng bất đồng bộ theo cách xác định. Thay vì tạo thread chạy tùy thời điểm, test dùng một executor giữ các Runnable trong hàng đợi. Test quyết định khi nào chạy từng task, từ đó kiểm tra rõ message được xếp lịch, handler nhận đúng payload/header và reply được gửi tiếp như mong đợi.

## 1. Phân biệt các loại channel và cách nhận message

Các abstraction chính trong Spring Messaging:

- **MessageChannel:** hợp đồng gửi Message. Phương thức send() trả về boolean để báo việc gửi được chấp nhận hay không.
- **SubscribableChannel:** channel giữ danh sách subscriber là các MessageHandler. Khi có message, channel gọi các handler đã đăng ký.
- **ExecutorSubscribableChannel:** một SubscribableChannel có thể giao việc gọi handler cho java.util.concurrent.Executor.
- **PollableChannel:** channel có API receive() để consumer chủ động lấy message. QueueChannel là một ví dụ thường gặp ở Spring Integration.

Cần phân biệt cách nhận của hai nhóm:

| Loại channel | Cách consumer nhận message | Cách kiểm thử |
|---|---|---|
| SubscribableChannel | MessageHandler được đăng ký bằng subscribe(handler) | Ghi nhận message trong handler và kiểm soát thời điểm executor chạy task |
| PollableChannel | Consumer gọi receive() hoặc receive(timeout) | Gửi message rồi gọi receive với timeout giới hạn |
| ExecutorSubscribableChannel | MessageHandler chạy qua Executor | Dùng executor giả để xếp lịch và chạy task theo ý test |

ExecutorSubscribableChannel thuộc package org.springframework.messaging.support của Spring Framework. QueueChannel thường được dùng từ Spring Integration; đừng nhầm implementation của Spring Integration với channel có sẵn trong module spring-messaging.

## 2. Điều gì xảy ra khi gọi send() trên ExecutorSubscribableChannel?

Với một ExecutorSubscribableChannel được tạo cùng executor:

1. Caller gọi channel.send(message).
2. Channel chạy các interceptor ở giai đoạn gửi.
3. Với mỗi subscriber, channel tạo một task xử lý message.
4. Channel chuyển task cho executor bằng execute(task).
5. send() trả về sau khi việc gửi/lập lịch hoàn tất.
6. Executor chạy task; task gọi MessageHandler.handleMessage(message).
7. Các callback sau xử lý của ExecutorChannelInterceptor được gọi sau khi handler hoàn thành hoặc ném lỗi.

Vì thế, send() trả về true không có nghĩa handler đã chạy xong. Nó thường chỉ cho biết channel đã chấp nhận việc gửi và chuyển task cho executor. Với executor chạy bất đồng bộ, handler có thể chưa được gọi tại thời điểm send() trả về.

Một điểm quan trọng khác: ExecutorSubscribableChannel không có phương thức receive(). Phía nhận chính là MessageHandler đã subscribe. Nếu test cần kiểm tra message đến consumer, hãy ghi nhận message ngay trong handler hoặc dùng một PollableChannel làm đầu ra của handler.

### 2.1. Executor mặc định và executor được truyền vào

- new ExecutorSubscribableChannel() tạo channel chạy handler trên thread gọi send().
- new ExecutorSubscribableChannel(executor) giao task cho executor đã cung cấp.
- Truyền null cũng có nghĩa thực thi trên thread gọi send().

Nếu mục tiêu là kiểm tra việc lập lịch bất đồng bộ, không dùng constructor mặc định hoặc executor đồng bộ. Hãy truyền một executor do test kiểm soát.

### 2.2. send() không chờ handler hoàn thành

Không dùng đoạn test như sau cho channel bất đồng bộ:

~~~java
assertTrue(channel.send(message));
assertEquals("hello", received.getPayload());
~~~

Đoạn trên có thể lúc chạy được, lúc thất bại tùy thời điểm worker thread. Không sửa race condition bằng Thread.sleep(100), vì sleep chỉ làm test chậm và vẫn không bảo đảm task đã hoàn thành.

Thay vào đó, test cần một tín hiệu xác định: tự chạy task trong executor giả, hoặc chờ CountDownLatch/CompletableFuture với timeout khi đang kiểm tra executor thật.

## 3. Tạo executor giả để điều khiển từng task

Một executor giả tối giản có thể giữ Runnable trong hàng đợi. Test gọi runNext() để thực thi chính xác một task, hoặc runAll() nếu muốn xử lý hết task đang chờ.

~~~java
import java.util.ArrayDeque;
import java.util.Queue;
import java.util.concurrent.Executor;

final class ManualExecutor implements Executor {

    private final Queue<Runnable> tasks = new ArrayDeque<>();

    @Override
    public void execute(Runnable task) {
        this.tasks.add(task);
    }

    int pendingTasks() {
        return this.tasks.size();
    }

    void runNext() {
        Runnable task = this.tasks.poll();
        if (task == null) {
            throw new IllegalStateException("No task is pending");
        }
        task.run();
    }

    void runAll() {
        while (!this.tasks.isEmpty()) {
            runNext();
        }
    }
}
~~~

Đặc điểm của ManualExecutor:

- execute() chỉ thêm task vào queue, không chạy task ngay.
- pendingTasks() cho biết số task đang chờ.
- runNext() chạy đúng một task và trả quyền điều khiển về test.
- runAll() chạy hết các task đang chờ, kể cả task mới được thêm trong lúc xử lý.

Executor này chỉ dành cho test đơn luồng. Nó không mô phỏng thread scheduling, race condition hoặc khả năng chạy song song của thread pool thật. Đổi lại, nó cho phép kiểm tra thứ tự và thời điểm xử lý mà không phụ thuộc tốc độ máy hoặc sleep.

## 4. Kiểm thử gửi request và nhận reply theo từng bước

Ví dụ dưới đây dùng hai ExecutorSubscribableChannel: một channel nhận request và một channel phát reply. Cả hai dùng chung ManualExecutor. Test chủ động chạy task của request trước, sau đó mới chạy task của reply.

~~~java
import java.util.concurrent.Executor;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class ExecutorSubscribableChannelTest {

    @Test
    void sendsRequestAndReceivesReplyDeterministically() {
        ManualExecutor executor = new ManualExecutor();

        ExecutorSubscribableChannel inbound =
                new ExecutorSubscribableChannel(executor);
        ExecutorSubscribableChannel outbound =
                new ExecutorSubscribableChannel(executor);

        AtomicReference<Message<?>> requestReceived = new AtomicReference<>();
        AtomicReference<Message<?>> replyReceived = new AtomicReference<>();

        inbound.subscribe(request -> {
            requestReceived.set(request);

            Message<String> reply = MessageBuilder.withPayload("pong")
                    .setHeader(
                            "correlationId",
                            request.getHeaders().get("correlationId"))
                    .build();

            assertTrue(outbound.send(reply));
        });

        outbound.subscribe(replyReceived::set);

        Message<String> request = MessageBuilder.withPayload("ping")
                .setHeader("correlationId", "corr-42")
                .build();

        // Send chỉ xếp task; handler chưa chạy.
        assertTrue(inbound.send(request));
        assertNull(requestReceived.get());
        assertNull(replyReceived.get());
        assertEquals(1, executor.pendingTasks());

        // Chạy task của inbound channel.
        executor.runNext();
        assertEquals("ping", requestReceived.get().getPayload());
        assertNull(replyReceived.get());

        // Handler inbound đã gửi reply, nên có một task outbound đang chờ.
        assertEquals(1, executor.pendingTasks());

        // Chạy task của outbound channel.
        executor.runNext();
        assertEquals("pong", replyReceived.get().getPayload());
        assertEquals(
                "corr-42",
                replyReceived.get().getHeaders().get("correlationId"));
        assertEquals(0, executor.pendingTasks());
    }

    static final class ManualExecutor implements Executor {

        private final java.util.Queue<Runnable> tasks =
                new java.util.ArrayDeque<>();

        @Override
        public void execute(Runnable task) {
            this.tasks.add(task);
        }

        int pendingTasks() {
            return this.tasks.size();
        }

        void runNext() {
            Runnable task = this.tasks.poll();
            if (task == null) {
                throw new IllegalStateException("No task is pending");
            }
            task.run();
        }
    }
}
~~~

Đây là một JUnit 5 test class hoàn chỉnh. Test dùng MessageBuilder để tạo message có payload và correlationId, sau đó xác nhận cả request lẫn reply giữ đúng dữ liệu.

Luồng thực thi:

~~~text
Test
 |
 | inbound.send(request)
 v
ManualExecutor: [request task]
 |
 | runNext()
 v
Inbound MessageHandler nhận "ping"
 |
 | outbound.send(reply)
 v
ManualExecutor: [reply task]
 |
 | runNext()
 v
Outbound MessageHandler nhận "pong"
 |
 v
Test xác nhận payload + correlationId
~~~

Điểm cần quan sát là sau lần runNext() thứ nhất, request handler đã nhận message nhưng reply handler vẫn chưa chạy. Reply chỉ được nhận sau lần runNext() thứ hai. Test vì thế chứng minh được ranh giới bất đồng bộ giữa hai channel.

## 5. Kiểm thử nhiều subscriber

ExecutorSubscribableChannel gửi message tới từng subscriber. Với mỗi handler, channel tạo một task riêng và chuyển task cho executor.

Ví dụ có hai subscriber:

~~~java
ManualExecutor executor = new ManualExecutor();
ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel(executor);

List<String> received = new ArrayList<>();

channel.subscribe(message -> received.add("handler-A"));
channel.subscribe(message -> received.add("handler-B"));

assertTrue(channel.send(
        MessageBuilder.withPayload("event").build()));

assertEquals(2, executor.pendingTasks());
assertTrue(received.isEmpty());

executor.runNext();
assertEquals(1, received.size());

executor.runNext();
assertEquals(2, received.size());
~~~

Ví dụ này minh họa một task cho mỗi subscriber. Không nên mặc định thứ tự hoàn thành của nhiều subscriber khi dùng thread pool thật. Với ManualExecutor dạng FIFO, test có thể kiểm soát thứ tự chạy task, nhưng đó là thứ tự do executor giả tạo ra, không phải cam kết tổng quát cho mọi executor.

Nếu nghiệp vụ yêu cầu thứ tự xử lý, hãy kiểm tra cấu hình preserve order hoặc cơ chế tuần tự hóa phù hợp của hệ thống thực tế. Không suy ra thứ tự xử lý từ thứ tự gọi subscribe() khi các task có thể chạy đồng thời.

## 6. Kiểm thử lỗi trong MessageHandler

Với executor bất đồng bộ, exception phát sinh bên trong handler thường xuất hiện khi executor chạy task. Caller đã nhận kết quả từ send() trước đó nên không thể dùng assertThrows quanh send() để bắt lỗi xử lý bất đồng bộ.

Với một handler ném IllegalStateException, ExecutorSubscribableChannel bọc lỗi xử lý thành MessageDeliveryException. ManualExecutor giúp test bắt exception tại đúng thời điểm chạy task:

~~~java
import org.springframework.messaging.MessageDeliveryException;

@Test
void handlerFailureIsObservedWhenExecutorRunsTask() {
    ManualExecutor executor = new ManualExecutor();
    ExecutorSubscribableChannel channel =
            new ExecutorSubscribableChannel(executor);

    channel.subscribe(message -> {
        throw new IllegalStateException("invalid state");
    });

    Message<String> message =
            MessageBuilder.withPayload("bad-event").build();

    assertTrue(channel.send(message));

    assertEquals(1, executor.pendingTasks());

    assertThrows(
            MessageDeliveryException.class,
            executor::runNext);
}
~~~

Trong trường hợp handler ném một MessagingException, implementation có thể chuyển tiếp chính exception đó thay vì bọc thành MessageDeliveryException. Test nên xác nhận đúng exception contract mà handler và adapter của ứng dụng cung cấp.

Đừng coi việc send() trả true là bằng chứng message đã được xử lý thành công. Nếu cần xác nhận kết quả xử lý, hãy kiểm tra output channel, completion signal, trạng thái nghiệp vụ hoặc callback phù hợp.

## 7. Phân biệt ChannelInterceptor và ExecutorChannelInterceptor

Hai loại interceptor hoạt động ở các giai đoạn khác nhau.

### ChannelInterceptor

ChannelInterceptor quan sát vòng đời gửi/nhận ở mức channel:

- preSend(): trước khi channel gửi message; có thể sửa message hoặc trả null để chặn việc gửi.
- postSend(): ngay sau khi lời gọi send hoàn thành; nhận boolean cho biết send thành công hay không.
- afterSendCompletion(): chạy sau khi hoàn tất chu kỳ send, kể cả khi có exception.

Với ExecutorSubscribableChannel, postSend() có thể chạy trước khi subscriber xử lý message vì send chỉ mới xếp task cho executor.

### ExecutorChannelInterceptor

ExecutorChannelInterceptor mở rộng ChannelInterceptor và cung cấp callback theo từng subscriber trong task executor:

- beforeHandle(): ngay trước khi gọi MessageHandler.
- afterMessageHandled(): sau khi handler hoàn thành, kể cả khi handler ném exception.

Nếu mục tiêu test là xác nhận handler đã bắt đầu hoặc hoàn tất xử lý, callback của ExecutorChannelInterceptor phù hợp hơn postSend().

Ví dụ ghi nhận kết quả xử lý:

~~~java
AtomicReference<Exception> handlingError = new AtomicReference<>();

channel.addInterceptor(new ExecutorChannelInterceptor() {

    @Override
    public void afterMessageHandled(
            Message<?> message,
            MessageChannel channel,
            MessageHandler handler,
            Exception ex) {

        handlingError.set(ex);
    }
});
~~~

Trong test dùng ManualExecutor, có thể assert handlingError vẫn null trước runNext(), rồi kiểm tra giá trị sau khi task chạy. Nếu handler thành công, ex là null; nếu handler lỗi, callback nhận exception tương ứng.

## 8. Khi cần kiểm thử executor thật

ManualExecutor phù hợp cho unit test về lập lịch và thứ tự. Khi cần xác nhận tích hợp với ThreadPoolTaskExecutor hoặc hành vi đa luồng, hãy dùng executor thật và một tín hiệu đồng bộ.

Ví dụ dùng CountDownLatch:

~~~java
CountDownLatch handled = new CountDownLatch(1);
AtomicReference<Message<?>> received = new AtomicReference<>();

ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel(threadPoolTaskExecutor);

channel.subscribe(message -> {
    received.set(message);
    handled.countDown();
});

assertTrue(channel.send(
        MessageBuilder.withPayload("async-event").build()));

assertTrue(handled.await(2, TimeUnit.SECONDS));
assertEquals("async-event", received.get().getPayload());
~~~

Trong ví dụ này, threadPoolTaskExecutor là ThreadPoolTaskExecutor đã được initialize và quản lý vòng đời bởi Spring context. Test phải shutdown context hoặc executor sau khi hoàn tất.

CountDownLatch.await(timeout) có giới hạn thời gian nên test không treo vô hạn. Nếu dùng CompletableFuture, hãy dùng get(timeout, unit) hoặc một API await tương đương có deadline. Không dùng Thread.sleep để đoán khi nào handler hoàn thành.

ManualExecutor và executor thật kiểm tra hai loại thuộc tính khác nhau:

| Mục tiêu | Công cụ phù hợp |
|---|---|
| Xác nhận send chỉ xếp task | ManualExecutor |
| Chạy từng handler theo ý test | ManualExecutor |
| Kiểm tra request/reply theo từng bước | ManualExecutor |
| Kiểm tra exception khi task chạy | ManualExecutor |
| Kiểm tra thread thực tế, concurrency, shutdown | ThreadPoolTaskExecutor + latch/future |
| Kiểm tra race condition và tính thread-safe | Executor thật, barrier/latch và kiểm thử lặp có kiểm soát |

## 9. Các lưu ý khi dùng executor trong test

### 9.1. Executor từ chối task

Trong implementation hiện hành của ExecutorSubscribableChannel, nếu executor ném RejectedExecutionException, channel chạy task ngay trên thread gửi như một fallback được xem là trường hợp executor đang shutdown. Vì vậy, đừng mặc định rằng executor từ chối task sẽ khiến send() trả false hoặc handler không được gọi.

Hành vi fallback này có thể làm handler chạy đồng bộ trên caller thread và thay đổi latency. Nếu ứng dụng cần chính sách từ chối task khác, hãy kiểm tra phiên bản Spring đang dùng và cấu hình executor phù hợp.

### 9.2. Không để task rò rỉ giữa các test

ManualExecutor phải được tạo mới cho từng test hoặc được dọn sạch sau mỗi test. Nếu queue còn task từ test trước, test sau có thể chạy nhầm message và tạo lỗi khó giải thích.

Với executor thật, đóng ApplicationContext hoặc gọi shutdown đúng vòng đời. Không dùng chung một thread pool toàn cục giữa test nếu không có lý do rõ ràng.

### 9.3. Tránh assert trạng thái trước khi đồng bộ

Đọc AtomicReference ngay sau send() chỉ chứng minh handler chưa cập nhật giá trị tại thời điểm đọc. Với executor thật, giá trị có thể thay đổi ngay sau đó. Chỉ assert trạng thái cuối sau latch/future hoặc một cơ chế đồng bộ tương đương.

### 9.4. Không giả định send timeout giới hạn thời gian xử lý handler

MessageChannel.send(message, timeout) mô tả thời gian chờ gửi/được channel chấp nhận theo implementation. Nó không phải deadline chung cho toàn bộ thời gian handler xử lý. Với ExecutorSubscribableChannel, task có thể tiếp tục chạy sau khi send() đã trả về. Muốn giới hạn thời gian xử lý, hãy quản lý deadline ở handler, executor hoặc tầng ứng dụng.

### 9.5. Kiểm thử channel không thay thế integration test với broker

Một test ExecutorSubscribableChannel xác nhận logic gửi, lập lịch và gọi handler trong process. Nó không xác nhận broker bên ngoài đã nhận message, ACK, persistence, redelivery, routing hoặc delivery guarantee.

Với broker thật, cần integration test riêng để kiểm tra adapter, connection, serialization, acknowledgment và retry. Giữ unit test nhanh, xác định; chỉ dùng broker trong test khi đang kiểm tra hành vi tích hợp.

## 10. Checklist cho một test gửi nhận đáng tin cậy

- [ ] Dùng đúng loại channel cho mục tiêu: SubscribableChannel hay PollableChannel.
- [ ] Nếu kiểm tra bất đồng bộ, truyền executor do test kiểm soát.
- [ ] Xác nhận send() trả true và task đã được xếp lịch.
- [ ] Xác nhận handler chưa chạy trước khi executor thực thi task.
- [ ] Chủ động chạy task và xác nhận payload/header nhận được.
- [ ] Nếu handler gửi reply, xác nhận reply chỉ được nhận sau task tương ứng.
- [ ] Kiểm tra correlationId hoặc message ID được bảo toàn.
- [ ] Kiểm tra exception tại thời điểm task chạy, không chỉ quanh send().
- [ ] Dùng ExecutorChannelInterceptor nếu cần xác nhận thời điểm handler hoàn tất.
- [ ] Không dùng Thread.sleep hoặc timeout vô hạn.
- [ ] Dọn queue, subscription, ApplicationContext và executor sau test.
- [ ] Có integration test riêng cho broker thật nếu cần xác nhận delivery/ACK.

## Tài liệu tham khảo

- Spring Framework Javadoc — ExecutorSubscribableChannel: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html
- Spring Framework Javadoc — SubscribableChannel: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/SubscribableChannel.html
- Spring Framework Javadoc — MessageChannel: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html
- Spring Framework Javadoc — ChannelInterceptor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html
- Spring Framework Javadoc — ExecutorChannelInterceptor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ExecutorChannelInterceptor.html
- Spring Framework source — ExecutorSubscribableChannel implementation: https://github.com/spring-projects/spring-framework/blob/main/spring-messaging/src/main/java/org/springframework/messaging/support/ExecutorSubscribableChannel.java
- Spring Framework tests — MessageBrokerConfigurationTests: https://github.com/spring-projects/spring-framework/blob/main/spring-messaging/src/test/java/org/springframework/messaging/simp/config/MessageBrokerConfigurationTests.java
