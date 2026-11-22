# Kết hợp selector với receive hoặc @JmsListener

**Chủ đề:** Spring Framework - jms → Lọc thông điệp

## 1. Mục tiêu: chỉ nhận message phù hợp, thay vì nhận rồi bỏ

Trong hệ thống JMS (Java Message Service, hiện thuộc Jakarta Messaging), một queue có thể chứa nhiều loại thông điệp: đơn hàng ưu tiên cao, đơn thường, sự kiện thanh toán, thông báo từ nhiều tenant. Consumer không phải lúc nào cũng muốn xử lý tất cả.

Ví dụ một queue `orders.events` chứa:

| Message body | Property `eventType` | Property `priorityLevel` | Consumer mong nhận |
| --- | --- | --- | --- |
| `order-101` | `ORDER_CREATED` | 2 (int) | Luồng thường |
| `order-102` | `ORDER_CREATED` | 8 (int) | Luồng ưu tiên |
| `refund-1` | `REFUND_REQUESTED` | 9 (int) | Luồng hoàn tiền |
| `order-103` | `ORDER_CREATED` | 6 (int) | Luồng ưu tiên |

Một consumer chỉ lấy các đơn hàng được đánh dấu ưu tiên cao có thể sử dụng:

~~~sql
eventType = 'ORDER_CREATED' AND priorityLevel >= 5
~~~

Đây là **JMS message selector**, một biểu thức điều kiện do consumer truyền cho JMS provider. Provider chỉ cung cấp những message có headers/properties khớp selector cho consumer tương ứng. Với queue, message không khớp vẫn có thể nằm trong queue hoặc được consumer khác đủ điều kiện nhận; chúng **không** bị consumer vừa gọi tự lấy ra rồi bỏ.

Trong Spring JMS có hai cách thường dùng:

- **Nhận đồng bộ:** `JmsTemplate.receiveSelected(...)` hoặc `receiveSelectedAndConvert(...)`.
- **Nhận bất đồng bộ:** `@JmsListener(destination = "...", selector = "...")`.

Hai cách dùng **cùng ngôn ngữ selector JMS**, nhưng khác vòng đời, tài nguyên, cách xử lý kết quả và concurrency. Bài hướng dẫn cách kết hợp đúng trong ứng dụng Spring Framework 6.x / Spring Boot 3.x, Java 17+, dùng `jakarta.jms.*`.

## 2. Selector hoạt động ở đâu trong luồng gửi–nhận?

~~~text
                 Producer (Spring JmsTemplate)
                         |
          convertAndSend("orders.events", body,
              message -> {
                setStringProperty("eventType", ...);
                setIntProperty("priorityLevel", ...);
              })
                         |
                         v
                  JMS provider/broker
                         |
                  queue: orders.events
                         |
            +------------+------------+
            |                         |
   Consumer A                    Consumer B
   selector:                     selector:
   eventType='ORDER_CREATED'     eventType='REFUND_REQUESTED'
   AND priorityLevel >= 5
            |                         |
     chỉ nhận các message khớp điều kiện mỗi consumer
~~~

**Selector do consumer chỉ định, không phải lời gọi để sửa message.** Producer phải gắn các message properties hoặc standard headers mà selector có thể truy cập; consumer khai báo biểu thức khi tạo consumer/endpoint. Một selector **không** tự bổ sung property thiếu lên message.

Trong Jakarta Messaging, selector là một `String` với cú pháp dựa trên **một tập con của SQL-92**, nhưng không phải câu SQL chạy trong database. Nó được JMS provider đánh giá trên **JMS message properties và một số standard headers**. Nó **không đọc nội dung body**.

Nếu producer chỉ gửi JSON trong `TextMessage`:

~~~json
{"eventType":"ORDER_CREATED","priorityLevel":8,"orderId":"order-102"}
~~~

thì selector `priorityLevel >= 5` **không thể đọc field JSON** bên trong body. Producer phải đặt một property cùng tên/ý nghĩa nếu muốn lọc ở cấp JMS:

~~~java
// Trong callback MessagePostProcessor, message là jakarta.jms.Message.
message.setStringProperty("eventType", "ORDER_CREATED");
message.setIntProperty("priorityLevel", 8);
~~~

Body và property là hai vùng khác nhau, dù có thể chứa giá trị trùng nhau. Chỉ đưa metadata thật sự cần lọc lên properties, tránh nhân đôi mọi field của payload.

## 3. Nền tảng cú pháp selector cần nắm

### 3.1. Các toán tử phổ biến

| Biểu thức | Ý nghĩa |
| --- | --- |
| `eventType = 'ORDER_CREATED'` | Property String bằng một giá trị |
| `priorityLevel >= 5` | So sánh property số |
| `express = TRUE` | So sánh property boolean |
| `priorityLevel BETWEEN 5 AND 9` | Giá trị trong một khoảng, gồm hai đầu |
| `eventType IN ('ORDER_CREATED', 'ORDER_UPDATED')` | Thuộc danh sách literal String |
| `source LIKE 'mobile%'` | Chuỗi có tiền tố `mobile` |
| `tenantId IS NOT NULL` | Property tồn tại với giá trị khác NULL |
| `tenantId IS NULL` | Không có property hoặc giá trị mang nghĩa NULL |
| `NOT (status = 'CANCELLED')` | Phủ định theo logic ba giá trị |
| `(a = 1 OR b = 2) AND active = TRUE` | Nhóm ưu tiên bằng ngoặc |
| `JMSPriority >= 7` | Kiểm tra một standard header được phép |
| `JMSCorrelationID = 'corr-123'` | Match standard correlation header |

Tên property **phân biệt chữ hoa–thường**: `priorityLevel` khác `PriorityLevel`. Tên toán tử và literal `TRUE`/`FALSE` của selector không phân biệt chữ hoa–thường theo chuẩn, nhưng nên viết thống nhất để dễ đọc. Literal String dùng **nháy đơn**; Java String chứa selector thường dùng nháy kép bao ngoài.

Ví dụ kết hợp nhiều điều kiện:

~~~sql
eventType IN ('ORDER_CREATED', 'ORDER_UPDATED')
AND priorityLevel BETWEEN 5 AND 9
AND tenantId IS NOT NULL
AND (express = TRUE OR source LIKE 'mobile%')
~~~

Đây là **biểu thức selector độc lập**, không phải script SQL database. Trong Java, viết thành một `String` hoặc nhiều literal nối với dấu `+`.

### 3.2. Bắt buộc chú ý kiểu property

Các so sánh JMS không tự đổi chuỗi số thành số. Hai lệnh sau tạo property **khác kiểu**:

~~~java
message.setStringProperty("priorityLevel", "8"); // String
message.setIntProperty("priorityLevel", 8);      // int
~~~

Với selector:

~~~sql
priorityLevel >= 5
~~~

chỉ **property có kiểu numeric phù hợp** mới match theo ý nghĩa mong đợi. Giá trị `"8"` là String và không được selector tự parse sang int như cách một số getter JMS có thể hỗ trợ. Tương tự:

~~~java
message.setBooleanProperty("express", true);     // boolean đúng
message.setStringProperty("express", "true");     // String, không phải boolean
~~~

Selector `express = TRUE` được thiết kế để nhận trường hợp đầu. Hãy thống nhất một **message contract** về tên, kiểu và ý nghĩa property giữa producer với consumer.

### 3.3. NULL và logic ba giá trị

JMS selector đánh giá theo ba trạng thái: **TRUE**, **FALSE**, **UNKNOWN**. Chỉ kết quả **TRUE** được xem là match.

| Property `tenantId` | Selector | Kết quả |
| --- | --- | --- |
| Chưa đặt | `tenantId = 'blue'` | UNKNOWN → không match |
| Chưa đặt | `tenantId IS NULL` | TRUE |
| `"blue"` | `tenantId = 'blue'` | TRUE |
| `"red"` | `tenantId = 'blue'` | FALSE |
| Chưa đặt | `NOT (tenantId = 'blue')` | UNKNOWN → không match |

Vì vậy một selector như `NOT (tenantId = 'blue')` **không** có nghĩa là nhận mọi message thiếu `tenantId`. Nếu nghiệp vụ muốn bao gồm message thiếu property, phải nói rõ:

~~~sql
tenantId IS NULL OR tenantId <> 'blue'
~~~

Không suy luận rằng NULL là một String đặc biệt hoặc rằng NULL = NULL trả TRUE. Dùng `IS NULL`/`IS NOT NULL` khi cần kiểm tra sự tồn tại.

### 3.4. Header chuẩn nào có thể dùng?

JMS chuẩn cho phép tham chiếu **sáu standard headers** trong selector:

- `JMSDeliveryMode`
- `JMSPriority`
- `JMSMessageID`
- `JMSTimestamp`
- `JMSCorrelationID`
- `JMSType`

**Không** dùng `JMSDestination` hay `JMSReplyTo` làm header selector chuẩn, dù cả hai có getter trên `Message`. Cũng không dùng `JMSExpiration` như một selector header chuẩn.

Với `JMSDeliveryMode`, trong selector giá trị tương ứng là literal **`'PERSISTENT'`** hoặc **`'NON_PERSISTENT'`**, không phải giá trị số nguyên Java của hằng `DeliveryMode.PERSISTENT`.

Các property như `JMSXGroupID` có ngữ nghĩa JMS riêng; không tự tạo tên nghiệp vụ bằng tiền tố `JMSX` hoặc `JMS_`, vì chúng thuộc không gian tên chuẩn/provider.

## 4. Kết hợp selector với receive đồng bộ của JmsTemplate

### 4.1. Tại sao không gọi receive(selector) trực tiếp?

Trong Spring JMS, các overload cơ bản:

~~~java
jakarta.jms.Message receive();
jakarta.jms.Message receive(String destinationName);
jakarta.jms.Message receive(jakarta.jms.Destination destination);
~~~

**Không** nhận selector dưới dạng tham số thứ hai. Muốn lọc message đồng bộ, dùng các overload **`receiveSelected`**:

~~~java
// Destination mặc định của JmsTemplate:
jakarta.jms.Message receiveSelected(String messageSelector);

// Destination chỉ định bằng tên:
jakarta.jms.Message receiveSelected(
        String destinationName, String messageSelector);

// Destination object đã có:
jakarta.jms.Message receiveSelected(
        jakarta.jms.Destination destination, String messageSelector);
~~~

Đây là **chữ ký diễn giải để học**, không phải file Java độc lập. Giá trị thực tế trả về có thể là `null` khi timeout. Khi code đang nhận raw JMS message, bạn có thể lấy body, properties, header và JMS message type.

Ví dụ trích đoạn trong một service có `JmsTemplate jmsTemplate`:

~~~java
String selector =
        "eventType = 'ORDER_CREATED' AND priorityLevel >= 5";

jakarta.jms.Message message =
        jmsTemplate.receiveSelected("orders.events", selector);

if (message == null) {
    System.out.println("NO_MATCH_IN_TIMEOUT");
} else {
    System.out.println("EVENT_TYPE="
            + message.getStringProperty("eventType"));
    System.out.println("PRIORITY="
            + message.getIntProperty("priorityLevel"));
}
~~~

**Điều kiện chạy:** template có `ConnectionFactory` hợp lệ, queue tồn tại và có quyền consume. Lệnh `getStringProperty`/`getIntProperty` ném `JMSException` nên method bao ngoài phải khai báo hoặc bắt ngoại lệ. Trên đường nhận được message phù hợp, code in type và priority thực tế; với queue rỗng/không có message match trước timeout, chỉ in `NO_MATCH_IN_TIMEOUT`.

### 4.2. receiveSelectedAndConvert: lọc trước, convert sau

Nếu chỉ cần payload Java, dùng:

~~~java
Object receiveSelectedAndConvert(String messageSelector);
Object receiveSelectedAndConvert(
        String destinationName, String messageSelector);
Object receiveSelectedAndConvert(
        jakarta.jms.Destination destination, String messageSelector);
~~~

Quy trình: JMS provider chọn message phù hợp selector → `JmsTemplate` nhận message → `MessageConverter.fromMessage` chuyển body sang Java value. Ví dụ:

~~~java
Object payload = jmsTemplate.receiveSelectedAndConvert(
        "orders.events",
        "eventType = 'ORDER_CREATED' AND priorityLevel >= 5");

if (payload instanceof String text) {
    System.out.println("MATCHED_BODY=" + text);
} else if (payload == null) {
    System.out.println("NO_MATCH_IN_TIMEOUT");
}
~~~

Với converter mặc định, `TextMessage` → `String`; `BytesMessage` → `byte[]`; `MapMessage` → `Map`; `ObjectMessage` → một Java object đã deserialize được. **Selector không quyết định kiểu Java sau convert.** Nó chỉ chọn message, còn converter quyết định Java payload.

Muốn đọc `JMSCorrelationID` hay properties của **chính message nhận được**, `receiveSelected` trả raw `jakarta.jms.Message` thích hợp hơn; `receiveSelectedAndConvert` thường chỉ trả payload, không còn wrapper mang toàn bộ metadata.

### 4.3. Default destination và overload một tham số

~~~java
jmsTemplate.setDefaultDestinationName("orders.events");
jmsTemplate.setReceiveTimeout(2_000L);

Object matched = jmsTemplate.receiveSelectedAndConvert(
        "eventType = 'ORDER_CREATED'");
~~~

Dòng `receiveSelectedAndConvert(String)` **một tham số** coi đối số là **selector**, rồi lấy destination mặc định từ template. Đừng nhầm nó với `receiveAndConvert("orders.events")`, nơi đối số lại là **destination name**. Nếu chưa cấu hình default, overload một tham số không có đích nhận hợp lệ và phát sinh lỗi cấu hình.

Tương tự, `receiveSelected("eventType = 'ORDER_CREATED'")` sử dụng default destination. Nếu cần chọn queue đích trong mỗi lời gọi, dùng overload hai tham số `receiveSelected("orders.events", selector)`.

### 4.4. receiveTimeout: không match không đồng nghĩa không có message

JMS receive đồng bộ có thể **block**. `JmsTemplate` cho phép:

~~~java
jmsTemplate.setReceiveTimeout(2_000L); // tối đa khoảng 2 giây
~~~

Quy tắc:

| Giá trị timeout | Hành vi |
| --- | --- |
| `0` (mặc định) | Chờ vô hạn |
| Số dương | Chờ tối đa số milliseconds đã đặt |
| Số âm | Thử nhận ngay, không chờ |

Ví dụ queue chứa message không phù hợp selector:

~~~text
Queue orders.events:
  m1 eventType=ORDER_CREATED priorityLevel=2
  m2 eventType=REFUND_REQUESTED priorityLevel=9

Consumer selector:
  eventType = 'ORDER_CREATED' AND priorityLevel >= 5
~~~

Lời gọi `receiveSelected("orders.events", selector)` với timeout hữu hạn có thể trả `null`, **dù queue không hề rỗng**. Hai message không match vẫn có thể chờ consumer khác hoặc nằm trong queue theo chính sách provider, retention và expiry.

Không có lý do gì để tự dequeue message rồi discard nếu mục đích chỉ là filter: đó là việc selector được thiết kế để thực hiện. Tuy nhiên nếu có nhiều consumer không selector, chúng **có thể lấy** các message mà consumer có selector không muốn xử lý.

### 4.5. Dùng MessageConsumer trực tiếp trong JMS classic API

Spring `receiveSelected` sử dụng khả năng consumer-side selection của JMS. Ở API gốc, cú pháp tương ứng:

~~~java
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;
import jakarta.jms.Session;

// session thuộc một connection hợp lệ.
// connection.start() phải được gọi để cho phép delivery.
Queue queue = session.createQueue("orders.events");

try (MessageConsumer consumer = session.createConsumer(
        queue,
        "eventType = 'ORDER_CREATED' AND priorityLevel >= 5")) {

    Message message = consumer.receive(2_000L);
    if (message != null) {
        System.out.println(message.getJMSMessageID());
    }
}
~~~

Đây là **đoạn trích**; code còn cần `Session`, `Connection`, broker và exception handling. `try (MessageConsumer...)` sử dụng JMS 2.0+/Jakarta Messaging API với `AutoCloseable` resource contract. Ý chính: selector được gắn vào **consumer khi tạo**, không phải đặt lên message, và consumer chỉ nhận những message đáp ứng biểu thức.

Không tạo hàng nghìn consumer mới cho từng HTTP request nếu throughput lớn. Khi cần polling thường xuyên, cân nhắc listener lâu dài, batching, transaction, backpressure hoặc service chuyên nhận message.

## 5. Kết hợp selector với @JmsListener

Với consumer hoạt động liên tục, Spring Framework cung cấp annotation:

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class HighPriorityOrderListener {

    @JmsListener(
            destination = "orders.events",
            selector = "eventType = 'ORDER_CREATED' "
                    + "AND priorityLevel >= 5")
    public void onOrder(Message message) throws JMSException {
        System.out.println("BODY_TYPE="
                + message.getClass().getSimpleName());
        System.out.println("PRIORITY="
                + message.getIntProperty("priorityLevel"));
    }
}
~~~

Đây là **Spring component minh họa**: để hoạt động phải có JMS provider, `ConnectionFactory`, listener infrastructure và queue phù hợp. `@JmsListener.selector` là **JMS selector**, được cấu hình cho endpoint/consumer của listener container. Chỉ những message match mới được chuyển vào method.

Spring có thể chuyển đổi payload cho tham số `String` hoặc DTO theo converter được cấu hình. Nhận `jakarta.jms.Message` như trên thuận tiện nếu cần kiểm tra chính property/header dùng để lọc.

### 5.1. Spring setup và lifecycle

Một listener có hai phần:

1. **Đăng ký endpoint:** Spring tìm `@JmsListener` trong bean đã được quản lý.
2. **Tạo listener container/consumer:** container sử dụng `ConnectionFactory` và cấu hình `destination`, `selector`, concurrency, transaction và acknowledgment.

Trong Spring Framework thuần, bật `@EnableJms` và cấu hình `JmsListenerContainerFactory` phù hợp. Với Spring Boot, JMS starter và auto-configuration thường cung cấp các bean cần thiết; vẫn có thể khai báo `@EnableJms` rõ ràng trong ví dụ.

Nếu không có broker hoặc bean factory đúng, chỉ đặt `@JmsListener` trên một class Java không đủ tạo listener hoạt động. Những class không phải Spring-managed bean cũng không tự được scan.

### 5.2. Selector được gắn ở consumer, không phải câu if trong method

So sánh:

~~~java
// Phương án KHÔNG filter ở broker:
@JmsListener(destination = "orders.events")
public void receiveAll(Message msg) throws JMSException {
    if (msg.getIntProperty("priorityLevel") >= 5) {
        handle(msg);
    }
}
~~~

với:

~~~java
// Phương án filter trước khi giao message cho method:
@JmsListener(
    destination = "orders.events",
    selector = "priorityLevel >= 5")
public void receiveHigh(Message msg) throws JMSException {
    handle(msg);
}
~~~

Hai đoạn **mã minh họa** giả định có method `handle(Message)` và imports phù hợp, không phải toàn bộ class chạy độc lập.

Ở phương án đầu, consumer **đã lấy** message khỏi queue; với acknowledgment thành công, message không phù hợp có thể bị coi là tiêu thụ dù code bỏ qua. Ở phương án thứ hai, selector ngăn việc giao message không match cho consumer ấy; message còn có cơ hội được consumer khác nhận hoặc lưu lại trong queue.

Đây là sự khác biệt về **semantics**, không chỉ là tối ưu CPU.

### 5.3. Nhiều listener trên cùng queue

Giả sử cùng queue có:

~~~java
@JmsListener(
    destination = "orders.events",
    selector = "eventType = 'ORDER_CREATED'")
public void orders(Message m) { /* ... */ }

@JmsListener(
    destination = "orders.events",
    selector = "eventType = 'REFUND_REQUESTED'")
public void refunds(Message m) { /* ... */ }
~~~

Nếu selectors **không giao nhau**, mỗi consumer chỉ đủ điều kiện nhận nhóm message tương ứng (với queue permissions/provider hoạt động bình thường). Nhưng đây **không phải broadcast**. Nếu hai selectors **cùng match một message**, JMS queue vẫn giao message đó cho **một consumer đủ điều kiện**, chứ không phát hai bản sao cho cả hai listener.

Nếu có thêm một consumer **không selector**, consumer đó cũng có thể lấy message của cả hai nhóm. Nếu muốn fan-out tới nhiều dịch vụ độc lập, cần cân nhắc Topic/subscriptions hoặc cơ chế nhân bản/route ở broker.

### 5.4. Selector annotation thường là cấu hình endpoint tĩnh

Không nên hiểu `@JmsListener(selector="...")` là một expression được tự động thay đổi theo từng message. Consumer selector được gắn khi endpoint/consumer được thiết lập; muốn thay đổi điều kiện thường cần điều chỉnh configuration và khởi tạo lại endpoint/container theo cơ chế Spring.

Nếu ứng dụng cần lọc theo tenant động từng request, không thể đơn giản đổi biến Java trong method rồi mong consumer selector thay đổi lập tức. Cân nhắc partition queue, logical subscriptions, selector cấu hình theo instance hoặc routing riêng.

## 6. Lựa chọn receiveSelected hay @JmsListener

| Tiêu chí | `receiveSelected(...)` | `@JmsListener(selector = ...)` |
| --- | --- | --- |
| Mô hình | Đồng bộ, caller chủ động gọi | Bất đồng bộ, container gọi method |
| Khi nào bắt đầu nhận? | Khi chạy lời gọi | Khi listener container đang hoạt động |
| Số message mỗi lần | Tối đa một message/lời gọi | Mỗi lần invoke xử lý một message |
| Thread | Thread caller bị block cho đến match/timeout/lỗi | Thread của listener container |
| Timeout | `JmsTemplate.receiveTimeout` | Container quản lý vòng lặp receive/lifecycle riêng |
| Kiểm soát startup/shutdown | Do caller quyết định | Do listener container/registry |
| Property/filter | Truyền selector String mỗi lời gọi | Selector khai báo tại endpoint |
| Payload | Có thể lấy raw Message hoặc convert | Parameter raw Message hoặc payload được converter xử lý |
| Resource | Có thể tạo/đóng JMS consumer theo từng lời gọi | Consumer lâu dài, được container quản lý |
| Use case | Worker polling ngắn, nhận reply hoặc job theo điều kiện | Service tiêu thụ liên tục, worker nền |
| Rủi ro | Block thread, tạo nhiều consumers, timeout | Concurrency, transaction/redelivery, nhầm selector tĩnh |

**Không có một cách luôn tốt hơn.** Dùng `receiveSelected` khi workflow cần gọi nhận **có chủ đích** tại một thời điểm; dùng listener khi ứng dụng cần tiêu thụ liên tục và container quản lý vòng đời.

Cả hai đều dùng chung ngôn ngữ JMS selector. Khi thiết kế hệ thống, đừng đặt consumer polling không selector cạnh listener có selector trên cùng queue mà vẫn kỳ vọng listener luôn nhận được nhóm ưu tiên; consumer không selector có thể giành trước message.

## 7. Ví dụ chạy được: Spring Boot 3.x + Artemis, so sánh cả hai cách

Ví dụ sử dụng hai queue riêng để **không tranh nhau message**:

- `demo.selector.poll`: minh họa `JmsTemplate.receiveSelectedAndConvert`.
- `demo.selector.listen`: minh họa `@JmsListener(selector = ...)`.

Mỗi queue nhận một message `priorityLevel=2` và một message `priorityLevel=8`, cùng một loại sự kiện tương ứng. Consumer có selector chỉ nhận message ưu tiên cao. Message ưu tiên thấp **không được consumer có selector lấy đi**; nếu không có consumer khác và message chưa hết hạn, chúng có thể còn trên broker.

### 7.1. Chuẩn bị môi trường

Tạo dự án Maven từ [Spring Initializr](https://start.spring.io/) với:

- Java **17+**, Spring Boot **3.x**, Group `com.example`, Artifact `jms-selectors-demo`.
- Dependency **Spring for Apache ActiveMQ Artemis** (`org.springframework.boot:spring-boot-starter-artemis`).
- Broker Artemis chạy **ngoài ứng dụng** ở `tcp://localhost:61616`.
- Hai queue `demo.selector.poll` và `demo.selector.listen` tồn tại hoặc broker có chính sách auto-create phù hợp, tài khoản có quyền send/consume.
- Không có message cũ trong hai queue, và không có consumer khác của hai queue khi chạy demo.

Đặt biến môi trường `ARTEMIS_USER` và `ARTEMIS_PASSWORD` ứng với broker. Tệp `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}

spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=3s
~~~

`spring.artemis.mode=native` **không khởi chạy broker nhúng**. `receive-timeout=3s` giới hạn thời gian chờ của `JmsTemplate`, không quy định TTL hay timeout của listener.

### 7.2. Mã Java đầy đủ

Tạo file `src/main/java/com/example/JmsSelectorsDemoApplication.java`:

~~~java
package com.example;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class JmsSelectorsDemoApplication {

    private static final String POLL_QUEUE = "demo.selector.poll";
    private static final String LISTEN_QUEUE = "demo.selector.listen";

    public static void main(String[] args) {
        SpringApplication.run(JmsSelectorsDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(JmsTemplate template) {
        return args -> {
            // Nhóm 1: polling queue có một low và một high.
            sendEvent(template, POLL_QUEUE,
                    "POLL_LOW", "ORDER_CREATED", 2);
            sendEvent(template, POLL_QUEUE,
                    "POLL_HIGH", "ORDER_CREATED", 8);

            Object chosen = template.receiveSelectedAndConvert(
                    POLL_QUEUE,
                    "eventType = 'ORDER_CREATED' "
                            + "AND priorityLevel >= 5");

            System.out.println("POLL_MATCH=" + chosen);

            // Nhóm 2: listener queue, consumer @JmsListener có selector.
            sendEvent(template, LISTEN_QUEUE,
                    "LISTENER_LOW", "INVOICE_READY", 2);
            sendEvent(template, LISTEN_QUEUE,
                    "LISTENER_HIGH", "INVOICE_READY", 8);

            System.out.println("PUBLISHED=4");
        };
    }

    private static void sendEvent(
            JmsTemplate template,
            String destination,
            String body,
            String eventType,
            int priority) {

        template.convertAndSend(destination, body, message -> {
            message.setStringProperty("eventType", eventType);
            message.setIntProperty("priorityLevel", priority);
            return message;
        });
    }
}

@Component
class HighPriorityInvoiceListener {

    @JmsListener(
            destination = "demo.selector.listen",
            selector = "eventType = 'INVOICE_READY' "
                    + "AND priorityLevel >= 5")
    public void receive(Message message) throws JMSException {
        if (!(message instanceof TextMessage textMessage)) {
            throw new IllegalArgumentException(
                    "Expected TextMessage");
        }

        System.out.println("LISTENER_MATCH="
                + textMessage.getText());
        System.out.println("LISTENER_PRIORITY="
                + message.getIntProperty("priorityLevel"));
    }
}
~~~

Tại sao code có thể biên dịch:

1. Một `public class JmsSelectorsDemoApplication` nằm trong file cùng tên; `HighPriorityInvoiceListener` là package-private `@Component` trong cùng package, Spring vẫn có thể scan.
2. `@EnableJms` bật hạ tầng listener annotation (Spring Boot có hỗ trợ auto-configured listener factory khi dependency/ConnectionFactory hợp lệ).
3. `MessagePostProcessor` đặt properties native JMS trước khi gửi.
4. `receiveSelectedAndConvert` trả Java `Object` (trong case TextMessage mặc định là String), và timeout trả `null` nếu không có message phù hợp.
5. `@JmsListener` nhận raw `jakarta.jms.Message`, đọc `TextMessage` và property kiểu int.
6. Hai consumer dùng **hai queue độc lập**, tránh nguy cơ polling và listener cùng queue tranh một message khi minh họa.

### 7.3. Chạy và quan sát

Ở thư mục dự án Maven:

~~~bash
mvn spring-boot:run
~~~

Trên Windows, nếu project có Maven Wrapper:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Với broker, quyền truy cập, queue và consumer configuration hợp lệ, khi không có message cũ/consumer khác, các dòng nghiệp vụ kỳ vọng gồm:

~~~text
POLL_MATCH=POLL_HIGH
LISTENER_MATCH=LISTENER_HIGH
LISTENER_PRIORITY=8
PUBLISHED=4
~~~

**Thứ tự các dòng không phải luôn đúng như khối trên.** `POLL_MATCH=POLL_HIGH` xảy ra trong ApplicationRunner trước phần gửi nhóm listener; hai dòng từ listener có thể xuất hiện trước hoặc sau `PUBLISHED=4` do xử lý bất đồng bộ. Spring còn in startup logs. Mẫu output là **kỳ vọng**, không phải kết quả đã chạy Maven/broker trong môi trường soạn bài.

Nếu queue không sẵn sàng hoặc quyền sai, send/receive có thể ném exception. Nếu receive hết 3 giây mà không có message match, code in `POLL_MATCH=null`. Vì có message high vừa được gửi, trường hợp timeout trong môi trường chuẩn là dấu hiệu cần kiểm tra broker, selector hoặc resource. Khi có message tồn đọng, thứ tự/giá trị có thể khác.

### 7.4. Kiểm tra hai message không match

Trong môi trường thử nghiệm **không có consumer khác** và chưa hết hạn, broker có thể vẫn giữ:

~~~text
demo.selector.poll    -> POLL_LOW      priorityLevel=2
demo.selector.listen  -> LISTENER_LOW  priorityLevel=2
~~~

Có thể dùng broker management UI/JMX/CLI để kiểm tra queue depth và properties. Không cần sửa code để dequeue chúng trong bài thử selector chính.

**Quan trọng:** một message không match selector không có nghĩa provider phải lưu vĩnh viễn. TTL, expiration, broker policy và consumer khác vẫn có thể làm message biến mất hoặc được phân phối. Với queue, chỉ kết luận consumer hiện tại **không được giao message đó**.

### 7.5. Đổi property để thử tính mạnh về kiểu

Thử thay dòng:

~~~java
message.setIntProperty("priorityLevel", priority);
~~~

bằng:

~~~java
message.setStringProperty(
        "priorityLevel", Integer.toString(priority));
~~~

trong một **bản chạy test riêng**, vẫn giữ `priorityLevel >= 5` trong selector. Giá trị String `"8"` không tự trở thành numeric, nên message `POLL_HIGH`/`LISTENER_HIGH` không match theo ý muốn. Cần phục hồi typed setter `setIntProperty`.

Không đổi cả code và broker queues đang có backlog mà không làm sạch test data, vì mixed messages từ lần chạy trước có thể gây sai nhận định.

## 8. Queue so với Topic khi dùng selector

Selector áp dụng được với cả `Queue` và `Topic`, nhưng **semantics của message không match khác nhau**.

| Trường hợp | Queue | Topic |
| --- | --- | --- |
| Consumer không match selector | Message có thể tiếp tục nằm trong queue hoặc được consumer phù hợp khác nhận | Message không được thêm vào subscription ấy khi không match |
| Có nhiều consumer | Một message được giao cho một consumer của queue trong mỗi lần delivery | Mỗi subscription có thể nhận bản riêng theo pub/sub |
| Có hai selector cùng match | Không có broadcast: một message queue chỉ được giao một consumer | Hai subscription độc lập có thể đều nhận bản riêng |
| Chưa có consumer | Queue có thể lưu backlog theo chính sách | Non-durable subscription không tồn tại khi không có consumer; durable có quy tắc riêng |
| Cần nhận cùng một event ở nhiều service | Thường cần nhiều queue/broker routing | Topic + subscriptions là mô hình phù hợp hơn |

Ví dụ một Topic `orders.events` có hai subscriptions:

~~~text
Topic orders.events
    |
    +--> Subscription A:
    |      selector = "eventType = 'ORDER_CREATED'"
    |
    +--> Subscription B:
           selector = "priorityLevel >= 5"
~~~

Message có `eventType=ORDER_CREATED` và `priorityLevel=8` có thể được **cả hai subscriptions** nhận theo cơ chế topic, không giống hai `@JmsListener` competing trên cùng queue.

Trong Spring, cấu hình topic cần `pubSubDomain=true`/listener container factory đúng, và có thể cần subscription name/client ID cho durable subscription. **Không** chỉ đổi tên queue thành `"topic.orders"` rồi giả định JMS tự biến nó thành topic; domain và provider destination phải đồng bộ.

## 9. Selector theo JMSCorrelationID trong request/reply

Một use case quan trọng của `receiveSelected` là nhận phản hồi theo correlation ID trên một **reply queue chung**. Ví dụ requester đã biết correlation:

~~~java
import java.util.UUID;
import jakarta.jms.Message;

String correlation = "corr-" + UUID.randomUUID();
String selector =
        "JMSCorrelationID = '" + correlation + "'";

Message reply = jmsTemplate.receiveSelected(
        "replies.shared", selector);

if (reply == null) {
    System.out.println("REPLY_TIMEOUT");
} else if (!correlation.equals(reply.getJMSCorrelationID())) {
    throw new IllegalStateException("Correlation mismatch");
}
~~~

Đây là **trích đoạn** cần `jmsTemplate`, broker và một responder thực sự gửi reply tới `replies.shared` **với JMSCorrelationID được đặt đúng giá trị**. Nó không tự gửi request hay tạo reply. `UUID` sinh correlation không có nháy đơn nên ví dụ tránh phải escape selector literal; nếu correlation đến từ input tự do, phải escape nháy đơn theo JMS selector syntax hoặc dùng ID do ứng dụng tạo có bộ ký tự an toàn.

**Phân biệt ba điều:**

- Destination quyết định reply được gửi đến queue nào.
- Selector quyết định consumer nhận message nào trên queue đó.
- JMSCorrelationID giúp requester xác định reply thuộc request nào; không tự bảo đảm response đến đúng nơi, không phải credential xác thực.

Với lượng request cao, **mỗi request tạo riêng một MessageConsumer có selector** có thể tốn tài nguyên broker/connection. Cân nhắc temporary reply queue hoặc một dispatcher nhận reply chung rồi phân phối theo correlation bằng map pending requests.

Không dùng selector một mình làm hệ thống RPC hoàn chỉnh: cần timeout, xử lý reply muộn, correlation uniqueness, bảo mật, idempotency và lifecycle phù hợp.

## 10. Nhiều selector và overlapping conditions

Nếu cùng queue có hai listener:

~~~text
A: priorityLevel >= 5
B: eventType = 'ORDER_CREATED'
~~~

Một message `priorityLevel=8` và `eventType=ORDER_CREATED` match **cả A và B**. Queue **không** gửi hai bản sao cho hai listener, và JMS không bảo đảm message sẽ vào đúng listener mà nghiệp vụ kỳ vọng nếu cả hai đủ điều kiện.

Khi muốn phân tuyến theo kiểu sự kiện, nên thiết kế selectors **loại trừ nhau**:

~~~sql
eventType = 'ORDER_CREATED' AND priorityLevel >= 5
~~~

và:

~~~sql
eventType = 'ORDER_CREATED' AND priorityLevel < 5
~~~

Khi đó mỗi message `ORDER_CREATED` có property priority numeric hợp lệ chỉ match một nhánh. Nhưng các message **thiếu priorityLevel** hoặc có kiểu sai có thể **không match cả hai** vì logic NULL/UNKNOWN/so sánh sai kiểu; phải quyết định rule cho dữ liệu lỗi/thừa kế schema.

Có thể thêm consumer riêng xử lý metadata thiếu, ví dụ `eventType = 'ORDER_CREATED' AND priorityLevel IS NULL`, với điều kiện broker/provider xử lý đúng cú pháp và thống nhất contract. Tránh triển khai selector chồng chéo rồi kỳ vọng message được phân phối deterministic đến một handler cố định.

## 11. Selector và bảo mật, hiệu năng, vận hành

### 11.1. Selector không phải cơ chế phân quyền

Một selector như `tenantId = 'tenantA'` chỉ là **điều kiện lọc message**. Nó không xác minh người gửi có quyền ghi `tenantId`, cũng không ngăn một consumer khác có quyền queue đọc message của tenantA qua selector khác.

Để tách tenant có yêu cầu bảo mật, dùng ACL ở broker, phân tách destination/identity, mã hóa và xác thực nguồn dữ liệu phù hợp. Không dựa vào một property String để thực hiện isolation bắt buộc.

### 11.2. Selector phức tạp có chi phí

Broker/provider cần đánh giá biểu thức trên metadata. Selector quá dài, nhiều OR/LIKE hoặc số lượng lớn consumers mỗi consumer một selector có thể tăng chi phí CPU/memory và làm phân phối khó dự đoán về throughput. Tối ưu phụ thuộc provider, không có chuẩn JMS bảo đảm index hoặc hiệu năng cụ thể.

Cân nhắc:

- Phân chia destination rõ ràng nếu các luồng message hoàn toàn khác nhau.
- Dùng ít property ổn định và typed đúng để selector đơn giản.
- Có metric về queue depth, age of oldest message, expired/dead-letter và số consumer.
- Đặt receive timeout hữu hạn cho synchronous polling.
- Dùng container lâu dài với concurrency phù hợp cho workload liên tục.
- Không sinh selector mới từ input người dùng trực tiếp; có validation và escaping.
- Phân biệt backlog **không match** với backlog do consumer chậm hoặc broker lỗi.

### 11.3. Nháy đơn và selector injection

Nếu cần tạo selector từ String có dấu nháy đơn, JMS syntax escape literal bằng **hai nháy đơn**. Ví dụ tên chứa `O'Neil` cần biểu diễn literal `'O''Neil'`:

~~~java
String tenant = "O'Neil";
String escaped = tenant.replace("'", "''");
String selector = "tenantName = '" + escaped + "'";
~~~

Nếu quyền lọc liên quan đến dữ liệu nhạy cảm, đừng chỉ dựa vào escaping: xác thực/ủy quyền tenant, giới hạn độ dài/ký tự và bảo vệ tài nguyên broker. Selector là một expression có ý nghĩa, không phải chuỗi tìm kiếm vô hại.

### 11.4. Đừng tưởng mọi SQL-92 đều dùng được

JMS selector chỉ hỗ trợ **subset** SQL-92. Không viết:

~~~sql
SELECT * FROM orders WHERE status = 'READY'
~~~

hoặc dùng SQL comments `-- comment`, JOIN, subquery, hàm database tùy ý; chúng **không phải** message selector hợp lệ. Selector chỉ là biểu thức điều kiện, chẳng hạn:

~~~sql
status = 'READY' AND priorityLevel >= 5
~~~

Tên property cần tuân thủ identifier rules; không dùng tên chứa khoảng trắng/dấu gạch ngang rồi mong parser tự chấp nhận. Nếu cần biểu diễn metadata tên phức tạp, chuẩn hóa tên hợp lệ khi producer đặt property.

## 12. Transaction, acknowledgment và redelivery

Selector quyết định **message nào được cung cấp** cho consumer, nhưng không thay thế cơ chế ack/transaction.

- Với `receiveSelected`, khi nhận được message, cách acknowledge/commit phụ thuộc session/transaction của template. Không giả định ném exception **sau** khi method trả về sẽ khiến broker redeliver.
- Với `@JmsListener`, listener container quản lý session/concurrency/ack/transaction; khi method thất bại, việc rollback/redelivery phụ thuộc cấu hình tương ứng.
- Nếu message được redeliver, nó có thể lại match cùng selector vì các properties không đổi; nghiệp vụ nên idempotent.
- Message không match thường không được consumer có selector lấy/ack. Tuy nhiên expiry, broker policy và consumer khác vẫn có thể thay đổi queue.
- Không có JMS selector nào đảm bảo xử lý exactly-once với database; nếu cần atomicity/correctness phải thiết kế transaction, idempotency, retry và DLQ phù hợp.

Trong một queue có nhóm message không match mọi selector hiện tại, chúng có thể tích tụ lâu dài. Thiết kế tuyến xử lý metadata lạ/sai schema, expiry hoặc DLQ có quan sát được; đừng bật consumer không selector chỉ để “dọn sạch” rồi âm thầm bỏ toàn bộ message.

### 12.1. Poison messages và nhận diện message sai schema

Giả sử producer đổi `priorityLevel` từ int thành String mà không nâng cấp consumer. Hai listener có selectors `priorityLevel >= 5` và `priorityLevel < 5` đều không nhận bản String phù hợp theo giả định numeric. Kết quả có thể là backlog tăng dần mà code listener không hề ném exception.

Cần monitor queue depth và message age, kiểm tra properties thực, làm integration test giữa producer và selectors trước khi triển khai thay đổi kiểu. Không tự kết luận mọi message tồn đọng đều là message “hỏng”; đôi khi nó vẫn hợp lệ nhưng không có consumer đăng ký đúng điều kiện.

## 13. Checklist kiểm thử selector

1. **Tên và kiểu:** producer có dùng đúng `setStringProperty`, `setIntProperty`, `setBooleanProperty` tương ứng selector không?
2. **Destination:** hai phía cùng Queue/Topic thật sự và cùng tên/namespace/provider chưa?
3. **Cú pháp:** selector là biểu thức điều kiện JMS; nháy đơn String, TRUE/FALSE boolean, ngoặc rõ ràng chưa?
4. **Null:** thuộc tính nào có thể thiếu? `IS NULL`, UNKNOWN và `NOT` đã được tính đúng chưa?
5. **Consumer cạnh tranh:** có consumer không selector hay selector chồng lấn trên queue không?
6. **Timeout:** synchronous receive có thời hạn hợp lý và xử lý `null` chưa?
7. **Listener:** `@JmsListener` được Spring scan, listener factory chạy và cấu hình selector có hiệu lực chưa?
8. **Kiểu sau convert:** nếu dùng `receiveSelectedAndConvert`, có kiểm tra runtime payload type không?
9. **Transaction:** ack, rollback, retry và DLQ đã phù hợp khi handler lỗi chưa?
10. **Observability:** có metric backlog/no matching consumers/expired messages không?
11. **Bảo mật:** có ACL và authorization ngoài selector cho tenant/đối tượng nhạy cảm không?
12. **Triển khai:** tên property/schema có tương thích với message cũ còn tồn trong broker không?

Một bộ test tối thiểu cần gửi **message match**, **message không match**, **property thiếu**, **property sai kiểu**, và **hai selector chồng lấn** nếu kiến trúc có nhiều consumers. Đối chiếu queue depth và message body/metadata bằng broker management tooling, không chỉ dựa trên log handler.

## 14. Lỗi phổ biến và hướng xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `receiveSelected` luôn trả `null` | Không có message match trước timeout | Xem queue depth, selector và properties thực |
| Queue có message nhưng listener không chạy | Các message tồn không match, endpoint chưa start hoặc sai destination | Kiểm tra listener registry, selector, broker permissions |
| Selector numeric không nhận `"8"` | Property được ghi String | Dùng `setIntProperty`, không kỳ vọng auto-conversion |
| Selector Boolean không nhận `"true"` | Property được ghi String | Dùng `setBooleanProperty` |
| `NOT (tenantId = ...)` không nhận message thiếu tenantId | Logic UNKNOWN | Dùng `IS NULL` nếu muốn bao gồm trường hợp thiếu |
| Gọi `receiveSelected("queue")` nhận sai kết quả | Một tham số là **selector** khi dùng default destination | Gọi overload `receiveSelected(destinationName, selector)` |
| Gọi `receive(...)` không lọc dù có property | `receive` không nhận selector | Dùng `receiveSelected` hoặc listener có selector |
| Listener lấy message không đúng nhóm | Selector chồng lấn hoặc có consumer không selector | Kiểm kê toàn bộ consumers, thiết kế điều kiện loại trừ |
| Hai listener mong nhận cùng một queue message | Queue không broadcast | Dùng topic/subscription hoặc routing fan-out |
| `JMSReplyTo = ...` trong selector không hoạt động | Header này không nằm trong tập selector headers JMS | Dùng header hợp lệ, property hoặc chọn destination ngay ở consumer |
| TextMessage JSON có field nhưng selector không thấy | Selector không đọc body | Copy metadata cần lọc thành typed property |
| Selector String literal chứa nháy đơn báo lỗi | Không escape `'` | Escape bằng `''` hoặc tạo ID an toàn |
| Không nhận đúng reply request/reply | Correlation thiếu/sai hoặc consumer khác đã lấy | Dùng `JMSCorrelationID` đúng contract; quản lý shared reply queue |
| Message không match tích tụ | Không có consumer đủ điều kiện/TTL chưa phù hợp | Monitor backlog, sửa contract, bổ sung consumer/chính sách |
| Lỗi sau receive gây mất hoặc lặp message | Ack/transaction/redelivery không đúng | Cấu hình và kiểm thử rollback/idempotency |
| Hiệu năng giảm khi hàng nghìn selector consumers | Chi phí broker/consumer creation | Consolidate dispatch, chọn partitioning hoặc listener lâu dài |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Muốn đọc đồng bộ chỉ các order có `priorityLevel>=5`, nên gọi `receive("orders.events")` rồi kiểm tra hay `receiveSelected("orders.events", selector)`?

**Đáp án:** Dùng `receiveSelected` để provider chỉ giao message match. Nếu gọi `receive` không selector rồi bỏ qua, message không mong muốn có thể đã bị tiêu thụ/ack.

**Câu 2.** `receiveSelectedAndConvert("eventType = 'ORDER_CREATED'")` dùng destination nào?

**Đáp án:** Default destination đã cấu hình trên JmsTemplate. Đây là overload một tham số **selector**, không phải destination name.

**Câu 3.** `@JmsListener(selector="express = TRUE")` có nhận message với `setStringProperty("express","true")` không?

**Đáp án:** Không match theo Boolean như mong muốn: String không được selector tự parse thành Boolean. Producer cần dùng `setBooleanProperty`.

**Câu 4.** Queue có message không match một listener. Có chắc message bị xóa không?

**Đáp án:** Không. Message không được giao cho consumer có selector đó; nó có thể còn trong queue hoặc được consumer khác nhận, tùy expiry và chính sách broker.

**Câu 5.** Hai listener trên cùng queue có selector chồng lấn cùng match một message. Cả hai đều được gọi?

**Đáp án:** Không. Queue giao một message tới một consumer đủ điều kiện, không fan-out. Nếu cần hai service đều nhận, cân nhắc Topic/subscriptions.

**Câu 6.** Selector có truy cập `JMSDestination` hoặc field `orderId` trong JSON body không?

**Đáp án:** Không. `JMSDestination` không thuộc tập standard headers JMS cho selector; body cũng không được selector đọc. Dùng property phù hợp hoặc chọn destination trực tiếp.

**Câu 7.** Khác nhau giữa `receiveSelected` và `receiveSelectedAndConvert`?

**Đáp án:** Cả hai chọn message bằng selector, nhưng `receiveSelected` trả raw JMS Message, còn `receiveSelectedAndConvert` trả payload Java qua MessageConverter.

**Câu 8.** `tenantId` thiếu và selector là `NOT (tenantId='blue')`. Message có match không?

**Đáp án:** Không, vì so sánh với property NULL là UNKNOWN, phủ định UNKNOWN vẫn UNKNOWN. Chỉ TRUE mới match.

**Câu 9.** Có thể dùng `JMSCorrelationID` để lọc response trên reply queue chung không?

**Đáp án:** Có, vì đây là một trong sáu standard headers được JMS selector hỗ trợ. Vẫn cần quản lý reply destination, timeout, concurrency và bảo mật riêng.

**Câu 10.** Trong demo hai queue, vì sao cần tách polling queue khỏi listener queue?

**Đáp án:** Nếu dùng chung queue, hai consumers có thể cạnh tranh lấy message, khiến output phụ thuộc timing. Tách hai queue giúp minh họa độc lập hai hình thức selection.

## Tài liệu chính thức để đối chiếu

- [Jakarta Messaging 3.1 Specification — Message selection (3.8), queue semantics (4.1.2) và topic semantics (4.2.2)](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): chuẩn cú pháp, loại header/property selector có thể truy cập, NULL, behavior khi không match.
- [Jakarta Messaging 3.1 API — Message](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message): property types, selector syntax và rules.
- [Spring Framework 6.2.14 Javadoc — JmsTemplate](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `receiveSelected`, `receiveSelectedAndConvert`, `setReceiveTimeout` và overloads.
- [Spring Framework Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): synchronous receive, blocking and timeout.
- [Spring Framework Reference — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@JmsListener`, endpoint/container lifecycle, listener arguments.
- [Spring Framework 6.2 — JmsListener Annotation](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/annotation/JmsListener.html): thuộc tính `selector` của annotation.
- [Spring Boot 3.5 — JMS/Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): starter, native broker, listener auto-configuration.
