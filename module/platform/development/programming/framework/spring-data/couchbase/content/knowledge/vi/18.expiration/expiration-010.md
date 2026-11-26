# Kiểm thử thời gian hết hạn mà không dựa vào chờ tùy tiện

## 1. Vì sao `Thread.sleep` không phải chiến lược kiểm thử TTL?

Trong **Spring Data Couchbase**, một document có thể được gán thời hạn bằng `@Document(expiry = ...)`, SDK `expiry(Duration)`/`expiry(Instant)` hoặc một cơ chế expiry động theo phiên bản. Nếu viết kiểm thử bằng cách tạo document, gọi `Thread.sleep(5000)` rồi khẳng định nó không còn tồn tại, test dễ thất bại ngẫu nhiên hoặc thậm chí **thành công vì lý do sai**.

Ví dụ:

~~~java
// Phản ví dụ: chỉ minh họa cách KHÔNG nên viết integration test.
collection.upsert("otp::test", payload,
        UpsertOptions.upsertOptions().expiry(Duration.ofSeconds(5)));

Thread.sleep(5000);

assertThat(collection.exists("otp::test").exists()).isFalse();
~~~

Có ít nhất năm vấn đề:

1. Thời lượng chờ bắt đầu từ **client**, không phải chính xác thời điểm server ghi expiry.
2. Độ phân giải expiry metadata, đồng hồ client/server và scheduling có sai số.
3. Build agent quá tải có thể khiến thời điểm quan sát thay đổi.
4. Nếu thao tác ghi không đúng keyspace hoặc document chưa từng tồn tại, assertion “không thấy” vẫn có thể vô tình đạt.
5. Nếu sleep cố định quá dài cho mọi trường hợp, bộ test chạy chậm không cần thiết.

Bài **“Kiểm thử thời gian hết hạn mà không dựa vào chờ tùy tiện”** thuộc chương **Thời gian hết hạn** của module **SPRING_DATA_COUCHBASE**. Nội dung kết nối với document mapping, repository, `CouchbaseTemplate`, truy vấn SQL++, thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và reactive API nhằm bảo đảm hiệu năng, nhất quán và khả năng vận hành.

Sau bài, bạn có thể:

- Tách **unit test chính sách thời gian** khỏi **integration test server TTL**.
- Dùng `Clock.fixed` hoặc `Clock.offset` để kiểm tra ranh giới thời gian mà không chờ.
- Đọc `expiryTime()` để chứng minh mutation đã gán hạn trước khi document biến mất.
- Dùng **polling có thời hạn**, điều kiện dừng rõ và độ dung sai hợp lý, thay vì ngủ tùy tiện.
- Kiểm tra expiry của `insert`/`upsert`/`replace`, `preserveExpiry`, `touch` và `getAndTouch`.
- Phân biệt KV expiry với index visibility, cache TTL, concurrency và Query consistency.
- Tránh dùng **Reactor virtual time** để giả vờ tăng tốc đồng hồ của Couchbase Server.

Ví dụ theo phong cách Java 17, Spring Boot 3.x, Spring Data Couchbase 5.x, Couchbase Java SDK 3.x, JUnit 5, AssertJ và Awaitility. API cụ thể cần kiểm tra với dependency đã resolve. Không cần chạy Gradle hay Couchbase Server để hiểu và soạn bài; phần integration test chỉ thực thi khi hạ tầng test đã được chuẩn bị.

## 2. Tách ba loại thời gian cần đo

Đầu tiên, phải biết test muốn xác minh cái gì.

| Lớp thời gian | Câu hỏi | Kỹ thuật phù hợp |
| --- | --- | --- |
| **Thời gian nghiệp vụ** | Session hết hạn lúc nào? OTP có bị gia hạn khi retry không? | `Clock.fixed`, pure functions, unit tests |
| **Expiry metadata của Couchbase** | Server thực sự đã gắn deadline nào? | KV GET với `withExpiry(true)`, so sánh time window |
| **Khả năng đọc sau expiry** | Document cuối cùng không còn được trả về hợp lệ qua KV khi đến hạn? | Bounded polling trên `exists`/`get` |

Ngoài ra còn một lớp khác: **SQL++ index visibility**. Nó cần test riêng vì Query/Index service, scan consistency và index cleanup có semantics khác KV GET.

~~~mermaid
flowchart TD
    A["Yêu cầu kiểm thử expiry"] --> B{"Cần chứng minh điều gì?"}
    B -- "Quy tắc deadline" --> C["Unit test + Clock.fixed"]
    B -- "Mutation đặt hạn đúng" --> D["Đọc expiry metadata"]
    B -- "Document không còn đọc KV" --> E["Polling có deadline"]
    B -- "Query/index thấy thay đổi" --> F["Test SQL++ / consistency riêng"]
    C --> G["Kết quả có thể giải thích"]
    D --> G
    E --> G
    F --> G
~~~

Nếu không tách mục tiêu, một test có thể “đạt” vì KV không tìm thấy document, nhưng chưa từng chứng minh annotation Spring Data đã được mapper sử dụng hoặc `maxTTL` đúng như yêu cầu.

## 3. Ba bất biến cần kiểm tra cho một document hết hạn

Một integration test TTL tốt thường chứng minh theo thứ tự:

1. **Đã ghi thành công:** document thật sự tồn tại ngay sau thao tác, có đúng key và content.
2. **Đã đặt expiry đúng:** metadata expiry nằm trong khoảng dự kiến hoặc trùng deadline tuyệt đối trong độ chính xác hỗ trợ.
3. **Đã hết hiệu lực:** sau deadline, một KV lookup cuối cùng trả not-found trong một khoảng polling hữu hạn.

Ví dụ timeline:

~~~text
T_before       Gửi mutation tới server
T_after        Mutation hoàn tất
T_observe      GET metadata expiry + content
T_expiry       Deadline hiệu lực mà server trả
T_poll         GET/EXISTS lặp có giới hạn sau expiry
T_stop         Assertion đạt hoặc hết test deadline
~~~

Không tự suy `T_expiry = T_before + TTL` chính xác từng mili giây. Với TTL tương đối, thời điểm áp mutation nằm trong một **cửa sổ** liên quan tới request; các API và server có độ phân giải riêng.

## 4. Test thuần không cần cluster: đưa `Clock` vào logic nghiệp vụ

Một session có idle timeout 20 phút và hard lifetime 8 giờ. Logic tính deadline không cần gọi Couchbase:

~~~java
import java.time.Duration;
import java.time.Instant;

public final class ExpirationPolicy {

    private ExpirationPolicy() {
    }

    public static Instant sessionDeadline(
            Instant issuedAt,
            Instant lastActivityAt,
            Duration idleTimeout,
            Duration absoluteLifetime) {

        Instant idleUntil = lastActivityAt.plus(idleTimeout);
        Instant hardUntil = issuedAt.plus(absoluteLifetime);

        return idleUntil.isBefore(hardUntil)
                ? idleUntil
                : hardUntil;
    }

    public static boolean isActive(Instant now, Instant deadline) {
        return now.isBefore(deadline);
    }
}
~~~

Đây là một **pure function**: cùng tham số sẽ cho cùng kết quả, không phụ thuộc timing của CI. Nó phân biệt:

- `issuedAt`: thời điểm phát hành ban đầu, không reset khi hoạt động.
- `lastActivityAt`: sự kiện hợp lệ cuối cùng được phép gia hạn.
- `idleTimeout`: thời lượng từ hoạt động cuối.
- `absoluteLifetime`: trần tính từ lúc phát hành.

### 4.1. Nếu cần đọc thời gian hiện tại trong service

Thay vì gọi `Instant.now()` khắp nơi, inject `Clock`:

~~~java
import java.time.Clock;
import java.time.Instant;

public final class SessionPolicyService {

    private final Clock clock;

    public SessionPolicyService(Clock clock) {
        this.clock = clock;
    }

    public boolean isNotExpired(Instant expiresAt) {
        return Instant.now(clock).isBefore(expiresAt);
    }
}
~~~

Một cấu hình Spring có thể cung cấp bean `Clock.systemUTC()` cho production; test truyền `Clock.fixed(...)`. Đừng tự đổi timezone mặc định của JVM để giả lập deadline nếu logic dùng `Instant`; hãy kiểm thử chuyển đổi timezone ở hàm chuyên trách.

## 5. `Clock.fixed`: kiểm thử đúng ranh giới mà không ngủ

Ví dụ session được cấp lúc 09:00 UTC, hoạt động hợp lệ lúc 16:50. Idle 20 phút nhưng hard deadline 17:00.

~~~java
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ExpirationPolicyTest {

    @Test
    void idleDeadlineIsCappedByAbsoluteLifetime() {
        Instant issued = Instant.parse("2026-12-01T09:00:00Z");
        Instant lastActivity = Instant.parse("2026-12-01T16:50:00Z");

        Instant expiry = ExpirationPolicy.sessionDeadline(
                issued,
                lastActivity,
                Duration.ofMinutes(20),
                Duration.ofHours(8)
        );

        assertThat(expiry).isEqualTo(
                Instant.parse("2026-12-01T17:00:00Z")
        );
    }
}
~~~

Không có chờ đợi. Test không phụ thuộc ngày chạy thật hoặc hiệu năng máy.

### 5.1. Kiểm tra thời điểm ngay trước, đúng tại và sau deadline

~~~java
import java.time.Instant;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ExpirationBoundaryTest {

    @Test
    void deadlineIsExclusive() {
        Instant deadline = Instant.parse("2026-12-01T17:00:00Z");

        assertThat(ExpirationPolicy.isActive(
                deadline.minusNanos(1), deadline)).isTrue();

        assertThat(ExpirationPolicy.isActive(
                deadline, deadline)).isFalse();

        assertThat(ExpirationPolicy.isActive(
                deadline.plusNanos(1), deadline)).isFalse();
    }
}
~~~

Đây là **quy tắc nghiệp vụ** mà bạn có thể định nghĩa chính xác ở cấp nanosecond trong Java. Đừng nhầm độ chính xác này với độ phân giải metadata expiry của Couchbase Server.

### 5.2. `Clock.fixed` cho một service có dependency thời gian

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class SessionPolicyServiceTest {

    @Test
    void checksBoundaryUsingInjectedClock() {
        Instant deadline = Instant.parse("2026-12-01T17:00:00Z");
        Clock before = Clock.fixed(
                deadline.minusSeconds(1), ZoneOffset.UTC);
        Clock at = Clock.fixed(deadline, ZoneOffset.UTC);

        assertThat(new SessionPolicyService(before)
                .isNotExpired(deadline)).isTrue();

        assertThat(new SessionPolicyService(at)
                .isNotExpired(deadline)).isFalse();
    }
}
~~~

Không cần chạy theo thời gian thật. Với một quy tắc thời gian phức tạp, hãy kiểm tra các mốc ranh giới, timezone và dữ liệu không hợp lệ bằng test thuần trước khi thử Couchbase.

## 6. Dùng `Clock.offset` khi muốn giả lập dịch thời gian

`Clock.offset(baseClock, duration)` tạo một đồng hồ cho thấy thời gian dịch so với base clock. Nó hữu ích khi kiểm tra một service dùng `Clock` nhưng cần nhiều kịch bản.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

Clock base = Clock.fixed(
        Instant.parse("2026-12-01T10:00:00Z"),
        ZoneOffset.UTC
);

Clock fiveMinutesLater = Clock.offset(
        base, Duration.ofMinutes(5)
);
~~~

**Ranh giới:** `Clock.offset` chỉ thay cách code Java nhận thời gian từ `Clock`. Nó **không chỉnh đồng hồ Couchbase Server**, không làm expiry pager chạy và không thể biến 5 phút TTL thật thành vài mili giây trong integration test.

Đây là điểm phân biệt quan trọng nhất của bài học.

## 7. Vì sao không dùng `System.setProperty` hoặc thay đồng hồ hệ điều hành?

Có những cách giả lập thời gian gây tác dụng ngoài ý muốn:

- Đổi đồng hồ hệ điều hành để “đẩy” expiry của server có thể làm lệch TLS certificate, log, cluster coordination và cơ chế phân tán.
- Đổi timezone mặc định JVM có thể khiến các test khác phụ thuộc vào môi trường.
- Stub static `Instant.now()` ở khắp nơi làm thiết kế khó hiểu, khó kiểm tra luồng có nhiều thư viện.
- Chạy một server giả không thực hiện Couchbase expiry không thể chứng minh hành vi của Couchbase thật.

**Nguyên tắc:** time travel chỉ ở lớp logic ứng dụng thông qua injected clock. Với integration test expiration trên Couchbase, dùng TTL ngắn có kiểm soát, metadata readback và polling hữu hạn trên server thật.

## 8. Chọn môi trường integration test độc lập

Một cluster Couchbase dùng để test nên có:

- Bucket/scope/collection dành riêng cho test.
- `maxTTL` được biết rõ và tương thích với các test.
- User có RBAC đủ cho thao tác test, không dùng quyền admin production.
- Index được tạo trước nếu có SQL++ test.
- Cơ chế tạo unique key để các test không đạp lên nhau.
- Cleanup an toàn sau test nếu document còn tồn tại.
- Đồng hồ client và server được đồng bộ để so sánh deadline tương đối/tuyệt đối.

Ví dụ:

~~~text
Cluster test
Bucket: integration_test
Scope: expiration
Collections:
  relative_ttl
  fixed_deadline
  max_ttl_10s
  no_default_expiry
~~~

Collection test `max_ttl_10s` chỉ là **tên ví dụ**: tên không tự tạo policy. Phải thực sự cấu hình maxTTL trên server nếu bài test phụ thuộc nó.

Các công cụ như Testcontainers có thể hỗ trợ khởi động Couchbase trong môi trường CI, nhưng phải chuẩn bị bucket/collection, index, feature flags và image version cụ thể. Không nên xây test dựa vào một container không được tạo keyspace hoặc server version khác production.

## 9. Phụ thuộc test: JUnit, AssertJ và Awaitility

Trong dự án Spring Boot, `spring-boot-starter-test` thường cung cấp JUnit 5 và AssertJ. Để polling diễn đạt rõ, có thể thêm **Awaitility** vào test scope nếu chưa có:

~~~xml
<dependency>
    <groupId>org.awaitility</groupId>
    <artifactId>awaitility</artifactId>
    <scope>test</scope>
</dependency>
~~~

Đoạn phụ thuộc trên không chỉ định version vì một số dự án dùng dependency management/BOM. Nếu BOM không quản lý version, build phải khai báo version phù hợp.

Có thể viết polling bằng Java thuần với deadline tổng và khoảng lặp, nhưng Awaitility giúp việc chờ theo **điều kiện quan sát** dễ đọc hơn một chuỗi sleep không giải thích lý do.

### 9.1. Phụ thuộc công cụ không thay test contract

Awaitility không khiến document hết hạn nhanh hơn; nó chỉ giúp **kiểm tra lại cho tới khi điều kiện đạt hoặc hết thời gian chờ**. Test vẫn phải có điều kiện trước hạn và metadata readback để tránh pass giả.

## 10. Tạo key test duy nhất và xác minh ghi thành công

Không sử dụng một key cố định như `otp::test` cho tất cả test chạy song song, vì một test khác có thể xóa hoặc TOUCH key đó.

~~~java
import java.util.UUID;

String key = "expiry-it::" + UUID.randomUUID();
~~~

Một fixture có thể tạo document bằng SDK:

~~~java
import java.time.Duration;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

Duration ttl = Duration.ofSeconds(10);

testCollection.upsert(
        key,
        JsonObject.create()
                .put("kind", "expiry-test")
                .put("marker", "created"),
        UpsertOptions.upsertOptions().expiry(ttl)
);
~~~

**Ngay sau thao tác**, GET và assert content:

~~~java
var initial = testCollection.get(key);
assertThat(initial.contentAsObject().getString("marker"))
        .isEqualTo("created");
~~~

Nếu chỉ kiểm tra `exists(key) == false` sau khi chờ, một test có key sai hoặc write chưa chạy cũng có thể đạt. Đọc trước khi hết hạn chứng minh thao tác tạo đã có hiệu lực.

## 11. Đọc metadata expiry trước khi deadline tới

Couchbase Java SDK 3.x cung cấp khả năng yêu cầu metadata expiry:

~~~java
import com.couchbase.client.java.kv.GetOptions;

var read = testCollection.get(
        key,
        GetOptions.getOptions().withExpiry(true)
);

var expiry = read.expiryTime().orElseThrow();
~~~

`expiryTime()` trong các SDK hỗ trợ trả một giá trị tùy chọn. Nếu test kỳ vọng document **có expiry**, `orElseThrow()` là assertion hợp lý: test thất bại khi metadata không được trả về. Nếu test dành cho document **không TTL**, phải thiết kế assertion khác theo API contract/version thực.

Metadata phải được kiểm tra **sớm**, trước khi document hết hạn. Sau expiry, KV GET có thể báo not-found, nên test sẽ không còn đọc được metadata bằng đường GET thông thường.

## 12. So sánh relative TTL bằng một khoảng thời gian, không so bằng đúng một timestamp

Giả sử server nhận `Duration.ofSeconds(10)`. Ta biết mutation được gọi giữa thời điểm bắt đầu và thời điểm hoàn tất ở client:

~~~java
import java.time.Instant;
import java.time.Duration;

Instant before = Instant.now();

testCollection.upsert(
        key,
        JsonObject.create().put("kind", "expiry-test"),
        UpsertOptions.upsertOptions().expiry(Duration.ofSeconds(10))
);

Instant after = Instant.now();

Instant actual = testCollection.get(
        key,
        GetOptions.getOptions().withExpiry(true)
).expiryTime().orElseThrow();
~~~

Dùng cửa sổ thay vì đòi bằng tuyệt đối:

~~~java
Duration ttl = Duration.ofSeconds(10);
Duration tolerance = Duration.ofSeconds(2);

Instant earliest = before.plus(ttl).minus(tolerance);
Instant latest = after.plus(ttl).plus(tolerance);

assertThat(actual).isBetween(earliest, latest);
~~~

Cửa sổ là ví dụ cho môi trường test tương đối ổn định; **không phải một con số Couchbase cam kết**. Tolerance phải dựa vào độ phân giải SDK/server, đồng bộ đồng hồ và latency của môi trường. Nếu phải tăng tolerance quá lớn, hãy chẩn đoán thay vì làm test mất ý nghĩa.

### 12.1. Đồng hồ giữa client và server

Nếu client và server lệch nhau đáng kể, so sánh `Instant.now()` phía Java với expiry metadata có thể gây false failure. Trước khi nới tolerance, kiểm tra NTP/sự đồng bộ thời gian. Với deadline tuyệt đối, việc định nghĩa `Instant` cũng cần bảo đảm đồng hồ và timezone nhất quán.

## 13. Kiểm tra absolute expiry với `Instant` cố định

Khi nghiệp vụ dùng deadline cố định, test có thể chọn một `Instant` đủ xa trong tương lai để chắc chắn document chưa biến mất trước GET metadata:

~~~java
import java.time.Instant;
import com.couchbase.client.java.kv.UpsertOptions;

Instant deadline = Instant.now().plusSeconds(30);

testCollection.upsert(
        key,
        JsonObject.create().put("type", "absolute"),
        UpsertOptions.upsertOptions().expiry(deadline)
);

Instant actual = testCollection.get(
        key,
        GetOptions.getOptions().withExpiry(true)
).expiryTime().orElseThrow();
~~~

So sánh với độ chính xác SDK/server thực tế:

~~~java
assertThat(actual.getEpochSecond())
        .isEqualTo(deadline.getEpochSecond());
~~~

Dùng `getEpochSecond()` ở đây là **quy ước test theo giây**, không phải khẳng định mọi server version chỉ chính xác đến giây. Nếu maxTTL phía server ngắn hơn, test có thể không giữ deadline đã yêu cầu; cần kiểm tra keyspace policy.

Không dùng một deadline đã qua hoặc quá gần hiện tại cho test metadata vì document có thể hết hạn ngay và không còn đọc được.

## 14. Polling có điều kiện và thời hạn tổng bằng Awaitility

Sau khi đã xác minh document tồn tại và deadline thực, test tiếp tục chờ **trạng thái KV không còn tồn tại**.

~~~java
import java.time.Duration;
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;

await()
        .atMost(Duration.ofSeconds(25))
        .pollInterval(Duration.ofMillis(200))
        .untilAsserted(() -> {
            assertThat(testCollection.exists(key).exists())
                    .isFalse();
        });
~~~

Khác `Thread.sleep`, polling:

- **Dừng sớm** khi điều kiện đạt, không chờ vô ích tới hết 25 giây.
- Có **giới hạn tổng** để test không chạy mãi.
- Lặp lại phép đo theo API thực tế thay vì suy đoán dựa vào đồng hồ client.
- Thất bại rõ ràng nếu điều kiện không xuất hiện trong deadline.

Thời hạn 25 giây ở ví dụ chỉ phù hợp khi test dùng TTL 10 giây và môi trường có dư địa. Nó không phải cấu hình bắt buộc. Tránh polling interval quá ngắn khiến tạo tải không cần thiết lên Data service.

### 14.1. Không cho phép test đậu chỉ vì document chưa tồn tại

**Luôn assert tồn tại ngay sau ghi** trước khi bắt đầu chờ not-found. Nếu dùng thư viện reactive, phải bảo đảm publisher write đã được subscribe/hoàn tất trước phép kiểm tra.

### 14.2. Polling KV không chứng minh xóa vật lý

`exists(key) == false` cho thấy key không tồn tại hợp lệ theo KV tại thời điểm quan sát; không có nghĩa mọi byte đã được purged khỏi storage, replica, backup hoặc downstream caches.

## 15. Ví dụ integration test tương đối hoàn chỉnh

Giả định một fixture `testCollection` được tạo trước bởi test harness, trỏ đúng collection không có maxTTL ngắn hơn TTL test. Test dùng JUnit 5, AssertJ, Awaitility và Couchbase SDK:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

import com.couchbase.client.core.error.DocumentNotFoundException;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.GetOptions;
import com.couchbase.client.java.kv.UpsertOptions;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

class CouchbaseExpiryIntegrationTest {

    private Collection testCollection; // Do fixture test cung cấp.

    @Test
    void expiresAfterRequestedDuration() {
        String key = "expiry-it::" + UUID.randomUUID();
        Duration ttl = Duration.ofSeconds(10);

        try {
            Instant before = Instant.now();
            testCollection.upsert(
                    key,
                    JsonObject.create().put("marker", "written"),
                    UpsertOptions.upsertOptions().expiry(ttl)
            );
            Instant after = Instant.now();

            var initial = testCollection.get(
                    key, GetOptions.getOptions().withExpiry(true));

            assertThat(initial.contentAsObject().getString("marker"))
                    .isEqualTo("written");

            Instant actual = initial.expiryTime().orElseThrow();
            assertThat(actual).isBetween(
                    before.plus(ttl).minusSeconds(2),
                    after.plus(ttl).plusSeconds(2)
            );

            await()
                    .atMost(Duration.ofSeconds(25))
                    .pollInterval(Duration.ofMillis(200))
                    .untilAsserted(() ->
                            assertThat(testCollection.exists(key).exists())
                                    .isFalse()
                    );
        } finally {
            try {
                testCollection.remove(key);
            } catch (DocumentNotFoundException ignored) {
                // Đã expired: không còn gì để cleanup.
            }
        }
    }
}
~~~

**Giới hạn được nêu rõ:** field `testCollection` là fixture chưa được khởi tạo trong snippet, vì việc tạo bucket/scope/collection tùy hạ tầng test của dự án. Đây là code minh họa test method trong lớp được nối với fixture thật, không phải một file chạy standalone nếu không có cluster. Trong CI, cần cấu hình RBAC, time synchronization và server maxTTL phù hợp.

### 15.1. Cleanup chỉ nên xóa key test của chính nó

Không dùng `DELETE FROM collection` hoặc xóa toàn bộ bucket chỉ để cleanup một test. Key mang UUID giúp tránh xung đột và cleanup an toàn.

Nếu thao tác cleanup thất bại do outage, test harness cần ghi nhận failure theo policy; không nên im lặng nuốt mọi lỗi và để lại lượng lớn document test tồn tại lâu dài.

## 16. Test không expiry và server `maxTTL`

Một document không có TTL ở cấp client có thể vẫn bị áp policy mặc định nếu bucket/collection có `maxTTL`.

Kiểm thử “document không có hạn” cần:

1. Một collection test được xác minh có effective maxTTL phù hợp, không buộc TTL.
2. Ghi document không truyền expiry.
3. Đọc metadata theo SDK version để hiểu trường hợp “không có deadline”.
4. Đọc lại sau một khoảng quan sát thích hợp, **không dùng test dài hàng giờ trong CI**.
5. Cleanup key test chủ động.

Đừng cố chứng minh **“tồn tại vĩnh viễn”** bằng một test chạy 30 giây. Test có thể chỉ chứng minh “không gán metadata expiry tại thời điểm quan sát” và “vẫn đọc được sau khoảng ngắn”, trong điều kiện server được kiểm soát.

### 16.1. Test `maxTTL` riêng khỏi TTL của annotation

Nếu collection test có maxTTL 10 giây và client yêu cầu TTL 30 giây, hãy đọc metadata ngay sau ghi để xác nhận policy server đã áp gì. Đừng đợi đúng 30 giây rồi chỉ kết luận “document biến mất sớm”.

~~~text
Client yêu cầu:      30 giây
Server maxTTL:       10 giây
Metadata quan sát:   hạn gần 10 giây từ mutation
~~~

Đây là một **kỳ vọng kiểm chứng** theo cấu hình minh họa, không tự động đúng cho mọi server version/policy/operation. Test phải xác minh chính sách đã được provisioning trước.

## 17. Test `@Document(expiry)` của Spring Data

Một entity có TTL tĩnh:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;

@Document(expiry = 20) // 20 giây theo release hỗ trợ.
public class EphemeralDocument {

    @Id
    private String id;
    private String value;

    protected EphemeralDocument() {
    }

    public EphemeralDocument(String id, String value) {
        this.id = id;
        this.value = value;
    }

    public String getId() { return id; }
    public String getValue() { return value; }
}
~~~

Repository:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface EphemeralRepository
        extends CouchbaseRepository<EphemeralDocument, String> {
}
~~~

Integration test nên:

1. Tạo entity với key duy nhất.
2. Gọi `repository.save(entity)`.
3. Đọc lại bằng repository hoặc SDK GET, xác minh content.
4. Dùng SDK đọc metadata expiry từ **đúng bucket/scope/collection mà entity map tới**.
5. So thời hạn server đã gán với khoảng dự kiến của `@Document(expiry = 20)`.
6. Poll KV sau deadline và xác minh not-found.
7. Cleanup key nếu test thất bại.

Nếu mapping entity nằm ở default collection nhưng SDK đọc ở named collection khác, test có thể đậu “not-found” giả. Bước xác minh content và keyspace là bắt buộc.

### 17.1. Cùng một entity, test create và update riêng

Một lần `repository.save(entity)` khi tạo và một lần `save(entity)` khi cập nhật có thể có semantics expiry khác theo mapper/version. Không suy ra hành vi update từ test insert.

Test riêng:

~~~text
10:00  Save entity mới với TTL 20 giây
10:05  Save entity đã sửa
       → Metadata giữ deadline gốc?
       → Hay reset hạn theo TTL annotation?
       → Có chịu maxTTL?
~~~

Đọc metadata **trước và sau** update để kết luận. Nếu chính sách là deadline cố định, không dùng test chỉ so “document vẫn tồn tại” để khẳng định preservation.

## 18. Test preserve expiry khi cập nhật JSON

Với OTP, cập nhật số lần nhập sai **không được gia hạn**. Có thể dùng `ReplaceOptions.preserveExpiry(true)` cùng CAS:

~~~java
import com.couchbase.client.java.kv.GetOptions;
import com.couchbase.client.java.kv.ReplaceOptions;

var before = otpCodes.get(
        otpKey, GetOptions.getOptions().withExpiry(true));

var oldDeadline = before.expiryTime().orElseThrow();
var updated = before.contentAsObject();

updated.put("failedAttempts", 2);

otpCodes.replace(
        otpKey,
        updated,
        ReplaceOptions.replaceOptions()
                .cas(before.cas())
                .preserveExpiry(true)
);

var after = otpCodes.get(
        otpKey, GetOptions.getOptions().withExpiry(true));

assertThat(after.contentAsObject().getInt("failedAttempts"))
        .isEqualTo(2);

assertThat(after.expiryTime().orElseThrow().getEpochSecond())
        .isEqualTo(oldDeadline.getEpochSecond());
~~~

Test này kiểm tra **cả content và expiry metadata**. Nếu chỉ assert content thì một mutation vô tình reset TTL vẫn có thể đậu.

### 18.1. Dùng key test có TTL đủ dài

Nếu tạo OTP test TTL 1 giây và chạy nhiều thao tác GET/REPLACE/GET, document có thể expire giữa test, gây lỗi không liên quan đến preserve. Chọn TTL đủ dài cho phép quan sát metadata và kiểm thử race trong một test **riêng**.

### 18.2. Test không được tự “hồi sinh” OTP đã hết hạn

Khi document đã expired, `replace` thường trả not-found; không fallback sang `upsert` trừ khi nghiệp vụ thực sự phát hành một challenge mới.

## 19. Test refresh expiry bằng `touch`

Một giỏ hàng có thể được gia hạn sau thao tác sửa hợp lệ:

~~~java
import java.time.Duration;
import com.couchbase.client.java.kv.GetOptions;

Instant oldDeadline = carts.get(
        key,
        GetOptions.getOptions().withExpiry(true)
).expiryTime().orElseThrow();

carts.touch(key, Duration.ofSeconds(20));

Instant newDeadline = carts.get(
        key,
        GetOptions.getOptions().withExpiry(true)
).expiryTime().orElseThrow();
~~~

Test cần xác nhận:

- JSON content không bị TOUCH thay đổi.
- Deadline mới được đặt theo khoảng thời gian yêu cầu.
- Nếu muốn **chứng minh gia hạn về sau**, trước TOUCH phải có đủ thời gian trôi qua hoặc chủ động đặt một deadline ngắn rồi touch dài hơn.
- maxTTL server không giới hạn hành vi khác kỳ vọng.
- Khi key đã hết hạn, TOUCH không tạo document mới.

Một assertion `newDeadline.isAfter(oldDeadline)` chỉ có ý nghĩa nếu setup bảo đảm renewal mới phải muộn hơn. Với TTL mới ngắn hơn, kết quả đúng có thể là **rút ngắn** hạn.

### 19.1. Kiểm tra `getAndTouch` có tác dụng khác `get`

Tạo document có JSON cố định, đọc metadata. Gọi `getAndTouch(id, ttl)`, kiểm tra content trả về và metadata mới. Sau đó gọi `get(id)` thuần và xác nhận nó **không đổi expiry thêm lần nữa**.

Không dùng `getAndTouch` trong helper `readOtp` hoặc `getSessionForAuth` khi nghiệp vụ không cho phép gia hạn trước khi kiểm tra deadline/revoked.

## 20. Test retry không làm trôi deadline cố định

Giả sử OTP được tạo lúc T0, deadline là T0 + 5 phút. Một retry kỹ thuật ở T0 + 30 giây không được biến deadline thành T0 + 5 phút 30 giây.

Unit test có thể chứng minh **chính sách tính một lần**:

~~~java
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class FixedExpiryRetryTest {

    @Test
    void retryKeepsOriginalDeadline() {
        Instant issuedAt =
                Instant.parse("2026-12-01T10:00:00Z");

        Instant fixedDeadline = issuedAt.plus(
                Duration.ofMinutes(5)
        );

        Instant retryAt =
                Instant.parse("2026-12-01T10:00:30Z");

        assertThat(fixedDeadline).isEqualTo(
                Instant.parse("2026-12-01T10:05:00Z")
        );

        assertThat(retryAt.plus(Duration.ofMinutes(5)))
                .isNotEqualTo(fixedDeadline);
    }
}
~~~

Đây mới là kiểm tra phép tính. Để kiểm tra code service **thực sự truyền cùng deadline** vào SDK khi retry, dùng fake/spy ở boundary thích hợp, bắt tham số `Instant` hoặc kiểm tra record một cách độc lập với SDK mock. Sau đó có integration test cho một mutation được phép retry, đọc metadata để phát hiện drift.

### 20.1. Ambiguous mutation timeout

Khi gặp `AmbiguousTimeoutException`, client không biết chắc server đã ghi thành công chưa. Một retry có thể gửi lại operation và thay expiry. Test không nên giả định rằng timeout nghĩa là “không có write”.

Với challenge OTP, dùng identity ổn định, deadline cố định, idempotency và đối soát state. Không tạo challenge mới hoặc gửi mã mới vô điều kiện sau timeout chỉ vì test muốn thao tác có vẻ thành công.

## 21. CAS và document hết hạn giữa hai thao tác

Một tình huống:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant CB as Couchbase
    A->>CB: GET OTP -> CAS c1
    B->>CB: REPLACE OTP -> CAS c2
    A->>CB: REPLACE với CAS c1
    CB-->>A: CAS mismatch
    Note over CB: Trường hợp khác: document expiry trước REPLACE
    A->>CB: REPLACE khi document đã hết hạn
    CB-->>A: Not found
~~~

Không viết test race bằng cách chọn `Thread.sleep(37)` và hy vọng hai request xen vào đúng thời điểm.

Với CAS conflict có thể điều phối deterministically:

1. Tạo document test, đọc CAS c1.
2. Mutation từ writer B dùng CAS c1 thành công, lấy CAS mới.
3. Writer A cố replace với CAS c1 cũ.
4. Assert loại lỗi CAS mismatch theo SDK version.
5. Kiểm tra expiry metadata không bị kéo dài ngoài policy.

**Đây là test cập nhật cạnh tranh**, không cần document thật sự hết hạn trong lúc test.

### 21.1. Race với expiry là test integration riêng

Nếu muốn kiểm tra document biến mất giữa GET/REPLACE, có thể:

- Đọc một document có deadline ngắn còn vài giây.
- Đợi tới khi KV xác nhận document không còn hợp lệ bằng polling có deadline.
- Thử `replace` trên key cũ.
- Assert not-found và **không tự upsert**.

Test này kiểm tra hành vi khi document đã hết hạn. Nó không chứng minh một lịch scheduling nhất định đã tạo ra race giữa đúng hai câu lệnh; nhưng vẫn bao phủ nhánh nghiệp vụ phải xử lý.

## 22. Kiểm thử session với idle và absolute deadline

Session thường có hai điều kiện:

~~~text
issuedAt:           09:00
lastActivityAt:     16:50
idle TTL:           20 phút
absolute lifetime:  8 giờ
idle deadline:      17:10
hard deadline:      17:00
effective expiry:   17:00
~~~

Dùng unit test đã trình bày để tính mốc. Bổ sung một test service:

- Khi `revoked=true`, không gọi mutation gia hạn.
- Khi `now >= hardDeadline`, từ chối ngay.
- Khi còn 10 phút tới hard deadline, không gọi `touch(Duration.ofMinutes(20))` như thể không có trần.
- Khi session chưa hết hạn, mutation đặt `expiry(effectiveInstant)` hoặc option tương đương có kiểm soát.
- Khi CAS conflict, đọc lại và không reset `issuedAt`.

### 22.1. Tách clock nghiệp vụ khỏi đồng hồ server

`Clock.fixed` có thể giả lập việc session hết hạn sau tám giờ **ở tầng Java** trong vài mili giây test. Nhưng nếu code gửi một `Instant` đã quá khứ vào Couchbase test thật, document có thể bị hết hạn ngay; đó không phải cách tăng tốc một bài test idle policy end-to-end.

Thiết kế tốt là có **unit test cho policy** và **integration test cho wiring đến expiry metadata** với deadline thực đủ xa để quan sát.

## 23. Kiểm thử OTP một lần, không chỉ expiry

Một OTP có yêu cầu:

- Hết hạn 5 phút kể từ phát hành.
- Không gia hạn khi nhập sai.
- Số lần thử bị giới hạn.
- Chỉ được sử dụng thành công một lần.

Test cần bao phủ nhiều hơn câu hỏi `exists(key) == false`:

| Kịch bản | Assertion |
| --- | --- |
| Phát hành | Deadline metadata gần `issuedAt + 5m` |
| Nhập sai | Counter thay đổi; deadline không đổi |
| Nhập đúng | Chỉ một state transition thành công |
| Hai request đồng thời | CAS khiến không có hai lần consume thành công |
| Sau deadline | Không xác minh được mã |
| Retry timeout | Không tạo deadline mới |
| Kích hoạt revoke | Không xác minh được dù metadata expiry chưa đến |
| Wrong purpose/subject | Từ chối ngay dù document vẫn tồn tại |

Với deadline và counter, dùng unit test `Clock.fixed`; với CAS one-time transition, dùng integration test hoặc test giả có phiên bản/document state được mô hình hóa. Nếu có external side effect như thanh toán hoặc đặt hàng, dùng idempotency và test flow riêng; CAS trên OTP không tự tạo giao dịch với bên ngoài.

## 24. Test reactive với `StepVerifier.withVirtualTime`: hiểu giới hạn

Reactor có công cụ **virtual time** giúp kiểm tra `Mono.delay`, `Flux.interval` và các operator time-based **trong pipeline** mà không phải đợi đồng hồ thật.

Ví dụ không có Couchbase:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofMinutes(5))
                .thenReturn("EXPIRED")
)
        .expectSubscription()
        .expectNoEvent(Duration.ofMinutes(4))
        .thenAwait(Duration.ofMinutes(1))
        .expectNext("EXPIRED")
        .verifyComplete();
~~~

Điều này xác minh rằng một **publisher trong JVM** phát tín hiệu sau thời lượng virtual được mô phỏng.

**Nó KHÔNG làm Couchbase Server chạy nhanh thêm 5 phút.** Nếu reactive SDK gọi `collection.reactive().get(key)` tới một server thật, kết quả still phụ thuộc đồng hồ server và network. Không viết một test `withVirtualTime` quanh SDK GET rồi kỳ vọng document TTL 5 phút trên server tự hết ngay khi scheduler của Reactor tiến năm phút.

### 24.1. Tách reactive policy và reactive integration

Một thiết kế là:

- Pure function `ExpirationPolicy` dùng `Clock` cho deadline.
- Reactive service gọi policy, sau đó gọi port `SessionStore`.
- Unit test dùng fake port và `StepVerifier` để kiểm tra signal/error, có thể dùng virtual time cho retry delay.
- Integration test dùng reactive SDK thật với TTL ngắn, chờ bằng bounded polling thực.

Đây là sự tách biệt giữa **đồng hồ logic trong JVM** và **metadata expiry trên Couchbase**.

## 25. Reactor retry có thể gia hạn TTL không mong muốn

Giả sử pipeline:

~~~java
Mono<?> write = carts.reactive().upsert(
        key,
        content,
        UpsertOptions.upsertOptions()
                .expiry(Duration.ofMinutes(30))
);
~~~

Nếu publisher bị resubscribe hoặc `retryWhen` gửi lại mutation, một TTL tương đối có thể được áp lần nữa và đẩy deadline ra xa. Đó có thể là hành vi được phép với cart sau thao tác sửa thật, nhưng không đúng với OTP deadline cố định.

Test policy retry nên:

1. Giữ một `Instant fixedDeadline` được tính từ lúc nghiệp vụ phát hành.
2. Dùng cùng instant trong các mutation được phép thử lại.
3. Khẳng định không tạo một ID mới hoặc side effect mới ngoài ý định.
4. Không trộn retry kỹ thuật với quyền renew nghiệp vụ.
5. Đối soát trạng thái nếu mutation timeout mơ hồ.

Không đơn giản thêm `retry(3)` cho mọi lệnh ghi có side effect và cho rằng test sẽ chứng minh hệ thống an toàn.

## 26. Test SQL++ riêng với KV expiry

Một derived repository query hoặc `CouchbaseTemplate` query theo predicate thường sử dụng SQL++/Index service. Khả năng nhìn thấy một mutation hoặc một document đã hết hạn có thể bị ảnh hưởng bởi index propagation, query plan và scan consistency.

Ví dụ:

~~~sql
SELECT META(d).id AS id, d.kind
FROM `integration_test`.`expiration`.`relative_ttl` AS d
WHERE d.kind = "expiry-test";
~~~

Một query không trả row không phải bằng chứng duy nhất rằng document đã hết hạn:

- Secondary index có thể chưa thấy một mutation mới.
- Query trỏ nhầm scope/collection.
- Query/index service có lỗi hoặc query plan không phù hợp.
- Một document có thể hết hạn logic nhưng cleanup/index cập nhật theo cơ chế riêng.

### 26.1. `REQUEST_PLUS` không tăng tốc đồng hồ TTL

Nếu test cần read-after-write qua SQL++, Query service có `QueryScanConsistency.REQUEST_PLUS` theo SDK contract:

~~~java
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryScanConsistency;

var result = cluster.query(
        "SELECT META(d).id AS id " +
        "FROM `integration_test`.`expiration`.`relative_ttl` AS d " +
        "WHERE d.kind = $kind",
        QueryOptions.queryOptions()
                .parameters(
                        JsonObject.create().put("kind", "expiry-test"))
                .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
);
~~~

`REQUEST_PLUS` giúp index đạt mức consistency đối với mutation tại thời điểm request theo semantics Query service. Nó **không buộc expiry pager xóa ngay document khi thời gian vừa qua**, và không thay thế kiểm tra KV + expiry metadata.

### 26.2. Định nghĩa test Query visibility rõ ràng

Nếu cần quan sát độ trễ giữa KV và SQL++, hãy:

1. Tạo key test riêng với TTL và xác minh KV.
2. Dùng query có index đã sẵn sàng và key/marker chỉ dành cho test.
3. Chạy query ở consistency đã định và ghi nhận plan/latency.
4. Sau deadline, poll KV xác nhận document không còn tồn tại hợp lệ.
5. Đo query visibility riêng, ghi rõ đây là quan sát trên cluster/version đó.
6. Không gộp Query visibility với kết luận TTL chính xác từng mili giây.

## 27. Test cache TTL tách khỏi Couchbase TTL

Ứng dụng có thể dùng Caffeine, Redis, Spring `@Cacheable` hoặc `Mono.cache`. TTL của cache ứng dụng là một cơ chế **khác** với expiry metadata Couchbase.

Ví dụ session trong Couchbase đã hết hạn lúc 10:05, nhưng cache lưu bản đọc đến 10:30. Một cache hit có thể trả session đã hết hạn nếu ứng dụng không kiểm tra deadline khi dùng.

Test riêng:

- Cache không trả dữ liệu sau business deadline.
- Logout/revoke làm invalidation theo thiết kế.
- Một cache hit không gọi get-and-touch Couchbase ngoài ý muốn.
- Expiry cache không được tự dùng làm bằng chứng về expiry server.
- Với tài liệu nhạy cảm, không dựa trên cached user profile cũ để bỏ qua kiểm tra phiên tại điểm quyết định.

Đừng dùng `Thread.sleep` 30 phút để test cache expire nếu cache library hỗ trợ fake ticker/virtual clock; chọn cơ chế thời gian của chính cache. Nhưng điều đó vẫn **không** thay đồng hồ Couchbase Server.

## 28. Test độ chính xác theo thời điểm hiệu lực và TOCTOU

Một request có thể đọc OTP trước hạn nhưng xử lý xong sau hạn:

~~~text
T - 100 ms: GET OTP thành công
T:          Deadline OTP
T + 200 ms: Service muốn chấp nhận OTP
~~~

Nếu chính sách “chỉ được chấp nhận trước T”, GET thành công chưa đủ. Test logic nghiệp vụ bằng `Clock.fixed`:

- `now = T - 1 ns` → có thể hợp lệ nếu trạng thái khác đúng.
- `now = T` → từ chối.
- `now = T + 1 ns` → từ chối.

Sau đó test concurrency/CAS với Couchbase theo tài liệu đã đọc; không cố khiến scheduler thực của server đi qua ranh giới nanosecond. Với external side effect, chọn một điểm xác nhận nghiệp vụ rõ ràng và cơ chế transaction/idempotency phù hợp.

## 29. Kiểm tra loại lỗi: not-found không giống timeout

Một test có thể thấy operation không trả document vì nhiều nguyên nhân.

| Lỗi/tín hiệu | Điều được kết luận |
| --- | --- |
| `DocumentNotFoundException` | Key không tồn tại hợp lệ ở thời điểm đọc; có thể expired, removed hoặc chưa từng tồn tại |
| `TimeoutException` | Operation chưa có kết quả trước timeout; chưa biết document còn hay hết |
| `AmbiguousTimeoutException` trên mutation | Không rõ mutation đã được server áp hay chưa |
| CAS mismatch | Một writer khác thay đổi document so với phiên bản đã đọc |
| Query/index error | SQL++ path có vấn đề, không đồng nghĩa TTL sai |
| Scope/collection không tồn tại | Sai setup keyspace; không phải expiry |
| Authentication failure | Lỗi quyền/kết nối, không thể diễn giải là expired |

**Không viết test** kiểu “bắt mọi exception rồi assert expired”. Nó có thể biến cluster outage thành kết quả test đạt.

Một ví dụ phân loại:

~~~java
import com.couchbase.client.core.error.DocumentNotFoundException;

boolean noLongerReadable;

try {
    testCollection.get(key);
    noLongerReadable = false;
} catch (DocumentNotFoundException ex) {
    noLongerReadable = true;
}

assertThat(noLongerReadable).isTrue();
~~~

Code chỉ bắt **not-found**. Các lỗi hạ tầng khác được phép làm test thất bại để phản ánh đúng nguyên nhân.

## 30. Polling cũng có thể sai nếu không đặt ranh giới

Polling không tự là phép màu. Một test `await().until(...)` vẫn có thể flaky hoặc không hữu ích nếu:

1. Điều kiện có thể đạt ngay trước khi dữ liệu được ghi.
2. Timeout tổng ngắn hơn TTL thực.
3. Polling interval quá dày tạo tải lớn lên server.
4. Test đọc sai collection.
5. Test chấp nhận mọi exception như success.
6. Một test khác cùng key đang TOUCH hoặc upsert lại.
7. Đã đổi config maxTTL nhưng fixture không kiểm tra.
8. Test dùng deadline tính theo client mà server/client có clock skew lớn.

Vì vậy luôn thiết kế:

~~~text
Arrange:
  key test duy nhất
  collection test và maxTTL đã biết
  TTL đủ dài cho bước verify ban đầu

Act:
  mutation thành công

Assert trước:
  GET content thành công
  đọc expiry metadata

Assert sau:
  bounded polling cho not-found qua KV

Cleanup:
  chỉ xóa key do chính test tạo
~~~

## 31. Thêm chẩn đoán khi test thất bại

Khi một bài test TTL fail trong CI, thông tin hữu ích gồm:

- Thời điểm bắt đầu/kết thúc mutation (client).
- TTL hoặc `Instant` đã yêu cầu.
- Metadata expiry quan sát được trước expiry.
- Bucket/scope/collection và maxTTL cấu hình test.
- Thời điểm polling bắt đầu, số lần thử, khoảng cách thử.
- Lỗi cuối cùng: not-found, timeout, CAS mismatch hay Query error.
- Server/SDK/Spring Data version và trạng thái cluster test.
- Có thao tác TOUCH/REPLACE/UPSERT cạnh tranh không.

Không log OTP thật, raw session token, mật khẩu hoặc JSON nhạy cảm chỉ để gỡ lỗi thời hạn. Dùng key test không chứa dữ liệu người dùng, correlation ID và giá trị TTL đã được chuẩn hóa.

### 31.1. Lỗi thường gặp

| Hiện tượng | Giả thuyết | Hướng xử lý |
| --- | --- | --- |
| Test đôi khi fail ở đúng 5 giây | Sleep sát ranh giới | Dùng metadata và polling với dư địa |
| Test “đậu” dù write lỗi | Chỉ assert not-found | Assert content tồn tại ngay sau write |
| Fake Clock không làm server expire | Clock chỉ ảnh hưởng Java | Dùng integration TTL thật |
| `StepVerifier.withVirtualTime` không làm mất key | Virtual scheduler không đổi clock Couchbase | Tách reactive policy test |
| Test no-TTL vẫn thấy expiry | Server maxTTL | Kiểm tra effective policy |
| Test preserve thấy deadline dịch | Mutation không preserve hoặc đường mapper khác | Đọc options và metadata trước/sau |
| Test refresh không thấy deadline tăng | TTL mới ngắn hoặc maxTTL chặn | Thiết kế timeline hợp lệ |
| Test Query fail nhưng KV đúng | Index/scan consistency | Test SQL++ riêng |
| CAS conflict không ổn định | Hai thread không được điều phối | Dùng CAS cũ deterministically |
| Test timeout biến thành expired | Catch mọi exception | Phân loại đúng |
| Test chậm toàn suite | TTL quá dài hoặc sleep vô ích | Tách unit/integration, TTL ngắn có kiểm soát |
| Test thay đổi kết quả khi chạy song song | Dùng chung key/collection state | Unique key, fixture độc lập |
| Document expired nhưng disk chưa giảm | Cleanup vật lý khác expiry logic | Đừng assert disk usage như TTL |
| Test kỳ vọng chính xác mili giây | Rounding và clock skew | Tolerance có cơ sở |

## 32. Ma trận kiểm thử tối thiểu cho module

Một bộ test đáng tin cậy nên bao phủ các đường nghiệp vụ:

| Nhóm | Test nhanh (không Couchbase) | Test tích hợp (Couchbase thật) |
| --- | --- | --- |
| TTL tương đối | Validation `Duration`, đơn vị | SDK expiry metadata và KV expiry |
| Deadline tuyệt đối | `Clock.fixed`, timezone, boundary | `expiry(Instant)` metadata |
| Session idle/hard limit | `min(idle, hard)` và revoked | Không renew vượt deadline, CAS |
| OTP one-time | Deadline, max attempts, status | Preserve expiry, consume CAS |
| `@Document(expiry)` | Type/mapping config theo version | Save create/update và metadata |
| TOUCH/GET-AND-TOUCH | Quyết định nghiệp vụ được renew | Expiry trước/sau, JSON không đổi |
| Bucket/collection maxTTL | Configuration contract | Fixture theo policy server, readback |
| Reactive | StepVerifier/virtual time cho publisher | SDK reactive + bounded KV polling |
| SQL++ index | Query builder/sanitization | Query plan/scan consistency riêng |
| Retry/ambiguous | Idempotency/fixed deadline | Tình huống có điều phối hoặc fault injection |
| Cache | Fake ticker/clock của cache | Cache invalidation + backend expiry |

Không cần tất cả test chạy trong mọi commit ở cùng một tầng. Unit tests nên nhanh và deterministically; integration tests có thể chạy trong pipeline riêng với môi trường cố định, nhưng phải đủ để phát hiện sai cấu hình thật.

## 33. Tình huống thực hành: thiết kế lại bộ test lỗi thời gian

Một checkout-service có:

~~~text
commerce.auth.sessions
commerce.auth.otp_challenges
commerce.checkout.carts
commerce.processing.temporary_results
~~~

Chính sách:

- Session: idle 20 phút, hard lifetime 8 giờ.
- OTP: 5 phút từ lúc phát hành, không gia hạn khi nhập sai.
- Cart: 30 phút sau lần sửa hợp lệ.
- Result tạm: 24 giờ sau khi tạo xong.
- Collection `carts` có `maxTTL` 10 phút.
- Các thao tác đi qua repository, SDK blocking và reactive.

Bộ test cũ:

~~~java
// Phản ví dụ có mục đích:
repository.save(entity);
Thread.sleep(5000);
assertThat(repository.findById(entity.getId())).isEmpty();
~~~

**Câu hỏi:**

1. Vì sao test này có thể pass nếu entity chưa từng được lưu thành công?
2. Nếu TTL annotation là 30 giây, tại sao ngủ 5 giây rồi đòi hết hạn là sai?
3. Có cách nào xác nhận mapper đã gắn expiry bằng SDK mà không đợi 30 giây không?
4. Cách test deadline OTP từ lúc phát hành dùng `Clock.fixed` như thế nào?
5. Vì sao `StepVerifier.withVirtualTime` không làm TTL server tiến nhanh?
6. Test gì để chứng minh tăng counter OTP không refresh expiry?
7. Làm thế nào phát hiện một collection `maxTTL` 10 phút làm sai yêu cầu cart 30 phút?
8. Với session hard deadline, nên test chính xác ranh giới ở unit layer hay server layer?
9. Khi kiểm tra Query result khác KV, cần tách những yếu tố nào?
10. Làm thế nào test CAS conflict mà không dùng sleep để tạo race?
11. Một retry sau timeout có thể thay đổi deadline OTP ra sao?
12. Viết lại test TTL đơn giản thành **arrange → write → immediate GET + metadata → bounded poll → cleanup**.

**Định hướng trả lời:**

- Kiểm tra document tồn tại trước khi đợi.
- Dùng Clock cố định cho logic thời gian.
- Đọc expiry metadata ngay sau ghi để chứng minh TTL được áp.
- Poll có thời hạn thay cho sleep tùy tiện.
- Test Query/index và cache riêng với KV.
- Dùng CAS cũ để tạo conflict có thể tái hiện.
- Với OTP dùng fixed deadline và preserve expiry; với cart hiểu server maxTTL.
- Không coi TTL là scheduler hoặc cam kết xóa vật lý ngay.

## 34. Checklist cho một test TTL tốt

- [ ] Test có mục tiêu rõ: tính deadline, metadata hay KV không còn đọc được.
- [ ] Logic thời gian nghiệp vụ đã tách ra để unit test với `Clock.fixed`.
- [ ] Không sửa đồng hồ Couchbase Server để chạy nhanh test.
- [ ] Không dùng `Thread.sleep` làm bằng chứng duy nhất về expiry.
- [ ] Key test là duy nhất và không chứa dữ liệu người dùng thật.
- [ ] Bucket/scope/collection được setup rõ, `maxTTL` được xác minh.
- [ ] Mutation write hoàn tất trước khi GET và polling.
- [ ] Có assertion content tồn tại ngay sau write.
- [ ] Có metadata expiry readback trước khi deadline.
- [ ] So relative TTL bằng cửa sổ thời gian, không từng mili giây.
- [ ] Absolute deadline được kiểm tra với độ chính xác SDK/server hỗ trợ.
- [ ] Polling có atMost và interval hợp lý, không chạy vô hạn.
- [ ] Chỉ coi document-not-found là tín hiệu mất document; không nuốt mọi exception.
- [ ] Không kết luận từ KV not-found rằng dữ liệu đã bị purge khỏi backup.
- [ ] Có test riêng create/update `@Document` và preserve/refresh expiry.
- [ ] Reactive virtual time chỉ dùng cho publisher trong JVM.
- [ ] Không dùng SQL++ scan consistency như công cụ ép expiry pager chạy.
- [ ] Có test CAS conflict bằng cách điều phối trạng thái, không dựa vào sleep.
- [ ] Retry không tạo deadline mới khi chính sách cố định.
- [ ] Kiểm tra cleanup chỉ ảnh hưởng key test.
- [ ] Không biến suite thành các bài đợi nhiều phút khi unit test có thể chứng minh policy.
- [ ] Ghi lại điều kiện test, version và chẩn đoán khi CI lỗi.

## 35. Tổng kết

Kiểm thử expiration trong **Spring Data Couchbase** không nên dựa vào “ngủ N giây rồi hy vọng document biến mất”. Một chiến lược bền vững gồm **hai lớp**:

1. **Unit test với `Clock.fixed`/`Clock.offset`** để kiểm tra chính xác ranh giới deadline, idle TTL, absolute lifetime, OTP không gia hạn và quy tắc retry mà không cần chờ.
2. **Integration test với Couchbase thật** để xác minh thao tác ghi, đọc metadata expiry ngay sau mutation rồi **bounded polling** theo KV cho đến khi document không còn hợp lệ.

Cần tách test SQL++ index visibility, cache và reactive virtual time khỏi đồng hồ expiry của server. Đồng thời, `maxTTL`, CAS, timeout, retry và đường ghi repository/`CouchbaseTemplate`/SDK phải được kiểm chứng trên đúng keyspace và phiên bản.

Khi kiểm tra theo bất biến, đo đúng tầng và chẩn đoán các mốc quan sát một cách có cơ sở, bộ test TTL sẽ nhanh hơn, ít flaky hơn và thực sự bảo vệ vòng đời dữ liệu thay vì chỉ kiểm tra máy CI có chờ đủ lâu hay không.

