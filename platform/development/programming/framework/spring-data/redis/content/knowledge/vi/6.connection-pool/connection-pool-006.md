# Phân biệt kết nối dùng cho lệnh thường, lệnh chặn và Pub/Sub

Khi bắt đầu dùng **Spring Data Redis**, chúng ta thường gọi `StringRedisTemplate.opsForValue().get(...)` hoặc `set(...)` và thấy thao tác kết thúc ngay. Nhưng Redis còn có **lệnh chặn** như `BLPOP`/`BRPOP` và cơ chế **Publish/Subscribe (Pub/Sub)** với `SUBSCRIBE`. Chúng sử dụng kết nối theo những cách khác nhau, vì vậy cách chia sẻ, cấp phát, trả lại pool và quản lý vòng đời cũng khác nhau.

Đây là một chủ đề quan trọng trong chương **Kết nối và pool**: cấu hình pool có thể trông hợp lý khi thử vài lệnh GET/SET, nhưng ứng dụng vẫn có thể gặp timeout hoặc cạn tài nguyên khi nhiều consumer cùng chờ hàng đợi, hoặc khi subscription cần duy trì liên tục.

Ta sẽ phân biệt ba nhóm:

1. **Lệnh thường (ordinary commands):** gửi lệnh, nhận phản hồi, hoàn tất một thao tác ngắn; ví dụ `GET`, `SET`, `INCR`, `HGET`.
2. **Lệnh chặn (blocking commands):** server có thể giữ lệnh đang chờ cho đến khi có dữ liệu hoặc hết thời gian chờ; ví dụ `BLPOP`, `BRPOP`, `BZPOPMIN`, `XREAD BLOCK`.
3. **Pub/Sub:** kết nối đăng ký kênh và duy trì trạng thái nhận thông điệp do publisher gửi; ví dụ `SUBSCRIBE`, `PSUBSCRIBE`, `UNSUBSCRIBE`.

**Khác nhau cốt lõi:** lệnh thường có vòng đời yêu cầu–phản hồi ngắn; lệnh chặn tạm thời giữ kết nối trong một lần chờ; Pub/Sub duy trì một phiên đăng ký tồn tại dài lâu. Cả ba đều trao đổi với Redis Server nhưng tạo ra áp lực tài nguyên và yêu cầu quản lý khác nhau.

## 1. Nhìn tổng thể: vì sao không thể xem mọi Redis connection giống nhau?

~~~text
                    SPRING BOOT APPLICATION
   +------------------------------------------------------+
   |                                                    |
   |  REST / Service           Background Consumer        |
   |       |                          |                   |
   |       v                          v                   |
   |  StringRedisTemplate       RedisTemplate             |
   |   GET / SET / INCR           BRPOP / BLPOP            |
   |       |                          |                   |
   |       | ngắn                    | chờ tối đa N giây  |
   |       v                          v                   |
   |  Kết nối cho lệnh thường    Kết nối dành cho chờ      |
   |                                                    |
   |  MessageListenerContainer                            |
   |       |                                            |
   |       v                                            |
   |  Kết nối subscribe dài hạn                           |
   |       |                                            |
   +-------+--------------------------------------------+
           |
           v
     Redis Driver (Lettuce / Jedis)
           |
           | Redis protocol, TCP/TLS
           v
       REDIS SERVER
   +------------------------------------------------------+
   | GET/SET: xử lý và phản hồi                            |
   | BRPOP: chờ list có item hoặc hết timeout             |
   | SUBSCRIBE: gắn kết nối với các channel đã đăng ký    |
   +------------------------------------------------------+
~~~

Sơ đồ là **mô hình chức năng**, không cam kết rằng mỗi mũi tên luôn tương ứng với một socket TCP mới. Spring Data Redis cung cấp `RedisConnection` ở tầng trừu tượng, còn Lettuce hoặc Jedis quyết định cách dùng **native connection**, chia sẻ connection hoặc lấy connection từ pool.

| Góc nhìn | Lệnh thường | Lệnh chặn | Pub/Sub |
|---|---|---|---|
| Ví dụ | `GET`, `SET`, `INCR` | `BLPOP`, `BRPOP`, `XREAD BLOCK` | `SUBSCRIBE`, `PSUBSCRIBE` |
| Thời gian một yêu cầu | Thường ngắn | Có thể đợi nhiều giây/phút theo cấu hình | Subscription có thể tồn tại suốt vòng đời listener |
| Tại sao Redis giữ trạng thái? | Xử lý lệnh và trả kết quả | Đang chờ dữ liệu hoặc timeout | Đang theo dõi các kênh/pattern |
| Có thể dùng chung native connection cho mọi trường hợp? | Driver có thể hỗ trợ chia sẻ có kiểm soát | Thường cần kết nối riêng trong lúc chờ | Cần đường đăng ký/nhận thông điệp được quản lý lâu dài |
| Nguy cơ tài nguyên | Nhiều request, timeout, latency | Nhiều waiter giữ connection trong lúc chờ | Subscription không giải phóng khi một message đến |
| Spring Data Redis nên dùng gì? | `RedisTemplate`, `StringRedisTemplate` | List/Stream operations từ một background consumer, timeout hữu hạn | `RedisMessageListenerContainer` / API listener tương ứng |
| Kết quả khi không có dữ liệu | `GET` thường trả ngay `null` | Lệnh chờ cho đến khi có dữ liệu hoặc hết timeout | Listener tiếp tục chờ; không có “kết quả cuối” cho cả subscription |

## 2. Ba lớp connection cần gọi đúng tên

Một nguyên nhân dễ nhầm là **connection của Spring Data Redis** và **connection vật lý của driver** không nhất thiết có quan hệ một-một.

### 2.1. `RedisConnectionFactory`

`RedisConnectionFactory` là bean cung cấp các `RedisConnection` cho Spring Data Redis. Implementation thường gặp:

- `LettuceConnectionFactory`, dựa trên Lettuce.
- `JedisConnectionFactory`, dựa trên Jedis.

Factory giữ cấu hình kết nối và tích hợp cơ chế cấp phát của driver. Factory là thành phần **sống dài hạn**, thường được tạo một lần theo Spring application context; không nên dựng factory mới cho mỗi thao tác.

### 2.2. `RedisConnection`

`RedisConnection` là interface Spring Data Redis dùng để thực thi lệnh Redis. Khi ứng dụng gọi:

~~~java
try (RedisConnection conn = connectionFactory.getConnection()) {
    // Thực thi một hoặc nhiều lệnh Redis qua conn.
}
~~~

code đã nhận một đối tượng connection ở tầng Spring. Khi hoàn tất phải giải phóng đúng vòng đời, chẳng hạn bằng try-with-resources cho việc lấy connection trực tiếp. **Không nên lưu RedisConnection thành field của singleton service để chia sẻ giữa nhiều thread**, vì connection có thể mang trạng thái transaction, pipeline hoặc subscription.

`RedisTemplate` thường tự lấy và giải phóng `RedisConnection`, nên nghiệp vụ bình thường không phải gọi `getConnection()` hoặc `close()` thủ công.

### 2.3. Native connection / socket

Phía dưới là đối tượng kết nối do Lettuce hoặc Jedis quản lý, và cuối cùng là kết nối mạng đến Redis Server. Tùy implementation:

- Nhiều `RedisConnection` wrapper có thể cùng sử dụng một native connection phù hợp.
- Một loại thao tác cần trạng thái riêng có thể yêu cầu native connection độc lập.
- Kết nối có thể được cấp trực tiếp, tái sử dụng hoặc mượn từ pool.
- `close()` trên wrapper có thể giải phóng/trả tài nguyên về pool, **không nhất thiết đóng ngay socket TCP**.

Vì vậy, **đếm số lần `getConnection()` không phải là cách chính xác để đếm socket**.

## 3. Lệnh thường: kết nối phục vụ request–response ngắn

Lệnh thường là nhóm dễ gặp nhất khi dùng Spring Data Redis:

~~~java
String value = redis.opsForValue().get("profile:42");

redis.opsForValue().set("profile:42", "active");

Long count = redis.opsForValue().increment("visits:today");
~~~

Mỗi lần gọi tương ứng một thao tác Redis hoặc một chuỗi thao tác mà template điều phối. Với kết nối bình thường:

~~~text
Thread ứng dụng
     |
     | GET profile:42
     v
Redis driver -----> Redis Server
     ^                 |
     |    value/null   |
     +-----------------+
     |
     v
Trả kết quả; thread tiếp tục công việc khác
~~~

Đặc điểm:

- Client gửi lệnh, server thực thi rồi trả phản hồi.
- Một lời gọi đồng bộ chỉ trả về khi nhận được phản hồi hoặc gặp lỗi/timeout.
- Với lệnh nhanh, connection không bị một lệnh đơn lẻ chiếm giữ lâu như lệnh blocking.
- Driver có thể tối ưu số connection dùng cho nhiều lệnh; **không tự động tạo socket mới với mỗi `get()`**.

### 3.1. Lettuce thường chia sẻ native connection cho lệnh thường

`LettuceConnectionFactory` theo cấu hình chia sẻ native connection phổ biến có thể sử dụng **một native connection thread-safe** cho các thao tác **không blocking và không thuộc transaction**. Phía trên nó, Spring Data Redis vẫn cấp các wrapper `RedisConnection` theo nhu cầu.

Hệ quả quan trọng:

- Một ứng dụng có thể chạy nhiều lệnh GET/SET từ nhiều thread nhưng **không phải mỗi thread giữ một socket riêng** cho lệnh thường.
- Bật pool **không có nghĩa toàn bộ GET/SET đều đi qua pool** khi chế độ chia sẻ native connection vẫn đang được dùng.
- Nếu cấu hình tắt chia sẻ native connection hoặc dùng loại thao tác cần connection riêng, chiến lược cấp phát thay đổi.

Không nên suy luận rằng mọi driver đều có cùng khả năng chia sẻ. Hãy đọc hành vi của **implementation và phiên bản** thực tế khi quyết định cấu hình pool.

### 3.2. “Lệnh thường” không có nghĩa luôn nhanh

`GET`, `SET` thường có thời gian thực thi ngắn trên workload hợp lý, nhưng request vẫn có thể chậm do network, Redis quá tải, payload lớn, lệnh nặng hoặc vấn đề vận hành. **Lệnh thường** là phân loại theo cơ chế giao tiếp, không phải cam kết độ trễ.

Một lệnh có thể rất tốn thời gian xử lý mà không phải là lệnh blocking kiểu `BLPOP`. Phải theo dõi latency và command mix để xác định vấn đề.

## 4. Lệnh chặn: server giữ yêu cầu chờ dữ liệu

Một số ứng dụng sử dụng Redis List làm hàng đợi đơn giản:

- Producer ghi job vào list.
- Consumer đợi job xuất hiện rồi lấy ra.
- Nếu list đang rỗng, consumer không muốn liên tục gọi `RPOP` nhiều lần gây polling.

Redis có các lệnh blocking như `BLPOP` và `BRPOP`. Khi chưa có phần tử, server **chờ tới khi có phần tử hoặc timeout**; khi dữ liệu xuất hiện, server trả phần tử và lệnh kết thúc.

### 4.1. Minh họa với BRPOP

Giả sử list **jobs:pending** đang rỗng:

~~~text
Consumer                         Redis Server
   |                                  |
   |---- BRPOP jobs:pending 10 ------>|
   |                                  | chưa có phần tử
   |                                  | giữ yêu cầu đang chờ
   |                                  |
   |               Producer: LPUSH jobs:pending job-42
   |                                  |
   |<------- ["jobs:pending", "job-42"]|
   |                                  |
   | xử lý job-42                     |
~~~

Nếu không có item trong thời hạn chờ, Redis trả **nil** và lệnh chặn kết thúc. Với API template thường sẽ biểu diễn tình huống này bằng **null**.

Ví dụ ở redis-cli:

~~~bash
# Terminal A: đợi tối đa 10 giây nếu list chưa có dữ liệu.
redis-cli BRPOP jobs:pending 10
~~~

Trong terminal B (khi terminal A đang chờ):

~~~bash
redis-cli LPUSH jobs:pending job-42
~~~

Terminal A nhận phần tử khi producer ghi. Sau khi BRPOP trả về, kết nối có thể phục vụ yêu cầu khác theo chiến lược của client.

**Lưu ý:** `BRPOP ... 10` dùng timeout ở tầng lệnh Redis; đó không phải giới hạn thời gian tồn tại của connection trong pool. Với một số lệnh blocking, timeout bằng 0 biểu thị chờ vô thời hạn; chỉ sử dụng cách này nếu đã thiết kế được việc dừng worker và hoàn trả tài nguyên.

### 4.2. Vì sao lệnh blocking cần xử lý connection khác?

Giả sử một connection đang thực thi `BRPOP jobs:pending 30` và không có item. Connection đó đang chờ kết quả của lệnh blocking, có thể kéo dài tới 30 giây.

Nếu mã khác gửi một lệnh lên cùng connection mà không có cơ chế multiplexing/isolation phù hợp, nó có nguy cơ phải chờ phía sau lệnh blocking. Để tránh một consumer đang đợi làm ảnh hưởng các lệnh thường, **driver/factory cần cấp connection phù hợp cho thao tác blocking**.

Trong Spring Data Redis với Lettuce, các thao tác blocking thường sử dụng **kết nối chuyên biệt** thay vì native connection chia sẻ cho lệnh thường. Cơ chế có thể lấy connection mới hoặc từ pool tùy cấu hình. Điều này giải thích vì sao:

- Các lệnh GET/SET ngắn có thể vẫn hoạt động trong khi một worker đang chờ BRPOP.
- Mỗi consumer chặn lâu vẫn tạo ra chi phí connection/resource thực tế.
- Nếu số consumer chờ đồng thời lớn hơn khả năng cấp connection chuyên biệt, pool có thể bị cạn và các consumer khác phải đợi hoặc thất bại vì timeout khi mượn connection.

Không nên **mở một RedisConnection rồi chia sẻ cho cả consumer blocking và các request HTTP**. Connection có trạng thái chờ và cách driver triển khai có thể khiến request khác bị trì hoãn hoặc gây lỗi.

### 4.3. Ví dụ Spring Data Redis với timeout hữu hạn

Đối với Redis List, **StringRedisTemplate** có thể gửi lệnh blocking thông qua phương thức `rightPop(..., Duration)`:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class JobQueue {

    private static final String KEY = "jobs:pending";
    private final StringRedisTemplate redis;

    public JobQueue(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void publishJob(String jobId) {
        // LPUSH: thêm job vào đầu list.
        redis.opsForList().leftPush(KEY, jobId);
    }

    public String receiveJob() {
        // Chờ tối đa 5 giây nếu list rỗng.
        // Khi hết thời gian mà không có job, kết quả là null.
        return redis.opsForList().rightPop(
                KEY,
                Duration.ofSeconds(5)
        );
    }
}
~~~

Ví dụ này sử dụng **LPUSH ở đầu** và **BRPOP ở cuối** để giữ thứ tự FIFO cho các job được thêm tuần tự. Trong ứng dụng thực tế, nhiều producer và nhiều consumer có thể làm thay đổi thứ tự thời điểm xử lý hoàn tất; FIFO ở list không tự bảo đảm job được xử lý xong theo cùng thứ tự.

Một worker riêng có thể gọi `receiveJob()` lặp lại trong khi đang chạy. Khi phương thức trả **null**, worker hiểu là hết thời gian chờ và có thể kiểm tra trạng thái dừng hoặc tiếp tục vòng lặp. Khi trả chuỗi, nó xử lý job nhận được.

**Không nên gọi phương thức chờ 5 giây này trực tiếp trên event-loop WebFlux** hoặc vô tình giữ hết worker thread của HTTP server. Lệnh blocking theo API đồng bộ sẽ chiếm **thread đang gọi** trong thời gian chờ, dù Redis Server không phải đang tính toán liên tục. Dùng một nhóm worker/background executor có giới hạn và quản lý vòng đời rõ ràng.

### 4.4. Timeout tầng Redis và timeout tầng driver

Hai loại timeout thường bị nhầm:

| Timeout | Đặt ở đâu? | Quyết định điều gì? |
|---|---|---|
| Timeout lệnh blocking | Ví dụ `BRPOP jobs:pending 5` hoặc `Duration.ofSeconds(5)` | Server chờ dữ liệu tối đa bao lâu trước khi trả kết quả rỗng |
| Timeout command/client | Cấu hình driver/Spring Boot, tùy command và driver | Client cho phép một thao tác chờ phản hồi bao lâu trước khi báo lỗi |
| Timeout mượn connection | Cấu hình pool, ví dụ `max-wait` | Caller được đợi bao lâu để nhận connection từ pool khi pool hết |
| Timeout kết nối TCP | Cấu hình network/driver | Cho phép thiết lập kết nối đến Redis Server trong bao lâu |

Nếu lệnh blocking dự kiến đợi 10 giây nhưng timeout phía client hoặc cơ chế cấp connection lại không phù hợp, nó có thể thất bại trước khi lệnh trả về đúng kỳ vọng. **Cần kiểm tra semantics timeout của driver thực tế** và chọn timeout hữu hạn tương thích với bài toán.

Đừng giải quyết mọi trường hợp timeout bằng cách tăng bừa một giá trị cấu hình duy nhất: cần xác định **đang chờ dữ liệu, chờ mạng, hay chờ pool**.

### 4.5. BLPOP không phải Pub/Sub

BLPOP/BRPOP lấy **phần tử khỏi list** khi thực thi. Redis List vì vậy có thể dùng như hàng đợi đơn giản: nếu chưa có consumer, phần tử vẫn tồn tại cho tới khi được lấy hoặc bị xóa theo chính sách riêng. Tuy nhiên, khi một consumer đã lấy phần tử ra rồi crash trước khi xử lý xong, Redis List đơn giản **không tự đưa job trở lại**.

Nếu cần acknowledgement, retry, phân phối theo consumer group hoặc theo dõi pending message, nên đánh giá **Redis Streams** hoặc hệ thống message broker phù hợp. Việc dùng lệnh blocking tự thân không cung cấp bảo đảm giao hàng đầy đủ.

## 5. Pub/Sub: kết nối đăng ký dài hạn

Redis Pub/Sub hoạt động theo mô hình:

- Publisher gửi message lên một channel, ví dụ `events:order`.
- Subscriber đã đăng ký `SUBSCRIBE events:order` sẽ nhận các message mới được publish khi subscription đang hoạt động.
- Một subscription thường tiếp tục tồn tại cho tới khi unsubscribe, disconnect hoặc ứng dụng đóng listener.

~~~text
Publisher A ----- PUBLISH events:order "created:42" ----+
                                                       |
Publisher B ----- PUBLISH events:order "paid:42" -------+--> Redis
                                                       |
                                                       +---> Subscriber 1
                                                       |
                                                       +---> Subscriber 2
~~~

**Pub/Sub không phải GET/SET lặp lại** và cũng không giống một BRPOP có timeout. Client đăng ký channel rồi nhận một **luồng thông điệp liên tục**, thay vì hoàn tất sau mỗi thông điệp.

### 5.1. Tại sao Pub/Sub cần connection được quản lý riêng?

Khi kết nối đã đăng ký subscription, Redis và client duy trì trạng thái các channel/pattern và luồng thông điệp gửi đến client. Điều này có các hệ quả:

1. Kết nối subscription có **vòng đời dài**, không được trả về pool như một request GET/SET bình thường sau mỗi message.
2. Không nên dùng tùy tiện cùng kết nối đó làm nơi thực thi nghiệp vụ GET/SET hoặc một lệnh blocking khác.
3. Khi ứng dụng shutdown hoặc listener được gỡ, cơ chế subscription cần unsubscribe/close và giải phóng resource đúng cách.
4. Khi network disconnect, cơ chế reconnect/resubscribe cần được theo dõi để biết listener có nhận lại message chưa.

Trong giao thức Redis kiểu RESP2 truyền thống, kết nối ở trạng thái subscribed bị hạn chế các loại lệnh có thể gửi. Khả năng của RESP3 và các driver hiện đại có thể khác, nhưng **thiết kế một subscription connection dài hạn vẫn cần quản lý độc lập với connection cho request thường**.

### 5.2. Dùng RedisMessageListenerContainer trong Spring

Spring Data Redis cung cấp **RedisMessageListenerContainer** để quản lý đăng ký channel/pattern, lifecycle và dispatch thông điệp tới `MessageListener`. Ta không cần tự gọi `SUBSCRIBE` bằng một RedisConnection thủ công rồi giữ nó vô thời hạn.

Ví dụ cấu hình:

~~~java
import java.nio.charset.StandardCharsets;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration(proxyBeanMethods = false)
public class OrderEventSubscriptionConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(OrderEventSubscriptionConfiguration.class);

    @Bean
    MessageListener orderEventListener() {
        return (message, pattern) -> {
            String body = new String(
                    message.getBody(),
                    StandardCharsets.UTF_8
            );
            log.info("Received order event: {}", body);
        };
    }

    @Bean
    RedisMessageListenerContainer redisMessageListenerContainer(
            RedisConnectionFactory connectionFactory,
            MessageListener orderEventListener) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.addMessageListener(
                orderEventListener,
                new ChannelTopic("events:order")
        );
        return container;
    }
}
~~~

**Ý nghĩa của từng thành phần:**

- `RedisConnectionFactory` cung cấp hạ tầng kết nối cho container.
- `RedisMessageListenerContainer` quản lý connection/subscription, lắng nghe message và chuyển đến listener.
- `ChannelTopic("events:order")` chỉ định channel cần đăng ký.
- `MessageListener` xử lý message nhận được.

Trong Spring container, `RedisMessageListenerContainer` có thể gom nhiều listener/channel trên cơ chế subscription được chia sẻ do chính container quản lý, thay vì bắt mỗi listener mở một socket riêng. Nhưng không nên giả định số socket luôn bằng số bean hoặc số channel; cần xét implementation, topology và cấu hình.

Ví dụ publisher sử dụng StringRedisTemplate:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final StringRedisTemplate redis;

    public OrderEventPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void notifyOrderCreated(String orderId) {
        redis.convertAndSend(
                "events:order",
                "created:" + orderId
        );
    }
}
~~~

`convertAndSend` dùng Pub/Sub thông qua Redis connection cho thao tác publish. Publisher không trở thành subscriber và không cần giữ một subscription connection. Listener tồn tại độc lập, nhận message khi đã đăng ký và Redis chuyển phát.

### 5.3. Tại sao callback Pub/Sub không nên xử lý quá lâu?

Mặc dù listener thường không chạy trực tiếp trên request HTTP, mỗi message vẫn cần được xử lý. Nếu callback:

- gọi một API bên ngoài rất chậm,
- chờ khóa trong thời gian dài,
- làm công việc CPU nặng,
- hoặc chặn đồng bộ nhiều giây,

thì thread/executor dispatch có thể bị ùn ứ. Trong production, nên thiết kế executor phù hợp, giới hạn độ đồng thời và tách công việc lâu dài khỏi callback nhận message. Redis Pub/Sub **không có hàng đợi bền vững tích hợp** để bảo đảm subscriber chậm sẽ xử lý lại mọi message sau khi bị disconnect.

### 5.4. Pub/Sub có bảo đảm nhận message khi subscriber offline không?

**Không.** Pub/Sub truyền message cho subscriber đang kết nối/đăng ký; message thường **không được lưu lại** để subscriber offline đọc bù. `PUBLISH` cũng không tương đương ghi một job bền vào list/stream. Không có acknowledgement/replay theo thiết kế Pub/Sub cơ bản.

Ví dụ:

~~~text
12:00:00  Subscriber đăng ký channel events:order
12:00:02  Publisher gửi "created:42"  -> subscriber nhận
12:00:05  Subscriber mất kết nối
12:00:07  Publisher gửi "paid:42"     -> subscriber vắng mặt, không có replay
12:00:10  Subscriber kết nối lại      -> chỉ nhận message mới
~~~

Việc driver/container có thể tự reconnect và đăng ký lại **không có nghĩa** các message xuất hiện trong khoảng mất kết nối được gửi lại. Nếu sự kiện là nghiệp vụ bắt buộc phải xử lý, cần cân nhắc Redis Streams hoặc một hệ thống event/messaging có cơ chế lưu trữ và xác nhận xử lý.

## 6. So sánh vòng đời qua ba tình huống

### 6.1. Tình huống A: 100 request GET/SET

~~~text
HTTP request 1 -> GET -> response
HTTP request 2 -> SET -> response
...
HTTP request N -> GET -> response
~~~

Các thao tác ngắn có thể được driver multiplex trên native connection phù hợp (đặc biệt với Lettuce), hoặc dùng connection từ pool tùy cấu hình. Một lệnh hoàn tất không giữ connection ở trạng thái chờ dữ liệu dài hạn.

### 6.2. Tình huống B: 100 background worker cùng BRPOP 30 giây

~~~text
Worker 1   -> BRPOP queue 30 -> đang chờ
Worker 2   -> BRPOP queue 30 -> đang chờ
...
Worker 100 -> BRPOP queue 30 -> đang chờ
~~~

Nếu queue rỗng, các worker tiếp tục chờ. **Số worker đang chờ có thể trở thành yếu tố chi phối số connection chuyên biệt hoặc pool capacity**. Khi pool chỉ cho cấp một số lượng nhỏ connection tương ứng, các worker còn lại có thể bị kẹt ở bước mượn connection, gặp `max-wait` timeout hoặc exception. Điều này khác với 100 request GET/SET ngắn.

Chưa kể mỗi lời gọi đồng bộ còn giữ một worker thread phía ứng dụng, dù không bận CPU nhiều.

### 6.3. Tình huống C: 1 listener đăng ký 20 channels

~~~text
RedisMessageListenerContainer
  +-- events:order
  +-- events:payment
  +-- events:inventory
  '-- ... 17 channels khác

  => duy trì subscription và nhận thông điệp liên tục
~~~

Một container có thể multiplex nhiều listener/subscription thay vì tạo một connection riêng cho từng channel. Nhưng connection/lifecycle này **không trả về pool sau mỗi message**, vì nó cần tiếp tục nhận message mới.

## 7. Lettuce và Jedis khác nhau thế nào khi tổ chức connection?

| Khía cạnh | Lettuce | Jedis |
|---|---|---|
| Bản chất | Redis driver cho Java, có kết nối dựa trên mô hình bất đồng bộ/Netty | Redis driver cho Java với các API kết nối và pooling của riêng nó |
| Lệnh thường | Có thể chia sẻ native connection phù hợp với `LettuceConnectionFactory` mặc định | Phụ thuộc connection/client và pool được cấu hình |
| Lệnh blocking | Cần connection phù hợp để không ảnh hưởng luồng lệnh thường; factory có thể cấp dedicated connection | Dùng connection/client phục vụ thao tác chặn, chú ý thời gian mượn pool |
| Pub/Sub | Driver hỗ trợ subscription; Spring listener container quản lý vòng đời | Driver hỗ trợ subscription; Spring listener container quản lý vòng đời |
| Pool | Có thể cấu hình pooling cho những kết nối cần cấp riêng | Pool có vai trò lớn trong mô hình mượn/trả Jedis truyền thống |
| Điểm cần kiểm tra | `shareNativeConnection`, cấu hình pool, blocking/transaction/subscription | Pool sizing, lifecycle của Jedis connection, không chia sẻ connection đang có state |

Không nên sao chép công thức cấp connection của Lettuce sang Jedis. Số kết nối vật lý thực tế phụ thuộc driver/version, standalone hay cluster, cách factory khởi tạo, trạng thái kết nối, các command đồng thời và lựa chọn pooling.

### 7.1. Cấu hình chia sẻ native connection của Lettuce

`LettuceConnectionFactory` có thiết lập **shareNativeConnection**. Khi chia sẻ được bật trong cấu hình hỗ trợ:

- Lệnh thông thường không blocking/transaction có thể dùng native connection chia sẻ.
- Lệnh blocking và transaction thường yêu cầu connection chuyên biệt.
- Pool, nếu được cấu hình, có thể được dùng cho các connection cần cấp riêng theo cơ chế cụ thể của factory/driver.

Khi tắt chia sẻ, mỗi RedisConnection có thể cần được cấp một native connection riêng từ provider tương ứng. Điều đó làm thay đổi áp lực connection/pool và không nên thực hiện chỉ vì “càng nhiều connection càng nhanh”.

Việc cấu hình cụ thể còn phụ thuộc Spring Data Redis và Lettuce version; khi thay đổi giá trị này trong dự án thật, cần kiểm tra hành vi runtime và số connection đồng thời dưới workload của mình.

## 8. Pool đóng vai trò gì?

**Connection pool** giữ một tập connection để ứng dụng mượn và trả lại, giảm chi phí tạo mới đối với các connection cần cấp riêng và giới hạn số lượng connection đồng thời.

Pool thường có các trạng thái:

~~~text
                +------------------+
                |   IDLE / READY   |
                +------------------+
                         |
                      borrow
                         v
                +------------------+
                | ACTIVE / IN USE  |
                +------------------+
                         |
                       return
                         v
                +------------------+
                |   IDLE / READY   |
                +------------------+
~~~

Với thao tác ngắn, connection có thể được trả nhanh; với `BRPOP` chờ nhiều giây, connection tiếp tục **ACTIVE** trong lúc chờ; với Pub/Sub, subscription được giữ cho đến khi unsubscribe/stop chứ không phải mượn–trả theo từng message.

### 8.1. Ví dụ cấu hình pooling cho Lettuce trong Spring Boot

Một ứng dụng Spring Boot 3.x có thể khai báo:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    // Cần khi sử dụng Commons Pool 2 cho Lettuce pooling.
    implementation 'org.apache.commons:commons-pool2'
}
~~~

Cấu hình ví dụ:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 5s
      lettuce:
        pool:
          max-active: 16
          max-idle: 8
          min-idle: 1
          max-wait: 2s
~~~

Các con số ở trên **chỉ để minh họa cấu trúc cấu hình**, không phải khuyến nghị dùng nguyên trong production.

| Thuộc tính | Ý nghĩa thường gặp |
|---|---|
| `max-active` | Số connection tối đa được cấp đồng thời trong pool |
| `max-idle` | Số connection idle tối đa giữ trong pool |
| `min-idle` | Mục tiêu số connection idle tối thiểu |
| `max-wait` | Thời gian tối đa chờ mượn connection khi pool không có sẵn |

Cấu hình pool không thể tự giải quyết mọi vấn đề:

- Nếu Lettuce vẫn chia sẻ native connection cho GET/SET, những lệnh đó **không nhất thiết dùng một slot pool cho mỗi request**.
- Nếu 16 consumer cùng chờ BRPOP và một worker thứ 17 cần connection nhưng pool đã đầy, nó có thể phải đợi hoặc gặp lỗi khi quá `max-wait`.
- Nếu Pub/Sub dùng connection dài hạn, cần tính tài nguyên của subscription khi thiết kế tổng connection budget; không nên cho rằng message được xử lý xong thì connection lập tức về pool.
- Một số kết nối nội bộ của driver/topology có thể tồn tại ngoài cách đếm đơn giản của một pool.

### 8.2. Pool không phải worker queue

Một ví dụ cần hiểu rõ:

~~~text
Pool capacity: 4
Background workers: 10
Mỗi worker gọi BRPOP, chờ tối đa 30 giây

Workers 1..4:  có thể mượn 4 connection, đang BRPOP
Workers 5..10: đợi pool cấp connection hoặc hết max-wait
~~~

Tăng `max-active` lên 10 có thể giúp tất cả worker cùng chờ, nhưng cũng khiến nhiều connection và nhiều thread bị giữ lâu. Nếu Redis chỉ có ít job, **giảm số worker chờ** đôi khi hợp lý hơn tăng số socket.

Pool không thay thế:

- giới hạn concurrency ở tầng ứng dụng,
- backpressure và scheduling,
- timeout phù hợp,
- retry có kiểm soát,
- monitoring pool và Redis Server.

### 8.3. Kích thước pool phải dựa trên workload

Không có một con số `max-active` đúng cho mọi hệ thống. Khi dự kiến triển khai, cần biết:

1. Bao nhiêu luồng xử lý Redis đồng thời?
2. Bao nhiêu thao tác là blocking và mỗi lần có thể giữ connection bao lâu?
3. Pub/Sub có bao nhiêu container/subscription độc lập, vòng đời thế nào?
4. Driver/factory có dùng shared native connection không?
5. Redis Server và môi trường mạng cho phép bao nhiêu client connection?
6. Có ứng dụng khác đang dùng Redis, Sentinel, Cluster hoặc dịch vụ managed có hạn mức riêng không?

Đo các chỉ số như số borrowed/idle connection, số caller chờ pool, timeout khi lấy connection, command latency, số Redis clients và mức sử dụng thread của application. Những quan sát này đáng tin hơn việc chỉ tăng `max-active` theo cảm tính.

## 9. Vì sao không nên dùng chung một RedisConnection để vừa GET vừa blocking vừa subscribe?

Xét cách làm có vấn đề:

~~~java
// Minh họa thiết kế cần tránh: giữ connection dài hạn làm field singleton.
@Service
public class MixedConnectionAntiPattern {

    private final RedisConnection connection;

    public MixedConnectionAntiPattern(
            RedisConnectionFactory connectionFactory) {
        this.connection = connectionFactory.getConnection();
    }

    // Một method chạy BRPOP trong lúc method khác GET
    // hoặc SUBSCRIBE trên cùng connection: dễ đụng trạng thái,
    // thread-safety và lifecycle. Không triển khai như thế này.
}
~~~

Các nguy cơ:

- **Blocking:** một lệnh đang chờ dữ liệu có thể khiến thao tác khác không nhận phản hồi theo cách mong đợi trên cùng connection.
- **Pub/Sub:** connection có trạng thái subscription, có thể chỉ phục vụ một nhóm lệnh nhất định tùy protocol; các message đến bất kỳ thời điểm nào.
- **Thread safety:** `RedisConnection` của Spring không được xem là đối tượng thread-safe để chia sẻ tùy tiện.
- **Close/lifecycle:** một luồng đóng connection có thể phá vỡ công việc đang chờ hoặc subscription do luồng khác sở hữu.
- **Transaction/pipeline:** đây cũng là những trạng thái connection cần cách xử lý riêng, làm việc chia sẻ bừa bãi càng nguy hiểm.

Thay bằng ranh giới rõ ràng:

~~~text
Service đọc/ghi thường  --> StringRedisTemplate
Worker chờ queue        --> ListOperations.rightPop(..., timeout)
Listener nhận sự kiện   --> RedisMessageListenerContainer

Tất cả có thể dùng RedisConnectionFactory phù hợp,
nhưng mỗi loại tác vụ có vòng đời connection riêng.
~~~

Chia sẻ **factory** là cách bình thường; chia sẻ **RedisConnection đang thực thi lệnh chặn/subscription** giữa các thread tùy tiện là điều cần tránh.

## 10. Thiết kế worker chặn an toàn hơn

Lệnh blocking không có gì sai; vấn đề là dùng nó ở đâu và điều khiển vòng đời thế nào.

### 10.1. Dành tài nguyên riêng cho consumer

Một consumer đợi queue nên chạy trên một background worker/managed executor có giới hạn, tách khỏi thread xử lý request HTTP. Với WebFlux, không gọi trực tiếp API Redis blocking trên event-loop. Nếu ứng dụng có cả traffic API lớn và nhiều worker blocking, nên xét **hạn mức concurrency riêng** và khi cần một factory/pool phù hợp để hai loại workload không tranh cạn cùng nguồn tài nguyên.

Ví dụ khung luồng xử lý:

~~~java
public void consumeOnce() {
    String item = jobQueue.receiveJob(); // Chờ tối đa 5 giây.

    if (item == null) {
        // Hết timeout; có thể kiểm tra yêu cầu shutdown.
        return;
    }

    processItem(item); // Logic nghiệp vụ của worker.
}
~~~

Ví dụ trên là **một lần nhận**, được gọi bởi worker do ứng dụng quản lý. Việc tổ chức vòng lặp, shutdown, retry/backoff, số worker và logging là phần của kiến trúc background processing; không nên tự tạo thread vô hạn cho mỗi HTTP request.

### 10.2. Ưu tiên timeout hữu hạn để dừng được worker

Nếu consumer dùng thời gian chờ hữu hạn, nó có cơ hội quay lại kiểm tra cờ dừng. Chờ vô hạn có thể hợp lý với một số thiết kế, nhưng lúc shutdown cần đảm bảo cancellation/đóng connection có kiểm soát.

Ví dụ:

~~~text
while application is running:
    BRPOP queue 5 seconds
    if item received:
        process item
    else:
        check shutdown condition
~~~

Đây là pseudocode, không phải một đoạn Java phải copy vào service.

### 10.3. Xác định kỳ vọng giao hàng

Redis List với BRPOP có mô hình lấy phần tử ra khỏi queue trước khi xử lý. Nếu xử lý lỗi sau khi pop, cần thiết kế retry/idempotency và cách khôi phục job. Đối với yêu cầu delivery đáng tin cậy hoặc nhiều consumer độc lập, Redis Streams với consumer groups có thể thích hợp hơn.

**Tăng pool không biến Redis List thành queue có ACK** và cũng không khiến Pub/Sub tự lưu message offline.

## 11. Kiểm tra hành vi bằng redis-cli

Có thể làm ba thí nghiệm trên Redis Server dùng riêng cho môi trường học tập. Mỗi lệnh ở terminal là một chương trình client khác nhau; mục tiêu là nhận diện hành vi chờ và vòng đời.

### 11.1. Lệnh thường trả về ngay

~~~bash
redis-cli SET demo:conn:status ready
redis-cli GET demo:conn:status
redis-cli DEL demo:conn:status
~~~

Kết quả GET điển hình:

~~~text
"ready"
~~~

### 11.2. BRPOP chờ trên một kết nối

Terminal A:

~~~bash
redis-cli BRPOP demo:jobs 15
~~~

Terminal B, chạy trước khi hết 15 giây:

~~~bash
redis-cli LPUSH demo:jobs task-001
~~~

Terminal A nhận item và thoát khỏi lệnh. Nếu không có item đến kịp, terminal A trả kết quả rỗng sau timeout; không có nghĩa Redis Server bị lỗi.

### 11.3. SUBSCRIBE tiếp tục chờ nhiều message

Terminal A:

~~~bash
redis-cli SUBSCRIBE demo:events
~~~

Terminal B:

~~~bash
redis-cli PUBLISH demo:events "event-one"
redis-cli PUBLISH demo:events "event-two"
~~~

Terminal A tiếp tục ở chế độ subscription sau khi nhận message thứ nhất và thứ hai. Không có bước “tự kết thúc sau khi đọc xong một message” như GET hoặc BRPOP. Kết thúc ví dụ bằng cách dừng lệnh subscribe tại terminal A.

Nếu chạy `PUBLISH` **trước khi terminal A subscribe**, terminal A sẽ không nhận lại message cũ khi đăng ký. Đây là khác biệt quan trọng so với item còn lưu trong list.

### 11.4. Quan sát connection thực tế

Khi có quyền quản trị/quan sát, Redis có lệnh như `CLIENT LIST` để xem các client connection đang có. Có thể đối chiếu trong môi trường test lúc:

- chạy vài GET/SET,
- bật nhiều consumer BRPOP chờ,
- bật một subscription,
- dừng listener/consumer và chờ driver giải phóng tài nguyên.

Thông tin trả về của `CLIENT LIST` thay đổi theo phiên bản Redis, driver và các bước reconnect; không dùng một con số socket cố định làm kết luận chung. Một số lệnh quan sát yêu cầu Redis ACL phù hợp; tránh dùng lệnh theo dõi nặng trên production chỉ vì đang thử bài học.

## 12. Các lỗi thường gặp khi tổ chức connection và pool

| Triệu chứng | Khả năng cần điều tra | Hướng xử lý |
|---|---|---|
| GET/SET hoạt động nhưng nhiều worker BRPOP bị timeout lấy connection | Pool cho connection chuyên biệt bị cạn | Xem số worker blocking, `max-active`, `max-wait` và thời gian chờ |
| Request HTTP đột ngột chậm khi nhiều consumer chờ | Tài nguyên connection/thread dùng chung không được phân bổ hợp lý | Tách background worker, xem cấu hình driver và concurrency |
| BRPOP trả null sau vài giây | List không có dữ liệu trong thời gian chờ | Phân biệt timeout bình thường với lỗi kết nối |
| BRPOP bị exception trước thời gian chờ dự kiến | Command/client timeout hoặc network lỗi | Đối chiếu blocking timeout và driver timeout |
| Listener Pub/Sub không nhận sự kiện sau reconnect | Khoảng disconnect, resubscribe hoặc lỗi lifecycle | Theo dõi listener container và network; nhớ Pub/Sub không replay |
| Subscriber mới không nhận message cũ | Semantics Pub/Sub | Dùng cơ chế lưu message nếu cần replay |
| Thêm listener và số connection tăng bất ngờ | Nhiều container/factory hoặc topology tạo subscription khác nhau | Kiểm tra container đã được chia sẻ/cấu hình chưa |
| Pool `max-active` tăng nhưng GET/SET latency không đổi | Lệnh thường đang dùng shared native connection hoặc nghẽn không nằm ở pool | Quan sát latency, CPU, network, Redis load |
| Đóng connection làm hỏng consumer hoặc listener khác | Chia sẻ sai RedisConnection/native resource | Dùng template/container quản lý vòng đời, không tự đóng tài nguyên do Spring sở hữu |
| Pool có idle connection nhưng ứng dụng vẫn lỗi | Lỗi auth/TLS, stale connection, routing, server hoặc timeout | Xem stack trace và tầng thực sự phát sinh lỗi |
| Worker thread tăng không kiểm soát | Mỗi request tạo một thread/chờ blocking | Sử dụng managed executor có giới hạn và cơ chế dừng |

### 12.1. Dấu hiệu cạn pool không phải lỗi Redis Server “không xử lý SET”

Khi tất cả connection trong pool đang được mượn bởi các consumer chờ, một caller mới có thể thất bại **trước cả khi gửi được lệnh Redis**. Redis Server có thể vẫn khỏe, nhưng ứng dụng chưa có resource client để gửi yêu cầu.

Phân tích stack trace giúp phân biệt:

~~~text
Chờ connection từ pool -> timeout  (client resource exhaustion)
Gửi lệnh thành công -> Redis trả lỗi (server/command semantics)
Gửi lệnh -> mất mạng/timeout        (connection/driver/network)
~~~

Điều chỉnh đúng tầng thường hiệu quả hơn tăng timeout không rõ nguyên nhân.

### 12.2. Redis timeout, pool wait và Pub/Sub reconnect là ba thứ khác nhau

- `BRPOP ... 5` trả về rỗng sau 5 giây có thể là **hành vi bình thường**.
- Pool không cấp được connection trong 2 giây có thể là **thiếu tài nguyên client**.
- Subscriber vừa reconnect không thấy message lúc offline là **đặc tính không replay** của Pub/Sub.

Ba tình huống này có biểu hiện “không nhận dữ liệu” giống nhau nhưng nguyên nhân và cách giải quyết hoàn toàn khác.

## 13. Transaction và pipeline có liên quan gì?

Dù bài học tập trung vào ba nhóm lệnh, cần biết rằng **transaction** và **pipeline** cũng tạo yêu cầu riêng về trạng thái connection.

- Redis transaction dùng `MULTI`, `EXEC`, có trạng thái nhóm lệnh gắn với connection. Spring Data Redis cần quản lý connection đúng phạm vi transaction.
- Pipeline gom lệnh để giảm round trips và xử lý phản hồi theo cách riêng; các lời gọi trên connection đang mở pipeline không giống hoàn toàn GET/SET bình thường.
- Vì thế, Lettuce có thể chọn connection chuyên biệt cho transaction; không nên dựa vào giả định “mọi command trừ Pub/Sub đều dùng chung một native connection”.

Lý do là **tính trạng thái của thao tác**, không chỉ tên lệnh. Một phép so sánh đầy đủ cần xét lệnh thường không stateful, lệnh chặn, Pub/Sub, transaction và pipeline.

## 14. Đồng bộ và reactive không làm thay đổi ngữ nghĩa Redis Server

Spring Data Redis cung cấp:

- `RedisTemplate`, `StringRedisTemplate`: API imperative/synchronous.
- `ReactiveRedisTemplate`, `ReactiveStringRedisTemplate`: API theo mô hình reactive khi driver/cấu hình hỗ trợ.
- Các abstraction listener dành cho Pub/Sub, bao gồm container và API reactive phù hợp.

Một lời gọi reactive không chặn thread theo cách API đồng bộ trong quá trình đợi kết quả, nhưng **lệnh blocking trên Redis Server vẫn có thể cần một connection đang chờ phản hồi**. Reactive cũng không làm Pub/Sub trở thành hàng đợi có replay. Cần phân biệt **không chặn thread phía ứng dụng** với **không giữ tài nguyên kết nối phía server**.

Không gọi API blocking đồng bộ trên event-loop WebFlux; nếu bắt buộc tương tác với API đồng bộ, phải chuyển sang executor/scheduler phù hợp và cân nhắc chi phí tài nguyên. Trong kiến trúc reactive thuần, chọn API reactive phù hợp và thiết kế concurrency/backpressure rõ ràng.

## 15. Chọn mô hình nào cho từng mục đích?

| Nhu cầu | Cách tiếp cận phù hợp ban đầu | Vì sao |
|---|---|---|
| Cache một giá trị có TTL | `StringRedisTemplate` hoặc Spring Cache | Lệnh GET/SET ngắn, dễ quản lý vòng đời |
| Tăng bộ đếm truy cập | `increment()` trên template | Lệnh `INCR` thực thi atomic ở Redis |
| Chờ job mới trong list | `rightPop(key, timeout)` ở background worker | Lệnh chặn giúp tránh polling liên tục |
| Nhận thông báo realtime cho nhiều instance | `RedisMessageListenerContainer` + Pub/Sub | Nhận broadcast khi đang subscribed |
| Cần xử lý lại sự kiện khi consumer offline | Redis Streams/consumer group hoặc broker phù hợp | Pub/Sub cơ bản không lưu/replay sự kiện |
| Worker có nhiều tác vụ nặng | Executor có giới hạn và quy trình retry/ACK phù hợp | Không nên dùng connection pool thay thế việc điều phối worker |
| Cần kiểm soát kết nối cho lệnh chuyên biệt | RedisConnection/driver API với lifecycle rõ ràng | Phù hợp cho tính năng thấp hơn abstraction template |

## 16. Tình huống thiết kế kết hợp: API, job worker và notification

Một ứng dụng bán hàng có ba chức năng:

1. **API đọc trạng thái giỏ hàng** qua GET.
2. **Worker chờ job xử lý hóa đơn** qua BRPOP.
3. **Listener nhận sự kiện thay đổi giá** qua Redis Pub/Sub.

Cách tổ chức:

~~~text
                    Spring Boot Application
   +-----------------------------------------------------+
   |                                                     |
   |   CartController --> CartService                    |
   |                      |                              |
   |                      v                              |
   |               StringRedisTemplate                   |
   |                     GET                             |
   |                                                     |
   |   InvoiceWorker --> JobQueue                        |
   |                      |                              |
   |                      v                              |
   |               RedisTemplate                         |
   |                 BRPOP 5s                            |
   |                                                     |
   |   PriceEventListener <-- RedisMessageListenerContainer
   |                              SUBSCRIBE              |
   |                                                     |
   +----------------------+------------------------------+
                          |
                 RedisConnectionFactory
                          |
                     Lettuce/Jedis
                          |
                       Redis Server
~~~

Giả sử lúc cao điểm có:

- 150 request GET/SET đồng thời,
- 12 invoice workers đang BRPOP chờ,
- 1 listener container đăng ký 4 channels.

Không thể kết luận ứng dụng cần **167 connection** bằng phép cộng 150 + 12 + 1 + 4. Với Lettuce, các request thường có thể chia sẻ native connection; 12 worker blocking có thể cần connection riêng; Pub/Sub có connection dài hạn do container quản lý; topology và pool cấu hình còn ảnh hưởng số lượng thực.

Phương pháp đúng là xác định **loại kết nối, mức đồng thời và vòng đời** của từng workload, sau đó đo số kết nối thực tế và hiệu chỉnh giới hạn tài nguyên.

## 17. Những nhầm lẫn cần tránh

**“Nếu GET/SET chạy tốt thì BRPOP cũng không thể thiếu connection.”** Không đúng. Blocking worker có thể phải mượn connection chuyên biệt trong thời gian lâu và gây áp lực pool.

**“Pub/Sub chỉ là một lệnh Redis nên dùng xong sẽ trả connection về pool.”** Không đúng. Subscription tồn tại cho tới khi bị hủy/dừng, và có thể nhận nhiều thông điệp trong suốt thời gian đó.

**“Mỗi RedisTemplate method luôn mở một TCP socket mới.”** Không đúng. Template lấy abstraction connection, còn native connection có thể được chia sẻ hoặc pool quản lý.

**“Có 100 request HTTP thì luôn cần pool 100 connections.”** Không đúng. Tùy driver, connection sharing, thời gian mỗi lệnh và yêu cầu concurrency.

**“Nếu BRPOP trả null nghĩa là Redis bị mất kết nối.”** Không đúng. Đó có thể chỉ là timeout do queue rỗng. Lỗi mất kết nối thường có exception hoặc dấu hiệu khác.

**“Bật pool là giải quyết được Pub/Sub mất message.”** Không đúng. Pool quản lý connection; Pub/Sub không cung cấp lưu trữ/replay cho subscriber offline.

**“Reactive có nghĩa không còn connection chờ ở Redis.”** Không đúng. Reactive chủ yếu thay đổi cách phía ứng dụng xử lý bất đồng bộ; Redis Server và protocol vẫn có trạng thái blocking/subscription.

**“Đóng một RedisConnection luôn đóng socket.”** Không đúng với mọi implementation. Nó có thể giải phóng wrapper/trả native connection vào pool.

## 18. Câu hỏi tự kiểm tra

**1. Hai consumer đều gọi `BRPOP queue 30` khi queue trống. Chúng khác hai lời gọi `GET key` thế nào?**

Hai BRPOP có thể chờ lâu và giữ connection phục vụ lệnh blocking; GET thường trả nhanh với giá trị hoặc nil. Khi tăng concurrency, các connection dành cho lệnh blocking cần được tính riêng theo hành vi driver/factory.

**2. Vì sao `RedisMessageListenerContainer` phù hợp hơn việc tự giữ `RedisConnection` để subscribe trong một `@Service`?**

Vì container quản lý lifecycle đăng ký, callback, subscription và việc sử dụng connection trong hệ sinh thái Spring, giảm nguy cơ chia sẻ connection sai hoặc quên giải phóng khi shutdown.

**3. Pool `max-active=8`, có 8 worker đang blocking. Worker thứ 9 có chắc sẽ gửi được BRPOP ngay không?**

Không. Nếu cả 8 connection chuyên biệt của pool đã được mượn và worker thứ 9 phải mượn cùng pool, nó sẽ chờ hoặc gặp timeout tùy cấu hình. Nhưng cần xác định implementation nào thực sự sử dụng pool trước khi kết luận.

**4. Nếu Pub/Sub listener disconnect trong 3 giây rồi reconnect, message publish trong khoảng đó có tự về lại không?**

Không theo Pub/Sub cơ bản. Cần cơ chế lưu/đọc lại độc lập nếu bắt buộc bảo đảm xử lý.

**5. Vì sao không nên gọi `rightPop(key, Duration.ofSeconds(30))` trên thread xử lý request WebFlux?**

Đây là API synchronous có thể chặn thread đang gọi, gây ảnh hưởng khả năng phục vụ request của event-loop. Dùng background worker hoặc API reactive phù hợp.

**6. Với Lettuce shareNativeConnection bật, bật pool có nhất thiết khiến tất cả GET/SET mượn connection từ pool?**

Không. Các lệnh thường có thể đi trên native connection chia sẻ; pool có thể chủ yếu phục vụ thao tác cần connection chuyên biệt.

**7. Khi một BRPOP hết timeout, có cần đóng cả RedisConnectionFactory không?**

Không. Factory là bean lâu dài. Template hoặc code quản lý thao tác giải phóng RedisConnection theo vòng đời phù hợp; factory tiếp tục phục vụ các lệnh khác.

## Ghi nhớ

~~~text
LỆNH THƯỜNG
  GET / SET / INCR ...
  -> request–response
  -> kết thúc nhanh trong điều kiện thông thường
  -> có thể chia sẻ native connection nếu driver hỗ trợ

LỆNH CHẶN
  BLPOP / BRPOP / XREAD BLOCK ...
  -> một yêu cầu có thể chờ dữ liệu nhiều giây
  -> cần connection phù hợp/dành riêng khi chờ
  -> nhiều waiter có thể gây áp lực pool và worker threads

PUB/SUB
  SUBSCRIBE / PSUBSCRIBE ...
  -> subscription dài hạn, liên tục nhận message mới
  -> container/driver quản lý connection và lifecycle riêng
  -> không lưu message để replay cho subscriber offline

REDISCONNECTIONFACTORY
  -> cung cấp RedisConnection dựa trên driver/configuration

CONNECTION POOL
  -> mượn, giữ và trả các connection được quản lý
  -> không quyết định semantics của lệnh hoặc bảo đảm giao hàng
~~~

Muốn cấu hình Spring Data Redis ổn định, hãy bắt đầu từ **loại lệnh và vòng đời sử dụng connection**. Lệnh thường, lệnh blocking và subscription có các nhu cầu khác nhau; chia sẻ factory được, nhưng cách dùng connection, số worker, thời gian chờ và cơ chế giám sát phải phù hợp từng loại.
