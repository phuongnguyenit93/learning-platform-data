# RedisMessageListenerContainer và nhận thông báo liên quan đến phiên

Khi ứng dụng dùng Spring Session với Redis, việc lưu session và việc nhận thông báo về vòng đời session là hai nhiệm vụ khác nhau. Repository ghi dữ liệu phiên vào Redis; Redis phát các thông báo khi có một số sự kiện; `RedisMessageListenerContainer` nhận các thông báo đó và chuyển chúng tới listener của Spring Session. Listener dịch thông điệp Redis thành các application event như `SessionCreatedEvent`, `SessionDeletedEvent` và `SessionExpiredEvent` để mã ứng dụng có thể phản ứng.

Để nhận đầy đủ các sự kiện vòng đời phiên từ Redis, ứng dụng Servlet cần dùng `RedisIndexedSessionRepository`. Repository Redis cơ bản (`RedisSessionRepository`) lưu session theo ID nhưng không hỗ trợ phát session events. Cấu hình thường dùng là `@EnableRedisHttpSession(enableIndexingAndEvents = true)` hoặc cơ chế tương đương của Spring Boot theo phiên bản đang triển khai.

`RedisMessageListenerContainer` là thành phần của Spring Data Redis quản lý việc đăng ký subscription và phân phối message. Nó không phải nơi lưu session, không tự xác thực người dùng và không quyết định request có được phép dùng session hay không. Hiểu đúng vai trò của container, Redis keyspace notifications và các event Spring giúp ứng dụng xử lý logout, timeout, WebSocket và dọn tài nguyên mà vẫn giữ được tính đúng đắn khi chạy nhiều instance.

## 1. Các thành phần trong luồng thông báo

### 1.1. `RedisIndexedSessionRepository`

`RedisIndexedSessionRepository` là triển khai `SessionRepository` dùng Redis và bổ sung cấu trúc index cho session. Ngoài việc lưu dữ liệu theo session ID, repository có thể lập chỉ mục để tìm các phiên theo principal hoặc thông tin được hỗ trợ. Đây cũng là triển khai Spring Session Redis hỗ trợ các event vòng đời quan trọng.

Trong ứng dụng Servlet, repository thường được dùng cùng `SessionRepositoryFilter`. Filter tiếp tục cung cấp API `HttpSession` cho controller và Spring Security, còn repository lưu dữ liệu phiên vào Redis. Khi cần nhận session events, repository được kết hợp với `SessionMessageListener` và `RedisMessageListenerContainer`.

### 1.2. `RedisMessageListenerContainer`

`org.springframework.data.redis.listener.RedisMessageListenerContainer` thuộc Spring Data Redis. Nó quản lý các subscription tới Redis Pub/Sub channel hoặc pattern channel, sử dụng `RedisConnectionFactory` để tạo kết nối và chuyển message nhận được tới một hoặc nhiều `MessageListener`.

Container giúp ứng dụng không phải tự viết vòng lặp đọc socket Redis. Nó quản lý vòng đời subscription, kết nối lại theo cơ chế của Spring Data Redis và việc dispatch message bằng executor được cấu hình. Trong Spring Session, container chuyển các thông báo liên quan đến session tới listener do framework đăng ký.

Các trách nhiệm cần phân biệt:

| Thành phần | Trách nhiệm |
|---|---|
| Redis | Lưu key/hash của session và phát Pub/Sub hoặc keyspace notification |
| `RedisMessageListenerContainer` | Đăng ký nhận message, quản lý subscription và dispatch message |
| `SessionMessageListener` | Diễn giải thông báo Redis liên quan tới vòng đời session |
| `RedisIndexedSessionRepository` | Tìm/xóa dữ liệu phiên và phát Spring application event phù hợp |
| `ApplicationEventPublisher` | Phát event trong Spring `ApplicationContext` của instance |
| `@EventListener` | Chạy logic ứng dụng khi nhận Spring event |

### 1.3. Luồng tổng quát

```mermaid
flowchart TD
    A[RedisIndexedSessionRepository] --> B[(Redis)]
    B --> C[Pub/Sub: channel tạo session]
    B --> D[Keyspace notification: del/expired]
    C --> E[RedisMessageListenerContainer]
    D --> E
    E --> F[SessionMessageListener]
    F --> G[RedisIndexedSessionRepository]
    G --> H[Spring ApplicationEventPublisher]
    H --> I[@EventListener trong ứng dụng]
```

Luồng tạo session và luồng xóa/hết hạn dùng các loại thông báo Redis khác nhau. Khi session được tạo, Spring Session phát một message lên channel riêng. Khi session bị xóa hoặc hết hạn, Redis keyspace notifications cung cấp thông báo về thao tác `DEL` hoặc expiration. Container tiếp nhận cả hai loại thông báo theo subscription được cấu hình.

## 2. Chọn repository có hỗ trợ event

### 2.1. Repository Redis cơ bản và repository indexed

Spring Session có hai triển khai Redis thường gặp:

| Repository | Lưu session | Index để tra theo principal | Session lifecycle events |
|---|---|---|---|
| `RedisSessionRepository` | Có | Không có đầy đủ khả năng indexed của triển khai indexed | Không hỗ trợ phát session events |
| `RedisIndexedSessionRepository` | Có | Có | Hỗ trợ `SessionCreatedEvent`, `SessionDeletedEvent`, `SessionExpiredEvent` |

Nếu ứng dụng cần phản ứng khi session bị xóa hoặc hết hạn, chỉ cấu hình Redis repository mặc định là chưa đủ. Cần bật indexing và events để dùng `RedisIndexedSessionRepository`.

### 2.2. Cấu hình bằng annotation

Ví dụ cấu hình ứng dụng Servlet:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisHttpSession;

@Configuration
@EnableRedisHttpSession(
    enableIndexingAndEvents = true,
    maxInactiveIntervalInSeconds = 1800,
    redisNamespace = "portal:session"
)
public class RedisSessionConfiguration {
}
```

Trong ví dụ:

- `enableIndexingAndEvents = true` chọn `RedisIndexedSessionRepository` và bật cơ chế nhận session events.
- `maxInactiveIntervalInSeconds = 1800` đặt timeout không hoạt động mặc định là 30 phút.
- `redisNamespace` tạo vùng khóa riêng cho ứng dụng; khóa Redis và channel liên quan bắt đầu bằng namespace này.

Khi dùng Spring Boot, có thể để auto-configuration tạo repository và chọn loại repository indexed theo property mà phiên bản Boot hỗ trợ. Hãy kiểm tra cấu hình thực tế của phiên bản Spring Boot/Spring Session trong dự án. Không khai báo thêm một `RedisMessageListenerContainer` hoặc listener thứ hai nếu cấu hình Spring Session đã tự tạo chúng; hai container cùng đăng ký có thể làm event được xử lý lặp.

## 3. Những loại thông báo Redis liên quan đến session

### 3.1. Session được tạo: Redis Pub/Sub channel

Khi session được tạo, Spring Session phát message lên một channel có tên chứa session ID. Với namespace mặc định, channel có dạng:

```text
spring:session:channel:created:<session-id>
```

Phần `<session-id>` là ID của phiên mới. Nội dung message chứa dữ liệu session được tạo. Khi đăng ký làm `MessageListener`, `RedisIndexedSessionRepository` nhận message và chuyển thành `SessionCreatedEvent` trong Spring application context.

Đây là message Pub/Sub do Spring Session phát, không phải keyspace notification do Redis tự phát khi key hết hạn. Vì vậy, nếu cần nhận thông báo tạo phiên, ứng dụng phải dùng cấu hình indexed/events tương ứng và subscription của Spring Session.

### 3.2. Session bị xóa: keyspace notification `del`

Khi session bị xóa rõ ràng, ví dụ người dùng logout và repository xóa phiên, Redis phát keyspace notification tương ứng với lệnh xóa. Spring Session lắng nghe sự kiện generic command `del` và chuyển nó thành `SessionDeletedEvent`.

`SessionDeletedEvent` là một dạng `SessionDestroyedEvent`. Nó thể hiện phiên bị hủy do thao tác xóa rõ ràng, khác với việc phiên hết hạn do không hoạt động.

### 3.3. Session hết hạn: keyspace notification `expired`

Khi TTL của khóa theo dõi expiration hết hạn, Redis có thể phát keyspace notification `expired`. Spring Session dùng thông báo này để xác định session ID, tra dữ liệu phiên còn được giữ lại và phát `SessionExpiredEvent`.

`SessionExpiredEvent` cũng là một dạng `SessionDestroyedEvent`. Event này cho biết phiên bị hủy vì hết hạn theo timeout. Ứng dụng có thể dùng nó để đóng WebSocket, thu hồi tài nguyên gắn với phiên hoặc cập nhật số liệu.

### 3.4. Bảng phân biệt

| Tình huống | Nguồn thông báo | Spring event |
|---|---|---|
| Tạo session | Redis Pub/Sub channel do Spring Session phát | `SessionCreatedEvent` |
| Logout/invalidate và xóa session | Redis keyspace notification cho `del` | `SessionDeletedEvent` |
| Session hết hạn | Redis keyspace notification cho `expired` | `SessionExpiredEvent` |

Không phải mọi lần cập nhật thuộc tính session đều phát một lifecycle event tương ứng. Những event này tập trung vào tạo, xóa và hết hạn. Nếu cần theo dõi mọi thay đổi thuộc tính, cần một cơ chế audit riêng ở tầng nghiệp vụ.

## 4. Redis keyspace notifications

### 4.1. Vì sao phải bật?

Redis không mặc định phát tất cả keyspace notifications. Spring Session cần nhận thông báo về lệnh xóa key và key hết hạn để dọn các tài nguyên gắn với phiên. Với cấu hình Redis thường dùng, các nhóm notification cần thiết gồm:

- `E`: phát thông báo theo dạng keyevent channel.
- `g`: các lệnh generic như `DEL`.
- `x`: sự kiện key hết hạn (`expired`).

Tổ hợp ví dụ là:

```text
notify-keyspace-events Egx
```

`E` chọn keyevent notification, `g` bật nhóm generic command và `x` bật expired event. Tên channel keyevent có dạng `__keyevent@<db>__:del` hoặc `__keyevent@<db>__:expired`; container có thể subscribe theo pattern để nhận trên database index phù hợp.

### 4.2. Cấu hình Redis

Trong môi trường cho phép thay đổi cấu hình runtime, quản trị viên có thể bật tùy chọn bằng lệnh Redis:

```bash
redis-cli CONFIG SET notify-keyspace-events Egx
```

Hoặc cấu hình trong file `redis.conf`:

```text
notify-keyspace-events Egx
```

Đây là cấu hình ở phía Redis server. Khi đã có các cờ notification khác, cần hợp nhất các cờ cần thiết thay vì vô tình ghi đè cấu hình hiện hữu. `CONFIG SET` có thể bị vô hiệu hóa trong môi trường production được bảo vệ; không nên cấp quyền quản trị Redis rộng cho ứng dụng chỉ để bật notification.

### 4.3. Redis được quản lý hoặc khóa quyền CONFIG

Trong Redis được quản trị bởi cloud provider hoặc cấu hình bảo mật nghiêm ngặt, ứng dụng có thể không được phép gọi `CONFIG SET`. Spring Session mặc định có thể thử cấu hình keyspace notifications khi khởi động. Nếu Redis không cho phép lệnh cấu hình, cần cấu hình notification ở phía quản trị dịch vụ và khai báo `ConfigureRedisAction.NO_OP` để Spring Session không cố thay đổi cấu hình Redis.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.ConfigureRedisAction;

@Configuration
public class RedisNotificationConfiguration {

    @Bean
    ConfigureRedisAction configureRedisAction() {
        return ConfigureRedisAction.NO_OP;
    }
}
```

`NO_OP` chỉ tắt thao tác tự cấu hình Redis của Spring Session. Nó không tự bật notification. Nếu dùng `NO_OP` mà quản trị viên chưa bật `notify-keyspace-events` trên Redis, các event dựa trên `del`/`expired` sẽ không đến ứng dụng.

### 4.4. Kiểm tra cấu hình notification

Có thể kiểm tra giá trị hiện tại bằng lệnh:

```bash
redis-cli CONFIG GET notify-keyspace-events
```

Trong môi trường không cho phép `CONFIG GET`, cần dùng console hoặc công cụ quản trị của nhà cung cấp Redis để xác minh. Sau khi cấu hình, hãy kiểm thử thực tế bằng cách tạo một session, xóa session và để một session test hết hạn; xác nhận event listener của ứng dụng nhận đúng event. Chỉ thấy cấu hình trong file không đủ để chứng minh mọi node Redis đang chạy với cùng giá trị.

## 5. RedisMessageListenerContainer quản lý subscription

### 5.1. Vòng đời container

`RedisMessageListenerContainer` sử dụng `RedisConnectionFactory` để thiết lập subscription tới Redis. Nó nhận đăng ký gồm listener và topic/pattern, sau đó dispatch message tới listener khi Redis phát thông báo.

Trong cấu hình Spring Session indexed thông thường, framework tạo và cấu hình container cùng `SessionMessageListener`. Vì vậy, ứng dụng thường chỉ cần bật repository indexed/events và cung cấp các bean tùy chỉnh nếu có nhu cầu về executor. Không nên tạo một container thủ công chỉ để nghe lại cùng các channel mà Spring Session đã đăng ký.

### 5.2. Subscription và dispatch là hai việc khác nhau

Container có hai nhóm công việc:

- **Subscription:** duy trì việc đăng ký nhận message từ Redis. Công việc này có thể được thực hiện bằng subscription executor.
- **Dispatch:** đưa message nhận được tới `MessageListener` để xử lý. Công việc này có thể dùng task executor.

Spring Session cho phép tùy chỉnh hai executor thông qua bean có tên `springSessionRedisTaskExecutor` và `springSessionRedisSubscriptionExecutor`. Nếu không có nhu cầu hiệu năng cụ thể, nên giữ cấu hình mặc định do Spring Session cung cấp.

### 5.3. Tùy chỉnh executor khi cần

Ví dụ cấu hình task executor để dispatch message:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class RedisListenerExecutorConfiguration {

    @Bean(name = "springSessionRedisTaskExecutor")
    ThreadPoolTaskExecutor springSessionRedisTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("spring-session-redis-");
        return executor;
    }
}
```

Các con số chỉ là ví dụ. Chọn pool size và queue capacity dựa trên số message, thời gian xử lý listener và tài nguyên của instance. Queue quá nhỏ có thể gây từ chối hoặc nghẽn khi có đợt event lớn; queue quá lớn làm tăng bộ nhớ và độ trễ xử lý. Nếu listener thực hiện công việc chậm, nên chuyển công việc nghiệp vụ nặng sang executor hoặc hàng đợi riêng.

Nếu cần điều chỉnh việc đăng ký subscription, có thể cung cấp bean tên `springSessionRedisSubscriptionExecutor` theo cùng nguyên tắc. Không dùng một executor có số thread quá thấp cho cả công việc subscription và xử lý nặng nếu điều đó khiến việc nhận message bị trì hoãn.

### 5.4. Không xử lý nghiệp vụ nặng ngay trong listener

Spring application event listener mặc định có thể chạy đồng bộ trên thread đang phát event. Nếu listener thực hiện gọi API chậm, truy vấn database dài hoặc gửi email, nó có thể làm chậm đường xử lý message. Hãy giữ listener ngắn, ghi nhận ID/event type và chuyển công việc nặng sang worker/queue phù hợp.

Nếu dùng `@Async`, cần cấu hình executor và xác định rõ hành vi khi queue đầy, ứng dụng dừng hoặc xử lý thất bại. `@Async` không biến Redis Pub/Sub thành một hàng đợi bền vững; nó chỉ thay đổi cách ứng dụng thực thi listener.

## 6. Nhận Spring Session event trong ứng dụng

### 6.1. Dùng `@EventListener`

Sau khi message Redis được chuyển thành Spring event, ứng dụng có thể dùng `@EventListener` để xử lý. Ví dụ:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.session.events.SessionCreatedEvent;
import org.springframework.session.events.SessionDeletedEvent;
import org.springframework.session.events.SessionExpiredEvent;

@Component
public class SessionLifecycleListener {

    private static final Logger log = LoggerFactory.getLogger(SessionLifecycleListener.class);

    @EventListener
    public void onCreated(SessionCreatedEvent event) {
        log.info("Session created: {}", event.getSessionId());
    }

    @EventListener
    public void onDeleted(SessionDeletedEvent event) {
        log.info("Session deleted: {}", event.getSessionId());
    }

    @EventListener
    public void onExpired(SessionExpiredEvent event) {
        log.info("Session expired: {}", event.getSessionId());
    }
}
```

`getSessionId()` là định danh phù hợp để ghi log có kiểm soát hoặc liên kết với số liệu. Không ghi toàn bộ session attribute hoặc session ID dạng credential vào log công khai. `getSession()` có thể cung cấp đối tượng session cho event; với một số repository, dữ liệu session gốc có thể không còn lấy được và giá trị trả về có thể là `null`. Listener nên xử lý trường hợp này.

### 6.2. Dùng event cha `SessionDestroyedEvent`

`SessionDeletedEvent` và `SessionExpiredEvent` đều kế thừa `SessionDestroyedEvent`. Nếu cùng một logic áp dụng cho mọi trường hợp phiên bị hủy, có thể lắng nghe event cha:

```java
@EventListener
public void onDestroyed(SessionDestroyedEvent event) {
    String sessionId = event.getSessionId();
    // Dọn tài nguyên dùng chung cho mọi session bị hủy.
}
```

Nếu cần phân biệt logout rõ ràng với timeout, hãy lắng nghe hai event con riêng. Tránh đăng ký đồng thời handler cho event cha và event con rồi thực hiện cùng một side effect hai lần mà không có chủ đích.

### 6.3. Ứng dụng với WebSocket

Một use case quan trọng của `SessionDestroyedEvent` là đóng các kết nối WebSocket gắn với HTTP session đã bị xóa hoặc hết hạn. Nếu người dùng logout ở một instance, Redis notification giúp các instance có listener biết session đã bị hủy và có thể dọn kết nối tương ứng.

Đây là cơ chế phối hợp vòng đời giữa HTTP session và tài nguyên WebSocket. Nó không thay thế việc kiểm tra quyền ở mỗi thao tác WebSocket và không đảm bảo event đến tức thì trong mọi tình huống. Ứng dụng nên thiết kế thời hạn kết nối, xác thực lại và xử lý khi listener tạm mất kết nối.

## 7. Redis lưu expiration và phát event như thế nào?

### 7.1. Không xóa hash session ngay tại thời điểm timeout

`RedisIndexedSessionRepository` cần dữ liệu session còn tồn tại trong một khoảng ngắn sau khi session hết hạn logic để có thể dựng event và dọn index/tài nguyên liên quan. Vì vậy, TTL của hash session có thể dài hơn timeout thực tế khoảng năm phút.

Repository tạo một khóa expiration riêng có dạng:

```text
spring:session:sessions:expires:<session-id>
```

Khóa riêng này có TTL bằng `maxInactiveInterval`. Khi nó hết hạn, Redis phát keyspace notification `expired`. Listener dùng session ID trong tên key để tra session hash còn được giữ lại và phát `SessionExpiredEvent`.

Nhờ vậy, session data vẫn sẵn sàng cho việc xử lý event khi thời hạn không hoạt động vừa kết thúc. API `findById` của repository vẫn bảo đảm không trả về session đã hết hạn, kể cả khi hash vật lý còn tồn tại thêm khoảng đệm.

### 7.2. Redis có thể phát expired event trễ

Redis không cam kết phát expired notification chính xác ngay tại thời điểm TTL chạm 0. Việc xóa key hết hạn có thể diễn ra khi key được truy cập hoặc trong quá trình Redis quét nền. Nếu key không được truy cập, event có thể đến muộn.

Spring Session theo dõi các session sắp hết hạn theo mốc thời gian và có tác vụ nền truy cập các khóa expiration có khả năng đã hết TTL. Việc truy cập cho phép Redis tự xóa key nếu TTL thực sự đã hết và phát event tương ứng. Cách này giúp việc phát event có tính xác định cao hơn so với chỉ chờ Redis background expiration.

Tuy vậy, thời điểm listener nhận `SessionExpiredEvent` vẫn không nên được xem là đồng hồ chính xác cho nghiệp vụ. Khi xác minh một request, repository mới là nguồn quyết định session còn hợp lệ hay không. Event phục vụ thông báo và dọn tài nguyên liên quan.

### 7.3. Phân biệt hết hạn logic và xóa vật lý

| Mốc | Ý nghĩa |
|---|---|
| Inactivity timeout đạt hạn | Session không còn hợp lệ để dùng cho request |
| Expiration key hết TTL | Redis có thể phát notification để Spring Session xử lý |
| Session hash được dọn | Dữ liệu session bị xóa sau khi hoàn tất xử lý cần thiết |
| Spring event được phát | Listener trong ứng dụng nhận thông báo vòng đời |

Vì các bước không nhất thiết xảy ra cùng một mili giây, không dùng việc nhìn thấy hash trong Redis làm bằng chứng session còn hợp lệ. Cũng không dùng event listener làm cơ chế duy nhất để từ chối request trái phép.

## 8. Vận hành nhiều instance

### 8.1. Mỗi instance có listener riêng

Trong triển khai nhiều instance, mỗi application instance thường có `RedisMessageListenerContainer` kết nối tới Redis và đăng ký các subscription tương ứng. Redis Pub/Sub phát message tới các subscriber đang lắng nghe channel/pattern đó. Do vậy, event có thể được chuyển tới application context của nhiều instance.

Điều này hữu ích khi mỗi instance cần dọn tài nguyên cục bộ, ví dụ đóng WebSocket đang được giữ trên chính instance đó. Tuy nhiên, nếu mọi instance đều chạy cùng một listener nghiệp vụ để gửi email, ghi audit hoặc gọi dịch vụ ngoài, cùng một Redis event có thể khiến side effect chạy nhiều lần.

Hãy phân biệt:

- Công việc cục bộ trên từng instance: có thể cần mọi instance nhận event.
- Công việc toàn hệ thống chỉ được thực hiện một lần: cần cơ chế phối hợp như idempotency key, distributed lock, consumer group/queue bền vững hoặc một worker được chọn.

Redis Pub/Sub không phải consumer group và không phân phối message theo kiểu mỗi message chỉ tới một worker. Tất cả subscriber phù hợp có thể nhận cùng message.

### 8.2. Redis Cluster

Khi dùng `RedisIndexedSessionRepository` với Redis Cluster, cần chú ý giới hạn subscription keyspace event theo node của Redis Cluster. Tài liệu Spring Session lưu ý repository có thể chỉ subscribe từ một node được chọn, trong khi event phát sinh ở node khác. Điều này có thể khiến một số index session không được dọn như mong đợi.

Trước khi triển khai Redis Cluster, hãy xác minh hành vi theo phiên bản Spring Session và Spring Data Redis đang dùng, kiểm tra topology và cách phân phối key, đồng thời kiểm thử việc tạo, xóa và hết hạn session trên các shard. Đừng giả định một subscription tới một node sẽ tự động quan sát mọi keyspace event trên toàn cluster.

### 8.3. Mất kết nối và message bị bỏ lỡ

Redis Pub/Sub là cơ chế truyền thông điệp tạm thời. Nếu container chưa subscribe, ứng dụng mất kết nối hoặc instance đang khởi động lại đúng lúc message được phát, message có thể bị bỏ lỡ; Redis không lưu message để phát lại cho subscriber sau khi kết nối trở lại.

Do đó:

- Event listener phải chịu được việc không nhận được một thông báo.
- Dọn tài nguyên cần có cơ chế đối soát hoặc timeout dự phòng nếu tài nguyên không thể rò rỉ lâu dài.
- Không dùng session event làm nguồn duy nhất cho audit pháp lý, thanh toán hoặc tác vụ cần đảm bảo không mất.
- Với tác vụ quan trọng, ghi nhận trạng thái bền vững trong database/outbox hoặc queue có cơ chế retry và xác nhận.

### 8.4. Idempotency

Một listener có thể nhận lại cùng một thông tin do retry ở tầng ứng dụng, do nhiều instance cùng nhận broadcast hoặc do một quy trình dọn dẹp được kích hoạt nhiều lần. Thiết kế handler idempotent: xử lý cùng `sessionId` và event type nhiều lần không tạo ra kết quả sai.

Ví dụ, xóa một WebSocket session đã đóng nên an toàn nếu thao tác được gọi lần thứ hai. Cập nhật trạng thái audit nên có khóa duy nhất hoặc event ID để tránh tạo bản ghi trùng. Không giả định Redis Pub/Sub cung cấp exactly-once delivery.

## 9. Kiểm thử listener và session events

### 9.1. Kiểm thử cấu hình

Xác minh ứng dụng thực sự dùng `RedisIndexedSessionRepository` và có `RedisMessageListenerContainer` hoạt động. Nếu dùng annotation, kiểm tra `enableIndexingAndEvents = true`; nếu dùng Spring Boot, kiểm tra repository type hiệu lực. Đồng thời xác minh Redis đã bật `notify-keyspace-events` phù hợp.

### 9.2. Kiểm thử tạo session

Tạo session thông qua `HttpSession` hoặc `SessionRepository`, sau đó xác minh listener nhận `SessionCreatedEvent` với đúng session ID. Kiểm tra subscription tới channel created đang dùng namespace tương ứng.

### 9.3. Kiểm thử xóa session

Tạo session, lưu ID, gọi logout/invalidate và xác minh `SessionDeletedEvent` được phát. Kiểm tra `findById` không còn trả session và các tài nguyên gắn với session được dọn theo chính sách.

### 9.4. Kiểm thử hết hạn

Trong môi trường test, đặt timeout rất ngắn. Không chỉ chờ một khoảng thời gian rồi giả định event đã được phát; hãy chờ event với timeout kiểm thử hợp lý và kiểm tra cả trạng thái repository. Xác minh `SessionExpiredEvent` đến, nhưng cũng xác minh request tiếp theo không được dùng phiên ngay khi phiên hết hạn logic.

### 9.5. Kiểm thử nhiều instance và lỗi

Chạy hai instance cùng dùng một Redis. Tạo session qua A, quan sát event ở A và B; logout ở A, kiểm tra listener trên B cũng nhận event; để session hết hạn và kiểm tra tài nguyên WebSocket cục bộ ở mỗi instance được dọn. Ngắt listener tạm thời rồi khôi phục kết nối để quan sát rằng message trong thời gian mất kết nối không được phát lại.

## 10. Chẩn đoán sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| Không nhận `SessionCreatedEvent` | Đang dùng `RedisSessionRepository` cơ bản hoặc indexing/events chưa bật | Kiểm tra repository type và `enableIndexingAndEvents` |
| Không nhận `SessionDeletedEvent` | Redis chưa bật keyspace generic command notifications hoặc listener container không hoạt động | Kiểm tra `notify-keyspace-events` có `E` và `g`, subscription và log container |
| Không nhận `SessionExpiredEvent` | Thiếu cờ `x`, expiration key không phát event hoặc keyspace subscription lỗi | Kiểm tra `Egx`, TTL expiration key, listener và Redis logs |
| Ứng dụng lỗi khi khởi động vì `CONFIG SET` | Redis khóa lệnh CONFIG | Quản trị viên cấu hình keyspace notifications và khai báo `ConfigureRedisAction.NO_OP` |
| Event đến trễ | Redis phát expired notification không đúng thời điểm tuyệt đối hoặc tác vụ nền chưa truy cập key | Kiểm tra expiration mapping, cleanup task và trạng thái repository |
| Một side effect chạy nhiều lần | Nhiều instance cùng subscribe Pub/Sub | Thiết kế handler idempotent hoặc dùng cơ chế điều phối cho công việc toàn cục |
| Không dọn đủ index trên Redis Cluster | Subscription keyspace event không quan sát mọi node | Kiểm thử theo shard và đối chiếu giới hạn của phiên bản đang dùng |
| Listener làm chậm xử lý message | Handler đồng bộ thực hiện công việc nặng | Rút gọn handler, điều chỉnh executor hoặc chuyển công việc sang queue riêng |
| Session vẫn còn key sau timeout | Hash được giữ thêm khoảng đệm để xử lý event | Kiểm tra expiration key và kết quả `findById`, không chỉ kiểm tra hash |

Khi điều tra, không ghi session ID hoặc session attribute nhạy cảm vào log. Ghi event type, namespace, instance ID, thời điểm nhận và một định danh đã che/mã hóa phù hợp để đối chiếu giữa các node.

## 11. Quy trình triển khai

Khi cần nhận thông báo vòng đời session từ Redis, thực hiện theo trình tự:

1. Xác định ứng dụng cần indexing và event nào: tạo, xóa hay hết hạn.
2. Chọn `RedisIndexedSessionRepository` bằng cấu hình phù hợp, ví dụ `enableIndexingAndEvents = true`.
3. Bảo đảm `RedisMessageListenerContainer` và `SessionMessageListener` được cấu hình bởi Spring Session; tránh tạo subscription trùng lặp.
4. Bật Redis keyspace notifications cho generic command và expired event; với Redis được quản trị, cấu hình ở phía dịch vụ và dùng `ConfigureRedisAction.NO_OP` khi cần.
5. Viết `@EventListener` ngắn, idempotent và chỉ thực hiện công việc phù hợp với độ tin cậy của Pub/Sub.
6. Nếu cần tùy chỉnh dispatch, cấu hình đúng executor bean name và theo dõi queue, thread, độ trễ.
7. Kiểm thử create/delete/expire, logout, timeout, WebSocket và trường hợp listener mất kết nối.
8. Với nhiều instance hoặc Redis Cluster, kiểm tra event fan-out, duplicate side effect và khả năng nhận keyspace event trên mọi node.
9. Dùng repository làm nguồn quyết định session còn hợp lệ; dùng event để thông báo và dọn tài nguyên liên quan.

`RedisMessageListenerContainer` là cầu nối subscription và dispatch message từ Redis tới listener của Spring Session. Khi dùng `RedisIndexedSessionRepository`, các message tạo phiên và keyspace notifications cho xóa/hết hạn được chuyển thành Spring application events. Cấu hình đúng repository, keyspace notifications và listener giúp các instance phối hợp dọn tài nguyên theo vòng đời session; đồng thời ứng dụng phải chịu được event trễ, message bị bỏ lỡ và việc nhiều subscriber cùng nhận một message.

## Tài liệu tham khảo

- [Spring Session — Redis Configurations và Listening to Session Events](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session API — RedisIndexedSessionRepository](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/data/redis/RedisIndexedSessionRepository.html)
- [Spring Session API — SessionCreatedEvent](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/events/SessionCreatedEvent.html)
- [Spring Session API — SessionDeletedEvent](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/events/SessionDeletedEvent.html)
- [Spring Session API — SessionExpiredEvent](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/events/SessionExpiredEvent.html)
- [Spring Data Redis — RedisMessageListenerContainer](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html)
