# Đồng bộ và bất đồng bộ nhìn từ bên gửi và bên nhận

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt xử lý đồng bộ và bất đồng bộ trong một luồng messaging.
- Giải thích điều gì xảy ra trên thread của bên gửi khi gọi MessageChannel.send().
- Xác định handler chạy trong thread nào và bên nhận chủ động lấy hay được channel đẩy thông điệp tới.
- Phân biệt việc gửi được chấp nhận với việc xử lý nghiệp vụ đã hoàn tất.
- Chọn cách trao đổi phù hợp khi cần request-reply, xử lý nền, timeout, retry hoặc kiểm soát tải.
- Đọc được hành vi của các channel trong Spring Framework và không nhầm chúng với channel của Spring Integration.

## 1. Đồng bộ và bất đồng bộ nói về điều gì?

Trong messaging, bên gửi (producer) tạo và gửi thông điệp; bên nhận (consumer) tiếp nhận rồi xử lý thông điệp. Đồng bộ và bất đồng bộ mô tả cách hai phía phối hợp về thời điểm thực thi, thời gian chờ và thread.

**Đồng bộ (synchronous)** thường có nghĩa là lời gọi gửi chưa kết thúc cho tới khi phần xử lý được gọi trong cùng luồng thực thi hoàn tất. Bên gửi chờ bên nhận trong cùng call stack. Nếu handler xử lý chậm, thread gửi cũng bị giữ lại.

**Bất đồng bộ (asynchronous)** thường có nghĩa là bên gửi bàn giao thông điệp cho một cơ chế trung gian như executor, queue hoặc broker, rồi có thể tiếp tục trước khi handler hoàn tất. Bên nhận xử lý sau, thường trên thread khác hoặc thậm chí trong tiến trình khác.

Điểm quan trọng là chữ “đồng bộ” có thể được dùng để mô tả nhiều ranh giới khác nhau:

1. **Đồng bộ tại lời gọi send:** send chờ handler chạy xong hay chỉ chờ channel nhận thông điệp?
2. **Đồng bộ tại nghiệp vụ:** bên gửi có chờ kết quả nghiệp vụ hoặc phản hồi từ consumer không?
3. **Đồng bộ tại thread:** producer và handler có chạy trên cùng thread hay không?
4. **Đồng bộ tại transport:** client có chờ broker xác nhận đã nhận hoặc lưu thông điệp không?

Bốn điều này liên quan nhưng không đồng nghĩa. Một producer có thể chờ broker xác nhận việc publish, trong khi consumer xử lý bất đồng bộ sau đó. Một lời gọi send có thể trả về nhanh sau khi executor nhận task, nhưng điều đó chưa cho biết nghiệp vụ đã hoàn tất.

## 2. Hai vai trò: bên gửi và bên nhận

### 2.1. Nhìn từ bên gửi

Bên gửi quan tâm đến thời điểm nó được phép tiếp tục.

- **Gửi đồng bộ tới handler đồng bộ:** producer gọi send; handler chạy trong call stack hiện tại; send chỉ trả về sau khi handler kết thúc hoặc phát sinh lỗi.
- **Gửi qua channel có executor:** producer gọi send; channel giao task cho executor; send thường trả về sau khi task được chấp nhận hoặc được lên lịch. Handler có thể chạy sau đó trên worker thread.
- **Gửi tới broker từ adapter:** producer gửi qua adapter. Adapter có thể chờ xác nhận của broker, chờ ghi vào socket hoặc chỉ bàn giao cho client nội bộ. Cần xem hợp đồng cụ thể của adapter và broker.
- **Producer tự offload lời gọi gửi:** ứng dụng đưa cả thao tác send vào executor riêng. Thread của request ban đầu có thể tiếp tục, nhưng lời gọi send vẫn có thể chặn thread worker cho tới khi channel chấp nhận thông điệp.

Vì vậy, “gửi bất đồng bộ” cần nói rõ bất đồng bộ ở đâu: ứng dụng offload thao tác gửi, channel dispatch handler bằng executor, hay adapter/broker xử lý qua mạng.

### 2.2. Nhìn từ bên nhận

Bên nhận quan tâm đến cách thông điệp tới được nó và thread nào thực hiện công việc.

- **Nhận kiểu push:** consumer đăng ký một MessageHandler. Channel chủ động gọi handler khi có thông điệp. SubscribableChannel là hợp đồng kiểu này.
- **Nhận kiểu pull/poll:** consumer chủ động gọi receive() để lấy thông điệp. PollableChannel là hợp đồng kiểu này. Lời gọi receive có thể trả về ngay, chờ tới timeout hoặc chờ theo cấu hình của channel.
- **Nhận qua executor:** channel hoặc adapter chuyển việc xử lý sang worker thread. Consumer không cần gọi receive trực tiếp cho mỗi thông điệp.
- **Nhận qua broker:** consumer chạy độc lập với producer, có thể ở tiến trình hoặc máy khác. Thread, số lượng consumer, phân vùng và cách xác nhận phụ thuộc integration và broker.

Push/pull mô tả cách consumer nhận thông điệp. Đồng bộ/bất đồng bộ mô tả cách các bên chờ nhau. Hai trục này không nên bị gộp thành một khái niệm.

## 3. Điều gì xảy ra trong Spring Messaging?

spring-messaging cung cấp các hợp đồng nền tảng như Message, MessageChannel, SubscribableChannel, PollableChannel và MessageHandler. Hợp đồng MessageChannel có phương thức send, nhưng bản thân interface không bắt buộc mọi implementation phải chạy đồng bộ hoặc bất đồng bộ.

Hai interface nhận thông điệp thường gặp:

| Hợp đồng | Cách consumer nhận | Ý nghĩa |
|---|---|---|
| SubscribableChannel | Đăng ký MessageHandler bằng subscribe() | Channel đẩy thông điệp tới handler |
| PollableChannel | Gọi receive() hoặc receive(timeout) | Consumer chủ động lấy thông điệp |

Một số implementation trong Spring Framework giúp nhìn rõ sự khác nhau:

- **ExecutorSubscribableChannel không có Executor:** gọi handler trực tiếp trong thread đang gọi send. Với handler chạy bình thường, send chưa kết thúc trước khi handler trả về.
- **ExecutorSubscribableChannel có Executor:** channel giao việc gọi handler cho Executor. Với thread pool thông thường, handler chạy trên worker thread và producer có thể tiếp tục sau khi task được chấp nhận.
- **ExecutorSubscribableChannel với direct executor:** dù constructor có nhận một Executor, executor có thể thực thi Runnable ngay trong thread gọi nó. Vì thế, chỉ sự hiện diện của Executor chưa chứng minh xử lý bất đồng bộ.

Hợp đồng của channel chỉ cho biết khả năng gửi/nhận. Cách dispatch, lưu đệm, giới hạn tải, xử lý lỗi và thread thực tế phải được xác định từ implementation và cấu hình đang dùng.

## 4. Luồng đồng bộ: producer chờ handler

Khi dùng một SubscribableChannel mà handler được gọi trực tiếp, trình tự thường là:

~~~mermaid
sequenceDiagram
    participant P as Producer thread
    participant C as SubscribableChannel
    participant H as MessageHandler

    P->>C: send(message)
    C->>H: handleMessage(message)
    Note over P,H: Handler chạy trong cùng thread/call stack
    H-->>C: Trả về
    C-->>P: send trả về
    Note over P: Producer tiếp tục
~~~

Các hệ quả:

- Handler chạy lâu sẽ kéo dài thời gian send.
- Nếu handler chặn khi gọi I/O đồng bộ, thread producer cũng bị giữ.
- Trong trường hợp in-process, exception từ handler có thể ảnh hưởng tới lời gọi gửi; cách truyền lỗi cuối cùng còn tùy channel và cấu hình xử lý lỗi.
- Không có hàng đợi executor ở giữa để hấp thụ một lượng công việc lớn.
- Việc handler trả về chỉ cho biết lời gọi handler kết thúc. Điều đó không tự chứng minh dữ liệu đã commit bền vững ở một hệ thống ngoài.

Mô hình này phù hợp khi cần xử lý ngay trong cùng luồng, muốn luồng điều khiển đơn giản và không cần tách thời điểm xử lý khỏi lời gọi gửi. Nó cũng có thể hữu ích trong kiểm thử vì thứ tự thực thi dễ quan sát.

## 5. Luồng bất đồng bộ: producer bàn giao rồi tiếp tục

Khi channel dispatch handler qua executor, trình tự thường là:

~~~mermaid
sequenceDiagram
    participant P as Producer thread
    participant C as SubscribableChannel
    participant E as Executor
    participant W as Worker thread
    participant H as MessageHandler

    P->>C: send(message)
    C->>E: submit task gọi handler
    E-->>C: Task được nhận
    C-->>P: send trả về
    Note over P: Producer tiếp tục công việc khác
    E->>W: Chạy task trên worker
    W->>H: handleMessage(message)
    H-->>W: Xử lý xong
~~~

Các hệ quả:

- Producer thường không phải chờ handler xử lý xong.
- Handler chạy trên thread do Executor cung cấp, thường là worker thread.
- send trả về nhanh hơn nếu thời gian xử lý handler dài, nhưng vẫn có chi phí đóng gói và dispatch.
- Lỗi xảy ra sau khi producer đã tiếp tục không thể được ném ngược về call stack cũ theo cách thông thường.
- Nếu executor có hàng đợi, công việc có thể chờ trong hàng đợi trước khi handler bắt đầu.
- Nếu executor bị từ chối task, send có thể thất bại hoặc ném exception tùy implementation và rejection policy.

Bất đồng bộ giúp giảm thời gian chờ của producer, nhưng không làm cho công việc biến mất. Tải xử lý vẫn cần tài nguyên thread, bộ nhớ, queue và giới hạn concurrency.

## 6. Ví dụ Java: so sánh thread của sender và receiver

Ví dụ dưới đây dùng spring-messaging trực tiếp. Nó tạo hai SubscribableChannel:

1. Một ExecutorSubscribableChannel không có Executor để minh họa handler chạy trong thread gửi.
2. Một ExecutorSubscribableChannel dùng single-thread Executor để minh họa handler chạy trong worker thread.

### 6.1. Cấu hình Maven

Ví dụ dùng Java 17 và Spring Framework 6.2.8. Spring Framework BOM giúp đồng bộ phiên bản dependency:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>sync-async-messaging</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>6.2.8</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
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

### 6.2. Chương trình hoàn chỉnh

Tạo file src/main/java/demo/SyncAsyncMessagingDemo.java:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.springframework.messaging.Message;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class SyncAsyncMessagingDemo {

    public static void main(String[] args) throws InterruptedException {
        runSynchronousExample();
        runAsynchronousExample();
    }

    private static void runSynchronousExample() {
        SubscribableChannel channel = new ExecutorSubscribableChannel();

        channel.subscribe(message ->
                System.out.println(
                        "sync.receiverThread=" + Thread.currentThread().getName()
                )
        );

        System.out.println(
                "sync.senderThread=" + Thread.currentThread().getName()
        );

        boolean accepted = channel.send(createMessage("sync"));
        System.out.println("sync.sendReturned=" + accepted);
    }

    private static void runAsynchronousExample() throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "messaging-worker")
        );

        CountDownLatch allowHandler = new CountDownLatch(1);
        CountDownLatch handled = new CountDownLatch(1);

        try {
            SubscribableChannel channel =
                    new ExecutorSubscribableChannel(executor);

            channel.subscribe(message -> {
                try {
                    if (!allowHandler.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "Timed out waiting for the sender"
                        );
                    }

                    System.out.println(
                            "async.receiverThread="
                                    + Thread.currentThread().getName()
                    );
                }
                catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(ex);
                }
                finally {
                    handled.countDown();
                }
            });

            System.out.println(
                    "async.senderThread=" + Thread.currentThread().getName()
            );

            boolean accepted = channel.send(createMessage("async"));
            System.out.println("async.sendReturned=" + accepted);

            // Chỉ cho handler chạy sau khi sender đã in kết quả send.
            allowHandler.countDown();

            if (!handled.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Handler did not complete in time"
                );
            }
        }
        finally {
            allowHandler.countDown();
            executor.shutdown();

            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }

    private static Message<String> createMessage(String payload) {
        return MessageBuilder.withPayload(payload).build();
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.SyncAsyncMessagingDemo
~~~

Stdout:

~~~text
sync.senderThread=main
sync.receiverThread=main
sync.sendReturned=true
async.senderThread=main
async.sendReturned=true
async.receiverThread=messaging-worker
~~~

### 6.3. Đọc kết quả

Ở ví dụ đồng bộ, sender và receiver cùng chạy trên thread main. Handler được gọi trong lời gọi send, nên dòng sync.receiverThread xuất hiện trước sync.sendReturned.

Ở ví dụ bất đồng bộ, channel sử dụng ExecutorService. send bàn giao công việc cho executor và trả về true. Chương trình in async.sendReturned trước khi mở latch cho handler tiếp tục. Handler sau đó chạy trên thread messaging-worker.

CountDownLatch ở đây chỉ giúp kết quả minh họa có thứ tự ổn định. Trong ứng dụng thật, không nên dùng latch để điều phối mọi thông điệp. Hãy dùng cơ chế đồng bộ phù hợp với nghiệp vụ, hoặc thiết kế response/acknowledgement riêng.

Kết quả true cho biết channel đã chấp nhận thông điệp theo hợp đồng của implementation. Nó không có nghĩa rằng mọi xử lý nghiệp vụ đã hoàn tất hoặc dữ liệu đã được lưu bền.

## 7. Bên nhận chủ động lấy: PollableChannel

SubscribableChannel là mô hình push: consumer đăng ký handler và channel gọi handler khi có thông điệp.

PollableChannel là mô hình pull: consumer chủ động gọi receive:

~~~java
Message<?> message = channel.receive();
~~~

Hoặc chỉ chờ tối đa một khoảng thời gian:

~~~java
Message<?> message = channel.receive(1_000);
~~~

Với cách nhận pull, consumer quyết định khi nào lấy thông điệp. Lời gọi receive có thể trả về null khi hết thời gian chờ mà không có thông điệp. Cách channel lưu trữ, giới hạn queue và hành vi send khi channel đầy phụ thuộc implementation.

Một vòng lặp consumer có thể có dạng:

~~~java
while (running) {
    Message<?> message = channel.receive(1_000);

    if (message == null) {
        continue;
    }

    process(message);
}
~~~

Đây là mã minh họa cho ý tưởng polling; trong ứng dụng thực tế cần bổ sung xử lý shutdown, interrupt, timeout, exception và giới hạn thời gian xử lý.

Pull không tự động đồng nghĩa với bất đồng bộ. Nếu producer gọi send và receiver gọi receive trên thread riêng, hai phía được tách về thời điểm thực thi. Nhưng nếu cùng một thread lần lượt gọi send rồi receive, chương trình vẫn có thể chờ đồng bộ. Tương tự, push không tự động đồng nghĩa với bất đồng bộ: SubscribableChannel có thể gọi handler ngay trên thread gửi.

## 8. Request-reply: gửi bất đồng bộ nhưng vẫn cần câu trả lời

Nhiều hệ thống gửi một lệnh và cần nhận kết quả. Đây là request-reply, khác với publish event một chiều.

Có hai cách phối hợp phổ biến:

**Request-reply đồng bộ**

1. Producer gửi request.
2. Producer chờ reply trên reply channel.
3. Consumer xử lý và gửi response tương ứng.
4. Producer tiếp tục khi nhận được reply hoặc hết timeout.

Spring Messaging cung cấp `GenericMessagingTemplate` trong `org.springframework.messaging.core`, với API `sendAndReceive` cho các tình huống phù hợp. Kiểu gọi này có thể chờ phản hồi; timeout phải được cấu hình và xử lý rõ ràng.

**Request-reply bất đồng bộ**

1. Producer gửi request có request ID hoặc correlation ID.
2. Producer tiếp tục công việc khác.
3. Consumer xử lý request và gửi response mang correlation ID tương ứng.
4. Thành phần quản lý pending request ghép response với request ban đầu.
5. Kết quả được chuyển cho callback, future, reactive publisher hoặc cơ chế phản hồi của ứng dụng.

Bất đồng bộ không loại bỏ nhu cầu quản lý timeout. Producer vẫn cần biết phải làm gì khi không có reply, reply đến trễ hoặc reply trùng lặp.

### Event và command không giống nhau

- **Event:** thông báo một điều đã xảy ra, ví dụ OrderCreated. Producer thường không chờ một consumer cụ thể trả lời.
- **Command:** yêu cầu một hành động, ví dụ ReserveInventory. Producer có thể cần acknowledgement hoặc kết quả.
- **Request-reply:** producer gửi request và mong đợi response tương ứng.

Chọn đúng ý nghĩa giúp tránh dùng một event một chiều trong khi nghiệp vụ thực chất cần kết quả xác nhận.

## 9. Timeout, lỗi và bảo đảm xử lý

### 9.1. Timeout ở bên gửi

Timeout có thể xuất hiện khi:

- Gửi qua channel có giới hạn thời gian chờ.
- Executor hoặc queue quá tải.
- Adapter chờ broker xác nhận.
- Request-reply chờ response.
- Producer gọi dịch vụ ngoài trong khi tạo hoặc gửi thông điệp.

Timeout không luôn có nghĩa là thao tác chưa xảy ra. Ví dụ producer có thể timeout khi chờ phản hồi, trong khi consumer đã nhận và xử lý xong. Nếu producer gửi lại ngay mà không có idempotency, nghiệp vụ có thể bị thực hiện hai lần.

### 9.2. Lỗi ở bên nhận

Với xử lý đồng bộ trong cùng call stack, lỗi từ handler có thể được truyền về lời gọi gửi tùy implementation và cấu hình.

Với xử lý bất đồng bộ, producer có thể đã nhận kết quả send trước khi handler gặp lỗi. Khi đó, lỗi cần được quan sát và xử lý ở phía consumer hoặc hạ tầng trung gian. Tùy kiến trúc, các cơ chế có thể gồm:

- Error handler hoặc error channel.
- Retry có giới hạn và backoff.
- Dead-letter queue hoặc dead-letter topic do broker/integration hỗ trợ.
- Ghi nhận trạng thái xử lý để có thể phục hồi.
- Idempotency key để tránh xử lý lặp.

spring-messaging cung cấp abstraction thông điệp và channel; nó không tự cung cấp đầy đủ retry, dead-letter, transaction hay durable delivery cho mọi implementation.

### 9.3. Gửi được chấp nhận không có nghĩa xử lý thành công

MessageChannel.send trả về boolean. Giá trị này cho biết việc gửi có được channel chấp nhận hay không theo hợp đồng của channel.

Không nên diễn giải send=true thành một trong các kết luận sau:

- Consumer đã bắt đầu xử lý.
- Consumer đã xử lý xong.
- Transaction nghiệp vụ đã commit.
- Broker đã lưu bền thông điệp.
- Thông điệp sẽ không bao giờ bị mất hoặc xử lý lặp.

Muốn có các bảo đảm này, cần xem xét channel/adapter/broker, transaction, acknowledgement, persistence và chính sách retry cụ thể.

## 10. Concurrency, thứ tự và kiểm soát tải

Khi dùng executor để xử lý bất đồng bộ, nhiều handler có thể chạy đồng thời. Điều này giúp tăng throughput nhưng phát sinh các vấn đề mới:

- **Race condition:** nhiều handler cùng cập nhật một trạng thái hoặc tài nguyên.
- **Ordering:** thông điệp đến trước có thể hoàn tất sau thông điệp đến sau.
- **Thread safety:** service, cache hoặc object được chia sẻ phải an toàn khi truy cập đồng thời.
- **Queue growth:** producer gửi nhanh hơn tốc độ consumer xử lý khiến hàng đợi tăng và tiêu thụ bộ nhớ.
- **Rejection:** executor từ chối task khi đã quá tải hoặc đã shutdown.
- **Shutdown:** ứng dụng cần xác định có chờ task đang chạy, drain queue hay dừng ngay.

Một số biện pháp thiết kế:

1. Dùng thread pool có kích thước và queue capacity phù hợp.
2. Xác định rejection policy rõ ràng; không để quá tải trở thành mất thông điệp âm thầm.
3. Đặt timeout cho các thao tác I/O và request-reply.
4. Dùng correlation ID để theo dõi một luồng xử lý qua nhiều thành phần.
5. Dùng idempotency key cho nghiệp vụ có thể được gửi lại.
6. Nếu thứ tự quan trọng, phân vùng theo khóa nghiệp vụ hoặc tuần tự hóa xử lý trong phạm vi cần thiết.
7. Đo queue depth, thời gian chờ, thời gian xử lý, số lỗi và số lần retry.
8. Tránh dùng một executor không giới hạn cho công việc có thể tăng đột biến.

### Ví dụ về thứ tự

Giả sử một đơn hàng phát hai thông điệp theo thứ tự:

1. OrderCreated
2. OrderPaid

Nếu hai handler được chạy trên hai worker khác nhau, handler xử lý OrderPaid có thể hoàn tất trước OrderCreated. Nếu logic nghiệp vụ yêu cầu thứ tự, hãy thiết kế cơ chế bảo đảm thứ tự thay vì dựa vào thời điểm gửi.

## 11. Các channel của Spring Integration và ranh giới module

Một số tên channel thường xuất hiện trong tài liệu Spring:

| Channel | Module | Hành vi thường dùng |
|---|---|---|
| ExecutorSubscribableChannel | Spring Framework, spring-messaging | Push tới subscriber; có thể dispatch qua Executor |
| DirectChannel | Spring Integration | Thường gọi handler đồng bộ trong luồng gửi |
| ExecutorChannel | Spring Integration | Dùng TaskExecutor để dispatch handler |
| QueueChannel | Spring Integration | Lưu thông điệp để consumer lấy bằng polling |
| PublishSubscribeChannel | Spring Integration | Phát thông điệp tới các subscriber |

Bảng này giúp phân biệt phạm vi API. DirectChannel, ExecutorChannel và QueueChannel là các implementation của Spring Integration; không nên cho rằng chúng đều được cung cấp chỉ bằng dependency spring-messaging.

Tương tự, một broker như Kafka hoặc RabbitMQ có consumer thread, acknowledgement, partition/queue và semantics riêng. Các tính chất này không thể suy ra chỉ từ tên MessageChannel.

## 12. Khi nào chọn đồng bộ, khi nào chọn bất đồng bộ?

| Tình huống | Hướng phù hợp | Lý do |
|---|---|---|
| Cần kết quả ngay để hoàn tất request hiện tại | Đồng bộ hoặc request-reply | Caller cần phản hồi trước khi tiếp tục |
| Handler nhẹ, chạy trong cùng tiến trình và cần luồng điều khiển đơn giản | Đồng bộ | Dễ theo dõi call stack và lỗi |
| Công việc mất nhiều thời gian, người dùng không cần chờ | Bất đồng bộ | Có thể trả phản hồi sớm và xử lý nền |
| Cần fan-out tới nhiều thành phần độc lập | Messaging bất đồng bộ hoặc pub/sub | Producer tách khỏi từng consumer |
| Consumer cần chủ động điều tiết tốc độ | Pull/poll | Consumer kiểm soát nhịp lấy dữ liệu |
| Cần giao tiếp qua nhiều tiến trình hoặc máy | Broker/transport phù hợp | Cần hạ tầng truyền và quản lý thông điệp |
| Thao tác phải có xác nhận nghiệp vụ | Request-reply hoặc acknowledgement | Chấp nhận gửi không phải kết quả nghiệp vụ |

Không có lựa chọn luôn tốt hơn. Đồng bộ đơn giản hơn khi caller thực sự cần kết quả ngay. Bất đồng bộ phù hợp khi muốn tách thời gian xử lý, hấp thụ tải hoặc kết nối các thành phần độc lập, nhưng cần thêm cơ chế quan sát, timeout, retry và phục hồi.

## 13. Lỗi thường gặp

1. **Cho rằng mọi MessageChannel đều bất đồng bộ:** interface không quy định điều đó; implementation quyết định cách dispatch.
2. **Cho rằng có Executor là chắc chắn chạy ở thread khác:** direct executor có thể chạy ngay trong thread gọi.
3. **Cho rằng send=true là consumer đã xử lý xong:** boolean chỉ phản ánh việc channel chấp nhận thông điệp.
4. **Nhầm push với async:** SubscribableChannel có thể gọi handler đồng bộ trong thread gửi.
5. **Nhầm pull với sync:** consumer polling trên thread riêng vẫn có thể hoạt động độc lập với producer.
6. **Đưa cả send vào executor nhưng tưởng channel đã async:** đây là offload từ ứng dụng; bản thân send bên trong worker vẫn có thể chặn.
7. **Không quản lý timeout:** producer có thể chờ vô hạn hoặc gửi lại trong khi lần xử lý cũ vẫn đang chạy.
8. **Không xử lý lỗi bất đồng bộ:** lỗi của handler có thể xuất hiện sau khi producer đã tiếp tục.
9. **Không kiểm soát concurrency:** nhiều worker có thể cập nhật cùng tài nguyên và làm sai thứ tự nghiệp vụ.
10. **Dùng queue không giới hạn:** khi consumer chậm, bộ nhớ có thể tăng cho tới khi ứng dụng gặp sự cố.
11. **Không làm idempotent:** retry hoặc gửi lại sau timeout có thể tạo hiệu ứng nghiệp vụ trùng lặp.
12. **Nhầm channel trong Spring Integration với API nền tảng:** kiểm tra module và dependency thực tế trước khi dùng.

## 14. Câu hỏi tự kiểm tra

1. Trong một ExecutorSubscribableChannel không có Executor, handler chạy ở thread nào?
2. Khi channel dùng thread pool, send thường trả về ở thời điểm nào?
3. Vì sao send=true không chứng minh consumer đã xử lý xong?
4. SubscribableChannel khác PollableChannel ở cách consumer nhận thông điệp như thế nào?
5. Push có luôn bất đồng bộ không? Pull có luôn đồng bộ không?
6. Producer offload lời gọi send sang executor khác khác gì với channel dispatch handler sang executor?
7. Nếu handler lỗi sau khi send đã trả về, producer nhận lỗi bằng cách nào?
8. Khi nào nên dùng request-reply thay vì event một chiều?
9. Vì sao cần idempotency khi producer retry sau timeout?
10. Làm thế nào để bảo toàn thứ tự khi nhiều worker xử lý đồng thời?

## 15. Kết luận

Đồng bộ và bất đồng bộ cần được phân tích từ cả hai phía. Bên gửi quan tâm nó phải chờ tới đâu; bên nhận quan tâm thông điệp được đẩy tới handler hay được chủ động lấy, và handler chạy trên thread nào.

Trong Spring Messaging, MessageChannel chỉ định nghĩa hợp đồng gửi. SubscribableChannel và PollableChannel thể hiện hai cách nhận, còn implementation như ExecutorSubscribableChannel quyết định cách dispatch cụ thể. Một channel chạy handler trong thread gửi có hành vi đồng bộ; channel dispatch qua executor thường cho phép producer tiếp tục trước khi handler hoàn tất.

Khi thiết kế, hãy xác định rõ điều kiện hoàn tất mà nghiệp vụ cần: channel đã nhận thông điệp, broker đã xác nhận, consumer đã xử lý, hay kết quả nghiệp vụ đã được trả về. Từ đó mới chọn đồng bộ, bất đồng bộ, polling, request-reply và các chính sách timeout, retry, ordering phù hợp.

## Tài liệu tham khảo chính thức

- Spring Framework Messaging API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/package-summary.html
- MessageChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html
- SubscribableChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/SubscribableChannel.html
- PollableChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/PollableChannel.html
- ExecutorSubscribableChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html
- Spring Integration channel reference: https://docs.spring.io/spring-integration/reference/channel.html
