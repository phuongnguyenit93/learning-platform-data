# Kiểm thử giao dịch, WATCH, pipeline và Lua

Khi ứng dụng dùng **Spring Data Redis**, việc một lệnh `GET` hoặc `SET` chạy thành công chưa đủ để chứng minh các thao tác có tính nhất quán khi có nhiều client, lỗi mạng hay xử lý đồng thời. Redis có nhiều cơ chế dễ bị nhầm lẫn:

- **`MULTI`/`EXEC`**: xếp hàng nhiều command rồi thực thi tuần tự, không cho command từ client khác xen vào khoảng thực thi `EXEC`.
- **`WATCH`**: thêm điều kiện optimistic locking cho `EXEC`; nếu key được theo dõi đã thay đổi, giao dịch có thể bị hủy trước khi chạy các command đã xếp hàng.
- **Pipeline**: gửi nhiều command mà không chờ phản hồi từng lệnh, giúp giảm chi phí round-trip; **không mặc nhiên tạo transaction**.
- **Lua script**: gom logic đọc–kiểm tra–ghi vào một script thực thi nguyên tử đối với sự xen kẽ command khác trên cùng Redis server, nhưng **không có rollback tự động khi script runtime error**.

Bốn cơ chế giải quyết những vấn đề khác nhau. Vì thế, chiến lược kiểm thử tốt phải chứng minh **trạng thái Redis sau thao tác**, **kết quả khi có tranh chấp**, **hành vi khi lỗi** và **giới hạn của bảo đảm**, thay vì chỉ kiểm tra một method Java không ném exception.

Bài học xây dựng các kịch bản kiểm thử trong ngữ cảnh Spring Boot, `RedisTemplate`, `StringRedisTemplate`, `SessionCallback`, JUnit 5, Testcontainers và Reactor. Các ví dụ có thể điều chỉnh theo version Spring Data Redis và Redis server trong dự án.

## 1. Xác định đúng thứ cần chứng minh

Trước khi viết test, cần mô tả bất biến nghiệp vụ bằng câu có thể kiểm chứng.

Ví dụ một ứng dụng quản lý số điểm:

```text
Key: points:{user-42}
Giá trị ban đầu: 10

Bất biến A:
  Khi chuyển 3 điểm từ ví A sang ví B,
  không được thấy trạng thái chỉ trừ A mà chưa cộng B
  trong khoảng các lệnh của một EXEC.

Bất biến B:
  Nếu hai client cùng cập nhật từ version 10,
  một client phải phát hiện xung đột và không ghi đè kết quả của client kia.

Bất biến C:
  Ghi 1.000 cache entries nhanh không đòi hỏi chúng nguyên tử như một transaction.

Bất biến D:
  Kiểm tra giới hạn rồi tăng counter phải nguyên tử;
  hai request đồng thời không được cùng vượt hạn mức.
```

Bốn bất biến dẫn tới các công cụ khác nhau:

| Mục tiêu | Cơ chế phù hợp để xem xét | Test quan trọng |
|---|---|---|
| Nhóm command không bị command client khác xen giữa lúc `EXEC` | `MULTI`/`EXEC` | Commit, discard, kết quả và lỗi trong transaction |
| Phát hiện cập nhật đồng thời làm thay đổi dữ liệu đã đọc | `WATCH` + `MULTI`/`EXEC` | Xung đột giữa WATCH và EXEC, transaction bị hủy |
| Giảm latency khi gửi nhiều command độc lập | Pipeline | Tất cả kết quả đúng, thứ tự replies, không giả định rollback |
| Đọc–kiểm tra–ghi trong một thao tác Redis | Lua | Kết quả đúng, tranh chấp đồng thời, lỗi script |
| Phối hợp Redis với giao dịch SQL | Transaction synchronization/outbox | Commit/rollback ở SQL và khoảng lỗi sau commit |
| Nhiều key trong Redis Cluster | Cùng hash slot hoặc thiết kế lại | CROSSSLOT, routing/failover |

**Sai lầm phổ biến:** test pipeline thấy 100 lần `SET` thành công rồi đặt tên test `allWritesAreAtomic`. Pipeline chỉ chứng minh việc gửi và nhận replies theo một cơ chế tối ưu I/O, không chứng minh atomicity của cả batch.

## 2. Phân biệt phạm vi bảo đảm trước khi kiểm thử

```text
Một Redis command đơn:
  Lệnh A
  -> được Redis xử lý như một command

MULTI/EXEC:
  MULTI
  QUEUED A
  QUEUED B
  EXEC -> chạy A rồi B mà không có command client khác xen vào

WATCH + MULTI/EXEC:
  WATCH key
  READ current
  ...
  MULTI
  QUEUED SET
  EXEC -> chỉ chạy nếu key WATCH không bị thay đổi

Pipeline:
  gửi A, B, C liên tiếp -> nhận replies
  không mặc nhiên bảo đảm không có command khác xen giữa

Lua:
  EVAL script
  -> logic nhiều lệnh Redis được thực hiện nguyên tử
     đối với command client khác trong lúc script chạy
```

| Thuộc tính | `MULTI/EXEC` | `WATCH + EXEC` | Pipeline | Lua |
|---|---|---|---|---|
| Giảm round-trip? | Có thể tùy cách gửi lệnh | Không phải mục tiêu chính | **Có**, là mục tiêu chính | Có, gom logic server-side |
| Command client khác xen giữa lúc nhóm thực thi? | Không giữa các command thực thi tại `EXEC` | Không nếu EXEC chạy | Có thể | Không trong thời gian script chạy |
| Phát hiện thay đổi giữa đọc và ghi? | Không nếu chỉ MULTI | **Có**, với key được WATCH | Không | Có thể thực hiện kiểm tra trực tiếp trong script |
| Rollback mọi runtime error? | **Không** | **Không** | **Không** | **Không** |
| Yêu cầu cùng Redis connection cho chuỗi điều khiển? | Có | **Có** | Pipeline quản lý connection trong callback | Một lệnh script |
| Có tự commit cùng PostgreSQL/JPA? | Không | Không | Không | Không |
| Khi client timeout sau lệnh ghi, retry chắc chắn an toàn? | Không | Không | Không | Không |

Từ đây, mỗi test nên ghi rõ **điều kiện bắt đầu – hành động – điểm đồng bộ – kết quả Redis kỳ vọng**.

## 3. Môi trường kiểm thử nên độc lập với production

Nên dùng một Redis instance thử nghiệm có thể tái tạo, không chia sẻ với cache/session/queue của môi trường thật.

Một bố cục:

```text
JUnit 5 / Spring Boot integration test
                 |
                 +--> Spring ApplicationContext
                 |        |
                 |        +--> StringRedisTemplate
                 |        +--> RedisConnectionFactory (Lettuce)
                 |
                 +--> Testcontainers Redis
                          |
                          +--> Database 0 của container test
                 |
                 +--> Writer client độc lập cho WATCH conflict
```

Lợi ích của Testcontainers:

- Redis server thật, không phải mock in-memory giả định toàn bộ semantics.
- Test có thể tạo key, WATCH, `MULTI`/`EXEC` và Lua.
- Có thể cấu hình maxmemory, ACL hoặc network fault trên **container riêng**.
- Khi test xong có thể bỏ container mà không ảnh hưởng ứng dụng.

### Dependencies minh họa

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:testcontainers")

    // Chỉ cần nếu viết reactive tests:
    testImplementation("io.projectreactor:reactor-test")
}
```

Các dependency/version có thể đã được Spring Boot BOM quản lý. Không tự thêm nhiều Redis clients nếu starter đã dùng Lettuce; trong test WATCH có thể dùng thêm **một Lettuce connection độc lập** từ cùng dependency hiện có.

### Khởi tạo một Redis test container

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class RedisSemanticsIT {

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port",
                () -> REDIS.getMappedPort(6379));
    }

    // @Autowired StringRedisTemplate redis;
    // Các test cụ thể ở phần dưới.
}
```

Đây là **khung integration test**, không phải một class độc lập có sẵn tất cả test methods. Cần Spring Boot application/configuration trong test scope và Docker/Testcontainers chạy được. Tag image được ghim để tránh một bản `latest` thay đổi không kiểm soát; trong dự án thật nên chọn tag/digest phù hợp với Redis version đang vận hành.

Nếu ứng dụng ở phiên bản Spring Boot dùng property prefix khác, điều chỉnh `@DynamicPropertySource` theo metadata của version đó.

## 4. Cô lập dữ liệu để test không phụ thuộc nhau

Một test tốt không dựa vào key còn sót lại từ lượt trước.

Ví dụ:

```java
String id = java.util.UUID.randomUUID().toString();
String key = "test:redis:tx:" + id;
```

Dùng cùng prefix cho key cùng kịch bản và cleanup có chủ đích:

```java
String base = "test:redis:tx:" + id;
String a = base + ":a";
String b = base + ":b";

try {
    // Arrange / Act / Assert
} finally {
    redis.delete(java.util.List.of(a, b));
}
```

Không nên chạy `FLUSHDB` hoặc `FLUSHALL` trong test nếu Redis còn được chia sẻ với bất kỳ dữ liệu nào ngoài phạm vi test. Với container thật sự dành riêng cho một suite, có thể làm sạch toàn bộ khi container bị hủy, nhưng xóa key theo namespace giúp test dễ chạy song song và dễ kiểm toán hơn.

Cần tránh những lỗi làm test khó tái hiện:

- Dùng `Thread.sleep(100)` để “chờ thread kia chạy” mà không có điểm đồng bộ.
- Dùng cùng key static cho nhiều test chạy song song.
- Không reset timeout/consumer state giữa các kịch bản.
- Assert số mili giây tuyệt đối trên CI có CPU/network dao động.
- Chỉ kiểm tra exception mà không kiểm tra dữ liệu Redis sau lỗi.
- Dùng mock để kiểm chứng semantics chỉ Redis server mới thực thi được.

## 5. Redis transaction: MULTI, EXEC, DISCARD

Redis transaction dùng các lệnh:

```text
MULTI     -> bắt đầu xếp hàng commands
SET a 1   -> QUEUED
SET b 2   -> QUEUED
EXEC      -> thực thi hàng đợi, trả replies
```

Hoặc hủy trước khi thực thi:

```text
MULTI
SET a 1   -> QUEUED
DISCARD   -> bỏ hàng đợi, không chạy SET
```

Các bảo đảm quan trọng:

1. Redis thực thi các commands trong `EXEC` **tuần tự, không có command từ client khác xen giữa**.
2. Trước `EXEC`, các command đang nằm trong hàng đợi, chưa làm thay đổi dữ liệu.
3. `DISCARD` bỏ các command đã được queue trước đó.
4. Redis transaction **không hỗ trợ rollback như SQL** đối với mọi lỗi runtime.
5. Nếu connection bị mất **trước khi EXEC được gửi**, các command đang queue không được commit.
6. Nếu client mất phản hồi trong lúc/ sau khi gửi `EXEC`, kết quả từ góc nhìn client có thể **không chắc chắn**; không tự retry toàn bộ side effects.
7. `WATCH` bổ sung điều kiện ở thời điểm `EXEC`; `MULTI` đơn thuần không kiểm tra data đã bị client khác sửa giữa các lần đọc.

### Thử bằng Redis CLI

```text
SET test:tx:a old
MULTI
SET test:tx:a new
SET test:tx:b second
EXEC
GET test:tx:a
GET test:tx:b
```

Kỳ vọng sau `EXEC`: `test:tx:a = new`, `test:tx:b = second`.

Thử riêng một kịch bản mới:

```text
SET test:tx:a old
MULTI
SET test:tx:a never
DISCARD
GET test:tx:a
```

Kỳ vọng vẫn là `old`. Nên kiểm tra cả **trạng thái trước EXEC** trên một connection độc lập nếu muốn chứng minh command chưa được áp dụng khi vẫn đang queue.

## 6. SessionCallback giữ cùng connection cho transaction

`RedisTemplate` không đảm bảo mọi lời gọi tách rời của Java đều dùng cùng Redis connection. `MULTI`/`EXEC` và `WATCH` là trạng thái gắn với một connection; vì vậy Spring Data Redis cung cấp **`SessionCallback`** để chạy nhóm thao tác trong một session.

Ví dụ trong service/test:

```java
import java.util.List;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class RedisTransactionExamples {

    private final StringRedisTemplate redis;

    public RedisTransactionExamples(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> savePair(String keyA, String keyB) {
        return redis.execute(new SessionCallback<List<Object>>() {

            @Override
            @SuppressWarnings({"rawtypes", "unchecked"})
            public List<Object> execute(RedisOperations operations)
                    throws DataAccessException {

                operations.multi();

                try {
                    operations.opsForValue().set(keyA, "A");
                    operations.opsForValue().set(keyB, "B");
                    return operations.exec();
                } catch (RuntimeException error) {
                    try {
                        operations.discard();
                    } catch (RuntimeException cleanupError) {
                        error.addSuppressed(cleanupError);
                    }
                    throw error;
                }
            }
        });
    }
}
```

Trong các ví dụ Java dùng `SessionCallback`, phần `RedisOperations` raw được giữ gần với mẫu API trong tài liệu Spring Data Redis. Có thể bổ sung wrapper/type-safe helper theo dự án; ở đây mục tiêu là thấy chính xác chuỗi `multi → queued commands → exec`.

`RedisTemplate` deserialize kết quả `exec()` theo serializers phù hợp. Kết quả có thể là `List<Object>` thay vì các giá trị trả trực tiếp của từng lời gọi khi đang nằm trong transaction.

### Test thành công của EXEC

```java
import static org.assertj.core.api.Assertions.assertThat;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.core.StringRedisTemplate;

class TransactionCases {

    @Autowired
    StringRedisTemplate redis;

    @Test
    void execCommitsAllQueuedWrites() {
        String base = "test:tx:" + UUID.randomUUID();
        String keyA = base + ":a";
        String keyB = base + ":b";

        List<Object> replies =
                new RedisTransactionExamples(redis)
                        .savePair(keyA, keyB);

        assertThat(replies).hasSize(2);
        assertThat(redis.opsForValue().get(keyA)).isEqualTo("A");
        assertThat(redis.opsForValue().get(keyB)).isEqualTo("B");

        redis.delete(List.of(keyA, keyB));
    }
}
```

Class test minh họa ở đây cần được chạy trong Spring Test context phù hợp (ví dụ `@SpringBootTest` trên class chứa test), không phải JUnit unit test thuần có thể tự inject `@Autowired`. Khi sử dụng chung một class integration test, có thể đặt các test methods vào `RedisSemanticsIT` ở phần chuẩn bị môi trường.

**Điều cần chứng minh:** không chỉ có `replies`, mà **hai key thật sự chứa giá trị đã kỳ vọng sau EXEC**.

## 7. Test DISCARD và khôi phục connection state

`DISCARD` hủy những command đã được queue nhưng chưa chạy. Test cần kiểm tra cả dữ liệu không thay đổi và session không bị để ở trạng thái transaction.

Ví dụ:

```java
@Test
void discardDoesNotWriteQueuedValue() {
    String key = "test:discard:" + UUID.randomUUID();
    redis.opsForValue().set(key, "before");

    redis.execute(new SessionCallback<Void>() {
        @Override
        @SuppressWarnings({"rawtypes", "unchecked"})
        public Void execute(RedisOperations operations) {
            operations.multi();
            operations.opsForValue().set(key, "should-not-appear");
            operations.discard();
            return null;
        }
    });

    assertThat(redis.opsForValue().get(key))
            .isEqualTo("before");

    // Lệnh mới phải chạy bình thường sau khi DISCARD.
    redis.opsForValue().set(key, "after");
    assertThat(redis.opsForValue().get(key))
            .isEqualTo("after");
}
```

Cần nhấn mạnh: `DISCARD` dùng **trước EXEC** để hủy hàng đợi. Không thể gọi DISCARD sau khi `EXEC` đã thực thi rồi mong Redis đảo ngược kết quả.

### Lỗi giữa MULTI và EXEC

Nếu Java ném exception, command Redis bị timeout hoặc client không nhận được phản hồi giữa `MULTI` và `EXEC`, connection có thể còn ở transaction state. Trong `SessionCallback` nên có cleanup **best-effort** bằng `DISCARD` khi phù hợp, sau đó để lỗi gốc đi tiếp.

Không nên nuốt lỗi cleanup vì nó có thể gợi ý connection đã hỏng; ít nhất giữ nó dưới dạng suppressed exception hoặc log ở tầng kỹ thuật.

Khi mất kết nối trong lúc EXEC, một lần DISCARD sau đó không có tác dụng “thu hồi commit” đã diễn ra. Cần phân biệt **chưa gửi EXEC** và **không nhận được reply của EXEC**.

## 8. Test lỗi command trong transaction: đừng giả định rollback toàn bộ

Một khác biệt quan trọng so với SQL là Redis không tự rollback các command đã thành công khi một command khác lỗi runtime trong `EXEC`.

Ví dụ bằng Redis CLI trong môi trường lab:

```text
SET test:wrongtype "hello"
MULTI
SET test:tx:ok "written"
LPUSH test:wrongtype "not-a-list"
EXEC
GET test:tx:ok
GET test:wrongtype
```

Ở `EXEC`, `LPUSH` trên String có thể trả `WRONGTYPE`, nhưng `SET test:tx:ok written` đã được thực hiện thành công. Vì vậy sau EXEC, `GET test:tx:ok` vẫn có thể là `written`.

Cần phân biệt:

- **Lỗi phát hiện khi queue command** (ví dụ cú pháp sai theo giao thức): Redis có thể đánh dấu transaction lỗi và `EXEC` từ chối thực thi hàng đợi.
- **Lỗi runtime khi EXEC chạy** (ví dụ WRONGTYPE): những command khác đã chạy không được rollback tự động.
- **WATCH conflict**: `EXEC` trả nil/null và **không chạy hàng đợi**.
- **DISCARD trước EXEC**: hàng đợi bị bỏ, không chạy.

| Tình huống | Kỳ vọng |
|---|---|
| Hai SET hợp lệ, EXEC | Cả hai có thể được áp dụng |
| MULTI → SET → DISCARD | SET chưa được áp dụng |
| WATCH key thay đổi trước EXEC | Toàn transaction bị hủy trước thực thi |
| EXEC có một lệnh WRONGTYPE runtime | Command hợp lệ khác có thể vẫn có tác động |
| Lỗi network sau khi đã gửi EXEC | Caller có thể không biết transaction đã chạy hay chưa |

**Bài test không nên chỉ assert “EXEC báo lỗi” rồi kết luận mọi key được rollback.** Hãy kiểm tra từng key có liên quan.

## 9. WATCH: optimistic locking cho check-and-set

`WATCH` biến `EXEC` thành một thao tác có điều kiện dựa trên thay đổi của key được theo dõi.

Quy trình:

```text
Client A:
    WATCH account:42
    GET account:42      -> 10
    tính giá trị mới     -> 15
    MULTI
    SET account:42 15
    EXEC

Client B có thể ghi account:42 giữa GET của A và EXEC của A.
Nếu có thay đổi, EXEC của A bị hủy.
```

Redis không tự kiểm tra “giá trị hiện tại còn bằng 10 hay không” theo phép so sánh text; nó theo dõi **việc key được sửa** sau WATCH. Trong Redis hiện đại, expiration/eviction của key cũng có thể gây WATCH conflict.

Ví dụ Redis CLI qua **hai kết nối khác nhau**:

```text
Kết nối A:
  SET test:watch:key v1
  WATCH test:watch:key
  GET test:watch:key  -> v1

Kết nối B:
  SET test:watch:key v2

Kết nối A:
  MULTI
  SET test:watch:key v3
  EXEC  -> nil/null do key bị thay đổi

Sau:
  GET test:watch:key -> v2
```

Nếu không có B sửa key thì EXEC có thể thành công và key thành `v3`.

### Những điểm dễ nhầm

- `WATCH` phải được gọi **trước MULTI**; không đặt WATCH sau khi đã bắt đầu queue.
- WATCH gắn với **Redis connection**, không phải biến Java toàn cục.
- `EXEC` thành công hoặc abort sẽ chấm dứt trạng thái WATCH của giao dịch đó.
- `UNWATCH` cho phép bỏ theo dõi nếu quyết định không đi tới EXEC.
- Tranh chấp chỉ làm một transaction bị hủy, không tự động retry; ứng dụng phải quyết định retry hay trả conflict.
- Với nhiều key được watch, thay đổi một key cũng có thể khiến EXEC abort.
- Nếu bản ghi có thể bị xóa/hết hạn giữa chừng, test phải xem đây có phải một conflict hợp lệ không.

## 10. Viết WATCH test có điểm đồng bộ xác định

Không nên chạy hai thread rồi dùng `Thread.sleep(200)` để hy vọng client B kịp ghi trước EXEC của A. Hãy dùng `CountDownLatch` để bảo đảm đúng thứ tự.

Sơ đồ test:

```text
Thread A                     Thread B
------------------------------------------------
WATCH key
GET key -> "v1"
signal WATCHED
WAIT releaseA
                             await WATCHED
                             SET key "v2"
                             releaseA
MULTI
SET key "v3"
EXEC -> aborted
------------------------------------------------
Assert cuối: key == "v2"
```

**Điều kiện quan trọng:** B phải sử dụng **một Redis connection thực sự độc lập** với connection A đang WATCH. Một số client có cơ chế shared native connection; nếu test dùng chung connection sai cách, conflict test có thể không kiểm chứng được hai client độc lập.

Có thể dùng một Lettuce client/connection riêng cho B trong integration test:

```java
import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;

RedisClient external = RedisClient.create(redisUriForTestContainer);

try {
    StatefulRedisConnection<String, String> writer =
            external.connect();
    try {
        writer.sync().set(key, "v2");
    } finally {
        writer.close();
    }
} finally {
    external.shutdown();
}
```

`redisUriForTestContainer` là URI của Redis lab, được xây từ host và mapped port Testcontainers. Dùng client riêng giúp tránh vô tình chia sẻ trạng thái WATCH với tác vụ đang kiểm thử.

### Ví dụ WATCH với latches

```java
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;

CountDownLatch watched = new CountDownLatch(1);
CountDownLatch resume = new CountDownLatch(1);

// Chạy phần này trên worker thread A.
List<Object> outcome = redis.execute(
        new SessionCallback<List<Object>>() {

    @Override
    @SuppressWarnings({"rawtypes", "unchecked"})
    public List<Object> execute(RedisOperations ops) {
        ops.watch(key);

        try {
            String old = (String) ops.opsForValue().get(key);
            watched.countDown();

            // Test driver B chờ WATCHED, ghi v2 bằng connection riêng,
            // sau đó mới countDown resume.
            if (!resume.await(5, TimeUnit.SECONDS)) {
                ops.unwatch();
                throw new IllegalStateException(
                        "Timeout waiting for competing writer");
            }

            ops.multi();
            ops.opsForValue().set(key, old + "-A");
            return ops.exec();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            ops.unwatch();
            throw new IllegalStateException(ex);
        } catch (RuntimeException ex) {
            // Dọn best-effort theo trạng thái session thực tế.
            throw ex;
        }
    }
});
```

Đoạn trên minh họa **logic của thread A**, không phải toàn bộ test điều phối. JUnit test cần chạy đoạn đó qua một `ExecutorService`/`Future`, đợi `watched.await(...)` rồi cho B ghi `v2` bằng connection riêng trước khi `resume.countDown()`; cuối cùng đợi Future và assert:

```java
assertThat(outcome).isNull(); // EXEC bị WATCH abort
assertThat(redis.opsForValue().get(key)).isEqualTo("v2");
```

Khi dùng API Redis/driver trả một biểu diễn khác cho aborted EXEC, cần dựa vào contract của version đang sử dụng; ở Redis protocol, `EXEC` trả nil/null khi WATCH abort.

Một test còn cần timeout cho Future và cleanup trong `finally`, tránh để latches/thread treo nếu một assertion thất bại. Với code production, dọn `UNWATCH` khi abort trước MULTI và `DISCARD` nếu đã bắt đầu MULTI nhưng chưa EXEC.

## 11. Test WATCH không có xung đột

Ngoài negative test, phải có positive path.

Ví dụ:

```java
String key = "test:watch:" + java.util.UUID.randomUUID();
redis.opsForValue().set(key, "10");

List<Object> result = redis.execute(
        new SessionCallback<List<Object>>() {

    @Override
    @SuppressWarnings({"rawtypes", "unchecked"})
    public List<Object> execute(RedisOperations ops) {
        ops.watch(key);
        String current = (String) ops.opsForValue().get(key);
        int next = Integer.parseInt(current) + 1;

        ops.multi();
        ops.opsForValue().set(key, Integer.toString(next));
        return ops.exec();
    }
});

assertThat(result).hasSize(1);
assertThat(redis.opsForValue().get(key)).isEqualTo("11");
```

Nếu muốn kiểm thử **tăng bộ đếm**, Redis đã có `INCR` nguyên tử và thường phù hợp hơn `WATCH + GET + SET`. WATCH hữu ích hơn khi business condition phức tạp hoặc phải kiểm tra nhiều dữ liệu trước khi commit.

### WATCH và TTL

Một key được WATCH có thể bị expiration/eviction trước `EXEC` và khiến transaction abort. Test nên dùng Redis version phù hợp với hợp đồng production và không kết luận “chỉ một writer Java khác mới gây conflict”.

Nếu test dùng key gần hết hạn, kết quả có thể phụ thuộc timing. Để kiểm chứng expiration có chủ đích, dùng một kịch bản riêng với TTL đủ ngắn và đồng bộ thời gian rõ ràng; không vô tình đặt TTL cho key WATCH trong test concurrency cơ bản.

## 12. Retry WATCH conflict phải có giới hạn

WATCH conflict là kết quả **được mong đợi** khi hai client cạnh tranh, không nhất thiết là lỗi hệ thống.

Một mô hình CAS:

```text
attempt = 1..maxAttempts:
    WATCH key
    read current
    validate business condition
    MULTI
    queue update
    EXEC
    nếu thành công -> return success
    nếu bị conflict -> backoff ngắn, đọc lại và thử tiếp
hết attempts -> trả conflict/overload theo hợp đồng
```

Cần test:

1. Một client không tranh chấp: thành công ngay.
2. Hai client cố cập nhật từ cùng version: một thành công, một abort rồi retry.
3. Nhiều client tranh chấp liên tục: không retry vô hạn.
4. Key bị xóa/hết hạn trong lúc WATCH: xử lý conflict đúng.
5. Business condition không còn đúng sau retry: trả kết quả từ chối, không cố ghi.

Không đặt sleep/backoff quá lớn trong Redis connection đang WATCH nếu điều đó giữ connection chờ không cần thiết. Thông thường nên kết thúc session sau conflict rồi mới backoff trước khi bắt đầu attempt mới.

Với điều kiện đơn giản, ưu tiên command Redis nguyên tử (`INCR`, `SET NX`, `HINCRBY`...) hoặc Lua để giảm vòng lặp WATCH.

## 13. Spring @Transactional khác Redis MULTI/EXEC trong test

Một method được gắn `@Transactional` có thể do `JpaTransactionManager` hoặc `DataSourceTransactionManager` quản lý. **Nó không tự khiến RedisTemplate dùng Redis transaction.**

Spring Data Redis cho phép bật transaction support trên từng template:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class RedisTxTestConfiguration {

    @Bean("transactionalRedisTemplate")
    StringRedisTemplate transactionalRedisTemplate(
            RedisConnectionFactory factory) {

        StringRedisTemplate template =
                new StringRedisTemplate(factory);

        template.setEnableTransactionSupport(true);
        return template;
    }
}
```

Khi có Spring-managed transaction thích hợp và transaction synchronization, write commands của template có thể được xếp hàng để `EXEC` khi Spring transaction commit hoặc `DISCARD` khi rollback. Các read-only commands trong transaction có thể được chuyển qua một connection khác để trả kết quả.

### Bộ test nên có

| Kịch bản | Kỳ vọng |
|---|---|
| Không bật `enableTransactionSupport` | Redis write có thể thực hiện ngay, không chờ commit SQL |
| Bật support + Spring transaction commit | Redis queued writes được thực hiện sau commit theo cơ chế hỗ trợ |
| Bật support + Spring transaction rollback | Redis queued writes bị discard |
| Đọc key vừa SET nhưng transaction chưa commit | Không giả định sẽ thấy write vừa queue |
| SQL commit thành công, Redis EXEC lỗi | SQL không tự rollback; cần repair/đối soát |
| Method tự gọi chính nó (*self invocation*) | `@Transactional` proxy có thể không được áp dụng như dự kiến |
| Test method tự có `@Transactional` rollback mặc định | After-commit path có thể không được chạy, gây test sai |

### Dùng TransactionTemplate để kiểm soát rõ commit và rollback

Giả sử test context đã có `PlatformTransactionManager` cho một database thử nghiệm:

```java
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

TransactionTemplate tx =
        new TransactionTemplate(transactionManager);

tx.executeWithoutResult(status -> {
    transactionalRedisTemplate.opsForValue()
            .set(key, "committed");
});

assertThat(redis.opsForValue().get(key))
        .isEqualTo("committed");
```

Tương tự test rollback:

```java
redis.opsForValue().set(key, "before");

assertThatThrownBy(() ->
        tx.executeWithoutResult(status -> {
            transactionalRedisTemplate.opsForValue()
                    .set(key, "should-not-commit");
            throw new IllegalStateException("force rollback");
        })
).isInstanceOf(IllegalStateException.class);

assertThat(redis.opsForValue().get(key))
        .isEqualTo("before");
```

`assertThatThrownBy` đến từ AssertJ. Ví dụ giả định `transactionManager`, `transactionalRedisTemplate` và `redis` đã được inject; không tạo transaction manager giả chỉ để test Redis MULTI/EXEC.

**Quan trọng:** Test trong Spring thường có thể được rollback tự động nếu method test mang `@Transactional`. Nếu muốn kiểm chứng callback `AFTER_COMMIT`, hãy kết thúc transaction **thực sự** bằng `TransactionTemplate` hoặc cơ chế test transaction rõ ràng và assert **sau khi commit**. Đừng đặt assertion commit bên trong một test transaction chưa hoàn tất.

## 14. Những điều @Transactional không bảo đảm

```text
SQL transaction           Redis transaction/callback
-----------------------   ---------------------------
BEGIN
UPDATE orders
COMMIT  ----------------> Redis EXEC/evict callback
                               |
                               +--> Redis có thể lỗi/timeout
```

Ngay cả khi Redis transaction support được bật, không có mặc định một **XA two-phase commit** kết hợp SQL và Redis.

Do đó nên có test:

1. Database commit thành công.
2. Giả lập Redis không khả dụng đúng giai đoạn đồng bộ sau commit.
3. Xác nhận database **đã commit**.
4. Xác nhận Redis chưa phản ánh thay đổi hoặc callback thất bại.
5. Xác minh có cơ chế reconciliation, retry hoặc transactional outbox nếu nghiệp vụ yêu cầu.

Không retry toàn bộ command SQL mù quáng sau một lỗi cache callback: có thể tạo dữ liệu nghiệp vụ trùng.

## 15. Pipeline: tối ưu I/O, không phải atomic transaction

Một chuỗi Redis commands đồng bộ có thể phải trải qua nhiều lần chờ:

```text
Client: SET k1 -> chờ reply
Client: SET k2 -> chờ reply
Client: SET k3 -> chờ reply
```

Pipeline gửi các command mà không cần chờ từng reply riêng:

```text
Client: SET k1
        SET k2
        SET k3
          |
          v
Redis xử lý, trả các replies theo thứ tự command
          |
          v
Client thu kết quả pipeline
```

Pipeline giúp giảm chi phí nhiều vòng mạng, đặc biệt khi có nhiều command độc lập. Tuy nhiên:

- Nó không ngăn Redis xử lý command từ client khác **giữa** những command của pipeline.
- Một command lỗi không tự undo các command pipeline đã thành công.
- Mỗi command vẫn có kiểu trả về riêng.
- Một connection pipeline cần được đóng/flushed đúng cách.
- Redis Cluster có giới hạn routing theo slot/node tùy driver/command.
- Đo hiệu năng cần tính chi phí serialization, bộ nhớ reply list và kích thước batch.

## 16. Spring Data Redis executePipelined

Spring Data Redis cung cấp `RedisTemplate.executePipelined(...)` với `RedisCallback` hoặc `SessionCallback` để tập hợp nhiều command.

Ví dụ:

```java
import java.util.List;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;

public List<Object> writeAndReadPipeline(
        String keyA, String counterKey) {

    return redis.executePipelined(
            new SessionCallback<Object>() {

        @Override
        @SuppressWarnings({"rawtypes", "unchecked"})
        public Object execute(RedisOperations ops) {
            ops.opsForValue().set(keyA, "A");
            ops.opsForValue().increment(counterKey);
            ops.opsForValue().get(keyA);

            // Callback của executePipelined phải trả null.
            return null;
        }
    });
}
```

**Vì sao callback phải trả `null`?** Kết quả trả trực tiếp của callback được bỏ qua; kết quả chính thức là `List<Object>` chứa replies của những commands được gửi qua pipeline.

Spring Data Redis dùng serializers phù hợp để deserialize kết quả pipeline. Nếu dùng `StringRedisTemplate`, value trả về thường là String; các reply số học vẫn là số hoặc kiểu phù hợp theo command.

### Test kết quả pipeline

```java
@Test
void pipelineReturnsRepliesAndPersistsCommands() {
    String base = "test:pipe:" + UUID.randomUUID();
    String keyA = base + ":a";
    String counter = base + ":counter";

    List<Object> replies =
            writeAndReadPipeline(keyA, counter);

    assertThat(replies).hasSize(3);
    assertThat(replies.get(2)).isEqualTo("A");

    assertThat(redis.opsForValue().get(keyA)).isEqualTo("A");
    assertThat(redis.opsForValue().get(counter)).isEqualTo("1");
}
```

Nếu ứng dụng dùng serializer khác, cần điều chỉnh kiểu kỳ vọng của reply thay vì ép mọi thứ là String.

**Không assert giá trị trả về tức thì của `opsForValue().get` ngay trong pipeline callback.** Trong chế độ pipeline, kết quả của command thường được đưa vào reply list khi pipeline hoàn tất, không được trả ngay như lời gọi đồng bộ bình thường.

## 17. Test pipeline không nguyên tử

Một kịch bản âm cần chứng minh **pipeline không rollback những command hợp lệ** khi một command khác lỗi.

Ví dụ về ý tưởng:

```text
Chuẩn bị:
  SET test:pipeline:wrongtype "string-value"

Trong pipeline:
  SET test:pipeline:ok "written"
  LPUSH test:pipeline:wrongtype "x"  -> WRONGTYPE
  SET test:pipeline:later "maybe"

Sau khi pipeline kết thúc/lỗi:
  Kiểm tra test:pipeline:ok đã được ghi.
  Quan sát phản hồi/lỗi đối với LPUSH.
  Kiểm tra test:pipeline:later theo hành vi driver và server.
```

Một số phiên bản driver/template có thể báo exception khi thu replies của pipeline; không giả định một lỗi sẽ trả List đúng ba phần tử trong mọi môi trường. Kết luận quan trọng là **các thao tác đã được Redis xử lý trước lỗi không được hoàn tác**.

### Test xen kẽ với client khác

Nếu muốn kiểm chứng tính **không nguyên tử** của pipeline, có thể sử dụng server-side instrumentation hoặc thiết kế một lịch trình có thể điều khiển giữa hai lệnh. Đừng dùng test dạng “chạy 100.000 lần hy vọng thấy xen kẽ” làm nguồn chứng cứ chính; nó dễ flaky.

Khi cần một nhóm command thật sự không bị xen kẽ, dùng `MULTI/EXEC` hoặc một Lua script phù hợp thay vì pipeline thuần.

## 18. Pipeline không có nghĩa là batch không giới hạn

Một pipeline chứa hàng triệu commands/replies có thể làm tăng bộ nhớ ở client và server, giữ connection lâu, tăng latency cho các client khác hoặc bị lỗi khi network quá tải.

Nên test các đặc điểm:

- Batch size 100, 1.000, 5.000 trong môi trường benchmark phù hợp.
- Kích thước value từ nhỏ tới gần dữ liệu production.
- Kết quả đúng trước khi đánh giá latency.
- Độ trễ p95/p99, không chỉ tổng thời gian trung bình.
- Số memory allocations/reply list lớn.
- Tác động khi một command lỗi giữa batch.
- Hiệu ứng khi có nhiều client đồng thời.
- Khả năng timeout/retry không làm trùng side effects.

Câu hỏi hiệu năng đúng không phải “pipeline luôn nhanh hơn đúng 10 lần?” mà là “với command mix, số lượng và độ trễ mạng thực tế, pipeline tăng throughput bao nhiêu mà vẫn giữ đúng ngữ nghĩa và tài nguyên?”.

## 19. Không trộn ngữ nghĩa pipeline với MULTI/EXEC một cách tùy tiện

Pipeline và transaction có thể được kết hợp trong những tình huống đặc biệt (ví dụ gửi `MULTI`, nhiều command rồi `EXEC` trong một đợt giao tiếp) nếu driver/framework hỗ trợ đúng.

Nhưng trong kiểm thử Spring Data Redis cần phân biệt:

- `executePipelined` trả replies của pipeline, có thể gồm nhiều loại kết quả.
- `execute(SessionCallback)` với `multi/exec` trả kết quả Redis transaction.
- Việc gọi `multi()` trong một pipeline thay đổi hình thức reply và state của connection; không thể áp dụng assertion của pipeline thuần mà không hiểu kết quả transaction.
- Lỗi enqueue hoặc lỗi EXEC có semantics khác lỗi pipeline thuần.
- Việc dùng `executePipelined(SessionCallback)` không tự biến mọi command trong callback thành một transaction.

Nếu bài toán yêu cầu atomicity, hãy viết một test transaction riêng trước; nếu cần thêm performance, sau đó mới đánh giá phương án pipeline+transaction. Không gọi `executePipelined` chỉ vì muốn “nhiều lệnh nguyên tử”.

## 20. Lua: gom đọc–kiểm tra–ghi thành một Redis operation

Khi ứng dụng cần kiểm tra rồi cập nhật một key theo điều kiện, Lua thường giúp giảm khoảng race so với `GET → xử lý Java → SET`.

Ví dụ quy tắc **compare-and-set**:

```text
Nếu key hiện tại bằng expected:
    ghi newValue
    trả 1
Ngược lại:
    giữ nguyên
    trả 0
```

Lua script:

```lua
-- KEYS[1] = khóa cần CAS
-- ARGV[1] = expected value
-- ARGV[2] = new value

local current = redis.call('GET', KEYS[1])

if current == ARGV[1] then
    redis.call('SET', KEYS[1], ARGV[2])
    return 1
end

return 0
```

Redis chạy script như một thao tác nguyên tử đối với các lệnh từ client khác trong lúc script đang thực thi. Hai client cùng CAS từ `v1` sang hai giá trị khác nhau không thể **cùng** thấy và ghi đè giá trị `v1` nếu cùng thao tác trên key được script bảo vệ.

Không nên hiểu “Lua atomic” là “Lua script luôn rollback khi ném lỗi”. Nếu script đã ghi một key rồi gặp runtime error ở bước sau, tác động trước lỗi không được tự hoàn tác.

## 21. Spring Data Redis chạy Lua bằng DefaultRedisScript

`DefaultRedisScript<T>` là abstraction cho script text/resource và result type. Nên khai báo **một bean singleton** để giảm việc tính lại SHA1 không cần thiết.

Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class RedisScriptConfiguration {

    @Bean
    public RedisScript<Long> compareAndSetScript() {
        String lua =
                "local c = redis.call('GET', KEYS[1]); " +
                "if c == ARGV[1] then " +
                "  redis.call('SET', KEYS[1], ARGV[2]); " +
                "  return 1; " +
                "end; return 0;";

        DefaultRedisScript<Long> script =
                new DefaultRedisScript<>();
        script.setScriptText(lua);
        script.setResultType(Long.class);
        return script;
    }
}
```

Service gọi script:

```java
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class CompareAndSetService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> cas;

    public CompareAndSetService(
            StringRedisTemplate redis,
            RedisScript<Long> cas) {
        this.redis = redis;
        this.cas = cas;
    }

    public boolean update(
            String key, String expected, String replacement) {

        Long changed = redis.execute(
                cas,
                List.of(key),
                expected,
                replacement);

        return Long.valueOf(1L).equals(changed);
    }
}
```

`StringRedisTemplate` dùng serialization phù hợp cho key/arguments dạng chuỗi trong ví dụ. Nếu template có serializer nhị phân/JSON, một phép so sánh Lua dạng String có thể không khớp wire format thực tế.

Spring Data Redis script executor thường thử `EVALSHA` để dùng script cache và fallback `EVAL` nếu script chưa có trên Redis server. Không cần tự viết đoạn gọi SHA1 cho use case cơ bản.

## 22. Lua test: đúng điều kiện và sai điều kiện

Test positive path:

```java
@Test
void casUpdatesOnlyWhenExpectedValueMatches() {
    String key = "test:cas:" + UUID.randomUUID();
    redis.opsForValue().set(key, "v1");

    boolean changed =
            casService.update(key, "v1", "v2");

    assertThat(changed).isTrue();
    assertThat(redis.opsForValue().get(key))
            .isEqualTo("v2");
}
```

Test negative path:

```java
@Test
void casDoesNotUpdateWhenExpectedValueDiffers() {
    String key = "test:cas:" + UUID.randomUUID();
    redis.opsForValue().set(key, "v2");

    boolean changed =
            casService.update(key, "v1", "v3");

    assertThat(changed).isFalse();
    assertThat(redis.opsForValue().get(key))
            .isEqualTo("v2");
}
```

Điều cần assert là **cả return value và Redis state**. Nếu chỉ assert trả `false` mà không đọc lại key, test không chứng minh được script đã tránh side effect.

## 23. Lua concurrency test: hai client chỉ một người thắng

Với key ban đầu `v1`, hai client đồng thời yêu cầu:

```text
A: CAS(v1 -> v2)
B: CAS(v1 -> v3)
```

Kỳ vọng:

- Tổng số thành công bằng **1**.
- Final value là `v2` hoặc `v3` tùy client thắng.
- Không có trạng thái final vừa `v2` vừa `v3`.
- Client thua nhận kết quả `0`/false, không tự ghi đè client thắng.

Pseudo-test với latches:

```java
String key = "test:cas:race:" + UUID.randomUUID();
redis.opsForValue().set(key, "v1");

CountDownLatch release = new CountDownLatch(1);

Future<Boolean> left = executor.submit(() -> {
    release.await();
    return casService.update(key, "v1", "v2");
});

Future<Boolean> right = executor.submit(() -> {
    release.await();
    return casService.update(key, "v1", "v3");
});

release.countDown();

boolean a = left.get(5, TimeUnit.SECONDS);
boolean b = right.get(5, TimeUnit.SECONDS);

assertThat((a ? 1 : 0) + (b ? 1 : 0))
        .isEqualTo(1);

assertThat(redis.opsForValue().get(key))
        .isIn("v2", "v3");
```

Đây là phần thân của test; `executor` cần một `ExecutorService` tối thiểu hai worker threads và cleanup trong `finally`. Nếu dùng executor một thread, test vẫn có thể cho kết quả đúng theo logic CAS nhưng sẽ không thử được mức đồng thời mong muốn.

Bản thân Redis thực thi Lua script tuần tự, nên test không cần hy vọng một interleaving đặc biệt trong nội bộ script. Điểm quan trọng là hai client đều cố cập nhật từ **cùng expected value**.

## 24. Test Lua runtime error: atomic không bằng rollback

Ví dụ script cố ý lỗi **sau** một thao tác ghi:

```lua
redis.call('SET', KEYS[1], 'written')
redis.call('LPUSH', KEYS[2], 'x')
return 1
```

Nếu `KEYS[2]` đã là một Redis String, `LPUSH` gây `WRONGTYPE`. Lúc đó `KEYS[1]` **có thể vẫn chứa `written`**, vì Redis không rollback các lệnh script đã thực thi trước runtime error.

Để kiểm chứng trong lab:

1. Đặt `KEYS[1]` là key thử nghiệm có thể thay đổi.
2. Đặt `KEYS[2]` thành String để tạo WRONGTYPE.
3. Chạy script qua một template/script executor phù hợp.
4. Ghi nhận exception từ Spring Data Redis.
5. Đọc lại `KEYS[1]` và kiểm tra tác động trước lỗi.
6. Không kết luận script đã rollback chỉ vì client nhận exception.

**Thiết kế script an toàn:** kiểm tra kiểu/điều kiện đầu vào trước khi ghi nếu cần tránh partial effects do runtime errors; dùng ít command, có branch rõ ràng và input validation phù hợp.

### Redis Cluster và keys của Lua

Mọi Redis key mà script truy cập cần được truyền hợp lệ trong `KEYS` và các thao tác liên quan phải tuân thủ giới hạn hash slot của Redis Cluster. Ví dụ:

```text
test:lua:{account-42}:balance
test:lua:{account-42}:version
```

Hai key có cùng hash tag và cùng slot. Test trên Redis standalone không kiểm chứng được `CROSSSLOT`; nếu deployment dùng Cluster, cần một test riêng trên Redis Cluster thật.

## 25. Test script cache và NOSCRIPT

Redis có script cache. Spring Data Redis dùng SHA1 của script và thường thử `EVALSHA`, fallback sang `EVAL` khi script chưa tồn tại trong cache server.

Một kịch bản integration test:

1. Chạy `compareAndSetScript` lần đầu trên container.
2. Chạy lại script với một key khác.
3. Trên **Redis lab riêng**, làm trống script cache nếu cần kiểm thử `NOSCRIPT`.
4. Gọi script lại qua Spring Data Redis.
5. Xác nhận vẫn trả kết quả đúng và key được cập nhật.
6. Quan sát exception nếu cấu hình/driver không hỗ trợ fallback như giả định.

Trong Redis CLI, lệnh `SCRIPT FLUSH` thay đổi script cache của node, nên **không chạy trên production để kiểm thử**. Khi dùng Redis Cluster, script cache/trạng thái của nhiều nodes cần được xem xét theo version Redis và cơ chế triển khai.

Đừng assert “luôn dùng EVALSHA” theo ý tưởng performance nếu không kiểm soát script cache/lifecycle; nên assert **kết quả nghiệp vụ** của script và theo dõi hiệu năng riêng.

## 26. Lua không có quyền thực hiện side effect ngoài Redis

Lua trong Redis được thiết kế để chạy các Redis commands theo khả năng scripting của server, không phải script tùy ý truy cập network, filesystem hay gọi database ngoài.

Vì vậy không thể viết một script Redis để atomically:

```text
UPDATE PostgreSQL
SET Redis key
Publish HTTP message
```

như thể Redis Lua là một distributed transaction coordinator. Nếu nguồn dữ liệu nằm trong PostgreSQL và Redis là cache, cần thiết kế đồng bộ như outbox, invalidation sau commit, versioning hoặc reconciliation.

Một lỗi Redis sau SQL commit không làm SQL tự rollback. Đây là một kịch bản nên có trong bộ integration tests khi business workflow có nhiều tài nguyên.

## 27. Reactive Redis: kiểm thử bằng StepVerifier

`ReactiveRedisTemplate` và `ReactiveStringRedisTemplate` trả Reactor publishers. Trong reactive code, **chỉ tạo publisher mà không subscribe có thể không gửi Redis command**.

Ví dụ Lua execution reactive, với một `RedisScript<Long>` có sẵn:

```java
import java.util.List;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import reactor.core.publisher.Flux;

public Flux<Long> reactiveCas(
        ReactiveStringRedisTemplate redis,
        RedisScript<Long> script,
        String key,
        String expected,
        String replacement) {

    return redis.execute(
            script,
            List.of(key),
            List.of(expected, replacement));
}
```

API overload cụ thể phụ thuộc version Spring Data Redis; kiểu publisher trả về cho script execution là `Flux<T>` trong mô hình reactive scripting.

Dùng `StepVerifier` để tạo subscription và assert:

```java
import reactor.test.StepVerifier;

StepVerifier.create(reactiveCas(
        reactiveRedis,
        casScript,
        key,
        "v1",
        "v2"))
        .expectNext(1L)
        .verifyComplete();
```

Nếu key chưa tồn tại hoặc expected không khớp, script trả `0L` theo định nghĩa.

### Thử lỗi trong reactive pipeline

Nếu Redis mất kết nối hoặc script bị từ chối, publisher có thể phát `onError`. `Mono.empty()`/`Flux.empty()` không đồng nghĩa timeout hay Redis server lỗi. Đừng dùng `onErrorResume(ex -> Mono.empty())` rồi coi test “thành công vì không có dữ liệu”, trừ khi nghiệp vụ chủ động cho phép fallback đó.

Trong WebFlux, tránh `block()` trên event-loop; `StepVerifier` được dùng ở thread của test như một công cụ kiểm chứng publisher, không phải cách viết service production.

## 28. Redis Cluster ảnh hưởng tới test thế nào?

Một Redis Testcontainers standalone phù hợp để chứng minh semantics của `MULTI/EXEC`, `WATCH`, pipeline và Lua **trong một node**. Nhưng ứng dụng production sử dụng Redis Cluster còn có các giới hạn:

- Các key trong transaction hoặc script phải đáp ứng quy tắc hash slot.
- Một command nhiều key khác slot có thể bị `CROSSSLOT`.
- Pipeline nhiều key có routing và driver support riêng; không giả định mọi command được gửi qua một connection như standalone.
- Failover/resharding có thể gây `MOVED`/`ASK`, timeout hoặc invalidation của slot map.
- Test trên standalone không chứng minh retry/connection behavior khi cluster đổi primary.
- Khi đọc từ replica, dữ liệu có thể trễ so với primary vì replication bất đồng bộ.

Một cách đặt key test cho cùng entity:

```text
test:transfer:{account-42}:balance
test:transfer:{account-42}:audit
```

Hai key có cùng hash tag `{account-42}`, nên cùng slot.

Để chứng minh hỗ trợ Cluster:

1. Chuẩn bị Redis Cluster test với nhiều primary.
2. Chạy các test WATCH/Lua sử dụng key cùng slot.
3. Thử một command nhiều key thuộc slot khác nhau và assert lỗi phù hợp.
4. Thực hiện failover/reshard ở cluster lab, không phải production.
5. Xác nhận application có recovery/routing theo driver mà không vi phạm bất biến nghiệp vụ.

Không đưa các lệnh quản trị chuyển role/slot vào test chạy trên Redis dùng chung với bất kỳ dịch vụ khác.

## 29. Lỗi mạng, timeout và kết quả không chắc chắn

Một test chỉ kiểm chứng happy path có thể bỏ qua trường hợp nguy hiểm nhất:

```text
Client gửi EXEC / EVAL / INCR
           |
           v
Redis đã thực thi command
           |
           v
Network bị đứt trước khi reply đến client
           |
           v
Client timeout, không biết lệnh đã chạy hay chưa
```

Trong tình huống này:

- `GET` có thể retry theo chính sách đọc thích hợp.
- `INCR` retry mù quáng có thể tăng hai lần.
- Lua script có side effect có thể đã chạy hoàn tất dù caller nhận timeout.
- Transaction `EXEC` có thể đã commit nhưng client không nhận reply.
- Pipeline có thể đã thực hiện **một phần hoặc toàn bộ** command trước khi mất kết nối, tùy thời điểm.
- `WATCH` không phải cơ chế idempotency xuyên retry.

### Kịch bản fault injection

Trong môi trường test:

1. Dùng một proxy mạng có thể chủ động ngắt kết nối giữa app và Redis.
2. Đưa command có side effect vào trạng thái đã gửi nhưng chưa nhận reply.
3. Ngắt kết nối ở mốc được kiểm soát.
4. Ghi nhận error/timeout của caller.
5. Đọc trạng thái Redis từ kết nối quản trị độc lập.
6. Assert chính sách retry có hoặc không gây side effect lặp.
7. Nếu operation phải exactly-once theo nghiệp vụ, dùng operation ID/idempotency record bên nguồn có thẩm quyền.

Một fault proxy có thể không điều khiển chính xác được mốc Redis đã thực thi command mà client chưa thấy reply; cần instrumentation hoặc thiết kế test double ở đúng ranh giới, không tuyên bố “đã chứng minh mất reply sau commit” chỉ bằng cách kill container ngẫu nhiên.

## 30. Assert đúng loại kết quả và serializer

Spring Data Redis có thể serialize value theo String, JDK serializer hoặc JSON. Kết quả của `exec()` và `executePipelined()` được deserialize theo serializer của template.

Những khác biệt thường gặp:

| Operation | Kết quả thường gặp | Điều cần kiểm tra |
|---|---|---|
| `SET` | Boolean/status hoặc kiểu reply phù hợp | Không so sánh bừa với String `"OK"` |
| `INCR` | Long | Không ép số thành String khi kiểm tra reply |
| `GET` | Giá trị đã deserialize | Key/value serializer có tương thích không |
| `HGET` | Hash value serializer | Không dùng nhầm serializer của value bình thường |
| `MULTI/EXEC` | List của replies hoặc nil nếu abort | WATCH conflict vs EXEC success |
| `executePipelined` | List replies theo command order | Callback phải trả null |
| Lua trả `1`/`0` | `Long` khi script result type là Long | Script result type và serializer |
| Lua trả boolean | `Boolean` khi script result type Boolean | Không giả định kiểu raw Redis reply |
| Reactive script | Flux của script result | Cần subscription |

Ví dụ nếu Java mong JSON DTO nhưng Redis key thực tế chứa string đơn, lỗi decode không phải bằng chứng Redis transaction thất bại. Trong test, nên dùng `StringRedisTemplate` để wire format dễ quan sát, sau đó tạo test riêng cho serializer tùy chỉnh của ứng dụng.

## 31. Bộ ma trận kiểm thử đề xuất

| ID | Cơ chế | Arrange/Act | Assert tối thiểu |
|---|---|---|---|
| TX-01 | `MULTI/EXEC` | Queue 2 SET rồi EXEC | Hai key đúng sau EXEC; replies tương ứng |
| TX-02 | `DISCARD` | Queue SET rồi DISCARD | Key giữ giá trị cũ |
| TX-03 | Chưa EXEC | Queue SET, đọc bằng connection khác | Connection khác chưa thấy write |
| TX-04 | Runtime error | SET hợp lệ + WRONGTYPE trong EXEC | SET hợp lệ có thể vẫn tồn tại |
| TX-05 | Connection cleanup | Lỗi giữa MULTI và EXEC | Session được dọn hoặc connection không tái sử dụng sai |
| WATCH-01 | Không conflict | WATCH, read, MULTI, EXEC | Thành công, key là giá trị mới |
| WATCH-02 | Có conflict | B ghi giữa WATCH và EXEC của A | EXEC A abort, B không bị ghi đè |
| WATCH-03 | Retry có giới hạn | Nhiều client cạnh tranh | Không loop vô hạn, xử lý conflict đúng |
| WATCH-04 | Key expiration | WATCH key rồi key hết hạn | Theo Redis version/hợp đồng, conflict được xử lý |
| PIPE-01 | Pipeline happy path | SET, INCR, GET | Reply list/thứ tự và final state đúng |
| PIPE-02 | Callback return | Callback trả non-null | Test phát hiện sai contract của executePipelined |
| PIPE-03 | Partial failure | Có WRONGTYPE giữa commands | Không giả định rollback |
| PIPE-04 | Batch size | Nhiều commands có giới hạn | Đúng dữ liệu, đo latency/memory |
| LUA-01 | CAS success | Expected khớp | Script trả 1, key đổi |
| LUA-02 | CAS rejection | Expected không khớp | Script trả 0, key giữ nguyên |
| LUA-03 | Concurrent CAS | Hai clients cùng expected | Đúng một thành công |
| LUA-04 | Runtime error | Script ghi rồi lỗi WRONGTYPE | Phân biệt atomicity và rollback |
| LUA-05 | Script cache | Script bị flush trong lab | Executor fallback, kết quả đúng |
| CLUSTER-01 | Same slot | Multi-key Lua/transaction | Thành công theo slot contract |
| CLUSTER-02 | Cross-slot | Multi-key khác slot | Lỗi được phân loại, không retry mù |
| FAIL-01 | Timeout sau write | Mất reply | Retry không tạo duplicate side effect |
| SQL-01 | Spring commit/rollback | TransactionTemplate và Redis transaction support | Sau commit/rollback có trạng thái đúng |
| SQL-02 | Redis lỗi sau SQL commit | Simulate callback failure | SQL vẫn commit, repair path hoạt động |

**Điểm kiểm chứng cuối:** những test trên cần chạy ở mức thích hợp (unit, integration, concurrency, fault injection), không dồn tất cả vào một class JUnit với một timeout chung khó chẩn đoán.

## 32. Benchmark pipeline và Lua theo cách không đánh đổi tính đúng

Hiệu năng nên được đo sau khi bộ test correctness chạy với data và serializers tương ứng.

Một kế hoạch benchmark:

1. Chuẩn bị Redis lab và dataset cố định.
2. Làm nóng JVM/connection/serializer.
3. Đo n lần `SET` tuần tự.
4. Đo `executePipelined` với cùng số commands và batch hợp lý.
5. Nếu nghiệp vụ cần logic kiểm tra–ghi, đo `WATCH` loop và Lua script tương đương.
6. Đo latency p50/p95/p99, throughput, CPU và memory.
7. Chạy với nhiều clients để xem contention.
8. Kiểm tra mọi giá trị cuối cùng sau benchmark.
9. Thử khi Redis có mạng latency cao hơn thay vì chỉ loopback.
10. Không so sánh kết quả giữa pipeline “chỉ ghi” với WATCH “đọc, validate, retry” như thể chúng có cùng ngữ nghĩa.

Một benchmark “pipeline nhanh gấp X” không có ý nghĩa khi không nói số commands, kích thước payload, độ trễ mạng, version Redis, kết quả có được deserialize không và mức đồng thời.

## 33. Debug khi test thất bại

### 33.1. `exec()` trả null trong test tưởng phải thành công

Khả năng là WATCH conflict, key bị expire/evict, hoặc một thread khác đã sửa key. Dùng key unique, ghi mốc WATCH/EXEC, giữ TTL ổn định và bảo đảm không có background job động vào namespace test.

### 33.2. GET trong MULTI trả null

Trong transaction, command được queue và một số method có thể trả `null` ngay thay vì dữ liệu thật. Không dùng giá trị tạm đó như thể command đã chạy. Nếu cần đọc trước khi quyết định, `WATCH` rồi `GET` **trước MULTI**.

### 33.3. Pipeline trả các phần tử không đúng Java type

Kiểm tra RedisTemplate serializer, đặc biệt value/hash value và custom result serializer. String key có thể được encode khác với tên key gõ trong CLI.

### 33.4. Test WATCH đôi lúc qua, đôi lúc không

Có thể do dùng `sleep` thay vì latches, dùng connection của cùng client sai cách, cleanup key/TTL từ test khác hoặc assert trước khi Future hoàn tất.

### 33.5. Lua chạy qua CLI nhưng Spring trả 0

Kiểm tra key bytes, argument serialization, expected value có đúng wire format, script result type và tên key. StringRedisTemplate có thể phù hợp cho script so sánh chuỗi; một JSON serializer thì không.

### 33.6. Lua test trên standalone thành công nhưng Cluster lỗi

Kiểm tra hash slots của toàn bộ `KEYS` và cách script khai báo key. Multi-key script trên cluster cần đáp ứng cùng slot; standalone không phát hiện điều kiện này.

### 33.7. Test có @Transactional nhưng after-commit không chạy

Spring Test có thể rollback test method khi kết thúc theo mặc định. Dùng transaction được commit thực sự nếu mục tiêu là kiểm tra `AFTER_COMMIT` và kiểm tra sau khi transaction đóng.

### 33.8. Redis timeout làm test treo

Đặt timeout ở Testcontainers startup, Future, latch và Redis command, nhưng phân biệt lỗi performance thực với tài nguyên CI quá thiếu. Không để một thread chờ latch vô hạn nếu setup fail.

### 33.9. Test “rollback” vẫn có một key bị ghi

Kiểm tra lệnh bị lỗi runtime trong `EXEC` hay transaction bị DISCARD trước EXEC. Redis không rollback runtime errors; kỳ vọng toàn bộ key cũ là sai nếu transaction đã thực thi một số command.

## 34. Những câu hỏi tự đánh giá

**1. Vì sao phải dùng SessionCallback với MULTI/EXEC?**  
Vì WATCH/MULTI/EXEC gắn với connection; các lời gọi RedisTemplate tách rời không đảm bảo dùng chung connection.

**2. EXEC có rollback mọi lệnh nếu một lệnh WRONGTYPE không?**  
Không. Lỗi runtime của một command có thể cùng tồn tại với các command khác đã thực thi thành công.

**3. WATCH dùng để làm gì?**  
Biến EXEC thành một transaction có điều kiện dựa trên việc key được theo dõi có thay đổi kể từ WATCH hay không.

**4. Vì sao WATCH test cần hai connection độc lập?**  
Để mô phỏng một client khác thực sự sửa key trong khoảng WATCH → EXEC; không trộn trạng thái của cùng connection.

**5. WATCH conflict tự retry không?**  
Không. Ứng dụng phải quyết định thử lại với giới hạn, backoff hoặc trả conflict.

**6. Pipeline có tạo atomic transaction không?**  
Không. Nó tối ưu truyền nhiều commands/replies, không bảo đảm rollback hay không có xen kẽ.

**7. Callback của executePipelined phải trả gì?**  
`null`; kết quả pipeline được trả riêng dưới dạng `List<Object>`.

**8. Lua CAS giúp tránh race nào?**  
Race giữa đọc giá trị, kiểm tra điều kiện và ghi khi hai client đồng thời sửa một key.

**9. Lua script có rollback khi lỗi sau SET không?**  
Không. Việc script chạy nguyên tử không đồng nghĩa tác động đã ghi được hoàn tác khi runtime error.

**10. Tại sao không retry mù quáng INCR sau timeout?**  
Vì lệnh đầu có thể đã chạy, retry có thể tăng hai lần.

**11. Test trên Redis standalone có chứng minh multi-key Lua chạy trên Cluster không?**  
Không. Cần test cùng slot/cross-slot trong Redis Cluster thật.

**12. Test method gắn @Transactional có thể kiểm chứng AFTER_COMMIT ngay không?**  
Không chắc; Spring Test có thể rollback mặc định. Cần commit thực sự và assert ngoài transaction.

**13. Vì sao chỉ assert số replies của pipeline là chưa đủ?**  
Vì cần kiểm chứng giá trị cuối cùng và lỗi một phần; reply count không chứng minh dữ liệu đúng.

**14. Khi Redis chỉ là cache của SQL, Redis EXEC lỗi có rollback SQL không?**  
Không tự động. Hai tài nguyên không có commit nguyên tử mặc định; cần recovery/outbox khi thích hợp.

## 35. Checklist thiết kế test trước khi đưa vào CI

- [ ] Dùng Redis test riêng; không có command quản trị nguy hiểm trên production.
- [ ] Mỗi test có key namespace riêng và cleanup rõ ràng.
- [ ] Mô tả bất biến, setup, điểm đồng bộ và final state cần assert.
- [ ] Có test MULTI/EXEC success, DISCARD, WATCH conflict và WRONGTYPE runtime.
- [ ] WATCH conflict được tạo bằng latches và connection độc lập, không dựa vào sleep.
- [ ] Có giới hạn timeout cho Future/threads/connections.
- [ ] Pipeline test assert **reply order + dữ liệu thực tế**, không nhầm pipeline với transaction.
- [ ] Lua test assert success, rejection, concurrency và runtime-error semantics.
- [ ] Script serializers và result type được xác định tường minh.
- [ ] Kết quả Redis được đọc **sau EXEC/pipeline** bằng connection/đường đọc phù hợp.
- [ ] Có test Redis transaction support khi dùng @Transactional, kể cả rollback.
- [ ] Có test lỗi sau SQL commit nếu Redis chỉ là cache của database.
- [ ] Mỗi retry side effect có chiến lược idempotency.
- [ ] Cluster deployment có test hash slots, routing và failover tương ứng.
- [ ] CI báo lỗi rõ để phân biệt Redis chưa start, timeout do tài nguyên và lỗi nghiệp vụ.

Checklist này phục vụ việc **thiết kế bộ test của ứng dụng**, không thay thế những assertion cụ thể trên Redis state.

## 36. Tổng kết

- **`MULTI/EXEC`** chứng minh một nhóm commands được Redis thực thi tuần tự khi EXEC, nhưng Redis không rollback mọi lỗi runtime.
- **`DISCARD`** hủy những commands chưa được EXEC; không hoàn tác transaction đã commit.
- **`WATCH`** giúp kiểm tra optimistic concurrency; hãy viết test xung đột có thứ tự xác định và connection độc lập.
- **Pipeline** giảm round-trips; kiểm thử reply list, serialization, order và partial failures, nhưng không giả định atomicity.
- **Lua** phù hợp để gom read–check–write trên Redis; kiểm thử cùng expected value từ nhiều clients và lỗi sau tác động.
- **Spring Data Redis** cung cấp `SessionCallback`, `executePipelined` và `DefaultRedisScript`; chúng có contract khác nhau.
- **`@Transactional` với SQL** không tự cho Redis và SQL commit nguyên tử; test phải xem hậu quả commit/rollback và lỗi after-commit.
- **Timeout sau write** có thể để kết quả không chắc chắn; retry cần idempotency, không chỉ thêm số lần thử.
- **Redis Cluster** có hash slots, redirection và multi-key limitations cần kiểm thử riêng.
- **JUnit + Testcontainers + StepVerifier** giúp kiểm thử hành vi Redis thật trong môi trường cô lập, thay vì suy đoán từ mocks.

Một bộ kiểm thử đáng tin cậy không chỉ hỏi “command có chạy không?” mà còn hỏi **“Khi hai client cạnh tranh, một command lỗi, connection mất phản hồi hoặc transaction SQL đã commit, trạng thái nào thực sự còn lại trong Redis và ứng dụng sẽ phục hồi ra sao?”**

## Tài liệu tham khảo

- [Spring Data Redis — Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html): `SessionCallback`, `multi`/`exec`/`discard` và Spring transaction support.
- [Spring Data Redis — Pipelining](https://docs.spring.io/spring-data/redis/reference/redis/pipelining.html): `executePipelined`, callback result và serializers.
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html): `DefaultRedisScript`, `EVALSHA` và `EVAL`.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): connection handling và Redis operations.
- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/): MULTI/EXEC/DISCARD/WATCH, optimistic locking và không có rollback.
- [Redis — WATCH](https://redis.io/docs/latest/commands/watch/): optimistic locking theo key.
- [Redis — EXEC](https://redis.io/docs/latest/commands/exec/): execute transaction và nil reply khi WATCH abort.
- [Redis — Pipelining](https://redis.io/docs/latest/develop/using-commands/pipelining/): giảm round-trip và xử lý replies.
- [Redis — Lua Scripting](https://redis.io/docs/latest/develop/programmability/eval-intro/): EVAL/EVALSHA, atomicity và scripting conventions.
- [Spring Framework — Testing Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback mặc định của test-managed transactions và `TestTransaction`.
- [Testcontainers — Java](https://java.testcontainers.org/): Redis test instance/container lifecycle.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier` và kiểm thử publisher reactive.
- [Redis — Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): slot constraints cho multi-key operations và Lua.
