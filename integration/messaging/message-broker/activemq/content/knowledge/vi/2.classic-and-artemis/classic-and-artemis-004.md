# Kiểm tra mức hỗ trợ `JMSContext`, gửi bất đồng bộ và shared subscription theo phiên bản

> **Chương:** Classic và Artemis  
> **Phạm vi:** Apache ActiveMQ Classic, Apache ActiveMQ Artemis và ứng dụng Java dùng JMS/Jakarta Messaging.  
> **Trọng tâm:** Kiểm tra **đúng tổ hợp phiên bản client – API – broker – cấu hình** trước khi dùng `JMSContext`, `CompletionListener` hoặc shared topic subscription.

## 1. Vì sao phải kiểm tra theo phiên bản?

Giả sử hệ thống xử lý đơn hàng phát sự kiện `OrderCreated` lên topic `orders.events`:

- Dịch vụ **billing** chạy ba replica, nhưng mỗi sự kiện chỉ được **một replica billing** xử lý.
- Dịch vụ **analytics** cũng phải nhận một bản sự kiện độc lập.
- Producer muốn gửi hàng loạt mà không chặn luồng xử lý trong lúc chờ broker xác nhận.
- Nhóm phát triển muốn dùng API gọn của JMS 2.0 thay cho việc tạo `Connection`, `Session` và `MessageProducer` thủ công.

Ba nhu cầu này dẫn đến ba tính năng khác nhau:

| Nhu cầu | API liên quan | Cần kiểm chứng |
| --- | --- | --- |
| Tạo kết nối/phiên và gửi nhận gọn hơn | `ConnectionFactory.createContext(...)`, `JMSContext`, `JMSProducer`, `JMSConsumer` | Client thực sự cài đặt Simplified JMS API hay chỉ có giao diện trong thư viện API? |
| Gửi không chờ kết quả ngay tại `send` | `JMSProducer.setAsync(CompletionListener)` hoặc `MessageProducer.send(..., CompletionListener)` | Callback được triển khai đầy đủ, trả thành công/lỗi và hoạt động đúng với delivery mode đang dùng? |
| Nhiều consumer chia một subscription của topic | `createSharedConsumer`, `createSharedDurableConsumer` | Provider có hỗ trợ shared subscription tiêu chuẩn JMS 2.0 với phiên bản broker và client hiện tại? |

Sơ đồ logic:

```text
                          topic orders.events
Producer ------------------------+
                                 |
                       +---------+----------+
                       |                    |
                subscription          subscription
                billing-workers       analytics
                       |                    |
              +--------+--------+      analytics-1
              |        |        |
           billing-1 billing-2 billing-3

Trong một subscription: mỗi message -> tối đa một consumer tại mỗi lần giao.
Giữa hai subscription: mỗi subscription có bản giao riêng.
```

**Đừng suy luận từ việc broker dùng tên “ActiveMQ” rằng cả hai sản phẩm có cùng mức hỗ trợ JMS 2.0.** ActiveMQ Classic và ActiveMQ Artemis là hai broker có lộ trình triển khai khác nhau. Ngoài ra, ứng dụng có thể dùng **Classic client** để kết nối một broker khác qua OpenWire; khi đó khả năng của *client* vẫn là một yếu tố quyết định.

## 2. Nền tảng: JMS 1.1, JMS 2.0 và Jakarta Messaging 3.x

### 2.1. `JMSContext` giải quyết vấn đề gì?

Trong JMS 1.1, chương trình thường tạo `ConnectionFactory → Connection → Session → MessageProducer/MessageConsumer`, khởi động connection và đóng nhiều tài nguyên. JMS 2.0 bổ sung *Simplified API*:

```java
try (JMSContext context =
         factory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
    Queue queue = context.createQueue("orders.created");
    context.createProducer().send(queue, "order-123");

    JMSConsumer consumer = context.createConsumer(queue);
    Message message = consumer.receive(3_000);
}
```

`JMSContext` gộp vai trò của `Connection` và `Session` ở mức API, hỗ trợ `AutoCloseable` và thường tự khởi động việc giao message khi tạo consumer. `JMSProducer` là đối tượng nhẹ, không có `close()` riêng.

**Giới hạn quan trọng:** mỗi `JMSContext` vẫn gắn với khái niệm session vốn được thiết kế cho truy cập tuần tự. Không dùng cùng một context đồng thời từ nhiều worker thread; mỗi thread xử lý độc lập nên có context/session riêng hoặc dùng cơ chế container quản lý.

### 2.2. Hai namespace không thể thay tùy ý

| Tiêu chuẩn | Import trong mã nguồn | Ví dụ thư viện client |
| --- | --- | --- |
| JMS 2.0 (Java EE, `javax`) | `javax.jms.JMSContext` | Classic 5.18.x `activemq-client`; Artemis `artemis-jms-client` |
| Jakarta Messaging 3.x | `jakarta.jms.JMSContext` | Classic 6.x `activemq-client`; Artemis `artemis-jakarta-client` |
| Client Jakarta chuyển tiếp cho Classic 5.18.1+ | `jakarta.jms.*` | `activemq-client-jakarta`, chỉ dành cho kết nối broker từ xa |

Việc Maven tải được `jakarta.jms-api` chỉ chứng minh **interface có mặt trong classpath**, không chứng minh client provider hỗ trợ method cụ thể. Ngược lại, ghép client triển khai `javax.jms.ConnectionFactory` với biến kiểu `jakarta.jms.ConnectionFactory` sẽ không hoạt động dù tên các phương thức giống nhau.

### 2.3. Phân biệt gửi bất đồng bộ theo chuẩn với tùy chọn của Classic

Hai thuật ngữ thường bị nhầm:

1. **JMS 2.0 asynchronous send:** gọi `setAsync(CompletionListener)`; kết quả của lệnh gửi được thông báo qua `onCompletion(Message)` hoặc `onException(Message, Exception)`.
2. **Classic `useAsyncSend=true`:** tùy chọn vận chuyển riêng của ActiveMQ Classic, cho phép client chuyển một số lệnh gửi sang kiểu không chờ broker phản hồi đồng bộ. Nó **không đồng nghĩa** với việc triển khai API `CompletionListener` của JMS 2.0.

Ví dụ URI `tcp://localhost:61616?jms.useAsyncSend=true` là cấu hình riêng của Classic. Với persistent message ngoài transaction, chế độ đồng bộ mặc định của Classic liên quan trực tiếp đến xác nhận broker đã lưu message; thay đổi cách gửi có thể làm thay đổi bảo đảm mà ứng dụng nhìn thấy khi xảy ra lỗi. Không dùng tùy chọn này thay thế một contract callback mà ứng dụng đang phụ thuộc.

## 3. Ma trận hỗ trợ cần đọc trước khi chọn API

Bảng sau dựa trên **bảng theo dõi triển khai chính thức của ActiveMQ Classic** và **tài liệu cùng ví dụ JMS của Artemis** tại thời điểm biên soạn. “Đang triển khai” nghĩa là **không được mặc nhiên coi là hỗ trợ ổn định**; phải kiểm tra release notes và chạy probe với đúng bản đang triển khai.

| Dòng / phiên bản | Namespace/client tiêu biểu | `JMSContext` | `setAsync(CompletionListener)` | Shared topic subscription |
| --- | --- | --- | --- | --- |
| **Classic trước 5.18.0** | Chủ yếu `javax.jms`, JMS 1.1 | Không nên giả định đã triển khai đầy đủ | Không nên giả định | Không nên giả định |
| **Classic 5.18.0+ (nhánh 5.18.x)** | `activemq-client` với `javax.jms` | **Có từ 5.18.0** | Chưa được xác nhận hoàn tất trong bảng tính năng Classic | Chưa được xác nhận hoàn tất trong bảng tính năng Classic |
| **Classic 5.18.1+ với client chuyển tiếp** | `activemq-client-jakarta`, `jakarta.jms` | Có API giản lược; client **remote-only** | Cần kiểm tra như Classic tương ứng | Cần kiểm tra như Classic tương ứng |
| **Classic 6.x** | `activemq-client` dùng `jakarta.jms` | Có | Bảng chính thức ghi công việc/PR, mốc mục tiêu **6.5.0**; không coi mốc mục tiêu là mốc hoàn thành | Bảng chính thức ghi công việc/PR, mốc mục tiêu **7.0.0**; không coi mốc mục tiêu là mốc hoàn thành |
| **Artemis 2.x** | `artemis-jms-client` (`javax`) hoặc `artemis-jakarta-client` (`jakarta`), chọn đúng bản | Có | Có; có ví dụ `jms-completion-listener` | Có; có ví dụ `jms-shared-consumer` |

Các mốc Classic khác giúp nhận biết sự khác biệt giữa **từng method**:

- **5.18.0:** bảng chính thức ghi hoàn tất `JMSContext`, `JMSConsumer`, `JMSProducer` và chuyển đổi sang `JMSRuntimeException` (AMQ-8322).
- **6.4.0:** bảng chính thức mới ghi hoàn tất nhóm `JMSConsumer.receiveBody(Class<T>)` (AMQ-8464) và `JMSContext` trong pooled connection factory (AMQ-9451). Vì vậy ví dụ tương thích 5.18.x nên dùng `receive()` rồi đọc `TextMessage`, không mặc định dùng `receiveBody(...)`.
- **6.5.0 / 7.0.0:** là **target version** hiển thị cho async send callback / shared consumer, không phải bằng chứng feature đã xuất hiện trong artifact mà ứng dụng đang sử dụng. Đối chiếu cột trạng thái, release notes, issue và phép thử runtime.

Riêng namespace:

- Classic 5.18.x: `activemq-client` dùng `javax.jms`. Từ 5.18.1 có `activemq-client-jakarta` cho ứng dụng `jakarta.jms` kết nối broker từ xa; theo tài liệu Classic, không nạp nó chung JVM với client/broker `javax` cùng dòng và không dùng embedded broker/`vm://` cho biến thể chuyển tiếp.
- Classic 6.x: sử dụng `activemq-client` với `jakarta.jms`; module `activemq-client-jakarta` chuyển tiếp được loại bỏ.
- Artemis: chọn **một** trong hai client `javax`/`jakarta` phù hợp ứng dụng. Từ **Artemis 2.50.0**, Maven `groupId` chính thức đổi từ `org.apache.activemq` sang `org.apache.artemis`; các dự án dùng Artemis đời cũ cần kiểm tra `groupId` đúng theo release của mình.

**Kết luận lựa chọn:** nếu bài toán bắt buộc dùng đúng API `CompletionListener` hoặc `createSharedDurableConsumer`, Artemis là hướng có ví dụ triển khai sẵn. Nếu hệ thống đang chạy Classic, hãy xác thực đúng bản trước khi thiết kế phụ thuộc API đó; có thể cân nhắc queue hoặc Virtual Topic của Classic như phương án kiến trúc riêng.

## 4. Quy trình kiểm tra tương thích có thể lặp lại

Một kết quả “hỗ trợ” chỉ đáng tin khi trả lời được bốn câu hỏi: **API nào? client implementation nào? broker/protocol nào? đã thử hành vi nào?**

### Bước 1: Chốt phiên bản chạy thực tế

Ghi rõ:

```text
JDK:                 17
Application API:     javax.jms 2.0  HOẶC  jakarta.jms 3.x
Client artifact:     groupId:artifactId:version
Broker:              Classic/Artemis + version thực tế
Protocol/URL:        OpenWire, Artemis Core, AMQP 1.0... + URL
Môi trường:          Java SE, Spring, Jakarta EE container; XA/transaction?
Các quyền broker:    connect, create destination, consume, send
```

Có thể xem dependency đã resolve bằng Maven:

```bash
mvn dependency:tree
```

Tìm `activemq-client`, `activemq-client-jakarta`, `artemis-jms-client`, `artemis-jakarta-client` và các API jar `javax.jms`/`jakarta.jms`. Đặc biệt loại bỏ trường hợp vô tình nạp **hai implementation trái namespace** hoặc nhiều phiên bản JMS API cùng lúc.

### Bước 2: Đối chiếu tài liệu của **đúng bản** client

Đọc bảng JMS 2.0 support của Classic hoặc versioned documentation/release notes của Artemis. Với tính năng còn là issue/PR, trạng thái “target” không đủ để triển khai sản xuất.

Một broker Artemis có hỗ trợ shared subscription cũng không làm cho method chưa được triển khai trong **Classic client jar** tự nhiên hoạt động. Phải xác định chính xác implementation của `ConnectionFactory` trong JVM.

### Bước 3: Compile và chạy probe trên broker thử nghiệm

Thử lần lượt:

1. Tạo `JMSContext`, gửi và nhận một `TextMessage`.
2. Gọi `setAsync(CompletionListener)`, đợi callback, kiểm tra lỗi và xác nhận message thực sự đến queue.
3. Tạo **hai context khác nhau** dùng cùng tên shared subscription trên một topic, phát nhiều message rồi xác minh tổng số message trong nhóm chỉ nhận mỗi ID một lần.
4. Nếu cần lưu message khi consumer ngắt kết nối, kiểm tra riêng `createSharedDurableConsumer` bằng thử nghiệm “đăng ký → offline → publish → reconnect → receive”.

Không thử trực tiếp trên topic/queue nghiệp vụ: probe có thể tạo subscription, gửi dữ liệu hoặc tăng backlog. Dùng destination thử nghiệm được cấp quyền và có chính sách dọn dẹp.

### Bước 4: Phân loại lỗi cho đúng

| Hiện tượng | Diễn giải cần kiểm tra |
| --- | --- |
| `cannot find symbol: JMSContext` khi biên dịch | Thiếu/sai API jar hoặc đang dùng API JMS 1.1 |
| `ClassNotFoundException` cho `jakarta.jms.*` | Thiếu dependency Jakarta, sai packaging hoặc sai classpath |
| `NoSuchMethodError` / `AbstractMethodError` | API và provider implementation không khớp phiên bản/ABI; không coi là broker từ chối tính năng |
| `UnsupportedOperationException` khi gọi method | Provider có method trong giao diện nhưng chưa triển khai tính năng ở bản đang chạy |
| `JMSRuntimeException` / `JMSSecurityRuntimeException` | Kiểm tra nguyên nhân lồng nhau, quyền truy cập, tên destination, kết nối hoặc cấu hình trước khi kết luận “không hỗ trợ” |
| Callback báo lỗi hoặc quá thời gian chờ | Lệnh gửi thất bại/chưa hoàn tất; kiểm tra broker log, kết nối, persistence, transaction và timeout |
| Hai shared consumer đều nhận cùng một sự kiện | Có thể đã tạo **hai subscription khác tên**; cần so lại `subscriptionName`, `clientID` và selector |
| Message mất khi tất cả consumer offline | Đang dùng **non-durable** subscription; muốn giữ backlog thì dùng durable và kiểm tra cơ chế lưu trữ |

## 5. Thực hành Java: kiểm chứng `JMSContext` và gửi bất đồng bộ

Ví dụ dưới đây dùng **Artemis 2.57.0** với `jakarta.jms` và Java 17, là một tổ hợp tham khảo cụ thể. Cần broker Artemis đang chạy tại `tcp://localhost:61616` với tài khoản/quyền phù hợp. Khi dùng Classic, hãy **đổi đúng dependency, import và ConnectionFactory**, sau đó chạy lại để quan sát khác biệt tính năng.

### 5.1. Dependency Maven

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<dependencies>
    <dependency>
        <groupId>org.apache.artemis</groupId>
        <artifactId>artemis-jakarta-client</artifactId>
        <version>2.57.0</version>
    </dependency>
</dependencies>
```

Ghi nhớ khi đổi hệ:

| Tình huống | Artifact phù hợp | Import |
| --- | --- | --- |
| Artemis 2.50.0 trở lên, Jakarta | `org.apache.artemis:artemis-jakarta-client` | `jakarta.jms.*` |
| Artemis 2.50.0 trở lên, JMS 2.0 | `org.apache.artemis:artemis-jms-client` | `javax.jms.*` |
| Artemis trước 2.50.0 | `org.apache.activemq:artemis-jms-client` hoặc `artemis-jakarta-client` nếu bản đó có cung cấp | Tùy artifact |
| Classic 5.18.x tiêu chuẩn | `org.apache.activemq:activemq-client` | `javax.jms.*` |
| Classic 5.18.1+ chuyển tiếp | `org.apache.activemq:activemq-client-jakarta` | `jakarta.jms.*` |
| Classic 6.x | `org.apache.activemq:activemq-client` | `jakarta.jms.*` |

Các version thực tế phải dùng **số bản phát hành cụ thể**, phù hợp chính sách nâng cấp của dự án. Không mix hai client Artemis `javax`/`jakarta` trong cùng ví dụ.

### 5.2. Probe thứ nhất: `JMSContext` hoạt động đến đâu?

```java
import jakarta.jms.*;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class ContextProbe {
    public static void main(String[] args) throws Exception {
        String url = args.length == 0
                ? "tcp://localhost:61616"
                : args[0];
        ConnectionFactory factory = new ActiveMQConnectionFactory(url);

        try (JMSContext context =
                     factory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
            // TemporaryQueue tự được dọn khi connection đóng.
            TemporaryQueue queue = context.createTemporaryQueue();
            JMSConsumer consumer = context.createConsumer(queue);

            context.createProducer().send(queue, "probe-context");
            Message received = consumer.receive(5_000);

            if (!(received instanceof TextMessage)) {
                throw new IllegalStateException("Không nhận TextMessage");
            }

            String body = ((TextMessage) received).getText();
            if (!"probe-context".equals(body)) {
                throw new IllegalStateException("Sai payload: " + body);
            }

            System.out.println("JMSContext: PASS");
        }
    }
}
```

Điểm chủ ý: ví dụ dùng `receive()` và `TextMessage.getText()` thay cho `receiveBody(String.class)` để còn đánh giá được các bản Classic đã có `JMSContext` nhưng chưa hoàn tất mọi method của `JMSConsumer`.

Một phép thử `JMSContext` thành công **không suy ra** async send hay shared subscription cũng thành công. Phải kiểm tra độc lập.

### 5.3. Probe thứ hai: gửi bất đồng bộ với callback

```java
import jakarta.jms.*;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class AsyncSendProbe {
    public static void main(String[] args) throws Exception {
        ConnectionFactory factory =
                new ActiveMQConnectionFactory("tcp://localhost:61616");

        CountDownLatch completed = new CountDownLatch(1);
        AtomicReference<Exception> sendFailure = new AtomicReference<>();

        try (JMSContext context =
                     factory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
            TemporaryQueue queue = context.createTemporaryQueue();
            JMSConsumer consumer = context.createConsumer(queue);

            CompletionListener listener = new CompletionListener() {
                @Override
                public void onCompletion(Message message) {
                    completed.countDown();
                }

                @Override
                public void onException(Message message, Exception exception) {
                    sendFailure.set(exception);
                    completed.countDown();
                }
            };

            JMSProducer producer = context.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .setAsync(listener);

            producer.send(queue, "order-123");

            if (!completed.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Không có callback trong 10 giây");
            }
            if (sendFailure.get() != null) {
                throw new IllegalStateException(
                        "Broker/provider báo gửi lỗi", sendFailure.get());
            }

            Message received = consumer.receive(5_000);
            if (!(received instanceof TextMessage)
                    || !"order-123".equals(((TextMessage) received).getText())) {
                throw new IllegalStateException("Gửi xong nhưng chưa nhận đúng dữ liệu");
            }
            System.out.println("Async CompletionListener: PASS");
        }
    }
}
```

Nếu API chưa được cài đặt, `setAsync` hoặc `send` có thể ném `UnsupportedOperationException`. Đây là kết quả probe có ý nghĩa trên client tương ứng, **không phải lý do để tự bật `useAsyncSend=true` và tuyên bố API đã hỗ trợ**.

Cách hiểu đúng callback:

- `send(...)` trả về **chưa chắc** message đã gửi xong; chương trình cần đợi hoặc theo dõi callback.
- `onCompletion` thông báo phần gửi của provider đã hoàn tất theo contract JMS; **không xác nhận** consumer đã xử lý xong nghiệp vụ hoặc database downstream đã commit.
- `onException` là một đường báo lỗi riêng. Luồng gọi `send` cũng có thể ném ngoại lệ trước callback; production code phải xử lý cả hai.
- Không đọc/sửa cùng đối tượng `Message` sau `send` bất đồng bộ cho đến khi callback kết thúc; provider có thể vẫn đang cập nhật header/property. Không thực hiện thao tác nặng hoặc gọi đóng/commit context ngay trong callback.
- Không đóng `JMSContext` hoặc cho ứng dụng kết thúc trước khi giải quyết các lần gửi đang chờ. Với luồng quan trọng, cần timeout, giới hạn số yêu cầu đang bay, retry có kiểm soát và khóa chống gửi trùng.

**Lưu ý môi trường:** đặc tả Jakarta Messaging hạn chế lời gọi async send trong web/EJB container được Jakarta EE quản lý. Ví dụ trên dành cho Java SE; khi chạy trong application server hãy theo đúng mô hình transaction và messaging do container hỗ trợ.

## 6. Thực hành Java: kiểm tra shared topic subscription

### 6.1. Shared khác queue và subscriber bình thường ra sao?

Xét topic `orders.events`:

| Cách nhận | Hai replica billing có nhận cùng message không? | Tồn tại khi toàn bộ replica offline? |
| --- | --- | --- |
| Mỗi replica gọi `createConsumer(topic)` | **Có thể có:** mỗi replica sở hữu một subscription riêng | Không, nếu là non-durable |
| Hai replica cùng `createSharedConsumer(topic, "billing")` | **Không** trong một shared subscription ở một lượt giao; broker phân phối cho một consumer | Không; subscription biến mất khi consumer cuối đóng |
| Hai replica cùng `createSharedDurableConsumer(topic, "billing")` | **Không** trong một shared durable subscription ở một lượt giao | **Có**; subscription được giữ đến khi unsubscribe |
| Hai replica đọc chung **một JMS Queue** | Mỗi message được giao cho một consumer ở một lượt giao | Phụ thuộc độ bền queue/message/cấu hình |
| Classic Virtual Topic + hai consumer trên queue cùng group | Chia việc trong queue của group; các group có bản độc lập | Phụ thuộc queue, persistence và cấu hình riêng Classic |

“Ở một lượt giao” không có nghĩa hệ thống bảo đảm xử lý *exactly once*: nếu worker lỗi trước acknowledgment/commit, broker có thể redeliver message đó. Handler cần **idempotent** theo message/business ID.

### 6.2. Probe shared non-durable bằng hai `JMSContext`

```java
import jakarta.jms.*;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class SharedConsumerProbe {
    private static void record(Message message, Set<String> received)
            throws JMSException {
        if (message instanceof TextMessage) {
            received.add(((TextMessage) message).getText());
        }
    }

    public static void main(String[] args) throws Exception {
        ConnectionFactory factory =
                new ActiveMQConnectionFactory("tcp://localhost:61616");

        String runId = UUID.randomUUID().toString();
        String subscription = "billing_" + runId;
        int expected = 8;

        try (JMSContext worker1 = factory.createContext();
             JMSContext worker2 = factory.createContext();
             JMSContext publisher = factory.createContext()) {

            // Nên cấu hình một topic probe riêng, không trùng topic thật.
            Topic topic = publisher.createTopic("probe.shared.orders");

            JMSConsumer c1 =
                    worker1.createSharedConsumer(topic, subscription);
            JMSConsumer c2 =
                    worker2.createSharedConsumer(topic, subscription);

            JMSProducer sender = publisher.createProducer();
            for (int i = 0; i < expected; i++) {
                sender.send(topic, runId + ":" + i);
            }

            Set<String> received = new HashSet<>();
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(12);

            while (received.size() < expected
                    && System.nanoTime() < deadline) {
                Message m1 = c1.receive(250);
                Message m2 = c2.receive(250);
                if (m1 != null) record(m1, received);
                if (m2 != null) record(m2, received);
            }

            if (received.size() != expected) {
                throw new IllegalStateException(
                        "Nhóm shared nhận " + received.size()
                        + "/" + expected + " message");
            }
            System.out.println("Shared non-durable: PASS");
            // Khi cả hai consumer/context đóng, non-durable subscription mất.
        }
    }
}
```

Đây là bài test **một nhóm shared có hai consumer**, không phải bài benchmark phân phối công bằng. Không yêu cầu mỗi consumer nhận đúng 50%; số nhận tùy prefetch, tải và chính sách broker. Để phép thử khắt khe hơn, đối chiếu thêm **toàn bộ tập ID mong đợi**, kiểm tra ID trùng và xác minh subscription thứ hai nhận bản của riêng nó.

Nếu method chưa hỗ trợ trong Classic, lỗi thường xuất hiện ngay khi `createSharedConsumer`. Nếu nhận thiếu message trên Artemis, hãy xem quyền tạo/nhận topic, cấu hình routing `MULTICAST`, thời điểm tạo subscription, timeout, và redelivery trước khi kết luận sản phẩm không hỗ trợ.

### 6.3. Shared durable: giữ backlog khi không còn consumer

Một quy trình kiểm thử bền vững gồm:

1. Tạo shared durable subscription cố định: `createSharedDurableConsumer(topic, "billing_v1")`.
2. Đóng **tất cả** consumer của subscription.
3. Publish message `PERSISTENT` trong lúc không có consumer.
4. Tạo lại một hoặc nhiều consumer với **cùng tên subscription**, cùng topic và selector.
5. Xác nhận message đã gửi trong giai đoạn offline được nhận, sau đó acknowledgment/commit phù hợp.
6. Chỉ khi kết thúc thử nghiệm và không còn consumer hoạt động mới gọi `context.unsubscribe("billing_v1")`.

Ví dụ phần cốt lõi:

```java
// factory là ConnectionFactory phù hợp với client và broker.
String name = "billing_probe_v1";
String topicName = "probe.durable.orders";

// 1. Đăng ký durable rồi đóng consumer.
try (JMSContext setup = factory.createContext()) {
    Topic topic = setup.createTopic(topicName);
    setup.createSharedDurableConsumer(topic, name).close();
}

// 2. Không consumer nào online, vẫn gửi message persistent.
try (JMSContext publisher = factory.createContext()) {
    publisher.createProducer()
            .setDeliveryMode(DeliveryMode.PERSISTENT)
            .send(publisher.createTopic(topicName), "order-offline-1");
}

// 3. Hai worker cùng mở lại một subscription.
try (JMSContext workerA = factory.createContext();
     JMSContext workerB = factory.createContext()) {
    Topic topic = workerA.createTopic(topicName);
    JMSConsumer a = workerA.createSharedDurableConsumer(topic, name);
    JMSConsumer b = workerB.createSharedDurableConsumer(topic, name);

    Message m = a.receive(1_000);
    if (m == null) m = b.receive(1_000);
    if (m == null) throw new IllegalStateException("Mất backlog offline");

    a.close();
    b.close();
}

// 4. Dọn subscription demo sau khi đã đóng mọi consumer.
try (JMSContext admin = factory.createContext()) {
    admin.unsubscribe(name);
}
```

Đoạn này minh họa **vòng đời** của subscription; nên triển khai `try/finally` bảo đảm dọn dữ liệu thử nghiệm nếu một bước lỗi. Trong ứng dụng thật, **không tự động `unsubscribe` khi mỗi worker dừng**, vì thao tác này xóa chính subscription durable cùng backlog còn chờ.

Theo đặc tả JMS 2.0, shared subscription được định danh bằng **tên và `clientID` nếu có**. Với shared durable, `clientID` **không bắt buộc**, khác với unshared durable. Nếu hệ thống đã đặt `clientID` thì các kết nối vào cùng subscription phải dùng đúng định danh theo quy định của provider; không tùy tiện sinh clientID mới cho mỗi lần khởi động. Các consumer dùng chung subscription phải nhất quán về topic và message selector.

### 6.4. Đằng sau shared subscription trên Artemis

Artemis có mô hình **address + queue + routing type**:

- Topic JMS thường tương ứng address có routing `MULTICAST`; mỗi subscription được biểu diễn bằng queue gắn với address.
- Hai consumer trên **cùng subscription queue** cạnh tranh nhận message, vì vậy một bản message của subscription được giao cho một consumer.
- Hai subscription tên khác nhau có hai queue; message được multicast đến mỗi queue, phù hợp yêu cầu billing và analytics nhận độc lập.
- Độ bền của subscription quyết định queue/backlog còn tồn tại khi không có consumer.

Vì vậy khi troubleshooting cần xem **address, routing type, subscription queue, consumer count, message count và delivering count** trên Artemis Console, thay vì chỉ kiểm tra topic name.

## 7. Khi phải tiếp tục dùng ActiveMQ Classic

Classic có mô hình **Virtual Topics** để thực hiện bài toán “phát cho nhiều nhóm, chia việc trong từng nhóm” mà không phụ thuộc JMS 2.0 shared consumer:

```text
Producer -> Topic: VirtualTopic.Orders
                       |
          +------------+----------------+
          |                             |
Queue: Consumer.Billing.VirtualTopic.Orders
Queue: Consumer.Analytics.VirtualTopic.Orders
          |                             |
   +------+-------+                 analytics-1
   |              |
billing-1      billing-2
```

Trong code JMS Classic, một producer gửi vào `Topic("VirtualTopic.Orders")`; các consumer của nhóm billing cùng đọc `Queue("Consumer.Billing.VirtualTopic.Orders")`. Nhóm analytics sử dụng queue riêng. Đây là **quy ước/cơ chế ActiveMQ Classic**, không phải lời gọi `createSharedConsumer` theo JMS 2.0, nên cấu hình và chuyển broker cần được kiểm tra riêng.

Nếu chỉ cần một nhóm worker chia việc và **không** cần fan-out theo nhóm, một queue JMS thông thường có thể đơn giản hơn. Nếu cần tiêu chuẩn JMS shared durable có thể di chuyển provider, nên chọn client/broker đã thực sự hỗ trợ chuẩn và chạy compatibility test trước khi đưa vào sản xuất.

## 8. Các bẫy vận hành thường gặp

### 8.1. Nhầm “có interface” với “có hành vi”

Một thư viện API có `JMSContext.createSharedConsumer` có thể compile thành công nhưng implementation lại ném `UnsupportedOperationException`. Tiêu chí chấp nhận phải gồm **compile + tạo đối tượng + hành vi gửi/nhận + callback + lỗi mạng/đóng kết nối** ở phiên bản thật.

### 8.2. Nhầm “async gửi thành công” với “xử lý exactly once”

Callback gửi thành công chỉ mô tả trạng thái bên producer/provider. Consumer vẫn có thể xử lý thất bại và message được giao lại. Với nghiệp vụ thanh toán/đơn hàng, dùng transaction ở phạm vi phù hợp, idempotency key, retry có giới hạn và DLQ. Nếu cập nhật database rồi phát sự kiện, cân nhắc **transactional outbox** để hạn chế sai lệch giữa hai hệ.

### 8.3. Nhầm shared non-durable với shared durable

Shared non-durable xóa khi consumer cuối cùng rời subscription; lúc đó event tiếp theo có thể không được giữ lại cho nhóm. Muốn giảm nguy cơ mất event khi deploy toàn bộ replica, cần shared **durable**, persistence và chính sách hết hạn/retention phù hợp.

### 8.4. Dùng chung một `JMSContext` trên nhiều thread

`JMSContext` làm API gọn hơn, không biến JMS session thành đối tượng thread-safe. Mỗi luồng tiêu thụ nên có session/context riêng. Với nhiều shared consumer, mỗi replica hoặc worker có consumer và context của mình, cùng subscription name.

### 8.5. Quên selector và danh tính subscription

Cùng `subscriptionName` nhưng khác topic/selector có thể bị từ chối hoặc khiến subscription bị thay thế ở những điều kiện nhất định. Cần quản lý tên subscription ổn định theo **service/group + môi trường + phiên bản contract**, ví dụ `billing-prod-v1`. Nếu dùng clientID, ghi nhận vai trò của nó trong danh tính subscription và cơ chế reconnect.

### 8.6. Đo kết quả trên môi trường không tương đương

Kết quả trên Java SE khác môi trường Jakarta EE container về transaction, quản lý connection và một số API được phép gọi. Ngoài ra, quyền auto-create destination, cấu hình `MULTICAST`, prefetch/consumer window, broker failover và persistence đều ảnh hưởng kết quả. Hãy test đúng chế độ thực tế hoặc ghi rõ sự khác biệt.

## 9. Checklist chấp nhận trước khi triển khai

- [ ] Ghi phiên bản broker, client artifact, Java và namespace (`javax` hoặc `jakarta`).
- [ ] Xác nhận `ConnectionFactory` thực sự thuộc implementation định dùng; kiểm tra dependency tree không xung đột.
- [ ] Chạy probe `JMSContext` và nhận lại `TextMessage` trên broker thử nghiệm.
- [ ] Nếu dùng async, nhận được cả callback thành công và tín hiệu lỗi trong tình huống giả lập mất kết nối; có timeout và quản lý inflight.
- [ ] Nếu dùng shared, hai consumer mở cùng một subscription, message không bị nhân bản giữa chúng trong một lần giao; group khác vẫn có bản riêng.
- [ ] Nếu cần offline backlog, thử shared durable qua chu kỳ disconnect/reconnect; không `unsubscribe` trong shutdown bình thường.
- [ ] Kiểm chứng acknowledgment, rollback/redelivery, duplicate handling, DLQ, quyền access và giám sát backlog.
- [ ] Đọc release notes/issue của bản chính xác khi đổi phiên bản; không dựa duy nhất vào số major/minor.

## 10. Câu hỏi tự kiểm tra

1. Vì sao một dự án có `jakarta.jms.JMSContext` trong dependency nhưng vẫn có thể gặp `UnsupportedOperationException` khi gọi `setAsync`?
2. Classic `useAsyncSend=true` khác gì với `JMSProducer.setAsync(CompletionListener)`?
3. Khi billing có ba replica cần chia việc, còn analytics cần bản sự kiện riêng, dùng shared subscription hoặc queue như thế nào?
4. Vì sao `createSharedDurableConsumer` có thể phục hồi message đã gửi lúc không có worker, còn `createSharedConsumer` thì không?
5. Khi nâng Artemis từ nhánh cũ sang 2.50.0+, cần xem lại metadata Maven nào và vì sao?
6. Kết quả callback `onCompletion` có xác nhận database của consumer đã commit không?

**Gợi ý đáp án:** (1) API jar và provider implementation là hai lớp khác nhau; (2) một bên là tùy chọn transport riêng Classic, bên kia là callback theo chuẩn; (3) một subscription/queue chung cho billing, subscription/queue khác cho analytics; (4) do vòng đời và persistence của subscription; (5) `groupId` chuyển sang `org.apache.artemis`; (6) không.

## 11. Tài liệu đối chiếu

1. [Apache ActiveMQ Classic — Jakarta Messaging 3.1 & JMS 2.0 Support](https://activemq.apache.org/components/classic/documentation/jms2): bảng từng feature, target version và trạng thái triển khai.
2. [ActiveMQ Classic — Async Sends](https://activemq.apache.org/components/classic/documentation/async-sends): hành vi gửi đồng bộ/bất đồng bộ riêng của Classic.
3. [Apache Artemis — JMS/Jakarta Client Classpath](https://artemis.apache.org/components/artemis/documentation/latest/client-classpath): cách chọn client Maven cho hai namespace.
4. [Apache Artemis — Maven GroupId Migration](https://artemis.apache.org/artemis-tlp-groupid-migration): thay đổi từ `org.apache.activemq` sang `org.apache.artemis` ở mốc 2.50.0.
5. [Apache Artemis — Examples](https://artemis.apache.org/components/artemis/documentation/latest/examples.html): các ví dụ `jms-context`, `jms-completion-listener` và `jms-shared-consumer`.
6. [Apache Artemis — Address Model](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html): ánh xạ topic subscription sang multicast address/queue.
7. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): contract chuẩn cho async send, shared non-durable/durable subscription, vòng đời và clientID.

> **Ghi nhớ:** Tài liệu hỗ trợ theo phiên bản là điểm bắt đầu; **phép thử hành vi trên đúng client, broker và runtime** mới là căn cứ cuối cùng để bật tính năng.
