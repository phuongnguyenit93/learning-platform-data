# Chuẩn bị bộ môi giới và thông tin xác thực cho môi trường thử nghiệm

## 1. Mục tiêu và phạm vi

Ứng dụng Spring sử dụng message broker cần biết địa chỉ kết nối, cổng giao thức, virtual host, tên người dùng và mật khẩu. Broker cũng phải được khởi tạo đúng cách, có namespace riêng cho môi trường thử nghiệm và cấp quyền phù hợp cho ứng dụng.

Một cấu hình thử nghiệm tốt cần đáp ứng các mục tiêu:

- Có thể khởi động broker trên máy phát triển hoặc trong CI một cách lặp lại.
- Cô lập queue, exchange và binding của ứng dụng khỏi môi trường khác.
- Dùng tài khoản riêng cho ứng dụng, với quyền vừa đủ trên virtual host thử nghiệm.
- Không ghi mật khẩu thật vào Git, file cấu hình dùng chung, log hoặc ảnh chụp màn hình.
- Để Spring Boot nhận cấu hình qua environment variables và profile.
- Có health check và smoke test để phát hiện lỗi kết nối, sai mật khẩu hoặc thiếu quyền sớm.
- Có cách dọn dữ liệu thử nghiệm mà không vô tình xóa dữ liệu của môi trường dùng chung.

Bài này dùng RabbitMQ làm ví dụ vì Spring AMQP tích hợp trực tiếp với RabbitMQ. Các nguyên tắc về endpoint, danh tính, phân quyền, cô lập môi trường và quản lý secret cũng áp dụng cho các broker khác, dù tên cấu hình và giao thức sẽ khác.

## 2. Các thông tin cần chuẩn bị

Một kết nối AMQP đến RabbitMQ thường cần các thông tin sau:

| Thông tin | Ví dụ trong môi trường thử nghiệm | Ý nghĩa |
|---|---|---|
| Host | localhost | Tên máy hoặc DNS của broker mà ứng dụng nhìn thấy |
| Port | 5672 | Cổng AMQP không mã hóa mặc định |
| Username | spring_test | Tài khoản dành riêng cho ứng dụng |
| Password | Secret được tạo riêng | Bí mật xác thực của tài khoản |
| Virtual host | /messaging-test | Namespace chứa exchange, queue và binding |
| TLS | Tắt ở local loopback; bật theo chính sách của test server | Mã hóa kết nối qua mạng |

Không nhầm cổng AMQP với cổng quản trị:

- 5672 là cổng giao thức AMQP mà Spring AMQP dùng để gửi và nhận message.
- 15672 là giao diện quản trị HTTP của RabbitMQ Management Plugin. Spring AMQP không kết nối đến cổng này.

Virtual host (vhost) là namespace logic trong RabbitMQ. Queue tên orders trong /messaging-test và queue tên orders trong / là hai tài nguyên khác nhau. Dùng vhost riêng giúp tránh đụng tên và giới hạn phạm vi quyền.

Trong môi trường thử nghiệm, nên có một vhost riêng như /messaging-test và một user ứng dụng như spring_test. Không dùng tài khoản quản trị để chạy listener hoặc gửi message trong ứng dụng.

## 3. Khởi chạy RabbitMQ bằng Docker Compose

Docker Compose giúp cả nhóm dùng cùng phiên bản broker, cùng cổng và cùng cách khởi tạo. Tạo thư mục dành cho môi trường thử nghiệm, sau đó tạo file compose.yaml:

~~~yaml
services:
  rabbitmq:
    image: rabbitmq:3.13-management
    container_name: spring-messaging-test-rabbitmq
    hostname: rabbitmq
    environment:
      RABBITMQ_DEFAULT_USER: ${RABBITMQ_BOOTSTRAP_USER:?Set RABBITMQ_BOOTSTRAP_USER}
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_BOOTSTRAP_PASSWORD:?Set RABBITMQ_BOOTSTRAP_PASSWORD}
      RABBITMQ_DEFAULT_VHOST: ${RABBITMQ_VHOST:-/messaging-test}
    ports:
      - "127.0.0.1:5672:5672"
      - "127.0.0.1:15672:15672"
    volumes:
      - rabbitmq_test_data:/var/lib/rabbitmq
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 20s

volumes:
  rabbitmq_test_data:
~~~

Image rabbitmq:3.13-management bao gồm RabbitMQ và giao diện quản trị. Trong CI hoặc nhóm có yêu cầu tái lập nghiêm ngặt, hãy pin patch version hoặc image digest đã được kiểm tra thay vì để tag thay đổi theo thời gian.

Các cổng được bind vào 127.0.0.1, vì vậy broker chỉ được công bố trên loopback của máy chạy Docker. Điều này phù hợp với broker local. Nếu broker nằm trên máy chủ dùng chung, hãy cấu hình firewall, TLS, DNS và quyền truy cập theo hạ tầng của môi trường đó; không mở giao diện quản trị ra Internet.

Volume rabbitmq_test_data giữ dữ liệu broker qua lần khởi động container. Đây là lựa chọn thuận tiện cho môi trường phát triển. Với bài test cần môi trường sạch hoàn toàn, có thể dùng container tạm thời riêng cho từng lần chạy.

### 3.1. Tạo file secret cục bộ

Tạo file .env.example để ghi lại tên biến cần có:

~~~dotenv
RABBITMQ_BOOTSTRAP_USER=local_admin
RABBITMQ_BOOTSTRAP_PASSWORD=replace-with-a-random-secret
RABBITMQ_VHOST=/messaging-test

RABBITMQ_USER=spring_test
RABBITMQ_PASSWORD=replace-with-another-random-secret
~~~

Sao chép thành .env trên máy cá nhân và thay hai giá trị password bằng secret ngẫu nhiên. Có thể tạo secret bằng openssl rand -base64 32 hoặc trình quản lý mật khẩu của tổ chức. Không dùng cùng một mật khẩu cho tài khoản bootstrap và tài khoản ứng dụng.

Thêm .env vào .gitignore:

~~~gitignore
.env
.env.*
!.env.example
~~~

Kiểm tra .gitignore hiện tại trước khi thêm quy tắc để tránh ghi đè các ngoại lệ đang có. File .env.example chỉ chứa placeholder, không chứa mật khẩu dùng được.

Docker Compose tự đọc .env để thay thế biến trong compose.yaml. Tuy nhiên, điều đó không có nghĩa tiến trình Spring Boot chạy trực tiếp trên máy cũng tự đọc file .env. Ứng dụng cần được cấp các biến môi trường riêng qua terminal, IDE, CI secret store hoặc cấu hình chạy của môi trường.

### 3.2. Khởi động và kiểm tra container

Từ thư mục có compose.yaml và .env, chạy:

~~~bash
docker compose up -d rabbitmq
docker compose ps
~~~

Kiểm tra broker đã phản hồi:

~~~bash
docker exec spring-messaging-test-rabbitmq rabbitmq-diagnostics -q ping
~~~

Kết quả thành công cho biết node RabbitMQ đang phản hồi lệnh chẩn đoán. Có thể xem log khi khởi động gặp lỗi:

~~~bash
docker compose logs --tail=100 rabbitmq
~~~

Mở giao diện quản trị tại http://localhost:15672. Đăng nhập bằng tài khoản bootstrap đã khai báo trong .env. Tài khoản này dùng để cấu hình broker, không đưa vào application-test.yaml của ứng dụng.

## 4. Tạo tài khoản ứng dụng và cấp quyền

### 4.1. Tách bootstrap user khỏi application user

RABBITMQ_DEFAULT_USER và RABBITMQ_DEFAULT_PASS tạo tài khoản bootstrap khi RabbitMQ khởi tạo data directory lần đầu. Tài khoản mặc định này thường có quyền quản trị. Chỉ dùng nó để tạo vhost, user và quyền ban đầu.

Tạo tài khoản ứng dụng riêng tên spring_test. Có thể tạo qua giao diện quản trị:

1. Mở tab Admin, chọn Users, rồi chọn Add a user.
2. Nhập username spring_test và password lấy từ secret cục bộ.
3. Để trống user tags để tài khoản không có quyền quản trị giao diện.
4. Tạo user, sau đó mở mục Virtual Hosts và chọn /messaging-test.
5. Cấp quyền cho spring_test trên vhost này. Với vhost local chỉ dành cho bài thử nghiệm, có thể dùng .* cho configure, write và read.
6. Xác nhận tài khoản bootstrap vẫn có thể quản trị broker khi cần.

Có thể thực hiện các thao tác tương đương bằng CLI:

~~~bash
docker exec spring-messaging-test-rabbitmq rabbitmqctl add_user spring_test 'PASTE_APP_PASSWORD_HERE'
docker exec spring-messaging-test-rabbitmq rabbitmqctl set_permissions -p /messaging-test spring_test '.*' '.*' '.*'
~~~

Thay placeholder bằng giá trị password của ứng dụng. Lệnh CLI nhận password như một tham số, vì vậy terminal history hoặc danh sách tiến trình có thể để lộ bí mật. Khi cần tránh rủi ro này, tạo user qua giao diện quản trị hoặc dùng quy trình provisioning nhận secret an toàn của tổ chức.

Ba biểu thức trong set_permissions lần lượt là quyền configure, write và read đối với tài nguyên trong vhost. .* cho phép tài khoản tạo và sử dụng các queue/exchange trong vhost đó. Đây là quyền rộng trong một namespace đã cô lập, phù hợp cho môi trường local. Với môi trường dùng chung, hãy giới hạn tên queue và exchange theo quy ước của ứng dụng, đồng thời chỉ cấp quyền thực sự cần.

### 4.2. Xác minh vhost, user và permission

Các lệnh kiểm tra:

~~~bash
docker exec spring-messaging-test-rabbitmq rabbitmqctl list_vhosts name
docker exec spring-messaging-test-rabbitmq rabbitmqctl list_users
docker exec spring-messaging-test-rabbitmq rabbitmqctl list_permissions -p /messaging-test
~~~

Xác nhận rằng:

- Vhost /messaging-test tồn tại.
- User spring_test tồn tại và không có administrator tag.
- User có configure, write và read permission trên đúng vhost.
- Ứng dụng không cần đăng nhập bằng tài khoản bootstrap.

Không chia sẻ output có username hoặc thông tin môi trường nội bộ ở nơi công khai. Các lệnh liệt kê permission không hiển thị password, nhưng log triển khai vẫn cần được xử lý như thông tin vận hành.

## 5. Cấu hình Spring Boot theo profile

Tách cấu hình kết nối broker vào profile thử nghiệm. Tạo src/main/resources/application-test.yaml:

~~~yaml
spring:
  application:
    name: spring-messaging-sample
  rabbitmq:
    host: ${RABBITMQ_HOST:localhost}
    port: ${RABBITMQ_PORT:5672}
    username: ${RABBITMQ_USER}
    password: ${RABBITMQ_PASSWORD}
    virtual-host: ${RABBITMQ_VHOST:/messaging-test}
    connection-timeout: 5s
    requested-heartbeat: 30s
~~~

Các placeholder RABBITMQ_USER và RABBITMQ_PASSWORD không có giá trị mặc định. Nếu quên cấu hình, ứng dụng sẽ báo thiếu biến thay vì âm thầm sử dụng một mật khẩu yếu hoặc tài khoản không đúng. host và port có giá trị mặc định thuận tiện cho ứng dụng chạy trên máy phát triển.

Chạy ứng dụng với profile test. Trong PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "test"
$env:RABBITMQ_HOST = "localhost"
$env:RABBITMQ_PORT = "5672"
$env:RABBITMQ_USER = "spring_test"
$env:RABBITMQ_PASSWORD = "set-the-local-secret"
$env:RABBITMQ_VHOST = "/messaging-test"
./mvnw spring-boot:run
~~~

Trong Bash:

~~~bash
export SPRING_PROFILES_ACTIVE=test
export RABBITMQ_HOST=localhost
export RABBITMQ_PORT=5672
export RABBITMQ_USER=spring_test
export RABBITMQ_PASSWORD='set-the-local-secret'
export RABBITMQ_VHOST=/messaging-test
./mvnw spring-boot:run
~~~

Thay giá trị password minh họa bằng secret đã tạo. Với IDE, khai báo profile và biến môi trường trong Run Configuration. Với CI, lấy username/password từ secret store của pipeline; không ghi chúng vào YAML của workflow hoặc tham số dòng lệnh được lưu trong log.

### 5.1. Hostname phụ thuộc nơi ứng dụng chạy

Địa chỉ broker phụ thuộc network namespace:

- Spring Boot chạy trực tiếp trên máy host: dùng localhost và cổng đã publish, ví dụ 5672.
- Spring Boot chạy trong một service khác của cùng Docker Compose project: dùng hostname service rabbitmq và cổng container 5672.
- Spring Boot chạy trên CI runner hoặc máy khác: dùng DNS/IP mà runner nhìn thấy, cùng cổng broker được phép truy cập.

localhost bên trong container ứng dụng trỏ về chính container ứng dụng, không phải container RabbitMQ. Đây là nguyên nhân phổ biến gây Connection refused khi chuyển ứng dụng từ chạy trên máy host sang chạy trong Docker.

Nếu đóng gói cả ứng dụng vào Compose, có thể khai báo dependency theo health status:

~~~yaml
services:
  app:
    build: .
    environment:
      SPRING_PROFILES_ACTIVE: test
      RABBITMQ_HOST: rabbitmq
      RABBITMQ_PORT: 5672
      RABBITMQ_USER: ${RABBITMQ_USER}
      RABBITMQ_PASSWORD: ${RABBITMQ_PASSWORD}
      RABBITMQ_VHOST: ${RABBITMQ_VHOST:-/messaging-test}
    depends_on:
      rabbitmq:
        condition: service_healthy
~~~

Đây là phần bổ sung cho service app trong cùng file Compose đã khai báo service rabbitmq. depends_on với service_healthy giúp chờ health check của broker trước khi khởi động ứng dụng. Ứng dụng vẫn cần xử lý broker mất kết nối sau thời điểm khởi động.

## 6. Cô lập môi trường và quản lý vòng đời dữ liệu

Nên dùng cấu hình khác nhau cho local, integration test, shared test, staging và production:

| Môi trường | Broker | Credential | Dữ liệu |
|---|---|---|---|
| Local developer | Container trên máy | Secret riêng từng máy | Có thể giữ trong volume local |
| Integration test | Container tạm hoặc service riêng của job | Credential test dùng một lần | Xóa sau mỗi lần chạy |
| Shared test | Broker/vhost được quản lý chung | Secret cấp cho nhóm hoặc pipeline | Có chính sách dọn queue và message |
| Staging/production | Broker do hạ tầng vận hành | Secret manager và rotation | Retention, backup và monitoring theo SLA |

Không dùng chung vhost giữa test và production. Nếu nhiều ứng dụng dùng cùng một broker, cấp vhost riêng cho từng ứng dụng hoặc nhóm có ranh giới dữ liệu rõ ràng. Nếu nhiều nhánh CI chạy song song, dùng vhost hoặc prefix tài nguyên riêng theo build để tránh hai job cùng xóa queue hoặc tiêu thụ message của nhau.

Một volume có dữ liệu cũ sẽ giữ lại user, vhost và permission đã tạo trước đó. Thay đổi RABBITMQ_DEFAULT_USER, RABBITMQ_DEFAULT_PASS hoặc RABBITMQ_DEFAULT_VHOST trong .env không tự sửa các tài khoản đã có trong data directory. Khi cần thay đổi user trên broker đang chạy, dùng lệnh quản trị như change_password, add_user, set_permissions hoặc giao diện quản trị.

Với môi trường local có thể tái tạo hoàn toàn, docker compose down -v xóa container và volume đã khai báo trong project, bao gồm message và dữ liệu broker. Chỉ chạy lệnh này khi chắc chắn volume thuộc môi trường thử nghiệm có thể xóa. Với shared test, không tự ý xóa volume hoặc reset broker để khắc phục một lỗi kết nối.

## 7. Kiểm tra kết nối từ ứng dụng

Một broker khỏe mạnh chưa chứng minh Spring Boot đã xác thực thành công. Cần kiểm tra từ đúng runtime của ứng dụng để phát hiện sai hostname, port, user, password, vhost hoặc permission.

Một smoke test đơn giản có thể dùng RabbitTemplate để khai báo một queue tạm, gửi một message rồi nhận lại:

~~~java
package com.example.messaging;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
class RabbitMqConnectionTest {

    @Autowired
    private RabbitTemplate rabbitTemplate;

    @Test
    void applicationCanPublishAndReceive() {
        String queueName = "test.connectivity.queue";

        rabbitTemplate.execute(channel -> {
            channel.queueDeclare(
                queueName,
                true,
                false,
                false,
                null
            );
            return null;
        });

        try {
            rabbitTemplate.convertAndSend(queueName, "connection-ok");

            Object received = rabbitTemplate.receiveAndConvert(
                queueName,
                5_000
            );

            assertThat(received).isEqualTo("connection-ok");
        } finally {
            rabbitTemplate.execute(channel -> {
                channel.queueDelete(queueName);
                return null;
            });
        }
    }
}
~~~

Queue trong test là durable, không exclusive và không auto-delete; mỗi test xóa queue tường minh trong khối finally, kể cả khi assertion thất bại. `receiveAndConvert` dùng thao tác polling AMQP `basic.get`, không đăng ký consumer dài hạn, vì vậy không thể dựa vào auto-delete để dọn queue. RabbitTemplate dùng default exchange khi gửi với routing key là tên queue.

Bổ sung spring-boot-starter-test ở scope test nếu dự án chưa có. Khi chạy smoke test với profile test, hãy cấp cùng các biến môi trường kết nối như khi chạy ứng dụng. Test này xác nhận đường đi cơ bản từ Spring đến broker; nó chưa kiểm tra retry, dead-letter, concurrency hoặc khả năng phục hồi khi broker restart.

### 7.1. Dùng Testcontainers để có broker riêng cho integration test

Với CI hoặc integration test cần tính độc lập, Testcontainers có thể khởi chạy RabbitMQ trong container tạm. Thêm dependency test:

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>1.20.6</version>
    <scope>test</scope>
</dependency>
~~~

Ví dụ dưới đây dùng GenericContainer, nên không cần module RabbitMQ riêng:

~~~java
package com.example.messaging;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
@ActiveProfiles("test")
class RabbitMqContainerTest {

    @Container
    static final GenericContainer<?> rabbit =
        new GenericContainer<>(
            DockerImageName.parse("rabbitmq:3.13-management")
        )
            .withExposedPorts(5672)
            .withEnv("RABBITMQ_DEFAULT_USER", "test_user")
            .withEnv("RABBITMQ_DEFAULT_PASS", "test_password")
            .withEnv("RABBITMQ_DEFAULT_VHOST", "/messaging-test");

    @DynamicPropertySource
    static void rabbitProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host", rabbit::getHost);
        registry.add(
            "spring.rabbitmq.port",
            () -> rabbit.getMappedPort(5672)
        );
        registry.add("spring.rabbitmq.username", () -> "test_user");
        registry.add("spring.rabbitmq.password", () -> "test_password");
        registry.add(
            "spring.rabbitmq.virtual-host",
            () -> "/messaging-test"
        );
    }

    @Autowired
    RabbitTemplate rabbitTemplate;

    @Test
    void canPublishAndReceiveFromTemporaryBroker() {
        String queueName = "test.container.queue";

        rabbitTemplate.execute(channel -> {
            channel.queueDeclare(
                queueName,
                false,
                false,
                true,
                null
            );
            return null;
        });

        try {
            rabbitTemplate.convertAndSend(queueName, "container-ok");

            Object received = rabbitTemplate.receiveAndConvert(
                queueName,
                5_000
            );

            assertThat(received).isEqualTo("container-ok");
        } finally {
            rabbitTemplate.execute(channel -> {
                channel.queueDelete(queueName);
                return null;
            });
        }
    }
}
~~~

Testcontainers cần Docker daemon hoạt động. Container test dùng user/password giả lập, chỉ tồn tại trong vòng đời container thử nghiệm và không phải secret dùng chung. DynamicPropertySource truyền host và cổng được ánh xạ ngẫu nhiên vào Spring context, tránh phụ thuộc cổng 5672 trên máy chạy CI. Queue kiểm thử được xóa tường minh trong `finally`; Testcontainers cũng dừng và xóa container sau test.

Dùng cùng một phiên bản RabbitMQ trong Testcontainers và môi trường local/shared test nếu cần tái hiện hành vi theo phiên bản. Không dựa vào dữ liệu còn sót từ lần chạy trước; container tạm giúp mỗi lượt test có broker sạch.

## 8. Bật TLS và kết nối tới broker dùng chung

Cấu hình local loopback thường có thể dùng AMQP không TLS vì kết nối không rời khỏi máy phát triển. Khi kết nối qua mạng đến shared test hoặc staging, cần tuân thủ chính sách TLS của broker.

Với RabbitMQ có TLS listener, Spring Boot hỗ trợ cấu hình SSL qua các thuộc tính spring.rabbitmq.ssl. Ví dụ bật SSL:

~~~yaml
spring:
  rabbitmq:
    ssl:
      enabled: true
~~~

Đoạn trên chỉ bật SSL phía client; broker phải có TLS listener và chứng thư phù hợp. Môi trường thực tế còn cần cấu hình trust store hoặc cơ chế tin cậy chứng thư theo hạ tầng. Không tắt xác minh chứng thư để “sửa nhanh” lỗi TLS. Cổng TLS thường được cấu hình riêng, vì vậy phải lấy đúng endpoint và port từ người quản trị broker.

Đối với shared test:

- Lấy hostname, port, vhost và tên secret từ nguồn cấu hình được nhóm phê duyệt.
- Không tự tạo tài khoản trên broker dùng chung nếu chưa có quyền provisioning.
- Không sao chép password vào ticket, chat, commit hoặc log CI.
- Yêu cầu quyền tối thiểu theo vhost và tên tài nguyên.
- Xác định cách rotation password và cập nhật secret của pipeline.
- Không ghi payload nhạy cảm vào message chỉ vì môi trường được gọi là test.

## 9. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Connection refused | Broker chưa chạy, sai port, sai hostname hoặc port chưa publish | Kiểm tra docker compose ps, health check và endpoint từ đúng nơi ứng dụng chạy |
| UnknownHostException | Dùng hostname service Compose từ máy host hoặc DNS sai | Host process dùng localhost; container cùng network dùng rabbitmq |
| ACCESS_REFUSED khi đăng nhập | Sai username/password hoặc user không được phép truy cập vhost | Kiểm tra user, vhost và secret đang được nạp vào tiến trình |
| ACCESS_REFUSED khi declare/publish/consume | Thiếu configure, write hoặc read permission | Kiểm tra rabbitmqctl list_permissions -p /messaging-test |
| NOT_ALLOWED hoặc lỗi vhost | Vhost chưa tồn tại hoặc tên vhost không khớp | Kiểm tra chính xác dấu / và tên vhost |
| Kết nối chập chờn | Broker restart, network không ổn định, heartbeat hoặc timeout không phù hợp | Kiểm tra log broker, heartbeat và thời gian kết nối |
| Ứng dụng chạy được local nhưng fail trong Docker | Dùng localhost bên trong container ứng dụng | Đổi host thành tên service rabbitmq |
| Đổi password nhưng vẫn bị từ chối | Volume cũ giữ tài khoản cũ hoặc secret chưa được cập nhật đúng | Kiểm tra user trên broker và biến môi trường của tiến trình |
| Test pass riêng lẻ nhưng fail khi chạy song song | Các test dùng chung queue hoặc vhost và tiêu thụ message của nhau | Dùng tên queue/vhost riêng theo test hoặc container riêng |

Khi điều tra, kiểm tra theo thứ tự: broker có chạy không, ứng dụng có nhìn thấy endpoint không, xác thực có thành công không, vhost có tồn tại không, user có permission không, rồi mới kiểm tra queue/exchange và topology. Không sửa bằng cách cấp administrator tag cho application user; điều đó che khuất vấn đề phân quyền và mở rộng phạm vi ảnh hưởng.

## 10. Bảo mật thông tin xác thực

- Tạo password ngẫu nhiên, đủ dài và khác nhau giữa bootstrap user, application user và từng môi trường.
- Đưa .env vào .gitignore; chỉ commit .env.example với placeholder.
- Dùng secret store của CI/CD hoặc nền tảng triển khai cho shared test và production.
- Không ghi password vào source code, Dockerfile, image layer, test report, command log hoặc exception message.
- Không dùng tài khoản bootstrap/admin trong cấu hình Spring Boot.
- Không cấp administrator tag cho user chạy consumer.
- Giới hạn quyền trên vhost và giới hạn mạng truy cập broker.
- Bật TLS khi kết nối qua mạng theo chính sách hạ tầng.
- Rotation secret cần cập nhật broker và secret store đồng bộ; kiểm tra kết nối mới trước khi thu hồi credential cũ nếu hệ thống cần chuyển đổi không gián đoạn.
- Xóa hoặc vô hiệu hóa user thử nghiệm không còn sử dụng.

Docker Compose .env thuận tiện cho local nhưng không phải một secret manager. Bất kỳ ai có quyền đọc file hoặc quyền truy cập Docker daemon trên máy đều có thể lấy được biến môi trường của container. Vì vậy, không dùng cách lưu này cho thông tin xác thực production hoặc shared environment có yêu cầu kiểm soát truy cập cao.

## 11. Dọn dẹp môi trường thử nghiệm

Dừng broker nhưng giữ volume:

~~~bash
docker compose down
~~~

Khởi động lại sau đó sẽ dùng lại data directory, vhost, user, permission và message còn tồn tại.

Nếu cần reset hoàn toàn một broker local có thể xóa:

~~~bash
docker compose down -v
~~~

Lệnh có -v xóa named volume của project. Toàn bộ queue, exchange được khai báo động, message và dữ liệu broker trong volume đó có thể mất. Chỉ dùng trên môi trường local hoặc test tạm thời đã xác nhận có thể hủy. Không chạy lệnh này với broker shared test hoặc production.

## 12. Checklist trước khi bắt đầu kiểm thử

- [ ] Phiên bản RabbitMQ được pin và tương thích với phiên bản Spring AMQP của dự án.
- [ ] Broker đã khởi động và health check thành công.
- [ ] Cổng AMQP và management được phân biệt đúng.
- [ ] Vhost riêng cho môi trường thử nghiệm đã tồn tại.
- [ ] Application user riêng đã được tạo, không có administrator tag.
- [ ] User có configure/write/read permission cần thiết trên đúng vhost.
- [ ] Password được tạo ngẫu nhiên và lưu ngoài Git.
- [ ] Spring Boot nhận đúng profile, host, port, username, password và vhost.
- [ ] Hostname đúng với vị trí chạy ứng dụng: host hoặc container.
- [ ] Smoke test publish/receive thành công.
- [ ] CI lấy secret từ secret store và không in giá trị ra log.
- [ ] Có cách reset dữ liệu local an toàn và có quy trình quản lý shared test.
- [ ] TLS được bật khi kết nối qua mạng theo yêu cầu môi trường.

## 13. Tổng kết

Một môi trường thử nghiệm message broker đáng tin cậy bắt đầu từ endpoint rõ ràng, vhost riêng, tài khoản ứng dụng có quyền tối thiểu và secret được quản lý ngoài source code. Docker Compose cung cấp broker tái lập cho local; Spring Boot profile và environment variables giúp chuyển cấu hình theo nơi chạy; smoke test hoặc Testcontainers xác nhận ứng dụng thực sự kết nối, xác thực, publish và consume được.

Khi thay đổi môi trường, cần phân biệt cấu hình bootstrap ban đầu với dữ liệu đã lưu trong volume. Cũng cần phân biệt cổng AMQP với cổng quản trị, hostname của host với hostname trong Docker network, và tài khoản quản trị với tài khoản ứng dụng. Làm rõ các ranh giới này giúp phát hiện lỗi sớm và giữ môi trường thử nghiệm độc lập, an toàn, dễ tái tạo.