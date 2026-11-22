# Phân biệt xác thực kết nối và phân quyền destination

> **Chương:** Bảo mật  
> **Học phần:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Apache ActiveMQ Classic và Artemis trong giao tiếp bất đồng bộ qua queue, topic và JMS; producer/consumer Java, acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành broker đáng tin cậy.  
> **Phạm vi:** Phân biệt rõ **authentication** (ai được kết nối) và **authorization** (người đã kết nối được làm gì trên destination cụ thể). Ví dụ chính dùng **Apache ActiveMQ Artemis 2.40.0**, **Jakarta JMS 3.1** và **Java 17**. ActiveMQ Classic 5.x được đối chiếu riêng về ACL, client và giao thức.

## 1. Hai ranh giới bảo mật tách biệt

Một service `shipping-worker` đăng nhập broker bằng username/password hợp lệ. Lệnh tạo `JMSContext` thành công, thậm chí client có thể lấy JMS metadata. Nhưng ngay sau đó lệnh gửi tới queue `shipping.commands` thất bại vì tài khoản chỉ có quyền **consume**, không có quyền **send**.

Điều này **không mâu thuẫn**:

- **Xác thực kết nối (authentication):** broker xác định danh tính, ví dụ username/password trong JAAS properties/LDAP hoặc principal từ cơ chế xác thực phù hợp. Kết quả: client được công nhận là **ai**.
- **Phân quyền (authorization):** broker đối chiếu danh tính và **roles/principals** với quyền trên **address, queue, destination hoặc hoạt động quản trị**. Kết quả: danh tính đó được phép **thực hiện thao tác nào, ở đâu**.
- **TLS:** bảo vệ kênh truyền và xác thực danh tính TLS của peer theo cấu hình. TLS **không đồng nghĩa** tài khoản đã được cấp quyền gửi/nhận JMS. Ngay cả mTLS cũng cần ánh xạ danh tính chứng chỉ sang principal/role nếu muốn dùng nó cho authorization.

~~~mermaid
sequenceDiagram
    participant C as JMS client
    participant T as Transport / TLS
    participant A as Artemis authentication
    participant Z as Artemis authorization
    participant Q as Queue shipping.commands

    C->>T: TCP + TLS handshake (nếu bật)
    T-->>C: Kênh truyền được thiết lập
    C->>A: Username + password / cơ chế broker auth
    A-->>C: Xác thực thành công, principal/roles
    C->>Z: SEND tới shipping.commands
    Z-->>C: DENIED nếu thiếu role send
    Note over C,Q: Đăng nhập thành công không cấp quyền SEND
    C->>Z: CONSUME shipping.commands
    Z->>Q: Kiểm tra role consume
    Q-->>C: Delivery nếu được phép
~~~

### 1.1. Ma trận hành vi mong muốn

Hệ thống ví dụ có ba loại người dùng dịch vụ:

| Danh tính | Vai trò | Đăng nhập | `send` shipping.commands | `consume` shipping.commands | `browse` |
|---|---|---:|---:|---:|---:|
| `app-writer` | `shipping-producer` | Được | Được | **Từ chối** | Từ chối |
| `app-reader` | `shipping-consumer` | Được | **Từ chối** | Được | Từ chối |
| `app-auditor` | `shipping-auditor` | Được | Từ chối | Từ chối | Được |
| `unknown-user` | Không có danh tính hợp lệ | **Từ chối** | Không tới bước kiểm tra | Không tới bước kiểm tra | Không tới bước kiểm tra |

Giữ ba kết quả thử nghiệm thật tách bạch:

1. **Sai mật khẩu:** thất bại ở authentication, chưa có ngữ cảnh role hợp lệ.
2. **Mật khẩu đúng, thiếu quyền:** authentication qua, authorization từ chối thao tác trên destination.
3. **Đúng role nhưng sai routing/queue:** authentication và authorization có thể qua nhưng message không được route như kỳ vọng; đây là **vấn đề destination/routing**, không nhất thiết lỗi security.

**Bảo mật không kết thúc ở câu hỏi “kết nối có thành công không?”.** Một smoke test chỉ gọi `createConnection()` hoặc `createContext()` có thể bỏ sót lỗ hổng hoặc thiếu quyền khi ứng dụng bắt đầu gửi/nhận thực sự.

## 2. Chuỗi kiểm tra từ socket đến destination

~~~text
TCP endpoint đúng?
    |
    +-- Không -> DNS/port/firewall/connection refused
    |
    v
TLS đúng? (nếu acceptor yêu cầu)
    |
    +-- Không -> handshake, trust chain, certificate/SAN
    |
    v
Broker hỗ trợ đúng wire protocol?
    |
    +-- Không -> Core/OpenWire/AMQP mismatch
    |
    v
Authentication: user/principal được công nhận?
    |
    +-- Không -> auth failure; không có session hợp lệ
    |
    v
Destination operation:
  send / consume / browse / createQueue / deleteQueue / manage...
    |
    +-- Role/ACL thiếu -> authorization denied
    |
    v
Broker routing, queue, selector, TTL, redelivery...
    |
    v
Nghiệp vụ consumer và ACK/transaction
~~~

### 2.1. Danh tính kết nối không tự cho quyền quản trị

Trong thực tế, broker có các nhóm đặc quyền tách biệt:

- Kết nối được chấp nhận.
- Gửi message vào **address**.
- Tiêu thụ message ở queue.
- Browse message không làm mất message.
- Tạo/xóa address hoặc queue (kể cả durable và non-durable).
- Quản trị broker, xem/chỉnh cấu hình/metrics qua kênh quản lý.

Một tài khoản chỉ cần nhận hàng từ queue không nên có quyền tạo/xóa destination hoặc thực hiện thao tác quản trị. **Least privilege** còn có lợi cho reliability: tránh một service lỗi có khả năng xóa queue hoặc tạo hàng loạt address.

### 2.2. Authentication xảy ra ở connection, authorization xảy ra khi hành động

Tùy JMS provider, một số kết nối/consumer có thể được khởi tạo **lazy**; lỗi có thể xuất hiện khi `createContext`, `createProducer`, `send`, `createConsumer`, `receive` hoặc khi container listener khởi động.

Do đó, không ràng buộc chẩn đoán bằng “exception ném ở dòng thứ N”. Phân loại bằng **loại thao tác, thông báo lỗi broker/client và security audit**:

- Sai credential/JAAS realm → authentication.
- User hợp lệ nhưng thiếu `send`/`consume`/`browse` → authorization.
- Không có destination hoặc policy auto-create chặn → destination provisioning; có thể liên quan quyền `createAddress`/`createDurableQueue`.
- Kết nối sau TLS lỗi → transport/identity; chưa chắc broker đã tới bước kiểm tra username.

Lưu ý: producer và consumer của hai service có thể **dùng cùng broker URL** nhưng phải dùng **hai danh tính/role khác nhau**.

## 3. Định danh, role và quyền trong Artemis

Artemis có thể xác thực bằng các cấu hình security manager/JAAS tương thích, chẳng hạn **properties-based login**, LDAP hoặc cơ chế tích hợp khác. Ví dụ dễ quan sát dùng **properties-based JAAS**.

### 3.1. Chuỗi mapping chuẩn

~~~text
JMS username = app-writer
         |
         v
JAAS / SecurityManager kiểm tra mật khẩu
         |
         v
Principal = app-writer
         |
         v
Role mapping: app-writer thuộc shipping-producer
         |
         v
broker.xml:
security-setting match="shipping.commands"
  send -> shipping-producer
  consume -> shipping-consumer
         |
         v
send OK, consume DENIED
~~~

Không nên nhầm:

- **Username**: một danh tính đăng nhập, ví dụ `app-writer`.
- **Role**: tập quyền logic, ví dụ `shipping-producer`.
- **Permission**: hành động kiểm tra bởi broker, ví dụ `send`.
- **Destination/address match**: nơi permission có hiệu lực, ví dụ `shipping.commands`.

Một user có thể mang nhiều role, và một role có thể được cấp cho nhiều user. Cấu hình role **không** mặc nhiên cấp quyền gì nếu `security-settings` của broker không ánh xạ role đó vào permission tương ứng.

### 3.2. Ví dụ ánh xạ role trong file properties

Một Artemis instance dùng `PropertiesLoginModule` có thể có những file như:

~~~text
etc/
  login.config
  artemis-users.properties
  artemis-roles.properties
~~~

Mẫu ánh xạ **role → danh sách username** trong `artemis-roles.properties`:

~~~properties
shipping-producer=app-writer
shipping-consumer=app-reader
shipping-auditor=app-auditor
shipping-admin=broker-operator
~~~

Các password của user nằm ở `artemis-users.properties` theo định dạng/hash phù hợp **version và login module**. **Không** chép mật khẩu thật vào bài học hoặc Git. Dùng công cụ quản lý user của instance, hoặc hệ identity/secret quản lý, để tạo/cập nhật credential; kiểm tra trợ giúp CLI của bản Artemis đang chạy và quy trình reload/restart security configuration khi thay đổi.

Ví dụ **mô tả vị trí** trong file login config, không phải thay thế file hiện có:

~~~text
activemq {
    org.apache.activemq.artemis.spi.core.security.jaas.PropertiesLoginModule required
        debug=false
        org.apache.activemq.jaas.properties.user="artemis-users.properties"
        org.apache.activemq.jaas.properties.role="artemis-roles.properties";
};
~~~

Broker phải thực sự dùng security domain/login module tương ứng; đường dẫn file được resolve theo cấu hình instance và JVM. Nếu broker đã dùng LDAP, certificate authentication hoặc plugin, **không tự thêm properties login module** rồi mặc định nó thay thế policy hiện hữu.

**Tạo user và gán role là bước riêng với ACL.** Bạn có thể gán `shipping-producer` cho `app-writer` mà vẫn bị từ chối gửi nếu thiếu `send` tại security-setting đích.

### 3.3. Đừng nhầm password broker và thông tin TLS

| Thành phần | Dùng vào việc gì? |
|---|---|
| `app-writer` / broker password | Broker authentication |
| `shipping-producer` | Role để broker authorize thao tác |
| TLS truststore ở client | Kiểm tra certificate và danh tính broker |
| TLS keystore ở broker | Private key và certificate server |
| TLS client certificate (khi mTLS) | Bằng chứng danh tính TLS của client |
| Mapping certificate principal → role | Cần nếu cơ chế xác thực broker dựa trên cert và muốn cấp quyền JMS |

**mTLS không có nghĩa “tự được send/consume”.** Broker vẫn phải biết principal nào được phép làm gì. Trong mô hình username/password + server-auth TLS, TLS và broker credential là hai lớp bảo vệ độc lập.

## 4. Artemis ACL theo destination: cấu hình tối thiểu quyền

Giả sử một queue công việc **đã được tạo sẵn**. Mảnh XML bên trong phần `<addresses>` hiện hữu của `broker.xml`:

~~~xml
<address name="shipping.commands">
    <anycast>
        <queue name="shipping.commands" durable="true"/>
    </anycast>
</address>
~~~

Trong Artemis, address là điểm routing và queue là nơi giữ message/delivery. JMS queue `shipping.commands` ở ví dụ dùng address và queue cùng tên, routing **ANYCAST**. Không tự thêm trùng vào broker.xml nếu destination đã tồn tại.

### 4.1. Security-setting chính xác

Bên trong phần `<security-settings>` hiện hữu:

~~~xml
<security-setting match="shipping.commands">
    <permission type="send" roles="shipping-producer"/>
    <permission type="consume" roles="shipping-consumer"/>
    <permission type="browse" roles="shipping-auditor"/>

    <!-- Cấp riêng cho role quản trị provisioning. -->
    <permission type="createAddress" roles="shipping-admin"/>
    <permission type="deleteAddress" roles="shipping-admin"/>
    <permission type="createDurableQueue" roles="shipping-admin"/>
    <permission type="deleteDurableQueue" roles="shipping-admin"/>
    <permission type="createNonDurableQueue" roles="shipping-admin"/>
    <permission type="deleteNonDurableQueue" roles="shipping-admin"/>
</security-setting>
~~~

Các thao tác được phân tách như sau:

| Permission Artemis | Ý nghĩa trong bài |
|---|---|
| `send` | Cho phép producer gửi tới address phù hợp |
| `consume` | Cho phép consumer tiêu thụ message ở queue phù hợp |
| `browse` | Cho phép duyệt message không tiêu thụ/ACK theo API browse |
| `createAddress` / `deleteAddress` | Cho phép tạo/xóa address; không nên cấp cho worker thường |
| `createDurableQueue` / `deleteDurableQueue` | Tạo/xóa durable queue |
| `createNonDurableQueue` / `deleteNonDurableQueue` | Tạo/xóa non-durable queue, có thể liên quan reply/temp-queue |
| `manage` | Quyền thao tác quản lý broker qua cơ chế management; **không** cấp cho producer/consumer chỉ cần gửi/nhận |

**Tính chất quan trọng:** deny trong mẫu được biểu diễn bằng việc **không cấp** permission cho role tương ứng. Không suy từ mẫu rằng broker production đã có default-deny hoàn chỉnh: phải rà **mọi security-setting trùng/lân cận, wildcard, security-enabled, role mapping và management policy** đang có.

Nếu cấu hình hiện hữu có `match="#"` hoặc các rule wildcard, cần xác minh **rule thực sự khớp** `shipping.commands`. Chỉ xét một đoạn XML cục bộ có thể bỏ sót một wildcard permissive ở nơi khác hoặc một permission bị ghi đè do matching rules.

### 4.2. Không để auto-create làm lệch phép thử

Một producer có `send` không nhất thiết được tự tạo address hoặc queue mới. Nếu message gửi tới destination chưa tồn tại, broker có thể:

- Từ chối do policy provisioning/authorization.
- Tự tạo address/queue nếu bật auto-create và tài khoản có quyền thích hợp.
- Không route message tới queue mong muốn theo policy/address settings; kết quả cần kiểm tra broker thực tế.

Để thử đúng **send vs consume**, hãy tạo sẵn queue và trong bài lab có thể tắt auto-create tại address:

~~~xml
<!-- Bên trong <address-settings> đang có, hợp nhất rule trùng match. -->
<address-setting match="shipping.commands">
    <auto-create-addresses>false</auto-create-addresses>
    <auto-create-queues>false</auto-create-queues>
</address-setting>
~~~

Nếu đã có address-setting về redelivery, DLQ, paging hoặc expiry cho `shipping.commands`, **hợp nhất** các trường thay vì tạo nhiều rule cùng `match`. Không tắt auto-create trên broker production chỉ để làm lab.

### 4.3. Trường hợp queue browser và temporary destination

- `QueueBrowser` cần quyền browse phù hợp; đó không mặc nhiên là quyền consume và không ACK message.
- Một ứng dụng JMS request–reply tạo temporary queue có thể cần quyền **tạo/xóa non-durable queue**, ngoài quyền consume/send thường dùng. Chỉ cấp quyền cần thiết với scope/quy trình phù hợp.
- Durable topic subscription có thể cần quyền tạo durable queue và consume tùy topology; việc tạo subscription không chỉ là “đăng nhập”.
- Tài khoản có quyền `send` vào `shipping.commands` không mặc nhiên có quyền `send` vào mọi address khác.

**Quyền gửi/nhận và quyền tạo/xóa destination là hai câu hỏi khác nhau.** Rất nhiều lỗi “consumer tạo được connection nhưng không subscribe được” xuất phát từ quyền tạo queue/subscription hoặc ACL đích, không phải mật khẩu.

## 5. Phân tích tình huống cụ thể

### 5.1. User đăng nhập được nhưng gửi bị từ chối

~~~text
createContext(app-reader, correct-password) -> OK
send(shipping.commands)                     -> authorization denied
~~~

Broker xác thực `app-reader` hợp lệ, lấy role `shipping-consumer`, nhưng security-setting cho `send` chỉ gồm `shipping-producer`. **Sửa đúng:** dùng account producer hoặc gán role theo quyết định quản trị bảo mật; **không** thay mật khẩu ngẫu nhiên, không tắt security và không cấp quyền `#` toàn hệ thống.

### 5.2. Producer gửi được nhưng consumer bị từ chối

~~~text
createContext(app-writer, correct-password) -> OK
send(shipping.commands)                     -> OK
createConsumer(shipping.commands)            -> authorization denied
~~~

`app-writer` có role send nhưng không consume. Tách role như vậy ngăn producer đọc nội dung message hoặc nhận nhầm công việc.

### 5.3. User có browse nhưng không consume

`app-auditor` được cấp `browse` cho `shipping.commands`. Nhân viên giám sát có thể quan sát message qua **broker/API browse** phù hợp mà không được tự tạo consumer thường để lấy/ACK message. Tuy nhiên quyền xem **web console/Jolokia/management endpoint** còn có chính sách quản trị riêng; đừng coi `browse` của destination là quyền đăng nhập toàn console.

### 5.4. TLS thành công nhưng user sai mật khẩu

TLS server-auth xác minh broker, không cấp username. Sau handshake, user sai mật khẩu vẫn bị authentication từ chối. Nếu dùng mTLS, client certificate cũng phải đi qua cơ chế mapping/role nếu broker dùng certificate principal để authorize.

### 5.5. Kết nối OK, gửi đúng role nhưng sai queue

Nếu `shipping.commands` tồn tại nhưng client dùng `shipping.command`, broker có thể báo destination không tồn tại, auto-create hoặc xử lý no-route tùy cấu hình. Không gán mọi trường hợp “không thấy message” cho ACL; kiểm tra **address, routing type, destination name và consumer selector**.

## 6. Lab Java: cùng URL, đổi credential là đổi quyền

Bài lab dùng **Artemis 2.40.0**, **JDK 17**, **Jakarta JMS 3.1**, queue `shipping.commands`. Điều kiện: broker đã cấu hình các user/role và security-setting như trên; client được kết nối bằng native Core transport tại `tcp://127.0.0.1:61616`.

### 6.1. Maven

Cấu trúc:

~~~text
jms-security-boundary/
├── pom.xml
└── src/main/java/lab/SecurityBoundaryLab.java
~~~

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lab</groupId>
    <artifactId>jms-security-boundary</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.40.0</version>
        </dependency>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
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

### 6.2. Chương trình thực hành bốn thao tác

File `src/main/java/lab/SecurityBoundaryLab.java`:

~~~java
package lab;

import java.util.Enumeration;
import java.util.UUID;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSRuntimeException;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.QueueBrowser;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class SecurityBoundaryLab {

    private static final String QUEUE = "shipping.commands";

    private SecurityBoundaryLab() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Dùng: auth | send | consume | browse");
        }

        String url = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = requiredEnv("BROKER_USER");
        String password = requiredEnv("BROKER_PASSWORD");

        ConnectionFactory factory = new ActiveMQConnectionFactory(url);

        try (JMSContext context = factory.createContext(
                user, password, JMSContext.AUTO_ACKNOWLEDGE)) {

            switch (args[0]) {
                case "auth" -> {
                    // Lấy metadata để quan sát hoạt động kết nối.
                    // Không kiểm tra quyền trên queue tại đây.
                    System.out.println("AUTH_OK user=" + user
                            + " jmsVersion="
                            + context.getMetaData().getJMSVersion());
                }

                case "send" -> {
                    Queue destination = context.createQueue(QUEUE);
                    TextMessage message = context.createTextMessage(
                            "ship-order-1001");
                    message.setStringProperty("eventId",
                            UUID.randomUUID().toString());

                    context.createProducer()
                            .setDeliveryMode(DeliveryMode.PERSISTENT)
                            .send(destination, message);

                    System.out.println("SEND_OK queue=" + QUEUE
                            + " user=" + user);
                }

                case "consume" -> {
                    JMSConsumer consumer = context.createConsumer(
                            context.createQueue(QUEUE));

                    Message received = consumer.receive(3000);
                    if (received == null) {
                        System.out.println("CONSUME_ALLOWED_NO_MESSAGE");
                    } else {
                        System.out.println("CONSUME_OK messageId="
                                + received.getJMSMessageID());
                        // AUTO_ACKNOWLEDGE: delivery được ACK
                        // theo JMS provider semantics.
                    }
                }

                case "browse" -> {
                    QueueBrowser browser = context.createBrowser(
                            context.createQueue(QUEUE));
                    try {
                        Enumeration<?> messages =
                                browser.getEnumeration();
                        int count = 0;
                        while (messages.hasMoreElements()) {
                            messages.nextElement();
                            count++;
                        }
                        System.out.println("BROWSE_OK sampled=" + count);
                    } finally {
                        browser.close();
                    }
                }

                default -> throw new IllegalArgumentException(
                        "Mode không hợp lệ: " + args[0]);
            }
        } catch (JMSRuntimeException failure) {
            // Cụ thể hóa lỗi bằng audit từ broker; provider có thể
            // khác nhau về subtype và thời điểm ném exception.
            System.err.println("JMS_OPERATION_FAILED mode=" + args[0]
                    + " user=" + user
                    + " reason=" + failure.getClass().getSimpleName());
            throw failure;
        }
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Thiếu biến " + key);
        }
        return value;
    }
}
~~~

**Tính chất của ví dụ:**

- `auth` kiểm tra khả năng thiết lập phiên/giao tiếp với provider, **không chứng minh quyền send/consume**.
- `send` thực hiện thao tác publish thật; broker mới có cơ hội kiểm tra quyền `send` trên address.
- `consume` tạo consumer thật; quyền consume có thể được kiểm tra khi tạo hoặc khi nhận, tùy client/provider.
- `browse` dùng `QueueBrowser` để duyệt mà không ACK message; với snapshot/queue biến động, số đếm browse không phải một phép đo atomic queue depth.
- Mode `consume` dùng `AUTO_ACKNOWLEDGE` và **có thể lấy/ACK message thật**. Chỉ chạy trên queue lab có chủ đích, không phải queue production.
- Code chỉ chứng minh ranh giới **broker access control**, không có business DB. `SEND_OK` không đồng nghĩa shipping worker đã hoàn tất vận đơn.
- Không in password hoặc payload nhạy cảm. Ở production nên phân tích lỗi cùng broker audit và correlation ID, không chỉ dựa vào class exception.

### 6.3. Chạy kiểm thử dương/âm

Trong PowerShell, dùng broker lab đã có ba user:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61616"
mvn -q -DskipTests package
~~~

**Kịch bản A — user chỉ có quyền gửi:**

~~~powershell
$env:BROKER_USER = "app-writer"
$env:BROKER_PASSWORD = "MAT_KHAU_LAB_WRITER"

mvn -q exec:java "-Dexec.mainClass=lab.SecurityBoundaryLab" "-Dexec.args=auth"
mvn -q exec:java "-Dexec.mainClass=lab.SecurityBoundaryLab" "-Dexec.args=send"
mvn -q exec:java "-Dexec.mainClass=lab.SecurityBoundaryLab" "-Dexec.args=consume"
~~~

Kỳ vọng:

~~~text
AUTH_OK user=app-writer jmsVersion=...
SEND_OK queue=shipping.commands user=app-writer
JMS_OPERATION_FAILED mode=consume user=app-writer reason=...
~~~

Lệnh consume phải bị từ chối khi broker thực sự áp dụng ACL như ví dụ. Loại exception chính xác có thể khác; **không** hardcode test chỉ chấp nhận một subtype nhất định.

**Kịch bản B — user chỉ có quyền tiêu thụ:**

~~~powershell
$env:BROKER_USER = "app-reader"
$env:BROKER_PASSWORD = "MAT_KHAU_LAB_READER"

mvn -q exec:java "-Dexec.mainClass=lab.SecurityBoundaryLab" "-Dexec.args=auth"
mvn -q exec:java "-Dexec.mainClass=lab.SecurityBoundaryLab" "-Dexec.args=consume"
mvn -q exec:java "-Dexec.mainClass=lab.SecurityBoundaryLab" "-Dexec.args=send"
~~~

Kỳ vọng:

~~~text
AUTH_OK user=app-reader jmsVersion=...
CONSUME_OK messageId=...
JMS_OPERATION_FAILED mode=send user=app-reader reason=...
~~~

Nếu message đã bị consumer khác lấy, `CONSUME_ALLOWED_NO_MESSAGE` cũng có thể là kết quả hợp lệ của kiểm thử **quyền consume**. Muốn test nhận message cụ thể, phải đảm bảo queue lab có đúng dữ liệu đã seed và không có consumer cạnh tranh.

**Kịch bản C — user auditor chỉ được browse:**

~~~powershell
$env:BROKER_USER = "app-auditor"
$env:BROKER_PASSWORD = "MAT_KHAU_LAB_AUDITOR"

mvn -q exec:java "-Dexec.mainClass=lab.SecurityBoundaryLab" "-Dexec.args=browse"
mvn -q exec:java "-Dexec.mainClass=lab.SecurityBoundaryLab" "-Dexec.args=consume"
~~~

Kỳ vọng browse thành công (số sampled có thể 0 nếu queue rỗng), còn consume bị từ chối.

**Kịch bản D — credential sai:**

~~~powershell
$env:BROKER_USER = "app-writer"
$env:BROKER_PASSWORD = "sai-mat-khau"

mvn -q exec:java "-Dexec.mainClass=lab.SecurityBoundaryLab" "-Dexec.args=auth"
~~~

Kỳ vọng bị từ chối ở broker authentication, không thể suy ra lỗi thiếu `send` hoặc `consume`. Việc dùng placeholder password trên command example chỉ phục vụ lab; mật khẩu thật không được đưa vào tài liệu, Git hoặc log.

### 6.4. Ma trận nghiệm thu độc lập

| Case | User hợp lệ? | Quyền cần kiểm tra | Kết quả mong đợi |
|---|---:|---|---|
| A1: writer auth | Có | Chưa kiểm tra destination | PASS |
| A2: writer send | Có | `send` | PASS |
| A3: writer consume | Có | `consume` | **DENIED** |
| B1: reader consume | Có | `consume` | PASS (có thể không có message) |
| B2: reader send | Có | `send` | **DENIED** |
| C1: auditor browse | Có | `browse` | PASS |
| C2: auditor consume | Có | `consume` | **DENIED** |
| D1: wrong password | Không | Authentication | **DENIED** trước destination action |
| E1: right role, wrong address | Có | Routing/ACL trên address khác | Không suy nguyên nhân trước khi xem security + destination |

Lặp lại sau mọi thay đổi security policy hoặc client version. **Không chỉ test case thành công:** phép thử user đã xác thực nhưng bị từ chối là bằng chứng role separation hoạt động.

## 7. Spring Boot: credential đúng vẫn có thể thiếu quyền listener

Nếu service dùng Spring Boot 3.x và Artemis starter, một profile tối thiểu có thể là:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: "${ARTEMIS_BROKER_URL}"
    user: "${ARTEMIS_USER}"
    password: "${ARTEMIS_PASSWORD}"

app:
  messaging:
    queue: shipping.commands
~~~

Cấu hình qua **environment/secret provider**:

~~~text
SPRING_PROFILES_ACTIVE=prod
ARTEMIS_BROKER_URL=tcp://mq.internal.example:61617?sslEnabled=true;...
ARTEMIS_USER=app-reader
ARTEMIS_PASSWORD=<injected-secret>
~~~

Không hardcode password và không in URL đã resolve nếu chứa truststore password. Cần kiểm tra TLS truststore/hostname riêng khỏi broker credential.

Listener ví dụ:

~~~java
package lab.shipping;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class ShippingListener {
    @JmsListener(destination = "${app.messaging.queue}")
    public void process(String body) {
        // Demo. Production: DB transaction + idempotent handler.
        System.out.println("SHIPPING_REQUEST_RECEIVED");
    }
}
~~~

Nếu app dùng `app-reader`, listener có thể subscribe/consume nhưng `JmsTemplate.convertAndSend("shipping.commands", ...)` từ **cùng ConnectionFactory/user** sẽ bị từ chối vì thiếu `send`. Đây là đúng thiết kế security, không phải bug Spring.

**Một ConnectionFactory dùng chung credential không tự tách vai trò producer/consumer.** Nếu một service thực sự có cả hai trách nhiệm, cần quyết định cấp đủ quyền trên đúng destination hoặc tổ chức **hai ConnectionFactory với credential riêng**, được Spring wiring rõ ràng. Không tăng quyền toàn cục cho một user chỉ để một method tiện sử dụng.

### 7.1. Một listener startup failure chưa chắc là sai password

Khi `@JmsListener` khởi động, container cần tạo connection, session và consumer. Lỗi có thể đến từ:

- User sai/secret chưa nạp.
- Acceptor/TLS sai, protocol không tương thích.
- User được xác thực nhưng thiếu `consume`.
- Destination chưa được provision, cần `createAddress` hoặc `createDurableQueue` theo chính sách.
- Queue/topic routing mismatch.
- ACL trên address đúng nhưng role mapping chưa reload.
- Một listener container khác trong ứng dụng dùng sai ConnectionFactory.

Nên log đủ **destination, listener ID, profile, username không nhạy cảm, error category**; không log password. Tách signal authentication failures và authorization denials trên broker.

## 8. TLS, authentication và authorization không thể thay nhau

### 8.1. Mảnh cấu hình TLS của Artemis acceptor

Ví dụ trong phần `<acceptors>` hiện hữu của broker.xml, chỉ dùng trên broker lab và thay secret an toàn:

~~~xml
<acceptor name="core-tls">
    tcp://0.0.0.0:61617?protocols=CORE;sslEnabled=true;keyStorePath=/run/secrets/broker.p12;keyStorePassword=REPLACE_ME;keyStoreType=PKCS12;needClientAuth=false
</acceptor>
~~~

Đây là **server-authenticated TLS**, chưa phải mTLS vì `needClientAuth=false`. Khi bật mTLS, broker phải validate client cert và có cơ chế identity/roles nếu dùng cert-based authentication. Cấu hình listener TLS **không cấp** quyền `send`, `consume` hay `browse`.

Với client Artemis, transport URI có thể bật:

~~~text
tcp://mq.internal.example:61617?sslEnabled=true;trustStorePath=/run/secrets/ca-trust.p12;trustStorePassword=REPLACE_ME;trustStoreType=PKCS12;verifyHost=true
~~~

Chứng chỉ server cần SAN phù hợp `mq.internal.example`. Không bật `trustAll=true` hoặc tắt `verifyHost` để né lỗi production. Không đưa password thật vào URI được in log hoặc source code.

### 8.2. Từng lỗi chứng minh điều gì?

| Lỗi | Kết luận gần đúng | Chưa thể kết luận |
|---|---|---|
| Socket timeout/refused | Network/endpoint không đạt | User có quyền gì |
| SSL handshake/trust failure | Client không thiết lập được kênh TLS tin cậy | Broker có chấp nhận username hay không |
| Authentication failure | Danh tính không được broker công nhận | Quyền send/consume của một user hợp lệ khác |
| Authorization failure ở send | User đã có ngữ cảnh bảo mật nhưng thiếu phép gửi tại đích | Consumer khác có thể nhận hay không |
| Authorization failure ở consume | User thiếu quyền nhận hoặc cấu hình đích liên quan | Producer send có thành công không |
| No-route/no destination | Routing/provisioning cần điều tra | Password chắc chắn sai |

Có thể có nhiều lỗi đồng thời: ví dụ staging dùng DNS sai **và** password sai, nhưng bạn chỉ thấy lỗi TCP trước. Khi sửa lớp thấp hơn, lỗi auth mới lộ ra. Vì vậy test tuần tự từ transport tới permission.

## 9. ActiveMQ Classic: cùng nguyên lý, khác tên quyền và cấu hình

**ActiveMQ Classic 5.x** có xác thực và phân quyền riêng, thường qua **authentication plugin/JAAS** và **authorization plugin** với ACL `read`, `write`, `admin`. Đây **không** phải XML `security-setting` kiểu Artemis.

Mảnh cấu hình XBean minh họa bên trong `<broker>` của Classic `activemq.xml`:

~~~xml
<plugins>
    <!-- Lab only: không lưu plaintext password trong production. -->
    <simpleAuthenticationPlugin>
        <users>
            <authenticationUser username="app-writer"
                                password="LAB_ONLY_REPLACE"
                                groups="shipping-producer"/>
            <authenticationUser username="app-reader"
                                password="LAB_ONLY_REPLACE"
                                groups="shipping-consumer"/>
        </users>
    </simpleAuthenticationPlugin>

    <authorizationPlugin>
        <map>
            <authorizationMap>
                <authorizationEntries>
                    <authorizationEntry queue="shipping.commands"
                                        read="shipping-consumer"
                                        write="shipping-producer"
                                        admin="shipping-admin"/>
                </authorizationEntries>
            </authorizationMap>
        </map>
    </authorizationPlugin>
</plugins>
~~~

Đoạn này **chỉ minh họa cú pháp phân vai**, không phải file broker đầy đủ hoặc policy production an toàn. Trên Classic thực tế cần cấu hình quyền cho advisory destinations, temporary destinations và các destination khác theo nhu cầu, đồng thời kiểm tra default/wildcard ACL và cơ chế xác thực bảo mật thích hợp.

| Hoạt động | Artemis | Classic |
|---|---|---|
| Producer phát message | `send` | `write` |
| Consumer nhận message | `consume` | `read` |
| Tạo/quản trị destination | Quyền riêng như `createDurableQueue`, `createAddress`, `delete...` | `admin` theo ACL destination và cơ chế quản lý |
| Browser message | `browse` được phân tách | Thường gắn với quyền `read` theo Classic authorization model; phải kiểm tra cơ chế client/browser |
| Identity/role source | JAAS/security manager tùy cấu hình | Authentication plugin/JAAS/LDAP tùy cấu hình |

**Không bê XML Artemis qua Classic hoặc đổi tên permission một cách máy móc.** Classic 5.x client truyền thống dùng `javax.jms`; ví dụ Artemis trong bài dùng `jakarta.jms`. Với Spring Boot 3, phải chọn client Classic tương thích Jakarta hoặc một cấu hình phù hợp thực tế, không trộn namespace.

Một bẫy Classic: `read` cho queue có thể đồng nghĩa quyền **consume**, không tạo được user “chỉ được xem message nhưng không được lấy message” chỉ bằng cách suy từ tên permission. Nếu cần read-only audit, thiết kế kênh quản trị/monitoring có quyền riêng phù hợp và kiểm chứng hành vi.

## 10. Tránh mở rộng quyền bằng cách sửa mọi lỗi thành admin

Khi gặp `not authorized`, rất dễ sửa nhanh thành:

~~~xml
<!-- KHÔNG dùng làm biện pháp production để hết lỗi: -->
<permission type="send" roles="all"/>
<permission type="consume" roles="all"/>
<permission type="createAddress" roles="all"/>
<permission type="deleteAddress" roles="all"/>
~~~

Nếu role `all` được cấp rộng, cấu hình này mở nhiều thao tác cho nhiều client, che mất lỗi gốc và gia tăng blast radius. **Lỗi authorization cần được sửa bằng một permission tối thiểu tại đúng destination cho đúng role**.

### 10.1. Quy tắc rà quyền tối thiểu

1. Service này **chỉ gửi** hay còn nhận?
2. Nó làm việc trên **address/queue cụ thể nào**?
3. Destination đã provision sẵn hay ứng dụng cần tự tạo?
4. Có cần browse, temporary queue, durable subscription không?
5. Có cần thao tác quản trị broker không? Nếu không, không cấp `manage`.
6. User thuộc role nào tại runtime? Có security config reload thành công không?
7. Broker đang dùng ACL nào là **effective rule** khi wildcard/overlap?
8. Có user/role shared giữa nhiều service làm mất khả năng kiểm toán không?

### 10.2. Quyền theo môi trường và rotation

- **Local:** account lab có quyền cần thiết trên queue lab; không reuse production secret.
- **Staging:** policy gần production, test âm tính (writer không được consume, reader không được send).
- **Production:** identity riêng theo service, least privilege, audit, secret rotation.
- Khi rotation password/roles, chú ý ConnectionFactory/pool giữ connection đang sống; thay file secret không đồng nghĩa mọi connection tự login lại ngay. Kế hoạch reload/restart và khả năng chạy đồng thời credential cũ/mới phải được kiểm soát.
- Nếu mất credential, phải revoke/rotate ở nguồn xác thực, không chỉ xóa biến môi trường khỏi một pod.

## 11. Bảo vệ hệ thống khi kiểm thử authorization

Các thử nghiệm từ chối truy cập là cần thiết nhưng phải giới hạn:

- Dùng **broker/queue riêng cho lab** và user giả lập, không test deny bằng cách gửi hàng loạt tới queue production.
- Giới hạn thông điệp gửi và thời gian `receive` để tránh backlog.
- Phân biệt `JMSSecurityException` với `JMSSecurityRuntimeException` hoặc exception được wrap bởi Spring/provider; tham khảo audit broker để xác nhận nguyên nhân.
- Không log raw credential, token, private key, truststore password, thông tin khách hàng trong payload.
- Nếu cần chứng minh quyền browse, tránh hiện toàn bộ body nhạy cảm; chỉ dùng message ID/metadata mẫu.
- Sau khi đổi policy, kiểm tra kết nối hiện hữu có còn được giữ bởi client pooling và policy đã được nạp chưa.
- Nếu bật audit, giới hạn thông tin PII và có thời hạn lưu; đừng biến logging thành lỗ hổng bảo mật mới.

## 12. Runbook khi kết nối được nhưng không gửi hoặc nhận

### Bước 1 — xác nhận endpoint và transport

Kiểm tra broker URL, host, port, DNS/container namespace, TLS/truststore và protocol. Nếu TLS/transport chưa thành công, chưa thể coi là lỗi authorization.

### Bước 2 — xác nhận principal đã đăng nhập

Kiểm tra username nào được dùng tại runtime, cơ chế JAAS/security manager và broker audit authentication. Đừng suy từ username trong một file profile nếu environment/secret manager có override.

### Bước 3 — xác định thao tác bị từ chối

Phân biệt chính xác: `send`, `consume`, `browse`, `createAddress`, `createDurableQueue`, `delete...` hoặc `manage`. Tên queue destination và address routing phải chính xác.

### Bước 4 — đối chiếu role mapping với ACL

Với Artemis properties login: kiểm tra role mapping hiệu lực; sau đó xem `security-setting match=...` nào thật sự được chọn cho address đích. Với Classic: xem authentication groups và `authorizationEntry` `read/write/admin` của destination.

### Bước 5 — kiểm tra auto-create và topology

Destination đã tồn tại? Có dùng request–reply temporary queue, topic durable subscription hoặc queue do Spring tự khởi tạo không? Nếu có, quyền create/delete cũng quan trọng. Không cấp quyền này khi application không cần.

### Bước 6 — thử các case âm/dương

- Correct writer: auth PASS, send PASS, consume DENIED.
- Correct reader: auth PASS, consume PASS, send DENIED.
- Wrong credential: auth DENIED.
- Reader với queue không được cấp quyền: DENIED theo policy.
- Browser-only identity: browse PASS nhưng không consume.

### Bước 7 — nghiệm thu sau khi sửa

Xác nhận broker security errors giảm, consumer đăng ký đúng queue, producer send được, message xử lý/ACK và redelivery/DLQ đúng policy. **Đừng coi “authentication OK” hoặc “send OK” là bằng chứng nghiệp vụ consumer hoàn tất.**

## 13. Câu hỏi suy luận

**1. Vì sao `createContext()` có thể thành công nhưng `createConsumer()` báo lỗi?**  
Vì connection authentication chấp nhận danh tính, còn authorization trên queue không cấp `consume` hoặc quyền tạo destination cần thiết.

**2. User có `send` vào `shipping.commands` có tự được `consume` không?**  
Không. Đây là hai permission riêng của Artemis. Muốn cả hai phải có ACL/role phù hợp.

**3. TLS server certificate hợp lệ có chứng minh user JMS có quyền tạo queue không?**  
Không. TLS xác thực server/kênh; broker user/role và permission `createDurableQueue` hoặc `createNonDurableQueue` là lớp độc lập.

**4. Một service có quyền `browse` có nên được cấp `manage` để xem message dễ hơn không?**  
Không mặc định. `manage` có phạm vi quản trị rộng hơn; chỉ cấp nếu có nhu cầu được phê duyệt, còn xem message thường chỉ cần cơ chế browse/monitoring đã giới hạn.

**5. Vì sao tắt auto-create khiến ứng dụng trước đó chạy được nay báo lỗi?**  
Ứng dụng có thể đã phụ thuộc vào broker tự tạo address/queue. Cần provision destination chính thức hoặc cấp quyền create có phạm vi thích hợp, không suy ngay mật khẩu sai.

**6. Có thể dùng một security-setting của Artemis áp dụng trực tiếp lên Classic `activemq.xml` không?**  
Không. Classic dùng nhóm `read/write/admin` và authorization plugins; Artemis có phân loại quyền riêng.

**7. Mật khẩu đúng, role đúng nhưng ACL thay đổi mà client đang kết nối vẫn hoạt động khác kỳ vọng: kiểm tra gì?**  
Kiểm tra broker đã reload policy, security cache, connection pool/cached credentials và effective matching rule; không khẳng định chỉ từ file vừa được chỉnh.

**8. Producer gửi thành công có chứng minh consumer đã xử lý và ACK chưa?**  
Không. Authentication/authorization chỉ quyết định quyền thao tác; delivery, business transaction và ACK là các mốc độc lập.

## 14. Checklist security review

- [ ] Biết rõ authentication backend: properties, LDAP, certificate principal hoặc cơ chế khác.
- [ ] Mỗi client có identity/secret riêng, không tái sử dụng tài khoản broker admin.
- [ ] TLS và broker authentication được kiểm tra độc lập, không coi mTLS là full authorization.
- [ ] Role mapping từ user/principal tới role được kiểm chứng trên broker runtime.
- [ ] ACL send/consume/browse áp dụng đúng address/queue và wildcard scope.
- [ ] Quyền tạo/xóa address/queue không cấp cho worker thường nếu không cần.
- [ ] Request–reply temporary queue và durable subscription được xét nếu ứng dụng sử dụng.
- [ ] Management/console permissions được bảo vệ riêng với quyền JMS destination.
- [ ] Không hardcode secret hoặc log URL/truststore/password.
- [ ] Có negative tests: wrong password, writer cannot consume, reader cannot send.
- [ ] Không dựa vào client exception type duy nhất mà bỏ qua broker audit.
- [ ] Policy được kiểm tra sau reload/restart và với connection pooling thực tế.
- [ ] Không biến lỗi authorization thành cấp role rộng trên mọi destination.
- [ ] Có monitoring security denials, auth failures, audit và secret rotation.
- [ ] Đã phân biệt security pass với queue routing và business processing success.

## 15. Kết luận kỹ thuật

**Xác thực kết nối trả lời “bạn là ai?”, phân quyền destination trả lời “bạn được làm gì ở đâu?”.** Một producer có thể đăng nhập broker thành công nhưng không được `send`; một consumer có thể đăng nhập được nhưng không có `consume`; và TLS thành công chỉ chứng minh trạng thái kênh truyền/danh tính TLS theo cấu hình, không cấp đặc quyền JMS.

Với **Artemis**, hãy kiểm tra đủ **authentication backend → principal/role mapping → security-setting match → permission cụ thể**. Với **ActiveMQ Classic**, giữ nguyên nguyên tắc nhưng dùng đúng plugin, `read/write/admin`, client và giao thức của Classic. Độ tin cậy đi cùng bảo mật khi ứng dụng chỉ có quyền tối thiểu cần thiết, policy được kiểm thử bằng cả ca cho phép và từ chối, và trạng thái **đăng nhập / gửi / nhận / ACK / hoàn tất nghiệp vụ** không bị đánh đồng.
