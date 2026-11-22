# Vai trò của bản sao phụ khi xử lý sự kiện hết hạn

Trong **Spring Data Redis Repository**, TTL (*Time To Live*) có thể được khai báo trực tiếp trên entity để Redis tự loại bỏ bản ghi sau một khoảng thời gian. Nhưng có một câu hỏi thực tế: **khi khóa chính đã hết hạn và bị Redis xóa, làm thế nào ứng dụng vẫn lấy được nội dung của entity để xử lý sự kiện hết hạn?**

Spring Data Redis giải quyết bài toán này bằng một **bản sao phụ** (*shadow copy*, còn gọi là *phantom copy*). Khi Repository lưu entity có TTL dương, ngoài khóa chính, framework có thể lưu thêm một bản sao với thời hạn dài hơn khoảng **5 phút**. Khi Redis thông báo khóa chính hết hạn, bản sao phụ cho phép Spring Data Redis tái tạo giá trị entity để đưa vào `RedisKeyExpiredEvent`.

Bản sao phụ hữu ích cho việc quan sát và xử lý sự kiện, nhưng phải hiểu đúng phạm vi: nó không kéo dài thời gian sống của khóa chính, không phải Redis replica và không biến thông báo hết hạn thành hàng đợi đáng tin cậy. Bài học này giải thích cơ chế, những gì còn tồn tại sau khi TTL hết hạn, cách cấu hình và những đánh đổi khi triển khai.

## 1. Từ TTL của entity đến câu hỏi “giá trị đã xóa nằm ở đâu?”

Giả sử một ứng dụng lưu phiên đăng nhập theo quy tắc:

```text
Keyspace: sessions
ID:       s-101
Redis key: sessions:s-101
TTL:      120 giây
```

Ở thời điểm mới lưu, Redis có khóa chứa dữ liệu của phiên và thời hạn tồn tại 120 giây. Khi thời gian này kết thúc và Redis thực sự xóa khóa do hết hạn:

```text
Trước khi hết hạn:
  sessions:s-101  --> HASH chứa thông tin phiên

Sau khi hết hạn:
  sessions:s-101  --> không còn tồn tại
```

Nếu ứng dụng chỉ quan tâm việc phiên không còn được truy cập thì hành vi đó có thể đã đủ. Nhưng nhiều hệ thống còn muốn biết:

- Phiên nào vừa hết hạn để ghi log/metric?
- Phiên thuộc người dùng nào để phát tín hiệu cập nhật trạng thái?
- Entity có những thuộc tính nào tại thời điểm được lưu gần nhất?
- Những cấu trúc phụ hoặc chỉ mục của Repository cần dọn dẹp ra sao?

Thông báo hết hạn từ Redis bản thân nó chủ yếu mang **tên khóa hết hạn**, không gửi lại toàn bộ nội dung Redis Hash đã bị xóa. Vì vậy, sau khi nhận thông báo, ứng dụng không thể đơn giản `HGETALL sessions:s-101` rồi mong lấy được dữ liệu: khóa đã biến mất.

Spring Data Redis Repository có thể lưu thêm một bản sao để cung cấp **giá trị đã hết hạn** cho ứng dụng trong khoảng thời gian xử lý sự kiện.

## 2. Phân biệt ba khái niệm dễ bị gọi chung là “bản sao”

| Khái niệm | Ai quản lý? | Mục đích | Có thay thế khóa entity chính không? |
|---|---|---|---|
| **Entity chính** | Spring Data Redis Repository và Redis | Lưu dữ liệu đang còn hiệu lực, ví dụ `sessions:s-101` | Chính là dữ liệu được Repository đọc theo ID |
| **Shadow copy / phantom copy** | Spring Data Redis Repository | Giữ bản sao giá trị trong một khoảng thời gian bổ sung để phát sự kiện hết hạn có payload | Không; chỉ hỗ trợ vòng đời sự kiện |
| **Redis replica** | Redis replication/Redis Cluster | Sao chép trạng thái từ primary nhằm phục vụ khả dụng và vận hành hệ thống | Không; là một node máy chủ sao chép dữ liệu Redis |

**Shadow copy là một khóa dữ liệu phụ do framework tạo trong Redis**, không phải một Redis server thứ hai. Nếu Redis có primary và replica, cả khóa chính lẫn khóa shadow (nếu tồn tại) đều là các khóa Redis bình thường và có thể được sao chép theo cơ chế replication của hạ tầng.

Điều này cũng có nghĩa:

- Bật Redis replica **không tự động** giúp `RedisKeyExpiredEvent` lấy lại nội dung khóa chính đã hết hạn.
- Tắt shadow copy **không tắt** Redis replication.
- Shadow copy không phải bản sao lưu dài hạn, không dùng để khôi phục phiên đã hết hạn theo nhu cầu nghiệp vụ.
- Không nên sử dụng khóa shadow như một khóa nghiệp vụ hợp lệ để bỏ qua TTL của entity chính.

## 3. Cơ chế Spring Data Redis tạo bản sao phụ

Khi ứng dụng lưu entity bằng Repository và có **TTL dương**, Spring Data Redis có thể thực hiện các bước logic:

1. Chuyển entity Java thành các field trong Redis Hash chính.
2. Đặt TTL cho khóa chính theo cấu hình entity.
3. Tạo một bản sao phụ chứa giá trị của entity, với thời gian hết hạn muộn hơn khóa chính khoảng **5 phút**.
4. Khi Redis thông báo khóa chính hết hạn, bộ lắng nghe của Spring Data Redis cố gắng đọc bản sao phụ và phát sự kiện Spring mang giá trị entity đã hết hạn.

Ví dụ thời gian:

```text
T = 0 giây
  Repository.save(session id=s-101, TTL=120s)
  |
  |-- khóa chính: sessions:s-101
  |       hết hạn sau 120 giây
  |
  |-- khóa shadow: bản sao nội bộ của session
          hết hạn dự kiến sau 120 + 300 = 420 giây

T ~ 120 giây
  Redis xóa khóa chính và phát thông báo expired
  |
  v
  Spring Data Redis nhận thông báo
  |
  +-- xác định khóa/ID đã hết hạn
  +-- đọc shadow copy nếu còn tồn tại
  +-- phát RedisKeyExpiredEvent với giá trị entity (nếu có)

T ~ 420 giây
  shadow copy cũng hết hạn; không còn payload để phục hồi từ bản sao này
```

**Năm phút bổ sung** là khoảng đệm cho việc đọc payload sau khi khóa chính hết hạn, không phải lời hứa rằng mọi sự kiện đều được xử lý trong năm phút. Thời điểm Redis phát sự kiện hết hạn có thể trễ so với mốc TTL về 0, và thông báo qua Pub/Sub có thể bị bỏ lỡ. Nếu shadow copy đã hết hạn trước lúc listener đọc, nó không còn cung cấp giá trị.

### Bản sao phụ có tên khóa nào?

Spring Data Redis sử dụng tên khóa nội bộ để lưu bản sao, thường có cấu trúc liên quan đến khóa entity gốc và một hậu tố nội bộ. Không nên xây logic ứng dụng bằng cách đoán hoặc hard-code tên khóa shadow:

- Tên cụ thể và cách mã hóa phụ thuộc vào cách framework triển khai và phiên bản đang chạy.
- Khóa shadow không phải khóa entity thông thường để trả về từ `findById()`.
- Khi dùng `SCAN` theo tiền tố keyspace, có thể quan sát thấy các khóa phụ khác với HASH entity chính.
- Nếu cần debug, phải xác định `TYPE`, `TTL` và nội dung theo cách ánh xạ đang dùng; không đánh đồng mọi khóa cùng prefix là entity đang có hiệu lực.

Mục tiêu của bản sao là **phục vụ sự kiện**, không tạo một API truy vấn thứ hai cho dữ liệu đã hết hạn.

## 4. Redis thông báo hết hạn như thế nào?

Redis hỗ trợ **keyspace notifications**. Đối với sự kiện hết hạn, Redis có thể công bố thông báo qua cơ chế **Pub/Sub** khi một khóa thực sự bị xóa do hết hạn.

Ví dụ với database 0, kênh sự kiện thường có dạng:

```text
__keyevent@0__:expired
```

Nội dung thông báo là **tên khóa đã hết hạn**. Nó không phải snapshot của toàn bộ Hash hay dữ liệu Java:

```text
Redis key expires
       |
       v
Pub/Sub notification:
  channel = __keyevent@0__:expired
  payload = sessions:s-101
       |
       v
Spring Data Redis key expiration listener
       |
       +--> biết khóa nào đã hết hạn
       +--> đọc shadow copy để lấy dữ liệu entity nếu có
       |
       v
Spring ApplicationEventPublisher
       |
       v
RedisKeyExpiredEvent
       |
       v
@EventListener trong ứng dụng
```

Sự kiện `expired` không nhất thiết được phát **đúng tại mili giây TTL chuyển thành 0**. Redis có cơ chế xóa khóa hết hạn theo truy cập và theo chu kỳ; thời điểm thực tế của sự kiện gắn với lúc Redis xóa khóa. Không dùng timestamp của event như một đồng hồ chính xác tuyệt đối cho nghiệp vụ.

Pub/Sub cũng **không lưu sự kiện để consumer đọc lại**. Nếu listener chưa đăng ký, ứng dụng đang tắt hoặc đường kết nối bị gián đoạn, sự kiện phát trong khoảng đó có thể mất. Shadow copy còn tồn tại trong Redis cũng **không tự tạo lại một sự kiện Pub/Sub đã bỏ lỡ**.

## 5. Ví dụ khai báo TTL trên entity

Xây dựng một entity phiên đăng nhập được quản lý bằng Redis Repository:

```java
package example.session;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "sessions", timeToLive = 120)
public class LoginSession {

    @Id
    private String id;

    private String userId;

    private String device;

    public LoginSession() {
    }

    public LoginSession(String id, String userId, String device) {
        this.id = id;
        this.userId = userId;
        this.device = device;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getUserId() {
        return userId;
    }

    public void setUserId(String userId) {
        this.userId = userId;
    }

    public String getDevice() {
        return device;
    }

    public void setDevice(String device) {
        this.device = device;
    }
}
```

Annotation `@RedisHash(value = "sessions", timeToLive = 120)` khai báo keyspace `sessions` và TTL mặc định **120 giây**. Repository:

```java
package example.session;

import org.springframework.data.repository.CrudRepository;

public interface LoginSessionRepository
        extends CrudRepository<LoginSession, String> {
}
```

Sử dụng:

```java
LoginSession session = new LoginSession(
        "s-101",
        "user-42",
        "mobile"
);

repository.save(session);

// Khi khóa chính chưa hết hạn:
LoginSession loaded = repository.findById("s-101")
        .orElseThrow();
```

Khi khóa chính `sessions:s-101` đã bị Redis xóa do hết hạn, `repository.findById("s-101")` sẽ không còn trả về entity đó theo cách đọc thông thường. Nếu shadow copy được bật, nó chỉ giúp **đường xử lý sự kiện** khôi phục giá trị ở thời điểm thích hợp; nó không khiến `findById()` tiếp tục trả phiên đã hết hạn.

### TTL động qua `@TimeToLive`

Không phải mọi session đều cần chung 120 giây. Spring Data Redis cũng hỗ trợ TTL trên một thuộc tính:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("sessions")
public class LoginSession {
    @Id
    private String id;

    private String userId;

    @TimeToLive
    private Long ttlSeconds;

    // Constructor, getter và setter cho các thuộc tính.
}
```

Khi lưu với `ttlSeconds = 90L`, khóa chính được thiết lập TTL theo giá trị dương này. Shadow copy, nếu bật, có thời hạn kéo dài thêm khoảng năm phút so với thời điểm hết hạn của khóa chính. Khi entity được nạp lại, giá trị TTL hiển thị có thể là **thời gian còn lại** mà Redis báo chứ không phải giá trị ban đầu khi tạo entity.

Hai cách `@RedisHash(timeToLive = ...)` và `@TimeToLive` cùng phục vụ TTL của entity. Không nên định nghĩa nhiều nguồn TTL mâu thuẫn cho cùng entity mà chưa xác định thứ tự ưu tiên theo phiên bản Spring Data sử dụng.

## 6. Đọc giá trị entity từ `RedisKeyExpiredEvent`

Spring Data Redis có thể chuyển thông báo hết hạn của Redis thành một sự kiện trong **Spring ApplicationContext**:

```java
import org.springframework.context.event.EventListener;
import org.springframework.data.redis.core.RedisKeyExpiredEvent;
import org.springframework.stereotype.Component;

@Component
public class SessionExpirationListener {

    @EventListener
    public void onExpired(RedisKeyExpiredEvent<?> event) {
        Object expiredValue = event.getValue();

        if (expiredValue instanceof LoginSession session) {
            System.out.printf(
                    "Session expired: id=%s, user=%s%n",
                    session.getId(),
                    session.getUserId());
        }
    }
}
```

Ở ví dụ này:

- `RedisKeyExpiredEvent<?>` là sự kiện Spring Data Redis phát khi tiếp nhận thông tin hết hạn của một entity được Repository quản lý.
- `event.getValue()` là nội dung entity **nếu framework đọc được bản sao phụ** và giải mã thành công.
- Khi có payload, listener có thể đọc các thuộc tính cần thiết như `id` và `userId` mà không phải truy vấn khóa chính đã bị xóa.
- Khi **không có payload** (chẳng hạn đã tắt shadow copy), `getValue()` có thể bằng `null`; listener phải xử lý tình huống này.

Trường hợp ứng dụng quản lý nhiều kiểu entity trong cùng Redis, dùng kiểm tra `instanceof` giúp xác định loại payload phù hợp. Trong code production, nên ghi log phù hợp với yêu cầu bảo mật; ví dụ chỉ in thông tin nhận diện tối thiểu và không ghi token, secret hoặc dữ liệu riêng tư của session.

### Khi chỉ cần biết ID, có cần bản sao phụ không?

Không nhất thiết. Một thông báo Redis về khóa hết hạn đã mang tên khóa; sự kiện của Spring Data Redis còn có thông tin nhận diện khóa/ID theo API. Nếu yêu cầu chỉ là đo số session hết hạn hoặc ghi nhận định danh, ứng dụng có thể thiết kế listener dựa trên thông tin khóa và cấu hình **không giữ bản sao toàn bộ entity**.

Tuy nhiên, code phía nhận phải rõ ràng: khi shadow copy tắt, **không được truy cập `event.getValue().get...` mà không kiểm tra null**. Đồng thời, nhu cầu xử lý thông qua event vẫn chịu giới hạn độ tin cậy của Redis Pub/Sub.

## 7. Cấu hình bật hoặc tắt bản sao phụ

Với Spring Data Redis Repository, shadow copy thường được bật theo mặc định. Ứng dụng có thể chọn tắt thông qua `@EnableRedisRepositories`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisKeyValueAdapter;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
        enableKeyspaceEvents =
                RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP,
        shadowCopy = RedisKeyValueAdapter.ShadowCopy.OFF
)
public class RedisRepositoryConfiguration {
}
```

Ở cấu hình minh họa:

- `enableKeyspaceEvents = ON_STARTUP` yêu cầu thành phần lắng nghe keyspace events khởi động cùng ứng dụng. Đây là lựa chọn rõ ràng khi ứng dụng cần quan sát sự kiện ngay sau khi khởi động, thay vì chờ phát sinh thao tác có TTL theo hành vi kích hoạt của cấu hình khác.
- `shadowCopy = OFF` yêu cầu không giữ bản sao phụ chỉ để đưa nội dung entity vào thông báo hết hạn.
- Khi một entity hết hạn và notification được nhận, sự kiện có thể vẫn được phát nhưng **`getValue()` không có entity đã hết hạn**.

Muốn nhận payload đầy đủ, không cấu hình `ShadowCopy.OFF` hoặc chọn chế độ bật tương ứng của phiên bản Spring Data Redis đang dùng. Không xem việc bật shadow copy là đủ để bảo đảm nhận sự kiện: ứng dụng còn phải thực sự có listener và cấu hình nhận Redis keyspace notifications hoạt động.

### Không nhầm hai nhóm cấu hình

| Cấu hình | Tác động trực tiếp | Có bảo đảm nhận đầy đủ sự kiện không? |
|---|---|---|
| TTL trên entity | Quy định khi nào khóa chính đủ điều kiện hết hạn | Không |
| `shadowCopy` | Quy định có giữ thêm bản sao giá trị entity để cung cấp cho event không | Không |
| `enableKeyspaceEvents` | Điều khiển thời điểm/cách khởi tạo listener của Redis Repository | Không |
| Redis `notify-keyspace-events` | Cho phép Redis phát loại notification cần lắng nghe | Không; Pub/Sub vẫn có thể mất |
| `@EventListener` | Xử lý sự kiện đã được Spring phát bên trong ứng dụng | Không tự khôi phục sự kiện phát lúc ứng dụng offline |

Vì thế, **cấu hình shadow copy là lựa chọn về khả năng khôi phục payload**, còn **cấu hình keyspace notifications/listener là điều kiện để quan sát sự kiện**.

## 8. Redis keyspace notifications cần được cấu hình phù hợp

Để Redis phát sự kiện khi một khóa hết hạn, cần có thiết lập `notify-keyspace-events` phù hợp. Với kiểu thông báo **keyevent** cho **expired**, các ký hiệu liên quan thường là:

```text
E = keyevent notifications
x = expired events
```

Trong môi trường Redis tự quản lý phục vụ thực hành, có thể quan sát cấu hình:

```bash
redis-cli CONFIG GET notify-keyspace-events
```

Để thử nghiệm, quản trị viên có thể cấu hình Redis cho các event cần thiết, chẳng hạn:

```bash
redis-cli CONFIG SET notify-keyspace-events Ex
```

Sau đó có thể quan sát channel bằng một kết nối Redis CLI:

```bash
redis-cli PSUBSCRIBE '__keyevent@0__:expired'
```

Trên cửa sổ khác, dùng Repository để lưu entity có TTL. Khi Redis thực sự xóa khóa chính do hết hạn, subscriber có thể thấy tên khóa. Những câu lệnh này minh họa **Redis Pub/Sub**, không trực tiếp hiển thị đối tượng Java của `RedisKeyExpiredEvent`; đối tượng Java chỉ xuất hiện trong ứng dụng khi listener Spring nhận và xử lý sự kiện.

### Các hạn chế cần chú ý

- Một số dịch vụ Redis được quản lý hạn chế hoặc không cho dùng `CONFIG SET` từ ứng dụng. Spring Data Redis có tùy chọn không tự cấu hình keyspace notifications cho server; khi sử dụng nó, quản trị hạ tầng phải cung cấp cấu hình phù hợp.
- Cấu hình `notify-keyspace-events` có thể ảnh hưởng các loại notification khác mà ứng dụng đang dùng; không ghi đè tùy tiện cấu hình production chỉ để thử bài học.
- Redis Cluster có nhiều primary; việc thiết lập và nhận event cần được xem xét theo phạm vi những node phát ra notification. Không giả định chỉ subscribe một node là đã quan sát mọi khóa trong cả cluster.
- Phiên bản/configuration của Spring Data Redis có thể bật listener khi ứng dụng khởi động hoặc theo nhu cầu. Nếu listener được khởi tạo muộn, sự kiện xảy ra trước đó có thể đã mất.

Spring Data có thể chủ động cấu hình keyspace notification phù hợp khi được phép. Ở hạ tầng không có quyền sửa cấu hình Redis, cần phối hợp với cấu hình server và cách Spring lắng nghe, thay vì suy luận rằng chỉ cần thêm annotation TTL là tự động có event đầy đủ.

## 9. Quan sát vòng đời khóa chính và bản sao phụ

Giả sử dùng `LoginSession` ở phần trên và cấu hình shadow copy bật.

### Bước 1: Lưu phiên qua Repository

```java
repository.save(new LoginSession(
        "lab-01",
        "user-lab",
        "browser"
));
```

### Bước 2: Kiểm tra TTL của khóa chính

```bash
redis-cli TYPE sessions:lab-01
redis-cli TTL sessions:lab-01
redis-cli HGETALL sessions:lab-01
```

Ngay sau khi lưu, TTL của khóa chính sẽ gần thời lượng cấu hình, ví dụ khoảng 120 giây. `TTL` trả thời gian theo giây, nên giá trị quan sát có thể nhỏ hơn con số cấu hình vì thời gian đã trôi qua. Dùng `PTTL` nếu cần độ phân giải mili giây.

### Bước 3: Quan sát các khóa phụ

Trong môi trường thử nghiệm:

```bash
redis-cli SCAN 0 MATCH 'sessions*' COUNT 100
```

Quét tiếp theo cursor Redis trả về đến khi cursor là `0`. Kết quả có thể gồm khóa chính, keyspace SET, khóa shadow và các metadata khác. **Không có quy tắc rằng mọi khóa cùng tiền tố đều là entity có thể đăng nhập**. Dùng `TYPE` và `TTL` để phân biệt các khóa quan sát được.

Không dùng `KEYS sessions*` trong production có dữ liệu lớn. Nếu chạy Redis Cluster, một lần `SCAN` trên một node cũng chưa bao phủ mọi primary.

### Bước 4: Chờ thông báo hết hạn qua Redis và Spring

Khi Redis thực sự xóa `sessions:lab-01`, một subscriber Pub/Sub đang hoạt động có thể thấy:

```text
channel: __keyevent@0__:expired
message: sessions:lab-01
```

Đồng thời, nếu listener Spring Data Redis hoạt động và shadow copy được bật, `SessionExpirationListener` có thể nhận giá trị entity đã hết hạn. Sau thời điểm này:

```bash
redis-cli EXISTS sessions:lab-01
```

thường trả `0`. Điều đó hoàn toàn bình thường, dù event bên Spring có thể chứa đối tượng `LoginSession`. Nội dung sự kiện được lấy từ **bản sao phụ**, không phải bằng cách hồi sinh khóa chính.

### Bước 5: So sánh với chế độ không giữ shadow copy

Chạy lại thí nghiệm trên môi trường riêng với:

```java
@EnableRedisRepositories(
        enableKeyspaceEvents =
                RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP,
        shadowCopy = RedisKeyValueAdapter.ShadowCopy.OFF
)
```

Quan sát:

- Khóa chính vẫn được đặt TTL và hết hạn theo Redis.
- Khi notification tới nơi và được xử lý, ứng dụng vẫn có thể nhận sự kiện hết hạn.
- `event.getValue()` có thể là `null` vì không có bản sao payload để đọc.
- Redis không cần giữ thêm một bản sao entity chỉ để phát event có giá trị đầy đủ.

Thí nghiệm này cần tách riêng cấu hình/khóa thử nghiệm để tránh dữ liệu và listener từ lần chạy trước gây nhầm lẫn. Giá trị nhận được tùy thời điểm Redis phát thông báo và trạng thái kết nối; không coi việc “không thấy event trong một lần chạy” là bằng chứng shadow copy bị lỗi.

## 10. Lợi ích của bản sao phụ

### 10.1. Lấy lại giá trị sau khi khóa chính biến mất

Ưu điểm trực tiếp nhất là listener có thể biết **entity mang những thuộc tính gì** tại thời điểm bản sao được lưu/cập nhật qua Repository. Ví dụ:

```text
Thông báo Redis:
  "sessions:s-101"

Event Spring Data (khi có shadow payload):
  LoginSession {
    id: "s-101",
    userId: "user-42",
    device: "mobile"
  }
```

Điều này giúp viết xử lý ứng dụng như cập nhật thống kê số phiên theo thiết bị, ghi nhận dấu vết kiểm toán phù hợp hoặc phát tín hiệu làm mới giao diện, khi nghiệp vụ thật sự cần những field đó.

### 10.2. Giảm phụ thuộc vào khả năng đọc khóa đã hết hạn

Không thể sửa bằng cách “nhanh chóng đọc Hash ngay khi nhận event” vì Redis đã xóa khóa để phát thông báo `expired`. Bản sao tạo trước thời điểm hết hạn giải quyết được giới hạn này trong khoảng thời gian nó còn tồn tại.

### 10.3. Hỗ trợ luồng xử lý vòng đời ở tầng Repository

Spring Data Redis có cơ chế quản lý chỉ mục và các cấu trúc liên quan đến entity; thông tin về sự kiện hết hạn có thể được dùng trong các bước dọn dẹp và đồng bộ metadata. Bản sao phụ bổ sung nội dung entity cho luồng sự kiện, nhưng việc giữ index sạch còn phụ thuộc vào listener và cơ chế cleanup thực tế của phiên bản/cấu hình.

Không nên suy ra rằng *có shadow copy* thì *mọi chỉ mục sẽ được dọn chính xác*, nhất là khi ứng dụng offline hoặc sự kiện Pub/Sub bị bỏ lỡ.

## 11. Chi phí và đánh đổi: bản sao phụ không miễn phí

### Bộ nhớ

Nếu mỗi session có TTL ngắn và ứng dụng tạo rất nhiều session, Redis có thể chứa đồng thời **khóa chính và khóa shadow** của cùng entity trong phần lớn thời gian tồn tại của khóa chính. Sau khi khóa chính hết hạn, shadow còn tồn tại thêm khoảng 5 phút.

Một cách ước lượng sơ bộ:

```text
Mỗi phút tạo 10.000 session mới
Mỗi session sống 2 phút
Shadow sống thêm khoảng 5 phút

Số session chính ổn định xấp xỉ:
  10.000 x 2 = 20.000 khóa chính

Số shadow ổn định xấp xỉ:
  10.000 x (2 + 5) = 70.000 khóa shadow
```

Ví dụ chỉ để minh họa **số lượng khóa** khi tốc độ tạo đều và mỗi entity có một shadow copy. Bộ nhớ thực tế còn phụ thuộc kích thước HASH, serializer, cấu trúc dữ liệu Redis, metadata, eviction policy, pattern ghi/cập nhật và thời điểm expire. Không lấy các con số này làm dự báo RAM chính xác nếu chưa đo.

### Lưu giữ dữ liệu sau TTL nghiệp vụ

Khi TTL của `sessions:s-101` đã hết, nghiệp vụ có thể xem phiên là vô hiệu, nhưng **nội dung của entity vẫn có thể còn trong shadow copy thêm năm phút**. Nếu entity mang token, thông tin cá nhân hoặc giá trị nhạy cảm, cần xem xét chính sách lưu giữ dữ liệu:

- Không đưa secret thô vào entity được giữ bản sao nếu không thật sự cần.
- Chỉ lưu những thuộc tính cần thiết để xử lý sự kiện.
- Cân nhắc `shadowCopy = OFF` khi event chỉ cần khóa/ID.
- Đừng mô tả TTL khóa chính là “đã xóa mọi bản sao vật lý ngay lập tức”.

Tắt shadow copy chỉ tắt bản sao phụ do Spring Data Redis Repository tạo để phục vụ expiration event. Nó **không** là cam kết xóa mọi dữ liệu khỏi Redis replication, snapshot, AOF hoặc backup hạ tầng.

### Tải vận hành

Khi lưu entity có TTL, việc tạo khóa phụ kéo theo thêm thao tác ghi, đặt TTL và dữ liệu cần quản lý. Trong Redis Cluster, khóa chính và khóa nội bộ còn có thể có vị trí hash slot khác nhau tùy quy tắc đặt khóa. Bật shadow copy cần được tính vào tải ghi, số lượng khóa và ngân sách bộ nhớ của ứng dụng.

### Độ tin cậy sự kiện

Đây là đánh đổi quan trọng nhất: giữ một bản sao đẹp và đầy đủ **không khiến Pub/Sub trở nên bền vững**. Nếu sự kiện không được chuyển đến consumer, bản sao có thể tự hết hạn mà không bao giờ được sử dụng.

## 12. Điều gì xảy ra trong các tình huống lỗi?

| Tình huống | Khóa chính | Shadow copy | Sự kiện nhận được |
|---|---|---|---|
| TTL dương, listener hoạt động, notifications đúng | Hết hạn theo Redis | Có thể còn khi event đến | Có thể chứa entity đầy đủ |
| Shadow copy bị tắt | Vẫn hết hạn | Không tạo vì mục đích payload event | Event nhận được có thể có `value = null` |
| Ứng dụng tắt đúng lúc khóa hết hạn | Redis vẫn xóa khóa | Có thể còn thêm một thời gian | Event Pub/Sub trong lúc offline có thể mất |
| Listener được khởi tạo sau khi event đã xảy ra | Khóa chính đã mất | Có thể còn | Không tự phát lại thông báo cũ |
| Redis xóa khóa chính trễ so với TTL danh nghĩa | Không còn hợp lệ khi TTL đã qua; xóa thực tế có thể muộn | Có thể tiến gần mốc hết hạn của shadow | Event có thể đến muộn |
| Bản sao phụ bị xóa hoặc hết hạn trước khi listener đọc | Khóa chính đã mất | Không còn | Payload có thể trống, tùy cơ chế xử lý |
| Dùng `DEL` thủ công trước khi TTL hết | Khóa bị xóa chủ động | Không có bảo đảm dọn shadow theo đường ngoài Repository | Không phải sự kiện `expired`; không giả định có `RedisKeyExpiredEvent` như TTL |
| Dùng `EXPIRE` thủ công sau khi đã lưu | TTL khóa chính thay đổi | TTL shadow có thể không được cập nhật cùng | Có nguy cơ payload không còn hoặc lưu lâu hơn cần thiết |

### Vì sao `DEL` không đồng nghĩa với `expired`?

Redis phân biệt khóa bị xóa bởi lệnh `DEL` hoặc `UNLINK` và khóa bị xóa vì hết hạn. Notification cho xóa chủ động và cho expiration là những loại sự kiện khác nhau. Nếu nghiệp vụ cần phản ứng với **mọi hình thức kết thúc phiên**, chỉ lắng nghe `expired` là không đủ; cần thiết kế đường xóa chủ động và đường TTL cùng cập nhật trạng thái nghiệp vụ theo quy tắc rõ ràng.

### Nếu TTL được thay đổi nhiều lần?

Ví dụ application gia hạn một session từ 120 giây thành 600 giây bằng `EXPIRE` gọi ngoài Repository. Framework không nhất thiết cập nhật bản sao phụ của lần lưu trước. Shadow có thể hết hạn sớm hơn thời điểm cuối cùng của khóa chính, hoặc giữ dữ liệu lâu hơn mốc mới nếu TTL bị rút ngắn.

Với entity thuộc Repository, thay đổi TTL theo API/mapping mà framework hỗ trợ và quan sát cả vòng đời dữ liệu thay vì giả định sửa TTL của một khóa là đã điều chỉnh mọi khóa nội bộ.

## 13. Liên hệ với secondary index và dọn dẹp metadata

Một entity `@RedisHash("sessions")` có thể dùng thêm `@Indexed`:

```java
import org.springframework.data.redis.core.index.Indexed;

@RedisHash(value = "sessions", timeToLive = 120)
public class LoginSession {
    @Id
    private String id;

    @Indexed
    private String userId;

    // Các thuộc tính khác, constructor, getter/setter.
}
```

Khi Repository save entity, ngoài Hash và shadow copy còn có thể tồn tại secondary index hỗ trợ tìm session theo `userId`. Sau khi Hash hết hạn, liên kết trong index **cũng cần được dọn** để không giữ tham chiếu đến entity đã mất.

Sơ đồ vòng đời logic:

```text
Repository.save(entity TTL)
   |
   +--> Hash chính có TTL
   +--> Shadow copy (nếu bật)
   +--> Index / metadata hỗ trợ truy vấn

Hash chính hết hạn
   |
   +--> Redis Pub/Sub expired event
              |
              v
          Repository listener
              |
              +--> phát RedisKeyExpiredEvent
              +--> xử lý vòng đời index/metadata theo cơ chế hỗ trợ
```

Khi notification bị mất, **việc dọn sạch các tham chiếu index có thể bị ảnh hưởng**. Đừng phụ thuộc duy nhất vào một listener đang chạy để bảo đảm hệ thống luôn có chỉ mục hoàn toàn nhất quán. Với dữ liệu quan trọng, cần quan sát và có chiến lược đối soát các entity hết hạn hoặc các tham chiếu không còn hợp lệ.

**Shadow copy và index là hai nhóm khóa phụ khác nhau.** Shadow giữ **giá trị** phục vụ event; secondary index giúp **tra cứu** entity theo thuộc tính. Tắt shadow copy không có nghĩa “tắt tất cả chỉ mục”, và thêm `@Indexed` không tự biến event Redis thành thông báo chứa đầy đủ giá trị.

## 14. Khi nào nên giữ shadow copy, khi nào nên tắt?

| Nhu cầu | Lựa chọn cân nhắc | Lý do |
|---|---|---|
Ghi log ID của entity hết hạn | Có thể tắt shadow copy | Tên khóa/ID thường đủ, giảm việc giữ bản sao toàn entity |
Đọc `userId`, loại thiết bị hoặc thuộc tính entity tại lúc hết hạn | Giữ shadow copy nếu sự kiện best-effort là đủ | Listener có thể nhận payload ngay cả khi Hash chính đã bị xóa |
Hàng triệu entity TTL ngắn, mỗi entity lớn | Cân nhắc tắt hoặc thu gọn entity | Bản sao phụ có thể tạo tải bộ nhớ đáng kể |
Entity chứa token/secret cần giảm thời gian tồn tại vật lý | Cân nhắc tắt shadow copy | Tránh giữ thêm payload sau thời hạn khóa chính |
Yêu cầu xử lý hết hạn chắc chắn, có thể replay sau downtime | Cần thiết kế sự kiện bền vững riêng | Redis Pub/Sub + shadow copy không bảo đảm giao hàng |
Yêu cầu dọn secondary index khi TTL hết | Cấu hình và quan sát expiration handling, có đối soát | Shadow là hỗ trợ payload; độ đúng index còn phụ thuộc xử lý event |

Nếu nghiệp vụ **phải** thực hiện một tác vụ chính xác một lần khi session hết hạn, ví dụ ghi nhận khoản phí, chuyển tiền, thực hiện xóa dữ liệu tuân thủ SLA hay chuyển trạng thái đơn hàng, không nên đặt tính đúng đắn duy nhất lên `RedisKeyExpiredEvent`. Có thể cần một nguồn trạng thái bền vững, tác vụ theo lịch có khả năng retry, hàng đợi/bảng outbox hoặc một cơ chế phát sự kiện có xác nhận và tính idempotent. Những thành phần này phục vụ yêu cầu đảm bảo nghiệp vụ mà Pub/Sub không cung cấp.

## 15. Bài tập tư duy

**Câu 1.** Session có TTL 60 giây; shadow copy được bật. Khi session chính hết hạn, ứng dụng có thể còn đọc được nó bằng `repository.findById()` không?

**Đáp án:** Không. `findById()` nhắm đến khóa entity chính. Shadow chỉ phục vụ cơ chế lấy giá trị cho sự kiện hết hạn, không làm session còn hiệu lực.

**Câu 2.** Vì sao sự kiện Redis về một Hash đã hết hạn không tự mang các field `userId` và `device`?

**Đáp án:** Notification của Redis chứa tên khóa bị hết hạn, còn Hash gốc đã bị xóa. Framework cần bản sao phụ nếu muốn khôi phục nội dung entity cho Spring event.

**Câu 3.** Redis replica có giúp thay thế shadow copy không?

**Đáp án:** Không. Replica sao chép dữ liệu của server Redis, bao gồm cả việc khóa hết hạn bị xóa; shadow copy là khóa phụ do Spring Data tạo để giữ payload sự kiện.

**Câu 4.** Nếu bật shadow copy nhưng ứng dụng tắt lúc Redis phát `expired`, sự kiện có tự chạy lại khi ứng dụng khởi động không?

**Đáp án:** Không có bảo đảm. Redis Pub/Sub không lưu lịch sử sự kiện để replay; shadow copy còn tồn tại cũng không tự phát lại notification đã mất.

**Câu 5.** Vì sao ứng dụng cần kiểm tra `event.getValue() == null`?

**Đáp án:** Shadow có thể bị tắt, đã hết hạn hoặc không đọc được; khi đó event không có payload entity. Code phải xử lý trường hợp thiếu giá trị.

**Câu 6.** Nếu mỗi phút tạo 10.000 entity, TTL chính là 2 phút và shadow sống thêm 5 phút, lớp shadow có thể tạo ra số khóa lớn hay nhỏ?

**Đáp án:** Với tốc độ đều và một shadow mỗi entity, mức ổn định sơ bộ vào khoảng 70.000 khóa shadow, so với 20.000 khóa chính; cần đo kích thước thực tế để ước lượng RAM.

**Câu 7.** Tắt shadow copy có đồng nghĩa tắt TTL hoặc tắt keyspace notifications không?

**Đáp án:** Không. TTL, cơ chế phát/nhận notification và bản sao phục vụ payload là ba vấn đề cấu hình khác nhau.

**Câu 8.** Xóa session bằng `DEL` có nhất thiết tạo `RedisKeyExpiredEvent` giống như khi TTL hết không?

**Đáp án:** Không. Xóa chủ động và xóa do expiration là hai loại nguyên nhân/sự kiện Redis khác nhau; cần thiết kế riêng nếu muốn theo dõi cả hai.

## 16. Ghi nhớ khi áp dụng

- **Khóa chính** là dữ liệu đang còn hiệu lực; TTL của nó quyết định khi nào Redis có thể xóa entity.
- **Bản sao phụ** được Spring Data Redis tạo khi lưu entity có TTL dương (nếu shadow copy bật), thường có thời gian hết hạn muộn hơn khoảng **5 phút** để hỗ trợ khôi phục payload của sự kiện.
- **Redis notification** báo khóa nào đã hết hạn; **Spring Data Redis** đọc shadow copy để tạo `RedisKeyExpiredEvent` có giá trị entity nếu còn có thể.
- **`shadowCopy = OFF`** giảm việc lưu thêm payload và khiến listener phải chấp nhận giá trị sự kiện có thể là `null`.
- **Redis Pub/Sub là best-effort**, không lưu lịch sử để phát lại. Shadow copy không khắc phục được mất event khi listener offline.
- **Tải bộ nhớ, dữ liệu nhạy cảm, TTL thay đổi ngoài Repository và dọn secondary index** là những lý do cần cân nhắc cấu hình trước khi áp dụng ở quy mô lớn.

Một thiết kế đúng cần tách ba câu hỏi: *Khi nào khóa chính hết hạn? Ứng dụng có thể đọc lại dữ liệu gì khi nhận thông báo? Và điều gì xảy ra nếu thông báo không đến?* Shadow copy giải quyết chủ yếu câu hỏi thứ hai. Hai câu hỏi còn lại thuộc về TTL của Redis và thiết kế độ tin cậy của toàn hệ thống.

## Tài liệu tham khảo

- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html): thời gian sống của entity, phantom/shadow copy, `RedisKeyExpiredEvent` và cách tắt bản sao.
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): mô hình lưu entity và quản lý keyspace.
- [Spring Data Redis — Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html): các secondary index có thể cần dọn theo vòng đời entity.
- [Redis — Keyspace Notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/): cấu hình notifications, phân biệt expired/deleted và giới hạn Pub/Sub.
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/): thiết lập TTL và những hành vi liên quan đến hết hạn khóa.
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/): quan sát thời gian sống còn lại của khóa.
- [Redis — PTTL](https://redis.io/docs/latest/commands/pttl/): quan sát TTL theo mili giây.
