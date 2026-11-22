# Mất thông điệp khi subscriber ngắt kết nối

Trong **Spring Data Redis**, Redis Pub/Sub thường được dùng để phát thông báo thời gian thực giữa các ứng dụng: một dịch vụ phát sự kiện đơn hàng vừa thay đổi, các dịch vụ khác đang đăng ký kênh sẽ nhận thông báo và phản ứng. Cách làm này đơn giản, độ trễ thấp, nhưng có một giới hạn quan trọng: **Redis Pub/Sub không lưu thông điệp để phát lại cho subscriber đã ngắt kết nối**.

Nếu một subscriber bị mất mạng, dừng để triển khai phiên bản mới, chưa kịp đăng ký kênh hoặc không thể xử lý thông điệp, những sự kiện được phát trong khoảng thời gian đó có thể **mất vĩnh viễn đối với subscriber ấy**. Kết nối lại chỉ khôi phục việc nhận **thông điệp mới**; nó không tạo ra backlog để đọc bù.

Bài học này phân tích giới hạn delivery của Pub/Sub, những khoảng thời gian dễ mất thông điệp trong Spring Data Redis, cách quan sát và thử nghiệm, cùng các thiết kế thay thế khi nghiệp vụ thực sự cần xử lý đủ sự kiện.

## 1. Pub/Sub là kênh thông báo trực tiếp, không phải hàng đợi bền vững

Redis Pub/Sub có hai vai trò:

- **Publisher:** gửi nội dung vào một kênh bằng lệnh `PUBLISH`.
- **Subscriber:** đăng ký kênh bằng `SUBSCRIBE` hoặc mẫu kênh bằng `PSUBSCRIBE` và nhận thông điệp khi đang kết nối, đang đăng ký.

Ví dụ:

```text
                    Redis Pub/Sub
                          |
           PUBLISH orders.events.v1
                          |
            +-------------+-------------+
            |             |             |
         App A          App B          App C
        SUBSCRIBE      SUBSCRIBE      DISCONNECTED
            |             |             |
         Nhận sự kiện  Nhận sự kiện   Không nhận
                                      |
                                Kết nối lại
                                      |
                                Chỉ nhận sự kiện
                                phát sau thời điểm
                                đăng ký trở lại
```

Redis Pub/Sub không quản lý một hàng đợi riêng cho mỗi subscriber, không có message ID bền vững, không có acknowledgment từ nghiệp vụ và không có cơ chế “đọc lại từ vị trí cuối” như một hệ thống log sự kiện.

Tính chất cốt lõi là **at-most-once delivery theo mô hình Pub/Sub**: một thông điệp đã được Redis phát đi sẽ không được Redis Pub/Sub tự phát lại cho subscriber nếu subscriber không nhận hoặc không xử lý được. Trong thực tế, ứng dụng có thể tự phát lại sự kiện bằng cơ chế riêng và gây trùng, nhưng đó **không phải redelivery có quản lý bởi Redis Pub/Sub**.

### Bảng so sánh nhanh

| Thuộc tính | Redis Pub/Sub |
|---|---|
| Thông báo tức thời cho subscriber đang kết nối | Có |
| Lưu thông điệp cho subscriber offline | Không |
| Đọc lại theo message ID hoặc offset | Không |
| Xác nhận đã xử lý thành công bằng ACK | Không |
| Theo dõi danh sách thông điệp còn chờ xử lý | Không |
| Redis tự gửi lại khi callback xử lý lỗi | Không |
| Dùng cho thông báo “có gì đó vừa thay đổi” | Phù hợp |
| Dùng làm nguồn duy nhất cho nghiệp vụ không được mất sự kiện | Không phù hợp |

Một kênh có thể có nhiều subscriber đang trực tuyến. Mỗi subscriber có thể nhận cùng một thông điệp, nhưng điều đó không khiến thông điệp trở thành dữ liệu được giữ lại sau khi mọi subscriber rời đi.

## 2. Kịch bản mất thông điệp khi subscriber offline

Giả sử `notification-service` đang đăng ký kênh `orders.events.v1` để cập nhật bảng trạng thái đơn hàng:

```text
Thời gian    Publisher                  Subscriber
---------------------------------------------------------------
10:00:00     PUBLISH order-100:CREATED   Đang kết nối -> nhận
10:00:05     PUBLISH order-100:PAID      Đang kết nối -> nhận
10:00:10     --                          Mất kết nối Redis
10:00:12     PUBLISH order-100:PACKED    Offline -> mất
10:00:15     PUBLISH order-100:SHIPPED   Offline -> mất
10:00:20     --                          Kết nối trở lại
10:00:21     PUBLISH order-100:DELIVERED Online -> nhận
```

Sau khi kết nối trở lại, subscriber có thể thấy chuỗi:

```text
CREATED -> PAID -> DELIVERED
```

Nó **không tự nhận được `PACKED` và `SHIPPED`**. Nếu ứng dụng dùng Pub/Sub chỉ để đánh thức một worker đọc lại trạng thái mới nhất từ database, việc thiếu hai thông báo trung gian có thể chấp nhận được khi có đường đồng bộ bù. Nhưng nếu mỗi thông điệp có nghĩa là “thực hiện một lần thanh toán”, “trừ một lần tồn kho”, “gửi một email bắt buộc”, mất thông điệp là lỗi nghiệp vụ nghiêm trọng.

Điều cần phân biệt:

- **Trạng thái hiện tại:** nhiều khi chỉ cần biết đơn hàng cuối cùng đang `DELIVERED`.
- **Sự kiện bắt buộc:** có nghiệp vụ phải xử lý đủ từng sự kiện, kể cả nếu trạng thái cuối đã thay đổi.

Pub/Sub phù hợp hơn với loại thứ nhất khi có nguồn dữ liệu chính để truy vấn lại.

## 3. Thử ngay bằng Redis CLI

Có thể tái hiện trên một Redis thử nghiệm, không cần viết Java.

### Terminal A: đăng ký kênh

```bash
redis-cli SUBSCRIBE orders.events.demo
```

Terminal A chuyển sang chế độ nhận thông điệp từ kênh. Khi có publisher gửi, terminal A hiển thị thông điệp.

### Terminal B: phát sự kiện khi A đang online

```bash
redis-cli PUBLISH orders.events.demo "order-1:CREATED"
```

Terminal A nhận `order-1:CREATED`. Kết quả số mà lệnh `PUBLISH` trả về phản ánh số subscriber được Redis tính là nhận thông điệp theo ngữ nghĩa lệnh và topology hiện tại; **không phải số nghiệp vụ xử lý thành công**.

### Dừng subscriber

Trong Terminal A, nhấn `Ctrl+C` để thoát `redis-cli SUBSCRIBE`. Sau đó Terminal B phát tiếp:

```bash
redis-cli PUBLISH orders.events.demo "order-1:PAID"
redis-cli PUBLISH orders.events.demo "order-1:SHIPPED"
```

Nếu không còn subscriber tương ứng, Redis vẫn chấp nhận lệnh phát. Pub/Sub **không tạo backlog** cho terminal vừa thoát.

### Đăng ký trở lại

Terminal A chạy lại:

```bash
redis-cli SUBSCRIBE orders.events.demo
```

A **không nhận lại** hai thông điệp `PAID` và `SHIPPED` trước đó. Khi Terminal B phát mới:

```bash
redis-cli PUBLISH orders.events.demo "order-1:DELIVERED"
```

A sẽ nhận `DELIVERED`.

Đây là đặc tính thiết kế của Redis Pub/Sub, không phải lỗi cấu hình Spring Boot, driver Lettuce hay xử lý `MessageListener`.

## 4. Tích hợp Redis Pub/Sub với Spring Data Redis

Spring Data Redis hỗ trợ đăng ký kênh thông qua `RedisMessageListenerContainer`. Container quản lý quá trình thiết lập subscription và gửi thông điệp đến các `MessageListener` đã cấu hình.

Ví dụ các dependency Spring Boot dùng với Redis:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Cấu hình kết nối Redis minh họa:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
```

Với môi trường production, sử dụng host, TLS, credential, timeout và topology đúng hạ tầng; không đưa thông tin bí mật vào mã nguồn.

### 4.1. Subscriber bằng RedisMessageListenerContainer

```java
import java.nio.charset.StandardCharsets;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class RedisPubSubConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(RedisPubSubConfiguration.class);

    @Bean
    public MessageListener orderEventListener(
            OrderEventHandler handler) {

        return (Message message, byte[] pattern) -> {
            String payload = new String(
                    message.getBody(),
                    StandardCharsets.UTF_8);

            // Handler xử lý theo hợp đồng payload của ứng dụng.
            handler.onNotification(payload);
        };
    }

    @Bean
    public RedisMessageListenerContainer messageListenerContainer(
            RedisConnectionFactory connectionFactory,
            MessageListener orderEventListener) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.addMessageListener(
                orderEventListener,
                new ChannelTopic("orders.events.v1"));

        // Ghi nhận lỗi callback; không có Pub/Sub ACK để replay.
        container.setErrorHandler(error ->
                log.error("Redis Pub/Sub listener failed", error));

        return container;
    }
}
```

Interface của handler:

```java
public interface OrderEventHandler {
    void onNotification(String payload);
}
```

Nếu handler ném exception, error handler có thể ghi nhận lỗi, nhưng **Redis không tự đưa thông điệp đó trở lại hàng đợi**, vì Pub/Sub không có hàng đợi bền. Việc ghi log thành công cũng không làm thông điệp đã mất xuất hiện lại.

Container giúp quản lý subscription trong lifecycle của Spring và khả năng phục hồi kết nối theo driver/cấu hình, nhưng **reconnect không đồng nghĩa replay**.

### 4.2. Publisher bằng StringRedisTemplate

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final StringRedisTemplate redis;

    public OrderEventPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long publish(String payload) {
        Long subscribers =
                redis.convertAndSend("orders.events.v1", payload);
        return subscribers == null ? 0L : subscribers;
    }
}
```

`convertAndSend` gửi lệnh `PUBLISH` theo serializer của template. Với `StringRedisTemplate`, payload minh họa được serialize thành chuỗi.

**Giá trị trả về không xác nhận việc xử lý nghiệp vụ.** Một subscriber có thể được Redis tính vào số nhận, nhưng ứng dụng đóng kết nối ngay sau đó, callback lỗi, process crash hoặc không commit được dữ liệu. Trong Redis Cluster, cách tính số subscriber còn liên quan đến topology và phạm vi nút xử lý. Không dùng một số dương trả từ `PUBLISH` làm bằng chứng “mọi consumer đã xử lý xong”.

### 4.3. Nhất quán serialization giữa publisher và subscriber

`Message.getBody()` cung cấp dữ liệu dạng byte. Nếu publisher phát JSON, subscriber có thể deserialize JSON theo schema có version. Nếu publisher dùng Java/JDK serializer hoặc một serializer khác, việc lấy UTF-8 string như ví dụ có thể không đúng.

Hợp đồng truyền thông nên xác định:

- Channel name và phiên bản, ví dụ `orders.events.v1`.
- Encoding và định dạng, ví dụ UTF-8 JSON.
- Các trường bắt buộc và version payload.
- Phân biệt notification với dữ liệu nguồn.
- Định dạng ID, tenant và yêu cầu bảo mật.

Một message được nhận thành công ở tầng TCP vẫn có thể không xử lý được nếu payload không tương thích.

## 5. Những thời điểm Spring subscriber có thể bỏ lỡ thông điệp

Không phải chỉ khi server Redis sập thì mới mất message. Các khoảng mất thông điệp còn có thể xuất hiện trong hoạt động bình thường:

| Tình huống | Điều có thể xảy ra | Vì sao thông điệp mất? |
|---|---|---|
| Ứng dụng khởi động nhưng chưa subscribe xong | Publisher phát trước khi subscription có hiệu lực | Redis không giữ lại cho subscriber chưa đăng ký |
| Rolling deployment | Instance cũ dừng, instance mới chưa sẵn sàng | Có khoảng trống không có listener của instance đó |
| Redis connection mất tạm thời | Container đang tìm cách reconnect | Thông điệp phát trong thời gian ngắt không được replay |
| Network partition hoặc failover | Subscription bị cắt rồi thiết lập lại | Redis Pub/Sub không có offset để đọc bù |
| Consumer xử lý chậm | Buffer client tăng, có thể bị ngắt khi vượt giới hạn | Những thông điệp chưa được xử lý không có ACK/retry bền |
| Callback ném exception | Payload đã được phát/nhận nhưng handler thất bại | Redis không biết trạng thái xử lý nghiệp vụ |
| Process crash sau khi nhận message | Handler chưa hoàn tất side effect | Không có cơ chế lấy lại message sau restart |
| Subscriber dùng sai channel hoặc serializer | Không nhận hoặc không đọc được message | Subscription/contract không đúng, không có replay tự động |

### Khoảng hở lúc khởi động

Một ứng dụng có thể đã “healthy” ở mức HTTP nhưng listener chưa hoàn tất subscription. Nếu publisher bắt đầu phát ngay trong khoảng này, event có thể mất đối với instance đó.

Đừng coi sự kiện Spring application start, bean đã tạo hoặc Redis TCP connection mở là bằng chứng rằng **subscription đã sẵn sàng nhận đúng kênh**. Nếu nghiệp vụ cần kiểm soát startup, phải xác định chính xác điều kiện readiness theo cách thư viện, hạ tầng và kiến trúc thực tế hỗ trợ.

Ngay cả khi có readiness thật, **khoảng mất kết nối về sau vẫn không được bù** bằng Pub/Sub.

### Khoảng hở lúc reconnect

Giả sử:

```text
T0  Subscription đang hoạt động.
T1  Mất kết nối.
T2  Publisher gửi event A.
T3  Publisher gửi event B.
T4  Listener container reconnect, đăng ký lại channel.
T5  Publisher gửi event C.
```

Subscriber có thể nhận C, nhưng không nhận A và B. Logic “thử kết nối lại đến khi thành công” chỉ phục hồi trạng thái online ở T4; nó không thể truy ngược các event từ T1 đến T4.

## 6. Pub/Sub không có ACK xử lý và không có replay

Trong một hệ thống hàng đợi có ACK, consumer thường nhận message, xử lý, xác nhận hoàn thành; nếu consumer dừng trước khi ACK, message có thể được phân phối lại. Redis Pub/Sub **không có bước ACK đó**.

```text
Pub/Sub:
Publisher -> Redis -> Subscriber -> Handler
                       |
                       +-- handler lỗi
                       |
                       +-- Redis không biết và không gửi lại

Hàng đợi/stream có ACK:
Publisher -> Durable log -> Consumer -> Handler -> ACK
                 |                    |
                 |                    +-- lỗi trước ACK
                 +-- có thể giữ message để xử lý lại
```

Không thể giải quyết thiếu ACK bằng cách thêm một dòng `try/catch` quanh callback rồi “throw lại” để Redis gửi lại. Throw có thể giúp ghi log hoặc phục vụ chính sách lỗi của ứng dụng, nhưng **Redis Pub/Sub không có hàng đợi chưa ACK**.

### Phân biệt đã phát, đã nhận và đã xử lý

Cần tách ba trạng thái:

1. **Published:** Redis nhận lệnh `PUBLISH`.
2. **Received:** kết nối subscriber đã nhận và chuyển thông điệp vào client/handler.
3. **Processed:** nghiệp vụ đã hoàn tất thao tác, như ghi database hoặc gửi notification.

Một kết quả `PUBLISH` thành công không chứng minh trạng thái 2 hay 3 cho từng subscriber. Một log “Received message” cũng chưa chứng minh trạng thái 3 nếu handler chưa hoàn tất.

## 7. Khi nào mất thông điệp là chấp nhận được?

Không phải tất cả kênh Pub/Sub đều cần độ tin cậy như message queue. Redis Pub/Sub vẫn rất phù hợp cho những notification có thể bị bỏ lỡ mà hệ thống vẫn đúng nhờ một đường đồng bộ khác.

Ví dụ thường chấp nhận mất một số thông báo:

- Thông báo giao diện “có dữ liệu mới” để client tự gọi API lấy state hiện tại.
- Tín hiệu đánh thức một worker vốn **định kỳ quét nguồn dữ liệu**.
- Cập nhật dashboard có chu kỳ refresh lại.
- Invalidation cache có TTL đủ ngắn và có cơ chế đối soát; nếu bỏ lỡ, dữ liệu cũ vẫn được giới hạn theo chính sách.
- Thông báo không quan trọng về trạng thái tức thời, khi người dùng có thể refresh để xem hiện tại.

Ví dụ không nên dùng Redis Pub/Sub làm kênh duy nhất:

- Trừ tồn kho chính xác một lần cho mỗi đơn.
- Gửi hóa đơn bắt buộc sau khi thanh toán.
- Xử lý hoàn tiền hoặc quyết toán.
- Thực thi workflow phải có đầy đủ từng bước sự kiện.
- Tạo audit trail hoặc nhật ký tuân thủ.
- Đồng bộ dữ liệu mà một message bị mất sẽ gây lệch vĩnh viễn.

**Nguyên tắc:** Nếu bỏ lỡ một sự kiện mà hệ thống vẫn có thể tự phục hồi từ nguồn sự thật, Pub/Sub có thể làm “tín hiệu nhanh”. Nếu phải xử lý **từng sự kiện** và có chứng từ xử lý, cần hệ thống lưu thông điệp và trạng thái tiêu thụ.

## 8. Biện pháp giảm rủi ro khi vẫn dùng Pub/Sub

Với các kênh chỉ dùng để thông báo, có thể tăng khả năng phục hồi bằng những biện pháp sau. Chúng **không biến Pub/Sub thành hàng đợi bền**, nhưng giúp hệ thống tự sửa khi bỏ lỡ tín hiệu.

### 8.1. Subscriber đọc lại trạng thái hiện tại khi reconnect

Thay vì coi payload là lệnh bắt buộc, publisher phát ID của thực thể đã thay đổi:

```json
{
  "eventId": "evt-00981",
  "eventType": "ORDER_CHANGED",
  "orderId": "o-1001",
  "version": 42
}
```

Subscriber nhận notification rồi truy vấn database/API nguồn để lấy trạng thái hiện tại. Khi reconnect, subscriber chủ động chạy một **đợt đồng bộ trạng thái**, không kỳ vọng Redis trả lại event cũ.

```text
Subscribe online  --------> Nhận notification -> đọc state mới
       |
       +-- disconnected
       |
       +-- reconnect ---------> Đọc lại state/snapshot từ nguồn
                                |
                                +-- Tiếp tục nhận notification mới
```

Cách này thích hợp cho cache hoặc projection **có thể tái tạo**. Tuy nhiên, nếu nguồn quá lớn, không thể scan toàn bộ sau mỗi reconnect. Cần checkpoint, dữ liệu có version/update timestamp, index thay đổi hoặc nguồn log bền để đồng bộ theo phần đã thay đổi.

### 8.2. Đồng bộ định kỳ để sửa những lần miss đã bị bỏ lỡ

Dùng một lịch reconcile độc lập với Pub/Sub:

```text
Khi có notification:
  -> refresh nhanh bản ghi liên quan

Mỗi vài phút:
  -> đối chiếu state với nguồn sự thật
  -> sửa bản ghi thiếu/cũ
```

Khi notification bị mất, reconcile đưa hệ thống về trạng thái đúng theo giới hạn thời gian đã cam kết. Cách này không khôi phục **từng event** đã mất; nó chỉ phục hồi **trạng thái cuối** hoặc trạng thái có thể suy ra từ nguồn.

### 8.3. Dùng version để phát hiện bản cũ

Ví dụ source lưu `order.version = 42`, payload notification cũng mang `version = 42`. Subscriber đang giữ phiên bản 38 có thể nhận thấy cần tải lại state. Version giúp ngăn cập nhật chậm ghi đè state mới hơn.

Nhưng **chỉ nhìn version khi nhận notification mới chưa đủ**: nếu mất toàn bộ thông báo và không có reconcile/poll, subscriber sẽ không biết có phiên bản mới. Version phải đi cùng một đường kiểm tra chủ động hoặc log bền.

### 8.4. Bật giám sát reconnect và khoảng offline

Ghi nhận thời điểm mất kết nối, thời điểm subscription khôi phục và số lần listener lỗi. Nếu khoảng offline vượt ngưỡng, chạy reconcile hoặc cảnh báo.

Theo dõi disconnect giúp **phát hiện rủi ro mất dữ liệu**, nhưng không tự tạo ra message để đọc lại.

## 9. Mẫu kết hợp: lưu sự kiện trước, dùng Pub/Sub để đánh thức

Khi cần ưu tiên thời gian phản ứng nhưng không muốn phụ thuộc vào message tạm thời, có thể thiết kế hai đường:

1. **Đường bền:** ghi sự kiện vào Redis Streams hoặc một kho sự kiện/hàng đợi có lưu trữ.
2. **Đường nhanh:** phát Pub/Sub chỉ để báo “có bản ghi mới”.
3. Subscriber nhận thông báo thì đọc **nguồn bền** từ checkpoint. Nếu bỏ lỡ Pub/Sub, một vòng poll/reconnect vẫn đọc bù được.

```text
Business service
       |
       v
Ghi event vào durable log / stream
       |
       +----------------------------+
       |                            |
       v                            v
PUBLISH "new event"            Stream giữ event
       |                            |
       v                            |
Subscriber đang online              |
       |                            |
       v                            |
Đọc stream từ checkpoint <----------+
       |
       v
Xử lý và ghi nhận vị trí/ACK
```

Điểm quyết định là **thứ tự ghi**: với một hệ thống dùng log làm nguồn cho consumer, sự kiện phải được lưu bền **trước khi** thông báo “có event” được phát. Nếu chỉ phát notification rồi mới cố lưu sự kiện và ứng dụng crash ở giữa, subscriber có thể được đánh thức nhưng không có dữ liệu bền để xử lý.

Tuy nhiên, việc ghi database nghiệp vụ rồi ghi stream Redis bằng hai thao tác riêng **không tự tạo một transaction chung**. Nếu cần đảm bảo event phát sinh từ transaction database, hãy cân nhắc transactional outbox hoặc cơ chế đồng bộ đáng tin cậy.

## 10. Redis Streams là lựa chọn khi cần đọc bù

**Redis Streams** là cấu trúc dữ liệu khác với Pub/Sub. Mỗi sự kiện được thêm bằng `XADD`, nhận một stream ID và được giữ trong stream cho tới khi bị xóa hoặc trim theo chính sách. Consumer có thể đọc từ vị trí đã biết, hoặc dùng **consumer group** để phối hợp xử lý và ACK.

### 10.1. So sánh Pub/Sub và Streams

| Thuộc tính | Redis Pub/Sub | Redis Streams |
|---|---|---|
| Cách phát | `PUBLISH` | `XADD` |
| Thông điệp được lưu để đọc lại | Không | Có, trong thời gian tồn tại của stream entry |
| Có ID sự kiện | Không theo hạ tầng Pub/Sub | Có stream ID |
| ACK xử lý | Không | Có với consumer group qua `XACK` |
| Theo dõi pending | Không | Có Pending Entries List của consumer group |
| Consumer offline rồi quay lại | Mất message phát trong lúc offline | Có thể đọc lại nếu entry còn và offset/group được quản lý đúng |
| Phân phối cho nhiều nhóm xử lý độc lập | Mỗi subscriber online được phát | Mỗi consumer group có tiến độ riêng |
| Khả năng nhận trùng khi phục hồi | Không có redelivery nội bộ | Có thể có; cần idempotency |
| Giữ dữ liệu mãi không cấu hình | Không | Không: retention/trim, memory và persistence quyết định |

Redis Streams phù hợp hơn với event cần xử lý đủ, nhưng **không tự đảm bảo exactly-once processing**. Consumer có thể thực hiện side effect thành công rồi crash trước `XACK`; khi message được xử lý lại, side effect có thể lặp nếu không có idempotency.

### 10.2. Tạo event vào stream

```bash
redis-cli XADD stream:orders:v1 '*' \
    eventId evt-00981 \
    type ORDER_PAID \
    orderId o-1001 \
    version 42
```

Redis trả một ID dạng `<milliseconds>-<sequence>`, ví dụ `1780000000000-0` (giá trị minh họa). Message vẫn là phần tử stream cho tới khi có thao tác xóa/trim phù hợp.

Khác với `PUBLISH`, người tiêu thụ không cần trực tuyến **đúng thời điểm `XADD`** để đọc event.

### 10.3. Tạo consumer group và đọc event

Trong Redis CLI:

```bash
redis-cli XGROUP CREATE stream:orders:v1 order-workers 0 MKSTREAM
```

Tham số `0` yêu cầu group bắt đầu từ phần đầu của stream hiện tại. Nếu dùng `$` khi tạo group, các event đã có trước khi tạo group không được đưa vào luồng “event mới” của group theo cách tương tự; chọn vị trí khởi đầu phải theo yêu cầu nghiệp vụ.

Worker A đọc sự kiện mới:

```bash
redis-cli XREADGROUP GROUP order-workers worker-a \
    COUNT 10 BLOCK 2000 STREAMS stream:orders:v1 '>'
```

Các thành phần:

- `GROUP order-workers worker-a`: worker-a thuộc consumer group `order-workers`.
- `COUNT 10`: đọc tối đa 10 event trong một lượt.
- `BLOCK 2000`: chờ tối đa khoảng 2 giây khi chưa có event mới.
- `STREAMS ... >`: yêu cầu các event mới chưa phân phối cho consumer trong group theo ngữ nghĩa consumer group.

Xử lý thành công event rồi ACK:

```bash
redis-cli XACK stream:orders:v1 order-workers 1780000000000-0
```

**ACK phải xảy ra sau khi side effect nghiệp vụ đã hoàn tất theo hợp đồng.** Nếu ACK trước rồi ứng dụng crash, stream không còn biết event đó đang chờ xử lý, dù nghiệp vụ chưa được thực hiện.

### 10.4. Consumer crash và Pending Entries List

Khi consumer group giao event cho worker nhưng worker chưa `XACK`, event thuộc **pending** của group. Kiểm tra:

```bash
redis-cli XPENDING stream:orders:v1 order-workers
```

Khi worker chết, worker khác có thể nhận lại các event pending đã idle đủ lâu bằng cơ chế như `XAUTOCLAIM`:

```bash
redis-cli XAUTOCLAIM stream:orders:v1 order-workers worker-b \
    60000 0-0 COUNT 100
```

Ví dụ này yêu cầu message đã idle ít nhất 60.000 ms; consumer `worker-b` nhận lại trách nhiệm xử lý những event phù hợp.

Điểm cần hiểu: nếu worker A đã thực hiện side effect thành công nhưng chết trước ACK, worker B có thể xử lý lại event. Bởi vậy, **sử dụng event ID hoặc business operation ID để xử lý idempotent** là bắt buộc nếu tác dụng lặp không được chấp nhận.

### 10.5. Streams có giữ được sự kiện trong mọi tình huống không?

Không. Cần phân biệt “có cơ chế lưu và replay” với “bền tuyệt đối”:

- `XTRIM` hoặc `XADD MAXLEN` có thể loại bỏ event cũ trước khi consumer kịp đọc.
- Chính sách giữ stream, giới hạn bộ nhớ và hoạt động dọn dữ liệu phải phù hợp thời gian subscriber có thể offline.
- Redis persistence, replication và failover ảnh hưởng độ bền sau sự cố.
- Nếu đọc sai vị trí group, bỏ qua pending hoặc ACK quá sớm, ứng dụng vẫn có thể bỏ sót nghiệp vụ.
- Consumer group giúp chia việc giữa các consumer **trong cùng group**, không phát một bản riêng cho mọi consumer trong group. Nếu cần các hệ thống độc lập cùng xử lý tất cả event, thường tạo group khác nhau.

Vì vậy, khi thay Pub/Sub bằng Streams, phải thiết kế **retention, offset, pending recovery, ACK, idempotency và độ bền Redis** đồng bộ với SLO nghiệp vụ.

## 11. Ví dụ Spring Data Redis Streams: producer và consumer

Spring Data Redis hỗ trợ `StreamOperations` qua `RedisTemplate`/`StringRedisTemplate`. Ví dụ producer lưu sự kiện trước khi bất kỳ consumer nào đọc:

```java
import java.util.Map;

import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class DurableOrderEventPublisher {

    private static final String STREAM = "stream:orders:v1";

    private final StringRedisTemplate redis;

    public DurableOrderEventPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public RecordId appendOrderPaid(
            String eventId,
            String orderId,
            long version) {

        return redis.opsForStream().add(
                STREAM,
                Map.of(
                        "eventId", eventId,
                        "type", "ORDER_PAID",
                        "orderId", orderId,
                        "version", Long.toString(version)));
    }
}
```

`RecordId` cho biết stream ID trả về khi `XADD` thành công. Một producer có thể vẫn cần **business event ID** riêng để xử lý retry/duplicate, vì một event được thêm hai lần sẽ có hai stream ID khác nhau.

Consumer có thể dùng một nhóm đã được tạo trước, đọc và ACK sau khi handler hoàn tất:

```java
import java.time.Duration;
import java.util.List;

import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderStreamConsumer {

    private static final String STREAM = "stream:orders:v1";
    private static final String GROUP = "order-workers";

    private final StringRedisTemplate redis;
    private final DurableOrderHandler handler;

    public OrderStreamConsumer(
            StringRedisTemplate redis,
            DurableOrderHandler handler) {
        this.redis = redis;
        this.handler = handler;
    }

    public void pollOnce(String consumerName) {
        List<MapRecord<String, Object, Object>> records =
                redis.opsForStream().read(
                        Consumer.from(GROUP, consumerName),
                        StreamReadOptions.empty()
                                .count(10)
                                .block(Duration.ofSeconds(2)),
                        StreamOffset.create(
                                STREAM,
                                ReadOffset.lastConsumed()));

        if (records == null || records.isEmpty()) {
            return;
        }

        for (MapRecord<String, Object, Object> record : records) {
            // Handler cần hỗ trợ xử lý idempotent theo eventId.
            handler.handle(record.getValue());

            // Chỉ ACK khi xử lý đã thành công.
            redis.opsForStream().acknowledge(
                    STREAM, GROUP, record.getId());
        }
    }
}
```

Giao diện handler:

```java
import java.util.Map;

public interface DurableOrderHandler {
    void handle(Map<Object, Object> payload);
}
```

Ví dụ này minh họa API synchronous polling. Với Spring Data Redis, có thể dùng `StreamMessageListenerContainer` hoặc các API reactive tương ứng để quản lý vòng đọc thay vì tự dựng loop. Dù chọn API nào, các nguyên tắc không đổi:

1. Group phải được tạo đúng một lần hoặc theo quy trình idempotent, trước khi đọc.
2. Event mới được lấy theo offset của group.
3. Handler hoàn tất side effect trước ACK.
4. Có đường xử lý **pending khi crash**, không chỉ vòng đọc event mới.
5. Xử lý deserialize/validation và lỗi Redis theo chính sách retry.
6. Có cơ chế ngăn side effect lặp khi event bị nhận lại.

Đoạn ví dụ **chưa triển khai pending recovery, retry policy hoặc dead-letter handling**; những phần đó cần bổ sung nếu sử dụng cho workflow production có yêu cầu độ tin cậy cao.

## 12. Pub/Sub + Streams: notification nhanh, xử lý dựa trên log bền

Có hệ thống đã dùng Pub/Sub cho phản ứng nhanh và không muốn bỏ hoàn toàn cơ chế này. Một phương án là:

1. Producer `XADD` event vào stream.
2. Producer `PUBLISH` notification ngắn chứa ID/stream name sau khi append thành công.
3. Subscriber nhận Pub/Sub thì kích hoạt việc đọc stream từ checkpoint.
4. Một vòng poll định kỳ vẫn đọc stream, kể cả không có notification.
5. Sau reconnect, subscriber tiếp tục từ vị trí group/checkpoint.

```text
Producer
   |
   +-- XADD stream:orders:v1 -------------> Event lưu trong stream
   |                                             |
   +-- PUBLISH orders.notify.v1                  |
                   |                             |
                   v                             |
             Subscriber online                   |
                   |                             |
                   +-- Wake up ------------------+
                                                 |
                                                 v
                                           XREADGROUP / XACK
                                                 |
                                           Process nghiệp vụ

Subscriber offline:
   Không nhận notification
   -> khi online/poll trở lại vẫn đọc event còn giữ trong stream
```

**Notification chỉ là tối ưu độ trễ; stream mới là nguồn để phục hồi.** Nếu Pub/Sub bị mất, vòng poll phải vẫn tiếp tục. Nếu vòng poll chỉ chạy khi nhận notification, kiến trúc vẫn có thể mắc kẹt sau một notification bị bỏ lỡ.

### Tránh tạo khoảng mất giữa “subscribe” và “catch-up”

Đường thiết kế an toàn cần xử lý race ở thời điểm bắt đầu. Nếu dùng notification và một cursor riêng, tránh quy trình:

```text
1. Đọc hết backlog.
2. Sau đó mới SUBSCRIBE.
```

Một event xuất hiện giữa bước 1 và 2 có thể không được xử lý cho tới lần poll sau. Để không dựa vào subscription đúng thời điểm, hãy có vòng đọc stream theo offset luôn hoạt động hoặc đồng bộ backlog theo checkpoint sau khi subscription có hiệu lực.

Khi dùng consumer group, bản thân Redis Streams đã hỗ trợ block-read event mới; trong nhiều trường hợp không cần thêm kênh Pub/Sub chỉ để đánh thức consumer. Chỉ bổ sung nếu đã đo thấy lợi ích rõ ràng và chấp nhận chi phí vận hành hai cơ chế.

## 13. Transactional outbox khi sự kiện gắn với thay đổi database

Giả sử ứng dụng xử lý thanh toán:

```text
1. UPDATE orders SET status = 'PAID'
2. PUBLISH "ORDER_PAID" qua Redis Pub/Sub
```

Có một khoảng hở nguy hiểm: database có thể commit thành công nhưng process crash trước khi `PUBLISH`. Sự kiện không được phát dù subscriber luôn online. Đây là lỗi **dual-write**, không chỉ lỗi subscriber ngắt kết nối.

Nếu đưa event vào stream bằng một lệnh Redis riêng sau database commit, khoảng dual-write vẫn còn:

```text
DB COMMIT thành công
     |
     +-- process crash trước XADD
     |
     v
Stream không có event, không có gì để replay
```

Một cách giải quyết phổ biến là **transactional outbox**:

```text
Trong cùng transaction database:
   UPDATE orders ...
   INSERT INTO outbox_events(..., status='NEW')
              |
              v
         DB COMMIT
              |
              v
     Outbox dispatcher đọc event
              |
              v
       XADD Redis Stream
              |
              v
     Ghi nhận outbox đã phát
              |
              v
   Consumer xử lý + idempotency + ACK
```

Event được lưu cùng transaction nguồn nên sau khi commit còn dấu vết để dispatcher retry. Tuy nhiên, dispatcher có thể gửi được event rồi crash trước khi đánh dấu đã gửi, nên **có thể phát trùng**. Consumer cần idempotency theo business event ID.

Nếu không muốn dùng Redis Streams, outbox có thể phát tới broker khác có lưu trữ bền, tùy yêu cầu throughput, retention, routing, ordering và hệ thống vận hành của tổ chức.

## 14. Không nên coi Redis Pub/Sub là hệ thống phân phối chính xác một lần

Ba khái niệm thường bị nhầm:

- **At-most-once:** không có retry tự động; mất một lần nhận có nghĩa message biến mất đối với subscriber đó.
- **At-least-once:** có retry/redelivery để tăng cơ hội xử lý; consumer phải chịu được nhận trùng.
- **Exactly-once effect:** tác dụng nghiệp vụ xảy ra đúng một lần; đây là yêu cầu end-to-end, thường cần idempotency hoặc transaction/ràng buộc dữ liệu phù hợp.

Redis Pub/Sub hướng tới **at-most-once delivery**, không phải at-least-once. Redis Streams với consumer group, pending recovery và ACK có thể hỗ trợ cách tổ chức **at-least-once processing**, nhưng không tự giải quyết exactly-once side effect trong database.

### Ví dụ gửi email sau thanh toán

Nếu consumer nhận lại `ORDER_PAID` sau crash:

```text
Lần 1: gửi email thành công
        crash trước khi ACK

Lần 2: nhận lại message pending
        gửi email lần nữa nếu không kiểm tra eventId
```

Cần lưu idempotency key hoặc trạng thái gửi theo hợp đồng ở hệ thống có khả năng kiểm soát trùng. Đây là lý do **chuyển từ Pub/Sub sang Streams giải quyết khả năng phục hồi message, nhưng vẫn cần xử lý tính đúng đắn của nghiệp vụ**.

## 15. Khi nào cần message broker khác?

Redis Streams là lựa chọn khả thi cho nhiều workload, nhưng không phải tất cả yêu cầu đều nên được giải quyết bằng Redis.

Có thể cân nhắc RabbitMQ, Kafka hoặc dịch vụ message queue được quản lý nếu hệ thống cần:

- Retention dài hoặc replay sự kiện theo thời gian.
- Nhiều consumer group độc lập với throughput lớn.
- Routing, dead-letter queue, delayed retry và quản lý consumer phức tạp.
- Cam kết vận hành riêng cho durability, replication và audit.
- Dòng sự kiện lớn, phân vùng, ordering và scale-out theo partition.
- Tách rõ trách nhiệm giữa Redis cache và nền tảng truyền sự kiện nghiệp vụ.

Việc lựa chọn cần so sánh SLA, latency, throughput, chi phí hạ tầng và kỹ năng vận hành. Không có broker nào tự đảm bảo exactly-once business effect chỉ vì hỗ trợ ACK; idempotency và transaction nghiệp vụ vẫn quan trọng.

## 16. Theo dõi sức khỏe Pub/Sub trong Spring

Vì Pub/Sub không có queue depth hay pending offset, việc giám sát phải dựa nhiều vào **trạng thái kết nối, thời gian và hiệu ứng ở phía consumer**.

| Metric/tín hiệu | Câu hỏi cần trả lời |
|---|---|
| Subscriber connected/ready | Listener đang đăng ký đúng kênh không? |
| Reconnect count | Kết nối Redis bị ngắt thường xuyên không? |
| Offline duration | Khoảng thời gian nào có nguy cơ bỏ lỡ event? |
| Publisher count | Ứng dụng đã cố phát bao nhiêu notification? |
| Subscriber receive count | Ứng dụng đã nhận bao nhiêu notification? |
| Handler success/error count | Có thông điệp đã nhận nhưng xử lý lỗi không? |
| Last received timestamp | Subscriber có im lặng bất thường không? |
| Business event gap/version lag | Trạng thái bên nhận có chậm/thiếu so với nguồn không? |
| Reconciliation repairs | Có bao nhiêu bản ghi phải đồng bộ lại? |
| Redis disconnected clients / output buffers | Subscriber chậm hoặc mạng yếu có bị cắt không? |

**Không so sánh trực tiếp `PUBLISH return count` với `handler success count` rồi cho rằng chênh lệch chính xác bằng số event mất.** Số subscriber của một kênh có thể biến động, mỗi message có thể phát tới nhiều client và điều kiện đo ở Redis Cluster còn phức tạp.

### Redis CLI hỗ trợ điều tra

```bash
redis-cli PUBSUB CHANNELS
redis-cli PUBSUB NUMSUB orders.events.v1
redis-cli INFO clients
redis-cli INFO stats
```

Những lệnh này phản ánh trạng thái tại thời điểm khảo sát và phạm vi Redis node/topology đang truy vấn. Chúng **không cung cấp danh sách message đã mất khi offline**.

Với subscription của ứng dụng, cần thêm metric và log theo instance, thời gian bắt đầu subscription, số lần reconnect và trạng thái reconcile.

Lưu ý: Redis Pub/Sub có cơ chế buffer cho client đang kết nối, nhưng đó **không phải hàng đợi bền**. Subscriber quá chậm có thể khiến Redis đóng kết nối do giới hạn output buffer; event chưa được xử lý vẫn không có ACK để replay.

## 17. Đánh giá bằng thử nghiệm ngắt kết nối có kiểm soát

Một tính năng được mô tả là “reconnect tự động” cần được kiểm chứng bằng tình huống thực, vì yêu cầu nghiệp vụ quan trọng không chỉ là khôi phục kết nối mà còn là **khôi phục dữ liệu bị bỏ lỡ**.

### Kịch bản A — Dừng subscriber khi publisher vẫn phát

1. Khởi chạy publisher và subscriber trên môi trường test.
2. Phát một message có `eventId = e1`, xác nhận subscriber nhận.
3. Dừng subscriber hoặc ngắt mạng Redis phía subscriber.
4. Phát `e2`, `e3`, `e4`.
5. Khởi động subscriber lại.
6. Phát `e5`.
7. Quan sát subscriber chỉ có thể nhận các message trong thời gian subscription thực sự hoạt động, còn `e2–e4` không được Pub/Sub replay.

### Kịch bản B — Callback lỗi sau khi nhận

1. Subscriber đang online.
2. Gửi message có payload hợp lệ nhưng cấu hình handler giả lập lỗi sau khi bắt đầu xử lý.
3. Ghi nhận `MessageListener` hoặc handler phát exception.
4. Xác nhận Redis Pub/Sub không tự redeliver event theo cơ chế ACK.

Điều cần đánh giá là hiệu ứng nghiệp vụ, không chỉ log callback.

### Kịch bản C — Deploy hai phiên bản

1. Instance A chạy bản cũ, instance B chạy bản mới.
2. Phát message trong lúc A đóng subscription, B chưa đăng ký hoàn tất.
3. Kiểm tra có khoảng trống nhận sự kiện không.
4. Nếu hệ thống dùng reconciliation/Streams, xác nhận B vẫn phục hồi đúng dữ liệu sau khi sẵn sàng.

### Kịch bản D — Subscriber chậm hơn publisher

1. Publisher phát thông điệp nhanh hơn khả năng xử lý của subscriber.
2. Quan sát thread pool/queue của listener, client buffer và lỗi connection.
3. Kiểm tra thời điểm mất kết nối và liệu có event không được xử lý hay không.
4. Xác nhận thiết kế fallback đọc nguồn không phụ thuộc vào receipt từng message.

### Kịch bản E — Phục hồi bằng Streams

1. Tạo stream và consumer group.
2. `XADD` nhiều event khi consumer offline.
3. Khởi chạy consumer, đọc các event còn giữ trong stream.
4. Crash consumer sau side effect nhưng trước `XACK`.
5. Khôi phục pending cho consumer khác.
6. Xác nhận logic idempotency ngăn side effect lặp.

Kết quả của kịch bản A và E cho thấy khác biệt nền tảng giữa **Pub/Sub chỉ phát trực tiếp** và **Streams có khả năng lưu/replay theo group**.

## 18. Những sai lầm thường gặp

### 18.1. “RedisMessageListenerContainer tự reconnect nên sẽ không mất message”

Container giúp khôi phục subscription, không cung cấp backlog. Những event phát trong khoảng offline vẫn mất với Pub/Sub.

### 18.2. “PUBLISH trả về 1 nghĩa là người nhận đã xử lý xong”

Giá trị trả về không phải ACK nghiệp vụ. Subscriber có thể chưa xử lý, có thể crash hoặc thất bại sau khi nhận.

### 18.3. “Subscriber lỗi thì throw exception để Redis gửi lại”

Pub/Sub không có redelivery dựa trên exception của callback. Muốn retry, phải có cơ chế lưu message và trạng thái xử lý ở nơi khác.

### 18.4. “Có nhiều replica subscriber thì không lo mất”

Nhiều replica có thể giảm xác suất **không có bất kỳ** subscriber nào online, nhưng không đảm bảo một instance nhận đủ mọi event. Nếu mỗi replica duy trì projection/cache cục bộ, instance offline vẫn có dữ liệu cũ sau khi quay lại.

### 18.5. “Gửi lại từ publisher là đủ”

Publisher không biết chính xác subscriber nào xử lý thành công. Nếu retry không có business event ID/idempotency, có thể tạo tác dụng lặp.

### 18.6. “Thay bằng Redis Streams là automatically exactly-once”

Streams có khả năng lưu và đọc lại, nhưng ACK trước/sau side effect vẫn có những trường hợp mất hoặc xử lý lặp nếu thiết kế không đúng.

### 18.7. “Tạo consumer group ở cuối stream là sẽ xử lý đủ mọi event cũ”

Khởi tạo group bằng `$` thường bỏ qua các entry hiện có ở thời điểm tạo group đối với luồng nhận message mới. Phải chọn vị trí bắt đầu theo yêu cầu replay/cutover.

### 18.8. “Đã ACK thì có thể xóa/trim stream tùy ý”

Một consumer group ACK không có nghĩa tất cả group khác đã xử lý. Retention phải tính thời gian lag của mọi nhóm cần dữ liệu.

### 18.9. “Đặt eventId trong Pub/Sub thì sẽ không mất”

Event ID giúp dedup, phát hiện lỗ hổng trong một số tình huống và đối soát, nhưng không tạo bản sao bền để lấy lại event đã mất.

### 18.10. “Keyspace notifications của Redis là event log”

Thông báo keyspace/keyevent của Redis cũng dựa trên Pub/Sub và không được lưu bền cho subscriber offline. Không dùng chúng làm audit log hoặc nguồn duy nhất cho workflow bắt buộc.

## 19. Cây quyết định kiến trúc

```text
Ứng dụng cần nhận sự kiện Redis?
                   |
                   v
Nếu subscriber offline, có được bỏ lỡ thông báo?
                   |
             +-----+-----+
             |           |
            Có          Không
             |           |
             v           v
      Redis Pub/Sub    Cần lưu event bền
      có thể phù hợp       |
             |             v
             |       Redis Streams / broker
             |             |
             |             v
             |       Consumer group/offset,
             |       ACK, pending recovery
             |             |
             |             v
             |       Idempotency và retention
             |             |
             +------+------+ 
                    |
                    v
  Nếu bỏ lỡ notification, có thể đồng bộ state từ nguồn?
                    |
              +-----+-----+
              |           |
             Có          Không
              |           |
              v           v
       Reconcile/poll   Cần đường event bền,
       khi reconnect   không chỉ Pub/Sub
              |
              v
       Đo offline gap,
       handler errors và state lag
```

### Gợi ý lựa chọn theo bài toán

| Bài toán | Phương án nền tảng |
|---|---|
| Gửi thông báo “danh mục vừa đổi” để giao diện làm mới | Pub/Sub + API đọc state, có periodic refresh |
| Invalidate cache giữa nhiều service, TTL có giới hạn | Pub/Sub có thể dùng làm tín hiệu nhanh + TTL/reconcile |
| Đồng bộ projection có thể rebuild | Pub/Sub + reconcile hoặc stream nếu cần catch-up hiệu quả |
| Gửi email bắt buộc sau thanh toán | Durable queue/stream + ACK/retry/idempotency |
| Xử lý đầy đủ mọi sự kiện đơn hàng | Stream/event log + retention và checkpoint |
| Phát message gắn với database transaction | Outbox + dispatcher + durable messaging |
| Cần lịch sử sự kiện để audit | Kho sự kiện bền với retention/audit phù hợp, không dùng Pub/Sub đơn thuần |

## 20. Kết luận

Trong Spring Data Redis, **`RedisMessageListenerContainer` không biến Redis Pub/Sub thành một hệ thống có lưu trữ và phát lại thông điệp**. Nó quản lý việc lắng nghe và khôi phục subscription; khi subscriber offline, các thông điệp được phát trong khoảng đó không được tự gửi bù lúc kết nối lại. Tương tự, `PUBLISH` thành công hay một handler đã nhận thông điệp đều không chứng minh nghiệp vụ đã hoàn tất.

Đối với **thông báo tức thời có thể bỏ lỡ**, Pub/Sub vẫn là công cụ đơn giản và hiệu quả nếu ứng dụng có đường đọc trạng thái hiện tại, đồng bộ bù khi reconnect và giám sát khoảng offline. Đối với **sự kiện không được phép mất**, hãy dùng Redis Streams hoặc một hệ thống message broker bền, thiết kế ACK, pending recovery, retention và idempotency; khi sự kiện gắn với thay đổi database, xem xét transactional outbox để đóng khoảng hở dual-write.

**Quy tắc quyết định:** Hãy thử tắt toàn bộ subscriber trong lúc publisher vẫn gửi sự kiện. Nếu hệ thống không thể khôi phục đúng nghiệp vụ sau khi subscriber quay lại, thì **Pub/Sub không đủ làm kênh duy nhất** cho luồng đó.

