# Dừng nhận, hoàn tất phần đang xử lý và đóng consumer an toàn

> **Chương:** Consumer  
> **Phạm vi:** Java/JMS với Apache ActiveMQ Artemis và ActiveMQ Classic. Bài tập trung vào *graceful shutdown* của consumer chạy độc lập, bao gồm synchronous `receive()`, asynchronous `MessageListener`, transaction/acknowledgment và tác động của broker redelivery.

## 1. Tình huống: nhận SIGTERM khi đang xử lý đơn hàng

Một worker `fulfillment-worker` đang tiêu thụ queue `shutdown.jobs`. Mỗi message yêu cầu gọi hệ thống kho và cập nhật cơ sở dữ liệu trong 3–20 giây. Khi triển khai phiên bản mới, bộ điều phối gửi tín hiệu dừng tiến trình. Nếu worker đóng kết nối ngay, tác vụ đang chạy có thể bị ngắt sau khi DB đã commit nhưng trước khi JMS xác nhận; broker sẽ giao lại và có thể tạo vận đơn hai lần. Nếu worker tiếp tục nhận vô hạn thì lần triển khai không bao giờ dừng hoàn toàn.

Vì vậy, yêu cầu shutdown là:

1. **Ngừng bắt đầu công việc mới.** Sau khi nhận yêu cầu dừng, worker không lấy thêm job từ queue; job được broker hoặc worker khác xử lý sau.
2. **Cho phép tác vụ đang chạy hoàn tất trong hạn mức thời gian.** Nếu đã nhận job và bắt đầu thực hiện, xử lý xong rồi `commit()`/ACK đúng cách.
3. **Trả lại các message chưa xử lý.** Nếu nhận thêm message đúng lúc tín hiệu dừng nhưng chưa khởi động nghiệp vụ, `rollback()` trong transacted session thay vì âm thầm ACK.
4. **Đóng consumer, session và connection sau bước drain.** Giải phóng tài nguyên client và trả những delivery chưa commit về cơ chế redelivery của broker.
5. **Giữ giới hạn shutdown hữu hạn.** Nếu DB/API ngoài bị treo, không thể chờ mãi; cần timeout, readiness và grace period của tiến trình, đồng thời thiết kế handler idempotent.

**Graceful shutdown không bảo đảm exactly-once ở cấp nghiệp vụ.** Nó giảm khả năng công việc bị ngắt giữa chừng; vẫn phải chấp nhận redelivery khi broker/client mất kết nối hoặc khi tiến trình bị dừng cưỡng bức.

~~~mermaid
flowchart LR
    R[RUNNING: nhận job] -->|SIGTERM / yêu cầu dừng| Q[QUIESCING: không nhận job mới]
    Q -->|Có job đang xử lý| D[DRAINING: hoàn tất tác vụ]
    Q -->|Không có job đang xử lý| C[CLOSING]
    D -->|Nghiệp vụ thành công| A[Commit JMS / ACK]
    D -->|Không thể hoàn tất| B[Rollback / redelivery]
    A --> C
    B --> C
    C --> X[CLOSED: giải phóng consumer/session/connection]
~~~

Lưu ý `rollback()` không tự chạy bù tác vụ đã ghi ngoài JMS. Cụ thể, nếu HTTP gửi email thành công nhưng JMS rollback, lần giao lại vẫn có nguy cơ gửi email lần hai. Phần idempotency ở cuối bài giải quyết giới hạn đó.

## 2. Những phương thức JMS dễ nhầm trong shutdown

Giả sử ứng dụng có các đối tượng `Connection`, `Session` và `MessageConsumer` theo JMS truyền thống, hoặc `JMSContext` và `JMSConsumer` theo Jakarta Messaging.

| Thao tác | Tác động chính | Điều **không** được suy ra |
|---|---|---|
| Đặt cờ `stopRequested=true` trong ứng dụng | Worker chủ động không gọi `receive()` ở vòng tiếp theo | Broker chưa tự đóng consumer hoặc thu hồi message đã nhận |
| `Connection.stop()` hoặc `JMSContext.stop()` | Tạm dừng **delivery của các consumer dùng cùng connection**; chờ các `MessageListener` đang chạy hoàn tất rồi mới trả về | Không đóng connection, không commit/ACK transaction, không xóa queue |
| `MessageConsumer.close()` / `JMSConsumer.close()` | Đóng **consumer này**; nếu có `receive()` hoặc listener đang thực thi ở thread khác thì thao tác close phải chờ phù hợp với đặc tả | Không bảo đảm side effect ngoài JMS đã hoàn tất |
| `Session.commit()` / `JMSContext.commit()` | Commit transaction JMS: xác nhận các message đã tiêu thụ trong transaction và hoàn tất các lệnh gửi thuộc transaction đó | Không commit luôn DB transaction bên ngoài nếu không có cơ chế phối hợp |
| `Session.rollback()` / `JMSContext.rollback()` | Hủy transaction JMS hiện tại; message đã nhận mà chưa commit đủ điều kiện giao lại theo policy | Không đảo ngược email, HTTP request hoặc DB commit trước đó |
| `Session.close()` | Đóng session/consumer của session; **rollback** transaction local đang mở | Không tự commit một transaction chưa commit |
| `Connection.close()` / `JMSContext.close()` | Chấm dứt tài nguyên JMS, chờ các callback/receive liên quan kết thúc theo hợp đồng API; transaction local chưa commit được rollback | Không tương đương “xử lý tất cả job đang treo thành công” |

Hai điểm của chuẩn Jakarta Messaging đặc biệt quan trọng:

- `Connection.stop()` **không trả về trước khi các listener hiện tại trả về**. Trong thời gian đó, callback đang chạy vẫn có quyền sử dụng các chức năng connection/session của nó để hoàn tất xử lý. Một `receive(timeout)` trên connection đã stop vẫn có thể hết timeout và trả về `null`.
- `Session.close()` và `JMSContext.close()` **không auto-commit** transaction còn dở. Với session `CLIENT_ACKNOWLEDGE`, việc close connection cũng không ép ACK các message chưa xác nhận.

### Tránh gọi stop/close từ chính `onMessage()`

Một `MessageListener` không nên gọi `connection.stop()`, `connection.close()`, `session.close()`, `context.stop()` hoặc `context.close()` trên các đối tượng chứa chính callback ấy. Jakarta Messaging cho phép các implementation hoặc ném `IllegalStateException`/`IllegalStateRuntimeException` hoặc thực hiện hành vi dừng/đóng nhất định, nên mã như vậy **không portable**. Trong một số mô hình cũ, nó còn có nguy cơ chờ vòng và deadlock.

Ngoại lệ theo đặc tả: callback **được phép** đóng chính `MessageConsumer`/`JMSConsumer` của nó. Tuy vậy, để dễ kiểm soát shutdown toàn worker, bài này dùng **luồng điều phối riêng** để yêu cầu dừng, còn callback tự kết thúc xử lý.

**Không gọi đồng thời các phương thức session tùy ý từ nhiều thread.** `Session`/`JMSContext` thông thường có giới hạn sử dụng theo một thread; ứng dụng nên để thread đang sở hữu session thực hiện `receive`, `commit`, `rollback`. Việc `close` được cho phép đồng thời trong một số tình huống không biến mọi thao tác của session thành thread-safe.

## 3. Chọn chiến lược theo cách nhận message

### 3.1. Consumer nhận đồng bộ bằng `receive(timeout)`

Đây là đường đi dễ kiểm soát nhất cho một worker:

~~~text
while (!stopRequested) {
    message = consumer.receive(500 ms);
    if (message == null) continue;

    if (stopRequested) {
        session.rollback();   // Vừa nhận nhưng chưa xử lý: trả lại.
        break;
    }

    processBusiness(message); // Hoàn tất hoặc lỗi có kiểm soát.
    session.commit();         // Chỉ sau khi nghiệp vụ thành công.
}

consumer.close();
session.close();
connection.close();
~~~

Một callback shutdown hook **chỉ đặt cờ dừng**. Worker thực hiện mọi thao tác JMS theo thứ tự trong chính thread của nó. Lựa chọn `receive(500)` thay vì `receive()` vô hạn cho phép quan sát tín hiệu dừng nhanh ngay cả khi queue đang rỗng; khoảng 500 ms là con số ví dụ, cần cân bằng độ trễ shutdown và overhead thực tế.

**Cửa sổ race:** nếu lệnh `receive()` vừa trả về một message đúng lúc tín hiệu dừng xuất hiện, kiểm tra lại `stopRequested` **sau receive**. Nếu chưa bắt đầu nghiệp vụ, rollback message đó và thoát; nếu đã bắt đầu, cố gắng hoàn tất message rồi commit trong hạn mức.

### 3.2. Consumer bất đồng bộ dùng `MessageListener`

Với `consumer.setMessageListener(listener)`, thread do provider gọi `onMessage()`. Nếu gọi `Connection.stop()` từ **luồng điều phối khác**, provider phải đợi những callback đang chạy trả về; các callback đó vẫn phải thực hiện `commit()` hoặc `rollback()` trước khi trả về.

~~~mermaid
sequenceDiagram
    participant O as Orchestrator
    participant M as Shutdown controller
    participant J as JMS Connection
    participant L as onMessage()
    participant D as Business DB
    O->>M: SIGTERM
    M->>J: stop() từ luồng điều phối
    Note over J: Không phát callback mới
    L->>D: Hoàn tất xử lý hiện tại
    D-->>L: Commit DB
    L->>J: JMS session.commit()
    L-->>J: onMessage() trả về
    J-->>M: stop() trả về
    M->>J: close consumer/session/connection
~~~

**Cẩn thận với xử lý bất đồng bộ bên trong callback:** Nếu `onMessage()` chỉ `executor.submit(job)` rồi trả về ngay, `Connection.stop()` có thể trả về khi job trong executor **vẫn đang chạy**. Khi ấy phải tự quản lý `inFlight`, drain executor có timeout và ràng buộc ACK với kết quả xử lý. Với `Session` không thread-safe, không được tùy tiện gọi `session.commit()` từ task trong executor khác.

### 3.3. Chọn ACK mode cho phép drain có ý nghĩa

| Chế độ | Thời điểm acknowledgment | Phù hợp khi shutdown? |
|---|---|---|
| `AUTO_ACKNOWLEDGE` + synchronous receive | Provider tự xác nhận khi `receive()` trả message thành công theo JMS | **Không phù hợp** nếu nghiệp vụ chỉ bắt đầu xử lý sau `receive()` và cần rollback khi lỗi |
| `AUTO_ACKNOWLEDGE` + MessageListener | Provider tự xác nhận khi `onMessage()` trả về thành công | Có thể dùng cho handler ngắn, nhưng thiếu điểm commit tường minh của nghiệp vụ ngoài JMS |
| `CLIENT_ACKNOWLEDGE` | Code gọi `message.acknowledge()`; thao tác có thể ACK **mọi message đã nhận trong cùng session** | Cần kiểm soát số message unacked; không hiểu lầm ACK riêng message hiện tại |
| `SESSION_TRANSACTED` | Code gọi `commit()`/`rollback()` sau mỗi đơn vị việc JMS | **Được dùng trong bài lab**, vì ranh giới hoàn tất dễ kiểm chứng |

Đối với shutdown cần chờ một message xử lý xong rồi xác nhận, transacted session là lựa chọn rõ ràng. Tuy nhiên transaction JMS chỉ bao trùm **các thao tác JMS thuộc session**, trừ khi ứng dụng được cấu hình phối hợp transaction với tài nguyên khác bằng cơ chế phù hợp. Đừng đặt DB commit và JMS commit vào cùng một lời gọi rồi giả định chúng nguyên tử.

## 4. Chuẩn bị broker và message thử nghiệm

Ví dụ dùng một broker **ActiveMQ Artemis** local, acceptor CORE ở `tcp://127.0.0.1:61616`. Dùng một queue anycast tồn tại trước khi producer phát message.

Trong `ARTEMIS_INSTANCE/etc/broker.xml`, đặt cấu hình sau **bên trong section `<addresses>` đã có**:

~~~xml
<address name="shutdown.jobs">
    <anycast>
        <queue name="shutdown.jobs">
            <durable>true</durable>
        </queue>
    </anycast>
</address>
~~~

Chỉ thêm nếu chưa có address/queue cùng tên, giữ nguyên các phần cấu hình broker khác. User thực hành cần quyền `send` cho producer và `consume` cho consumer trên address này; có thể dùng tài khoản lab được cấp quyền tương ứng.

Ví dụ chính sách redelivery đặt trong `<address-settings>` hiện có nếu muốn quan sát retry:

~~~xml
<address-setting match="shutdown.jobs">
    <redelivery-delay>1000</redelivery-delay>
    <max-delivery-attempts>5</max-delivery-attempts>
    <dead-letter-address>DLQ</dead-letter-address>
</address-setting>
~~~

`DLQ` phải được khai báo hoặc được broker cấp phát theo cấu hình cụ thể. Không mặc định mọi instance đều có sẵn queue này; kiểm tra trước khi dùng. Các chính sách khác như TTL, expiry và địa chỉ không có consumer cũng ảnh hưởng số message tồn.

**Phân biệt broker:** ActiveMQ Classic sử dụng cơ chế và cấu hình destination/redelivery khác Artemis. Mẫu `broker.xml` ở trên là **riêng Artemis**; thuật toán graceful shutdown dùng các API JMS tiêu chuẩn nên có thể áp dụng sang Classic sau khi thay ConnectionFactory, namespace và cấu hình broker cho đúng bản đang chạy.

## 5. Mã Java hoàn chỉnh: graceful shutdown cho synchronous consumer

### 5.1. Điều kiện chạy

Ví dụ dùng Java 17, Artemis Jakarta Messaging client và tài khoản có quyền consume. Trong `pom.xml` của một dự án thực hành riêng:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <artemis.version>2.33.0</artemis.version>
</properties>
<dependencies>
    <dependency>
        <groupId>org.apache.activemq</groupId>
        <artifactId>artemis-jakarta-client</artifactId>
        <version>${artemis.version}</version>
    </dependency>
</dependencies>
~~~

Phiên bản client ở đây là **ví dụ đã công bố** để minh họa một bộ dependency; khi chạy thực tế phải kiểm tra tương thích Java, broker và namespace API. Nếu ứng dụng dùng `javax.jms.*`, chọn dòng client tương ứng; đừng trộn với `jakarta.jms.*`.

Cung cấp `ARTEMIS_USER` và `ARTEMIS_PASSWORD` qua environment của tiến trình. Đặt password thực tế trong secret/configuration của môi trường, không ghi thẳng vào mã nguồn.

### 5.2. Consumer có cờ dừng, transaction và shutdown hook

~~~java
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.concurrent.atomic.AtomicBoolean;

public final class GracefulOrderConsumer {
    private static final String URL = "tcp://127.0.0.1:61616";
    private static final String QUEUE = "shutdown.jobs";
    private static final long POLL_MS = 500;
    private static final long SHUTDOWN_WAIT_MS = 35_000;

    public static void main(String[] args) throws InterruptedException {
        AtomicBoolean stopRequested = new AtomicBoolean(false);

        Thread worker = new Thread(
            () -> runWorker(stopRequested), "jms-consumer-worker");

        // Hook không gọi JMSContext.close()/stop() trên thread worker.
        // Nó chỉ ra tín hiệu dừng và đợi worker tự hoàn tất.
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            System.out.println("[shutdown] yêu cầu ngừng nhận job");
            stopRequested.set(true);
            try {
                worker.join(SHUTDOWN_WAIT_MS);
                if (worker.isAlive()) {
                    System.err.println(
                        "[shutdown] quá hạn drain, tiến trình sắp thoát; "
                        + "message chưa commit có thể được giao lại");
                } else {
                    System.out.println("[shutdown] worker đã đóng JMS");
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        }, "jms-shutdown-hook"));

        worker.start();
        worker.join();
    }

    private static void runWorker(AtomicBoolean stopRequested) {
        String user = requiredEnv("ARTEMIS_USER");
        String password = requiredEnv("ARTEMIS_PASSWORD");

        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory(URL);

        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {

            context.setAutoStart(false);
            Queue queue = context.createQueue(QUEUE);
            JMSConsumer consumer = context.createConsumer(queue);
            context.start();

            System.out.println("[worker] bắt đầu nhận message");
            while (!stopRequested.get()) {
                Message message = consumer.receive(POLL_MS);
                if (message == null) {
                    continue; // Hết timeout; quay lại kiểm tra cờ dừng.
                }

                if (stopRequested.get()) {
                    // Race: message vừa được nhận, nghiệp vụ chưa bắt đầu.
                    context.rollback();
                    System.out.println(
                        "[worker] trả message chưa xử lý về queue");
                    break;
                }

                try {
                    process(message);  // Có timeout nghiệp vụ thực tế.
                    context.commit();  // ACK message trong JMS transaction.

                    System.out.println("[worker] committed "
                        + message.getStringProperty("eventId"));
                } catch (Exception failure) {
                    try {
                        context.rollback();
                    } catch (Exception rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }

                    if (failure instanceof InterruptedException) {
                        Thread.currentThread().interrupt();
                    }
                    System.err.println(
                        "[worker] lỗi, đã thử rollback: " + failure);

                    // Dừng demo để tránh lặp nhanh một poison message.
                    // Production cần retry/backoff/DLQ và chính sách alert.
                    break;
                }
            }

            // Chỉ có thread worker thao tác JMSContext và consumer.
            // Không còn nghiệp vụ đang xử lý tại thời điểm này.
            context.stop();
            consumer.close();
            System.out.println("[worker] consumer đã đóng an toàn");
        } catch (Exception failure) {
            // Nếu kết nối lỗi khi stop/close, provider sẽ quyết định
            // redelivery các message chưa được commit.
            System.err.println("[worker] JMS bị lỗi: " + failure);
        }
    }

    private static void process(Message message) throws Exception {
        if (!(message instanceof TextMessage text)) {
            throw new IllegalArgumentException(
                "Bài lab chỉ chấp nhận TextMessage");
        }

        String eventId = text.getStringProperty("eventId");
        System.out.println(
            "[business] bắt đầu eventId=" + eventId
            + ", body=" + text.getText());

        // Giả lập một tác vụ 3 giây. Hệ thống thật cần timeout
        // HTTP/DB riêng, idempotency và quản lý lỗi có kiểm soát.
        Thread.sleep(3_000);

        System.out.println("[business] hoàn tất eventId=" + eventId);
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến " + key);
        }
        return value;
    }
}
~~~

### 5.3. Tại sao thiết kế này xử lý được ba thời điểm dừng?

| Khi tín hiệu dừng xuất hiện | Điều worker thực hiện |
|---|---|
| Đang đợi trong `receive(500)` | Chờ timeout/nhận message, kiểm tra cờ, không bắt đầu việc mới |
| `receive()` vừa trả message nhưng chưa vào `process()` | `rollback()` rồi thoát vòng lặp; message có thể được giao lại |
| Đã ở trong `process()` | Hoàn tất xử lý, gọi `commit()`; sau đó nhận ra cờ dừng và đóng JMS |

**Quan sát code:** cờ dừng được kiểm tra trước vòng lặp và sau khi `receive` trả về. Khi tín hiệu dừng đến **trong `process()`**, hook **không interrupt worker**; worker được tiếp tục để commit. Chính sách dừng hữu hạn được giới hạn bằng `SHUTDOWN_WAIT_MS` và timeout của các I/O thực tế.

Mã trên dành cho **một worker / một session**. Nếu cần xử lý nhiều job song song, tạo nhiều worker độc lập có session/context riêng và chờ tất cả hoàn tất. Không chia sẻ một `JMSContext` giữa các worker thread.

**Lưu ý quan trọng về thời hạn:** Nếu shutdown hook đợi 35 giây nhưng công việc ngoài JMS treo vô hạn, khi hook kết thúc JVM có thể bị hệ điều hành/bộ điều phối kết thúc trước lúc context kịp close. Message chưa commit phải được phép redelivery. Không ghi nhận “shutdown thành công hoàn toàn” chỉ vì hook đã trả về.

### 5.4. Producer để tạo dữ liệu thử nghiệm

Chạy chương trình sender sau khi broker và queue đã sẵn sàng. Nó gửi 5 message persistent trong một JMS transaction:

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class GracefulTestPublisher {
    public static void main(String[] args) throws Exception {
        String user = System.getenv("ARTEMIS_USER");
        String password = System.getenv("ARTEMIS_PASSWORD");
        if (user == null || user.isBlank()
                || password == null || password.isBlank()) {
            throw new IllegalStateException("Thiếu tài khoản Artemis");
        }

        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");

        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue queue = context.createQueue("shutdown.jobs");
            for (int i = 1; i <= 5; i++) {
                String eventId = "shutdown-lab-" + i;
                TextMessage message = context.createTextMessage(
                    "{\"eventId\":\"" + eventId + "\"}");
                message.setStringProperty("eventId", eventId);

                context.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .send(queue, message);
            }
            context.commit();
            System.out.println("Đã publish 5 message.");
        }
    }
}
~~~

Ở đây `eventId` cố định chỉ phục vụ bài lab. Trong hệ thống thật, nó phải được cấp một lần cho **cùng một sự kiện nghiệp vụ**, giữ nguyên khi gửi lại sau timeout và được consumer dùng để chống xử lý trùng.

## 6. Thực hành SIGTERM: dừng nhận nhưng vẫn hoàn tất job đang chạy

### 6.1. Kiểm chứng lần chạy bình thường

1. Dùng Artemis Console xác nhận queue `shutdown.jobs` đang rỗng và không có consumer khác.
2. Chạy `GracefulTestPublisher` một lần. Queue có 5 message nếu đã commit và chưa ai consume.
3. Khởi động `GracefulOrderConsumer` trong một terminal.
4. Quan sát cặp log `[business] bắt đầu` → `[business] hoàn tất` → `[worker] committed` cho từng message; mỗi job giả lập mất khoảng 3 giây.
5. Để worker nhận hết năm message và quan sát queue count về 0; sau đó yêu cầu dừng.

Kết quả mong đợi: worker không cần tạo message mới khi shutdown; `context.stop()` và `consumer.close()` được chạy sau cùng, connection/session đóng bởi `try-with-resources`.

### 6.2. Kiểm chứng dừng khi đang xử lý

1. Làm queue trở lại trạng thái rỗng; chạy publisher để tạo 5 message.
2. Bật consumer, chờ log bắt đầu xử lý một message.
3. Yêu cầu dừng tiến trình: trên Linux/macOS có thể gửi `SIGTERM` bằng công cụ điều phối hoặc lệnh `kill -TERM <pid>`; trong terminal tương tác có thể dùng Ctrl+C. Trên Windows, Ctrl+C trong console có thể kích hoạt shutdown hook; việc “End task” cưỡng bức không nhất thiết chạy hook.
4. Theo dõi: hook in `yêu cầu ngừng nhận job`, message đang chạy tiếp tục `hoàn tất` và `committed`, sau đó worker đóng consumer.
5. Mở lại consumer để xử lý message còn nằm trong queue.

Ví dụ trình tự log khả dĩ:

~~~text
[worker] bắt đầu nhận message
[business] bắt đầu eventId=shutdown-lab-1
[shutdown] yêu cầu ngừng nhận job
[business] hoàn tất eventId=shutdown-lab-1
[worker] committed shutdown-lab-1
[worker] consumer đã đóng an toàn
[shutdown] worker đã đóng JMS
~~~

Không yêu cầu **đúng một message** được commit trước shutdown ở mọi lần chạy: thời điểm gửi SIGTERM, prefetch và tốc độ xử lý có thể khác nhau. Kết quả cần kiểm là *không có job mới được chủ ý bắt đầu sau khi cờ dừng đã được quan sát; job đang xử lý có commit hoặc rollback rõ ràng; message còn lại không bị mất*.

### 6.3. Các phép thử lỗi quan trọng

| Phép thử | Điều cần quan sát | Diễn giải |
|---|---|---|
| Dừng khi queue trống | Worker thoát sau thời gian poll; không treo ở `receive()` vô hạn | Cờ dừng có hiệu lực |
| Dừng lúc job đang chạy | Job hoàn tất rồi JMS commit trước close | Drain hoạt động |
| Tạo exception trong `process()` | JMS rollback; message đủ điều kiện redelivery theo policy | Không ACK nhầm job lỗi |
| Dừng cưỡng bức, hook không kịp chạy | Broker phát hiện session/connection mất; message chưa commit có thể được giao lại | Graceful shutdown **không thay thế** idempotency |
| Giảm grace period ngắn hơn thời gian xử lý | Worker có nguy cơ bị kill trước commit | Cần điều chỉnh timeout I/O và thời hạn dừng |
| Hai consumer cạnh tranh cùng queue | Consumer mới có thể xử lý phần backlog còn lại | Queue tiếp tục phục vụ sau khi một instance dừng |

Đo thêm `delivering count` hoặc số message unacknowledged bên broker nếu công cụ quản trị có hỗ trợ; queue depth một mình có thể khiến bạn nhầm message đang **in-flight** với message đã ACK.

## 7. Consumer callback: dừng an toàn với `MessageListener`

Với ứng dụng dùng JMS API truyền thống, ví dụ theo một luồng listener:

~~~java
Connection connection = factory.createConnection(user, password);
Session session = connection.createSession(
    true, Session.SESSION_TRANSACTED);
Queue queue = session.createQueue("shutdown.jobs");
MessageConsumer consumer = session.createConsumer(queue);

consumer.setMessageListener(message -> {
    try {
        processBusiness(message); // Chạy đồng bộ ngay trong onMessage.
        session.commit();         // ACK ngay khi tác vụ hoàn tất.
    } catch (Exception failure) {
        try {
            session.rollback();
        } catch (JMSException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        logFailure(failure);
    }
});
connection.start();
~~~

Đoạn trên là **mẫu logic đặt trong một lớp có các hàm `processBusiness` và `logFailure`**, không phải chương trình độc lập có thể biên dịch ngay. Tạo các đối tượng bằng client phù hợp với `jakarta.jms.*` hoặc `javax.jms.*`; listener chỉ dùng **session của chính nó**, không giao `Session` sang các thread khác.

Khi cần shutdown, **luồng điều phối** — không phải `onMessage()` — gọi:

~~~java
// Phải chạy từ thread điều phối lifecycle bên ngoài callback.
connection.stop();   // Đợi mọi onMessage đang chạy kết thúc.
consumer.close();    // Đóng consumer sau khi đã tạm dừng delivery.
session.close();     // Không còn transaction chưa commit.
connection.close();  // Giải phóng socket và tài nguyên provider.
~~~

Nếu callback cần thời gian 20 giây, `connection.stop()` có thể chờ tới khi callback trả về. Nếu callback đã xử lý DB thành công nhưng `session.commit()` lỗi, catch cần rollback nếu còn khả thi và **không đánh dấu job thành công**; message vẫn có thể bị giao lại.

**Vấn đề định nghĩa “in-flight”:** Với JMS listener, hợp đồng `stop()` chờ tới lúc `onMessage()` trả về. Nếu callback dispatch sang thread pool rồi trả về ngay, điều phối phải **tự** chờ pool drain và xây dựng quy tắc xác nhận an toàn; không thể dựa một mình vào `connection.stop()`. Cách dễ an toàn là callback xử lý và commit **đồng bộ trong chính thread của listener**, hoặc sử dụng listener container/framework đã giải quyết vòng đời session và acknowledgment.

### Những thao tác cần tránh

~~~java
consumer.setMessageListener(message -> {
    // KHÔNG làm như sau:
    // connection.stop();  // Có thể lỗi hoặc gây hành vi không portable.
    // session.close();    // Không portable từ chính listener.
    // connection.close(); // Không portable từ chính listener.
});
~~~

Cũng không nên dùng `setMessageListener(null)` tùy tiện khi listener đang xử lý; đặc tả không bảo đảm mọi hành vi khi thay listener đồng thời. Nếu cần dừng một consumer, hãy dùng lifecycle rõ ràng, và gọi `close`/`stop` ở thời điểm thích hợp.

## 8. Liên hệ với ActiveMQ Artemis, Classic và consumer buffer

Khi broker gửi message, client có thể **nhận trước/prefetch** để tăng throughput. Vì vậy không được suy rằng “worker chưa gọi `process()`” thì message chắc chắn vẫn ở trạng thái ready trên broker.

- **ActiveMQ Artemis:** client có consumer window/credit và khả năng buffering. Một số message có thể đang được broker ghi nhận là *delivering*, dù ứng dụng chưa xử lý xong. Nếu session đóng mà chưa ACK/commit, các message đó đủ điều kiện quay lại queue theo cơ chế của broker.
- **ActiveMQ Classic:** client có chính sách prefetch, redelivery và failover riêng. Có thể có message đã dispatch tới consumer trước khi shutdown. Cần đo `in-flight` và kiểm tra chính sách redelivery của đúng phiên bản.
- **Cả hai:** graceful close của một consumer queue **không xóa queue** và không xóa backlog đã lưu. Với **durable topic subscription**, đóng consumer không tương đương gọi `unsubscribe()`; durable subscription vẫn tồn tại khi không có subscriber online, theo chính sách broker.

Nếu mục tiêu là giảm “message đang được giữ ở client”, có thể thử các thiết lập consumer window/prefetch của provider trong môi trường tải thật. Tuy nhiên hạ prefetch có thể giảm throughput đáng kể; không cần thay chúng để triển khai cơ chế stop–drain–commit–close đúng.

## 9. Deadline shutdown và hành vi khi vượt hạn

Một consumer ngoài đời thường được dừng bởi systemd, Docker hoặc Kubernetes. Bộ điều phối thường cho tiến trình một **khoảng grace period**, rồi có thể dừng cưỡng bức. Ví dụ:

~~~yaml
# Mảnh cấu hình Pod/Deployment; đặt trong spec.template.spec phù hợp.
terminationGracePeriodSeconds: 45
~~~

Giả sử:

- Một job có timeout ở tầng HTTP/DB tối đa **20 giây**.
- Poll `receive(500)` có độ trễ kiểm tra cờ tối đa cỡ **0,5 giây** nếu không lỗi.
- Shutdown hook chờ worker tối đa **35 giây**.
- Grace period của orchestrator là **45 giây** để còn khoảng dự phòng.

Đây là ngân sách **minh họa**, phải đo từ percentile xử lý thực tế. Nếu job có thể chạy 3 phút, một grace period 45 giây không đủ để luôn hoàn tất; cần chia nhỏ job, checkpoint, timeout/cancellation hoặc chính sách broker redelivery phù hợp.

**Lưu ý về SIGTERM và readiness:** trước khi drain, ứng dụng nên ngừng nhận yêu cầu hoặc job mới theo lifecycle của nó. Với consumer polling, cờ dừng có hiệu lực sau vòng lặp/poll; với listener, dùng phương thức `stop()` của connection từ thread điều phối. Nếu triển khai dùng Spring JMS, Quarkus hoặc application server, ưu tiên lifecycle listener container do framework quản lý và kiểm chứng `stop/close/ack` thực tế. Không tự đóng một `JMSContext` được container inject nếu Jakarta EE quản lý vòng đời nó.

Khi quá deadline:

1. Ghi nhận timeout và state của job đang chạy, nếu còn có thể.
2. Đừng ACK/commit cho job chưa đạt điều kiện nghiệp vụ.
3. Để broker phục hồi message khi session/connection mất; xử lý duplicate theo `eventId`.
4. Không dùng `Thread.stop()` hoặc tự động “ACK tất cả cho nhanh” chỉ để tiến trình tắt đúng giờ.

Shutdown hook không thể bảo đảm chạy khi bị `SIGKILL`, kernel panic, mất điện hoặc JVM crash. Đây là lý do hệ thống vẫn cần persistence, redelivery và idempotency bên cạnh graceful shutdown.

## 10. Idempotency và transaction khi message được giao lại

Một trường hợp mất kết nối:

~~~mermaid
sequenceDiagram
    participant B as ActiveMQ broker
    participant C as Consumer
    participant D as Business DB
    B->>C: Job eventId=E-100
    C->>D: INSERT/UPDATE nghiệp vụ
    D-->>C: DB commit thành công
    Note over C: JVM chết trước JMS commit
    B->>C: Redelivery E-100
    C->>D: Kiểm tra E-100 đã xử lý
    D-->>C: Bỏ qua side effect trùng
    C->>B: JMS commit
~~~

Nếu công việc cập nhật DB, một mẫu phổ biến:

~~~sql
BEGIN;

-- Cần ràng buộc UNIQUE trên (consumer_name, event_id).
INSERT INTO processed_messages (consumer_name, event_id)
VALUES ('fulfillment-worker', 'E-100');

-- Cùng DB transaction, chỉ cập nhật khi chưa xử lý event.
UPDATE orders
SET status = 'READY_FOR_SHIPPING'
WHERE order_id = 'ORD-100'
  AND status = 'PAID';

COMMIT;
~~~

Nếu lần redelivery gặp lỗi unique, handler phân loại đó là **event đã xử lý**, không chạy lại side effect rồi vẫn hoàn tất JMS transaction. Bắt buộc thao tác chống trùng và nghiệp vụ được điều phối trong **cùng transaction DB**; mô hình “`SELECT` thấy chưa có rồi `INSERT` sau” không đủ nếu nhiều replica chạy đồng thời.

Với API ngoài như gửi email hoặc tạo vận đơn, cần thêm idempotency key do downstream hỗ trợ, hoặc outbox/saga phù hợp. JMS transaction không làm email đã gửi được “rollback” nếu message phải giao lại.

## 11. Checklist quan sát và lỗi thường gặp

| Hiện tượng | Nguyên nhân cần xem | Cách khắc phục |
|---|---|---|
| Shutdown không thoát khi queue rỗng | Dùng `receive()` chờ vô hạn, không có cơ chế wake-up | Poll `receive(timeout)` hoặc lifecycle stop/close có kiểm soát |
| Consumer thoát nhưng job đang chạy bị mất tác động | ACK trước khi xử lý, hoặc tiến trình bị kill giữa tác vụ | Đổi ranh giới ACK/transaction, tăng grace period, idempotency |
| `Connection.stop()` mất nhiều giây | `MessageListener` đang xử lý, stop **chờ listener trở về** | Đặt timeout cho tác vụ, đo thời gian drain |
| Stop được nhưng broker còn nhiều message `delivering` | Prefetch/client buffer, transaction chưa commit | Kiểm tra consumer window/prefetch và trạng thái session; không kết luận mất message |
| `Session.close()` làm message quay lại | Transaction chưa commit nên close rollback | Commit sau xử lý thành công; rollback có chủ đích khi lỗi |
| Stop được nhưng app chưa tắt | `stop()` chỉ **tạm dừng delivery**, connection/session vẫn mở | Đóng consumer/session/connection theo thứ tự sau drain |
| Hook bị timeout | I/O downstream treo hoặc job dài hơn budget | Cấu hình timeout/cancellation, giảm kích thước job, tăng grace period phù hợp |
| Một event được xử lý hai lần sau restart | DB commit trước JMS ACK; broker redelivery | Unique idempotency key và side effect an toàn |
| Gọi `connection.close()` trong `onMessage()` báo lỗi | Không portable theo đặc tả | Dời shutdown về thread quản lý lifecycle |
| Queue trống nhưng DLQ tăng | Poison message retry đến giới hạn, chuyển dead-letter | Điều tra nguyên nhân, dùng replay có kiểm soát |
| Hai message được ACK chung ngoài ý định | Dùng `CLIENT_ACKNOWLEDGE` với nhiều delivery trong một session | Tách session hoặc dùng transaction JMS rõ ràng |

### Nên theo dõi những chỉ số nào?

- **In-flight/processing count** trong ứng dụng, thời gian xử lý job và số transaction JMS commit/rollback.
- **Queue ready/delivering count**, consumer count, redelivery count, DLQ growth và tuổi message cũ nhất.
- **Shutdown requested timestamp**, thời gian drain, số shutdown thành công và số lần vượt deadline.
- **Idempotency duplicate-detected count**, số side effect không thể khôi phục và lỗi của DB/API downstream.

Không tuyên bố shutdown an toàn chỉ vì process exit code bằng 0; kiểm tra broker backlog, unacknowledged delivery, tác vụ dở dang và side effect thực tế.

## 12. Bài tập tự kiểm tra

1. Consumer có `AUTO_ACKNOWLEDGE` và gọi synchronous `receive()` rồi mất 10 giây xử lý DB. Nếu tiến trình chết ở giây thứ 5, rủi ro gì khiến job không được giao lại?
2. Tại sao `Connection.stop()` khác `Connection.close()`? `stop()` có tự commit transaction JMS chưa xong không?
3. Hãy giải thích vì sao shutdown hook trong ví dụ **chỉ đặt cờ** và gọi `join()` thay vì tự gọi `context.close()` từ thread của hook.
4. Khi SIGTERM đến trong lúc `process()` đã bắt đầu, khi nào nên `commit()` và khi nào nên `rollback()`?
5. Với ba `MessageListener` đang chạy trên các session khác nhau nhưng dùng cùng connection, điều gì xảy ra khi thread điều phối gọi `connection.stop()`?
6. Nếu `onMessage()` gửi job vào một executor rồi trả về ngay, `Connection.stop()` đã đủ để bảo đảm job của executor hoàn tất chưa?
7. Broker Artemis báo `delivering count = 8` ngay trước khi một consumer đóng. Điều đó có nghĩa cả tám message đã được ứng dụng ACK chưa?
8. Vì sao tăng `terminationGracePeriodSeconds` lên 120 giây vẫn không thay thế idempotency nếu DB commit xong rồi JMS commit thất bại?

**Đáp án gợi ý:** (1) synchronous `AUTO_ACKNOWLEDGE` có thể ACK khi `receive()` trả về nên side effect bị thiếu; (2) stop tạm dừng delivery, không đóng/commit; (3) tránh thao tác đồng thời trên session/context và bảo đảm worker tự xử lý/commit; (4) xử lý thành công thì commit, thất bại hoặc chưa bắt đầu thì rollback; (5) stop chờ các listener đang chạy hoàn tất; (6) chưa, phải drain executor và quản lý ACK; (7) chưa, có thể chỉ ở client buffer/in-flight; (8) crash và mất kết nối vẫn có thể tạo duplicate, cần khóa nghiệp vụ.

## 13. Tài liệu chuẩn để đối chiếu

- [Jakarta Messaging — Connection API](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/connection): ý nghĩa `stop()`, `close()` và các ràng buộc với callback.
- [Jakarta Messaging — JMSContext API](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/jmscontext): `stop()`, `close()`, transaction/rollback và hạn chế của context do container quản lý.
- [Jakarta Messaging — Session API](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/session): thread confinement, `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE`, `commit()`/`rollback()` và `close()`.
- [Jakarta Messaging — MessageConsumer API](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/messageconsumer): cách `close()` tương tác với `receive()` và `MessageListener`.
- [ActiveMQ Artemis — Message Redelivery and Undelivered Messages](https://artemis.apache.org/components/artemis/documentation/latest/undelivered-messages): delayed redelivery, max delivery attempts và DLQ.
- [ActiveMQ Artemis — Address Model](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html): queue/address định tuyến và các loại routing.

**Kết luận:** Dừng consumer an toàn là một **quy trình có trạng thái**, không phải một lời gọi `close()` đơn lẻ: *ngừng nhận → hoàn tất hoặc rollback job đang xử lý → commit/ACK đúng ranh giới → đóng consumer/session/connection → kiểm tra backlog/redelivery*. Với polling consumer, một cờ dừng và `receive(timeout)` giúp giữ mọi thao tác JMS trong một thread; với listener, thread điều phối gọi `stop()` và chờ callback hoàn tất. Ở cả ActiveMQ Classic và Artemis, cần kết hợp deadline, redelivery và idempotency để đối phó những lần dừng cưỡng bức ngoài kiểm soát.
