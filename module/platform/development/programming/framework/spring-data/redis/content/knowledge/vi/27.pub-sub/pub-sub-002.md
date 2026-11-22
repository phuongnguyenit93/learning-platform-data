# Phân biệt channel thường với pattern subscription trong Spring Data Redis Pub/Sub

## 1. Bài toán: nhận đúng một channel hay nhận cả một nhóm channel?

Redis Pub/Sub cho phép một ứng dụng **publish** thông điệp lên một tên channel và các client đang **subscribe** nhận thông điệp tương ứng. Với Spring Data Redis, ứng dụng có thể đăng ký hai kiểu subscription:

- **Channel thường** (*exact channel subscription*): lắng nghe **một tên channel chính xác**, sử dụng lệnh Redis `SUBSCRIBE` hoặc `ChannelTopic` trong Spring Data Redis.
- **Pattern subscription**: lắng nghe **mọi channel có tên khớp một mẫu glob**, sử dụng lệnh Redis `PSUBSCRIBE` hoặc `PatternTopic`.

Ví dụ hệ thống phát các sự kiện:

```text
orders.created
orders.cancelled
orders.paid
payments.completed
```

Nếu một thành phần chỉ xử lý sự kiện tạo đơn hàng, nó có thể subscribe chính xác `orders.created`.

Nếu một thành phần ghi nhật ký mọi sự kiện đơn hàng, nó có thể subscribe pattern `orders.*`. Khi một event được publish lên `orders.created`, cả hai dạng subscription có thể nhận thông điệp.

Điểm cốt lõi: **publisher vẫn publish lên tên channel cụ thể**. Pattern nằm ở phía **subscriber** và là quy tắc chọn các channel cần nghe; nó không phải một loại channel riêng mà publisher phải ghi vào.

Sau bài học, bạn có thể:

1. Phân biệt `SUBSCRIBE`, `PSUBSCRIBE`, `UNSUBSCRIBE` và `PUNSUBSCRIBE`.
2. Hiểu quy tắc glob của Redis và tránh nhầm với regex.
3. Phân biệt thông điệp kiểu `message` với `pmessage`.
4. Dùng `ChannelTopic` và `PatternTopic` với `RedisMessageListenerContainer`.
5. Nhận biết việc một publication có thể xuất hiện nhiều lần khi subscriptions chồng lấn.
6. Chọn phạm vi subscription theo yêu cầu nghiệp vụ, bảo mật và hiệu năng.
7. Hiểu giới hạn về độ bền, thứ tự, thời điểm đăng ký và vận hành nhiều instance.
8. Chẩn đoán lỗi khi subscriber không nhận hoặc nhận nhiều thông điệp hơn dự kiến.

## 2. Mô hình hoạt động của Redis Pub/Sub

Một publisher gửi thông điệp:

```redis
PUBLISH orders.created '{"orderId":"o-101","status":"CREATED"}'
```

Redis xác định các subscription phù hợp rồi chuyển thông điệp đến những client đang đăng ký:

```text
                          Redis Pub/Sub

Publisher
    |
    | PUBLISH orders.created payload
    v
Tên channel "orders.created"
    |
    +--> Client A: SUBSCRIBE orders.created  ------> nhận
    |
    +--> Client B: PSUBSCRIBE orders.*       ------> nhận
    |
    +--> Client C: PSUBSCRIBE orders.paid    ------> không nhận
    |
    +--> Client D: SUBSCRIBE payments.done   ------> không nhận
```

**Channel không phải Redis List, Stream hay Hash chứa lịch sử sự kiện.** Trong cơ chế Pub/Sub thông thường, tên channel là tuyến phát thông điệp trong thời gian thực. Redis không tạo hàng đợi bền vững chỉ vì một client gọi `SUBSCRIBE` hay `PSUBSCRIBE`.

Nếu publisher gửi khi chưa có subscriber phù hợp, thông điệp không được lưu lại để subscriber đăng ký sau đó đọc bù.

### 2.1. Hai góc nhìn cần tách biệt

| Khái niệm | Thuộc bên nào? | Ví dụ | Ý nghĩa |
|---|---|---|---|
| Channel | Publisher chỉ định khi gửi; subscriber có thể đăng ký chính xác | `orders.created` | Tên tuyến mà thông điệp được publish lên |
| Exact subscription | Subscriber | `SUBSCRIBE orders.created` | Chỉ quan tâm tên channel đúng bằng chuỗi chỉ định |
| Pattern subscription | Subscriber | `PSUBSCRIBE orders.*` | Quan tâm tất cả tên channel khớp mẫu glob |
| Message payload | Publisher gửi, subscriber nhận | `{"orderId":"o-101"}` | Dữ liệu sự kiện |
| Matching pattern | Redis cho biết với thông điệp pattern | `orders.*` | Mẫu nào đã khớp với channel gốc |

Publisher không cần biết có bao nhiêu subscriber, họ đăng ký theo tên hay theo pattern. Những quyết định đó thuộc phía nhận.

## 3. Channel thường: SUBSCRIBE

Cú pháp Redis:

```redis
SUBSCRIBE channel [channel ...]
```

Ví dụ:

```redis
SUBSCRIBE orders.created
```

Client này nhận thông điệp được publish lên đúng channel:

```redis
PUBLISH orders.created "new-order"
```

Nhưng không nhận thông điệp publish lên các tên khác:

```redis
PUBLISH orders.cancelled "cancelled-order"
PUBLISH orders.created.v2 "new-order-v2"
PUBLISH payments.completed "payment-done"
```

Redis so khớp tên channel chính xác. Dấu chấm (`.`) trong `orders.created` chỉ là một ký tự của tên; Redis không tự hiểu đây là cấu trúc cha/con của namespace.

### 3.1. Có thể subscribe nhiều channel cụ thể

Một subscriber có thể nghe nhiều tên:

```redis
SUBSCRIBE orders.created orders.cancelled orders.paid
```

Đây vẫn là **exact subscription** đối với từng channel. Các tên được liệt kê không trở thành một pattern.

Khi danh sách kênh biết trước và tương đối ổn định, subscribe tường minh giúp phạm vi dữ liệu nhận được rõ ràng. Nó cũng dễ kiểm soát khi mỗi loại sự kiện có handler hoặc chính sách xử lý riêng.

### 3.2. Thông điệp dạng message

Sau khi `SUBSCRIBE orders.created`, một publication phù hợp có dạng phản hồi Pub/Sub logic:

```text
1) "message"
2) "orders.created"
3) "{\"orderId\":\"o-101\"}"
```

Ba thông tin quan trọng:

1. Loại thông điệp: `message`.
2. Tên channel thực tế: `orders.created`.
3. Payload được publish: chuỗi hoặc byte dữ liệu.

Một thông điệp kiểu exact không mang thêm trường pattern vì không được gửi qua một pattern subscription.

## 4. Pattern subscription: PSUBSCRIBE

Cú pháp:

```redis
PSUBSCRIBE pattern [pattern ...]
```

Ví dụ:

```redis
PSUBSCRIBE orders.*
```

Subscriber nhận publication trên các channel khớp mẫu:

```text
orders.created
orders.cancelled
orders.paid
orders.created.v2
orders.
```

Mẫu `orders.*` nghĩa là tên bắt đầu bằng chuỗi ký tự `orders.` rồi đến **không hoặc nhiều ký tự bất kỳ**.

Mẫu này không tự giới hạn ở “đúng một cấp” của một namespace. Nếu ứng dụng dùng nhiều dấu chấm trong tên channel, `orders.*` vẫn có thể khớp nhiều cấp.

### 4.1. Pattern của Redis dùng glob, không phải regex

Những ký hiệu phổ biến:

| Pattern | Quy tắc | Ví dụ khớp | Ví dụ không khớp |
|---|---|---|---|
| `orders.*` | Bắt đầu bằng `orders.` rồi đến 0 hoặc nhiều ký tự | `orders.created`, `orders.a.b` | `payments.created` |
| `orders.?` | Bắt đầu bằng `orders.` rồi thêm đúng một ký tự theo phép so khớp glob | `orders.a` | `orders.created` |
| `orders.[ab]` | Ký tự cuối thuộc nhóm `a` hoặc `b` | `orders.a`, `orders.b` | `orders.c` |
| `orders.[0-9]` | Một ký tự trong khoảng đã cho | `orders.7` | `orders.ready` |
| `*` | Mọi tên channel | `orders.created`, `payments.paid` | Không có tên channel bình thường nào bị loại vì tên |
| `audit.*` | Mọi channel có tiền tố `audit.` | `audit.login` | `orders.created` |

Redis glob không phải biểu thức chính quy đầy đủ:

- Không có cú pháp regex như `^orders\\..+$` theo nghĩa regex.
- Dấu `.` là ký tự thông thường; nó không có nghĩa “bất kỳ ký tự” như trong nhiều regex engine.
- `*` là wildcard trong glob; viết `orders.*` không có nghĩa “dấu chấm rồi lặp lại chính dấu chấm”.
- So khớp tên channel cần xem như một giao kèo đặt tên chính xác, có phân biệt chữ hoa/chữ thường.
- Khi cần khớp ký tự wildcard theo nghĩa đen, phải dùng cơ chế escape glob tương ứng và kiểm tra tên thực tế; tránh tự xây pattern phức tạp không cần thiết.

Ví dụ:

```text
Pattern: orders.*

orders.created      -> khớp
orders.CANCELLED    -> khớp
orders.created.v2   -> khớp
orders.             -> khớp
order.created       -> không khớp
Orders.created      -> không khớp
```

### 4.2. Pattern tự nhận tên channel mới trong tương lai

Giả sử hôm nay hệ thống mới dùng:

```text
orders.created
orders.cancelled
```

Một subscriber có `PSUBSCRIBE orders.*` không cần đăng ký lại khi ngày mai publisher bắt đầu phát:

```text
orders.refunded
orders.shipped
```

Miễn tên mới khớp pattern và subscriber vẫn đang kết nối, nó sẽ nhận những publication mới ấy.

**Pattern subscription không tạo các channel và không quét lịch sử.** Nó chỉ mở rộng phạm vi tên channel được chọn khi thông điệp được publish trong tương lai.

### 4.3. Thông điệp dạng pmessage

Với:

```redis
PSUBSCRIBE orders.*
```

khi publisher gửi:

```redis
PUBLISH orders.created '{"orderId":"o-101"}'
```

subscriber pattern nhận phản hồi logic:

```text
1) "pmessage"
2) "orders.*"
3) "orders.created"
4) "{\"orderId\":\"o-101\"}"
```

Bốn thành phần:

1. Loại thông điệp: `pmessage`.
2. Pattern đã khớp: `orders.*`.
3. Tên channel **thực tế**: `orders.created`.
4. Payload.

Nếu handler cần biết đây là sự kiện `created` hay `cancelled`, nó phải dựa vào **channel thực tế**, không được dùng pattern `orders.*` như tên sự kiện.

## 5. So sánh trực tiếp hai loại subscription

| Tiêu chí | Channel thường | Pattern subscription |
|---|---|---|
| Redis command | `SUBSCRIBE` | `PSUBSCRIBE` |
| Hủy đăng ký | `UNSUBSCRIBE` | `PUNSUBSCRIBE` |
| Spring Data Redis Topic | `ChannelTopic` | `PatternTopic` |
| Phạm vi khớp | Tên channel chính xác | Tên channel phù hợp mẫu glob |
| Loại thông điệp Pub/Sub | `message` | `pmessage` |
| Metadata về pattern | Không có pattern | Có tên pattern đã khớp |
| Nhận thêm channel mới? | Cần subscribe tên mới | Tự nhận nếu tên mới khớp |
| Chi phí chọn lọc | Không phải duyệt mẫu glob cho đăng ký này | Redis phải xét các pattern được đăng ký |
| Khả năng nhận ngoài ý định | Thấp nếu danh sách channel chính xác | Cao hơn nếu pattern quá rộng |
| Trường hợp phù hợp | Handler nghiệp vụ chuyên trách một vài sự kiện | Logging, quan sát, dispatcher theo namespace |
| Lưu trữ/đảm bảo delivery | Pub/Sub tạm thời | Cũng là Pub/Sub tạm thời; không có độ bền cao hơn |

Một khác biệt quan trọng về thiết kế: **mẫu rộng tiện cho mở rộng**, nhưng có thể khiến subscriber nhận loại thông điệp chưa được hỗ trợ. Khi đặt pattern, cần cùng lúc quy định cách xử lý channel mới và payload mới.

## 6. Thực hành với ba terminal

Mở Redis cục bộ hoặc kết nối tới một Redis thử nghiệm. Có thể chạy Redis bằng Docker:

```bash
docker run --rm --name redis-pubsub-demo -p 6379:6379 redis:7-alpine
```

Ở terminal A:

```bash
redis-cli
```

Sau đó:

```redis
SUBSCRIBE orders.created
```

Ở terminal B:

```bash
redis-cli
```

Sau đó:

```redis
PSUBSCRIBE orders.*
```

Ở terminal C:

```bash
redis-cli
```

Publish:

```redis
PUBLISH orders.created "event-1"
PUBLISH orders.cancelled "event-2"
PUBLISH orders.created.v2 "event-3"
PUBLISH payments.completed "event-4"
```

Kỳ vọng:

| Publication | Terminal A (`SUBSCRIBE orders.created`) | Terminal B (`PSUBSCRIBE orders.*`) |
|---|---|---|
| `orders.created` / `event-1` | Nhận `message` | Nhận `pmessage` |
| `orders.cancelled` / `event-2` | Không nhận | Nhận |
| `orders.created.v2` / `event-3` | Không nhận | Nhận |
| `payments.completed` / `event-4` | Không nhận | Không nhận |

Cần **đăng ký subscriber trước khi publish**. Nếu chạy lệnh publish trước khi terminal A hoặc B subscribe xong, thông điệp đã đi qua sẽ không được phát lại.

Khi muốn hủy:

```redis
UNSUBSCRIBE orders.created
PUNSUBSCRIBE orders.*
```

Hai lệnh hủy tác động lên **hai loại subscription khác nhau**. Hủy exact subscription không đồng nghĩa hủy pattern subscription có cùng phạm vi tên, và ngược lại.

## 7. Vì sao một thông điệp có thể được nhận hai lần?

Giả sử **một client** đồng thời đăng ký:

```redis
SUBSCRIBE orders.created
PSUBSCRIBE orders.*
```

Khi có:

```redis
PUBLISH orders.created "event-1"
```

Redis có thể gửi **hai thông báo Pub/Sub riêng biệt** đến client đó:

```text
message:
    channel = orders.created
    payload = event-1

pmessage:
    pattern = orders.*
    channel = orders.created
    payload = event-1
```

Đây không phải Redis tự retry một message bị lỗi. Nó là hệ quả của **hai subscription cùng khớp một publication**.

Tương tự, một client đăng ký nhiều pattern chồng lấn:

```redis
PSUBSCRIBE orders.* *.created
```

Một publication trên `orders.created` có thể khớp cả hai pattern và được gửi dưới dạng các `pmessage` tương ứng.

### 7.1. Hệ quả với nghiệp vụ

Nếu subscriber làm một side effect:

```text
Nhận order created
    -> gửi email
    -> ghi điểm thưởng
    -> cập nhật hệ thống khác
```

việc hai subscription chồng lấn có thể làm xử lý nghiệp vụ hai lần nếu code không phân biệt hoặc loại trừ.

Các hướng tránh:

- Với handler chuyên trách, chỉ đăng ký **một exact channel**.
- Với handler tổng hợp, dùng một pattern có chủ đích và tránh nhiều pattern trùng phạm vi.
- Tách handler logging/metrics khỏi handler tạo side effect.
- Truyền `eventId` trong payload và áp dụng idempotency cho side effect quan trọng.
- Nếu ứng dụng chủ động đăng ký cả exact và pattern, quy định rõ một trong hai đường chỉ dùng để quan sát hoặc thống kê.

**Idempotency là yêu cầu nghiệp vụ riêng.** Một Pub/Sub message được phát một lần vẫn có thể kích hoạt nhiều callback vì có nhiều subscription hoặc nhiều instance ứng dụng cùng nghe.

### 7.2. Cần phân biệt bản sao theo số subscriber

Nếu ba instance ứng dụng cùng subscribe `orders.created`, cả ba có thể nhận cùng một publication. Redis Pub/Sub là **broadcast tới các subscriber phù hợp**, không tự chia công việc “một event chỉ cho một worker” như queue có consumer group.

Kết hợp nhiều instance và nhiều pattern chồng lấn có thể tạo nhiều lượt xử lý hơn mong đợi. Nếu mục tiêu là một nhóm worker chia nhau công việc và cần ghi nhận xử lý, hãy xem xét Redis Streams với consumer group hoặc hệ thống queue phù hợp.

## 8. Spring Data Redis: ChannelTopic và PatternTopic

Spring Data Redis ánh xạ hai kiểu subscription vào abstraction `Topic`.

Các class thường dùng:

```java
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.PatternTopic;
import org.springframework.data.redis.listener.Topic;
```

Tạo exact topic:

```java
Topic exact = new ChannelTopic("orders.created");
```

Tạo pattern topic:

```java
Topic wildcard = new PatternTopic("orders.*");
```

Một `ChannelTopic` diễn đạt mong muốn subscribe **chính xác tên channel**. Một `PatternTopic` diễn đạt mong muốn subscribe **mẫu glob**.

Hai đối tượng đều mô tả việc **nhận**, không phải nơi chứa payload hoặc một loại data structure Redis được tạo sẵn. Publisher vẫn gọi lệnh publish với một channel string như bình thường.

### 8.1. RedisMessageListenerContainer

Thay vì tự mở connection rồi gọi `SUBSCRIBE` và quản lý vòng đời chặn thread, Spring Data Redis cung cấp `RedisMessageListenerContainer`.

Container quản lý việc đăng ký, kết nối và phân phối thông điệp đến `MessageListener`. Trong ứng dụng Spring thông thường, container được đăng ký như một bean; nó bắt đầu nhận subscription theo lifecycle của Spring.

Ví dụ cấu hình hai listener:

```java
package com.example.pubsub;

import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.PatternTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class PubSubConfiguration {

    @Bean
    RedisMessageListenerContainer redisMessageListenerContainer(
            RedisConnectionFactory connectionFactory) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);

        MessageListener exactListener = (message, matchedPattern) ->
            trace("EXACT", message, matchedPattern);

        MessageListener patternListener = (message, matchedPattern) ->
            trace("PATTERN", message, matchedPattern);

        container.addMessageListener(
            exactListener,
            new ChannelTopic("orders.created")
        );

        container.addMessageListener(
            patternListener,
            new PatternTopic("orders.*")
        );

        return container;
    }

    private static void trace(
            String source,
            Message message,
            byte[] matchedPattern) {

        String channel = new String(
            message.getChannel(),
            StandardCharsets.UTF_8
        );

        String payload = new String(
            message.getBody(),
            StandardCharsets.UTF_8
        );

        String pattern = matchedPattern == null
            ? "(direct)"
            : new String(matchedPattern, StandardCharsets.UTF_8);

        System.out.printf(
            "%s | pattern=%s | channel=%s | payload=%s%n",
            source, pattern, channel, payload
        );
    }
}
```

Ví dụ này giả định tên channel và payload được gửi dưới dạng văn bản UTF-8. Với payload nhị phân, JSON serializer riêng hoặc JDK serializer, không thể tùy tiện dùng `new String(bytes, UTF_8)` để dựng lại object nghiệp vụ.

Nhờ đăng ký hai listener, khi publish lên `orders.created`:

```text
EXACT   | pattern=(direct) | channel=orders.created | payload=...
PATTERN | pattern=orders.* | channel=orders.created | payload=...
```

Khi publish lên `orders.cancelled`, chỉ pattern listener trong cấu hình này được gọi.

### 8.2. MessageListener nhận được những gì?

Giao diện:

```java
public interface MessageListener {
    void onMessage(Message message, byte[] pattern);
}
```

Trong callback:

- `message.getChannel()` chứa **tên channel thực tế** dạng byte.
- `message.getBody()` chứa payload dạng byte.
- `pattern` chứa mẫu đã khớp đối với pattern subscription; với direct subscription thông thường là `null`.

Mã xử lý chung có thể phân biệt:

```java
@Override
public void onMessage(Message message, byte[] pattern) {
    boolean fromPatternSubscription = pattern != null;

    String actualChannel = new String(
        message.getChannel(),
        StandardCharsets.UTF_8
    );

    if (fromPatternSubscription) {
        String matchedPattern = new String(
            pattern,
            StandardCharsets.UTF_8
        );
        // Xử lý theo pattern và tên channel thực tế.
    } else {
        // Xử lý direct subscription.
    }
}
```

Đối với handler đăng ký bằng `PatternTopic("orders.*")`, **đừng dùng `pattern` để suy ra tên sự kiện đã xảy ra**. Một pattern có thể khớp nhiều channel; chính `message.getChannel()` cho biết channel nào đã được publish.

### 8.3. Không nhầm tên method hoặc tên class

| Redis CLI | Spring Data Redis |
|---|---|
| `SUBSCRIBE orders.created` | `new ChannelTopic("orders.created")` |
| `PSUBSCRIBE orders.*` | `new PatternTopic("orders.*")` |
| `PUBLISH orders.created payload` | `StringRedisTemplate.convertAndSend("orders.created", payload)` |
| Hủy exact subscription | Gỡ `ChannelTopic` listener hoặc quản lý vòng đời subscription |
| Hủy pattern subscription | Gỡ `PatternTopic` listener hoặc quản lý vòng đời subscription |

Các phương thức quản lý listener trong container cần được gọi đúng theo API và lifecycle của Spring. Đăng ký/hủy theo yêu cầu động nên có cơ chế tránh trùng registration và tránh gỡ nhầm listener dùng chung.

## 9. Publisher Spring Data Redis vẫn publish vào channel cụ thể

Một publisher:

```java
package com.example.pubsub;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final StringRedisTemplate redis;

    public OrderEventPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long publishCreated(String json) {
        Long subscribers = redis.convertAndSend(
            "orders.created",
            json
        );
        return subscribers == null ? 0L : subscribers;
    }

    public long publishCancelled(String json) {
        Long subscribers = redis.convertAndSend(
            "orders.cancelled",
            json
        );
        return subscribers == null ? 0L : subscribers;
    }
}
```

Cấu hình Redis tương ứng trong một ứng dụng Spring Boot:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Ví dụ payload:

```json
{
  "eventId": "evt-1001",
  "orderId": "o-101",
  "occurredAt": "2026-11-13T02:00:00Z"
}
```

`StringRedisTemplate` serialize String bằng cách phù hợp cho văn bản. Nếu producer dùng `RedisTemplate<String, Object>` và serializer khác, receiver phải biết format payload tương ứng để đọc dữ liệu.

**Publisher không gửi vào `orders.*`.** Nếu gọi `PUBLISH orders.* payload`, Redis sẽ coi `orders.*` là **tên channel thật**. Nó không tự fan-out tới `orders.created` và `orders.cancelled`. Pattern có ý nghĩa ở phía subscription.

### 9.1. Giá trị trả về từ PUBLISH không phải ACK nghiệp vụ

Giá trị trả về của `PUBLISH`/`convertAndSend` có liên quan đến số subscriber nhận publication ở mức Redis theo ngữ nghĩa lệnh và cấu hình triển khai. Nó **không chứng minh**:

- Handler đã xử lý payload thành công.
- Dữ liệu đã được ghi vào database của subscriber.
- Một email đã được gửi.
- Một tiến trình không bị lỗi sau khi nhận.
- Message đã được lưu để đọc lại.

Trong Redis Cluster, phạm vi đếm mà lệnh `PUBLISH` trả về còn có giới hạn theo node. Vì vậy không dùng số trả về như biên nhận nghiệp vụ end-to-end hay bằng chứng bảo đảm giao hàng.

Nếu ứng dụng cần ACK, retry, dead-letter hoặc lịch sử sự kiện, Redis Pub/Sub thông thường chưa đủ.

## 10. Định tuyến sự kiện bên trong pattern listener

Khi một listener subscribe `orders.*`, nó nhận nhiều loại sự kiện. Vì vậy cần phân loại rõ theo **actual channel**.

Ví dụ:

```java
package com.example.pubsub;

import java.nio.charset.StandardCharsets;

import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.stereotype.Component;

@Component
public class OrderPatternListener implements MessageListener {

    @Override
    public void onMessage(Message message, byte[] pattern) {
        String channel = new String(
            message.getChannel(),
            StandardCharsets.UTF_8
        );

        String body = new String(
            message.getBody(),
            StandardCharsets.UTF_8
        );

        switch (channel) {
            case "orders.created":
                handleCreated(body);
                break;
            case "orders.cancelled":
                handleCancelled(body);
                break;
            case "orders.paid":
                handlePaid(body);
                break;
            default:
                handleUnknownChannel(channel, body);
        }
    }

    private void handleCreated(String json) {
        // Parse JSON và áp dụng nghiệp vụ tương ứng.
    }

    private void handleCancelled(String json) {
        // Parse JSON và áp dụng nghiệp vụ tương ứng.
    }

    private void handlePaid(String json) {
        // Parse JSON và áp dụng nghiệp vụ tương ứng.
    }

    private void handleUnknownChannel(String channel, String json) {
        // Log/metric theo chính sách, tránh side effect ngoài dự kiến.
    }
}
```

Nếu dùng bean này thay cho lambda trong phần cấu hình:

```java
@Bean
RedisMessageListenerContainer orderListenerContainer(
        RedisConnectionFactory factory,
        OrderPatternListener listener) {

    RedisMessageListenerContainer container =
        new RedisMessageListenerContainer();

    container.setConnectionFactory(factory);
    container.addMessageListener(
        listener,
        new PatternTopic("orders.*")
    );

    return container;
}
```

Đây là **cấu hình thay thế**, không đặt đồng thời với container demo ở phần 8 nếu không muốn tạo thêm subscription. Trong dự án thật, chọn một cách tổ chức bean rõ ràng để tránh đăng ký listener trùng.

### 10.1. Tránh xử lý không biết loại dữ liệu

Mỗi channel có thể dùng schema khác nhau. Ví dụ `orders.created` chứa `newOrder`, `orders.cancelled` chứa `reason`. Pattern listener cần phân loại channel **trước khi** deserialize theo DTO chuyên biệt.

Nếu parse mọi payload thành một class duy nhất vì chúng cùng khớp `orders.*`, sự kiện mới có thể tạo lỗi hoặc bị xử lý sai.

Một hướng mở rộng là chuẩn hóa envelope:

```json
{
  "eventId": "evt-1001",
  "type": "OrderCreated",
  "schemaVersion": 1,
  "payload": {
    "orderId": "o-101"
  }
}
```

Khi đó tên channel và trường `type` có thể cùng góp phần kiểm tra hợp đồng, nhưng phải quy định rõ trường nào là nguồn định tuyến chính và cách xử lý khi hai thông tin mâu thuẫn.

### 10.2. Xử lý sự kiện không biết trước

Vì pattern có thể khớp channel mới trong tương lai, handler tổng hợp cần chính sách:

- Bỏ qua channel chưa hỗ trợ và ghi metric.
- Gửi sự kiện tới handler mở rộng nếu có.
- Cảnh báo khi event/schema ngoài hợp đồng.
- Không thực hiện side effect mặc định chỉ vì tiền tố khớp pattern.

Pattern giúp subscriber ít phải đăng ký lại, nhưng **không tự bảo đảm khả năng tương thích payload**.

## 11. Lưu ý về serialization của channel và payload

`MessageListener` nhận byte. Tên channel và payload có thể được serialize khác nhau:

```text
Publisher Java:
    convertAndSend(channel, object)
       |
       +-- channel serializer -> bytes tên channel
       +-- value serializer   -> bytes payload

Redis Pub/Sub:
    channel bytes + payload bytes

Listener:
    message.getChannel() -> byte[]
    message.getBody()    -> byte[]
```

Nếu publisher dùng `StringRedisTemplate`, channel và payload String có dạng dễ đọc. Nhưng nếu dùng `RedisTemplate` với serializer nhị phân cho đối tượng, body không nhất thiết là JSON hay UTF-8.

### 11.1. Lỗi phổ biến: subscriber đang nghe String channel nhưng publisher gửi key theo format khác

Ví dụ subscriber:

```java
new ChannelTopic("orders.created")
```

Publisher lại dùng template có cách encode channel khác với String mong đợi. Dù Java nhìn thấy cùng chuỗi `"orders.created"`, **byte channel thực tế** có thể không trùng, làm listener không nhận gì.

Hãy thống nhất serializer của tên channel, thường dùng `StringRedisSerializer` hoặc `StringRedisTemplate`. Dữ liệu body có thể áp dụng JSON codec riêng nhưng phải chia sẻ format giữa producer và consumer.

### 11.2. JSON không tự thành DTO trong MessageListener

Code:

```java
String json = new String(
    message.getBody(),
    StandardCharsets.UTF_8
);
```

chỉ tạo một Java String. Nếu cần DTO, dùng `ObjectMapper` hoặc một codec phù hợp:

```java
OrderCreatedEvent event = objectMapper.readValue(
    message.getBody(),
    OrderCreatedEvent.class
);
```

Ở đây `OrderCreatedEvent` là DTO do ứng dụng định nghĩa, và publisher phải gửi JSON đúng schema. Khi thiết kế listener cần xử lý exception parse ở tầng phù hợp, tránh để một payload lỗi làm gián đoạn liên tục toàn bộ đường nhận sự kiện.

## 12. Chi phí hiệu năng: pattern matching không miễn phí

Với exact subscription, Redis có thể tìm tập subscriber theo tên channel. Với pattern subscription, Redis cần xét các pattern đã được đăng ký để xác định mẫu nào khớp tên channel.

Mô hình chi phí publish thường được diễn tả theo:

```text
PUBLISH complexity: O(N + M)

N = số client subscribe trực tiếp channel nhận message
M = tổng số pattern subscription được đăng ký
```

Công thức diễn tả việc gửi cho subscriber trực tiếp và xét các mẫu. Chi phí thực tế còn chịu ảnh hưởng kích thước payload, số client, kết nối chậm, buffer và lượng traffic.

Ví dụ:

```text
10 channel cụ thể có nhiều subscriber
  -> Redis xử lý theo channel khi có publication.

5.000 pattern được đăng ký
  -> Mỗi lần publish có thể phải xem xét nhiều pattern.
```

Đừng suy rằng wildcard luôn chậm hoặc exact subscription luôn tốt hơn trong mọi trường hợp. Một pattern duy nhất có thể hợp lý hơn việc ứng dụng động duy trì hàng trăm tên channel. Nhưng **một số lượng lớn pattern rất rộng** có thể làm tăng chi phí trên mỗi publication và gửi nhiều message không cần thiết cho subscriber.

### 12.1. Pattern rộng tạo tải xử lý lớn ở phía consumer

Nếu ứng dụng subscribe:

```redis
PSUBSCRIBE *
```

nó có thể nhận gần như mọi publication trong phạm vi Redis Pub/Sub thông thường mà nó có quyền truy cập. Một logger hoặc listener xử lý chậm có thể trở thành điểm nghẽn, tiêu thụ memory buffer và CPU.

Nên chọn pattern hẹp hơn:

```text
orders.*
orders.audit.*
tenant:{t-7}:orders.*
```

Nhưng nhớ: đây chỉ là **quy ước đặt tên** và glob matching. Redis không hiểu tenant, order hay dấu hai chấm theo ngữ nghĩa nghiệp vụ.

### 12.2. Pattern không phải hệ thống routing nhiều thuộc tính

Pattern chủ yếu khớp **tên channel**. Nó không hỗ trợ query tùy ý trên field JSON trong payload:

```json
{
  "tenant": "t-7",
  "priority": 10,
  "region": "south"
}
```

`PSUBSCRIBE orders.*` không thể tự lọc `priority > 5` hoặc `region == "south"` từ JSON. Nếu cần lọc như vậy, phải đưa thông tin vào tên channel, lọc ở application hoặc dùng hệ thống nhắn tin/truy vấn phù hợp.

Cần cân đối: mã hóa quá nhiều thuộc tính vào channel name có thể làm namespace phức tạp và dễ tạo nhiều pattern chồng lấn.

## 13. Quan sát subscriber với các lệnh PUBSUB

Redis cung cấp một số lệnh chẩn đoán:

```redis
PUBSUB CHANNELS
PUBSUB CHANNELS orders.*
PUBSUB NUMSUB orders.created orders.cancelled
PUBSUB NUMPAT
```

Ý nghĩa:

| Lệnh | Dùng để làm gì? | Lưu ý |
|---|---|---|
| `PUBSUB CHANNELS` | Liệt kê các channel đang có subscriber trực tiếp | Không dùng để liệt kê tất cả channel từng được publish |
| `PUBSUB CHANNELS orders.*` | Lọc danh sách channel có direct subscription theo pattern được truyền | Không có nghĩa đang liệt kê chính các pattern subscriptions |
| `PUBSUB NUMSUB orders.created` | Đếm direct subscriber cho tên channel | Không tính toàn bộ pattern subscriber sẽ khớp |
| `PUBSUB NUMPAT` | Đếm pattern subscriptions đang hoạt động theo ngữ nghĩa Redis | Không phải số event hoặc số channel |

Một hiểu nhầm thường gặp là:

```redis
PUBSUB NUMSUB orders.created
```

trả `0` dù có listener `PSUBSCRIBE orders.*`. Điều đó có thể hoàn toàn bình thường vì lệnh này tập trung vào **direct subscription**. Không được suy rằng không ai nhận được publication chỉ dựa trên `NUMSUB = 0`.

Trong Redis Cluster, kết quả quan sát các subscription có thể mang tính cục bộ hoặc có những quy tắc phạm vi theo command và node. Khi điều tra hệ thống phân tán, cần biết node đã truy vấn và loại Pub/Sub đang sử dụng.

### 13.1. PUBLISH response là phép đo hạn chế

```redis
PUBLISH orders.created "hello"
```

lệnh trả số liên quan đến các client nhận publication ở mức broker. Con số này **không phải ACK hoàn thành xử lý**. Một handler có thể nhận rồi lỗi, bị restart hoặc chưa kịp lưu dữ liệu ra nơi khác.

Trong Cluster, phạm vi đếm có thể chỉ phản ánh client kết nối với node nơi publish theo ngữ nghĩa Redis Cluster. Vì thế, không dựa vào con số này để xác nhận tất cả instance ứng dụng đã nhận và xử lý thành công.

## 14. Vòng đời kết nối và listener container

Lệnh `SUBSCRIBE`/`PSUBSCRIBE` chuyển connection vào trạng thái đăng ký nhận thông điệp. Với RESP2, khả năng chạy lệnh khác trên subscribed connection bị giới hạn; với RESP3 có khác biệt, nhưng ứng dụng thông thường vẫn nên để listener container quản lý kết nối Pub/Sub.

Không nên:

1. Lấy một connection bình thường từ pool dùng cho các lệnh dữ liệu.
2. Gọi `SUBSCRIBE` theo cách block vô thời hạn trên thread request.
3. Tiếp tục giả định connection đó có thể được dùng hệt connection bình thường.
4. Quên hủy subscription hoặc không quản lý reconnect.

`RedisMessageListenerContainer` cung cấp cơ chế quản lý vòng đời, đăng ký nhiều listener và phân phối callback phù hợp với Spring. Nó được thiết kế để chia sẻ kết nối subscription và phục vụ listener ở cấp container; khả năng threading cụ thể phụ thuộc executor và cấu hình.

### 14.1. Không để handler chặn quá lâu

Nếu một callback làm việc nặng:

```java
@Override
public void onMessage(Message message, byte[] pattern) {
    // Gọi API ngoài nhiều giây, retry vô hạn hoặc đọc một file rất lớn...
}
```

nó có thể làm chậm xử lý thông điệp, làm nghẽn executor và tăng số payload chờ xử lý. Với tải cao, nên:

- Giữ callback ngắn.
- Decode và validate đủ để định tuyến.
- Chuyển việc nặng sang một executor/queue được quản lý có giới hạn.
- Đặt timeout cho I/O và tránh retry vô hạn trong callback.
- Ghi metric về số message nhận, lỗi xử lý và thời gian handler.

Tuy nhiên, chuyển sang hàng đợi in-memory riêng vẫn không làm Pub/Sub trở nên bền vững. Khi tiến trình chết, những message chưa xử lý trong bộ nhớ cũng có thể mất.

### 14.2. Đăng ký động

Trong một số ứng dụng, các channel cần nghe phụ thuộc cấu hình hoặc trạng thái runtime. Container hỗ trợ quản lý listener theo topic, nên có thể thêm/hủy registration có kiểm soát.

Cần lưu ý:

- Tránh đăng ký cùng listener/topic nhiều lần ngoài ý định.
- Theo dõi channel/pattern nào đang gắn với handler nào.
- Nếu mở rộng pattern, rà soát phạm vi sự kiện có thể nhận.
- Khi hủy exact listener, kiểm tra có pattern listener nào vẫn nhận channel đó không.
- Khi container reconnect, cần bảo đảm lifecycle và trạng thái registration được khôi phục đúng theo cơ chế thư viện.

Trước khi cố tối ưu số lượng connection, hãy ưu tiên tính rõ ràng của phạm vi subscription và khả năng xử lý lỗi.

## 15. Độ tin cậy: direct và pattern đều không có lưu trữ bền vững

Redis Pub/Sub thông thường có ngữ nghĩa giao thông điệp **at-most-once** cho từng delivery theo cơ chế Pub/Sub: khi thông điệp được gửi tới subscriber, broker không giữ một bản ghi bền vững để subscriber ACK và yêu cầu phát lại khi xử lý lỗi.

Những tình huống dễ mất message:

```text
Publisher phát trước khi subscriber đăng ký xong.
Subscriber mất kết nối tại thời điểm publish.
Ứng dụng dừng trong lúc handler chưa xử lý.
Client bị quá tải hoặc connection bị đóng.
Redis/Network gặp sự cố.
```

Cả `SUBSCRIBE` và `PSUBSCRIBE` đều chịu các giới hạn đó. Pattern subscription **không phải một hàng đợi với wildcard**, và cũng không biến thông điệp thành bản ghi có thể replay.

### 15.1. Đừng nhầm Pub/Sub với Redis Streams

Nếu cần:

- Đọc lại message khi consumer khởi động sau.
- Theo dõi ID/offset.
- ACK sau khi xử lý.
- Chia công việc cho consumer group.
- Xử lý pending, retry hoặc khôi phục sau disconnect.

thì Redis Streams (`XADD`, `XREAD`, `XREADGROUP`, `XACK`) hoặc hệ thống message broker khác thường phù hợp hơn. Redis Streams có mô hình lưu trữ, giới hạn retention và tiêu thụ dữ liệu khác Pub/Sub.

Một hệ thống vẫn có thể dùng Pub/Sub cho tín hiệu realtime (invalidate cache, báo thay đổi trạng thái) và Streams/queue cho công việc cần độ tin cậy cao.

### 15.2. Khả năng nhận lặp không mâu thuẫn at-most-once

Redis không retry Pub/Sub theo kiểu queue có ACK, nhưng ứng dụng có thể **tự tạo các lượt nhận trùng về mặt nghiệp vụ**:

- Một client cùng đăng ký exact và pattern chồng lấn.
- Hai pattern cùng khớp một publication.
- Nhiều instance cùng đăng ký một channel.
- Publisher gửi hai event có payload giống nhau.

Vì vậy, với side effect quan trọng cần nhận diện `eventId`, chống xử lý trùng và xem xét liệu Pub/Sub có đáp ứng yêu cầu mất thông điệp hay không.

## 16. Redis Cluster: không nhầm classic Pub/Sub với sharded Pub/Sub

Redis Cluster có nhiều shard. Đối với **Pub/Sub thông thường** (`PUBLISH`, `SUBSCRIBE`, `PSUBSCRIBE`), Redis Cluster có cơ chế truyền publication để subscriber có thể nghe theo hệ thống Pub/Sub toàn cluster, dù đang kết nối ở các node khác nhau. Điều này có thể làm tăng giao tiếp giữa các node khi lượng sự kiện lớn.

Redis 7 giới thiệu **sharded Pub/Sub** với nhóm lệnh khác:

```text
SPUBLISH
SSUBSCRIBE
SUNSUBSCRIBE
```

Sharded Pub/Sub gắn channel với hash slot/shard để hạn chế phạm vi propagation. Đây là một mô hình khác với classic Pub/Sub.

| Khía cạnh | Classic Pub/Sub | Sharded Pub/Sub |
|---|---|---|
| Publish | `PUBLISH` | `SPUBLISH` |
| Exact subscribe | `SUBSCRIBE` | `SSUBSCRIBE` |
| Pattern subscribe | `PSUBSCRIBE` | Không có lệnh tương đương `SPSUBSCRIBE` trong nhóm cơ bản |
| Phạm vi truyền trong Cluster | Classic Pub/Sub propagation trên cluster | Chủ yếu theo shard của channel |
| Định tuyến qua Spring Data Redis | `ChannelTopic`/`PatternTopic` theo API Pub/Sub thông thường | Cần xác minh API và driver hỗ trợ sharded Pub/Sub cụ thể |
| Độ bền | Không lưu backlog | Cũng không phải Redis Stream có ACK/replay |

Một `PatternTopic("orders.*")` của `RedisMessageListenerContainer` phục vụ cơ chế Pub/Sub pattern thông thường. Không nên mặc định cho rằng nó tự subscribe tất cả sharded Pub/Sub channels tương ứng.

Nếu yêu cầu hệ thống là “subscribe wildcard xuyên nhiều shard của sharded Pub/Sub”, phải thiết kế riêng cách đăng ký các channel hoặc chọn hệ thống tương thích với mục đích đó; không thể suy ra có `SPSUBSCRIBE` chỉ vì có `PSUBSCRIBE` của classic mode.

### 16.1. Chi phí trong Cluster

Với classic Pub/Sub, nhiều publication và pattern rộng có thể làm tăng tải truyền thông điệp và CPU của cluster. Với sharded Pub/Sub, lựa chọn hash slot và shard ảnh hưởng nơi phân phối dữ liệu; đổi lại khả năng wildcard pattern không giống classic Pub/Sub.

Vì vậy, câu hỏi chọn `ChannelTopic` hay `PatternTopic` thường thuộc **classic Pub/Sub API**, trong khi câu hỏi chọn classic hay sharded Pub/Sub là một quyết định kiến trúc riêng.

## 17. Bảo mật và phân tách namespace

Một pattern như:

```redis
PSUBSCRIBE *
```

có thể nhận nhiều loại thông điệp ngoài phạm vi nghiệp vụ mong muốn, tùy ACL và cấu hình Redis. Đừng dùng một pattern rất rộng trong dịch vụ xử lý dữ liệu nhạy cảm nếu không có nhu cầu rõ ràng.

Ví dụ thiết kế tên channel theo tenant:

```text
tenant.t-7.orders.created
tenant.t-7.orders.cancelled
tenant.t-8.orders.created
```

Một listener của tenant `t-7` có thể chọn:

```redis
PSUBSCRIBE tenant.t-7.orders.*
```

Nhưng **pattern trong tên channel không tự tạo ranh giới bảo mật**. Nếu client có quyền Pub/Sub rộng, nó vẫn có thể tự yêu cầu subscription khác. Cần cấu hình Redis ACL channel permissions và phân tách kết nối, quyền truy cập hoặc hạ tầng theo mức bảo mật của ứng dụng.

Không để client bên ngoài tự gửi một pattern tùy ý đến ứng dụng rồi mở subscription rộng mà không kiểm soát authorization và mức sử dụng tài nguyên.

### 17.1. Thiết kế tên channel có chủ đích

Một quy ước đơn giản:

```text
<domain>.<entity>.<event>
orders.order.created
orders.order.cancelled
billing.invoice.paid
```

Khi đó:

```text
orders.order.created  -> một sự kiện chính xác
orders.order.*        -> tất cả sự kiện của order
orders.*              -> mọi tên bắt đầu bằng "orders."
```

Tên càng ổn định, càng dễ kiểm soát mức độ rộng của các pattern. Nếu thay đổi quy ước tên, cần hỗ trợ migration cho publisher và subscriber; đổi channel name có thể làm subscriber cũ không nhận được message.

## 18. Khi nào nên dùng exact channel và khi nào dùng pattern?

### 18.1. Ưu tiên ChannelTopic khi

- Handler chỉ nhận một sự kiện nghiệp vụ cụ thể.
- Payload có một schema chuyên biệt.
- Side effect chỉ được phép xảy ra cho một event type.
- Cần hạn chế nguy cơ nhận message ngoài ý định.
- Danh sách channel nhỏ và đã biết.
- Có yêu cầu kiểm soát permission chặt theo channel.

Ví dụ:

```java
container.addMessageListener(
    paymentSuccessListener,
    new ChannelTopic("payments.completed")
);
```

### 18.2. Ưu tiên PatternTopic khi

- Có nhiều channel cùng namespace cần quan sát.
- Tên channel có thể phát sinh động theo ID/tenant/nguồn, nhưng vẫn theo quy ước rõ ràng.
- Listener tổng hợp cần tiếp nhận event mới nếu tên khớp.
- Cần logging/metrics/audit nhẹ cho một nhóm sự kiện.
- Đã có cơ chế dispatch theo actual channel và xử lý unknown event.

Ví dụ:

```java
container.addMessageListener(
    orderAuditListener,
    new PatternTopic("orders.*")
);
```

### 18.3. Bảng lựa chọn

| Nhu cầu | Phương án | Vì sao |
|---|---|---|
| Chỉ xử lý `orders.created` | `ChannelTopic("orders.created")` | Rõ tên event, ít nhận ngoài phạm vi |
| Ghi log tất cả `orders.*` | `PatternTopic("orders.*")` | Một registration nhận nhiều channel |
| Chỉ nhận `orders.created` và `orders.cancelled` | Hai `ChannelTopic` | Tường minh, tránh event mới vô tình vào handler |
| Tiếp nhận channel mới `orders.shipped` mà không sửa cấu hình subscription | `PatternTopic("orders.*")` | Mẫu tự khớp tên channel mới |
| Cần xử lý chính xác một lần bởi một worker | Pub/Sub chưa đủ | Cần queue/Streams và idempotency |
| Cần replay sau mất kết nối | Pub/Sub chưa đủ | Dùng lưu trữ message có retention |
| Muốn đăng ký pattern cho sharded Pub/Sub | Cần thiết kế khác | `PSUBSCRIBE` thuộc classic Pub/Sub |
| Cần lọc theo trường JSON | Handler/filter hoặc hệ thống khác | Pattern chỉ khớp tên channel |

Lựa chọn thường hiệu quả nhất là dùng **exact cho business handler có side effect**, còn **pattern cho observer hoặc dispatcher có khả năng xử lý schema/unknown channel**.

## 19. Lỗi thường gặp và hướng điều tra

### 19.1. “PUBLISH thành công nhưng Spring listener không nhận”

Kiểm tra lần lượt:

1. Container đã khởi động và subscribe xong trước khi publish chưa?
2. Tên channel Java thực sự có khớp exact/pattern không?
3. `ChannelTopic` có bị dùng thay cho `PatternTopic` không?
4. Publisher và subscriber có kết nối cùng Redis/Cluster đúng mục tiêu không?
5. Channel serializer có tạo byte giống nhau không?
6. Redis ACL có cho phép subscribe/publish channel đó không?
7. Connection Pub/Sub có bị ngắt và container có reconnect không?
8. Callback có đang lỗi parse payload hoặc chặn ở executor không?

Đừng vội kết luận Redis không gửi khi chưa kiểm tra lifecycle và format channel.

### 19.2. “PSUBSCRIBE orders.* không chỉ nhận orders.created”

Đây là hành vi đúng: wildcard `*` có thể khớp mọi phần mở rộng sau `orders.`. Nếu cần đúng một sự kiện, dùng `SUBSCRIBE orders.created`. Nếu cần một nhóm hữu hạn, dùng nhiều `ChannelTopic` tường minh.

### 19.3. “Có một publish nhưng handler chạy hai lần”

Tìm exact subscription và pattern subscription chồng lấn, các pattern trùng nhau, listener bean được đăng ký hai lần hoặc nhiều application instance đang subscribe. Kiểm tra `message`/`pmessage`, matched pattern và actual channel trước khi cho rằng Redis retry.

### 19.4. “PUBSUB NUMSUB trả 0 nhưng vẫn có người nhận”

Lệnh `PUBSUB NUMSUB` chủ yếu thống kê direct subscriber của channel. Pattern listener có thể nhận message mà không được tính như một direct subscriber của tên ấy.

### 19.5. “Subscriber nhận cả những channel chưa được ứng dụng xử lý”

Pattern mở rộng phạm vi subscription. Cần dispatch theo `message.getChannel()`, xử lý unknown event rõ ràng và không mặc định áp dụng một DTO cho mọi channel.

### 19.6. “Một message đến nhưng decode thành ký tự lạ”

Publisher có thể dùng JDK/JSON/binary serializer trong khi listener giả định UTF-8 text. Phân biệt channel bytes và payload bytes, thống nhất format hoặc dùng serializer tương thích.

### 19.7. “Mất message sau restart”

Pub/Sub không lưu backlog và không replay. Cần Redis Streams hoặc message broker có retention và ACK nếu nghiệp vụ đòi hỏi.

### 19.8. “Nhiều instance cùng xử lý một tác vụ”

Pub/Sub broadcast tới các subscriber phù hợp, không tự phân chia task. Dùng consumer group/queue khi yêu cầu một message do một thành viên nhóm xử lý.

### 19.9. “Pattern listener trở nên quá tải khi hệ thống mở thêm event type”

Pattern đang khớp thêm nhiều channel mới, handler decode/dispatch phải làm nhiều việc hơn. Đo message rate, lỗi handler, độ trễ xử lý; xem lại độ rộng pattern và executor.

### 19.10. “Channel có cùng prefix nhưng pattern không khớp”

Kiểm tra dấu chấm, ký tự phân cách, chữ hoa/chữ thường, tên thực sự được publish, wildcard và byte serializer. `orders.*` không khớp `order.created`; `Orders.created` cũng không giống `orders.created`.

## 20. Bài thực hành có hướng dẫn

### Bài 1 — Quan sát message và pmessage

Tạo ba terminal như ở phần 6. Trong terminal A `SUBSCRIBE orders.created`, terminal B `PSUBSCRIBE orders.*`, terminal C publish bốn sự kiện. Ghi nhận loại reply, channel thật và matched pattern.

Trả lời: Vì sao terminal B có thêm trường `orders.*` trong message, còn terminal A thì không?

### Bài 2 — Phân biệt glob với regex

Dự đoán pattern `orders.*` nhận các channel sau không:

```text
orders.
orders.created
orders.created.v2
order.created
orders.paid
Orders.paid
```

Sau đó thử từ Redis CLI để kiểm tra. Giải thích vì sao glob `*` không tương đương với một cấp namespace.

### Bài 3 — Dùng ChannelTopic và PatternTopic

Dùng `RedisMessageListenerContainer`:

```java
container.addMessageListener(
    createdListener,
    new ChannelTopic("orders.created")
);

container.addMessageListener(
    auditListener,
    new PatternTopic("orders.*")
);
```

Publish `orders.created`, `orders.cancelled`, `payments.completed`. Quan sát listener nào được gọi. Trong audit listener, in ra `message.getChannel()` và `pattern`.

### Bài 4 — Đăng ký chồng lấn

Cho cùng một client subscribe exact `orders.created` và pattern `orders.*`, hoặc hai pattern `orders.*` và `*.created`. Publish một event `orders.created`. Ghi nhận số phản hồi Pub/Sub và giải thích vì sao một publication có thể sinh nhiều callback logic.

Nếu listener tạo side effect, đề xuất cách không xử lý trùng.

### Bài 5 — Kênh mới

Subscriber đang chạy với:

```redis
PSUBSCRIBE orders.*
```

Bắt đầu publish thêm:

```redis
PUBLISH orders.shipped "shipped"
```

Quan sát nó có nhận ngay hay cần subscribe lại. Giải thích vì sao behavior này không đồng nghĩa có message replay.

### Bài 6 — Chẩn đoán bằng PUBSUB

Chạy:

```redis
PUBSUB CHANNELS
PUBSUB NUMSUB orders.created
PUBSUB NUMPAT
```

Thử khi chỉ có exact subscriber, chỉ có pattern subscriber, rồi cả hai. Phân biệt số direct subscribers với số pattern subscriptions. Không dùng các con số này như số event đã xử lý thành công.

### Bài 7 — Serialization khác nhau

Dùng `StringRedisTemplate` publish JSON text và một `MessageListener` giải mã UTF-8. Sau đó thử publisher dùng một serializer nhị phân khác trong môi trường thử nghiệm. Giải thích vì sao callback không thể coi mọi payload là String JSON.

### Bài 8 — Chọn Pub/Sub hay Streams

Với ba tình huống:

1. Cập nhật trạng thái realtime cho dashboard đang online.
2. Gửi email bắt buộc dù service xử lý bị restart.
3. Log nhẹ tất cả sự kiện `orders.*` khi hệ thống đang chạy.

Đề xuất `ChannelTopic`, `PatternTopic` hoặc một hệ thống message có retention/ACK. Giải thích sự khác nhau giữa **phạm vi kênh nhận** và **đảm bảo giao thông điệp**.

## 21. Ghi nhớ

- **`SUBSCRIBE`/`ChannelTopic` nhận một tên channel chính xác**. Có thể subscribe nhiều channel nhưng mỗi tên vẫn được so khớp riêng.
- **`PSUBSCRIBE`/`PatternTopic` nhận mọi tên channel khớp glob** như `orders.*`, kể cả các channel được dùng lần đầu sau khi subscriber đã đăng ký.
- Publisher luôn dùng **tên channel thực tế** với `PUBLISH`; publish vào `orders.*` không tự phát tới mọi `orders.*`.
- Direct subscription nhận dạng `message`; pattern subscription nhận dạng `pmessage` và mang thêm **matched pattern** bên cạnh actual channel.
- **Một publication có thể sinh nhiều thông báo** khi direct/pattern hoặc nhiều pattern chồng lấn. Nhiều instance cùng subscribe cũng đều có thể nhận.
- Trong `MessageListener.onMessage`, `message.getChannel()` là channel thực tế, `message.getBody()` là payload dạng byte, còn tham số `pattern` cho biết pattern khớp hoặc `null` với direct subscription.
- Pattern là **glob, không phải regex hay bộ lọc JSON**. Mẫu rộng làm tăng phạm vi nhận và chi phí xét pattern.
- Redis Pub/Sub thông thường **không lưu lịch sử, không replay và không có ACK xử lý**. Exact và pattern có cùng giới hạn độ tin cậy.
- `PUBSUB NUMSUB` không đếm đầy đủ những người nghe bằng pattern; `PUBLISH` response không phải xác nhận nghiệp vụ.
- **Classic Pub/Sub với `PSUBSCRIBE` khác sharded Pub/Sub** trên Redis Cluster; không có wildcard sharded tương đương trực tiếp trong nhóm lệnh cơ bản.
- Chọn `ChannelTopic` cho handler nghiệp vụ cụ thể; chọn `PatternTopic` cho quan sát hoặc dispatcher theo namespace có xử lý event chưa biết.

### Tài liệu tham khảo chính thức

- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/)
- [Redis — SUBSCRIBE](https://redis.io/docs/latest/commands/subscribe/)
- [Redis — PSUBSCRIBE](https://redis.io/docs/latest/commands/psubscribe/)
- [Redis — PUBLISH](https://redis.io/docs/latest/commands/publish/)
- [Redis — PUBSUB](https://redis.io/docs/latest/commands/pubsub/)
- [Redis — PUBSUB NUMSUB](https://redis.io/docs/latest/commands/pubsub-numsub/)
- [Redis — PUBSUB NUMPAT](https://redis.io/docs/latest/commands/pubsub-numpat/)
- [Redis — Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Spring Data Redis — Pub/Sub Messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html)
- [Spring Data Redis — RedisMessageListenerContainer](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html#redis:pubsub:messaging)
