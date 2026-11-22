# Cơ chế hết hạn chủ động, thụ động và độ trễ thông báo trong Spring Data Redis

## 1. Vì sao TTL bằng 0 không đồng nghĩa sự kiện được gửi ngay?

Khi xây dựng session, mã OTP, giỏ hàng tạm hoặc khóa tạm thời với Redis, ta thường gán **time to live (TTL)** để dữ liệu tự hết hiệu lực. Tuy nhiên, có ba mốc thời gian khác nhau:

1. **`t_deadline` – hết hiệu lực về mặt logic:** thời hạn đã tới, lệnh đọc thông thường không được coi khóa đó là còn hợp lệ.
2. **`t_delete` – Redis thực sự loại bỏ khóa:** Redis phát hiện khóa hết hạn và xóa nó bằng cơ chế **thụ động** hoặc **chủ động**.
3. **`t_receive` – ứng dụng nhận thông báo:** một subscriber còn kết nối nhận sự kiện từ Redis, rồi callback của Spring xử lý nó.

Ta có thể hình dung:

~~~text
SET session:42 ... PX 30000
      |
      |       Khóa vẫn còn thời gian sống
      v
t0 -------------------------- t_deadline ------- t_delete ---- t_receive
                              TTL hết hạn        Redis xóa      Spring nhận
                              về mặt logic       khóa           sự kiện
~~~

Hai khoảng trễ cần phân biệt:

- **Trễ phát hiện/xóa**: `t_delete - t_deadline`. Redis không có nghĩa vụ xóa mọi khóa chính xác vào mili giây cuối cùng của TTL.
- **Trễ truyền và xử lý**: `t_receive - t_delete`. Gồm việc phân phối Pub/Sub, kết nối mạng, lập lịch luồng và phần việc trong listener.

Nếu ứng dụng cần chặn truy cập sau thời hạn, phải kiểm tra tính hợp lệ của dữ liệu/thời hạn ở **đường đọc hoặc đường thực hiện nghiệp vụ**. Không dùng thời điểm nhận `expired` làm đồng hồ quyết định quyền truy cập.

> **Nguyên tắc cốt lõi:** TTL kiểm soát **hiệu lực** của khóa; Redis keyspace notification chỉ báo rằng Redis **đã xóa** khóa hết hạn. Thông báo là tín hiệu phụ trợ, không phải một bộ lập lịch đúng hạn hoặc hàng đợi công việc bền vững.

## 2. Redis lưu và kiểm tra thời hạn ra sao?

Redis gắn thời điểm hết hạn cho các khóa có TTL. Khi thao tác với khóa, Redis so sánh thời điểm hiện tại với hạn đã lưu; khi quá hạn, khóa được xem là hết hiệu lực. TTL được đặt bằng những lệnh như:

~~~redis
SET session:42 "user-7" EX 30
EXPIRE session:42 60
PEXPIRE session:42 1500
EXPIREAT session:42 1893456000
PERSIST session:42
~~~

- `EX` và `EXPIRE` dùng giây; `PX` và `PEXPIRE` dùng mili giây.
- `EXPIREAT` dùng thời điểm Unix tính bằng giây; `PEXPIREAT` dùng mili giây.
- `PERSIST` bỏ thời hạn của một khóa đang tồn tại; sau đó khóa không tự hết hạn do TTL cũ.
- Ghi đè giá trị bằng một lệnh như `SET key value` không giữ TTL cũ nếu không yêu cầu giữ thời hạn; lệnh `SET ... KEEPTTL` có mục đích giữ TTL.

Kiểm tra:

~~~redis
TTL session:42
PTTL session:42
EXISTS session:42
~~~

| Kết quả | Ý nghĩa |
| --- | --- |
| `TTL` trả về số dương hoặc `0` | Thời gian còn lại tính bằng giây; `0` có thể chỉ là còn dưới một giây do cách làm tròn |
| `PTTL` trả về số không âm | Thời gian còn lại tính bằng mili giây |
| `TTL` hoặc `PTTL` trả về `-1` | Khóa còn tồn tại nhưng không có thời hạn |
| `TTL` hoặc `PTTL` trả về `-2` | Khóa không tồn tại hoặc đã được coi là hết hạn |
| `EXISTS` trả về `0` | Khóa không còn hiện diện từ góc nhìn thao tác này |

Điểm cần nhớ: `TTL == -2` hoặc `GET == nil` **không chứng minh** subscriber đã nhận `expired`. Có thể khóa vừa bị phát hiện và xóa, event không được bật, listener chưa đăng ký hoặc thông điệp đã bị mất.

## 3. Hết hạn thụ động (passive / lazy expiration)

Cơ chế thụ động xảy ra khi một lệnh **truy cập khóa** và Redis phát hiện hạn đã qua:

1. Client gửi lệnh liên quan đến `session:42`.
2. Redis kiểm tra metadata hết hạn.
3. Nếu thời hạn đã qua, Redis xử lý khóa như đã hết hạn và loại bỏ khóa theo cơ chế tương ứng.
4. Lệnh đọc nhận kết quả như khóa không còn tồn tại; nếu cấu hình notification phù hợp, sự kiện `expired` được phát khi xóa.

Ví dụ, đặt TTL một giây rồi để hai giây mới đọc:

~~~redis
SET demo:lazy "hello" EX 1
GET demo:lazy
~~~

Nếu `GET` được gọi sau hạn và khóa chưa bị cơ chế chủ động xóa trước đó, chính lần truy cập này khiến Redis phát hiện và xóa khóa. Kết quả là `nil`.

**Ưu điểm:** Redis không phải quét mọi khóa trong từng thao tác; khóa được truy cập sẽ không tiếp tục trả về dữ liệu đã quá hạn.

**Giới hạn:** khóa đã hết hạn nhưng **không ai truy cập** có thể còn chiếm bộ nhớ cho tới khi cơ chế chủ động phát hiện nó. Vì vậy cần thêm cơ chế chủ động.

Không nên gọi `GET` liên tục chỉ để thúc ép gửi sự kiện. Việc truy cập có thể làm sự kiện xuất hiện sớm hơn, nhưng vẫn không bảo đảm subscriber nhận được, đồng thời tạo tải không cần thiết.

## 4. Hết hạn chủ động (active expiration)

Redis định kỳ dành một phần công việc nền của vòng xử lý để **lấy mẫu những khóa có TTL** và xóa các khóa đã quá hạn, kể cả khi không có client nào truy cập chúng.

Luồng khái niệm:

~~~text
Chu kỳ xử lý chủ động
       |
       v
Chọn một tập khóa có TTL
       |
       v
Kiểm tra hạn từng khóa
       |
       +--> Chưa hết hạn --> giữ lại
       |
       +--> Đã hết hạn ---> xóa --> có thể phát "expired"
       |
       v
Tiếp tục / kết thúc chu kỳ theo ngân sách xử lý
~~~

Redis sử dụng cơ chế lấy mẫu và giới hạn công việc để tránh dành toàn bộ CPU cho việc xóa khóa. Một chu kỳ không nhất thiết kiểm tra hết mọi khóa có TTL. Khi số lượng khóa lớn, thời điểm hết hạn phân bố dày hoặc Redis đang bận, việc xóa có thể xảy ra sau hạn một khoảng đáng kể.

Các điểm vận hành cần hiểu:

- **Chủ động** không có nghĩa là một timer riêng được đăng ký cho từng khóa. Không nên hình dung `EXPIRE` tạo một callback chính xác sau N giây.
- **Thụ động và chủ động bổ sung cho nhau.** Khóa nóng thường bị phát hiện qua truy cập; khóa lạnh vẫn có cơ hội được cơ chế chủ động thu hồi.
- Cấu hình Redis như `hz` hoặc `active-expire-effort` (tùy phiên bản) có thể ảnh hưởng mức nỗ lực xử lý hết hạn. Tăng nỗ lực có thể giảm lượng khóa đã quá hạn còn lưu nhưng tiêu tốn thêm CPU; đây là bài toán cân bằng, không tạo cam kết độ trễ.
- Đếm số khóa đã hết hạn (`expired_keys`) cho biết Redis đã xử lý bao nhiêu khóa, không cho biết subscriber đã nhận bao nhiêu sự kiện.

### So sánh hai cơ chế

| Tiêu chí | Thụ động | Chủ động |
| --- | --- | --- |
| Yếu tố kích hoạt | Có thao tác chạm tới khóa | Redis thực hiện công việc hết hạn theo chu kỳ |
| Khóa ít/không được truy cập | Không tự phát hiện chỉ nhờ cách này | Vẫn có thể được thu hồi |
| Tính đúng của đường đọc | Hỗ trợ tránh đọc dữ liệu quá hạn | Hỗ trợ dọn dẹp bộ nhớ |
| Thời điểm xóa | Khi khóa hết hạn bị truy cập | Khi mẫu/chu kỳ phát hiện ra khóa |
| Thời điểm sự kiện `expired` | Sau khi phát hiện và xóa | Sau khi phát hiện và xóa |
| Cam kết đúng deadline | Không | Không |

### Ví dụ cùng một thời hạn nhưng khác thời điểm thông báo

Giả sử hai khóa cùng hết hạn về mặt logic ở giây thứ 10:

~~~text
Thời gian (giây)       0               10                11        15
                       |---------------|-----------------|---------|
key A: GET ở giây 11   SET             hết hạn           GET -> xóa -> expired
key B: không ai đọc    SET             hết hạn                     quét -> xóa -> expired
~~~

Giây thứ 11 và 15 là **minh họa**, không phải thời gian Redis bảo đảm. Trong thực tế, chu kỳ chủ động có thể xóa cả A trước khi lệnh `GET` tới; hoặc B được xóa sớm hơn ví dụ.

## 5. Redis phát sự kiện gì, vào lúc nào?

Redis có cơ chế **keyspace notifications** qua Pub/Sub, mặc định có thể đang tắt. Hai họ kênh thường gặp:

| Kiểu | Kênh ví dụ | Nội dung message |
| --- | --- | --- |
| Keyspace | `__keyspace@0__:session:42` | Tên sự kiện, ví dụ `expired` |
| Keyevent | `__keyevent@0__:expired` | Tên khóa, ví dụ `session:42` |

Số `0` là logical database đang theo dõi. Để nghe các sự kiện **khóa hết hạn** của DB 0 theo kiểu keyevent, cấu hình tối thiểu:

~~~bash
redis-cli CONFIG SET notify-keyspace-events Ex
redis-cli CONFIG GET notify-keyspace-events
~~~

Trong chuỗi `Ex`, chữ hoa `E` bật **keyevent**, chữ thường `x` bật **expired**. Nếu muốn keyspace events, dùng `Kx`; dùng `KEx` khi muốn cả hai. Chỉ định `x` mà thiếu `E` hoặc `K` sẽ không tạo channel có thể nhận theo hai họ trên.

### Thực hành quan sát trên hai terminal

**Terminal A – đăng ký trước khi tạo khóa:**

~~~bash
redis-cli PSUBSCRIBE '__keyevent@0__:expired'
~~~

**Terminal B – tạo khóa ngắn hạn:**

~~~bash
redis-cli SET demo:ttl-42 "payload" PX 1500
redis-cli PTTL demo:ttl-42
~~~

Khi Redis **thực sự xóa** `demo:ttl-42` do hết hạn, Terminal A có thể nhận:

~~~text
pmessage
__keyevent@0__:expired
__keyevent@0__:expired
demo:ttl-42
~~~

Khoảng chờ không nhất thiết đúng 1.500 ms. Nếu cần tự quan sát sự khác nhau giữa hai cơ chế, hãy tạo nhiều khóa cùng hạn, để một phần không được truy cập và thử `GET` một khóa sau deadline. Chỉ xem đây là thí nghiệm minh họa; chu kỳ chủ động có thể xóa khóa trước thao tác đọc.

### Phân biệt các sự kiện dễ nhầm

| Tình huống | Sự kiện tiêu biểu | Điều cần hiểu |
| --- | --- | --- |
| `EXPIRE k 30` thành công | `expire` nếu bật nhóm sự kiện liên quan | Báo **đã đặt TTL**, chưa phải khóa đã chết |
| Redis xóa `k` vì TTL kết thúc | `expired` | Báo khóa đã bị xóa do hết hạn |
| `DEL k` | `del` | Xóa chủ động bởi lệnh |
| `EXPIRE k 0` hoặc đặt hạn đã qua | `del` | Redis xóa ngay; không đồng nghĩa `expired` |
| Redis thu hồi khóa vì `maxmemory` | `evicted` | Hết bộ nhớ theo chính sách, không phải TTL |
| `PERSIST k` | `persist` nếu được bật và có thay đổi | Xóa thời hạn, không xóa khóa |

Đây là khác biệt quan trọng khi viết xử lý nghiệp vụ: **`expire` (không có chữ d cuối)** là sự kiện đặt hạn; **`expired`** là sự kiện đã hết hạn và bị loại bỏ.

## 6. Vì sao thông báo đến trễ, hoặc hoàn toàn không đến?

Ngay cả khi khóa có deadline xác định, ứng dụng có thể không thấy sự kiện đúng thời điểm. Các nguồn trễ và mất thông báo nằm ở nhiều tầng:

| Tầng | Nguyên nhân | Biểu hiện |
| --- | --- | --- |
| Redis – phát hiện | Active expiration lấy mẫu và có giới hạn ngân sách | Khóa hết hiệu lực ở `t_deadline` nhưng event xuất hiện muộn |
| Redis – tài nguyên | Nhiều khóa hết hạn đồng loạt, CPU bận, lượng TTL lớn | Độ trễ xóa biến động |
| Redis – cấu hình | `notify-keyspace-events` chưa bật đúng nhóm | Không có sự kiện trên channel đang nghe |
| Kết nối Pub/Sub | Mất kết nối, khởi động listener muộn, Redis failover | Sự kiện trong khoảng gián đoạn bị mất |
| Spring – tiêu thụ | Listener bận, luồng xử lý nghẽn, GC hoặc mạng chậm | Redis đã phát nhưng handler chạy muộn |
| Kiến trúc | Nghe sai DB, sai node hoặc thiếu node trong Redis Cluster | Chỉ nhận được một phần các sự kiện |

Cần tách rõ hai vấn đề:

**1. Redis phát chậm:** `t_delete` muộn hơn `t_deadline`. Đây là bản chất của cơ chế hết hạn.

**2. Ứng dụng bỏ lỡ:** Redis có thể đã phát sự kiện, nhưng Pub/Sub **không lưu hàng đợi để phát lại**. Listener rớt mạng hoặc ứng dụng tắt lúc đó sẽ mất sự kiện. Bật lại listener không khôi phục các message đã trôi qua.

Redis Cluster còn có một điểm đặc biệt: keyspace notification thuộc **node chứa khóa**, không tự được phát rộng tới mọi node như kỳ vọng của người chỉ subscribe một kết nối. Để quan sát đầy đủ phải cân nhắc subscribe tới các node liên quan và xử lý topology khi failover.

### Kết luận vận hành về độ trễ

Không nên coi `expired` là một lời hứa kiểu “sẽ chạy callback trong vòng 100 ms kể từ khi hết TTL”. Dù dùng `@TimeToLive`, `RedisMessageListenerContainer` hay `@EventListener`, Spring vẫn phụ thuộc vào thời điểm Redis phát event và khả năng nhận Pub/Sub.

## 7. Dùng `StringRedisTemplate` và `RedisMessageListenerContainer`

Với Spring Boot có dependency `spring-boot-starter-data-redis`, ta có thể gắn TTL trực tiếp lên giá trị bằng `StringRedisTemplate`:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SessionStore {
    private final StringRedisTemplate redis;

    public SessionStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String sessionId, String userId) {
        redis.opsForValue().set(
            "session:" + sessionId,
            userId,
            Duration.ofSeconds(30)
        );
    }

    public boolean isValid(String sessionId) {
        return Boolean.TRUE.equals(redis.hasKey("session:" + sessionId));
    }
}
~~~

Ở đây, `isValid` hỏi Redis ngay thời điểm truy cập. Phương thức này **không đợi** sự kiện hết hạn để quyết định session có hiệu lực.

Để nghe tên khóa đã hết hạn trên Redis đơn lẻ, database 0:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class RedisExpirationListenerConfig {

    @Bean
    RedisMessageListenerContainer expirationListenerContainer(
            RedisConnectionFactory connectionFactory) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);

        container.addMessageListener((message, pattern) -> {
            String key = new String(
                message.getBody(),
                StandardCharsets.UTF_8
            );

            if (key.startsWith("session:")) {
                // Demo: ghi nhận sự kiện; không thực hiện việc nặng tại callback.
                System.out.println("Session key expired: " + key);
            }
        }, new ChannelTopic("__keyevent@0__:expired"));

        return container;
    }
}
~~~

Cần bật `notify-keyspace-events Ex` tại Redis trước, vì listener trực tiếp trong ví dụ không tự bảo đảm cấu hình Redis. Với môi trường production, nên dùng logger và chuyển công việc tốn thời gian sang bộ xử lý riêng.

**Lưu ý về payload:** trên `__keyevent@0__:expired`, message là **tên khóa**. Giá trị của khóa gốc đã bị xóa nên `GET key` trong callback thường trả về `nil`. Nếu cần thông tin nghiệp vụ sau khi hết hạn, hãy lưu metadata ở nơi có vòng đời phù hợp, hoặc thiết kế một sự kiện riêng.

**Lưu ý phạm vi:** ví dụ này subscribe một Redis instance, logical DB 0. Không thể chỉ đổi thành wildcard ở tên DB rồi mặc định có đủ event của Redis Cluster; cần xử lý kết nối tới các node tương ứng.

## 8. Dùng Spring Data Redis Repository với `@TimeToLive`

Spring Data Redis Repository quản lý đối tượng và TTL qua `@RedisHash(timeToLive = ...)` hoặc `@TimeToLive`.

### Cấu hình một entity hết hạn

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

Ví dụ, lưu `new LoginSession("s-42", "u-7", 30L)` bằng một Redis Repository sẽ thiết lập hạn cho entity theo số giây của `ttlSeconds`.

Khai báo thay thế bằng `@RedisHash(value = "login-session", timeToLive = 30)` phù hợp khi mọi entity cùng TTL. Nếu cùng lúc có `@TimeToLive` trên thuộc tính, thuộc tính này dùng để quyết định TTL. Với `@TimeToLive` trên property, khi đọc entity, Spring Data Redis có thể nạp giá trị TTL hiện tại từ Redis; `-1` nghĩa là không có expiration.

### Bật lắng nghe sự kiện cho Repository

Mặc định cơ chế lắng nghe expiry của Redis Repository có thể **tắt**. Có thể bật khi ứng dụng khởi động:

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

Khi listener nhận notification thích hợp, Spring Data Redis có thể phát sự kiện ứng dụng `RedisKeyExpiredEvent<?>`:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.context.event.EventListener;
import org.springframework.data.redis.core.RedisKeyExpiredEvent;
import org.springframework.stereotype.Component;

@Component
public class SessionExpirationEvents {

    @EventListener
    public void onExpired(RedisKeyExpiredEvent<?> event) {
        String id = new String(event.getId(), StandardCharsets.UTF_8);
        System.out.println("Redis repository entity expired, id=" + id);

        // event.getValue() có thể null, tùy cấu hình shadow copy.
    }
}
~~~

Đây là sự kiện của **Spring Data Redis Repository** và phụ thuộc vào listener của Repository. Không mặc định suy ra rằng mọi khóa do `StringRedisTemplate` hoặc Spring Cache tạo ra đều phát cùng một `RedisKeyExpiredEvent`.

### Phantom/shadow copy: vì sao đôi khi event có giá trị đã xóa?

Để hỗ trợ sự kiện mang theo object đã hết hạn, Repository có thể lưu **bản sao tạm (phantom/shadow copy)** của entity, với hạn muộn hơn khóa gốc khoảng năm phút. Khi nhận notification của khóa chính, Repository có cơ hội đọc bản sao và đưa object vào `event.getValue()`. Việc này tiêu thụ thêm bộ nhớ.

Nếu chỉ cần ID, có thể tắt shadow copy:

~~~java
@EnableRedisRepositories(
    enableKeyspaceEvents =
        RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP,
    shadowCopy = RedisKeyValueAdapter.ShadowCopy.OFF
)
~~~

Khi tắt, đừng kỳ vọng `event.getValue()` chứa object đã hết hạn; hãy dùng ID và dữ liệu lưu ở nơi khác.

### Cấu hình Redis được quản lý không cho phép `CONFIG SET`

Một số dịch vụ Redis được quản lý hạn chế lệnh `CONFIG`. Với Repository, Spring Data Redis có thể cố thiết lập `notify-keyspace-events` nếu chưa có. Khi nhà cung cấp không cho phép, phải cấu hình notification bằng phương thức được họ hỗ trợ và yêu cầu Repository **không can thiệp**:

~~~java
@EnableRedisRepositories(
    enableKeyspaceEvents =
        RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP,
    keyspaceNotificationsConfigParameter = ""
)
~~~

Giá trị rỗng ở đây có nghĩa là không gửi lệnh cấu hình notification; **Redis vẫn phải được cấu hình để phát `Ex`**. Nếu dùng Redis Cluster, còn phải xem cách ứng dụng subscribe các node.

### Cảnh báo về secondary indexes

Redis Repository có thể dùng thông báo hết hạn để dọn tham chiếu trong secondary indexes. Nếu listener tắt hoặc ứng dụng mất kết nối lúc khóa hết hạn, công việc dọn các tham chiếu đó có thể bị bỏ qua. Do đó, đặc biệt với tìm kiếm qua index, cần thiết kế đường kiểm tra dữ liệu gốc và phương án dọn đối soát nếu tính nhất quán là quan trọng.

## 9. Thiết kế nghiệp vụ khi cần đúng hạn hoặc xử lý chắc chắn

Từ các đặc điểm trên, hãy phân loại yêu cầu trước khi chọn giải pháp.

| Nhu cầu | Thiết kế phù hợp | Vai trò của expired event |
| --- | --- | --- |
| Session/OTP không được dùng sau hạn | Đọc Redis hoặc kiểm tra `expiresAt` trước khi cho thao tác | Tùy chọn, dùng để cập nhật UI, đo đạc hoặc dọn phụ |
| Cache tự biến mất sau một khoảng | Redis TTL | Không bắt buộc |
| Ghi log/metric “khóa đã được xóa” | Keyspace notification, chấp nhận có thể trễ/mất | Phù hợp nếu metric là best effort |
| Hủy đơn hàng/chốt trạng thái đúng deadline | Lưu deadline bền vững, scheduler/worker kiểm tra trạng thái và deadline | Chỉ dùng như tín hiệu đánh thức sớm |
| Gửi email, hoàn tiền, thu phí hoặc xử lý bắt buộc một lần | Hàng đợi bền vững + idempotency + trạng thái giao dịch | Không làm nguồn công việc duy nhất |

### Ví dụ: đơn hàng chờ thanh toán 15 phút

**Thiết kế dễ lỗi:**

~~~text
Tạo order:123 trong Redis, TTL=15 phút
      |
      v
Chỉ khi nhận expired -> cập nhật DB: order = CANCELLED
~~~

Nếu Pub/Sub mất event, đơn hàng có thể mắc kẹt ở `PENDING`. Nếu Redis phát muộn, việc hủy cũng muộn.

**Thiết kế có thể phục hồi:**

1. Khi tạo đơn, lưu `status=PENDING` và `expiresAt` trong cơ sở dữ liệu bền vững; Redis TTL có thể dùng để tối ưu truy cập hoặc đánh thức xử lý.
2. Worker định kỳ tìm các đơn `PENDING` với `expiresAt <= now`, hoặc lấy deadline từ một lịch tác vụ bền vững.
3. Worker đổi trạng thái bằng thao tác có điều kiện, ví dụ chỉ cập nhật nếu trạng thái **vẫn** là `PENDING`; đã thanh toán thì không hủy.
4. Nếu có `expired` event, dùng nó để kích hoạt kiểm tra sớm, nhưng worker đối soát vẫn bảo đảm phát hiện các đơn bị bỏ sót.

Pseudocode cho ý tưởng:

~~~sql
UPDATE orders
SET status = 'CANCELLED'
WHERE id = :order_id
  AND status = 'PENDING'
  AND expires_at <= CURRENT_TIMESTAMP;
~~~

Số hàng được cập nhật bằng 0 nghĩa là order không còn thỏa điều kiện; handler có thể kết thúc an toàn. Logic tương tự giúp tránh xung đột khi event tới sau khi người dùng đã thanh toán hoặc khi nhiều instance cùng nhận event.

### Vì sao idempotency vẫn cần thiết?

Pub/Sub không có cơ chế phát lại và xác nhận như hàng đợi bền vững. Tuy nhiên, trong môi trường ứng dụng nhiều instance, một event có thể được **mỗi instance** đang subscribe xử lý, dẫn tới nhiều tác dụng phụ cho cùng khóa. Cần dùng trạng thái bền vững, khóa/idempotency key hoặc cập nhật có điều kiện để nghiệp vụ không chạy lặp sai.

Ngoài ra, nếu ứng dụng tái sử dụng tên khóa (ví dụ `session:42` được tạo lại sau khi cũ hết hạn), handler nhận tên khóa không nên tự suy ra “phiên mới cũng đã hết hạn”. Dùng phiên bản/generation hoặc xác thực trạng thái hiện tại trước thao tác quan trọng.

## 10. Quan sát, chẩn đoán và đo độ trễ

Để điều tra “TTL 30 giây nhưng event đến phút thứ 31” hoặc “không thấy event”, nên ghi nhận theo từng tầng.

### Kiểm tra phía Redis

~~~bash
redis-cli CONFIG GET notify-keyspace-events
redis-cli INFO stats
redis-cli INFO keyspace
redis-cli PTTL session:42
~~~

- `notify-keyspace-events` phải chứa đúng ký tự nhóm sự kiện và kiểu kênh đang subscribe.
- `INFO stats` có các bộ đếm như `expired_keys` và `evicted_keys`; sự tăng của `expired_keys` cho thấy Redis có xóa khóa hết hạn, không bảo đảm app nhận Pub/Sub.
- `INFO keyspace` giúp quan sát số khóa và số khóa có expiry của từng logical DB.
- `PTTL` hữu ích trước deadline; sau khi khóa không còn, nó không phục dựng được thời điểm Redis đã phát thông báo.

### Ghi log có ba mốc rõ ràng

Khi nghiệp vụ tạo khóa, lưu `createdAt` và `expectedExpiresAt` (hoặc correlation ID) vào hệ quan sát. Trong handler, ghi `receivedAt` và tên khóa. Độ chênh quan sát được:

~~~text
observed_delay = receivedAt - expectedExpiresAt
~~~

**Đây là độ trễ đầu cuối**, gồm thời điểm Redis phát hiện, truyền thông và Spring xử lý; không chỉ riêng active expiration. Nếu dùng đồng hồ từ nhiều máy, phải tính sai lệch đồng hồ và việc đồng bộ thời gian. Chỉ từ timestamp tại ứng dụng không thể khẳng định chính xác Redis đã xóa vào lúc nào.

### Các câu hỏi chẩn đoán hữu ích

1. Khóa có TTL thực sự không, hay một lần `SET` sau đó đã làm mất TTL?
2. Listener có đăng ký từ **trước khi khóa hết hạn** không?
3. Đang subscribe `__keyevent@0__:expired` nhưng Redis chỉ bật `Kx`, hoặc khóa nằm ở DB khác?
4. Có failover/reconnect/khởi động lại ứng dụng quanh thời điểm đó không?
5. Đang kết nối một node Redis Cluster trong khi khóa nằm ở node khác?
6. Có phải người dùng đang đợi `expired` nhưng khóa được `DEL` hoặc `EXPIRE 0`, nên sự kiện thực tế là `del`?
7. Callback có đang thực hiện I/O chậm, chặn luồng listener hoặc thiếu cơ chế bàn giao việc sang worker?

## 11. Những câu hỏi thường gặp

**TTL đã hết mà bộ nhớ chưa giảm ngay, có phải Redis bị lỗi?**  
Không nhất thiết. Hết hạn logic và thu hồi vật lý là hai thời điểm; Redis dùng cơ chế lấy mẫu chủ động và xóa thụ động để cân bằng chi phí CPU. Bộ nhớ còn phụ thuộc allocator, cấu trúc dữ liệu và việc Redis tái sử dụng bộ nhớ.

**Tại sao gọi `GET` ngay sau deadline thì thấy event?**  
Đó có thể là cơ chế thụ động phát hiện khóa hết hạn khi bị truy cập. Nhưng cũng có thể active expiration vừa xóa nó. Không thể suy ra mọi lần đọc sau deadline đều làm event đến listener.

**Dùng `@TimeToLive` có làm event chính xác hơn không?**  
Không. Annotation giúp Spring Data Redis thiết lập/đọc TTL của entity; thời điểm Redis xóa và gửi `expired` vẫn tuân theo cơ chế Redis.

**Tại sao handler nhận key nhưng không lấy được value?**  
Vì sự kiện `expired` được gửi khi khóa gốc đã bị xóa. Repository có thể hỗ trợ shadow copy để mang object vào `RedisKeyExpiredEvent`, còn listener Redis thông thường nhận tên khóa.

**Nên chọn `ON_STARTUP` hay `ON_DEMAND`?**  
`ON_STARTUP` khởi tạo listener khi ứng dụng bắt đầu; `ON_DEMAND` chờ lần đầu lưu entity có expiration. Khởi động muộn có thể bỏ lỡ sự kiện. Cả hai đều không sửa được tính không bền vững của Pub/Sub.

**Có thể dùng Redis expired event làm cron job không?**  
Chỉ phù hợp cho hành động phụ trợ chấp nhận chậm hoặc bỏ lỡ. Công việc phải hoàn thành đúng hạn cần deadline bền vững, worker đối soát và xử lý idempotent.

## 12. Ghi nhớ khi áp dụng

- **Passive expiration:** kiểm tra khi truy cập khóa; hỗ trợ trả kết quả đúng ở đường đọc.
- **Active expiration:** lấy mẫu và dọn khóa nền; xử lý cả khóa không có người truy cập.
- **Expired notification:** phát **sau khi Redis xóa khóa**, không phải khi bộ đếm TTL vừa đạt 0; có thể trễ và Pub/Sub có thể làm mất message.
- **Spring Data Redis:** `StringRedisTemplate` đặt TTL; `RedisMessageListenerContainer` nghe kênh Redis; Repository có `@TimeToLive` và `RedisKeyExpiredEvent` khi bật listener tương ứng.
- **Thiết kế đáng tin cậy:** deadline và trạng thái nghiệp vụ là nguồn quyết định, còn event hết hạn là tín hiệu hỗ trợ.

## Tài liệu chính thức

- [Redis – EXPIRE: How Redis expires keys](https://redis.io/docs/latest/commands/expire/)
- [Redis – Keyspace notifications và timing của expired events](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
- [Spring Data Redis – Time To Live (Repositories)](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Spring Data Redis – EnableRedisRepositories API](https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/repository/configuration/EnableRedisRepositories.html)
