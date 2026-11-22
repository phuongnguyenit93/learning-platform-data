# Kiểm soát ObjectMessage, trusted packages và rủi ro giải tuần tự

> **Chương:** Bảo mật  
> **Phạm vi:** Java/JMS với Apache ActiveMQ Classic và Apache Artemis. Bài tập trung vào **Java native deserialization** khi xử lý `ObjectMessage`, cách đặt allowlist/trusted packages cho đúng client/provider, cách xác minh cấu hình có tác dụng và lựa chọn an toàn hơn bằng `TextMessage`/JSON. Ví dụ dùng Java 17 + `jakarta.jms`, ActiveMQ Classic 6.x hoặc Artemis 2.57.x. Không dùng mẫu payload khai thác hay tắt kiểm soát bảo mật để chạy thử.

## 1. Điểm nguy hiểm không nằm ở tên message mà ở việc dựng lại Java object

`jakarta.jms.ObjectMessage` chứa một đối tượng triển khai `java.io.Serializable`. Khi producer gọi `setObject(...)` hoặc `createObjectMessage(...)`, provider tuần tự hóa đối tượng thành byte; khi consumer gọi `getObject()`, provider khôi phục một *object graph* từ những byte này bằng cơ chế Java serialization.

```text
Producer Java                     ActiveMQ broker                  Consumer Java
     │                                  │                                │
     │ ObjectMessage(Serializable)      │                                │
     ├── Java serialization ───────────▶│ lưu/routing serialized bytes   │
     │                                  ├────────── delivery ───────────▶│
     │                                  │                                ├── getObject()
     │                                  │                                ├── ObjectInputStream /
     │                                  │                                │   class resolution + readObject()
     │                                  │                                └── object được tạo trong JVM
```

**Ranh giới tin cậy:** sau khi byte đi qua broker, consumer không nên coi object graph là đáng tin chỉ vì message đến từ một queue có tên quen thuộc. Tài khoản producer có thể bị lộ, bridge có thể chuyển dữ liệu từ broker khác, một hệ thống tích hợp có thể gửi dữ liệu lỗi hoặc consumer có thể đọc backlog được tạo từ phiên bản ứng dụng cũ.

Java deserialization có thể thực hiện mã trong `readObject`/`readResolve`, constructor liên quan hoặc các phương thức của class xuất hiện trong object graph; class trên classpath có thể có hành vi nguy hiểm ngoài việc gán dữ liệu. Một chuỗi gadget phù hợp trên classpath có thể dẫn tới thực thi hành vi ngoài ý muốn; object graph rất lớn/sâu cũng gây cạn CPU, RAM hoặc tài nguyên. **Không cần cung cấp mã khai thác để nhận diện rủi ro này**. [Oracle Java Serialization Filtering](https://docs.oracle.com/en/java/javase/17/core/serialization-filtering1.html).

Điều nguy hiểm là ứng dụng **tự động giải tuần tự một kiểu tùy ý trước khi validate nội dung nghiệp vụ**. Chỉ catch `ClassCastException` *sau* `getObject()` không tạo được ranh giới an toàn, vì việc dựng object đã xảy ra.

## 2. Chính xác lúc nào ứng dụng có thể deserialization?

| Thao tác | Có cần khôi phục object graph hay không? | Cách nhìn nhận an toàn |
|---|---|---|
| `JMSContext.createObjectMessage(dto)` | Producer thường serialize đối tượng để gửi | Producer phải kiểm soát kiểu và kích thước dữ liệu |
| Broker forward/store một message | Có thể chủ yếu vận chuyển byte; implementation/plugin có thể inspect nội dung | **Không** suy rằng broker đã quét và bảo đảm an toàn cho client |
| `consumer.receive(...)` trả về `ObjectMessage` | Không nên mặc định đã có object DTO | **Chưa** gọi `getObject()` chỉ để log payload |
| `((ObjectMessage) m).getObject()` | **Có**: điểm deserialization điển hình | Áp allowlist trước khi tạo connection/consumer |
| `message.getBody(MyDto.class)` với `ObjectMessage` | Có thể kích hoạt conversion/deserialization | Không phải giải pháp tránh rủi ro |
| Spring `JmsTemplate.receiveAndConvert(...)` | Với `SimpleMessageConverter` + `ObjectMessage` sẽ lấy body Java object | Có thể vô tình kích hoạt deserialization dù service không gọi `getObject()` trực tiếp |
| JMS `TextMessage.getText()` | Trả chuỗi; **không** dùng Java ObjectInputStream | Vẫn cần JSON/schema validation, giới hạn kích thước và xử lý input không tin cậy |

**Quy tắc ưu tiên:** nếu đang thiết kế integration mới, **không sử dụng ObjectMessage**. Ưu tiên `TextMessage` chứa JSON được parse vào một DTO tường minh, hoặc `BytesMessage` với schema codec được kiểm soát. Chỉ áp dụng cơ chế ObjectMessage cho tích hợp Java–Java cũ chưa thể chuyển đổi ngay.

### Tại sao một `trustedPackages` rộng vẫn chưa đủ?

Allowlist package chỉ hạn chế **tên class có thể được dựng lại**. Nó không kiểm tra tính hợp lệ của `eventId`, số lượng phần tử, đường dẫn tệp, URL nội bộ, nội dung lệnh nghiệp vụ hoặc hành vi của tất cả class được phép. Nếu một package đã được allow có class nguy hiểm, allowlist không thể thay security review của class ấy.

Do đó cần nhiều lớp: **chọn codec an toàn → allowlist cụ thể nếu buộc dùng ObjectMessage → hạn chế độ sâu/kích thước → xác thực và phân quyền destination → vận hành, logging và xử lý lỗi**. TLS và ACL giúp giảm nguồn dữ liệu ác ý nhưng không biến native deserialization thành an toàn.

## 3. ActiveMQ Classic: `SERIALIZABLE_PACKAGES` và `setTrustedPackages`

ActiveMQ Classic bổ sung cơ chế danh sách package đáng tin cho `ObjectMessage` từ các nhánh 5.12.2 và 5.13.0 trở đi. Cơ chế này vẫn cần được cấu hình có chủ đích cho client hiện đại. Có hai nơi cấu hình **khác phạm vi**:

1. **JVM system property** `org.apache.activemq.SERIALIZABLE_PACKAGES`, được Classic client và broker đọc để giới hạn package có thể deserialize.
2. **`ActiveMQConnectionFactory.setTrustedPackages(...)`**, cấu hình danh sách trên factory của ứng dụng; **ghi đè system property** đối với các connection được tạo từ factory đó.

**Nguyên tắc:** giữ `trustAllPackages=false`; không cấu hình `*`. Bật allowlist theo package hẹp mà ứng dụng thực sự cần để đọc ObjectMessage.

### 3.1. Client Classic dùng allowlist hẹp

```java
import java.util.List;
import org.apache.activemq.ActiveMQConnectionFactory;

ActiveMQConnectionFactory factory = new ActiveMQConnectionFactory(
    "tcp://127.0.0.1:61616");

factory.setTrustAllPackages(false);
factory.setTrustedPackages(List.of(
    "com.example.messaging.dto",
    "java.lang" // Ví dụ DTO chỉ chứa String; kiểm tra toàn bộ object graph thực tế.
));

// Sau khi cấu hình factory mới tạo Connection/JMSContext.
// Đừng thay allowlist trên singleton factory khi đang có client hoạt động.
```

`com.example.messaging.dto` là package minh họa của DTO **do ứng dụng sở hữu**, không phải tên package được mặc định tin cậy của Classic. Trong hệ thống thật, dùng namespace ứng dụng cụ thể, không chọn `com.example`, `java`, `org.apache` hoặc `*` như một cách mở rộng nhanh. Nếu DTO chứa `ArrayList`, `HashMap` hoặc class khác trong graph, cần đánh giá kỹ từng package bổ sung; nếu phải allow `java.util` quá rộng, nên ưu tiên chuyển sang JSON.

### 3.2. Cấu hình ở JVM broker hoặc client

Ví dụ cấu hình property cho **một JVM Classic** đã được kiểm thử, kèm các package runtime mà tài liệu Classic nêu:

```text
-Dorg.apache.activemq.SERIALIZABLE_PACKAGES=javax.security,java.util,org.apache.activemq,org.fusesource.hawtbuf,com.thoughtworks.xstream.mapper,com.example.messaging.dto
```

Đối với broker được khởi động bằng shell script Classic, property này có thể đặt trong `ACTIVEMQ_OPTS` của cấu hình môi trường broker. **Không** coi danh sách trên là danh sách chuẩn cho mọi phiên bản: kiểm tra defaults/client/broker thực tế trước khi thay để tránh loại bỏ class nội bộ đang cần; thu hẹp theo phần mềm triển khai và review khi upgrade.

Trong một JVM có nhiều ứng dụng JMS hoặc nhiều factory, system property ảnh hưởng mặc định của JVM, còn `setTrustedPackages(...)` trên một factory cụ thể có thể override. Nếu broker phải deserialize nội dung vì plugin/selector/logic đặc thù, **cấu hình ở client không tự bảo vệ broker**; kiểm soát từng JVM/đường code có quyền giải tuần tự.

### 3.3. Một anti-pattern thường thấy

```java
// KHÔNG LÀM: vô hiệu hóa lớp kiểm soát của Classic.
factory.setTrustAllPackages(true);
```

Tài liệu Classic có API này để hỗ trợ kiểm thử/khả năng tương thích, nhưng dùng trong production sẽ cho phép class bất kỳ từ stream được thử deserialize. Tương tự, `-Dorg.apache.activemq.SERIALIZABLE_PACKAGES=*` là mở toàn bộ. Nếu một hệ thống cũ chỉ hoạt động khi bật các tùy chọn này, **đó là tín hiệu cần inventory DTO và thu hẹp allowlist**, không phải lý do mặc định nới ACL.

## 4. Artemis: `deserializationAllowList` và `deserializationDenyList`

Artemis 2.57.0 cung cấp bộ lọc class/package cho **JMS ObjectMessage**. Hai danh sách có semantics khác Classic:

- **Allow list:** class/package được phép deserialize.
- **Deny list:** class/package bị từ chối. **Deny list được ưu tiên** nếu một class xuất hiện đồng thời ở cả hai.
- **Cả hai danh sách rỗng (mặc định):** bộ lọc Artemis **cho phép mọi class serializable** được deserialize. Nghĩa là **không có chặn class theo chính sách này**; không được suy rằng bản thân Artemis bật allowlist chặt theo mặc định.
- **Allow list khác rỗng:** class không khớp danh sách allow sẽ bị từ chối, trừ trường hợp nó đã bị từ chối sớm bởi deny list.

Một entry có thể là **fully qualified class name** (`com.example.messaging.dto.LegacyOrderEvent`), package chính xác (`com.example.messaging.dto`) hoặc package cha bao gồm subpackages. `*` nghĩa là khớp mọi class — **không dùng cho allow list production**.

### 4.1. Cấu hình trực tiếp trên Artemis Core JMS factory

```java
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

ActiveMQConnectionFactory factory = new ActiveMQConnectionFactory(
    "tcp://127.0.0.1:61616"
    + "?deserializationAllowList=com.example.messaging.dto,java.lang"
    + "&deserializationDenyList=com.example.legacy.unsafe");

try {
    // Chỉ tạo context và đọc ObjectMessage sau khi factory đã an toàn.
    // Nếu đọc ngoài allowlist, getObject() bị từ chối.
} finally {
    factory.close();
}
```

Đây là **URI của Artemis Core JMS client**, không phải `broker.xml`. `deserializationAllowList` và `deserializationDenyList` có phân cách bằng dấu phẩy. Trong attribute XML, dấu `&` của query string phải được escape thành `&amp;`.

**Không bắt buộc khai báo deny list để allowlist hoạt động:** một allowlist hẹp đã mặc định chặn mọi class không khớp. Deny list hữu ích để chặn rõ ràng các nhóm bị cấm, nhưng không phải thay thế allowlist.

### 4.2. Cấu hình toàn JVM hoặc resource adapter

Nếu không tiện truyền URI, có thể đặt **JVM system properties** trên phía **consumer**:

```text
-Dorg.apache.activemq.artemis.jms.deserialization.allowlist=com.example.messaging.dto,java.lang
-Dorg.apache.activemq.artemis.jms.deserialization.denylist=com.example.legacy.unsafe
```

Factory có allow/deny list explicit **ghi đè** các giá trị system properties đối với factory đó. Với JMS resource adapter trong application server, các trường cấu hình tương ứng là `deserializationAllowList` và `deserializationDenyList`; phải áp dụng chúng trong cấu hình adapter/connection factory thực tế, không chỉ trong cấu hình của một client Java SE khác.

**Không nhầm vị trí bảo vệ:** tài liệu Artemis mô tả hai property này cho **JMS ObjectMessage deserialization** của runtime sử dụng JMS client/resource adapter. Đây **không** phải một bộ lọc protocol chung có thể tự động chặn mọi loại serialized data trên mọi acceptor; authorization của broker là lớp bảo vệ khác.

### 4.3. So sánh Classic và Artemis trước khi đổi broker

| Điều cần kiểm soát | ActiveMQ Classic | Apache Artemis |
|---|---|---|
| Class/package filtering | `SERIALIZABLE_PACKAGES` / `setTrustedPackages` | `deserializationAllowList` / `deserializationDenyList` |
| Mặc định khi không explicit allowlist | Classic yêu cầu package tin cậy cho ObjectMessage ở các bản đã được harden | **Hai list rỗng ⇒ class filter cho phép tất cả** |
| Cấu hình client Java | `ActiveMQConnectionFactory.setTrustedPackages(List<String>)` | Query URI `deserializationAllowList=...` |
| Cấu hình JVM | `-Dorg.apache.activemq.SERIALIZABLE_PACKAGES=...` | `-Dorg.apache.activemq.artemis.jms.deserialization.allowlist=...` |
| Tắt kiểm soát | `trustAllPackages=true` / wildcard `*` (tránh) | Allowlist trống hoặc `*`, không đáp ứng deny-by-default |
| Phạm vi bảo vệ | Classic-side ObjectMessage unmarshal | Artemis JMS ObjectMessage unmarshal |
| Có thay thế JSON schema validation? | **Không** | **Không** |

Khi migrate từ Classic sang Artemis, **không được** giả định danh sách `trustedPackages` tự được chuyển theo. Cần tạo allowlist tương ứng trong config Artemis và chạy negative test; nếu không, hành vi có thể **lỏng hơn** mong đợi.

## 5. Code Java/JMS: ObjectMessage legacy được lọc có chủ đích

Mục tiêu phần này **không khuyến khích tạo ObjectMessage mới**. Đây là ví dụ giảm rủi ro khi đang bảo trì một integration Java–Java cũ bắt buộc dùng `Serializable`.

### 5.1. DTO được phép: không có hook deserialization tự viết

Tệp `src/main/java/com/example/messaging/dto/LegacyOrderEvent.java`:

```java
package com.example.messaging.dto;

import java.io.Serializable;

// Chỉ chứa các trường bất biến kiểu String.
public record LegacyOrderEvent(String eventId, String orderId)
        implements Serializable {
    private static final long serialVersionUID = 1L;
}
```

Record này giúp ví dụ đơn giản; **không** coi `record implements Serializable` tự động an toàn nếu nó chứa các đối tượng phức tạp/cấu trúc không giới hạn. Cần pin/schema version và review mọi nested class trong object graph, vì ObjectMessage có sự phụ thuộc classpath giữa sender và receiver.

### 5.2. Sender/receiver Java dùng API chung

Tệp `src/main/java/com/example/messaging/LegacyObjectMessageProbe.java`:

```java
package com.example.messaging;

import com.example.messaging.dto.LegacyOrderEvent;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.ObjectMessage;
import jakarta.jms.Queue;

public final class LegacyObjectMessageProbe {
    private static final String QUEUE = "lab.security.object.allowed";

    private LegacyObjectMessageProbe() {}

    public static void sendAllowed(ConnectionFactory factory,
                                   String user, String password) {
        try (JMSContext tx = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue queue = tx.createQueue(QUEUE);
            LegacyOrderEvent dto =
                new LegacyOrderEvent("evt-001", "order-981");
            ObjectMessage message = tx.createObjectMessage(dto);
            tx.createProducer().send(queue, message);
            tx.commit();
        }
    }

    public static void receiveAllowed(ConnectionFactory factory,
                                      String user, String password)
                                      throws JMSException {
        try (JMSContext tx = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue queue = tx.createQueue(QUEUE);
            try {
                Message received = tx.createConsumer(queue).receive(3_000L);
                if (!(received instanceof ObjectMessage objectMessage)) {
                    throw new IllegalStateException("ObjectMessage expected");
                }

                // ĐIỂM NHẠY CẢM: provider sẽ deserialize ở getObject().
                Object value = objectMessage.getObject();
                if (!(value instanceof LegacyOrderEvent dto)) {
                    throw new IllegalStateException("Unexpected object type");
                }
                if (!"evt-001".equals(dto.eventId())
                        || !"order-981".equals(dto.orderId())) {
                    throw new IllegalStateException("Invalid DTO fields");
                }

                // Không làm side effect ngoài JMS trong ví dụ.
                System.out.println("ALLOWED type=" + value.getClass().getName());
                tx.commit();
            } catch (JMSException | RuntimeException failure) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
```

**Ranh giới mẫu:** `instanceof LegacyOrderEvent` chạy **sau** `getObject()`, nên **không thay cho allowlist**. Nó chỉ kiểm tra kiểu **sau khi** provider đã giải tuần tự theo class filter. Mỗi lần xử lý có một `JMSContext` transaction; nếu deserialize lỗi, rollback và giữ nguyên message cho cơ chế cách ly, không ACK một payload chưa kiểm tra.

### 5.3. Wiring bằng Classic hoặc Artemis

Với Classic 6.x (chọn Maven dependency `org.apache.activemq:activemq-client` theo BOM/version tương thích Jakarta):

```java
import java.util.List;
import org.apache.activemq.ActiveMQConnectionFactory;

ActiveMQConnectionFactory factory =
    new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");
factory.setTrustAllPackages(false);
factory.setTrustedPackages(List.of(
    "com.example.messaging.dto", "java.lang"));

LegacyObjectMessageProbe.sendAllowed(factory, user, password);
LegacyObjectMessageProbe.receiveAllowed(factory, user, password);
```

Với Artemis 2.57.x (chọn `org.apache.artemis:artemis-jakarta-client`):

```java
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

ActiveMQConnectionFactory factory = new ActiveMQConnectionFactory(
    "tcp://127.0.0.1:61616"
    + "?deserializationAllowList=com.example.messaging.dto,java.lang");
try {
    LegacyObjectMessageProbe.sendAllowed(factory, user, password);
    LegacyObjectMessageProbe.receiveAllowed(factory, user, password);
} finally {
    factory.close();
}
```

Các đoạn wiring nằm trong một method có `user`/`password` lấy từ nguồn bí mật của deployment. **Chọn một provider cho mỗi lần chạy** và dùng đúng transport (Classic OpenWire, Artemis Core); không để hai `ActiveMQConnectionFactory` từ hai package cùng import vào một file với tên đơn. Trong lab phải provision queue `lab.security.object.allowed` và cấp ACL tối thiểu cho user thử nghiệm.

**Không chứng minh broker được bảo vệ chỉ bằng test consumer:** với Classic, review `org.apache.activemq.SERIALIZABLE_PACKAGES` trên chính broker JVM; với Artemis, test chủ yếu xác minh client-side `ObjectMessage` filtering, không thay kiểm soát access cho broker/management tools.

## 6. Negative test bằng DTO lành tính để chứng minh “deny-by-default”

Một allowlist chỉ có ý nghĩa khi **class không thuộc allowlist thật sự bị chặn**. Không dùng gadget, payload độc hại hoặc công cụ exploit; dùng một DTO tầm thường ở package khác, chẳng hạn:

```java
package com.example.external.dto;

import java.io.Serializable;

public record HarmlessExtraEvent(String name) implements Serializable {
    private static final long serialVersionUID = 1L;
}
```

Sử dụng một producer **lab** để gửi `ObjectMessage(new HarmlessExtraEvent("test"))` vào queue riêng `lab.security.object.blocked`. Trong consumer test, class `HarmlessExtraEvent` **có trên classpath** để phân biệt “bị chính allowlist chặn” với `ClassNotFoundException`. Cấu hình chỉ allow `com.example.messaging.dto` và `java.lang` như mục 5.

**Ma trận kỳ vọng:**

| Case | Payload | Consumer allowlist | Mong đợi |
|---|---|---|---|
| Positive | `LegacyOrderEvent` từ package được phép | Hẹp | `getObject()` trả DTO và validate thành công |
| Negative | `HarmlessExtraEvent` từ package khác | Hẹp | Consumer **không được phép** deserialize; nhận exception phù hợp provider |
| Same class, no classpath | `LegacyOrderEvent` | Hẹp nhưng thiếu jar DTO | Có thể gặp `ClassNotFoundException`; **khác** bằng chứng allowlist |
| Artemis default lists rỗng | `HarmlessExtraEvent` | Không cấu hình | Bộ lọc class của Artemis **không chặn chỉ vì package**, cho thấy cần explicit allowlist |
| Classic wildcard/trustAll | `HarmlessExtraEvent` | Mở toàn bộ | Là cấu hình **không đạt security review**, không dùng cho production |

Khi gửi một message không được phép, điểm từ chối có thể phụ thuộc provider hoặc phía broker (đặc biệt nếu có plugin giải tuần tự): đừng hardcode assertion phải ném exception **chính xác tại lệnh send**. Mục tiêu kiểm chứng là **không thể lấy được object từ consumer đã khóa**; ghi exception class/cause chain và xác nhận không có side effect.

### Không biến negative test thành vòng rollback vô hạn

Nếu consumer gặp `getObject()` bị từ chối rồi `rollback()` vô hạn, message độc hại/lỗi vẫn có thể chiếm queue và tạo *poison loop*. Cần:

- Phân loại exception deserialization là **lỗi dữ liệu/quyền lớp**, không phải lỗi mạng tạm thời.
- Có chính sách giới hạn redelivery và **DLQ/quarantine** riêng; không dùng thao tác browse DLQ mà lại gọi `getObject()` vô điều kiện.
- Chỉ log **message ID, destination, eventId từ property đơn giản và mã lỗi**; tránh log raw serialized bytes hoặc `toString()` của object không tin cậy.
- Điều tra message ở quarantine bằng metadata/raw bytes theo quy trình kiểm soát, không mở bằng một công cụ admin tự deserialize trên classpath rộng.

**Không** đưa case negative vào queue nghiệp vụ thật hoặc để test tự động xóa backlog để làm assertion xanh.

## 7. Lựa chọn nên dùng: `TextMessage` + JSON + DTO tường minh

Với hợp đồng integration mới, tránh Java Object Serialization:

```text
OrderCreatedV1 Java record
       │
       ├── Jackson serializeToJson()
       ▼
JMS TextMessage: {"eventId":"evt-001","orderId":"order-981"}
       │
       └── consumer: JSON parser → OrderCreatedV1 → validation → nghiệp vụ
```

Ưu điểm: không phụ thuộc native `Serializable` graph, dễ tương tác giữa Java/Go/Node.js, có schema/version độc lập với classpath, dễ quan sát metadata mà không cần khởi tạo class không đáng tin. JSON **vẫn là dữ liệu không tin cậy**: phải giới hạn kích thước, cấm polymorphic default typing nguy hiểm, parse vào type cụ thể và validate trường nghiệp vụ.

### 7.1. Ví dụ Java/JMS không dùng ObjectMessage

DTO ở `src/main/java/com/example/messaging/contract/OrderCreatedV1.java`:

```java
package com.example.messaging.contract;

public record OrderCreatedV1(String eventId, String orderId) {}
```

Code gửi/nhận (thêm Jackson databind tương thích bản ứng dụng):

```java
package com.example.messaging;

import com.example.messaging.contract.OrderCreatedV1;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

public final class JsonTextMessageProbe {
    private static final String QUEUE = "lab.security.orders.json";
    private final ObjectMapper mapper = new ObjectMapper();

    public void publish(ConnectionFactory factory, String user,
                        String password, OrderCreatedV1 event) throws Exception {
        if (event.eventId() == null || event.eventId().isBlank()) {
            throw new IllegalArgumentException("Missing eventId");
        }
        String body = mapper.writeValueAsString(event);
        try (JMSContext ctx = factory.createContext(user, password)) {
            TextMessage message = ctx.createTextMessage(body);
            message.setStringProperty("schema", "order-created-v1");
            message.setStringProperty("eventId", event.eventId());
            ctx.createProducer().send(ctx.createQueue(QUEUE), message);
        }
    }

    public void receive(ConnectionFactory factory, String user,
                        String password) throws Exception {
        try (JMSContext tx = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            try {
                Message message = tx.createConsumer(tx.createQueue(QUEUE))
                    .receive(3_000L);
                if (!(message instanceof TextMessage text)) {
                    throw new IllegalArgumentException("TextMessage expected");
                }
                if (!"order-created-v1".equals(
                        message.getStringProperty("schema"))) {
                    throw new IllegalArgumentException("Unsupported schema");
                }

                String json = text.getText();
                if (json.length() > 32_768) {
                    throw new IllegalArgumentException("Payload too large");
                }
                OrderCreatedV1 event =
                    mapper.readValue(json, OrderCreatedV1.class);
                if (event.eventId() == null || event.eventId().isBlank()
                        || event.orderId() == null || event.orderId().isBlank()) {
                    throw new IllegalArgumentException("Invalid event fields");
                }

                System.out.println("VALIDATED eventId=" + event.eventId());
                // Trong lab chưa có side effect; production dùng outbox/idempotency.
                tx.commit();
            } catch (Exception failure) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
```

Đoạn trên **không hề gọi `ObjectInputStream`/`ObjectMessage.getObject()`**. Cần giới hạn kích thước trước khi parse JSON; `String.length()` chỉ là chốt minh họa **sau khi JMS provider đã nhận bytes**, không thay broker-side `max-size-bytes`/max-message-size và giới hạn parser input. Với JSON rất lớn, xác minh provider/message-size policy và Jackson stream constraints trước khi deploy.

### 7.2. Tránh ObjectMessage “ẩn” trong Spring JMS

`SimpleMessageConverter` (mặc định của `JmsTemplate` khi không cấu hình khác) có thể biến một `Serializable DTO` thành **`ObjectMessage`**, và `receiveAndConvert` trên `ObjectMessage` có thể gọi `getObject()`. Vì vậy câu “ứng dụng không dùng `createObjectMessage`” **không chứng minh** không có native deserialization.

Ví dụ cấu hình Spring Framework 6.2 để dùng JSON `TextMessage` với class mapping cụ thể:

```java
import java.util.Map;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import com.example.messaging.contract.OrderCreatedV1;

@Configuration(proxyBeanMethods = false)
class SafeJmsConverterConfig {
    @Bean
    MessageConverter jmsMessageConverter() {
        MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();
        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("_type");
        converter.setTypeIdMappings(
            Map.of("order-created-v1", OrderCreatedV1.class));
        return converter;
    }
}
```

Đây là **mẫu cho Spring Framework 6.2/Jackson 2**; cấu hình bean phải thực sự được gắn vào `JmsTemplate`/listener container đang chạy. Với Spring Framework 7/Jackson đời mới, kiểm tra API và version tương ứng. Dùng mapping class **cố định**, không bật Jackson default polymorphic typing trên input không tin cậy chỉ để tiết kiệm định nghĩa DTO.

**Chốt kiểm thử:** gửi một `OrderCreatedV1` bằng `JmsTemplate.convertAndSend`, đọc message thô bằng `receive()` trên queue lab và assert nó là `TextMessage`; không chỉ assert business payload đúng. Test giúp phát hiện converter bị thay đổi làm quay lại `ObjectMessage`.

## 8. JDK `ObjectInputFilter`: lớp phòng vệ bổ sung, không thay allowlist broker client

Java 17 có `java.io.ObjectInputFilter` (JEP 290) để giới hạn class, độ sâu, số reference, array và số byte của object graph đang deserialize. Một ví dụ **pattern minh họa** cho JVM chuyên dụng, cần review và test ở staging:

```text
-Djdk.serialFilter=maxdepth=20;maxrefs=1000;maxarray=10000;maxbytes=1048576;com.example.messaging.dto.**;java.base/*;!*
```

Giải thích:

- `maxdepth`, `maxrefs`, `maxarray`, `maxbytes` đặt giới hạn object graph/stream.
- `com.example.messaging.dto.**` cho phép các class trong package DTO và subpackages theo cú pháp JDK filter.
- `java.base/*` là **toàn bộ module java.base**, khá rộng; dùng để minh họa cú pháp module pattern, phải thu hẹp theo dữ liệu và rủi ro thực tế.
- `!*` từ chối các class không khớp pattern trước đó.

**Không paste trực tiếp cấu hình này vào broker production.** Bộ lọc JVM-wide có thể ảnh hưởng những luồng Java serialization nội bộ khác của broker/framework, hoặc bị kết hợp với stream-specific filter theo quy tắc `serialFilterFactory`. Quan trọng hơn, filtering chỉ có tác dụng trên các luồng deserialization thực sự đi qua cơ chế `ObjectInputStream` có áp filter tương ứng. Phải test cùng với Classic trusted packages hoặc Artemis allowlist, không dùng `jdk.serialFilter` như bằng chứng “mọi protocol đã an toàn”.

Nếu chạy property này trong shell, phải **quote** đúng để dấu `;` không bị shell xử lý thành dấu phân tách lệnh. Có thể đặt vào JVM arguments trong cấu hình startup và xác minh qua cấu hình runtime. Đọc thêm [Oracle ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html).

## 9. Runbook xác minh và xử lý sự cố

### 9.1. Bộ test tối thiểu không chứa payload độc hại

| Test | Thao tác | PASS khi |
|---|---|---|
| T1 — Positive allowlist | Gửi `LegacyOrderEvent` từ package được phép | `getObject()` trả đúng record và validated fields |
| T2 — Negative class | Gửi `HarmlessExtraEvent` ở package ngoài allowlist | Consumer khóa **không thể** lấy object; không có side effect |
| T3 — Classpath lỗi | Bỏ jar DTO ở một consumer lab | Phân biệt được `ClassNotFoundException` với từ chối allowlist |
| T4 — Artemis default risk | Trong JVM lab riêng, thử client không allowlist | Kiểm tra thấy default filter không bảo vệ deny-by-default; **không** dùng cấu hình này ở production |
| T5 — Spring converter | Gửi DTO bằng template đã cấu hình JSON | Nhận JMS `TextMessage`, không phải `ObjectMessage` |
| T6 — Poison handling | Consumer nhận message bị chặn, rollback/retry hữu hạn | Sau ngưỡng, vào quarantine/DLQ; consumer không kẹt vòng lặp |
| T7 — Restart/upgrade | Restart consumer và chạy lại T1/T2 | Allowlist vẫn có hiệu lực, không bị startup config override |

**Ghi nhận kiểm chứng:** JVM/JDK version, broker/client artifact versions, tên factory, startup JVM args, package allow/deny có hiệu lực, queue lab, eventId, exception class/cause chain và kết quả T1/T2. Không log raw byte serialization hoặc thông tin bí mật; không cố deserialize payload ở console chỉ để xem dữ liệu.

### 9.2. Phân biệt triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Hướng khắc phục |
|---|---|---|
| Classic báo class/package untrusted | `trustedPackages` không có DTO hoặc class nested | Thu thập class name trong log an toàn, review graph rồi cập nhật allowlist hẹp |
| Artemis bất ngờ deserialize class không mong đợi | Allow/deny mặc định rỗng hoặc factory override property | Đặt allowlist explicit ở đúng factory/resource adapter và test T2 |
| `ClassNotFoundException` | Consumer thiếu đúng artifact DTO hoặc package đổi | Đồng bộ contract/version; ưu tiên JSON để giảm phụ thuộc classpath |
| `InvalidClassException`/`serialVersionUID` mismatch | Java class producer/consumer khác version | Version hóa DTO/sự kiện; không dùng Serializable làm hợp đồng liên hệ thống |
| `ClassCastException` sau `getObject()` | DTO class/kiểu nghiệp vụ khác dự kiến | Kiểm tra type contract; **không** xem đây là cơ chế chống deserialization |
| `JmsTemplate.receiveAndConvert` gây lỗi deserialization | Converter mặc định nhận `ObjectMessage` | Kiểm tra actual JMS type; cấu hình JSON converter, test `TextMessage` |
| Consumer liên tục rollback cùng message | Poison payload và redelivery không giới hạn | Giới hạn retry và quarantine; tránh tự động deserialize ở DLQ browser |
| Tắt allowlist làm lỗi biến mất | Bộ lọc đang hoạt động đúng nhưng contract/class chưa phù hợp | **Không** bật trustAll; sửa contract hoặc chuyển sang `TextMessage` |

### 9.3. Security review trước khi release

1. **Inventory** toàn bộ chỗ dùng `createObjectMessage`, `setObject`, `getObject`, `Message.getBody` và converter của JMS/Spring.
2. Phân loại **nguồn gửi có tin cậy không**, queue nào có bridge, user nào có quyền send/browse; chặn public/untrusted producer bằng ACL/network.
3. Với Classic, xác minh cả **client factory allowlist** và broker JVM property nếu có deserialization trên broker; không có `trustAllPackages=true` hoặc `SERIALIZABLE_PACKAGES=*`.
4. Với Artemis, xác minh **allowlist không rỗng**, denylist chỉ bổ trợ, factory overrides được review; chạy negative test T2 ở runtime thật.
5. Giới hạn class/package, kích thước payload/object graph, timeout và resource; rà thư viện trên classpath và các method custom deserialization.
6. Có quarantine cho message không deserialize được, không để message gây retry vô tận; không xem raw object bằng công cụ tự động deserialize.
7. Với luồng mới, thay `ObjectMessage` bằng `TextMessage` JSON + schema/validation; test không có serialization native ngầm qua converter.
8. Tạo security regression test chạy sau nâng phiên bản Classic/Artemis, Spring và JDK, vì mặc định và khả năng mapping có thể thay đổi.

**Kết luận:** `ObjectMessage` vận chuyển Java serialized object graph qua một ranh giới tin cậy và có thể khiến code trong classpath được thực thi trong lúc deserialization. **Classic** cung cấp `trustedPackages` và `SERIALIZABLE_PACKAGES`; **Artemis** cung cấp `deserializationAllowList`/`DenyList` nhưng **không deny-by-default khi cả hai rỗng**. Cơ chế lọc là biện pháp giảm thiểu cho hệ thống legacy; thiết kế tốt hơn cho các service mới là **truyền dữ liệu bằng định dạng có schema** và chỉ dựng lại DTO được chỉ định rõ.

## Tài liệu chính thức

1. [ActiveMQ Classic — ObjectMessage](https://activemq.apache.org/components/classic/documentation/objectmessage): `SERIALIZABLE_PACKAGES`, `setTrustedPackages`, `setTrustAllPackages` và cảnh báo deserialization.
2. [Apache Artemis 2.57.0 — Authentication & Authorization, Controlling JMS ObjectMessage Deserialization](https://artemis.apache.org/components/artemis/documentation/latest/security.html#controlling-jms-objectmessage-deserialization): allow/deny precedence, URI properties, JVM properties và resource adapters.
3. [Oracle JDK 17 — Serialization Filtering](https://docs.oracle.com/en/java/javase/17/core/serialization-filtering1.html): serialization gadget risk, `ObjectInputFilter` và giới hạn object graph.
4. [Oracle JDK 17 — ObjectInputFilter API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): pattern syntax, filtering và filter factories.
5. [Spring Framework 6.2 — SimpleMessageConverter](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html): Serializable DTO có thể thành `ObjectMessage`.
6. [Spring Framework 6.2 — MappingJackson2MessageConverter](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html): JSON `TextMessage` và type mapping có kiểm soát.
7. [Apache Artemis — Performance Tuning](https://artemis.apache.org/components/artemis/documentation/latest/perf-tuning.html): khuyến cáo tránh `ObjectMessage` do serialization overhead.
