# Kiểm chứng hành vi hết hạn trên đúng repository và phiên bản đang dùng

Khi một session hết hạn trong Spring Session Redis, có thể quan sát thấy ba thời điểm khác nhau: repository ngừng trả session cho ứng dụng, Redis xóa các key lưu session, và ứng dụng nhận event thông báo session đã hết hạn. Ba thời điểm này không nhất thiết trùng nhau. Đặc biệt, `RedisIndexedSessionRepository` giữ hash session lâu hơn thời hạn không hoạt động để có thể xử lý expiration event và dọn index. Vì vậy, chỉ nhìn `TTL` của một key rồi kết luận session còn hợp lệ hay đã hết hạn là chưa đủ.

Muốn kiểm chứng chính xác, trước hết phải xác định ứng dụng đang chạy `RedisSessionRepository` hay `RedisIndexedSessionRepository`, phiên bản Spring Session/Spring Boot nào thực sự được nạp, cấu hình timeout và namespace nào có hiệu lực, rồi kiểm tra riêng hành vi logic, TTL vật lý và event. Không áp dụng chi tiết nội bộ của một repository hoặc một phiên bản cho repository khác.

## 1. Ba khái niệm cần tách biệt khi kiểm chứng

### 1.1. Hết hạn logic của session

Session có `lastAccessedTime` và `maxInactiveInterval`. Thời điểm hết hạn logic được tính theo:

\[
T_{expire}=T_{lastAccessed}+I_{maxInactive}
\]

Khi vượt qua thời điểm này, session không còn hợp lệ để sử dụng. Hợp đồng `SessionRepository.findById(id)` trả về `null` khi không tìm thấy session; các repository Spring Session cần bảo đảm session hết hạn không được trả lại như một session hợp lệ.

Đây là câu hỏi quan trọng nhất đối với bảo mật và xác thực: request kế tiếp có còn được xem là đã đăng nhập không? Nếu repository từ chối session sau timeout, việc key Redis còn tồn tại thêm một khoảng thời gian không có nghĩa người dùng vẫn có thể dùng phiên.

### 1.2. Xóa dữ liệu vật lý trong Redis

Redis dùng TTL để xóa key khi hết hạn. Tùy repository, một session có thể có một key chính và các key phụ để theo dõi expiration hoặc index. TTL của key chính không nhất thiết bằng `maxInactiveInterval`.

Với `RedisIndexedSessionRepository`, tài liệu Spring Session mô tả hash session được đặt TTL dài hơn timeout thực tế năm phút. Một key `expires` riêng được đặt TTL bằng timeout để Redis phát notification khi session đến hạn. Khoảng đệm năm phút giữ dữ liệu session đủ lâu cho quá trình phát event và dọn tài nguyên. Do đó, sau khi timeout 30 phút, hash có thể còn khoảng 5 phút TTL dù `findById` đã không trả session. <Cite refs={ ["turn992581view0"] } />

Không tự động áp dụng quy tắc năm phút này cho `RedisSessionRepository` cơ bản hoặc cho một bản phát hành Spring Session khác nếu tài liệu/API của phiên bản đó không xác nhận. Hãy quan sát key và TTL của chính repository đang chạy.

### 1.3. Event hết hạn

`SessionExpiredEvent` là thông báo vòng đời, thường được phát khi Spring Session nhận Redis keyspace notification và xử lý session tương ứng. Event có thể đến muộn so với hạn logic vì Redis không cam kết phát expired notification chính xác ngay khi TTL chạm 0. Event cũng phụ thuộc repository có hỗ trợ event, Redis notification đã bật và listener đang hoạt động.

Vì vậy, cần kiểm chứng riêng ba câu hỏi:

1. Session có bị từ chối sau timeout không?
2. Redis xóa key vật lý khi nào?
3. Listener nhận `SessionExpiredEvent` khi nào và có nhận được không?

Một kết quả PASS cho câu hỏi thứ nhất không tự chứng minh câu hỏi thứ hai và thứ ba cũng PASS.

## 2. Xác định đúng phiên bản đang chạy

### 2.1. Kiểm tra dependency đã được resolve

Spring Boot thường quản lý phiên bản Spring Session thông qua dependency management/BOM. Không chỉ đọc version được khai báo trong `pom.xml` hoặc `build.gradle`: dependency trực tiếp, BOM, version catalog, dependency constraint hoặc override có thể khiến version thực tế khác với điều bạn nghĩ.

Với Maven, xem dependency tree của đúng module chạy ứng dụng:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.session:spring-session-data-redis
```

Với Gradle, xem dependency đã resolve trong `runtimeClasspath` bằng `dependencyInsight` của dự án. Trong môi trường CI, có thể kiểm tra dependency report hoặc lockfile được sinh từ lần build tương ứng.

Ghi lại ít nhất:

- Phiên bản Spring Boot.
- Phiên bản `spring-session-core` và `spring-session-data-redis` đã resolve.
- Phiên bản Spring Data Redis.
- Phiên bản Redis server hoặc dịch vụ Redis tương thích đang chạy.
- Servlet stack hay Reactive WebFlux stack.

Không lấy phiên bản từ tài liệu `current` rồi giả định dự án cũ có cùng API hoặc cùng cấu trúc key. Chọn tài liệu versioned trùng với artifact đã resolve.

### 2.2. Kiểm tra class repository thực tế

Hai repository Servlet phổ biến có hành vi khác nhau:

| Repository | Mục đích | Session events |
|---|---|---|
| `RedisSessionRepository` | Lưu session Redis cơ bản, tra cứu theo session ID | Không hỗ trợ publish session events |
| `RedisIndexedSessionRepository` | Lưu session kèm index và hỗ trợ quản lý session theo index | Hỗ trợ các event vòng đời như xóa và hết hạn |

Tài liệu API hiện hành ghi rõ `RedisSessionRepository` không hỗ trợ phát session events; `RedisIndexedSessionRepository` triển khai `MessageListener` để nhận thông báo liên quan. <Cite refs={ ["turn455468view0", "turn992581view0"] } />

Có thể ghi log class repository trong lúc khởi động để xác minh cấu hình runtime:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.aop.support.AopUtils;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.SessionRepository;

@Configuration
public class SessionRepositoryDiagnostics {

    private static final Logger log = LoggerFactory.getLogger(SessionRepositoryDiagnostics.class);

    @Bean
    ApplicationRunner logSessionRepository(ApplicationContext context) {
        return args -> context.getBeansOfType(SessionRepository.class)
            .forEach((name, repository) -> log.info(
                "SessionRepository bean {} uses {}",
                name,
                AopUtils.getTargetClass(repository).getName()));
    }
}
```

Chỉ bật log chẩn đoán phù hợp với môi trường. Không log session ID hoặc session attribute nhạy cảm. Nếu ứng dụng tự khai báo repository hoặc có nhiều `ApplicationContext`, hãy kiểm tra bean thực sự được `SessionRepositoryFilter` sử dụng.

### 2.3. Xác minh property theo phiên bản

Tên property Spring Boot có thể thay đổi theo dòng phiên bản. Ví dụ, tài liệu Spring Session 3.5.7 minh họa:

```yaml
spring:
  session:
    redis:
      repository-type: indexed
```

Trong tài liệu Spring Session 4.2.0, property được minh họa dưới nhánh `data`:

```yaml
spring:
  session:
    data:
      redis:
        repository-type: indexed
```

Tương ứng, giá trị `default` chọn `RedisSessionRepository`, còn `indexed` chọn `RedisIndexedSessionRepository` trong các cấu hình Boot hỗ trợ property này. Tài liệu 3.5.7 và 4.2.0 trình bày hai prefix khác nhau, vì vậy phải tra đúng reference của phiên bản đang dùng thay vì sao chép cấu hình từ một bài hướng dẫn khác. <Cite refs={ ["turn792350view0", "turn159478view0"] } />

Với cấu hình Java, các phiên bản có thể cung cấp `@EnableRedisIndexedHttpSession` hoặc `@EnableRedisHttpSession(enableIndexingAndEvents = true)`. Hãy kiểm tra API của artifact đang resolve. Không bật đồng thời nhiều cơ chế cấu hình repository nếu chưa xác định rõ bean nào có hiệu lực.

## 3. Xác định timeout có hiệu lực

### 3.1. Đọc cấu hình của ứng dụng

Timeout mặc định thường được đặt qua `spring.session.timeout` trong Spring Boot hoặc `maxInactiveIntervalInSeconds` trên annotation cấu hình Spring Session. Timeout cũng có thể được đặt riêng cho từng session qua Servlet API. Vì vậy, giá trị trong YAML chỉ cho biết mặc định; session đang kiểm thử có thể đã được đặt timeout riêng.

Ví dụ timeout mặc định ngắn trong profile kiểm thử:

```yaml
spring:
  session:
    timeout: 20s
```

Không dùng timeout ngắn này trong production chỉ để quan sát expiration. Giữ cấu hình kiểm thử tách biệt và xác minh giá trị timeout trên session được tạo.

### 3.2. Kiểm tra thuộc tính session

Khi có thể quan sát session trong môi trường test, kiểm tra các giá trị:

- `creationTime`: thời điểm tạo session.
- `lastAccessedTime`: lần truy cập cuối được repository ghi nhận.
- `maxInactiveInterval`: khoảng không hoạt động tối đa.

Với Redis indexed, các trường này thường được lưu trong hash session. Có thể đọc chúng bằng `HGET` hoặc `HGETALL` trong môi trường test. Dữ liệu thuộc tính ứng dụng có thể được serialize, nên tránh dùng `HGETALL` trên production nếu kết quả có thể làm lộ dữ liệu nhạy cảm.

### 3.3. Đảm bảo không có request nền gia hạn phiên

Một test expiration dễ sai nếu trình duyệt, SPA, health check hoặc heartbeat liên tục gửi request kèm session ID. Các request có sử dụng session có thể cập nhật `lastAccessedTime` và gia hạn timeout trượt.

Trong thời gian đo inactivity timeout:

- Dừng polling, heartbeat và request tự động dùng cùng cookie/header.
- Dùng client kiểm thử riêng và chỉ gửi request tại các mốc đã định.
- Không gọi `save(session)` lặp lại trong lúc đang chờ hết hạn.
- Nếu kiểm thử HTTP, đợi response hoàn tất để repository lưu thay đổi trước khi đo TTL.

Nếu không kiểm soát hoạt động nền, kết quả “session chưa hết hạn” có thể chỉ là session vừa được gia hạn.

## 4. Kiểm chứng hành vi logic bằng repository

### 4.1. Kiểm thử `findById` sau timeout

Một kiểm thử tích hợp có thể tạo session với timeout vài giây, lưu vào repository thật đang cấu hình và chờ đến khi `findById` không còn trả session. Ví dụ dùng JUnit, AssertJ và Awaitility:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.awaitility.Awaitility;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.session.Session;
import org.springframework.session.SessionRepository;

@SpringBootTest
class RedisSessionExpirationIntegrationTest {

    @Autowired
    SessionRepository<? extends Session> repository;

    @Test
    void repositoryStopsReturningSessionAfterInactivityTimeout() {
        verifyExpiration(this.repository);
    }

    private static <S extends Session> void verifyExpiration(SessionRepository<S> repository) {
        var session = repository.createSession();
        session.setMaxInactiveInterval(Duration.ofSeconds(3));
        session.setAttribute("testMarker", "expiration-check");
        repository.save(session);

        String sessionId = session.getId();
        assertThat(repository.findById(sessionId)).isNotNull();

        Awaitility.await()
            .atMost(Duration.ofSeconds(20))
            .untilAsserted(() -> assertThat(repository.findById(sessionId)).isNull());
    }
}
```

Kiểm thử này phải chạy với repository và Redis thật tương ứng với profile kiểm thử. `findById` được gọi để xác minh tính hợp lệ logic; nó không yêu cầu key vật lý đã bị xóa ngay lúc đó. Không gọi `save` trong vòng chờ vì việc lưu lại session sẽ cập nhật thời gian truy cập và làm thay đổi hạn.

### 4.2. Kiểm thử qua HTTP và `SessionRepositoryFilter`

Kiểm thử repository trực tiếp chưa xác minh cookie, filter, Spring Security và luồng request. Với ứng dụng web, tạo endpoint test-only có thể ghi một marker vào `HttpSession`, gửi request đầu tiên để nhận cookie, sau đó kiểm tra:

1. Request đầu tiên tạo session và response trả session ID.
2. Request thứ hai dùng cookie cũ đọc lại marker.
3. Không gửi request hoặc heartbeat trong thời gian timeout.
4. Sau timeout, request dùng cookie cũ không còn nhận được trạng thái đã đăng nhập.
5. Nếu gửi request trước khi hết hạn, mốc truy cập cuối được cập nhật và timeout trượt được tính lại.

Kiểm tra trạng thái xác thực ở response hoặc endpoint bảo vệ. Không chỉ kiểm tra cookie còn tồn tại trong client, vì cookie có thể còn được gửi sau khi repository đã từ chối session.

## 5. Kiểm chứng key và TTL trong Redis

### 5.1. Tìm key theo namespace

Spring Session dùng namespace để tách dữ liệu giữa các ứng dụng. Namespace mặc định thường là `spring:session`; nếu cấu hình namespace riêng, mọi lệnh kiểm tra phải dùng đúng prefix đó.

Với repository indexed và namespace mặc định, key session có dạng:

```text
spring:session:sessions:<session-id>
```

Key expiration tương ứng có dạng:

```text
spring:session:sessions:expires:<session-id>
```

Nếu namespace là `portal:session`, prefix trở thành `portal:session:`. Không tìm key bằng cách giả định namespace mặc định khi ứng dụng đã cấu hình namespace riêng.

Trong môi trường test, có thể dùng `SCAN` để tìm key:

```bash
redis-cli --scan --pattern 'spring:session:sessions:*'
```

Tránh dùng `KEYS *` trên Redis production vì lệnh này có thể quét toàn bộ keyspace và ảnh hưởng latency. Khi test, nên dùng namespace riêng và chỉ truy vấn key của session thử nghiệm.

### 5.2. Đọc TTL và kiểu dữ liệu

Ví dụ với một session indexed:

```bash
redis-cli TYPE 'spring:session:sessions:<session-id>'
redis-cli TTL 'spring:session:sessions:<session-id>'
redis-cli PTTL 'spring:session:sessions:<session-id>'
redis-cli TTL 'spring:session:sessions:expires:<session-id>'
```

Các lệnh này giúp xác minh loại key và thời gian sống còn lại. `TTL` trả về số giây nguyên; `PTTL` trả về mili giây. Redis có các giá trị đặc biệt:

| Kết quả | Ý nghĩa |
|---|---|
| Số dương | Thời gian còn lại trước khi key hết hạn |
| `-1` | Key tồn tại nhưng không có expiration |
| `-2` | Key không tồn tại |

TTL giảm liên tục, vì vậy không so sánh một con số duy nhất với timeout rồi kết luận cấu hình sai. Hãy ghi lại thời điểm tạo, timeout, TTL ban đầu và TTL sau các khoảng chờ xác định.

### 5.3. Mẫu TTL riêng của `RedisIndexedSessionRepository`

Trong tài liệu Spring Session 4.2.0, ví dụ timeout là 1.800 giây (30 phút):

| Key | TTL khi lưu session theo ví dụ | Vai trò |
|---|---:|---|
| `sessions:<id>` | 2.100 giây (35 phút) | Hash session được giữ thêm 5 phút sau hạn logic |
| `sessions:expires:<id>` | 1.800 giây (30 phút) | Key theo dõi thời điểm hết hạn logic |
| `expirations:<timestamp>` | Có TTL riêng | Nhóm theo dõi session sắp hết hạn để cleanup |

Khoảng đệm năm phút cho phép Spring Session truy cập dữ liệu phiên để xử lý event và dọn index. `findById` vẫn không trả về session đã hết hạn. <Cite refs={ ["turn992581view0", "turn870753search1"] } />

Với test timeout 20 giây, nếu cùng cơ chế của repository indexed đang được áp dụng, có thể thấy hash còn TTL xấp xỉ 320 giây trong khi expiration key có TTL xấp xỉ 20 giây ngay sau khi lưu. Giá trị thực tế sẽ giảm trong lúc quan sát. Không dùng phép tính này để kết luận cho repository mặc định hoặc một phiên bản có cơ chế lưu expiration khác.

### 5.4. Cẩn trọng với `RedisSessionRepository` cơ bản

`RedisSessionRepository` cơ bản không phát session events và không cung cấp các index như repository indexed. Đừng tìm `expires:<id>` hay `expirations:<timestamp>` rồi kết luận repository bị lỗi nếu các key đó không tồn tại. Hãy kiểm tra đúng kiểu key và TTL được tạo bởi phiên bản đang dùng, đồng thời xác minh `findById` và request HTTP sau timeout.

Tài liệu API hiện hành xác nhận repository cơ bản không publish session events; chi tiết TTL vật lý cần được đối chiếu với API/source version tương ứng. <Cite refs={ ["turn455468view0", "turn159478view0"] } />

## 6. Kiểm chứng event hết hạn

### 6.1. Chỉ kiểm thử event với repository hỗ trợ

Nếu mục tiêu là nhận `SessionExpiredEvent`, phải xác minh ứng dụng đang dùng `RedisIndexedSessionRepository`. `RedisSessionRepository` mặc định không hỗ trợ publish session events. Với indexed repository, Spring Session dùng Redis keyspace notifications và listener để chuyển thông báo thành Spring application event. <Cite refs={ ["turn159478view0", "turn455468view0"] } />

Có thể tạo listener test:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.session.events.SessionExpiredEvent;

@Component
public class SessionExpirationProbe {

    private final BlockingQueue<String> expiredSessionIds = new LinkedBlockingQueue<>();

    @EventListener
    public void onSessionExpired(SessionExpiredEvent event) {
        this.expiredSessionIds.offer(event.getSessionId());
    }

    public BlockingQueue<String> getExpiredSessionIds() {
        return this.expiredSessionIds;
    }
}
```

Trong test, chờ event theo session ID được tạo và timeout ngắn. Không dùng session ID thật trong log hoặc output kiểm thử chia sẻ. Hãy bảo đảm listener không bị đăng ký trùng và không dùng cùng queue giữa các test chạy song song.

### 6.2. Xác minh Redis keyspace notifications

Với indexed repository, các notification `del` và `expired` được dùng để phát event xóa/hết hạn. Một cấu hình Redis thường gặp là:

```text
notify-keyspace-events Egx
```

Trong đó `E` bật keyevent notification, `g` bật generic command như `DEL`, `x` bật expired event. Có thể kiểm tra bằng:

```bash
redis-cli CONFIG GET notify-keyspace-events
```

Nếu Redis được quản lý hoặc khóa lệnh `CONFIG`, cấu hình notification ở phía dịch vụ. `ConfigureRedisAction.NO_OP` chỉ ngăn Spring Session tự thay đổi cấu hình Redis; nó không tự bật các notification cần thiết. Nếu notification chưa được bật, event có thể không đến dù session vẫn hết hạn logic đúng cách.

### 6.3. Không yêu cầu event đến đúng mili giây timeout

Redis không bảo đảm expired notification được phát đúng thời điểm TTL chạm 0. Spring Session indexed có cơ chế theo dõi expiration và tác vụ nền để truy cập các key gần đến hạn, giúp notification được kích hoạt ổn định hơn. Trong các phiên bản hỗ trợ `RedisSessionExpirationStore`, cách theo dõi expiration có thể được cấu hình. <Cite refs={ ["turn159478view0", "turn792350view0"] } />

Khi test, đặt một giới hạn chờ hợp lý cho event thay vì yêu cầu event xuất hiện chính xác ở giây thứ 20. Đồng thời xác minh repository đã từ chối session sau hạn logic, độc lập với thời điểm listener nhận event.

## 7. Khác biệt cần chú ý giữa các phiên bản

### 7.1. API expiration store

Trong API `RedisIndexedSessionRepository`, `setExpirationStore(RedisSessionExpirationStore)` được đánh dấu có từ Spring Session 3.4. Mặc định hiện hành là `MinuteBasedRedisSessionExpirationStore`. Các bản cũ có thể triển khai việc theo dõi expiration nội bộ nhưng không cung cấp cùng extension point công khai. <Cite refs={ ["turn992581view0", "turn792350view0"] } />

Vì vậy, trước khi viết customizer hoặc test kiểm tra expiration store:

- Xác minh version đã resolve có `RedisSessionExpirationStore` hay chưa.
- Đọc API của đúng phiên bản thay vì dùng setter từ tài liệu mới hơn.
- Xác định đang dùng Servlet `RedisIndexedSessionRepository` hay Reactive `ReactiveRedisSessionRepository`.
- Không sao chép cấu trúc expiration store của Reactive sang Servlet nếu chưa đối chiếu API tương ứng.

### 7.2. Thay đổi cách theo dõi expiration

Các phiên bản có thể khác nhau ở cấu trúc theo dõi session sắp hết hạn. Tài liệu Spring Session 3.5 mô tả việc nhóm session theo phút và dùng tác vụ nền truy cập các expiration key. Tài liệu 4.2 tiếp tục mô tả `MinuteBasedRedisSessionExpirationStore` mặc định và cho phép tùy chỉnh bằng `RedisSessionExpirationStore`. Một triển khai khác như `SortedSetRedisSessionExpirationStore` có thể lưu session ID trong Redis Sorted Set theo thời điểm hết hạn. <Cite refs={ ["turn792350view0", "turn159478view0"] } />

Do đó, không viết test phụ thuộc cứng vào tên mọi key phụ trừ khi test đang xác minh chính xác cấu trúc của phiên bản đó. Với kiểm thử nghiệp vụ, ưu tiên `findById`, hành vi HTTP và TTL quan sát được của key session chính. Chỉ kiểm tra key phụ khi đang kiểm thử integration ở mức implementation và đã cố định version.

### 7.3. API thay đổi kiểu dữ liệu

API repository hiện đại dùng `Duration` cho `maxInactiveInterval`; một số overload nhận số nguyên giây đã bị deprecated từ Spring Session 3.0. Annotation Servlet vẫn có thể cung cấp thuộc tính `maxInactiveIntervalInSeconds`. Khi biên soạn test hoặc customizer, kiểm tra kiểu tham số đúng với API đang dùng để tránh lỗi biên dịch hoặc timeout bị quy đổi sai đơn vị. <Cite refs={ ["turn992581view0", "turn455468view0"] } />

## 8. Kiểm thử đồng thời và nhiều instance

### 8.1. Không để request khác vô tình gia hạn session

Khi một session được dùng đồng thời bởi nhiều request, một request có thể cập nhật `lastAccessedTime` trong khi test đang chờ expiration. Kết quả là hạn mới được đẩy về phía trước. Để test ổn định, cô lập client, tắt polling và kiểm tra log request trong khoảng thời gian đo.

### 8.2. Xác minh cùng một Redis và namespace

Với nhiều instance, mỗi instance cần dùng cùng repository type, namespace, serializer và timeout mặc định. Tạo session qua instance A, sau đó gửi request qua B để xác minh B đọc được session. Sau khi hết timeout, gửi ID cũ tới cả A và B; cả hai phải từ chối session theo cùng quy tắc.

Nếu A và B dùng namespace khác nhau, một instance có thể không tìm thấy key do instance kia tạo. Điều này có thể bị hiểu nhầm là expiration sớm. Hãy ghi nhận namespace runtime của từng instance trong chẩn đoán.

### 8.3. Redis Cluster và event cleanup

Tài liệu Spring Session lưu ý `RedisIndexedSessionRepository` với Redis Cluster chỉ subscribe sự kiện từ một node Redis được chọn; index có thể không được dọn nếu sự kiện xảy ra ở node khác. Đây là vấn đề cần kiểm chứng riêng trong test theo topology cluster. Nó không đồng nghĩa với việc có thể bỏ qua kiểm tra `findById` và tính hợp lệ logic của session. <Cite refs={ ["turn159478view0", "turn792350view0"] } />

### 8.4. Độ bền của test

Để test có thể lặp lại:

- Dùng Redis thật qua Testcontainers hoặc môi trường test tương đương với Redis production.
- Cố định Spring Session, Spring Data Redis và Redis server version trong test.
- Dùng namespace riêng cho mỗi test suite.
- Đặt timeout đủ ngắn nhưng vẫn lớn hơn sai số khởi động, network và scheduling.
- Chờ bằng polling/Awaitility thay vì `Thread.sleep` rồi giả định cleanup đã hoàn tất.
- Dọn dữ liệu test sau khi chạy; không xóa key namespace dùng chung với ứng dụng khác.

## 9. Ma trận kiểm chứng theo repository

| Nội dung kiểm tra | `RedisSessionRepository` | `RedisIndexedSessionRepository` |
|---|---|---|
| Xác minh class runtime | Bắt buộc | Bắt buộc |
| Tạo session và timeout ngắn | Có | Có |
| `findById` sau timeout | Kiểm tra hành vi thực tế | Kiểm tra hành vi thực tế; không trả session hết hạn |
| Quan sát TTL key chính | Ghi lại TTL thực tế, không giả định cấu trúc indexed | Kiểm tra hash TTL; tài liệu hiện hành mô tả khoảng đệm 5 phút |
| Tìm key `expires:<id>` | Không giả định key này tồn tại | Có trong mô hình expiration indexed được tài liệu mô tả |
| `SessionExpiredEvent` | Không hỗ trợ publish session events | Hỗ trợ, phụ thuộc keyspace notification và listener |
| Index/principal lookup | Không có khả năng indexed tương ứng | Có index session |
| Test Redis Cluster event cleanup | Không áp dụng như indexed event flow | Kiểm tra subscription và dọn index theo node |

## 10. Quy trình điều tra khi kết quả không như mong đợi

| Triệu chứng | Những điều cần xác minh trước |
|---|---|
| Session bị đăng xuất sớm | Timeout thực tế của session, request có làm mới hay không, namespace và repository type của từng instance |
| Session vẫn được dùng sau thời gian dự kiến | `lastAccessedTime`, timeout riêng của session, request nền và việc filter có dùng repository mong đợi |
| Hash còn tồn tại sau timeout | Repository có giữ hash thêm thời gian để xử lý event không; kiểm tra `findById` trước khi kết luận |
| TTL không bằng timeout cấu hình | Đang xem key nào, repository nào, flush mode nào và có khoảng đệm vật lý hay không |
| Không nhận `SessionExpiredEvent` | Repository có phải indexed không, keyspace notification có bật không, listener/container có hoạt động không |
| Event đến trễ | Redis lazy expiration, expiration store, tác vụ cleanup và tải của listener |
| Test pass nhưng production fail | Redis server/version, managed Redis policy, namespace, cluster topology, dependency runtime và config drift |
| Một instance nhận session, instance khác không nhận | Repository type, namespace, serializer, timeout và phiên bản dependency có đồng nhất không |

Khi điều tra, lưu lại timestamp, repository class, dependency version, timeout, namespace, key pattern, TTL quan sát được và kết quả `findById`. Không lưu session ID thật hoặc nội dung thuộc tính phiên vào log dùng chung.

## 11. Checklist trước khi kết luận expiration đã đúng

1. Đã xác định phiên bản Spring Boot, Spring Session, Spring Data Redis và Redis server thực tế.
2. Đã xác định class repository đang chạy.
3. Đã xác minh property/annotation đúng với phiên bản đó và timeout có hiệu lực trên session thử nghiệm.
4. Đã loại bỏ request nền có thể gia hạn session.
5. Đã kiểm tra `findById` hoặc request HTTP sau timeout để xác minh hết hạn logic.
6. Đã dùng `SCAN`, `TTL`/`PTTL` và key pattern đúng namespace để kiểm tra xóa vật lý.
7. Nếu cần session event, đã xác minh indexed repository, Redis keyspace notifications và listener.
8. Đã phân biệt thời điểm session bị từ chối, key bị xóa và event được phát.
9. Đã chạy kiểm thử qua nhiều instance và đúng topology Redis dự kiến.
10. Đã cố định version trong test để thay đổi implementation có thể được phát hiện khi nâng cấp.

Hành vi hết hạn của Spring Session Redis chỉ có thể được đánh giá đúng khi biết repository và phiên bản cụ thể. `findById` cùng hành vi HTTP xác minh session còn hợp lệ hay không; TTL xác minh vòng đời key vật lý; session event xác minh cơ chế thông báo và cleanup. Với `RedisIndexedSessionRepository`, hash có thể được giữ thêm năm phút và expiration store có thể thay đổi theo phiên bản. Hãy kiểm tra từng lớp riêng biệt để kết luận timeout hoạt động chính xác và có thể lặp lại.

## Tài liệu tham khảo

- [Spring Session 4.2 — Redis Configurations](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session 4.2 — RedisIndexedSessionRepository API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/data/redis/RedisIndexedSessionRepository.html)
- [Spring Session 4.2 — RedisSessionRepository API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/data/redis/RedisSessionRepository.html)
- [Spring Session 3.5 — Redis Configurations](https://docs.spring.io/spring-session/reference/3.5/configuration/redis.html)
- [Spring Session 3.2 — Redis Configurations](https://docs.spring.io/spring-session/reference/3.2/configuration/redis.html)
