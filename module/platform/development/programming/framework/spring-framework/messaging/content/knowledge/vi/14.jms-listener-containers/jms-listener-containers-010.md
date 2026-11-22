# Khởi động, dừng, chờ xử lý và nhận thông điệp khi đang dừng

Trong Spring JMS, **DefaultMessageListenerContainer (DMLC)** quản lý vòng đời của các consumer nhận message từ Queue hoặc Topic. Container hỗ trợ khởi động, tạm dừng, khởi động lại và giải phóng resource khi ứng dụng đóng. Khi dừng, một câu hỏi quan trọng là listener đang xử lý message có được hoàn tất không, message mới đến trong lúc dừng có được nhận không và ứng dụng biết thời điểm nào có thể đóng các dependency khác.

Cần phân biệt ba thao tác: **stop** tạm dừng việc nhận message và cho listener invoker dừng; **stop(Runnable)** cung cấp callback khi mọi listener processing đã thực sự dừng; **shutdown/destroy** giải phóng các Session, Consumer và Connection do container quản lý. Hiểu đúng các thao tác này giúp triển khai graceful shutdown, tránh đóng database hoặc dependency quá sớm và kiểm soát message được nhận trong giai đoạn dừng.

## 1. Lifecycle của DefaultMessageListenerContainer

DMLC triển khai các interface lifecycle của Spring, gồm **Lifecycle**, **SmartLifecycle** và **DisposableBean**. Vì vậy, nó có thể được Spring ApplicationContext tự khởi động và dừng theo vòng đời ứng dụng.

Các trạng thái cần phân biệt:

- **Initialized/active:** container đã được cấu hình và tạo hạ tầng cần thiết.
- **Running:** container đang cho phép các invoker nhận message và gọi listener.
- **Stopped:** container đã nhận yêu cầu dừng; có thể được start lại nếu chưa shutdown.
- **Shutdown/destroyed:** container đã đóng các resource đang quản lý và kết thúc vòng đời.

Một số phương thức chính:

| Phương thức | Ý nghĩa |
|---|---|
| start() | Khởi động hoặc tiếp tục nhận message |
| stop() | Yêu cầu container dừng nhận message và dừng các invoker |
| stop(Runnable callback) | Dừng container và gọi callback sau khi listener processing thực sự dừng |
| shutdown() | Dừng Connection dùng chung, hủy Session/Consumer và đóng container |
| destroy() | Hook của Spring để gọi shutdown() khi bean bị hủy |
| isRunning() | Cho biết container đang ở trạng thái running |
| isActive() | Cho biết container đã được khởi tạo và chưa shutdown |

**stop() có thể theo sau bằng start()** để tiếp tục sử dụng container. shutdown() và destroy() dành cho việc kết thúc vòng đời và giải phóng resource. Không dùng shutdown() như thao tác pause thông thường nếu còn dự định restart container.

### 1.1. Tự khởi động và thứ tự lifecycle

DMLC mặc định có **autoStartup=true**, nghĩa là Spring LifecycleProcessor tự start container khi ApplicationContext refresh hoàn tất. Có thể tắt để chủ động start sau khi ứng dụng đã sẵn sàng:

~~~java
container.setAutoStartup(false);
~~~

DMLC cũng có lifecycle phase. Spring start các component theo thứ tự phase tăng dần và stop theo thứ tự ngược lại. Mặc định DMLC dùng SmartLifecycle.DEFAULT_PHASE, tức khởi động muộn và dừng sớm trong chuỗi lifecycle. Có thể điều chỉnh phase để kiểm soát quan hệ giữa listener và các dependency khác.

Ví dụ, nếu listener cần database và service phụ trợ, các dependency đó phải sẵn sàng trước khi listener bắt đầu. Khi shutdown, listener nên dừng trước khi database connection pool hoặc dependency mà listener cần bị đóng.

## 2. Điều gì xảy ra khi gọi stop()?

DMLC dùng các invoker chạy vòng lặp nhận message bằng MessageConsumer.receive(). Khi gọi stop():

1. Container chuyển trạng thái running sang false.
2. Container đánh thức các invoker đang chờ điều kiện lifecycle.
3. Connection dùng chung được dừng nếu cache strategy của container sử dụng shared Connection.
4. Các invoker ngừng nhận message mới theo quy tắc dừng.
5. Listener đang chạy được phép đi đến điểm kết thúc xử lý; container theo dõi thời điểm toàn bộ listener processing dừng.

stop() không có nghĩa là xóa message còn trong Queue hoặc chờ toàn bộ destination rỗng. Message chưa được nhận vẫn thuộc broker/destination và có thể được xử lý sau khi container start lại hoặc bởi consumer khác.

Cũng không nên dùng riêng isRunning()==false để kết luận mọi listener invocation đã kết thúc. Trạng thái running phản ánh yêu cầu lifecycle; để biết việc dừng listener đã hoàn tất, hãy dùng stop(Runnable callback).

## 3. Chờ listener đang xử lý hoàn tất bằng stop(Runnable)

DMLC cung cấp overload:

~~~java
container.stop(() -> {
    // Listener processing đã thực sự dừng.
    stoppedLatch.countDown();
});
~~~

Callback chỉ được gọi sau khi mọi listener processing của container đã dừng. Đây là tín hiệu phù hợp để ứng dụng tiếp tục bước shutdown tiếp theo, chẳng hạn đóng các service mà listener sử dụng.

Có thể dùng CountDownLatch để chờ callback với timeout do ứng dụng quyết định:

~~~java
CountDownLatch stopped = new CountDownLatch(1);

container.stop(stopped::countDown);

boolean completed = stopped.await(30, TimeUnit.SECONDS);

if (!completed) {
    throw new IllegalStateException(
            "JMS listener container did not stop in time"
    );
}
~~~

Trong ví dụ, 30 giây là giới hạn chờ do ứng dụng đặt ra. DMLC không cung cấp một phương thức awaitTermination() riêng. Nếu hết timeout, không được xem container đã dừng hoàn toàn; cần ghi nhận tình trạng còn listener đang chạy và áp dụng chính sách shutdown của ứng dụng.

Một số lưu ý về callback:

- Callback được gọi sau khi listener processing thực sự dừng, không chỉ sau khi yêu cầu stop được gửi đi.
- Nếu gọi stop(callback) nhiều lần trong khi lần dừng trước chưa hoàn tất, callback mới nhất sẽ thay thế callback trước.
- Nếu gọi start() để restart container trước khi quá trình stop hoàn tất, callback đang chờ có thể không được gọi.
- Callback nên ngắn gọn. Nếu cần thực hiện nhiều bước shutdown, callback có thể báo tín hiệu cho một coordinator riêng để coordinator tiếp tục công việc.

## 4. Nhận message khi container đang dừng

DMLC có thuộc tính **acceptMessagesWhileStopping** để quyết định xử lý message mà receive() trả về trong giai đoạn container đang dừng.

Cấu hình:

~~~java
container.setAcceptMessagesWhileStopping(false);
~~~

Giá trị mặc định là **false**.

### 4.1. acceptMessagesWhileStopping=false

Khi container đang dừng, message được trả về từ một receive attempt có thể bị từ chối bằng cách hủy receive attempt. Điều này giúp container thoát khỏi vòng nhận và kết thúc nhanh hơn.

Hành vi này không có nghĩa DMLC chủ động xóa toàn bộ message đang chờ. Message bị receive attempt hủy sẽ được xử lý theo semantics của JMS provider và acknowledgement/transaction đang dùng.

Javadoc Spring lưu ý rằng việc abort receive attempt có thể làm bộ đếm retry của provider giảm đối với message liên quan. Nếu có nhiều consumer đồng thời, cần kiểm tra retry/redelivery policy của provider và bảo đảm số lần retry đủ lớn so với số consumer trong các tình huống shutdown.

### 4.2. acceptMessagesWhileStopping=true

Có thể bật:

~~~java
container.setAcceptMessagesWhileStopping(true);
~~~

Khi bật, DMLC tiếp tục xử lý message mà các receive attempt đang chờ trả về trong giai đoạn stopping. Điều này có thể giúp hoàn tất thêm một số message đã được broker giao cho consumer trong lúc shutdown bắt đầu.

Tuy nhiên, các receive timeout chưa hết vẫn có thể nhận cả message mới được gửi sau thời điểm bắt đầu stop. Vì vậy, container có thể tiếp tục xử lý message mới trong lúc dừng. Nếu producer vẫn liên tục gửi message, thời gian chờ callback có thể kéo dài.

Cờ này không phải chế độ drain toàn bộ Queue. Nó chỉ quyết định cách xử lý các message được nhận bởi những receive attempt còn đang diễn ra trong giai đoạn dừng. Muốn drain backlog có kiểm soát, cần phối hợp dừng producer, quan sát backlog và quản lý thời gian shutdown ở cấp ứng dụng.

### 4.3. So sánh hai lựa chọn

| Cấu hình | Hành vi trong stopping | Tác động |
|---|---|---|
| false (mặc định) | Abort receive attempt đối với message đến trong giai đoạn dừng | Dừng nhận nhanh hơn; cần kiểm tra redelivery/retry của provider |
| true | Xử lý message được receive trả về trong giai đoạn dừng | Có thể hoàn tất thêm message nhưng cũng có thể nhận message mới và kéo dài shutdown |

Chọn theo yêu cầu nghiệp vụ. Nếu ưu tiên ngừng nhận nhanh để triển khai phiên bản mới, false thường phù hợp. Nếu muốn hoàn tất các message mà consumer đang chờ nhận và chấp nhận thời gian shutdown dài hơn, có thể cân nhắc true sau khi kiểm thử.

## 5. In-flight message, acknowledgement và transaction

Cách message được xử lý khi dừng liên quan trực tiếp đến acknowledgement và transaction của Session.

### 5.1. AUTO_ACKNOWLEDGE

Với DMLC, chế độ AUTO_ACKNOWLEDGE mặc định thực hiện acknowledgement trước khi gọi listener. Nếu listener ném exception hoặc ứng dụng dừng trong một thời điểm không thuận lợi, message có thể đã được acknowledge và không được redelivery.

Vì vậy, AUTO_ACKNOWLEDGE không cung cấp mức bảo đảm đáng tin cậy cho các luồng mà message không được phép mất. Không nên xem stop callback là cơ chế khôi phục message đã acknowledge.

### 5.2. Local transacted Session

Có thể bật transaction JMS cục bộ:

~~~java
container.setSessionTransacted(true);
~~~

Khi đó, việc nhận message và xử lý listener nằm trong transaction của Session:

- Listener hoàn tất bình thường: container commit transaction.
- Listener ném exception: container rollback transaction theo cơ chế xử lý lỗi.
- Container dừng trong lúc message chưa commit: transaction chưa hoàn tất có thể bị rollback khi resource được kết thúc, để provider xử lý redelivery theo cấu hình.

Đối với message đang được listener xử lý, stop callback chỉ hoàn tất sau khi listener processing đã dừng. Nếu listener hoàn tất bình thường và transaction commit, message đã được xử lý. Nếu listener thất bại và rollback, provider có thể giao lại message.

Redelivery count, delay, dead-letter policy và số lần thử phụ thuộc JMS provider. Cần cấu hình giới hạn cho poison message để một message lỗi không bị giao lại vô hạn.

### 5.3. External transaction manager

DMLC cũng có thể tham gia transaction bên ngoài qua thuộc tính transactionManager, thường là JtaTransactionManager trong môi trường hỗ trợ XA/JTA.

Khi shutdown, cần để transaction manager hoàn tất hoặc rollback transaction đang hoạt động trước khi đóng các resource liên quan. Thứ tự dừng các bean theo lifecycle phase giúp bảo đảm listener kết thúc trước các dependency transaction/database mà nó cần.

Transaction JMS và database không tự trở thành một transaction nguyên tử nếu chỉ dùng local transacted Session. Nếu cần bảo đảm nhất quán giữa database và message, hãy cấu hình XA/JTA phù hợp hoặc dùng Transactional Outbox.

## 6. stop(), shutdown() và đóng ApplicationContext

Ba thao tác này có mục đích khác nhau:

| Thao tác | Mục đích | Có thể start lại? |
|---|---|---|
| stop() | Tạm dừng listener container | Có, gọi start() |
| stop(Runnable) | Tạm dừng và nhận callback khi listener processing đã dừng | Có, gọi start() sau khi dừng hoàn tất |
| shutdown() | Dừng Connection, hủy Session/Consumer và đóng container | Dùng cho kết thúc vòng đời; cần initialize lại nếu muốn tái sử dụng |
| destroy() | Hook giải phóng bean, gọi shutdown() | Không dùng để pause/restart |

Trong ứng dụng Spring, ApplicationContext quản lý SmartLifecycle và DisposableBean. Khi context đóng, lifecycle processor yêu cầu các SmartLifecycle component dừng theo phase; sau đó bean được destroy để giải phóng resource.

Nếu cần điều phối shutdown thủ công, có thể gọi stop(callback), chờ callback hoàn tất, rồi mới đóng các dependency khác. Tránh gọi destroy() hoặc đóng ConnectionFactory trong khi listener vẫn đang sử dụng Session, database hoặc service phụ trợ.

## 7. Quy trình graceful shutdown cho ứng dụng JMS

Một quy trình shutdown có kiểm soát thường gồm:

1. Ngừng nhận công việc mới từ HTTP/API hoặc producer nội bộ.
2. Nếu nghiệp vụ yêu cầu, tạm ngừng producer phát message mới đến destination.
3. Gọi stop(Runnable) cho DMLC.
4. Chọn acceptMessagesWhileStopping theo chính sách xử lý message trong thời gian dừng.
5. Chờ callback xác nhận listener processing đã dừng, với timeout do ứng dụng quy định.
6. Sau callback, đóng database pool, service phụ trợ và các resource mà listener cần.
7. Đóng ApplicationContext để Spring destroy container và các bean còn lại.
8. Khi khởi động lại, start container sau khi dependency và broker đã sẵn sàng.

Nếu queue còn backlog sau khi container dừng, message vẫn có thể nằm trên broker và được consumer xử lý sau. Điều đó thường tốt hơn việc cố xử lý hết backlog trong một cửa sổ shutdown không giới hạn.

### 7.1. Giới hạn thời gian shutdown

Timeout chờ callback phải được chọn theo thời gian xử lý tối đa của listener và thời gian shutdown mà nền tảng triển khai cho phép.

Ví dụ:

~~~java
CountDownLatch stopped = new CountDownLatch(1);

container.stop(stopped::countDown);

if (!stopped.await(45, TimeUnit.SECONDS)) {
    // Ghi log/metric và áp dụng chính sách shutdown của ứng dụng.
}
~~~

Nếu listener có thể chạy lâu hơn 45 giây, ứng dụng cần quyết định liệu có chờ thêm, báo shutdown chưa hoàn tất hay chuyển sang cơ chế dừng khẩn cấp. Không nên giả định timeout của CountDownLatch tự dừng thread listener.

Listener nên có timeout cho các thao tác gọi HTTP, database và dịch vụ ngoài. Nếu một listener có thể treo vô hạn, callback stop cũng có thể không bao giờ hoàn tất.

## 8. Cấu hình mẫu cho DMLC

Ví dụ cấu hình container với local JMS transaction và không nhận message trong giai đoạn stopping:

~~~java
@Configuration
public class JmsListenerConfiguration {

    @Bean
    public DefaultMessageListenerContainer orderContainer(
            ConnectionFactory connectionFactory,
            MessageListener orderListener) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.queue");
        container.setMessageListener(orderListener);

        container.setConcurrentConsumers(2);
        container.setMaxConcurrentConsumers(8);

        container.setSessionTransacted(true);
        container.setAcceptMessagesWhileStopping(false);
        container.setReceiveTimeout(1_000);

        container.setAutoStartup(false);

        return container;
    }
}
~~~

Ứng dụng có thể start sau khi dependency sẵn sàng:

~~~java
container.start();
~~~

Và dừng có chờ callback:

~~~java
CountDownLatch stopped = new CountDownLatch(1);

container.stop(stopped::countDown);

if (!stopped.await(45, TimeUnit.SECONDS)) {
    throw new IllegalStateException(
            "Order listener did not stop before the deadline"
    );
}
~~~

Đây là cấu hình minh họa. Với Spring Framework 6 trở lên, JMS API dùng package jakarta.jms; ứng dụng Spring cũ có thể dùng javax.jms. Cần đồng bộ package với phiên bản framework và provider.

Nếu dùng external transaction manager, hãy cấu hình transactionManager phù hợp và kiểm tra cacheLevel theo quy tắc XA của application server. Không ép cache Session/Consumer nếu provider yêu cầu lấy resource mới trong phạm vi transaction.

## 9. Các tình huống cần kiểm thử

Kiểm thử lifecycle nên xác nhận hành vi thực tế thay vì chỉ kiểm tra isRunning():

- **Start:** container bắt đầu nhận message sau khi dependency đã sẵn sàng.
- **Stop khi rảnh:** invoker thoát vòng receive và callback được gọi.
- **Stop khi listener đang xử lý:** callback chỉ được gọi sau khi listener processing hoàn tất.
- **Stop với message đang chờ receive:** kiểm tra acceptMessagesWhileStopping=false và true trên provider thật.
- **Backlog:** message chưa nhận vẫn còn trên destination sau stop và được xử lý khi start lại.
- **Transaction rollback:** listener ném exception trong transacted Session; xác nhận redelivery theo provider.
- **Shutdown timeout:** listener xử lý lâu hơn deadline; xác nhận ứng dụng báo shutdown chưa hoàn tất.
- **Restart:** stop rồi start lại container; xác nhận Connection, Session và Consumer được tạo lại đúng lifecycle.
- **ApplicationContext close:** kiểm tra listener dừng trước database pool và các dependency khác.
- **Concurrent stop/start:** tránh restart container trước khi callback stop hoàn tất nếu ứng dụng phụ thuộc tín hiệu callback.

Theo dõi thêm activeConsumerCount, scheduledConsumerCount, thời gian xử lý message, số lần rollback/redelivery, số message trong backlog và thời gian từ lúc stop request đến callback.

## 10. Ví dụ Java 17: chờ message đang xử lý hoàn tất trước khi dừng worker

Ví dụ sau dùng BlockingQueue, ExecutorService và CountDownLatch để mô phỏng một worker đang xử lý message khi nhận yêu cầu stop. Worker hoàn tất message hiện tại, sau đó thoát vòng lặp; message còn lại trong queue vẫn chờ.

Đây là chương trình JDK thuần để minh họa lifecycle và callback chờ. Nó không thay thế DMLC, không kết nối JMS broker và không mô phỏng acknowledgement/redelivery của provider.

Tạo file **ListenerStopLifecycleDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ListenerStopLifecycleDemo {

    record DemoMessage(String id) {}

    public static void main(String[] args) throws Exception {
        BlockingQueue<DemoMessage> queue =
                new ArrayBlockingQueue<>(4);

        queue.add(new DemoMessage("M-1"));
        queue.add(new DemoMessage("M-2"));

        AtomicBoolean running = new AtomicBoolean(true);
        CountDownLatch processingStarted = new CountDownLatch(1);
        CountDownLatch finishCurrentMessage = new CountDownLatch(1);
        CountDownLatch stoppedCallback = new CountDownLatch(1);

        ExecutorService executor = Executors.newSingleThreadExecutor();

        Future<?> worker = executor.submit(() -> {
            try {
                while (running.get()) {
                    DemoMessage message =
                            queue.poll(5, TimeUnit.SECONDS);

                    if (message == null) {
                        continue;
                    }

                    System.out.println("Processing " + message.id());
                    processingStarted.countDown();

                    // Mô phỏng listener đang thực hiện nghiệp vụ.
                    finishCurrentMessage.await();

                    System.out.println("Processed " + message.id());
                }
            }
            catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
            finally {
                // Mô phỏng stop(Runnable) callback.
                stoppedCallback.countDown();
            }
        });

        try {
            if (!processingStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not start processing");
            }

            running.set(false);
            System.out.println(
                    "Stop requested; in-flight message is finishing");

            finishCurrentMessage.countDown();

            if (!stoppedCallback.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not stop before timeout");
            }

            worker.get();

            System.out.println("Stop callback invoked");
            System.out.println("Pending messages: " + queue.size());
        }
        finally {
            finishCurrentMessage.countDown();
            executor.shutdown();

            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac ListenerStopLifecycleDemo.java
java ListenerStopLifecycleDemo
~~~

Kết quả:

~~~text
Processing M-1
Stop requested; in-flight message is finishing
Processed M-1
Stop callback invoked
Pending messages: 1
~~~

Worker nhận M-1 và bắt đầu xử lý. Main thread gửi yêu cầu stop trong lúc message vẫn đang được xử lý. Worker hoàn tất M-1 rồi thoát; callback mô phỏng chỉ được phát sau khi worker dừng. M-2 vẫn nằm trong queue.

Trong DMLC thật, stop(Runnable) cung cấp callback tương tự sau khi listener processing thực sự dừng. Việc message còn lại được giữ, redelivery hay acknowledgement như thế nào phụ thuộc JMS provider và transaction/acknowledgement mode.

## 11. Lỗi thường gặp khi quản lý lifecycle

### 11.1. Nghĩ rằng stop() chờ toàn bộ queue rỗng

stop() dừng listener container. Nó không tự drain toàn bộ backlog trên broker.

Cách xử lý: nếu cần drain, dừng producer, quan sát backlog và đặt deadline rõ ràng; dùng stop callback để biết listener processing đã kết thúc.

### 11.2. Dùng isRunning() làm tín hiệu hoàn tất shutdown

isRunning() phản ánh trạng thái lifecycle. Khi stop được yêu cầu, nó có thể chuyển false trước khi listener invocation cuối cùng hoàn tất.

Cách xử lý: dùng stop(Runnable) callback hoặc cơ chế điều phối lifecycle của ApplicationContext.

### 11.3. Đóng database trước khi listener dừng

Listener đang chạy có thể còn cần database hoặc service phụ trợ. Đóng dependency quá sớm khiến xử lý đang diễn ra thất bại.

Cách xử lý: chờ callback stop hoàn tất rồi mới đóng dependency mà listener sử dụng.

### 11.4. Bật acceptMessagesWhileStopping và kỳ vọng shutdown luôn nhanh

Khi bật, các receive attempt đang chờ có thể tiếp tục nhận message, kể cả message mới đến. Nếu producer còn hoạt động, shutdown có thể kéo dài.

Cách xử lý: dừng producer trước hoặc giữ false nếu ưu tiên ngừng nhận nhanh.

### 11.5. Dùng AUTO_ACKNOWLEDGE cho nghiệp vụ không được mất message

DMLC acknowledge trước khi gọi listener ở chế độ mặc định. Listener lỗi không tự bảo đảm redelivery.

Cách xử lý: dùng sessionTransacted hoặc external transaction manager, đồng thời kiểm tra retry và DLQ của provider.

### 11.6. Restart trước khi stop callback hoàn tất

DMLC có thể không gọi callback stop nếu container được start lại trước khi quá trình dừng trước đó hoàn tất.

Cách xử lý: đợi callback rồi mới start lại khi ứng dụng cần dùng callback làm mốc lifecycle.

### 11.7. Gọi shutdown() khi chỉ muốn pause

shutdown() giải phóng Session/Consumer và đóng container. Đây là thao tác kết thúc resource lifecycle.

Cách xử lý: dùng stop() để pause và start() để tiếp tục; để Spring gọi destroy() khi bean thực sự bị hủy.

## 12. Quy tắc thiết kế

- Dùng start/stop cho pause và restart trong vòng đời container.
- Dùng stop(Runnable) để biết listener processing đã dừng thực sự.
- Dùng shutdown/destroy khi cần giải phóng resource.
- Quyết định rõ acceptMessagesWhileStopping dựa trên chính sách nhận message trong lúc dừng.
- Dùng transacted Session hoặc external transaction manager nếu cần độ tin cậy khi listener lỗi hoặc ứng dụng shutdown.
- Dừng producer và nguồn công việc mới trước khi dừng consumer nếu cần kiểm soát lượng message phát sinh.
- Chờ callback trước khi đóng database, HTTP client hoặc dependency listener cần.
- Đặt timeout shutdown ở cấp ứng dụng và có chính sách khi timeout.
- Theo dõi backlog, active consumer, rollback, redelivery và thời gian stop.
- Kiểm thử stop/start, broker restart và ApplicationContext close trên JMS provider thực tế.

DMLC hỗ trợ lifecycle theo chuẩn Spring để ứng dụng điều khiển lúc nhận message, lúc dừng listener và lúc giải phóng JMS resource. stop(Runnable) là tín hiệu đáng tin cậy để phối hợp graceful shutdown vì callback chỉ được gọi khi listener processing đã kết thúc. acceptMessagesWhileStopping quyết định cách xử lý các message được receive trong giai đoạn stopping; lựa chọn này cần đi cùng transaction, acknowledgement, retry và chính sách backlog của ứng dụng.

## Tài liệu tham khảo

- [Spring Framework 6.2: DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework 6.2: AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [Spring Framework: JMS integration reference](https://docs.spring.io/spring-framework/reference/integration/jms.html)