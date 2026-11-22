# Thứ tự interceptor, ngoại lệ và dọn dẹp tài nguyên

## 1. Vì sao thứ tự interceptor quan trọng?

`ChannelInterceptor` cho phép áp dụng hành vi dùng chung tại ranh giới `MessageChannel`: kiểm tra message, bổ sung metadata, ghi log, đo thời gian, từ chối message hoặc dọn dẹp context sau khi gửi/nhận. Một channel có thể đăng ký nhiều interceptor; vì vậy cần hiểu callback nào chạy trước, callback nào chạy sau và callback nào vẫn được gọi khi có lỗi.

Trong Spring Framework Messaging, `AbstractMessageChannel` điều phối chuỗi interceptor cho thao tác gửi. Các implementation channel có thể khác nhau về cách dispatch, nhưng thứ tự của các callback trong một lần `send()` được quản lý theo cùng một nguyên tắc: các bước mở chạy theo thứ tự đăng ký, còn bước hoàn tất chạy ngược lại.

## 2. Vòng đời của một lần gửi

Với hai interceptor A rồi B được đăng ký theo thứ tự đó, một lần gửi thành công có trình tự:

~~~text
Producer
  |
  v
A.preSend
  |
  v
B.preSend
  |
  v
channel.sendInternal(message, timeout)
  |
  v
A.postSend(message, sent)
  |
  v
B.postSend(message, sent)
  |
  v
B.afterSendCompletion(message, sent, ex)
  |
  v
A.afterSendCompletion(message, sent, ex)
~~~

Ba nhóm callback có nhiệm vụ khác nhau:

- **`preSend`** chạy trước khi channel thực sự gửi message. Interceptor có thể trả lại message đã biến đổi hoặc trả `null` để ngăn lần gửi.
- **`postSend`** chạy ngay sau khi thao tác gửi trả về. Tham số `sent` chính là kết quả boolean của lần gửi; callback này cũng chạy khi `sendInternal` trả `false`.
- **`afterSendCompletion`** chạy khi lần gửi hoàn tất, kể cả khi có exception, để interceptor dọn dẹp tài nguyên hoặc context đã tạo trong `preSend`.

`preSend` và `postSend` chạy theo thứ tự đăng ký. `afterSendCompletion` chạy theo thứ tự ngược, tương tự cách đóng các tài nguyên được mở theo kiểu lồng nhau. Nếu A chạy trước B để thiết lập context, B được dọn trước A.

## 3. Điều kiện gọi từng callback

| Callback | Khi nào được gọi? | Có thể ngăn luồng? |
| --- | --- | --- |
| `preSend` | Trước `sendInternal` | Trả `null` để hủy gửi; ném exception để báo lỗi |
| `postSend` | Sau khi `sendInternal` trả boolean | Không có giá trị trả về; exception có thể làm lần gửi thất bại |
| `afterSendCompletion` | Sau khi lần gửi hoàn tất hoặc gặp lỗi | Không thay đổi kết quả gửi; exception trong callback được framework ghi log |
| `preReceive` | Trước khi poll một `PollableChannel` | Trả `false` để không nhận message |
| `postReceive` | Sau khi nhận được message, trước khi trả cho caller | Trả `null` để dừng chuỗi interceptor nhận |
| `afterReceiveCompletion` | Khi lần receive hoàn tất, kể cả khi không có message hoặc có lỗi | Dùng để dọn dẹp context/tài nguyên |

`preReceive`, `postReceive` và `afterReceiveCompletion` chỉ áp dụng cho `PollableChannel`. `SubscribableChannel` dispatch message tới subscriber nên không có API `receive()` để các callback receive này can thiệp.

## 4. Ngoại lệ ở từng giai đoạn gửi

Không phải mọi callback đều chạy trong mọi tình huống. Cần phân biệt việc từ chối có chủ ý với exception:

| Tình huống | Điều xảy ra | Callback hoàn tất |
| --- | --- | --- |
| `preSend` trả message | Chuỗi tiếp tục tới interceptor kế tiếp rồi `sendInternal` | `afterSendCompletion` cho các interceptor đã hoàn thành `preSend`, theo thứ tự ngược |
| `preSend` trả `null` | Dừng chuỗi; `sendInternal` không chạy; `send()` trả `false` | Chỉ các interceptor trước interceptor từ chối được gọi `afterSendCompletion`; interceptor trả `null` không được gọi completion |
| `preSend` ném exception | Dừng chuỗi trước khi gửi | Các interceptor trước đó đã hoàn thành `preSend` được gọi completion; interceptor đang ném lỗi tự chịu trách nhiệm dọn phần tài nguyên đã mở trong callback của nó |
| `sendInternal` trả `false` | Message không được chấp nhận theo semantics của channel | `postSend(sent=false)`, sau đó completion ngược thứ tự với `ex=null` |
| `sendInternal` ném exception | `postSend` không chạy; lần gửi kết thúc bằng lỗi | Completion ngược thứ tự nhận exception |
| `postSend` ném exception | Chuỗi `postSend` dừng tại callback lỗi | Completion vẫn chạy cho các interceptor đã qua `preSend`; exception được truyền lên theo cơ chế của channel |
| `afterSendCompletion` ném exception | Framework ghi log lỗi callback completion | Không thay thế exception chính của lần gửi |

Điểm quan trọng: `afterSendCompletion` chỉ được gọi cho interceptor mà `preSend` đã hoàn thành thành công và trả về một `Message`. Nếu chính interceptor đang mở tài nguyên trong `preSend` rồi trả `null` hoặc ném exception, nó không thể trông chờ callback completion của chính mình.

Với `AbstractMessageChannel`, exception không phải `MessagingException` thường được bọc trong `MessageDeliveryException`. Nếu `sendInternal` trả `false`, `postSend` vẫn được gọi với `sent=false`; `false` không phải exception.

## 5. Dọn dẹp tài nguyên đúng cách

`afterSendCompletion` là nơi thích hợp để giải phóng tài nguyên gắn với lần gửi: khôi phục MDC, gỡ context tạm, đóng scope quan sát hoặc hoàn nguyên trạng thái đã đặt trong `preSend`.

Mẫu xử lý:

1. Trong `preSend`, xác thực điều kiện trước khi mở tài nguyên.
2. Nếu cần tạo context/tài nguyên, ghi nhận đủ thông tin để có thể khôi phục hoặc đóng nó.
3. Trả về message để framework đưa interceptor vào chuỗi completion.
4. Trong `afterSendCompletion`, giải phóng tài nguyên trong `try/finally` và khôi phục trạng thái trước đó.

Nếu `preSend` có thể trả `null` hoặc ném exception sau khi đã mở tài nguyên, callback đó phải tự dọn trong chính `preSend` trước khi trả về hoặc ném lỗi. Ví dụ:

~~~java
@Override
public Message<?> preSend(Message<?> message, MessageChannel channel) {
    openTemporaryScope();
    try {
        if (!isAllowed(message)) {
            closeTemporaryScope();
            return null;
        }
        return message;
    } catch (RuntimeException ex) {
        closeTemporaryScope();
        throw ex;
    }
}
~~~

Đây là mẫu minh họa; trong code thực tế nên dùng một helper scope có `close()` idempotent để tránh đóng hai lần khi có nhiều nhánh thoát.

### 5.1. Không giữ trạng thái của từng message trong field dùng chung

Interceptor thường là Spring singleton và có thể xử lý nhiều message đồng thời. Không lưu một `currentMessage`, `startTime` hoặc `resource` duy nhất trong field mutable rồi ghi đè ở mỗi `preSend`; các thread sẽ làm lẫn trạng thái của nhau.

Nếu cần đo thời gian, có thể lưu timestamp vào header mới hoặc dùng context theo từng lần gọi. Nếu dùng `ThreadLocal`/MDC, phải khôi phục giá trị cũ hoặc xóa đúng key trong completion callback. Với xử lý lồng nhau, cần lưu/khôi phục theo stack hoặc scope để không xóa context của lần gọi bên ngoài.

Không đặt I/O chậm, gọi service ngoài hoặc công việc có thể block lâu trong `afterSendCompletion`. Completion callback nằm trên đường gọi của `send()` và có thể làm tăng latency của producer. Callback nên ngắn, có giới hạn thời gian và không được để lỗi dọn dẹp che mất lỗi gốc.

## 6. Luồng nhận và thứ tự callback receive

Đối với `PollableChannel`, trình tự của một lần nhận là:

~~~text
Caller.receive()
  |
  v
A.preReceive
  |
  v
B.preReceive
  |
  v
Channel lấy message
  |
  v
A.postReceive
  |
  v
B.postReceive
  |
  v
B.afterReceiveCompletion
  |
  v
A.afterReceiveCompletion
~~~

Nếu `preReceive` trả `false`, channel không lấy message; completion chỉ chạy cho các interceptor trước đó đã trả `true`. Nếu `postReceive` trả `null`, các interceptor postReceive tiếp theo không được gọi, nhưng completion vẫn được dùng để kết thúc các interceptor đã tham gia lần receive.

Trong Spring Integration từ phiên bản 5.1, `postReceive` không được gọi khi poll không lấy được message. `afterReceiveCompletion` vẫn là callback để xử lý việc kết thúc lần receive, kể cả khi message là `null` hoặc có exception.

Không giả định thứ tự toàn cục giữa callback gửi và callback nhận. Với queue channel, sender và receiver có thể chạy trên các thread khác nhau. Nếu receiver đang chờ sẵn, `preReceive` có thể xảy ra trước `postSend`; nếu receiver poll sau khi sender trả về, `postSend` có thể xảy ra trước `preReceive`. Chỉ dựa vào thứ tự trong từng lời gọi: `preSend` trước `postSend`, và `preReceive` trước `postReceive`.

## 7. Channel bất đồng bộ: phân biệt hoàn tất gửi và hoàn tất handler

Với channel dispatch qua `Executor`, `send()` có thể trả về sau khi task được executor chấp nhận, trong khi handler chưa chạy xong. Vì vậy:

- `ChannelInterceptor.afterSendCompletion` hoàn tất vòng đời của thao tác `send()` ở phía sender. Nó không chứng minh handler đã xử lý xong.
- `ExecutorChannelInterceptor.beforeHandle` chạy bên trong task executor, ngay trước khi gọi `MessageHandler`.
- `ExecutorChannelInterceptor.afterMessageHandled` chạy bên trong task executor sau khi gọi handler, kể cả khi handler ném exception, nên phù hợp để dọn context gắn với thread xử lý.

`afterMessageHandled` chỉ được gọi cho interceptor mà `beforeHandle` đã hoàn thành và trả về message. Nếu `beforeHandle` trả `null` hoặc ném lỗi sau khi mở tài nguyên, interceptor đó phải tự dọn phần tài nguyên đã mở; các interceptor trước đó được completion theo thứ tự ngược.

Nếu cần đặt MDC, security context hoặc tenant context cho handler bất đồng bộ, hãy thiết lập trong `beforeHandle` và khôi phục/xóa trong `afterMessageHandled`. Dùng `afterSendCompletion` để dọn ThreadLocal của sender là sai thread và có thể để context rò rỉ trên worker thread.

## 8. Thứ tự đăng ký interceptor

Với interceptor cục bộ trên `InterceptableChannel`, thứ tự trong danh sách là thứ tự callback mở: `preSend`, `postSend`, `preReceive`, `postReceive`. Có thể cấu hình danh sách bằng `setInterceptors(...)`, thêm ở cuối bằng `addInterceptor(...)` hoặc chèn tại vị trí cụ thể bằng `addInterceptor(index, ...)`.

Trong Spring Integration, global channel interceptor có thêm quy tắc chèn tương đối với interceptor cục bộ: `order` âm được chèn trước các interceptor hiện có; `order` dương được chèn sau; giữa các global interceptor, giá trị `order` quyết định thứ tự. Đây là quy tắc cấu hình của Spring Integration, không phải thuộc tính tự động của mọi `ChannelInterceptor` trong Spring Framework thuần.

Không dựa vào thứ tự khởi tạo bean hoặc thứ tự quét component nếu cấu hình không quy định rõ. Hãy đặt thứ tự tường minh khi một interceptor phụ thuộc vào thay đổi do interceptor khác tạo ra.

## 9. Ví dụ Java 17: quan sát thứ tự và exception

Ví dụ dùng `AbstractMessageChannel` để minh họa hai interceptor A và B. Channel trả thành công với payload `ok` và ném lỗi với payload `fail`. Đây là ví dụ đồng bộ để thứ tự callback có thể quan sát chính xác; không mô phỏng executor hoặc broker.

Tạo Maven project:

~~~text
interceptor-lifecycle-demo/
  pom.xml
  src/main/java/com/example/messaging/InterceptorLifecycleDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>interceptor-lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.18</spring.version>
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

`src/main/java/com/example/messaging/InterceptorLifecycleDemo.java`:

~~~java
package com.example.messaging;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.messaging.support.AbstractMessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageBuilder;

public final class InterceptorLifecycleDemo {
    private InterceptorLifecycleDemo() {
    }

    private static final class DemoChannel extends AbstractMessageChannel {
        @Override
        protected boolean sendInternal(Message<?> message, long timeout) {
            System.out.println("sendInternal payload=" + message.getPayload());
            if ("fail".equals(message.getPayload())) {
                throw new IllegalStateException("simulated transport failure");
            }
            return true;
        }
    }

    private static ChannelInterceptor named(String name) {
        return new ChannelInterceptor() {
            @Override
            public Message<?> preSend(Message<?> message, MessageChannel channel) {
                System.out.println(name + ".preSend");
                return message;
            }

            @Override
            public void postSend(Message<?> message, MessageChannel channel, boolean sent) {
                System.out.println(name + ".postSend sent=" + sent);
            }

            @Override
            public void afterSendCompletion(
                    Message<?> message, MessageChannel channel, boolean sent, Exception ex) {
                String error = (ex == null ? "none" : ex.getClass().getSimpleName());
                System.out.println(name + ".afterSendCompletion sent=" + sent + " ex=" + error);
            }
        };
    }

    public static void main(String[] args) {
        DemoChannel channel = new DemoChannel();
        channel.addInterceptor(named("A"));
        channel.addInterceptor(named("B"));

        System.out.println("=== success ===");
        boolean sent = channel.send(MessageBuilder.withPayload("ok").build());
        System.out.println("sendResult=" + sent);

        System.out.println("=== failure ===");
        try {
            channel.send(MessageBuilder.withPayload("fail").build());
        } catch (MessageDeliveryException ex) {
            System.out.println("caught=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.InterceptorLifecycleDemo
~~~

Stdout:

~~~text
=== success ===
A.preSend
B.preSend
sendInternal payload=ok
A.postSend sent=true
B.postSend sent=true
B.afterSendCompletion sent=true ex=none
A.afterSendCompletion sent=true ex=none
sendResult=true
=== failure ===
A.preSend
B.preSend
sendInternal payload=fail
B.afterSendCompletion sent=false ex=IllegalStateException
A.afterSendCompletion sent=false ex=IllegalStateException
caught=MessageDeliveryException
~~~

Quan sát được:

- A và B chạy theo thứ tự đăng ký ở `preSend` và `postSend`.
- `afterSendCompletion` chạy B rồi A, tức thứ tự ngược.
- Khi `sendInternal` ném exception, `postSend` không chạy nhưng completion vẫn chạy với exception.
- `AbstractMessageChannel` bọc lỗi runtime không phải `MessagingException` thành `MessageDeliveryException` khi trả lỗi cho caller.

## 10. Những lỗi thường gặp

- **Dọn tài nguyên trong `postSend`:** callback này không chạy nếu `sendInternal` ném exception. Dùng `afterSendCompletion` cho cleanup của send.
- **Cho rằng completion luôn gọi trên mọi interceptor:** interceptor trả `null` hoặc ném lỗi trong `preSend` không nhận completion của chính nó; phải tự dọn phần tài nguyên đã mở.
- **Giải phóng theo cùng thứ tự mở:** completion chạy ngược thứ tự interceptor đã hoàn tất `preSend`/`preReceive`.
- **Coi `sent=true` là handler đã xong:** với executor channel, nó có thể chỉ có nghĩa task đã được chấp nhận.
- **Dọn context async ở sender thread:** dùng `ExecutorChannelInterceptor.afterMessageHandled` cho context của handler thread.
- **Giữ trạng thái từng message trong field singleton:** nhiều thread có thể ghi đè và làm lẫn dữ liệu.
- **Không khôi phục MDC/ThreadLocal cũ:** context của message trước có thể rò sang message sau trên cùng worker thread.
- **Nuốt exception trong interceptor:** lỗi validation hoặc delivery biến mất khỏi đường xử lý và khó điều tra.
- **Ném exception trong cleanup:** có thể làm nhiễu lỗi chính; framework ghi log exception từ completion, nhưng interceptor vẫn nên xử lý cleanup an toàn.
- **Giả định thứ tự send/receive toàn cục:** queue sender và receiver có thể chạy độc lập và xen kẽ.
- **Dựa vào thứ tự bean không được cấu hình:** thứ tự đăng ký phải được xác định rõ ở channel hoặc cấu hình global interceptor.

## 11. Checklist review

1. Interceptor được đăng ký theo thứ tự nào? Có phụ thuộc vào kết quả của interceptor trước không?
2. `preSend` có thể trả `null` hoặc ném exception sau khi đã mở tài nguyên không?
3. Có cleanup cục bộ cho các nhánh thoát sớm trong `preSend`/`preReceive` không?
4. `postSend` có được dùng đúng cho quan sát kết quả thay vì cleanup bắt buộc không?
5. `afterSendCompletion` có xử lý cả `sent=false` và `ex != null` không?
6. Completion có khôi phục trạng thái trước đó và không làm rò ThreadLocal/MDC không?
7. Có field mutable dùng chung lưu trạng thái theo message không?
8. Với `PollableChannel`, receive interceptor có xử lý trường hợp không có message không?
9. Với executor channel, context của handler được dọn trong `afterMessageHandled` chưa?
10. Exception từ handler, interceptor và cleanup được log/propagate theo chính sách nào?
11. Các callback có tránh I/O/blocking không cần thiết không?
12. Có test cho success, false, preSend reject, exception ở sendInternal và exception trong handler không?

## 12. Ghi nhớ

`preSend` chạy theo thứ tự đăng ký; `postSend` chạy sau khi send trả kết quả boolean; `afterSendCompletion` chạy ngược thứ tự cho các interceptor đã hoàn tất `preSend` và trả về message. Nếu `preSend` trả `null` hoặc ném lỗi, interceptor hiện tại phải tự dọn tài nguyên mà nó đã mở. Với pollable channel, `preReceive` và `postReceive` chạy theo thứ tự đăng ký, còn `afterReceiveCompletion` chạy ngược và là nơi dọn dẹp. Với executor channel, `afterSendCompletion` chỉ kết thúc lần gửi ở phía producer; `ExecutorChannelInterceptor.afterMessageHandled` mới kết thúc việc gọi handler trên worker thread. Hãy thiết kế cleanup theo đúng thread, đúng vòng đời và an toàn khi callback xảy ra trong cả nhánh thành công lẫn nhánh lỗi.

### Tài liệu tham khảo

- [Spring Framework 6.2.18 — ChannelInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [Spring Framework 6.2.18 — ExecutorChannelInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/ExecutorChannelInterceptor.html)
- [Spring Framework 6.2.18 — AbstractMessageChannel Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/AbstractMessageChannel.html)
- [Spring Integration — Channel Interceptors](https://docs.spring.io/spring-integration/reference/6.2/channel/interceptors.html)