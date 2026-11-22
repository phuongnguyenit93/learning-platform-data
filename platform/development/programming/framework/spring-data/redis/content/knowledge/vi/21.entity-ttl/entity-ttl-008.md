# Ứng dụng dừng hoạt động trong thời gian khóa hết hạn

## 1. Tình huống: khóa hết hạn khi không có Spring Boot listener

Trong Spring Data Redis, một thực thể có thể được lưu với **TTL (time to live)**. Khi hạn đến, Redis coi khóa đã hết hiệu lực và sẽ loại bỏ nó. Spring Data Redis Repository còn có thể lắng nghe thông báo hết hạn để phát `RedisKeyExpiredEvent` cho ứng dụng.

Vấn đề nảy sinh khi ứng dụng Spring Boot **dừng hoạt động đúng vào khoảng Redis xóa khóa**.

~~~text
09:00                  09:05                  09:15                   09:25
  |                      |                      |                       |
  | save session         | Spring Boot stop     | TTL đã hết hạn        | Spring Boot restart
  | TTL = 15 phút        |                      | Redis xóa khóa       |
  |                      |                      | và publish expired   |
  +----------------------+----------------------+-----------------------+
                         Không có subscriber của ứng dụng

Sau restart:
- Khóa đã hết hạn không tự xuất hiện trở lại.
- Listener không nhận được event expired cũ.
- Mọi tác vụ chỉ kích hoạt bằng event có nguy cơ bị bỏ sót.
~~~

Điểm cần nắm trước tiên là **TTL của Redis và callback của Spring là hai cơ chế độc lập**. Nếu Redis vẫn hoạt động, TTL không ngừng đếm vì JVM đã tắt. Ngược lại, Redis Pub/Sub không chờ JVM hoạt động trở lại để phát lại thông báo.

Ví dụ: một session hết hạn khi ứng dụng đang tắt. Khi khởi động lại, `findById(sessionId)` không tìm thấy session, nhưng một `@EventListener` từng định ghi lịch sử logout sẽ không được gọi bù chỉ vì ứng dụng vừa chạy lại.

> **Nguyên tắc:** TTL quyết định khi nào khóa hết hiệu lực; expired event chỉ là thông báo về việc Redis xóa khóa. Không dùng event làm nguồn duy nhất cho công việc bắt buộc phải hoàn thành.

## 2. Ba mốc thời gian cần phân biệt

Một khóa có TTL có thể trải qua:

1. **`t_deadline`:** thời điểm TTL kết thúc về mặt logic.
2. **`t_delete`:** thời điểm Redis phát hiện và thực sự loại bỏ khóa.
3. **`t_receive`:** thời điểm listener đang kết nối nhận được thông báo.

~~~text
SET key EX 30
   |
   v
t0 ----------------> t_deadline -----> t_delete -----> t_receive
                     Hết hiệu lực     Redis xóa       Spring xử lý
                                      và publish
~~~

Redis xử lý hết hạn theo hai cách:

| Cơ chế | Khi nào chạy? | Ý nghĩa |
| --- | --- | --- |
| Hết hạn thụ động | Có lệnh truy cập khóa đã quá hạn | Khóa được xử lý như không tồn tại; có thể bị xóa tại lúc truy cập |
| Hết hạn chủ động | Redis định kỳ kiểm tra một tập khóa có expiration | Dọn cả khóa không được ai truy cập |

Vì Redis không đặt một timer callback riêng chính xác cho từng khóa, `t_delete` có thể trễ hơn `t_deadline`. Notification `expired` xuất hiện khi khóa bị xóa, không nhất thiết ngay khi TTL chạm 0.

Nếu ứng dụng restart **trước** khi Redis thực sự xóa một khóa đã quá hạn, listener mới có thể bắt được sự kiện phát sau đó. Đây chỉ là tình huống phụ thuộc timing, **không phải khả năng replay**. Thiết kế phục hồi không được dựa vào cơ hội này.

### Trường hợp Redis cũng dừng hoạt động

Khi Redis server tắt, hành vi phục hồi còn phụ thuộc persistence và thời điểm hệ thống. Redis lưu expiration theo thời điểm tuyệt đối; khóa có thể đã quá hạn khi dữ liệu được tải lại. Dù vậy, **không có bảo đảm rằng ứng dụng sẽ nhận được một thông báo expired cho từng khóa quá hạn trong giai đoạn ngừng dịch vụ**.

Do đó, kể cả khi ứng dụng và Redis cùng khởi động lại, nguồn khôi phục công việc phải là một trạng thái/deadline đã được lưu bền vững từ trước.

## 3. Redis keyspace notification hoạt động thế nào?

Redis hỗ trợ thông báo thay đổi khóa qua **Pub/Sub**. Ví dụ với database 0:

~~~bash
redis-cli CONFIG SET notify-keyspace-events Ex
redis-cli PSUBSCRIBE '__keyevent@0__:expired'
~~~

Ý nghĩa của `Ex`:

- `E`: bật nhóm **keyevent**, trong đó tên sự kiện nằm ở channel.
- `x`: bật thông báo **expired**.

Khi Redis xóa khóa `login-session:42` do TTL, message có thể là:

~~~text
channel = __keyevent@0__:expired
message = login-session:42
~~~

Nếu dùng nhóm keyspace, cần `Kx` và channel có dạng `__keyspace@0__:login-session:42`, còn payload mang tên sự kiện.

**Redis Pub/Sub không lưu message để phát lại cho subscriber bị ngắt kết nối.** Listener Spring Boot tắt lúc sự kiện được publish sẽ mất thông báo đó. Kết nối lại, khởi động pod mới hoặc tạo lại `RedisMessageListenerContainer` chỉ cho phép nhận các thông báo trong tương lai.

Điều này cũng xảy ra khi:

- JVM crash, hết bộ nhớ hoặc container bị terminate.
- Đang rolling deployment và chưa có listener thay thế sẵn sàng.
- Kết nối Redis mất trong một khoảng thời gian.
- Redis failover và client đang reconnect.
- Listener khởi tạo muộn sau khi application context đã bắt đầu.
- Ứng dụng chỉ subscribe một node của Redis Cluster trong khi khóa nằm ở node khác.

Với nhiều instance, các instance còn subscribe có thể nhận cùng tín hiệu, nhưng việc một instance nhận được **không tự phục hồi** callback cho instance đã offline.

### Không nhầm `expire` và `expired`

| Hành động | Event liên quan | Diễn giải |
| --- | --- | --- |
| Đặt `EXPIRE key 600` | `expire` nếu bật nhóm tương ứng | Báo vừa đặt hạn, chưa phải khóa hết hạn |
| Redis xóa key do TTL | `expired` | Báo khóa bị Redis xóa vì hết hạn |
| `DEL key` | `del` | Xóa chủ động |
| `EXPIRE key 0` hoặc hạn trong quá khứ | `del` | Khóa bị xóa ngay |
| Redis evict vì giới hạn bộ nhớ | `evicted` | Khác với TTL hết hạn |

Một listener chỉ xử lý `expired` không biết mọi nguyên nhân khiến một thực thể biến mất.

## 4. Khai báo TTL trên entity bằng Spring Data Redis

Ví dụ entity phiên đăng nhập:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("login-session")
public class LoginSession {

    @Id
    private String id;

    private String userId;

    @TimeToLive
    private Long ttlSeconds;

    public LoginSession() { }

    public LoginSession(String id, String userId, Long ttlSeconds) {
        this.id = id;
        this.userId = userId;
        this.ttlSeconds = ttlSeconds;
    }

    public String getId() { return id; }
    public String getUserId() { return userId; }
    public Long getTtlSeconds() { return ttlSeconds; }

    public void setId(String id) { this.id = id; }
    public void setUserId(String userId) { this.userId = userId; }
    public void setTtlSeconds(Long ttlSeconds) {
        this.ttlSeconds = ttlSeconds;
    }
}
~~~

Repository:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface LoginSessionRepository
        extends CrudRepository<LoginSession, String> {
}
~~~

Lưu entity với TTL 15 phút:

~~~java
LoginSession session = new LoginSession("s-42", "u-7", 900L);
repository.save(session);
~~~

`@TimeToLive` trên thuộc tính cho phép Repository đặt TTL từ giá trị đó; trong ví dụ là 900 giây. Với TTL cố định cho mọi entity, có thể dùng `@RedisHash(value = "login-session", timeToLive = 900)`. Khi dùng property `@TimeToLive`, Spring Data Redis cũng có thể đọc TTL hiện tại; giá trị `-1` có nghĩa khóa không có expiration.

Redis quản lý TTL sau khi lưu khóa. **Repository không phải duy trì một timer Java cho từng entity**, nên khóa vẫn hết hạn khi ứng dụng ngừng chạy.

Khi ứng dụng trở lại:

~~~java
boolean exists = repository.findById("s-42").isPresent();
~~~

Nếu khóa đã hết hiệu lực, kết quả thường là `false`. Không cần listener nhận `RedisKeyExpiredEvent` trước thì lần đọc mới coi session là hết hạn.

## 5. Bật expiration listener của Repository

Spring Data Redis Repository có thể nghe keyspace notification và phát một event trong `ApplicationContext`.

Cấu hình listener ngay từ lúc ứng dụng khởi động:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisKeyValueAdapter;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
    enableKeyspaceEvents =
        RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP
)
public class RedisRepositoryConfig {
}
~~~

Nhận event:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.context.event.EventListener;
import org.springframework.data.redis.core.RedisKeyExpiredEvent;
import org.springframework.stereotype.Component;

@Component
public class SessionExpirationObserver {

    @EventListener
    public void onExpired(RedisKeyExpiredEvent<?> event) {
        String id = new String(
            event.getId(),
            StandardCharsets.UTF_8
        );

        // Ví dụ quan sát: log hoặc tăng metric best effort.
        System.out.println("Expired entity: " + id);
    }
}
~~~

Luồng bình thường:

~~~text
Redis phát keyevent "expired"
          |
          v
Subscriber trong Spring Data Redis
          |
          v
RedisKeyExpiredEvent<?>
          |
          v
@EventListener xử lý
~~~

Nếu ứng dụng offline, chuỗi này bị đứt ở subscriber. Redis không giữ một danh sách event chờ `@EventListener` đăng ký trở lại.

### `ON_STARTUP` không sửa được downtime

Các chế độ phổ biến:

| Chế độ | Cách khởi tạo listener | Lưu ý |
| --- | --- | --- |
| `ON_STARTUP` | Khi ứng dụng khởi động | Giảm khoảng thời gian khởi tạo chậm; vẫn bỏ lỡ event trong lúc offline |
| `ON_DEMAND` | Khi có yêu cầu lưu entity TTL đầu tiên | Có thể bỏ lỡ thêm event nếu listener chưa được khởi tạo |
| `OFF` | Không bật listener Repository | Không xử lý expired event qua cơ chế này |

`ON_STARTUP` là lựa chọn hợp lý khi cần quan sát TTL ngay sau startup, nhưng bản thân nó **không đem lại tính bền vững** cho sự kiện.

### Cấu hình Redis được quản lý

Một số dịch vụ Redis hạn chế `CONFIG SET`. Spring Data Redis có thể cố cấu hình keyspace notifications lúc khởi tạo. Khi Redis đã được cấu hình qua cơ chế quản trị riêng, có thể ngăn Repository tự gửi lệnh cấu hình:

~~~java
@EnableRedisRepositories(
    enableKeyspaceEvents =
        RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP,
    keyspaceNotificationsConfigParameter = ""
)
~~~

Cấu hình trên **không tự bật event ở Redis**. Nhà cung cấp/hệ vận hành vẫn phải cho phép phát event phù hợp, chẳng hạn `Ex`.

## 6. Shadow copy của Repository có cứu được event đã mất không?

Trong một số cấu hình, Redis Repository tạo **shadow copy** (còn gọi phantom copy) của entity với hạn dài hơn khóa chính khoảng **5 phút**. Mục đích là giữ payload đủ lâu để handler có thể nhận object đã hết hạn khi Redis đã xóa khóa gốc.

~~~text
T0:    entity gốc được lưu với TTL 15 phút
       shadow copy giữ lâu hơn khoảng 5 phút

T+15:  entity gốc bị xóa -> Redis publish expired
       listener đang online có thể đọc shadow copy

T+20:  shadow copy có thể hết hạn
~~~

**Shadow copy không phải hàng đợi event.**

Giả sử Spring Boot offline từ phút 10 đến phút 18. Redis xóa entity chính ở phút 15 và phát sự kiện, nhưng không có subscriber. Khi ứng dụng trở lại ở phút 18, dù shadow copy còn tồn tại, **không có cơ chế tự phát lại event phút 15**.

Nếu không cần payload của entity trong event và muốn giảm chi phí bộ nhớ, có thể tắt shadow copy:

~~~java
@EnableRedisRepositories(
    enableKeyspaceEvents =
        RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP,
    shadowCopy = RedisKeyValueAdapter.ShadowCopy.OFF
)
~~~

Khi tắt, không nên kỳ vọng `event.getValue()` luôn mang theo entity đã xóa.

### Khi nào shadow copy hữu ích?

Nó hữu ích khi listener **có mặt tại lúc event được phát** nhưng cần đọc thêm thông tin entity đã mất khỏi khóa gốc. Với dữ liệu bắt buộc phải khôi phục sau offline dài, metadata phải được lưu ở nguồn bền vững độc lập.

## 7. Hậu quả thứ nhất: callback nghiệp vụ không chạy

Xét một đơn hàng chỉ được giữ chỗ 15 phút. Thiết kế ban đầu:

~~~text
Tạo đơn:
  Lưu Redis key order:123 với TTL 15 phút
  DB: order.status = PENDING

Khi nhận RedisKeyExpiredEvent:
  Cập nhật order.status = CANCELLED
~~~

Diễn tiến khi downtime:

~~~text
T+00: order=123, status=PENDING
T+10: Spring Boot dừng
T+15: Redis xóa order:123, gửi expired
      Không có listener -> mất event
T+30: Spring Boot chạy lại
      DB vẫn còn status=PENDING
~~~

Nếu không có cơ chế khác, đơn hàng có thể nằm ở `PENDING` mãi dù đã hết hạn.

Một vấn đề tương tự xảy ra với:

- gửi email hoặc thông báo sau deadline;
- hoàn tiền hoặc hoàn tài nguyên giữ chỗ;
- cập nhật lịch sử nghiệp vụ;
- dọn bản ghi liên quan;
- kích hoạt chuyển trạng thái đơn hàng/công việc;
- ghi dữ liệu kiểm toán cần đầy đủ.

**Không nên đặt công việc bắt buộc trong expired handler như đường duy nhất.** Callback thích hợp hơn cho log, metric, dọn phụ hoặc tín hiệu đánh thức worker.

### Tại sao không thể “đọc lại key” sau startup?

Khi TTL đã hết, khóa gốc không còn. Nếu toàn bộ thông tin nghiệp vụ chỉ nằm trong khóa đó, ứng dụng **không thể tái tạo chính xác payload đã mất** bằng `GET`, `SCAN` hoặc subscribe lại. Cần lưu ID, deadline và dữ liệu đủ để xử lý công việc ở nơi khác **trước khi khóa hết hạn**.

## 8. Hậu quả thứ hai: secondary index giữ ID đã hết hạn

Redis Repository có thể tạo secondary index cho trường được đánh dấu `@Indexed`:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("otp")
public class OtpRecord {

    @Id
    private String id;

    @Indexed
    private String userId;

    @TimeToLive
    private Long ttlSeconds;

    // constructor, getter, setter lược bớt
}
~~~

Để truy vấn theo `userId`, Repository sử dụng chỉ mục chứa các ID tương ứng. Khi entity hết hạn, notification có thể tham gia việc dọn index.

Nếu **ứng dụng không nhận event đúng lúc**, các tham chiếu trong secondary index có thể còn lại:

~~~text
Trước deadline:
  entity otp:o-7        tồn tại (TTL 60 giây)
  index userId=u-1      chứa ID o-7

Sau deadline lúc ứng dụng offline:
  entity otp:o-7        đã hết hạn/biến mất
  index userId=u-1      vẫn có thể chứa ID o-7
~~~

Hậu quả có thể gồm:

- Chỉ mục có member tham chiếu khóa không tồn tại.
- Truy vấn phải xử lý ID không nạp được entity.
- Phép đếm dựa trực tiếp vào số member index không phản ánh số entity còn sống.
- Dữ liệu index cũ làm tăng sử dụng bộ nhớ.
- Danh sách phân trang dựa trên index có thể trả thiếu phần tử thực tế nếu không lọc và đọc bù.

Không đồng nghĩa Repository sẽ trả về entity đã hết hạn: khi nạp khóa gốc, entity có thể không còn. Vấn đề nằm ở **metadata/index thiếu nhất quán** sau khi callback dọn chỉ mục bị bỏ lỡ.

Đối với index do ứng dụng tự quản lý (ví dụ một Sorted Set chứa ID entity), TTL trên entity gốc cũng **không tự xóa member trong ZSET**. Ứng dụng phải có quy tắc dọn riêng.

## 9. Quy tắc thiết kế: phân biệt hiệu lực và tác dụng phụ

Đối với mỗi thực thể TTL, hãy xác định hai câu hỏi khác nhau.

**Câu hỏi A: dữ liệu có còn hợp lệ để đọc/sử dụng không?**

Ví dụ OTP hoặc session. Có thể dựa vào TTL ở Redis, đồng thời kiểm tra điều kiện nghiệp vụ tại lúc sử dụng. Nếu khóa hết hạn trong lúc ứng dụng tắt, nó không được chấp nhận sau restart.

**Câu hỏi B: có công việc bắt buộc phải làm khi deadline qua hạn không?**

Ví dụ hủy đơn, giải phóng booking, phát email, ghi outbox. Công việc đó cần **nguồn deadline và trạng thái bền vững**, worker có thể chạy bù và thao tác idempotent.

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Dữ liệu cache tự vô hiệu hóa | Redis TTL thường đủ |
| Session bị từ chối sau hạn | Đọc Redis/kiểm tra deadline tại đường xác thực |
| Theo dõi metric hết hạn tương đối | Expired listener có thể phù hợp |
| Hủy đơn hàng quá hạn | Database deadline + worker đối soát |
| Hoàn tiền/gửi sự kiện bắt buộc | Trạng thái bền vững + outbox/queue có retry |
| Làm sạch secondary index | Dọn khi nhận event và đối soát/rebuild khi cần |

Điểm chung là **đường đọc và đường ghi** phải kiểm tra quy tắc nghiệp vụ hiện tại, không đợi callback chạy rồi mới thay đổi hành vi bảo mật hoặc tính hợp lệ.

## 10. Mẫu phục hồi đáng tin cậy: deadline bền vững + scheduler

Giả sử đơn hàng chờ thanh toán có thời hạn 15 phút. Lưu trạng thái ở database:

~~~sql
CREATE TABLE orders (
    id         VARCHAR(64) PRIMARY KEY,
    status     VARCHAR(16) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_orders_pending_expiry
  ON orders (expires_at)
  WHERE status = 'PENDING';
~~~

Tại lúc tạo đơn, lưu `expires_at` cùng với trạng thái `PENDING`; Redis có thể chứa bản sao tạm có TTL để tối ưu đường đọc. Worker tìm đơn quá hạn dựa trên database, không cần event Redis.

Ví dụ Spring Boot với `JdbcTemplate` và `@Scheduled`:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ExpiredOrderSweeper {

    private final JdbcTemplate jdbc;

    public ExpiredOrderSweeper(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Scheduled(fixedDelay = 30_000, initialDelay = 10_000)
    public void cancelOverdueOrders() {
        int updated = jdbc.update("""
            UPDATE orders
               SET status = 'CANCELLED'
             WHERE status = 'PENDING'
               AND expires_at <= CURRENT_TIMESTAMP
            """);

        System.out.println("Cancelled overdue orders: " + updated);
    }
}
~~~

Bật scheduling:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Sau restart, job chạy lại, đọc toàn bộ `PENDING` đã quá hạn và cập nhật. Nếu downtime kéo dài hơn TTL, job vẫn xác định được công việc từ database.

**Giới hạn ví dụ:** câu cập nhật tất cả bản ghi phù hợp dành cho minh họa. Với hàng triệu bản ghi quá hạn, cần batch giới hạn, chỉ mục phục vụ truy vấn, timeout và chiến lược điều phối. Nếu hủy đơn cần gửi email hoặc gọi API ngoài, nên dùng **transactional outbox** hoặc một cơ chế công việc bền vững riêng thay vì gọi bên ngoài trực tiếp trong câu quét.

### Chống thực hiện trùng

Nếu event đến muộn hoặc cả hai instance cùng chạy job:

~~~sql
UPDATE orders
   SET status = 'CANCELLED'
 WHERE id = :id
   AND status = 'PENDING'
   AND expires_at <= CURRENT_TIMESTAMP;
~~~

Điều kiện `status = 'PENDING'` giúp lần chạy sau không chuyển trạng thái thêm lần nữa. Để bảo vệ nghiệp vụ thanh toán, đường xác nhận thanh toán cũng phải kiểm tra hạn và trạng thái theo cùng quy tắc giao dịch; không chờ scheduler rồi mới từ chối đơn quá hạn.

Cần tránh trường hợp order được gia hạn nhưng handler vẫn dùng deadline cũ, hoặc entity được tạo lại với cùng ID khiến event cũ tác động đến entity mới. Khi cần, lưu **version/generation** để xác định chính xác đối tượng.

## 11. Kết hợp expired event như tín hiệu xử lý sớm

Khi đã có job bù, listener vẫn hữu ích để giảm độ trễ trong lúc ứng dụng online:

~~~text
                   Deadline + status ở DB
                             |
                             v
                +-------------------------+
                | Xử lý quá hạn idempotent|
                +------------+------------+
                             ^
                  +----------+----------+
                  |                     |
       Redis expired event      Scheduler đối soát
       (nhanh khi online)       (bù khi mất event)
~~~

Hai đường nên dùng cùng một hàm nghiệp vụ:

~~~java
public void onExpirationSignal(String id) {
    // Đọc trạng thái và expiresAt hiện tại.
    // Nếu vẫn quá hạn và chưa xử lý:
    // cập nhật có điều kiện, ghi outbox nếu cần.
}

public void recoverOverdueWork() {
    // Duyệt các đối tượng quá hạn chưa xử lý,
    // gọi cùng logic như đường nhận event.
}
~~~

Không nên viết một nhánh callback bỏ qua kiểm tra trạng thái chỉ vì tin rằng Redis `expired` đồng nghĩa với việc công việc chưa được ai xử lý. Pub/Sub có thể tới muộn; nhiều listener có thể nhận cùng notification; job bù cũng có thể chạy song song.

Nếu hành động có tác dụng ngoài (gửi email, thanh toán, chuyển tiền), cần lưu **idempotency key** hoặc trạng thái phát hành. Một câu cập nhật database có điều kiện giúp chống hủy trùng, nhưng chưa tự chống gửi cùng email hai lần nếu mã gửi chạy ngoài transaction.

## 12. Không có database khác: dùng deadline ledger trong Redis

Có hệ thống dùng Redis làm nơi lưu chính. Khi cần khôi phục việc đã đến hạn, có thể lưu **ledger công việc** ở một cấu trúc Redis không hết hạn cùng lúc với entity.

Ví dụ:

~~~text
session:s-42              khóa session tạm, TTL 15 phút

jobs:deadlines            Sorted Set
   member = "s-42"
   score  = deadline epoch milliseconds

jobs:payload:s-42         metadata đủ để hoàn thành công việc
                         không bị xóa theo TTL 15 phút
~~~

Lệnh minh họa:

~~~redis
SET session:s-42 "temporary" EX 900
ZADD jobs:deadlines 1893456000000 s-42

ZRANGE jobs:deadlines -inf 1893456000000 BYSCORE LIMIT 0 100
~~~

Khi restart, worker quét `jobs:deadlines` với score nhỏ hơn hoặc bằng thời điểm hiện tại. Nếu entity `session:s-42` đã biến mất, ledger vẫn giữ ID và deadline. Chỉ sau khi công việc hoàn thành mới loại bỏ khỏi ledger:

~~~redis
ZREM jobs:deadlines s-42
~~~

Ledger giải quyết bài toán “làm sao biết công việc nào đã quá hạn trong lúc offline”, nhưng chưa tự giải quyết toàn bộ vấn đề tin cậy:

- **Payload cần thiết phải còn tồn tại**, nếu không ledger chỉ cho biết ID.
- **Lưu entity và ledger phải có quy tắc nhất quán**, tránh một bước thành công còn bước kia thất bại.
- **Nhiều worker cần cơ chế claim/lease hoặc cập nhật có điều kiện** để không xử lý trùng.
- **Không xóa ledger trước khi ghi nhận thành công**; nếu crash giữa chừng sẽ mất công việc.
- **Cần retry và idempotency** đối với tác dụng phụ.
- **Cần cấu hình persistence và recovery phù hợp** nếu Redis cũng có thể ngừng hoạt động hoặc mất dữ liệu.

Các thao tác transaction/script nhiều key trong Redis Cluster phải đáp ứng yêu cầu hash slot. Không nên mặc định các lệnh trên nhiều slot có thể ghép thành một transaction nguyên tử.

Nếu tác vụ có hậu quả lớn, queue bền vững hoặc database giao dịch có outbox thường dễ lập luận tính đúng hơn một ledger tùy biến chưa xử lý hết các race condition.

## 13. Đối soát index sau khi ứng dụng trở lại

Với secondary index hoặc ZSET do ứng dụng quản lý, có ba mức xử lý.

### Mức 1: xác minh ở đường đọc

Khi lấy một danh sách ID từ index:

1. Đọc ID theo yêu cầu.
2. Nạp entity tương ứng.
3. Nếu entity đã hết hạn, loại nó khỏi kết quả.
4. Có thể đọc bù ID kế tiếp để đủ kích thước trang, đồng thời ghi nhận ID rác để dọn nền.

Cách này giúp API không dùng dữ liệu hết hạn, nhưng không làm index tự sạch.

### Mức 2: dọn theo batch

Worker định kỳ kiểm tra member trong index và đối chiếu với khóa entity. Với index do mình tạo, có thể dùng các lệnh quét thích hợp để loại ID đã mất. Cần giới hạn số lượng thao tác mỗi lượt.

Nếu cần duyệt keyspace, `SCAN` theo batch thường thích hợp hơn `KEYS *` trên hệ thống lớn. `SCAN` không tạo snapshot tuyệt đối, nên job phải idempotent và có thể chạy lại.

### Mức 3: rebuild index từ nguồn sự thật

Nếu dữ liệu chính nằm trong database bền vững, hãy xây lại index Redis từ nguồn đó. Để giảm gián đoạn, có thể tạo index mới theo namespace/version rồi chuyển đường đọc sau khi index sẵn sàng. Khi có ghi đồng thời, cần cơ chế cập nhật phát sinh trong quá trình rebuild để tránh thiếu dữ liệu.

Với index nội bộ của Redis Repository, nên dựa vào cơ chế chính thức của phiên bản đang dùng khi thiết kế đối soát; đừng tùy tiện sửa key nội bộ nếu chưa hiểu cấu trúc và quy tắc của Repository.

## 14. Thứ tự khởi động lại và xử lý backlog

Một tiến trình restart có thể tổ chức:

~~~text
Spring Boot START
       |
       v
Tạo kết nối Redis và bật listener khi cần
       |
       v
Khởi động đường đọc/ghi có kiểm tra trạng thái hiện tại
       |
       v
Chạy đối soát quá hạn từ nguồn bền vững
       |
       v
Tiếp tục scheduler định kỳ
~~~

Không nhất thiết chặn toàn bộ API trong lúc job bù đang chạy. Quyết định phụ thuộc mức nghiêm trọng của nghiệp vụ. Nhưng **đường thao tác quan trọng phải tự kiểm tra deadline**, kể cả khi backlog chưa xử lý xong.

Nếu downtime 6 giờ và có hàng triệu mục quá hạn, quá trình chạy bù có thể gây tải đột biến. Nên có:

- Batch size giới hạn và có thể cấu hình.
- Chỉ mục theo trạng thái/deadline ở nguồn dữ liệu.
- Retry có backoff khi hệ phụ thuộc lỗi.
- Trạng thái tiến độ đủ để tiếp tục sau lần crash tiếp theo.
- Idempotency cho từng bản ghi.
- Giới hạn công việc đồng thời và tốc độ phát tác dụng phụ.
- Theo dõi số việc tồn đọng và độ tuổi lớn nhất của việc trễ.

Đối với ứng dụng có nhiều instance, quyết định có một job coordinator hay nhiều worker cùng claim việc. Không để mỗi instance chạy một lượt toàn bảng chỉ vì cùng có annotation `@Scheduled`.

## 15. Quan sát độ trễ và sự kiện bị bỏ lỡ

Redis không có lệnh nào trả về danh sách `expired` mà một Spring Boot subscriber đã bỏ lỡ. Có thể quan sát tình hình bằng các số liệu gián tiếp:

~~~bash
redis-cli CONFIG GET notify-keyspace-events
redis-cli INFO stats
redis-cli INFO keyspace
~~~

| Chỉ số | Có thể biết | Không thể kết luận |
| --- | --- | --- |
| `notify-keyspace-events` | Redis đang bật loại event nào | Java handler đã nhận hay chưa |
| `expired_keys` trong `INFO stats` | Redis đã xóa bao nhiêu khóa do expiration | Những event đã mất của riêng ứng dụng |
| Log `@EventListener` | Sự kiện ứng dụng thực sự xử lý | Toàn bộ khóa hết hạn |
| Số bản ghi `PENDING` quá hạn | Khối lượng công việc cần phục hồi | Thời điểm Redis publish từng event |
| Số ID index không còn entity | Dấu hiệu index cũ | Mọi nguyên nhân của tình trạng đó |

Một số metric vận hành hữu ích:

~~~text
overdue_work_count
oldest_overdue_age_seconds
recovery_processed_total
recovery_failures_total
index_orphan_count
redis_expired_event_received_total
~~~

Metric cuối chỉ là số event **được nhận**; không thể dùng nó thay cho toàn bộ số thực thể đã hết hạn khi hệ thống có downtime.

## 16. Thực hành minh họa downtime và mất Pub/Sub message

Có thể thử trong môi trường Redis local để hiểu hiện tượng. Không cần chạy tác vụ build hoặc sửa cấu hình production.

### Bước 1 — Bật event ở Redis thử nghiệm

~~~bash
redis-cli CONFIG SET notify-keyspace-events Ex
redis-cli CONFIG GET notify-keyspace-events
~~~

### Bước 2 — Subscribe và tạo khóa khi listener đang online

Terminal A:

~~~bash
redis-cli PSUBSCRIBE '__keyevent@0__:expired'
~~~

Terminal B:

~~~bash
redis-cli SET demo:online "value" EX 5
~~~

Giữ Terminal A đang kết nối. Khi Redis thực sự xóa `demo:online`, Terminal A có thể nhận message.

### Bước 3 — Mô phỏng ứng dụng offline

Dừng Terminal A, sau đó ở Terminal B:

~~~bash
redis-cli SET demo:offline "value" EX 5
~~~

Sau deadline, kiểm tra:

~~~bash
redis-cli EXISTS demo:offline
redis-cli TTL demo:offline
~~~

Khi khóa không còn, `EXISTS` trả `0` và `TTL` trả `-2`.

### Bước 4 — Khởi động lại subscriber

Terminal A:

~~~bash
redis-cli PSUBSCRIBE '__keyevent@0__:expired'
~~~

Event `demo:offline` đã được publish trong lúc Terminal A không subscribe **không được phát lại**. Tạo một khóa mới để thấy subscriber có thể nhận notification mới.

**Lưu ý:** nếu Redis chưa kịp xóa vật lý `demo:offline` cho đến sau lúc Terminal A subscribe trở lại, có thể thấy event lúc đó. Đây là sự kiện được **publish muộn**, không phải replay event cũ.

### Bước 5 — Áp dụng với Repository

1. Lưu một entity `@TimeToLive` TTL ngắn.
2. Dừng Spring Boot trước deadline, giữ Redis chạy.
3. Chờ khóa gốc hết hạn và bị xóa.
4. Khởi động lại Spring Boot.
5. Xác minh entity đã hết hiệu lực nhưng callback trước đó không tự được chạy bù.
6. Nếu có worker đối soát, xác minh worker đọc deadline/trạng thái độc lập để xử lý việc tồn đọng.

Tình huống thử nghiệm cần quan sát cả việc Redis xóa khóa và thời điểm listener bắt đầu subscribe, tránh nhầm độ trễ active expiration với tính năng replay.

## 17. Các lỗi thiết kế phổ biến

### “`ON_STARTUP` giúp lấy lại mọi event khi restart”

Không. Chế độ này chỉ giúp listener sẵn sàng sớm hơn sau startup. Pub/Sub không có lịch sử để đọc bù.

### “Shadow copy giữ thêm 5 phút thì còn event để nhận”

Không. Shadow copy có thể giữ **dữ liệu**, không giữ **message**. Một message đã mất không tự quay lại.

### “Cứ lấy event expired làm lệnh hủy đơn”

Nếu application offline, lệnh hủy có thể không chạy. Nếu application có nhiều instance, cùng tín hiệu còn có thể đến nhiều handler. Cần nguồn bền vững và idempotency.

### “Redis key hết hạn thì mọi index liên quan được dọn”

Redis không tự hiểu mọi ZSET/index nghiệp vụ. Ngay cả secondary index do Repository quản lý cũng có thể còn tham chiếu cũ nếu notification cần thiết đã bị mất.

### “Chạy scheduler là đảm bảo đúng deadline”

Scheduler Spring cũng ngừng khi JVM tắt. Nó giúp **chạy bù** khi hệ thống trở lại, còn logic nghiệp vụ cần kiểm tra hạn ngay tại đường tương tác. Nếu cần xử lý liên tục trong lúc một instance tắt, triển khai worker HA hoặc scheduler hạ tầng có độ sẵn sàng phù hợp.

### “Có thể quét Redis để tìm tất cả entity đã chết”

Khóa đã xóa không còn dữ liệu để quét. Muốn khôi phục tác vụ, phải giữ danh sách ID/deadline/payload ở nơi khác từ trước.

### “Gọi lại subscriber là sẽ đọc được phần bị mất”

Tái kết nối Redis Pub/Sub không giống consumer group của một durable queue. Không có offset hay ACK cho các expired messages đã trôi qua.

## 18. Chọn cách xử lý theo thực thể

| Trường hợp | Redis TTL đủ chưa? | Có cần khôi phục công việc sau downtime? |
| --- | --- | --- |
| Cache thông thường | Thường đủ | Thường không, cache miss sẽ nạp lại |
| OTP hết hiệu lực sau 2 phút | TTL + xác minh dùng một lần | Không cần expired listener để từ chối OTP cũ |
| Session hết hạn | TTL và kiểm tra trạng thái mỗi request | Chỉ khi có công việc phụ bắt buộc |
| Giỏ hàng tạm | Tùy sản phẩm | Có nếu phải gửi thông báo/giữ lịch sử |
| Giữ chỗ | Không đủ cho toàn nghiệp vụ | Có: deadline bền vững và đối soát |
| Đơn hàng chờ thanh toán | Không đủ cho chuyển trạng thái | Có: kiểm tra trạng thái và hủy có điều kiện |
| Xử lý tài chính/email bắt buộc | Không | Có: outbox hoặc queue có retry |
| Entity có `@Indexed` | TTL của entity hoạt động | Có thể cần dọn/rebuild index |

Nếu chỉ cần “không thể đăng nhập bằng session đã hết hạn”, đừng thiết kế đăng xuất dựa vào listener mới chặn truy cập. Nếu cần “sau 15 phút phải giải phóng một tài nguyên trong hệ khác”, cần thiết kế một tác vụ bền vững và có thể thực hiện lại.

## 19. Một số câu hỏi thường gặp

**Ứng dụng tắt 30 phút, Redis key có TTL 5 phút. Sau restart key có còn không?**

Nếu Redis còn hoạt động và deadline đã qua, các thao tác truy cập thông thường coi khóa là hết hiệu lực. Không cần Spring Boot nhận event để khóa mất giá trị sử dụng.

**Có thể dùng `RedisMessageListenerContainer` để replay event cũ không?**

Không. Container chỉ subscribe Redis Pub/Sub. Nó không thể khôi phục những message publish khi không có subscriber kết nối.

**Nếu Redis xóa khóa trễ, ứng dụng có thể thấy event sau restart không?**

Có thể, nếu việc xóa thật sự xảy ra sau khi listener kết nối lại. Không được lấy tình huống này làm bảo đảm vận hành.

**`@TimeToLive` có làm việc khác `EXPIRE` khi ứng dụng tắt không?**

Không về bản chất quản lý TTL tại Redis. Annotation giúp Repository thiết lập expiration; sau khi lưu, Redis giữ thông tin thời hạn và xử lý khóa độc lập với JVM.

**Tắt shadow copy có làm mất TTL không?**

Không. Shadow copy phục vụ việc lấy payload khi nhận expiration event; TTL của khóa chính vẫn được Redis quản lý.

**Dùng Redis Streams để thay Pub/Sub được không?**

Streams có khả năng lưu message và hỗ trợ consumer group, nhưng expired notifications **không tự động biến thành một Stream**. Ứng dụng phải ghi công việc cần phục hồi vào Stream/queue tại thời điểm đáng tin cậy, chẳng hạn khi tạo deadline. Nếu chỉ ghi vào Stream bên trong expired callback, callback vẫn có thể bị bỏ lỡ khi ứng dụng offline.

**Nếu chạy nhiều pod Spring Boot thì sao?**

Pod còn subscribe có thể nhận event dù pod khác offline; tuy nhiên nếu toàn bộ consumer dừng hoặc kết nối lỗi, event có thể mất. Ngoài ra nhiều pod có thể xử lý cùng tín hiệu. Giữ cơ chế đối soát và idempotency.

**Vì sao không nên chỉ dùng timestamp trong event?**

Event được phát khi Redis xóa khóa, có thể muộn hơn deadline logic. Một callback sau restart còn có thể đến sau khi object cùng ID được tạo lại. Hãy kiểm tra trạng thái, deadline, generation/version từ nguồn sự thật trước khi gây tác dụng phụ.

## 20. Nguyên tắc áp dụng

Khi một entity Spring Data Redis có TTL, hãy nhớ:

1. Redis vẫn quản lý TTL khi Spring Boot tắt, nếu Redis đang hoạt động.
2. `expired` là notification tại thời điểm Redis xóa khóa, có thể trễ hơn deadline.
3. Notification truyền qua Pub/Sub **không bền vững và không replay**.
4. `RedisKeyExpiredEvent`, `ON_STARTUP` và shadow copy **không sửa được sự kiện đã mất lúc offline**.
5. Secondary indexes có thể giữ tham chiếu cũ nếu bước dọn phụ thuộc listener.
6. Mọi nghiệp vụ bắt buộc sau deadline phải có **deadline/trạng thái bền vững, worker đối soát, xử lý idempotent và quan sát backlog**.
7. Đường đọc/ghi phải tự kiểm tra hiệu lực và deadline; event chỉ làm tín hiệu hỗ trợ.

## Tài liệu tham khảo

- [Spring Data Redis – Time To Live trong Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Spring Data Redis – Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html)
- [Spring Data Redis – EnableRedisRepositories API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/repository/configuration/EnableRedisRepositories.html)
- [Redis – Keyspace Notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
- [Redis – Pub/Sub](https://redis.io/docs/latest/develop/pubsub/)
- [Redis – EXPIRE](https://redis.io/docs/latest/commands/expire/)
- [Redis – ZRANGE](https://redis.io/docs/latest/commands/zrange/)
