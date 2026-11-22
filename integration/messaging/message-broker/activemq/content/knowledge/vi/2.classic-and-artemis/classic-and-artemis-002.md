# Lập bảng tương thích broker, client, JDK và phiên bản API JMS

> **Phạm vi:** Apache ActiveMQ Classic và Apache Artemis trong hệ thống Java sử dụng queue, topic, giao tiếp bất đồng bộ và JMS/Jakarta Messaging. Các dòng phiên bản được đối chiếu với tài liệu Apache tại **ngày 17/11/2026**. Luôn xác nhận lại trang phát hành khi triển khai vì yêu cầu JDK, phiên bản thư viện và mức hỗ trợ tính năng có thể thay đổi ở bản vá tiếp theo.

## 1. Vì sao phải lập ma trận tương thích?

Một ứng dụng Java có thể biên dịch thành công nhưng vẫn không kết nối được broker, hoặc kết nối thành công mà chạy sai một tính năng JMS. Đó là vì chữ *tương thích* bao gồm **bốn lớp độc lập**:

1. **Broker:** sản phẩm và bản phát hành thực sự đang chạy, ví dụ ActiveMQ Classic 5.19.12, Classic 6.4.0 hoặc Artemis 2.57.0.
2. **JDK:** bản Java dùng chạy tiến trình broker và bản Java dùng chạy tiến trình ứng dụng client. Hai tiến trình có thể dùng JDK khác nhau.
3. **API Java:** `javax.jms` hay `jakarta.jms`, cùng mức JMS 1.1, JMS 2.0 hoặc Jakarta Messaging 3.x mà thư viện triển khai.
4. **Giao thức mạng:** OpenWire, Artemis Core, AMQP 1.0, STOMP… Broker và client phải nói được *cùng giao thức*, dù hai phía sử dụng các API Java khác nhau.

Ví dụ, một client sử dụng `jakarta.jms.ConnectionFactory` không tự nhiên nói được với bất kỳ broker nào có chữ “Jakarta” trong tài liệu. Nó cần một **provider client** triển khai giao diện đó và sử dụng giao thức mà broker hỗ trợ. Ngược lại, nếu broker đã hỗ trợ OpenWire, ứng dụng `javax.jms` cũ có thể tiếp tục giao tiếp qua mạng dù phần mềm broker mới hơn sử dụng `jakarta.jms` ở phía Java.

## 2. Phân biệt JMS, Jakarta Messaging và giao thức trên dây

| Đặc tả API | Package Java | Điểm đáng chú ý | Cách đọc khi chọn thư viện |
|---|---|---|---|
| JMS 1.1 | `javax.jms` | Mô hình `Connection` → `Session` → `MessageProducer`/`MessageConsumer`; queue, topic, acknowledgment, transaction | Thường thấy ở các ứng dụng Java EE hoặc ActiveMQ Classic đời cũ |
| JMS 2.0 | `javax.jms` | Thêm API đơn giản hóa `JMSContext`, `JMSProducer`, `JMSConsumer` và các tính năng như delivery delay, shared subscription | Phải kiểm tra **provider** đã triển khai những phương thức nào |
| Jakarta Messaging 2.0 | `javax.jms` | Tên đặc tả chuyển sang Jakarta EE nhưng vẫn giữ namespace cũ | Không suy rằng chữ “Jakarta” trong tên phiên bản đồng nghĩa với `jakarta.jms` |
| Jakarta Messaging 3.0/3.1 | `jakarta.jms` | Đổi namespace Java từ `javax.jms` sang `jakarta.jms`; phù hợp hệ sinh thái Jakarta EE mới | Phải dùng thư viện client phiên bản Jakarta, đồng bộ với framework của ứng dụng |

**Ba điều dễ nhầm:**

- `javax.jms.ConnectionFactory` và `jakarta.jms.ConnectionFactory` là **hai kiểu Java khác nhau**. Không thể ép kiểu qua lại; chỉ đổi một dòng `import` trong khi giữ provider cũ sẽ gây lỗi biên dịch hoặc nạp lớp.
- JMS và Jakarta Messaging định nghĩa **API và ngữ nghĩa ứng dụng**, không quy định một giao thức TCP chung. OpenWire, Core và AMQP 1.0 mới là những giao thức kết nối giữa client và broker.
- Nhãn “hỗ trợ Jakarta Messaging 3.1” **không mặc nhiên bảo đảm mọi chức năng**. Đặc biệt ActiveMQ Classic 5.18+/6.x công bố nhiều tính năng JMS 2.0/Jakarta Messaging 3.1 ở mức *partial*; phải kiểm tra từng chức năng dự định sử dụng.

Sơ đồ lớp kết nối:

```text
Ứng dụng Java
   |
   +-- import javax.jms.* hoặc jakarta.jms.*    [API]
   |
   +-- activeMQ / Artemis / AMQP JMS provider   [thư viện client]
                    |
                    +-- OpenWire / Core / AMQP 1.0   [giao thức mạng]
                                      |
                             Classic hoặc Artemis   [broker]
```

## 3. Bảng tương thích phiên bản **broker ↔ JDK ↔ JMS**

Bảng dưới đây lấy các dòng phát hành tiêu biểu từ trang tải chính thức. Cột JDK nói về **JVM chạy broker**, không phải một bảo đảm tự động cho mọi ứng dụng client. Dấu `[11,23)` trong tài liệu Apache có nghĩa là từ Java 11 đến trước Java 23.

| Broker và dòng bản phát hành | JDK chạy broker được trang phát hành công bố | API/namespace chủ đạo ở dòng đó | Client Java tiêu biểu | Tình trạng và lưu ý |
|---|---|---|---|---|
| **Classic 5.16.x** | Java 8 | JMS 1.1, `javax.jms` | `activemq-client` 5.16.x | Dòng cũ, không còn được duy trì; phù hợp để nhận diện hệ thống legacy |
| **Classic 5.17.x** | `[11,23)` | JMS 1.1, `javax.jms` | `activemq-client` 5.17.x | Dòng cũ, không còn được duy trì |
| **Classic 5.18.x** | `[11,23)` | Broker gốc `javax.jms`; client mở rộng một phần JMS 2.0, có client Jakarta chuyển tiếp từ 5.18.1 | `activemq-client` hoặc `activemq-client-jakarta` | Dòng đã ngừng duy trì; hỗ trợ JMS 2.0/3.1 chưa đầy đủ |
| **Classic 5.19.x**; ví dụ **5.19.12** | `[11,23)`; bản 5.19.12 nêu Java 11, 17, 21 | Broker tương thích hệ JMS 1.1/`javax.jms`; client có lựa chọn `javax.jms` và `jakarta.jms` | `activemq-client` hoặc `activemq-client-jakarta` | Dòng còn hoạt động tại thời điểm đối chiếu; lựa chọn hợp lý khi cần giữ Classic 5.x |
| **Classic 6.0–6.2.x** | `[17,23)` | `jakarta.jms`, hỗ trợ Jakarta Messaging 3.1/JMS 2.0 **một phần** | `activemq-client` 6.x | Các dòng này đã ngừng duy trì; không dùng `activemq-client-jakarta` 5.x thay thế |
| **Classic 6.3–6.4.x**; ví dụ **6.4.0** | `[17,26)`; 6.4.0 có Java 17, 21, 25 | `jakarta.jms`, hỗ trợ Jakarta Messaging 3.1/JMS 2.0 **một phần** | `activemq-client` 6.3/6.4 | Dòng còn hoạt động tại thời điểm đối chiếu; cần đọc danh sách tính năng JMS 2.0 đã triển khai |
| **Artemis 2.57.0** | Java **17+** theo công bố bản phát hành | Hai biến thể client: JMS 2.0/`javax.jms` và Jakarta Messaging 3.x/`jakarta.jms` | `artemis-jms-client` hoặc `artemis-jakarta-client` | Artemis dùng giao thức Core cho hai provider này; Maven groupId mới từ 2.57.0 |

**Lưu ý về cách sử dụng bảng:**

- Phạm vi JDK ở bảng trên phản ánh **ma trận được Apache công bố cho dòng Classic** hoặc **yêu cầu tối thiểu Artemis**. Java 17+ của Artemis không có nghĩa mọi bản Java tương lai đều đã được thử nghiệm; nên chọn một bản LTS được dự án xác nhận.
- Tên sản phẩm Artemis và Classic không phải hai số phiên bản của cùng một broker. Không được suy ra “Artemis 2.57” tương đương “Classic 6.4” hoặc có thể thay thế tệp cấu hình broker cho nhau.
- Chỉ lấy thông tin phát hành mới nhất khi chuẩn bị nâng cấp. Bản vá có thể đổi thư viện nền, cấu hình TLS, cách xác thực hoặc khả năng tương thích mà số major không đổi.
- Việc chạy `activemq-client` 5.x trên Java 17 không tự làm cho API trở thành `jakarta.jms`; namespace phụ thuộc vào **artifact** đã chọn.

## 4. Bảng chọn thư viện Java client

| Ứng dụng cần | Maven coordinates mẫu | Namespace ứng dụng | Giao thức thông thường | Ràng buộc quan trọng |
|---|---|---|---|---|
| Classic 5.19 với API cũ | `org.apache.activemq:activemq-client:5.19.12` | `javax.jms` | OpenWire | Hợp với mã JMS cũ; mức JMS 2.0 chỉ một phần |
| Classic 5.19 với mã Jakarta mới | `org.apache.activemq:activemq-client-jakarta:5.19.12` | `jakarta.jms` | OpenWire | **Chỉ client từ xa**; không đặt cùng JVM với `activemq-client` 5.x hoặc embedded broker 5.x dựa trên `javax.jms` |
| Classic 6.4 | `org.apache.activemq:activemq-client:6.4.0` | `jakarta.jms` | OpenWire | Từ Classic 6.x, module `activemq-client-jakarta` chuyển tiếp đã bị loại bỏ |
| Artemis 2.57, JMS 2.0 | `org.apache.artemis:artemis-jms-client:2.57.0` | `javax.jms` | Artemis Core | Dùng provider JMS của Artemis; trỏ tới Artemis acceptor hỗ trợ Core |
| Artemis 2.57, Jakarta Messaging | `org.apache.artemis:artemis-jakarta-client:2.57.0` | `jakarta.jms` | Artemis Core | Phù hợp ứng dụng Jakarta EE/Spring mới |
| Client JMS qua AMQP 1.0 | Chọn provider AMQP JMS tương ứng phiên bản API, chẳng hạn họ Apache Qpid JMS | Tùy bản thư viện: `javax.jms` hoặc `jakarta.jms` | AMQP 1.0 | Phù hợp khi muốn độc lập với provider gốc, nhưng vẫn phải kiểm thử mapping của message/destination |

**Thay đổi Maven dễ gây lỗi khi nâng Artemis:** tài liệu chính thức của **2.57.0** dùng groupId `org.apache.artemis`. Các ví dụ cho các bản Artemis cũ có thể dùng `org.apache.activemq`. Khi nâng cấp, thay cả **groupId** lẫn **version** theo tài liệu của bản thực tế. Package của lớp triển khai, ví dụ `org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory`, **không nhất thiết đổi theo Maven groupId**.

Không đặt nhiều bản của cùng một client provider trong classpath để “tăng tương thích”. Nếu hai module kéo vào các phiên bản khác nhau của cùng lớp API hoặc lớp triển khai, có thể xuất hiện `NoSuchMethodError`, `ClassCastException` hoặc `LinkageError`.

## 5. Bảng **client ↔ broker** theo giao thức thực tế

Ký hiệu: **✓** = có đường kết nối được tài liệu mô tả; **△** = có thể phù hợp nhưng phải xác nhận giao thức, khả năng thương lượng phiên bản và tính năng; **✕** = không hỗ trợ trực tiếp bằng giao thức của client đó. Đây là bảng **khả năng kết nối**, chưa phải chứng nhận toàn bộ ngữ nghĩa JMS.

| Client / giao thức gửi đi | Classic 5.19.x | Classic 6.4.x | Artemis 2.57.0 | Giải thích |
|---|:---:|:---:|:---:|---|
| Classic `activemq-client` 5.x / OpenWire | ✓ | △ | ✓ | Native với Classic 5.x; Artemis nêu hỗ trợ thư viện OpenWire từ Classic 5.12.x trở lên; kiểm thử riêng khi đi qua Classic 6.x |
| Classic `activemq-client-jakarta` 5.18.1+/5.19.x / OpenWire | ✓ | △ | △ | Chỉ dành cho kết nối broker qua mạng; phiên bản ứng dụng là `jakarta.jms` nhưng giao thức vẫn là OpenWire |
| Classic `activemq-client` 6.x / OpenWire | △ | ✓ | △ | Native với Classic 6.x; khi kết nối ngược sang Classic 5.x hoặc sang Artemis cần xác thực và kiểm thử liên thông |
| Artemis `artemis-jms-client` hoặc `artemis-jakarta-client` / Core | ✕ | ✕ | ✓ | Classic không triển khai Artemis Core; đổi `import` không biến Core thành OpenWire |
| Provider AMQP 1.0 / AMQP 1.0 | ✓ | ✓ | ✓ | Cả hai họ broker hỗ trợ AMQP 1.0 khi connector/acceptor phù hợp đã được bật |

Để bảng này đúng trong thực tế, **broker phải mở đúng cổng và bật đúng protocol**:

- Classic thường dùng một `transportConnector` OpenWire, ví dụ `tcp://broker-host:61616`; có thể cấu hình AMQP riêng tại `amqp://broker-host:5672`.
- Artemis có `acceptor` cho Core, OpenWire, AMQP… Một acceptor có thể bật nhiều protocol; ví dụ `tcp://0.0.0.0:61616?protocols=CORE,OPENWIRE,AMQP`, hoặc tách từng acceptor/cổng.
- Số cổng là **ví dụ cấu hình**, không phải một cách tự động để nhận biết protocol. Chỉ việc cả hai đầu cùng dùng cổng 61616 không chứng minh chúng tương thích.

### Các khác biệt cần kiểm thử khi đi qua hai broker

| Hạng mục | Vì sao kết nối thành công vẫn có thể chưa tương thích |
|---|---|
| Queue và topic | Artemis ánh xạ JMS queue/topic lên address với routing type như `ANYCAST`/`MULTICAST`; tên destination và quy tắc auto-create cần khớp cấu hình |
| Durable subscription | Kiểm tra `clientID`, tên subscription, hành vi reconnect và message tồn đọng |
| Acknowledgment và redelivery | `CLIENT_ACKNOWLEDGE`, rollback và redelivery có thể chịu chính sách của provider/broker khác nhau |
| Transaction/XA | Có kết nối chưa chứng minh XA enlistment, commit, rollback hoặc recovery hoạt động đúng |
| DLQ và retry | Thời gian retry, số lần delivery, tên dead-letter queue và chính sách chuyển thư là cấu hình broker, không được chuẩn hóa hoàn toàn bởi JMS |
| Header, selector và message body | Phải xác nhận `JMSCorrelationID`, `JMSXGroupID`, selector, `TextMessage`/`BytesMessage`; qua AMQP cần xem cơ chế chuyển đổi message |
| TLS và đăng nhập | Client đúng protocol vẫn thất bại nếu truststore, cơ chế xác thực hoặc quyền gửi/nhận không tương thích |

Riêng Classic khi dùng AMQP 1.0 có các chiến lược transformer `native`, `raw` và `jms`; nếu mục tiêu là đọc nội dung JMS tương ứng thay vì bọc byte AMQP, hãy xem lựa chọn `jms` trong tài liệu Classic. Đừng kết luận tương thích về payload chỉ từ việc gửi một thông điệp text đơn giản thành công.

## 6. Chọn tổ hợp theo tình huống

### Tình huống A — Ứng dụng Java 11 dùng `javax.jms`, broker Classic 5.19

Giữ API `javax.jms` và dùng `org.apache.activemq:activemq-client:5.19.12` cho kết nối OpenWire. Phương án này tránh việc nâng Jakarta chỉ vì broker đã được nâng bản vá. Nếu mã dùng `JMSContext` của JMS 2.0 thì phải kiểm tra riêng phương thức vì hỗ trợ của Classic 5.19 là **một phần**.

### Tình huống B — Ứng dụng dùng Spring 6/Jakarta, nhưng broker vẫn là Classic 5.19

Với kết nối từ xa, chọn `org.apache.activemq:activemq-client-jakarta:5.19.12` và `import jakarta.jms.*`. Đây là client chuyển tiếp giúp ứng dụng Jakarta trao đổi qua OpenWire với broker Classic 5.x. Không triển khai nó chung JVM với embedded Classic 5.x dựa trên `javax.jms`; mô hình riêng tiến trình là phù hợp.

### Tình huống C — Broker Classic 6.4 và ứng dụng Java 17

Chọn `org.apache.activemq:activemq-client:6.4.0`; mã dùng `jakarta.jms.*`. Không sử dụng tọa độ `activemq-client-jakarta` từ Classic 5.x. Đối chiếu danh sách hỗ trợ JMS 2.0: những thao tác như gửi bất đồng bộ với `CompletionListener`, delivery delay hoặc shared topic consumers không nên coi là hoàn chỉnh chỉ vì API Jakarta 3.1 tồn tại.

### Tình huống D — Artemis 2.57 và ứng dụng Java 17/21

Nếu mã dùng `javax.jms.*`, chọn `org.apache.artemis:artemis-jms-client:2.57.0`. Nếu mã dùng `jakarta.jms.*`, chọn `org.apache.artemis:artemis-jakarta-client:2.57.0`. Cả hai là provider dùng Artemis Core khi nối trực tiếp đến Artemis; không sử dụng chúng để kết nối Classic. Nếu cần liên thông khác sản phẩm, cân nhắc OpenWire hoặc AMQP 1.0 theo bảng giao thức.

## 7. Ví dụ chạy thử Artemis 2.57 với Jakarta Messaging

Giả sử broker Artemis đang chạy ở `localhost:61616`, acceptor bật `CORE`, đã có queue `orders.demo` theo routing type `ANYCAST` (hoặc broker cho phép tự tạo queue) và có tài khoản được phép gửi/nhận. Đoạn Java sau kiểm tra được một tổ hợp **Artemis 2.57 + JDK 17 + `jakarta.jms` + Core**.

**Phần dependency trong `pom.xml`:**

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

**Lớp `ArtemisCompatibilityDemo.java`:**

```java
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public class ArtemisCompatibilityDemo {
    public static void main(String[] args) {
        String username = System.getenv("BROKER_USER");
        String password = System.getenv("BROKER_PASSWORD");
        if (username == null || password == null) {
            throw new IllegalStateException(
                "Cần cấu hình BROKER_USER và BROKER_PASSWORD");
        }

        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory("tcp://localhost:61616");

        try (JMSContext context =
                 factory.createContext(username, password, JMSContext.AUTO_ACKNOWLEDGE)) {
            Queue queue = context.createQueue("orders.demo");

            context.createProducer().send(queue, "order-123");
            String received =
                context.createConsumer(queue).receiveBody(String.class, 5000);

            if (!"order-123".equals(received)) {
                throw new IllegalStateException(
                    "Không nhận lại đúng thông điệp: " + received);
            }
            System.out.println("PASS: Jakarta Messaging qua Artemis Core");
        } finally {
            factory.close();
        }
    }
}
```

Thử nghiệm trên xác thực **kết nối, kiểu API, route đến queue và gửi/nhận cơ bản**. Nó chưa chứng minh độ bền message, redelivery, XA hoặc DLQ. Trong ứng dụng thật, hãy tái sử dụng `ConnectionFactory` và tránh tạo connection/consumer mới cho từng message; ví dụ ở đây chỉ minh họa phép thử nhanh.

Muốn chuyển ví dụ sang biến thể `javax.jms` của Artemis, đổi dependency thành `artemis-jms-client` cùng bản `2.57.0` và thay `import jakarta.jms.*` thành `javax.jms.*`. **Không** dùng cách thay import đơn thuần để chuyển từ Artemis sang Classic: cần thay cả provider factory và giao thức.

## 8. Kiểm chứng ma trận trước khi nâng cấp

### 8.1. Checklist kiểm tra tĩnh

1. Ghi chính xác **broker + patch version**, **client artifact + version**, **JDK broker**, **JDK ứng dụng**, **namespace JMS** và **protocol** vào hồ sơ triển khai.
2. Đối chiếu yêu cầu JVM ở trang phát hành của đúng dòng broker; đối chiếu bytecode và các dependency của **client** với JDK chạy ứng dụng.
3. Kiểm tra classpath bằng `mvn dependency:tree` hoặc công cụ tương đương: phát hiện hai provider/version bị kéo đồng thời, `javax.jms` lẫn `jakarta.jms` không đúng ý đồ, hoặc jar `-all` trộn cùng jar riêng lẻ của Artemis.
4. Kiểm tra acceptor/transport connector, TLS, tài khoản, quyền trên destination, cơ chế tự tạo queue và địa chỉ thực tế.
5. Với Classic 5.18+/6.x, lập danh sách **phương thức JMS 2.0/3.1** đang gọi và tra bảng triển khai tính năng; không suy ra từ tên bản đặc tả.

Để hiểu một lỗi JDK, nhớ các mức class file thường gặp: **52 = Java 8**, **55 = Java 11**, **61 = Java 17**, **65 = Java 21**. Một class build cho Java 17 sẽ không chạy trên JVM 11. Dùng `javap -verbose` với một class trong jar thực tế để kiểm tra `major version` khi cần.

### 8.2. Bộ kiểm thử tích hợp tối thiểu

| Kịch bản chạy thử | Điều kiện PASS cần quan sát |
|---|---|
| Đăng nhập, TLS và tạo connection | Đúng hostname/port/protocol, xác thực thành công; tài khoản không có quyền bị từ chối đúng cách |
| Producer → queue → consumer | Nội dung và các header cần thiết đến đúng destination, message được tiêu thụ |
| Topic với durable subscription | Subscriber ngắt rồi kết nối lại nhận được message tồn đọng đúng chính sách |
| `CLIENT_ACKNOWLEDGE` và `AUTO_ACKNOWLEDGE` | Ack theo chế độ mong đợi; message chưa được xử lý không bị mất |
| Local transaction `commit`/`rollback` | Message được xác nhận hoặc phát lại phù hợp khi rollback |
| Redelivery và DLQ | Sau số lần thất bại cấu hình, message vào đúng DLQ; không lặp vô hạn ngoài dự kiến |
| Tái kết nối/failover | Client khôi phục sau restart broker hoặc mất mạng trong giới hạn đã cấu hình |
| Tính năng JMS 2.0/Jakarta 3.x đang sử dụng | Phương thức hoạt động thực tế; không ném `UnsupportedOperationException` hoặc làm khác ngữ nghĩa dự kiến |

Nếu kiến trúc có nhiều phiên bản client cùng truy cập một broker, hãy chạy **mỗi phiên bản ứng dụng trong một JVM độc lập** và kiểm tra producer phiên bản A → consumer phiên bản B theo cả hai chiều. Đo kiểm cả message text, binary, selector, expiration, priority và trường header mà hệ thống thực sự phụ thuộc.

### 8.3. Ma trận ghi nhận kết quả để dùng trong dự án

| Broker | JDK broker | Artifact client | JDK app | API package | Wire protocol | Tính năng phải kiểm thử | Kết quả |
|---|---|---|---|---|---|---|---|
| Classic 5.19.12 | 17 | `activemq-client:5.19.12` | 11 | `javax.jms` | OpenWire | Queue, ack, rollback | Chưa chạy |
| Classic 5.19.12 | 17 | `activemq-client-jakarta:5.19.12` | 17 | `jakarta.jms` | OpenWire | Queue, topic, DLQ | Chưa chạy |
| Classic 6.4.0 | 21 | `activemq-client:6.4.0` | 17 | `jakarta.jms` | OpenWire | JMSContext, transaction, redelivery | Chưa chạy |
| Artemis 2.57.0 | 17 | `artemis-jakarta-client:2.57.0` | 21 | `jakarta.jms` | Core | Queue, durable topic, failover | Chưa chạy |

Những dòng mẫu trên minh họa **tổ hợp cấu hình cần đánh giá**, không phải tuyên bố đã kiểm thử. Trong dự án thực tế, điền bản vá được khóa trong BOM/lockfile, môi trường test, ngày chạy và kết quả có bằng chứng.

## 9. Xử lý lỗi tương thích thường gặp

| Triệu chứng | Nghi ngờ đầu tiên | Cách xử lý |
|---|---|---|
| `UnsupportedClassVersionError` | Client jar hoặc ứng dụng build cho Java mới hơn JVM đang chạy | Đối chiếu JDK thực tế, `major version` và yêu cầu phát hành; nâng JVM hoặc chọn artifact phù hợp |
| `ClassNotFoundException: jakarta.jms...` hoặc `NoClassDefFoundError` | Thiếu API Jakarta hoặc chọn nhầm provider `javax.jms` | Đồng bộ namespace giữa mã, framework và client dependency |
| `ClassCastException` giữa hai `ConnectionFactory` | Đang trộn `javax.jms` và `jakarta.jms`, hoặc nhiều classloader/provider | Dùng một API family nhất quán trong từng module/classloader |
| `NoSuchMethodError` / `LinkageError` | Trùng phiên bản jar, BOM ép về API/provider không khớp | Xem dependency tree, loại trừ dependency mâu thuẫn |
| Timeout/“protocol mismatch” dù mở được cổng | Core client gửi đến OpenWire-only connector, hoặc ngược lại | Kiểm tra protocol acceptor và URL kết nối, không phỏng đoán theo port |
| `UnsupportedOperationException` ở `JMSProducer` / shared consumer | Đang gọi tính năng JMS 2.0 chưa được Classic triển khai | Tra bảng tính năng theo patch version; đổi API sử dụng hoặc cân nhắc provider khác |
| Message có header/body bất thường qua AMQP | Khác cách ánh xạ message | Kiểm tra AMQP transformer, message type, selector, content type và header |
| Lỗi sau khi nâng Artemis 2.57 | Dependency Maven vẫn dùng groupId cũ; hoặc thay đổi bắt tay Core/xác thực | Chuyển Maven groupId sang `org.apache.artemis` và đọc hướng dẫn upgrade cho Core client |

## 10. Quy tắc kết luận tương thích

Một cặp “broker – client” chỉ nên được đánh dấu **đã xác minh** khi trả lời được đầy đủ:

- **JDK:** Broker và ứng dụng đều khởi chạy bằng phiên bản JDK phù hợp với các jar đang nạp.
- **API:** Code, framework và provider cùng namespace `javax.jms` **hoặc** `jakarta.jms`; không nhầm “JMS 2.0” với “Jakarta 3.x”.
- **Protocol:** Cả hai phía hỗ trợ cùng wire protocol và cấu hình cổng, mã hóa, authentication đã khớp.
- **Behavior:** Những tính năng ứng dụng thật dùng — queue, topic, acknowledgment, transaction, DLQ, failover — đã qua kiểm thử tích hợp.

Đối với hệ thống dùng ActiveMQ Classic và Artemis, bảng phiên bản là **điểm khởi đầu để chọn cấu hình**; kết quả kiểm thử theo giao thức và hành vi message mới là chứng cứ đủ mạnh để chấp nhận nâng cấp sản xuất.

## Tài liệu chính thức để đối chiếu

1. Apache ActiveMQ Classic — [Download và ma trận Java/JMS theo dòng](https://activemq.apache.org/components/classic/download/).
2. Apache ActiveMQ Classic — [Jakarta Messaging 3.1 & JMS 2.0 Support](https://activemq.apache.org/components/classic/documentation/jms2) (bao gồm các chức năng triển khai một phần).
3. Apache ActiveMQ Classic — [AMQP 1.0 và chiến lược ánh xạ JMS](https://activemq.apache.org/components/classic/documentation/amqp).
4. Apache Artemis — [Download, bản 2.57.0 và yêu cầu Java](https://artemis.apache.org/components/artemis/download/).
5. Apache Artemis — [The Client Classpath: hai client Maven JMS/Jakarta](https://artemis.apache.org/components/artemis/documentation/latest/client-classpath.html).
6. Apache Artemis — [Protocols and Interoperability](https://artemis.apache.org/components/artemis/documentation/latest/protocols-interoperability.html), gồm OpenWire 5.12+, AMQP, Core và cấu hình acceptor.
7. Apache Artemis — [Version History](https://artemis.apache.org/components/artemis/documentation/latest/versions.html), gồm thay đổi groupId và lưu ý khi nâng lên 2.57.0.
