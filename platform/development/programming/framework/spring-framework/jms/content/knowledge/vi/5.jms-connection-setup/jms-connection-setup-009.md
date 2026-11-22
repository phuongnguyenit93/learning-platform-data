# Kiểm tra kết nối và quyền gửi nhận bằng thí nghiệm tối thiểu

> **Chủ đề:** Thiết lập kết nối – Spring Framework JMS. Bài này xây dựng một phép thử độc lập để xác nhận kết nối JMS, quyền gửi (`send`) và quyền nhận (`consume`) trên **một queue thử nghiệm đã xác định**. Kết quả là các tín hiệu quan sát được, giúp phân biệt lỗi mạng, xác thực, phân quyền, định tuyến và timeout.

## 1. Câu hỏi cần được chứng minh

Ứng dụng Spring Boot khởi động thành công và tạo được bean `ConnectionFactory` có nghĩa là đã gửi/nhận message được chưa? **Chưa.** Phải kiểm tra theo các lớp độc lập:

| Lớp | Hành động kiểm tra | Kết luận hợp lệ | Điều chưa chứng minh |
| --- | --- | --- | --- |
| Mạng | Kết nối TCP đến host/port của broker | Cổng đích truy cập được tại thời điểm thử | Giao thức JMS, TLS, user, quyền |
| Kết nối JMS | `createConnection()`, `createSession()` và `start()` | Client thực hiện được bước setup JMS với cấu hình hiện tại | Quyền `send` và `consume` |
| Gửi | `MessageProducer.send(...)` không ném lỗi | Thao tác gửi được provider chấp nhận theo hợp đồng áp dụng | Có consumer đọc được hoặc xử lý nghiệp vụ thành công |
| Nhận | `MessageConsumer.receive(timeout)` trả đúng `TextMessage` | User hiện tại nhận được message mang ID thử từ đúng queue | Đã commit database, xử lý exactly-once |
| Cả hai quyền | Một lần `send → receive` đúng ID | Tài khoản thử dùng được hai đường trên queue này | User khác hoặc môi trường khác có cùng quyền |

Đích cuối là **một chứng cứ có thể lặp lại** với danh tính, broker, queue, mã thử và kết quả từng giai đoạn. Không dùng một phép thử thành công để khẳng định hệ thống sẽ luôn khỏe hoặc mọi quyền đã được cấu hình chính xác.

### Các kết quả mong muốn

- `CONNECT_OK`: setup JMS đã hoàn thành.
- `SEND_OK`: gửi message thử đã hoàn thành mà không báo lỗi.
- `RECEIVE_OK`: nhận được **đúng** message và body mong đợi.
- `ROUNDTRIP_OK`: cùng một tài khoản gửi và nhận thành công.
- `RECEIVE_TIMEOUT`: không nhận được message phù hợp trong 5 giây; **không tự động đồng nghĩa thiếu quyền**.
- `JMS_FAIL phase=...`: lỗi JMS xảy ra trong giai đoạn ghi kèm theo exception class và error code, cần đối chiếu broker log.

## 2. Chuẩn bị môi trường thử nghiệm

Dùng **Java 17+, Spring Boot 3.3.x, Jakarta Messaging 3.1 và ActiveMQ Artemis**. Spring Boot tự cấu hình `ConnectionFactory` từ các thuộc tính `spring.artemis.*`; phép thử dùng API JMS thuần bên trên factory đó để nhìn rõ bước nào có lỗi.

### 2.1. Broker local có thể khởi động nhanh

Nếu đã cài Docker, có thể dùng image Artemis được hướng dẫn trong tài liệu chính thức:

~~~bash
docker run --detach --name jms-probe-broker --rm -p 61616:61616 -p 8161:8161 apache/artemis:latest-alpine
~~~

Lệnh là một dòng nên chạy được trong Bash và PowerShell. Đợi broker sẵn sàng trước khi chạy client:

~~~bash
docker logs jms-probe-broker
~~~

- `61616`: port messaging cho ứng dụng.
- `8161`: console quản trị tại `http://localhost:8161`.
- Image demo mặc định dùng thông tin quản trị `artemis/artemis`. **Chỉ dùng trong môi trường local cách ly**; không giữ thông tin mặc định khi triển khai hạ tầng chia sẻ.
- Sau khi thử, dùng `docker stop jms-probe-broker` để dừng container test. Vì có `--rm` và không gắn volume dữ liệu, container sẽ bị xóa khi dừng.

Nếu tổ chức đã có broker thử nghiệm, không cần chạy Docker. Khi đó ghi lại hostname, port, TLS, môi trường và vai trò của user được cấp; tránh dùng nhầm broker production.

### 2.2. Queue riêng biệt

Chọn queue `demo.probe` theo kiểu point-to-point/**anycast**. Với một số cấu hình Artemis, address/queue có thể được auto-create khi client gửi. Để **kiểm tra quyền** chính xác, tốt nhất nhờ quản trị viên tạo **sẵn** address và queue:

~~~text
Artemis broker
  address: demo.probe
  routing: ANYCAST
  queue:   demo.probe
~~~

Chính sách này giúp phân biệt thiếu quyền `send`/`consume` với thiếu quyền `createAddress` hoặc `createDurableQueue`. `session.createQueue("demo.probe")` trong code tạo đối tượng `Queue` ở phía JMS; nó không phải bằng chứng chắc chắn rằng tài nguyên thực tế đã được tạo và có quyền truy cập trên broker.

**Chỉ thao tác với queue thử.** Nếu dùng queue thật rồi thực hiện `receive()`, thử nghiệm có thể xác nhận/tiêu thụ message nghiệp vụ. Queue thử nên có quyền truy cập, dung lượng và chính sách dọn dữ liệu rõ ràng.

### 2.3. Danh tính và quyền trên broker

Với Artemis, các quyền quan trọng là `send` trên address và `consume` trên queue; ngoài ra còn quyền tạo/xóa address/queue. Cấu hình role, wildcard và policy cụ thể có thể thay đổi theo broker.

| Danh tính minh họa | Quyền kỳ vọng trên `demo.probe` | Cách kiểm chứng |
| --- | --- | --- |
| `probe-both` | `send`, `consume` | `roundtrip` phải PASS |
| `probe-writer` | Chỉ `send` | `send` PASS; `receive` phải bị từ chối theo policy |
| `probe-reader` | Chỉ `consume` | `receive` PASS với message tồn tại; `send` phải bị từ chối |
| `probe-none` | Không có quyền destination | Có thể connect nếu xác thực hợp lệ; send/receive phải bị từ chối |
| Username/password sai | Không xác thực | Connection/session setup phải lỗi |

Các tài khoản này là **ví dụ về vai trò cần được quản trị viên cấp trước**, không phải user có sẵn trong Docker image. Thử nghiệm với admin thành công chỉ chứng minh admin có đường gửi/nhận, **không** chứng minh quyền của hai tài khoản ứng dụng thực tế.

## 3. Thiết kế thí nghiệm

Chương trình có bốn chế độ:

~~~text
connect:
  ConnectionFactory -> Connection -> Session -> start()
  -> CONNECT_OK

send (có probeId):
  Connection -> Session -> MessageProducer
  -> TextMessage có property probeId
  -> demo.probe -> SEND_OK

receive (dùng cùng probeId):
  Connection -> Session -> MessageConsumer
  -> selector: probeId = '...'
  -> receive(5000 ms)
  -> RECEIVE_OK hoặc RECEIVE_TIMEOUT/JMS_FAIL

roundtrip:
  connect -> send -> receive đúng probeId + body -> ROUNDTRIP_OK
~~~

**Vì sao dùng `probeId` và JMS selector?** Queue thử có thể chứa message từ lần kiểm tra trước. Mỗi lần tạo một ID duy nhất, gắn nó thành string property và lọc bằng `probeId = 'id'`. Chỉ khi message có đúng ID và body, chương trình mới in `RECEIVE_OK`. Điều này hạn chế nhận nhầm message, dù vẫn nên dùng **queue riêng** và không chia sẻ tùy tiện với các job khác.

**Vì sao dùng timeout 5 giây?** Thí nghiệm cần kết thúc có hạn định. Nếu gọi `receive()` không timeout, một queue rỗng có thể làm ứng dụng chờ vô hạn. Timeout 5 giây hợp lý để minh họa tại máy local, nhưng môi trường WAN/broker quá tải có thể cần giá trị khác.

**Vì sao tách các mode?** Khi cần thử quyền `send` và `consume` bằng **hai user khác nhau**, ta gửi với user writer rồi chạy lượt receive bằng user reader với cùng ID. Round-trip trên một user không thay thế được kiểm thử quyền của user khác.

## 4. Tạo project Java 17 + Spring Boot

Cấu trúc dự án chạy độc lập:

~~~text
jms-permission-probe/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/JmsProbeApplication.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-permission-probe'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: "tcp://localhost:61616"
    user: "artemis"
    password: "artemis"
  jms:
    cache:
      enabled: false
~~~

Ở đây credential là **thông tin demo mặc định của Docker image**, không phải secret production. Khi thử tài khoản hạn chế, đặt các biến môi trường `SPRING_ARTEMIS_USER`, `SPRING_ARTEMIS_PASSWORD` để ghi đè cấu hình tương ứng (Spring Boot hỗ trợ externalized configuration). Nếu cần kiểm tra broker ở host khác, thay `SPRING_ARTEMIS_BROKER_URL`. Không commit mật khẩu của môi trường chia sẻ vào source code/YAML. Cờ `mode: native` tránh nhầm với broker embedded; tắt `spring.jms.cache` chỉ để kiểm tra kết nối riêng ở demo, không phải cấu hình hiệu năng production.

### 4.1. File Java đầy đủ

`src/main/java/demo/JmsProbeApplication.java`:

~~~java
package demo;

import java.util.List;
import java.util.UUID;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JmsProbeApplication implements ApplicationRunner {

    private static final String QUEUE_NAME = "demo.probe";
    private static final long RECEIVE_TIMEOUT_MS = 5_000L;
    private static final long TTL_MS = 300_000L;

    private final ConnectionFactory connectionFactory;

    public JmsProbeApplication(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public static void main(String[] args) {
        SpringApplication.run(JmsProbeApplication.class, args);
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        String mode = option(args, "probe.mode", "roundtrip");
        if (!List.of("connect", "send", "receive", "roundtrip")
                .contains(mode)) {
            throw new IllegalArgumentException(
                    "Unsupported probe.mode: " + mode);
        }

        if ("receive".equals(mode)
                && !hasValue(args, "probe.id")) {
            throw new IllegalArgumentException(
                    "receive mode requires --probe.id=<id>");
        }

        String probeId = option(
                args, "probe.id", UUID.randomUUID().toString());
        if (!probeId.matches("[A-Za-z0-9._-]{1,80}")) {
            throw new IllegalArgumentException(
                    "probe.id must contain 1..80 safe characters");
        }

        System.out.println("MODE=" + mode);
        System.out.println("PROBE_ID=" + probeId);

        String phase = "CONNECT";

        try (Connection connection =
                     connectionFactory.createConnection();
             Session session =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE)) {

            // Classic JMS: start cho phép broker giao message cho consumer.
            connection.start();
            System.out.println("CONNECT_OK");

            if ("connect".equals(mode)) {
                return;
            }

            Queue queue = session.createQueue(QUEUE_NAME);

            if ("send".equals(mode) || "roundtrip".equals(mode)) {
                phase = "SEND";
                try (MessageProducer sender =
                             session.createProducer(queue)) {
                    TextMessage message = session.createTextMessage(
                            "probe:" + probeId);
                    message.setStringProperty("probeId", probeId);
                    sender.send(message, DeliveryMode.PERSISTENT, 4, TTL_MS);
                    System.out.println("SEND_OK");
                }
            }

            if ("receive".equals(mode) || "roundtrip".equals(mode)) {
                phase = "RECEIVE";
                String selector = "probeId = '" + probeId + "'";

                try (MessageConsumer receiver =
                             session.createConsumer(queue, selector)) {
                    Message received =
                            receiver.receive(RECEIVE_TIMEOUT_MS);
                    if (received == null) {
                        System.out.println("RECEIVE_TIMEOUT");
                        throw new IllegalStateException(
                                "No matching message within 5000 ms");
                    }
                    if (!(received instanceof TextMessage text)) {
                        throw new IllegalStateException(
                                "Expected TextMessage");
                    }
                    String body = text.getText();
                    if (!("probe:" + probeId).equals(body)) {
                        throw new IllegalStateException(
                                "Unexpected body for probeId");
                    }
                    System.out.println("RECEIVE_OK body=" + body);
                }
            }

            if ("roundtrip".equals(mode)) {
                System.out.println("ROUNDTRIP_OK");
            }

        } catch (JMSException failure) {
            System.err.println(
                    "JMS_FAIL phase=" + phase
                    + " type=" + failure.getClass().getSimpleName()
                    + " errorCode=" + failure.getErrorCode());
            throw failure;
        }
    }

    private static boolean hasValue(
            ApplicationArguments args, String name) {
        List<String> values = args.getOptionValues(name);
        return values != null && !values.isEmpty()
                && values.get(0) != null
                && !values.get(0).isBlank();
    }

    private static String option(
            ApplicationArguments args,
            String name,
            String fallback) {
        List<String> values = args.getOptionValues(name);
        return values == null || values.isEmpty()
                ? fallback : values.get(0);
    }
}
~~~

**Giải thích chính xác các phần:**

1. `SpringApplication.run` khởi tạo Spring context; Spring Boot đưa `ConnectionFactory` của Artemis vào constructor. Nếu broker chưa kết nối, bean được tạo không bảo đảm mọi quyền JMS đã được xác minh.
2. Trong `try-with-resources`, code tạo `Connection` và `Session.AUTO_ACKNOWLEDGE`. Nếu bước nào lỗi, ngoại lệ được báo theo `phase`. `connection.start()` chỉ ảnh hưởng delivery đến consumer; gửi JMS không bắt buộc connection phải started, nhưng ở đây gọi start để kiểm tra đường setup/receiving.
3. `connect` dừng sau `CONNECT_OK` và **không tạo producer/consumer**. Do đó nó không xác nhận quyền trên destination.
4. `send` tạo `TextMessage` với body `probe:<ID>` và property `probeId`. Giá trị `DeliveryMode.PERSISTENT`, priority `4`, TTL `300_000 ms` được truyền vào lần gửi cụ thể.
5. `receive` dựng JMS selector từ ID đã validate chỉ gồm chữ/số/dấu chấm/gạch dưới/gạch ngang; không chấp nhận quote hoặc ký tự làm thay đổi biểu thức selector.
6. `receive(RECEIVE_TIMEOUT_MS)` trả message hoặc `null` sau timeout. Sau khi nhận, code đối chiếu **kiểu TextMessage và body**, không chỉ tin vào bất kỳ message nào trên queue.
7. `roundtrip` thực hiện hai pha trên cùng connection và session rồi in `ROUNDTRIP_OK` sau khi cả hai hoàn tất.
8. `try-with-resources` đóng producer, consumer, session và connection sau lượt thử kể cả khi lỗi. Không chia sẻ `Session` này đồng thời giữa nhiều thread.

Ví dụ là **một chương trình runnable**, không phải đoạn pseudo-code. Tên public class là `JmsProbeApplication` khớp với file `JmsProbeApplication.java`. Cần Gradle/dependencies/broker để chạy; `javac JmsProbeApplication.java` đơn lẻ không có classpath Spring/JMS sẽ thất bại.

## 5. Chạy lần lượt từng phép thử

Dùng Gradle đã cài hoặc Gradle wrapper nếu project có sẵn. Thư mục làm việc là root `jms-permission-probe`.

### 5.1. Kiểm tra kết nối

~~~bash
gradle bootRun --args="--probe.mode=connect --probe.id=connect-001"
~~~

Nếu xác thực/setup thành công, phần output **do ứng dụng in ra**:

~~~text
MODE=connect
PROBE_ID=connect-001
CONNECT_OK
~~~

Các dòng log của Spring Boot và Artemis có thể xuất hiện thêm. Nếu broker chưa chạy/sai credentials, thay vì `CONNECT_OK`, bạn sẽ nhận lỗi trong bước setup. Một số provider có thể trì hoãn thao tác mạng; vì vậy `CONNECT_OK` chỉ là dấu mốc đã vượt qua các thao tác setup thực sự được gọi, không phải kiểm tra quyền destination.

### 5.2. Kiểm tra round-trip cùng tài khoản

~~~bash
gradle bootRun --args="--probe.mode=roundtrip --probe.id=trial-001"
~~~

Với queue mới/trống, broker hoạt động và user có quyền gửi + nhận, các dòng ứng dụng là:

~~~text
MODE=roundtrip
PROBE_ID=trial-001
CONNECT_OK
SEND_OK
RECEIVE_OK body=probe:trial-001
ROUNDTRIP_OK
~~~

Đây là ví dụ output có ID cố định nên dễ đối chiếu. Trong các lần chạy thực tế, hãy đổi `trial-001` thành ID mới, hoặc bỏ tham số `probe.id` ở mode `roundtrip` để chương trình tự sinh UUID. Mỗi lần thử nên có một mã riêng, tránh message cũ trùng ID.

Nếu có `SEND_OK` nhưng sau đó `RECEIVE_TIMEOUT`, đừng kết luận ngay tài khoản không có quyền: hãy kiểm tra routing, consumer, selector, queue depth, message expiry và broker audit log.

### 5.3. Kiểm tra quyền gửi bằng user chuyên dụng

Đặt user/pasword của `probe-writer` theo secret source, ví dụ trên Windows PowerShell:

~~~powershell
$env:SPRING_ARTEMIS_USER = "probe-writer"
$env:SPRING_ARTEMIS_PASSWORD = "<secret-from-secure-store>"
gradle bootRun --args="--probe.mode=send --probe.id=acl-001"
~~~

Khi có `send` và queue đã tồn tại:

~~~text
MODE=send
PROBE_ID=acl-001
CONNECT_OK
SEND_OK
~~~

Output này chứng minh **tài khoản writer** gọi send thành công. Nó chưa chứng minh quyền consume. Nếu gửi thành công nhưng receiver chưa chạy, message có thể còn trong queue cho đến khi được nhận hoặc hết TTL (5 phút). Không dùng tên ID lặp lại giữa các lượt thử.

### 5.4. Kiểm tra quyền nhận bằng user riêng

Thay credentials bằng user `probe-reader` trong cùng shell hoặc một shell riêng, rồi nhận sớm hơn 5 phút sau bước send:

~~~powershell
$env:SPRING_ARTEMIS_USER = "probe-reader"
$env:SPRING_ARTEMIS_PASSWORD = "<secret-from-secure-store>"
gradle bootRun --args="--probe.mode=receive --probe.id=acl-001"
~~~

Nếu user có `consume` và message đúng ID còn tồn tại:

~~~text
MODE=receive
PROBE_ID=acl-001
CONNECT_OK
RECEIVE_OK body=probe:acl-001
~~~

Không chạy mode `receive` nhiều lần với cùng ID rồi kỳ vọng đều PASS: lần nhận thành công có thể đã xác nhận và tiêu thụ message. Nếu nhận lần hai bị timeout, đó thường là hành vi bình thường của queue đã hết message phù hợp.

### 5.5. Kiểm tra trường hợp phải bị từ chối

Trên broker test có cấu hình phân quyền rõ ràng, thử:
- `probe-writer` chạy `receive` với một ID có message đang chờ: policy phải từ chối consume, thường bằng exception hoặc broker audit event.
- `probe-reader` chạy `send`: policy phải từ chối quyền send.
- Một user hợp lệ không có quyền destination chạy cả `send` và `receive`: kiểm tra chính sách thực tế của broker.
- Username/password sai chạy `connect`: authentication phải thất bại.

Các thử nghiệm âm tính có thể trả `JMSSecurityException` hoặc `JMSException` được provider bọc với mã lỗi riêng. **Không khóa kỳ vọng vào một chuỗi exception duy nhất.** Đối chiếu broker security log để biết request bị deny vì quyền nào. `RECEIVE_TIMEOUT` có thể do thiếu message, sai ID hoặc mạng chậm; bản thân timeout **không chứng minh** policy deny.

## 6. Đọc kết quả một cách có kỷ luật

~~~text
             +-----------------------+
             | TCP đến broker mở?    |
             +-----------+-----------+
                         |
          NO: kiểm tra host, port, firewall, Docker
                         |
                        YES
                         v
             +-----------------------+
             | CONNECT_OK ?          |
             +-----------+-----------+
                         |
          NO: kiểm tra TLS, credentials, protocol, logs
                         |
                        YES
                         v
             +-----------------------+
             | SEND_OK ?             |
             +-----------+-----------+
                         |
          NO: kiểm tra send role, address/queue provisioning
                         |
                        YES
                         v
             +-----------------------+
             | RECEIVE_OK ?          |
             +-----------+-----------+
                         |
          NO: selector, TTL, queue depth, consume role,
              competing consumer, auth log, timeout
                         |
                        YES
                         v
             +-----------------------+
             | ROUNDTRIP_OK          |
             +-----------------------+
~~~

Chạy một kiểm tra TCP (Windows PowerShell):

~~~powershell
Test-NetConnection localhost -Port 61616
~~~

`TcpTestSucceeded: True` chỉ chứng minh route TCP có thể kết nối; nó không thực hiện bắt tay JMS hoặc xác thực/ủy quyền. Nếu broker đang trong container, còn cần kiểm tra port mapping và Docker logs. Nếu broker dùng TLS, client cấu hình `tcp://` không phù hợp phải được sửa ở transport trước khi thử permission.

### Phân tích vài trường hợp khó

**`CONNECT_OK` nhưng `SEND` báo lỗi:** Kiểm tra address security-setting, role `send`, broker queue provisioning, namespace. Nếu address/queue chưa được tạo và broker không cho auto-create, thiếu quyền `createAddress` hoặc `createDurableQueue` có thể gây lỗi trước bước gửi. Tạo trước queue để cô lập phép đo.

**`SEND_OK` nhưng `receive(timeout)` trả `null`:** Xác minh message có thực sự được route vào `demo.probe`, có property `probeId` đúng String/value, chưa hết TTL, không bị consumer khác nhận và connection đã start. Sau đó xem broker log để kết luận permission. Không tăng timeout vô hạn.

**`RECEIVE_OK` với user admin, nhưng ứng dụng thật không nhận:** So sánh principal, destination, selector, listener container start, concurrency, transaction manager, broker URL và Spring profiles của **ứng dụng thật**. Hai phiên đăng nhập khác nhau không có nghĩa quyền giống nhau.

**`JMSSecurityException` xảy ra khi tạo consumer:** Đây là dấu hiệu mạnh về auth/authorization; kiểm tra policy áp dụng, principal được gửi đến broker, đặc biệt khi dùng login module hoặc wildcard. Một số provider có thể thông báo lỗi ở thao tác khác nhau (tạo consumer hoặc receive), không áp đặt vị trí lỗi như hợp đồng chung.

**Có nhiều broker/cluster:** Khai báo host/port đúng chưa đủ nếu load balancer dẫn sang node khác hoặc môi trường dùng HA/failover; ghi nhận instance và quan sát queue phía broker quản trị. Cùng tên `demo.probe` ở hai instance khác nhau vẫn là hai destination khác nhau.

**Dùng `@JmsListener`:** Listener có thể được Spring quản lý, tự start và có cấu hình transaction/concurrency riêng. Raw probe giúp khoanh vùng quyền tại JMS trước; sau khi nó PASS mà listener lỗi, hãy chuyển sang kiểm tra cấu hình container/converter/handler. Không tự ý đóng connection dùng chung của Spring để “reset” khi đang test.

## 7. Quyền Artemis và nguyên tắc least privilege

Apache ActiveMQ Artemis phân quyền theo address/queue. Những quyền cần phân biệt:

| Quyền Artemis | Ý nghĩa trong thử nghiệm |
| --- | --- |
| `send` | Cho phép gửi message đến address |
| `consume` | Cho phép nhận từ queue gắn với address |
| `createAddress` | Tạo address khi chưa tồn tại |
| `createDurableQueue` | Tạo durable queue |
| `createNonDurableQueue` | Tạo non-durable queue |
| `browse` | Có thể duyệt message mà không tiêu thụ, không thay thế consume |
| `manage` | Tác vụ quản trị, không nên cấp rộng cho app chỉ cần gửi/nhận |

Một tài khoản chỉ có quyền `send` **không mặc nhiên** có quyền `consume`. Một role có quyền `browse` cũng không đồng nghĩa được tiêu thụ. Policy có wildcard và rule cụ thể; Artemis dùng rule match cụ thể nhất, vì vậy không giả định mọi quyền từ wildcard được cộng dồn. Quản trị viên cần đối chiếu chính xác security-setting với địa chỉ `demo.probe`.

Đối với ứng dụng tách producer và consumer, cấp quyền theo chức năng. Nếu service A chỉ phát sự kiện, service A không cần quyền consume toàn bộ queue. Nếu worker B chỉ đọc queue, B không cần quyền send đến mọi address. Cách làm này vừa giúp kiểm thử rõ, vừa giới hạn rủi ro khi một dịch vụ bị chiếm quyền.

**Không sửa broker security policy chỉ để làm probe PASS** nếu chưa xác định hành vi kỳ vọng. Kết quả đúng đôi khi chính là `ACCESS_DENIED` cho user không có quyền.

## 8. Các giới hạn của thí nghiệm

Đây là **smoke test** cho kết nối và authorization, chưa phải bài kiểm tra đầy đủ về độ tin cậy:

- `SEND_OK` không chứng minh business handler nhận message hoặc cập nhật cơ sở dữ liệu.
- `RECEIVE_OK` không chứng minh retry, transaction, DLQ, idempotency hay exactly-once side effect.
- `DeliveryMode.PERSISTENT` không chứng minh broker lưu được message qua mọi sự cố; còn storage, retention, TTL, transaction và broker HA.
- TTL 5 phút tránh giữ message thử quá lâu, nhưng provider có thể áp dụng expiry policy riêng; expired message có thể được di chuyển vào expiry address thay vì xóa ngay.
- Timeout 5 giây chỉ phù hợp kiểm tra nhanh; hệ thống tải nặng hoặc truyền qua WAN có thể cần điều kiện đo khác.
- Một lượt thử thành công không kiểm tra failover/reconnect, TLS rotation, connection pooling, nhiều consumer hay SLA production.
- `AUTO_ACKNOWLEDGE` dùng cho demo; khi cần bảo đảm message và cập nhật database nhất quán, cần test transaction/ack và cơ chế chống xử lý trùng riêng.

Việc chạy smoke test liên tục vào queue đang phục vụ khách hàng cũng có thể gây ảnh hưởng: tạo message thừa, dùng quota và làm nhiễu giám sát. Nếu muốn giám sát tổng hợp thường xuyên, sử dụng **dedicated synthetic queue**, giới hạn tần suất và retention, có quyền phù hợp.

## 9. Checklist nghiệm thu có thể kiểm toán

- [ ] Xác định đúng tên broker/host/port, môi trường và giao thức/TLS.
- [ ] Đã sử dụng queue riêng `demo.probe` hoặc queue thử được quản trị cho phép.
- [ ] Đã tạo trước queue khi muốn cô lập quyền gửi/nhận khỏi quyền tạo đích.
- [ ] Đã ghi nhận principal/role của mỗi lần chạy; không in mật khẩu.
- [ ] `CONNECT_OK` xuất hiện sau tạo connection/session và start thành công.
- [ ] `SEND_OK` xuất hiện sau lần gửi message có `probeId` duy nhất.
- [ ] `RECEIVE_OK` xuất hiện sau khi nhận đúng `TextMessage` và body.
- [ ] Đã thử quyền với **writer** và **reader** khác danh tính.
- [ ] Kết quả deny có bằng chứng từ exception/broker audit, không suy từ timeout.
- [ ] Message thử có TTL, không để tồn đọng kéo dài; biết cách dọn queue thử.
- [ ] Lưu run ID, thời gian, môi trường, destination, trạng thái từng bước và lỗi (nếu có).

### Câu hỏi tự kiểm tra

1. Tại sao `Test-NetConnection` thành công vẫn chưa thể khẳng định ứng dụng gửi được message JMS?
2. Một user tạo được `Connection` nhưng bị từ chối ở `send`: đó có nhất thiết là lỗi mật khẩu không?
3. Vì sao việc queue chưa tồn tại làm phép đo quyền `send` khó diễn giải hơn?
4. `RECEIVE_TIMEOUT` khác `JMSSecurityException` như thế nào?
5. Tại sao cần `connection.start()` khi dùng `MessageConsumer` của classic JMS API?
6. Nếu `probe-writer` và `probe-reader` là hai tài khoản, thứ tự thử nghiệm hợp lý là gì?
7. `ROUNDTRIP_OK` có chứng minh tất cả JMS listeners của ứng dụng thật hoạt động không? Vì sao?

**Ghi nhớ:** Phép thử tốt nhất là phép thử đưa ra **kết luận vừa đủ từ chứng cứ**. Được TCP không nghĩa là được JMS; được kết nối không nghĩa là có quyền gửi; được gửi không nghĩa là được nhận; nhận được message thử không nghĩa là nghiệp vụ đã hoàn thành.

## Tài liệu tham khảo

- Jakarta Messaging 3.1 Specification – Connections, Sessions, Message Producers/Consumers: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Spring Boot 3.3 – JMS and Artemis: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
- Spring Framework – JMS integration: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Apache ActiveMQ Artemis – Docker quickstart: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
- Apache ActiveMQ Artemis – Authentication and Authorization: https://artemis.apache.org/components/artemis/documentation/latest/security.html
