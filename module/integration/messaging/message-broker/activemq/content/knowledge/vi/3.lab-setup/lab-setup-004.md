# Dựng ActiveMQ Classic và Artemis bằng Docker Compose với cổng và tài khoản tách biệt

## 1. Mục tiêu và kết quả cần đạt

Bài thực hành trong chương **Môi trường thực hành** của module **INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ** hướng dẫn chạy đồng thời **Apache ActiveMQ Classic** và **Apache ActiveMQ Artemis** trên một máy bằng Docker Compose. Sau khi hoàn tất, bạn có thể gửi/nhận thông điệp Java/JMS, quan sát queue trên giao diện quản trị và lý giải cách tách cổng, tài khoản, dữ liệu cùng phạm vi kết nối của mỗi broker.

Kết quả cần kiểm chứng:

1. Hai container **classic** và **artemis** cùng chạy trong một Compose project.
2. Giao thức messaging của Classic lắng nghe ở **127.0.0.1:61616**; Artemis ở **127.0.0.1:61617** trên **máy host**. Bên trong container, cả hai vẫn có thể dùng cổng **61616**.
3. Web console Classic là **http://127.0.0.1:8161/admin/**; Artemis là **http://127.0.0.1:8162/console**. Mỗi console dùng thông tin đăng nhập của broker tương ứng.
4. Người dùng JMS của Classic và Artemis **khác nhau**, kết nối được đúng broker; thử sai mật khẩu phải bị từ chối khi cấu hình bảo mật đã áp dụng.
5. Producer/consumer Java gửi và nhận một **TextMessage** qua **queue** trên từng broker.
6. Dữ liệu broker được đặt trong **named volumes** để không mặc nhiên biến mất khi container được tạo lại, đồng thời biết cách xóa dữ liệu lab có chủ đích.

### Sơ đồ cổng

~~~mermaid
flowchart LR
    subgraph HOST["Máy host: 127.0.0.1"]
        JC["Java client Classic"]
        JA["Java client Artemis"]
        B1["Browser Classic"]
        B2["Browser Artemis"]
    end

    subgraph COMPOSE["Docker Compose / bridge network"]
        C["classic\ncontainer: 61616, 8161"]
        A["artemis\ncontainer: 61616, 8161"]
        VC[("classic-data")]
        VA[("artemis-data")]
        C --- VC
        A --- VA
    end

    JC -->|"host 61616 → 61616"| C
    JA -->|"host 61617 → 61616"| A
    B1 -->|"host 8161 → 8161"| C
    B2 -->|"host 8162 → 8161"| A
~~~

| Hệ thống | Service DNS trong Compose | Cổng messaging nội bộ | Cổng messaging trên host | Console trên host | Tài khoản mẫu |
| --- | --- | ---: | ---: | --- | --- |
| ActiveMQ Classic | **classic** | 61616 | **61616** | **8161** tại **/admin/** | **classic_app** cho JMS; **classic_ops** cho web |
| ActiveMQ Artemis | **artemis** | 61616 | **61617** | **8162** tại **/console** | **artemis_app** cho bootstrap JMS và web |

Đây là **hai broker độc lập**, không phải một cluster. Chúng không tự đồng bộ message, queue hoặc tài khoản. Một producer gửi tới Classic không khiến consumer chỉ kết nối Artemis nhận cùng message.

## 2. Điều kiện tiên quyết và quyết định kỹ thuật

Bạn cần **Docker Engine** đang hoạt động, **Docker Compose v2** (lệnh **docker compose** có khoảng trắng), quyền chạy Docker, bốn cổng host chưa bị chiếm, và khoảng vài GB dung lượng đĩa trống cho image và journal của broker. Nếu chạy Java, cần thêm **JDK 17+** và **Maven**. Docker Desktop trên Windows/macOS hoặc Docker Engine trên Linux đều phù hợp với cấu hình mạng bên dưới.

Kiểm tra công cụ:

~~~powershell
docker version
docker compose version
java -version
mvn -version
~~~

Hướng dẫn dùng hai image công khai **apache/activemq-classic** và **apache/activemq-artemis**, ví dụ tag **latest** để trình bày cú pháp lab. **latest không phải một phiên bản bất biến**: sau khi pull ở hai thời điểm khác nhau, bản broker và hành vi mặc định có thể khác. Với dự án thực tế hoặc lab cần tái lập, thay bằng các **tag hoặc digest đã được xác minh cho đúng release**, đồng thời lưu lại phiên bản image, Java và client JMS được sử dụng.

Hai dòng broker không dùng một bộ cấu hình giống hệt nhau:

- **Classic** dùng các biến bootstrap của image như **ACTIVEMQ_CONNECTION_USER**, **ACTIVEMQ_CONNECTION_PASSWORD** và **ACTIVEMQ_WEB_USER**, **ACTIVEMQ_WEB_PASSWORD** để tạo thông tin đăng nhập kết nối và web.
- **Artemis** dùng **ARTEMIS_USER**, **ARTEMIS_PASSWORD** và **ANONYMOUS_LOGIN** khi khởi tạo broker instance. Với cấu hình lab cơ bản, một user bootstrap Artemis có thể dùng cho cả JMS và console. Việc phân tách riêng tài khoản quản trị/ứng dụng **bên trong Artemis** cần cấu hình thêm user, role và quyền trong broker.

Giá trị environment chỉ nên xem là giao diện bootstrap của **image đã chọn**. Nếu image/tag bạn sử dụng không hỗ trợ biến tương ứng hoặc broker đã có volume cấu hình cũ, cần kiểm tra tài liệu của đúng tag và trạng thái instance trước khi kết luận biến đã có hiệu lực.

## 3. Chuẩn bị cấu trúc lab và tài khoản

Trên máy người học, tạo một thư mục mới, chẳng hạn **activemq-dual-lab**, chứa hai tệp được mô tả trong bài:

~~~text
activemq-dual-lab/
├── compose.yaml
└── .env
~~~

Đoạn này là **hướng dẫn người học tự tạo file trong thư mục lab**; bản thân bài Markdown không yêu cầu sửa file nào khác trong repository khóa học.

Tạo **.env** cho Docker Compose, dùng ba bộ thông tin khác nhau. Các mật khẩu sau **chỉ là dữ liệu mẫu cho máy local** và phải thay trước khi sử dụng môi trường chia sẻ:

~~~dotenv
CLASSIC_IMAGE=apache/activemq-classic:latest
ARTEMIS_IMAGE=apache/activemq-artemis:latest

CLASSIC_JMS_USER=classic_app
CLASSIC_JMS_PASSWORD=ClassicLocal_61616_ChangeMe

CLASSIC_WEB_USER=classic_ops
CLASSIC_WEB_PASSWORD=ClassicLocal_8161_ChangeMe

ARTEMIS_USER=artemis_app
ARTEMIS_PASSWORD=ArtemisLocal_61617_ChangeMe
~~~

**Không commit .env chứa mật khẩu** vào Git, không gửi nội dung file lên ticket/chat và không dùng các mật khẩu ví dụ trên máy có người dùng khác. Có thể commit một **.env.example** chỉ có tên biến với giá trị placeholder. Với secret chứa ký tự đặc biệt (**#**, **$**, dấu cách), lưu ý quy tắc parse và interpolation của Docker Compose; kiểm thử trực tiếp bằng tài khoản được cấu hình, tránh tưởng mật khẩu đã đặt đúng khi bị biến đổi lúc parse.

Tài khoản tách biệt ở đây được hiểu theo hai lớp:

- **Giữa hai broker:** Classic dùng **classic_app**, Artemis dùng **artemis_app**; mật khẩu khác nhau và không chia sẻ cấu hình chứng thực.
- **Trong Classic:** tài khoản dành cho kết nối JMS (**classic_app**) khác với tài khoản web (**classic_ops**).
- **Trong Artemis:** ví dụ tối thiểu dùng một user bootstrap cho cả hai bề mặt. Để có **artemis_app** cho JMS và **artemis_ops** cho console, cần tạo hai user/role và giới hạn quyền với **artemis-users.properties**, **artemis-roles.properties** cùng chính sách security của broker. Không nên giả vờ chỉ thêm một biến environment là đạt yêu cầu này.

## 4. Viết compose.yaml cho hai broker

Tạo **compose.yaml**:

~~~yaml
name: activemq-dual-lab

services:
  classic:
    image: ${CLASSIC_IMAGE:-apache/activemq-classic:latest}
    restart: unless-stopped
    environment:
      ACTIVEMQ_CONNECTION_USER: ${CLASSIC_JMS_USER:?CLASSIC_JMS_USER is required}
      ACTIVEMQ_CONNECTION_PASSWORD: ${CLASSIC_JMS_PASSWORD:?CLASSIC_JMS_PASSWORD is required}
      ACTIVEMQ_WEB_USER: ${CLASSIC_WEB_USER:?CLASSIC_WEB_USER is required}
      ACTIVEMQ_WEB_PASSWORD: ${CLASSIC_WEB_PASSWORD:?CLASSIC_WEB_PASSWORD is required}
    ports:
      - "127.0.0.1:61616:61616"
      - "127.0.0.1:8161:8161"
    volumes:
      - classic-data:/opt/apache-activemq/data
    networks:
      - brokers

  artemis:
    image: ${ARTEMIS_IMAGE:-apache/activemq-artemis:latest}
    restart: unless-stopped
    environment:
      ARTEMIS_USER: ${ARTEMIS_USER:?ARTEMIS_USER is required}
      ARTEMIS_PASSWORD: ${ARTEMIS_PASSWORD:?ARTEMIS_PASSWORD is required}
      ANONYMOUS_LOGIN: "false"
    ports:
      - "127.0.0.1:61617:61616"
      - "127.0.0.1:8162:8161"
    volumes:
      - artemis-data:/var/lib/artemis-instance
    networks:
      - brokers

networks:
  brokers:
    driver: bridge

volumes:
  classic-data:
  artemis-data:
~~~

Các cặp ánh xạ port có dạng **địa-chỉ-host:cổng-host:cổng-container**. Vì vậy **127.0.0.1:61617:61616** không đổi cấu hình connector bên trong Artemis thành 61617; nó chỉ công bố cổng 61616 của container qua 61617 trên máy host.

Các điểm chủ ý của cấu hình:

| Dòng Compose | Lý do |
| --- | --- |
| **name: activemq-dual-lab** | Cho project và volumes tên dễ nhận diện khi dùng lệnh Compose |
| **classic**, **artemis** | Hai service độc lập, có hostname DNS nội bộ tương ứng |
| **127.0.0.1** trước cổng | Chỉ publish trên loopback của host, phù hợp máy cá nhân |
| **ACTIVEMQ_CONNECTION_*** | Credential dành cho OpenWire/JMS client của Classic theo image được nêu |
| **ACTIVEMQ_WEB_*** | Credential đăng nhập web console Classic theo image được nêu |
| **ARTEMIS_USER/PASSWORD** | Bootstrap user Artemis trên instance mới |
| **ANONYMOUS_LOGIN: "false"** | Yêu cầu không tự mở truy cập ẩn danh khi tạo Artemis instance |
| **classic-data**, **artemis-data** | Hai nơi lưu dữ liệu tách biệt qua named volume |
| **brokers** | Mạng bridge cho các container; cho phép truy cập bằng service name |

Trong dòng image Classic, **/opt/apache-activemq/data** là đường dẫn dữ liệu quen thuộc của image Classic được sử dụng; ở Artemis, **/var/lib/artemis-instance** là nơi chứa instance đã khởi tạo. Đường dẫn container có thể thay đổi theo image/tag hoặc image tùy biến, nên kiểm tra release đang dùng trước khi quyết định layout lưu trữ lâu dài. Đừng mount trống đè lên thư mục cấu hình mà không biết startup script tạo broker instance như thế nào.

**Tại sao không đặt container_name?** Docker Compose tự đặt tên container theo project/service và cung cấp DNS **classic**/**artemis** trong network. Không cố định container name giúp tránh xung đột khi chạy nhiều Compose project độc lập.

**Tại sao không thêm healthcheck ngay?** Image/tag có thể khác về **sh**, **curl**, **nc** hoặc lệnh CLI bên trong. Một healthcheck sao chép từ image khác dễ báo false-negative. Bài lab sử dụng kiểm tra socket, log, console và một vòng gửi/nhận JMS thực sự; đó là bằng chứng chức năng mạnh hơn chỉ thấy port đang mở.

## 5. Khởi động, xác minh cổng và giao diện

Mở terminal trong thư mục **activemq-dual-lab**:

~~~powershell
docker compose config --quiet
docker compose pull
docker compose up -d
docker compose ps
~~~

Lệnh **config --quiet** kiểm tra cú pháp và biến bắt buộc mà không in bản cấu hình đã nội suy (có thể chứa mật khẩu) lên màn hình. **pull** tải image theo tag; **up -d** tạo network, volumes và khởi động hai service. **ps** cho biết container và cổng được publish. Không khẳng định broker đã sẵn sàng ngay khi trạng thái container chuyển sang **Up**: quá trình khởi tạo broker/journal có thể vẫn đang diễn ra.

Theo dõi log riêng từng service:

~~~powershell
docker compose logs --tail=100 classic
docker compose logs --tail=100 artemis
~~~

Khi cần xem trực tiếp log trong lúc khởi động:

~~~powershell
docker compose logs -f --tail=50 artemis
~~~

Dừng theo dõi bằng **Ctrl+C**; thao tác này không dừng container. Kiểm tra socket từ **PowerShell trên Windows**:

~~~powershell
Test-NetConnection 127.0.0.1 -Port 61616
Test-NetConnection 127.0.0.1 -Port 61617
Test-NetConnection 127.0.0.1 -Port 8161
Test-NetConnection 127.0.0.1 -Port 8162
~~~

Nếu **TcpTestSucceeded = True**, cổng TCP có thể kết nối ở thời điểm kiểm tra. Kết quả đó **chưa chứng minh** JMS authentication, queue routing hoặc commit hoạt động; mục 7 và 8 sẽ kiểm tra những tầng này.

Mở trình duyệt trên chính máy host:

- **Classic:** **http://127.0.0.1:8161/admin/**, đăng nhập **classic_ops** bằng **CLASSIC_WEB_PASSWORD**.
- **Artemis:** **http://127.0.0.1:8162/console**, đăng nhập **artemis_app** bằng **ARTEMIS_PASSWORD**.

Tùy phiên bản console, giao diện có thể tự chuyển hướng đến URL có dấu **/** cuối hoặc trang login khác; không lấy hình thức giao diện làm bằng chứng một giao thức JMS cụ thể đã sẵn sàng. Trên một số image cũ/tùy biến, console path và cách kích hoạt authentication khác nhau: kiểm tra log hoặc tài liệu tag tương ứng khi gặp HTTP 404/401.

### Host và container dùng endpoint khác nhau

| Client đang chạy ở đâu? | Classic URL | Artemis URL |
| --- | --- | --- |
| Java chạy trực tiếp trên host | **tcp://127.0.0.1:61616** | **tcp://127.0.0.1:61617** |
| Java chạy trong một service cùng network **brokers** | **tcp://classic:61616** | **tcp://artemis:61616** |
| Máy khác trong mạng LAN | Không truy cập trực tiếp theo cấu hình mặc định | Không truy cập trực tiếp theo cấu hình mặc định |

Đừng truyền **tcp://127.0.0.1:61617** cho ứng dụng đang chạy **trong container khác**: khi đó **127.0.0.1** là chính container ứng dụng, không phải host Docker. Dùng service DNS khi container ở cùng network. Để kết nối từ ngoài máy, cần thiết kế publish/TLS/firewall và xác thực phù hợp; bài lab chủ ý giữ cổng ở loopback.

## 6. Kiểm tra Java/JMS với Artemis (Jakarta Messaging)

Artemis hỗ trợ nhiều giao thức; ví dụ này dùng Artemis JMS client với namespace **jakarta.jms**. Broker expose cổng 61616 trong container, còn Java chạy trên host dùng **61617**.

Trong một **thư mục demo Java riêng** trên máy người học, tạo Maven project tối thiểu với **src/main/java/ArtemisProbe.java** và **pom.xml**. Ví dụ dependency theo một release tham chiếu; chọn lại phiên bản phù hợp với broker khi cần tái lập thực nghiệm:

~~~xml
<!-- pom.xml của dự án demo Artemis -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>lab.messaging</groupId>
  <artifactId>artemis-jms-probe</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.apache.activemq</groupId>
      <artifactId>artemis-jakarta-client</artifactId>
      <version>2.42.0</version>
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
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Lớp **ArtemisProbe.java** nhận tham số **send** hoặc **receive**; session dùng **SESSION_TRANSACTED**, nên chương trình phải **commit** sau khi gửi hoặc xử lý thành công. Message có **eventId** để đối chiếu trong log.

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.Objects;
import java.util.UUID;

public final class ArtemisProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1 ||
                (!"send".equals(args[0]) && !"receive".equals(args[0]))) {
            throw new IllegalArgumentException("Usage: send | receive");
        }

        String url = System.getenv().getOrDefault(
                "JMS_URL", "tcp://127.0.0.1:61617");
        String user = Objects.requireNonNull(
                System.getenv("JMS_USER"), "Missing JMS_USER");
        String password = Objects.requireNonNull(
                System.getenv("JMS_PASSWORD"), "Missing JMS_PASSWORD");

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);

        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue queue = context.createQueue("lab.orders");

            if ("send".equals(args[0])) {
                String eventId = UUID.randomUUID().toString();
                TextMessage message = context.createTextMessage(
                        "OrderPlaced:ORD-1001");
                message.setStringProperty("eventId", eventId);

                context.createProducer()
                        .setDeliveryMode(DeliveryMode.PERSISTENT)
                        .send(queue, message);
                context.commit();

                System.out.println("ARTEMIS SENT eventId=" + eventId);
            } else {
                JMSConsumer consumer = context.createConsumer(queue);
                Message message = consumer.receive(10000);
                if (message == null) {
                    System.out.println("ARTEMIS EMPTY: no message in 10s");
                    return;
                }

                try {
                    if (!(message instanceof TextMessage)) {
                        throw new IllegalArgumentException("TextMessage required");
                    }
                    String eventId = message.getStringProperty("eventId");
                    String payload = ((TextMessage) message).getText();

                    // Trong ứng dụng thật, commit database và idempotency
                    // phải thành công trước khi commit JMS.
                    System.out.println("ARTEMIS RECEIVED " + eventId
                            + " payload=" + payload);
                    context.commit();
                } catch (Exception error) {
                    context.rollback();
                    throw error;
                }
            }
        }
    }
}
~~~

Chạy **trong terminal dự án demo Java** trên host Windows (đặt mật khẩu đúng bằng giá trị ở **.env**, ví dụ dưới đây dùng credential lab):

~~~powershell
$env:JMS_URL = "tcp://127.0.0.1:61617"
$env:JMS_USER = "artemis_app"
$env:JMS_PASSWORD = "ArtemisLocal_61617_ChangeMe"

mvn -q compile exec:java "-Dexec.mainClass=ArtemisProbe" "-Dexec.args=send"
mvn -q compile exec:java "-Dexec.mainClass=ArtemisProbe" "-Dexec.args=receive"
~~~

Trên Linux/macOS, export các biến **JMS_URL**, **JMS_USER**, **JMS_PASSWORD** tương tự trước khi chạy hai lệnh Maven. Lưu ý Docker Compose tự đọc **.env** để tạo container, nhưng **không tự động đưa các biến đó vào shell** chạy Maven trên host.

Kết quả kỳ vọng: **SENT** hiển thị một eventId, sau đó **RECEIVED** hiển thị đúng eventId và payload. Queue **lab.orders** được tạo tự động nếu broker/role cho phép auto-create; nếu tính năng này bị tắt, tạo address/queue với **ANYCAST** và cấp quyền gửi/tiêu thụ trước. Sau khi nhận và commit thành công, queue không còn message đó đang chờ.

## 7. Kiểm tra Java/JMS với ActiveMQ Classic (javax.jms)

Với ActiveMQ Classic, dùng client **org.apache.activemq:activemq-client** và namespace **javax.jms** cho ví dụ này. Đây là **một project demo Maven khác**; không trộn classpath **javax.jms** với **jakarta.jms** như thể hai package tương đương.

Tạo Maven project Classic tương tự, nhưng thay dependency trong **pom.xml** bằng:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>activemq-client</artifactId>
    <version>6.1.6</version>
  </dependency>
</dependencies>
~~~

Giữ lại cấu hình **maven.compiler.release=17**, plugin **maven-compiler-plugin** và **exec-maven-plugin** như POM đầy đủ ở mục 6. Nếu chọn một Classic release khác, chọn client tương thích, kiểm tra JDK tối thiểu và Javax/Jakarta API trên đúng dependency đang dùng.

Lớp **ClassicProbe.java** dùng JMS 1.1-style API: **Connection → Session → Producer/Consumer**. So với **JMSContext** ở ví dụ Artemis, cách thao tác khác nhau nhưng ý nghĩa **commit/rollback** là như nhau.

~~~java
import javax.jms.Connection;
import javax.jms.DeliveryMode;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.MessageProducer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TextMessage;
import org.apache.activemq.ActiveMQConnectionFactory;

import java.util.Objects;
import java.util.UUID;

public final class ClassicProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1 ||
                (!"send".equals(args[0]) && !"receive".equals(args[0]))) {
            throw new IllegalArgumentException("Usage: send | receive");
        }

        String url = System.getenv().getOrDefault(
                "JMS_URL", "tcp://127.0.0.1:61616");
        String user = Objects.requireNonNull(
                System.getenv("JMS_USER"), "Missing JMS_USER");
        String password = Objects.requireNonNull(
                System.getenv("JMS_PASSWORD"), "Missing JMS_PASSWORD");

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);
        Connection connection = factory.createConnection(user, password);

        try {
            connection.start();
            Session session = connection.createSession(
                    true, Session.SESSION_TRANSACTED);
            try {
                Queue queue = session.createQueue("lab.orders");

                if ("send".equals(args[0])) {
                    MessageProducer producer = session.createProducer(queue);
                    try {
                        producer.setDeliveryMode(DeliveryMode.PERSISTENT);
                        String eventId = UUID.randomUUID().toString();
                        TextMessage message = session.createTextMessage(
                                "OrderPlaced:ORD-2002");
                        message.setStringProperty("eventId", eventId);
                        producer.send(message);
                        session.commit();
                        System.out.println("CLASSIC SENT eventId=" + eventId);
                    } finally {
                        producer.close();
                    }
                } else {
                    MessageConsumer consumer = session.createConsumer(queue);
                    try {
                        Message message = consumer.receive(10000);
                        if (message == null) {
                            System.out.println("CLASSIC EMPTY: no message in 10s");
                            return;
                        }
                        try {
                            if (!(message instanceof TextMessage)) {
                                throw new IllegalArgumentException(
                                        "TextMessage required");
                            }
                            System.out.println("CLASSIC RECEIVED "
                                    + message.getStringProperty("eventId")
                                    + " payload="
                                    + ((TextMessage) message).getText());
                            session.commit();
                        } catch (Exception error) {
                            session.rollback();
                            throw error;
                        }
                    } finally {
                        consumer.close();
                    }
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
        }
    }
}
~~~

Chạy thử Classic trên host:

~~~powershell
$env:JMS_URL = "tcp://127.0.0.1:61616"
$env:JMS_USER = "classic_app"
$env:JMS_PASSWORD = "ClassicLocal_61616_ChangeMe"

mvn -q compile exec:java "-Dexec.mainClass=ClassicProbe" "-Dexec.args=send"
mvn -q compile exec:java "-Dexec.mainClass=ClassicProbe" "-Dexec.args=receive"
~~~

Trong console Classic, tìm queue **lab.orders** và các chỉ số **enqueued/dequeued**, **queue size**, **consumer count** (tên field có thể khác theo giao diện). Khi test Artemis, queue có cùng tên **lab.orders** nhưng nằm trên **broker khác**; hai queue không dùng chung message.

### Kiểm tra rằng credential và cổng thực sự bị tách

Sau khi cả hai bài probe thành công, thử **đổi JMS_USER thành user của broker còn lại**, giữ nguyên endpoint. Trong cấu hình bảo mật đúng, phiên đăng nhập phải thất bại. Sau đó phục hồi đúng user; không cần xóa hoặc tạo lại volume để thử sai credential.

Thử thêm các kiểm chứng sau:

| Phép thử | Kỳ vọng |
| --- | --- |
| ArtemisProbe tới **61617** với user Artemis | Kết nối và gửi/nhận thành công |
| ClassicProbe tới **61616** với user Classic | Kết nối và gửi/nhận thành công |
| ClassicProbe tới **61616** với user Artemis | Bị từ chối xác thực nếu tài khoản này không được tạo ở Classic |
| ArtemisProbe tới **61617** với user Classic | Bị từ chối xác thực nếu tài khoản này không được tạo ở Artemis |
| Dùng URL console Classic tại **8162** | Không ra console Classic, vì 8162 ánh xạ tới Artemis |
| Dùng URL console Artemis tại **8161** | Không ra console Artemis, vì 8161 ánh xạ tới Classic |

**Lưu ý giao thức:** Classic JMS client trên cổng Classic và Artemis JMS client trên cổng Artemis là cách thử dễ hiểu nhất. Hai broker có thể hỗ trợ nhiều giao thức, và Artemis thường có acceptor đa giao thức; không nên kết luận endpoint không hợp lệ chỉ vì chọn **sai library client** trong một phép thử.

## 8. Dữ liệu lưu bền và vòng đời Docker Compose

Chạy thành công một thông điệp với **PERSISTENT** là bước đầu; để xem persistence qua restart, cần quan sát khi message **chưa được consumer xác nhận**.

Thí nghiệm:

1. Từ ứng dụng Java của một broker, chạy **send**.
2. **Chưa chạy receive**; kiểm tra queue đang có message.
3. Khởi động lại service tương ứng.
4. Khi service ổn định, chạy **receive** và đối chiếu eventId.

Ví dụ kiểm tra riêng Artemis:

~~~powershell
docker compose restart artemis
docker compose logs --tail=80 artemis
~~~

Đợi broker khởi động lại, rồi dùng **ArtemisProbe receive**. Tương tự với **classic**. Message persistent vẫn có thể bị ảnh hưởng bởi TTL, policy, quota, cách storage đang cấu hình và cơ chế failover; trong lab dùng volume dữ liệu phù hợp, message chưa ack được kỳ vọng tồn tại qua restart bình thường.

| Lệnh | Tác động | Dữ liệu volume |
| --- | --- | --- |
| **docker compose stop** | Dừng service | Giữ nguyên |
| **docker compose start** | Khởi động service đã tạo | Giữ nguyên |
| **docker compose restart artemis** | Restart Artemis | Giữ nguyên |
| **docker compose down** | Xóa container và network Compose | **Giữ named volumes** |
| **docker compose up -d** sau down | Tạo lại container dùng lại volumes của project | Dữ liệu cũ có thể được dùng lại |
| **docker compose down -v** | Xóa cả named volumes do project quản lý | **Xóa dữ liệu broker của lab** |

Chỉ chạy **down -v** khi chủ động muốn **reset toàn bộ** message, journal và Artemis instance trong lab. Lệnh này có tính phá hủy dữ liệu; tránh áp dụng cho broker có dữ liệu cần giữ.

### Cảnh báo quan trọng: thay mật khẩu nhưng volume cũ vẫn tồn tại

Artemis image thường dùng **ARTEMIS_USER/PASSWORD** ở bước tạo broker instance ban đầu. Khi instance đã nằm trong volume **artemis-data**, đổi **.env** rồi chạy **up -d** không bảo đảm user/password trong instance được cập nhật. Hãy kiểm tra security files của instance và quy trình quản trị tài khoản tương ứng với release.

Với môi trường học **không có dữ liệu cần giữ**, có thể reset instance qua **down -v** rồi tạo lại; với môi trường thực tế, cần **thay đổi user/role/secret trong broker** theo đúng cơ chế của sản phẩm, đồng bộ client credentials và kiểm tra quyền truy cập. Xóa data volume để đổi password không phải quy trình vận hành chấp nhận được.

## 9. Acknowledgment, transaction, redelivery và DLQ trong lab

Hai ứng dụng probe dùng **transacted JMS session**. Khi **commit** hoàn tất sau receive, broker xem message đã được tiêu thụ trong session đó. Nếu consumer nhận message nhưng **rollback**, hoặc chết trước **commit**, message có thể được phát lại theo chính sách redelivery. Đây là điểm thiết yếu của giao tiếp bất đồng bộ đáng tin cậy.

Thử thực hành:

1. Gửi một event vào **lab.orders**.
2. Trong code consumer, thay dòng **commit** ở nhánh nhận bằng **rollback** cho lần thử đầu.
3. Chạy receive thêm một lần và quan sát khả năng nhận lại cùng **eventId**.
4. Khôi phục commit sau khi kiểm tra; nếu message liên tục lỗi, giới hạn số lần thử và cấu hình DLQ.

**Không kết luận exactly-once** chỉ vì sau một lần commit queue về 0. Nếu transaction database đã commit nhưng JMS commit bị mất kết nối, broker có thể gửi lại. Trong ứng dụng thật, dùng **eventId** ổn định và lưu trạng thái xử lý trong DB cùng transaction với side effect; khi redelivery, nhận ra sự kiện đã xử lý rồi commit JMS mà không trừ kho/ghi tiền thêm lần nữa.

### Cấu hình minh họa trên Artemis

Đoạn XML sau minh họa chính sách ở **broker.xml** của Artemis; **không tự có hiệu lực chỉ bằng việc dán vào compose.yaml**. Khi tùy chỉnh, đặt nó **bên trong phần address-settings hiện hữu** theo cấu trúc XML của broker instance và bảo đảm dead-letter address/queue phù hợp đã tồn tại hoặc được tự tạo theo policy:

~~~xml
<address-setting match="lab.#">
  <dead-letter-address>DLQ</dead-letter-address>
  <expiry-address>ExpiryQueue</expiry-address>
  <redelivery-delay>2000</redelivery-delay>
  <redelivery-multiplier>2.0</redelivery-multiplier>
  <max-redelivery-delay>30000</max-redelivery-delay>
  <max-delivery-attempts>5</max-delivery-attempts>
</address-setting>
~~~

Ý nghĩa:

- **redelivery-delay = 2000**: giãn 2 giây trước retry trong trường hợp áp dụng.
- **redelivery-multiplier = 2.0**, **max-redelivery-delay = 30000**: tăng delay theo cấp số nhân tới giới hạn 30 giây.
- **max-delivery-attempts = 5**: giới hạn số lần giao thất bại trước khi áp dụng DLQ policy.
- **dead-letter-address = DLQ**: địa chỉ nhận các message đạt điều kiện dead-letter.
- **expiry-address = ExpiryQueue**: nơi xử lý message hết hạn, khác với lỗi nghiệp vụ.

Muốn dùng DLQ/expiry thực tế, phải kiểm tra binding/routing queue tương ứng, security permission, cơ chế tự tạo destination và khả năng quan sát trong console. Đừng ép message lỗi vô hạn quay về queue chính.

### Cấu hình client redelivery với ActiveMQ Classic

Với Classic, ví dụ tùy chỉnh **client-side redelivery policy** như sau (đặt ở phía tạo **ActiveMQConnectionFactory** trước khi tạo Connection):

~~~java
org.apache.activemq.RedeliveryPolicy policy =
        factory.getRedeliveryPolicy();
policy.setInitialRedeliveryDelay(2000);
policy.setUseExponentialBackOff(true);
policy.setBackOffMultiplier(2.0);
policy.setMaximumRedeliveries(4);
~~~

Classic còn có **dead-letter strategy** ở broker trong chính sách destination; việc queue DLQ nào được chọn phụ thuộc cấu hình broker. Cần hiểu ranh giới: cài policy trên client Classic không tương đương với việc chỉnh **address-settings** của Artemis và không tự biến Classic thành Artemis.

## 10. Bảo mật: tách tài khoản là điều kiện cần, chưa đủ

Đây là lab chạy trên máy cá nhân; cấu hình publish đến **127.0.0.1** hạn chế kết nối từ mạng ngoài. Trong hệ thống thật, cần thêm các lớp bảo vệ:

- **Xác thực:** không chấp nhận anonymous nếu nghiệp vụ yêu cầu; không dùng mật khẩu ví dụ; đặt secret qua cơ chế quản lý secret thích hợp.
- **Phân quyền:** producer chỉ được send destination cần thiết, consumer chỉ được consume queue của mình; operator/admin có quyền quản trị riêng. Chính sách xác thực thành công không đồng nghĩa user có quyền trên mọi queue.
- **TLS:** URL **tcp://** trong bài chưa mã hóa lưu lượng. Với môi trường nhiều máy, cấu hình connector/acceptor TLS và dùng client truststore/keystore tương ứng; console cũng nên dùng HTTPS sau reverse proxy hoặc security của broker.
- **Quản lý console:** hạn chế nguồn truy cập console, bảo vệ endpoint quản trị, không publish console ra Internet chỉ với mật khẩu đơn giản.
- **Secret trong Compose:** biến environment có thể lộ qua một số lệnh kiểm tra cấu hình hoặc quyền Docker; không in **docker compose config** đầy đủ vào log công khai. Cân nhắc Docker secrets/secret manager theo khả năng từng image ở production.
- **Lưu trữ và audit:** volume bền vững không thay thế backup/restore, disk quota, giám sát journal/paging, alert DLQ, retention và chính sách xử lý message chứa dữ liệu nhạy cảm.

Để tách **console user và JMS user trong Artemis**, cấu hình thêm role với nhóm quyền **send**, **consume**, **browse**, **manage**, **create/delete address/queue** phù hợp; quyền **manage** đặc biệt cần hạn chế. Với Classic, phân tách **ACTIVEMQ_WEB_*** và **ACTIVEMQ_CONNECTION_*** là bước đầu, nhưng broker authorization theo queue/topic vẫn phải được thiết kế nếu nhiều ứng dụng chia sẻ broker.

## 11. Khắc phục lỗi theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách khoanh vùng |
| --- | --- | --- |
| **port is already allocated / bind failed** | Cổng host 61616/61617/8161/8162 đã bị chiếm | **docker compose ps**, kiểm tra ứng dụng đang dùng cổng; đổi **cổng host** ở trái dấu **:** rồi cập nhật JMS_URL |
| Classic lên nhưng Artemis không lên | Image pull lỗi, instance/volume hoặc quyền ghi lỗi | **docker compose logs --tail=100 artemis**, kiểm tra đường dẫn volume và phiên bản image |
| **connection refused** tới 61617 | Artemis chưa sẵn sàng, port mapping sai, Docker Engine chưa chạy | **docker compose ps**, **Test-NetConnection**, xem log startup |
| **Authentication failed** | Sai user/password, env chưa áp dụng, instance Artemis dùng credential cũ | Đối chiếu **.env**, kiểm tra login đúng broker và lifecycle volume; không xóa dữ liệu khi chưa hiểu |
| Console 401/403 | Sai tài khoản quản trị hoặc role không đủ quyền | Thử credential web của đúng broker và kiểm tra cấu hình role/security |
| Console 404 | Sai path hoặc biến thể image khác | Thử **/admin/** (Classic) hoặc **/console** (Artemis), kiểm tra log và tài liệu release |
| Java lỗi **ClassNotFound** hoặc **NoSuchMethod** | Classpath JMS sai, trộn javax/jakarta, dependency không tương thích | Tách hai Maven project và kiểm tra client artifact/phiên bản |
| Producer send được nhưng consumer không nhận | Đọc nhầm broker, destination sai, message chưa commit, TTL đã hết, thiếu quyền | In **JMS_URL** (không in password), tên queue, eventId; xem queue depth/in-flight/expiry |
| Restart xong mất message | Dùng non-persistent, message đã ack/expired, mapping volume sai | Kiểm tra delivery mode, trạng thái ack, retention và mount path |
| Queue liên tục tăng | Không có consumer hoặc consumer chậm/bị lỗi, prefetch cao, DB nghẽn | Quan sát consumer count, queue depth, oldest-message age, redelivery và resource |
| Message không vào DLQ | Chưa cấu hình DLQ/attempts, sai binding, policy mặc định khác giả định | Kiểm tra config broker thực tế, delivery count và destination của DLQ |

Khi debug, luôn ghi rõ **broker nào**, **host hay container**, **cổng nào**, **user nào** (không ghi password), **queue/topic nào** và **eventId nào**. Những thông tin này thường chỉ ra nguyên nhân nhanh hơn việc thay đổi ngẫu nhiên cấu hình.

### Ba lỗi dễ nhầm nhất

**Nhầm host port với container port:** trong Compose, **61617:61616** nghĩa là Java trên host dùng **61617**, Java trong cùng Docker network dùng **61616** với hostname **artemis**.

**Nhầm tài khoản JMS với tài khoản console:** Classic có thể cấp hai bộ credential riêng. Đăng nhập console thành công không chứng minh **classic_app** có quyền consume queue; phải thử với client JMS thực sự.

**Nhầm container up với message xử lý xong:** broker đang chạy chỉ cho biết tiến trình còn hoạt động. Hãy xác thực gửi, nhận, commit, idempotency và redelivery bằng bài thử đầu cuối.

## 12. Bài tập mở rộng và tiêu chí nghiệm thu

### Bài tập A — Gửi mỗi broker một thông điệp riêng

Gửi **OrderPlaced:ORD-2002** tới Classic và **OrderPlaced:ORD-1001** tới Artemis. Mở cả hai console, xác nhận queue **lab.orders** xuất hiện trên từng broker. Nhận từng message với đúng ứng dụng. Giải thích vì sao eventId và queue name có thể giống nhau nhưng message không bị trộn giữa hai broker.

### Bài tập B — Thử sai mật khẩu

Đổi tạm **JMS_PASSWORD** trong shell thành mật khẩu của broker kia rồi thử **send**. Xác nhận client bị từ chối, ghi nhận lỗi ở log và khôi phục secret. Nếu vẫn gửi thành công, cần kiểm tra anonymous authentication, default account hoặc credential config còn cũ, không nên xem bài tập là đã đạt.

### Bài tập C — Chứng minh persistence

Gửi message ở mode **PERSISTENT**, đừng chạy receive, restart đúng broker rồi nhận lại. Nêu khác biệt giữa **docker compose restart**, **down** và **down -v**. Nếu kết quả khác kỳ vọng, kiểm tra journal/volume/TTL/policy thay vì tự động kết luận broker lỗi.

### Bài tập D — Redelivery và DLQ

Sửa consumer để rollback một message cố định, cấu hình policy có retry delay và giới hạn attempts trên môi trường lab, quan sát **JMSRedelivered**/**JMSXDeliveryCount** khi provider cung cấp. Sau ngưỡng, kiểm tra DLQ và đề xuất thủ tục sửa dữ liệu/replay. Khi kiểm thử, tránh vòng lặp rollback quá nhanh làm đầy log hoặc CPU.

| Tiêu chí | Cách kiểm chứng | Đạt khi |
| --- | --- | --- |
| Hai broker chạy song song | **docker compose ps** và logs | Cả hai khởi động bình thường, không xung đột cổng |
| Cổng tách biệt | Test-NetConnection và URL console | 61616/8161 trỏ Classic; 61617/8162 trỏ Artemis |
| Credential tách biệt | Đăng nhập console và probe đúng/sai user | Đúng broker thành công; sai credential bị từ chối |
| Messaging hoạt động | ArtemisProbe và ClassicProbe | Gửi và nhận được eventId/payload trên đúng queue |
| JMS transaction hoạt động | Nhánh send/receive gọi commit | Message được ack sau xử lý thành công |
| Persistence hoạt động | Gửi, restart, nhận lại | Message persistent chưa ack vẫn có thể nhận sau restart |
| Biết ứng phó sự cố | Thử rollback và xem DLQ | Giải thích được redelivery, backoff và ngưỡng retry |
| Hiểu giới hạn bảo mật | Kiểm tra endpoint localhost, TLS, role | Không đánh đồng user/password với phân quyền và mã hóa |

## 13. Dừng lab và những điều cần ghi nhớ

Dừng container nhưng giữ dữ liệu:

~~~powershell
docker compose stop
~~~

Xóa container/network Compose, **giữ named volumes**:

~~~powershell
docker compose down
~~~

Chỉ khi dữ liệu lab không còn cần thiết và muốn xóa hoàn toàn instance thử nghiệm:

~~~powershell
docker compose down -v
~~~

Lab đã thiết lập **hai môi trường ActiveMQ tách biệt** để kiểm chứng **queue, routing, producer/consumer Java, JMS acknowledgment/transaction, redelivery/DLQ và bảo mật kết nối**. Hãy giữ rõ ba ranh giới: **port được publish trên host** khác với **port nội bộ container**; **credential của Classic** khác với **credential của Artemis**; và **broker đã nhận message** khác với **consumer đã xử lý và xác nhận thành công**. Khi chuyển từ thử nghiệm sang vận hành, cần bổ sung pin version, TLS, RBAC, kiểm thử failover, giám sát backlog/DLQ và kiểm soát side effect bằng idempotency.
