# Cấu hình host, port, virtual host và tài khoản kết nối

Trong chương **Khởi tạo** của **SPRING_AMQP**, bước đầu tiên để Spring Boot dùng được **RabbitTemplate** và **@RabbitListener** là kết nối đúng đến RabbitMQ. Các tham số **host**, **port**, **virtual host (vhost)**, **username** và **password** xác định ứng dụng kết nối tới broker nào, đi vào không gian tài nguyên nào và được phép làm gì.

Bài này thực hành cấu hình một kết nối hoạt động từ đầu đến cuối: chạy RabbitMQ, khai báo thuộc tính kết nối trong Spring Boot, gửi message bằng RabbitTemplate, nhận bằng @RabbitListener và xử lý các lỗi kết nối thường gặp. Đây là nền tảng để học tiếp exchange, queue, binding, xác nhận giao nhận, retry, dead-letter, giao dịch và giám sát xử lý bất đồng bộ.

## 1. Năm thông tin quan trọng của kết nối

~~~mermaid
flowchart LR
    A["Spring Boot<br/>RabbitTemplate / @RabbitListener"] -->|"AMQP / TCP"| C["ConnectionFactory<br/>host + port + credentials + vhost"]
    C --> B["RabbitMQ broker<br/>cổng 5672 (AMQP)"]
    B --> V["Virtual host: app_dev"]
    V --> E["Exchange"]
    E --> Q["Queue"]
    M["Browser quản trị"] -.->|"HTTP: cổng 15672"| B
~~~

| Thuộc tính | Ý nghĩa | Ví dụ môi trường local |
|---|---|---|
| **host** | Tên DNS hoặc địa chỉ IP của máy/container chạy RabbitMQ | **localhost** |
| **port** | Cổng nhận kết nối giao thức AMQP | **5672** |
| **virtual-host** | Không gian logic chứa exchange, queue, binding và quyền truy cập | **app_dev** |
| **username** | Tài khoản RabbitMQ dùng để xác thực ứng dụng | **learn_amqp** |
| **password** | Mật khẩu của tài khoản RabbitMQ | Cung cấp qua biến môi trường |

Đừng nhầm hai cổng phổ biến:

- **5672**: AMQP qua TCP, là cổng ứng dụng Spring AMQP thường sử dụng.
- **15672**: HTTP của RabbitMQ Management UI, dùng mở trình duyệt quản trị khi plugin Management hoạt động.
- **5671**: cổng AMQPS thường dùng khi broker cấu hình AMQP qua TLS. Cổng này chỉ hoạt động nếu listener TLS đã được thiết lập.

**Virtual host không phải hostname.** Một broker có thể có nhiều vhost độc lập, chẳng hạn **app_dev** và **app_prod**. Queue **orders.q** trong **app_dev** là tài nguyên khác queue có cùng tên trong **app_prod**. Ứng dụng không thể tự động truy cập queue của vhost khác qua cùng một kết nối.

RabbitMQ có vhost mặc định là **/**. Muốn sử dụng vhost này, cấu hình **virtual-host: "/"**; không tự suy luận vhost từ tên máy hoặc thư mục của dự án.

## 2. Chuẩn bị RabbitMQ cho môi trường phát triển

Có thể dùng một broker RabbitMQ đang tồn tại hoặc chạy broker local bằng Docker Compose. Ví dụ sau tạo tài khoản **learn_amqp**, mật khẩu thử nghiệm **dev_only_123**, và vhost **app_dev**.

~~~yaml
# compose.yaml
services:
  rabbitmq:
    image: rabbitmq:4-management
    hostname: rabbitmq
    environment:
      RABBITMQ_DEFAULT_USER: learn_amqp
      RABBITMQ_DEFAULT_PASS: dev_only_123
      RABBITMQ_DEFAULT_VHOST: app_dev
    ports:
      - "5672:5672"
      - "15672:15672"
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq

volumes:
  rabbitmq_data:
~~~

Chạy broker trong thư mục chứa file Compose:

~~~bash
docker compose up -d
docker compose ps
~~~

Mở **http://localhost:15672** và đăng nhập bằng **learn_amqp / dev_only_123**. Trong trang quản trị, kiểm tra vhost **app_dev** đã có và người dùng **learn_amqp** có quyền với vhost đó.

Các giá trị mật khẩu viết trực tiếp ở đây **chỉ dành cho bài thực hành local**. Với môi trường dùng chung hoặc production, dùng secret manager hoặc cơ chế inject secret của nền tảng triển khai; tránh commit mật khẩu thật lên Git.

**Lưu ý về volume:** biến **RABBITMQ_DEFAULT_USER**, **RABBITMQ_DEFAULT_PASS** và **RABBITMQ_DEFAULT_VHOST** dùng để thiết lập mặc định khi database của RabbitMQ được khởi tạo. Nếu volume đã chứa dữ liệu từ lần chạy trước, thay các biến này không nhất thiết cập nhật user/vhost đã tồn tại. Khi đó hãy kiểm tra hoặc điều chỉnh trực tiếp bằng công cụ quản trị, không tự ý xóa volume có dữ liệu.

### 2.1. Host thay đổi theo nơi chạy ứng dụng

| Spring Boot chạy ở đâu? | Host thường sử dụng | Vì sao? |
|---|---|---|
| Trên máy tính cá nhân, RabbitMQ publish cổng 5672 ra máy | **localhost** | Port mapping của Docker chuyển kết nối đến broker |
| Trong một container thuộc cùng Docker Compose network với RabbitMQ | **rabbitmq** | DNS của Compose nhận diện service theo tên |
| Trên máy chủ khác | DNS/IP của broker được phép truy cập | **localhost** sẽ trỏ về chính máy chạy ứng dụng |
| Trong Kubernetes | DNS của Service RabbitMQ | Ứng dụng truy cập qua Service trong cluster |

Nếu **Spring Boot nằm trong container**, **localhost** là container Spring Boot, không phải container RabbitMQ. Đây là một trong những nguyên nhân phổ biến dẫn đến lỗi **Connection refused** dù RabbitMQ đang chạy.

## 3. Thêm Spring AMQP vào Spring Boot

Với dự án Maven sử dụng Spring Boot, thêm starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Starter cung cấp tích hợp RabbitMQ, RabbitTemplate, container cho listener và cấu hình kết nối. Khi có starter và các thuộc tính phù hợp, Spring Boot tự cấu hình **ConnectionFactory**, **RabbitTemplate** và các thành phần listener thông dụng.

Ở cấp độ triển khai:

- **ConnectionFactory** quản lý cách tạo và tái sử dụng kết nối/channel tới RabbitMQ.
- **RabbitTemplate** dùng ConnectionFactory để gửi message hoặc thực hiện một số thao tác AMQP.
- **@RabbitListener** nhận message thông qua listener container, cũng dùng kết nối đến broker.
- **Exchange, queue, binding** được khai báo bên trong **vhost** mà kết nối đã chọn. Có cấu hình đúng host và tài khoản nhưng sai vhost thì ứng dụng vẫn có thể không tìm thấy queue mong đợi.

Thông thường chỉ cần cấu hình thuộc tính **spring.rabbitmq**. Không cần tự viết một **ConnectionFactory** khác nếu không có yêu cầu đặc biệt.

## 4. Cấu hình application.yml

Ví dụ file **src/main/resources/application.yml**:

~~~yaml
spring:
  rabbitmq:
    host: ${RABBITMQ_HOST:localhost}
    port: ${RABBITMQ_PORT:5672}
    virtual-host: ${RABBITMQ_VHOST:app_dev}
    username: ${RABBITMQ_USERNAME:learn_amqp}
    password: ${RABBITMQ_PASSWORD}
    connection-timeout: 10s
    requested-heartbeat: 30s
~~~

Spring Boot phân giải cú pháp **${ENV_NAME:default}** theo thứ tự: đọc giá trị từ môi trường nếu có, nếu không thì dùng **default**. Riêng **${RABBITMQ_PASSWORD}** không có giá trị mặc định, vì vậy cần cấp mật khẩu từ môi trường hoặc nguồn cấu hình tương đương.

Ví dụ trên phù hợp với broker Docker Compose ở mục 2. Với ứng dụng chạy trên máy cá nhân, những biến bắt buộc chỉ cần:

**Linux/macOS (terminal shell):**

~~~bash
export RABBITMQ_PASSWORD='dev_only_123'
~~~

**Windows PowerShell:**

~~~powershell
$env:RABBITMQ_PASSWORD = 'dev_only_123'
~~~

Sau khi đặt biến môi trường, chạy ứng dụng Spring Boot từ cùng môi trường shell hoặc cấu hình biến trong phần Run/Debug của IDE. Nếu RabbitMQ và ứng dụng nằm trong cùng Docker Compose network, đặt thêm **RABBITMQ_HOST=rabbitmq**.

### 4.1. Ý nghĩa các thuộc tính Spring Boot

| Property | Giá trị minh họa | Vai trò |
|---|---|---|
| **spring.rabbitmq.host** | **localhost** | Địa chỉ của broker |
| **spring.rabbitmq.port** | **5672** | Cổng kết nối AMQP |
| **spring.rabbitmq.virtual-host** | **app_dev** | Chọn không gian exchange/queue/binding |
| **spring.rabbitmq.username** | **learn_amqp** | Danh tính ứng dụng |
| **spring.rabbitmq.password** | Biến môi trường | Xác thực danh tính |
| **spring.rabbitmq.connection-timeout** | **10s** | Giới hạn thời gian chờ mở kết nối |
| **spring.rabbitmq.requested-heartbeat** | **30s** | Đề xuất chu kỳ heartbeat AMQP để phát hiện kết nối bị gián đoạn |

Tham số **requested-heartbeat** giúp các bên phát hiện một số sự cố mất kết nối; nó **không** thay thế ACK, publisher confirm hoặc cơ chế xử lý lại message.

Ngoài cú pháp YAML, có thể dùng biến môi trường Spring Boot trực tiếp, chẳng hạn **SPRING_RABBITMQ_HOST**, **SPRING_RABBITMQ_PORT**, **SPRING_RABBITMQ_VIRTUAL_HOST**, **SPRING_RABBITMQ_USERNAME**, **SPRING_RABBITMQ_PASSWORD**. Cần thống nhất một nguồn cấu hình để tránh nhầm giá trị đang có hiệu lực.

### 4.2. Cấu hình nhiều địa chỉ broker

Nếu cần khai báo nhiều endpoint RabbitMQ, Spring Boot hỗ trợ thuộc tính **spring.rabbitmq.addresses**:

~~~yaml
spring:
  rabbitmq:
    addresses: ${RABBITMQ_ADDRESSES:rabbit-1.example:5672,rabbit-2.example:5672}
    virtual-host: ${RABBITMQ_VHOST:app_dev}
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
~~~

Khi dùng **addresses**, danh sách này được ưu tiên thay cho một cặp **host/port** đơn lẻ. Các địa chỉ phải thực sự trỏ đến những node/endpoint RabbitMQ phù hợp; việc cung cấp nhiều địa chỉ **không tự động tạo một cluster** hay bảo đảm message được sao chép giữa các node.

Nếu sử dụng URI AMQP để khai báo kết nối, các ký tự đặc biệt trong username, password và vhost phải được mã hóa đúng theo cú pháp URI. Với cấu hình cơ bản, các property riêng lẻ thường dễ kiểm tra hơn.

## 5. Virtual host và quyền của tài khoản

Một người dùng có thể đăng nhập thành công vào RabbitMQ nhưng vẫn **không được phép truy cập vhost**. RabbitMQ tách xác thực (authentication) khỏi phân quyền (authorization).

~~~mermaid
flowchart TD
    A["Ứng dụng yêu cầu kết nối"] --> B{"Host:port có kết nối được?"}
    B -->|"Không"| C["Kiểm tra DNS, mạng, listener và firewall"]
    B -->|"Có"| D{"Username/password hợp lệ?"}
    D -->|"Không"| E["Lỗi xác thực"]
    D -->|"Có"| F{"Vhost tồn tại và user có quyền?"}
    F -->|"Không"| G["Lỗi truy cập vhost"]
    F -->|"Có"| H["Có thể dùng exchange/queue theo quyền cụ thể"]
~~~

Với các user và vhost do Docker Compose ở mục 2 khởi tạo, người dùng thử nghiệm có thể truy cập vhost **app_dev**. Khi tạo tài khoản thủ công trên broker khác, quản trị viên phải cấp quyền riêng.

Ví dụ lệnh chạy bằng **rabbitmqctl** trong môi trường quản trị của RabbitMQ:

~~~bash
rabbitmqctl add_vhost app_dev
rabbitmqctl add_user app_worker 'replace-with-a-secret'
rabbitmqctl set_permissions -p app_dev app_worker '.*' '.*' '.*'
~~~

Ba biểu thức cuối của **set_permissions** tương ứng quyền **configure**, **write** và **read**. Mẫu regex `.*` khớp với mọi tên tài nguyên phù hợp trong vhost và **chỉ phù hợp để minh họa hoặc thực hành**. Trong production cần thu hẹp quyền theo exchange/queue và vai trò cụ thể của service.

Nếu vhost **app_dev** hoặc user **app_worker** đã có, các lệnh **add_vhost/add_user** tương ứng có thể báo tồn tại. Không chạy lại các lệnh tạo mà không kiểm tra trạng thái broker.

Một số nguyên tắc tổ chức:

- Mỗi môi trường hoặc nhóm ứng dụng có thể dùng vhost riêng để giảm nhầm lẫn tài nguyên.
- Dùng tài khoản ứng dụng riêng, chỉ cấp quyền ở những vhost và tài nguyên cần thiết.
- Tài khoản chỉ publish vào exchange không nhất thiết phải có cùng quyền như listener đọc queue.
- Vhost là ranh giới quản lý tài nguyên và phân quyền; nó **không phải** một broker vật lý khác hay một cơ chế cô lập hiệu năng tuyệt đối.

**Tài khoản guest:** RabbitMQ thường tạo tài khoản **guest/guest** ban đầu và mặc định hạn chế tài khoản này với kết nối loopback. Vì vậy, ứng dụng từ máy/container khác có thể bị từ chối dù mật khẩu đúng. Nên tạo user riêng như **learn_amqp** thay vì nới lỏng quyền truy cập của guest.

## 6. Kiểm chứng bằng RabbitTemplate và @RabbitListener

Việc ứng dụng khởi động được **chưa đủ chứng minh** toàn bộ cấu hình đã hoạt động. Tùy thời điểm mở kết nối, lỗi mạng hoặc phân quyền có thể chỉ xuất hiện khi producer, listener hoặc bước khai báo queue thực sự kết nối tới broker. Hãy thử một vòng gửi và nhận message.

### 6.1. Khai báo một queue dùng để kiểm tra

~~~java
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableRabbit
public class RabbitSetupConfig {
    public static final String CHECK_QUEUE = "setup.connection.check.q";

    @Bean
    public Queue connectionCheckQueue() {
        return QueueBuilder.durable(CHECK_QUEUE).build();
    }
}
~~~

Ở cấu hình Spring Boot thông dụng, **RabbitAdmin** của Spring AMQP có thể tự khai báo queue bean này trên broker khi có kết nối. Queue được tạo **bên trong vhost app_dev**, vì ConnectionFactory đã chọn vhost đó. Queue durable sẽ tồn tại sau khi RabbitMQ khởi động lại, nhưng độ bền message còn phụ thuộc loại message và chiến lược bảo đảm giao nhận.

### 6.2. Gửi một message khi ứng dụng sẵn sàng

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SetupProbePublisher {
    @Bean
    ApplicationRunner publishProbe(RabbitTemplate rabbitTemplate) {
        return args -> rabbitTemplate.convertAndSend(
                "",
                RabbitSetupConfig.CHECK_QUEUE,
                "hello-from-spring-amqp"
        );
    }
}
~~~

Đối số đầu tiên là **""** (tên rỗng của default exchange), đối số thứ hai là **routing key** trùng tên queue. Trong RabbitMQ, default exchange định tuyến message tới queue bằng tên queue khi queue đó tồn tại.

Cách này dùng để thử cấu hình kết nối tối thiểu. Ở bài về exchange và binding, bạn có thể thay default exchange bằng direct/topic exchange tự khai báo.

### 6.3. Nhận message qua @RabbitListener

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class SetupProbeListener {
    @RabbitListener(queues = RabbitSetupConfig.CHECK_QUEUE)
    public void receive(String body) {
        System.out.println("RabbitMQ received: " + body);
    }
}
~~~

Khởi chạy ứng dụng có ba lớp này và cấu hình ở mục 4. Nếu kết nối, vhost và quyền đều đúng, listener sẽ ghi nội dung tương tự:

~~~text
RabbitMQ received: hello-from-spring-amqp
~~~

Listener mặc định của Spring Boot thường được cấu hình theo cơ chế container tự ACK sau khi xử lý thành công (**AcknowledgeMode.AUTO**); đó không phải chế độ broker tự ACK ngay khi giao. Bài kiểm tra này chỉ xác minh luồng kết nối cơ bản, chưa kiểm thử manual ACK, retry hay xử lý mất kết nối.

Trong RabbitMQ Management UI, chọn đúng **vhost app_dev**, tìm queue **setup.connection.check.q** và quan sát consumer cùng các chỉ số **Ready/Unacked**. Với ví dụ đơn giản, message có thể được tiêu thụ rất nhanh nên không thấy tồn đọng.

**Nếu publish thất bại nhưng RabbitMQ đang chạy:** kiểm tra Spring Boot có dùng đúng username, password và vhost hay không. **Nếu publish thành công mà listener không nhận:** kiểm tra queue trong đúng vhost, listener container, quyền read và log lỗi của ứng dụng.

## 7. Các lỗi thường gặp và cách xác định nguyên nhân

| Triệu chứng / lỗi | Khả năng thường gặp | Cách kiểm tra |
|---|---|---|
| **Connection refused** | Sai host/port; broker chưa lắng nghe; port chưa publish | Kiểm tra container, cổng 5672, firewall và địa chỉ đang dùng |
| **UnknownHostException** | Tên host không phân giải được | Dùng DNS phù hợp môi trường; trong Compose dùng tên service **rabbitmq** |
| **ACCESS_REFUSED - Login was refused** | Sai username/password, user bị hạn chế hoặc không tồn tại | Kiểm tra user, secret và hạn chế của **guest** |
| **access to vhost ... refused** | Vhost không tồn tại hoặc user thiếu quyền | Kiểm tra đúng tên vhost và quyền của user trên vhost |
| **NOT_FOUND - no queue** | Queue chưa được khai báo hoặc đang tìm trong vhost khác | Kiểm tra tên queue, quá trình declare và vhost hiện tại |
| **access to queue/exchange refused** | User không đủ quyền read/write/configure | Kiểm tra permission pattern theo đúng tài nguyên |
| **SSLHandshakeException** | TLS không khớp, chứng chỉ/trust không hợp lệ | Kiểm tra cổng TLS, bật TLS đúng phía client và xác minh chứng chỉ |
| Mở **localhost:5672** trên trình duyệt không thấy UI | Dùng cổng AMQP thay vì HTTP Management | Mở **http://localhost:15672** |

Khi dùng Docker Compose ở mục 2, các lệnh hỗ trợ kiểm tra là:

~~~bash
docker compose ps
docker compose logs rabbitmq
docker compose exec rabbitmq rabbitmq-diagnostics listeners
docker compose exec rabbitmq rabbitmqctl list_vhosts
docker compose exec rabbitmq rabbitmqctl list_permissions -p app_dev
~~~

**Không in hoặc gửi log chứa mật khẩu thật** vào công cụ chia sẻ công khai. Nếu broker được cung cấp bởi dịch vụ managed, thực hiện các bước kiểm tra tương đương bằng console hoặc API của dịch vụ đó.

### 7.1. Kết nối thành công nhưng vẫn không gửi/nhận được

Đừng kết luận chỉ từ việc đăng nhập được Management UI. Đó là kết nối HTTP, còn Spring AMQP dùng một kết nối AMQP khác. Cả hai có thể cùng được xác thực bởi RabbitMQ nhưng đi qua cổng, đường mạng và quyền thao tác khác nhau.

Ngoài ra, kết nối mở thành công không chứng minh message đã được route đến queue hoặc đã xử lý xong. Các bước sau còn cần **routing key/binding**, **publisher confirm/return**, **consumer acknowledgment**, retry, DLQ và cơ chế xử lý trùng tùy mục tiêu độ tin cậy của hệ thống.

## 8. Kết nối bảo mật và vận hành thực tế

### 8.1. Kết nối qua TLS

Khi RabbitMQ được cấu hình AMQPS, có thể bật TLS trên client và sử dụng đúng cổng mà broker cung cấp; cổng phổ biến là **5671**:

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.example.internal
    port: 5671
    virtual-host: app_prod
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    ssl:
      enabled: true
~~~

Ví dụ này giả định RabbitMQ đã có **TLS listener**, chứng chỉ máy chủ hợp lệ và ứng dụng tin cậy chuỗi chứng chỉ đó. Các môi trường dùng CA nội bộ hoặc mutual TLS cần cấu hình trust/certificate tương ứng. Không nên vô hiệu hóa xác thực chứng chỉ hoặc hostname để “sửa nhanh” lỗi kết nối.

### 8.2. Phân biệt kết nối lại và retry message

- **Connection recovery:** ứng dụng và thư viện có thể thử kết nối lại khi broker/network gián đoạn; thông số host/port/TLS phải đúng trước khi cơ chế này có hiệu quả.
- **Publisher confirm:** dùng để biết broker đã xác nhận một publish theo cơ chế được cấu hình; không đồng nghĩa consumer đã xử lý xong.
- **Consumer ACK:** cho broker biết delivery đã được xử lý theo chính sách của listener.
- **Message retry và DLQ:** xử lý lỗi khi logic tiêu thụ message thất bại; cần giới hạn số lần thử và tránh vòng lặp lỗi vô hạn.
- **Idempotency:** cần thiết vì delivery chưa ACK có thể được giao lại sau một sự cố kết nối.

Việc cài host, port, vhost và tài khoản chính xác là **điều kiện cần**, chưa phải đầy đủ để đạt xử lý bất đồng bộ đáng tin cậy.

### 8.3. Quản lý cấu hình theo môi trường

Một cách triển khai thường dùng:

| Môi trường | Host | Virtual host | Tài khoản |
|---|---|---|---|
| Local | **localhost** hoặc **rabbitmq** | **app_dev** | User riêng dùng cho học tập |
| Staging | DNS broker staging | **app_staging** | User của ứng dụng staging |
| Production | DNS/service broker production | **app_prod** | User riêng, secret được quản lý tập trung |

Tránh hardcode thông tin production trong mã nguồn. Có thể dùng profile Spring Boot, biến môi trường hoặc secret manager; khi đổi môi trường cần kiểm tra cả **host, port, vhost, username, password**, giao thức TLS và permission trên broker.

## 9. Bài tập tự thực hành

1. Chạy RabbitMQ với **app_dev** như mục 2, khởi động Spring Boot trên máy và xác nhận listener nhận **hello-from-spring-amqp**.
2. Đổi **RABBITMQ_VHOST** sang một vhost chưa tồn tại. Ghi lại thông báo lỗi và giải thích vì sao broker vẫn chạy mà ứng dụng không vào được queue.
3. Khôi phục vhost rồi cố ý đặt sai **RABBITMQ_PASSWORD**. So sánh lỗi xác thực với lỗi mạng khi đổi **port** sang một cổng không lắng nghe.
4. Đưa ứng dụng vào cùng Compose network với RabbitMQ, đổi **RABBITMQ_HOST** từ **localhost** sang **rabbitmq**. Giải thích DNS của Compose.
5. Tạo vhost mới và tài khoản riêng, chỉ cấp quyền cần thiết; thử thao tác publish và consume để thấy ranh giới permission.
6. Trong Management UI, tìm queue ở hai vhost khác nhau (nếu đã tạo) và giải thích vì sao cùng tên queue không có nghĩa là cùng dữ liệu.

**Tự kiểm tra:** nếu thấy broker ở **http://localhost:15672** nhưng Spring Boot không kết nối được **localhost:5672**, bạn cần xác minh điều gì trước? Nếu thông tin đăng nhập đúng nhưng báo không truy cập được **app_dev**, vì sao việc thay password có thể không giải quyết được?

## 10. Những điều cần nhớ

- **Host + port** định vị listener AMQP của RabbitMQ; **vhost** chọn không gian tài nguyên; **username/password** xác thực ứng dụng và quyền của user quyết định thao tác được phép.
- **localhost**, **rabbitmq** và DNS của broker từ xa chỉ đúng trong những bối cảnh mạng cụ thể; kiểm tra ứng dụng thực sự chạy ở đâu.
- **5672** dùng cho AMQP, **15672** cho Management UI, **5671** thường dùng cho AMQPS khi đã cấu hình TLS.
- **spring.rabbitmq** là điểm cấu hình tiêu chuẩn trong Spring Boot; cung cấp password qua môi trường/secret và dùng tài khoản riêng cho ứng dụng.
- Kiểm chứng kết nối bằng **publish + consume thực tế**, rồi mới xây tiếp exchange/binding, xác nhận giao nhận, retry, DLQ và xử lý lỗi cho hệ thống bất đồng bộ.
