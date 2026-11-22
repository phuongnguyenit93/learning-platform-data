# ExecutorChannelInterceptor trước và sau thực thi MessageHandler

Trong Spring Messaging, một message được gửi qua channel và có thể được phân phối đến một hoặc nhiều MessageHandler. Với channel sử dụng Executor, việc gửi message và việc handler thực sự xử lý message có thể diễn ra ở hai thời điểm và hai thread khác nhau.

ExecutorChannelInterceptor bổ sung hai callback nằm ngay quanh lần gọi một MessageHandler cụ thể:

- beforeHandle chạy trong task xử lý, ngay trước khi gọi handler. Nó có thể giữ nguyên message, trả về message mới hoặc trả về null để bỏ qua handler đó.
- afterMessageHandled chạy sau khi handler kết thúc, dù thành công hay ném exception. Callback nhận exception nếu handler thất bại và phù hợp để dọn dẹp tài nguyên hoặc khôi phục context.

Điểm quan trọng là interceptor này làm việc ở ranh giới **mỗi handler invocation**. Nó không chỉ bao quanh thao tác send() của channel.

## 1. ExecutorChannelInterceptor là gì?

ExecutorChannelInterceptor thuộc package org.springframework.messaging.support và mở rộng ChannelInterceptor.

Hai method chính:

~~~java
Message<?> beforeHandle(
        Message<?> message,
        MessageChannel channel,
        MessageHandler handler
);

void afterMessageHandled(
        Message<?> message,
        MessageChannel channel,
        MessageHandler handler,
        Exception ex
);
~~~

Các method có implementation mặc định nên class triển khai có thể chỉ override callback cần dùng.

| Callback | Thời điểm | Giá trị trả về / tham số quan trọng |
|---|---|---|
| beforeHandle | Ngay trước MessageHandler.handleMessage | Trả message đầu vào, message mới hoặc null |
| afterMessageHandled | Sau khi handler kết thúc | ex là null nếu handler không ném exception; có exception nếu xử lý thất bại |

Interface được hỗ trợ bởi các MessageChannel có thể cấu hình Executor. Trong Spring Framework, ExecutorSubscribableChannel là implementation tiêu biểu.

Khi ExecutorSubscribableChannel có nhiều subscriber, mỗi subscriber được gọi trong một task xử lý riêng. Vì vậy beforeHandle và afterMessageHandled được gọi theo từng handler, không chỉ một lần cho toàn bộ lần gửi message.

## 2. Phân biệt với ChannelInterceptor

ChannelInterceptor và ExecutorChannelInterceptor đều liên quan đến MessageChannel, nhưng chúng quan sát hai giai đoạn khác nhau.

ChannelInterceptor tập trung vào vòng đời gửi/nhận ở cấp channel, với các callback như:

- preSend: chạy trước khi channel gửi message; có thể trả message mới hoặc null để chặn việc gửi.
- postSend: chạy sau khi channel hoàn tất thao tác dispatch ở cấp channel.
- afterSendCompletion: callback hoàn tất sau giai đoạn gửi, kể cả khi có lỗi.
- preReceive, postReceive và afterReceiveCompletion: phục vụ các channel hỗ trợ nhận bằng polling.

ExecutorChannelInterceptor tập trung vào lần gọi MessageHandler bên trong task của Executor:

- beforeHandle: chuẩn bị ngay trước khi handler chạy.
- afterMessageHandled: dọn dẹp ngay sau khi handler chạy.

| Câu hỏi | ChannelInterceptor | ExecutorChannelInterceptor |
|---|---|---|
| Quan sát điều gì? | Việc gửi/nhận qua channel | Việc gọi một subscriber handler |
| Callback tiêu biểu | preSend, postSend, afterSendCompletion | beforeHandle, afterMessageHandled |
| Có biết handler cụ thể đang được gọi? | Không phải trọng tâm của callback | Có, nhận MessageHandler |
| Chạy ở đâu? | Trong luồng gửi/nhận channel | Trong task thực thi handler; thường là executor thread nếu channel có Executor |
| Dùng cho việc gì? | Validate, sửa hoặc từ chối message ở cấp channel | Context propagation, đo thời gian và cleanup quanh handler |

Ví dụ: preSend có thể từ chối message trước khi channel dispatch. beforeHandle có thể bỏ qua một handler cụ thể sau khi task đã được tạo. Hai quyết định này xảy ra ở các giai đoạn khác nhau.

## 3. Vòng đời xử lý trong ExecutorSubscribableChannel

Khi ứng dụng gọi send(message), channel dispatch message đến các subscriber. Nếu cấu hình Executor, mỗi handler được gọi trong một task do Executor thực thi.

Luồng tổng quát:

~~~text
Producer
   |
   | channel.send(message)
   v
ChannelInterceptor.preSend
   |
   v
ExecutorSubscribableChannel
   |
   +---- tạo task cho Handler A
   |          |
   |          v
   |    beforeHandle(...)
   |          |
   |          v
   |    Handler A.handleMessage(...)
   |          |
   |          v
   |    afterMessageHandled(...)
   |
   +---- tạo task cho Handler B
              |
              v
        beforeHandle(...)
              |
              v
        Handler B.handleMessage(...)
              |
              v
        afterMessageHandled(...)

Channel-level postSend / afterSendCompletion
diễn ra quanh thao tác dispatch của channel.
~~~

Với executor nhiều thread, task của các subscriber có thể chạy đồng thời. Không có bảo đảm mọi handler hoàn tất theo cùng thứ tự chúng được đăng ký. Thứ tự thực thi giữa các task phụ thuộc Executor và tải hệ thống.

Nếu ExecutorSubscribableChannel được tạo mà không truyền Executor, task chạy trực tiếp trên thread gọi send(). Một Executor thực thi Runnable ngay lập tức cũng có thể giữ xử lý trên caller thread. Vì vậy, không nên giả định callback luôn chạy bất đồng bộ chỉ dựa vào tên interface.

### 3.1. Thứ tự các interceptor

Với một handler invocation:

1. beforeHandle được gọi theo thứ tự interceptor được đăng ký.
2. MessageHandler.handleMessage được gọi với message cuối cùng mà chuỗi beforeHandle trả về.
3. afterMessageHandled được gọi theo thứ tự ngược lại đối với các interceptor đã hoàn thành beforeHandle và trả về message khác null.

Thứ tự ngược giúp cleanup theo kiểu stack: tài nguyên được mở ở interceptor ngoài cùng trước, rồi đóng theo thứ tự ngược sau khi handler kết thúc.

### 3.2. Một message có thể tạo nhiều chuỗi callback

Giả sử channel có ba subscriber. Mỗi subscriber có một task và một chuỗi callback riêng. Nếu handler A xử lý thành công nhưng handler B ném exception, afterMessageHandled của A nhận ex=null còn callback của B nhận exception tương ứng.

Không dùng một biến instance mutable duy nhất để lưu trạng thái của từng message hoặc handler invocation. Nhiều task có thể chạy đồng thời trên cùng một interceptor instance.

## 4. beforeHandle: chuẩn bị message trước khi gọi handler

beforeHandle nhận ba tham số:

- message: message sắp được handler xử lý.
- channel: channel đã dispatch message đến handler.
- handler: subscriber cụ thể sắp được gọi.

Method có thể thực hiện ba lựa chọn.

### 4.1. Trả lại message ban đầu

~~~java
@Override
public Message<?> beforeHandle(
        Message<?> message,
        MessageChannel channel,
        MessageHandler handler) {

    return message;
}
~~~

Đây là cách dùng khi interceptor chỉ cần quan sát hoặc thiết lập context, không cần thay đổi payload hay header.

### 4.2. Trả về message mới

Nếu cần bổ sung metadata cho handler, tạo message mới bằng MessageBuilder:

~~~java
@Override
public Message<?> beforeHandle(
        Message<?> message,
        MessageChannel channel,
        MessageHandler handler) {

    return MessageBuilder
            .fromMessage(message)
            .setHeader("appHandlerStage", "before")
            .build();
}
~~~

Handler nhận message mới. Message gốc không bị sửa trực tiếp vì MessageHeaders của Spring là immutable.

Việc thay message ở đây áp dụng cho task của handler hiện tại. Nếu channel có nhiều subscriber, mỗi task có thể đi qua chuỗi interceptor riêng và nhận một message đã biến đổi riêng.

Không nên dùng beforeHandle để thay đổi payload theo cách khiến các subscriber khác nhận dữ liệu khác ngoài ý muốn. Hãy xác định rõ việc biến đổi có thuộc contract của từng handler hay không.

### 4.3. Trả về null để bỏ qua handler

~~~java
@Override
public Message<?> beforeHandle(
        Message<?> message,
        MessageChannel channel,
        MessageHandler handler) {

    if (!isAllowed(message, handler)) {
        return null;
    }

    return message;
}
~~~

Khi trả về null, MessageHandler tương ứng không được gọi. Đây là cơ chế bỏ qua một handler cụ thể trong chuỗi dispatch.

Cần phân biệt với preSend trả về null:

- preSend trả null: channel không tiếp tục gửi message.
- beforeHandle trả null: task không gọi handler đang xét; những subscriber khác vẫn có thể được xử lý.

Trả null không có nghĩa message tự động được retry, đưa vào dead-letter queue hoặc gửi lại sau. Nếu cần retry hoặc xử lý lỗi, phải thiết kế cơ chế riêng.

Nếu một interceptor trước đó đã chạy beforeHandle thành công, Spring gọi afterMessageHandled cho interceptor trước đó để nó có thể cleanup. Interceptor trả null không nhận callback afterMessageHandled của chính nó, và các interceptor phía sau không được gọi.

## 5. afterMessageHandled: cleanup sau khi handler kết thúc

afterMessageHandled nhận message đã được chuỗi beforeHandle chuẩn bị, channel, handler và exception nếu có.

Ví dụ:

~~~java
@Override
public void afterMessageHandled(
        Message<?> message,
        MessageChannel channel,
        MessageHandler handler,
        Exception ex) {

    if (ex == null) {
        recordSuccess(handler);
    }
    else {
        recordFailure(handler, ex);
    }
}
~~~

Callback được gọi sau khi handler kết thúc dù handler thành công hay thất bại, miễn là beforeHandle của interceptor đã hoàn tất và trả về message.

Các công việc phù hợp:

- Dừng timer đã bắt đầu ở beforeHandle.
- Ghi metric thành công/thất bại theo handler.
- Khôi phục hoặc xóa MDC/logging context.
- Khôi phục SecurityContext hoặc context gắn với thread.
- Giải phóng tài nguyên tạm đã được mở ở beforeHandle.
- Ghi nhận exception để quan sát và chẩn đoán.

Không dùng afterMessageHandled để giả định transaction nghiệp vụ đã commit hoặc message đã được broker xác nhận. Callback chỉ cho biết lần gọi MessageHandler đã kết thúc; transaction và acknowledgement có thể được quản lý ở tầng khác.

Không ném exception từ cleanup callback. ExecutorSubscribableChannel xử lý lỗi phát sinh trong callback cleanup bằng cách ghi log; lỗi cleanup không nên làm hỏng thêm luồng dispatch.

## 6. Ví dụ Java 17: theo dõi trước và sau handler

Ví dụ hoàn chỉnh sau sử dụng ExecutorSubscribableChannel với một single-thread executor. CountDownLatch giữ chương trình chạy đến khi callback afterMessageHandled hoàn tất.

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.ExecutorChannelInterceptor;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class ExecutorChannelInterceptorDemo {

    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            CountDownLatch completed = new CountDownLatch(1);
            ExecutorSubscribableChannel channel =
                    new ExecutorSubscribableChannel(executor);

            channel.addInterceptor(new ExecutorChannelInterceptor() {

                @Override
                public Message<?> beforeHandle(
                        Message<?> message,
                        MessageChannel channel,
                        MessageHandler handler) {

                    System.out.println(
                            "beforeHandle: " + message.getPayload()
                    );
                    return message;
                }

                @Override
                public void afterMessageHandled(
                        Message<?> message,
                        MessageChannel channel,
                        MessageHandler handler,
                        Exception ex) {

                    System.out.println(
                            "afterMessageHandled: "
                                    + (ex == null ? "success" : "failed")
                    );
                    completed.countDown();
                }
            });

            channel.subscribe(message ->
                    System.out.println(
                            "handleMessage: " + message.getPayload()
                    )
            );

            channel.send(
                    MessageBuilder.withPayload("order-110").build()
            );

            if (!completed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Handler did not finish");
            }
        }
        finally {
            executor.shutdownNow();
        }
    }
}
~~~

Ví dụ cần dependency spring-messaging và các dependency transitive tương ứng của Spring Framework trên classpath. Có thể để Gradle hoặc Maven quản lý các dependency này.

Stdout:

~~~text
beforeHandle: order-110
handleMessage: order-110
afterMessageHandled: success
~~~

Ba dòng được in trong cùng task xử lý nên giữ đúng thứ tự. Chương trình chờ latch trước khi đóng executor, nhờ đó không kết thúc trước callback sau handler.

## 7. Xử lý exception của MessageHandler

Nếu handler ném exception, afterMessageHandled vẫn được gọi và nhận exception trong tham số ex.

Ví dụ phần callback:

~~~java
@Override
public void afterMessageHandled(
        Message<?> message,
        MessageChannel channel,
        MessageHandler handler,
        Exception ex) {

    if (ex != null) {
        logger.error(
                "Handler {} failed for message {}",
                handler,
                message.getHeaders().getId(),
                ex
        );
        return;
    }

    logger.debug(
            "Handler {} completed for message {}",
            handler,
            message.getHeaders().getId()
    );
}
~~~

Đây là nơi phù hợp để ghi nhận lỗi theo handler và message ID. Cần cân nhắc dữ liệu nhạy cảm trước khi log payload hoặc toàn bộ headers.

### 7.1. Exception và send() là hai thời điểm khác nhau

Với executor bất đồng bộ:

1. Producer gọi channel.send(message).
2. Channel dispatch hoặc submit các task.
3. send() có thể trả về trước khi handler bắt đầu hoặc kết thúc.
4. Handler có thể ném exception sau khi producer đã nhận kết quả send().

Do đó, kết quả true từ send() chỉ cho biết channel đã chấp nhận thao tác gửi theo hợp đồng của channel. Nó không chứng minh tất cả handler đã xử lý thành công.

Không dựa vào try/catch quanh send() để bắt mọi lỗi xảy ra trong executor task. Hãy sử dụng error handling phù hợp với kiến trúc messaging, logging/metrics và cơ chế retry hoặc dead-letter nếu nghiệp vụ yêu cầu.

Khi channel chạy trực tiếp trên caller thread, exception có thể xuất hiện trong cùng call stack. Khi dùng executor bất đồng bộ, exception thường thuộc task của executor và được xử lý theo cơ chế của channel/executor.

### 7.2. Callback cleanup khi beforeHandle thất bại

Nếu beforeHandle ném exception, handler không được gọi. Các interceptor trước đó đã hoàn thành beforeHandle có thể nhận afterMessageHandled để cleanup.

Nếu beforeHandle trả null, handler cũng không được gọi. Spring cleanup những interceptor đã chạy thành công trước interceptor trả null. Callback afterMessageHandled chỉ được gọi cho interceptor có beforeHandle trả về một message khác null.

Điều này quan trọng khi mỗi interceptor mở tài nguyên hoặc đặt context. Hãy chỉ coi cleanup của interceptor là hợp lệ khi chính interceptor đó đã hoàn thành bước khởi tạo tương ứng.

## 8. Context propagation qua executor thread

Một use case phổ biến là truyền context từ producer sang thread xử lý:

- Correlation ID để log các message cùng workflow.
- MDC để log có request/event context.
- SecurityContext đã được xác thực khi kiến trúc cho phép.
- Observation hoặc tracing context.
- Context tenant đã được server xác định.

Vì thread của executor có thể được tái sử dụng cho nhiều message, dữ liệu ThreadLocal không được dọn dẹp sẽ rò sang lần xử lý tiếp theo.

Mẫu xử lý:

1. Trong beforeHandle, đọc metadata đã được xác thực từ message.
2. Lưu lại context cũ của thread.
3. Cài context mới cho lần gọi handler hiện tại.
4. Trong afterMessageHandled, khôi phục context cũ hoặc xóa nếu trước đó không có.
5. Dùng cấu trúc theo stack nếu xử lý có thể lồng nhau trên cùng thread.

Không lưu trạng thái của từng message vào field thông thường của interceptor singleton. Các task có thể chạy đồng thời trên nhiều thread và ghi đè lẫn nhau. Dùng ThreadLocal với cleanup rõ ràng hoặc cơ chế context propagation chuyên biệt.

Đối với dữ liệu bảo mật, không tin header do client tự gửi. Chỉ propagate SecurityContext hoặc tenant sau khi danh tính đã được xác thực và kiểm tra quyền ở phía server.

## 9. Đo thời gian xử lý từng handler

ExecutorChannelInterceptor có cả điểm bắt đầu và kết thúc của một handler invocation, phù hợp để đo latency theo handler:

- beforeHandle: ghi nhận thời điểm bắt đầu.
- afterMessageHandled: tính thời gian kết thúc và ghi metric.
- Dùng handler type/name và trạng thái exception làm tag có giới hạn cardinality.
- Không dùng message ID, user ID hoặc order ID làm metric tag vì số lượng giá trị có thể tăng không giới hạn; các giá trị này phù hợp hơn với log hoặc trace.

Nếu nhiều handler cùng nhận một message, mỗi handler có một thời gian xử lý riêng. Metric nên phản ánh đúng phạm vi đó, không cộng nhầm thời gian chờ queue của toàn bộ luồng vào thời gian thực thi handler.

Để đo cả thời gian chờ executor, cần instrument tại nơi submit task hoặc dùng khả năng quan sát của Executor. beforeHandle chỉ chạy khi task đã bắt đầu thực thi, nên nó không đo được thời gian message nằm chờ trong queue trước đó.

## 10. Đăng ký ExecutorChannelInterceptor

Có thể đăng ký interceptor trực tiếp trên ExecutorSubscribableChannel:

~~~java
Executor executor = Executors.newFixedThreadPool(4);

ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel(executor);

channel.addInterceptor(new AuditExecutorChannelInterceptor());
channel.subscribe(handler);
~~~

Các cách đăng ký:

- addInterceptor(interceptor): thêm vào cuối danh sách interceptor.
- addInterceptor(index, interceptor): thêm tại vị trí chỉ định.
- setInterceptors(list): thay toàn bộ danh sách interceptor hiện tại.

Nên dùng addInterceptor khi chỉ bổ sung một interceptor để không vô tình xóa các interceptor đã được cấu hình. Nếu dùng ExecutorService, ứng dụng phải quản lý vòng đời và shutdown executor phù hợp.

Không phải mọi MessageChannel đều hỗ trợ ExecutorChannelInterceptor. Nếu channel không hỗ trợ cơ chế executor callback này, không thể giả định beforeHandle và afterMessageHandled sẽ chạy chỉ vì interceptor đã được tạo.

## 11. Lỗi thường gặp

### 11.1. Nghĩ afterMessageHandled chạy ngay sau send()

afterMessageHandled chạy sau handler invocation. Với executor bất đồng bộ, send() có thể đã trả về trước đó.

### 11.2. Dùng beforeHandle thay cho preSend

beforeHandle chỉ tác động đến handler cụ thể. Nếu muốn từ chối toàn bộ lần gửi ở cấp channel, hãy xem xét ChannelInterceptor.preSend.

### 11.3. Trả null và mong message được retry

null chỉ bỏ qua handler invocation. Retry cần một cơ chế riêng như retry template, broker redelivery hoặc error flow.

### 11.4. Giữ trạng thái trong field của interceptor

Một interceptor có thể phục vụ nhiều task đồng thời. Field mutable dùng chung dễ tạo race condition. Dùng state theo thread/task và luôn cleanup.

### 11.5. Không khôi phục ThreadLocal

Executor thread được tái sử dụng. Nếu không khôi phục hoặc xóa context trong afterMessageHandled, message tiếp theo có thể nhận nhầm correlation ID, principal hoặc tenant.

### 11.6. Đo latency từ postSend

postSend ở cấp channel không đại diện cho thời gian handler xử lý xong. Dùng beforeHandle và afterMessageHandled nếu cần đo thời gian thực thi handler.

### 11.7. Làm công việc nặng trong interceptor

Interceptor nằm trên đường xử lý message. Tránh gọi remote service, truy vấn database hoặc chờ I/O lâu trong callback. Giữ callback ngắn để không làm nghẽn executor.

## 12. Checklist khi triển khai

1. Xác nhận channel hỗ trợ ExecutorChannelInterceptor.
2. Xác định channel có Executor hay chạy trực tiếp trên caller thread.
3. Dùng preSend cho kiểm soát cấp channel và beforeHandle cho kiểm soát từng handler.
4. Chỉ trả null khi thật sự muốn bỏ qua handler tương ứng.
5. Xử lý ex trong afterMessageHandled và không để callback cleanup ném lỗi.
6. Dọn dẹp hoặc khôi phục toàn bộ ThreadLocal/context.
7. Không dùng field mutable để lưu state của từng message.
8. Đo riêng queue wait time và handler execution time.
9. Không coi send() thành công là handler đã xử lý thành công.
10. Kiểm thử nhiều subscriber, nhiều thread, handler exception, beforeHandle trả null và cleanup.
11. Quản lý vòng đời Executor và giới hạn tải của nó.
12. Dùng log/metric có cardinality phù hợp và không ghi dữ liệu nhạy cảm.

## 13. Tài liệu tham khảo

- [ExecutorChannelInterceptor — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/support/ExecutorChannelInterceptor.html)
- [ExecutorSubscribableChannel — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html)
- [ChannelInterceptor — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [MessageChannel — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/MessageChannel.html)

ExecutorChannelInterceptor phù hợp để chuẩn bị và dọn dẹp context quanh từng lần gọi MessageHandler. Hãy dùng nó cho những việc thuộc vòng đời thực thi handler, giữ logic ngắn gọn, quản lý trạng thái an toàn giữa các thread và thiết kế error handling riêng cho những lỗi xảy ra sau khi message đã được dispatch.