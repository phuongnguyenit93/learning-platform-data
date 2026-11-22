# Đưa Clock vào thiết kế để kiểm thử logic theo thời gian

## 1. Vì sao thời gian là một dependency cần kiểm soát?

Một quy tắc nghiệp vụ thường phụ thuộc vào câu hỏi “**bây giờ là lúc nào?**”: phiên đăng nhập đã hết hạn chưa, đơn hàng còn trong thời gian hủy không, mã giảm giá đã bắt đầu hiệu lực chưa, có được nộp hồ sơ trong ngày chốt không, hay cảnh báo đã quá hạn bao lâu.

Cách viết trực tiếp **Instant.now()**, **LocalDate.now()** hoặc **System.currentTimeMillis()** ở giữa logic khiến test chịu ảnh hưởng của đồng hồ thật. Khi test chuẩn bị giá trị lúc 10:00:00 nhưng code thực thi vài mili giây sau, những phép so sánh sát biên có thể cho kết quả khác dự kiến. Test chạy gần nửa đêm có thể thất bại phụ thuộc thời gian; test chạy ở máy có múi giờ khác cũng có thể đổi kết quả.

Trong Java 17+, **java.time.Clock** là abstraction tiêu chuẩn để lấy thời gian. Ta truyền Clock vào đối tượng nghiệp vụ qua constructor; code sản xuất dùng một Clock thực, còn unit test dùng Clock cố định do test tạo. Đây là một dạng **dependency injection** và **kiểm soát nguồn dữ liệu không xác định**, tương tự việc tiêm repository hoặc random generator.

Sau bài này, bạn có thể:

- Thiết kế service nhận **Clock** thay vì đọc thời gian hệ thống trực tiếp.
- Phân biệt **Instant**, **Duration**, **LocalDate**, **ZoneId** và điều chúng đại diện trong nghiệp vụ.
- Dùng **Clock.fixed(...)** và **Clock.offset(...)** để kiểm thử trước, đúng tại và sau mốc hết hạn.
- Tạo bean Clock bằng Spring Boot, thay Clock trong test tích hợp mà không thay code sản xuất.
- Tránh các lỗi khó nhận ra về múi giờ, daylight saving time (DST), phép cộng ngày và nhiều lần đọc “now”.
- Hiểu giới hạn: Clock chỉ kiểm soát **code thật sự dùng Clock ấy**, không tự đổi thời gian của database, scheduler bên ngoài hoặc dịch vụ thứ ba.

**Mục tiêu không phải “mock mọi lời gọi thời gian”.** Mục tiêu là chuyển quyền lựa chọn nguồn thời gian ra khỏi thuật toán nghiệp vụ, để logic luôn chạy với thời điểm rõ ràng và có thể tái hiện.

## 2. Trước và sau: từ đọc thời gian ngầm sang nhận Clock qua constructor

**Thiết kế dễ gây test thiếu ổn định:**

~~~java
import java.time.Instant;

class ExpirationPolicyBefore {
    boolean expired(Instant expiresAt) {
        return !Instant.now().isBefore(expiresAt);
    }
}
~~~

Nếu test tạo expiresAt bằng Instant.now().plusMillis(1), kết quả có thể đổi theo tốc độ máy và thời điểm scheduling. Nếu đặt expiresAt trong quá khứ rất xa, test có thể ổn định hơn nhưng không chứng minh được quy tắc **đúng tại ranh giới**.

**Thiết kế có thể kiểm thử:**

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

class ExpirationPolicyAfter {
    private final Clock clock;

    ExpirationPolicyAfter(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    boolean expired(Instant expiresAt) {
        Objects.requireNonNull(expiresAt);
        return !clock.instant().isBefore(expiresAt);
    }
}
~~~

Đây là hai class minh họa độc lập về cơ chế, không phải mã Spring Boot đầy đủ. Trong class thứ hai, Clock được inject từ bên ngoài. **clock.instant()** đại diện cho “bây giờ” theo nguồn thời gian đã lựa chọn; test có thể cung cấp Clock cố định tại một thời điểm chính xác.

Dấu so sánh quan trọng: **!now.isBefore(expiresAt)** tương đương **now >= expiresAt**. Nghĩa là phiên **đã hết hạn đúng tại expiresAt**. Một đặc tả khác có thể cho phép dùng đến hết thời điểm ấy; lúc đó điều kiện phải thay đổi và test phải phản ánh yêu cầu. Không tự quyết định dấu bằng từ cách đặt tên “expired”.

Sơ đồ luồng:

~~~text
Ứng dụng Spring Boot                      Unit test
          |                                   |
          v                                   v
    Clock.systemUTC()                 Clock.fixed(t0, UTC)
          |                                   |
          +-----------------+-----------------+
                            |
                            v
                   TokenService(Clock)
                            |
                            v
                       clock.instant()
                            |
                            v
                quy tắc hết hạn / thời gian còn lại
~~~

Logic của TokenService giữ nguyên ở hai môi trường; khác biệt nằm ở Clock được cung cấp.

## 3. Hiểu API java.time.Clock và các loại thời gian

**Clock** là một abstraction có ba khả năng cơ bản: lấy thời điểm tức thời **instant()**, cung cấp múi giờ **getZone()**, và tạo một Clock có múi giờ khác bằng **withZone(...)**. Các factory thường dùng:

| Clock / API | Hành vi | Khi dùng |
|---|---|---|
| Clock.systemUTC() | Đọc thời gian hệ thống, có ZoneOffset.UTC | Bean Clock mặc định cho ứng dụng |
| Clock.system(ZoneId.of("Asia/Ho_Chi_Minh")) | Đọc thời gian hệ thống với zone đã chỉ định | Logic chuyển đổi ngày/giờ theo múi giờ nghiệp vụ |
| Clock.systemDefaultZone() | Phụ thuộc múi giờ hệ điều hành/JVM | Tránh làm mặc định ngầm với nghiệp vụ có quy định zone cụ thể |
| Clock.fixed(instant, zone) | Luôn trả cùng một Instant | Test ở thời điểm xác định, không chờ đợi |
| Clock.offset(baseClock, duration) | Trả thời điểm của baseClock cộng offset | Test trước/sau deadline; nếu baseClock fixed thì kết quả vẫn fixed |
| Clock.tick(baseClock, duration) | Làm tròn/truncated thời gian về bước nhảy xác định | Một số hệ thống cần độ phân giải thô; không thích hợp mặc định cho test so sánh sát mili giây |
| Instant.now(clock) | Lấy Instant theo Clock đã truyền | Viết business code bằng Instant mà vẫn kiểm thử được |
| LocalDate.now(clock) | Lấy ngày ở zone của Clock | Khi “hôm nay” theo múi giờ của Clock là điều mong muốn |

Có hai cách tương đương về ý nghĩa để lấy “now” theo Clock: **clock.instant()** hoặc **Instant.now(clock)**. Hãy chọn nhất quán trong dự án. **Instant.now()** không nhận Clock là lời gọi đọc hệ thống trực tiếp, nên tránh trong các quy tắc cần kiểm thử. **LocalDate.now()** cũng đọc system default zone khi không nhận Clock.

Phân biệt các lớp ngày giờ:

- **Instant:** Điểm thời gian tuyệt đối trên timeline UTC, ví dụ 2026-11-08T10:00:00Z. Thích hợp cho issuedAt, expiresAt, createdAt, thời điểm sự kiện và so sánh hạn dùng tính theo giây/phút.
- **Duration:** Khoảng cách thời gian có độ dài chính xác dựa trên giây/nanosecond, ví dụ 15 phút hoặc 24 giờ.
- **LocalDate:** Ngày theo lịch, ví dụ 2026-11-08; bản thân nó **không có giờ, múi giờ hoặc Instant**. Hợp với ngày chốt sổ/ngày sinh/ngày giao hàng được định nghĩa theo địa phương.
- **LocalDateTime:** Ngày + giờ **không có zone/offset**. Không thể kết luận một LocalDateTime tương ứng với Instant nào khi chưa có quy tắc zone; trong vùng chuyển DST có giờ không tồn tại hoặc xảy ra hai lần.
- **ZonedDateTime:** Ngày giờ gắn ZoneId và quy tắc offset, phù hợp thao tác theo lịch địa phương.
- **ZoneId:** Tên vùng có quy tắc thời gian, ví dụ Asia/Ho_Chi_Minh hoặc America/New_York. ZoneOffset.UTC là offset cố định 0; không đại diện cho các quy tắc DST của một vùng.

**Nên lưu mốc hết hạn dưới dạng Instant** khi yêu cầu là “sau đúng 15 phút”. Với “có thể nộp đến hết ngày 08/11 theo giờ Việt Nam”, hãy dùng **LocalDate + ZoneId** để hiểu chính xác ngày nghiệp vụ, rồi chuyển sang Instant khi cần trao đổi hoặc lưu trữ mốc tuyệt đối.

## 4. Chốt đặc tả trước khi viết test: phép so sánh và mốc biên

Giả sử một phiên được cấp lúc **2026-11-08T10:00:00Z**, có thời hạn **15 phút**. Mốc hết hạn là **2026-11-08T10:15:00Z**.

| Thời điểm kiểm tra | Quan hệ với expiresAt | Mong đợi expired |
|---|---|---|
| 10:00:00Z | Mới cấp | false |
| 10:14:59Z | Trước mốc một giây | false |
| 10:15:00Z | Đúng mốc | true |
| 10:15:01Z | Sau mốc một giây | true |
| 10:16:00Z | Sau mốc một phút | true |

Khi tính “thời gian còn lại”, ví dụ này trả **Duration.ZERO** khi đã hết hạn, thay vì số âm. Đây là **quy tắc của bài**; hệ thống thực tế có thể muốn biểu diễn thời gian đã trễ bằng Duration âm. Không tự sửa expected nếu yêu cầu khác.

Cần có thêm các trường hợp không hợp lệ: thời hạn null, Duration.ZERO và Duration âm; chủ sở hữu phiên thiếu/trống; token giả có expiresAt không sau issuedAt. Các đầu vào này được từ chối rõ ràng để tránh tạo phiên có hạn dùng không hợp lệ.

Ba nhóm test hỗ trợ nhau:
1. **Kiểm tra giá trị khi cấp phiên:** issuedAt đúng bằng Instant do Clock cung cấp, expiresAt đúng bằng issuedAt + TTL.
2. **Kiểm tra biên khi hết hạn:** false trước mốc, true tại mốc và sau mốc.
3. **Kiểm tra đầu vào và bất biến:** thời hạn phải dương, subject không blank, expiresAt phải sau issuedAt.

Không cần dùng Thread.sleep(...) trong những bài test này. Sleep làm test chậm và dễ flaky vì OS/JVM scheduling, nhất là khi so đúng mốc ngắn.

## 5. Ví dụ dự án Spring Boot 3.3.5 + Java 17 + JUnit Jupiter

Đây là ví dụ có đầy đủ tệp nguồn và test. Dự án chứa một service cấp/kiểm tra phiên và một policy ngày nghiệp vụ; hai quy tắc đều nhận Clock qua constructor. Kiểm thử unit không cần database hoặc mở cổng HTTP.

### 5.1. Cấu trúc tệp

~~~text
settings.gradle
build.gradle
src/main/java/demo/time/TimeTestingApplication.java
src/main/java/demo/time/ApplicationClockConfiguration.java
src/main/java/demo/time/SessionToken.java
src/main/java/demo/time/TokenService.java
src/main/java/demo/time/BusinessDayPolicy.java
src/test/java/demo/time/TokenServiceTest.java
src/test/java/demo/time/BusinessDayPolicyTest.java
src/test/java/demo/time/ClockSpringIntegrationTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'clock-business-testing'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

Spring Boot starter-test cung cấp JUnit Jupiter và các thư viện kiểm thử cần thiết. **useJUnitPlatform()** yêu cầu Gradle chạy test trên JUnit Platform. Ví dụ dùng Gradle 8.x tương thích Spring Boot 3.3.5; nếu dự án có Gradle Wrapper thì ưu tiên dùng Wrapper để các máy có cùng phiên bản Gradle.

**src/main/java/demo/time/TimeTestingApplication.java**

~~~java
package demo.time;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TimeTestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TimeTestingApplication.class, args);
    }
}
~~~

**src/main/java/demo/time/ApplicationClockConfiguration.java**

~~~java
package demo.time;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ApplicationClockConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

Trong ứng dụng thật, **Clock.systemUTC()** đọc thời gian hệ thống và cung cấp UTC làm zone mặc định. Việc dùng UTC giúp biểu diễn timestamp nhất quán, nhưng không loại bỏ nhu cầu chuyển sang **ZoneId nghiệp vụ** nếu quy tắc dựa trên ngày địa phương. Spring không tự thay mọi lời gọi Instant.now() của thư viện khác chỉ vì ta khai báo bean Clock.

### 5.2. Định nghĩa token và bất biến thời gian

**src/main/java/demo/time/SessionToken.java**

~~~java
package demo.time;

import java.time.Instant;
import java.util.Objects;

public record SessionToken(
        String owner, Instant issuedAt, Instant expiresAt) {

    public SessionToken {
        if (owner == null || owner.isBlank()) {
            throw new IllegalArgumentException("owner must not be blank");
        }
        Objects.requireNonNull(issuedAt, "issuedAt");
        Objects.requireNonNull(expiresAt, "expiresAt");
        if (!expiresAt.isAfter(issuedAt)) {
            throw new IllegalArgumentException(
                    "expiresAt must be after issuedAt");
        }
    }
}
~~~

Java record giúp dữ liệu gần như immutable ở mức các thành phần Instant/String, đồng thời compact constructor giữ bất biến: phải có owner và **expiresAt > issuedAt**. Record không sinh clock; nó chỉ lưu dữ liệu đã nhận. Kiểm tra thuộc tính thời gian ở nơi tạo dữ liệu giúp chặn token có cấu trúc sai.

### 5.3. Service nhận Clock qua constructor

**src/main/java/demo/time/TokenService.java**

~~~java
package demo.time;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class TokenService {

    private final Clock clock;

    public TokenService(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public SessionToken issue(String owner, Duration lifetime) {
        if (lifetime == null || lifetime.isZero()
                || lifetime.isNegative()) {
            throw new IllegalArgumentException(
                    "lifetime must be positive");
        }

        Instant issuedAt = clock.instant();
        Instant expiresAt = issuedAt.plus(lifetime);
        return new SessionToken(owner, issuedAt, expiresAt);
    }

    public boolean isExpired(SessionToken token) {
        Objects.requireNonNull(token, "token");
        Instant now = clock.instant();
        return !now.isBefore(token.expiresAt());
    }

    public Duration remaining(SessionToken token) {
        Objects.requireNonNull(token, "token");
        Instant now = clock.instant();
        Duration left = Duration.between(now, token.expiresAt());
        return left.isNegative() ? Duration.ZERO : left;
    }
}
~~~

Điểm cần chú ý:

- TokenService chỉ phụ thuộc **Clock**. Spring có thể tự inject bean Clock vì class chỉ có một constructor; unit test có thể new TokenService(fixedClock) trực tiếp.
- Trong **issue(...)**, chỉ gọi **clock.instant() đúng một lần** rồi tính expiresAt từ cùng issuedAt. Nếu gọi instant() hai lần, expiresAt có thể phụ thuộc độ trễ giữa hai lời gọi và sinh kết quả khó dự đoán sát biên.
- **isExpired(...)** dùng now >= expiresAt, với mốc đúng bằng expiresAt được coi là đã hết hạn.
- **remaining(...)** có một lần đọc now; dùng Duration.between(now, expiresAt) rồi chặn giá trị âm về ZERO.
- Duration.plus hoặc Instant.plus có thể ném ngoại lệ với giá trị cực lớn vượt miền biểu diễn của Instant; nếu API cho phép TTL do khách hàng cung cấp, nên đặt mức tối đa hợp lệ và test biên đó. Mục tiêu ví dụ là xử lý TTL dương thường dùng, không tuyên bố hỗ trợ mọi Duration có thể biểu diễn.

Ở lớp controller thực tế, có thể nhận thời hạn cấu hình từ application properties rồi truyền vào service. Đừng dùng new Clock hay Instant.now() bên trong mỗi lần gọi nghiệp vụ.

### 5.4. Policy cho ngày nghiệp vụ theo múi giờ cố định

**src/main/java/demo/time/BusinessDayPolicy.java**

~~~java
package demo.time;

import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Objects;

public final class BusinessDayPolicy {

    private final Clock clock;
    private final ZoneId businessZone;

    public BusinessDayPolicy(Clock clock, ZoneId businessZone) {
        this.clock = Objects.requireNonNull(clock, "clock");
        this.businessZone =
                Objects.requireNonNull(businessZone, "businessZone");
    }

    public LocalDate today() {
        return clock.instant().atZone(businessZone).toLocalDate();
    }

    public boolean canSubmitThrough(LocalDate cutoffDate) {
        Objects.requireNonNull(cutoffDate, "cutoffDate");
        LocalDate today = today();
        return !today.isAfter(cutoffDate);
    }
}
~~~

Policy này nhận cả **Clock** và **ZoneId**, vì “hôm nay” là một **ngày theo lịch tại một vùng xác định**, không chỉ là một Instant. Điều kiện canSubmitThrough() có nghĩa “được nộp đến hết ngày cutoffDate, tính theo ngày tại businessZone”. Nếu quy tắc yêu cầu cutoff vào 17:00 ngày đó, cần một mô hình ngày giờ có múi giờ rõ ràng, không dùng trực tiếp logic “đến hết ngày”.

BusinessDayPolicy ở ví dụ là một class thuần Java dùng trong unit test; nó không có @Service. Khi đưa vào ứng dụng Spring, có thể cấu hình một bean riêng với Clock và zone nghiệp vụ lấy từ cấu hình. Không nên ép service nhận múi giờ máy đang chạy một cách ngầm định.

## 6. Unit test: Clock.fixed và Clock.offset để kiểm tra chính xác từng mốc

**src/test/java/demo/time/TokenServiceTest.java**

~~~java
package demo.time;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TokenServiceTest {

    private static final Instant T0 =
            Instant.parse("2026-11-08T10:00:00Z");

    private final Clock fixedClock =
            Clock.fixed(T0, ZoneOffset.UTC);

    @Test
    void issuedAndExpiryTimesComeFromInjectedClock() {
        TokenService service = new TokenService(fixedClock);

        SessionToken token =
                service.issue("alice", Duration.ofMinutes(15));

        assertEquals("alice", token.owner());
        assertEquals(T0, token.issuedAt());
        assertEquals(T0.plus(Duration.ofMinutes(15)), token.expiresAt());
    }

    @ParameterizedTest(name = "{index}: elapsed={0}s => expired={1}")
    @CsvSource({
            "0, false",
            "899, false",
            "900, true",
            "901, true",
            "960, true"
    })
    void expirationBoundary(
            long elapsedSeconds, boolean expectedExpired) {
        SessionToken token = new TokenService(fixedClock)
                .issue("alice", Duration.ofMinutes(15));

        Clock checkingClock = Clock.offset(
                fixedClock, Duration.ofSeconds(elapsedSeconds));

        TokenService checkingService =
                new TokenService(checkingClock);

        assertEquals(expectedExpired, checkingService.isExpired(token));
    }

    @Test
    void remainingTimeIsClampedAtZero() {
        SessionToken token = new TokenService(fixedClock)
                .issue("alice", Duration.ofMinutes(15));

        TokenService before = new TokenService(
                Clock.offset(fixedClock, Duration.ofMinutes(14)));
        TokenService after = new TokenService(
                Clock.offset(fixedClock, Duration.ofMinutes(16)));

        assertEquals(Duration.ofMinutes(1), before.remaining(token));
        assertEquals(Duration.ZERO, after.remaining(token));
    }

    @Test
    void rejectsZeroNegativeAndMissingLifetime() {
        TokenService service = new TokenService(fixedClock);

        assertThrows(IllegalArgumentException.class,
                () -> service.issue("alice", Duration.ZERO));
        assertThrows(IllegalArgumentException.class,
                () -> service.issue("alice", Duration.ofSeconds(-1)));
        assertThrows(IllegalArgumentException.class,
                () -> service.issue("alice", null));
    }

    @Test
    void rejectsBlankOwner() {
        TokenService service = new TokenService(fixedClock);

        assertThrows(IllegalArgumentException.class,
                () -> service.issue("  ", Duration.ofMinutes(15)));
    }

    @Test
    void rejectsInvalidTokenTimeOrder() {
        assertThrows(IllegalArgumentException.class,
                () -> new SessionToken("alice", T0, T0));
    }

    @Test
    void fixedClockDoesNotAdvanceWhenCalledAgain() {
        assertEquals(T0, fixedClock.instant());
        assertEquals(T0, fixedClock.instant());
        assertFalse(new TokenService(fixedClock).isExpired(
                new SessionToken(
                        "alice", T0.minusSeconds(60), T0.plusSeconds(60))));
        assertTrue(new TokenService(fixedClock).isExpired(
                new SessionToken(
                        "alice", T0.minusSeconds(60), T0)));
    }
}
~~~

**Diễn giải test:**

1. issuedAndExpiryTimesComeFromInjectedClock kiểm tra phép tính thời hạn dựa trên đúng T0; không có thời gian thực xen vào.
2. expirationBoundary dùng **@CsvSource** để chạy nhiều invocation của một phương thức, mỗi lần với elapsedSeconds và expectedExpired cụ thể. **899 giây = 14 phút 59 giây** còn hiệu lực; **900 giây** đúng mốc hết hạn; **901 giây** đã quá mốc. Những điểm sát biên phát hiện được lỗi so sánh < và <=.
3. Clock.offset(fixedClock, Duration.ofSeconds(...)) tạo một **Clock mới** ở thời điểm T0 cộng offset. Vì base là fixed clock, các phép kiểm tra vẫn lặp lại được. **Clock.offset không làm fixedClock gốc “chạy nhanh lên” hay thay đổi nó**.
4. remainingTimeIsClampedAtZero chứng minh quy tắc không trả Duration âm.
5. rejectsZeroNegativeAndMissingLifetime cùng rejectsBlankOwner kiểm tra đầu vào sai.
6. fixedClockDoesNotAdvanceWhenCalledAgain cho thấy fixed clock không thay đổi giữa các lời gọi, đồng thời kiểm tra thêm chính ranh giới now == expiresAt.

Tất cả test trên là unit test thuần JUnit Jupiter; không có Spring ApplicationContext, Mockito mock hay Thread.sleep. Điều này giúp test nhanh và khẳng định trực tiếp logic nghiệp vụ của TokenService.

**Đừng dùng Clock.systemUTC() trong test so biên.** Nó vẫn đọc thời gian thật; ở thời điểm bắt đầu và lúc assertion có thể có sai khác. Clock.fixed mới đảm bảo hai lần đọc trả cùng Instant.

## 7. Unit test: ngày nghiệp vụ, múi giờ và chuyển DST

Một thời điểm có thể thuộc **hai ngày lịch khác nhau** ở hai múi giờ. Chẳng hạn 2026-03-08T04:59:59Z là ngày 08/03 ở UTC nhưng vẫn là tối 07/03 tại America/New_York. Một ứng dụng phục vụ nhiều địa phương không nên dùng ZoneId.systemDefault() chỉ vì server chạy ở máy nào đó.

**src/test/java/demo/time/BusinessDayPolicyTest.java**

~~~java
package demo.time;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BusinessDayPolicyTest {

    private static final ZoneId NEW_YORK =
            ZoneId.of("America/New_York");

    @Test
    void oneInstantCanBelongToDifferentCalendarDays() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-03-08T04:59:59Z"),
                ZoneOffset.UTC);

        BusinessDayPolicy inUtc =
                new BusinessDayPolicy(clock, ZoneOffset.UTC);
        BusinessDayPolicy inNewYork =
                new BusinessDayPolicy(clock, NEW_YORK);

        assertEquals(LocalDate.of(2026, 3, 8), inUtc.today());
        assertEquals(LocalDate.of(2026, 3, 7), inNewYork.today());
    }

    @Test
    void deadlineDayIsIncluded() {
        LocalDate cutoff = LocalDate.of(2026, 3, 8);

        BusinessDayPolicy beforeMidnight = new BusinessDayPolicy(
                Clock.fixed(
                        Instant.parse("2026-03-08T04:59:59Z"),
                        ZoneOffset.UTC),
                NEW_YORK);
        BusinessDayPolicy midnight = new BusinessDayPolicy(
                Clock.fixed(
                        Instant.parse("2026-03-08T05:00:00Z"),
                        ZoneOffset.UTC),
                NEW_YORK);
        BusinessDayPolicy nextDay = new BusinessDayPolicy(
                Clock.fixed(
                        Instant.parse("2026-03-09T04:00:00Z"),
                        ZoneOffset.UTC),
                NEW_YORK);

        assertTrue(beforeMidnight.canSubmitThrough(cutoff));
        assertTrue(midnight.canSubmitThrough(cutoff));
        assertFalse(nextDay.canSubmitThrough(cutoff));
    }

    @Test
    void daylightSavingGapDoesNotChangeCalendarDate() {
        Instant beforeTransition =
                Instant.parse("2026-03-08T06:59:59Z");
        Instant afterTransition =
                Instant.parse("2026-03-08T07:00:00Z");

        ZonedDateTime before = beforeTransition.atZone(NEW_YORK);
        ZonedDateTime after = afterTransition.atZone(NEW_YORK);

        assertEquals(1, before.getHour());
        assertEquals(3, after.getHour());
        assertEquals(LocalDate.of(2026, 3, 8), before.toLocalDate());
        assertEquals(LocalDate.of(2026, 3, 8), after.toLocalDate());
    }

    @Test
    void calendarDayAndTwentyFourHoursAreDifferentAtDst() {
        ZonedDateTime noon = ZonedDateTime.of(
                2026, 3, 7, 12, 0, 0, 0, NEW_YORK);

        ZonedDateTime nextCalendarDay = noon.plusDays(1);
        ZonedDateTime twentyFourHoursLater =
                noon.plus(Duration.ofDays(1));

        assertEquals(12, nextCalendarDay.getHour());
        assertEquals(13, twentyFourHoursLater.getHour());
        assertEquals(
                Duration.ofHours(23),
                Duration.between(noon.toInstant(),
                        nextCalendarDay.toInstant()));
    }
}
~~~

**Vì sao deadlineDayIsIncluded hợp lý?** Chính sách canSubmitThrough(cutoffDate) cho phép nộp **trong toàn bộ ngày cutoffDate tại New York**, không chỉ đến nửa đêm mở đầu ngày ấy. Ở năm 2026, New York chuyển sang daylight saving time ngày 08/03; ngày sau bắt đầu lúc **2026-03-09T04:00:00Z** (00:00 theo giờ EDT), nên lúc đó phải trả false cho cutoff ngày 08/03.

**Lưu ý quan trọng về DST:** Khi đồng hồ New York nhảy từ 01:59:59 lên 03:00:00 ngày 08/03/2026, vẫn chỉ trôi qua một giây trên timeline UTC. Vì vậy:
- **plusDays(1)** trên ZonedDateTime tiến một **ngày theo lịch địa phương**.
- **plus(Duration.ofDays(1))** cộng đúng **24 giờ thời gian thực**.
- Ở ngày chuyển DST, khoảng từ 12:00 trưa ngày 07/03 đến 12:00 trưa ngày 08/03 tại New York có độ dài **23 giờ**.

Không dùng Duration.ofDays(1) thay cho “ngày lịch tiếp theo” nếu yêu cầu kinh doanh là theo LocalDate. Ngược lại, với TTL “hiệu lực đúng 24 giờ”, dùng Duration 24 giờ là điều cần thiết, kể cả khi địa phương đang chuyển DST.

## 8. Spring Boot: đưa Clock vào ApplicationContext và thay Clock khi test

Với unit test, new TokenService(Clock.fixed(...)) là đủ. Nhưng nếu muốn kiểm chứng **Spring đã nối đúng bean Clock cho service**, có thể viết một bài test tích hợp nạp ApplicationContext.

**src/test/java/demo/time/ClockSpringIntegrationTest.java**

~~~java
package demo.time;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@Import(ClockSpringIntegrationTest.FixedClockConfig.class)
class ClockSpringIntegrationTest {

    @Autowired
    TokenService tokenService;

    @Test
    void tokenServiceUsesInjectedPrimaryTestClock() {
        SessionToken token =
                tokenService.issue("linh", Duration.ofMinutes(5));

        assertEquals(
                Instant.parse("2026-11-08T10:00:00Z"),
                token.issuedAt());
        assertEquals(
                Instant.parse("2026-11-08T10:05:00Z"),
                token.expiresAt());
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedClockConfig {

        @Bean
        @Primary
        Clock fixedClockForTest() {
            return Clock.fixed(
                    Instant.parse("2026-11-08T10:00:00Z"),
                    ZoneOffset.UTC);
        }
    }
}
~~~

Cơ chế:
- Trong ứng dụng bình thường có bean **applicationClock** từ ApplicationClockConfiguration.
- Test dùng @Import(FixedClockConfig.class) để thêm bean **fixedClockForTest**, được đánh dấu **@Primary**.
- Khi Spring inject dependency theo kiểu Clock vào TokenService, bean @Primary được ưu tiên. Test xác minh bằng issuedAt cố định.
- Hai bean có **tên khác nhau**; không cần bật cơ chế overriding bean definition. Nếu đặt cùng tên mà overriding bị tắt, context có thể không khởi động; hãy dùng @Primary với tên khác hoặc cấu hình thay thế rõ ràng.
- @TestConfiguration chỉ dành cho phạm vi test đã import, tránh vô tình sử dụng Clock cố định trong runtime ứng dụng.
- Đây là **integration test cho wiring Spring**, chậm hơn unit test vì khởi động context. Không cần dùng @SpringBootTest cho từng ca kiểm tra dấu so sánh biên; hãy giữ phần lớn các ca ở unit test.

Nếu ứng dụng có nhiều Clock bean theo mục đích (ví dụ thời gian vận hành và thời gian tính phí), nên đặt @Qualifier hoặc kiểu abstraction theo lĩnh vực để injection không mơ hồ. Việc chọn Clock theo tên bean tình cờ có thể khiến test chạy với nguồn thời gian khác dự định.

## 9. Chạy ví dụ và đọc kết quả

Trong thư mục chứa build.gradle:

~~~bash
./gradlew test
~~~

Trên Windows PowerShell nếu có Gradle Wrapper:

~~~powershell
.\gradlew.bat test
~~~

Các tệp ví dụ mô tả toàn bộ phần mã và Gradle configuration; **./gradlew** chỉ tồn tại khi project đã có Gradle Wrapper. Nếu tạo project từ đầu mà chưa có Wrapper, dùng Gradle tương thích đã cài để tạo Wrapper hoặc chạy gradle test.

Khi các assertion đúng, task test hoàn thành thành công. Xem **build/reports/tests/test/index.html** để kiểm tra số invocation và trạng thái. Trong bảng kết quả, cần tìm được:
- Test cấp phiên trả đúng issuedAt/expiresAt.
- Các ca @CsvSource bao gồm **ngay trước**, **đúng tại** và **ngay sau** mốc hết hạn.
- Test ngày ở UTC và New York tại cùng một Instant.
- Test thời điểm DST chuyển 01:59:59 → 03:00:00 nhưng ngày lịch không đổi.
- Test Spring Boot nhận bean Clock cố định do @Primary cung cấp.

Không đặt một chuỗi stdout/BUILD SUCCESSFUL tuyệt đối vào assertion vì cách Gradle in log phụ thuộc phiên bản và cấu hình; hãy dựa vào exit code và báo cáo test thật.

Để chạy riêng test thời gian mà không phải toàn bộ suite:

~~~bash
./gradlew test --tests demo.time.TokenServiceTest
./gradlew test --tests demo.time.BusinessDayPolicyTest
./gradlew test --tests demo.time.ClockSpringIntegrationTest
~~~

JUnit Jupiter với @CsvSource chạy một invocation cho mỗi dòng dữ liệu; khi lỗi, Gradle/JUnit report giúp chỉ ra elapsedSeconds ứng với kết quả sai. Vì tất cả Instant trong test đều fixed/offset, chạy trên CI ở các múi giờ máy khác nhau sẽ không thay đổi expected.

## 10. Những ranh giới thời gian cần có trong test nghiệp vụ

### 10.1. Hết hạn đúng tại mốc

Đặc tả thường phải trả lời: “Hết hạn khi **now >= expiresAt** hay chỉ khi **now > expiresAt**?” Hai quy tắc khác nhau duy nhất tại thời điểm bằng nhau. Viết test **đúng mốc** là bắt buộc nếu thời gian hết hạn ảnh hưởng quyền truy cập hoặc quyết định tài chính.

Một sai lệch phổ biến là dùng:

~~~java
// Sai với đặc tả "hết hạn ngay tại expiresAt".
return clock.instant().isAfter(expiresAt);
~~~

Dòng này trả false tại now == expiresAt. Để thỏa quy tắc của ví dụ, dùng **!clock.instant().isBefore(expiresAt)**. Đoạn trên chỉ minh họa biểu thức trong một phương thức, không phải chương trình Java độc lập.

### 10.2. Thời gian hiệu lực bằng 0 hoặc âm

Với TTL:
- Duration.ZERO thường khiến token hết hạn ngay lập tức; bài ví dụ **từ chối việc tạo token như vậy**.
- Duration âm có thể tạo expiresAt trước issuedAt, trái với bất biến của SessionToken.
- Duration rất lớn có thể tràn phạm vi của Instant.plus; API production nên định nghĩa TTL tối đa nếu input không đáng tin.
- null là lỗi đầu vào rõ ràng, không nên chuyển ngầm thành TTL mặc định nếu đặc tả không yêu cầu.

Nếu nghiệp vụ cho phép token dùng một lần với TTL = 0, thiết kế và test phải thể hiện quy tắc khác. Không coi hành vi minh họa là tiêu chuẩn cho mọi token.

### 10.3. Ngày cuối tháng, năm nhuận và DST

Với deadline theo lịch, thử các ngày: 28/02, 29/02 ở năm nhuận, 31/12 → 01/01, đúng ngày cutoff và ngày hôm sau; nếu có địa phương chuyển DST, thử vùng giờ cụ thể. Có thể dùng LocalDate.plusDays(1) để chuyển lịch; phép biến đổi sang Instant phải qua ZoneId.

**Không biến LocalDate thành Instant bằng cách ghép bừa 00:00Z.** Ngày 08/11 tại Việt Nam bắt đầu ở 17:00Z của ngày hôm trước vì UTC+7. Nếu chốt giờ địa phương, cần xác định ZoneId rõ ràng.

### 10.4. Nhiều lần đọc “now” trong một transaction

Một lỗi tinh vi:

~~~java
// Hai lần đọc đồng hồ thật có thể thuộc hai thời điểm khác nhau.
Instant start = clock.instant();
doBusinessWork();
Instant end = clock.instant();
~~~

Đoạn trên là minh họa khi thực sự muốn đo hai mốc thời gian khác nhau. Nếu cả hai phép tính đều phải dựa trên **một thời điểm quyết định nghiệp vụ**, nên lấy một Instant duy nhất ở đầu operation và truyền nó vào những hàm tính toán phía sau:

~~~java
Instant decisionTime = clock.instant();
boolean expired = !decisionTime.isBefore(expiresAt);
Duration remaining = Duration.between(decisionTime, expiresAt);
~~~

Các snippet này dùng trong method có biến expiresAt. Cùng một decisionTime tránh tình huống expired được tính trước hạn, còn remaining được tính sau hạn. Khi cần **đo thời gian thực thi** hay timeout chính xác dưới ảnh hưởng điều chỉnh đồng hồ hệ thống, nên cân nhắc nguồn đo elapsed time đơn điệu (như System.nanoTime hoặc Timer/Metric API), chứ Clock wall time không phải công cụ đo performance tuyệt đối chính xác.

## 11. Clock.fixed, Clock.offset và việc mô phỏng thời gian trôi

**Clock.fixed(t0, UTC)** luôn trả t0. Điều này hoàn hảo để test một phép so sánh nhưng không mô phỏng một hệ thống đang chạy trong nhiều bước nếu service giữ cùng instance Clock cố định.

**Clock.offset(base, delta)** cho ra một Clock khác, tại thời gian **base.instant() + delta**. Nếu base là fixed, offset cũng cố định. Nếu base là systemUTC, offset tiếp tục chạy theo đồng hồ hệ thống và **không cho test tất định**. Đừng nhầm offset với “tua” đồng hồ cũ.

Trong TokenServiceTest, việc tạo một TokenService cho Clock lúc cấp và một TokenService khác cho Clock lúc kiểm tra có chủ đích: kiểm tra một token được sinh ở t0 và được kiểm chứng ở các mốc sau. Trong ứng dụng thật, cùng một service sống lâu với một Clock hệ thống, nhưng mỗi lần gọi lại nhận Instant mới.

Nếu cần mô phỏng **một service instance duy nhất** trải qua nhiều thời điểm trong test:
- Có thể truyền một **Clock implementation điều khiển được** trong test (đảm bảo getZone/withZone/instant đúng hợp đồng).
- Hoặc mock Clock bằng Mockito và cấu hình **clock.instant()** trả các giá trị tuần tự cho từng invocation; cần hiểu chính xác số lần gọi.
- Hoặc thiết kế method nghiệp vụ nhận **Instant decisionTime** làm tham số khi bài toán cho phép, rồi test nhiều thời điểm mà không cần Clock biến đổi.

Đây là lựa chọn thiết kế theo phạm vi; không cần tự tạo MutableClock chỉ để test một biểu thức hết hạn có thể kiểm bằng Clock.fixed.

## 12. Tách “đồng hồ” khỏi “quy tắc ngày giờ”

Với quy tắc cần nhiều phép toán, có thể truyền Clock vào một lớp chuyên trách chính sách thời gian:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.Duration;

final class RenewalPolicy {
    private final Clock clock;

    RenewalPolicy(Clock clock) {
        this.clock = clock;
    }

    boolean canRenew(Instant paidUntil) {
        Instant now = clock.instant();
        Instant renewalWindowStarts =
                paidUntil.minus(Duration.ofDays(7));

        return !now.isBefore(renewalWindowStarts)
                && now.isBefore(paidUntil);
    }
}
~~~

Đây là ví dụ class Java độc lập không cần Spring. Quy tắc: có thể gia hạn **từ đúng 7×24 giờ trước paidUntil đến ngay trước paidUntil**; đúng tại paidUntil thì không còn trong cửa sổ. Một nghiệp vụ khác có thể muốn “bắt đầu từ đầu ngày lịch thứ bảy trước hạn”, trong trường hợp đó Duration.ofDays(7) chưa phù hợp và cần dùng LocalDate/ZoneId.

Test tối thiểu cho chính sách này nên có:
- trước cửa sổ một giây → false;
- tại cửa sổ mở → true;
- trong cửa sổ → true;
- ngay trước paidUntil → true;
- tại paidUntil và sau đó → false.

Đây là lý do một Clock testable chỉ là **hạ tầng**. Việc chọn phép toán Duration hay LocalDate, dấu so sánh và vùng giờ là **quy tắc nghiệp vụ** phải ghi rõ và kiểm thử.

## 13. Spring Boot: những thành phần Clock không tự kiểm soát

Khai báo một bean Clock là bước tốt nhưng **không làm mọi nguồn thời gian của hệ thống tự động chuyển sang Clock ấy**.

| Nguồn thời gian | Clock injected có kiểm soát trực tiếp không? | Cách xử lý |
|---|---|---|
| TokenService gọi clock.instant() | Có | Test bằng Clock.fixed |
| Service gọi Instant.now() trực tiếp | Không | Refactor để dùng Clock |
| LocalDate.now() trong logic nghiệp vụ | Không | Dùng LocalDate.now(clock) hoặc clock.instant().atZone(zone) |
| Database dùng NOW()/CURRENT_TIMESTAMP | Không | Kiểm soát thời gian DB hoặc điều chỉnh cách lấy timestamp, test tích hợp riêng |
| Hibernate/DB sinh created_at mặc định | Không bảo đảm | Xem nơi timestamp được sinh: JVM, ORM hay DB |
| @Scheduled do scheduler kích hoạt | Clock bean không mặc định tua lịch chạy | Tách phương thức nghiệp vụ khỏi trigger rồi test riêng; integration test scheduling theo cơ chế thực |
| Thư viện JWT tự kiểm tra exp bằng thời gian của nó | Không mặc định | Xem API clock/skew/tolerance mà thư viện JWT hỗ trợ |
| API ngoài có expiry riêng | Không | Dùng stub/contract/integration test đúng boundary; không giả định clock của mình điều khiển họ |
| Phân tích độ trễ, benchmark, timeout | Clock wall time không phải công cụ duy nhất | Dùng timer/monotonic clock và metric phù hợp |

**Ví dụ @Scheduled:** Nếu có một job hàng ngày gửi cảnh báo nợ quá hạn, bạn có thể test hàm **findOverdueInvoices(clock.instant())** bằng thời gian cố định; test riêng việc job được kích hoạt theo cron và zone cấu hình. Đưa Clock vào service không khiến framework tự chạy một trigger đã hẹn trong tương lai.

**Ví dụ database:** Nếu service cấp token bằng clock.instant() nhưng cột created_at dùng DEFAULT CURRENT_TIMESTAMP tại database, hai giá trị có thể khác nhau. Phải thống nhất nguồn thời gian theo đặc tả hoặc chấp nhận và kiểm tra sai số cho phép trong integration test; không viết assertion rằng mọi timestamp DB bằng token issuedAt tuyệt đối.

**Ví dụ tài chính/quy định pháp lý:** Nếu ngày kết sổ phụ thuộc khu vực, lưu ZoneId có quy tắc rõ ràng. Múi giờ “UTC+7” và “Asia/Ho_Chi_Minh” có thể cho cùng offset trong thời gian hiện tại, nhưng offset cố định không biểu đạt toàn bộ lịch sử/quy tắc của một khu vực. Chọn mô hình dựa trên yêu cầu thật.

## 14. Anti-pattern và cách sửa

| Anti-pattern | Hậu quả | Cách sửa |
|---|---|---|
| Instant.now() ở nhiều nhánh nghiệp vụ | Không điều khiển được thời điểm trong test | Inject Clock, lấy now một lần mỗi quyết định |
| Thread.sleep(1000) để test token hết hạn | Chậm, flaky, phụ thuộc scheduler | Dùng Clock.fixed/Clock.offset |
| Mock static Instant.now() toàn bộ test | Ràng buộc vào chi tiết JVM, khó bảo trì | Tiêm Clock vào đối tượng |
| Chỉ thử thời điểm quá hạn xa | Không bắt lỗi > so với >= | Thử trước/tại/sau mốc sát biên |
| Dùng Clock.systemDefaultZone() mà không ghi quy tắc | Kết quả lệch giữa laptop và CI | Chọn ZoneId nghiệp vụ rõ ràng |
| Dùng LocalDateTime cho mốc hết hạn tuyệt đối | Thiếu zone để xác định thời điểm | Lưu Instant hoặc OffsetDateTime/ZonedDateTime khi cần |
| Dùng Duration.ofDays(1) cho ngày lịch qua DST | Có thể lệch giờ địa phương | Dùng LocalDate/Period/plusDays phù hợp |
| Test chỉ assert không ném exception | Bỏ sót expiresAt sai hoặc ngày chốt sai | Assert giá trị cụ thể, dấu biên và dữ liệu zone |
| Định nghĩa test Clock cố định trong config production | Ứng dụng “đứng thời gian” khi triển khai | Dùng production Clock.systemUTC, test @TestConfiguration/@Primary |
| Tạo hai bean Clock mà không có rule chọn | Spring injection mơ hồ | @Primary/@Qualifier rõ ràng |
| Cho rằng Clock bean chi phối DB/JWT/scheduler | Test không bao phủ nguồn thời gian thực | Kiểm tra tích hợp ở mỗi boundary |
| Thử sát biên bằng thời gian thực | Test lúc pass lúc fail | Cố định Instant của test |

**Không dùng test Clock cố định ở production.** Clock.fixed chỉ phù hợp cho mô phỏng và test. Nếu vô tình đưa nó vào cấu hình mặc định, tất cả phiên tạo mới có thể cùng một issuedAt và hệ thống tính “bây giờ” không tiến lên.

## 15. Quy trình áp dụng vào một nghiệp vụ thực tế

Khi cần refactor code đang dùng thời gian hệ thống:
1. **Ghi rõ đặc tả:** Hết hạn tại mốc hay sau mốc? TTL là giây thực hay ngày lịch? Múi giờ nào quyết định hạn? Ai sở hữu mốc thời gian nếu có database/service ngoài?
2. **Tìm nơi lấy thời gian:** Các lời gọi Instant.now(), LocalDate.now(), System.currentTimeMillis() và timestamp từ DB/API. Chọn ranh giới code bạn thực sự có quyền kiểm soát.
3. **Đưa Clock vào constructor:** Dùng field final; tạo bean Clock.systemUTC() ở cấu hình Spring Boot, không để service tự new Clock.
4. **Chuẩn hóa mô hình:** Instant cho timestamp tuyệt đối; Duration cho TTL theo thời gian thực; LocalDate + ZoneId cho hạn theo ngày lịch.
5. **Lấy một “now” cho một quyết định:** Tránh nhiều lần đọc thời gian tạo trạng thái tự mâu thuẫn.
6. **Viết unit test bằng fixed/offset:** Các mốc trước/tại/sau expiry; giá trị đầu vào sai; chuyển ngày, DST và năm nhuận nếu liên quan.
7. **Kiểm thử wiring Spring khi cần:** @TestConfiguration + @Primary hoặc cấu hình thay thế bean phù hợp; không để test gián tiếp dựa vào hệ thống thật.
8. **Kiểm thử ranh giới ngoài:** DB timestamp, scheduler, JWT, API khác, cache TTL; mỗi thành phần có nguồn thời gian và cơ chế đo riêng.
9. **Chạy đúng suite trên CI:** Xem kết quả test, loại bỏ Sleep và phép so sánh phụ thuộc múi giờ máy.
10. **Giữ Clock là dependency có ý nghĩa:** Không thêm abstraction riêng rườm rà nếu java.time.Clock đã giải quyết nhu cầu.

Tự đánh giá: một người sửa **!now.isBefore(expiresAt)** thành **now.isAfter(expiresAt)**. Ca test nào sẽ phát hiện ngay lỗi đó? Chính là **now == expiresAt**. Nếu suite không có ca đó, Clock đã được inject tốt nhưng yêu cầu nghiệp vụ vẫn chưa được chứng minh.

**Tài liệu Java API để tra cứu:** [Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html), [Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html), [Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html), [LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html) và [ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html).