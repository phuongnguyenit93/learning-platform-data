# Phân biệt luồng thực thi của ChannelInterceptor và ExecutorChannelInterceptor

Spring Messaging có hai loại interceptor thường xuất hiện khi gửi message qua channel:

- `ChannelInterceptor` quan sát hoặc điều chỉnh vòng đời gửi/nhận ở cấp channel.
- `ExecutorChannelInterceptor` mở rộng `ChannelInterceptor` và bổ sung callback chạy quanh việc một `MessageHandler` xử lý message trên channel có dispatch qua executor.

Điểm khác nhau quan trọng là **vị trí callback trong luồng xử lý**. Với `ExecutorSubscribableChannel` có executor, các callback gửi của `ChannelInterceptor` chạy trong thread gọi `send()`; còn `beforeHandle` và `afterMessageHandled` của `ExecutorChannelInterceptor` chạy trong thread thực thi handler. Khi channel chạy inline, hai nhóm callback có thể cùng chạy trong thread gửi.

## 1. Hai interface và phạm vi của chúng

Cả hai interface thuộc package `org.springframework.messaging.support`.

### ChannelInterceptor

`ChannelInterceptor` định nghĩa các callback ở cấp channel:

| Callback | Thời điểm | Mục đích |
| --- | --- | --- |
| `preSend(message, channel)` | Trước khi channel gửi message | Kiểm tra, ghi log hoặc trả về message đã chỉnh sửa |
| `postSend(message, channel, sent)` | Sau khi channel thực hiện thao tác gửi | Quan sát kết quả gửi `true/false` |
| `afterSendCompletion(message, channel, sent, ex)` | Khi vòng đời gửi hoàn tất | Dọn tài nguyên hoặc ghi nhận lỗi |
| `preReceive(channel)` | Trước khi nhận từ channel có hỗ trợ receive | Cho phép hoặc ngăn thao tác nhận |
| `postReceive(message, channel)` | Sau khi nhận message | Kiểm tra hoặc thay đổi message nhận được |
| `afterReceiveCompletion(message, channel, ex)` | Khi vòng đời nhận hoàn tất | Dọn tài nguyên hoặc ghi nhận lỗi |

Với thao tác `send()`, ba callback đầu thường chạy trong thread gọi `channel.send(...)`. Đây là thread thực hiện thao tác gửi ở cấp channel, thường là thread producer. Nếu producer gọi `send` từ một worker thread thì interceptor cũng chạy trong worker thread đó.

`preSend` có thể trả về một message mới để thay message gửi đi. Trả về `null` có nghĩa là chặn việc gửi. `postSend` nhận biến `sent` để biết kết quả của thao tác gửi. `afterSendCompletion` nhận exception nếu vòng đời gửi kết thúc bằng lỗi.

Ba callback nhận chỉ áp dụng cho channel có hỗ trợ thao tác nhận, chẳng hạn một `PollableChannel`. `ExecutorSubscribableChannel` là channel gửi đến các subscriber và không cung cấp `receive()`.

### ExecutorChannelInterceptor

`ExecutorChannelInterceptor` kế thừa `ChannelInterceptor` và thêm hai callback:

```java
Message<?> beforeHandle(
        Message<?> message,
        MessageChannel channel,
        MessageHandler handler);

void afterMessageHandled(
        Message<?> message,
        MessageChannel channel,
        MessageHandler handler,
        Exception ex);
```

Hai callback này bao quanh việc thực thi từng `MessageHandler`:

- `beforeHandle` chạy trước `handler.handleMessage(message)`. Nó có thể trả về message đã chỉnh sửa hoặc trả `null` để bỏ qua handler.
- `afterMessageHandled` chạy sau khi handler xử lý xong hoặc thất bại. Tham số `ex` là `null` nếu handler hoàn tất bình thường; nếu có lỗi, nó chứa exception liên quan.

Với `ExecutorSubscribableChannel`, các callback này chạy trong thread thực hiện task gửi đến handler. Nếu executor thực sự dispatch sang worker thread thì callback chạy trên worker thread đó.

Vì interface này kế thừa `ChannelInterceptor`, một object triển khai `ExecutorChannelInterceptor` vẫn có thể override `preSend`, `postSend`, `afterSendCompletion` và các callback cấp channel khác. Các callback cấp channel chạy trong thread gọi gửi/nhận; chỉ hai callback bổ sung có ngữ cảnh thực thi handler.

## 2. Luồng thread khi dùng ExecutorSubscribableChannel

Giả sử producer gọi `send()` trên một `ExecutorSubscribableChannel` được cấu hình với executor:

```text
Producer thread                         Executor worker
      |                                       |
      |-- ChannelInterceptor.preSend ---------|
      |                                       |
      |-- submit SendTask -------------------->|
      |                                       |-- ExecutorChannelInterceptor.beforeHandle
      |-- ChannelInterceptor.postSend         |-- MessageHandler.handleMessage
      |-- ChannelInterceptor.afterSendCompletion
      |                                       |-- ExecutorChannelInterceptor.afterMessageHandled
      |<-- send() returns                     |
```

Đây là hai luồng callback có thể chạy đồng thời. Sơ đồ thể hiện ranh giới xử lý, không cam kết worker luôn bắt đầu sau `afterSendCompletion`. Executor có thể bắt đầu task ngay khi nhận lệnh submit, trong lúc thread producer vẫn đang hoàn tất callback sau gửi.

Do đó:

- `ChannelInterceptor.postSend` không phải callback báo handler đã xử lý xong.
- `ChannelInterceptor.afterSendCompletion` cũng không phải callback kết thúc xử lý nghiệp vụ bất đồng bộ.
- Muốn quan sát thời điểm handler bắt đầu/kết thúc, dùng `ExecutorChannelInterceptor.beforeHandle` và `afterMessageHandled`.
- Muốn biết kết quả nghiệp vụ đã được lưu hay chưa, cần acknowledgement hoặc trạng thái ở tầng ứng dụng; interceptor không tự cung cấp bảo đảm đó.

### Luồng đồng bộ khi không có executor

`ExecutorSubscribableChannel()` không nhận executor. Trong trường hợp này, channel thực thi task trực tiếp trong thread gọi `send()`:

```text
Producer thread
      |
      |-- ChannelInterceptor.preSend
      |-- ExecutorChannelInterceptor.beforeHandle
      |-- MessageHandler.handleMessage
      |-- ExecutorChannelInterceptor.afterMessageHandled
      |-- ChannelInterceptor.postSend
      |-- ChannelInterceptor.afterSendCompletion
      |-- send() returns
```

Vì vậy, không thể chỉ nhìn tên `ExecutorChannelInterceptor` rồi kết luận callback luôn chạy trên một thread pool. Thread thực tế phụ thuộc cách channel dispatch task.

## 3. Ví dụ Java 17+: quan sát thread của từng callback

Ví dụ dưới đây đăng ký một `ChannelInterceptor` và một `ExecutorChannelInterceptor` trên cùng `ExecutorSubscribableChannel`. Executor dùng thread tên `message-worker`. Một `CountDownLatch` giữ handler lại cho đến khi thread gửi đã nhận kết quả `send()`, giúp output dễ quan sát và ổn định.

Tạo file `src/main/java/InterceptorThreadDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.ExecutorChannelInterceptor;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class InterceptorThreadDemo {

    private static void log(String event) {
        System.out.println(
                event + " [" + Thread.currentThread().getName() + "]");
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor(task ->
                new Thread(task, "message-worker"));

        CountDownLatch allowHandler = new CountDownLatch(1);
        CountDownLatch handlerFinished = new CountDownLatch(1);

        ExecutorSubscribableChannel asyncChannel =
                new ExecutorSubscribableChannel(executor);

        // Callback cấp channel: chạy trong thread gọi send().
        asyncChannel.addInterceptor(new ChannelInterceptor() {
            @Override
            public Message<?> preSend(
                    Message<?> message, MessageChannel channel) {
                log("ChannelInterceptor.preSend");
                return message;
            }

            @Override
            public void postSend(
                    Message<?> message,
                    MessageChannel channel,
                    boolean sent) {
                log("ChannelInterceptor.postSend sent=" + sent);
            }

            @Override
            public void afterSendCompletion(
                    Message<?> message,
                    MessageChannel channel,
                    boolean sent,
                    Exception ex) {
                log("ChannelInterceptor.afterSendCompletion ex="
                        + (ex == null ? "null" : ex.getClass().getSimpleName()));
            }
        });

        // Callback bao quanh handler: chạy trong thread thực thi SendTask.
        asyncChannel.addInterceptor(new ExecutorChannelInterceptor() {
            @Override
            public Message<?> beforeHandle(
                    Message<?> message,
                    MessageChannel channel,
                    MessageHandler handler) {
                try {
                    allowHandler.await(2, TimeUnit.SECONDS);
                }
                catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return null;
                }

                log("ExecutorChannelInterceptor.beforeHandle");
                return message;
            }

            @Override
            public void afterMessageHandled(
                    Message<?> message,
                    MessageChannel channel,
                    MessageHandler handler,
                    Exception ex) {
                log("ExecutorChannelInterceptor.afterMessageHandled ex="
                        + (ex == null ? "null" : ex.getClass().getSimpleName()));
                handlerFinished.countDown();
            }
        });

        asyncChannel.subscribe(message ->
                log("handler.handleMessage"));

        log("caller.beforeSend");
        boolean sent = asyncChannel.send(
                MessageBuilder.withPayload("order-created").build());

        log("caller.sendReturned sent=" + sent);
        allowHandler.countDown();

        if (!handlerFinished.await(2, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Handler did not finish");
        }

        executor.shutdown();
        executor.awaitTermination(2, TimeUnit.SECONDS);

        // Không cấu hình executor: task chạy inline trong thread gọi send().
        ExecutorSubscribableChannel inlineChannel =
                new ExecutorSubscribableChannel();

        inlineChannel.addInterceptor(new ExecutorChannelInterceptor() {
            @Override
            public Message<?> beforeHandle(
                    Message<?> message,
                    MessageChannel channel,
                    MessageHandler handler) {
                log("inline.beforeHandle");
                return message;
            }

            @Override
            public void afterMessageHandled(
                    Message<?> message,
                    MessageChannel channel,
                    MessageHandler handler,
                    Exception ex) {
                log("inline.afterMessageHandled");
            }
        });

        inlineChannel.subscribe(message -> log("inline.handler"));
        inlineChannel.send(
                MessageBuilder.withPayload("inline-event").build());
    }
}
```

Tạo `pom.xml` ở thư mục gốc của project Maven:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>interceptor-thread-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>7.0.10</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>InterceptorThreadDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q clean compile exec:java
```

Kết quả stdout:

```text
caller.beforeSend [InterceptorThreadDemo.main()]
ChannelInterceptor.preSend [InterceptorThreadDemo.main()]
ChannelInterceptor.postSend sent=true [InterceptorThreadDemo.main()]
ChannelInterceptor.afterSendCompletion ex=null [InterceptorThreadDemo.main()]
caller.sendReturned sent=true [InterceptorThreadDemo.main()]
ExecutorChannelInterceptor.beforeHandle [message-worker]
handler.handleMessage [message-worker]
ExecutorChannelInterceptor.afterMessageHandled ex=null [message-worker]
inline.beforeHandle [InterceptorThreadDemo.main()]
inline.handler [InterceptorThreadDemo.main()]
inline.afterMessageHandled [InterceptorThreadDemo.main()]
```

Trong phần đầu, ba callback `ChannelInterceptor` chạy trên thread gọi `send()`; ba dòng liên quan đến handler chạy trên `message-worker`. Phần cuối dùng channel không có executor, nên `beforeHandle`, handler và `afterMessageHandled` đều chạy trên thread main.

Latch chỉ được dùng để tạo thứ tự output xác định cho ví dụ. Trong ứng dụng thực tế, không nên block `beforeHandle` như vậy.

## 4. Thứ tự và ý nghĩa callback

### Vòng đời ở cấp channel

Đối với thao tác gửi thông thường:

1. `preSend` chạy trước khi channel thực hiện việc gửi.
2. Nếu message được tiếp tục gửi, channel gọi logic gửi nội bộ.
3. `postSend` nhận kết quả boolean của logic gửi.
4. `afterSendCompletion` được gọi khi vòng đời gửi kết thúc, kể cả khi logic gửi phát sinh exception.

Nếu `preSend` trả về `null`, message bị chặn và không được chuyển đến handler. Vì vậy, đừng dùng `postSend` như một bộ đếm duy nhất cho mọi message producer từng tạo; hãy tính cả khả năng interceptor từ chối message.

### Vòng đời quanh handler

Với `ExecutorSubscribableChannel`, mỗi subscriber nhận một task xử lý. Các `ExecutorChannelInterceptor` được gọi theo thứ tự đăng ký ở giai đoạn `beforeHandle`. Callback `afterMessageHandled` được gọi theo thứ tự ngược lại để hoàn tất các interceptor đã tham gia.

`beforeHandle` có thể trả về message đã sửa đổi để handler nhận message đó. Nếu trả về `null`, handler bị bỏ qua. `afterMessageHandled` nhận exception nếu handler thất bại, giúp đo thời gian xử lý, ghi nhận lỗi hoặc kết thúc context đã tạo ở `beforeHandle`.

Nếu một channel có nhiều subscriber, callback executor-specific được thực hiện cho từng handler/task. Vì vậy một message gửi vào channel có thể tạo nhiều cặp `beforeHandle` / `afterMessageHandled`.

## 5. Các tình huống làm thay đổi thread thực thi

### Không có executor

`new ExecutorSubscribableChannel()` chạy task trực tiếp trong thread gọi `send()`. Các callback executor-specific và handler cùng thread với producer.

### Executor chạy task bất đồng bộ

Với `new ExecutorSubscribableChannel(executor)`, executor quyết định thread thực thi. Nếu executor dùng thread pool, handler và hai callback executor-specific thường chạy trên một worker thread của pool.

### Executor chạy inline hoặc CallerRunsPolicy

Một executor có thể thực thi task ngay trong thread gọi `execute`, ví dụ direct executor hoặc `ThreadPoolExecutor.CallerRunsPolicy` khi pool bão hòa. Khi đó callback executor-specific và handler lại chạy trên caller thread.

Trong implementation `ExecutorSubscribableChannel` của Spring Framework 7.0.10, nếu không có executor hoặc việc submit bị `RejectedExecutionException`, task cũng được chạy trực tiếp trong thread gửi. Do đó, không nên xem tên channel là bảo đảm tuyệt đối rằng handler luôn ở một worker thread.

### Nhiều handler và thứ tự xử lý

Nếu channel có nhiều subscriber, từng handler có thể được dispatch thành task riêng. Không nên giả định tất cả handler chạy tuần tự hoặc cùng một worker thread. Nếu thứ tự nghiệp vụ quan trọng, cần thiết kế channel, executor và cơ chế đồng bộ/partition phù hợp.

## 6. Xử lý lỗi ở đúng tầng

Hai loại interceptor quan sát hai phạm vi lỗi khác nhau:

- `ChannelInterceptor.afterSendCompletion` quan sát lỗi trong vòng đời gửi ở cấp channel. Với dispatch bất đồng bộ, task có thể đã được executor nhận thành công nên callback này có thể nhận `ex=null` dù handler thất bại sau đó.
- `ExecutorChannelInterceptor.afterMessageHandled` quan sát lỗi phát sinh khi một handler xử lý task. Tham số `ex` cho biết handler hoàn tất bình thường hay có lỗi.

Với executor bất đồng bộ, exception trong handler thường xảy ra trên worker thread sau khi `send()` đã trả về. Producer không thể chỉ dựa vào try/catch quanh `channel.send()` để bắt mọi lỗi handler. Hãy cấu hình logging, error handling hoặc luồng thông báo lỗi ở tầng phù hợp.

Không nên ném exception mới từ callback `afterMessageHandled` để thay thế lỗi gốc. Callback này chủ yếu phục vụ quan sát và dọn dẹp; giữ logic xử lý lỗi rõ ràng để không che mất nguyên nhân ban đầu.

## 7. Thread safety và context propagation

Interceptor có thể được dùng chung bởi nhiều thread và nhiều message. Vì vậy:

- Không lưu trạng thái riêng của một message vào field mutable của interceptor nếu không có đồng bộ.
- Đưa correlation ID, trace ID hoặc thông tin cần thiết vào message headers khi có thể.
- Nếu cần tạo context ở `beforeHandle` và dọn context ở `afterMessageHandled`, bảo đảm luôn dọn kể cả khi handler thất bại.
- Không giả định `ThreadLocal`, MDC logging context hoặc security context tự động được truyền từ producer sang executor worker.
- Nếu cần truyền context qua executor, cấu hình executor có cơ chế propagation phù hợp, chẳng hạn `TaskDecorator` với `ThreadPoolTaskExecutor`, và luôn khôi phục trạng thái thread sau khi task kết thúc.

Không giữ một transaction hoặc request-scoped object chỉ dựa trên việc hai callback có tên liên quan đến cùng message. Với executor bất đồng bộ, chúng có thể chạy ở thread khác và ngoài transaction/request context ban đầu.

## 8. Chọn interceptor theo nhu cầu

| Nhu cầu | Nên dùng | Lý do |
| --- | --- | --- |
| Kiểm tra hoặc thay message trước khi channel gửi | `ChannelInterceptor.preSend` | Chạy tại ranh giới gửi |
| Ghi nhận channel đã chấp nhận hay từ chối message | `ChannelInterceptor.postSend` | Có kết quả boolean `sent` |
| Dọn context sau thao tác gửi | `ChannelInterceptor.afterSendCompletion` | Kết thúc vòng đời gửi |
| Quan sát handler bắt đầu xử lý | `ExecutorChannelInterceptor.beforeHandle` | Chạy sát thời điểm gọi handler |
| Đo thời gian handler xử lý | Cặp `beforeHandle` và `afterMessageHandled` | Bao quanh xử lý thực tế |
| Ghi nhận exception của handler | `ExecutorChannelInterceptor.afterMessageHandled` | Nhận exception của lần xử lý handler |
| Kiểm soát thao tác nhận trên pollable channel | Các callback receive của `ChannelInterceptor` | Bao quanh `receive()` |

Nếu chỉ cần log producer gửi message, `ChannelInterceptor` là đủ. Nếu cần đo thời gian hoặc xử lý context quanh từng handler trên `ExecutorSubscribableChannel`, dùng `ExecutorChannelInterceptor`.

## 9. Lỗi thường gặp

1. **Cho rằng `ChannelInterceptor.postSend` chạy sau khi handler hoàn tất.** Với executor bất đồng bộ, nó chỉ chạy sau thao tác dispatch/gửi nội bộ.
2. **Cho rằng `afterSendCompletion` là callback hoàn tất xử lý message.** Nó kết thúc vòng đời gửi của channel, không phải vòng đời handler bất đồng bộ.
3. **Cho rằng `ExecutorChannelInterceptor` luôn chạy trên thread pool.** Không có executor, direct executor hoặc rejection fallback có thể chạy inline.
4. **Dùng `ExecutorChannelInterceptor` trên channel không hỗ trợ executor-specific callbacks.** Các callback bổ sung chỉ được gọi bởi implementation có tích hợp cơ chế này.
5. **Không xử lý message trả về từ `beforeHandle`.** Trả về message mới sẽ thay message đưa vào handler; trả `null` sẽ bỏ qua handler.
6. **Dùng `preSend` để đo thời gian handler.** Khoảng thời gian từ `preSend` đến `afterSendCompletion` không đại diện cho thời gian xử lý bất đồng bộ.
7. **Lưu dữ liệu message trong field interceptor không thread-safe.** Nhiều task có thể cùng truy cập interceptor.
8. **Giả định MDC hoặc ThreadLocal tự truyền sang worker.** Cần cấu hình context propagation và dọn trạng thái sau task.
9. **Dùng try/catch quanh `send()` để bắt lỗi handler bất đồng bộ.** Lỗi handler có thể phát sinh sau khi producer đã nhận kết quả gửi.

## 10. Checklist triển khai

- Xác định channel đang dùng có executor hay chạy inline.
- Dùng `ChannelInterceptor` cho các callback ở cấp gửi/nhận.
- Dùng `ExecutorChannelInterceptor` khi cần hook quanh từng handler.
- Đặt log thread name trong môi trường kiểm thử để xác nhận giả định về luồng.
- Không coi `postSend` hoặc `afterSendCompletion` là xác nhận handler đã hoàn tất.
- Xử lý kết quả `sent` và exception đúng tầng.
- Bảo đảm interceptor thread-safe và không giữ state theo message trong field dùng chung.
- Truyền trace/security context qua executor bằng cơ chế rõ ràng.
- Kiểm thử cả trường hợp executor bất đồng bộ và channel chạy inline.

## 11. Tài liệu tham khảo

- [Spring Framework – ChannelInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [Spring Framework – ExecutorChannelInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ExecutorChannelInterceptor.html)
- [Spring Framework – ExecutorSubscribableChannel Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html)
- [Spring Framework – AbstractMessageChannel Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/AbstractMessageChannel.html)
- [Spring Framework – MessageHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHandler.html)
