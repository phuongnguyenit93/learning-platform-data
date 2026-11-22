# QueueBrowser: xem message mà không tiêu thụ trong Spring JMS

## 1. Vấn đề và mục tiêu

Khi vận hành hệ thống sử dụng Queue, đôi khi bạn cần **xem các message đang nằm trong hàng đợi** để xác định chúng có đúng định dạng, đúng property, đúng correlation ID hoặc đúng trạng thái xử lý hay không. Nhưng nếu gọi `MessageConsumer.receive()` chỉ để “xem thử”, bạn có thể **lấy message ra khỏi queue**, kích hoạt acknowledgment/transaction, tranh message với worker thật và làm thay đổi trạng thái của hệ thống.

Jakarta Messaging (JMS) cung cấp **`jakarta.jms.QueueBrowser`** để **browse/peek các message trên Queue mà không tiêu thụ chúng**. Spring JMS bọc chức năng này bằng `JmsTemplate.browse(...)` và `browseSelected(...)`.

Sau bài học, bạn sẽ:

1. Phân biệt **browse** với **receive/consume** và hiểu tác động tới acknowledgment.
2. Tạo `QueueBrowser` bằng `Session.createBrowser` hoặc `JMSContext.createBrowser`.
3. Duyệt `java.util.Enumeration` để đọc headers, properties và body khi cần.
4. Dùng `JmsTemplate.browse`/`browseSelected` với `BrowserCallback<T>`.
5. Áp dụng JMS message selector để chỉ xem nhóm message phù hợp.
6. Hiểu vì sao **browse không phải snapshot nhất quán**, không bảo đảm số lượng/độ mới tuyệt đối, không hiển thị message trước `JMSDeliveryTime`.
7. Viết và chạy demo **Java 17+, Spring Boot 3.5.x, ActiveMQ Artemis embedded** để chứng minh browse không làm mất message.
8. Biết cách dùng browse an toàn trong production: giới hạn tài nguyên, bảo vệ dữ liệu, phân quyền và chọn metrics khi cần đo backlog.

Bài thuộc nhóm **Nhận đồng bộ**. Dù browser giúp quan sát queue, nó **không phải một consumer nhận để xử lý**, cũng không phải cơ chế để đọc lại mọi sự kiện trong Topic.

## 2. QueueBrowser là gì?

Theo Jakarta Messaging, một `QueueBrowser` cho phép ứng dụng **xem các message trong Queue mà không loại chúng ra khỏi Queue**. API chính:

~~~java
// Chữ ký rút gọn để học, không phải interface cần tự định nghĩa.
jakarta.jms.QueueBrowser browser =
        session.createBrowser(queue);
java.util.Enumeration<?> messages = browser.getEnumeration();
~~~

`QueueBrowser` là một **AutoCloseable resource**. Các method tiêu biểu:

| API | Vai trò |
| --- | --- |
| `Session.createBrowser(Queue)` | Tạo browser không selector. |
| `Session.createBrowser(Queue, String)` | Tạo browser chỉ nhìn message khớp selector. |
| `JMSContext.createBrowser(Queue)` | Tương đương ở simplified JMS API. |
| `JMSContext.createBrowser(Queue, String)` | Browser có selector với `JMSContext`. |
| `QueueBrowser.getEnumeration()` | Nhận `Enumeration` để duyệt message có thể browse. |
| `QueueBrowser.getQueue()` | Trả về queue mà browser đang gắn vào. |
| `QueueBrowser.getMessageSelector()` | Trả về biểu thức selector (hoặc null khi không có). |
| `QueueBrowser.close()` | Đóng browser, giải phóng tài nguyên tại provider. |

`getEnumeration()` không phải stream bất tận. Nó cung cấp một cách **duyệt các message phù hợp tại thời điểm/tiến trình browse**, theo semantics của provider. Khi duyệt xong, nếu muốn kiểm tra lại, hãy mở/duyệt lần khác, không giữ browser lâu như một listener.

### 2.1. So sánh browse, receive và monitor

| Thao tác | Đọc nội dung message? | Có tiêu thụ message? | Có thích hợp xử lý nghiệp vụ? |
| --- | --- | --- | --- |
| `QueueBrowser.getEnumeration()` | Có, theo quyền và message khả dụng để browse. | **Không** | Không; mục đích chính là quan sát. |
| `MessageConsumer.receive(timeout)` | Có. | **Có**, theo ack/transaction của session. | Có. |
| `JmsTemplate.receive(queue)` | Có, trả raw `jakarta.jms.Message`. | **Có** | Có, trong luồng synchronous receive. |
| `JmsTemplate.receiveAndConvert(queue)` | Có, trả body sau conversion. | **Có** | Có, khi cần dữ liệu đã chuyển đổi. |
| `@JmsListener` | Có, qua listener container. | **Có** theo thiết lập container. | Có, cho luồng xử lý bất đồng bộ. |
| Queue metrics/management API | Thường là thống kê (count, depth, age, v.v.). | Không | Dùng cho observability, không dùng để đọc từng message. |

**Browse ≠ receive không ACK**. Ngay cả khi một consumer ở `CLIENT_ACKNOWLEDGE` chưa gọi `acknowledge()`, message đã được **delivered/received** và có thể đang in-flight. Browser thì **không thực hiện thao tác nhận tiêu thụ đó**. Do vậy, không dùng `receiveNoWait()` thay cho peek để “an toàn”.

## 3. Mô hình hoạt động

Giả sử queue `orders.pending` chứa ba message:

~~~text
orders.pending:
    M1: orderId=O-101, type=Created
    M2: orderId=O-102, type=Cancelled
    M3: orderId=O-103, type=Created
~~~

Browser đi qua queue:

~~~mermaid
flowchart TD
    Q[("orders.pending: M1, M2, M3")]
    Q --> B["QueueBrowser.getEnumeration()"]
    B --> D["Ứng dụng đọc header/property/body"]
    D --> X["Không acknowledge, không xóa message"]
    Q --> C["MessageConsumer.receive()"]
    C --> A["Xử lý + ack/commit"]
    A --> R["Message được xử lý theo semantics nhận"]
~~~

Trong trường hợp **không có producer/consumer khác đồng thời thay đổi queue** và không có TTL/delay/selector cản trở, browser có thể liệt kê M1–M3. Sau browse, consumer thật **vẫn có thể nhận M1, M2 và M3**.

Tuy nhiên, đây **không phải phép chụp ảnh toàn bộ queue một cách giao dịch**. Nếu đang browse mà worker khác consume M2, hoặc có producer thêm M4, hoặc M3 hết hạn, việc M2/M3/M4 có xuất hiện trong enumeration hay không **phụ thuộc JMS provider**. Không dùng một kết quả browse làm bằng chứng tuyệt đối rằng queue có đúng N message tại một thời điểm duy nhất.

### 3.1. “Không tiêu thụ” nghĩa là gì?

- Browser không xóa/ack message chỉ vì đã đọc chúng.
- Browser không biến việc quan sát thành **business processing**.
- Nó không thay thế consumer trong transaction.
- Truy cập property/body để debug vẫn là **đọc dữ liệu** và phải chịu chính sách bảo mật.
- Đóng browser giải phóng tài nguyên của hoạt động duyệt; **không có commit/rollback message tiêu thụ nào do browser tạo ra**.

Nếu một message biến mất khỏi lần browse tiếp theo, **không** tự kết luận browser vừa xóa nó. Có thể worker khác đã consume/commit, message hết hạn, broker policy chuyển nó sang expiry queue, hoặc selector/delivery time khiến nó không còn trong tập được browse.

## 4. Classic API: Session.createBrowser

Đoạn mã sau dùng `jakarta.jms.ConnectionFactory` đã được cấu hình, tạo `QueueBrowser` rồi duyệt message.

~~~java
// Fragment: factory là jakarta.jms.ConnectionFactory kết nối broker thật.
try (jakarta.jms.Connection connection = factory.createConnection();
     jakarta.jms.Session session = connection.createSession(
             false, jakarta.jms.Session.AUTO_ACKNOWLEDGE)) {

    jakarta.jms.Queue queue = session.createQueue("orders.pending");
    connection.start();

    try (jakarta.jms.QueueBrowser browser =
                 session.createBrowser(queue)) {

        java.util.Enumeration<?> enumeration =
                browser.getEnumeration();

        while (enumeration.hasMoreElements()) {
            Object candidate = enumeration.nextElement();

            if (candidate instanceof jakarta.jms.Message message) {
                System.out.println(
                        "ID=" + message.getJMSMessageID()
                                + ", correlation="
                                + message.getJMSCorrelationID());
            }
        }
    }
}
~~~

**Giải thích từng phần:**

1. `Session.createQueue("orders.pending")` tạo **đối tượng Queue gắn tên**, không phải yêu cầu tạo queue vật lý từ quyền quản trị. Broker phải có destination hoặc chính sách provisioning hợp lệ.
2. `Session.createBrowser(queue)` tạo đối tượng browser dành cho **Queue**, không phải Topic.
3. `connection.start()` ở ví dụ giúp connection sẵn sàng cho hoạt động nhận; browser **không phải** một consumer cần `receive()`.
4. `getEnumeration()` trả cách duyệt message; `hasMoreElements()` và `nextElement()` là API của `java.util.Enumeration`, **không phải** `Iterator`.
5. Ép kiểu an toàn rồi gọi các getter JMS.
6. `try-with-resources` đóng browser, session và connection, tránh rò rỉ tài nguyên provider.

Đây là **fragment**, chưa có hàm `main` hay cấu hình `factory`. Nó có thể ném `JMSException` khi thiếu quyền, destination không hợp lệ hoặc broker gặp lỗi. Không nên lấy body của mọi message một cách mặc định: payload có thể lớn hoặc nhạy cảm.

### 4.1. Browser kèm message selector

~~~java
// Fragment: đã có jakarta.jms.Session session và Queue queue.
try (jakarta.jms.QueueBrowser browser = session.createBrowser(
        queue, "eventType = 'OrderCreated' AND schemaVersion >= 2")) {

    java.util.Enumeration<?> e = browser.getEnumeration();

    while (e.hasMoreElements()) {
        jakarta.jms.Message m =
                (jakarta.jms.Message) e.nextElement();

        System.out.println(m.getJMSMessageID());
    }
}
~~~

Chỉ những message có JMS property `eventType` và `schemaVersion` thỏa điều kiện mới được browser trả về. `schemaVersion` trong ví dụ nên được producer đặt bằng `setIntProperty(..., 2)`; nếu gửi dưới dạng `String "2"` thì phép so sánh số có thể không match.

**Selector dựa trên headers/properties**, không parse body JSON. SQL92 subset của JMS không phải SQL truy vấn tùy ý. `eventType` phân biệt chữ hoa/thường; giá trị chuỗi dùng dấu nháy đơn `'...'`.

### 4.2. Tránh can thiệp message khi đang browse

Browser có thể trả về một `Message` cho phép đọc header/body, nhưng **không nên sửa Message đó để kỳ vọng cập nhật message vật lý trong queue**. Đừng dùng:

~~~java
// PHẢN VÍ DỤ: không được xem đây là cách cập nhật message đã nằm trong queue.
m.setStringProperty("status", "fixed");
m.acknowledge(); // Browser không phải phương thức consume + ack.
~~~

Không có API JMS portable cho phép “browse rồi sửa/xóa chính message đó trong queue”. Nếu cần xử lý message lỗi, dùng consumer có transaction/acknowledgment, hoặc công cụ quản trị/broker API được cấp quyền với quy trình an toàn. Phép browse **không được biến thành read-modify-write** tùy tiện.

## 5. Simplified API: JMSContext.createBrowser

`JMSContext` (JMS 2.0+/Jakarta Messaging) cung cấp phương thức tạo QueueBrowser trực tiếp:

~~~java
// Fragment: factory là jakarta.jms.ConnectionFactory đã cấu hình.
try (jakarta.jms.JMSContext context = factory.createContext()) {
    jakarta.jms.Queue queue = context.createQueue("orders.pending");

    try (jakarta.jms.QueueBrowser browser =
                 context.createBrowser(queue)) {

        java.util.Enumeration<?> enumeration =
                browser.getEnumeration();

        while (enumeration.hasMoreElements()) {
            jakarta.jms.Message message =
                    (jakarta.jms.Message) enumeration.nextElement();
            System.out.println(message.getJMSMessageID());
        }
    }
}
~~~

Với filter:

~~~java
// Fragment trong cùng JMSContext với Queue queue.
try (jakarta.jms.QueueBrowser browser = context.createBrowser(
        queue, "eventType = 'OrderCreated'")) {
    java.util.Enumeration<?> e = browser.getEnumeration();
    while (e.hasMoreElements()) {
        jakarta.jms.Message m =
                (jakarta.jms.Message) e.nextElement();
        System.out.println(m.getJMSType());
    }
}
~~~

`JMSContext` đóng cả session/connection liên quan khi kết thúc theo quy định của API. Vẫn nên đóng `QueueBrowser` riêng khi không còn sử dụng để tài nguyên được giải phóng kịp thời.

### 5.1. Không nhầm QueueBrowser với JMSConsumer

`context.createConsumer(queue)` cho ra `JMSConsumer`, dùng `receive()`, `receiveNoWait()` hoặc `setMessageListener()`. **Đó là consumer thật**, có acknowledgment và làm thay đổi tập message còn lại.

`context.createBrowser(queue)` cho ra **QueueBrowser**, dùng `getEnumeration()` và **không tiêu thụ**. Cả hai đều có thể quan sát message, nhưng mục đích và hệ quả khác nhau.

## 6. Spring JMS: JmsTemplate.browse và BrowserCallback

Khi ứng dụng đã sử dụng Spring, thường không cần tự mở `Connection`, `Session` hay `QueueBrowser` cho tác vụ inspect ngắn. `org.springframework.jms.core.JmsTemplate` có các overload:

~~~java
// Chữ ký API tóm lược:
<T> T browse(
        String queueName,
        org.springframework.jms.core.BrowserCallback<T> action);

<T> T browseSelected(
        String queueName,
        String messageSelector,
        org.springframework.jms.core.BrowserCallback<T> action);
~~~

Các overload khác có thể nhận đối tượng `jakarta.jms.Queue` hoặc default queue. `JmsTemplate` chuẩn bị session/browser, gọi callback rồi **đóng tài nguyên ở đúng vòng đời**, và chuyển `JMSException` thích hợp thành `JmsException` không kiểm tra.

### 6.1. Hợp đồng BrowserCallback<T>

~~~java
// Chữ ký API để tham khảo, không định nghĩa interface này trong ứng dụng.
T doInJms(
        jakarta.jms.Session session,
        jakarta.jms.QueueBrowser browser)
        throws jakarta.jms.JMSException;
~~~

`BrowserCallback<T>` là functional interface. Callback nhận **hai tham số** `(session, browser)`, không nhận trực tiếp `Message`; bạn chủ động lấy `browser.getEnumeration()`.

**Quy tắc vòng đời:** duyệt và trích xuất dữ liệu **ngay trong callback**, trả về một giá trị đã độc lập với session/browser (ví dụ List ID, Map thống kê nhỏ). Đừng trả về `QueueBrowser`, `Enumeration` hay một object phụ thuộc tài nguyên đã đóng.

### 6.2. Browse ra danh sách ID

~~~java
// Fragment trong service đã có JmsTemplate jmsTemplate.
java.util.List<String> ids = jmsTemplate.browse(
        "orders.pending",
        (session, browser) -> {
            java.util.List<String> result =
                    new java.util.ArrayList<>();

            java.util.Enumeration<?> e =
                    browser.getEnumeration();

            while (e.hasMoreElements()) {
                jakarta.jms.Message m =
                        (jakarta.jms.Message) e.nextElement();
                result.add(m.getJMSMessageID());
            }
            return result;
        });

System.out.println("IDs seen: " + ids.size());
~~~

Đây là fragment trong service Spring đã có Queue. **Danh sách không nhất thiết là toàn bộ queue tại cùng một thời điểm**; nó chỉ phản ánh các message mà browser đã nhìn thấy trong lần duyệt. Cần giới hạn số phần tử và tránh log dữ liệu nhạy cảm nếu queue lớn.

### 6.3. BrowseSelected theo property

~~~java
// Fragment trong Spring bean đã có JmsTemplate jmsTemplate.
java.util.List<String> ids = jmsTemplate.browseSelected(
        "orders.pending",
        "eventType = 'OrderCreated'",
        (session, browser) -> {
            java.util.List<String> result =
                    new java.util.ArrayList<>();

            java.util.Enumeration<?> e =
                    browser.getEnumeration();

            while (e.hasMoreElements()) {
                jakarta.jms.Message m =
                        (jakarta.jms.Message) e.nextElement();
                result.add(m.getStringProperty("eventId"));
            }
            return result;
        });
~~~

`browseSelected` gắn selector vào **QueueBrowser**, không tự tiêu thụ message bị lọc hay không bị lọc. Phân biệt với `JmsTemplate.receiveSelected`: **receiveSelected vẫn là receive**, có thể lấy message và tham gia cơ chế acknowledgment/transaction.

### 6.4. Không dùng receiveAndConvert để debug mà không biết hệ quả

~~~java
// Đoạn này TIÊU THỤ, không phải "peek":
Object payload = jmsTemplate.receiveAndConvert("orders.pending");
~~~

Một số lập trình viên tưởng rằng chỉ đọc object Java là không làm gì đến Queue. Nhưng `receiveAndConvert` gọi receive rồi mới converter sang Java object; message đã được giao cho consumer. Dù application ném lỗi sau đó, trạng thái ack/rollback phụ thuộc transaction/session; **không dùng cách này chỉ để xem**.

## 7. Demo đầy đủ: Java 17 + Spring Boot + ActiveMQ Artemis

Demo sau chứng minh ba điều:

1. `JmsTemplate.browse` nhìn thấy các message đã gửi.
2. `JmsTemplate.browseSelected` chỉ liệt kê message có property phù hợp.
3. Sau **hai lần browse**, việc `JmsTemplate.receive` vẫn lấy được **toàn bộ** message ban đầu, nghĩa là browse **không tiêu thụ**.

**Điều kiện:** JDK 17+, Maven 3.6.3+, kết nối Maven Central để lấy dependency. Dùng **Spring Boot 3.5.7** với **Artemis broker embedded** để không cần khởi chạy broker ngoài. Queue demo chỉ được một `ApplicationRunner` truy cập, tránh concurrent consumer trong bài học.

Cấu trúc thư mục:

~~~text
jms-browser-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/jmsbrowser/
    │   └── JmsBrowserDemoApplication.java
    └── resources/
        └── application.properties
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>jms-browser-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>

        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-server</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Starter bổ sung Spring JMS và Artemis client, còn `artemis-jakarta-server` giúp Boot tạo broker embedded. Dependency versions được Boot parent quản lý.

### 7.2. application.properties

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=demo.browser
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=5s
spring.main.banner-mode=off
~~~

- `demo.browser` là queue demo được tạo lúc broker khởi động.
- `persistent=false` chỉ phù hợp demo; không mô phỏng phục hồi message sau broker restart.
- `receive-timeout=5s` bảo vệ lần receive khỏi chờ vô thời hạn.
- `pub-sub-domain=false` khiến tên destination mặc định được hiểu là Queue.

### 7.3. JmsBrowserDemoApplication.java

Tạo `src/main/java/com/example/jmsbrowser/JmsBrowserDemoApplication.java`:

~~~java
package com.example.jmsbrowser;

import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;
import java.util.TreeSet;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.QueueBrowser;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class JmsBrowserDemoApplication {

    private static final String QUEUE = "demo.browser";

    public static void main(String[] args) {
        SpringApplication.run(JmsBrowserDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(JmsTemplate template) {
        return args -> {
            template.convertAndSend(QUEUE, "ORDER-101", message -> {
                message.setStringProperty("eventId", "E-101");
                message.setStringProperty("eventType", "OrderCreated");
                return message;
            });
            template.convertAndSend(QUEUE, "ORDER-102", message -> {
                message.setStringProperty("eventId", "E-102");
                message.setStringProperty("eventType", "OrderCancelled");
                return message;
            });
            template.convertAndSend(QUEUE, "ORDER-103", message -> {
                message.setStringProperty("eventId", "E-103");
                message.setStringProperty("eventType", "OrderCreated");
                return message;
            });

            List<String> allIds = template.browse(
                    QUEUE, (session, browser) -> collectIds(browser));

            List<String> createdIds = template.browseSelected(
                    QUEUE,
                    "eventType = 'OrderCreated'",
                    (session, browser) -> collectIds(browser));

            List<String> receivedBodies = new ArrayList<>();
            for (int i = 0; i < 3; i++) {
                Message message = template.receive(QUEUE);

                if (!(message instanceof TextMessage text)) {
                    throw new IllegalStateException(
                            "Không nhận được TextMessage đúng thời hạn");
                }
                receivedBodies.add(text.getText());
            }

            int remaining = template.browse(
                    QUEUE, (session, browser) -> collectIds(browser).size());

            System.out.println("BROWSED_IDS="
                    + new TreeSet<>(allIds));
            System.out.println("SELECTED_IDS="
                    + new TreeSet<>(createdIds));
            System.out.println("RECEIVED_BODIES="
                    + new TreeSet<>(receivedBodies));
            System.out.println("AFTER_CONSUME_COUNT=" + remaining);
            System.out.println("BROWSE_PRESERVED_ALL="
                    + (allIds.size() == 3 && receivedBodies.size() == 3));
        };
    }

    private static List<String> collectIds(QueueBrowser browser)
            throws JMSException {

        List<String> ids = new ArrayList<>();
        Enumeration<?> enumeration = browser.getEnumeration();

        while (enumeration.hasMoreElements()) {
            Object element = enumeration.nextElement();
            if (!(element instanceof Message message)) {
                throw new IllegalStateException(
                        "Browser returned a non-JMS Message");
            }
            ids.add(message.getStringProperty("eventId"));
        }
        return ids;
    }
}
~~~

**Giải thích:**

1. `ApplicationRunner` chạy sau khi Spring Boot đã khởi tạo JMS connection factory và embedded broker.
2. Ba message `TextMessage` được gửi với `eventId` và `eventType` là JMS properties.
3. `template.browse(QUEUE,...)` gọi callback, duyệt enumeration và trả về một `List<String>` chứa ID. Danh sách độc lập với browser sau khi callback kết thúc.
4. `template.browseSelected` dùng selector để tìm hai message loại `OrderCreated`; message `OrderCancelled` không bị xóa.
5. **Sau khi browse**, `template.receive(QUEUE)` được gọi ba lần. Vì không có consumer khác, message TTL hay delay, cả ba message dự kiến vẫn có thể nhận.
6. Lần browse cuối kiểm tra queue demo sau khi cả ba message được nhận. Khi template dùng session/ack mặc định, các lần receive hoàn tất sẽ dẫn đến message được tiêu thụ theo semantics JMS.
7. In `TreeSet` để minh họa tập hợp ổn định mà **không phụ thuộc thứ tự enumeration**. Không hiểu TreeSet là thứ tự thực tế của broker.

Chạy trong thư mục `jms-browser-demo`:

~~~bash
mvn spring-boot:run
~~~

Các dòng do chương trình in, bỏ qua log Maven/Spring/Artemis:

~~~text
BROWSED_IDS=[E-101, E-102, E-103]
SELECTED_IDS=[E-101, E-103]
RECEIVED_BODIES=[ORDER-101, ORDER-102, ORDER-103]
AFTER_CONSUME_COUNT=0
BROWSE_PRESERVED_ALL=true
~~~

**Đây là output kỳ vọng** trong môi trường broker embedded mới, queue không có concurrent consumer, message không expire và cả ba send thành công. Nếu test được chạy trên broker chia sẻ và queue đã tồn tại dữ liệu, kết quả có thể khác. Bài này **không tuyên bố đã biên dịch/chạy Maven**; khi áp dụng thực tế nên chạy integration test tương tự.

### 7.4. Biến thể kiểm thử

- Comment toàn bộ bước `receive`, browse lại: dự kiến ba message vẫn còn.
- Chỉ giữ `browseSelected` với `eventType='OrderCreated'`: hai message match, message còn lại vẫn ở Queue.
- Đổi selector thành `eventType='OrderShipped'`: không match message nào; **không xóa message**.
- Cho consumer thật chạy đồng thời: số message browser nhìn thấy có thể thay đổi; đừng assert snapshot cố định.
- Đặt delivery delay trên producer rồi browse ngay: message **không được xuất hiện trước `JMSDeliveryTime`** theo chuẩn.
- Cho message TTL ngắn: message có thể hết hạn trong lúc browse; đừng lấy một enumeration làm mẫu cố định.

## 8. Quan trọng: QueueBrowser không bảo đảm snapshot

Đây là quy tắc chuẩn của Jakarta Messaging: **Enumeration không bắt buộc phải là snapshot tĩnh của Queue**. Khi bạn duyệt, message mới có thể đến, message cũ có thể hết hạn, và các consumer khác có thể nhận chúng.

Ví dụ timeline:

~~~text
12:00:00.000  Queue có M1, M2, M3.
12:00:00.010  Browser bắt đầu enumerate.
12:00:00.015  Consumer A nhận M2.
12:00:00.020  Producer B gửi M4.
12:00:00.025  M3 hết hạn TTL.
12:00:00.030  Browser kết thúc.
~~~

Tùy provider, browser có thể thấy M1/M2/M3 hoặc một tập khác, có thể thấy hoặc không thấy M4. **Không dùng kết quả này như một giao dịch đọc nhất quán**. Một QueueBrowser không cung cấp primitive “lock cả Queue” hay `SELECT ... FOR UPDATE`.

### 8.1. Hệ quả với số lượng message

Một cách đếm tưởng đúng:

~~~java
// Fragment: JmsTemplate template đã có.
int count = template.browse("orders.pending", (session, browser) -> {
    int n = 0;
    java.util.Enumeration<?> e = browser.getEnumeration();
    while (e.hasMoreElements()) {
        e.nextElement();
        n++;
    }
    return n;
});
~~~

`count` là **số message mà enumeration đã trả trong lần browse**, không nhất thiết là **queue depth chính xác tại một instant**. Với Queue lớn, việc duyệt toàn bộ chỉ để đếm còn gây tải không cần thiết.

**Đúng công cụ đúng mục đích:** để đo backlog, queue depth, messages added/acked, expiry và consumer count, ưu tiên **broker management metrics / JMX / Prometheus exporter** của nhà cung cấp. Cần mô tả semantics của chỉ số: ready vs delivering/in-flight vs scheduled vs expired có thể được broker định nghĩa khác nhau. Không đánh đồng `browseCount` với mọi metric.

### 8.2. Hệ quả với thứ tự

Javadoc nêu enumeration theo thứ tự message **would be received**, nhưng đó không phải lời hứa thứ tự tuyệt đối khi:

- Có producer/consumer đồng thời.
- Message khác `JMSPriority`, delivery time, selector, transaction, expiry.
- Broker áp dụng message grouping hoặc chính sách dispatch riêng.

Nếu cần xử lý theo thứ tự nghiệp vụ, dùng consumer, khóa nghiệp vụ/idempotency và thiết kế sequencing; **đừng lấy thứ tự browse làm quyết định xử lý transaction**.

### 8.3. Giới hạn kết quả và vòng đời

Khi Queue có hàng triệu message, `getEnumeration()` có thể tiêu hao tài nguyên broker/network/JVM. Một vòng lặp có thể bị cắt sau N phần tử:

~~~java
// Fragment trong JmsTemplate.browse callback:
java.util.List<String> ids = new java.util.ArrayList<>();
java.util.Enumeration<?> e = browser.getEnumeration();

while (e.hasMoreElements() && ids.size() < 100) {
    jakarta.jms.Message m = (jakarta.jms.Message) e.nextElement();
    ids.add(m.getJMSMessageID());
}
return ids;
~~~

**Giới hạn 100 chỉ giới hạn số phần tử ứng dụng lưu/đọc ở callback**, không phải đảm bảo broker chỉ tạo hoặc truyền đúng 100 phần tử; provider có thể prefetch/đệm trước. JMS `QueueBrowser` không định nghĩa giao thức paging/offset ổn định. Nếu cần phân trang Queue lớn, hãy tìm broker-specific management API có pagination; vẫn phải ghi nhớ dữ liệu Queue có thể thay đổi giữa các trang.

Không giữ browser mở nhiều phút để “monitor realtime”. Với dashboard, dùng metrics; với điều tra một số message, browse ngắn, đóng tài nguyên sớm.

## 9. Delivery delay và JMSDeliveryTime

Một chi tiết dễ bỏ qua: **JMS yêu cầu QueueBrowser không được trả về một message trước khi `JMSDeliveryTime` của message đó đã tới**.

Giả sử:

~~~text
10:00:00 Producer send M1, delivery delay 5 phút
JMSDeliveryTime của M1 ≈ 10:05:00

10:02:00 Browser duyệt Queue
          -> không được trả M1 trước 10:05

10:05:00+ Browser mới có thể nhìn M1,
           nếu M1 chưa bị consume, expire hoặc xử lý khác.
~~~

Điều này quan trọng nếu broker hỗ trợ **scheduled/delayed delivery**. Queue metrics của broker có thể báo còn một scheduled message, nhưng QueueBrowser không thấy nó trước khi đủ điều kiện. **Không kết luận message bị mất** chỉ vì browse không trả về một message còn nằm trong thời gian delay.

Phân biệt:

- `JMSDeliveryTime`: **sớm nhất được phép giao**.
- `JMSExpiration`: **mốc hết hạn** theo TTL (0 nghĩa không hết hạn theo TTL JMS).
- `JMSTimestamp`: thời điểm provider ghi nhận khi send (có thể 0 nếu tắt timestamp).
- `receivedAt` do ứng dụng đo: thời điểm consumer thực sự nhận.

QueueBrowser không cam kết “chụp” cả những scheduled message mà broker chưa được phép giao. Nếu cần điều tra scheduled messages ở mức broker, dùng **management API riêng**, không ép JMS `QueueBrowser` làm việc ngoài đặc tả.

## 10. Browsing với selector: cơ chế và giới hạn

`Session.createBrowser(queue, selector)` và `JmsTemplate.browseSelected` đều dùng **JMS message selector**.

Một số trường hợp:

| Selector | Ý nghĩa |
| --- | --- |
| `eventType = 'OrderCreated'` | Chọn message có `eventType` là String đúng giá trị. |
| `schemaVersion >= 2` | Chọn message có property numeric phù hợp. |
| `JMSCorrelationID = 'corr-123'` | Chọn message cùng correlation ID. |
| `eventType = 'OrderCreated' AND schemaVersion >= 2` | Hai điều kiện đồng thời. |
| `JMSPriority >= 7` | Chọn theo header JMS priority, nếu provider/selector áp dụng giá trị đó. |
| `tenantId IS NOT NULL` | Chọn message có giá trị property không null theo rules của selector. |

Trong JMS, selector diễn giải kiểu dữ liệu và biểu thức logic gần SQL-92 subset. Không hỗ trợ việc đọc tùy ý sâu vào JSON body; nếu phải lọc `orderId` trong JSON, hãy cân nhắc bổ sung property đã được validate ở producer, dùng công cụ broker/search chuyên biệt, hoặc đọc dữ liệu qua consumer khi thực sự cần xử lý.

**Không nên dùng selector để thay authorization.** Một tài khoản đã được phép browse queue có thể truy cập những message mà browser/broker cho phép, trong khi selector là lựa chọn logic của client. Bảo vệ dữ liệu multi-tenant cần ACL, queue segmentation và kiểm soát danh tính độc lập.

### 10.1. Nếu selector không match

Browser có thể trả enumeration trống dù queue còn nhiều message:

~~~text
Queue: eventType = "OrderCancelled" cho mọi message
Selector: eventType = 'OrderCreated'
Kết quả browse: 0
Queue vẫn chứa message; không bị xóa.
~~~

Nếu thuộc tính vắng mặt, biểu thức thường không đánh giá thành true. Đừng mặc định NULL/unknown sẽ tương đương String rỗng. Kiểm tra producer dùng đúng setter property và type: `setIntProperty` thay vì `setStringProperty` cho version số.

## 11. QueueBrowser không dành cho Topic

Jakarta Messaging định nghĩa `QueueBrowser` để browse **Queue**. Không có API JMS chuẩn tương đương để browse trực tiếp “toàn bộ Topic” như một Queue.

| Đích | Hành vi |
| --- | --- |
| **Queue** | Browser xem message phù hợp còn khả dụng mà **không consume**. |
| **Topic** | Subscriber có subscription; message publish thường được phân phối theo từng subscription. |
| **Durable Topic subscription** | Broker có thể lưu message cho subscription khi consumer offline, nhưng JMS **không định nghĩa API chuẩn browse Topic**. |
| **Broker-specific queue dùng để lưu subscription** | Nhà cung cấp có thể cho inspect bằng management API/queue bên dưới, nhưng không portable. |

Nếu cần kiểm tra một durable subscription, hãy dùng công cụ/management API của broker được hỗ trợ và cân nhắc permissions; đừng giả định `Session.createBrowser((Queue) topic)` là hợp lệ.

Với ActiveMQ Artemis, Topic thường được hiện thực bằng multicast address và subscription queues. Đây là mô hình broker-specific; nó không biến `QueueBrowser` thành Topic browser của chuẩn JMS.

## 12. Transaction, acknowledgment và redelivery

Để không nhầm browse với các chế độ nhận:

### 12.1. AUTO_ACKNOWLEDGE

Consumer dùng `AUTO_ACKNOWLEDGE` có thể làm message được acknowledge tự động sau receive hoặc khi listener hoàn tất theo quy tắc JMS. `QueueBrowser` chỉ quan sát, **không tạo bước ACK của consumer**.

### 12.2. CLIENT_ACKNOWLEDGE

Consumer sử dụng `CLIENT_ACKNOWLEDGE` nhận message rồi có thể gọi `message.acknowledge()`. Đây vẫn là **receive** và message có thể đang unacknowledged/in-flight. Browser không phải “CLIENT_ACKNOWLEDGE không gọi ACK”; nó là **API khác**.

### 12.3. Transacted session

Với session transacted, consumer nhận message rồi `commit()`/ `rollback()`; rollback thường khiến message có thể giao lại. Browser **không cần commit để message đã browse được coi là xử lý**. Cũng không dùng `session.rollback()` như một cách “undo browse”.

Một transaction producer **chưa commit** thì message chưa được công bố bình thường cho các consumer/browsers khác. Sau commit, message mới có cơ hội xuất hiện nếu đủ điều kiện delivery time và các chính sách khác. Không dựa vào browser để quan sát trạng thái transaction chưa commit.

### 12.4. Browser có làm tăng delivery count không?

`JMSXDeliveryCount` và `JMSRedelivered` dùng trong ngữ cảnh **giao message cho consumer**. Browsing **không tương đương delivery cho consumer thực thi business**, do đó không dùng nó để kích hoạt retry hay định nghĩa một attempt đã xử lý. Giá trị provider công bố trên một message **được browser nhìn thấy** có thể phụ thuộc trạng thái của message/broker; đừng lấy một phép browse làm bằng chứng về lần nhận/ack.

Nếu muốn kiểm tra retry thực tế, xem event logs, consumer transaction và broker redelivery/DLQ metrics. Đừng sửa `JMSRedelivered` hay `JMSXDeliveryCount` trên message được browse.

## 13. Quyền browse là một quyền truy cập dữ liệu

QueueBrowser là công cụ **đọc dữ liệu**; vì thế quyền browse cần được kiểm soát. Trên **Apache ActiveMQ Artemis**, ACL có các quyền **`send`**, **`consume`**, **`browse`** và các quyền quản trị riêng.

| Quyền Artemis | Vai trò | Có nghĩa được browse không? |
| --- | --- | --- |
| `send` | Producer gửi message vào address. | Không tự suy ra. |
| `consume` | Worker nhận message từ Queue. | Không tự suy ra. |
| `browse` | Cho phép xem các message trong Queue tương ứng. | Có, theo ACL/cấu hình. |
| `manage`, `view`, `edit` | Các thao tác quản trị/management API. | Phân quyền khác, không đánh đồng với JMS QueueBrowser. |
| `create*`/`delete*` | Provision và xóa Queue/Address. | Không đồng nghĩa browse. |

Ví dụ **fragment** trong `broker.xml` của Artemis, phải tích hợp vào cấu hình broker hiện có:

~~~xml
<security-settings>
    <security-setting match="orders.#">
        <permission type="send" roles="order-producers"/>
        <permission type="consume" roles="order-workers"/>
        <permission type="browse" roles="order-auditors"/>
    </security-setting>
</security-settings>
~~~

Điểm cần hiểu:

- Đây không phải file `broker.xml` đầy đủ; user/role mapping phải được cấu hình bên security manager.
- Một security-setting cụ thể hơn có thể **ghi đè** quyền từ rule rộng trong Artemis; phải xem **effective rule**.
- Một số hoạt động tạo destination/temporary queue còn cần các quyền `create*` riêng.
- Không cấp `consume` chỉ để cho đội vận hành xem message; cấp `browse` trong phạm vi phù hợp.
- Không cấp `browse` toàn bộ `#` cho nhiều người; Queue có thể chứa payload khách hàng, đơn hàng, token nội bộ.

**Cẩn trọng với production:** người có quyền browse vẫn có thể xem dữ liệu của message. Nếu Queue chứa thông tin nhạy cảm, cân nhắc metadata-only logging, redaction, giới hạn quyền và audit truy cập. Dữ liệu bí mật không nên được log nguyên payload chỉ vì mục đích debug.

## 14. Trường hợp nên và không nên sử dụng QueueBrowser

### 14.1. Khi nên dùng

- Chẩn đoán một Queue đang chứa loại sự kiện nào hoặc có schemaVersion nào.
- Kiểm tra nhanh một số `JMSMessageID`, `JMSCorrelationID`, `eventId`, `eventType` hoặc property do producer đã đặt.
- Xem một message **không tiêu thụ** trước khi quyết định dùng công cụ vận hành hợp lệ.
- Kiểm thử việc message còn trong Queue sau browse.
- Lấy một mẫu nhỏ message khớp selector để điều tra migration/format.

### 14.2. Khi không nên dùng

- **Xử lý message nghiệp vụ**: cần consumer và ack/transaction.
- **Đếm backlog chính xác/tin cậy** trên Queue lớn: dùng broker metrics.
- **Theo dõi liên tục realtime** bằng polling nhanh: dùng monitoring metrics; browser không phải streaming subscription.
- **Phân trang hàng triệu message** với offset cố định: JMS không có paging cursor bất biến chung.
- **Xem Topic toàn cục**: API JMS QueueBrowser không hỗ trợ.
- **Sửa/xóa/republish message** đang trong Queue: không có API browser portable cho thao tác đó.
- **Đọc message delayed trước delivery time**: bị chuẩn JMS cấm.
- **Quản trị Queue trong môi trường đa tenant không có phân quyền**: browse có thể lộ dữ liệu.

### 14.3. So sánh với Artemis Console

Artemis Console có màn hình xem danh sách Queue, browse message và có thể phân trang qua API quản trị. Đây là một **giao diện broker-specific**, không phải `QueueBrowser` tiêu chuẩn mà Java code luôn có thể dựa vào. Một số màn hình còn cho phép **delete/move/copy/resend** khi tài khoản có quyền; chúng **không còn là thao tác “browse chỉ đọc”**.

Nếu cần công cụ vận hành, phân quyền console cho người dùng riêng; không cho ứng dụng producer/worker dùng tài khoản quản trị chỉ để gọi `JmsTemplate.browse`.

## 15. Performance, memory và lưu ý triển khai

### 15.1. Bounded browse

Luôn cân nhắc giới hạn:

- Số message tối đa xem mỗi lần, ví dụ 20–100 ID.
- Kích thước body tối đa được log; ưu tiên metadata.
- Thời gian cho phép thao tác browse tồn tại; dùng timeout/request deadline ở tầng quản lý phù hợp.
- Tần suất thực hiện. Một tác vụ browse tự động mỗi 100 ms trên Queue lớn có thể gây overhead.
- Quyền truy cập và audit; log mỗi lần người dùng xem message nhạy cảm nếu chính sách yêu cầu.

Chỉ đọc 100 phần tử từ Enumeration **không bảo đảm provider chỉ prefetch 100 phần tử**. Nếu cần hard page size, tìm chức năng management/paging của chính broker.

### 15.2. Không giữ JMS Message sau khi đóng browser để xử lý muộn

Mặc dù phần lớn getter của Message có thể dùng sau khi nhận, thực tế có provider dùng các lazy body stream/resource phụ thuộc phiên. Đối với ứng dụng browse, nên **trích xuất các field nhỏ vào DTO/snapshot riêng ngay trong callback**. Không trả về `Enumeration` hoặc `QueueBrowser` từ callback.

Ví dụ DTO quan sát:

~~~java
// Java 17 record khai báo trong ứng dụng phù hợp:
public record MessageInfo(
        String jmsId,
        String eventType,
        String correlationId) {}
~~~

Trong browser callback, có thể lấy:

~~~java
// Fragment: jakarta.jms.Message m từ Enumeration.
MessageInfo info = new MessageInfo(
        m.getJMSMessageID(),
        m.getStringProperty("eventType"),
        m.getJMSCorrelationID());
~~~

Không bắt buộc load toàn bộ `BytesMessage` dung lượng lớn để trả về màn hình. Nếu cần hiển thị body phải sanitize và giới hạn kích thước, tránh vô tình đưa payload vào log.

### 15.3. Không khóa Queue hoặc tranh nhận để tạo “snapshot”

Không có phương pháp JMS portable “khóa hàng đợi trong lúc browse”. Tạm dừng worker, bật broker pause hoặc dùng management freeze có thể ảnh hưởng luồng sản xuất; chỉ thực hiện sau khi đánh giá rủi ro và theo quy trình vận hành.

Với chẩn đoán nhẹ, kết quả approximate thường đủ. Với audit pháp lý cần bản ghi bất biến, hãy thiết kế **outbox, audit log, event store hoặc CDC** từ đầu. QueueBrowser không phải kho lưu lịch sử.

## 16. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Browser trả 0 nhưng Queue metrics báo nhiều | Message delayed chưa tới `JMSDeliveryTime`, selector không match, in-flight, expiry hoặc broker semantics. | Kiểm tra delivery time, selector, ready/scheduled/dispatching metrics. |
| Browser nhìn thấy message nhưng worker không nhận | Worker chưa start, thiếu `consume`, selector khác, broker routing/transaction. | Consumer count, application log, queue configuration. |
| Browse đếm 12 nhưng metrics báo 10 | Queue biến động trong lúc enumerate; provider buffering. | Dùng metrics cho backlog, không dùng browse làm count tuyệt đối. |
| `JMSException` hoặc Spring `JmsException` khi browse | Không có quyền `browse`, sai Queue, kết nối lỗi, provider nội bộ. | Xem cause chain và broker security logs. |
| Browse có message nhưng receive ra message khác | Có concurrent consumer/producer, priority/selector. | Kiểm tra concurrent flow, không giả định snapshot/thứ tự tuyệt đối. |
| Browser đã đóng, vẫn dùng Enumeration và bị lỗi | Tài nguyên bị giải phóng. | Duyệt hết bên trong callback/try block. |
| Body không thể đọc bằng `TextMessage.getText()` | Message thực là `BytesMessage`/`MapMessage`/... | Kiểm tra `instanceof` hoặc converter phù hợp. |
| Dùng `receiveNoWait()` để peek làm message biến mất | Đó là nhận tiêu thụ, không phải browse. | Dùng `QueueBrowser` hoặc `JmsTemplate.browse`. |
| Không browse được Topic | API chuẩn chỉ có QueueBrowser cho Queue. | Dùng provider-specific management/subscription diagnostics. |
| App vượt memory khi browse Queue lớn | Duyệt/load body quá nhiều, provider prefetch. | Giới hạn, lấy metadata, monitoring/paging broker. |
| Người dùng read-only truy cập bị từ chối | Role có `send`/`consume` nhưng thiếu `browse`. | Cấp quyền browse thích hợp, tránh nâng thành admin. |

**Thứ tự debug khuyến nghị:**

1. Xác nhận Queue thực sự tồn tại và đúng tên/routing.
2. Kiểm tra principal của JMS `ConnectionFactory` và quyền `browse`.
3. Thử không selector trên Queue test; sau đó kiểm tra type/name của từng property.
4. Kiểm tra TTL, `JMSDeliveryTime`, transaction và consumer đang chạy.
5. So sánh metrics broker với kết quả browser, nhớ hai nguồn có semantics khác.
6. Đảm bảo browser đã đóng, không có vòng lặp vô hạn hoặc body logging không giới hạn.
7. Kiểm thử lại trong broker riêng với queue cô lập để loại bỏ cạnh tranh đồng thời.

## 17. Kiểm thử cho tính “không tiêu thụ”

### 17.1. Unit test của BrowserCallback

Với mock `QueueBrowser` và `Enumeration<Message>`, có thể xác minh:

- Callback gọi `getEnumeration()` và thu thập ID/property đúng.
- Không tạo `MessageConsumer` hoặc gọi `acknowledge()`.
- Trả lại `List` đã chứa String/DTO, không trả `QueueBrowser`.
- Tôn trọng giới hạn phần tử khi được cấu hình.
- Xử lý `JMSException`/message type lạ theo chính sách.

Mock chỉ xác minh callback, **không chứng minh broker không consume**, nên cần integration test.

### 17.2. Integration test với broker thật

Trên queue riêng không có consumer khác:

1. Gửi M1/M2/M3 với `eventId` khác nhau và `JMSDeliveryTime` đã tới.
2. Browse không selector, lấy tập ID A.
3. Browse lần nữa, lấy tập ID B; với queue không đổi, dự kiến A = B.
4. BrowseSelected chỉ message phù hợp, không ảnh hưởng tập A/B.
5. Gọi consumer receive ba lần và xác minh nhận được cả M1/M2/M3.
6. Browse sau khi các receive đã ack/commit, kết quả trống.
7. Kiểm tra các trường hợp đặc biệt: selector không match, TTL, delay và concurrent consumer **riêng**, không trộn vào assertion của demo ổn định.

Đây là kiểm chứng **hành vi không tiêu thụ** chứ không dùng một câu “browse trả N” rồi suy ra queue không đổi mà chưa thử consumer sau đó.

### 17.3. Các test âm tính đáng có

- Browse với account không có quyền `browse`: phải bị từ chối theo policy.
- Receive với account chỉ có `browse`: không được phép `consume`.
- Queue sai tên: báo lỗi hoặc không nhìn thấy message theo broker policy; không tự bật auto-create trong production.
- Browse message chưa tới delivery time: không được trả message đó.
- Browser kết thúc trong lúc queue thay đổi: test chấp nhận outcome phụ thuộc provider, không assert snapshot cứng.
- Thử `browseSelected` với tên property sai/khác type: không match như kỳ vọng, message không mất.

## 18. Câu hỏi ôn tập

1. **QueueBrowser có consume message không?** Không; nó duyệt message trên Queue mà không loại chúng ra khỏi Queue.
2. **API để duyệt là gì?** `QueueBrowser.getEnumeration()`, trả `java.util.Enumeration`.
3. **Tại sao không dùng `receiveNoWait()` để peek?** Vì đó là receive tiêu thụ, có thể ảnh hưởng ack/transaction.
4. **`JmsTemplate.browse` callback nhận tham số gì?** `Session` và `QueueBrowser` qua `BrowserCallback<T>`.
5. **`browseSelected` khác `receiveSelected` thế nào?** Browse chỉ xem; receive lấy message để xử lý.
6. **QueueBrowser có bảo đảm snapshot tĩnh không?** Không. Message có thể đến, expire hoặc bị consumer khác nhận trong lúc duyệt.
7. **Có thấy message có `JMSDeliveryTime` trong tương lai không?** Không được trả trước delivery time.
8. **Có browser chuẩn cho Topic không?** Không; JMS QueueBrowser chỉ dành cho Queue.
9. **Dùng QueueBrowser để đếm queue depth production có chính xác tuyệt đối không?** Không; dùng broker metrics.
10. **Quyền `browse` có khác `consume` trong Artemis không?** Có; là hai quyền riêng.
11. **Browser đọc body có an toàn dữ liệu tuyệt đối không?** Không; payload có thể nhạy cảm, cần ACL và giới hạn log.
12. **Đóng browser có làm mất message không?** Không; đóng giải phóng tài nguyên, không tiêu thụ message.
13. **Selector lọc trên body JSON được không?** Không, JMS selector làm việc với headers/properties.
14. **Nếu có consumer khác nhận message giữa hai lần browse, kết quả có thể khác không?** Có, tùy broker và hoạt động đồng thời.
15. **Muốn sửa/xóa message bằng QueueBrowser được không?** Không có API portable cho thao tác đó; cần consumer hoặc management API được kiểm soát.
16. **Vì sao không trả `Enumeration` ra khỏi `JmsTemplate.browse` callback?** Browser/session có thể đã được đóng, nên phải trích xuất dữ liệu cần dùng ngay trong callback.

## 19. Tài liệu chính thức

- [Jakarta Messaging 3.1 Specification — QueueBrowser](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html), mục **4.1.6 QueueBrowser**: browse không consume, enumeration không bắt buộc snapshot, không trả message trước delivery time.
- [Jakarta Messaging 3.1 — QueueBrowser API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/queuebrowser): `getEnumeration`, `getQueue`, `getMessageSelector`, `close`.
- [Jakarta Messaging — Session API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/session): `createBrowser(Queue)` và overload selector.
- [Jakarta Messaging — JMSContext API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmscontext): simplified API `createBrowser`.
- [Spring Framework 6.2 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `browse` và `browseSelected`.
- [Spring Framework 6.2 — BrowserCallback API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/BrowserCallback.html): `doInJms(Session, QueueBrowser)`.
- [Spring Boot 3.5 — JMS with Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): cấu hình broker embedded và `JmsTemplate`.
- [Apache ActiveMQ Artemis — Authentication & Authorization](https://artemis.apache.org/components/artemis/documentation/latest/security.html): phân quyền `browse`, `consume`, `send`.
- [Apache ActiveMQ Artemis Console](https://artemis.apache.org/components/artemis-console/documentation/latest/): công cụ quản trị queue, browse và phân trang theo provider.

**Ghi nhớ:** `QueueBrowser` là công cụ **quan sát message trên Queue mà không tiêu thụ**, thông qua `Enumeration`; trong Spring JMS dùng `JmsTemplate.browse/browseSelected`. Nó **không bảo đảm snapshot**, không thay consumer/ACK/transaction, không browse Topic theo chuẩn và **không được trả delayed message trước `JMSDeliveryTime`**. Khi production cần số liệu backlog, sử dụng metrics; khi cần xem nội dung, bảo vệ quyền `browse`, giới hạn phạm vi và đóng tài nguyên.
