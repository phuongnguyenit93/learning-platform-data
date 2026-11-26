# Dựng RabbitMQ cục bộ bằng Docker Compose cho thực hành

Để học **Spring AMQP**, cần một RabbitMQ broker mà ta có thể chủ động khởi động, dừng, tạo exchange/queue/binding và quan sát việc gửi nhận thông điệp. **Docker Compose** giúp dựng môi trường thực hành nhất quán: chỉ cần một tệp cấu hình để chạy broker RabbitMQ cùng giao diện **RabbitMQ Management**, sau đó kết nối từ ứng dụng Spring Boot sử dụng **RabbitTemplate** và **@RabbitListener**.

Bài này hướng dẫn xây dựng môi trường **cục bộ phục vụ học tập**. Cuối bài, bạn sẽ có thể:

1. Khởi chạy RabbitMQ với Docker Compose và giữ dữ liệu trong Docker volume.
2. Phân biệt cổng **5672** dành cho AMQP với **15672** dành cho giao diện quản trị HTTP.
3. Tự tạo exchange, queue, binding và kiểm chứng một message đi đến nhiều queue.
4. Kết nối Spring AMQP, gửi message bằng RabbitTemplate và xử lý bằng @RabbitListener.
5. Quan sát tình trạng broker, kiểm tra kết nối và xử lý lỗi cấu hình thường gặp.

## 1. Môi trường cần chuẩn bị

Bạn cần:

- **Docker Engine** đang chạy: trên Windows/macOS thường là Docker Desktop; trên Linux có thể dùng Docker Engine.
- **Docker Compose V2**, sử dụng cú pháp lệnh **docker compose** (có dấu cách).
- Một terminal (PowerShell, Terminal hoặc shell), trình duyệt web và một thư mục trống cho bài thực hành.
- Nếu thực hành phần Java: JDK và dự án Spring Boot có dependency **spring-boot-starter-amqp**.

Kiểm tra Docker và Compose trong terminal:

~~~bash
docker version
docker compose version
docker info
~~~

Lệnh **docker version** cho biết Docker client và server có giao tiếp được không; **docker compose version** xác nhận plugin Compose; **docker info** giúp phát hiện Docker Engine chưa khởi động. Nếu báo không kết nối được Docker daemon, hãy khởi động Docker Desktop hoặc Docker Engine rồi thử lại.

Tạo một thư mục thực hành, ví dụ **spring-amqp-lab**, và đặt tệp **compose.yaml** trong đó:

~~~text
spring-amqp-lab/
└── compose.yaml
~~~

Không cần cài RabbitMQ trực tiếp lên máy, cũng không cần cài Erlang riêng: image Docker đã chứa môi trường chạy RabbitMQ.

## 2. Hiểu các thành phần của mô hình

~~~mermaid
flowchart LR
    A["Ứng dụng Spring Boot<br/>RabbitTemplate / @RabbitListener"]
    B["127.0.0.1:5672<br/>AMQP 0-9-1"]
    C[("RabbitMQ<br/>Docker container")]
    D["127.0.0.1:15672<br/>HTTP Management"]
    E["Trình duyệt web"]
    V[("Docker volume<br/>rabbitmq_data")]
    A <-->|"Gửi / nhận message"| B
    B <--> C
    E <-->|"Giám sát / thao tác"| D
    D <--> C
    C <-->|"Dữ liệu broker"| V
~~~

Trong sơ đồ:

- **RabbitMQ container** chạy broker và plugin Management.
- **Cổng 5672** dùng giao thức AMQP để ứng dụng Spring AMQP kết nối. Đây **không** phải địa chỉ để mở trong trình duyệt.
- **Cổng 15672** dùng HTTP cho trang quản trị RabbitMQ và API Management.
- **Volume** giữ trạng thái dữ liệu của broker khi container bị xóa và tạo lại, miễn là volume vẫn còn.
- **Exchange** nhận message được publish; **binding** quyết định queue nào nhận; **queue** giữ message cho consumer. RabbitMQ Management giúp quan sát các thành phần này.

## 3. Viết compose.yaml

Tạo tệp **compose.yaml** với nội dung sau:

~~~yaml
name: spring-amqp-lab

services:
  rabbitmq:
    image: rabbitmq:4-management
    hostname: rabbitmq
    restart: unless-stopped

    environment:
      RABBITMQ_DEFAULT_USER: app
      RABBITMQ_DEFAULT_PASS: local_dev_password
      RABBITMQ_DEFAULT_VHOST: /

    ports:
      - "127.0.0.1:5672:5672"
      - "127.0.0.1:15672:15672"

    volumes:
      - rabbitmq_data:/var/lib/rabbitmq

    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "check_running"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 20s

volumes:
  rabbitmq_data:
~~~

Ví dụ dùng image **rabbitmq:4-management** để có RabbitMQ 4.x cùng plugin Management. Tag theo dòng phiên bản lớn có thể được cập nhật theo thời gian; nếu cần môi trường nhóm hoặc CI tái lập chính xác, hãy thống nhất và cố định tag phiên bản cụ thể hoặc digest image. Mật khẩu **local_dev_password** chỉ dành cho môi trường thực hành; không dùng nó cho hệ thống triển khai thật.

Giải thích các cấu hình chính:

| Khai báo | Tác dụng |
| --- | --- |
| **name: spring-amqp-lab** | Đặt tên Compose project, dùng để phân biệt tài nguyên với project khác. |
| **services.rabbitmq** | Đặt tên service. Các container cùng mạng Compose có thể tìm broker qua hostname DNS **rabbitmq**. |
| **image: rabbitmq:4-management** | Dùng image RabbitMQ kèm giao diện quản trị. |
| **hostname: rabbitmq** | Giữ hostname ổn định, hữu ích khi sử dụng volume chứa dữ liệu của RabbitMQ node. |
| **RABBITMQ_DEFAULT_USER / PASS** | Tạo tài khoản mặc định trong quá trình khởi tạo broker mới. |
| **RABBITMQ_DEFAULT_VHOST: /** | Dùng virtual host mặc định **/**. |
| **127.0.0.1:5672:5672** | Chỉ mở AMQP trên loopback của máy chạy Docker. |
| **127.0.0.1:15672:15672** | Chỉ mở giao diện Management trên loopback. |
| **rabbitmq_data:/var/lib/rabbitmq** | Lưu dữ liệu broker vào named volume. |
| **healthcheck** | Kiểm tra RabbitMQ application đã chạy bằng **rabbitmq-diagnostics check_running**. |
| **restart: unless-stopped** | Cho Docker tự khởi động lại container trong các trường hợp phù hợp, trừ khi người dùng chủ động dừng. |

### Tại sao chỉ công khai cổng trên 127.0.0.1?

Cấu hình **127.0.0.1:5672:5672** và **127.0.0.1:15672:15672** giúp môi trường thực hành chỉ nhận kết nối từ chính máy host, tránh vô tình mở tài khoản demo cho các máy khác trong mạng. Nếu truy cập từ máy từ xa hoặc dựng môi trường phân tán, cần thiết kế mạng, tài khoản, quyền và bảo mật phù hợp thay vì bỏ giới hạn loopback một cách tùy tiện.

Các cổng nội bộ khác của RabbitMQ (ví dụ phục vụ giao tiếp node) không cần ánh xạ ra host cho bài học với **một broker**.

### Vì sao dùng named volume?

Thông điệp, định nghĩa queue/exchange, người dùng và thông tin broker có thể được giữ lại khi bạn chạy **docker compose down** rồi **docker compose up -d**. Tuy nhiên, volume không biến message thành bất tử: muốn message tồn tại qua restart còn phụ thuộc queue durable, delivery mode persistent và chính sách broker. Lệnh **docker compose down -v** sẽ xóa cả volume do Compose quản lý, vì vậy chỉ dùng khi thực sự muốn làm mới toàn bộ dữ liệu thực hành.

## 4. Khởi chạy và kiểm tra trạng thái RabbitMQ

Trong thư mục chứa **compose.yaml**, chạy lần lượt:

~~~bash
docker compose config
docker compose up -d
docker compose ps
~~~

**docker compose config** giúp kiểm tra Compose có đọc và phân tích cấu hình hay không; nó không đảm bảo broker đã chạy. **docker compose up -d** tải image nếu cần rồi khởi động container ở chế độ nền. **docker compose ps** hiển thị service, trạng thái và ánh xạ cổng.

Bạn có thể thấy trạng thái **starting** trong giai đoạn RabbitMQ khởi động. Kiểm tra thêm:

~~~bash
docker compose exec rabbitmq rabbitmq-diagnostics -q check_running
docker compose logs --tail=100 rabbitmq
~~~

Nếu lệnh **check_running** thành công và container ở trạng thái **healthy**, broker đã qua kiểm tra sức khỏe được cấu hình. Có thể theo dõi log trực tiếp bằng:

~~~bash
docker compose logs -f rabbitmq
~~~

Nhấn **Ctrl+C** để thoát chế độ theo dõi log; container vẫn tiếp tục chạy. Log thường hữu ích khi cần xem broker đã bật listener AMQP/HTTP hay có lỗi cấu hình, phân quyền hoặc cổng.

**Lưu ý:** Compose chạy được container không có nghĩa ứng dụng Java đã kết nối được. Kết nối cần đúng host, cổng, user, password và virtual host.

## 5. Đăng nhập RabbitMQ Management

Mở địa chỉ:

**http://localhost:15672**

Đăng nhập bằng tài khoản trong **compose.yaml**:

| Trường | Giá trị bài thực hành |
| --- | --- |
| Username | **app** |
| Password | **local_dev_password** |
| Virtual host khi ứng dụng AMQP kết nối | **/** |

Trong Management UI, các vùng cần làm quen là:

- **Overview:** tổng quan tình trạng broker, message rate, kết nối và số lượng queue.
- **Connections:** kết nối TCP/AMQP giữa ứng dụng và broker.
- **Channels:** các AMQP channel đang hoạt động; một connection có thể có nhiều channel.
- **Exchanges:** exchange nhận thông điệp từ publisher, loại exchange và binding.
- **Queues and Streams / Queues:** danh sách queue, ready/unacked message, consumer và các thao tác gửi nhận kiểm tra. Tên tab có thể khác giữa các phiên bản Management UI.

Khi mới khởi tạo, broker có thể chỉ có các exchange hệ thống và chưa có queue nghiệp vụ. Đây là trạng thái bình thường.

## 6. Thực hành định tuyến trực tiếp trên Management UI

Mục tiêu: gửi **một** sự kiện vào một **fanout exchange** nhưng thấy **hai queue** cùng nhận. Chưa cần khởi chạy ứng dụng Spring Boot ở bước này.

### 6.1. Tạo exchange

Trong tab **Exchanges**, tìm chức năng tạo exchange mới:

| Thuộc tính | Giá trị |
| --- | --- |
| Name | **lab.events** |
| Type | **fanout** |
| Durable | **true** |
| Auto delete | **false** |
| Virtual host | **/** |

**Fanout** định tuyến message đến tất cả queue được bind với exchange, không xét routing key. **Durable exchange** tiếp tục tồn tại qua broker restart nếu trạng thái broker được duy trì.

### 6.2. Tạo hai queue

Trong **Queues**, lần lượt tạo:

| Queue name | Durable | Mục đích |
| --- | --- | --- |
| **lab.email** | **true** | Nhận sự kiện để gửi email. |
| **lab.audit** | **true** | Nhận sự kiện để ghi nhật ký nghiệp vụ. |

Chọn cùng virtual host **/** và để các tùy chọn khác theo mặc định cho bài thực hành. Nếu UI hỏi queue type, có thể chọn kiểu queue mặc định của broker; hãy dùng cùng loại queue trong suốt lần thực hành. Một queue durable không tự đảm bảo mọi message sẽ được ghi bền nếu message không được publish persistent.

### 6.3. Tạo hai binding

Mở exchange **lab.events**, tìm khu vực **Bindings** và tạo hai binding có **destination type = queue**:

~~~text
lab.events (fanout)
   ├── lab.email
   └── lab.audit
~~~

Với fanout, routing key của binding không quyết định việc message có được gửi tới queue hay không. Khi kiểm tra exchange, cần thấy **hai binding tới hai queue**.

### 6.4. Publish một message

Tại trang chi tiết exchange **lab.events**, dùng chức năng **Publish message** với payload dạng văn bản:

~~~text
order.created:O-1001
~~~

Để routing key trống nếu UI cho phép; fanout không cần key để chọn queue. Đặt **content type = text/plain** nếu giao diện hỗ trợ. Dùng văn bản giúp ví dụ tương thích với listener nhận **String** ở phần Spring Boot. Nếu gửi payload JSON với **application/json**, cần cấu hình message converter phù hợp hoặc xử lý đúng dạng payload ở phía consumer.

Vì chưa có consumer chạy, quay lại danh sách queue và kiểm tra:

| Queue | Ready dự kiến sau một lần publish | Consumers |
| --- | ---: | ---: |
| **lab.email** | 1 | 0 |
| **lab.audit** | 1 | 0 |

Các con số này giả định hai queue ban đầu trống, binding đúng, không có consumer hoặc chính sách tự loại message. Nếu publish hai lần thì mỗi queue có thể có hai message. Nếu bạn dùng chức năng **Get messages** của UI và chọn chế độ xác nhận/xóa, số message sẽ thay đổi.

Ở ví dụ này, exchange **định tuyến**, còn mỗi queue giữ **một bản sao logic độc lập**. Nếu hai consumer cùng nghe **lab.email** thay vì mỗi consumer nghe một queue, hai consumer sẽ **chia nhau** xử lý message trong queue đó, không cùng nhận mọi message.

## 7. Kết nối ứng dụng Spring Boot với RabbitMQ cục bộ

Sau khi môi trường hoạt động, tích hợp cơ bản vào Spring AMQP để thử **RabbitTemplate**, **@RabbitListener**, exchange, queue và binding. Ví dụ dưới đây giả định bạn đã có một dự án Spring Boot được cấu hình dependency management phù hợp với phiên bản Spring Boot đang dùng.

### 7.1. Thêm Spring AMQP starter

Với Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-amqp")
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Starter cung cấp cấu hình kết nối RabbitMQ, **RabbitTemplate**, listener container và các thành phần liên quan. Thông thường không cần tự mở TCP socket hay tự tạo AMQP connection theo cách thủ công.

### 7.2. Cấu hình application.yml

Nếu Spring Boot chạy **trực tiếp trên máy host**, sử dụng:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: app
    password: local_dev_password
    virtual-host: /
~~~

Đây là thông tin kết nối tương ứng với **compose.yaml**. Giá trị username/password trong ví dụ chỉ dành cho máy thực hành. Với dự án thật, truyền thông tin nhạy cảm qua biến môi trường hoặc cơ chế quản lý secret.

**Nếu ứng dụng Spring Boot cũng chạy trong container thuộc cùng Compose network**, host phải là **rabbitmq** và port nội bộ vẫn là **5672**:

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq
    port: 5672
    username: app
    password: local_dev_password
    virtual-host: /
~~~

Bên trong container, **localhost** chỉ chính container đó; dùng **localhost** để tìm RabbitMQ ở container khác là nguyên nhân kết nối lỗi rất phổ biến.

### 7.3. Khai báo exchange, queue và binding từ Spring AMQP

Lớp cấu hình sau sử dụng **cùng tên exchange/queue** đã tạo bằng UI. Nếu trước đó đã khai báo các đối tượng này với thuộc tính tương thích, Spring sẽ làm việc với chúng. Nếu bạn chưa tạo bằng UI, Spring AMQP có thể khai báo chúng tự động thông qua **RabbitAdmin** khi có kết nối với broker.

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.FanoutExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableRabbit
public class LabTopology {
    public static final String EXCHANGE = "lab.events";
    public static final String EMAIL_QUEUE = "lab.email";
    public static final String AUDIT_QUEUE = "lab.audit";

    @Bean
    public FanoutExchange labExchange() {
        return new FanoutExchange(EXCHANGE, true, false);
    }

    @Bean("emailQueue")
    public Queue emailQueue() {
        return QueueBuilder.durable(EMAIL_QUEUE).build();
    }

    @Bean("auditQueue")
    public Queue auditQueue() {
        return QueueBuilder.durable(AUDIT_QUEUE).build();
    }

    @Bean
    public Binding emailBinding(
            @Qualifier("emailQueue") Queue queue,
            FanoutExchange labExchange) {
        return BindingBuilder.bind(queue).to(labExchange);
    }

    @Bean
    public Binding auditBinding(
            @Qualifier("auditQueue") Queue queue,
            FanoutExchange labExchange) {
        return BindingBuilder.bind(queue).to(labExchange);
    }
}
~~~

Các bean khai báo topology thống nhất giữa code Java và broker. **QueueBuilder.durable(...)** tạo queue durable. Hai binding nối cùng fanout exchange đến hai queue độc lập.

Nếu bạn đã tạo queue qua giao diện với kiểu queue hoặc các thuộc tính không tương thích với khai báo Java, RabbitMQ có thể từ chối khai báo lại bằng lỗi **PRECONDITION_FAILED**. Khi đó cần đồng bộ cấu hình thay vì cố khai báo một tên queue với hai cấu hình khác nhau.

### 7.4. Viết publisher dùng RabbitTemplate

~~~java
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class LabPublisher {
    private final RabbitTemplate rabbitTemplate;

    public LabPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishCreatedOrder(String orderId) {
        rabbitTemplate.convertAndSend(
                LabTopology.EXCHANGE,
                "",
                "order.created:" + orderId,
                message -> {
                    message.getMessageProperties()
                           .setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                    return message;
                }
        );
    }
}
~~~

Publisher gửi **một message** vào exchange **lab.events**. Với fanout exchange, cả **lab.email** và **lab.audit** đều có thể nhận một bản sao. Trong ví dụ này payload là chuỗi văn bản, nên listener đọc **String** mà không cần tự khai báo JSON message converter.

Đặt delivery mode **PERSISTENT** giúp message phù hợp với queue durable trong bài thực hành lưu trữ. Đây chưa phải bảo đảm tuyệt đối chống mất dữ liệu: khi đi sâu về độ tin cậy, cần học **publisher confirms**, **consumer acknowledgements**, retry và dead-letter.

### 7.5. Viết hai listener

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class LabConsumers {

    @RabbitListener(queues = LabTopology.EMAIL_QUEUE)
    public void onEmail(String message) {
        System.out.println("[email] " + message);
    }

    @RabbitListener(queues = LabTopology.AUDIT_QUEUE)
    public void onAudit(String message) {
        System.out.println("[audit] " + message);
    }
}
~~~

Mỗi listener lắng nghe **một queue riêng**, nên hai chức năng có thể cùng nhận sự kiện. Để tự publish một message khi ứng dụng Spring Boot khởi động, có thể thêm bean **ApplicationRunner** vào một lớp **@Configuration**:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DemoRunner {
    @Bean
    public ApplicationRunner sendExample(LabPublisher publisher) {
        return args -> publisher.publishCreatedOrder("O-1002");
    }
}
~~~

Chạy ứng dụng bằng IDE hoặc lệnh chạy Spring Boot theo công cụ build của dự án. Khi kết nối thành công và hai listener đang chạy, output có thể tương tự:

~~~text
[email] order.created:O-1002
[audit] order.created:O-1002
~~~

Thứ tự hai dòng không được đảm bảo. Nếu bạn đã publish message **text/plain** qua Management UI trước đó, listener có thể xử lý những message đang chờ trước hoặc cùng thời điểm với message mới. Khi consumer xử lý và ack, chỉ số **Ready** của queue có thể trở về 0.

## 8. Quan sát kết nối, queue và trạng thái message

Mở **Management UI** trong lúc Spring Boot đang chạy để xem:

| Nơi quan sát | Thông tin cần kiểm tra |
| --- | --- |
| **Connections** | Có connection từ ứng dụng Spring Boot đến broker. |
| **Channels** | Channel được dùng để publish hoặc consume message. |
| **Exchanges → lab.events** | Exchange kiểu fanout và hai binding đúng. |
| **Queues → lab.email** | Queue tồn tại, có consumer; Ready và Unacked thay đổi khi nhận message. |
| **Queues → lab.audit** | Queue thứ hai độc lập với trạng thái queue email. |
| **Message rates** | Tốc độ publish, deliver và acknowledge khi có hoạt động. |

Ba chỉ số phổ biến:

- **Ready:** message đang ở queue và sẵn sàng giao cho consumer.
- **Unacked:** message đã giao cho consumer nhưng chưa được xác nhận hoàn tất.
- **Total:** tổng Ready và Unacked ở thời điểm quan sát.

Không nên mong đợi các số đếm đứng yên khi listener đang xử lý: RabbitMQ có thể chuyển message từ **Ready → Unacked → được ack/xóa** rất nhanh.

Ngoài UI, có thể quan sát bằng lệnh trong container:

~~~bash
docker compose exec rabbitmq rabbitmqctl list_exchanges name type
docker compose exec rabbitmq rabbitmqctl list_queues name messages_ready messages_unacknowledged consumers
docker compose exec rabbitmq rabbitmqctl list_bindings
~~~

Lệnh **rabbitmqctl list_queues** thường hiển thị danh sách thuộc virtual host mặc định nếu không chỉ định vhost; trong bài này vhost là **/**. Khi làm việc với nhiều virtual host, cần chỉ định đúng phạm vi nếu muốn kiểm tra queue khác.

**Quan sát hệ thống là một phần của độ tin cậy**: broker chạy khỏe chưa đủ; còn cần biết queue có tồn đọng hay không, consumer có kết nối hay không, số lượng message unacked có tăng liên tục hay không, và liệu message lỗi có bị chuyển sang dead-letter queue theo chính sách dự kiến.

## 9. Kiểm tra tính bền qua vòng đời container

Phân biệt các lệnh để tránh mất dữ liệu ngoài ý muốn:

| Lệnh | Điều xảy ra |
| --- | --- |
| **docker compose stop** | Dừng container, giữ lại container và volume. |
| **docker compose start** | Khởi động lại container đã dừng. |
| **docker compose restart rabbitmq** | Khởi động lại service RabbitMQ. |
| **docker compose down** | Dừng và xóa container/network do Compose quản lý; named volume vẫn được giữ theo mặc định. |
| **docker compose up -d** | Tạo lại hoặc khởi chạy service từ cấu hình hiện có. |
| **docker compose down -v** | Xóa cả named volume của Compose; dữ liệu RabbitMQ trong volume sẽ mất. |

Thử thực hành:

1. Tắt ứng dụng Spring Boot để không có consumer lấy message.
2. Publish một message thông qua Management UI tới **lab.events**, kiểm tra hai queue có message **Ready**.
3. Chạy **docker compose restart rabbitmq**.
4. Truy cập lại Management UI và kiểm tra exchange, queue cùng message còn đó trong điều kiện đã khai báo durable, message persistent và volume còn nguyên.

Đối với message publish từ Management UI, cần **chọn thuộc tính delivery mode persistent** khi thực hiện thử nghiệm bền dữ liệu. Nếu bạn chỉ publish message transient rồi khởi động lại broker, không thể dùng kết quả đó để kết luận cơ chế durable hoạt động sai.

**Phân biệt ba mức độ:**

- **Durable exchange:** định nghĩa exchange có thể tồn tại qua restart.
- **Durable queue:** định nghĩa queue có thể tồn tại qua restart.
- **Persistent message:** message có yêu cầu được lưu bền tại broker trong queue thích hợp. Kết hợp các tùy chọn này vẫn cần xét publisher confirms, loại queue và các kịch bản lỗi khi thiết kế độ tin cậy thực tế.

Với RabbitMQ, thay đổi **RABBITMQ_DEFAULT_USER** hoặc **RABBITMQ_DEFAULT_PASS** trong Compose thường **không đặt lại** người dùng đã được lưu trong volume cũ; các biến mặc định này chủ yếu áp dụng lúc khởi tạo broker mới. Nếu cần đổi mật khẩu khi volume đã tồn tại, hãy dùng công cụ quản lý user của RabbitMQ hoặc chủ động tạo lại môi trường thực hành khi không cần dữ liệu cũ.

## 10. Sự cố thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/xử lý |
| --- | --- | --- |
| **Cannot connect to Docker daemon** | Docker Engine chưa chạy hoặc CLI trỏ sai Docker context | Kiểm tra Docker Desktop/Engine, **docker info**, context Docker đang chọn. |
| **Port is already allocated** ở 5672 hoặc 15672 | Dịch vụ khác đã chiếm cổng trên máy host | Tắt dịch vụ xung đột hoặc đổi **cổng phía host**, rồi cập nhật cấu hình Spring Boot/URL UI. |
| **http://localhost:15672** không mở | Container chưa ready, lỗi startup, sai cổng đã ánh xạ | Dùng **docker compose ps**, **docker compose logs rabbitmq** và kiểm tra healthcheck. |
| **ACCESS_REFUSED / login failed** | Sai user/password hoặc tài khoản/permission của volume cũ khác cấu hình hiện tại | Kiểm tra tài khoản thực trên broker, vhost; nhớ biến **RABBITMQ_DEFAULT_*** không tự ghi đè user đã tồn tại. |
| **Connection refused** từ Spring Boot | Sai host/cổng hoặc broker chưa chạy | Ứng dụng trên host dùng **localhost:5672**; ứng dụng trong Compose network dùng **rabbitmq:5672**. |
| **NOT_FOUND - no exchange/queue** | Chưa khai báo topology hoặc sai vhost/tên | Kiểm tra **Exchanges**, **Queues**, **Bindings**, vhost và bean khai báo. |
| **PRECONDITION_FAILED - inequivalent arg** | Khai báo lại queue/exchange cùng tên nhưng khác thuộc tính | So sánh kiểu queue, durable, auto-delete và các argument; đồng bộ topology trước khi chạy lại. |
| Publish thành công nhưng queue không có message | Exchange không có binding khớp, consumer đã xử lý rất nhanh hoặc message bị loại | Kiểm tra binding, routing key, consumer, message rates và chính sách TTL/limit. |
| Queue tăng **Ready**, không có consumer | Listener chưa chạy hoặc đang nghe queue khác | Kiểm tra **@RabbitListener**, connection, tên queue và log ứng dụng. |
| Queue tăng **Unacked**, không giảm | Consumer nhận nhưng chưa ack, xử lý chậm hoặc bị kẹt | Kiểm tra log listener, prefetch, thời gian xử lý và chính sách ack/retry. |

### Đổi cổng host khi máy đã dùng 5672 hoặc 15672

Bạn có thể thay riêng phần cổng **bên trái** trong Compose:

~~~yaml
ports:
  - "127.0.0.1:5673:5672"
  - "127.0.0.1:15673:15672"
~~~

Khi đó Spring Boot chạy trên host kết nối **localhost:5673**, còn Management UI mở tại **http://localhost:15673**. Nếu Spring Boot chạy trong cùng Compose network, nó vẫn dùng **rabbitmq:5672** vì cổng nội bộ không thay đổi. Sau khi chỉnh cấu hình, chạy lại **docker compose up -d** để Compose áp dụng thay đổi container.

### Xem log nhanh khi có lỗi

~~~bash
docker compose ps
docker compose logs --tail=200 rabbitmq
docker compose exec rabbitmq rabbitmq-diagnostics -q check_running
~~~

Nếu container đã thoát nên không thể dùng **exec**, ưu tiên xem **docker compose logs rabbitmq** để tìm nguyên nhân khởi động thất bại.

## 11. Dừng môi trường và vệ sinh sau khi thực hành

Khi muốn giữ dữ liệu cho buổi học tiếp theo:

~~~bash
docker compose down
~~~

Lần sau, trong cùng thư mục:

~~~bash
docker compose up -d
~~~

Chỉ khi đã xác định không cần **bất kỳ** dữ liệu thực hành nào trong named volume, mới dùng:

~~~bash
docker compose down -v
~~~

Lệnh có **-v** xóa dữ liệu RabbitMQ trong volume liên quan, bao gồm queue, message và định nghĩa đã lưu. Đây là thao tác dọn sạch môi trường học tập, không phù hợp khi bạn muốn tiếp tục kiểm chứng persistence.

## 12. Bước tiếp theo khi học Spring AMQP

Từ môi trường vừa dựng, có thể mở rộng dần các bài thực hành:

| Chủ đề tiếp theo | Cách thử trong môi trường này |
| --- | --- |
| **Direct / topic exchange** | Tạo exchange và binding key, publish với các routing key khác nhau; quan sát queue nào nhận. |
| **Competing consumers** | Chạy hai instance listener cùng nghe một queue và quan sát cách chúng chia việc. |
| **Publisher confirms / returns** | Bật cấu hình phía publisher và thử gửi đến exchange/routing không tồn tại hoặc không khớp; quan sát kết quả theo từng cơ chế. |
| **Consumer ack / nack** | Cho listener xử lý lỗi có kiểm soát; theo dõi Ready/Unacked và redelivery. |
| **Retry / dead-letter** | Khai báo retry policy, dead-letter exchange và dead-letter queue; quan sát thông điệp lỗi. |
| **Giao dịch / tính nhất quán** | Phân tích việc publish message và ghi database có thể thất bại độc lập; cân nhắc cơ chế đảm bảo nhất quán phù hợp. |
| **Monitoring** | Theo dõi backlog, consumer count, unacked, connections và tốc độ publish/ack trong Management UI. |

**Kiểm tra kết quả bài thực hành:**

1. Docker Compose hiển thị RabbitMQ đang chạy và healthcheck thành công.
2. Có thể đăng nhập **http://localhost:15672** bằng tài khoản thực hành.
3. Exchange **lab.events** có hai binding đến **lab.email** và **lab.audit**.
4. Một lần publish tạo message trong **cả hai queue** khi chưa có consumer.
5. Ứng dụng Spring Boot kết nối bằng **localhost:5672**, RabbitTemplate gửi và hai @RabbitListener nhận sự kiện.
6. Có thể dùng Management UI hoặc **rabbitmqctl** để xem queue, binding, consumer và Ready/Unacked.

Khi đạt được các mục trên, môi trường đã sẵn sàng để học sâu hơn về định tuyến, xác nhận giao nhận, retry, dead-letter, giao dịch và quan sát hệ thống trong **Spring AMQP**.
