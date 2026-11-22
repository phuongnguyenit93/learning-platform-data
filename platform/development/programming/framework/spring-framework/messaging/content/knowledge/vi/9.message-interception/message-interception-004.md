# postSend và afterSendCompletion trong thành công hoặc thất bại

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả vòng đời gửi Message qua một channel có đăng ký ChannelInterceptor.
- Phân biệt preSend, postSend và afterSendCompletion.
- Hiểu tham số sent và ex thể hiện những trạng thái khác nhau.
- Nhận biết trường hợp send trả về true, trả về false hoặc ném exception.
- Biết khi nào postSend được gọi và khi nào afterSendCompletion được gọi.
- Hiểu giới hạn của interceptor khi channel dispatch bất đồng bộ.
- Dùng afterSendCompletion để giải phóng tài nguyên theo đúng vòng đời.
- Viết interceptor an toàn khi nhiều thread cùng gửi Message.

## 1. ChannelInterceptor đứng ở đâu?

Trong Spring Messaging, MessageChannel là ranh giới gửi thông điệp. Một producer gọi send(Message), channel tiếp nhận và chuyển Message theo implementation. ChannelInterceptor cho phép quan sát hoặc can thiệp vào thao tác gửi/nhận tại ranh giới đó mà không phải sửa code của producer hay handler.

ChannelInterceptor thuộc package org.springframework.messaging.support. Nó cung cấp các callback cho quá trình gửi:

- **preSend:** chạy trước khi channel thực hiện thao tác gửi; có thể sửa Message hoặc chặn việc gửi.
- **postSend:** chạy ngay sau khi lời gọi gửi trả về bình thường; nhận boolean cho biết kết quả gửi.
- **afterSendCompletion:** chạy khi thao tác gửi kết thúc để cleanup; nhận cả kết quả sent và exception nếu có.

Một channel có hỗ trợ đăng ký interceptor thường triển khai InterceptableChannel. Các channel của Spring Framework và Spring Integration có thể cung cấp API addInterceptor để đăng ký.

~~~mermaid
flowchart TB
    A["Producer gọi send(message)"]
    B["preSend(message, channel)"]
    C{"preSend trả Message?"}
    D["Channel thực hiện send"]
    E{"send trả về bình thường?"}
    F["postSend(message, channel, sent)"]
    G["afterSendCompletion(message, channel, sent, null)"]
    H["afterSendCompletion(message, channel, sent, exception)"]
    I["send trả về boolean"]
    J["Send bị chặn trước channel"]

    A --> B --> C
    C -->|Có| D --> E
    C -->|Không, trả null| J
    E -->|Có| F --> G --> I
    E -->|Ném exception| H
~~~

Sơ đồ mô tả vòng đời gửi của một interceptor đã hoàn tất preSend thành công. Nếu preSend trả về null, thao tác gửi bị chặn và không có postSend cho interceptor đó; các interceptor trước đó đã hoàn tất preSend có thể vẫn nhận callback completion để dọn dẹp.

## 2. Ba callback cần phân biệt

### 2.1. preSend: trước khi gửi

Chữ ký:

~~~java
Message<?> preSend(Message<?> message, MessageChannel channel);
~~~

Callback nhận Message và channel đích. Nó có thể:

- Trả lại Message ban đầu để tiếp tục gửi.
- Tạo Message mới bằng MessageBuilder để bổ sung hoặc điều chỉnh headers.
- Trả về null để ngăn thao tác gửi thực sự xảy ra.
- Ném exception nếu phát hiện điều kiện không hợp lệ.

Ví dụ chặn một Message không có header bắt buộc:

~~~java
@Override
public Message<?> preSend(Message<?> message, MessageChannel channel) {
    if (!message.getHeaders().containsKey("eventType")) {
        return null;
    }
    return message;
}
~~~

Khi preSend trả về null, channel không gọi sendInternal cho Message đó và lời gọi send thường trả về false. Đây là một lần gửi bị interceptor chặn, không phải một Message đã được consumer xử lý thất bại.

### 2.2. postSend: ngay sau lời gọi gửi

Chữ ký:

~~~java
void postSend(Message<?> message, MessageChannel channel, boolean sent);
~~~

Callback này chạy ngay sau khi thao tác gửi của channel trả về một boolean. Tham số sent chính là kết quả boolean đó:

- sent=true: channel báo đã chấp nhận/gửi Message theo hợp đồng của implementation.
- sent=false: channel trả về bình thường nhưng không chấp nhận hoặc không gửi được Message trong điều kiện hiện tại.

postSend phù hợp để ghi nhận kết quả gửi, tăng counter hoặc phát metric. Nó không nhận exception vì callback này chỉ chạy khi thao tác gửi đã trả về bình thường.

Nếu phần gửi ném exception thay vì trả về boolean, postSend không được gọi cho lần gửi đó. Việc dọn dẹp vẫn được xử lý qua afterSendCompletion.

### 2.3. afterSendCompletion: cleanup sau khi thao tác kết thúc

Chữ ký:

~~~java
void afterSendCompletion(
        Message<?> message,
        MessageChannel channel,
        boolean sent,
        Exception ex
);
~~~

Callback này được thiết kế làm điểm hoàn tất sau thao tác gửi, kể cả khi có exception, để interceptor giải phóng tài nguyên hoặc hoàn tất công việc cleanup.

Hai tham số kết quả phải được đọc cùng nhau:

- sent cho biết kết quả boolean nếu thao tác gửi trả về bình thường; khi thao tác ném exception, giá trị này thường vẫn là false vì chưa có kết quả gửi thành công.
- ex là exception phát sinh trong quá trình gửi, nếu có; ex=null nghĩa là không có exception được truyền vào callback.

afterSendCompletion chỉ được gọi cho interceptor có preSend hoàn tất thành công và trả về một Message. Nếu preSend trả null, callback completion không được gọi cho chính interceptor đã chặn Message đó.

Không nên nhầm afterSendCompletion với callback “consumer đã xử lý xong”. Nó chỉ đánh dấu thao tác send của channel đã kết thúc.

## 3. Phân biệt ba trạng thái gửi

Một interceptor cần phân biệt ít nhất ba tình huống sau:

| Tình huống | send trả về | postSend | afterSendCompletion |
|---|---|---|---|
| Gửi được chấp nhận | true | Có, sent=true | Có, sent=true, ex=null |
| Channel trả về false | false | Có, sent=false | Có, sent=false, ex=null |
| Thao tác gửi ném exception | Không có boolean | Không chạy | Có, sent=false, ex chứa exception |

Đây là điểm quan trọng: **false và exception là hai kiểu thất bại khác nhau**.

- false là một kết quả bình thường của lời gọi send; producer có thể kiểm tra và quyết định retry, giảm tải hoặc ghi nhận việc từ chối.
- exception cho biết thao tác gửi không hoàn tất theo luồng bình thường. Ứng dụng cần phân loại exception và quyết định xử lý.
- true chỉ phản ánh việc channel chấp nhận Message theo implementation. Nó không bảo đảm handler đã hoàn tất nghiệp vụ hoặc broker đã lưu bền dữ liệu.

Với một channel bất đồng bộ, send có thể trả về true sau khi task được dispatch vào executor. Nếu handler lỗi sau đó trên worker thread, exception của handler thường không được truyền ngược về afterSendCompletion của thread gửi. Interceptor chỉ quan sát vòng đời gửi/dispatch của channel.

## 4. Thứ tự callback trong một lần gửi

Với một interceptor duy nhất, khi send trả về bình thường, thứ tự cơ bản là:

~~~text
preSend
channel thực hiện gửi
postSend
afterSendCompletion
send trả về caller
~~~

Nếu send trả về false, postSend vẫn được gọi với sent=false, sau đó afterSendCompletion nhận sent=false và ex=null.

Nếu thao tác gửi ném exception:

~~~text
preSend
channel thực hiện gửi
exception phát sinh
afterSendCompletion(sent=false, ex=exception)
exception được ném về caller
~~~

postSend không được gọi trong trường hợp này vì không có kết quả boolean trả về từ thao tác gửi.

Khi có nhiều interceptor:

- preSend được gọi theo thứ tự đăng ký.
- postSend được gọi sau thao tác gửi; việc triển khai channel quản lý thứ tự callback.
- afterSendCompletion được gọi theo thứ tự ngược với thứ tự preSend thành công, tương tự việc tháo stack tài nguyên theo chiều ngược lại.

Không nên dựa vào thứ tự giữa các thread producer/consumer khác nhau. Với channel bất đồng bộ, consumer có thể bắt đầu xử lý trước hoặc sau khi producer nhận callback postSend, tùy cơ chế dispatch và lịch chạy thread.

## 5. afterSendCompletion không đồng nghĩa với hoàn tất nghiệp vụ

Tên callback có thể khiến người đọc nghĩ rằng nó chạy sau khi consumer xử lý xong. Thực tế, callback gắn với lời gọi send trên MessageChannel.

Ví dụ với ExecutorSubscribableChannel:

1. Producer gọi send.
2. Channel giao task cho executor.
3. Executor chấp nhận task.
4. send trả về true.
5. postSend và afterSendCompletion chạy trên luồng gửi.
6. Handler có thể bắt đầu hoặc tiếp tục xử lý trên worker thread.

Vì thế, interceptor có thể ghi nhận channel đã chấp nhận Message, nhưng không thể kết luận rằng handler đã hoàn tất.

Nếu cần quan sát kết quả xử lý nghiệp vụ, hãy dùng cơ chế ở phía consumer như logging trong handler, error channel, acknowledgement, reply hoặc metric nghiệp vụ. Không dùng afterSendCompletion để thay thế acknowledgement.

## 6. Đăng ký interceptor vào channel

Các channel hỗ trợ interceptor cung cấp API đăng ký, thường là addInterceptor:

~~~java
DirectChannel channel = new DirectChannel();
channel.addInterceptor(new ChannelInterceptor() {
    @Override
    public void postSend(
            Message<?> message,
            MessageChannel channel,
            boolean sent) {
        System.out.println("sent=" + sent);
    }

    @Override
    public void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex) {
        System.out.println("completed");
    }
});
~~~

ChannelInterceptor trong các phiên bản Spring Framework hiện đại có các phương thức mặc định. Vì vậy, có thể chỉ override những callback cần dùng mà không phải viết lại toàn bộ interface.

Nếu cần logic áp dụng cho mọi channel trong ứng dụng Spring Integration, có thể xem xét global channel interceptor. Global interceptor cần được cấu hình theo cơ chế của Spring Integration; việc đăng ký trực tiếp bằng addInterceptor chỉ áp dụng cho channel cụ thể.

## 7. Ví dụ Java 17 chạy được: success, false và exception

Ví dụ dưới đây dùng DirectChannel và QueueChannel của Spring Integration để thể hiện ba kết quả gửi. Nó ghi log từ postSend và afterSendCompletion.

### 7.1. Cấu hình Maven

Tạo file pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>channel-interceptor-lifecycle</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>6.5.10</version>
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

### 7.2. Chương trình hoàn chỉnh

Tạo file src/main/java/demo/ChannelInterceptorLifecycleDemo.java:

~~~java
package demo;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageBuilder;

public class ChannelInterceptorLifecycleDemo {

    private static ChannelInterceptor loggingInterceptor(String label) {
        return new ChannelInterceptor() {
            @Override
            public void postSend(
                    Message<?> message,
                    MessageChannel channel,
                    boolean sent) {
                System.out.println(label + ".postSend.sent=" + sent);
            }

            @Override
            public void afterSendCompletion(
                    Message<?> message,
                    MessageChannel channel,
                    boolean sent,
                    Exception ex) {
                System.out.println(
                        label + ".afterSendCompletion.sent=" + sent
                );
                System.out.println(
                        label + ".afterSendCompletion.exceptionPresent="
                                + (ex != null)
                );
            }
        };
    }

    public static void main(String[] args) {
        demonstrateSuccess();
        demonstrateFalseResult();
        demonstrateException();
    }

    private static void demonstrateSuccess() {
        System.out.println("-- success --");

        DirectChannel channel = new DirectChannel();
        channel.addInterceptor(loggingInterceptor("success"));

        channel.subscribe(message ->
                System.out.println(
                        "handler.payload=" + message.getPayload()
                )
        );

        boolean sent = channel.send(message("ORD-108"));
        System.out.println("send.result=" + sent);
    }

    private static void demonstrateFalseResult() {
        System.out.println("-- false result --");

        QueueChannel channel = new QueueChannel(1);

        // Lấp đầy queue trước khi đăng ký interceptor.
        channel.send(message("already-queued"));
        channel.addInterceptor(loggingInterceptor("full"));

        // Queue đầy; timeout 0 yêu cầu không chờ để có chỗ trống.
        boolean sent = channel.send(message("ORD-108"), 0);
        System.out.println("send.result=" + sent);
    }

    private static void demonstrateException() {
        System.out.println("-- exception --");

        DirectChannel channel = new DirectChannel();
        channel.addInterceptor(loggingInterceptor("failure"));

        channel.subscribe(message -> {
            System.out.println("handler.throwing=true");
            throw new IllegalStateException("simulated handler failure");
        });

        try {
            channel.send(message("ORD-108"));
        }
        catch (RuntimeException ex) {
            System.out.println("send.exceptionObserved=true");
        }
    }

    private static Message<String> message(String payload) {
        return MessageBuilder.withPayload(payload).build();
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.ChannelInterceptorLifecycleDemo
~~~

Stdout:

~~~text
-- success --
handler.payload=ORD-108
success.postSend.sent=true
success.afterSendCompletion.sent=true
success.afterSendCompletion.exceptionPresent=false
send.result=true
-- false result --
full.postSend.sent=false
full.afterSendCompletion.sent=false
full.afterSendCompletion.exceptionPresent=false
send.result=false
-- exception --
handler.throwing=true
failure.afterSendCompletion.sent=false
failure.afterSendCompletion.exceptionPresent=true
send.exceptionObserved=true
~~~

### 7.3. Giải thích ba kết quả

**Trường hợp thành công**

DirectChannel gọi handler đồng bộ. Handler in payload rồi trả về. Lời gọi send có kết quả true, nên postSend nhận sent=true. Sau đó afterSendCompletion nhận sent=true và ex=null.

**Trường hợp channel trả về false**

QueueChannel có sức chứa 1 và đã được lấp đầy trước khi đăng ký interceptor. Lần gửi thứ hai dùng timeout 0, nên channel không chờ để có chỗ trống và trả về false. Vì send trả về bình thường, postSend vẫn chạy với sent=false. afterSendCompletion cũng chạy với sent=false và ex=null.

**Trường hợp exception**

Handler của DirectChannel ném IllegalStateException. Thao tác gửi không trả về boolean bình thường, do đó postSend không chạy. afterSendCompletion vẫn được gọi với sent=false và ex khác null. Caller bắt RuntimeException và ghi nhận lỗi.

Ví dụ minh họa vòng đời callback. Trong ứng dụng thật, loại exception cụ thể có thể được channel bọc trong một MessagingException chuyên biệt; vì vậy nên xử lý theo nhóm exception và nguyên nhân gốc thay vì phụ thuộc một class duy nhất.

## 8. Khi preSend chặn hoặc ném exception

preSend có thể thay đổi luồng trước khi channel gửi Message:

- Nếu trả về Message, thao tác gửi tiếp tục và interceptor đó đủ điều kiện nhận afterSendCompletion.
- Nếu trả về null, channel không thực hiện thao tác gửi. postSend không chạy cho interceptor đã chặn Message đó. Lời gọi send thường trả về false.
- Nếu ném exception, thao tác gửi bị dừng và exception được truyền ra ngoài. Những interceptor có preSend đã hoàn tất trước đó có thể nhận afterSendCompletion để cleanup.

Khi có nhiều interceptor, một interceptor có thể đã mở tài nguyên trong preSend. Nếu interceptor sau đó chặn Message hoặc ném exception, afterSendCompletion của interceptor trước là nơi phù hợp để giải phóng tài nguyên.

Không nên mở tài nguyên trong postSend rồi mới mong afterSendCompletion dọn dẹp nếu postSend không được gọi do send ném exception. Nếu phải mở tài nguyên trong preSend, hãy bảo đảm completion callback tương ứng có thể giải phóng tài nguyên trong cả trường hợp thành công và thất bại.

## 9. Nhiều interceptor và thứ tự cleanup

Giả sử có hai interceptor A và B được đăng ký theo thứ tự A rồi B.

Luồng thành công thông thường:

~~~text
A.preSend
B.preSend
channel.send
A.postSend
B.postSend
B.afterSendCompletion
A.afterSendCompletion
~~~

afterSendCompletion chạy theo thứ tự ngược để hỗ trợ mô hình stack: tài nguyên được mở theo thứ tự A rồi B thì được giải phóng theo thứ tự B rồi A.

Khi preSend của B trả về null hoặc ném exception, A đã hoàn tất preSend nên A có thể nhận callback completion. B chưa hoàn tất preSend thành công nên không được xem như interceptor đã đăng ký đầy đủ trong stack completion.

Các interceptor không nên phụ thuộc lẫn nhau nếu không cần thiết. Hãy giữ callback nhỏ, rõ ràng và có thể chạy nhiều lần trên các thread khác nhau.

## 10. Thread safety và chi phí của interceptor

ChannelInterceptor có thể được gọi đồng thời khi nhiều producer gửi Message qua cùng một channel. Một interceptor được đăng ký một lần thường được chia sẻ giữa nhiều lời gọi send.

Vì vậy:

- Tránh lưu trạng thái riêng của từng Message vào field mutable của interceptor.
- Dùng AtomicInteger, LongAdder hoặc metric registry an toàn khi cập nhật counter đồng thời.
- Không giả định cùng một thread sẽ gọi mọi callback nếu channel hoặc adapter thay đổi cách dispatch.
- Tránh gọi HTTP, database hoặc thao tác blocking dài trong callback.
- Không ném exception từ afterSendCompletion chỉ để báo metric; callback này chủ yếu phục vụ cleanup và ghi nhận.
- Nếu cần truyền context theo từng lần gửi, dùng Message headers hoặc context có vòng đời rõ ràng.

Nếu cần đo thời gian send, có thể ghi thời điểm trong preSend và tính thời gian trong afterSendCompletion. Dữ liệu thời gian cần được lưu theo cách an toàn với nhiều thread; không dùng một field startedAt duy nhất cho mọi Message.

## 11. Chọn callback cho đúng mục đích

| Nhu cầu | Callback phù hợp | Lý do |
|---|---|---|
| Kiểm tra hoặc sửa Message trước khi gửi | preSend | Chạy trước channel send |
| Chặn Message không hợp lệ | preSend trả null hoặc ném exception | Ngăn thao tác gửi |
| Ghi nhận kết quả boolean của send | postSend | Nhận sent=true hoặc false khi send trả về bình thường |
| Cleanup sau khi send kết thúc, kể cả exception | afterSendCompletion | Nhận sent và exception |
| Đo xử lý thực tế trong consumer | Logic ở handler hoặc endpoint | Interceptor send không chứng minh handler đã hoàn tất |
| Theo dõi từng lần gọi handler trong executor | ExecutorChannelInterceptor | Callback ở ranh giới thực thi handler |
| Quan sát mọi thao tác qua channel | ChannelInterceptor | Cross-cutting behavior tại channel |

ChannelInterceptor cũng có các callback cho receive. preReceive, postReceive và afterReceiveCompletion chỉ áp dụng cho PollableChannel vì chỉ loại channel đó có thao tác receive do consumer chủ động gọi.

## 12. Lỗi thường gặp

1. **Cho rằng postSend chạy khi send ném exception:** postSend nhận boolean nên chỉ chạy khi lời gọi gửi trả về bình thường.
2. **Cho rằng sent=false luôn có exception:** send có thể trả về false bình thường; khi đó ex trong afterSendCompletion là null.
3. **Cho rằng afterSendCompletion luôn chạy cho mọi interceptor:** callback chỉ chạy cho interceptor có preSend hoàn tất thành công và trả về Message.
4. **Cho rằng afterSendCompletion là consumer completion:** nó chỉ hoàn tất thao tác send của channel.
5. **Dùng postSend để cleanup tài nguyên:** nếu send ném exception, postSend không chạy; cleanup nên đặt trong afterSendCompletion.
6. **Bỏ qua preSend trả null:** Message bị chặn, không có postSend cho interceptor chặn nó.
7. **Ghi log exception nhưng bỏ qua sent:** cần phân biệt false result và exception để hiểu đúng trạng thái.
8. **Giả định send=true nghĩa handler thành công:** channel bất đồng bộ có thể chỉ mới chấp nhận task.
9. **Giữ trạng thái mutable chung trong interceptor:** nhiều thread có thể ghi đè dữ liệu của nhau.
10. **Thực hiện I/O nặng trong callback:** làm tăng latency của thao tác gửi hoặc giữ tài nguyên lâu.
11. **Giả định thứ tự callback giữa các channel và thread giống nhau:** chỉ dựa vào thứ tự được bảo đảm trong một send chain.
12. **Nhầm ChannelInterceptor với ExecutorChannelInterceptor:** một cái can thiệp ở channel, cái kia theo dõi việc thực thi handler.

## 13. Câu hỏi tự kiểm tra

1. postSend nhận tham số sent để biểu thị điều gì?
2. Khi send trả về false, postSend và afterSendCompletion có chạy không?
3. Khi send ném exception, callback nào được dùng để cleanup?
4. Vì sao postSend không thể nhận exception trực tiếp?
5. afterSendCompletion có được gọi nếu preSend trả null không?
6. sent=false và ex=null khác sent=false và ex khác null như thế nào?
7. Với channel bất đồng bộ, postSend có chứng minh handler đã xử lý xong không?
8. Vì sao afterSendCompletion chạy theo thứ tự ngược với preSend?
9. Khi nào nên dùng ExecutorChannelInterceptor thay vì ChannelInterceptor?
10. Làm thế nào để interceptor an toàn khi nhiều thread cùng gửi?

## 14. Kết luận

postSend và afterSendCompletion phục vụ hai điểm khác nhau trong vòng đời gửi của ChannelInterceptor. postSend chạy ngay sau khi thao tác gửi trả về bình thường và cho biết boolean sent. afterSendCompletion chạy khi thao tác gửi kết thúc để cleanup, kể cả khi có exception, với điều kiện preSend của interceptor đã hoàn tất và trả về Message.

Khi send trả về false, postSend vẫn chạy với sent=false và afterSendCompletion nhận ex=null. Khi send ném exception, postSend không chạy; afterSendCompletion nhận exception để interceptor dọn dẹp. Với channel bất đồng bộ, các callback này chỉ nói về việc channel chấp nhận hoặc hoàn tất thao tác gửi, không chứng minh consumer đã xử lý nghiệp vụ xong.

## Tài liệu tham khảo chính thức

- Spring Framework ChannelInterceptor API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html
- Spring Framework AbstractMessageChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/AbstractMessageChannel.html
- Spring Integration Channel Interceptors reference: https://docs.spring.io/spring-integration/reference/channel/interceptors.html
- Spring Integration DirectChannel API: https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/DirectChannel.html
- Spring Integration QueueChannel API: https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/QueueChannel.html
