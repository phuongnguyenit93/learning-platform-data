# CachingConnectionFactory và tái sử dụng connection/channel

## Mục tiêu bài học

Trong module **SPRING_AMQP**, chúng ta dùng **RabbitTemplate** để phát message, **@RabbitListener** để nhận message, và các **exchange, queue, binding** để định tuyến qua RabbitMQ. Ở phía dưới những API ấy là kết nối TCP và các **AMQP channel**. Nếu mỗi lần gửi một message lại mở kết nối TCP mới, hiệu năng giảm và broker phải liên tục cấp phát tài nguyên. Nếu giữ và chia sẻ channel không đúng cách, ứng dụng lại dễ gặp lỗi khi xử lý đồng thời.

**CachingConnectionFactory** là thành phần của Spring AMQP giúp quản lý và tái sử dụng connection/channel. Sau bài học, bạn có thể:

1. Phân biệt **connection** và **channel**, hiểu tại sao RabbitMQ cho phép nhiều channel trên một connection.
2. Giải thích cách **CachingConnectionFactory** quản lý connection, cache channel và hành vi **close()**.
3. Phân biệt **CacheMode.CHANNEL** (mặc định) với **CacheMode.CONNECTION**.
4. Cấu hình **channelCacheSize**, **channelCheckoutTimeout**, **connectionCacheSize**, **connectionLimit** và hiểu các giới hạn thực tế.
5. Phân tích cách **RabbitTemplate**, **@RabbitListener**, **RabbitAdmin**, publisher confirms và transaction sử dụng tài nguyên.
6. Chẩn đoán thiếu channel, kết nối bị ngắt, tăng số connection bất thường và các lỗi khi khai báo tài nguyên.

## 1. Connection và channel là hai tầng khác nhau

Một **AMQP connection** là kết nối TCP lâu dài từ ứng dụng đến RabbitMQ. Trên kết nối này, client có thể mở nhiều **AMQP channel** để gửi lệnh publish, consume, declare, ACK và thực hiện các thao tác khác.

~~~mermaid
flowchart LR
    subgraph APP["Ứng dụng Spring"]
        T["RabbitTemplate"]
        L1["@RabbitListener #1"]
        L2["@RabbitListener #2"]
        A["RabbitAdmin"]
        CF["CachingConnectionFactory"]
        T --> CF
        L1 --> CF
        L2 --> CF
        A --> CF
    end
    CF -->|"TCP connection"| B["RabbitMQ broker"]
    B --> C1["AMQP channel: publish"]
    B --> C2["AMQP channel: consumer 1"]
    B --> C3["AMQP channel: consumer 2"]
    B --> C4["AMQP channel: declare"]
~~~

Sơ đồ cho thấy về mặt khái niệm nhiều thao tác được **ghép kênh trên một TCP connection**. Các channel thực tế được mở ở hai đầu cùng một kết nối; chúng không phải bốn TCP connection khác nhau.

| Đặc điểm | Connection | Channel |
| --- | --- | --- |
| Bản chất | Kết nối TCP/AMQP giữa client và broker | Phiên logic nằm trong connection |
| Chi phí tạo | Cao hơn: TCP, TLS (nếu có), xác thực, thương lượng thông số | Thấp hơn; vẫn tốn tài nguyên client/broker |
| Một connection có thể chứa | Nhiều channel | Một channel thuộc một connection cụ thể |
| Phạm vi lỗi | Mất connection thường làm **mọi channel bên trong** mất theo | Lỗi giao thức trên một channel có thể chỉ khiến channel đó bị đóng |
| Mục đích | Giữ đường truyền ổn định | Cô lập hoạt động publish, consume, ACK và transaction |
| Dùng đa luồng | Có thể là nền cho nhiều channel | **Không nên chia sẻ trực tiếp một Channel cho các thread publish đồng thời** |

Một channel mở vẫn là tài nguyên thật trên RabbitMQ. Mở hàng trăm connection hoặc hàng chục nghìn channel mà không có nhu cầu có thể tăng chi phí bộ nhớ, CPU, file descriptor và công việc quản lý của broker.

**Không nhầm:** exchange, queue, binding là **tài nguyên định tuyến trên broker**, còn connection/channel là **tài nguyên truyền thông của client**. Tăng số channel không tự tạo thêm queue hoặc làm consumer xử lý đúng thứ tự.

## 2. CachingConnectionFactory giải quyết vấn đề gì?

Spring AMQP cung cấp interface **org.springframework.amqp.rabbit.connection.ConnectionFactory**. Một triển khai thông dụng là **org.springframework.amqp.rabbit.connection.CachingConnectionFactory**.

Khi RabbitTemplate hoặc listener container cần làm việc với RabbitMQ, chúng lấy connection/channel thông qua ConnectionFactory; ứng dụng không cần liên tục tạo và đóng kết nối từ đầu.

### Cơ chế mượn và trả channel

~~~mermaid
sequenceDiagram
    participant App as RabbitTemplate
    participant CF as CachingConnectionFactory
    participant B as RabbitMQ
    App->>CF: Xin channel để publish
    alt Có channel rảnh hợp lệ
        CF-->>App: Tái sử dụng channel từ cache
    else Chưa có channel phù hợp
        CF->>B: Mở channel trên connection
        CF-->>App: Cấp channel mới
    end
    App->>B: Publish message
    App->>CF: close() channel qua proxy
    alt Cache còn chỗ và channel dùng lại được
        CF-->>CF: Đưa channel về cache
    else Cache đầy hoặc channel không hợp lệ
        CF->>B: Đóng channel vật lý
    end
~~~

**close() trên channel proxy do CachingConnectionFactory cấp thường có nghĩa là trả về cache**, không phải luôn đóng ngay channel vật lý. Khi channel cache đầy, channel bị lỗi hoặc không đủ điều kiện tái sử dụng, Spring có thể đóng channel thật.

Ở chế độ cache channel mặc định, **close() trên connection proxy không nhất thiết đóng TCP connection vật lý**; Spring giữ connection để tái sử dụng. Điều này giúp tránh chi phí kết nối lại cho từng thao tác.

**Lưu ý phạm vi quản lý:** cơ chế trên áp dụng cho những channel/connection được lấy thông qua Spring CachingConnectionFactory. Nếu ứng dụng trực tiếp tạo channel từ RabbitMQ Java Client bên ngoài factory, lifecycle của đối tượng đó không tự được cache như channel Spring.

### Vì sao không chia sẻ một channel Java giữa nhiều thread?

RabbitMQ Java Client không khuyến khích các thread cùng publish đồng thời trên một **Channel**; frame có thể đan xen và làm hỏng luồng truyền hoặc gây lỗi khó tái hiện. **CachingConnectionFactory** giúp mỗi thao tác mượn một channel phù hợp, nhưng **không biến một channel duy nhất thành thread-safe cho mọi tác vụ**.

Với ứng dụng Spring, cách thông thường là dùng **một RabbitTemplate singleton** (không sửa cấu hình của nó đồng thời khi đang hoạt động) và để template tự lấy/trả channel. Không lưu một Channel thủ công vào field static hay chia sẻ nó giữa nhiều worker thread.

## 3. Hai chế độ cache: CHANNEL và CONNECTION

**CachingConnectionFactory** có hai chế độ chính:

| Thuộc tính | **CacheMode.CHANNEL** | **CacheMode.CONNECTION** |
| --- | --- | --- |
| Cách tái sử dụng | Một shared connection chính, cache các channel trên connection đó | Có thể cache **nhiều connection**, mỗi connection có cache channel riêng |
| Chế độ mặc định | **Có** | Không |
| Kiểm soát channel | **channelCacheSize**, **channelCheckoutTimeout** | Vẫn dùng **channelCacheSize** cho từng connection |
| Kiểm soát connection | Thường một connection vật lý dùng chung trong factory | **connectionCacheSize**, **connectionLimit**, timeout chờ connection |
| Phù hợp | Đa số Spring Boot service có RabbitTemplate, RabbitAdmin, listener | Tình huống cần quản lý nhiều physical connection qua cùng factory |
| RabbitAdmin tự động declare | Hoạt động theo cơ chế auto-declaration thông thường | **Không hỗ trợ auto-declaration theo cùng cách**; cần provisioning rõ ràng |
| Tác động khi connection hỏng | Channel trên connection đó mất; Spring tạo lại connection/channel | Ảnh hưởng connection cụ thể, nhưng topology và các channel vẫn cần recovery |

### 3.1. CacheMode.CHANNEL — lựa chọn phổ biến

Trong **CHANNEL mode**, CachingConnectionFactory giữ một connection dùng chung và nhiều channel. Khi một thao tác RabbitTemplate hoàn tất, channel có thể được cache để lần gửi sau dùng lại.

~~~text
                    CachingConnectionFactory (CHANNEL)
                                  |
                         1 TCP connection
                                  |
                  +---------------+----------------+
                  |               |                |
             Channel #1      Channel #2       Channel #3
             publish        consumer A       consumer B
                  |
             Trả về cache
             sau publish
~~~

**Một connection dùng chung** nói ở đây là connection chính của factory trong CHANNEL mode. Nếu bật **publisher connection** riêng hoặc khai báo nhiều factory, số TCP connection thực tế có thể nhiều hơn một.

### 3.2. CacheMode.CONNECTION — dùng có chủ đích

Trong **CONNECTION mode**, factory có thể cấp nhiều connection vật lý và cache chúng khi không còn được sử dụng. **Mỗi connection** vẫn có các channel của riêng mình. Chế độ này có thể hữu ích khi một thiết kế cần phân lập nhiều connection cho những thao tác độc lập, nhưng tăng lượng tài nguyên broker phải quản lý.

~~~text
                  CachingConnectionFactory (CONNECTION)
                            /              \
                    Connection A       Connection B
                       /   \               /   \
                    Ch 1   Ch 2          Ch 1   Ch 2
~~~

**Cảnh báo quan trọng:** Spring AMQP ghi rõ **RabbitAdmin auto-declaration không được hỗ trợ trong CONNECTION cache mode**. Nếu service dựa vào bean Queue/Exchange/Binding tự được khai báo trong mỗi lần reconnect, chuyển mode có thể khiến listener không tìm thấy queue. Khi dùng CONNECTION mode, nên cung cấp topology bằng cơ chế provisioning độc lập hoặc quy trình khai báo kiểm soát được.

Ngoài ra, **exclusive queue** thuộc về connection khai báo. Nếu RabbitAdmin tạo queue trên connection A còn consumer dùng connection B, broker có thể trả **RESOURCE_LOCKED**. Vì vậy không mặc định chuyển sang CONNECTION mode để “tăng tốc” khi kiến trúc đang có anonymous/exclusive queue.

## 4. Hiểu đúng các tham số cache

### 4.1. channelCacheSize

**channelCacheSize** quy định số channel nhàn rỗi mà factory có thể giữ trong cache **trên mỗi connection**. Trong trường hợp thông thường (không cấu hình timeout chờ channel), nó **không phải giới hạn cứng cho tổng số channel đang hoạt động**:

- Nếu cache có channel nhàn rỗi, Spring lấy channel đó.
- Nếu không có, Spring có thể tạo channel mới, kể cả khi tổng channel đang dùng vượt channelCacheSize.
- Khi trả channel, nếu cache còn chỗ thì giữ lại; nếu cache đã đầy thì đóng channel vật lý.

Ví dụ, **channelCacheSize=10** không đồng nghĩa chỉ có tối đa 10 thao tác RabbitTemplate chạy đồng thời khi chưa kích hoạt cơ chế giới hạn bằng timeout.

### 4.2. channelCheckoutTimeout thay đổi ngữ nghĩa giới hạn

Khi **channelCheckoutTimeout** được cấu hình lớn hơn 0, **channelCacheSize** trở thành giới hạn số channel có thể được cấp/mở trên một connection trong cơ chế checkout. Khi đạt giới hạn, thread xin channel phải chờ channel được trả; hết thời gian có thể phát sinh **AmqpTimeoutException**.

| Cấu hình minh họa | Diễn giải |
| --- | --- |
| **channelCacheSize=25**, **channelCheckoutTimeout=0** | Giữ tối đa khoảng 25 channel idle; số channel đang mở có thể vượt mức này lúc tải cao |
| **channelCacheSize=25**, **channelCheckoutTimeout=3000 ms** | Giới hạn checkout theo kích thước cache, thread có thể chờ tối đa khoảng 3 giây khi thiếu channel |
| **channelCacheSize=5**, **channelCheckoutTimeout=1000 ms** | Dễ chạm giới hạn nếu listener giữ nhiều channel lâu dài hoặc publisher đồng thời cao |

**Không tăng size một cách tùy tiện:** mỗi channel có chi phí trên broker. Nếu đặt size quá nhỏ kết hợp timeout, có thể làm chậm publish/khởi động consumer; nếu quá lớn, tài nguyên có thể bị giữ nhàn rỗi nhiều. Hãy dựa vào mức đồng thời thực tế và số liệu cache high-water.

### 4.3. connectionCacheSize và connectionLimit

Hai tham số này chủ yếu có ý nghĩa trong **CacheMode.CONNECTION**:

- **connectionCacheSize:** số connection idle mà factory có thể giữ lại để sử dụng tiếp.
- **connectionLimit:** số connection vật lý tối đa mà factory cho phép trong CONNECTION mode.
- **channelCheckoutTimeout:** có thể được dùng làm thời gian chờ khi đạt giới hạn connection và chưa có connection rảnh.

Tương tự channel cache, **connectionCacheSize không mặc nhiên là giới hạn cứng số connection vật lý**. Muốn giới hạn số connection, sử dụng **connectionLimit** theo đúng phiên bản và cấu hình phù hợp.

### 4.4. Bảng ghi nhớ

| Tham số | Câu hỏi | Cần tránh |
| --- | --- | --- |
| **cacheMode** | Cache channel hay connection? | Đổi sang CONNECTION chỉ vì muốn “nhiều consumer hơn” |
| **channelCacheSize** | Cần giữ bao nhiêu channel để tái sử dụng? | Nhầm số channel idle với số worker tối đa |
| **channelCheckoutTimeout** | Có chờ khi không còn channel? | Bật giới hạn cứng nhưng giữ size thấp hơn nhu cầu thực |
| **connectionCacheSize** | Trong CONNECTION mode giữ bao nhiêu connection idle? | Coi đây luôn là giới hạn kết nối |
| **connectionLimit** | Trong CONNECTION mode giới hạn tổng connection ra sao? | Quên cộng chi phí mỗi connection tới broker |
| **publisher confirm / returns** | Producer biết gì sau khi gửi? | Tưởng channel cache bảo đảm message đã được lưu/xử lý |

## 5. Cấu hình thực tế trong Spring Boot

Với Spring Boot dùng Spring AMQP, cách thuận tiện là để Boot khởi tạo CachingConnectionFactory và tinh chỉnh bằng properties. Ví dụ sau minh họa ứng dụng **Spring Boot 3.x** với dependency **spring-boot-starter-amqp**.

### 5.1. Dependency Maven

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Nếu dùng Spring Boot nhánh khác, kiểm tra tên starter và chính sách dependency management tương ứng; không trộn tùy ý các version **spring-rabbit**, **spring-amqp** và Spring Boot.

### 5.2. application.yml: cache channel, kết nối và xác nhận publish

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
    requested-heartbeat: 30s
    connection-timeout: 5s
    cache:
      connection:
        mode: channel
      channel:
        size: 32
        checkout-timeout: 3s
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

**Ý nghĩa:**

- **mode: channel**: giữ connection chính và tái sử dụng channel.
- **channel.size: 32**: kích thước cache và cũng là giới hạn channel checkout nếu timeout > 0.
- **checkout-timeout: 3s**: thao tác chờ channel rảnh khi chạm giới hạn.
- **requested-heartbeat: 30s**: đề xuất heartbeat với broker để phát hiện một số loại đứt kết nối; thời gian thực tế do hai phía thương lượng.
- **publisher-confirm-type: correlated**: bật cơ chế publisher confirm cho producer xử lý kết quả.
- **publisher-returns + mandatory**: cho phép phát hiện message publish không được định tuyến tới queue trong trường hợp thích hợp.

Ví dụ **guest/guest** chỉ dành cho RabbitMQ chạy cục bộ với cấu hình mặc định; môi trường triển khai cần user riêng, secret bên ngoài tệp cấu hình và TLS khi phù hợp.

**Lưu ý:** chỉ bật thuộc tính publisher confirms/returns **chưa đủ** để bảo đảm giao nhận; ứng dụng còn cần xử lý confirm/return, retry, idempotency và trạng thái nghiệp vụ. Các thuộc tính cache cũng không thay thế việc khai báo exchange, queue, binding.

### 5.3. Java config nếu không dùng Boot auto-configuration

Đây là **cách thay thế** cho cấu hình tự động nói trên, chẳng hạn khi ứng dụng Spring tự quản lý ConnectionFactory:

~~~java
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RabbitConnectionConfig {
    @Bean
    public CachingConnectionFactory rabbitConnectionFactory() {
        CachingConnectionFactory factory =
                new CachingConnectionFactory("localhost");

        factory.setPort(5672);
        factory.setCacheMode(
                CachingConnectionFactory.CacheMode.CHANNEL);
        factory.setChannelCacheSize(32);
        factory.setChannelCheckoutTimeout(3_000);

        factory.setPublisherConfirmType(
                CachingConnectionFactory.ConfirmType.CORRELATED);
        factory.setPublisherReturns(true);
        return factory;
    }
}
~~~

Nếu tạo bean ConnectionFactory bằng Java, các property Boot có thể không còn được áp dụng tự động như khi Boot sở hữu bean. Chọn **một nguồn cấu hình nhất quán**; tách credentials và TLS ra khỏi ví dụ.

### 5.4. Tùy chọn CONNECTION mode

~~~java
CachingConnectionFactory factory = new CachingConnectionFactory("localhost");
factory.setCacheMode(CachingConnectionFactory.CacheMode.CONNECTION);
factory.setConnectionCacheSize(2);
factory.setConnectionLimit(6);
factory.setChannelCacheSize(16);
factory.setChannelCheckoutTimeout(5_000);
~~~

Đoạn mã trên minh họa ý nghĩa cấu hình, không phải khuyến nghị mặc định. Cần xem xét cách provisioning topology vì **RabbitAdmin auto-declaration không hoạt động như CHANNEL mode**; đặc biệt thận trọng với exclusive/anonymous queue và listener phụ thuộc vào tên queue.

## 6. RabbitTemplate sử dụng channel như thế nào?

**RabbitTemplate** là API mức cao để publish/receive AMQP message. Khi gọi **convertAndSend**, template thực hiện chuyển đổi payload, lấy channel phù hợp qua ConnectionFactory, publish, rồi giải phóng tài nguyên theo cơ chế Spring.

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrderEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void orderCreated(String orderId) {
        rabbitTemplate.convertAndSend(
                "orders.events",          // exchange
                "order.created",          // routing key
                orderId);                 // payload
    }
}
~~~

Với code này, RabbitTemplate **không cần tự tạo TCP connection và channel mới cho mỗi lời gọi**. Khi nhiều request gọi producer đồng thời, Spring có thể cấp các channel khác nhau trên connection dùng chung. Channel sau thao tác ngắn có cơ hội quay lại cache.

### Khi nào channel được giữ lâu hơn một lời gọi?

Không phải thao tác nào cũng mượn rồi trả ngay:

- **Publisher confirm:** channel hoặc dữ liệu xác nhận liên quan cần được quản lý đủ lâu để nhận broker confirm. Spring AMQP có cơ chế phối hợp channel cache với các confirm đang chờ, tránh tái sử dụng channel không an toàn.
- **Transaction:** nếu sử dụng channel transaction do Spring quản lý, channel có thể được gắn với transaction đến khi commit/rollback; các channel transactional và non-transactional được quản lý riêng trong cache.
- **RabbitTemplate.execute(...)**: callback thao tác trực tiếp với channel trong phạm vi Spring cấp; không nên giữ tham chiếu đó và dùng sau khi callback kết thúc.
- **Listener container:** channel tiêu thụ thường được giữ trong suốt vòng đời consumer, khác với các channel gửi message ngắn hạn.

### Xác nhận publisher khác việc tái sử dụng channel

~~~mermaid
sequenceDiagram
    participant S as Order Service
    participant T as RabbitTemplate
    participant B as RabbitMQ
    participant C as Consumer
    S->>T: convertAndSend(event)
    T->>B: basic.publish trên channel
    B-->>T: Publisher confirm (nếu được bật)
    B->>C: Giao message qua queue
    C-->>B: Consumer ACK sau xử lý
~~~

**Publisher confirm** là tín hiệu broker trả về cho producer về publish. **Consumer ACK** là tín hiệu consumer xác nhận lần giao message đã xử lý. **Channel cache** chỉ giúp tiết kiệm tài nguyên; bản thân nó không chứng minh broker đã route, lưu bền hoặc consumer đã xử lý xong.

Để phát hiện publish không có queue đích, dùng **mandatory + returns**; để giảm rủi ro mất message giữa DB và broker, cân nhắc **transactional outbox**. Khi retry producer/consumer, cần **eventId** hoặc idempotency key để xử lý trùng.

## 7. @RabbitListener và channel dài hạn

Đối với listener, nhiều thao tác không kết thúc sau một message. **SimpleRabbitListenerContainer** hoặc **DirectMessageListenerContainer** quản lý một hoặc nhiều consumer, và consumer giữ channel phục vụ nhận message, ACK và QoS trong suốt thời gian hoạt động.

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

@Configuration
class OrderListenerConfig {
    @Bean
    SimpleRabbitListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrentConsumers(3);
        factory.setMaxConcurrentConsumers(6);
        factory.setPrefetchCount(20);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        return factory;
    }
}

@Component
class OrderListener {
    @RabbitListener(
            queues = "orders.created",
            containerFactory = "ordersListenerFactory")
    public void onOrder(String orderId) {
        // Xử lý, commit nghiệp vụ và ném exception nếu thất bại.
        System.out.println("Order received: " + orderId);
    }
}
~~~

Giả định queue **orders.created** đã tồn tại hoặc được RabbitAdmin khai báo bằng topology tương ứng. Với **AcknowledgeMode.AUTO** của Spring listener container, Spring thường gửi ACK khi handler trả về thành công; nếu handler ném exception, cách reject/requeue phụ thuộc cấu hình error handling. AUTO **không có nghĩa broker ACK trước khi xử lý**.

### Số consumer không bằng kích thước channel cache

Ví dụ container có **3 consumer ban đầu**, có thể tăng tới **6**. Trong phần lớn cấu hình listener container, mỗi consumer cần channel của riêng nó trong khi đang chạy. Bên cạnh đó, publisher đồng thời và RabbitAdmin cũng có lúc cần channel.

Nếu bật giới hạn channel với **channelCacheSize=4** và chạy 6 consumer cùng trên connection, ứng dụng có thể bị nghẽn hoặc không cấp được channel cho toàn bộ nhu cầu. Vì vậy cấu hình cache cần tính cả **channel giữ dài hạn của consumer** và **channel dùng tạm của publisher**.

**PrefetchCount=20** là số message có thể được giao trước mà chưa ACK theo QoS của consumer/channel. Nó ảnh hưởng số message **unacked** và bộ nhớ xử lý, **không phải** số channel trong cache.

### CachingConnectionFactory có tạo “một channel cho mỗi message” không?

Với RabbitTemplate, channel có thể được mượn/trả cho từng thao tác publish. Với listener container, một consumer thường tiếp tục sử dụng **cùng channel của nó** để nhận nhiều message. Khi consumer dừng, channel có thể được đóng hoặc trả lại cho factory theo lifecycle và trạng thái cache.

Một thao tác gửi nhiều message trong một transaction hoặc một callback có thể dùng cùng channel trong phạm vi thao tác; không nên suy ra tất cả message luôn dùng channel khác nhau.

## 8. Quy trình sizing: chọn cache theo tải thực tế

Không có một kích thước cache đúng cho mọi ứng dụng. Hãy ước lượng **độ đồng thời** trước khi chọn:

1. **Listener channels:** số consumer AMQP đang chạy và số channel giữ dài hạn.
2. **Publisher channels:** số lời gọi RabbitTemplate thực sự đồng thời tại thời điểm cao điểm.
3. **Channel phục vụ quản trị và transaction:** nhu cầu declare, publish transaction, callback dài hạn.
4. **Buffer:** một biên độ nhỏ cho spike, retry và tăng số worker.
5. **Giới hạn broker:** số connection/channel được phép, bộ nhớ, CPU và cảnh báo resource.

### Ví dụ tính sơ bộ

Giả sử một service có:

| Tác nhân | Đồng thời dự kiến | Ghi chú |
| --- | ---: | --- |
| Listener xử lý đơn hàng | 8 consumer | Channel dài hạn |
| HTTP request publish event | 12 publish đồng thời | Channel tạm thời |
| Tác vụ quản trị/khác | 2 channel | Dự phòng |
| **Tổng nhu cầu minh họa** | **22 channel** | Chưa tính spike |

Nếu dùng **channelCheckoutTimeout > 0** để giới hạn cứng, **channelCacheSize=32** có thể là **điểm thử ban đầu** trong ví dụ; sau đó phải đo thật và điều chỉnh. Đây không phải công thức được RabbitMQ bảo đảm, vì khả năng cạnh tranh tài nguyên còn phụ thuộc loại container, số connection và thời gian giữ channel.

Nếu **không bật checkout timeout**, channelCacheSize chủ yếu là cache idle; cần quan sát số channel mới tạo/đóng thay vì dùng nó như giới hạn tải.

### Các dấu hiệu size không phù hợp

- **Nhiều channel create/close liên tục:** cache idle có thể quá nhỏ hoặc lifecycle không tối ưu.
- **AmqpTimeoutException lúc xin channel:** giới hạn checkout đã bị chạm, channel bị giữ quá lâu hoặc số consumer/publisher vượt năng lực.
- **Số connection tăng bất thường:** có nhiều ConnectionFactory, CONNECTION mode, publisher connection riêng, hoặc app instance tăng.
- **Số channel quá cao trên broker:** đồng thời quá lớn, cache giữ nhiều channel idle, hoặc thiếu quản lý lifecycle.
- **Publish latency tăng nhưng broker vẫn khỏe:** có thể bị chờ channel checkout ở phía client.

Đừng chữa mọi vấn đề bằng tăng channelCacheSize. Nếu consumer xử lý chậm do database, tăng channel không giải quyết nút nghẽn đó; đôi khi chỉ làm tăng số message **unacked**.

## 9. Quan sát cache và RabbitMQ broker

**CachingConnectionFactory.getCacheProperties()** trả về các thông tin thống kê cache theo phiên bản Spring AMQP, ví dụ số connection/channel cached và các chỉ số high-water.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.stereotype.Component;

@Component
public class RabbitConnectionDiagnostics {
    private static final Logger log =
            LoggerFactory.getLogger(RabbitConnectionDiagnostics.class);

    private final CachingConnectionFactory factory;

    public RabbitConnectionDiagnostics(
            CachingConnectionFactory factory) {
        this.factory = factory;
    }

    public void logCacheSnapshot() {
        factory.getCacheProperties().forEach(
                (key, value) ->
                        log.info("RabbitMQ cache {}={}", key, value));
    }
}
~~~

Ví dụ trên để chẩn đoán nội bộ; tránh xuất toàn bộ thông tin connection vào log không được bảo vệ, và kiểm tra key thực tế theo phiên bản thư viện. **getCacheProperties() là snapshot**, không phải tự động một hệ thống metrics dài hạn.

Trong **RabbitMQ Management UI**, có thể xem:

- **Connections:** ứng dụng đang mở bao nhiêu connection, node/vhost nào, có reconnect liên tục không.
- **Channels:** số channel đang mở, tốc độ publish/confirm, nhiều channel idle hay channel có unacked messages.
- **Queues:** ready/unacked, consumer count, publish/deliver/ack rate.
- **Node metrics:** bộ nhớ, file descriptors, flow control, socket và resource alarms.

Kết hợp số liệu trên broker với **latency publish**, **AmqpTimeoutException**, **consumer processing time**, **publisher confirms/returns**, **retry**, **DLQ** và kết quả nghiệp vụ. Nếu queue backlog tăng vì consumer xử lý chậm, cần tối ưu logic hoặc tăng worker có kiểm soát; không kết luận ngay rằng cache channel quá nhỏ.

## 10. Phục hồi khi mất kết nối

CachingConnectionFactory giúp tái sử dụng connection/channel, nhưng **không thể giữ sống một TCP connection đã bị ngắt**. Khi connection chết, channel bên trong không còn dùng được; Spring cần tạo connection/channel mới và listener container phải khôi phục consumer.

~~~mermaid
sequenceDiagram
    participant A as Spring application
    participant F as CachingConnectionFactory
    participant R as RabbitMQ
    A->>F: Lấy connection/channel
    F->>R: Mở connection và channel
    R--xF: Network outage / connection closed
    F-->>A: Connection/channel không còn hợp lệ
    Note over A,F: Spring container / retry logic phát hiện lỗi
    F->>R: Kết nối lại khi broker sẵn sàng
    A->>F: Xin channel mới
    F->>R: Mở channel mới
~~~

Trong Spring AMQP, nên để **cơ chế connection/listener recovery của Spring** quản lý vòng đời thay vì tự bật thêm cơ chế automatic recovery của RabbitMQ Java Client mà không kiểm soát hai lớp cùng phục hồi.

**RabbitAdmin** có thể khai báo lại exchange/queue/binding được Spring quản lý khi connection mới xuất hiện trong cấu hình hỗ trợ, đặc biệt với **CHANNEL mode**. Tuy nhiên:

- **Queue durable** tồn tại qua broker restart theo cấu hình phù hợp; không đồng nghĩa message chắc chắn đã được publisher xác nhận.
- **Exclusive queue** có thể bị xóa khi connection sở hữu biến mất; dù khai báo lại cùng tên, message cũ không tự trở về.
- **Auto-delete queue** có thể bị xóa khi consumer cuối rời đi.
- Nếu kết nối mất **trong lúc publish** và producer không có kết quả confirm rõ ràng, **không thể kết luận chắc broker có hay chưa ghi message**; retry có thể gây trùng.
- Nếu consumer đã làm xong tác động ngoài broker nhưng mất connection trước ACK, message có thể bị giao lại. Consumer cần **idempotency**.

**CachingConnectionFactory không thay thế retry, DLQ, outbox hoặc transaction nghiệp vụ.** Nó giải quyết phần quản lý kết nối/channel; tin cậy end-to-end vẫn phải được thiết kế ở publisher, broker và consumer.

### Heartbeat và timeout không đồng nghĩa reconnect thành công

Heartbeat giúp phát hiện một số trường hợp kết nối chết nhưng không bảo đảm mọi sự cố được phát hiện tức thời. **connection-timeout** liên quan thiết lập connection, còn **channelCheckoutTimeout** liên quan chờ channel từ factory; hai timeout phục vụ hai việc khác nhau.

Nếu RabbitMQ bị lỗi xác thực, vhost không tồn tại, topology sai hoặc cấu hình TLS sai, tạo lại connection nhiều lần cũng không giải quyết được. Cần quan sát exception gốc và cấu hình broker.

## 11. ConnectionFactory và transaction

Spring AMQP có cơ chế **channel transaction** và tích hợp với Spring transaction management. Khi transaction đang hoạt động, channel có thể được gắn với phạm vi transaction; không nên mượn một channel transaction rồi dùng ngoài vòng đời được quản lý.

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class TransactionalRabbitTemplateConfig {
    @Bean
    RabbitTemplate transactionalRabbitTemplate(
            org.springframework.amqp.rabbit.connection.ConnectionFactory cf) {
        RabbitTemplate template = new RabbitTemplate(cf);
        template.setChannelTransacted(true);
        return template;
    }
}
~~~

**channelTransacted=true** kích hoạt transaction của AMQP channel cho thao tác thích hợp. Đây **không phải** transaction phân tán nguyên tử giữa RabbitMQ và cơ sở dữ liệu. Ví dụ, DB commit rồi RabbitMQ publish lỗi vẫn có thể tạo khe hở nếu không thiết kế bổ sung.

Khi cần phát event đáng tin cậy cùng lúc ghi đơn hàng, **transactional outbox** là chiến lược thông dụng: trong cùng DB transaction, lưu cả dữ liệu nghiệp vụ và bản ghi event; một worker khác publish bản ghi outbox. Sau đó vẫn cần publisher confirms, retry và consumer idempotency.

**Publisher confirms** và **AMQP channel transactions** là hai cơ chế khác nhau, không nên coi một cơ chế tương đương cơ chế kia hoặc bật phối hợp tùy tiện mà không xem tài liệu phiên bản. Trong ứng dụng phát sự kiện có thông lượng cao, thường ưu tiên publisher confirms kết hợp outbox hơn là mở transaction RabbitMQ cho từng message.

## 12. Các lỗi cấu hình phổ biến

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| **AmqpTimeoutException** khi publish | Chạm giới hạn channel sau khi đặt checkout timeout > 0 | Xem channelCacheSize, số consumer, publisher đồng thời và thời gian giữ channel |
| Publish lúc cao điểm chậm dù broker rảnh | Nhiều thread chờ checkout, công việc trong callback/transaction kéo dài | Kiểm tra cache high-water, thread dump, thời gian publish |
| Connection/channel tăng mạnh | Có nhiều factory, mode CONNECTION hoặc cache không phù hợp | Đối chiếu app instance, factory, broker Management |
| **RESOURCE_LOCKED** khi dùng exclusive queue | Queue được declare bằng connection khác connection consume | Đảm bảo vòng đời/connection của RabbitAdmin và consumer tương thích |
| Listener báo **NOT_FOUND** | Queue chưa declare, bị auto-delete hoặc cấu hình factory sai | Kiểm tra RabbitAdmin, mode cache, topology và quyền |
| **PRECONDITION_FAILED** khi declare | Cố khai báo queue/exchange cùng tên với thuộc tính khác trên broker | Sửa cấu hình topology cho nhất quán; không chỉ tăng cache |
| Publish bị trùng sau reconnect | Producer retry khi không chắc lần trước đã được confirm | Dùng eventId, outbox và idempotency |
| Queue backlog tăng nhưng channel vẫn nhiều | Consumer chậm do xử lý nghiệp vụ, DB hoặc API ngoài | Đo thời gian xử lý, retry, prefetch và concurrency |
| Số lượng channel gần giới hạn broker | Cấu hình concurrency/cache quá lớn hoặc tồn tại nhiều instance | Điều chỉnh tải, hạn chế concurrency và quan sát broker |

### Một quy trình chẩn đoán hiệu quả

1. **Nhận diện lỗi:** exception là timeout checkout, mất kết nối TCP, authorization, queue không tồn tại, hay nghiệp vụ thất bại?
2. **Đọc số liệu hai phía:** CachingConnectionFactory cache properties, RabbitMQ Connections/Channels, publish/ack rate.
3. **Đo thời gian giữ channel:** thao tác publish ngắn hay transaction/callback giữ channel lâu? Listener có bao nhiêu consumer?
4. **Kiểm tra mode:** CHANNEL hay CONNECTION? Có publisher connection tách riêng? RabbitAdmin đang declare trên factory nào?
5. **Chỉnh một biến và đo lại:** cache size/timeout, concurrency, prefetch hoặc tốc độ nghiệp vụ; kiểm tra latency và lỗi sau khi chỉnh.

Đừng đặt **channelCacheSize bằng số message/giây**. Kích thước cache phụ thuộc số channel cần dùng **đồng thời** và thời gian giữ chúng, chứ không tỷ lệ tuyến tính với tổng số message.

## 13. Bài tập thực hành

### Bài 1 — Quan sát channel cache khi publish liên tục

1. Tạo Spring Boot service kết nối RabbitMQ và khai báo một queue/exchange thử nghiệm.
2. Bắt đầu với **channelCacheSize=2**, không bật channel checkout timeout.
3. Publish 100 message tuần tự bằng RabbitTemplate; theo dõi số channel trên broker và snapshot **getCacheProperties()**.
4. Tăng độ đồng thời lên 10 thread rồi so sánh số channel được mở và channel idle sau khi chạy.
5. Giải thích tại sao **channelCacheSize=2 không nhất thiết giới hạn còn hai thao tác đồng thời** khi checkout timeout = 0.

### Bài 2 — Kích hoạt giới hạn checkout

1. Đặt **channelCacheSize=3** và **channelCheckoutTimeout=1000 ms**.
2. Chạy listener hoặc producer đồng thời đủ lớn để giữ quá ba channel trong một khoảng thời gian.
3. Quan sát thao tác nào phải chờ, thao tác nào gặp **AmqpTimeoutException**.
4. Tăng size phù hợp và đo lại. Nêu rõ lý do **không** tăng vô hạn số channel.

### Bài 3 — So sánh consumer dài hạn với publisher ngắn hạn

Tạo @RabbitListener với ba consumer và một RabbitTemplate publisher. Quan sát số channel đang mở **trước, trong và sau** khi publish nhiều message. Giải thích vì sao channel consumer vẫn tồn tại lúc queue không có message, còn publisher channel có thể được trả về cache.

### Bài 4 — Thử mất kết nối

Chạy producer/consumer, tạm dừng RabbitMQ rồi khởi động lại. Theo dõi exception, reconnect, RabbitAdmin và các channel được tạo lại. Xác định message nào đã được confirm, message nào có thể được giao lại, và vì sao chỉ dựa vào CachingConnectionFactory **không** đủ để bảo đảm exactly-once.

### Bài 5 — Thiết kế cho nghiệp vụ đặt hàng

Order Service publish event **OrderCreated**; Notification Service nhận rồi gửi email. Chọn cache mode, kích thước channel thử nghiệm, publisher confirm, consumer ACK, retry/DLQ và idempotency. Giải thích trường hợp:

- Producer đã publish nhưng mất kết nối trước khi nhận confirm.
- Consumer gửi email xong nhưng crash trước ACK.
- Có sáu listener và nhiều request cùng publish; giới hạn channel quá thấp.

### Câu hỏi tự đánh giá

1. Vì sao nhiều channel có thể hoạt động trên một TCP connection?
2. Trong CHANNEL mode, **close()** trên channel do Spring cấp thường làm gì?
3. Khi nào **channelCacheSize** trở thành giới hạn cứng thay vì kích thước cache idle?
4. Vì sao **CONNECTION mode** cần thận trọng với RabbitAdmin và exclusive queue?
5. Số consumer đang chạy liên quan gì đến số channel được giữ lâu dài?
6. **Publisher confirm**, **consumer ACK** và **channel cache** khác nhau thế nào?
7. Nếu kết nối đứt giữa lúc publish, retry ngay có thể tạo rủi ro gì?
8. Cần xem những số liệu nào để biết một lỗi là do cache channel hay do consumer xử lý chậm?

## 14. Tài liệu tham khảo

- [Spring AMQP — Connections and Resource Management](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): CachingConnectionFactory, cache modes, checkout timeout, connection/channel reuse, diagnostics.
- [Spring AMQP — Listener Concurrency](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html): Simple/Direct listener container, concurrent consumers, scaling.
- [Spring AMQP — Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/confirms.html): publisher confirm, return và xử lý publish bất định.
- [Spring AMQP — Resilience: Recovering from Broker Failures](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html): reconnect và khai báo tài nguyên.
- [RabbitMQ — Channels](https://www.rabbitmq.com/docs/channels): channel lifecycle, resource usage và các lưu ý thread safety.
- [RabbitMQ — Connections](https://www.rabbitmq.com/docs/connections): connection lifecycle, heartbeat và network failure.

---

**Ghi nhớ:** **CachingConnectionFactory** tái sử dụng connection/channel để ứng dụng Spring AMQP làm việc hiệu quả với RabbitMQ. **CHANNEL mode** thường phù hợp nhất: một connection dùng chung, nhiều channel được mượn/trả; **CONNECTION mode** quản lý nhiều physical connection và có giới hạn về auto-declaration. **channelCacheSize** chủ yếu là số channel idle có thể cache, nhưng khi **channelCheckoutTimeout > 0** nó trở thành giới hạn checkout. Việc cache tài nguyên **không bảo đảm** publish, ACK, retry hoặc xử lý nghiệp vụ đúng một lần; cần kết hợp confirms, idempotency, retry/DLQ và giám sát phù hợp.
