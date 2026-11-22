# Kiểm thử TTL mà không phụ thuộc chờ cố định dễ sai lệch

Trong Spring Data Redis, **TTL (time to live)** là khoảng thời gian Redis cho phép một key tồn tại trước khi key đó hết hạn. Kiểm thử TTL thường gặp lỗi không ổn định khi viết theo kiểu: đặt TTL 1 giây, `Thread.sleep(1000)`, rồi khẳng định key đã biến mất. Một bài kiểm thử như vậy có thể thành công trên máy cá nhân nhưng thất bại trên CI vì thời gian chạy lệnh, lập lịch luồng, tải máy và thời điểm Redis xử lý key hết hạn không trùng khít với thời gian chờ.

Mục tiêu là kiểm tra **hành vi có thể quan sát được**: key có TTL sau khi ghi, Redis còn trả về giá trị khi key chưa hết hạn, và cuối cùng key không còn truy xuất được trong một khoảng chờ hợp lý. Ta không cần dự đoán chính xác một lệnh sẽ hoàn thành ở mili giây nào.

## 1. Vì sao `sleep` cố định dễ làm kiểm thử thất bại?

Giả sử ứng dụng đặt TTL 1 giây:

```java
redisTemplate.opsForValue().set("otp:123", "654321", Duration.ofSeconds(1));
Thread.sleep(1000);
assertThat(redisTemplate.opsForValue().get("otp:123")).isNull();
```

Đoạn mã này có nhiều vấn đề:

- Lệnh ghi và lệnh đọc đi qua mạng; thời điểm luồng Java ngủ không nhất thiết là mốc chính xác Redis bắt đầu tính TTL.
- Trên CI, luồng kiểm thử có thể bị tạm dừng hoặc được đánh thức muộn; với trường hợp cần xác nhận key **chưa** hết hạn, sự chậm trễ tạo ra kết quả sai.
- Nếu thời gian chờ ngắn hơn thời gian thực tế cần thiết, kiểm thử thất bại ngẫu nhiên. Nếu tăng `sleep` quá dài để “chắc ăn”, toàn bộ bộ kiểm thử chạy chậm.
- Redis có cơ chế hết hạn chủ động và thụ động. Việc dọn dẹp key vật lý hoặc phát sự kiện hết hạn không nhất thiết xảy ra đúng một mốc thời gian tuyệt đối. Tuy nhiên, khi đọc key đã quá hạn, Redis xử lý trạng thái hết hạn và không trả về giá trị cũ.

Đặc biệt, không nên thay `sleep(1000)` bằng `sleep(1200)` rồi xem đó là giải pháp tổng quát. Khoảng đệm có thể giảm tần suất lỗi nhưng vẫn gắn bài kiểm thử với giả định về tốc độ thực thi của môi trường.

## 2. Phân biệt ba trạng thái TTL của Redis

Redis cung cấp các lệnh `TTL` (giây) và `PTTL` (mili giây). Với Spring Data Redis, có thể lấy TTL theo mili giây bằng:

```java
Long remainingMillis = redisTemplate.getExpire(key, TimeUnit.MILLISECONDS);
```

Giá trị trả về có ý nghĩa như sau:

| Giá trị | Ý nghĩa | Cách kiểm thử |
| --- | --- | --- |
| Số dương | Key còn tồn tại và đang có hạn sử dụng | Khẳng định TTL dương; có thể kiểm tra thêm giới hạn phù hợp |
| `-1` | Key tồn tại nhưng không được gắn hạn sử dụng | Khẳng định `-1` khi kiểm tra key lưu vĩnh viễn |
| `-2` | Key không tồn tại, kể cả khi đã hết hạn | Khẳng định `-2` khi kiểm tra kết quả cuối của quá trình hết hạn |
| `0` | Với cách đo theo mili giây, có thể gặp trạng thái sát ranh giới hết hạn | Không nhầm `0` với `-2`; tránh dựa vào mốc thời gian quá sát |

`TTL` tính bằng giây có độ phân giải thô: key còn chưa đến một giây có thể trả về `0`. Vì thế, **ưu tiên `getExpire(..., TimeUnit.MILLISECONDS)`** khi cần quan sát TTL ở mức kiểm thử. Đừng đòi giá trị chính xác bằng TTL cấu hình: độ trễ giữa thao tác ghi và truy vấn khiến thời gian còn lại đã giảm.

Một số câu hỏi cần tách riêng:

1. *Có thiết lập TTL thành công không?* — Sau khi ghi, kiểm tra TTL dương.
2. *Key có thể truy xuất ngay sau khi tạo không?* — Kiểm tra giá trị ngay sau lệnh ghi với TTL đủ rộng.
3. *Key cuối cùng có hết hạn không?* — Chờ theo điều kiện, có thời hạn tối đa.
4. *Gia hạn hoặc xóa TTL có đúng không?* — Đọc lại trạng thái TTL sau thao tác tương ứng, không chờ TTL thực sự chạy hết nếu không cần.

## 3. Dùng polling có timeout thay cho chờ cố định

**Polling** là liên tục kiểm tra một điều kiện với khoảng nghỉ ngắn giữa các lần kiểm tra. Khi điều kiện trở thành đúng, kiểm thử kết thúc ngay; nếu quá thời hạn, kiểm thử thất bại và cho biết điều kiện nào vẫn chưa đạt.

```text
Ghi key kèm TTL
       │
       ▼
Xác nhận key và TTL ban đầu
       │
       ▼
Kiểm tra key đã biến mất? ── Có ──► Thành công
       │
      Chưa
       │
       ▼
Chưa vượt timeout? ─────── Không ──► Thất bại với assertion cuối
       │
       Có
       │
       ▼
Nghỉ một khoảng poll ngắn rồi thử lại
```

Với Java/JUnit, thư viện **Awaitility** cung cấp API rõ ràng cho kiểu kiểm thử này:

```java
await()
    .atMost(Duration.ofSeconds(8))
    .pollInterval(Duration.ofMillis(50))
    .untilAsserted(() ->
        assertThat(redisTemplate.opsForValue().get(key)).isNull()
    );
```

`atMost` là **giới hạn trên**, không phải yêu cầu phải chờ đủ 8 giây. `pollInterval` kiểm soát tần suất truy vấn để tránh bắn lệnh liên tục vào Redis. `untilAsserted` thử lại assertion cho đến khi thành công hoặc hết timeout. Timeout nên rộng hơn TTL kiểm thử và có phần dự phòng cho CI; khoảng poll nên đủ nhỏ để quan sát thay đổi nhưng không quá ngắn để gây tải.

## 4. Ví dụ hoàn chỉnh: JUnit 5 + Spring Data Redis + Testcontainers

Kiểm thử tích hợp cần một Redis thực sự xử lý thời gian hết hạn. Testcontainers giúp tạo Redis riêng cho bộ kiểm thử, tránh phụ thuộc dữ liệu và cấu hình của Redis dùng chung. Ví dụ dưới đây dùng Spring Boot 3.x, Java 21, AssertJ, Awaitility và JUnit 5.

Nếu dự án đã quản lý phiên bản thư viện qua Spring Boot BOM/plugin, có thể khai báo dependencies theo Gradle Groovy như sau:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.awaitility:awaitility'
}
```

Máy chạy kiểm thử cần Docker (hoặc môi trường container tương thích) để khởi động Redis. Nếu dự án đã cung cấp Redis riêng cho integration test, có thể tái sử dụng cấu hình đó thay cho Testcontainers.

```java
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@Testcontainers
@SpringBootTest(classes = RedisTtlIntegrationTest.TestApplication.class)
class RedisTtlIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", () -> REDIS.getMappedPort(6379));
    }

    @Autowired
    StringRedisTemplate redisTemplate;

    @Test
    void keyEventuallyExpiresWithoutFixedSleep() {
        String key = "test:ttl:" + UUID.randomUUID();

        try {
            // SET k value EX/PX: giá trị và TTL được thiết lập cùng thao tác.
            redisTemplate.opsForValue().set(
                key, "payload", Duration.ofMillis(1800)
            );

            assertThat(redisTemplate.opsForValue().get(key))
                .isEqualTo("payload");

            Long initialTtl = redisTemplate.getExpire(
                key, TimeUnit.MILLISECONDS
            );
            assertThat(initialTtl).isNotNull().isPositive();

            // Chờ đến khi Redis không còn trả về key, tối đa 8 giây.
            await()
                .atMost(Duration.ofSeconds(8))
                .pollInterval(Duration.ofMillis(50))
                .untilAsserted(() -> {
                    assertThat(redisTemplate.opsForValue().get(key))
                        .isNull();
                    assertThat(redisTemplate.getExpire(
                        key, TimeUnit.MILLISECONDS
                    )).isEqualTo(-2L);
                });
        } finally {
            redisTemplate.delete(key);
        }
    }

    @Test
    void distinguishesNoExpiryFromMissingKey() {
        String persistentKey = "test:persistent:" + UUID.randomUUID();
        String missingKey = "test:missing:" + UUID.randomUUID();

        try {
            redisTemplate.opsForValue().set(persistentKey, "value");

            assertThat(redisTemplate.getExpire(
                persistentKey, TimeUnit.MILLISECONDS
            )).isEqualTo(-1L);

            assertThat(redisTemplate.getExpire(
                missingKey, TimeUnit.MILLISECONDS
            )).isEqualTo(-2L);
        } finally {
            redisTemplate.delete(persistentKey);
            redisTemplate.delete(missingKey);
        }
    }

    @Test
    void refreshingTtlIncreasesRemainingLifetime() {
        String key = "test:refresh:" + UUID.randomUUID();

        try {
            redisTemplate.opsForValue().set(
                key, "value", Duration.ofSeconds(30)
            );
            Long before = redisTemplate.getExpire(
                key, TimeUnit.MILLISECONDS
            );
            assertThat(before).isNotNull().isPositive();

            assertThat(redisTemplate.expire(key, Duration.ofSeconds(60)))
                .isTrue();

            Long after = redisTemplate.getExpire(
                key, TimeUnit.MILLISECONDS
            );
            assertThat(after).isNotNull().isGreaterThan(before);
        } finally {
            redisTemplate.delete(key);
        }
    }
}
```

### Điều gì khiến ví dụ trên ổn định hơn?

- **Tạo key độc lập:** hậu tố UUID giúp các test chạy song song không vô tình ghi đè key của nhau.
- **Ghi giá trị và TTL trong một thao tác:** `opsForValue().set(key, value, Duration)` loại bỏ khoảng trống giữa lệnh `SET` và `EXPIRE` nếu ứng dụng muốn cả hai có hiệu lực cùng lúc.
- **Kiểm tra tín hiệu thay vì đếm thời gian:** bài test hết hạn chờ `get(key) == null` và TTL `-2`; nó có thể kết thúc ngay sau khi điều kiện đạt.
- **Đặt timeout hữu hạn:** nếu TTL không được thiết lập hoặc Redis bị lỗi, kiểm thử thất bại trong thời gian giới hạn.
- **Không chờ hết 30/60 giây để thử gia hạn:** hai lần đọc TTL đã đủ xác nhận gia hạn tạo thời gian sống còn lại lớn hơn; một bài test chỉ kiểm tra gia hạn không cần chờ key chết.
- **Dọn dẹp đúng key:** `finally` loại bỏ dữ liệu của test kể cả khi assertion thất bại. Không dùng `FLUSHALL` vì có thể ảnh hưởng các test khác.

Một ứng dụng Spring Boot có cấu hình lớp khởi động riêng có thể thay `TestApplication` bằng lớp cấu hình kiểm thử hiện có. Điều kiện quan trọng là `StringRedisTemplate` thực sự kết nối tới Redis do Testcontainers cung cấp.

## 5. Chọn timeout và độ phân giải thế nào?

Không có con số đúng cho mọi hệ thống. Có thể bắt đầu với các tham số của ví dụ rồi hiệu chỉnh dựa trên loại kiểm thử và hạ tầng:

| Tham số | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| TTL thử nghiệm | 1,8 giây | Đủ dài để xác nhận key tồn tại ngay sau ghi |
| Poll interval | 50 ms | Tần suất kiểm tra vừa phải, không tạo vòng lặp bận |
| Timeout | 8 giây | Giới hạn cho Redis xử lý hết hạn và cho CI có độ trễ |
| Mức so sánh TTL | Mili giây | Tránh sai khác do làm tròn về giây |

Timeout phải là **ngân sách tối đa** cho sự kiện mong đợi. Ví dụ TTL 1,8 giây nhưng `atMost(1.8 giây)` là quá sát ranh giới; việc thực thi chậm một chút có thể khiến thử nghiệm thất bại. Trái lại, TTL 60 giây với timeout 2 phút tạo một test tích hợp rất chậm; hãy dùng TTL ngắn cho bài test hết hạn và TTL dài cho bài test chỉ cần kiểm tra gia hạn.

Không nên đặt `pollInterval` quá nhỏ, chẳng hạn 1 ms, khi các lần poll phải gửi lệnh qua mạng: truy vấn dày gây lãng phí CPU và tăng tải Redis. Cũng không nên chỉ dùng một lần poll sau vài giây vì khi đó việc kiểm thử trở lại gần với `sleep` cố định.

## 6. Những trường hợp dễ nhầm khi kiểm thử TTL

### 6.1. Nhầm “Redis đã hết hạn” với “đã phát sự kiện xóa key”

Redis có thể trả về `null` cho key đã quá hạn khi key được truy cập, trong khi sự kiện keyspace notification hoặc quá trình dọn key không có cùng thời điểm quan sát được. Nếu mục tiêu là kiểm tra dữ liệu cache không còn đọc được, hãy assert qua `GET`/`PTTL`. Nếu mục tiêu là kiểm tra listener xử lý **sự kiện hết hạn**, hãy cấu hình cơ chế thông báo phù hợp rồi kiểm tra việc nhận sự kiện riêng, bằng latch hoặc polling có timeout. Không suy ra listener chắc chắn đã nhận event chỉ từ `get(key) == null`.

Ví dụ, `CountDownLatch.await(timeout, unit)` cho phép chờ một sự kiện và thoát sớm ngay khi sự kiện đến. Đây là chờ có điều kiện, khác với `Thread.sleep` luôn chờ đủ một khoảng bất kể điều gì đã xảy ra. Trong Redis, keyspace notifications còn phụ thuộc cấu hình và có tính chất Pub/Sub; không nên dùng chúng làm tín hiệu đáng tin cậy cho nghiệp vụ yêu cầu giao sự kiện bảo đảm.

### 6.2. Dùng `Clock.fixed()` rồi nghĩ Redis cũng dừng hoặc chạy nhanh thời gian

Một `Clock` được inject vào Java chỉ điều khiển phần mã ứng dụng **đọc clock đó**. Nó không làm đồng hồ của Redis trong container nhảy về tương lai. Tương tự, `StepVerifier.withVirtualTime()` chỉ điều khiển các scheduler Reactor thuộc phạm vi được virtualize; lệnh Redis thật vẫn dùng thời gian thật của server.

Nên tách hai loại kiểm thử:

- **Unit test**: dùng `Clock.fixed()` hoặc fake clock để kiểm tra cách ứng dụng tính thời điểm hết hạn, chọn TTL, hoặc quyết định có gia hạn hay không. Unit test không cần đợi và không chứng minh Redis đã tự xóa key.
- **Integration test**: dùng Redis thật, TTL ngắn và Awaitility để xác nhận các lệnh Redis, serializing, truy xuất cache, repository hoặc hành vi hết hạn hoạt động đúng cùng nhau.

Với `@Cacheable`, cấu hình `RedisCacheManager` hoặc repository dùng `@TimeToLive`, hãy kiểm tra TTL trên **key thực tế được tạo ra** và hành vi đọc ở lớp đang được kiểm thử. Đừng giả định mọi lần đọc cache sẽ tự làm mới TTL; chính sách gia hạn phụ thuộc cách ứng dụng cấu hình và ghi key.

### 6.3. Kiểm tra đúng mili giây còn lại

Ví dụ sau rất mong manh:

```java
redisTemplate.opsForValue().set(key, "value", Duration.ofSeconds(5));
assertThat(redisTemplate.getExpire(key, TimeUnit.MILLISECONDS))
    .isEqualTo(5000L); // Dễ sai: TTL đã bắt đầu giảm.
```

Nếu chỉ cần chứng minh đã gắn TTL, kiểm tra `TTL > 0` và (khi phù hợp) `TTL <= 5000`. Nếu yêu cầu nghiệp vụ có ngưỡng tối thiểu hoặc tối đa, chọn một khoảng dung sai dựa trên yêu cầu ấy và chi phí thực thi dự kiến, không gắn chặt assertion vào một giá trị thời gian tuyệt đối. Với các TTL quá ngắn, ngay cả phép kiểm tra dương ngay sau ghi cũng có thể không ổn định; hãy chọn TTL đủ rộng cho loại assertion đó.

### 6.4. Kết luận sai khi key vẫn tồn tại

Khi `PTTL = -1`, key đang tồn tại nhưng **không có hạn sử dụng**; khi `PTTL = -2`, key **không tồn tại**. Nếu key không hết hạn như mong đợi, kiểm tra liệu đoạn mã có vô tình gọi `persist`, `SET` không kèm TTL, ghi đè bằng thao tác làm mất TTL, hoặc tính TTL sai đơn vị hay không. Một số thao tác ghi đè làm thay đổi hoặc xóa TTL cũ, trong khi một số thao tác cập nhật tại chỗ giữ nguyên TTL: hành vi tùy lệnh Redis được sử dụng.

### 6.5. Test chạy song song hoặc dùng Redis chung

Hai test cùng sử dụng key `session:test` có thể tạo kết quả khó lặp lại dù cả hai đều đúng riêng lẻ. Đặt tên key duy nhất, cô lập Redis test và dọn dẹp key sau khi chạy. Tránh phụ thuộc thứ tự test, dữ liệu có sẵn từ lần chạy trước hoặc clock/tải máy của một CI runner cụ thể.

## 7. Khi polling hết timeout, tìm nguyên nhân ở đâu?

Nếu `untilAsserted` vẫn thất bại khi hết thời hạn, kiểm tra theo thứ tự hợp lý:

1. **TTL đã được gắn chưa?** Đọc `PTTL`; giá trị `-1` cho biết không có hạn sử dụng, `-2` cho biết key đã mất.
2. **Đã gắn TTL cho đúng key chưa?** Key cache có thể được thêm prefix, namespace hoặc serializer khác với tên key trong mã nguồn.
3. **Có luồng nào ghi lại key không?** Một job refresh, callback hoặc test khác có thể tạo lại key khiến điều kiện `GET == null` không bao giờ bền vững.
4. **TTL tính theo đơn vị nào?** Sai khác giữa giây và mili giây có thể làm TTL lớn gấp 1.000 lần hoặc gần như bằng 0.
5. **Redis đang dùng có đúng instance không?** Xác nhận host/port của Spring Boot trỏ vào container được khởi động cho test.
6. **Có đang đợi sự kiện khác với việc key không còn đọc được không?** Listener expiration, tác vụ dọn dẹp và `GET` là các tín hiệu khác nhau.

Khi cần điều tra, log các dữ liệu có ý nghĩa như tên key dùng cho test, TTL đọc được, trạng thái `GET`, thời điểm bắt đầu chờ và timeout đã chọn. Có thể ghi nhận các lần poll tại một khoảng vừa phải; tránh log quá dày hay làm thay đổi đáng kể timing của bài kiểm thử.

## 8. Nguyên tắc áp dụng trong dự án

Một kiểm thử TTL tốt thường có ba pha: **thiết lập trạng thái rõ ràng**, **quan sát kết quả bằng điều kiện**, và **giới hạn thời gian chờ**. Đối với Spring Data Redis, kết hợp `set(key, value, Duration)` + `getExpire(..., MILLISECONDS)` + Awaitility là đủ cho phần lớn kiểm thử hết hạn của cache, token, session hoặc dữ liệu tạm.

Hãy chọn loại bằng chứng khớp với điều cần chứng minh: TTL dương cho việc gắn hạn sử dụng, `-1` cho key không TTL, `-2` cùng giá trị `null` cho key đã hết hạn, và sự kiện riêng khi cần xác minh listener. Nhờ đó, bài kiểm thử diễn đạt đúng nghiệp vụ, kết thúc khi điều kiện đạt và ít chịu ảnh hưởng bởi tốc độ máy hay lịch chạy của CI.
