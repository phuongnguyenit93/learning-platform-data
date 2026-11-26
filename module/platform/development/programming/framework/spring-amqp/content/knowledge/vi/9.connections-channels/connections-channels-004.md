# channelCacheSize là kích thước cache hay giới hạn đang dùng

## 1. Một cấu hình, hai cách hiểu rất khác nhau

Trong **Spring AMQP** sử dụng RabbitMQ qua **AMQP 0-9-1**, `CachingConnectionFactory` quản lý connection và tái sử dụng channel để `RabbitTemplate` gửi message và `@RabbitListener` tiêu thụ message hiệu quả. Thuộc tính `channelCacheSize` thường bị hiểu nhầm là “ứng dụng chỉ được mở tối đa N channel”. Thực tế:

> **Mặc định, `channelCacheSize` là số lượng channel nhàn rỗi tối đa mà Spring giữ lại để tái sử dụng; nó không phải giới hạn số channel đồng thời đang dùng. Chỉ khi `channelCheckoutTimeout > 0`, thuộc tính này mới trở thành giới hạn số channel có thể được cấp trên mỗi connection.**

Ví dụ:

- `channelCacheSize=10` và `channelCheckoutTimeout=0`: nếu 40 tác vụ cần channel cùng lúc, Spring có thể tạo **hơn 10 channel**; khi chúng lần lượt được trả về, chỉ tối đa 10 channel nhàn rỗi của loại tương ứng được giữ trong cache, phần dư đóng vật lý.
- `channelCacheSize=10` và `channelCheckoutTimeout=2000 ms`: tối đa **10 channel trên một connection** có thể được cấp phát/giữ trong phạm vi factory đó; tác vụ thứ 11 khi tất cả đã được mượn sẽ chờ có channel trả lại, tối đa 2 giây, rồi có thể ném `AmqpTimeoutException`.

Đó là điểm chính của bài **Kết nối và channel** này. Hiểu đúng cặp cấu hình trên giúp tránh cả hai sai lầm: tưởng rằng một cache nhỏ tự bảo vệ broker trước việc mở quá nhiều channel; hoặc tăng cache liên tục nhưng thực ra hệ thống đang bị giới hạn channel đồng thời vì checkout timeout đã được bật.

## 2. Connection, channel và cache đóng vai trò gì?

RabbitMQ cho phép **một TCP connection** mang nhiều **AMQP channel**. Mỗi channel là một luồng giao tiếp logic của AMQP 0-9-1 trên connection, mang các thao tác như `basic.publish`, `basic.consume`, `basic.ack` và transaction. Mở và đóng channel liên tục có chi phí; duy trì quá nhiều channel đang mở cũng tiêu tốn tài nguyên ở client và broker.

~~~mermaid
flowchart TB
    APP["Spring application"]
    CF["CachingConnectionFactory<br/>CacheMode.CHANNEL"]
    TCP["Một TCP connection tới RabbitMQ"]
    C1["Channel 1: producer"]
    C2["Channel 2: producer"]
    C3["Channel 3: listener"]
    CN["Channel N"]
    Q["RabbitMQ exchange / queue"]
    APP --> CF --> TCP
    TCP --> C1
    TCP --> C2
    TCP --> C3
    TCP --> CN
    C1 --> Q
    C2 --> Q
    C3 --> Q
    CN --> Q
~~~

| Thành phần | Vai trò | Có tương đương `channelCacheSize` không? |
| --- | --- | --- |
| **Connection** | Kết nối TCP/AMQP tới broker; có thể mang nhiều channel. | Không. |
| **Channel** | Kênh logic thực hiện thao tác AMQP 0-9-1. | Không; channel có thể đang được mượn hoặc nhàn rỗi trong cache. |
| **Channel cache** | Giữ channel đã sử dụng để lần sau dùng lại. | Có: `channelCacheSize` điều chỉnh kích thước lưu giữ này khi timeout bằng 0. |
| **Checkout limit** | Giới hạn số channel có thể cấp trên connection khi tính năng chờ được bật. | Có: khi `channelCheckoutTimeout > 0`, `channelCacheSize` còn đóng vai trò giới hạn. |
| **RabbitMQ `channel_max`** | Giới hạn channel theo giao thức, được client và server thương lượng. | Không; đây là giới hạn khác của client/broker. |
| **Listener concurrency** | Số consumer có thể xử lý message song song. | Không; có liên hệ nhu cầu channel, nhưng phải cấu hình độc lập. |
| **Prefetch** | Số delivery chưa ACK tối đa mà broker có thể gửi trước theo phạm vi QoS. | Không; liên quan message delivery, không phải số channel được cache. |

Ở `CachingConnectionFactory.CacheMode.CHANNEL` (chế độ mặc định), một factory thường sử dụng một connection chia sẻ và quản lý cache channel trên connection đó. Một ứng dụng có thể có **connection khác** cho publisher, hoặc nhiều connection factory khác nhau; vì thế không thể nhìn `channelCacheSize=10` rồi kết luận **toàn bộ JVM** chỉ mở tối đa 10 channel.

Một lớp Spring quan trọng khác là `RabbitTemplate`. Nó có thể được dùng chung giữa các luồng; framework sẽ mượn và trả channel phù hợp. Tránh chia sẻ trực tiếp **cùng một `com.rabbitmq.client.Channel`** giữa nhiều luồng để publish đồng thời, vì thao tác trên raw channel không có cùng hợp đồng thread-safety như `RabbitTemplate`.

## 3. Trường hợp mặc định: channelCacheSize là sức chứa cache

### 3.1. `channelCheckoutTimeout=0` nghĩa là không bật channel limiting

Mặc định, `channelCheckoutTimeout` bằng **0**. Khi đó, `CachingConnectionFactory` hoạt động theo hướng:

1. Tác vụ cần channel thì factory tìm channel phù hợp còn nhàn rỗi trong cache.
2. Nếu không có channel nhàn rỗi, factory có thể **tạo channel mới**, ngay cả khi số channel đang được mượn đã vượt `channelCacheSize`.
3. Khi tác vụ hoàn thành và trả channel, nếu cache còn chỗ thì channel được giữ lại.
4. Nếu cache đã đầy, channel trả về sẽ **bị đóng vật lý** thay vì giữ thêm.

Trong cấu hình này, giới hạn thực tế của số channel có thể mở còn phụ thuộc tài nguyên hệ thống và giới hạn của RabbitMQ, đặc biệt **channel_max**. Spring không giới hạn tổng số channel đang hoạt động bằng `channelCacheSize` khi timeout bằng 0.

~~~text
Giả sử channelCacheSize = 3; channelCheckoutTimeout = 0:

Thời điểm T1: 5 tác vụ chạy đồng thời
  Channel A: IN USE
  Channel B: IN USE
  Channel C: IN USE
  Channel D: IN USE
  Channel E: IN USE
  ==> 5 channel đang dùng dù cache size = 3.

Thời điểm T2: cả 5 tác vụ đã trả channel
  Cache giữ tối đa 3 channel nhàn rỗi phù hợp.
  Hai channel còn lại được đóng vật lý.

Thời điểm T3: một tác vụ mới
  Thường tái sử dụng một channel đã cache.
~~~

**Không có việc pre-create sẵn 3 hay 25 channel chỉ vì đã đặt cache size**: cache tăng theo nhu cầu thực tế. Giá trị mặc định của `channelCacheSize` trong `CachingConnectionFactory` hiện đại là **25**, nhưng một ứng dụng tải thấp hoàn toàn có thể chỉ dùng vài channel.

### 3.2. Vì sao cache quá nhỏ gây tốn tài nguyên?

Giả sử 20 luồng publish có lúc cùng hoạt động, nhưng cache chỉ giữ 2 channel. Sau mỗi đợt tải, nhiều channel mới phải đóng; đợt tiếp theo lại mở chúng. Nếu quá trình này diễn ra liên tục:

- RabbitMQ Management UI ghi nhận tốc độ **channel opened/closed** cao.
- Broker và client tốn CPU, bộ nhớ và thời gian để mở/đóng channel.
- Độ trễ publish/consume có thể tăng vì chi phí tạo resource.

Khi cần thiết, tăng `channelCacheSize` có thể **giảm churn**. Nhưng nếu tải thấp, tăng từ 25 lên 100 thường không có nghĩa Spring lập tức chiếm 100 channel.

### 3.3. Cache có thể có nhóm channel riêng

`CachingConnectionFactory` quản lý cache channel **transactional** và **non-transactional** riêng biệt. Các thống kê như `idleChannelsTx` và `idleChannelsNotTx` vì thế cần được đọc **riêng**, đặc biệt khi vừa dùng `channelTransacted=true` vừa có các thao tác publish thông thường.

Ví dụ một hệ thống có cache size 10 nhưng bạn nhìn thấy hai nhóm channel idle; không nên cộng tất cả thống kê một cách cơ học rồi khẳng định “cache đã vượt 10”. Trong chế độ có giới hạn checkout, bộ cấp phép channel được tính theo **connection**, bao gồm nhu cầu channel từ những loại thao tác liên quan.

## 4. Khi checkout timeout lớn hơn 0: channelCacheSize trở thành giới hạn

### 4.1. Quy tắc

Khi gọi:

~~~java
connectionFactory.setChannelCacheSize(10);
connectionFactory.setChannelCheckoutTimeout(2000);
~~~

Factory bật **channel limiting**. Lúc này `channelCacheSize=10` không chỉ là số channel được giữ khi idle, mà còn là **số channel tối đa được mở/cấp phát trên mỗi connection** do factory quản lý. Nếu 10 channel đều đang được sử dụng và luồng thứ 11 cần thêm channel:

1. Luồng thứ 11 **chờ** có channel được trả lại.
2. Nếu một channel được trả trong khoảng **2000 ms**, thao tác có thể tiếp tục với channel đó.
3. Nếu quá thời gian mà vẫn không có channel, Spring ném **`org.springframework.amqp.AmqpTimeoutException`** với ngữ cảnh không thể lấy channel.

~~~mermaid
flowchart TD
    START["Tác vụ yêu cầu channel"]
    IDLE{"Có channel phù hợp đang idle?"}
    ROOM{"Số channel đã cấp < channelCacheSize?"}
    WAIT["Chờ tối đa channelCheckoutTimeout"]
    BACK{"Có channel được trả trước timeout?"}
    OK["Nhận channel, chạy RabbitTemplate / listener"]
    FAIL["AmqpTimeoutException"]
    START --> IDLE
    IDLE -- Có --> OK
    IDLE -- Không --> ROOM
    ROOM -- Có --> OK
    ROOM -- Không --> WAIT
    WAIT --> BACK
    BACK -- Có --> OK
    BACK -- Không --> FAIL
~~~

Sơ đồ mô tả đường đi ở mức khái niệm. Chi tiết kỹ thuật về semaphore, channel transactional, connection riêng cho publisher và listener container có thể khiến số lượng thực tế quan sát từ RabbitMQ khác một ví dụ chỉ có một factory.

### 4.2. Bảng tình huống cùng `channelCacheSize=5`

| Checkout timeout | 8 tác vụ cùng lúc cần channel trên cùng connection | Kết quả cần hiểu |
| --- | --- | --- |
| `0` (mặc định) | Có thể tạo 8 channel nếu tài nguyên broker cho phép. | Cache size 5 chỉ giới hạn số giữ để tái sử dụng; các channel dư sẽ đóng khi trả lại. |
| `500 ms` | 5 channel được mượn, 3 tác vụ còn lại chờ. | Nếu đủ channel trở về trước timeout thì tiếp tục; tác vụ quá hạn nhận `AmqpTimeoutException`. |
| `2000 ms` | Cũng chỉ cấp tối đa 5 channel trên connection. | Tác vụ có thêm thời gian chờ; **không** được cấp thêm channel thứ 6. |

Việc tăng checkout timeout từ 500 ms lên 2000 ms **không tăng mức song song**; nó chỉ tăng thời gian một tác vụ có thể chờ. Việc tăng channel cache size khi limiter đang bật có thể tăng mức song song, nhưng phải kiểm tra tài nguyên broker, thời gian giữ channel và nhu cầu thực tế trước.

### 4.3. Đây không phải broker channel_max

RabbitMQ có giới hạn `channel_max` / `max_channels_per_connection` tại phía broker và giá trị thương lượng với client. Giới hạn này là **độc lập** với `channelCacheSize`.

Ví dụ:

- Broker cho tối đa 32 channel/connection, Spring `channelCacheSize=5`, checkout timeout bằng 0: Spring có thể cố tạo channel thứ 6, 7… và đụng giới hạn broker nếu không được trả lại kịp.
- Broker cho tối đa 32, Spring cache size 5 và checkout timeout dương: Spring tự dừng cấp ở 5 trên connection trước khi chạm giới hạn broker.
- Broker cho tối đa 4, Spring cache size 20 và checkout timeout bằng 0: đặt cache 20 **không vượt qua** broker limit 4.

Không sử dụng `channelCacheSize` để thay đổi chính sách giới hạn `channel_max` của RabbitMQ.

## 5. Cấu hình trong Spring Boot và Java

### 5.1. Spring Boot 3.x: minh họa hai chế độ

Với ứng dụng Spring Boot 3.x có dependency `spring-boot-starter-amqp` và sử dụng AMQP 0-9-1, giữ chế độ **chỉ cache**:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    cache:
      connection:
        mode: channel
      channel:
        size: 10
        checkout-timeout: 0ms
~~~

Khi đó `size: 10` nghĩa là giữ tối đa 10 channel idle thuộc nhóm cache tương ứng để tái sử dụng, **không phải** trần channel in-use.

Nếu muốn **giới hạn channel** trên connection:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    cache:
      connection:
        mode: channel
      channel:
        size: 10
        checkout-timeout: 2s
~~~

Đây là hai ví dụ **thay thế nhau**. Không đặt hai block `spring` trùng nhau trong cùng một file YAML. Thời gian `2s` được Spring Boot bind thành Duration và truyền xuống timeout millisecond phù hợp.

Tên thuộc tính quan trọng:

| Spring Boot property | Java API | Ý nghĩa |
| --- | --- | --- |
| `spring.rabbitmq.cache.channel.size` | `CachingConnectionFactory#setChannelCacheSize(int)` | Kích thước cache idle; trở thành channel limit khi checkout timeout dương. |
| `spring.rabbitmq.cache.channel.checkout-timeout` | `setChannelCheckoutTimeout(long)` | Thời gian chờ lấy channel; `0` tắt limiting. |
| `spring.rabbitmq.cache.connection.mode` | `setCacheMode(...)` | `CHANNEL` hoặc `CONNECTION`; mặc định `CHANNEL`. |
| `spring.rabbitmq.cache.connection.size` | `setConnectionCacheSize(int)` | Số connection idle tối đa được cache trong chế độ `CONNECTION`. |

Tài khoản `guest/guest` và `localhost:5672` chỉ phù hợp với môi trường RabbitMQ demo cục bộ. Trong hệ thống thực, hãy dùng credentials, virtual host và kết nối bảo mật riêng.

### 5.2. Java configuration

Nếu cấu hình Spring AMQP trực tiếp không qua Boot auto-configuration:

~~~java
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RabbitConnectionConfiguration {

    @Bean
    CachingConnectionFactory rabbitConnectionFactory() {
        CachingConnectionFactory factory = new CachingConnectionFactory("localhost");
        factory.setPort(5672);
        factory.setUsername("guest");
        factory.setPassword("guest");
        factory.setCacheMode(CachingConnectionFactory.CacheMode.CHANNEL);
        factory.setChannelCacheSize(10);
        factory.setChannelCheckoutTimeout(2000); // milliseconds; bật channel limiting
        return factory;
    }
}
~~~

**Nếu đang dùng Spring Boot, nên ưu tiên cách cấu hình bằng properties** để giữ cơ chế auto-configuration. Ví dụ Java trên minh họa một lựa chọn thay thế: nếu bạn tự định nghĩa bean connection factory, phải hiểu các bean tự cấu hình còn lại của ứng dụng sẽ kết nối tới factory nào, tránh vô tình tạo nhiều factory khác nhau.

### 5.3. Đừng chỉnh cache giữa lúc chạy mà bỏ qua connection cũ

Theo Javadoc, khi đã bật giới hạn checkout, thay đổi `channelCacheSize` **không tự cập nhật giới hạn trên connection hiện hữu**. Cần tái tạo connection một cách có kiểm soát (theo cơ chế được Javadoc hỗ trợ, chẳng hạn `destroy()` hoặc khởi động lại ứng dụng tại thời điểm phù hợp) để giới hạn mới có hiệu lực nhất quán.

Không gọi `destroy()` vô điều kiện trên factory production đang phục vụ consumer hoặc publish đang xử lý: việc thay connection có thể ngắt thao tác in-flight và gây re-delivery. Hãy áp dụng thay đổi có kế hoạch, quan sát publish confirm và consumer ack khi khởi động lại.

## 6. Ví dụ dễ kiểm chứng: giữ channel chưa trả về

Nếu chỉ gọi liên tiếp 100 lần `RabbitTemplate.convertAndSend(...)` trên một luồng, factory thường tái sử dụng một channel, nên **không chứng minh** được giá trị 10 là limit hay cache.

Để quan sát sự khác nhau, cần tạo tình huống có **nhiều channel được mượn cùng lúc**. Ví dụ sau minh họa trong một Spring component có `CachingConnectionFactory` do ứng dụng quản lý:

~~~java
import com.rabbitmq.client.Channel;
import org.springframework.amqp.AmqpTimeoutException;
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.amqp.rabbit.connection.Connection;
import org.springframework.stereotype.Component;

@Component
public class ChannelCheckoutProbe {

    private final CachingConnectionFactory factory;

    public ChannelCheckoutProbe(CachingConnectionFactory factory) {
        this.factory = factory;
    }

    public void runProbe() throws Exception {
        // Điều kiện demo: cache mode CHANNEL, channelCacheSize=2.
        Connection connection = factory.createConnection();
        Channel first = connection.createChannel(false);
        Channel second = connection.createChannel(false);

        try {
            try {
                Channel third = connection.createChannel(false);
                try {
                    System.out.println("Lay duoc channel thu ba");
                } finally {
                    third.close();
                }
            } catch (AmqpTimeoutException ex) {
                System.out.println("Timeout khi lay channel thu ba: " + ex.getMessage());
            }
        } finally {
            // Dù thành công hay lỗi, phải trả lại channel.
            second.close();
            first.close();
        }
    }
}
~~~

Thử **lần lượt hai cấu hình** với cùng `channelCacheSize=2`:

~~~yaml
# Thí nghiệm A: chỉ cache
spring:
  rabbitmq:
    cache:
      channel:
        size: 2
        checkout-timeout: 0ms
~~~

~~~yaml
# Thí nghiệm B: bật giới hạn
spring:
  rabbitmq:
    cache:
      channel:
        size: 2
        checkout-timeout: 1s
~~~

**Kết quả dự kiến:**

- **A:** Factory có thể cấp channel thứ ba mặc dù size=2; lúc đóng, chỉ các channel phù hợp nằm trong sức chứa cache được giữ lại.
- **B:** Khi `first` và `second` đang được mượn, việc xin `third` sẽ chờ khoảng 1 giây rồi ném `AmqpTimeoutException` nếu không có channel nào được trả trong khoảng đó.

Chỉ chạy thử trên môi trường phát triển có broker sẵn sàng. Code chủ động mượn channel để minh họa hành vi của cache; trong ứng dụng thật, `RabbitTemplate` và listener container thường quản lý vòng đời channel cho bạn. Nếu chủ động gọi API `createChannel(...)`, phải **trả channel đúng cách**, thường bằng `close()` trong `finally`; không giữ raw channel vô thời hạn.

Một điểm nữa: khi dùng factory tách riêng cho publisher, hoặc `CacheMode.CONNECTION`, những channel của connection khác **không chia sẻ cùng một bộ giới hạn per-connection** của thí nghiệm trên.

## 7. Tác động đối với RabbitTemplate và @RabbitListener

### 7.1. RabbitTemplate và lượng publish đồng thời

`RabbitTemplate` được thiết kế để dùng chung trong nhiều luồng. Khi gửi message, nó lấy channel phù hợp từ Spring AMQP, rồi trả lại khi thao tác hoàn tất. Giả sử:

~~~java
rabbitTemplate.convertAndSend(
        "orders.events",
        "order.created",
        "ORD-1001"
);
~~~

Nếu ứng dụng có nhiều tác vụ publish cùng lúc:

- Với timeout bằng 0: khi cache không còn channel idle, Spring có thể mở thêm channel để phục vụ nhu cầu.
- Với timeout dương và tất cả channel slots đã được dùng: tác vụ gửi mới có thể bị chặn khi mượn channel, rồi ném timeout.
- Publisher confirms, transactions hoặc request/reply có thể khiến thời gian một channel được giữ khác trường hợp fire-and-forget thông thường; cần **đo theo workload thật**.

Publisher confirm **không tự trở thành consumer acknowledgment**. Kể cả khi có đủ channel, một publish thành công vẫn phải đi qua exchange, binding và queue trước khi `@RabbitListener` xử lý. Quá trình xử lý lỗi, retry, dead-letter và idempotency là những lớp bảo đảm khác.

### 7.2. Listener có thể giữ channel trong suốt vòng đời consumer

Container chạy `@RabbitListener` thường dùng channel phục vụ consumer và giữ nó trong thời gian consumer hoạt động, thay vì mượn/trả riêng cho mỗi message. Ví dụ:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
class OrdersListener {

    @RabbitListener(queues = "orders.created.q")
    public void handle(String orderId) {
        System.out.println("Da xu ly: " + orderId);
    }
}
~~~

Nếu chạy nhiều consumer cùng lúc, nhu cầu channel có thể tăng. Trong ứng dụng có **checkout limit thấp** và dùng chung factory/connection cho cả listener lẫn publisher, một số channel bị giữ lâu bởi listener có thể làm producer gặp `AmqpTimeoutException`.

Do đó, trước khi đặt một giới hạn thấp:

1. Xác định số consumer chạy đồng thời, cùng các thao tác producer, request/reply và admin cần channel.
2. Xác định producer có dùng **connection/factory riêng** không.
3. Dành đủ room cho các channel cần thiết ở thời điểm tải cao nhất.
4. Kiểm chứng với publisher confirm, consumer ack và cơ chế reconnect; không chỉ nhìn số channel khi hệ thống rảnh.

**Đừng dùng `channelCacheSize` như núm điều chỉnh số consumer**. Concurrency là thuộc tính của listener container; prefetch kiểm soát message delivery; cache size quản lý tài nguyên channel.

### 7.3. Về connection riêng cho publisher

Spring AMQP có cơ chế dùng **publisher connection** riêng trong một số cấu hình. Khi đó producer và consumer có thể có những connection và pool channel khác nhau. Việc `channelCacheSize=10` được áp dụng trên mỗi connection không đồng nghĩa chỉ có tối đa 10 channel trên toàn ứng dụng.

Chia sẻ hay tách connection là quyết định thiết kế tùy workload, publisher confirms, transaction và hiện tượng broker block connection. Không suy ra tất cả `RabbitTemplate` đều chắc chắn dùng cùng connection với listener; hãy kiểm tra cấu hình factory thực tế và RabbitMQ Management UI.

## 8. CacheMode.CHANNEL khác CacheMode.CONNECTION

`CachingConnectionFactory` có hai chế độ chính. Chúng khác nhau ở cách cache **connection**, còn channel cache vẫn tồn tại:

| Cấu hình | `CacheMode.CHANNEL` (mặc định) | `CacheMode.CONNECTION` |
| --- | --- | --- |
| `createConnection()` | Trả về kết nối dùng chung theo factory. | Có thể lấy connection idle hoặc tạo connection mới. |
| `channelCacheSize` | Cỡ cache channel (hoặc channel limit khi timeout dương) **trên connection**. | Cũng là cỡ cache/giới hạn channel **trên từng connection**. |
| `connectionCacheSize` | Không dùng để mở rộng số connection trong mode này. | Giới hạn **số connection idle được giữ trong cache**; không tự là tổng số connection tối đa. |
| `connectionLimit` | Không phải núm điều chỉnh cho mode CHANNEL. | Có thể giới hạn tổng số connection và khiến lệnh mượn connection chờ theo timeout thích hợp. |
| Auto-declare với `RabbitAdmin` | Cơ chế auto-declare queue/exchange/binding được hỗ trợ trong cấu hình thông dụng. | **Không hỗ trợ automatic declaration** qua RabbitAdmin theo tài liệu Spring AMQP. |

Không nên chuyển sang `CONNECTION` chỉ vì muốn “có thêm channel”. Thông thường, `CHANNEL` có thể dùng nhiều channel trên một connection, trong khi `CONNECTION` làm tăng chi phí TCP connection và yêu cầu cân nhắc khai báo topology, quản lý executor và các giới hạn broker.

Nếu ứng dụng có **3 connection** và mỗi connection được giới hạn **5 channel**, không thể kết luận toàn bộ ứng dụng dùng đúng 5 channel. Giới hạn per-connection nghĩa là có thể có các nhóm channel khác nhau trên từng connection. Hãy ghi nhận rõ connection nào thuộc producer, consumer và admin.

## 9. Quan sát và điều chỉnh bằng dữ liệu

### 9.1. Các chỉ số từ Spring

`CachingConnectionFactory` có API `getCacheProperties()` để xem thống kê cache tại runtime:

~~~java
import java.util.Properties;
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;

public void logCacheStats(CachingConnectionFactory factory) {
    Properties props = factory.getCacheProperties();
    System.out.println("channelCacheSize = " + props.getProperty("channelCacheSize"));
    System.out.println("idleChannelsNotTx = " + props.getProperty("idleChannelsNotTx"));
    System.out.println("idleChannelsNotTxHighWater = "
            + props.getProperty("idleChannelsNotTxHighWater"));
    System.out.println("idleChannelsTx = " + props.getProperty("idleChannelsTx"));
    System.out.println("idleChannelsTxHighWater = "
            + props.getProperty("idleChannelsTxHighWater"));
}
~~~

Đây là method minh họa để thêm vào một bean/utility nhận `CachingConnectionFactory` đã được inject. Trong `CacheMode.CONNECTION`, các khóa thống kê channel có thể mang hậu tố `:<localPort>` để phân biệt từng connection.

| Property trong `CacheMode.CHANNEL` | Diễn giải |
| --- | --- |
| `channelCacheSize` | Kích thước cache được cấu hình, không phải số đang mượn. |
| `idleChannelsNotTx` | Số channel không dùng transaction hiện đang nhàn rỗi trong cache. |
| `idleChannelsTx` | Số channel transactional hiện đang nhàn rỗi trong cache. |
| `idleChannelsNotTxHighWater` | Mức cao nhất của **số channel idle cached** non-transactional được ghi nhận. |
| `idleChannelsTxHighWater` | Mức cao nhất của **số channel idle cached** transactional được ghi nhận. |
| `localPort` | Port cục bộ giúp đối chiếu với connection trong RabbitMQ Management UI. |

**High-water của idle cache không phải “đỉnh số channel đang in-use”.** Nếu giá trị high-water chạm cache size và RabbitMQ cho thấy channel liên tục được tạo/đóng, có thể cần tăng cache. Nhưng high-water thấp chưa đủ để khẳng định workload không có thời điểm bùng nổ channel in-use; phải đối chiếu số channel đang mở và lưu lượng thực tế.

### 9.2. Những gì cần xem trong RabbitMQ Management UI

Trên RabbitMQ, quan sát:

- **Connections**: mỗi application instance có bao nhiêu connection, connection nào thuộc publisher/consumer, host, vhost và client properties.
- **Channels per connection**: channel đang mở, channel dùng bởi consumer và publisher, có dấu hiệu chạm giới hạn `channel_max` không.
- **Channel open/close rate**: mở/đóng liên tục báo hiệu cache nhỏ so với biến động tải hoặc channel bị lỗi/đóng bất thường.
- **Consumer count và unacknowledged messages**: listener đang xử lý chậm hoặc giữ delivery lâu; số này không phải số channel cache.
- **Publisher confirms, exceptions, logs `AmqpTimeoutException`**: lỗi chờ lấy channel xảy ra trước hoặc khi thao tác yêu cầu channel; cần phân biệt với broker NACK hay listener reject message.
- **Memory và CPU**: quá nhiều channel có thể gây áp lực lên broker ngay cả khi số connection thấp.

### 9.3. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Cache size 5 nhưng Management UI thấy hơn 5 channel đang mở | Timeout bằng 0; nhiều tác vụ đang dùng đồng thời; hoặc có nhiều connection. | Kiểm tra checkout timeout, cache mode và connection thật; không coi đó mặc nhiên là lỗi. |
| `AmqpTimeoutException: No available channels` | Timeout dương, mọi channel slot trên connection đang bị dùng. | Kiểm tra thời gian giữ channel, listener concurrency, consumer/producer share connection, tăng limit nếu phù hợp. |
| Nhiều channel được mở rồi đóng liên tục | Cache idle quá nhỏ so với đỉnh tải, hoặc lỗi channel dẫn đến đóng lại. | Xem channel churn, logs và idle high-water; tăng cache có cơ sở. |
| Channel tăng mãi, broker báo chạm `channel_max` | Channel không được đóng/trả, timeout=0 cho phép mở thêm, hoặc nhiều consumer. | Tìm channel leak, giảm concurrency hoặc bật limit hợp lý; không chỉ tăng cache. |
| Tăng `channelCacheSize` nhưng throughput không tăng | Bottleneck ở DB, network, broker, consumer processing, publisher confirm hoặc prefetch. | Đo latency, ready/unacked, CPU, network, thời gian xử lý. |
| Đổi cache size runtime nhưng giới hạn checkout vẫn như cũ | Connection hiện hữu đang dùng bộ limit cũ. | Tái tạo connection có kiểm soát hoặc restart theo quy trình. |

## 10. Tương quan với retry, dead-letter và giao dịch

Trong ứng dụng xử lý bất đồng bộ đáng tin cậy, việc **không lấy được channel** khác việc **xử lý message thất bại**:

| Lỗi | Giai đoạn | Cách phản ứng cần cân nhắc |
| --- | --- | --- |
| `AmqpTimeoutException` khi mượn channel để gửi | Trước hoặc khi cố thực hiện publish. | Log/metrics, xác định message đã publish hay chưa theo ngữ cảnh; chờ backoff và retry có kiểm soát. |
| Publisher confirm NACK | Broker phản hồi publish. | Theo dõi correlation ID, reason và chính sách gửi lại. |
| Message không định tuyến được | Exchange/binding không có queue đích. | Dùng mandatory returns và giám sát topology, routing key. |
| Listener xử lý lỗi | Sau khi broker giao message. | Ack/nack theo chính sách, retry có giới hạn, DLX/DLQ và idempotency. |
| Database commit xong nhưng consumer ACK thất lạc | Sau side effect nghiệp vụ, trước khi broker xác nhận delivery. | Consumer idempotent theo event ID; không phụ thuộc số channel cache. |

Khi đặt `channelCheckoutTimeout` dương, lỗi cạn channel có thể xảy ra khi nhiều tác vụ tranh một connection. Đừng tự động biến mọi lỗi đó thành “retry lập tức vô hạn”: retry không có backoff có thể làm tình trạng tranh chấp nặng hơn.

Với `channelTransacted=true`, channel có thêm các bước transactional và có thể được giữ lâu hơn; hãy tính nhu cầu của nhóm transactional/non-transactional riêng. **Giao dịch trên AMQP channel không tự gộp commit database và publish RabbitMQ** thành một giao dịch phân tán đúng một lần. Nếu cần đảm bảo event được phát sau khi DB commit, cân nhắc **transactional outbox**.

## 11. Bài thực hành

Sử dụng RabbitMQ cục bộ có Management UI và một ứng dụng Spring Boot 3.x với `spring-boot-starter-amqp`; không chạy thử cạn channel trên môi trường production.

1. **Chế độ cache**: đặt `spring.rabbitmq.cache.channel.size=2` và `checkout-timeout=0ms`. Chạy `ChannelCheckoutProbe` ở mục 6. Xem code có xin được channel thứ ba không; xem lượng channel idle sau khi trả.
2. **Chế độ giới hạn**: restart ứng dụng với cùng size 2 và `checkout-timeout=1s`. Chạy lại probe; mong đợi lỗi timeout khi hai channel đầu chưa trả.
3. **Thử trả channel sớm**: đổi probe để đóng channel thứ hai trước khi xin channel thứ ba. Trong chế độ có limit, yêu cầu mới phải có thể tiếp tục bằng channel đã được trả.
4. **Quan sát cache**: in `getCacheProperties()` sau từng lần chạy. Ghi `idleChannelsNotTx` và `idleChannelsNotTxHighWater`; phân biệt chúng với số channel broker đang mở.
5. **Tải producer**: gửi các thông điệp kiểm thử qua `RabbitTemplate` từ nhiều luồng và đo channel open/close rate. Đổi size 2 thành 10, giữ timeout bằng 0, kiểm tra sự khác nhau về churn; số lượng mở thực tế phụ thuộc workload.
6. **Tải consumer**: tạo queue và `@RabbitListener`; tăng số consumer đồng thời một cách có kiểm soát. Với checkout limit thấp, quan sát liệu các channel của listener có chiếm phần lớn slot trên cùng connection không.
7. **Kiểm tra giới hạn broker**: xem `channel_max` đang thương lượng và xác nhận `channelCacheSize` không thay thế cấu hình này.
8. **Thử lỗi và phục hồi**: theo dõi publish confirms, consumer acknowledgments và event ID trong lúc restart ứng dụng có kiểm soát, để không đánh đồng timeout mượn channel với việc broker đã ACK/NACK message.

### Mẫu ghi chép kết quả

~~~text
Spring AMQP / Boot version:
RabbitMQ version / negotiated channel_max:
CacheMode:
Publisher dùng connection riêng?:
channelCacheSize:
channelCheckoutTimeout:
Concurrent publishers:
Concurrent consumers:
RabbitMQ open channels peak:
Channel open / close rate:
idleChannelsNotTx / idleChannelsNotTxHighWater:
idleChannelsTx / idleChannelsTxHighWater:
AmqpTimeoutException count:
Publish confirms / returned messages:
Messages ready / unacknowledged:
Nhận xét về bottleneck:
~~~

## 12. Những hiểu nhầm cần tránh

**“`channelCacheSize=10` nghĩa là tối đa 10 channel đang dùng?”** Không, nếu checkout timeout vẫn bằng 0. Mặc định đó là mức giữ channel idle để tái sử dụng.

**“`channelCacheSize=25` làm Spring mở ngay 25 channel khi start?”** Không. Cache được mở rộng theo nhu cầu.

**“Tăng `channelCacheSize` chắc chắn tăng throughput?”** Không. Nó có thể giảm channel churn; throughput còn phụ thuộc broker, mạng, database, publisher confirm và listener.

**“`channelCheckoutTimeout=2s` tức là RabbitMQ chỉ có 2 giây để ACK message?”** Không. Đây là thời gian **chờ mượn channel khi cache/limit bị cạn**, không phải thời gian chờ publisher confirm hoặc consumer acknowledgment.

**“Có timeout dương thì channelCacheSize là giới hạn của toàn JVM?”** Không. Giới hạn áp dụng theo **connection** của factory tương ứng; ứng dụng có thể có nhiều connection/factory.

**“Tăng `connectionCacheSize` làm `CacheMode.CHANNEL` có thêm connection?”** Không. Đây là thuộc tính dành cho cache mode `CONNECTION`, và ngay cả khi đó cũng là mức cache idle connection, không tự là max open connections.

**“Có thể dùng `channelCacheSize` thay cho listener concurrency hoặc prefetch?”** Không. Ba cấu hình giải quyết ba vấn đề khác nhau: resource reuse/limit, số consumer chạy song song và lượng delivery đang chờ ACK.

**“Đóng channel mượn từ `CachingConnectionFactory` luôn đóng TCP connection?”** Không. Trong cơ chế caching bình thường, `Channel.close()` trên proxy trả channel về cache nếu còn chỗ; nó không có nghĩa đóng TCP connection. Việc đóng vật lý xảy ra khi cần và khi không giữ channel trong cache.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `channelCacheSize=4`, `channelCheckoutTimeout=0`. Sáu tác vụ cần channel cùng lúc. Có chắc tác vụ thứ năm bị chặn không?

**Trả lời:** Không. Với timeout bằng 0, Spring có thể mở hơn bốn channel đang dùng; cache size giới hạn số channel nhàn rỗi được giữ.

**Câu 2.** `channelCacheSize=4`, `channelCheckoutTimeout=1500 ms`. Cả bốn channel đều đang mượn. Tác vụ thứ năm sẽ như thế nào?

**Trả lời:** Nó chờ một channel được trả lại; nếu sau khoảng 1500 ms vẫn không có, nhận `AmqpTimeoutException`.

**Câu 3.** Application có hai connection, mỗi connection bị giới hạn 4 channel. Có thể nói ứng dụng chỉ có 4 channel đang dùng?

**Trả lời:** Không. Giới hạn là **per connection**; tổng có thể lớn hơn, tùy số connection và nhu cầu.

**Câu 4.** `idleChannelsNotTxHighWater` có cho biết đỉnh số channel producer đang in-use?

**Trả lời:** Không. Đó là đỉnh **idle channel cached** của nhóm non-transactional; cần đối chiếu broker metrics cho channel đang mở.

**Câu 5.** Vì sao các consumer `@RabbitListener` có thể khiến producer hết channel dù producer gửi ít message?

**Trả lời:** Consumer có thể giữ channel lâu trong thời gian chạy. Nếu producer dùng chung connection với listener và checkout limit thấp, ít slot còn lại cho producer.

**Câu 6.** Nếu RabbitMQ báo vượt `channel_max`, tăng `channelCacheSize` có giải quyết chắc chắn không?

**Trả lời:** Không. Cần kiểm tra channel leak, concurrency, giới hạn broker và chế độ checkout; tăng cache không thay đổi giới hạn do broker thương lượng.

## 14. Tài liệu tham khảo

- [Spring AMQP Reference — Connection and Resource Management](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): `CachingConnectionFactory`, `CacheMode.CHANNEL`, `channelCacheSize`, `channelCheckoutTimeout` và `getCacheProperties()`.
- [Spring AMQP Javadoc — CachingConnectionFactory](https://docs.spring.io/spring-amqp/api/org/springframework/amqp/rabbit/connection/CachingConnectionFactory.html): ý nghĩa các setter, điều kiện bật channel limiting và lưu ý khi thay đổi cache size trên connection hiện hữu.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.rabbitmq.cache.channel.size` và `spring.rabbitmq.cache.channel.checkout-timeout`.
- [RabbitMQ — Channels](https://www.rabbitmq.com/docs/channels): channel trên TCP connection, tài nguyên, `channel_max`, giám sát số channel và channel churn.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): khác biệt giữa xác nhận gửi và xác nhận xử lý message.

**Ghi nhớ:** Với `CachingConnectionFactory` của **Spring AMQP cho RabbitMQ AMQP 0-9-1**, **`channelCacheSize` mặc định là sức chứa của cache channel nhàn rỗi**, không phải giới hạn channel đang dùng. Khi **`channelCheckoutTimeout > 0`**, giá trị đó mới tham gia giới hạn số channel trên **mỗi connection** và có thể khiến tác vụ chờ rồi ném `AmqpTimeoutException`. Hãy điều chỉnh theo số producer/consumer đồng thời, thời gian giữ channel, số connection thực tế và thống kê broker; sau đó mới đánh giá độ tin cậy của luồng gửi/nhận bằng publisher confirms, consumer acknowledgments, retry/dead-letter và idempotency.
