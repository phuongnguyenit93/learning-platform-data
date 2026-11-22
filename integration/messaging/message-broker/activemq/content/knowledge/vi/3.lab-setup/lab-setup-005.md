# Gắn volume dữ liệu và phân biệt khởi động lại container với tạo broker mới

> **Chương: Môi trường thực hành.** Bài thuộc module **INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ**, tìm hiểu Apache ActiveMQ Classic và Apache Artemis trong giao tiếp bất đồng bộ bằng queue, topic, routing và JMS. Trọng tâm là quản lý **vòng đời broker chạy trong Docker**: dữ liệu nào nằm trong container, dữ liệu nào nằm trong volume, khi nào là khởi động lại cùng broker, khi nào một broker instance mới được tạo, và cách tự kiểm chứng bằng message JMS. Các vấn đề acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành sẽ được liên hệ tới khả năng phục hồi sau restart.

## 1. Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Giải thích sự khác nhau giữa **Docker image**, **container**, **container writable layer**, **Docker named volume**, **bind mount** và **broker instance**.
2. Dự đoán trạng thái queue/message khi chạy `docker restart`, `docker compose restart`, `docker compose up --force-recreate`, `docker compose down` rồi `up`, đổi volume, hoặc chủ động xóa volume.
3. Khởi chạy một Artemis broker bằng Docker Compose, **gắn đúng thư mục dữ liệu và cấu hình** vào named volume, kiểm tra mount thực tế.
4. Viết producer/consumer Java JMS để gửi persistent message, duyệt queue mà không tiêu thụ, thử rollback/commit và xác nhận khả năng phục hồi.
5. Phân biệt dữ liệu biến mất vì **thay broker** với dữ liệu không còn vì **message đã ack, hết TTL, bị xóa/expiry, hoặc chưa từng được yêu cầu lưu bền vững**.
6. Liệt kê điều kiện cần cho môi trường đáng tin cậy: journal persistence, bảo vệ volume, quyền file, sao lưu, redelivery/DLQ, giữ định danh broker và quan sát sự cố.

**Tình huống:** Một ứng dụng đặt hàng gửi lệnh `ProcessOrder` vào queue. Bạn dừng Docker, khởi động lại và bất ngờ thấy queue trống. Có phải ActiveMQ đã làm mất message? Có thể, nhưng cũng có thể bạn đã tạo broker instance mới với volume rỗng, message đã được consumer nhận/ack, hoặc producer gửi message không bền vững. Bài thực hành dưới đây giúp phân biệt từng khả năng bằng bằng chứng cụ thể.

## 2. Ba đối tượng cần phân biệt: image, container và broker instance

Một **Docker image** chứa chương trình ActiveMQ, runtime Java, tập tin cấu hình mẫu và entrypoint. **Container** là một lần tạo môi trường chạy dựa trên image: nó có ID, process, network namespace và một writable layer riêng. **Broker instance** là tập cấu hình và trạng thái mà chương trình broker sử dụng khi chạy: cấu hình address/queue, journal, paging, message chưa ack, metadata broker, v.v.

Ba đối tượng này có vòng đời khác nhau:

```text
                  image apache/artemis:2.57.0-alpine
                               │
                       docker compose up
                               │
              ┌────────────────▼────────────────┐
              │ Container: broker               │
              │  • process Java                 │
              │  • writable layer riêng         │
              │  • mount point                   │
              │    /var/lib/artemis-instance ───────┐
              └─────────────────────────────────┘   │
                                                    ▼
                                        Docker named volume
                                        <project>_broker_instance
                                          ├── etc/
                                          ├── data/
                                          ├── log/
                                          └── ...
```

Trong image Artemis chính thức dùng ở bài này, thư mục **`/var/lib/artemis-instance`** chứa cấu hình **và** dữ liệu của broker. Khi thư mục đó được gắn vào named volume, container mới có thể dùng lại instance cũ, miễn là nó gắn **đúng volume** và phiên bản broker tương thích.

**Phân biệt cực kỳ quan trọng:**

- **Khởi động lại container**: dừng và chạy lại **cùng container ID**; writable layer chưa bị xóa. Một thí nghiệm chỉ dùng `docker restart` có thể thấy dữ liệu còn nguyên **kể cả khi chưa gắn volume**. Nó chưa chứng minh bạn đã thiết kế persistence đúng.
- **Tạo lại container**: container ID mới, writable layer mới. Dữ liệu ngoài volume/bind mount cũ thường không tự chuyển sang container mới. Nếu gắn lại **chính volume cũ**, broker có thể phục hồi state đã persist.
- **Tạo broker instance mới**: thư mục instance chưa từng được khởi tạo hoặc được cấp một thư mục/volume rỗng. Entry point của Artemis tạo cấu hình và các data directory mới. Container mới **không đồng nghĩa** broker mới; container cũ **không đồng nghĩa** state chắc chắn còn.
- **Đổi image version**: có thể vẫn dùng lại volume hiện hữu, nhưng đây là thao tác nâng cấp broker, cần xét tương thích định dạng journal/config và quy trình rollback. Không tự coi mọi phiên bản có thể đọc cùng dữ liệu.

Tên container (ví dụ `broker`), hostname, cổng `61616` hay `8161` **không phải định danh duy nhất của broker instance**. Một container mới mang cùng tên và map cùng cổng vẫn có thể dùng một storage hoàn toàn rỗng.

### 2.1. State nằm ở đâu?

Với **Artemis file journal**, một instance thường có:

| Phần | Vai trò | Vì sao liên quan tới volume |
|---|---|---|
| `etc/` | `broker.xml`, cấu hình bảo mật, cấu hình runtime | Đổi container mà không giữ `etc/` có thể tạo broker với setting khác |
| `data/bindings/` | Thông tin định nghĩa và binding của queue/address, metadata | Giúp broker khôi phục cấu trúc destination có lưu bền vững |
| `data/journal/` | Message journal, trạng thái nhận/xóa/ack và metadata có liên quan | Bảo toàn các persistent message chưa xử lý theo chính sách |
| `data/paging/` | Các message page khi lượng dữ liệu vượt giới hạn bộ nhớ | Không được quên nếu muốn khôi phục backlog lớn |
| `data/largemessages/` hoặc đường dẫn đã cấu hình | Dữ liệu large message bên ngoài journal | Mất đường dẫn này có thể khiến bản ghi journal trỏ tới nội dung thiếu |
| `log/`, `tmp/` | Log/đối tượng tạm của instance | Hữu ích khi điều tra nhưng không thay thế dữ liệu nghiệp vụ |

Các đường dẫn con là **giá trị phổ biến trong instance Artemis file journal**, không phải cam kết bất biến của mọi phiên bản/configuration. Kiểm tra `broker.xml` thực tế vì `bindings-directory`, `journal-directory`, `paging-directory` và `large-messages-directory` có thể được đổi; nếu chúng trỏ ra **ngoài** mount, chỉ gắn một thư mục có thể chưa đủ.

**ActiveMQ Classic** thường dùng **KahaDB** làm persistent message store trong thư mục dữ liệu (thường là `/opt/apache-activemq/data` ở image Classic chính thức) và sử dụng cấu hình tại `conf/activemq.xml`. Classic và Artemis có định dạng lưu trữ khác nhau: không thể đem volume journal của Artemis gắn thẳng cho Classic hoặc ngược lại để “khôi phục”.

**Ngoại lệ khác:** Artemis cũng có thể dùng JDBC store thay vì file journal. Khi đó trạng thái nằm trong database; volume cho thư mục instance vẫn có thể cần để giữ cấu hình, nhưng khả năng phục hồi message phụ thuộc vào DB, schema, kết nối và backup của DB.

### 2.2. Hai trục độc lập: Docker persistence và JMS persistence

Cần **đồng thời** nhìn vào storage của container và chính sách giao nhận message:

| Trục | Câu hỏi | Ví dụ |
|---|---|---|
| Docker storage | “File journal có tồn tại sau khi container bị xóa?” | Named volume gắn đúng `/var/lib/artemis-instance` |
| Broker persistence | “Broker có ghi trạng thái message xuống store?” | Artemis `persistence-enabled=true`, sync journal thích hợp |
| JMS delivery | “Producer yêu cầu message bền vững?” | `DeliveryMode.PERSISTENT` thay cho `NON_PERSISTENT` |
| Destination/consumer | “Message còn chờ ở đâu, có bị ai xử lý/ack chưa?” | Queue durable; subscription bền vững cho topic nếu cần nhận khi offline |
| TTL và chính sách | “Message có thể hết hạn, hết backlog, bị purge hoặc bị chuyển DLQ?” | Expiry, max delivery attempts, auto-delete queue, retention |

**Gắn volume không tự biến NON_PERSISTENT message thành PERSISTENT.** Ngược lại, producer gửi PERSISTENT vào broker có file journal nhưng chỉ ghi trong writable layer sẽ vẫn mất khả năng khôi phục khi container bị *remove* và tạo container khác không mang theo state.

## 3. Bảng quyết định: lệnh Docker tác động tới dữ liệu ra sao?

Bảng này giả định một broker Artemis đơn lẻ, persistent message còn trong queue, không có consumer tự ack và mount đúng named volume:

| Thao tác | Container ID | Named volume | Kỳ vọng với message đang chờ |
|---|---|---|---|
| `docker restart <container>` | Giữ nguyên | Giữ nguyên | Còn sau broker khởi động lại |
| `docker stop` rồi `docker start` | Giữ nguyên | Giữ nguyên | Còn |
| `docker compose restart broker` | Giữ nguyên | Giữ nguyên | Còn |
| `docker compose up -d` khi service đã có | Thường giữ nếu không cần recreate | Giữ nguyên | Còn |
| `docker compose up -d --force-recreate` | **Đổi** | **Giữ volume cũ** | Còn |
| `docker compose down` rồi `docker compose up -d` | **Đổi** | **Giữ named volume** | Còn |
| `docker compose down -v` rồi `up` | Đổi | **Xóa named volume do Compose quản lý** | **Mất dữ liệu của volume bị xóa** |
| Tạo service với **một named volume rỗng khác** | Có thể đổi | Volume khác | Broker mới, queue/message cũ không hiện |
| Đổi **Compose project name** khi volume dùng tên theo project | Thường đổi | Tự tạo volume khác | Có thể thấy broker rỗng như mới |
| Xóa container **không có mount lưu dữ liệu** rồi tạo mới | Đổi | Không có volume để dùng lại | Writable layer cũ bị loại bỏ; dữ liệu không được giữ |
| Dùng image broker mới nhưng mount **cùng volume** | Đổi | Cũ | Có thể phục hồi nếu hỗ trợ nâng cấp/tương thích |

Các kết quả “còn” dựa trên giả định broker ghi bền vững thành công, dữ liệu chưa bị tiêu thụ/ack, không hết hạn và hệ lưu trữ không lỗi. **Cùng volume không đồng nghĩa tất cả message đều phải còn**.

> **Không chạy `docker compose down -v`, `docker volume rm` hoặc xóa thư mục bind mount trên một môi trường đang giữ dữ liệu cần thiết.** Đó là thao tác reset/xóa dữ liệu, không phải cách restart thông thường. Trong bài này, lệnh có `-v` chỉ được phân tích để nhận biết rủi ro; không cần thực thi để chứng minh mount hoạt động.

### 3.1. Named volume, bind mount và anonymous volume

**Named volume** do Docker quản lý, ví dụ `broker_instance:/var/lib/artemis-instance`, là lựa chọn thuận tiện cho lab và nhiều môi trường triển khai. Dữ liệu không phụ thuộc writable layer của container và có thể được một container mới gắn lại bằng tên. Với Docker Compose, tên thực tế thường có tiền tố project, ví dụ `artemis-volume-lab_broker_instance`.

**Bind mount** ánh xạ một thư mục host vào container:

```yaml
services:
  broker:
    volumes:
      - ./artemis-instance:/var/lib/artemis-instance
```

Bind mount dễ thấy file trên máy host và dễ backup bằng công cụ host, nhưng phải kiểm soát quyền đọc/ghi, khác biệt đường dẫn Windows/Linux và trạng thái của ổ đĩa. Trên Linux, thư mục bind mount phải writable cho UID/GID đang chạy broker; không khắc phục lỗi permission bằng cách mặc định chạy broker dưới quyền root.

**Anonymous volume** không đặt tên tường minh. Nó có thể tồn tại sau khi xóa container nhưng thường khó gắn lại đúng volume ở lần tạo mới; việc Docker image khai báo `VOLUME` **không thay cho** thiết kế named volume rõ ràng. Vì thế một lần restart thấy data còn không chứng minh lần recreate tiếp theo sẽ tự tìm lại anonymous volume.

**Cần thêm sự phân biệt:** `docker compose down` mặc định không xóa named volumes, nhưng `docker compose down -v` có thể xóa volumes do Compose quản lý; việc đổi project name sẽ đổi prefix của named volume trừ khi volume đặt `name` cố định hoặc là external volume.

## 4. Lab chính: tạo Artemis với named volume

Ví dụ dùng image Apache Artemis **`apache/artemis:2.57.0-alpine`**, tương ứng một bản release đã phát hành. Việc cố định tag giúp kết quả lab lặp lại được; trong môi trường được quản trị chặt hơn, có thể pin image digest và kiểm thử quy trình nâng cấp riêng.

### 4.1. Điều kiện chuẩn bị

- Docker Engine/Docker Desktop hoạt động và có Docker Compose v2 (`docker compose version`).
- Máy có cổng `61616` (client messaging) và `8161` (web console) chưa bị process khác sử dụng.
- JDK 17 trở lên, Maven 3.9+ cho phần Java JMS. Thực hành trên terminal Linux/macOS hoặc PowerShell với Docker Desktop đều được.
- Lab trên máy cá nhân, không mở cổng broker ra Internet.

Hãy tạo **một thư mục lab độc lập trên máy của bạn** và đặt nội dung bên dưới vào `compose.yaml`. Đây là **mẫu minh họa** để người học tự thực hiện; bài học không cần thêm file cấu hình nào vào repo hiện tại.

```yaml
name: artemis-volume-lab

services:
  broker:
    image: apache/artemis:2.57.0-alpine
    ports:
      - "127.0.0.1:61616:61616"
      - "127.0.0.1:8161:8161"
    environment:
      ARTEMIS_USER: labuser
      ARTEMIS_PASSWORD: ${ARTEMIS_PASSWORD:?Set ARTEMIS_PASSWORD in your shell}
      ANONYMOUS_LOGIN: "false"
    volumes:
      - broker_instance:/var/lib/artemis-instance
    stop_grace_period: 30s
    restart: unless-stopped

volumes:
  broker_instance:
```

Giải thích từng điểm liên quan đến mục tiêu:

- `image` là **chương trình broker**; `volume` là **state instance**, không phải một phần mới của image.
- `broker_instance:/var/lib/artemis-instance` giữ cả `etc` và `data` của Artemis, giúp container được recreate mà vẫn dùng cùng instance.
- `ARTEMIS_USER` và `ARTEMIS_PASSWORD` là thông tin **khởi tạo** của image cho instance mới. Nếu instance đã tồn tại trong volume, **đổi biến môi trường không tự ghi đè user/password trong config cũ**. Thay đổi tài khoản về sau phải thực hiện bằng quy trình quản trị broker thích hợp.
- Bind cổng vào `127.0.0.1` để chỉ phục vụ trên loopback host trong lab. Không coi cấu hình này là đủ bảo mật cho production.
- `stop_grace_period` cho broker thời gian kết thúc process sạch hơn khi dừng; nó không thay thế durability/sao lưu.
- `restart: unless-stopped` là chính sách tự khởi động lại container khi phù hợp; nó không quyết định việc tạo hay gắn volume.

**Cảnh báo về secret:** Đặt một mật khẩu **chỉ dùng cho lab** và không commit vào Git. Production cần cơ chế lưu secret thích hợp, TLS, mạng riêng, role/permission theo destination và quản trị tài khoản.

### 4.2. Đặt biến môi trường và khởi động

Trên **PowerShell**, tại thư mục chứa `compose.yaml`:

```powershell
$env:ARTEMIS_PASSWORD = 'lab-only-change-this-password'
$env:BROKER_USER = 'labuser'
$env:BROKER_PASSWORD = $env:ARTEMIS_PASSWORD

docker compose config
docker compose up -d
docker compose ps
docker compose logs --tail 80 broker
```

Trên **Bash/zsh**:

```bash
export ARTEMIS_PASSWORD='lab-only-change-this-password'
export BROKER_USER='labuser'
export BROKER_PASSWORD="$ARTEMIS_PASSWORD"

docker compose config
docker compose up -d
docker compose ps
docker compose logs --tail 80 broker
```

`docker compose config` kiểm tra cú pháp và các biến đã được interpolate. Lệnh này có thể **in mật khẩu** trong phần output `environment`; đừng sao chép output đó vào ticket, screenshot hoặc log công khai. Nếu dùng shell mới cho các bước tiếp theo, bạn phải nạp lại biến môi trường cần thiết; biến PowerShell của terminal trước không tự truyền sang terminal mới.

Nếu broker khởi động đúng, trang quản trị ở `http://127.0.0.1:8161` và client JMS kết nối `tcp://127.0.0.1:61616`. Tên đăng nhập là `labuser` và mật khẩu do bạn đặt. Web console và network listener dùng cùng broker nhưng khác mục đích; hoạt động của trang web **không tự chứng minh** journal đã được gắn đúng.

### 4.3. Xác minh mount thực sự tồn tại

```bash
docker compose ps
docker compose ps -q broker

# Xem danh sách mount thực của container hiện tại:
docker inspect --format '{{json .Mounts}}' artemis-volume-lab-broker-1

# Xem các volume do Docker quản lý:
docker volume ls

# Với project và key ở compose.yaml, thông thường:
docker volume inspect artemis-volume-lab_broker_instance
```

Tên container tự sinh có thể khác theo Compose/project/version; nếu `artemis-volume-lab-broker-1` không tồn tại, hãy lấy tên thực trong `docker compose ps`. Một lệnh thay thế ít phụ thuộc tên container là `docker compose exec broker sh -c 'ls -la /var/lib/artemis-instance'`.

Trong `docker inspect`, kiểm tra **`Type=volume`**, **`Destination=/var/lib/artemis-instance`**, tên volume thực tế, và mount **không phải read-only**. `docker volume inspect` cho biết `Mountpoint` trên host Docker. Với Docker Desktop, đó thường là path nằm trong VM/WSL do Docker quản lý; đừng sửa trực tiếp file journal đang được broker sử dụng.

Kiểm tra cấu trúc bên trong:

```bash
docker compose exec broker sh -c 'ls -la /var/lib/artemis-instance'
docker compose exec broker sh -c 'ls -la /var/lib/artemis-instance/data'
docker compose exec broker sh -c 'ls -la /var/lib/artemis-instance/etc'
```

Thường thấy `etc` và `data` được tạo trong lần bootstrap đầu tiên. Với file journal, có thể có file journal đã được preallocate dù queue không chứa message; **kích thước file lớn không phải bằng chứng có message đang chờ**. Dùng console/JMS để kiểm tra message thực tế.

## 5. Thực hành Java/JMS: gửi và quan sát message chưa ack

Mục tiêu thí nghiệm là tạo một message **PERSISTENT** vào queue, không có consumer chạy liên tục, sau đó dùng **QueueBrowser** kiểm tra trạng thái trước và sau thao tác Docker. QueueBrowser xem message nhưng không tiêu thụ/ack, giúp kết quả thí nghiệm dễ kiểm soát hơn.

### 5.1. Maven dependency phù hợp Artemis 2.57.0

Đặt file `pom.xml` trong một project Maven lab độc lập, với nội dung tối thiểu:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo.activemq</groupId>
  <artifactId>broker-volume-probe</artifactId>
  <version>1.0-SNAPSHOT</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.apache.artemis</groupId>
      <artifactId>artemis-jakarta-client</artifactId>
      <version>2.57.0</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
```

Từ Artemis 2.57, Maven group ID được sử dụng trong tài liệu hiện hành là `org.apache.artemis`; artifact `artemis-jakarta-client` sử dụng API `jakarta.jms`. Khi dùng client Classic/JMS cũ có thể cần tọa độ và namespace khác; **không trộn `javax.jms` và `jakarta.jms` một cách ngẫu nhiên**.

### 5.2. Một chương trình dùng lại cho mọi vòng test

Tạo `src/main/java/demo/BrokerVolumeProbe.java`:

```java
package demo;

import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSProducer;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.QueueBrowser;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.Enumeration;

public final class BrokerVolumeProbe {
    private static final String QUEUE_NAME = "lab.persistence.queue";

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            usage();
            return;
        }

        String url = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = required("BROKER_USER");
        String password = required("BROKER_PASSWORD");

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url, user, password);

        switch (args[0]) {
            case "send" -> {
                if (args.length != 3) {
                    usage();
                    return;
                }
                send(factory, args[1], args[2]);
            }
            case "browse" -> browse(factory);
            case "receive-commit" -> receive(factory, true);
            case "receive-rollback" -> receive(factory, false);
            default -> usage();
        }
    }

    private static void send(ActiveMQConnectionFactory factory,
                             String delivery, String probeId) throws Exception {
        boolean persistent = switch (delivery) {
            case "persistent" -> true;
            case "nonpersistent" -> false;
            default -> throw new IllegalArgumentException(
                    "Use persistent or nonpersistent");
        };

        // Producer gửi trong JMS transaction và commit rõ ràng.
        try (JMSContext context =
                     factory.createContext(Session.SESSION_TRANSACTED)) {
            Queue queue = context.createQueue(QUEUE_NAME);
            TextMessage message = context.createTextMessage(
                    "probe=" + probeId + ";delivery=" + delivery);
            message.setStringProperty("probeId", probeId);

            JMSProducer producer = context.createProducer()
                    .setDeliveryMode(persistent
                            ? DeliveryMode.PERSISTENT
                            : DeliveryMode.NON_PERSISTENT)
                    .setTimeToLive(0L); // Không tự đặt TTL từ producer.
            producer.send(queue, message);
            context.commit();

            System.out.println("SENT " + probeId
                    + " JMSMessageID=" + message.getJMSMessageID());
        }
    }

    private static void browse(ActiveMQConnectionFactory factory)
            throws Exception {
        try (JMSContext context =
                     factory.createContext(Session.AUTO_ACKNOWLEDGE)) {
            Queue queue = context.createQueue(QUEUE_NAME);
            QueueBrowser browser = context.createBrowser(queue);
            int seen = 0;
            try {
                Enumeration<?> items = browser.getEnumeration();
                while (items.hasMoreElements()) {
                    Message message = (Message) items.nextElement();
                    String text = message instanceof TextMessage
                            ? ((TextMessage) message).getText()
                            : "<not text>";
                    System.out.println("QUEUED " + text
                            + " id=" + message.getJMSMessageID());
                    seen++;
                }
            } finally {
                browser.close();
            }
            System.out.println("BROWSED count=" + seen);
        }
    }

    private static void receive(ActiveMQConnectionFactory factory,
                                boolean commit) throws Exception {
        try (JMSContext context =
                     factory.createContext(Session.SESSION_TRANSACTED)) {
            Queue queue = context.createQueue(QUEUE_NAME);
            Message message = context.createConsumer(queue).receive(5000L);
            if (message == null) {
                System.out.println("QUEUE_EMPTY");
                context.rollback();
                return;
            }

            String text = message instanceof TextMessage
                    ? ((TextMessage) message).getText()
                    : "<not text>";
            System.out.println("RECEIVED " + text
                    + " redelivered=" + message.getJMSRedelivered());

            if (commit) {
                context.commit();
                System.out.println("COMMITTED: message was acknowledged");
            } else {
                context.rollback();
                System.out.println("ROLLED_BACK: message may redeliver");
            }
        }
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing environment variable " + name);
        }
        return value;
    }

    private static void usage() {
        System.out.println("Usage:");
        System.out.println("  send persistent|nonpersistent PROBE-ID");
        System.out.println("  browse");
        System.out.println("  receive-commit");
        System.out.println("  receive-rollback");
    }
}
```

**Lưu ý về bản chất thí nghiệm:**

- `send persistent` sử dụng `DeliveryMode.PERSISTENT` và `context.commit()` để chốt **JMS transaction gửi**. Điều này chưa phải bằng chứng broker đã đặt file ở volume mong muốn; ta cần test recreate.
- `browse` gọi `QueueBrowser`, không acknowledge. Vì vậy message đang chờ vẫn có thể tồn tại qua restart.
- `receive-commit` thực sự nhận rồi commit transaction tiêu thụ: message được ack/loại khỏi queue theo semantics, **không được kỳ vọng xuất hiện trở lại sau restart**.
- `receive-rollback` nhận nhưng rollback: broker có thể phân phối lại, có thể kèm delay theo cấu hình redelivery.
- Đoạn code không chạy consumer nền, không xử lý nghiệp vụ và không thay thế idempotency. Nó chỉ là **đầu dò về durability**.

### 5.3. Gửi và duyệt queue trước khi restart

Từ thư mục Maven lab, với các biến `BROKER_USER`, `BROKER_PASSWORD` đã đặt:

```bash
mvn -q compile exec:java '-Dexec.mainClass=demo.BrokerVolumeProbe' '-Dexec.args=send persistent P-001'

mvn -q compile exec:java '-Dexec.mainClass=demo.BrokerVolumeProbe' '-Dexec.args=browse'
```

Kết quả kỳ vọng: có dòng `SENT P-001` và `BROWSED count=1`, kèm payload `probe=P-001;delivery=persistent`. Không dùng `receive-commit` trước thử nghiệm restart nếu muốn chứng minh message còn chờ. Broker có thể tự tạo queue `lab.persistence.queue` nhờ setting `auto-create-queues` của cấu hình lab mặc định; trong môi trường đã khóa quyền auto-create, tạo trước queue **durable/anycast** qua công cụ quản trị phù hợp.

Mỗi lần thử với queue cũ đã chứa nhiều message, `BROWSED count` có thể lớn hơn 1. Hãy dùng `probeId` riêng cho mỗi vòng để truy dấu message và ghi lại ID trong kết quả; không cần xóa queue để thực hiện lại bài.

## 6. Thí nghiệm A — restart cùng container

Sau khi thấy `P-001` trong queue:

```bash
docker compose ps -q broker
docker compose restart broker
docker compose ps -q broker
docker compose logs --tail 50 broker
```

Chạy lại:

```bash
mvn -q compile exec:java '-Dexec.mainClass=demo.BrokerVolumeProbe' '-Dexec.args=browse'
```

Dự kiến `P-001` vẫn được duyệt thấy, do broker đọc lại state đã persist.

**Nhưng đây chưa phải phép thử volume đầy đủ.** `restart` vẫn giữ nguyên container và writable layer của nó. Một container được khởi tạo **không có named volume** nhưng ghi journal trong writable layer cũng có thể vượt qua thử nghiệm này. Vì thế cần tiếp tục **thí nghiệm B**.

**Nếu message không còn:** kiểm tra có consumer nào đã ack, message có TTL/expiry không, đã gửi persistent đúng chưa, nhật ký broker có lỗi journal hay không. Đừng quy kết ngay rằng `restart` đã tạo broker mới.

## 7. Thí nghiệm B — ép tạo container mới nhưng dùng cùng volume

Lấy ID hiện tại qua `docker compose ps -q broker`. Sau đó:

```bash
docker compose up -d --force-recreate broker
docker compose ps -q broker
docker compose logs --tail 50 broker
```

Đọc lại:

```bash
mvn -q compile exec:java '-Dexec.mainClass=demo.BrokerVolumeProbe' '-Dexec.args=browse'
```

**Quan sát quan trọng:**

1. Container ID **đổi** vì đã recreate.
2. `docker volume inspect artemis-volume-lab_broker_instance` vẫn chỉ ra **cùng named volume**.
3. `P-001` vẫn hiện trong kết quả browse.
4. Thông tin cấu hình của instance trước (bao gồm tài khoản được khởi tạo lần đầu) vẫn được dùng.

Đây là phép thử tốt hơn vì nó cho thấy data **không phụ thuộc vào writable layer của container cũ**. Nếu container mới không thể start do lỗi quyền ghi volume, broker có thể chưa hề khôi phục thành công; hãy xem log và xử lý permission trước khi đánh giá kết quả.

Có thể dùng `docker compose down` rồi `docker compose up -d` để kiểm tra thêm đường vòng đời khác. `down` xóa container/network của project, nhưng **mặc định không xóa named volume**. Trong lab này, `P-001` vẫn phải xuất hiện sau khi start lại, nếu các điều kiện persistence khác vẫn thỏa.

## 8. Thí nghiệm C — tạo broker mới bằng volume khác

Thí nghiệm này chứng minh ý nghĩa của cụm từ **“broker mới”**. Chỉ cần trỏ cùng image tới **một volume rỗng khác**: Artemis phải bootstrap instance khác. Không cần xóa volume trước đó để quan sát sự khác biệt.

Với Compose file đã có, thực hiện khi project `artemis-volume-lab` **đã dừng** để tránh xung đột cổng:

```bash
docker compose down

# -p ghi đè tên project của Compose.
# Project mới dùng named volume có prefix khác:
docker compose -p artemis-fresh-lab up -d
docker compose -p artemis-fresh-lab ps
docker volume ls
```

Vì volume khai báo là `broker_instance` nhưng project đã đổi tên, Docker Compose thường tạo volume `artemis-fresh-lab_broker_instance` mới. Cấu hình ở `environment` được dùng để bootstrap instance này, miễn volume ban đầu thực sự rỗng.

Bây giờ chạy:

```bash
mvn -q compile exec:java '-Dexec.mainClass=demo.BrokerVolumeProbe' '-Dexec.args=browse'
```

Kết quả kỳ vọng: `P-001` **không xuất hiện** trong broker mới. Thậm chí queue `lab.persistence.queue` có thể chưa tồn tại cho tới khi JMS client tạo/auto-create. **Điều đó không chứng minh dữ liệu cũ đã bị xóa**: nó vẫn ở volume `artemis-volume-lab_broker_instance` của project trước.

Trở về broker cũ:

```bash
docker compose -p artemis-fresh-lab down
docker compose up -d
mvn -q compile exec:java '-Dexec.mainClass=demo.BrokerVolumeProbe' '-Dexec.args=browse'
```

Nếu state cũ còn đúng và không có actor khác consume, `P-001` hiện lại vì Compose gắn volume cũ. Hai lần container mới chạy cùng image, cùng cổng, cùng username ban đầu **nhưng là hai broker instance khác nhau**. Khác biệt nằm ở **volume được gắn**, không nằm ở lệnh `restart` hay tên cổng.

> **Tại sao bài dùng project name thay vì xóa volume?** Đổi project tạo namespace volume riêng, cho phép so sánh hai instance mà không xóa dữ liệu cũ. Để làm đúng thí nghiệm, project mới và project cũ không chạy đồng thời trên cùng hai host port.

## 9. Thí nghiệm D — nhận, rollback, commit và kiểm tra sau restart

Dùng lại broker cũ có `P-001`. Thử nhận message nhưng **rollback**:

```bash
mvn -q compile exec:java '-Dexec.mainClass=demo.BrokerVolumeProbe' '-Dexec.args=receive-rollback'
mvn -q compile exec:java '-Dexec.mainClass=demo.BrokerVolumeProbe' '-Dexec.args=browse'
```

Kết quả: message thường vẫn trong queue hoặc được lên lịch redelivery; nếu có delay cấu hình, có thể chưa hiện ngay lập tức cho consumer. `JMSRedelivered` có thể cho biết message đã được phát lại. Lặp lại quá nhiều lần có thể khiến message chạm chính sách `max-delivery-attempts` và bị chuyển DLQ, nên chỉ làm một lần trong lab.

Sau đó:

```bash
mvn -q compile exec:java '-Dexec.mainClass=demo.BrokerVolumeProbe' '-Dexec.args=receive-commit'
mvn -q compile exec:java '-Dexec.mainClass=demo.BrokerVolumeProbe' '-Dexec.args=browse'

docker compose restart broker

mvn -q compile exec:java '-Dexec.mainClass=demo.BrokerVolumeProbe' '-Dexec.args=browse'
```

Nếu `P-001` đã được consumer nhận và commit, **không còn `P-001` ở queue** là kết quả đúng của broker đáng tin cậy. Volume phải giữ **cả thông tin gửi message lẫn trạng thái ack/xóa message**. “Có volume nhưng sau restart không thấy message” tự nó **không phải dấu hiệu mất dữ liệu**.

### 9.1. NON_PERSISTENT là thí nghiệm đối chứng

Gửi một message khác:

```bash
mvn -q compile exec:java '-Dexec.mainClass=demo.BrokerVolumeProbe' '-Dexec.args=send nonpersistent NP-001'
```

Đừng dùng trường hợp `NP-001` để kiểm chứng bảo đảm khôi phục. Theo ngữ nghĩa JMS, `NON_PERSISTENT` không yêu cầu broker bảo toàn message qua sự cố/restart; có thể thấy message tồn tại trong một số lần dừng/start thuận lợi, nhưng đó **không phải cam kết durability**. Giá trị của thí nghiệm này là phân biệt thiết lập **volume** với **delivery mode** và chính sách của broker.

### 9.2. Điều gì xảy ra với topic và durable subscription?

Với topic, producer `PERSISTENT` là một điều kiện, nhưng **subscriber thường** (non-durable) offline có thể bỏ lỡ event. Nếu cần backlog qua downtime, phải tạo durable subscription theo contract JMS, giữ định danh subscription (`clientID`/subscription name hoặc shared durable subscription tùy API và topology), và kiểm tra broker có lưu queue subscription thích hợp. Volume giúp state đó sống qua recreate; volume không tự biến subscriber không bền vững thành durable subscriber.

## 10. Thí nghiệm E — nhận biết lệnh xóa volume và cơ chế “reset” broker

Các lệnh dưới đây **khác nhau về mức độ xóa**:

```bash
docker compose stop                 # Chỉ dừng service
docker compose start                # Start container hiện hữu
docker compose down                 # Xóa container và network mặc định
docker compose down -v              # Xóa thêm volumes do Compose quản lý
```

**`docker compose down -v` có thể phá hủy toàn bộ journal/data của lab**. Chỉ dùng nếu bạn đã **chủ động muốn reset**, hiểu đúng tên project/volume, không có dữ liệu cần giữ và có backup thích hợp. Bài học không yêu cầu thực thi lệnh này.

Tương tự, đừng dùng `docker volume rm` hay lệnh dọn dẹp volume hàng loạt như `docker volume prune` trên máy có dữ liệu quan trọng nếu chưa kiểm tra toàn bộ volume sẽ bị ảnh hưởng. Docker không tự khôi phục message khi một named volume đã bị xóa mà không có bản sao lưu bên ngoài.

**Một trường hợp dễ gây nhầm lẫn:** Bạn dùng `docker run --rm` trên image Artemis mà **không chỉ định named volume**. Khi container kết thúc, Docker có thể loại bỏ container và anonymous volume gắn kèm theo cơ chế `--rm`. Lần chạy sau có thể bootstrap instance mới. Tên image không đổi nhưng trạng thái khác nhau.

**Một trường hợp khác:** Dùng Compose nhưng đổi thư mục chạy hoặc thay `COMPOSE_PROJECT_NAME`; nếu Compose project name mới và volume không đặt tên cố định, broker sẽ được cấp volume khác. Bằng chứng nên lấy từ **`docker inspect` Mounts và `docker volume inspect`**, không đoán theo tên container.

## 11. Cấu hình persistence của Artemis: volume đúng vẫn cần broker ghi đúng

Trong trường hợp file journal, một số setting liên quan có thể được nhìn thấy trong `/var/lib/artemis-instance/etc/broker.xml`. Ví dụ fragment **nằm bên trong phần `<core>` của cấu hình hiện hữu**, không phải một file XML hoàn chỉnh:

```xml
<persistence-enabled>true</persistence-enabled>

<!-- Các setting cần cân nhắc theo yêu cầu durability/hiệu năng. -->
<journal-datasync>true</journal-datasync>
<journal-sync-transactional>true</journal-sync-transactional>
<journal-sync-non-transactional>true</journal-sync-non-transactional>
```

Ý nghĩa:

- `persistence-enabled=true`: broker sử dụng cơ chế lưu trạng thái bền vững; đặt `false` sẽ bỏ khả năng lưu journal theo cách cần cho bài.
- `journal-datasync` và `journal-sync-*` kiểm soát hành vi đồng bộ ghi; thay đổi để “tăng tốc” có thể đánh đổi tính bền vững khi mất điện/host crash. Chọn theo tài liệu phiên bản thực tế và yêu cầu vận hành.
- `bindings-directory`, `journal-directory`, `paging-directory`, `large-messages-directory` có thể tùy biến. Khi đổi sang đường dẫn tuyệt đối ngoài `/var/lib/artemis-instance`, phải thiết kế mount khác tương ứng.
- Với journal mặc định, file có thể được cấp phát trước. Không suy số message đang chờ bằng kích thước thư mục `data/journal`; dùng management/JMS/metrics.

**Đừng chỉnh trực tiếp journal hoặc copy một phần journal khi broker đang ghi.** Dữ liệu gồm nhiều nhóm file và trạng thái liên kết. Việc backup/restore phải được thiết kế nhất quán.

### 11.1. Cấu hình cũng là một phần của broker instance

Image Artemis có cơ chế bootstrap: khi volume instance rỗng, entrypoint tạo instance và các file như `broker.xml`, cấu hình user/role. Khi mount lại volume cũ, broker dùng instance đã tồn tại. Bởi vậy:

- Đổi `ARTEMIS_USER` hay `ARTEMIS_PASSWORD` trong Compose sau lần chạy đầu có thể **không đổi** account của broker cũ.
- Đổi image từ phiên bản A sang B **không có nghĩa** mọi giá trị mặc định của image B tự ghi đè `broker.xml` trong volume.
- Đối với một số image Artemis, thư mục `etc-override` được hỗ trợ để cung cấp các file cấu hình tùy chỉnh; cần nắm rõ thời điểm entrypoint sao chép file và tác động lên instance hiện hữu trước khi triển khai.
- Nếu cần tạo instance mới thực sự, phải chỉ định một storage rỗng **khác** hoặc thực hiện quy trình reset có kiểm soát; đơn thuần `restart` không “làm mới” cấu hình khởi tạo.

Đây là lý do **quản lý state của broker và quản lý cấu hình** phải đi cùng nhau. Khi vận hành, nên theo dõi image digest, cấu hình đang áp dụng, phiên bản schema/client, tên volume, user chạy broker và lịch sử migration.

## 12. ActiveMQ Classic: cùng nguyên lý, khác thư mục và định dạng store

Artemis và Classic đều là message broker thuộc hệ sinh thái ActiveMQ nhưng khác triển khai. Với image Classic chính thức `apache/activemq` và dữ liệu mặc định tại `/opt/apache-activemq/data`, có thể dùng named volume như sau (một **Compose project riêng**, không chạy cùng Artemis nếu dùng chung cổng host):

```yaml
name: classic-volume-lab

services:
  classic:
    image: apache/activemq:latest
    ports:
      - "127.0.0.1:61616:61616"
      - "127.0.0.1:8161:8161"
    volumes:
      - classic_data:/opt/apache-activemq/data

volumes:
  classic_data:
```

Đây là mẫu tập trung vào mount. **Trước khi dùng trong hệ thống thật**, pin image tag/digest, xác minh đường dẫn `ACTIVEMQ_DATA` của image đã chọn, cấu hình authentication/authorization và xác định store thực tế (KahaDB hay JDBC). Image Classic có thể có cách bootstrap và đường dẫn cấu hình khác Artemis; không suy cấu trúc từ tên container.

Khác biệt đáng nhớ:

| Nội dung | ActiveMQ Artemis | ActiveMQ Classic |
|---|---|---|
| Image minh họa | `apache/artemis:2.57.0-alpine` | `apache/activemq:latest` |
| Mount minh họa | `/var/lib/artemis-instance` | `/opt/apache-activemq/data` |
| Dữ liệu lưu trên disk mặc định | Journal, bindings, paging, large messages | Thường KahaDB và dữ liệu liên quan |
| Config broker | Thường `etc/broker.xml` trong instance | Thường `conf/activemq.xml` |
| Định tuyến | Address + anycast/multicast + queue | JMS queue/topic và cơ chế destination Classic |
| Chuyển store giữa hai sản phẩm | Không copy trực tiếp journal để thay engine | Không đọc trực tiếp journal Artemis |

Với Classic, nếu chỉ gắn `data`, cấu hình nằm ngoài mount có thể **không được giữ** khi recreate. Vì thế phải phân biệt nhu cầu giữ **message store** và nhu cầu giữ **cấu hình tùy biến**. Nếu dùng JDBC store, đảm bảo DB và config liên quan được bảo toàn.

## 13. Cách chẩn đoán khi “restart xong mất message”

Đừng đoán nguyên nhân chỉ bằng cách nhìn queue trống. Làm tuần tự:

| Triệu chứng quan sát | Giả thuyết | Cách kiểm chứng an toàn |
|---|---|---|
| Sau `restart` message không còn | Consumer đã ack, TTL/expiry, DLQ, broker failure | Browse/management, consumer log, `JMSMessageID`/`probeId`, expiry/DLQ |
| Sau `--force-recreate` mất queue | Mount sai hoặc volume khác | `docker inspect` Mounts, `docker volume inspect`, project name |
| Volume có file nhưng queue không có message | Message đã ack; file journal được cấp phát sẵn | JMS QueueBrowser, queue metrics; không dựa vào `du -sh` |
| Đổi password trong Compose nhưng đăng nhập bằng mật khẩu mới thất bại | Instance đã tồn tại, bootstrap vars không được áp lại | Xem cấu hình security của instance được dùng; quản trị credential đúng cách |
| Khởi động container mới có cùng name nhưng queue trống | Container mới đang dùng instance rỗng | So sánh volume name/mount point, config, metadata instance |
| Broker không thể start khi gắn bind mount | UID/GID hoặc SELinux/file permission | Broker log, owner/mode của mount, chính sách host |
| Message queue còn nhưng nội dung large message lỗi | Mount không chứa đủ large-message store | Kiểm tra đường dẫn large messages, journal/paging config, backup |
| Topic subscriber offline không nhận được event | Non-durable subscriber hoặc subscription identity khác | Kiểm tra durable subscription, client ID, retention, routing |
| Message bị chuyển queue khác sau nhiều lần nhận | Redelivery/DLQ policy | Quan sát delivery count, DLQ, error log của consumer |
| Cùng volume nhưng broker báo lỗi journal/version | Hỏng file, lock, nâng cấp không tương thích | Dừng broker, giữ nguyên bản sao state, đọc log và quy trình migration |
| Hai broker cùng sử dụng storage không đúng thiết kế | Cạnh tranh lock, hỏng state hoặc startup thất bại | Kiểm tra topology/HA mode, mount, stop broker thứ hai |

### 13.1. Mẫu quy trình chẩn đoán tối thiểu

1. **Chứng minh đúng service**: `docker compose ps`, image/version, hostname, endpoint client đang dùng; tránh gửi đến broker khác ở cùng môi trường.
2. **Chứng minh đúng volume**: `docker inspect` Mounts có expected `Destination` và đúng tên volume hay host path.
3. **Chứng minh message được gửi bền vững**: sender báo commit, `JMSDeliveryMode=PERSISTENT`, broker có persistence đang bật, không có transaction bị rollback.
4. **Chứng minh message chưa được xử lý/xóa**: tắt các consumer nền, dùng QueueBrowser; xem TTL/expiry, DLQ, auto-delete queues và broker metrics.
5. **Chứng minh quá trình khôi phục**: theo dõi broker logs ở thời điểm start, xem lỗi permission/journal, chờ broker thực sự sẵn sàng rồi mới browse.
6. **Chứng minh không đổi broker**: so sánh project name, volume identity và các cấu hình instance; đừng chỉ so container name.

**Ví dụ nghiệp vụ:** Order Service gửi `ProcessOrder` với `DeliveryMode.PERSISTENT` vào queue có consumer chạy. Nếu consumer nhận, ghi DB rồi commit JMS, queue trống sau restart **là đúng**. Nếu consumer crash trước JMS commit, message có thể xuất hiện lại sau restart. Vì vậy business handler phải có `orderId`/`commandId` chống lặp; volume không giải quyết vấn đề idempotency.

## 14. Độ tin cậy thật sự của volume và giới hạn vận hành

Named volume chỉ giải quyết **vòng đời dữ liệu so với container**. Nó không tự cung cấp high availability, backup, replication hay chống mất dữ liệu khi host/volume hỏng.

### 14.1. Backup và khôi phục

- Sao lưu phải **nhất quán** giữa journal, bindings, paging, large messages và config. Tránh copy ngẫu nhiên trong khi broker đang ghi. Dùng phương án backup/snapshot được hỗ trợ hoặc đưa broker về trạng thái yên trước khi chụp bản sao phù hợp.
- Thực hành **restore vào môi trường cô lập** và chứng minh bằng JMS browse hoặc metrics; backup “có file” nhưng không khởi động được broker thì chưa đạt yêu cầu.
- Nếu dùng **JDBC store**, phải backup/restore database theo quy trình DB phù hợp, cùng với cấu hình broker cần thiết.
- Không gắn cùng một file journal volume vào **hai broker active** đồng thời nếu không có kiến trúc HA/shared-store và cơ chế lock được hỗ trợ, đã được cấu hình và kiểm thử chính thức.
- Theo dõi free space, inode, journal/paging growth, I/O latency, permission và filesystem health; disk đầy có thể gây block producer hoặc broker failure, ngay cả khi volume không bị xóa.

### 14.2. Trường hợp gây mất tính bền vững dù volume còn

- **Không persistent**: producer gửi `NON_PERSISTENT` hoặc server cấu hình `persistence-enabled=false`.
- **Consumer đã ack**: một tác vụ đã hoàn tất và broker dọn message khỏi queue.
- **Expiry/purge**: message TTL hết, queue bị purge, subscription không durable, hoặc policy xóa queue/address phù hợp.
- **Dữ liệu nằm ngoài mount**: journal đặt ở thư mục khác, chỉ mount `logs` hoặc `data` nhưng bỏ quên cấu hình/large-message store.
- **Thay đổi instance**: tên project thay đổi, volume mới, bind path khác, image bootstrap trên thư mục rỗng.
- **Thiếu bảo đảm durability cấp host**: journal sync, volume driver, filesystem, cloud disk và phần cứng có thể có các failure mode khác nhau.

### 14.3. Bảo mật trong lab và production

- Giới hạn port ở `127.0.0.1` cho lab; production nên đặt broker trong private network và dùng TLS cho kết nối phù hợp.
- Áp dụng authentication/authorization cho queue/topic, management console, JMX/Jolokia; mỗi service có quyền cần thiết, không dùng tài khoản admin chung cho mọi producer/consumer.
- Không lưu plaintext production secrets trong Compose, source code, output `docker compose config` hoặc backup không được mã hóa.
- Bảo vệ quyền truy cập volume: journal có thể chứa nội dung message, metadata vận hành, dữ liệu liên quan tới nghiệp vụ và cấu hình bảo mật.
- Với DLQ, đảm bảo dữ liệu nhạy cảm được quản lý như dữ liệu ban đầu; thông điệp lỗi vẫn có thể được lưu dài ngày.

### 14.4. Quan sát cần có

| Chỉ số / bằng chứng | Giúp trả lời |
|---|---|
| Container ID, image digest, Compose project | Đang restart hay recreate? Có đổi image không? |
| Volume name và mount destination | Container mới có đọc cùng instance không? |
| Broker version, startup/recovery log | Có lỗi recover journal, lock hoặc permission? |
| Queue message count / delivering count | Bao nhiêu message chờ và bao nhiêu đang được phát tới consumer? |
| Persistent send/commit, producer error | Sender có thực sự chốt việc gửi? |
| ACK/rollback/redelivery count | Message đã bị xóa hợp lệ hay đang chờ retry? |
| DLQ và expiry address metrics | Message đã được chuyển đi vì lỗi/timeout? |
| Disk/volume capacity và I/O | Có nguy cơ broker không ghi được journal? |

## 15. Bộ bài tập tự kiểm chứng

**Bài 1 — Chứng minh restart không đủ để test volume.** Giải thích vì sao container ID không đổi sau `docker compose restart`. Một broker không gắn named volume nhưng dùng writable layer sẽ có thể vượt qua test này theo cơ chế nào?

**Đáp án gợi ý:** `restart` chỉ restart process trong container cũ; writable layer còn tồn tại. Bài kiểm thử quyết định phải bao gồm `--force-recreate` hoặc `down` rồi `up`, cùng quan sát volume ID và QueueBrowser.

**Bài 2 — Hai broker có cùng port, cùng image.** Project A gửi `P-001`, project B dùng tên project khác và volume khác nên thấy queue trống. Có được kết luận project A mất dữ liệu không?

**Đáp án gợi ý:** Không. Cần trở lại project A, mount lại volume A và browse. Tên host port giống nhau vì hai project chạy lần lượt không chứng minh hai broker dùng cùng state.

**Bài 3 — Nêu đủ điều kiện để `P-001` còn sau recreate.**

**Đáp án gợi ý:** Sender gửi `PERSISTENT` và commit; broker bật persistence, journal ghi thành công; đúng volume chứa đủ state được gắn lại; message chưa ack/expiry/purge/DLQ; broker/version/config cho phép phục hồi; không có consumer khác tiêu thụ trong thời gian test.

**Bài 4 — Vì sao `receive-commit` làm queue trống qua restart lại là dấu hiệu tốt?**

**Đáp án gợi ý:** ACK/commit là trạng thái bền vững của quá trình tiêu thụ; broker phải nhớ message đã hoàn tất để không phát lại sai. Không còn message là kết quả đúng sau khi xử lý thành công.

**Bài 5 — Mật khẩu cũ vẫn hoạt động sau khi đã đổi `ARTEMIS_PASSWORD` trong Compose, dù container ID mới. Giải thích.**

**Đáp án gợi ý:** Biến môi trường dùng cho bootstrap instance ban đầu; volume cũ giữ các file cấu hình tài khoản. Recreate container không tạo lại instance. Cần thay đổi credential ở cơ chế quản trị của broker chứ không xóa volume để “sửa password”.

**Bài 6 — Một team muốn share volume journal giữa hai broker đang chạy để tăng throughput. Có đúng không?**

**Đáp án gợi ý:** Không với cấu hình standalone: cùng truy cập một journal có thể tranh lock, khởi động thất bại hoặc hỏng dữ liệu. Cần thiết kế cluster, replication hoặc shared-store HA theo mô hình broker hỗ trợ, với cơ chế quản lý failover và fencing thích hợp.

### 15.1. Checklist hoàn thành lab

- [ ] Compose khai báo named volume trỏ tới **`/var/lib/artemis-instance`**.
- [ ] `docker inspect` xác nhận đúng `Type=volume` và `Destination`.
- [ ] Gửi `P-001` ở chế độ `PERSISTENT`, commit thành công và browse thấy.
- [ ] `docker compose restart broker` xong vẫn thấy `P-001`.
- [ ] `--force-recreate` đổi container ID nhưng dùng cùng volume, vẫn thấy `P-001`.
- [ ] Dùng project name khác tạo volume mới, không thấy `P-001`; quay về volume cũ lại thấy.
- [ ] `receive-rollback` không xóa kết quả nghiệp vụ; `receive-commit` làm message rời queue đúng ngữ nghĩa.
- [ ] Phân biệt được message mất vì ACK/TTL/expiry/DLQ với volume/broker bị thay.
- [ ] Biết các lệnh reset mang tính phá hủy và quy trình backup/restore trước khi thao tác.

## 16. Tóm tắt trọng tâm

**Volume giữ broker state qua vòng đời container, nhưng không tự bảo đảm delivery/processing đúng trong mọi tình huống.** Phân biệt các thực thể bằng ba câu hỏi thực dụng:

1. **Container có được tạo lại hay chỉ restart process?** Xem container ID và hành vi `restart`/`recreate`.
2. **Broker đang dùng lại đúng state cũ không?** Xem volume name, mount destination, cấu hình instance và dấu vết journal.
3. **Message có lý do hợp lệ để không còn ở queue không?** Xem delivery mode, JMS transaction/ack, consumer, TTL/expiry, redelivery/DLQ và broker persistence.

Một người vận hành tốt có thể **chứng minh** ba câu trả lời trên bằng `docker inspect`, `docker volume inspect`, broker log và JMS QueueBrowser. Khi làm được, bạn sẽ không nhầm **“tạo container mới”** với **“tạo broker mới”**, và biết cách giữ backlog quan trọng khi triển khai lại một ActiveMQ broker.

## 17. Tài liệu tham khảo chính thức

- [Apache Artemis — Docker: official image, environment, instance mapping](https://artemis.apache.org/components/artemis/documentation/latest/docker.html).
- [Apache Artemis — Using the Server: instance `etc`/`data`](https://artemis.apache.org/components/artemis/documentation/latest/using-server.html).
- [Apache Artemis — Persistence: journal, bindings, paging, JDBC store](https://artemis.apache.org/components/artemis/documentation/latest/persistence.html).
- [Apache Artemis — Address Settings: auto-create và auto-delete queue](https://artemis.apache.org/components/artemis/documentation/latest/address-settings.html).
- [Apache Artemis — Client Classpath: Maven Jakarta client](https://artemis.apache.org/components/artemis/documentation/latest/client-classpath.html).
- [Apache ActiveMQ Classic — Official Docker Image](https://activemq.apache.org/components/classic/documentation/docker-image).
- [Docker Docs — Volumes](https://docs.docker.com/engine/storage/volumes/) và [Docker Compose — `down`](https://docs.docker.com/reference/cli/docker/compose/down/).
